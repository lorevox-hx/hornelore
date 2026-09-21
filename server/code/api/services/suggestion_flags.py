"""Suggestions that must not be accepted without a deliberate act. WO-04.

The acceptance criterion for the whole work order:

    expanding the biography must not make an old extraction mistake
    easier to turn into a permanent family record.

Adding a questionnaire section flips WO-03B's destination guard for
every queued proposal aimed at it. Kent's
`military.branch = "Nike Ajax Nike Hercules missile site"` is "cannot be
added" today and becomes one click from his archive the moment
`military` exists. This module is what stops that, and it stops it at
the WRITE, not in the interface.

WHY THE GUARD WIDENED
---------------------

The first version of this module refused only legacy proposals aimed at
the four sections WO-04 created, and said so in a comment that called
widening it "a regression dressed as caution". Classifying the queue
proved that comment wrong. Eleven of the thirty queued proposals target
destinations that ALREADY EXISTED, so the narrow guard never saw them,
and among them:

    personal.fullName      = "kind of scared"
    personal.preferredName = "Christopher Todd Horne"
    education.schooling    = "induction physical and testing in Fargo"

`personal.fullName = "kind of scared"` was one click from becoming
Christopher's name. The destination being old is exactly why nothing
stopped it. So the guard now covers every legacy proposal.

TWO TIERS, BECAUSE "OLD" AND "WRONG" ARE DIFFERENT CLAIMS
----------------------------------------------------------

Widening must not turn into calling thirty proposals incorrect. Most of
them are fine. `education.schooling = "high school"` needs a person to
look at it, not a person to rewrite it. So a requirement has a LEVEL:

  ACKNOWLEDGE  An old proposal. Someone must say they have read it and
               they accept it as it stands. The value may be perfectly
               good; this asserts nothing about the content. Satisfied
               by an explicit acknowledgement, or by a correction.

  CORRECT      A questionable value, or a destination nobody ever chose.
               Acknowledging is NOT enough: the person supplies the
               value they want, or sends it to a destination that fits.

WHERE EACH LEVEL COMES FROM — three sources, strongest wins
------------------------------------------------------------

1. A RECORDED FLAG (`suggestion_flags`, migration 0061). Any of the four
   reasons. Always CORRECT — a flag exists because someone looked at the
   content and doubted it.

2. STRUCTURAL, legacy row aimed at a section WO-04 created. Always
   CORRECT, and needs no flag: the destination did not exist when this
   was queued, so nobody ever chose it, and there is nothing to
   acknowledge. Unchanged from the first version.

3. STRUCTURAL, legacy row anywhere else. ACKNOWLEDGE. This is the new
   tier, and it is what covers the eleven.

They are evaluated together and the STRONGEST applies. A flagged
proposal at a pre-existing destination is CORRECT, not ACKNOWLEDGE —
checking the structural tier first and returning early would have let a
recorded doubt be satisfied by a checkbox.

The widening is monotone on purpose: nothing that was refused before is
easier to accept now. Eleven proposals that had no requirement at all
now have one.

VOCABULARY — two sets, and they are not the same set
-----------------------------------------------------

`REASONS` is what can be RECORDED in `suggestion_flags`, constrained by
0061's CHECK. `legacy_unreviewed` is deliberately NOT among them: it is
derived from the shape of the proposal, never stored, so there is no
row to write, nothing to seed, and nothing that can rot out of date
against the queue. A table whose purpose is accurate records should not
carry thirty rows asserting only "this is old", which the proposal
already says for itself.

WHAT A REQUIREMENT DOES NOT AUTHORISE
-------------------------------------

Nothing here declines, accepts, migrates, rewrites or deletes a
suggestion, and nothing here touches a biographical answer. A
requirement makes acceptance need a deliberate act; it never resolves
anything on its own.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

from .suggestion_review import split_destination, value_hash

__all__ = [
    "REASONS", "LEGACY_UNREVIEWED", "SECTIONS_ADDED_BY_WO04",
    "REQUIRE_ACKNOWLEDGE", "REQUIRE_CORRECT",
    "SuggestionFlagged", "flag_for", "requires_review", "record_flag",
    "mark_disposed", "flags_for_person",
]

# Recordable in `suggestion_flags`. Mirrors 0061's CHECK constraint; a
# test asserts the two agree, because a reason this module accepts and
# the database rejects would fail at the INSERT, mid-classification.
REASONS = (
    "queued_before_home",
    "value_not_a_field",
    "model_uncertainty",
    "misclassified_section",
)

# Derived, never stored. See "VOCABULARY" above.
LEGACY_UNREVIEWED = "legacy_unreviewed"

# The two levels. Ordered: index in this tuple is the strength.
REQUIRE_ACKNOWLEDGE = "acknowledge"
REQUIRE_CORRECT = "correct"
_STRENGTH = (REQUIRE_ACKNOWLEDGE, REQUIRE_CORRECT)

# The sections WO-04 creates. A proposal aimed at one of these that
# predates the server-owned queue could not have had its destination
# checked when it was queued, because the destination did not exist.
#
# This tuple is the strong structural tier's whole basis, so it is
# defined once here and asserted against the questionnaire by a test:
# every id must BE a section (after WO-04's schema commit), and every
# one must have been absent before it.
SECTIONS_ADDED_BY_WO04 = frozenset({"military", "residence", "travel", "faith"})


class SuggestionFlagged(Exception):
    """Acceptance refused: this proposal needs a deliberate act and the
    request did not supply one.

    Carries everything the review surface needs to explain the refusal
    and offer the real options. `requirement` is which act will do —
    CORRECT means a value or a different destination, ACKNOWLEDGE means
    an explicit "I have read this and it is right".
    """

    def __init__(self, reason: str, detail: str, proposed_value: Any = None,
                 source_note: str = "", field_path: str = "",
                 requirement: str = REQUIRE_CORRECT):
        self.reason = reason
        self.detail = detail
        self.proposed_value = proposed_value
        self.source_note = source_note
        self.field_path = field_path
        self.requirement = requirement
        super().__init__(detail)

    @property
    def needs_correction(self) -> bool:
        return self.requirement == REQUIRE_CORRECT


def _stronger(a: Optional[SuggestionFlagged],
              b: Optional[SuggestionFlagged]) -> Optional[SuggestionFlagged]:
    """The requirement a person must satisfy when two apply.

    Not "the first one found". A recorded doubt about the content must
    not be downgraded to a checkbox because the destination happens to
    be old.
    """
    if a is None:
        return b
    if b is None:
        return a
    return b if _STRENGTH.index(b.requirement) > _STRENGTH.index(a.requirement) else a


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
    about whether its destination existed, whether the value was
    validated, or whether anyone ever looked at it.
    Present-and-False means the destination was checked and was fine.

    This is the whole basis of both structural tiers, and it is a
    statement about PROVENANCE, not about content. A proposal made
    through the current route carries the key and is not legacy however
    old it later becomes.
    """
    return "destination_undefined" not in suggestion


