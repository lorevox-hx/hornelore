"""What a person decides about a proposal. WO-03B steps 1–2.

Three operations, all server-side, all acting on a proposal identified
by its server-minted `suggestion_id` — never on a field path and a value
the client asserts were offered (ruling C3).

    decline(person_id, suggestion_id)
    accept(person_id, suggestion_id, entry_id=None)
    is_suppressed(con, person_id, field_path, value)   -- used by propose

THE ONE THING ACCEPT MUST NEVER DO is disguise Lori's proposal as
something a person originally entered. The answer it writes carries
`origin='ai_suggested'`, `proposed_by='lori'`, `confirmed_via='acceptance'`
and stays that way forever. An operator who wants a DIFFERENT value is
not accepting — that is an ordinary entry through the WO-03A route, and
it correctly records a human entry.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .. import db as _db
from . import questionnaire_persistence as _qp
from .answer_provenance import (
    AnswerOrigin, ORIGIN_SUGGESTED, ORIGIN_OPERATOR, EVIDENCE_ABSENT,
    ENTRY_ID_KEY,
)

__all__ = [
    "canonical_value", "value_hash", "split_destination",
    "SuggestionNotFound", "SuggestionUnresolved", "SuggestionConflict",
    "find_suggestion", "decline", "accept", "is_suppressed", "note_reproposal",
]

# The eight repeatable questionnaire sections. Mirrors the router's list;
# a test asserts both against the questionnaire's own definitions.
REPEATABLE_SECTIONS = frozenset({
    "parents", "grandparents", "siblings", "children", "spouse",
    "marriage", "familyTraditions", "pets",
    # WO-04. A life has more than one posting, more than one home and
    # more than one trip; each needs its own dates and its own memories.
    "military", "residence", "travel",
})

NEW_ENTRY = "__new__"


# ── canonical form ──────────────────────────────────────────────────

_WS = re.compile(r"\s+")


def canonical_value(v: Any) -> str:
    """ONE function, used by the review write and the re-proposal check,
    so the two cannot drift.

    NFC, trimmed, internal whitespace collapsed to one space, casefolded.
    So "Minot , ND " and "minot , nd" hash alike.

    Deliberately NOT normalising punctuation or word order: "Minot, ND"
    and "ND, Minot" are different claims, and a person who declined one
    has not declined the other.
    """
    s = "" if v is None else str(v)
    s = unicodedata.normalize("NFC", s)
    s = _WS.sub(" ", s.strip())
    return s.casefold()


def value_hash(v: Any) -> str:
    return hashlib.sha256(canonical_value(v).encode("utf-8")).hexdigest()


def split_destination(field_path: str) -> Tuple[str, str, bool]:
    """'personal.placeOfBirth'   -> ('personal', 'placeOfBirth', False)
       'parents.occupation'      -> ('parents',  'occupation',   True)
       'parents[0].occupation'   -> ('parents',  'occupation',   True)

    The third value is "unresolved": a repeatable section with no
    person-chosen entry. An ordinal in the path is NOT a resolution —
    after an insertion or reorder it names a different relative — so it
    is stripped rather than honoured (ruling C4)."""
    parts = (field_path or "").split(".", 1)
    head = parts[0]
    section = head.split("[")[0]
    field = parts[1] if len(parts) > 1 else ""
    return section, field, section in REPEATABLE_SECTIONS


# ── errors ──────────────────────────────────────────────────────────


class SuggestionNotFound(Exception):
    pass


class SuggestionUnresolved(Exception):
    """A repeatable destination with no entry chosen. Resolve at review."""


def SuggestionFlagged_unchanged(blocker):
    """A correction identical to the proposal is not a correction.

    Re-raises the original block with a message that names the specific
    evasion, rather than letting `corrected_value == proposed` satisfy
    the requirement by technicality.

    Raised only where a CORRECTION was required. Where an
    acknowledgement would have done, resubmitting the same value is not
    an evasion — it is the acknowledgement, spelled the long way — and
    the accept path treats it as one.
    """
    from .suggestion_flags import SuggestionFlagged
    return SuggestionFlagged(
        blocker.reason,
        "The corrected value is the same as what was proposed, so nothing "
        "was corrected. " + blocker.detail,
        proposed_value=blocker.proposed_value,
        source_note=blocker.source_note,
        field_path=blocker.field_path,
        requirement=blocker.requirement,
    )


class DestinationUndefined(Exception):
    """The questionnaire does not define this field, so an accepted value
    would be stored where no form can render it.

    Filed from BUG-SUGGESTION-ACCEPTED-INTO-AN-INVISIBLE-FIELD-01: on
    2026-09-20 a proposal for `personal.notes` was accepted, the whole
    transaction succeeded, and the value was invisible afterwards —
    Personal Information defines seven fields and `notes` is not one.
    A person had approved information they could not then see or correct.

    Measured on the live database the same day: 20 of 30 queued
    suggestions point at undefined destinations — every `military.*`,
    `residence.*`, `travel.*` and `family.marriage*` among them, because
    `extract.py`'s EXTRACTABLE_FIELDS has drifted from the questionnaire.
    """

    def __init__(self, section: str, field: str, detail: str = ""):
        self.section, self.field, self.detail = section, field, detail
        super().__init__(detail or f"{section}.{field} is not a questionnaire field")


class SuggestionConflict(Exception):
    """The destination holds a DIFFERENT value than the proposal. Accepting
    would silently discard a newer answer — possibly one a person typed.
    Carries both so the person can decide."""

    def __init__(self, path: str, stored: Any, proposed: Any):
        self.path, self.stored, self.proposed = path, stored, proposed
        super().__init__(f"{path}: stored={stored!r} proposed={proposed!r}")


# ── lookup ──────────────────────────────────────────────────────────


def _load_queue(con: sqlite3.Connection, person_id: str):
    row = con.execute(
        "SELECT projection_json, version FROM interview_projections WHERE person_id=?",
        (person_id,),
    ).fetchone()
    env = json.loads(row["projection_json"] or "{}") if row else {}
    return env, list(env.get("pendingSuggestions") or []), (int(row["version"]) if row else 0)


def find_suggestion(con: sqlite3.Connection, person_id: str,
                    suggestion_id: str) -> Optional[Dict[str, Any]]:
    _env, pending, _v = _load_queue(con, person_id)
    for s in pending:
        if isinstance(s, dict) and s.get("suggestion_id") == suggestion_id:
            return s
    return None


def _write_queue_without(con: sqlite3.Connection, person_id: str,
                         suggestion_id: str, source: str, now: str) -> None:
    """Rewrite the queue minus one entry, on the caller's connection and
    inside the caller's transaction. Touches `pendingSuggestions` only."""
    env, pending, version = _load_queue(con, person_id)
    env["pendingSuggestions"] = [
        s for s in pending
        if not (isinstance(s, dict) and s.get("suggestion_id") == suggestion_id)
    ]
    con.execute(
        "UPDATE interview_projections SET projection_json=?, version=?, "
        "source=?, updated_at=? WHERE person_id=?",
        (json.dumps(env, ensure_ascii=False), version + 1, source, now, person_id),
    )


