#!/usr/bin/env python3
"""JAKE MAX MILLER long-narration harness — Kent content, fresh narrator.

End-to-end test of the WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01 + the
oral-history / Phase 1 / reflection-grounding stack on a freshly-created
narrator:

  1. POST /api/people/intake — creates Jake Max Miller with the full
     9-section intake payload (DOB 1939-12-24, Stanley ND, parents,
     siblings, spouse, children, Army service, faith, etc.). This step
     alone exercises the WO end-to-end as a live integration test —
     if /api/people/intake 422s, the WO is broken.

  2. Opens a chat WebSocket connection at ws://localhost:8000/api/chat/ws
     with Jake's new person_id.

  3. Sends three long-form chapters (Earliest Years / Early School Years
     / Later Years) as three separate narrator turns. Captures Lori's
     full response per turn. The chapters are drawn from Kent James
     Horne's biographical material rewritten as Jake's first-person
     monologue — same era and historical anchors that broke the May 11
     Kent transcript, so any regression in the stack will surface here.

  4. Sends the bonus probe ("anyway, that's about it…") as a short
     closing-marker turn to exercise the thread-bank surfacing rules
     under low-momentum / closing-marker mode.

  5. Scores each chapter against the 8-row checklist from the WO spec
     (reflection grounded, one-question max, no questionnaire interrogation,
     no forbidden empathy openers, no era-label menu, no same-anchor loop,
     word budget honored, translation absent).

  6. Greps the live api.log for the WO sequence signatures (oral_history
     posture firing per turn, reflection-not-grounded markers, extraction
     accepted counts, the May 11 "meal tickets" sanity check).

  7. Writes a full report (verbatim Lori responses + per-chapter matrix +
     log grep summary) to docs/reports/jake_long_narration_<conv_id>.txt.

Usage:

    cd /mnt/c/Users/chris/hornelore
    python3 scripts/run_jake_long_narration_harness.py

Stack must be warm. Cold-boot run will timeout the first chapter.

Pass criteria (per chapter): see SCORING.md inline below.
Acceptance: 3/3 chapters PASS + bonus probe surfaces one thread anchor
or stays warm-with-no-surface (both acceptable per spec).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import websockets
except ImportError:
    print(
        "Missing dependency: websockets. Try: python3 -m pip install websockets",
        file=sys.stderr,
    )
    raise

try:
    import urllib.request
    import urllib.error
except ImportError:
    print("urllib missing — Python install is broken", file=sys.stderr)
    raise


# ── Configuration ──────────────────────────────────────────────────────────

API_BASE = os.environ.get("HORNELORE_API_BASE", "http://localhost:8000")
WS_URL = f"{API_BASE.replace('http', 'ws')}/api/chat/ws"
INTAKE_URL = f"{API_BASE}/api/people/intake"
PING_URL = f"{API_BASE}/api/ping"

REPO_ROOT = Path("/mnt/c/Users/chris/hornelore")
API_LOG = REPO_ROOT / ".runtime" / "logs" / "api.log"
REPORTS_DIR = REPO_ROOT / "docs" / "reports"


# ── Jake Max Miller intake payload ─────────────────────────────────────────
#
# Mirrors the Phase 2B orchestrator's NarratorIntakePayload schema. The
# fields are the same shape the intake form FE sends.

JAKE_INTAKE_PAYLOAD: Dict[str, Any] = {
    "full_legal_name": "Jake Max Miller",
    "preferred_name": "Jake",
    "date_of_birth": "1939-12-24",
    "place_of_birth": "Stanley, North Dakota",
    "pronouns": "he_him",
    "pronouns_other": "",
    "current_residence": "Bismarck, North Dakota",
    "consent_recording_agreement": True,
    "consent_disclosure_reviewed": True,
    "consent_checked_by_operator": "harness:jake_long_narration",
    "testing_only": False,
    "family_of_origin": {
        "father_name": "Ervin Horne",
        "father_birth_date": "1910-01-01",
        "mother_name": "Leila Myrtle",
        "mother_maiden_name": "Carkuff",
        "mother_birth_date": "1912-01-01",
        "siblings": [
            {"name": "Sharon", "birth_date": "1937-01-01", "birth_order": 1},
            {"name": "Linda", "birth_date": "1942-01-01", "birth_order": 3},
        ],
    },
    "marriage": {
        "marital_status": "married",
        "number_of_marriages": 1,
        "spouses": [
            {"name": "Janice", "year_married": 1959, "status": "current"},
        ],
    },
    "children": [
        {"name": "Vincent", "birth_date": "1960-01-01"},
        {"name": "Jason", "birth_date": "1961-01-01"},
        {"name": "Christopher", "birth_date": "1962-12-24"},
    ],
    "education_work": {
        "highest_education_level": "bachelors",
        "primary_career": "Photographer; later economics scholarship",
        "years_working": "1960s-2000s",
    },
    "military": {
        "served": True,
        "branch": "Army",
        "service_dates": "1959-1962",
        "rank": "Specialist",
        "units": "Nike-Hercules missile units",
        "locations": "Fort Ord, California; Germany; Landstuhl",
        "wars_conflicts": "Cold War",
        "decorations": "M1 expert qualification",
        "experience_notes": "Missile-system path; quiet Cold War service.",
    },
    "faith": {
        "religion_raised": "Roman Catholic",
        "current_faith": "Catholic",
        "ethnicity_heritage": "French (Alsace-Lorraine), German (Hanover); Catholic",
        "languages_at_home": "English",
    },
    "today": {
        "living_situation": "At home with spouse Janice and golden retriever Ivan",
        "health_considerations": "86 years old; otherwise no specific notes.",
    },
}


# ── Three chapters (verbatim from WO spec) ─────────────────────────────────

CHAPTER_1_EARLIEST_YEARS = """\
I was born on Christmas Eve, 1939, in Stanley, North Dakota. My father Ervin worked the land outside of town and my mother Leila — Leila Myrtle, Carkuff was her maiden name — kept the house and the garden and the canning and the kids. I had an older sister Sharon who was two when I came along, and three years later in 1942 our little sister Linda was born. So we were three: Sharon, me, Linda. The middle one. My father's people were Hornes who had come up to Ross, North Dakota in 1902 — my grandfather George Horne walked north from Ross looking for satisfactory land, filed his claim, and received title in June 1904. He died in 1914 when my father was only four years old. So my father grew up without his father. Then my grandmother Elizabeth married a man named William Mc Raith in 1916, and William died two years later in 1918. So my father lost two fathers before he was nine years old. I think about that sometimes when I think about how he raised me. He was a quiet man. He did not tell stories the way some men do. He worked. He came in for breakfast and went out again. The kitchen always had the coal stove going in winter — that is one of my earliest real memories, the smell of coal and the smell of bread baking and the sound of the wind coming across the prairie in those long Dakota winters. The wind in Stanley was not a sometimes thing. It was the air. I remember the train coming through Stanley too. You could hear it a long way off and then it would come right through the middle of town, and we would stop and watch it. My grandmother Elizabeth — the one who had been twice widowed — was still alive when I was little. She would come around with stories about her family. Her family was the Shong family, and she would tell us the name was originally Schong with a C, and they had dropped the C when they came to America. Her father John Michael Shong had come from Lorraine, France, near a city called Nancy, around 1848, and after he died in 1891 letters were still coming to him in French from his people back in France. She said her mother Christine was a Bolley from Hanover, Germany, and the Bolleys had come over in 1850 when Christine was eight. Catholic, both sides. When I was very small I did not know what any of that meant. I just knew that the old people came from someplace called France and someplace called Germany and that my grandmother kept a rosary. The war was on for most of those years. I do not remember the war the way an adult remembers a war — I was two when Pearl Harbor happened, six when it ended — but I remember rationing in the way a small child remembers things. Sugar was a thing my mother was careful with. Coffee was a thing the grown-ups talked about. My father was past the draft age and he was a farmer besides, so he was not called up. But the radio was always on for the news and the grown-ups would get quiet when it came on. I remember that. The radio meant be quiet.\
"""