def _structural(suggestion: Mapping[str, Any],
                section: str) -> Optional[SuggestionFlagged]:
    """The requirement that needs no flag row.

    Cannot be missed by a classifier that did not run, cannot go stale
    against the queue, and cannot be removed by deleting a row.
    """
    if not _is_unchecked_legacy(suggestion):
        return None

    path = str(suggestion.get("fieldPath") or "")

    if section in SECTIONS_ADDED_BY_WO04:
        # Nobody ever chose this destination, because it did not exist.
        # There is nothing to acknowledge — the placement itself is the
        # open question, so a correction or a re-home is the honest act.
        return SuggestionFlagged(
            "queued_before_home",
            f"This was proposed before the questionnaire had a '{section}' "
            "section, so nobody ever chose this destination for it. Check the "
            "value belongs here before accepting. If it belongs somewhere "
            "else, decline it and enter it yourself in the right section — "
            "there is no one-click way to move it.",
            proposed_value=suggestion.get("value"),
            field_path=path,
            requirement=REQUIRE_CORRECT,
        )

    # A destination that existed all along. The proposal may well be
    # right — and this tier says nothing about whether it is. It says
    # only that it is old and unreviewed, and that someone should read
    # it before it becomes permanent.
    return SuggestionFlagged(
        LEGACY_UNREVIEWED,
        "This was queued before suggestions were reviewed at all, so nobody "
        "has read it. Confirm it is right and accept it as it stands, correct "
        "it, or decline it.",
        proposed_value=suggestion.get("value"),
        field_path=path,
        requirement=REQUIRE_ACKNOWLEDGE,
    )


