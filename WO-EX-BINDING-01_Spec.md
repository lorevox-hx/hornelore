# WO-EX-BINDING-01 — Schema-binding rules for weakly-constrained narrative (Type C)

**Status:** DRAFT (2026-04-23, authored after #95 PARK)
**Owner:** extractor lane (Claude)
**Priority:** parallel lane — does not block SPANTAG promotion (#90)
**Blocks:** nothing directly; may reduce friction for SPANTAG Pass 2 binding step
**Blocked by:** nothing
**Eval tag:** `r5l` or successor (runs after SPANTAG r5f-spantag + any BINDING rule layer)
**Task:** new (created 2026-04-23 as follow-up #2 from SECTION-EFFECT Phase 3 PARK)

---

## 1. Problem statement

The #95 SECTION-EFFECT causal matrix surfaced a question typology (Type A / B / C). Type C — weakly-constrained narrative — is the class the existing extractor handles worst. case_082 (janice-josephine-horne / developmental_foundations / childhood_moves) is the smoke-test exemplar.

**Core diagnosis (upgraded after per-item read).** The over-emission on case_082 is not a V6 regression — V1 already emits four `personal.placeOfBirth` items in the "ideal" configuration (full target_path + section + era/pass/mode). That reframes the whole lane: **Type C is mis-bound under ideal conditions, not just under prompt stripping.** Routing signals (target_path, section) don't fix it. Context signals (era/pass/mode) don't fix it. The failure is extractor-internal binding, not runtime context.

**Evidence from the matrix (per-item view, V1 and V6 both):**

| Symptom | V1 (baseline) | V6 (target stripped) | Interpretation |
|---|---|---|---|
| `personal.placeOfBirth` emits 4 items (Spokane, Dodge, Glen Ullin, Strasburg) | ✓ | ✓ | **Two violations:** (a) domain-bind error — places she *lived* routed to birthplace-scalar slot; (b) cardinality violation — scalar field emits 4 values. Prompt-invariant. |
| `residence.period` with grade-range values ("first and second grade"…) | ✓ (3 items) | ✗ (swapped for `education.gradeLevel`) | Schema-slot drift when target_path absent. Target_path nudges but is not authoritative. |
| `education.schooling` = "Sacred Hearts" (correct) | ✓ | ✓ | No problem. |

case_082 passes the eval by accident — `alt_defensible_paths` credits the places-lived-as-birthplace emissions against the `residence.place` truth zone. But the underlying extraction is incorrect on two orthogonal axes: (i) the LLM is conflating three distinct schema families (`personal.*` narrator-scalar, `residence.*` temporal-list, `education.*` school-indexed) — **wrong-field** error; (ii) the LLM is emitting N values into a scalar slot — **wrong-cardinality** error. Both must be addressed for Type C to be honestly correct.

Type A (case_008) and Type B (case_018) are not affected — Type A has target_path as its semantic anchor and Type B has evidence that is self-binding. Type C has neither: target_path helps at the margin (restores `residence.period`) but does not fix the underlying binding failure.

## 2. Scope (in)

Binding rules in two layers: **wrong-field** (routing) and **wrong-cardinality** (constraint).

**Layer 1 — routing rules (three conflation pairs evident in case_082):**

1. **`residence.place` vs `personal.placeOfBirth`** — multi-value movement places must not land on a birthplace-scalar. When the question-section is `childhood_moves` / `middle_moves` / any `*_moves` section, `personal.placeOfBirth` is `must_not_write` unless the evidence text contains explicit birthplace language ("born in", "birthplace", "I was born").
2. **`residence.period` vs `education.gradeLevel`** — grade-range values ("first and second grade") anchor residence duration when the narrator is describing a move; they anchor education timeline only when the narrator is describing schooling separately. Default: grade-range values co-occurring with place-name values attach to `residence.period`, not `education.gradeLevel`.
3. **`siblings.*` vs narrative-reference collisions** — sibling first-name mentions inside a narrative about the narrator's life (not the sibling's) should land on `siblings.firstName` only when the narrator's explicit subject was a sibling. Otherwise mention-only with no write. (case_082 `siblings.firstName='Verene'` currently lands because the narrator mentions her — but the subject of the narrative was Janice's moves, not Verene.)

**Layer 2 — cardinality enforcement:**

4. **Scalar fields must emit ≤1 value per extraction call.** Enforced on the schema-declared scalar set: `personal.placeOfBirth`, `personal.dateOfBirth`, `personal.firstName`, `personal.lastName`, `personal.birthOrder`, and any other field the schema marks as scalar. When the LLM emits N>1 candidates for a scalar, the binding pass selects the best candidate (highest confidence, most-explicit anchor) and demotes the rest — either remapped to the correct list-field if routing rule 1–3 identifies one (e.g., four `personal.placeOfBirth` candidates in a `*_moves` section become four `residence.place` candidates), or dropped with a `[extract][binding] cardinality_demotion` log line.
5. **Multi-value fields emit N as-is** (`residence.place`, `residence.period`, `education.schooling`, `siblings.firstName`, etc.). No enforcement needed — this is the default.

The cardinality layer is the reason SPANTAG alone will not close Type C: SPANTAG separates span-detection from binding, but the binding step still needs a schema-aware constraint check before it commits. Without Layer 2, four `placeOfBirth` candidates remain four `placeOfBirth` items regardless of how cleanly Pass 1 detects them.

## 3. Scope (out)

- **Global synonym tables.** This WO introduces section-conditioned routing rules only, not a lookup dictionary.
- **Any change to `alt_defensible_paths` / `alt_defensible_values` scorer annotations.** Those are #94 and #97 respectively; BINDING-01 is extractor-side.
- **Type A (case_008) and Type B (case_018) behavior.** Both are already handled correctly by the matrix-baseline extractor; the friendly-fire probe (§5) is the guardrail that catches any bleed-through.
- **Naming / scope extension to a successor "FIELD-DISCIPLINE-01" lane.** Explicitly not used — #142 owns "discipline" (run-report header). If Layer 2 cardinality enforcement proves insufficient and a further domain-gating lane emerges, it will be named separately and scoped on its own evidence.
- **Coupling with SPANTAG (#90).** BINDING-01 runs **after** SPANTAG, not alongside — see §4.

## 4. Implementation options — sequencing decision

**SPANTAG runs first, alone. BINDING-01 layers on top.** Three-agent convergence on this ordering:

- Coupling BINDING into SPANTAG's Pass 2 prompt would confound the eval gate — any r5f-spantag delta could be attributed to span-separation (SPANTAG), binding rules (BINDING-01), or interaction, and the matrix that produced this WO explicitly set up clean causal attribution. Collapsing the variables now throws that away.
- Separating them preserves signal: (1) r5f-spantag eval measures pure span-separation lift; (2) r5l eval (BINDING on top of adopted SPANTAG) measures the binding delta.
- This also means if SPANTAG's Pass 2 prompt rewrite itself lifts case_082 materially (possible — two-pass structure may improve routing as a side effect), BINDING-01's scope can contract accordingly.

**Three implementation options, evaluated against the separated-sequencing decision:**

**Option B (preferred) — standalone rule layer in extract.py.**
Add a post-LLM rewrite pass (layers 1 + 2) that inspects emitted items and applies remapping + cardinality demotion. Gated behind `HORNELORE_BINDING=1` flag. Lands **after** SPANTAG default-on. Independent of the SPANTAG gate; clean r5l delta. Requires explicit "this is not a Type C case" short-circuit (section-based gate: fire only on `*_moves`, `childhood_*`, `family_*_lore` sections, plus whichever sections the Type C classifier evolves to cover).

**Option C — fewshot addition to `_NARRATIVE_FIELD_FEWSHOTS`.**
Add a case_082-style fewshot demonstrating correct routing + scalar cardinality. Cheapest commit, but least durable — fewshots regress under LLM sampling and don't enforce cardinality deterministically. Fallback only; not primary.

**Option A — prompt rule layer in SPANTAG Pass 2.** Rejected for primary BINDING-01 delivery (couples the evals), but a targeted lightweight version of the routing rules MAY land as a SPANTAG Pass 2 fewshot addition if (and only if) SPANTAG's eval shows no Type C improvement without binding help. That would be scoped as a SPANTAG addendum, not a BINDING-01 deliverable, to keep the eval-attribution story clean.

**Decision gate:** Option B primary; Option C fallback if B's cardinality demotion proves too aggressive on non-Type-C cases; Option A only as a scoped SPANTAG addendum if Type C signal is invisible without binding help.

## 5. Acceptance (r5l — run **after** SPANTAG r5f-spantag has been adopted)

- **Smoke-test target: case_082.**
  - `personal.placeOfBirth` emits ≤1 item (preferably 0, since Janice's birthplace is not clearly in the childhood_moves evidence text; certainly not 4). This is the cardinality-layer check.
  - The four place values (Spokane/Dodge/Glen Ullin/Strasburg) land on `residence.place` (list field) via Layer 1 rule 1 remap. This is the routing-layer check.
  - `residence.period` restored in V6-equivalent runs (target-stripped) — grade-range anchors land on residence, not education.
  - `education.gradeLevel` not emitted unless evidence text describes schooling separately from place-movement.
  - `siblings.firstName='Verene'` down-weighted or absent.
  - Overall case_082 score stays 1.0 on the primary truth zone (`residence.place`, now via primary path not alt-credit), with the failure-category tags reducing: `noise_leakage` classifier should lose its trigger on this case.
- **No regressions on Type A / Type B exemplars.** case_008 and case_018 unchanged.
- **Master eval (r5l vs post-SPANTAG baseline):** pass count ≥ post-SPANTAG baseline, zero newly-failing cases from the BINDING rule firing on cases it shouldn't. v3 and v2 subsets flat or improved.
- **must_not_write ≤ 2** (same two pre-existing offenders; no new violations from BINDING firing).
- **Friendly-fire probe.** A 10-case sample of non-Type-C cases (5 Type A + 5 Type B proxies, chosen from the post-SPANTAG passing set) must emit byte-identical items with and without the BINDING flag. This is the guardrail that caught the r5e2 ATTRIBUTION-BOUNDARY regression — bake it in before landing.
- **Clean causal attribution.** r5l minus post-SPANTAG baseline isolates the BINDING delta; SPANTAG's own signal is already banked separately. No collapsed variables.

## 6. Evaluation & rollback

Eval tag `r5l`, master + standard post-eval audit block (pass count / v3 / v2 / mnw / flips / scorer-drift / truncation_rate).

Rollback: if Option A, revert the Pass 2 prompt additions; if Option B, set `HORNELORE_BINDING=0` and byte-check against r5h. No scorer-side changes to revert.

## 7. Open questions (resolve before implementation)

- Is the Type A/B/C classification cheap enough at runtime to gate BINDING firing? (Crude: BINDING applies only when `current_section` matches `*_moves` and target_path is in `residence.*`. Finer gates possible.)
- Does Option A's SPANTAG coupling complicate the SPANTAG gate itself? (If BINDING fires inside SPANTAG Pass 2, does SPANTAG's eval need to separately credit BINDING for any improvement?)
- Should `siblings.firstName` routing rule wait for a bigger-sample evidence base? (case_082 alone may not justify it; the `noise_leakage` classifier signal is diffuse.)

## 8. Standard audit block (required at landing)

Report r5l:

- total pass count
- v3 / v2 contract subset
- must_not_write violations
- named affected cases (case_082 primary; any non-Type-C case that moves)
- pass↔fail flips (must be 0 friendly-fire)
- scorer-drift audit on every flip
- truncation_rate
- friendly-fire probe result (byte-identical on 10-case sample)

---

## Changelog

- 2026-04-23: Drafted as follow-up #2 from #95 SECTION-EFFECT Phase 3 PARK. Smoke-test target case_082 V1 per-item view pulled and grounded (V1 already emits 4 `personal.placeOfBirth` items; V6 preserves that and swaps `residence.period` for `education.gradeLevel`). Cardinality/domain-gating lane name deferred per Chris's direction; explicitly not FIELD-DISCIPLINE-01 (#142 collision). Three implementation options scoped; decision gate favors Option A if SPANTAG lands cleanly.
- 2026-04-23 (revision): Cardinality pulled **into** BINDING-01 scope as Layer 2 — per-item read confirmed the over-emission is prompt-invariant (V1 baseline already has it), which upgrades the diagnosis from "Type C gets worse without target" to "Type C is mis-bound under ideal conditions." Scalar fields enforce ≤1 value per extraction call; excess candidates demote (remap to list-field if routing identifies one, drop otherwise) with a `[extract][binding] cardinality_demotion` log line. SPANTAG↔BINDING coupling decision flipped: **sequenced, not coupled** — SPANTAG eval runs alone (r5f-spantag) for clean span-separation signal; BINDING-01 layers on top (r5l) for clean binding delta. Option A (BINDING inside SPANTAG Pass 2) demoted to fallback-only to protect eval attribution. Option B (standalone rule layer, `HORNELORE_BINDING=1`) promoted to primary. Successor-lane naming language tightened in §3 (still not FIELD-DISCIPLINE-01). Bumper sticker captured: **"Extraction is semantics-driven, but errors are binding-driven."**
