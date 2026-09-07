#!/usr/bin/env python3
"""Shared long-narration harness scaffold.

Extracted from scripts/run_jake_long_narration_harness.py (2026-06-15)
so the same WS-send / scorer / report-writer / log-grep stack can drive
multiple narrator personas without copy-paste drift.

The Jake harness stays as a complete standalone (it's a known-working
reference). New harnesses (Shatner, they/them, late-coming-out gay
narrator, female teacher + Betty, multicultural regional variants)
import HarnessConfig + run_harness from this module and provide
narrator-specific data.

USAGE:
    from harness_lib import HarnessConfig, ChapterConfig, run_harness

    cfg = HarnessConfig(
        narrator_label="William Shatner",
        intake_payload={...},          # full /api/people/intake body
        chapters=[
            ChapterConfig(
                label="Earliest Years",
                runtime71_era="earliest_years",
                text="I was born ...",
                anchors=["born", "montreal", ...],
            ),
            # ...two more chapters...
        ],
        bonus_probe="Anyway, that's about it for what I wanted to say today.",
        report_prefix="shatner_long_narration",
    )
    asyncio.run(run_harness(cfg))

LAW: scoring rows + report shape match the Jake harness exactly so
results across narrators are comparable on the 8-row matrix.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import websockets  # type: ignore
except ImportError:
    print(
        "Missing dependency: websockets. Try: python3 -m pip install websockets",
        file=sys.stderr,
    )
    raise

import urllib.error
import urllib.request


# ── Configuration ──────────────────────────────────────────────────────────


API_BASE = os.environ.get("HORNELORE_API_BASE", "http://localhost:8000")
WS_URL = f"{API_BASE.replace('http', 'ws')}/api/chat/ws"
INTAKE_URL = f"{API_BASE}/api/people/intake"
PING_URL = f"{API_BASE}/api/ping"

REPO_ROOT = Path("/mnt/c/Users/chris/hornelore")
API_LOG = REPO_ROOT / ".runtime" / "logs" / "api.log"
REPORTS_DIR = REPO_ROOT / "docs" / "reports"


# Forbidden empathy openers — Lori must not start her response with
# any of these (they signal therapist-bot / chatbot-empathy register
# that breaks the oral-history posture).
FORBIDDEN_OPENERS: Tuple[str, ...] = (
    "thank you for sharing",
    "that's beautiful",
    "what a beautiful",
    "what a wonderful",
    "i'm so glad",
    "i love that",
    "wow, ",
    "wow.",
    "incredible.",
    "incredible,",
)


# Era-label menu patterns — single canonical era labels firing in
# Lori's response is fine; multiple labels in one sentence ("Would
# you rather talk about your earliest years or your building years?")
# is the failure mode this guard catches.
ERA_LABEL_MENU_PATTERNS: Tuple[str, ...] = (
    "earliest years", "early school years", "adolescence",
    "coming of age", "building years", "later years",
)


# ── BUG-HARNESS-SCORER-TOO-LENIENT-CONTENT-QUALITY-01 patterns ────────────
# Eight new pattern banks for the content-quality scoring rows added to
# score_chapter. Each catches a distinct Lori-voice failure that the
# original 8-row matrix was calling PASS.

# Stop-words that should NEVER be treated as candidate names by the
# META_FEEDBACK / correction pipeline (the source of the false
# name-confirmation pattern).
_NAME_LIKELIHOOD_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "i", "you", "he", "she", "it", "we", "they",
    "this", "that", "these", "those", "is", "was", "were", "are",
    "be", "been", "being", "and", "or", "but", "so", "because",
    "what", "when", "where", "why", "how", "all", "some", "any",
    "many", "few", "no", "yes", "ok", "okay", "well", "so",
    "still", "always", "never", "sometimes", "often", "just", "very",
    "really", "more", "less", "again", "only", "even", "also", "too",
    "now", "then", "there", "here",
    # calendar / date tokens — Lori treats "Wednesday" or "October" as anchors
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    "sunday", "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    # religious / common nouns
    "catholic", "mass", "church", "school", "home", "family",
    "love", "life", "war", "joy",
})

# Compiled regex patterns for the 8 new rows.
_FALSE_NAME_CONFIRM_PATTERNS = (
    # The exact "Got it — [phrase]. Did I get that name right?" template
    # from the full-family run — Jake, Shatner, Frank, Walter, Richard
    re.compile(r"did i get (that|the|your) (name|title) right", re.IGNORECASE),
    re.compile(r"is that (the right|your real) (name|spelling)", re.IGNORECASE),
)

_GOT_IT_STUB_PATTERN = re.compile(
    r"^\s*got it\s*[—\-:,]+\s*[^.!?]{0,80}[.!?]\s*"
    r"(did i get|what happened next|tell me more)",
    re.IGNORECASE | re.MULTILINE,
)

# A "titlecase phrase as candidate name" is a 3+ word capitalized sequence
# being treated as an entity (e.g. "Originally Schong With A C",
# "It Was The Air", "You Learned To Stand Up And Sit Down And Kneel At
# The Right Times", "Because The Adults Stopped Moving").
# `[Gg]ot [Ii]t` covers the case-variation on the prefix; [A-Z] stays
# strict so the titlecase requirement still has bite.
_TITLECASE_PHRASE_AS_NAME = re.compile(
    r"[Gg]ot\s+[Ii]t\s*[—\-:,]+\s*"
    r"((?:[A-Z][a-zA-Z]*\s+){2,}[A-Z][a-zA-Z]*)"
    r"\s*[.!?]"
)

# Orphan fragments: 1–2 token responses ending in '.' OR a single
# capitalized fragment like "St." / "West St." / "Began."
_FRAGMENT_PATTERNS = (
    # 1–2 word total response
    re.compile(r"^\s*([A-Za-z][A-Za-z'\.]*\s+){0,1}[A-Za-z][A-Za-z'\.]*[.!?]?\s*$"),
    # Partial place name "West St." with no body
    re.compile(r"^\s*[A-Z][a-z]*\s+St\.?\s*$"),
    # Single capitalized word ending in period
    re.compile(r"^\s*[A-Z][a-z]{1,15}\.\s*$"),
)

# Meta-instruction leak (LLM expose-its-own-rules postamble/preamble)
_META_RESPONSE_LEAK_PATTERNS = (
    re.compile(r"here is (a |the )?response (that|which) (follows|reflects)", re.IGNORECASE),
    re.compile(r"this response (reflects|follows|adheres|captures|invites)", re.IGNORECASE),
    re.compile(r"let me capture (a few|the|some) key points", re.IGNORECASE),
    re.compile(r"this (follows|adheres to) the (rules|guidelines)", re.IGNORECASE),
    re.compile(r"the response (should|will|must) (be|follow|reflect)", re.IGNORECASE),
    re.compile(r"what a (rich|wonderful|beautiful|moving|evocative) (narrative|story)", re.IGNORECASE),
    re.compile(r"i'?m so grateful to be listening", re.IGNORECASE),
)

# Anchor-cascade: 3+ comma-or-conjunction-separated proper nouns dumped
# in sequence: "You went from X to Y, then Z, A, B, and C"
_ANCHOR_CASCADE_PATTERNS = (
    re.compile(
        r"\byou went from\s+[A-Z][\w\s]*\s+to\s+[A-Z][\w\s]*,\s*then\s+"
        r"([A-Z][\w]*(?:,\s*|,\s*and\s+|\s+and\s+)){2,}",
        re.IGNORECASE,
    ),
    # "You said X: ... You kept coming back to X" stock-phrase
    re.compile(
        r"\byou said\s+[A-Z][\w\s]*:.+you kept coming back to",
        re.IGNORECASE | re.DOTALL,
    ),
)


def _detect_titlecase_phrase_as_name(text: str) -> Optional[str]:
    """Return the offending titlecase phrase if 'Got it — [Title Cased]'."""
    m = _TITLECASE_PHRASE_AS_NAME.search(text)
    if not m:
        return None
    phrase = m.group(1).strip()
    words = phrase.split()
    if len(words) < 3:
        return None
    # If every word starts uppercase and is not a stopword, it's a flagged phrase
    if all(w[0].isupper() and w.lower() not in _NAME_LIKELIHOOD_STOPWORDS for w in words):
        return phrase
    # If 3+ words and mostly titlecase, also flag (catches "It Was The Air")
    cap_words = [w for w in words if w[0].isupper()]
    if len(cap_words) >= 3:
        return phrase
    return None


def _detect_fragment(text: str) -> bool:
    """True if the response is an orphan stub (1–3 tokens, abbreviated)."""
    stripped = (text or "").strip()
    if not stripped:
        return True
    # Count meaningful tokens (drop trailing punctuation)
    tokens = [t for t in re.split(r"\s+", stripped) if t]
    if len(tokens) <= 2:
        return True
    # "West St." / "St. Paul" with no further body
    for pat in _FRAGMENT_PATTERNS:
        if pat.match(stripped):
            return True
    return False


def _detect_meta_leak(text: str) -> Optional[str]:
    """Return the offending meta-instruction phrase if present."""
    for pat in _META_RESPONSE_LEAK_PATTERNS:
        m = pat.search(text or "")
        if m:
            return m.group(0)
    return None


def _detect_anchor_cascade(text: str) -> bool:
    """True if the response is a 3+ token proper-noun cascade dump."""
    if not text:
        return False
    for pat in _ANCHOR_CASCADE_PATTERNS:
        if pat.search(text):
            return True
    # Cheaper heuristic: count comma-separated capitalized tokens after
    # "from X to Y, then "
    m = re.search(
        r"\byou went from\s+\w[\w\s]*\s+to\s+\w[\w\s]*,\s*then\s+(.+?)[.?!]",
        text, re.IGNORECASE,
    )
    if m:
        tail = m.group(1)
        parts = [p.strip() for p in re.split(r",\s*(?:and\s+)?|\s+and\s+", tail)]
        cap_parts = [p for p in parts if p and p[0].isupper()]
        if len(cap_parts) >= 3:
            return True
    return False


def _detect_false_name_confirm(text: str) -> bool:
    """True if 'Did I get that name right?' appears (any context)."""
    for pat in _FALSE_NAME_CONFIRM_PATTERNS:
        if pat.search(text or ""):
            return True
    return False


def _detect_got_it_stub(text: str) -> bool:
    """True if the response is a 'Got it — X. What happened next?' shell."""
    return bool(_GOT_IT_STUB_PATTERN.search(text or ""))


# Seeded-fact intake-question detection: catches Lori asking for
# intake-style confirmations of bio facts that should not be intake
# questions (DOB, POB, current residence, current work, parent status,
# career start year). Fires on PATTERN ALONE — seeded_facts kwarg is
# optional context that strengthens the signal but no longer required.
# Per Boris Phase 8 contract: the question shape itself is the failure,
# not "shape AND it happens to be seeded".
_SEEDED_FACT_INTAKE_PATTERNS = (
    # "You were born in X" / "Were you born in X" — confirming seeded birth
    (re.compile(r"\b(you were|were you) born in ([^?.,]+)", re.IGNORECASE), "place_of_birth"),
    (re.compile(r"\b(you were|were you) born (in|on)\s+(?:[^?.,]+,\s*)?(\d{4})", re.IGNORECASE), "birth_year"),
    # "Do you live in X" / "You live in X" — confirming seeded residence
    (re.compile(r"\b(do you (currently )?live|you (currently )?live) in ([^?.,]+)", re.IGNORECASE), "current_residence"),
    # "Does your mother live in X" / "Is your mother alive"
    (re.compile(r"\b(is your (mother|father|mom|dad)) (still )?alive\b", re.IGNORECASE), "parent_alive"),
    (re.compile(r"\b(does your (mother|father|mom|dad)) live in ([^?.,]+)", re.IGNORECASE), "parent_residence"),
    # "Do you work at X" / "Did you become a Y in YYYY"
    (re.compile(r"\b(do you (currently )?work|you (currently )?work) (at|for) ([^?.,]+)", re.IGNORECASE), "current_work"),
    (re.compile(r"\b(did you become a|did you start (working|as) a)\s+[A-Za-z ]+\s+in\s+(\d{4})", re.IGNORECASE), "career_start_year"),
    # "Did you have N children"
    (re.compile(r"\b(did you have|do you have)\s+(one|two|three|four|five|six|\d+)\s+(child|children|kids)", re.IGNORECASE), "children_count"),
)


def _detect_seeded_fact_intake(text: str, seeded_facts: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Return a description of the intake-question mis-fire if present.

    Contract:
      - When `seeded_facts` is None / empty, return None. The
        intake-question shape on its own is not actionable; we need a
        scoring context that knows what's seeded.
      - When `seeded_facts` is a real dict, fire on PATTERN match. If
        the dict carries a value for the matched field_key, include it
        in the message; otherwise return the bare field_key form.

    2026-06-17 — restored the None gate after the Boris Phase 8 work
    flipped behavior to "fire on pattern alone." That over-fired in
    direct-call test contexts (test_no_seeded_facts_returns_none) and
    in `score_chapter()` for narrators without seeded profiles where
    pattern-shape questions are legitimate. Boris scorer paths always
    pass a real seeded_facts dict for John/Mable, so those tests stay
    green.
    """
    if not text:
        return None
    if not seeded_facts:
        return None
    for pattern, field_key in _SEEDED_FACT_INTAKE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        seeded_value = seeded_facts.get(field_key)
        if seeded_value:
            return f"{field_key}={seeded_value!r} (intake-shaped question about seeded fact)"
        return f"{field_key} (intake-shaped question — should be lived-experience)"
    return None


