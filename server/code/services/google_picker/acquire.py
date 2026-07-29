"""Byte acquisition for the Google Photos Picker lane -- Phase 2B.

WHAT THIS MODULE DOES

    max_bytes()              the streamed download cap, read from the env
    sniff_image()            magic-byte content inspection -> (mime, ext)
    download_original()      one picked item's original bytes -> a temp file
    read_evidence_metadata() EXIF date + GPS read off the bytes on disk
    incoming_dir_for()       DATA_DIR/import_staging/.incoming/<batch>/
    staging_dir_for()        DATA_DIR/import_staging/<batch>/<candidate>/
    stage_original()         move the temp file into that directory
    is_retryable()           reason -> whether re-running ingest can fix it

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

THE CONSISTENCY GAP THIS MODULE IS SHAPED AROUND

``candidate_create()`` commits and cannot be rolled back, and the file
is staged AFTER it returns. So there is a window in which a committed
candidate row has no staged original, and the only thing that decides
whether that window is repairable is whether staging failed in a way
worth retrying and whether a half-written file was left behind. Every
staging rule below exists for that window:

  * the temp file is written UNDER ``DATA_DIR`` so the final move is a
    same-filesystem rename rather than a copy that can tear;
  * the final step is ``os.replace`` onto ``original.<ext>``, which
    either happens or does not -- no reader ever sees a partial one;
  * an existing staged original is not removed until its replacement is
    already in place, so a failed re-ingest cannot destroy the last
    verified copy;
  * every failure that a retry could fix is classified retryable IN THE
    VOCABULARY, not at the raise site, so the two cannot disagree.

TIMESTAMPS

This repository stores timestamps as UTC with no offset -- naive
strings, or a literal ``Z``. Its one reader of photo capture times,
``trip_photo_clustering._parse_dt``, accepts ``YYYY-MM-DDTHH:MM:SS``,
``YYYY-MM-DD HH:MM:SS``, ``YYYY:MM:DD HH:MM:SS`` and ``YYYY-MM-DD``,
strips a trailing ``Z``, and CANNOT read a numeric offset at all: a
value ending ``+02:00`` parses as nothing and drops silently out of
scoring. The Picker's ``createTime`` is RFC 3339 and does carry an
offset. So this module parses that offset, converts to UTC, and emits
the naive shape -- see ``_provider_time``.
"""

from __future__ import annotations

import errno
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests

from .. import import_staging
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

# 2026-07-29: these three were DEFINED here. The lines that stood here
# read ``STAGING_ROOT = "import_staging"``, ``INCOMING_DIRNAME =
# ".incoming"`` and ``DATA_DIR_ENV = "DATA_DIR"``, and that was right
# while this module was both the only writer and the only reader of the
# staging tree.
#
# It stopped being right when promotion had to read the same tree.
# Promotion lives in the SHARED intake lane, and a shared lane must not
# import one provider's module to find out where bytes live. The
# convention moved to ``services/import_staging.py`` -- one definition,
# delegated to from both ends -- and these names are re-exported here so
# this module's own callers and tests keep working against the
# vocabulary they already use.
STAGING_ROOT = import_staging.STAGING_ROOT
INCOMING_DIRNAME = import_staging.INCOMING_DIRNAME
DATA_DIR_ENV = import_staging.DATA_DIR_ENV


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

# Every reason this module raises, and whether re-running ingest can fix
# it. Kept as data so the route can report the split without restating
# the judgement, and so a new reason cannot be added without landing in
# exactly one of these.
#
# `staging_failed` and `hash_failed` are RETRYABLE, and that is a product
# ruling rather than an implementation detail: a locked file, an
# interrupted permission, a full disk or a temp file that vanished under
# us is a fact about this machine at this moment. It is not an operator's
# verdict about the photograph. Classifying either as permanent would
# strand a perfectly good picked item that a second run would have taken.
RETRYABLE_REASONS = (
    "acquire_error",          # the unspecific default; see AcquireError
    "network",
    "base_url_expired",
    "upstream_rate_limited",
    "upstream_error",
    "empty_body",
    "hash_failed",
    "staging_failed",
)
PERMANENT_REASONS = (
    "invalid_request",
    "too_large",
    "unsupported_content",
    "item_not_found",
    "data_dir_unset",
    "unsafe_identifier",
    "upstream_client_error",
)

