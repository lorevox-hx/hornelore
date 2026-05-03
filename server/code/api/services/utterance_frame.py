"""WO-EX-UTTERANCE-FRAME-01 Phase 0-2 — Narrator Utterance Frame builder.

═══════════════════════════════════════════════════════════════════════
  LAW: Pure deterministic. No LLM. No DB. No IO. No NLP framework.
       Stdlib + reuse of existing _KINSHIP_CANON / _AFFECT_TOKENS_RX
       from lori_reflection.py. Build gate at
       tests/test_utterance_frame_isolation.py enforces this.

  This module turns narrator text into a Story Clause Map. It does
  NOT call the extractor, does NOT call Lori, does NOT write truth.
  Phase 0-2 ships the builder + fixtures + tests + a CLI runner +
  observability-only logging in chat_ws (HORNELORE_UTTERANCE_FRAME_LOG
  flag, default-off). Consumer wiring (extractor binding, Lori
  reflection grounding, validator, safety) lands in later phases per
  WO-EX-UTTERANCE-FRAME-01_Spec.md §"Three consumption surfaces".
═══════════════════════════════════════════════════════════════════════

What the frame captures (per spec):
    WHO / KINSHIP CANON / SUBJECT CLASS / EVENT / EVENT CLASS /
    PLACE / TIME / OBJECT / FEELING / NEGATION / UNCERTAINTY /
    CANDIDATE FIELD TARGETS / UNBOUND REMAINDER / PARSE CONFIDENCE

What it does NOT do (locked design rules):
    - Invent facts. Every slot traces to verbatim narrator text or a
      canonical mapping (kinship canon).
    - Write truth. The frame produces CANDIDATES; extractor +
      projection + Phase G protected identity remain truth authority.
    - Auto-promote to schema. Recognition is for downstream consumers
      to use as hints; the frame itself never updates state.
    - Therapize. Affect slot captures only narrator-stated affect
      words (verbatim from _AFFECT_TOKENS_RX).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any

# Reuse existing helpers — ZERO new dependencies.
# _AFFECT_TOKENS_RX preserves the "feeling captured ONLY when narrator
# said it" rule established by lori_reflection. We do NOT add a separate
# affect lexicon.
from .lori_reflection import _AFFECT_TOKENS_RX


# ═══ Public constants ════════════════════════════════════════════════

SUBJECT_SELF              = "self"
SUBJECT_PARENT            = "parent"
SUBJECT_SIBLING           = "sibling"
SUBJECT_SPOUSE            = "spouse"
SUBJECT_CHILD             = "child"
SUBJECT_GRANDPARENT       = "grandparent"
SUBJECT_GREAT_GRANDPARENT = "great_grandparent"
SUBJECT_COMMUNITY         = "community_member"
SUBJECT_PET               = "pet"
SUBJECT_UNKNOWN           = "unknown"

EVENT_BIRTH      = "birth"
EVENT_DEATH      = "death"
EVENT_MOVE       = "move"
EVENT_WORK       = "work"
EVENT_MARRIAGE   = "marriage"
EVENT_MILITARY   = "military"
EVENT_EDUCATION  = "education"
EVENT_FAITH      = "faith"
EVENT_ILLNESS    = "illness"
EVENT_LOSS       = "loss"
EVENT_LEISURE    = "leisure"
EVENT_UNKNOWN    = "unknown"

CONFIDENCE_HIGH    = "high"
CONFIDENCE_PARTIAL = "partial"
CONFIDENCE_LOW     = "low"


# ═══ Subject patterns ════════════════════════════════════════════════
#
# RELATIONAL patterns are checked BEFORE the bare self pattern because
# "My dad was born in Stanley" contains both "My" (potentially self)
# and "dad" (parent). The relational match wins; if no relational
# match, we fall back to the explicit self pronouns ("I", "me", "we",
# "us"). "my" alone is a possessive, not a subject.
#
# Each pattern carries an explicit canonical label so consumers don't
# have to re-canonicalize at the call site. This mirrors the kinship
# canon already in lori_reflection.

_RELATIONAL_PATTERNS = [
    # ── Parent ──────────────────────────────────────────────────────
    (re.compile(r"\b(my\s+)?(dad|daddy|papa|pop|father)\b", re.IGNORECASE),
     SUBJECT_PARENT, "father"),
    (re.compile(r"\b(my\s+)?(mom|mommy|mama|ma|mother)\b", re.IGNORECASE),
     SUBJECT_PARENT, "mother"),
    (re.compile(r"\b(my\s+)?(parents|folks)\b", re.IGNORECASE),
     SUBJECT_PARENT, "parents"),

    # ── Spouse ──────────────────────────────────────────────────────
    (re.compile(r"\b(my\s+)?(wife|husband|spouse|partner)\b", re.IGNORECASE),
     SUBJECT_SPOUSE, None),

    # ── Sibling (incl diminutives) ──────────────────────────────────
    (re.compile(r"\b(my\s+)?(brother|sister|sis|bro|siblings)\b", re.IGNORECASE),
     SUBJECT_SIBLING, None),

    # ── Child ───────────────────────────────────────────────────────
    (re.compile(r"\b(my\s+)?(son|daughter|child|children|kids)\b", re.IGNORECASE),
     SUBJECT_CHILD, None),

    # ── Great-grandparent (BEFORE grandparent — more specific) ──────
    (re.compile(r"\b(my\s+)?great[\s-]?grandm(other|a|ama)\b", re.IGNORECASE),
     SUBJECT_GREAT_GRANDPARENT, "great_grandmother"),
    (re.compile(r"\b(my\s+)?great[\s-]?grandf(ather|a)\b", re.IGNORECASE),
     SUBJECT_GREAT_GRANDPARENT, "great_grandfather"),

    # ── Grandparent ─────────────────────────────────────────────────
    (re.compile(r"\b(my\s+)?(grandma|granny|nana|grandmother)\b", re.IGNORECASE),
     SUBJECT_GRANDPARENT, "grandmother"),
    (re.compile(r"\b(my\s+)?(grandpa|gramps|grandfather)\b", re.IGNORECASE),
     SUBJECT_GRANDPARENT, "grandfather"),
    (re.compile(r"\b(my\s+)?grandparents\b", re.IGNORECASE),
     SUBJECT_GRANDPARENT, None),

    # ── Pet ─────────────────────────────────────────────────────────
    # 2026-05-02 sentence-diagram-survey polish: added horse + kitten +
    # puppy + pig. Survey (sd_011 / sd_013 / sd_040 / sd_043) plus
    # Janice's template (childhood pet pig, narrator-confirmed) showed
    # the canon was too narrow — dog/cat/pet missed real narrator pets.
    # The alternation stays conservative — we do NOT add bare "barn" or
    # "ranch" because those are place tokens; horse, kitten, puppy, and
    # pig are unambiguously animal subjects.
    (re.compile(r"\b(my\s+)?(dog|puppy|cat|kitten|horse|pig|pet)\b", re.IGNORECASE),
     SUBJECT_PET, None),
]

# Self pronouns (fallback after relational). "my" alone is excluded —
# it's a possessive, not a subject. Case-insensitive so STT lowercase
# "we got married" still classifies. The literal "I" stays uppercase by
# convention; IGNORECASE handles "we"/"We", "us"/"Us", etc.
_SELF_PATTERN = re.compile(r"\b(I|me|myself|we|us)\b", re.IGNORECASE)


# ═══ Event patterns ══════════════════════════════════════════════════
#
# Order matters: more specific verb phrases first. EVENT_DEATH /
# EVENT_LOSS overlap deliberately — death is a specific event_class;
# loss is the broader category for "lost X" / "passing of Y" without
# a clear death event. Caller distinguishes if needed.

_EVENT_PATTERNS = [
    (re.compile(r"\b(was\s+born|am\s+born|born\s+in|born\s+at|born\s+on)\b",
                re.IGNORECASE),
     EVENT_BIRTH, "born"),

    (re.compile(r"\b(passed\s+away|died|death\s+of|funeral)\b", re.IGNORECASE),
     EVENT_DEATH, "died"),

    (re.compile(r"\b(moved\s+to|moved\s+from|relocated|came\s+to\s+live)\b",
                re.IGNORECASE),
     EVENT_MOVE, "moved"),

    (re.compile(r"\b(worked|works|working|job\s+at|spokesman|spokesperson|"
                r"spokeswoman|employed)\b", re.IGNORECASE),
     EVENT_WORK, "worked"),

    (re.compile(r"\b(married|marriage|wedding|got\s+married|engaged)\b",
                re.IGNORECASE),
     EVENT_MARRIAGE, "married"),

    (re.compile(r"\b(served|enlisted|deployed|in\s+the\s+(army|navy|marines|"
                r"air\s+force|coast\s+guard))\b", re.IGNORECASE),
     EVENT_MILITARY, "served"),

    (re.compile(r"\b(school|college|university|graduated|attended|studied|"
                r"high\s+school)\b", re.IGNORECASE),
     EVENT_EDUCATION, "school"),

    (re.compile(r"\b(church|baptized|faith|prayed|prayer|congregation)\b",
                re.IGNORECASE),
     EVENT_FAITH, "faith"),

    # Illness — specific medical/symptom vocabulary
    (re.compile(r"\b(sick|illness|ache|aches|aching|pain|hospital|surgery|"
                r"mastoidectomy|operation|diagnosis|cancer|stroke)\b",
                re.IGNORECASE),
     EVENT_ILLNESS, "illness"),

    # Loss — broader than death
    (re.compile(r"\b(lost|gone|widowed|burial|grief)\b", re.IGNORECASE),
     EVENT_LOSS, "loss"),
]


# ═══ Place patterns ══════════════════════════════════════════════════
#
# Two layers:
#   1. Place preposition + capitalized name (works on STT lowercase too
#      because we apply re.IGNORECASE).
#   2. Common place nouns that can appear bare ("home", "the farm",
#      "hospital").
#
# We DO NOT try to parse arbitrary noun phrases as places — that lands
# us in NLP-framework territory which the LAW prohibits.

_PLACE_PREP_RX = re.compile(
    # "in/at/from/to/outside of/near" + capitalized place name (1-3 caps tokens).
    # Preps allow any case (handles STT lowercasing the connector word).
    # The place name itself MUST start with a capital letter to be picked up
    # as a proper-noun place. Bare lowercase "alive anymore" / "Stanley too"
    # do NOT match because the second/third word slot also requires capital
    # initial. (We deliberately do NOT pass re.IGNORECASE here — it would
    # make [A-Z] match lowercase letters and produce false-positive places
    # like "be alive anymore" for the negation fixture.)
    r"\b(?:[Ii]n|[Aa]t|[Ff]rom|[Tt]o|[Oo]utside\s+[Oo]f|[Nn]ear|[Mm]oved\s+[Tt]o)\s+"
    r"([A-Z][\w\-']*(?:\s+[A-Z][\w\-']*){0,2})",
)

# Bare common place nouns — only fire when no preposition match found
_PLACE_NOUNS_RX = re.compile(
    r"\b(home|farm|hospital|church|school|kitchen|yard|"
    r"factory|plant|mill|office|shop|store|barn|fields?)\b",
    re.IGNORECASE,
)

# Known place aliases for STT/lowercase narrator speech. This is NOT
# geocoding and NOT inference: a canonical place is emitted only when
# the place token appears verbatim after a place preposition in the
# narrator text. Keeps the no-invented-facts rule while making
# lowercase STT input ("in spokane", "born in stanley") frameable.
_KNOWN_PLACE_ALIASES = {
    "spokane": "Spokane",
    "stanley": "Stanley",
    "mandan": "Mandan",
    "bismarck": "Bismarck",
    "montreal": "Montreal",
    "oslo": "Oslo",
    "hanover": "Hanover",
    "norway": "Norway",
}

_PLACE_ALIAS_PREP_RX_TEMPLATE = (
    r"\b(?:in|at|from|to|near|outside\s+of|moved\s+to|came\s+from|born\s+in)\s+{place}\b"
)


def _extract_known_place_alias(text: str) -> Optional[str]:
    """Return canonical place for lowercase/STT place mentions.

    Conservative by design: only matches known aliases after a place
    preposition. Does not infer states/countries. Does not match bare
    names used as surnames or people.
    """
    for raw, canonical in _KNOWN_PLACE_ALIASES.items():
        rx = re.compile(_PLACE_ALIAS_PREP_RX_TEMPLATE.format(place=re.escape(raw)), re.IGNORECASE)
        if rx.search(text):
            return canonical
    return None


# ═══ Time patterns ══════════════════════════════════════════════════

_TIME_PATTERNS = [
    re.compile(r"\bin\s+(\d{4})\b", re.IGNORECASE),       # in 1954
    re.compile(r"\b(\d{4}s?)\b"),                          # 1954, 1950s
    re.compile(r"\bwhen\s+(I|we|he|she)\s+w(as|ere)\s+\w+", re.IGNORECASE),
    re.compile(r"\bduring\s+(the\s+)?(war|depression|sixties|seventies|"
               r"eighties|nineties|fifties|forties)\b", re.IGNORECASE),
    re.compile(r"\bafter\s+(high\s+school|college|the\s+war|the\s+wedding|"
               r"my\s+father|my\s+mother)\b", re.IGNORECASE),
    re.compile(r"\bwhen\s+I\s+was\s+(little|young|small|growing\s+up|"
               r"a\s+(boy|girl|child|kid))\b", re.IGNORECASE),
    re.compile(r"\b(yesterday|last\s+week|last\s+year|recently)\b",
               re.IGNORECASE),
]


# ═══ Negation + uncertainty ═════════════════════════════════════════
#
# Both are first-class slots per the WO design rule
# "NEGATION + UNCERTAINTY ARE FIRST-CLASS." Downstream consumers
# (extractor, Lori, validator) MUST honor these flags — extractor:
# skip the field hint; Lori: don't push; validator: don't score
# grounding on negated content.

_NEGATION_RX = re.compile(
    r"\b(don't|do\s+not|didn't|did\s+not|don't\s+remember|"
    r"can't\s+remember|never|no\s+one\s+ever|nothing|nobody)\b",
    re.IGNORECASE,
)

_UNCERTAINTY_RX = re.compile(
    r"\b(maybe|perhaps|possibly|i\s+think|i\s+believe|"
    r"i'm\s+not\s+sure|i\s+don't\s+know|might\s+have|could\s+have|"
    r"sort\s+of|kind\s+of)\b",
    re.IGNORECASE,
)


# ═══ Object / scene anchor patterns ══════════════════════════════════
#
# Concrete physical anchors that make a memory specific. Conservative
# list; expansion belongs in WO-LORI-LANGUAGE-CANON-01 Layer 3.

_OBJECT_NOUNS_RX = re.compile(
    r"\b(railroad\s+tracks|kitchen\s+table|piano|organ|car|truck|"
    r"uniform|hospital|church|farmhouse|barn|fields?|"
    r"radio|tv|television|stove|fireplace|"
    r"camera|photograph|picture|letter|diary|"
    r"aluminum\s+plant|steel\s+mill|drug\s+store|"
    r"swimming\s+hole|tree\s+house|"
    # 2026-05-02 sentence-diagram-survey polish: horse + named-pet
    # context (Silver / Grey / Dusty are typical names). The object
    # lexicon stays conservative — horse here is a scene anchor noun,
    # not a subject. Subject classification handles "my horse" via
    # _RELATIONAL_PATTERNS pet alternation.
    r"horse)\b",
    re.IGNORECASE,
)


# ═══ Data classes ═══════════════════════════════════════════════════

@dataclass
class Clause:
    """One semantic clause from a narrator turn. Every slot is optional
    (None / False / empty list); a slot is filled ONLY when there's
    verbatim narrator evidence for it."""
    raw: str = ""
    who: Optional[str] = None
    who_canonical: Optional[str] = None
    who_subject_class: str = SUBJECT_UNKNOWN
    event: Optional[str] = None
    event_class: str = EVENT_UNKNOWN
    place: Optional[str] = None
    time: Optional[str] = None
    object: Optional[str] = None
    feeling: Optional[str] = None
    negation: bool = False
    uncertainty: bool = False
    candidate_fieldPaths: List[str] = field(default_factory=list)


@dataclass
class NarratorUtteranceFrame:
    """Top-level frame for a narrator turn."""
    raw_text: str = ""
    clauses: List[Clause] = field(default_factory=list)
    unbound_remainder: str = ""
    parse_confidence: str = CONFIDENCE_LOW

    def to_dict(self) -> Dict[str, Any]:
        """JSON-friendly dict. Stable shape for logging + fixtures."""
        return {
            "raw_text": self.raw_text,
            "clauses": [asdict(c) for c in self.clauses],
            "unbound_remainder": self.unbound_remainder,
            "parse_confidence": self.parse_confidence,
        }


# ═══ Clause splitter ════════════════════════════════════════════════

def _has_subject(text: str) -> bool:
    """Quick check: does this text contain any subject marker?
    Used by the splitter to validate compound-clause splits."""
    for rx, _, _ in _RELATIONAL_PATTERNS:
        if rx.search(text):
            return True
    if _SELF_PATTERN.search(text):
        return True
    return False


def _split_clauses(text: str) -> List[str]:
    """Split a narrator turn into clauses. Conservative.

    Algorithm:
      1. Split on sentence terminators (. ! ?) — cheap and safe.
      2. Within each sentence, split on ", and" / "; and" / "; but"
         when BOTH halves contain a subject marker. Otherwise the
         compound stays intact (the conjunction was likely connecting
         predicates of the same subject, not switching subjects).

    Returns a list of clause strings, in narrator order, with no
    empty entries."""
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    out: List[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        sub_parts = re.split(r",\s+and\s+|;\s+and\s+|;\s+but\s+", p)
        if len(sub_parts) > 1 and all(_has_subject(sp) for sp in sub_parts):
            out.extend(sp.strip() for sp in sub_parts if sp.strip())
        else:
            out.append(p)
    return out


# ═══ Single-clause builder ══════════════════════════════════════════

def _build_clause(text: str) -> Clause:
    """Build one Clause from one clause string. Pure function."""
    c = Clause(raw=text.strip())

    # ── Subject ──────────────────────────────────────────────────────
    # Try relational patterns first (more specific than bare self).
    for rx, subj_class, canonical in _RELATIONAL_PATTERNS:
        m = rx.search(text)
        if m:
            c.who = m.group(0)
            c.who_subject_class = subj_class
            c.who_canonical = canonical or m.group(0).lower().strip()
            break
    # Fallback to self pronoun if no relational subject found.
    if c.who_subject_class == SUBJECT_UNKNOWN:
        m = _SELF_PATTERN.search(text)
        if m:
            c.who = m.group(0)
            c.who_subject_class = SUBJECT_SELF
            c.who_canonical = "narrator"

    # ── Event ────────────────────────────────────────────────────────
    for rx, evt_class, _ in _EVENT_PATTERNS:
        m = rx.search(text)
        if m:
            c.event = m.group(0)
            c.event_class = evt_class
            break

    # ── Place ────────────────────────────────────────────────────────
    m = _PLACE_PREP_RX.search(text)
    if m:
        c.place = m.group(1).strip()
    else:
        alias_place = _extract_known_place_alias(text)
        if alias_place:
            c.place = alias_place
        else:
            m2 = _PLACE_NOUNS_RX.search(text)
            if m2:
                c.place = m2.group(0).strip()

    # ── Time ─────────────────────────────────────────────────────────
    for rx in _TIME_PATTERNS:
        m = rx.search(text)
        if m:
            c.time = m.group(0).strip()
            break

    # ── Object / scene anchor ────────────────────────────────────────
    m = _OBJECT_NOUNS_RX.search(text)
    if m:
        c.object = m.group(0).strip()
        # If the place fallback only found a generic noun ("plant") but
        # the object matcher found the specific narrator phrase
        # ("aluminum plant"), preserve the specific phrase in the place
        # slot too. This is still verbatim narrator text, not inference.
        if (
            c.place
            and c.place.lower() in {"plant", "mill", "factory", "hospital", "church", "school"}
            and c.object.lower().endswith(c.place.lower())
        ):
            c.place = c.object
        elif not c.place and c.event_class == EVENT_WORK:
            c.place = c.object

    # ── Feeling — ONLY narrator-stated affect words ─────────────────
    # Reuses lori_reflection's existing affect regex so we don't
    # introduce a parallel affect lexicon.
    m = _AFFECT_TOKENS_RX.search(text)
    if m:
        c.feeling = m.group(0).strip()

    # ── Negation ─────────────────────────────────────────────────────
    if _NEGATION_RX.search(text):
        c.negation = True

    # ── Uncertainty ─────────────────────────────────────────────────
    if _UNCERTAINTY_RX.search(text):
        c.uncertainty = True

    # ── Field-target hints (the bridge to extractor) ────────────────
    c.candidate_fieldPaths = _hint_field_paths(c)

    return c


# ═══ Field-target hint heuristic ════════════════════════════════════

def _hint_field_paths(c: Clause) -> List[str]:
    """Map (subject_class, event_class, slots) → candidate fieldPaths.
    Conservative — emits ONLY when both subject + event are known.
    Negated clauses emit no hints (extractor should not write a fact
    the narrator denied). Uncertain clauses still emit hints (the
    extractor decides whether to downgrade to suggest_only).

    These are HINTS, not truth. The extractor decides whether to
    consume them."""
    if c.negation:
        return []
    s, e = c.who_subject_class, c.event_class
    if s == SUBJECT_UNKNOWN or e == EVENT_UNKNOWN:
        return []

    paths: List[str] = []

    # ── Self ─────────────────────────────────────────────────────────
    if s == SUBJECT_SELF:
        if e == EVENT_BIRTH:
            if c.place:
                paths.append("personal.placeOfBirth")
            if c.time:
                paths.append("personal.dateOfBirth")
        elif e == EVENT_WORK:
            paths.append("education.earlyCareer")
        elif e == EVENT_MARRIAGE:
            paths.append("family.marriageDate")
            if c.place:
                paths.append("family.marriagePlace")
        elif e == EVENT_MOVE and c.place:
            paths.append("residence.place")
        elif e == EVENT_MILITARY:
            paths.append("military.branch")
        elif e == EVENT_EDUCATION:
            paths.append("education.schooling")

    # ── Parent ───────────────────────────────────────────────────────
    elif s == SUBJECT_PARENT:
        if e == EVENT_BIRTH:
            if c.place:
                paths.append("parents.birthPlace")
            if c.time:
                paths.append("parents.dateOfBirth")
        elif e == EVENT_WORK:
            paths.append("parents.occupation")
        elif e == EVENT_MOVE and c.place:
            paths.append("residence.place")
        elif e == EVENT_DEATH:
            paths.append("parents.dateOfDeath")

    # ── Sibling ──────────────────────────────────────────────────────
    elif s == SUBJECT_SIBLING:
        if e == EVENT_BIRTH and c.place:
            paths.append("siblings.birthPlace")

    # ── Spouse ───────────────────────────────────────────────────────
    elif s == SUBJECT_SPOUSE:
        if e == EVENT_BIRTH and c.place:
            paths.append("family.spouse.placeOfBirth")
        elif e == EVENT_MARRIAGE and c.time:
            paths.append("family.marriageDate")

    # ── Child ────────────────────────────────────────────────────────
    elif s == SUBJECT_CHILD:
        if e == EVENT_BIRTH and c.place:
            paths.append("family.children.placeOfBirth")
        elif e == EVENT_BIRTH and c.time:
            paths.append("family.children.dateOfBirth")

    # ── Grandparent ──────────────────────────────────────────────────
    elif s == SUBJECT_GRANDPARENT:
        if e == EVENT_BIRTH and c.place:
            paths.append("grandparents.birthPlace")

    # ── Great-grandparent ────────────────────────────────────────────
    elif s == SUBJECT_GREAT_GRANDPARENT:
        if e == EVENT_BIRTH and c.place:
            paths.append("greatGrandparents.birthPlace")

    # ── Pet ──────────────────────────────────────────────────────────
    elif s == SUBJECT_PET:
        # No specific event mapping for v1 — extractor handles
        # pets.* via its own classifier. Frame just signals the
        # subject class; consumer decides field path.
        pass

    return paths


# ═══ Confidence scoring ═════════════════════════════════════════════

def _score_confidence(clauses: List[Clause]) -> str:
    """high  = all clauses fully classified (subject + event + ≥1 anchor)
       partial = some slots filled, some unknown
       low    = parser had to fall back to whole-turn-as-one-clause
                with no useful classification

    Downstream consumers MAY downgrade behavior on low confidence."""
    if not clauses:
        return CONFIDENCE_LOW
    fully = 0
    partial_count = 0
    for c in clauses:
        has_subject = c.who_subject_class != SUBJECT_UNKNOWN
        has_event = c.event_class != EVENT_UNKNOWN
        has_anchor = bool(c.place or c.time or c.object)
        if has_subject and has_event and has_anchor:
            fully += 1
        elif has_subject or has_event:
            partial_count += 1
    if fully == len(clauses):
        return CONFIDENCE_HIGH
    if fully + partial_count > 0:
        return CONFIDENCE_PARTIAL
    return CONFIDENCE_LOW


# ═══ Public entry point ═════════════════════════════════════════════

def build_frame(narrator_text: str) -> NarratorUtteranceFrame:
    """Top-level: turn narrator text into a Story Clause Map.

    Pure function. No IO. No LLM. No DB. No truth-write.
    Deterministic — same input always yields the same output.

    Args:
        narrator_text: the user's last turn (raw STT or typed text)

    Returns:
        NarratorUtteranceFrame with one or more Clauses, an
        unbound_remainder, and a parse_confidence label.

    Edge cases:
        - Empty / whitespace-only text → empty frame, confidence=low
        - No classifiable clauses → fallback to whole text as one
          unbound clause, confidence=low
    """
    if not narrator_text or not narrator_text.strip():
        return NarratorUtteranceFrame(
            raw_text=narrator_text or "",
            clauses=[],
            unbound_remainder="",
            parse_confidence=CONFIDENCE_LOW,
        )

    text = narrator_text.strip()
    clause_strings = _split_clauses(text)

    if not clause_strings:
        # Defensive — splitter returned nothing (shouldn't happen for
        # non-empty input but let's be safe). Treat as one unbound.
        return NarratorUtteranceFrame(
            raw_text=text,
            clauses=[Clause(raw=text)],
            unbound_remainder=text,
            parse_confidence=CONFIDENCE_LOW,
        )

    clauses = [_build_clause(cs) for cs in clause_strings if cs.strip()]
    confidence = _score_confidence(clauses)
    # Unbound remainder: empty when at least one clause classified.
    # When NOTHING classified, we still emit the clauses (raw-only)
    # but flag the whole turn as unbound.
    if confidence == CONFIDENCE_LOW:
        unbound = text
    else:
        unbound = ""

    return NarratorUtteranceFrame(
        raw_text=text,
        clauses=clauses,
        unbound_remainder=unbound,
        parse_confidence=confidence,
    )


# ═══ Module exports ═════════════════════════════════════════════════

__all__ = [
    # Public API
    "build_frame",
    "NarratorUtteranceFrame",
    "Clause",
    # Subject class constants
    "SUBJECT_SELF", "SUBJECT_PARENT", "SUBJECT_SIBLING", "SUBJECT_SPOUSE",
    "SUBJECT_CHILD", "SUBJECT_GRANDPARENT", "SUBJECT_GREAT_GRANDPARENT",
    "SUBJECT_COMMUNITY", "SUBJECT_PET", "SUBJECT_UNKNOWN",
    # Event class constants
    "EVENT_BIRTH", "EVENT_DEATH", "EVENT_MOVE", "EVENT_WORK",
    "EVENT_MARRIAGE", "EVENT_MILITARY", "EVENT_EDUCATION", "EVENT_FAITH",
    "EVENT_ILLNESS", "EVENT_LOSS", "EVENT_LEISURE", "EVENT_UNKNOWN",
    # Confidence constants
    "CONFIDENCE_HIGH", "CONFIDENCE_PARTIAL", "CONFIDENCE_LOW",
]
