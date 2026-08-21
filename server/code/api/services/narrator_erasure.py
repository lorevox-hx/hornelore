"""Filesystem erasure for a deleted narrator: planned, symlink-safe,
fully inventoried and retryable.

WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01 — deletion integrity
(2026-08-20).

WHERE THIS STARTED. `hard_delete_person()` removed every database row,
answered 200 `{"status": "hard_deleted"}`, and left the narrator's own
words on disk -- measured live, eight files across two directories,
five of them verbatim narrator speech. The first repair named four
directories and reported partial honestly. Review then found three
things that repair had not:

  * **an internal symlink could delete a DIFFERENT narrator.**
    `stories-captured/A -> stories-captured/B` resolves INSIDE the data
    root, so a containment check that only asked "is the resolved path
    under the root" said yes and `rmtree` took B. Containment was
    necessary and nowhere near sufficient.
  * **retry was not a product capability.** The plan lived in the
    caller's memory and the `people` row was already gone, so the
    second attempt got a 404. The service was idempotent; the product
    could not reach it.
  * **the inventory was a quarter of the surface.** Personal media
    archive, media uploads, trip-source documents, import staging,
    legacy agent transcript exports and the translation cache all held
    narrator content and none were named.

── THE THREE RULES ───────────────────────────────────────────────────

**NO SYMLINK, ANYWHERE BELOW THE ROOT.** Every component of every
target is `lstat`-ed on the way down and a link is refused, whether it
points outside the root or at another narrator inside it. Resolving
first and comparing afterwards is what made A-deletes-B possible: it
asks where the path ENDS UP and never asks what it went through.

**THE PLAN IS BUILT BEFORE THE AUTHORITY IS DESTROYED.** Trip-source
directories, staging batches and legacy transcript files are named by
database rows that cascade away with the person. Planned first,
persisted, then executed -- so a retry after the rows are gone still
knows what to remove.

**SCOPE IS STATED, NEVER IMPLIED.** `active_data_erased` is what this
narrator's live footprint looks like. `historical_residue_present`
covers backups and exports -- shared artefacts that genuinely contain
the narrator and that this path must NOT rewrite. `erasure_complete`
is only true when the first is done and the second is empty, so
"complete" can never quietly mean "complete apart from the backups".
"""
from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger("narrator_erasure")

__all__ = [
    "FIXED_TARGETS", "SHARED_PURGE", "HISTORICAL_STORES", "PlanIncomplete",
    "EraseResult", "data_root", "validate_root",
    "build_plan", "execute_plan", "erase_person_files",
    "person_file_residue", "UnsafePersonId", "UnsafeDataRoot",
    "UnsafeTarget",
]


class UnsafePersonId(ValueError):
    """The id is not a shape this system ever generates."""


class UnsafeDataRoot(RuntimeError):
    """A root that no deletion may be attempted against."""


class PlanIncomplete(RuntimeError):
    """A lane that IS installed could not be read, so the plan would be
    short. Raised rather than logged: a short plan hands the caller
    permission to destroy the database authority those targets are
    named by, after which the files are unreachable."""


class UnsafeTarget(RuntimeError):
    """A path that must not be removed: a symlink, an escape, or the
    root itself."""


#: uuid4 plus the `harness-test-...` ids the operator harness makes.
#: Anything else -- a separator, `..`, a NUL, a leading dot, an empty
#: string -- is refused BEFORE it is joined to a path.
_SAFE_PERSON_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,127}$")

#: The same shape rule for the ids that name dynamic targets. A trip
#: source id or a batch id comes from our own database, but it reaches
#: a path either way, so it is validated with the same rule rather than
#: trusted for being ours.
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

#: Directories named by the person id alone. `(key, relative parts)`.
FIXED_TARGETS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("memory_archive", ("memory", "archive", "people")),
    ("stories_captured", ("stories-captured",)),
    ("photo_archive", ("memory", "archive", "photos")),
    ("kawa_segments", ("kawa", "people")),
    # Personal archive documents. Distinct from `media/<pid>` below:
    # this is the archive lane, that is the upload lane, and both hold
    # the narrator's own material.
    ("personal_media_archive", ("media", "archive", "people")),
    # Uploads. Erased on a CONFIRMED HARD DELETE per Chris's ruling of
    # 2026-08-20: `ON DELETE SET NULL` may stay as a database
    # fallback, but an explicit hard erasure must not leave
    # identifiable photographs behind as ownerless rows.
    ("media_uploads", ("media",)),
)

