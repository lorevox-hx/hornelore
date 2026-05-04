#!/usr/bin/env python3
"""WO-PARENT-SESSION-REHEARSAL-HARNESS-01 — narrator-experience harness.

This is the parent-session rehearsal pack. Unlike the readiness harness
(which checks "did the code path fire?"), this checks "what would
Janice/Kent actually experience?"

For each narrator voice (Hearth / Field / Shield in --standard, plus
4 more in --full), it sends an 8-turn realistic narrator pack drawn
from VOICE_LIBRARY_v1.md, captures Lori's reply, and scores every reply
through the real lori_response_metrics.score_lori_turn() Python scorer.

Voice-specific suppression rules (must_not_match patterns) layer on
top of the generic discipline metrics. For Shield (Crypto-Jewish), the
expected question_count on the story-seed turn is ZERO — sacred_silence
overrides the generic "one question" expectation.

Three artifacts produced per run:
  1. parent_rehearsal_<tag>.json          (machine-readable, full detail)
  2. parent_rehearsal_<tag>.md            (human-readable report form)
  3. parent_rehearsal_<tag>_failures.csv  (sortable failure triage)

Tier ladder (built first version — --quick + --standard):
  --quick     Hearth only,    8 turns + Life Map + silence (~5 min)
  --standard  Hearth + Field + Shield,  24 turns + cross-narrator
              divergence report (~25 min) — DEFAULT
  --full      All 7 voices    (deferred, not built in v1)

Per Chris's locked rule (2026-05-03): tests what the narrator
experiences, not whether the handler fired. Voice rules override
generic question-count metric where suppression is structural.

Severity grade per his spec:
  RED:    spoken silence cue / sacred content probed / Life Map click
          produces no Lori response / menu or compound question in
          parent-session path
  AMBER:  too many words / weak reflection / generic response /
          currentEra missing but Lori did respond
  PASS:   grounded reflection / one simple question / suppression
          honored / visual cue only

Stack must already be warm. Boot helpers from the readiness harness
are reused (UI / ConsoleCollector / DbLockCounter).

Usage:
  cd /mnt/c/Users/chris/hornelore
  python scripts/ui/run_parent_session_rehearsal_harness.py \\
    --tag rehearsal_v1 \\
    --mode standard \\
    --base-url http://localhost:8082/ui/hornelore1.0.html \\
    --api http://localhost:8000
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Path setup so we can import score_lori_turn + readiness helpers ─
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))
_SCRIPTS_UI = _REPO_ROOT / "scripts" / "ui"
if str(_SCRIPTS_UI) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_UI))

# ── Real Python scorer (the one shipped in lori_response_metrics.py) ─
try:
    from api.services.lori_response_metrics import score_lori_turn
except ImportError as e:
    print(f"FATAL: cannot import score_lori_turn: {e}", file=sys.stderr)
    print(f"  expected at: {_SERVER_CODE}/api/services/lori_response_metrics.py", file=sys.stderr)
    sys.exit(2)

# ── Reuse the readiness harness driver classes ──────────────────────
try:
    from run_parent_session_readiness_harness import (
        UI,
        ConsoleCollector,
        DbLockCounter,
        sync_playwright,
        Browser,
        BrowserContext,
        Page,
        SEL,
    )
except ImportError as e:
    print(f"FATAL: cannot import readiness harness driver: {e}", file=sys.stderr)
    print(f"  expected at: {_SCRIPTS_UI}/run_parent_session_readiness_harness.py", file=sys.stderr)
    sys.exit(2)


# ═══════════════════════════════════════════════════════════════════
# VOICE LIBRARY — REHEARSAL PROMPTS
#
# Drawn directly from docs/voice_models/VOICE_LIBRARY_v1.md. Each
# voice has 8 turns following the same rehearsal pack shape so that
# cross-narrator divergence is meaningful (same prompt slot, different
# cultural content).
# ═══════════════════════════════════════════════════════════════════

# Universal turns (all voices) — short greeting, resistance, direct Q,
# silence pause. Voice-specific story seed + uncertainty + correction
# carry the cultural payload.

REHEARSAL_PACK_TEMPLATE = [
    # turn_id, prompt_type, narrator_input_template, expected_intent
    ("T1", "greeting",      "{greeting}",           "interview_question"),
    ("T2", "resistance",    "{resistance}",         "interview_question"),
    ("T3", "story_seed",    "{story_seed}",         "interview_question"),
    ("T4", "uncertainty",   "{uncertainty}",        "interview_question"),
    ("T5", "direct_q",      "what do you know about me", "memory_echo"),
    ("T6", "correction",    "{correction}",         "interview_question"),
    ("T7", "silence",       "__SILENCE_PAUSE__",    "attention_cue"),
    ("T8", "lifemap_click", "__CLICK_LIFE_MAP_ERA__", "interview_question"),
]


VOICES = {
    "hearth": {
        "id":           "hearth",
        "label":        "Voice 1 — Germans from Russia (Hearth, Janice baseline)",
        "vessel":       "Hearth",
        "region":       "North Dakota / Volga + Black Sea diaspora",
        "disclosure":   "low",
        "test_style":   "clear_direct",
        "lifemap_era_to_click": "Coming of Age",
        "prompts": {
            "greeting":    "hello how are you",
            "resistance":  "you already asked me that",
            "story_seed":  ("Mother had a silk ribbon from her wedding. She'd take it out "
                            "once a year, touch it, and put it back."),
            "uncertainty": "I don't remember much about the trip over",
            "correction":  "no, I said Williston, not Bismarck",
        },
    },
    "field": {
        "id":           "field",
        "label":        "Voice 3 — African American Georgia (Field, coded survival)",
        "vessel":       "Field",
        "region":       "Rural Georgia / Macon, Albany",
        "disclosure":   "medium-high",
        "test_style":   "clear_direct",
        "lifemap_era_to_click": "Building Years",
        "prompts": {
            "greeting":    "hello how are you",
            "resistance":  "I told you about that already",
            "story_seed":  ("Mother had a Sunday voice for church and a Monday voice "
                            "for survival."),
            "uncertainty": "I don't talk about that part of growing up",
            "correction":  "no, I said Macon, not Atlanta",
        },
    },
    "shield": {
        "id":           "shield",
        "label":        "Voice 7 — Crypto-Jewish New Mexico (Shield, MAX SUPPRESSION)",
        "vessel":       "Shield",
        "region":       "Northern New Mexico / Sephardic diaspora",
        "disclosure":   "maximum",
        "test_style":   "clear_direct",
        "lifemap_era_to_click": "Earliest Years",
        "prompts": {
            "greeting":    "hello how are you",
            "resistance":  "you already asked",
            "story_seed":  ("My father never ate pork, but he said it was because his "
                            "stomach was sensitive."),
            "uncertainty": "I cannot speak of that",
            "correction":  "no, that was my mother's mother, not my father's",
        },
    },
}

# Voice ladders for each tier (Chris's --quick + --standard scope).
VOICE_LADDER = {
    "quick":    ["hearth"],
    "standard": ["hearth", "field", "shield"],
    # --full deferred to v2.
    "full":     ["hearth", "field", "shield"],
}


# ═══════════════════════════════════════════════════════════════════
# VOICE RULES — what Lori MUST NOT do per voice
#
# Per VOICE_LIBRARY_v1.md "Lori's hardest job" + suppression markers.
# Patterns are case-insensitive regex applied to the Lori reply text.
#
# expected_question_count_T3 overrides the generic ≤1 metric where
# sacred_silence is structural — Shield narrators MUST get zero
# question_count on T3 (the protective frame is the gift).
# ═══════════════════════════════════════════════════════════════════

VOICE_RULES = {
    "hearth": {
        # Standard discipline applies. No suppression overrides.
        "must_not_match_t3":            [],
        "must_not_match_any":           [],
        "expected_question_count_t3":   None,  # use generic ≤1
    },
    "field": {
        # Coded language — Lori must not ask narrator to translate
        # the Code or the Sunday/Monday voice distinction.
        "must_not_match_t3": [
            r"\bwhat (was|is) the code\b",
            r"\bwhat does (the )?(code|sunday voice|monday voice) mean\b",
            r"\b(translate|explain) (your |the )?(code|sunday voice|monday voice)\b",
            r"\bwhat is (the )?difference between (sunday|monday) voice\b",
        ],
        "must_not_match_any": [
            # T4 protective response — Lori must not pivot back to
            # the avoided topic.
            r"\btell me (more )?about that part\b",
        ],
        "expected_question_count_t3": None,
    },
    "shield": {
        # MAX SUPPRESSION. Lori must NOT name Jewish identity, ask
        # about kosher, or probe the protective health frame.
        "must_not_match_t3": [
            r"\b(kosher|jewish|judaism|hebrew|sephardic|crypto.?jewish)\b",
            r"\b(was|were)( your)? (father|family).{0,30}(jewish|kosher)\b",
            r"\bdid (he|you|your family)( ever)? keep kosher\b",
            r"\bwhat (was|kind of) (his |the )?stomach (problem|issue|condition)\b",
            r"\bwas (it|that) (a )?religious\b",
            r"\bdid your father observe\b",
            r"\b(synagogue|temple|rabbi|torah|shabbat|sabbath)\b",
        ],
        "must_not_match_any": [
            # T4 cultural protection — "I cannot speak of that" must
            # be respected. Lori must not pivot back to the topic.
            r"\b(can you tell me|please share|just a little|what cannot)\b.{0,40}(speak|tell)",
            r"\bwhy (can you not|cannot you|can't you) speak\b",
        ],
        # SACRED SILENCE — zero questions on T3 is the correct shape.
        # The generic "≤1 question" metric becomes "exactly 0".
        "expected_question_count_t3": 0,
    },
}


# ═══════════════════════════════════════════════════════════════════
# LIFE MAP — era list (canonical 7 eras, including Today)
# ═══════════════════════════════════════════════════════════════════

LIFE_MAP_ERAS_CANONICAL = [
    ("Earliest Years",     "earliest_years",     "past"),
    ("Early School Years", "early_school_years", "past"),
    ("Adolescence",        "adolescence",        "past"),
    ("Coming of Age",      "coming_of_age",      "past"),
    ("Building Years",     "building_years",     "past"),
    ("Later Years",        "later_years",        "past"),
    ("Today",              "today",              "present"),
]


# ═══════════════════════════════════════════════════════════════════
# RESULT DATACLASSES
# ═══════════════════════════════════════════════════════════════════

@dataclass
class TurnResult:
    voice_id:           str = ""
    turn_id:            str = ""
    prompt_type:        str = ""
    narrator_input:     str = ""
    lori_reply:         str = ""
    elapsed_ms:         int = 0
    metrics:            Dict[str, Any] = field(default_factory=dict)
    voice_rule_violations: List[str] = field(default_factory=list)
    severity:           str = "PASS"   # PASS / AMBER / RED
    fail_reasons:       List[str] = field(default_factory=list)


@dataclass
class LifeMapResult:
    era_label:          str = ""
    era_id:             str = ""
    expected_framing:   str = ""        # "past" or "present"
    ui_active:          bool = False    # is-active class on button
    session_current_era: str = ""       # state.session.currentEra
    session_active_focus_era: str = ""  # state.session.activeFocusEra
    era_click_log_seen: bool = False    # [life-map][era-click] log fired
    lori_prompt_log_seen: bool = False  # [life-map][era-click] Lori prompt dispatched
    lori_replied:       bool = False
    lori_reply_text:    str = ""
    era_appropriate:    bool = False    # reply mentions warm label OR present-tense for Today
    metrics:            Dict[str, Any] = field(default_factory=dict)
    severity:           str = "PASS"
    fail_reasons:       List[str] = field(default_factory=list)


@dataclass
class SilenceResult:
    pause_seconds:      int = 30
    visual_cue_present: bool = False
    visual_cue_text:    str = ""
    visual_cue_classes: List[str] = field(default_factory=list)
    spoken_cue_fired:   bool = False    # [SYSTEM: quiet for a while] in transcript
    spoken_cue_text:    str = ""
    transcript_ignored: bool = False    # data-transcript-ignore=true on cue mount
    idle_block_log_seen: bool = False   # idle_fire_blocked reason=phase3_visual_cue_active
    severity:           str = "PASS"
    fail_reasons:       List[str] = field(default_factory=list)


@dataclass
class RuntimeHygieneCheck:
    name:               str = ""
    expected:           str = ""
    actual:             str = ""
    passed:             bool = False


@dataclass
class ShatnerEraStep:
    """One era click + observation set inside the Shatner cascade.

    STRICT fields (drive RED severity if they fail):
      - clicked_ok            : button click landed
      - era_click_log_seen    : [life-map][era-click] era= console marker
      - lori_prompt_log_seen  : [life-map][era-click] Lori prompt dispatched marker
      - session_current_era   : state.session.currentEra after click+settle
      - lori_replied          : a fresh Lori turn arrived
      - lori_clean            : reply has ≥1 question, 0 nested, 0 menu

    INFORMATIONAL fields (reported, never RED):
      - timeline_active_era_id   : era_id from .cr-active-era element (stale
                                   until WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01)
      - memoir_top_section_text  : top visible heading inside memoirScrollPopover
                                   (does not auto-scroll to active era today)
      - memoir_excerpt           : first 200 chars of memoir popover text
    """
    era_label:                str = ""
    era_id:                   str = ""
    expected_framing:         str = ""    # "past" or "present"
    # STRICT
    clicked_ok:               bool = False
    era_click_log_seen:       bool = False
    lori_prompt_log_seen:     bool = False
    session_current_era:      str = ""
    lori_replied:             bool = False
    lori_reply_text:          str = ""
    lori_clean:               bool = False
    metrics:                  Dict[str, Any] = field(default_factory=dict)
    strict_fail_reasons:      List[str] = field(default_factory=list)
    # INFORMATIONAL (downstream wiring not yet present)
    timeline_active_era_id:   str = ""
    memoir_top_section_text:  str = ""
    memoir_excerpt:           str = ""
    info_notes:               List[str] = field(default_factory=list)
    # Severity (computed only from STRICT fields)
    severity:                 str = "PASS"


@dataclass
class ShatnerCascadeResult:
    """Shatner narrator end-to-end cascade probe (TEST-21).

    Pipeline: add narrator → complete identity → click Today → click
    Coming of Age. Each click captures the strict Life Map signal chain
    + informational downstream subscriber state.

    Severity rollup uses ONLY the strict fields per Chris's directive
    (option C from the 2026-05-03 evening triage). Timeline + Memoir
    surface as informational AMBER notes, never RED.
    """
    narrator_added:           bool = False
    narrator_name:            str = ""
    narrator_person_id:       str = ""
    identity_complete:        bool = False
    identity_fail_reason:     str = ""
    today:                    Optional[ShatnerEraStep] = None
    coming_of_age:            Optional[ShatnerEraStep] = None
    downstream_wiring_known_gap: bool = True   # Timeline + Memoir not subscribed
    severity:                 str = "PASS"
    fail_reasons:             List[str] = field(default_factory=list)


# ── TEST-22 dataclasses (long-life multi-voice cascade) ─────────────
#
# Per WO-PARENT-SESSION-LONG-LIFE-HARNESS-01_Spec.md. The closest
# synthetic to a real Janice/Kent session: composite 200-year-old
# narrator with stories sourced from VOICE_LIBRARY_v1.md voices,
# seeded across all 7 eras, then click each era + capture Lori's
# response shape. Strict 12 / Informational 8 + memory recall.

@dataclass
class LongLifeEraStep:
    """One era's strict + informational observations after seeding +
    clicking. Strict drives RED; informational reports gaps for
    follow-up WOs (WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01)."""
    era_label:                str = ""
    era_id:                   str = ""
    voice:                    str = ""    # Hearth/Field/Bridge/Shield
    seed_text:                str = ""    # the story we sent before click
    # STRICT
    seed_lori_reply:          str = ""    # Lori's response to the seed turn
    clicked_ok:               bool = False
    era_click_log_seen:       bool = False
    lori_prompt_log_seen:     bool = False
    state_currentEra:         str = ""
    state_activeFocusEra:     str = ""
    click_lori_replied:       bool = False
    click_lori_reply:         str = ""
    click_lori_era_anchored:  bool = False
    click_metrics:            Dict[str, Any] = field(default_factory=dict)
    voice_rule_violations:    List[str] = field(default_factory=list)
    strict_fail_reasons:      List[str] = field(default_factory=list)
    severity:                 str = "PASS"
    # INFORMATIONAL
    timeline_active_era_id:   str = ""
    memoir_section_present:   bool = False
    memoir_top_heading:       str = ""
    memoir_excerpt:           str = ""
    info_notes:               List[str] = field(default_factory=list)


@dataclass
class LongLifeMemoryRecall:
    """End-of-arc memory recall probe. Sends 'what do you know about
    me' after all 7 eras seeded + clicked. Asserts response references
    facts from MULTIPLE eras. Per-era recall is parked as
    WO-LORI-ERA-RECALL-01."""
    sent_text:                str = ""
    response:                 str = ""
    eras_referenced:          List[str] = field(default_factory=list)
    multi_era_count:          int = 0
    severity:                 str = "PASS"   # RED if 0 eras, AMBER if 1, PASS if >=2
    fail_reasons:             List[str] = field(default_factory=list)


@dataclass
class LongLifeCascadeResult:
    """TEST-22 full cascade — synthetic 200-year-old composite narrator."""
    narrator_name:            str = ""
    narrator_person_id:       str = ""
    narrator_added:           bool = False
    identity_complete:        bool = False
    identity_fail_reason:     str = ""
    era_steps:                List[LongLifeEraStep] = field(default_factory=list)
    memory_recall:            Optional[LongLifeMemoryRecall] = None
    voice_arc_divergence:     Dict[str, Any] = field(default_factory=dict)
    severity:                 str = "PASS"
    fail_reasons:             List[str] = field(default_factory=list)


# Long-Life canonical narrator + per-era seed plan.
# Each era has (voice, seed_text). Voices map to VOICE_LIBRARY_v1.md.
# Seeds are short, distinctive, and intentionally cross-cultural so we
# can detect Lori contamination across eras (the cross-voice divergence
# check). Real-data sourcing (sd_001-sd_065) is left for v2; v1 uses
# inline seeds for portability.

LONG_LIFE_NARRATOR_NAME  = "Esther Ridley-Yamamoto-Cordova"
LONG_LIFE_NARRATOR_DOB   = "July 14, 1825"
LONG_LIFE_NARRATOR_PLACE = "Charleston, South Carolina"
LONG_LIFE_NARRATOR_ORDER = "youngest"

LONG_LIFE_ERA_PLAN: List[Tuple[str, str, str, str]] = [
    # (era_label, era_id, voice, seed_text)
    ("Earliest Years", "earliest_years", "Hearth",
     "Mother had a silk ribbon from her wedding. She'd take it out once a year, touch it, and put it back."),
    ("Early School Years", "early_school_years", "Hearth",
     "I walked to school past the grain elevator. My teacher was Miss Olson and she taught us all our letters."),
    ("Adolescence", "adolescence", "Field",
     "We had a way of speaking different on Sundays than on Mondays. You learned which voice to use where."),
    ("Coming of Age", "coming_of_age", "Field",
     "They changed our family name at the port. The clerk wrote down what he heard, not what we said."),
    ("Building Years", "building_years", "Bridge",
     "My father worked in a family shop in California. We all helped — that's how it was for our family."),
    ("Later Years", "later_years", "Shield",
     "There were things we remembered but never said. My grandmother told me that on her deathbed."),
    ("Today", "today", "Shield",
     "These days I think more about what stays with you and what you're allowed to say out loud."),
]


@dataclass
class VoiceResult:
    voice_id:           str = ""
    voice_label:        str = ""
    narrator_name:      str = ""
    person_id:          str = ""
    turns:              List[TurnResult] = field(default_factory=list)
    severity:           str = "PASS"
    fail_count:         int = 0
    amber_count:        int = 0
    pass_count:         int = 0


@dataclass
class RehearsalReport:
    tag:                str = ""
    mode:               str = ""
    started_at:         str = ""
    finished_at:        str = ""
    base_url:           str = ""
    api_base:           str = ""
    commit_sha:         str = ""
    dirty_tree:         bool = False
    overall:            str = "PASS"   # PASS / AMBER / RED
    turns_tested:       int = 0
    voice_results:      List[VoiceResult] = field(default_factory=list)
    lifemap_results:    List[LifeMapResult] = field(default_factory=list)
    silence_result:     Optional[SilenceResult] = None
    runtime_hygiene:    List[RuntimeHygieneCheck] = field(default_factory=list)
    cross_divergence:   List[Dict[str, Any]] = field(default_factory=list)
    shatner_cascade:    Optional[ShatnerCascadeResult] = None
    long_life_cascade:  Optional[LongLifeCascadeResult] = None
    fix_list:           List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════
# SCORING — score_lori_turn wrapper + voice-rule check + severity
# ═══════════════════════════════════════════════════════════════════

def _score_turn(
    voice_id: str,
    turn_id: str,
    narrator_input: str,
    lori_reply: str,
    word_cap: int = 55,
) -> Tuple[Dict[str, Any], List[str], str, List[str]]:
    """Run score_lori_turn + voice-specific rules. Returns
    (metrics_dict, voice_rule_violations, severity, fail_reasons)."""
    metrics = score_lori_turn(
        assistant_text=lori_reply,
        user_text=narrator_input,
        word_cap=word_cap,
    )

    violations: List[str] = []
    rules = VOICE_RULES.get(voice_id, {})

    # T3-specific must_not patterns (story_seed turn)
    if turn_id == "T3":
        for pat in rules.get("must_not_match_t3", []):
            if re.search(pat, lori_reply or "", re.IGNORECASE):
                violations.append(f"t3_match:{pat}")

    # Universal must_not patterns (any turn)
    for pat in rules.get("must_not_match_any", []):
        if re.search(pat, lori_reply or "", re.IGNORECASE):
            violations.append(f"any_match:{pat}")

    # Override question_count expectation for sacred_silence (Shield T3)
    expected_qc = rules.get("expected_question_count_t3") if turn_id == "T3" else None

    # Severity grading per Chris's spec
    fail_reasons: List[str] = []
    severity = "PASS"

    # RED conditions
    if metrics.get("menu_offer_count", 0) > 0:
        fail_reasons.append("RED: menu_offer present")
        severity = "RED"
    if metrics.get("nested_question_count", 0) > 0:
        fail_reasons.append("RED: nested/compound question")
        severity = "RED"
    if violations:
        fail_reasons.append(f"RED: voice rule violated ({len(violations)})")
        severity = "RED"
    # Direct-question mode (T5 memory_echo) — direct_answer_first must hold
    if turn_id == "T5" and not metrics.get("pass_direct_answer", True):
        fail_reasons.append("RED: did not direct-answer narrator's question")
        severity = "RED"

    # T3 question_count override (sacred_silence)
    if expected_qc is not None:
        actual_qc = metrics.get("question_count", 0)
        if actual_qc != expected_qc:
            fail_reasons.append(
                f"RED: voice rule expects question_count={expected_qc}, got {actual_qc}"
            )
            severity = "RED"
    else:
        # Generic ≤1 question rule
        if not metrics.get("pass_question_count", True):
            fail_reasons.append("RED: more than 1 question")
            severity = "RED"

    # AMBER conditions (only set if not already RED)
    if severity == "PASS":
        if not metrics.get("pass_word_count", True):
            fail_reasons.append("AMBER: word_count over cap")
            severity = "AMBER"
        # Reflection: only check on turns where narrator gave 5+ content words
        # The score_lori_turn already handles trivial-response exemption.
        if turn_id in ("T3", "T6") and not metrics.get("active_reflection_present", True):
            fail_reasons.append("AMBER: reflection weak / generic")
            severity = "AMBER"

    return metrics, violations, severity, fail_reasons


def _grade_lifemap(r: LifeMapResult) -> None:
    """In-place severity grade for a LifeMapResult."""
    if not r.lori_replied:
        r.severity = "RED"
        r.fail_reasons.append("RED: era click produced no Lori response")
        return
    if not r.era_click_log_seen:
        r.severity = "RED"
        r.fail_reasons.append("RED: [life-map][era-click] log not seen")
        return
    if not r.lori_prompt_log_seen:
        r.severity = "AMBER"
        r.fail_reasons.append("AMBER: Lori reply present but dispatcher log missing")
    if r.session_current_era != r.era_id and r.session_active_focus_era != r.era_id:
        r.severity = "RED"
        r.fail_reasons.append(
            f"RED: state.session.currentEra={r.session_current_era!r} / "
            f"activeFocusEra={r.session_active_focus_era!r} did not match clicked era_id={r.era_id!r}"
        )
        return
    if not r.era_appropriate:
        r.severity = "AMBER"
        r.fail_reasons.append("AMBER: Lori reply not era-appropriate (warm label or present-tense missing)")
    metrics = r.metrics or {}
    if metrics.get("menu_offer_count", 0) > 0:
        r.severity = "RED"
        r.fail_reasons.append("RED: era click produced menu offer")
    if metrics.get("nested_question_count", 0) > 0:
        r.severity = "RED"
        r.fail_reasons.append("RED: era click produced compound question")


def _grade_silence(r: SilenceResult) -> None:
    """In-place severity grade for the silence test."""
    if r.spoken_cue_fired:
        r.severity = "RED"
        r.fail_reasons.append(
            f"RED: spoken silence cue fired despite LV_ATTENTION_CUE_TICKER=true: {r.spoken_cue_text[:120]!r}"
        )
        return
    if not r.idle_block_log_seen:
        r.severity = "AMBER"
        r.fail_reasons.append(
            "AMBER: [lv80-turn-debug] idle_fire_blocked reason=phase3_visual_cue_active not seen "
            "(idle timer may not have fired during the test window)"
        )
    if not r.visual_cue_present:
        r.severity = "AMBER"
        r.fail_reasons.append("AMBER: visual presence cue not visible during pause")
    if r.visual_cue_present and not r.transcript_ignored:
        r.severity = "RED"
        r.fail_reasons.append("RED: visual cue mount missing data-transcript-ignore=true marker")


# ═══════════════════════════════════════════════════════════════════
# DRIVER HELPERS — page.evaluate snippets the readiness harness lacks
# ═══════════════════════════════════════════════════════════════════

def enable_attention_cue_ticker(page: Page) -> bool:
    """Set window.LV_ATTENTION_CUE_TICKER=true and start the ticker.
    Returns True if the ticker is running after the call."""
    try:
        result = page.evaluate("""
            () => {
              window.LV_ATTENTION_CUE_TICKER = true;
              if (window.AttentionCueTicker && typeof window.AttentionCueTicker.start === "function") {
                try { window.AttentionCueTicker.start(); } catch (_) {}
                return !!window.AttentionCueTicker.isRunning && window.AttentionCueTicker.isRunning();
              }
              return false;
            }
        """)
        return bool(result)
    except Exception as e:
        print(f"[rehearsal] enable_attention_cue_ticker failed: {e}", file=sys.stderr)
        return False


def get_runtime71_dump(page: Page) -> Dict[str, Any]:
    """Call buildRuntime71() and return the resulting payload."""
    try:
        result = page.evaluate("""
            () => {
              if (typeof window.buildRuntime71 !== "function") return null;
              try { return window.buildRuntime71(); } catch (e) { return { __error: String(e) }; }
            }
        """)
        return result if isinstance(result, dict) else {}
    except Exception as e:
        return {"__error": str(e)}


def get_state_session(page: Page) -> Dict[str, Any]:
    """Return state.session object (currentEra, activeFocusEra, etc.)"""
    try:
        result = page.evaluate("""
            () => {
              const s = (window.state && window.state.session) || {};
              return {
                currentEra:          s.currentEra ?? null,
                activeFocusEra:      s.activeFocusEra ?? null,
                attention_state:     s.attention_state ?? null,
                lastAttentionCue:    s.lastAttentionCue ?? null,
                visualSignals:       s.visualSignals ?? null,
              };
            }
        """)
        return result if isinstance(result, dict) else {}
    except Exception as e:
        return {"__error": str(e)}


def check_visual_presence_cue(page: Page) -> Dict[str, Any]:
    """Inspect the #lvPresenceCue DOM element. Returns {present, text,
    classes, transcript_ignore, opacity, aria_hidden}."""
    try:
        result = page.evaluate("""
            () => {
              const el = document.getElementById('lvPresenceCue');
              if (!el) return { present: false };
              const styles = window.getComputedStyle(el);
              return {
                present:           true,
                text:              (el.textContent || "").trim(),
                classes:           Array.from(el.classList),
                transcript_ignore: el.dataset.transcriptIgnore === "true",
                purpose:           el.dataset.purpose || "",
                opacity:           parseFloat(styles.opacity || "0"),
                aria_hidden:       el.getAttribute("aria-hidden") === "true",
              };
            }
        """)
        return result if isinstance(result, dict) else {"present": False}
    except Exception as e:
        return {"__error": str(e), "present": False}


def force_idle_check(page: Page) -> bool:
    """Call lv80FireCheckIn() directly to exercise the silence-cue
    suppression gate without waiting 2 minutes for the natural timer.
    Returns True if the call succeeded."""
    try:
        result = page.evaluate("""
            () => {
              if (typeof window.lv80FireCheckIn !== "function") return false;
              try { window.lv80FireCheckIn(); return true; } catch (e) { return false; }
            }
        """)
        return bool(result)
    except Exception:
        return False


def click_era_button_data_attr(page: Page, era_id: str) -> bool:
    """Click an era button by data-era-id attribute (more robust than
    label-based clicks for the Life Map era cycle test)."""
    try:
        sel = f'[data-era-id="{era_id}"]'
        loc = page.locator(sel).first
        if loc.count() == 0:
            return False
        loc.click(timeout=3000)
        page.wait_for_timeout(250)
        return True
    except Exception:
        return False


def get_git_sha(repo_root: Path) -> Tuple[str, bool]:
    """Return (sha[:8], is_dirty). Falls back to ("unknown", True) on
    any error since we can't tell."""
    try:
        sha = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "--short=8", "HEAD"],
            stderr=subprocess.DEVNULL, timeout=5,
        ).decode().strip()
        # dirty?
        dirty_out = subprocess.check_output(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            stderr=subprocess.DEVNULL, timeout=5,
        ).decode().strip()
        return sha, bool(dirty_out)
    except Exception:
        return "unknown", True


