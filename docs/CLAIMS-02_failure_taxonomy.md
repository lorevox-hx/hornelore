# WO-CLAIMS-02 — Extraction Failure Taxonomy

**Generated:** 2026-04-17
**Baseline:** 22/30 (73.3%), avg score 0.723
**Source:** `docs/reports/question_bank_extraction_eval_report.json` (2026-04-16 eval run)

---

## Summary

| Category | Count | Description |
|---|---|---|
| **Known-gap failures** | 5 | Cases marked `currentExtractorExpected: false` that failed as predicted |
| **Unexpected failures** | 3 | Cases marked `currentExtractorExpected: true` that should have passed |
| **Known-gap surprise pass** | 1 | case_005 (compound children) passed despite being marked as gap |

---

## Root Cause Categories (from eval report)

| Root Cause | Cases | Notes |
|---|---|---|
| `llm_hallucination` | 4 | LLM produced wrong values or invented fields |
| `schema_gap` | 4 | No field path exists for the information, or repeatable grouping lost |
| `field_path_mismatch` | 2 | LLM routed value to wrong field path |

Note: Some cases have multiple root causes, so counts sum to 10 across 8 failures.

---

## Failure Detail

### Category A: Compound Entity Grouping (5 cases)

**Root cause:** When narrator mentions multiple entities of the same repeatable type in one reply, the LLM produces items but the eval scorer or the pipeline loses entity coherence.

| Case | Narrator | Content | Key Failure |
|---|---|---|---|
| case_002 | Christopher | 4 family members + birth order | `parents.relation` missing; `personal.birthOrder` = "youngest" not "3" |
| case_013 | Kent | 3 children with partial dates/places | Entity cross-contamination (Vincent's birthplace vs Christopher's) |
| case_014 | Kent | 2 siblings + birth order | Sibling repeatable grouping lost |
| case_024 | Janice | 2 siblings + birth order + lore | Sibling repeatable grouping lost |
| case_030 | Janice | 3 children (mirror of 013) | Entity cross-contamination + forbidden field risk |

**Pattern:** All 5 are `extract_multiple` with repeatable groups. The LLM often gets the names right but loses relational metadata (`relation`, `birthOrder`) or conflates entities.

**Fix path (CLAIMS-02):**
1. Post-extraction entity coherence check — verify each repeatable group has required anchor fields (at minimum `firstName` + `relation`)
2. Split compound replies into per-entity extraction passes if >2 entities detected
3. Add `birthOrder` normalization (map "youngest" → ordinal based on sibling count)

---

### Category B: LLM Hallucination (overlaps with A)

**Root cause:** LLM produces `relation: "then"` or `relation: "and"` by parsing sentence connectors as field values. Also produces `relation: "kids"` as a collective instead of individual roles.

**Evidence from case_005 raw output:**
- `family.children.relation` = `"then"` (confidence 0.7) — from "then Gretchen Jo"
- `family.children.relation` = `"and"` (confidence 0.7) — from "and my youngest"
- `family.children.relation` = `"kids"` (confidence 0.9) — from "I have four kids"

**Fix path (CLAIMS-02):**
1. Add `relation` value allowlist in validation: `["son", "daughter", "child", "mother", "father", "parent", "brother", "sister", "sibling"]`
2. Reject any extracted `relation` value not in allowlist
3. Add confidence floor — items with confidence < 0.5 auto-rejected

---

### Category C: Field Path Mismatch (2 cases)

**Root cause:** LLM routes extracted value to a plausible but incorrect field path.

**Observed patterns:**
- `education.higherEducation` = `"graduated"` when the answer was about high school (case_003, partial score)
- `education.careerProgression` = `"1997"` as a bare year fragment (case_006, partial score)
- `parents.notableLifeEvents` receiving name fragments instead of event text (case_008)

**Fix path (CLAIMS-02):**
1. Value-shape validation: reject bare years, single words, connector words as field values
2. Field-type heuristic: if value looks like a name but field expects an event, flag for review
3. Minimum value length for narrative fields (suggest_only writeMode): reject < 5 characters

---

### Category D: Unexpected Failures (3 cases)

**Cases:** 3 failures from Kent (1) and Janice (2) narrators in cases marked `currentExtractorExpected: true`.

**Likely root causes (inferred from narrator-level scores):**
- Kent avg score 0.673, Janice avg score 0.662 — both significantly below Christopher's 0.835
- Kent and Janice have more complex family narratives (German heritage, multiple relocations, deep genealogy)
- Narrative style: Kent gives terse answers; Janice gives long, digressive answers with asides — both challenge the LLM differently

**Fix path (CLAIMS-02):**
1. Re-run eval after SCHEMA-02 field expansion to see if new alias mappings resolve field routing
2. Add narrator-style prompt tuning (terse vs verbose extraction modes)
3. Analyze the 3 specific unexpected failures once eval report is regenerated with full data

---

## Priority Order for CLAIMS-02 Fixes

1. **Value validation** (quick win): Reject connector words, bare fragments, values < 3 chars
2. **Relation allowlist** (quick win): Enumerated valid values for `.relation` fields
3. **Confidence floor** (quick win): Auto-reject below 0.5
4. **Entity coherence check** (medium): Verify repeatable groups have anchor fields
5. **Compound reply splitting** (hard): Multi-pass extraction for dense multi-entity replies
6. **Narrator style tuning** (hard): Adjust prompt based on answer verbosity

---

## Metrics Targets

| Metric | Current | Target (post-CLAIMS-02) |
|---|---|---|
| Pass rate (original 30) | 22/30 (73.3%) | 26/30 (86.7%) |
| Pass rate (full 44) | — | 36/44 (81.8%) |
| Avg score | 0.723 | ≥ 0.80 |
| Unexpected failures | 3 | 0 |
| Known-gap failures | 5 | ≤ 3 |

---

## Next Steps

1. ✅ SCHEMA-02 field expansion complete (35 fields, 50 aliases, 7 prompt examples, 14 eval cases)
2. Re-run eval with expanded 44-case suite to establish new baseline
3. Implement quick-win validators (value shape, relation allowlist, confidence floor)
4. Re-run eval — expect +2-4 case improvement
5. Implement entity coherence check for repeatables
6. Re-run eval — expect +2-3 more
7. Decision gate: if ≥ 80% pass rate, proceed to INTENT-01; otherwise deeper CLAIMS-02 work
