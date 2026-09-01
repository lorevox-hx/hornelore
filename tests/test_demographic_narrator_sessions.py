"""Offline contracts for the demographic narrator UI cohort runner."""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_demographic_cohort_ui_plan as plan  # noqa: E402
import run_narrator_cohort_acceptance as cohort  # noqa: E402


class RealFixturePlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.personas = [p for p in cohort.load_personas(False)
                        if p.get("source") == "harness"]

    def test_all_ten_scripted_demographic_personas_are_present(self):
        self.assertEqual(10, len(self.personas))
        self.assertEqual(set(cohort.COHORT_HARNESSES),
                         {p["harness"] for p in self.personas})

    def test_real_chapters_produce_short_verbatim_excerpts(self):
        eras = 0
        for persona in self.personas:
            for chapter in persona["chapters"]:
                eras += 1
                excerpts = plan.select_excerpts(chapter.text, 1)
                self.assertEqual(1, len(excerpts))
                self.assertIn(excerpts[0], " ".join(chapter.text.split()))
                words = len(excerpts[0].split())
                self.assertGreaterEqual(words, 20)
                self.assertLessEqual(words, 84)
        self.assertEqual(38, eras)

    def test_two_turn_mode_remains_short_and_ordered(self):
        chapter = self.personas[0]["chapters"][0]
        excerpts = plan.select_excerpts(chapter.text, 2)
        self.assertEqual(2, len(excerpts))
        normalized = " ".join(chapter.text.split())
        self.assertLess(normalized.index(excerpts[0]), normalized.index(excerpts[1]))
        self.assertTrue(all(len(x.split()) <= 84 for x in excerpts))

    def test_plan_reads_chapter_text_directly(self):
        source = (ROOT / "scripts" / "build_demographic_cohort_ui_plan.py").read_text(
            encoding="utf-8")
        self.assertIn("text = chapter.text", source)
        self.assertNotIn('getattr(chapter, "narrator_text"', source)

    def test_build_plan_requires_one_journaled_uuid_per_source(self):
        """The journal carries the FIXTURE LABEL, not the product name.

        *(This fixture used "ZZ COHORT <run> · Person N", which is the
        PRODUCT display name. `run_narrator_cohort_acceptance.py:1375`
        journals `persona["label"]` — 'Alex Eunseo Park (they/them)' —
        and the ZZ COHORT name is stamped separately at intake via
        preferred_name. Against the real journal the old expectation
        refused all ten narrators and no plan could ever be built. The
        rows here now match what the cohort runner actually writes.)*
        """
        run_id = "r-test"
        rows = []
        personas = {p["harness"]: p for p in cohort.load_personas(quick=False)
                    if p["source"] == "harness"}
        for i, source in enumerate(cohort.COHORT_HARNESSES, start=1):
            rows.append({
                "source": source,
                "person_id": f"00000000-0000-4000-8000-{i:012d}",
                "display_name": personas[source]["label"],
            })
        with tempfile.TemporaryDirectory() as td:
            journal = pathlib.Path(td) / "artifacts.json"
            journal.write_text(json.dumps({"people": rows}), encoding="utf-8")
            with mock.patch.object(plan, "_journal_path", return_value=journal):
                result = plan.build_plan(run_id)
        self.assertEqual(10, result["narrator_count"])
        self.assertEqual(38, result["era_count"])
        self.assertEqual(38, result["narrator_turn_count"])
        # The product-marker check cannot live here — this module takes
        # no --api and does no network. It emits the prefix so the
        # runner, which has the API, can verify the painted card.
        for n in result["narrators"]:
            self.assertEqual(f"ZZ COHORT {run_id} · ", n["product_marker"])

    def test_duplicate_journal_source_is_refused(self):
        source = next(iter(cohort.COHORT_HARNESSES))
        rows = [{"source": source, "person_id": "00000000-0000-4000-8000-000000000001",
                 "display_name": "A"}] * 2
        with tempfile.TemporaryDirectory() as td:
            journal = pathlib.Path(td) / "artifacts.json"
            journal.write_text(json.dumps({"people": rows}), encoding="utf-8")
            with mock.patch.object(plan, "_journal_path", return_value=journal):
                with self.assertRaises(plan.PlanRefusal):
                    plan.build_plan("r-test")


class BrowserRunnerSourceContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "scripts" / "ui" /
                      "run_demographic_narrator_sessions.js").read_text(
                          encoding="utf-8")

    def test_never_creates_or_deletes_a_narrator(self):
        self.assertNotIn("/api/intake", self.source)
        self.assertNotIn("create_narrator", self.source)
        self.assertNotIn("delete-inventory", self.source)
        self.assertNotIn("hard-delete", self.source)

    def test_selection_is_exact_uuid_open_not_position(self):
        self.assertIn('button[onclick*="${narrator.person_id}"]', self.source)
        self.assertIn("await button.count() !== 1", self.source)
        self.assertIn("DESTRUCTIVE.test", self.source)
        self.assertNotIn(".first()", self.source)
        self.assertNotIn(".last()", self.source)

    def test_every_action_waits_for_response_and_tts(self):
        self.assertIn("waitForResponseAndTts", self.source)
        self.assertIn("ttsFinishedAt", self.source)
        self.assertIn("/api/tts/speak_stream", self.source)
        self.assertIn("ttsRows.some((r) => r.ok !== true)", self.source)
        self.assertIn("await waitForAudioIdle(page)", self.source)

    def test_real_composer_and_real_life_map_controls_are_used(self):
        self.assertIn('page.locator("#chatInput")', self.source)
        self.assertIn("await input.type(text", self.source)
        self.assertIn('data-era-id="${era.era_id}"', self.source)
        self.assertIn('modal.locator(".lv-interview-confirm-continue")', self.source)

    def test_real_operator_wrap_up_button_is_clicked(self):
        self.assertIn('page.getByRole("button", { name: "Wrap Up Session"', self.source)
        self.assertIn("await button.click()", self.source)
        self.assertIn("Wrap Up Session produced no archive ZIP", self.source)
        self.assertIn("Wrap Up Session produced no operator log", self.source)

    def test_transcripts_are_exact_session_exports(self):
        self.assertIn("/api/transcript/export/txt", self.source)
        self.assertIn("/api/transcript/export/json", self.source)
        self.assertIn("session_id=${encodeURIComponent(conversationId)}", self.source)
        self.assertIn("validateDurableTranscript", self.source)

    def test_downloads_are_scoped_below_each_narrator(self):
        self.assertIn('path.join(narratorDir, "downloads")', self.source)
        self.assertIn("download.saveAs(target)", self.source)

    def test_checkpoint_drives_resume(self):
        self.assertIn('readJson(path.join(outDir, "checkpoint.json"))', self.source)
        self.assertIn("checkpoint.completedSources.includes", self.source)
        self.assertIn("resume cannot change source run", self.source)


if __name__ == "__main__":
    unittest.main()


class RealJournalBuildsAPlanTests(unittest.TestCase):
    """The check that would have caught this before a live run.

    Every earlier test used a synthetic journal, so none of them
    exercised the shape the cohort runner actually writes.
    """

    RUN = "r20260831-040506-010cd6"

    def setUp(self):
        j = (ROOT / ".runtime" / "eval" / "narrator-cohort"
             / self.RUN / "artifacts.json")
        if not j.is_file():
            self.skipTest(f"source journal {self.RUN} not present locally")

    def test_the_real_journal_produces_the_full_plan(self):
        result = plan.build_plan(self.RUN)
        self.assertEqual(10, result["narrator_count"])
        self.assertEqual(38, result["era_count"])
        self.assertEqual(38, result["narrator_turn_count"])

    def test_every_narrator_carries_the_product_marker(self):
        for n in plan.build_plan(self.RUN)["narrators"]:
            self.assertEqual(f"ZZ COHORT {self.RUN} · ", n["product_marker"])

    def test_the_runner_verifies_identity_by_the_exact_name(self):
        """*(Asserted `startsWith(product_marker)`. That was my own
        regression: all ten narrators share that prefix, so a stale card
        painted with a different cohort narrator satisfied it. The plan
        now carries the exact product name and equality is required.)*"""
        js = (ROOT / "scripts" / "ui"
              / "run_demographic_narrator_sessions.js").read_text(
                  encoding="utf-8")
        self.assertIn("narrator.product_display_name", js)
        self.assertNotIn("text.startsWith(expected.marker)", js)


def _js_code_only(src):
    """JS with comments stripped — a guard must not match its own note."""
    import re
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?m)^\s*//[^\n]*", "", src)


