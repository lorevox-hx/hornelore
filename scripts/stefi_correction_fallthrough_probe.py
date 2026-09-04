#!/usr/bin/env python3
"""Stefi's correction fallthrough, proved over the production WebSocket.

    cd /mnt/c/Users/chris/hornelore
    python3 scripts/stefi_correction_fallthrough_probe.py

── WHAT THIS PROVES, AND WHY IT NEEDED ITS OWN PROBE ─────────────────

WO-LORI-ARCHIVE-TO-MEMOIR-02 Phase 3 (`chat_ws.py:4370-4379`). Stefi's
opening line says which Las Vegas she was born in:

    "I was born in Las Vegas, New Mexico — not the Nevada one, the New
     Mexico one — on the twenty-third of May, 1944. My father Eliseo
     was a sheep rancher..."

The BROWSER routes that as a correction — `_looksLikeStrongCorrection`
in `ui/js/app.js` matches `not\\s+the`. The SERVER's parser then finds no
actionable target or value, and before Phase 3 the correction branch
finalised anyway: a deterministic turn, extraction- and
placement-INELIGIBLE by construction. A narrator clarifying her own
birthplace received a correction acknowledgement, and her father, her
birth date and her birthplace reached nothing.

**TEST-23 cannot be this gate.** It is a persistence/resume harness, it
failed before any meaningful interaction (blank `person_id`, zero-word
replies), and its RED is a setup defect rather than a Phase 3 signal.
This probe asserts the six properties that fix actually owes.

── THE SIX ASSERTIONS ────────────────────────────────────────────────

  1. her exact statement is initially routed as `correction`
  2. the server emits `[correction-fallthrough]` for this conversation
  3. no correction mutation and no correction acknowledgement occur
  4. a NONEMPTY ordinary Lori response is committed
  5. the narrator turn and the assistant turn both persist
  6. the completed-turn extraction/tracing hooks run normally

── SAFETY ────────────────────────────────────────────────────────────

  * ONE synthetic narrator, created through the product endpoint with
    `testing_only=true`, named so no human could mistake it for family.
  * Its UUID is journalled to disk BEFORE any other request.
  * It refuses to run a second time rather than creating a duplicate.
  * **No deletion path exists in this file.** Preserve the narrator for
    review; erasure is a separate, authorized, product-path operation.
  * No existing narrator is read, enrolled, paused or modified.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import subprocess
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
DB_PATH = Path(os.environ.get("HORNELORE_DB_PATH", str(REPO_ROOT / ".runtime" / "hornelore.db")))
API_LOG = REPO_ROOT / ".runtime" / "logs" / "api.log"
APP_JS = REPO_ROOT / "ui" / "js" / "app.js"
HARNESS = REPO_ROOT / "scripts" / "run_regional_crypto_jewish_new_mexico_harness.py"

RUN_ID = f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
NARRATOR_NAME = f"ZZ STEFI FALLTHROUGH {RUN_ID}"
CONV_ID = f"stefi-fallthrough-{RUN_ID}"
JOURNAL = REPO_ROOT / ".runtime" / "eval" / "stefi-fallthrough" / f"{RUN_ID}.json"

_results: List[Dict[str, Any]] = []


def check(ok: Optional[bool], name: str, detail: str = "") -> Optional[bool]:
    """`None` means UNVERIFIED — measured nothing, so claims nothing."""
    mark = {True: "PASS", False: "FAIL", None: "UNVERIFIED"}[ok]
    print(f"  {mark:11} {name}" + (f"   [{detail}]" if detail else ""))
    _results.append({"assertion": name, "result": mark, "detail": detail})
    return ok


# ── the fixture, loaded from the shipped harness ──────────────────────
def stefi_text() -> str:
    """Stefi's opening chapter, read from the fixture — never retyped.

    A probe that pastes its own copy of the narrator's words proves
    something about the paste, not about the fixture the cohort runs.
    """
    import importlib.util
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    sys.modules.setdefault("websockets", type(sys)("websockets"))
    spec = importlib.util.spec_from_file_location("_stefi", HARNESS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    chapter = list(mod.build_config().chapters)[0]
    text = getattr(chapter, "text", "") or getattr(chapter, "narrator_text", "")
    if not text.strip():
        raise SystemExit("fixture produced no narrator text")
    return text


# ── assertion 1: the BROWSER's routing decision ───────────────────────
def browser_routes_as_correction(text: str) -> Optional[bool]:
    """Run the SHIPPED regex from `ui/js/app.js`, not a retyped copy.

    The routing happens in the browser, so the honest way to assert it is
    to extract the literal out of the shipped file and evaluate it with
    node. Retyping the pattern here would test this file's transcription.
    If node is unavailable the assertion is UNVERIFIED, never PASS.
    """
    src = APP_JS.read_text(encoding="utf-8")
    m = re.search(
        r"if \((/\\b\(\?:not\|.*?/)\.test\(t\)\) return true;", src)
    if not m:
        m = re.search(r"(/\\b\(\?:not\|wasn't\|[^\n]*?/)\.test\(t\)", src)
    if not m:
        return check(None, "her statement routes as `correction`",
                     "could not locate the contradiction regex in app.js")
    literal = m.group(1)
    try:
        proc = subprocess.run(
            ["node", "-e",
             "const re=" + literal + ";"
             "const t=JSON.parse(process.argv[1]).toLowerCase();"
             "process.stdout.write(re.test(t)?'true':'false');",
             json.dumps(text)],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return check(None, "her statement routes as `correction`",
                     f"node unavailable: {exc}")
    if proc.returncode != 0:
        return check(None, "her statement routes as `correction`",
                     f"node failed: {proc.stderr.strip()[:120]}")
    fired = proc.stdout.strip() == "true"
    return check(fired, "her statement routes as `correction`",
                 f"shipped app.js regex fired={fired}")


def server_parser_finds_nothing(text: str) -> bool:
    """The precondition for the fallthrough, MEASURED.

    Includes a non-vacuity control: a real correction must still parse,
    or an always-empty parser would satisfy this trivially.
    """
    sys.path.insert(0, str(REPO_ROOT / "server" / "code"))
    from api.memory_echo import parse_correction_rule_based
    parsed = parse_correction_rule_based(text)
    control = parse_correction_rule_based("Actually we only had two kids, not three.")
    ok = (not parsed) and bool(control)
    return bool(check(ok, "parser finds no actionable target/value",
                      f"stefi={parsed!r} control={control!r}"))


# ── product helpers ───────────────────────────────────────────────────
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


def sql(query: str, args=()) -> List[sqlite3.Row]:
    """Read-only. `mode=ro` cannot write whatever the query says."""
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return con.execute(query, args).fetchall()
    finally:
        con.close()


def create_narrator() -> str:
    """One marked, testing-only narrator. Journalled before anything else."""
    existing = sql("SELECT id FROM people WHERE display_name=?;", (NARRATOR_NAME,))
    if existing:
        raise SystemExit(f"REFUSING: {NARRATOR_NAME} already exists "
                         f"({existing[0]['id']}). This probe never reuses or "
                         "deletes; start a new run.")
    status, body = http("POST", "/api/people", {
        "display_name": NARRATOR_NAME,
        "role": "",
        "narrator_type": "live",
        # An intake/consent behaviour, not a durable classification: it
        # lets the product skip consent attestations for a fixture no
        # human consented on behalf of. Forging the consent booleans
        # instead would defeat the gate that exists to prevent exactly
        # that.
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
        "conv_id": CONV_ID, "testing_only_requested": True,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "deletion": "none — this probe has no deletion path; erasure is a "
                    "separate authorized product-path operation",
    }, indent=1), encoding="utf-8")
    print(f"  narrator : {pid}  (journalled to {JOURNAL.relative_to(REPO_ROOT)})")
    return pid


async def send_correction_turn(person_id: str, text: str, timeout: float = 240.0):
    """One production turn sent EXACTLY as the browser would send it.

    `turn_mode="correction"` is not this probe's opinion — it is what the
    shipped classifier produces for this text, asserted separately above.
    Every frame is captured, because assertion 3 is about a frame that
    must NOT arrive.
    """
    import websockets
    frames: List[Dict[str, Any]] = []
    final = ""
    async with websockets.connect(WS_URL, max_size=8 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"type": "sync_session", "person_id": person_id}))
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout))
            frames.append(msg)
            if msg.get("type") == "session_verified":
                break
        await ws.send(json.dumps({
            "type": "start_turn",
            "session_id": CONV_ID,
            "message": text,
            "turn_mode": "correction",
            "params": {"person_id": person_id, "surface": "narrator"},
        }))
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout))
            frames.append(msg)
            kind = msg.get("type")
            if kind == "token":
                final += msg.get("delta") or ""
            elif kind == "done":
                return (msg.get("final_text") or final), frames
            elif kind == "error":
                raise RuntimeError(f"server error frame: {msg.get('message')}")
        raise TimeoutError(f"no 'done' frame within {timeout}s")


def log_lines_for_conv() -> List[str]:
    if not API_LOG.is_file():
        return []
    text = API_LOG.read_text(encoding="utf-8", errors="replace")
    return [ln for ln in text.splitlines() if CONV_ID in ln]


def main() -> int:
    print(f"Stefi correction-fallthrough probe — {API}")
    print(f"  run id   : {RUN_ID}")
    print(f"  conv id  : {CONV_ID}")
    print(f"  narrator : {NARRATOR_NAME}\n")

    text = stefi_text()
    print(f"  fixture  : {text[:88]}...\n")

    print("── preconditions ──")
    browser_routes_as_correction(text)
    server_parser_finds_nothing(text)

    if not DB_PATH.exists():
        check(False, "database is readable", str(DB_PATH))
        return 1

    print("\n── live turn ──")
    person_id = create_narrator()
    log_before = len(log_lines_for_conv())
    assistant_text, frames = asyncio.run(send_correction_turn(person_id, text))
    time.sleep(2.0)   # let the completed-turn hooks flush to the log

    kinds = [f.get("type") for f in frames]
    print(f"  frames   : {kinds}\n")

    print("── the six assertions ──")

    # 2 — the fallthrough actually fired, for THIS conversation.
    lines = log_lines_for_conv()
    fell_through = any("[correction-fallthrough]" in ln for ln in lines)
    check(fell_through, "server emitted [correction-fallthrough]",
          f"{len(lines) - log_before} new log lines for this conv")

    # 3 — no mutation, no acknowledgement.
    got_payload = "correction_payload" in kinds
    applied = any("[chat_ws][correction-apply]" in ln for ln in lines)
    check(not got_payload and not applied,
          "no correction mutation and no correction acknowledgement",
          f"correction_payload_frame={got_payload} correction_apply_logged={applied}")

    # 4 — an ordinary, nonempty reply.
    check(bool(assistant_text.strip()),
          "a nonempty ordinary Lori response is committed",
          f"{len(assistant_text)} chars")

    # 5 — both turns persisted.
    #
    # The column is `conv_id`, not `conversation_id` (`db.py:589`).
    # Written from the schema rather than from memory: the wrong name
    # raises OperationalError, and an assertion that crashes reads as a
    # product failure when it is a typo in the probe.
    rows = sql(
        "SELECT role, content, meta_json FROM turns WHERE conv_id=? "
        "ORDER BY id;", (CONV_ID,))
    roles = [r["role"] for r in rows]
    check("user" in roles and "assistant" in roles,
          "narrator and assistant turns persist",
          f"roles={roles} rows={len(rows)}")

    # 6 — the completed-turn hooks ran on the ORDINARY path.
    #
    # Read from the PERSISTED turn meta, not inferred from log text. The
    # mode reset is what makes the turn extraction- and
    # placement-eligible; a turn still stamped `correction` is
    # deterministic and ineligible by construction, which is precisely
    # the defect Phase 3 repaired.
    modes = []
    for row in rows:
        try:
            modes.append((json.loads(row["meta_json"] or "{}") or {}).get("turn_mode"))
        except ValueError:
            modes.append("<unparseable meta_json>")
    persisted_correction = [m for m in modes if m == "correction"]
    check(rows and not persisted_correction,
          "the committed turn is stamped interview, not correction",
          f"persisted turn_mode values={modes}")

    hooks = [ln for ln in lines
             if "[extract]" in ln or "turnscope" in ln or "story" in ln.lower()]
    check(True if hooks else None,
          "extraction/tracing hooks ran",
          f"{len(hooks)} hook lines" if hooks
          else "no hook lines for this conv — inspect .runtime/logs/api.log")

    failed = [r for r in _results if r["result"] == "FAIL"]
    unver = [r for r in _results if r["result"] == "UNVERIFIED"]
    print(f"\n  {len(_results) - len(failed) - len(unver)} passed, "
          f"{len(failed)} failed, {len(unver)} unverified")
    print(f"  narrator {person_id} PRESERVED — this probe deletes nothing.")

    report = JOURNAL.with_suffix(".report.json")
    report.write_text(json.dumps({
        "run_id": RUN_ID, "conv_id": CONV_ID, "person_id": person_id,
        "assistant_chars": len(assistant_text),
        "frames": kinds, "assertions": _results,
        "assistant_text": assistant_text,
    }, indent=1), encoding="utf-8")
    print(f"  report   : {report.relative_to(REPO_ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":      # pragma: no cover
    sys.exit(main())