# The vocabulary flattened into the one lookup every raise site obeys.
# Built here, once, from the two tuples above so the tuples cannot drift
# apart from the behaviour -- and asserted disjoint at import, because a
# reason living in both lists would resolve to whichever tuple happened
# to be second.
_REASON_RETRYABLE: Dict[str, bool] = {}
for _reason in RETRYABLE_REASONS:
    _REASON_RETRYABLE[_reason] = True
for _reason in PERMANENT_REASONS:
    if _reason in _REASON_RETRYABLE:
        raise AssertionError(
            "google_picker acquire: %r is classified both retryable and "
            "permanent" % _reason)
    _REASON_RETRYABLE[_reason] = False
del _reason


def is_retryable(reason: str) -> bool:
    """Whether re-running ingest can fix a failure with this reason.

    An unrecognised reason is treated as retryable. That is the safe
    default of the two: a retryable failure that is really permanent
    costs one wasted download on the next run, while a permanent verdict
    on a really-transient failure strands a photograph the operator
    picked and never explains why.
    """
    known = _REASON_RETRYABLE.get(reason)
    if known is None:
        logger.warning("google_picker: unclassified failure reason %r; "
                       "treating it as retryable", reason)
        return True
    return known


class AcquireError(Exception):
    """One item could not be acquired.

    ``retryable`` is the field that matters downstream, and it is a
    property of the FAILURE, not of the item. A short-lived download URL
    that expired mid-run is retryable -- re-listing the session mints a
    new one. A file whose bytes are not an image never becomes one, so
    retrying it forever would be a lie told once per run.

    IT IS NOT A CONSTRUCTOR ARGUMENT. It is derived from ``reason`` via
    ``is_retryable`` precisely so a raise site cannot contradict the
    vocabulary the route reports against -- which is exactly what had
    happened: ``staging_failed`` sat in ``PERMANENT_REASONS`` while both
    of its raise sites passed ``retryable=True``, so the route and the
    exception would have told an operator two different stories about
    the same photograph.

    Neither the message nor any attribute here ever carries a credential
    or a download URL.
    """

    def __init__(self, message: str, *, reason: str = "acquire_error",
                 status: int = 0) -> None:
        super().__init__(message)
        self.reason = reason
        self.retryable = is_retryable(reason)
        self.status = status


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


# Status -> reason only. The retryability that used to ride along in
# these tuples now comes from the vocabulary, which is the whole point of
# fix 1: two places that each carried half the judgement had already
# managed to disagree once.
_STATUS_REASONS = {
    401: "base_url_expired",
    403: "base_url_expired",
    404: "item_not_found",
    429: "upstream_rate_limited",
}


def _raise_for_status(status: int, item_id: str) -> None:
    if status == 200:
        return
    if status in _STATUS_REASONS:
        reason = _STATUS_REASONS[status]
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
        raise AcquireError(message, reason=reason, status=status)
    # An unmapped 5xx is Google having a bad minute and is worth another
    # run; an unmapped 4xx is this request being wrong and will be just
    # as wrong next time. They get SEPARATE reasons rather than one
    # reason carrying a computed retryable, because a reason whose
    # retryability depends on its call site is exactly what the
    # vocabulary now forbids.
    reason = "upstream_error" if status >= 500 else "upstream_client_error"
    raise AcquireError(
        "Google answered HTTP %d downloading item %s (body withheld)."
        % (status, item_id),
        reason=reason, status=status)


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
            reason="too_large", status=200)


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
                    reason="network") from None
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
                        reason="network") from None
                if not chunk:
                    continue
                total += len(chunk)
                if total > cap:
                    raise AcquireError(
                        "item %s exceeded the %d byte cap (%s) while "
                        "downloading." % (item_id, cap, MAX_BYTES_ENV),
                        reason="too_large")
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
                                reason="unsupported_content")
                handle.write(chunk)
        if total == 0:
            raise AcquireError(
                "item %s returned an empty body." % item_id,
                reason="empty_body")
        if sniffed is None:
            raise AcquireError(
                "item %s returned only %d byte(s), too few to identify as "
                "an image." % (item_id, total),
                reason="unsupported_content")
    except BaseException:
        _unlink(tmp_name)
        raise
    mime, ext = sniffed
    return tmp_name, total, mime, ext