class RunnerReadinessTests(unittest.TestCase):
    """Four defects that would have let a run report COMPLETE wrongly."""

    def setUp(self):
        raw = (ROOT / "scripts" / "ui"
               / "run_demographic_narrator_sessions.js").read_text(
                   encoding="utf-8")
        self.raw = raw
        self.src = _js_code_only(raw)

    # 1 — the correlation id
    def test_it_reads_client_turn_id_not_turn_id(self):
        self.assertIn("lastSent?.params?.client_turn_id", self.src)
        self.assertNotIn("lastSent?.params?.turn_id", self.src)

    def test_the_ui_actually_sends_that_field(self):
        """Non-vacuity: the name must match what app.js puts on the wire."""
        app = (ROOT / "ui" / "js" / "app.js").read_text(
            encoding="utf-8", errors="replace")
        self.assertIn("client_turn_id:_lvCtid", app)

    def test_a_turn_without_a_client_turn_id_is_refused(self):
        self.assertIn("no client turn id on the sent frame", self.src)

    # 2 — exactly one start_turn and one done
    def test_multiple_model_turns_are_refused(self):
        self.assertIn("evidence.sentCount !== 1", self.src)
        self.assertIn("evidence.doneCount !== 1", self.src)

    # 3 — the era actually used
    def test_both_selected_and_sent_era_must_equal_the_intent(self):
        self.assertIn("evidence.selectedEra !== expectedEra", self.src)
        self.assertIn("evidence.sentEra !== expectedEra", self.src)

    def test_the_gate_runs_on_every_action(self):
        """runAction is the single funnel for era prompts and turns."""
        fn = self.src[self.src.index("async function runAction("):]
        self.assertIn("assertActionIntegrity(evidence, expectedEra, what)",
                      fn[:900])

    # 4 — the narrator identity
    def test_identity_requires_the_exact_product_name(self):
        self.assertIn("narrator.product_display_name", self.src)
        self.assertIn('=== expected', self.src)

    def test_the_shared_prefix_check_is_gone(self):
        self.assertNotIn("text.startsWith(expected.marker)", self.src)
        self.assertNotIn("startsWith(narrator.product_marker)", self.src)

    # 5 — the downloads
    def test_downloads_are_waited_for_not_assumed(self):
        self.assertNotIn("waitForTimeout(500)", self.src)
        self.assertIn("requireSuffixes", self.src)
        self.assertIn("wrap-up downloads never arrived", self.src)

    def test_both_artifacts_are_required(self):
        self.assertIn('requireSuffixes = [".zip", ".md"]', self.src)


class PlanCarriesTheExactNameTests(unittest.TestCase):
    RUN = "r20260831-040506-010cd6"

    def setUp(self):
        j = (ROOT / ".runtime" / "eval" / "narrator-cohort" / self.RUN
             / "artifacts.json")
        if not j.is_file():
            self.skipTest(f"source journal {self.RUN} not present locally")
        self.plan = plan.build_plan(self.RUN)

    def test_the_shape_is_unchanged(self):
        self.assertEqual(10, self.plan["narrator_count"])
        self.assertEqual(38, self.plan["era_count"])
        self.assertEqual(38, self.plan["narrator_turn_count"])

    def test_every_narrator_has_a_distinct_product_display_name(self):
        names = [n["product_display_name"] for n in self.plan["narrators"]]
        self.assertEqual(10, len(set(names)),
                         "a shared name would let a stale card pass")

    def test_each_name_is_more_than_the_shared_prefix(self):
        marker = f"ZZ COHORT {self.RUN} · "
        for n in self.plan["narrators"]:
            self.assertTrue(n["product_display_name"].startswith(marker))
            self.assertGreater(len(n["product_display_name"]), len(marker),
                               "the name is only the shared cohort prefix")

    def test_it_matches_what_the_cohort_runner_stamps(self):
        """Derived through the same mark_intake_payload, not guessed."""
        for persona in cohort.load_personas(quick=False):
            if persona["source"] != "harness":
                continue
            marked = cohort.mark_intake_payload(
                dict(persona.get("intake_payload") or {}), self.RUN)
            expected = str(marked.get("preferred_name") or "").strip()
            row = next(n for n in self.plan["narrators"]
                       if n["source"] == persona["harness"])
            self.assertEqual(expected, row["product_display_name"])


class DoneCheckIsHonestlyDescribedTests(unittest.TestCase):
    """The done frame has no client_turn_id; the comment must say so."""

    def test_the_comment_does_not_claim_an_id_matched_done(self):
        raw = (ROOT / "scripts" / "ui"
               / "run_demographic_narrator_sessions.js").read_text(
                   encoding="utf-8")
        self.assertIn("does\n * NOT carry client_turn_id", raw)
        self.assertIn("not an id match on the done frame", raw)

    def test_the_id_is_matched_where_it_exists(self):
        raw = (ROOT / "scripts" / "ui"
               / "run_demographic_narrator_sessions.js").read_text(
                   encoding="utf-8")
        src = _js_code_only(raw)
        self.assertIn("lastSent?.params?.client_turn_id", src)


