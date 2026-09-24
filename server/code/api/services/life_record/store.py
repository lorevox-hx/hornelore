"""Read side of the Life Record: assemble the record from lr_* rows.

READS ONLY. Nothing here writes — not on GET, render, section change or
narrator switch (WO-LIFE-RECORD-01 §3.10). A narrator with no record yet
assembles as an empty record at revision 0; the row is created by the first
real write, never by a read.

The assembled shape is the one the model rules read (rules.py, and the
design validator's situations):

  * a value-bearing concept assembles as a LIST of assertions under its
    concept id, with `<concept_id>AcceptedId` when a human has decided;
  * the single "current" value (e.g. `lifeStatus`, an event's `date`) is
    DERIVED here: the accepted assertion, else the only live one, else
    absent — two live accounts with no decision are UNRESOLVED and are
    reported as such, never guessed (§2.4);
  * event dates assemble as `dateAssertions` + `acceptedAssertionId`.

Each concept gets its OWN list. `rules.proposition_key` tells propositions
apart by context only, so a shared bucket of mixed concepts would read as a
single disputed fact.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

# Which catalog concept holds the date of each event type. Types absent here
# cannot carry a date until the catalog defines one (fail closed).
EVENT_DATE_CONCEPT = {
    "birth": "person.birth.date",
    "death": "person.death.date",
    "union": "event.union.date",
    "move": "event.residence.period",
    "service": "event.service.period",
}
DATE_CONCEPTS = set(EVENT_DATE_CONCEPT.values())

REPORTED_COUNT_PREFIX = "person.reported_count."
LIVE = lambda a: a.get("status") not in ("rejected", "superseded")  # noqa: E731


def _j(text: Optional[str], default: Any = None) -> Any:
    if text is None or text == "":
        return default
    return json.loads(text)


def assertion_view(row: sqlite3.Row) -> Dict[str, Any]:
    """An assertion in the rules' vocabulary. A date assertion is FLAT — its
    {text, value, precision} beside its provenance — as the validator writes
    it; every other assertion carries `value`."""
    value = _j(row["value_json"])
    out: Dict[str, Any] = {
        "id": row["id"], "source": row["source"], "status": row["status"],
        "recordedAt": row["recorded_at"], "recordedBy": row["recorded_by"],
        "assertedBy": row["asserted_by"],
    }
    if row["concept_id"] in DATE_CONCEPTS and isinstance(value, dict):
        out.update({k: value.get(k) for k in ("text", "value", "precision")})
    else:
        out["value"] = value
    if row["context_key"]:
        out["context"] = _j(row["context_key"], row["context_key"])
    for col, key in (("source_id", "sourceId"), ("supersedes_id", "supersedes"),
                     ("superseded_by_id", "supersededBy"),
                     ("conflict_with_id", "conflictWith")):
        if row[col]:
            out[key] = row[col]
    return out


def derived(assertions: List[Dict[str, Any]], accepted_id: Optional[str]):
    """The accepted assertion, else the only live one, else None (unresolved)."""
    live = [a for a in assertions if LIVE(a)]
    if accepted_id is not None:
        return next((a for a in live if a["id"] == accepted_id), None)
    return live[0] if len(live) == 1 else None


def _names(con, person_id):
    out = []
    for r in con.execute("SELECT * FROM lr_names WHERE person_id = ? ORDER BY created_at, id",
                         (person_id,)):
        n = {"id": r["id"], "fullText": r["full_text"], "kind": r["kind"]}
        for col, key, is_json in (("given_parts_json", "givenParts", True),
                                  ("family", "family", False),
                                  ("birth_family", "birthFamily", False),
                                  ("prefixes_json", "prefixes", True),
                                  ("suffixes_json", "suffixes", True),
                                  ("use", "use", False),
                                  ("period_json", "period", True),
                                  ("pronunciation", "pronunciation", False),
                                  ("origin_story", "originStory", False)):
            if r[col] is not None:
                n[key] = _j(r[col]) if is_json else r[col]
        out.append(n)
    return out


def assemble(con: sqlite3.Connection, narrator_id: str) -> Dict[str, Any]:
    """The whole record for one narrator. Every query is scoped by narrator_id."""
    rec = con.execute("SELECT * FROM lr_record WHERE narrator_id = ?", (narrator_id,)).fetchone()
    bio: Dict[str, Any] = {
        "narrator_id": narrator_id,
        "narrator_person_id": narrator_id,
        "revision": rec["revision"] if rec else 0,
        "schema_version": rec["schema_version"] if rec else 1,
        "people": [], "events": [], "relationships": [], "stories": [],
        "places": [], "animals": [], "reportedCounts": {},
    }
    if rec is None:
        return bio

    # assertions and acceptances, grouped by subject
    by_subject: Dict[tuple, Dict[str, List[Dict[str, Any]]]] = {}
    for r in con.execute("SELECT * FROM lr_assertions WHERE narrator_id = ? "
                         "ORDER BY recorded_at, id", (narrator_id,)):
        by_subject.setdefault((r["subject_type"], r["subject_id"]), {}) \
                  .setdefault(r["concept_id"], []).append(assertion_view(r))
    accepted: Dict[tuple, str] = {}
    for r in con.execute("SELECT * FROM lr_acceptances WHERE narrator_id = ?", (narrator_id,)):
        accepted[(r["subject_type"], r["subject_id"], r["concept_id"], r["context_key"])] = \
            r["accepted_assertion_id"]

    def attach(node, stype, sid, skip=()):
        """Per-concept lists + explicit acceptance, on `node`."""
        for concept, lst in by_subject.get((stype, sid), {}).items():
            if concept in skip:
                continue
            node[concept] = lst
            acc = accepted.get((stype, sid, concept, ""))
            if acc is not None:
                node[f"{concept}AcceptedId"] = acc

    for p in con.execute("SELECT * FROM lr_people WHERE narrator_id = ? ORDER BY created_at, id",
                         (narrator_id,)):
        person: Dict[str, Any] = {"id": p["id"], "names": _names(con, p["id"])}
        for col, key in (("birth_event_id", "birthEventRef"), ("death_event_id", "deathEventRef"),
                         ("preferred_name_id", "preferredNameRef")):
            if p[col]:
                person[key] = p[col]
        attach(person, "person", p["id"])
        concepts = by_subject.get(("person", p["id"]), {})
        if "person.life_status" in concepts:
            ls = derived(concepts["person.life_status"],
                         accepted.get(("person", p["id"], "person.life_status", "")))
            if ls is not None:
                person["lifeStatus"] = ls
        # Reported counts ("six siblings stated") — the narrator's live at
        # the record root, where the counting rule reads them.
        for concept, lst in concepts.items():
            if concept.startswith(REPORTED_COUNT_PREFIX):
                rc = derived(lst, accepted.get(("person", p["id"], concept, "")))
                if rc is not None:
                    target = bio["reportedCounts"] if p["id"] == narrator_id \
                        else person.setdefault("reportedCounts", {})
                    target[concept[len(REPORTED_COUNT_PREFIX):]] = rc
        bio["people"].append(person)

    for pl in con.execute("SELECT * FROM lr_places WHERE narrator_id = ? ORDER BY created_at, id",
                          (narrator_id,)):
        place = {"id": pl["id"], "label": pl["label"]}
        if pl["parts_json"]:
            place["parts"] = _j(pl["parts_json"])
        if pl["merged_into_id"]:
            place["mergedInto"] = pl["merged_into_id"]
        attach(place, "place", pl["id"])
        bio["places"].append(place)

    for e in con.execute("SELECT * FROM lr_events WHERE narrator_id = ? ORDER BY created_at, id",
                         (narrator_id,)):
        ev: Dict[str, Any] = {"id": e["id"], "type": e["type"], "participants": [
            {"person": r["person_id"], "role": r["role"]}
            for r in con.execute("SELECT person_id, role FROM lr_event_participants "
                                 "WHERE event_id = ? ORDER BY person_id, role", (e["id"],))]}
        if e["place_id"]:
            ev["place"] = e["place_id"]
        if e["attributes_json"]:
            ev["attributes"] = _j(e["attributes_json"])
        date_concept = EVENT_DATE_CONCEPT.get(e["type"])
        attach(ev, "event", e["id"], skip=(date_concept,) if date_concept else ())
        if date_concept:
            dates = by_subject.get(("event", e["id"]), {}).get(date_concept, [])
            if dates:
                ev["dateAssertions"] = dates
                acc = accepted.get(("event", e["id"], date_concept, ""))
                if acc is not None:
                    ev["acceptedAssertionId"] = acc
                d = derived(dates, acc)
                if d is not None:
                    ev["date"] = {k: d.get(k) for k in ("text", "value", "precision")}
        bio["events"].append(ev)

    for r in con.execute("SELECT * FROM lr_relationships WHERE narrator_id = ? "
                         "ORDER BY created_at, id", (narrator_id,)):
        rel: Dict[str, Any] = {"id": r["id"], "subjectPersonId": r["subject_person_id"],
                               "otherPersonId": r["other_person_id"], "kind": r["kind"],
                               "basis": r["basis"]}
        for col, key, is_json in (("described_as", "describedAs", False),
                                  ("qualifiers_json", "qualifiers", True),
                                  ("narrator_label", "narratorLabel", False),
                                  ("period_json", "period", True),
                                  ("derived_from_event_id", "derivedFromEventId", False)):
            if r[col] is not None:
                rel[key] = _j(r[col]) if is_json else r[col]
        attach(rel, "relationship", r["id"])
        kinds = by_subject.get(("relationship", r["id"]), {}).get("relationship.kind", [])
        a = derived(kinds, accepted.get(("relationship", r["id"], "relationship.kind", "")))
        if a is not None:
            rel["assertion"] = a
        bio["relationships"].append(rel)

    for a in con.execute("SELECT * FROM lr_animals WHERE narrator_id = ? ORDER BY created_at, id",
                         (narrator_id,)):
        animal = {"id": a["id"]}
        for col, key in (("name", "name"), ("species", "species")):
            if a[col] is not None:
                animal[key] = a[col]
        if a["attributes_json"]:
            animal["attributes"] = _j(a["attributes_json"])
        attach(animal, "animal", a["id"])
        bio["animals"].append(animal)

    refs_by_story: Dict[str, Dict[str, List[str]]] = {}
    for r in con.execute("SELECT story_id, target_type, target_id FROM lr_story_refs "
                         "WHERE narrator_id = ? ORDER BY target_type, target_id", (narrator_id,)):
        refs_by_story.setdefault(r["story_id"], {}) \
                     .setdefault(f"{r['target_type']}Refs".replace("personRefs", "peopleRefs"),
                                 []).append(r["target_id"])
    for s in con.execute("SELECT * FROM lr_stories WHERE narrator_id = ? ORDER BY created_at, id",
                         (narrator_id,)):
        story: Dict[str, Any] = {"id": s["id"], "origin": s["origin"], "kind": s["kind"]}
        if s["candidate_id"]:
            story["candidateRef"] = s["candidate_id"]
        if s["body"] is not None:
            story["body"] = s["body"]
        for col, key, is_json in (("title", "title", False), ("when_json", "when", True),
                                  ("supersedes_id", "supersedes", False)):
            if s[col] is not None:
                story[key] = _j(s[col]) if is_json else s[col]
        story.update(refs_by_story.get(s["id"], {}))
        bio["stories"].append(story)

    # The narrator's candidate inventory: what a captured story may resolve to.
    bio["_storyCandidates"] = [r["id"] for r in con.execute(
        "SELECT id FROM story_candidates WHERE narrator_id = ?", (narrator_id,))]
    return bio
