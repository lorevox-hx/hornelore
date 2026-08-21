"""Where a legacy chat-memory export lands, defined once.

WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01 — deletion integrity
(2026-08-20).

THE DEFECT THIS CLOSES. `api._save_chat_memory_fs()` slugs the
conversation id and picks ONE subfolder; the erasure plan used the
UNSLUGGED id and scheduled all three. So a conversation whose id
contained anything outside `[A-Za-z0-9._ -]` was written as
`weird_id.txt` and scheduled for deletion as `weird:id.txt` -- the real
file survived a "complete" erasure. And scheduling `interviews/`,
`bot_tests/` AND `sessions/` meant the plan named two paths that were
never this narrator's, where an unrelated file of the same name would
have been removed.

Two functions, imported by the writer and by the erasure planner, so
the two cannot drift again. Deliberately dependency-free: the planner
must not have to import `api.py` and drag the model stack in behind
it.
"""
from __future__ import annotations

import re

__all__ = ["MEMORY_SUBFOLDERS", "slug", "subfolder_for", "export_basenames"]

_UNSAFE = re.compile(r"[^A-Za-z0-9._ -]+")

#: Every subfolder the writer can choose. Enumerated so a reader can
#: see the whole set; `subfolder_for` picks exactly one of them.
MEMORY_SUBFOLDERS = ("interviews", "bot_tests")

#: The extensions the writer emits, in the order it writes them.
_EXTENSIONS = ("json", "txt", "jsonl")


def slug(s: str) -> str:
    """The filesystem-safe basename the writer uses.

    Byte-identical to `api._slug` -- that function now delegates here,
    so this IS the definition rather than a copy of it.
    """
    return _UNSAFE.sub("_", (s or "")).strip("_ ").replace(" ", "_") or "session"


def subfolder_for(conv_id: str) -> str:
    """The ONE directory this conversation's exports live in."""
    return "interviews" if (conv_id or "").lower().startswith("legacy") \
        else "bot_tests"


def export_basenames(conv_id: str):
    """`(subfolder, filename)` for every file the writer creates.

    The planner walks this instead of guessing, so a target it
    schedules is a file the writer could actually have written.
    """
    sub = subfolder_for(conv_id)
    base = slug(conv_id)
    return [(sub, "%s.%s" % (base, ext)) for ext in _EXTENSIONS]
