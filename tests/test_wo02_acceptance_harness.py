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
         {"id": "d2", "n": 2, "date": "2026-07-15"},
         {"id": "d3", "n": 3, "date": "2026-07-16"}]


def link(days, ch="capA", approved=0):
    """A photo-link snapshot entry in SET shape.

    Was a scalar `{"day": "d1", ...}`. WO-TRIP-PHOTO-MULTI-DAY-
    PLACEMENT-01 gave placements their own table, so the harness records
    the day SET and a placement id per day. Sorted, because the set is
    the fact and its order is not — two runs of the same state have to
    produce identical files.
    """
    days = sorted(days)
    return {"days": days,
            "pids": dict((d, "pl-%s-%s" % (ch, d)) for d in days),
            "ch": ch, "approved": approved}


def _baseline():
    return snap(
        _DAYS,
        {"p1": link(["d1"])},
        {"c1": {"day": "d1", "u": 10, "a": 11, "nh": "nA", "lh": "lA",
                "src": "active_trip_day", "st": "needs_day"}},
        {"d1": [["photo", "p1", "pl-capA-d1", "capA"],
                ["conversation", "c1", ""],
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

    def write_checkpoint(self, s=None):
        """Stage B is measured against THIS, not against capture.

        Added 2026-08-13: do_verify used to read the capture baseline,
        so Stage A's work was reported as Stage B's. Every verify test
        now has to supply the checkpoint the real workflow would have
        written.
        """
        cp = dict(s or _baseline())
        cp.setdefault("stage_a", {"removed_placements": [], "new_notes": [],
                                  "edited_kinds": []})
        with open(wo02.STATE_CP, "w", encoding="utf-8") as fh:
            json.dump(cp, fh)
        return cp

    def run_mode(self, fn, *a):
        wo02._reset()
        rc = fn(*a)
        return rc, "\n".join(wo02.LINES), {
            "pass": wo02.PASS[0], "fail": wo02.FAIL[0],
            "skip": wo02.SKIP[0], "attest": wo02.ATTEST[0]}

    def assertFailed(self, log, needle):
        """That LINE failed — not merely that the words appeared.

        Added 2026-08-13 after a mutation survived. `check()` prints its
        message on both branches, so `assertIn("no photo link
        disappeared", log)` passes on a run where the check was forced
        true. The run had other genuine failures, so `fail > 0` passed
        too, and a removed assertion looked exactly like a present one.

        Asserting the PASS/FAIL prefix is what distinguishes them.
        """
        for line in log.split("\n"):
            if line.startswith("FAIL") and needle in line:
                return
        self.fail("expected a FAIL line containing %r.\n%s" % (needle, log))

    def assertPassed(self, log, needle):
        for line in log.split("\n"):
            if line.startswith("PASS") and needle in line:
                return
        self.fail("expected a PASS line containing %r.\n%s" % (needle, log))


class CheckpointTest(_HarnessCase):

    def _stage_a_done(self):
        """Photo removed from its day, day text edited, one note added."""
        return snap(
            _DAYS,
            {"p1": link([])},
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
        self.assertEqual(cp["stage_a"]["removed_placements"],
            [{"link": "p1", "before": ["d1"], "after": []}])
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
        cp["stage_a"] = {"removed_placements": [{"link": "p1", "before": ["d1"], "after": []}], "new_notes": ["n9"],
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
        bad["photo_links"]["p1_copy"] = {"days": ["d1"], "pids": {},
                                        "ch": "capA",
                                         "approved": 0}
        rc, logs, n = self.run_mode(wo02.do_restore_verify, bad, [], "T")
        self.assertEqual(rc, 1)
        self.assertIn("no duplicate photo link", logs)

    def test_a_photo_left_on_the_wrong_day_fails(self):
        self.write_baseline()
        self._checkpoint_state()
        bad = self._restored()
        bad["photo_links"]["p1"]["days"] = ["d2"]
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
        cp["stage_a"] = {"removed_placements": [{"link": "p1", "before": ["d1"], "after": []}], "new_notes": ["n9"],
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


class MainDispatchAttestationTest(_HarnessCase):
    """`verify --attest` must report the attestation it records.

    THE GAP THIS CLOSES, stated plainly: the 16 tests written with the
    harness all called the do_* functions DIRECTLY and none exercised
    main(). The defect lived in main()'s wiring -- attestation handling
    sat at the call site, after `rc = do_verify(now)` had returned, and
    do_verify returns _verdict(), which prints the summary. So the
    attestation was saved (restore-verify could see it) while the run
    reported "0 attested" and printed its ATTEST line BELOW the verdict
    meant to count it. Testing the decision logic and leaving the mode
    dispatch untested is what allowed that.

    These tests therefore go through main() with real argv, doubling
    only snapshot() -- the single network boundary.
    """

    def _run_main(self, argv, snapshot):
        wo02._reset()
        saved_argv, saved_snap = sys.argv, wo02.snapshot
        sys.argv = ["wo02_acceptance.py"] + argv
        wo02.snapshot = lambda: snapshot
        try:
            rc = wo02.main()
        finally:
            sys.argv, wo02.snapshot = saved_argv, saved_snap
        return rc, "\n".join(wo02.LINES), {
            "pass": wo02.PASS[0], "fail": wo02.FAIL[0],
            "skip": wo02.SKIP[0], "attest": wo02.ATTEST[0]}

    def _seed_checkpoint(self):
        cp = _baseline()
        cp["stage_a"] = {"removed_placements": [], "new_notes": [],
                         "edited_kinds": []}
        with open(wo02.STATE_CP, "w", encoding="utf-8") as fh:
            json.dump(cp, fh)

    def test_verify_attest_reports_the_attestation_it_records(self):
        self.write_baseline()
        self._seed_checkpoint()
        rc, logs, n = self._run_main(
            ["verify", "--attest", "modal-reopen"], _baseline())

        # 1. persisted where restore-verify will look for it
        with open(wo02.STATE_CP, encoding="utf-8") as fh:
            cp = json.load(fh)
        self.assertIn("modal-reopen", cp.get("attestations") or {})
        self.assertEqual(cp["attestations"]["modal-reopen"]["mode"], "verify")

        # 2. the ATTEST line precedes the summary/verdict it is counted in.
        # Anchor on " passed," -- the summary's own text. "=== " matches
        # the "=== WO-02 VERIFY ===" HEADER at index 0, which made this
        # assertion compare against the top of the run and fail on
        # correct code.
        attest_at = logs.index("ATTEST")
        summary_at = logs.index(" passed,")
        self.assertLess(attest_at, summary_at,
                        "the ATTEST line printed after the verdict that "
                        "counts it")
        self.assertLess(attest_at, logs.index("RESULT:"))

        # 3. the summary reports it
        self.assertEqual(n["attest"], 1)
        self.assertIn("1 attested", logs)
        self.assertNotIn("0 attested", logs)

    def test_an_attestation_never_inflates_the_pass_count(self):
        """The rule the whole mechanism exists to protect."""
        self.write_baseline()
        self._seed_checkpoint()
        _, _, without = self._run_main(["verify"], _baseline())
        self.write_baseline()
        self._seed_checkpoint()
        _, logs, with_attest = self._run_main(
            ["verify", "--attest", "modal-reopen"], _baseline())
        self.assertEqual(with_attest["pass"], without["pass"],
                         "an operator attestation was counted as a machine "
                         "PASS")
        self.assertEqual(with_attest["attest"], 1)
        self.assertIn("operator-attested, not machine-verified", logs)

    def test_verify_without_a_checkpoint_refuses_rather_than_falling_back(
            self):
        """REWRITTEN 2026-08-13.

        This asserted that a missing checkpoint printed "--attest
        ignored" and carried on verifying against the ORIGINAL capture.
        That fallback was the defect: comparing Stage B against the
        beginning reports Stage A's work as Stage B's, so a walkthrough
        where Stage B never happened could pass on Stage A alone.

        Verify now refuses, with exit 2 and the command to run. The
        attestation is not recorded either — there is no checkpoint to
        record it in, and inventing one would fabricate the very
        baseline whose absence stopped the run.
        """
        self.write_baseline()  # no checkpoint state written
        rc, logs, n = self._run_main(
            ["verify", "--attest", "modal-reopen"], _baseline())
        self.assertEqual(rc, 2, logs)
        self.assertIn("No checkpoint at", logs)
        self.assertIn("run 'checkpoint'", logs.replace(
            "./scripts/wo02_acceptance.py checkpoint", "run 'checkpoint'"))
        self.assertEqual(n["attest"], 0)
        self.assertEqual(n["pass"], 0,
                         "a refused verify must not report passes")


class ModeValidationTest(_HarnessCase):
    """Recorded because an agent misread this in review: an unknown mode
    has ALWAYS been rejected, never silently treated as `verify`."""

    def test_all_four_plan_modes_are_accepted_and_junk_is_not(self):
        src = _SCRIPT.read_text(encoding="utf-8")
        self.assertIn('modes = ("capture", "checkpoint", "verify", '
                      '"restore-verify")', src)
        self.assertIn("if mode not in modes:", src)

    def test_every_mode_still_has_a_handler(self):
        """The source check above proves the LIST is intact. This proves
        each entry still resolves to something callable, which is the
        half that would break if a revision quietly folded two modes
        together."""
        for fn in ("do_capture", "do_checkpoint", "do_verify",
                   "do_restore_verify"):
            self.assertTrue(callable(getattr(wo02, fn, None)),
                            "%s is gone" % fn)


# ══════════════════════════════════════════════════════════════════════
#  WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01 Phase 4 — set semantics
#
#  The harness measured a photograph's day as ONE nullable value. Under
#  many-to-many that is not merely incomplete: two of its three photo
#  questions become actively wrong, and one of them passes on data it
#  should reject. These tests pin the corrected questions.
# ══════════════════════════════════════════════════════════════════════


class SnapshotReadsTheApiTest(_HarnessCase):
    """`snapshot()` itself, with the network stubbed.

    ADDED 2026-08-13 BECAUSE A MUTATION SURVIVED. Reverting the snapshot
    to the old scalar — `"days": [link["trip_day_id"]]` — killed no
    test, and so did removing the sort. Every other test in this file
    builds its fixtures by hand, so the one function that actually reads
    the API and decides the shape of every state file had no coverage at
    all. The tests were measuring their own fixtures.
    """

    def _stub(self, photo_links, timeline=None):
        cal = {"days": [{"id": "d1", "day_index": 1, "date": "2026-07-14",
                         "row_count": 1}]}
        tl = {"items": timeline if timeline is not None else []}

        def fake_get(path):
            if "/calendar" in path:
                return cal
            if "/timeline" in path:
                return tl
            if "/photo-links" in path:
                return {"photo_links": photo_links}
            raise AssertionError("unexpected path %r" % path)
        return fake_get

    def _with_stub(self, fake_get):
        real = wo02.get
        wo02.get = fake_get
        try:
            return wo02.snapshot()
        finally:
            wo02.get = real

    def test_it_records_the_placement_set_not_the_scalar(self):
        snap_ = self._with_stub(self._stub([{
            "id": "p1",
            # What the server sends for a photograph on TWO days: the
            # derived scalar is null BY RULE.
            "trip_day_id": None,
            "trip_day_ids": ["d3", "d1"],
            "day_placements": [{"id": "plA", "trip_day_id": "d1"},
                               {"id": "plB", "trip_day_id": "d3"}],
            "caption": "c", "caption_approved_for_lori": 0,
        }]))
        entry = snap_["photo_links"]["p1"]
        self.assertEqual(entry["days"], ["d1", "d3"],
                         "the snapshot recorded the null scalar instead "
                         "of the placement set")
        self.assertEqual(entry["pids"], {"d1": "plA", "d3": "plB"})

    def test_the_day_set_is_sorted(self):
        """Two runs of the same state must produce identical files, so
        the set's order cannot leak in from the server's."""
        a = self._with_stub(self._stub([{
            "id": "p1", "trip_day_id": None,
            "trip_day_ids": ["d3", "d1"], "day_placements": [],
            "caption": "c", "caption_approved_for_lori": 0}]))
        b = self._with_stub(self._stub([{
            "id": "p1", "trip_day_id": None,
            "trip_day_ids": ["d1", "d3"], "day_placements": [],
            "caption": "c", "caption_approved_for_lori": 0}]))
        self.assertEqual(a["photo_links"], b["photo_links"])
        self.assertEqual(a["photo_links"]["p1"]["days"], ["d1", "d3"])

    def test_an_unplaced_photo_records_an_empty_set(self):
        snap_ = self._with_stub(self._stub([{
            "id": "p1", "trip_day_id": None, "trip_day_ids": [],
            "day_placements": [], "caption": "c",
            "caption_approved_for_lori": 0}]))
        self.assertEqual(snap_["photo_links"]["p1"]["days"], [])

    def test_a_timeline_photo_row_carries_its_placement_id(self):
        snap_ = self._with_stub(self._stub(
            [], timeline=[{"kind": "photo", "link_id": "p1",
                           "placement_id": "plA", "caption": "c"}]))
        row = snap_["items"]["d1"][0]
        self.assertEqual(row[0], "photo")
        self.assertEqual(row[1], "p1")
        self.assertEqual(row[2], "plA",
                         "the timeline row lost its placement id, so two "
                         "occurrences of one photograph are indistinguishable")


class SnapshotShapeTest(_HarnessCase):

    def test_days_are_sorted_so_two_runs_agree(self):
        a = link(["d3", "d1"])
        b = link(["d1", "d3"])
        self.assertEqual(a["days"], b["days"])
        self.assertEqual(a["days"], ["d1", "d3"])

    def test_days_of_reads_the_new_shape(self):
        self.assertEqual(wo02.days_of(link(["d1", "d3"])), ["d1", "d3"])
        self.assertEqual(wo02.days_of(link([])), [])

    def test_days_of_still_reads_a_pre_migration_snapshot(self):
        """A state file captured before 2026-08-13 carries `day`.
        Refusing it would throw away a real capture; it is read as the
        one-day set it was."""
        self.assertEqual(wo02.days_of({"day": "d1"}), ["d1"])
        self.assertEqual(wo02.days_of({"day": None}), [])

    def test_a_legacy_snapshot_is_detected(self):
        legacy = _baseline()
        legacy["photo_links"]["p1"] = {"day": "d1", "ch": "capA",
                                       "approved": 0}
        self.assertTrue(wo02._snapshot_is_legacy(legacy))
        self.assertFalse(wo02._snapshot_is_legacy(_baseline()))


class MultiDayCheckpointTest(_HarnessCase):
    """One photograph, several days, and the three operations told
    apart."""

    def _two_day_baseline(self):
        s = _baseline()
        s["photo_links"]["p1"] = link(["d1", "d3"])
        s["items"]["d1"] = [["photo", "p1", "pl-capA-d1", "capA"],
                            ["conversation", "c1", ""],
                            ["day_text", "t1", "txtA"]]
        s["items"]["d3"] = [["photo", "p1", "pl-capA-d3", "capA"]]
        s["counts"]["d3"] = {"row_count": 1}
        return s

    def test_a_photo_can_be_on_two_days_at_once(self):
        s = self._two_day_baseline()
        self.assertEqual(wo02.days_of(s["photo_links"]["p1"]), ["d1", "d3"])
        # And it is ONE trip link, not two.
        self.assertEqual(len(s["photo_links"]), 1)

    def test_removing_one_placement_keeps_the_other_and_the_link(self):
        self.write_baseline(self._two_day_baseline())
        after = self._two_day_baseline()
        after["photo_links"]["p1"] = link(["d3"])
        after["items"]["d1"] = [["conversation", "c1", ""],
                                ["day_text", "t1", "txtB"],
                                ["note", "n9", "newnote"]]
        after["counts"]["d1"] = {"row_count": 3}
        rc, log, n = self.run_mode(wo02.do_checkpoint, after, [], "T")
        self.assertEqual(n["fail"], 0, log)
        self.assertIn("lost exactly one day", log)
        self.assertIn("kept every other placement", log)
        self.assertEqual(len(after["photo_links"]), 1)

    def test_losing_BOTH_days_when_one_was_removed_fails(self):
        """Non-vacuity for the test above: the assertion has to be able
        to tell 'one occurrence removed' from 'the photograph swept off
        every day'."""
        self.write_baseline(self._two_day_baseline())
        bad = self._two_day_baseline()
        bad["photo_links"]["p1"] = link([])
        bad["items"]["d1"] = [["conversation", "c1", ""],
                              ["day_text", "t1", "txtB"],
                              ["note", "n9", "newnote"]]
        bad["counts"]["d1"] = {"row_count": 3}
        bad["items"]["d3"] = []
        bad["counts"]["d3"] = {"row_count": 0}
        rc, log, n = self.run_mode(wo02.do_checkpoint, bad, [], "T")
        self.assertGreater(n["fail"], 0, log)
        self.assertIn("lost exactly one day, not 2", log)

    def test_gaining_a_day_is_not_reported_as_a_removal(self):
        """The old scalar test fired FALSELY here: a photograph going
        from one day to two makes the derived scalar go from a day to
        null, which read as 'removed from its day'."""
        self.write_baseline(_baseline())
        grew = _baseline()
        grew["photo_links"]["p1"] = link(["d1", "d3"])
        grew["items"]["d3"] = [["photo", "p1", "pl-capA-d3", "capA"]]
        grew["counts"]["d3"] = {"row_count": 1}
        grew["items"]["d1"] = [["photo", "p1", "pl-capA-d1", "capA"],
                               ["conversation", "c1", ""],
                               ["day_text", "t1", "txtB"],
                               ["note", "n9", "newnote"]]
        grew["counts"]["d1"] = {"row_count": 4}
        rc, log, n = self.run_mode(wo02.do_checkpoint, grew, [], "T")
        self.assertEqual(n["fail"], 0, log)
        self.assertIn("no photo was removed from a day", log)
        self.assertIn("which is Add and not a defect", log)


class MultiDayRestoreTest(_HarnessCase):
    """Restoration returns the COMPLETE original set and deletes nothing
    it was not asked to."""

    def _base(self):
        s = _baseline()
        s["photo_links"]["p1"] = link(["d1", "d3"])
        s["photo_links"]["p2"] = link(["d2"], ch="capB")
        s["items"]["d1"] = [["photo", "p1", "pl-capA-d1", "capA"],
                            ["conversation", "c1", ""],
                            ["day_text", "t1", "txtA"]]
        s["items"]["d2"] = [["photo", "p2", "pl-capB-d2", "capB"]]
        s["items"]["d3"] = [["photo", "p1", "pl-capA-d3", "capA"]]
        s["counts"]["d2"] = {"row_count": 1}
        s["counts"]["d3"] = {"row_count": 1}
        return s

    def _cp(self):
        cp = self._base()
        cp["stage_a"] = {"removed_placements": [], "new_notes": [],
                         "edited_kinds": []}
        cp["attestations"] = {"dirty-guard": {"mode": "checkpoint",
                                              "at": "T"},
                              "modal-reopen": {"mode": "verify", "at": "T"}}
        return cp

    def _write(self, cp=None):
        self.write_baseline(self._base())
        with open(wo02.STATE_CP, "w", encoding="utf-8") as fh:
            json.dump(cp or self._cp(), fh)

    def test_a_complete_restore_passes(self):
        self._write()
        rc, log, n = self.run_mode(wo02.do_restore_verify, self._base(),
                                   [], "T")
        self.assertEqual(n["fail"], 0, log)
        self.assertIn("complete original day set", log)

    def test_a_half_restore_fails(self):
        """Back on Day 1 but not Day 3. The OLD scalar assertion could
        not fail this: both the wanted and the got scalar are null when
        the set has two members, so it compared null to null and
        passed."""
        self._write()
        half = self._base()
        half["photo_links"]["p1"] = link(["d1"])
        half["items"]["d3"] = []
        half["counts"]["d3"] = {"row_count": 0}
        rc, log, n = self.run_mode(wo02.do_restore_verify, half, [], "T")
        self.assertGreater(n["fail"], 0, log)
        self.assertIn("wanted ['d1', 'd3'], got ['d1']", log)

    def test_a_restore_to_the_wrong_one_of_two_days_fails(self):
        self._write()
        wrong = self._base()
        wrong["photo_links"]["p1"] = link(["d2"])
        wrong["items"]["d1"] = [["conversation", "c1", ""],
                                ["day_text", "t1", "txtA"]]
        wrong["items"]["d2"] = [["photo", "p2", "pl-capB-d2", "capB"],
                                ["photo", "p1", "pl-capA-d2", "capA"]]
        wrong["items"]["d3"] = []
        wrong["counts"] = dict(
            (d["id"], {"row_count": len(wrong["items"].get(d["id"]) or [])})
            for d in _DAYS)
        rc, log, n = self.run_mode(wo02.do_restore_verify, wrong, [], "T")
        self.assertGreater(n["fail"], 0, log)

    def test_restoring_one_photo_by_unplacing_another_fails(self):
        """The check that no unrelated placement was deleted. Both links
        still exist and both still have days, so every per-link
        comparison except p2's would pass — the total is what catches
        it."""
        self._write()
        robbed = self._base()
        robbed["photo_links"]["p2"] = link([], ch="capB")
        robbed["items"]["d2"] = []
        robbed["counts"]["d2"] = {"row_count": 0}
        rc, log, n = self.run_mode(wo02.do_restore_verify, robbed, [], "T")
        self.assertGreater(n["fail"], 0, log)
        self.assertIn("same number of placements", log)


class WalkthroughNamesTheThreeOperationsTest(_HarnessCase):
    """§8: Add, Remove from this day and Move are explicit operations,
    and the readout tells them apart."""

    def _cp(self, links):
        cp = _baseline()
        cp["photo_links"] = links
        cp["stage_a"] = {"removed_placements": [], "new_notes": [],
                         "edited_kinds": []}
        return cp

    def _run_verify(self, before, after):
        # `before` is the CHECKPOINT — the state Stage A left behind —
        # because Stage B is measured against it and not against the
        # original capture.
        self.write_baseline()
        self.write_checkpoint(self._cp(before))
        rc, log, n = self.run_mode(wo02.do_verify, self._cp(after), [], "T")
        return log, n

    def test_a_grown_set_is_reported_as_Add(self):
        log, n = self._run_verify({"p1": link(["d1"])},
                                  {"p1": link(["d1", "d3"])})
        self.assertIn("1 Add operation(s) seen", log)
        self.assertIn("adding a day kept every day it already had", log)

    def test_a_shrunk_set_is_reported_as_Remove(self):
        log, n = self._run_verify({"p1": link(["d1", "d3"])},
                                  {"p1": link(["d1"])})
        self.assertIn("1 Remove from this day operation(s) seen", log)

    def test_a_same_size_change_is_reported_as_Move(self):
        log, n = self._run_verify({"p1": link(["d1"])},
                                  {"p1": link(["d2"])})
        self.assertIn("1 Move operation(s) seen", log)
        self.assertIn("moving changed the day and kept the count", log)

    def test_an_add_is_not_reported_as_a_move(self):
        """The conflation the old scalar test made unavoidable."""
        log, n = self._run_verify({"p1": link(["d1"])},
                                  {"p1": link(["d1", "d3"])})
        self.assertNotIn("Move operation(s) seen", log)

    def test_the_walkthrough_docstring_names_all_three(self):
        src = _SCRIPT.read_text(encoding="utf-8")
        for phrase in ("Add to this day", "Remove from this day", "Move"):
            self.assertIn(phrase, src)


class VerifyMeasuresAgainstTheCheckpointTest(_HarnessCase):
    """Review correction, 2026-08-13.

    do_verify loaded STATE — the `capture` baseline — so Stage B was
    compared against the world as it was BEFORE Stage A. Every Stage A
    edit therefore read as Stage B evidence, and a walkthrough where
    Stage B never happened could report PASS on Stage A alone.
    """

    def _stage_a(self):
        """What the checkpoint holds: Stage A already done."""
        s = _baseline()
        s["photo_links"]["p1"] = link([])
        s["items"]["d1"] = [["conversation", "c1", ""],
                            ["day_text", "t1", "txtB"],
                            ["note", "n9", "newnote"]]
        s["counts"]["d1"] = {"row_count": 3}
        return s

    def test_stage_a_alone_does_not_satisfy_stage_b(self):
        """THE NON-VACUITY CASE. Capture, then Stage A, then verify with
        Stage B never performed. The world differs from `capture` in
        every way Stage A changed it — and none of that is Stage B.
        Against the checkpoint the correct answer is INCOMPLETE."""
        self.write_baseline()                    # capture
        self.write_checkpoint(self._stage_a())   # after Stage A
        # `now` is unchanged from the checkpoint: Stage B did nothing.
        rc, log, n = self.run_mode(wo02.do_verify, self._stage_a(), [], "T")
        self.assertEqual(n["fail"], 0, log)
        self.assertIn("INCOMPLETE", log)
        self.assertIn("no photo placement changed", log)
        self.assertIn("no note was added", log)

    def test_the_same_run_would_have_looked_like_stage_b_against_capture(self):
        """The defect, demonstrated rather than asserted.

        Feeding the SAME two states to the old comparison — capture as
        the baseline — reports Stage A's removal and Stage A's note as
        Stage B's work. This drives do_verify with the capture state
        written into the checkpoint slot, which is exactly what the old
        code did by reading STATE.
        """
        self.write_baseline()
        self.write_checkpoint(_baseline())       # the OLD (wrong) baseline
        rc, log, n = self.run_mode(wo02.do_verify, self._stage_a(), [], "T")
        self.assertIn("Remove from this day operation(s) seen", log)
        self.assertIn("quick capture created a note", log)

    def test_a_missing_checkpoint_refuses_and_reports_nothing(self):
        self.write_baseline()
        rc, log, n = self.run_mode(wo02.do_verify, _baseline(), [], "T")
        self.assertEqual(rc, 2)
        self.assertEqual(n["pass"], 0)
        self.assertEqual(n["fail"], 0)
        self.assertIn("No checkpoint at", log)
        self.assertIn("checkpoint", log)

    def test_restore_verify_still_measures_against_the_original_capture(self):
        """The other half of the correction: `restore-verify` asks
        whether the ORIGINAL world came back, which is a question about
        capture and not about the checkpoint. It must NOT have been
        repointed."""
        src = _SCRIPT.read_text(encoding="utf-8")
        i = src.index("def do_restore_verify(")
        j = src.index("def do_verify(")
        body = src[i:j] if i < j else src[i:]
        self.assertIn("with open(STATE, encoding=", body,
                      "restore-verify stopped reading the capture state")


class PlacementIdentityIsProvedTest(_HarnessCase):
    """Review correction, 2026-08-13. The day-set assertions compare day
    NAMES. Code that deleted every placement and re-created the
    survivors would satisfy all of them while preserving nothing."""

    def _two_days(self, pids=None):
        e = link(["d1", "d3"])
        if pids:
            e["pids"] = pids
        return e

    def test_a_surviving_placement_that_was_rekeyed_fails(self):
        """The exact hole: Day 3 is still there, with a different row."""
        base = _baseline()
        base["photo_links"]["p1"] = self._two_days()
        base["items"]["d3"] = [["photo", "p1", "pl-capA-d3", "capA"]]
        base["counts"]["d3"] = {"row_count": 1}
        self.write_baseline(base)

        bad = dict(base)
        bad["photo_links"] = {"p1": {"days": ["d3"],
                                     "pids": {"d3": "pl-RECREATED"},
                                     "ch": "capA", "approved": 0}}
        bad["items"] = dict(base["items"])
        bad["items"]["d1"] = [["conversation", "c1", ""],
                              ["day_text", "t1", "txtB"],
                              ["note", "n9", "newnote"]]
        bad["counts"] = dict(base["counts"])
        bad["counts"]["d1"] = {"row_count": 3}
        rc, log, n = self.run_mode(wo02.do_checkpoint, bad, [], "T")
        self.assertFailed(log, "kept the SAME placement row")

    def test_the_same_shape_with_ids_preserved_passes(self):
        """Non-vacuity for the test above."""
        base = _baseline()
        base["photo_links"]["p1"] = self._two_days()
        base["items"]["d3"] = [["photo", "p1", "pl-capA-d3", "capA"]]
        base["counts"]["d3"] = {"row_count": 1}
        self.write_baseline(base)

        good = dict(base)
        good["photo_links"] = {"p1": {"days": ["d3"],
                                      "pids": {"d3": "pl-capA-d3"},
                                      "ch": "capA", "approved": 0}}
        good["items"] = dict(base["items"])
        good["items"]["d1"] = [["conversation", "c1", ""],
                               ["day_text", "t1", "txtB"],
                               ["note", "n9", "newnote"]]
        good["counts"] = dict(base["counts"])
        good["counts"]["d1"] = {"row_count": 3}
        rc, log, n = self.run_mode(wo02.do_checkpoint, good, [], "T")
        self.assertEqual(n["fail"], 0, log)

    def _state(self, links):
        """A whole snapshot whose timeline rows and rail counts AGREE
        with its photo links.

        Built rather than hand-written after the first version moved a
        photograph between days without moving its timeline row — and
        the harness correctly failed on `day counts changed on 0 day(s)`.
        That was the instrument working; a fixture that contradicts
        itself tests nothing but the fixture.
        """
        items = {}
        for d in _DAYS:
            rows = []
            if d["id"] == "d1":
                rows.append(["conversation", "c1", ""])
                rows.append(["day_text", "t1", "txtA"])
            items[d["id"]] = rows
        for lid, entry in links.items():
            for day in entry.get("days") or []:
                items.setdefault(day, []).append(
                    ["photo", lid,
                     (entry.get("pids") or {}).get(day), entry.get("ch")])
        return snap(_DAYS, links,
                    {"c1": {"day": "d1", "u": 10, "a": 11, "nh": "nA",
                            "lh": "lA", "src": "active_trip_day",
                            "st": "needs_day"}},
                    items)

    def _verify_pair(self, before_links, after_links):
        cp = self._state(before_links)
        cp["stage_a"] = {"removed_placements": [], "new_notes": [],
                         "edited_kinds": []}
        self.write_baseline()
        self.write_checkpoint(cp)
        return self.run_mode(wo02.do_verify, self._state(after_links),
                             [], "T")

    def test_add_creates_one_new_row_and_keeps_the_old_one(self):
        rc, log, n = self._verify_pair(
            {"p1": link(["d1"])},
            {"p1": {"days": ["d1", "d3"],
                    "pids": {"d1": "pl-capA-d1", "d3": "pl-NEW"},
                    "ch": "capA", "approved": 0}})
        self.assertEqual(n["fail"], 0, log)
        self.assertPassed(log, "created exactly one placement")
        self.assertPassed(log, "created a NEW placement row")

    def test_an_add_that_reused_an_existing_row_id_fails(self):
        """ADDED after a mutation survived.

        `test_add_creates_one_new_row_and_keeps_the_old_one` asserted
        that the message appears — and it appears whether the check
        passed or failed, so forcing that check to True killed no test.
        Asserting a line is present proves the line is reachable, not
        that the assertion behind it bites.

        This drives the case the assertion exists for: the new day
        carries an id that already belonged to another day, i.e. the row
        was re-pointed rather than created.
        """
        rc, log, n = self._verify_pair(
            {"p1": link(["d1"])},
            {"p1": {"days": ["d1", "d3"],
                    "pids": {"d1": "pl-capA-d1", "d3": "pl-capA-d1"},
                    "ch": "capA", "approved": 0}})
        self.assertFailed(log, "created a NEW placement row")

    def test_a_move_that_kept_the_source_row_id_fails(self):
        """Same shape for Move: the destination must be a new row, and
        the named source must be gone rather than re-pointed."""
        rc, log, n = self._verify_pair(
            {"p1": link(["d1"])},
            {"p1": {"days": ["d2"], "pids": {"d2": "pl-capA-d1"},
                    "ch": "capA", "approved": 0}})
        self.assertFailed(log, "removed the named source placement")

    def test_an_add_that_rewrote_the_existing_row_fails(self):
        rc, log, n = self._verify_pair(
            {"p1": link(["d1"])},
            {"p1": {"days": ["d1", "d3"],
                    "pids": {"d1": "pl-REWRITTEN", "d3": "pl-NEW"},
                    "ch": "capA", "approved": 0}})
        self.assertFailed(log, "left every untouched placement's row alone")

    def test_move_removes_the_source_and_creates_the_destination(self):
        rc, log, n = self._verify_pair(
            {"p1": link(["d1"])},
            {"p1": {"days": ["d2"], "pids": {"d2": "pl-NEW"},
                    "ch": "capA", "approved": 0}})
        self.assertEqual(n["fail"], 0, log)
        self.assertPassed(log, "removed the named source placement")
        self.assertPassed(log, "created the destination placement")

    def test_an_operation_that_disturbs_an_unrelated_photo_fails(self):
        rc, log, n = self._verify_pair(
            {"p1": link(["d1"]), "p2": link(["d2"], ch="capB")},
            {"p1": {"days": ["d1", "d3"],
                    "pids": {"d1": "pl-capA-d1", "d3": "pl-NEW"},
                    "ch": "capA", "approved": 0},
             # p2 was not touched by the operator and must not have moved.
             "p2": {"days": ["d2"], "pids": {"d2": "pl-SOMETHING-ELSE"},
                    "ch": "capB", "approved": 0}})
        self.assertFailed(log,
                          "no unrelated photograph's placement rows were "
                          "rewritten")

    def test_a_current_entry_listing_a_day_with_no_id_fails(self):
        """Review correction, 2026-08-13.

        `rekeyed_days` skipped any day whose id was absent on either
        side, which was right for a HISTORICAL entry and wrong for a
        current one: a set-format entry claiming a photograph is on d1
        while recording no placement row for d1 is malformed, and
        passing it silently is how a snapshot that lost its ids reports
        success.
        """
        rc, log, n = self._verify_pair(
            {"p1": link(["d1"])},
            {"p1": {"days": ["d1", "d3"],
                    "pids": {"d3": "pl-NEW"},        # d1's id is gone
                    "ch": "capA", "approved": 0}})
        self.assertFailed(log, "lists day d1 with no placement id")

    def test_a_surviving_day_that_lost_its_id_fails_as_a_rewrite_too(self):
        """The direct comparison, not the truthiness one: `id -> None`
        is a change like any other."""
        self.assertEqual(
            wo02.rekeyed_days(link(["d1"]),
                              {"days": ["d1"], "pids": {}, "ch": "capA",
                               "approved": 0},
                              ["d1"]),
            [("d1", "pl-capA-d1", "(none)")])

    def test_add_from_zero_days_still_requires_a_destination_id(self):
        """The guard used to be `if b_ids and a_ids`, and `b_ids` is
        empty for a photograph that had NO placements — so the whole
        check was skipped for the commonest Add there is."""
        rc, log, n = self._verify_pair(
            {"p1": link([])},
            {"p1": {"days": ["d1"], "pids": {}, "ch": "capA",
                    "approved": 0}})
        self.assertFailed(log, "recorded a placement row for the new day d1")

    def test_add_from_zero_days_with_an_id_passes(self):
        """Non-vacuity for the test above."""
        rc, log, n = self._verify_pair(
            {"p1": link([])},
            {"p1": {"days": ["d1"], "pids": {"d1": "pl-NEW"},
                    "ch": "capA", "approved": 0}})
        self.assertEqual(n["fail"], 0, log)

    def test_move_with_no_destination_id_fails(self):
        """Pinned to the LINE, not to the run's failure count.

        A missing destination id also trips `missing_pids`, so
        `fail > 0` was satisfied even with the Move-specific check
        forced true — the mutation survived because the test was
        watching the wrong signal.
        """
        rc, log, n = self._verify_pair(
            {"p1": link(["d1"])},
            {"p1": {"days": ["d2"], "pids": {}, "ch": "capA",
                    "approved": 0}})
        self.assertFailed(
            log, "recorded a placement row for the destination day d2")

    def test_two_days_sharing_one_placement_id_fails(self):
        """Impossible in the database — a placement row has one day — so
        seeing it means the reader collapsed two rows into one, and
        every per-day identity check downstream is comparing a value
        that does not mean what it says."""
        rc, log, n = self._verify_pair(
            {"p1": link(["d1"])},
            {"p1": {"days": ["d1", "d3"],
                    "pids": {"d1": "pl-SAME", "d3": "pl-SAME"},
                    "ch": "capA", "approved": 0}})
        self.assertFailed(log, "same placement id")

    def test_a_vanished_photo_link_is_a_failure_not_a_skip(self):
        """The loudest failure had the quietest answer.

        The classification loop skips anything absent from the
        checkpoint and the unrelated-link sweep iterates `now`, so a
        link DELETED during Stage B appeared in neither: no Add, no
        Remove, no Move, and the run reported SKIP / INCOMPLETE.
        """
        rc, log, n = self._verify_pair(
            {"p1": link(["d1"]), "p2": link(["d2"], ch="capB")},
            {"p1": link(["d1"])})            # p2 deleted outright
        self.assertFailed(log, "no photo link disappeared during Stage B")
        self.assertNotIn("INCOMPLETE", log)

    def test_a_new_trip_membership_is_reported_not_counted_as_an_Add(self):
        rc, log, n = self._verify_pair(
            {"p1": link(["d1"])},
            {"p1": link(["d1"]), "p9": link(["d2"], ch="capC")})
        self.assertIn("new trip membership(s) since the checkpoint", log)
        self.assertFailed(log, "created no second trip link")
        self.assertNotIn("Add operation(s) seen", log)

    def test_a_legacy_snapshot_without_ids_makes_no_identity_claim(self):
        """A pre-migration baseline recorded no placement ids. The
        harness must treat that as 'cannot tell', not as 'rewritten' —
        otherwise a historical comparison manufactures failures about a
        field that never existed."""
        self.assertEqual(
            wo02.rekeyed_days({"day": "d1"}, link(["d1"]), ["d1"]), [])
        self.assertEqual(
            wo02.rekeyed_days(link(["d1"]), {"day": "d1"}, ["d1"]), [])

    def test_restoration_does_not_require_the_original_row_ids(self):
        """Explicitly NOT asserted: the product never promised that
        restoring a photograph to a day reuses the deleted placement
        row. Demanding it would fail a correct restore."""
        base = _baseline()
        base["photo_links"]["p1"] = link(["d1"])
        self.write_baseline(base)
        cp = dict(base)
        cp["stage_a"] = {"removed_placements": [], "new_notes": [],
                         "edited_kinds": []}
        cp["attestations"] = {"dirty-guard": {"mode": "checkpoint", "at": "T"},
                              "modal-reopen": {"mode": "verify", "at": "T"}}
        with open(wo02.STATE_CP, "w", encoding="utf-8") as fh:
            json.dump(cp, fh)

        restored = dict(base)
        restored["photo_links"] = {"p1": {"days": ["d1"],
                                          "pids": {"d1": "pl-BRAND-NEW"},
                                          "ch": "capA", "approved": 0}}
        rc, log, n = self.run_mode(wo02.do_restore_verify, restored, [], "T")
        self.assertEqual(n["fail"], 0, log)
        self.assertIn("complete original day set", log)


class LegacyEvidenceIsMarkedHistoricalTest(_HarnessCase):
    """Requirement 9: a pre-migration capture is still readable, and is
    never presented as current acceptance evidence."""

    def _legacy(self):
        s = _baseline()
        s["photo_links"]["p1"] = {"day": "d1", "ch": "capA", "approved": 0}
        return s

    def test_verify_says_the_baseline_is_historical(self):
        self.write_baseline(self._legacy())
        self.write_checkpoint(self._legacy())
        rc, log, n = self.run_mode(wo02.do_verify, _baseline(), [], "T")
        self.assertIn("HISTORICAL BASELINE", log)
        self.assertIn("SINGLE-DAY product", log)

    def test_checkpoint_says_it_too(self):
        self.write_baseline(self._legacy())
        rc, log, n = self.run_mode(wo02.do_checkpoint, _baseline(), [], "T")
        self.assertIn("HISTORICAL BASELINE", log)

    def test_a_current_baseline_says_nothing_of_the_sort(self):
        """Non-vacuity: the notice must not print on every run."""
        self.write_baseline(_baseline())
        self.write_checkpoint(_baseline())
        rc, log, n = self.run_mode(wo02.do_verify, _baseline(), [], "T")
        self.assertNotIn("HISTORICAL", log)

    def test_the_notice_is_not_a_failure(self):
        """It is a caveat about the EVIDENCE, not a defect in the
        product. Counting it as a FAIL would make an operator think
        something broke."""
        self.write_baseline(self._legacy())
        before = wo02.FAIL[0]
        wo02.warn_if_legacy(self._legacy(), "verify")
        self.assertEqual(wo02.FAIL[0], before)


if __name__ == "__main__":
    unittest.main()
