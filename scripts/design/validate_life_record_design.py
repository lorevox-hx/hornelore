#!/usr/bin/env python3
"""Design verification for WO-LIFE-RECORD-01 — run BEFORE any implementation.

WHY THIS EXISTS, AND WHY IT IS NOT A PROTOTYPE.

A small working questionnaire proves four inputs work together. It does not
prove the design is coherent, and this project has already paid for that
distinction: a working demonstration sitting on an inconsistent system.

So this does the opposite. It expresses the SPECIFICATION'S RULES as
executable predicates, then runs hard life situations against them — cases
chosen to break the model rather than to flatter it. A situation that cannot
be represented, or that can be represented in a way the rules forbid, is a
DESIGN failure, findable now, on paper, for the cost of an afternoon.

WHAT THIS CANNOT TELL YOU. The situations and the rules are both authored
here, so this is a coherence check, not an independent audit, and it says
nothing about whether an operator finds the form usable. Those need a person.
See WO-LIFE-RECORD-01 §14.

All narrators below are fictional.
"""

import json
import sys

# ─────────────────────────────────────────────────────────────────────
#  The rules, as stated in WO-LIFE-RECORD-01. Each returns a list of
#  violations. A rule that cannot fail is not a rule.
# ─────────────────────────────────────────────────────────────────────

# ── MOVED 2026-09-23 (Batch B-3) ──────────────────────────────────────
# The vocabularies, the 21 model rules, `RULES`, the life-span resolver and
# `run` now live ONCE, in the product: server/code/api/services/life_record/
# rules.py. This file imports them, so the design situations below and the
# product writer are judged by the same code.
_HERE = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
_CODE = __import__("os").path.join(_HERE, "..", "..", "server", "code")
if _CODE not in sys.path:
    sys.path.insert(0, _CODE)
from api.services.life_record import rules as _R  # noqa: E402
globals().update({k: v for k, v in vars(_R).items() if not k.startswith("__")})


def A(value, source="operator", status="operator_entered", **kw):
    """An assertion, in the vocabulary §3.9 adopts from `bio_facts`."""
    d = {"value": value, "source": source, "status": status,
         "recordedAt": "2026-09-22"}
    d.update(kw)
    return d


def D(text, value=None, precision="day"):
    return {"text": text, "value": value, "precision": precision}


# ─────────────────────────────────────────────────────────────────────
#  Hard situations. Each is a life the model must hold, chosen because it
#  breaks something. All fictional.
# ─────────────────────────────────────────────────────────────────────

CASES = {}

CASES["1 · compound surname, several given names, a variant spelling"] = {
    "narrator_person_id": "P1",
    "people": [
        {"id": "P1", "names": [{"fullText": "Ari Jo del Río Mercer",
                                "givenParts": ["Ari", "Jo"],
                                "family": "del Río Mercer",
                                "variants": ["Ari Jo Delrio Mercer"],
                                "use": "legal"}],
         "lifeStatus": A("explicitly_living")},
        {"id": "P2", "names": [{"fullText": "Marisol Elena Isabel Vega",
                                "givenParts": ["Marisol", "Elena", "Isabel"],
                                "family": "Vega", "use": "birth"},
                               {"fullText": "Marisol Vega de Mercer",
                                "use": "married"}],
         "lifeStatus": A("deceased")},
    ],
    "relationships": [
        {"id": "R1", "subjectPersonId": "P2", "otherPersonId": "P1",
         "kind": "parent_of", "qualifiers": ["biological"], "basis": "stated",
         "assertion": A("parent_of")},
    ],
    "events": [
        {"id": "E1", "type": "death", "date": D("1998", "1998", "year"),
         "participants": [{"person": "P2", "role": "subject"}]},
    ],
    "stories": [], "places": [], "animals": [],
}

CASES["2 · six siblings stated, two identified"] = {
    "narrator_person_id": "P1",
    "people": [
        {"id": "P1", "names": [{"fullText": "Rosalind Okonkwo"}]},
        {"id": "P2", "names": [{"fullText": "Chidi Okonkwo"}]},
        {"id": "P3", "names": [{"fullText": "Ngozi Okonkwo"}]},
    ],
    "relationships": [
        {"id": "R1", "subjectPersonId": "P2", "otherPersonId": "P1",
         "kind": "sibling_of", "basis": "stated", "assertion": A("sibling_of")},
        {"id": "R2", "subjectPersonId": "P3", "otherPersonId": "P1",
         "kind": "sibling_of", "basis": "stated", "assertion": A("sibling_of")},
    ],
    "reportedCounts": {"siblings": A(6, source="narrator_stated")},
    "events": [], "stories": [], "places": [], "animals": [],
}

CASES["3 · a child with two mothers, neither the current partner"] = {
    "narrator_person_id": "P1",
    "people": [
        {"id": "P1", "names": [{"fullText": "Tomas Lindqvist"}]},
        {"id": "P2", "names": [{"fullText": "Ilse Brandt"}]},      # co-parent
        {"id": "P3", "names": [{"fullText": "Annika Roos"}]},      # co-parent
        {"id": "P4", "names": [{"fullText": "Nils Lindqvist"}]},   # child
        {"id": "P5", "names": [{"fullText": "Bea Halvorsen"}]},    # current partner
    ],
    "relationships": [
        {"id": "R1", "subjectPersonId": "P2", "otherPersonId": "P4",
         "kind": "parent_of", "qualifiers": ["biological"], "basis": "stated",
         "assertion": A("parent_of")},
        {"id": "R2", "subjectPersonId": "P3", "otherPersonId": "P4",
         "kind": "parent_of", "qualifiers": ["adoptive"], "basis": "stated",
         "assertion": A("parent_of")},
        {"id": "R3", "subjectPersonId": "P1", "otherPersonId": "P5",
         "kind": "partner_of", "basis": "stated", "assertion": A("partner_of")},
    ],
    "events": [], "stories": [], "places": [], "animals": [],
}

CASES["4 · a marriage that ended, then a later partner"] = {
    "narrator_person_id": "P1",
    "people": [
        {"id": "P1", "names": [{"fullText": "Halina Zielińska"}]},
        {"id": "P2", "names": [{"fullText": "Jan Wozniak"}]},
        {"id": "P3", "names": [{"fullText": "Piotr Malik"}]},
    ],
    "events": [
        {"id": "E1", "type": "union", "date": D("1971-06-12", "1971-06-12"),
         "participants": [{"person": "P1", "role": "spouse"},
                          {"person": "P2", "role": "spouse"}]},
        {"id": "E2", "type": "separation", "date": D("1989", "1989", "year"),
         "participants": [{"person": "P1", "role": "subject"},
                          {"person": "P2", "role": "subject"}]},
    ],
    "relationships": [
        {"id": "R1", "subjectPersonId": "P1", "otherPersonId": "P2",
         "kind": "spouse_of", "qualifiers": ["former"],
         "period": {"start": D("1971-06-12", "1971-06-12"),
                    "end": D("1989", "1989", "year")},
         "basis": "derived_from_event", "derivedFromEventId": "E1",
         "assertion": A("spouse_of")},
        {"id": "R2", "subjectPersonId": "P1", "otherPersonId": "P3",
         "kind": "partner_of", "basis": "stated", "assertion": A("partner_of")},
    ],
    "stories": [], "places": [], "animals": [],
}