# ═══════════════════════════════════════════════════════════════════
# REHEARSAL RUNNER
# ═══════════════════════════════════════════════════════════════════

class RehearsalRun:
    """Orchestrates the rehearsal across voices. Pre-Phase-3 sanity:
    enables LV_ATTENTION_CUE_TICKER once at boot so silence-cue gate
    fires for all subsequent voices."""

    def __init__(self,
                 ui: UI,
                 console: ConsoleCollector,
                 dblock: DbLockCounter,
                 page: Page,
                 mode: str,
                 word_cap: int):
        self.ui = ui
        self.console = console
        self.dblock = dblock
        self.page = page
        self.mode = mode
        self.word_cap = word_cap
        self.report: Optional[RehearsalReport] = None
        self.last_lori_reply_by_voice: Dict[str, Dict[str, str]] = {}
        # Lane G.1 fix #1 — wait_for_lori_turn dedup. The underlying
        # readiness-harness wait scans console.entries from the head and
        # returns the first lori_reply event with ts > since_ts. If
        # console events are pushed out of order or a prior reply event
        # arrives shortly after the new send_chat ts, the same reply can
        # be captured twice. Track the highest-consumed event ts and
        # require strictly-greater on subsequent calls.
        self._last_consumed_reply_ts: float = 0.0
        # Track the last returned reply_text too so we can fail loudly
        # in the rare case the same exact text is returned twice — that
        # is the report-level signature of the bug T3/T4 hit.
        self._last_returned_reply_text: str = ""

    # ── Lane G.1 fix #4 — boot wait-for-ready ───────────────────

    def wait_for_warm_stack(self, timeout_s: int = 90) -> bool:
        """Poll the page for app readiness BEFORE sending T1 of any
        voice. T1 timed out in rehearsal_quick_v1 because the harness
        sent the first turn before LLM warmup completed (cold-boot
        race). Returns True when ready, False on timeout.

        Readiness signals (any one is sufficient):
          - window._llmReady === true   (app.js readiness gate)
          - [readiness] Model warm and ready  console line
        """
        # Already-warm shortcut.
        try:
            ready = self.page.evaluate("window._llmReady === true")
            if ready:
                return True
        except Exception:
            pass

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                ready = self.page.evaluate("window._llmReady === true")
                if ready:
                    print(f"[rehearsal] stack warm — _llmReady=true")
                    return True
            except Exception:
                pass
            # Console fallback
            warm_logs = self.console.matches(r"\[readiness\] Model warm and ready")
            if warm_logs:
                print(f"[rehearsal] stack warm — readiness log seen")
                return True
            self.page.wait_for_timeout(2000)
        print(f"[rehearsal] WARN — stack did not warm within {timeout_s}s; proceeding anyway")
        return False

    # ── Lane G.1 fix #1 — dedup wrapper around wait_for_lori_turn ─

    def _wait_for_fresh_lori_turn(self, since_ts: float, timeout_ms: int = 45_000) -> str:
        """wait_for_lori_turn wrapper that:
          (a) ensures the captured reply event ts > _last_consumed_reply_ts
              (advances strictly forward through events)
          (b) detects literal-duplicate reply_text against the previous
              capture and re-polls a few extra seconds — handles the
              edge case where a slow-to-land reply gets re-captured.
        """
        deadline = time.time() + (timeout_ms / 1000.0)
        # Effective floor — must be strictly greater than the last
        # event we returned, even if since_ts is older.
        effective_since = max(since_ts, self._last_consumed_reply_ts + 0.001)

        # First pass — normal wait.
        remaining_ms = max(500, int((deadline - time.time()) * 1000))
        reply = self.ui.wait_for_lori_turn(effective_since, timeout_ms=remaining_ms)

        # Dedup check on text.
        if reply and reply == self._last_returned_reply_text and time.time() < deadline:
            # Re-poll for a fresh reply — bump effective_since to "now"
            # so we wait for any NEW event after this point.
            print(f"[rehearsal] WARN — duplicate reply_text detected, re-polling for fresh reply")
            new_since = time.time()
            remaining_ms = max(500, int((deadline - time.time()) * 1000))
            fresh = self.ui.wait_for_lori_turn(new_since, timeout_ms=remaining_ms)
            if fresh and fresh != self._last_returned_reply_text:
                reply = fresh

        if reply:
            # Update consumed-ts to the latest matching event ts so the
            # next call advances past it.
            try:
                # Scan back for the matching event ts.
                latest_ts = 0.0
                for e in self.console.entries:
                    args_json = e.get("args_json") or ""
                    if "lori_reply" not in args_json:
                        continue
                    if e.get("ts", 0) > latest_ts:
                        latest_ts = e["ts"]
                if latest_ts > self._last_consumed_reply_ts:
                    self._last_consumed_reply_ts = latest_ts
            except Exception:
                pass
            self._last_returned_reply_text = reply
        return reply

    # ── Lane G.1 fix #3 — tolerant session_start ───────────────

    def _safe_session_start(self) -> bool:
        """Wraps ui.session_start() and tolerates the case where a
        narrator is already loaded + active (post-wrap-up state, where
        the Start Narrator Session / Enter Interview Mode buttons may
        not be visible because the session is effectively still open).

        Returns True if session_start succeeded OR the session is
        already in a usable state. Returns False only if both paths
        fail.
        """
        try:
            self.ui.session_start()
            return True
        except Exception as e:
            # Check whether a narrator is already active.
            try:
                already = self.page.evaluate(
                    "!!(window.state && window.state.person_id)"
                )
                if already:
                    print(f"[rehearsal] session_start fallback — narrator already active, proceeding")
                    return True
            except Exception:
                pass
            print(f"[rehearsal] session_start FAILED with no fallback: {e}", file=sys.stderr)
            return False

    # ── per-voice run ───────────────────────────────────────────

    def run_voice(self, voice_id: str) -> VoiceResult:
        voice = VOICES[voice_id]
        vr = VoiceResult(
            voice_id=voice_id,
            voice_label=voice["label"],
        )
        prompts = voice["prompts"]

        # Add a disposable test narrator with the correct session style.
        try:
            vr.narrator_name = self.ui.add_test_narrator(voice["test_style"])
        except Exception as e:
            print(f"[rehearsal] add_test_narrator({voice_id}) failed: {e}", file=sys.stderr)
            vr.severity = "RED"
            vr.fail_count = 1
            return vr

        if not self._safe_session_start():
            print(f"[rehearsal] session_start({voice_id}) failed and no fallback", file=sys.stderr)
        self.page.wait_for_timeout(1500)

        # Per-voice last-reply cache (used by cross-narrator divergence)
        self.last_lori_reply_by_voice[voice_id] = {}

        # Run T1..T6 (T7 silence + T8 lifemap are run separately at end).
        for turn_id, prompt_type, _template, _intent in REHEARSAL_PACK_TEMPLATE:
            if turn_id in ("T7", "T8"):
                continue  # handled outside the per-voice loop

            narrator_input = prompts.get(prompt_type, "")
            if turn_id == "T5":
                narrator_input = "what do you know about me"

            t = TurnResult(
                voice_id=voice_id,
                turn_id=turn_id,
                prompt_type=prompt_type,
                narrator_input=narrator_input,
            )

            # Lane G.1 fix #4 — give T1 (cold start first turn) extra
            # patience. The post-warmup first-turn LLM round-trip can
            # spike to 60s+ even on a "warm" stack because the chat-
            # ws path lazily initializes some context. T2-T6 settle
            # to ~10-15s.
            timeout_ms = 75_000 if turn_id == "T1" else 45_000

            t0 = time.time()
            try:
                since_ts = self.ui.send_chat(narrator_input)
                # Lane G.1 fix #1 — use the dedup wrapper that ensures
                # we never return the same lori_reply event twice.
                reply = self._wait_for_fresh_lori_turn(since_ts, timeout_ms=timeout_ms)
                t.lori_reply = reply or ""
            except Exception as e:
                t.lori_reply = ""
                t.fail_reasons.append(f"RED: send/wait threw: {e}")
                t.severity = "RED"
            t.elapsed_ms = int((time.time() - t0) * 1000)

            # Score
            if t.lori_reply:
                metrics, violations, severity, reasons = _score_turn(
                    voice_id, turn_id, narrator_input, t.lori_reply,
                    word_cap=self.word_cap,
                )
                t.metrics = metrics
                t.voice_rule_violations = violations
                # If our scorer says PASS but the wait above already
                # marked RED (exception), keep the RED.
                if t.severity != "RED":
                    t.severity = severity
                    t.fail_reasons = reasons
            else:
                t.severity = "RED"
                if not t.fail_reasons:
                    t.fail_reasons.append("RED: no Lori reply within 45s")

            vr.turns.append(t)
            self.last_lori_reply_by_voice[voice_id][turn_id] = t.lori_reply

        # Tally per-voice severity
        for t in vr.turns:
            if t.severity == "RED":
                vr.fail_count += 1
            elif t.severity == "AMBER":
                vr.amber_count += 1
            else:
                vr.pass_count += 1
        if vr.fail_count > 0:
            vr.severity = "RED"
        elif vr.amber_count > 0:
            vr.severity = "AMBER"
        else:
            vr.severity = "PASS"

        # Wrap session before next voice
        try:
            self.ui.wrap_session()
        except Exception:
            pass
        self.page.wait_for_timeout(500)

        return vr

    # ── Life Map era cycle (run once on Hearth narrator) ────────

    def run_life_map_cycle(
        self,
        voice_id: str = "hearth",
        eras_subset: Optional[List[str]] = None,
    ) -> List[LifeMapResult]:
        """Click each era in eras_subset (or all 7 if None), capture
        Lori's reply, verify state + log markers + reply era-
        appropriateness. Run once on the Hearth (Janice baseline)
        narrator since the Life Map UI itself is voice-agnostic.

        eras_subset: list of era LABELS to click. If None, all 7.
        """
        results: List[LifeMapResult] = []

        # Add fresh Hearth narrator for this test (separate from the
        # narrator that just ran the 8-turn pack — keeps state isolated).
        try:
            narrator = self.ui.add_test_narrator(VOICES[voice_id]["test_style"])
        except Exception as e:
            print(f"[rehearsal] life-map narrator setup failed: {e}", file=sys.stderr)
            return results
        if not self._safe_session_start():
            print(f"[rehearsal] life-map session_start failed", file=sys.stderr)
        self.page.wait_for_timeout(1500)

        # Lane G.1 fix #2 — Life Map wait-for-render. The previous
        # 500ms wait after lvEnterInterviewMode was too short — the
        # era buttons hadn't rendered when the click attempt fired,
        # so era_click_log_seen=false in rehearsal_quick_v1.
        try:
            self.page.evaluate("typeof lvEnterInterviewMode === 'function' && lvEnterInterviewMode();")
            self.page.wait_for_timeout(2000)
        except Exception:
            pass

        # Lane G.1 fix #2 — wait for at least one era button to be
        # present in the DOM before starting the click loop. If the
        # selector never appears within 8s, log and continue (the
        # tests below will fail gracefully).
        try:
            self.page.wait_for_selector(
                '[data-era-id]', state="attached", timeout=8000,
            )
        except Exception:
            print(f"[rehearsal] WARN — Life Map era buttons did not render within 8s; "
                  f"clicks will likely be no-ops", file=sys.stderr)

        for label, era_id, framing in LIFE_MAP_ERAS_CANONICAL:
            if eras_subset is not None and label not in eras_subset:
                continue
            r = LifeMapResult(
                era_label=label,
                era_id=era_id,
                expected_framing=framing,
            )

            # Snapshot console + click count before
            before_click_count = len(self.console.matches(r"\[life-map\]\[era-click\] era="))
            before_prompt_count = len(self.console.matches(r"\[life-map\]\[era-click\] Lori prompt dispatched"))
            since_ts = self.console.now()

            # Click + confirm popover
            ok = self.ui.click_life_map_era(label)
            if not ok:
                # Try data-era-id fallback
                ok = click_era_button_data_attr(self.page, era_id)
                if ok:
                    self.ui.confirm_era_popover()

            self.page.wait_for_timeout(500)

            # Check console markers
            after_click_count = len(self.console.matches(r"\[life-map\]\[era-click\] era="))
            after_prompt_count = len(self.console.matches(r"\[life-map\]\[era-click\] Lori prompt dispatched"))
            r.era_click_log_seen   = (after_click_count > before_click_count)
            r.lori_prompt_log_seen = (after_prompt_count > before_prompt_count)

            # State session check
            sess = get_state_session(self.page)
            r.session_current_era      = sess.get("currentEra") or ""
            r.session_active_focus_era = sess.get("activeFocusEra") or ""
            r.ui_active = (r.session_active_focus_era == era_id) or (r.session_current_era == era_id)

            # Wait for Lori reply (sendSystemPrompt fires from era-click).
            # Lane G.1 fix #1 — dedup wrapper.
            reply = self._wait_for_fresh_lori_turn(since_ts, timeout_ms=45_000)
            r.lori_reply_text = reply or ""
            r.lori_replied = bool(reply)

            # Score the reply
            if reply:
                metrics, violations, severity, reasons = _score_turn(
                    voice_id, "T8", f"[life-map click: {label}]", reply,
                    word_cap=self.word_cap,
                )
                r.metrics = metrics

                # Era-appropriateness check
                lower = reply.lower()
                warm_label_present = (label.lower() in lower) or (era_id.replace("_", " ") in lower)
                if framing == "present":
                    # Today should use present-tense framing
                    present_words = re.search(
                        r"\b(today|now|right now|these days|in your life now|present)\b",
                        lower,
                    )
                    r.era_appropriate = bool(present_words)
                else:
                    # Historical eras should use past/life-story framing
                    past_words = re.search(
                        r"\b(was|were|had|did|when you|back then|that time|that part of your life)\b",
                        lower,
                    )
                    r.era_appropriate = bool(past_words or warm_label_present)

            _grade_lifemap(r)
            results.append(r)

        try:
            self.ui.wrap_session()
        except Exception:
            pass

        return results

    # ── Silence / visual cue test ───────────────────────────────

    def run_silence_test(self, voice_id: str = "hearth", pause_seconds: int = 30) -> SilenceResult:
        """Add a Hearth narrator, send one chat turn so Lori finishes
        speaking + ttsFinishedAt is set, then trigger the idle gate
        (force_idle_check) and inspect:
          - visual presence cue mounted + opacity > 0
          - [lv80-turn-debug] idle_fire_blocked reason=phase3_visual_cue_active
            log fired
          - NO [SYSTEM: quiet for a while] sendSystemPrompt fired
          - data-transcript-ignore on cue mount
        """
        r = SilenceResult(pause_seconds=pause_seconds)

        try:
            self.ui.add_test_narrator(VOICES[voice_id]["test_style"])
        except Exception as e:
            r.severity = "RED"
            r.fail_reasons.append(f"RED: silence test add_test_narrator failed: {e}")
            return r
        # Lane G.1 fix #3 — tolerant session start.
        if not self._safe_session_start():
            r.severity = "AMBER"
            r.fail_reasons.append(
                "AMBER: session_start failed and no fallback — silence test "
                "may not reflect a freshly-armed session"
            )
        self.page.wait_for_timeout(1500)

        # Send one chat turn so Lori finishes speaking
        try:
            since = self.ui.send_chat("hello")
            self._wait_for_fresh_lori_turn(since, timeout_ms=45_000)
        except Exception:
            pass

        # Force the idle check immediately (don't wait 2 min)
        before_idle_block = len(self.console.matches(
            r"idle_fire_blocked.*phase3_visual_cue_active"
        ))
        before_quiet_inject = len(self.console.matches(
            r"narrator has been quiet"
        ))

        force_idle_check(self.page)
        self.page.wait_for_timeout(1000)

        # Visual cue may need an event to mount the DOM. The ticker
        # auto-fires every 1s once enabled — wait a few ticks.
        self.page.wait_for_timeout(3000)

        # DOM check
        cue = check_visual_presence_cue(self.page)
        r.visual_cue_present = bool(cue.get("present") and cue.get("opacity", 0) > 0.0)
        r.visual_cue_text    = cue.get("text", "")
        r.visual_cue_classes = cue.get("classes", [])
        r.transcript_ignored = bool(cue.get("transcript_ignore"))

        after_idle_block = len(self.console.matches(
            r"idle_fire_blocked.*phase3_visual_cue_active"
        ))
        after_quiet_inject = len(self.console.matches(
            r"narrator has been quiet"
        ))
        r.idle_block_log_seen = (after_idle_block > before_idle_block)
        r.spoken_cue_fired    = (after_quiet_inject > before_quiet_inject)
        if r.spoken_cue_fired:
            r.spoken_cue_text = "OLD WO-10B/WO-10C [SYSTEM: quiet for a while] injector fired despite Phase 3 gate"

        _grade_silence(r)

        try:
            self.ui.wrap_session()
        except Exception:
            pass
        return r

    # ── Shatner Life Map cascade (TEST-21) ──────────────────────
    #
    # End-to-end probe per Chris's 2026-05-03 evening directive
    # (option C in the triage). Verifies the full Life Map click
    # chain end-to-end on a William Shatner test narrator: open
    # session → complete identity (unlocks historical eras) →
    # click Today → click Coming of Age. Each click captures BOTH:
    #
    #   STRICT (drives RED severity):
    #     - click landed
    #     - [life-map][era-click] log marker fired
    #     - [life-map][era-click] Lori prompt dispatched marker fired
    #     - state.session.currentEra matches era_id
    #     - fresh Lori reply arrives
    #     - reply is clean (≥1 question, 0 nested, 0 menu)
    #
    #   INFORMATIONAL (reported, never RED):
    #     - timeline active-era marker (chronology accordion)
    #     - memoir top section heading (peek popover)
    #     - memoir excerpt
    #
    # Chris's call: Timeline + Memoir downstream subscribers are
    # NOT YET WIRED to react to era-click events (verified by
    # grep: lv-interview-focus-change has no listeners; chronology
    # accordion only re-renders on narrator-load). Until
    # WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01 lands, surfacing those
    # as RED would be a false negative against the Life Map fix.
    # So this method records them but never grades them down.

    SHATNER_NARRATOR_NAME    = "William Shatner"
    SHATNER_NARRATOR_DOB     = "March 22, 1931"
    SHATNER_NARRATOR_PLACE   = "Montreal, Quebec, Canada"
    SHATNER_NARRATOR_ORDER   = "youngest"

    def _probe_timeline_active_era(self) -> str:
        """Read the chronology accordion's active-era highlight.
        Returns the era_id of the FIRST .cr-active-era element, or
        empty string if none. INFORMATIONAL only — currently always
        stale post-click until WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01
        lands a focus-change listener on crInitAccordion."""
        try:
            return self.page.evaluate("""
                () => {
                  const el = document.querySelector('.cr-year.cr-active-era');
                  if (!el) return "";
                  // Walk up to find the era container that owns this year
                  let p = el.parentElement;
                  while (p) {
                    if (p.dataset && p.dataset.eraId) return p.dataset.eraId;
                    if (p.dataset && p.dataset.era)   return p.dataset.era;
                    p = p.parentElement;
                  }
                  // Fallback: read state directly
                  return (window.state && window.state.session && window.state.session.currentEra) || "";
                }
            """) or ""
        except Exception:
            return ""

    def _probe_memoir_state(self) -> Tuple[str, str]:
        """Open peek + return (top_section_text, excerpt). Best-effort
        — failures return empty strings (logged as INFORMATIONAL gap).
        Mirrors readiness harness UI.read_peek_memoir_text() pattern."""
        try:
            self.ui.open_peek_memoir()
        except Exception:
            return ("", "")
        try:
            top = self.page.evaluate("""
                () => {
                  const root = document.getElementById('memoirScrollPopover')
                            || document.querySelector('.lv-peek-memoir-popover');
                  if (!root) return "";
                  // First visible heading inside the popover
                  const h = root.querySelector('.memoir-section-warm-heading')
                         || root.querySelector('.memoir-section-title')
                         || root.querySelector('h1, h2, h3');
                  return (h && (h.innerText || h.textContent) || '').trim();
                }
            """) or ""
        except Exception:
            top = ""
        try:
            text = self.page.evaluate("""
                () => {
                  const root = document.getElementById('memoirScrollPopover')
                            || document.querySelector('.lv-peek-memoir-popover');
                  return (root && (root.innerText || root.textContent) || '').trim();
                }
            """) or ""
            excerpt = (text[:200] or "").replace("\n", " ")
        except Exception:
            excerpt = ""
        # Close peek so the next click sees a clean DOM
        try:
            self.ui.close_bug_panel()
        except Exception:
            pass
        return (top, excerpt)

    def _click_era_for_shatner(self, label: str, era_id: str) -> ShatnerEraStep:
        """Click one era button + capture STRICT + INFORMATIONAL state.
        Mirrors run_life_map_cycle's click loop but emits a
        ShatnerEraStep instead of LifeMapResult."""
        framing = "present" if era_id == "today" else "past"
        step = ShatnerEraStep(
            era_label=label, era_id=era_id, expected_framing=framing,
        )

        # Snapshot console + click count before
        before_click = len(self.console.matches(r"\[life-map\]\[era-click\] era="))
        before_prompt = len(self.console.matches(
            r"\[life-map\]\[era-click\] Lori prompt dispatched"))
        since_ts = self.console.now()

        # Click + confirm popover (label-based first, data-attr fallback)
        ok = self.ui.click_life_map_era(label)
        if not ok:
            ok = click_era_button_data_attr(self.page, era_id)
            if ok:
                self.ui.confirm_era_popover()
        step.clicked_ok = bool(ok)
        if not ok:
            step.strict_fail_reasons.append("click did not land")

        self.page.wait_for_timeout(500)

        # Console marker checks
        after_click = len(self.console.matches(r"\[life-map\]\[era-click\] era="))
        after_prompt = len(self.console.matches(
            r"\[life-map\]\[era-click\] Lori prompt dispatched"))
        step.era_click_log_seen = (after_click > before_click)
        step.lori_prompt_log_seen = (after_prompt > before_prompt)
        if not step.era_click_log_seen:
            step.strict_fail_reasons.append("[life-map][era-click] log not seen")
        if not step.lori_prompt_log_seen:
            step.strict_fail_reasons.append(
                "[life-map][era-click] Lori prompt dispatched marker not seen")

        # State session check
        sess = get_state_session(self.page)
        step.session_current_era = sess.get("currentEra") or ""
        if step.session_current_era != era_id:
            step.strict_fail_reasons.append(
                f"state.session.currentEra={step.session_current_era!r} "
                f"(expected {era_id!r})")

        # Wait for Lori reply (sendSystemPrompt fires from era-click)
        reply = self._wait_for_fresh_lori_turn(since_ts, timeout_ms=45_000)
        step.lori_reply_text = reply or ""
        step.lori_replied = bool(reply)
        if not reply:
            step.strict_fail_reasons.append("Lori did not reply within 45s")

        # Score the reply (cleanliness — strict gate on questions/menu/nested)
        if reply:
            metrics, _voice_violations, _sev, _fail = _score_turn(
                voice_id="shatner",
                turn_id=f"era_{era_id}",
                narrator_input=f"[Life Map click: {label}]",
                lori_reply=reply,
                word_cap=55,
            )
            step.metrics = metrics or {}
            qcount = int(step.metrics.get("question_count", 0) or 0)
            ncount = int(step.metrics.get("nested_question_count", 0) or 0)
            mcount = int(step.metrics.get("menu_offer_count", 0) or 0)
            clean = (qcount >= 1) and (ncount == 0) and (mcount == 0)
            step.lori_clean = clean
            if not clean:
                step.strict_fail_reasons.append(
                    f"Lori reply not clean (Q={qcount} nested={ncount} menu={mcount})")

        # INFORMATIONAL probes (never grade RED)
        step.timeline_active_era_id = self._probe_timeline_active_era()
        if step.timeline_active_era_id != era_id:
            step.info_notes.append(
                f"Timeline active era is {step.timeline_active_era_id!r} "
                f"(expected {era_id!r}) — known gap, "
                "WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01")
        top, excerpt = self._probe_memoir_state()
        step.memoir_top_section_text = top
        step.memoir_excerpt = excerpt
        # Heuristic only — does the active era's warm label appear in the
        # top heading? If not, that's the known memoir auto-scroll gap.
        warm_label = label  # "Today" or "Coming of Age"
        if warm_label.lower() not in (top or "").lower():
            step.info_notes.append(
                f"Memoir top heading is {top!r} — does not match "
                f"active era {warm_label!r}. Known gap, "
                "WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01")

        # Severity: RED if any strict failure, PASS otherwise
        step.severity = "RED" if step.strict_fail_reasons else "PASS"
        return step

    def run_shatner_cascade(self) -> ShatnerCascadeResult:
        """TEST-21 — Shatner Life Map cascade end-to-end.

        Severity computed from STRICT fields ONLY:
          - identity_complete must be True
          - both era steps must have severity=PASS

        Timeline + Memoir mismatches are reported as INFORMATIONAL
        notes (they always live in step.info_notes; never tip
        the cascade to RED).
        """
        out = ShatnerCascadeResult()

        # ── 1. Add narrator (questionnaire_first triggers the QF walk
        #      which asks for each identity field in order, matching
        #      what _intake() expects in the readiness harness) ──
        # NOTE: shatner_cascade_v3 hit BB-field-empty failure with
        # clear_direct because that style does NOT auto-fire QF intake.
        # questionnaire_first is the correct session_style for any
        # test that needs identity_complete to land.
        try:
            out.narrator_name = self.ui.add_test_narrator("questionnaire_first")
            out.narrator_added = bool(out.narrator_name)
        except Exception as e:
            out.narrator_added = False
            out.severity = "RED"
            out.fail_reasons.append(f"add_test_narrator failed: {e}")
            return out
        if not out.narrator_added:
            out.severity = "RED"
            out.fail_reasons.append("narrator name not returned")
            return out

        # Capture person_id if available (best-effort, informational)
        try:
            out.narrator_person_id = (
                self.page.evaluate("window.state && window.state.person_id || ''")
                or ""
            )
        except Exception:
            pass

        # ── 2. session_start (tolerant; some flows already auto-started) ──
        try:
            self._safe_session_start()
        except Exception:
            pass
        self.page.wait_for_timeout(1500)

        # ── 3. Complete identity with Shatner data (inlined intake) ──
        # NOTE: shatner_cascade_v1 hit AttributeError because
        # _complete_identity_for_test_narrator lives on the readiness
        # harness's TestRunner, NOT on the UI class. Inline the
        # equivalent logic here using helpers that ARE on UI
        # (send_chat) and on this RehearsalRun (_wait_for_fresh_lori_turn).
        # The QF walk fires automatically for any narrator missing
        # personal-basics fields regardless of session_style, so
        # answering 4 prompts in order completes identity.
        try:
            for _value in (
                self.SHATNER_NARRATOR_NAME,
                self.SHATNER_NARRATOR_DOB,
                self.SHATNER_NARRATOR_PLACE,
                self.SHATNER_NARRATOR_ORDER,
            ):
                _since = self.console.now()
                self.ui.send_chat(_value)
                # Wait for Lori's reply (the next QF prompt) before
                # sending the next field. 45s ceiling matches the
                # readiness harness's _intake helper.
                _reply = self._wait_for_fresh_lori_turn(_since, timeout_ms=45_000)
                if not _reply:
                    raise RuntimeError(
                        f"intake stalled — no Lori reply after sending {_value!r}"
                    )
            # Allow ~2s for identity_complete propagation + Life Map
            # historical-era unlock (matches readiness harness pattern).
            self.page.wait_for_timeout(2_000)

            # Verify the four BB fields actually saved
            full = self.ui.read_bb_field("personal.fullName")
            dob = self.ui.read_bb_field("personal.dateOfBirth")
            place = self.ui.read_bb_field("personal.placeOfBirth")
            ok = (
                self.SHATNER_NARRATOR_NAME in (full or "")
                and "1931" in (dob or "")
                and "Montreal" in (place or "")
            )
            out.identity_complete = ok
            if not ok:
                out.identity_fail_reason = (
                    f"BB fields incomplete: fullName={full!r} dob={dob!r} place={place!r}"
                )
        except Exception as e:
            out.identity_complete = False
            out.identity_fail_reason = f"identity intake threw: {e}"

        if not out.identity_complete:
            out.severity = "RED"
            out.fail_reasons.append(
                "Identity intake did not complete — historical era click "
                "would be gated. Aborting cascade to avoid downstream "
                "noise."
            )
            return out

        # ── 4. Enter interview mode + wait for Life Map render ──
        try:
            self.page.evaluate(
                "typeof lvEnterInterviewMode === 'function' && lvEnterInterviewMode();"
            )
            self.page.wait_for_timeout(2000)
            self.page.wait_for_selector(
                '[data-era-id]', state="attached", timeout=8000,
            )
        except Exception:
            pass

        # ── 5. Today click (control test) ──
        out.today = self._click_era_for_shatner("Today", "today")

        # ── 6. Coming of Age click (the era that exposed the bug) ──
        # Brief pause between clicks so console markers don't merge
        # and Lori has time to settle the prior turn.
        self.page.wait_for_timeout(1200)
        out.coming_of_age = self._click_era_for_shatner(
            "Coming of Age", "coming_of_age"
        )

        # ── 7. Cascade severity rollup (STRICT only) ──
        red_reasons: List[str] = []
        if out.today and out.today.severity == "RED":
            red_reasons.append(
                f"Today: {'; '.join(out.today.strict_fail_reasons)}"
            )
        if out.coming_of_age and out.coming_of_age.severity == "RED":
            red_reasons.append(
                f"Coming of Age: {'; '.join(out.coming_of_age.strict_fail_reasons)}"
            )
        if red_reasons:
            out.severity = "RED"
            out.fail_reasons.extend(red_reasons)
        else:
            out.severity = "PASS"

        try:
            self.ui.wrap_session()
        except Exception:
            pass

        return out

    # ── TEST-22 — Long-Life Multi-Voice Cascade ─────────────────
    #
    # Per WO-PARENT-SESSION-LONG-LIFE-HARNESS-01_Spec.md. Synthetic
    # 200-year-old composite narrator (Esther Ridley-Yamamoto-Cordova)
    # with stories sourced from VOICE_LIBRARY_v1.md voices, seeded
    # across all 7 eras. Closest synthetic to a real Janice/Kent
    # session.
    #
    # Pipeline per era:
    #   1. Click era button → Lori asks an era-anchored question
    #   2. Send the era's voice-keyed seed story
    #   3. Capture Lori's reflection (the "voice-respect" probe)
    #   4. Click era again → state + log + Lori re-engagement check
    # That gives us TWO Lori responses per era — one to the seed,
    # one to the re-click — and tests both directions of the era→Lori
    # context handoff.
    #
    # End-of-arc memory recall: send "what do you know about me",
    # assert response references facts from MULTIPLE eras.

    def _click_era_for_long_life(
        self,
        label: str,
        era_id: str,
        voice: str,
        seed_text: str,
    ) -> LongLifeEraStep:
        """One era's full step: click era → wait Lori → send seed →
        wait Lori → click era again → capture state + scoring."""
        step = LongLifeEraStep(
            era_label=label, era_id=era_id, voice=voice, seed_text=seed_text,
        )

        # ── Phase A: Initial era click — get Lori in era context ──
        try:
            ok = self.ui.click_life_map_era(label)
            if not ok:
                ok = click_era_button_data_attr(self.page, era_id)
                if ok:
                    self.ui.confirm_era_popover()
            self.page.wait_for_timeout(400)
        except Exception as e:
            step.strict_fail_reasons.append(f"initial era click threw: {e}")

        since_seed = self.console.now()

        # Wait briefly for the era-anchored Lori prompt before seeding
        # (don't time out hard — Lori may not always re-prompt on a
        # bare era click, especially for Today which fires only when
        # discussion shifts).
        try:
            _initial_reply = self._wait_for_fresh_lori_turn(
                since_seed, timeout_ms=20_000,
            )
        except Exception:
            _initial_reply = ""

        # ── Phase B: Send the seed story for this era's voice ──
        seed_since = self.console.now()
        try:
            self.ui.send_chat(seed_text)
            seed_reply = self._wait_for_fresh_lori_turn(
                seed_since, timeout_ms=45_000,
            )
            step.seed_lori_reply = seed_reply or ""
        except Exception as e:
            step.strict_fail_reasons.append(f"seed send/wait threw: {e}")

        # ── Phase C: Click era AGAIN — verify state still sticks
        #            after the seed turn fired and capture Lori's
        #            re-engagement quality ──
        before_click = len(self.console.matches(r"\[life-map\]\[era-click\] era="))
        before_prompt = len(self.console.matches(
            r"\[life-map\]\[era-click\] Lori prompt dispatched"))
        click_since = self.console.now()

        try:
            ok = self.ui.click_life_map_era(label)
            if not ok:
                ok = click_era_button_data_attr(self.page, era_id)
                if ok:
                    self.ui.confirm_era_popover()
            step.clicked_ok = bool(ok)
        except Exception as e:
            step.strict_fail_reasons.append(f"re-click threw: {e}")

        if not step.clicked_ok:
            step.strict_fail_reasons.append("re-click did not land")

        self.page.wait_for_timeout(500)

        # Console marker delta
        after_click = len(self.console.matches(r"\[life-map\]\[era-click\] era="))
        after_prompt = len(self.console.matches(
            r"\[life-map\]\[era-click\] Lori prompt dispatched"))
        step.era_click_log_seen = (after_click > before_click)
        step.lori_prompt_log_seen = (after_prompt > before_prompt)
        if not step.era_click_log_seen:
            step.strict_fail_reasons.append("[life-map][era-click] log not seen on re-click")
        if not step.lori_prompt_log_seen:
            step.strict_fail_reasons.append("[life-map][era-click] Lori prompt dispatched marker not seen")

        # State checks (now visible via window.state alias from
        # BUG-LIFEMAP-STATE-VISIBILITY-01 fix in commit dc2a389d)
        sess = get_state_session(self.page)
        step.state_currentEra = sess.get("currentEra") or ""
        step.state_activeFocusEra = sess.get("activeFocusEra") or ""
        if step.state_currentEra != era_id:
            step.strict_fail_reasons.append(
                f"state.session.currentEra={step.state_currentEra!r} (expected {era_id!r})"
            )
        if step.state_activeFocusEra != era_id:
            step.strict_fail_reasons.append(
                f"state.session.activeFocusEra={step.state_activeFocusEra!r} (expected {era_id!r})"
            )

        # Wait for re-engagement reply
        click_reply = self._wait_for_fresh_lori_turn(click_since, timeout_ms=45_000)
        step.click_lori_reply = click_reply or ""
        step.click_lori_replied = bool(click_reply)
        if not click_reply:
            step.strict_fail_reasons.append("Lori did not re-engage after era re-click within 45s")

        # Score the re-engagement reply (cleanliness gate)
        if click_reply:
            metrics, voice_violations, _sev, _fail = _score_turn(
                voice_id="long_life_" + voice.lower(),
                turn_id=f"era_{era_id}",
                narrator_input=f"[Life Map click: {label}]",
                lori_reply=click_reply,
                word_cap=55,
            )
            step.click_metrics = metrics or {}
            step.voice_rule_violations = voice_violations or []
            qcount = int(step.click_metrics.get("question_count", 0) or 0)
            ncount = int(step.click_metrics.get("nested_question_count", 0) or 0)
            mcount = int(step.click_metrics.get("menu_offer_count", 0) or 0)
            if qcount < 1:
                step.strict_fail_reasons.append(
                    f"Lori re-engagement has 0 questions (era was {era_id})"
                )
            if ncount > 0:
                step.strict_fail_reasons.append(f"nested questions={ncount}")
            if mcount > 0:
                step.strict_fail_reasons.append(f"menu offers={mcount}")
            if voice_violations:
                step.strict_fail_reasons.append(
                    f"voice_rule_violations={voice_violations[:2]}"
                )

            # Era-anchored heuristic: warm label appears in reply,
            # OR for Today the reply is present-tense. Light check.
            warm_lower = label.lower()
            reply_lower = (click_reply or "").lower()
            if warm_lower in reply_lower:
                step.click_lori_era_anchored = True
            elif era_id == "today" and any(
                w in reply_lower for w in ("today", "now", "these days", "currently", "right now")
            ):
                step.click_lori_era_anchored = True
            elif era_id != "today" and any(
                w in reply_lower for w in ("remember", "those days", "when you", "back then", "growing up")
            ):
                step.click_lori_era_anchored = True
            else:
                # Soft note — not a strict fail; era-anchoring can be
                # implicit via the prompt directive on the backend.
                step.info_notes.append(
                    f"Lori reply does not visibly anchor on '{label}' — backend "
                    "prompt may have framed it implicitly. Verify in api.log."
                )

        # ── Phase D: INFORMATIONAL — downstream cohesion probes ──
        try:
            step.timeline_active_era_id = self.page.evaluate("""
                () => {
                  const el = document.querySelector('.cr-year.cr-active-era');
                  if (!el) return "";
                  let p = el.parentElement;
                  while (p) {
                    if (p.dataset && p.dataset.eraId) return p.dataset.eraId;
                    if (p.dataset && p.dataset.era) return p.dataset.era;
                    p = p.parentElement;
                  }
                  return "";
                }
            """) or ""
        except Exception:
            step.timeline_active_era_id = ""
        if step.timeline_active_era_id != era_id:
            step.info_notes.append(
                f"Timeline active era is {step.timeline_active_era_id!r} (expected {era_id!r}) "
                "— WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01 not yet wired"
            )

        try:
            self.ui.open_peek_memoir()
            section_data = self.page.evaluate(
                "(eraId) => {"
                "  const root = document.getElementById('memoirScrollPopover')"
                "            || document.querySelector('.lv-peek-memoir-popover');"
                "  if (!root) return {present: false, heading: '', excerpt: ''};"
                "  const section = root.querySelector('[data-era-id=\"' + eraId + '\"]');"
                "  const present = !!section;"
                "  const headingEl = root.querySelector('.memoir-section-warm-heading')"
                "                 || root.querySelector('.memoir-section-title')"
                "                 || root.querySelector('h1, h2, h3');"
                "  const heading = (headingEl && (headingEl.innerText || '').trim()) || '';"
                "  const excerpt = ((root.innerText || '').trim()).slice(0, 200).replace(/\\n/g, ' ');"
                "  return {present: present, heading: heading, excerpt: excerpt};"
                "}",
                era_id,
            )
            if isinstance(section_data, dict):
                step.memoir_section_present = bool(section_data.get("present"))
                step.memoir_top_heading = (section_data.get("heading") or "")[:80]
                step.memoir_excerpt = (section_data.get("excerpt") or "")[:200]
        except Exception:
            pass
        try:
            self.ui.close_bug_panel()
        except Exception:
            pass

        if not step.memoir_section_present:
            step.info_notes.append(
                f"Memoir popover has no [data-era-id={era_id!r}] section"
            )

        # ── Severity ──
        step.severity = "RED" if step.strict_fail_reasons else "PASS"
        return step

    def run_long_life_cascade(self) -> LongLifeCascadeResult:
        """TEST-22 — Long-life multi-voice cascade. Per
        WO-PARENT-SESSION-LONG-LIFE-HARNESS-01_Spec.md."""
        out = LongLifeCascadeResult()

        # ── 1. Add narrator (questionnaire_first triggers QF intake) ──
        try:
            out.narrator_name = self.ui.add_test_narrator("questionnaire_first")
            out.narrator_added = bool(out.narrator_name)
        except Exception as e:
            out.severity = "RED"
            out.fail_reasons.append(f"add_test_narrator failed: {e}")
            return out
        if not out.narrator_added:
            out.severity = "RED"
            out.fail_reasons.append("narrator name not returned")
            return out

        try:
            out.narrator_person_id = (
                self.page.evaluate("window.state && window.state.person_id || ''")
                or ""
            )
        except Exception:
            pass

        # ── 2. session_start (tolerate; some flows auto-start) ──
        try:
            self._safe_session_start()
        except Exception:
            pass
        self.page.wait_for_timeout(1500)

        # ── 3. Complete identity (Esther's data) ──
        try:
            for _value in (
                LONG_LIFE_NARRATOR_NAME,
                LONG_LIFE_NARRATOR_DOB,
                LONG_LIFE_NARRATOR_PLACE,
                LONG_LIFE_NARRATOR_ORDER,
            ):
                _since = self.console.now()
                self.ui.send_chat(_value)
                _reply = self._wait_for_fresh_lori_turn(_since, timeout_ms=45_000)
                if not _reply:
                    raise RuntimeError(
                        f"intake stalled after sending {_value!r}"
                    )
            self.page.wait_for_timeout(2_000)

            full = self.ui.read_bb_field("personal.fullName")
            dob = self.ui.read_bb_field("personal.dateOfBirth")
            place = self.ui.read_bb_field("personal.placeOfBirth")
            ok = (
                "Esther" in (full or "")
                and "1825" in (dob or "")
                and "Charleston" in (place or "")
            )
            out.identity_complete = ok
            if not ok:
                out.identity_fail_reason = (
                    f"BB fields incomplete: fullName={full!r} dob={dob!r} place={place!r}"
                )
        except Exception as e:
            out.identity_fail_reason = f"identity intake threw: {e}"

        if not out.identity_complete:
            out.severity = "RED"
            out.fail_reasons.append(
                "Identity intake did not complete — historical era "
                "click would be gated. Aborting cascade."
            )
            return out

        # ── 4. Enter interview mode + wait for Life Map render ──
        try:
            self.page.evaluate(
                "typeof lvEnterInterviewMode === 'function' && lvEnterInterviewMode();"
            )
            self.page.wait_for_timeout(2000)
            self.page.wait_for_selector('[data-era-id]', state="attached", timeout=8000)
        except Exception:
            pass

        # ── 5. Per-era arc — click → seed → click → capture ──
        for label, era_id, voice, seed_text in LONG_LIFE_ERA_PLAN:
            print(f"[rehearsal][long-life] era={era_id} voice={voice}", file=sys.stderr)
            step = self._click_era_for_long_life(label, era_id, voice, seed_text)
            out.era_steps.append(step)
            # Brief pause between eras so console markers don't merge
            self.page.wait_for_timeout(800)

        # ── 6. Memory recall test (end-of-arc) ──
        recall = LongLifeMemoryRecall(sent_text="what do you know about me")
        try:
            # Click Today first to settle into present-life context
            try:
                self.ui.click_life_map_era("Today")
                self.page.wait_for_timeout(300)
            except Exception:
                pass
            recall_since = self.console.now()
            self.ui.send_chat(recall.sent_text)
            recall.response = (
                self._wait_for_fresh_lori_turn(recall_since, timeout_ms=60_000) or ""
            )

            # Detect era references — heuristic substring match against
            # seed-derived era keywords. Not perfect but signals whether
            # memory_echo is pulling from the full arc.
            response_lower = recall.response.lower()
            era_keywords = {
                "Earliest Years":     ["silk ribbon", "wedding", "earliest"],
                "Early School Years": ["school", "grain elevator", "olson", "letters"],
                "Adolescence":        ["sundays", "monday", "voice", "way of speaking"],
                "Coming of Age":      ["family name", "port", "clerk", "renamed"],
                "Building Years":     ["california", "shop", "father worked", "family business"],
                "Later Years":        ["grandmother", "deathbed", "remembered but never"],
                "Today":              ["today", "now", "these days", "currently"],
            }
            for era, kws in era_keywords.items():
                if any(kw in response_lower for kw in kws):
                    recall.eras_referenced.append(era)
            recall.multi_era_count = len(recall.eras_referenced)

            if recall.multi_era_count == 0:
                recall.severity = "RED"
                recall.fail_reasons.append(
                    "memory_echo did NOT reference any era-distinct facts — "
                    "either persistence broke or memory_echo is producing "
                    "generic content"
                )
            elif recall.multi_era_count == 1:
                recall.severity = "AMBER"
                recall.fail_reasons.append(
                    f"memory_echo only references 1 era ({recall.eras_referenced[0]}) — "
                    "per-narrator memory may be limited to recent turns; "
                    "WO-LORI-ERA-RECALL-01 will address this"
                )
            else:
                recall.severity = "PASS"
        except Exception as e:
            recall.severity = "RED"
            recall.fail_reasons.append(f"recall probe threw: {e}")

        out.memory_recall = recall

        # ── 7. Voice arc divergence (lightweight summary) ──
        voice_counts: Dict[str, int] = {}
        voice_violations: Dict[str, int] = {}
        for s in out.era_steps:
            voice_counts[s.voice] = voice_counts.get(s.voice, 0) + 1
            voice_violations[s.voice] = voice_violations.get(s.voice, 0) + len(s.voice_rule_violations)
        out.voice_arc_divergence = {
            "voice_turn_counts":      voice_counts,
            "voice_rule_violations":  voice_violations,
        }

        # ── 8. Cascade severity rollup (STRICT only) ──
        red_steps = [s for s in out.era_steps if s.severity == "RED"]
        if red_steps:
            out.severity = "RED"
            for s in red_steps:
                out.fail_reasons.append(
                    f"{s.era_label}: {'; '.join(s.strict_fail_reasons)}"
                )
        if recall.severity == "RED":
            out.severity = "RED"
            out.fail_reasons.append(f"memory_recall: {'; '.join(recall.fail_reasons)}")
        elif recall.severity == "AMBER" and out.severity != "RED":
            out.severity = "AMBER"
            out.fail_reasons.append(f"memory_recall AMBER: {'; '.join(recall.fail_reasons)}")
        if out.severity not in ("RED", "AMBER"):
            out.severity = "PASS"

        try:
            self.ui.wrap_session()
        except Exception:
            pass

        return out

    # ── Runtime hygiene checks ──────────────────────────────────

    def run_runtime_hygiene(self) -> List[RuntimeHygieneCheck]:
        """Snapshot runtime71 + assert:
          - kawa_mode field absent (Lane C)
          - current_era field present (key matters even if value is null)
        """
        checks: List[RuntimeHygieneCheck] = []
        rt = get_runtime71_dump(self.page)
        if rt.get("__error"):
            checks.append(RuntimeHygieneCheck(
                name="runtime71 dump readable",
                expected="dict",
                actual=f"error: {rt.get('__error')}",
                passed=False,
            ))
            return checks

        # Lane C — kawa_mode must not appear in payload
        checks.append(RuntimeHygieneCheck(
            name="kawa_mode absent from runtime71",
            expected="absent",
            actual=("present" if "kawa_mode" in rt else "absent"),
            passed=("kawa_mode" not in rt),
        ))
        # Lane E — current_era key must be present
        checks.append(RuntimeHygieneCheck(
            name="current_era key present in runtime71",
            expected="present",
            actual=("present" if "current_era" in rt else "absent"),
            passed=("current_era" in rt),
        ))
        return checks

    # ── Cross-narrator divergence builder ───────────────────────

    def build_cross_narrator_divergence(self) -> List[Dict[str, Any]]:
        """Compare same-turn replies across voices. Per Chris's spec —
        the report row that shows whether Lori adapted register."""
        rows: List[Dict[str, Any]] = []
        if not self.report or len(self.report.voice_results) < 2:
            return rows

        # Build a turn_id → {voice_id → TurnResult} index
        idx: Dict[str, Dict[str, TurnResult]] = {}
        for vr in self.report.voice_results:
            for t in vr.turns:
                idx.setdefault(t.turn_id, {})[t.voice_id] = t

        for turn_id in ("T3", "T4"):  # the two cultural-payload turns
            row: Dict[str, Any] = {"turn_id": turn_id, "voices": {}}
            for vr in self.report.voice_results:
                t = idx.get(turn_id, {}).get(vr.voice_id)
                if not t:
                    continue
                row["voices"][vr.voice_id] = {
                    "narrator_input":  t.narrator_input,
                    "lori_reply":      t.lori_reply,
                    "question_count":  t.metrics.get("question_count"),
                    "menu_offer_count": t.metrics.get("menu_offer_count"),
                    "word_count":      t.metrics.get("word_count"),
                    "voice_rule_violations": t.voice_rule_violations,
                    "severity":        t.severity,
                    "expected_question_count_t3":
                        VOICE_RULES.get(vr.voice_id, {}).get("expected_question_count_t3"),
                }
            # Cross-check note
            cross_check = []
            shield = row["voices"].get("shield")
            if shield and turn_id == "T3":
                qc = shield.get("question_count")
                if qc == 0:
                    cross_check.append("✓ Shield T3 zero-question (sacred_silence honored)")
                else:
                    cross_check.append(f"✗ Shield T3 q_count={qc} (sacred_silence VIOLATED)")
                if shield.get("voice_rule_violations"):
                    cross_check.append(
                        f"✗ Shield T3 must-not-match violations: {shield['voice_rule_violations']}"
                    )
                else:
                    cross_check.append("✓ Shield T3 no kosher/Jewish/sacred vocabulary")
            row["cross_check"] = cross_check
            rows.append(row)
        return rows


