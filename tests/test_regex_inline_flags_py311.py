"""BUG-GUARDS-DEAD-ON-PY311-INLINE-FLAG-01 — build gate.

An inline regex flag that is not at position 0 — e.g. a SECOND "(?i)" before an
alternation — is a DeprecationWarning on Python 3.10 and a HARD re.error on
3.11+:

    re.error: global flags not at the start of the expression at position 99

_META_REASONING_RX in lori_response_guards.py had exactly that. The server runs
3.12, so the module died AT IMPORT. chat_ws imported the guards inside the
per-turn try/except whose job is "never break a turn on guard failure" — it
caught the ImportError, logged one WARNING, and passed every reply through
UNGUARDED.

So EVERY narrator-facing guard was silently dead in production — narrator_echo,
meta_response_leak, dangling_determiner, language_drift, the "I can see" block —
on every single turn. Live proof: Lori parroting the narrator's own sentence back
in the first person ("My father built the back porch himself. That's a specific
memory.") while the echo guard sat there working perfectly and never being called.

And the unit tests all PASSED, because the dev sandbox is 3.10.

This gate emulates 3.11+ strictness regardless of the interpreter running the
suite, so the bug cannot come back on a machine that merely warns.
"""
from __future__ import annotations

import importlib
import pathlib
import re
import sys
import unittest

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

_INLINE_FLAGS = ("(?i)", "(?s)", "(?m)", "(?x)", "(?a)", "(?u)", "(?L)")


def _offending_flag(pattern: str):
    """Return (flag, pos) for an inline flag that py3.11+ would reject.

    Search PAST index 0. The real bug had "(?i)" at position 0 AND AGAIN at 99;
    a naive find() returns the first (0), concludes "at the start", and waves
    the broken pattern through. My first version of this gate did exactly that
    and went green on the very bug it was written to catch.
    """
    for fl in _INLINE_FLAGS:
        pos = pattern.find(fl, 1)      # <- past the start, not at it
        if pos > 0:
            return fl, pos
    return None


class InlineFlagBuildGate(unittest.TestCase):
    def test_no_module_dies_under_py311_regex_rules(self):
        """Import every api module with a 3.11-strict re.compile installed."""
        real_compile = re.compile

        def strict_compile(pattern, flags=0):
            if isinstance(pattern, str):
                bad = _offending_flag(pattern)
                if bad:
                    raise re.error(
                        "global flags not at the start of the expression "
                        "at position %d (%s)" % (bad[1], bad[0]))
            return real_compile(pattern, flags)

        # Modules already in sys.modules are NOT re-executed, so the patched
        # re.compile would never see their patterns and the gate would pass on a
        # file that is definitely broken. (It did. This test was worthless until
        # the purge below — verified by re-injecting the original bug and
        # watching it go green.)
        for name in [n for n in list(sys.modules)
                     if n == "api" or n.startswith("api.")]:
            del sys.modules[name]

        re.compile = strict_compile
        try:
            broken = []
            for f in sorted((_SERVER_CODE / "api").rglob("*.py")):
                mod = (str(f.with_suffix(""))
                       .replace(str(_SERVER_CODE) + "/", "")
                       .replace("/", "."))
                if mod.endswith(".__init__"):
                    mod = mod[:-9]
                sys.modules.pop(mod, None)
                try:
                    importlib.import_module(mod)
                except re.error as exc:
                    broken.append("%s -> %s" % (mod, exc))
                except Exception:
                    # torch/fastapi/etc. not installed in every env — not ours.
                    pass
            self.assertEqual(
                broken, [],
                "these modules would die at import on Python 3.11+, silently "
                "disabling whatever they protect:\n  " + "\n  ".join(broken))
        finally:
            re.compile = real_compile

    def test_the_guards_module_specifically_loads(self):
        # The one that was actually broken. If this cannot import, every
        # narrator protection is off.
        mod = importlib.import_module("api.services.lori_response_guards")
        for fn in ("apply_response_guards", "detect_narrator_echo",
                   "repair_narrator_echo", "detect_meta_response_leak"):
            self.assertTrue(hasattr(mod, fn), fn)


class GuardsMustFailTheBootNotTheNarratorTest(unittest.TestCase):
    def test_chat_ws_imports_guards_at_module_scope(self):
        """A broken guards module must fail the BOOT, not every turn quietly.

        The lazy import lived inside the per-turn `except: pass-through`, so an
        ImportError was indistinguishable from a transient hiccup — which is
        exactly how this went unnoticed in production.
        """
        src = (_SERVER_CODE / "api" / "routers" / "chat_ws.py").read_text(
            encoding="utf-8")
        self.assertIn(
            "from ..services.lori_response_guards import (", src,
            "guards must be imported at module scope so a broken guards "
            "module refuses to boot instead of silently disabling protection")
        # and the lazy in-try import must be gone
        self.assertNotIn(
            "            from ..services.lori_response_guards import "
            "apply_response_guards as _apply_guards", src)


class TheLiveEchoIsActuallyCaughtTest(unittest.TestCase):
    """The guard was always correct — it was just never being called."""

    def test_first_person_parrot_is_blocked(self):
        from api.services.lori_response_guards import apply_response_guards
        narr = "My father built the back porch himself."
        asst = ("My father built the back porch himself. That's a specific "
                "memory. What do you remember about where you lived?")
        out, fired = apply_response_guards(
            assistant_text=asst, narrator_text=narr,
            recent_narrator_turns=[narr], target_language="en",
            surface="narrator")
        self.assertIn("narrator_echo", fired)
        self.assertNotIn("My father built the back porch himself.", out)
        self.assertTrue(out.strip())


if __name__ == "__main__":
    unittest.main()