def _insert_review(con: sqlite3.Connection, person_id: str, s: Mapping[str, Any],
                   verdict: str, entry_id: str, now: str, reviewed_by: str,
                   corrected_value: Optional[Any] = None,
                   correction_reason: str = "",
                   accept_mode: Optional[str] = None) -> None:
    section, field, unresolved = split_destination(str(s.get("fieldPath") or ""))
    con.execute(
        "INSERT INTO suggestion_reviews "
        "(person_id, section, entry_id, field, value_hash, verdict, "
        " suggestion_id, field_path, proposed_value, proposed_at, "
        " source_turn_id, turn_evidence, repeats, destination_unresolved, "
        " reviewed_at, reviewed_by, corrected_value, correction_reason, "
        " accept_mode) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(person_id, section, entry_id, field, value_hash) DO UPDATE SET "
        "  verdict=excluded.verdict, "
        # PREFER the newer id, but never replace a known one with NULL.
        # The row's key is the canonical tuple, so a second proposal of
        # the same value at the same destination lands here — and the
        # newest review is what the row should name. But
        # `projection_writer` still appends entries with no id at all
        # (:207-215), so `excluded.suggestion_id` can be NULL, and a
        # bare `=excluded` would erase the identity of the proposal that
        # was actually reviewed. 0061 got this right with COALESCE on
        # the flags side; this is the same asymmetry, fixed.
        "  suggestion_id=COALESCE(excluded.suggestion_id, suggestion_reviews.suggestion_id), "
        "  proposed_at=excluded.proposed_at, source_turn_id=excluded.source_turn_id, "
        "  turn_evidence=excluded.turn_evidence, repeats=excluded.repeats, "
        "  destination_unresolved=excluded.destination_unresolved, "
        "  reviewed_at=excluded.reviewed_at, reviewed_by=excluded.reviewed_by, "
        "  corrected_value=excluded.corrected_value, "
        "  correction_reason=excluded.correction_reason, "
        "  accept_mode=excluded.accept_mode",
        (person_id, section, entry_id, field, value_hash(s.get("value")), verdict,
         s.get("suggestion_id"), str(s.get("fieldPath") or ""),
         "" if s.get("value") is None else str(s.get("value")),
         s.get("ts"), s.get("source_turn_id"),
         s.get("turn_evidence") or EVIDENCE_ABSENT, int(s.get("repeats") or 1),
         1 if (unresolved and not entry_id) else 0, now, reviewed_by or "",
         # The ORIGINAL proposal stays in `proposed_value` above; this is
         # what the person put in its place. Losing the original would
         # erase the fact that a machine proposed something else and a
         # person fixed it.
         (None if corrected_value is None else str(corrected_value)),
         correction_reason or None,
         # HOW the acceptance was arrived at — 0062. NULL on a decline,
         # and on every row written before the column existed, which is
         # the truthful answer for them.
         accept_mode),
    )