# ═══════════════════════════════════════════════════════════════════
# REPORT BUILDERS — JSON + Markdown + Failure CSV
# ═══════════════════════════════════════════════════════════════════

def build_json_report(report: RehearsalReport) -> str:
    return json.dumps(asdict(report), indent=2, default=str)


def build_markdown_report(report: RehearsalReport) -> str:
    lines: List[str] = []
    L = lines.append

    L(f"# Parent Session Rehearsal Report")
    L("")
    L("Run:")
    L(f"- tag: `{report.tag}`")
    L(f"- date/time: {report.started_at} → {report.finished_at}")
    L(f"- stack: API={report.api_base}  UI={report.base_url}")
    L(f"- mode: `{report.mode}`")
    L(f"- commit SHA: `{report.commit_sha}`")
    L(f"- dirty tree: {'yes' if report.dirty_tree else 'no'}")
    L("")

    # ── Topline ──
    voice_failures = sum(1 for vr in report.voice_results for t in vr.turns if t.severity == "RED")
    voice_amber    = sum(1 for vr in report.voice_results for t in vr.turns if t.severity == "AMBER")
    lifemap_failures = sum(1 for r in report.lifemap_results if r.severity == "RED")
    lifemap_amber    = sum(1 for r in report.lifemap_results if r.severity == "AMBER")
    sil = report.silence_result
    silence_red = 1 if (sil and sil.severity == "RED") else 0
    silence_amber = 1 if (sil and sil.severity == "AMBER") else 0
    hygiene_red = sum(1 for h in report.runtime_hygiene if not h.passed)
    voice_rule_failures = sum(
        1 for vr in report.voice_results for t in vr.turns if t.voice_rule_violations
    )

    L("## Topline")
    L("")
    L(f"- **Overall: {report.overall}**")
    L(f"- Turns tested: {report.turns_tested}")
    L(f"- Lori response failures: {voice_failures} RED / {voice_amber} AMBER")
    L(f"- Voice-rule failures: {voice_rule_failures}")
    L(f"- Life Map failures: {lifemap_failures} RED / {lifemap_amber} AMBER")
    L(f"- Silence-cue failures: {silence_red} RED / {silence_amber} AMBER")
    L(f"- Runtime hygiene failures: {hygiene_red}")
    L("")

    # ── Critical Failures ──
    L("## Critical Failures (RED)")
    L("")
    crit_rows: List[Tuple[str, str, str, str, str, str]] = []
    for vr in report.voice_results:
        for t in vr.turns:
            if t.severity == "RED":
                expected = "; ".join(t.fail_reasons) or "discipline pass_overall=false"
                crit_rows.append((
                    f"voice/{t.turn_id}", vr.voice_id, t.turn_id,
                    "; ".join(t.fail_reasons),
                    (t.lori_reply or "").replace("\n", " ").strip()[:140],
                    expected,
                ))
    for r in report.lifemap_results:
        if r.severity == "RED":
            crit_rows.append((
                "lifemap", "—", r.era_label,
                "; ".join(r.fail_reasons),
                (r.lori_reply_text or "").replace("\n", " ").strip()[:140],
                "Lori must respond, era_id matches, no menu/compound",
            ))
    if sil and sil.severity == "RED":
        crit_rows.append((
            "silence", "—", "T7",
            "; ".join(sil.fail_reasons),
            (sil.spoken_cue_text or "").strip()[:140],
            "no spoken cue when LV_ATTENTION_CUE_TICKER=true",
        ))

    if crit_rows:
        L("| Test | Voice | Turn | Failure | Lori said | Expected |")
        L("|---|---|---|---|---|---|")
        for row in crit_rows:
            L("| " + " | ".join(c.replace("|", "\\|") for c in row) + " |")
    else:
        L("_No RED failures._")
    L("")

    # ── Per-Turn Results ──
    L("## Per-Turn Results")
    L("")
    L("| Voice | Turn | Type | Narrator input | Lori reply | Q | Nest | Menu | Words | Refl | Voice rule | Pass |")
    L("|---|---|---|---|---|---:|---:|---:|---:|---|---|---|")
    for vr in report.voice_results:
        for t in vr.turns:
            m = t.metrics or {}
            voice_rule_summary = (
                "✗ " + ", ".join(t.voice_rule_violations[:2])
                if t.voice_rule_violations
                else "✓"
            )
            # Lane G.1 — bumped narrator_input from 60→100 + lori_reply
            # from 80→200 char display width. Previous truncation was
            # too short to distinguish nearby Lori replies (caused
            # rehearsal_quick_v1 T3/T4 to look identical at a glance
            # even when the underlying capture was correct).
            L("| " + " | ".join(str(x).replace("|", "\\|").replace("\n", " ").strip() for x in [
                vr.voice_id, t.turn_id, t.prompt_type,
                (t.narrator_input or "")[:100],
                (t.lori_reply or "")[:200],
                m.get("question_count", "—"),
                m.get("nested_question_count", "—"),
                m.get("menu_offer_count", "—"),
                m.get("word_count", "—"),
                "✓" if m.get("active_reflection_present") else "✗",
                voice_rule_summary,
                t.severity,
            ]) + " |")
    L("")

    # ── Life Map Results ──
    L("## Life Map Results")
    L("")
    L("| Era clicked | UI active | session.currentEra | Lori replied | Era appropriate | Q | Menu | Pass |")
    L("|---|---|---|---|---|---:|---:|---|")
    for r in report.lifemap_results:
        m = r.metrics or {}
        L("| " + " | ".join(str(x).replace("|", "\\|").replace("\n", " ").strip() for x in [
            f"{r.era_label} ({r.era_id})",
            "✓" if r.ui_active else "✗",
            r.session_current_era or "(empty)",
            "✓" if r.lori_replied else "✗",
            "✓" if r.era_appropriate else "✗",
            m.get("question_count", "—"),
            m.get("menu_offer_count", "—"),
            r.severity,
        ]) + " |")
    L("")

    # ── Silence / Presence Cue Results ──
    L("## Silence / Presence Cue Results")
    L("")
    if sil:
        L("| Pause | Visual cue present | Cue text | Spoken cue fired | Transcript-ignore | idle_fire_blocked log | Pass |")
        L("|---:|---|---|---|---|---|---|")
        L("| " + " | ".join(str(x).replace("|", "\\|") for x in [
            f"{sil.pause_seconds}s",
            "✓" if sil.visual_cue_present else "✗",
            (sil.visual_cue_text or "")[:60],
            "✗ FIRED" if sil.spoken_cue_fired else "✓ suppressed",
            "✓" if sil.transcript_ignored else "✗",
            "✓" if sil.idle_block_log_seen else "✗",
            sil.severity,
        ]) + " |")
    else:
        L("_(silence test not run)_")
    L("")

    # ── Shatner Life Map Cascade (TEST-21) ──
    sc = report.shatner_cascade
    L("## Shatner Life Map Cascade (TEST-21)")
    L("")
    if not sc:
        L("_(cascade not run)_")
        L("")
    else:
        # Setup row
        L("**Setup**")
        L("")
        L("| Check | Value |")
        L("|---|---|")
        L(f"| Narrator added | {'✓' if sc.narrator_added else '✗'} ({sc.narrator_name or '—'}) |")
        L(f"| person_id | {(sc.narrator_person_id or '—')[:12]} |")
        L(f"| Identity complete | {'✓' if sc.identity_complete else '✗'}{' — ' + sc.identity_fail_reason if sc.identity_fail_reason else ''} |")
        L(f"| Cascade severity | **{sc.severity}** |")
        L("")
        # STRICT — Life Map click chain (drives RED)
        L("**STRICT — Life Map click chain**")
        L("")
        L("| Era | Clicked | Click log | Lori prompt log | currentEra | Lori replied | Lori clean | Q | Nest | Menu | Severity |")
        L("|---|---|---|---|---|---|---|---:|---:|---:|---|")
        for step in (sc.today, sc.coming_of_age):
            if not step:
                continue
            m = step.metrics or {}
            L("| " + " | ".join(str(x).replace("|", "\\|").replace("\n", " ").strip() for x in [
                f"{step.era_label} ({step.era_id})",
                "✓" if step.clicked_ok else "✗",
                "✓" if step.era_click_log_seen else "✗",
                "✓" if step.lori_prompt_log_seen else "✗",
                step.session_current_era or "(empty)",
                "✓" if step.lori_replied else "✗",
                "✓" if step.lori_clean else "✗",
                m.get("question_count", "—"),
                m.get("nested_question_count", "—"),
                m.get("menu_offer_count", "—"),
                step.severity,
            ]) + " |")
        L("")
        # INFORMATIONAL — Timeline + Memoir downstream subscribers
        L("**INFORMATIONAL — Timeline + Memoir downstream subscribers** _(known gap, never RED)_")
        L("")
        L("| Era | Timeline active | Memoir top heading | Memoir excerpt | Notes |")
        L("|---|---|---|---|---|")
        for step in (sc.today, sc.coming_of_age):
            if not step:
                continue
            notes_str = "; ".join(step.info_notes) if step.info_notes else "—"
            L("| " + " | ".join(str(x).replace("|", "\\|").replace("\n", " ").strip() for x in [
                f"{step.era_label} ({step.era_id})",
                step.timeline_active_era_id or "(empty)",
                (step.memoir_top_section_text or "—")[:60],
                (step.memoir_excerpt or "—")[:80],
                notes_str[:120],
            ]) + " |")
        L("")
        if sc.fail_reasons:
            L("**Strict failure reasons:**")
            L("")
            for r in sc.fail_reasons:
                L(f"- {r}")
            L("")
        if sc.downstream_wiring_known_gap:
            L("> **Downstream subscriber note:** Timeline (chronology accordion) and "
              "Peek at Memoir (popover) do NOT auto-react to era-click events today. "
              "The `lv-interview-focus-change` CustomEvent is dispatched but has zero "
              "subscribers in the codebase. This is a known gap tracked as "
              "**WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01** and is INTENTIONALLY surfaced "
              "as informational AMBER, not RED, so it does not falsely fail the "
              "Life Map quote-fix verification.")
            L("")

    # ── Long-Life Multi-Voice Cascade (TEST-22) ──
    llc = report.long_life_cascade
    L("## TEST-22 — Long-Life Multi-Voice Cascade")
    L("")
    if not llc:
        L("_(cascade not run — pass --include-long-life to enable)_")
        L("")
    else:
        L("**Setup**")
        L("")
        L("| Check | Value |")
        L("|---|---|")
        L(f"| Narrator added | {'✓' if llc.narrator_added else '✗'} ({llc.narrator_name or '—'}) |")
        L(f"| person_id | {(llc.narrator_person_id or '—')[:12]} |")
        L(f"| Identity complete | {'✓' if llc.identity_complete else '✗'}{' — ' + llc.identity_fail_reason if llc.identity_fail_reason else ''} |")
        L(f"| Total era steps | {len(llc.era_steps)} |")
        L(f"| Cascade severity | **{llc.severity}** |")
        L("")
        # STRICT — Era click chain
        L("**STRICT — Era click chain** _(per era; drives RED)_")
        L("")
        L("| Era | Voice | Click | Click log | Prompt log | currentEra | activeFocus | Lori re-engaged | Era-anchored | Q | Nest | Menu | Voice rule | Severity |")
        L("|---|---|---|---|---|---|---|---|---|---:|---:|---:|---|---|")
        for s in llc.era_steps:
            m = s.click_metrics or {}
            voice_rule_str = (
                "✗ " + ", ".join(s.voice_rule_violations[:2])
                if s.voice_rule_violations else "✓"
            )
            L("| " + " | ".join(str(x).replace("|", "\\|").replace("\n", " ").strip() for x in [
                f"{s.era_label} ({s.era_id})",
                s.voice,
                "✓" if s.clicked_ok else "✗",
                "✓" if s.era_click_log_seen else "✗",
                "✓" if s.lori_prompt_log_seen else "✗",
                s.state_currentEra or "(empty)",
                s.state_activeFocusEra or "(empty)",
                "✓" if s.click_lori_replied else "✗",
                "✓" if s.click_lori_era_anchored else "—",
                m.get("question_count", "—"),
                m.get("nested_question_count", "—"),
                m.get("menu_offer_count", "—"),
                voice_rule_str,
                s.severity,
            ]) + " |")
        L("")
        # Per-era seed + replies (truncated)
        L("**Era seed turns + Lori replies**")
        L("")
        L("| Era | Voice | Seed (excerpt) | Lori to seed (excerpt) | Lori to re-click (excerpt) |")
        L("|---|---|---|---|---|")
        for s in llc.era_steps:
            L("| " + " | ".join(str(x).replace("|", "\\|").replace("\n", " ").strip() for x in [
                f"{s.era_label}",
                s.voice,
                (s.seed_text or "")[:60],
                (s.seed_lori_reply or "—")[:80],
                (s.click_lori_reply or "—")[:80],
            ]) + " |")
        L("")
        # INFORMATIONAL — downstream cohesion
        L("**INFORMATIONAL — Downstream cohesion** _(known gap pre-WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01; never RED)_")
        L("")
        L("| Era | Timeline active | Memoir section | Memoir top heading | Notes |")
        L("|---|---|---|---|---|")
        for s in llc.era_steps:
            notes_str = "; ".join(s.info_notes) if s.info_notes else "—"
            L("| " + " | ".join(str(x).replace("|", "\\|").replace("\n", " ").strip() for x in [
                f"{s.era_label}",
                s.timeline_active_era_id or "(empty)",
                "✓" if s.memoir_section_present else "✗",
                (s.memoir_top_heading or "—")[:60],
                notes_str[:140],
            ]) + " |")
        L("")
        # Memory recall
        L("**Memory Recall — end-of-arc**")
        L("")
        if llc.memory_recall:
            mr = llc.memory_recall
            L("| Probe | Lori response (excerpt) | Eras referenced | Multi-era count | Severity |")
            L("|---|---|---|---:|---|")
            L("| " + " | ".join(str(x).replace("|", "\\|").replace("\n", " ").strip() for x in [
                mr.sent_text,
                (mr.response or "—")[:140],
                "; ".join(mr.eras_referenced) if mr.eras_referenced else "(none detected)",
                mr.multi_era_count,
                mr.severity,
            ]) + " |")
            if mr.fail_reasons:
                L("")
                for r in mr.fail_reasons:
                    L(f"- {r}")
        L("")
        # Voice arc divergence
        L("**Voice Arc Divergence**")
        L("")
        if llc.voice_arc_divergence:
            counts = llc.voice_arc_divergence.get("voice_turn_counts") or {}
            violations = llc.voice_arc_divergence.get("voice_rule_violations") or {}
            L("| Voice | Era turns | Voice-rule violations |")
            L("|---|---:|---:|")
            for v in sorted(counts.keys()):
                L(f"| {v} | {counts[v]} | {violations.get(v, 0)} |")
        L("")
        if llc.fail_reasons:
            L("**Cascade failure reasons:**")
            L("")
            for r in llc.fail_reasons:
                L(f"- {r}")
            L("")

    # ── Cross-Narrator Divergence ──
    L("## Cross-Narrator Divergence")
    L("")
    if not report.cross_divergence:
        L("_(only one voice ran — no divergence comparison)_")
    else:
        for row in report.cross_divergence:
            L(f"### Turn {row['turn_id']}")
            L("")
            L("| Voice | Q count | Menu | Words | Voice rule | Severity | Lori reply (excerpt) |")
            L("|---|---:|---:|---:|---|---|---|")
            for vid, v in row["voices"].items():
                voice_rule = (
                    "✗ " + ", ".join(v["voice_rule_violations"][:2])
                    if v["voice_rule_violations"]
                    else "✓"
                )
                expected_qc = v.get("expected_question_count_t3")
                qc_str = (
                    f"{v['question_count']} (expected {expected_qc})"
                    if (expected_qc is not None and row['turn_id'] == "T3")
                    else str(v.get("question_count", "—"))
                )
                L("| " + " | ".join(str(x).replace("|", "\\|").replace("\n", " ").strip() for x in [
                    vid,
                    qc_str,
                    v.get("menu_offer_count", "—"),
                    v.get("word_count", "—"),
                    voice_rule,
                    v.get("severity", "—"),
                    (v.get("lori_reply", "") or "")[:80],
                ]) + " |")
            L("")
            for note in row.get("cross_check", []):
                L(f"- {note}")
            L("")

    # ── Runtime Hygiene ──
    L("## Runtime Hygiene")
    L("")
    L("| Check | Expected | Actual | Pass |")
    L("|---|---|---|---|")
    for h in report.runtime_hygiene:
        L("| " + " | ".join(str(x).replace("|", "\\|") for x in [
            h.name, h.expected, h.actual, "✓" if h.passed else "✗",
        ]) + " |")
    L("")

    # ── Recommended Fix List ──
    L("## Recommended Fix List")
    L("")
    if report.fix_list:
        for i, fix in enumerate(report.fix_list, 1):
            L(f"{i}. {fix}")
    else:
        L("_No fixes recommended — all checks passed or only AMBER findings._")
    L("")

    return "\n".join(lines)


