#!/usr/bin/env python3
"""WO-LIVE-TRIP-COMPANION-01 Vertical Slice 1 — the live acceptance driver.

WHY THIS SCRIPT EXISTS. Vertical Slice 1 joined two subsystems that
both already worked and had never met: Lori's persisted interview turns
and the travel-document system's trips and trip days. The automated
suite (tests/test_trip_placement.py, 34 tests) proves the join in
isolation against a temporary database. The work order asks for more
than that:

    "Stop only after the complete browser workflow passes against the
    real stack."

So this script drives the RUNNING stack along the work order's required
path, over the same HTTP routes and the same WebSocket message the
browser sends, and then reads the real database independently to check
that what the API claims is what was actually written.

═══════════════════════════════════════════════════════════════════════
  USAGE — two phases, because the restart is the point
═══════════════════════════════════════════════════════════════════════

    python scripts/vs1_trip_companion_acceptance.py --list

        Prints the trips this narrator has, with their ids, dates,
        generated day counts and current live state. Nothing is
        written. Use it to choose the --trip-id for phase 1.

    python scripts/vs1_trip_companion_acceptance.py --phase 1 \
        --trip-id <id>

        Marks the trip active, selects its first generated day, sends
        ONE real interview turn to Lori over /api/chat/ws using the
        exact payload shape ui/js/travel-doc-lab.js sends, then checks
        that the turn persisted, that a link row now points at the trip
        and the day, and that the day's timeline projects it.

        Writes DATA_DIR/_xfer/vs1_acceptance_state.json.

    # bash scripts/stop_all.sh && bash scripts/start_all.sh

    python scripts/vs1_trip_companion_acceptance.py --phase 2

        Reads the state file, then checks that the active trip, the
        selected day and the timeline event all survived the restart —
        by asking the API, and again by reading sqlite directly.

    python scripts/vs1_trip_companion_acceptance.py --restore

        Optional. Puts the trip's live_state back to whatever it was
        before phase 1 touched it. The acceptance run should not decide
        for the operator whether he is on his trip.

WHY THE TURN IS SENT OVER THE WEBSOCKET AND NOT FAKED. The link is
created inside chat_ws's completed-turn path, after persistence and
after extraction, in the same try-block. A driver that inserted rows
into `turns` itself would prove the repository works and prove nothing
about the wiring — which is the part that was missing.

WHY IT MIRRORS travel-doc-lab.js EXACTLY. That pane sends no top-level
`turn_mode`. chat_ws defaults the mode to "interview" at the start_turn
entry point, which is what makes a Travel Doc turn placement-eligible
at all. If that default ever changes, this script must fail rather than
paper over it, so the payload here is a copy of the pane's, not a
convenient superset.

WHAT IT REFUSES TO DO
  * It never infers which trip to use. `--trip-id` is required, and
    `--person-id` is read off the trip's own record rather than guessed.
  * It never creates or deletes a trip, a day, a narrator or a photo.
    The only rows it causes are one conversation's turns, that turn's
    archive and extraction rows, and one trip_turn_links row.
  * It never prints a credential, a provider identifier or a staging
    path, and it prints the narrative text only because the operator
    typed it here himself and has to be able to recognise it in the UI.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent

# ── Environment resolution — same two keys, same reasons, as the Gate 7
#    driver. .env carries a hundred and forty others, several of them
#    credentials, and none of them are this script's business. ───────────
_ENV_KEYS_READ = ("DATA_DIR", "DB_NAME")


def load_env_defaults() -> Dict[str, str]:
    resolved: Dict[str, str] = {}
    env_path = _REPO_ROOT / ".env"
    from_file: Dict[str, str] = {}
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if k in _ENV_KEYS_READ:
                from_file[k] = v.strip().strip('"').strip("'")
    for key in _ENV_KEYS_READ:
        if os.environ.get(key):
            resolved[key] = f"{os.environ[key]} (from shell)"
        elif key in from_file:
            os.environ[key] = from_file[key]
            resolved[key] = f"{from_file[key]} (from .env)"
        else:
            resolved[key] = "(unset - api/db.py default applies)"
    return resolved


_ENV_PROVENANCE = load_env_defaults()

_DATA_DIR = Path(os.environ.get("DATA_DIR", "data")).expanduser()
_DB_NAME = (os.environ.get("DB_NAME") or "lorevox.sqlite3").strip()
_DB_PATH = _DATA_DIR / "db" / _DB_NAME
_XFER_DIR = _DATA_DIR / "_xfer"
_STATE_PATH = _XFER_DIR / "vs1_acceptance_state.json"
_EVIDENCE_PATH = _XFER_DIR / "vs1_acceptance_evidence.json"

# Both third-party clients are imported lazily, and deliberately so.
# `--list` is a read-only sqlite query against the operator database; it
# does not touch the running stack at all, and it is the first thing an
# operator types when they want to know which trip id to pass. Demanding
# the server virtualenv before answering that question would turn a
# question into an obstacle. Only the phases that actually speak HTTP or
# WebSocket to the live API are allowed to insist on these packages, and
# when they do, they say which interpreter has them.
requests = None    # type: ignore[assignment]
websockets = None  # type: ignore[assignment]

_VENV_HINT = ("Run it with the server virtualenv active, or invoke "
              ".venv/bin/python3 directly.")


def _need_requests():
    """Import `requests` at the moment an HTTP call is really made."""
    global requests
    if requests is None:
        try:
            import requests as _requests  # type: ignore[import-untyped]
        except ImportError:  # pragma: no cover
            print("FATAL: the `requests` package is required for this "
                  "phase. " + _VENV_HINT, file=sys.stderr)
            raise
        requests = _requests
    return requests


def _need_websockets():
    """Import `websockets` at the moment the live turn is really sent."""
    global websockets
    if websockets is None:
        try:
            import websockets as _websockets  # type: ignore[import-untyped]
        except ImportError:  # pragma: no cover
            print("FATAL: the `websockets` package is required to send a "
                  "real turn. " + _VENV_HINT, file=sys.stderr)
            raise
        websockets = _websockets
    return websockets


DEFAULT_MESSAGE = (
    "We spent the morning walking, and I want to remember how the light "
    "looked on the water before we went in for coffee."
)


def _api_base() -> str:
    return (os.environ.get("HORNELORE_API_URL")
            or os.environ.get("HORNELORE_API_BASE")
            or "http://localhost:8000").rstrip("/")


def _ws_url() -> str:
    return _api_base().replace("http", "ws", 1) + "/api/chat/ws"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn


# ── result recording ──────────────────────────────────────────────────────

RESULTS: List[Dict[str, Any]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append({"name": name, "ok": bool(ok), "detail": detail})
    print(("  PASS  " if ok else "  FAIL  ") + name +
          (("   " + detail) if detail else ""))
    return bool(ok)


def _get(path: str, **params: Any) -> Dict[str, Any]:
    r = _need_requests().get(
        _api_base() + path, params=params or None, timeout=30)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "_status": r.status_code, "_text": r.text[:300]}


def _post(path: str, body: Dict[str, Any]) -> Any:
    r = _need_requests().post(_api_base() + path, json=body, timeout=30)
    try:
        payload = r.json()
    except Exception:
        payload = {"_text": r.text[:300]}
    if isinstance(payload, dict):
        payload["_status"] = r.status_code
    return payload


# ── --list ────────────────────────────────────────────────────────────────

def do_list(person_id: Optional[str]) -> int:
    conn = _connect()
    where, args = "", ()
    if person_id:
        where, args = " WHERE person_id = ?", (person_id,)
    # --list is the first command an operator runs, and on a database that
    # has not yet met migration 0039 the lifecycle columns simply are not
    # there. That is a normal state, not a fault: the migration applies
    # itself when the API next starts. So ask the schema rather than
    # assuming it, and say plainly what is missing instead of failing with
    # a traceback on the operator's very first keystroke.
    migrated = _has_col(conn, "trips", "live_state")
    live_cols = ("COALESCE(live_state,'?') AS live_state, "
                 "COALESCE(active_trip_day_id,'') AS sel "
                 if migrated else
                 "'(not migrated)' AS live_state, '' AS sel ")
    rows = conn.execute(
        "SELECT id, person_id, title, start_date, end_date, status, "
        + live_cols +
        "FROM trips" + where + " ORDER BY start_date DESC;", args).fetchall()
    print(f"\nDATABASE: {_DB_PATH}\n")
    if not migrated:
        print("  NOTE: migration 0039 has not been applied to this database")
        print("        yet, so no trip has a live state. Start the API once")
        print("        (bash scripts/start_all.sh) and it applies itself.\n")
    if not rows:
        print("  (no trips)")
        return 1
    for r in rows:
        n = conn.execute("SELECT COUNT(*) FROM trip_days WHERE trip_id = ?;",
                         (r["id"],)).fetchone()[0]
        links = conn.execute(
            "SELECT COUNT(*) FROM trip_turn_links WHERE trip_id = ?;",
            (r["id"],)).fetchone()[0] if _has_links(conn) else "-"
        print(f"  {r['id']}")
        print(f"      {r['title']}")
        print(f"      {r['start_date']} .. {r['end_date']}   "
              f"days={n}  live_state={r['live_state']}  "
              f"selected_day={'yes' if r['sel'] else 'no'}  links={links}")
        print(f"      person_id={r['person_id']}")
    conn.close()
    print("\nPick one and run:  --phase 1 --trip-id <id>\n")
    return 0


def _has_links(conn: sqlite3.Connection) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='trip_turn_links';").fetchone())


def _has_col(conn: sqlite3.Connection, table: str, col: str) -> bool:
    """True when `table.col` exists. Identifiers are literals here."""
    try:
        cols = conn.execute("PRAGMA table_info(%s);" % table).fetchall()
    except sqlite3.Error:
        return False
    return any((r[1] if not isinstance(r, sqlite3.Row) else r["name"]) == col
               for r in cols)


# ── the one live turn ─────────────────────────────────────────────────────

async def _send_one_turn(conv_id: str, person_id: str, message: str,
                         modal_scope: Optional[Dict[str, Any]] = None,
                         timeout_s: int = 240) -> Dict[str, Any]:
    """One interview turn, sent the way ui/js/travel-doc-lab.js sends it.

    `modal_scope` IS AN OBJECT, NOT A WORD. This script sent the string
    "trip" for three runs while its own docstring claimed to copy the
    pane's payload. The server read `.get("active_trip_id")` off it and
    raised `'str' object has no attribute 'get'`; trip story capture
    swallowed that as `reason=error` and the modal direct-answer branch
    logged a warning and continued. The link still formed --- placement
    reads the day off `trips.active_trip_day_id` on the server and never
    trusted this object --- so the run went green over two production
    behaviours that had not actually run. A harness that lies about its
    payload does not test the path it names; it tests a path the product
    does not have. The shape below is `LoriPane.scope()` in
    ui/js/travel-doc-lab.js, field for field.
    """
    payload = {
        "type": "start_turn",
        "session_id": conv_id,
        "message": message,
        "params": {
            "person_id": person_id,
            "surface": "travel_doc_modal",
            "modal_scope": modal_scope,
            "turn_id": "vs1_acceptance_t1",
        },
    }
    tokens: List[str] = []
    _ws = _need_websockets()
    async with _ws.connect(_ws_url(), max_size=1 << 22) as ws:
        await ws.send(json.dumps(payload, ensure_ascii=False))
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
            except asyncio.TimeoutError:
                continue
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            typ = msg.get("type")
            if typ == "token":
                delta = msg.get("delta") or msg.get("text") or ""
                tokens.append(delta)
                print(delta, end="", flush=True)
            elif typ == "done":
                print("")
                return {"ok": True,
                        "final_text": msg.get("final_text")
                        or "".join(tokens)}
            elif typ == "error":
                print("")
                return {"ok": False, "error": json.dumps(msg)[:300]}
    return {"ok": False, "error": f"no done event within {timeout_s}s"}


# ── phase 1 ───────────────────────────────────────────────────────────────

def do_phase1(trip_id: str, day_id: Optional[str], message: str) -> int:
    print("\n=== VS1 LIVE ACCEPTANCE - PHASE 1 (before restart) ===\n")
    print(f"API      : {_api_base()}")
    print(f"DATABASE : {_DB_PATH}")
    print("")

    conn = _connect()
    trip = conn.execute("SELECT * FROM trips WHERE id = ?;",
                        (trip_id,)).fetchone()
    if not trip:
        print(f"FATAL: no trip with id {trip_id}. Run --list.")
        return 2
    person_id = trip["person_id"]
    prior_live_state = (trip["live_state"]
                        if "live_state" in trip.keys() else "planning")
    print(f"trip     : {trip['title']}")
    print(f"days     : {trip['start_date']} .. {trip['end_date']}")
    print(f"was      : live_state={prior_live_state}")
    print("")

    # ── STEP 1: mark it active ────────────────────────────────────────
    print("STEP 1 - mark the trip active")
    res = _post(f"/api/trips/{trip_id}/live-state", {"state": "active"})
    check("POST /live-state accepted",
          res.get("_status") == 200 and res.get("ok") is True,
          f"status={res.get('_status')} {str(res.get('message') or '')[:120]}")
    act = _get("/api/trips/active", person_id=person_id)
    check("GET /active reports this trip",
          ((act.get("trip") or {}).get("id")) == trip_id,
          f"got {(act.get('trip') or {}).get('id')}")

    # ── STEP 2: choose a generated day ────────────────────────────────
    print("\nSTEP 2 - select one generated trip day")
    cal = _get(f"/api/trips/{trip_id}/calendar")
    days = cal.get("days") or []
    check("GET /calendar lists generated days", bool(days),
          f"n={len(days)}")
    if not days:
        return _finish(1, trip_id, person_id, prior_live_state)
    chosen = day_id or days[0]["id"]
    if chosen not in [d["id"] for d in days]:
        print(f"FATAL: day {chosen} is not on this trip.")
        return 2
    res = _post(f"/api/trips/{trip_id}/selected-day", {"trip_day_id": chosen})
    check("POST /selected-day accepted", res.get("ok") is True)
    cal = _get(f"/api/trips/{trip_id}/calendar")
    check("GET /calendar reports the selected day",
          cal.get("selected_day_id") == chosen)
    chosen_row = [d for d in (cal.get("days") or []) if d["id"] == chosen][0]
    before_count = int(chosen_row.get("conversation_count") or 0)
    print(f"  day    : Day {chosen_row.get('day_index')} "
          f"{chosen_row.get('date')}  (conversations before: {before_count})")

    # ── STEP 3: one real interview turn ───────────────────────────────
    print("\nSTEP 3 - open Lori from the trip workspace and complete a turn")
    conv_id = "tdlab_" + trip_id
    links_before = _link_count(conn, trip_id)
    print(f"  you    : {message}")
    print("  lori   : ", end="", flush=True)
    # The pane opened on a DAY, so it sends a day-scoped modal scope.
    # Region and stop come off the chosen day's own row, exactly as
    # LoriPane.scope() reads them from `dayById(this.dayId)`.
    modal_scope = {
        "source_surface": "travel_doc_modal",
        "person_id": person_id,
        "active_trip_id": trip_id,
        # `chosen`, NOT `day_id` --- `day_id` is the optional command
        # line argument and is None whenever the caller let the script
        # pick the first day. Sending it would put a null day on the
        # scope while the server had a real one selected, and the modal
        # would be scoped to the trip on a run that reads day-scoped.
        "active_trip_day_id": chosen,
        "active_trip_region_id": chosen_row.get("trip_region_id") or None,
        "active_trip_stop_id": chosen_row.get("trip_stop_id") or None,
        "active_photo_link_id": None,
        "selected_kind": "day",
    }
    turn = asyncio.run(_send_one_turn(conv_id, person_id, message,
                                      modal_scope=modal_scope))
    check("the turn completed", turn.get("ok") is True,
          str(turn.get("error") or "")[:160])
    final_text = str(turn.get("final_text") or "")
    check("Lori answered with text", bool(final_text.strip()),
          f"{len(final_text)} chars")

    # The link is written after the response is streamed. Give the
    # server's own task a moment rather than racing it -- a false FAIL
    # here would send someone hunting a bug that is a stopwatch.
    time.sleep(2.0)

    # ── STEP 4: the turn persisted normally ───────────────────────────
    print("\nSTEP 4 - the turn persisted normally")
    conn.close()
    conn = _connect()
    rows = conn.execute(
        "SELECT id, role, content FROM turns WHERE conv_id = ? "
        "ORDER BY id DESC LIMIT 2;", (conv_id,)).fetchall()
    check("two turn rows exist for this conversation", len(rows) == 2,
          f"n={len(rows)}")
    asst = next((r for r in rows if r["role"] == "assistant"), None)
    user = next((r for r in rows if r["role"] == "user"), None)
    check("the narrator's words were stored",
          bool(user) and message[:40] in (user["content"] or ""))
    check("Lori's words were stored", bool(asst) and bool(asst["content"]))

    # ── STEP 5: the link ──────────────────────────────────────────────
    print("\nSTEP 5 - the persisted turn is linked to the trip and the day")
    check("trip_turn_links table exists", _has_links(conn))
    link = conn.execute(
        "SELECT * FROM trip_turn_links WHERE assistant_turn_row_id = ?;",
        (asst["id"] if asst else -1,)).fetchone()
    check("a link row exists for this turn", link is not None)
    if link is None:
        return _finish(1, trip_id, person_id, prior_live_state)
    check("the link points at this trip", link["trip_id"] == trip_id)
    check("the link points at the selected day",
          link["trip_day_id"] == chosen,
          f"got {link['trip_day_id']}")
    check("placement_source is active_trip_day",
          link["placement_source"] == "active_trip_day",
          link["placement_source"])
    check("placement_status is confirmed",
          link["placement_status"] == "confirmed",
          link["placement_status"])
    check("exactly one new link row",
          _link_count(conn, trip_id) == links_before + 1,
          f"{links_before} -> {_link_count(conn, trip_id)}")
    keys = link.keys()
    narrative_leak = [k for k in keys
                      if isinstance(link[k], str)
                      and (message[:40] in link[k]
                           or (final_text[:40] and final_text[:40] in link[k]))]
    check("the link table holds no narrative text", not narrative_leak,
          ",".join(narrative_leak))

    # ── STEP 6: the timeline projects it ──────────────────────────────
    print("\nSTEP 6 - the conversation shows on the day's timeline")
    tl = _get(f"/api/trips/{trip_id}/days/{chosen}/timeline")
    items = tl.get("items") or []
    # The timeline carries the whole day now --- photographs, story
    # notes and sources sit on it beside the conversations --- so match
    # on kind as well as id rather than on a bare link_id that other
    # kinds also carry.
    mine = [i for i in items
            if i.get("link_id") == link["id"]
            and (i.get("kind") or "conversation") == "conversation"]
    check("GET /timeline returns the event", bool(mine), f"n={len(items)}")
    if mine:
        it = mine[0]
        check("the timeline shows what the narrator said",
              message[:40] in (it.get("narrator_said") or ""))
        check("the timeline shows what Lori said",
              bool((it.get("lori_said") or "").strip()))
        check("the timeline carries conv_id for source navigation",
              it.get("conv_id") == conv_id)
        check("the timeline says Confirmed day, not Suggested day",
              it.get("placement_status") == "confirmed")
    cal = _get(f"/api/trips/{trip_id}/calendar")
    after_row = [d for d in (cal.get("days") or []) if d["id"] == chosen]
    check("the calendar day's conversation count went up by one",
          bool(after_row)
          and int(after_row[0].get("conversation_count") or 0)
          == before_count + 1,
          f"{before_count} -> "
          f"{after_row[0].get('conversation_count') if after_row else '?'}")

    # The state file is the handshake with phase 2, and it is only
    # written when phase 1 actually passed. A state file produced by a
    # partly-failed phase 1 would let phase 2 run and report a green
    # restart over a link that was never right in the first place ---
    # the restart test would then be measuring the wrong thing and
    # saying so confidently.
    _failed = [r["name"] for r in RESULTS if not r["ok"]]
    if _failed:
        print("\nstate NOT written: phase 1 has failures, so there is "
              "nothing for phase 2 to re-check.")
        for _n in _failed:
            print("   failed: " + _n)
        conn.close()
        return _finish(1, trip_id, person_id, prior_live_state)

    _XFER_DIR.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps({
        "trip_id": trip_id,
        "person_id": person_id,
        "trip_day_id": chosen,
        "conv_id": conv_id,
        "link_id": link["id"],
        "assistant_turn_row_id": link["assistant_turn_row_id"],
        "user_turn_row_id": link["user_turn_row_id"],
        "message_head": message[:40],
        "prior_live_state": prior_live_state,
        "link_count_after_phase1": _link_count(conn, trip_id),
        "phase1_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }, indent=2), encoding="utf-8")
    print(f"\nstate written: {_STATE_PATH}")
    conn.close()
    return _finish(1, trip_id, person_id, prior_live_state)


def _link_count(conn: sqlite3.Connection, trip_id: str) -> int:
    if not _has_links(conn):
        return 0
    return int(conn.execute(
        "SELECT COUNT(*) FROM trip_turn_links WHERE trip_id = ?;",
        (trip_id,)).fetchone()[0])


# ── phase 2 ───────────────────────────────────────────────────────────────

def do_phase2() -> int:
    print("\n=== VS1 LIVE ACCEPTANCE - PHASE 2 (after restart) ===\n")
    if not _STATE_PATH.exists():
        print(f"FATAL: no state file at {_STATE_PATH}. Run --phase 1 first.")
        return 2
    st = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    trip_id = st["trip_id"]
    person_id = st["person_id"]
    day_id = st["trip_day_id"]
    link_id = st["link_id"]
    print(f"API      : {_api_base()}")
    print(f"trip     : {trip_id}")
    print(f"day      : {day_id}")
    print(f"link     : {link_id}")
    print("")

    print("STEP 7 - the trip is still the active one")
    act = _get("/api/trips/active", person_id=person_id)
    check("GET /active still reports this trip",
          ((act.get("trip") or {}).get("id")) == trip_id,
          f"got {(act.get('trip') or {}).get('id')}")
    check("its live_state is still active",
          ((act.get("trip") or {}).get("live_state")) == "active")

    print("\nSTEP 8 - the selected day survived")
    cal = _get(f"/api/trips/{trip_id}/calendar")
    check("GET /calendar still reports the selected day",
          cal.get("selected_day_id") == day_id,
          f"got {cal.get('selected_day_id')}")

    print("\nSTEP 9 - the same timeline event is still there")
    tl = _get(f"/api/trips/{trip_id}/days/{day_id}/timeline")
    items = tl.get("items") or []
    mine = [i for i in items if i.get("link_id") == link_id]
    check("the linked conversation is still on the day", bool(mine),
          f"n={len(items)}")
    if mine:
        it = mine[0]
        check("it still shows what the narrator said",
              st["message_head"] in (it.get("narrator_said") or ""))
        check("it still shows what Lori said",
              bool((it.get("lori_said") or "").strip()))
        check("it is still Confirmed day",
              it.get("placement_status") == "confirmed")
        check("it still carries conv_id for source navigation",
              it.get("conv_id") == st["conv_id"])

    print("\nSTEP 10 - the database agrees, independently of the API")
    conn = _connect()
    row = conn.execute(
        "SELECT live_state, active_trip_day_id FROM trips WHERE id = ?;",
        (trip_id,)).fetchone()
    check("trips.live_state == active", row and row["live_state"] == "active")
    check("trips.active_trip_day_id == the selected day",
          row and row["active_trip_day_id"] == day_id)
    link = conn.execute("SELECT * FROM trip_turn_links WHERE id = ?;",
                        (link_id,)).fetchone()
    check("the link row is still there", link is not None)
    check("it still points at the trip and the day",
          link is not None and link["trip_id"] == trip_id
          and link["trip_day_id"] == day_id)
    check("the restart created no extra links",
          _link_count(conn, trip_id) == st["link_count_after_phase1"],
          f"{st['link_count_after_phase1']} -> {_link_count(conn, trip_id)}")
    turn = conn.execute("SELECT content FROM turns WHERE id = ?;",
                        (st["assistant_turn_row_id"],)).fetchone()
    check("the linked turn row still holds Lori's words",
          turn is not None and bool((turn["content"] or "").strip()))
    conn.close()
    return _finish(2, trip_id, person_id, st.get("prior_live_state", ""))


# ── --restore ─────────────────────────────────────────────────────────────

def do_restore() -> int:
    if not _STATE_PATH.exists():
        print(f"FATAL: no state file at {_STATE_PATH}.")
        return 2
    st = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    prior = st.get("prior_live_state") or "planning"
    res = _post(f"/api/trips/{st['trip_id']}/live-state", {"state": prior})
    ok = res.get("ok") is True
    print(f"live_state restored to {prior}: {'yes' if ok else 'NO'}")
    return 0 if ok else 1


# ── summary ───────────────────────────────────────────────────────────────

def _finish(phase: int, trip_id: str, person_id: str,
            prior_live_state: str) -> int:
    passed = [r for r in RESULTS if r["ok"]]
    failed = [r for r in RESULTS if not r["ok"]]
    print(f"\n=== PHASE {phase}: {len(passed)} passed, {len(failed)} failed "
          "===")
    for f in failed:
        print("  FAILED: " + f["name"] + ("   " + f["detail"]
                                          if f["detail"] else ""))
    _XFER_DIR.mkdir(parents=True, exist_ok=True)
    prev: Dict[str, Any] = {}
    if _EVIDENCE_PATH.exists():
        try:
            prev = json.loads(_EVIDENCE_PATH.read_text(encoding="utf-8"))
        except Exception:
            prev = {}
    prev[f"phase{phase}"] = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "api": _api_base(),
        "db": str(_DB_PATH),
        "env_provenance": _ENV_PROVENANCE,
        "trip_id": trip_id,
        "person_id": person_id,
        "prior_live_state": prior_live_state,
        "passed": len(passed),
        "failed": len(failed),
        "results": RESULTS,
    }
    _EVIDENCE_PATH.write_text(json.dumps(prev, indent=2), encoding="utf-8")
    print(f"evidence written: {_EVIDENCE_PATH}")
    if phase == 1 and not failed:
        print("\nNEXT: restart the stack, then run --phase 2")
        print("  bash scripts/stop_all.sh && bash scripts/start_all.sh")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", type=int, choices=(1, 2))
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--trip-id")
    ap.add_argument("--day-id")
    ap.add_argument("--person-id")
    ap.add_argument("--message", default=DEFAULT_MESSAGE)
    args = ap.parse_args()

    if not _DB_PATH.exists():
        print(f"FATAL: no database at {_DB_PATH}. DATA_DIR/DB_NAME are "
              "probably not the ones the server is using.")
        return 2

    if args.list:
        return do_list(args.person_id)
    if args.restore:
        return do_restore()
    if args.phase == 1:
        if not args.trip_id:
            print("FATAL: --trip-id is required. Run --list first.")
            return 2
        return do_phase1(args.trip_id, args.day_id, args.message)
    if args.phase == 2:
        return do_phase2()
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