CASES["5 · an interpretation that must not become a fact"] = {
    "narrator_person_id": "P1",
    "people": [
        {"id": "P1", "names": [{"fullText": "Ruth Adeyemi"}]},
        {"id": "P2", "names": [{"fullText": "Samuel Adeyemi"}], "attributes": []},
    ],
    "relationships": [
        {"id": "R1", "subjectPersonId": "P2", "otherPersonId": "P1",
         "kind": "parent_of", "basis": "stated", "assertion": A("parent_of")},
    ],
    # She said both of these aloud, so the preservation lane owns the words
    # and the life record holds only the curation (§2.6).
    "_storyCandidates": ["C1", "C2"],
    "stories": [
        {"id": "S1", "kind": "reflection", "origin": "captured",
         "candidateRef": "C1",
         "peopleRefs": ["P2"], "source": "narrator_stated"},
        {"id": "S2", "kind": "memory", "origin": "captured",
         "candidateRef": "C2",
         "peopleRefs": [], "placeRefs": [], "eventRefs": [],
         "source": "narrator_stated"},
    ],
    "events": [], "places": [], "animals": [],
}

CASES["6 · contradictory sources, neither discarded"] = {
    "narrator_person_id": "P1",
    "people": [
        {"id": "P1", "names": [{"fullText": "Eileen Carr"}]},
        {"id": "P2", "names": [{"fullText": "Maureen Carr"}],
         "occupations": [
             A("Midwife", source="operator", status="conflicted",
               conflictWith="OC2", id="OC1"),
             A("Nurse", source="extracted", status="conflicted",
               conflictWith="OC1", id="OC2"),
         ]},
    ],
    "relationships": [
        {"id": "R1", "subjectPersonId": "P2", "otherPersonId": "P1",
         "kind": "parent_of", "basis": "stated", "assertion": A("parent_of")},
    ],
    "events": [], "stories": [], "places": [], "animals": [],
}

CASES["7 · deceased with no date; living stated; another unknown"] = {
    "narrator_person_id": "P1",
    "people": [
        {"id": "P1", "names": [{"fullText": "Sipho Ndlovu"}]},
        {"id": "P2", "names": [{"fullText": "Thandi Ndlovu"}],
         "lifeStatus": A("deceased")},                       # no death event
        {"id": "P3", "names": [{"fullText": "Bongani Ndlovu"}],
         "lifeStatus": A("explicitly_living")},
        {"id": "P4", "names": [{"fullText": "Lerato Ndlovu"}]},   # nobody has said
    ],
    "relationships": [
        {"id": "R1", "subjectPersonId": "P2", "otherPersonId": "P1",
         "kind": "parent_of", "basis": "stated", "assertion": A("parent_of")},
    ],
    "events": [], "stories": [], "places": [], "animals": [],
}

CASES["8 · incomplete and vague — almost nothing is known"] = {
    "narrator_person_id": "P1",
    "people": [
        {"id": "P1", "names": [{"fullText": "Wren"}]},
    ],
    "events": [
        {"id": "E1", "type": "birth",
         "date": D("around 1945", "1945~", "approximate"),
         "participants": [{"person": "P1", "role": "subject"}]},
    ],
    "militaryService": A("unanswered"),
    "relationships": [], "stories": [], "places": [], "animals": [],
}

CASES["9 · an only child — zero stated is an answer"] = {
    # The case the old rule REFUSED. A narrator who says "there was just me"
    # states a count of zero and identifies nobody, and both are true.
    "narrator_person_id": "P1",
    "people": [{"id": "P1", "names": [{"fullText": "Dorothy Pike"}],
                "lifeStatus": A("explicitly_living")}],
    "reportedCounts": {"siblings": A(0, source="narrator_stated"),
                       "children": A(3, source="narrator_stated")},
    "relationships": [], "events": [], "stories": [], "places": [], "animals": [],
}

CASES["10 · a correction supersedes; both tellings survive"] = {
    "narrator_person_id": "P1",
    "_storyCandidates": ["C1", "C2"],
    "people": [{"id": "P1", "names": [{"fullText": "Ester Vance"}]}],
    "stories": [
        {"id": "S1", "kind": "memory", "origin": "captured", "candidateRef": "C1",
         "source": "narrator_stated"},
        {"id": "S2", "kind": "memory", "origin": "captured", "candidateRef": "C2",
         "source": "narrator_stated", "supersedes": "S1"},
    ],
    "relationships": [], "events": [], "places": [], "animals": [],
}

CASES["11 · two jobs in sequence are two facts, not a dispute"] = {
    # The case the OLD conflict rule would have rejected: a list of two
    # assertions is not a contradiction when they are about different
    # propositions. The period is the context that tells them apart.
    "narrator_person_id": "P1",
    "people": [{"id": "P1", "names": [{"fullText": "Nadia Feld"}],
                "occupations": [
                    A("Midwife", period={"start": "1961", "end": "1975"}),
                    A("Nurse", period={"start": "1975", "end": "1998"}),
                ]}],
    "relationships": [], "events": [], "stories": [], "places": [], "animals": [],
}

CASES["12 · an accepted DOB beside a retained alternative"] = {
    # The DOB contract's own state, now also a first-class model case.
    "narrator_person_id": "P1",
    "people": [{"id": "P1", "names": [{"fullText": "Janet Reyes"}],
                "birthEventRef": "B17", "lifeStatus": A("explicitly_living")}],
    "events": [{"id": "B17", "type": "birth",
                "participants": [{"person": "P1", "role": "subject"}],
                "acceptedAssertionId": "A1",
                "dateAssertions": [
                    dict(D("August 30, 1939", "1939-08-30"), status="operator_entered",
                         source="operator", id="A1", conflictWith="A2",
                         recordedAt="2026-09-22"),
                    dict(D("1938", "1938", "year"), status="conflicted",
                         source="extracted", id="A2", conflictWith="A1",
                         recordedAt="2026-09-22"),
                ]}],
    "relationships": [], "stories": [], "places": [], "animals": [],
}

# ── cases that MUST be refused ───────────────────────────────────────
MUST_FAIL = {}

MUST_FAIL["a birth pointer aimed at someone else's wedding"] = ({
    "narrator_person_id": "P1",
    "people": [{"id": "P1", "names": [{"fullText": "Ada Roche"}], "birthEventRef": "E9"},
               {"id": "P2", "names": [{"fullText": "Cormac Roche"}]}],
    "events": [{"id": "E9", "type": "union", "date": D("1965", "1965", "year"),
                "participants": [{"person": "P2", "role": "spouse"}]}],
    "relationships": [], "stories": [], "places": [], "animals": [],
}, "birth/death refs are the person's own")

