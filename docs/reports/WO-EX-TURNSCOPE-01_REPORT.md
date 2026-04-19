# WO-EX-TURNSCOPE-01 — Implementation Report

**Task #72.** Follow-up turn-scope filter / entity-role binding enforcement.
Generated 2026-04-19. Status: code landed, syntax-checked, unit-tested, pending confirmation master-eval.

## Summary

Added `_apply_turn_scope_filter` to `server/code/api/routers/extract.py` and wired it into the `extract_fields` endpoint on both the LLM and rules-fallback paths. The filter enforces entity-role binding on follow-up turns: when `current_target_path` resolves to a family-relations branch root (siblings / parents / grandparents / greatGrandparents / family.children / family.spouse), it drops any extracted item whose fieldPath lives in a *different* branch of that cluster. Items outside the cluster (personal.*, residence.*, earlyMemories.*, pets.*, education.*, community.*, military.*, travel.*, health.*, laterYears.*, family.marriage*) pass through unchanged.

Root cause addressed: `master_loop01_r4f.json` `case_094` (janice-josephine-horne, sibling_detail) wrote 4 `parents.*` fields from the narratorReply "Ervin and Leila Horne's anniversary" — the model bound relational names that appeared as *references* inside the reply to the adjacent `parents.*` schema branch. That produced the lone `must_not_write` violation in the R4f eval (and was the only member of the `guard_false_positive` failure category, which is mislabeled — the root cause is turn-scope, not negation-guard misfire).

## Files Changed

| File | Change | Lines |
|---|---|---|
| `server/code/api/routers/extract.py` | Added `_FAMILY_RELATIONS_ROOTS`, `_resolve_turn_scope_branch`, `_fieldpath_branch_root`, `_apply_turn_scope_filter` | 2836–2935 (new 100 lines) |
| `server/code/api/routers/extract.py` | Wired filter into LLM path in `extract_fields()` — after `_apply_semantic_rerouter`, before `_apply_birth_context_filter` | 4342–4352 |
| `server/code/api/routers/extract.py` | Wired filter into rules-fallback path in `extract_fields()` — before `_apply_birth_context_filter` | 4470–4475 |
| `scripts/run_question_bank_extraction_eval.py` | **No change needed.** Line 437 already passes `extractPriority[0]` as `current_target_path`. |
| `data/qa/question_bank_extraction_cases.json` | No change. |

## Design

### The cluster

```python
_FAMILY_RELATIONS_ROOTS = (
    "family.children",    # ordered longest-first for prefix match
    "family.spouse",
    "greatGrandparents",
    "grandparents",
    "siblings",
    "parents",
)
```

`family.marriage*` is deliberately **not** in the cluster — marriage notes are narrative metadata, not a family-relations entity branch, and `family.marriageNotes` is a legitimate may_extract for spouse_detail (case_093). Keeping it out of the cluster preserves that flow.

### The resolution functions

`_resolve_turn_scope_branch(current_target_path)` and `_fieldpath_branch_root(field_path)` both do longest-prefix match against the cluster. Examples:

- `siblings.uniqueCharacteristics` → `siblings`
- `family.children.firstName` → `family.children`
- `family.spouse.maidenName` → `family.spouse`
- `family.marriageNotes` → None (outside cluster)
- `personal.placeOfBirth` → None
- `pets.name` → None
- `residence.notes` → None

### The drop rule

For each extracted item, drop iff:
1. `_resolve_turn_scope_branch(current_target_path) != None` (the turn has a cluster target), AND
2. `_fieldpath_branch_root(fieldPath) != None` (the item is in the cluster), AND
3. `item_root != target_root` (different branches within the cluster).

Items outside the cluster always pass through. Items in the same branch as the target always pass through. Only the narrow cross-branch-within-cluster case triggers a drop.

Each drop emits:
```
[extract][turnscope] DROP fieldPath=<path> value=<80 char preview> target_branch=<root> item_branch=<root> reason=cross_branch_bleed
```

### Placement in the guard stack

**LLM path (around line 4352):**

```
_extract_via_llm
  ↓
_apply_semantic_rerouter        # fix valid-but-wrong paths first
  ↓
_apply_turn_scope_filter        # ← NEW: enforce cluster boundary
  ↓
_apply_birth_context_filter
  ↓
_apply_month_name_sanity
  ↓
_apply_field_value_sanity
  ↓
_apply_claims_validators
    (inner: _apply_refusal_guard → _apply_claims_value_shape →
     _apply_value_length_cap → _apply_claims_relation_allowlist →
     _apply_relation_scope_guard → _apply_write_time_normalisation →
     _apply_claims_confidence_floor → _apply_negation_guard)
```

