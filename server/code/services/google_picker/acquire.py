"""Byte acquisition for the Google Photos Picker lane -- Phase 2B.

WHAT THIS MODULE DOES

    max_bytes()              the streamed download cap, read from the env
    sniff_image()            magic-byte content inspection -> (mime, ext)
    download_original()      one picked item's original bytes -> a temp file
    read_evidence_metadata() EXIF date + GPS read off the bytes on disk
    staging_dir_for()        DATA_DIR/import_staging/<batch>/<candidate>/
    stage_original()         move the temp file into that directory

WHAT IT DELIBERATELY DOES NOT DO

It opens no database handle and creates no candidate. The required order
(spec 12.2) is: download to a temporary file, validate it, extract
metadata, call ``candidate_create()``, take the id it ACTUALLY returned
-- it is idempotent on ``(batch_id, external_id)`` and hands back the
existing row's id -- and only then move the bytes into that id's staging
directory. A module that could create the candidate itself would make
that order optional, and staging under a preallocated id orphans the
file on every re-ingest.

It also never calls ``candidate_decide()`` (spec 12.3). An item that
cannot be acquired produces no candidate row at all and is reported as
an ingest failure carrying ``retryable``. ``error`` is a terminal
operator judgement with no undecide; a network timeout is not one.

WHAT IT REFUSES TO TRUST

The provider's declared ``mimeType``, its ``filename``, and the claimed
``Content-Length``. Bytes are identified by their own leading bytes, and
the cap is enforced DURING the stream as well as against the header --
a header is a promise, not a limit. Unrecognised bytes are REJECTED.
There is no ``.jpg`` fallback here; ``photo_intake/storage.py`` has one
and spec 12.1 names it as the thing this lane must not copy.

THE CREDENTIAL RULE

``base_url`` is a bearer-scoped download URL, live for about an hour. It
is never logged and never placed in an exception message, and neither is
the access token. That includes transport failures: a ``requests``
exception stringifies to a message CONTAINING the full URL, so only the
exception class name is ever reported. Failures name the item id and a
reason, nothing else.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests

from ..photo_intake.dedupe import sha256_file
from ..photo_intake.exif import extract_exif
from ..photo_intake.metadata_trust import classify_metadata_trust

logger = logging.getLogger("code.services.google_picker.acquire")


# ------------------------------------------------------------------ the cap

MAX_BYTES_ENV = "HORNELORE_GOOGLE_PICKER_MAX_BYTES"
DEFAULT_MAX_BYTES = 50 * 1024 * 1024      # matches MAX_UPLOAD_MB=50 in spirit
_MIN_MAX_BYTES = 64 * 1024
_ABS_MAX_BYTES = 2 * 1024 * 1024 * 1024

_CHUNK = 65536
_TIMEOUT = (10, 120)                      # (connect, read-between-chunks)

STAGING_ROOT = "import_staging"
DATA_DIR_ENV = "DATA_DIR"


def max_bytes() -> int:
    """The per-item download cap, in bytes.

    Read from the environment on every call rather than at import, so
    changing ``.env`` and restarting the stack is enough -- there is no
    cached module-level copy to go stale.

    A missing, unparseable or out-of-range value falls back to the
    default WITH a warning rather than refusing to start. A typo in one
    optional tuning key should not take the whole lane down; the warning
    is what makes the typo findable.
    """
    raw = (os.getenv(MAX_BYTES_ENV) or "").strip()
    if not raw:
        return DEFAULT_MAX_BYTES
    try:
        value = int(raw)
    except ValueError:
        logger.warning("google_picker: %s is not an integer; using the "
                       "default cap of %d bytes", MAX_BYTES_ENV,
                       DEFAULT_MAX_BYTES)
        return DEFAULT_MAX_BYTES
    if value < _MIN_MAX_BYTES or value > _ABS_MAX_BYTES:
        logger.warning("google_picker: %s=%d is outside the accepted range "
                       "%d..%d; using the default cap of %d bytes",
                       MAX_BYTES_ENV, value, _MIN_MAX_BYTES, _ABS_MAX_BYTES,
                       DEFAULT_MAX_BYTES)
        return DEFAULT_MAX_BYTES
    return value


# ---------------------------------------------------------------- the errors

class AcquireError(Exception):
    """One item could not be acquired.

    ``retryable`` is the field that matters downstream, and it is a
    property of the FAILURE, not of the item. A short-lived download URL
    that expired mid-run is retryable -- re-listing the session mints a
    new one. A file whose bytes are not an image never becomes one, so
    retrying it forever would be a lie told once per run.

    Neither the message nor any attribute here ever carries a credential
    or a download URL.
    """

    def __init__(self, message: str, *, reason: str = "acquire_error",
                 retryable: bool = True, status: int = 0) -> None:
        super().__init__(message)
        self.reason = reason
        self.retryable = retryable
        self.status = status


# Every reason this module raises, and whether re-running ingest can fix
# it. Kept as data so the route can report the split without restating
# the judgement, and so a new reason cannot be added without landing in
# exactly one of these.
RETRYABLE_REASONS = (
    "network",
    "base_url_expired",
    "upstream_rate_limited",
    "upstream_error",
    "empty_body",
)
PERMANENT_REASONS = (
    "invalid_request",
    "too_large",
    "unsupported_content",
    "item_not_found",
    "data_dir_unset",
    "unsafe_identifier",
    "staging_failed",
)


# --------------------------------------------------------------- the sniffer

# Leading-byte signatures. Deliberately images only: the Picker returns
# VIDEO items too, and this lane has no video evidence story yet, so a
# video is refused as unsupported content rather than half-ingested.
_SIGNATURES = (
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"GIF87a", "image/gif", ".gif"),
    (b"GIF89a", "image/gif", ".gif"),
    (b"II*\x00", "image/tiff", ".tif"),
    (b"MM\x00*", "image/tiff", ".tif"),
)

# ISO-BMFF brands that mean "this is a still image", not a movie. `mif1`
# and `msf1` are the generic image / image-sequence brands HEIF uses.
_HEIF_BRANDS = frozenset(
    (b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevm", b"hevs",
     b"mif1", b"msf1")
)

SNIFF_BYTES = 32
_MIN_SNIFF_BYTES = 12

# The only extensions this module will ever write into staging. Phase 3
# resolves `original.*` from the batch and candidate id and expects
# exactly one; an extension outside this set would be unresolvable.
VERIFIED_EXTENSIONS = (".jpg", ".png", ".gif", ".tif", ".webp", ".heic")


def sniff_image(head: bytes) -> Optional[Tuple[str, str]]:
    """Identify image bytes by their own content. ``None`` means refuse.

    Returns ``(mime, extension)``. The provider's declared ``mimeType``
    is not consulted and is not an input here on purpose -- if it were,
    a disagreement would eventually be resolved in its favour by someone
    fixing a bug at 1am.
    """
    if not isinstance(head, (bytes, bytearray)):
        return None
    head = bytes(head)
    if len(head) < _MIN_SNIFF_BYTES:
        return None
    for magic, mime, ext in _SIGNATURES:
        if head[:len(magic)] == magic:
            return mime, ext
    if head[0:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp", ".webp"
    if head[4:8] == b"ftyp" and head[8:12] in _HEIF_BRANDS:
        return "image/heic", ".heic"
    return None


# -------------------------------------------------------------- the download

def _auth_headers(access_token: str) -> Dict[str, str]:
    return {"Authorization": "Bearer %s" % access_token,
            "Accept": "*/*"}


_STATUS_REASONS = {
    401: ("base_url_expired", True),
    403: ("base_url_expired", True),
    404: ("item_not_found", False),
    429: ("upstream_rate_limited", True),
}


def _raise_for_status(status: int, item_id: str) -> None:
    if status == 200:
        return
    if status in _STATUS_REASONS:
        reason, retryable = _STATUS_REASONS[status]
        if reason == "base_url_expired":
            message = ("Google refused the download of item %s (HTTP %d). A "
                       "picked item's download URL is short-lived; re-list "
                       "the session and retry." % (item_id, status))
        elif reason == "item_not_found":
            message = ("Google no longer has item %s (HTTP 404). The picking "
                       "session may have ended." % item_id)
        else:
            message = ("Google rate-limited the download of item %s (HTTP "
                       "%d)." % (item_id, status))
        raise AcquireError(message, reason=reason, retryable=retryable,
                           status=status)
    retryable = status >= 500
    raise AcquireError(
        "Google answered HTTP %d downloading item %s (body withheld)."
        % (status, item_id),
        reason="upstream_error", retryable=retryable, status=status)


def _refuse_declared_oversize(headers: Any, item_id: str, cap: int) -> None:
    """Refuse before reading a byte when the provider ADMITS it is over.

    This is an optimisation, not the limit. The stream loop enforces the
    cap regardless, because a Content-Length is a claim.
    """
    try:
        declared = int(str((headers or {}).get("Content-Length") or "").strip())
    except (ValueError, AttributeError):
        return
    if declared > cap:
        raise AcquireError(
            "item %s declares %d bytes, over the %d byte cap (%s)."
            % (item_id, declared, cap, MAX_BYTES_ENV),
            reason="too_large", retryable=False, status=200)


def _unlink(path: Optional[str]) -> None:
    """Best-effort removal of a partial download.

    An already-absent file is the SUCCESS case, not a warning: the bytes
    are gone, which is the whole point. Warning on it would fire on every
    ordinary double-cleanup and teach the reader to ignore the one
    message that matters -- a partial photo this process could NOT
    remove, which a later glob would find and mistake for a staged one.
    """
    if not path:
        return
    try:
        os.unlink(path)
    except FileNotFoundError:
        return
    except OSError:
        logger.warning("google_picker: could not remove a partial download")


def _stream_to_temp(resp: Any, item_id: str, cap: int,
                    tmp_dir: Optional[str]) -> Tuple[str, int, str, str]:
    """Bytes to a temp file, capped and content-checked as they arrive.

    On ANY failure the partial file is removed before the exception
    leaves. A refused download that left half a photo on disk would be
    indistinguishable from a staged one to anything that later went
    looking with a glob.
    """
    handle = tempfile.NamedTemporaryFile(delete=False, dir=tmp_dir,
                                         prefix="picker-", suffix=".part")
    tmp_name = handle.name
    head = b""
    total = 0
    sniffed: Optional[Tuple[str, str]] = None
    try:
        with handle:
            try:
                chunks = resp.iter_content(chunk_size=_CHUNK)
            except requests.RequestException:
                raise AcquireError(
                    "the download of item %s failed before it started (%s)."
                    % (item_id, "transport error"),
                    reason="network", retryable=True) from None
            while True:
                try:
                    chunk = next(chunks)
                except StopIteration:
                    break
                except requests.RequestException as exc:
                    # str(exc) contains the full download URL. The class
                    # name does not.
                    raise AcquireError(
                        "the download of item %s was interrupted (%s)."
                        % (item_id, exc.__class__.__name__),
                        reason="network", retryable=True) from None
                if not chunk:
                    continue
                total += len(chunk)
                if total > cap:
                    raise AcquireError(
                        "item %s exceeded the %d byte cap (%s) while "
                        "downloading." % (item_id, cap, MAX_BYTES_ENV),
                        reason="too_large", retryable=False)
                if sniffed is None:
                    if len(head) < SNIFF_BYTES:
                        head += chunk[:SNIFF_BYTES - len(head)]
                    if len(head) >= _MIN_SNIFF_BYTES:
                        sniffed = sniff_image(head)
                        if sniffed is None:
                            raise AcquireError(
                                "item %s is not a supported image: its "
                                "leading bytes match no known image "
                                "signature. Video and other media are not "
                                "evidence this lane can stage yet."
                                % item_id,
                                reason="unsupported_content", retryable=False)
                handle.write(chunk)
        if total == 0:
            raise AcquireError(
                "item %s returned an empty body." % item_id,
                reason="empty_body", retryable=True)
        if sniffed is None:
            raise AcquireError(
                "item %s returned only %d byte(s), too few to identify as "
                "an image." % (item_id, total),
                reason="unsupported_content", retryable=False)
    except BaseException:
        _unlink(tmp_name)
        raise
    mime, ext = sniffed
    return tmp_name, total, mime, ext


def download_original(access_token: str, base_url: str, *,
                      item_id: str = "unknown",
                      cap: Optional[int] = None,
                      tmp_dir: Optional[str] = None) -> Dict[str, Any]:
    """Download one picked item's ORIGINAL bytes to a temporary file.

    Google serves the original for a picked item at ``baseUrl + "=d"``
    with the same bearer token the listing used. Without the suffix the
    response is a display-sized re-encode -- which would look fine and
    would silently destroy the EXIF this lane exists to read.

    Returns ``{tmp_path, byte_size, file_hash, verified_mime,
    verified_ext}``. The caller owns the temp file from here: hand it to
    ``stage_original`` once a candidate id exists, or unlink it.

    Raises ``AcquireError`` and leaves nothing behind on failure.
    """
    if not isinstance(access_token, str) or not access_token.strip():
        raise AcquireError("an access token is required to download bytes.",
                           reason="invalid_request", retryable=False)
    if not isinstance(base_url, str) or not base_url.strip():
        raise AcquireError(
            "item %s has no download URL." % item_id,
            reason="invalid_request", retryable=False)

    cap = int(cap) if cap else max_bytes()
    url = base_url.strip() + "=d"

    try:
        resp = requests.get(url, headers=_auth_headers(access_token),
                            stream=True, timeout=_TIMEOUT)
    except requests.RequestException as exc:
        raise AcquireError(
            "could not reach Google to download item %s (%s)."
            % (item_id, exc.__class__.__name__),
            reason="network", retryable=True) from None

    try:
        _raise_for_status(getattr(resp, "status_code", 0), item_id)
        _refuse_declared_oversize(getattr(resp, "headers", {}), item_id, cap)
        tmp_name, total, mime, ext = _stream_to_temp(resp, item_id, cap,
                                                     tmp_dir)
    finally:
        try:
            resp.close()
        except Exception:
            pass

    file_hash = sha256_file(tmp_name)
    logger.info("google_picker: downloaded item %s -- %d byte(s), %s",
                item_id, total, mime)
    return {
        "tmp_path": tmp_name,
        "byte_size": total,
        "file_hash": file_hash,
        "verified_mime": mime,
        "verified_ext": ext,
    }


# -------------------------------------------------------------- the metadata

def _provider_time(raw: Optional[str]) -> Optional[str]:
    """RFC3339 from Google -> the 'YYYY-MM-DD HH:MM:SS' shape EXIF uses.

    Returns ``None`` for anything that does not parse, rather than a
    partial date. Half a timestamp is worse than no timestamp: it looks
    authoritative in the review queue.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().replace("T", " ")[:19]
    try:
        datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return text