MUST_FAIL["the same parent stored twice (C-3, 2026-09-24)"] = ({
    "narrator_person_id": "P1",
    "people": [{"id": "P1", "names": [{"fullText": "Ada Roche"}]},
               {"id": "P2", "names": [{"fullText": "Nuala Roche"}]}],
    "events": [],
    "relationships": [
        {"id": "R1", "subjectPersonId": "P2", "otherPersonId": "P1", "kind": "parent_of", "basis": "stated"},
        {"id": "R2", "subjectPersonId": "P2", "otherPersonId": "P1", "kind": "parent_of", "basis": "stated"}],
    "stories": [], "places": [], "animals": [],
}, "no relationship stored twice")

MUST_FAIL["a sibling stored once in each direction under one kind"] = ({
    "narrator_person_id": "P1",
    "people": [{"id": "P1", "names": [{"fullText": "Ada Roche"}]},
               {"id": "P2", "names": [{"fullText": "Liam Roche"}]}],
    "events": [],
    "relationships": [
        {"id": "R1", "subjectPersonId": "P2", "otherPersonId": "P1", "kind": "friend_of", "basis": "stated"},
        {"id": "R2", "subjectPersonId": "P1", "otherPersonId": "P2", "kind": "friend_of", "basis": "stated"}],
    "stories": [], "places": [], "animals": [],
}, "no relationship stored twice")

CASES["married, divorced and remarried to the same person (C-3, 2026-09-24)"] = {
    "narrator_person_id": "P1",
    "people": [{"id": "P1", "names": [{"fullText": "Ada Roche"}]},
               {"id": "P2", "names": [{"fullText": "Cormac Roche"}]},
               {"id": "P3", "names": [{"fullText": "Bridget Roche"}]}],
    "events": [],
    "relationships": [
        {"id": "R1", "subjectPersonId": "P2", "otherPersonId": "P1", "kind": "spouse_of", "basis": "stated",
         "period": {"start": D("1960", "1960", "year"), "end": D("1968", "1968", "year")}},
        # stored in the SAME direction: rule_no_stored_inverse refuses the
        # reverse direction even with a different period (a known strictness,
        # recorded in the C-3 checkpoint; the editor always stores person→narrator)
        {"id": "R2", "subjectPersonId": "P2", "otherPersonId": "P1", "kind": "spouse_of", "basis": "stated",
         "period": {"start": D("1975", "1975", "year")}},
        # one person, two different relationships: grandmother AND caregiver
        {"id": "R3", "subjectPersonId": "P3", "otherPersonId": "P1", "kind": "grandparent_of", "basis": "stated"},
        {"id": "R4", "subjectPersonId": "P3", "otherPersonId": "P1", "kind": "caregiver_of", "basis": "stated"}],
    "stories": [], "places": [], "animals": [],
}

CASES["married once with dates unknown, remarried the same person in 1992 (C-3 review)"] = {
    "narrator_person_id": "P1",
    "people": [{"id": "P1", "names": [{"fullText": "Ada Roche"}]},
               {"id": "P2", "names": [{"fullText": "Pat Roche"}]}],
    "events": [],
    "relationships": [
        {"id": "R1", "subjectPersonId": "P2", "otherPersonId": "P1", "kind": "spouse_of", "basis": "stated"},
        {"id": "R2", "subjectPersonId": "P2", "otherPersonId": "P1", "kind": "spouse_of", "basis": "stated",
         "period": {"start": D("1992", "1992", "year")}}],
    "stories": [], "places": [], "animals": [],
}

MUST_FAIL["a birth pointer aimed at another person's birth"] = ({
    "narrator_person_id": "P1",
    "people": [{"id": "P1", "names": [{"fullText": "Ada Roche"}], "birthEventRef": "B2"},
               {"id": "P2", "names": [{"fullText": "Cormac Roche"}]}],
    "events": [{"id": "B2", "type": "birth", "date": D("1910", "1910", "year"),
                "participants": [{"person": "P2", "role": "subject"}]}],
    "relationships": [], "stories": [], "places": [], "animals": [],
}, "birth/death refs are the person's own")

MUST_FAIL["two accounts of one fact, unlinked and undecided"] = ({
    "narrator_person_id": "P1",
    "people": [{"id": "P1", "names": [{"fullText": "Ada Roche"}]}],
    "events": [{"id": "B1", "type": "birth",
                "participants": [{"person": "P1", "role": "subject"}],
                "dateAssertions": [
                    dict(D("1939-08-30", "1939-08-30"), status="operator_entered",
                         source="operator", id="A1", recordedAt="2026-09-22"),
                    dict(D("1938", "1938", "year"), status="needs_verify",
                         source="extracted", id="A2", recordedAt="2026-09-22"),
                ]}],
    "relationships": [], "stories": [], "places": [], "animals": [],
}, "competing claims kept and linked")

MUST_FAIL["a date assertion with no provenance, hiding among dates"] = ({
    "narrator_person_id": "P1",
    "people": [{"id": "P1", "names": [{"fullText": "Ada Roche"}]}],
    "events": [{"id": "B1", "type": "birth",
                "participants": [{"person": "P1", "role": "subject"}],
                "dateAssertions": [dict(D("1939", "1939", "year"), id="A1")]}],
    "relationships": [], "stories": [], "places": [], "animals": [],
}, "assertions well formed")

MUST_FAIL["a captured story holding its own copy of the words"] = ({
    "narrator_person_id": "P1",
    "_storyCandidates": ["C1"],
    "people": [{"id": "P1", "names": [{"fullText": "Ada Roche"}]}],
    "stories": [{"id": "S1", "kind": "memory", "origin": "captured",
                 "candidateRef": "C1", "body": "Woodsmoke.",
                 "source": "narrator_stated"}],
    "events": [], "relationships": [], "places": [], "animals": [],
}, "story ownership is unambiguous")

MUST_FAIL["editing the words the narrator actually said"] = ({
    "narrator_person_id": "P1",
    "_storyCandidates": ["C1"],
    "people": [{"id": "P1", "names": [{"fullText": "Ada Roche"}]}],
    "stories": [{"id": "S1", "kind": "memory", "origin": "captured",
                 "candidateRef": "C1", "bodyEdited": True,
                 "source": "narrator_stated"}],
    "events": [], "relationships": [], "places": [], "animals": [],
}, "story ownership is unambiguous")

MUST_FAIL["a value recorded with no provenance"] = ({
    "narrator_person_id": "P1",
    "people": [{"id": "P1", "names": [{"fullText": "Ada Roche"}],
                "occupations": [{"value": "Nurse"}]}],     # no source, no status
    "events": [], "relationships": [], "stories": [], "places": [], "animals": [],
}, "assertions well formed")

MUST_FAIL["a story pointing at an event that does not exist"] = ({
    "narrator_person_id": "P1",
    "_storyCandidates": ["C1"],
    "people": [{"id": "P1", "names": [{"fullText": "Ada Roche"}]}],
    "stories": [{"id": "S1", "kind": "memory", "origin": "captured",
                 "candidateRef": "C1", "source": "narrator_stated",
                 "eventRefs": ["E404"]}],
    "events": [], "relationships": [], "places": [], "animals": [],
}, "stories are first class")

