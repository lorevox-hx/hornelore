"""The generation observer watches and never participates.

`WO-LORI-LISTEN-AND-RETAIN-01` §9.

── WHAT IS BEING PROTECTED ───────────────────────────────────────────

The observer is a `StoppingCriteria` installed in the SAME list as
`StopOnEvent`, on the live narrator generation path. That is the most
dangerous place in the system to add anything: a criterion that returns
True cuts a narrator off mid-sentence, and one that raises aborts the
turn. So the two properties asserted hardest here are that it **always
returns False** and that it **cannot raise**.

── WHY IT EXISTS AT ALL ──────────────────────────────────────────────

An exact generated-token count needs the token ids, and there are only
two places they exist: `model.generate`'s return value, and the
`input_ids` a stopping criterion sees each step.

The return value is unavailable — text comes from a
`TextIteratorStreamer` and the call runs in a thread whose result is
deliberately discarded. Retaining it would hold the full sequence tensor
on-device across the inter-turn window, which is exactly the window
whose VRAM this diagnostic measures: the instrument would perturb the
measurement.

── TWO WRONG ANSWERS I TRIED FIRST, RECORDED ─────────────────────────

Both were proposed as "exact" and neither is:

* **re-encoding the decoded text** — the streamer is built
  `skip_special_tokens=True`, so EOS never appears in the text and is
  invisible to re-encoding by construction; and BPE decode-then-encode
  is not guaranteed to reproduce the original segmentation;
* **counting streamer yields** — `TextIteratorStreamer` flushes on word
  boundaries, so a yield is a text chunk, not a token.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
for _p in (str(_REPO), str(_REPO / "server" / "code")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


class _Ids:
    """The shape a `StoppingCriteria` is handed: `.shape` and `[0, -1]`."""

    def __init__(self, tokens):
        self._t = list(tokens)
        self.shape = (1, len(self._t))

    def __getitem__(self, key):
        if key == (0, -1):
            return self._t[-1]
        raise KeyError(key)


def _observer(prompt_len):
    from api.services.generation_trace import _GenerationTraceObserver
    return _GenerationTraceObserver(prompt_len)


def _reason(observer, *, cancelled=False, max_new=256, eos=2):
    from api.services.generation_trace import _generation_end_reason
    return _generation_end_reason(observer, cancelled=cancelled,
                                  max_new=max_new, eos_token_id=eos)


class TheObserverNeverParticipatesTests(unittest.TestCase):
    """The property that matters more than any measurement."""

    def test_it_always_returns_False(self):
        obs = _observer(100)
        for n in range(1, 40):
            self.assertIs(
                False, obs(_Ids(range(100 + n)), None),
                "the observer requested a stop — it would cut a narrator "
                "off mid-sentence")

    def test_it_returns_False_even_at_and_beyond_the_cap(self):
        obs = _observer(100)
        for n in (255, 256, 257, 1000):
            self.assertIs(False, obs(_Ids(range(100 + n)), None))

    def test_a_malformed_input_does_not_raise(self):
        """It is here to watch. Failing to watch is not a reason to fail
        a narrator's turn."""
        obs = _observer(100)
        self.assertIs(False, obs(None, None))
        self.assertIs(False, obs(object(), None))


class TheCountIsSequenceBasedTests(unittest.TestCase):
    """Counted from sequence growth, not from text."""

    def test_the_count_is_the_sequence_growth(self):
        obs = _observer(prompt_len=100)
        obs(_Ids(range(137 + 100)), None)
        self.assertEqual(137, obs.generated_tokens)

    def test_it_tracks_the_last_step_not_the_first(self):
        obs = _observer(prompt_len=10)
        for n in (1, 5, 9):
            obs(_Ids(range(10 + n)), None)
        self.assertEqual(9, obs.generated_tokens)
        self.assertEqual(3, obs.steps)

    def test_the_last_token_id_is_recorded(self):
        obs = _observer(prompt_len=3)
        obs(_Ids([7, 8, 9, 42]), None)
        self.assertEqual(42, obs.last_token_id)

    def test_the_router_does_not_retokenize_text_to_count(self):
        """The two wrong answers must not reappear.

        `tok.encode(final_text)` or a streamer-chunk count would both
        look plausible and be silently approximate.
        """
        src = (_REPO / "server" / "code" / "api" / "routers"
               / "chat_ws.py").read_text(encoding="utf-8")
        block = src[src.index("GENERATION TELEMETRY"):]
        block = block[:block.index("_gen_tel_exc")]
        self.assertIn("_gen_observer.generated_tokens", block)
        self.assertNotIn("tok.encode(final_text)", block)
        self.assertNotIn("len(reply_parts)", block)


