# BUG-LIFEMAP-COMM-CONTROL-TRIM-01

**Status:** OPEN — observed 2026-06-17
**Severity:** MEDIUM (silent content loss — Life Map era entries
get clipped before they reach the operator; for a regular chat
turn this would be correct behavior, but for a Life-Map-entry
harness it discards exactly the substance the entry was supposed
to preserve)
**Narrator generality:** UNIVERSAL — fires whenever
`lori_communication_control` detects either `too_long` OR
`response_stub_collapse` and applies a runtime shape

## Reproduction

1. Start a narrator session in `oral_history` style (default).
2. Send an operator-side prompt asking Lori for a substantive
   Life Map era entry. Example: the John Baldy harness Era 1
   prompt (~200 words asking for a warm oral-history note ending
   in a gentle question).
3. Lori's raw LLM output exceeds the per-turn word cap
   (`comm_control` cap is style-dependent; oral_history allows
   more than `warm_storytelling` but not unlimited).
4. `lori_communication_control` shapes the response:
   ```
   [chat_ws][comm_control] changed=True
     conv=<...> failures=too_long,response_stub_collapse
     atomicity= reflection=
     before_words=65 after_words=43
   [lori][reflection-shape] conv=<...>
     actions=shaped_echo_trimmed_to_anchor softened=False
     before_words=65
   ```
5. The narrator/operator sees a 43-word response. The 22 trimmed
   words contained the substantive era content the harness was
   designed to capture.

Live evidence from `.runtime/logs/api.log` 2026-06-17 11:12:24:

```
[chat_ws][comm_control] changed=True conv=switch_mqi9rego_cd2k
  failures=too_long,response_stub_collapse
  atomicity= reflection= before_words=65 after_words=43

[lori][reflection-shape] conv=switch_mqi9rego_cd2k
  actions=shaped_echo_trimmed_to_anchor softened=False
  before_words=65
```

## Diagnosis

Two intersecting layers fire simultaneously:

1. **`too_long` failure** (from `lori_communication_control` per-style
   word cap). Style `oral_history` allows longer responses than
   `warm_storytelling`, but the cap still applies. Per the 2026-05-07
   BUG-LORI-RESPONSE-CAP-ADAPTIVE work the cap auto-extends by ~35
   words when the narrator's prior turn was ≥50 words — but the
   adaptive bump triggers off the NARRATOR's prior turn, not the
   OPERATOR's directive. A harness prompt from the operator carries
   the era content, but the WRAPPER doesn't recognize it as
   substantive narrator content, so the adaptive bump doesn't apply.

2. **`response_stub_collapse` failure** (from the 2026-05-09
   BUG-LORI-RESPONSE-STUB-COLLAPSE-01 Phase 1 detector — Step 6 in
   `lori_communication_control.py`). The detector flags a response
   as collapsed when it's ≤3 words AND the narrator's input was
   substantive AND not safety-triggered. Here the narrator input
   IS substantive (the era directive), so when Lori's raw output
   happens to be brief — even if the brevity is RIGHT for the
   moment — the detector adds `response_stub_collapse` to the
   warnings.

The two failures stack: the shaper trims `too_long`'s overage AND
shapes around `stub_collapse`'s detection. Output is "shaped echo
trimmed to anchor" — meaning the runtime BUG-LORI-REFLECTION-02
Patch C work selected ONE concrete anchor from the operator
directive ("West St. Paul" likely) and trimmed Lori's echo to lead
with that anchor.

For a normal chat turn, that's exactly the right behavior. For a
Life Map ENTRY harness — where the operator is explicitly asking
Lori to write a longer warm note — that's destructive.

## Why this matters

The Life Map harness is a deliberate operator-driven extraction of
content longer than a normal conversational turn. The wrapper
treats every turn as a conversational turn, regardless of intent.
That means the harness produces clipped Life Map entries even when
the underlying LLM is producing the right content.

Same content-loss class as the sibling
BUG-LIFEMAP-CONTEXT-TRUNCATION-01 (input side) — this is the
output-side equivalent.

## Proposed fix

### Option A — operator-directive opt-out for comm_control

Add an HTTP header / WS message flag (e.g. `x-harness-mode: 1` or
`{"mode": "lifemap_entry"}` in the chat WS open frame) that the
operator UI sets when it's driving a structured-output harness. When
present:

- `comm_control` skips the `too_long` cap (or raises it to
  500-1000 words)
- `comm_control` skips the `response_stub_collapse` detection
- Reflection-shape still runs (it's anchor-grounding, not
  trimming-only) but with a higher word budget

The harness becomes a deliberate operator-side opt-out, with the
default still being narrator-safe shaping.

### Option B — per-style word-cap adjustment

Recognize that `oral_history` style's whole point is longer
responses. Bump the cap (currently ~55 words from the 2026-05-07
work, with adaptive +35 for substantive narrator turns) to ~120
words for `oral_history`. Doesn't help with the
`response_stub_collapse` false positive but reduces the trim
frequency.

### Option C — directive-tag heuristic

Have `comm_control` parse the operator directive at the top of the
user turn and, if it detects phrases like "Write a Life Map entry"
or "write a fuller oral-history note", bump the budget for that turn
only. Heuristic, brittle, not recommended as the primary fix.

Recommend **A + B combined** — explicit opt-out for harness mode
AND a more generous default for oral_history style.

## Acceptance gates

1. Re-run the John Baldy Life Map harness with the harness-mode
   flag set. No `[chat_ws][comm_control] changed=True` lines for
   the era prompts. Lori produces 120-180 word warm era entries.
2. Regular chat turn (no harness flag) still gets the existing
   comm_control discipline: caps, stub-collapse detection,
   reflection-shape.
3. `tests/test_shape_reflection.py` (2026-05-05) all 21 cases
   still pass.
4. `tests/test_lori_communication_control.py` stub-collapse
   detection tests (2026-05-09) all 5 cases still pass.

## Files likely touched

- `server/code/api/services/lori_communication_control.py` —
  Step 3.5 wire + Step 6 stub-collapse detection + add a
  harness-mode skip
- `server/code/api/routers/chat_ws.py` — read the harness-mode
  flag off the chat WS open frame
- `ui/js/app.js` — the operator-driven Life Map harness path
  needs to set the flag when sending era prompts (if any future
  in-app harness lands)
- `prompt_composer.py` — already routes by `turn_mode`;
  add an `oral_history_lifemap_entry` mode variant

## Related lanes

- 2026-05-07 BUG-LORI-RESPONSE-MID-SENTENCE-CUT (#60) — sentence-
  boundary walk in `_truncate_to_word_limit`. The trim point is
  smarter than a hard slice, but it still trims content.
- 2026-05-07 BUG-LORI-RESPONSE-CAP-ADAPTIVE (#62) — +35 word
  headroom for substantive narrator turns. Doesn't help with
  operator-directive turns.
- 2026-05-09 BUG-LORI-RESPONSE-STUB-COLLAPSE-01 — the detector
  firing here. Working as designed; the issue is the wrapper
  treating a harness turn as a normal turn.
- 2026-05-05 BUG-LORI-REFLECTION-02 Patch C — the runtime
  reflection-shape `shape_reflection()` that produced
  `actions=shaped_echo_trimmed_to_anchor`.

## Investigation notes

Captured via `scripts/tail_harness_log.sh` (banked 2026-06-17).
Same filtered log run as the sibling
BUG-LIFEMAP-CONTEXT-TRUNCATION-01 — both fired on the same era 1
turn, evidence two paragraphs apart in the same log.