MUST_FAIL["an assertion with no recordedAt"] = ({
    "narrator_person_id": "P1",
    "people": [{"id": "P1", "names": [{"fullText": "Ada Roche"}],
                "occupations": [{"value": "Nurse", "source": "operator",
                                 "status": "operator_entered"}]}],
    "events": [], "relationships": [], "stories": [], "places": [], "animals": [],
}, "assertions well formed")

MUST_FAIL["a captured story with no resolvable candidate"] = ({
    "narrator_person_id": "P1",
    "people": [{"id": "P1", "names": [{"fullText": "Ada Roche"}]}],
    "stories": [{"id": "S1", "kind": "memory", "origin": "captured",
                 "candidateRef": "C404", "source": "narrator_stated"}],
    "events": [], "relationships": [], "places": [], "animals": [],
}, "story ownership is unambiguous")

MUST_FAIL["a stated count computed from the list"] = ({
    "narrator_person_id": "P1",
    "people": [{"id": "P1", "names": [{"fullText": "Ada Roche"}]}],
    "reportedCounts": {"siblings": A(2, source="operator",
                                     derivedFrom="relationships")},
    "events": [], "relationships": [], "stories": [], "places": [], "animals": [],
}, "stated counts not overwritten")

MUST_FAIL["a relationship to a person who is not recorded"] = ({
    "narrator_person_id": "P1",
    "people": [{"id": "P1", "names": [{"fullText": "Ada Roche"}]}],
    "relationships": [{"id": "R1", "subjectPersonId": "P9",
                       "otherPersonId": "P1", "kind": "parent_of",
                       "basis": "stated", "assertion": A("parent_of")}],
    "events": [], "stories": [], "places": [], "animals": [],
}, "relationship endpoints resolve")

MUST_FAIL["a death event with the person still marked living"] = ({
    "narrator_person_id": "P1",
    "people": [
        {"id": "P1", "names": [{"fullText": "Ada Roche"}]},
        {"id": "P2", "names": [{"fullText": "Cormac Roche"}],
         "lifeStatus": A("explicitly_living")},
    ],
    "events": [{"id": "E1", "type": "death", "date": D("2001", "2001", "year"),
                "participants": [{"person": "P2", "role": "subject"}]}],
    "relationships": [], "stories": [], "places": [], "animals": [],
}, "life status valid, never inferred")

MUST_FAIL["a birth date stored on the person as well as the event"] = ({
    "narrator_person_id": "P1",
    "people": [{"id": "P1", "names": [{"fullText": "Ada Roche"}],
                "birth": {"date": D("1950-01-01", "1950-01-01")}}],
    "events": [], "relationships": [], "stories": [], "places": [], "animals": [],
}, "birth/death dates stored once")

MUST_FAIL["a reflection promoted to an attribute of the person"] = ({
    "narrator_person_id": "P1",
    "people": [
        {"id": "P1", "names": [{"fullText": "Ada Roche"}]},
        {"id": "P2", "names": [{"fullText": "Cormac Roche"}],
         "attributes": [A("silent", derivedFromStory="S1")]},
    ],
    "_storyCandidates": ["C1"],
    "stories": [{"id": "S1", "kind": "reflection", "origin": "captured",
                 "candidateRef": "C1",
                 "peopleRefs": ["P2"], "source": "narrator_stated"}],
    "events": [], "relationships": [], "places": [], "animals": [],
}, "interpretations not promoted to facts")

MUST_FAIL["a form default recorded as 'did not serve'"] = ({
    "narrator_person_id": "P1",
    "people": [{"id": "P1", "names": [{"fullText": "Ada Roche"}]}],
    "militaryService": {"value": "no", "source": "form_default",
                        "confirmation": "stated", "recordedAt": "2026-09-22"},
    "events": [], "relationships": [], "stories": [], "places": [], "animals": [],
}, "no form default becomes an answer")

MUST_FAIL["'around 1945' normalised into an exact date"] = ({
    "narrator_person_id": "P1",
    "people": [{"id": "P1", "names": [{"fullText": "Ada Roche"}]}],
    "events": [{"id": "E1", "type": "birth",
                "date": {"text": "around 1945", "value": "1945-01-01",
                         "precision": "approximate"},
                "participants": [{"person": "P1", "role": "subject"}]}],
    "relationships": [], "stories": [], "places": [], "animals": [],
}, "dates keep original text")

MUST_FAIL["a story reduced to a single subject"] = ({
    "narrator_person_id": "P1",
    "people": [{"id": "P1", "names": [{"fullText": "Ada Roche"}]}],
    "stories": [{"id": "S1", "kind": "memory", "origin": "authored",
                 "body": "Woodsmoke.",
                 "subject": "P1", "source": "operator"}],
    "events": [], "relationships": [], "places": [], "animals": [],
}, "stories are first class")

MUST_FAIL["a derived relationship edited by hand"] = ({
    "narrator_person_id": "P1",
    "people": [{"id": "P1", "names": [{"fullText": "Ada Roche"}]},
               {"id": "P2", "names": [{"fullText": "Cormac Roche"}]}],
    "events": [{"id": "E1", "type": "union", "date": D("1970", "1970", "year"),
                "participants": [{"person": "P1", "role": "spouse"},
                                 {"person": "P2", "role": "spouse"}]}],
    "relationships": [{"id": "R1", "subjectPersonId": "P1", "otherPersonId": "P2",
                       "kind": "spouse_of", "basis": "derived_from_event",
                       "derivedFromEventId": "E1", "handEdited": True,
                       "assertion": A("spouse_of")}],
    "stories": [], "places": [], "animals": [],
}, "derived relationships not hand-edited")

MUST_FAIL["competing claims silently reduced to one"] = ({
    "narrator_person_id": "P1",
    "people": [{"id": "P1", "names": [{"fullText": "Ada Roche"}]},
               {"id": "P2", "names": [{"fullText": "Cormac Roche"}],
                "occupations": [A("Midwife"),
                                A("Nurse", source="extracted",
                                  status="operator_entered")]}],
    "events": [], "relationships": [], "stories": [], "places": [], "animals": [],
}, "competing claims kept and linked")


# ═════════════════════════════════════════════════════════════════════
#  §2 CONTRACT CHECKS — the boundary, not the model.
#
#  The model rules above ask "can this life be represented?". These ask
#  "does the rest of Hornelore agree about who owns what?" — which the
#  repository review identified as the harder problem. Each is a small
#  reference implementation of a rule the work order states, exercised
#  against scenarios that would break it.
# ═════════════════════════════════════════════════════════════════════

ABSENT = object()


def apply_changes(store, base_revision, changes):
    """§3.10 reference implementation. Conflict is decided PER PATH — a
    stale baseRevision alone is not a conflict; a changed path is."""
    rejected = []
    for c in changes:
        cur = store["paths"].get(c["path"], ABSENT)
        if c["op"] in ("set", "remove"):
            if "expectedPrevious" not in c:
                rejected.append((c["path"], "no expectedPrevious supplied"))
            else:
                exp = c["expectedPrevious"]
                exp = ABSENT if exp is None else exp
                if cur != exp:
                    rejected.append((c["path"],
                                     "absent" if cur is ABSENT else cur))
        elif c["op"] == "add":
            if c["value"]["id"] in store["ids"]:
                rejected.append((c["path"], f"id {c['value']['id']} exists"))
    if rejected:
        return {"conflict": rejected, "revision": store["revision"],
                "wrote": False}
    for c in changes:                                  # all-or-nothing
        if c["op"] == "set":
            store["paths"][c["path"]] = c["value"]
        elif c["op"] == "remove":
            store["paths"].pop(c["path"], None)
        elif c["op"] == "add":
            store["ids"].add(c["value"]["id"])
    store["revision"] += 1
    return {"revision": store["revision"], "wrote": True}


