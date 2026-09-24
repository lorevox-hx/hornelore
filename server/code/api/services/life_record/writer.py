"""The ONE writer of the Life Record (WO-LIFE-RECORD-01 §3.10, Batch B-2).

    apply_changes(narrator_id, base_revision, changes, actor)
        -> {"ok": True, "revision": n}
         | {"ok": False, "conflict": [...]}          # stale paths; nothing written
         | {"ok": False, "refused": [...]}           # invalid change or model rule; nothing written

    change = {"op": "add" | "set" | "remove", "path": "...", "value"?: ..., "expectedPrevious"?: ...}

THE CONTRACT
  * CONFLICT IS PER PATH. The write is rejected if and only if some path's
    current value differs from its `expectedPrevious`. An intervening edit to
    an unrelated path does not reject; a stale `baseRevision` alone is not a
    conflict — it is recorded on the revision and returned with a conflict.
  * `expectedPrevious` is REQUIRED on every `set` and `remove`. The absent
    case is written explicitly as `null`. `add` names a new id that must not
    exist anywhere.
  * ALL-OR-NOTHING. One `BEGIN IMMEDIATE` transaction: every expectation is
    checked against the state BEFORE the change set, every change applied,
    then the model rules (rules.py) run on the resulting record. Any conflict,
    refusal or rule violation rolls back and writes nothing.
  * NARRATOR ISOLATION (D8). Every id a change names must belong to this
    narrator; ids are global primary keys, so another narrator's id is
    refused, never touched.
  * NEVER INFERS. No person merge, no inverse relationship, no life status
    from a date, no date from an age, no acceptance from a status. A death
    event does not set `deceased`; the caller asserts it, in the same change
    set, and the rules refuse the record if it does not.
  * ASSERTIONS ARE NEVER EDITED. A correction is a NEW assertion that
    `supersedes` the old one, whose status becomes `superseded` — both
    survive (§3.9). Acceptance is a separate, explicit human decision
    (`acceptances/...`), never derived from provenance (§2.4).

PATHS
  people/<pid>                                  add {} · remove
  people/<pid>/names/<nid>                      add · set · remove   {fullText, kind, givenParts, family, birthFamily,
                                                                     prefixes, suffixes, use, period, pronunciation, originStory}
  people/<pid>/birthEventRef | deathEventRef | preferredNameRef          set <id>|null
  places/<id>                                   add · set · remove   {label, parts}
  events/<id>                                   add · set · remove   {type, place, participants:[{person, role}], attributes}
  relationships/<id>                            add · set · remove   {subjectPersonId, otherPersonId, kind, describedAs,
                                                                     qualifiers, narratorLabel, period, basis, derivedFromEventId}
  animals/<id>                                  add · set · remove   {name, species, attributes}
  stories/<id>                                  add · set · remove   {origin, candidateRef|body, kind, title, when,
                                                                     supersedes, peopleRefs, placeRefs, eventRefs, animalRefs}
  sources/<id>                                  add                  {kind, ref, description}
  assertions/<id>                               add                  {subjectType, subjectId, conceptId, context, value,
                                                                     source, sourceId, assertedBy, status, supersedes, conflictWith}
  assertions/<id>/status | supersededBy | conflictWith                  set
  acceptances/<subjectType>/<subjectId>/<conceptId>                     set <assertionId>|null
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ... import db as _db
from . import graph_projection as _graph
from . import rules as _rules
from . import store as _store

_ABSENT = None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _dump(v: Any) -> Optional[str]:
    return None if v is None else json.dumps(v, sort_keys=True, ensure_ascii=False)


def _same(a: Any, b: Any) -> bool:
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


class _Refuse(Exception):
    def __init__(self, path: str, why: str):
        super().__init__(why)
        self.item = {"path": path, "reason": why}


def _catalog_concepts() -> set:
    from ..concept_catalog import load
    return set(load()._concepts)


# ── entity specs: the client-facing fields of each simple entity ────────
# (field, column, is_json). The view of an entity path is exactly these.
_NAME_FIELDS = (("fullText", "full_text", False), ("kind", "kind", False),
                ("givenParts", "given_parts_json", True), ("family", "family", False),
                ("birthFamily", "birth_family", False), ("prefixes", "prefixes_json", True),
                ("suffixes", "suffixes_json", True), ("use", "use", False),
                ("period", "period_json", True), ("pronunciation", "pronunciation", False),
                ("originStory", "origin_story", False))
_PLACE_FIELDS = (("label", "label", False), ("parts", "parts_json", True))
_EVENT_FIELDS = (("type", "type", False), ("place", "place_id", False),
                 ("attributes", "attributes_json", True))
_REL_FIELDS = (("subjectPersonId", "subject_person_id", False),
               ("otherPersonId", "other_person_id", False), ("kind", "kind", False),
               ("describedAs", "described_as", False), ("qualifiers", "qualifiers_json", True),
               ("narratorLabel", "narrator_label", False), ("period", "period_json", True),
               ("basis", "basis", False), ("derivedFromEventId", "derived_from_event_id", False))
_ANIMAL_FIELDS = (("name", "name", False), ("species", "species", False),
                  ("attributes", "attributes_json", True))
_STORY_FIELDS = (("origin", "origin", False), ("candidateRef", "candidate_id", False),
                 ("body", "body", False), ("kind", "kind", False), ("title", "title", False),
                 ("when", "when_json", True), ("supersedes", "supersedes_id", False))
_STORY_REF_KINDS = {"peopleRefs": "person", "placeRefs": "place",
                    "eventRefs": "event", "animalRefs": "animal"}

_ENTITY = {  # collection -> (table, fields)
    "places": ("lr_places", _PLACE_FIELDS),
    "events": ("lr_events", _EVENT_FIELDS),
    "relationships": ("lr_relationships", _REL_FIELDS),
    "animals": ("lr_animals", _ANIMAL_FIELDS),
    "stories": ("lr_stories", _STORY_FIELDS),
}
_POINTERS = {"birthEventRef": "birth_event_id", "deathEventRef": "death_event_id",
             "preferredNameRef": "preferred_name_id"}
_SUBJECT_TABLE = {"person": "lr_people", "event": "lr_events", "place": "lr_places",
                  "animal": "lr_animals", "relationship": "lr_relationships"}


def _row_view(row, fields) -> Dict[str, Any]:
    out = {}
    for key, col, is_json in fields:
        v = row[col]
        if v is not None:
            out[key] = json.loads(v) if is_json else v
    return out


class _Tx:
    """One change set against one narrator, inside one transaction."""

    def __init__(self, con: sqlite3.Connection, narrator_id: str, actor: str):
        self.con, self.nid, self.actor, self.now = con, narrator_id, actor, _now()

    # ── ownership ──────────────────────────────────────────────────────
    def _owner(self, table: str, id_: str) -> Optional[str]:
        r = self.con.execute(f"SELECT narrator_id FROM {table} WHERE id = ?", (id_,)).fetchone()
        return None if r is None else r["narrator_id"]

    def own(self, table: str, id_: str, path: str) -> None:
        owner = self._owner(table, id_)
        if owner is None:
            raise _Refuse(path, f"{id_!r} does not exist")
        if owner != self.nid:
            raise _Refuse(path, f"{id_!r} belongs to another narrator")

    def fresh(self, table: str, id_: str, path: str) -> None:
        if not id_:
            raise _Refuse(path, "an added element must name its id")
        if self._owner(table, id_) is not None:
            raise _Refuse(path, f"{id_!r} already exists")

    # ── current value of a path (for expectedPrevious) ─────────────────
    def view(self, path: str) -> Any:
        p = path.split("/")
        c = self.con
        if p[0] == "people" and len(p) == 2:
            r = c.execute("SELECT id FROM lr_people WHERE id = ? AND narrator_id = ?",
                          (p[1], self.nid)).fetchone()
            return None if r is None else {}
        if p[0] == "people" and len(p) == 3 and p[2] in _POINTERS:
            r = c.execute(f"SELECT {_POINTERS[p[2]]} v FROM lr_people WHERE id = ? AND narrator_id = ?",
                          (p[1], self.nid)).fetchone()
            return None if r is None else r["v"]
        if p[0] == "people" and len(p) == 4 and p[2] == "names":
            r = c.execute("SELECT * FROM lr_names WHERE id = ? AND person_id = ? AND narrator_id = ?",
                          (p[3], p[1], self.nid)).fetchone()
            return None if r is None else _row_view(r, _NAME_FIELDS)
        if p[0] in _ENTITY and len(p) == 2:
            table, fields = _ENTITY[p[0]]
            r = c.execute(f"SELECT * FROM {table} WHERE id = ? AND narrator_id = ?",
                          (p[1], self.nid)).fetchone()
            if r is None:
                return None
            v = _row_view(r, fields)
            if p[0] == "events":
                v["participants"] = [{"person": x["person_id"], "role": x["role"]} for x in c.execute(
                    "SELECT person_id, role FROM lr_event_participants WHERE event_id = ? "
                    "ORDER BY person_id, role", (p[1],))]
            if p[0] == "stories":
                for key, t in _STORY_REF_KINDS.items():
                    refs = [x["target_id"] for x in c.execute(
                        "SELECT target_id FROM lr_story_refs WHERE story_id = ? AND target_type = ? "
                        "ORDER BY target_id", (p[1], t))]
                    if refs:
                        v[key] = refs
            return v
        if p[0] == "assertions" and len(p) == 3:
            col = {"status": "status", "supersededBy": "superseded_by_id",
                   "conflictWith": "conflict_with_id"}.get(p[2])
            if col is None:
                raise _Refuse(path, "only status, supersededBy and conflictWith of an assertion "
                                    "may change — a correction is a new assertion")
            r = c.execute(f"SELECT {col} v FROM lr_assertions WHERE id = ? AND narrator_id = ?",
                          (p[1], self.nid)).fetchone()
            return None if r is None else r["v"]
        if p[0] == "acceptances" and len(p) == 4:
            r = c.execute("SELECT accepted_assertion_id v FROM lr_acceptances WHERE narrator_id = ? "
                          "AND subject_type = ? AND subject_id = ? AND concept_id = ? "
                          "AND context_key = ''", (self.nid, p[1], p[2], p[3])).fetchone()
            return None if r is None else r["v"]
        raise _Refuse(path, "not a settable path")

    # ── apply one change ───────────────────────────────────────────────
    def apply(self, ch: Dict[str, Any]) -> None:
        op, path = ch.get("op"), str(ch.get("path") or "")
        v = ch.get("value")
        p = path.split("/")
        c = self.con
        if op not in ("add", "set", "remove"):
            raise _Refuse(path, f"unknown op {op!r}")

        if p[0] == "people" and len(p) == 2:
            if op == "add":
                self.fresh("lr_people", p[1], path)
                c.execute("INSERT INTO lr_people(id, narrator_id, created_at, updated_at) "
                          "VALUES (?,?,?,?)", (p[1], self.nid, self.now, self.now))
            elif op == "remove":
                self.own("lr_people", p[1], path)
                if p[1] == self.nid:
                    raise _Refuse(path, "the narrator cannot be removed from their own record")
                # Names are part of the person; everything that REFERS to them
                # (relationships, participation, assertions) must have been
                # removed explicitly in this change set, or the FK refuses.
                c.execute("DELETE FROM lr_names WHERE person_id = ?", (p[1],))
                try:
                    c.execute("DELETE FROM lr_people WHERE id = ?", (p[1],))
                except sqlite3.IntegrityError:
                    raise _Refuse(path, "the person is still referenced — remove or reassign "
                                        "their relationships and participations explicitly")
                if c.execute("SELECT 1 FROM lr_assertions WHERE subject_type = 'person' "
                             "AND subject_id = ?", (p[1],)).fetchone():
                    raise _Refuse(path, "assertions about the person remain — a person's "
                                        "evidence is not discarded implicitly")
            else:
                raise _Refuse(path, "a person has no value to set; edit names, pointers or assertions")
            return

        if p[0] == "people" and len(p) == 3 and p[2] in _POINTERS:
            if op != "set":
                raise _Refuse(path, "pointers are set, never added or removed")
            self.own("lr_people", p[1], path)
            if v is not None:
                target = "lr_names" if p[2] == "preferredNameRef" else "lr_events"
                self.own(target, v, path)
            c.execute(f"UPDATE lr_people SET {_POINTERS[p[2]]} = ?, updated_at = ? WHERE id = ?",
                      (v, self.now, p[1]))
            return

        if p[0] == "people" and len(p) == 4 and p[2] == "names":
            self.own("lr_people", p[1], path)
            if op == "remove":
                self.own("lr_names", p[3], path)
                c.execute("UPDATE lr_people SET preferred_name_id = NULL WHERE preferred_name_id = ?",
                          (p[3],))
                c.execute("DELETE FROM lr_names WHERE id = ?", (p[3],))
                return
            if not isinstance(v, dict) or not str(v.get("fullText") or "").strip():
                raise _Refuse(path, "a name needs its fullText, as supplied")
            cols = {col: (_dump(v.get(key)) if js else v.get(key)) for key, col, js in _NAME_FIELDS}
            cols["kind"] = cols["kind"] or "current"
            if cols["kind"] != "current" and cols["use"] is None:
                # Chris, 2026-09-23: a former or alternate name is not
                # disclosed merely because it exists.
                cols["use"] = "historical_only"
            if op == "add":
                self.fresh("lr_names", p[3], path)
                c.execute(f"INSERT INTO lr_names(id, narrator_id, person_id, {', '.join(cols)}, "
                          f"created_at, updated_at) VALUES (?,?,?,{','.join('?' * len(cols))},?,?)",
                          (p[3], self.nid, p[1], *cols.values(), self.now, self.now))
            else:
                self.own("lr_names", p[3], path)
                c.execute(f"UPDATE lr_names SET {', '.join(f'{k} = ?' for k in cols)}, updated_at = ? "
                          f"WHERE id = ?", (*cols.values(), self.now, p[3]))
            return

        if p[0] in _ENTITY and len(p) == 2:
            return self._entity(op, p[0], p[1], v, path)

        if p[0] == "sources" and len(p) == 2:
            if op != "add":
                raise _Refuse(path, "a source is added once and never edited")
            self.fresh("lr_sources", p[1], path)
            c.execute("INSERT INTO lr_sources(id, narrator_id, kind, ref_json, description, created_at) "
                      "VALUES (?,?,?,?,?,?)", (p[1], self.nid, (v or {}).get("kind"),
                                               _dump((v or {}).get("ref")),
                                               (v or {}).get("description"), self.now))
            return

        if p[0] == "assertions" and len(p) == 2:
            return self._add_assertion(op, p[1], v, path)

        if p[0] == "assertions" and len(p) == 3:
            if op != "set":
                raise _Refuse(path, "assertion links and status are set")
            self.own("lr_assertions", p[1], path)
            col = {"status": "status", "supersededBy": "superseded_by_id",
                   "conflictWith": "conflict_with_id"}[p[2]]
            if p[2] != "status" and v is not None:
                self.own("lr_assertions", v, path)
            c.execute(f"UPDATE lr_assertions SET {col} = ? WHERE id = ?", (v, p[1]))
            return

        if p[0] == "acceptances" and len(p) == 4:
            if op != "set":
                raise _Refuse(path, "an acceptance is set (to an assertion id, or null to withdraw)")
            stype, sid, concept = p[1], p[2], p[3]
            if stype not in _SUBJECT_TABLE:
                raise _Refuse(path, f"unknown subject type {stype!r}")
            self.own(_SUBJECT_TABLE[stype], sid, path)
            c.execute("DELETE FROM lr_acceptances WHERE narrator_id = ? AND subject_type = ? "
                      "AND subject_id = ? AND concept_id = ? AND context_key = ''",
                      (self.nid, stype, sid, concept))
            if v is not None:
                a = c.execute("SELECT * FROM lr_assertions WHERE id = ? AND narrator_id = ?",
                              (v, self.nid)).fetchone()
                if a is None:
                    raise _Refuse(path, f"{v!r} is not an assertion in this record")
                if (a["subject_type"], a["subject_id"], a["concept_id"]) != (stype, sid, concept):
                    raise _Refuse(path, "the accepted assertion is about a different proposition")
                if a["status"] in ("rejected", "superseded"):
                    raise _Refuse(path, f"a {a['status']} assertion cannot be accepted")
                c.execute("INSERT INTO lr_acceptances(id, narrator_id, subject_type, subject_id, "
                          "concept_id, context_key, accepted_assertion_id, decided_by, decided_at) "
                          "VALUES (?,?,?,?,?,'',?,?,?)",
                          (str(uuid.uuid4()), self.nid, stype, sid, concept, v, self.actor, self.now))
            return

        raise _Refuse(path, "not a writable path")

    def _entity(self, op, coll, id_, v, path):
        table, fields = _ENTITY[coll]
        c = self.con
        if op == "remove":
            self.own(table, id_, path)
            if coll == "events":
                c.execute("DELETE FROM lr_event_participants WHERE event_id = ?", (id_,))
            if coll == "stories":
                c.execute("DELETE FROM lr_story_refs WHERE story_id = ?", (id_,))
            try:
                c.execute(f"DELETE FROM {table} WHERE id = ?", (id_,))
            except sqlite3.IntegrityError:
                raise _Refuse(path, f"{id_!r} is still referenced — a referenced "
                                    f"{coll[:-1]} is not removed implicitly")
            return
        if not isinstance(v, dict):
            raise _Refuse(path, "a value object is required")
        if coll == "stories" and v.get("origin") == "captured" and v.get("body") is not None:
            raise _Refuse(path, "a captured story never carries a copy of the narrator's words")
        cols = {col: (_dump(v.get(key)) if js else v.get(key)) for key, col, js in fields}
        for key, col, _js in fields:
            if key in ("place", "candidateRef", "subjectPersonId", "otherPersonId",
                       "derivedFromEventId", "supersedes") and v.get(key):
                target = {"place": "lr_places", "candidateRef": None,
                          "subjectPersonId": "lr_people", "otherPersonId": "lr_people",
                          "derivedFromEventId": "lr_events", "supersedes": "lr_stories"}[key]
                if target:
                    self.own(target, v[key], path)
                else:
                    cand = c.execute("SELECT narrator_id FROM story_candidates WHERE id = ?",
                                     (v[key],)).fetchone()
                    if cand is None or cand["narrator_id"] != self.nid:
                        raise _Refuse(path, "the captured story's candidate is not this narrator's")
        if coll == "relationships" and cols.get("basis") is None:
            cols["basis"] = "stated"
        if op == "add":
            self.fresh(table, id_, path)
            c.execute(f"INSERT INTO {table}(id, narrator_id, {', '.join(cols)}, created_at, updated_at) "
                      f"VALUES (?,?,{','.join('?' * len(cols))},?,?)",
                      (id_, self.nid, *cols.values(), self.now, self.now))
        else:
            self.own(table, id_, path)
            if coll == "events":
                old_type = c.execute("SELECT type FROM lr_events WHERE id = ?", (id_,)).fetchone()["type"]
                if cols["type"] != old_type:
                    raise _Refuse(path, "an occurrence keeps its type; a different kind of "
                                        "occurrence is a new event")
            if coll == "stories":
                old = c.execute("SELECT origin, candidate_id, body FROM lr_stories WHERE id = ?",
                                (id_,)).fetchone()
                if old["origin"] == "captured" and (cols["origin"] != "captured"
                                                    or cols["candidate_id"] != old["candidate_id"]):
                    raise _Refuse(path, "the narrator's recorded words are never re-pointed or "
                                        "relabelled — curation may change, the recording may not")
            c.execute(f"UPDATE {table} SET {', '.join(f'{k} = ?' for k in cols)}, updated_at = ? "
                      f"WHERE id = ?", (*cols.values(), self.now, id_))
        if coll == "events":
            c.execute("DELETE FROM lr_event_participants WHERE event_id = ?", (id_,))
            for part in v.get("participants") or []:
                self.own("lr_people", part.get("person"), path)
                c.execute("INSERT INTO lr_event_participants(id, narrator_id, event_id, person_id, role) "
                          "VALUES (?,?,?,?,?)", (str(uuid.uuid4()), self.nid, id_,
                                                  part["person"], part.get("role")))
        if coll == "stories":
            c.execute("DELETE FROM lr_story_refs WHERE story_id = ?", (id_,))
            for key, ttype in _STORY_REF_KINDS.items():
                for tid in v.get(key) or []:
                    self.own(_SUBJECT_TABLE[ttype], tid, path)
                    c.execute("INSERT INTO lr_story_refs(id, narrator_id, story_id, target_type, "
                              "target_id) VALUES (?,?,?,?,?)",
                              (str(uuid.uuid4()), self.nid, id_, ttype, tid))

    def _add_assertion(self, op, id_, v, path):
        if op != "add":
            raise _Refuse(path, "an assertion is never edited or deleted — a correction "
                                "is a new assertion that supersedes it")
        if not isinstance(v, dict):
            raise _Refuse(path, "a value object is required")
        stype, sid, concept = v.get("subjectType"), v.get("subjectId"), v.get("conceptId")
        if stype not in _SUBJECT_TABLE:
            raise _Refuse(path, f"unknown subject type {stype!r}")
        self.own(_SUBJECT_TABLE[stype], sid, path)
        if concept not in _catalog_concepts():
            raise _Refuse(path, f"{concept!r} is not a concept in the catalog (fail closed)")
        if concept in _store.DATE_CONCEPTS:
            ev = self.con.execute("SELECT type FROM lr_events WHERE id = ?", (sid,)).fetchone()
            if stype != "event" or ev is None or _store.EVENT_DATE_CONCEPT.get(ev["type"]) != concept:
                raise _Refuse(path, f"{concept!r} is the date of a {concept.split('.')[1]} event "
                                    "and lives on that event (§3.8)")
            val = v.get("value")
            if not isinstance(val, dict) or not str(val.get("text") or "").strip():
                raise _Refuse(path, "a date keeps the text as said: {text, value?, precision}")
        if "value" not in v:
            raise _Refuse(path, "an assertion needs a value")
        if not str(v.get("assertedBy") or "").strip():
            raise _Refuse(path, "an assertion names whose claim it is (assertedBy)")
        self.fresh("lr_assertions", id_, path)
        for key in ("supersedes", "conflictWith", "sourceId"):
            if v.get(key):
                self.own("lr_sources" if key == "sourceId" else "lr_assertions", v[key], path)
        ctx = v.get("context")
        self.con.execute(
            "INSERT INTO lr_assertions(id, narrator_id, subject_type, subject_id, concept_id, "
            "context_key, value_json, source, source_id, recorded_by, asserted_by, recorded_at, "
            "status, supersedes_id, superseded_by_id, conflict_with_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (id_, self.nid, stype, sid, concept,
             "" if ctx in (None, "") else _dump(ctx),
             json.dumps(v["value"], sort_keys=True, ensure_ascii=False),
             v.get("source"), v.get("sourceId"), self.actor, v["assertedBy"], self.now,
             v.get("status"), v.get("supersedes"), None, v.get("conflictWith")))


def apply_changes(narrator_id: str, base_revision: Optional[int],
                  changes: List[Dict[str, Any]], actor: str) -> Dict[str, Any]:
    if not str(actor or "").strip():
        return {"ok": False, "refused": [{"path": "", "reason": "a write names its actor"}]}
    if not isinstance(changes, list) or not changes:
        return {"ok": False, "refused": [{"path": "", "reason": "an empty change set writes nothing"}]}
    con = _db._connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        try:
            if con.execute("SELECT 1 FROM people WHERE id = ?", (narrator_id,)).fetchone() is None:
                raise _Refuse("", f"narrator {narrator_id!r} does not exist")
            tx = _Tx(con, narrator_id, actor)

            # 1. EVERY expectation, against the state BEFORE the change set.
            conflicts, refused = [], []
            for ch in changes:
                path = str(ch.get("path") or "")
                if ch.get("op") in ("set", "remove"):
                    if "expectedPrevious" not in ch:
                        refused.append({"path": path, "reason": "expectedPrevious is required on "
                                        "set and remove (null for the absent case)"})
                        continue
                    try:
                        cur = tx.view(path)
                    except _Refuse as r:
                        refused.append(r.item)
                        continue
                    if not _same(cur, ch["expectedPrevious"]):
                        conflicts.append({"path": path, "current": cur,
                                          "expected": ch["expectedPrevious"]})
            rec = con.execute("SELECT revision FROM lr_record WHERE narrator_id = ?",
                              (narrator_id,)).fetchone()
            current_rev = rec["revision"] if rec else 0
            if refused:
                con.execute("ROLLBACK")
                return {"ok": False, "refused": refused}
            if conflicts:
                con.execute("ROLLBACK")
                return {"ok": False, "conflict": conflicts, "revision": current_rev,
                        "baseRevision": base_revision}

            # 2. the record row and the narrator's own person, on first write
            if rec is None:
                con.execute("INSERT INTO lr_record(narrator_id, narrator_person_id, revision, "
                            "schema_version, created_at, updated_at) VALUES (?,?,0,1,?,?)",
                            (narrator_id, narrator_id, tx.now, tx.now))
                con.execute("INSERT INTO lr_people(id, narrator_id, created_at, updated_at) "
                            "VALUES (?,?,?,?)", (narrator_id, narrator_id, tx.now, tx.now))

            # 3. apply, with the previous value of every path for the audit
            applied = []
            for ch in changes:
                path = str(ch.get("path") or "")
                prev = tx.view(path) if ch.get("op") != "add" else None
                tx.apply(ch)
                applied.append({"op": ch.get("op"), "path": path, "previous": prev,
                                "value": ch.get("value")})

            # 4. the model rules, on the record as it would be committed
            violations = _rules.run(_store.assemble(con, narrator_id))
            if violations:
                con.execute("ROLLBACK")
                return {"ok": False, "refused": [{"rule": r, "reason": why}
                                                 for r, why in violations]}

            new_rev = current_rev + 1
            con.execute("UPDATE lr_record SET revision = ?, updated_at = ? WHERE narrator_id = ?",
                        (new_rev, tx.now, narrator_id))
            con.execute("INSERT INTO lr_revisions(id, narrator_id, revision, base_revision, "
                        "changes_json, actor, created_at) VALUES (?,?,?,?,?,?,?)",
                        (str(uuid.uuid4()), narrator_id, new_rev, base_revision,
                         json.dumps(applied, ensure_ascii=False, default=str), actor, tx.now))
            # 5. the family graph, re-projected in the SAME transaction: the
            #    record and its graph are never observed disagreeing (B-4).
            graph_rev = _graph.project_graph(con, _store.assemble(con, narrator_id))
            con.execute("COMMIT")
            return {"ok": True, "revision": new_rev, "graphRevision": graph_rev}
        except _Refuse as r:
            con.execute("ROLLBACK")
            return {"ok": False, "refused": [r.item]}
        except sqlite3.IntegrityError as e:
            con.execute("ROLLBACK")
            return {"ok": False, "refused": [{"path": "", "reason": f"integrity: {e}"}]}
        except Exception:
            con.execute("ROLLBACK")
            raise
    finally:
        con.close()


def read_record(narrator_id: str) -> Dict[str, Any]:
    """The assembled record. Opens, reads and closes; writes nothing."""
    con = _db._connect()
    try:
        return _store.assemble(con, narrator_id)
    finally:
        con.close()
