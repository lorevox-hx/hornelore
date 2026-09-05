#!/usr/bin/env python3
"""Phase 4 live probe — the capture decision reaches the committed turn.

    cd /mnt/c/Users/chris/hornelore
    .venv-gpu/bin/python scripts/story_capture_decision_probe.py

WO-LORI-STORY-CAPTURE-DECISION-DURABILITY-01.

── WHAT THIS PROVES ──────────────────────────────────────────────────

Two turns over the production WebSocket, against one synthetic narrator:

  * a NOMINATED turn — rich enough that the shipped trigger fires. Its
    decision must name the candidate that preservation actually created,
    and that candidate must be bound to this same source row.
  * a DECLINED turn — short enough that nothing fires. **This is the
    case the phase exists for**: it creates no `story_candidates` row,
    so before Phase 4 the only record of why lived in a rotating,
    gitignored log.

Neither record may contain a word the narrator or Lori said.

── WHY IT IS A SEPARATE PROBE ────────────────────────────────────────

The offline suite proves the writer commits what it is handed. It cannot
prove that the RUNNING SERVER hands it anything — the emit sites, the
`params` hand-off across the preserve/commit boundary, and the two
completion paths are only exercised by a real turn.

── SAFETY ────────────────────────────────────────────────────────────

  * ONE synthetic narrator via the product endpoint with
    `testing_only=true`, named so no human could mistake it for family.
  * Its UUID is journalled BEFORE any turn is sent.
  * A retry reuses a journalled narrator with zero turns rather than
    creating a sibling.
  * **No deletion path exists in this file.**
  * No existing narrator is read, enrolled, paused or modified.
  * Read-only database access (`mode=ro`), resolved exactly as the
    server resolves it.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
API = os.environ.get("HORNELORE_API", "http://localhost:8000")
WS_URL = API.replace("http://", "ws://").replace("https://", "wss://") + "/api/chat/ws"

RUN_ID = f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
NARRATOR_NAME = f"ZZ CAPTURE DECISION {RUN_ID}"
CONV_NOMINATED = f"capdec-nom-{RUN_ID}"
CONV_DECLINED = f"capdec-dec-{RUN_ID}"
JOURNAL = REPO_ROOT / ".runtime" / "eval" / "capture-decision" / f"{RUN_ID}.json"

#: Rich enough for the shipped trigger. Synthetic, not any real person.
NOMINATING_TEXT = (
    "I was born in Las Vegas, New Mexico, and my father Eliseo was a sheep "
    "rancher in San Miguel County when I was a girl. My mother Adela kept the "
    "house on Hot Springs Road, and years later we walked to Mass at Our Lady "
    "of Sorrows together."
)
#: Short enough that nothing fires. The case with no candidate.
DECLINING_TEXT = "Yes."

_results: List[Dict[str, Any]] = []


def check(ok: Optional[bool], name: str, detail: str = "") -> Optional[bool]:
    mark = {True: "PASS", False: "FAIL", None: "UNVERIFIED"}[ok]
    print(f"  {mark:11} {name}" + (f"   [{detail}]" if detail else ""))
    _results.append({"assertion": name, "result": mark, "detail": detail})
    return ok


def _resolve_db_path() -> Path:
    """Resolve the database EXACTLY as the server does.

    `db.py:58-63` builds `DATA_DIR / "db" / DB_NAME`, both from the
    environment, both supplied by `.env`. `db.py` is deliberately NOT
    imported: it runs `DB_DIR.mkdir()` at module scope, and a read-only
    probe must not create directories. A guessed path is worse than a
    wrong one — SQLite CREATES a database on open, so the guess yields an
    empty file and a "no such table" error that reads like data loss.
    """
    override = os.environ.get("HORNELORE_DB")
    if override:
        return Path(override).expanduser()
    env: Dict[str, str] = {}
    dotenv = REPO_ROOT / ".env"
    if dotenv.is_file():
        for line in dotenv.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$", line)
            if m and m.group(1) in ("DATA_DIR", "DB_NAME"):
                env[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    data_dir = Path(env.get("DATA_DIR") or os.getenv("DATA_DIR", "data")).expanduser()
    db_name = (env.get("DB_NAME") or os.getenv("DB_NAME", "lorevox.sqlite3")).strip() \
        or "lorevox.sqlite3"
    return data_dir / "db" / db_name


DB_PATH = _resolve_db_path()


def sql(query: str, args=()) -> List[sqlite3.Row]:
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return con.execute(query, args).fetchall()
    finally:
        con.close()


def http(method: str, path: str, payload: Optional[Dict[str, Any]] = None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode()
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"detail": raw[:300]}


def require_dependencies() -> None:
    """Fail BEFORE creating a narrator, not after.

    A previous probe in this repository created a narrator and then died
    because the transport turned out to be a stub. Anything that can make
    the run impossible is checked while checking is still free.
    """
    try:
        import websockets
    except ImportError:
        raise SystemExit(
            "`websockets` is not importable by this interpreter. It lives in "
            "the venvs, not in system python3 — run with .venv-gpu/bin/python.")
    if not hasattr(websockets, "connect"):
        raise SystemExit(
            "the `websockets` module in scope has no `connect` — a stub is "
            "shadowing the real package; refusing to create a narrator.")


def reusable_narrator() -> Optional[Dict[str, str]]:
    """A narrator a previous attempt created but never spoke to."""
    d = JOURNAL.parent
    if not d.is_dir():
        return None
    for path in sorted(d.glob("*.json"), reverse=True):
        if path.name.endswith(".report.json"):
            continue
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        pid = row.get("person_id")
        if not pid:
            continue
        if not sql("SELECT id FROM people WHERE id=?;", (pid,)):
            continue
        used = sql("SELECT count(*) AS n FROM turns WHERE conv_id IN (?,?);",
                   (row.get("conv_nominated") or "", row.get("conv_declined") or ""))
        if used and used[0]["n"] == 0:
            return {"person_id": pid, "journal": path.name}
    return None


def create_narrator() -> str:
    prior = reusable_narrator()
    if prior:
        print(f"  reusing  : {prior['person_id']} — from {prior['journal']}, "
              "zero turns, never used")
        return prior["person_id"]
    status, body = http("POST", "/api/people", {
        "display_name": NARRATOR_NAME,
        "role": "",
        "narrator_type": "live",
        # An intake/consent behaviour, not a durable classification: it
        # lets intake skip consent attestations for a fixture no human
        # consented on behalf of. Forging the consent booleans instead
        # would defeat the gate that exists to prevent exactly that.
        "testing_only": True,
    })
    if status != 200:
        raise SystemExit(f"narrator creation failed: HTTP {status} {body}")
    pid = body.get("person_id") or (body.get("person") or {}).get("id") or body.get("id")
    if not pid:
        raise SystemExit(f"no person_id in create response: {body}")
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    JOURNAL.write_text(json.dumps({
        "run_id": RUN_ID, "person_id": pid, "display_name": NARRATOR_NAME,
        "conv_nominated": CONV_NOMINATED, "conv_declined": CONV_DECLINED,
        "testing_only_requested": True,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "deletion": "none — this probe has no deletion path",
    }, indent=1), encoding="utf-8")
    print(f"  narrator : {pid}  (journalled to {JOURNAL.relative_to(REPO_ROOT)})")
    return pid


async def send_turn(person_id: str, conv_id: str, text: str,
                    timeout: float = 240.0) -> str:
    import websockets
    final = ""
    async with websockets.connect(WS_URL, max_size=8 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"type": "sync_session", "person_id": person_id}))
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout))
            if msg.get("type") == "session_verified":
                break
        await ws.send(json.dumps({
            "type": "start_turn", "session_id": conv_id, "message": text,
            "turn_mode": "interview",
            "params": {"person_id": person_id, "surface": "narrator"},
        }))
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout))
            kind = msg.get("type")
            if kind == "token":
                final += msg.get("delta") or ""
            elif kind == "done":
                return msg.get("final_text") or final
            elif kind == "error":
                raise RuntimeError(f"server error frame: {msg.get('message')}")
        raise TimeoutError(f"no 'done' frame within {timeout}s")


def decision_for(conv_id: str) -> Optional[Dict[str, Any]]:
    """The decision on the USER row of this conversation."""
    for row in sql("SELECT role, meta_json FROM turns WHERE conv_id=? ORDER BY id;",
                   (conv_id,)):
        if row["role"] != "user":
            continue
        try:
            return (json.loads(row["meta_json"] or "{}") or {}).get(
                "story_capture_decision")
        except ValueError:
            return None
    return None


def assistant_meta_for(conv_id: str) -> Dict[str, Any]:
    for row in sql("SELECT role, meta_json FROM turns WHERE conv_id=? ORDER BY id;",
                   (conv_id,)):
        if row["role"] == "assistant":
            try:
                return json.loads(row["meta_json"] or "{}") or {}
            except ValueError:
                return {}
    return {}


def main() -> int:
    print(f"Story-capture decision probe — {API}")
    print(f"  run id   : {RUN_ID}")
    print(f"  database : {DB_PATH}\n")

    print("── preconditions ──")
    require_dependencies()
    if not DB_PATH.exists():
        check(False, "database exists at the server-resolved path", str(DB_PATH))
        return 1
    if not sql("SELECT name FROM sqlite_master WHERE type='table' AND name='people';"):
        check(False, "database carries the Hornelore schema",
              f"{DB_PATH} is not the Hornelore database")
        return 1
    check(True, "database resolved and carries the Hornelore schema", str(DB_PATH))

    print("\n── live turns ──")
    person_id = create_narrator()
    say_nom = asyncio.run(send_turn(person_id, CONV_NOMINATED, NOMINATING_TEXT))
    say_dec = asyncio.run(send_turn(person_id, CONV_DECLINED, DECLINING_TEXT))
    time.sleep(2.0)
    print(f"  replies  : nominated={len(say_nom)}c declined={len(say_dec)}c\n")

    print("── assertions ──")

    nom = decision_for(CONV_NOMINATED)
    dec = decision_for(CONV_DECLINED)

    check(bool(nom) and bool(dec),
          "every evaluated turn carries exactly one decision on its user row",
          f"nominated={bool(nom)} declined={bool(dec)}")
    if not (nom and dec):
        print("\n  cannot continue without both records.")
        return 1

    for label, rec in (("nominated", nom), ("declined", dec)):
        check(rec.get("schema_version") == "story_capture_decision/v1",
              f"{label}: schema is story_capture_decision/v1",
              str(rec.get("schema_version")))

    check(nom.get("outcome") == "nominated" and bool(nom.get("candidate_id")),
          "the nominated record names a candidate",
          f"outcome={nom.get('outcome')} candidate={nom.get('candidate_id')}")

    cand = sql("SELECT id, conversation_id FROM story_candidates WHERE id=?;",
               (nom.get("candidate_id") or "",))
    check(bool(cand) and cand[0]["conversation_id"] == CONV_NOMINATED,
          "that candidate exists and is bound to this same source conversation",
          f"rows={len(cand)} conv={cand[0]['conversation_id'] if cand else None}")

    check(dec.get("outcome") == "declined" and dec.get("candidate_id") is None,
          "the declined record has complete diagnostics and NO candidate",
          f"outcome={dec.get('outcome')} candidate={dec.get('candidate_id')} "
          f"reason={dec.get('reason')}")

    check(not sql("SELECT id FROM story_candidates WHERE conversation_id=?;",
                  (CONV_DECLINED,)),
          "the declined turn created no story row at all")

    for field in ("word_count", "anchor_count", "place_anchor", "time_anchor",
                  "person_anchor", "thresholds"):
        if field not in (dec.get("diagnostic") or {}):
            check(False, "the declined record carries the full diagnostic",
                  f"missing {field}")
            break
    else:
        check(True, "the declined record carries the full diagnostic",
              f"{len(dec.get('diagnostic') or {})} fields")

    leaked = []
    for label, rec in (("nominated", nom), ("declined", dec)):
        blob = json.dumps(rec)
        for fragment in ("Las Vegas", "Eliseo", "Adela", "Hot Springs",
                         "Sorrows", DECLINING_TEXT):
            if fragment and fragment in blob:
                leaked.append(f"{label}:{fragment}")
    check(not leaked, "neither record contains narrator or assistant prose",
          ", ".join(leaked) if leaked else "clean")

    check("story_capture_decision" not in assistant_meta_for(CONV_NOMINATED)
          and "story_capture_decision" not in assistant_meta_for(CONV_DECLINED),
          "no decision was written to an assistant row")

    failed = [r for r in _results if r["result"] == "FAIL"]
    unver = [r for r in _results if r["result"] == "UNVERIFIED"]
    print(f"\n  {len(_results) - len(failed) - len(unver)} passed, "
          f"{len(failed)} failed, {len(unver)} unverified")
    print(f"  narrator {person_id} PRESERVED — this probe deletes nothing.")

    report = JOURNAL.with_suffix(".report.json")
    report.write_text(json.dumps({
        "run_id": RUN_ID, "person_id": person_id,
        "conv_nominated": CONV_NOMINATED, "conv_declined": CONV_DECLINED,
        "nominated_decision": nom, "declined_decision": dec,
        "assertions": _results,
    }, indent=1), encoding="utf-8")
    print(f"  report   : {report.relative_to(REPO_ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":      # pragma: no cover
    sys.exit(main())
