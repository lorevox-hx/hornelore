"""Filesystem erasure for a deleted narrator.

WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01 — deletion integrity
(2026-08-20).

THE DEFECT THIS EXISTS TO CLOSE. `hard_delete_person()` removed every
database row for a narrator, returned `{"status": "hard_deleted"}` with
HTTP 200, and left the narrator's own words on disk. Measured during
the synthetic live acceptance: after a successful hard delete, eight
files survived in two directories and five of them contained the
narrator's verbatim speech --

    memory/archive/people/<pid>/sessions/<conv>/transcript.txt
    memory/archive/people/<pid>/sessions/<conv>/transcript.jsonl
    memory/archive/people/<pid>/sessions/<conv>/thread_anchor.json
    memory/archive/people/<pid>/rolling_summary.json
    stories-captured/<pid>/<stamp>__<cid>/transcript.txt

Only the Kawa directory was being removed, because it was the only one
anybody had remembered to name. A deletion that reports success while
retaining the thing it claimed to delete is worse than a deletion that
fails: the operator stops looking.

── DESIGN RULES ──────────────────────────────────────────────────────

**Every target is derived, never supplied.** A caller passes a person
id and nothing else. Each path is built from the validated data root
plus a fixed relative template plus that id. There is no parameter
through which a client could name a directory to delete, because the
one thing worse than not erasing a narrator is erasing something else.

**Containment is checked before every removal, on the RESOLVED path.**
A person id is validated against a strict pattern first, and the
resolved target must still be inside the resolved root afterwards.
The second check is not redundant: a symlink placed inside the data
root can carry an otherwise-valid path outside it, and the pattern
cannot see that.

**Absent is a SUCCESS, not a failure.** That is what makes a retry
safe. A partial failure -- one directory removed, the next refused by a
file lock -- must be re-runnable, and on the second run the first
directory is simply already gone.

**A failure is reported, never swallowed.** `ok` is false and the
target appears in `residue` with the reason. The caller is expected to
turn that into a partial-deletion answer rather than a 200.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("narrator_erasure")

__all__ = [
    "ERASURE_TARGETS",
    "RETAINED_BY_DESIGN",
    "EraseResult",
    "data_root",
    "erase_person_files",
    "person_file_residue",
    "UnsafePersonId",
    "UnsafeDataRoot",
]


class UnsafePersonId(ValueError):
    """The id is not a shape this system ever generates."""


class UnsafeDataRoot(RuntimeError):
    """DATA_DIR is missing, relative, or points somewhere no deletion
    may be attempted."""


#: Person ids in this system are uuid4 strings, and the harness also
#: creates `harness-test-...` ids. Both are covered by one conservative
#: pattern. Anything else -- a path separator, a `..`, a NUL, a leading
#: dot, an empty string -- is refused BEFORE it is ever joined to a
#: path. Validating the id is cheaper and clearer than trying to
#: sanitise a path after the fact.
_SAFE_PERSON_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,127}$")

#: Directories that hold this narrator's own content and must go when
#: they do. `(key, *relative parts under the data root)` -- the person
#: id is appended as the final component by the resolver, so no entry
#: here can name a specific directory.
ERASURE_TARGETS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    # Conversation transcripts: the narrator's speech, verbatim.
    ("memory_archive", ("memory", "archive", "people")),
    # Captured stories mirror: transcript + metadata per candidate.
    ("stories_captured", ("stories-captured",)),
    # Photographs. `photos.narrator_id` is ON DELETE CASCADE, so the
    # rows go with the person and the files must follow them.
    ("photo_archive", ("memory", "archive", "photos")),
    # Kawa segments. Already removed before this module existed; moved
    # here so there is ONE inventory rather than one remembered case
    # and four forgotten ones.
    ("kawa_segments", ("kawa", "people")),
)

#: Narrator-owned locations this module deliberately does NOT erase,
#: and why. Reported on every call so "complete" can never be read as
#: "nothing of this person remains" when something does.
RETAINED_BY_DESIGN: Tuple[Tuple[str, Tuple[str, ...], str], ...] = (
    ("media_uploads", ("media",),
     "media.person_id and media_attachments.person_id are ON DELETE SET "
     "NULL by schema design, so those rows deliberately outlive the "
     "narrator; erasing the files would orphan rows the schema chose to "
     "keep. Whether that design should change is a product decision, "
     "not one this deletion path may take on its own."),
)


class EraseResult:
    """What actually happened on disk, in a shape a caller can report.

    `ok` is False if ANY target failed. The caller must not answer 200
    "complete" on a False.
    """

    def __init__(self) -> None:
        self.removed: List[Dict[str, Any]] = []
        self.absent: List[str] = []
        self.failed: List[Dict[str, Any]] = []
        self.retained: List[Dict[str, Any]] = []
        self.residue: List[Dict[str, Any]] = []

    @property
    def ok(self) -> bool:
        return not self.failed and not self.residue

    @property
    def files_removed(self) -> int:
        return sum(int(r.get("files") or 0) for r in self.removed)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "directories_removed": [r["target"] for r in self.removed],
            "files_removed": self.files_removed,
            "removed_detail": self.removed,
            "already_absent": self.absent,
            "failed": self.failed,
            "retained_by_design": self.retained,
            "residue": self.residue,
        }


def data_root() -> Path:
    """The validated erasure root.

    Read at call time, not import time, so a test can point it at a
    temporary directory the same way the rest of the stack does.

    Refuses a relative root, a root that does not exist, and a root
    that resolves to the filesystem root. Each refusal is a case where
    a bug in configuration would otherwise be executed as a recursive
    delete somewhere unintended.
    """
    raw = (os.getenv("DATA_DIR", "") or "").strip()
    if not raw:
        raise UnsafeDataRoot(
            "DATA_DIR is not set; refusing to erase narrator files without "
            "an explicit data root")
    root = Path(raw).expanduser()
    if not root.is_absolute():
        # A relative root resolves against the process's working
        # directory, which is not a property anybody reviewing a
        # deletion can see.
        raise UnsafeDataRoot("DATA_DIR must be an absolute path, got %r" % raw)
    root = root.resolve()
    if root == Path(root.anchor):
        raise UnsafeDataRoot("DATA_DIR resolves to the filesystem root")
    if not root.is_dir():
        raise UnsafeDataRoot("DATA_DIR %s is not a directory" % root)
    return root


def _validated_id(person_id: str) -> str:
    pid = (person_id or "").strip()
    if not _SAFE_PERSON_ID.match(pid):
        raise UnsafePersonId(
            "refusing to build a deletion path from an id of this shape")
    return pid


def _resolve_target(root: Path, parts: Tuple[str, ...], person_id: str) -> Path:
    """Build one target and prove it is inside the root.

    The containment check runs on the RESOLVED path. A symlink under
    the data root pointing elsewhere would satisfy the id pattern and
    the string join and still land outside; only resolving catches it.
    """
    target = root.joinpath(*parts, person_id)
    try:
        resolved = target.resolve()
    except OSError:                                   # pragma: no cover
        resolved = target
    try:
        resolved.relative_to(root)
    except ValueError:
        raise UnsafePersonId(
            "resolved deletion target escapes the data root")
    if resolved == root:
        raise UnsafePersonId("resolved deletion target IS the data root")
    return resolved


def _count_files(path: Path) -> int:
    try:
        return sum(1 for p in path.rglob("*") if p.is_file())
    except OSError:                                   # pragma: no cover
        return 0


def erase_person_files(person_id: str,
                       *,
                       root: Optional[Path] = None) -> EraseResult:
    """Remove every narrator-owned directory for `person_id`.

    Idempotent: a target that is already gone is recorded as `absent`
    and is not an error, so a run that failed halfway can be repeated
    without special handling.
    """
    res = EraseResult()
    pid = _validated_id(person_id)
    base = root.resolve() if root is not None else data_root()

    for key, parts in ERASURE_TARGETS:
        try:
            target = _resolve_target(base, parts, pid)
        except UnsafePersonId as exc:
            res.failed.append({"target": key, "reason": str(exc)})
            continue
        rel = "/".join(parts) + "/" + pid
        if not target.exists():
            res.absent.append(key)
            continue
        n = _count_files(target)
        try:
            shutil.rmtree(target)
        except OSError as exc:
            # Reported, never swallowed. A locked file here means the
            # narrator's words are still on disk.
            logger.error("[erasure] %s failed for %s: %s", key, pid, exc)
            res.failed.append({"target": key, "path": rel,
                               "reason": exc.__class__.__name__})
            continue
        if target.exists():                           # pragma: no cover
            res.failed.append({"target": key, "path": rel,
                               "reason": "still present after removal"})
            continue
        logger.info("[erasure] removed %s (%d file(s)) for %s", rel, n, pid)
        res.removed.append({"target": key, "path": rel, "files": n})

    for key, parts, why in RETAINED_BY_DESIGN:
        try:
            target = _resolve_target(base, parts, pid)
        except UnsafePersonId:                        # pragma: no cover
            continue
        if not target.exists():
            continue
        n = _count_files(target)
        entry = {"target": key, "path": "/".join(parts) + "/" + pid,
                 "files": n, "reason": why}
        res.retained.append(entry)
        # Retained-by-design still means narrator bytes are on disk.
        # It is listed as residue too, so `ok` is False and no caller
        # can answer "complete" while the files are there.
        res.residue.append(entry)

    return res


def person_file_residue(person_id: str,
                        *,
                        root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Every narrator-owned directory still on disk for `person_id`.

    Read-only. Used to VERIFY an erasure rather than to trust its own
    report -- a synthetic harness that checked only the response body
    would have passed on the defect this module closes.
    """
    pid = _validated_id(person_id)
    base = root.resolve() if root is not None else data_root()
    out: List[Dict[str, Any]] = []
    for key, parts in ERASURE_TARGETS + tuple(
            (k, p) for k, p, _ in RETAINED_BY_DESIGN):
        try:
            target = _resolve_target(base, parts, pid)
        except UnsafePersonId:                        # pragma: no cover
            continue
        if target.exists():
            out.append({"target": key,
                        "path": "/".join(parts) + "/" + pid,
                        "files": _count_files(target)})
    return out
