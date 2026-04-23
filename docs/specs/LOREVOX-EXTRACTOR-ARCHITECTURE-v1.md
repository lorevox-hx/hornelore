# Lorevox Extractor Architecture Spec v1

**Title:** Causal Architecture of Extraction Behavior — Layers, Failures, and Work Orders
**Status:** Spec v1 — ACTIVE (2026-04-23)
**Owner:** Chris (authored), Claude (stood up from paste)
**Audience:** every extractor-lane WO, prompt experiment, and eval cycle

This document supersedes scattered framing in individual WOs, reports, and changelog entries. When a WO, probe, or eval needs to situate itself in the system, it points here.

---

## 0. Purpose

Define a single canonical model for how extraction works in Lorevox:

- map **theory → implementation**
- map **failures → measurable eval signals**
- map **fixes → concrete WOs**

This replaces:

- vague "prompt tuning"
- scattered fixes
- misaligned experiments

## 1. Core Principle (LOCKED)

> **Extraction is semantics-driven, but errors arise from failures in causal attribution at the binding layer.**

This is the governing law of the extractor lane. Every WO in the extractor lane should be expressible as "which layer does this act on, and what binding failure does it reduce."

## 2. System Overview

Extraction is a causal pipeline, not a monolith:

```
Raw Text
   ↓
Architectural Layer (model)
   ↓
Control Layer (prompt + routing)
   ↓
Binding Layer (span → schema mapping)   ← PRIMARY FAILURE SURFACE
   ↓
Decision Layer (final structured output)
   ↓
Evaluation Layer (scoring + filtering)
```

Each layer has an owning code surface, an owning WO lane, a set of failure modes, and an owning eval signal. The layers are not interchangeable: a fix at the wrong layer leaves the real failure untouched and wastes eval attribution.

## 3. Layer → Code Mapping

### 3.1 Architectural Layer

- **Role:** token understanding, semantic representation, attention routing.
- **Code:** underlying LLM (LLaMA / Qwen / Hermes / GPT / Claude), HF Transformers stack, frozen model weights.
- **Control surface:** None for this system. Treated as fixed.
- **Typical failure signature:** none actionable from the extractor lane. Model-swap experiments (Hermes 3 / Qwen A/B) are deferred and only open if every other layer is exhausted.

### 3.2 Control Layer

