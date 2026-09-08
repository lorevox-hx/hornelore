"""One definition of the onboarding runtime payload, for every transport.

WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 2, Step 6.

── WHY THIS MODULE EXISTS ─────────────────────────────────────────────

Step 5 built the payload inline in `profile_seed_rest.py`. Step 6 needed
the same payload on the WebSocket path, and the obvious way to get it —
writing the dict again next to the WebSocket's own composition — would
have produced **two hand-built definitions of what the composer reads**.

That is not a style objection. The composer's section renders from
`action`, `topic_id`, `known_topics`, `remaining_topics` and
`completes_walk`; two builders drift one field at a time, and the drift
is silent because each transport's own tests keep passing. The failure
mode is a narrator who gets one prompt over REST and a different prompt
over the WebSocket for the same durable state — the two paths disagreeing
about what the server knows, which is the exact class of defect this
work order exists to end.

**So the payload is built once, here, and both transports call it.**

── WHAT THIS MODULE IS, STATED ACCURATELY ─────────────────────────────

*(An earlier version of this note called the module "a serializer" that
"resolves nothing, writes nothing". That was true of the payload half
and FALSE of the module — `prepare_turn` drives a recovery that can
apply a disposition to durable state. Describing an orchestrator as a
formatting helper is how a reader concludes it is safe to call twice, or
safe to call from a read-only path, and neither is true.)*

Two halves, with different characters, and the difference is the thing
to keep straight:

  * **`onboarding_payload` and `attach_onboarding` are pure.** Given a
    plan and a state they compute a dict. No I/O, no ordering
    requirement, safe anywhere.
  * **`prepare_turn` ORCHESTRATES.** It runs recovery before resolution
    before planning, and recovery calls the injected `apply_fn` — so a
    call to `prepare_turn` CAN WRITE, advancing the walk by re-applying
    a response committed on an earlier turn. It is once-per-turn, on the
    committed-turn path, and it is not safe to call speculatively.
  * `commit_meta` and `should_advance` are pure decisions over that
    plan, kept here so both live beside the orchestration they gate.

What the module still does NOT own is authority: `profile_seed.py` owns
the state and its transitions, `profile_seed_turn.py` owns the reducer
and the plan. Storage access arrives only as injected callables, never
imported here — which is what keeps the write confined to the caller's
own database session and testable without one.

── BYTE-STABILITY IS A CONSTRAINT, NOT AN ASPIRATION ──────────────────

The fields are reproduced exactly as Step 5 emitted them, including two
details that look like defects and are deliberately preserved:

  * `known_topics` and `remaining_topics` are passed through as stored
    without re-validating each id against the registry. Step 5 did not
    filter, and filtering here would change accepted REST output in a
    commit whose job is extraction.
  * `completes_walk` is always present. Step 5 guarded it with
    `if plan.completes_walk is not None`, which can never be false — the
    field is a `bool` with a default — so the key was always emitted.
    The guard is dropped rather than reproduced, because copying a
    condition that cannot vary preserves the appearance of a decision
    nobody made.

Both are recorded so a later reader can change them on purpose.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional

from . import profile_seed_turn as _turn

#: Imported, never retyped. A rename in the composer must break this
#: import rather than leave two transports writing a key nobody reads —
#: and a key nobody reads looks exactly like a narrator who has finished
#: the walk, which is the quietest possible way to lose the feature.
from ..prompt_composer import (PROFILE_SEED_ONBOARDING_KEY,
                               PROFILE_SEED_SERVER_ATTESTED_KEY,
                               PROFILE_SEED_STATUS_KEY,
                               PROFILE_SEED_RESERVED_RUNTIME_KEYS)

__all__ = [
    "PROFILE_SEED_ONBOARDING_KEY",
    "PROFILE_SEED_SERVER_ATTESTED_KEY",
    "PROFILE_SEED_STATUS_KEY",
    "PROFILE_SEED_RESERVED_RUNTIME_KEYS",
    "apply_server_identity",
    "attach_seed_status",
    "sanitize_client_runtime",
    "onboarding_payload",
    "attach_onboarding",
    "PreparedTurn",
    "prepare_turn",
    "commit_meta",
    "should_advance",
]


def onboarding_payload(
    plan: Optional[_turn.TurnPlan],
    state: Optional[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    """The composer's onboarding fragment, or `None` for "say nothing".

    `None` is returned for a missing plan and for `IDLE`, and the two
    mean the same thing to a caller: compose exactly as if this feature
    did not exist. `HOLD` deliberately DOES produce a payload — it is an
    active walk that asks nothing this turn, and the section's job on a
    held turn is to keep the legacy browser pass suppressed rather than
    to render a question.
    """
    if plan is None or plan.action == _turn.IDLE:
        return None
    resolved = state or {}
    return {
        "action": plan.action,
        "topic_id": plan.topic_id,
        "known_topics": list(resolved.get("known_topics") or []),
        "remaining_topics": list(resolved.get("remaining_topics") or []),
        "completes_walk": bool(plan.completes_walk),
    }


def attach_onboarding(
    runtime: Optional[Mapping[str, Any]],
    plan: Optional[_turn.TurnPlan],
    state: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """`runtime` plus the onboarding key, as a NEW dict.

    Copied rather than mutated because `runtime71` is threaded through a
    long handler and shared with callers that must not observe a key
    appearing underneath them; every other runtime contributor on that
    path copies for the same reason.

    When there is nothing to say the runtime is returned unchanged apart
    from the copy, so the composed prompt stays byte-identical to a tree
    without this step.
    """
    out: Dict[str, Any] = dict(runtime or {})
    payload = onboarding_payload(plan, state)
    if payload is not None:
        out[PROFILE_SEED_ONBOARDING_KEY] = payload
        # Reaching this line means a resolver ran against the database for
        # this narrator on this turn. A client cannot forge it ON THIS
        # PATH because `sanitize_client_runtime` removes the key from
        # browser input before any resolution starts.
        #
        # **The marker is a Boolean and proves nothing by itself** — it
        # cannot show who set it. That stripping is what actually holds
        # the boundary, and every client-derived transport must keep
        # doing it. The composer's contribution is narrower and still
        # worth having: it FAILS CLOSED when the marker is absent.
        out[PROFILE_SEED_SERVER_ATTESTED_KEY] = True
    else:
        # ── THE SERVER'S ANSWER IS AUTHORITATIVE BOTH WAYS, Phase 3 ────
        #
        # *(This used to only ADD the key. When the server had no plan it
        # left `runtime` untouched — and `runtime` is the browser's
        # `runtime71`, so a CLIENT-SUPPLIED onboarding payload survived
        # into composition unchallenged. A fabricated one would then have
        # rendered an onboarding block and suppressed the legacy pass
        # directive for a narrator the server says has no walk at all.*
        #
        # *`test_an_untruthful_sparse_runtime_does_NOT_get_identity_for_free`
        # already guarded the identity half of that hole from the
        # composer side. This closes the transport half: on any path that
        # calls this, the key is present when the SERVER resolved a plan
        # and absent when it did not.)*
        for _key in PROFILE_SEED_RESERVED_RUNTIME_KEYS:
            out.pop(_key, None)
    return out


# ── The three rules the committed-turn path runs on ────────────────────
#
# ── WHY THESE ARE HERE AND NOT INLINE IN THE ROUTER, Step 6 ────────────
#
# The WebSocket handler is a 5,000-line function inside an async
# websocket route. Logic written inline there is reachable only by a test
# that can stand up fastapi, torch and a model — which is why the rules
# that decide whether a narrator's answer is recorded would otherwise
# have been the least-tested code in the feature.
#
# Extracting them is NOT a redesign of the step: the router still does
# the recovering, the merging and the applying, in that order, at the
# same three points. What moved out is the DECIDING. Each function below
# answers one question with no I/O of its own, so the tests exercise the
# same code the router runs rather than a second copy of its reasoning
# living in a test file — the failure mode where a simulator and a
# handler agree with each other and both differ from production.


@dataclass(frozen=True)
class PreparedTurn:
    """What the pre-composition pass produced for one turn."""
    plan: _turn.TurnPlan
    state: Optional[Dict[str, Any]]
    recovery: _turn.RecoveryOutcome


def prepare_turn(
    person_id: str,
    history: Optional[Any],
    *,
    narrator_text: Optional[str],
    eligible: bool,
    resolve_fn: Callable[[str], Optional[Mapping[str, Any]]],
    apply_fn: Callable[..., Any],
) -> PreparedTurn:
    """Recover, then resolve, then plan. **In that order, every turn.**

    **THIS CAN WRITE.** Recovery calls `apply_fn`, so a call here may
    advance the walk by re-applying a response committed on an earlier
    turn whose apply never landed. It is once per committed turn and it
    is not safe to call speculatively, from a read-only path, or twice.


    Recovery runs FIRST and composition uses the state it re-resolved,
    never the snapshot from before it. Reversing those two produces a
    specific and cruel bug: a response committed on an earlier turn whose
    apply never landed stays unapplied, the presentation it consumed is
    gone, and the narrator is asked a question whose answer is sitting
    committed one row above. That is repetition wearing retry's clothes.

    **Storage faults PROPAGATE.** Nothing here converts a `sqlite3.Error`
    into "this narrator has no onboarding row", because that is
    indistinguishable from a historical narrator and would retire the
    walk for someone halfway through it. The caller must refuse the turn
    visibly; Phase 1's accepted rule is that a storage fault never makes
    an onboarding decision, and "ask it again" is one.
    """
    recovery = _turn.recover(person_id, history,
                             resolve_fn=resolve_fn, apply_fn=apply_fn)
    state = dict(recovery.state) if recovery.state else None
    plan = _turn.plan_turn(state=state, history=history,
                           narrator_text=narrator_text, eligible=eligible)
    return PreparedTurn(plan=plan, state=state, recovery=recovery)


def commit_meta(
    plan: Optional[_turn.TurnPlan],
    *,
    eligible: bool,
    cancelled: bool,
) -> Dict[str, Any]:
    """The Profile Seed keys for this turn's assistant row. Often `{}`.

    `cancelled` is RE-READ at commit time rather than inherited from
    composition, because the narrator may have stopped the turn while the
    model was generating. A presentation stamped onto a cancelled turn
    records a question that was never asked, and the response later
    matched against it would apply a disposition to an answer that does
    not exist.

    Which keys is the plan's decision alone: `PRESENT`/`RE_PRESENT` stamp
    only a presentation, `ACKNOWLEDGE` stamps only a response, `HOLD` and
    `IDLE` stamp nothing.
    """
    if plan is None or not eligible or cancelled:
        return {}
    return dict(plan.turn_meta())


def should_advance(
    plan: Optional[_turn.TurnPlan],
    *,
    persisted: bool,
    eligible: bool,
    cancelled: bool,
) -> bool:
    """Whether the post-commit apply may run.

    Four ways the answer can turn out not to exist, and every one of them
    must block the write: the plan produced no response event, the turn
    was ineligible, it was cancelled between composition and commit, or
    **persistence failed**. That last one is why this is a separate
    decision from `commit_meta`: an apply against a turn whose rows were
    never written would advance the walk past a question the narrator's
    answer to no longer exists anywhere.
    """
    return bool(persisted and eligible and not cancelled
                and plan is not None and plan.advances)


def sanitize_client_runtime(
    runtime: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Strip every server-only Profile Seed key from CLIENT input.

    ── RUN THIS BEFORE ANYTHING RESOLVES, AND UNCONDITIONALLY ──────────

    On the WebSocket path `runtime71` is the browser's own dictionary. It
    is composed into the system prompt, so anything a client puts in it
    reaches Lori unless something removes it.

    `attach_onboarding` cleans the reserved keys, but it only runs for a
    turn that HAS a resolved narrator — the production call sits inside
    `if person_id:`. An anonymous or historical turn never reached it, so
    a forged `profile_seed_onboarding` payload, or a forged attestation
    marker, survived into composition on exactly the paths with no
    narrator identity to check them against.

    This is the unconditional half of that guarantee: every turn, before
    any lookup, whatever the client sent under a reserved name is gone.
    The server then puts back only what it resolved itself.

    Returns a COPY. The caller's dict is left alone, because it is shared
    with other consumers on the same turn.
    """
    out: Dict[str, Any] = dict(runtime or {})
    for key in PROFILE_SEED_RESERVED_RUNTIME_KEYS:
        out.pop(key, None)
    return out


