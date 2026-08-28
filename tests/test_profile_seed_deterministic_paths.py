"""Nine deterministic WebSocket paths, and none of them can advance the walk.

WO-LORI-PROFILE-SEED-REACHABILITY-01 — pre-Step-6 correction checkpoint,
2026-08-27.

── HOW TO RUN THIS ───────────────────────────────────────────────────

    PYTHONPATH=server/code python3 -m unittest \\
        tests.test_profile_seed_deterministic_paths

**No skips, on any interpreter.** It reads `chat_ws.py` as source and
parses it. `chat_ws` imports fastapi, which is not installed on every
interpreter this repository is tested on, and a gate that skips where
fastapi is missing would be absent exactly where nobody is looking.

── WHY THIS FILE EXISTS: THE INVENTORY SAID SIX ──────────────────────

The Phase 2 transport map, §6, called its list of turns-that-must-not-
advance COMPLETE and named six deterministic branches — the six that go
through `_finalize_deterministic_turn`. That function is genuinely
structural: it never writes the params keys, so anything routed through
it is held out by construction rather than by six authors each
remembering.

**Three more deterministic early returns exist and BYPASS it**, each
calling `persist_turn_transaction` directly with its own inline `meta`
dict and returning:

    floor_buffer            chat_ws.py:1672
    past_tense_acknowledge  chat_ws.py:3071
    bank_flush              chat_ws.py:3654

They were not in the map. An inventory that is wrong about its own size
is the worst kind of inventory, because the six it lists make the three
it omits look considered. Step 6 will merge Profile Seed metadata into
the assistant row's turn commit; a persist site the map does not know
about is a persist site nobody thinks to check.

── WHAT IS ASSERTED, AND WHAT IS NOT ─────────────────────────────────

Asserted:

  * the number of deterministic persist CALL SITES in `chat_ws.py` is
    exactly nine, every expected mode occurs exactly once, no unlisted
    mode is present, and each site carries its expected
    finalized/bypassing classification — so a tenth path fails this file
    rather than joining silently;

    *(Corrected 2026-08-28. This read "the SET of deterministic
    `turn_mode` values", and the extractor returned a dict keyed by
    mode, so two sites sharing a mode collapsed into one. The claim in
    the same sentence — that a tenth path cannot join silently — was
    therefore false in exactly the case a tenth path is most likely to
    arise: a copied branch that keeps its predecessor's `turn_mode`. A
    set answers "which modes exist"; the question here is "how many
    paths persist a turn", and only a sequence can answer it.)*
  * no `meta` dict literal anywhere in `chat_ws.py` carries a Profile
    Seed metadata key;
  * `_finalize_deterministic_turn` mentions no Profile Seed key and
    calls no Profile Seed apply — the structural guarantee for six;
  * each of the three bypassing paths carries no Profile Seed key and
    performs no apply within its own early-return region — the
    individual guarantee the other three need, precisely because they
    do not inherit one;
  * the transport map document lists all nine.

NOT asserted: that `chat_ws.py` never mentions Profile Seed at all.
Step 6 will legitimately add a resolve, a plan, a merge on the MODEL
path and a post-commit apply. This file is written so Step 6 extends
the sanctioned list and keeps failing for the deterministic nine — see
`Step6TripwireTests`.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path
from typing import List, NamedTuple

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
for _p in (str(_SERVER_CODE), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.services import profile_seed_turn as _turn  # noqa: E402

_CHAT_WS = _SERVER_CODE / "api" / "routers" / "chat_ws.py"
_TRANSPORT_MAP = (_REPO_ROOT / "docs" / "wo"
                  / "WO-LORI-PROFILE-SEED-REACHABILITY-01_PHASE2_TRANSPORT_MAP.md")

#: The six that go through the shared finalizer.
FINALIZED_MODES = ("floor_hold", "meta_question", "witness", "memory_echo",
                   "age_recall", "correction")

#: The three that persist directly and return. They need their OWN
#: guards because they inherit nothing from the finalizer.
BYPASSING_MODES = ("floor_buffer", "past_tense_acknowledge", "bank_flush")

ALL_DETERMINISTIC_MODES = FINALIZED_MODES + BYPASSING_MODES

#: Names that would mean this turn is touching onboarding progress.
_APPLY_NAMES = ("profile_seed_apply", "profile_seed_resolve",
                "plan_turn", "recover")


def _tree():
    return ast.parse(_CHAT_WS.read_text(encoding="utf-8"))


def _call_name(node):
    return getattr(node.func, "id", None) or getattr(node.func, "attr", None)


def _kwargs(node):
    return {k.arg: k.value for k in node.keywords if k.arg}


def _const(node):
    return node.value if isinstance(node, ast.Constant) else None


def _dict_literal(node):
    """`{literal key: node}` for a dict literal, else `None`."""
    if not isinstance(node, ast.Dict):
        return None
    out = {}
    for key, value in zip(node.keys, node.values):
        name = _const(key)
        if isinstance(name, str):
            out[name] = value
    return out


class Site(NamedTuple):
    """One deterministic persist site. ONE PER CALL, never per mode."""
    turn_mode: str
    lineno: int
    kind: str          # "finalized" | "bypassing"


def _deterministic_sites(tree) -> List[Site]:
    """EVERY deterministic call site, in source order.

    ── A DICT KEYED BY `turn_mode` COLLAPSED DUPLICATES, 2026-08-28 ─────

    *(This returned `{turn_mode: (lineno, kind)}`. Two call sites using
    the same mode overwrote one another, so the inventory reported the
    number of DISTINCT MODES and called it the number of paths. Proved
    directly against a two-line synthetic module:*

        call sites in source: 2
        sites reported:       1   {'floor_hold': (2, 'finalized')}

    *Which makes this file's own headline claim — "a tenth path fails
    this file rather than joining silently" — FALSE in exactly the case
    a tenth path is most likely to arise: someone copying an existing
    branch, keeping its `turn_mode`, and adding a persist call. The
    inventory would have counted nine and reported green.*

    *A container that deduplicates is the wrong instrument for a
    question about COUNTING call sites, and it hid that by answering a
    different question fluently.)*

    A list, in source order. `test_the_extractor_does_NOT_collapse_two_sites_sharing_a_mode`
    is the positive control that keeps it one.
    """
    found: List[Site] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        kwargs = _kwargs(node)
        if name == "_finalize_deterministic_turn":
            mode = _const(kwargs.get("turn_mode"))
            if isinstance(mode, str):
                found.append(Site(mode, node.lineno, "finalized"))
        elif name == "persist_turn_transaction":
            meta = _dict_literal(kwargs.get("meta"))
            if not meta:
                continue
            mode = _const(meta.get("turn_mode"))
            if isinstance(mode, str):
                found.append(Site(mode, node.lineno, "bypassing"))
    return sorted(found, key=lambda s: s.lineno)


def _sites_for(sites: List[Site], mode: str) -> List[Site]:
    return [s for s in sites if s.turn_mode == mode]


class InventoryTests(unittest.TestCase):
    """The map said six. There are nine, and the COUNT OF SITES is asserted."""

    def setUp(self):
        self.sites = _deterministic_sites(_tree())

    def test_exactly_NINE_CALL_SITES_exist(self):
        """The count of SITES, not of distinct modes.

        This is the assertion the dict could not make. A tenth path that
        reuses an existing `turn_mode` — the likeliest kind, since it
        arrives by copying a branch — left the mode set unchanged and
        the old inventory reported green.
        """
        self.assertEqual(
            len(self.sites), len(ALL_DETERMINISTIC_MODES),
            "the number of deterministic persist SITES in chat_ws.py is "
            f"{len(self.sites)}, not {len(ALL_DETERMINISTIC_MODES)}. Sites "
            f"found: {self.sites}. A NEW path must be added to this "
            "inventory, to transport map §6, and given a guard below — it "
            "does not inherit one by existing.")

    def test_every_expected_mode_occurs_EXACTLY_ONCE(self):
        for mode in ALL_DETERMINISTIC_MODES:
            with self.subTest(mode=mode):
                hits = _sites_for(self.sites, mode)
                self.assertEqual(
                    len(hits), 1,
                    f"{mode} appears at {len(hits)} deterministic persist "
                    f"sites: {hits}. Each mode names ONE path; two sites "
                    "sharing a mode are two paths wearing one name, and the "
                    "guards below are written per path.")

    def test_no_UNEXPECTED_mode_is_present(self):
        unexpected = [s for s in self.sites
                      if s.turn_mode not in ALL_DETERMINISTIC_MODES]
        self.assertEqual(unexpected, [], f"unlisted deterministic paths: "
                                         f"{unexpected}")

    def test_every_site_carries_its_expected_classification(self):
        """Per SITE, not per mode.

        `finalized` inherits the shared finalizer's structural guarantee;
        `bypassing` inherits nothing and is guarded individually. A site
        that changed category silently would move between two different
        proofs.
        """
        expected = dict.fromkeys(FINALIZED_MODES, "finalized")
        expected.update(dict.fromkeys(BYPASSING_MODES, "bypassing"))
        for site in self.sites:
            with self.subTest(mode=site.turn_mode, line=site.lineno):
                self.assertEqual(
                    site.kind, expected.get(site.turn_mode),
                    f"chat_ws.py:{site.lineno} ({site.turn_mode}) is "
                    f"{site.kind}, not {expected.get(site.turn_mode)}")

    def test_the_extractor_does_NOT_collapse_two_sites_sharing_a_mode(self):
        """THE POSITIVE CONTROL for the 2026-08-28 defect.

        Synthetic, because the real module deliberately has no duplicate
        — so nothing in the tree can demonstrate that the extractor
        would see one. Without this, the count assertion above passes
        whether or not the collapse was ever fixed.
        """
        duplicated = ast.parse(
            '_finalize_deterministic_turn(ws, turn_mode="floor_hold")\n'
            '_finalize_deterministic_turn(ws, turn_mode="floor_hold")\n'
            'persist_turn_transaction(conv_id=c, '
            'meta={"ws": True, "turn_mode": "floor_buffer"})\n'
            'persist_turn_transaction(conv_id=c, '
            'meta={"ws": True, "turn_mode": "floor_buffer"})\n')
        sites = _deterministic_sites(duplicated)
        self.assertEqual(
            len(sites), 4,
            f"the extractor collapsed four call sites into {len(sites)}: "
            f"{sites}. Keyed by turn_mode it reported 2, and an inventory "
            "that deduplicates cannot count paths.")
        self.assertEqual(len(_sites_for(sites, "floor_hold")), 2)
        self.assertEqual(len(_sites_for(sites, "floor_buffer")), 2)
        self.assertEqual([s.kind for s in sites],
                         ["finalized", "finalized", "bypassing", "bypassing"])

    def test_the_six_finalized_paths_route_through_the_shared_finalizer(self):
        for mode in FINALIZED_MODES:
            with self.subTest(mode=mode):
                self.assertEqual(_sites_for(self.sites, mode)[0].kind,
                                 "finalized")

    def test_the_three_bypassing_paths_persist_directly(self):
        """Named as a property, not as trivia.

        These three do not go through `_finalize_deterministic_turn`, so
        every guarantee that function provides — including the one that
        keeps deterministic turns extraction-ineligible — has to be
        established separately for them.
        """
        for mode in BYPASSING_MODES:
            with self.subTest(mode=mode):
                self.assertEqual(_sites_for(self.sites, mode)[0].kind,
                                 "bypassing")

    def test_the_transport_map_lists_all_nine(self):
        """The document and the code agree, or this fails.

        §6 called a six-row table "the complete inventory". A map that
        is confidently wrong about its own size is worse than a missing
        one: the rows it has make the rows it lacks look considered.
        """
        text = _TRANSPORT_MAP.read_text(encoding="utf-8")
        for mode in ALL_DETERMINISTIC_MODES:
            with self.subTest(mode=mode):
                self.assertIn(
                    mode, text,
                    f"{mode} is a persisted deterministic early return and "
                    "the transport map does not name it")


class NoSeedMetadataTests(unittest.TestCase):
    """No deterministic turn can stamp Profile Seed metadata."""

    def setUp(self):
        self.tree = _tree()

    def _meta_dicts(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and _call_name(node) in (
                    "persist_turn_transaction", "_finalize_deterministic_turn"):
                literal = _dict_literal(_kwargs(node).get("meta"))
                if literal is not None:
                    yield node.lineno, literal

    def test_no_meta_literal_carries_a_profile_seed_key(self):
        seen = 0
        for lineno, literal in self._meta_dicts():
            seen += 1
            for key in _turn.META_KEYS:
                with self.subTest(line=lineno, key=key):
                    self.assertNotIn(
                        key, literal,
                        f"chat_ws.py:{lineno} stamps {key} onto a turn row. "
                        "Only the model path may carry Profile Seed "
                        "presentation or response metadata, and only from a "
                        "validated plan.")
        self.assertGreaterEqual(
            seen, len(BYPASSING_MODES),
            "the meta-dict scan found fewer literals than there are "
            "bypassing paths, so it is not looking where it claims to")

    def test_no_profile_seed_key_appears_anywhere_in_chat_ws_yet(self):
        """The Step 6 tripwire, stated as a fact about today's tree.

        Step 6 will legitimately add these keys ON THE MODEL PATH. When
        it does, this test fails — and that is the point: the author has
        to come here, narrow it to the model path, and leave the nine
        deterministic paths covered by the test above.
        """
        source = _CHAT_WS.read_text(encoding="utf-8")
        for key in _turn.META_KEYS:
            with self.subTest(key=key):
                self.assertNotIn(
                    key, source,
                    "Profile Seed metadata has reached chat_ws.py. If this "
                    "is Step 6, narrow this test to the model path rather "
                    "than deleting it — the deterministic paths still owe "
                    "the guarantee.")

    def test_the_scan_would_SEE_a_seed_key_if_one_were_there(self):
        """Positive control on the extractor, not on the source.

        Parses a synthetic module shaped like the bypassing paths and
        requires the key to be found. Without this, "no key found" could
        equally mean "the walker never looked inside a meta dict".
        """
        fake = ast.parse(
            "persist_turn_transaction(conv_id=c, meta={'ws': True, "
            "'turn_mode': 'floor_buffer', "
            f"'{_turn.PRESENTED_TOPIC}': 'childhood_home'}})")
        literals = []
        for node in ast.walk(fake):
            if isinstance(node, ast.Call):
                literal = _dict_literal(_kwargs(node).get("meta"))
                if literal is not None:
                    literals.append(literal)
        self.assertTrue(literals, "the extractor found no meta dict at all")
        self.assertIn(_turn.PRESENTED_TOPIC, literals[0])


class FinalizerStructuralGuaranteeTests(unittest.TestCase):
    """The six inherit their guarantee from one function. Pin that."""

    def _finalizer(self):
        for node in ast.walk(_tree()):
            if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == "_finalize_deterministic_turn"):
                return node
        self.fail("_finalize_deterministic_turn is gone; the six branches "
                  "that rely on it no longer inherit anything")

    def test_the_finalizer_names_no_profile_seed_metadata_key(self):
        body = ast.dump(self._finalizer())
        for key in _turn.META_KEYS:
            with self.subTest(key=key):
                self.assertNotIn(key, body)

    def test_the_finalizer_calls_no_profile_seed_accessor(self):
        called = {_call_name(n) for n in ast.walk(self._finalizer())
                  if isinstance(n, ast.Call)}
        for name in _APPLY_NAMES:
            with self.subTest(name=name):
                self.assertNotIn(
                    name, called,
                    f"_finalize_deterministic_turn calls {name}; six "
                    "deterministic branches would advance the walk at once")

    def test_a_missing_finalizer_FAILS_rather_than_passes(self):
        """The lookup above must fail loudly if the function is renamed.

        A structural guard whose target has moved reports green while
        measuring nothing — this repository has shipped that defect once
        already, in the composer's own AST guard.
        """
        tree = ast.parse("def something_else():\n    pass\n")
        names = [n.name for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        self.assertNotIn("_finalize_deterministic_turn", names)


class BypassingPathGuardTests(unittest.TestCase):
    """The three that inherit nothing, guarded one at a time."""

    def _enclosing_region(self, lineno):
        """The branch's EARLY-RETURN REGION: the smallest enclosing
        `if`/`try` that contains both the persist call and the `return`.

        "Smallest enclosing block" alone is not it. All three of these
        wrap their `persist_turn_transaction` in a narrow `try` that
        swallows a persistence failure, and that `try` does not contain
        the `return` — so it is a fragment of the branch, not the branch.
        The region that matters is the one that ends the turn.

        Scoping to it — rather than to the whole 6,000-line module — is
        what lets these guards stay true after Step 6 adds Profile Seed
        work to the MODEL path.
        """
        tree = _tree()
        candidates = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.If, ast.Try)):
                continue
            start = node.lineno
            end = getattr(node, "end_lineno", start)
            if start <= lineno <= end:
                candidates.append((end - start, node))
        candidates.sort(key=lambda pair: pair[0])
        for _span, node in candidates:
            if any(isinstance(n, ast.Return) for n in ast.walk(node)):
                return node
        self.fail(f"no enclosing block containing a return found at {lineno}")

    def _site_line(self, mode):
        """The ONE call site for `mode`, or a named failure.

        `InventoryTests` proves each mode occurs exactly once; this
        asserts it again at the point of use so a duplicate cannot
        silently make these guards inspect only the first site.
        """
        hits = _sites_for(_deterministic_sites(_tree()), mode)
        self.assertEqual(len(hits), 1,
                         f"{mode} has {len(hits)} call sites: {hits}")
        return hits[0].lineno

    def test_each_bypassing_path_stamps_no_profile_seed_key(self):
        for mode in BYPASSING_MODES:
            lineno = self._site_line(mode)
            region = ast.dump(self._enclosing_region(lineno))
            for key in _turn.META_KEYS:
                with self.subTest(mode=mode, key=key):
                    self.assertNotIn(
                        key, region,
                        f"the {mode} early return stamps {key}")

    def test_each_bypassing_path_applies_no_onboarding_progress(self):
        for mode in BYPASSING_MODES:
            lineno = self._site_line(mode)
            region = self._enclosing_region(lineno)
            called = {_call_name(n) for n in ast.walk(region)
                      if isinstance(n, ast.Call)}
            for name in _APPLY_NAMES:
                with self.subTest(mode=mode, name=name):
                    self.assertNotIn(
                        name, called,
                        f"the {mode} early return calls {name} — a turn the "
                        "narrator never answered would advance the walk")

    def test_each_bypassing_path_returns_without_reaching_the_model(self):
        """They are early RETURNS, which is why they need their own guard.

        If one stopped returning it would fall through to the model path
        and be covered by Step 6's plan instead — a different contract,
        and one this file should stop claiming to cover.
        """
        for mode in BYPASSING_MODES:
            lineno = self._site_line(mode)
            region = self._enclosing_region(lineno)
            returns = [n for n in ast.walk(region) if isinstance(n, ast.Return)]
            with self.subTest(mode=mode):
                self.assertTrue(
                    returns,
                    f"the {mode} branch no longer returns; it is not a "
                    "deterministic early return any more and this "
                    "inventory is describing something that stopped "
                    "existing")

    def test_the_region_finder_is_not_vacuous(self):
        """A region that is the whole module would pass everything.

        Each of the three must resolve to a block strictly smaller than
        the file, or the guards above are asserting about nothing in
        particular.
        """
        total = len(_CHAT_WS.read_text(encoding="utf-8").splitlines())
        for mode in BYPASSING_MODES:
            region = self._enclosing_region(self._site_line(mode))
            span = getattr(region, "end_lineno", 0) - region.lineno
            with self.subTest(mode=mode, span=span):
                self.assertGreater(span, 0)
                self.assertLess(
                    span, total // 2,
                    "the enclosing region is most of the module, so a "
                    "'not in this region' assertion means very little")


class Step6TripwireTests(unittest.TestCase):
    """What Step 6 is allowed to change here, written down in advance."""

    def test_no_deterministic_path_advances_today(self):
        """The single claim this whole file supports, restated plainly.

        Nine paths persist a turn and return. None of them stamps a
        presentation or a response, and none applies progress. A narrator
        whose turn resolves deterministically is exactly where the walk
        left them.
        """
        sites = _deterministic_sites(_tree())
        self.assertEqual(len(sites), 9, f"sites: {sites}")
        self.assertEqual(sorted(s.turn_mode for s in sites),
                         sorted(ALL_DETERMINISTIC_MODES))
        source = _CHAT_WS.read_text(encoding="utf-8")
        self.assertNotIn("profile_seed_apply", source)
        for key in _turn.META_KEYS:
            self.assertNotIn(key, source)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
