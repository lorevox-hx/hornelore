"""WO-LORI-STORY-CAPTURE-01 Phase 1A Commit 3a — story trigger detection.

Post-turn classifier. Decides whether a narrator turn merits creating a
story_candidate row. Pure functions, no I/O, zero extraction-stack
imports — sits cleanly under the LAW 3 INFRASTRUCTURE gate.

Two trigger paths (per WO §3.3):
  * full_threshold        — long story with at least one scene anchor
                            (duration ≥ 30s AND words ≥ 60 AND ≥1 anchor)
  * borderline_scene_anchor — short turn rescued by HIGH anchor density
                            (anchors ≥ 3) — catches Janice's actual
                            mastoidectomy turn (~25s/50w but rich in
                            place + relative-time + person-relation
                            references)

Returns None when neither path fires. Caller decides what to do then
(default: skip story_candidate creation, let extraction run as normal).

Thresholds are env-tunable so an operator can dial them per narrator
without a code change. Defaults match the WO spec.
"""
from __future__ import annotations

import os
import re
from typing import List, Optional


# ── Thresholds (env-tunable) ──────────────────────────────────────────────

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# Recomputed per call so tests / live operators can re-tune at runtime
# without re-importing the module.
def _min_duration_sec() -> float:
    return _env_float("STORY_TRIGGER_MIN_DURATION_SEC", 30.0)


def _min_words() -> int:
    return _env_int("STORY_TRIGGER_MIN_WORDS", 60)


def _borderline_anchor_count() -> int:
    return _env_int("STORY_TRIGGER_BORDERLINE_ANCHOR_COUNT", 3)


# ── WO-ML-EX-RICH-SHORT-NARRATIVE-01 (2026-05-09) ───────────────────────
# Spanish narrators (and elder narrators in general) often speak in
# shorter, more compact emotive bursts than the English-test-corpus
# thresholds were tuned for. A turn like
#   "Hola Lori, me llamo María. Cuando mi abuela hablaba de Perú,
#    yo escuchaba su voz y me sentía cerca de ella."
# (21 words, 15s, 2 anchors) is rich content but fails ALL three
# existing trigger gates (min_words=60, min_duration=30s, borderline=3).
# Result: Mary's grandmother story never reached story_candidates table.
#
# Add a third trigger that catches "rich short narratives": a turn with
# at least ONE place anchor AND at least ONE other anchor type (person
# or relative-time), plus a minimum word + duration floor to avoid
# false-positive on greetings / short confirmations.
#
# Tunable via env so operator can tighten/loosen without code change:
#   STORY_TRIGGER_RICH_SHORT_MIN_WORDS=15
#   STORY_TRIGGER_RICH_SHORT_MIN_DURATION_SEC=10
def _rich_short_min_words() -> int:
    return _env_int("STORY_TRIGGER_RICH_SHORT_MIN_WORDS", 15)


def _rich_short_min_duration_sec() -> float:
    return _env_float("STORY_TRIGGER_RICH_SHORT_MIN_DURATION_SEC", 10.0)


# ── Scene-anchor detection ────────────────────────────────────────────────
#
# Conservative bigram detection, NOT loose keyword presence. Janice
# saying "I was very little" is not a scene anchor; "in Spokane" is.
# The dimensions:
#   1. PLACE — explicit place noun OR matches proper-noun place pattern
#   2. RELATIVE_TIME — phrasing that anchors the memory in time
#   3. PERSON_RELATION — family/role reference ("my dad", "my mom",
#      "my grandmother", etc.)
#
# Each dimension that fires contributes 1 to the anchor count. Total
# range is 0–3 per turn.

# Place words split into two tiers to keep bare-reference false positives
# out (a 2026-04-30 reviewer caught "School was hard" / "Kitchen was tidy"
# firing as place anchors against the docstring's stated intent — bug was
# real, fixed before 3b banks):
#
# Tier 1 (BARE): institutional / industrial nouns whose bare mention is
# overwhelmingly locational. "Hospital was crowded" reads as place.
#
# Tier 2 (PREP_REQUIRED): common nouns that ALSO denote places. These
# only count as place anchors when preceded by a place preposition
# ("in the kitchen", "at school", "to the barn"). "Kitchen was tidy"
# is a state predicate about an object and does NOT fire.
_PLACE_NOUNS_BARE = {
    "hospital", "church", "factory", "fairgrounds",
}

