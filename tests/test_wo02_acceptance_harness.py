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

import ast
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


def calendar_counts(rows):
    """The count block a real calendar day serves, for these rows.

    CORRECTED 2026-08-13. The default used to be `{"row_count": len(rows)}`,
    which no calendar has ever served. That single synthetic key made the
    rail-count checks pass on every fixture while the production shape --
    four component lanes plus an `item_count` that is their sum, with
    `day_text` deliberately outside it -- went entirely unexercised. A
    fixture that is easier than production tests the fixture.
    """
    kinds = {}
    for r in rows:
        kinds[str(r[0])] = kinds.get(str(r[0]), 0) + 1
    block = {"conversation_count": kinds.get("conversation", 0),
             "photo_count": kinds.get("photo", 0),
             "note_count": kinds.get("note", 0),
             "source_count": kinds.get("source", 0)}
    block["item_count"] = sum(block.values())
    return block


def snap(days, photo_links, turns, items, counts=None):
    """Build a snapshot in the shape snapshot() returns.

    `counts` defaults to agreeing with `items`, because a disagreement is
    a thing under test (restore-verify checks rail counts against rows)
    and must never appear by accident in a fixture that is not testing it.
    """
    counts = counts or dict(
        (d["id"], calendar_counts(items.get(d["id"]) or [])) for d in days)
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
        s["counts"]["d1"] = calendar_counts(s["items"]["d1"])
        return s

    def _checkpoint_state(self, s=None):
        cp = s if s is not None else _baseline()
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
        """A count lane that contradicts the rows it describes.

        REWRITTEN 2026-08-13. This used to inject `{"row_count": 99}`,
        a key no calendar serves, and passed only because the old check
        summed every `*_count` blindly. Under the real contract that
        block asserts nothing at all, so the test would have gone
        vacuously green -- proving the point it exists to prove.
        """
        self.write_baseline()
        self._checkpoint_state()
        bad = self._restored()
        bad["counts"]["d1"]["photo_count"] += 3
        bad["counts"]["d1"]["item_count"] += 3
        rc, logs, n = self.run_mode(wo02.do_restore_verify, bad, [], "T")
        self.assertEqual(rc, 1)
        self.assertFailed(logs, "photo_count")

    def test_an_unrecognised_count_block_is_reported_not_accepted(self):
        self.write_baseline()
        self._checkpoint_state()
        odd = self._restored()
        odd["counts"]["d1"] = {"row_count": 99}
        rc, logs, n = self.run_mode(wo02.do_restore_verify, odd, [], "T")
        self.assertIn("no recognised count lane", logs)
        # INCOMPLETE, not PASS. An unverifiable day is "not exercised"
        # rather than "broken", so the exit code stays 0 by design --
        # what must not happen is the run claiming that day was checked.
        self.assertIn("RESULT: INCOMPLETE", logs)
        self.assertGreaterEqual(n["skip"], 1)

    def test_item_count_that_omits_a_lane_fails(self):
        """`item_count` is the sum of the four lanes, not a free number."""
        self.write_baseline()
        self._checkpoint_state()
        bad = self._restored()
        bad["counts"]["d1"]["item_count"] -= 1
        rc, logs, n = self.run_mode(wo02.do_restore_verify, bad, [], "T")
        self.assertEqual(rc, 1)
        self.assertFailed(logs, "sum of its four lanes")

    def test_item_count_must_exclude_day_text_rows(self):
        """The day's own typed fields are the day, not items on it.

        Reproduces the shape of Chris's live Bismarck Day 1 after Stage
        A: one conversation, no photographs, three notes, and three
        day_text rows. `item_count` is 4. An implementation that counted
        day_text would say 7, and the old blind-sum check would have
        called that agreement.
        """
        rows = [["conversation", "c1", ""],
                ["note", "n1", "a"], ["note", "n2", "b"],
                ["note", "n3", "c"],
                ["day_text", "d1:main_location", "x"],
                ["day_text", "d1:morning", "y"],
                ["day_text", "d1:afternoon", "z"]]
        counts = calendar_counts(rows)
        self.assertEqual(counts["item_count"], 4,
                         "day_text must stay outside item_count")

        live = snap(_DAYS, {}, {}, {"d1": rows, "d2": [], "d3": []})
        self.write_baseline(live)
        self._checkpoint_state(live)
        rc, logs, n = self.run_mode(wo02.do_restore_verify, live, [], "T")
        self.assertPassed(logs, "excludes the 3 day_text row(s)")

        counted = snap(_DAYS, {}, {}, {"d1": rows, "d2": [], "d3": []})
        counted["counts"]["d1"]["item_count"] = 7
        rc, logs, n = self.run_mode(wo02.do_restore_verify, counted, [], "T")
        self.assertEqual(rc, 1)
        self.assertFailed(logs, "excludes the 3 day_text row(s)")

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
                      '"restore-verify", "plan")', src)
        self.assertIn("if mode not in modes:", src)

    def test_every_mode_still_has_a_handler(self):
        """The source check above proves the LIST is intact. This proves
        each entry still resolves to something callable, which is the
        half that would break if a revision quietly folded two modes
        together."""
        for fn in ("do_capture", "do_checkpoint", "do_verify",
                   "do_restore_verify", "do_plan"):
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
        self.assertPassed(log, "lost 1 day(s); exactly one was expected")
        self.assertPassed(log, "kept every other placement")
        self.assertEqual(len(after["photo_links"]), 1)

    def test_a_passing_readout_never_contradicts_itself(self):
        """Found in the live 2026-08-13 Stage A run, which PASSED and
        printed

            PASS  photo 2a54d793 lost exactly one day, not 1

        `check()` prints ONE message whatever the outcome, and that one
        was written for the failure branch only, so on success it
        contradicted both itself and the number beside it. A readout
        that reads as nonsense when everything is fine teaches the
        operator to stop reading it.

        Scanned rather than string-matched on one phrase: any PASS line
        asserting a quantity must not also carry a "not <n>" clause,
        which is the shape that only makes sense while failing.
        """
        self.write_baseline(self._two_day_baseline())
        after = self._two_day_baseline()
        after["photo_links"]["p1"] = link(["d3"])
        after["items"]["d1"] = [["conversation", "c1", ""],
                                ["day_text", "t1", "txtB"],
                                ["note", "n9", "newnote"]]
        after["counts"]["d1"] = {"row_count": 3}
        rc, log, n = self.run_mode(wo02.do_checkpoint, after, [], "T")
        self.assertEqual(n["fail"], 0, log)
        for line in log.split("\n"):
            if not line.startswith("PASS"):
                continue
            self.assertNotRegex(
                line, r", not \d",
                "a passing line reads as a failure message: %r" % line)
        self.assertPassed(log, "lost 1 day(s); exactly one was expected")

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
        self.assertFailed(log, "lost 2 day(s); exactly one was expected")

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

    def test_the_printed_walkthrough_asks_for_every_operation_verified(self):
        """The instructions and the checks must not drift apart.

        `verify` reports "no Move was performed" when a Move is absent.
        That is only fair if the operator was asked to perform one. This
        pins the two together: every operation the harness classifies is
        an operation the printed walkthrough names.
        """
        text = " ".join(t + " " + d
                        for _k, t, d in wo02.STAGE_B_STEPS).lower()
        for phrase in ("add", "remove from this day", "move"):
            self.assertIn(phrase, text)

    def test_the_walkthrough_covers_the_whole_phase_5_sequence(self):
        wo02._reset()
        wo02.print_stage_b_walkthrough()
        text = "\n".join(wo02.LINES)
        for needle in ("two days", "several photographs",
                       "Remove from this day", "Move...",
                       "caption", "Taken on this date",
                       "hard-reload", "verify --attest modal-reopen",
                       "restore-verify"):
            with self.subTest(step=needle):
                self.assertIn(needle, text)

    def test_the_walkthrough_says_stage_a_needs_no_repeat_work(self):
        """The instruction the corrected instrument makes true.

        Until 2026-08-13 `verify` looked for a CHANGE since the
        checkpoint, so an operator who correctly left Stage A alone was
        told the steps were 'not done'. The text now says the opposite,
        and it is the code that changed to match it.
        """
        wo02._reset()
        wo02.print_stage_b_walkthrough()
        text = "\n".join(wo02.LINES)
        self.assertIn("NO further edit", text)
        self.assertIn("NO second", text)
        self.assertIn("Leaving Stage A's work untouched is the pass", text)

    def test_the_walkthrough_asks_for_the_dirty_guard_on_a_photo_control(self):
        """The attestation must be exercised where the guard was missing.

        Add photos had been guarded all along; Remove, Move and the
        direct date-suggestion Add had not. An attestation collected by
        pressing only the control that already worked proves nothing
        about the three that did not.
        """
        wo02._reset()
        wo02.print_stage_b_walkthrough()
        text = "\n".join(wo02.LINES)
        self.assertIn("WITHOUT saving", text)
        for control in ("Add to this", "Remove from this day", "Move..."):
            with self.subTest(control=control):
                self.assertIn(control, text)


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
        # RETARGETED 2026-08-13. This asserted `created 1 placement(s);
        # exactly one was expected`, which encoded a rule the review
        # retired: an Add may legitimately place a photograph on
        # SEVERAL days, and the walkthrough's own first step asks for
        # exactly that. What still holds is that the new day got a new
        # row and the old one was left alone.
        self.assertPassed(log, "placed it on 1 new day(s)")
        self.assertPassed(log, "created NEW placement rows rather than "
                               "re-pointing")
        self.assertPassed(log, "preserved all 1 placement row(s)")

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
        self.assertFailed(log, "created NEW placement rows rather than "
                               "re-pointing")

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
        self.assertFailed(log, "recorded a placement row for every new day")

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


