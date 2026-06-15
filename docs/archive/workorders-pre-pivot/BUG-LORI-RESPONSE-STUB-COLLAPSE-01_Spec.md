# BUG-LORI-RESPONSE-STUB-COLLAPSE-01

**Status:** LANDED 2026-05-09 (detection-only, v1)
**Severity:** HIGH (parent-presentable surface)

## Live evidence

Mary's session 2026-05-09 14:03:23 + 14:04:53 (`transcript_switch_moyc6
(2).txt` lines 145-149 + 157-161):

> Mary: what is an AI? you tell me that like i know what AI is?
>
> Lori: AI.

> Mary: But you say you are AI like I know what that is
>
> Lori: AI.

Console log: `[ml-tts][fe] lang=en chars=3 preview="AI."` — the
3-character byte-stable response actually reaches the chat bubble
and TTS. Sandwiched between paragraph-length real answers (line 154).

## Root cause

LLM under directive pressure is collapsing on substantive narrator
questions. The composer's `INTERVIEW DISCIPLINE — STRICT` block tells
Lori to "acknowledge briefly, then move on" + "≤55 words" + interview
track gravity. Llama-3.1-8B interprets meta-questions about itself
as fields to echo back rather than questions to answer — emits the
narrator's own keyword as the entire response.

Reflection shaper (BUG-LORI-REFLECTION-02 Patch C) is NOT the
culprit — Cases A/B/C1/C2/D never strip content this aggressively.
This is the LLM's own output, reaching `lori_communication_control`
in stub form and passing the existing word-cap and atomicity checks
because the stub is technically valid.

## Fix architecture

Two layers:

1. **Primary fix (in BUG-LORI-IDENTITY-META-QUESTION-DETERMINISTIC-
   ROUTE-01).** The deterministic meta-question intercept catches
   "what is an AI?" / "what are you" before the LLM is invoked,
   and emits a full deterministic answer (capability_explain
   category, ≥50 chars, EN+ES). This eliminates the known stub-
   collapse failure shape entirely.

2. **Detection-only safety net (this WO).** New `Step 6` in
   `lori_communication_control.py`: when the final response is ≤3
   words AND narrator's input was substantive (≥4 words AND not a
   safety-triggered turn), append `response_stub_collapse` to
   `failures`. Operator visibility via `[lori][response-stub]` log
   marker (downstream consumers of `failures` may add this).

   v1 is detection-only — no rewrite. Replacing real short answers
   with fabricated content would backfire on legitimate brevity
   ("Yes." in response to a yes-no question is fine). Iteration
   adds deterministic-rescue composer for specific failure shapes
   once the in-the-wild distribution is characterized.

## Acceptance gates

1. **Mary's "AI." stub flags.**
   - `enforce_lori_communication_control(assistant_text="AI.",
     user_text="what is an AI? you tell me that like i know what AI
     is?")` → `failures` contains `response_stub_collapse`.

2. **Single-word response to long narrator question flags.**
   - `assistant_text="Spokane.", user_text="tell me what you know
     about my time growing up there"` → flags.

3. **Normal response does not flag.**
   - Multi-word real reflection-and-question response → no flag.

4. **Trivial narrator does not flag short Lori.**
   - `user_text="yes"` + `assistant_text="Got it."` → no flag.

5. **Three-word narrator does not flag.**
   - `user_text="that's right yes"` + short Lori → no flag (4-word
     floor on narrator side).

6. **Safety-triggered turns are exempt.**
   - When `safety_triggered=True`, short responses are legitimate
     (deterministic safety templates can be brief) → no flag.

## Test coverage

`tests/test_lori_communication_control.py::StubCollapseDetectionTest`:
- Mary's literal "AI." → flags
- Single-word "Spokane." to long narrator → flags
- Normal response → no flag
- Yes-narrator + short Lori → no flag
- 3-word narrator + short Lori → no flag (boundary)

24/24 tests green.

## Live verification

This is detection-only, so live verification is observational:
1. After stack restart, run any session.
2. Grep `api.log` for `response_stub_collapse` failure label
   (typically surfaces in `[chat_ws]` log lines containing the
   failure list).
3. The meta-question intercept should make this near-zero on Mary-
   class turns; remaining flags identify NEW failure shapes for
   future iteration.

## Related lanes

- **BUG-LORI-IDENTITY-META-QUESTION-DETERMINISTIC-ROUTE-01**
  (primary fix) — eliminates the known stub-collapse class.
- **BUG-LORI-RESPONSE-MID-SENTENCE-CUT-01** (closed 2026-05-07) —
  mid-sentence chop class. Different failure mode (truncation, not
  stub-collapse) but same operator-visibility theme.

## Files changed

- `server/code/api/services/lori_communication_control.py` (+~25
  lines: Step 6 detection block)
- `tests/test_lori_communication_control.py` (+~50 lines: 5 new
  tests in StubCollapseDetectionTest)