# `plant` and `mill` were originally Tier 1 but a 2026-04-30 reviewer
# caught them overfiring on bare predicate uses ("The plant died.",
# "They mill around.") because both nouns also act as common nouns
# ("a houseplant") and as verbs ("mill around"). Demoted to Tier 2 —
# they only count as place anchors with a place preposition
# ("at the plant", "to the mill", "near the aluminum plant").
_PLACE_NOUNS_PREP_REQUIRED = {
    "plant", "mill",
    "farm", "ranch", "shop", "store",
    "kitchen", "yard", "porch",
    "river", "lake", "park",
    "neighborhood", "town", "village", "city", "county",
    "school", "library", "barn", "garage", "alley",
}

# Word-boundary match (the previous substring approach matched "plant"
# inside "implant" and "mill" inside "million" — silently correct on
# the canonical Janice text but a real risk elsewhere).
_PLACE_NOUN_BARE_RE = re.compile(
    r"\b(?:" + "|".join(sorted(_PLACE_NOUNS_BARE)) + r")\b",
    re.IGNORECASE,
)

# Tier 2 must be preceded by a place preposition. Optional determiner
# (the / a / my / etc.) followed by 0–2 lowercase adjective tokens
# before the noun ("at the aluminum plant", "in the small white
# kitchen"). The adjective slot is bounded at 2 to keep "at home with
# my plant" from sneaking in via greedy consumption.
_PLACE_NOUN_PREP_RE = re.compile(
    r"\b(?:in|at|to|from|near|outside|inside|behind|by|around|through|"
    r"over|across|beside|past|toward|towards)\s+"
    r"(?:(?:the|a|an|my|our|her|his|their)\s+)?"
    r"(?:[a-z]+\s+){0,2}"
    r"(?:" + "|".join(sorted(_PLACE_NOUNS_PREP_REQUIRED)) + r")\b",
    re.IGNORECASE,
)

# ── WO-ML-05A (Phase 5A multilingual capture, 2026-05-07) ─────────────
# Spanish parallel pattern sets. Always run alongside the English
# patterns above (no language gating) so code-switched narrators
# ("I was born in Spokane pero nos mudamos a Sonora") get full
# coverage and pure English narrators are byte-stable (Spanish words
# never appear in pure English prose, so Spanish patterns produce
# zero false positives on the existing English fixture set).
#
# Trade-off: each anchor matcher runs ~2x the regex evaluations per
# turn. Acceptable — story_trigger fires once per turn, not per chunk.

# Tier 1 BARE (es): institutional / industrial nouns whose bare
# mention is overwhelmingly locational. Same posture as the English
# Tier 1 set. Conservative — common Spanish nouns that ALSO denote
# objects (e.g. "fábrica de chocolate" vs "fábrica" alone is locational)
# stay in Tier 2.
#
# WO-ML-05A.1 hardening (2026-05-07): Whisper STT occasionally drops
# Spanish diacritics — outputs "fabrica" instead of "fábrica", "rio"
# instead of "río", "callejon" instead of "callejón". The bare/prep
# regexes are case-insensitive but accent-sensitive in Python's re
# module by default, so without the unaccented variants below the
# anchor would silently miss on STT-degraded transcripts. Adding the
# unaccented form as a parallel alias is cheaper than running a full
# diacritic-stripper before matching, and keeps the regex set
# transparent for review.
_PLACE_NOUNS_BARE_ES = {
    "hospital",        # same form as English; cognate
    "iglesia",         # church
    "fábrica", "fabrica",   # factory (accent + Whisper-degraded)
    "parroquia",       # parish (church)
    "capilla",         # chapel
    "monasterio",      # monastery
    "cementerio",      # cemetery
    "feria",           # fair / fairgrounds
}