def read_evidence_metadata(path: str, *,
                           provider_create_time: Optional[str] = None
                           ) -> Dict[str, Any]:
    """Date and location, read off the bytes -- with ONE asymmetry.

    The asymmetry is deliberate and is the whole reason this is a
    function rather than four lines at the call site.

    DATE falls back. EXIF capture time wins; when the file carries none,
    the Picker's ``createTime`` is used and labelled
    ``taken_at_source='provider_metadata'`` -- which is exactly what that
    enum value exists for. A roughly-right date the operator can correct
    beats an empty one they cannot sort by.

    LOCATION DOES NOT FALL BACK. Valid EXIF GPS gives latitude, longitude
    and ``location_source='exif_gps'``. Anything else gives null, null
    and ``location_source='unknown'``. Google Picker metadata is never a
    GPS source. ``CANDIDATE_LOCATION_SOURCES`` does permit
    ``provider_metadata``, so nothing in the schema stops a later change
    here -- this rule is the only thing that does, which is why it is
    written down at the point where it would be broken.

    ``gps_present_unparseable`` carries the third state
    ``photo_intake/exif.py`` already ships: a GPS tag that EXISTS but did
    not decode. It is not the same as no GPS at all, it has no enum value
    and no candidate column, and the review queue's ``match_reason`` is
    its only home. Never raises.
    """
    exif: Dict[str, Any] = {}
    try:
        exif = extract_exif(path) or {}
    except Exception as exc:
        logger.warning("google_picker: EXIF read failed (%s); the item is "
                       "still ingestable with unknown metadata",
                       exc.__class__.__name__)
        exif = {}

    gps = exif.get("gps") or {}
    lat = gps.get("latitude")
    lng = gps.get("longitude")
    has_gps = isinstance(lat, (int, float)) and isinstance(lng, (int, float))

    captured_at = exif.get("captured_at")
    if isinstance(captured_at, str) and captured_at.strip():
        taken_at = captured_at.strip()
        taken_at_source = "exif"
    else:
        taken_at = _provider_time(provider_create_time)
        taken_at_source = "provider_metadata" if taken_at else "unknown"

    try:
        trust = classify_metadata_trust(exif) or {}
    except Exception:
        trust = {}

    return {
        "taken_at": taken_at,
        "taken_at_source": taken_at_source,
        "latitude": float(lat) if has_gps else None,
        "longitude": float(lng) if has_gps else None,
        "location_source": "exif_gps" if has_gps else "unknown",
        "gps_present_unparseable": bool(gps.get("present_unparseable")),
        "metadata_trust": trust.get("trust") or "none",
        "trust_reasons": list(trust.get("reasons") or []),
    }


