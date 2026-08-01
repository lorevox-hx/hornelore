# Phase 5 — extraction prompt selection and its limitation

**Closed 2026-08-01.** WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01.

Counts and configuration only. No narrator prose. Raw reports are
gitignored; see `../manifests/` for their SHA-256 hashes.

---

## Why this work happened

Live Travel Doc work was running duplicate extraction calls, overloading
the GPU and timing out. That had to be fixed before any Trip Companion
acceptance could be trusted. It is fixed. The 114-case evaluation was one
regression check on the safer runtime, not a research programme — and it
was allowed to expand too far past the product goal before being stopped.

## What is fixed and frozen

| | |
|---|---|
| extraction owner | one (backend); the browser no longer extracts |
| execution path | `prompt_mode="raw_ephemeral"`, `conv_id=None` |
| persona / RAG / chat history | absent from extraction |
| extraction persistence | none — no `_extract_*` conversations or turns |
| `MAX_CONTEXT_WINDOW` | 8192, unchanged |
| VRAM / model / quantization | unchanged, tested envelope |
| oversized prompt | fails closed as `ExtractionPromptBudgetExceeded` |
| extraction truncation | zero |
| field catalog | complete, all 140 paths, never filtered |

Before: the extraction prompt reached the model at ~12,300 tokens against
an 8192 window and was silently front-truncated on every call, and every
call wrote two `turns` rows. 464 rows across 232 `_extract_*`
conversations are the receipt; they are left in place as history.

## The prompt selection

Measured on a 29-case delta pack built from the arm-B regressions, the
arm-B gains, the repeat-invalid-path cases, every `must_not_write` case
and the stubborn primary set. The pack captured the entire full-bank
delta (baseline 18/29, arm B 13/29).

| variant | catalog | few-shots | delta pack |
|---|---|---|---|
| arm B | grouped | topic-matched | 13/29 |
| b2b | grouped | legacy static (33) | 16/29 |
| **b2a** | **labeled** | **topic-matched** | **17/29 — adopted** |
| b2c | labeled | legacy static | **cannot run** |

`b2c` was not attempted: at ~7,984 tokens it exceeds the 7,296 compound
ceiling, so every compound extraction would have failed closed and the
run would have measured the budget rather than the prompt. This is worth
recording as a structural fact rather than a scheduling one — **the
legacy prompt only ever fitted because truncation was silently
discarding the composer's persona.** Remove the composer and the legacy
content alone is over the window. You can have the fail-closed budget or
the full legacy prompt, not both.

### The finding that reversed the working hypothesis

Phase 5 began from the belief that truncation was destroying the field
catalog and that this drove the hallucinated-field-path cluster. Arm B
ran with the complete catalog visible on every call, zero truncation —
and invented field paths went **up**, 49 → 52 offenders across 16 → 18
cases. Catalog *visibility* was not the driver.

What the catalog's **labels** turned out to be worth is the opposite of
the obvious guess: restoring them recovered four of the five cases arm B
had lost, while restoring the 33 legacy few-shots recovered three and
cost more elsewhere. The labels were carrying the weight, not the
examples.

## The limitation, stated plainly

- b2a was selected at **17/29 on the delta pack, below the 18/29 gate**
  that would have earned a full 114-case run.
- It was **not** given a second full-bank run. The agreed hard endpoint
  prohibited further prompt research, and that endpoint was the right
  call — the extractor had many known schema gaps before this work and
  they are not Phase 5's to close.
- On the delta pack b2a showed **2 rules fallbacks** and **1
  `must_not_write` violation** (`case_066`, `parents.notableLifeEvents`),
  which was already failing under arm B and is not a new regression.
- The last full-bank number for the bounded path is **arm B's 73/114**
  against a historical **78/114**. b2a is expected to sit between them on
  the full bank; that is an inference from the delta pack, not a
  measurement, and it is not claimed as one.

### Narrator-turn headroom

The labeled catalog costs ~6,300 chars that the narrator's own words no
longer get. At the pessimistic 4.0 chars/token floor, b2a leaves roughly
**5,300 chars of narrator turn** before the budget refuses, under the
tighter compound ceiling. The largest turn in the 114-case bank is 1,032
chars (median 172, p90 674), so the margin is ~5×. A pinned test states
this so a future prompt growth that eats it fails loudly instead of
surfacing as an operator's long story failing closed.

## Verification

- 60 live `[EXTRACT-BUDGET]` calls across the b2a and b2b runs: **zero
  budget refusals, zero truncations**, tokens 4,969–6,810, chars/token
  4.23–4.31.
- `_extract_*` conversations and turns: **232 / 464, unchanged** across
  every Phase 5 run.
- Family database untouched — all Phase 5 evaluation ran against
  `hornelore_evalcopy.sqlite3`.

## Not done, deliberately

No `b2c`, no label-plus-example variant, no further prompt tuning, no
additional question-bank testing. The temporary
`HORNELORE_EXTRACTION_VARIANT` selector has been removed; the bounded
prompt now has exactly one definition.
