"""Operator control surface for the Lori intervention registry.

WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01 Continuation A, sections Q and R.

The backend already decides what a narrator turn receives: the registry
names 43 authorities, the store persists operator overrides, the
resolver turns those into one immutable snapshot, and the gate decides
whether that snapshot is allowed to govern anything. This router is the
only way a human reaches any of it.

WHAT THIS SURFACE IS FOR. `All Switchable Off` has been a resolver
result and a set of passing tests. It becomes an experiment the moment
an operator can select it, watch the next turn pick it up, and read back
the identity of the configuration that produced the transcript. Until
then the instrument exists and nobody can hold it.

FOUR THINGS THIS ROUTER REFUSES TO DO, each because doing it would make
the panel lie:

  ONE ROW PER ACTION IS NOT AN OPTION. `All Switchable Off` is one
  request, one transaction and ONE revision. Thirty-seven sequential
  writes would produce 37 revisions and let a narrator turn start on a
  half-applied mixture no operator ever chose — a transcript attributable
  to a configuration that never existed.

  IT NEVER COLLAPSES THE THREE STATES. Canonical default, deployment
  default, operator override and effective state are four separate
  fields on every row, with the reason that decided it. Id 2 is
  canonically ON, never overridable, and effectively PARKED; a single
  green toggle would be wrong three ways at once.

  IT NEVER REPORTS A CONFIGURATION IT DID NOT READ. The revision, both
  fingerprints and the gate readiness come from the same read that built
  the rows.

  IT CANNOT MANUFACTURE ELIGIBILITY. The narrator listing is read-only
  and has no write partner. `testing_only` is set at creation and
  nowhere else; a panel button that converted a real narrator into an
  experiment target would defeat the whole gate.

GATE, LIKE EVERY OTHER OPERATOR ROUTE. `HORNELORE_OPERATOR_GUARD_LAB=1`,
404 when off — not 403 — so an outside probe cannot distinguish "off"
from "absent". Same posture as `operator_story_review` and
`operator_eval_harness`.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from .. import db as _db
from ..services import lori_guard_authority as authority
from ..services import lori_guard_gate as gate
from ..services import lori_guard_registry as registry
from ..services import lori_guard_store as store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/operator/guard-lab", tags=["operator", "guard-lab"])


# ── Backend gate ───────────────────────────────────────────────────────────

def _guard_lab_enabled() -> bool:
    return os.getenv("HORNELORE_OPERATOR_GUARD_LAB", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _require_enabled() -> None:
    if not _guard_lab_enabled():
        raise HTTPException(status_code=404, detail="Not found")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ── Request bodies ─────────────────────────────────────────────────────────

class AuthorityChange(BaseModel):
    """One authority, one deliberate operator decision.

    `enabled` is three-valued on purpose. True selects, False excludes,
    and **null RESETS** — deleting the override so the canonical default
    resumes living in code. Writing today's default back in would freeze
    it into this installation: change the default in the registry
    afterwards and this deployment silently keeps the old one, with
    nothing on screen to explain why.

    `expected_revision` is REQUIRED. Making it optional would give the
    panel a way to skip the check by omission, which is the same as not
    having it — and the case it exists for is a second browser tab whose
    view of the configuration is minutes old.
    """

    enabled: Optional[bool] = Field(
        None, description="true select · false exclude · null reset to default")
    expected_revision: int = Field(..., ge=0)
    #: Identity only, echoed back so the response can answer the same
    #: question the card was asking. It has no bearing on the write.
    narrator_id: Optional[str] = None


class PresetRequest(BaseModel):
    """An atomic preset. One request, one transaction, one revision."""

    expected_revision: int = Field(..., ge=0)
    #: Identity only. See AuthorityChange.narrator_id.
    narrator_id: Optional[str] = None


# ── State assembly ─────────────────────────────────────────────────────────

def _open_store() -> sqlite3.Connection:
    """503, never a 500 traceback, and never a silent empty configuration.

    An unreadable store on the RUNTIME path is fail-closed to canonical
    production, because a narrator must not lose their turn to a Guard
    Lab problem (IC-9). On the OPERATOR path the opposite is true: an
    operator who is shown a page of canonical-looking rows would believe
    that is the live configuration. Saying so is the only honest answer.
    """
    try:
        return _db._connect()
    except Exception:
        logger.exception("[guard-lab][api] could not open the override store")
        raise HTTPException(
            status_code=503,
            detail="guard lab store unavailable — the configuration on "
                   "screen would not be the live one")


def _row(state: authority.AuthorityState,
         item: registry.Intervention,
         deployment: Dict[int, bool]) -> Dict[str, Any]:
    """One authority as the panel must render it.

    The four state fields travel separately and are never merged. So
    does the POLICY, because "cannot, for safety" and "cannot, until
    somebody splits a string" are different truths and an operator
    staring at a disabled row deserves to know which one they have.
    """
    return {
        "id": state.id,
        "name": state.name,
        "display": state.display,
        "cls": state.cls,
        "position": state.position,
        "policy": state.policy,
        "switchable": state.policy == registry.POLICY_SWITCHABLE,
        "counterfactual": state.counterfactual,

        # The four-part truth. Collapsing any two of these is the defect
        # this shape exists to prevent.
        "canonical_default": state.canonical_default,
        "deployment_default": deployment.get(state.id),
        "operator_override": state.operator_override,
        "effective": state.effective,
        "reason": state.reason,
        "differs_from_canonical": state.differs_from_canonical,

        # Documentation. Never fingerprinted, and the reason an operator
        # can judge an authority instead of just toggling a number.
        "purpose": item.purpose,
        "motivating_failure": item.motivating_failure,
        "known_harm": item.known_harm,
        "policy_reason": item.policy_reason,
        "location": item.location,
        "trace_stage": item.trace_stage,
    }


def _gate_readiness() -> Dict[str, Any]:
    """Whether the selected configuration can actually reach a turn.

    WITHOUT THIS THE PANEL IS A TRAP. An operator can select `All
    Switchable Off`, see 37 excluded rows, start talking to Lori and
    receive canonical production — because no evaluation is armed, or
    the trace is not recording, or the narrator is not testing-only. The
    gate refused silently and correctly; the panel looked broken. Every
    one of the four conditions is therefore reported by name.

    Each probe is independently fail-safe: a probe that raises reports
    its condition as unmet rather than costing the operator the page.
    """
    eval_dir = None
    try:
        eval_dir = gate.armed_eval_dir()
    except Exception:
        logger.exception("[guard-lab][api] eval marker probe failed")

    recording = False
    try:
        from ..services import lori_response_trace as _rt
        recording = bool(_rt.enabled())
    except Exception:
        logger.exception("[guard-lab][api] trace probe failed")

    try:
        narrators = _db.list_testing_only_people()
    except Exception:
        logger.exception("[guard-lab][api] testing-only listing failed")
        narrators = []

    return {
        "experiment_armed": bool(eval_dir),
        "eval_dir": eval_dir,
        "trace_recording": recording,
        "testing_only_narrators": [
            {"id": n.get("id"), "display_name": n.get("display_name")}
            for n in narrators
        ],
        # Deliberately derived here rather than restated in the panel:
        # two copies of one rule is how they drift.
        "can_apply_to_a_turn": bool(eval_dir) and recording and bool(narrators),
        "conditions": [
            {"name": "armed_evaluation", "met": bool(eval_dir),
             "detail": eval_dir or "no marker at .runtime/eval/current_eval_dir"},
            {"name": "trace_recording", "met": recording,
             "detail": "HORNELORE_RESPONSE_TRACE resolves only when a "
                       "process STARTS — arming mid-run leaves it off"},
            {"name": "testing_only_narrator", "met": bool(narrators),
             "detail": f"{len(narrators)} eligible narrator(s)"},
            {"name": "real_narrators_never_eligible", "met": True,
             "detail": "an ordinary narrator receives canonical Lori "
                       "whatever is selected here"},
        ],
    }


# ── Configuration classification ───────────────────────────────────────────

CONFIG_DEFAULTS = "defaults"
CONFIG_LEAN = "lean"
CONFIG_CUSTOM = "custom"


def _configuration(overrides: Dict[int, bool]) -> Dict[str, Any]:
    """Name the configuration ON THE SERVER, from the overrides it just read.

    The Operator card shows one word — Defaults, Lean, or Custom — and
    that word must not be computed in the browser. A page that decided
    'this looks like the lean baseline' by counting 43 rows would be a
    second implementation of a rule the server already owns, and the two
    would disagree the first time the registry changed.

    `lean` is deliberately EXACT, not 'mostly off': every switchable
    authority present, every one excluded. An operator who turned one
    back on is in a CUSTOM configuration and needs to be told so —
    calling that lean is how a comparison gets attributed to the wrong
    selection.
    """
    switchable_ids = {item.id for item in registry.switchable()}
    if not overrides:
        return {"id": CONFIG_DEFAULTS, "label": "Defaults",
                "detail": "no operator override; the registry and any "
                          "deployment defaults decide every authority"}
    if (set(overrides) == switchable_ids
            and all(value is False for value in overrides.values())):
        return {"id": CONFIG_LEAN, "label": "Lean (All Switchable Off)",
                "detail": f"all {len(switchable_ids)} switchable authorities "
                          f"excluded; protected authorities unchanged"}
    return {"id": CONFIG_CUSTOM, "label": "Custom",
            "detail": f"{len(overrides)} operator override(s) of "
                      f"{len(switchable_ids)} switchable authorities"}


# ── Current-narrator eligibility ───────────────────────────────────────────

ELIGIBLE = "eligible"
NO_NARRATOR_SELECTED = "no_narrator_selected"
NARRATOR_NOT_FOUND = "narrator_not_found"
NOT_TESTING_ONLY = "not_testing_only"
EVAL_NOT_ARMED = "eval_not_armed"
TRACE_NOT_RECORDING = "trace_not_recording"

VALID_ELIGIBILITY_REASONS = frozenset({
    ELIGIBLE, NO_NARRATOR_SELECTED, NARRATOR_NOT_FOUND, NOT_TESTING_ONLY,
    EVAL_NOT_ARMED, TRACE_NOT_RECORDING,
})


def _current_narrator(narrator_id: Optional[str],
                      gate_info: Dict[str, Any]) -> Dict[str, Any]:
    """Can the configuration reach THE NARRATOR BEING INTERVIEWED?

    THE GAP THIS CLOSES, found during the live acceptance. `/state`
    could say an eligible narrator EXISTS; it could not say whether the
    person on the other side of the microphone was that narrator. So an
    operator could select a lean baseline, talk to an ordinary narrator,
    receive canonical Lori, and have nothing on screen explain it.

    THE BROWSER SUPPLIES IDENTITY ONLY. It says which narrator is
    selected; the server looks up the durable row and returns the
    verdict. A stale or hostile `narrator_id` cannot manufacture
    `testing_only` — that is read from the people table by
    `person_is_testing_only`, which is fail-closed, and IC-7 is the
    contract being kept here. Deciding this in JavaScript by testing
    whether an id appears in a list would put eligibility on the wire
    where a browser could arrange the answer.

    Reasons are ordered most-specific first, so the card can say the one
    thing the operator has to fix rather than a list of everything.
    """
    requested = (narrator_id or "").strip()
    out: Dict[str, Any] = {
        "requested_id": requested or None,
        "exists": False,
        "display_name": None,
        "testing_only": False,
        "can_receive_experiment": False,
        "reason": NO_NARRATOR_SELECTED,
    }
    if not requested:
        out["message"] = ("No narrator is selected, so nothing here can "
                          "reach a session.")
        return out

    try:
        person = _db.get_person(requested)
    except Exception:
        logger.exception(
            "[guard-lab][api] narrator lookup failed for %r", requested)
        person = None

    if not person:
        out["reason"] = NARRATOR_NOT_FOUND
        out["message"] = "That narrator id does not resolve to a person."
        return out

    out["exists"] = True
    # SERVER-DERIVED. Not the display name the browser sent — this
    # surface must not be paintable from the client side.
    out["display_name"] = person.get("display_name")

    try:
        is_testing = bool(_db.person_is_testing_only(requested))
    except Exception:
        logger.exception(
            "[guard-lab][api] testing_only probe failed for %r", requested)
        is_testing = False
    out["testing_only"] = is_testing

    if not is_testing:
        out["reason"] = NOT_TESTING_ONLY
        out["message"] = (
            f"{person.get('display_name') or 'This narrator'} is an ordinary "
            f"narrator. Experimental selections will NOT affect this "
            f"session — Lori runs canonically for them whatever is selected "
            f"here.")
        return out

    if not gate_info.get("experiment_armed"):
        out["reason"] = EVAL_NOT_ARMED
        out["message"] = ("This narrator is eligible, but no evaluation is "
                          "armed, so turns still run canonically.")
        return out

    if not gate_info.get("trace_recording"):
        out["reason"] = TRACE_NOT_RECORDING
        out["message"] = (
            "This narrator is eligible and an evaluation is armed, but the "
            "response trace is not recording — an unmeasured experimental "
            "turn is refused. Tracing resolves when a process STARTS.")
        return out

    out["can_receive_experiment"] = True
    out["reason"] = ELIGIBLE
    out["message"] = (
        f"{person.get('display_name') or 'This narrator'} will receive the "
        f"selected configuration on their next turn.")
    return out


def _state_payload(con: sqlite3.Connection,
                   narrator_id: Optional[str] = None) -> Dict[str, Any]:
    """The whole truthful configuration, from ONE coherent read.

    `read_state` is a single statement precisely so the overrides and
    the revision cannot be torn apart by a concurrent write, and this
    payload inherits that: the fingerprints below describe the same
    generation the rows do.
    """
    try:
        overrides, revision = store.read_state(con)
    except Exception:
        logger.exception("[guard-lab][api] override store unreadable")
        raise HTTPException(
            status_code=503, detail="guard lab configuration unreadable")

    deployment = gate.deployment_defaults()
    snapshot = authority.resolve(
        overrides, revision=revision, deployment_defaults=deployment)

    by_id = {item.id: item for item in registry.REGISTRY}
    rows = [_row(s, by_id[s.id], deployment) for s in snapshot.states]
    gate_info = _gate_readiness()

    return {
        # Server-owned, so the compact Operator card and the 43-row panel
        # cannot disagree about what configuration is running.
        "configuration": _configuration(dict(overrides)),
        "current_narrator": _current_narrator(narrator_id, gate_info),
        # The generation an experimental turn taken RIGHT NOW would
        # consume, and the token every write must echo back.
        "revision": revision,
        "registry_fingerprint": snapshot.registry_fingerprint,
        "selection_fingerprint": snapshot.selection_fingerprint,
        "authorities": rows,
        "counts": {
            "total": len(rows),
            "selected": len(snapshot.selected),
            "excluded": len(snapshot.excluded),
            "policy": registry.policy_counts(),
        },
        # `All Switchable Off` cannot be described without qualification
        # while this is non-empty: a pending-seam authority stays RUNNING
        # through the preset, and a button claiming otherwise would be
        # false. Empty today; reported anyway so it cannot go quietly
        # non-empty again.
        "pending_seam": [
            {"id": i.id, "display": i.display, "policy_reason": i.policy_reason}
            for i in registry.pending_seam()
        ],
        "gate": gate_info,
        # THE SEMANTICS, ON THE WIRE. A change takes effect on the NEXT
        # turn; a turn already in flight keeps the snapshot it acquired
        # (IC-10). The panel renders this string rather than composing
        # its own wording, so the promise the operator reads is the one
        # the server actually keeps.
        "applies": "next_turn",
        "applies_note": (
            "Changes take effect on the NEXT narrator turn. A turn "
            "already generating keeps the configuration it acquired — no "
            "restart and no page reload are required, and a mid-turn "
            "change can never reach a response already in flight."),
        "fetched_at": _now_iso(),
    }


def _conflict(exc: store.StaleRevisionError,
              con: sqlite3.Connection,
              narrator_id: Optional[str] = None) -> HTTPException:
    """409 carrying the CURRENT state, not just a complaint.

    An operator whose write is refused needs to see what is live now, in
    the same response — otherwise resolving the conflict means a manual
    refresh and a guess about what changed.
    """
    try:
        current = _state_payload(con, narrator_id)
    except HTTPException:
        current = None
    return HTTPException(status_code=409, detail={
        "error": "stale_revision",
        "message": str(exc),
        "expected_revision": exc.expected,
        "current_revision": exc.actual,
        "current": current,
    })


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/state")
def api_guard_lab_state(
    narrator_id: Optional[str] = Query(
        None,
        description="The narrator currently selected in the interview. "
                    "Identity ONLY — the server resolves eligibility from "
                    "the durable person row and never trusts this for "
                    "testing_only."),
) -> Dict[str, Any]:
    """Every registered authority, truthfully, with the identity to cite."""
    _require_enabled()
    con = _open_store()
    try:
        return _state_payload(con, narrator_id)
    finally:
        try:
            con.close()
        except Exception:
            pass


@router.post("/authorities/{authority_id}")
def api_guard_lab_set_authority(
    authority_id: int,
    change: AuthorityChange = Body(...),
) -> Dict[str, Any]:
    """Select, exclude or reset ONE authority.

    404 for an id that is not registered. 400 for one the operator may
    not change, carrying the policy reason — a PROTECTED refusal is a
    statement about the authority, not a permissions failure, and the
    operator should be told which it is. 409 for a stale revision.
    """
    _require_enabled()
    item = registry.by_id(int(authority_id))
    if item is None:
        raise HTTPException(status_code=404, detail="no such authority")

    con = _open_store()
    try:
        try:
            store.apply_changes(
                con, {int(authority_id): change.enabled},
                expected_revision=change.expected_revision)
        except store.StaleRevisionError as exc:
            raise _conflict(exc, con, change.narrator_id)
        except store.NotSwitchableError as exc:
            raise HTTPException(status_code=400, detail={
                "error": "not_switchable",
                "authority_id": int(authority_id),
                "policy": item.policy,
                "message": str(exc),
            })
        return _state_payload(con, change.narrator_id)
    finally:
        try:
            con.close()
        except Exception:
            pass


@router.post("/all-switchable-off")
def api_guard_lab_all_switchable_off(
    request: PresetRequest = Body(...),
) -> Dict[str, Any]:
    """The lean baseline, in ONE revision.

    Not 37 requests and not 37 revisions. Protected authorities are
    untouched and keep behaving as their protected state dictates, which
    is exactly what the label claims and no more.
    """
    _require_enabled()
    con = _open_store()
    try:
        try:
            store.all_switchable_off(
                con, expected_revision=request.expected_revision)
        except store.StaleRevisionError as exc:
            raise _conflict(exc, con, request.narrator_id)
        payload = _state_payload(con, request.narrator_id)
        logger.info(
            "[guard-lab][api] all switchable off — revision=%s selection=%s",
            payload["revision"], payload["selection_fingerprint"][:12])
        return payload
    finally:
        try:
            con.close()
        except Exception:
            pass


@router.post("/restore-defaults")
def api_guard_lab_restore_defaults(
    request: PresetRequest = Body(...),
) -> Dict[str, Any]:
    """Delete every override so the code-side defaults resume.

    A DELETE, not a write-back of today's values — see the reset
    reasoning in `lori_guard_store`. Also one revision.
    """
    _require_enabled()
    con = _open_store()
    try:
        try:
            store.restore_canonical_defaults(
                con, expected_revision=request.expected_revision)
        except store.StaleRevisionError as exc:
            raise _conflict(exc, con, request.narrator_id)
        payload = _state_payload(con, request.narrator_id)
        logger.info(
            "[guard-lab][api] restored canonical defaults — revision=%s",
            payload["revision"])
        return payload
    finally:
        try:
            con.close()
        except Exception:
            pass


@router.get("/narrators")
def api_guard_lab_narrators() -> Dict[str, Any]:
    """The narrators an experiment may reach. READ ONLY.

    There is no companion write route and there must not be one. A real
    narrator cannot be converted into an experiment target from this
    panel, from a PATCH, or from anything a browser can send.
    """
    _require_enabled()
    try:
        people: List[Dict[str, Any]] = _db.list_testing_only_people()
    except Exception:
        logger.exception("[guard-lab][api] testing-only listing failed")
        raise HTTPException(
            status_code=503, detail="narrator listing unavailable")
    return {
        "items": [
            {
                "id": p.get("id"),
                "display_name": p.get("display_name"),
                "narrator_type": p.get("narrator_type"),
                "created_at": p.get("created_at"),
            }
            for p in people
        ],
        "count": len(people),
        "note": "testing_only is set at narrator creation and is not "
                "editable from any operator surface.",
        "fetched_at": _now_iso(),
    }
