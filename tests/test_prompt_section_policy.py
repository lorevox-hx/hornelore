"""One authoritative policy per prompt section, resolved not restated.

WO-LEAN-LORI-RUNTIME-01 item 1 (prompt-section metadata), 2026-08-18.

`required` and `drop_order` used to be typed at each `parts.add()` call
inside a 1,200-line function, and omitting them meant `False` and `0`.
That is how `approved_stories` shipped ranked below a per-turn hint:
nobody chose 0, it was simply what silence meant. The scattering is also
why it took a whole phase to notice that nothing read the classification
at all -- there was no single place to look.

WHAT THESE TESTS PIN:

  * one registry, keyed by stable section id, with the full declarative
    set: owner, activation, trim policy, source, tier, required, order;
  * every section the composer emits resolves through it, including the
    transport-appended `trip_context`;
  * an unknown id RAISES and a duplicate id fails at import -- neither
    may inherit a silent default;
  * token counts and digests are absent from the declarative layer,
    because the tokenizer does not exist at composition time;
  * item 1 is behaviour-neutral: every registered value matches the call
    site it replaced.
"""
from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "server" / "code"))

from api.prompt_composer import (          # noqa: E402
    compose_prompt_sections, make_section,
)
from api.services import prompt_section_policy as pol   # noqa: E402
from api.services.prompt_budget import SectionPlan      # noqa: E402

_COMPOSER = _REPO / "server" / "code" / "api" / "prompt_composer.py"
_CHAT_WS = _REPO / "server" / "code" / "api" / "routers" / "chat_ws.py"
_POLICY = _REPO / "server" / "code" / "api" / "services" / "prompt_section_policy.py"

# The values in force BEFORE item 1, transcribed from the call sites this
# change removed. Behaviour neutrality is asserted against this table.
_PRE_ITEM_1 = {
    "system_head":              (True, 0),
    "ui_context":               (False, 30),
    "pinned_facts":             (False, 40),
    "identity_facts":           (True, 0),
    "identity_grounding":       (True, 0),
    "approved_stories":         (False, 25),
    "english_first":            (False, 20),
    "factual_chain":            (False, 10),
    "trip_context":             (False, 15),
    "directives_bio_builder":   (True, 0),
    "directives_questionnaire": (True, 0),
    "directives_interview":     (True, 0),
    "memory_context":           (False, 5),
}


class TheRegistryIsComplete(unittest.TestCase):
    def test_every_section_declares_the_full_policy_set(self):
        for sid in pol.known_section_ids():
            with self.subTest(section=sid):
                p = pol.policy_for(sid)
                self.assertTrue(p.owner, "no owner")
                self.assertTrue(p.activation, "no activation condition")
                self.assertIn(p.trim_policy, (pol.TRIM_NEVER, pol.TRIM_DROP_WHOLE))
                self.assertTrue(p.source, "no source")
                self.assertTrue(p.priority_tier, "no priority tier")
                self.assertIsInstance(p.required, bool)
                self.assertIsInstance(p.drop_order, int)

    def test_required_and_trim_policy_cannot_disagree(self):
        """Two spellings of one fact. Letting them differ would give two
        answers to 'may this be dropped'."""
        for sid in pol.known_section_ids():
            with self.subTest(section=sid):
                p = pol.policy_for(sid)
                self.assertEqual(p.required, p.trim_policy == pol.TRIM_NEVER)

    def test_no_droppable_section_takes_the_default_order(self):
        """The exact defect that put a reviewed story below a per-turn
        hint: an unspecified `drop_order` meant 0, and 0 is first out."""
        for sid in pol.known_section_ids():
            p = pol.policy_for(sid)
            if not p.required:
                with self.subTest(section=sid):
                    self.assertGreater(p.drop_order, 0)

    def test_no_two_droppable_sections_share_an_order(self):
        orders = [pol.policy_for(s).drop_order
                  for s in pol.known_section_ids()
                  if not pol.policy_for(s).required]
        self.assertEqual(len(orders), len(set(orders)))


