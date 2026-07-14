"""BUG-GUARDS-DEAD-ON-PY311-INLINE-FLAG-01 — build gate.

An inline regex flag group that is not at position 0 — a SECOND "(?i)" before an
alternation, say — is a DeprecationWarning on Python 3.10 and a HARD re.error on
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

DESIGN OF THIS GATE (two hard-won constraints):

  * The strict-import sweep runs in a CLEAN SUBPROCESS. An earlier version did
    it in-process: purge sys.modules, monkey-patch re.compile, re-import every
    api module, and leave them there. That is the same shared-process global
    mutation that made 27 test modules stub `pydantic` into sys.modules and
    poison whatever ran after them. A gate against silent breakage must not
    itself be a source of silent breakage.

  * The detector must catch flag GROUPS, not just single letters — (?im), (?is),
    (?msx) are the same bug. Scoped groups like (?i:...) are legal anywhere and
    must NOT be flagged.
"""
from __future__ import annotations

import importlib
import pathlib
import re
import subprocess
import sys
import unittest

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

# A GLOBAL inline flag group: "(?" + one or more flag letters + ")".
# NOT "(?i:...)" (scoped — legal at any position) and not "(?:...)".
_GLOBAL_FLAG_RX = re.compile(r"\(\?[aiLmsux]+\)")


def _offending_flag(pattern: str):
    """(text, pos) of a global inline flag group past index 0, else None.

    Search PAST the start. The real bug had "(?i)" at position 0 AND AGAIN at
    99; a naive find() returns the first (0), concludes "at the start", and
    waves the broken pattern through. The first version of this gate did
    exactly that and went green on the very bug it was written to catch.
    """
    for m in _GLOBAL_FLAG_RX.finditer(pattern):
        if m.start() > 0:
            return m.group(0), m.start()
    return None


# Runs in its OWN interpreter. Nothing it imports can leak into the suite.
_SWEEP = r'''
import importlib, pathlib, re, sys

SERVER_CODE = sys.argv[1]
sys.path.insert(0, SERVER_CODE)

GLOBAL_FLAG_RX = re.compile(r"\(\?[aiLmsux]+\)")
real_compile = re.compile

def strict_compile(pattern, flags=0):
    if isinstance(pattern, str):
        for m in GLOBAL_FLAG_RX.finditer(pattern):
            if m.start() > 0:
                raise re.error(
                    "global flags not at the start of the expression at "
                    "position %d (%s)" % (m.start(), m.group(0)))
    return real_compile(pattern, flags)

re.compile = strict_compile

broken = []
for f in sorted(pathlib.Path(SERVER_CODE, "api").rglob("*.py")):
    mod = str(f.with_suffix("")).replace(SERVER_CODE + "/", "").replace("/", ".")
    if mod.endswith(".__init__"):
        mod = mod[:-9]
    try:
        importlib.import_module(mod)
    except re.error as exc:
        broken.append("%s -> %s" % (mod, exc))
    except Exception:
        pass          # torch/fastapi/etc. absent in some envs — not our concern

for b in broken:
    print("BROKEN " + b)
sys.exit(1 if broken else 0)
'''


class InlineFlagBuildGate(unittest.TestCase):
    def test_no_module_dies_under_py311_regex_rules(self):
        out = subprocess.run(
            [sys.executable, "-c", _SWEEP, str(_SERVER_CODE)],
            capture_output=True, text=True, timeout=180)
        broken = [l for l in out.stdout.splitlines() if l.startswith("BROKEN")]
        self.assertEqual(
            out.returncode, 0,
            "these modules would die at import on Python 3.11+, silently "
            "disabling whatever they protect:\n  " + "\n  ".join(broken))

    def test_sweep_leaves_no_api_modules_behind(self):
        """The gate must not be the thing that poisons the suite.

        Other tests in this file legitimately import api.services, so the
        assertion is not "no api modules exist" — it is "the SWEEP added
        none". Snapshot, run, compare.
        """
        before = {n for n in sys.modules if n.startswith("api")}
        self.test_no_module_dies_under_py311_regex_rules()
        after = {n for n in sys.modules if n.startswith("api")}
        self.assertEqual(
            after - before, set(),
            "the strict-import sweep leaked reloaded api modules into the "
            "parent test process — that is the sys.modules-mutation class "
            "this suite already got burned by")


class DetectorCatchesFlagGroupsTest(unittest.TestCase):
    def test_catches_the_original_bug(self):
        self.assertIsNotNone(_offending_flag(r"(?i)foo|(?i)bar"))

    def test_catches_combined_flag_groups(self):
        for pat in (r"(?i)foo|(?im)bar", r"(?i)a|(?is)b", r"^x|(?msx)y"):
            self.assertIsNotNone(_offending_flag(pat), pat)

    def test_allows_a_single_flag_at_the_start(self):
        self.assertIsNone(_offending_flag(r"(?i)foo|bar"))

    def test_allows_SCOPED_inline_groups_anywhere(self):
        # (?i:...) is legal at any position — must not be flagged.
        for pat in (r"foo|(?i:bar)", r"(?i:a)|(?s:b)", r"x(?im:y)z"):
            self.assertIsNone(_offending_flag(pat), pat)

    def test_allows_non_capturing_groups(self):
        self.assertIsNone(_offending_flag(r"foo(?:bar|baz)"))


class GuardsMustFailTheBootNotTheNarratorTest(unittest.TestCase):
    def test_chat_ws_imports_guards_at_module_scope(self):
        """A broken guards module must fail the BOOT, not every turn quietly.

        The lazy import lived inside the per-turn `except: pass-through`, so an
        ImportError was indistinguishable from a transient hiccup — which is
        exactly how this went unnoticed in production.
        """
        src = (_SERVER_CODE / "api" / "routers" / "chat_ws.py").read_text(
            encoding="utf-8")
        self.assertIn("from ..services.lori_response_guards import (", src)
        self.assertNotIn(
            "            from ..services.lori_response_guards import "
            "apply_response_guards as _apply_guards", src)

    def test_the_guards_module_loads(self):
        mod = importlib.import_module("api.services.lori_response_guards")
        for fn in ("apply_response_guards", "detect_narrator_echo",
                   "repair_narrator_echo", "detect_meta_response_leak"):
            self.assertTrue(hasattr(mod, fn), fn)


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
