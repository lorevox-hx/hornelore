"""Server-authoritative Profile Seed state for the two REST chat paths.

WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 2, Step 5.

── WHAT THIS IS FOR ───────────────────────────────────────────────────

Steps 1–4 built the walk and the prompt section; nothing supplied the
state, so `profile_seed_onboarding` was unreachable by any narrator.
This is the first transport that supplies it, and it supplies it for
**prompt composition only**.

`POST /api/chat` and `POST /api/chat/stream` compose with
`runtime71=None` today. That is not a neutral default: with no runtime
the composer renders `KNOWN IDENTITY FACTS:\\n- none yet` and treats
identity as incomplete, so a narrator the server knows perfectly well is
described to Lori as a stranger. Supplying `identity_complete=True` on
its own does not fix it — the three facts are read from three separate
runtime keys (`speaker_name`, `dob`, `pob`), and a runtime carrying only
the Boolean produces a prompt that says identity is complete and then
lists no identity. **The Boolean and the facts travel together or not at
all.**

── WHAT IT DELIBERATELY DOES NOT DO ───────────────────────────────────

**It never advances the walk and never writes a turn event.** Step 3's
two durable events — `presented` and `response` — live on the
committed-turn path, which is Step 6's work over WebSocket. REST reads
the resolved row and composes from it.

**The consequence is sharper than "the question repeats", and the first
version of this note understated it.** Measured on the live stack,
2026-08-27:

    narrator: "We moved to Minot when I was four, so I grew up there."
    Lori:     "Minot is coming through clearly. What was your family's
               reason for moving?"
    durable:  active=childhood_home · remaining=10 · version=2  UNCHANGED

The narrator ANSWERED the topic and it stays `unanswered` permanently.
Within a session the conversation history hides that, because Lori can
see what was just said and follows it naturally. **Across a session
boundary she cannot** — the history is gone, the durable row still says
the topic is open, and she asks for something the narrator already told
her. That is the re-interrogation Principle 8 forbids, arriving through
a gap in recording rather than through a design that intended to ask.

It is bounded: `active_topic_id` only moves when a real answer is
applied, so nothing is lost or corrupted, and this is still strictly
better than the status quo where the question could not be asked at all.
But it is a REASON TO FINISH STEP 6, not a reason to make REST write —
recording a presentation belongs on the committed-turn path, where the
response event that consumes it also lives.

*(The earlier wording — "a REST caller can be shown the same question on
consecutive turns" — described a cosmetic annoyance. What is actually at
risk is a narrator being asked twice for something they have already
given, which is the specific harm this work order exists to prevent.)*

`reconcile()` is NOT called here either. It materializes changes and
this path must not. `read_row()` plus the pure resolution is all a read
needs, and the difference matters: a GET that writes turns every page
refresh into a version bump.

── OWNERSHIP, AND WHY THE CLAIM LOSES ─────────────────────────────────

`PROFILE_JSON` arrives inside the system message of an HTTP body. It is
a CLAIM by the caller, not an authority, and the Picker identity
boundary in `CLAUDE.md` is explicit that destination identity is never
inferred from a payload.

So: the recorded session owner wins. The claim is used only when no
owner is recorded — which is the truthful state of every session row
written before migration 0044, and is not a guess about who they are but
an admission that we never wrote it down. When the two DISAGREE, this
module refuses and composes nothing, because a mismatch means one of two
things and both are bad: a stale browser tab pointed at another
narrator, or a caller asserting an identity that is not theirs. Guessing
between them would put one narrator's onboarding questions in front of
another narrator.

── STORAGE FAULTS ARE NOT ABSENCE ─────────────────────────────────────

The same rule Phase 1 established. A `sqlite3.Error` here must not
degrade into "this narrator has no onboarding row", because that is
indistinguishable from a historical narrator and would silently retire
the walk for someone mid-way through it. Storage faults propagate.
"Compose nothing" is reserved for cases we actually resolved.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Tuple

from . import profile_seed as _seed
from . import profile_seed_turn as _turn
from . import profile_seed_runtime as _runtime

#: The runtime key the composer's section reads. Imported rather than
#: retyped so a rename cannot leave this transport writing a key nobody
#: reads — the failure would be silent, and would look exactly like a
#: narrator who has finished the walk.
from ..prompt_composer import PROFILE_SEED_ONBOARDING_KEY

__all__ = [
    "CLAIM_KEY",
    "ContradictoryClaim",
    "OwnerClaimMismatch",
    "onboarding_runtime",
    "resolve_rest_identity",
]


def _now() -> str:
    """Passed to the resolver, which needs it only for `completed_at`.

    Nothing here writes, so this timestamp never reaches storage. It is
    supplied because the shared resolver's signature requires it, and a
    resolver that invented its own clock would be harder to test than
    one handed a value.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class OwnerClaimMismatch(Exception):
    """The session's recorded owner is not the narrator the caller claims.

    Carries both ids for the operator-facing log. It is deliberately NOT
    an HTTP exception: this module must stay importable without FastAPI,
    and the router decides the status code.
    """

    def __init__(self, conv_id: str, owner: str, claimed: str) -> None:
        super().__init__(
            f"session {conv_id!r} belongs to {owner!r} but the request "
            f"claims {claimed!r} — refusing to compose")
        self.conv_id = conv_id
        self.owner = owner
        self.claimed = claimed