def contract_write_is_per_path():
    bad = []
    s = {"paths": {"a": "1", "b": "2"}, "ids": set(), "revision": 7}

    r = apply_changes(s, 7, [{"op": "set", "path": "a", "value": "x",
                              "expectedPrevious": "1"}])
    if not r["wrote"]:
        bad.append("a clean edit was rejected")

    # the second operator's base is now stale, but they touch another path
    r = apply_changes(s, 7, [{"op": "set", "path": "b", "value": "y",
                              "expectedPrevious": "2"}])
    if not r["wrote"]:
        bad.append("an unrelated path was rejected for a stale baseRevision "
                   "— §3.10 says the revision does not decide")

    # same path, stale expectation: must reject, name the path, write nothing
    before = dict(s["paths"])
    r = apply_changes(s, 7, [{"op": "set", "path": "a", "value": "z",
                              "expectedPrevious": "1"}])
    if r["wrote"]:
        bad.append("a stale same-path edit overwrote")
    elif [p for p, _ in r["conflict"]] != ["a"]:
        bad.append("the conflict did not name the offending path")
    elif s["paths"] != before:
        bad.append("a rejected write still changed something "
                   "— all-or-nothing broken")

    # a blind overwrite must be impossible
    r = apply_changes(s, 9, [{"op": "set", "path": "a", "value": "q"}])
    if r["wrote"]:
        bad.append("a set with no expectedPrevious was accepted")

    # one bad path in a batch rejects the whole batch
    before = dict(s["paths"])
    r = apply_changes(s, 9, [{"op": "set", "path": "b", "value": "ok",
                              "expectedPrevious": "y"},
                             {"op": "set", "path": "a", "value": "no",
                              "expectedPrevious": "WRONG"}])
    if r["wrote"] or s["paths"] != before:
        bad.append("a batch with one conflicting path was partially applied")
    return bad


def required_facts(bio, mentions, window=3, cap=5, ceiling=400):
    """§9.1 reference implementation. Constant part plus a turn-scoped part
    selected BY MENTION, capped, most recent first.

    DEFECT FIXED 2026-09-22. This MEASURED the ceiling and returned the
    number; nothing enforced it, and the contract check passed only because
    the fixture used names like "Relative 12". Real names — a compound
    surname, a long relation word — took it to 443 characters against a
    declared 400. The fixture was supplying the property being proven, which
    is the failure docs/TESTING-DOCTRINE.md exists to catch; it is the tenth
    recorded instance, found in the code written to enforce the rule.

    The ceiling is now a BUDGET. Lines are admitted while they fit, and a
    person who does not fit falls to retrieval — they are never included
    with their life status trimmed off, because a name without a status is
    exactly the death defect."""
    nar = next(p for p in bio["people"] if p["id"] == bio["narrator_person_id"])
    lines = [f"{nar['names'][0]['fullText']} — the narrator"]
    used = len(lines[0])
    dropped = []

    recent = sorted((m for m in mentions if m["turnsAgo"] <= window),
                    key=lambda m: m["turnsAgo"])
    for m in recent[:cap]:
        p = next((x for x in bio["people"] if x["id"] == m["person"]), None)
        if p is None:
            continue
        st = (p.get("lifeStatus") or {}).get("value", "unknown")
        line = f"{p['names'][0]['fullText']} — {m['relation']} — {st}"
        if used + len(line) > ceiling:
            dropped.append(m["person"])          # falls to retrieval, whole
            continue
        lines.append(line)
        used += len(line)
    return {"lines": lines, "chars": used, "ceiling": ceiling, "cap": cap,
            "dropped_to_retrieval": dropped}


def contract_required_facts_bounded():
    bad = []
    people = [{"id": "P1", "names": [{"fullText": "Dorothy Pike"}],
               "lifeStatus": A("explicitly_living")}]
    people += [{"id": f"P{i}", "names": [{"fullText": f"Relative {i}"}],
                "lifeStatus": A("deceased" if i % 3 else "explicitly_living")}
               for i in range(2, 62)]                        # sixty on record
    bio = {"narrator_person_id": "P1", "people": people}

    block = required_facts(bio, [])
    if len(block["lines"]) != 1:
        bad.append("with nothing mentioned the block is not just the narrator")

    # Adversarial by construction: a compound surname and a long relation
    # word. Short fixture names are what hid the ceiling defect.
    longs = [{"id": f"L{i}",
              "names": [{"fullText": "Bartholomew Aleksander Rasmussen-Delacroix"}],
              "lifeStatus": A("deceased")} for i in range(2, 62)]
    bio_long = {"narrator_person_id": "P1",
                "people": [dict(people[0],
                                names=[{"fullText": "Margarethe Wilhelmina van der Bergh-Okonkwo"}])] + longs}
    long_mentions = [{"person": f"L{i}", "relation": "maternal great-aunt",
                      "turnsAgo": 1} for i in range(2, 62)]
    lb = required_facts(bio_long, long_mentions)
    if lb["chars"] > lb["ceiling"]:
        bad.append(f"{lb['chars']} chars exceeds the ceiling {lb['ceiling']} "
                   "with realistic names — the ceiling is measured, not enforced")
    for line in lb["lines"][1:]:
        if not any(s in line for s in LIFE_STATUSES):
            bad.append("a person was trimmed to fit and lost their life status")

    mentions = [{"person": f"P{i}", "relation": "cousin", "turnsAgo": i % 5}
                for i in range(2, 62)]
    block = required_facts(bio, mentions)
    if len(block["lines"]) > block["cap"] + 1:
        bad.append(f"{len(block['lines'])} lines exceeds the cap of {block['cap']}")
    if block["chars"] > block["ceiling"]:
        bad.append(f"{block['chars']} chars exceeds the ceiling "
                   f"{block['ceiling']} at sixty people on record")

    # every mentioned person carries their status — the death defect
    for line in block["lines"][1:]:
        if not any(s in line for s in LIFE_STATUSES):
            bad.append(f"a mentioned person appears without life status: {line!r}")

    # selection is by mention, never by closeness
    close = [{"person": "P2", "relation": "daughter", "turnsAgo": 99}]
    if len(required_facts(bio, close)["lines"]) != 1:
        bad.append("an unmentioned close relative was included — §9.1 says "
                   "selection is by mention, not by closeness")
    return bad


