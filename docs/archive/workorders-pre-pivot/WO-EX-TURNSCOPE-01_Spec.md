# WO-EX-TURNSCOPE-01 — Follow-Up Turn-Scope Filter (Entity-Role Binding)

**Task #72.** Last open correctness fix before R4 closure. Targets the lone `must_not_write` violation surfaced by `master_loop01_r4f` (`case_094`, janice-josephine-horne, `sibling_detail`).

## Goal

On a `follow_up` turn whose intent is scoped to one entity-role branch (e.g. `siblings.*`), prevent the extractor from writing to **sibling entity-role branches** (`parents.*`, `family.children.*`, `family.spouse.*`, `grandparents.*`, `greatGrandparents.*`) just because their names or dates happened to appear as a reference inside the answer.

This is the runtime enforcement of **entity-role binding** — the follow-up's target branch is the only family-relations branch the turn can write to.

## Root Cause (case_094, grounded)

`priorContext`: "Narrator previously mentioned siblings Verene Marie (older sister) and James Peter (younger brother)."

`loriPrompt`: "Tell me more about your brother James."

`narratorReply`: "James Peter Zarr — he was the youngest. He was born on June 29th, which is the same day as Kent's **parents' wedding anniversary. Ervin and Leila Horne's anniversary.** And get this — James was born in a car on the way to Richardton Hospital! Mom and Dad didn't make it in time."

**What the extractor wrote (all conf 0.9 except birthPlace 0.8):**

| fieldPath | value | zone | verdict |
|---|---|---|---|
| siblings.firstName | James Peter | should_ignore | leaked |
| siblings.birthOrder | youngest | should_ignore | leaked |
| siblings.birthDate | June 29th | (extraneous) | leaked |
| **parents.firstName** | **Ervin** | **must_not_write** | **violated** |
| parents.middleName | Leila | (extraneous) | scope escape |
| parents.lastName | Horne | (extraneous) | scope escape |
| parents.birthPlace | Richardton Hospital | (extraneous) | scope escape + hallucinated (Richardton was *James'* birth, not a parent's) |

And **missed** `siblings.uniqueCharacteristics` = "born in a car on the way to Richardton Hospital" (the only zone-legal field).

The model saw the names "Ervin and Leila Horne" in the text and bound them to the `parents.*` schema branch, ignoring the semantic anchor ("Kent's parents' wedding anniversary" — Kent's parents, not Janice's). This is classic **entity-role binding** under a parallel-branch prompt: when multiple family-relations branches exist in the schema, surface-level name mentions bleed across branches.

Research tie-in: mention-order echo — a cousin of the Order-to-Space Bias (OINL, §2.7 of `loop01_research_synthesis.md`). Same failure family as the upstream field-scope filter sketched as R6 candidate.

## Non-Goals