def _stage_a_pair():
    """(capture, checkpoint) for a Stage A that did all four things.

    Modelled on Chris's live 2026-08-13 walkthrough, including the two
    shapes a row diff cannot see:

      * `t2` is a day-text field that was EMPTY at capture, so no row
        existed to compare against -- the Afternoon field;
      * the caption on `p1` was edited and the photograph was THEN
        removed from d1, so by checkpoint time no d1 photo row survives
        to carry the changed hash.
    """
    cap = snap(
        _DAYS,
        {"p1": link(["d1", "d3"], ch="capA")},
        {"c1": {"day": "d1", "u": 10, "a": 11, "nh": "nA", "lh": "lA",
                "src": "active_trip_day", "st": "needs_day"}},
        {"d1": [["photo", "p1", "pl-capA-d1", "capA"],
                ["conversation", "c1", ""],
                ["day_text", "t1", "txtA"],
                ["note", "n1", "noteA"]],
         "d2": [],
         "d3": [["photo", "p1", "pl-capA-d3", "capA"]]},
    )
    cp = snap(
        _DAYS,
        {"p1": link(["d3"], ch="capB")},
        {"c1": {"day": "d1", "u": 10, "a": 11, "nh": "nA", "lh": "lA",
                "src": "active_trip_day", "st": "needs_day"}},
        {"d1": [["conversation", "c1", ""],
                ["day_text", "t1", "txtB"],
                ["day_text", "t2", "txtNEW"],
                ["note", "n1", "noteB"],
                ["note", "n9", "quickcap"]],
         "d2": [],
         "d3": [["photo", "p1", "pl-capA-d3", "capB"]]},
    )
    cp["photo_links"]["p1"]["pids"] = {"d3": "pl-capA-d3"}
    return cap, cp