CHAPTER_2_EARLY_SCHOOL_YEARS = """\
I started school in Stanley right around the end of the war. So my first-grade memory is mixed up with the memory of the war ending, which the grown-ups talked about more than the children did. My sister Sharon had already been in school for a couple of years by then so she had the routine down. I followed her. The schoolhouse in Stanley was a real building, brick and wood, not a one-room school the way the very early prairie schools had been, though my father had stories about going to one of those. The walk to school in winter was the test. North Dakota winter is not the kind of winter where you put on a coat and walk to the corner. It is the kind of winter where my mother would check our gloves and our scarves and our boots before we went out the door, and even then you could lose feeling in your face in five minutes if the wind was wrong. I remember her standing at the door with my muffler in her hands telling me to tuck it inside the coat, not on top of it. Tuck it in. Tuck it in. She said that every winter morning of my school years. The teachers in Stanley were strict in the way teachers were strict then, which meant you stood up when the teacher spoke to you, and you did your work, and you did not question why. Penmanship mattered. Arithmetic mattered. They were not telling us to express ourselves. They were telling us to do our work. Some of those teachers were the kind you remember the rest of your life because they cared. Some were the kind you remember because they did not. I had both. One of the women — I believe her name was Mrs. Pederson, but I would not swear to that — used to keep a small jar of lemon drops on her desk for the children who got their multiplication tables right the first time all the way through. That was the only candy I ever got at school and I worked for it. I do not remember whether I ever beat all of them, but I remember the lemon drops. The Catholic part of life was on Sunday and during Lent. My grandmother Elizabeth's people had been Catholic since France, and my father was raised Catholic, and so we went. Mass was in Latin then, the old way. I did not understand most of it but you learned to stand up and sit down and kneel at the right times. The hymns were the part that stayed with you. After Mass my grandmother would tell us things about her people — about her brother Charlie who ran a hotel in Penn, North Dakota, about her father John Michael who had served in the Civil War with the 28th Infantry from February 1865 to January 1866 in Kansas and Missouri, about how the family had ended up in Fall Creek, Wisconsin before some of them came west to North Dakota around 1902. I did not write any of that down when I was a child. Nobody told me to. I wish I had. By the time I was ten or eleven my father had me out with him doing real work — not just watching him work, which is what little boys do, but actually doing things. Carrying. Lifting. Holding what needed to be held while he worked. He did not give a lot of instructions because he expected you to watch and figure it out. He would say one thing once. If you missed it, he said it once more, and that was the second time, and there was not going to be a third time. So you learned to listen. I learned to listen on that farm before I ever learned to listen in the Army, and I think the Army part later was easier because of the farm part earlier.\
"""

