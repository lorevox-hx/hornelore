#!/usr/bin/env python3
"""WO-ARCHIVE-AUDIO-01 — end-to-end smoke test for /api/memory-archive/*.

Usage:
    HORNELORE_ARCHIVE_ENABLED=1 ./scripts/run_memory_archive_smoke.py

Requires the stack to be running (http://localhost:8000 by default) with
the archive flag enabled.  Creates a throwaway test narrator + conv_id,
exercises all seven endpoints, and deletes the archive at the end.

Exits 0 on all-green, 1 on any FAIL.  Prints a compact A-H acceptance
block suitable for dropping into the WO report.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import urllib.request
import urllib.error


API = os.environ.get("HORNELORE_API", "http://localhost:8000")
PID = f"smoketest_{uuid.uuid4().hex[:8]}"
CID = f"conv_{uuid.uuid4().hex[:10]}"

# Small silent webm-like payload — not a real webm, just bytes for the
# upload path; the server doesn't decode.
FAKE_AUDIO = b"\x1a\x45\xdf\xa3smoketest\x00" * 64


_results: list[tuple[str, bool, str]] = []


def log(msg: str) -> None:
    print(msg, flush=True)


def check(name: str, cond: bool, detail: str = "") -> None:
    _results.append((name, bool(cond), detail))
    marker = "PASS" if cond else "FAIL"
    log(f"  {marker}  {name}" + (f"  — {detail}" if detail else ""))


def _request(
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    multipart: list[tuple[str, tuple[str, bytes, str]]] | None = None,
    form: dict | None = None,
    expect_ok: bool = True,
) -> tuple[int, dict | bytes | str]:
    url = API.rstrip("/") + path
    headers: dict[str, str] = {}
    data: bytes | None = None

    if json_body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(json_body).encode("utf-8")
    elif multipart is not None or form is not None:
        boundary = f"----smoke{uuid.uuid4().hex}"
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        buf = io.BytesIO()
        if form:
            for k, v in form.items():
                buf.write(f"--{boundary}\r\n".encode())
                buf.write(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode())
                buf.write(str(v).encode("utf-8"))
                buf.write(b"\r\n")
        if multipart:
            for fname, (fn, payload, mime) in multipart:
                buf.write(f"--{boundary}\r\n".encode())
                buf.write(f'Content-Disposition: form-data; name="{fname}"; filename="{fn}"\r\n'.encode())
                buf.write(f"Content-Type: {mime}\r\n\r\n".encode())
                buf.write(payload)
                buf.write(b"\r\n")
        buf.write(f"--{boundary}--\r\n".encode())
        data = buf.getvalue()

    req = urllib.request.Request(url, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            status = resp.status
            raw = resp.read()
            ctype = resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        status = e.code
        raw = e.read() or b""
        ctype = e.headers.get("Content-Type", "") if e.headers else ""

    body: dict | bytes | str
    if "application/json" in ctype:
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = raw
    elif "application/zip" in ctype or status == 200 and b"PK" == raw[:2]:
        body = raw
    else:
        try:
            body = raw.decode("utf-8")
        except UnicodeDecodeError:
            body = raw

    return status, body


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_a_health() -> None:
    log("\n[A] GET /api/memory-archive/health")
    status, body = _request("GET", "/api/memory-archive/health")
    check("A.1 status=200", status == 200, f"got {status}")
    if isinstance(body, dict):
        check("A.2 ok=true", body.get("ok") is True)
        check("A.3 enabled=true (flag was set)", body.get("enabled") is True,
              "Set HORNELORE_ARCHIVE_ENABLED=1 in the server env and restart the stack"
              if not body.get("enabled") else "")
        check("A.4 data_dir present", bool(body.get("data_dir")))
        check("A.5 archive_root present", bool(body.get("archive_root")))
        check("A.6 cap_mb is int", isinstance(body.get("max_mb_per_person"), int))
    else:
        check("A.2 ok=true", False, f"non-dict body: {body!r}")


def test_b_session_start() -> None:
    log(f"\n[B] POST /api/memory-archive/session/start  person_id={PID} conv_id={CID}")
    status, body = _request("POST", "/api/memory-archive/session/start",
                            json_body={
                                "person_id": PID, "conv_id": CID,
                                "session_style": "memory_exercise",
                                "audio_enabled": True,
                            })
    check("B.1 status=200", status == 200, f"got {status} body={body!r}")
    if isinstance(body, dict):
        check("B.2 ok=true", body.get("ok") is True)
        check("B.3 archive_dir present", bool(body.get("archive_dir")))
        check("B.4 meta.started_at present",
              bool(body.get("meta", {}).get("started_at")))
        check("B.5 meta.audio_enabled=true",
              body.get("meta", {}).get("audio_enabled") is True)


def test_c_append_turns() -> None:
    log("\n[C] POST /api/memory-archive/turn (narrator, then Lori)")
    # Narrator turn with an audio_ref (points at the file we'll upload next).
    narrator_tid = "turn_narr_01"
    status, body = _request("POST", "/api/memory-archive/turn",
                            json_body={
                                "person_id": PID, "conv_id": CID,
                                "turn_id": narrator_tid,
                                "role": "narrator",
                                "content": "I was born in Williston in 1962.",
                                "audio_ref": f"audio/{narrator_tid}.webm",
                                "confirmed": True,
                            })
    check("C.1 narrator turn status=200", status == 200, f"got {status}")
    check("C.2 narrator audio_ref preserved",
          isinstance(body, dict) and body.get("audio_ref") == f"audio/{narrator_tid}.webm")

    # Lori turn — server must force audio_ref=null regardless of input.
    status, body = _request("POST", "/api/memory-archive/turn",
                            json_body={
                                "person_id": PID, "conv_id": CID,
                                "turn_id": "turn_lori_01",
                                "role": "lori",
                                "content": "You were born in Williston in 1962. What do you remember?",
                                "audio_ref": "audio/should_be_stripped.webm",
                            })
    check("C.3 lori turn status=200", status == 200, f"got {status}")
    check("C.4 lori audio_ref forced null",
          isinstance(body, dict) and body.get("audio_ref") is None)


def test_d_upload_narrator_audio() -> None:
    log("\n[D] POST /api/memory-archive/audio (narrator)")
    status, body = _request(
        "POST", "/api/memory-archive/audio",
        form={"person_id": PID, "conv_id": CID, "turn_id": "turn_narr_01", "role": "narrator"},
        multipart=[("file", ("turn_narr_01.webm", FAKE_AUDIO, "audio/webm"))],
    )
    check("D.1 status=200", status == 200, f"got {status} body={body!r}")
    if isinstance(body, dict):
        check("D.2 audio_ref matches", body.get("audio_ref") == "audio/turn_narr_01.webm")
        check("D.3 bytes == payload", body.get("bytes") == len(FAKE_AUDIO))


def test_e_reject_lori_audio() -> None:
    log("\n[E] POST /api/memory-archive/audio (role=lori) — MUST 400")
    status, body = _request(
        "POST", "/api/memory-archive/audio",
        form={"person_id": PID, "conv_id": CID, "turn_id": "turn_lori_01", "role": "lori"},
        multipart=[("file", ("bad.webm", FAKE_AUDIO, "audio/webm"))],
    )
    check("E.1 status=400", status == 400, f"got {status} body={body!r}")
    check("E.2 detail mentions never saved",
          isinstance(body, dict) and "never saved" in str(body.get("detail", "")))


def test_f_session_read_and_audio_lost() -> None:
    log("\n[F] GET /api/memory-archive/session/{conv_id}")
    path = f"/api/memory-archive/session/{quote(CID)}?person_id={quote(PID)}"
    status, body = _request("GET", path)
    check("F.1 status=200", status == 200, f"got {status}")
    if isinstance(body, dict):
        turns = body.get("turns") or []
        check("F.2 turns count == 2", len(turns) == 2, f"got {len(turns)}")
        narr = next((t for t in turns if t.get("role") == "narrator"), {})
        lori = next((t for t in turns if t.get("role") == "lori"), {})
        check("F.3 narrator audio_lost=false (file on disk)",
              narr.get("audio_lost") is False)
        check("F.4 lori audio_ref is None", lori.get("audio_ref") is None)

    # Inject a bogus audio_ref turn pointing at a missing file, then re-read.
    status, _ = _request("POST", "/api/memory-archive/turn",
                         json_body={
                             "person_id": PID, "conv_id": CID,
                             "turn_id": "turn_missing_01",
                             "role": "narrator",
                             "content": "(audio upload failed midway)",
                             "audio_ref": "audio/turn_missing_01.webm",
                         })
    check("F.5 inject missing-audio turn status=200", status == 200)
    status, body = _request("GET", path)
    missing = next((t for t in (body.get("turns") or []) if t.get("turn_id") == "turn_missing_01"), {})
    check("F.6 missing-audio row has audio_lost=true",
          missing.get("audio_lost") is True)


def test_g_export() -> None:
    log(f"\n[G] GET /api/memory-archive/people/{PID}/export")
    status, body = _request("GET", f"/api/memory-archive/people/{quote(PID)}/export")
    check("G.1 status=200", status == 200, f"got {status}")
    check("G.2 zip magic PK header", isinstance(body, bytes) and body[:2] == b"PK")
    if isinstance(body, bytes):
        import zipfile
        try:
            zf = zipfile.ZipFile(io.BytesIO(body))
            names = zf.namelist()
            check("G.3 zip contains transcript.jsonl",
                  any("transcript.jsonl" in n for n in names))
            check("G.4 zip contains meta.json",
                  any("meta.json" in n for n in names))
            check("G.5 zip contains audio/turn_narr_01.webm",
                  any("audio/turn_narr_01.webm" in n for n in names))
        except zipfile.BadZipFile:
            check("G.3 zip parse", False, "BadZipFile")


def test_h_delete() -> None:
    log(f"\n[H] DELETE /api/memory-archive/people/{PID}")
    status, body = _request("DELETE", f"/api/memory-archive/people/{quote(PID)}")
    check("H.1 status=200", status == 200, f"got {status}")
    if isinstance(body, dict):
        check("H.2 removed_files > 0", int(body.get("removed_files", 0)) > 0)
    # Subsequent read must 404.
    status, _ = _request("GET", f"/api/memory-archive/session/{quote(CID)}?person_id={quote(PID)}")
    check("H.3 post-delete session read 404", status == 404, f"got {status}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    log(f"=== WO-ARCHIVE-AUDIO-01 smoke test ===")
    log(f"  api: {API}")
    log(f"  pid: {PID}")
    log(f"  cid: {CID}")

    try:
        test_a_health()
        # Abort early if health is bad — the rest won't pass either.
        if not any(r[1] for r in _results if r[0].startswith("A.3")):
            log("\nABORT: HORNELORE_ARCHIVE_ENABLED appears to be off. Set it in the server env and restart the stack.")
            return 1
        test_b_session_start()
        test_c_append_turns()
        test_d_upload_narrator_audio()
        test_e_reject_lori_audio()
        test_f_session_read_and_audio_lost()
        test_g_export()
        test_h_delete()
    except Exception as exc:
        log(f"\n!!! unexpected error: {exc}")
        return 1

    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    log(f"\n=== summary: {passed} pass / {failed} fail ===")
    for name, ok, detail in _results:
        if not ok:
            log(f"  FAIL {name}  {detail}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
