#!/usr/bin/env python3
"""Step 6 live acceptance — the production WebSocket, one synthetic narrator.

WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 2, Step 6.

    cd /mnt/c/Users/chris/hornelore
    .venv-gpu/bin/python scripts/step6_ws_probe.py

**Chris starts the stack. This script never does**, and it never
restarts it. It assumes `http://localhost:8000` is up and the extractor
is warm; a cold boot takes about four minutes and a `curl /` proves only
that the socket is listening.

── WHAT THIS PROVES, AND WHY A UNIT TEST CANNOT ──────────────────────

The Step 6 suites exercise the real rules against a real database, and
`test_profile_seed_deterministic_paths` pins that the router calls them
in the right order. Neither runs the actual WebSocket, the actual model,
or the actual prompt. This does. It is the only instrument that can show
Lori ASKING the first canonical topic in her own words and then not
asking it again.

── THE NARRATOR IS SYNTHETIC, AND NOTHING ELSE IS TOUCHED ────────────

Authorized by Chris, 2026-08-28, as one clearly disposable narrator.

  * created through the product endpoint `POST /api/people`, so
    migration 0051's enrollment runs exactly as it does for a real
    narrator — not by an INSERT that would bypass the thing under test;
  * a reserved conversation id used by nothing else;
  * **no existing narrator is read, enrolled, backfilled, paused,
    resumed, switched to, or modified.** The probe never calls
    `sync_session` with any id but its own.

**IT DELETES NOTHING, INCLUDING ITSELF.** The narrator is preserved for
review. Deletion happens later, on Chris's explicit authorization,
through the product erasure path — never from here, because a probe that
tidies up after itself destroys the evidence it was run to produce.

── HOW IT REPORTS ────────────────────────────────────────────────────

Every check prints PASS or FAIL with the value it saw. The exit code is
non-zero if any check failed. The final section is an INVENTORY —
person id, conversation id, session row, turn ids, onboarding row — so
the artifacts this probe created can be found and erased deliberately.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests
    import websockets
except ImportError as exc:  # pragma: no cover - operator-facing
    sys.exit(f"missing dependency: {exc}. Run with .venv-gpu/bin/python "
             "(requirements-gpu.txt pins websockets==16.0 and requests).")

API = os.environ.get("HORNELORE_API", "http://localhost:8000")
WS_URL = API.replace("http://", "ws://").replace("https://", "wss://") + "/api/chat/ws"

# ── PRE-REGISTERED IDENTIFIERS ────────────────────────────────────────
#
# Recorded here BEFORE the probe runs, so the artifacts it creates were
# named in advance rather than discovered afterwards.
#
# ── A CLOSED REGISTRY, NOT A `--name` FLAG, 2026-08-29 ────────────────
#
# Run 1 was performed with an uncommitted working copy of this script.
# The product tree was byte-identical to the accepted commit and the
# result stands on its own, but the INSTRUMENT was not in Git, so that
# run is not reproducible from a revision — which is exactly the
# property the repository's clean-tree rule exists to protect. Run 2
# repeats it from a committed instrument on a clean tree.
#
# That needs a second identity, and the obvious way to get one — a
# `--name` argument — is the wrong way. A free-text narrator name on a
# script that CREATES narrators and drives live turns is one typo away
# from pointing at a real person. The identities are therefore a closed
# registry: two entries, chosen by number, and anything else refuses.
#
# Run 1's identity is kept here rather than deleted. It names a narrator
# that still exists and whose inventory is preserved for review, and a
# probe that forgot its own earlier subject could recreate it.
PROBES: Dict[int, Dict[str, str]] = {
    1: {"name": "ZZ Step6 WebSocket Probe (delete me)",
        "conv": "step6-ws-probe-2026-08-28"},
    2: {"name": "ZZ Step6 WebSocket Probe 2 (delete me)",
        "conv": "step6-ws-probe-2-2026-08-28"},
}
#: Run 2 is the clean-tree acceptance run and is therefore the default.
#
# Parsed defensively: `int()` on a non-numeric value raises `ValueError`
# and would reach the operator as a traceback from a line that looks
# like configuration. A script that creates narrators refuses clearly.
_RAW_PROBE = os.environ.get("STEP6_PROBE", "2").strip()
if not _RAW_PROBE.isdigit() or int(_RAW_PROBE) not in PROBES:
    sys.exit(f"STEP6_PROBE must be one of {sorted(PROBES)}; got "
             f"{_RAW_PROBE!r}. The identities are a closed registry on "
             "purpose — this script creates narrators and drives live turns, "
             "and a free-text name is one typo away from a real person.")
PROBE_N = int(_RAW_PROBE)

PROBE_NAME = PROBES[PROBE_N]["name"]
CONV_ID = PROBES[PROBE_N]["conv"]
PROBE_DOB = "1901-01-01"
PROBE_POB = "Probeville, Testland"
#: The person id is minted by the product path and inventoried below.

DB_PATH = Path(os.environ.get(
    "HORNELORE_DB", "/mnt/c/hornelore_data/db/hornelore.sqlite3"))

_RESULTS: List[bool] = []


def check(ok: bool, label: str, saw: Any = "") -> bool:
    _RESULTS.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}"
          + (f"\n         saw: {saw}" if saw != "" else ""))
    return bool(ok)


def sql(query: str, args: tuple = ()) -> List[sqlite3.Row]:
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return con.execute(query, args).fetchall()
    finally:
        con.close()


def turns() -> List[Dict[str, Any]]:
    rows = sql("SELECT id, role, content, meta_json FROM turns "
               "WHERE conv_id=? ORDER BY id ASC;", (CONV_ID,))
    out = []
    for r in rows:
        try:
            meta = json.loads(r["meta_json"] or "{}")
        except Exception:
            meta = {}
        out.append({"id": r["id"], "role": r["role"],
                    "content": r["content"], "meta": meta})
    return out


def onboarding(person_id: str) -> Optional[sqlite3.Row]:
    rows = sql("SELECT * FROM profile_seed_onboarding WHERE person_id=?;",
               (person_id,))
    return rows[0] if rows else None


def assistant_meta() -> List[Dict[str, Any]]:
    return [t["meta"] for t in turns() if t["role"] == "assistant"]


async def say(person_id: str, text: str, *, turn_mode: str = "interview",
              timeout: float = 180.0) -> str:
    """One production turn. Returns Lori's final text.

    The timeout is generous on purpose: it must cover generation, and
    the repo's TTS rule is explicit that a timeout sized for text fails
    a working spoken turn.
    """
    async with websockets.connect(WS_URL, max_size=8 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"type": "sync_session",
                                  "person_id": person_id}))
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout))
            if msg.get("type") == "session_verified":
                break
        await ws.send(json.dumps({
            "type": "start_turn",
            "session_id": CONV_ID,
            "message": text,
            "turn_mode": turn_mode,
            "params": {"person_id": person_id, "surface": "narrator"},
        }))
        final = ""
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout))
            kind = msg.get("type")
            if kind == "done":
                return msg.get("final_text") or final
            if kind == "error":
                raise RuntimeError(f"server error frame: {msg.get('message')}")
            if kind == "token":
                final += msg.get("delta") or ""
        raise TimeoutError(f"no 'done' frame within {timeout}s")


async def main() -> int:
    print(f"Step 6 live acceptance — {API}")
    print(f"  probe number     : {PROBE_N} of {sorted(PROBES)}")
    print(f"  reserved conv_id : {CONV_ID}")
    print(f"  narrator name    : {PROBE_NAME}")
    print(f"  database         : {DB_PATH}\n")

    if not DB_PATH.exists():
        return int(not check(False, "database is readable", str(DB_PATH)))

    existing = sql("SELECT id FROM people WHERE display_name=?;", (PROBE_NAME,))
    if existing:
        print(f"  probe narrator already exists: {existing[0]['id']}")
        print("  REFUSING to create a second one. Erase the first through "
              "the product path, or read its inventory below.")
        return 1

    # ── 1. Create through the PRODUCT path ────────────────────────────
    # `testing_only` is the correct flag and it is not a shortcut past
    # consent: the endpoint requires both consent attestations unless a
    # narrator is declared synthetic, and this one IS synthetic. Setting
    # it false and forging the two consent booleans would record a
    # fabricated attestation for a person who does not exist.
    resp = requests.post(f"{API}/api/people", json={
        "display_name": PROBE_NAME,
        "date_of_birth": PROBE_DOB,
        "place_of_birth": PROBE_POB,
        "narrator_type": "live",
        "testing_only": True,
    }, timeout=30)
    resp.raise_for_status()
    # The endpoint returns `person_id` alongside the full `person` row and
    # the consent attestations — NOT a bare `id`. Read the documented key.
    body = resp.json() or {}
    person_id = body.get("person_id") or (body.get("person") or {}).get("id")
    print(f"  MINTED person_id : {person_id}\n")
    if not person_id:
        return int(not check(False, "product endpoint returned a person id",
                             resp.text[:200]))

    row = onboarding(person_id)
    check(row is not None,
          "migration 0051 enrolled the new narrator (product path, not INSERT)")
    if row is None:
        return 1
    # ── ENROLLMENT STARTS `pending`, AND THAT IS CORRECT ──────────────
    #
    # *(An earlier version of this probe asserted `active` here and
    # captured the topic and version BEFORE any turn. Both were wrong,
    # and they would have failed on the first live run for a reason that
    # has nothing to do with Step 6. `enroll()` writes `pending` at
    # version 1; `resolve_effective()` materializes it to `active` once
    # the identity anchors resolve, and it BUMPS THE VERSION when it
    # changes anything. So the presentation is stamped at version 2,
    # and a pre-turn capture would have compared against version 1.)*
    #
    # The pre-turn claim is therefore about enrollment only. The walk's
    # tuple is read after the first turn, from the row the WebSocket's
    # own resolve materialized.
    check(row["status"] == "pending" and row["version"] == 1,
          "enrollment starts pending at version 1, as Phase 1 accepted",
          f"{row['status']} @ v{row['version']}")

    # ── 2. Lori presents ──────────────────────────────────────────────
    print("\nTURN 1 — the narrator says hello; Lori should present topic one")
    reply1 = await say(person_id, "Hello Lori.")
    print(f"         Lori: {reply1[:160]}")

    row = onboarding(person_id)
    check(row["status"] == "active",
          "the WebSocket's resolve materialized the walk to ACTIVE",
          f"{row['status']} @ v{row['version']}")
    first_topic, first_version = row["active_topic_id"], row["version"]
    print(f"         walk now at: {first_topic} @ v{first_version}")

    metas = assistant_meta()
    check(any(m.get("profile_seed_presented_topic") == first_topic
              and m.get("profile_seed_presented_version") == first_version
              for m in metas),
          "the committed assistant row carries presented(topic, version) "
          "matching the authoritative row",
          metas[-1] if metas else "no assistant row")
    check(all("profile_seed_response_topic" not in m for m in metas),
          "no response event was stamped by a presentation")
    # "Advanced nothing" cannot be a before/after version comparison,
    # because materialization legitimately moves the version on this
    # first turn. The claim that matters is that the walk still sits on
    # the topic it just asked about — asking is not answering.
    check(row["active_topic_id"] == first_topic,
          "asking advanced NOTHING — the walk still sits on the topic "
          "it just presented",
          f"{row['active_topic_id']} @ v{row['version']}")

    # ── 3. The narrator answers ───────────────────────────────────────
    print("\nTURN 2 — the narrator answers; Lori should acknowledge, not re-ask")
    reply2 = await say(person_id, "I grew up in Probeville, on a quiet street.")
    print(f"         Lori: {reply2[:160]}")
    metas = assistant_meta()
    last = metas[-1] if metas else {}
    check(last.get("profile_seed_response_topic") == first_topic
          and last.get("profile_seed_response_version") == first_version,
          "the acknowledgement row carries response(topic, version, disposition)",
          last)
    check(last.get("profile_seed_response_disposition") == "addressed",
          "the disposition is `addressed`",
          last.get("profile_seed_response_disposition"))
    check("profile_seed_presented_topic" not in last,
          "the acknowledgement did NOT ask the next topic in the same turn",
          last)
    row = onboarding(person_id)
    check(row["active_topic_id"] != first_topic,
          "durable onboarding advanced AFTER the commit",
          f"{row['active_topic_id']} @ v{row['version']}")
    second_topic, second_version = row["active_topic_id"], row["version"]

    # ── 4. The next canonical topic ───────────────────────────────────
    print("\nTURN 3 — Lori should now present the NEXT canonical topic")
    reply3 = await say(person_id, "What else would you like to know?")
    print(f"         Lori: {reply3[:160]}")
    last = assistant_meta()[-1]
    check(last.get("profile_seed_presented_topic") == second_topic,
          "the next turn presents the next canonical topic", last)

    # ── 5. A control turn must not advance ────────────────────────────
    print("\nTURN 4 — a control turn; it must HOLD and stamp nothing")
    before = onboarding(person_id)
    await say(person_id, "pause")
    last = assistant_meta()[-1]
    after = onboarding(person_id)
    check(not any(k.startswith("profile_seed_") for k in last),
          "the control turn stamped no Profile Seed metadata", last)
    check(after["active_topic_id"] == before["active_topic_id"]
          and after["version"] == before["version"],
          "the control turn advanced nothing",
          f"{after['active_topic_id']} @ v{after['version']}")

    # ── 6. Reconnect ──────────────────────────────────────────────────
    #
    # A DEFERRAL, deliberately, and the earlier draft got this wrong.
    #
    # *(It said "Sorry, I'm back." — which `classify_response` reads as
    # an ANSWER, because everything non-empty that is not a refusal, a
    # deferral or a control is `addressed`. The HOLD on turn 4 stamped
    # nothing, so topic two's presentation was still outstanding, and
    # that turn would have ACKNOWLEDGED it and advanced the walk — then
    # failed the very check it was written to make.)*
    #
    # A deferral re-presents the same question and applies nothing, so
    # what it proves is exactly the claim: the outstanding tuple
    # survived a control turn and a fresh socket.
    print("\nTURN 5 — a NEW socket; the outstanding question must survive")
    reply5 = await say(person_id, "let me think")
    print(f"         Lori: {reply5[:160]}")
    last = assistant_meta()[-1]
    after = onboarding(person_id)
    check(last.get("profile_seed_presented_topic") == second_topic,
          "the reconnected turn re-presented the SAME outstanding topic",
          last)
    check("profile_seed_response_topic" not in last,
          "a deferral recorded no response event", last)
    check(after["active_topic_id"] == second_topic,
          "reconnecting preserved the outstanding state and advanced nothing",
          f"{after['active_topic_id']} @ v{after['version']}")

    # ── INVENTORY — everything this probe created ─────────────────────
    print("\n" + "=" * 68)
    print("INVENTORY — preserve this. Deletion needs Chris's authorization")
    print("=" * 68)
    print(f"  person_id        : {person_id}")
    print(f"  display_name     : {PROBE_NAME}")
    print(f"  conv_id          : {CONV_ID}")
    rows = sql("SELECT id, person_id FROM interview_sessions WHERE id=?;",
               (CONV_ID,))
    print(f"  session row      : {dict(rows[0]) if rows else 'none'}")
    tl = turns()
    print(f"  turn ids         : {[t['id'] for t in tl]}  ({len(tl)} rows)")
    ob = onboarding(person_id)
    print(f"  onboarding row   : status={ob['status']} "
          f"active={ob['active_topic_id']} version={ob['version']}")
    for label, query in (
            ("story candidates", "SELECT id FROM story_candidates WHERE narrator_id=?;"),
            ("photos", "SELECT id FROM photos WHERE narrator_id=?;"),
    ):
        try:
            found = sql(query, (person_id,))
            print(f"  {label:<16} : {[r['id'] for r in found] or 'none'}")
        except sqlite3.Error as exc:
            print(f"  {label:<16} : (not queryable: {exc})")
    data_dir = Path(os.environ.get("DATA_DIR", "/mnt/c/hornelore_data"))
    for sub in ("memory/archive/people", "kawa/people", "media/archive/people"):
        p = data_dir / sub / person_id
        print(f"  {sub}/<id> : {'EXISTS' if p.exists() else 'absent'}")

    failed = _RESULTS.count(False)
    print("\n" + "=" * 68)
    print(f"  {len(_RESULTS) - failed}/{len(_RESULTS)} checks passed"
          + (f" — {failed} FAILED" if failed else ""))
    print("  This narrator was NOT deleted. That is deliberate.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