class SwitcherLifecycleIsObservedNotMaskedTests(unittest.TestCase):
    """Run 20260901T012105Z died at narrator 1 of 10.

    `#lv80NarratorSwitcher` is popover="auto" and the PRODUCT intends to
    close it — ui/hornelore1.0.html:5989, "belt-and-suspenders close here
    covers every path" inside lv80SwitchPerson. It stayed open past 30s
    and overlaid the shell tabs, so Playwright refused to click
    #lvShellTabOperator and never got to act as the outside-click that
    would light-dismiss it.

    My first fix called hidePopover(). That made the run pass while
    HIDING the defect — the harness repairing the product instead of
    measuring it. These tests exist to keep that from coming back.
    """

    def setUp(self):
        raw = (ROOT / "scripts" / "ui"
               / "run_demographic_narrator_sessions.js").read_text(
                   encoding="utf-8")
        self.raw = raw
        self.src = _js_code_only(raw)

    # ── no workarounds ───────────────────────────────────────────────
    def test_it_does_not_call_hide_popover(self):
        self.assertNotIn("hidePopover()", self.src,
                         "calling hidePopover would mask the defect")

    def test_it_does_not_force_or_use_coordinates(self):
        self.assertNotIn("force: true", self.src)
        self.assertNotIn("mouse.click(", self.src)

    # ── recovery only after identity is established ──────────────────
    def test_recovery_runs_after_the_exact_identity_checks(self):
        fn = self.src[self.src.index("async function openExactNarrator"):]
        fn = fn[:fn.index("\nasync function")] if "\nasync function" in fn else fn
        pid = fn.index("window.state?.person_id === pid")
        status = fn.index("narratorOpen?.openStatus")
        name = fn.index("narrator.product_display_name")
        recover = fn.index("resolveSwitcherLifecycle(page)")
        self.assertLess(pid, recover)
        self.assertLess(status, recover)
        self.assertLess(name, recover,
                        "recovering before the name is verified could "
                        "dismiss a popover for a switch that never landed")

    # ── Escape only when it is still open ────────────────────────────
    def test_escape_is_the_dismissal(self):
        fn = self.src[self.src.index("async function resolveSwitcherLifecycle"):]
        self.assertIn('keyboard.press("Escape")', fn[:2500])

    def test_escape_only_after_the_grace_wait_fails(self):
        fn = self.src[self.src.index("async function resolveSwitcherLifecycle"):]
        block = fn[:2500]
        grace = block.index("graceMs })")
        esc = block.index('keyboard.press("Escape")')
        self.assertLess(grace, esc,
                        "Escape must be a recovery, not the first move")

    def test_an_already_closed_switcher_needs_no_recovery(self):
        fn = self.src[self.src.index("async function resolveSwitcherLifecycle"):]
        self.assertIn("switcherAutoClosed: true", fn[:2500])

    # ── it must actually close ───────────────────────────────────────
    def test_it_waits_for_the_popover_to_actually_close(self):
        fn = self.src[self.src.index("async function resolveSwitcherLifecycle"):]
        after_esc = fn[fn.index('keyboard.press("Escape")'):]
        self.assertIn(":popover-open", after_esc[:600])
        self.assertIn("waitForFunction", after_esc[:600])

    # ── the finding is kept ──────────────────────────────────────────
    def test_the_finding_is_recorded_not_discarded(self):
        self.assertIn("switcherAutoClosed: false", self.src)
        self.assertIn("switcherDismissedByHarness: true", self.src)
        self.assertIn("UI LIFECYCLE:", self.raw)
        self.assertIn("NOT repaired", self.raw)

    def test_the_finding_names_the_product_close_that_did_not_fire(self):
        self.assertIn("ui/hornelore1.0.html:5989", self.raw)

    def test_the_verdict_is_downgraded_when_recovery_was_needed(self):
        self.assertIn('"COMPLETE WITH UI FINDINGS"', self.src)
        self.assertIn("uiFindings.length ?", self.src)

    def test_the_product_still_has_the_close_that_did_not_fire(self):
        """Non-vacuity: if this fails the product changed and the
        finding should be re-derived rather than assumed."""
        ui = (ROOT / "ui" / "hornelore1.0.html").read_text(
            encoding="utf-8", errors="replace")
        self.assertIn('if (_sw && _sw.matches && _sw.matches(":popover-open")) '
                      '_sw.hidePopover();', ui)