def requires_review(con: sqlite3.Connection, person_id: str,
                    suggestion: Mapping[str, Any]) -> Optional[SuggestionFlagged]:
    """What must a person do before this proposal can be accepted?

    Returns the exception to raise — carrying `.requirement`, which is
    REQUIRE_ACKNOWLEDGE or REQUIRE_CORRECT — or None if nothing is
    required. Called from inside the accept transaction as well as
    before it; see the module docstring for why an interface that hides
    a button is not sufficient.
    """
    section, field, _rep = split_destination(str(suggestion.get("fieldPath") or ""))

    # Both tiers are evaluated. The strongest applies — see `_stronger`.
    req = _structural(suggestion, section)

    row = flag_for(con, person_id, suggestion)
    if row is not None:
        detail = {
            "queued_before_home":
                "This was proposed before the questionnaire had a place for it. "
                "Check it belongs here before accepting.",
            "value_not_a_field":
                f"The proposed value does not look like a '{field}'. "
                "Correct it here, or decline it and enter it yourself where "
                "it belongs.",
            "model_uncertainty":
                "This value is the model describing its own uncertainty rather "
                "than an answer. Enter what is actually known, or decline it.",
            "misclassified_section":
                f"This looks like the right kind of fact in the wrong place — "
                f"'{section}' may not be where it belongs. Decline it and "
                f"enter it in the right section; accepting here would file it "
                f"under '{section}' permanently.",
        }.get(row["reason"], "This proposal was flagged for review.")
        req = _stronger(req, SuggestionFlagged(
            row["reason"], detail,
            proposed_value=row["proposed_value"],
            source_note=row["source_note"] or "",
            field_path=row["field_path"] or "",
            requirement=REQUIRE_CORRECT,
        ))

    return req


# ── writes ──────────────────────────────────────────────────────────


def record_flag(con: sqlite3.Connection, person_id: str,
                suggestion: Mapping[str, Any], reason: str, *,
                source_note: str = "", flagged_by: str = "") -> None:
    """Record one flag. Idempotent on the canonical tuple.

    Running the classifier twice records the same flags, not duplicates:
    the primary key is (person, section, entry, field, value_hash) and
    the ON CONFLICT re-states the same reason. A `suggestion_id` learned
    on a later run is filled in; one already known is never overwritten
    with NULL.

    Does NOT commit — the caller owns the transaction, so a classifier
    run is all-or-nothing.

    Writes only to `suggestion_flags`. No suggestion, no questionnaire
    answer and no review record is touched here.
    """
    if reason not in REASONS:
        # `legacy_unreviewed` lands here too, and should: it is derived,
        # not recorded. See "VOCABULARY" in the module docstring.
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
        # `flagged_at` and `flagged_by` are FIRST-flagged, not
        # last-recorded. Overwriting them made a re-run of the
        # classifier move every timestamp forward, so a flag raised in
        # September looked raised today — and the idempotency check had
        # to leave two columns out of the comparison to pass. A check
        # that has to look away from a column is reporting the column,
        # not the code.
        "  flagged_at=COALESCE(suggestion_flags.flagged_at, excluded.flagged_at), "
        "  flagged_by=CASE WHEN COALESCE(suggestion_flags.flagged_by,'') = '' "
        "                  THEN excluded.flagged_by ELSE suggestion_flags.flagged_by END",
        (person_id, section, "", field, value_hash(suggestion.get("value")),
         (suggestion.get("suggestion_id") or None),
         str(suggestion.get("fieldPath") or ""),
         "" if suggestion.get("value") is None else str(suggestion.get("value")),
         reason, source_note, now, flagged_by),
    )


def mark_disposed(con: sqlite3.Connection, person_id: str,
                  suggestion: Mapping[str, Any], disposition: str) -> None:
    """A person acted on a flagged proposal. Same transaction as the act.

    A no-op when the requirement was structural, because there is no row
    to dispose — which is correct, and is why the structural tiers
    cannot be cleared by acting once.
    """
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
    canonical tuple. Read-only; used by the review surface.

    RECORDED flags only. The structural tiers are not here, because they
    are derived from each proposal and the review surface can derive
    them the same way. A surface that showed only this dict would show
    nothing for the eleven legacy rows — which is why the endpoint, not
    the surface, is what refuses.
    """
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
            "requirement": REQUIRE_CORRECT,
        }
    return out