class UnknownAndDuplicateIdsFail(unittest.TestCase):
    def test_an_unknown_id_raises_rather_than_defaulting(self):
        with self.assertRaises(pol.UnknownSectionError):
            pol.policy_for("not_a_real_section")

    def test_the_error_says_what_to_do(self):
        try:
            pol.policy_for("not_a_real_section")
        except pol.UnknownSectionError as exc:
            msg = str(exc)
        self.assertIn("REGISTRY", msg)
        self.assertIn("drop order", msg)

    def test_a_duplicate_id_fails_at_registry_build(self):
        p = pol.policy_for("memory_context")
        with self.assertRaises(ValueError) as ctx:
            pol._build_registry([p, p])
        self.assertIn("duplicate", str(ctx.exception))

    def test_a_droppable_section_without_an_order_fails_at_build(self):
        bad = pol.policy_for("memory_context")._replace(drop_order=0)
        with self.assertRaises(ValueError):
            pol._build_registry([bad])

    def test_contradictory_required_and_trim_policy_fails_at_build(self):
        bad = pol.policy_for("memory_context")._replace(required=True)
        with self.assertRaises(ValueError):
            pol._build_registry([bad])

    def test_shared_drop_orders_fail_at_build(self):
        a = pol.policy_for("memory_context")
        b = pol.policy_for("english_first")._replace(drop_order=a.drop_order)
        with self.assertRaises(ValueError):
            pol._build_registry([a, b])

    def test_make_section_refuses_an_unregistered_id(self):
        """The transport path is the one place a section could still be
        conjured with an invented policy."""
        with self.assertRaises(pol.UnknownSectionError):
            make_section("smuggled_section", "text")


class TheComposerResolvesRatherThanRestates(unittest.TestCase):
    def _composer_body(self):
        src = _COMPOSER.read_text(encoding="utf-8")
        fn = next(n for n in ast.parse(src).body
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "_compose_prompt_assembly")
        return fn

    def test_no_call_site_states_its_own_policy(self):
        """The scattering this item removes. A call site that can set its
        own drop order is a call site that can set it to 0 by omission."""
        offenders = []
        for n in ast.walk(self._composer_body()):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "add"
                    and getattr(n.func.value, "id", "") == "parts"
                    and n.keywords):
                offenders.append((n.args[0].value if n.args else "?",
                                  [k.arg for k in n.keywords]))
        self.assertEqual([], offenders,
                         f"call sites still declare policy: {offenders}")

    def test_every_composed_section_resolves_to_a_policy(self):
        shapes = [
            ("c1", None, None, None),
            ("c2", 'PROFILE_JSON: {"basics":{"firstName":"T"}}', "hi", None),
            ("c3", None, "q", {"current_era": "early_school_years",
                               "story_context": {
                                   "available": True, "status": "read",
                                   "approved": [{"id": "s", "text": "A story.",
                                                 "era": "early_school_years",
                                                 "year": 1945,
                                                 "placement": "operator_set"}],
                                   "approved_count": 1,
                                   "provisional_count": 1}}),
            ("c4", None, "hola", {"current_era": "today"}),
        ]
        for cid, ui, ut, rt in shapes:
            with self.subTest(case=cid):
                for s in compose_prompt_sections(cid, ui_system=ui,
                                                 user_text=ut,
                                                 runtime71=rt).sections:
                    self.assertIsNotNone(
                        s.policy, f"{s.name} composed without a policy")
                    self.assertEqual(s.name, s.policy.section_id)
                    self.assertEqual(s.required, s.policy.required)
                    self.assertEqual(s.drop_order, s.policy.drop_order)

    def test_the_transport_section_resolves_through_the_registry(self):
        sec = make_section("trip_context", "TRIP TEXT")
        self.assertIsNotNone(sec.policy)
        self.assertEqual(15, sec.drop_order)
        self.assertEqual(pol.SOURCE_TRANSPORT, sec.policy.source)

    def test_the_transport_call_site_states_no_policy(self):
        code = "\n".join(ln for ln in _CHAT_WS.read_text(encoding="utf-8").splitlines()
                         if not ln.lstrip().startswith("#"))
        m = re.search(r"make_section\([^)]*\)", code, re.S)
        self.assertIsNotNone(m)
        self.assertNotIn("drop_order", m.group(0))
        self.assertNotIn("required", m.group(0))


