"""The WO-02 acceptance harness must be right before it judges Gate 3.

`scripts/wo02_acceptance.py` is the instrument that decides whether the
Travel Document editable-timeline implementation passes Gate 3. It has
already been wrong once in a way that mattered: an early run reported
"4 passed, 5 failed" when the only thing that had happened was that the
operator had not done the walkthrough yet — the harness manufacturing
the very edits it was supposed to be verifying. That produced the
three-way verdict (PASS / FAIL / SKIP) it has now.

The `checkpoint` and `restore-verify` modes added 2026-08-12 cannot be
exercised from a dev sandbox, because the harness reads a live API on the
operator's machine. So the decision logic is driven here with synthetic
snapshots in exactly the shape `snapshot()` returns. What this proves:
each mode's verdict, that a real defect is reported FAIL, that a step the
operator skipped is reported SKIP and never FAIL, and that an operator
attestation is never counted as machine evidence.

Run per-module:
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_wo02_acceptance_harness
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "wo02_acceptance.py"

_spec = importlib.util.spec_from_file_location("wo02_acceptance", _SCRIPT)
wo02 = importlib.util.module_from_spec(_spec)
sys.modules["wo02_acceptance"] = wo02
_spec.loader.exec_module(wo02)


def snap(days, photo_links, turns, items, counts=None):
    """Build a snapshot in the shape snapshot() returns.

    `counts` defaults to agreeing with `items`, because a disagreement is
    a thing under test (restore-verify checks rail counts against rows)
    and must never appear by accident in a fixture that is not testing it.
    """
    counts = counts or dict(
        (d["id"], {"row_count": len(items.get(d["id"]) or [])}) for d in days)
    return {"days": days, "counts": counts, "photo_links": photo_links,
            "turns": turns, "items": items}


_DAYS = [{"id": "d1", "n": 1, "date": "2026-07-14"},
         {"id": "d2", "n": 2, "date": "2026-07-15"}]


def _baseline():
    return snap(
        _DAYS,
        {"p1": {"day": "d1", "ch": "capA", "approved": 0}},
        {"c1": {"day": "d1", "u": 10, "a": 11, "nh": "nA", "lh": "lA",
                "src": "active_trip_day", "st": "needs_day"}},
        {"d1": [["photo", "p1", "capA"], ["conversation", "c1", ""],
                ["day_text", "t1", "txtA"]],
         "d2": []},
    )


class _HarnessCase(unittest.TestCase):
    """Point the harness's state files at a temp dir and reset counters."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wo02-")
        self._saved = (wo02.STATE, wo02.STATE_CP, wo02.CONSOLE)
        wo02.STATE = os.path.join(self.tmp, "state.json")
        wo02.STATE_CP = os.path.join(self.tmp, "checkpoint.json")
        wo02.CONSOLE = os.path.join(self.tmp, "console_%s.txt")
        wo02._reset()

    def tearDown(self):
        wo02.STATE, wo02.STATE_CP, wo02.CONSOLE = self._saved

    def write_baseline(self, s=None):
        with open(wo02.STATE, "w", encoding="utf-8") as fh:
            json.dump(s or _baseline(), fh)

    def run_mode(self, fn, *a):
        wo02._reset()
        rc = fn(*a)
        return rc, "\n".join(wo02.LINES), {
            "pass": wo02.PASS[0], "fail": wo02.FAIL[0],
            "skip": wo02.SKIP[0], "attest": wo02.ATTEST[0]}