# Tier 2 PREP_REQUIRED (es): common nouns that denote places. Only
# count as place anchors after a Spanish place preposition.
_PLACE_NOUNS_PREP_REQUIRED_ES = {
    "casa",            # house / home
    "granja",          # farm
    "rancho",          # ranch
    "finca",           # estate / farm (rural)
    "hacienda",        # plantation / estate
    "tienda",          # shop / store
    "mercado",         # market
    "cocina",          # kitchen
    "patio",           # courtyard / patio
    "porche",          # porch
    "río", "rio",      # river (accent + Whisper-degraded)
    "lago",            # lake
    "parque",          # park
    "barrio",          # neighborhood
    "vecindario",      # neighborhood (alt)
    "pueblo",          # town / village
    "aldea",           # small village
    "ciudad",          # city
    "condado",         # county
    "escuela",         # school
    "colegio",         # school (esp. Catholic / private school)
    "biblioteca",      # library
    "granero",         # barn
    "garaje",          # garage
    "callejón", "callejon",  # alley (accent + Whisper-degraded)
    "cuadra",          # block (city block / stable)
    "establo",         # stable
    "campo",           # field / countryside
    "milpa",           # corn field (Mexican / Central American)
}

_PLACE_NOUN_BARE_ES_RE = re.compile(
    r"\b(?:" + "|".join(sorted(_PLACE_NOUNS_BARE_ES)) + r")\b",
    re.IGNORECASE,
)

# Spanish place prepositions: en (in/at), a (to), de (from), cerca de
# (near), fuera de (outside of), dentro de (inside of), detrás de
# (behind), por (around/through), sobre (over), a través de (across),
# hacia (toward), desde (from), pasando (past). The compound preps
# (cerca de / fuera de / etc.) are matched as multi-word alternatives.
#
# Adjective slot is bounded at 0-2 lowercase tokens, same posture as
# English. The optional determiner set ('el', 'la', 'los', 'las',
# 'un', 'una', 'unos', 'unas', 'mi', 'mis', 'nuestra', 'nuestro',
# 'nuestras', 'nuestros', 'su', 'sus') matches Spanish article +
# possessive forms before the noun.
#
# WO-ML-05A.1 hardening (2026-05-07): Spanish contracts "a + el = al"
# and "de + el = del". So "junto al callejón", "cerca del río", "fuera
# del pueblo", "dentro del granero" are all valid Spanish place
# constructions that the prior pattern missed because it required
# explicit "a el" / "de el" forms. Adding the contracted variants as
# alternatives keeps single-arg preps ("en", "a", "de") working AND
# adds the contracted compound forms ("al", "del", "junto al",
# "cerca del", etc.). When a contraction is used, the determiner
# slot below should NOT also fire (Spanish doesn't say "del el río"),
# but the regex is forgiving — the determiner branch is optional so
# excess matches don't accumulate falsely.
_PLACE_NOUN_PREP_ES_RE = re.compile(
    r"\b(?:en|a|al|de|del|cerca\s+de|cerca\s+del|"
    r"fuera\s+de|fuera\s+del|dentro\s+de|dentro\s+del|"
    r"detr[áa]s\s+de|detr[áa]s\s+del|"
    r"por|sobre|a\s+trav[ée]s\s+de|a\s+trav[ée]s\s+del|"
    r"hacia|desde|pasando|junto\s+a|junto\s+al)\s+"
    r"(?:(?:el|la|los|las|un|una|unos|unas|mi|mis|"
    r"nuestra|nuestro|nuestras|nuestros|su|sus)\s+)?"
    r"(?:[a-záéíóúñ]+\s+){0,2}"
    r"(?:" + "|".join(sorted(_PLACE_NOUNS_PREP_REQUIRED_ES)) + r")\b",
    re.IGNORECASE,
)