class ContradictoryClaim(Exception):
    """A PROFILE_JSON blob names more than one narrator.

    Refused for the same reason an owner/claim mismatch is: two answers
    to "who is this" is not a tie to be broken, and picking one would
    put a narrator's onboarding questions in front of someone else.
    """

    def __init__(self, keys: Mapping[str, str]) -> None:
        named = ", ".join(f"{k}={v!r}" for k, v in sorted(keys.items()))
        super().__init__(
            f"PROFILE_JSON names more than one narrator ({named}) — "
            "refusing to choose between them")
        self.keys = dict(keys)


#: The ONLY key the transport map specifies. The aliases are read solely
#: to DETECT a contradiction, never to satisfy a claim on their own.
CLAIM_KEY = "person_id"
_CLAIM_ALIASES = ("personId", "active_person_id")


def _claimed_person_id(profile_obj: Optional[Mapping[str, Any]]) -> Optional[str]:
    """The `person_id` a PROFILE_JSON blob asserts, if it asserts one.

    ── ONE SPECIFIED KEY, 2026-08-26 ──────────────────────────────────

    *(This accepted `person_id`, `personId` and `active_person_id`, and
    returned whichever it met first. Two problems, and the second is the
    worse one. The specification names `person_id` alone, so the others
    widened an identity boundary with no stated contract — and this
    repository's Picker doctrine is explicit that destination identity is
    never inferred. Worse, first-match meant a payload whose keys
    DISAGREED silently resolved to whichever the loop happened to reach
    first, which is a coin toss deciding which narrator gets asked about
    their childhood.)*

    So `person_id` is the claim. The aliases are still READ, because a
    payload carrying a conflicting one is evidence of a confused caller
    and must not be quietly ignored either — it raises.

    Only a non-empty string counts. A number, a dict or a blank is not a
    narrator id, and coercing one would manufacture a claim the caller
    did not make.
    """
    if not isinstance(profile_obj, Mapping):
        return None

    def _clean(key):
        value = profile_obj.get(key)
        return value.strip() if isinstance(value, str) and value.strip() else None

    claim = _clean(CLAIM_KEY)
    present = {k: v for k, v in
               ((a, _clean(a)) for a in _CLAIM_ALIASES) if v}
    if present:
        distinct = set(present.values()) | ({claim} if claim else set())
        if len(distinct) > 1:
            named = dict(present)
            if claim:
                named[CLAIM_KEY] = claim
            raise ContradictoryClaim(named)
    return claim


