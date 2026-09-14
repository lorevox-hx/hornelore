"""WO-LOREVOX-PORTABLE-NARRATOR-01 — the exporter's reference closure, extended 2026-09-12.

WHY THIS SUITE EXISTS. The exporter has promised "refuse, never dangle" since §30, and
Phases 2-6 proved it against the references the checker knew about: SQL foreign keys and
declared `ColumnRef`s. The two-origin comparison then found `turns.id` stored in SEVEN
places, of which the checker covered TWO — and a real family package (laptop Christopher)
carrying nine `turn_extraction_ledger` rows whose `turnrow:<turns.id>` keys name turns the
package does not contain. It was structurally valid and semantically incomplete, and every
existing test passed.

The gap was never in the checking LOGIC; it was in what the declaration DESCRIBED. So the
repair is declarative — `narrator_data_inventory.ENCODED_REFERENCES` plus two ColumnRefs
for migration 0047's columns — and these tests prove the exporter enforces it for each
storage form, in both directions:

    turn_extraction_ledger.turn_key    TEXT  'turnrow:<id>'
    turn_extraction_results.turn_key   TEXT  'turnrow:<id>'
    bio_facts.source                   JSON  {"turn_key": "turnrow:<id>"}
    story_candidates.source_user_turn_row_id          INTEGER (0047)
    story_candidates.completed_assistant_turn_row_id  INTEGER (0047)

plus the two cases a naive implementation gets wrong: a MALFORMED encoding must refuse
rather than be skipped, and a legitimately ABSENT reference must not refuse.

Every test asserts the SPECIFIC refusal code and the table/column it names — not merely
that some `ExportRefused` occurred, which would pass even if the exporter refused for an
unrelated reason.

Rows are inserted with the fixture's own `ins()` helper so NOT NULL columns are filled
from the live schema rather than guessed at here.

Run:
    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_narrator_package_encoded_references
"""
from __future__ import annotations

import json
import unittest
from typing import Any, Dict

from tests.test_narrator_package_export import _Fixture          # noqa: F401
from api.services import narrator_data_inventory as inv          # noqa: E402
from api.services import narrator_package as pkg                 # noqa: E402


class TheDeclarationDescribesEveryEncodedForm(unittest.TestCase):
    """The declaration is the authority: a form it does not describe is a form the
    exporter cannot check. These assert the declaration itself, not the exporter."""

    def test_all_three_encoded_references_are_declared_with_a_citation(self):
        got = {(r.table, r.column): r for r in inv.ENCODED_REFERENCES}
        for expected in (("turn_extraction_ledger", "turn_key"),
                         ("turn_extraction_results", "turn_key"),
                         ("bio_facts", "source")):
            self.assertIn(expected, got)
            self.assertTrue(got[expected].cite, f"{expected} needs a source citation")
            self.assertEqual(got[expected].parent_table, "turns")

    def test_the_two_story_candidate_columns_are_now_declared_column_refs(self):
        """0047 added them as bare INTEGERs — SQLite's ALTER cannot add a foreign key —
        so without a ColumnRef the exporter never looked at them."""
        got = {(r.table, r.column) for r in inv.COLUMN_ONLY_REFERENCES}
        self.assertIn(("story_candidates", "source_user_turn_row_id"), got)
        self.assertIn(("story_candidates", "completed_assistant_turn_row_id"), got)

    def test_parsing_belongs_to_the_declaration_not_the_exporter(self):
        led = [r for r in inv.ENCODED_REFERENCES if r.table == "turn_extraction_ledger"][0]
        self.assertEqual(led.parse("turnrow:42"), (42, False))
        self.assertEqual(led.parse(""), (None, False))            # no reference
        self.assertEqual(led.parse(None), (None, False))
        self.assertEqual(led.parse("turnrow:abc"), (None, True))   # malformed
        self.assertEqual(led.parse("something-else:42"), (None, True))

    def test_the_parsed_id_is_an_int_because_the_parent_key_is_an_int(self):
        """Not cosmetic. `turns.id` is INTEGER, so SQLite returns ints; a string here
        made every membership test fail and the checker refused every legitimately
        resolvable reference — i.e. every narrator with extraction history."""
        led = [r for r in inv.ENCODED_REFERENCES if r.table == "turn_extraction_ledger"][0]
        parsed, malformed = led.parse("turnrow:1455")
        self.assertIsInstance(parsed, int)
        self.assertFalse(malformed)

    def test_json_form_reads_the_named_key_and_tolerates_an_absent_one(self):
        fact = [r for r in inv.ENCODED_REFERENCES if r.table == "bio_facts"][0]
        self.assertEqual(fact.parse(json.dumps({"tier": 1, "turn_key": "turnrow:7"})), (7, False))
        # a tier-4 operator entry carries no turn provenance: absence is not an error
        self.assertEqual(fact.parse(json.dumps({"tier": 4, "kind": "operator"})), (None, False))
        self.assertEqual(fact.parse("{}"), (None, False))
        self.assertEqual(fact.parse("not json at all"), (None, True))


