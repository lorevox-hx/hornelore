"""WO-LEAN-LORI-RUNTIME-01 Phase 4A — the chat prompt fits without cutting Lori.

These execute the real function. The token counter is injected, so the
tests can state token costs exactly instead of depending on a tokenizer
being present -- and the shape of that injection is the same one the
three production call sites use, so what is exercised here is the code
that ships.

The properties, in the order they matter:

  1. the system message is never modified;
  2. the narrator's current message is never modified;
  3. history is dropped oldest-first, at turn boundaries, never
     mid-message;
  4. when the mandatory content alone does not fit, the function says so
     rather than slicing.

Run:
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_prompt_budget
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "server" / "code"))

from api.services.prompt_budget import (  # noqa: E402
    BudgetOutcome,
    fit_chat_messages,
    history_segments,
)


def sysmsg(n=100):
    return {"role": "system", "content": "S" * n}


def user(text, n=10):
    return {"role": "user", "content": text * n}


def bot(text, n=10):
    return {"role": "assistant", "content": text * n}


def counter(per_message=0, per_char=1, template=0):
    """A token counter with a stated cost model.

    `template` exists because the real one is applied AFTER the chat
    template, which adds tokens of its own -- a counter that ignored that
    would let the tests pass on a budget that overruns in production by
    exactly the template's width.
    """
    def count(msgs):
        return template + sum(per_message + per_char * len(m["content"])
                              for m in msgs)
    return count


class TheMandatoryContentIsNeverTouchedTest(unittest.TestCase):
    """Properties 1 and 2. Everything else is negotiable; these are not."""

    def test_the_system_message_survives_heavy_trimming(self):
        s = sysmsg(500)
        msgs = [s] + [user("q"), bot("a")] * 40 + [user("now", 3)]
        out = fit_chat_messages(msgs, limit=800, count_tokens=counter())
        self.assertTrue(out.fits)
        self.assertEqual(s, out.messages[0])

    def test_the_current_turn_survives_heavy_trimming(self):
        last = user("the thing I am asking about right now", 5)
        msgs = [sysmsg(300)] + [user("q"), bot("a")] * 40 + [last]
        out = fit_chat_messages(msgs, limit=700, count_tokens=counter())
        self.assertTrue(out.fits)
        self.assertEqual(last, out.messages[-1])

    def test_no_message_content_is_ever_partially_cut(self):
        """The whole point. A half-sentence from 20 turns ago is not
        context, it is noise that reads as context."""
        msgs = [sysmsg(200)] + [user("q"), bot("a")] * 30 + [user("now")]
        original = {m["content"] for m in msgs}
        out = fit_chat_messages(msgs, limit=600, count_tokens=counter())
        for m in out.messages:
            self.assertIn(m["content"], original,
                          "a message was truncated rather than dropped")

    def test_a_prompt_that_already_fits_is_returned_unchanged(self):
        msgs = [sysmsg(10), user("q"), bot("a"), user("now")]
        out = fit_chat_messages(msgs, limit=10_000, count_tokens=counter())
        self.assertEqual("fits", out.reason)
        self.assertEqual(msgs, out.messages)
        self.assertEqual(0, out.dropped_turns)


class HistoryIsDroppedOldestFirstAtTurnBoundariesTest(unittest.TestCase):
    """Property 3."""

    def test_the_oldest_turns_go_first(self):
        msgs = ([sysmsg(10)]
                + [{"role": "user", "content": f"q{i}"} for i in range(1)]
                + [])
        # build an explicit 5-turn history with identifiable content
        hist = []
        for i in range(5):
            hist.append({"role": "user", "content": f"Q{i}"})
            hist.append({"role": "assistant", "content": f"A{i}"})
        msgs = [sysmsg(10)] + hist + [{"role": "user", "content": "NOW"}]
        # each message costs 2 chars; system 10; NOW 3 -> keep only ~2 turns
        out = fit_chat_messages(msgs, limit=10 + 3 + 8, count_tokens=counter())
        kept = [m["content"] for m in out.messages]
        self.assertNotIn("Q0", kept)
        self.assertNotIn("Q1", kept)
        self.assertIn("Q4", kept)
        self.assertIn("NOW", kept)

    def test_a_question_and_its_answer_are_dropped_together(self):
        """Dropping only the reply leaves a question nobody answered;
        dropping only the question leaves an answer to nothing. The
        second is worse -- Lori can re-ask what she has already been
        told, which is the failure this system exists to avoid."""
        hist = []
        for i in range(6):
            hist.append({"role": "user", "content": f"Q{i}"})
            hist.append({"role": "assistant", "content": f"A{i}"})
        msgs = [sysmsg(5)] + hist + [{"role": "user", "content": "NOW"}]
        for limit in range(12, 40):
            out = fit_chat_messages(msgs, limit=limit, count_tokens=counter())
            kept = [m["content"] for m in out.messages
                    if m["content"].startswith(("Q", "A"))]
            qs = {c[1:] for c in kept if c.startswith("Q")}
            as_ = {c[1:] for c in kept if c.startswith("A")}
            self.assertEqual(qs, as_,
                             f"limit={limit} split a turn: Q{sorted(qs)} "
                             f"A{sorted(as_)}")

    def test_a_leading_assistant_message_is_its_own_segment(self):
        """A resumed greeting before the first question is not part of
        that question's turn; gluing them would misreport what is
        dropped."""
        segs = history_segments([
            {"role": "assistant", "content": "welcome back"},
            {"role": "user", "content": "Q0"},
            {"role": "assistant", "content": "A0"},
        ])
        self.assertEqual(2, len(segs))
        self.assertEqual("welcome back", segs[0][0]["content"])

    def test_the_reported_counts_match_what_was_actually_kept(self):
        hist = []
        for i in range(8):
            hist.append({"role": "user", "content": f"Q{i}"})
            hist.append({"role": "assistant", "content": f"A{i}"})
        msgs = [sysmsg(5)] + hist + [{"role": "user", "content": "NOW"}]
        out = fit_chat_messages(msgs, limit=25, count_tokens=counter())
        kept_turns = sum(1 for m in out.messages if m["content"].startswith("Q"))
        self.assertEqual(kept_turns, out.kept_turns)
        self.assertEqual(8 - kept_turns, out.dropped_turns)


class TheSearchIsExactTest(unittest.TestCase):
    """The binary search must find the LARGEST fitting suffix, not merely
    a fitting one. Keeping less history than necessary is a silent
    quality loss that no assertion elsewhere would catch."""

    def _brute(self, msgs, limit, count):
        best = -1
        head, tail = msgs[0], msgs[-1]
        segs = history_segments(msgs[1:-1])
        for k in range(len(segs) + 1):
            cand = [head]
            for s in segs[len(segs) - k:] if k else []:
                cand.extend(s)
            cand.append(tail)
            if count(cand) <= limit:
                best = k
        return best

    def test_matches_brute_force_across_many_limits(self):
        hist = []
        for i in range(12):
            hist.append({"role": "user", "content": f"Q{i}" * (i + 1)})
            hist.append({"role": "assistant", "content": f"A{i}" * (i + 1)})
        msgs = [sysmsg(20)] + hist + [{"role": "user", "content": "NOW"}]
        count = counter(per_message=1)
        for limit in range(20, 400, 7):
            out = fit_chat_messages(msgs, limit=limit, count_tokens=count)
            expected = self._brute(msgs, limit, count)
            got = out.kept_turns if out.fits else -1
            self.assertEqual(expected, got, f"limit={limit}")

    def test_the_result_actually_fits(self):
        hist = []
        for i in range(15):
            hist.append({"role": "user", "content": "Q" * (i + 1)})
            hist.append({"role": "assistant", "content": "A" * (i + 1)})
        msgs = [sysmsg(30)] + hist + [{"role": "user", "content": "NOW"}]
        count = counter(per_message=2, template=7)
        for limit in range(40, 500, 11):
            out = fit_chat_messages(msgs, limit=limit, count_tokens=count)
            if out.fits:
                self.assertLessEqual(count(out.messages), limit, f"limit={limit}")

    def test_the_template_cost_is_respected(self):
        """A counter that ignored the template would let this pass on a
        budget that overruns in production by exactly the template's
        width."""
        msgs = [sysmsg(10), {"role": "user", "content": "NOW"}]
        tight = counter(template=0)(msgs)
        out = fit_chat_messages(msgs, limit=tight,
                                count_tokens=counter(template=5))
        self.assertFalse(out.fits)
        self.assertEqual("mandatory_too_large", out.reason)


class WhenNothingFitsItSaysSoTest(unittest.TestCase):
    """Property 4. The extraction lane already refuses rather than
    truncating; the same reasoning holds here."""

    def test_mandatory_content_over_budget_is_reported_not_sliced(self):
        msgs = [sysmsg(9000), {"role": "user", "content": "hello"}]
        out = fit_chat_messages(msgs, limit=100, count_tokens=counter())
        self.assertFalse(out.fits)
        self.assertEqual("mandatory_too_large", out.reason)

    def test_the_refusal_still_reports_what_did_not_fit(self):
        """An operator needs to see WHICH content was too large, not just
        that something was."""
        msgs = [sysmsg(9000)] + [user("q"), bot("a")] * 3 + [
            {"role": "user", "content": "hello"}]
        out = fit_chat_messages(msgs, limit=100, count_tokens=counter())
        self.assertEqual(2, len(out.messages),
                         "the refusal should report the minimal set")
        self.assertGreater(out.tokens, out.limit)
        self.assertEqual(3, out.dropped_turns)

    def test_the_refusal_never_returns_a_partial_message(self):
        msgs = [sysmsg(9000), {"role": "user", "content": "hello"}]
        out = fit_chat_messages(msgs, limit=100, count_tokens=counter())
        self.assertEqual(9000, len(out.messages[0]["content"]))
        self.assertEqual("hello", out.messages[-1]["content"])


class DegenerateShapesTest(unittest.TestCase):
    """The three call sites always build [system] + history + [user], but
    a function that only works on well-formed input fails on the day
    something upstream changes."""

    def test_empty(self):
        out = fit_chat_messages([], limit=10, count_tokens=counter())
        self.assertTrue(out.fits)
        self.assertEqual([], out.messages)

    def test_system_only(self):
        out = fit_chat_messages([sysmsg(5)], limit=10, count_tokens=counter())
        self.assertTrue(out.fits)
        self.assertEqual(1, len(out.messages))

    def test_no_system_message_at_all(self):
        msgs = [user("q"), bot("a"), {"role": "user", "content": "NOW"}]
        out = fit_chat_messages(msgs, limit=1000, count_tokens=counter())
        self.assertTrue(out.fits)
        self.assertEqual("NOW", out.messages[-1]["content"])

    def test_history_with_no_user_messages(self):
        msgs = [sysmsg(5), bot("a"), bot("b"), {"role": "user", "content": "NOW"}]
        out = fit_chat_messages(msgs, limit=1000, count_tokens=counter())
        self.assertTrue(out.fits)

    def test_the_input_is_not_mutated(self):
        msgs = [sysmsg(10), user("q"), bot("a"), {"role": "user", "content": "NOW"}]
        snapshot = [dict(m) for m in msgs]
        fit_chat_messages(msgs, limit=12, count_tokens=counter())
        self.assertEqual(snapshot, msgs)

    def test_roles_are_matched_case_insensitively(self):
        msgs = [{"role": "SYSTEM", "content": "S" * 5},
                {"role": "User", "content": "Q0"},
                {"role": "ASSISTANT", "content": "A0"},
                {"role": "user", "content": "NOW"}]
        out = fit_chat_messages(msgs, limit=1000, count_tokens=counter())
        self.assertEqual("S" * 5, out.messages[0]["content"])


class TheOutcomeIsLoggableTest(unittest.TestCase):
    def test_log_fields_carry_the_decision(self):
        msgs = [sysmsg(5)] + [user("q"), bot("a")] * 5 + [
            {"role": "user", "content": "NOW"}]
        out = fit_chat_messages(msgs, limit=60, count_tokens=counter())
        fields = out.as_log_fields()
        for key in ("reason=", "tokens=", "limit=", "kept_turns=",
                    "dropped_turns="):
            self.assertIn(key, fields)

    def test_no_narrator_content_is_in_the_log_line(self):
        """Operator logs carry ids and counts, never narrator words."""
        secret = "my father died in Bismarck in 1962"
        msgs = [sysmsg(5), {"role": "user", "content": secret},
                {"role": "assistant", "content": "A"},
                {"role": "user", "content": "NOW"}]
        out = fit_chat_messages(msgs, limit=12, count_tokens=counter())
        self.assertNotIn(secret, out.as_log_fields())


if __name__ == "__main__":
    unittest.main(verbosity=2)
