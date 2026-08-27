"""Phase 0 executable map: who promotes the pass, and who opens the walk.

WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 0 (2026-08-26).

**THIS PHASE CHANGES NO BEHAVIOUR.** It makes the present situation
executable, so a later phase cannot move a promotion or a gate without a
test noticing.

── HOW TO RUN THIS ───────────────────────────────────────────────────

    PYTHONPATH=server/code python3 -m unittest tests.test_profile_seed_reachability_map

**NOT `.venv/bin/python`.** An earlier version of this header said to use
it, which was wrong and was caught in review after the module failed to
import in a clean checkout. `CLAUDE.md` records the reason under
**Environment**: `.venv` is Python 3.10.12 with NO fastapi, so any module
whose import chain reaches the app skips or dies there. This particular
file happens to import cleanly under `.venv` — it only reads source text
— but its sibling
`tests/test_profile_seed_ordinary_intake_reachability.py` does not, and
publishing two different run commands for one phase invites the wrong
one to be copied. One command, and it is the interpreter that has
fastapi.

── THE DEFECT, STATED AS A RACE ──────────────────────────────────────

The ten-topic Profile Seed walk is preserved in the composer and is
ordinarily unreachable, and no single line is wrong. Correct behaviours
compose into a skip:

  1. ordinary intake REQUIRES name, date of birth and place of birth;
  2. those three anchors are exactly what the chronology needs;
  3. a ready chronology promotes the browser `pass1 -> pass2a` — and a
     narrator classified "ready" is initialised **directly into
     `pass2a`**, never passing through `pass1` at all;
  4. the composer emits the walk only for an identity-complete narrator
     whose browser-supplied `current_pass` is STILL `pass1`.

── WHAT THIS FILE PINS ───────────────────────────────────────────────

* **Eight DISTINCT promotion sites**, each by enclosing function, plus a
  per-file occurrence count. An earlier version listed six `(file,
  needle)` patterns and relied on a global count of eight — which proved
  eight literals existed somewhere, not that these eight sites survived.
  Two `app.js` patterns each matched two different functions, so a site
  could vanish and be replaced elsewhere with the suite still green.
* **The composer gate**, both halves.
* **All ten topics**, by name and in order.
* **Pass ownership**, swept across the WHOLE of `server/code/api` rather
  than one file — the previous version examined only `prompt_composer.py`
  and could not support the claim it made.
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
_API = _SERVER_CODE / "api"
_UI = _REPO_ROOT / "ui"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


#: Matches any client write that lands a narrator in `pass2a`.
_PROMOTION_RE = re.compile(
    r'setPass\(\s*["\']pass2a["\']\s*\)|currentPass\s*[:=]\s*["\']pass2a["\']')

#: Finds the nearest preceding function name, for a stable site id.
_FUNCTION_RE = re.compile(
    r'(?:async\s+)?function\s+([A-Za-z_$][\w$]*)'
    r'|([A-Za-z_$][\w$]*)\s*[:=]\s*(?:async\s*)?function')

#: THE EIGHT SITES, each identified by its enclosing function rather than
#: by a line number (line numbers churn; a test that fails for churn gets
#: muted) and rather than by the matched text alone (two of these share
#: identical text and would collapse into one entry).
#:
#: `(path, enclosing_context, matched_text)`
PROMOTION_SITES = [
    # 1. THE DIRECT READY-NARRATOR INITIALISATION. Not a `setPass()` call,
    #    so a sweep for the function alone misses it. It is also the most
    #    direct expression of the defect: a narrator classified "ready" is
    #    seated in `pass2a` AND `identityPhase: "complete"` in the same
    #    object literal, so they never occupy `pass1` for even one turn.
    ("ui/hornelore1.0.html", 'openState === "ready"', 'currentPass: "pass2a"'),
    # 2-5. Four distinct functions in app.js, two sharing identical text.
    ("ui/js/app.js", "_hydrateChronologyFromServer",
     'if (state.session.currentPass === "pass1") setPass("pass2a");'),
    ("ui/js/app.js", "selectEra", 'setPass("pass2a");'),
    ("ui/js/app.js", "loadPerson",
     'if (state.session.currentPass === "pass1") setPass("pass2a");'),
    ("ui/js/app.js", "initTimelineSpine", 'setPass("pass2a");'),
    # 6.
    ("ui/js/chronology-accordion.js", "crJumpToEra",
     'if (typeof setPass === "function") setPass("pass2a");'),
    # 7-8.
    ("ui/js/interview.js", "renderRoadmap",
     'if(interviewMode==="chronological") setPass("pass2a");'),
    ("ui/js/interview.js", "setInterviewMode",
     'if(mode==="chronological") setPass("pass2a");'),
]

#: Expected promotion writes per file. Catches a site being deleted from
#: one file and added to another, which a total-only count cannot see.
PROMOTIONS_PER_FILE = {
    "ui/hornelore1.0.html": 1,
    "ui/js/app.js": 4,
    "ui/js/chronology-accordion.js": 1,
    "ui/js/interview.js": 2,
}

#: The ten topics, in the composer's own order and wording.
TEN_TOPICS = [
    "1. CHILDHOOD HOME", "2. SIBLINGS", "3. PARENTS' WORK", "4. HERITAGE",
    "5. EDUCATION", "6. MILITARY", "7. CAREER", "8. PARTNER", "9. CHILDREN",
    "10. LIFE STAGE",
]


def _sites_in(rel: str):
    """Every promotion in one file, as `(enclosing_context, text)`."""
    lines = _read(_REPO_ROOT / rel).splitlines()
    out = []
    for i, line in enumerate(lines):
        if not _PROMOTION_RE.search(line):
            continue
        ctx = "<module>"
        for j in range(i, max(-1, i - 400), -1):
            m = _FUNCTION_RE.search(lines[j])
            if m:
                ctx = m.group(1) or m.group(2)
                break
        out.append((ctx, line.strip(), i + 1))
    return out


class EightDistinctPromotionSitesTests(unittest.TestCase):
    """Eight sites, each pinned individually.

    ChatGPT's review supplied the list of eight; it was verified line by
    line and swept independently. The review then caught that the FIRST
    version of this file pinned only six patterns — the count was right
    and the pinning was not.
    """

    def test_each_of_the_eight_sites_is_present_in_its_own_function(self):
        for rel, ctx, text in PROMOTION_SITES:
            with self.subTest(site=f"{rel}::{ctx}"):
                if rel.endswith(".html"):
                    # The HTML site sits in an inline branch, not a named
                    # function, so it is anchored on the branch condition
                    # and the adjacency that makes it meaningful.
                    src = _read(_REPO_ROOT / rel)
                    self.assertIn(ctx, src)
                    i = src.index(ctx)
                    window = src[i:i + 900]
                    self.assertIn(text, window,
                                  "the ready-narrator branch no longer seats "
                                  "the narrator in pass2a")
                    self.assertIn('identityPhase: "complete"', window,
                                  "the ready branch no longer marks identity "
                                  "complete; the defect's shape has changed")
                    continue
                found = [(c, t) for c, t, _ in _sites_in(rel)]
                self.assertIn(
                    (ctx, text), found,
                    f"no promotion in {ctx}() of {rel}; the map is stale and "
                    f"Phase 1 would plan against a tree that moved.\n"
                    f"Present: {found}")

    def test_the_per_file_counts_are_unchanged(self):
        """Per-file, not just a global total.

        A global count of eight stays eight when a site is deleted from
        one file and a new one appears in another. Per-file counts do
        not.
        """
        for rel, expected in PROMOTIONS_PER_FILE.items():
            with self.subTest(file=rel):
                self.assertEqual(
                    len(_sites_in(rel)), expected,
                    f"{rel} promotion count changed; update PROMOTION_SITES "
                    f"and the work order's map.\nFound: {_sites_in(rel)}")

    def test_no_promotion_exists_outside_the_mapped_files(self):
        """The whole client tree, so a ninth site cannot hide elsewhere."""
        stray = []
        for path in sorted(_UI.rglob("*")):
            if path.suffix not in (".js", ".html") or "vendor" in path.parts:
                continue
            rel = str(path.relative_to(_REPO_ROOT)).replace("\\", "/")
            if rel in PROMOTIONS_PER_FILE:
                continue
            for n, line in enumerate(_read(path).splitlines(), 1):
                if _PROMOTION_RE.search(line):
                    stray.append(f"{rel}:{n}")
        self.assertEqual(stray, [],
                         "a promotion appeared in an unmapped file")

    def test_the_eight_sites_are_eight_distinct_functions(self):
        contexts = {(rel, ctx) for rel, ctx, _ in PROMOTION_SITES}
        self.assertEqual(len(PROMOTION_SITES), 8)
        self.assertEqual(len(contexts), 8,
                         "two mapped sites share a context, so one of them "
                         "is not independently pinned")

    def test_setPass_is_a_single_plain_setter(self):
        """No indirection, so the literal sites ARE the population."""
        self.assertIn(
            'function setPass(p)  { if (state.session) state.session.currentPass = p; }',
            _read(_UI / "js" / "state.js"),
            "setPass is no longer a one-line setter; indirect promotions "
            "are now possible and the map must account for them")


class ThePassIsBrowserOwnedTests(unittest.TestCase):
    """Swept across the whole server API tree.

    The previous version of this claim examined `prompt_composer.py`
    alone and asserted "the server never writes the pass" — a statement
    about the server proved from one file. The sweep below is what the
    claim actually needs.
    """

    def test_no_server_file_assigns_a_pass_value(self):
        writer = re.compile(
            r'\bcurrent_pass\b\s*=\s*["\'](?:pass1|pass2a|pass2b)["\']')
        offenders = []
        for path in sorted(_API.rglob("*.py")):
            for n, line in enumerate(_read(path).splitlines(), 1):
                if writer.search(line):
                    offenders.append(
                        f"{path.relative_to(_REPO_ROOT)}:{n}  {line.strip()[:70]}")
        self.assertEqual(
            offenders, [],
            "the server now writes the pass; ownership moved and the work "
            "order's premise — that onboarding progress has no server-side "
            "owner — needs revisiting.\n  " + "\n  ".join(offenders))

    def test_the_server_only_reads_what_the_browser_sends(self):
        self.assertIn('current_pass   = runtime71.get("current_pass", "pass1")',
                      _read(_COMPOSER))

    def test_no_persistence_layer_stores_a_pass(self):
        """Nothing writes it to the database either.

        If a column existed, progress would already have a durable
        owner and the lane would be a different shape.
        """
        db_src = _read(_API / "db.py")
        for marker in ("current_pass", "currentPass"):
            self.assertNotIn(
                marker, db_src,
                f"db.py now references {marker!r}; a persistence path may "
                f"have appeared")


class TheComposerGateIsPinnedTests(unittest.TestCase):
    """Both halves of the live gate, and all ten topics."""

    def setUp(self):
        self.src = _read(_COMPOSER)

    def test_the_walk_requires_pass1(self):
        self.assertIn('elif current_pass == "pass1":', self.src)

    def test_the_walk_requires_identity_to_be_complete(self):
        """The legacy pass-1 branch still sits under the identity gate.

        *(Widened from 400 characters to 3,000 on 2026-08-26, and the
        marker gained its `elif`. Phase 2 step 4 inserted an onboarding
        suppression branch plus its rationale between the two, so the
        gate was unchanged and the DISTANCE was not — this pin failed on
        a comment.*

        *That is the cost of measuring structure by character
        proximity, and it is worth naming rather than quietly widening:
        the number has no meaning, so it will drift again. The claim
        being pinned is "the pass-1 branch is nested inside
        `elif not identity_mode:`", which a real parse would answer
        exactly. Left as a proximity check because Phase 0 is accepted
        and this lane should not rewrite its instrument mid-flight;
        recorded here so the next reader knows the number is arbitrary
        and the claim is not.)*
        """
        i = self.src.index('elif current_pass == "pass1":')
        self.assertIn("elif not identity_mode:", self.src[max(0, i - 3000):i])

    def test_the_legacy_branch_is_suppressed_for_enrolled_narrators(self):
        """Phase 2 step 4: enrolled narrators get the canonical section
        instead, so the two topic lists can never both render."""
        i = self.src.index('elif current_pass == "pass1":')
        window = self.src[max(0, i - 3000):i]
        self.assertIn("if profile_seed_onboarding_active(runtime71):", window)

    def test_pass2a_is_the_mutually_exclusive_alternative(self):
        i = self.src.index('elif current_pass == "pass1":')
        # The pass-1 branch used to be long because the ten questions
        # were string literals here. They are generated from the registry
        # now, so the branch is short — but the window is left wide, since
        # a window that is too big only risks a false PASS on a claim the
        # next test makes exactly.
        self.assertIn('elif current_pass == "pass2a":', self.src[i:i + 12000])

    def test_all_ten_topics_are_present_and_ordered(self):
        """Pinned against the RENDERED list, not the source.

        *(This asserted the ten topic labels were string literals inside
        the pass-1 branch. Phase 2 step 4 generates them from
        `TOPIC_REGISTRY` — precisely so the composer stops holding a
        second hand-written order — so the literals are gone and this
        pin failed on the improvement it was watching for.*

        *The CLAIM is still exactly right: all ten, in documented order,
        reach the historical narrator's prompt. It is now checked
        against what is rendered, which is what the claim was always
        about; the literals were only ever a proxy for it.)*
        """
        from api.prompt_composer import _legacy_profile_seed_question_list
        rendered = _legacy_profile_seed_question_list()
        positions = []
        for topic in TEN_TOPICS:
            with self.subTest(topic=topic):
                self.assertIn(topic, rendered)
            positions.append(rendered.index(topic))
        self.assertEqual(positions, sorted(positions),
                         "the ten topics are no longer in documented order")

    def test_the_composer_holds_no_topic_literals(self):
        """The other half, and the reason the test above changed shape.

        Work order §4.1: the composer renders from the registry and
        "must not keep a second hand-written order". A literal here is
        that second order.
        """
        for topic in TEN_TOPICS:
            with self.subTest(topic=topic):
                self.assertNotIn(
                    topic, self.src,
                    "a topic label is a literal in prompt_composer.py — "
                    "the second hand-written list is back")

    def test_the_predicate_records_the_same_gate(self):
        """The inert registry must not drift from the live composer."""
        self.assertIn('return s.current_pass == "pass1" and not s.identity_mode',
                      _read(_PREDICATES))
