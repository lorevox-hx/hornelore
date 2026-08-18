"""Phase 4: the section classification finally has a production reader.

WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 Phase 4, 2026-08-18.

The composer has classified the system prompt into named sections with a
`required` flag and a `drop_order` since Lean Lori Phase 2A. Nothing in
production ever read that classification: `render()` joined every section
unconditionally, and the budget could drop whole conversation turns and
nothing else. When the mandatory content alone exceeded the window, the
only available answer was to refuse.

Phase 3's live acceptance is what made the gap visible -- it briefly
looked as though a reviewed story had been dropped from an over-budget
prompt, and checking that claim is what revealed the ladder was never
enforced at all.

WHAT THESE TESTS PIN, and why each one exists:

  * The two composer entry points return the same bytes, so exposing the
    structure cannot change what Lori is told.
  * Section removal is a rung BELOW history exhaustion, so no prompt that
    fits today changes at all.
  * Required sections and the complete current narrator turn survive
    every path, including the refusal path.
  * Sections go in the composer's own drop order, lowest first.
  * Telemetry carries identifiers, counts, decisions and digests, and
    never carries prompt text.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "server" / "code"))

from api.prompt_composer import (          # noqa: E402
    _PromptAssembly,
    compose_prompt_sections,
    compose_system_prompt,
    make_section,
    render_sections,
)
from api.services.prompt_budget import (   # noqa: E402
    fit_chat_messages,
    fit_chat_messages_with_sections,
    section_digest,
)

_COMPOSER = _REPO_ROOT / "server" / "code" / "api" / "prompt_composer.py"
_BUDGET = _REPO_ROOT / "server" / "code" / "api" / "services" / "prompt_budget.py"
_API = _REPO_ROOT / "server" / "code" / "api" / "api.py"
_CHAT_WS = _REPO_ROOT / "server" / "code" / "api" / "routers" / "chat_ws.py"

# Word-count stands in for the tokenizer. The REAL counter goes through
# `_apply_chat_template` and needs the model; what these tests are about
# is the DECISION the budget makes given a count, not the count itself.
def _count(msgs):
    return sum(len(m["content"].split()) for m in msgs)


def _assembly():
    asm = _PromptAssembly("system_head", "HEAD " * 50)
    asm.add("identity_facts", "FACTS " * 40, required=True)
    asm.add("memory_context", "MEM " * 60, required=False, drop_order=5)
    asm.add("english_first", "ENG " * 60, required=False, drop_order=20)
    asm.add("approved_stories", "STORY " * 60, required=False, drop_order=25)
    asm.add("pinned_facts", "PIN " * 40, required=False, drop_order=40)
    return asm


def _msgs(sections, *, history=True):
    out = [{"role": "system", "content": render_sections(sections)}]
    if history:
        out += [{"role": "user", "content": "old question " * 5},
                {"role": "assistant", "content": "old answer " * 5}]
    out.append({"role": "user", "content": "CURRENT " * 10})
    return out


class ComposerEntryPointsAgree(unittest.TestCase):
    """Exposing the structure must not change the prompt.

    Byte-equivalence is structural -- both entry points call the same
    `render` -- but it is asserted anyway, across shapes that exercise
    different section sets, because "structural" is a claim about code
    that a later edit can quietly break.
    """

    CASES = [
        ("c1", None, None, None),
        ("c2", 'PROFILE_JSON: {"basics":{"firstName":"Tomasita"}}', "hello", None),
        ("c3", None, "what did I tell you?",
         {"current_era": "early_school_years",
          "story_context": {"available": True, "status": "read",
                            "approved": [{"id": "s", "text": "A story.",
                                          "era": "early_school_years",
                                          "year": 1945,
                                          "placement": "operator_set"}],
                            "approved_count": 1, "provisional_count": 2}}),
        ("c4", None, "hola", {"current_era": "today"}),
    ]

    def test_the_two_entry_points_return_identical_text(self):
        for cid, ui, ut, rt in self.CASES:
            with self.subTest(case=cid):
                a = compose_system_prompt(cid, ui_system=ui, user_text=ut,
                                          runtime71=rt)
                b = compose_prompt_sections(cid, ui_system=ui, user_text=ut,
                                            runtime71=rt)
                self.assertEqual(a, b.text)

    def test_rendering_all_sections_reproduces_the_text(self):
        """The budget renders SUBSETS. If rendering the full set did not
        reproduce the composed text, every subset would be wrong too."""
        for cid, ui, ut, rt in self.CASES:
            with self.subTest(case=cid):
                b = compose_prompt_sections(cid, ui_system=ui, user_text=ut,
                                            runtime71=rt)
                self.assertEqual(b.text, render_sections(b.sections))

    def test_there_is_exactly_one_joiner(self):
        """A second function that knows how a prompt is assembled is a
        second answer to what the prompt says.

        Asserted on what READS SECTIONS, not on the `"\\n\\n".join(`
        string. That string occurs three times in this file -- once in a
        comment quoting the joiner, once in the joiner, and once joining
        pinned-fact fragments INSIDE a single section, which is a
        different operation entirely. A guard written against the literal
        would fire on prose and on unrelated code, which is a mistake
        this repository has made five times and does not need a sixth.
        """
        src = _COMPOSER.read_text(encoding="utf-8")
        # Exactly one expression turns section records into text.
        self.assertEqual(1, src.count("sec.text for sec in"),
                         "more than one place reads section text to join it")
        # And both public paths delegate to it rather than reimplementing.
        self.assertIn("out = _PromptAssembly.join(self._sections)", src)
        self.assertIn("return _PromptAssembly.join(sections)", src)

    def test_the_system_head_is_always_present_and_required(self):
        for cid, ui, ut, rt in self.CASES:
            with self.subTest(case=cid):
                secs = compose_prompt_sections(cid, ui_system=ui,
                                               user_text=ut, runtime71=rt).sections
                head = [s for s in secs if s.name == "system_head"]
                self.assertEqual(1, len(head))
                self.assertTrue(head[0].required)


class SectionRemovalIsBelowHistoryExhaustion(unittest.TestCase):
    """The conservative ordering, which is the whole safety argument.

    Section removal engages only where the previous code REFUSED. That is
    why this change cannot regress a working turn: it converts some
    refusals into graceful degradation and touches nothing else.
    """

    def test_a_prompt_that_fits_is_untouched(self):
        secs = _assembly().sections()
        msgs = _msgs(secs)
        out = fit_chat_messages_with_sections(
            msgs, limit=10_000, count_tokens=_count,
            sections=secs, render_sections=render_sections)
        self.assertTrue(out.fits)
        self.assertEqual("fits", out.reason)
        self.assertEqual(msgs, out.messages)
        self.assertEqual([], out.dropped_sections)

    def test_history_is_dropped_before_any_section(self):
        secs = _assembly().sections()
        msgs = _msgs(secs)
        # A limit that the full prompt misses but that history-trimming
        # alone can reach.
        limit = _count(msgs) - 5
        out = fit_chat_messages_with_sections(
            msgs, limit=limit, count_tokens=_count,
            sections=secs, render_sections=render_sections)
        self.assertTrue(out.fits)
        self.assertEqual([], out.dropped_sections,
                         "a section was dropped while history remained")
        self.assertGreater(out.dropped_turns, 0)

    def test_without_sections_it_is_the_history_only_entry_point(self):
        secs = _assembly().sections()
        msgs = _msgs(secs)
        for limit in (10_000, 300, 120):
            with self.subTest(limit=limit):
                a = fit_chat_messages(msgs, limit=limit, count_tokens=_count)
                b = fit_chat_messages_with_sections(
                    msgs, limit=limit, count_tokens=_count)
                self.assertEqual(a.messages, b.messages)
                self.assertEqual(a.reason, b.reason)
                self.assertEqual(a.fits, b.fits)
                self.assertEqual([], b.sections,
                                 "claimed a section decision it could not make")


class DropOrderIsHonoured(unittest.TestCase):
    def test_sections_go_lowest_drop_order_first(self):
        secs = _assembly().sections()
        msgs = _msgs(secs, history=False)
        seen = []
        for limit in (300, 250, 200, 120):
            out = fit_chat_messages_with_sections(
                msgs, limit=limit, count_tokens=_count,
                sections=secs, render_sections=render_sections)
            for name in out.dropped_sections:
                if name not in seen:
                    seen.append(name)
        expected = ["memory_context", "english_first", "approved_stories",
                    "pinned_facts"]
        self.assertEqual(expected, seen[:len(expected)])

    def test_a_required_section_is_never_dropped(self):
        secs = _assembly().sections()
        msgs = _msgs(secs, history=False)
        for limit in (300, 200, 120, 60, 10):
            with self.subTest(limit=limit):
                out = fit_chat_messages_with_sections(
                    msgs, limit=limit, count_tokens=_count,
                    sections=secs, render_sections=render_sections)
                for s in out.sections:
                    if s.required:
                        self.assertTrue(s.kept, f"{s.name} was dropped")

    def test_the_current_narrator_turn_survives_every_path(self):
        """Including the refusal path. A reply built from a prompt with
        the narrator's own words cut out of it is worse than an error."""
        secs = _assembly().sections()
        msgs = _msgs(secs)
        current = msgs[-1]["content"]
        for limit in (10_000, 300, 120, 60, 5):
            with self.subTest(limit=limit):
                out = fit_chat_messages_with_sections(
                    msgs, limit=limit, count_tokens=_count,
                    sections=secs, render_sections=render_sections)
                self.assertEqual(current, out.messages[-1]["content"])