# Relative-time phrasing — these are the elder-narrator markers that
# place a memory without forcing precision. Multi-word patterns must
# match as bigrams or trigrams; single tokens like "remember" are too
# loose and would fire on every other turn.
_RELATIVE_TIME_PATTERNS = (
    re.compile(r"\bwhen i was\b", re.IGNORECASE),
    re.compile(r"\bwhen we were\b", re.IGNORECASE),
    re.compile(r"\bback then\b", re.IGNORECASE),
    re.compile(r"\bin those days\b", re.IGNORECASE),
    re.compile(r"\bgrowing up\b", re.IGNORECASE),
    re.compile(r"\bbefore (?:the |my )?(?:war|school|kids|that|then)\b", re.IGNORECASE),
    re.compile(r"\bafter (?:the |my )?(?:war|wedding|funeral|service)\b", re.IGNORECASE),
    re.compile(r"\b(?:as|when) a (?:child|kid|girl|boy|teenager)\b", re.IGNORECASE),
    re.compile(r"\bone (?:summer|winter|spring|fall|day|night|morning|evening)\b", re.IGNORECASE),
    re.compile(r"\b(?:in|during) (?:the |my )?(?:summer|winter|spring|fall|war|childhood)\b", re.IGNORECASE),
    # 2026-04-30 polish: live narrator turn "He walked because gas was so
    # expensive because of the war" should anchor in time. The existing
    # "during/in the war" pattern misses "because of the war" / "due to
    # the war" / "since the war" — common phrasings for elder narrators
    # locating a memory by historical era.
    re.compile(r"\b(?:because|due to|since) (?:of )?(?:the |that |my )?(?:war|depression|drought|flu|epidemic)\b", re.IGNORECASE),
)

# Person-relation phrasing — narrators referencing the people who
# populated the scene. "my dad", "my mother", "my grandmother". Bare
# pronouns and common names don't fire.
_PERSON_RELATION_PATTERNS = (
    re.compile(r"\bmy (?:dad|father|papa|pop)\b", re.IGNORECASE),
    re.compile(r"\bmy (?:mom|mother|mama|ma)\b", re.IGNORECASE),
    re.compile(r"\bmy (?:brother|sister|sibling)s?\b", re.IGNORECASE),
    re.compile(r"\bmy (?:grandmother|grandma|granny|nana)\b", re.IGNORECASE),
    re.compile(r"\bmy (?:grandfather|grandpa|granddad|papa)\b", re.IGNORECASE),
    re.compile(r"\bmy (?:aunt|uncle|cousin)s?\b", re.IGNORECASE),
    re.compile(r"\bmy (?:husband|wife|spouse)\b", re.IGNORECASE),
    re.compile(r"\bmy (?:son|daughter|kids?|children)\b", re.IGNORECASE),
)

# 2026-04-30 polish: bare-capital relation usage. English convention is
# that family-relation nouns capitalize when used AS A PROPER NOUN
# referring to a specific person (the speaker's actual mother/father):
# "Dad walked nights at the plant" vs "every dad walked nights." The
# capitalized form is conventional narrator shorthand for "my dad" and
# narrators frequently use it without the possessive. Case-sensitive
# regex (no IGNORECASE) so we only fire on the proper-noun form, which
# protects against false positives like "MOM" in caps-lock or "pop" in
# the verb sense. Word boundary at start prevents matching "Madame".
_BARE_CAPITAL_RELATION_RE = re.compile(
    r"\b(?:Dad|Mom|Mama|Mother|Father|Papa|Pop|Mommy|Daddy|"
    r"Grandma|Grandpa|Granny|Nana|Gramps|Granddad)\b"
)