**Rules-fallback path (around line 4475):** same placement, before `_apply_birth_context_filter`.

Rationale for ordering: the rerouter must run first so valid-but-wrong paths get a chance to be rebound to correct branches before the cluster boundary is enforced. The turn-scope filter must run before the birth-context filter and the full claims validator stack so downstream guards operate on a turn-scope-clean item list.

### Fallback behavior

Filter is a **no-op** when:
- `items` is empty
- `current_target_path` is None
- `current_target_path` is an empty string
- `current_target_path` resolves outside the cluster (e.g. `pets.notes`, `residence.notes`, `personal.placeOfBirth`, `family.marriagePlace`)

This keeps the filter silent on non-follow-up turns and on follow-ups targeting non-cluster fields. No production traffic should see unexpected drops.

## Follow-Up Case Impact Map (from `master_loop01_r4f.json`)

| case_id | subTopic | extractPriority[0] | resolves to | filter state |
|---|---|---|---|---|
| case_088 | childhood_pets | pets.notes | — | no-op |
| case_089 | birthplace_detail | residence.notes | — | no-op |
| case_090 | father_detail | parents.notableLifeEvents | `parents` | **active** |
| case_091 | marriage_detail | family.marriagePlace | — | no-op |
| case_092 | child_detail | family.children.firstName | `family.children` | **active** |
| case_093 | spouse_detail | family.spouse.firstName | `family.spouse` | **active** |
| **case_094** | **sibling_detail** | **siblings.firstName** | **`siblings`** | **target case** |
| case_095 | birthplace_clarify | personal.placeOfBirth | — | no-op |

Filter is active on 4 of the 8 follow-up cases. The other 4 are safely outside the cluster.

## Unit Test Results

Ran 9 table-driven tests + 3 edge cases against the filter function in isolation (no router boot):

```
case        target                                expect    result
----------------------------------------------------------------------
case_088    pets.notes                            drop=0    drop=0 OK    pets outside cluster → no-op
case_089    residence.notes                       drop=0    drop=0 OK    residence outside cluster → no-op
case_090    parents.notableLifeEvents             drop=0    drop=0 OK    parents + earlyMemories both OK
case_090b   parents.notableLifeEvents             drop=1    drop=1 OK    drop sibling bleed
case_091    family.marriagePlace                  drop=0    drop=0 OK    target outside cluster → no-op
case_092    family.children.firstName             drop=1    drop=1 OK    drop parents, keep residence
case_093    family.spouse.firstName               drop=1    drop=1 OK    drop parents.occupation
case_094    siblings.firstName                    drop=4    drop=4 OK    TARGET: drop all 4 parents.* writes
case_095    personal.placeOfBirth                 drop=0    drop=0 OK    target outside cluster → no-op

Edge cases (None target, empty items, "" target): OK
```

Syntax check: `python3 -m py_compile server/code/api/routers/extract.py` → OK.

## Expected Behavior on `case_094` (confirmation eval)

Given the `master_loop01_r4f.json` raw_items for case_094:

```
siblings.firstName     = "James Peter"      → should_ignore (would leak; filter does not block should_ignore, this is eval-zone concept)
siblings.birthOrder    = "youngest"         → should_ignore (same)
siblings.birthDate     = "June 29th"        → extraneous (same branch; passes filter)
parents.firstName      = "Ervin"            → must_not_write + cross-branch → DROPPED by filter ✓
parents.middleName     = "Leila"            → cross-branch → DROPPED ✓
parents.lastName       = "Horne"            → cross-branch → DROPPED ✓
parents.birthPlace     = "Richardton Hospital" → cross-branch → DROPPED ✓
```

**Note:** The filter does not address the `should_ignore` leakage on `siblings.firstName` / `siblings.birthOrder` — those are within the target branch and correctly pass through. Resolving those requires a separate state-aware post-extraction reconciler (out of scope for this WO; scored as noise_leakage, not must_not_write). Score on case_094 will likely jump from 0.60 into the 0.80–0.90 range — the must_not_write violation clears and the 3 parents.* scope-escapes stop, but the siblings.* noise_leakage remains until state-anchored dedup ships.

## Acceptance Gates

| Gate | Expected Outcome |
|---|---|
| case_094 must_not_write violations | 1 → 0 |
| case_094 score | 0.60 → ≥ 0.80 |
| `guard_false_positive` failure category | 1 → 0 |
| `must_not_write violations` total | 0.6% → 0.0% |
| v3 contract subset | ≥ 34/62 (no regression) |
| Master pass count | ≥ 54/104 (no regression) |
| follow_up bucket pass rate | ≥ 6/8 (unchanged) |
| `[extract][turnscope] DROP` log lines | 4 entries for case_094 on the `parents.*` writes |