class CheckpointTest(_HarnessCase):

    def _stage_a_done(self):
        """Photo removed from its day, day text edited, one note added."""
        return snap(
            _DAYS,
            {"p1": {"day": None, "ch": "capA", "approved": 0}},
            {"c1": {"day": "d1", "u": 10, "a": 11, "nh": "nA", "lh": "lA",
                    "src": "active_trip_day", "st": "needs_day"}},
            {"d1": [["conversation", "c1", ""], ["day_text", "t1", "txtB"],
                    ["note", "n9", "newnote"]],
             "d2": []},
        )

    def test_stage_a_done_passes_and_writes_the_stage_b_baseline(self):
        self.write_baseline()
        rc, logs, n = self.run_mode(wo02.do_checkpoint,
                                    self._stage_a_done(), [], "T")
        self.assertEqual(rc, 0)
        self.assertEqual(n["fail"], 0, logs)
        self.assertEqual(n["skip"], 0, logs)
        self.assertIn("Stage A held", logs)
        # The Stage B baseline must exist and carry the identities the
        # later modes measure against.
        self.assertTrue(os.path.exists(wo02.STATE_CP))
        with open(wo02.STATE_CP, encoding="utf-8") as fh:
            cp = json.load(fh)
        self.assertEqual(cp["stage_a"]["removed_photo_links"], ["p1"])
        self.assertEqual(cp["stage_a"]["new_notes"], ["n9"])

    def test_nothing_done_is_incomplete_never_failed(self):
        """The original defect: a walkthrough nobody performed must not
        be reported as broken behaviour."""
        self.write_baseline()
        rc, logs, n = self.run_mode(wo02.do_checkpoint, _baseline(), [], "T")
        self.assertEqual(rc, 0)
        self.assertEqual(n["fail"], 0, logs)
        self.assertGreater(n["skip"], 0)
        self.assertIn("INCOMPLETE", logs)

    def test_a_caption_edit_that_grants_approval_fails(self):
        self.write_baseline()
        bad = self._stage_a_done()
        bad["photo_links"]["p1"]["approved"] = 1
        rc, logs, n = self.run_mode(wo02.do_checkpoint, bad, [], "T")
        self.assertEqual(rc, 1)
        self.assertIn("FAIL", logs)
        self.assertIn("approval", logs)

    def test_a_removed_photo_that_lost_its_link_fails(self):
        """'Remove from day' must not be a delete wearing another word."""
        self.write_baseline()
        bad = self._stage_a_done()
        del bad["photo_links"]["p1"]
        rc, logs, n = self.run_mode(wo02.do_checkpoint, bad, [], "T")
        self.assertEqual(rc, 1)
        self.assertIn("disappeared", logs)

    def test_a_rewritten_transcript_fails(self):
        self.write_baseline()
        bad = self._stage_a_done()
        bad["turns"]["c1"]["nh"] = "TAMPERED"
        rc, logs, n = self.run_mode(wo02.do_checkpoint, bad, [], "T")
        self.assertEqual(rc, 1)
        self.assertIn("byte-identical", logs)

    def test_a_duplicated_quick_note_fails(self):
        s = self._stage_a_done()
        s["items"]["d1"].append(["note", "n10", "newnote"])
        s["counts"]["d1"] = {"row_count": len(s["items"]["d1"])}
        self.write_baseline()
        rc, logs, n = self.run_mode(wo02.do_checkpoint, s, [], "T")
        self.assertEqual(rc, 1)
        self.assertIn("exactly once", logs)