# --------------------------------------------------------------- the staging

# A path segment this module is willing to build a directory out of.
# Batch and candidate ids are uuid4 hex-with-dashes today, but the guard
# is about traversal, not about uuid shape: `..` and separators are what
# must never reach a filesystem call.
_SAFE_ID_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _data_dir() -> Path:
    raw = (os.environ.get(DATA_DIR_ENV) or "").strip()
    if not raw:
        raise AcquireError(
            "%s is not set; refusing to stage bytes without an explicit "
            "base path." % DATA_DIR_ENV,
            reason="data_dir_unset", retryable=False)
    return Path(raw).expanduser()


def _safe_segment(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AcquireError("a %s is required to resolve a staging path."
                           % label,
                           reason="invalid_request", retryable=False)
    text = value.strip()
    if not _SAFE_ID_RX.match(text) or ".." in text:
        raise AcquireError(
            "%s is not usable as a path segment (value withheld)." % label,
            reason="unsafe_identifier", retryable=False)
    return text


def staging_dir_for(batch_id: str, candidate_id: str) -> Path:
    """``DATA_DIR/import_staging/<batch_id>/<candidate_id>/`` -- derived.

    Derived on demand, never stored. Spec 12.5: ``match_reason`` is
    effectively write-once, so a path recorded there could never be
    corrected after the file moved. Phase 3 recomputes this from the two
    ids it already holds.
    """
    return (_data_dir() / STAGING_ROOT / _safe_segment(batch_id, "batch_id")
            / _safe_segment(candidate_id, "candidate_id"))


def stage_original(tmp_path: str, batch_id: str, candidate_id: str,
                   verified_ext: str) -> str:
    """Move the downloaded bytes into the candidate's staging directory.

    Called ONLY after ``candidate_create()`` has returned a real id.

    Phase 3 will require exactly one ``original.*`` in this directory, so
    a re-ingest that produces a different verified extension -- the same
    photo re-exported, say -- must not leave two. Any pre-existing
    ``original.*`` is removed first.
    """
    if verified_ext not in VERIFIED_EXTENSIONS:
        raise AcquireError(
            "refusing to stage item bytes with an unverified extension %r."
            % verified_ext,
            reason="unsupported_content", retryable=False)
    src = Path(tmp_path)
    if not src.is_file():
        raise AcquireError(
            "the downloaded bytes for candidate %s are gone before staging."
            % candidate_id,
            reason="staging_failed", retryable=True)

    target_dir = staging_dir_for(batch_id, candidate_id)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        for stale in target_dir.glob("original.*"):
            if stale.name != "original%s" % verified_ext:
                logger.info("google_picker: replacing a stale %s for "
                            "candidate %s", stale.name, candidate_id)
                stale.unlink()
        target = target_dir / ("original%s" % verified_ext)
        shutil.move(str(src), str(target))
    except AcquireError:
        raise
    except OSError as exc:
        raise AcquireError(
            "could not stage the bytes for candidate %s (%s)."
            % (candidate_id, exc.__class__.__name__),
            reason="staging_failed", retryable=True) from None
    return str(target)


__all__ = [
    "AcquireError",
    "DEFAULT_MAX_BYTES",
    "MAX_BYTES_ENV",
    "PERMANENT_REASONS",
    "RETRYABLE_REASONS",
    "STAGING_ROOT",
    "VERIFIED_EXTENSIONS",
    "download_original",
    "max_bytes",
    "read_evidence_metadata",
    "sniff_image",
    "stage_original",
    "staging_dir_for",
]