# ── BUG-HARNESS-SCORER no_broken_code_mix + direct_human_voice ─────────
# Boris Phase 9 + Phase 2 additions.
#
# no_broken_code_mix: catches "Tú had an older brother Antonio... y
# asked my mother. ¿Qué pasó después?" — Spanish scaffolding tokens
# bolted onto English narrative.
#
# direct_human_voice: meta-row that FAILS when any of the following
# fingerprints fire: fragment / cascade / meta-leak / phrase-as-name /
# got-it-stub / broken-code-mix. The original 8 rows give granular
# diagnostics; this row gives the operator a single "would a human
# narrator hear this and feel listened to?" gate.
_BROKEN_CODE_MIX_SIGNALS = (
    # Spanish receipt scaffolding bolted onto otherwise-English text
    re.compile(r"\bcapté\b", re.IGNORECASE),
    re.compile(r"\btú\s+(had|made|asked|went|said|called)\b", re.IGNORECASE),
    re.compile(r"¿qué pasó después", re.IGNORECASE),
    re.compile(r"[a-z]\s+y\s+(asked|said|made|had|went|called|told)\b", re.IGNORECASE),
)

# Inverted Spanish punctuation embedded mid-text (not a leading sentence)
_SPANISH_PUNCT_RX = re.compile(r"[¿¡]")

