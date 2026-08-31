from typing import Any, Dict

from fastapi import APIRouter

from .. import flags

router = APIRouter(prefix="/api", tags=["ping"])

@router.get("/ping")
def ping():
    return {"ok": True}

# WO-10K: Add /api/health so both API and TTS have consistent health endpoints.
# Bug Panel and diagnostics can use the same path for both services.
@router.get("/health")
def health():
    return {"ok": True, "service": "api"}


# ── WO-LEAN-LORI-RUNTIME-01 Phase 3B ──────────────────────────────────
# The browser is TOLD the safety state; it is not trusted to work it out.
#
# Parking safety has to hold in three places at once -- the prompt, the
# server, and the browser -- and only the server reads the environment.
# Before this endpoint the browser had its own copy of the safety
# patterns and its own latch, so a parked deployment would still arm a
# safety posture in the UI and still append a [SAFETY MODE: ACTIVE]
# directive to the outgoing turn: a posture with nothing behind it, and
# a directive pointing at instructions the parked prompt no longer
# carries. That is precisely the false impression the decision removes.
#
# Deliberately NOT a general feature-flag dump. Handing the browser the
# whole flag table would make every future server-side default part of
# the client contract. This answers one question.
@router.get("/runtime-posture")
def runtime_posture() -> Dict[str, Any]:
    parked = flags.safety_parked()
    return {
        "ok": True,
        "safety": {
            "state": flags.safety_state(),
            "parked": parked,
            # Stated in the payload rather than left to a comment,
            # because the browser is not the only future reader of this
            # endpoint and the claim matters more than the boolean.
            "emergency_monitoring": False,
        },
    }


# ── WO-LORI-LISTEN-AND-RETAIN-01 ──────────────────────────────────────
# Read-only trace status for the evaluation harness preflight.
#
# The harness previously probed a route that did not exist, and on the
# resulting failure fell back to accepting the mere presence of a trace
# DIRECTORY. A stale directory from an earlier day therefore satisfied
# preflight while this process had tracing switched off, and the run
# could reach PASS with zero raw-response evidence in it.
#
# `enabled` here is the live value read by the API process that will
# actually write the traces. Deliberately reports state only: it cannot
# turn tracing on, and it exposes no narrator content.
@router.get("/health/response-trace")
def response_trace_health() -> Dict[str, Any]:
    try:
        from ..services import lori_response_trace as rt
        payload = rt.health()
        payload["ok"] = True
        return payload
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "enabled": False, "error": str(exc)}
