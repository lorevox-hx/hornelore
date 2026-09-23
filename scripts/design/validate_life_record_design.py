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

KINDS = {"parent_of", "child_of", "sibling_of", "spouse_of", "partner_of",
         "grandparent_of", "caregiver_of", "chosen_family_of", "friend_of",
         "mentor_of", "other"}
LIFE_STATUSES = {"deceased", "explicitly_living", "unknown"}
SOURCES = {"operator", "narrator_stated", "extracted", "imported"}

# §3.9 — the EXISTING vocabulary, adopted rather than reinvented. Revision 2
# settled this; the validator had been left on the invented `stated/disputed`
# names, so it was checking a model the specification no longer describes.
ASSERTION_STATUSES = {"empty", "needs_verify", "operator_entered",
                      "conflicted", "rejected", "narrator_corrected",
                      "superseded"}


def rule_person_ids_unique(b):
    seen, bad = set(), []
    for p in b["people"]:
        if p["id"] in seen:
            bad.append(f"duplicate person id {p['id']}")
        seen.add(p["id"])
    return bad


def rule_one_narrator(b):
    """§3.1 — narrator_person_id is a pointer, so two narrators is impossible
    by construction. The check is that it resolves."""
    ids = {p["id"] for p in b["people"]}
    if b.get("narrator_person_id") not in ids:
        return ["narrator_person_id does not resolve to a person"]
    return []


def rule_relationship_endpoints_resolve(b):
    """§3.7 — a relationship to an unrecorded person is refused, never stored
    as a name."""
    ids = {p["id"] for p in b["people"]}
    bad = []
    for r in b.get("relationships", []):
        for end in ("subjectPersonId", "otherPersonId"):
            if r.get(end) not in ids:
                bad.append(f"relationship {r['id']}: {end}={r.get(end)!r} does not resolve")
    return bad


def rule_relationship_kind_valid(b):
    bad = []
    for r in b.get("relationships", []):
        if r.get("kind") not in KINDS:
            bad.append(f"relationship {r['id']}: unknown kind {r.get('kind')!r}")
        if r.get("kind") == "other" and not r.get("describedAs"):
            bad.append(f"relationship {r['id']}: kind=other requires describedAs")
    return bad


def rule_no_stored_inverse(b):
    """§3.7 — only one direction is stored, so the pair can never disagree."""
    seen, bad = set(), []
    INV = {"parent_of": "child_of", "child_of": "parent_of",
           "grandparent_of": None, "sibling_of": "sibling_of",
           "spouse_of": "spouse_of", "partner_of": "partner_of"}
    for r in b.get("relationships", []):
        key = (r["subjectPersonId"], r["otherPersonId"], r["kind"])
        inv_kind = INV.get(r["kind"])
        if inv_kind:
            inv = (r["otherPersonId"], r["subjectPersonId"], inv_kind)
            if inv in seen:
                bad.append(f"relationship {r['id']}: inverse of an existing edge is stored separately")
        seen.add(key)
    return bad


def rule_derived_relationships_not_hand_edited(b):
    """§3.7 — basis=derived_from_event must name its event and must not carry
    hand-edited attributes."""
    events = {e["id"] for e in b.get("events", [])}
    bad = []
    for r in b.get("relationships", []):
        if r.get("basis") == "derived_from_event":
            if r.get("derivedFromEventId") not in events:
                bad.append(f"relationship {r['id']}: derived but its event does not resolve")
            if r.get("handEdited"):
                bad.append(f"relationship {r['id']}: derived relationship was edited directly")
        elif r.get("derivedFromEventId"):
            bad.append(f"relationship {r['id']}: basis=stated but names an event")
    return bad


def rule_event_participants_resolve(b):
    ids = {p["id"] for p in b["people"]}
    bad = []
    for e in b.get("events", []):
        for part in e.get("participants", []):
            if part["person"] not in ids:
                bad.append(f"event {e['id']}: participant {part['person']!r} does not resolve")
    return bad


def rule_life_status_valid_and_not_inferred(b):
    """§3.8 — status is stored, never inferred. A death event implies
    deceased; nothing else implies anything."""
    bad = []
    death_subjects = {
        part["person"]
        for e in b.get("events", []) if e["type"] == "death"
        for part in e.get("participants", []) if part.get("role") == "subject"
    }
    for p in b["people"]:
        st = (p.get("lifeStatus") or {}).get("value")
        if st is not None and st not in LIFE_STATUSES:
            bad.append(f"person {p['id']}: bad lifeStatus {st!r}")
        if p["id"] in death_subjects and st != "deceased":
            bad.append(f"person {p['id']}: has a death event but lifeStatus is {st!r}")
    return bad


