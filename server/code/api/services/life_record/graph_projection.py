"""The family graph as a PROJECTION of the Life Record (Batch B-4).

The graph tables (`graph_persons`, `graph_relationships`) are not a second
place where facts live. Every row this module writes is derived from the
assembled record, tagged `source='life_record'`, and rewritten from the record
on every committed Life Record write — inside the writer's own transaction, so
the record and its graph can never be observed disagreeing.

What the projection will NOT do, on purpose:

  * guess. An unresolved date (two live accounts, no decision) projects as
    empty, not as either account. Unknown life status projects as not
    deceased — the graph has no "unknown" column, and `deceased=1` would be
    an assertion nobody made.
  * disclose. A name whose `use` is `historical_only` or `do_not_use` is never
    the display name; the graph shows no former names at all. Batch D owns
    the full disclosure rules; the projection only refuses to leak.
  * touch rows it did not write. Rows the questionnaire UI wrote (any other
    source) are left alone; the graph routes in turn cannot edit, forge or
    remove projected rows (db._graph_guard_row).

Projected ids are `lr:<record id>`, so they cannot collide with the UI's
UUIDs. Record ids are already globally unique (a single-column primary key),
so they cannot collide across narrators either.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from ... import db as _db

PREFIX = _db.GRAPH_PROJECTION_ID_PREFIX
_HIDDEN_USES = ("historical_only", "do_not_use")


def graph_id(record_id: str) -> str:
    return PREFIX + record_id


def _display_name(person: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    names = person.get("names") or []
    by_id = {n["id"]: n for n in names}
    pref = by_id.get(person.get("preferredNameRef"))
    if pref is not None and pref.get("use") not in _HIDDEN_USES:
        return pref
    for n in names:
        if n.get("kind", "current") == "current" and n.get("use") not in _HIDDEN_USES:
            return n
    return None


def _derived_value(node: Dict[str, Any], concept: str) -> Any:
    from .store import derived
    lst = node.get(concept) or []
    d = derived(lst, node.get(f"{concept}AcceptedId"))
    return None if d is None else d.get("value")


def _text(v: Any) -> str:
    if v is None:
        return ""
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, sort_keys=True)


def project(record: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Pure: the graph rows the record implies. No IO."""
    nid = record["narrator_id"]
    events = {e["id"]: e for e in record.get("events", [])}
    places = {p["id"]: p for p in record.get("places", [])}
    persons = []
    for p in record.get("people", []):
        n = _display_name(p) or {}
        given = n.get("givenParts") or []
        birth = events.get(p.get("birthEventRef")) or {}
        persons.append({
            "id": graph_id(p["id"]),
            "display_name": n.get("fullText", ""),
            "first_name": given[0] if given else "",
            "middle_name": " ".join(given[1:]),
            "last_name": n.get("family") or "",
            "maiden_name": n.get("birthFamily") or "",
            "birth_date": (birth.get("date") or {}).get("text") or "",
            "birth_place": (places.get(birth.get("place")) or {}).get("label", ""),
            "occupation": _text(_derived_value(p, "person.occupation")),
            "deceased": (p.get("lifeStatus") or {}).get("value") == "deceased",
            "is_narrator": p["id"] == nid,
            "meta": {"lifeRecordId": p["id"]},
        })
    rels = []
    for r in record.get("relationships", []):
        period = r.get("period") if isinstance(r.get("period"), dict) else {}
        rels.append({
            "id": graph_id(r["id"]),
            "from_person_id": graph_id(r["subjectPersonId"]),
            "to_person_id": graph_id(r["otherPersonId"]),
            "relationship_type": r["kind"],
            "subtype": r.get("describedAs") or "",
            "label": r.get("narratorLabel") or "",
            "start_date": _text(period.get("start")),
            "end_date": _text(period.get("end")),
            "meta": {"lifeRecordId": r["id"]},
        })
    return {"persons": persons, "relationships": rels}