class StageAPersistenceIsDerivedTest(_HarnessCase):
    """`verify` proves Stage A's results SURVIVED, not that things changed.

    ADDED 2026-08-13. The old check diffed the checkpoint against now and
    called any difference "edits persisted across the restart". That is
    change, not persistence, and it graded backwards in both directions:
    an operator who restarted and correctly touched nothing was told
    SKIP, while one who edited something unrelated afterwards was told
    PASS. The live run also proved it imprecise -- it reported only
    `Stage A edits landed (note)` although day text and a caption had
    also been edited.
    """

    def _write(self):
        cap, cp = _stage_a_pair()
        self.write_baseline(cap)
        self.write_checkpoint(cp)
        return cap, cp

    def test_the_change_set_finds_all_four_kinds(self):
        cap, cp = _stage_a_pair()
        ch = wo02.stage_a_changeset(cap, cp)
        self.assertEqual([r["id"] for r in ch["notes"]], ["n1"])
        self.assertEqual([r["id"] for r in ch["new_notes"]], ["n9"])
        self.assertEqual([r["link"] for r in ch["captions"]], ["p1"])
        self.assertEqual(sorted(r["id"] for r in ch["day_text"]),
                         ["t1", "t2"],
                         "a day-text field that was EMPTY at capture is a "
                         "Stage A edit, not a row with nothing to compare")

    def test_a_caption_edit_is_seen_even_when_the_photo_left_the_day(self):
        """The live case. A caption lives on the LINK.

        The operator edited the caption and then removed the photograph
        from that day, so the row carrying the changed hash was gone by
        checkpoint time. Reading captions from the timeline rows misses
        it entirely; reading them from photo_links cannot.
        """
        cap, cp = _stage_a_pair()
        for rows in cp["items"].values():
            self.assertFalse([r for r in rows
                              if r[0] == "photo" and r[1] == "p1"
                              and r[-1] == "capA"])
        ch = wo02.stage_a_changeset(cap, cp)
        self.assertEqual(ch["captions"][0]["ch"], "capB")

    def test_an_unchanged_checkpoint_value_is_persistence_and_passes(self):
        """The operator restarts and correctly changes nothing."""
        cap, cp = self._write()
        rc, logs, n = self.run_mode(wo02.do_verify, json.loads(json.dumps(cp)))
        self.assertPassed(logs, "day text t1 on day d1 survived the restart")
        self.assertPassed(logs, "quick-capture note n9")
        self.assertPassed(logs, "still holds its Stage A caption")
        self.assertPassed(logs, "is still off day d1")
        self.assertEqual(n["fail"], 0)

    def test_no_further_edit_is_required_or_rewarded(self):
        """Non-vacuity, in the direction that matters.

        The old instrument SKIPped a run in which nothing changed after
        the checkpoint -- which is exactly what the walkthrough asks for.
        """
        cap, cp = self._write()
        rc, logs, n = self.run_mode(wo02.do_verify, json.loads(json.dumps(cp)))
        self.assertNotIn("no row text changed", logs)
        self.assertIn("Stage A wrote: 2 day-text field(s), 1 note edit(s), "
                      "1 new note(s), 1 caption(s)", logs)

    def test_a_reverted_day_text_field_fails(self):
        cap, cp = self._write()
        now = json.loads(json.dumps(cp))
        now["items"]["d1"][1] = ["day_text", "t1", "txtA"]
        rc, logs, n = self.run_mode(wo02.do_verify, now)
        self.assertEqual(rc, 1)
        self.assertFailed(logs, "day text t1 still holds its checkpoint")

    def test_a_lost_quick_capture_note_fails(self):
        cap, cp = self._write()
        now = json.loads(json.dumps(cp))
        now["items"]["d1"] = [r for r in now["items"]["d1"] if r[1] != "n9"]
        now["counts"]["d1"] = calendar_counts(now["items"]["d1"])
        rc, logs, n = self.run_mode(wo02.do_verify, now)
        self.assertEqual(rc, 1)
        self.assertFailed(logs, "quick-capture note n9 on day d1 survived")

    def test_a_duplicated_note_fails_as_loudly_as_a_missing_one(self):
        cap, cp = self._write()
        now = json.loads(json.dumps(cp))
        now["items"]["d1"].append(["note", "n9", "quickcap"])
        now["counts"]["d1"] = calendar_counts(now["items"]["d1"])
        rc, logs, n = self.run_mode(wo02.do_verify, now)
        self.assertEqual(rc, 1)
        self.assertFailed(logs, "exactly once (found 2)")

    def test_a_reverted_caption_fails(self):
        cap, cp = self._write()
        now = json.loads(json.dumps(cp))
        now["photo_links"]["p1"]["ch"] = "capA"
        now["items"]["d3"] = [["photo", "p1", "pl-capA-d3", "capA"]]
        rc, logs, n = self.run_mode(wo02.do_verify, now)
        self.assertEqual(rc, 1)
        self.assertFailed(logs, "still holds its Stage A caption")

    def test_a_destroyed_placement_row_that_is_resurrected_fails(self):
        """Stage B may re-add the photograph; it may not reuse the row.

        Re-adding is an Add and must mint a NEW placement. If the id
        Stage A destroyed comes back, ids are being reused and every
        identity comparison in this harness is reading a value that
        does not mean what it says -- so this half carries no Stage B
        exemption.
        """
        cap, cp = self._write()
        now = json.loads(json.dumps(cp))
        now["photo_links"]["p1"]["days"] = ["d1", "d3"]
        now["photo_links"]["p1"]["pids"] = {"d1": "pl-capA-d1",
                                            "d3": "pl-capA-d3"}
        now["items"]["d1"].append(["photo", "p1", "pl-capA-d1", "capB"])
        now["counts"]["d1"] = calendar_counts(now["items"]["d1"])
        rc, logs, n = self.run_mode(wo02.do_verify, now)
        self.assertEqual(rc, 1)
        self.assertFailed(logs, "was not resurrected")

    def test_stage_b_may_re_add_the_photograph_with_a_new_row(self):
        cap, cp = self._write()
        now = json.loads(json.dumps(cp))
        now["photo_links"]["p1"]["days"] = ["d1", "d3"]
        now["photo_links"]["p1"]["pids"] = {"d1": "pl-FRESH-d1",
                                            "d3": "pl-capA-d3"}
        now["items"]["d1"].append(["photo", "p1", "pl-FRESH-d1", "capB"])
        now["counts"]["d1"] = calendar_counts(now["items"]["d1"])
        rc, logs, n = self.run_mode(wo02.do_verify, now)
        self.assertPassed(logs, "was not resurrected")
        self.assertPassed(logs, "Add on photo p1")
        self.assertEqual(n["fail"], 0)

    def test_a_surviving_placement_row_that_was_rekeyed_fails(self):
        cap, cp = self._write()
        now = json.loads(json.dumps(cp))
        now["photo_links"]["p1"]["pids"] = {"d3": "pl-DIFFERENT"}
        now["items"]["d3"] = [["photo", "p1", "pl-DIFFERENT", "capB"]]
        rc, logs, n = self.run_mode(wo02.do_verify, now)
        self.assertEqual(rc, 1)
        self.assertFailed(logs, "kept placement row pl-capA- on day d3")

    def test_stage_b_may_move_what_stage_a_placed(self):
        """The exemption, and why it exists.

        Stage B deliberately moves photographs. Without exempting the
        links Stage B touched, the harness would demand a photograph
        stay where Stage A left it while the walkthrough asks the
        operator to move it, and would report that contradiction as a
        product failure. Stage B's own change is proved by the
        Add/Remove/Move classification instead.
        """
        cap, cp = self._write()
        now = json.loads(json.dumps(cp))
        now["photo_links"]["p1"]["days"] = ["d2"]
        now["photo_links"]["p1"]["pids"] = {"d2": "pl-new-d2"}
        now["items"]["d3"] = []
        now["items"]["d2"] = [["photo", "p1", "pl-new-d2", "capB"]]
        now["counts"]["d2"] = calendar_counts(now["items"]["d2"])
        now["counts"]["d3"] = calendar_counts(now["items"]["d3"])
        rc, logs, n = self.run_mode(wo02.do_verify, now)
        self.assertPassed(logs, "Move on photo p1")
        self.assertNotIn("kept placement row pl-capA- on day d3", logs)
        self.assertEqual(n["fail"], 0)

    def test_a_missing_capture_baseline_is_reported_not_assumed(self):
        _cap, cp = _stage_a_pair()
        self.write_checkpoint(cp)          # no capture file written
        rc, logs, n = self.run_mode(wo02.do_verify, json.loads(json.dumps(cp)))
        self.assertIn("Stage A persistence cannot be derived", logs)