def rule_no_duplicate_birth_death_storage(b):
    """§3.8 — dates live on the event. A person must not also carry one."""
    bad = []
    for p in b["people"]:
        for k in ("birth", "death"):
            v = p.get(k)
            if isinstance(v, dict) and ("date" in v or "place" in v):
                bad.append(f"person {p['id']}: stores {k}.date/place, which belongs to the event")
    return bad


def rule_assertions_well_formed(b):
    """§3.9 — a value and its provenance cannot be separated."""
    bad = []

    def is_assertion(node):
        """A date carries `value` too, so `value` alone cannot mean assertion.
        A date is recognised by its own shape and excluded."""
        return "value" in node and not ("precision" in node or "text" in node)

    def check(node, path):
        if isinstance(node, dict):
            # DEFECT FIXED 2026-09-22: this branch required BOTH value and
            # source, so a value with NO provenance was skipped entirely —
            # the rule whose whole purpose is that a value and its provenance
            # cannot be separated was blind to them being separated.
            if is_assertion(node) and "source" not in node:
                bad.append(f"{path}: a value with no provenance")
            elif is_assertion(node) and "status" not in node:
                bad.append(f"{path}: an assertion with no status")
            elif is_assertion(node) and not node.get("recordedAt"):
                # Provenance is who said it AND when. Without the when, a
                # later correction cannot be ordered against it.
                bad.append(f"{path}: an assertion with no recordedAt")
            if "value" in node and "source" in node:
                if node["source"] not in SOURCES:
                    bad.append(f"{path}: unknown source {node['source']!r}")
                st = node.get("status")
                if st is not None and st not in ASSERTION_STATUSES:
                    bad.append(f"{path}: unknown assertion status {st!r}")
                if st == "superseded" and not node.get("supersededBy"):
                    bad.append(f"{path}: superseded but nothing supersedes it")
                if st == "conflicted" and not node.get("conflictWith"):
                    bad.append(f"{path}: conflicted but no conflictWith link")
            for k, v in node.items():
                check(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                check(v, f"{path}[{i}]")

    check(b, "")
    return bad


def rule_competing_claims_kept_and_linked(b):
    """§2.4 / §3.9 — competing claims are retained and LINKED. The automatic
    write policy may decline to write; it may never pick a winner."""
    bad = []

    def check(node, path):
        if isinstance(node, list) and len(node) > 1 and all(
                isinstance(x, dict) and "value" in x and "source" in x for x in node):
            if not all(x.get("status") == "conflicted" for x in node):
                bad.append(f"{path}: competing assertions not all marked conflicted")
            elif not all(x.get("conflictWith") for x in node):
                bad.append(f"{path}: conflicted assertions are not linked")
        if isinstance(node, dict):
            for k, v in node.items():
                check(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                check(v, f"{path}[{i}]")

    check(b, "")
    return bad


def rule_stated_counts_not_overwritten(b):
    """§6 — six stated and two identified are different facts.

    DEFECT FIXED 2026-09-22. This rule used to read:

        elif rs["value"] == identified and identified == 0:
            bad.append("...appears to have been derived from an empty list")

    which REFUSED A LEGITIMATE LIFE: a narrator who says "I had no siblings"
    states zero and identifies none, and the model must hold that. The rule
    was trying to detect derivation from the values alone, which values
    cannot tell you — a stated 2 matching 2 identified is equally suspect on
    that logic, and it let that through.

    Derivation is a fact about PROVENANCE, so provenance is what is checked:
    a count must come from someone stating it, and must never carry a marker
    saying the list produced it."""
    bad = []
    reported = (b.get("reportedCounts") or {})
    STATING = {"narrator_stated", "operator", "imported"}
    for concept, rc in reported.items():
        if not isinstance(rc, dict) or "value" not in rc:
            bad.append(f"reportedCounts.{concept} is not an assertion")
            continue
        if not isinstance(rc["value"], int) or rc["value"] < 0:
            bad.append(f"reportedCounts.{concept}: {rc['value']!r} is not a count")
        if rc.get("derivedFrom"):
            bad.append(f"reportedCounts.{concept}: derived from "
                       f"{rc['derivedFrom']!r} — a count is stated, not computed")
        elif rc.get("source") not in STATING:
            bad.append(f"reportedCounts.{concept}: source {rc.get('source')!r} "
                       "does not state a count")
    return bad


def rule_story_ownership(b):
    """§2.6 — one authority over any given sentence. A captured story's words
    belong to `story_candidates` and are read through a reference; an authored
    story's words belong to the life record. Never both, never neither."""
    bad = []
    candidates = set(b.get("_storyCandidates", []))
    for s in b.get("stories", []):
        origin = s.get("origin")
        if origin not in ("captured", "authored"):
            bad.append(f"story {s['id']}: origin {origin!r} — must be captured or authored")
            continue
        if origin == "captured":
            if s.get("body"):
                bad.append(f"story {s['id']}: captured but carries its own body "
                           "— that is a second copy of the narrator's words")
            if not s.get("candidateRef"):
                bad.append(f"story {s['id']}: captured but references no candidate")
            elif not candidates:
                # `candidates and ...` made an ABSENT inventory disable the
                # check, so the least verifiable case was the one that passed.
                # A captured story with no inventory to resolve against is
                # unrestorable, which is a portability defect.
                bad.append(f"story {s['id']}: captured, but no candidate "
                           "inventory exists to resolve it against")
            elif s["candidateRef"] not in candidates:
                bad.append(f"story {s['id']}: candidateRef {s['candidateRef']!r} does not resolve")
            if s.get("bodyEdited"):
                bad.append(f"story {s['id']}: a captured story's words were edited")
        else:
            if not s.get("body"):
                bad.append(f"story {s['id']}: authored but has no body")
            if s.get("candidateRef"):
                bad.append(f"story {s['id']}: authored but claims a candidate")
    return bad


def rule_stories_are_first_class(b):
    """§3.6 — a story keeps its body, may reference many things or none, and
    never becomes an attribute of a person."""
    bad = []
    ids = {p["id"] for p in b["people"]}
    for s in b.get("stories", []):
        # The text is either held here or read through the candidate (§2.6);
        # what is forbidden is a story with no words reachable at all.
        if not s.get("body") and not s.get("candidateRef"):
            bad.append(f"story {s['id']}: no reachable text")
        if "subject" in s:
            bad.append(f"story {s['id']}: has a single `subject` — stories reference many or none")
        # DEFECT FIXED 2026-09-22: only peopleRefs were resolved, so a story
        # could point at an event, place or animal that does not exist. A
        # dangling reference is the untyped-anchor defect this model exists
        # to end; checking one of four kinds was checking none of them.
        for kind, universe in (("peopleRefs", ids),
                               ("eventRefs", {e["id"] for e in b.get("events", [])}),
                               ("placeRefs", {p["id"] for p in b.get("places", [])}),
                               ("animalRefs", {a["id"] for a in b.get("animals", [])})):
            for ref in s.get(kind, []):
                if ref not in universe:
                    bad.append(f"story {s['id']}: {kind[:-4]} {ref!r} does not resolve")
    return bad


def rule_interpretation_not_promoted(b):
    """§15.2 — a reflection must not also appear as an asserted attribute."""
    bad = []
    for s in b.get("stories", []):
        if s.get("kind") != "reflection":
            continue
        for ref in s.get("peopleRefs", []):
            person = next((p for p in b["people"] if p["id"] == ref), None)
            if person and any(a.get("derivedFromStory") == s["id"]
                              for a in person.get("attributes", [])):
                bad.append(f"story {s['id']}: a reflection became an attribute of {ref}")
    return bad


def rule_names_not_parsed(b):
    """§4 — parts are supplied, never derived. If parts exist they must be
    consistent with the full text having been typed, not split."""
    bad = []
    for p in b["people"]:
        for n in p.get("names", []):
            if not n.get("fullText"):
                bad.append(f"person {p['id']}: a name has no fullText")
            if n.get("derivedBySplit"):
                bad.append(f"person {p['id']}: name parts were derived by splitting")
            if n.get("variants") and n.get("use") == "birth" and n.get("createdNewPerson"):
                bad.append(f"person {p['id']}: a name variant created a person")
    return bad


def rule_dates_keep_original_text(b):
    """§5 — original text survives; a year never gains a day."""
    bad = []

    def check(node, path):
        if isinstance(node, dict):
            if "precision" in node and "text" in node:
                if node["precision"] == "year" and node.get("value", "").count("-") > 0:
                    bad.append(f"{path}: year precision but a fuller value was stored")
                if node.get("text") and node.get("value") and \
                        node["precision"] in ("approximate", "uncertain") and \
                        "~" not in node["value"] and "?" not in node["value"]:
                    bad.append(f"{path}: approximate/uncertain text normalised to an exact value")
            for k, v in node.items():
                check(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                check(v, f"{path}[{i}]")

    check(b, "")
    return bad


def rule_no_defaults_as_answers(b):
    """§6 — unanswered must be representable and distinct from No."""
    bad = []
    ms = b.get("militaryService")
    if ms is not None:
        if not isinstance(ms, dict) or "value" not in ms:
            bad.append("militaryService is not an assertion")
        elif ms["value"] not in ("yes", "no", "unanswered"):
            bad.append(f"militaryService has value {ms['value']!r}")
        elif ms["value"] == "no" and ms.get("source") == "form_default":
            bad.append("militaryService 'no' came from a form default")
    return bad


RULES = [
    ("person ids unique", rule_person_ids_unique),
    ("exactly one narrator, and it resolves", rule_one_narrator),
    ("relationship endpoints resolve", rule_relationship_endpoints_resolve),
    ("relationship kinds valid", rule_relationship_kind_valid),
    ("no stored inverse relationships", rule_no_stored_inverse),
    ("derived relationships not hand-edited", rule_derived_relationships_not_hand_edited),
    ("event participants resolve", rule_event_participants_resolve),
    ("life status valid, never inferred", rule_life_status_valid_and_not_inferred),
    ("birth/death dates stored once", rule_no_duplicate_birth_death_storage),
    ("assertions well formed", rule_assertions_well_formed),
    ("competing claims kept and linked", rule_competing_claims_kept_and_linked),
    ("stated counts not overwritten", rule_stated_counts_not_overwritten),
    ("story ownership is unambiguous", rule_story_ownership),
    ("stories are first class", rule_stories_are_first_class),
    ("interpretations not promoted to facts", rule_interpretation_not_promoted),
    ("names never parsed", rule_names_not_parsed),
    ("dates keep original text", rule_dates_keep_original_text),
    ("no form default becomes an answer", rule_no_defaults_as_answers),
]


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

# ── cases that MUST be refused ───────────────────────────────────────
MUST_FAIL = {}

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


def _person(bio, pid):
    return next((p for p in bio["people"] if p["id"] == pid), None)


def _event(bio, eid):
    return next((e for e in bio.get("events", []) if e["id"] == eid), None)


def accepted_date(event):
    """The assertion a human has accepted — named EXPLICITLY.

    DEFECT FIXED 2026-09-22. This used to pick the first assertion whose
    status was `operator_entered` or `narrator_corrected`, which is precisely
    the collapse §2.4 forbids: a STATUS describes how a value arrived and the
    write policy that let it in; it does not record whose account was
    accepted. Ordering by status name made the operator's typo outrank the
    narrator correcting it — the exact outcome §2.4 exists to prevent.

    Acceptance is now a recorded review decision (`acceptedAssertionId`).
    With several live assertions and no decision, the answer is UNRESOLVED,
    and unresolved is returned as such. A guess would be worse than nothing,
    because the scaffold anchors every age in the record."""
    if event is None:
        return None
    dates = event.get("dateAssertions") or ([event["date"]] if event.get("date") else [])
    live = [d for d in dates if d.get("status") not in ("rejected", "superseded")]
    if not live:
        return None
    accepted_id = event.get("acceptedAssertionId")
    if accepted_id is not None:
        return next((d for d in live if d.get("id") == accepted_id), None)
    # One live assertion is not an authority decision — there is nothing to
    # decide between. Two is, and nobody has made it.
    return live[0] if len(live) == 1 else None


def resolve_life_span(bio, today):
    """§2A reference implementation — the DOB-anchored scaffold Hornelore
    already has. Nothing here is stored; it is resolved at render."""
    nar = _person(bio, bio["narrator_person_id"])
    start = accepted_date(_event(bio, nar.get("birthEventRef")))
    status = (nar.get("lifeStatus") or {}).get("value", "unknown")

    if status == "deceased":
        death = accepted_date(_event(bio, nar.get("deathEventRef")))
        end, kind = (death, "death_date") if death else (None, "deceased_date_unknown")
    elif status == "explicitly_living":
        end, kind = {"text": today, "value": today, "precision": "day"}, "today_computed"
    else:
        end, kind = None, "life_status_unknown"

    return {"start": start, "end": end, "end_kind": kind,
            "available": start is not None,
            "precision": (start or {}).get("precision")}


def age_at(birth, when):
    """Uncertainty PROPAGATES, and the arithmetic is calendar arithmetic.

    DEFECT FIXED 2026-09-22. This subtracted birth years and called the
    result exact: born 1939-08-30, asked about 1971-06-12, it answered 32.
    She was 31 — her birthday had not come round yet. The contract check
    asserted 32, so the wrong answer was written in twice, as behaviour and
    as expectation. DOB anchors every age in the record, so an off-by-one
    here is not a display nicety.

    When month and day are not both known on both sides, the true age is one
    of two values and the answer says so rather than picking one."""
    if not birth or not when or not birth.get("value") or not when.get("value"):
        return None

    def parts(d):
        s = str(d["value"]).strip("~?")
        return (int(s[:4]),
                int(s[5:7]) if len(s) >= 7 else None,
                int(s[8:10]) if len(s) >= 10 else None)

    by, bm, bd = parts(birth)
    wy, wm, wd = parts(when)
    span = wy - by
    vague = {"approximate", "uncertain"}
    approximate = (birth.get("precision") in vague or when.get("precision") in vague)
    complete = None not in (bm, bd, wm, wd)

    if complete and not approximate:
        if (wm, wd) < (bm, bd):          # birthday not yet reached that year
            span -= 1
        return {"years": span, "exact": True, "render": str(span)}

    if approximate:
        return {"years": span, "exact": False, "low": span - 1, "high": span,
                "render": f"about {span}"}
    # dates are firm but coarse: the answer is genuinely one of two
    return {"years": span, "exact": False, "low": span - 1, "high": span,
            "render": f"{span - 1} or {span}"}


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
    if ls["end_kind"] != "today_computed":
        bad.append("a living narrator's endpoint is not the computed present")

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

    # the scaffold is RESOLVED, never stored — tomorrow's value differs
    b = bio({"birthEventRef": "B17", "lifeStatus": A("explicitly_living")}, [birth])
    if "life_span" in b:
        bad.append("the scaffold was persisted into the biography")
    if resolve_life_span(b, "2026-09-23")["end"]["value"] == \
            resolve_life_span(b, TODAY)["end"]["value"]:
        bad.append("the present-day endpoint did not move with the date "
                   "— it is a stored fact, not a view calculation")
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

    # TWO live assertions and NOBODY has decided → unresolved, never a guess
    ls = resolve_life_span(b, TODAY)
    if ls["available"]:
        bad.append("the scaffold picked a DOB with no recorded acceptance "
                   "— §2.4 says the write policy does not decide whose "
                   "account is accepted")

    birth["acceptedAssertionId"] = "A1"               # a human decides
    ls = resolve_life_span(b, TODAY)
    if not ls["available"] or ls["start"]["value"] != "1939-08-30":
        bad.append("the scaffold did not use the accepted assertion")
    if len(birth["dateAssertions"]) != 2:
        bad.append("the competing assertion was discarded")

    # The status name must NOT decide. Same two assertions, acceptance moved
    # to the extracted one: the scaffold must follow the decision, not the
    # more authoritative-sounding status.
    birth["acceptedAssertionId"] = "A2"
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
    ls = resolve_life_span(b, TODAY)
    if ls["start"]["value"] != "1940-08-30":
        bad.append("a narrator correction did not move the scaffold")
    if len(birth["dateAssertions"]) != 3:
        bad.append("the corrected assertion was deleted rather than superseded")

    # a superseded assertion may not be resurrected by pointing at it
    birth["acceptedAssertionId"] = "A1"
    if resolve_life_span(b, TODAY)["available"]:
        bad.append("a superseded assertion was accepted")
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


def run(b):
    out = []
    for name, fn in RULES:
        out.extend((name, v) for v in fn(b))
    return out


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
