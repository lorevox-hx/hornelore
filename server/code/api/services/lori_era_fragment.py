"""Guard Lab authority 44 — Era Fragment Repair. Pure, deterministic.

── WHY THIS IS A SERVICE MODULE AND NOT ROUTER CODE ────────────────────

The logic lived inside the WebSocket handler in `chat_ws.py`, and it
shipped a defect that deleted a narrator's turn:

    _repaired = "Can you tell me about " + ...
    if not _authority.snapshot.is_selected(44):
        _repaired = ""          # <-- OFF meant DELETE
    final_text = _repaired      # <-- assigned either way

Under Lean — every switchable authority excluded — that emptied the
reply. Measured, Phase 6 turn 10 (2026-09-07): a complete 16-word
response generated normally (`eos`, 22 tokens) and reached the narrator
as nothing. `delivered_text` and `persisted_text` were both empty with
`delivered_equals_persisted=True`, so the EMPTY string was written to
`turnrow:2285`.

Moving it out of the router is the actual fix for how that shipped
green. A first attempt left the function at module scope in `chat_ws`,
which still required importing FastAPI to test it — and on the
authoritative `.venv` run the six tests SKIPPED and a deliberate
mutation "passed" because nothing executed. `OK` with skips is not a
pass; that is written down, and it still caught us.

Here the function imports nothing but `re`, so it is testable on every
interpreter — bare `python3` included — and a mutation cannot hide
behind a skip. This matches the existing pure-guard posture in
`lori_response_guards.py`: "LAW 3: pure deterministic. No LLM. No DB.
No IO."
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

#: Detection only. Shapes the repair is meant to catch — see the registry
#: entry for id 44 (`lori_guard_registry.py`), including its recorded
#: `known_harm` from Walt turn 2.
OPENER_RX = re.compile(r"^(?:The|Those|Your|That)\s+\w")

#: Skip a real sentence: "Article + (zero or one noun) + main verb", so
#: "That was a special time, wasn't it?" and "The book is on the table?"
#: are left alone while "The conversations you had together back then?"
#: is not.
MAIN_VERB_RX = re.compile(
    r"^(?:The|Those|Your|That|These|This)\s+"
    r"(?:\w+\s+)?"  # optional ONE noun
    r"(?:was|were|is|are|had|have|will|would|should|"
    r"could|might|may|do|does|did|can|won't|isn't|"
    r"wasn't|weren't|aren't)\b",
    re.IGNORECASE,
)

#: Already a well-formed question; nothing to repair.
INTERROGATIVE_RX = re.compile(
    r"^(?:What|Where|When|Who|How|Why|Did|Were|Was|Had|Could|"
    r"Can|Do|Does|Is|Are|Will|Would|Should|May|Might|Tell|"
    r"Share|Say|Describe)\b",
    re.IGNORECASE,
)

PREFIX = "Can you tell me about "


def era_fragment_repair(final_text: Optional[str], *,
                        selected: bool) -> Tuple[str, bool, str]:
    """Authority 44. Returns `(text, fired, would_repair)`.

    `selected` is the Guard Lab decision — `snapshot.is_selected(44)`.

    THE LAW THIS FUNCTION EXISTS TO KEEP: when `selected` is False the
    input is returned unchanged. There is no input for which an excluded
    call returns a different string, and none for which it returns "".

    44 is `POLICY_SWITCHABLE` with `CF_PURE` in the registry, and a pure
    counterfactual means excluding the authority yields the text the
    model actually produced. "Do not apply this repair" and "there is no
    response" are different outcomes; only the first is a counterfactual.

    `would_repair` is returned even when excluded, so the OFF arm stays
    observable in logs and traces without being applied — the
    counterfactual can be reported without being performed.
    """
    text = final_text or ""
    stripped = text.strip()
    if not (stripped
            and stripped.endswith("?")
            and OPENER_RX.match(stripped)
            and not MAIN_VERB_RX.match(stripped)
            and not INTERROGATIVE_RX.match(stripped)):
        return text, False, ""

    # Lowercase the leading article: "The conversations..." →
    # "...about the conversations..."
    would_repair = PREFIX + stripped[0].lower() + stripped[1:]
    if not selected:
        return text, False, would_repair
    return would_repair, True, would_repair
