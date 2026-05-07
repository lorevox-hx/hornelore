"""
WO-ARCH-07A Patch Set 2 — Memory Echo correction parsing module.

Provides:
  - Rule-based correction parsing (deterministic, no LLM)
  - One structured retry helper for near-valid JSON
  - Extraction hint schema for correction-facing fields
"""
import json
import re
from typing import Any, Callable, Dict, Optional, Tuple


# ── Extraction hints for correction-critical fields ─────────────────────────
# These are PARSE-style hints: one sentence describing what the field contains,
# so the LLM (or a future constrained decoder) knows what shape to expect.
CORRECTION_SCHEMA_HINTS: Dict[str, str] = {
    "identity.full_name": "Narrator's full legal or primary name as explicitly corrected by the narrator.",
    "identity.preferred_name": "Narrator's preferred everyday name or nickname if explicitly corrected.",
    "identity.date_of_birth": "Narrator's date of birth exactly as corrected, preserving month/day/year precision if given.",
    "identity.place_of_birth": "Narrator's birthplace city/state/country exactly as corrected.",
    "family.children.count": "The number of narrator's children if explicitly corrected.",
    "education_work.retirement": "Narrator's retirement status or correction to retirement wording.",
}


def _safe_json_load(raw: str) -> Any:
    """Parse JSON, stripping markdown fences if the model wrapped its output."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # Strip ```json ... ``` or ``` ... ```
        lines = cleaned.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return json.loads(cleaned)


def _extract_json_retry(
    llm_call: Callable[[str], str],
    prompt: str,
) -> Tuple[Optional[Any], Optional[str]]:
    """
    One retry only.

    Research-backed schema reflection: return structured error to the model once,
    then fail closed. This follows the Schema Reflection pattern from the
    validation research — structured error feedback for exactly one retry.
    """
    raw = llm_call(prompt)
    try:
        return _safe_json_load(raw), None
    except Exception as e1:
        retry_prompt = (
            prompt
            + "\n\nYour output was not valid JSON."
            + f"\nValidation error: {str(e1)}"
            + "\nReturn ONLY valid JSON matching the requested shape."
        )
        raw2 = llm_call(retry_prompt)
        try:
            return _safe_json_load(raw2), None
        except Exception as e2:
            return None, f"{e1}; retry_failed: {e2}"


def parse_correction_rule_based(text: str) -> Dict[str, Any]:
    """Deterministic rule-based correction parser.

    Extracts structured field updates from natural-language correction text.
    No LLM call. Returns a dict mapping field paths to corrected values OR
    special control entries (retraction-intents).

    Returned dict shapes:
      {"<field_path>": <new_value>}                  — corrected field
      {"_retracted": [<value1>, <value2>]}           — values the narrator
                                                       says they did NOT say
                                                       or are NOT real (e.g.,
                                                       "there was no Hannah")
      Empty dict means no correction could be parsed.

    BUG-LORI-CORRECTION-ABSORBED-NOT-APPLIED-01 Phase 3 (2026-05-07):
    Extended pattern set covering Melanie Zollner session evidence:
      - "Actually, we only had two children, not three"
        → family.children.count = 2 (corrected) AND retracted=3
      - "there was no Hannah I said hold my hand"
        → _retracted = ["Hannah"]
      - "I never said hate"
        → _retracted = ["hate"]
    """
    t = (text or "").strip()
    out: Dict[str, Any] = {}

    # Birthplace: "I was born in <place>"
    m = re.search(r"\bi was born in ([A-Za-z .,'-]+)$", t, re.I)
    if m:
        out["identity.place_of_birth"] = m.group(1).strip()

    # Father's name: "my father was <name>" or "my father's name was <name>"
    m = re.search(r"\bmy father(?:'s name)? was ([A-Za-z .,'-]+)$", t, re.I)
    if m:
        out["family.parents.father.name"] = m.group(1).strip()

    # Mother's name
    m = re.search(r"\bmy mother(?:'s name)? was ([A-Za-z .,'-]+)$", t, re.I)
    if m:
        out["family.parents.mother.name"] = m.group(1).strip()

    # Child count: "I had N children/kids/sons/daughters"
    m = re.search(r"\bi had (\d+) (?:children|kids|sons|daughters)\b", t, re.I)
    if m:
        out["family.children.count"] = int(m.group(1))

    # Child count present tense: "I have N children/kids"
    m = re.search(r"\bi have (\d+) (?:children|kids|sons|daughters)\b", t, re.I)
    if m:
        out["family.children.count"] = int(m.group(1))

    # Phase 3 (2026-05-07): "we only had N children/kids, not M" —
    # the Melanie Zollner pattern. Captures both corrected count AND
    # the retracted (wrong) count for audit + composer surfacing.
    # Also handles "we had only N" / "I only had N" / "had two not three".
    _word_to_int = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    }
    def _to_int(s: str) -> Optional[int]:
        s = (s or "").strip().lower()
        if s.isdigit():
            try: return int(s)
            except Exception: return None
        return _word_to_int.get(s)

    m = re.search(
        r"\b(?:we|i)\s+(?:only\s+)?had\s+(only\s+)?(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
        r"(?:children|kids|sons|daughters)"
        r"(?:[\s,]+not\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten))?",
        t, re.I,
    )
    if m:
        corrected = _to_int(m.group(2))
        retracted = _to_int(m.group(3)) if m.group(3) else None
        if corrected is not None:
            out["family.children.count"] = corrected
            if retracted is not None and retracted != corrected:
                out.setdefault("_retracted", []).append(retracted)

    # Phase 3 (2026-05-07): "there was no <X>" — narrator retracting
    # something Lori (or STT) introduced as a fact. Captures up to 3
    # words of <X> as the retracted token (covers single names, short
    # phrases). Followed-by clause (" I said Y") is best-effort and
    # not parsed here — the retracted token alone is enough for the
    # projection_writer to scrub from pendingSuggestions. Bare
    # "there was no" without a captured term is rejected (length<2).
    for m in re.finditer(
        r"\bthere\s+(?:was|were)\s+no\s+([A-Za-z][A-Za-z'-]{1,30}(?:\s+[A-Za-z][A-Za-z'-]{1,30}){0,2})\b",
        t, re.I,
    ):
        token = m.group(1).strip()
        # Reject super-short or stop-word-only matches
        if len(token) >= 2 and token.lower() not in {"way", "one", "more", "such", "doubt"}:
            out.setdefault("_retracted", []).append(token)

    # Phase 3 (2026-05-07): "I never said <X>" — narrator retracting
    # a word Lori or STT attributed to them. Captures a short phrase.
    for m in re.finditer(
        r"\bi\s+never\s+said\s+([A-Za-z][A-Za-z'-]{1,30}(?:\s+[A-Za-z][A-Za-z'-]{1,30}){0,2})\b",
        t, re.I,
    ):
        token = m.group(1).strip()
        if len(token) >= 2:
            out.setdefault("_retracted", []).append(token)

    # Phase 3 (2026-05-07): "I meant <X>, not <Y>" — explicit
    # substitution. <X> goes to retracted-as-correction; <Y> retracted.
    # No specific field mapping (that requires context); composer
    # acknowledges the substitution by name. This catches Melanie's
    # "I meant pinch not paint" pattern.
    m = re.search(
        r"\bi\s+meant\s+([A-Za-z][A-Za-z'-]{1,30})(?:\s*,?\s+not\s+([A-Za-z][A-Za-z'-]{1,30}))?",
        t, re.I,
    )
    if m and m.group(1):
        if m.group(2):
            out.setdefault("_retracted", []).append(m.group(2).strip())
        # The corrected token is recorded as a free-form _meant marker
        # for the composer to acknowledge ("Got it — pinch, not paint").
        out["_meant"] = m.group(1).strip()

    # Retirement: "I never really retired"
    m = re.search(r"\bi never (?:really )?retired\b", t, re.I)
    if m:
        out["education_work.retirement"] = "never fully retired"

    return out