class TheEndReasonIsFactBasedTests(unittest.TestCase):
    """`eos_at_limit` exists because both can be true at once.

    Choosing one arbitrarily would report a model that finished its
    thought as one that ran out of room, or the reverse — and that is
    precisely the question the 256 cap is under investigation for.
    """

    def test_eos_below_the_cap_is_eos(self):
        obs = _observer(10)
        obs(_Ids(list(range(10)) + [1] * 136 + [2]), None)
        self.assertEqual("eos", _reason(obs, max_new=256, eos=2))

    def test_the_cap_without_eos_is_max_new(self):
        obs = _observer(10)
        obs(_Ids(list(range(10)) + [1] * 256), None)
        self.assertEqual("max_new", _reason(obs, max_new=256, eos=2))

    def test_eos_exactly_at_the_cap_is_neither_alone(self):
        """The discriminating case. Reporting `eos` or `max_new` here
        would each be half true and wholly misleading."""
        obs = _observer(10)
        obs(_Ids(list(range(10)) + [1] * 255 + [2]), None)
        self.assertEqual("eos_at_limit", _reason(obs, max_new=256, eos=2))

    def test_a_cancelled_turn_says_cancelled(self):
        obs = _observer(10)
        obs(_Ids(list(range(10)) + [1] * 5), None)
        self.assertEqual("cancelled", _reason(obs, cancelled=True))

    def test_no_observation_is_unknown_not_a_guess(self):
        """`unknown` is a fact. A guessed `eos` is not."""
        self.assertEqual("unknown", _reason(None))
        self.assertEqual("unknown", _reason(_observer(10)))

    def test_a_multi_valued_eos_is_handled(self):
        """Some tokenizers carry a list of terminators."""
        obs = _observer(10)
        obs(_Ids(list(range(10)) + [1] * 20 + [128009]), None)
        self.assertEqual("eos", _reason(obs, max_new=256,
                                        eos=[2, 128009]))

    def test_stopping_short_of_the_cap_without_eos_is_other_stop(self):
        """The positive control: not everything is eos or max_new."""
        obs = _observer(10)
        obs(_Ids(list(range(10)) + [1] * 40 + [77]), None)
        self.assertEqual("other_stop", _reason(obs, max_new=256, eos=2))


class TheObserverIsOnlyInstalledWhenTracingTests(unittest.TestCase):
    """With tracing off, the criteria list is what it always was."""

    def test_the_router_gates_installation_on_the_trace_flag(self):
        src = (_REPO / "server" / "code" / "api" / "routers"
               / "chat_ws.py").read_text(encoding="utf-8")
        self.assertIn("if _rt.enabled() and _rt_id:", src)
        self.assertIn("stop = StoppingCriteriaList([StopOnEvent(ev)])", src,
                      "the untraced path no longer builds the original "
                      "criteria list")

    def test_the_generation_thread_target_is_untouched(self):
        """`model.generate` is NOT wrapped. Named explicitly because
        wrapping it was the first design and it was wrong twice: it is a
        product change to the most sensitive path, and retaining the
        returned tensor perturbs the VRAM measurement."""
        src = (_REPO / "server" / "code" / "api" / "routers"
               / "chat_ws.py").read_text(encoding="utf-8")
        self.assertIn("target=model.generate,", src)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class TracingCannotAlterNarratorVisibleTextTests(unittest.TestCase):
    """The instrumentation observes. It must not be able to participate.

    ── WHY THIS IS AN AST CHECK, NOT A MOCKED TURN, 2026-09-06 ────────

    "Trace on and trace off deliver byte-identical text" is the claim.
    A mocked generation would demonstrate it for ONE path through a
    handler with many branches — three refusals, cancellation, buffered
    and unbuffered streaming — and would say nothing about the others.
    Worse, it would need the whole router imported, so it could only run
    where the serving stack exists.

    The PROPERTY is stronger and mechanically checkable: **no trace call
    result is ever consumed.** If every `_rt.*` call is a bare
    expression statement, its return value cannot reach a variable, a
    condition or a return, so it cannot change what the narrator sees on
    any path — including ones nobody thought to mock.

    `_rt.begin()` and `_rt.enabled()` are the deliberate exceptions:
    `begin` yields the trace id every later call needs, and `enabled`
    gates whether the observer is installed at all. Both are named here
    so the exception is a decision rather than a gap.
    """

    ALLOWED_TO_RETURN = {"begin", "enabled", "current", "attach"}

    def _trace_calls(self):
        import ast
        src = (_REPO / "server" / "code" / "api" / "routers"
               / "chat_ws.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        bare = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                bare.add(id(node.value))
        consumed = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not (isinstance(fn, ast.Attribute)
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "_rt"):
                continue
            if id(node) in bare:
                continue
            consumed.append((fn.attr, node.lineno))
        return consumed

    def test_no_trace_call_result_is_consumed(self):
        offenders = [(name, ln) for name, ln in self._trace_calls()
                     if name not in self.ALLOWED_TO_RETURN]
        self.assertEqual(
            [], offenders,
            "a trace call's return value is used in the router, so "
            "instrumentation can influence narrator-visible behaviour: "
            f"{offenders}")

    def test_the_exceptions_are_the_ones_we_named(self):
        """Non-vacuity: if nothing consumed a result, the test above
        would pass against a router with no tracing at all."""
        consumed = {name for name, _ln in self._trace_calls()}
        self.assertIn("begin", consumed,
                      "the trace id is not captured, so the router is not "
                      "tracing and this test proves nothing")
        self.assertTrue(consumed <= self.ALLOWED_TO_RETURN)

    def test_every_telemetry_block_swallows_its_own_failures(self):
        """A trace failure must never become a turn failure."""
        src = (_REPO / "server" / "code" / "api" / "routers"
               / "chat_ws.py").read_text(encoding="utf-8")
        for marker in ("GENERATION TELEMETRY", "def _trace_pre_generation_terminal"):
            block = src[src.index(marker):]
            block = block[:block.index("\n\n\n")] if "\n\n\n" in block else block
            self.assertIn(
                "except Exception", block,
                f"the block at {marker!r} can raise out of a narrator turn")

    def test_the_cuda_reads_are_read_only(self):
        """`reset_peak_memory_stats` and the two `max_memory_*` reads
        are the only CUDA calls the instrumentation makes. Nothing
        empties a cache or synchronises, which would change timing —
        and timing is one of the things being measured."""
        src = (_REPO / "server" / "code" / "api" / "routers"
               / "chat_ws.py").read_text(encoding="utf-8")
        block = src[src.index("PyTorch allocator peaks are per-turn"):]
        block = block[:block.index("_gen_started_perf") + 40]
        self.assertIn("reset_peak_memory_stats", block)
        for forbidden in ("empty_cache", "synchronize", "ipc_collect"):
            self.assertNotIn(forbidden, block)