def contract_cross_domain_references():
    """§2.7 — reference, do not replace; correct the record, not the trip's
    words; merge rather than delete; and export the closure."""
    bad = []
    places = {"PL1": {"label": "Spokane, Washington", "deleted": False}}
    trip = {"id": "T1", "stopLabel": "spokane wa", "place_id": "PL1"}

    places["PL1"]["label"] = "Spokane, Washington, USA"     # a correction
    if trip["stopLabel"] != "spokane wa":
        bad.append("correcting a place rewrote the trip's own label")

    unreferenced = {"id": "T2", "stopLabel": "Butte", "place_id": None}
    if unreferenced["place_id"] is not None:
        bad.append("a trip without a reference was forced to adopt one")

    def hard_delete(pid, trips):
        if any(t["place_id"] == pid for t in trips):
            return "refused: merge instead"
        return "deleted"
    if hard_delete("PL1", [trip, unreferenced]) != "refused: merge instead":
        bad.append("a referenced place was hard-deleted, leaving a dangling id")

    def export(trips, included_places):
        missing = {t["place_id"] for t in trips
                   if t["place_id"] and t["place_id"] not in included_places}
        return "refused" if missing else "ok"
    if export([trip], set()) != "refused":
        bad.append("export produced a package whose trip references a place "
                   "it does not carry")
    if export([trip], {"PL1"}) != "ok":
        bad.append("a complete package was refused")
    return bad


def contract_review_gate_not_bypassed():
    """§2.5 — a first-class event makes chronology possible, not automatic."""
    bad = []
    events = [
        {"id": "E1", "type": "union", "date": D("1971", "1971", "year"),
         "promoted": False},
        {"id": "E2", "type": "birth", "date": D("1939-08-30", "1939-08-30"),
         "promoted": True, "placement_source": "operator_set",
         "era_candidates": ["childhood"]},
    ]
    for e in events:
        on_map = e.get("promoted")
        if on_map and not e.get("era_candidates"):
            bad.append(f"event {e['id']}: promoted with no confirmed era")
        if on_map and len(e.get("era_candidates", [])) > 1:
            bad.append(f"event {e['id']}: two eras is not a placement")
        if not on_map and e.get("era_candidates"):
            bad.append(f"event {e['id']}: unpromoted but carries a placement "
                       "— the review gate was bypassed")
        if e.get("era_from_year"):
            bad.append(f"event {e['id']}: an era was derived from a year")
    return bad


def contract_producers_resolve_against_catalog():
    """§2.2 — the single rule that would have prevented all 69 homeless
    extraction targets: a producer may not name an undefined concept."""
    bad = []
    catalog = {"person.birth.date", "person.death.date", "person.lifeStatus",
               "person.name.full"}
    producers = {
        "questionnaire": {"person.name.full", "person.birth.date"},
        "extraction": {"person.birth.date", "person.death.date"},
        "asking": {"person.birth.date", "person.lifeStatus"},
        "lori": {"person.name.full", "person.lifeStatus"},
    }
    for who, refs in producers.items():
        for r in sorted(refs - catalog):
            bad.append(f"{who} names {r!r}, which the catalog does not define")

    drifted = dict(producers, extraction=producers["extraction"] | {"parents.deathDate"})
    caught = any(r not in catalog for refs in drifted.values() for r in refs)
    if not caught:
        bad.append("the check does not notice a drifted producer — it is inert")
    return bad


def contract_every_entity_has_a_lane():
    """§3.11 — every new table needs a DbLane entry or it silently fails to
    export AND to erase. A missing lane is a privacy defect, not a chore."""
    bad = []
    entities = ["people", "places", "events", "relationships", "stories",
                "animals", "biography"]
    lanes = {"people", "places", "events", "relationships", "stories",
             "animals", "biography"}
    for e in entities:
        if e not in lanes:
            bad.append(f"entity {e!r} has no DbLane — it cannot be exported or erased")
    if not (set(entities) - (lanes - {"places"})) == {"places"}:
        bad.append("the check does not notice a missing lane — it is inert")
    return bad



def contract_dob_anchors_the_life_span():
    """Hornelore ALREADY has a temporal spine: the narrator's DOB anchors it
    and the seven-era framework is built forward from there. The occurrence
    layer describes what happened inside that span — it must not become a
    second life-span timeline."""
    bad = []
    TODAY = "2026-09-22"

    def bio(nar_extra=None, events=(), people_extra=()):
        nar = {"id": "P1", "names": [{"fullText": "Janet Reyes"}]}
        nar.update(nar_extra or {})
        return {"narrator_person_id": "P1",
                "people": [nar] + list(people_extra),
                "events": list(events), "relationships": [], "stories": [],
                "places": [], "animals": []}

    birth = {"id": "B17", "type": "birth", "date": D("August 30, 1939", "1939-08-30"),
             "participants": [{"person": "P1", "role": "subject"}]}

    # the narrator's DOB, reached by POINTER — not a second copy of the date
    ls = resolve_life_span(bio({"birthEventRef": "B17",
                                "lifeStatus": A("explicitly_living")}, [birth]), TODAY)
    if not ls["available"] or ls["start"]["value"] != "1939-08-30":
        bad.append("the narrator's DOB did not anchor the scaffold")
    if ls["end_kind"] != "open" or ls["end"] is not None:
        bad.append("a living narrator's span was given an end — the shipped "
                   "scaffold is open-ended (checkpoint §3.3b)")

    # a pointer to a UNION event — the case that anchored a life at 1965
    union = {"id": "E9", "type": "union", "date": D("1965", "1965", "year"),
             "participants": [{"person": "P1", "role": "spouse"}]}
    ls = resolve_life_span(bio({"birthEventRef": "E9",
                                "lifeStatus": A("explicitly_living")}, [union]), TODAY)
    if ls["available"]:
        bad.append("a union event anchored the life span")
    if not ls["anchor"].startswith("ref_is_union"):
        bad.append(f"the refusal did not say why: {ls['anchor']}")

    # a pointer to SOMEONE ELSE's birth
    other = {"id": "B99", "type": "birth", "date": D("1910", "1910", "year"),
             "participants": [{"person": "P2", "role": "subject"}]}
    ls = resolve_life_span(bio({"birthEventRef": "B99",
                                "lifeStatus": A("explicitly_living")}, [other],
                               [{"id": "P2", "names": [{"fullText": "Peter Zarr"}]}]), TODAY)
    if ls["available"] or ls["anchor"] != "subject_is_someone_else":
        bad.append("another person's birth anchored the narrator's span")

    # a RELATIVE's DOB anchors nothing
    rel_birth = {"id": "B18", "type": "birth", "date": D("1910", "1910", "year"),
                 "participants": [{"person": "P2", "role": "subject"}]}
    b = bio({"lifeStatus": A("explicitly_living")}, [rel_birth],
            [{"id": "P2", "names": [{"fullText": "Peter Zarr"}],
              "birthEventRef": "B18"}])
    if resolve_life_span(b, TODAY)["available"]:
        bad.append("a relative's DOB was used as the narrator's life-span start")

    # no DOB → no spine. It must not be defaulted to anything.
    ls = resolve_life_span(bio({"lifeStatus": A("explicitly_living")}), TODAY)
    if ls["available"] or ls["start"] is not None:
        bad.append("a missing DOB produced a scaffold anyway")

    # approximate DOB keeps its precision; no invented day
    approx = {"id": "B19", "type": "birth",
              "date": D("around 1945", "1945~", "approximate"),
              "participants": [{"person": "P1", "role": "subject"}]}
    ls = resolve_life_span(bio({"birthEventRef": "B19",
                                "lifeStatus": A("explicitly_living")}, [approx]), TODAY)
    if ls["precision"] != "approximate" or "~" not in ls["start"]["value"]:
        bad.append("an approximate DOB was sharpened by the scaffold")

    # deceased, date known → that date ends the span
    death = {"id": "D1", "type": "death", "date": D("2011", "2011", "year"),
             "participants": [{"person": "P1", "role": "subject"}]}
    ls = resolve_life_span(bio({"birthEventRef": "B17", "deathEventRef": "D1",
                                "lifeStatus": A("deceased")}, [birth, death]), TODAY)
    if ls["end_kind"] != "death_date" or ls["end"]["value"] != "2011":
        bad.append("a known death date did not end the span")

    # deceased, date UNKNOWN → no endpoint is invented, and it is not today
    ls = resolve_life_span(bio({"birthEventRef": "B17",
                                "lifeStatus": A("deceased")}, [birth]), TODAY)
    if ls["end"] is not None:
        bad.append("a deceased narrator with no death date was given an endpoint "
                   "— the span was falsely extended")
    if ls["end_kind"] != "deceased_date_unknown":
        bad.append("the unknown-death-date case is not distinguished")

    # the scaffold is RESOLVED, never stored
    b = bio({"birthEventRef": "B17", "lifeStatus": A("explicitly_living")}, [birth])
    if "life_span" in b:
        bad.append("the scaffold was persisted into the biography")
    # and the biography that anchors correctly also passes the FULL model
    # rules — the resolver is not tested in isolation from them
    if run(b):
        bad.append(f"the anchoring fixture fails the model rules: {run(b)}")
    return bad