#: Disposable, shared, and not attributable per narrator. Translated
#: narrator text is written here keyed by content hash, so there is no
#: way to select this person's entries -- and it is a CACHE, so the
#: right answer is to drop all of it rather than leave narrator
#: sentences in a file nobody can attribute.
SHARED_PURGE: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("translation_cache", ("translations-cache",)),
)

#: Shared historical artefacts. REPORTED, never touched: a backup is a
#: point-in-time copy of everybody, and silently rewriting one to
#: remove a person destroys its value as a restore point. Naming them
#: is what stops "erasure_complete" from meaning less than it says.
HISTORICAL_STORES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("backups", ("backups",)),
    ("exports", ("exports",)),
)


# ── Root and path safety ────────────────────────────────────────────────

def validate_root(raw: Any) -> Path:
    """The one root check, applied to the environment AND to an
    explicit root passed by internal code.

    The `root=` argument exists so tests can point at a tempdir. It
    used to skip these checks, which meant internal callers had a
    weaker safety contract than the environment did -- and internal
    callers are the ones that run inside a `rmtree`.
    """
    if isinstance(raw, Path):
        text = str(raw)
    else:
        text = (raw or "").strip()
    if not text:
        raise UnsafeDataRoot(
            "no data root; refusing to erase narrator files without one")
    root = Path(text).expanduser()
    if not root.is_absolute():
        # Resolves against the process's working directory, which is
        # not a property anybody reviewing a recursive delete can see.
        raise UnsafeDataRoot("data root must be absolute, got %r" % text)
    root = root.resolve()
    if root == Path(root.anchor):
        raise UnsafeDataRoot("data root resolves to the filesystem root")
    if not root.is_dir():
        raise UnsafeDataRoot("data root %s is not a directory" % root)
    return root


def data_root() -> Path:
    """The validated root from the environment, read at call time."""
    return validate_root(os.getenv("DATA_DIR", ""))


def _validated_id(person_id: str) -> str:
    pid = (person_id or "").strip()
    if not _SAFE_PERSON_ID.match(pid):
        raise UnsafePersonId(
            "refusing to build a deletion path from an id of this shape")
    return pid


def _validated_segment(seg: Any) -> Optional[str]:
    s = str(seg or "").strip()
    return s if _SAFE_SEGMENT.match(s) else None


def safe_target(root: Path, parts: Iterable[str]) -> Path:
    """Resolve one target under `root`, refusing every symlink on the way.

    THE CHECK THAT MATTERS. `Path.resolve()` answers where a path ends
    up; it does not answer what it passed through. So

        stories-captured/A -> stories-captured/B

    resolves to a directory INSIDE the root, satisfies containment, and
    `rmtree` then deletes narrator B. Each component is `lstat`-ed
    instead, and a link is refused wherever it points -- outside the
    root or at another narrator inside it. Nothing is resolved and then
    trusted.
    """
    current = root
    walked: List[str] = []
    for raw in parts:
        seg = str(raw)
        if seg in ("", ".", "..") or "/" in seg or "\\" in seg or "\x00" in seg:
            raise UnsafeTarget("refusing path segment %r" % seg)
        current = current / seg
        walked.append(seg)
        try:
            st = current.lstat()
        except FileNotFoundError:
            # Nothing here yet. A component that does not exist cannot
            # be a link, and the remaining components cannot exist
            # either -- the caller treats an absent target as success.
            continue
        except OSError as exc:                          # pragma: no cover
            raise UnsafeTarget("cannot inspect %s: %s"
                               % ("/".join(walked), exc.__class__.__name__))
        import stat as _stat
        if _stat.S_ISLNK(st.st_mode):
            raise UnsafeTarget(
                "refusing to follow a symlink at %s; a link inside the data "
                "root can point at ANOTHER narrator's directory"
                % "/".join(walked))
    if current == root:
        raise UnsafeTarget("target IS the data root")
    return current


# ── The plan ────────────────────────────────────────────────────────────

def _fixed_plan(person_id: str) -> List[Dict[str, Any]]:
    out = [{"target": key, "parts": list(parts) + [person_id], "kind": "dir"}
           for key, parts in FIXED_TARGETS]
    out += [{"target": key, "parts": list(parts), "kind": "dir",
             "shared": True}
            for key, parts in SHARED_PURGE]
    return out


