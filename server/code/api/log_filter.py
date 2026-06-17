"""Uvicorn access log noise filter — 2026-06-17.

The operator stack-dashboard widget polls a handful of endpoints
(test-lab status/system/log-tail, ui-heartbeat, ping, safety-events,
eval-harness summary, TTS voice list, the UI bundle itself) several
times per second. Each request writes one INFO line to the uvicorn
access log, which gets routed to .runtime/logs/api.log. The result is
that api.log becomes ~95% polling noise and the actual harness events
(chat_ws turns, story-trigger, VRAM-GUARD, comm_control, facts/add,
4xx/5xx) are buried.

This filter drops access-log records for those polling endpoints at
the logger level. The handlers still run, the dashboard still works,
we just don't write the access line. After installing this filter,
``tail .runtime/logs/api.log`` shows only signal.

Env opt-out: set ``HORNELORE_API_ACCESS_LOG_VERBOSE=1`` to disable the
filter and restore the noisy raw access log. Useful when you actually
want to see every request — e.g. debugging the polling endpoints
themselves.

The pattern mirrors the same noise list used by
``scripts/common.sh start_useful_log_tail`` so api.log and useful.log
agree on what counts as noise. If you add a new high-volume polling
endpoint, add it to both places.
"""
from __future__ import annotations

import logging
import os
import re

__all__ = ["AccessLogNoiseFilter", "install_access_log_noise_filter"]


# Endpoints that the operator stack-dashboard / test-lab widgets poll
# constantly. Each is reachable through normal user action too (Bug
# Panel, etc.) so the handlers stay live; we just stop writing the
# access line. Keep this in sync with the grep filter inside
# ``scripts/common.sh start_useful_log_tail``.
_NOISE_RX = re.compile(
    r"(?:"
    r"/api/test-lab/(?:status|system|log-tail|results)"
    r"|/api/operator/stack-dashboard/(?:ui-heartbeat|summary|history|system-status)"
    r"|/api/ping"
    r"|/api/operator/safety-events"
    r"|/api/operator/eval-harness/summary"
    r"|/api/tts/voices"
    r"|/ui/hornelore1\.0\.html"
    r")"
)


class AccessLogNoiseFilter(logging.Filter):
    """Drops uvicorn access-log records matching the noise pattern.

    Uvicorn formats access log records as e.g.
    ``127.0.0.1:38182 - "GET /api/ping HTTP/1.1" 200 OK`` — a single
    message string we can regex-match. Anything that DOES match the
    noise pattern is suppressed; everything else (real harness traffic,
    4xx/5xx, etc.) passes through unchanged.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        try:
            msg = record.getMessage()
        except Exception:
            return True  # if formatting fails, default to keeping the record
        return _NOISE_RX.search(msg) is None


def install_access_log_noise_filter() -> None:
    """Install the noise filter on the uvicorn access logger.

    Safe to call multiple times — idempotent via the ``_lv_noise``
    sentinel attribute. Skipped entirely when the operator sets
    ``HORNELORE_API_ACCESS_LOG_VERBOSE`` to a truthy value, restoring
    the raw access log.
    """
    if os.getenv("HORNELORE_API_ACCESS_LOG_VERBOSE", "0").strip().lower() in (
        "1", "true", "yes", "on",
    ):
        return
    access_logger = logging.getLogger("uvicorn.access")
    # Idempotency check — don't stack duplicate filters on uvicorn auto-reloads
    for f in getattr(access_logger, "filters", []) or []:
        if getattr(f, "_lv_noise", False):
            return
    nf = AccessLogNoiseFilter()
    nf._lv_noise = True  # type: ignore[attr-defined]
    access_logger.addFilter(nf)