class ItemOneIsBehaviourNeutral(unittest.TestCase):
    def test_every_registered_value_matches_the_call_site_it_replaced(self):
        for sid, (required, order) in sorted(_PRE_ITEM_1.items()):
            with self.subTest(section=sid):
                p = pol.policy_for(sid)
                self.assertEqual(required, p.required)
                self.assertEqual(order, p.drop_order)

    def test_the_registry_covers_exactly_the_known_sections(self):
        self.assertEqual(set(_PRE_ITEM_1), set(pol.known_section_ids()))


class TheTwoLayersStaySeparate(unittest.TestCase):
    """Counts and digests are per-turn and measured; policy is not."""

    def test_the_declarative_layer_has_no_token_count_or_digest(self):
        fields = pol.SectionPolicy._fields
        for banned in ("tokens", "token_count", "digest", "hash", "kept"):
            with self.subTest(field=banned):
                self.assertNotIn(banned, fields)

    @staticmethod
    def _executable_source(path):
        """Source with comments AND docstrings removed.

        A line-based `#` strip is not enough here: this module's own
        docstring explains why token counts do not belong in it, so it
        contains the words a naive scan bans. That is the sixth time a
        guard in this repository has fired on the prose describing the
        rule it enforces, and the fix is the same each time -- match what
        the interpreter executes, not what the file contains.
        """
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if (isinstance(body, list) and body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(getattr(body[0], "value", None), ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body.pop(0)
        return ast.unparse(tree)

    def test_the_policy_module_never_estimates_tokens(self):
        code = self._executable_source(_POLICY)
        for banned in ("len(text)", "// 4", "/ 4", "encode(", "tokenize"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, code)

    def test_the_docstring_stripper_is_not_vacuous(self):
        """A stripper that returned nothing would pass the test above.

        The positive control: real code from the module must survive.
        """
        code = self._executable_source(_POLICY)
        self.assertIn("def policy_for", code)
        self.assertIn("UnknownSectionError", code)
        self.assertIn("TRIM_DROP_WHOLE", code)
        # And the docstring it strips really did contain a banned word.
        self.assertIn("tokenize", _POLICY.read_text(encoding="utf-8"))

    def test_the_evaluated_layer_carries_the_measured_fields(self):
        for field in ("tokens", "digest", "kept"):
            self.assertIn(field, SectionPlan.__dataclass_fields__)

    def test_the_evaluated_layer_reports_policy_without_re_deriving_it(self):
        p = pol.policy_for("approved_stories")
        plan = SectionPlan(name="approved_stories", required=False,
                           drop_order=25, tokens=309, digest="abc123def456",
                           kept=True, policy=p)
        self.assertEqual("story-review", plan.owner)
        self.assertEqual(pol.TIER_REVIEWED_EVIDENCE, plan.priority_tier)
        self.assertEqual(pol.TRIM_DROP_WHOLE, plan.trim_policy)

    def test_an_unregistered_plan_says_so_rather_than_guessing(self):
        plan = SectionPlan(name="mystery", required=False, drop_order=1,
                           tokens=1, digest="d", kept=True)
        self.assertEqual("unregistered", plan.owner)
        self.assertEqual("unregistered", plan.priority_tier)


class TrimPolicyDoesNotDecideGlobalOrdering(unittest.TestCase):
    """Item 3, not item 1.

    `trim_policy` says what MAY happen to a section. Whether optional
    sections should go before or after conversation history is a product
    decision to be made from measurement, and a vocabulary that could
    express it here would invite someone to guess.
    """

    def test_the_vocabulary_cannot_express_a_history_comparison(self):
        src = _POLICY.read_text(encoding="utf-8")
        code = "\n".join(ln for ln in src.splitlines()
                         if not ln.lstrip().startswith("#"))
        for banned in ("before_history", "after_history", "history_first",
                       "prefer_history", "drop_before_history"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, code)

    def test_only_two_trim_policies_exist(self):
        self.assertEqual({pol.TRIM_NEVER, pol.TRIM_DROP_WHOLE},
                         set(pol._TRIM_POLICIES))


if __name__ == "__main__":
    unittest.main()
