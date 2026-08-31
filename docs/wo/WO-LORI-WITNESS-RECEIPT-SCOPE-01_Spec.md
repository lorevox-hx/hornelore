# WO-LORI-WITNESS-RECEIPT-SCOPE-01

**Scope the witness receipt validator to witness mode, and stop it replacing
good replies with a worse template.**

Status: **SUPERSEDED 2026-08-31 by `WO-LORI-RESPONSE-GATING-AUDIT-01`**, which
found this validator is one of NINE rewrite layers and that measurement must
precede recalibration. Retained for its root-cause detail, which the successor
cites as L1/L2/L3.

Filed 2026-08-31 · Lane: Lori runtime (chat_ws response guards)
Evidence: `docs/reports/UI-REVIEW-2026-08-31.md` §C1 · interactive-dialogue
evaluation, `.runtime/eval/narrator-cohort/` + API log 2026-08-31 06:06–07:29

---

## 1. Symptom

Lori produces a good, grounded sentence. A validator rejects it and substitutes
a canned template. Two captures from one session, both on turns logged
`turn_mode=interview`:

```
[witness][llm-receipt] validator FAIL failures=too_short:22,too_few_facts:2/3
  before='New York marked a significant departure from Minnesota for you.
          What was your experience like adjusting to college life in the Northeast?'
  after ="Let and After — there's a lot held in that.
          What was your experience like adjusting to college life in the Northeast?"
```

```
[witness][llm-receipt] validator FAIL failures=too_short:17
  before='What does come to mind when you think about your childhood home
          on Capitol Hill in Seattle?'
  after ="Seoul and Min — there's a lot held in that. What does come to mind…"
```

The template appeared in **12 of 38** dense-run turns and reproduced in the
interactive run. It was reported up to now as "Lori's stock phrase". **It is
not model output.** It is this repair path.

The anchors are chosen by `[lori][reflection-shape] shaped_anchor_prepended`
over the narrator's raw text, which is why they include stopwords: `"Let"` and
`"After"` were taken from the narrator's own sentence *"**Let**'s move to my
coming of age. **After** high school…"*. Also observed: `"Paul and For"`,
`"For and They"`, `"Seoul and Min"` (`Min` truncating `Min-Jung`).

## 2. Root cause — three facts, all read from the tree

**2.1 The gate is detection, not mode.** `chat_ws.py:5656`:

```python
if (
    _witness_use_llm_receipt
    and _witness_detection_for_fallback is not None
    and final_text
):
```

`_witness_detection_for_fallback = _detect_we(user_text)` (`chat_ws.py:3497`).
So the validator runs on **any turn where witness detection returns a
detection**, independent of `turn_mode`. Both captures above were preceded by:

```
[witness][deterministic] type=STRUCTURED_NARRATIVE sub=structured anchor='Seattle'
[witness][deterministic] type=STRUCTURED_NARRATIVE sub=structured anchor='Minnesota'
```

`STRUCTURED_NARRATIVE` fires when a narrator tells a structured story. In an
oral-history system whose interview default IS `oral_history`, that is the
normal case, not the exception.

**2.2 The word floor is 35.** `lori_witness_mode.py:1626`:

```python
def validate_witness_receipt(..., min_words: int = 35, max_words: int = 110,
                             max_questions: int = 1, min_facts: int = 3)
```

A 17-word question — *"What does come to mind when you think about your
childhood home on Capitol Hill in Seattle?"* — is rejected for being too short.
The narrator-facing surface of this product should be producing short, gentle
turns; a 35-word floor is in direct tension with that.

**2.3 The fact floor is 3.** *"New York marked a significant departure from
Minnesota for you"* echoes one narrator fact, well. The rule wants three, so a
good sentence loses to a bad one on a count.

## 3. Why it exists — do NOT simply delete it

This guard was built twice, to fix worse things. Both markers are in the tree:

* `BUG-LORI-WITNESS-RICH-RECEIPT-01 (2026-05-10)` — replaced a thin
  `"I caught X, Y, and Z. What happened next?"` template that fired on Kent's
  TEST-B / TEST-C / TEST-G / TEST-COMBINED.
