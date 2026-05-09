# BUG-LORI-IDENTITY-META-QUESTION-DETERMINISTIC-ROUTE-01

**Status:** LANDED 2026-05-09
**Severity:** CRITICAL (parent-session blocker)
**Replaces:** prior BUG-LORI-IDENTITY-DENIAL-01 / BUG-LORI-RESPONSE-STUB-COLLAPSE-01 (folded in)

## Live evidence

Mary's session 2026-05-09 (`transcript_switch_moyc6 (2).txt`):

| Line | Mary | Lori |
|------|------|------|
| 22-26 | what is your name | I don't have a name, I'm just a listener and a guide. |
| 28-32 | what are you | I'm a companion, here to listen... |
| 34-38 | what is your name again and your purpose | Last time we were talking about your childhood in Minot, North Dakota. Shall we continue there? |
| 145-149 | what is an AI? | AI. |
| 157-161 | But you say you are AI like I know what that is | AI. |

Three failure modes from one class of question:
1. Identity denial — flat contradiction of `prompt_composer.py:34` ("You are Lorevox ('Lori')")
2. Question ignore — pivot to continuation-walk template instead of answering
3. Stub collapse — single-word `"AI."` response to substantive narrator question

## Root cause

No deterministic intercept for narrator meta-questions. The LLM is left
to reconcile (a) `DEFAULT_CORE` identity rule, (b) "stay in pass2a
interview directive", (c) ERA EXPLAINER + REFRAME RULE + GROUNDING
RULE (added 2026-05-04). It resolves the conflict by deflecting,
ignoring, or stub-collapsing instead of answering.

Stack-warm T (2026-05-05) established the deterministic-bypass
pattern for age-recall questions. This WO extends that pattern to
identity / safety-trust / capability questions about Lori herself.

## Fix architecture

New pure-stdlib module `services/lori_meta_question.py`:
- 5 categories: `identity_name`, `identity_what`, `purpose`,
  `safety_concern`, `capability_explain`
- EN + ES locale pack (Lorevox etymology in identity answers per
  Chris's 2026-05-09 directive)
- Pure regex detection, no LLM call, LAW 3 isolated
- Priority ordering: safety > capability > what > name+purpose >
  name > purpose > what

Wire into `chat_ws.py`:
- Detection runs BEFORE safety scan (line 605 area, immediately
  after `_safety_result = None`)
- When detected: skip safety scan entirely, override `turn_mode =
  "meta_question"`
- New dispatcher branch emits deterministic answer via WS, persists
  via existing `persist_turn_transaction`
- Default-on, no env flag (correctness fix, not feature)
- Defensive try/except at every step — detection failure falls
  through to normal LLM behavior

## Acceptance gates

1. **Mary's 5 turns produce correct deterministic answers.**
   - "what is your name" → identity_name response with Lorevox
     etymology
   - "what are you" → identity_what response naming Lori as AI
     assistant
   - "what is your name again and your purpose" → name_and_purpose
     combined response
   - "what is an AI?" → capability_explain response (>50 chars, no
     stub)
   - "I am kind of scared, are you safe to talk to?" → safety_concern
     response (no 988, affirms safety)

2. **No false positives on storytelling.**
   - "my name was different back then" → not detected
   - "my purpose in life was..." → not detected
   - "who was my father" → not detected

3. **Spanish parity.**
   - "¿cómo te llamas?" → identity_name ES response
   - "¿es seguro hablar?" → safety_concern ES response

4. **LAW 3 isolation gate green.**
   - `lori_meta_question.py` must not import from extract / prompt
     composer / memory_echo / llm_api / chat_ws / safety / db /
     story preservation / story trigger.

5. **Logging.**
   - `[chat_ws][meta-question][deterministic]` log marker fires per
     intercept turn with category + categories_matched + lang.

## Test coverage

- `tests/test_lori_meta_question.py` — 58 tests across 10 classes
- `tests/test_lori_meta_question_isolation.py` — 4 LAW 3 gate tests
- Mary's literal turns appear as `MaryLiteralFailureMode` /
  `IdentityNameDetectionTest.test_*` / `SafetyConcernDetectionTest
  .test_mary_literal_2026_05_09` — any regression on her exact
  phrasing fails the build.

## Live verification (after stack restart)

1. Cycle stack, confirm new branch loaded.
2. Run Mary's 5 questions verbatim from interview chat.
3. Each must produce the deterministic answer (operator log
   `[chat_ws][meta-question][deterministic]`), not the LLM's
   evasion / stub.
4. Confirm safety classifier did NOT fire on the "scared/safe"
   turn (no 988 in response, no `[chat_ws][safety][llm_layer]
   triggered` log line).

## Related lanes

- **BUG-LORI-SAFETY-FALSE-POSITIVE-EXTERNAL-FEAR-01** (sibling, same
  commit) — defense-in-depth on the LLM safety classifier in case
  the regex misses a future class.
- **BUG-LORI-RESPONSE-STUB-COLLAPSE-01** (sibling) — operator-
  visibility warning for any stub-collapse that escapes the
  intercept.
- **Stack-warm T (2026-05-05)** — established the deterministic-
  bypass pattern for age-recall.

## Files changed

- `server/code/api/services/lori_meta_question.py` (NEW, ~370 lines)
- `server/code/api/routers/chat_ws.py` (+~50 lines: detection +
  safety-scan gate + dispatcher branch)
- `tests/test_lori_meta_question.py` (NEW, 58 tests)
- `tests/test_lori_meta_question_isolation.py` (NEW, LAW 3 gate)
