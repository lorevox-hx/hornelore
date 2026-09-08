# BUG-LORI-META-RESPONSE-LEAK-01

**Status:** CLOSED — patched 2026-06-17
**Severity:** HIGH (the LLM exposes its prompt-compliance reasoning to the
narrator, breaking the trust illusion + revealing operator-side instruction
text + violating principle 2 "no operator leakage")
**Surface:** `server/code/api/services/lori_response_guards.py`

## Reproduction

Richard Earliest Years from the 2026-06-17 full-family harness run:

```
"Here is a response that follows the rules and guidelines:

"You mentioned Magee Hospital where you were born, your parents, and the
Catholic Church, where you attended Mass and served as an altar boy. You
also talked about your family's neighborhood in Oakland, near the river,
and your father's work at Jones and Laughlin. What do you remember about
your daily life in Oakland, particularly during your early years, around
the time you started school?"

This response reflects the narrator's mentions of Magee Hospital, the
Catholic Church, and Oakland, and asks a follow-up question that invites
the narrator to share more about their daily life during this period."
```

The narrator is presented with:
1. A meta-instruction preamble exposing operator-side prompt vocabulary
   ("rules and guidelines")
2. A quoted draft of the actual response — useful but wrapped in quotes
   for no narrator-facing reason
3. A meta-instruction postamble dissecting what the response is supposed
   to accomplish ("This response reflects... and asks a follow-up question
   that invites the narrator to share...")

Per CLAUDE.md design principle 2: *"No operator leakage. Anything a
narrator can see or interact with must be designed for narrators."*

A narrator who reads this is being shown the operator-side scaffold — Lori
is unintentionally outing herself as a directed agent rather than a
listener.

## Root cause

Generation drift. The LLM's instruction-tuning sometimes produces
prompt-compliance reasoning as part of its output when the system prompt
contains explicit rule blocks (e.g. EXPLICIT REFLECTION DISCIPLINE,
NO-FORK RULE, GROUNDING RULE, etc.). Llama 3.1-8B Q4 in particular has
a pronounced tendency to do this when directives are nested or layered.

This cannot be reliably eliminated at the prompt level — the LLM's
"following instructions" register is part of how it complies. The fix
must be a post-LLM cleanup pass.

## Fix

Add three new regex pattern banks + detection + repair logic to
`services/lori_response_guards.py`:

```python
_META_PREAMBLE_RX    # "Here is a response that follows..."
_META_POSTAMBLE_RX   # "This response reflects..."
_FAKE_WARMTH_RX      # "What a rich and evocative narrative", "Let me capture key points"
```

Plus `_QUOTED_DRAFT_RX` to extract the LLM's actual draft when wrapped in
quotes (the common shape — the wrapped draft is usually the response
Lori meant to send).

Recovery priority:
1. If quoted draft present (length ≥ 6 words) → return longest quoted draft
2. Else strip preamble + postamble + fake-warmth → return remainder if
   length ≥ 6 words
3. Else deterministic continuation ("Tell me more about that." / Spanish equiv)

Wired into `apply_response_guards()` BETWEEN language-drift and
dangling-determiner so the recovered draft itself still gets the
dangling-determiner check (an unwrapped draft may still end with "the.").

## Acceptance gates

1. Richard Earliest verbatim text from harness → recovered to a clean
   reflective response, no preamble, no postamble
2. `"What a rich and evocative narrative!"` → suppressed
3. `"This response reflects the narrator's mentions of X."` postamble → suppressed
4. Clean response → passes through unchanged, `fired=[]`
5. Meta-leak that contains dangling determiner in recovered draft → both
   `meta_response_leak` AND `dangling_determiner` fire in sequence
6. Spanish target language → recovery returns Spanish continuation when
   fallback path is taken
7. Existing language_drift and dangling_determiner tests still pass

## Files changed

- `server/code/api/services/lori_response_guards.py`
  - `_META_PREAMBLE_RX`, `_META_POSTAMBLE_RX`, `_FAKE_WARMTH_RX`,
    `_QUOTED_DRAFT_RX` patterns
  - `detect_meta_response_leak(text)` function
  - `repair_meta_response_leak(text, target_language)` function with
    3-priority recovery logic
  - `apply_response_guards()` extended to invoke meta-leak guard between
    language_drift and dangling_determiner
  - `__all__` extended with two new public symbols
- `tests/test_lori_meta_response_leak_guard.py` — 12 tests across 3
  classes: detection (6), repair (4), integration (3)

## Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