def download_original(access_token: str, base_url: str, *,
                      item_id: str = "unknown",
                      cap: Optional[int] = None,
                      batch_id: Optional[str] = None,
                      tmp_dir: Optional[str] = None) -> Dict[str, Any]:
    """Download one picked item's ORIGINAL bytes to a temporary file.

    Google serves the original for a picked item at ``baseUrl + "=d"``
    with the same bearer token the listing used. Without the suffix the
    response is a display-sized re-encode -- which would look fine and
    would silently destroy the EXIF this lane exists to read.

    WHERE THE TEMP FILE LANDS DECIDES WHETHER STAGING CAN BE ATOMIC.
    Pass ``batch_id`` and the bytes are written into
    ``DATA_DIR/import_staging/.incoming/<batch_id>/``, which shares a
    filesystem with the staging directory, so ``stage_original`` finishes
    with a rename. Pass neither ``batch_id`` nor ``tmp_dir`` and the
    system temp directory is used -- which on this stack is a different
    filesystem from ``DATA_DIR``, so the final move degrades to a copy.
    ``stage_original`` still lands the bytes correctly in that case; it
    just cannot promise the same thing about a crash mid-copy. The route
    passes ``batch_id``.

    Returns ``{tmp_path, byte_size, file_hash, verified_mime,
    verified_ext}``. The caller owns the temp file from here: hand it to
    ``stage_original`` once a candidate id exists, or unlink it.

    Raises ``AcquireError`` and leaves nothing behind on failure.
    """
    if not isinstance(access_token, str) or not access_token.strip():
        raise AcquireError("an access token is required to download bytes.",
                           reason="invalid_request")
    if not isinstance(base_url, str) or not base_url.strip():
        raise AcquireError(
            "item %s has no download URL." % item_id,
            reason="invalid_request")

    cap = int(cap) if cap else max_bytes()
    url = base_url.strip() + "=d"
    if tmp_dir is None and batch_id is not None:
        tmp_dir = str(_ensure_incoming_dir(batch_id))

    try:
        resp = requests.get(url, headers=_auth_headers(access_token),
                            stream=True, timeout=_TIMEOUT)
    except requests.RequestException as exc:
        raise AcquireError(
            "could not reach Google to download item %s (%s)."
            % (item_id, exc.__class__.__name__),
            reason="network") from None

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

    # Hashing sits OUTSIDE the streaming loop's cleanup, so it needs its
    # own. Until this returns, the caller does not know the temp file
    # exists and cannot be expected to remove it; a read error here would
    # otherwise leave a complete, valid, unreferenced photo in the
    # incoming directory forever.
    try:
        file_hash = sha256_file(tmp_name)
    except Exception as exc:
        _unlink(tmp_name)
        raise AcquireError(
            "could not hash the downloaded bytes for item %s (%s)."
            % (item_id, exc.__class__.__name__),
            reason="hash_failed") from None

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

# The offset tail of an RFC 3339 timestamp: Z, +HH:MM, -HH:MM, +HHMM.
_OFFSET_RX = re.compile(r"(?:Z|z|(?P<sign>[+-])(?P<h>\d{2}):?(?P<m>\d{2}))$")


