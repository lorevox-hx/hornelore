# LOOP-01 R4 master eval readout

Date: 2026-04-19
Report: `master_loop01_r4.json` (283,780 bytes, 104 cases, live mode)
Compared against: `master_loop01_r2.json`, `master_loop01_r3.json`,
`master_loop01_r3b.json`.
Companion docs: `loop01_r4_code_review_while_eval.md` (tactical),
`loop01_r4_strategy_bridge.md` (R5+ architecture),
`loop01_r4_eval_first_note.md` (eval-first protocol).

---

## TL;DR

R4 recovered **+4 on the contract v2 subset** (25 → 29) where the
eleven patches were aimed, but paid for it with **+5 must_not_write
violations** (Patch E over-reach), a **dense_truth collapse** (1 → 0
passed, avg 0.352 → 0.083) most plausibly driven by prompt truncation,
one direct **Patch H regression** (case_011 date *un-normalised*),
and one **wrong-entity extraction** (case_053 flipped narrator's
family). Net vs R3b: **−1 passed, −0.023 avg score**. R2 remains the
best baseline at 57 passed and 0.682 avg — the R3 regression has not
been recovered.

R5 should not start until we decide what to keep and what to roll back
from the R4 patch set, which this doc ends with.

---

## Headline numbers

|                         | R2        | R3    | R3b   | R4        |
| ---                     | ---       | ---   | ---   | ---       |
| Passed / 104            | **57**    | 49    | 50    | 49        |
| Pass rate               | **54.8%** | 47.1% | 48.1% | 47.1%     |
| Avg overall score       | **0.682** | 0.594 | 0.605 | 0.582     |
| Contract v3 / 62        | **33**    | 28    | 28    | 30        |
| Contract v2 / 62        | **30**    | 25    | 25    | **29**    |
| V2-compat all / 104     | **44**    | 33    | 34    | 35        |
| must_not_write viol.    | 2         | 2     | 2     | **7**     |

**By case type**

| Type            | R2      | R3      | R3b     | R4      |
| ---             | ---     | ---     | ---     | ---     |
| contract        | 33/62   | 28/62   | 28/62   | 30/62   |
| mixed_narrative | 10/19   | 6/19    | 7/19    | 7/19    |
| dense_truth     | 1/8     | 1/8     | 1/8     | **0/8** |
| follow_up       | 6/8     | 7/8     | 7/8     | 6/8     |
| null_clarify    | 7/7     | 7/7     | 7/7     | 6/7     |

**By chunk size**

| Size   | R4 passed | R4 avg  |
| ---    | ---       | ---     |
| tiny   | 22/42     | 0.644   |
| small  | 18/34     | 0.664   |
| medium | 9/24      | 0.411   |
| large  | **0/4**   | 0.242   |

The tiny/small bucket is where the contract patches paid off; the
medium/large bucket is where the regressions concentrated, which
matches the VRAM-GUARD evidence below.

**Failure category trend**

|                        | R2 | R3 | R3b | R4 |
| ---                    | -- | -- | --- | -- |
| schema_gap             | 27 | 25 | 26  | 29 |
| llm_hallucination      | 11 | 12 | 11  | 14 |
| field_path_mismatch    | 16 | 26 | 25  | 14 |
| noise_leakage          | 15 | 9  | 9   | 12 |
| guard_false_positive   | 2  | 2  | 2   | 4  |

field_path_mismatch is the one category that improved materially since
R3 (26 → 14), which is where Patch I (alias batch) and Patch K
(family.marriagePlace schema) were targeted. That recovery is real.

---

## Step 0b — VRAM-GUARD truncation confirmed

ChatGPT's api.log finding is confirmed. Grep for `VRAM-GUARD` in the
active log returns **21 truncation events** during the R4 eval run,
with input-token counts ranging 8194 → 8738 (truncation target 8192).

The truncation code in `api.py` lines 249-251:

```python
if inputs["input_ids"].shape[-1] > MAX_CONTEXT_WINDOW:
    inputs = {k: v[:, -MAX_CONTEXT_WINDOW:] for k, v in inputs.items()}
```