# ── decline ─────────────────────────────────────────────────────────


def decline(person_id: str, suggestion_id: str, *, reviewed_by: str = "",
            source: str = "suggestion_decline") -> Dict[str, Any]:
    """Record the refusal, THEN remove from the queue. One transaction.

    Requirement 2 of the ruling. A decline that vanished from the queue
    without a record would re-offer itself on the next extraction.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    con = _db._connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        s = find_suggestion(con, person_id, suggestion_id)
        if s is None:
            con.rollback()
            raise SuggestionNotFound(suggestion_id)
        _section, _field, unresolved = split_destination(str(s.get("fieldPath") or ""))
        # An unresolved decline is keyed on entry_id='' and marked so; it
        # suppresses only other UNRESOLVED proposals of the same value.
        _insert_review(con, person_id, s, "declined", "", now, reviewed_by)
        _write_queue_without(con, person_id, suggestion_id, source, now)
        con.commit()
        return {"person_id": person_id, "suggestion_id": suggestion_id,
                "verdict": "declined", "reviewed_at": now,
                "destination_unresolved": bool(unresolved)}
    except Exception:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


# ── accept ──────────────────────────────────────────────────────────


def _resolve_path(stored_doc: Mapping[str, Any], section: str, field: str,
                  unresolved: bool, entry_id: Optional[str]) -> Tuple[str, str, Optional[str]]:
    """Turn a proposal's destination into the flattened path `_write` uses.

    Returns (path, entry_id_for_provenance, new_entry_id_path_or_None).

    For a repeatable section the person must have named an entry by its
    `_entryId` (or NEW_ENTRY). The entry's CURRENT index is looked up in
    the stored document at accept time — the ordinal is derived from the
    id, never the other way round.
    """
    if not unresolved:
        return f"{section}.{field}", "", None
    if not entry_id:
        raise SuggestionUnresolved(section)
    entries = stored_doc.get(section)
    entries = entries if isinstance(entries, list) else []
    if entry_id == NEW_ENTRY:
        import uuid
        new_id = "e_" + uuid.uuid4().hex[:12]
        idx = len(entries)
        return f"{section}[{idx}].{field}", new_id, f"{section}[{idx}].{ENTRY_ID_KEY}"
    for i, e in enumerate(entries):
        if isinstance(e, Mapping) and e.get(ENTRY_ID_KEY) == entry_id:
            return f"{section}[{i}].{field}", entry_id, None
    raise SuggestionNotFound(f"no entry {entry_id!r} in {section}")


def accept(person_id: str, suggestion_id: str, *, entry_id: Optional[str] = None,
           reviewed_by: str = "", source: str = "suggestion_accept",
           corrected_value: Optional[Any] = None,
           correction_reason: str = "",
           acknowledge_legacy: bool = False) -> Dict[str, Any]:
    """Write the proposed value as an accepted AI suggestion. One transaction
    across the questionnaire, its provenance, the queue and the review record.

    REFUSES rather than overwrites when the destination already holds a
    different non-empty value (ruling C3). The response carries both
    values; the person decides. Accepting a machine's date over an
    operator's date by one click labelled "Accept" is exactly the silent
    overwrite this refuses.

    A destination that is empty, or already equal to the proposal, is
    written. The second case is a real acceptance of a value that
    happened to be entered independently — it gains the confirmation and
    keeps `ai_suggested`, per 0059.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # Read the proposal and the stored document first, on a short-lived
    # connection. The write itself goes through `_write`, which opens its
    # own BEGIN IMMEDIATE and re-reads under the lock; the hook below runs
    # inside it. So the ordering is: read, decide, then one transaction.
    con = _db._connect()
    try:
        s = find_suggestion(con, person_id, suggestion_id)
        if s is None:
            raise SuggestionNotFound(suggestion_id)
        qrow = con.execute(
            "SELECT questionnaire_json FROM bio_builder_questionnaires WHERE person_id=?",
            (person_id,),
        ).fetchone()
        stored_doc = json.loads(qrow["questionnaire_json"] or "{}") if qrow else {}
    finally:
        con.close()

    section, field, unresolved = split_destination(str(s.get("fieldPath") or ""))

    # ── the destination must be a field the form can render ──────────
    #
    # Checked HERE, at acceptance, and not merely at proposal time. The
    # schema is a file that can change while a suggestion sits in the
    # queue, so a flag recorded when it was proposed is a statement about
    # the past. The ruling was explicit: validate again, against the same
    # authoritative schema.
    #
    # A SchemaUnavailable is NOT caught. If the schema cannot be read we
    # refuse to accept anything, because the alternative is writing
    # another value nobody can see.
    from . import questionnaire_schema as _qs
    if not _qs.is_defined(section, field):
        raise DestinationUndefined(
            section, field,
            f"The questionnaire has no '{field}' field in '{section}'. "
            "Accepting would store the value where no form can show it.")
    # And the section's shape must agree with how we are about to write
    # it: a flat section addressed as repeatable (or the reverse) would
    # produce a list where the form expects an object.
    if _qs.is_repeatable(section) != unresolved:
        raise DestinationUndefined(
            section, field,
            f"'{section}' is "
            + ("repeatable" if _qs.is_repeatable(section) else "not repeatable")
            + " in the questionnaire, but this proposal is shaped the other way.")

    path, prov_entry_id, new_id_path = _resolve_path(stored_doc, section, field, unresolved, entry_id)

    # ── a proposal that needs a deliberate act cannot be accepted by
    #    an ordinary click ────────────────────────────────────────────
    #
    # WO-04 requirement 3, widened. Two levels, because "this is old"
    # and "this value looks wrong" are different claims:
    #
    #   CORRECT      `military.branch = "Nike Ajax Nike Hercules missile
    #                site"`. A confirmation dialog is not enough — the
    #                person supplies the value they want, or sends it to
    #                a destination that fits. Clicking through a warning
    #                must not convert a known mismatch into a
    #                biographical fact.
    #
    #   ACKNOWLEDGE  `education.schooling = "high school"`, and the ten
    #                other legacy rows at destinations that existed all
    #                along. The value may be perfectly good, so
    #                demanding a rewrite would be caution that damages
    #                the record. What is demanded is that a person say
    #                they read it: `acknowledge_legacy`. A correction
    #                also satisfies it — a stronger act than the one
    #                asked for.
    #
    # `acknowledge_legacy` must never satisfy a CORRECT requirement.
    # That is the whole distinction, and it is enforced here and again
    # inside the transaction — a requirement can appear between the two
    # moments, when a classifier runs or another operator reviews the
    # same queue.
    from . import suggestion_flags as _flags
    corrected = corrected_value is not None and str(corrected_value).strip() != ""
    con = _db._connect()
    try:
        blocker = _flags.requires_review(con, person_id, s)
    finally:
        con.close()
    if blocker is not None:
        _satisfied = corrected or (
            blocker.requirement == _flags.REQUIRE_ACKNOWLEDGE and acknowledge_legacy)
        if not _satisfied:
            raise blocker
        # A "correction" that changes nothing is a confirmation wearing
        # a correction's clothes — where a correction was what was
        # required. Where an acknowledgement would have done, the same
        # value coming back IS the acknowledgement, so it stands, and is
        # recorded as one rather than as a correction of nothing.
        if corrected and canonical_value(corrected_value) == canonical_value(s.get("value")):
            if blocker.requirement == _flags.REQUIRE_CORRECT:
                raise SuggestionFlagged_unchanged(blocker)
            corrected = False
            acknowledge_legacy = True

    # How this acceptance was arrived at, for migration 0062. Derived
    # once, here, so the record and the write agree about what happened.
    if corrected:
        accept_mode = "corrected"
    elif blocker is not None:
        accept_mode = "acknowledged_legacy"
    else:
        accept_mode = "direct"

    proposed = corrected_value if corrected else s.get("value")

    # Staleness / conflict, TWICE, on purpose.
    #
    # Here, outside the lock, so the person gets a 409 that carries both
    # values and can decide. And again inside `_write` via `base_fields`,
    # under BEGIN IMMEDIATE, so a value that lands between this read and
    # the write is contested rather than overwritten. The first is for
    # the person; the second is for the race. Neither alone is enough.
    stored_leaves = _qp.flatten_document(stored_doc)
    current = stored_leaves.get(path)
    if current not in (None, "") and current != proposed:
        raise SuggestionConflict(path, current, proposed)

    # WHO AUTHORED THE VALUE THAT LANDS.
    #
    # An ordinary acceptance is Lori's value with a person's agreement:
    # ai_suggested / confirmed_via='acceptance'. Permanent, per 0059 —
    # "Lori proposed it and a person agreed" is a weaker fact than "a
    # person said it", and rewriting it would launder the first into the
    # second.
    #
    # A CORRECTED acceptance is different in kind. The person rejected
    # Lori's value and typed their own, so the answer is theirs:
    # operator_direct, with `proposed_by='lori'` recording that Lori
    # prompted it and NO `confirmed_via`, because nothing of Lori's was
    # confirmed. This matches what the ordinary form already does when
    # someone edits an accepted value by hand (observed on the ZZ
    # walkthrough: origin flipped to operator_direct, correctly).
    if corrected:
        origin = AnswerOrigin(
            ORIGIN_OPERATOR,
            actor_id=reviewed_by or "",
            proposed_by="lori",
            sections=[section],
        )
    else:
        origin = AnswerOrigin(
            ORIGIN_SUGGESTED,
            actor_id=reviewed_by or "",
            proposed_by="lori",
            confirmed_via="acceptance",
            confirmed_at=now,
            sections=[section],
        )

    mutations: Dict[str, Any] = {path: proposed}
    base_fields: Dict[str, Any] = {path: current}
    if new_id_path is not None:
        # A person chose "add as a new entry", so the entry id is a
        # person's decision, not the model's. It travels with the value,
        # and is bookkeeping — identify_path skips it, so it gets no
        # provenance row of its own.
        mutations[new_id_path] = prov_entry_id
        base_fields[new_id_path] = None

    # The fingerprint as it stood when we decided the destination was
    # valid. Re-checked inside the transaction below.
    schema_at_decision = _qs.schema_fingerprint()

    def _also(con2: sqlite3.Connection) -> None:
        # THE FLAG CHECK, INSIDE THE TRANSACTION.
        #
        # Not a duplicate of the pre-check above: a flag can be recorded
        # between that read and this write — by the classifier, or by
        # another operator reviewing the same queue. Raising here rolls
        # back the questionnaire, its provenance, the queue rewrite and
        # the review record together, so a flagged value cannot land
        # through a race.
        #
        # This is the layer the UI cannot bypass. Hiding the Accept
        # button is presentation; this is the write.
        _blocker2 = _flags.requires_review(con2, person_id, s)
        if _blocker2 is not None:
            # `and acknowledge_legacy` is qualified by the TIER on
            # purpose, and the qualification is the whole point: an
            # acknowledgement collected before this write satisfies only
            # the acknowledge tier. If a correction requirement was
            # recorded in between — by the classifier, or by another
            # operator reviewing the same queue — a checkbox ticked
            # before it existed does not clear it. The person agreed to
            # read something old; they did not agree to a value someone
            # has since doubted.
            #
            # Mutation-checked: dropping the tier test here passes every
            # test that goes through the pre-check, and fails only the
            # one where the requirement appears mid-flight. That test is
            # the only thing holding this line up.
            if not (corrected or (_blocker2.requirement == _flags.REQUIRE_ACKNOWLEDGE
                                  and acknowledge_legacy)):
                raise _blocker2
            if corrected:
                # No-op when the requirement was structural — there is
                # no row to dispose, and that is correct: a structural
                # tier is not cleared by acting once.
                _flags.mark_disposed(con2, person_id, s, "corrected")

        # SECOND VALIDATION, INSIDE THE TRANSACTION.
        #
        # Not belt-and-braces: `load_schema` re-reads on mtime change, so
        # the questionnaire can be edited between the check above and
        # this write. Raising here rolls back the questionnaire row, its
        # provenance, the queue rewrite and the review record together —
        # which is what makes "422 without changing anything" true rather
        # than merely intended.
        if _qs.schema_fingerprint() != schema_at_decision:
            if not _qs.is_defined(section, field):
                raise DestinationUndefined(
                    section, field,
                    "The questionnaire changed while this was being accepted, "
                    f"and '{section}.{field}' is no longer a field. Nothing "
                    "was written; review the suggestion again.")
        _insert_review(con2, person_id, s, "accepted", prov_entry_id, now, reviewed_by,
                       corrected_value=(corrected_value if corrected else None),
                       correction_reason=correction_reason,
                       accept_mode=accept_mode)
        _write_queue_without(con2, person_id, suggestion_id, source, now)

    try:
        res = _qp.merge_questionnaire(
            person_id, mutations, [], source=source, provenance=origin,
            base_fields=base_fields, also_in_transaction=_also,
        )
    except _qp.QuestionnaireConflict as qc:
        # The race case: something wrote the destination between our read
        # and the locked write. Re-read and report both values.
        con = _db._connect()
        try:
            qrow = con.execute(
                "SELECT questionnaire_json FROM bio_builder_questionnaires WHERE person_id=?",
                (person_id,)).fetchone()
        finally:
            con.close()
        latest = _qp.flatten_document(json.loads(qrow["questionnaire_json"] or "{}") if qrow else {})
        raise SuggestionConflict(path, latest.get(path), proposed) from qc
    res["suggestion_id"] = suggestion_id
    res["path"] = path
    res["verdict"] = "accepted"
    res["accept_mode"] = accept_mode
    res["entry_id"] = prov_entry_id
    return res