CHAPTER_3_LATER_YEARS = """\
I am eighty-six now. Christmas Eve is coming around again in a few months, and that is a strange thing — to keep having birthdays and to keep noticing that the people who were there at your earlier ones are not all there anymore. My father Ervin died in 1967. My mother Leila held on until 1985. My sister Sharon is still here, ninety this year, married to Ed Woodmansee all this time. My younger sister Linda is still here too. So three of us made it this far, which considering the family pattern — my father lost his father at four — is something I do not take for granted. Janice and I have been married since 1959. We met in Bismarck, actually, at the dentist's office, of all places. She was working there and I was a young man with the wrong tooth situation, and that was that. October 10, 1959. I was nineteen, she was twenty. Sixty-six years married now and we still talk every day about something that matters. Our three sons all turned out. Vincent, the oldest, was born in Germany at Landstuhl. Jason came after that. And Christopher — Chris, our youngest — was born on Christmas Eve 1962 in Williston. Christmas Eve, the same as mine. That fact has always struck me as one of the small symmetries a life can hand you. He grew up to be the kind of son who built things you could not have predicted. He is the one who built this system I am talking to right now. I will not pretend I understand all of it. The dog right now is Ivan. He is a golden retriever and he is the most generous animal I have ever known. He follows Janice from room to room, and when she sits down he lies down at her feet, and when she gets up he gets up. He is not a young dog anymore. We are not young either. But the three of us are still a household, and that is what matters at the end. People ask me what I learned. I will tell you the honest answer. I learned that you have to pay attention to people while they are still here. My father did not tell stories. He worked. And I admired him for that when I was a boy because that is what a son does. But I wish I had asked him more. I wish I had asked him about his father George who died in 1914, and about his stepfather William who died in 1918, and about what it was like to grow up a boy who had buried two fathers before he was nine. I never asked him. He never volunteered. And then he was gone in 1967 and the chance was over. I would say to anyone listening — and I am aware this is being recorded — ask them while they are here. Even if they will not answer the first time, ask them again later. The answers are not always in the asking. Sometimes the answer is that they trusted you enough to be silent in front of you. But you can only learn that by asking. The other thing I would say is that I did not realize until I was old how much of my life was set by the train ride west to Fort Ord in 1959, and by choosing the missile-system path over the three-month wait for Army Security Agency. Those two decisions, made by a boy who did not know what he was choosing, ran the rest of my life. They took me to Germany. They put me where I met the work and the timing that produced Vincent. They eventually came home to North Dakota and the photography work and then the University of North Dakota and the economics degrees. None of that was planned at eighteen. All of it followed from being too impatient to wait three months. So when young people ask me about choices, I tell them that even the small ones become large. You will not know it at the time. You will not know it for years. But you find out later that the choice you thought was about three months was about everything.\
"""