# Proper-noun place pattern: capitalized word(s) that look like a place
# name. Conservative — must be either after a place preposition (in/at/from)
# OR a multi-word capitalized run ("Grand Forks", "North Dakota").
#
# 2026-04-30 polish: use inline (?i:...) flag so the PREP is matched
# case-insensitively while the noun still REQUIRES a capital. This is
# what makes the lowercase-input fallback in _matches_place work —
# "in spokane" → text.title() → "In Spokane" still matches because
# "In" matches the case-insensitive prep, "Spokane" matches the
# capital noun. Without the inline flag, title-casing "in" → "In"
# breaks the existing regex.
_PROPER_NOUN_PLACE_AFTER_PREP = re.compile(
    r"\b(?i:in|at|from|to|near|outside)\s+([A-Z][a-zA-Z]+(?:[ \-][A-Z][a-zA-Z]+)*)",
)
_PROPER_NOUN_MULTI_WORD = re.compile(
    r"\b([A-Z][a-zA-Z]+)\s+([A-Z][a-zA-Z]+)\b",
)

# WO-ML-05A (Phase 5A): Spanish counterpart. Capitalized place name
# after a Spanish place preposition: "en Lima", "a México", "de Cuba",
# "cerca de Buenos Aires", "fuera de Madrid". Compound preps are
# matched as alternatives. The capitalized noun slot is the same as
# the English version — accepts multi-word place names like "Buenos
# Aires", "Ciudad de México", "Las Cruces".
#
# WO-ML-05A.1 hardening (2026-05-07): same al/del contraction support
# applied here so "fuera del Sonora" / "cerca del Río Bravo" /
# "junto al Lago Atitlán" all anchor on the proper-noun pattern.
_PROPER_NOUN_PLACE_AFTER_PREP_ES = re.compile(
    r"\b(?i:en|a|al|de|del|"
    r"cerca\s+de|cerca\s+del|fuera\s+de|fuera\s+del|"
    r"dentro\s+de|dentro\s+del|junto\s+a|junto\s+al|"
    r"hacia|desde)\s+"
    r"([A-Z][a-záéíóúñA-Z]+(?:[ \-][A-Z][a-záéíóúñA-Z]+)*)",
)

# Spanish relative-time phrasing — elder-narrator markers that anchor
# a memory in time. Bigram / trigram patterns; single tokens like
# "recordar" are too loose. Mirrors the English set's coverage:
# childhood, "back then", before/after-X, during-summer, day/night.
_RELATIVE_TIME_PATTERNS_ES = (
    # "cuando era niña/niño" / "cuando éramos niños"
    re.compile(r"\bcuando era (?:ni[ñn][oa]|peque[ñn][oa]|chiquit[oa]|joven|chico|chica)\b", re.IGNORECASE),
    re.compile(r"\bcuando ten[íi]a\b", re.IGNORECASE),  # "cuando tenía cinco años"
    re.compile(r"\bcuando [ée]ramos (?:ni[ñn]os|peque[ñn]os|j[óo]venes)\b", re.IGNORECASE),
    # "de niña/niño" / "de joven" / "de adolescente"
    re.compile(r"\bde (?:ni[ñn][oa]|peque[ñn][oa]|joven|adolescente|chico|chica|muchach[oa])\b", re.IGNORECASE),
    # "en aquellos tiempos" / "en aquellos días" / "en ese entonces"
    re.compile(r"\ben (?:aquellos|esos|los) (?:tiempos|d[íi]as|a[ñn]os)\b", re.IGNORECASE),
    re.compile(r"\ben (?:ese|aquel) entonces\b", re.IGNORECASE),
    # "antes de la guerra" / "antes de casarme" / "antes de los niños"
    re.compile(r"\bantes de (?:la |mi |los |el )?(?:guerra|escuela|boda|casarme|los\s+ni[ñn]os|eso|entonces)\b", re.IGNORECASE),
    # "después de la guerra" / "después del funeral" / "después de la boda"
    re.compile(r"\bdespu[ée]s d(?:e|el) (?:la |mi |los )?(?:guerra|boda|funeral|servicio|entierro)\b", re.IGNORECASE),
    # "durante la guerra" / "durante el verano"
    re.compile(r"\bdurante (?:la |el |mi )?(?:guerra|verano|invierno|primavera|oto[ñn]o|infancia|ni[ñn]ez|juventud)\b", re.IGNORECASE),
    # "un verano / un día / una noche / una mañana"
    re.compile(r"\b(?:un|una) (?:d[íi]a|noche|ma[ñn]ana|tarde|verano|invierno|primavera|oto[ñn]o)\b", re.IGNORECASE),
    # "creciendo" / "mientras crecía"
    re.compile(r"\b(?:creciendo|mientras crec[íi]a)\b", re.IGNORECASE),
    # "por causa de la guerra" / "debido a la guerra" / "desde la guerra"
    re.compile(r"\b(?:por causa de|debido a|desde|a causa de) (?:la |mi |el )?(?:guerra|depresi[óo]n|sequ[íi]a|gripe|epidemia|hambruna)\b", re.IGNORECASE),
    # "hace mucho tiempo" / "hace años" — vague but elder-narrator-typical
    re.compile(r"\bhace (?:mucho tiempo|muchos a[ñn]os|tantos a[ñn]os|tiempo)\b", re.IGNORECASE),
)