def contract_dob_conflicts_and_corrections():
    """One person, one birth concept, disagreeing date assertions."""
    bad = []
    TODAY = "2026-09-22"
    birth = {"id": "B17", "type": "birth",
             "participants": [{"person": "P1", "role": "subject"}],
             "dateAssertions": [
                 dict(D("August 30, 1939", "1939-08-30"), status="operator_entered",
                      source="operator", id="A1", conflictWith="A2",
                      recordedAt="2026-09-22"),
                 dict(D("1938", "1938", "year"), status="conflicted",
                      source="extracted", id="A2", conflictWith="A1",
                      recordedAt="2026-09-22"),
             ]}
    b = {"narrator_person_id": "P1",
         "people": [{"id": "P1", "names": [{"fullText": "Janet Reyes"}],
                     "birthEventRef": "B17", "lifeStatus": A("explicitly_living")}],
         "events": [birth], "relationships": [], "stories": [],
         "places": [], "animals": []}

    def model_ok(stage):
        """DEFECT FIXED 2026-09-22: this fixture was only ever fed to the
        resolver. Run through the full model rules it was REJECTED, because
        the conflict rule read list length as dispute. Every stage below now
        goes through `run()` as well."""
        v = run(b)
        if v:
            bad.append(f"[{stage}] the DOB fixture fails the model rules: {v}")

    # TWO live assertions, mutually linked, NOBODY has decided → the model
    # accepts the state (they are linked) but the scaffold stays unresolved
    model_ok("linked, undecided")
    ls = resolve_life_span(b, TODAY)
    if ls["available"]:
        bad.append("the scaffold picked a DOB with no recorded acceptance "
                   "— §2.4 says the write policy does not decide whose "
                   "account is accepted")

    birth["acceptedAssertionId"] = "A1"               # a human decides
    model_ok("accepted A1")
    ls = resolve_life_span(b, TODAY)
    if not ls["available"] or ls["start"]["value"] != "1939-08-30":
        bad.append("the scaffold did not use the accepted assertion")
    if len(birth["dateAssertions"]) != 2:
        bad.append("the competing assertion was discarded")

    # The status name must NOT decide. Same two assertions, acceptance moved
    # to the extracted one: the scaffold must follow the decision, not the
    # more authoritative-sounding status.
    birth["acceptedAssertionId"] = "A2"
    model_ok("accepted A2")
    if resolve_life_span(b, TODAY)["start"]["value"] != "1938":
        bad.append("the scaffold overrode a recorded decision because the "
                   "other assertion's STATUS looked more authoritative")

    # a correction supersedes rather than erases, and acceptance moves with it
    birth["dateAssertions"][0]["status"] = "superseded"
    birth["dateAssertions"][0]["supersededBy"] = "A3"
    birth["dateAssertions"].append(
        dict(D("August 30, 1940", "1940-08-30"), status="narrator_corrected",
             source="narrator_stated", id="A3", recordedAt="2026-09-23"))
    birth["acceptedAssertionId"] = "A3"
    model_ok("corrected, accepted A3")
    ls = resolve_life_span(b, TODAY)
    if ls["start"]["value"] != "1940-08-30":
        bad.append("a narrator correction did not move the scaffold")
    if len(birth["dateAssertions"]) != 3:
        bad.append("the corrected assertion was deleted rather than superseded")

    # a superseded assertion may not be resurrected by pointing at it
    birth["acceptedAssertionId"] = "A1"
    if resolve_life_span(b, TODAY)["available"]:
        bad.append("a superseded assertion was accepted")

    # a date assertion with NO provenance inside dateAssertions is caught —
    # the location-aware fix, on the fixture that used to escape
    birth["acceptedAssertionId"] = "A3"
    birth["dateAssertions"].append(dict(D("1941", "1941", "year"), id="A4"))
    if not any("no provenance" in v for _, v in run(b)):
        bad.append("a date assertion without provenance escaped the model rules")
    birth["dateAssertions"].pop()
    return bad


def contract_uncertainty_propagates():
    """§5 stores the uncertainty; this spends it correctly."""
    bad = []
    # 1939-08-30 → 1971-06-12. The birthday has NOT come round: she is 31.
    exact = age_at(D("1939-08-30", "1939-08-30"), D("1971-06-12", "1971-06-12"))
    if not exact["exact"] or exact["render"] != "31":
        bad.append(f"age before the birthday is wrong: got {exact['render']}, "
                   "expected 31 — year subtraction is not age")
    after = age_at(D("1939-08-30", "1939-08-30"), D("1971-09-01", "1971-09-01"))
    if after["render"] != "32":
        bad.append(f"age after the birthday is wrong: got {after['render']}")
    onday = age_at(D("1939-08-30", "1939-08-30"), D("1971-08-30", "1971-08-30"))
    if onday["render"] != "32":
        bad.append("age on the birthday itself is wrong")

    coarse = age_at(D("1939-08-30", "1939-08-30"), D("1971", "1971", "year"))
    if coarse["exact"] or coarse["render"] != "31 or 32":
        bad.append("a firm but coarse date did not yield the two-value answer")

    vague = age_at(D("around 1945", "1945~", "approximate"),
                   D("1965", "1965", "year"))
    if vague["exact"] or not vague["render"].startswith("about"):
        bad.append("an approximate birth produced an exact age — false precision")

    # C-4 contract: approximation lives in the VALUE. `1945~` is YEAR
    # precision and still approximate — reading precision alone is the bug.
    vague_new = age_at(D("around 1945", "1945~", "year"), D("1965", "1965", "year"))
    if vague_new["exact"] or not vague_new["render"].startswith("about"):
        bad.append("a C-4 approximate birth (1945~, year) produced an unqualified age")
    day_uncertain = age_at(D("1939-08-30?", "1939-08-30?"), D("1971-09-01", "1971-09-01"))
    if day_uncertain["exact"]:
        bad.append("an uncertain day-precision birth produced an exact age")
    if age_at(D("the 1920s", "192X", "year"), D("1965", "1965", "year")) is not None:
        bad.append("an age was computed from a decade (192X) — a range is not a birth day")
    if age_at(D("1939", "1939", "year"), D("1960 to 1965", "1960/1965", "unknown")) is not None:
        bad.append("an age was computed at an interval — a range is not a point in time")

    if age_at(None, D("1971", "1971", "year")) is not None:
        bad.append("an age was computed with no birth date")
    return bad


