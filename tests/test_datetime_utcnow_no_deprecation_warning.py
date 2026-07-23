"""Regression gate: no `datetime.utcnow()` in production code.

Locks the 2026-07-23 sweep (BUG-DEPRECATION-DATETIME-UTCNOW-01).

Two attack surfaces:

  * **Runtime** — call the timestamp-producing helpers on the sweep's
    target modules under ``warnings.simplefilter('error',
    DeprecationWarning)``. If anyone re-introduces
    ``datetime.utcnow()`` on a hot path, this test fails LOUD because
    the deprecation warning becomes an exception.

  * **Static** — scan the 8 target files' source for the literal
    substring ``datetime.utcnow(`` in non-comment lines. Catches
    regressions on cold paths that runtime coverage might miss
    (unused code, error branches, functions we don't hit in the
    fast test).

Under Python 3.10/3.11 the deprecation warning doesn't fire (the
runtime API was still supported). Under 3.12+ the warning is active
and this test enforces the fix. The static check runs on every
Python version — it doesn't depend on the interpreter's warning
behavior.
"""
from __future__ import annotations

import re
import sys
import warnings
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

# Files touched by the 2026-07-23 sweep — the whole "does this file
# hold a call to datetime.utcnow()?" question is settled per file.
# Any addition (new module using utcnow) is caught by the runtime
# check when its helper fires. Any re-introduction on an existing
# module is caught by both the runtime and static checks.
_SWEPT_FILES = (
    "server/code/api/api.py",
    "server/code/api/archive.py",
    "server/code/api/db.py",
    "server/code/api/prompt_composer.py",
    "server/code/api/routers/narrator_state.py",
    "server/code/api/routers/projection.py",
    "server/code/api/routers/questionnaire.py",
    "server/code/api/services/projection_writer.py",
    "server/code/api/services/story_preservation.py",
)


def _strip_python_comments_and_strings(source: str) -> str:
    """Return `source` with # comments AND string/docstring content
    stripped, so a regex match on the survivor is a real code
    reference — not a comment that documents the OLD bug shape or a
    docstring that quotes the deprecation message.

    Cheap tokenize pass. Preserves whitespace and newline structure
    so error messages can still point at line numbers usefully.
    """
    import tokenize
    import io

    out_chars = []
    prev_end = (1, 0)
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except tokenize.TokenizeError:
        # Fallback: strip # to end-of-line only. Slightly less strict
        # but never worse than the pre-sweep behavior.
        return re.sub(r"#[^\n]*", "", source)

    for tok in tokens:
        # Skip comment + string tokens; keep everything else.
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            # Preserve line/col structure by replacing with spaces
            # (so line numbers in downstream error messages are
            # unchanged).
            (sr, sc), (er, ec) = tok.start, tok.end
            if sr == er:
                out_chars.append(" " * (ec - sc))
            else:
                # Multi-line string — replace with same-shape blanks
                # per line.
                lines = tok.string.split("\n")
                filler = []
                for i, line in enumerate(lines):
                    if i == 0:
                        filler.append(" " * len(line))
                    else:
                        filler.append("\n" + " " * len(line))
                out_chars.append("".join(filler))
        else:
            out_chars.append(tok.string)
    return "".join(out_chars)


class NoDatetimeUtcnowInSwepFilesTest(unittest.TestCase):
    """Static: none of the 8 swept files may hold a live call to
    datetime.utcnow(). Comments + docstrings that reference the OLD
    bug shape (e.g. the age_arithmetic.py 'Patch G' historical
    comment) are exempt via the token-strip pass."""

    def test_no_utcnow_call_in_any_swept_file(self):
        offenders = []
        pat = re.compile(r"\bdatetime\.utcnow\s*\(")
        for rel in _SWEPT_FILES:
            path = _REPO_ROOT / rel
            self.assertTrue(path.exists(), f"missing swept file: {rel}")
            src = path.read_text(encoding="utf-8")
            cleaned = _strip_python_comments_and_strings(src)
            for line_no, line in enumerate(cleaned.splitlines(), start=1):
                if pat.search(line):
                    offenders.append(f"{rel}:{line_no}: {line.strip()[:120]}")
        if offenders:
            self.fail(
                "The 2026-07-23 sweep locked these files against "
                "datetime.utcnow() (deprecated in Python 3.12+). "
                "One or more regressed:\n" + "\n".join(offenders)
                + "\n\nUse: datetime.now(timezone.utc).replace("
                "tzinfo=None)\n"
                "which produces byte-identical output (needed because "
                "operator_stack_dashboard.py and stack_monitor.py "
                "still parse timestamps with a naive strptime format).")


class NoDeprecationWarningOnHotHelpersTest(unittest.TestCase):
    """Runtime: call the sweep's most-hit timestamp helpers under
    ``warnings.simplefilter('error', DeprecationWarning)`` and
    assert nothing fires. If Python re-implements the deprecation
    strictness in a future release, this test still passes because
    the code no longer uses the deprecated API.
    """

    def _hot_helpers(self):
        """Return an iterable of (label, callable-that-returns-a-str).
        Each helper is called once per test invocation. Adding a new
        callable here also covers it under the DeprecationWarning
        strictness gate."""
        from api import db as _db
        from api import archive as _archive
        from api.services import story_preservation as _sp
        return (
            ("db._now_iso", _db._now_iso),
            ("archive._now_iso", _archive._now_iso),
            ("story_preservation._now_iso", _sp._now_iso),
        )

    def test_hot_helpers_produce_no_deprecation_warning(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            for label, fn in self._hot_helpers():
                try:
                    result = fn()
                except DeprecationWarning as exc:
                    self.fail(
                        f"{label}() raised DeprecationWarning: {exc}. "
                        "The 2026-07-23 sweep should have replaced its "
                        "datetime.utcnow() call with "
                        "datetime.now(timezone.utc).replace(tzinfo=None).")
                # Sanity: helpers must still return a string that
                # SQLite can store. Byte-stability with the pre-sweep
                # naive-ISO format matters because two downstream
                # parsers (operator_stack_dashboard, stack_monitor)
                # use a strict naive strptime format that would
                # reject a "+00:00" suffix.
                self.assertIsInstance(result, str)
                # No tz suffix on the wire — confirms the .replace(
                # tzinfo=None) call is in place.
                self.assertNotIn("+00:00", result,
                                 f"{label}() leaked +00:00 suffix into "
                                 "ISO string; strict-format downstream "
                                 "parsers would fail.")
                self.assertFalse(result.endswith("Z"),
                                 f"{label}() unexpectedly appended 'Z'.")


if __name__ == "__main__":
    unittest.main()