class RefusalIsStillPossible(unittest.TestCase):
    def test_it_refuses_when_required_content_alone_does_not_fit(self):
        asm = _PromptAssembly("system_head", "HEAD " * 50)
        asm.add("identity_facts", "FACTS " * 40, required=True)
        asm.add("memory_context", "MEM " * 60, required=False, drop_order=5)
        secs = asm.sections()
        out = fit_chat_messages_with_sections(
            _msgs(secs, history=False), limit=50, count_tokens=_count,
            sections=secs, render_sections=render_sections)
        self.assertFalse(out.fits)
        self.assertEqual("mandatory_too_large", out.reason)
        self.assertIn("memory_context", out.dropped_sections)
        self.assertEqual(["system_head", "identity_facts"],
                         [s.name for s in out.sections if s.kept])


class TelemetryCarriesNoPromptText(unittest.TestCase):
    """Section IDs, token counts, decisions and digests -- never words.

    Asserted against the SERIALISED record rather than an enumerated
    field list, because the defect this guards against is narrator text
    arriving through a field nobody thought to check. Same reasoning as
    the Phase 2 queue-response contract test.
    """

    SECRETS = ["Brownsville", "HEAD", "FACTS", "MEM", "ENG", "STORY", "PIN",
               "CURRENT"]

    def test_the_log_record_contains_no_section_text(self):
        asm = _PromptAssembly("system_head", "HEAD Brownsville " * 30)
        asm.add("identity_facts", "FACTS " * 40, required=True)
        asm.add("memory_context", "MEM " * 60, required=False, drop_order=5)
        secs = asm.sections()
        out = fit_chat_messages_with_sections(
            _msgs(secs), limit=120, count_tokens=_count,
            sections=secs, render_sections=render_sections)
        record = out.as_log_fields()
        for needle in self.SECRETS:
            with self.subTest(needle=needle):
                self.assertNotIn(needle, record)

    def test_the_record_carries_ids_counts_decisions_and_digests(self):
        secs = _assembly().sections()
        out = fit_chat_messages_with_sections(
            _msgs(secs), limit=200, count_tokens=_count,
            sections=secs, render_sections=render_sections)
        record = out.as_log_fields()
        self.assertIn("memory_context:", record)          # identifier
        self.assertIn("DROP", record)                     # decision
        self.assertRegex(record, r"memory_context:\w+:\d+:[0-9a-f]{12}")
        self.assertIn("dropped_sections=", record)

    def test_the_digest_is_short_stable_and_not_the_text(self):
        d = section_digest("some narrator words")
        self.assertEqual(12, len(d))
        self.assertEqual(d, section_digest("some narrator words"))
        self.assertNotEqual(d, section_digest("some other words"))
        self.assertNotIn("narrator", d)

    def test_history_only_outcomes_report_no_sections(self):
        """A budget that could not see sections must not appear to have
        judged any -- an empty section list in a log means 'not asked',
        and it would be dishonest for it to mean 'nothing dropped'."""
        secs = _assembly().sections()
        out = fit_chat_messages(_msgs(secs), limit=10_000, count_tokens=_count)
        self.assertEqual([], out.sections)
        self.assertNotIn("sections=", out.as_log_fields())