# Spanish person-relation phrasing — narrator-volunteered family
# references with possessive ("mi mamá", "mi abuela"). Same posture
# as English: bare pronouns and common names don't fire.
_PERSON_RELATION_PATTERNS_ES = (
    re.compile(r"\bmi (?:padre|pap[áa]|papi|tata|jefe)\b", re.IGNORECASE),
    re.compile(r"\bmi (?:madre|mam[áa]|mami|jefa)\b", re.IGNORECASE),
    re.compile(r"\bmis? hermanos?\b", re.IGNORECASE),
    re.compile(r"\bmis? hermanas?\b", re.IGNORECASE),
    re.compile(r"\bmi (?:abuela|abuelita|nana|abue)\b", re.IGNORECASE),
    re.compile(r"\bmi (?:abuelo|abuelito|tata|abue)\b", re.IGNORECASE),
    re.compile(r"\bmis? (?:t[íi]as?|t[íi]os?|primos?|primas?|sobrinos?|sobrinas?)\b", re.IGNORECASE),
    re.compile(r"\bmi (?:esposo|esposa|marido|mujer|pareja)\b", re.IGNORECASE),
    re.compile(r"\bmis? (?:hijos?|hijas?|ni[ñn]os?|ni[ñn]as?|chamacos?|chamacas?)\b", re.IGNORECASE),
    re.compile(r"\bmis? (?:padrinos?|padrino|madrina|madrinas?|compadres?|comadres?)\b", re.IGNORECASE),
)

# Bare-capital relation usage in Spanish. Convention: relation nouns
# capitalize when used as proper nouns referring to the speaker's
# actual parent ("Papá trabajaba de noche"). Case-sensitive (no
# IGNORECASE flag) so we only fire on the proper-noun form.
#
# Caveat: "Madre" and "Padre" can also be religious titles
# (priest/nun). In context that rarely produces a false positive,
# but worth noting. The patterns lean toward the diminutive /
# affectionate forms that elder narrators use when speaking about
# their own family.
_BARE_CAPITAL_RELATION_ES_RE = re.compile(
    r"\b(?:Pap[áa]|Mam[áa]|Mami|Papi|Madre|Padre|Tata|Nana|"
    r"Abuela|Abuelo|Abuelita|Abuelito|Abue|"
    r"T[íi]a|T[íi]o|Madrina|Padrino|Comadre|Compadre)\b"
)