BONUS_PROBE = "Anyway, that's about it for what I wanted to say today."


# Per-chapter expected anchors — used by the scorer to confirm Lori's
# response references at least one specific anchor from that chapter,
# not abstract "your childhood" / "your service" framing.
CHAPTER_ANCHORS: Dict[str, List[str]] = {
    "earliest_years": [
        "stanley", "ervin", "leila", "carkuff", "sharon", "linda",
        "christmas eve", "1939", "george horne", "elizabeth",
        "shong", "lorraine", "hanover", "bolley", "rosary",
        "the train", "coal stove", "the radio", "the wind",
    ],
    "early_school_years": [
        "stanley", "tuck it in", "lemon drops", "mrs. pederson",
        "multiplication", "penmanship", "catholic", "mass",
        "latin", "muffler", "sharon", "the farm", "carry", "lifting",
        "father said", "say one thing once", "schoolhouse",
        "john michael", "civil war", "28th infantry",
        "fall creek", "penn", "north dakota",
    ],
    "later_years": [
        "eighty-six", "janice", "1959", "dentist", "bismarck",
        "vincent", "jason", "christopher", "chris", "landstuhl",
        "germany", "ivan", "golden retriever", "fort ord",
        "missile", "army security agency", "photography",
        "university of north dakota", "economics",
        "sharon", "linda", "ed woodmansee", "1967", "1985",
        "ed", "woodmansee", "october 10",
    ],
    "bonus_probe": [
        # Bonus probe expects Lori to surface one banked thread —
        # any anchor from chapters 1-3 is acceptable here.
        "linda", "sharon", "vincent", "jason", "christopher",
        "chris", "janice", "ivan", "ervin", "leila", "elizabeth",
        "george", "william", "ed", "woodmansee",
    ],
}


# Forbidden-empathy openers that signal Lori is not grounding her
# reflection in the chapter content. Per WO spec LORI_REFLECTION_GROUNDING.
FORBIDDEN_OPENERS = [
    "thank you for sharing",
    "thanks for sharing",
    "that sounds difficult",
    "that sounds hard",
    "that must have been",
    "i can imagine",
    "i'm so sorry",
    "i am so sorry",
    "wow",
    "how wonderful",
    "how beautiful",
]

# Era-label menus — if Lori dumps these at the narrator, that's the
# May 11 Kent failure.
ERA_LABEL_MENU_PATTERNS = [
    "earliest years",
    "early school years",
    "adolescence",
    "coming of age",
    "building years",
    "later years",
    "today",
]


# ── HTTP helpers ───────────────────────────────────────────────────────────


def _http_post_json(url: str, body: Dict[str, Any], timeout: int = 30) -> Tuple[int, Any]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            payload = resp.read().decode("utf-8", errors="replace")
            try:
                return status, json.loads(payload)
            except json.JSONDecodeError:
                return status, payload
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, body
    except urllib.error.URLError as e:
        return -1, str(e)


def _http_get(url: str, timeout: int = 10) -> Tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return e.code, body
    except urllib.error.URLError as e:
        return -1, str(e)