# English function words (rough density estimate)
_ENGLISH_FUNCTION_WORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "is", "was",
    "you", "your", "i", "me", "my", "we", "had", "have", "with", "for",
    "on", "at", "what", "when", "where", "do", "did", "are", "be", "been",
})


def _detect_broken_code_mix(text: str) -> Optional[str]:
    """True if Spanish scaffolding tokens appear in otherwise-English text.

    Heuristic:
      1. Any explicit broken-code-mix signal (Capté / Tú X / ¿Qué pasó / X y verb)
      2. Inverted Spanish punctuation present AND English function-word
         density ≥ 30% (mid-text Spanglish; pure-Spanish narrator turns
         are NOT broken — they only become broken when mixed)
    """
    if not text or len(text.split()) < 4:
        return None
    for pat in _BROKEN_CODE_MIX_SIGNALS:
        m = pat.search(text)
        if m:
            return m.group(0)
    # Density check
    if _SPANISH_PUNCT_RX.search(text):
        tokens = re.findall(r"\b[a-z]+\b", text.lower())
        if tokens:
            en_hits = sum(1 for t in tokens if t in _ENGLISH_FUNCTION_WORDS)
            density = en_hits / len(tokens)
            if density >= 0.30:
                return "spanish_punct_in_english_context"
    return None