def project_graph(con: sqlite3.Connection, record: Dict[str, Any]) -> int:
    """Rewrite this narrator's projected rows from `record`, on `con` (the
    caller's transaction), and bump the graph revision. Returns it.

    Upsert, not delete-and-reinsert: a UI-written edge that points at a
    projected person must survive re-projection (the FK cascades on delete).
    Projected rows that no longer exist in the record are removed."""
    nid = record["narrator_id"]
    rows = project(record)
    now = _db._now_iso()
    provenance = f"life_record:r{record.get('revision', 0)}"
    want_p = {p["id"] for p in rows["persons"]}
    want_r = {r["id"] for r in rows["relationships"]}

    for r in con.execute("SELECT id FROM graph_relationships WHERE narrator_id=? AND source=?",
                         (nid, _db.GRAPH_PROJECTION_SOURCE)).fetchall():
        if r["id"] not in want_r:
            con.execute("DELETE FROM graph_relationships WHERE id=?", (r["id"],))
    for r in con.execute("SELECT id FROM graph_persons WHERE narrator_id=? AND source=?",
                         (nid, _db.GRAPH_PROJECTION_SOURCE)).fetchall():
        if r["id"] not in want_p:
            con.execute("DELETE FROM graph_persons WHERE id=?", (r["id"],))

    for p in rows["persons"]:
        con.execute(
            """INSERT INTO graph_persons
                   (id, narrator_id, display_name, first_name, middle_name, last_name,
                    maiden_name, birth_date, birth_place, occupation, deceased, is_narrator,
                    source, provenance, confidence, created_at, updated_at, meta_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1.0,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                   display_name=excluded.display_name, first_name=excluded.first_name,
                   middle_name=excluded.middle_name, last_name=excluded.last_name,
                   maiden_name=excluded.maiden_name, birth_date=excluded.birth_date,
                   birth_place=excluded.birth_place, occupation=excluded.occupation,
                   deceased=excluded.deceased, is_narrator=excluded.is_narrator,
                   provenance=excluded.provenance, updated_at=excluded.updated_at,
                   meta_json=excluded.meta_json
               WHERE graph_persons.narrator_id = excluded.narrator_id
                 AND graph_persons.source = excluded.source""",
            (p["id"], nid, p["display_name"], p["first_name"], p["middle_name"], p["last_name"],
             p["maiden_name"], p["birth_date"], p["birth_place"], p["occupation"],
             1 if p["deceased"] else 0, 1 if p["is_narrator"] else 0,
             _db.GRAPH_PROJECTION_SOURCE, provenance, now, now, json.dumps(p["meta"])))
    for r in rows["relationships"]:
        con.execute(
            """INSERT INTO graph_relationships
                   (id, narrator_id, from_person_id, to_person_id, relationship_type, subtype,
                    label, status, notes, source, provenance, confidence, start_date, end_date,
                    created_at, updated_at, meta_json)
               VALUES (?,?,?,?,?,?,?,'active','',?,?,1.0,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                   from_person_id=excluded.from_person_id, to_person_id=excluded.to_person_id,
                   relationship_type=excluded.relationship_type, subtype=excluded.subtype,
                   label=excluded.label, provenance=excluded.provenance,
                   start_date=excluded.start_date, end_date=excluded.end_date,
                   updated_at=excluded.updated_at, meta_json=excluded.meta_json
               WHERE graph_relationships.narrator_id = excluded.narrator_id
                 AND graph_relationships.source = excluded.source""",
            (r["id"], nid, r["from_person_id"], r["to_person_id"], r["relationship_type"],
             r["subtype"], r["label"], _db.GRAPH_PROJECTION_SOURCE, provenance,
             r["start_date"], r["end_date"], now, now, json.dumps(r["meta"])))
    return _db.graph_bump_revision(con, nid)


def read_projection(con: sqlite3.Connection, narrator_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """The projected rows as stored, in `project()`'s shape — for agreement checks."""
    persons = [{
        "id": r["id"], "display_name": r["display_name"], "first_name": r["first_name"],
        "middle_name": r["middle_name"], "last_name": r["last_name"],
        "maiden_name": r["maiden_name"], "birth_date": r["birth_date"],
        "birth_place": r["birth_place"], "occupation": r["occupation"],
        "deceased": bool(r["deceased"]), "is_narrator": bool(r["is_narrator"]),
        "meta": json.loads(r["meta_json"] or "{}"),
    } for r in con.execute("SELECT * FROM graph_persons WHERE narrator_id=? AND source=? ORDER BY id",
                           (narrator_id, _db.GRAPH_PROJECTION_SOURCE))]
    rels = [{
        "id": r["id"], "from_person_id": r["from_person_id"], "to_person_id": r["to_person_id"],
        "relationship_type": r["relationship_type"], "subtype": r["subtype"], "label": r["label"],
        "start_date": r["start_date"], "end_date": r["end_date"],
        "meta": json.loads(r["meta_json"] or "{}"),
    } for r in con.execute("SELECT * FROM graph_relationships WHERE narrator_id=? AND source=? "
                           "ORDER BY id", (narrator_id, _db.GRAPH_PROJECTION_SOURCE))]
    return {"persons": persons, "relationships": rels}
