"""What `_apply_refusal_guard` does today, pinned before it is moved.

WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 2 step 1 (2026-08-26).

── HOW TO RUN THIS ───────────────────────────────────────────────────

    PYTHONPATH=server/code python3 -m unittest tests.test_narrator_refusal_characterization

The INVENTORY class reads source text with `ast` and needs no imports at
all, so `.venv` runs it. The BEHAVIOUR class imports the extract router,
which reaches fastapi, and skips under `.venv` — **a skip is not a
pass**, so report the count.

── WHY THIS FILE EXISTS, AND WHY IT LANDS BEFORE THE MOVE ────────────

Phase 2 needs narrator-refusal detection in two places: extraction,
where it already lives, and the Profile Seed walk, where an explicit
refusal must record `declined`. The work order's answer is ONE shared
helper called by both, never a second copy of the patterns — two lists
are how the extractor and the onboarding walk would come to disagree
about what a refusal is, and then Lori would strip a field from a
sentence she did not treat as a refusal in conversation.

Moving code is the easy part. The problem found while planning it:

  **`_apply_refusal_guard` HAS NO UNIT COVERAGE AT ALL.** Its only
  exercise today is indirect, through the eval case banks under
  `data/qa/`. Moving a function with no net under it is how behaviour
  changes without anyone noticing — the tests still pass, because there
  were no tests.

So this lands in its own commit FIRST, against the code in its current
home, and re-runs unchanged after the move. That is what makes the move
provable rather than merely careful.

── EIGHT PATTERNS, AND WHY THE COUNT IS ASSERTED ─────────────────────

There are EIGHT `re.compile` entries. The Phase 2 map said seven for
three revisions, because I read a truncated listing instead of counting
one. A characterization suite over seven patterns would have left the
eighth's behaviour unproven across the move — which is precisely the
silent drift this file exists to prevent, arriving through the front
door.

`test_there_are_exactly_eight_patterns` is therefore not decoration. It
fails if a pattern is added or dropped, and it fails after the move if
the helper does not carry all eight in the same order.

── EACH PATTERN IS EXERCISED UNIQUELY ────────────────────────────────

Every phrase below matches EXACTLY ONE pattern, verified by
`test_each_phrase_exercises_exactly_its_own_pattern`. Without that, a
phrase matching two patterns would let one of them be deleted with the
suite still green, and "eight patterns characterized" would be false
while looking true.
"""
from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
for _p in (str(_SERVER_CODE), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import fastapi  # noqa: F401
    _HAS_FASTAPI = True
except Exception:  # pragma: no cover
    _HAS_FASTAPI = False

_EXTRACT_PY = _SERVER_CODE / "api" / "routers" / "extract.py"

#: The canonical count. See the module docstring for why this is asserted.
_EXPECTED_PATTERN_COUNT = 8

#: One phrase per pattern, in pattern order. Each matches exactly one.
#: Measured, not assumed — see the uniqueness test.
_POSITIVES = (
    (1, "I don't think that's something I want written down."),
    (2, "That's not for putting in a book."),
    (3, "There's nothing I want to go into there."),
    (4, "I'd rather leave it at that."),
    (5, "I would prefer not to answer that."),
    (6, "Let's skip that, if you don't mind."),
    (7, "I don't want to talk about that."),
    # Pattern 8 overlaps pattern 4 for "I'd rather not get into that", so
    # the phrase deliberately avoids the "I'd " / "I would " prefix that
    # pattern 4 requires. Otherwise pattern 4 would fire first and 8
    # would never be exercised.
    (8, "We'd rather not talk about that."),
)

#: Must match NOTHING. The first four are the ones that matter most:
#: under the Phase 2 dignity rulings, forgetting resolves to `addressed`
#: and a temporary deferral leaves the question open — NEITHER is a
#: refusal, and treating them as one would record a narrator's memory
#: loss as a refusal to speak.
_NEGATIVES = (
    "I don't remember.",
    "I can't recall that at all.",
    "Nothing comes to mind right now.",
    "Let me think about that for a moment.",
    "Give me a moment.",
    "Come back to that later.",
    "I would rather have coffee first.",
    "I don't want to forget that.",
    "We moved to a new place in 1952.",
    "Devils Lake, North Dakota.",
    "I never served in the military.",
    "My father worked at the grain elevator.",
)


def _pattern_sources_from(path: Path, func_name: str):
    """The regex source strings, in order, read from a function's AST.

    Read from SOURCE rather than imported, for two reasons. The list is
    a local inside the function today and cannot be imported at all —
    which is the thing Phase 2 is about to change. And reading the
    source means this test can be pointed at the new home after the
    move and compare the two, rather than trusting that they match.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != func_name:
            continue
        out = []
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            fn = inner.func
            is_compile = (
                (isinstance(fn, ast.Attribute) and fn.attr == "compile")
                or (isinstance(fn, ast.Name) and fn.id == "compile")
            )
            if not is_compile or not inner.args:
                continue
            first = inner.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                out.append(first.value)
        return out
    return []


def _module_level_pattern_sources(path: Path, name: str):
    """Regex sources from a MODULE-LEVEL assignment — the post-move shape."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        if not any(isinstance(t, ast.Name) and t.id == name for t in targets):
            continue
        value = node.value
        out = []
        for inner in ast.walk(value):
            if not isinstance(inner, ast.Call):
                continue
            fn = inner.func
            is_compile = (
                (isinstance(fn, ast.Attribute) and fn.attr == "compile")
                or (isinstance(fn, ast.Name) and fn.id == "compile")
            )
            if is_compile and inner.args:
                first = inner.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    out.append(first.value)
        return out
    return []


def _live_patterns():
    """The eight compiled patterns, wherever they currently live.

    Looks in the original home first, then the shared helper. This is
    what lets ONE unchanged test file run before and after the move: it
    follows the code instead of being rewritten around it.
    """
    srcs = _pattern_sources_from(_EXTRACT_PY, "_apply_refusal_guard")
    if not srcs:
        helper = _SERVER_CODE / "api" / "services" / "narrator_refusal.py"
        if helper.exists():
            srcs = _module_level_pattern_sources(helper, "REFUSAL_PATTERNS")
            if not srcs:
                srcs = _pattern_sources_from(helper, "is_topic_refusal")
    return [re.compile(s, re.IGNORECASE) for s in srcs]


class PatternInventoryTests(unittest.TestCase):
    """Source-level. No imports, so `.venv` runs these too."""

    def setUp(self):
        self.patterns = _live_patterns()

    def test_there_are_exactly_eight_patterns(self):
        self.assertEqual(
            len(self.patterns), _EXPECTED_PATTERN_COUNT,
            "the refusal pattern count changed. If a pattern was added "
            "deliberately, add a positive phrase for it below and update the "
            "constant. If this fires after the move to the shared helper, a "
            "pattern was dropped in transit — which is exactly what this "
            "file exists to catch.")

    def test_every_pattern_compiles(self):
        for i, pat in enumerate(self.patterns, 1):
            with self.subTest(pattern=i):
                self.assertTrue(pat.pattern)

    def test_each_phrase_exercises_exactly_its_own_pattern(self):
        """The non-vacuity control on the characterization data itself.

        A phrase that matched two patterns would let one of them be
        deleted with this suite still green — and "eight patterns
        characterized" would be false while reading as true.
        """
        for index, phrase in _POSITIVES:
            with self.subTest(pattern=index, phrase=phrase):
                hits = [i for i, p in enumerate(self.patterns, 1)
                        if p.search(phrase.lower())]
                self.assertEqual(
                    hits, [index],
                    f"{phrase!r} was meant to exercise pattern {index} alone")

    def test_every_pattern_has_a_positive_phrase(self):
        covered = {i for i, _ in _POSITIVES}
        self.assertEqual(
            covered, set(range(1, _EXPECTED_PATTERN_COUNT + 1)),
            "a pattern has no characterization phrase, so its behaviour "
            "would not be pinned across the move")

    def test_no_negative_matches_any_pattern(self):
        for phrase in _NEGATIVES:
            with self.subTest(phrase=phrase):
                hits = [i for i, p in enumerate(self.patterns, 1)
                        if p.search(phrase.lower())]
                self.assertEqual(hits, [], f"{phrase!r} matched {hits}")

    def test_forgetting_is_not_refusing(self):
        """The Phase 2 dignity ruling, as a property of the patterns.

        "I don't remember" resolves to `addressed` and records nothing
        about the recall difficulty. If it ever matched a refusal
        pattern, a narrator's memory loss would be written down as a
        refusal to speak.
        """
        for phrase in ("I don't remember.", "I can't recall that at all.",
                       "Nothing comes to mind right now."):
            with self.subTest(phrase=phrase):
                self.assertFalse(
                    any(p.search(phrase.lower()) for p in self.patterns))

    def test_a_temporary_deferral_is_not_refusing(self):
        for phrase in ("Let me think about that for a moment.",
                       "Give me a moment.", "Come back to that later."):
            with self.subTest(phrase=phrase):
                self.assertFalse(
                    any(p.search(phrase.lower()) for p in self.patterns))


@unittest.skipUnless(_HAS_FASTAPI,
                     "the extract router imports fastapi; .venv has none — "
                     "a skip is not a pass, report the count")
class GuardBehaviourTests(unittest.TestCase):
    """What the live function does, not what the regexes match."""

    def setUp(self):
        from api.routers import extract as _extract
        self.guard = _extract._apply_refusal_guard
        self.items = [{"fieldPath": "personal.placeOfBirth",
                       "value": "Devils Lake"},
                      {"fieldPath": "family.siblingCount", "value": 2}]

    def test_every_refusal_strips_every_item(self):
        for index, phrase in _POSITIVES:
            with self.subTest(pattern=index, phrase=phrase):
                self.assertEqual(
                    self.guard(list(self.items), phrase), [],
                    "a topic refusal must strip ALL fields — the narrator is "
                    "refusing the line of questioning, not one field")

    def test_no_negative_strips_anything(self):
        for phrase in _NEGATIVES:
            with self.subTest(phrase=phrase):
                self.assertEqual(self.guard(list(self.items), phrase),
                                 self.items)

    def test_empty_items_pass_through_untouched(self):
        self.assertEqual(self.guard([], "I'd rather not talk about that."), [])

    def test_empty_answer_passes_items_through(self):
        for answer in ("", "   ", None):
            with self.subTest(answer=answer):
                self.assertEqual(self.guard(list(self.items), answer),
                                 self.items)

    def test_the_guard_returns_the_same_list_object_when_not_refusing(self):
        """Pinned because it is observable and easy to lose in a move.

        The function returns its input list, not a copy. A caller that
        happens to rely on identity would break silently if the move
        introduced a copy.
        """
        items = list(self.items)
        self.assertIs(self.guard(items, "We moved in 1952."), items)

    def test_a_refusal_anywhere_in_a_long_answer_still_strips(self):
        long_answer = (
            "Well, we lived in Devils Lake until I was about nine, and my "
            "father worked at the grain elevator there. As for the other "
            "thing, I'd rather not talk about that."
        )
        self.assertEqual(self.guard(list(self.items), long_answer), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