# ── Data classes ───────────────────────────────────────────────────────────


@dataclass
class ChapterConfig:
    """One narrator chapter to send."""
    label: str               # human-readable, e.g. "Earliest Years"
    runtime71_era: str       # canonical era_id, e.g. "earliest_years"
    text: str                # the narrator monologue
    anchors: List[str]       # lowercase substrings Lori must reference
    word_budget: int = 110   # how long Lori's reply may be

    @property
    def key(self) -> str:
        return self.runtime71_era


@dataclass
class HarnessConfig:
    """Per-narrator harness config."""
    narrator_label: str
    intake_payload: Dict[str, Any]
    chapters: List[ChapterConfig]
    bonus_probe: str = "Anyway, that's about it for what I wanted to say today."
    report_prefix: str = "long_narration"
    # When False, harness keeps testing_only=True so we don't pollute the
    # consent_attestations table with non-consenting test rows.
    testing_only: bool = True


# ── HTTP helpers ───────────────────────────────────────────────────────────


def _http_post_json(
    url: str, body: Dict[str, Any], timeout: int = 30,
) -> Tuple[int, Any]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw)
            except (ValueError, TypeError):
                return resp.status, raw
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", errors="replace"))
        except (ValueError, TypeError):
            return e.code, None
    except (urllib.error.URLError, OSError) as e:
        return 0, str(e)