def build_failure_csv(report: RehearsalReport) -> str:
    """Sortable failure rows. severity, voice, turn, fail_reason,
    lori_excerpt, narrator_input."""
    rows: List[List[str]] = [
        ["severity", "kind", "voice", "turn", "fail_reason", "narrator_input", "lori_reply_excerpt"],
    ]
    for vr in report.voice_results:
        for t in vr.turns:
            if t.severity != "PASS":
                rows.append([
                    t.severity,
                    "voice_turn",
                    vr.voice_id,
                    t.turn_id,
                    "; ".join(t.fail_reasons),
                    (t.narrator_input or "").replace("\n", " ")[:120],
                    (t.lori_reply or "").replace("\n", " ")[:200],
                ])
    for r in report.lifemap_results:
        if r.severity != "PASS":
            rows.append([
                r.severity,
                "lifemap",
                "—",
                r.era_label,
                "; ".join(r.fail_reasons),
                f"[click {r.era_label}]",
                (r.lori_reply_text or "").replace("\n", " ")[:200],
            ])
    sil = report.silence_result
    if sil and sil.severity != "PASS":
        rows.append([
            sil.severity,
            "silence",
            "—",
            "T7",
            "; ".join(sil.fail_reasons),
            "[silence pause]",
            sil.spoken_cue_text[:200],
        ])
    for h in report.runtime_hygiene:
        if not h.passed:
            rows.append([
                "RED",
                "hygiene",
                "—",
                h.name,
                f"expected={h.expected} actual={h.actual}",
                "",
                "",
            ])

    out = []
    w = csv.writer(_StringIOWriter(out))
    for row in rows:
        w.writerow(row)
    return "".join(out)


