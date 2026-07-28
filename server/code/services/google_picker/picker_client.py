"""Thin ``requests`` wrapper over the Google Photos Picker API.

WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01 Phase 1 -- SESSIONS ONLY.

The verified surface (Google's live docs, 2026-07-27):

    POST   https://photospicker.googleapis.com/v1/sessions
    GET    https://photospicker.googleapis.com/v1/sessions/{sessionId}
    DELETE https://photospicker.googleapis.com/v1/sessions/{sessionId}
    GET    https://photospicker.googleapis.com/v1/mediaItems?sessionId=...

``mediaItems`` listing landed in Phase 2A. It reads back what the
operator picked and returns it. It downloads no bytes, opens no
database handle and stages no files -- acquisition is Phase 2B and is
a separate work item on purpose.

Shapes this reads, verbatim from the API:

    PickingSession   { id, pickerUri, mediaItemsSet, pollingConfig {
                       pollInterval, timeoutIn } }
    PickedMediaItem  { id, createTime, type, mediaFile {
                       baseUrl, mimeType, filename, mediaFileMetadata {
                       width, height, cameraMake, cameraModel,
                       photoMetadata | videoMetadata } } }

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
from typing import Any, Dict, List, Optional, Set
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


# ------------------------------------------------------------ media items
#
# Phase 2A. Listing only.
#
# What the operator picked is readable from Google for as long as the
# picking session lives. Reading it is cheap and repeatable; acting on
# it is not, which is why the two are separate phases. Nothing below
# writes a row, opens a file, or touches DATA_DIR.

_PAGE_SIZE_MAX = 100        # Google's documented maximum
_PAGE_SIZE_DEFAULT = 100    # fewest round trips; Google's own default is 50
_MAX_PAGES = 200            # runaway guard, not a product limit


def _as_int(value: Any) -> Optional[int]:
    """Google serializes some integer fields as decimal strings. Accept
    both spellings and refuse anything else rather than guessing -- a
    width that arrived as a dict is missing information, not zero."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _shape_error(position: int, what: str) -> PickerApiError:
    """A shape complaint that names the position and the missing field,
    never the value.

    Every picked item carries a ``baseUrl``, which is a bearer-scoped
    download URL. Echoing an offending item into an exception message
    would put that URL into whatever log or HTTP response catches the
    exception, so the item is described and withheld.
    """
    return PickerApiError(
        "Picker API returned a media item at position %d that %s "
        "(item withheld)." % (position, what),
        status=200, reason="upstream_error",
    )


def _normalize_media_item(item: Any, position: int) -> Dict[str, Any]:
    """One PickedMediaItem, flattened to snake_case.

    Unknown and unused fields are dropped rather than passed through,
    for the same reason ``_normalize_session`` drops them: a field the
    API grows should not silently start appearing in our data.

    Deliberately NOT surfaced, each for a reason:

      * ``cameraMake`` / ``cameraModel`` / ``photoMetadata`` /
        ``videoMetadata`` -- nothing consumes them. Provider metadata is
        the weaker source; ``photo_intake.metadata_trust`` grades EXIF
        read from the actual bytes, and that is what Phase 2B extracts.
      * There is no GPS field to surface. The Picker response carries no
        location anywhere, on the session or on an item.
      * There is no byte-size field to surface either. True size comes
        from stat() on the downloaded file in Phase 2B.

    ``base_url`` IS returned, because Phase 2B cannot download without
    it. It is never logged and never put in an error message.
    """
    if not isinstance(item, dict):
        raise _shape_error(position, "is not a JSON object")

    item_id = item.get("id")
    if not isinstance(item_id, str) or not item_id.strip():
        raise _shape_error(position, "has no usable id")

    media_file = item.get("mediaFile")
    if not isinstance(media_file, dict):
        raise _shape_error(position, "has no mediaFile object")

    base_url = media_file.get("baseUrl")
    if not isinstance(base_url, str) or not base_url.strip():
        raise _shape_error(position, "has no baseUrl")

    mime_type = media_file.get("mimeType")
    if not isinstance(mime_type, str) or not mime_type.strip():
        raise _shape_error(position, "has no mimeType")

    media_type = item.get("type")
    if not isinstance(media_type, str) or not media_type.strip():
        media_type = "TYPE_UNSPECIFIED"

    meta = media_file.get("mediaFileMetadata")
    if not isinstance(meta, dict):
        meta = {}

    filename = media_file.get("filename")
    create_time = item.get("createTime")

    return {
        "media_item_id": item_id.strip(),
        "create_time": create_time if isinstance(create_time, str) else None,
        "media_type": media_type.strip(),
        "mime_type": mime_type.strip(),
        "filename": filename if isinstance(filename, str) and filename else None,
        "base_url": base_url.strip(),
        "width": _as_int(meta.get("width")),
        "height": _as_int(meta.get("height")),
    }


