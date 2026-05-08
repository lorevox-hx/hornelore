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

    # BUG-ML-LORI-CORRECTION-PARSER-VALUE-OVERCAPTURE-01 (2026-05-07):
    # Eight value-capture patterns below previously over-greedy-captured
    # the retraction clause ("Lima, no en Cuzco" → place="Lima, no en
    # Cuzco" instead of place="Lima" + _retracted=["Cuzco"]). The fix:
    # non-greedy value capture + optional retraction-clause group at the
    # end of the regex. When the retraction group fires, its captured
    # value is added to _retracted via _capture_retraction(). Comma is
    # KEPT in the value char class so legitimate "Buenos Aires, Argentina"
    # cases still parse correctly.
    #
    # Retraction markers:
    #   English: ", not <retracted>"
    #   Spanish: ", no <retracted>"  OR  ", no en <retracted>" (place form)
    _EN_VALUE_CC = r"A-Za-z .,'\-"
    _ES_VALUE_CC = r"A-Za-zÁÉÍÓÚÑáéíóúñ .,'\-"
    # English retraction tail: ", not X" — captures retraction value as group
    _EN_RETRACT_TAIL = r"(?:,\s+not\s+([A-Za-z .'\-]+?))?"
    # Spanish retraction tail: ", no [en] X" — `en` optional for places
    _ES_RETRACT_TAIL = r"(?:,\s+no(?:\s+en)?\s+([A-Za-zÁÉÍÓÚÑáéíóúñ .'\-]+?))?"

    def _capture_retraction(retracted_raw: Optional[str]) -> None:
        """Append a retraction value (from the optional group) to
        out['_retracted'] when present + non-empty."""
        if not retracted_raw:
            return
        val = retracted_raw.strip()
        if val:
            out.setdefault("_retracted", []).append(val)

    # Birthplace: "I was born in <place>" — with optional ", not <retracted>"
    m = re.search(
        r"\bi was born in ([" + _EN_VALUE_CC + r"]+?)" + _EN_RETRACT_TAIL + r"\s*$",
        t, re.I,
    )
    if m:
        out["identity.place_of_birth"] = m.group(1).strip()
        _capture_retraction(m.group(2))

    # WO-ML-05B (Phase 5B multilingual capture, 2026-05-07):
    # Spanish birthplace — "nací en X" / "yo nací en X". Accent-
    # flexible (Whisper STT may drop the accent on "nací" → "naci").
    # Spanish proper-noun chars (á/é/í/ó/ú/ñ) accepted in the
    # captured place name. Always-run-both posture parallel to 5A:
    # English patterns continue to fire on English content; Spanish
    # patterns fire on Spanish content; both fire on a code-switched
    # turn. Pure English never produces a Spanish false-positive
    # because "nací" doesn't appear in English prose.
    m = re.search(
        r"\b(?:yo\s+)?nac[íi] en ([" + _ES_VALUE_CC + r"]+?)" + _ES_RETRACT_TAIL + r"\s*$",
        t, re.I,
    )
    if m:
        out["identity.place_of_birth"] = m.group(1).strip()
        _capture_retraction(m.group(2))

    # Father's name: "my father was <name>" or "my father's name was <name>"
    m = re.search(
        r"\bmy father(?:'s name)? was ([" + _EN_VALUE_CC + r"]+?)" + _EN_RETRACT_TAIL + r"\s*$",
        t, re.I,
    )
    if m:
        out["family.parents.father.name"] = m.group(1).strip()
        _capture_retraction(m.group(2))

    # WO-ML-05B Spanish father's name — natural Spanish constructions:
    #   "mi padre se llamaba X"  / "mi papá se llamaba X"  / "mi papi
    #    se llamaba X"
    #   "el nombre de mi padre era X"  / "el nombre de mi papá era X"
    # Accent-flexible on "papá" (Whisper may drop the accent → "papa").
    m = re.search(
        r"\bmi (?:padre|pap[áa]|papi) se llamaba ([" + _ES_VALUE_CC + r"]+?)" + _ES_RETRACT_TAIL + r"\s*$",
        t, re.I,
    )
    if m:
        out["family.parents.father.name"] = m.group(1).strip()
        _capture_retraction(m.group(2))
    m = re.search(
        r"\bel nombre de mi (?:padre|pap[áa]|papi) era ([" + _ES_VALUE_CC + r"]+?)" + _ES_RETRACT_TAIL + r"\s*$",
        t, re.I,
    )
    if m:
        out["family.parents.father.name"] = m.group(1).strip()
        _capture_retraction(m.group(2))

    # Mother's name
    m = re.search(
        r"\bmy mother(?:'s name)? was ([" + _EN_VALUE_CC + r"]+?)" + _EN_RETRACT_TAIL + r"\s*$",
        t, re.I,
    )
    if m:
        out["family.parents.mother.name"] = m.group(1).strip()
        _capture_retraction(m.group(2))

    # WO-ML-05B Spanish mother's name — same construction set as father.
    m = re.search(
        r"\bmi (?:madre|mam[áa]|mami) se llamaba ([" + _ES_VALUE_CC + r"]+?)" + _ES_RETRACT_TAIL + r"\s*$",
        t, re.I,
    )
    if m:
        out["family.parents.mother.name"] = m.group(1).strip()
        _capture_retraction(m.group(2))
    m = re.search(
        r"\bel nombre de mi (?:madre|mam[áa]|mami) era ([" + _ES_VALUE_CC + r"]+?)" + _ES_RETRACT_TAIL + r"\s*$",
        t, re.I,
    )
    if m:
        out["family.parents.mother.name"] = m.group(1).strip()
        _capture_retraction(m.group(2))

    # Child count: "I had N children/kids/sons/daughters"
    m = re.search(r"\bi had (\d+) (?:children|kids|sons|daughters)\b", t, re.I)
    if m:
        out["family.children.count"] = int(m.group(1))

    # Child count present tense: "I have N children/kids"
    m = re.search(r"\bi have (\d+) (?:children|kids|sons|daughters)\b", t, re.I)
    if m:
        out["family.children.count"] = int(m.group(1))

    # WO-ML-05B Spanish child count — past + present tense, singular
    # + plural narrator. Verb forms:
    #   tuve     — I had       (preterite, 1st person singular)
    #   tuvimos  — we had      (preterite, 1st person plural)
    #   tengo    — I have      (present, 1st person singular)
    #   tenemos  — we have     (present, 1st person plural)
    # Noun forms cover hijos / hijas / niños / niñas / chamacos
    # (Mexican Spanish for "kids"); ñ is accent-flexible. The
    # compound-correction pattern further down handles "tuvimos N,
    # no M"; this simpler pattern catches the bare declaration.
    # Spanish written numbers (uno..diez) accepted alongside digits.
    m = re.search(
        r"\b(?:yo\s+)?(?:tuve|tuvimos|tengo|tenemos)\s+"
        r"(\d+|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+"
        r"(?:hijos?|hijas?|ni[ñn]os?|ni[ñn]as?|chamacos?|chamacas?)\b",
        t, re.I,
    )
    if m:
        _bare_word_to_int_es = {
            "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
            "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
        }
        s = m.group(1).strip().lower()
        if s.isdigit():
            try:
                out["family.children.count"] = int(s)
            except Exception:
                pass
        elif s in _bare_word_to_int_es:
            out["family.children.count"] = _bare_word_to_int_es[s]

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

    # WO-ML-05B Spanish compound count correction — the Melanie Zollner
    # pattern in Spanish:
    #   "Sólo tuvimos dos hijos, no tres"
    #   "Tuvimos dos hijos, no tres"
    #   "Eran tres no dos" (preterite copula form)
    #   "No eran tres, eran dos" (negation-first form)
    # Spanish written numbers (uno/una..diez) accepted alongside digits.
    # Accent-flexible on "sólo" → "solo" (RAE accepts both).
    _word_to_int_es = {
        "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
        "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    }
    def _to_int_es(s: str) -> Optional[int]:
        s = (s or "").strip().lower()
        if s.isdigit():
            try: return int(s)
            except Exception: return None
        return _word_to_int_es.get(s)

    # Pattern 1: "(sólo) tuvimos/tuve N hijos, no M" — corrected first
    m = re.search(
        r"\b(?:s[óo]lo\s+)?(?:tuvimos|tuve|tengo|tenemos)\s+"
        r"(\d+|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+"
        r"(?:hijos?|hijas?|ni[ñn]os?|ni[ñn]as?|chamacos?|chamacas?)"
        r"(?:[\s,]+no\s+(\d+|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez))?",
        t, re.I,
    )
    if m:
        corrected = _to_int_es(m.group(1))
        retracted = _to_int_es(m.group(2)) if m.group(2) else None
        if corrected is not None:
            out["family.children.count"] = corrected
            if retracted is not None and retracted != corrected:
                out.setdefault("_retracted", []).append(retracted)

    # Pattern 2: "no eran/fueron M, eran/fueron N" — negation-first
    # form. Captures retracted (M, the wrong count) and corrected
    # (N, the right count).
    m = re.search(
        r"\bno\s+(?:eran|fueron|hab[íi]a|hubo)\s+"
        r"(\d+|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)"
        r"[\s,]+(?:eran|fueron|hab[íi]a|hubo|fue)\s+"
        r"(\d+|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)",
        t, re.I,
    )
    if m:
        retracted = _to_int_es(m.group(1))
        corrected = _to_int_es(m.group(2))
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

    # WO-ML-05B Spanish "no había/no hubo <X>" / "no era <X>" —
    # narrator retracting a fact Lori (or STT) introduced. The two
    # most natural Spanish copular negations:
    #   "no había Hannah, dije sostén la mano"  (there wasn't Hannah)
    #   "no era Sonora, era Sinaloa"            (it wasn't Sonora)
    # Accent-flexible "había" → "habia" (Whisper-degraded). Accept
    # Spanish proper-noun chars (á/é/í/ó/ú/ñ) in the captured token.
    # Stop-word-only matches rejected per the English equivalent.
    # Spanish written number words also rejected — "no eran tres,
    # eran dos" is handled by the count-correction pattern above
    # and the bare "tres" captured here would be a duplicate signal
    # the projection_writer would have to disambiguate. Cleaner to
    # block at source.
    _ES_RETRACT_STOPWORDS = {
        "nadie", "nada", "ninguno", "ninguna", "más", "mas",
        # Spanish number words (handled by count-correction pattern)
        "uno", "una", "dos", "tres", "cuatro", "cinco",
        "seis", "siete", "ocho", "nueve", "diez",
    }
    for m in re.finditer(
        r"\bno\s+(?:hab[íi]a|hubo|era|fue|son|eran|fueron)\s+"
        r"([A-Za-zÁÉÍÓÚÑáéíóúñ][A-Za-zÁÉÍÓÚÑáéíóúñ'-]{1,30}"
        r"(?:\s+[A-Za-zÁÉÍÓÚÑáéíóúñ][A-Za-zÁÉÍÓÚÑáéíóúñ'-]{1,30}){0,2})\b",
        t, re.I,
    ):
        token = m.group(1).strip()
        # Reject pure-digit or Spanish-number-word matches and
        # stop-words from above. The token's FIRST word is what we
        # check against the number set since multi-word captures
        # like "tres dos" would still want to be rejected.
        first_word = token.split()[0].lower() if token else ""
        if len(token) >= 2 and first_word not in _ES_RETRACT_STOPWORDS and not token.replace(" ", "").isdigit():
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

    # WO-ML-05B Spanish "nunca dije <X>" / "yo nunca dije <X>" —
    # narrator retracting a word the system attributed to them.
    # Mirrors the English shape; same up-to-3-word capture.
    for m in re.finditer(
        r"\b(?:yo\s+)?nunca\s+dije\s+"
        r"([A-Za-zÁÉÍÓÚÑáéíóúñ][A-Za-zÁÉÍÓÚÑáéíóúñ'-]{1,30}"
        r"(?:\s+[A-Za-zÁÉÍÓÚÑáéíóúñ][A-Za-zÁÉÍÓÚÑáéíóúñ'-]{1,30}){0,2})\b",
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

    # WO-ML-05B Spanish "quería decir <X>, no <Y>" / "quise decir
    # <X>, no <Y>" / "lo que quise decir fue <X>, no <Y>" — explicit
    # substitution mirroring the English shape. Two preterite forms
    # accepted ("quería" imperfect, "quise" preterite). Accent-
    # flexible on "quería" → "queria". Captures up to 2 capital-led
    # words for both _meant and _retracted so multi-word place names
    # ("Buenos Aires", "Ciudad de México", "Lima Perú") survive.
    # The corrected token populates _meant; the retracted token (if
    # present) joins _retracted.
    _ES_MEANT_TOKEN = (
        r"([A-Za-zÁÉÍÓÚÑáéíóúñ][A-Za-zÁÉÍÓÚÑáéíóúñ'-]{1,30}"
        r"(?:\s+[A-Za-zÁÉÍÓÚÑáéíóúñ][A-Za-zÁÉÍÓÚÑáéíóúñ'-]{1,30}){0,1})"
    )
    m = re.search(
        r"\b(?:lo\s+que\s+)?quer[íi]a\s+decir\s+"
        + _ES_MEANT_TOKEN
        + r"(?:\s*,?\s+no\s+" + _ES_MEANT_TOKEN + r")?",
        t, re.I,
    )
    if m and m.group(1):
        if m.group(2):
            out.setdefault("_retracted", []).append(m.group(2).strip())
        # Composer downstream will acknowledge: "Entendido — X, no Y."
        out["_meant"] = m.group(1).strip()
    else:
        m = re.search(
            r"\bquise\s+decir\s+"
            + _ES_MEANT_TOKEN
            + r"(?:\s*,?\s+no\s+" + _ES_MEANT_TOKEN + r")?",
            t, re.I,
        )
        if m and m.group(1):
            if m.group(2):
                out.setdefault("_retracted", []).append(m.group(2).strip())
            out["_meant"] = m.group(1).strip()

    # Retirement: "I never really retired"
    m = re.search(r"\bi never (?:really )?retired\b", t, re.I)
    if m:
        out["education_work.retirement"] = "never fully retired"

    # WO-ML-05B Spanish retirement — "nunca me jubilé" / "nunca me
    # retiré" / "no me jubilé realmente". Two verb forms accepted
    # (jubilar / retirar — both used for retirement in Spanish, with
    # regional + register variation). Accent-flexible "jubilé" →
    # "jubile" / "retiré" → "retire" for Whisper-degraded input.
    m = re.search(
        r"\b(?:nunca|jam[áa]s)\s+me\s+(?:jubil[ée]|retir[ée])\b",
        t, re.I,
    )
    if m:
        out["education_work.retirement"] = "never fully retired"
    else:
        m = re.search(
            r"\bno\s+me\s+(?:jubil[ée]|retir[ée])\s+(?:realmente|de\s+verdad|del\s+todo)\b",
            t, re.I,
        )
        if m:
            out["education_work.retirement"] = "never fully retired"

    return out
