# Testing doctrine — a fixture may not supply the property being proven

**Status:** ACTIVE, adopted 2026-09-04 during `WO-LORI-ARCHIVE-TO-MEMOIR-02`
Phase 3. **To be folded into `CLAUDE.md` at the Phase 3 reconciliation.**

## The rule

> **A fixture may supply values, but it may not supply the property being
> proven.** That property must be produced by shipped code, or loaded from the
> real persisted/file format. **Every helper-level assertion needs a
> production-boundary companion, and every mutation must make that companion
> fail.**

## Why it exists

The table below is the authoritative count — **this file owns it, and no other
document restates the number.** All share one shape: *a test constructs the
property it intends to prove, exercises a helper against that constructed
shape, and passes without crossing the production boundary that actually
creates or consumes the value.*

| # | The claim | What the fixture supplied | What production actually does |
|---|---|---|---|
| 1 | "this fixture has 3 scene anchors" | the number, in a comment | `story_trigger` scored 2 — a bare year is not a TIME anchor |
| 2 | "the kinship guard groups correctly" | `repeatableGroup` on the dict | the field is `_repeatableGroup` until after the guard runs |
| 3 | "the downgrade is applied" | asserted on the helper's return | the constructor re-derived `writeMode` from the schema |
| 4 | "a downgraded spouse doesn't prefill" | a guessed questionnaire nesting | `parsePath` splits `family.spouse.firstName` differently |
| 5 | "noop vs succeeded is decided correctly" | tested `_store_result` and the trace | neither is the branch that decides |
| 6 | "the envelope mirrors the item" | a hand-built dict | production builds it inside `_apply_transcript_safety_layer` |
| 7 | "token matching, not substring" | a fixture with no cue present | both behaviours quarantined it — no discrimination |
| 8 | "preservation accounting works" | `truthZones: {"must_extract": [...]}` | no bank uses that shape; 114 real cases returned empty |
| 9 | "the router records session and turn provenance" | `session_id="s1"`, `turn_id="t1"` passed straight into the router | `extract.py:9748` reads `req.conv_id` / `req.turn_id`, **neither of which is a field on `ExtractFieldsRequest`** — production sends `None` for both, while the real `session_id` field goes unused |
| 10 | "`ex-wife` is canonicalized to relation `wife`" | called `interpret_phrase()` directly and asserted on its return | no `*.relation` item was ever sent through `run_field_extraction`. Production moved the item to the right lane carrying the narrator's phrase `ex-wife` **as the stored relation value** — the exact collapse the phase existed to prevent |
| 11 | "the lexical provenance is recorded" | asserted on the dict the canonicalizer returns | `ExtractedItem(...)` on the LLM path **names its kwargs explicitly**, so the recorded phrase was dropped one call later. No error, no warning; the field simply arrived `None` |

Every one of these shipped green. Mutation testing caught 5, 6, 7 and 11;
external review caught 1, 2, 3, 4, 8 and 10. **Nothing in the test suite itself
objected.**

**Instances 10 and 11 are the same seam twice** — a value produced correctly and
then lost between the producer and the consumer — and they are the reason the
rule below about mutations exists in the form it does. Number 11 was found only
because a mutation was written for the constructor line; grepping for the field
name would have found it present and concluded it worked.

## And a mutation that catches nothing is a missing test

Recorded 2026-09-05. Mutation `L9` restores the defect where a reading is
located by searching the answer again instead of using the offsets it already
carries — and **the whole suite stayed green.** Every passage in it mentioned
each phrase once, where a search and a span agree, so nothing discriminated.

A `MISSED` verdict is not a note that the mutation was unimportant. It is the
gate saying *no test in this suite can tell these two products apart*, which is
the same statement as "this behaviour is untested". The fix is the discriminating
case — for `L9`, a passage saying `wife` three times, where the last reading
reports the first one's position — not the removal of the mutation.

## What follows from it

1. **Name the boundary.** For each test family, state the production
   *producer* of the value and its production *consumer*. If the test touches
   neither, it is a helper test and needs a companion.
2. **Load the real format.** Any test about a persisted or on-disk shape reads
   the real file — `data/qa/*.json`, the live schema, the shipped serializer —
   never a literal transcribed from memory.
3. **One production-path test per family, minimum.** Helper tests are allowed
   and useful; they are not acceptance evidence on their own.
4. **Evaluators load one real case per supported corpus format.** The question
   bank has three shapes; a test that exercises one proves nothing about the
   others.
5. **Source-string assertions are never acceptance evidence by themselves.**
   Grepping the product proves a line exists, not that it does anything. Pair
   every such check with one that runs the code. *(This rule cost an export:
   `lvStoryReviewRenderExtraction` exists so the operator view is tested by
   rendering it rather than by grepping it.)*
6. **A mutation must break the production-path assertion**, not only the
   helper one. If mutating the product leaves the suite green, the test is
   decorative — delete it or fix it.

## The audit that adopted it

Phase 3 test families, checked 2026-09-04. "Boundary" = does the test call a
production entry point rather than only a helper.

| Family | Production entry point | Real-format fixture | Boundary crossed |
|---|---|---|---|
| `test_extraction_finalization` | `run_field_extraction` (both paths) | schema via `EXTRACTABLE_FIELDS` | yes |
| `test_confirmation_reasons` | `run_field_extraction`, `_apply_transcript_safety_layer` | model fields via `model_fields` | yes |
| `test_review_only_results` | `_complete_claim_inner`, `_store_result` | `_Claim` fields read from the dataclass | yes |
| `test_kinship_group_guard` | `run_field_extraction` (both paths) | narrator text from the real defect | yes |
| `test_eval_preservation_accounting` | `score_case`, `preservation_accounting`, `normalize_truth_zones` | **`data/qa/*.json`, all three shapes** | yes |
| `projection_authority_domtest.js` | shipped `projection-sync.js`, `transcript-guard.js`, `bug-panel-story-review.js` | — | yes |
| `review_only_result_domtest.js` | shipped `interview.js` | — | yes |

**One gap was found and closed by this audit:** the Bug Panel's rendering of
`proposed_items` was source-string evidence only. It now runs the shipped
`renderExtraction` against a minimal DOM and reads the resulting text.

**And the audit immediately caught a ninth instance:** the first draft of that
render test passed a bare result object, because I supplied `renderExtraction`'s
input shape instead of reading it. It takes `d.extraction` and short-circuits on
`status`. Every assertion failed until the fixture was corrected against the
function. The rule works on the person applying it.
