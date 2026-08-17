from __future__ import annotations

import asyncio
import gc
import json
import logging
import os
import threading
import uuid  # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 §3.3 — per-socket conv ids
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
_LV_DEBUG = os.getenv("LV_DEV_MODE", "0") in ("1", "true", "True")

# ── WO-10M: Token cap + VRAM guard configuration ───────────────────────────
# Pulled from env so the launcher can tune without code edits. The chat cap
# is the default floor when the UI does not pass an explicit max_new_tokens
# in params. WO-10M post-fix: default 256 (was 512) to start conservative
# under full Hornelore + Whisper co-residency; raise only after stability
# is proven green.
_WO10M_CHAT_CAP = int(os.getenv("MAX_NEW_TOKENS_CHAT", os.getenv("MAX_NEW_TOKENS", "256")))
_WO10M_CHAT_CAP_HARD = int(os.getenv("MAX_NEW_TOKENS_CHAT_HARD", "1024"))  # absolute ceiling
_WO10M_GUARD_ENABLED = os.getenv("VRAM_GUARD_ENABLED", "1") in ("1", "true", "True")
_WO10M_GUARD_BASE_MB = float(os.getenv("VRAM_GUARD_BASE_MB", "600"))
_WO10M_GUARD_PER_TOKEN_MB = float(os.getenv("VRAM_GUARD_PER_TOKEN_MB", "0.14"))

# ── WO-QA-01: tunable repetition_penalty ──────────────────────────────────
# Default 1.1 preserves prior hardcoded behavior. Env override lets the
# operator shift the production default without a code change. The harness
# (WO-QA-01) additionally passes repetition_penalty per-request via
# params, so individual config cells can sweep this knob.
_REP_PENALTY_DEFAULT = float(os.getenv("REPETITION_PENALTY_DEFAULT", "1.1"))

# WO-LORI-SAFETY-LLM-CLASSIFIER-01 (2026-06-14) — per-session counter
# of LLM safety-classifier parse failures (post retry-once). Operator-
# panel signal that the LLM is producing malformed JSON for this
# conversation; frequent increments mean the prompt or the model
# needs attention. In-memory only, cleared on stack restart — fine
# for a debug counter; not a durability concern. Read via
# get_safety_llm_parse_failures(conv_id) below.
_SAFETY_LLM_PARSE_FAILURES: Dict[str, int] = {}


def get_safety_llm_parse_failures(conv_id: str) -> int:
    """Return the current parse-failure count for `conv_id`. Operator
    panels and the safety bug-panel surface read through this. Returns
    0 when the conv has had no failures (or doesn't exist)."""
    return int(_SAFETY_LLM_PARSE_FAILURES.get(conv_id or "", 0))


def reset_safety_llm_parse_failures(conv_id: str) -> None:
    """Clear the counter for `conv_id`. Operator action — typically
    called after the operator has acknowledged the parse-failure
    signal in the Bug Panel."""
    _SAFETY_LLM_PARSE_FAILURES.pop(conv_id or "", None)


# WO-LORI-SOFTENED-MODE-PERSISTENCE-01 (2026-06-14) — per-trigger N
# values for the softened window. Defaults per WO §3:
#   acute       = 5 turns (covers acknowledgment + recovery arc)
#   past_tense  = 2 turns (narrator already moved material into past
#                          tense; longer would be patronizing)
# Both env-tunable. Setting to 0 disables softened for that trigger
# (dev only — production must not run with 0).
def softened_n_acute() -> int:
    """Read HORNELORE_SOFTENED_N_ACUTE; default 5; clamped 0..20."""
    try:
        n = int(os.getenv("HORNELORE_SOFTENED_N_ACUTE", "5"))
    except (TypeError, ValueError):
        n = 5
    return max(0, min(20, n))


def softened_n_past_tense() -> int:
    """Read HORNELORE_SOFTENED_N_PAST_TENSE; default 2; clamped 0..20."""
    try:
        n = int(os.getenv("HORNELORE_SOFTENED_N_PAST_TENSE", "2"))
    except (TypeError, ValueError):
        n = 2
    return max(0, min(20, n))


def _softened_write(
    conv_id: str,
    current_turn: int,
    n_turns: int,
    trigger: str,
    existing_state: Optional[Dict[str, Any]] = None,
) -> None:
    """WO-LORI-SOFTENED-MODE-PERSISTENCE-01 — unified softened-write
    helper used by both the acute path and the past-tense path.

    Picks `set_session_softened` (fresh entry) or `extend_session_
    softened` (max-not-clobber) based on whether the session is
    already in softened state. The nested-trigger case must NEVER
    shorten the existing window — an acute that fires during a
    past-tense softened window extends to max(existing, current+5),
    NOT clobber to current+5 (which could be SHORTER if the past-
    tense window had already extended out).

    `existing_state` is the dict from get_session_softened_state();
    None means caller didn't read it (we treat as "not in softened").
    """
    is_already_softened = bool(
        isinstance(existing_state, dict)
        and existing_state.get("interview_softened")
    )
    try:
        if is_already_softened:
            extend_session_softened(
                conv_id, current_turn,
                softened_turns=n_turns, trigger=trigger,
            )
        else:
            set_session_softened(
                conv_id, current_turn,
                softened_turns=n_turns, trigger=trigger,
            )
    except Exception as _sw_exc:
        logger.warning(
            "[chat_ws][softened] write failed conv=%s trigger=%s n=%d: %s",
            conv_id, trigger, n_turns, _sw_exc,
        )


from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from transformers import TextIteratorStreamer, StoppingCriteriaList

from ..db import (
    export_turns,
    persist_turn_transaction,
    clear_turns,
    save_segment_flag,
    increment_session_turn,
    set_session_softened,
    extend_session_softened,  # WO-LORI-SOFTENED-MODE-PERSISTENCE-01 — max-not-clobber on nested triggers
    ensure_interview_session,  # BUG-DBLOCK-01 PATCH 3
    get_session_softened_state,  # WO-LORI-SOFTENED-RESPONSE-01
)
import torch
from ..api import (_load_model, _apply_chat_template, StopOnEvent,
                   _normalize_role, MAX_CHAT_PROMPT_TOKENS)
from ..services.prompt_budget import fit_chat_messages
from ..db import turn_is_system_directive as _turn_is_system_directive
from ..prompt_composer import compose_system_prompt

# BUG-GUARDS-DEAD-ON-PY311-INLINE-FLAG-01 (2026-07-14) — FAIL LOUD, AT BOOT.
#
# The response guards used to be imported INSIDE the per-turn try/except whose
# stated job is "never break a turn on guard failure". That is right for a
# transient runtime error. It is catastrophically wrong for an ImportError: a
# guards module that cannot even load means the narrator has NO protection at
# all, and the except turned that into a WARNING line nobody read.
#
# It happened. A stray inline (?i) mid-pattern is a DeprecationWarning on py3.10
# and a hard re.error on py3.11+. The server runs 3.12, so the module blew up at
# import and EVERY guard — narrator_echo, meta_response_leak,
# dangling_determiner, language_drift, the "I can see" block — was silently off
# in production, on every turn, while its unit tests passed on 3.10.
#
# Importing at module scope makes that failure mode impossible to hide: if the
# guards cannot load, the server does not start. A stack that refuses to boot is
# strictly better than a stack that quietly talks to an 86-year-old with every
# protection disabled.
from ..services.lori_response_guards import (
    apply_response_guards as _APPLY_RESPONSE_GUARDS,
    # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 §3.1 — the guard-
    # wrapper FAIL-CLOSED fallback. Imported at module scope, like the
    # guards themselves, so the fallback path can never hit a lazy-import
    # failure inside the exception handler it serves.
    compose_guard_failure_fallback as _COMPOSE_GUARD_FAILURE_FALLBACK,
)
from ..archive import (
    ensure_session as archive_ensure_session,
    append_event as archive_append_event,
    rebuild_txt as archive_rebuild_txt,
)
# WO-LORI-SAFETY-INTEGRATION-01 Phase 1 — chat-path safety hook.
# Mirrors interview.py:269-307 pattern. scan_answer() is the existing
# pattern detector (50+ regexes, 7 categories, 0.70 threshold, false-positive
# guards). Phase 1 wires it; Phases 2-4 layer LLM second-layer + operator
# surface + warm-first prompt block on top.
from ..safety import (
    scan_answer,
    build_segment_flags,
    get_resources_for_category,
    set_softened,
    SafetyResult,  # 2026-07-11 repo-review HIGH fix — synthesized at
                   # L1784 when the LLM classifier catches indirect
                   # ideation the pattern layer missed. Missing this
                   # import silently no-oped SAFETY-INTEGRATION-01
                   # Phase 2 on every trigger via the wrapping
                   # `except Exception` at L1968.
)

router = APIRouter(prefix="/api/chat", tags=["chat-ws"])


# ── BUG-LORI-SESSION-LANGUAGE-CONTRACT-01 — Layer 1 emergency lock ──────
#
# IMPORTANT: this is an EMERGENCY SAFETY BELT, not the product design.
#
# The product design is Layer 2 — profile_json.session_language_mode +
# session_start.language_mode. This UUID set exists only because:
#
#   - the harness uses a hardcoded UUID (4aa0cc2b…) that may not have
#     a profile_json row when the test fires, and
#   - Kent's morning session needs an irrevocable Spanish-block while
#     we trial the patience layer.
#
# When a narrator's profile_json carries session_language_mode, that
# pin is the contract. This set is consulted only as a fallback for
# narrators whose profile pin is missing OR for known-fragile
# emergency narrators where the operator wants a code-level guarantee.
#
# REMOVAL CRITERIA: once profile-based session_language_mode has been
# proven across a full Kent + Janice session and the operator UI for
# pinning is wired into Bug Panel, this constant should be reduced to
# the empty set or deleted. Do not let it become the product design.
#
# TODO(REMOVE-EMERGENCY-ENGLISH-LOCK):
# Remove this hardcoded narrator UUID set once session_language_mode is
# persisted, selected at session start, and enforced through LLM,
# witness fallback, validator repair, and TTS. Do NOT add more narrator
# IDs to this set unless there is an explicit emergency note + dated
# removal commitment recorded alongside the entry.
#
# Current entries (audited 2026-05-10):
#   - 4aa0cc2b-1f27-433a-9152-203bb1f69a55 — Kent harness UUID. Locks
#     against looks_spanish overfire on "fiancée" + "Once" /
#     "attaché" + "son" trip-tokens that produced Capté/Tú/¿Qué
#     Spanglish on Kent's English interview before the contract
#     landed.
_EMERGENCY_ENGLISH_LOCK_PERSON_IDS: frozenset = frozenset({
    "4aa0cc2b-1f27-433a-9152-203bb1f69a55",  # Kent harness UUID
})


async def _ws_send(ws: WebSocket, obj: Dict[str, Any]) -> None:
    try:
        await ws.send_text(json.dumps(obj, ensure_ascii=False))
    except Exception:
        pass


async def _finalize_deterministic_turn(
    ws: WebSocket,
    *,
    params: Dict[str, Any],
    conv_id: str,
    person_id: Optional[str],
    user_text: str,
    assistant_text: str,
    turn_mode: str,
    model_name: str,
    meta: Optional[Dict[str, Any]] = None,
    current_era: Optional[str] = None,
    done_extra: Optional[Dict[str, Any]] = None,
    archive: bool = True,
) -> None:
    """Finish a server-resolved deterministic turn: persist, archive, deliver.

    WO-LEAN-LORI-RUNTIME-01 Phase 1A, 2026-08-04. Six branches
    (floor_hold, meta_question, witness, memory_echo, age_recall,
    correction) each answered the narrator, persisted the turn and
    returned. Only `meta_question` wrote the assistant archive event, and
    only because BUG-DETERMINISTIC-TURN-ARCHIVE-MISSING-01 repaired it on
    2026-08-01. The USER archive event is written unconditionally ~1,500
    lines above (`chat_ws.py:1888`), so on the other five the exported
    transcript showed the narrator speaking and Lori silent. That
    asymmetry is why it stayed invisible: the export reads as an
    unanswered turn rather than as a missing write.

    THE FLAGS ARE THE WHOLE SAFETY PROPERTY OF THIS FUNCTION, so it is
    worth saying plainly why it exists at all rather than five inline
    copies. Under LLR-22 the completed-turn hooks are NOT held out by
    their mode gates: the dispatcher resolves the deterministic mode into
    a LOCAL `turn_mode` and never writes it back, the only three writes to
    `params["turn_mode"]` (`:5480`, `:1247`, `:2909`) all yield
    "interview", both hooks read the mode from **params** (`:648`, `:836`),
    and both eligibility sets are `frozenset({"interview"})`. So both mode
    gates PASS on a deterministic turn. A branch's `return` does not skip
    them either -- `_generate_and_stream_body` is awaited at `:481` and the
    hooks run at `:490`/`:502` immediately after a normal return.

    What actually holds the hooks out is the ABSENCE of three keys:
    `_persisted_turn_row_id`, `_persisted_user_turn_row_id` and
    `_archive_event_persisted`. Five branches each independently
    remembering not to set them is a guarantee that survives exactly
    until the next person adds a sixth branch by copying a fifth. Here it
    is structural: this function never captures `row_ids_out` and never
    writes those keys, and one test asserts that over this function's own
    AST. Deterministic turns therefore stay extraction-ineligible and
    trip-placement-ineligible, per R3 Phase 1A, and they will stay that
    way without anyone having to remember.

    Do NOT add row-id plumbing here to "complete" it. Reinstating those
    keys fires an extraction generation and a trip conversation link
    against Lori's own deterministic answer -- which is precisely what the
    first cut of the meta_question repair did on 2026-08-01 and what the
    2026-08-03 correction removed. That contract changes only when the
    effective-mode handoff is repaired and a deliberate decision is made
    about which deterministic modes are extraction-eligible.

    `archive=False` is offered for a branch whose reply must not enter the
    life story. No branch passes it today; it exists so that decision can
    be made per branch, as R3 requires, rather than by editing this body.
    """
    turn_meta: Dict[str, Any] = {"ws": True, "turn_mode": turn_mode}
    if meta:
        turn_meta.update(meta)

    # ONE user turn and ONE assistant turn. No `row_ids_out` -- see above.
    # WO-SYSTEM-DIRECTIVE-PERSISTENCE-01 Phase 1 (2026-08-09). The
    # classification was already made at `:1247` and carried in `params`
    # at `:1263` -- it is passed on rather than re-derived, because the
    # point of the work order is that authorship is decided once.
    # WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 R2.3 (2026-08-16):
    # `person_id` is already a parameter of this function and is already
    # passed to the archive write below. It is passed to the DB row too,
    # so the two stop disagreeing about who spoke.
    persist_turn_transaction(
        conv_id=conv_id,
        user_message=user_text,
        assistant_message=assistant_text,
        model_name=model_name,
        meta=turn_meta,
        is_system_directive=bool(params.get("_is_system_directive")),
        person_id=person_id,
    )

    # The modal-surface gate is RECOMPUTED here rather than inherited.
    # The user-turn gate sits ~1,500 lines up and an early return can
    # leave its binding unreached, which would NameError the archive write
    # for every narrator (BUG-MODAL-TURNS-ARCHIVED-AS-LIFE-STORY-01: an
    # operator's workspace question came back to the narrator as their own
    # words, so a modal reply must never land in the life story).
    _skip_modal_archive = (
        (params.get("surface") or "narrator").strip().lower()
        == "travel_doc_modal")

    if archive and person_id and not _skip_modal_archive:
        try:
            archive_append_event(
                person_id=person_id,
                session_id=conv_id,
                role="assistant",
                content=assistant_text,
                meta={"ws": True, "turn_mode": turn_mode},
                current_era=current_era,
            )
            # Rebuild only AFTER a successful append, so a failed append
            # cannot rewrite the transcript to assert the turn is absent.
            archive_rebuild_txt(person_id=person_id, session_id=conv_id)
        except Exception as _arch_err:
            # Never raise into the chat path. Losing the archive event
            # costs a transcript line; raising costs the narrator's turn.
            logger.error(
                "[chat_ws][deterministic-finalize] archive write failed "
                "mode=%s conv=%s — %s", turn_mode, conv_id, _arch_err)

    # Delivered AFTER the writes, so a persistence failure cannot leave the
    # narrator looking at an answer the system has no record of.
    await _ws_send(ws, {"type": "token", "delta": assistant_text})
    done: Dict[str, Any] = {
        "type": "done",
        "final_text": assistant_text,
        "turn_mode": turn_mode,
    }
    if done_extra:
        done.update(done_extra)
    await _ws_send(ws, done)


async def _safety_notify_operator(
    *,
    conv_id: str,
    category: Optional[str],
    confidence: float,
    matched_phrase: Optional[str],
    turn_excerpt: str,
    person_id: Optional[str] = None,
) -> None:
    """WO-LORI-SAFETY-INTEGRATION-01 Phase 3 — operator notification.

    Persists each safety trigger to the safety_events table so the
    operator's Bug Panel banner / between-session digest can surface
    them. Always logs to api.log too (the existing grep audit trail
    stays intact). Persistence failure is logged but never raised — a
    chat turn must complete even if the operator surface DB write fails.

    Per the spec: this surface is operator-only. NEVER narrator-visible,
    no scores, no severity, no trends. The DB row carries category +
    matched_phrase + 200-char excerpt — enough context for the operator
    to assess "should I check on the narrator?" without leaking signal
    back to the narrator session.
    """
    logger.warning(
        "[chat_ws][safety][notify] conv=%s person=%s category=%s confidence=%.2f matched=%r excerpt=%r",
        conv_id,
        person_id or "(none)",
        category or "?",
        confidence,
        (matched_phrase or "")[:60],
        (turn_excerpt or "")[:200],
    )
    try:
        from ..db import save_safety_event
        event_id = save_safety_event(
            session_id=conv_id,
            person_id=person_id,
            category=category or "",
            matched_phrase=matched_phrase,
            turn_excerpt=turn_excerpt,
        )
        logger.info("[chat_ws][safety][persist] event_id=%s conv=%s", event_id, conv_id)
    except Exception as _persist_exc:
        logger.error("[chat_ws][safety][persist] save_safety_event failed: %s", _persist_exc)


# WO-TRIP-LORI-ANSWER-CAPTURE-01 Step 2 (2026-07-08): per-conversation memory
# for trip story capture. _TRIP_PREV_LORI[conv_id] records whether the Lori
# turn we just composed was trip-scoped, so the NEXT narrator answer can be
# captured as a candidate Travel Doc note. _TRIP_LAST_CAPTURE[conv_id] holds
# the most recent capture result for operator visibility (logs / Bug Panel).
# Overwritten each turn; one entry per active conversation. Not a hidden
# global — every read/write is logged under [chat_ws][trip-story-capture].
_TRIP_PREV_LORI: Dict[str, Dict[str, Any]] = {}
_TRIP_LAST_CAPTURE: Dict[str, Dict[str, Any]] = {}

# These two caches are keyed by conv_id and, before this, were never evicted —
# one entry per conversation, forever, so a long-running server leaked memory
# across a day of narrator sessions. Cap them with oldest-first eviction (dicts
# are insertion-ordered on py3.7+). 500 conversations of headroom is plenty for
# the active-capture window; anything older has already been persisted.
_TRIP_CONV_CACHE_CAP = 500


def _cap_conv_cache(d: Dict[str, Any], cap: int = _TRIP_CONV_CACHE_CAP) -> None:
    while len(d) > cap:
        try:
            d.pop(next(iter(d)))
        except StopIteration:
            break


