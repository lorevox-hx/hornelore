"""WO-LORI-COMMUNICATION-CONTROL-01 — Runtime Communication Guard for Lori.

The unifying enforcement layer that wraps the existing atomicity
filter (WO-LORI-QUESTION-ATOMICITY-01) and reflection validator
(WO-LORI-REFLECTION-01), and adds:

  * Per-session-style word-count limits
  * Question-count enforcement (≤1 per turn)
  * Safety-trigger exemption (acute SAFETY responses keep their own
    structure)
  * One unified result dataclass for harness + log consumption

Architecture grounding (per the WO):

  Layer 1 — Cognitive rules (Grice's maxims): WHAT good communication is
  Layer 2 — Behavioral control (this module): runtime enforcement
  Layer 3 — Interview intelligence: emotional continuity, life-map
            anchoring, etc. (separate lane)

The Wang et al. 2025 STA paper finding — prompt engineering is fragile
to small input changes while deterministic enforcement is robust — is
the load-bearing argument for THIS module's existence. The Rappa et
al. 2026 Grice paper supplies the four maxims that map onto the rules:

  Quantity   → word_count limits per session_style
  Manner     → atomicity enforcement (truncate compounds)
  Relation   → reflection grounding (dropped if drifts off topic)
  Quality    → reflection validator (no invented affect, no archive
              language)

LAW-3 isolation: this module imports zero extraction-stack code. It
composes the existing question_atomicity + lori_reflection modules,
which themselves are LAW-3 isolated. No LLM call. Pure-function.

Public API:

    enforce_lori_communication_control(
        assistant_text, user_text,
        *, safety_triggered=False, session_style="clear_direct",
    ) -> CommunicationControlResult

The chat_ws.py wire-up is a single call site. The harness consumes
the result.communication_control_dict() directly into its per-turn
record.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List

from .question_atomicity import classify_atomicity, enforce_question_atomicity
from .lori_reflection import validate_memory_echo, shape_reflection


def _reflection_shaping_enabled() -> bool:
    """WO-LORI-REFLECTION-02 — runtime reflection shaping is gated
    DEFAULT-OFF behind HORNELORE_REFLECTION_SHAPING for the first eval
    cycle. Per Phase 4 of the spec, flip the default to "1" in
    .env.example after two consecutive golfball passes at ≥ 6/8 with
    the flag ON.
    """
    return os.environ.get("HORNELORE_REFLECTION_SHAPING", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _phantom_noun_guard_enabled() -> bool:
    """BUG-STT-PHANTOM-PROPER-NOUNS-01 Layer 2 (2026-05-07) — runtime
    behavioral guard that catches Lori inventing proper nouns the
    narrator never said. Default OFF for first ship — observe how
    often the guard would have fired before flipping. Set
    HORNELORE_PHANTOM_NOUN_GUARD=1 to enable flag-only mode (logs
    warnings, no mutation). Set HORNELORE_PHANTOM_NOUN_SCRUB=1 to
    additionally drop sentences containing flagged proper nouns.
    """
    return os.environ.get("HORNELORE_PHANTOM_NOUN_GUARD", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _phantom_noun_scrub_enabled() -> bool:
    """When BOTH this flag AND _phantom_noun_guard_enabled are on,
    flagged proper nouns trigger sentence-drop in the reply text
    (mutation). When only the guard flag is on, behavior is flag-only
    (logs warnings, no mutation). Default OFF — flag-only first.
    """
    return os.environ.get("HORNELORE_PHANTOM_NOUN_SCRUB", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


# False-positive whitelist for the phantom-noun guard. Capitalized
# tokens in this set are NEVER flagged, regardless of whether the
# narrator said them. Categories: pronouns, common articles + Lori's
# own name, day/month names, season names, religious references that
# narrators commonly invoke without naming, generic family terms,
# US-specific place names that frequently appear in reflective prose.
_PHANTOM_NOUN_WHITELIST = frozenset({
    # Pronouns + I-contractions (capitalized at sentence start anyway
    # but captured here as belt-and-suspenders for the case where
    # they appear mid-sentence in dialect or quotation).
    "I", "I'm", "I'll", "I've", "I'd",
    # Common articles + possessives that may appear capitalized in
    # the middle of sentences after dashes / em-dashes.
    "A", "An", "The", "Your", "My", "Our", "His", "Her", "Their",
    "Yes", "No", "OK", "Okay", "So", "Now", "Well",
    # System / brand references — Lori is allowed to refer to herself.
    "Lori", "Lorevox", "Hornelore",
    # Calendar names — generic, narrators reference dates without
    # introducing them as characters.
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
    "Spring", "Summer", "Fall", "Autumn", "Winter",
    # Religious / cultural references that elder narrators commonly
    # use as concepts rather than as named individuals.
    "God", "Lord", "Christ", "Jesus", "Heaven",
    # Generic family terms — Lori echoes these as kinship roles, not
    # as characters with names.
    "Mom", "Mother", "Mama", "Dad", "Father", "Papa",
    "Grandma", "Grandmother", "Grandpa", "Grandfather",
    "Sis", "Sister", "Bro", "Brother",
    "Aunt", "Uncle", "Cousin",
    "Wife", "Husband", "Son", "Daughter", "Child",
    # Holidays and major shared events.
    "Christmas", "Easter", "Hanukkah", "Passover", "Ramadan", "Diwali",
    "Thanksgiving", "Halloween", "Valentine's",
    # America / U.S. references that appear in life-story prose.
    "America", "American", "United", "States", "USA",
    # Common warm reflection phrases Lori uses.
    "Take", "Could", "Would", "Should", "Tell", "Share",
    "What", "When", "Where", "Why", "How", "Who", "Which",
})


# Pattern: capitalized word ≥3 chars NOT at sentence start. Sentence
# starts include: very beginning of text, after period+space,
# question-mark+space, exclam+space, newline. Mid-sentence capitalized
# tokens are real proper-noun candidates.
_MID_SENTENCE_PROPER_NOUN_RX = re.compile(
    r"(?<![.!?]\s)(?<![.!?]\n)(?<!\n)(?<!^)"
    r"\b([A-Z][a-z'-]{2,})\b"
)


def _extract_proper_noun_candidates(text: str) -> List[str]:
    """Find proper-noun-shaped tokens in `text` that are NOT at
    sentence start and NOT in the false-positive whitelist.

    Returns a deduplicated list of candidate tokens (preserving
    first-appearance order for stable test output).
    """
    if not text:
        return []
    seen: List[str] = []
    seen_lower: set = set()
    # Walk the text sentence-by-sentence so we can correctly identify
    # mid-sentence vs sentence-start positions. Splitting on the
    # standard sentence terminators preserves the first-word-after-
    # punctuation rule that capitalization always allows.
    sentence_parts = re.split(r"([.!?]+\s+)", text)
    # sentence_parts alternates: [sentence, separator, sentence, separator, ...]
    sentences: List[str] = []
    for i in range(0, len(sentence_parts), 2):
        if i < len(sentence_parts):
            sentences.append(sentence_parts[i])
    for sent in sentences:
        if not sent.strip():
            continue
        # Within a sentence: skip the first word (sentence-start cap
        # is mandatory per English rules). Look at every subsequent
        # capitalized word ≥3 chars.
        words = re.findall(r"\b([A-Za-z][A-Za-z'-]*)\b", sent)
        for idx, w in enumerate(words):
            if idx == 0:
                continue  # sentence start — capitalization allowed
            if not w or len(w) < 3:
                continue
            if not w[0].isupper():
                continue  # not capitalized
            # Reject all-caps tokens (likely acronyms) — too noisy
            # to flag confidently. Adjust later if needed.
            if w.isupper() and len(w) > 2:
                continue
            if w in _PHANTOM_NOUN_WHITELIST:
                continue
            wl = w.lower()
            if wl in seen_lower:
                continue
            seen.append(w)
            seen_lower.add(wl)
    return seen


def _build_known_names(profile_seed: Dict[str, object]) -> List[str]:
    """Pull canonical names from the profile_seed dict so the guard
    doesn't flag them. Looks at common keys that may carry strings:
    preferred_name, full_name, parents/children/spouse names, plus
    any list of person dicts with firstName/lastName/preferredName.
    """
    if not isinstance(profile_seed, dict):
        return []
    out: List[str] = []
    # Direct-string keys
    for k in ("preferred_name", "full_name", "speaker_name",
              "childhood_home", "partner", "spouse_name",
              "father_name", "mother_name"):
        v = profile_seed.get(k)
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
    # Comma/space-joined list keys (parents_work, children, etc.)
    for k in ("parents_work", "children", "siblings", "education", "career"):
        v = profile_seed.get(k)
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, str):
                    out.append(item)
                elif isinstance(item, dict):
                    for kk in ("firstName", "preferredName", "fullName",
                               "first_name", "preferred_name", "full_name"):
                        vv = item.get(kk)
                        if isinstance(vv, str) and vv.strip():
                            out.append(vv.strip())
    return out


def _verify_proper_noun(
    token: str,
    narrator_corpus: str,
    known_names: List[str],
) -> bool:
    """True if `token` is justified by appearing in narrator's recent
    turns OR in canonical profile names. Case-insensitive substring
    match — tolerant to declension and partial appearance ("David"
    matches "David's", etc.).
    """
    token_lower = token.lower()
    if narrator_corpus and token_lower in narrator_corpus.lower():
        return True
    for name in known_names:
        if name and token_lower in str(name).lower():
            return True
    return False


def scrub_phantom_proper_nouns(
    reply: str,
    *,
    narrator_corpus: str,
    profile_seed: Dict[str, object],
    scrub_mode: bool = False,
) -> Dict[str, object]:
    """Scan `reply` for proper-noun-shaped tokens, verify each
    against `narrator_corpus` (recent narrator turns concatenated)
    and `profile_seed` (canonical names). Tokens that fail BOTH
    checks are flagged as phantom (likely STT mishearings or LLM
    hallucinations).

    Args:
        reply:           Lori's reply text
        narrator_corpus: concatenated narrator turn(s) — most recent
                         2-3 turns is enough; longer hurts precision
        profile_seed:    profile_seed dict from runtime71
        scrub_mode:      when False (default), flag-only — returns
                         the reply unchanged + flagged list. When
                         True, drop sentences containing any flagged
                         token from the returned text.

    Returns dict:
        {
          "final_text": str,        # possibly-scrubbed reply
          "flagged":    List[str],  # phantom proper nouns found
          "scrubbed":   bool,       # True if final_text != reply
          "dropped_sentences": List[str],  # only populated when
                                            scrub_mode=True
        }

    Conservative drop strategy: when scrub_mode=True, find every
    sentence containing a flagged token, drop the whole sentence.
    Preserves Lori's other content (acknowledgment + follow-up
    question) when only one sentence carries the phantom noun.
    """
    out: Dict[str, object] = {
        "final_text": reply,
        "flagged": [],
        "scrubbed": False,
        "dropped_sentences": [],
    }
    if not reply or not reply.strip():
        return out

    candidates = _extract_proper_noun_candidates(reply)
    if not candidates:
        return out

    known_names = _build_known_names(profile_seed or {})

    flagged: List[str] = []
    for tok in candidates:
        if not _verify_proper_noun(tok, narrator_corpus or "", known_names):
            flagged.append(tok)

    out["flagged"] = flagged

    if not flagged or not scrub_mode:
        return out

    # Scrub mode — drop sentences containing flagged tokens.
    # Split reply into sentences; rebuild without any sentence whose
    # tokens overlap with flagged.
    flagged_lower = {f.lower() for f in flagged}
    parts = re.split(r"([.!?]+\s+|\n+)", reply)
    rebuilt: List[str] = []
    dropped: List[str] = []
    for i in range(0, len(parts), 2):
        sentence = parts[i] if i < len(parts) else ""
        sep = parts[i + 1] if i + 1 < len(parts) else ""
        # Any token in this sentence overlap with flagged?
        words = re.findall(r"\b([A-Za-z][A-Za-z'-]*)\b", sentence)
        if any(w.lower() in flagged_lower for w in words):
            dropped.append(sentence.strip())
            # Skip BOTH the sentence and its separator — sentence is gone.
            continue
        rebuilt.append(sentence)
        rebuilt.append(sep)

    final = "".join(rebuilt).strip()
    if final != reply:
        out["final_text"] = final
        out["scrubbed"] = True
        out["dropped_sentences"] = dropped
    return out


# Per-session-style word-count limits (Quantity maxim).
# clear_direct stays tight; warm_storytelling allows more narrative
# breath; companion sits between.
_SESSION_STYLE_WORD_LIMITS: Dict[str, int] = {
    "clear_direct": 55,
    "warm_storytelling": 90,
    "questionnaire_first": 70,
    "companion": 80,
}
_DEFAULT_WORD_LIMIT = 55


# Patterns used to detect "normal interview question during safety" —
# the case where Lori has been told there's safety content but still
# routes the turn through a normal interview prompt. This is a safety
# violation distinct from atomicity / reflection.
_SAFETY_NORMAL_QUESTION_RX = re.compile(
    r"\b(what|when|where|who|why|how|which|did|do|does|tell\s+me\s+about)\b"
    r"[^?!.]+\?",
    re.IGNORECASE,
)
# Tokens that indicate the response IS an ACUTE safety acknowledgment —
# i.e. a 988-bearing crisis-resource pointer, not a softened-mode
# presence response. If any of these appear, we treat the response
# as ACUTE: we don't fire the "normal question during safety" failure
# even when there's a '?' present (Lori is allowed to ask "are you
# safe?" / "do you have someone you can call?" within a safety frame),
# AND we bypass the SOFTENED_WORD_LIMIT cap (acute responses
# legitimately run 40-60 words including 988 phrasing).
#
# 2026-05-01 tighten (post-WO-LORI-SOFTENED-RESPONSE-01 verify): the
# previous regex over-broadly matched warm-presence phrases ("I'm so
# sorry", "glad you're still here", "takes a lot of courage", "reach
# out", "safe right now") that legitimately appear in BOTH acute and
# softened responses. That made the wrapper bypass the softened cap on
# softened-mode turns where the LLM happened to use any of those
# phrases (golfball-softened-on Turn 07: 36-word softened response
# with "takes a lot of courage" passed without firing the cap).
#
# Acute is distinguished from softened by RESOURCE-POINTER language —
# the tokens softened mode is FORBIDDEN from re-quoting. Keep only
# those: 988, crisis/suicide lifeline, hotline, emergency, "call or
# text" (988 phrasing), "someone you can call/reach" (resource
# referral). Drop the warm-presence phrases.
_SAFETY_ACKNOWLEDGMENT_RX = re.compile(
    r"\b(988|crisis\s+lifeline|suicide.+lifeline|"
    r"call\s+or\s+text|"
    r"someone\s+(you\s+)?can\s+(call|reach)|"
    r"hotline|emergency)\b",
    re.IGNORECASE,
)


# WO-LORI-CONTROL-YIELD push-after-resistance detector (Phelan SIN 3 —
# too much arguing). Single-turn detection: narrator signals resistance
# in their turn, AND Lori's response in the same turn includes a probe
# verb. Caller is expected to skip this on safety/softened turns (those
# paths own the no-probe rule there). Bare "I don't know" intentionally
# NOT in RESISTANCE_RX — too conversational, would over-fire on neutral
# exchanges. PROBE_RX intentionally narrow (does NOT include a bare
# "?$" alternative) so legitimate off-ramp questions like "Would you
# like to try a different memory?" don't get falsely flagged.
_RESISTANCE_RX = re.compile(
    r"\b("
    r"i don'?t remember|i can'?t remember|"
    r"not much|not really|"
    r"i'?m not sure|"
    r"i can'?t think of anything|"
    r"i already told you|you ignored|"
    r"i don'?t want to talk about|"
    r"let'?s not|no thanks"
    r")\b",
    re.IGNORECASE,
)
_PROBE_RX = re.compile(
    r"\b("
    r"can you tell me|tell me more|"
    r"what was it like|do you remember|"
    r"what do you remember|how did you|"
    r"why did you|where were you|when did you|who was"
    r")\b",
    re.IGNORECASE,
)


def _detect_push_after_resistance(user_text: str, assistant_text: str) -> bool:
    """Return True if narrator signaled resistance AND Lori's reply
    contains a probe verb, in the same turn. Narrow by design — sequence-
    level escalation patterns (resistance → probe → resistance → probe)
    live in the harness rollup."""
    u = (user_text or "").strip()
    a = (assistant_text or "").strip()
    if not u or not a:
        return False
    if not _RESISTANCE_RX.search(u):
        return False
    if not _PROBE_RX.search(a):
        return False
    return True


@dataclass
class CommunicationControlResult:
    """Single unified result for chat_ws + harness consumption."""

    original_text: str
    final_text: str
    changed: bool
    failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    question_count: int = 0
    word_count: int = 0
    atomicity_failures: List[str] = field(default_factory=list)
    reflection_failures: List[str] = field(default_factory=list)
    session_style: str = "clear_direct"
    safety_triggered: bool = False

    def to_dict(self) -> Dict:
        """Harness-friendly dict shape. Excludes original_text + final_text
        to avoid leaking narrator/assistant content into the JSON report
        beyond what the harness already records."""
        return {
            "changed": self.changed,
            "failures": list(self.failures),
            "warnings": list(self.warnings),
            "question_count": self.question_count,
            "word_count": self.word_count,
            "atomicity_failures": list(self.atomicity_failures),
            "reflection_failures": list(self.reflection_failures),
            "session_style": self.session_style,
            "safety_triggered": self.safety_triggered,
        }


def _truncate_to_first_question(text: str) -> str:
    """Keep everything up to and including the first '?'. Used when
    question_count > 1."""
    idx = text.find("?")
    if idx == -1:
        return text
    return text[: idx + 1].strip()


def _truncate_to_word_limit(text: str, limit: int) -> str:
    """Truncate to `limit` words. Strategy ladder:

      1. If text fits, return as-is.
      2. If the first '?' fits within the limit, return up to that '?'
         (preserve a complete question — the most useful single-turn
         shape for the narrator).
      3. If no question fits, walk backward from the word-budget edge
         to the last sentence-ending punctuation ('.', '!', '?') and
         end cleanly there. This preserves at least one complete
         thought rather than chopping mid-sentence.
      4. Last resort: truncate mid-sentence and append '…' so the
         narrator at least sees the response was clipped.

    BUG-LORI-RESPONSE-MID-SENTENCE-CUT-01 (2026-05-07): Melanie Zollner
    live session 03:23 had three Lori turns ending with mid-question
    truncation — "What do you remember about...", "How did you feel
    about being the center of attention like...", "Does that..." —
    because the first '?' fell past the 55-word clear_direct cap and
    the old truncator went straight to mid-sentence chop. New strategy
    3 catches all three: walk back to the previous '.'/'!'/'?' and
    end the response there with a complete thought.
    """
    words = text.split()
    if len(words) <= limit:
        return text

    # Strategy 2: preserve first complete question if it fits.
    first_q = text.find("?")
    if first_q != -1:
        candidate = text[: first_q + 1].strip()
        if len(candidate.split()) <= limit:
            return candidate

    # Strategy 3: walk backward from word-budget edge to last clean
    # sentence boundary. Build the budget-window text, then scan for
    # the last '.', '!', or '?' inside it (skip ellipsis '...' so we
    # don't pretend a chopped truncation was a complete sentence).
    budget_text = " ".join(words[:limit])
    last_sent_end = -1
    for i in range(len(budget_text) - 1, -1, -1):
        ch = budget_text[i]
        if ch in (".", "!", "?"):
            # Reject if this is part of an ellipsis '...'.
            if ch == "." and i >= 2 and budget_text[i-2:i+1] == "...":
                continue
            last_sent_end = i
            break

    if last_sent_end != -1:
        clean = budget_text[: last_sent_end + 1].strip()
        # Guard against absurdly short cuts (e.g., a stray "Yes." in
        # the first sentence). Require at least 6 words in the kept
        # portion or fall through to ellipsis chop.
        if len(clean.split()) >= 6:
            return clean

    # Strategy 4: last resort — truncate mid-sentence + ellipsis.
    return budget_text.rstrip(".,;: ") + "…"


def _safety_path(
    assistant_text: str,
    session_style: str,
    softened_mode_active: bool = False,
) -> CommunicationControlResult:
    """Safety-acute exemption: do not modify the assistant_text at all.
    Just record whether the turn appears to have a "normal interview
    question during safety" violation (informational only — caller
    decides what to do).

    WO-LORI-SOFTENED-RESPONSE-01 note: this same path also fires when
    a softened-mode turn is in flight (chat_ws sets safety_triggered=
    True for both acute pattern matches AND DB-persisted softened
    state). For softened-mode turns we additionally record whether
    the response exceeded the SOFTENED_WORD_LIMIT (35 words), but
    we still do NOT mutate — the spec says no rewrite of safety/
    softened responses; let the operator see the violation and
    re-tune Layer 1 if it persists.

    2026-05-01 — softened-mode-aware fix (post-golfball-softened-on-v2).
    The "normal interview question during safety" check uses the wh-word
    + '?' pattern, which over-fires in softened mode where gentle
    invitations like "Would you like to talk about what's making you
    feel that way?" legitimately use wh-words. The check existed to
    catch ACUTE-frame failures where the LLM would route through a
    normal interview prompt mid-crisis. In softened mode the SOFTENED
    MODE composer directive owns the "no fresh interview question" rule,
    and the SOFTENED_WORD_LIMIT cap owns the budget. So when caller
    signals softened_mode_active=True, we skip the normal-question
    check entirely and rely on the composer + cap. The acute path
    (safety_triggered=True AND softened_mode_active=False) preserves
    the original behavior.
    """
    failures: List[str] = []
    has_safety_ack = bool(_SAFETY_ACKNOWLEDGMENT_RX.search(assistant_text))
    has_normal_q = bool(_SAFETY_NORMAL_QUESTION_RX.search(assistant_text))
    if has_normal_q and not has_safety_ack and not softened_mode_active:
        failures.append("normal_interview_question_during_safety")

    word_count = len(assistant_text.split())
    # Softened-mode word budget — softer cap than session_style default.
    # CRITICAL distinction: ACUTE safety responses legitimately run
    # 40-60 words (warm acknowledgment + 988 phrasing + soft re-engage
    # invitation), while SOFTENED-mode responses (post-acute, no fresh
    # trigger) should stay under 35 words per the spec. We can tell
    # the two apart at this layer by looking for safety-acknowledgment
    # tokens — acute responses always carry 988/hotline language, so
    # has_safety_ack=True is the acute signal. If there's no safety
    # ack AND we're in safety_triggered=True territory, we must be
    # in softened mode (or in a misrouted normal question, which
    # already flagged above).
    #
    # Imported lazily so question_atomicity / lori_reflection isolation
    # tests don't fail because of an unrelated import.
    try:
        from .lori_softened_response import SOFTENED_WORD_LIMIT
    except Exception:
        SOFTENED_WORD_LIMIT = 35
    if not has_safety_ack and word_count > SOFTENED_WORD_LIMIT:
        failures.append("softened_response_too_long")

    # WO-LORI-REFLECTION-02 Layer 3: softened-mode runtime shaping.
    # When softened_mode_active=True (post-acute, no fresh trigger) AND
    # the response exceeds SHAPER_SOFTENED_TURN_BUDGET (30 words), AND
    # the response is NOT carrying acute-safety-acknowledgment language
    # (988 / hotline / etc — those legitimately run longer), truncate
    # to the first sentence. Default-OFF behind the same flag as the
    # ordinary-path shaper. Acute responses (has_safety_ack=True) are
    # never shaped — their length is load-bearing for crisis pointers.
    final_text = assistant_text
    changed = False
    warnings: List[str] = []
    if (
        _reflection_shaping_enabled()
        and softened_mode_active
        and not has_safety_ack
        and word_count > 30  # SHAPER_SOFTENED_TURN_BUDGET
    ):
        try:
            from .lori_reflection import shape_reflection as _shape
            shaped, shape_actions = _shape(
                assistant_text=assistant_text,
                narrator_text="",  # softened-mode shaper doesn't need narrator content
                softened_mode_active=True,
            )
            if shape_actions and shape_actions[0] == "shaped_softened_truncated":
                final_text = shaped
                changed = True
                warnings.append("reflection_shaped:shaped_softened_truncated")
                word_count = len(final_text.split())
        except Exception:
            # Shaper is best-effort — never break a safety-path turn
            pass

    return CommunicationControlResult(
        original_text=assistant_text,
        final_text=final_text,
        changed=changed,
        failures=failures,
        warnings=warnings,
        question_count=final_text.count("?"),
        word_count=word_count,
        atomicity_failures=[],
        reflection_failures=[],
        session_style=session_style,
        safety_triggered=True,
    )


def enforce_lori_communication_control(
    assistant_text: str,
    user_text: str,
    *,
    safety_triggered: bool = False,
    session_style: str = "clear_direct",
    softened_mode_active: bool = False,
) -> CommunicationControlResult:
    """The single runtime enforcement entry point.

    Returns a CommunicationControlResult with possibly-truncated final_text
    and structured failure attribution. Caller (chat_ws) replaces
    assistant_text with result.final_text before sending the `done`
    event.

    Order of operations (each step modifies final_text):
      0. Safety path: exempt + validate-only
      1. Atomicity (truncate compounds)
      2. Question count (truncate to first '?' if multiple)
      3. Word-count limit per session_style (truncate preserving first '?')
      4. Reflection validation (REPORT-ONLY — no mutation)

    Empty assistant_text → returns unchanged with failures=[].
    """
    if not assistant_text or not assistant_text.strip():
        return CommunicationControlResult(
            original_text=assistant_text,
            final_text=assistant_text,
            changed=False,
            failures=[],
            warnings=[],
            question_count=0,
            word_count=0,
            atomicity_failures=[],
            reflection_failures=[],
            session_style=session_style,
            safety_triggered=safety_triggered,
        )

    # Step 0: safety exemption
    if safety_triggered:
        return _safety_path(
            assistant_text,
            session_style,
            softened_mode_active=softened_mode_active,
        )

    failures: List[str] = []
    warnings: List[str] = []
    current = assistant_text

    # Step 1: atomicity (truncate compounds)
    atom_text, atomicity_failures = enforce_question_atomicity(current)
    if atomicity_failures:
        if atom_text != current:
            current = atom_text

    # Step 2: question count
    question_count = current.count("?")
    if question_count > 1:
        failures.append("too_many_questions")
        current = _truncate_to_first_question(current)
        question_count = current.count("?")

    # Step 3: word-count limit per session_style (adaptive on narrator length).
    #
    # BUG-LORI-RESPONSE-CAP-FIXED-FOR-RICH-NARRATOR-01 (2026-05-07,
    # Chris's observation from Melanie Zollner live session): when the
    # narrator shares a rich multi-sentence turn, Lori legitimately
    # needs room to (a) reflect a concrete anchor back, (b) acknowledge
    # the substance, (c) ask one focused follow-up. A flat 55-word cap
    # for clear_direct can't fit all three when the narrator just gave
    # 80 words of story. Pre-fix, three Lori turns hit the cap and got
    # truncated mid-question.
    #
    # Solution: when the narrator's turn is rich (>= 50 words), allow
    # Lori an extra 35-word headroom on top of the base session-style
    # cap. Short narrator turns keep the tight original cap so brevity
    # discipline still applies for thin replies.
    base_word_limit = _SESSION_STYLE_WORD_LIMITS.get(session_style, _DEFAULT_WORD_LIMIT)
    narrator_word_count = len((user_text or "").split())
    if narrator_word_count >= 50:
        word_limit = base_word_limit + 35
    else:
        word_limit = base_word_limit
    word_count = len(current.split())
    if word_count > word_limit:
        failures.append("too_long")
        current = _truncate_to_word_limit(current, word_limit)
        word_count = len(current.split())

    # Step 3.5 (WO-LORI-REFLECTION-02): runtime shaping. Default-OFF
    # behind HORNELORE_REFLECTION_SHAPING=1. The locked design
    # constraint is: prompt-heavy reflection rules made Lori worse
    # (Patch B regressed golfball 4/8 → 1/8), so the next iteration
    # MUST be runtime shaping. shape_reflection() runs deterministic
    # rules over the LLM's output — never invents a narrator fact, only
    # re-arranges or trims what Lori already produced. Idempotent.
    shape_actions: List[str] = []
    if _reflection_shaping_enabled():
        shaped, shape_actions = shape_reflection(
            assistant_text=current,
            narrator_text=user_text or "",
            softened_mode_active=False,  # ordinary path; safety_path handles softened
        )
        if shape_actions and shape_actions[0] != "shaped_no_change":
            warnings.append(f"reflection_shaped:{shape_actions[0]}")
            current = shaped

    # Step 4: reflection validation (REPORT-ONLY per §5 of the spec —
    # reflection is content, deterministic rewrite would invent narrator
    # facts. v1 logs failures only. WO-LORI-REFLECTION-02 adds the
    # shaper above; this validator continues to flag any cases the
    # shaper didn't catch — e.g. echo_contains_diagnostic_language is
    # NOT in the shaper's lane (the shaper trims length, not content
    # violations) and remains report-only here.).
    _passed, reflection_failures = validate_memory_echo(
        assistant_text=current,
        user_text=user_text or "",
    )

    # Step 5: push-after-resistance (Phelan SIN 3 — too much arguing).
    # Single-turn detection: narrator-side resistance phrase + Lori-side
    # probe verb in the same turn. Report-only; never modifies output.
    # Skipped on safety/softened paths — those own no-probe via the
    # safety_path branch above.
    if _detect_push_after_resistance(user_text or "", current):
        failures.append("push_after_resistance")

    return CommunicationControlResult(
        original_text=assistant_text,
        final_text=current,
        changed=(current != assistant_text),
        failures=failures,
        warnings=warnings,
        question_count=question_count,
        word_count=word_count,
        atomicity_failures=atomicity_failures,
        reflection_failures=reflection_failures,
        session_style=session_style,
        safety_triggered=safety_triggered,
    )


__all__ = [
    "CommunicationControlResult",
    "enforce_lori_communication_control",
]