## Confirmation Eval Command

Chris to run on the WSL box after restarting the API:

```bash
cd ~/hornelore
# restart API so the module reloads
./scripts/stop_all.sh
./scripts/start_all.sh
# wait for the API to come up (watch the health check)
./scripts/run_question_bank_extraction_eval.py --mode live \
  --api http://localhost:8000 \
  --output docs/reports/master_loop01_r4g.json \
  2>&1 | tee docs/reports/master_loop01_r4g.console.txt

# quick grep for the filter firing
grep "\\[extract\\]\\[turnscope\\]" .runtime/logs/api.log | head -20
```

Read these metrics from the console output:

1. Total pass count (target ≥ 54/104).
2. `must_not_write violations:` line (target 0.0%).
3. `guard_false_positive` under "Failure categories:" (target 0).
4. `case_094` line under "FAILED CASES" — should be absent, or present with a higher score and no `guard_false_positive` tag.
5. `follow_up` under "By case type" (target ≥ 6/8, avg ≥ 0.787).

## Regression Risk Assessment

**Low-risk changes:**

- Outer-level placement means no signature changes to existing validators.
- No-op on all turns where `current_target_path` is None or outside the cluster — the vast majority of production turns.
- Drops are logged with a uniform tag for grep-ability.
- No changes to negation-guard (preserves the 4→1 win on guard_false_positive from Patch F narrowing).
- No changes to the semantic rerouter, alias table, or field-value sanity filters.

**Known trade-offs:**

- The filter is scoped to the family-relations cluster. If a production follow-up turn about one's father legitimately mentions grandparents' details (e.g. "my dad told me his father was a farmer"), those grandparents.* writes would be dropped. This is acceptable in R4 because the eval doesn't exercise that pattern and capturing adjacent-generation details during a single-parent follow-up is a v2 concern. R5.5 citation grounding will handle this more cleanly via span-level anchoring.
- `family.marriage*` is intentionally outside the cluster. A spouse_detail turn that writes `family.marriageNotes` is not blocked. This is the currently-passing case_093 shape.
- The filter does NOT address the `siblings.firstName` / `siblings.birthOrder` leakage on case_094 (those are within the target branch and would incorrectly pass through with a naive rule that also blocks same-branch writes). Those are state-already-present leaks and require a separate state-aware reconciler (out of scope).

**Regression scenarios to watch in the confirmation eval:**

- case_090 (father_detail, target=parents): any earlyMemories.* or personal.* extractions should still pass (outside cluster).
- case_092 (child_detail, target=family.children): residence.place / health.majorCondition should still pass (outside cluster; must_not_write for the case eval, but not filter's concern).
- case_093 (spouse_detail, target=family.spouse): family.marriageNotes should still pass (outside cluster).

## Note for Task #63 (eval-harness audit)

When this WO ships, `guard_false_positive` drops to 0 because case_094 was its only member and the root cause was turn-scope rather than guard misfire. The failure categorizer in the eval scorer currently uses the `guard_false_positive` label too broadly — it tags any `must_not_write` violation that *could* have been caught by a guard-like mechanism as `guard_false_positive`. Recommendation for #63: retag rule should require evidence that a guard log line (`[negation-guard]`, `[refusal-guard]`) actually fired for the case. Scope-escape failures should get their own category, e.g. `scope_escape` or `entity_role_bleed`. This will make future failure triage cleaner.

## Next Steps

1. Chris restarts API and runs the confirmation master-eval (command above).
2. Confirm gates pass. If any regression, revert the rules-path wiring first (line 4475), re-run to isolate; otherwise revert the LLM-path wiring (line 4352).
3. On clean confirmation, proceed to:
   - **#67** — D/H ordering reconciliation (case_011).
   - **#68** — wrong-entity investigation (case_053).
   - Prompt/schema catalog shrink (recover VRAM headroom; peels confound from dense_truth/large chunk cliffs).
   - Freeze post-R4 baseline + short readout memo.
4. Only then pivot to **R5.5 citation grounding** against the clean baseline.

## Files

- Spec: `WO-EX-TURNSCOPE-01_Spec.md` (repo root)
- Code: `server/code/api/routers/extract.py` (lines 2836–2935, 4342–4352, 4470–4475)
- This report: `docs/reports/WO-EX-TURNSCOPE-01_REPORT.md`