#: The browser's own default once identity is complete —
#: `getEffectivePass74()` returns `state.session.currentPass || "pass1"`
#: (`ui/js/app.js:5372`). Reused rather than invented so the override
#: reproduces the shipped semantics instead of introducing a new phase.
_BROWSER_DEFAULT_PASS = "pass1"

#: The browser's literal for a finished identity (`app.js:5359`).
_PHASE_COMPLETE = "complete"

#: The pass value that means "identity collection owns this turn".
_PASS_IDENTITY = "identity"

#: runtime71 keys, as `buildRuntime71()` emits them (`app.js:3030-3036`)
#: and as `chat_ws` reads them back for the trace.
EFFECTIVE_PASS_KEY = "effective_pass"
CURRENT_PASS_KEY = "current_pass"


def apply_server_identity(
    runtime: Optional[Mapping[str, Any]],
    state: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Server-resolved identity completion outranks the browser's guess.

    ── WHY THIS EXISTS — PHASE 6 BASELINE 2, MEASURED ──────────────────

    The browser decides identity completion from `state.profile.basics`:
    `hasIdentityBasics74()` (`app.js:5341`) requires name AND dob AND
    pob, and `buildRuntime71()` (`app.js:3034-3036`) ships that verdict
    as `identity_complete` / `identity_phase` / `effective_pass`.

    But `basics.fullname` and `basics.preferred` are only populated when
    the narrator SAYS their name in-session (`session-loop.js:298-301`).
    A narrator whose name is durably on file, who has not introduced
    themselves today, therefore reports identity INCOMPLETE — while the
    server's Profile Seed resolver has already resolved that same
    narrator as complete, and `_known_identity_facts_block` renders the
    name as an authoritative fact.

    The composer then sees the contradiction and resolves it the wrong
    way, because `identity_mode = (effective_pass == "identity") or (not
    identity_complete)` (`prompt_composer.py:4418`) trusts the browser.

    Measured, Ada Pruitt, Phase 6 Baseline 2 (2026-09-07): all ten
    prompts carried `KNOWN IDENTITY FACTS: - Name: Ada Pruitt` AND
    `IDENTITY MODE: ... Still needed: name, date of birth...`, with the
    effective pass reading "identity" while the current pass read
    "pass1". (Written in prose rather than as a literal assignment: the
    ownership sweep in `test_profile_seed_reachability_map` greps the
    server tree for a pass being written, and it is right to be blunt —
    a docstring that looks like an assignment should not be the thing
    that softens it.) Lori asked
    for a known identity fact on 10 of 10 turns — obeying the prompt
    exactly. The "invented significance" on the green dish was likewise
    recited: `"what a tender thing to keep"` is an exemplar inside the
    IDENTITY MODE directive (`prompt_composer.py:5066`).

    THE RULE. Browser runtime state is OBSERVATIONAL; server-derived
    narrator truth wins when they disagree. This is the same precedence
    the Guard Lab gate and the Profile Seed resolver already use.

    SCOPE, deliberately narrow. This only ever turns identity mode OFF,
    and only when the server has resolved the narrator as complete. It
    never turns it on, never edits the IDENTITY MODE collection branch,
    and returns the runtime untouched for a genuinely new or incomplete
    narrator — who must still walk name -> DOB -> birthplace exactly as
    designed.
    """
    out: Dict[str, Any] = dict(runtime or {})
    if not isinstance(state, Mapping) or not state.get("identity_complete"):
        # New or incomplete narrator, or no resolved state at all: the
        # browser's account stands and onboarding proceeds unchanged.
        return out

    out["identity_complete"] = True
    out["identity_phase"] = _PHASE_COMPLETE

    # A stale `effective_pass="identity"` alone re-activates identity
    # mode through the first disjunct, so correcting `identity_complete`
    # without this would fix nothing.
    if str(out.get(EFFECTIVE_PASS_KEY) or "").strip() == _PASS_IDENTITY:
        current = str(out.get(CURRENT_PASS_KEY) or "").strip()
        # Preserve the narrator's REAL interview pass. `current_pass`
        # was `pass1` throughout Baseline 2 while `effective_pass` was
        # overridden to `identity`, so the true pass was there all along.
        out[EFFECTIVE_PASS_KEY] = (
            current if current and current != _PASS_IDENTITY
            else _BROWSER_DEFAULT_PASS)
    return out


def attach_seed_status(
    runtime: Optional[Mapping[str, Any]],
    state: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Carry the SERVER's Profile Seed lifecycle on every turn.

    ── WHY THIS IS SEPARATE FROM `attach_onboarding` ───────────────────

    `attach_onboarding` carries the QUESTION — the payload for the topic
    being asked right now — and correctly attaches nothing when the plan
    is IDLE, stripping the reserved keys so no stale question survives.

    But "no question this turn" is not "no walk". A COMPLETED narrator
    and a HISTORICAL narrator with no onboarding row both arrive at the
    composer with no payload, and the composer needs to tell them apart:
    the historical narrator still needs the legacy ten-question block;
    the completed one must never see it again.

    Measured, Phase 6 Run 3 (2026-09-08): Ada's completed walk planned
    IDLE, the markers were stripped, and all ten prompts carried the
    legacy "PROFILE SEED QUESTIONS (ask in this order...)" list. Lori
    recited item 5 back to her as "How far did you go in school – did
    you attend college?" — her schooling being already on file.

    Called AFTER `attach_onboarding`, because that function clears the
    reserved keys and would otherwise remove this one too.

    A narrator with no resolved state gets NO key — absence is how a
    historical narrator stays byte-compatible with the legacy path.
    """
    out: Dict[str, Any] = dict(runtime or {})
    if not isinstance(state, Mapping):
        out.pop(PROFILE_SEED_STATUS_KEY, None)
        return out
    status = str(state.get("status") or "").strip()
    if status:
        out[PROFILE_SEED_STATUS_KEY] = status
    else:
        out.pop(PROFILE_SEED_STATUS_KEY, None)
    return out