def _wait_for_api(timeout_s: int = 60) -> bool:
    """Block until /api/ping returns 200 or timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status, _ = _http_get(PING_URL, timeout=3)
        if status == 200:
            return True
        time.sleep(2)
    return False


# ── Step 1: create Jake via the intake orchestrator ────────────────────────


def create_jake() -> Optional[str]:
    """POST /api/people/intake. Returns the new person_id or None on failure."""
    print("=" * 70)
    print("STEP 1 — Creating Jake Max Miller via POST /api/people/intake")
    print("=" * 70)
    print(f"  Endpoint: {INTAKE_URL}")
    print(f"  Payload sections:")
    for section in ["family_of_origin", "marriage", "children",
                    "education_work", "military", "faith", "today"]:
        block = JAKE_INTAKE_PAYLOAD.get(section)
        if block:
            print(f"    {section}: keys={list(block.keys()) if isinstance(block, dict) else type(block).__name__}")
    print()

    status, body = _http_post_json(INTAKE_URL, JAKE_INTAKE_PAYLOAD, timeout=30)
    if status != 200:
        print(f"  ✗ INTAKE FAILED — HTTP {status}")
        print(f"  Body: {json.dumps(body, indent=2) if isinstance(body, dict) else body}")
        return None

    if not isinstance(body, dict):
        print(f"  ✗ INTAKE returned non-dict body: {body}")
        return None

    pid = body.get("person_id") or (body.get("person") or {}).get("id")
    if not pid:
        print(f"  ✗ INTAKE returned no person_id in body: {json.dumps(body, indent=2)}")
        return None

    print(f"  ✓ Jake created — person_id={pid}")
    consent = body.get("consent_attestations") or []
    print(f"  ✓ consent_attestations written: {len(consent)}")
    print(f"  ✓ bio_facts_written: {body.get('bio_facts_written')}")
    if body.get("profile_json_error"):
        print(f"  ⚠ profile_json_error: {body['profile_json_error']}")
    print()
    return pid


# ── Step 2: WS chat helpers ────────────────────────────────────────────────


async def _send_turn_and_capture(
    ws,
    *,
    text: str,
    conv_id: str,
    person_id: str,
    runtime71_era: str,
    chapter_label: str,
    timeout_s: int = 240,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Send one narrator turn, stream tokens, return final_text + events."""

    params = {
        "person_id": person_id,
        "turn_mode": "interview",
        "session_style": "oral_history",
        "runtime71": {
            "current_pass": "pass2a",
            "current_era": runtime71_era,
            "current_mode": "open",
            "affect_state": "neutral",
            "affect_confidence": 0,
            "cognitive_mode": "open",
            "fatigue_score": 0,
            "paired": False,
            "assistant_role": "interviewer",
            "session_style_directive": "Listen long. Reflect with one specific anchor. Ask one short question at most.",
            "identity_complete": True,
            "identity_phase": "complete",
            "effective_pass": "pass2a",
            "speaker_name": "Jake",
            "person_id": person_id,
            "conversation_state": "answering",
            "cognitive_support_mode": False,
        },
        "max_new_tokens": 256,
        "turn_final": True,
    }

    print(f"  --- SENDING {chapter_label} ({len(text.split())} words) ---")
    send_start = time.time()
    await ws.send(json.dumps({
        "type": "start_turn",
        "session_id": conv_id,
        "conv_id": conv_id,
        "message": text,
        "turn_mode": "interview",
        "params": params,
    }, ensure_ascii=False))

    tokens = []
    events = []
    final_text = ""

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
        events.append(msg)
        typ = msg.get("type")
        if typ == "token":
            delta = msg.get("delta") or msg.get("text") or ""
            tokens.append(delta)
            print(delta, end="", flush=True)
        elif typ == "done":
            final_text = msg.get("final_text") or "".join(tokens)
            elapsed = time.time() - send_start
            print(f"\n  --- {chapter_label} DONE in {elapsed:.1f}s ---")
            return final_text, events
        elif typ == "error":
            print(f"\n  ✗ ERROR EVENT on {chapter_label}: {json.dumps(msg)[:400]}")
            return "", events

    raise TimeoutError(f"No done event for {chapter_label} after {timeout_s}s")


# ── Step 3: scorer ─────────────────────────────────────────────────────────