class RailCountArithmeticTest(_HarnessCase):
    """Rail counts must follow the placements EXACTLY, not merely change.

    CORRECTED 2026-08-13. The old assertion was `bool(changed)` -- true
    if any day's count dictionary differed at all -- and it was gated on
    a Move or a note, so an Add or a Remove, the two operations most
    likely to move a photo count, activated no verification whatsoever.
    """

    def _pair(self, before_days, after_days, before_pids, after_pids):
        def build(days_map, pids_map):
            items = dict((d["id"], []) for d in _DAYS)
            for d in days_map:
                items[d].append(["photo", "p1", pids_map[d], "capA"])
            s = snap(_DAYS, {"p1": {"days": sorted(days_map), "pids": pids_map,
                                    "ch": "capA", "approved": 0}},
                     {}, items)
            return s
        cp = build(before_days, before_pids)
        now = build(after_days, after_pids)
        self.write_baseline(cp)
        self.write_checkpoint(cp)
        return cp, now

    def test_add_moves_the_destination_count_by_one(self):
        cp, now = self._pair(["d1"], ["d1", "d3"],
                             {"d1": "x1"}, {"d1": "x1", "d3": "x3"})
        rc, logs, n = self.run_mode(wo02.do_verify, now)
        self.assertPassed(logs, "day d3 photo_count moved by +1")
        self.assertPassed(logs, "day d1 photo_count moved by +0")
        self.assertEqual(n["fail"], 0)

    def test_remove_moves_the_source_count_by_minus_one(self):
        cp, now = self._pair(["d1", "d3"], ["d3"],
                             {"d1": "x1", "d3": "x3"}, {"d3": "x3"})
        rc, logs, n = self.run_mode(wo02.do_verify, now)
        self.assertPassed(logs, "day d1 photo_count moved by -1")
        self.assertPassed(logs, "day d3 photo_count moved by +0")
        self.assertEqual(n["fail"], 0)

    def test_move_shifts_one_count_each_way(self):
        cp, now = self._pair(["d1"], ["d2"], {"d1": "x1"}, {"d2": "x2"})
        rc, logs, n = self.run_mode(wo02.do_verify, now)
        self.assertPassed(logs, "day d1 photo_count moved by -1")
        self.assertPassed(logs, "day d2 photo_count moved by +1")
        self.assertPassed(logs, "day d3 photo_count moved by +0")

    def test_move_onto_a_day_it_is_already_on_leaves_that_count_alone(self):
        """The case the arithmetic is easiest to get wrong.

        Under set semantics the destination already holds the
        photograph, so the source loses one and the destination gains
        nothing. A naive "a move shifts one count each way" would demand
        d3 go up and would fail a correct system.
        """
        cp, now = self._pair(["d1", "d3"], ["d3"],
                             {"d1": "x1", "d3": "x3"}, {"d3": "x3"})
        rc, logs, n = self.run_mode(wo02.do_verify, now)
        self.assertPassed(logs, "day d3 photo_count moved by +0")
        self.assertEqual(n["fail"], 0)

    def test_a_count_that_did_not_follow_its_placement_fails(self):
        cp, now = self._pair(["d1"], ["d1", "d3"],
                             {"d1": "x1"}, {"d1": "x1", "d3": "x3"})
        now["counts"]["d3"]["photo_count"] = 0   # rail did not follow
        now["counts"]["d3"]["item_count"] = 0
        rc, logs, n = self.run_mode(wo02.do_verify, now)
        self.assertEqual(rc, 1)
        self.assertFailed(logs, "day d3 photo_count moved by +1")

    def test_an_unrelated_day_that_drifted_fails(self):
        cp, now = self._pair(["d1"], ["d1", "d3"],
                             {"d1": "x1"}, {"d1": "x1", "d3": "x3"})
        now["counts"]["d2"]["photo_count"] = 2
        now["counts"]["d2"]["item_count"] = 2
        rc, logs, n = self.run_mode(wo02.do_verify, now)
        self.assertEqual(rc, 1)
        self.assertFailed(logs, "day d2 photo_count moved by +0")

    def test_the_component_contract_holds_on_the_live_day_1_shape(self):
        """One conversation, no photographs, three notes, three day-text.

        Chris's Bismarck Day 1 after Stage A. `item_count` is 4.
        """
        rows = [["conversation", "c1", ""],
                ["note", "n1", "a"], ["note", "n2", "b"],
                ["note", "n3", "c"],
                ["day_text", "d1:main_location", "x"],
                ["day_text", "d1:morning", "y"],
                ["day_text", "d1:afternoon", "z"]]
        s = snap(_DAYS, {}, {}, {"d1": rows, "d2": [], "d3": []})
        self.assertEqual(s["counts"]["d1"]["item_count"], 4)
        self.assertEqual(s["counts"]["d1"]["note_count"], 3)
        self.assertEqual(s["counts"]["d1"]["photo_count"], 0)
        self.write_baseline(s)
        self.write_checkpoint(s)
        rc, logs, n = self.run_mode(wo02.do_verify,
                                    json.loads(json.dumps(s)))
        self.assertPassed(logs, "day d1: note_count (3) matches its note")
        self.assertPassed(logs, "day d1: item_count excludes the 3 day_text")


