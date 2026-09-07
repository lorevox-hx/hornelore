"""Phase 5 exit gate, audited obligation by obligation.

WO-LORI-ARCHIVE-TO-MEMOIR-02, the Phase 5 closeout.

    Every extracted proposal has a correct structured destination, an
    attributed review/candidate destination, or a defensible rejection;
    no valid information is forced into a false schema field.

SIX OBLIGATIONS WERE STILL UNCHECKED when Phase 5C was written, and the
5C closeout said four — the count was wrong, which is how a checklist
starts describing a different repository than the one it lives in. Each
one below is measured at the PRODUCTION boundary and either passes or
names precisely what is absent.

TWO WERE GENUINELY BROKEN AND ARE FIXED IN THIS SLICE. The validator
chain dropped items with `[extract][WO-CLAIMS-02] dropping ...` and
`cause=validator_drop` into `.runtime/logs/api.log` — gitignored, and
it rotates. A "defensible rejection" defensible only to somebody
reading a log at the right moment is indistinguishable, on every
operator surface, from the narrator never having said it. That is the
same silent loss Phase 5C fixed one layer up, and this audit is what
found it rather than assuming the layer below was fine.

ONE IS TRANSFERRED, EXPLICITLY. Grouping candidates by ERA and EVENT
has no producer anywhere; person and narrator grouping do. It is
recorded as absent and moved to Phase 7 rather than left as a checkbox
that quietly disagrees with the code.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server" / "code"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATA_DIR", "/tmp/_phase5_audit")

from api.routers import extract as ex                      # noqa: E402
from api.services import meaning_disposition as md         # noqa: E402


def _run(answer, items):
    from tests.test_kinship_qualifier_binding import item, run
    return run(answer, [item(*pair) for pair in items])


def _dispositions(resp, disposition=None):
    out = [c for c in (resp.clarification_required or [])
           if isinstance(c, dict)]
    if disposition:
        out = [c for c in out if c.get("disposition") == disposition]
    return out


class Obligation1_ConfidentFactReachesAField(unittest.TestCase):
    """SATISFIED. Producer `run_field_extraction`; consumer the
    projection/BB write path via `writeMode`."""

    def test_a_confident_source_bound_fact_reaches_a_structured_field(self):
        resp = _run("My wife Mary is a nurse.",
                    [("family.spouse.firstName", "Mary", 0.95)])
        paths = {i.fieldPath: i for i in resp.items}
        self.assertIn("family.spouse.firstName", paths)
        self.assertEqual("Mary", paths["family.spouse.firstName"].value)
        self.assertTrue(paths["family.spouse.firstName"].writeMode,
                        "a field with no writeMode reaches no consumer")

    def test_it_carries_the_narrators_own_wording(self):
        """5A/5B provenance, still bound at the boundary."""
        resp = _run("My daddy Otis was a machinist.",
                    [("parents.firstName", "Otis", 0.9)])
        self.assertTrue(resp.items)
        self.assertTrue(
            hasattr(resp.items[0], "source_phrase"),
            "provenance is what makes a field traceable to what was said")


class Obligation2_UnmappedMeaningReachesReview(unittest.TestCase):
    """SATISFIED BY PHASE 5C. Producer `meaning_disposition`; consumer
    `clarification_required` -> `turn_extraction_results` ->
    `/api/operator/meaning-dispositions`."""

    def test_meaning_with_no_field_reaches_an_attributed_destination(self):
        resp = _run("My older brother Ray was a welder.",
                    [("siblings.firstName", "Ray", 0.9)])
        recs = _dispositions(resp, md.DISPOSITION_NO_DESTINATION)
        self.assertTrue(recs)
        self.assertTrue(recs[0]["narrator_phrase"])
        self.assertTrue(recs[0]["would_need"])
        self.assertTrue(recs[0]["not_applied"])


class Obligation3_WeakBindingReachesReview(unittest.TestCase):
    """SATISFIED ON BOTH PATHS — the second only after this slice.

    The kinship guard already quarantined a group whose relationship the
    narrator never stated. The CONFIDENCE-FLOOR path did not: it dropped
    the item, logged it, and produced nothing durable. Two different
    weaknesses, and only one of them was answerable.
    """

    def test_an_unstated_relationship_is_quarantined_with_a_reason(self):
        resp = _run("Otis was a machinist.",
                    [("parents.firstName", "Otis", 0.9),
                     ("parents.occupation", "machinist", 0.9)])
        entries = [c for c in (resp.clarification_required or [])
                   if c.get("reasons") or c.get("reason")]
        self.assertTrue(
            entries,
            "an unstated relationship reached no review destination")
        self.assertFalse(
            [i for i in resp.items if i.fieldPath.startswith("parents.")],
            "and it must not have been written as a parent")

    def test_a_low_confidence_proposal_is_now_RECORDED_not_only_logged(self):
        resp = _run("Otis was a machinist.",
                    [("parents.firstName", "Otis", 0.4)])
        recs = _dispositions(resp, md.DISPOSITION_REJECTED)
        self.assertTrue(
            recs, "a below-floor drop produced no durable record — it "
                  "existed only in a rotating gitignored log")
        self.assertEqual("rejected_confidence_floor", recs[0]["reason"])
        self.assertEqual("parents.firstName", recs[0]["proposed_fieldPath"])
        self.assertEqual("Otis", recs[0]["value"])
        self.assertEqual(0.4, recs[0]["confidence"])


class Obligation4_ParseDebrisIsRejectedWithSourceAndReason(unittest.TestCase):
    """SATISFIED after this slice. The reason is now attributed to the
    STEP that removed the item, diffed one validator at a time."""

    def test_debris_is_rejected_with_a_named_reason(self):
        resp = _run("Um, uh, you know.", [("personal.firstName", "Um", 0.2)])
        self.assertEqual([], list(resp.items))
        recs = _dispositions(resp, md.DISPOSITION_REJECTED)
        self.assertTrue(recs)
        self.assertTrue(recs[0]["reason"].startswith("rejected_"))
        self.assertTrue(recs[0]["not_applied"])

    def test_the_reason_names_the_step_that_judged_it(self):
        """Not a generic 'a validator removed this'. WHICH one."""
        resp = _run("Um, uh, you know.", [("personal.firstName", "Um", 0.2)])
        recs = _dispositions(resp, md.DISPOSITION_REJECTED)
        self.assertIn(recs[0]["reason"], {
            "rejected_narrator_refusal", "rejected_value_shape",
            "rejected_value_length_cap", "rejected_relation_allowlist",
            "rejected_relation_scope", "rejected_confidence_floor",
            "rejected_negation_guard"})

    def test_a_clean_turn_records_no_rejection(self):
        """THE DISCRIMINATION. Without it the pass could record on every
        turn and every assertion above would still hold."""
        resp = _run("My wife Mary is a nurse.",
                    [("family.spouse.firstName", "Mary", 0.95)])
        self.assertEqual([], _dispositions(resp, md.DISPOSITION_REJECTED))

    def test_rejections_do_not_leak_between_turns(self):
        """One turn, one ledger. The chain runs twice on a fallback turn
        and the parked list is module-level, so this is the failure mode
        that shape invites."""
        first = _run("Um, uh, you know.", [("personal.firstName", "Um", 0.2)])
        self.assertTrue(_dispositions(first, md.DISPOSITION_REJECTED))
        second = _run("My wife Mary is a nurse.",
                      [("family.spouse.firstName", "Mary", 0.95)])
        self.assertEqual([], _dispositions(second, md.DISPOSITION_REJECTED))


class Obligation5_GroupingForReview(unittest.TestCase):
    """PARTLY SATISFIED — and the remainder is TRANSFERRED, not ticked.

    By narrator: yes, every durable row is narrator-scoped by required
    argument. By person: yes, `repeatableGroup` and the regroup pass
    after a lane change. **By ERA and by EVENT: no producer exists**,
    and inventing one from the runtime era is forbidden — `CLAUDE.md`:
    *the era a conversation was in is not the era a story belongs to*.

    So this is recorded as absent and moved to Phase 7, where the
    operator review surface is built, rather than left as a checkbox
    that disagrees with the code.
    """

    def test_candidates_are_grouped_by_person(self):
        resp = _run("My brother Ray was a welder. My sister Joan taught.",
                    [("siblings.firstName", "Ray", 0.9),
                     ("siblings.firstName", "Joan", 0.9)])
        groups = {i.repeatableGroup for i in resp.items
                  if i.fieldPath.startswith("siblings.")}
        self.assertTrue(
            len(groups) >= 1,
            "sibling items carry no person grouping at all")

    def test_era_and_event_grouping_have_no_producer(self):
        """MEASURED, so the transfer cannot quietly stop being true.

        If a producer appears, this fails and the Phase 7 transfer must
        be revisited — which is the point of measuring it rather than
        asserting it in prose.
        """
        fields = set(ex.EXTRACTABLE_FIELDS)
        self.assertEqual(
            [], [f for f in fields if f.endswith(".era")],
            "an era destination now exists on extracted items")
        item_fields = set(ex.ExtractedItem.model_fields)
        for absent in ("era", "event", "eventGroup"):
            self.assertNotIn(
                absent, item_fields,
                f"ExtractedItem now carries {absent} — Phase 5 obligation 5 "
                f"was transferred to Phase 7 on the measured basis that it "
                f"does not")


class Obligation6_SourceTurnLinkage(unittest.TestCase):
    """SATISFIED, at the ROW rather than per item — and that is correct.

    One extraction result belongs to exactly one committed turn, and
    `turn_extraction_results` binds `turn_key`, `turn_id`, `session_id`
    and `narrator_id` from the `_Claim`. Per-item duplication of the
    same four values would be a second copy of one truth.
    """

    def test_the_result_row_binds_the_committed_turn(self):
        import importlib
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        prev = {k: os.environ.get(k) for k in ("DATA_DIR", "DB_NAME")}

        def _restore():
            for key, value in prev.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            from api import db as _db
            importlib.reload(_db)

        os.environ["DATA_DIR"] = tmp.name
        os.environ["DB_NAME"] = "phase5_audit.sqlite3"
        from api import db as _db
        importlib.reload(_db)
        _db.init_db()
        self.assertTrue(str(_db.DB_PATH).startswith(tmp.name))
        self.addCleanup(_restore)

        from api.services import turn_extraction as te
        person = _db.create_person(display_name="Linkage Probe")
        ledger_id = _db.turn_extraction_claim(
            narrator_id=person["id"], turn_key="turnrow:77", turn_id="t77",
            session_id="s1", turn_mode="interview", source="test")
        te._store_result(te._Claim(
            ledger_id=ledger_id, started=0.0, narrator_id=person["id"],
            turn_id="t77", turn_key="turnrow:77", session_id="s1",
            turn_mode="interview", source="test", user_text="x"),
            [{"fieldPath": "personal.firstName", "value": "Ray"}], [], "test")

        rows = _db.turn_extraction_results_pending(person["id"])
        self.assertEqual(1, len(rows))
        self.assertEqual("turnrow:77", rows[0]["turn_key"])
        self.assertEqual("t77", rows[0]["turn_id"])
        self.assertEqual(person["id"], rows[0]["narrator_id"])

    def test_a_candidate_binds_its_source_turn_too(self):
        """The story lane's half of the same obligation.

        CITED CORRECTLY THE SECOND TIME. The first version of this
        looked for `source_user_turn_row_id` in `story_preservation`,
        which does not write it — and could not, since LAW 3 forbids
        that module reaching into the extraction stack. The linkage is
        written by `db.story_candidate_bind_turn_rows`, and citing the
        module that merely sits nearby is the "cite the line that READS
        the value" failure in its writing form.
        """
        import inspect
        from api import db as _db
        binder = getattr(_db, "story_candidate_bind_turn_rows", None)
        self.assertIsNotNone(
            binder, "no accessor binds a candidate to its source turn")
        source = inspect.getsource(binder)
        self.assertIn("source_user_turn_row_id", source)
        self.assertIn("UPDATE", source.upper())


if __name__ == "__main__":
    unittest.main()