class AllThreeTransportsUseTheAuthority(unittest.TestCase):
    """Source-level, because the alternative is standing up three servers.

    The claim is narrow and structural: no transport composes a prompt
    that the section-aware budget has not been given the sections for.
    """

    def test_the_rest_paths_compose_with_sections(self):
        src = _API.read_text(encoding="utf-8")
        self.assertEqual(2, src.count("compose_prompt_sections("),
                         "a REST path still composes without its sections")
        self.assertEqual(0, len(re.findall(
            r"^\s*unified_system = compose_system_prompt\(", src, re.M)),
            "a REST path still uses the string-only entry point")

    def test_both_rest_fit_calls_pass_the_sections(self):
        src = _API.read_text(encoding="utf-8")
        calls = re.findall(r"_fit_chat_prompt\(msgs, tok,[^)]*\)", src, re.S)
        self.assertEqual(2, len(calls))
        for c in calls:
            self.assertIn("sections=_composed.sections", c)

    def test_the_websocket_path_composes_with_sections_and_budgets_them(self):
        src = _CHAT_WS.read_text(encoding="utf-8")
        self.assertIn("_composed = compose_prompt_sections(", src)
        self.assertIn("fit_chat_messages_with_sections(", src)
        self.assertIn("sections=_prompt_sections", src)

    def test_the_trip_block_is_a_section_not_a_concatenation(self):
        """It used to be `system_prompt = system_prompt + _tic_block`,
        which meant the budget priced a system message that was not the
        one sent -- on a shelf-open turn that block can be hundreds of
        tokens the ladder knew nothing about."""
        src = _CHAT_WS.read_text(encoding="utf-8")
        # The retired form, quoted so a reader can see what was replaced.
        # It appears in a comment explaining the change, so the ban is on
        # EXECUTABLE occurrences: comment lines are stripped first.
        code = "\n".join(ln for ln in src.splitlines()
                         if not ln.lstrip().startswith("#"))
        self.assertNotIn("system_prompt = system_prompt + _tic_block", code)
        self.assertIn('"trip_context", _tic_block.lstrip', code)
        self.assertIn("system_prompt = render_sections(_prompt_sections)", code)

    def test_converting_the_trip_block_changes_only_trailing_whitespace(self):
        """Stated as a measurement rather than a claim of byte-equality.

        The renderer strips the finished prompt, so the block's trailing
        newline is gone. Every other composition path was already
        stripped; raw concatenation was the one that bypassed it.
        """
        block = "\n\n[TRIP CONTEXT — facts about this trip.\nDay 2.\n"
        composed = compose_prompt_sections("conv", user_text="q",
                                           runtime71={"current_era": "today"})
        old = composed.text + block
        new = render_sections(list(composed.sections) + [
            make_section("trip_context", block.lstrip("\n"), drop_order=15)])
        self.assertNotEqual(old, new, "the trailing-newline delta is expected")
        self.assertEqual(old.rstrip(), new.rstrip(),
                         "the difference is NOT confined to trailing whitespace")


if __name__ == "__main__":
    unittest.main()
