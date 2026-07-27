"""Thin ``requests`` wrapper over the Google Photos Picker API.

WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01 Phase 1 -- SESSIONS ONLY.

The verified surface (Google's live docs, 2026-07-27):

    POST   https://photospicker.googleapis.com/v1/sessions
    GET    https://photospicker.googleapis.com/v1/sessions/{sessionId}
    DELETE https://photospicker.googleapis.com/v1/sessions/{sessionId}
    GET    https://photospicker.googleapis.com/v1/mediaItems?sessionId=...

``mediaItems`` is deliberately NOT implemented here. Phase 1 does not
download bytes and does not create candidates, and a listing function
sitting unused would be an invitation to reach past the phase wall. It
lands in Phase 2 alongside the fetch that gives it a purpose.

Shapes this returns, verbatim from the API:

    PickingSession { id, pickerUri, mediaItemsSet, pollingConfig {
                     pollInterval, timeoutIn } }

Two facts about that response that shape everything downstream, recorded
here because they are easy to assume away:

  * There is NO location/GPS field anywhere in the Picker response --
    not on the session, not on a picked item, not in its metadata. A
    picked photo's coordinates can only come from EXIF in the bytes.
  * There is NO byte-size field either. Size comes from stat() on the
    downloaded file.

Neither of those matters in Phase 1. Both are why Phase 2 must download.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from urllib.parse import quote

import requests

logger = logging.getLogger("code.services.google_picker.picker_client")

PICKER_BASE = "https://photospicker.googleapis.com/v1"

_TIMEOUT = (10, 30)   # (connect, read)


class PickerApiError(RuntimeError):
    """Google answered a Picker call with something other than success.

    ``status`` is the upstream HTTP status (0 for a transport failure) and
    ``reason`` is a short string the router maps to its own status code.
    """

    def __init__(self, message: str, status: int = 0,
                 reason: str = "upstream_error") -> None:
        super().__init__(message)
        self.status = status
        self.reason = reason


def _auth_headers(access_token: str) -> Dict[str, str]:
    return {"Authorization": "Bearer %s" % access_token,
            "Accept": "application/json"}


def _describe_error(resp: "requests.Response") -> str:
    """Google's JSON error envelope, without echoing the raw body.

    The request carried a bearer token in a header; a raw-body echo is a
    place that could resurface in a log. Only the structured
    ``error.status`` / ``error.message`` fields are surfaced.
    """
    try:
        payload = resp.json()
    except ValueError:
        return "Picker API returned HTTP %d (body withheld)." % resp.status_code
    err = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(err, dict):
        return "Picker API returned HTTP %d (body withheld)." % resp.status_code
    parts = [p for p in (err.get("status"), err.get("message"))
             if isinstance(p, str) and p]
    if not parts:
        return "Picker API returned HTTP %d (body withheld)." % resp.status_code
    return "Picker API returned HTTP %d: %s" % (resp.status_code,
                                                " -- ".join(parts))


def _reason_for(status: int) -> str:
    if status in (401, 403):
        return "upstream_forbidden"
    if status == 404:
        return "session_not_found"
    if status == 429:
        return "upstream_rate_limited"
    return "upstream_error"


def _call(method: str, url: str, access_token: str,
          json_body: Optional[Dict[str, Any]] = None,
          expect_json: bool = True) -> Dict[str, Any]:
    try:
        resp = requests.request(
            method, url,
            headers=_auth_headers(access_token),
            json=json_body,
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PickerApiError(
            "could not reach the Picker API: %s" % exc,
            status=0, reason="network",
        ) from None

    if resp.status_code >= 400:
        raise PickerApiError(_describe_error(resp),
                             status=resp.status_code,
                             reason=_reason_for(resp.status_code))

    if not expect_json:
        return {}
    if not (resp.content or b"").strip():
        return {}
    try:
        payload = resp.json()
    except ValueError:
        raise PickerApiError(
            "Picker API returned HTTP %d with a non-JSON body (body "
            "withheld)." % resp.status_code,
            status=resp.status_code, reason="upstream_error",
        ) from None
    if not isinstance(payload, dict):
        raise PickerApiError(
            "Picker API returned HTTP %d with an unexpected JSON shape."
            % resp.status_code,
            status=resp.status_code, reason="upstream_error",
        )
    return payload


def _normalize_session(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Google's camelCase session, flattened to the snake_case shape the
    router hands out. Unknown fields are dropped rather than passed
    through -- an API that grows a field should not silently start
    appearing in our responses."""
    polling = payload.get("pollingConfig")
    if not isinstance(polling, dict):
        polling = {}
    return {
        "session_id": payload.get("id"),
        "picker_uri": payload.get("pickerUri"),
        "media_items_set": bool(payload.get("mediaItemsSet")),
        "poll_interval": polling.get("pollInterval"),
        "timeout_in": polling.get("timeoutIn"),
        "expire_time": payload.get("expireTime"),
    }


def create_session(access_token: str) -> Dict[str, Any]:
    """POST /v1/sessions -- returns the normalized PickingSession.

    The body is empty on purpose: the Picker session takes no filters,
    and the operator chooses what to pick in Google's own UI.
    """
    payload = _call("POST", "%s/sessions" % PICKER_BASE, access_token,
                    json_body={})
    out = _normalize_session(payload)
    if not out["session_id"] or not out["picker_uri"]:
        raise PickerApiError(
            "Picker API created a session without an id or a pickerUri.",
            status=200, reason="upstream_error",
        )
    logger.info("google_picker: created picker session")
    return out


def get_session(access_token: str, session_id: str) -> Dict[str, Any]:
    """GET /v1/sessions/{sessionId} -- the poll."""
    url = "%s/sessions/%s" % (PICKER_BASE, quote(session_id, safe=""))
    return _normalize_session(_call("GET", url, access_token))


def delete_session(access_token: str, session_id: str) -> None:
    """DELETE /v1/sessions/{sessionId}.

    This ends the picking session at Google. It does NOT delete the
    ``import_batch`` -- there is no DELETE on the evidence lane, and a
    batch that was opened stays openable, closeable and hideable.
    """
    url = "%s/sessions/%s" % (PICKER_BASE, quote(session_id, safe=""))
    _call("DELETE", url, access_token, expect_json=False)
    logger.info("google_picker: deleted picker session")