- Not touching the negation-guard (Patch F narrowing just landed 4→1 on `guard_false_positive`; don't re-open).
- Not a general schema-scope filter (that's the R6 candidate). This WO is bounded to **follow-up turns within the family-relations cluster**.
- Not a prompt rewrite. Pure post-extraction runtime filter.
- No new LLM calls. No new eval cases.

## Stop Conditions

- If the filter fires on any `currentExtractorExpected=true` case that currently passes → revert that rule, tighten the precondition.
- If case_094 still fails after the filter → the fix surface is wrong; reopen for design.
- If `must_not_write` violation count goes above 1 on the confirmation eval → regression, revert.

---

## Design

### Scope preconditions (all must hold to fire)

1. `caseType == follow_up` — OR at runtime: `current_target_path` is set and resolves to one of the family-relations branch roots below.
2. The follow-up's resolved target branch root is one of:
   - `siblings.*`
   - `parents.*`
   - `family.children.*`
   - `family.spouse.*`
   - `grandparents.*`
   - `greatGrandparents.*`

If both hold, the filter defines an **allowed-branch** set = {target branch root} ∪ optional adjacent zones (see Layer A.2 below).

### Layer A — The Filter

**A.1. Drop-rule:**

For each extracted item, if `fieldPath` falls under a **family-relations branch root that is NOT the target branch root**, drop the item with log:

```
[extract][turnscope] DROP fieldPath=%s value=%r target_branch=%s reason=cross_branch_bleed
```

Non-family-relations branches (`personal.*`, `residence.*`, `education.*`, `health.*`, `community.*`, `military.*`, `travel.*`, `laterYears.*`, `earlyMemories.*`, `pets.*`, `family.marriage*`) are **unaffected** — the filter is tight to the entity-role cluster where case_094 lives.

**A.2. Adjacency whitelist (optional, conservative):**

Looking at passing follow-up cases in `master_loop01_r4f.json`:

- `case_090` (father_detail): target `parents.*`, also allows `earlyMemories.significantEvent` (may_extract).
- `case_089` (birthplace_detail): target `personal.placeOfBirth`, also allows `pets.*`, `earlyMemories.*`.
- `case_093` (spouse_detail): target `family.spouse.*`, also allows `family.marriageNotes`.

The filter only restricts **within the family-relations branch cluster**, so these cross-cluster may_extracts are naturally preserved. No adjacency whitelist needed in v1.

**A.3. Ordering:**

Runs **before** `_apply_negation_guard` and **after** `_apply_semantic_rerouter`, in the LLM-output guard stack in `extract_fields()`. Rationale: give the rerouter a chance to fix valid-but-wrong paths first, then enforce turn scope.

### Layer B — The Signal

**B.1. Runtime signal source.**

The filter reads `req.current_target_path` from `ExtractFieldsRequest` (already on the request model, line 41 of `extract.py`). When `current_target_path` is populated with a field path like `siblings.uniqueCharacteristics`, the filter resolves its **branch root** by first-segment match:

```python
_FAMILY_RELATIONS_ROOTS = {
    "siblings", "parents",
    "grandparents", "greatGrandparents",
    "family.children", "family.spouse",
}

def _resolve_target_branch_root(current_target_path: Optional[str]) -> Optional[str]:
    if not current_target_path:
        return None
    # Match longest prefix — "family.children" before "family"
    for root in sorted(_FAMILY_RELATIONS_ROOTS, key=len, reverse=True):
        if current_target_path == root or current_target_path.startswith(root + "."):
            return root
    return None
```

**B.2. What counts as a "family-relations bleed":**

```python
def _is_family_relations_path(field_path: str) -> bool:
    for root in _FAMILY_RELATIONS_ROOTS:
        if field_path == root or field_path.startswith(root + "."):
            return True
    return False
```

An item is dropped iff: `_is_family_relations_path(item['fieldPath'])` AND `_resolve_target_branch_root(item['fieldPath']) != target_root`.

**B.3. Fallback behavior when `current_target_path` is unset.**

No-op. Filter is silent. This is conservative — we only restrict when we have a clear turn-scope signal.

---

## Exact File Scope

| File | Change |
|---|---|
| `server/code/api/routers/extract.py` | Add `_apply_turn_scope_filter(items, current_target_path)` near line ~2785 (next to `_apply_relation_scope_guard`). Call it in `extract_fields()` after `_apply_semantic_rerouter` (line 4240) and before `_apply_birth_context_filter`. |
| `scripts/run_question_bank_extraction_eval.py` | Ensure the harness passes `current_target_path` for follow-up cases. Verify by: case_094 log shows `target=siblings.*` on entry. |
| `data/qa/question_bank_extraction_cases.json` | No changes. |
| `docs/reports/WO-EX-TURNSCOPE-01_REPORT.md` | New file. Report after confirmation eval. |

## Acceptance Gates

| Gate | Criterion |
|------|-----------|
| **case_094 passes** | Score ≥ 0.80. At minimum, `parents.*` writes dropped and `must_not_write violations = 0`. |
| **No follow-up regressions** | The other 7 follow-up cases (088–095 minus 094) all maintain their current pass/fail state. |
| **No global regressions** | Master eval pass rate ≥ 54/104. v3 contract subset ≥ 34/62. |
| **guard_false_positive = 0** | The filter fires cleanly and absorbs the lone remaining `guard_false_positive` bucket member (which was scope-escape mislabeled — see Note below). |
| **Log visibility** | `[extract][turnscope]` DROP lines present on case_094 for all 4 `parents.*` writes. |
| **Wobble** | Two consecutive master-eval runs agree on case_094 pass/fail. |

## Note on Failure Taxonomy

Once this ships, the `guard_false_positive` category in the eval scorer will be at 0 (case_094 was its only member, and the root cause is turn-scope, not guard misfire). Fold this observation into **task #63** (eval-harness audit): the failure categorizer's `guard_false_positive` rule is currently over-broad — it's catching scope-escapes that weren't near the negation guard at all. Retag rule should key on "guard log line present in api.log" to be tight.

## Confirmation Eval

```bash
./scripts/run_question_bank_extraction_eval.py --mode live \
  --api http://localhost:8000 \
  --output docs/reports/master_loop01_r4g.json \
  2>&1 | tee docs/reports/master_loop01_r4g.console.txt
```

Then read: pass count, `must_not_write violations`, case_094 line, `guard_false_positive` count, and `follow_up` bucket score.

## Sequence After This WO

```
WO-EX-TURNSCOPE-01 (this, #72)
  → #67 D/H ordering reconciliation (case_011)
  → #68 wrong-entity investigation (case_053)
  → prompt / schema-catalog shrink (recover VRAM headroom — addresses large/dense_truth cliff as a confound, not a cure)
  → freeze post-R4 baseline + short readout memo
  → R5.5 citation grounding (the real attack on dense_truth 0/8 / large 0/4)
```

## Hard Rules

- Filter only fires when `current_target_path` resolves to a family-relations branch root. Otherwise no-op.
- Drops are logged with a uniform tag for grep-ability.
- No changes to the negation guard, the semantic rerouter, or the field-path alias table.
- Two consecutive master evals before this WO is declared done.