- **Role:** steer extraction toward the task.
- **Code:** `server/code/api/routers/extract.py` (prompt construction), `server/code/api/routers/chat_ws.py` (runtime inputs), `state.session.currentMode` (frontend), section / target_path injection (interview.js → extraction payload).
- **Variables:** section, target_path, era, pass, mode.
- **Matrix result (#95 SECTION-EFFECT Phase 3, LOCKED):**
  - era / pass / mode → **non-causal** across all three typology exemplars, within-cell variance zero on 16 of 18 slots.
  - section / target_path → **conditionally causal** (Type A requires target_path as semantic anchor; Type B is invariant; Type C is mis-bound regardless).
- **Typical failure signature:** Type A collapse when target_path is absent. Does not explain Type C failures.

### 3.3 Binding Layer (NEW — PRIMARY FAILURE SURFACE)

- **Role:** map detected semantic spans → schema fields.
- **Code:** `extract.py` binding instructions / prompt rules, SPANTAG Pass 2 binding stage (#90, in flight), any post-bind guards (`_parse_llm_json`, validator, `_apply_transcript_safety_layer`, any future BINDING rule layer).
- **Responsibilities:**
  - **field selection** — the correct schema path for a detected span.
  - **domain separation** — resisting conflation between semantically-adjacent families (residence vs personal.placeOfBirth, residence.period vs education.gradeLevel, siblings vs narrative mentions).
  - **cardinality enforcement** — scalar fields emit ≤1, multi-value fields emit N as supported by text.
- **Typical failure signature:** `case_082`-class — four `personal.placeOfBirth` items, grade-range timing routed to `education.gradeLevel` instead of `residence.period`, `siblings.firstName` leaked from incidental mention. Prompt-invariant; target_path nudges but is not authoritative.

### 3.4 Decision Layer

- **Role:** produce final structured output.
- **Code:** LLM output formatting, constrained decoding (if any), schema alignment checks, salvage walker (`_salvage_truncated_array`), preamble tolerance (`_parse_llm_json`).
- **Typical failure modes:** hallucination (fabricated paths / values), omission (silent drops), incorrect mapping downstream of a bad binding decision. Secondary surface — most failures that appear here trace back to Binding.

### 3.5 Evaluation Layer

- **Role:** measure correctness.
- **Code:** `scripts/run_question_bank_extraction_eval.py`, `scripts/run_canon_grounded_eval.py`, `scripts/run_stubborn_pack_eval.py`, `scripts/run_section_effect_matrix.py`, `scripts/failure_pack.py` (sidecar).
- **Metrics:** pass / fail, `schema_gap`, `field_path_mismatch`, `hallucination`, `noise_leakage`, `defensible_alt_credit`, `defensible_alt_value_credit` (pending #97), `must_not_write`, `truncation_rate`, `parse_success_rate`, `parse_failure_rate`.
- **Gating principle:** every extractor-lane adoption decision goes through the standard post-eval audit block, with scorer-drift audited on every flip.

## 4. Failure → Eval Metric Mapping

### 4.1 Binding Failures (Primary)

| Failure Type | Example | Metric |
|---|---|---|
| Wrong field | residence → placeOfBirth | `field_path_mismatch` |
| Missing field | no `residence.period` | `schema_gap` |
| Leakage | grade-range → `education.gradeLevel` | `noise_leakage` |
| Over-emission | 4× `personal.placeOfBirth` | (cardinality — no dedicated metric yet; candidate for FIELD-CARDINALITY-01) |

### 4.2 Detection vs Binding Split

| Layer | Status |
|---|---|
| Detection (finding spans) | generally works |
| Binding (mapping spans) | **broken — primary failure surface** |

This is the core system diagnosis.

### 4.3 Decision Failures

| Failure | Metric |
|---|---|
| Fabrication | `hallucination` |
| Omission | `schema_gap` (when traceable to silent drop) |
| Overreach | `must_not_write` |

## 5. Question-Type Model (LOCKED)

Evidence source: #95 SECTION-EFFECT Phase 3 matrix (72 extractions, tag `se_r5h_20260423`).

### Type A — Target-Anchored Abstract Narrative

- Abstract prompts that require `target_path` to pin the semantic anchor.
- **Failure:** collapse without anchor (parse-or-fallback cliff in the case_008 V6 data).
- **Exemplar:** `case_008`.

### Type B — Overdetermined Factual

- Factual statements where evidence is self-binding.
- **Failure:** minimal; ignores routing signals cleanly.
- **Exemplar:** `case_018`.

### Type C — Weakly-Constrained Narrative (PRIMARY PROBLEM CLASS)

- Narrative evidence with ambiguous schema homing; places, timelines, and named people compete for scalar slots.
- **Failures:** over-emission, domain confusion, incorrect field binding — present even in the V1 "ideal" configuration.
- **Exemplar:** `case_082` (janice-josephine-horne / developmental_foundations / childhood_moves).

Type A/B/C is a **question-typology** classification, not a runtime state. Claude should reach for it when scoping any binding-class fix or adjudicating a friendly-fire probe result.

## 6. Causal Findings (from SECTION-EFFECT Phase 3, #95)

- **Q1:** era / pass / mode → **NO effect**.
- **Q2 / Q3:** **YES**, stratified by Type A/B/C (not unresolved).
- **Final disposition:** **PARK**. No further matrix iteration — the answers are locked; the follow-up work is lane work.

## 7. Fix → WO Mapping

### 7.1 WO-EX-BINDING-01

- **Layer:** Binding.
- **Goal:** correct causal attribution at the binding layer.
- **Fixes:** residence vs placeOfBirth; residence.period vs education.gradeLevel; sibling vs incidental mentions; minimal scalar-cardinality guard for `personal.placeOfBirth`.
- **Delivery vector:** SPANTAG Pass 2 prompt / binding contract (Option A, re-locked 2026-04-23).
- **Eval tag:** `r5g-binding` (after `r5f-spantag` banked).

### 7.2 WO-EX-SPANTAG-01 (#90)

- **Layer:** Detection → Binding separation.
- **Goal:** isolate spans before binding; reduce ambiguity at the binding step.
- **Delivery vector:** two-pass extraction pipeline (Pass 1 evidence, Pass 2 bind); Pass 2's controlled-prior block keeps `current_section` + `current_target_path` and drops `current_era` / `current_pass` / `current_mode` per #95 Q1 evidence.
- **Eval tag:** `r5f-spantag`.

### 7.3 WO-EX-FIELD-CARDINALITY-01 (NEW, deferred)

- **Layer:** Binding / Decision.
- **Goal:** enforce scalar vs multi-value field discipline beyond BINDING-01's minimal guard.
- **Examples:** `personal.placeOfBirth` ≤1, `personal.dateOfBirth` ≤1, `personal.firstName` ≤1, `residence.place` N-many, `siblings.firstName` N-many.
- **Opens when:** BINDING-01 PATCH 4 minimal scalar guard proves insufficient, or cardinality violations persist on non-`personal.placeOfBirth` scalars post-r5g-binding. Not a blocking prerequisite.
- **Explicitly not named FIELD-DISCIPLINE-01** — #142 owns "discipline" (run-report header). Name collision avoided.

### 7.4 WO-SCHEMA-ANCESTOR-EXPAND-01 (#144)

- **Layer:** Schema (orthogonal to binding).
- **Goal:** expand schema coverage for `greatGrandparents.*` identity fields. Lane 1 scorer-only trial annotations landed (r5h). Lane 2 pending.

### 7.5 WO-EX-VALUE-ALT-CREDIT-01 (#97)

- **Layer:** Evaluation.
- **Goal:** value-axis alt-credit for cases like case_087 where alt path matches but LLM value fuzzy-matches <0.5 against expected.
- **Status:** spec authored; runs after #144 Lane 1.

## 8. What NOT to Do (LOCKED)

Non-causal levers — do not tune these as primary fixes for extraction behavior:

- era / pass / mode tuning.
- routing-logic expansion.
- new section heuristics.
- prompt wording tweaks alone.

These are Control Layer knobs. The matrix proved they don't carry independent extraction signal at the layer where Type C fails.

## 9. Execution Order

```
1. SPANTAG (#90)                  [Detection → Binding separation]
2. BINDING-01                     [Binding correction, Option A]
3. FIELD-CARDINALITY-01           [Binding discipline, conditional]
4. SCHEMA + CANON work            [#144 Lane 2, #97, ongoing]
```

Each step banks its own eval tag and its own audit block.

## 10. Acceptance Model

A fix is valid if it:

- improves Type C cases (especially `case_082`).
- does **not** degrade Type A or Type B.
- reduces `field_path_mismatch`, `schema_gap`, `noise_leakage`.
- introduces no new `must_not_write` violations.
- passes the friendly-fire probe against a sample of non-target cases.
- preserves eval causal attribution (never collapses two mechanisms into one eval tag).

## 11. Logging Standard

Binding-layer fixes must emit a narrow debug marker:

```
[extract][BINDING-01]
```

Required so that eval interpretation can confirm a correction fired on the intended class. Sibling markers for future lanes: `[extract][SPANTAG]`, `[extract][FIELD-CARDINALITY-01]`, `[extract][turnscope]`, `[extract][binding]` (already in BINDING-01 spec for cardinality demotion).

## 12. Final Model

| Layer | Status |
|---|---|
| Architecture | stable |
| Control | mostly irrelevant for extraction (§6 Q1) |
| **Binding** | **primary failure point** |
| Decision | secondary |
| Evaluation | working |

**Final Statement:** Lorevox extraction failures are not caused by model capability or routing logic. They are caused by incorrect causal attribution at the binding layer.

---

## Appendix A — System Map (Causal Flow Diagram)

```
                 ┌──────────────────────────────┐
                 │        RAW NARRATIVE         │
                 │ (user speech / transcript)  │
                 └──────────────┬──────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────┐
│                 ARCHITECTURAL LAYER                          │
│  Transformer / LLM                                           │
│  - tokenization                                              │
│  - attention                                                 │
│  - semantic representation                                   │
│                                                              │
│  STATUS: FIXED                                               │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                    CONTROL LAYER                             │
│  extract.py / prompt construction                            │
│  - section                                                   │
│  - target_path                                               │
│  - (era / pass / mode — NON-CAUSAL)                          │
│                                                              │
│  EFFECT: CONDITIONAL (Type A only)                           │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                    BINDING LAYER  🔴                         │
│  (PRIMARY FAILURE SURFACE)                                   │
│                                                              │
│  Maps: semantic spans → schema fields                        │
│                                                              │
│  Responsibilities:                                           │
│   - field selection                                          │
│   - domain separation                                        │
│   - cardinality enforcement                                  │
│                                                              │
│  FAILURES:                                                   │
│   - field_path_mismatch                                      │
│   - schema_gap                                               │
│   - noise_leakage                                            │
│   - over-emission                                            │
│                                                              │
│  WOs:                                                        │
│   - BINDING-01                                               │
│   - SPANTAG (feeds into this)                                │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                    DECISION LAYER                            │
│  Structured output assembly                                  │
│                                                              │
│  - final JSON fields                                         │
│  - constrained decoding (if any)                             │
│                                                              │
│  FAILURES:                                                   │
│   - hallucination                                            │
│   - omission                                                 │
│                                                              │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                    EVALUATION LAYER                          │
│  run_canon_grounded_eval / cg-eval / master eval            │
│                                                              │
│  METRICS:                                                    │
│   - pass/fail                                                │
│   - field_path_mismatch                                      │
│   - schema_gap                                               │
│   - noise_leakage                                            │
│   - must_not_write                                           │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

## Appendix B — One-Page Quick Reference (Keep Next to Eval Runs)

```
LOREVOX EXTRACTION — QUICK REFERENCE (v1)

CORE LAW:
Extraction is semantics-driven,
but errors come from binding failures.

────────────────────────────────────────────

INPUT TYPES (DETERMINE BEHAVIOR)

Type A — Abstract / Narrative
→ Needs target_path
→ Failure: collapse

Type B — Overdetermined / Factual
→ Ignores control layer
→ Stable

Type C — Weakly Constrained  🔴
→ PRIMARY PROBLEM CLASS
→ Failure: mis-binding + leakage

────────────────────────────────────────────

WHAT DOES NOT MATTER (PROVEN)

✘ era
✘ pass (pass1 vs pass2)
✘ mode (open vs recognition)

→ DO NOT TUNE THESE

────────────────────────────────────────────

WHERE THE SYSTEM BREAKS

BINDING LAYER 🔴

Symptoms:
- residence → placeOfBirth
- grade → education instead of timeline
- multiple placeOfBirth values
- missing residence.period

Metrics:
- field_path_mismatch
- schema_gap
- noise_leakage

────────────────────────────────────────────

ACTIVE FIXES

#90 SPANTAG
→ separates detection from binding

BINDING-01
→ fixes:
   - residence vs birth
   - timeline vs education
   - sibling leakage
   - cardinality (minimal scalar guard)

NEXT:
FIELD-CARDINALITY-01 (if needed)

────────────────────────────────────────────

EVAL CHECKLIST (RUN EVERY TIME)

□ Type C case improves (case_082)
□ placeOfBirth ≤ 1
□ residence.period present
□ no education leakage
□ Type A unchanged
□ Type B unchanged
□ no new must_not_write

────────────────────────────────────────────

DECISION RULE

If it fails:
→ it is NOT routing
→ it is NOT prompt wording

👉 it is BINDING

────────────────────────────────────────────

MENTAL MODEL

Detection = "what is in the text"  ✔
Binding   = "what field it belongs to"  ❌

Fix the second.

────────────────────────────────────────────
```

---

## Changelog

- 2026-04-23: v1 authored from Chris's paste. Incorporates #95 SECTION-EFFECT Phase 3 matrix results, Type A/B/C typology lock, Core Law statement, 5-layer pipeline with Binding Layer named as primary failure surface, fix → WO mapping through BINDING-01 / SPANTAG / FIELD-CARDINALITY-01 / #144 / #97, system-map diagram and one-page quick reference as appendices.