class _Encoded(_Fixture):
    """Ada's fixture, whose every semantic reference resolves as shipped — proven by the
    baseline test below. Each test then mutates ONLY the reference form it exercises."""

    def _refused(self, code: str) -> Dict[str, Any]:
        with self.assertRaises(pkg.ExportRefused) as cm:
            self.export()
        reasons = [r for r in cm.exception.reasons if r["code"] == code]
        self.assertTrue(reasons,
                        f"expected refusal {code!r}, got {[r['code'] for r in cm.exception.reasons]}")
        self.assertEqual(list(self.out.glob("*.lorevox.zip")), [],
                         "a refused export left a package behind")
        return reasons[0]

    def _ledger(self, turn_key: str) -> str:
        return self.ins("turn_extraction_ledger", narrator_id=self.ada, turn_key=turn_key)

    def _result(self, turn_key: str) -> str:
        return self.ins("turn_extraction_results", narrator_id=self.ada, turn_key=turn_key)

    def _fact(self, source: str, field_key: str = "birth_place") -> str:
        return self.ins("bio_facts", narrator_id=self.ada, field_key=field_key,
                        value='"x"', source=source)


class TheBaselineFixtureIsClosedUnderTheStrongerInvariant(_Encoded):
    """If this fails, every refusal test below is meaningless — they would be proving
    that a already-broken fixture refuses, not that the mutation refuses."""

    def test_the_unmutated_fixture_still_exports(self):
        res = self.export()
        self.assertTrue(res.package_path.is_file())


class EncodedTextReferences(_Encoded):

    def test_ledger_turnrow_naming_a_missing_turn_refuses_and_names_the_column(self):
        """The exact shape found in the laptop's Christopher package."""
        self._ledger("turnrow:999001")
        self.con.commit()
        r = self._refused("unresolved_reference")
        self.assertEqual(r["table"], "turn_extraction_ledger")
        self.assertEqual(r["column"], "turn_key")
        self.assertEqual(r["value"], "999001")
        self.assertEqual(r["parent"], "turns")

    def test_ledger_turnrow_naming_a_packaged_turn_passes(self):
        self._ledger(f"turnrow:{self.turn_ids[0]}")
        self.con.commit()
        self.assertTrue(self.export().package_path.is_file())

    def test_result_turnrow_naming_a_missing_turn_refuses(self):
        self._result("turnrow:999002")
        self.con.commit()
        r = self._refused("unresolved_reference")
        self.assertEqual(r["table"], "turn_extraction_results")
        self.assertEqual(r["column"], "turn_key")

    def test_result_turnrow_naming_a_packaged_turn_passes(self):
        self._result(f"turnrow:{self.turn_ids[1]}")
        self.con.commit()
        self.assertTrue(self.export().package_path.is_file())


class EncodedJsonReferences(_Encoded):

    def test_bio_fact_source_json_turn_key_naming_a_missing_turn_refuses(self):
        self._fact(json.dumps({"tier": 1, "turn_key": "turnrow:999003"}))
        self.con.commit()
        r = self._refused("unresolved_reference")
        self.assertEqual(r["table"], "bio_facts")
        self.assertEqual(r["column"], "source")
        self.assertEqual(r["value"], "999003")

    def test_bio_fact_source_json_turn_key_naming_a_packaged_turn_passes(self):
        self._fact(json.dumps({"tier": 1, "turn_key": f"turnrow:{self.turn_ids[0]}"}))
        self.con.commit()
        self.assertTrue(self.export().package_path.is_file())


