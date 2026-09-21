"""What a queue entry IS. One constructor, for every producer.

WHY THIS MODULE EXISTS
----------------------
The previous commit message claimed:

    Both producers now go through one constructor establishing the four
    facts the server owns.

That was not true of the code. `projection_writer` called
`_server_owned_suggestion`; the append route still built its own dict
inline. The fields happened to line up, so nothing was broken — but two
implementations of "what a queue entry is" drift, and the drift is
invisible until a row reaches a consumer that needs a key one of them
forgot. That is exactly how the thirty ID-less fossils happened.

An outside review caught the overstatement. This module makes the claim
true rather than rewording it.

THE FOUR FACTS THE SERVER OWNS
------------------------------
Decided here, at creation, and never re-decided downstream:

  suggestion_id           minted. Without it `find_suggestion` cannot
                          match the entry, so it can be neither accepted
                          NOR declined — only accumulated. Thirty
                          proposals sat in that state.
  turn_evidence           the MEASURED verdict on the cited turn, via
                          the same join WO-03A uses. A citation is a
                          claim; it is checked before it is stored.
  destination_undefined   whether the questionnaire defines this field.
                          Its PRESENCE is also what marks an entry as
                          non-legacy, which is correct: this one was
                          checked by today's code.
  destination_unresolved  a repeatable section needs a person to choose
                          an entry. An ordinal is never inferred.

FAIL-CLOSED ON AN UNREADABLE SCHEMA. If the questionnaire cannot be
parsed we cannot claim the destination is valid, so we say it is
undefined and acceptance refuses until someone looks. Claiming `False`
— "checked, and fine" — on the strength of an exception is the one
answer that is definitely wrong.

`test_there_is_exactly_one_construction_site` asserts no other module
mints an id, so a third producer added later fails a test rather than
quietly rebuilding the problem.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

__all__ = ["build", "mint_id"]


def mint_id() -> str:
    """`sg_` + 16 hex. One shape, so nothing downstream can branch on
    which producer made an entry."""
    return "sg_" + uuid.uuid4().hex[:16]


def build(field_path: str, value: Any, now: str, *,
          person_id: Optional[str] = None,
          source_turn_id: Optional[str] = None,
          confidence: float = 0.0,
          origin: Optional[str] = None,
          con=None,
          **extra: Any) -> Dict[str, Any]:
    """One queue entry, with every fact the server owns already decided.

    `con` is an open connection when the caller already holds one — the
    append route does, inside its own transaction. Omitted, a short-lived
    connection is opened just for the turn check.
    """
    entry: Dict[str, Any] = {
        "suggestion_id": mint_id(),
        "fieldPath": field_path,
        "value": value,
        "confidence": float(confidence or 0.0),
        # The CLAIMED turn, kept whatever the verdict. Nulling it would
        # erase the difference between "no citation" and "a citation that
        # did not check out" — WO-03A's rule.
        "turnId": source_turn_id,
        "source_turn_id": source_turn_id,
        "ts": now,
        "repeats": 1,
    }
    if origin:
        entry["origin"] = origin
    entry.update({k: v for k, v in extra.items() if v is not None})

    entry["turn_evidence"] = _evidence(con, person_id, source_turn_id)

    # THE INDEX IS STRIPPED. `parents[0].firstName` is a proposal about
    # the `parents` section; leaving the `[0]` on makes `is_repeatable`
    # answer about a section called "parents[0]", which does not exist,
    # so an indexed path would come back resolved and Accept would light
    # up with no entry chosen. Caught by
    # `test_an_indexed_path_is_also_unresolved`, which the first version
    # of this function broke.
    head, _, rest = str(field_path or "").partition(".")
    section = head.split("[")[0]
    field = rest.split(".")[-1] if rest else ""
    try:
        from . import questionnaire_schema as _qs
        entry["destination_undefined"] = not _qs.is_defined(section, field)
        # ALWAYS WRITTEN, both ways. The review surface reads
        # `!!s.destination_unresolved`, so False and absent behave the
        # same there — but a consumer that checks `in` rather than
        # truthiness would read an absent key as "nobody decided", and
        # the whole point of this constructor is that somebody did.
        entry["destination_unresolved"] = bool(_qs.is_repeatable(section))
    except Exception:
        logger.warning("[suggestion-entry] questionnaire schema unreadable; "
                       "queuing %s as destination_undefined", field_path)
        entry["destination_undefined"] = True
        # Unknown, and an unresolved proposal is refused at accept until
        # a person picks an entry — the safe direction.
        entry["destination_unresolved"] = True
    return entry


def _evidence(con, person_id: Optional[str], turn_id: Optional[str]) -> str:
    if not (turn_id and person_id):
        return "absent"
    try:
        from .answer_provenance import verify_turn
        if con is not None:
            return verify_turn(con, person_id, turn_id)
        from .. import db as _db
        c = _db._connect()
        try:
            return verify_turn(c, person_id, turn_id)
        finally:
            c.close()
    except Exception:
        # A citation we could not check is UNVERIFIED, not absent.
        # "absent" means no conversation was cited, which would be a
        # false statement about a proposal that cited one.
        logger.warning("[suggestion-entry] could not verify turn %r; "
                       "recording the citation as unverified", turn_id)
        return "unverified"