def resolve_rest_identity(
        conv_id: Optional[str],
        profile_obj: Optional[Mapping[str, Any]],
        *,
        owner_lookup=None) -> Optional[str]:
    """Which narrator this REST turn is for, or `None`.

    Owner first, claim only as a fallback, mismatch refused. `None` means
    "no narrator resolved", which is an ordinary and common answer — an
    anonymous `/api/chat` call with no `conv_id` is not an error.

    `owner_lookup` is injected for tests; production passes
    `db.get_session_owner`.
    """
    claimed = _claimed_person_id(profile_obj)
    conv = (conv_id or "").strip()
    if not conv:
        # No session to own anything. A bare claim is all there is, and
        # it is the caller's own assertion about a conversation with no
        # server-side identity — accepted, because refusing would break
        # every anonymous call, and harmless, because an unenrolled or
        # unknown id resolves to no onboarding state below.
        return claimed

    if owner_lookup is None:                     # pragma: no cover - wiring
        from ..db import get_session_owner as owner_lookup

    # NOT wrapped in `except sqlite3.Error`. A failed owner lookup that
    # fell through to the claim would let a storage fault promote an
    # unverified assertion into an authority — the exact inversion this
    # module exists to prevent.
    owner = owner_lookup(conv)
    owner = owner.strip() if isinstance(owner, str) else None

    if owner and claimed and owner != claimed:
        raise OwnerClaimMismatch(conv, owner, claimed)
    return owner or claimed


def _identity_facts(person: Mapping[str, Any],
                    basics: Mapping[str, Any]) -> Dict[str, Any]:
    """The three anchors, in the keys the composer actually reads.

    `speaker_name` / `dob` / `pob` are `_known_identity_facts_block`'s
    field names. Empty values are OMITTED rather than sent as `""` so
    that a partially known narrator renders the facts we have and stays
    silent about the rest, which is what that block already does for
    every other caller.
    """
    facts: Dict[str, Any] = {}
    name = ((person or {}).get("display_name")
            or (basics or {}).get("preferred") or "")
    if isinstance(name, str) and name.strip():
        facts["speaker_name"] = name.strip()
    dob = (person or {}).get("date_of_birth")
    if isinstance(dob, str) and dob.strip():
        facts["dob"] = dob.strip()
    pob = (person or {}).get("place_of_birth")
    if isinstance(pob, str) and pob.strip():
        facts["pob"] = pob.strip()
    return facts


def _resolved_read(con: sqlite3.Connection,
                   person_id: str) -> Tuple[Optional[Dict[str, Any]],
                                            Dict[str, Any], bool]:
    """`(state_dict_or_None, identity_facts, identity_complete)`.

    A READ, through the SHARED resolver.

    *(This first read the stored row directly — status, active topic and
    topic_state straight off `profile_seed_onboarding`. It looked
    read-only and correct, and it was neither: a freshly enrolled
    narrator sits at `pending` until the identity anchors are resolved,
    so REST would have composed nothing for exactly the narrators this
    work order exists for, and the walk would have stayed unreachable
    with a test suite reporting green. The obvious repair — recompute
    status here — would have been a second definition of narrator state.
    `resolve_effective()` was extracted from `reconcile()` instead, so
    the rules live in one place and this path simply declines to
    write.)*
    """
    # ── ONE SNAPSHOT, 2026-08-26 ───────────────────────────────────────
    #
    # These were two independent reads of `people`: identity facts here,
    # then `resolve_effective()` reading the same row again. Review
    # reproduced a concurrent update landing between them and got
    # `identity_complete=True` with `speaker_name` present but `dob` and
    # `pob` GONE — the self-contradicting runtime this whole requirement
    # exists to prevent, assembled from two moments that never both
    # existed.
    #
    # `BEGIN DEFERRED` opens the read transaction, so every SELECT below
    # sees one consistent view of the database. It takes no write lock
    # and this path still writes nothing.
    con.execute("BEGIN DEFERRED;")
    try:
        person, basics = _seed._person_and_basics(con, person_id)
        facts = _identity_facts(person, basics)
        resolved = _seed.resolve_effective(con, person_id, now=_now())
    finally:
        # ROLLBACK, not commit. Nothing here may write, and rolling back
        # a read-only transaction is how that is enforced rather than
        # merely intended — `resolve_effective()` is shared with the
        # write path, and a future change there must not be able to
        # persist through this caller.
        #
        # The rollback's OWN failure is swallowed, and only its own.
        #
        # *(Unguarded, a `ROLLBACK` that failed inside `finally` would
        # REPLACE the exception propagating through it — so "database is
        # locked", the fault this module exists to keep visible, would
        # reach the operator as a rollback error from a line that is not
        # where anything went wrong. Storage faults are not absence, and
        # they are also not to be overwritten by the cleanup that
        # follows them. The connection is closed by the caller either
        # way, and SQLite rolls back an open transaction on close, so
        # nothing is left dangling.)*
        try:
            con.execute("ROLLBACK;")
        except sqlite3.Error:
            pass

    if resolved is None:
        # HISTORICAL narrator: no onboarding row, and none is created.
        # Identity facts still travel — knowing who someone is was never
        # conditional on enrolling them in a walk.
        return None, facts, _seed.identity_anchors_complete(person, basics)

    state, _changed = resolved
    # `_changed` is DISCARDED, deliberately. It is the write half's
    # signal and this path does not write; acting on it here is how a
    # read starts materializing.
    return state.as_dict(), facts, state.identity_complete