def _provider_time(raw: Optional[str]) -> Optional[str]:
    """RFC 3339 from Google -> naive UTC ``'YYYY-MM-DD HH:MM:SS'``.

    THE OFFSET IS PARSED, NOT TRIMMED. This used to slice the string to
    nineteen characters, which turns ``2026-04-11T09:15:00+02:00`` into
    ``2026-04-11 09:15:00`` -- a different instant wearing the same
    digits, two hours wrong, and wrong silently.

    Converting to UTC rather than keeping the provider's wall clock is
    what this repository already does everywhere else: every ``_now()``
    helper in the services layer is
    ``datetime.now(timezone.utc)`` stored naive or with a literal ``Z``,
    and ``trip_photo_clustering._parse_dt`` -- the one reader of capture
    times -- has no tz-aware branch and cannot read a numeric offset at
    all. Emitting ``+02:00`` would parse as nothing there and the photo
    would drop out of time scoring without a word.

    So the offset is honoured and then normalised away. The result is UTC
    wall time, which is NOT local capture time -- a photo taken at 01:30
    in Rome is dated the previous day here. Nothing in the Picker payload
    can tell us the local zone, so that is not a gap this lane can close,
    and it is precisely why the value is labelled
    ``taken_at_source='provider_metadata'`` and promotes with
    ``date_precision='unknown'``: a starting point the operator corrects,
    never an authority. EXIF, when the file carries it, wins outright and
    is local wall time by definition.

    Returns ``None`` for anything that does not parse, rather than a
    partial date. Half a timestamp is worse than no timestamp: it looks
    authoritative in the review queue.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()

    offset = None
    match = _OFFSET_RX.search(text)
    if match:
        text = text[:match.start()]
        if match.group("h") is None:
            offset = timedelta(0)                       # Z
        else:
            offset = timedelta(hours=int(match.group("h")),
                               minutes=int(match.group("m")))
            if match.group("sign") == "-":
                offset = -offset

    text = text.replace("T", " ").replace("t", " ")
    fraction = ""
    if "." in text:
        text, fraction = text.split(".", 1)
    if fraction and not fraction.isdigit():
        return None                                     # not a fraction

    try:
        moment = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

    # No offset at all is not valid RFC 3339, but Google is not the only
    # thing that will ever hand this function a string. Such a value is
    # taken at face value rather than assumed to be UTC, because guessing
    # would move a timestamp that was already right.
    if offset is not None:
        moment = (moment.replace(tzinfo=timezone.utc) - offset
                  ).astimezone(timezone.utc).replace(tzinfo=None)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


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
#
# 2026-07-29: the expression itself moved to ``import_staging`` with the
# rest of the convention. Re-exported rather than restated, because two
# copies of a traversal guard is one copy that can be relaxed alone.
_SAFE_ID_RX = import_staging._SAFE_ID_RX


def _as_acquire_error(exc: import_staging.StagingPathError) -> AcquireError:
    """One refusal, retold in this lane's vocabulary.

    ``import_staging`` raises with the SAME three reason strings this
    module already classifies (``data_dir_unset``, ``invalid_request``,
    ``unsafe_identifier``), so the translation carries the reason across
    unchanged and ``is_retryable`` reaches the same verdict it always
    did. The message is carried across too: it never contains the
    offending value, by construction on both sides.
    """
    return AcquireError(str(exc), reason=exc.reason)


def _data_dir() -> Path:
    try:
        return import_staging.data_dir()
    except import_staging.StagingPathError as exc:
        raise _as_acquire_error(exc) from None


def _safe_segment(value: Any, label: str) -> str:
    try:
        return import_staging.safe_segment(value, label)
    except import_staging.StagingPathError as exc:
        raise _as_acquire_error(exc) from None


def staging_dir_for(batch_id: str, candidate_id: str) -> Path:
    """``DATA_DIR/import_staging/<batch_id>/<candidate_id>/`` -- derived.

    Derived on demand, never stored. Spec 12.5: ``match_reason`` is
    effectively write-once, so a path recorded there could never be
    corrected after the file moved. Every reader recomputes this from
    the two ids it already holds.

    2026-07-29: the body moved to ``import_staging.staging_dir_for``.
    This is now the Picker lane's door onto the shared convention, kept
    so that a raise inside it is still an ``AcquireError`` with a reason
    this lane's failure vocabulary knows how to classify.
    """
    try:
        return import_staging.staging_dir_for(batch_id, candidate_id)
    except import_staging.StagingPathError as exc:
        raise _as_acquire_error(exc) from None


def incoming_dir_for(batch_id: str) -> Path:
    """``DATA_DIR/import_staging/.incoming/<batch_id>/`` -- derived.

    Downloads land here rather than in the system temp directory for one
    reason: this is under ``DATA_DIR``, so the move into
    ``staging_dir_for(...)`` is a rename on one filesystem and the final
    step can be genuinely atomic. ``shutil.move`` across filesystems is a
    copy followed by a delete, and a copy can be interrupted halfway.

    ``.incoming`` sits alongside the per-batch directories and CANNOT
    collide with one: ``_SAFE_ID_RX`` requires a batch id to begin with
    an alphanumeric, so no batch can ever produce a directory whose name
    starts with a dot. The reservation is enforced by the same expression
    that keeps ``..`` out of these paths, not by hoping uuids stay uuids.
    """
    return (_data_dir() / STAGING_ROOT / INCOMING_DIRNAME
            / _safe_segment(batch_id, "batch_id"))


def _ensure_incoming_dir(batch_id: str) -> Path:
    path = incoming_dir_for(batch_id)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AcquireError(
            "could not open a download area for this batch (%s)."
            % exc.__class__.__name__,
            reason="staging_failed") from None
    return path


def _move_onto(src: Path, dst: Path) -> None:
    """Rename ``src`` onto ``dst``, falling back to a copy across devices.

    ``os.replace`` is the whole point -- it is atomic and it overwrites.
    The ``EXDEV`` branch exists only for a caller that downloaded into
    the system temp directory instead of the incoming area; it is not
    atomic and cannot be, which is why the incoming area exists.
    """
    try:
        os.replace(str(src), str(dst))
        return
    except OSError as exc:
        if getattr(exc, "errno", None) != errno.EXDEV:
            raise
    shutil.copy2(str(src), str(dst))
    _unlink(str(src))


def hash_file(path: Any) -> str:
    """The sha256 of a file already on disk, by the SAME rule as download.

    Exists so a caller can ask whether the bytes staged under a candidate
    are still the bytes that candidate's ``file_hash`` column claims,
    without reaching past this module into ``photo_intake.dedupe`` for
    the helper and without computing a digest a different way. One lane,
    one definition of "the hash of this photograph": if
    ``download_original`` ever changes how it digests, this changes with
    it and the comparison stays honest.

    Raises ``AcquireError(reason="hash_failed")`` -- retryable, because
    an unreadable file is a fact about this machine at this moment and
    not a verdict about the photograph.
    """
    try:
        return import_staging.hash_file(path)
    except Exception as exc:
        raise AcquireError(
            "could not hash the file at the staged location (%s)."
            % exc.__class__.__name__,
            reason="hash_failed") from None


def stage_original(tmp_path: str, batch_id: str, candidate_id: str,
                   verified_ext: str) -> str:
    """Move the downloaded bytes into the candidate's staging directory.

    Called ONLY after ``candidate_create()`` has returned a real id.

    THE ORDER HERE IS THE POINT. A re-ingest of a candidate that already
    has a staged original must not be able to end with NO staged
    original. So the bytes go to a temp name inside the candidate's own
    directory first, that temp name is atomically renamed onto
    ``original.<ext>``, and only once that has succeeded is a stale
    ``original.*`` with a DIFFERENT extension removed. Deleting first --
    which is what this did -- means an interrupted replacement takes the
    last verified copy with it.

    Phase 3 will require exactly one ``original.*`` in this directory, so
    a re-ingest that produces a different verified extension (the same
    photo re-exported, say) must not leave two. A crash between the
    rename and the cleanup can leave a ``.incoming-`` file behind, which
    is harmless: it does not match ``original.*`` and so is invisible to
    the reader that counts.
    """
    if verified_ext not in VERIFIED_EXTENSIONS:
        raise AcquireError(
            "refusing to stage item bytes with an unverified extension %r."
            % verified_ext,
            reason="unsupported_content")
    src = Path(tmp_path)
    if not src.is_file():
        raise AcquireError(
            "the downloaded bytes for candidate %s are gone before staging."
            % candidate_id,
            reason="staging_failed")

    target_dir = staging_dir_for(batch_id, candidate_id)
    target = target_dir / ("original%s" % verified_ext)
    pending: Optional[str] = None
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        handle, pending = tempfile.mkstemp(dir=str(target_dir),
                                           prefix=".incoming-",
                                           suffix=verified_ext)
        os.close(handle)
        _move_onto(src, Path(pending))
        os.replace(pending, str(target))
        pending = None
    except AcquireError:
        _unlink(pending)
        raise
    except OSError as exc:
        _unlink(pending)
        raise AcquireError(
            "could not stage the bytes for candidate %s (%s)."
            % (candidate_id, exc.__class__.__name__),
            reason="staging_failed") from None

    # Only now. The new original is already in place, so a failure in
    # this loop costs a duplicate to clean up rather than the photograph.
    for stale in target_dir.glob("original.*"):
        if stale.name == target.name:
            continue
        logger.info("google_picker: removing a stale %s for candidate %s",
                    stale.name, candidate_id)
        _unlink(str(stale))
    return str(target)


__all__ = [
    "AcquireError",
    "DEFAULT_MAX_BYTES",
    "INCOMING_DIRNAME",
    "MAX_BYTES_ENV",
    "PERMANENT_REASONS",
    "RETRYABLE_REASONS",
    "STAGING_ROOT",
    "VERIFIED_EXTENSIONS",
    "download_original",
    "incoming_dir_for",
    "is_retryable",
    "max_bytes",
    "read_evidence_metadata",
    "sniff_image",
    "stage_original",
    "staging_dir_for",
]
