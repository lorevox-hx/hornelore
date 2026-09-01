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
        run_id = "r-test"
        rows = []
        for i, source in enumerate(cohort.COHORT_HARNESSES, start=1):
            rows.append({
                "source": source,
                "person_id": f"00000000-0000-4000-8000-{i:012d}",
                "display_name": f"ZZ COHORT {run_id} · Person {i}",
            })
        with tempfile.TemporaryDirectory() as td:
            journal = pathlib.Path(td) / "artifacts.json"
            journal.write_text(json.dumps({"people": rows}), encoding="utf-8")
            with mock.patch.object(plan, "_journal_path", return_value=journal):
                result = plan.build_plan(run_id)
        self.assertEqual(10, result["narrator_count"])
        self.assertEqual(38, result["era_count"])
        self.assertEqual(38, result["narrator_turn_count"])

    def test_duplicate_journal_source_is_refused(self):
        source = next(iter(cohort.COHORT_HARNESSES))
        rows = [{"source": source, "person_id": "00000000-0000-4000-8000-000000000001",
                 "display_name": "ZZ COHORT r-test · A"}] * 2
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
