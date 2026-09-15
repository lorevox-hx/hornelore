"""The ONE runtime-root contract.

WO-LOREVOX-CLEAN-DATA-WORLD-01 (Phase 7) — Part B.

WHY THIS MODULE EXISTS. A reader audit taken 2026-09-14 found the application
resolving its own data root in at least seven independent places, and they did
not agree:

    silently default to a RELATIVE "data" (so the root follows the working
    directory of whatever started the process):
        api/db.py:58            — and mkdir'd it at import
        api/api.py:50           — and mkdir'd it at import
        api/archive.py:40
        utils/archive_paths.py:35

    refuse when DATA_DIR is unset:
        services/import_staging.py:107
        services/media_archive/storage.py:54
        services/photo_intake/storage.py:35

With DATA_DIR unset the product therefore did not fail — it HALF-WORKED. The
database was created under ./data/db/, memory archive and travel-doc paths
followed it there, and photos, media and import staging refused. A narrator
could be created and talked to while every photo of them was rejected.

`scripts/` re-derives the same formula again in at least five more places,
each from a comment rather than from code, and one of them defaults to a
DIFFERENT root and a DIFFERENT filename (scripts/archive/seed_interview_plan.py
:31-32 → /mnt/c/hornelore_data + hornelore.sqlite3). What that costs is on the
record: scripts/phase2_verify_ledger.py:60-62 records a pass that read the
repo-local data/db/lorevox.sqlite3 — "a stale file with different data — and
reported zero candidates for a narrator who has five" — and
tests/test_people_testing_only_persistence.py:110-116 records a suite that
created narrators in Chris's real database for the same reason.

THE CONTRACT, in one sentence: the runtime root is whatever DATA_DIR says, it
must be said absolutely, and if anything in the environment disagrees about
where the root is, the product refuses rather than choosing.

REFUSAL IS THE FEATURE. There is deliberately no fallback root here. A default
root is a guess about where somebody's life stories live, and the failure mode
of guessing wrong is not an error message — it is a second, silent, plausible
installation that accumulates real data nobody knows about.

This module reads the environment and the filesystem. It creates nothing,
writes nothing, and imports nothing from the rest of the application, so it is
safe to call before the application has resolved anything.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

__all__ = [
    "RootContractError",
    "DATA_DIR_ENV",
    "DB_NAME_ENV",
    "runtime_root",
    "db_name",
    "db_path",
    "coherence_problems",
    "assert_coherent_root",
    "describe_root",
]

DATA_DIR_ENV = "DATA_DIR"
DB_NAME_ENV = "DB_NAME"

# The default DB filename. This is a FILENAME inside a root the operator chose,
# not a root — naming a file is not the same as guessing a location.
DEFAULT_DB_NAME = "lorevox.sqlite3"

# Filenames that have been used as the Lorevox database on this project. A root
# containing more than one of them is ambiguous: `hornelore.sqlite3` was the
# WO-11 standalone-repo name and `lorevox.sqlite3` is the current default, and
# a root holding BOTH cannot say which one is the installation.
KNOWN_DB_NAMES = ("lorevox.sqlite3", "hornelore.sqlite3")

# Read by hornelore-serve.py:30 in preference to DATA_DIR. If the two disagree
# the UI server and the API server are serving two different installations.
LEGACY_ROOT_ENV = "HORNELORE_DATA_DIR"

# Advertised by .env.example but read by NOTHING in the application: db.py
# composes DATA_DIR/db/DB_NAME and never consults DB_PATH. An operator who sets
# it believes they have moved the database and has not, so tools that DO honour
# it read a different file from the server. Treated as a contradiction, not a
# setting.
UNREAD_DB_PATH_ENV = "DB_PATH"


class RootContractError(RuntimeError):
    """The runtime root is unset, ambiguous, or contradicted."""


def _raw(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def runtime_root() -> Path:
    """The configured root, or a refusal.

    Read from the environment on EVERY call rather than cached at import, for
    the reason services/import_staging.py:102-105 already gives: tests point
    DATA_DIR at a fresh temporary directory per case, and a cached value makes
    the second test read the first test's files. It is also why this module
    must never be the thing that mkdirs at import.
    """
    raw = _raw(DATA_DIR_ENV)
    if not raw:
        raise RootContractError(
            f"{DATA_DIR_ENV} is not set. Lorevox will not guess where narrator "
            f"data lives: set {DATA_DIR_ENV} to an absolute path.")
    root = Path(raw).expanduser()
    if not root.is_absolute():
        raise RootContractError(
            f"{DATA_DIR_ENV}={raw!r} is relative, so the root would depend on "
            "the working directory of whatever started the process — two "
            "launchers would resolve two different installations. Set an "
            "absolute path.")
    return root


def db_name() -> str:
    return _raw(DB_NAME_ENV) or DEFAULT_DB_NAME


def db_path(root: Optional[Path] = None) -> Path:
    """``<root>/db/<DB_NAME>`` — the composition api/db.py:58-63 performs.

    Stated once, here, so a caller never has to re-derive it from a comment.
    """
    return (root if root is not None else runtime_root()) / "db" / db_name()


def coherence_problems() -> List[str]:
    """Every way this environment is currently ambiguous about its root.

    Returns a list of human-readable problems — empty means coherent. Reports
    ALL of them rather than the first, because an operator fixing a mixed root
    one refusal at a time learns about it one restart at a time.
    """
    problems: List[str] = []

    try:
        root = runtime_root()
    except RootContractError as exc:
        return [str(exc)]

    # 1. A second root variable pointing somewhere else.
    legacy = _raw(LEGACY_ROOT_ENV)
    if legacy:
        legacy_path = Path(legacy).expanduser()
        if legacy_path != root:
            problems.append(
                f"{LEGACY_ROOT_ENV}={legacy_path} disagrees with "
                f"{DATA_DIR_ENV}={root}. hornelore-serve.py prefers "
                f"{LEGACY_ROOT_ENV}, so the UI server and the API server would "
                "serve two different installations. Unset one.")

    # 2. A DB_PATH the application does not read.
    stray = _raw(UNREAD_DB_PATH_ENV)
    if stray:
        stray_path = Path(stray).expanduser()
        composed = db_path(root)
        if stray_path != composed:
            problems.append(
                f"{UNREAD_DB_PATH_ENV}={stray_path} is set but the application "
                f"does not read it — it composes {composed} from "
                f"{DATA_DIR_ENV} and {DB_NAME_ENV}. Scripts that honour "
                f"{UNREAD_DB_PATH_ENV} would read a different database from "
                f"the server. Remove {UNREAD_DB_PATH_ENV} or make it agree.")

    # 3. More than one known database inside the root.
    db_dir = root / "db"
    if db_dir.is_dir():
        # EMPTY FILES DO NOT COUNT, and this is not a nicety — it is what
        # stops the gate refusing a perfectly good production root.
        #
        # /mnt/c/hornelore_data/db/ holds the live 21 MB hornelore.sqlite3 AND
        # a zero-byte lorevox.sqlite3 left behind on 2026-04-25. Counting the
        # stray made the root "ambiguous" and refused the boot. A zero-byte
        # file is not an installation: it has no schema, no narrators, and
        # nothing could have been written to it. Ambiguity means two
        # candidates that could each plausibly BE the installation.
        found = sorted(
            n for n in KNOWN_DB_NAMES
            if (db_dir / n).is_file() and (db_dir / n).stat().st_size > 0
        )
        if len(found) > 1:
            problems.append(
                f"{db_dir} contains {len(found)} Lorevox databases "
                f"({', '.join(found)}). This root cannot say which one is the "
                f"installation; {DB_NAME_ENV} currently selects "
                f"{db_name()!r}. Move the others out of the root before "
                "starting — do not delete them.")
        elif found and found[0] != db_name():
            problems.append(
                f"{db_dir} contains {found[0]!r} but {DB_NAME_ENV} selects "
                f"{db_name()!r}, which does not exist there. Starting would "
                "create a SECOND, empty database beside a populated one. "
                f"Set {DB_NAME_ENV}={found[0]!r} if that is the installation "
                "you meant.")

    return problems


def assert_coherent_root() -> Path:
    """Refuse to proceed unless the environment names exactly one root.

    Call this BEFORE anything durable — before the first connection, the first
    file, and before any module that resolves a root of its own is imported.
    Returns the root so a caller can use it without resolving it twice.
    """
    problems = coherence_problems()
    if problems:
        raise RootContractError(
            "Refusing to start: the runtime root is ambiguous.\n  - "
            + "\n  - ".join(problems))
    return runtime_root()


def describe_root() -> dict:
    """What this process believes, for logs and health output. Never raises."""
    out = {
        "data_dir_env": _raw(DATA_DIR_ENV) or None,
        "db_name": db_name(),
        "root": None,
        "db_path": None,
        "root_exists": None,
        "db_exists": None,
        "problems": [],
    }
    try:
        root = runtime_root()
    except RootContractError as exc:
        out["problems"] = [str(exc)]
        return out
    path = db_path(root)
    out["root"] = str(root)
    out["db_path"] = str(path)
    out["root_exists"] = root.is_dir()
    out["db_exists"] = path.is_file()
    out["problems"] = coherence_problems()
    return out