class AddMayPlaceAPhotographOnSeveralDaysTest(_HarnessCase):
    """The assertion that contradicted the walkthrough's first step.

    ADDED 2026-08-13 after review. `verify` demanded that an Add create
    EXACTLY ONE fresh placement, while step 1 of the printed
    instructions told the operator to add one photograph to TWO days.
    Following the walkthrough correctly produced a FAIL. That limit is
    the single-day product's rule in set-shaped clothing;
    PLACEMENT_BATCH_MAX caps a REQUEST, not how many days a photograph
    may occupy between two snapshots.
    """

    def _cp(self, links):
        cp = _baseline()
        cp["photo_links"] = links
        cp["stage_a"] = {"removed_placements": [], "new_notes": [],
                         "edited_kinds": []}
        return cp

    def _verify(self, before, after):
        self.write_baseline()
        self.write_checkpoint(self._cp(before))
        return self.run_mode(wo02.do_verify, self._cp(after), [], "T")

    def test_an_unplaced_photograph_may_gain_two_days(self):
        rc, log, n = self._verify(
            {"p1": {"days": [], "pids": {}, "ch": "c", "approved": 0}},
            {"p1": {"days": ["d1", "d2"],
                    "pids": {"d1": "new-1", "d2": "new-2"},
                    "ch": "c", "approved": 0}})
        self.assertPassed(log, "placed it on 2 new day(s)")
        self.assertPassed(log, "gave each new day its OWN placement row")
        self.assertPassed(log, "recorded a placement row for every new day")
        self.assertNotIn("exactly one", log)

    def test_two_new_days_sharing_one_placement_row_fails(self):
        rc, log, n = self._verify(
            {"p1": {"days": [], "pids": {}, "ch": "c", "approved": 0}},
            {"p1": {"days": ["d1", "d2"],
                    "pids": {"d1": "same", "d2": "same"},
                    "ch": "c", "approved": 0}})
        self.assertEqual(rc, 1)
        self.assertFailed(log, "gave each new day its OWN placement row")

    def test_a_new_day_with_no_placement_row_fails(self):
        rc, log, n = self._verify(
            {"p1": {"days": [], "pids": {}, "ch": "c", "approved": 0}},
            {"p1": {"days": ["d1", "d2"], "pids": {"d1": "new-1"},
                    "ch": "c", "approved": 0}})
        self.assertEqual(rc, 1)
        self.assertFailed(log, "recorded a placement row for every new day")

    def test_an_add_that_reuses_an_existing_row_fails(self):
        rc, log, n = self._verify(
            {"p1": {"days": ["d1"], "pids": {"d1": "old-1"},
                    "ch": "c", "approved": 0}},
            {"p1": {"days": ["d1", "d2"],
                    "pids": {"d1": "old-1", "d2": "old-1"},
                    "ch": "c", "approved": 0}})
        self.assertEqual(rc, 1)
        self.assertFailed(log, "created NEW placement rows rather than "
                               "re-pointing")

    def test_an_add_that_rewrites_an_existing_row_fails(self):
        rc, log, n = self._verify(
            {"p1": {"days": ["d1"], "pids": {"d1": "old-1"},
                    "ch": "c", "approved": 0}},
            {"p1": {"days": ["d1", "d2"],
                    "pids": {"d1": "REKEYED", "d2": "new-2"},
                    "ch": "c", "approved": 0}})
        self.assertEqual(rc, 1)
        self.assertFailed(log, "preserved all 1 placement row(s) it already "
                               "had")

    def test_the_count_added_is_reported(self):
        rc, log, n = self._verify(
            {"p1": {"days": [], "pids": {}, "ch": "c", "approved": 0}},
            {"p1": {"days": ["d1", "d2", "d3"],
                    "pids": {"d1": "n1", "d2": "n2", "d3": "n3"},
                    "ch": "c", "approved": 0}})
        self.assertPassed(log, "placed it on 3 new day(s)")