* `lori_structured_narrative_fallback.py` ("Boris Phase 7") exists so the
  system never again emits *"You went from X to Y, then Z, A, B, and C"* —
  the docstring names it **"the cascade dump that fired across 5 narrators in
  the 2026-06-17 full-family run."**

The intent is sound and remains sound: in witness mode a narrator with memory
difficulty should hear their own content reflected back, and the system should
verify Lori actually received it. The `fail CLOSED` posture on validator
exceptions is also correct and stays.

**This WO narrows scope and recalibrates. It does not remove the guard.**

## 4. Scope

In scope:

1. Gate the receipt validator to the mode it was designed for, rather than to
   any `_detect_we()` hit. Determine whether `STRUCTURED_NARRATIVE` should
   route here at all, or only the `META_FEEDBACK` / deep-witness detections.
2. Recalibrate `min_words` and `min_facts` for turns that legitimately reach
   the validator, with the values justified against real narrator turns rather
   than chosen.
3. Decide the failure behaviour: today a failure **substitutes** a canned
   string. Evaluate regenerating once under a corrective instruction, and
   falling back to substitution only if that also fails.
4. Fix the anchor picker's stopword leakage (`Let`, `After`, `For`, `They`) and
   name truncation (`Min` from `Min-Jung`) in whatever path survives.

Explicitly OUT of scope — do not touch in this WO:

* the model or the 8,192-token window (LOCKED)
* runtime safety (PARKED)
* `comm_control` atomicity trimming and `trim-to-one-q` — a separate defect
  with its own evidence, filed separately
* the language-drift guard and `prior_es_index` stickiness — separate
* extraction, the field whitelist, and JSON truncation — extractor lane
* Spanish canonical questions — deferred, per standing ruling

## 5. Acceptance criteria

1. **The two captured cases pass through unchanged.** Both `before` strings in
   §1 reach the narrator as written.
2. **No narrator-facing turn contains `— there's a lot held in that`** across a
   full cohort run, unless the validator legitimately fired in witness mode and
   the regenerate attempt also failed; every such instance is logged with its
   `failures=` list and its `turn_mode`.
3. **Stopword anchors are impossible.** `Let`, `After`, `For`, `They`, `It`,
   `Today` and the existing `_CASCADE_FILTER_TOKENS` set can never be selected
   as an anchor. Unit-tested directly.
4. **Names are not truncated.** `Min-Jung` never yields `Min`.
5. **The 2026-06-17 cascade cannot return.** The regression that Boris Phase 7
   was written for stays covered — assert the old
   `"You went from X to Y, then Z…"` shape is still unreachable.
6. **Kent's original cases still hold.** TEST-B / TEST-C / TEST-G /
   TEST-COMBINED behaviour from `BUG-LORI-WITNESS-RICH-RECEIPT-01` is
   re-verified, not assumed.
7. **Fail-closed is preserved.** A validator exception still routes to the
   deterministic fallback; that path is unchanged.
8. Every reported result names its interpreter and its skip count.

## 6. Test plan

Offline first, then one live pass.

* Unit: `validate_witness_receipt` against the two captured `before` strings —
  currently FAIL, must PASS after recalibration.
* Unit: anchor selection over the four observed narrator inputs; assert no
  stopword and no truncated name.
* Unit: gate condition — a `turn_mode=interview` turn with a
  `STRUCTURED_NARRATIVE` detection must not enter the receipt path (or must,
  with justification recorded in the WO report).
* Regression: the Boris Phase 7 cascade shape and the Kent TEST cases.
* Live: one narrow interactive pass through the real UI composer, reusing the
  existing `ZZ COHORT` narrators. No new people. Nothing deleted.

## 7. Open question for Chris

`STRUCTURED_NARRATIVE` currently routes to the witness receipt path. That may
be deliberate — a narrator telling a structured story is arguably exactly when
a receipt matters. If so, the fix is thresholds and the repair strategy only,
and the gate stays. **This is a product decision, not an implementation
detail, and it is not the agent's to make.**
