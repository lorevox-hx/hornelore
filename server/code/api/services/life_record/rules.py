"""The Life Record's model rules — the ONE copy (Batch B-3, 2026-09-23).

Moved VERBATIM from scripts/design/validate_life_record_design.py, which now
imports them. Before the move there was one executable statement of the
model (the design validator) and none in the product; keeping a second copy
here would have been two lists of one truth, the drift this project keeps
paying for. The writer (writer.py) runs `run(record)` on every change set
before commit, and the design validator runs the same functions over its
fictional situations.

The input is the record as ASSEMBLED (store.assemble): the shape the
validator's situations use — people / events / relationships / stories /
places / animals, dates as {text, value, precision}, value-bearing facts as
assertions with source / status / recordedAt, competing date accounts in
`dateAssertions` with an explicit `acceptedAssertionId`.

Specification: docs/wo/WO-LIFE-RECORD-01_Spec.md §2–§5.
"""
import json
import sys


KINDS = {"parent_of", "child_of", "sibling_of", "spouse_of", "partner_of",
         "grandparent_of", "caregiver_of", "chosen_family_of", "friend_of",
         "mentor_of", "other"}
LIFE_STATUSES = {"deceased", "explicitly_living", "unknown"}
# `document` and `migrated` added for the product (Batch B, Chris
# 2026-09-23: document-sourced and migrated facts are distinct provenance).
SOURCES = {"operator", "narrator_stated", "extracted", "imported",
           "document", "migrated"}

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


_SYMMETRIC = {"sibling_of", "spouse_of", "partner_of", "friend_of", "chosen_family_of"}


def rule_no_duplicate_relationship(b):
    """§3.7 — one relationship is stored once. ADDED 2026-09-24 (Batch C-3):
    the writer accepted the same "P is parent_of N" twice, so an editor that
    re-added an existing relative would silently double them in every
    projection. Two edges of one kind between one pair are the same fact
    when their periods are EQUAL — both absent, or both the same span. A
    period present on one and absent on the other, or two different spans,
    are two relationships (married Pat once, dates unknown; remarried Pat in
    1992). For a symmetric kind the pair is unordered. Different kinds are
    different facts (a grandmother who was also the caregiver is two
    relationships to ONE person). CORRECTED in C-3 review: it first treated a
    missing period on EITHER side as a duplicate, so the unknown-dates
    remarriage it was written to allow could not be stored."""
    seen, bad = {}, []
    for r in b.get("relationships", []):
        pair = (r["subjectPersonId"], r["otherPersonId"])
        if r["kind"] in _SYMMETRIC:
            pair = tuple(sorted(pair))
        key = (pair, r["kind"], r.get("describedAs") or "")
        per = json.dumps(r.get("period"), sort_keys=True) if r.get("period") else None
        for other_id, other_per in seen.get(key, []):
            if per == other_per:
                bad.append(f"relationship {r['id']}: the same relationship as {other_id} is stored twice")
        seen.setdefault(key, []).append((r["id"], per))
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


def anchor_event(bio, person_id, ref, expected_type):
    """§2A — a birth/death pointer resolves ONLY to an event of the right
    type whose subject is THIS person. Returns (event, reason)."""
    if not ref:
        return None, "no_ref"
    ev = next((e for e in bio.get("events", []) if e["id"] == ref), None)
    if ev is None:
        return None, "ref_does_not_resolve"
    if ev.get("type") != expected_type:
        return None, f"ref_is_{ev.get('type')}_not_{expected_type}"
    subjects = [p["person"] for p in ev.get("participants", []) if p.get("role") == "subject"]
    if person_id not in subjects:
        return None, "subject_is_someone_else"
    if len(subjects) != 1:
        return None, "ambiguous_subject"
    return ev, "ok"