# ── propose-time suppression ────────────────────────────────────────


def is_suppressed(con: sqlite3.Connection, person_id: str, field_path: str,
                  value: Any) -> Optional[sqlite3.Row]:
    """Was this exact (destination, value) already declined?

    Requirement 3. Matches on the canonical hash. For an unresolved
    repeatable destination the key is entry_id='' with the unresolved
    flag, so it never suppresses the same value proposed for a NAMED
    entry — those are different claims about different people.

    Returns the review row when suppressed, else None. An accepted row
    does not suppress: the value is in the biography, and re-proposing it
    is harmless (and the append path's own duplicate check handles it).
    """
    section, field, unresolved = split_destination(field_path)
    return con.execute(
        "SELECT * FROM suggestion_reviews WHERE person_id=? AND section=? "
        "AND entry_id='' AND field=? AND value_hash=? AND verdict='declined' "
        "AND destination_unresolved=?",
        (person_id, section, field, value_hash(value), 1 if unresolved else 0),
    ).fetchone()


def note_reproposal(con: sqlite3.Connection, person_id: str, field_path: str,
                    value: Any, now: str) -> None:
    """A declined value was proposed again. Not queued; counted, so the
    model's persistence stays observable."""
    section, field, unresolved = split_destination(field_path)
    con.execute(
        "UPDATE suggestion_reviews SET reproposals=reproposals+1, last_reproposed_at=? "
        "WHERE person_id=? AND section=? AND entry_id='' AND field=? AND value_hash=? "
        "AND verdict='declined' AND destination_unresolved=?",
        (now, person_id, section, field, value_hash(value), 1 if unresolved else 0),
    )
