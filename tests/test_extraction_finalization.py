"""Shared final-materialization invariant for BOTH extraction routes.

WO-LORI-ARCHIVE-TO-MEMOIR-02 Phase 3, prerequisite commit (2026-09-04).

WHY THESE TESTS GO THROUGH run_field_extraction
===============================================
The reverted kinship guard (`add4753`, reverted `1c70567`) shipped with 19
passing tests. Every one of them called the guard helper directly and handed
it a `repeatableGroup` key. Production does not have that key at that stage --
the field is `_repeatableGroup` until it is published in the tail -- and the
constructor downstream re-derived `writeMode` from the SCHEMA while never
reading `needs_confirmation` at all. So the guard's advertised downgrade never
reached a caller, and no test noticed, because no test looked at what
`run_field_extraction` actually returns.

These tests therefore assert on the FINAL `ExtractFieldsResponse`. A guard
whose decision does not survive to this surface has not made a decision.

The transcript-safety layer is used as the probe because it is the one
authority-reducing guard already in the tree that is known to work end to end.
If these invariants hold for it, they hold for anything placed at the same
seam -- which is where the rebuilt kinship guard goes next.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "server" / "code") not in sys.path:
    sys.path.insert(0, str(ROOT / "server" / "code"))

from api.routers import extract as EX  # noqa: E402

# Two parents in one answer, each with a name and a surname. Whether these
# four fields can be told apart afterwards is exactly what grouping decides.
TWO_PARENTS = ("My father Clarence Hudson worked at the plant and my mother "
               "Ida Hudson taught school in town.")


def req(answer=TWO_PARENTS, **kw):
    kw.setdefault("person_id", "test-narrator")
    kw.setdefault("current_section", "early_caregivers")
    kw.setdefault("current_target_path", "parents.firstName")
    return EX.ExtractFieldsRequest(answer=answer, **kw)


def llm_returns(items):
    """Patch the LLM stage to emit `items`; empty list forces rules fallback."""
    return mock.patch.object(
        EX, "_extract_via_llm", return_value=(list(items), "[stubbed]"))


def rules_return(items):
    return mock.patch.object(EX, "_extract_via_rules", return_value=list(items))


def item(fp, value, conf=0.9):
    return {"fieldPath": fp, "value": value, "confidence": conf}


PARENTS_PAIR = [
    item("parents.firstName", "Clarence"), item("parents.lastName", "Hudson"),
    item("parents.firstName", "Ida"),      item("parents.lastName", "Hudson"),
]


class SchemaPremises(unittest.TestCase):
    """The fixtures' properties, MEASURED from the shipped schema.

    If any of these change, the tests below are exercising a different case and
    should fail here rather than quietly pass on the wrong path.
    """

    def test_parents_fields_are_repeatable_and_candidate_only(self):
        for fp in ("parents.firstName", "parents.lastName"):
            meta = EX.EXTRACTABLE_FIELDS[fp]
            self.assertEqual("parents", meta.get("repeatable"), fp)
            self.assertEqual("candidate_only", meta.get("writeMode"), fp)

    def test_the_probe_field_is_fragile_and_the_control_is_not(self):
        self.assertTrue(EX._is_fragile_field("parents.firstName"))
        self.assertFalse(EX._is_fragile_field("parents.occupation"))


class BothPathsGroup(unittest.TestCase):
    """repeatableGroup must reach the caller on BOTH routes."""

    def _groups(self, resp):
        return [i.repeatableGroup for i in resp.items]

    def test_llm_path_publishes_repeatable_group(self):
        with llm_returns(PARENTS_PAIR):
            resp = EX.run_field_extraction(req())
        self.assertEqual("llm", resp.method)
        self.assertTrue(all(g is not None for g in self._groups(resp)),
                        self._groups(resp))
        self.assertEqual(2, len(set(self._groups(resp))),
                         "two named parents must land in two groups")

    def test_rules_fallback_path_now_publishes_repeatable_group(self):
        """THE INTENTIONAL OUTPUT CHANGE. This path never called
        _group_repeatable_items, so every fallback item reached callers with
        repeatableGroup=None however many people the answer named."""
        with llm_returns([]), rules_return(PARENTS_PAIR):
            resp = EX.run_field_extraction(req())
        self.assertEqual("rules_fallback", resp.method)
        self.assertTrue(all(g is not None for g in self._groups(resp)),
                        self._groups(resp))
        self.assertEqual(2, len(set(self._groups(resp))))

    def test_grouping_tags_and_never_drops(self):
        """_group_repeatable_items partitions and tags; it must not filter.
        Adding it to the fallback path would otherwise lose narrator facts."""
        for stub, expect in ((llm_returns(PARENTS_PAIR), "llm"),
                             (llm_returns([]), "rules_fallback")):
            with self.subTest(path=expect):
                ctx = [stub] if expect == "llm" else [stub, rules_return(PARENTS_PAIR)]
                with ctx[0]:
                    if len(ctx) > 1:
                        with ctx[1]:
                            resp = EX.run_field_extraction(req())
                    else:
                        resp = EX.run_field_extraction(req())
                self.assertEqual(len(PARENTS_PAIR), len(resp.items))


class GuardDecisionsSurvive(unittest.TestCase):
    """A downgrade applied at the seam must reach the response intact.

    This is the invariant `add4753` violated: it set writeMode and
    needs_confirmation on a dict, and the constructor downstream overwrote the
    first from the schema and ignored the second.
    """

    def _confirming_req(self):
        return req(transcript_source="whisper", transcript_confidence=0.42,
                   confirmation_required=True)

    def _assert_downgraded(self, resp):
        fragile = [i for i in resp.items if i.fieldPath == "parents.firstName"]
        self.assertTrue(fragile, "probe item missing from the response")
        for i in fragile:
            self.assertEqual("suggest_only", i.writeMode,
                             "schema writeMode overwrote the guard's decision")
            self.assertTrue(i.needs_confirmation,
                            "needs_confirmation did not survive serialization")
            self.assertEqual("low_confidence", i.confirmation_reason,
                             "the REASON was lost; a downgrade with no reason "
                             "is unreviewable")
            self.assertIsNotNone(i.repeatableGroup,
                                 "guards must see grouped items")

    def test_llm_path_downgrade_survives_to_the_response(self):
        with llm_returns(PARENTS_PAIR):
            resp = EX.run_field_extraction(self._confirming_req())
        self._assert_downgraded(resp)
        self.assertTrue(resp.clarification_required)

    def test_rules_fallback_downgrade_survives_to_the_response(self):
        with llm_returns([]), rules_return(PARENTS_PAIR):
            resp = EX.run_field_extraction(self._confirming_req())
        self._assert_downgraded(resp)
        self.assertTrue(resp.clarification_required)

    def test_a_non_fragile_field_keeps_its_schema_authority(self):
        """The downgrade must be targeted, not blanket — otherwise the test
        above would pass on a guard that flattened everything."""
        items = PARENTS_PAIR + [item("parents.occupation", "plant foreman")]
        with llm_returns(items):
            resp = EX.run_field_extraction(self._confirming_req())
        occ = [i for i in resp.items if i.fieldPath == "parents.occupation"]
        self.assertEqual(1, len(occ))
        self.assertEqual("candidate_only", occ[0].writeMode)
        self.assertFalse(occ[0].needs_confirmation)

    def test_no_confirmation_requested_means_no_downgrade(self):
        """Byte-stability for today's callers, who leave the STT fields unset."""
        with llm_returns(PARENTS_PAIR):
            resp = EX.run_field_extraction(req())
        for i in resp.items:
            self.assertEqual("candidate_only", i.writeMode)
            self.assertFalse(i.needs_confirmation)
        self.assertEqual([], resp.clarification_required)