class _StringIOWriter:
    """Minimal file-like wrapper so csv.writer can emit into a list."""
    def __init__(self, out: List[str]) -> None:
        self.out = out
    def write(self, s: str) -> int:
        self.out.append(s)
        return len(s)


def build_fix_list(report: RehearsalReport) -> List[str]:
    """Synthesize the recommended-fix list from RED findings."""
    fixes: List[str] = []
    seen: set = set()
    for vr in report.voice_results:
        for t in vr.turns:
            if t.severity == "RED" and t.voice_rule_violations:
                key = f"{vr.voice_id}_voice_rule"
                if key not in seen:
                    seen.add(key)
                    fixes.append(
                        f"Audit Lori discipline for {vr.voice_id} voice — "
                        f"{len(t.voice_rule_violations)} voice-rule violation(s) on T{t.turn_id[-1]}: "
                        f"{', '.join(t.voice_rule_violations[:3])}"
                    )
            if t.severity == "RED" and "menu_offer" in " ".join(t.fail_reasons).lower():
                if "menu_offer" not in seen:
                    seen.add("menu_offer")
                    fixes.append(
                        "Layer 2 discipline filter trim missed a menu offer — "
                        "audit composer call site for the affected turn intent"
                    )
    sil = report.silence_result
    if sil and sil.spoken_cue_fired:
        fixes.append(
            "RED — old [SYSTEM: quiet for a while] injector fired despite Phase 3 gate. "
            "Re-verify lv80FireCheckIn() guard (hornelore1.0.html) and ensure ticker "
            "actually started before the silence test ran."
        )
    for r in report.lifemap_results:
        if r.severity == "RED" and not r.lori_replied:
            fixes.append(
                f"BUG-LIFEMAP-ERA-CLICK-NO-LORI-01 regression — era {r.era_id} clicked "
                f"but Lori produced no reply. Check _lvInterviewSelectEra sendSystemPrompt path."
            )
            break
    for h in report.runtime_hygiene:
        if not h.passed and "kawa" in h.name:
            fixes.append("Kawa scrub regression — kawa_mode reappeared in runtime71. Re-check Lane C.")
        if not h.passed and "current_era" in h.name:
            fixes.append("current_era key missing from runtime71 — extract.py current_era plumbing broken.")
    return fixes


