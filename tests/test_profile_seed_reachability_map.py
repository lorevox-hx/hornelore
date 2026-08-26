"""Phase 0 executable map: who promotes the pass, and who opens the walk.

WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 0 (2026-08-26).

**THIS PHASE CHANGES NO BEHAVIOUR.** It makes the present situation
executable, so that a later phase cannot move a promotion or a gate
without a test noticing, and so the defect is demonstrated rather than
described.

── THE DEFECT, STATED AS A RACE ──────────────────────────────────────

The ten-topic Profile Seed walk is preserved in the composer and is
ordinarily unreachable, and no single line is wrong. Four correct
behaviours compose into a skip:

  1. ordinary intake REQUIRES name, date of birth and place of birth;
  2. those three anchors are exactly what the chronology needs;
  3. a ready chronology promotes the browser `pass1 -> pass2a`;
  4. the composer emits the walk only for an identity-complete narrator
     whose browser-supplied `current_pass` is STILL `pass1`.

So the ordinary path supplies what closes its own gate, before the
narrator's first normal turn. A testing-only narrator without the three
anchors goes down identity mode instead, and identity mode mutually
excludes the walk. The workflow is present in source, covered as a
predicate, and proven by nothing.

── WHAT THIS FILE PINS ───────────────────────────────────────────────

* **Every promotion writer**, by file and line, including the direct
  `currentPass: "pass2a"` initialisation that is not a `setPass()` call
  and would be missed by grepping for the function alone.
* **The composer gate**, both halves: `current_pass == "pass1"` AND not
  identity mode.
* **All ten topics**, by name, so a later edit cannot quietly drop one.
* **The pass is browser-owned.** The server reads `current_pass` off the
  turn parameters and never writes it. That is the structural reason the
  spec calls for server-owned onboarding progress: today the only record
  of how far a narrator has got is a value the browser sends.

Run with:

    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_profile_seed_reachability_map
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
for _p in (str(_SERVER_CODE), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_COMPOSER = _SERVER_CODE / "api" / "prompt_composer.py"
_PREDICATES = _SERVER_CODE / "api" / "services" / "directive_predicates.py"
_UI = _REPO_ROOT / "ui"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


#: Every client site that moves a narrator to `pass2a`, verified against
#: the tree on 2026-08-26. `(path, needle)` — the line number is
#: deliberately NOT pinned, because line numbers churn on every edit and
#: a test that fails for churn gets muted. The SITE is what matters.
PROMOTION_WRITERS = [
    # The direct initialisation. Not a `setPass()` call, so a sweep that
    # greps only for the function misses it — which is why it is first.
    ("ui/hornelore1.0.html", 'currentPass: "pass2a"'),
    ("ui/js/app.js", 'if (state.session.currentPass === "pass1") setPass("pass2a");'),
    ("ui/js/app.js", 'setPass("pass2a");'),
    ("ui/js/chronology-accordion.js", 'if (typeof setPass === "function") setPass("pass2a");'),
    ("ui/js/interview.js", 'if(interviewMode==="chronological") setPass("pass2a");'),
    ("ui/js/interview.js", 'if(mode==="chronological") setPass("pass2a");'),
]

#: The ten topics, in the composer's own order and wording.
TEN_TOPICS = [
    "1. CHILDHOOD HOME",
    "2. SIBLINGS",
    "3. PARENTS' WORK",
    "4. HERITAGE",
    "5. EDUCATION",
    "6. MILITARY",
    "7. CAREER",
    "8. PARTNER",
    "9. CHILDREN",
    "10. LIFE STAGE",
]


class EveryPromotionWriterIsPinnedTests(unittest.TestCase):
    """Eight sites move a narrator out of `pass1`. All eight are here.

    ChatGPT's review supplied the list; it was verified line by line
    against the tree and then swept independently, because a list that
    is merely accepted is a list nobody checked.
    """

    def test_each_named_writer_still_exists(self):
        for rel, needle in PROMOTION_WRITERS:
            with self.subTest(site=rel, needle=needle[:48]):
                self.assertIn(needle, _read(_REPO_ROOT / rel),
                              f"a promotion writer vanished from {rel}; the "
                              f"map is stale and Phase 1 would plan against "
                              f"a tree that no longer exists")

    def test_the_total_count_of_writers_is_eight(self):
        """A COUNT, not just a presence check.

        Presence tests pass while somebody adds a ninth promotion
        nobody mapped. If this number changes, the map must change with
        it — that is the point of asserting it.
        """
        pattern = re.compile(
            r'setPass\(\s*["\']pass2a["\']\s*\)|currentPass\s*[:=]\s*["\']pass2a["\']')
        found = []
        for path in sorted(_UI.rglob("*")):
            if path.suffix not in (".js", ".html") or "vendor" in path.parts:
                continue
            for n, line in enumerate(_read(path).splitlines(), 1):
                if pattern.search(line):
                    found.append(f"{path.relative_to(_REPO_ROOT)}:{n}")
        self.assertEqual(
            len(found), 8,
            "the population of pass2a writers changed; update "
            "PROMOTION_WRITERS and the work order's map.\nFound:\n  "
            + "\n  ".join(found))

    def test_setPass_is_a_single_plain_setter(self):
        """No indirection, so the literal sites ARE the population.

        If `setPass` ever grows a branch, a caller could reach `pass2a`
        without the literal appearing at the call site, and the count
        above would silently under-report.
        """
        src = _read(_UI / "js" / "state.js")
        self.assertIn(
            'function setPass(p)  { if (state.session) state.session.currentPass = p; }',
            src,
            "setPass is no longer a one-line setter; indirect promotions "
            "are now possible and the map must account for them")

    def test_no_server_side_writer_exists(self):
        """The pass is BROWSER-OWNED, and that is the structural defect.

        The server reads `current_pass` off the turn parameters and
        never assigns it. So the only record of how far a narrator has
        got through onboarding is a value the client sends — which is
        why the spec calls for server-owned, restart-safe progress
        rather than a fix to any one promotion site.
        """
        composer = _read(_COMPOSER)
        self.assertIn('current_pass   = runtime71.get("current_pass", "pass1")', composer)
        for bad in ('current_pass = "pass2a"', "current_pass = 'pass2a'"):
            self.assertNotIn(bad, composer,
                             "the server now writes the pass; ownership moved "
                             "and the map is wrong")


class TheComposerGateIsPinnedTests(unittest.TestCase):
    """Both halves of the live gate, and all ten topics."""

    def setUp(self):
        self.src = _read(_COMPOSER)

    def test_the_walk_requires_pass1(self):
        self.assertIn('if current_pass == "pass1":', self.src)

    def test_the_walk_requires_identity_to_be_complete(self):
        """`elif not identity_mode:` encloses it.

        This is the half that makes a testing-only narrator — created
        without the three anchors — go down identity mode instead, which
        mutually excludes the walk. Both exclusions have to hold for the
        race to be a race.
        """
        i = self.src.index('if current_pass == "pass1":')
        window = self.src[max(0, i - 400):i]
        self.assertIn("elif not identity_mode:", window)

    def test_pass2a_is_the_mutually_exclusive_alternative(self):
        i = self.src.index('if current_pass == "pass1":')
        # The pass1 branch is long — the ten topics are string literals —
        # so the window has to clear it. Measured at ~7.5 KB; 12 KB gives
        # headroom without reaching into an unrelated branch.
        self.assertIn('elif current_pass == "pass2a":', self.src[i:i + 12000])

    def test_all_ten_topics_are_present_and_ordered(self):
        i = self.src.index('if current_pass == "pass1":')
        block = self.src[i:i + 6000]
        positions = []
        for topic in TEN_TOPICS:
            with self.subTest(topic=topic):
                self.assertIn(topic, block, f"topic {topic!r} is missing from "
                                            f"the preserved walk")
            positions.append(block.index(topic))
        self.assertEqual(positions, sorted(positions),
                         "the ten topics are no longer in their documented "
                         "order")

    def test_the_predicate_records_the_same_gate(self):
        """The inert directive registry carries the same condition.

        It is NOT the live gate — the registry is deliberately inert —
        but it must not drift from the composer, or a later activation
        would change behaviour while looking like a no-op.
        """
        src = _read(_PREDICATES)
        self.assertIn('return s.current_pass == "pass1" and not s.identity_mode', src)
