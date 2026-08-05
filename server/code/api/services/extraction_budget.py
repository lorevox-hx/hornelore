"""WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 5 —
the extraction prompt budget, and the refusal that enforces it.

WHY THIS EXISTS
---------------
Extraction prompts were reaching the model at ~12,300 tokens against a
MAX_EXTRACTION_CONTEXT_WINDOW of 8,192. The generic chat guard in
api._generate_text
handled that with `v[:, -MAX_CHAT_PROMPT_TOKENS:]` -- it keeps the LAST
8,192 tokens, so it cuts the FRONT, where the extraction preamble, the
"use ONLY these exact fieldPath values" rule and the 140-field catalog
all live. Nothing reported which of those a given call had lost, so an
extraction running without its own schema returned items that looked
exactly like ordinary proposals in Shadow Review.

THE RULE, AND WHY IT IS A REFUSAL RATHER THAN A TRIM
---------------------------------------------------
Chris's ruling, 2026-07-31: extraction fails CLOSED. An extraction
prompt that would lose protected content does not enter the model at
all. Trimming is not available to this lane, because there is no part
of an extraction prompt that is safe to lose silently -- drop the
catalog and the model invents field paths; drop the narrator's turn and
there is nothing to extract from; drop the JSON contract and the output
cannot be parsed. A refusal is legible. A quiet truncation is not.

THE WINDOW IS A FIXED CONSTRAINT, NOT A TUNING KNOB
---------------------------------------------------
Also Chris's ruling: "Hornelore must operate within the tested VRAM
envelope of the existing computer." MAX_EXTRACTION_CONTEXT_WINDOW stays 8192 and
the model, quantization, offload and serving configuration stay as they
are. This module therefore never proposes a larger window; it exists to
make the prompt fit the machine that was actually tested. Raising the
window would hide the prompt-construction defect and move VRAM risk
into Phase 3 before the inference coordinator exists.

WHO OWNS WHICH NUMBER
---------------------
The window belongs to api.py, which reads MAX_EXTRACTION_CONTEXT_WINDOW and passes
it in. This module owns the RESERVE POLICY and the arithmetic. Splitting
it that way means the two cannot drift into disagreeing about the window,
which is the failure a second os.getenv here would eventually produce.

PRIVACY
-------
Every value this module carries is a count. No prompt text, no narrator
prose, no extracted values, no field paths -- the same rule that binds
the ledger (migration 0038) binds the refusal that closes it.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

__all__ = [
    "ExtractionPromptBudgetExceeded",
    "PromptBudget",
    "safety_reserve_tokens",
    "budget_for",
]


def safety_reserve_tokens() -> int:
    """Head-room kept free beyond the generation cap.

    Not decoration. `max_new_tokens` bounds what the model is ASKED to
    produce; the KV cache, the chat template's own added tokens and any
    per-call overhead are on top of that. Landing one token under the
    window leaves nothing for them, so the reserve is what makes the
    ceiling an operational limit rather than an arithmetic one.

    Chris's Phase 5 spec: at least 384-512. Default 512, the safer end,
    because the cost of over-reserving is a slightly tighter prompt and
    the cost of under-reserving is an OOM on the machine we are
    explicitly not allowed to buy more VRAM for.
    """
    try:
        v = int(os.getenv("HORNELORE_EXTRACTION_RESERVE_TOKENS", "512"))
    except (TypeError, ValueError):
        return 512
    # A reserve below the documented floor is almost certainly a typo, and
    # one at or above the window would refuse every prompt including empty
    # ones. Clamp rather than trust, and stay silent about it -- this is
    # arithmetic, not an event.
    return max(384, min(v, 4096))


class PromptBudget:
    """What a single extraction call is allowed, and what it used.

    Counts only -- see the module docstring.
    """

    __slots__ = ("window", "max_new", "reserve", "ceiling", "prompt_tokens",
                 "components")

    def __init__(self, *, window: int, max_new: int, reserve: int,
                 prompt_tokens: int = 0,
                 components: Optional[Dict[str, int]] = None) -> None:
        self.window = int(window)
        self.max_new = int(max_new)
        self.reserve = int(reserve)
        # The ceiling is derived from THIS call's generation cap, not from
        # a constant. Extraction runs at max_new=128 for an ordinary answer
        # and 768 for a compound one (MAX_NEW_TOKENS_EXTRACT_COMPOUND), so a
        # fixed ceiling would be wrong for one of the two -- and wrong in
        # the dangerous direction for the compound case, which is exactly
        # the case whose prompt is longest.
        self.ceiling = max(0, self.window - self.max_new - self.reserve)
        self.prompt_tokens = int(prompt_tokens)
        self.components = dict(components or {})

    @property
    def exceeded(self) -> bool:
        return self.prompt_tokens > self.ceiling

    @property
    def headroom(self) -> int:
        return self.ceiling - self.prompt_tokens

    def as_log_fields(self) -> str:
        """One flat line of counts, safe to emit at INFO."""
        parts = [
            "kind=extraction",
            f"tokens_total={self.prompt_tokens}",
            f"budget={self.ceiling}",
            f"window={self.window}",
            f"max_new={self.max_new}",
            f"reserve={self.reserve}",
            f"headroom={self.headroom}",
        ]
        for name in sorted(self.components):
            parts.append(f"{name}={self.components[name]}")
        return " ".join(parts)

    def as_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "kind": "extraction",
            "tokens_total": self.prompt_tokens,
            "budget": self.ceiling,
            "window": self.window,
            "max_new": self.max_new,
            "reserve": self.reserve,
            "headroom": self.headroom,
        }
        d.update(self.components)
        return d


def budget_for(*, window: int, max_new: int,
               prompt_tokens: int = 0,
               components: Optional[Dict[str, int]] = None) -> PromptBudget:
    return PromptBudget(window=window, max_new=max_new,
                        reserve=safety_reserve_tokens(),
                        prompt_tokens=prompt_tokens, components=components)


class ExtractionPromptBudgetExceeded(RuntimeError):
    """Raised INSTEAD of generating, when an extraction prompt is too big.

    It must reach `turn_extraction._complete_claim`, which closes the
    claim already held with error_class=ExtractionPromptBudgetExceeded.
    That means it must survive `llm_interview._try_call_llm`, whose
    blanket `except Exception: return None` would otherwise turn a
    refusal into an empty result and then into a rules fallback -- a
    silent degradation of exactly the kind INC-2026-07-09 was about. The
    re-raise there is load-bearing, not defensive.

    The message carries counts only. It is allowed to be logged.
    """

    def __init__(self, budget: PromptBudget) -> None:
        self.budget = budget
        super().__init__(
            "extraction prompt exceeds its protected budget "
            f"({budget.prompt_tokens} > {budget.ceiling} tokens; "
            f"window={budget.window} max_new={budget.max_new} "
            f"reserve={budget.reserve}). Refused rather than truncated: "
            "front-truncating an extraction prompt silently removes the "
            "field catalog and the model then invents field paths."
        )
