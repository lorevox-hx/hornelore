# WO-EX-NARRATIVE-FIELD-01 — narrative-story field extraction

**Author:** Claude (LOOP-01 R5.5, tasks #112–#117)
**Status:** Phases 1–3 landed; Phase 4 eval (r5e) PENDING — numbers to fill below
**Touches:** `server/code/api/routers/extract.py`, `scripts/run_question_bank_extraction_eval.py`
**Spec:** `WO-EX-NARRATIVE-FIELD-01_Spec.md` (repo root)

## Background

Biographical narrative fields (`parents.notableLifeEvents`, `grandparents.memorableStories`, `siblings.memories`, `spouse.narrative`, etc.) were systematically under-extracted by the single-pass extractor. Canon-grounded eval `cg01` (2026-04-20) surfaced two clean signal cases:

- `cg_006`: narrative about mother's musical career routed to `parents.occupation` + scalar `parents.notes` instead of `parents.notableLifeEvents` (score 0.50)
- `cg_007`: grandmother's backstory dropped entirely — only identity scalars (name/maidenName) emitted (score 0.50)

The extractor was catching identity scalars cleanly but could not route prose to narrative slots.

## Hypothesis (from spec)

Two interlocking causes:

1. **Few-shot gap** — `extract.py` few-shot catalog has strong coverage on structural fields and pets, but little coverage on `.notableLifeEvents` / `.memorableStories` as target paths.
2. **Section/target gradient** — under SECTION-EFFECT Phase 2 (`current_target_path`), the section context pushes toward identity-shaped schema, so narrative content gets lost.

## Phase 1 — diagnostic attribution (task #113, completed)

Targeted `cg01` slice + verbose `[extract]` logging confirmed few-shot gap is the dominant cause. LLM raw output on `cg_006` contained narrative tokens but the extractor bound them to the closest familiar scalar slot (`.occupation`) rather than the narrative catchment path. No guard-drop evidence. Attribution: few-shot gap > target-gradient.

## Phase 2 — few-shot additions (task #114, landed)

Introduced `_NARRATIVE_FIELD_FEWSHOTS` block in `extract.py` (L1537–1584), gated behind `HORNELORE_NARRATIVE=1` for legacy byte-stability. Appended to system prompt in both legacy and shrunk-prompt paths.

**First tighten (2026-04-21, commits `3fec639` + `9706a87`):**

Added anti-consolidation rules after the initial narrative catchment fewshots, addressing a Phase 2 regression where narrative fewshots pulled narrator scalars (`personal.dateOfBirth`, `personal.placeOfBirth`) into parent-prose buckets on case_049.

Two new rule blocks:

1. **SCALAR CO-EMISSION RULE** (L1564) — "narrative catchment NEVER replaces scalar extraction." When answer contains both a scalar fact and surrounding prose, emit scalar first, then optionally narrative. Never consolidate scalars into prose bucket.

2. **NARRATOR-IDENTITY PRIORITY RULE** (L1579) — `personal.dateOfBirth` / `personal.placeOfBirth` / `personal.fullName` emit FIRST in output array. Never suppressed by parent context or occupation prose. Critically, the rule forces coupling: *"If you emit one narrator-identity scalar, you MUST also emit any other narrator-identity scalar present in the same sentence — this coupling holds EVEN WHEN the interview target is only one of them."*

### Phase 2 smoke signal

| Case | Behavior | Score |
|---|---|---|
| `case_010` | Narrative path correctly hit | pass |
| `case_012` | Narrator scalars emit before parent context | pass |
| `case_049` | Target=`personal.placeOfBirth`, narrator DOB co-emits | **1.000** |

## Phase 3 — scorer alias relax + date-range prompt rule (task #115, landed)

Phase 1 diagnostic also surfaced case_040-class failures: `community.role='OT'` being dropped by CLAIMS-02 validator as <3-char, and `community.yearsActive='twenty-nine years'` losing the range endpoints. Two disjoint fixes landed.

### Fix A — scorer-side role-abbreviation alias (commit `77e5b52`)

In `scripts/run_question_bank_extraction_eval.py` (L149–168, wired into `score_field_match` at L181):

```python
_ROLE_ALIASES = {
    "ot":  "occupational therapist",
    "pt":  "physical therapist",
    "rn":  "registered nurse",
    "lpn": "licensed practical nurse",
    "np":  "nurse practitioner",
    "slp": "speech language pathologist",
}

def _role_alias_match(e: str, a: str) -> bool:
    if _ROLE_ALIASES.get(e) == a:
        return True
    if _ROLE_ALIASES.get(a) == e:
        return True
    return False
```

Inserted AFTER exact-match, BEFORE date-normalization in `score_field_match`. Bidirectional. Scope narrowed to six healthcare/therapy initialisms where collision with common English words is zero. Widens only when a corpus case surfaces need.

**This is the only measurement-side change in the r5e bundle.** Every r5e flip touching a `.role` field must be audited to attribute whether extraction changed or scorer credited a value it wouldn't have before.

### Fix B — CLAIMS-02 role-exempt (commit `291cbb8`)

In `extract.py` (L4547), added `"role"` to `_SHORT_VALUE_EXEMPT_SUFFIXES`:

```python
_SHORT_VALUE_EXEMPT_SUFFIXES = frozenset({
    ...
    "rank", "role", "status", "species", "type", ...
})
```

Effect: `community.role='OT'` (2 chars) no longer dropped by the sub-3-char guard in `_apply_claims_value_shape` at L5064. Joins the existing exemption class for short-value fields (rank, status, branch, etc.). Pre-existing bug — r5c and r5d only passed case_040 because the LLM stochastically rolled `'OT (Occupational Therapist)'` (26 chars) instead of bare `'OT'`. 3-run smoke probe (`smoke_r5e2_case040_run{1,2,3}.json`) confirmed pre-fix deterministic failure.

### Fix C — DATE-RANGE PREFERENCE RULE (commit `74f7b0d`)

Appended to `_NARRATIVE_FIELD_FEWSHOTS` in `extract.py` (L1586–1595):

> DATE-RANGE PREFERENCE RULE: for `*.yearsActive`, `*.dateRange`, `*.servicePeriod` and similar date-span fields, when the answer contains BOTH an explicit range (`"from 1985 to 2010"`, `"1997-2026"`) AND a duration phrase (`"twenty-five years"`, `"almost three decades"`), emit the explicit range form using a dash (`"1985-2010"`). The range carries both endpoints; the duration phrase loses one endpoint and is redundant. Expand common professional-role abbreviations (OT → Occupational therapist, RN → Registered nurse, PT → Physical therapist, NP → Nurse practitioner) where the surrounding context makes the expansion clear.

Instruction-level rule with one concrete exemplar (Mercy Hospital RN → `yearsActive='1985-2010'`, `role='Registered nurse'`). Complements Fix A — Fix C tries to get the extraction right at emission time; Fix A catches the legacy `'OT'` form when extraction still emits unexpanded.

## Phase 4 — eval + decision gate (task #116, IN PROGRESS)

Master r5e rerun pending. Baseline context:

| Tag | Topline | v2 contract |
|---|---|---|
| r4i (locked) | 55/104 | 30/62 |
| r5a | 57/104 | 31/62 |
| r5c | 58/104 | 30/62 |
| r5d | 58/104 | 30/62 |
| **r5e target** | **TBD** | **TBD** |

### r5e prediction (pre-landing)

| Metric | r5d | r5e prediction | Rationale |
|---|---|---|---|
| Topline pass | 58/104 | **59–62/104** | +1 case_049 (Phase 2 tighten), +0–2 from case_040-class (Fix A + Fix B + Fix C), +0–1 cg-case gains |
| v2 contract | 30/62 | **31–33/62** | case_049 is contract; case_040 is contract |
| must_not_write | 0/104 | 0/104 | no guard logic touched |
| case_040 role field | fail | **pass** | Fix B unblocks extraction; Fix A credits if unexpanded |
| case_040 yearsActive | fail | pass (if Fix C fires) / fail (if LLM still emits duration phrase) | prompt-level rule; not deterministic |
| case_049 | fail 0.50 | **pass 1.00** | proven in smoke |

Floor is r5d (58/30). Any topline below 58 means a tighten over-fired and the composite needs to be decomposed.

### Decision gate

- **Adopt (flag default-on)** if ≥ +2 topline gains AND 0 regressions AND case_040 OR case_049 green
- **Adopt with caveat** if +1 topline with regressions explained by scorer drift (not extraction)
- **Reject / iterate** if regressions on net-neutral flips or scorer-drift audit shows Fix A is doing all the work

### Results (TO FILL ON EVAL LANDING)

```
Topline:        XX/104 (delta vs r5d: ±YY)
v2 contract:    XX/62  (delta vs r5d: ±YY)
v3 contract:    XX/62
must_not_write: XX violations
method_distribution: llm=XX, rules=XX, error=XX
parse_failure_rate: XX%
truncation_rate: XX%

NEW GREENS (vs r5d): [case_id list]
NEW REDS   (vs r5d): [case_id list]

Scorer-drift audit (per flip):
  - case_NNN .role field: attribution = extraction_change | scorer_credit
  - case_NNN .yearsActive: attribution = prompt_rule_fired | unchanged
  - ...

Decision: ADOPT | ADOPT-WITH-CAVEAT | ITERATE | REJECT
```

## Risk register

- **Medium risk**: NARRATOR-IDENTITY PRIORITY RULE is strongly worded ("MUST", "NEVER"). Could over-fire if a case targets only one narrator scalar and has no others present — should be no-op but watch for over-emission regressions on single-target narrator cases.
- **Low risk**: Fix A scope is bounded (6 initialisms, zero English collision). Widening requires new corpus evidence.
- **Low risk**: Fix B (role-exempt) joins an established exemption list. No new failure modes unless garbage connector words ever ended up targeted to `.role` — `_VALUE_GARBAGE_WORDS` filter still runs upstream.
- **Low risk**: Fix C is prompt-level; LLM may or may not follow on any given sample. Worst case it's a no-op.
- **Methodology risk**: 5 stacked commits for one measurement (r5e). Fix A is scorer-side, so flips touching `.role` need per-case attribution (documented in the audit block above). If we see >3 unexplained flips, propose split-eval (revert Fix A locally, rerun for clean extraction signal; restore, rerun for alias delta).

## Rollback

- Phase 2 tighten: commits `3fec639` + `9706a87` — revert cleanly; `_NARRATIVE_FIELD_FEWSHOTS` returns to pre-tighten state, `HORNELORE_NARRATIVE` flag remains off-by-default.
- Role-exempt: commit `291cbb8` — revert by removing `"role"` from the frozenset.
- Fix A: commit `77e5b52` — revert removes `_ROLE_ALIASES` dict + `_role_alias_match` func + the call site. Scorer falls back to exact-match only.
- Fix C: commit `74f7b0d` — revert drops the DATE-RANGE PREFERENCE block; rest of `_NARRATIVE_FIELD_FEWSHOTS` unaffected.

All four rollbacks are independent — no cross-dependencies.

## Closeout checklist

- [x] Phase 1 diagnostic (task #113)
- [x] Phase 2 narrative fewshots (task #114)
- [x] Phase 2 tighten: SCALAR CO-EMISSION + NARRATOR-IDENTITY PRIORITY (2026-04-21)
- [x] Phase 3 Fix A scorer alias
- [x] Phase 3 Fix B role-exempt (originally scoped as Phase 4 incidental; promoted after case_040 three-run probe)
- [x] Phase 3 Fix C date-range + role-abbrev prompt rule
- [x] WO report written (this file)
- [ ] Live r5e eval lands
- [ ] Scorer-drift audit completed per flip
- [ ] Decision gate called (ADOPT / ADOPT-WITH-CAVEAT / ITERATE / REJECT)
- [ ] CLAUDE.md current-phase block updated
- [ ] Tasks #115, #116, #117 status → completed