class TheWalkthroughCanActuallyBeCompletedTest(_HarnessCase):
    """One synthetic Stage B, performed exactly as published.

    ADDED 2026-08-13 after review, and it is the test this whole
    correction exists for. Two operator actions `verify` checks -- a
    conversation move and a Stage B quick note -- had dropped out of
    the instructions, and step 1 asked for something the Add assertion
    rejected. The published walkthrough could not reach PASS.

    So: build the checkpoint the plan is derived from, apply exactly
    the changes the plan names, and require zero FAIL and zero SKIP.
    """

    DAYS = [{"id": "d1", "n": 1, "date": "2026-07-14"},
            {"id": "d2", "n": 2, "date": "2026-07-15"},
            {"id": "d3", "n": 3, "date": "2026-07-16"}]

    def _checkpoint(self):
        """Four links, shaped like the live Bismarck fixture."""
        links = {
            "pA": {"days": [], "pids": {}, "ch": "capA", "approved": 0},
            "pB": {"days": ["d3"], "pids": {"d3": "b-d3"},
                   "ch": "capB", "approved": 0},
            "pC": {"days": ["d3"], "pids": {"d3": "c-d3"},
                   "ch": "capC", "approved": 0},
            "pD": {"days": [], "pids": {}, "ch": "capD", "approved": 0},
        }
        return snap(
            self.DAYS, links,
            {"c1": {"day": "d1", "u": 10, "a": 11, "nh": "nA", "lh": "lA",
                    "src": "active_trip_day", "st": "needs_day"}},
            {"d1": [["conversation", "c1", ""],
                    ["day_text", "t1", "txtA"]],
             "d2": [],
             "d3": [["photo", "pB", "b-d3", "capB"],
                    ["photo", "pC", "c-d3", "capC"]]},
        )

    def _capture(self):
        """A pre-Stage-A world, so the Stage A derivation has work.

        Stage A here: typed a day-text field that was empty, and edited
        photo A's caption. Both are shapes a row diff cannot see, which
        is why they are the ones modelled.
        """
        cap = self._checkpoint()
        cap["items"]["d1"] = [["conversation", "c1", ""]]
        cap["counts"]["d1"] = calendar_counts(cap["items"]["d1"])
        cap["photo_links"]["pA"] = dict(cap["photo_links"]["pA"],
                                        ch="capA_before")
        return cap

    def _after_stage_b(self, plan):
        """Replay the plan's steps IN THE PRINTED ORDER.

        REWRITTEN 2026-08-13 after review. This used to assign each
        photograph its final day set directly, which proves the
        endpoint and says nothing about the sequence -- and the defect
        under review WAS a sequence defect: the batch landed on the day
        whose date suggestion the operator still had to accept, so
        step 2 destroyed step 1's affordance while the final state
        looked perfectly correct.

        Applying the operations one at a time, in order, is what makes
        that observable. `suggested` models the one rule that matters
        here: a photograph already on a day is not offered as that
        day's suggestion.
        """
        s = self._checkpoint()
        a, b, c = plan["a"], plan["b"], plan["c"]
        links = s["photo_links"]
        seq = 0

        def place(lid, day_id):
            nonlocal seq
            seq += 1
            v = links[lid]
            if day_id in v["days"]:
                raise AssertionError(
                    "step %d put %s on %s twice -- the plan's order is "
                    "self-defeating" % (seq, lid, day_id))
            v["days"] = sorted(v["days"] + [day_id])
            v["pids"] = dict(v["pids"], **{day_id: "new-%d" % seq})

        def suggested(lid, day_id):
            """Would the interface offer `lid` under Taken on this date?"""
            return day_id not in links[lid]["days"]

        # 1. the date suggestion, FIRST
        sug = plan["suggestion"]
        if not suggested(sug["link"], sug["day"]["id"]):
            raise AssertionError(
                "step 1 cannot run: %s is already on %s, so it is not "
                "offered as that day's suggestion"
                % (sug["link"], sug["day"]["id"]))
        place(sug["link"], sug["day"]["id"])

        # 2. the multi-select batch
        for lid in plan["d"]:
            place(lid, plan["d_day"]["id"])

        # 3. photo A on both of its days
        for d in (a["days"][0]["id"], a["days"][1]["id"]):
            if d not in links[a["link"]]["days"]:
                place(a["link"], d)

        # 4. remove B's one placement
        links[b["link"]] = {
            "days": [d for d in links[b["link"]]["days"] if d != b["day"]["id"]],
            "pids": dict((k, v) for k, v in links[b["link"]]["pids"].items()
                         if k != b["day"]["id"]),
            "ch": links[b["link"]]["ch"], "approved": 0}

        # 5. move C
        links[c["link"]] = {
            "days": sorted([d for d in links[c["link"]]["days"]
                            if d != c["from"]["id"]] + [c["to"]["id"]]),
            "pids": dict(
                [(k, v) for k, v in links[c["link"]]["pids"].items()
                 if k != c["from"]["id"]] + [(c["to"]["id"], "c-moved")]),
            "ch": links[c["link"]]["ch"], "approved": 0}

        # Rebuild every day's timeline from those placements.
        rows = dict((d["id"], []) for d in self.DAYS)
        for lid, v in s["photo_links"].items():
            for day in v["days"]:
                rows[day].append(["photo", lid, v["pids"][day], v["ch"]])
        # The conversation moved d1 -> d2, confirmed by the operator.
        rows["d2"].append(["conversation", "c1", ""])
        s["turns"]["c1"] = {"day": "d2", "u": 10, "a": 11, "nh": "nA",
                            "lh": "lA", "src": "operator_selected",
                            "st": "confirmed"}
        # Stage A's day text survives; Stage B adds exactly one note.
        rows["d1"].append(["day_text", "t1", "txtA"])
        rows["d1"].append(["note", "nB", "stageBnote"])
        s["items"] = rows
        s["counts"] = dict((d["id"], calendar_counts(rows[d["id"]]))
                           for d in self.DAYS)
        return s

    def test_the_published_walkthrough_reaches_pass(self):
        cap, cp = self._capture(), self._checkpoint()
        self.write_baseline(cap)
        self.write_checkpoint(cp)

        plan = wo02.build_stage_b_plan(cp)
        self.assertTrue(plan["ok"], plan["problems"])

        rc, log, n = self.run_mode(
            wo02.do_verify, self._after_stage_b(plan), ["modal-reopen"], "T")

        self.assertEqual(n["fail"], 0, "\n".join(
            l for l in log.splitlines() if l.startswith("FAIL")))
        self.assertEqual(n["skip"], 0, "\n".join(
            l for l in log.splitlines() if l.startswith("SKIP")))
        self.assertEqual(n["attest"], 1)
        self.assertEqual(rc, 0)
        self.assertIn("RESULT: PASS", log)

        # Each behaviour the work order exists to prove, named.
        self.assertPassed(log, "placed it on 2 new day(s)")
        self.assertPassed(log, "adding a day kept every day it already had")
        self.assertPassed(log, "removing a day kept every other day")
        self.assertPassed(log, "moving changed the day and kept the count")
        self.assertPassed(log, "recorded as confirmed operator placement")
        self.assertPassed(log, "Stage B quick capture created a note")
        self.assertPassed(log, "still holds its Stage A caption")
        self.assertPassed(log, "caption is still withheld from Lori")
        self.assertPassed(log, "photo_count moved by")

    def test_the_multi_day_state_is_actually_multi_day(self):
        """Non-vacuity: photo A really ends up on two days."""
        cp = self._checkpoint()
        plan = wo02.build_stage_b_plan(cp)
        after = self._after_stage_b(plan)
        self.assertEqual(len(after["photo_links"][plan["a"]["link"]]["days"]),
                         2)
        self.assertEqual(
            len(set(after["photo_links"][plan["a"]["link"]]["pids"].values())),
            2, "two days must not share one placement row")

    def test_omitting_the_conversation_move_is_reported_not_ignored(self):
        cap, cp = self._capture(), self._checkpoint()
        self.write_baseline(cap)
        self.write_checkpoint(cp)
        plan = wo02.build_stage_b_plan(cp)
        after = self._after_stage_b(plan)
        after["turns"]["c1"]["day"] = "d1"          # never moved
        after["items"]["d1"].append(["conversation", "c1", ""])
        after["items"]["d2"] = [r for r in after["items"]["d2"]
                                if r[0] != "conversation"]
        after["counts"] = dict(
            (d["id"], calendar_counts(after["items"][d["id"]]))
            for d in self.DAYS)
        rc, log, n = self.run_mode(wo02.do_verify, after, [], "T")
        self.assertIn("no conversation was moved", log)
        self.assertGreaterEqual(n["skip"], 1)

    def test_omitting_the_stage_b_note_is_reported_not_ignored(self):
        cap, cp = self._capture(), self._checkpoint()
        self.write_baseline(cap)
        self.write_checkpoint(cp)
        plan = wo02.build_stage_b_plan(cp)
        after = self._after_stage_b(plan)
        after["items"]["d1"] = [r for r in after["items"]["d1"]
                                if r[1] != "nB"]
        after["counts"]["d1"] = calendar_counts(after["items"]["d1"])
        rc, log, n = self.run_mode(wo02.do_verify, after, [], "T")
        self.assertIn("no note was added during Stage B", log)


class WalkthroughCoversEverySkipTest(_HarnessCase):
    """No SKIP may name an action the instructions never asked for.

    A SKIP is the harness saying *you did not do this*. That is only
    fair if the walkthrough asked. Two of them were being reported
    against instructions that had stopped mentioning either.
    """

    def _skip_calls(self, fn_name):
        src = _SCRIPT.read_text(encoding="utf-8")
        tree = ast.parse(src)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == fn_name)
        return [c for c in ast.walk(fn)
                if isinstance(c, ast.Call)
                and getattr(c.func, "id", None) == "skip"]

    def test_every_skip_declares_a_step_or_declares_itself_environmental(self):
        for fn in ("do_verify", "do_checkpoint", "do_restore_verify",
                   "check_count_contract"):
            for call in self._skip_calls(fn):
                kw = {k.arg for k in call.keywords}
                with self.subTest(fn=fn, line=call.lineno):
                    self.assertTrue(
                        ("step" in kw) ^ ("environmental" in kw),
                        "skip() at %s:%d must name exactly one of step= / "
                        "environmental=" % (fn, call.lineno))

    def test_every_named_step_exists_in_the_walkthrough(self):
        keys = set(wo02.STAGE_B_STEP_KEYS)
        for fn in ("do_verify",):
            for call in self._skip_calls(fn):
                for k in call.keywords:
                    # Literal keys are checked here. One call site
                    # passes the loop variable `step_key`; those three
                    # values are pinned by the test below, and skip()
                    # itself raises on an unknown key at runtime.
                    if k.arg == "step" and isinstance(k.value, ast.Constant):
                        with self.subTest(line=call.lineno):
                            self.assertIn(k.value.value, keys)

    def test_the_stage_b_actions_verify_checks_are_all_asked_for(self):
        """Every step key verify can skip on appears in the printed text."""
        wanted = set()
        for call in self._skip_calls("do_verify"):
            for k in call.keywords:
                if k.arg == "step" and isinstance(k.value, ast.Constant):
                    wanted.add(k.value.value)
        # The three placement operations are skipped through a variable
        # (step_key), so name them explicitly rather than pretending the
        # AST saw them.
        wanted |= {"add_two_days", "remove", "move"}
        self.assertTrue(wanted)
        for key in wanted:
            with self.subTest(step=key):
                self.assertIn(key, wo02.STAGE_B_STEP_KEYS)

    def test_skip_refuses_an_unclassified_call(self):
        with self.assertRaises(AssertionError):
            wo02.skip("nobody said which step this is")

    def test_skip_refuses_an_unknown_step(self):
        with self.assertRaises(AssertionError):
            wo02.skip("x", step="not_a_real_step")


