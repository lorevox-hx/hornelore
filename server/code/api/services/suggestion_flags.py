"""Suggestions that must not be accepted unchanged. WO-04.

The acceptance criterion for the whole work order:

    expanding the biography must not make an old extraction mistake
    easier to turn into a permanent family record.

Adding a questionnaire section flips WO-03B's destination guard for
every queued proposal aimed at it. Kent's
`military.branch = "Nike Ajax Nike Hercules missile site"` is "cannot be
added" today and becomes one click from his archive the moment
`military` exists. This module is what stops that, and it stops it at
the WRITE, not in the interface.

TWO LAYERS, because either alone fails open
--------------------------------------------

1. A FLAG, recorded before the sections exist. `queued_before_home` is
   applied to every queued proposal whose destination did not exist at
   the time — a fact about timing, asserting nothing about content.

2. A STRUCTURAL RULE that needs no flag. A proposal that carries no
   `destination_undefined` field at all is pre-WO-03B, so nothing is
   known about whether its destination was checked; if it targets a
   section this work created, acceptance is refused regardless of
   flagging. Layer 1 can be incomplete — a row missed by the classifier,
   a row queued between two deploys — and layer 2 still holds.

   This is deliberately NARROW. It refuses only legacy rows aimed at the
   new sections, so `education.schooling`, which was always acceptable,
   stays acceptable. Widening it to all legacy rows would be a
   regression dressed as caution.

WHAT A FLAG DOES NOT AUTHORISE
------------------------------

Nothing here declines, accepts, migrates, rewrites or deletes a
suggestion. A flag makes acceptance require an explicit human
correction; it never resolves anything on its own.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

from .suggestion_review import split_destination, value_hash

__all__ = [
    "REASONS", "SECTIONS_ADDED_BY_WO04", "SuggestionFlagged",
    "flag_for", "requires_correction", "record_flag", "mark_disposed",
    "flags_for_person",
]

REASONS = (
    "queued_before_home",
    "value_not_a_field",
    "model_uncertainty",
    "misclassified_section",
)

# The sections WO-04 creates. A proposal aimed at one of these that
# predates the server-owned queue could not have had its destination
# checked when it was queued, because the destination did not exist.
#
# This tuple is the structural guard's whole basis, so it is defined
# once here and asserted against the questionnaire by a test: every id
# must BE a section (after WO-04's schema commit), and every one must
# have been absent before it.
SECTIONS_ADDED_BY_WO04 = frozenset({"military", "residence", "travel", "faith"})


class SuggestionFlagged(Exception):
    """Acceptance refused: this proposal is flagged and the request did
    not correct it.

    Carries everything the review surface needs to explain the refusal
    and offer the two real options — correct the value, or send it to a
    different destination.
    """

    def __init__(self, reason: str, detail: str, proposed_value: Any = None,
                 source_note: str = "", field_path: str = ""):
        self.reason = reason
        self.detail = detail
        self.proposed_value = proposed_value
        self.source_note = source_note
        self.field_path = field_path
        super().__init__(detail)


# ── lookup ──────────────────────────────────────────────────────────


def flag_for(con: sqlite3.Connection, person_id: str,
             suggestion: Mapping[str, Any]) -> Optional[sqlite3.Row]:
    """The undisposed flag on this proposal, if any.

    IDENTITY, in order of strength:

      1. `suggestion_id` when the proposal has one. Unambiguous, and it
         survives the value being edited.
      2. the canonical tuple (person, section, entry, field, value_hash)
         for the 29 rows queued before ids existed.

    The fallback's known weakness: two distinct proposals of the same
    value to the same destination look identical. For a flag that is
    acceptable — both deserve the protection. It is not acceptable for
    a disposition, which is why dispositions carry the id when there is
    one.
    """
    sid = (suggestion.get("suggestion_id") or "").strip()
    if sid:
        row = con.execute(
            "SELECT * FROM suggestion_flags WHERE person_id=? AND suggestion_id=? "
            "AND disposition IS NULL", (person_id, sid),
        ).fetchone()
        if row is not None:
            return row
        # Fall through: a flag may have been recorded by canonical tuple
        # before this proposal was re-queued with an id.

    section, field, _rep = split_destination(str(suggestion.get("fieldPath") or ""))
    return con.execute(
        "SELECT * FROM suggestion_flags WHERE person_id=? AND section=? "
        "AND entry_id='' AND field=? AND value_hash=? AND disposition IS NULL",
        (person_id, section, field, value_hash(suggestion.get("value"))),
    ).fetchone()


def _is_unchecked_legacy(suggestion: Mapping[str, Any]) -> bool:
    """Was this queued before destinations were checked at all?

    `destination_undefined` is written by the WO-03B append route. Its
    ABSENCE means the proposal predates that route, so nothing is known
    about whether its destination existed. Present-and-False means the
    destination was checked and was fine.
    """
    return "destination_undefined" not in suggestion


def requires_correction(con: sqlite3.Connection, person_id: str,
                        suggestion: Mapping[str, Any]) -> Optional[SuggestionFlagged]:
    """Must this proposal be corrected before it can be accepted?

    Returns the exception to raise, or None. Called from inside the
    accept transaction — see the module docstring for why the interface
    hiding a button is not sufficient.
    """
    section, field, _rep = split_destination(str(suggestion.get("fieldPath") or ""))

    # Layer 2 first: structural, needs no flag, cannot be missed by a
    # classifier that did not run.
    if _is_unchecked_legacy(suggestion) and section in SECTIONS_ADDED_BY_WO04:
        return SuggestionFlagged(
            "queued_before_home",
            f"This was proposed before the questionnaire had a '{section}' "
            "section, so nobody ever chose this destination for it. Check the "
            "value belongs here, or send it somewhere else, before accepting.",
            proposed_value=suggestion.get("value"),
            field_path=str(suggestion.get("fieldPath") or ""),
        )

    # Layer 1: a recorded flag.
    row = flag_for(con, person_id, suggestion)
    if row is None:
        return None

    detail = {
        "queued_before_home":
            "This was proposed before the questionnaire had a place for it. "
            "Check it belongs here before accepting.",
        "value_not_a_field":
            f"The proposed value does not look like a '{field}'. "
            "Correct it, or send it to a destination that fits.",
        "model_uncertainty":
            "This value is the model describing its own uncertainty rather "
            "than an answer. Enter what is actually known, or decline it.",
        "misclassified_section":
            f"This looks like the right kind of fact in the wrong place — "
            f"'{section}' may not be where it belongs.",
    }.get(row["reason"], "This proposal was flagged for review.")

    return SuggestionFlagged(
        row["reason"], detail,
        proposed_value=row["proposed_value"],
        source_note=row["source_note"] or "",
        field_path=row["field_path"] or "",
    )


# ── writes ──────────────────────────────────────────────────────────


def record_flag(con: sqlite3.Connection, person_id: str,
                suggestion: Mapping[str, Any], reason: str, *,
                source_note: str = "", flagged_by: str = "") -> None:
    """Record one flag. Idempotent on the canonical tuple.

    Does NOT commit — the caller owns the transaction, so a classifier
    run is all-or-nothing.
    """
    if reason not in REASONS:
        raise ValueError(f"unknown reason {reason!r}")
    section, field, _rep = split_destination(str(suggestion.get("fieldPath") or ""))
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    con.execute(
        "INSERT INTO suggestion_flags "
        "(person_id, section, entry_id, field, value_hash, suggestion_id, "
        " field_path, proposed_value, reason, source_note, flagged_at, flagged_by) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(person_id, section, entry_id, field, value_hash) DO UPDATE SET "
        "  reason=excluded.reason, source_note=excluded.source_note, "
        "  suggestion_id=COALESCE(suggestion_flags.suggestion_id, excluded.suggestion_id), "
        "  flagged_at=excluded.flagged_at, flagged_by=excluded.flagged_by",
        (person_id, section, "", field, value_hash(suggestion.get("value")),
         (suggestion.get("suggestion_id") or None),
         str(suggestion.get("fieldPath") or ""),
         "" if suggestion.get("value") is None else str(suggestion.get("value")),
         reason, source_note, now, flagged_by),
    )


def mark_disposed(con: sqlite3.Connection, person_id: str,
                  suggestion: Mapping[str, Any], disposition: str) -> None:
    """A person acted on a flagged proposal. Same transaction as the act."""
    if disposition not in ("corrected", "re-homed", "declined"):
        raise ValueError(f"unknown disposition {disposition!r}")
    section, field, _rep = split_destination(str(suggestion.get("fieldPath") or ""))
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    con.execute(
        "UPDATE suggestion_flags SET disposition=?, disposed_at=? "
        "WHERE person_id=? AND section=? AND entry_id='' AND field=? AND value_hash=?",
        (disposition, now, person_id, section, field,
         value_hash(suggestion.get("value"))),
    )


def flags_for_person(person_id: str) -> Dict[str, Dict[str, Any]]:
    """Undisposed flags, keyed by suggestion_id when present else by the
    canonical tuple. Read-only; used by the review surface."""
    from .. import db as _db
    con = _db._connect()
    try:
        rows = con.execute(
            "SELECT * FROM suggestion_flags WHERE person_id=? AND disposition IS NULL",
            (person_id,),
        ).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        con.close()
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        key = r["suggestion_id"] or f"{r['section']}|{r['entry_id']}|{r['field']}|{r['value_hash']}"
        out[key] = {
            "reason": r["reason"], "source_note": r["source_note"] or "",
            "field_path": r["field_path"], "proposed_value": r["proposed_value"],
        }
    return out