uses a **trailing** slice, which chops the **beginning** of the
prompt — that's the system instructions + few-shots + schema catalog.
On a truncated call the model is answering without ever seeing the
instructions, only the transcript + target field.

The truncations correlate sharply with chunk size in the case-type
results: **large chunks 0/4 passed, medium 9/24, tiny/small 40/76**.
`dense_truth` (always medium/large) went 1/8 → 0/8. Three of the nine
R3b→R4 regressions are medium-chunk schema_gap failures (case_076,
case_086, case_104) — all plausible truncation victims.

**This is a larger score mover than any single patch finding in the
code review.** Every per-axis delta below should be read with this
caveat: cases that trip VRAM-GUARD are not representative of the
extractor; they are representative of the extractor running without
its system prompt.

Two independent fixes are available, and one should be picked before
R5 work begins:

1. **Shrink the prompt.** The current prompt carries all of
   `EXTRACTABLE_FIELDS` as the schema catalog regardless of section
   (this is code review finding #5, the `compact_catalog isn't
   compact` bug). Fixing that alone is likely to pull the 8200-ish
   dense cases under the 8192 budget.
2. **Raise MAX_CONTEXT_WINDOW.** If VRAM allows, move to 16384 or
   32768. Cheaper in code; more expensive in VRAM; does not address
   the prompt-bloat root cause.

Recommendation: do (1) first. It's the same fix we were going to make
eventually, and it removes the truncation without paying VRAM cost.

---

## Step 0 — Patch-H scorer-drift audit on the 8 R3b→R4 gains

For each gain, check whether Patch H canonicalisation (ISO dates /
canonical birthOrder) is what moved the score.

| case_id  | Patch-H touched?            | Why it moved                                   |
| ---      | ---                         | ---                                            |
| case_005 | yes (family.children.dob)   | R3b extracted None → R4 extracted "October 4th, 1991" (genuine extraction win, not scorer drift) |
| case_010 | no                          | no H-fields involved                           |
| case_013 | yes (family.children.dob)   | R3b None → R4 "December 24, 1962" (genuine)    |
| case_015 | no                          | no H-fields                                    |
| case_027 | no                          | no H-fields                                    |
| case_037 | no                          | no H-fields                                    |
| case_072 | yes (family.marriageDate)   | R3b had **answer-dump** (full paragraph) → R4 "1959-10-10" (Patch A + Patch H working together; genuine) |
| case_103 | no                          | no H-fields                                    |

**Conclusion: none of the R4 gains are pure scorer drift.** In every
case where Patch H touched the field, the R3b value was either
`None` or a raw answer-dump — so the move is a real extraction win
from Patch A (answer-dump cap) and/or Patch H (canonicalise),
working together. The scorer-compatibility trap the research warned
about didn't fire here, because the comparison isn't "prose date vs
ISO date" — it's "no date / paragraph-with-a-date-in-it vs ISO date."

---

## R3b → R4 movement

**Gains (8 cases)** — all clean contract or mid-noise mixed_narrative:
case_005, case_010, case_013, case_015, case_027, case_037, case_072,
case_103.

**Regressions (9 cases)** split cleanly into four buckets:

### Bucket 1 — Patch E guard false positives (3 cases)
| case     | narrator | forbidden violated                                              |
| ---      | ---      | ---                                                             |
| case_038 | janice   | health.majorCondition, health.milestone, health.lifestyleChange |
| case_056 | janice   | health.majorCondition, health.milestone                         |
| case_100 | janice   | community.role                                                  |

All three cases **were passing at R3b** and newly trigger Patch E's
guard at R4. Patch E was scoped narrowly in design ("uncle/aunt ≠
children, sibling ≠ parent") but in practice is now stripping janice's
narrator-first health writes and a community.role write. The R4
must_not_write violation count went 2 → 7 entirely from Patch E.

**Action:** task #69. Tighten or narrow Patch E before R5.

### Bucket 2 — medium-chunk schema_gap (3 cases, VRAM-GUARD candidates)
| case     | profile                             | R3b → R4                                               |
| ---      | ---                                 | ---                                                    |
| case_076 | mixed_narrative / medium / mixed    | marriageDate + spouse.firstName both 1.0 → None        |
| case_086 | dense_truth    / medium / dense     | education.earlyCareer 0.8 → None                       |
| case_104 | mixed_narrative / medium / g_garbage| laterYears.lifeLessons 0.8 → None                      |

Complete extraction loss on medium chunks, cases that previously
produced correct values. Strong match for the VRAM-GUARD
truncation pattern: the prompt is too long, system instructions get
chopped, and the model falls back to nothing. These are not R4 patch
regressions — they are pre-existing truncation behaviour newly
exposed by other patches changing per-case token budget.

**Action:** fix prompt bloat (finding #5) and re-run. If these
recover without touching A-K, they were never R4 regressions.

### Bucket 3 — Patch H ordering regression (1 case)
| case     | path                | R3b → R4                                |
| ---      | ---                 | ---                                     |
| case_011 | personal.dateOfBirth| "1939-12-24" (1.0) → "Christmas Eve, 1939" (0.0) |

**This is a direct hit on code review finding #3** (Patch H runs
after Patch D). At R3b this field was getting ISO-canonicalised
somewhere. At R4, Patch D's birthOrder rerouter changed the path
this value travels through, and Patch H no longer fires on it — so
we wrote the raw prose form. Patch H is firing on *some* paths but
not *this* one after Patch D's rewrite.

**Action:** task #67. Audit Patch H's set of paths against Patch D's
rewrite targets. Either run Patch H *after* Patch D's rewrite, or
register the rewritten path with Patch H.

### Bucket 4 — wrong-entity extraction + subtle (3 cases)
| case     | issue                                                                  |
| ---      | ---                                                                    |
| case_053 | complete entity flip — christopher's father Kent became "Dorothy", sibling Vincent became "Christine" (classic OTS-bias, entity-binding failure) |
| case_088 | pets.notes — narrator-signature voice ("rode him every morning") compressed to third-person ("narrator's favorite horse") — scores 0.67 → 0 under signature-preservation |
| case_011 | (also Bucket 3) |

case_053 is the frame-perfect demonstration of the Pillar-2
(mirrored counterexamples) concern from `loop01_r4_strategy_bridge.md`:
the model took a chunk where the narrator talks about his parents,
bound the facts to the wrong parent/sibling names, and the alias-dict
+ rerouter stack had nothing to say about it because the *paths* were
all legal. Validity passed; binding was wrong. No patch A–K targeted
this and no patch would have caught it.

**Action:** task #68. Inspect the case_053 chunk + raw LLM output to
confirm OTS-bias symptom; this is an R5 (Pillar 2) test case, not an
R4 patch.

---

## R2 → R4 debt

13 cases pass R2 but fail R4. Breakdown:

| Bucket                        | Cases                                                   |
| ---                           | ---                                                     |
| Patch E false positives       | case_038, case_056, case_100                            |
| VRAM-GUARD truncation victims | case_076, case_077, case_078, case_086, case_104        |
| Field-path/schema regressions | case_012, case_020, case_023, case_061                  |
| Patch H ordering (case_011)   | case_011                                                |

The field_path_mismatch category improved R3→R4 (26 → 14) but the
schema_gap category nudged up (26 → 29). Some of that is the truncation
victims appearing as schema_gap. The remaining true schema_gap
regressions (case_012, case_020, case_023, case_061) are pre-R4 — they
regressed in R3 and have not been recovered. They overlap with the
alias/rerouter collision cases documented in the code review (#1, #8,
#14).

---

## Per-patch keep / roll back / isolate / abandon

Using movement evidence only. Some calls are confident; some wait on
the prompt-truncation fix.

| Patch | Intent                                           | Evidence                                                                                          | Call                          |
| ---   | ---                                              | ---                                                                                               | ---                           |
| A     | cap scalar-field value length (answer-dump)      | case_072 went from full paragraph to clean date. No observed regressions from A.                  | **KEEP**                      |
| B     | parenthood + relationship_anchors zero-raw       | No clean attribution in movement set. No regressions attributable.                                | **KEEP** (neutral)            |
| C     | pets.name / pets.species routing                 | No pets.name / pets.species cases in movement set. case_088 pets.notes regressed but Patch C targets name/species, not notes.  | **KEEP** (weak signal)        |
| D     | narrator-first-person birthOrder                 | case_011 regression is Patch D + Patch H ordering interaction. Patch D itself correct in intent. | **KEEP, but fix ordering**    |
| E     | relation-scope guard (uncle/aunt ≠ children)     | Directly responsible for +5 must_not_write violations (cases 038, 056, 100).                     | **SURGICAL ROLLBACK**         |
| F     | contrast-affirmation exception in negation-guard | No observed regressions. Can't isolate gains.                                                     | **KEEP** (neutral)            |
| G     | grandparents.ancestry schema + few-shot          | No observed regressions. Ancestry-binding cases not represented enough in the bank to measure.    | **KEEP** (neutral)            |
| H     | write-time normalisation for dates + birthOrder  | Cases 005/013/072 moved fail→pass *because* of H. Case 011 regressed *because* of H ordering.    | **KEEP, but fix ordering with D**  |
| I     | field-name aliases batch                         | field_path_mismatch went 26 → 14 (R3→R4). Almost certainly I.                                     | **KEEP**                      |
| J     | ancestor-military alias                          | No ancestor-military cases in movement set.                                                       | **KEEP** (neutral)            |
| K     | add family.marriagePlace to schema               | No marriagePlace cases in movement set.                                                           | **KEEP** (neutral)            |

**Summary of patch calls:**
- KEEP as-is: A, B, C, F, G, I, J, K
- KEEP but fix ordering bug (tasks #67 = Patch D/H ordering): D, H
- SURGICAL ROLLBACK (task #69 = Patch E narrowing): E

No full rollbacks. Only Patch E needs a targeted narrowing before R5
begins. Patches D and H stay but need their ordering reconciled.

---

## What this means for R5

The R4 patch set did what patches can do: it moved the field-path
mismatch category from 26 to 14, shored up the contract v2 subset
+4, and started normalising dates and birthOrders cleanly. That's
legitimate progress.

The R4 patch set cannot do what it was never designed to do:

- It cannot fix dense_truth cases where the prompt is truncated
  before the model sees the schema. That's a harness / prompt
  architecture problem (the `compact_catalog` bug, finding #5).
- It cannot catch entity-binding errors like case_053 where every
  extracted path is legal. That's an architecture problem
  (Pillar 2 in `loop01_r4_strategy_bridge.md`).
- It cannot stop its own patches from colliding with each other
  (Patch D vs Patch H, Patch E over-reach). That's a mechanism
  problem (Pillar 1: validity vs. binding separation).

The readout validates the bridge document: what's left to fix in
R4 is finite (fix ordering, narrow Patch E, shrink the prompt), and
everything past that needs the architectural work in R5.

---

## Next steps (in order)

1. **Fix the prompt-bloat / VRAM-GUARD truncation** (finding #5).
   Rebuild the schema catalog per-section so dense cases fit under
   8192 tokens. Re-run and confirm case_076 / case_086 / case_104 /
   case_077 / case_078 recover.
2. **Narrow Patch E** (task #69). Remove / tighten the branch that
   catches janice's health fields and community.role. Re-run and
   confirm case_038 / case_056 / case_100 recover.
3. **Reconcile Patch D + Patch H ordering** (task #67). Make Patch H
   fire on paths Patch D rewrites into. Re-run and confirm
   case_011 recovers.
4. **Inspect case_053** (task #68) — confirm OTS-bias symptom; bank
   as an R5 Pillar-2 test case, do not patch.
5. **Harness audit** (task #63) — should_pass drift audit, still
   pending.
6. After 1–3 land and eval confirms recovery, begin R5 scoping per
   `loop01_r4_strategy_bridge.md`.

No further R4 patches beyond items 1–3 above.
