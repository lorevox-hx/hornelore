"""Preservation-oriented persistence for the narrator questionnaire.

WO-QUESTIONNAIRE-PERSISTENCE-INTEGRITY-01, block 2.
Filed from BUG-BIO-QUESTIONNAIRE-LOSSY-ROUNDTRIP-01 §B–§D.

═══════════════════════════════════════════════════════════════════════
THE RULE THIS MODULE EXISTS TO ENFORCE
═══════════════════════════════════════════════════════════════════════

    An ordinary questionnaire update may ADD or MODIFY information.
    It may not silently REMOVE information.
    Removal requires an explicitly different operation.

`db.upsert_questionnaire` means "replace everything we know about this
narrator with whatever JSON this caller happens to hold". Seven callers
use it believing it means "save the change I just made". Those are
different operations and the primitive cannot tell them apart, so on
2026-09-15 an ordinary Bio Builder save deleted ten populated values from
a real narrator's parents — birth dates, birthplaces, and several hundred
words of hand-typed family history — because the rendered form declared
six of the eleven stored fields. LOST 10, CHANGED 0, ADDED 0.

═══════════════════════════════════════════════════════════════════════
THIS IS A PORT, NOT A DESIGN
═══════════════════════════════════════════════════════════════════════

`db.merge_projection_fields` (WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01)
already solved this for `interview_projections`, and its docstring says
why a guarded whole-document PUT cannot work:

    The browser envelope is not a superset of the server one. The server
    writes keys the browser has never seen. Replacing the document
    destroys those keys even when the replacement is fresh, non-empty and
    authorised. Only a per-field write can leave a key the writer does
    not know about intact.

and why a single revision counter is not enough:

    `base_version` proves only that SOMETHING changed, not WHAT. Rebasing
    a dirty path onto a newer record and retrying is safe when the server
    touched *different* paths and silently destructive when it touched the
    *same* one — the conflict is delayed, not resolved.

So the vocabulary here is deliberately that module's vocabulary —
`mutations` / `removals` / `base_revision` / `base_fields`, per-path
conflict detection, `BEGIN IMMEDIATE` around compare-and-write. A second
differently-shaped envelope for the same job is how one system acquires
two mental models.

Two deliberate departures:

  * `base_revision`, not `base_version`. `bio_builder_questionnaires.version`
    already exists and is a SCHEMA version that every client hard-codes,
    so a stale client sends exactly what a fresh one sends. Attaching
    concurrency to it would look correct and verify nothing. (On
    `interview_projections`, confusingly, `version` IS the revision
    counter. Same name, opposite meanings, adjacent tables — 0058.)

  * History. The projection lane has none. Per-path concurrency prevents a
    bad write; it cannot undo one a caller was entitled to make.

═══════════════════════════════════════════════════════════════════════
PATHS
═══════════════════════════════════════════════════════════════════════

A path names one scalar leaf, or one array entry:

    personal.fullName
    parents[0].birthDate
    parents[1]                 (a whole entry — removals only)

Absence means untouched. `None` does NOT mean delete; deletion is
`removals`, so no caller can delete by accident while serialising a form.

⚠ KNOWN LIMITATION — POSITIONAL ARRAY IDENTITY
──────────────────────────────────────────────
`parents[0].birthPlace` identifies an entry BY POSITION. That is correct
for what this module was built to stop — a form that renders six of eleven
fields deleting the other five — and it is NOT sufficient forever:

  * two clients editing different entries can still collide if one of them
    inserts or removes an entry, because every later index shifts;
  * a reorder makes a base_fields comparison compare the wrong entries,
    which the per-path check would report as a conflict (safe) but which
    would also block legitimate concurrent work (annoying);
  * a mutation held in a browser draft across a reorder would be reapplied
    to the wrong person.

The fix is stable per-entry ids — `parents/<entry-id>/birthPlace` — stamped
on every repeatable entry and migrated onto existing data. That is a
bounded piece of work with a data migration in it, and it is deliberately
NOT bundled here: shipping it alongside the loss fix would mean rewriting
every stored narrator's questionnaire in the same change that is supposed
to be making stored questionnaires safe.

Until then the exposure is bounded by the fact that a single operator edits
one narrator at a time, and every one of those failure modes surfaces as a
refused write or a visible conflict rather than as silent deletion. Raised
by independent review 2026-09-17; recorded in the bug spec as the next
block.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .. import db as _db

logger = logging.getLogger(__name__)

__all__ = [
    "QuestionnaireConflict",
    "flatten_document",
    "read_for_edit",
    "merge_questionnaire",
    "merge_whole_document",
    "replace_questionnaire",
    "reset_questionnaire",
]

WRITE_MERGE = "merge"
WRITE_REPLACE = "replace"
WRITE_RESET = "reset"
WRITE_LEGACY = "legacy"

_SEGMENT = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


class QuestionnaireConflict(Exception):
    """A write was refused because the stored value of a path it touches is
    not the value the caller hydrated. Carries the contested paths so the
    caller can surface them. The caller must NOT retry — see
    merge_projection_fields on why a blind rebase is the destructive case."""

    def __init__(self, paths: Sequence[str], revision: int):
        self.paths = list(paths)
        self.revision = revision
        super().__init__(f"contested paths: {sorted(set(paths))}")


# ── path handling ────────────────────────────────────────────────────


def _split(path: str) -> List[Any]:
    """'parents[0].birthDate' -> ['parents', 0, 'birthDate']"""
    out: List[Any] = []
    pos = 0
    for m in _SEGMENT.finditer(path):
        if m.start() != pos and path[pos:m.start()] != ".":
            raise ValueError(f"malformed path {path!r} at {pos}")
        out.append(m.group(1) if m.group(1) is not None else int(m.group(2)))
        pos = m.end()
    if pos != len(path) or not out:
        raise ValueError(f"malformed path {path!r}")
    return out


def _get(doc: Any, parts: Sequence[Any]) -> Any:
    cur = doc
    for p in parts:
        if isinstance(p, int):
            if not isinstance(cur, list) or p >= len(cur):
                return None
            cur = cur[p]
        else:
            if not isinstance(cur, Mapping) or p not in cur:
                return None
            cur = cur[p]
    return cur


def _set(doc: Dict[str, Any], parts: Sequence[Any], value: Any) -> None:
    """Create intermediate containers as the path requires. Arrays are
    padded with empty objects rather than failing, because a caller adding
    a third parent legitimately writes parents[2].* before parents[2]
    exists."""
    cur: Any = doc
    for i, p in enumerate(parts[:-1]):
        nxt = parts[i + 1]
        want_list = isinstance(nxt, int)
        if isinstance(p, int):
            while len(cur) <= p:
                cur.append([] if want_list else {})
            if cur[p] is None or not isinstance(cur[p], (dict, list)):
                cur[p] = [] if want_list else {}
            cur = cur[p]
        else:
            if p not in cur or not isinstance(cur[p], (dict, list)):
                cur[p] = [] if want_list else {}
            cur = cur[p]
    last = parts[-1]
    if isinstance(last, int):
        while len(cur) <= last:
            cur.append({})
        cur[last] = value
    else:
        cur[last] = value


def _unset(doc: Dict[str, Any], parts: Sequence[Any]) -> bool:
    parent = _get(doc, parts[:-1]) if len(parts) > 1 else doc
    last = parts[-1]
    if isinstance(last, int):
        if isinstance(parent, list) and 0 <= last < len(parent):
            parent.pop(last)          # entries compact; scalars do not
            return True
        return False
    if isinstance(parent, Mapping) and last in parent:
        del parent[last]
        return True
    return False


def flatten_document(doc: Any, prefix: str = "") -> Dict[str, Any]:
    """Every populated scalar leaf, by path.

    Empty string / None / [] / {} are NOT leaves: a form that renders a
    field it has no value for submits "", and that must not be mistaken
    for an instruction to blank a stored value. Blanking is `removals`.
    """
    out: Dict[str, Any] = {}
    if isinstance(doc, Mapping):
        for k, v in doc.items():
            out.update(flatten_document(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            out.update(flatten_document(v, f"{prefix}[{i}]"))
    else:
        if doc not in (None, "", [], {}):
            out[prefix] = doc
    return out


# ── read ─────────────────────────────────────────────────────────────


def read_for_edit(person_id: str) -> Dict[str, Any]:
    """The stored document plus what a caller needs to write safely back.

    Deliberately reads the STORED row, never `bio_questionnaire_view` — the
    view projects nine sections and drops grandparents, marriage,
    familyTraditions, pets, technology, earlyMemories, laterYears, hobbies
    and additionalNotes entirely. A caller that hydrated from the view and
    wrote back what it received would delete seven sections, which is this
    bug's original mechanism arriving through the merge path.
    """
    con = _db._connect()
    try:
        row = con.execute(
            "SELECT questionnaire_json, source, version, revision, updated_at "
            "FROM bio_builder_questionnaires WHERE person_id = ?",
            (person_id,),
        ).fetchone()
    finally:
        con.close()
    if not row:
        return {"person_id": person_id, "questionnaire": {}, "revision": 0,
                "schema_version": 1, "source": "empty", "updated_at": "",
                "base_fields": {}, "exists": False}
    doc = json.loads(row["questionnaire_json"] or "{}")
    return {
        "person_id": person_id,
        "questionnaire": doc,
        "revision": int(row["revision"] or 0),
        "schema_version": int(row["version"] or 1),
        "source": row["source"],
        "updated_at": row["updated_at"] or "",
        "base_fields": flatten_document(doc),
        "exists": True,
    }


# ── write ────────────────────────────────────────────────────────────


def _archive(con: sqlite3.Connection, person_id: str, row: sqlite3.Row,
             superseded_by_source: str, write_kind: str, now: str,
             changed_paths: Optional[Sequence[str]] = None,
             removed_paths: Optional[Sequence[str]] = None,
             previous_values: Optional[Mapping[str, Any]] = None,
             previous_provenance: Optional[Mapping[str, Any]] = None) -> None:
    """Record the document as it stands BEFORE the write that replaces it.

    Inside the caller's transaction on purpose: the archive and the write it
    describes commit together or not at all, so history can never claim a
    write that did not land, nor miss one that did.

    The prior document is what recovery needs. `changed_paths` /
    `removed_paths` / `previous_values` are what make

        "which write removed parents[0].notableLifeEvents, and when?"

    a query rather than a diff hunt across archived documents.
    """
    con.execute(
        "INSERT INTO bio_builder_questionnaire_revisions "
        "(person_id, revision, questionnaire_json, source, schema_version, "
        " content_updated_at, superseded_at, superseded_by_source, write_kind, "
        " changed_paths, removed_paths, previous_values, previous_provenance) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (person_id, int(row["revision"] or 0), row["questionnaire_json"] or "{}",
         row["source"] or "unknown", int(row["version"] or 1),
         row["updated_at"] or "", now, superseded_by_source or "unknown", write_kind,
         json.dumps(sorted(changed_paths)) if changed_paths is not None else None,
         json.dumps(sorted(removed_paths)) if removed_paths is not None else None,
         json.dumps(previous_values, ensure_ascii=False) if previous_values is not None else None,
         # 0059. '{}' rather than NULL when nothing was superseded, so the
         # column means "we looked and there was none" rather than "nobody
         # ever looked" — the same distinction turn_evidence draws.
         json.dumps(previous_provenance or {}, ensure_ascii=False)),
    )


def _flatten_all(doc: Any, prefix: str = "") -> Dict[str, Any]:
    """Like flatten_document but KEEPS empty leaves. Used only to notice that
    a caller sent a blank where something is stored — never to write."""
    out: Dict[str, Any] = {}
    if isinstance(doc, Mapping):
        for k, v in doc.items():
            out.update(_flatten_all(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            out.update(_flatten_all(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = doc
    return out


def _write(
    person_id: str,
    *,
    source: str,
    write_kind: str,
    mutations: Optional[Mapping[str, Any]] = None,
    removals: Optional[Sequence[str]] = None,
    replacement: Optional[Mapping[str, Any]] = None,
    base_revision: Optional[int] = None,
    base_fields: Optional[Mapping[str, Any]] = None,
    schema_version: Optional[int] = None,
    blank_report_document: Optional[Mapping[str, Any]] = None,
    provenance: Optional[Any] = None,
    also_in_transaction: Optional[Any] = None,
) -> Dict[str, Any]:
    """`provenance` is an `answer_provenance.AnswerOrigin` or None.

    `also_in_transaction` is an optional callable `(con) -> None` run on
    THIS connection, inside THIS transaction, after the questionnaire row
    is written and before COMMIT. WO-03B accept uses it to remove the
    accepted proposal from `interview_projections` and record the review
    verdict, so the answer, its provenance, the queue and the review
    record commit together or not at all.

    Without this, accept would be two transactions on two tables, and a
    failure between them would leave either a value with no record of
    where it came from, or a proposal marked accepted whose value never
    landed. Either is a confident statement about something that is not
    there. If the callable raises, the whole write rolls back — including
    the questionnaire — and the caller sees the exception.

    It is NOT invoked on the no-op return: nothing was written, so there
    is nothing for it to be atomic with.

    None is the norm and means NO PROVENANCE ROW IS WRITTEN. The shared
    PUT has ~20 callers including two of Lori's own writers, and stamping
    that route with the operator's authority is the exact error WO-03
    exists to remove. Only a dedicated entry route constructs an origin,
    and it constructs it from the endpoint that was called rather than
    from anything the client asserted about itself.
    """
    mutations = dict(mutations or {})
    removals = list(removals or [])
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    parsed_mut = [(p, _split(p), v) for p, v in mutations.items()]
    parsed_rem = [(p, _split(p)) for p in removals]

    con = _db._connect()
    try:
        # ONE WRITE TRANSACTION AROUND COMPARE-AND-WRITE. BEGIN IMMEDIATE
        # takes the write lock BEFORE the SELECT; without it the read runs
        # in autocommit and two concurrent requests could both pass the
        # per-path comparison before either wrote, the second landing on top
        # of the first having "proved" it was safe against a row that no
        # longer existed. Same reasoning as merge_projection_fields.
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT questionnaire_json, source, version, revision, updated_at "
            "FROM bio_builder_questionnaires WHERE person_id = ?",
            (person_id,),
        ).fetchone()

        stored = json.loads(row["questionnaire_json"] or "{}") if row else {}
        stored_rev = int(row["revision"] or 0) if row else 0
        stored_schema = int(row["version"] or 1) if row else 1
        stored_leaves = flatten_document(stored)

        # ── intentional blanks, reported but NOT acted on ──────────────
        #
        # `flatten_document` drops "" / None / [] / {}, so a caller that
        # sends a whole document cannot blank a stored field — its empty
        # value means "untouched". That is the right default (it is what
        # stops a six-field form deleting five stored ones) and it has a
        # cost: an operator who clears a box and saves gets "Saved" and
        # the old value survives. Silent deletion traded for silent
        # NON-deletion, which is safer and still lies to them.
        #
        # So the blank is detected here and returned as `ignored_blank_paths`.
        # The write is unchanged; the caller now has what it needs to say
        # "you cleared Josie's occupation — delete it?" and to send a real
        # `removals` when the answer is yes. Reporting cannot delete
        # anything, which is why it can land before the UI is converted.
        ignored_blank_paths: List[str] = []
        if blank_report_document is not None:
            for p, v in _flatten_all(blank_report_document).items():
                if v in (None, "", [], {}) and p in stored_leaves:
                    ignored_blank_paths.append(p)

        # ── per-path concurrency ──────────────────────────────────────
        touched = [p for p, _, _ in parsed_mut] + [p for p, _ in parsed_rem]
        contested: List[str] = []
        if base_fields is not None:
            for p in touched:
                if stored_leaves.get(p) != base_fields.get(p):
                    contested.append(p)
        elif base_revision is not None and int(base_revision) != stored_rev:
            # Cannot prove any path is safe. Unprovable is not the same as
            # safe — merge_projection_fields, supervisor review 2026-08-17.
            contested = list(touched)
        if contested:
            con.rollback()
            raise QuestionnaireConflict(contested, stored_rev)

        # ── build the next document ───────────────────────────────────
        if replacement is not None:
            nxt: Dict[str, Any] = json.loads(json.dumps(replacement))
        else:
            nxt = json.loads(json.dumps(stored))
            for _p, parts, value in parsed_mut:
                _set(nxt, parts, value)
            # Deepest-last so that removing parents[1] cannot renumber a
            # path another removal in the same batch still refers to.
            for _p, parts in sorted(parsed_rem, key=lambda x: (-len(x[1]), x[0]), reverse=False):
                _unset(nxt, parts)

        # A WRITE THAT CHANGES NOTHING IS NOT A WRITE.
        #
        # This read `schema_version is None` until 2026-09-17, which meant the
        # early return never fired from the PUT route: merge_whole_document
        # always forwards a schema_version, because the route forwards
        # payload.version, and every client hard-codes that to 1. Found by
        # watching the first real Bio Builder save land — it changed nothing,
        # removed nothing, and still burned a revision and wrote a history row.
        #
        # That matters beyond tidiness. History exists to answer "which write
        # changed this field?", and a log where most entries changed nothing
        # makes that question harder to answer, not easier. Revision numbers
        # inflating on every idle save would also make a stale-client check
        # fire on clients that are not actually stale.
        #
        # An unchanged schema_version is not a change either, so compare it
        # rather than merely noting it was supplied.
        schema_unchanged = (schema_version is None or int(schema_version) == stored_schema)
        if row is not None and nxt == stored and schema_unchanged:
            con.rollback()
            return {"person_id": person_id, "questionnaire": stored,
                    "revision": stored_rev, "write_applied": False,
                    "conflict": False, "conflicting_paths": [],
                    "ignored_blank_paths": sorted(ignored_blank_paths)}

        next_rev = stored_rev + 1

        # ── provenance, in this transaction ───────────────────────────
        #
        # After the no-op return above, so an unchanged save never
        # restamps an answer as freshly entered — the same reasoning that
        # keeps it from burning a revision. Before `_archive`, because the
        # archive row carries the provenance this write supersedes and the
        # two must describe the same moment.
        #
        # Provenance that can outlive the value it describes is worse than
        # none: it is a confident statement about something that is not
        # there. Hence inside the transaction, never in the router after.
        prov_superseded: Dict[str, Any] = {}
        if provenance is not None and replacement is None:
            from .answer_provenance import record_provenance as _record_prov
            next_leaves_for_prov = flatten_document(nxt)
            prov_changed = sorted(
                {p for p, _, _ in parsed_mut
                 if stored_leaves.get(p) != next_leaves_for_prov.get(p)}
            )
            _keys, prov_superseded = _record_prov(
                con, person_id, nxt, prov_changed, provenance,
                now=now, revision=next_rev,
            )

        # A DELETED ANSWER TAKES ITS PROVENANCE WITH IT. Resolved against
        # the STORED document, because the entry is gone from `nxt` and an
        # id cannot be looked up in a document that no longer contains it.
        if parsed_rem:
            from .answer_provenance import identify_path as _ident_prov
            next_leaves_for_del = flatten_document(nxt)
            for _p in stored_leaves:
                if _p in next_leaves_for_del:
                    continue
                _ident = _ident_prov(stored, _p)
                if _ident is None:
                    continue
                con.execute(
                    "DELETE FROM bio_builder_answer_provenance "
                    "WHERE person_id=? AND section=? AND entry_id=? AND field=?",
                    (person_id, _ident[0], _ident[1], _ident[2]),
                )

        if row is not None:
            if replacement is not None:
                # "all of it" — the prior document above is the answer.
                _archive(con, person_id, row, source, write_kind, now)
            else:
                next_leaves = flatten_document(nxt)
                touched_paths = sorted(
                    {p for p, _, _ in parsed_mut if stored_leaves.get(p) != next_leaves.get(p)}
                )
                gone_paths = sorted(
                    {p for p in stored_leaves if p not in next_leaves}
                )
                _archive(con, person_id, row, source, write_kind, now,
                         changed_paths=touched_paths,
                         removed_paths=gone_paths,
                         previous_values={p: stored_leaves[p]
                                          for p in set(touched_paths) | set(gone_paths)
                                          if p in stored_leaves},
                         previous_provenance=prov_superseded)

        payload = json.dumps(nxt, ensure_ascii=False)
        next_schema = stored_schema if schema_version is None else int(schema_version)
        con.execute(
            "INSERT INTO bio_builder_questionnaires "
            "(person_id, questionnaire_json, source, version, revision, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(person_id) DO UPDATE SET "
            "  questionnaire_json = excluded.questionnaire_json, "
            "  source = excluded.source, "
            "  version = excluded.version, "
            "  revision = excluded.revision, "
            "  updated_at = excluded.updated_at",
            (person_id, payload, source, next_schema, next_rev, now),
        )
        if also_in_transaction is not None:
            also_in_transaction(con)
        con.execute("COMMIT")
        return {"person_id": person_id, "questionnaire": nxt, "revision": next_rev,
                "schema_version": next_schema, "updated_at": now,
                "write_applied": True, "conflict": False, "conflicting_paths": [],
                "write_kind": write_kind, "ignored_blank_paths": sorted(ignored_blank_paths)}
    except QuestionnaireConflict:
        raise
    except Exception:
        try:
            con.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        con.close()


def merge_questionnaire(
    person_id: str,
    mutations: Optional[Mapping[str, Any]] = None,
    removals: Optional[Sequence[str]] = None,
    *,
    source: str = "questionnaire_merge",
    base_revision: Optional[int] = None,
    base_fields: Optional[Mapping[str, Any]] = None,
    provenance: Optional[Any] = None,
    also_in_transaction: Optional[Any] = None,
) -> Dict[str, Any]:
    """Ordinary update. Cannot delete anything `removals` does not name."""
    return _write(person_id, source=source, write_kind=WRITE_MERGE,
                  mutations=mutations, removals=removals,
                  base_revision=base_revision, base_fields=base_fields,
                  provenance=provenance,
                  also_in_transaction=also_in_transaction)


def merge_whole_document(
    person_id: str,
    document: Mapping[str, Any],
    *,
    source: str = "legacy_put",
    base_revision: Optional[int] = None,
    base_fields: Optional[Mapping[str, Any]] = None,
    schema_version: Optional[int] = None,
    provenance: Optional[Any] = None,
) -> Dict[str, Any]:
    """Compatibility path for callers that still send a whole document.

    THE POINT OF THIS FUNCTION: it flattens the incoming document to its
    populated leaves and applies them as mutations with NO removals. A key
    the caller omitted is therefore untouched rather than deleted, which
    makes every existing whole-document PUT non-destructive WITHOUT any
    client change. That is the minimum safe subset.

    It reports, in `ignored_blank_paths`, every path where the caller sent an
    empty value over something stored. It does not act on them. That turns
    "the operator cleared a field and nothing happened, silently" into
    something the UI can ask about.

    What it deliberately cannot do: express a deletion. A client that
    genuinely needs to remove an entry must call `merge_questionnaire` with
    `removals`, or `replace_questionnaire` if it truly owns the whole
    document. Until a given client is converted, removing something through
    it will appear not to take effect — a visible, recoverable failure,
    which is the correct trade against an invisible destructive one.
    """
    return _write(person_id, source=source, write_kind=WRITE_LEGACY,
                  mutations=flatten_document(document),
                  base_revision=base_revision, base_fields=base_fields,
                  schema_version=schema_version,
                  blank_report_document=document,
                  provenance=provenance)


def replace_questionnaire(
    person_id: str,
    document: Mapping[str, Any],
    *,
    source: str,
    base_revision: Optional[int] = None,
) -> Dict[str, Any]:
    """Explicit whole-document replacement. Archives first.

    For operations that genuinely own the whole envelope — a snapshot
    restore, an authorised import. NOT for ordinary saves, and not
    reachable from the ordinary PUT: a caller has to name this function.
    """
    return _write(person_id, source=source, write_kind=WRITE_REPLACE,
                  replacement=document, base_revision=base_revision)


def reset_questionnaire(person_id: str, *, source: str,
                        base_revision: Optional[int] = None) -> Dict[str, Any]:
    """Deliberate emptying. Archives first, and is recorded as a reset so
    history can later answer whether an empty record was intended."""
    return _write(person_id, source=source, write_kind=WRITE_RESET,
                  replacement={}, base_revision=base_revision)