def score_chapter(
    label: str,
    chapter_key: str,
    response_text: str,
    *,
    word_budget: int = 110,
    is_bonus: bool = False,
) -> Dict[str, Any]:
    """8-row checklist scorer per WO spec."""
    text = (response_text or "").strip()
    lower = text.lower()
    words = text.split()
    word_count = len(words)
    question_count = text.count("?")

    # 1. Reflection grounded — references at least one chapter anchor
    anchors = CHAPTER_ANCHORS.get(chapter_key, [])
    anchor_hits = [a for a in anchors if a.lower() in lower]
    reflection_grounded = "PASS" if anchor_hits else "FAIL"

    # 2. One question max
    if question_count <= 1:
        one_question_max = "PASS"
    elif question_count == 2:
        one_question_max = "PARTIAL"
    else:
        one_question_max = "FAIL"

    # 3. No questionnaire interrogation — flag if multiple fact-asking
    #    patterns appear together
    interrogation_patterns = [
        r"\bwhat was your\b", r"\bwhen exactly\b",
        r"\bwhat year\b", r"\bwhat is your\b",
        r"\bmaiden name\b", r"\bbirth order\b",
    ]
    interrogation_hits = sum(
        1 for p in interrogation_patterns if re.search(p, lower)
    )
    if interrogation_hits >= 2:
        no_questionnaire = "FAIL"
    elif interrogation_hits == 1:
        no_questionnaire = "PARTIAL"
    else:
        no_questionnaire = "PASS"

    # 4. No forbidden empathy openers
    forbidden_hits = [op for op in FORBIDDEN_OPENERS if lower.startswith(op) or f". {op}" in lower]
    no_forbidden_empathy = "FAIL" if forbidden_hits else "PASS"

    # 5. No era-label menu
    era_menu_hits = [
        p for p in ERA_LABEL_MENU_PATTERNS
        # Only flag when surfaced as a menu — "early school years" appearing
        # naturally in a question is fine; multiple labels in one sentence
        # is the failure pattern.
        if p in lower
    ]
    era_label_count = len(era_menu_hits)
    if era_label_count >= 2:
        no_era_label_menu = "FAIL"
    elif era_label_count == 1:
        # Single label is fine if it matches the current chapter's era.
        no_era_label_menu = "PASS"
    else:
        no_era_label_menu = "PASS"

    # 6. No same-anchor loop — meta-check, populated by the caller looking
    #    across all chapters. Set to PASS here; cross-chapter pass tracked
    #    in the caller.
    no_same_anchor_loop = "PENDING"

    # 7. Word budget honored
    if word_count <= word_budget:
        word_budget_honored = "PASS"
    elif word_count <= word_budget + 20:
        word_budget_honored = "PARTIAL"
    else:
        word_budget_honored = "FAIL"

    # 8. Translation/refusal absent
    refusal_patterns = [
        "let me say that in english", "i cannot answer", "i can't answer",
        "i'm not able to", "i am not able to",
    ]
    refusal_hit = any(p in lower for p in refusal_patterns)
    if not text or refusal_hit:
        translation_refusal_absent = "FAIL"
    else:
        translation_refusal_absent = "PASS"

    return {
        "label": label,
        "chapter_key": chapter_key,
        "word_count": word_count,
        "question_count": question_count,
        "anchor_hits": anchor_hits,
        "rows": {
            "reflection_grounded": reflection_grounded,
            "one_question_max": one_question_max,
            "no_questionnaire_interrogation": no_questionnaire,
            "no_forbidden_empathy_openers": no_forbidden_empathy,
            "no_era_label_menu": no_era_label_menu,
            "no_same_anchor_loop": no_same_anchor_loop,
            "word_budget_honored": word_budget_honored,
            "translation_refusal_absent": translation_refusal_absent,
        },
        "forbidden_openers_hit": forbidden_hits,
        "interrogation_hits": interrogation_hits,
        "era_label_hits": era_menu_hits,
        "is_bonus": is_bonus,
    }


def cross_chapter_anchor_loop_check(scores: List[Dict[str, Any]]) -> None:
    """Detect when the same anchor (e.g. 'meal tickets' / 'ivan' / 'the train')
    appears in Lori's response across multiple chapters. Mutates the scores
    list in place to set the no_same_anchor_loop row."""
    # Pair each chapter's anchor_hits with neighbors
    for i, s in enumerate(scores):
        if s["is_bonus"]:
            s["rows"]["no_same_anchor_loop"] = "PASS"
            continue
        loop_hits = []
        for j, other in enumerate(scores):
            if i == j or other["is_bonus"]:
                continue
            shared = set(s["anchor_hits"]) & set(other["anchor_hits"])
            if shared:
                loop_hits.extend(shared)
        if loop_hits:
            s["rows"]["no_same_anchor_loop"] = "FAIL"
            s["repeated_anchors"] = sorted(set(loop_hits))
        else:
            s["rows"]["no_same_anchor_loop"] = "PASS"


# ── Step 4: api.log greps ──────────────────────────────────────────────────


