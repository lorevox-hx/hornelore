# BUG-EX-PROTECTED-IDENTITY-FRAGMENT-WRITE-01

**Status:** LANDED 2026-05-09
**Severity:** HIGH (Shadow Review noise + identity-field corruption risk)
**Architecture Spec v1 classification:** Type C binding error (binding
layer fails to reject distress fragments routing to identity slots)

## Live evidence

Mary's session 2026-05-09 14:02:50 (`OPERATOR-LOG-2026-05-09-12-47-00.md`
+ Bug Panel screenshot):

> Narrator turn: "I am kind of scared, are you safe to talk to?"
>
> Extractor candidate: `personal.fullName = "scared about talking to"`

The extractor took Mary's panic phrase, span-bound it to the identity
slot, and surfaced it as a Shadow Review candidate alongside the
PERSONAL > FULLNAME label.

BUG-312 protected-identity gate (2026-04-29) routes this to
`suggest_only` not promotion, so it didn't corrupt truth — but the
candidate should never have been emitted at all. Shadow Review
fatigue compounds: every distress turn becomes a noise candidate.

## Root cause

Pure Type C binding error per Architecture Spec v1 §7.1 — the LLM's
schema-binding layer doesn't reject affect/distress vocabulary
fragments routing to identity-field slots. The extractor sees
"scared about talking to..." in narrator text, decides "this is a
narrator-self statement, fullName is a narrator-self field, bind."

Sibling failure class to:
- BUG-EX-PLACE-LASTNAME-01 (place fragments → lastName)
- BUG-ML-SHADOW-EXTRACT-PLACE-AS-BIRTHPLACE-01 (place mentions →
  birthPlace)

Same architecture: post-LLM regex guard.

## Fix architecture

New helpers in `extract.py`:
- `_AFFECT_DISTRESS_TOKENS` — EN+ES affect vocabulary
  (scared/afraid/anxious/worried/frightened/nervous/upset/...,
  asustada/preocupada/miedo/...). Whisper accent-strip variants
  included.
- `_AFFECT_DISTRESS_PHRASES` — EN+ES distress-prefix patterns
  ("I am scared", "estoy asustada", "tengo miedo", ...).
- `_AFFECT_GUARDED_FIELD_SUFFIXES` — `.fullName`, `.firstName`,
  `.lastName`, `.middleName`, `.maidenName`, `.preferredName`.
- `_value_starts_with_affect_token(value)` — value-prefix trigger
  (Mary's literal failure mode).
- `_looks_like_affect_phrase_for_value(text, value)` — indirect
  trigger ("I'm scared of [name]").
- `_drop_affect_phrase_as_name(item, source_text)` — applies both
  triggers; either fires drop.

Two independent triggers — EITHER drops the candidate:

1. **Value-prefix trigger.** Candidate value begins with affect/
   distress token. Catches Mary's literal value="scared about talking
   to". Real names don't begin with these words.
2. **Indirect-prefix trigger.** Value appears in source text after
   a distress phrase. Catches "I'm afraid of [name]" → name extraction.

Wired into the per-item loop in `extract_fields()` right after the
existing two PLACE guards, before any other processing. Pure post-
LLM cleanup — no SPANTAG flag, ships independently.

## Acceptance gates

1. **Mary's literal failure mode drops.**
   - `item={fieldPath:"personal.fullName", value:"scared about
     talking to"}, source="I am kind of scared, are you safe to
     talk to?"` → drop.

2. **Real names kept.**
   - "Mary Stanley" / "Kent" / "Pedro Núñez" → no drop.

3. **Value-starts-with-distress drops regardless of source.**
   - "scared", "afraid", "asustada", "miedo" as value prefix → drop
     even with empty source.

4. **Indirect distress-phrase drops.**
   - "I'm scared of Stanley" + value="Stanley" → drop.
   - "Estoy asustada de Juan" + value="Juan" → drop.

5. **Non-identity fields unaffected.**
   - `parents.occupation = "scared worker"` → no drop (guard only
     fires on guarded identity suffixes).

6. **Names in distress-vocabulary-but-unrelated text kept.**
   - "I was scared of the storms. My father was Kent." +
     value="Kent" → no drop (Kent not adjacent to "scared", value
     doesn't start with distress token).

7. **Spanish parity.**
   - All EN cases must work with ES equivalents (asustada,
     preocupada, miedo, nerviosa).

## Test coverage

`tests/test_extract_affect_name_guard.py` — 32 tests across 6 classes:
- `MaryLiteralFailureMode` — load-bearing tests on Mary's literal
  failure
- `ValueStartsWithDistressTokenTest` — 9 tests on prefix trigger
- `SpanishDistressPrefixTest` — 5 ES tests
- `IndirectDistressPhraseTest` — 4 indirect-trigger tests
- `FalsePositiveResistanceTest` — 8 tests (real names, neutral
  text, non-identity fields, edge cases)
- `HelperFunctionTest` — 4 unit tests on helper internals

32/32 green. Stubs FastAPI + pydantic in test setup so the
extract.py module imports without the real web stack (mirrors
`test_extract_place_birthplace_guard.py` pattern).

## Live verification (after stack restart)

1. Run Mary's literal turn through the chat path: "I am kind of
   scared, are you safe to talk to?"
2. Confirm:
   - Bug Panel Shadow Review does NOT show "personal › fullName" =
     "scared about talking to" candidate
   - api.log shows `[extract][affect-name-guard] drop fieldPath=
     personal.fullName value='scared about talking to'
     reason=value_starts_with_distress_token`
3. Run a clean identity disclosure turn ("My name is Mary Stanley")
   to confirm legitimate names still flow through.

## Master eval impact

Pure post-LLM regex guard, runs independently of SPANTAG (no flag
gate). Should have zero impact on the locked baseline
`r5h-followup-guard-v1` (78/114) since none of the 114 cases
exercise this exact pattern. Added as defense for live narrator
sessions only.

If the master eval re-runs, expected delta: 0 cases flipped, 0
crashes. Any flips would indicate an unexpected interaction worth
investigation.

## Related lanes

- **BUG-EX-PLACE-LASTNAME-01** — sibling guard for place→lastName
  binding. Same architecture.
- **BUG-ML-SHADOW-EXTRACT-PLACE-AS-BIRTHPLACE-01** — sibling guard
  for place→birthPlace binding. Same architecture.
- **#152 WO-EX-BINDING-01** — broader Type C binding lane;
  prompt-side binding rules for SPANTAG Pass 2. This WO ships
  immediately as post-LLM cleanup; BINDING-01 will eventually
  reduce the upstream emission.

## Files changed

- `server/code/api/routers/extract.py` (+~110 lines: helpers +
  guard + per-item loop wire)
- `tests/test_extract_affect_name_guard.py` (NEW, 32 tests)