def _matches_place(text: str) -> bool:
    """Does this text contain a place reference?

    Order matters for clarity, not correctness — any single hit fires:
      1. Tier 1 institutional / industrial noun (bare mention OK)
      2. Tier 2 common-noun place word PRECEDED by a place preposition
      3. Proper noun after a place preposition ("in Spokane" / "en Lima")
      4. Multi-word capitalized run ("Grand Forks", "Buenos Aires")

    2026-04-30 polish: STT output and quick narrator typing often produce
    all-lowercase text ("in spokane" instead of "in Spokane"). When the
    incoming text contains NO uppercase at all, we retry the proper-noun
    matchers against title-cased text. The "no uppercase anywhere"
    condition keeps mixed-case narrator typing from being modified.

    WO-ML-05A (2026-05-07): Spanish patterns run in parallel — code-
    switched narrators ("I was born in Spokane pero nos mudamos a
    Sonora") get full coverage from both sides.
    """
    # English patterns
    if _PLACE_NOUN_BARE_RE.search(text):
        return True
    if _PLACE_NOUN_PREP_RE.search(text):
        return True
    if _PROPER_NOUN_PLACE_AFTER_PREP.search(text):
        return True
    if _PROPER_NOUN_MULTI_WORD.search(text):
        return True
    # WO-ML-05A: Spanish patterns
    if _PLACE_NOUN_BARE_ES_RE.search(text):
        return True
    if _PLACE_NOUN_PREP_ES_RE.search(text):
        return True
    if _PROPER_NOUN_PLACE_AFTER_PREP_ES.search(text):
        return True

    # All-lowercase fallback for STT-style input.
    if text and text == text.lower():
        title = text.title()
        if _PROPER_NOUN_PLACE_AFTER_PREP.search(title):
            return True
        if _PROPER_NOUN_PLACE_AFTER_PREP_ES.search(title):
            return True
        # Note: skip _PROPER_NOUN_MULTI_WORD on title-case fallback —
        # title-casing every word would make "every dad worked" read
        # as a multi-word proper noun. The prep-anchored variant is
        # specific enough.
    return False


def _matches_relative_time(text: str) -> bool:
    """Does this text contain time-anchoring phrasing?

    WO-ML-05A (2026-05-07): Spanish patterns run alongside English so
    code-switched / Spanish-monolingual narrators trigger when they
    use elder-narrator time markers ("cuando era niña", "en aquellos
    tiempos", "durante la guerra").
    """
    if any(pat.search(text) for pat in _RELATIVE_TIME_PATTERNS):
        return True
    if any(pat.search(text) for pat in _RELATIVE_TIME_PATTERNS_ES):
        return True
    return False


def _matches_person_relation(text: str) -> bool:
    """Does this text reference a family/role person?

    English pattern families:
      1. "my X" patterns (case-insensitive) — narrator explicitly names
         the relation with a possessive.
      2. Bare-capital relation noun (case-sensitive) — narrator uses
         the relation as a proper noun referring to their own parent
         ("Dad walked nights", "Mom sang in the choir"). 2026-04-30
         polish addition.

    WO-ML-05A (2026-05-07): Spanish patterns run in parallel.
    Possessive form ("mi mamá", "mi abuela", "mis tíos") and the
    bare-capital proper-noun form ("Papá trabajaba en la mina")
    both fire. Spanish "mi mamá" and English "my mom" both trigger
    on a code-switched turn.
    """
    if any(pat.search(text) for pat in _PERSON_RELATION_PATTERNS):
        return True
    if _BARE_CAPITAL_RELATION_RE.search(text):
        return True
    # WO-ML-05A: Spanish patterns
    if any(pat.search(text) for pat in _PERSON_RELATION_PATTERNS_ES):
        return True
    if _BARE_CAPITAL_RELATION_ES_RE.search(text):
        return True
    return False


def count_scene_anchors(text: str) -> int:
    """Return 0..3 — the number of anchor dimensions present.

    Each dimension contributes at most 1. A turn that mentions
    "Spokane" three times still has anchor_count=1 from the place
    axis. The point is *dimensional richness*, not raw frequency.
    """
    if not text:
        return 0
    score = 0
    if _matches_place(text):
        score += 1
    if _matches_relative_time(text):
        score += 1
    if _matches_person_relation(text):
        score += 1
    return score


def has_scene_anchor(text: str) -> bool:
    """Is there at least one anchor dimension? Cheap predicate."""
    return count_scene_anchors(text) >= 1


# ── Trigger classification ────────────────────────────────────────────────