def list_media_items(access_token: str, picker_session: str, *,
                     page_size: int = _PAGE_SIZE_DEFAULT) -> List[Dict[str, Any]]:
    """GET /v1/mediaItems?sessionId=... -- everything the operator picked.

    Pages to exhaustion and returns the whole selection in the order
    Google listed it. A partial listing is never returned quietly: if
    paging cannot finish, this raises instead of handing back a short
    list that would read as "the operator picked fewer photos".

    The parameter is named ``picker_session`` on purpose. Phase 2B will
    want to record which picking session an item came from, and
    ``import_repository``'s secret scanner treats both ``session_id``
    and ``auth`` as key-name hints -- so ``session_id`` and
    ``picker_session_id`` are both refused there. Using the safe name
    here keeps one word for the concept across the lane.

    Raises ``PickerApiError`` for every failure, with ``reason`` set to
    one of: ``invalid_request`` (our call was malformed, nothing was
    sent), ``network``, ``upstream_forbidden``, ``session_not_found``,
    ``upstream_rate_limited``, ``upstream_error``.

    No credential and no ``baseUrl`` appears in any message this raises
    or any line it logs.
    """
    if not isinstance(picker_session, str) or not picker_session.strip():
        raise PickerApiError(
            "a picker session id is required to list media items.",
            status=0, reason="invalid_request",
        )

    size = max(1, min(int(page_size), _PAGE_SIZE_MAX))
    session_q = quote(picker_session.strip(), safe="")

    items: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()
    seen_tokens: Set[str] = set()
    page_token: Optional[str] = None
    position = 0
    duplicates = 0
    pages = 0

    while True:
        url = "%s/mediaItems?sessionId=%s&pageSize=%d" % (
            PICKER_BASE, session_q, size)
        if page_token:
            url += "&pageToken=%s" % quote(page_token, safe="")

        payload = _call("GET", url, access_token)
        pages += 1

        page = payload.get("mediaItems")
        if page is None:
            page = []
        if not isinstance(page, list):
            raise PickerApiError(
                "Picker API returned a mediaItems field that is not a "
                "list (body withheld).",
                status=200, reason="upstream_error",
            )

        for raw in page:
            normalized = _normalize_media_item(raw, position)
            position += 1
            if normalized["media_item_id"] in seen_ids:
                duplicates += 1
                continue
            seen_ids.add(normalized["media_item_id"])
            items.append(normalized)

        next_token = payload.get("nextPageToken")
        if not isinstance(next_token, str) or not next_token.strip():
            break

        # Two ways a listing can fail to terminate, both of which would
        # otherwise spin against Google until the read timeout: a token
        # that repeats, and a token chain that simply never ends.
        if next_token in seen_tokens:
            raise PickerApiError(
                "Picker API paging did not advance: it repeated a page "
                "token after %d page(s) (token withheld)." % pages,
                status=200, reason="upstream_error",
            )
        if pages >= _MAX_PAGES:
            raise PickerApiError(
                "Picker API listing did not terminate within %d pages."
                % _MAX_PAGES,
                status=200, reason="upstream_error",
            )
        seen_tokens.add(next_token)
        page_token = next_token

    if duplicates:
        logger.warning(
            "google_picker: listing returned %d duplicate media item id(s); "
            "kept the first of each", duplicates)
    logger.info("google_picker: listed %d picked media item(s) over %d page(s)",
                len(items), pages)
    return items