class StoryCandidateIntegerReferences(_Encoded):
    """Migration 0047's two columns: real references with no SQL FK, invisible to the
    exporter until they were declared."""

    def test_source_turn_reference_naming_a_missing_turn_refuses(self):
        self.con.execute("UPDATE story_candidates SET source_user_turn_row_id=999004 "
                         "WHERE narrator_id=?", (self.ada,))
        self.con.commit()
        r = self._refused("unresolved_reference")
        self.assertEqual(r["table"], "story_candidates")
        self.assertEqual(r["column"], "source_user_turn_row_id")

    def test_completed_turn_reference_naming_a_missing_turn_refuses(self):
        self.con.execute("UPDATE story_candidates SET completed_assistant_turn_row_id=999005 "
                         "WHERE narrator_id=?", (self.ada,))
        self.con.commit()
        r = self._refused("unresolved_reference")
        self.assertEqual(r["column"], "completed_assistant_turn_row_id")

    def test_both_turn_references_naming_packaged_turns_pass(self):
        self.con.execute("UPDATE story_candidates SET source_user_turn_row_id=?, "
                         "completed_assistant_turn_row_id=? WHERE narrator_id=?",
                         (self.turn_ids[0], self.turn_ids[1], self.ada))
        self.con.commit()
        self.assertTrue(self.export().package_path.is_file())


class MalformedAndAbsent(_Encoded):
    """The two cases a naive implementation gets wrong in opposite directions."""

    def test_a_malformed_encoding_refuses_rather_than_being_skipped(self):
        """Silently skipping a value that looks like a reference but does not parse is
        how a broken reference ships. A future producer inventing a second key format is
        caught here, not by a narrator."""
        self._ledger("turnrow:not-a-number")
        self.con.commit()
        r = self._refused("malformed_encoded_reference")
        self.assertEqual(r["table"], "turn_extraction_ledger")
        self.assertEqual(r["column"], "turn_key")
        self.assertIn("turnrow:", r["expected_prefix"])

    def test_an_unrecognised_key_vocabulary_refuses(self):
        self._ledger("someotherformat:12")
        self.con.commit()
        self._refused("malformed_encoded_reference")

    def test_unparseable_json_in_a_reference_column_refuses(self):
        self._fact("this is not json")
        self.con.commit()
        r = self._refused("malformed_encoded_reference")
        self.assertEqual(r["table"], "bio_facts")

    def test_absent_references_do_not_refuse(self):
        """An empty ledger key, a tier-4 operator fact with no turn provenance, and NULL
        story-candidate turn columns must all stay silent — otherwise every ordinary
        narrator would block an export."""
        self._ledger("")
        self._fact(json.dumps({"tier": 4, "kind": "operator"}), field_key="full_legal_name")
        self.con.execute("UPDATE story_candidates SET source_user_turn_row_id=NULL, "
                         "completed_assistant_turn_row_id=NULL WHERE narrator_id=?", (self.ada,))
        self.con.commit()
        self.assertTrue(self.export().package_path.is_file())


class OwnershipIsNeverWidenedByAReference(_Encoded):
    """The rule that keeps this repair honest. A reference pointing outside the
    narrator-owned closure is a REFUSAL — never a reason to pull the row in. Only the
    ownership declaration decides what belongs to a narrator (WO §30)."""

    def test_a_ledger_row_naming_another_narrators_turn_refuses(self):
        bea_turn = self.con.execute(
            "SELECT id FROM turns WHERE conv_id='conv-bea-1'").fetchone()[0]
        self._ledger(f"turnrow:{bea_turn}")
        self.con.commit()
        r = self._refused("unresolved_reference")
        self.assertEqual(r["value"], str(bea_turn))
        self.assertEqual(list(self.out.glob("*.lorevox.zip")), [],
                         "Bea's turn must not have been pulled into Ada's package")


if __name__ == "__main__":
    unittest.main()
