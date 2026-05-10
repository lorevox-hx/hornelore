"""Kent 6-chapter arc replay harness.

Drives the live chat_ws endpoint at ws://localhost:8082/api/chat/ws
directly — no UI, no Kent involvement. Sends Kent's verbatim
narrator turns from the prior transcripts plus the 6-chapter arc
test cases, captures Lori's responses, and reports whether the
deterministic-route intercepts (witness mode, meta-feedback, era
lane hints, dangling-determiner guard) actually fired.

Usage (from a normal terminal that can reach localhost:8082):
    python3 scripts/replay_kent_arc.py

Output:
    docs/reports/kent_replay_<timestamp>.md     — verdict per turn
    docs/reports/kent_replay_<timestamp>.jsonl  — raw turns + replies

What the harness sends, in order:

    T1. Era-click SYSTEM directive for "Coming of Age" — verifies
        the per-era LANE HINT lands ("military, work, school,
        marriage, or another responsibility")
    T2. "military came first" — verifies Lori does NOT pivot to
        "culture and camaraderie"
    T3. Kent's verbatim line 38 (5-fact basic-training) — verifies
        STRUCTURED_NARRATIVE detection + continuation invitation
        + NO scenery probe
    T4. Germany continuation — verifies witness mode stays in
        factual/event lane, NO sensory
    T5. Marriage to Janice / second Germany — same
    T6. Vince born / photographer for general — same
    T7. Kent's verbatim line 80 (META_FEEDBACK "you are being
        vague") — verifies meta-feedback intercept fires + skip-
        sensory ack + "basic training" anchor

Per-turn verification:
    - Did the deterministic route fire? (turn_mode in done event)
    - Did the response contain ANY forbidden term?
        (sights / sounds / smells / scenery / camaraderie /
         "how did you feel" / "what was that like emotionally")
    - Word count of response (witness mode targets ≤30 words)

After all turns, the harness tails api.log for the conv_id and
captures every [chat_ws][...][deterministic] / [witness] /
[meta-question] / [response-guards] / [extract][affect-name-guard]
log marker.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import websockets
except ImportError:
    print("ERROR: websockets package not installed.")
    print("Install with: pip install websockets")
    sys.exit(1)


# Kent's known person_id from the operator log
KENT_PERSON_ID = "4aa0cc2b-1f27-433a-9152-203bb1f69a55"

# WS endpoint — port 8000 is the API server (chat_ws), 8082 is the
# static UI server. FE connects via ORIGIN=http://localhost:8000.
WS_URL = os.environ.get("LV_WS_URL", "ws://localhost:8000/api/chat/ws")

# Conv id — fresh per replay so the session is isolated
CONV_ID = f"replay_kent_{uuid.uuid4().hex[:12]}"

# Where to write the report
REPORT_DIR = Path(__file__).resolve().parent.parent / "docs" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
TS = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
REPORT_MD = REPORT_DIR / f"kent_replay_{TS}.md"
REPORT_JSONL = REPORT_DIR / f"kent_replay_{TS}.jsonl"

# Forbidden terms — if any of these appear in a Lori response to
# a structured-narrative turn, the witness mode failed.
_FORBIDDEN_RX = re.compile(
    r"\b(?:sights|sounds|smells|scenery|camaraderie|teamwork|"
    r"how did (?:you|that) feel|what was that like emotionally|"
    r"sensory aspects?)\b",
    re.IGNORECASE,
)


# Turn pack — Kent's VERBATIM transcript turns from session
# switch_moyvj5ew_f70j (2026-05-09 21:48-22:09). These are not
# synthesized approximations — they're his actual words from the
# real session that walked him out. Replaying them against the
# fixed stack tells us exactly what new-Lori would have said at
# each juncture.
TEST_TURNS: List[Dict[str, Any]] = [
    {
        "label": "K1 era-click Coming of Age (verbatim SYSTEM directive from transcript)",
        "kind": "era_click",
        "turn_mode": "interview",
        "message": (
            "[SYSTEM: The narrator just selected 'Coming of Age' on the "
            "Life Map — they want to talk about this era of their life. "
            "Ask ONE warm, open question about this period. Frame the "
            "question in PAST TENSE — use words like 'was', 'were', 'had', "
            "'when you', 'back then', 'that time'. Anchor the question in "
            "the era explicitly: you may name it directly (e.g. 'During "
            "your coming of age...' or 'In your coming of age years...') "
            "so the narrator hears you connect to the specific period "
            "they chose. Concrete-life-path anchors for this era: "
            "military service, work, school, training, marriage, first "
            "major responsibilities, moving out. Frame the opener as: "
            "what major adult path came first — the Army/military, work, "
            "school, marriage, or another responsibility? Do NOT default "
            "to feelings/sensory/people-who-supported-you framings unless "
            "the narrator volunteers them. Maximum 55 words. ONE question "
            "only. No menu choices. No 'or we could' phrasing. No "
            "compound 'and how / and what' follow-ups.]"
        ),
        "expected_passing_phrases": [
            "military", "work", "school", "marriage", "responsibility",
        ],
        "verify_deterministic_route": False,
    },
    {
        "label": "K2 'military came first' (verbatim)",
        "kind": "narrator_short",
        "turn_mode": "interview",
        "message": "military came first",
        "expected_passing_phrases": ["army", "military", "training", "service"],
        "verify_deterministic_route": False,
    },
    {
        "label": "K3 Kent verbatim — induction at Stanley/Fargo, meal tickets (long-form)",
        "kind": "narrator_structured",
        "turn_mode": "interview",
        "message": (
            "okay okay after going through the recruiting process for "
            "enlisting into the army my dad drove me into the railroad "
            "Depot at Stanley to put me on the train to go to Fargo for "
            "the induction physical and testing I took test there and I "
            "did medical exam and everything and after the physical exam "
            "they decided that because of my score on the induction "
            "physical and mental exam that they were going to put me in "
            "charge of the meal tickets for paying the meals on paying "
            "for the meals on their train on the way over to the West "
            "Coast we were going"
        ),
        "expected_passing_phrases": [
            "tell me more", "what happened next", "what came next",
            "go on",
        ],
        "verify_deterministic_route": True,
        "expected_turn_mode": "witness",
    },
    {
        "label": "K4 Kent verbatim — train fight, Fort Ord, M1 expert, Nike Ajax selection (long-form)",
        "kind": "narrator_structured",
        "turn_mode": "interview",
        "message": (
            "after getting on the train and fighting with the conductor "
            "once in awhile about the quality of the sloppy meals they "
            "were giving us and I finally resisted one of the payments "
            "and wanted to get a little bit better quality oatmeal and "
            "after a couple of threats and they decided that they would "
            "do that and just provide us with more meal better meals on "
            "the way out to Fort Ord California at Fort Ord we did the "
            "usual 8 weeks of basic training all the physical and mental "
            "stuff and then I got sent out for a couple of extra tests "
            "to qualify me for High School GED testing and when I finish "
            "there I had a high enough score that I had made I scored "
            "expert on the use of the M1 rifle M1 rifle and then at the "
            "end of Basic Training Day called each of us in for a "
            "decision on where we were going to call I had originally "
            "enlisted for participation in army security service and "
            "when I went in for my interview I was told that I would "
            "have to wait for 3 months I'd have to go out off duty and "
            "go home for 3 months until there was an opening available "
            "on training for National Security Agency Army Security "
            "Agency rather so I asked for other choices and one of the "
            "other choices was the Army on Nike Ajax Nike Hercules "
            "guided missile system radar and computer operator so I "
            "selected that and I got picked for that"
        ),
        "expected_passing_phrases": [
            "tell me more", "what happened", "go on",
        ],
        "verify_deterministic_route": True,
        "expected_turn_mode": "witness",
    },
    {
        "label": "K5 Kent verbatim — Detroit Southridge → Germany → Janice fiancee (long-form)",
        "kind": "narrator_structured",
        "turn_mode": "interview",
        "message": (
            "and then send oh okay so after busy training then they got "
            "selected to go to a couple of Nike Hercules sites the first "
            "one on the list was at Detroit Michigan Southridge Air "
            "Force Base and went there for training on the army Nike "
            "Ajax Nike Air Kelly's missile system radar operator "
            "computer operator and once there was a sort of sad slow "
            "training it was just not much except practice linking up "
            "with the radar signals to make a detection and after that "
            "sometime after about a year there I got notified I was "
            "being psyched to go to Germany to work in the same Nike "
            "Ajax and I currently systems and how I had to go home for "
            "a couple of weeks required vacation and then took the trip "
            "to Germany to get started on a training there after I'd "
            "been there for less than a year I contacted my fiance "
            "Janice and told her that if we were going to get married "
            "we should get married and be able to live in Germany "
            "because it was a wonderful place and"
        ),
        "expected_passing_phrases": [
            "tell me more", "what happened", "go on",
        ],
        "verify_deterministic_route": True,
        "expected_turn_mode": "witness",
    },
    {
        "label": "K6 Kent verbatim — Bismarck wedding at Cathedral of the Holy Spirit (long-form)",
        "kind": "narrator_structured",
        "turn_mode": "interview",
        "message": (
            "in Germany was fantastic it's a lot to learn and after I've "
            "been there for a bit then I got to leave to go home come "
            "back to Bismarck and Janice's family had put together a "
            "terrific marriage ceremony for us at the at the Cathedral "
            "of the Holy Spirit Leonard Duffy was the one that performed "
            "the marriage ceremony it was great and then we got "
            "everything organized and headed back to Germany"
        ),
        "expected_passing_phrases": [
            "tell me more", "what happened", "go on",
        ],
        "verify_deterministic_route": True,
        "expected_turn_mode": "witness",
    },
    {
        "label": "K7 Kent verbatim — Salamander/Kaiserslautern, courier, photographer for 32nd (long-form)",
        "kind": "narrator_structured",
        "turn_mode": "interview",
        "message": (
            "well among the various things that happened in Germany I "
            "first was assigned to I Nike Ajax Nike Hercules missile "
            "site at what was the city and Germany the first one started "
            "with food places to salamander true Factory and a couple "
            "of things went on there I was assigned to go up to an army "
            "site up in the mountains for training in use of chemical "
            "biological radiological training and did that and after "
            "some time at that missile site I was asked to be the "
            "replacement Courier document Courier for their mail run to "
            "replace Johnny Johnson who was going home on leave and so "
            "I did that and it got a little one day training for the "
            "route to run that and then after getting back to that did "
            "a number of things but in the course of doing The Courier "
            "document Courier thing I stopped in at the 32nd Artillery "
            "Brigade office in Kaiserslautern Germany and I asked if "
            "there was anything open for photographers in the 32nd "
            "Brigade and the officer in charge said yes there was and "
            "I could move up move in and start doing that and be a "
            "photographer for the 32nd Brigade which I did and"
        ),
        "expected_passing_phrases": [
            "tell me more", "what happened", "go on",
        ],
        "verify_deterministic_route": True,
        "expected_turn_mode": "witness",
    },
    {
        "label": "K8 Kent verbatim — General Peter Schmick, son Vince born (long-form)",
        "kind": "narrator_structured",
        "turn_mode": "interview",
        "message": (
            "that was General Peter Schmick a Canadian born General "
            "officer in the American Army and I went to work for them "
            "and we moved into up to Kaiserslautern then and while we "
            "were there our oldest son Vince was born and let's see we "
            "had to take care of a lot of constant change in the "
            "production photographer for the Brigade and then"
        ),
        "expected_passing_phrases": [
            "tell me more", "what happened", "go on",
        ],
        "verify_deterministic_route": True,
        "expected_turn_mode": "witness",
    },
    {
        "label": "K9 Kent verbatim — Vince born at (Lansdale wrong) hospital, citizenship (long-form)",
        "kind": "narrator_structured",
        "turn_mode": "interview",
        "message": (
            "while we were in Kaiserslautern our son Vince was born at "
            "the Lansdale Army hospital and we took care of all of the "
            "birth registration and everything through the embassy I "
            "think or attache I think Embassy in Frankfort one on a "
            "trip was a couple up to take the baby up and get him "
            "registered and we did that so then he had the opportunity "
            "to be to choose to be one National or the other or pool or "
            "a dual National later on he never followed up on getting "
            "the second nationality and just stayed with the American "
            "nationality but he was born as an American citizen"
        ),
        "expected_passing_phrases": [
            "tell me more", "what happened", "go on",
        ],
        "verify_deterministic_route": True,
        "expected_turn_mode": "witness",
    },
    {
        "label": "K10 Kent verbatim — hospital correction (Landstuhl not Lansdale)",
        "kind": "narrator_correction",
        "turn_mode": "interview",
        "message": (
            "you have the name of the hospital wrong not Lansdale Army "
            "hospital  but landstuhl air force hospital ramstein air "
            "force base"
        ),
        "expected_passing_phrases": [
            "got it", "landstuhl", "thank you", "noted",
        ],
        "verify_deterministic_route": False,
    },
    {
        "label": "K11 Kent verbatim — META_FEEDBACK 'you are being vague' (from earlier session)",
        "kind": "narrator_meta_feedback",
        "turn_mode": "interview",
        "message": (
            "You are being vague and not asking about basic training "
            "rather the sensory parts of it. I want to tell my "
            "experience and you want to know how I felt"
        ),
        "expected_passing_phrases": [
            "got it", "skip", "basic training", "what happened next",
        ],
        "verify_deterministic_route": True,
        "expected_turn_mode": "witness",
    },
]


def _build_runtime71(turn_idx: int) -> Dict[str, Any]:
    """Build a runtime71 dict approximating what the FE sends.
    Keeps it minimal — just the fields that drive composer behavior."""
    return {
        "current_pass": "pass2a",
        "current_era": "coming_of_age",
        "current_mode": "open",
        "affect_state": "neutral",
        "affect_confidence": 0,
        "cognitive_mode": "open",
        "fatigue_score": 0,
        "paired": False,
        "paired_speaker": None,
        "visual_signals": None,
        "assistant_role": "interviewer",
        "session_style_directive": "Ask one short question at a time. Avoid open-ended exploration. Acknowledge briefly, then move on.",
        "identity_complete": True,
        "identity_phase": "complete",
        "effective_pass": "pass2a",
        "speaker_name": "Kent",
        "dob": None,
        "pob": "Stanley ND",
        "profile_seed": {
            "childhood_home": None,
            "siblings": None,
            "parents_work": None,
            "heritage": None,
            "education": None,
            "military": None,
            "career": None,
            "partner": None,
            "children": None,
            "life_stage": None,
        },
        "device_context": {
            "date": datetime.now().strftime("%A, %B %-d, %Y"),
            "time": datetime.now().strftime("%-I:%M %p"),
            "timezone": "America/Denver",
        },
        "location_context": None,
        "memoir_context": {
            "state": "structured",
            "arc_roles_present": [],
            "meaning_tags_present": [],
        },
        "media_count": 0,
        "projection_family": None,
        "person_id": KENT_PERSON_ID,
        "conversation_state": "answering",
        "cognitive_support_mode": False,
        "chronology_context": None,
    }


async def _send_turn(ws, turn_idx: int, turn: Dict[str, Any]) -> Dict[str, Any]:
    """Send one turn, await the done event, return the captured
    response + metadata."""
    runtime71 = _build_runtime71(turn_idx)
    payload = {
        "type": "start_turn",
        "session_id": CONV_ID,
        "conv_id": CONV_ID,
        "message": turn["message"],
        "turn_mode": turn["turn_mode"],
        "params": {
            "person_id": KENT_PERSON_ID,
            "runtime71": runtime71,
            "turn_mode": turn["turn_mode"],
        },
    }
    await ws.send(json.dumps(payload))

    final_text = ""
    turn_mode_done = ""
    extras: Dict[str, Any] = {}
    # 90s overall turn budget; slow LLM streams can pause >10s between
    # token events on a warm-but-busy stack. Per-recv timeout bumped to
    # 30s so a slow LLM on a long Kent narrative doesn't get reported
    # as empty (K9 harness misread root cause, 2026-05-09).
    timeout_at = asyncio.get_event_loop().time() + 90.0
    while asyncio.get_event_loop().time() < timeout_at:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=30.0)
        except asyncio.TimeoutError:
            break
        try:
            ev = json.loads(raw)
        except Exception:
            continue
        ev_type = ev.get("type")
        if ev_type == "done":
            final_text = ev.get("final_text") or ""
            turn_mode_done = ev.get("turn_mode") or ""
            extras = {
                k: v for k, v in ev.items()
                if k not in ("type", "final_text", "turn_mode")
            }
            break
        elif ev_type == "error":
            final_text = f"[error: {ev.get('message', 'unknown')}]"
            break

    return {
        "final_text": final_text,
        "turn_mode": turn_mode_done,
        "extras": extras,
    }


def _verify_turn(turn: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    """Build a verdict dict for one turn."""
    text = result["final_text"]
    text_lower = text.lower()
    word_count = len(text.split())

    forbidden_hits = _FORBIDDEN_RX.findall(text)
    forbidden_match = forbidden_hits[0] if forbidden_hits else ""

    expected_passing = turn.get("expected_passing_phrases", [])
    matched_passing = [
        p for p in expected_passing
        if p.lower() in text_lower
    ]

    verdict = "PASS"
    notes = []

    if not text or text.startswith("[error"):
        verdict = "ERROR"
        notes.append(f"empty or error response: {text!r}")
    elif forbidden_match:
        verdict = "FAIL"
        notes.append(f"forbidden term in response: {forbidden_match!r}")
    elif turn.get("verify_deterministic_route"):
        expected_mode = turn.get("expected_turn_mode", "witness")
        if result["turn_mode"] != expected_mode:
            verdict = "FAIL"
            notes.append(
                f"turn_mode={result['turn_mode']!r} expected={expected_mode!r} "
                f"— deterministic intercept did NOT fire"
            )

    if not matched_passing and turn["kind"] != "narrator_short":
        if verdict == "PASS":
            verdict = "AMBER"
        notes.append(
            f"no expected-passing-phrase matched (looked for: "
            f"{expected_passing})"
        )

    return {
        "label": turn["label"],
        "verdict": verdict,
        "word_count": word_count,
        "turn_mode_done": result["turn_mode"],
        "forbidden_hit": forbidden_match,
        "matched_passing": matched_passing,
        "extras": result["extras"],
        "notes": notes,
        "lori_text": text,
    }


async def main() -> None:
    print(f"Replay harness — Kent (person_id={KENT_PERSON_ID})")
    print(f"  WS:      {WS_URL}")
    print(f"  conv_id: {CONV_ID}")
    print(f"  report:  {REPORT_MD}")
    print()

    results: List[Dict[str, Any]] = []
    raw_log = []

    async with websockets.connect(WS_URL, max_size=10_000_000) as ws:
        # Wait for the connected status event
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            print(f"  ws connected: {raw[:100]}")
        except asyncio.TimeoutError:
            print("  ws connected (no greeting)")

        # sync_session
        await ws.send(json.dumps({
            "type": "sync_session",
            "person_id": KENT_PERSON_ID,
        }))
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            print(f"  session_verified: {raw[:200]}")
        except asyncio.TimeoutError:
            print("  WARNING: no session_verified response")

        # Replay turns sequentially
        for idx, turn in enumerate(TEST_TURNS, 1):
            print(f"\n[{idx}/{len(TEST_TURNS)}] {turn['label']}")
            print(f"    user>  {turn['message'][:120]}{'...' if len(turn['message']) > 120 else ''}")
            result = await _send_turn(ws, idx, turn)
            verdict = _verify_turn(turn, result)
            results.append(verdict)
            raw_log.append({
                "turn_idx": idx,
                "turn": turn,
                "result": result,
                "verdict": verdict,
            })
            print(f"    lori<  ({verdict['turn_mode_done'] or 'llm'}, {verdict['word_count']}w) "
                  f"{result['final_text'][:200]}")
            print(f"    verdict: {verdict['verdict']}"
                  + (f" — {'; '.join(verdict['notes'])}" if verdict["notes"] else ""))
            # Brief pause to let api.log catch up + avoid LLM rate
            await asyncio.sleep(1.0)

    # Write reports
    with open(REPORT_JSONL, "w", encoding="utf-8") as fp:
        for entry in raw_log:
            fp.write(json.dumps(entry, default=str) + "\n")

    md_lines = [
        f"# Kent replay — {TS}",
        f"",
        f"- **conv_id:** `{CONV_ID}`",
        f"- **person_id:** `{KENT_PERSON_ID}`",
        f"- **WS:** `{WS_URL}`",
        f"- **turns:** {len(results)}",
        f"",
        "## Topline",
        f"",
    ]
    pass_n = sum(1 for r in results if r["verdict"] == "PASS")
    fail_n = sum(1 for r in results if r["verdict"] == "FAIL")
    amber_n = sum(1 for r in results if r["verdict"] == "AMBER")
    err_n = sum(1 for r in results if r["verdict"] == "ERROR")
    md_lines.append(f"- PASS: {pass_n}")
    md_lines.append(f"- FAIL: {fail_n}")
    md_lines.append(f"- AMBER: {amber_n}")
    md_lines.append(f"- ERROR: {err_n}")
    md_lines.append("")
    md_lines.append("## Per-turn verdicts")
    md_lines.append("")
    for r in results:
        md_lines.append(f"### {r['label']}  →  **{r['verdict']}**")
        md_lines.append(f"")
        md_lines.append(f"- turn_mode: `{r['turn_mode_done'] or '(llm)'}`")
        md_lines.append(f"- words: {r['word_count']}")
        if r['forbidden_hit']:
            md_lines.append(f"- ⚠️ forbidden term: `{r['forbidden_hit']}`")
        if r['matched_passing']:
            md_lines.append(f"- matched expected: {r['matched_passing']}")
        if r['notes']:
            md_lines.append(f"- notes: {'; '.join(r['notes'])}")
        md_lines.append("")
        md_lines.append("**Lori said:**")
        md_lines.append("")
        md_lines.append(f"> {r['lori_text']}")
        md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("## Next: tail api.log for deterministic-route markers")
    md_lines.append("")
    md_lines.append("```bash")
    md_lines.append(f"grep -E '\\[chat_ws\\]\\[(witness|meta-question|response-guards)\\]' \\\\")
    md_lines.append(f"  /mnt/c/Users/chris/hornelore/.runtime/logs/api.log \\\\")
    md_lines.append(f"  | grep '{CONV_ID[:25]}' | tail -30")
    md_lines.append("```")
    md_lines.append("")

    REPORT_MD.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"\n=== Topline ===")
    print(f"  PASS: {pass_n}  FAIL: {fail_n}  AMBER: {amber_n}  ERROR: {err_n}")
    print(f"\nReports written:")
    print(f"  {REPORT_MD}")
    print(f"  {REPORT_JSONL}")


if __name__ == "__main__":
    asyncio.run(main())