class StageBPlanTest(_HarnessCase):
    """`plan` names the actual links, and refuses when it cannot."""

    def _cp(self, links, days=None):
        cp = _baseline()
        cp["days"] = days if days is not None else _DAYS
        cp["photo_links"] = links
        return cp

    def test_each_operation_gets_its_own_photograph(self):
        plan = wo02.build_stage_b_plan(self._cp({
            "u1": {"days": [], "pids": {}, "ch": "", "approved": 0},
            "u2": {"days": [], "pids": {}, "ch": "", "approved": 0},
            "p1": {"days": ["d1"], "pids": {"d1": "x"}, "ch": "", "approved": 0},
            "p2": {"days": ["d1"], "pids": {"d1": "y"}, "ch": "", "approved": 0},
        }))
        self.assertTrue(plan["ok"], plan["problems"])
        chosen = [plan["a"]["link"], plan["b"]["link"], plan["c"]["link"]]
        self.assertEqual(len(set(chosen)), 3,
                         "Add, Remove and Move must not share a photograph")

    def test_the_move_destination_is_a_day_it_is_not_on(self):
        """Not merely a different day from the source.

        STRENGTHENED 2026-08-13: this asserted `to != from`, and a
        mutation replacing the destination search with "any day at all"
        survived it. A Move onto a day the photograph is ALREADY on is
        not a Move under set semantics -- the set does not change size
        or membership, so `verify` would classify it as nothing at all
        and the step would be unprovable. Both placed links start on
        the FIRST day here, so a mutation that ignores the day set
        picks that day and this fails.
        """
        links = {
            "u1": {"days": [], "pids": {}, "ch": "", "approved": 0},
            "u2": {"days": [], "pids": {}, "ch": "", "approved": 0},
            "p1": {"days": ["d1"], "pids": {"d1": "x"}, "ch": "", "approved": 0},
            "p2": {"days": ["d1"], "pids": {"d1": "y"}, "ch": "", "approved": 0},
        }
        plan = wo02.build_stage_b_plan(self._cp(links))
        c = plan["c"]
        self.assertNotIn(c["to"]["id"], links[c["link"]]["days"],
                         "a Move onto a day it is already on changes no set "
                         "and proves nothing")
        self.assertNotEqual(c["to"]["id"], c["from"]["id"])

    def test_a_single_spare_lets_photo_a_join_the_multi_select(self):
        """The live Bismarck shape: one unplaced spare, not two."""
        plan = wo02.build_stage_b_plan(self._cp({
            "u1": {"days": [], "pids": {}, "ch": "", "approved": 0},
            "u2": {"days": [], "pids": {}, "ch": "", "approved": 0},
            "p1": {"days": ["d3"], "pids": {"d3": "x"}, "ch": "", "approved": 0},
            "p2": {"days": ["d3"], "pids": {"d3": "y"}, "ch": "", "approved": 0},
        }))
        self.assertTrue(plan["ok"], plan["problems"])
        self.assertTrue(plan["d_includes_a"])
        self.assertIn(plan["a"]["link"], plan["d"])
        self.assertEqual(len(plan["d"]), 2)

    def test_the_date_suggestion_step_has_a_photograph_and_a_day(self):
        """ADDED 2026-08-13 after review.

        It read "find a photograph under 'Taken on this date'" and
        assigned nothing, while every step that affects placement
        classification named its own photograph. That is how it came to
        collide with the multi-select batch.
        """
        plan = wo02.build_stage_b_plan(self._cp({
            "u1": {"days": [], "pids": {}, "ch": "", "approved": 0},
            "u2": {"days": [], "pids": {}, "ch": "", "approved": 0},
            "p1": {"days": ["d3"], "pids": {"d3": "x"}, "ch": "", "approved": 0},
            "p2": {"days": ["d3"], "pids": {"d3": "y"}, "ch": "", "approved": 0},
        }))
        self.assertTrue(plan["ok"], plan["problems"])
        sug = plan["suggestion"]
        self.assertTrue(sug and sug.get("link") and sug.get("day"))
        self.assertEqual(sug["link"], plan["a"]["link"],
                         "photo A reaches its first day this way")
        self.assertEqual(sug["day"]["id"], plan["a"]["days"][0]["id"])

    def test_when_the_batch_includes_a_it_goes_to_as_second_day(self):
        """The blocking conflict, pinned.

        The batch used to be sent to A's FIRST day — the same day the
        operator has to reach through 'Taken on this date'. A
        photograph already on a day is not offered as that day's
        suggestion, so the batch consumed the affordance the next step
        needed. On the live fixture A IS the Day 1 suggestion, created
        by Stage A's own removal.
        """
        plan = wo02.build_stage_b_plan(self._cp({
            "u1": {"days": [], "pids": {}, "ch": "", "approved": 0},
            "u2": {"days": [], "pids": {}, "ch": "", "approved": 0},
            "p1": {"days": ["d3"], "pids": {"d3": "x"}, "ch": "", "approved": 0},
            "p2": {"days": ["d3"], "pids": {"d3": "y"}, "ch": "", "approved": 0},
        }))
        self.assertTrue(plan["d_includes_a"])
        self.assertNotEqual(plan["d_day"]["id"], plan["suggestion"]["day"]["id"],
                            "the batch must not land on the day whose "
                            "suggestion the operator still has to accept")
        self.assertEqual(plan["d_day"]["id"], plan["a"]["days"][1]["id"])
        self.assertEqual(plan["a_second_via"], "batch")

    def test_the_batch_always_holds_at_least_two_photographs(self):
        for links in (
            {"u1": {"days": [], "pids": {}, "ch": "", "approved": 0},
             "u2": {"days": [], "pids": {}, "ch": "", "approved": 0},
             "p1": {"days": ["d3"], "pids": {"d3": "x"}, "ch": "",
                    "approved": 0},
             "p2": {"days": ["d3"], "pids": {"d3": "y"}, "ch": "",
                    "approved": 0}},
            {"u1": {"days": [], "pids": {}, "ch": "", "approved": 0},
             "u2": {"days": [], "pids": {}, "ch": "", "approved": 0},
             "u3": {"days": [], "pids": {}, "ch": "", "approved": 0},
             "p1": {"days": ["d1"], "pids": {"d1": "x"}, "ch": "",
                    "approved": 0},
             "p2": {"days": ["d2"], "pids": {"d2": "y"}, "ch": "",
                    "approved": 0}},
        ):
            plan = wo02.build_stage_b_plan(self._cp(links))
            with self.subTest(spares=len(links)):
                self.assertTrue(plan["ok"], plan["problems"])
                self.assertGreaterEqual(len(plan["d"]), 2,
                                        "'several photographs' means two")
                self.assertEqual(len(set(plan["d"])), len(plan["d"]))

    def test_following_the_printed_order_leaves_a_on_exactly_two_days(self):
        """Replay the plan's own steps and count A's days at the end."""
        plan = wo02.build_stage_b_plan(self._cp({
            "u1": {"days": [], "pids": {}, "ch": "", "approved": 0},
            "u2": {"days": [], "pids": {}, "ch": "", "approved": 0},
            "p1": {"days": ["d3"], "pids": {"d3": "x"}, "ch": "", "approved": 0},
            "p2": {"days": ["d3"], "pids": {"d3": "y"}, "ch": "", "approved": 0},
        }))
        a = plan["a"]["link"]
        on = set()
        # 1. the date suggestion
        on.add(plan["suggestion"]["day"]["id"])
        # 2. the multi-select batch
        if a in plan["d"]:
            on.add(plan["d_day"]["id"])
        # 3. whatever the second day still needs
        on.add(plan["a"]["days"][1]["id"])
        self.assertEqual(len(on), 2, sorted(on))
        self.assertEqual(on, {plan["a"]["days"][0]["id"],
                              plan["a"]["days"][1]["id"]})

    def test_the_printed_order_puts_the_suggestion_before_the_batch(self):
        keys = list(wo02.STAGE_B_STEP_KEYS)
        self.assertLess(keys.index("date_suggestion"), keys.index("add_several"),
                        "the batch would consume the suggestion")
        self.assertLess(keys.index("add_several"), keys.index("add_two_days"))

    def test_the_precondition_is_printed_as_a_precondition(self):
        """It must not be claimed as derived.

        The snapshot stores days, placement ids, caption hash and
        approval — no `taken_at`. Nothing here can know which day
        suggests which photograph, and saying otherwise would be the
        harness inventing evidence.
        """
        plan = wo02.build_stage_b_plan(self._cp({
            "u1": {"days": [], "pids": {}, "ch": "", "approved": 0},
            "u2": {"days": [], "pids": {}, "ch": "", "approved": 0},
            "p1": {"days": ["d3"], "pids": {"d3": "x"}, "ch": "", "approved": 0},
            "p2": {"days": ["d3"], "pids": {"d3": "y"}, "ch": "", "approved": 0},
        }))
        wo02._reset()
        wo02.print_plan_assignments(plan)
        text = "\n".join(wo02.LINES)
        self.assertIn("PRECONDITION YOU MUST CONFIRM ON SCREEN", text)
        self.assertIn("does NOT record taken_at", text)
        self.assertIn("STOP", text)
        self.assertNotIn("guaranteed", text)
        # And the claim is true rather than merely cautious: the word
        # appears in this module only where the disclaimer says it is
        # absent. If a future revision starts capturing taken_at, this
        # fails and the precondition can become a derived fact.
        src = _SCRIPT.read_text(encoding="utf-8")
        occurrences = [ln for ln in src.splitlines() if "taken_at" in ln]
        self.assertEqual(
            len(occurrences), 2,
            "taken_at is mentioned somewhere new: %s" % occurrences)
        self.assertTrue(all("NOT record" in ln or "does not record" in ln
                            or "does NOT record" in ln for ln in occurrences),
                        occurrences)

    def test_it_refuses_when_no_photograph_is_unplaced(self):
        plan = wo02.build_stage_b_plan(self._cp({
            "p1": {"days": ["d1"], "pids": {"d1": "x"}, "ch": "", "approved": 0},
            "p2": {"days": ["d1"], "pids": {"d1": "y"}, "ch": "", "approved": 0},
        }))
        self.assertFalse(plan["ok"])
        self.assertTrue(any("unplaced" in p for p in plan["problems"]))

    def test_it_refuses_when_a_move_cannot_be_told_from_an_add(self):
        plan = wo02.build_stage_b_plan(self._cp({
            "u1": {"days": [], "pids": {}, "ch": "", "approved": 0},
            "p1": {"days": ["d1"], "pids": {"d1": "x"}, "ch": "", "approved": 0},
        }))
        self.assertFalse(plan["ok"])
        self.assertTrue(any("photo C" in p for p in plan["problems"]))

    def test_it_refuses_a_one_day_trip(self):
        plan = wo02.build_stage_b_plan(self._cp(
            {}, days=[{"id": "d1", "n": 1, "date": "2026-07-14"}]))
        self.assertFalse(plan["ok"])
        self.assertTrue(any("at least two" in p for p in plan["problems"]))

    def test_plan_mode_writes_nothing_and_needs_no_api(self):
        cp = self._cp({
            "u1": {"days": [], "pids": {}, "ch": "", "approved": 0},
            "u2": {"days": [], "pids": {}, "ch": "", "approved": 0},
            "p1": {"days": ["d1"], "pids": {"d1": "x"}, "ch": "", "approved": 0},
            "p2": {"days": ["d2"], "pids": {"d2": "y"}, "ch": "", "approved": 0},
        })
        self.write_checkpoint(cp)
        before = _SCRIPT.read_text(encoding="utf-8")
        raw = json.dumps(json.load(open(wo02.STATE_CP, encoding="utf-8")))
        wo02._reset()
        rc = wo02.do_plan(None)           # `now` is deliberately unused
        self.assertEqual(rc, 0)
        self.assertEqual(
            raw,
            json.dumps(json.load(open(wo02.STATE_CP, encoding="utf-8"))),
            "plan must not rewrite the checkpoint")
        self.assertEqual(before, _SCRIPT.read_text(encoding="utf-8"))

    def test_plan_mode_exits_nonzero_when_the_fixture_cannot_prove_stage_b(self):
        self.write_checkpoint(self._cp({
            "p1": {"days": ["d1"], "pids": {"d1": "x"}, "ch": "", "approved": 0},
        }))
        wo02._reset()
        rc = wo02.do_plan(None)
        self.assertEqual(rc, 2)
        self.assertIn("CANNOT PROVE STAGE B", "\n".join(wo02.LINES))

    def test_plan_is_a_real_mode(self):
        self.assertIn("plan", _SCRIPT.read_text(encoding="utf-8"))
        self.assertIn('"plan"', _SCRIPT.read_text(encoding="utf-8"))


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
