# Hornelore Master Work Order Checklist

**Updated: 2026-04-18**

## Shipped and Proven

| # | Work Order | What | Status | Eval Proof |
|---|---|---|---|---|
| 1 | WO-EX-01C | Narrator-identity subject guard + birth-context filter | Live-proven | Closed west-Fargo and Cole's-DOB bugs |
| 2 | WO-EX-01D | Field-value sanity blacklists | Live-proven | Closed Stanley/ND and and/dad bugs |
| 3 | WO-LIFE-SPINE-05 | Phase-aware question composer | Shipped | Flag OFF, content ready |
| 4 | WO-EX-VALIDATE-01 | Age-math plausibility validator | Shipped | Flag OFF |
| 5 | WO-EX-SCHEMA-01 | family.* + residence.* fields + repeatable entities | Live-proven | Unblocked CLAIMS-01 |
| 6 | WO-EX-SCHEMA-02 | 35 new fields (7 families), ~50 aliases, 7 prompt examples | Live-proven | 104-case eval |
| 7 | WO-EX-CLAIMS-01 | Dynamic token cap, position-aware grouping, 20 aliases | Live-proven | 22/30 (73.3%) |
| 8 | WO-EX-CLAIMS-02 | Quick-win validators + refusal guard + community denial | Live-proven | 114 unit tests, flag ON |
| 9 | WO-EX-REROUTE-01 | Semantic rerouter: 4 high-precision paths | Live-proven | 104-case eval |
| 10 | WO-GREETING-01 | Backend endpoint + frontend. Memory echo triggers. | Live-tested | All 3 narrators 2026-04-16 |
| 11 | WO-QB-MASTER-EVAL-01 | 62 → 104 cases, v2/v3 scoring, filters, atomic writer | Live-tested | Baseline: 56/104 |
| 12 | WO-EX-GUARD-REFUSAL-01 | Topic-refusal guard + community denial patterns | Live-tested | 0 must_not_write on full suite. Fixes 094/096/097/100 |
| 13 | WO-QB-GENERATIONAL-01 (content) | 4 decade packs, present_life_realities, 5 new fields, 14 eval cases | Live-tested | Baseline: 5/14 (est. 7/14 after case fix) |
| 14 | WO-QB-GENERATIONAL-01B (Part 1+3) | 6 extraction prompt examples, 2 rerouter rules, scorer collision fix | Live-tested | Moved generational from 2/14 → 5/14 |
| 15 | WO-KAWA-UI-01A | River View UI | Implementation complete | Needs live test |
| 16 | WO-KAWA-02A | 3 interview modes, 3 memoir modes, plain-language toggle | Implementation complete | Needs live test |

## Regressed / Shelved

| # | Work Order | What | Status | Notes |
|---|---|---|---|---|
| 17 | WO-EX-TWOPASS-01 | Two-pass extraction: span tagger + classifier | **Flag OFF** | Regressed 16/62 vs 32/62 baseline. Token starvation + context loss. Flag accidentally left ON in .env during 04-17 eval. |
| 18 | WO-EX-FIELDPATH-NORMALIZE-01A | Confusion-table-driven field-path normalization | **Reverted** | Regressed from 32/62 to 14/62. Answer vs value text mismatch. |

## In-Flight / Ready to Implement

| # | Work Order | What | Status | Next Action |
|---|---|---|---|---|
| 19 | WO-QB-GENERATIONAL-01B (Part 2) | Runtime composer wiring — interleave overlays at 1:4 ratio | Specced | Code `_pick_generational_question()` in phase_aware_composer.py |
| 20 | WO-INTENT-01 | Narrator topic pivots ignored by composer | **Not specced** | #1 felt bug from live sessions. Spec it next. |
| 21 | WO-EX-DENSE-01 | Dense-truth / large chunk / good-garbage extraction | **Not specced** | #1 extraction frontier: 1/8 dense, 0/4 large, 5/14 good-garbage |
| 22 | WO-KAWA-01 | Parallel Kawa river layer — LLM into kawa_projection.py | Fully specced | 10 phases. Next: wire LLM. |
| 23 | WO-KAWA-02 (remaining) | Phases 4-9: storage promotion, chapter weighting, deeper memoir | Phases 4-9 not implemented | Depends on KAWA-01 |
| 24 | WO-PHENO-01 | Phenomenology layer: lived experience + wisdom extraction | Fully specced | 3-4 sessions to implement |

## Not Yet Specced (Backlog)

| # | Work Order | What | Priority |
|---|---|---|---|
| 25 | WO-REPETITION-01 | Narrator repeats same content 2-3x, Lori keeps responding | Medium |
| 26 | WO-MODE-01/02 | Session Intent Profiles after narrator Open | Low |
| 27 | WO-UI-SHADOWREVIEW-01 | Show Phase G suppression reason instead of silent drop | Low |
| 28 | WO-EX-DIAG-01 | Surface extraction failure reason in response envelope | Low |

## Priority Sequence (as of 2026-04-18)

```
EX-GUARD-REFUSAL-01 (done)
  → QB-GENERATIONAL-01 content (done)
    → QB-GENERATIONAL-01B Part 1+3 (done)
      → INTENT-01 (next — #1 felt bug)
        → EX-DENSE-01 (extraction frontier)
          → QB-GENERATIONAL-01B Part 2 (runtime wiring)
            → KAWA-01 Phase 1
```

## Extraction Eval Baselines (2026-04-18)

| Suite | Cases | Score | Safety |
|---|---|---|---|
| Master suite | 104 | 56/104 (53.8%) | 1 must_not_write (case_094 cross-family) |
| Contract subset (v3) | 62 | 35/62 (56.5%) | — |
| Contract subset (v2) | 62 | 32/62 (51.6%) | — |
| Generational pack | 14 | 5/14 (35.7%) | 0 must_not_write |
| null_clarify | 7+2 | 9/9 (100%) | Refusal guard healthy |

## Extraction Pipeline Order (active)

```
LLM generate
  → JSON parse
    → semantic rerouter (4 rules + touchstone dup + story-priority)
      → birth-context filter
        → month-name sanity
          → field-value sanity
            → claims validators:
                refusal guard → shape → relation → confidence → negation guard
```

## Env Flags

| Flag | Default | Purpose |
|---|---|---|
| HORNELORE_TRUTH_V2 | 1 | Facts write freeze |
| HORNELORE_TRUTH_V2_PROFILE | 1 | Profile reads from promoted truth |
| HORNELORE_PHASE_AWARE_QUESTIONS | 0 | Phase-aware question composer |
| HORNELORE_AGE_VALIDATOR | 0 | Age-math plausibility filter |
| HORNELORE_CLAIMS_VALIDATORS | 1 | Value-shape, relation, confidence validators |
| HORNELORE_TWOPASS_EXTRACT | 0 | Two-pass extraction (REGRESSED — keep OFF) |