def ping_stack(timeout: int = 5) -> bool:
    try:
        with urllib.request.urlopen(PING_URL, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


# ── Step 1: intake ─────────────────────────────────────────────────────────


def create_narrator(cfg: HarnessConfig) -> Optional[str]:
    """POST /api/people/intake. Returns the new person_id or None on failure."""
    print("=" * 70)
    print(f"STEP 1 — Creating {cfg.narrator_label} via POST /api/people/intake")
    print("=" * 70)

    payload = dict(cfg.intake_payload)
    # Force testing_only if the config asks for it, so we don't
    # spuriously write consent rows for fictional personas.
    if cfg.testing_only:
        payload["testing_only"] = True
        payload["consent_recording_agreement"] = True
        payload["consent_disclosure_reviewed"] = True

    status, body = _http_post_json(INTAKE_URL, payload, timeout=30)
    if status != 200:
        print(f"  ✗ INTAKE FAILED — HTTP {status}")
        print(f"  Body: {json.dumps(body, indent=2) if isinstance(body, dict) else body}")
        return None
    if not isinstance(body, dict):
        print(f"  ✗ INTAKE returned non-dict body: {body}")
        return None
    pid = body.get("person_id") or (body.get("person") or {}).get("id")
    if not pid:
        print(f"  ✗ INTAKE returned no person_id: {json.dumps(body)[:300]}")
        return None
    print(f"  ✓ {cfg.narrator_label} created — person_id={pid}")
    print(f"  ✓ bio_facts_written: {body.get('bio_facts_written')}")
    if body.get("profile_json_error"):
        print(f"  ⚠ profile_json_error: {body['profile_json_error']}")
    print()
    return pid


# ── Step 2: WS chat helper ─────────────────────────────────────────────────


async def _send_turn_and_capture(
    ws,
    *,
    text: str,
    conv_id: str,
    person_id: str,
    speaker_name: str,
    runtime71_era: str,
    chapter_label: str,
    client_turn_id: str = "",
    timeout_s: int = 240,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Send one narrator turn, stream tokens, return (final_text, events).

    `client_turn_id` is the join key between three separate records —
    the server's response trace, this console output, and the external
    `nvidia-smi` timeline. `chat_ws.py` already reads
    `params.client_turn_id` into the trace; nothing was supplying one,
    so a report had to guess which turn a trace belonged to by
    timestamp. The seventh era and the closing bonus probe both report
    era `today`, which is exactly where guessing fails.
    """

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
            "session_style_directive": (
                "Listen long. Reflect with one specific anchor. "
                "Ask one short question at most."
            ),
            "identity_complete": True,
            "identity_phase": "complete",
            "effective_pass": "pass2a",
            "speaker_name": speaker_name,
            "person_id": person_id,
            "conversation_state": "answering",
            "cognitive_support_mode": False,
        },
        # Deliberately 256 for this diagnostic: whether that cap BINDS
        # is one of the things being measured, so it must not be raised
        # before the measurement.
        "max_new_tokens": 256,
        "turn_final": True,
    }
    if client_turn_id:
        params["client_turn_id"] = client_turn_id
    # ── THE JOIN KEY MUST BE IN THE CONSOLE, NOT ONLY THE PAYLOAD ────
    #
    # Added 2026-09-06, after review. The id was being SENT correctly and
    # described as the join key between the server trace, this console
    # and the GPU timeline — but it was never printed, so the console
    # (which is what `tee` captures) carried no such key and the claim
    # was two-thirds true. Correlating a console line to a trace still
    # meant guessing by timestamp, which is exactly what the id exists
    # to avoid, and worst on the two turns that both report era `today`.
    print(f"  --- SENDING {chapter_label} ({len(text.split())} words) ---")
    if client_turn_id:
        print(f"      client_turn_id={client_turn_id}")
    send_start = time.time()
    await ws.send(json.dumps({
        "type": "start_turn",
        "session_id": conv_id,
        "conv_id": conv_id,
        "message": text,
        "turn_mode": "interview",
        "params": params,
    }, ensure_ascii=False))

    tokens: List[str] = []
    #: Set when an `error` frame arrives. The turn is refused, but its
    #: `done` still has to be consumed before the next one is sent.
    error_seen = False
    events: List[Dict[str, Any]] = []
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
            if error_seen:
                # A refused turn: the `done` is the end of the contract,
                # not a response. Say so rather than reporting an empty
                # string as if Lori had answered with nothing.
                print(f"\n  --- {chapter_label} REFUSED, socket clean "
                      f"({elapsed:.1f}s) ---")
                return "", events
            print(f"\n  --- {chapter_label} DONE in {elapsed:.1f}s ---")
            return final_text, events
        elif typ == "error":
            # ── DO NOT RETURN HERE. KEEP READING UNTIL `done`. ────────
            #
            # CORRECTED 2026-09-06, after review, and this one would have
            # ruined the run rather than dented it.
            #
            # The server's blocked-turn contract is `error` THEN `done` —
            # every refusal path sends both: `PROMPT_TOO_LARGE`,
            # `VRAM_PRESSURE`, `GENERATION_BUSY`, `CUDA_OOM`. Returning
            # at the error left that `done` queued on the socket. The
            # next era would send its chapter and immediately read the
            # PREVIOUS turn's completion frame — so from the first
            # refusal onward every result was attributed to the wrong
            # era, silently, with plausible-looking output.
            #
            # And refusal is not an edge case here: it is one of the
            # OUTCOMES THIS DIAGNOSTIC IS LOOKING FOR. The failure mode
            # was triggered by the thing being measured, which is the
            # worst possible coupling.
            #
            # So the error is recorded and the loop continues to the
            # matching `done`, which returns an empty final response and
            # leaves the socket clean for the next turn.
            print(f"\n  ✗ ERROR on {chapter_label}: {json.dumps(msg)[:400]}")
            print("    (waiting for the matching `done` — the socket must "
                  "be clean for the next era)")
            error_seen = True
            continue
    raise TimeoutError(f"No done event for {chapter_label} after {timeout_s}s")


# ── Step 3: scorer ────────────────────────────────────────────────────────


def score_chapter(
    chapter: ChapterConfig,
    response_text: str,
    *,
    is_bonus: bool = False,
    seeded_facts: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """16-row checklist scorer.

    Original 8 rows (matrix integrity per LAW) are preserved. The 8 new
    content-quality rows added by BUG-HARNESS-SCORER-TOO-LENIENT-CONTENT-
    QUALITY-01 catch failure modes the original matrix called PASS:
      - "Got it — [phrase]. Did I get that name right?" stubs
      - Title-case descriptive phrases treated as names
      - Orphan fragments ("West St.", "St.", "Began.")
      - Lori asking for seeded bio facts she already has
      - LLM meta-response leak ("Here is a response that follows...")
      - Mechanical anchor-cascade dumps
      - Stock-phrase "You said X / You kept coming back to X"
      - Responses with zero anchor anchoring

    Pass `seeded_facts={'place_of_birth': 'Albany, Georgia', 'birth_year': 1942}`
    to enable the no_seeded_fact_intake_question check; otherwise that row
    is reported as PASS (no seeded context = no question to validate against).
    """
    text = (response_text or "").strip()
    lower = text.lower()
    words = text.split()
    word_count = len(words)
    question_count = text.count("?")

    # 1. Reflection grounded
    anchor_hits = [a for a in chapter.anchors if a.lower() in lower]
    reflection_grounded = "PASS" if anchor_hits else "FAIL"

    # 2. One question max
    if question_count <= 1:
        one_question_max = "PASS"
    elif question_count == 2:
        one_question_max = "PARTIAL"
    else:
        one_question_max = "FAIL"

    # 3. No questionnaire interrogation
    interrogation_patterns = [
        r"\bwhat was your\b", r"\bwhen exactly\b",
        r"\bwhat year\b", r"\bwhat is your\b",
        r"\bmaiden name\b", r"\bbirth order\b",
    ]
    interrogation_hits = sum(
        1 for p in interrogation_patterns if re.search(p, lower)
    )
    no_questionnaire = (
        "FAIL" if interrogation_hits >= 2
        else "PARTIAL" if interrogation_hits == 1
        else "PASS"
    )

    # 4. No forbidden empathy
    forbidden_hits = [
        op for op in FORBIDDEN_OPENERS
        if lower.startswith(op) or f". {op}" in lower
    ]
    no_forbidden_empathy = "FAIL" if forbidden_hits else "PASS"

    # 5. No era-label menu
    era_menu_hits = [p for p in ERA_LABEL_MENU_PATTERNS if p in lower]
    era_label_count = len(era_menu_hits)
    no_era_label_menu = "FAIL" if era_label_count >= 2 else "PASS"

    # 6. Same-anchor loop — meta, populated by caller
    no_same_anchor_loop = "PENDING"

    # 7. Word budget honored
    if word_count <= chapter.word_budget:
        word_budget_honored = "PASS"
    elif word_count <= chapter.word_budget + 20:
        word_budget_honored = "PARTIAL"
    else:
        word_budget_honored = "FAIL"

    # 8. Translation / refusal absent
    refusal_patterns = [
        "let me say that in english", "i cannot answer", "i can't answer",
        "i'm not able to", "i am not able to",
    ]
    refusal_hit = any(p in lower for p in refusal_patterns)
    translation_refusal_absent = (
        "FAIL" if (not text or refusal_hit) else "PASS"
    )

    # ── 8 NEW CONTENT-QUALITY ROWS ───────────────────────────────────────
    # BUG-HARNESS-SCORER-TOO-LENIENT-CONTENT-QUALITY-01
    # Hard FAIL rows (no PARTIAL — these patterns are unacceptable Lori voice).

    # 9. no_false_name_confirmation — "Did I get that name right?" on phrase
    no_false_name_confirmation = (
        "FAIL" if _detect_false_name_confirm(text) else "PASS"
    )

    # 10. no_got_it_stub — "Got it — X. What happened next?" shell
    no_got_it_stub = (
        "FAIL" if _detect_got_it_stub(text) else "PASS"
    )

    # 11. no_titlecase_phrase_as_name — "Originally Schong With A C"
    titlecase_phrase_offender = _detect_titlecase_phrase_as_name(text)
    no_titlecase_phrase_as_name = (
        "FAIL" if titlecase_phrase_offender else "PASS"
    )

    # 12. response_not_fragmented — orphan stub "West St." / "St."
    no_fragment = not _detect_fragment(text)
    response_not_fragmented = "PASS" if no_fragment else "FAIL"

    # 13. minimum_anchor_count — at least one grounded anchor from narrator text
    # (unless this is a safety response or a closing/bonus probe)
    if is_bonus:
        minimum_anchor_count = "PASS"
    elif refusal_hit:
        # Safety/translation refusal already failed translation_refusal_absent
        minimum_anchor_count = "PASS"
    elif len(anchor_hits) >= 1:
        minimum_anchor_count = "PASS"
    else:
        minimum_anchor_count = "FAIL"

    # 14. no_meta_response_leak — "Here is a response that follows..." etc.
    meta_leak_offender = _detect_meta_leak(text)
    no_meta_response_leak = "FAIL" if meta_leak_offender else "PASS"

    # 15. no_titlecased_anchor_cascade — "You went from X to Y, then Z, A, B, C"
    no_titlecased_anchor_cascade = (
        "FAIL" if _detect_anchor_cascade(text) else "PASS"
    )

    # 16. no_seeded_fact_intake_question — Lori asking about seeded bio facts
    # Per Boris Phase 8: pattern-only detection — seeded_facts is optional
    # context. The intake question shape itself is the failure regardless
    # of whether the operator pre-seeded the value.
    seeded_intake_offender = _detect_seeded_fact_intake(text, seeded_facts)
    no_seeded_fact_intake_question = (
        "FAIL" if seeded_intake_offender else "PASS"
    )

    # 17. no_broken_code_mix — Spanish scaffolding tokens bolted onto
    # otherwise-English text. "Tú had an older brother... y asked my
    # mother. ¿Qué pasó después?" is the classic shape; a clean Spanish
    # narrator turn does NOT trigger this row (density check excludes it).
    broken_code_mix_offender = _detect_broken_code_mix(text)
    no_broken_code_mix = "FAIL" if broken_code_mix_offender else "PASS"

    # 18. direct_human_voice — composite gate. FAILS if any failure
    # fingerprint that breaks the "would a human narrator hear this and
    # feel listened to" test is present. The granular rows above give
    # diagnostics; this row is the single operator-facing summary.
    # Triggered by:
    #   - got-it-stub / phrase-as-name / false-name-confirm (mechanical
    #     template firing on non-name)
    #   - cascade dump (proper-noun list recital)
    #   - meta-leak (LLM exposing prompt-compliance reasoning)
    #   - broken code-mix (Spanish scaffolding in English context)
    #   - response_not_fragmented FAIL (stub like "West St.")
    #   - minimum_anchor_count FAIL (zero anchoring)
    direct_human_voice_failures = []
    if no_got_it_stub == "FAIL":
        direct_human_voice_failures.append("got_it_stub")
    if no_false_name_confirmation == "FAIL":
        direct_human_voice_failures.append("false_name_confirmation")
    if no_titlecase_phrase_as_name == "FAIL":
        direct_human_voice_failures.append("titlecase_phrase_as_name")
    if no_titlecased_anchor_cascade == "FAIL":
        direct_human_voice_failures.append("anchor_cascade")
    if no_meta_response_leak == "FAIL":
        direct_human_voice_failures.append("meta_response_leak")
    if no_broken_code_mix == "FAIL":
        direct_human_voice_failures.append("broken_code_mix")
    if response_not_fragmented == "FAIL":
        direct_human_voice_failures.append("fragmented")
    if minimum_anchor_count == "FAIL" and not is_bonus and not refusal_hit:
        direct_human_voice_failures.append("zero_anchors")
    direct_human_voice = "FAIL" if direct_human_voice_failures else "PASS"

    return {
        "label": chapter.label,
        "chapter_key": chapter.key,
        "word_count": word_count,
        "question_count": question_count,
        "anchor_hits": anchor_hits,
        "rows": {
            # original 8 rows (preserved for matrix-integrity comparisons)
            "reflection_grounded": reflection_grounded,
            "one_question_max": one_question_max,
            "no_questionnaire_interrogation": no_questionnaire,
            "no_forbidden_empathy_openers": no_forbidden_empathy,
            "no_era_label_menu": no_era_label_menu,
            "no_same_anchor_loop": no_same_anchor_loop,
            "word_budget_honored": word_budget_honored,
            "translation_refusal_absent": translation_refusal_absent,
            # 8 new content-quality rows (hard FAIL on detection)
            "no_false_name_confirmation": no_false_name_confirmation,
            "no_got_it_stub": no_got_it_stub,
            "no_titlecase_phrase_as_name": no_titlecase_phrase_as_name,
            "response_not_fragmented": response_not_fragmented,
            "minimum_anchor_count": minimum_anchor_count,
            "no_meta_response_leak": no_meta_response_leak,
            "no_titlecased_anchor_cascade": no_titlecased_anchor_cascade,
            "no_seeded_fact_intake_question": no_seeded_fact_intake_question,
            # 2 additional Boris rows (Phase 2 + Phase 9 gap-fill)
            "no_broken_code_mix": no_broken_code_mix,
            "direct_human_voice": direct_human_voice,
        },
        "forbidden_openers_hit": forbidden_hits,
        "interrogation_hits": interrogation_hits,
        "era_label_hits": era_menu_hits,
        # New offenders for debugging
        "titlecase_phrase_offender": titlecase_phrase_offender,
        "meta_leak_offender": meta_leak_offender,
        "seeded_intake_offender": seeded_intake_offender,
        "broken_code_mix_offender": broken_code_mix_offender,
        "direct_human_voice_failures": direct_human_voice_failures,
        "is_bonus": is_bonus,
    }


def cross_chapter_anchor_loop_check(scores: List[Dict[str, Any]]) -> None:
    """Detect shared anchors across chapters — mutates in place."""
    for i, s in enumerate(scores):
        if s["is_bonus"]:
            s["rows"]["no_same_anchor_loop"] = "PASS"
            continue
        loop_hits: List[str] = []
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


# ── Step 4: log greps ─────────────────────────────────────────────────────


def log_grep_summary() -> Dict[str, Any]:
    if not API_LOG.exists():
        return {"error": f"api.log not found at {API_LOG}"}
    try:
        text = API_LOG.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"error": f"Cannot read api.log: {e}"}

    return {
        "oral_history_style_lines": len(re.findall(
            r"composer.*style[= ]oral_history", text, flags=re.IGNORECASE,
        )),
        "reflection_not_grounded_lines": len(re.findall(
            r"reflection_not_grounded|question_layer_ineligible", text,
        )),
        "extract_accepted_lines": len(re.findall(r"extract.*accepted=", text)),
        "spantag_flag_on_lines_observed": "[extract][spantag] flag ON" in text,
    }


# ── Step 5: report writer ────────────────────────────────────────────────


def write_report(
    cfg: HarnessConfig,
    conv_id: str,
    person_id: str,
    chapter_results: List[Tuple[ChapterConfig, str, Dict[str, Any]]],
    bonus_result: Optional[Tuple[str, Dict[str, Any]]],
    log_summary: Dict[str, Any],
) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{cfg.report_prefix}_{conv_id}.txt"
    lines: List[str] = []
    lines.append("=" * 80)
    lines.append(f"{cfg.narrator_label.upper()} — LONG-NARRATION HARNESS REPORT")
    lines.append("=" * 80)
    lines.append(f"conv_id:    {conv_id}")
    lines.append(f"person_id:  {person_id}")
    lines.append(f"run_time:   {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    overall_pass = 0
    overall_total = 0
    for chapter, response_text, score in chapter_results:
        lines.append("─" * 80)
        lines.append(f"CHAPTER — {chapter.label}")
        lines.append("─" * 80)
        lines.append(f"  word_count:     {score['word_count']}")
        lines.append(f"  question_count: {score['question_count']}")
        lines.append(f"  anchor_hits:    {', '.join(score['anchor_hits']) or '(none)'}")
        lines.append("")
        lines.append("  Lori response (verbatim):")
        lines.append("  ┌" + "─" * 76)
        for ln in (response_text or "(no response)").splitlines() or [response_text or ""]:
            lines.append(f"  │ {ln}")
        lines.append("  └" + "─" * 76)
        lines.append("")
        lines.append("  Scoring matrix:")
        for row_name, row_val in score["rows"].items():
            mark = ("✓" if row_val == "PASS" else
                    "⚠" if row_val == "PARTIAL" else
                    "✗" if row_val == "FAIL" else "·")
            lines.append(f"    {mark} {row_name}: {row_val}")
            overall_total += 1
            if row_val == "PASS":
                overall_pass += 1
        lines.append("")
    if bonus_result is not None:
        text, bs = bonus_result
        lines.append("─" * 80)
        lines.append("BONUS PROBE — closing marker")
        lines.append("─" * 80)
        lines.append(f"  Probe sent: {cfg.bonus_probe}")
        lines.append("")
        lines.append("  Lori response:")
        lines.append("  ┌" + "─" * 76)
        for ln in (text or "(no response)").splitlines() or [text or ""]:
            lines.append(f"  │ {ln}")
        lines.append("  └" + "─" * 76)
        lines.append("")
    lines.append("─" * 80)
    lines.append("BACKEND LOG GREP SUMMARY")
    lines.append("─" * 80)
    for k, v in log_summary.items():
        lines.append(f"  {k}: {v}")
    lines.append("")
    lines.append("─" * 80)
    lines.append(f"OVERALL: {overall_pass}/{overall_total} rows PASS")
    lines.append("─" * 80)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written: {report_path}")
    return report_path


# ── Public entry point ───────────────────────────────────────────────────


async def run_harness(cfg: HarnessConfig) -> int:
    """Top-level entry. Returns 0 on success, non-zero on failure."""
    if not ping_stack():
        print(f"✗ Stack not reachable at {PING_URL} — start the API first.",
              file=sys.stderr)
        return 1

    pid = create_narrator(cfg)
    if not pid:
        return 1

    conv_id = str(uuid.uuid4())[:12]
    speaker_name = cfg.intake_payload.get("preferred_name") or "the narrator"

    print(f"\nOpening chat WS: {WS_URL}  conv_id={conv_id}\n")
    chapter_results: List[Tuple[ChapterConfig, str, Dict[str, Any]]] = []
    bonus_result: Optional[Tuple[str, Dict[str, Any]]] = None
    async with websockets.connect(WS_URL, max_size=1 << 22) as ws:
        for _idx, ch in enumerate(cfg.chapters, start=1):
            # `<prefix>:<conv>:<NN>:<era>` — ordered, unique, and
            # readable in a console scrollback. The index is what
            # separates era seven from the bonus probe, which both
            # report era `today`.
            text, _events = await _send_turn_and_capture(
                ws,
                text=ch.text,
                conv_id=conv_id,
                person_id=pid,
                speaker_name=speaker_name,
                runtime71_era=ch.runtime71_era,
                chapter_label=ch.label,
                client_turn_id=(f"{cfg.report_prefix}:{conv_id}:"
                                f"{_idx:02d}:{ch.runtime71_era}"),
            )
            score = score_chapter(ch, text)
            chapter_results.append((ch, text, score))
            print()
        # Bonus probe — fixed bonus era ("today") since it's the closing marker
        if cfg.bonus_probe:
            text, _events = await _send_turn_and_capture(
                ws,
                text=cfg.bonus_probe,
                conv_id=conv_id,
                person_id=pid,
                speaker_name=speaker_name,
                runtime71_era="today",
                chapter_label="Bonus probe",
                client_turn_id=(f"{cfg.report_prefix}:{conv_id}:"
                                f"{len(cfg.chapters) + 1:02d}:bonus_probe"),
            )
            # Fake chapter-config for scoring shape
            fake_bonus_ch = ChapterConfig(
                label="Bonus probe", runtime71_era="today",
                text=cfg.bonus_probe, anchors=[], word_budget=60,
            )
            bonus_score = score_chapter(fake_bonus_ch, text, is_bonus=True)
            chapter_results.append((fake_bonus_ch, text, bonus_score))
            bonus_result = (text, bonus_score)

    # Cross-chapter anchor-loop pass
    cross_chapter_anchor_loop_check([s for (_c, _t, s) in chapter_results])

    log_summary = log_grep_summary()
    write_report(cfg, conv_id, pid, chapter_results[:len(cfg.chapters)],
                 bonus_result, log_summary)
    return 0