def classify_story_candidate(
    *,
    audio_duration_sec: Optional[float],
    transcript: str,
) -> Optional[str]:
    """Returns trigger_reason string if the turn should produce a
    story_candidate, else None.

    Inputs are kwargs (no positional confusion) and minimal — just the
    audio duration and the transcript text. Word count is computed
    from the transcript here so callers don't have to pre-compute and
    risk drift between the trigger threshold and the persisted
    word_count.

    Three trigger paths:
        full_threshold (medium confidence)
            duration ≥ MIN_DURATION_SEC
            AND words ≥ MIN_WORDS
            AND scene_anchor_count ≥ 1

        borderline_scene_anchor (low confidence)
            scene_anchor_count ≥ BORDERLINE_ANCHOR_COUNT (default 3)

        rich_short_narrative (low-medium confidence — added 2026-05-09)
            place anchor AND (person OR time anchor)
            AND words ≥ RICH_SHORT_MIN_WORDS (default 15)
            AND duration ≥ RICH_SHORT_MIN_DURATION_SEC (default 10s)
            Catches the Spanish elder-narrator "compact rich story" shape
            (e.g. María's "abuela / Perú" 21-word 15s memory). Requires
            BOTH place + (person OR time) so single-mention turns like
            "I saw the river" don't trigger.

    The borderline path catches Janice's actual mastoidectomy story,
    which is below the duration/word floor but rich in anchors.
    """
    if not transcript or not transcript.strip():
        return None

    word_count = len(transcript.split())
    anchors = count_scene_anchors(transcript)

    duration = audio_duration_sec if isinstance(audio_duration_sec, (int, float)) else 0.0

    # Primary path: substantial story with at least one anchor.
    if (
        duration >= _min_duration_sec()
        and word_count >= _min_words()
        and anchors >= 1
    ):
        return "full_threshold"

    # Borderline path: short but anchor-rich. The threshold is the
    # MAX dimensions (3) by default — all three axes must fire.
    if anchors >= _borderline_anchor_count():
        return "borderline_scene_anchor"

    # Rich short narrative path (WO-ML-EX-RICH-SHORT-NARRATIVE-01,
    # 2026-05-09). Catches compact emotive turns common in Spanish
    # elder-narrator speech where the content is rich but the
    # word/duration floor is below full_threshold and only 2 anchor
    # types fire. Requires PLACE + (PERSON or TIME) — that pairing is
    # the empirical signature of "this is a memory, not a greeting."
    has_place = _matches_place(transcript)
    has_person = _matches_person_relation(transcript)
    has_time = _matches_relative_time(transcript)
    if (
        has_place
        and (has_person or has_time)
        and word_count >= _rich_short_min_words()
        and duration >= _rich_short_min_duration_sec()
    ):
        return "rich_short_narrative"

    return None


def trigger_diagnostic(
    *,
    audio_duration_sec: Optional[float],
    transcript: str,
) -> dict:
    """Same inputs as classify_story_candidate, but returns the
    underlying numbers so logs and operator review can show WHY a
    turn was (or wasn't) classified.

    Useful in the chat_ws turn handler for emitting a
    [story-trigger] log marker per turn — operator can see the
    threshold proximity and tune env vars accordingly.
    """
    word_count = len(transcript.split()) if transcript else 0
    anchors = count_scene_anchors(transcript or "")
    duration = audio_duration_sec if isinstance(audio_duration_sec, (int, float)) else 0.0

    trigger = classify_story_candidate(
        audio_duration_sec=audio_duration_sec,
        transcript=transcript,
    )

    return {
        "trigger": trigger,
        "duration_sec": duration,
        "word_count": word_count,
        "anchor_count": anchors,
        "place_anchor": _matches_place(transcript or ""),
        "time_anchor": _matches_relative_time(transcript or ""),
        "person_anchor": _matches_person_relation(transcript or ""),
        "thresholds": {
            "min_duration_sec": _min_duration_sec(),
            "min_words": _min_words(),
            "borderline_anchor_count": _borderline_anchor_count(),
            "rich_short_min_words": _rich_short_min_words(),
            "rich_short_min_duration_sec": _rich_short_min_duration_sec(),
        },
    }


__all__ = [
    "count_scene_anchors",
    "has_scene_anchor",
    "classify_story_candidate",
    "trigger_diagnostic",
]
