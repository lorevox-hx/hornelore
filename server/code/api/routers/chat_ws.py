from __future__ import annotations

import asyncio
import gc
import json
import logging
import os
import threading
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

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from transformers import TextIteratorStreamer, StoppingCriteriaList

from ..db import (
    export_turns,
    persist_turn_transaction,
    clear_turns,
    save_segment_flag,
    increment_session_turn,
    set_session_softened,
    ensure_interview_session,  # BUG-DBLOCK-01 PATCH 3
    get_session_softened_state,  # WO-LORI-SOFTENED-RESPONSE-01
)
import torch
from ..api import _load_model, _apply_chat_template, StopOnEvent, _normalize_role, MAX_CONTEXT_WINDOW
from ..prompt_composer import compose_system_prompt
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
)

router = APIRouter(prefix="/api/chat", tags=["chat-ws"])


async def _ws_send(ws: WebSocket, obj: Dict[str, Any]) -> None:
    try:
        await ws.send_text(json.dumps(obj, ensure_ascii=False))
    except Exception:
        pass


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


@router.websocket("/ws")
async def ws_chat(ws: WebSocket):
    await ws.accept()
    await _ws_send(ws, {"type": "status", "state": "connected"})

    ev = threading.Event()
    current_task: Optional[asyncio.Task] = None
    # WO-2: track active person_id for identity-session handshake
    active_person_id: Optional[str] = None

    async def generate_and_stream(conv_id: str, user_text: str, params: Dict[str, Any]) -> None:
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
        _ut_lstrip = (user_text or "").lstrip()
        _is_system_directive = _ut_lstrip.startswith("[SYSTEM")

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
                    _trigger_diag = _story_trigger.trigger_diagnostic(
                        audio_duration_sec=None,
                        transcript=user_text,
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
                        try:
                            _candidate_id = _story_preservation.preserve_turn(
                                narrator_id=person_id,
                                transcript=user_text,
                                trigger_reason=_trigger_reason,
                                scene_anchor_count=int(
                                    _trigger_diag.get("anchor_count") or 0
                                ),
                                conversation_id=conv_id,
                                turn_id=_turn_id,
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

        # Memory Archive — ensure session exists and log user message
        if person_id:
            archive_ensure_session(
                person_id=person_id,
                session_id=conv_id,
                mode="chat_ws",
                title="Chat (WS)",
                extra_meta={"ws": True},
            )
            archive_append_event(
                person_id=person_id,
                session_id=conv_id,
                role="user",
                content=user_text,
                meta={"ws": True},
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
        # Defensive init for _safety_result here too — without it, a turn
        # with empty user_text would skip the scan_answer block entirely
        # and leave _safety_result unbound, raising NameError when the
        # wrapper later calls `bool(_safety_result and ...)`. Pre-existing
        # latent bug surfaced during this WO's code review; init here
        # fixes it for both the new softened path and the legacy path.
        _safety_result = None  # type: ignore[assignment]
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
        _softened_response_enabled = os.environ.get(
            "HORNELORE_SOFTENED_RESPONSE", "0"
        ).strip().lower() in ("1", "true", "yes", "on")
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
        # turn. Never logs narrator content; just flag + remaining turns.
        if _softened_state.get("interview_softened"):
            try:
                from ..services.lori_softened_response import turns_remaining as _trem
                _remaining = _trem(_softened_state)
            except Exception:
                _remaining = 0
            logger.info(
                "[chat_ws][softened] active conv=%s turns_remaining=%d turn_count=%d until=%d",
                conv_id, _remaining,
                _softened_state.get("turn_count", 0),
                _softened_state.get("softened_until_turn", 0),
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
        if user_text and user_text.strip():
            _safety_scan_failed = False
            try:
                _safety_result = scan_answer(user_text)
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
                # path failed with FOREIGN KEY constraint failed, leaking the
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
                    set_softened(conv_id, _session_turn_count)
                    set_session_softened(conv_id, _session_turn_count)
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

        if turn_mode == "memory_echo":
            from ..prompt_composer import compose_memory_echo, _build_profile_seed

            # WO-LORI-SESSION-AWARENESS-01 Phase 1b: server-side profile_seed
            # data wiring. UI may already populate runtime71["profile_seed"]
            # via buildRuntime71 (preferred — sees Bio Builder questionnaire
            # + projection state in real time). Server fills the gap when
            # UI didn't (or sent only a subset). Server source: profile_json
            # blob in profiles DB, hydrated from templates at preload time.
            ui_seed = runtime71.get("profile_seed") if isinstance(runtime71.get("profile_seed"), dict) else {}
            server_seed = _build_profile_seed(person_id) if person_id else {}
            # UI takes precedence per-bucket (real-time signal), server fills
            # only the buckets UI didn't populate.
            merged_seed = dict(server_seed)
            merged_seed.update({k: v for k, v in (ui_seed or {}).items() if v})
            if merged_seed:
                runtime71 = dict(runtime71)
                runtime71["profile_seed"] = merged_seed
                logger.info(
                    "[chat_ws][memory-echo] profile_seed sources: ui=%d server=%d merged=%d conv=%s person=%s",
                    len([k for k, v in (ui_seed or {}).items() if v]),
                    len(server_seed),
                    len(merged_seed),
                    conv_id,
                    person_id or "(none)",
                )

            assistant_text = compose_memory_echo(
                text=user_text,
                runtime=runtime71,
            )
            logger.info("[chat_ws][WO-ARCH-07A] memory_echo turn for conv=%s", conv_id)
            persist_turn_transaction(
                conv_id=conv_id,
                user_message=user_text,
                assistant_message=assistant_text,
                model_name="memory-echo",
                meta={"ws": True, "turn_mode": "memory_echo"},
            )
            await _ws_send(ws, {"type": "token", "delta": assistant_text})
            await _ws_send(ws, {"type": "done", "final_text": assistant_text, "turn_mode": "memory_echo"})
            return
        if turn_mode == "correction":
            from ..prompt_composer import compose_correction_ack
            from ..memory_echo import parse_correction_rule_based
            parsed = parse_correction_rule_based(user_text)
            logger.info("[chat_ws][WO-ARCH-07A] correction turn for conv=%s parsed=%s", conv_id, parsed)

            # WO-ARCH-07A PS2 — emit structured correction payload for client write-back
            await _ws_send(ws, {
                "type": "correction_payload",
                "parsed": parsed,
                "source_text": user_text,
                "turn_mode": "correction",
            })

            assistant_text = compose_correction_ack(
                text=user_text,
                runtime=runtime71,
            )
            persist_turn_transaction(
                conv_id=conv_id,
                user_message=user_text,
                assistant_message=assistant_text,
                model_name="correction-ack",
                meta={"ws": True, "turn_mode": "correction", "parsed_corrections": parsed},
            )
            await _ws_send(ws, {"type": "token", "delta": assistant_text})
            await _ws_send(ws, {"type": "done", "final_text": assistant_text, "turn_mode": "correction"})
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
        try:
            if _softened_state and _softened_state.get("interview_softened"):
                runtime71 = dict(runtime71) if isinstance(runtime71, dict) else {}
                runtime71["softened_state"] = dict(_softened_state)
        except Exception as _rt_exc:
            logger.warning(
                "[chat_ws][softened] runtime71 thread failed conv=%s: %s",
                conv_id, _rt_exc,
            )

        system_prompt = compose_system_prompt(conv_id, ui_system=None, user_text=user_text, runtime71=runtime71)

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
        _planned_seq = min(_prompt_tokens, MAX_CONTEXT_WINDOW) + max_new
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
        if inputs["input_ids"].shape[-1] > MAX_CONTEXT_WINDOW:
            logger.warning("[VRAM-GUARD] WS truncating input from %d to %d tokens",
                           inputs["input_ids"].shape[-1], MAX_CONTEXT_WINDOW)
            inputs = {k: v[:, -MAX_CONTEXT_WINDOW:] for k, v in inputs.items()}
        streamer = TextIteratorStreamer(tok, skip_prompt=True, skip_special_tokens=True)

        ev.clear()
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
        try:
            from ..prompt_composer import _discipline_filter_enabled
            _buffer_mode = _discipline_filter_enabled()
        except Exception:
            _buffer_mode = False

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
                _cc_result = enforce_lori_communication_control(
                    assistant_text=final_text,
                    user_text=user_text or "",
                    safety_triggered=_safety_triggered_now,
                    session_style=str(_session_style),
                    softened_mode_active=_softened_now,
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
        try:
            from ..prompt_composer import _trim_to_one_question
            if _buffer_mode and final_text:
                _trimmed, _was_trimmed, _reason = _trim_to_one_question(final_text)
                if _was_trimmed:
                    logger.info(
                        "[lori][discipline] trim-to-one-q conv=%s reason=%s before_len=%d after_len=%d",
                        conv_id, _reason, len(final_text), len(_trimmed),
                    )
                    final_text = _trimmed
                # Buffer mode: emit the cleaned text as a single delta so
                # the client UI gets the same shape it expects (token + done).
                await _ws_send(ws, {"type": "token", "delta": final_text})
        except Exception as _disc_exc:
            # Filter is a safety net — never let it kill a turn. If trim
            # raised in buffer mode, send the untrimmed text so the narrator
            # still sees an answer.
            logger.warning("[lori][discipline] filter raised, passing through: %s", _disc_exc)
            if _buffer_mode and final_text:
                await _ws_send(ws, {"type": "token", "delta": final_text})

        # Phase G: fail-closed — only persist if generation completed cleanly
        if ev.is_set():
            logger.warning("[chat-ws] Turn cancelled/disconnected — skipping persistence (fail-closed)")
            await _ws_send(ws, {"type": "done", "final_text": final_text, "cancelled": True})
            return

        try:
            persist_turn_transaction(
                conv_id=conv_id,
                user_message=user_text,
                assistant_message=final_text,
                model_name="local-llm-ws",
                meta={"ws": True, "cancelled": ev.is_set()},
            )
        except Exception as persist_err:
            logger.error("[chat-ws] Phase G: persist_turn_transaction failed — %s", persist_err)
            await _ws_send(ws, {"type": "error", "message": "Turn persist failed — no state written"})

        # Memory Archive — log assistant reply + rebuild transcript
        if person_id:
            try:
                archive_append_event(
                    person_id=person_id,
                    session_id=conv_id,
                    role="assistant",
                    content=final_text,
                    meta={"ws": True, "cancelled": ev.is_set()},
                )
                archive_rebuild_txt(person_id=person_id, session_id=conv_id)
            except Exception as arch_err:
                logger.error("[chat-ws] Phase G: archive write failed — %s", arch_err)

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
                await _ws_send(ws, {"type": "session_verified", "person_id": active_person_id})

            elif msg_type == "start_turn":
                conv_id = msg.get("session_id") or msg.get("conv_id") or "default"
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

                # cancel any in-flight turn on this socket
                ev.set()
                if current_task and not current_task.done():
                    current_task.cancel()

                ev.clear()
                current_task = asyncio.create_task(generate_and_stream(conv_id, user_text, params))

            elif msg_type == "cancel_turn":
                ev.set()
                await _ws_send(ws, {"type": "status", "state": "cancelled"})

            elif msg_type == "ping":
                await _ws_send(ws, {"type": "pong"})

            else:
                await _ws_send(ws, {"type": "error", "message": f"unknown type: {msg_type}"})

    except WebSocketDisconnect:
        # Phase G: fail-closed — cancel in-flight generation, do not replay stale state
        ev.set()
        if current_task and not current_task.done():
            current_task.cancel()
        logger.info("[chat-ws] Phase G: WebSocket disconnected — cancelled in-flight, no stale replay")
        return