def _dynamic_plan(person_id: str, con: Any) -> List[Dict[str, Any]]:
    """Targets named by rows that are about to cascade away.

    FAILS CLOSED, corrected 2026-08-20. Every lane failure used to be
    logged and swallowed to `[]`, which meant a transient error on an
    INSTALLED table produced a short plan -- and the caller then
    destroyed the database authority those targets were named by. The
    files became unreachable and the answer said complete.

    A MISSING TABLE is the one tolerated case, because it means the
    feature was never installed in this deployment and there is
    genuinely nothing to plan. Anything else stops planning, and the
    caller refuses the deletion.
    """
    out: List[Dict[str, Any]] = []

    def _rows(sql: str, args: Tuple[Any, ...], lane: str):
        try:
            return con.execute(sql, args).fetchall()
        except Exception as exc:
            if "no such table" in str(exc).lower():
                logger.info("[erasure-plan] %s lane not installed here", lane)
                return []
            # An installed table that will not answer. Refusing costs
            # the operator a retry; continuing costs the narrator their
            # files with nothing left that knows their names.
            raise PlanIncomplete(
                "cannot plan the %s lane: %s" % (lane, exc.__class__.__name__))

    # Trip source documents: tickets, PDFs, receipts. Keyed by the
    # source row id, reachable only through the narrator's trips.
    for r in _rows(
            "SELECT s.id FROM trip_sources s JOIN trips t ON t.id = s.trip_id "
            "WHERE t.person_id = ?", (person_id,), "trip_sources"):
        sid = _validated_segment(r[0] if not isinstance(r, dict) else r["id"])
        if sid:
            out.append({"target": "trip_sources", "parts": ["trip_sources", sid],
                        "kind": "dir"})

    # Import staging: the picked originals and the incoming scratch
    # area, both keyed by batch id.
    for r in _rows("SELECT id FROM import_batch WHERE person_id = ?",
                   (person_id,), "import_batch"):
        bid = _validated_segment(r[0] if not isinstance(r, dict) else r["id"])
        if bid:
            out.append({"target": "import_staging",
                        "parts": ["import_staging", bid], "kind": "dir"})
            out.append({"target": "import_staging_incoming",
                        "parts": ["import_staging", ".incoming", bid],
                        "kind": "dir"})

    # Legacy REST transcript exports. These predate the archive store
    # and are plain narrator speech on disk.
    #
    # NAMED BY THE WRITER'S OWN FUNCTION, corrected 2026-08-20. This
    # used the UNSLUGGED conversation id and scheduled all three of
    # `interviews`, `bot_tests` and `sessions`. The writer slugs the id
    # and picks exactly ONE subfolder -- so a conversation id needing
    # slugging was written as one name and scheduled for deletion as
    # another, and the real file survived a "complete" erasure, while
    # two of the three scheduled paths were never this narrator's at
    # all and an unrelated file of the same name would have gone.
    from .chat_memory_paths import export_basenames
    for r in _rows("SELECT conv_id FROM sessions WHERE person_id = ?",
                   (person_id,), "sessions"):
        raw = r[0] if not isinstance(r, dict) else r["conv_id"]
        for sub, fname in export_basenames(str(raw or "")):
            if not _validated_segment(fname):
                continue
            out.append({"target": "agent_transcripts",
                        "parts": ["memory", "agents", sub, fname],
                        "kind": "file"})
    return out


def build_plan(person_id: str, con: Any = None) -> List[Dict[str, Any]]:
    """Everything to remove, computed while the database still knows.

    `con` is an open connection so the plan can be built inside the
    same transaction that is about to delete the rows.
    """
    pid = _validated_id(person_id)
    plan = _fixed_plan(pid)
    if con is not None:
        plan += _dynamic_plan(pid, con)
    return plan


# ── Execution ───────────────────────────────────────────────────────────