def contract_calendar_is_not_narrative_placement():
    """DOB tells you how old someone was; it does not tell you which chapter
    of their life they think it belongs to. Knowing both the year AND the age
    still does not license an era."""
    bad = []
    ls_start = D("1939-08-30", "1939-08-30")
    occurrence = {"id": "E1", "type": "union", "date": D("1971-06-12", "1971-06-12"),
                  "promoted": False}

    age = age_at(ls_start, occurrence["date"])
    if age["render"] != "31":                  # June, before an August birthday
        bad.append(f"calendar arithmetic is wrong: {age['render']}")

    def place_on_life_map(ev, derived_age=None):
        """`derived_age` is accepted and DELIBERATELY UNUSED. Knowing the
        narrator was 32 says nothing about which chapter of their life this
        belongs to — that is the narrator's to say and the operator's to
        confirm. An occurrence with no confirmed era is UNPLACED, which is a
        legitimate state and never a reason to guess."""
        if not ev.get("promoted"):
            return "not_promoted"
        return ev.get("era_candidates") or "unplaced"

    if place_on_life_map(occurrence, age["years"]) != "not_promoted":
        bad.append("an unpromoted occurrence was placed")

    occurrence["promoted"] = True
    if place_on_life_map(occurrence, age["years"]) != "unplaced":
        bad.append("a promoted occurrence with no confirmed era was given one "
                   "— calendar chronology was mistaken for narrative placement")

    # and unplaced must not drift into Today, the other half of the rule
    if place_on_life_map(occurrence, age["years"]) == "today":
        bad.append("an unplaced occurrence became Today")

    occurrence["era_candidates"] = ["early married life"]      # operator confirms
    if place_on_life_map(occurrence, age["years"]) != ["early married life"]:
        bad.append("a confirmed placement was not honoured")
    return bad


def contract_restore_is_not_migrate():
    """§3.11 — three operations, and revision 3 collapsed two of them.
    `narrator_package.py:7`: "restore this narrator AS this narrator — every
    id verbatim, nothing overwritten, nothing merged, nothing remapped."
    An id ledger belongs to MIGRATE. A restore that sometimes remaps is not
    the operation a family was promised."""
    bad = []
    pkg = {"people": [{"id": "P1", "name": "Janice"}],
           "stories": [{"id": "S1", "candidateRef": "C1"}]}

    def restore(package, ledger=None):
        if ledger is not None:
            return {"refused": "restore does not take an id ledger"}
        return {"ids": [p["id"] for p in package["people"]], "remapped": False}

    def migrate(package, ledger):
        return {"ids": [ledger.get(p["id"], p["id"]) for p in package["people"]],
                "remapped": True, "ledger": ledger}

    r = restore(pkg)
    if r.get("ids") != ["P1"] or r.get("remapped"):
        bad.append("restore did not keep ids verbatim")
    if "refused" not in restore(pkg, ledger={"P1": "P9"}):
        bad.append("restore accepted an id ledger — that is migrate")

    m = migrate(pkg, {"P1": "P9"})
    if m["ids"] != ["P9"] or not m.get("ledger"):
        bad.append("migrate did not map through a reviewable ledger")

    # the two must not be reachable through one entry point
    if restore.__name__ == migrate.__name__:
        bad.append("restore and migrate are the same operation")
    return bad


CONTRACTS = [
    ("restore keeps ids; only migrate remaps (§3.11)", contract_restore_is_not_migrate),
    ("the narrator's DOB anchors the life span (§2A)", contract_dob_anchors_the_life_span),
    ("DOB conflicts and corrections resolve cleanly (§2A)", contract_dob_conflicts_and_corrections),
    ("uncertainty propagates into derived ages (§5)", contract_uncertainty_propagates),
    ("calendar chronology is not narrative placement (§2.5)", contract_calendar_is_not_narrative_placement),
    ("write conflict is decided per path (§3.10)", contract_write_is_per_path),
    ("required facts stay bounded at sixty people (§9.1)", contract_required_facts_bounded),
    ("places and events cross the domain safely (§2.7)", contract_cross_domain_references),
    ("the Life Map review gate is not bypassed (§2.5)", contract_review_gate_not_bypassed),
    ("producers resolve against the catalog (§2.2)", contract_producers_resolve_against_catalog),
    ("every entity has an export/erase lane (§3.11)", contract_every_entity_has_a_lane),
]



def main():
    ok = True
    print("\nSITUATIONS THE MODEL MUST HOLD\n" + "─" * 66)
    for title, bio in CASES.items():
        viol = run(bio)
        if viol:
            ok = False
            print(f"  FAIL  {title}")
            for r, v in viol:
                print(f"          [{r}] {v}")
        else:
            print(f"  ok    {title}")

    print("\nSITUATIONS THE MODEL MUST REFUSE\n" + "─" * 66)
    for title, (bio, expected_rule) in MUST_FAIL.items():
        viol = run(bio)
        caught = [r for r, _ in viol if r == expected_rule]
        if caught:
            print(f"  ok    refused: {title}")
        else:
            ok = False
            print(f"  FAIL  NOT refused: {title}")
            print(f"          expected rule {expected_rule!r} to fire; "
                  f"fired: {sorted({r for r, _ in viol}) or 'nothing'}")

    print("\nTHE CONTRACT WITH THE REST OF HORNELORE\n" + "─" * 66)
    for title, fn in CONTRACTS:
        viol = fn()
        if viol:
            ok = False
            print(f"  FAIL  {title}")
            for v in viol:
                print(f"          {v}")
        else:
            print(f"  ok    {title}")

    print("\n" + "─" * 66)
    print(f"  {len(RULES)} rules · {len(CASES)} situations · {len(MUST_FAIL)} refusals"
          f" · {len(CONTRACTS)} contracts")
    print("  DESIGN COHERENT" if ok else "  DESIGN HAS A HOLE — see above")
    print("\n  This checks COHERENCE, not usability, and both the rules and the")
    print("  scenarios are authored here. It cannot tell you whether an operator")
    print("  finds the form usable, or whether a narrator feels heard.\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
