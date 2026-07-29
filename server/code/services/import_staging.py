"""Where an import lane keeps its own verified copy of a picture.

WHY THIS MODULE EXISTS
======================

``import_staging/<batch_id>/<candidate_id>/original.<ext>`` was invented
by the Google Picker acquisition lane, and until 2026-07-29 it was also
DEFINED there, inside ``services/google_picker/acquire.py``. That was
correct while the only writer and the only reader were both the Picker.

It stopped being correct the moment promotion had to read it.

Promotion lives in ``api/services/import_repository.py``, which is the
shared intake lane every producer enters (spec 12.7). Had that module
imported ``services.google_picker.acquire`` to find the bytes, the
shared lane would have acquired a hard dependency on one provider's
module -- and the second provider to stage bytes would have had to
either import the Picker's module too or invent a second convention.
Both are drift. The convention is named ``import_staging``, not
``picker_staging``, because it never was provider-specific; only its
definition was.

So the convention lives here now, once, and both sides delegate:

    services/google_picker/acquire.py   -- writes the staged original
    api/services/import_repository.py   -- reads and verifies it

WHAT THIS MODULE IS NOT
=======================

It is not a general file store, and it must not grow into one. It knows
one directory shape, one filename stem, and how to answer two questions
about them: "where would this candidate's copy be?" and "is the copy
that is there the copy the row describes?". Anything that needs more
than that is describing the permanent archive, and the permanent archive
is ``photos`` -- reached through the photo lane, not through here.

STAGING IS NOT THE ARCHIVE (doctrine 1.14)
==========================================

A staged original is a working copy of something a provider still holds.
It is disposable: losing it costs a re-fetch, not a photograph. The
archive copy is the one promotion creates, under ``photos``, and once a
candidate has been promoted the staged copy stops being the authority
for anything. Nothing here deletes, moves, or repairs; the writers do
that, and they do it with the candidate row in hand.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

# ------------------------------------------------------------ the convention

STAGING_ROOT = "import_staging"
INCOMING_DIRNAME = ".incoming"
DATA_DIR_ENV = "DATA_DIR"

# The stem every staged original is written under. The extension varies
# because it is derived from the sniffed content type, never from a
# provider-supplied filename, so the glob is on the stem and the caller
# is required to find exactly one match.
ORIGINAL_STEM = "original"
ORIGINAL_GLOB = ORIGINAL_STEM + ".*"

# A path segment this module is willing to build a directory out of.
# Batch and candidate ids are uuid4 hex-with-dashes today, but the guard
# is about traversal, not about uuid shape: `..` and separators are what
# must never reach a filesystem call.
_SAFE_ID_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


# ----------------------------------------------------------------- the error


class StagingPathError(Exception):
    """A staging path could not be resolved.

    ``reason`` is the same vocabulary the Picker's ``AcquireError`` uses
    for these three cases (``data_dir_unset``, ``invalid_request``,
    ``unsafe_identifier``) so that ``acquire`` can translate one into
    the other without inventing a second set of names for one set of
    facts. The message never contains the offending value: an id that
    failed the safety expression is exactly the kind of string that
    should not be echoed back into a log line.
    """

    def __init__(self, message: str, *, reason: str = "invalid_request") -> None:
        super().__init__(message)
        self.reason = reason


# ------------------------------------------------------------------ resolving


def data_dir() -> Path:
    """The configured data root, or a refusal.

    Read from the environment on every call, not cached at import: the
    offline tests point ``DATA_DIR`` at a fresh temporary directory per
    test case, and a cached value would make the second test read the
    first test's files.
    """
    raw = (os.environ.get(DATA_DIR_ENV) or "").strip()
    if not raw:
        raise StagingPathError(
            "%s is not set; refusing to resolve a staging path without an "
            "explicit base path." % DATA_DIR_ENV,
            reason="data_dir_unset")
    return Path(raw).expanduser()


def safe_segment(value: Any, label: str) -> str:
    """One id, checked before it is allowed to become a path segment."""
    if not isinstance(value, str) or not value.strip():
        raise StagingPathError(
            "a %s is required to resolve a staging path." % label,
            reason="invalid_request")
    text = value.strip()
    if not _SAFE_ID_RX.match(text) or ".." in text:
        raise StagingPathError(
            "%s is not usable as a path segment (value withheld)." % label,
            reason="unsafe_identifier")
    return text


def staging_dir_for(batch_id: str, candidate_id: str) -> Path:
    """``DATA_DIR/import_staging/<batch_id>/<candidate_id>/`` -- derived.

    Derived on demand, never stored. Spec 12.5: ``match_reason`` is
    effectively write-once, so a path recorded there could never be
    corrected after the file moved. Every reader recomputes this from
    the two ids it already holds.
    """
    return (data_dir() / STAGING_ROOT / safe_segment(batch_id, "batch_id")
            / safe_segment(candidate_id, "candidate_id"))


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
    return (data_dir() / STAGING_ROOT / INCOMING_DIRNAME
            / safe_segment(batch_id, "batch_id"))


def staged_original(batch_id: str, candidate_id: str) -> Optional[Path]:
    """The one ``original.*`` in a candidate's staging directory, or None.

    None means "there is no single staged copy to work from" and
    deliberately covers four cases that all want the same answer: the
    path could not be resolved at all, the directory does not exist, it
    is empty, or it holds more than one ``original.*``.

    A directory holding two originals is already broken -- one of them
    is not the file the row describes and nothing on disk says which --
    so answering None is what makes the reader refuse instead of picking
    one. Re-staging is the repair: ``stage_original`` writes the new one
    and then removes the stale extensions.

    Returning None rather than raising is deliberate. Every caller has
    to decide what a missing copy MEANS in its own context -- for the
    Picker's re-ingest it is the repair condition, for promotion it is a
    refusal -- and an exception here would push that decision into a
    try/except in both.
    """
    try:
        target_dir = staging_dir_for(batch_id, candidate_id)
    except StagingPathError:
        return None
    try:
        found = sorted(p for p in target_dir.glob(ORIGINAL_GLOB) if p.is_file())
    except OSError:
        return None
    return found[0] if len(found) == 1 else None


def hash_file(path: Any) -> str:
    """The sha256 of a file already on disk.

    ONE definition of "the hash of this photograph", shared with the
    photo lane by using the photo lane's own helper. Download hashes
    what it just wrote with ``sha256_file``; ``photos.file_hash`` is
    written from ``sha256_file``; so a comparison between a staged copy
    and either of those is a comparison of like with like. Computing a
    digest a second way here -- even the same algorithm, read a
    different way -- would be a place for the two to silently disagree.

    Raises ``OSError`` on an unreadable file, unwrapped, because that is
    what the callers already catch and it says exactly what happened.
    """
    return _sha256_file()(str(path))


def _sha256_file() -> Any:
    """Deferred, with the same two-rooting fallback the rest of the
    codebase uses: the offline test env roots ``sys.path`` at ``server/``
    while the served app roots it at ``server/code``. Deferring also
    keeps this module importable by anything that only wants the path
    convention and has no interest in the photo lane."""
    try:
        from .photo_intake.dedupe import sha256_file as _h  # type: ignore
    except ImportError:
        from services.photo_intake.dedupe import (  # type: ignore
            sha256_file as _h,
        )
    return _h
