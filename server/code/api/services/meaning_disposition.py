"""One disposition contract for meaning the narrator stated.

WO-LORI-ARCHIVE-TO-MEMOIR-02 Phase 5C.

THE RULE THIS ENFORCES

    Every meaning Lori understands must reach a real field, an
    attributed review destination, or an EXPLICIT RECORDED REFUSAL.
    Nothing understood may silently disappear, and nothing may be
    forced into a false schema field to avoid a review item.

WHY ONE CONTRACT AND NOT ONE BRANCH PER CASE. Phase 5B produced the
first instance of this — `relationship_state_has_no_destination`, with
`would_need` naming the field that does not exist — because an ex-wife's
occupation proposed as `family.spouse.occupation` had been surviving as
the CURRENT spouse's occupation. Three more cases were already known
(`adult`, `older`/`younger`, `STATE_DECEASED`), and writing `if adult`,
`if older`, `if deceased` beside it would have produced four
independent refusals with four shapes and no way to ask whether the
list was complete. The next reading the interpreter learns would then
disappear exactly as these did, and nothing would object.

So the mechanism is a DECLARED TABLE of components to destinations, and
an `undeclared` verdict for anything nobody has ruled on. A future
interpreter addition that produces meaning with no destination makes
`tests/test_meaning_disposition_completeness.py` fail — which is the
whole of Phase 5C's protection.

WHAT THIS MODULE MAY NOT DO. It has no database, no IO and no LLM; it
is a pure reduction over a reading and a set of known field paths, and
the field set is INJECTED rather than imported so this module and
`routers/extract.py` do not close a cycle.

IT INVENTS NOTHING. That is the point rather than a caveat:

  * `older` / `younger` do NOT become `siblings.birthOrder`. A birth
    order is a position in a sequence; `older` is a comparison to the
    narrator, and the field exists, which is exactly what makes the
    mistake available. Manufacturing it would assert a fact about a
    family nobody stated.
  * `adult` does not become an age, a date of birth, or a year.
  * `STATE_DECEASED` does not become a death date, a death year, a
    cause, or a relationship end date. It records that the narrator
    said `late wife`, and nothing else.

NO SECOND REVIEW STORE. Measured before writing a line of this: the
existing path is
`_normalize_relationship_lane` -> `clarification_required` on
`ExtractFieldsResponse` -> `turn_extraction._clarifications` ->
`db.turn_extraction_result_store` (a real column, JSON) ->
`db.py:8615` on read -> `operator_story_review.py:321` ->
`bug-panel-story-review.js:707` "Needs clarification before it could be
trusted". It is durable, narrator-scoped, operator-visible, and
`_store_result` already persists a result with NO items when only
dispositions exist. Every record built here travels that path.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from . import relationship_interpreter as ri


# ── The three truthful outcomes ───────────────────────────────────────

DISPOSITION_FIELD = "field"
"""It reached a real structured destination."""

DISPOSITION_REVIEW = "review"
"""It reached an attributed review destination for a human to adjudicate."""

DISPOSITION_NO_DESTINATION = "no_destination"
"""Understood, and no approved destination exists. A RECORDED REFUSAL —
which is preferable to inventing a schema field, and is not the same as
silence."""

DISPOSITION_UNDECLARED = "undeclared"
"""NOBODY HAS RULED ON THIS COMPONENT.

