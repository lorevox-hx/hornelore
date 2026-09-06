"""Watch generation without ever participating in it.

`WO-LORI-LISTEN-AND-RETAIN-01` §9 — the VRAM/prompt-budget diagnostic.

── WHY A SEPARATE MODULE, 2026-09-06 ────────────────────────────────

These two pieces are pure logic: sequence arithmetic and a naming rule.
They lived in `chat_ws.py`, where testing them meant importing the whole
router — and with it `transformers`, `torch`, the database and the
FastAPI stack. A test that can only run where a GPU serving venv exists
is a test that gets skipped, and `OK` with skips is not a pass.

Here they are importable on their own, so the properties that matter
most — **the observer always returns False**, and the end reason is
derived rather than guessed — can be asserted anywhere.

Nothing about the generation path changed in the move. `chat_ws.py`
imports these and installs the observer only when tracing is enabled.
"""
from __future__ import annotations

from typing import Optional


class _GenerationTraceObserver:
    """Watch generation without ever influencing it.

    `WO-LORI-LISTEN-AND-RETAIN-01` §9. Installed ONLY when response
    tracing is enabled.

    ── WHY A StoppingCriteria, 2026-09-06 ─────────────────────────────

    An EXACT generated-token count needs the token ids, and there are
    only two places they exist: `model.generate`'s return value, and the
    `input_ids` a stopping criterion is handed on every decode step.

    The return value is not available — text comes from a
    `TextIteratorStreamer` and the call runs in a thread whose result is
    deliberately discarded. Retaining it would also hold the full
    sequence tensor on-device across the inter-turn window, which is the
    exact window whose VRAM this diagnostic measures: the instrument
    would perturb the measurement.

    So the criterion is the instrument. **It ALWAYS returns False.** It
    decides nothing, stops nothing, and changes no narrator-visible
    behaviour.

    ── WHY NOT COUNT THE TEXT, WHICH WAS MY FIRST ANSWER ──────────────

    Re-encoding the decoded text is NOT exact and was wrong twice over:
    the streamer is built `skip_special_tokens=True`, so EOS never
    appears in the text and is invisible to re-encoding by construction;
    and BPE decode-then-encode is not guaranteed to reproduce the
    original segmentation. Counting streamer yields is also wrong —
    `TextIteratorStreamer` flushes on word boundaries, so a yield is a
    text chunk, not a token.
    """

    def __init__(self, prompt_len: int):
        self.prompt_len = int(prompt_len)
        self.generated_tokens = 0
        self.last_token_id = None
        self.steps = 0

    def __call__(self, input_ids, scores, **kwargs) -> bool:
        try:
            self.steps += 1
            self.generated_tokens = int(input_ids.shape[-1]) - self.prompt_len
            self.last_token_id = int(input_ids[0, -1])
        except Exception:                     # pragma: no cover - defensive
            # An observer that raises would abort a narrator's turn. It
            # is here to watch; failing to watch is not a reason to fail.
            pass
        return False


def _generation_end_reason(observer, *, cancelled: bool, max_new: int,
                           eos_token_id) -> str:
    """Name why generation stopped, from evidence rather than assumption.

    `eos_at_limit` exists because both can be true at once, and choosing
    one arbitrarily would report a model that finished its thought as one
    that ran out of room — or the reverse. If the observer saw nothing,
    say so; `unknown` is a fact, and a guessed `eos` is not.
    """
    if cancelled:
        return "cancelled"
    if observer is None or observer.last_token_id is None:
        return "unknown"
    hit_cap = observer.generated_tokens >= int(max_new)
    is_eos = False
    try:
        if isinstance(eos_token_id, (list, tuple, set)):
            is_eos = observer.last_token_id in set(eos_token_id)
        elif eos_token_id is not None:
            is_eos = observer.last_token_id == int(eos_token_id)
    except Exception:                         # pragma: no cover - defensive
        is_eos = False
    if is_eos and hit_cap:
        return "eos_at_limit"
    if is_eos:
        return "eos"
    if hit_cap:
        return "max_new"
    return "other_stop"