class RestoreVerifyTest(_HarnessCase):

    def _restored(self):
        """Everything back where the baseline had it, plus the Stage A note."""
        s = _baseline()
        s["items"]["d1"] = s["items"]["d1"] + [["note", "n9", "newnote"]]
        s["counts"]["d1"] = {"row_count": len(s["items"]["d1"])}
        return s

    def _checkpoint_state(self):
        cp = _baseline()
        cp["stage_a"] = {"removed_photo_links": ["p1"], "new_notes": ["n9"],
                         "edited_kinds": ["day_text"]}
        cp["attestations"] = {"dirty-guard": {"mode": "checkpoint", "at": "T"},
                              "modal-reopen": {"mode": "verify", "at": "T"}}
        with open(wo02.STATE_CP, "w", encoding="utf-8") as fh:
            json.dump(cp, fh)
        return cp

    def test_a_clean_round_trip_passes_gate_3(self):
        self.write_baseline()
        self._checkpoint_state()
        rc, logs, n = self.run_mode(wo02.do_restore_verify,
                                    self._restored(), [], "T")
        self.assertEqual(rc, 0, logs)
        self.assertEqual(n["fail"], 0, logs)
        self.assertEqual(n["skip"], 0, logs)
        self.assertIn("Gate 3 complete", logs)

    def test_a_duplicate_link_from_the_round_trip_fails(self):
        """The strongest identity test: a product re-creating rows rather
        than moving them shows the duplicate here."""
        self.write_baseline()
        self._checkpoint_state()
        bad = self._restored()
        bad["photo_links"]["p1_copy"] = {"day": "d1", "ch": "capA",
                                         "approved": 0}
        rc, logs, n = self.run_mode(wo02.do_restore_verify, bad, [], "T")
        self.assertEqual(rc, 1)
        self.assertIn("no duplicate photo link", logs)

    def test_a_photo_left_on_the_wrong_day_fails(self):
        self.write_baseline()
        self._checkpoint_state()
        bad = self._restored()
        bad["photo_links"]["p1"]["day"] = "d2"
        rc, logs, n = self.run_mode(wo02.do_restore_verify, bad, [], "T")
        self.assertEqual(rc, 1)
        self.assertIn("original day", logs)

    def test_a_lost_stage_a_note_fails(self):
        self.write_baseline()
        self._checkpoint_state()
        bad = _baseline()  # note never restored
        rc, logs, n = self.run_mode(wo02.do_restore_verify, bad, [], "T")
        self.assertEqual(rc, 1)
        self.assertIn("exactly once", logs)

    def test_rail_counts_that_disagree_with_the_rows_fail(self):
        self.write_baseline()
        self._checkpoint_state()
        bad = self._restored()
        bad["counts"]["d1"] = {"row_count": 99}
        rc, logs, n = self.run_mode(wo02.do_restore_verify, bad, [], "T")
        self.assertEqual(rc, 1)
        self.assertIn("rail counts", logs)

    def test_missing_attestations_hold_the_gate_open(self):
        """Two requirements are browser-only. Without them Gate 3 is
        INCOMPLETE, not PASS — the harness must not close a gate on
        evidence it never had."""
        self.write_baseline()
        cp = _baseline()
        cp["stage_a"] = {"removed_photo_links": ["p1"], "new_notes": ["n9"],
                         "edited_kinds": []}
        with open(wo02.STATE_CP, "w", encoding="utf-8") as fh:
            json.dump(cp, fh)
        rc, logs, n = self.run_mode(wo02.do_restore_verify,
                                    self._restored(), [], "T")
        self.assertEqual(n["fail"], 0, logs)
        self.assertGreaterEqual(n["skip"], 2)
        self.assertIn("not attested", logs)
        self.assertIn("INCOMPLETE", logs)


class AttestationTest(_HarnessCase):

    def test_an_attestation_is_never_counted_as_a_pass(self):
        self.write_baseline()
        rc, logs, n = self.run_mode(
            wo02.do_checkpoint, _baseline(), ["dirty-guard"], "T")
        self.assertEqual(n["attest"], 1)
        self.assertIn("operator-attested, not machine-verified", logs)
        self.assertIn("ATTEST", logs)

    def test_attestations_persist_into_the_checkpoint_state(self):
        self.write_baseline()
        self.run_mode(wo02.do_checkpoint, _baseline(),
                      ["dirty-guard", "modal-reopen"], "T")
        with open(wo02.STATE_CP, encoding="utf-8") as fh:
            cp = json.load(fh)
        self.assertEqual(sorted(cp["attestations"]),
                         ["dirty-guard", "modal-reopen"])

    def test_the_attestable_keys_match_the_plan(self):
        self.assertEqual(sorted(wo02.ATTESTABLE),
                         ["dirty-guard", "modal-reopen"])


class ModeValidationTest(_HarnessCase):
    """Recorded because an agent misread this in review: an unknown mode
    has ALWAYS been rejected, never silently treated as `verify`."""

    def test_all_four_plan_modes_are_accepted_and_junk_is_not(self):
        src = _SCRIPT.read_text(encoding="utf-8")
        self.assertIn('modes = ("capture", "checkpoint", "verify", '
                      '"restore-verify")', src)
        self.assertIn("if mode not in modes:", src)


if __name__ == "__main__":
    unittest.main()