Not an outcome — a hole in the contract. It exists so that a new
qualifier or state added to the interpreter's table cannot quietly
inherit "no destination" and look deliberate. The completeness test
treats it as a failure and names the component.
"""

VALID_DISPOSITIONS = frozenset({
    DISPOSITION_FIELD, DISPOSITION_REVIEW, DISPOSITION_NO_DESTINATION,
})


# ── Reasons. Instances of one path, not separate mechanisms ───────────

REASON_LANE_HAS_NO_DESTINATION = "relationship_state_has_no_destination"
"""PRESERVED VERBATIM from Phase 5B. A value the narrator stated about a
former or deceased partner, proposed for a field that exists only on the
current-spouse lane. `tests/test_spouse_state_characterization.py`
asserts this exact string, and renaming it to fit a tidier scheme would
break a guard for cosmetic reasons."""

REASON_QUALIFIER_HAS_NO_DESTINATION = "relationship_qualifier_has_no_destination"
"""`older`, `younger`, `adult`, `half`, `step`. Read correctly by the
interpreter since Phase 5B and carried nowhere since."""

REASON_DECEASED_HAS_NO_DESTINATION = "relationship_state_deceased_has_no_destination"
"""`late wife`. Measured against the shipped field set: there is no
`deceased`, `status` or `livingState` path anywhere in the 141
extractable fields, and `grandparents.deathDate` is a DATE on a
different lane. So the death is recorded, never derived."""

REASON_RELATION_HAS_NO_DESTINATION = "relation_has_no_destination"
"""The lane exists and its `.relation` field does not — `grandparents`
and `greatGrandparents` today. `grandmother` must not be collapsed into
`grandparents.side`: `side` is maternal/paternal and the word says
nothing about which."""


# ── The declared table ────────────────────────────────────────────────
#
# A sentinel rather than a string, so "the group's own lane carries this"
# can never be mistaken for a field path.

_LANE = object()

#: state -> destination. `None` means a deliberate recorded refusal.
_STATE_DESTINATIONS: Dict[str, Any] = {
    "": _LANE,                     # lanes with no state concept
    ri.STATE_CURRENT: _LANE,       # the current lane IS the destination
    ri.STATE_FORMER: _LANE,        # `family.priorPartners` IS the destination
    ri.STATE_DECEASED: None,       # no field exists; recorded refusal
}

#: qualifier -> destination. Every non-empty one is a refusal today.
_QUALIFIER_DESTINATIONS: Dict[str, Any] = {
    "": _LANE,                     # nothing was said; nothing to place
    "older": None,
    "younger": None,
    "adult": None,
    "half": None,
    "step": None,
}

#: What each qualifier WOULD need. Three different missing capabilities,
#: and saying so beats one generic sentence: `older` is a comparison to
#: the narrator, `adult` is a life stage, and `half` / `step` describe
#: the KINSHIP ITSELF rather than the person's age. Answering all three
#: with "relative age" would misdescribe two of them, and the whole
#: value of `would_need` is that a future session can act on it.
_QUALIFIER_WOULD_NEED: Dict[str, str] = {
    "older": ("a relative-age destination — a comparison to the narrator. "
              "NOT siblings.birthOrder, which is a position in a sequence "
              "and would assert an order nobody stated"),
    "younger": ("a relative-age destination — a comparison to the narrator. "
                "NOT siblings.birthOrder, which is a position in a sequence "
                "and would assert an order nobody stated"),
    "adult": ("a life-stage destination. NOT an age and NOT a date of "
              "birth — neither is implied by the word"),
    "half": "a kinship-degree destination (half / step / full)",
    "step": "a kinship-degree destination (half / step / full)",
}

_QUALIFIER_FALLBACK_WOULD_NEED = (
    "a destination for this qualifier; none exists and none may be "
    "improvised from a nearby field")

#: The components of a reading that carry meaning. Provenance is here
#: deliberately: the narrator's exact wording is meaning, and Phase 5B
#: gave it a destination (`ExtractedItem.source_phrase`).
COMPONENTS: Tuple[str, ...] = ("group", "relation", "state", "qualifier",
                               "source_phrase")


def _lane_exists(group: str, known_fields: Set[str]) -> bool:
    prefix = f"{group}."
    return any(k.startswith(prefix) for k in known_fields)


def destination_for(reading: "ri.RelationshipReading", component: str,
                    known_fields: Set[str]) -> Tuple[str, Optional[str]]:
    """Where does one component of one reading go?

    Returns `(disposition, destination)`. `destination` is a field path
    or lane name when there is one, and `None` when the answer is a
    recorded refusal. An unrecognised state or qualifier comes back
    `undeclared` — deliberately distinguishable from a refusal, because
    "we decided nothing goes here" and "nobody has looked" are different
    facts and only one of them is safe.
    """
    if component == "group":
        return ((DISPOSITION_FIELD, reading.group)
                if _lane_exists(reading.group, known_fields)
                else (DISPOSITION_NO_DESTINATION, None))

    if component == "relation":
        path = f"{reading.group}.relation"
        return ((DISPOSITION_FIELD, path) if path in known_fields
                else (DISPOSITION_NO_DESTINATION, None))

    if component == "state":
        if reading.state not in _STATE_DESTINATIONS:
            return (DISPOSITION_UNDECLARED, None)
        target = _STATE_DESTINATIONS[reading.state]
        return ((DISPOSITION_FIELD, reading.group) if target is _LANE
                else (DISPOSITION_NO_DESTINATION, None))

    if component == "qualifier":
        if reading.qualifier not in _QUALIFIER_DESTINATIONS:
            return (DISPOSITION_UNDECLARED, None)
        target = _QUALIFIER_DESTINATIONS[reading.qualifier]
        return ((DISPOSITION_FIELD, reading.group) if target is _LANE
                else (DISPOSITION_NO_DESTINATION, None))

    if component == "source_phrase":
        # Phase 5B: `ExtractedItem.source_phrase` carries the narrator's
        # own wording into provenance.
        return (DISPOSITION_FIELD, "ExtractedItem.source_phrase")

    return (DISPOSITION_UNDECLARED, None)


# ── The record ────────────────────────────────────────────────────────

def no_destination_record(
    *,
    meaning: str,
    value: Any,
    label: str,
    reason: str,
    narrator_phrase: str,
    would_need: Optional[str],
    kind: str = "meaning_disposition",
    proposed_fieldPath: Optional[str] = None,
    normalized: Optional[str] = None,
    person: Optional[Dict[str, Any]] = None,
    extra_reasons: Sequence[str] = (),
) -> Dict[str, Any]:
    """One recorded refusal, in the shape the review surface already reads.

    ENOUGH FOR A HUMAN TO ACT ON, which is the whole difference between
    a refusal and a silence: what was understood, the narrator's own
    words, the canonical meaning where there is one, who it was about,
    what was proposed, why nothing approved exists, and what WOULD be
    needed.

    `not_applied` is unconditionally True. A record built here describes
    something that did NOT reach the narrator's truth, and a record that
    could claim otherwise would be worse than none.
    """
    return {
        # Existing consumers key on these. Unchanged on purpose.
        "kind": kind,
        "value": value,
        "label": label,
        "proposed_fieldPath": proposed_fieldPath,
        "not_applied": True,
        "reasons": [reason, *extra_reasons],
        "reason": reason,
        "narrator_phrase": narrator_phrase,
        "would_need": would_need,

        # Phase 5C additions. Additive, so nothing that reads the older
        # shape has to change to keep working.
        "disposition": DISPOSITION_NO_DESTINATION,
        "meaning": meaning,
        "normalized": normalized,
        "person": person or {},
    }


def _person_of(reading: "ri.RelationshipReading") -> Dict[str, Any]:
    return {
        "group": reading.group,
        "relation": reading.relation,
        "state": reading.state,
        "qualifier": reading.qualifier,
    }


# ── The accounting pass ───────────────────────────────────────────────

def account_for_readings(answer: str, known_fields: Iterable[str],
                         ) -> List[Dict[str, Any]]:
    """Every reading in the answer, every component, one disposition each.

    Only refusals are emitted: a component with a real destination needs
    no record, because the record IS the field. What this guarantees is
    that a component with NO destination cannot pass silently.

    Deliberately independent of whether extraction produced an item for
    the reading. "My older brother Ray was a welder" loses the word
    `older` whether or not `Ray` was captured, and a disposition that
    only fired alongside a successful item would miss the case where the
    meaning is all that survived.
    """
    known = set(known_fields or ())
    out: List[Dict[str, Any]] = []
    for reading in ri.readings_in(answer or ""):
        person = _person_of(reading)

        # ── the qualifier ─────────────────────────────────────────────
        disposition, _dest = destination_for(reading, "qualifier", known)
        if reading.qualifier and disposition != DISPOSITION_FIELD:
            out.append(no_destination_record(
                meaning="relationship_qualifier",
                value=reading.qualifier,
                label=(f"{reading.qualifier} {reading.relation} — the "
                       f"narrator said it and no field holds it"),
                reason=REASON_QUALIFIER_HAS_NO_DESTINATION,
                narrator_phrase=reading.source_phrase,
                # NAMED AS A CAPABILITY, NOT A FIELD PATH. A path here
                # would read as an instruction to wire it, and for
                # `older` the nearest-looking field is precisely the
                # wrong one.
                would_need=_QUALIFIER_WOULD_NEED.get(
                    reading.qualifier, _QUALIFIER_FALLBACK_WOULD_NEED),
                normalized=reading.qualifier,
                person=person,
            ))

        # ── the state ─────────────────────────────────────────────────
        disposition, _dest = destination_for(reading, "state", known)
        if reading.state and disposition != DISPOSITION_FIELD:
            out.append(no_destination_record(
                meaning="relationship_state",
                value=reading.state,
                label=(f"{reading.source_phrase} — the narrator said this "
                       f"{reading.relation} has died, and no field records it"),
                reason=REASON_DECEASED_HAS_NO_DESTINATION,
                narrator_phrase=reading.source_phrase,
                would_need=("a living/deceased state on the spouse lane; "
                            "NO date, year or cause is implied by the word"),
                normalized=reading.state,
                person=person,
            ))

        # ── the relation itself ───────────────────────────────────────
        disposition, _dest = destination_for(reading, "relation", known)
        if disposition != DISPOSITION_FIELD:
            out.append(no_destination_record(
                meaning="relationship_relation",
                value=reading.relation,
                label=(f"{reading.relation} — the lane {reading.group} has "
                       f"no relation field"),
                reason=REASON_RELATION_HAS_NO_DESTINATION,
                narrator_phrase=reading.source_phrase,
                would_need=f"{reading.group}.relation",
                normalized=reading.relation,
                person=person,
            ))
    return out