def log_grep_summary() -> Dict[str, Any]:
    """Mimic the WO spec's BACKEND SANITY GREP block."""
    if not API_LOG.exists():
        return {"error": f"api.log not found at {API_LOG}"}
    try:
        text = API_LOG.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"error": f"Cannot read api.log: {e}"}

    oral_history_count = len(re.findall(
        r"composer.*style[= ]oral_history", text, flags=re.IGNORECASE,
    ))
    reflection_not_grounded = len(re.findall(
        r"reflection_not_grounded|question_layer_ineligible", text,
    ))
    accepted_count = len(re.findall(
        r"extract.*accepted=", text,
    ))
    meal_tickets_in_log = "meal tickets" in text.lower()
    spantag_flag_on = "[extract][spantag] flag ON" in text

    return {
        "oral_history_style_lines": oral_history_count,
        "reflection_not_grounded_or_layer_ineligible_lines": reflection_not_grounded,
        "extract_accepted_lines": accepted_count,
        "meal_tickets_substring_present": meal_tickets_in_log,
        "spantag_flag_on_lines_observed": spantag_flag_on,
    }


# ── Step 5: report writer ─────────────────────────────────────────────────


def write_report(
    conv_id: str,
    person_id: str,
    intake_response_summary: Dict[str, Any],
    chapter_results: List[Tuple[str, str, str, Dict[str, Any]]],
    log_summary: Dict[str, Any],
) -> Path:
    """Writes a comprehensive report to docs/reports/."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"jake_long_narration_{conv_id}.txt"

    lines: List[str] = []
    lines.append("=" * 80)
    lines.append("JAKE MAX MILLER LONG-NARRATION HARNESS REPORT")
    lines.append("=" * 80)
    lines.append(f"conv_id:    {conv_id}")
    lines.append(f"person_id:  {person_id}")
    lines.append(f"run_time:   {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("Stack signature: oral_history default + Phase 1 validators +")
    lines.append("                 reflection-grounding + thread bank +")
    lines.append("                 LORI-CONFIRM scaffolding (post-WO sequence)")
    lines.append("")

    lines.append("─" * 80)
    lines.append("STEP 1 — Intake orchestrator result")
    lines.append("─" * 80)
    for k, v in intake_response_summary.items():
        lines.append(f"  {k}: {v}")
    lines.append("")

    overall_pass = 0
    overall_total = 0
    for chapter_label, chapter_key, response_text, score in chapter_results:
        lines.append("─" * 80)
        lines.append(f"CHAPTER — {chapter_label}")
        lines.append("─" * 80)
        lines.append("")
        lines.append(f"  word_count:    {score['word_count']}")
        lines.append(f"  question_count: {score['question_count']}")
        lines.append(f"  anchor_hits:   {', '.join(score['anchor_hits']) or '(none)'}")
        lines.append("")
        lines.append("  Lori response (verbatim):")
        lines.append("  ┌" + "─" * 76)
        for ln in (response_text or "(no response)").splitlines() or [(response_text or "")]:
            lines.append(f"  │ {ln}")
        lines.append("  └" + "─" * 76)
        lines.append("")
        lines.append("  Scoring matrix:")
        for row_name, row_val in score["rows"].items():
            mark = "✓" if row_val == "PASS" else ("⚠" if row_val == "PARTIAL" else "✗" if row_val == "FAIL" else "·")
            lines.append(f"    {mark} {row_name}: {row_val}")
        if score.get("repeated_anchors"):
            lines.append(f"    repeated_anchors: {', '.join(score['repeated_anchors'])}")
        # Count for the overall
        for row_val in score["rows"].values():
            if row_val == "PASS":
                overall_pass += 1
                overall_total += 1
            elif row_val in ("FAIL", "PARTIAL"):
                overall_total += 1
        lines.append("")

    lines.append("─" * 80)
    lines.append("LOG SANITY GREP SUMMARY")
    lines.append("─" * 80)
    for k, v in log_summary.items():
        lines.append(f"  {k}: {v}")
    lines.append("")

    lines.append("─" * 80)
    lines.append("AGGREGATE")
    lines.append("─" * 80)
    pct = (100.0 * overall_pass / overall_total) if overall_total else 0.0
    lines.append(f"  Score rows passed: {overall_pass} / {overall_total}  ({pct:.1f}%)")
    lines.append("")
    lines.append("  Acceptance criteria:")
    lines.append("    GREEN:  ≥ 75% rows pass AND zero hard FAILs on forbidden-empathy / era-label-menu")
    lines.append("    AMBER:  60-75% rows pass OR partial failures on word budget / one-question-max")
    lines.append("    RED:    < 60% rows pass OR hard FAILs on forbidden-empathy or era-label-menu")
    lines.append("")
    lines.append("Report file: " + str(report_path))
    lines.append("=" * 80)

    out = "\n".join(lines)
    report_path.write_text(out, encoding="utf-8")
    print()
    print(out)
    return report_path


# ── Main ─────────────────────────────────────────────────────────────────


async def run_harness() -> int:
    print()
    print("=" * 70)
    print("JAKE MAX MILLER LONG-NARRATION HARNESS — task #77")
    print("=" * 70)
    print()
    print("Stack ping check ...")
    if not _wait_for_api(timeout_s=60):
        print(f"✗ API at {PING_URL} not responding. Is the stack up?")
        return 2
    print("  ✓ API is up.")
    print()

    # Step 1 — create Jake
    person_id = create_jake()
    if not person_id:
        print("Aborting — cannot create Jake.")
        return 3

    intake_summary = {
        "person_id": person_id,
        "intake_endpoint": INTAKE_URL,
        "intake_payload_sections": 7,
        "intake_status": "200",
    }

    # Step 2 — WS conversation
    conv_id = f"jake_long_narration_{uuid.uuid4().hex[:12]}"
    print()
    print("=" * 70)
    print(f"STEP 2 — Opening chat WS — conv_id={conv_id}")
    print("=" * 70)
    print(f"  WS:        {WS_URL}")
    print(f"  person_id: {person_id}")
    print(f"  style:     oral_history")
    print()

    chapter_specs = [
        ("CHAPTER 1 — EARLIEST YEARS", "earliest_years", CHAPTER_1_EARLIEST_YEARS, "earliest_years"),
        ("CHAPTER 2 — EARLY SCHOOL YEARS", "early_school_years", CHAPTER_2_EARLY_SCHOOL_YEARS, "early_school_years"),
        ("CHAPTER 3 — LATER YEARS", "later_years", CHAPTER_3_LATER_YEARS, "later_years"),
        ("BONUS PROBE — closing marker", "bonus_probe", BONUS_PROBE, "today"),
    ]

    chapter_results: List[Tuple[str, str, str, Dict[str, Any]]] = []
    scores_only: List[Dict[str, Any]] = []

    try:
        async with websockets.connect(
            WS_URL, ping_interval=None, max_size=20_000_000,
        ) as ws:
            # sync_session
            await ws.send(json.dumps({
                "type": "sync_session",
                "session_id": conv_id,
                "person_id": person_id,
            }))
            # Drain ~2s of initial status
            t0 = time.time()
            while time.time() - t0 < 2:
                try:
                    await asyncio.wait_for(ws.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    break

            for chapter_label, chapter_key, chapter_text, runtime71_era in chapter_specs:
                print()
                print("=" * 70)
                print(f"  {chapter_label}")
                print("=" * 70)
                final_text, events = await _send_turn_and_capture(
                    ws,
                    text=chapter_text.strip(),
                    conv_id=conv_id,
                    person_id=person_id,
                    runtime71_era=runtime71_era,
                    chapter_label=chapter_label,
                    timeout_s=300,
                )
                is_bonus = (chapter_key == "bonus_probe")
                word_budget = 30 if is_bonus else 110
                score = score_chapter(
                    chapter_label,
                    chapter_key,
                    final_text,
                    word_budget=word_budget,
                    is_bonus=is_bonus,
                )
                chapter_results.append((chapter_label, chapter_key, final_text, score))
                scores_only.append(score)

    except Exception as exc:
        print(f"\n✗ WS failure: {exc}")
        if not chapter_results:
            return 4

    # Cross-chapter anchor-loop pass
    cross_chapter_anchor_loop_check(scores_only)

    # Log summary
    log_summary = log_grep_summary()

    # Report
    report_path = write_report(
        conv_id=conv_id,
        person_id=person_id,
        intake_response_summary=intake_summary,
        chapter_results=chapter_results,
        log_summary=log_summary,
    )
    print(f"\n✓ Report written: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_harness()))