def rule_birth_death_refs_are_the_persons_own(b):
    """DEFECT FIXED 2026-09-22. `birthEventRef` was followed wherever it
    pointed: a UNION event belonging to a DIFFERENT person anchored the
    narrator's whole life span at 1965. The pointer is the anchor for every
    age in the record, so it is checked for type and subject, not existence."""
    bad = []
    for p in b["people"]:
        for key, typ in (("birthEventRef", "birth"), ("deathEventRef", "death")):
            ref = p.get(key)
            if ref is None:
                continue
            _, why = anchor_event(b, p["id"], ref, typ)
            if why != "ok":
                bad.append(f"person {p['id']}: {key}={ref!r} refused — {why}")
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

    def is_assertion(node, parent_key):
        """What makes a dict an assertion is WHERE it lives, not only its
        shape. A plain date is `{text, value, precision}` under `date`; a
        DATE ASSERTION has the same three keys plus provenance and lives in
        a `dateAssertions` list.

        DEFECT FIXED 2026-09-22 (second pass): the earlier shape test
        excluded anything with `text`/`precision`, so a date assertion
        MISSING its provenance looked like a plain date and escaped the very
        rule meant to catch it. Location closes that hole: inside
        `dateAssertions` everything is an assertion and must prove itself."""
        if parent_key == "dateAssertions":
            return True
        return "value" in node and not ("precision" in node or "text" in node)

    def check(node, path, parent_key=None):
        if isinstance(node, dict):
            # DEFECT FIXED 2026-09-22: this branch required BOTH value and
            # source, so a value with NO provenance was skipped entirely —
            # the rule whose whole purpose is that a value and its provenance
            # cannot be separated was blind to them being separated.
            if is_assertion(node, parent_key) and "source" not in node:
                bad.append(f"{path}: a value with no provenance")
            elif is_assertion(node, parent_key) and "status" not in node:
                bad.append(f"{path}: an assertion with no status")
            elif is_assertion(node, parent_key) and not node.get("recordedAt"):
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
                check(v, f"{path}.{k}", k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                check(v, f"{path}[{i}]", parent_key)

    check(b, "")
    return bad


def _many_valued_concepts():
    """Concepts whose catalog cardinality is `many` — several live values are
    several FACTS (two languages, two heritages), not two accounts of one.

    DEFECT FIXED 2026-09-23 (found by Batch C-1): this rule compared every
    list of assertions as one proposition, so "Igbo" beside "Swedish" was
    refused as an unlinked dispute and no narrator could record two languages.
    Cardinality lives in ONE place, the concept catalog, and is read from it.
    An event's `dateAssertions` are keyed by that name, not by a concept id,
    so a residence or service period is still one proposition per event."""
    try:
        from ..concept_catalog import load
    except ImportError:          # the rules imported outside the product package
        from api.services.concept_catalog import load
    return {cid for cid, c in load()._concepts.items() if c.get("cardinality") == "many"}


def proposition_key(list_key, assertion):
    """The identity of ONE proposition: what concept, about what, in what
    context. Two assertions COMPETE only when they share this key and differ
    in value. Two occupations with different periods are two facts, not a
    dispute; two birth dates for one event are one fact with two accounts."""
    ctx = assertion.get("context") or assertion.get("period") or assertion.get("when")
    return (list_key, json.dumps(ctx, sort_keys=True) if ctx else None)


def rule_competing_claims_kept_and_linked(b):
    """§2.4 / §3.9 — competing accounts of ONE proposition are retained and
    are either LINKED to each other or ADJUDICATED by an explicit recorded
    decision. The automatic write policy may decline to write; it may never
    pick a winner.

    DEFECT FIXED 2026-09-22. This rule read "a list of length > 1 whose
    members are assertions" as a dispute and demanded every member be
    `conflicted`. That is inference from SHAPE — the same error as the
    zero-count rule — and it produced two failures at once: it rejected the
    DOB contract's own fixture (an accepted `operator_entered` beside a
    `conflicted` alternative is a legitimate, adjudicated state), and it
    would call two successive jobs a contradiction. Conflict is a fact about
    PROPOSITIONS, so the proposition is what is compared."""
    bad = []
    many = _many_valued_concepts()

    def check(node, path, parent=None, key=None):
        if isinstance(node, list):
            assertions = [x for x in node if isinstance(x, dict) and "value" in x
                          and ("source" in x or "status" in x)]
            if len(assertions) > 1 and key not in many:
                groups = {}
                for a in assertions:
                    groups.setdefault(proposition_key(key, a), []).append(a)
                accepted = None
                if isinstance(parent, dict):
                    accepted = (parent.get("acceptedAssertionId") if key == "dateAssertions"
                                else parent.get(f"{key}AcceptedId"))
                for pk, grp in groups.items():
                    live = [a for a in grp if a.get("status") not in ("rejected", "superseded")]
                    values = {json.dumps(a.get("value"), sort_keys=True) for a in live}
                    if len(live) < 2 or len(values) < 2:
                        continue                       # no competition here
                    if any(not a.get("id") for a in live):
                        # Without ids nothing can be linked or accepted — and a
                        # None id must not read as "matches the None decision".
                        bad.append(f"{path}: competing accounts without ids "
                                   "cannot be linked or adjudicated")
                        continue
                    ids = {a.get("id") for a in live}
                    adjudicated = accepted is not None and accepted in ids
                    linked = all(a.get("conflictWith") in ids and
                                 a.get("conflictWith") != a.get("id") for a in live)
                    if not (adjudicated or linked):
                        bad.append(f"{path}: {len(live)} live accounts of one proposition, "
                                   "neither linked to each other nor adjudicated by a "
                                   "recorded acceptance")
                    if adjudicated and any(a.get("status") == "rejected" for a in grp
                                           if a.get("id") == accepted):
                        bad.append(f"{path}: the accepted assertion is rejected")
            for i, v in enumerate(node):
                check(v, f"{path}[{i}]", node, key)
            return
        if isinstance(node, dict):
            for k, v in node.items():
                check(v, f"{path}.{k}", node, k)

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
                # `or ""`: a year said with no normalised value (value None)
                # is legitimate, and used to crash here (found 2026-09-24).
                if node["precision"] == "year" and str(node.get("value") or "").count("-") > 0:
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
    ("no relationship stored twice", rule_no_duplicate_relationship),
    ("derived relationships not hand-edited", rule_derived_relationships_not_hand_edited),
    ("event participants resolve", rule_event_participants_resolve),
    ("life status valid, never inferred", rule_life_status_valid_and_not_inferred),
    ("birth/death dates stored once", rule_no_duplicate_birth_death_storage),
    ("birth/death refs are the person's own", rule_birth_death_refs_are_the_persons_own),
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


def resolve_life_span(bio, today=None):
    """§2A reference implementation — the DOB-anchored scaffold Hornelore
    already has. Nothing here is stored; it is resolved at render.

    CORRECTED 2026-09-22 against the shipped engine (checkpoint §3.3b): the
    product's span has NO end — `later_years` is open-ended and
    `chronology_accordion.py` never calls `date.today()`. So a living
    narrator's end is `open`, matching what ships; this design ADDS
    truncation at a KNOWN death date and nothing else. `today` is accepted
    for callers that want a display boundary, but it is never the span's end.

    Anchors go through `anchor_event`, so a pointer to a union, to another
    person's birth, or to an ambiguous event yields NO scaffold — with the
    reason — rather than a wrong one."""
    nar = _person(bio, bio["narrator_person_id"])
    birth_ev, why = anchor_event(bio, nar["id"], nar.get("birthEventRef"), "birth")
    start = accepted_date(birth_ev) if birth_ev else None
    status = (nar.get("lifeStatus") or {}).get("value", "unknown")

    if status == "deceased":
        death_ev, dwhy = anchor_event(bio, nar["id"], nar.get("deathEventRef"), "death")
        death = accepted_date(death_ev) if death_ev else None
        end, kind = (death, "death_date") if death else (None, "deceased_date_unknown")
    elif status == "explicitly_living":
        end, kind = None, "open"                 # the shipped behaviour, kept
    else:
        end, kind = None, "life_status_unknown"

    return {"start": start, "end": end, "end_kind": kind,
            "available": start is not None,
            "anchor": why,
            "precision": (start or {}).get("precision")}


def _shipped_compute_age():
    """The product already has correct calendar arithmetic —
    `life_spine/validator.py:110` — and `age_arithmetic.py` deliberately
    does not. This REUSES the correct one rather than adding another
    implementation (checkpoint §3.3c; Chris, 2026-09-23)."""
    from ...life_spine.validator import compute_age
    return compute_age


def age_at(birth, when):
    """Uncertainty PROPAGATES, and the arithmetic is the SHIPPED arithmetic.

    DEFECT FIXED 2026-09-22, twice. First: this subtracted birth years and
    called the result exact — 32 where she was 31 — and the contract asserted
    32, so the wrong answer was written in as behaviour and as expectation.
    Second: the fix was a third age implementation in a codebase that already
    had a correct one. Now `life_spine.validator.compute_age` does the
    arithmetic; this function only decides how much of it is honest to say.

    The shipped function picks a July-1 midpoint for a year-only event. That
    is a CHOICE, and for a coarse date the honest answer is a pair. So the
    bounds come from the same function at Jan 1 and Dec 31."""
    if not birth or not when or not birth.get("value") or not when.get("value"):
        return None
    compute_age = _shipped_compute_age()
    from datetime import date

    def parts(d):
        s = str(d["value"]).strip("~?")
        return (int(s[:4]),
                int(s[5:7]) if len(s) >= 7 else None,
                int(s[8:10]) if len(s) >= 10 else None)

    by, bm, bd = parts(birth)
    wy, wm, wd = parts(when)
    vague = {"approximate", "uncertain"}
    approximate = (birth.get("precision") in vague or when.get("precision") in vague)
    complete = None not in (bm, bd, wm, wd)

    if complete and not approximate:
        years = compute_age(date(by, bm, bd), wy, wm, wd)
        return {"years": years, "exact": True, "render": str(years)}

    # Coarse on either side: bound it with the SAME arithmetic at the two
    # extremes of what is known, rather than choosing a midpoint.
    dob = date(by, bm or 7, bd or 1)
    lo = compute_age(dob if (bm and bd) else date(by, 12, 31), wy, wm or 1, wd or 1)
    hi = compute_age(dob if (bm and bd) else date(by, 1, 1), wy, wm or 12, wd or 31)
    lo, hi = min(lo, hi), max(lo, hi)
    if approximate:
        return {"years": hi, "exact": False, "low": lo, "high": hi,
                "render": f"about {hi}"}
    return {"years": hi, "exact": False, "low": lo, "high": hi,
            "render": f"{lo} or {hi}" if lo != hi else str(hi)}


def run(b):
    out = []
    for name, fn in RULES:
        out.extend((name, v) for v in fn(b))
    return out