def onboarding_runtime(
        conv_id: Optional[str],
        profile_obj: Optional[Mapping[str, Any]],
        *,
        owner_lookup=None,
        connect=None) -> Dict[str, Any]:
    """The runtime fragment for one REST turn. `{}` when there is none.

    An EMPTY DICT is the "nothing to say" answer, and the caller must
    treat it as meaning the prompt is composed exactly as it was before
    this step existed — see the byte-stability tests. That covers a
    conversation with no narrator, an unowned session with no claim, a
    person who does not exist, and a narrator with nothing to add.

    Raises `OwnerClaimMismatch` when ownership is contradicted, and
    propagates `sqlite3.Error`. Neither is converted into `{}`.
    """
    person_id = resolve_rest_identity(conv_id, profile_obj,
                                      owner_lookup=owner_lookup)
    if not person_id:
        return {}

    if connect is None:                          # pragma: no cover - wiring
        from ..db import _connect as connect, init_db
        init_db()

    con = connect()
    try:
        state, facts, anchors_ok = _resolved_read(con, person_id)
    finally:
        con.close()

    plan = _turn.plan_turn(state=state, history=[], narrator_text=None)

    # ── NO PLAN MEANS NO RUNTIME AT ALL, 2026-08-26 ────────────────────
    #
    # This returned the identity facts whenever the narrator had any —
    # including for HISTORICAL and COMPLETED narrators, who have no walk
    # to run. It read as generosity and was a boundary violation, and
    # the size of it is the point: **supplying ANY runtime dict makes
    # the composer emit its whole runtime block**, so a historical
    # narrator's prompt grew by 17,760 characters. Measured, not
    # estimated. Step 4's byte-stability tests had already recorded this
    # exact effect on a sparse runtime — 7,365 characters with no
    # runtime, 23,023 with a nearly empty one — and I reintroduced it
    # one module over.
    #
    # Step 5's boundary is explicit that ownerless, historical,
    # completed, warmup and translation prompts are preserved
    # byte-for-byte. Identity facts for narrators with no active walk
    # may well be worth supplying; that is a prompt change on its own
    # merits, for a step that is scoped to make it and review it.
    if plan.action == _turn.IDLE:
        return {}

    runtime: Dict[str, Any] = dict(facts)
    # The transport map requires `person_id` alongside the facts, and it
    # is load-bearing rather than informational: the composer's
    # person-dependent memory layer is skipped without it, so a narrator
    # would be named in the prompt and still have no memory attached.
    runtime["person_id"] = person_id
    runtime["identity_complete"] = bool(anchors_ok)
    # ── ONE PAYLOAD DEFINITION, SHARED WITH THE WEBSOCKET, Step 6 ──────
    #
    # This dict used to be built here by hand. Step 6 needs the same
    # fragment on the committed-turn path, and writing it a second time
    # there would give the composer two authors — which drifts one field
    # at a time, silently, because each transport's own tests keep
    # passing while the narrator gets a different prompt depending on how
    # they connected. `profile_seed_runtime` is the single builder;
    # REST's output is unchanged, and the byte-stability tests pin that.
    runtime[PROFILE_SEED_ONBOARDING_KEY] = _runtime.onboarding_payload(
        plan, state)
    return runtime
