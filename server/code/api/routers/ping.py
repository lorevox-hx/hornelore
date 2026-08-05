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