class FinalizationContract(unittest.TestCase):
    """Structural guards on the seam itself."""

    SRC = (ROOT / "server" / "code" / "api" / "routers" / "extract.py").read_text(
        encoding="utf-8")

    def test_both_paths_call_the_shared_finaliser(self):
        code = "\n".join(ln for ln in self.SRC.split("\n")
                         if not ln.lstrip().startswith("#"))
        self.assertIn('result_items, req, answer=answer, path="llm"', code)
        self.assertIn('result_items, req, answer=answer, path="rules"', code)

    def test_neither_path_still_finalises_inline(self):
        """One materialization point. Two would drift again — that drift is
        what let a guard be written against a shape production never has."""
        code = "\n".join(ln for ln in self.SRC.split("\n")
                         if not ln.lstrip().startswith("#"))
        self.assertEqual(1, code.count("_group_repeatable_items(\n"),
                         "grouping must be called from exactly one place")
        self.assertEqual(1, code.count("_apply_transcript_safety_layer(final_items, req)"),
                         "the guard seam must exist in exactly one place")

    def test_guards_run_after_grouping_inside_the_finaliser(self):
        """The ordering IS the contract: materialize -> group -> publish
        repeatableGroup -> only then reduce authority.

        Asserted against the CODE with the docstring stripped. The first draft
        of this test compared raw offsets and failed, because the docstring
        names _apply_transcript_safety_layer while explaining the ordering --
        it matched the prose, not the sequence. That is the same self-matching
        mistake this lane has now made six times; the fix is always to assert
        against the executable half."""
        body = self.SRC.split("def _finalize_extracted_items")[1]
        body = body.split("\ndef ")[0]
        # Drop the docstring: everything between the first pair of triple quotes.
        assert body.count('"""') >= 2, "finaliser docstring not found"
        code = body.split('"""', 2)[2]
        self.assertLess(code.index("_group_repeatable_items"),
                        code.index("_apply_transcript_safety_layer"))
        self.assertLess(code.index('item.pop("_repeatableGroup"'),
                        code.index("_apply_transcript_safety_layer"))

    def test_the_bio_fact_router_asymmetry_is_named_not_silently_fixed(self):
        self.assertIn("DELIBERATELY NOT UNIFIED HERE", self.SRC)


if __name__ == "__main__":
    unittest.main()