# WO-LIVE-TRIP-COMPANION-02 step 2 — ONE normalization of the inbound
# modal scope, at the boundary where it arrives, for every consumer.
#
# THE DEFECT THIS CLOSES. `params["modal_scope"]` is a browser-supplied
# object: {source_surface, person_id, active_trip_id, active_trip_day_id,
# active_trip_region_id, active_trip_stop_id, active_photo_link_id,
# selected_kind}. Two places read it --- trip story capture and the modal
# direct-answer branch --- and both did `(value or {}).get(...)`, which
# is only a guard against None. A client that sent a STRING sailed
# through both and raised `'str' object has no attribute 'get'` deep
# inside, where one consumer swallowed it as `reason=error` and the other
# logged a warning and carried on. The turn survived, which is correct;
# but two production behaviours silently did not run, and nothing said
# so in a way anyone would notice.
#
# WHY HERE AND NOT IN THE CONSUMERS. Scattering isinstance checks down
# the call chain spreads one question across many places and guarantees
# the next consumer forgets to ask it. A malformed scope is a fact about
# the REQUEST, so the request path decides it once, names it, and hands
# every consumer a value of a known shape.
#
# WHAT IT DELIBERATELY DOES NOT DO. It does not repair, coerce or guess.
# A string is not half a scope, and inventing an `active_trip_id` from
# one would file a conversation against a trip nobody chose. It does not
# log the value either: this object carries person and trip identifiers
# and is adjacent to narrative text, so the log gets the TYPE and the
# reason, never the contents.
def _normalized_modal_scope(
    params: Dict[str, Any], conv_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    raw = params.get("modal_scope")
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    logger.warning(
        "[chat_ws][modal-scope] conv=%s malformed modal_scope type=%s "
        "— scope dropped, turn continues", conv_id, type(raw).__name__)
    return None


@router.websocket("/ws")
async def ws_chat(ws: WebSocket):
    # SECURITY-REVIEW-2026-08-12: websockets are NOT subject to CORS, and
    # this socket accepts destructive commands (sync_session ->
    # clear_turns on a client-named conversation).  A hostile web page on
    # any device that can reach this port could previously open it.  A
    # browser always sends an Origin header on cross-origin WS; local
    # non-browser clients (harnesses, eval scripts) send none and are
    # still permitted.  Allowlist lives in net_guard.py, override with
    # HORNELORE_ALLOWED_ORIGINS.
    from ..net_guard import origin_permitted as _origin_permitted
    _ws_origin = ws.headers.get("origin")
    if not _origin_permitted(_ws_origin):
        logger.warning(
            "[chat_ws][origin-guard] refused websocket from origin=%r "
            "(set HORNELORE_ALLOWED_ORIGINS to permit)", _ws_origin)
        await ws.close(code=4403)
        return
    await ws.accept()
    # WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 2 — CAPABILITY
    # NEGOTIATION, advertised by the process that will actually do the
    # work.
    #
    # The browser must not decide who owns extraction from a constant
    # compiled into its own JavaScript. A cached page against a newer
    # server would stop extracting and never be told; a newer page
    # against an older server would stop extracting and get nothing back
    # -- Shadow Review would simply go quiet. Both are silent, and a
    # silent loss of the narrator's extracted facts is the worst shape
    # this failure can take.
    #
    # VERSIONED, because the next owner change must be distinguishable
    # from this one rather than inferred from its absence.
    await _ws_send(ws, {
        "type": "status",
        "state": "connected",
        "capabilities": {
            "field_extraction_owner": "backend_result_v1",
        },
    })

    # ── WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 §3.2 (2026-07-24) ──
    # PER-TURN cancellation event. The old socket-wide pattern was
    # `ev.set(); current_task.cancel(); ev.clear()` — a race: the clear
    # could land while the PREVIOUS generation thread was still between
    # its StopOnEvent checks, un-cancelling it. An old generation could
    # observe a newly cleared event and keep streaming a dead turn's
    # tokens into a new turn. Now every start_turn mints a FRESH
    # threading.Event owned by exactly that generation; a superseded
    # turn's event is set once and NEVER cleared, so an old generation
    # can never observe a newly cleared event.
    current_cancel_event: Optional[threading.Event] = None
    current_task: Optional[asyncio.Task] = None
    # ── WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 follow-up
    # (fix(chat-ws): serialize generation, 2026-07-24) — per-socket
    # generation-thread handle. The per-turn cancel event above removes
    # the set→clear race, but a superseded turn's DAEMON generation
    # thread only observes StopOnEvent at a token boundary — so without
    # this, turn B's model.generate could start while turn A's was still
    # unwinding (dual-generation VRAM pressure; the audit finding). The
    # generation path below joins the previous thread (bounded) before
    # starting the next generate. Scoped per-socket by construction
    # (closure state) — cross-socket concurrency semantics unchanged.
    generation_thread_holder: Dict[str, Any] = {"thread": None}
    # ── §3.3 — no shared "default" session. Two ID-less sockets used to
    # share history, softened state, segment flags, and follow-up-bank
    # rows under the literal conv_id "default" — one narrator's crisis
    # state could bleed into another narrator's session. Each socket
    # mints its own fallback conversation id at connect.
    socket_conv_id = f"ws_{uuid.uuid4()}"
    # WO-2: track active person_id for identity-session handshake
    active_person_id: Optional[str] = None

    async def generate_and_stream(conv_id: str, user_text: str, params: Dict[str, Any], ev: threading.Event) -> None:
        """TRUTH-PIPELINE-01 Phase 1 (Gate 7) --- observability-only probe.

        Wraps the real turn body so ONE `[truth-pipeline]` line is emitted
        per turn recording which of the five truth-write stages fired.

          - the probe is NOT consumed by the extractor
          - the probe is NOT consumed by Lori
          - the probe is NOT consumed by safety
          - the probe is NOT written to truth or any DB, and adds no table
          - the probe never reaches the narrator surface
          - probe failure is swallowed silently --- never breaks a turn

        Default-OFF behind HORNELORE_TRUTH_PIPELINE_LOG=1. When the flag
        is off, begin_turn returns None and every mark() downstream is a
        no-op, so this wrapper costs one attribute lookup per turn.

        It wraps rather than instruments in place because the turn body
        returns early from eight deterministic short-circuit branches; a
        finally is the only placement that sees all of them.

        WO-TRUTH-PIPELINE-01 PHASE 2 (2026-07-30) — this wrapper is no
        longer observability-only. The bullet list above said "the probe
        is NOT written to truth or any DB, and adds no table"; that is
        still true OF THE PROBE, and the probe itself is unchanged. What
        changed is that this wrapper now also carries the completed-turn
        extraction hook, which does write one ledger row per turn (see
        _run_completed_turn_extraction below).

        Placement here is the whole point. By the time the awaited body
        returns, every path — the main interview path and all six
        deterministic short-circuit branches — has already sent its
        {"type": "done"} frame. The extraction CLAIM therefore starts
        AFTER the browser's completed-turn signal is out the door and
        cannot delay it. The claim also runs while the probe window is
        still open, so `extract_fields_called` lands on the turn that
        provoked it.

        CORRECTED 2026-07-30 by the first live acceptance run. Until that
        run the paragraph above read:

            "Extraction therefore starts AFTER the browser's
            completed-turn signal is out the door and cannot delay it.
            It also runs while the probe window is still open, so
            `extract_fields_called` lands on the turn that provoked it."

        Both sentences were true of the CLAIM and remain true of it.
        Neither was true of the extractor call, which used to be awaited
        here as well. The harness closes its socket the moment it has
        `done`; chat_ws then cancels the turn task; and every interview
        turn in that run recorded outcome='failed'
        error_class='CancelledError' at roughly 830 ms. Only the claim is
        inline now. The extractor runs on a task the service holds in a
        strong-reference set and drains on process shutdown.
        """
        _tp_token = None
        try:
            from ..services import truth_pipeline_probe as _tp
            _tp_token = _tp.begin_turn(
                conv_id=conv_id,
                person_id=str((params or {}).get("person_id") or ""),
                turn_id=str((params or {}).get("turn_id") or ""),
                turn_mode=str((params or {}).get("turn_mode") or ""),
            )
        except Exception:
            _tp_token = None

        try:
            await _generate_and_stream_body(conv_id, user_text, params, ev)
            # WO-TRUTH-PIPELINE-01 Phase 2 — the verified Gate 7 defect
            # was that a completed chat_ws turn never requested field
            # extraction. This is the fix, and it is the ONLY new call.
            #
            # Inside the try, not the finally: a turn body that raised did
            # not complete, and an incomplete turn has nothing to extract.
            # A body that returned normally has persisted its turn, written
            # its archive event, and sent its done frame.
            await _run_completed_turn_extraction(conv_id, user_text, params, ev)
            # WO-LIVE-TRIP-COMPANION-01 Vertical Slice 1 — join the two
            # subsystems. Same position and same reasoning as the line
            # above: the turn is persisted, the archive event is
            # written, the done frame is sent. Placement runs after all
            # three or not at all.
            #
            # AFTER extraction, not before, and the order is deliberate.
            # Extraction is the older, load-bearing path; a placement
            # bug must not be able to delay or displace it. Placement is
            # three local SQLite statements, so it costs the extraction
            # claim single-digit milliseconds to go second.
            await _run_completed_turn_trip_link(conv_id, params, ev)
        finally:
            if _tp_token is not None:
                try:
                    from ..services import truth_pipeline_probe as _tp
                    _tp_summary = _tp.end_turn(_tp_token)
                    if _tp_summary:
                        logger.info("%s", _tp.log_line(_tp_summary))
                except Exception as _tp_err:
                    logger.warning(
                        "[truth-pipeline] probe close failed (turn "
                        "unaffected): %s", _tp_err,
                    )

    async def _deliver_extraction_result(
        outcome: Any,
        clarification_required: Any = None,
        source_text: str = "",
    ) -> None:
        """Send one finished extraction back to the browser that caused it.

        WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 2.

        AFTER THE `done` FRAME, ALWAYS. Extraction finishes on a task of
        its own, seconds after the narrator has read Lori's reply. That
        is the point: Lori's visible response must never wait for a
        field extraction, and before Phase 2 the browser paid for a
        second one to get this data.

        WHAT THE FRAME CARRIES. Identity first -- person_id, conv_id,
        turn_key -- because the browser must be able to refuse a result
        that belongs to a narrator it is no longer showing. turn_key is
        the dedup key and the only one: not elapsed time, not the input
        text, not "the last extraction was recent". Two turns a second
        apart are two turns.

        RAISING IS THE CONTRACT, AND THAT IS WHY THIS DOES NOT USE
        _ws_send(). That helper wraps every send in `except Exception:
        pass`, which is right for the turn itself -- a narrator must not
        lose a reply because one frame failed -- and exactly wrong here.
        The service stamps `delivered_at` only when this returns
        cleanly, so a swallowed failure would record every result as
        delivered, including to a socket that closed while the narrator
        walked away. `delivered_at` has to mean what it says.

        Deliberate deviation from the file's convention. Do not
        "restore symmetry" by routing this through _ws_send().

        Losing the send is cheap either way: the durable row is written
        before this runs, and the catch-up read filters on applied_at,
        not delivered_at, so an undelivered result is still offered on
        reconnect regardless of what this stamp says.
        """
        st = str(getattr(outcome, "status", "") or "")
        await ws.send_text(json.dumps({
            "type": "field_extraction_result",
            "turn_key": getattr(outcome, "turn_key", "") or "",
            "turn_id": getattr(outcome, "turn_id", "") or "",
            # narrator_id is the same identity the photos table calls
            # narrator_id and the trip lane calls person_id. The browser
            # compares it against its active person before applying.
            "person_id": getattr(outcome, "narrator_id", "") or "",
            "conv_id": getattr(outcome, "session_id", "") or "",
            "status": st,
            "method": getattr(outcome, "method", "") or "",
            # Only a succeeded result may carry work. noop and failed
            # travel so the browser can tell "nothing found" from
            # "never ran", and carry nothing to apply.
            "items": (list(getattr(outcome, "items", []) or [])
                      if st == "succeeded" else []),
            "clarification_required": (list(clarification_required or [])
                                       if st == "succeeded" else []),
            # THE TEXT THIS RESULT CAME FROM, carried with it.
            #
            # Shadow Review shows extracted claims beside the words that
            # produced them. The browser's only other source for those
            # words is its "most recent input" variable, which names a
            # DIFFERENT turn whenever two extractions finish out of
            # order -- and mis-attributed provenance in the surface an
            # operator uses to check attribution is worse than no
            # provenance at all.
            #
            # Sent, not stored: `turns` already holds the transcript and
            # the result table must not become a second copy of it.
            "answer_text": (source_text or "") if st == "succeeded" else "",
        }, ensure_ascii=False))

    async def _run_completed_turn_extraction(
        conv_id: str,
        user_text: str,
        params: Dict[str, Any],
        ev: threading.Event,
    ) -> None:
        """WO-TRUTH-PIPELINE-01 Phase 2 (Gate 7, 2026-07-30).

        Request field extraction for a turn that has already completed.

        THE DEFECT THIS CLOSES. Gate 7 Phase 1 measured five truth-write
        stages per turn and found exactly one real fault:
        extract_fields_called=0 on every chat_ws turn.
        /api/extract-fields had no internal Python caller anywhere under
        server/code/api/ — only ui/js/interview.js posted to it — so a
        WebSocket-driven turn never extracted and nothing downstream of
        extraction could fire.

        WHAT THIS FUNCTION DOES NOT DO. It does not write family truth.
        It does not touch a projection. Phase 1 proved both of those
        zeroes were correct by design — family truth is operator-gated
        behind POST /api/family-truth/*, projections are reachable only
        from the `turn_mode == "correction"` branch — and Phase 2 left
        both boundaries exactly where they were. The rule is: connect
        completed turns to EXTRACTION, not to TRUTH.

        FAILURE ISOLATION. Cannot raise except CancelledError. By the
        time this runs the turn is persisted, the archive event is
        written, and the done frame has been sent, so nothing here can
        roll back a turn, roll back an archive event, terminate the
        socket, replace the assistant reply, or leave the browser
        waiting. The service itself is also non-raising; the try/except
        here is a second wall in case this glue is what breaks.

        SCHEDULED, NOT AWAITED (2026-07-30). This hook calls
        schedule_completed_turn_extraction, which persists the ledger
        claim inline — so the attempt is auditable at outcome='started'
        before any task exists — and then runs the extractor on a task
        the service holds and drains at shutdown. The await that used to
        be here is gone; the wrapper docstring above carries the live
        evidence that retired it.

        PRECONDITIONS, all checked below rather than assumed:
          * a committed assistant row id (the idempotency key)
          * the required archive event actually persisted
          * turn_mode is extraction-eligible
          * the turn was not cancelled
        """
        try:
            params = params or {}
            turn_mode = str(params.get("turn_mode") or "").strip()

            from ..services.turn_extraction import (
                schedule_completed_turn_extraction as _schedule_extraction,
                extraction_eligible as _eligible,
            )

            # Cheapest gate first — most short-circuit modes exit here
            # without importing db or touching the ledger at all.
            if not _eligible(turn_mode):
                return

            # WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 2 —
            # THE SERVER HALF OF THE NEGOTIATION.
            #
            # Extract only for a browser that said it can receive the
            # result. A page that predates this protocol still runs its
            # own POST to /api/extract-fields; if this ran anyway, that
            # turn would be extracted TWICE -- which is the whole defect
            # this phase exists to remove, reappearing the moment a
            # stale tab reconnects to a fresh server.
            #
            # Declining is safe in a way that proceeding is not: the old
            # browser is already extracting, so the narrator loses
            # nothing. Neither end may assume the other has been
            # upgraded.
            _client_caps = params.get("client_capabilities")
            _client_caps = _client_caps if isinstance(_client_caps, dict) else {}
            if _client_caps.get("field_extraction_result") != "v1":
                logger.info(
                    "[extract-turn] skipped conv=%s — client did not declare "
                    "field_extraction_result=v1; it owns extraction on this "
                    "turn (declared=%s)",
                    conv_id, _client_caps.get("field_extraction_result") or "-",
                )
                return

            # A cancelled turn did not complete for the narrator. Its
            # persistence is already fail-closed upstream; do not layer
            # extraction on top of a turn the user abandoned.
            if ev is not None and ev.is_set():
                logger.info(
                    "[extract-turn] skipped conv=%s — turn cancelled",
                    conv_id,
                )
                return

            # The required archive event must have landed. Set by the
            # main path only after archive_append_event returned.
            if not params.get("_archive_event_persisted"):
                logger.info(
                    "[extract-turn] skipped conv=%s — required archive "
                    "event not persisted for this turn", conv_id,
                )
                return

            from ..db import turn_extraction_key_for_row as _key_for_row
            _turn_key = _key_for_row(params.get("_persisted_turn_row_id"))
            if not _turn_key:
                logger.warning(
                    "[extract-turn] skipped conv=%s — no committed turn "
                    "row id, so no stable idempotency key", conv_id,
                )
                return

            _outcome = _schedule_extraction(
                narrator_id=str(params.get("person_id") or ""),
                turn_id=str(params.get("turn_id") or ""),
                user_text=user_text or "",
                assistant_text=None,
                session_id=conv_id or None,
                turn_key=_turn_key,
                turn_mode=turn_mode,
                source="chat_ws",
                current_section=(params.get("current_section") or None),
                current_target_path=(params.get("current_target_path") or None),
                current_era=(params.get("current_era") or None),
                current_pass=(params.get("current_pass") or None),
                current_mode=(params.get("current_mode") or None),
                # WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 1.
                # The same verdict the story-capture and trip-placement
                # lanes already read, computed once where the payload is
                # seen. A BOOLEAN, not the text: the extraction service
                # does not inspect transcripts, and a second definition
                # of "this is a directive" would be a second thing to
                # drift.
                is_system_directive=bool(
                    params.get("_is_system_directive")),
                # WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 2.
                # The backend is now the sole automatic extractor, but
                # the BROWSER still owns projection, Shadow Review,
                # repeatable-section grouping and fragile-fact
                # clarification. So the result has to get back to it.
                #
                # A closure, not an import: turn_extraction must not
                # import a router, and this way it never learns what a
                # WebSocket is. It is handed something awaitable and
                # calls it once.
                on_result=_deliver_extraction_result,
            )
            logger.info(
                "[extract-turn][chat_ws] conv=%s %s",
                conv_id, _outcome.as_log_fields(),
            )
        except asyncio.CancelledError:
            # Honour cancellation. The service already recorded the
            # abandoned attempt in the ledger before re-raising.
            raise
        except Exception as _ext_exc:
            # Class name only — an extractor message can quote the
            # narrator's own words, and this line goes to api.log.
            logger.error(
                "[extract-turn] hook raised (turn already delivered and "
                "persisted; nothing rolled back) conv=%s err=%s",
                conv_id, _ext_exc.__class__.__name__,
            )

    async def _run_completed_turn_trip_link(
        conv_id: str,
        params: Dict[str, Any],
        ev: threading.Event,
    ) -> None:
        """WO-LIVE-TRIP-COMPANION-01 Vertical Slice 1 (2026-07-30).

        Link a turn that has already completed to the trip and the day
        the narrator is living in.

        THE GAP THIS CLOSES. Trips, generated trip days, day cards and
        photo placement all worked. Lori persisted turns, wrote archive
        events and dispatched extraction. Nothing joined them. The only
        notion of "the trip Lori is working on" was
        `runtime71.active_trip_id`, which is `state.session.activeTripId`
        in ui/js/travels-shelf.js. That is a browser fact: it does not
        survive a reload and it does not survive a restart. This hook
        therefore does NOT read runtime71. It asks the database which
        trip is live, which is why reopening the trip after a restart
        shows the same timeline event.

        AMENDED 2026-07-31, WO-TRIP-NARRATOR-BRIDGE-01. It now reads
        runtime71 for exactly two fields, and only as a fallback. A
        COMPLETED trip has live_state != 'active', so the database
        answer to "which trip is live" is None and every turn about it
        was a silent noop -- a man opened the Bismarck trip, told the
        story of visiting his mother's parents' grave, and nothing
        anywhere recorded which trip he had been talking about. The
        database is still asked first and still wins. Only when it has
        no answer at all does this hook hand the service the narrow
        shelf fact -- shelf open, this trip id -- and the service
        re-reads that trip and checks it belongs to him before using
        it. It never yields a day, and the whole path is behind the
        default-off HORNELORE_TRIP_SHELF_TURN_LINK.

        WHAT THIS HOOK DOES NOT DO. It does not write family truth. It
        does not touch a projection. It does not change correction
        behaviour. Placing a conversation on a calendar day is a
        statement about WHEN a conversation happened, not a claim about
        a family, and the two must not be allowed to blur. Gate 7 Phase
        1 measured both boundaries and proved their zeroes were correct
        by design; this slice leaves both exactly where they were.

        FAILURE ISOLATION. Cannot raise except CancelledError. The
        service is non-raising on every path; this try/except is a
        second wall in case the glue is what breaks. By the time this
        runs the turn is persisted, the archive event is written and
        the done frame is out, so nothing here can roll back a turn,
        roll back an archive event, terminate the socket, replace the
        assistant reply, or leave the browser waiting. Losing a link
        costs a timeline entry. It must never cost a conversation.

        AND WHEN THE DAY IS UNKNOWN, THE TURN IS STILL LINKED. An
        active trip with no chosen day does not discard the
        conversation; the service records it against the trip at
        placement_status='needs_day', which surfaces as a
        reconciliation item for a human to place. That is the work
        order's requirement, verbatim: a failure to link the trip
        should not lose the conversation, it should leave an observable
        reconciliation item.

        PRECONDITIONS, all checked in the service rather than assumed:
          * an eligible turn mode
          * a committed assistant row id (the idempotency key)
          * a trip for this narrator: the durable active trip, or the
            shelf trip when there is no active one and the fallback
            flag is on
        """
        try:
            params = params or {}

            from ..services.trip_placement import (
                link_completed_turn as _link_turn,
                placement_eligible as _placement_eligible,
            )

            turn_mode = str(params.get("turn_mode") or "").strip()

            # Cheapest gate first — the short-circuit modes exit here
            # without importing the repository or opening the DB.
            if not _placement_eligible(turn_mode):
                return

            # A cancelled turn did not happen for the narrator. Do not
            # put it on the trip's timeline.
            if ev is not None and ev.is_set():
                return

            # DELIBERATELY NOT THE SAME PRECONDITION AS EXTRACTION, and
            # this is the correction the first live acceptance run
            # bought (2026-07-30). The extraction hook above requires
            # `_archive_event_persisted`, and it is right to: extraction
            # reads the memoir archive, so an incomplete archive would
            # make it read a half-written turn.
            #
            # Placement requires no such thing, because
            # BUG-MODAL-TURNS-ARCHIVED-AS-LIFE-STORY-01 makes the
            # archive write conditional on surface: a turn whose
            # surface is `travel_doc_modal` is deliberately kept OUT of
            # the narrator's life story, so it never sets that flag.
            # Copying extraction's gate here therefore made every
            # single Travel Doc turn ineligible for the trip timeline —
            # which is to say, it made the one surface this whole slice
            # exists to serve the one surface it could never work on.
            # The live log recorded it as a silent skip, and a silent
            # skip on the happy path is the most expensive kind.
            #
            # What placement actually needs is that the conversation is
            # on disk, because the timeline reads its words back out of
            # `turns` by row id. That is `_persisted_turn_row_id`, set
            # after COMMIT a few thousand lines below, and the service
            # re-checks it rather than trusting this gate.
            #
            # DO NOT "restore symmetry" with the extraction gate above.
            # Placing a conversation on a calendar day says WHEN it
            # happened; it writes no family truth and no memoir. The
            # two hooks have different preconditions because they have
            # different jobs.
            if not params.get("_persisted_turn_row_id"):
                return

            # (x or {}).get() guards None and nothing else -- the exact
            # hole that let a string reach two consumers and raise
            # 'str' object has no attribute 'get' deep inside them. A
            # runtime71 of the wrong shape is not half a scope; it is
            # no scope, and the turn places on the durable path or not
            # at all.
            _rt71_shelf = params.get("runtime71")
            if not isinstance(_rt71_shelf, dict):
                _rt71_shelf = {}
            _shelf_scope = {
                "travels_shelf_open": bool(
                    _rt71_shelf.get("travels_shelf_open")),
                "active_trip_id": str(
                    _rt71_shelf.get("active_trip_id") or ""),
            }

            _outcome = _link_turn(
                narrator_id=str(params.get("person_id") or ""),
                assistant_turn_row_id=params.get("_persisted_turn_row_id"),
                user_turn_row_id=params.get("_persisted_user_turn_row_id"),
                conv_id=conv_id or "",
                turn_id=str(params.get("turn_id") or ""),
                turn_mode=turn_mode,
                source="chat_ws",
                # BUG-TRIP-SYSTEM-DIRECTIVE-PLACED-AS-NARRATOR-TURN-01.
                # A BOOLEAN, not the text. The service stays blind to
                # what the narrator said -- it holds identifiers only,
                # and handing it a transcript to sniff would give it a
                # second thing to be wrong about. The boundary read the
                # payload and already knows the answer; it passes the
                # answer.
                is_system_directive=bool(
                    params.get("_is_system_directive")),
                # Unwrapped HERE, at the boundary, so the placement
                # service never learns the browser's field names and
                # has only one thing to be wrong about. Two fields,
                # both re-validated downstream; the id is a claim, not
                # an authority.
                shelf_scope=_shelf_scope,
            )

            # A narrator with no trip running produces a noop on every
            # single turn. Logging that at INFO would bury api.log in
            # the ordinary case, so only real placements and real
            # failures speak up.
            if _outcome.status == "failed":
                logger.error(
                    "[trip-link][chat_ws] conv=%s %s",
                    conv_id, _outcome.as_log_fields(),
                )
            elif _outcome.status != "noop":
                logger.info(
                    "[trip-link][chat_ws] conv=%s %s",
                    conv_id, _outcome.as_log_fields(),
                )
        except asyncio.CancelledError:
            raise
        except Exception as _link_exc:
            # Class name only — a repository message can quote a trip
            # title or a day label, and this line goes to api.log.
            logger.error(
                "[trip-link] hook raised (turn already delivered and "
                "persisted; nothing rolled back) conv=%s err=%s",
                conv_id, _link_exc.__class__.__name__,
            )

    async def _generate_and_stream_body(conv_id: str, user_text: str, params: Dict[str, Any], ev: threading.Event) -> None:
      # WO-10M: Flag-outside-except OOM recovery pattern.
      # The exception object holds references to the stack frame where the
      # allocator failed, which in turn holds references to the tensors that
      # blew up. If we try to run recovery logic (empty_cache, mem_get_info,
      # new allocations) INSIDE the except block, those tensors are still
      # rooted and the allocator can't reclaim them. We set a flag, exit the
      # except scope cleanly, and run recovery after the exception object is
      # garbage-collected.
      oom_triggered = False
      generic_exc: Optional[BaseException] = None
      generic_msg: str = ""

      try:
        await _generate_and_stream_inner(ws, ev, conv_id, user_text, params)
        return
      except torch.cuda.OutOfMemoryError as oom_err:
        oom_triggered = True
        logger.error("[chat_ws][WO-10M] CUDA OOM caught (torch.cuda.OutOfMemoryError): %s", str(oom_err)[:200])
      except RuntimeError as rt_err:
        err_str = str(rt_err)
        if "out of memory" in err_str.lower() or "CUDA out of memory" in err_str:
            oom_triggered = True
            logger.error("[chat_ws][WO-10M] CUDA OOM caught (RuntimeError): %s", err_str[:200])
        else:
            generic_exc = rt_err
            generic_msg = err_str
            logger.error("[chat_ws] RuntimeError: %s", rt_err, exc_info=True)
      except Exception as exc:
        generic_exc = exc
        generic_msg = str(exc)
        logger.error("[chat_ws] generate_and_stream failed: %s", exc, exc_info=True)

      # ── Recovery phase: exception scope is now closed, references are
      #    dropped, allocator can reclaim memory safely. ────────────────────
      if oom_triggered:
        # Break any lingering reference cycles from the failed turn.
        try:
            gc.collect()
        except Exception:
            pass
        # Attempt cache release. Wrapped defensively because mem_get_info
        # and empty_cache can themselves raise if the allocator is wedged.
        vram_after_mb = -1.0
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                vram_after_mb = torch.cuda.mem_get_info()[0] / 1024**2
        except Exception as cleanup_err:
            logger.warning("[chat_ws][WO-10M] post-OOM cleanup failed: %s", cleanup_err)
        logger.info("[chat_ws][WO-10M] post-OOM recovery complete, free VRAM=%.0f MB", vram_after_mb)
        await _ws_send(ws, {
            "type": "error",
            "code": "CUDA_OOM",
            "message": "GPU ran out of memory mid-generation. VRAM has been freed — please try again.",
            "vram_free_mb": round(vram_after_mb) if vram_after_mb >= 0 else None,
        })
        await _ws_send(ws, {"type": "done", "final_text": "", "oom": True})
        return

      if generic_exc is not None:
        await _ws_send(ws, {"type": "error", "message": f"Chat backend error: {generic_msg[:300]}"})
        await _ws_send(ws, {"type": "done", "final_text": ""})
        return

    async def _generate_and_stream_inner(ws: WebSocket, ev: threading.Event, conv_id: str, user_text: str, params: Dict[str, Any]) -> None:
        # Extract person_id from params (sent by UI)
        person_id: Optional[str] = params.get("person_id") or None

        # WO-LORI-MEMORY-ECHO-ERA-STORIES-01 Phase 1 (2026-05-06):
        # Pull current_era from runtime71 once at the top of the turn so
        # both archive writes (user @ L454, assistant @ L1534) bind the
        # same era to both halves of the turn. Canonicalize via lv_eras
        # to absorb any legacy / "era:" prefixed values from older UI
        # bookmarks. None when no era is set (e.g., onboarding before
        # first Life Map click) — gracefully degrades; turns simply
        # don't bin into era groups in memory_echo readback.
        _current_era_for_archive: Optional[str] = None
        try:
            _rt71 = params.get("runtime71") or {}
            if isinstance(_rt71, dict):
                _raw_era = _rt71.get("current_era") or _rt71.get("currentEra")
                if _raw_era:
                    from ..lv_eras import legacy_key_to_era_id as _legacy_key_to_era_id
                    _canon = _legacy_key_to_era_id(str(_raw_era))
                    if _canon:
                        _current_era_for_archive = _canon
        except Exception as _era_exc:
            logger.debug("[chat_ws][era-binding] failed to canonicalize: %s", _era_exc)

        # BUG-ARCHIVE-AUDIO-NOT-LINKED-TO-TRANSCRIPT-01 (2026-05-07):
        # Audio_id extraction lifted to function-top scope so it's
        # available to BOTH the story-trigger preserve_turn call AND
        # the user-turn archive_append_event write. Earlier fix had
        # it scoped inside the archive block (later in the function),
        # which made the variable unreachable from the story-trigger
        # block above. Defensive: shape-guards keep garbage values
        # from reaching the archive layer.
        _audio_id_for_archive: Optional[str] = None
        try:
            _ai_raw = params.get("audio_id") or params.get("turn_id") or None
            if _ai_raw:
                _ai_str = str(_ai_raw).strip()
                if _ai_str and len(_ai_str) >= 8:
                    _audio_id_for_archive = _ai_str
        except Exception:
            _audio_id_for_archive = None

        # WO-ML-03B (Phase 3 of the multilingual project, 2026-05-07):
        # ISO-639-1 language code detected by the STT engine, threaded
        # from the FE TranscriptGuard's chat WS payload. Available to
        # BOTH the story-trigger preserve_turn call AND the user-turn
        # archive_append_event write. Null on Web Speech / typed input /
        # unknown — downstream layers tolerate null gracefully (no row
        # falls over because language is missing).
        #
        # Source priority: payload-level transcript_language (set by
        # TranscriptGuard.buildExtractionPayloadFields), then fall back
        # to the runtime71 transcript_language hint, then None. The
        # value is light-validated (lowercased, trimmed, length 2-3
        # for ISO-639-1/-3 codes) but NOT enforced — non-conforming
        # values pass through and the operator review can flag them.
        _transcript_language_for_archive: Optional[str] = None
        _transcript_language_prob_for_archive: Optional[float] = None
        try:
            _lang_raw = (
                params.get("transcript_language")
                or (params.get("runtime71") or {}).get("transcript_language")
                or None
            )
            if _lang_raw:
                _lang_str = str(_lang_raw).strip().lower()
                # Strip regional variants ("es-MX" → "es") for
                # consistent persistence; downstream consumers that
                # need the full tag can read raw_transcript metadata.
                if "-" in _lang_str:
                    _lang_str = _lang_str.split("-", 1)[0]
                if _lang_str and 2 <= len(_lang_str) <= 3:
                    _transcript_language_for_archive = _lang_str
            _prob_raw = (
                params.get("transcript_language_probability")
                or (params.get("runtime71") or {}).get("transcript_language_probability")
                or None
            )
            if isinstance(_prob_raw, (int, float)):
                # Clamp defensively — Whisper probabilities are in (0, 1]
                # but a buggy upstream could send anything.
                _p = float(_prob_raw)
                if 0.0 <= _p <= 1.0:
                    _transcript_language_prob_for_archive = _p
        except Exception:
            _transcript_language_for_archive = None
            _transcript_language_prob_for_archive = None

        # ── WO-LORI-STORY-CAPTURE-01 Phase 1A Commit 3b: story preservation hook ──
        # Path 1 entry point. Decoupled from the rest of the chat path:
        # a preservation failure logs CRITICAL but does NOT stop the
        # session. Imports are lazy and gated so LAW 3 INFRASTRUCTURE
        # isolation holds when the flag is off — the preservation
        # modules are not loaded into the process at all.
        #
        # See WO-LORI-STORY-CAPTURE-01_Spec.md §0.5 (golfball
        # architecture): this is the WINDINGS layer wired at the entry
        # point. Extraction (Path 2) runs separately on a different
        # route and cannot block this work.
        #
        # Behavior contract:
        #   flag off          → no-op, byte-stable with pre-3b chat path
        #   empty transcript  → no-op even with flag on (skip silently)
        #   flag on + text    → trigger_diagnostic() runs every turn,
        #                       [story-trigger] log marker emitted,
        #                       preserve_turn() called only if
        #                       trigger != None AND person_id present
        #   preserve raises   → [story-trigger][CRITICAL] log,
        #                       session continues, no rethrow
        # Patch A (2026-04-30 polish): skip SYSTEM_* in-band directives.
        # ui/js/session-loop.js emits [SYSTEM_QF: ...] and [SYSTEM: ...]
        # messages as user-role WS payloads to feed Lori in-band guidance;
        # those are not narrator-authored content and must not be classified.
        # Without this guard, a directive that happens to mention a relative,
        # a place noun, AND a time phrase would write a false-positive
        # story_candidate row.
        # ── WO-SYSTEM-DIRECTIVE-PERSISTENCE-01 Phase 1b, 2026-08-09 ────
        # PROVENANCE IS DECLARED BY THE SENDER; THE PREFIX IS THE LEGACY
        # FALLBACK.
        #
        # This line read, from 2026-04-30 to 2026-08-09:
        #
        #     _is_system_directive = _ut_lstrip.startswith("[SYSTEM")
        #
        # That was adequate while the answer was only used to SKIP work
        # (story capture, trip placement). It stopped being adequate the
        # moment Phase 1 began writing the answer down, because a
        # persisted guess is a durable one -- and the work order's own
        # acceptance requires that a narrator who genuinely types
        # "[SYSTEM: ..." is recorded as narrator speech. A prefix test
        # cannot satisfy that; it is the very thing that gets it wrong.
        #
        # THE BROWSER ALREADY KNEW, IN THREE WAYS, AND TRANSMITTED NONE
        # OF THEM. Directives are built by `sendSystemPrompt()` in
        # `ui/js/app.js` -- a different function from `sendUserMessage()`,
        # sending a differently-shaped frame (no `turn_mode`), under a
        # comment that says in words "This path sends [SYSTEM: ...]
        # directives". Forty-three call sites use it. The knowledge was
        # thrown away at the wire exactly as it was later thrown away at
        # the row, one layer up and for the same reason: nobody had asked
        # the question at a point where the answer could be recorded.
        #
        # So both frames now declare `params.message_kind`, and this is
        # where the declaration is believed. The prefix survives ONLY for
        # senders that have not declared -- older clients, the two
        # travel-doc senders, and any path not yet updated -- which is
        # the current behaviour, unchanged, for exactly those.
        #
        # PRODUCERS VERIFIED 2026-08-09: every internal directive reaches
        # the wire through `sendSystemPrompt()`. `session-loop.js` builds
        # the `[SYSTEM_QF: ...]` family and dispatches all of it there
        # (`:367`, `:464`, `:509`); `wo9SendOrQueueSystemPrompt` routes
        # there on both its immediate and drained-queue paths; and the
        # two travel-doc senders contain zero `[SYSTEM` strings, so they
        # produce no directives to misclassify.
        #
        # TRUST BOUNDARY, STATED SO NOBODY LATER MISTAKES IT FOR
        # AUTHENTICATION. `message_kind` is ordinary browser JSON. A
        # hostile client could set it, and this code does not stop that.
        # It is not trying to: Hornelore is a local, single-operator
        # family system, and the question here is not "who is allowed to
        # speak" but "which of our own two send paths built this
        # message". Signing it would add key management to a system whose
        # threat model does not include a hostile browser, and the cost
        # of a forged value is bounded -- a directive recorded as
        # narrator speech, or the reverse, which is the state the whole
        # repository was already in before today.
        #
        # An UNRECOGNISED declared value resolves to NOT-a-directive. It
        # fails toward narrator speech deliberately: a typo must never be
        # able to erase a narrator's words from their own memoir, and the
        # opposite failure -- a directive surviving into a transcript --
        # is one the readers already tolerate.
        _ut_lstrip = (user_text or "").lstrip()
        _declared_kind = str(params.get("message_kind") or "").strip().lower()
        if _declared_kind:
            _is_system_directive = (_declared_kind == "internal_directive")
        else:
            # Legacy fallback. Not a classification anybody is proud of;
            # it is what the undeclared senders have always got.
            _is_system_directive = _ut_lstrip.startswith("[SYSTEM")

        # BUG-TRIP-SYSTEM-DIRECTIVE-PLACED-AS-NARRATOR-TURN-01
        # (live, 2026-07-31). The completed-turn trip-placement hook runs
        # later with only `params` in hand -- user_text is a sibling of
        # params in the WS payload, not a member of it -- so the decision
        # made on this line is recorded here, where it is made, rather
        # than re-derived from a text the hook cannot see.
        #
        # Without it, three of the four conversations placed on the
        # Bismarck Trip were `[SYSTEM: The ...]` directives, and the day
        # timeline rendered that operator text as `narrator_said`: the
        # narrator appeared to have said 740 characters of instructions
        # to himself. The story-capture lane already refuses these, and
        # has since Patch A on 2026-04-30 for the same reason -- they are
        # not narrator-authored content. Placement did not inherit it.
        params["_is_system_directive"] = _is_system_directive

        # ── WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 (2026-07-24) ──
        # DETERMINISTIC SAFETY PREFLIGHT — runs ONCE, before EVERY narrator
        # short-circuit: claimed-floor buffering, identity/meta-question
        # detection, travel-doc modal direct answers, trip direct answers,
        # memory-echo routing, witness routing, follow-up-bank flushing.
        #
        # The 2026-07-24 code review found three bypass classes:
        #   1. The meta/modal/trip intercepts set _is_meta_question BEFORE
        #      scan_answer ran, and the safety block was gated on
        #      `not _is_meta_question` — so "What is your name? I want to
        #      kill myself." skipped even the deterministic pattern layer.
        #   2. Claimed-floor buffering (turn_final=False) early-returned
        #      "I'm listening." ~1200 lines before the safety block; a
        #      distress chunk was persisted and never scanned.
        #   3. Memory-echo / witness META_FEEDBACK / bank-flush could
        #      override the forced interview route AFTER a trigger.
        #
        # The preflight result is CONSUMED by the safety block below —
        # scan_answer is never called a second time for the same turn.
        #
        # Locked precedence (WO §2.2):
        #   positive deterministic trigger > claimed-floor buffering >
        #   meta/trip/modal deterministic answers > memory echo / witness /
        #   bank flush > normal LLM interview.
        #
        # WO-LORI-SAFETY-INTEGRATION-01 Phase 7 (2026-05-03): LV_ENABLE_SAFETY
        # kill-switch. Default-ON ("1"). Setting LV_ENABLE_SAFETY=0 disables
        # the ENTIRE chat-path safety pipeline: pattern scan, LLM
        # second-layer, segment_flag persistence, softened-mode set,
        # operator notification, and the Phase 5a discipline exemption (it
        # checks _safety_result which won't be set).
        #
        # This is a DEVELOPER-ONLY toggle. Use cases:
        #   - Running automated chat-path tests where deterministic safety
        #     routing would mask normal-turn behavior under inspection
        #   - Red-team eval that wants to test ONLY the LLM-side path
        #     (Phase 2) by suppressing pattern-side noise — but for that
        #     case, set HORNELORE_SAFETY_LLM_LAYER=1 separately and still
        #     leave LV_ENABLE_SAFETY=1; the LLM-layer fires inside the
        #     pattern block's else branch
        #   - Eyeballing a clean composer / extractor surface without
        #     safety interjections
        #
        # NEVER set LV_ENABLE_SAFETY=0 in a real narrator session. The
        # ACUTE SAFETY RULE in the prompt still fires (the rule is in
        # the system prompt unconditionally), but the deterministic
        # segment_flag → softened-mode → operator-notify → LLM-routing
        # cascade is GONE. That means:
        #   - No operator visibility (Bug Panel banner won't show)
        #   - No segment_flag in the DB (review queue won't see it)
        #   - No softened-mode for subsequent turns
        #   - turn_mode won't be forced to interview, so memory_echo
        #     could echo distress content back at the narrator
        # The default-OFF onboarding consent (Phase 9) and the kill-switch
        # itself are sufficient operator controls. The kill-switch is for
        # the operator workstation, not for a deployed kiosk.
        _safety_result = None  # type: ignore[assignment]
        _safety_scan_failed = False
        _safety_pattern_triggered = False
        # ── WO-LEAN-LORI-RUNTIME-01 Phase 3B ──────────────────────────
        # PARKED outranks the kill-switch. `LV_ENABLE_SAFETY` is a
        # developer kill-switch whose own comment says never to use it
        # in a real narrator session; parked is a deployment state, and
        # it is the server's single authority over the whole feature.
        # Checked first so no combination of stale legacy env values can
        # re-arm one piece of a parked feature.
        _safety_parked = False
        try:
            from .. import flags as _lean_flags
            _safety_parked = _lean_flags.safety_parked()
        except Exception:
            _safety_parked = False   # unknown -> historical behaviour
        _safety_enabled = (
            (not _safety_parked)
            and os.getenv("LV_ENABLE_SAFETY", "1") in ("1", "true", "True"))
        if _safety_parked:
            # INFO, not WARNING. The kill-switch warns on every turn
            # because it means something is wrong; parked is a decision
            # Chris made, recorded in docs/decisions, and a warning per
            # turn would train an operator to ignore the warning colour.
            logger.info(
                "[chat_ws][safety] PARKED — deterministic scan, LLM "
                "classifier, cascade, softened mode and notifications "
                "are inactive for this deployment. conv=%s", conv_id)
        elif not _safety_enabled:
            # Emit a per-turn WARNING — chosen over a session-only one-shot
            # because operators looking at api.log mid-incident need to see
            # this on every turn. Quiet noise on a normal session is the
            # cost of loud warning when something is actually wrong.
            logger.warning(
                "[chat_ws][safety][KILL-SWITCH] LV_ENABLE_SAFETY=0 — "
                "deterministic safety pipeline DISABLED for this turn. "
                "DEVELOPER MODE ONLY. conv=%s",
                conv_id,
            )
        # System directives ([SYSTEM...] in-band UI messages) are NOT
        # narrator disclosures — they retain their existing handling
        # (floor-hold ack etc., pinned by
        # tests/test_safety_directive_not_in_narrator_turn.py) and are
        # never scanned as narrator text.
        if _safety_enabled and user_text and user_text.strip() and not _is_system_directive:
            try:
                _safety_result = scan_answer(user_text)
                _safety_pattern_triggered = bool(
                    _safety_result and _safety_result.triggered
                )
            except Exception as _safety_exc:
                logger.warning("[chat_ws][safety] scan failed: %s", _safety_exc)
                _safety_result = None
                _safety_scan_failed = True

            # Default-safe fallback: when scan_answer raises, the deterministic
            # cascade below is skipped (no segment flag / no softened mode /
            # no UI overlay / no operator notify). The LLM-side ACUTE SAFETY
            # RULE in prompt_composer.py:108-193 still fires regardless, but
            # only the interview/LLM turn_mode actually consults the system
            # prompt. So on scan failure we force turn_mode='interview' to
            # guarantee the LLM path runs (memory_echo / correction composers
            # would skip the LLM entirely and echo distress content back).
            # Operators see [chat_ws][safety][default-safe] so they know the
            # deterministic layer had to fall back. Closes the silent-skip
            # gap surfaced by 2026-04-29 code review.
            if _safety_scan_failed:
                logger.warning(
                    "[chat_ws][safety][default-safe] forcing turn_mode=interview after scan_answer failure conv=%s",
                    conv_id,
                )
                params["turn_mode"] = "interview"

        # WO §2.5 — THE one authoritative route boolean. When True, the
        # turn is on the forced safety/interview route and NO deterministic
        # short-circuit may take it over: floor buffering may not early-
        # return, meta/modal/trip intercepts may not answer, memory-echo
        # may not flip turn_mode, witness META_FEEDBACK may not flip
        # turn_mode, bank-flush may not execute. Every gate below checks
        # THIS name — do not spread per-site safety conditions.
        # Refreshed once after the safety block below, because the LLM
        # second-layer classifier can synthesize a triggered
        # _safety_result the deterministic preflight missed.
        _safety_forced_interview = bool(
            _safety_scan_failed
            or (_safety_result and _safety_result.triggered)
        )
        if _safety_pattern_triggered:
            logger.warning(
                "[chat_ws][safety][preflight] deterministic trigger conv=%s "
                "category=%s confidence=%.2f — safety route takes precedence "
                "over floor-buffer/meta/trip/witness/bank short-circuits",
                conv_id,
                _safety_result.category if _safety_result else "?",
                _safety_result.confidence if _safety_result else 0.0,
            )

        # ── BUG-LORI-FLOOR-HOLD-DETERMINISTIC-01 (2026-05-10) ───────────
        # SYSTEM_FLOOR_HOLD short-circuit. When the narrator has pressed
        # and held the floor (UI emits [SYSTEM: pressed and held the
        # floor / still talking / has not submitted / Do not ask a
        # question / Do not summarize]), Lori MUST emit a small
        # deterministic ack — no LLM call, no question, no summary,
        # under 8 words. The harness's TEST-A regression evidence:
        # Lori said "It's great that you're taking the time to share
        # your story with me, Kent." (14 words) — too long, claims
        # gratitude rather than holding silent space.
        #
        # Three rotating acks ("Take your time." / "I'm listening." /
        # "Keep going.") — picks one based on a hash of conv_id so the
        # same session sees variety on repeated holds without becoming
        # parrot-like.
        _is_floor_hold = False
        if _is_system_directive:
            _ut_lower = _ut_lstrip.lower()
            _floor_hold_signals = (
                "pressed and held the floor",
                "still talking and has not submitted",
                "narrator is still talking",
                "do not ask a question. do not summarize",
                "claimed-floor mode",
            )
            if any(sig in _ut_lower for sig in _floor_hold_signals):
                _is_floor_hold = True

        # ── BUG-LORI-FLOOR-HOLD-DETERMINISTIC-01 (2026-05-10) ───────
        # turn_final=false defensive handler. Per Chris's claimed-
        # floor architecture rule: the narrator may speak/type for
        # 10-30 minutes uninterrupted. The frontend SHOULD buffer
        # chunks and only release the floor when the narrator/
        # operator explicitly signals "I'm done with this chapter."
        #
        # The current FE doesn't yet implement claimed-floor
        # buffering — every Send press fires a turn. But when the
        # FE does add it, it will send turn_final=false on partial
        # chunks. This branch makes the backend safe TODAY:
        #
        #   turn_final=false  → buffer only, ack "I'm listening.",
        #                       no LLM, no witness, no bank flush
        #   turn_final=true   → process normally (the default)
        #   turn_final absent → process normally (back-compat)
        #
        # Forward-compatible: if FE later implements buffering,
        # backend Just Works without code changes. For Kent's
        # morning session: the Send button is the explicit
        # release. Operator instruction: do NOT press Send until
        # Kent finishes the chapter.
        _turn_final = params.get("turn_final")
        _floor_state = params.get("floor_state", "")
        _floor_buffer_requested = _turn_final is False or (
            isinstance(_floor_state, str)
            and _floor_state.lower() in ("claimed", "holding", "buffering")
        )
        # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 §2.4: a
        # safety-triggered chunk (or a failed scan — default-safe) must
        # NOT take the buffering early return. It falls through into the
        # complete safety cascade below so the chunk itself is flagged
        # (segment flag on THIS chunk — no reliance on a chapter-
        # completion rescan) and Lori answers under the ACUTE SAFETY
        # RULE instead of "I'm listening.". Benign chunks keep the
        # existing persistence + quiet-ack behavior byte-for-byte.
        if _floor_buffer_requested and _safety_forced_interview:
            logger.warning(
                "[chat_ws][floor-buffer][safety-override] conv=%s — "
                "buffered chunk carries a safety trigger (or scan "
                "failure); skipping the buffer ack and entering the "
                "full safety cascade",
                conv_id,
            )
        if _floor_buffer_requested and not _safety_forced_interview:
            logger.info(
                "[chat_ws][floor-buffer] turn_final=False / floor_state=%s "
                "conv=%s — buffering, no LLM call",
                _floor_state, conv_id,
            )
            # Persist the chunk to history so it's retained, but
            # respond with a quiet ack. No LLM, no witness, no
            # bank flush. The completed chapter will arrive on the
            # next turn with turn_final=true (or absent).
            _buffer_ack = "I'm listening."
            try:
                persist_turn_transaction(
                    conv_id=conv_id,
                    user_message=user_text,
                    assistant_message=_buffer_ack,
                    model_name="floor-buffer-deterministic",
                    # WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 R2.3.
                    person_id=person_id,
                    # WO-SYSTEM-DIRECTIVE-PERSISTENCE-01 Phase 1 (2026-08-09).
                    is_system_directive=bool(params.get("_is_system_directive")),
                    meta={
                        "ws": True,
                        "turn_mode": "floor_buffer",
                        "turn_final": False,
                        "floor_state": _floor_state or "claimed",
                    },
                )
            except Exception as _buf_persist_exc:
                logger.warning(
                    "[chat_ws][floor-buffer] persist failed conv=%s: %s",
                    conv_id, _buf_persist_exc,
                )
            await _ws_send(ws, {"type": "token", "delta": _buffer_ack})
            await _ws_send(ws, {
                "type": "done",
                "final_text": _buffer_ack,
                "turn_mode": "floor_buffer",
                "buffering": True,
            })
            return

        # ── WO-LORI-FACTUAL-CHAIN-CAPTURE-01 Phase 2+3 (2026-06-24) ────────
        # Detect factual chains (place→event→outcome sequences, travel
        # legs, medical chains, family migrations, etc.) and capture
        # meta-feedback ("not the scenery — I want the facts") so the
        # composer directive can land BEFORE the LLM call and the
        # chain_meta can ride along to story_candidates.
        #
        # Default-on (classifier is pure-stdlib; failure is logged and
        # never blocks the turn). Disable with HORNELORE_FACTUAL_CHAIN=0
        # to fall back to byte-stable behavior in case of regression.
        _chain_ctx: Dict[str, Any] = {}
        _chain_directive_text: str = ""
        _chain_meta_for_preserve: Dict[str, Any] = {}
        if (
            os.getenv("HORNELORE_FACTUAL_CHAIN", "1") in ("1", "true", "True")
            and user_text
            and user_text.strip()
            and not _is_system_directive
        ):
            try:
                from ..services import factual_chain_capture as _fcc
                _prior_for_chain = []
                try:
                    _prior_for_chain = export_turns(conv_id) or []
                except Exception as _hist_exc:
                    logger.warning(
                        "[chat_ws][factual-chain] history fetch failed "
                        "(conv=%s) — falling back to meta-feedback-blind "
                        "detection: %s",
                        conv_id, _hist_exc,
                    )
                _chain_ctx = _fcc.build_factual_chain_followup_context(
                    user_text, prior_turns=_prior_for_chain
                ) or {}
                _chain_directive_text = (
                    _chain_ctx.get("composer_directive") or ""
                ).strip()
                # Phase 4 chain_meta — written into story_candidates.
                # Only populated when the detector classified the turn
                # as a factual chain; otherwise the row gets the
                # default '{}'.
                if _chain_ctx.get("is_factual_chain"):
                    _chain_meta_for_preserve = {
                        "chain_story_candidate": True,
                        "chain_anchors": list(_chain_ctx.get("anchors") or []),
                        "chain_cue_labels": list(_chain_ctx.get("cue_labels") or []),
                        "chain_confidence": _chain_ctx.get("confidence", 0.0),
                        "chain_blocked_probe_types": list(
                            _chain_ctx.get("blocked_probe_types") or []
                        ),
                        "chain_preferred_followup_type": (
                            _chain_ctx.get("preferred_followup_type") or ""
                        ),
                        # Reserved for follow-up phase that infers
                        # missing chain links from cue patterns.
                        "chain_missing_links": [],
                    }
                _meta_state = _chain_ctx.get("meta_feedback") or {}
                logger.info(
                    "[chat_ws][factual-chain] conv=%s narrator=%s "
                    "is_chain=%s conf=%s cues=%s anchors=%s "
                    "meta_feedback=%s rejected=%s",
                    conv_id,
                    person_id or "<unknown>",
                    _chain_ctx.get("is_factual_chain"),
                    _chain_ctx.get("confidence"),
                    _chain_ctx.get("cue_labels"),
                    len(_chain_ctx.get("anchors") or []),
                    _meta_state.get("is_meta_feedback"),
                    _meta_state.get("last_rejected_probe_type") or "",
                )
            except Exception as _fcc_exc:
                # LAW 3: detection failure is loud but NEVER fatal.
                # Chat turn continues with byte-stable behavior.
                logger.warning(
                    "[chat_ws][factual-chain] detection failed "
                    "conv=%s — chat continues without directive: %s",
                    conv_id, _fcc_exc,
                )

        if (
            os.getenv("HORNELORE_STORY_CAPTURE", "0") in ("1", "true", "True")
            and user_text
            and user_text.strip()
            and not _is_system_directive
        ):
            try:
                from ..services import story_trigger as _story_trigger
                from ..services import story_preservation as _story_preservation
            except Exception as _imp_exc:
                logger.warning(
                    "[story-trigger] import failed — skipping preservation "
                    "for this turn (conv=%s): %s",
                    conv_id, _imp_exc,
                )
            else:
                _trigger_diag = None
                try:
                    # WO-STORY-CANDIDATE-TEXT-CHAIN-PERSISTENCE-01
                    # (2026-06-25): pass the factual-chain context
                    # built earlier in this turn so story_trigger can
                    # fire chain_detection on typed/Web-Speech narrator
                    # turns that don't reach the audio/word/anchor
                    # gates of the other trigger paths. _chain_ctx is
                    # always defined (defaults to {}); story_trigger
                    # reads is_factual_chain defensively.
                    _trigger_diag = _story_trigger.trigger_diagnostic(
                        audio_duration_sec=None,
                        transcript=user_text,
                        chain_ctx=_chain_ctx,
                    )
                except Exception as _diag_exc:
                    logger.warning(
                        "[story-trigger] diagnostic failed (conv=%s): %s",
                        conv_id, _diag_exc,
                    )

                if _trigger_diag is not None:
                    logger.info(
                        "[story-trigger] conv=%s narrator=%s trigger=%s "
                        "words=%s anchors=%s place=%s time=%s person=%s",
                        conv_id,
                        person_id or "<unknown>",
                        _trigger_diag.get("trigger"),
                        _trigger_diag.get("word_count"),
                        _trigger_diag.get("anchor_count"),
                        _trigger_diag.get("place_anchor"),
                        _trigger_diag.get("time_anchor"),
                        _trigger_diag.get("person_anchor"),
                    )
                    _trigger_reason = _trigger_diag.get("trigger")
                    if _trigger_reason and person_id:
                        # turn_id threads through for application-level
                        # idempotency in preserve_turn (chat_ws may
                        # re-fire on reconnect/retry).
                        # Patch E (2026-04-30 polish): normalize whitespace
                        # so a sloppy "  " from the UI cleanly becomes None
                        # rather than a sentinel that won't match any row.
                        _turn_id = (params.get("turn_id") or "").strip() or None

                        # Stories-captured-fs (2026-05-07): resolve
                        # narrator_display_name + audio_id + current_era
                        # so preserve_turn can write the operator-friendly
                        # filesystem mirror (DATA_DIR/stories-captured/...).
                        # All three are best-effort: if any lookup fails,
                        # the DB row still goes through; only the FS mirror
                        # may have less context.
                        _narrator_dn = None
                        try:
                            from .. import db as _db_for_dn
                            _person = _db_for_dn.get_person(person_id) or {}
                            if isinstance(_person, dict):
                                _narrator_dn = (_person.get("display_name") or "").strip() or None
                        except Exception:
                            _narrator_dn = None
                        try:
                            _candidate_id = _story_preservation.preserve_turn(
                                narrator_id=person_id,
                                transcript=user_text,
                                trigger_reason=_trigger_reason,
                                scene_anchor_count=int(
                                    _trigger_diag.get("anchor_count") or 0
                                ),
                                session_id=conv_id,
                                conversation_id=conv_id,
                                turn_id=_turn_id,
                                audio_id=_audio_id_for_archive,
                                current_era=_current_era_for_archive,
                                narrator_display_name=_narrator_dn,
                                # WO-ML-03B Phase 3 multilingual (2026-05-07):
                                # ISO-639-1 language code detected by the STT
                                # engine (or None on Web Speech / typed input).
                                # Threaded into story_candidates.language +
                                # language_probability columns so operator
                                # review can group by language and Phase 4
                                # memoir export renders the correct template.
                                language=_transcript_language_for_archive,
                                language_probability=_transcript_language_prob_for_archive,
                                # WO-LORI-FACTUAL-CHAIN-CAPTURE-01
                                # Phase 4: forward chain detector
                                # output. Empty dict when this turn
                                # is not a factual chain.
                                chain_meta=_chain_meta_for_preserve or {},
                            )
                            logger.info(
                                "[story-trigger] preserved candidate_id=%s "
                                "conv=%s narrator=%s trigger=%s turn_id=%s",
                                _candidate_id, conv_id, person_id,
                                _trigger_reason, _turn_id,
                            )
                        except Exception as _preserve_exc:
                            # LAW 3: preservation failure is loud but
                            # NOT fatal. Chat turn continues so the
                            # narrator session is not interrupted.
                            logger.critical(
                                "[story-trigger][CRITICAL] preserve_turn "
                                "FAILED conv=%s narrator=%s trigger=%s — "
                                "session continues but story was NOT "
                                "saved: %s",
                                conv_id, person_id, _trigger_reason,
                                _preserve_exc,
                                exc_info=True,
                            )
                    elif _trigger_reason and not person_id:
                        # Trigger fired but no narrator association —
                        # can't persist (FK + LAW 3 require narrator_id).
                        # Log so operator can see this happened.
                        logger.warning(
                            "[story-trigger] trigger=%s fired but "
                            "person_id is missing — skipping preservation "
                            "(conv=%s)",
                            _trigger_reason, conv_id,
                        )

        # ── WO-EX-UTTERANCE-FRAME-01 Phase 0-2: observability-only log ──
        # Build the Story Clause Map for this narrator turn and emit a
        # single [utterance-frame] log line. This is OBSERVATION ONLY:
        #   - frame is NOT consumed by the extractor
        #   - frame is NOT consumed by Lori
        #   - frame is NOT consumed by safety
        #   - frame is NOT written to truth or any DB
        #   - frame failure is swallowed silently — never breaks a turn
        #
        # Default-OFF behind HORNELORE_UTTERANCE_FRAME_LOG=1. Goal of
        # Phase 0-2 is to gather real-world per-turn frame output in
        # api.log so we can survey the parser's actual behavior on
        # narrator-shaped text BEFORE wiring any consumer.
        #
        # See WO-EX-UTTERANCE-FRAME-01_Spec.md "Three consumption
        # surfaces" — those land in later phases. v1 is purely
        # representation.
        if (
            os.getenv("HORNELORE_UTTERANCE_FRAME_LOG", "0") in ("1", "true", "True")
            and user_text
            and user_text.strip()
            and not _is_system_directive
        ):
            try:
                from ..services import utterance_frame as _utterance_frame
                _frame = _utterance_frame.build_frame(user_text)
                _fd = _frame.to_dict()
                # Compact one-line summary; downstream tooling can
                # re-parse the full frame from the [utterance-frame]
                # JSON line if needed.
                _clauses_summary = ";".join(
                    f"{c['who_subject_class']}/{c['event_class']}"
                    f"@{c['place'] or '-'}|"
                    f"obj={c.get('object') or '-'}|"
                    f"feel={c.get('feeling') or '-'}|"
                    f"neg={int(c['negation'])}|"
                    f"unc={int(c['uncertainty'])}|"
                    f"hints={','.join(c['candidate_fieldPaths']) or '-'}"
                    for c in _fd["clauses"]
                )
                logger.info(
                    "[utterance-frame] conv=%s narrator=%s conf=%s "
                    "clauses=%d unbound=%s shape=%s",
                    conv_id,
                    person_id or "<unknown>",
                    _fd["parse_confidence"],
                    len(_fd["clauses"]),
                    "Y" if _fd["unbound_remainder"] else "N",
                    _clauses_summary or "-",
                )
            except Exception as _frame_exc:
                # Pure observability — failure is non-fatal and silent
                # at INFO level; turn continues unchanged.
                logger.warning(
                    "[utterance-frame] build_frame failed (conv=%s): %s",
                    conv_id, _frame_exc,
                )

        # ── WO-LIFEMAP-TRAVELS-SHELF-AND-NARRATION-01 Phases 2+3 ──────
        # Trip narration capture: the narrator TALKS, the SYSTEM builds
        # the route. Deterministic parser (trip_narration_capture) —
        # Lori never writes structure (principle 6); writes are
        # provisional and conservative (create-only-obvious, never
        # delete, operator rows never moved).
        #
        # Gate: HORNELORE_TRIP_NARRATION
        #   0 (default) -> off entirely
        #   log         -> parse + [trip-narration] log, ZERO writes
        #                  (the spec's dry-run rollout stage)
        #   1           -> parse + provisional writes
        # Scope: only fires when the narrator has a trip open on the
        # Travels shelf (runtime71.active_trip_id) — general chat is
        # never trip-parsed. Failure never breaks the turn.
        _trip_narration_mode = os.getenv("HORNELORE_TRIP_NARRATION", "0").strip().lower()
        if (
            _trip_narration_mode in ("log", "1", "true")
            and user_text
            and user_text.strip()
            and not _is_system_directive
            and person_id
        ):
            try:
                _rt71_trip = (params.get("runtime71") or {})
                _active_trip_id = _rt71_trip.get("active_trip_id")
                # BUG-TRAVELS-ZERO-TRIP-NARRATION-HOOK-NEVER-CREATES-TRIP-01
                # (review 2026-07-05): zero-trip narration must be able
                # to CREATE the first trip — the shelf-open flag scopes
                # the hook without opening general chat to trip parsing.
                _shelf_open = bool(_rt71_trip.get("travels_shelf_open"))
                if _active_trip_id or _shelf_open:
                    from ..services import trip_narration_capture as _tnc
                    _tn_parse = _tnc.parse_trip_narration(user_text)
                    logger.info(
                        "[trip-narration] conv=%s trip=%s conf=%s start=%s "
                        "stops=%s suppressed=%s corrections=%d obs=%d mode=%s",
                        conv_id, _active_trip_id or "<new-trip-scope>",
                        _tn_parse.get("confidence"),
                        _tn_parse.get("start_place") or "-",
                        [s["place"] for s in _tn_parse.get("stops", [])] or "-",
                        _tn_parse.get("suppressed") or "-",
                        len(_tn_parse.get("corrections", [])),
                        len(_tn_parse.get("observations", [])),
                        _trip_narration_mode,
                    )
                    if (_trip_narration_mode in ("1", "true")
                            and _tn_parse.get("confidence") != "none"):
                        _tn_out = _tnc.apply_trip_narration(
                            _tn_parse, person_id=person_id,
                            active_trip_id=_active_trip_id,
                        )
                        if _tn_out.get("applied"):
                            logger.info(
                                "[trip-narration] writes: trip=%s added=%s "
                                "reordered=%s",
                                _tn_out.get("trip_id"),
                                _tn_out.get("stops_added"),
                                _tn_out.get("reordered"),
                            )
            except Exception as _tn_exc:
                logger.warning(
                    "[trip-narration] hook failed (conv=%s): %s — turn continues",
                    conv_id, _tn_exc,
                )

        # ── WO-TRIP-LORI-ANSWER-CAPTURE-01 Step 2: trip STORY capture ────
        # Sibling to trip-narration above, but the OTHER lane: narration
        # captures route/structure (places, order); THIS captures memoir
        # material (the narrator's answer to a trip-scoped Lori question) as
        # a CANDIDATE trip_location_notes row (source_type=lori, both
        # promotion flags OFF — never auto-promoted). Default-OFF flag
        # HORNELORE_TRIP_STORY_CAPTURE (checked inside the service).
        # NON-FATAL: capture never blocks the turn, never dispatches a
        # prompt, never mutates runtime71. Skips SYSTEM/operator directives.
        # Uses the prior-turn trip-scope memory stamped where the trip
        # interview-context block is (not) injected below.
        # WO-TRAVEL-DOC-UI-LAB-02: _modal_capture_res holds THIS turn's
        # modal capture result (never a stale prior-turn one) so the
        # Day Capture deterministic ack below can key off it safely.
        _modal_capture_res = None
        if (
            user_text
            and user_text.strip()
            and not _is_system_directive
        ):
            try:
                from ..services import trip_story_capture as _tsc
                if _tsc.capture_enabled():
                    _tsc_prev = _TRIP_PREV_LORI.get(conv_id) or {}
                    # WO-TRAVEL-DOC-LORI-MODAL-01: the Travel Doc modal
                    # sends surface=travel_doc_modal + an explicit
                    # modal_scope — capture through the modal path
                    # (trip-scoped by construction, provenance stamped,
                    # shelf state irrelevant). All other turns keep the
                    # runtime71/shelf path unchanged.
                    if (params.get("surface") or "") == "travel_doc_modal":
                        _tsc_res = _tsc.capture_modal_turn(
                            person_id,
                            _normalized_modal_scope(params, conv_id),
                            user_text,
                            previous_lori_text=_tsc_prev.get("lori_text"),
                            conv_id=conv_id,
                            turn_id=(params.get("turn_id")
                                     or _audio_id_for_archive),
                        )
                        _modal_capture_res = _tsc_res
                    else:
                        _tsc_res = _tsc.capture_for_turn(
                            person_id,
                            params.get("runtime71"),
                            user_text,
                            previous_lori_text=_tsc_prev.get("lori_text"),
                            previous_prompt_kind=_tsc_prev.get("prompt_kind"),
                            conv_id=conv_id,
                            turn_id=(params.get("turn_id") or _audio_id_for_archive),
                        )
                    _TRIP_LAST_CAPTURE[conv_id] = _tsc_res
                    _cap_conv_cache(_TRIP_LAST_CAPTURE)
                    logger.info(
                        "[chat_ws][trip-story-capture] conv=%s captured=%s "
                        "reason=%s scope=%s note=%s",
                        conv_id, _tsc_res.get("captured"),
                        _tsc_res.get("reason"), _tsc_res.get("scope"),
                        (_tsc_res.get("note_id") or "-"),
                    )
            except Exception as _tsc_exc:
                logger.warning(
                    "[chat_ws][trip-story-capture] skipped (conv=%s): %s "
                    "— turn continues", conv_id, _tsc_exc,
                )

        # ── WO-NARRATIVE-CUE-LIBRARY-01 Phase 4: observability-only log ──
        # Run the narrative cue detector against this narrator turn and
        # emit a single [lori-cue] log line. This is OBSERVATION ONLY:
        #   - cue is NOT consumed by Lori response composer (Phase 5+)
        #   - cue is NOT consumed by extractor (would violate LAW 3)
        #   - cue is NOT consumed by safety
        #   - cue is NOT written to truth or any DB
        #   - cue failure is swallowed silently — never breaks a turn
        #
        # Default-OFF behind HORNELORE_LORI_CUE_LOG=1. Goal of Phase 4
        # is to gather real-world per-turn cue selections in api.log so
        # the library JSON can be tuned with measured evidence (using
        # scripts/run_narrative_cue_eval.py from Phase 3) BEFORE
        # wiring the cue into Lori's response composer.
        #
        # Section context (current_section) is not threaded into chat_ws
        # today; Phase 4 passes None and skips the section bonus
        # tie-break. If the operator side wants to inform tie-breaks
        # later, the path is to thread the active section from interview
        # state into the chat turn payload — separate WO.
        #
        # See WO-NARRATIVE-CUE-LIBRARY-01_PHASE3_HARNESS.md for the
        # tuning loop and PHASE2_CALIBRATION.md for the locked detector
        # behavior. v1 is purely the listener-aid representation; the
        # cue library may NEVER write truth (LAW from the WO spec).
        if (
            os.getenv("HORNELORE_LORI_CUE_LOG", "0") in ("1", "true", "True")
            and user_text
            and user_text.strip()
            and not _is_system_directive
        ):
            try:
                from ..services import narrative_cue_detector as _cue_detector
                _detection = _cue_detector.detect_cues(user_text, current_section=None)
                _top = _detection.top_cue
                if _top is not None:
                    _triggers = ",".join(_top.trigger_matches) or "-"
                    logger.info(
                        "[lori-cue] conv=%s narrator=%s cue_type=%s "
                        "risk=%s score=%d triggers=%s ranked_count=%d",
                        conv_id,
                        person_id or "<unknown>",
                        _top.cue_type,
                        _top.risk_level,
                        _top.score,
                        _triggers,
                        len(_detection.cues),
                    )
                else:
                    logger.info(
                        "[lori-cue] conv=%s narrator=%s cue_type=- "
                        "no_match_reason=%s ranked_count=0",
                        conv_id,
                        person_id or "<unknown>",
                        _detection.no_match_reason or "no_match",
                    )
            except Exception as _cue_exc:
                # Pure observability — failure is non-fatal and silent
                # at INFO level; turn continues unchanged.
                logger.warning(
                    "[lori-cue] detect_cues failed (conv=%s): %s",
                    conv_id, _cue_exc,
                )

        # Memory Archive — ensure session exists and log user message
        #
        # BUG-MODAL-TURNS-ARCHIVED-AS-LIFE-STORY-01 (live, 2026-07-14): this
        # write was gated on person_id ONLY, never on surface, so every Travel
        # Doc Lori MODAL turn was archived into the narrator's LIFE-STORY
        # conversation as something the narrator said. Observed in the Narrator
        # Room: an operator's workspace question ("can you tell me about this
        # photo?") rendered as Christopher's own turn, over and over.
        #
        # That is not cosmetic. peek_at_memoir / compose_memory_echo read these
        # archive sessions to build "what you've shared so far" — so operator
        # workspace chatter becomes narrator memory, and Lori reads it back to
        # them as their own words. It breaks the locked two-surface rule
        # (Narrator Room = life story; Travel Doc modal = trip building) and
        # the "no operator leakage" principle in one move.
        #
        # The modal already has its OWN capture path (trip_story_capture
        # .capture_modal_turn -> trip_location_notes, source_surface=
        # travel_doc_modal). Life-story archiving is pure leakage. Skip it.
        _archive_surface = (params.get("surface") or "narrator").strip().lower()
        _skip_life_story_archive = (_archive_surface == "travel_doc_modal")
        if _skip_life_story_archive:
            logger.info(
                "[chat_ws][archive] skipping life-story archive for modal turn "
                "(conv=%s) — trip capture owns this surface", conv_id)
        if person_id and not _skip_life_story_archive:
            archive_ensure_session(
                person_id=person_id,
                session_id=conv_id,
                mode="chat_ws",
                title="Chat (WS)",
                extra_meta={"ws": True},
            )
            # _audio_id_for_archive is extracted at function top so it
            # reaches both the story-trigger preserve_turn call and this
            # archive write. See BUG-ARCHIVE-AUDIO-NOT-LINKED-TO-TRANSCRIPT-01.

            archive_append_event(
                person_id=person_id,
                session_id=conv_id,
                role="user",
                content=user_text,
                meta={"ws": True},
                current_era=_current_era_for_archive,  # WO-LORI-MEMORY-ECHO-ERA-STORIES-01 Phase 1
                audio_id=_audio_id_for_archive,         # BUG-ARCHIVE-AUDIO-NOT-LINKED-TO-TRANSCRIPT-01
                language=_transcript_language_for_archive,  # WO-ML-03B Phase 3 multilingual
            )

        # ── WO-LORI-SOFTENED-RESPONSE-01: per-turn turn_count + softened read ─
        # Mirrors interview.py:302/305 — every interview-style chat turn
        # ticks the per-session turn_count and reads the current softened
        # state. Without this unconditional increment, the existing
        # set_session_softened math (softened_until_turn = current + 3)
        # is broken because turn_count only ticked on safety triggers.
        # Both calls wrapped in try/except — never let counter or read
        # failure kill a chat turn. Default-safe: missing state is
        # treated as "not softened" by get_session_softened_state.
        #
        # ensure_interview_session is called by the safety block below
        # before save_segment_flag; we also need the parent row to exist
        # before increment_session_turn here, so we ensure-up-front.
        # Idempotent INSERT OR IGNORE — safe to call every turn.
        #
        # _safety_result / _safety_scan_failed / _safety_pattern_triggered
        # are initialized unconditionally by the WO-POST-REVIEW-SAFETY-
        # DRAFT-EXPORT-HARDENING-01 preflight near the top of this
        # function — no defensive re-init needed here.

        # ── BUG-LORI-IDENTITY-META-QUESTION-DETERMINISTIC-ROUTE-01 ───────
        # 2026-05-09 (Mary's session) — three stacked failures from one
        # class of question: identity-denial ("I don't have a name"),
        # 988 false-positive on "are you safe to talk to?", and the
        # "AI." 3-char stub on "what is an AI?". All three vanish when
        # we intercept narrator meta-questions BEFORE the safety
        # classifier and BEFORE the LLM, and reply deterministically
        # in the narrator's language with a warm locked answer.
        #
        # The detection module is pure-stdlib (LAW 3 isolated, no LLM,
        # no DB). When it matches, we:
        #   (1) Skip the LLM safety classifier — Mary's "are you safe"
        #       must NOT route to 988. WO-POST-REVIEW-SAFETY-DRAFT-
        #       EXPORT-HARDENING-01 (2026-07-24): the DETERMINISTIC
        #       pattern scan is no longer skippable — it already ran in
        #       the preflight above, BEFORE this intercept. A benign
        #       meta question ("Are you safe to talk to?") produces no
        #       trigger, so this intercept still wins the route and the
        #       LLM classifier stays skipped for it (the "Mary fix",
        #       2026-05-09, is preserved). A meta-shaped question that
        #       ALSO carries a distress pattern is now caught by the
        #       preflight and this intercept is skipped entirely.
        #   (2) Override turn_mode to "meta_question" so the dispatcher
        #       below emits the deterministic text
        #   (3) Carry the composed answer in _meta_question_answer for
        #       the dispatcher to use
        #
        # Default-on, no env flag — this is a correctness fix, not a
        # feature. Failure of detection or composition is non-fatal:
        # the turn falls through to normal safety + LLM behavior.
        _meta_question_answer = None  # type: ignore[assignment]
        _is_meta_question = False
        if (user_text and user_text.strip() and not _is_system_directive
                and not _safety_forced_interview):
            try:
                from ..services.lori_meta_question import detect_and_compose as _meta_dac
                # Detect narrator language for locale routing. Mirrors
                # the same posture as compose_memory_echo Spanish branch.
                _meta_lang = "en"
                try:
                    from ..services.lori_spanish_guard import looks_spanish as _meta_looks_es
                    if _meta_looks_es(user_text or ""):
                        _meta_lang = "es"
                except Exception:
                    _meta_lang = "en"
                _meta_question_answer = _meta_dac(user_text, target_language=_meta_lang)
                if _meta_question_answer is not None:
                    _is_meta_question = True
                    logger.info(
                        "[chat_ws][meta-question][deterministic] conv=%s "
                        "primary=%s categories=%s lang=%s",
                        conv_id,
                        _meta_question_answer.primary_category,
                        ",".join(_meta_question_answer.categories_matched),
                        _meta_question_answer.language,
                    )
            except Exception as _meta_exc:
                # Detection failure must not break the turn. Fall through
                # to normal safety + LLM behavior.
                logger.warning(
                    "[chat_ws][meta-question] detect failed conv=%s: %s",
                    conv_id, _meta_exc,
                )
                _meta_question_answer = None
                _is_meta_question = False

        # ── Trip direct-answer intercept (WO-TRIP-LORI-REAL-BETA-USABILITY
        # -01 Phase 1) — sibling to the meta-question intercept above. When a
        # trip is open + owned and the narrator asks what Lori knows/remembers
        # about the trip (or a place on it, or a photo), answer DETERMINISTIC-
        # ally from approved trip context instead of deflecting. Reuses the
        # meta-question dispatch machinery by populating _meta_question_answer
        # with a small trip-answer shim (so skip-safety / skip-LLM / emit all
        # work unchanged). Gated inside the service (flag + active trip + shelf
        # open + ownership + question detection). Non-fatal.
        # WO-TRAVEL-DOC-LORI-MODAL-02 live fix (2026-07-10): modal turns
        # MUST hit the deterministic modal answerer FIRST — the live demo
        # showed 'what can you tell me about that photo' reaching the raw
        # LLM ('I'll respond with a neutral message' meta leak) because
        # only the Mark Twain gate called the service, not chat_ws.
        # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01: gated on the
        # authoritative safety route boolean — a distress turn must never
        # be answered with modal trip context.
        if ((params.get("surface") or "") == "travel_doc_modal"
                and not _is_meta_question and user_text
                and user_text.strip() and not _is_system_directive
                and not _safety_forced_interview):
            try:
                from ..services import travel_doc_lori_modal as _tdm
                _msc = _normalized_modal_scope(params, conv_id) or {}
                _modal_scope = _tdm.build_modal_scope(
                    person_id=person_id,
                    active_trip_id=_msc.get("active_trip_id"),
                    active_trip_region_id=_msc.get("active_trip_region_id"),
                    active_trip_stop_id=_msc.get("active_trip_stop_id"),
                    active_photo_link_id=_msc.get("active_photo_link_id"),
                    conv_id=conv_id,
                    selected_kind=_msc.get("selected_kind") or "trip",
                    active_trip_day_id=_msc.get("active_trip_day_id"),
                ) if _msc.get("active_trip_id") else None
                _modal_text = _tdm.answer_modal_direct_question(
                    person_id, _modal_scope, user_text) if _modal_scope else None
                _modal_category = "travel_doc_modal_direct"
                # WO-TRAVEL-DOC-UI-LAB-02 items 6+7 (Day Capture mode):
                # not a direct question, the modal is day-scoped, and THIS
                # turn's capture saved the memory -> reply with the
                # deterministic capture ack (day + narrator's own words)
                # instead of the LLM. Kills the chain anchor-echo garbage
                # on the operator capture surface by construction.
                if (not _modal_text and _modal_scope
                        and _modal_scope.get("active_trip_day_id")
                        and (_modal_capture_res or {}).get("captured")
                        and (_modal_capture_res or {}).get("reason")
                        in ("meaningful_trip_answer", "duplicate")):
                    from ..services import trip_repository as _trip_repo
                    _day_row = _trip_repo.trip_day_get(
                        _modal_scope["active_trip_day_id"])
                    if (_day_row and _day_row.get("trip_id")
                            == _modal_scope.get("active_trip_id")):
                        _modal_text = _tdm.compose_day_capture_ack(
                            _day_row, _modal_capture_res, user_text)
                        if _modal_text:
                            _modal_category = "travel_doc_day_capture_ack"
                if _modal_text:
                    class _ModalAnswerShim(object):
                        text = _modal_text
                        primary_category = _modal_category
                        categories_matched = [_modal_category]
                        language = "en"
                    _meta_question_answer = _ModalAnswerShim()
                    _is_meta_question = True
                    logger.info(
                        "[chat_ws][modal-direct-answer] conv=%s handled=true "
                        "category=%s", conv_id, _modal_category)
            except Exception as _tdm_exc:
                logger.warning(
                    "[chat_ws][modal-direct-answer] failed conv=%s: %s "
                    "— turn continues", conv_id, _tdm_exc)

        # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01: same gate — a
        # distress turn must never get a deterministic trip answer.
        if (not _is_meta_question and user_text and user_text.strip()
                and not _is_system_directive
                and not _safety_forced_interview):
            try:
                from ..services import trip_interview_context as _tdic
                _trip_direct_text = _tdic.direct_answer_for_turn(
                    person_id, params.get("runtime71"), user_text)
                if _trip_direct_text:
                    class _TripAnswerShim(object):
                        text = _trip_direct_text
                        primary_category = "trip_direct"
                        categories_matched = ["trip_direct"]
                        language = "en"
                    _meta_question_answer = _TripAnswerShim()
                    _is_meta_question = True
                    # WO-TRIP-NARRATOR-BRIDGE-01: two different
                    # questions reach this branch now. A log line that
                    # names only the older one would send the next
                    # reader looking for a trip-knowledge match that
                    # never happened. Structural label only -- never the
                    # narrator's text.
                    _tda_reason = (
                        "photo_capability_question"
                        if _tdic.is_photo_capability_question(user_text)
                        else "trip_knowledge_question")
                    logger.info(
                        "[chat_ws][trip-direct-answer] conv=%s handled=true "
                        "reason=%s", conv_id, _tda_reason)
            except Exception as _tda_exc:
                logger.warning(
                    "[chat_ws][trip-direct-answer] failed conv=%s: %s "
                    "— turn continues", conv_id, _tda_exc)

        # ── BUG-LORI-FACTUAL-OVER-SENSORY-PROBE-01 ──────────────────────
        # Witness mode + meta-feedback deterministic intercept. Kent's
        # 2026-05-09 session walked him out: Lori responded to his
        # 5-fact basic-training answer by asking about scenery, then
        # responded to "stop the sensory probes" by asking for sights/
        # sounds/smells. Sibling lane to the meta-question intercept
        # above — same architecture, different detection set.
        #
        # Detection types:
        #   META_FEEDBACK — narrator told Lori her behavior is wrong
        #     ("you are being vague", "stop sensory", "I want facts")
        #   STRUCTURED_NARRATIVE — multi-event chronological factual
        #     turn (admissions test → train → exam → score → ...)
        #
        # When fires: skip LLM, emit deterministic continuation
        # invitation with NO sensory/feeling/scenery/camaraderie probe.
        # Skipped if meta-question already fired (mutually exclusive).
        # ── BUG-LORI-SESSION-LANGUAGE-CONTRACT-01 (2026-05-10) ──────────
        # Resolve the session language contract. Two layers:
        #
        # Layer 1: HARDCODED english-lock — bisectable, ships in code
        # review, can't be lost in a DB write. Kent's harness UUID is
        # locked here so the deep-witness replay can never produce
        # Spanish/Spanglish regardless of profile_json state. As
        # operator narrators get instantiated for parent sessions
        # (Kent / Janice / Mary / Marvin), append their UUIDs here.
        # The hardcoded lock takes precedence over profile_json.
        #
        # Layer 2: profile_json session_language_mode pin (operator
        # script: scripts/set_session_language_mode.py). When unset
        # (legacy narrators), falls back to looks_spanish() heuristic
        # for backward compat with Spanish-tracked narrators (Melanie
        # Zollner). The pin is the operator's contract; Lori never
        # guesses for narrators with the field set.
        #
        # Three values:
        #   "english" — Lori always replies English. Per-turn
        #               looks_spanish on narrator text is advisory log
        #               only, never overrides routing. Post-output
        #               Spanish-scaffolding repair guard fires.
        #   "spanish" — Lori always replies Spanish.
        #   "mixed"   — Lori may follow per-turn narrator language.
        #
        # Kent harness 2026-05-09 21:46:53 motivating evidence:
        # English narrator turns containing "fiancée" + "Once" or
        # "attaché" + "son" tripped looks_spanish() despite being
        # unambiguously English, producing "Capté Nike, Detroit, y
        # Michigan" / "Tú worked for was General Peter Schmick" /
        # "¿Qué pasó después?" Spanglish output on Kent's English
        # interview.
        _session_lang_mode: Optional[str] = None

        # Layer 1 (emergency safety belt): per-UUID english lock.
        # See _EMERGENCY_ENGLISH_LOCK_PERSON_IDS docstring for removal
        # criteria — this is NOT the product design.
        if person_id and person_id in _EMERGENCY_ENGLISH_LOCK_PERSON_IDS:
            _session_lang_mode = "english"
            logger.info(
                "[chat_ws][lang-contract] EMERGENCY english lock "
                "conv=%s person=%s "
                "(see _EMERGENCY_ENGLISH_LOCK_PERSON_IDS docstring)",
                conv_id, person_id,
            )

        # Layer 2: profile_json pin (only if hardcoded didn't already win)
        # _early_profile_seed is hoisted so downstream consumers (the
        # seeded-fact intake guard at the response-guards call site)
        # can read it on EVERY path, including emergency-locked
        # narrators and seed-read failures (BUG fix 2026-07-06: it was
        # previously only bound inside this conditional try).
        _early_profile_seed: Dict[str, Any] = {}
        if _session_lang_mode is None:
            try:
                from ..prompt_composer import _build_profile_seed as _early_seed
                _early_profile_seed = _early_seed(person_id) if person_id else {}
                _slm = (_early_profile_seed or {}).get("session_language_mode")
                if _slm in ("english", "spanish", "mixed"):
                    _session_lang_mode = _slm
                    logger.info(
                        "[chat_ws][lang-contract] profile pin conv=%s mode=%s",
                        conv_id, _session_lang_mode,
                    )
            except Exception as _slm_exc:
                logger.warning(
                    "[chat_ws][lang-contract] early seed read failed "
                    "conv=%s: %s", conv_id, _slm_exc,
                )

        _witness_answer = None  # type: ignore[assignment]
        _is_witness_mode = False
        # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01: witness routing
        # (META_FEEDBACK ack AND structured-narrative receipt mode) may not
        # take over a safety-forced turn — "You are being vague. I want to
        # kill myself." must reach the safety cascade, not a witness ack.
        if (
            user_text and user_text.strip()
            and not _is_system_directive
            and not _is_meta_question
            and not _safety_forced_interview
        ):
            try:
                from ..services.lori_witness_mode import detect_and_compose as _wm_dac
                _wm_lang = "en"
                if _session_lang_mode == "english":
                    _wm_lang = "en"
                    logger.info(
                        "[chat_ws][lang-contract] english-locked conv=%s",
                        conv_id,
                    )
                elif _session_lang_mode == "spanish":
                    _wm_lang = "es"
                    logger.info(
                        "[chat_ws][lang-contract] spanish-locked conv=%s",
                        conv_id,
                    )
                elif _session_lang_mode == "mixed":
                    try:
                        from ..services.lori_spanish_guard import looks_spanish as _wm_looks_es
                        if _wm_looks_es(user_text or ""):
                            _wm_lang = "es"
                    except Exception:
                        _wm_lang = "en"
                    logger.info(
                        "[chat_ws][lang-contract] mixed-mode conv=%s "
                        "per_turn_lang=%s",
                        conv_id, _wm_lang,
                    )
                else:
                    # Unset profile pin — fall back to looks_spanish for
                    # backward compat with narrators created before the
                    # contract field landed. Logged as advisory so any
                    # surprise routing surfaces in api.log.
                    try:
                        from ..services.lori_spanish_guard import looks_spanish as _wm_looks_es
                        if _wm_looks_es(user_text or ""):
                            _wm_lang = "es"
                            logger.info(
                                "[chat_ws][lang-contract] unset profile pin; "
                                "looks_spanish advisory routed conv=%s lang=es",
                                conv_id,
                            )
                    except Exception:
                        _wm_lang = "en"
                _witness_answer = _wm_dac(user_text, target_language=_wm_lang)
                if _witness_answer is not None:
                    _is_witness_mode = True
                    logger.info(
                        "[chat_ws][witness][deterministic] conv=%s "
                        "type=%s sub=%s anchor=%r lang=%s",
                        conv_id,
                        _witness_answer.detection_type,
                        _witness_answer.sub_type,
                        _witness_answer.factual_anchor,
                        _witness_answer.language,
                    )
            except Exception as _wm_exc:
                logger.warning(
                    "[chat_ws][witness] detect failed conv=%s: %s",
                    conv_id, _wm_exc,
                )
                _witness_answer = None
                _is_witness_mode = False

        _session_turn_count: int = 0
        _softened_state: Dict[str, Any] = {
            "interview_softened": False, "softened_until_turn": 0, "turn_count": 0,
        }
        # Gate softened-state reads behind the same env flag as the
        # composer-side directive injection. Without this, the wrapper
        # could see softened=True from leftover DB state while the
        # composer ignores it (because flag is off) — Lori would get a
        # normal interview prompt but the wrapper would treat the
        # output as safety-exempt. Match composer + wrapper to the same
        # gate so flag-off means "do nothing softened anywhere."
        #
        # WO-LEAN-LORI-RUNTIME-01 Phase 3B: parked outranks this flag too.
        # Softened mode is a SAFETY state, and rows written before parking
        # do not expire when the feature is switched off -- a narrator who
        # triggered softened mode last week would still be met by a
        # softened Lori today, produced by a feature that is supposed to be
        # inactive, from a prompt that no longer carries the safety
        # protocol that softened mode was written to accompany.
        #
        # This suppresses the READ. It deliberately does not delete, clear
        # or expire the stored rows: they are part of the preserved
        # evidence, and reactivation must find the session state exactly as
        # it was left. Parking is not a data migration.
        _softened_response_enabled = (
            (not _safety_parked)
            and os.environ.get(
                "HORNELORE_SOFTENED_RESPONSE", "0"
            ).strip().lower() in ("1", "true", "yes", "on"))
        try:
            ensure_interview_session(conv_id, person_id)
            _session_turn_count = increment_session_turn(conv_id)
        except Exception as _tc_exc:
            logger.warning(
                "[chat_ws][softened] turn_count increment failed conv=%s: %s",
                conv_id, _tc_exc,
            )
        if _softened_response_enabled:
            try:
                _softened_state = get_session_softened_state(conv_id)
            except Exception as _ss_exc:
                logger.warning(
                    "[chat_ws][softened] state read failed conv=%s: %s",
                    conv_id, _ss_exc,
                )

        # Operator-facing log marker so api.log shows softened state per
        # turn. Never logs narrator content; just flag + state + trigger
        # + remaining turns.
        #
        # WO-LORI-SOFTENED-MODE-PERSISTENCE-01 (2026-06-14): log line
        # extended with state ("softened" / "softened_exiting") +
        # trigger ("acute" / "past_tense_acknowledge") so operators can
        # see which prompt block fired and when the recovering-mode
        # transition lands.
        _softened_machine_state = (_softened_state.get("state") or "normal")
        if _softened_machine_state in ("softened", "softened_exiting"):
            try:
                from ..services.lori_softened_response import turns_remaining as _trem
                _remaining = _trem(_softened_state)
            except Exception:
                _remaining = 0
            logger.info(
                "[chat_ws][softened] active conv=%s state=%s trigger=%s "
                "turns_remaining=%d turn_count=%d until=%d",
                conv_id,
                _softened_machine_state,
                (_softened_state.get("trigger") or ""),
                _remaining,
                _softened_state.get("turn_count", 0),
                _softened_state.get("softened_until_turn", 0),
            )
        elif _softened_response_enabled and _softened_state.get("softened_until_turn", 0) > 0:
            # First turn AFTER softened window closes — useful operator
            # signal that the session has returned to normal cadence.
            logger.info(
                "[chat_ws][softened] inactive conv=%s "
                "(last until_turn=%d, now turn_count=%d)",
                conv_id,
                _softened_state.get("softened_until_turn", 0),
                _softened_state.get("turn_count", 0),
            )

        # ── WO-LORI-STORY-FIRST-PHASE-1-01 (2026-06-14) ─────────────────────
        # Compute story momentum on the narrator turn, extract + persist
        # thread candidates, and select a surfacing target if eligible.
        # All four pieces run under a single HORNELORE_STORY_FIRST_PHASE_1
        # flag; off by default. When off, the downstream comm-control
        # wrapper sees `momentum_mode="normal"` + `session_hierarchy_state
        # =None` which means the Phase 1 validators are vacuously inactive
        # — byte-stable to pre-WO behavior.
        _phase_1_enabled_now = os.environ.get(
            "HORNELORE_STORY_FIRST_PHASE_1", "0",
        ).strip().lower() in ("1", "true", "yes", "on")
        _phase_1_momentum_mode = "normal"
        _phase_1_thread_to_surface: Optional[Dict[str, Any]] = None
        _phase_1_thread_surface_text = ""
        if _phase_1_enabled_now and user_text and user_text.strip() and not _is_system_directive:
            try:
                from ..services.story_momentum import (
                    score_story_momentum as _sm_score,
                )
                from ..services.thread_bank import (
                    extract_thread_candidates as _tb_extract,
                    bank_new_threads as _tb_bank,
                    select_surfacing_target as _tb_select,
                    build_surfacing_text as _tb_build_surface,
                )
                # uninterrupted_run defaults to 0 — full session-history
                # walk is parked behind a sub-task (would require an
                # archive query on every turn; cheaper to start with 0
                # and let the other 6 signals drive momentum).
                _phase_1_score = _sm_score(user_text, uninterrupted_run=0)
                _phase_1_momentum_mode = _phase_1_score.mode
                logger.info(
                    "[chat_ws][story_first] momentum conv=%s mode=%s "
                    "composite=%.3f wc=%d ne=%d tmp=%d sen=%d seq=%d "
                    "dlg=%s",
                    conv_id, _phase_1_score.mode,
                    _phase_1_score.composite,
                    _phase_1_score.word_count,
                    _phase_1_score.named_entity_count,
                    _phase_1_score.temporal_marker_count,
                    _phase_1_score.sensory_token_count,
                    _phase_1_score.sequence_marker_count,
                    _phase_1_score.dialogue_present,
                )

                # Extract + persist thread candidates from this narrator turn.
                _phase_1_threads = _tb_extract(
                    user_text, source_turn_index=int(_session_turn_count or 0),
                )
                if _phase_1_threads:
                    _phase_1_new_ids = _tb_bank(conv_id, _phase_1_threads)
                    logger.info(
                        "[chat_ws][story_first][thread_bank] extracted=%d "
                        "banked=%d conv=%s anchors=%s",
                        len(_phase_1_threads), len(_phase_1_new_ids),
                        conv_id,
                        ",".join(t.anchor for t in _phase_1_threads[:6]),
                    )

                # Select surfacing target (None when momentum suppresses
                # OR no eligible thread exists).
                _phase_1_thread_to_surface = _tb_select(
                    conv_id,
                    current_turn_index=int(_session_turn_count or 0),
                    momentum_mode=_phase_1_momentum_mode,
                    narrator_text=user_text,
                )
                if _phase_1_thread_to_surface:
                    _phase_1_thread_surface_text = _tb_build_surface(
                        _phase_1_thread_to_surface,
                        open_question="What was that like?",
                        connecting_phrase_index=int(_session_turn_count or 0),
                    )
                    logger.info(
                        "[chat_ws][story_first][thread_bank] surfacing "
                        "conv=%s thread_id=%s anchor=%r",
                        conv_id,
                        _phase_1_thread_to_surface.get("id"),
                        _phase_1_thread_to_surface.get("thread_anchor"),
                    )
            except Exception as _phase_1_exc:
                # Phase 1 must never break a turn. Log + fall through.
                logger.warning(
                    "[chat_ws][story_first] dispatch failed conv=%s: %s",
                    conv_id, _phase_1_exc,
                )

        # ── WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase D Tier 3 ──
        # Bio anchored asker — eligibility check + gap selection. Runs
        # AFTER the Phase 1 momentum + thread bank block so we can
        # consume the momentum score. Gated by HORNELORE_BIO_ANCHORED_
        # ASKER (default OFF). Per WO §Tier 3 + Defenses 1+2+3:
        # eligibility chain enforces caps + chapter health floor; the
        # placeholder bio_facts row carries the continuation metric
        # scaffold for Defense 1 telemetry. The next-turn pipeline
        # backfills the metric via update_metric_after_response (TBD
        # wiring in a follow-up commit; today's commit ships the
        # service + the fire-ask path).
        _bio_anchored_surface_text = ""
        _bio_anchored_fact_id: Optional[str] = None
        _bio_anchored_enabled_now = os.environ.get(
            "HORNELORE_BIO_ANCHORED_ASKER", "0",
        ).strip().lower() in ("1", "true", "yes", "on")
        if (
            _bio_anchored_enabled_now
            and user_text and user_text.strip()
            and not _is_system_directive
            and person_id
        ):
            try:
                from ..services.bio_anchored_asker import (
                    evaluate_eligibility as _ba_eligibility,
                    pick_anchored_gap as _ba_pick,
                    compose_surface_text as _ba_compose,
                    fire_anchored_ask as _ba_fire,
                )
                # Build the session-level signals the asker needs.
                # turns_since_last_ask + asks_this_session + word
                # count history are not yet maintained in chat_ws
                # state (deferred to a follow-up that adds session
                # turn-history walking); for v1 we provide
                # conservative defaults that pass the structural gates
                # — the eligibility chain itself catches the real
                # rate-limit when chat_ws state plumbing arrives.
                _momentum_score = 0.0
                try:
                    _momentum_score = float(
                        getattr(_phase_1_score, "composite", 0.0) or 0.0,
                    )
                except Exception:
                    _momentum_score = 0.0
                _ba_elig = _ba_eligibility(
                    narrator_id=person_id,
                    momentum_score=_momentum_score,
                    session_turn_word_counts=[],
                    turns_since_last_ask=999,
                    asks_this_session=0,
                )
                if _ba_elig.eligible:
                    _ba_gap = _ba_pick(person_id, user_text)
                    if _ba_gap is not None:
                        _bio_anchored_surface_text = _ba_compose(
                            _ba_gap, user_text,
                        )
                        try:
                            _bio_anchored_fact_id = _ba_fire(
                                person_id, _ba_gap,
                                session_id=conv_id,
                                turn_id=getattr(req, "turn_id", None) if "req" in dir() else None,
                                session_turn_word_counts=[],
                            )
                            logger.info(
                                "[chat_ws][bio_anchored] fired "
                                "conv=%s field=%s anchor=%r row=%s",
                                conv_id, _ba_gap.field_key,
                                _ba_gap.matched_anchor,
                                _bio_anchored_fact_id,
                            )
                        except Exception as _fire_exc:
                            logger.warning(
                                "[chat_ws][bio_anchored] fire failed "
                                "conv=%s: %s", conv_id, _fire_exc,
                            )
                            _bio_anchored_surface_text = ""
                else:
                    logger.info(
                        "[chat_ws][bio_anchored] ineligible "
                        "conv=%s reason=%s",
                        conv_id, _ba_elig.reason,
                    )
            except Exception as _ba_exc:
                # Asker must never break a turn — log + fall through.
                logger.warning(
                    "[chat_ws][bio_anchored] dispatch failed conv=%s: %s",
                    conv_id, _ba_exc,
                )

        # ── WO-LORI-SAFETY-INTEGRATION-01 Phase 1: chat-path safety scan ─────
        # Mirrors interview.py:269-307. Runs BEFORE turn_mode dispatch so a
        # triggered turn cannot be silently routed through memory_echo or
        # correction composers (which are deterministic and not safety-aware).
        # On trigger: persist segment flag, set softened mode, emit WS event
        # for the existing UI overlay (safety-ui.js), notify operator, force
        # turn_mode to "interview" so the LLM path runs and the ACUTE SAFETY
        # RULE in prompt_composer.py:108-193 fires. We do NOT short-circuit
        # the response — Lori still produces a turn, but under safety-side
        # prompt guidance.
        #
        # WO-LORI-SAFETY-INTEGRATION-01 Phase 7 LV_ENABLE_SAFETY
        # kill-switch: the flag read, the DEVELOPER-ONLY framing, and the
        # per-turn [chat_ws][safety][KILL-SWITCH] warning now live with
        # the WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 preflight
        # near the top of this function, because the deterministic scan
        # itself moved there. `_safety_enabled` is that same flag.
        #
        # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 (2026-07-24):
        # this block CONSUMES the preflight scan result — scan_answer is
        # NEVER called a second time for the same turn. The old gate here
        # carried `not _is_meta_question`, which let the meta/modal/trip
        # intercepts bypass even the deterministic pattern layer; the
        # preflight closed that. The meta exclusion is preserved ONLY for
        # the LLM second-layer classifier below (the locked "Mary fix":
        # a benign "are you safe to talk to?" must not be 988'd by the
        # LLM classifier — but it IS pattern-scanned now).
        if _safety_enabled and user_text and user_text.strip():
            # ── WO-LORI-SAFETY-INTEGRATION-01 Phase 2: LLM second-layer ──
            # Run the LLM-side classifier after the pattern detector.
            # Composition rule (locked, see WO spec):
            #   - Pattern detector wins on positive detection (always) —
            #     a deterministic positive always beats an LLM negative
            #   - LLM classifier fills gaps — only used when the
            #     deterministic scan SUCCEEDED and did not trigger
            #   - On LLM parse failure or LLM error, fall back to pattern
            #     result (fail-OPEN)
            #   - Never runs for system directives or deterministic
            #     meta-question turns (locked benign-route policy)
            #
            # Default-OFF behind HORNELORE_SAFETY_LLM_LAYER=0. Adds ~1-2s
            # latency per turn when enabled; needs Phase 6 red-team
            # validation before live narrator use.
            #
            # When the LLM detects distressed/ideation/acute on a turn
            # the pattern missed, we synthesize a SafetyResult and let
            # the existing segment_flag + softened-mode + UI overlay
            # pipeline below handle it identically to a pattern hit.
            # The LLM-source attribution is preserved in the log marker
            # [chat_ws][safety][llm_layer] so operators can distinguish.
            if (
                not _safety_scan_failed
                and not _safety_pattern_triggered
                and not _is_meta_question
                and user_text and user_text.strip()
                and not _is_system_directive
            ):
                try:
                    # WO-LORI-SAFETY-LLM-CLASSIFIER-01 (2026-06-14) — swap
                    # from the boolean should_route_to_safety to the four-
                    # route route_safety(). Old boolean wrapper remains for
                    # tests; this hook now consumes the structured route so
                    # past-tense and mortality-reflection don't escalate.
                    from ..safety_classifier import (
                        classify_safety_llm as _classify_llm,
                        route_safety as _route_safety_call,
                        ROUTE_ACUTE as _ROUTE_ACUTE,
                        ROUTE_PAST_TENSE_ACKNOWLEDGE as _ROUTE_PT,
                        ROUTE_MORTALITY_REFLECTION as _ROUTE_MR,
                        ROUTE_NONE as _ROUTE_NONE,
                    )
                    _llm_class = _classify_llm(user_text)
                    _route = _route_safety_call(False, _llm_class)

                    # WO-LORI-SAFETY-LLM-CLASSIFIER-01 §1 — per-session
                    # parse-failure counter. Increments when the
                    # classifier returns parse_ok=False AFTER the
                    # retry-once inside classify_safety_llm. This is
                    # the operator-panel signal that the LLM is
                    # producing malformed JSON for this conversation;
                    # frequent increments mean the prompt or the model
                    # needs attention. Exposed via the module-level
                    # _SAFETY_LLM_PARSE_FAILURES dict (in-memory, cleared
                    # on stack restart — acceptable for a debug signal).
                    if not _llm_class.parse_ok:
                        try:
                            _SAFETY_LLM_PARSE_FAILURES[conv_id] = (
                                _SAFETY_LLM_PARSE_FAILURES.get(conv_id, 0) + 1
                            )
                        except Exception:
                            pass

                    if _route == _ROUTE_ACUTE:
                        logger.warning(
                            "[chat_ws][safety][llm_layer] route=acute "
                            "conv=%s category=%s tense=%s subject=%s "
                            "confidence=%.2f reason=%s",
                            conv_id, _llm_class.category,
                            _llm_class.tense, _llm_class.subject,
                            _llm_class.confidence, _llm_class.reason,
                        )
                        # Synthesize a SafetyResult so the existing
                        # segment_flag / softened / overlay pipeline
                        # below handles it. Map LLM category to the
                        # closest existing pattern-side category.
                        _llm_cat_map = {
                            "acute": "suicidal_ideation",
                            "ideation": "suicidal_ideation_indirect",
                            "distressed": "cognitive_distress",
                        }
                        _safety_result = SafetyResult(
                            triggered=True,
                            category=_llm_cat_map.get(
                                _llm_class.category, "cognitive_distress"
                            ),
                            confidence=_llm_class.confidence,
                        )

                    elif _route == _ROUTE_PT:
                        # WO-LORI-SAFETY-LLM-CLASSIFIER-01 §3 + §4 — past-
                        # tense memoir ideation. NEVER calls the LLM for
                        # response composition. Emits a deterministic
                        # acknowledgment, writes a segment_flag with the
                        # new past_tense_ideation_acknowledged category,
                        # writes softened state with N=2, persists the
                        # turn, and returns BEFORE the normal LLM
                        # composition path runs. The narrator's chapter
                        # continues at their pace; the operator gets a
                        # post-session flag for review (Bug Panel queue,
                        # rendered by ui/js/operator-review.js card).
                        logger.warning(
                            "[chat_ws][safety][llm_layer] "
                            "route=past_tense_acknowledge conv=%s "
                            "category=%s tense=%s subject=%s "
                            "confidence=%.2f",
                            conv_id, _llm_class.category,
                            _llm_class.tense, _llm_class.subject,
                            _llm_class.confidence,
                        )
                        try:
                            from ..safety_acknowledgments import (
                                select_past_tense_acknowledgment as _select_ack,
                            )
                            # Deterministic round-robin counter: number of
                            # past_tense flags already persisted for this
                            # session. Defaults to 0 on first occurrence.
                            _ack_idx = 0
                            try:
                                from ..db import get_segment_flags as _get_flags
                                _existing_flags = _get_flags(conv_id) or []
                                _ack_idx = sum(
                                    1 for f in _existing_flags
                                    if (f.get("sensitive_category") or "")
                                    == "past_tense_ideation_acknowledged"
                                )
                            except Exception:
                                _ack_idx = 0
                            _ack_text = _select_ack(_ack_idx)

                            # Persist segment_flag (sensitive=True,
                            # excluded_from_memoir=False — past-tense
                            # memoir content stays in the memoir; the
                            # flag exists for operator awareness, not
                            # memoir exclusion).
                            try:
                                ensure_interview_session(conv_id, person_id)
                                save_segment_flag(
                                    session_id=conv_id,
                                    question_id=None,
                                    section_id=None,
                                    sensitive=True,
                                    sensitive_category="past_tense_ideation_acknowledged",
                                    excluded_from_memoir=False,
                                    private=False,
                                )
                            except Exception as _pt_flag_exc:
                                logger.warning(
                                    "[chat_ws][safety][past-tense] flag "
                                    "persist failed conv=%s: %s",
                                    conv_id, _pt_flag_exc,
                                )

                            # Softened-mode write (N=2 per WO spec). The
                            # in-memory set_softened uses a hardcoded
                            # SOFTENED_TURNS=3 timer which is the wrong
                            # window for past-tense; WO-LORI-SOFTENED-
                            # MODE-PERSISTENCE-01 (Gate 6) is the read-
                            # side WO that will reconcile the N=5 acute
                            # vs N=2 past-tense windows from a single
                            # source of truth. Until then we write the
                            # correct N=2 to the DB and skip the
                            # legacy in-memory write — the in-memory
                            # cache is only consumed by the existing
                            # acute path.
                            # WO-LORI-SOFTENED-MODE-PERSISTENCE-01
                            # (2026-06-14) — past-tense uses N=2
                            # (env-tunable) + trigger tag, max-not-
                            # clobber if already softened.
                            try:
                                _softened_write(
                                    conv_id=conv_id,
                                    current_turn=_session_turn_count,
                                    n_turns=softened_n_past_tense(),
                                    trigger="past_tense_acknowledge",
                                    existing_state=_softened_state,
                                )
                            except Exception as _pt_soft_exc:
                                logger.warning(
                                    "[chat_ws][safety][past-tense] "
                                    "softened persist failed conv=%s: %s",
                                    conv_id, _pt_soft_exc,
                                )

                            # Persist the turn (user_text + ack response).
                            try:
                                persist_turn_transaction(
                                    conv_id=conv_id,
                                    user_message=user_text,
                                    assistant_message=_ack_text,
                                    model_name="past-tense-acknowledgment",
                                    # WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 R2.3.
                                    person_id=person_id,
                                    # WO-SYSTEM-DIRECTIVE-PERSISTENCE-01 Phase 1.
                                    is_system_directive=bool(params.get("_is_system_directive")),
                                    meta={
                                        "ws": True,
                                        "turn_mode": "past_tense_acknowledge",
                                        "ack_idx": _ack_idx,
                                    },
                                )
                            except Exception as _pt_persist_exc:
                                logger.warning(
                                    "[chat_ws][safety][past-tense] "
                                    "persist failed conv=%s: %s",
                                    conv_id, _pt_persist_exc,
                                )

                            # Emit ack as the assistant response and
                            # return — no LLM composition on this turn.
                            await _ws_send(ws, {
                                "type": "token", "delta": _ack_text,
                            })
                            await _ws_send(ws, {
                                "type": "done",
                                "final_text": _ack_text,
                                "turn_mode": "past_tense_acknowledge",
                            })
                            return
                        except Exception as _pt_path_exc:
                            # If the past-tense path itself raises, fall
                            # through to the normal LLM path rather than
                            # leaving the narrator hanging. The flag may
                            # not be written but the turn completes. The
                            # warning surfaces in api.log.
                            logger.warning(
                                "[chat_ws][safety][past-tense] path raised "
                                "conv=%s: %s — falling through to normal "
                                "composition",
                                conv_id, _pt_path_exc,
                            )

                    elif _route == _ROUTE_MR:
                        # WO-LORI-SAFETY-LLM-CLASSIFIER-01 §2 — mortality
                        # reflection. Ordinary older-adult mortality talk
                        # (outliving peers, end-of-life peace, legacy
                        # planning). NO routing, NO flag, NO softened
                        # write, NO acknowledgment. Just a log line for
                        # telemetry. The chapter continues with normal
                        # LLM composition because this WO's whole point
                        # is that mortality reflection is normal memoir
                        # content for older narrators.
                        logger.info(
                            "[chat_ws][safety][llm_layer] "
                            "route=mortality_reflection conv=%s "
                            "category=%s subject=%s confidence=%.2f "
                            "(suppressed escalation — normal turn proceeds)",
                            conv_id, _llm_class.category,
                            _llm_class.subject, _llm_class.confidence,
                        )

                    elif _llm_class.parse_ok and _llm_class.category in (
                        "ideation", "distressed"
                    ):
                        # ROUTE_NONE but classifier had a triggering category
                        # that was suppressed (below floor OR subject was
                        # third_party / external). Log for telemetry so the
                        # operator can tune the floor or audit the
                        # suppression posture.
                        logger.info(
                            "[chat_ws][safety][llm_layer] route=none "
                            "conv=%s category=%s tense=%s subject=%s "
                            "confidence=%.2f (suppressed: below floor "
                            "or non-self subject)",
                            conv_id, _llm_class.category,
                            _llm_class.tense, _llm_class.subject,
                            _llm_class.confidence,
                        )

                except Exception as _llm_layer_exc:
                    # Pure observability — LLM-layer failure must not
                    # break the turn. Pattern result (or None) stands.
                    logger.warning(
                        "[chat_ws][safety][llm_layer] failed (conv=%s): %s",
                        conv_id, _llm_layer_exc,
                    )

            if _safety_result and _safety_result.triggered:
                logger.warning(
                    "[chat_ws][safety] triggered conv=%s category=%s confidence=%.2f",
                    conv_id,
                    _safety_result.category,
                    _safety_result.confidence,
                )

                # Persist segment flag (chat path: question_id=None, section_id=None).
                # BUG-DBLOCK-01 PATCH 3 (2026-04-30): segment_flags FK's into
                # interview_sessions(id). chat_ws creates conv_ids that are never
                # registered there — only routers/interview.py:start_session
                # inserts. Pre-patch, every safety segment_flag insert on the chat
                # path failed with the segment_flags FK violation, leaking the
                # write lock and cascading into 5s/10s/15s busy_timeout failures
                # across set_session_softened, save_safety_event, and init_db.
                # ensure_interview_session is idempotent (INSERT OR IGNORE), safe
                # to call every safety-trigger turn.
                try:
                    ensure_interview_session(conv_id, person_id)
                except Exception as _ensure_exc:
                    logger.warning(
                        "[chat_ws][safety] ensure_interview_session failed conv=%s: %s",
                        conv_id, _ensure_exc,
                    )
                try:
                    _flags = build_segment_flags(_safety_result)
                    save_segment_flag(
                        session_id=conv_id,
                        question_id=None,
                        section_id=None,
                        sensitive=_flags.sensitive,
                        sensitive_category=_flags.sensitive_category or "",
                        excluded_from_memoir=_flags.excluded_from_memoir,
                        private=_flags.private,
                    )
                except Exception as _seg_exc:
                    logger.warning("[chat_ws][safety] segment_flag persist failed: %s", _seg_exc)

                # Set softened mode (in-memory + DB), mirroring interview.py.
                # WO-LORI-SOFTENED-RESPONSE-01 refactor: use the
                # _session_turn_count from the upstream per-turn
                # increment instead of incrementing again here.
                # Double-incrementing would shift the softened window
                # math by one — and the existing math is already
                # tested via interview.py.
                try:
                    # WO-LORI-SOFTENED-MODE-PERSISTENCE-01 (2026-06-14)
                    # — write softened with N=5 (env-tunable) + trigger
                    # tag, max-not-clobber if already softened.
                    set_softened(conv_id, _session_turn_count)  # legacy in-memory N=3 (unchanged for now)
                    _softened_write(
                        conv_id=conv_id,
                        current_turn=_session_turn_count,
                        n_turns=softened_n_acute(),
                        trigger="acute",
                        existing_state=_softened_state,
                    )
                    # Refresh the local softened state so the same turn's
                    # composer and wrapper see softened=True (without this
                    # the acute-trigger turn itself wouldn't see the new
                    # softened flag — only subsequent turns would).
                    try:
                        _softened_state = get_session_softened_state(conv_id)
                    except Exception:
                        pass
                except Exception as _soft_exc:
                    logger.warning("[chat_ws][safety] softened persist failed: %s", _soft_exc)

                # Emit safety event to UI for overlay rendering (existing
                # ui/js/safety-ui.js handler picks this up).
                #
                # 2026-04-29: removed `confidence` from the payload per
                # WO-LORI-SAFETY-INTEGRATION-01 Phase 3 "no scores / no
                # severity / no trends" posture. Confidence remains in
                # api.log [chat_ws][safety][notify] WARNING line for
                # operator/dev debugging only. Narrator-side UI never
                # sees a score-like value over the wire.
                try:
                    await _ws_send(ws, {
                        "type": "safety_triggered",
                        "category": _safety_result.category,
                        "resources": get_resources_for_category(_safety_result.category),
                    })
                except Exception:
                    pass

                # Phase 3 — persist to safety_events table + log. Operator
                # Bug Panel polls the digest endpoint and surfaces a banner.
                try:
                    await _safety_notify_operator(
                        conv_id=conv_id,
                        category=_safety_result.category,
                        confidence=_safety_result.confidence,
                        matched_phrase=_safety_result.matched_phrase,
                        turn_excerpt=user_text[:200],
                        person_id=person_id,
                    )
                except Exception as _notify_exc:
                    logger.warning("[chat_ws][safety] notify failed: %s", _notify_exc)

                # Force turn_mode → "interview" so the LLM path runs and the
                # ACUTE SAFETY RULE prompt fires. Without this override, a
                # safety-triggered turn that happened to be flagged as
                # memory_echo or correction by the UI would skip the LLM
                # entirely and just echo the distress content back.
                params["turn_mode"] = "interview"

        # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 §2.5 — refresh
        # the ONE authoritative route boolean now that the LLM second-
        # layer has had its chance to synthesize a triggered
        # _safety_result the deterministic preflight missed (indirect
        # ideation). Every downstream route decision (turn_mode
        # resolution, witness dispatch, bank flush) checks THIS name.
        _safety_forced_interview = bool(
            _safety_scan_failed
            or (_safety_result and _safety_result.triggered)
        )
        # ── End safety scan ──────────────────────────────────────────────────

        # WO-ARCH-07A — explicit mode routing BEFORE model load.
        #
        # 2026-04-29 ordering fix: deterministic turn modes (memory_echo /
        # correction) must NOT depend on _load_model() succeeding. Memory
        # echo is the trust-behavior fallback for "what do you know about
        # me?" — if the LLM is cold, slow, wedged, or under VRAM pressure,
        # this branch must still answer warmly and immediately. Same for
        # correction acknowledgments. Both compose deterministically with
        # no LLM call. Loading the model first defeats the whole purpose
        # of having a no-LLM fallback path.
        runtime71: Dict[str, Any] = params.get("runtime71") or {}
        turn_mode = (params.get("turn_mode") or "interview").strip() or "interview"

        # BUG-LORI-IDENTITY-META-QUESTION-DETERMINISTIC-ROUTE-01 — if the
        # upstream detector matched, override whatever the FE asked for.
        # The "meta_question" turn_mode is handled by a dedicated branch
        # below that emits the deterministic warm answer with no LLM
        # call, mirroring the memory_echo / age_recall / correction
        # composer pattern.
        # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 §2.5: the
        # safety-forced route is AUTHORITATIVE — it wins over floor hold,
        # meta question, and the server-side memory-echo trigger below.
        # (In practice _is_floor_hold only fires on [SYSTEM...] directives,
        # which are never safety-scanned, so the first two branches cannot
        # actually collide — the ordering makes the precedence structural
        # rather than incidental.)
        # Floor-hold short-circuit overrides everything else. The narrator
        # is still talking and Lori must hold silent space.
        if _safety_forced_interview:
            turn_mode = "interview"
            logger.info(
                "[chat_ws][safety][route-lock] conv=%s turn_mode pinned to "
                "interview (deterministic/LLM trigger or scan failure) — "
                "memory-echo/witness/bank overrides disabled this turn",
                conv_id,
            )
        elif _is_floor_hold:
            turn_mode = "floor_hold"
        elif _is_meta_question and _meta_question_answer is not None:
            turn_mode = "meta_question"
        else:
            # BANK_PRIORITY_REBUILD 2026-05-10 — server-side memory-
            # echo trigger detection. The FE sends turn_mode="interview"
            # for every chat turn (no inspection of user_text); when
            # the narrator asks "what did you learn about me", "what do
            # you know about me", "tell me what you remember about me",
            # etc., we MUST route to memory_echo regardless of FE's
            # turn_mode. Multi-turn Kent test 2026-05-10 caught this:
            # Turn 2 "What did you learn about me from that?" was
            # treated as a regular interview turn and Lori asked a
            # fresh era question instead of summarizing Turn 1.
            #
            # Detection is conservative: requires explicit "about me"
            # OR "about [my name]" anchor + a remember/know/learn verb.
            # Pure-stdlib regex; no LLM call.
            try:
                import re as _re_me
                _ut_low = (user_text or "").lower().strip()
                # Must be a question OR end with a question-word
                _is_question_form = (
                    "?" in _ut_low or _ut_low.endswith(("?",))
                    or _ut_low.startswith((
                        "what ", "tell me", "do you ",
                        "can you ", "could you ", "would you ",
                    ))
                )
                _memory_echo_anchors = (
                    r"\babout\s+me\b",
                    r"\babout\s+(?:my|our)\s+(?:life|story|past)\b",
                    r"\bwho\s+i\s+am\b",
                )
                _memory_echo_verbs = (
                    r"\b(?:know|knew|learn(?:ed|t)?|remember|recall|"
                    r"hear(?:d)?|gather(?:ed)?|pick(?:ed)?\s+up)\b"
                )
                _has_anchor = any(
                    _re_me.search(p, _ut_low) for p in _memory_echo_anchors
                )
                _has_verb = bool(_re_me.search(_memory_echo_verbs, _ut_low))
                # Short-form turns only (≤ 30 words). Long monologues
                # that happen to contain "what did you learn about me"
                # in the middle are NOT memory-echo queries.
                _is_short = len(_ut_low.split()) <= 30
                if (
                    _is_question_form and _has_anchor and _has_verb
                    and _is_short
                ):
                    turn_mode = "memory_echo"
                    logger.info(
                        "[chat_ws][memory-echo][server-trigger] conv=%s "
                        "user_text=%r — overriding turn_mode to "
                        "memory_echo",
                        conv_id, (user_text or "")[:120],
                    )
            except Exception as _me_exc:
                logger.warning(
                    "[chat_ws][memory-echo][server-trigger] detector "
                    "raised conv=%s: %s — leaving turn_mode unchanged",
                    conv_id, _me_exc,
                )

        # BUG-LORI-FACTUAL-OVER-SENSORY-PROBE-01 + BUG-LORI-WITNESS-LLM-
        # RECEIPT-01 — witness-mode dispatch. Mutually exclusive with
        # meta_question (the upstream detector already gated on
        # _is_meta_question).
        #
        # Routing rule (2026-05-10 evolution after Kent's deep replay
        # showed deterministic-only structured composition was too
        # thin):
        #   - META_FEEDBACK (incl. correction sub_types) → turn_mode
        #     stays "witness" → dispatcher branch below short-circuits
        #     with the deterministic ack. Behavior unchanged.
        #   - STRUCTURED_NARRATIVE → DO NOT short-circuit. Set
        #     runtime71["witness_receipt_mode"] = True so the system
        #     prompt picks up the WITNESS RECEIPT directive (defined
        #     in prompt_composer._WITNESS_RECEIPT_DIRECTIVE). Stash
        #     the underlying detection for the post-LLM validator-
        #     failure fallback so we can recompose deterministically
        #     if the LLM drifts under directive pressure.
        _witness_use_llm_receipt = False
        _witness_detection_for_fallback = None  # type: ignore[assignment]
        _witness_receipt_lang = "en"
        _immediate_door_question: Optional[str] = None
        _immediate_door_anchor: Optional[str] = None
        _immediate_door_story_weight: int = 0
        _doors_to_bank: List[Any] = []  # List[Door] from lori_followup_bank
        _current_turn_doors: List[Any] = []
        # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 §2.5: witness
        # META_FEEDBACK may not set turn_mode on a safety-forced turn.
        # Detection upstream is already gated on the same boolean; this
        # site re-checks it because the LLM second-layer can flip the
        # route AFTER detection ran.
        if (_is_witness_mode and _witness_answer is not None
                and not _safety_forced_interview):
            if _witness_answer.detection_type == "META_FEEDBACK":
                turn_mode = "witness"
            elif _witness_answer.detection_type == "STRUCTURED_NARRATIVE":
                _witness_use_llm_receipt = True
                # BUG-LORI-SESSION-LANGUAGE-CONTRACT-01: Pin the
                # validator-fallback language to the session contract
                # FIRST. Without this, the deterministic fallback
                # composes in whatever language the upstream witness-
                # detection picked — which was Spanish on Kent's
                # English narrator turns when looks_spanish() falsely
                # tripped on a single accent loanword. The contract
                # is the operator's declaration; per-turn detection
                # never overrides it.
                if _session_lang_mode == "english":
                    _witness_receipt_lang = "en"
                elif _session_lang_mode == "spanish":
                    _witness_receipt_lang = "es"
                else:
                    # Mixed mode OR unset — use the per-turn detection.
                    _witness_receipt_lang = (
                        "es" if _witness_answer.language == "es" else "en"
                    )
                try:
                    from ..services.lori_witness_mode import (
                        detect_witness_event as _detect_we,
                    )
                    _witness_detection_for_fallback = _detect_we(user_text)
                except Exception as _det_exc:
                    logger.warning(
                        "[chat_ws][witness][llm-receipt] detect rebuild "
                        "failed conv=%s: %s",
                        conv_id, _det_exc,
                    )
                    _witness_detection_for_fallback = None
                runtime71 = dict(runtime71) if isinstance(runtime71, dict) else {}
                runtime71["witness_receipt_mode"] = True
                logger.info(
                    "[chat_ws][witness][llm-receipt] conv=%s lang=%s "
                    "anchor=%r events=%d",
                    conv_id,
                    _witness_receipt_lang,
                    (
                        _witness_detection_for_fallback.factual_anchor
                        if _witness_detection_for_fallback else ""
                    ),
                    (
                        len(_witness_detection_for_fallback.event_phrases)
                        if _witness_detection_for_fallback else 0
                    ),
                )

                # ── WO-LORI-WITNESS-FOLLOWUP-BANK-01 (2026-05-10) ─────
                # Run door detection on the narrator turn, pick the
                # immediate door (priority 1-3), bank the rest. The
                # immediate door's question_en flows into the
                # validator-fallback composer below; the banked
                # doors get persisted AFTER the response is sent
                # (post-persist, pre-WS-done).
                #
                # Per Chris's locked principle: "Each turn opens a new
                # door. Lori can bank follow-up questions. After a
                # chapter is told, Lori goes to the bank for
                # unanswered followups." Priority 4-6 doors NEVER
                # ask immediately.
                try:
                    from ..services.lori_followup_bank import (
                        detect_doors as _bank_detect_doors,
                        select_immediate_and_bank as _bank_select,
                    )
                    _current_turn_doors = _bank_detect_doors(user_text)
                    # BANK_PRIORITY_REBUILD 2026-05-10: thread the
                    # narrator_voice_overlay from profile_seed into
                    # the selector. For Kent (adult_competence),
                    # sensory doors get demoted; Tier-N institutional
                    # spelling-confirms never auto-immediate.
                    _overlay = "default"
                    try:
                        if isinstance(runtime71, dict):
                            _ps = runtime71.get("profile_seed") or {}
                            _ovl_raw = _ps.get("narrator_voice_overlay")
                            if _ovl_raw in (
                                "adult_competence",
                                "hearth_sensory",
                                "shield_protected",
                                "default",
                            ):
                                _overlay = _ovl_raw
                    except Exception:
                        _overlay = "default"
                    _imm_door, _doors_to_bank = _bank_select(
                        _current_turn_doors,
                        narrator_voice_overlay=_overlay,
                    )
                    if _imm_door is not None:
                        _immediate_door_question = _imm_door.question_en
                        _immediate_door_anchor = _imm_door.triggering_anchor
                        _immediate_door_story_weight = int(
                            getattr(_imm_door, "story_weight", 0) or 0
                        )
                        logger.info(
                            "[chat_ws][followup-bank][immediate] conv=%s "
                            "intent=%s priority=%d tier=%s sw=%d "
                            "overlay=%s anchor=%r",
                            conv_id, _imm_door.intent, _imm_door.priority,
                            _imm_door.tier or "(legacy)",
                            _imm_door.story_weight,
                            _overlay,
                            _imm_door.triggering_anchor[:60],
                        )
                    if _doors_to_bank:
                        logger.info(
                            "[chat_ws][followup-bank][to-bank] conv=%s "
                            "overlay=%s n=%d intents=%s",
                            conv_id, _overlay, len(_doors_to_bank),
                            ",".join(d.intent for d in _doors_to_bank[:5]),
                        )
                except Exception as _bank_exc:
                    logger.warning(
                        "[chat_ws][followup-bank] door detect failed "
                        "conv=%s: %s — falling back to legacy intent",
                        conv_id, _bank_exc,
                    )
                    _current_turn_doors = []
                    _doors_to_bank = []
                    _immediate_door_question = None

        # ── WO-LORI-WITNESS-FOLLOWUP-BANK-01 — bank-flush short-circuit ──
        # If the narrator's turn is a flush trigger AND there's an
        # unanswered banked question, emit "I want to come back to one
        # detail you mentioned earlier. {Q}" deterministically — no LLM
        # call. Fires BEFORE the witness/meta-question dispatchers so
        # this branch wins on flush turns.
        #
        # Conservative triggers per Chris's locked rule:
        #   - short narrator answer + no new door opened this turn
        #   - narrator says "what else / where were we / what next"
        #   - operator-click SYSTEM directive
        #   - floor-released SYSTEM directive
        #   - chapter-summary mode
        #
        # Skips entirely when:
        #   - This turn opened a sharp door (priority 1-3) — follow it
        #   - Bank is empty for this session
        #   - Floor-hold turn (already handled above)
        #   - Meta-question / witness short-circuit will fire downstream
        _bank_flush_used = False
        _bank_flushed_id: Optional[str] = None
        # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 §2.5: bank-flush
        # may not execute on a safety-forced turn — "What else? I want to
        # kill myself." must never be answered with a banked question, and
        # the banked row must not be burned (marked asked) on that turn.
        if (
            conv_id and user_text and user_text.strip()
            and not _is_floor_hold
            and not (_is_meta_question and _meta_question_answer is not None)
            and not _safety_forced_interview
        ):
            try:
                from ..services.lori_followup_bank import (
                    should_flush_bank as _bank_should_flush,
                    compose_bank_flush_response as _bank_compose_flush,
                )
                from ..db import (
                    followup_bank_get_unanswered as _bank_get_unanswered,
                    followup_bank_mark_asked as _bank_mark_asked,
                )
                _flush_ok, _flush_reason = _bank_should_flush(
                    narrator_text=user_text,
                    current_turn_doors=_current_turn_doors,
                    is_system_directive=_is_system_directive,
                    runtime71=runtime71 if isinstance(runtime71, dict) else None,
                )
                if _flush_ok:
                    _open_bank = _bank_get_unanswered(conv_id)
                    # Walk past malformed entries (false-positive
                    # corrections captured by an old detector run).
                    # Defense in depth — even if a junk door is in
                    # the bank, it never reaches the narrator.
                    from ..services.lori_followup_bank import (
                        is_bank_question_malformed as _is_malformed,
                    )
                    _to_flush = None
                    for _candidate in _open_bank:
                        if not _is_malformed(_candidate.get("question_en", "")):
                            _to_flush = _candidate
                            break
                        else:
                            logger.warning(
                                "[chat_ws][bank-flush] skipping malformed "
                                "entry id=%s intent=%s anchor=%r",
                                _candidate.get("id"),
                                _candidate.get("intent"),
                                _candidate.get("triggering_anchor"),
                            )
                    if _to_flush is not None:
                        _flush_text = _bank_compose_flush(
                            _to_flush["question_en"],
                        )
                        if _flush_text:
                            _turn_idx = _session_turn_count or 0
                            _bank_mark_asked(_to_flush["id"], _turn_idx)
                            persist_turn_transaction(
                                conv_id=conv_id,
                                user_message=user_text,
                                assistant_message=_flush_text,
                                model_name="bank-flush-deterministic",
                                # WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 R2.3.
                                person_id=person_id,
                                # WO-SYSTEM-DIRECTIVE-PERSISTENCE-01 Phase 1.
                                is_system_directive=bool(params.get("_is_system_directive")),
                                meta={
                                    "ws": True,
                                    "turn_mode": "bank_flush",
                                    "bank_flush_reason": _flush_reason,
                                    "banked_question_id": _to_flush["id"],
                                    "banked_intent": _to_flush["intent"],
                                    "banked_priority": _to_flush["priority"],
                                },
                            )
                            logger.info(
                                "[chat_ws][bank-flush] conv=%s reason=%s "
                                "intent=%s priority=%d question=%r",
                                conv_id, _flush_reason,
                                _to_flush["intent"],
                                _to_flush["priority"],
                                _to_flush["question_en"][:80],
                            )
                            await _ws_send(ws, {
                                "type": "token", "delta": _flush_text,
                            })
                            await _ws_send(ws, {
                                "type": "done",
                                "final_text": _flush_text,
                                "turn_mode": "bank_flush",
                                "banked_intent": _to_flush["intent"],
                            })
                            _bank_flush_used = True
                            _bank_flushed_id = _to_flush["id"]
                            return
            except Exception as _flush_exc:
                # Defense-in-depth: a bank-flush failure must not break
                # the turn. Fall through to normal LLM/dispatch.
                logger.warning(
                    "[chat_ws][bank-flush] wrapper raised conv=%s: %s",
                    conv_id, _flush_exc,
                )

        # WO-PROVISIONAL-TRUTH-01 Phase A polish (2026-05-04):
        # profile_seed bridge runs for ALL turn modes, not just memory_echo.
        # Phase A originally added the bridge inside the memory_echo branch
        # only — that was sufficient to fix Mary's "what do you know about
        # me?" readback, but the same provisional values (childhood_home,
        # heritage, etc. from interview_projections.projection_json) need
        # to reach compose_system_prompt for interview turns too, so that
        # the era-walk and identity-collection directives can REFRAME
        # known values as confirmation ("I have Minot, ND on record —
        # does that still feel right?") rather than asking from scratch.
        # Without this lift, Lori greets Mary by name correctly (memory_echo
        # path) but then asks "where were you born?" on the next interview
        # turn (interview path can't see the seed).
        #
        # Risk: pure expansion of an already-tested read. _build_profile_seed
        # is byte-stable when both profile_json and projection_json are
        # absent. UI seed still takes precedence per-bucket.
        try:
            from ..prompt_composer import _build_profile_seed
            ui_seed = runtime71.get("profile_seed") if isinstance(runtime71.get("profile_seed"), dict) else {}
            server_seed = _build_profile_seed(person_id) if person_id else {}
            # UI takes precedence per-bucket (real-time signal), server
            # fills only the buckets UI didn't populate.
            merged_seed = dict(server_seed)
            merged_seed.update({k: v for k, v in (ui_seed or {}).items() if v})
            if merged_seed:
                runtime71 = dict(runtime71)
                runtime71["profile_seed"] = merged_seed
                logger.info(
                    "[chat_ws][profile-seed] sources: ui=%d server=%d merged=%d turn_mode=%s conv=%s person=%s",
                    len([k for k, v in (ui_seed or {}).items() if v]),
                    len(server_seed),
                    len(merged_seed),
                    turn_mode,
                    conv_id,
                    person_id or "(none)",
                )
        except Exception as _seed_exc:
            # Never let the seed bridge fail the turn — fall through to
            # behavior identical to pre-Phase-A (UI seed only, if any).
            logger.warning(
                "[chat_ws][profile-seed] bridge failed conv=%s person=%s: %s",
                conv_id, person_id, _seed_exc,
            )

        # ── BUG-LORI-FLOOR-HOLD-DETERMINISTIC-01 ──────────────────────
        # When the narrator has pressed and held the floor, Lori must
        # emit a small deterministic ack — no LLM, no question, no
        # summary, ≤7 words. Three rotating acks based on conv_id hash
        # so the same session sees variety on repeated holds.
        if turn_mode == "floor_hold":
            _floor_acks = ("Take your time.", "I'm listening.", "Keep going.")
            try:
                _floor_idx = abs(hash(conv_id or "")) % len(_floor_acks)
            except Exception:
                _floor_idx = 0
            assistant_text = _floor_acks[_floor_idx]
            logger.info(
                "[chat_ws][floor-hold] deterministic conv=%s ack=%r",
                conv_id, assistant_text,
            )
            # Archived like any other delivered reply. It is three words,
            # but the narrator heard it, and a transcript that shows them
            # speaking into silence misrepresents the conversation. Memoir
            # surfaces can filter on meta.turn_mode; they cannot recover a
            # line that was never written.
            await _finalize_deterministic_turn(
                ws,
                params=params,
                conv_id=conv_id,
                person_id=person_id,
                user_text=user_text,
                assistant_text=assistant_text,
                turn_mode="floor_hold",
                model_name="floor-hold-deterministic",
                meta={"floor_ack_idx": _floor_idx},
                current_era=_current_era_for_archive,
            )
            return

        # ── BUG-LORI-IDENTITY-META-QUESTION-DETERMINISTIC-ROUTE-01 ──────
        # 2026-05-09 (Mary's session) — narrator meta-questions get a
        # deterministic warm answer composed above by lori_meta_question
        # .detect_and_compose. Bypasses the LLM, the safety classifier,
        # and all the directive layers that produced "I don't have a
        # name" / "AI." stub / 988-on-"are-you-safe" failures. Persisted
        # via the same persist_turn_transaction path so memory_echo,
        # archive, transcript, and operator visibility all see the turn
        # cleanly.
        if turn_mode == "meta_question" and _meta_question_answer is not None:
            # ── BUG-DETERMINISTIC-TURN-ARCHIVE-MISSING-01 (2026-08-01) ────
            # LIVE EVIDENCE. Chris asked "how many pictures can you see
            # from this trip" at 15:22:42. Lori answered correctly in the
            # browser -- "There are three photos attached to Bismarck
            # Trip, two of them placed on a day" -- and the exported
            # transcript jumps straight from his question to his NEXT
            # message at 15:24:25. The answer is missing.
            #
            # This branch persisted the turn and returned. The USER
            # archive event is written unconditionally ~1,500 lines above
            # (chat_ws.py:1888), so the transcript got the question and
            # never the answer. That asymmetry is what made it invisible
            # for so long: the export looks like an unanswered turn
            # rather than a missing write.
            #
            # THE REPAIR IS NARROW BY INSTRUCTION. The same gap exists in
            # floor_hold, witness, memory_echo, age_recall and correction,
            # measured from the AST, and a shared finaliser is the right
            # architecture -- but that is five unrelated Lori behaviours
            # and belongs to WO-DETERMINISTIC-TURN-FINALIZATION-01. Only
            # meta_question is repaired here, which is the path the trip
            # photo-capability answer and the trip-direct answer both
            # take.
            #
            # ── CORRECTED 2026-08-03. THE FIRST CUT OF THIS REPAIR ALSO
            # OPENED THE TWO COMPLETED-TURN HOOKS, AND THAT WAS A BUG. ───
            # It captured row_ids_out, set params["_persisted_turn_row_id"]
            # and params["_persisted_user_turn_row_id"], and set
            # params["_archive_event_persisted"]. The retired comment here
            # claimed:
            #
            #     "NO trip conversation link is created -- the placement
            #      hook is gated on params['_persisted_turn_row_id']"
            #     "completed-turn extraction never sees the turn -- same
            #      gate plus params['_archive_event_persisted']"
            #     "Setting the flags is the whole wiring."
            #
            # Each sentence described a gate correctly and stopped one
            # level too early. BOTH hooks ALSO gate on turn mode --
            # PLACEMENT_ELIGIBLE_TURN_MODES and
            # EXTRACTION_ELIGIBLE_TURN_MODES are each frozenset({"interview"})
            # -- and both read it from **params**, at :836 and :648. But the
            # dispatcher resolves the deterministic mode into a LOCAL
            # `turn_mode` and never writes it back: the only three writes to
            # params["turn_mode"] in this file are :5480 (whatever the
            # browser sent, "interview" for an ordinary turn) and :1247 and
            # :2909, which both force "interview". So on a turn the server
            # resolved to meta_question, params["turn_mode"] is still
            # "interview" and BOTH mode gates pass.
            #
            # A deterministic branch's `return` does not skip the hooks
            # either. `_generate_and_stream_body` is awaited at :481; an
            # early return from it is a normal return, and :490 and :502
            # run next. What was actually holding the hooks out was the
            # ABSENCE of these two flags -- so setting them fired an
            # extraction generation and a trip conversation link against
            # Lori's own deterministic capability answer.
            #
            # The flags are therefore NOT set here. This branch writes the
            # turn, the assistant archive event and the transcript rebuild,
            # and exposes nothing to the completed-turn hooks. That is the
            # whole of the transcript repair; the hooks were never part of
            # it. Repairing the effective-mode handoff itself is a separate
            # concern for WO-LEAN-LORI-RUNTIME-01 Phase 0/1A and must not
            # be attempted from inside one branch -- five other branches
            # reach the same seam.
            #
            # NOTHING IS DUPLICATED. The user archive event is NOT written
            # here -- 1888 already did it. persist_turn_transaction is
            # called ONCE, exactly as it was before any of this.
            #
            # ── MOVED INTO `_finalize_deterministic_turn` 2026-08-04, R3
            # Phase 1A. ────────────────────────────────────────────────
            # The persist + surface-gated archive + rebuild + frames that
            # used to be written out here inline are now the shared
            # finaliser, because the other five branches needed exactly
            # the same thing and the flag-absence contract described above
            # is far safer held in ONE place than remembered in six. The
            # behaviour is unchanged: same single persist, same
            # recomputed modal gate, same try-wrapped archive, same
            # rebuild-after-append, same two browser frames, and still
            # NO `_persisted_turn_row_id`, `_persisted_user_turn_row_id`
            # or `_archive_event_persisted`.
            assistant_text = _meta_question_answer.text
            await _finalize_deterministic_turn(
                ws,
                params=params,
                conv_id=conv_id,
                person_id=person_id,
                user_text=user_text,
                assistant_text=assistant_text,
                turn_mode="meta_question",
                model_name="meta-question-deterministic",
                meta={
                    "meta_question_category": _meta_question_answer.primary_category,
                    "meta_question_lang": _meta_question_answer.language,
                },
                current_era=_current_era_for_archive,
                done_extra={
                    "meta_question_category": _meta_question_answer.primary_category,
                },
            )
            return

        # ── BUG-LORI-FACTUAL-OVER-SENSORY-PROBE-01 ──────────────────────
        # Witness mode dispatcher branch. Sibling to meta_question.
        # Detection upstream populated _witness_answer when the narrator
        # turn matched META_FEEDBACK ("you are being vague", "stop
        # sensory") OR STRUCTURED_NARRATIVE (multi-event chronological
        # factual recounting like Kent's basic-training answer). The
        # composed deterministic text NEVER includes sensory probes,
        # feeling probes, scenery questions, or topic shifts.
        if turn_mode == "witness" and _witness_answer is not None:
            assistant_text = _witness_answer.text
            await _finalize_deterministic_turn(
                ws,
                params=params,
                conv_id=conv_id,
                person_id=person_id,
                user_text=user_text,
                assistant_text=assistant_text,
                turn_mode="witness",
                model_name="witness-deterministic",
                meta={
                    "witness_detection_type": _witness_answer.detection_type,
                    "witness_sub_type": _witness_answer.sub_type,
                    "witness_anchor": _witness_answer.factual_anchor,
                    "witness_lang": _witness_answer.language,
                },
                current_era=_current_era_for_archive,
                done_extra={
                    "witness_detection_type": _witness_answer.detection_type,
                    "witness_sub_type": _witness_answer.sub_type,
                },
            )
            return

        if turn_mode == "memory_echo":
            from ..prompt_composer import compose_memory_echo

            # ── WO-LORI-SESSION-AWARENESS-01 Phase 1c-wire (2026-05-03) ──
            # Pull promoted_truth + recent_turns via the peek_at_memoir
            # read accessor. Phase 5c safety filter is applied INSIDE
            # build_peek_at_memoir so any sensitive turn is dropped
            # automatically — no chance of distress content surfacing
            # in "what I know about you" memory_echo summaries.
            #
            # Default-OFF behind HORNELORE_PEEK_AT_MEMOIR_LIVE=0 because
            # the surface text rendering (compose_memory_echo's new
            # "From our records" section) is a real narrator-facing
            # behavior change that should be Chris-validated on the
            # parent-session readiness harness before flipping live.
            #
            # When the flag is off: runtime71["peek_data"] stays
            # absent, compose_memory_echo's new rendering branch is
            # skipped, and behavior is byte-identical to pre-Phase 1c.
            if (
                person_id
                and os.getenv("HORNELORE_PEEK_AT_MEMOIR_LIVE", "0") in ("1", "true", "True")
            ):
                try:
                    from ..services.peek_at_memoir import (
                        build_peek_at_memoir as _build_peek,
                        summarize_for_runtime as _summarize_peek,
                    )
                    _peek = _build_peek(person_id, session_id=conv_id)
                    _peek_summary = _summarize_peek(_peek)
                    runtime71 = dict(runtime71)
                    runtime71["peek_data"] = _peek_summary
                    logger.info(
                        "[chat_ws][memory-echo][peek] conv=%s person=%s "
                        "promoted_facts=%d recent_turns=%d sources=%s "
                        "errors=%d",
                        conv_id, person_id,
                        len(_peek_summary.get("promoted_facts") or []),
                        len(_peek_summary.get("recent_user_turns") or []),
                        ",".join(_peek_summary.get("sources_used") or []) or "none",
                        len(_peek.get("errors") or []),
                    )
                except Exception as _peek_exc:
                    logger.warning(
                        "[chat_ws][memory-echo][peek] build failed conv=%s person=%s: %s",
                        conv_id, person_id, _peek_exc,
                    )

            # BUG-ML-LORI-DETERMINISTIC-COMPOSERS-ENGLISH-ONLY-01 Phase 1
            # (2026-05-07): detect Spanish narrator via looks_spanish on the
            # incoming user_text and route memory_echo composer to the
            # Spanish locale pack. Failure is non-fatal — defaults to "en"
            # which preserves byte-stable behavior on any error.
            _memory_echo_lang = "en"
            try:
                from ..services.lori_spanish_guard import looks_spanish as _looks_es
                if _looks_es(user_text or ""):
                    _memory_echo_lang = "es"
            except Exception:
                _memory_echo_lang = "en"
            assistant_text = compose_memory_echo(
                text=user_text,
                runtime=runtime71,
                target_language=_memory_echo_lang,
            )

            # BANK_PRIORITY_REBUILD 2026-05-10 — recent-chapter summary
            # prefix. When the narrator's question is "what did you
            # learn about me from that?" / "from this chapter" / "from
            # what I just said", canonical memory_echo (profile +
            # promoted_facts) is the wrong shape — Kent wants to hear
            # what Lori HEARD from the immediately-preceding narrator
            # turn, not a profile recitation.
            #
            # Build a short deterministic summary from:
            #   1. anchors detected in the previous narrator turn
            #   2. banked doors persisted for this session
            # and prepend to assistant_text.
            #
            # English only (Spanish path uses canonical compose_memory_
            # echo which already supports both locales).
            try:
                _prev_user_text = ""
                _bank_doors_for_summary: List[Any] = []
                from ..db import (
                    export_turns as _export_turns_me,
                    followup_bank_get_unanswered as _bank_get_unanswered,
                )
                _hist_me = _export_turns_me(conv_id) or []
                # Walk backwards for last user turn that's NOT the
                # current memory-echo question.
                # WO-SYSTEM-DIRECTIVE-PERSISTENCE-01 Phase 2 pilot
                # (2026-08-09). Was `.startswith("[SYSTEM")`. These are
                # real `turns` rows via `export_turns()`, so the recorded
                # flag is available; the helper prefers it and falls back
                # to the prefix for pre-Phase-1 rows, of which 120 exist
                # and which this work order does not rewrite.
                for _t in reversed(_hist_me):
                    if (
                        isinstance(_t, dict)
                        and _t.get("role") == "user"
                        and not _turn_is_system_directive(_t)
                    ):
                        _candidate = (_t.get("content") or "").strip()
                        if _candidate and _candidate != (user_text or "").strip():
                            _prev_user_text = _candidate
                            break
                try:
                    _bank_rows = _bank_get_unanswered(conv_id) or []
                    _bank_doors_for_summary = [
                        r for r in _bank_rows if isinstance(r, dict)
                    ]
                except Exception:
                    _bank_doors_for_summary = []

                # Need previous turn AND English locale to compose.
                if (
                    _prev_user_text
                    and _memory_echo_lang == "en"
                    and len(_prev_user_text.split()) >= 60
                ):
                    from ..services.lori_followup_bank import (
                        detect_doors as _detect_doors_me,
                    )
                    _prev_doors = _detect_doors_me(_prev_user_text)
                    # Pull the Tier 1A anchor (highest story-weight).
                    _tier_1a = next(
                        (
                            d for d in _prev_doors
                            if (d.tier or "") == "1A"
                            and (d.story_weight or 0) >= 1
                        ),
                        None,
                    )
                    # Up to 3 narrator-named anchors from the previous
                    # turn to mention. Skip duplicates.
                    _anchors_seen: List[str] = []
                    if _tier_1a is not None and _tier_1a.triggering_anchor:
                        _anchors_seen.append(_tier_1a.triggering_anchor)
                    for _d in _prev_doors:
                        _a = _d.triggering_anchor or ""
                        if not _a or _a in _anchors_seen:
                            continue
                        if _a.lower() in (s.lower() for s in _anchors_seen):
                            continue
                        _anchors_seen.append(_a)
                        if len(_anchors_seen) >= 4:
                            break
                    # Up to 2 bank doors to mention (anchors only —
                    # don't read their full questions, just signal the
                    # operator/Lori is holding them).
                    _bank_anchors: List[str] = []
                    for _row in _bank_doors_for_summary:
                        _a = (_row.get("triggering_anchor") or "").strip()
                        if not _a:
                            continue
                        if _a in _anchors_seen or _a in _bank_anchors:
                            continue
                        _bank_anchors.append(_a)
                        if len(_bank_anchors) >= 2:
                            break

                    if _anchors_seen:
                        _summary_parts: List[str] = []
                        if len(_anchors_seen) == 1:
                            _summary_parts.append(
                                f"From what you just shared, I heard "
                                f"about {_anchors_seen[0]}."
                            )
                        elif len(_anchors_seen) == 2:
                            _summary_parts.append(
                                f"From what you just shared, I heard "
                                f"about {_anchors_seen[0]} and "
                                f"{_anchors_seen[1]}."
                            )
                        else:
                            _head = ", ".join(_anchors_seen[:-1])
                            _summary_parts.append(
                                f"From what you just shared, I heard "
                                f"about {_head}, and {_anchors_seen[-1]}."
                            )
                        if _bank_anchors:
                            if len(_bank_anchors) == 1:
                                _summary_parts.append(
                                    f"I'm holding a follow-up about "
                                    f"{_bank_anchors[0]} for when you "
                                    f"want to come back to it."
                                )
                            else:
                                _summary_parts.append(
                                    f"I'm holding follow-ups about "
                                    f"{_bank_anchors[0]} and "
                                    f"{_bank_anchors[1]} for when you "
                                    f"want to come back to them."
                                )
                        _recent_summary = " ".join(_summary_parts)
                        # Prepend with a blank line separator so the
                        # canonical "What I know about Kent so far:"
                        # block stays visually distinct.
                        assistant_text = (
                            f"{_recent_summary}\n\n{assistant_text}"
                        )
                        logger.info(
                            "[chat_ws][memory-echo][recent-chapter] "
                            "conv=%s anchors=%d bank=%d prev_words=%d",
                            conv_id, len(_anchors_seen),
                            len(_bank_anchors),
                            len(_prev_user_text.split()),
                        )
            except Exception as _rec_exc:
                logger.warning(
                    "[chat_ws][memory-echo][recent-chapter] failed "
                    "conv=%s: %s — falling back to canonical memory_echo",
                    conv_id, _rec_exc,
                )

            logger.info(
                "[chat_ws][WO-ARCH-07A] memory_echo turn conv=%s lang=%s",
                conv_id, _memory_echo_lang,
            )
            await _finalize_deterministic_turn(
                ws,
                params=params,
                conv_id=conv_id,
                person_id=person_id,
                user_text=user_text,
                assistant_text=assistant_text,
                turn_mode="memory_echo",
                model_name="memory-echo",
                current_era=_current_era_for_archive,
            )
            return
        # BUG-LORI-LATE-AGE-RECALL-01 (2026-05-06): deterministic age-recall
        # branch. Mirrors memory_echo: bypasses LLM, reads age_years +
        # DOB from profile_seed via compose_age_recall, persists the
        # turn, returns. v8 evidence showed both narrators dodged late-
        # age questions because the LLM had to infer age from DOB +
        # today across a long context window. The deterministic branch
        # can never deflect.
        if turn_mode == "age_recall":
            from ..prompt_composer import compose_age_recall
            # WO-SPANISH-LIVE-READINESS-01 Patch 7 (2026-06-17, ChatGPT
            # review follow-up): detect narrator language so Spanish
            # narrators asking "¿qué edad tengo?" get the Spanish
            # response shape. compose_age_recall's target_language
            # branch was added in Patch 3 but the caller was still
            # using the default "en". Same looks_spanish() probe as the
            # other deterministic-composer call sites in this file.
            _age_lang = "en"
            try:
                from ..services.lori_spanish_guard import looks_spanish as _ar_looks_es
                if user_text and _ar_looks_es(user_text):
                    _age_lang = "es"
            except Exception:
                _age_lang = "en"
            assistant_text = compose_age_recall(
                person_id=person_id,
                runtime=runtime71,
                target_language=_age_lang,
            )
            logger.info(
                "[chat_ws][age-recall] turn for conv=%s lang=%s",
                conv_id, _age_lang,
            )
            await _finalize_deterministic_turn(
                ws,
                params=params,
                conv_id=conv_id,
                person_id=person_id,
                user_text=user_text,
                assistant_text=assistant_text,
                turn_mode="age_recall",
                model_name="age-recall",
                meta={"age_recall_lang": _age_lang},
                current_era=_current_era_for_archive,
            )
            return
        if turn_mode == "correction":
            from ..prompt_composer import compose_correction_ack
            from ..memory_echo import parse_correction_rule_based
            parsed = parse_correction_rule_based(user_text)
            logger.info("[chat_ws][WO-ARCH-07A] correction turn for conv=%s parsed=%s", conv_id, parsed)

            # BUG-LORI-CORRECTION-ABSORBED-NOT-APPLIED-01 Phase 3 (2026-05-07):
            # Apply parsed corrections to projection_json BEFORE sending
            # the ack response. Without this, corrections were detected
            # and acknowledged in prose but never mutated the canonical
            # provisional-truth surface — Lori's "noted, let's continue"
            # without an actual data update was the failure mode Melanie
            # Zollner hit (her "we only had two children, not three"
            # never propagated to family.children.count). Best-effort:
            # apply_correction logs warnings but never raises into the
            # chat path. Summary goes into the persisted turn meta for
            # operator-side observability.
            apply_summary: Optional[Dict[str, Any]] = None
            if parsed and person_id:
                try:
                    from ..services import projection_writer as _projection_writer
                    apply_summary = _projection_writer.apply_correction(
                        person_id=person_id,
                        parsed=parsed,
                        source_turn_id=(params.get("turn_id") or None),
                    )
                    logger.info(
                        "[chat_ws][correction-apply] applied=%d retracted=%d skipped=%d errors=%d",
                        len(apply_summary.get("applied") or []),
                        len(apply_summary.get("retracted") or []),
                        len(apply_summary.get("skipped") or []),
                        len(apply_summary.get("errors") or []),
                    )
                except Exception as _apply_exc:
                    logger.warning(
                        "[chat_ws][correction-apply] apply_correction threw "
                        "(chat continues): %s", _apply_exc,
                    )
                    apply_summary = {"errors": [str(_apply_exc)]}

            # WO-ARCH-07A PS2 — emit structured correction payload for client write-back
            await _ws_send(ws, {
                "type": "correction_payload",
                "parsed": parsed,
                "source_text": user_text,
                "turn_mode": "correction",
                "apply_summary": apply_summary,
            })

            assistant_text = compose_correction_ack(
                text=user_text,
                runtime=runtime71,
            )
            # The `correction_payload` frame above is sent BEFORE this on
            # purpose and stays where it is: it carries the structured
            # parse for client write-back, and the browser applies it
            # while the ack is still being delivered. The finaliser owns
            # only the turn, the archive event and the two closing frames.
            # The projection write already happened above via
            # `apply_correction`; nothing here repeats it.
            await _finalize_deterministic_turn(
                ws,
                params=params,
                conv_id=conv_id,
                person_id=person_id,
                user_text=user_text,
                assistant_text=assistant_text,
                turn_mode="correction",
                model_name="correction-ack",
                meta={
                    "parsed_corrections": parsed,
                    "apply_summary": apply_summary,
                },
                current_era=_current_era_for_archive,
            )
            return

        # ── LLM-path setup — only reached for turn_mode='interview' ─────────
        # Deterministic turn modes (memory_echo, correction) returned above
        # without touching the model, so a cold/slow/wedged LLM never blocks
        # the trust-behavior fallback path.
        model, tok = _load_model()
        history = export_turns(conv_id)

        # WO-LORI-SOFTENED-RESPONSE-01 — thread softened state into
        # runtime71 BEFORE compose_system_prompt is called. The
        # composer reads runtime71["softened_state"] and injects the
        # SOFTENED MODE directive when interview_softened=True.
        # The env-flag gate already happened upstream when we decided
        # whether to read the DB state at all. _softened_state here is
        # either the freshly-read DB row (flag ON) or the safe default
        # zero-state (flag OFF). So the if-check below is just "did
        # we actually find a softened session?" — not a flag check.
        #
        # Phase 3B: and never while parked. `_softened_state` is already
        # zero-defaulted upstream when parked, so this is redundant --
        # deliberately. This is the handoff itself, the one line that
        # puts a safety state into Lori's prompt, and it should be
        # readable as refusing on its own terms rather than relying on a
        # value set 1,600 lines earlier.
        try:
            if (not _safety_parked
                    and _softened_state
                    and _softened_state.get("interview_softened")):
                runtime71 = dict(runtime71) if isinstance(runtime71, dict) else {}
                runtime71["softened_state"] = dict(_softened_state)
        except Exception as _rt_exc:
            logger.warning(
                "[chat_ws][softened] runtime71 thread failed conv=%s: %s",
                conv_id, _rt_exc,
            )

        # ── WO-LORI-STORY-FIRST-PHASE-1-01 — runtime71 keys for prompt composer.
        # When the Phase 1 flag is on, surface the momentum_mode and the
        # selected thread (if any) so the prompt composer can inject
        # the corresponding directive blocks. Default-off: when the flag
        # is off, _phase_1_momentum_mode stays "normal" and
        # _phase_1_thread_surface_text stays "" — composer sees no keys
        # set and emits no Phase 1 directives, preserving byte-stability.
        if _phase_1_enabled_now:
            try:
                runtime71 = dict(runtime71) if isinstance(runtime71, dict) else {}
                runtime71["story_first_momentum_mode"] = _phase_1_momentum_mode
                if _phase_1_thread_surface_text:
                    runtime71["story_first_thread_surface_text"] = _phase_1_thread_surface_text
            except Exception as _sf_rt_exc:
                logger.warning(
                    "[chat_ws][story_first] runtime71 thread failed conv=%s: %s",
                    conv_id, _sf_rt_exc,
                )

        # WO-LORI-BIO-BUILDER-UNIVERSAL-01 — Phase D Tier 3 runtime71 key.
        # When the bio anchored asker selected a gap this turn, surface
        # the composer-instruction text so prompt_composer can inject
        # the LORI_ANCHORED_ASK_DIRECTIVE block. Default OFF: when
        # _bio_anchored_surface_text is empty (flag off or not
        # eligible), no key is set and the composer sees no directive
        # — byte-stable.
        if _bio_anchored_surface_text:
            try:
                runtime71 = dict(runtime71) if isinstance(runtime71, dict) else {}
                runtime71["bio_anchored_ask_surface_text"] = _bio_anchored_surface_text
            except Exception as _ba_rt_exc:
                logger.warning(
                    "[chat_ws][bio_anchored] runtime71 surface failed conv=%s: %s",
                    conv_id, _ba_rt_exc,
                )

        # WO-LORI-FACTUAL-CHAIN-CAPTURE-01 Phase 2+3 (2026-06-24):
        # surface the composer_directive built earlier from
        # factual_chain_capture.build_factual_chain_followup_context.
        # When present, prompt_composer.compose_system_prompt injects
        # it as a high-priority [FACTUAL_CHAIN_DIRECTIVE] block above
        # per-pass/per-era/warmth rules. Empty / absent → no surface →
        # byte-stable for non-chain turns and turns where the
        # detection branch is disabled or errored.
        if _chain_directive_text:
            try:
                runtime71 = dict(runtime71) if isinstance(runtime71, dict) else {}
                runtime71["factual_chain_directive"] = _chain_directive_text
            except Exception as _fc_rt_exc:
                logger.warning(
                    "[chat_ws][factual-chain] runtime71 surface failed conv=%s: %s",
                    conv_id, _fc_rt_exc,
                )

        # BUG-SAFETY-DIRECTIVE-CONCATENATED-INTO-NARRATOR-TURN-01 (2026-07-14):
        # the UI used to APPEND its posture directive ([SAFETY MODE: ACTIVE ...],
        # [COMPANION MODE ...], etc.) onto the narrator's own message, so the
        # directive was archived, extracted, and mined for anchors as if the
        # narrator had SAID it. It now travels beside the message, in params,
        # and lands where it always belonged: the SYSTEM prompt.
        #
        # Sanitized like any other untrusted UI string, and hard-capped — this
        # is a directive channel, not an arbitrary prompt-injection surface.
        _ui_context_block = params.get("ui_context_block")
        _ui_system_for_prompt = None
        if isinstance(_ui_context_block, str) and _ui_context_block.strip():
            _ui_system_for_prompt = _ui_context_block.strip()[:1200]
            logger.info(
                "[chat_ws][ui-posture] directive routed to system prompt "
                "(posture=%s, %d chars) — NOT into the narrator turn",
                params.get("ui_posture") or "?", len(_ui_system_for_prompt))

        system_prompt = compose_system_prompt(
            conv_id, ui_system=_ui_system_for_prompt, user_text=user_text,
            runtime71=runtime71)

        # WO-TRIP-INTERVIEW-CONTEXT-01 Step 2 — when a trip is actively open
        # on the Travels shelf, append a compact, narrator-safe trip context
        # block so Lori can ask grounded questions. Default-OFF flag
        # (HORNELORE_TRIP_INTERVIEW_CONTEXT); the service owns the gate
        # (flag + active_trip_id + shelf open + trip owned by person_id) and
        # is read-only (no writes / dispatch / runtime mutation). Non-fatal:
        # the chat turn always proceeds even if this errors.
        try:
            from ..services import trip_interview_context as _tic
            _tic_block = _tic.context_block_for_turn(person_id, runtime71)
            if _tic_block:
                system_prompt = system_prompt + _tic_block
                logger.info("[chat_ws][trip-context] injected trip context "
                            "conv=%s person=%s", conv_id, person_id or "(none)")
            # Stamp prior-turn trip-scope for the NEXT narrator answer's
            # story capture (Step 2). The Lori turn we are composing now is
            # trip-scoped iff a trip-context block was injected.
            _TRIP_PREV_LORI[conv_id] = {
                "trip_scoped": bool(_tic_block),
                "prompt_kind": "trip" if _tic_block else None,
                "lori_text": None,   # filled with THIS turn's reply below
            }
            _cap_conv_cache(_TRIP_PREV_LORI)
        except Exception as _tic_exc:
            logger.warning("[chat_ws][trip-context] skipped conv=%s: %s",
                           conv_id, _tic_exc)

        # ── Debug logging ───────────────────────────────────────────────
        # Always log a compact runtime summary at INFO level.
        rt_summary = (
            f"pass={runtime71.get('current_pass','?')} "
            f"era={runtime71.get('current_era','?')} "
            f"mode={runtime71.get('current_mode','?')} "
            f"affect={runtime71.get('affect_state','?')} "
            f"fatigue={runtime71.get('fatigue_score','?')} "
            f"cog={runtime71.get('cognitive_mode','?')}"
        ) if runtime71 else "(no runtime71)"
        logger.info("[chat_ws] turn: conv=%s | %s", conv_id, rt_summary)

        # When LV_DEV_MODE=1, also log the full system prompt so you can
        # see exactly what the model receives.
        if _LV_DEBUG:
            sep = "─" * 60
            logger.info(
                "[chat_ws] SYSTEM PROMPT ↓\n%s\n%s\n%s",
                sep, system_prompt, sep
            )
        # ────────────────────────────────────────────────────────────────

        msgs: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        msgs.extend(
            [
                {"role": _normalize_role(m["role"]), "content": m["content"]}
                for m in history
                if _normalize_role(m.get("role", "")) != "system"
            ]
        )
        msgs.append({"role": "user", "content": user_text})

        # ── WO-LEAN-LORI-RUNTIME-01 Phase 4A ───────────────────────────
        # Fit the prompt HERE, where messages still exist, instead of
        # slicing tokens after the template. The slice below at :4294
        # kept the LAST N tokens, so it removed the FRONT -- Lori's
        # identity, purpose and interview discipline -- on 382 of 630
        # measured chat turns. That is the cemetery answer: she was not
        # ignoring her instructions, she was never shown them.
        #
        # Counted through the real `_apply_chat_template` + the real
        # tokenizer, because the template adds tokens of its own and a
        # builder-side estimate measures a prompt nobody sends.
        _budget = fit_chat_messages(
            msgs, limit=MAX_CHAT_PROMPT_TOKENS,
            count_tokens=lambda m: len(tok.encode(_apply_chat_template(m))))
        if not _budget.fits:
            # Honest refusal rather than a mutilated prompt. The
            # extraction lane already works this way; the same reasoning
            # holds here, and the narrator is told something true.
            logger.error("[chat_ws][prompt-budget] REFUSING turn — %s",
                         _budget.as_log_fields())
            await _ws_send(ws, {
                "type": "error",
                "code": "PROMPT_TOO_LARGE",
                "message": ("That message is too long for me to take in all "
                            "at once. Could you tell me a little at a time?"),
                "prompt_tokens": _budget.tokens,
                "limit": _budget.limit,
            })
            await _ws_send(ws, {"type": "done", "final_text": "",
                                "blocked": "prompt_too_large"})
            return
        if _budget.dropped_turns:
            # INFO, not WARNING: dropping old conversation is the budget
            # working as designed. The WARNING is reserved for the
            # refusal above, which is the condition that needs someone.
            logger.info("[chat_ws][prompt-budget] %s", _budget.as_log_fields())
        msgs = _budget.messages

        prompt = _apply_chat_template(msgs)

        # ── WO-10M: Cap enforcement + pre-generation VRAM guard ────────────
        # Resolve the effective max_new, capped hard at the launcher ceiling
        # so a misbehaving UI can't request 7168 and blow through our budget.
        _ui_max_new = int(params.get("max_new_tokens", params.get("max_new", _WO10M_CHAT_CAP)))
        max_new = max(1, min(_ui_max_new, _WO10M_CHAT_CAP_HARD))
        if max_new != _ui_max_new:
            logger.info("[chat_ws][WO-10M] capping max_new %d → %d (hard ceiling %d)",
                        _ui_max_new, max_new, _WO10M_CHAT_CAP_HARD)

        # Diagnostic: prompt size + current VRAM
        _prompt_tokens = len(tok.encode(prompt))
        try:
            _vram_free = torch.cuda.mem_get_info()[0] / 1024**2 if torch.cuda.is_available() else -1
            _vram_total = torch.cuda.mem_get_info()[1] / 1024**2 if torch.cuda.is_available() else -1
        except Exception as _mem_err:
            logger.warning("[chat_ws][WO-10M] mem_get_info failed pre-guard: %s", _mem_err)
            _vram_free, _vram_total = -1.0, -1.0

        # WO-10M: Pre-generation VRAM guard.
        # Conservative planning formula:
        #   required_mb = base + (prompt_tokens + max_new) * per_token_mb
        # base covers the MLP down_proj transient spike (~600 MB on Llama-3.1-8B
        # 4-bit). per_token_mb of 0.14 covers KV cache (~128 KB/token for GQA)
        # plus per-token activation overhead. If free VRAM is below this
        # threshold we refuse the turn cleanly instead of calling generate()
        # and crashing mid-forward-pass.
        _planned_seq = min(_prompt_tokens, MAX_CHAT_PROMPT_TOKENS) + max_new
        _required_mb = _WO10M_GUARD_BASE_MB + _planned_seq * _WO10M_GUARD_PER_TOKEN_MB
        _guard_blocked = False
        _guard_decision = "disabled"
        if _WO10M_GUARD_ENABLED and _vram_free >= 0:
            if _vram_free < _required_mb:
                # One retry after empty_cache — fragmentation may be the culprit.
                try:
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    _vram_free = torch.cuda.mem_get_info()[0] / 1024**2
                except Exception:
                    pass
                if _vram_free < _required_mb:
                    _guard_blocked = True
                    _guard_decision = "blocked"
                else:
                    _guard_decision = "pass_after_flush"
            else:
                _guard_decision = "pass"

        logger.info(
            "[chat_ws][WO-10M] prompt_tokens=%d max_new=%d required=%.0f MB "
            "free=%.0f/%.0f MB guard=%s",
            _prompt_tokens, max_new, _required_mb, _vram_free, _vram_total, _guard_decision,
        )

        if _guard_blocked:
            logger.warning(
                "[chat_ws][WO-10M] BLOCKING turn: required=%.0f MB > free=%.0f MB "
                "(prompt=%d, max_new=%d). Not calling model.generate().",
                _required_mb, _vram_free, _prompt_tokens, max_new,
            )
            # WO-OPS-VRAM-VISIBILITY-01 Phase 2 — record the block for
            # operator dashboard + eval discipline header. Lazy import +
            # try/except so a stack_monitor failure can't kill the turn.
            try:
                from ..services import stack_monitor as _sm
                _sm.record_vram_guard_block()
            except Exception as _vram_rec_exc:
                logger.warning(
                    "[chat_ws][WO-10M] vram-guard counter record failed: %s",
                    _vram_rec_exc,
                )
            await _ws_send(ws, {
                "type": "error",
                "code": "VRAM_PRESSURE",
                "message": "Not enough GPU memory for this turn — please try a shorter message or try again shortly.",
                "vram_free_mb": round(_vram_free),
                "required_mb": round(_required_mb),
                "prompt_tokens": _prompt_tokens,
            })
            await _ws_send(ws, {"type": "done", "final_text": "", "blocked": "vram_pressure"})
            return

        # Prep generation — clear cache first for max headroom
        if torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass
        inputs = tok(prompt, return_tensors="pt").to(model.device)
        # WO-1 VRAM guard: truncate input to MAX_CONTEXT_WINDOW to prevent KV cache OOM
        if inputs["input_ids"].shape[-1] > MAX_CHAT_PROMPT_TOKENS:
            # ── Phase 4A: this is now a BACKSTOP, and it should never fire.
            #
            # The blind front-slice that used to live here is gone. It kept
            # the LAST N tokens, so it removed the FRONT -- Lori's identity
            # -- on 382 of 630 measured turns. `fit_chat_messages` above now
            # guarantees the prompt fits before we get here.
            #
            # Reaching this line means the budget's count and the real
            # tokenizer disagreed, which is a defect in the budget rather
            # than an oversized prompt. So it is logged at ERROR with a
            # name that says so, and the turn is REFUSED rather than
            # silently mutilated: a disagreement of unknown size could be
            # one token or two thousand, and there is no way to tell from
            # here which part of Lori's prompt would be lost.
            logger.error(
                "[chat_ws][prompt-budget] BACKSTOP FIRED — budget said this "
                "prompt fit and the tokenizer disagrees (%d > %d). Refusing "
                "rather than cutting Lori's instructions.",
                inputs["input_ids"].shape[-1], MAX_CHAT_PROMPT_TOKENS)
            await _ws_send(ws, {
                "type": "error",
                "code": "PROMPT_TOO_LARGE",
                "message": ("Something went wrong preparing that turn. "
                            "Please try again."),
                "prompt_tokens": int(inputs["input_ids"].shape[-1]),
                "limit": MAX_CHAT_PROMPT_TOKENS,
            })
            await _ws_send(ws, {"type": "done", "final_text": "",
                                "blocked": "prompt_budget_backstop"})
            return
        streamer = TextIteratorStreamer(tok, skip_prompt=True, skip_special_tokens=True)

        # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 §3.2: NO
        # ev.clear() here. `ev` is this turn's OWN freshly minted event
        # (created in the start_turn handler); clearing at this point was
        # the race that could un-cancel a previous, still-running
        # generation sharing the socket-wide event. StopOnEvent receives
        # the event owned by exactly this generation.
        stop = StoppingCriteriaList([StopOnEvent(ev)])

        temperature = float(params.get("temperature", params.get("temp", 0.8)))
        top_p = float(params.get("top_p", 0.95))
        # WO-QA-01: per-request repetition_penalty, env default, hardcode fallback.
        repetition_penalty = float(params.get("repetition_penalty", _REP_PENALTY_DEFAULT))
        # WO-QA-02B: optional per-request seed for deterministic regression tests.
        # When supplied, we set torch.manual_seed before generate() so the
        # same prompt + same sampling params reproduces the same response
        # exactly. The harness sets seed=0 in its config grid; the production
        # UI omits it so behavior stays naturally varied for narrators.
        _seed = params.get("seed")
        if _seed is not None:
            try:
                torch.manual_seed(int(_seed))
                if torch.cuda.is_available():
                    torch.cuda.manual_seed_all(int(_seed))
            except Exception as _seed_err:
                logger.warning("[chat_ws][WO-QA-02B] seed apply failed: %s", _seed_err)

        # WO-S1: Centralized generation parameter guard — temp≤0 → greedy
        _do_sample = temperature > 0
        if not _do_sample:
            temperature = 1.0  # dummy; ignored when do_sample=False

        await _ws_send(ws, {"type": "status", "state": "generating"})

        th = threading.Thread(
            target=model.generate,
            kwargs=dict(
                **inputs,
                streamer=streamer,
                max_new_tokens=max_new,
                temperature=temperature,
                top_p=top_p,
                do_sample=_do_sample,
                repetition_penalty=repetition_penalty,
                stopping_criteria=stop,
                pad_token_id=tok.eos_token_id,
                eos_token_id=tok.eos_token_id,
            ),
            daemon=True,
        )

        # ── WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 follow-up
        # (fix(chat-ws): serialize generation) — NEVER overlap
        # model.generate calls on this socket. The superseded turn's
        # cancel event was set by the start_turn handler, but its daemon
        # thread only notices at the next token boundary (tens of ms).
        # Bounded join off the event loop; if the previous generate has
        # not exited within the window, we REFUSE this turn rather than
        # run dual generation (the audit's VRAM-pressure finding). A
        # refusal here is loud (ERROR log + error event) and recoverable
        # (the client can re-send); dual generation is neither.
        _prev_gen_th = generation_thread_holder.get("thread")
        if _prev_gen_th is not None and _prev_gen_th.is_alive():
            logger.info(
                "[chat_ws][gen-serialize] waiting for previous generation "
                "thread to exit conv=%s", conv_id,
            )
            await asyncio.to_thread(_prev_gen_th.join, 10.0)
            if _prev_gen_th.is_alive():
                logger.error(
                    "[chat_ws][gen-serialize] previous generation thread "
                    "did NOT exit within 10s conv=%s — refusing to start "
                    "a second concurrent model.generate (dual-generation "
                    "VRAM pressure). Turn dropped; client may retry.",
                    conv_id,
                )
                await _ws_send(ws, {
                    "type": "error",
                    "code": "GENERATION_BUSY",
                    "message": "The previous response is still winding "
                               "down — please try again in a moment.",
                })
                await _ws_send(ws, {
                    "type": "done", "final_text": "",
                    "blocked": "generation_serialization",
                })
                return
        generation_thread_holder["thread"] = th
        th.start()

        reply_parts: List[str] = []

        def _next_chunk():
            try:
                return next(streamer)
            except StopIteration:
                return None

        # WO-LORI-ACTIVE-LISTENING-01 Layer 2 — discipline filter mode gate.
        # 2026-04-29 fix: when the flag is on, BUFFER chunks silently instead
        # of streaming them. Otherwise the narrator already saw the bad
        # multi-question response before the post-stream trim runs — the
        # filter would only protect persistence, not visible behavior.
        # Buffer-then-send sacrifices token-by-token UX for parent-session
        # safety. Off-by-default; opt in via HORNELORE_INTERVIEW_DISCIPLINE=1.
        #
        # BANK_PRIORITY_REBUILD 2026-05-10 — witness-receipt mode is
        # ALWAYS buffered, regardless of the discipline-filter flag.
        # The 2026-05-10 Kent Fort Ord one-shot proved the LLM emits
        # third-person narrator-voice mimicry ("The narrator shares a
        # vivid account...") on long monologues; the post-stream
        # validator catches that and swaps in the deterministic
        # fallback at `done`, but raw tokens were already streamed to
        # the client (and therefore TTS / chat bubble). For Kent's
        # parent session that is unsafe — he could hear the bad
        # response before validation. Buffer in witness-receipt mode
        # by construction; client receives only the validated final.
        # BUG-LORI-RAW-STREAM-BEFORE-GUARDS-01 (2026-07-07): buffer
        # UNCONDITIONALLY. Raw tokens used to stream to the client while
        # the response guards (meta-preamble class, language drift,
        # seeded-fact, sensory-pivot) only ran after generation — the
        # narrator could see leaked text before the repaired final_text
        # replaced the bubble on `done` (live evidence 2026-07-07: the
        # trip-open "Here is the response in the requested format:"
        # leak). All narrator-visible LLM output now buffers server-side
        # and emits ONCE, after apply_response_guards, via the deferred
        # single-delta block just before `done` (witness-receipt mode
        # pioneered this posture; it now applies to every LLM turn on
        # this path). The discipline-filter flag no longer gates
        # buffering — it only gates the trim itself.
        _buffer_mode = True
        if _witness_use_llm_receipt:
            logger.info(
                "[chat_ws][witness][buffered-stream] conv=%s — "
                "tokens buffered server-side; emitting only validated "
                "final via done event",
                conv_id,
            )

        while True:
            if ev.is_set():
                break

            chunk = await asyncio.to_thread(_next_chunk)
            if chunk is None:
                break
            if not chunk:
                continue

            reply_parts.append(chunk)
            if not _buffer_mode:
                await _ws_send(ws, {"type": "token", "delta": chunk})

        final_text = "".join(reply_parts).strip()

        # ── WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 follow-up
        # (fix(chat-ws): never persist cancelled turns) — a cancelled
        # turn aborts HERE, immediately after the generation loop,
        # BEFORE: comm-control, discipline trim, era-fragment repair,
        # Spanish guards, duplicate check, witness validator, response
        # guards, persist_turn_transaction, archive writes, follow-up-
        # bank writes, trip-capture memory update, and the deferred
        # token emit. Previously the partial text flowed through the
        # whole post-generation pipeline and could be persisted with a
        # `cancelled` meta flag — a half-generated reply the narrator
        # explicitly cancelled has no business in history, the archive,
        # or the bank. The socket gets an empty, explicitly-cancelled
        # done and nothing else.
        #
        # NOTE (spec'd by Chris, flagged in the WO report): aborting
        # before persist_turn_transaction also drops the NARRATOR's
        # user text for this turn from the turns table — zero new turn
        # rows means zero, both halves. The replacing turn carries its
        # own user text. (The memory-archive user-turn write happens
        # BEFORE generation and is unaffected, so the narrator's words
        # are still retained in the archive.)
        if ev.is_set():
            logger.warning(
                "[chat_ws][cancel] turn cancelled mid-generation conv=%s "
                "— discarding %d chars of partial text; nothing persisted",
                conv_id, len(final_text),
            )
            await _ws_send(ws, {
                "type": "done", "final_text": "", "cancelled": True,
            })
            return

        # WO-LORI-COMMUNICATION-CONTROL-01 — the unifying runtime
        # enforcement layer. Replaces the per-WO call sites for
        # ATOMICITY-01 and REFLECTION-01 with one wrapper that runs:
        #   safety exemption → atomicity (truncate) → question-count cap
        #   → word-count cap (per session_style) → reflection (validate)
        #
        # Architecture rationale (Wang et al. 2025 STA): prompt
        # engineering is fragile to small input changes; deterministic
        # runtime enforcement is robust. This wrapper IS the runtime
        # authority. The LORI_INTERVIEW_DISCIPLINE prompt block is
        # Layer 1 (always-on guidance); this wrapper is Layer 2
        # (always-on enforcement when the flag is on).
        #
        # Runs in BOTH streaming and buffer modes. The `done` event
        # below carries result.final_text; harness reads it via
        # final_text_from_done.
        #
        # Memory_echo / correction turns return earlier (above) so they
        # bypass this filter by construction. Acute safety responses
        # bypass via the _safety_result.triggered flag inside the
        # wrapper.
        #
        # Gated DEFAULT-OFF behind HORNELORE_COMMUNICATION_CONTROL for
        # the first eval cycle. The legacy HORNELORE_ATOMICITY_FILTER
        # / HORNELORE_REFLECTION_VALIDATOR flags are deprecated — when
        # COMMUNICATION_CONTROL is on, the wrapper handles both. When
        # off, no enforcement runs (Layer 1 prompt directives still
        # fire). After one clean golfball rerun + master extractor
        # eval green, flip COMMUNICATION_CONTROL default to ON.
        comm_control_dict: Dict[str, Any] = {}
        atomicity_failures: List[str] = []
        reflection_failures: List[str] = []
        try:
            _cc_enabled = os.environ.get(
                "HORNELORE_COMMUNICATION_CONTROL", "0"
            ).strip().lower() in ("1", "true", "yes", "on")
            if _cc_enabled and final_text:
                from ..services.lori_communication_control import (
                    enforce_lori_communication_control,
                )
                # WO-LORI-SOFTENED-RESPONSE-01: softened state is also
                # a "safety frame" from the wrapper's perspective. Even
                # when this turn's user_text didn't match an acute
                # pattern (so _safety_result.triggered=False), if the
                # session is in softened mode from a prior acute
                # trigger, the wrapper should route through the
                # safety-exempt path — no atomicity rewrite of a
                # softened-mode response, and a "normal Q during
                # safety" check is exactly what flags Turn 07's bug.
                _acute_now = bool(
                    _safety_result and getattr(_safety_result, "triggered", False)
                )
                _softened_now = bool(
                    isinstance(_softened_state, dict)
                    and _softened_state.get("interview_softened")
                )
                _safety_triggered_now = _acute_now or _softened_now
                _session_style = (
                    (params.get("session_style") if isinstance(params, dict) else None)
                    or "clear_direct"
                )
                # BUG-STT-PHANTOM-PROPER-NOUNS-01 Layer 2 (2026-05-07):
                # Scrub Lori's reply for proper nouns the narrator never
                # said and that aren't in the canonical profile_seed.
                # Default-OFF behind HORNELORE_PHANTOM_NOUN_GUARD=1
                # (flag-only — logs warnings but doesn't mutate). With
                # HORNELORE_PHANTOM_NOUN_SCRUB=1 also on, drops the
                # offending sentence from final_text. Best-effort: any
                # exception here is logged + reply unchanged. Layer 1
                # is the mic-modal (#50 Phase A landed); Layer 3 is
                # the extractor verbatim guard (parked).
                #
                # Builds narrator_corpus by concatenating the most
                # recent narrator turns from comm-control's user_text
                # (current turn) + last 2 archive turns when available.
                # profile_seed comes straight from runtime71.
                try:
                    from ..services.lori_communication_control import (
                        scrub_phantom_proper_nouns as _scrub_phantom,
                        _phantom_noun_guard_enabled as _phantom_guard_on,
                        _phantom_noun_scrub_enabled as _phantom_scrub_on,
                    )
                except Exception as _imp_exc:
                    _scrub_phantom = None
                    _phantom_guard_on = lambda: False
                    _phantom_scrub_on = lambda: False
                    logger.debug("[chat_ws][phantom-noun] import failed: %s", _imp_exc)

                if _scrub_phantom is not None and _phantom_guard_on():
                    try:
                        # Build narrator_corpus from current turn + recent archive
                        _narrator_parts = [user_text or ""]
                        try:
                            _recent = export_turns(conv_id) or []
                            # Take last 4 user turns, skip the current one (head)
                            _user_turns = [
                                t.get("content", "") for t in _recent
                                if isinstance(t, dict) and (t.get("role") or "").lower() == "user"
                            ]
                            _narrator_parts = _user_turns[-3:] + _narrator_parts
                        except Exception:
                            pass
                        _narrator_corpus = " ".join(p for p in _narrator_parts if p).strip()

                        _profile_seed = (
                            runtime71.get("profile_seed")
                            if isinstance(runtime71, dict) else {}
                        ) or {}

                        _phantom_result = _scrub_phantom(
                            final_text,
                            narrator_corpus=_narrator_corpus,
                            profile_seed=_profile_seed,
                            scrub_mode=_phantom_scrub_on(),
                        )
                        if _phantom_result.get("flagged"):
                            logger.warning(
                                "[chat_ws][phantom-noun] flagged=%s scrub_mode=%s "
                                "scrubbed=%s conv=%s",
                                _phantom_result["flagged"],
                                _phantom_scrub_on(),
                                _phantom_result["scrubbed"],
                                conv_id,
                            )
                            if _phantom_result.get("scrubbed"):
                                final_text = _phantom_result["final_text"]
                    except Exception as _phantom_exc:
                        logger.warning(
                            "[chat_ws][phantom-noun] guard threw (chat continues): %s",
                            _phantom_exc,
                        )

                _cc_result = enforce_lori_communication_control(
                    assistant_text=final_text,
                    user_text=user_text or "",
                    safety_triggered=_safety_triggered_now,
                    session_style=str(_session_style),
                    softened_mode_active=_softened_now,
                    # WO-LORI-SOFTENED-MODE-PERSISTENCE-01 — pass the
                    # full state dict so the wrapper picks the right
                    # per-trigger + per-state word cap (acute=30,
                    # past-tense=35, softened_exiting=50).
                    softened_state=_softened_state if isinstance(_softened_state, dict) else None,
                    # WO-LORI-STORY-FIRST-PHASE-1-01 — momentum mode and
                    # session hierarchy state for the Phase 1 validators
                    # (reflection grounding + question hierarchy). Both
                    # default to "normal" / None when the flag is off,
                    # which makes the Phase 1 validators vacuous.
                    # Hierarchy state tracking (has_layer_1_succeeded,
                    # etc.) is parked behind a follow-up task; v1 ships
                    # with the dict empty so all higher layers are
                    # eligible-by-default — the validator can still
                    # flag absent reflection grounding, which is the
                    # high-value check for v1 telemetry.
                    momentum_mode=_phase_1_momentum_mode,
                    session_hierarchy_state=None,
                    # BUG-LORI-RESPONSE-STUB-COLLAPSE-01 it 2
                    # (2026-06-25): narrator anchors detected by
                    # factual_chain_capture upstream. Threaded so
                    # Step 6 substitutes an anchor-aware English
                    # continuation instead of letting bare anchor
                    # stubs reach the narrator.
                    narrator_anchors=list(
                        (_chain_ctx or {}).get("anchors") or []
                    ),
                    # BUG-LORI-CHAIN-ANCHOR-ECHO-STRENGTH-01 Path B
                    # (2026-07-02): gates the Step 6b anchor-echo
                    # injection on chain turns.
                    is_factual_chain=bool(
                        (_chain_ctx or {}).get("is_factual_chain")
                    ),
                )
                comm_control_dict = _cc_result.to_dict()
                atomicity_failures = list(_cc_result.atomicity_failures)
                reflection_failures = list(_cc_result.reflection_failures)
                if _cc_result.changed:
                    logger.warning(
                        "[chat_ws][comm_control] changed=True conv=%s "
                        "failures=%s atomicity=%s reflection=%s "
                        "before_words=%d after_words=%d",
                        conv_id,
                        ",".join(_cc_result.failures),
                        ",".join(_cc_result.atomicity_failures),
                        ",".join(_cc_result.reflection_failures),
                        len(final_text.split()),
                        _cc_result.word_count,
                    )
                    final_text = _cc_result.final_text
                # WO-LORI-REFLECTION-02 — emit a dedicated reflection-
                # shape log line whenever the shaper rewrote the turn.
                # Easier to grep than parsing the comm_control failures
                # list. Fires for both ordinary-path and softened-path
                # shaping; only emits when HORNELORE_REFLECTION_SHAPING
                # is on AND the shaper actually changed something.
                _shape_warnings = [
                    w for w in (_cc_result.warnings or [])
                    if isinstance(w, str) and w.startswith("reflection_shaped:")
                ]
                if _shape_warnings:
                    logger.info(
                        "[lori][reflection-shape] conv=%s actions=%s "
                        "softened=%s before_words=%d",
                        conv_id,
                        ",".join(w.split(":", 1)[1] for w in _shape_warnings),
                        _softened_now,
                        len((_cc_result.original_text or "").split()),
                    )
                elif _cc_result.failures or _cc_result.reflection_failures:
                    # Validation-only failures (reflection in v1, or
                    # safety-path "normal Q during safety"). No mutation.
                    logger.warning(
                        "[chat_ws][comm_control] validate-only conv=%s "
                        "failures=%s atomicity=%s reflection=%s "
                        "safety=%s",
                        conv_id,
                        ",".join(_cc_result.failures),
                        ",".join(_cc_result.atomicity_failures),
                        ",".join(_cc_result.reflection_failures),
                        _cc_result.safety_triggered,
                    )
        except Exception as _cc_exc:
            # Filter is a safety net — never kill a turn on enforcement
            # error. Log and continue with the original text.
            logger.warning(
                "[chat_ws][comm_control] wrapper raised, passing through: %s",
                _cc_exc,
            )

        # WO-LORI-ACTIVE-LISTENING-01 Layer 2 (legacy, retained for
        # backward compat with HORNELORE_INTERVIEW_DISCIPLINE flag).
        # Buffer-mode-only. Will be retired once ATOMICITY-01 default-on
        # is observed clean across two consecutive runs.
        #
        # WO-LORI-SAFETY-INTEGRATION-01 Phase 5a (2026-05-03): when a
        # safety event has triggered this turn (pattern OR LLM
        # second-layer), the safety response legitimately exceeds the
        # one-question discipline (988 + Friendship Line + warm
        # acknowledgment + step structure) and uses safety language
        # patterns the trim regex would mis-match as compound questions.
        # SKIP THE TRIM on safety-routed turns. The safety response
        # itself was carefully composed to be the right shape; the
        # one-question discipline is for normal interview turns.
        _is_safety_turn = bool(_safety_result and _safety_result.triggered)
        # BUG-LORI-RAW-STREAM-BEFORE-GUARDS-01: no pre-guard emits.
        # Every branch below marks the emit as pending; the single
        # delta fires AFTER apply_response_guards (deferred block
        # before `done`). This also fixes a mismatch where safety
        # turns SHOWED pre-guard text but ARCHIVED post-guard text.
        _deferred_emit_pending = False
        if _is_safety_turn and _buffer_mode and final_text:
            logger.info(
                "[lori][discipline][safety-exempt] trim skipped conv=%s "
                "category=%s — safety response bypasses one-question rule",
                conv_id,
                _safety_result.category if _safety_result else "?",
            )
            _deferred_emit_pending = True
            # Skip the normal trim path for this turn entirely.
            _buffer_mode_for_trim = False
        else:
            _buffer_mode_for_trim = _buffer_mode
        try:
            from ..prompt_composer import _trim_to_one_question
            if _buffer_mode_for_trim and final_text:
                _trimmed, _was_trimmed, _reason = _trim_to_one_question(final_text)
                if _was_trimmed:
                    logger.info(
                        "[lori][discipline] trim-to-one-q conv=%s reason=%s before_len=%d after_len=%d",
                        conv_id, _reason, len(final_text), len(_trimmed),
                    )
                    final_text = _trimmed
                # Buffer mode: emit the cleaned text as a single delta so
                # the client UI gets the same shape it expects (token + done).
                #
                # BANK_PRIORITY_REBUILD 2026-05-10 — EXCEPT when witness-
                # receipt mode is active. The witness validator at L2541+
                # runs AFTER this point and may replace final_text with
                # the deterministic fallback. Emitting here would leak
                # the LLM's pre-validation text (third-person mimicry,
                # "Here is a response following the guidelines:", etc.)
                # to the client BEFORE validation. Defer the single-
                # delta emit to AFTER the validator (L2660+ via the
                # post-validator block we add there).
                if not _witness_use_llm_receipt:
                    # BUG-LORI-RAW-STREAM-BEFORE-GUARDS-01: defer —
                    # response guards haven't run yet.
                    _deferred_emit_pending = True
                else:
                    logger.info(
                        "[chat_ws][witness][buffered-stream] conv=%s — "
                        "deferring token emit until post-validator",
                        conv_id,
                    )
        except Exception as _disc_exc:
            # Filter is a safety net — never let it kill a turn. If trim
            # raised in buffer mode, the untrimmed text still reaches the
            # narrator via the deferred post-guard emit.
            logger.warning("[lori][discipline] filter raised, passing through: %s", _disc_exc)
            if _buffer_mode_for_trim and final_text:
                if not _witness_use_llm_receipt:
                    _deferred_emit_pending = True

        # Phase G: fail-closed — only persist if generation completed cleanly.
        # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 follow-up: the
        # primary cancelled-turn abort now happens immediately after the
        # generation loop (above); this is the belt for the LATE race — a
        # cancel that lands while the post-generation pipeline is running.
        # Same contract: empty final_text, nothing persisted.
        if ev.is_set():
            logger.warning("[chat-ws] Turn cancelled/disconnected — skipping persistence (fail-closed)")
            await _ws_send(ws, {"type": "done", "final_text": "", "cancelled": True})
            return

        # BUG-LORI-ERA-FRAGMENT-COHERENCE-01 (2026-05-06): post-generation
        # repair guard for noun-phrase fragments masquerading as questions.
        # v8 evidence: Mary's coming_of_age + later_years prompts produced
        # "The conversations you had together back then?" / "The reflections
        # that came as you looked back on your life?" — both noun phrases
        # ending in '?', not actual questions. The era-click directive
        # tightening (app.js, same date) reduces frequency; this guard
        # catches the residual at output time. Pure repair: prepends
        # "Can you tell me about" to convert the fragment to a full
        # question. Skipped when the response already starts with a
        # wh-word, auxiliary verb, or imperative.
        try:
            import re as _re
            _ft_stripped = (final_text or "").strip()
            # Detect: starts with "The ..." OR "Those ..." OR "Your ..."
            # AND ends with "?" AND doesn't already have a wh-word or
            # auxiliary verb starting it. Targets the exact failure shape.
            # Detect the noun-phrase-fragment shape:
            #   Article + noun-phrase + (relative clause: "you|that") + ...?
            # Examples that match (true positives):
            #   "The conversations you had together back then?"
            #   "The reflections that came as you looked back on your life?"
            #   "Your favorite memory from that time?"
            # Excluded (full sentences with main verb after article):
            #   "That was a special time, wasn't it?"   (was = main verb)
            #   "The book is on the table?"             (is = main verb)
            # Heuristic: the second token must NOT be a main copula/auxiliary
            # in subject-verb-second position. Skip if (article noun) + "was/
            # were/is/are/had/have/will/would" appears at sentence start.
            # Match "Article + (zero or one noun) + main-verb" — i.e.,
            # the main verb appears as 2nd or 3rd token. Skips:
            #   "That was..."           ← That + was (skip-correct)
            #   "Those days were..."    ← Those + days + were (skip-correct)
            #   "The book is..."        ← The + book + is (skip-correct)
            # Doesn't skip:
            #   "The conversations you had..."   ← The + conversations + you + had (verb is 4th token, "you" between)
            #   "The walk you took every morning?" ← (same shape)
            _MAIN_VERB_RX = _re.compile(
                r"^(?:The|Those|Your|That|These|This)\s+"
                r"(?:\w+\s+)?"  # optional ONE noun
                r"(?:was|were|is|are|had|have|will|would|should|"
                r"could|might|may|do|does|did|can|won't|isn't|"
                r"wasn't|weren't|aren't)\b",
                _re.IGNORECASE,
            )
            if (
                _ft_stripped
                and _ft_stripped.endswith("?")
                and _re.match(r"^(?:The|Those|Your|That)\s+\w", _ft_stripped)
                and not _MAIN_VERB_RX.match(_ft_stripped)
                and not _re.match(
                    r"^(?:What|Where|When|Who|How|Why|Did|Were|Was|Had|Could|"
                    r"Can|Do|Does|Is|Are|Will|Would|Should|May|Might|Tell|"
                    r"Share|Say|Describe)\b",
                    _ft_stripped,
                    _re.IGNORECASE,
                )
            ):
                # Lowercase the leading article so "The conversations..." →
                # "the conversations..."
                _repaired = "Can you tell me about " + _ft_stripped[0].lower() + _ft_stripped[1:]
                logger.info(
                    "[lori][era-fragment-repair] noun-phrase fragment repaired conv=%s "
                    "original=%r → repaired=%r",
                    conv_id, _ft_stripped[:80], _repaired[:100],
                )
                final_text = _repaired
        except Exception as _frag_err:
            logger.debug("[lori][era-fragment-repair] check failed (non-fatal): %s", _frag_err)

        # BUG-ML-LORI-SPANISH-PERSPECTIVE-01 (2026-05-07): post-LLM
        # Spanish output guards. Two repairs:
        #   1. Perspective: rewrite "Mi abuela/mamá/papá" → "Tu X" when
        #      Lori is reflecting the narrator's family. Quote-safe.
        #   2. Fragment: trim Spanish sentences ending on a dangling
        #      connector ("su", "que", "cuando", "después de que").
        # English responses are no-ops — the helper detects Spanish
        # via accent chars / function-word density before firing.
        # Failure is non-fatal; falls through to legacy behavior.
        try:
            from ..services.lori_spanish_guard import (
                apply_spanish_guards as _apply_es_guards,
                detect_question_quality as _detect_es_q_quality,
            )
            _es_repaired, _es_changes = _apply_es_guards(final_text, user_text)
            if _es_changes:
                logger.info(
                    "[lori][es-guard] conv=%s changes=%s original=%r → repaired=%r",
                    conv_id, _es_changes, final_text[:120], _es_repaired[:120],
                )
                final_text = _es_repaired
            # BUG-ML-LORI-SPANISH-ACTIVE-LISTENING-QUESTION-01
            # (2026-05-07): detector-only — log yes/no closers and
            # missing Q-words but DO NOT rewrite the response. Locked
            # principle from BUG-LORI-REFLECTION-02 Patch B postmortem:
            # prompt-heavy reflection rules backfire; runtime content-
            # rewriting on questions risks the same regression. The
            # operator log captures violations so we can decide
            # whether to tighten prompt rules OR add deterministic
            # runtime question-rewrite later. Spanish-only: detector
            # short-circuits to [] on English.
            _es_q_issues = _detect_es_q_quality(final_text)
            if _es_q_issues:
                logger.info(
                    "[lori][es-active-listening] conv=%s issues=%s text=%r",
                    conv_id, _es_q_issues, final_text[:160],
                )
        except Exception as _es_err:
            logger.debug("[lori][es-guard] check failed (non-fatal): %s", _es_err)

        # BUG-LORI-DUPLICATE-RESPONSE-01 (2026-05-06): fingerprint guard
        # with deterministic bridge fallback. v8 evidence: Mary's two
        # consecutive Today cycles produced bit-identical replies. The
        # LLM either context-matched too strongly OR sampled the same
        # tokens. Without LLM-reroll access from this layer, the safe
        # fix is: when bit-identical to the most recent prior reply,
        # substitute a deterministic bridge phrase that gently moves
        # the conversation forward without flagging the duplicate to
        # the narrator. Per ChatGPT triage: "Do not make this narrator-
        # visible as 'I already said that.'"
        try:
            import hashlib as _hashlib
            _final_hash = _hashlib.sha256((final_text or "").encode("utf-8")).hexdigest()[:12]
            _final_tokens = set((final_text or "").lower().split())
            _prior_assistant = None
            try:
                # 2026-07-11 repo-review HIGH fix — `db.export_turns` was
                # a NameError (only `export_turns` was imported at L129;
                # the `db` module name was never bound). The wrapping
                # try/except swallowed it, so `_prior_turns` was always
                # [] and the bit-identical duplicate-reply substitution
                # never actually fired.
                _all_turns = export_turns(conv_id) or []
                _prior_turns = _all_turns[-6:]
            except Exception:
                _prior_turns = []
            for _t in reversed(_prior_turns):
                if _t.get("role") == "assistant" and _t.get("content"):
                    if _t.get("content") == final_text:
                        continue
                    _prior_assistant = _t.get("content")
                    break
            if _prior_assistant:
                _prior_norm = " ".join((_prior_assistant or "").lower().split()).strip(" .!?")
                _final_norm = " ".join((final_text or "").lower().split()).strip(" .!?")
                _bit_identical = _final_norm == _prior_norm and len(_final_norm) > 0
                _prior_tokens = set(_prior_assistant.lower().split())
                _intersect = len(_final_tokens & _prior_tokens)
                _union = max(len(_final_tokens | _prior_tokens), 1)
                _jaccard = _intersect / _union
                # Bridge phrases — deterministic, never invent narrator
                # facts. Rotate by hash so consecutive duplicates don't
                # produce the same bridge. ChatGPT-triage-approved set.
                _BRIDGES = (
                    "What part of that feels most present for you today?",
                    "Would you like to stay with that for a moment, "
                    "or move to another part of your story?",
                    "What has that been like for you lately?",
                    "Is there a particular memory from that time that "
                    "still feels close?",
                )
                if _bit_identical:
                    # Pick a bridge by hash so we don't always emit the
                    # same one when this fires repeatedly in a session.
                    _idx = int(_final_hash, 16) % len(_BRIDGES)
                    _bridge = _BRIDGES[_idx]
                    logger.warning(
                        "[lori][duplicate-response] BIT-IDENTICAL "
                        "substituted bridge=%d conv=%s — original_hash=%s",
                        _idx, conv_id, _final_hash,
                    )
                    final_text = _bridge
                elif _jaccard >= 0.85:
                    # High-similarity but not bit-identical — log only.
                    # Real fix would be LLM reroll; without that access
                    # here, leave the response and trust shape_reflection
                    # to handle minor variation.
                    logger.warning(
                        "[lori][duplicate-response] HIGH-SIMILARITY "
                        "jaccard=%.3f hash=%s conv=%s — left as-is "
                        "(reroll not available from this layer)",
                        _jaccard, _final_hash, conv_id,
                    )
                else:
                    logger.debug(
                        "[lori][response-hash] hash=%s jaccard=%.3f conv=%s",
                        _final_hash, _jaccard, conv_id,
                    )
            else:
                logger.debug("[lori][response-hash] hash=%s no_prior conv=%s",
                             _final_hash, conv_id)
        except Exception as _dup_err:
            logger.debug("[lori][duplicate-response] check failed (non-fatal): %s", _dup_err)

        # ── BUG-LORI-WITNESS-LLM-RECEIPT-01 — post-LLM validator + fallback ──
        # When the upstream detector flagged this turn as STRUCTURED_
        # NARRATIVE, the system prompt was injected with the WITNESS
        # RECEIPT directive (prompt_composer._WITNESS_RECEIPT_DIRECTIVE).
        # The validator now checks that final_text actually obeyed:
        #   - no FORBIDDEN_TOKENS (sights, sounds, smells, scenery,
        #     camaraderie, "how did that feel", etc.)
        #   - no FIRST_PERSON_MIMICRY ("our son", "we were in Germany",
        #     "my wife")
        #   - 35–110 words (witness receipt is meaty but not bloated)
        #   - ≤1 question (one open invitation to continue)
        #   - ≥3 narrator-named facts echoed (real reflection, not a
        #     label list)
        #
        # On any failure, replace final_text with the deterministic
        # compose_witness_response output for the same detection. Kent
        # never sees a sensory probe even when the LLM drifts under
        # directive pressure. Runs BEFORE the surface-level response
        # guards so we don't waste polish on text we're throwing away.
        if (
            _witness_use_llm_receipt
            and _witness_detection_for_fallback is not None
            and final_text
        ):
            try:
                from ..services.lori_witness_mode import (
                    validate_witness_receipt as _validate_wr,
                    compose_witness_response as _compose_wr,
                    compose_structured_witness_receipt as _compose_rich,
                )
                _wr_ok, _wr_failures = _validate_wr(
                    lori_text=final_text,
                    narrator_text=user_text or "",
                )
                if not _wr_ok:
                    # WO-LORI-WITNESS-FOLLOWUP-BANK-01 — prefer the
                    # rich receipt + immediate-door composer when in
                    # English. Falls back to legacy compose_witness_
                    # response when no anchors found OR Spanish locale.
                    _wr_fallback = ""
                    # BUG-LORI-SAME-ANCHOR-LOOP-01 (2026-06-24): pull
                    # anchors from the last 2 assistant turns so the
                    # diversity guard can avoid repeating the same lead
                    # anchor across consecutive turns. Walt Era 1 +
                    # Era 2 both naturally pick "Saint Augustine" as
                    # the lead; the loop scorer fires. Filtering recent
                    # anchors from the candidate pool eliminates this
                    # without changing per-turn anchor quality.
                    _witness_recent_anchors: List[str] = []
                    try:
                        from ..db import export_turns as _wr_export_turns
                        from ..services.lori_structured_narrative_fallback import (
                            extract_safe_anchors as _wr_safe_anchors,
                        )
                        _wr_hist = _wr_export_turns(conv_id) or []
                        _wr_recent_assist: List[str] = []
                        for _wr_t in _wr_hist:
                            if isinstance(_wr_t, dict) and _wr_t.get("role") == "assistant":
                                _wr_at = _wr_t.get("content") or ""
                                if _wr_at:
                                    _wr_recent_assist.append(_wr_at)
                        for _wr_at in _wr_recent_assist[-2:]:
                            for _wr_a in _wr_safe_anchors(_wr_at, max_n=4):
                                if _wr_a and _wr_a not in _witness_recent_anchors:
                                    _witness_recent_anchors.append(_wr_a)
                    except Exception as _wr_recent_exc:
                        logger.debug(
                            "[chat_ws][witness][diversity] recent-anchors "
                            "lookup raised conv=%s: %s — proceeding without "
                            "diversity filter",
                            conv_id, _wr_recent_exc,
                        )
                        _witness_recent_anchors = []
                    if _witness_receipt_lang == "en":
                        _wr_fallback = _compose_rich(
                            narrator_text=user_text or "",
                            llm_question=final_text,
                            target_language="en",
                            immediate_door_question=_immediate_door_question,
                            immediate_door_anchor=_immediate_door_anchor,
                            immediate_door_story_weight=_immediate_door_story_weight,
                            recent_assistant_anchors=_witness_recent_anchors,
                        )
                    if not _wr_fallback:
                        _wr_fallback = _compose_wr(
                            _witness_detection_for_fallback,
                            target_language=_witness_receipt_lang,
                        )
                    if _wr_fallback:
                        logger.warning(
                            "[chat_ws][witness][llm-receipt] validator "
                            "FAIL conv=%s failures=%s before=%r after=%r",
                            conv_id,
                            ",".join(_wr_failures) if _wr_failures else "",
                            (final_text or "")[:160],
                            _wr_fallback[:160],
                        )
                        final_text = _wr_fallback
                    else:
                        logger.warning(
                            "[chat_ws][witness][llm-receipt] validator "
                            "FAIL conv=%s but deterministic fallback "
                            "produced empty text; keeping LLM output. "
                            "failures=%s",
                            conv_id,
                            ",".join(_wr_failures) if _wr_failures else "",
                        )
                else:
                    logger.info(
                        "[chat_ws][witness][llm-receipt] validator PASS "
                        "conv=%s words=%d",
                        conv_id, len(final_text.split()),
                    )
            except Exception as _wr_exc:
                # Fail CLOSED. If the validator itself raises, the LLM
                # output has not been cleared of forbidden tokens, first-
                # person mimicry, length, fact-floor, or question-count
                # checks. For Kent's session we cannot risk showing
                # un-validated LLM text. Try the deterministic fallback;
                # only keep the LLM output if the fallback is empty
                # (e.g. event_phrases + multi_anchors both came back
                # zero, which means the upstream detector probably
                # shouldn't have routed here in the first place).
                _wr_fallback = ""
                try:
                    from ..services.lori_witness_mode import (
                        compose_witness_response as _compose_wr_safe,
                    )
                    _wr_fallback = _compose_wr_safe(
                        _witness_detection_for_fallback,
                        target_language=_witness_receipt_lang,
                    )
                except Exception as _wr_fallback_exc:
                    logger.warning(
                        "[chat_ws][witness][llm-receipt] validator AND "
                        "fallback both raised conv=%s val_exc=%s "
                        "fallback_exc=%s — keeping LLM output as last "
                        "resort",
                        conv_id, _wr_exc, _wr_fallback_exc,
                    )
                if _wr_fallback:
                    logger.warning(
                        "[chat_ws][witness][llm-receipt] validator raised "
                        "conv=%s: %s — fail-closed to deterministic "
                        "fallback; before=%r after=%r",
                        conv_id, _wr_exc,
                        (final_text or "")[:160],
                        _wr_fallback[:160],
                    )
                    final_text = _wr_fallback
                else:
                    logger.warning(
                        "[chat_ws][witness][llm-receipt] validator raised "
                        "conv=%s: %s — fallback empty, keeping LLM output",
                        conv_id, _wr_exc,
                    )

        # ── BUG-LORI-SESSION-LANGUAGE-CONTRACT-01 — Spanish-scaffolding repair guard ──
        # When the session is english-locked, ANY Spanish scaffolding
        # tokens leaking through (from validator-fallback, LLM drift, or
        # any other path) get hard-repaired to a deterministic English
        # fallback. The contract is: english mode never produces user-
        # facing Spanish/Spanglish, period. Detection signals:
        #   - Spanish-only punctuation: ¿ or ¡
        #   - Spanish-receipt scaffolding: "Capté", "Tú " (capitalized
        #     pronoun, English would use "You"), "¿Qué pasó después"
        #   - Spanish discourse markers in the middle of otherwise-
        #     English text: ", y " in narrative prose (English uses ",
        #     and "), "después" / "pasó" embedded as Spanish vocab
        #
        # When detected: try compose_witness_response(... lang="en") on
        # the stashed witness detection. If that produces non-empty
        # text, replace final_text. If detection is absent OR fallback
        # is empty, log a CRITICAL warning so the operator sees the
        # leak in api.log — last-resort string strip is unsafe (can
        # produce broken English).
        if _session_lang_mode == "english" and final_text:
            _es_tokens_seen: List[str] = []
            if "¿" in final_text or "¡" in final_text:
                _es_tokens_seen.append("spanish_punct")
            _ft_lower = final_text.lower()
            for _scaffold in (
                "capté", "capte ", "¿qué pasó", "qué pasó después",
                "pasó después", " tú ",
            ):
                if _scaffold in _ft_lower:
                    _es_tokens_seen.append(f"scaffold:{_scaffold.strip()}")
                    break
            # Mid-prose Spanish "y" — only count if surrounded by English
            # words (avoids false-positive on product names like
            # "Y Combinator"). Pattern: lowercase-letter-word + ", y " +
            # lowercase-letter-word — Spanglish glue.
            import re as _re_es
            if _re_es.search(r"[a-z]\s*,\s+y\s+[a-z]", _ft_lower):
                _es_tokens_seen.append("scaffold:comma_y")

            if _es_tokens_seen:
                _es_repair_text = ""
                if _witness_detection_for_fallback is not None:
                    try:
                        from ..services.lori_witness_mode import (
                            compose_witness_response as _compose_en_repair,
                        )
                        _es_repair_text = _compose_en_repair(
                            _witness_detection_for_fallback,
                            target_language="en",
                        )
                    except Exception as _es_repair_exc:
                        logger.warning(
                            "[chat_ws][lang-contract][es-repair] "
                            "compose_witness_response raised conv=%s: %s",
                            conv_id, _es_repair_exc,
                        )
                if _es_repair_text:
                    logger.warning(
                        "[chat_ws][lang-contract][es-repair] english-mode "
                        "Spanish leak repaired conv=%s tokens=%s "
                        "before=%r after=%r",
                        conv_id,
                        ",".join(_es_tokens_seen),
                        (final_text or "")[:160],
                        _es_repair_text[:160],
                    )
                    final_text = _es_repair_text
                else:
                    logger.error(
                        "[chat_ws][lang-contract][es-repair] CRITICAL: "
                        "english-mode Spanish leak detected but no "
                        "deterministic English fallback available — "
                        "operator review needed conv=%s tokens=%s "
                        "text=%r",
                        conv_id,
                        ",".join(_es_tokens_seen),
                        (final_text or "")[:200],
                    )

        # ── BUG-LORI-LANGUAGE-DRIFT-UNPROMPTED-01 + DANGLING-DETERMINER-01 ──
        # Post-LLM response guards (services/lori_response_guards.py).
        # Runs AFTER comm_control / reflection-shaper finalize final_text,
        # BEFORE persist + WS done event so the repaired text reaches the
        # bubble, the TTS pipeline, the transcript, and the archive.
        #
        # Two guards in priority order:
        #   1. language_drift — if last 3 narrator turns are English AND
        #      current narrator turn has no Spanish signal AND Lori output
        #      is Spanish, replace with English deterministic continuation.
        #      Kent's K1/K2/K10 evidence (2026-05-09 replay).
        #   2. dangling_determiner — Lori output ending with the/a/an/to/
        #      of/with/about/for + period → replace with safe continuation.
        #      Mary line 47 + Kent line 47 evidence.
        #
        # Both guards are pure-stdlib + idempotent + safe-by-default. When
        # the response looks fine, original text passes through unchanged.
        #
        # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 §3.1: resolve
        # the repair-target language pin BEFORE the guarded try, so the
        # fail-closed fallback in the except handler below honors
        # _session_lang_mode even when the wrapper crashes before the
        # per-turn looks_spanish heuristics ran.
        _guard_target_lang = "es" if _session_lang_mode == "spanish" else "en"
        try:
            _apply_guards = _APPLY_RESPONSE_GUARDS   # imported at module scope
            #   (see BUG-GUARDS-DEAD-ON-PY311-INLINE-FLAG-01 above) so a broken
            #   guards module fails the BOOT, not silently every narrator turn.
            # Pull the last few narrator turns from the conv history to
            # build the recent-context check. db.get_turns() returns
            # ordered turns; we pull the last 6 (3 narrator + 3 lori
            # interleaved) and filter to narrator-only.
            _recent_narr: List[str] = []
            try:
                from ..db import export_turns as _export_turns
                _hist = _export_turns(conv_id) or []
                for t in _hist:
                    if isinstance(t, dict) and t.get("role") == "user":
                        _ut = t.get("content") or ""
                        # Phase 3, same reasoning as the pilot above.
                        if _ut and not _turn_is_system_directive(t):
                            _recent_narr.append(_ut)
                _recent_narr = _recent_narr[-3:]
            except Exception:
                _recent_narr = []
            # WO-SPANISH-LIVE-READINESS-01 Patch 5 (2026-06-17): detect
            # narrator language for the guard pipeline. The hardcoded
            # "en" here meant Spanish narrators who hit a guard repair
            # (meta_response_leak / broken_code_mix / dangling_determiner)
            # got the English fallback prompt ("Tell me more about
            # that.") instead of the Spanish one ("Cuéntame más sobre
            # eso."). Use looks_spanish() on the narrator's current
            # turn, with the recent-turns context as a smoothing signal
            # for the case where a Spanish session sends a short EN
            # token like "yes".
            # (_guard_target_lang initialized pin-aware ABOVE the try —
            # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 §3.1.)
            # BUG-LORI-SPANISH-DRIFT-WALT-ERA-7 instrumentation
            # (2026-06-24): explain exactly which signal flipped the
            # guard target to "es" so the Era 7 Walt drift becomes
            # empirically traceable. Records whether the current
            # turn or one of the recent narrator turns tripped
            # looks_spanish.
            _gt_user_es = False
            _gt_prior_es_index = -1
            try:
                from ..services.lori_spanish_guard import looks_spanish as _gt_looks_es
                if user_text and _gt_looks_es(user_text):
                    _guard_target_lang = "es"
                    _gt_user_es = True
                elif _recent_narr:
                    # Smooth over short non-Spanish replies in an
                    # otherwise-Spanish session: if ANY of the last 3
                    # narrator turns looks Spanish, treat session as ES.
                    for _gt_i, _prior in enumerate(_recent_narr):
                        if _prior and _gt_looks_es(_prior):
                            _guard_target_lang = "es"
                            _gt_prior_es_index = _gt_i
                            break
            except Exception:
                _guard_target_lang = "en"
            # BUG-ML-SPANISH-DETECT-FRENCH-PLACE-OVERFIRE-01 hardening
            # (2026-07-02): the session-language profile pin must also
            # govern the response-guard repair target. Live 2019
            # France/Italy T3/T4 evidence: one looks_spanish false
            # positive on a narrator turn ("Palais de Chaillot...")
            # poisoned the 3-turn smoothing window and the T4 English
            # reply was replaced with the SPANISH drift repair
            # ("Disculpa, continuemos") — narrator-visible Spanish in
            # an English session. The witness/meta/memory-echo paths
            # already consult the pin; this block previously did not.
            # mixed/unset keeps the per-turn heuristic above.
            if _session_lang_mode == "english":
                _guard_target_lang = "en"
            elif _session_lang_mode == "spanish":
                _guard_target_lang = "es"
            logger.info(
                "[chat_ws][lang-debug] conv=%s guard_target=%s "
                "user_es=%s prior_es_index=%d recent_count=%d "
                "lang_mode=%s user_text_first120=%r",
                conv_id,
                _guard_target_lang,
                _gt_user_es,
                _gt_prior_es_index,
                len(_recent_narr),
                _session_lang_mode,
                (user_text or "")[:120],
            )
            # WO-LORI-FACTUAL-CHAIN-CAPTURE-01 / English-first
            # iteration 2 (2026-06-24): the drift-repair guard is
            # ACTIVE on every surface (the earlier trip-skip exposed
            # the underlying Spanish-pattern-completion bug). The
            # ENGLISH_FIRST_RULE prompt directive prevents most drift
            # at generation time; this guard remains as a safety net.
            # When it fires, the repair uses the narrator's detected
            # chain anchors so the continuation is substantive English
            # rather than the destructive "Sorry — let's continue"
            # boilerplate.
            _surface = (params.get("surface") or "narrator").strip().lower()
            if _surface not in ("narrator", "trip"):
                _surface = "narrator"
            _narrator_anchors_for_guard: List[str] = []
            try:
                if isinstance(_chain_ctx, dict):
                    _na = _chain_ctx.get("anchors") or []
                    if isinstance(_na, list):
                        _narrator_anchors_for_guard = [
                            str(a) for a in _na if a
                        ]
            except Exception:
                _narrator_anchors_for_guard = []
            # BUG-LORI-FACTUAL-OVER-SENSORY-PROBE-01 (2026-07-02):
            # thread the chain classification so the deterministic
            # sensory-pivot repair can fire on chain turns.
            _is_chain_for_guard = False
            try:
                if isinstance(_chain_ctx, dict):
                    _is_chain_for_guard = bool(
                        _chain_ctx.get("is_factual_chain")
                    )
            except Exception:
                _is_chain_for_guard = False
            # BUG-LORI-ASKS-WHAT-OPERATOR-SEEDED-01 wiring fix
            # (2026-07-06): detect_seeded_fact_intake was DEAD in
            # production — no caller ever passed seeded_facts, so Lori
            # could still ask intake questions for operator-seeded
            # facts. The guard expects place_of_birth /
            # current_residence / current_work keys; profile_seed
            # carries POB as childhood_home and work as career, so map
            # explicitly (passing profile_seed raw would silently
            # no-op on key mismatch).
            _seeded_facts_for_guard: Dict[str, Any] = {}
            try:
                if isinstance(_early_profile_seed, dict):
                    if _early_profile_seed.get("childhood_home"):
                        _seeded_facts_for_guard["place_of_birth"] = (
                            _early_profile_seed["childhood_home"]
                        )
                    if _early_profile_seed.get("career"):
                        _seeded_facts_for_guard["current_work"] = (
                            _early_profile_seed["career"]
                        )
            except Exception:
                _seeded_facts_for_guard = {}
            _guarded_text, _guards_fired = _apply_guards(
                assistant_text=final_text,
                narrator_text=user_text or "",
                recent_narrator_turns=_recent_narr,
                target_language=_guard_target_lang,
                surface=_surface,
                narrator_anchors=_narrator_anchors_for_guard,
                is_factual_chain=_is_chain_for_guard,
                seeded_facts=_seeded_facts_for_guard or None,
            )
            if _guards_fired:
                logger.warning(
                    "[chat_ws][response-guards] fired=%s conv=%s "
                    "before=%r after=%r",
                    ",".join(_guards_fired),
                    conv_id,
                    final_text[:120],
                    _guarded_text[:120],
                )
                final_text = _guarded_text
        except Exception as _guard_exc:
            # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 §3.1 —
            # FAIL CLOSED. The old handler logged a WARNING and "passed
            # through" — which meant a crash in the guard LAYER shipped
            # the raw, UNGUARDED LLM text (echo, meta-leak, Spanglish,
            # seeded-fact intake, sensory pivot — all unchecked) straight
            # to the narrator. That inverts the whole point of the layer.
            # BUG-GUARDS-DEAD-ON-PY311-INLINE-FLAG-01 proved this exact
            # class fires in production. Never send unguarded LLM text:
            # substitute the deterministic fallback (safety wording +
            # locked resource cards on a safety-triggered turn; the
            # locked neutral continuation otherwise), honoring the
            # session language pin resolved above the try.
            logger.error(
                "[chat_ws][response-guards] wrapper raised — FAIL CLOSED, "
                "unguarded LLM text suppressed conv=%s: %s",
                conv_id, _guard_exc, exc_info=True,
            )
            _guard_fail_resources = None
            if _is_safety_turn and _safety_result is not None:
                try:
                    _guard_fail_resources = get_resources_for_category(
                        _safety_result.category)
                except Exception as _res_exc:
                    logger.error(
                        "[chat_ws][response-guards] resource lookup also "
                        "raised conv=%s: %s — safety fallback proceeds "
                        "without resource lines", conv_id, _res_exc,
                    )
                    _guard_fail_resources = None
            final_text = _COMPOSE_GUARD_FAILURE_FALLBACK(
                target_language=_guard_target_lang,
                safety_triggered=_is_safety_turn,
                resources=_guard_fail_resources,
            )
            # Ensure the deterministic fallback actually reaches the
            # client bubble via the deferred single-delta emit.
            _deferred_emit_pending = True

        try:
            # WO-LIVE-TRIP-COMPANION-01 VS1 — the trip timeline renders a
            # conversation moment, which is both sides of it. It reads
            # the words back out of `turns` by row id and stores no
            # copy, so it needs the narrator's row as well as Lori's.
            # `row_ids_out` is populated only after COMMIT.
            _persisted_row_ids: Dict[str, Any] = {}
            _persisted_turn_row_id = persist_turn_transaction(
                conv_id=conv_id,
                user_message=user_text,
                assistant_message=final_text,
                model_name="local-llm-ws",
                # WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 R2.3 — the
                # narrator bound at the top of this turn, recorded on the
                # sessions row instead of being dropped.
                person_id=person_id,
                meta={"ws": True, "cancelled": ev.is_set()},
                row_ids_out=_persisted_row_ids,
                # WO-SYSTEM-DIRECTIVE-PERSISTENCE-01 Phase 1 (2026-08-09).
                is_system_directive=bool(params.get("_is_system_directive")),
            )
            # WO-TRUTH-PIPELINE-01 Phase 2 (Gate 7, 2026-07-30) — hand the
            # committed assistant rowid to the post-response extraction
            # hook in generate_and_stream(). `params` is the only object
            # shared between this body and that wrapper, and it is a plain
            # dict owned by this turn, so no new global or contextvar is
            # needed. The underscore prefix marks it as server-internal:
            # it is never echoed to the client and never persisted.
            #
            # The KEY is this row id, not the client's turn_id — a retrying
            # client may mint a fresh turn_id for the same saved turn, and
            # extraction must not run twice for one committed turn.
            try:
                params["_persisted_turn_row_id"] = _persisted_turn_row_id
                params["_persisted_user_turn_row_id"] = (
                    _persisted_row_ids.get("user_row_id"))
            except Exception:
                pass
        except Exception as persist_err:
            logger.error("[chat-ws] Phase G: persist_turn_transaction failed — %s", persist_err)
            await _ws_send(ws, {"type": "error", "message": "Turn persist failed — no state written"})

        # Memory Archive — log assistant reply + rebuild transcript.
        # Same surface gate as the user-turn write above
        # (BUG-MODAL-TURNS-ARCHIVED-AS-LIFE-STORY-01): a modal reply must not
        # land in the narrator's life story either, or the transcript rebuild
        # stitches Travel Doc workspace talk into the memoir source.
        # Recomputed, NOT inherited: the user-turn gate is ~3k lines up and an
        # early return path could leave it unbound. A NameError here would kill
        # the archive write for EVERY narrator, so derive it locally.
        _skip_modal_archive = (
            (params.get("surface") or "narrator").strip().lower()
            == "travel_doc_modal")
        if person_id and not _skip_modal_archive:
            try:
                archive_append_event(
                    person_id=person_id,
                    session_id=conv_id,
                    role="assistant",
                    content=final_text,
                    meta={"ws": True, "cancelled": ev.is_set()},
                    current_era=_current_era_for_archive,  # WO-LORI-MEMORY-ECHO-ERA-STORIES-01 Phase 1
                )
                archive_rebuild_txt(person_id=person_id, session_id=conv_id)
                # WO-TRUTH-PIPELINE-01 Phase 2 (Gate 7, 2026-07-30) — the
                # extraction hook may only fire once the REQUIRED archive
                # event has actually landed. Set inside the try, after the
                # append returns, so a raising archive write leaves this
                # False and extraction is skipped rather than run against a
                # turn whose archive is incomplete.
                try:
                    params["_archive_event_persisted"] = True
                except Exception:
                    pass
            except Exception as arch_err:
                logger.error("[chat-ws] Phase G: archive write failed — %s", arch_err)

        # ── WO-LORI-WITNESS-FOLLOWUP-BANK-01 — bank-write ──────────────
        # Persist banked doors AFTER the response is sent. Doors are
        # priority 4-6 (relationship / daily-life / medical-family) +
        # any priority 1-3 doors that didn't win the immediate slot.
        # Lori comes back to these later via bank-flush triggers.
        #
        # Best-effort: bank-write failure must not break the turn.
        # No-op if there are no doors to bank, OR if conv_id is empty
        # (defensive — should never happen but the DB write would
        # raise on empty session_id).
        if _doors_to_bank and conv_id:
            try:
                from ..db import followup_bank_add as _bank_add
                _turn_idx = _session_turn_count or 0
                _banked_count = 0
                for _door in _doors_to_bank:
                    try:
                        _bank_add(
                            session_id=conv_id,
                            intent=_door.intent,
                            question_en=_door.question_en,
                            triggering_anchor=_door.triggering_anchor,
                            why_it_matters=_door.why_it_matters,
                            priority=_door.priority,
                            triggering_turn_index=_turn_idx,
                            person_id=person_id,
                        )
                        _banked_count += 1
                    except Exception as _bank_one_exc:
                        logger.warning(
                            "[chat_ws][followup-bank] write failed door="
                            "%s conv=%s: %s",
                            _door.intent, conv_id, _bank_one_exc,
                        )
                if _banked_count:
                    logger.info(
                        "[chat_ws][followup-bank] persisted %d/%d doors "
                        "conv=%s person=%s turn=%d",
                        _banked_count, len(_doors_to_bank),
                        conv_id, person_id or "(none)", _turn_idx,
                    )
            except Exception as _bank_outer_exc:
                logger.warning(
                    "[chat_ws][followup-bank] outer wrapper raised "
                    "conv=%s: %s",
                    conv_id, _bank_outer_exc,
                )

        # BANK_PRIORITY_REBUILD 2026-05-10 — deferred token emit for
        # witness-receipt mode. The pre-validator emit at L2345 was
        # skipped (see comment there). Now that the validator + Spanish-
        # repair + response-guards have all run, final_text is the
        # validated/repaired text. Emit it as a single delta so the
        # client UI gets the same token+done shape it expects, and
        # Kent's chat-bubble fills with ONLY the validated text.
        if (_witness_use_llm_receipt or _deferred_emit_pending) and final_text:
            try:
                await _ws_send(ws, {"type": "token", "delta": final_text})
                logger.info(
                    "[chat_ws][%s][buffered-stream] conv=%s — "
                    "deferred token emitted post-guards words=%d",
                    "witness" if _witness_use_llm_receipt else "guards",
                    conv_id, len(final_text.split()),
                )
            except Exception as _emit_exc:
                logger.warning(
                    "[chat_ws][witness][buffered-stream] deferred emit "
                    "raised conv=%s: %s — done event still fires",
                    conv_id, _emit_exc,
                )

        # WO-TRIP-LORI-ANSWER-CAPTURE-01 — remember THIS Lori turn's final text
        # so the NEXT narrator answer's candidate note can be titled with the
        # question that was asked. Bounded + best-effort; the capture service
        # re-clips it. Only meaningful on trip turns (dict present only then).
        try:
            _tpl_mem = _TRIP_PREV_LORI.get(conv_id)
            if _tpl_mem is not None and final_text:
                _tpl_mem["lori_text"] = final_text[:300]
        except Exception:
            pass

        await _ws_send(ws, {"type": "done", "final_text": final_text, "turn_mode": turn_mode})

    try:
        while True:
            msg = await ws.receive_json()
            msg_type = msg.get("type")

            if msg_type == "sync_session":
                # WO-2: Identity-session handshake
                incoming_pid = str(msg.get("person_id") or "")
                if incoming_pid and incoming_pid != active_person_id:
                    # Person changed — flush conversation history
                    if active_person_id:
                        old_conv = msg.get("old_conv_id") or f"person_{active_person_id}"
                        cleared = clear_turns(old_conv)
                        logger.info("[WO-2] Session switch: %s → %s, flushed %d turns from %s",
                                    active_person_id, incoming_pid, cleared, old_conv)
                    active_person_id = incoming_pid
                else:
                    active_person_id = incoming_pid or active_person_id
                await _ws_send(ws, {
                    "type": "session_verified",
                    "person_id": active_person_id,
                    # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01
                    # §3.3 — surface the per-socket fallback conv id so
                    # an ID-less client can adopt and re-supply it.
                    "socket_conv_id": socket_conv_id,
                })

            elif msg_type == "start_turn":
                # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 §3.3 —
                # NEVER the literal "default" for a WS narrator turn.
                # Clients that supply session_id/conv_id keep it verbatim;
                # an ID-less client gets this socket's own minted id, so
                # two ID-less sockets can never share history, softened
                # state, segment flags, or follow-up-bank rows.
                conv_id = msg.get("session_id") or msg.get("conv_id") or ""
                if not conv_id:
                    conv_id = socket_conv_id
                    logger.warning(
                        "[chat_ws][session-identity] start_turn arrived "
                        "without session_id/conv_id — assigned per-socket "
                        "conv_id=%s (shared-'default' sessions are "
                        "retired)", conv_id,
                    )
                user_text = msg.get("message") or ""
                params = msg.get("params") or {}
                # WO-ARCH-07A — explicit turn mode from client router
                params["turn_mode"] = (msg.get("turn_mode") or "interview").strip() or "interview"

                # WO-2: check person_id in params matches active session
                turn_pid = str(params.get("person_id") or "")
                if turn_pid and active_person_id and turn_pid != active_person_id:
                    cleared = clear_turns(conv_id)
                    logger.info("[WO-2] Turn person_id mismatch: active=%s, turn=%s, flushed %d turns",
                                active_person_id, turn_pid, cleared)
                    active_person_id = turn_pid

                # §3.2 — cancel any in-flight turn on this socket:
                # permanently set the PREVIOUS turn's event (never
                # cleared again — an old generation must never observe a
                # newly cleared event), cancel its task, then mint a
                # FRESH event owned by exactly this new generation.
                if current_cancel_event is not None:
                    current_cancel_event.set()
                if current_task and not current_task.done():
                    current_task.cancel()

                current_cancel_event = threading.Event()
                current_task = asyncio.create_task(
                    generate_and_stream(
                        conv_id, user_text, params, current_cancel_event))

            elif msg_type == "cancel_turn":
                # §3.2 — set the ACTIVE turn's own event; the generation
                # loop observes it, stops streaming, and emits the
                # cancelled done (fail-closed persistence skip). Never
                # cleared afterward.
                if current_cancel_event is not None:
                    current_cancel_event.set()
                await _ws_send(ws, {"type": "status", "state": "cancelled"})

            elif msg_type == "ping":
                await _ws_send(ws, {"type": "pong"})

            else:
                await _ws_send(ws, {"type": "error", "message": f"unknown type: {msg_type}"})

    except WebSocketDisconnect:
        # Phase G: fail-closed — cancel in-flight generation, do not replay stale state
        # §3.2 — target the ACTIVE turn's own event (set, never cleared).
        if current_cancel_event is not None:
            current_cancel_event.set()
        if current_task and not current_task.done():
            current_task.cancel()
        logger.info("[chat-ws] Phase G: WebSocket disconnected — cancelled in-flight, no stale replay")
        return
