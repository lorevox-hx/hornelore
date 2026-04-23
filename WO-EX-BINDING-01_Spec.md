# WO-EX-BINDING-01 — Type C schema-binding correction (residence/placeOfBirth, residence.period/education.gradeLevel, sibling leakage)

**Status:** DRAFT v2 (2026-04-23, re-locked after Chris's Boris-style WO + Architecture Spec v1 paste)
**Owner:** extractor lane (Claude)
**Priority:** parallel lane — sequenced after SPANTAG (#90), not coupled to it
**Blocks:** nothing directly
**Blocked by:** SPANTAG (#90) landing + `r5f-spantag` eval banked
**Eval tag:** `r5g-binding`
**Task:** new (created 2026-04-23 as follow-up #2 from SECTION-EFFECT Phase 3 PARK; re-locked 2026-04-23 per Chris's Boris WO)

---

## 0. One-line intent

Fix Type C schema binding without touching extraction routing, era/pass/mode plumbing, schema inventory, or SPANTAG's own implementation. This is a **binding-only** lane.

## 1. Problem statement

#95 SECTION-EFFECT Phase 3 established:

- runtime context (era/pass/mode) is not causal for extraction behavior
- Q2/Q3 effects are stratified by Type A / Type B / Type C, not unresolved
- Type C remains mis-bound even in baseline V1
- `case_082` V1 already emits four `personal.placeOfBirth` values; V6 preserves that and swaps `residence.period` for `education.gradeLevel`

**Core Law (from Architecture Spec v1):** *Extraction is semantics-driven, but errors arise from failures in causal attribution at the binding layer.*

The Binding Layer maps detected semantic spans → schema fields. It owns field selection, domain separation, and cardinality enforcement. `case_082` fails on all three.

**Evidence from the matrix (per-item view, V1 and V6 both):**

| Symptom | V1 (baseline) | V6 (target stripped) | Interpretation |
|---|---|---|---|
| `personal.placeOfBirth` emits 4 items (Spokane, Dodge, Glen Ullin, Strasburg) | ✓ | ✓ | Two violations: (a) domain-bind error — places she *lived* routed to birthplace-scalar slot; (b) cardinality violation — scalar field emits 4 values. Prompt-invariant. |
| `residence.period` with grade-range values ("first and second grade"…) | ✓ (3 items) | ✗ (swapped for `education.gradeLevel`) | Schema-slot drift when target_path absent. Target_path nudges but is not authoritative. |
| `education.schooling` = "Sacred Hearts" (correct) | ✓ | ✓ | No problem. |

Type A (case_008) and Type B (case_018) are not affected — Type A is target-anchored, Type B is self-binding. Type C has neither; this WO targets Type C only.

## 2. Scope (in)

Three conflation pairs plus one enforcement layer.

**Conflation pairs:**

1. **`residence.*` vs `personal.placeOfBirth`** — multi-value movement places must not land on the birthplace scalar unless evidence explicitly anchors birth.
2. **`residence.period` vs `education.gradeLevel`** — grade-range values anchor residence duration when narrator is describing a move; they anchor education only when narrator is describing schooling separately.
3. **`siblings.*` vs narrative/person mentions** — sibling fields only when the text explicitly names a sibling relation or is strongly anchored in local family context.

**Cardinality discipline (minimal, PATCH 4 only):**

4. **`personal.placeOfBirth` is scalar — emit ≤1 per extraction pass.** Protected identity fields (`placeOfBirth`, `dateOfBirth`, `timeOfBirth`, scalar `firstName`/`lastName` per schema) must not receive repeated multi-location narrative values. If >1 `personal.placeOfBirth` survives binding: keep the strongest explicit birth-anchored candidate; if none is explicitly anchored, keep the first and flag the rest for drop; **do not silently re-route extras in this WO**.

Residence-shaped fields (`residence.place`, `residence.period`, `education.schooling`, `siblings.firstName`, etc.) may emit N values — no enforcement.

## 3. Scope (out)

- **No `extract.py` schema inventory changes.**
- **No turnscope / section-routing changes.**
- **No era/pass/mode prompt changes.**
- **SPANTAG implementation itself is not modified.** This WO *rides on* SPANTAG's Pass 2 prompt surface; it does not rewrite SPANTAG.
- **No new eval cases in this WO.**
- **No rename or re-open of #95.**
- **No global synonym tables.**
- **No `alt_defensible_paths` / `alt_defensible_values` scorer changes** (#94 / #97 own those).
- **No FIELD-DISCIPLINE-01 lane** — #142 owns "discipline" (run-report header).
- **FIELD-CARDINALITY-01 is a separate deferred lane, not folded here.** Architecture Spec v1 §7.3 names it as a potential future WO layered on top of BINDING-01 if the minimal scalar guard in PATCH 4 proves insufficient. BINDING-01 does not pre-commit to that scope.

## 4. Implementation strategy — Option A primary (re-locked 2026-04-23)

**Decision:** Option A first. Binding rules live in the SPANTAG Pass 2 prompt / binding contract. No standalone rule-layer in this WO. No fewshot-only patch as primary fix.

**Rationale:**

- Keeps causal attribution clean when paired with the sequencing decision below.
- Aligns with #90 SPANTAG being promoted to active; BINDING-01 uses the SPANTAG Pass 2 scaffold as its delivery vector without adding a second mechanism.
- Avoids a parallel rule-layer that would need its own env-flag guardrail, eval channel, and rollback surface.

**Option B (standalone rule layer, `HORNELORE_BINDING=1`):** demoted to conditional follow-up. Opens only if SPANTAG lands cleanly but binding still fails after Option A ships.

**Option C (fewshot-only patch to `_NARRATIVE_FIELD_FEWSHOTS`):** rejected as primary. Fewshots regress under sampling and don't enforce cardinality deterministically.

### Sequencing

1. Land SPANTAG-only (no binding rules in prompt).
2. Run `r5f-spantag` eval. Bank the pure span-separation delta.
3. Land BINDING-01 (PATCH 1–5 into SPANTAG Pass 2 surface).
4. Run `r5g-binding` eval. Bank the binding delta layered on SPANTAG.

Do **not** combine fresh SPANTAG changes and BINDING changes into the same tag. `r5f-spantag` and `r5g-binding` are the required tag pair.

## 5. Patch targets

**Primary file:** `server/code/api/routers/extract.py` — the SPANTAG Pass 2 prompt / binding contract block, any colocated binding rubric, and (only for PATCH 4) a narrow post-bind area if one already exists.

Do not patch unrelated prompt sections. Do not broaden scope.

### PATCH 1 — Explicit Type C binding rules in the Pass 2 binding contract

FIND the Pass 2 prompt block that tells the model how to map evidence spans / extracted facts onto canonical field paths (where the model is told to choose canonical paths, prefer exact schema matches, avoid unrelated fields, output structured items).

INSERT / MERGE:

```
BINDING RULES — TYPE C NARRATIVE CORRECTION

1. Residence vs place of birth
- Use personal.placeOfBirth only for the narrator's actual birth location.
- Do not write personal.placeOfBirth for places the narrator later lived,
  moved to, attended school in, or passed through.
- If multiple place names appear in a childhood-moves or life-sequence
  narrative, treat them as residence-related unless the text explicitly
  states birth.

2. Residence period vs education grade level
- Use residence.period for time anchors attached to where the narrator
  lived (e.g., "first and second grade in Strasburg", "third through
  fifth in Glen Ullin", "sixth grade in Bismarck").
- Do not bind grade-number timing phrases to education.gradeLevel when
  they are functioning as move/lived-there timeline anchors.
- Use education.gradeLevel only when the statement is about schooling
  level itself rather than residence chronology.

3. Sibling references vs narrative mentions
- Only write siblings.* when the text explicitly identifies a sibling
  relation or clearly names a sibling as a family member.
- Do not create sibling fields from incidental person mentions unless
  sibling relation is explicit or strongly anchored in local context.

4. Cardinality discipline
- personal.placeOfBirth is scalar: emit at most one value.
- dateOfBirth, timeOfBirth, placeOfBirth and other protected identity
  fields should not receive repeated multi-location narrative values.
- Residence-related fields may take multiple values across a life
  sequence when supported by the text.

5. Movement narratives
- In childhood_moves, middle_moves, or similar place-sequence prompts,
  default ambiguous place mentions toward residence.* rather than
  personal.placeOfBirth.
```

### PATCH 2 — Negative examples directly in prompt guidance

FIND the example / instruction area where field-path examples are given.

INSERT a tight contrast set:

```
Examples

Correct:
- "I was born in Williston, then we moved to Minot, then West Fargo."
  -> personal.placeOfBirth = "Williston"
  -> residence.place = "Minot"
  -> residence.place = "West Fargo"

Correct:
- "We were in Strasburg for first and second grade, then Glen Ullin for
   third through fifth."
  -> residence.period = "first and second grade"
  -> residence.period = "third through fifth grade"

Incorrect:
- "Strasburg", "Glen Ullin", "Bismarck" -> personal.placeOfBirth
  Reason: these are movement/lived-there places, not birth location
  unless birth is explicitly stated.

Incorrect:
- "first and second grade" -> education.gradeLevel
  Reason: here grade labels are being used as residence timeline anchors,
  not as school-level facts.

Incorrect:
- A named person mentioned in passing -> siblings.firstName
  Reason: sibling binding requires explicit sibling relation or clear
  local family anchor.
```

### PATCH 3 — Local tie-break for childhood_moves-style prompts

FIND any part of the Pass 2 contract that references current section / topic / section semantics.

INSERT:

```
Section-sensitive tie-break:
If the current section/topic is about moves, places lived, or life
chronology, and a phrase could map either to residence.* or to an
identity/education field, prefer residence.* unless the text explicitly
states birth or explicit schooling facts.
```

This is **not** reintroducing runtime-causal logic (era/pass/mode remain non-causal per #95). It is a local tie-break for schema binding in semantically ambiguous narratives — a Binding Layer concern, not a Control Layer one.

### PATCH 4 — Minimal post-bind scalar guard for `personal.placeOfBirth`

**Only apply if a narrow post-processing area for extracted items already exists in `extract.py`.** If no clean colocation exists, skip this patch rather than creating a large new rule layer. Deferred cardinality work belongs to FIELD-CARDINALITY-01.

RULE: if more than one `personal.placeOfBirth` item is produced in a single extraction pass:

- keep the strongest explicit birth-anchored candidate;
- if none is explicitly birth-anchored, keep only the first and flag the rest for drop;
- **do not silently re-route extras in this WO.** Silent re-routing could hide prompt failures; surface them.

This is a last-resort cardinality guard, not the primary fix. The primary fix is PATCH 1.4 inside the prompt.

### PATCH 5 — Debug marker

Add one narrow debug log marker around any binding correction branch or scalar guard touched. Format:

```
[extract][BINDING-01]
```

Examples:

- `[extract][BINDING-01] dropped repeated personal.placeOfBirth candidate`
- `[extract][BINDING-01] residence.period favored over education.gradeLevel due to movement narrative tie-break`

Required for eval interpretation — a targeted Type C run must show `[extract][BINDING-01]` evidence in logs if a correction or guard fires.

## 6. Acceptance tests

### A. Primary case — `case_082`

Run on the exact case used in the #95 matrix.

- `personal.placeOfBirth` emits ≤1 value (0 acceptable; 4 is not).
- Childhood movement places do not pile into `personal.placeOfBirth`.
- `residence.period` present for grade-range move anchors.
- `education.gradeLevel` not used for move-timeline anchors unless the text is explicitly about school level.
- No new sibling leakage from incidental mentions.

This is the main gate.

### B. Friendly-fire probe (bake in r5e2 lesson)

10-case Type A/B sample (5 Type A proxies + 5 Type B proxies, chosen from the post-SPANTAG passing set). Require byte-identical or behavior-identical output with the BINDING surface off vs on, except where a sample genuinely contains the targeted Type C conflation.

- Type A cases: no degradation.
- Type B cases: invariant.
- No new parse failures.
- No new `must_not_write` violations.

### C. Regression guard — identity damage

Probe clean personal-identity cases (cases where the narrator has an explicit, unambiguous birth location statement).

- True birth-location statements still bind to `personal.placeOfBirth`.
- No drop in legitimate birth-extraction recall.
- No changes to `dateOfBirth` / `timeOfBirth` behavior.

### D. Cardinality check

For every extraction in this WO:

- `personal.placeOfBirth` count ≤1.
- No duplicate scalar protected-identity fields.

### E. Log visibility

At least one targeted Type C run must show `[extract][BINDING-01]` evidence in `.runtime/logs/api.log` if any correction fires.

## 7. Eval & rollback

Tag: `r5g-binding`. Master eval + standard post-eval audit block (pass count / v3 / v2 / mnw / flips / scorer-drift / truncation_rate) plus the four probes above.

Baseline for delta: `r5f-spantag` (post-SPANTAG, pre-BINDING). Binding delta isolated by construction.

Rollback: revert PATCH 1–5 from the Pass 2 prompt block (single-file edit in `extract.py`). No scorer-side changes, no schema changes, no env flag gating (if PATCH 4 was applied with a flag, unset `HORNELORE_BINDING` to restore Option-A-prompt-only behavior, then revert PATCH 4). Byte-check against `r5f-spantag` after rollback.

## 8. Failure conditions — stop and report

Stop and escalate if:

- Fixing `case_082` requires large nonlocal rule machinery.
- Birth-location recall degrades on clean personal-information cases.
- Type A cases begin collapsing or routing incorrectly.
- SPANTAG and binding changes cannot be cleanly separated in eval (attribution breaks).
- `must_not_write` count rises above the known r5h floor of 2.

Disposition: **ADOPT** / **PARK** / **ITERATE** / **ESCALATE** per standard WO §8 semantics.

## 9. Report deliverables

1. Short code-review note on which of PATCH 1–5 landed and where.
2. Exact patch list (OLD → NEW prompt block diffs).
3. Eval command(s) executed.
4. Before/after for `case_082` (V1 and V6 per-item views if re-run against the matrix).
5. Friendly-fire probe result summary.
6. Final disposition.
7. Standard post-eval audit block + `[extract][BINDING-01]` log occurrences.

## 10. Claude execution notes

- Read the SPANTAG Pass 2 prompt surface in `extract.py` **before** writing any patch.
- Do not broaden scope.
- Do not re-open stage-routing theories.
- Do not tune era/pass/mode.
- Preserve existing extractor behavior outside the targeted Type C binding lane.
- Cardinality work beyond PATCH 4 belongs to FIELD-CARDINALITY-01.

---

## Changelog

- 2026-04-23 (morning): Drafted as follow-up #2 from #95 SECTION-EFFECT Phase 3 PARK. Smoke-test target case_082 V1 per-item view pulled and grounded. Three implementation options scoped.
- 2026-04-23 (afternoon): Cardinality pulled **into** BINDING-01 scope as Layer 2 — per-item read confirmed the over-emission is prompt-invariant (V1 baseline already has it), which upgrades the diagnosis from "Type C gets worse without target" to "Type C is mis-bound under ideal conditions." Option B promoted to primary; Option A (BINDING inside SPANTAG Pass 2) demoted to fallback to protect eval attribution. Eval tag `r5l`.
- 2026-04-23 (evening, re-lock): Chris's Boris-style WO + Architecture Spec v1 paste inverts the Option A/B decision. **Option A is now primary**: binding rules live in the SPANTAG Pass 2 prompt / binding contract via PATCH 1–3. **Option B demoted to conditional follow-up** — opens only if SPANTAG lands cleanly but binding still fails. **Option C rejected**. Sequencing preserved via distinct eval tags: `r5f-spantag` → `r5g-binding`. Cardinality scope contracted — PATCH 4 is a minimal scalar guard for `personal.placeOfBirth` only, optional and colocation-gated; broader cardinality work becomes **FIELD-CARDINALITY-01** as a separate deferred lane (Architecture Spec v1 §7.3). `[extract][BINDING-01]` log marker standard codified (PATCH 5). Friendly-fire probe (§B) + identity-damage regression guard (§C) added to acceptance. Core Law quoted verbatim from Architecture Spec v1. Eval tag changed `r5l` → `r5g-binding`.