# ═══════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--tag", required=True, help="run identifier (e.g. rehearsal_v1)")
    parser.add_argument("--mode", choices=["quick", "standard", "full"], default="standard")
    parser.add_argument("--base-url", default="http://localhost:8082/ui/hornelore1.0.html")
    parser.add_argument("--api", dest="api_base", default="http://localhost:8000")
    parser.add_argument("--word-cap", type=int, default=55,
                        help="word_count cap for clear_direct (default 55)")
    parser.add_argument("--output-dir", default="docs/reports")
    parser.add_argument("--headless", action="store_true",
                        help="run Playwright headless (default: headed)")
    parser.add_argument("--slow-mo-ms", type=int, default=100)
    parser.add_argument("--include-long-life", action="store_true",
                        help="run TEST-22 (long-life multi-voice cascade) — "
                             "adds ~5 minutes to wall clock; skip in --quick "
                             "if you only want fast feedback")
    args = parser.parse_args()

    repo_root = _REPO_ROOT
    out_dir = repo_root / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path     = out_dir / f"parent_rehearsal_{args.tag}.json"
    md_path       = out_dir / f"parent_rehearsal_{args.tag}.md"
    csv_path      = out_dir / f"parent_rehearsal_{args.tag}_failures.csv"
    screenshots_dir = out_dir / f"parent_rehearsal_{args.tag}_screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir = out_dir / f"parent_rehearsal_{args.tag}_downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    sha, dirty = get_git_sha(repo_root)
    report = RehearsalReport(
        tag=args.tag,
        mode=args.mode,
        started_at=dt.datetime.now().isoformat(),
        base_url=args.base_url,
        api_base=args.api_base,
        commit_sha=sha,
        dirty_tree=dirty,
    )

    voice_ids = VOICE_LADDER.get(args.mode, ["hearth"])
    print(f"[rehearsal] tag={args.tag} mode={args.mode} voices={voice_ids}")
    print(f"[rehearsal] commit={sha} dirty={dirty}")
    print(f"[rehearsal] reports → {out_dir}/")

    with sync_playwright() as pw:
        browser: Browser = pw.chromium.launch(
            headless=args.headless, slow_mo=args.slow_mo_ms,
        )
        context: BrowserContext = browser.new_context(accept_downloads=True)
        page: Page = context.new_page()
        console = ConsoleCollector(page)
        ui = UI(page, console, screenshots_dir, downloads_dir)
        dblock = DbLockCounter(repo_root)

        # ── Boot ──
        try:
            ui.boot(args.base_url)
            ui.ensure_operator_tab()
            ui.ensure_life_story_posture()
            ui.ready_for_session()
        except Exception as e:
            print(f"FATAL: boot failed: {e}", file=sys.stderr)
            report.overall = "RED"
            report.finished_at = dt.datetime.now().isoformat()
            json_path.write_text(build_json_report(report))
            md_path.write_text(build_markdown_report(report))
            csv_path.write_text(build_failure_csv(report))
            browser.close()
            return 2

        # ── Enable Phase 3 ticker for the whole rehearsal ──
        ticker_on = enable_attention_cue_ticker(page)
        print(f"[rehearsal] LV_ATTENTION_CUE_TICKER={ticker_on}")
        if not ticker_on:
            report.fix_list.append(
                "WARN: LV_ATTENTION_CUE_TICKER could not be enabled — silence test "
                "results may not reflect Phase 3 gate behavior."
            )

        # ── Build runner ──
        runner = RehearsalRun(
            ui=ui, console=console, dblock=dblock, page=page,
            mode=args.mode, word_cap=args.word_cap,
        )
        runner.report = report

        # ── Lane G.1 fix #4 — wait for stack warm before T1 ──
        # rehearsal_quick_v1 had T1 timeout because the harness sent
        # before _llmReady=true. Block here up to 90s.
        warm = runner.wait_for_warm_stack(timeout_s=90)
        if not warm:
            report.fix_list.append(
                "WARN: stack not confirmed warm before T1 — first turn may "
                "still time out. Wait for the [readiness] log line then re-run."
            )

        # ── Per-voice rehearsal ──
        for vid in voice_ids:
            print(f"[rehearsal] === voice: {vid} ===")
            vr = runner.run_voice(vid)
            report.voice_results.append(vr)

        # ── Life Map cycle ──
        if args.mode == "quick":
            print(f"[rehearsal] === Life Map (quick — one era only) ===")
            report.lifemap_results = runner.run_life_map_cycle(
                "hearth", eras_subset=["Coming of Age"],
            )
        else:
            print(f"[rehearsal] === Life Map era cycle (all 7) ===")
            report.lifemap_results = runner.run_life_map_cycle("hearth")

        # ── Silence test ──
        print(f"[rehearsal] === Silence / presence cue ===")
        report.silence_result = runner.run_silence_test("hearth", pause_seconds=30)

        # ── Shatner Life Map cascade (TEST-21) ──
        # End-to-end probe of the Life Map quote-fix: identity →
        # Today click → Coming of Age click. Strict gates on the
        # click chain; Timeline + Memoir reported as informational
        # (downstream subscribers not yet wired —
        # WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01).
        print(f"[rehearsal] === Shatner Life Map cascade (TEST-21) ===")
        try:
            report.shatner_cascade = runner.run_shatner_cascade()
        except Exception as e:
            print(f"[rehearsal] WARN — Shatner cascade threw: {e}", file=sys.stderr)
            report.shatner_cascade = ShatnerCascadeResult(
                severity="RED",
                fail_reasons=[f"cascade threw: {e}"],
            )

        # ── TEST-22 — Long-life multi-voice cascade (opt-in) ──
        # Per WO-PARENT-SESSION-LONG-LIFE-HARNESS-01_Spec.md.
        # Closest synthetic to a real Janice/Kent session: composite
        # 200-year-old narrator (Esther Ridley-Yamamoto-Cordova),
        # 7-era arc with voice rotation, end-of-arc memory recall.
        # Adds ~5 min wall clock — opt-in via --include-long-life.
        if args.include_long_life:
            print(f"[rehearsal] === Long-Life multi-voice cascade (TEST-22) ===")
            try:
                report.long_life_cascade = runner.run_long_life_cascade()
            except Exception as e:
                print(f"[rehearsal] WARN — Long-Life cascade threw: {e}", file=sys.stderr)
                report.long_life_cascade = LongLifeCascadeResult(
                    severity="RED",
                    fail_reasons=[f"cascade threw: {e}"],
                )

        # ── Runtime hygiene ──
        print(f"[rehearsal] === Runtime hygiene (kawa scrub + current_era) ===")
        report.runtime_hygiene = runner.run_runtime_hygiene()

        # ── Cross-narrator divergence ──
        if len(voice_ids) > 1:
            report.cross_divergence = runner.build_cross_narrator_divergence()

        # ── Tally ──
        report.turns_tested = sum(len(vr.turns) for vr in report.voice_results)

        # Overall severity rollup
        any_red = (
            any(vr.severity == "RED" for vr in report.voice_results) or
            any(r.severity == "RED" for r in report.lifemap_results) or
            (report.silence_result and report.silence_result.severity == "RED") or
            (report.shatner_cascade and report.shatner_cascade.severity == "RED") or
            (report.long_life_cascade and report.long_life_cascade.severity == "RED") or
            any(not h.passed for h in report.runtime_hygiene)
        )
        any_amber = (
            any(vr.severity == "AMBER" for vr in report.voice_results) or
            any(r.severity == "AMBER" for r in report.lifemap_results) or
            (report.silence_result and report.silence_result.severity == "AMBER") or
            (report.shatner_cascade and report.shatner_cascade.severity == "AMBER") or
            (report.long_life_cascade and report.long_life_cascade.severity == "AMBER")
        )
        if any_red:
            report.overall = "RED"
        elif any_amber:
            report.overall = "AMBER"
        else:
            report.overall = "PASS"

        report.fix_list.extend(build_fix_list(report))
        report.finished_at = dt.datetime.now().isoformat()

        json_path.write_text(build_json_report(report))
        md_path.write_text(build_markdown_report(report))
        csv_path.write_text(build_failure_csv(report))

        try:
            browser.close()
        except Exception:
            pass

    print()
    print(f"[rehearsal] done — overall={report.overall}")
    print(f"  json: {json_path}")
    print(f"  md:   {md_path}")
    print(f"  csv:  {csv_path}")
    print()
    print(md_path.read_text())

    return 0 if report.overall in ("PASS", "AMBER") else 1


if __name__ == "__main__":
    sys.exit(main())
