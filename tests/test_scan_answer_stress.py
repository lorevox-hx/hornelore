"""scan_answer() stress test — task #325, parent-session blocker.

Context
-------
chat_ws.py L540-565 wraps scan_answer() in try/except + a default-safe
fallback that forces turn_mode='interview' on failure (so the LLM-side
ACUTE SAFETY RULE in prompt_composer.py:108-193 still fires). The
fallback was landed in #324 after 2026-04-29 code review caught a
silent-skip gap.

The fallback only matters if scan_answer() ACTUALLY RAISES on
pathological inputs. This test proves the assumption: it sends ~15
pathological texts directly to scan_answer() and confirms each call
either returns None or a SafetyResult. Never raises.

If any pathological input raises, the failure surfaces here BEFORE a
narrator session does — and we know which input class to harden in
safety.py.

Coverage classes
----------------
  1. Empty / whitespace-only
  2. Unicode-heavy (smart quotes, emoji, RTL)
  3. Control characters
  4. Mixed STT garbage (uncommon punctuation patterns)
  5. Pathological lengths (very long, single-word repeats)
  6. Regex-pattern collision attempts (text that looks like regex
     metachars)
  7. Edge-case sentence boundaries (no punctuation, only periods,
     only ellipses)
  8. Real distress text (must trigger, not crash)
  9. Mixed-language text (English + non-English)
 10. Null bytes embedded in string (Python str supports them, scanners
     sometimes don't)

Each test is a single deterministic assertion: scan_answer(text) does
not raise. Triggered/not-triggered is incidental — what matters is
that the deterministic safety layer NEVER becomes the reason a chat
turn breaks.

Usage:
    python tests/test_scan_answer_stress.py
    python -m unittest tests.test_scan_answer_stress
    pytest tests/test_scan_answer_stress.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Add server/code to import path so api.safety resolves.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

# scan_answer / SafetyResult come from api.safety which depends on
# pydantic. In environments without pydantic (e.g. minimal sandboxes),
# the import is skipped and the runtime tests are marked skipped; the
# StructuralSanityTest at the bottom still runs because it only reads
# chat_ws.py as text.
try:
    from api.safety import scan_answer, SafetyResult  # noqa: E402
    _SAFETY_IMPORT_OK = True
    _SAFETY_IMPORT_ERR: str | None = None
except Exception as _imp_exc:  # broad on purpose — covers missing deps
    scan_answer = None  # type: ignore[assignment]
    SafetyResult = None  # type: ignore[assignment]
    _SAFETY_IMPORT_OK = False
    _SAFETY_IMPORT_ERR = repr(_imp_exc)


def _scan(text):
    """Wrapper that asserts scan_answer doesn't raise + returns the
    expected None | SafetyResult shape."""
    if not _SAFETY_IMPORT_OK:
        raise unittest.SkipTest(f"api.safety import failed: {_SAFETY_IMPORT_ERR}")
    result = scan_answer(text)
    assert result is None or isinstance(result, SafetyResult), (
        f"scan_answer returned unexpected type: {type(result)} for input "
        f"len={len(text) if text else 0}"
    )
    return result


class EmptyAndWhitespaceTest(unittest.TestCase):
    def test_empty_string(self):
        self.assertIsNone(_scan(""))

    def test_none_input(self):
        # scan_answer's docstring says it handles non-truthy input.
        # The chat_ws wrapper guards against None explicitly, but
        # scan_answer itself should also tolerate.
        self.assertIsNone(_scan(None))

    def test_whitespace_only(self):
        self.assertIsNone(_scan("   \n\t  \r\n"))

    def test_punctuation_only(self):
        result = _scan("...???!!!---")
        # May return None (no real sentence) or SafetyResult — both fine
        self.assertTrue(result is None or isinstance(result, SafetyResult))


class UnicodeHeavyTest(unittest.TestCase):
    def test_smart_quotes_and_curly_apostrophes(self):
        _scan("She said, “I’m fine.”")  # smart quotes
        _scan("‘Don’t worry,’ he said.")  # curly apostrophes

    def test_emoji_dense(self):
        _scan("\U0001f600\U0001f602\U0001f923\U0001f60d\U0001f44d hello there")

    def test_rtl_text(self):
        # Hebrew + Arabic — RTL chars sometimes confuse sentence splitters
        _scan("Hello שלום عالم world")

    def test_combining_marks(self):
        # Decomposed accented chars (NFD form)
        _scan("café vs café vs café")

    def test_zalgo_text(self):
        # Stack of combining marks — known to break naive parsers
        _scan("h́̂̃é̂̃ĺ̂̃ĺ̂̃ó̂̃")


class ControlCharactersTest(unittest.TestCase):
    def test_null_bytes(self):
        # Python strings support null; scanners sometimes don't
        _scan("hello\x00world")

    def test_bell_backspace_etc(self):
        _scan("alert\x07backspace\x08vt\x0bff\x0c")

    def test_zero_width_chars(self):
        _scan("hello​world‌with‍zero﻿width")

    def test_form_feed_in_middle(self):
        _scan("first sentence.\x0csecond sentence.")


class STTGarbageTest(unittest.TestCase):
    def test_repeated_dashes(self):
        _scan("uh---I---don't---really---know")

    def test_only_filler_words(self):
        _scan("um uh er ah hmm uh um")

    def test_run_on_no_punctuation(self):
        _scan(
            "so we got there and i mean it was fine but then later there was "
            "a thing and you know how those go anyway"
        )

    def test_random_capitalization(self):
        _scan("HeLLo WoRld THIs Is A tEsT")


class PathologicalLengthTest(unittest.TestCase):
    def test_single_char(self):
        _scan("a")

    def test_one_word_repeated(self):
        _scan("hello " * 500)  # 3000 chars of "hello "

    def test_very_long_paragraph(self):
        # 50 KB single paragraph
        _scan("This is a sentence. " * 2500)

    def test_huge_no_sentence_boundaries(self):
        # 10K chars, no period — sentence splitter must not loop
        _scan("a" * 10000)


class RegexCollisionTest(unittest.TestCase):
    """Text that looks like regex metachars must not break the
    safety pattern engine (it uses re.search internally; any literal
    metachar in user input must be treated as data, not pattern)."""

    def test_metachars_dense(self):
        _scan(r"^.*+?{[]\|()$")

    def test_pattern_lookalike(self):
        _scan(r"\b(suicide|kill)\b matches via regex")

    def test_unbalanced_brackets(self):
        _scan("[[[ unbalanced ((( brackets {{{ everywhere")


class SentenceBoundaryEdgeTest(unittest.TestCase):
    def test_no_terminator(self):
        _scan("this has no terminator at all just text")

    def test_only_ellipses(self):
        _scan("first... second... third...")

    def test_period_runs(self):
        _scan("a.b.c.d.e.f.g.h.i.j.k.l.m.n.o.p")

    def test_question_marks_only(self):
        _scan("???")


class RealDistressTextTest(unittest.TestCase):
    """Text that SHOULD trigger the safety scanner. Must not crash;
    must return a SafetyResult.triggered=True."""

    def test_explicit_acute_ideation(self):
        result = _scan("I want to kill myself.")
        self.assertIsNotNone(result)
        self.assertTrue(result.triggered)

    def test_implicit_distress(self):
        # Whether this triggers depends on safety.py patterns; what
        # matters is no crash. Returning None or a SafetyResult is fine.
        _scan("I just feel so empty all the time, like nothing matters anymore.")


class MixedLanguageTest(unittest.TestCase):
    def test_english_plus_spanish(self):
        _scan("Hello there, mi amigo, como estas?")

    def test_english_plus_chinese(self):
        _scan("I learned the word 你好 which means hello.")


class StructuralSanityTest(unittest.TestCase):
    """Confirm the chat_ws default-safe fallback path exists in source.
    Ride this as a regression guard so future refactors don't silently
    drop the fallback."""

    def test_chat_ws_has_safety_scan_failed_flag(self):
        chat_ws = _REPO_ROOT / "server" / "code" / "api" / "routers" / "chat_ws.py"
        text = chat_ws.read_text(encoding="utf-8")
        self.assertIn(
            "_safety_scan_failed",
            text,
            "chat_ws.py default-safe fallback flag missing — task #324 regression",
        )
        self.assertIn(
            "[chat_ws][safety][default-safe]",
            text,
            "chat_ws.py default-safe log marker missing — task #324 regression",
        )

    def test_chat_ws_forces_interview_mode_on_scan_failure(self):
        chat_ws = _REPO_ROOT / "server" / "code" / "api" / "routers" / "chat_ws.py"
        text = chat_ws.read_text(encoding="utf-8")
        self.assertIn(
            'params["turn_mode"] = "interview"',
            text,
            "chat_ws.py default-safe must force turn_mode=interview on scan failure",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
