"""HARNESS-KENT-DEEP-WITNESS-02 — try-to-break-Lori harness.

Per Chris + ChatGPT 2026-05-10: Lori must be tested on dense, messy,
long oral-history prose. The bar is interviewer competence, NOT word-
matching.

PASS criteria per test:
  - 9+ score on 12-point rubric
  - 0 hard-fail tokens (sensory/feelings/camaraderie/first-person mimicry)
  - Response 35-110 words (stub <35 = receipt failure)
  - Exactly 1 question
  - One GOOD question-intent class, zero BAD intents

This harness is SUPPOSED TO FAIL on the current Lori for most tests.
That failure is the morning's roadmap for the LLM-witness-receipt
architecture (deterministic detect → LLM compose with strict
directive → response-guards validate → fall back to multi-anchor on
drift).

Usage:
    cd /mnt/c/Users/chris/hornelore
    python3 scripts/replay_kent_deep_witness.py

Output:
    docs/reports/kent_deep_witness_<ts>.md  — verdict per test + summary
    docs/reports/kent_deep_witness_<ts>.jsonl
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
from typing import Any, Dict, List, Optional, Tuple

try:
    import websockets
except ImportError:
    print("ERROR: websockets not installed. pip install websockets")
    sys.exit(1)


KENT_PERSON_ID = "4aa0cc2b-1f27-433a-9152-203bb1f69a55"
WS_URL = os.environ.get("LV_WS_URL", "ws://localhost:8000/api/chat/ws")
CONV_ID = f"deep_kent_{uuid.uuid4().hex[:12]}"

REPORT_DIR = Path(__file__).resolve().parent.parent / "docs" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
TS = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
REPORT_MD = REPORT_DIR / f"kent_deep_witness_{TS}.md"
REPORT_JSONL = REPORT_DIR / f"kent_deep_witness_{TS}.jsonl"


# ── Hard-fail tokens (case-insensitive substring match) ───────────────────

FORBIDDEN_TOKENS = [
    "scenery", "sights", "sounds", "smells", "sensory",
    "how did that feel", "how did you feel", "what did that feel like",
    " emotion", " emotional",
    "camaraderie", "teamwork", "culture among your fellow soldiers",
    "sense of duty", "must have been", "pivotal", "resilience",
]
FIRST_PERSON_MIMICRY = [
    " our son", " my son", " my wife",
    "we were in germany", "we were in kaiserslautern",
    "we took care", "we got married",
    " i was assigned", " i went to germany", " i contacted janice",
]


# ── Question-intent classifier ────────────────────────────────────────────

GOOD_INTENT_KEYWORDS = {
    "communication_with_wife": [
        "communicate", "letters", "phone", "phone call",
        "talk to janice", "contact janice", "reach janice",
        "how did you and janice talk",
    ],
    "wife_travel_logistics": [
        "how did janice travel", "how did she come",
        "join you in germany", "she travel to germany",
        "her travel", "she got to germany",
    ],
    "return_to_usa_for_wedding": [
        "how did you get back", "return to bismarck", "travel home",
        "come home for the wedding", "leave to come back",
    ],
    "army_paperwork": [
        "paperwork", "permission", "orders", "army rules",
        "dependent", "dependents", "permission for janice",
    ],
    "housing_in_germany": [
        "where did you live", "housing", "first home", "quarters",
        "where did you and janice live",
    ],
    "off_duty_life": [
        "personal time", "off duty", "when you were not working",
        "off-duty", "when you were off",
    ],
    "role_transition": [
        "from missile", "into photography", "courier", "brigade photography",
        "moved into photography", "from radar", "into the photographer",
    ],
    "proper_noun_confirmation": [
        "did i get", " spell ", "spell that", "spelling",
        "record correctly", "record that", "heard that right",
        "name right", "did i hear",
    ],
    "rank_or_role": [
        "rank", "private", "promoted", "day-to-day", "day to day",
        "what changed", "change for you",
    ],
    "factual_continuation": [
        "what happened when basic training", "what came after",
        "what happened after",
    ],
}

BAD_INTENT_KEYWORDS = {
    "sensory": ["sights", "sounds", "smells", "scenery"],
    "feelings": [
        "how did you feel", "what did that feel like",
        "how did that feel", "emotion", "emotional",
        "must have felt",
    ],
    "camaraderie": [
        "camaraderie", "teamwork", "culture among", "sense of duty",
    ],
    "generic": [
        "what was it like", "tell me more about that time",
        "must have been",
    ],
}


def classify_question_intents(text: str) -> Tuple[List[str], List[str]]:
    """Return (good_intents, bad_intents) lists found in the response."""
    t = text.lower()
    good = []
    bad = []
    for intent, keywords in GOOD_INTENT_KEYWORDS.items():
        if any(k in t for k in keywords):
            good.append(intent)
    for intent, keywords in BAD_INTENT_KEYWORDS.items():
        if any(k in t for k in keywords):
            bad.append(intent)
    return good, bad


def find_forbidden(text: str) -> List[str]:
    t = text.lower()
    hits = [tok for tok in FORBIDDEN_TOKENS if tok.strip() in t]
    return hits


def find_first_person_mimicry(text: str) -> List[str]:
    t = text.lower()
    hits = [tok for tok in FIRST_PERSON_MIMICRY if tok.strip() in t]
    return hits


# ── Test pack — Chris/ChatGPT-specified deep tests ────────────────────────

# Each test: required_facts, scoring_weights, expected_question_intent
TESTS: List[Dict[str, Any]] = [
    {
        "label": "TEST-A floor-control: claimed-floor mode",
        "kind": "claimed_floor",
        "narrator_text": (
            "[SYSTEM: The narrator has pressed and held the floor. He is "
            "still talking and has not submitted the story. Do not ask a "
            "question. Do not summarize. Say one brief presence statement "
            "only.]"
        ),
        "expected_max_words": 12,
        "expected_no_question": True,
        "fact_buckets": [],
        "min_facts": 0,
        "good_intent_required": False,
    },
    {
        "label": "TEST-B induction chapter (dense prose)",
        "kind": "long_factual",
        "narrator_text": (
            "I'll start at the beginning of the Army part because it was "
            "more complicated than just \"I enlisted.\" My dad took me down "
            "to the railroad depot in Stanley before daylight, and I "
            "remember it mostly as a business trip, not some emotional "
            "farewell. He was making sure I got on the right train. I had "
            "paperwork with me for the induction process, and the trip was "
            "Stanley to Fargo. In Fargo they ran us through the physical "
            "exam, the mental exam, and the testing to see whether we "
            "qualified. I did well enough on the tests that the Army "
            "treated it almost like a reward and a penalty at the same "
            "time. They put me in charge of the meal tickets for a "
            "trainload of recruits going west. That meant I had to account "
            "for the meals, deal with the conductor and the dining car "
            "people, and make sure the recruits got fed on the way to "
            "California. The funny part is that I was not trying to "
            "become a leader on that train. I was just trying to do the "
            "job they handed me. But when the meals were sloppy, "
            "especially the oatmeal, I pushed back and refused one of the "
            "payments until they improved it. The conductor was not happy "
            "with me, and there were threats back and forth, but "
            "eventually they gave us better meals. So before I even got "
            "to basic training I had already been tested, scored high, "
            "assigned responsibility, and had to argue with railroad "
            "people over the quality of food for a train full of recruits. "
            "Then we arrived out west and ended up at Fort Ord, "
            "California, where the ordinary Army part began."
        ),
        "fact_buckets": [
            ["father", "dad"],
            ["stanley"],
            ["depot", "railroad"],
            ["fargo"],
            ["induction", "physical exam", "mental exam"],
            ["high score", "scored high", "did well"],
            ["meal ticket"],
            ["trainload", "train load", "train full of recruits"],
            ["conductor", "dining car"],
            ["oatmeal", "meals"],
            ["fort ord"],
        ],
        "min_facts": 5,
        "good_intent_required": True,
        "expected_min_words": 35,
        "expected_max_words": 110,
    },
    {
        "label": "TEST-C Fort Ord / skills / Nike choice point",
        "kind": "long_factual",
        "narrator_text": (
            "At Fort Ord we went through the usual eight weeks of basic "
            "training, and I was not thinking of it as a story at the "
            "time. It was just the Army taking a bunch of young men and "
            "processing us through the system. We drilled, took tests, "
            "qualified on weapons, and got sorted out for what would "
            "happen next. I was sent out for extra testing because they "
            "wanted to see whether I could qualify for high school GED "
            "work, and I did well enough there too. On the rifle range I "
            "qualified expert with the M1 rifle. That mattered because "
            "it was one more sign that I could handle technical work. At "
            "the end of basic training they called us in one by one and "
            "talked about where we were going. I had enlisted hoping for "
            "Army Security Agency work. They told me that if I wanted "
            "that path I would have to go home and wait three months for "
            "an opening, and I did not want to sit around for three "
            "months. So I asked what else was available. One option was "
            "Nike Ajax and Nike Hercules guided missile system work — "
            "radar operator and computer operator. That sounded more "
            "immediate and more technical, so I chose it, and they "
            "accepted me for that path."
        ),
        "fact_buckets": [
            ["fort ord"],
            ["eight weeks", "8 weeks", "basic training"],
            ["ged", "extra testing"],
            ["m1 rifle", "expert"],
            ["called us in", "called in"],
            ["army security agency"],
            ["three months", "3 months", "wait"],
            ["nike ajax", "nike hercules"],
            ["radar operator", "computer operator"],
        ],
        "min_facts": 6,
        "good_intent_required": True,
        "expected_min_words": 35,
        "expected_max_words": 110,
    },
    {
        "label": "TEST-D Germany + Janice logistics",
        "kind": "long_factual",
        "narrator_text": (
            "After basic training and the Nike selection, I was sent for "
            "missile-system training. The first place I remember was "
            "around Detroit, Michigan, and the name in my head is "
            "something like Southridge Air Force Base, though I may not "
            "have that exactly right. The work was Nike Ajax and Nike "
            "Hercules radar and computer operator training. Some of it "
            "was slow because there was a lot of practice linking up "
            "radar signals and making detections, but it was the kind of "
            "technical work I had been selected for. After about a year "
            "I was notified that I was being sent to Germany to work in "
            "the same Nike systems. I had to go home first for required "
            "leave, and then I traveled to Germany. Once I got there, "
            "Germany impressed me right away. It was a wonderful place, "
            "and after I had been there less than a year I contacted my "
            "fiancée Janice. I told her that if we were going to get "
            "married, we should get married soon and live in Germany "
            "together instead of waiting. That meant I had to come home "
            "to Bismarck, get married, get the paperwork and travel "
            "arranged, and then bring Janice back into that Army life "
            "overseas."
        ),
        "fact_buckets": [
            ["detroit", "michigan"],
            ["southridge"],
            ["nike ajax", "nike hercules"],
            ["radar", "computer operator"],
            ["sent to germany", "germany"],
            ["required leave"],
            ["fiancée janice", "fiancee janice", "janice"],
            ["marry", "married"],
            ["live in germany"],
            ["bismarck"],
            ["paperwork"],
        ],
        "min_facts": 7,
        "good_intent_required": True,
        "expected_min_words": 35,
        "expected_max_words": 110,
    },
    {
        "label": "TEST-E wedding / Janice identity / married life",
        "kind": "long_factual",
        "narrator_text": (
            "When I came back to Bismarck, Janice's family had put "
            "together the wedding. It was at the Cathedral of the Holy "
            "Spirit, and Leonard Duffy performed the marriage ceremony. "
            "That mattered because this was not just a quick courthouse "
            "thing before I went back overseas. Her family had organized "
            "a real wedding, and then almost immediately we had to get "
            "ourselves ready to leave for Germany. There were clothes, "
            "papers, travel, Army rules, and the practical question of "
            "how a young married couple was going to live overseas on an "
            "Army assignment. Once we got back, we had to learn ordinary "
            "married life in Germany around my duty schedule."
        ),
        "fact_buckets": [
            ["bismarck"],
            ["janice", "her family"],
            ["cathedral of the holy spirit"],
            ["leonard duffy"],
            ["not courthouse", "real wedding"],
            ["return overseas", "back to germany", "leave for germany"],
            ["papers", "travel", "army rules"],
            ["young married couple", "married couple"],
            ["married life"],
            ["duty schedule"],
        ],
        "min_facts": 6,
        "good_intent_required": True,
        "expected_min_words": 35,
        "expected_max_words": 110,
    },
    {
        "label": "TEST-F Germany duty / CBR / courier / photographer",
        "kind": "long_factual",
        "narrator_text": (
            "In Germany I was first assigned to a Nike Ajax and Nike "
            "Hercules missile site. I wish I had the city name clear, "
            "but the way it comes back to me is mixed up with a "
            "Salamander shoe factory and other landmarks around the "
            "place. From there I was sent up into the mountains for "
            "chemical, biological, and radiological training. That was "
            "another specialized training piece, separate from the "
            "missile work. Later I was asked to replace Johnny Johnson "
            "as the document courier because he was going home on leave. "
            "I got about one day of training on the route and then "
            "started doing the courier run. That courier job turned out "
            "to matter because one day I stopped at the 32nd Artillery "
            "Brigade office in Kaiserslautern. I asked whether they had "
            "any openings for photographers. The officer said yes, and "
            "I could move in and start doing that work. So the courier "
            "route became the bridge from missile-site work into being "
            "a photographer for the 32nd Brigade."
        ),
        "fact_buckets": [
            ["nike ajax", "nike hercules", "missile site"],
            ["salamander"],
            ["chemical", "biological", "radiological"],
            ["mountains"],
            ["johnny johnson"],
            ["document courier", "courier"],
            ["one day of training", "one day"],
            ["32nd artillery brigade", "32nd brigade"],
            ["kaiserslautern"],
            ["photographer", "photography"],
        ],
        "min_facts": 8,
        "good_intent_required": True,
        "expected_min_words": 35,
        "expected_max_words": 110,
    },
    {
        "label": "TEST-G General Schmick + Vince + fragile names",
        "kind": "long_factual",
        "narrator_text": (
            "The general I worked for was General Peter Schmick, a "
            "Canadian-born general officer in the American Army. After "
            "I moved into the photography work, Janice and I were "
            "living up around Kaiserslautern. Our oldest son Vince was "
            "born while we were there. The hospital name is important, "
            "and I want it right. It was not Lansdale Army Hospital. "
            "It was Landstuhl Air Force Hospital, connected with "
            "Ramstein Air Force Base. We had to handle birth "
            "registration and citizenship paperwork, and I think we "
            "dealt with the embassy or attaché office in Frankfurt. "
            "Vince ended up American, though at the time there was "
            "some question about nationality or dual nationality "
            "because he was born there."
        ),
        "fact_buckets": [
            ["general peter schmick", "schmick"],
            ["canadian-born", "canadian born"],
            ["american army"],
            ["photography", "photographer"],
            ["janice"],
            ["kaiserslautern"],
            ["oldest son vince", "son vince", "vince"],
            ["not lansdale"],
            ["landstuhl"],
            ["ramstein"],
            ["birth registration"],
            ["citizenship"],
            ["embassy", "attaché", "attache"],
            ["frankfurt"],
            ["american", "dual nationality"],
        ],
        "min_facts": 10,
        "good_intent_required": True,  # spelling confirmation expected
        "expected_min_words": 35,
        "expected_max_words": 110,
    },
    {
        "label": "TEST-H correction-perspective repair (you are talking like you are me)",
        "kind": "correction",
        "narrator_text": (
            "You are talking like you are me. Don't say \"our son\" or "
            "\"we were in Germany.\" I'm the one telling the story."
        ),
        "fact_buckets": [],
        "min_facts": 0,
        "good_intent_required": False,
        "expected_min_words": 8,
        "expected_max_words": 60,
    },
    {
        "label": "TEST-COMMS-1959 communication-with-fiancée-from-overseas",
        "kind": "long_factual",
        "narrator_text": (
            "I had been in Germany less than a year when I contacted my "
            "fiancée Janice and told her that if we were going to get "
            "married, we should do it and live in Germany. This was "
            "1959, so it was not like today where you just text "
            "someone. I had to make plans from overseas, get back to "
            "Bismarck, get married, and then arrange for her to come "
            "back with me."
        ),
        "fact_buckets": [
            ["germany"],
            ["janice", "fiancée", "fiancee"],
            ["1959"],
            ["overseas"],
            ["bismarck"],
            ["arrange", "back with me"],
        ],
        "min_facts": 4,
        "good_intent_required": True,
        # The KEY required intent for this test: communication_with_wife
        "required_good_intent": "communication_with_wife",
        "expected_min_words": 35,
        "expected_max_words": 110,
    },
    {
        "label": "TEST-COMBINED killer combined turn",
        "kind": "long_factual",
        "narrator_text": (
            "Let me tell it in order because one thing led to the next. "
            "My dad got me to the railroad depot in Stanley before I "
            "left for the Army. From Stanley I went by train to Fargo "
            "for the induction process. In Fargo they put us through "
            "the physical exam, the mental exam, and the tests to see "
            "whether we qualified. I scored high enough that the Army "
            "put me in charge of the meal tickets for a trainload of "
            "recruits going west. That was not something I had asked "
            "for, but it meant I was responsible for accounting for "
            "meals and dealing with railroad people before I had even "
            "reached basic training. On the train west, the food was "
            "not very good. I remember the oatmeal being sloppy, and I "
            "finally resisted one of the payments because I thought the "
            "recruits should be getting better meals. The conductor did "
            "not like that. There were some threats and back-and-forth, "
            "but eventually they improved the meals. So that was my "
            "first Army responsibility, before Fort Ord. Then at Fort "
            "Ord, California, we went through eight weeks of basic "
            "training. I was sent for extra testing connected to high "
            "school GED qualification, and I scored expert on the M1 "
            "rifle. At the end of basic, they called us in to decide "
            "where we were going next. I had originally enlisted hoping "
            "for Army Security Agency work, but they told me I would "
            "have to go home and wait three months for an opening. I "
            "did not want to sit around for three months, so I asked "
            "what else was available. One of the options was Nike Ajax "
            "and Nike Hercules guided missile system work, as a radar "
            "operator and computer operator. I selected that and got "
            "picked for it. Later I trained around Detroit, Michigan, "
            "at a base name I may not be saying right — something like "
            "Southridge Air Force Base — and the training was mostly "
            "radar signal work and detection practice. After about a "
            "year I was sent to Germany for the same Nike missile "
            "systems. I went home first on required leave, then "
            "traveled to Germany. Germany was a wonderful place, and "
            "after I had been there less than a year I contacted my "
            "fiancée Janice. I told her that if we were going to get "
            "married, we should get married and live in Germany. I "
            "came home to Bismarck, and Janice's family arranged a "
            "real wedding at the Cathedral of the Holy Spirit. Leonard "
            "Duffy performed the ceremony. Then Janice and I had to "
            "organize clothes, papers, travel, Army rules, and get "
            "ourselves back to Germany as a young married couple. In "
            "Germany I was first assigned to a Nike Ajax and Nike "
            "Hercules missile site. I wish I could remember the city "
            "name clearly; I remember something about a Salamander "
            "shoe factory near it. I was sent up into the mountains "
            "for chemical, biological, and radiological training. "
            "Later I replaced Johnny Johnson as a document courier "
            "while he was going home on leave. The courier route took "
            "me to the 32nd Artillery Brigade office in Kaiserslautern, "
            "and I asked whether they had openings for photographers. "
            "They did, so I moved into photography work for the "
            "Brigade. The general was General Peter Schmick, a "
            "Canadian-born general officer in the American Army. While "
            "Janice and I were in Kaiserslautern, our oldest son Vince "
            "was born. The hospital detail matters: not Lansdale Army "
            "Hospital, but Landstuhl Air Force Hospital at Ramstein "
            "Air Force Base. We had to handle birth registration and "
            "citizenship paperwork, maybe through the embassy or "
            "attaché office in Frankfurt, and Vince ended up American "
            "even though there was some question about dual nationality "
            "because he was born in Germany."
        ),
        "fact_buckets": [
            ["stanley"], ["fargo"], ["induction"], ["meal ticket"],
            ["fort ord"], ["m1 rifle", "expert"],
            ["army security agency"], ["nike ajax"], ["nike hercules"],
            ["germany"], ["janice"], ["bismarck"],
            ["cathedral of the holy spirit"],
            ["32nd artillery brigade", "32nd brigade"],
            ["general peter schmick", "schmick"],
            ["vince"], ["landstuhl"], ["ramstein"], ["frankfurt"],
        ],
        "min_facts": 8,  # 8 of 19 = ~42%
        "good_intent_required": True,
        "expected_min_words": 55,
        "expected_max_words": 120,
    },
]


# ── Scoring ───────────────────────────────────────────────────────────────


def count_facts(text: str, fact_buckets: List[List[str]]) -> int:
    """Count fact buckets matched (any keyword in the bucket counts)."""
    t = text.lower()
    matched = 0
    for bucket in fact_buckets:
        if any(kw.lower() in t for kw in bucket):
            matched += 1
    return matched


def score_response(test: Dict[str, Any], response_text: str) -> Dict[str, Any]:
    """Apply the 12-point rubric + hard-fail rules. Return verdict dict."""
    text = response_text or ""
    text_lower = text.lower()
    word_count = len(text.split())

    # Hard-fail checks
    forbidden = find_forbidden(text)
    mimicry = find_first_person_mimicry(text)
    q_count = text.count("?")

    # Length check (skip for claimed-floor)
    expected_min = test.get("expected_min_words", 0)
    expected_max = test.get("expected_max_words", 999)

    hard_fails = []
    if forbidden:
        hard_fails.append(f"forbidden_token:{forbidden[0]}")
    if mimicry:
        hard_fails.append(f"first_person_mimicry:{mimicry[0]}")
    if test.get("expected_no_question") and q_count > 0:
        hard_fails.append("question_in_claimed_floor")
    if q_count > 1:
        hard_fails.append(f"too_many_questions:{q_count}")
    if word_count < expected_min:
        hard_fails.append(f"too_short:{word_count}<{expected_min}")
    if word_count > expected_max:
        hard_fails.append(f"too_long:{word_count}>{expected_max}")

    # Intent classification
    good_intents, bad_intents = classify_question_intents(text)

    # 12-point rubric
    score = 0
    score_notes = []

    # Reflects multiple facts (chronology, not just nouns)
    fact_buckets = test.get("fact_buckets", [])
    min_facts = test.get("min_facts", 0)
    facts_matched = count_facts(text, fact_buckets) if fact_buckets else 0
    if min_facts > 0:
        if facts_matched >= min_facts:
            score += 2
            score_notes.append(f"facts:+2 ({facts_matched}/{len(fact_buckets)})")
        elif facts_matched >= min_facts // 2:
            score += 1
            score_notes.append(f"facts:+1 ({facts_matched}/{len(fact_buckets)})")
        else:
            score_notes.append(f"facts:+0 ({facts_matched}/{len(fact_buckets)})")

    # Reflects achievement / responsibility / role keywords
    achievement_keywords = [
        "score", "scored", "expert", "qualified", "selected", "chosen",
        "responsibility", "in charge", "promoted", "assigned",
    ]
    if any(kw in text_lower for kw in achievement_keywords):
        score += 2
        score_notes.append("achievement:+2")

    # Family/logistics thread
    family_keywords = [
        "janice", "wife", "fiancée", "fiancee", "married", "wedding",
        "vince", "son", "child", "leave", "travel", "paperwork",
        "permission", "communication", "communicate",
    ]
    if any(kw in text_lower for kw in family_keywords):
        score += 2
        score_notes.append("family:+2")

    # One useful next factual question (good intent + question mark)
    if good_intents and q_count >= 1:
        score += 2
        score_notes.append(f"good_question:+2 ({good_intents[0]})")

    # Spelling confirmation when fragile names appear
    fragile_names = [
        "schmick", "landstuhl", "ramstein", "kaiserslautern",
        "southridge", "salamander", "frankfurt",
    ]
    fragile_in_input = any(n in test.get("narrator_text", "").lower() for n in fragile_names)
    if fragile_in_input:
        if any(p in text_lower for p in
               ["did i get", "spell", "record correctly",
                "name right", "did i hear"]):
            score += 1
            score_notes.append("spelling:+1")

    # No feelings/sensory/camaraderie
    if not bad_intents:
        score += 1
        score_notes.append("no_bad:+1")

    # No first-person mimicry
    if not mimicry:
        score += 1
        score_notes.append("no_mimicry:+1")

    # Clear/direct (no therapeutic interpretation)
    therapy_phrases = [
        "must have been", "i imagine that", "that sounds", "must have felt",
    ]
    if not any(p in text_lower for p in therapy_phrases):
        score += 1
        score_notes.append("clear_tone:+1")

    # Required-good-intent overrides
    required_intent = test.get("required_good_intent")
    if required_intent and required_intent not in good_intents:
        hard_fails.append(f"missing_required_intent:{required_intent}")

    # Verdict
    if hard_fails:
        verdict = "HARD_FAIL"
    elif score >= 9:
        verdict = "PASS"
    elif score >= 7:
        verdict = "AMBER"
    else:
        verdict = "FAIL"

    return {
        "verdict": verdict,
        "score": score,
        "score_notes": score_notes,
        "word_count": word_count,
        "question_count": q_count,
        "facts_matched": facts_matched,
        "facts_total": len(fact_buckets),
        "good_intents": good_intents,
        "bad_intents": bad_intents,
        "forbidden_hits": forbidden,
        "mimicry_hits": mimicry,
        "hard_fails": hard_fails,
    }


# ── Runner ────────────────────────────────────────────────────────────────


def _build_runtime71() -> Dict[str, Any]:
    return {
        "current_pass": "pass2a",
        "current_era": "coming_of_age",
        "current_mode": "open",
        "affect_state": "neutral",
        "affect_confidence": 0,
        "cognitive_mode": "open",
        "fatigue_score": 0,
        "paired": False,
        "assistant_role": "interviewer",
        "session_style_directive": "Ask one short question at a time.",
        "identity_complete": True,
        "identity_phase": "complete",
        "effective_pass": "pass2a",
        "speaker_name": "Kent",
        "dob": None,
        "pob": "Stanley ND",
        "profile_seed": {
            "childhood_home": None, "siblings": None, "parents_work": None,
            "heritage": None, "education": None, "military": None,
            "career": None, "partner": None, "children": None,
            "life_stage": None,
        },
        "device_context": {
            "date": datetime.now().strftime("%A, %B %d, %Y"),
            "time": datetime.now().strftime("%I:%M %p"),
            "timezone": "America/Denver",
        },
        "person_id": KENT_PERSON_ID,
        "conversation_state": "answering",
        "cognitive_support_mode": False,
    }


async def _send_turn(ws, narrator_text: str) -> Dict[str, Any]:
    payload = {
        "type": "start_turn",
        "session_id": CONV_ID,
        "conv_id": CONV_ID,
        "message": narrator_text,
        "turn_mode": "interview",
        "params": {
            "person_id": KENT_PERSON_ID,
            "runtime71": _build_runtime71(),
            "turn_mode": "interview",
        },
    }
    await ws.send(json.dumps(payload))

    final_text = ""
    turn_mode_done = ""
    timeout_at = asyncio.get_event_loop().time() + 120.0
    while asyncio.get_event_loop().time() < timeout_at:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=45.0)
        except asyncio.TimeoutError:
            break
        try:
            ev = json.loads(raw)
        except Exception:
            continue
        if ev.get("type") == "done":
            final_text = ev.get("final_text") or ""
            turn_mode_done = ev.get("turn_mode") or ""
            break
        if ev.get("type") == "error":
            final_text = f"[error: {ev.get('message', '?')}]"
            break
    return {"final_text": final_text, "turn_mode": turn_mode_done}


async def main() -> None:
    print(f"HARNESS-KENT-DEEP-WITNESS-02")
    print(f"  WS:      {WS_URL}")
    print(f"  conv_id: {CONV_ID}")
    print(f"  report:  {REPORT_MD}")
    print()

    results: List[Dict[str, Any]] = []

    async with websockets.connect(WS_URL, max_size=10_000_000) as ws:
        try:
            await asyncio.wait_for(ws.recv(), timeout=5.0)
        except asyncio.TimeoutError:
            pass

        await ws.send(json.dumps({
            "type": "sync_session", "person_id": KENT_PERSON_ID,
        }))
        try:
            await asyncio.wait_for(ws.recv(), timeout=5.0)
        except asyncio.TimeoutError:
            pass

        for idx, test in enumerate(TESTS, 1):
            print(f"\n[{idx}/{len(TESTS)}] {test['label']}")
            narrator = test["narrator_text"]
            preview = narrator[:150].replace("\n", " ")
            print(f"  USER>  {preview}{'...' if len(narrator) > 150 else ''}")

            response = await _send_turn(ws, narrator)
            verdict = score_response(test, response["final_text"])
            verdict["lori_text"] = response["final_text"]
            verdict["turn_mode_done"] = response["turn_mode"]
            verdict["test_label"] = test["label"]
            results.append(verdict)

            symbol = {
                "PASS": "PASS",
                "AMBER": "AMBER",
                "FAIL": "FAIL",
                "HARD_FAIL": "HARD-FAIL",
            }.get(verdict["verdict"], verdict["verdict"])
            print(f"  LORI<  ({verdict['turn_mode_done'] or 'llm'} / {verdict['word_count']}w) "
                  f"{response['final_text'][:200]}")
            print(f"  → {symbol}  score={verdict['score']}/12  "
                  f"facts={verdict['facts_matched']}/{verdict['facts_total']}  "
                  f"good={verdict['good_intents']}  bad={verdict['bad_intents']}"
                  + (f"  hard_fails={verdict['hard_fails']}" if verdict["hard_fails"] else ""))
            await asyncio.sleep(2.0)

    # Reports
    pass_n = sum(1 for r in results if r["verdict"] == "PASS")
    amber_n = sum(1 for r in results if r["verdict"] == "AMBER")
    fail_n = sum(1 for r in results if r["verdict"] in ("FAIL", "HARD_FAIL"))

    md = [
        f"# Kent deep-witness harness — {TS}",
        "",
        f"- conv_id: `{CONV_ID}`",
        f"- person_id: `{KENT_PERSON_ID}`",
        f"- WS: `{WS_URL}`",
        f"- tests: {len(results)}",
        "",
        "## Topline",
        f"- PASS: {pass_n}",
        f"- AMBER: {amber_n}",
        f"- FAIL/HARD_FAIL: {fail_n}",
        "",
        "**This harness is built to find failures, not confirm passes.**",
        "Most tests will fail on the current Lori until the LLM-witness-receipt path lands.",
        "",
        "## Per-test verdicts",
        "",
    ]
    for r in results:
        md.append(f"### {r['test_label']}  →  **{r['verdict']}**  (score {r['score']}/12)")
        md.append("")
        md.append(f"- words: {r['word_count']}  questions: {r['question_count']}")
        md.append(f"- facts: {r['facts_matched']}/{r['facts_total']}")
        md.append(f"- good_intents: {r['good_intents']}")
        md.append(f"- bad_intents: {r['bad_intents']}")
        if r['hard_fails']:
            md.append(f"- hard_fails: {r['hard_fails']}")
        md.append(f"- score_notes: {', '.join(r['score_notes'])}")
        md.append("")
        md.append("**Lori said:**")
        md.append("")
        md.append(f"> {r['lori_text']}")
        md.append("")

    REPORT_MD.write_text("\n".join(md), encoding="utf-8")
    with open(REPORT_JSONL, "w", encoding="utf-8") as fp:
        for r in results:
            fp.write(json.dumps(r, default=str) + "\n")

    print(f"\n=== Topline ===")
    print(f"  PASS: {pass_n}  AMBER: {amber_n}  FAIL/HARD_FAIL: {fail_n}")
    print(f"\nReports:")
    print(f"  {REPORT_MD}")
    print(f"  {REPORT_JSONL}")


if __name__ == "__main__":
    asyncio.run(main())