class EraseResult:
    """What actually happened on disk.

    `active_data_erased` and `historical_residue_present` are separate
    because they answer different questions, and collapsing them is how
    "complete" comes to mean "complete apart from the backups".
    """

    def __init__(self) -> None:
        self.removed: List[Dict[str, Any]] = []
        self.absent: List[str] = []
        self.failed: List[Dict[str, Any]] = []
        self.historical: List[Dict[str, Any]] = []

    @property
    def active_data_erased(self) -> bool:
        return not self.failed

    @property
    def historical_residue_present(self) -> bool:
        return bool(self.historical)

    @property
    def ok(self) -> bool:
        """Retained for callers that ask one question. It means the
        ACTIVE erasure finished; historical residue is reported
        separately and never hidden inside this flag."""
        return self.active_data_erased

    @property
    def files_removed(self) -> int:
        return sum(int(r.get("files") or 0) for r in self.removed)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "active_data_erased": self.active_data_erased,
            "historical_residue_present": self.historical_residue_present,
            "paths_removed": [r["path"] for r in self.removed],
            "files_removed": self.files_removed,
            "removed_detail": self.removed,
            "already_absent": self.absent,
            "failed": self.failed,
            "historical_residue": self.historical,
        }


def _count_files(path: Path) -> int:
    try:
        if path.is_file():
            return 1
        return sum(1 for p in path.rglob("*") if p.is_file())
    except OSError:                                     # pragma: no cover
        return 0


def _historical_inventory(root: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for key, parts in HISTORICAL_STORES:
        try:
            target = safe_target(root, parts)
        except UnsafeTarget:                            # pragma: no cover
            continue
        if not target.exists():
            continue
        out.append({
            "store": key,
            "path": "/".join(parts),
            "files": _count_files(target),
            "reason": "a shared point-in-time artefact that may contain this "
                      "narrator; rewriting it to remove one person destroys "
                      "its value as a restore point, so it is reported and "
                      "left alone",
        })
    return out


def execute_plan(plan: List[Dict[str, Any]], *,
                 root: Optional[Any] = None) -> EraseResult:
    """Remove everything in `plan`. Idempotent.

    An entry already gone is `absent`, not an error -- that is what
    makes a retry safe. A refusal or a failure is reported and the run
    continues, so one locked directory does not strand the rest.
    """
    res = EraseResult()
    base = validate_root(root if root is not None else os.getenv("DATA_DIR", ""))

    for entry in plan or []:
        key = entry.get("target") or "?"
        parts = [str(p) for p in (entry.get("parts") or [])]
        rel = "/".join(parts)
        try:
            target = safe_target(base, parts)
        except (UnsafeTarget, UnsafePersonId) as exc:
            logger.error("[erasure] refused %s: %s", rel, exc)
            res.failed.append({"target": key, "path": rel,
                               "reason": "refused", "detail": str(exc)})
            continue
        if not target.exists():
            res.absent.append(key)
            continue
        n = _count_files(target)
        try:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        except OSError as exc:
            logger.error("[erasure] %s failed: %s", rel, exc)
            res.failed.append({"target": key, "path": rel,
                               "reason": exc.__class__.__name__})
            continue
        if target.exists():                             # pragma: no cover
            res.failed.append({"target": key, "path": rel,
                               "reason": "still present after removal"})
            continue
        logger.info("[erasure] removed %s (%d file(s))", rel, n)
        res.removed.append({"target": key, "path": rel, "files": n})

    res.historical = _historical_inventory(base)
    return res


def erase_person_files(person_id: str, *,
                       root: Optional[Any] = None,
                       plan: Optional[List[Dict[str, Any]]] = None,
                       con: Any = None) -> EraseResult:
    """Plan (if not given one) and execute, for one narrator."""
    pid = _validated_id(person_id)
    return execute_plan(plan if plan is not None else build_plan(pid, con),
                        root=root)


def person_file_residue(person_id: str, *,
                        root: Optional[Any] = None,
                        plan: Optional[List[Dict[str, Any]]] = None
                        ) -> List[Dict[str, Any]]:
    """Every planned target still on disk. Read-only.

    Used to VERIFY an erasure rather than to trust its own report -- a
    harness that checked only the response body would have passed on
    the defect this module exists to close.
    """
    pid = _validated_id(person_id)
    base = validate_root(root if root is not None else os.getenv("DATA_DIR", ""))
    out: List[Dict[str, Any]] = []
    for entry in (plan if plan is not None else build_plan(pid)):
        parts = [str(p) for p in (entry.get("parts") or [])]
        try:
            target = safe_target(base, parts)
        except UnsafeTarget as exc:
            # A refused target is residue: it is still there and this
            # path will not remove it.
            out.append({"target": entry.get("target"), "path": "/".join(parts),
                        "files": 0, "reason": str(exc)})
            continue
        if target.exists():
            out.append({"target": entry.get("target"), "path": "/".join(parts),
                        "files": _count_files(target)})
    return out
