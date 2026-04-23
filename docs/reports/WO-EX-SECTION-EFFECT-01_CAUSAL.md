# WO-EX-SECTION-EFFECT-01 Phase 3 — Causal matrix readout

**Author:** Claude (task #95)
**Date:** 2026-04-23
**Source run tag:** `se_r5h_20260423`
**Pack:** case_008, case_018, case_082
**Stack state:** r5h floor (70/104), HORNELORE_NARRATIVE=1, HORNELORE_ATTRIB_BOUNDARY=0
**Matrix cost:** 3 cases × 6 variants × 4 runs = 72 extractions, 0 errors, 0 retries.

---

## 1. Question, method, guards

**Questions this matrix answers.** Phase 1 adjudicated the stubborn-15; Phase 2 threaded `current_era` / `current_pass` / `current_mode` into the extraction payload. What the matrix settles is whether that stage context actually changes extractor output, or whether it is along for the ride while `current_section` + `current_target_path` do all the work.

**Method.** For each of three stubborn dual-answer-defensible cases (case_008, case_018, case_082), six payload variants were driven through `/api/extract-fields` four times each and scored with `score_case` from the master eval. V1 reproduces the r5h baseline; V2–V4 hold target fixed and vary era / pass / mode; V5 strips all stage context; V6 strips target_path only. Variance within a cell measures stochastic noise; variance between cells measures stage-context signal.

**Typological refinement surfaced by the matrix.** The three cases partition cleanly into a question typology that the matrix itself made visible:

- **Type A — target-anchored abstract narrative** (case_008, `earlyMemories.significantEvent`). The evidence text is rich but the field is an abstraction over that text; without the explicit target_path, the LLM has no handle to bind the prose to. Target_path is load-bearing.
- **Type B — overdetermined factual** (case_018, narrator says "we lived in Germany, Vincent was born there"). Subject, relation, and values are all explicit in the evidence; schema-binding is over-constrained regardless of prompt context. Target_path and stage context are both inert.
- **Type C — weakly-constrained narrative** (case_082, dense multi-place childhood-moves). Evidence is factual but schema mapping requires cardinality + domain judgments (residence.place vs personal.placeOfBirth; residence.period vs education.gradeLevel) that the prompt doesn't enforce. Target_path nudges schema slot selection at the margin but does not fix cardinality bugs.

This typology is the actionable finding of the matrix, not the Q1/Q2/Q3 numbers alone.

**What the matrix cannot claim.** n=4 per cell is a stability probe, not a power calculation. "V2=0 path diff" means "no change larger than the within-cell noise floor," not "era has no effect." The 7 truncation-starved stubborn cases are excluded on purpose — their bottleneck is max-new tokens, not stage context. And cross-case generalization from n=3 should be treated as directional, not authoritative — the Type A/B/C split is a hypothesis worth carrying forward, not a proven taxonomy.

---

## 2. Per-case matrix

### case_008 — christopher-todd-horne / developmental_foundations / family_stories_and_lore **(Type A — target-anchored abstract narrative)**

Baseline era = `school_years`; baseline target = `earlyMemories.significantEvent`.
Alt-defensible target = `parents.notableLifeEvents`.

| Variant | era | pass | mode | section | target_path | emitted (4-run union) | emit median | method modal | pass@alt | shape_chg |
|---|---|---|---|---|---|---|---|---|---|---|
| V1 | school_years | pass1 | open | family_stories_and_lore | earlyMemories.significantEvent | {earlyMemories.significantEvent} | 1 | llm | 4/4 @alt | no |
| V2 | adolescence | pass1 | open | family_stories_and_lore | earlyMemories.significantEvent | {earlyMemories.significantEvent} | 1 | llm | 4/4 @alt | no |
| V3 | school_years | pass2a | open | family_stories_and_lore | earlyMemories.significantEvent | {earlyMemories.significantEvent} | 1 | llm | 4/4 @alt | no |
| V4 | school_years | pass1 | recognition | family_stories_and_lore | earlyMemories.significantEvent | {earlyMemories.significantEvent} | 1 | llm | 4/4 @alt | no |
| V5 | — | — | — | — | — | {} | 0 | **fallback** | 0/4 | no |
| V6 | school_years | pass1 | open | family_stories_and_lore | **—** | {} | 0 | **fallback** | 0/4 | no |

**Attribution-count evidence:** V1 vs {V2,V3,V4} = 0 path diffs each. V1 vs V6 = 1 path diff (`-earlyMemories.significantEvent`, method flipped llm→fallback). V1 vs V5 = 1 path diff (same as V6).

**Type-A reading.** The target_path is the only handle the LLM has for this abstract field. With it: clean 4/4 via alt-defensible. Without it: the LLM produces output the parser rejects, fallback emits zero, score 0/4. Era/pass/mode carry no marginal signal.

### case_018 — kent-james-horne / midlife / middle_moves **(Type B — overdetermined factual)**

Baseline era = `midlife`; baseline target = `residence.place`.

| Variant | era | pass | mode | section | target_path | emitted (4-run union) | emit median | method modal | pass@alt | shape_chg |
|---|---|---|---|---|---|---|---|---|---|---|
| V1 | midlife | pass1 | open | middle_moves | residence.place | {family.children.firstName, family.children.placeOfBirth, family.children.relation} | 3 | llm | 4/4 @alt | no |
| V2 | later_life | pass1 | open | middle_moves | residence.place | (same) | 3 | llm | 4/4 @alt | no |
| V3 | midlife | pass2a | open | middle_moves | residence.place | (same) | 3 | llm | 4/4 @alt | no |
| V4 | midlife | pass1 | recognition | middle_moves | residence.place | (same) | 3 | llm | 4/4 @alt | no |
| V5 | — | — | — | — | — | (same) | 3 | llm | 4/4 @alt | no |
| V6 | midlife | pass1 | open | middle_moves | **—** | (same) | 3 | llm | 4/4 @alt | no |

**Attribution-count evidence:** V1 vs {V2,V3,V4,V5,V6} = 0 path diffs across the board. The extractor's behavior on this case is **completely invariant to stage context**.

**Type-B reading.** The narrator reply ("we lived in Germany… Vincent was born there") binds subject, relation, and values explicitly. The LLM extracts `family.children.placeOfBirth` as the defensible alt regardless of any prior — target_path, era, pass, and mode are all inert because the evidence text already answers its own binding question.

### case_082 — janice-josephine-horne / developmental_foundations / childhood_moves **(Type C — weakly-constrained narrative)**

Baseline era = `school_years`; baseline target = `residence.place`.
Dense multi-value truth zone (Spokane, Dodge, Glen Ulin…).

| Variant | era | pass | mode | section | target_path | emitted (4-run union, abbrev) | emit median | method modal | pass@alt | shape_chg |
|---|---|---|---|---|---|---|---|---|---|---|
| V1 | school_years | pass1 | open | childhood_moves | residence.place | {education.schooling, parents.firstName, parents.occupation, personal.placeOfBirth, **residence.period**, siblings.firstName} | 11 | llm | 4/4 @alt+primary | no |
| V2 | adolescence | pass1 | open | childhood_moves | residence.place | (same as V1) | 11 | llm | 4/4 @alt+primary | no |
| V3 | school_years | pass2a | open | childhood_moves | residence.place | (same as V1) | 11 | llm | 4/4 @alt+primary | no |
| V4 | school_years | pass1 | recognition | childhood_moves | residence.place | (same as V1) | 11 | llm | 4/4 @alt+primary | no |
| V5 | — | — | — | — | — | V1 + {**education.gradeLevel, siblings.relation**} − {**residence.period**} | 10 | llm | 4/4 @alt+primary | no |
| V6 | school_years | pass1 | open | childhood_moves | **—** | V1 + {**education.gradeLevel**} − {**residence.period**} | 10 | llm | 4/4 @alt+primary | no |

**Attribution-count evidence:** V1 vs {V2,V3,V4} = 0 path diffs. V1 vs V6 = 2 path diffs (adds education.gradeLevel, drops residence.period). V1 vs V5 = 3 path diffs (V6's two plus siblings.relation). Score stays 1.0 via alt paths in all variants.

**Per-item view (factual nit, honored).** The path-set summary hides a larger phenomenon: V1 already emits **four** `personal.placeOfBirth` items (Spokane WA, Dodge ND, Glen Ullin, Strasburg — all places Janice *lived*, not places she was *born*) and **three** `residence.period` items ("first and second grade", "third–fifth grade", "sixth grade"). V6 preserves the four-value `personal.placeOfBirth` over-emission and additionally swaps `residence.period` for `education.gradeLevel`. The cardinality+domain confusion (multiple values into a scalar field; residence-vs-personal, residence-vs-education) is **prompt-invariant** — it is present in V1 and persists through V6. Target_path nudges schema slot selection at the margin (residence.period vs education.gradeLevel) but does not fix the underlying over-cardinality.

**Type-C reading.** Evidence is factual but the schema mapping requires cardinality and domain-gating judgments the prompt doesn't currently carry. Target_path helps at the margin (restores `residence.period` as the slot for grade-range anchors); era/pass/mode add nothing. The real fix is extractor-side schema binding, not prompt-side stage context.

---

## 3. Attribution answers

- **Q1 — Does varying era/pass/mode with target held change emissions?** **NO.**
  Evidence: V2 / V3 / V4 produce **zero** path-set diffs vs V1 in all three cases (0+0+0 for case_008, 0+0+0 for case_018, 0+0+0 for case_082). Emission counts, methods, and scores are also bit-identical. At n=4 the within-cell stochastic floor didn't even produce cosmetic reshuffling — the extractor is indifferent to era/pass/mode once the section+target prior is in hand.

- **Q2 — Does stripping target_path with section held change emissions?** **YES, stratified by Type A/B/C.**
  - Type A (case_008): catastrophic — V6 drops the LLM path, emits zero, 0/4 pass. Target_path is the only semantic anchor available for an abstract target.
  - Type B (case_018): inert — V6 = V1 exactly. Evidence text is overdetermined; schema-binding is solved before prompt context arrives.
  - Type C (case_082): cosmetic at the path-set level (2 diffs: gains education.gradeLevel, loses residence.period; score still 1.0 via alts) and invariant at the per-item cardinality level (four-value personal.placeOfBirth over-emission is present in both V1 and V6). Target_path nudges but does not gate.

- **Q3 — Does stripping all stage context degrade toward scatter?** **YES, stratified by Type A/B/C — and the degradation is attributable to target-stripping, not era/pass/mode strip.**
  - Type A (case_008): V5 = V6 = catastrophic (both fallback-to-zero, 1 diff vs V1). Era/pass/mode strip adds nothing on top.
  - Type B (case_018): V5 = V6 = V1 (0 diffs). Completely invariant to everything.
  - Type C (case_082): V5 adds one extra path over V6 (siblings.relation). The target-strip does the heavy lifting; era/pass/mode strip is a rounding error.

---

## 4. Decision

**Disposition: PARK.**

**Reasoning — extraction is semantics-driven, but errors are binding-driven.** The matrix refutes the implicit SECTION-EFFECT Phase 2 hope that era/pass/mode carry independent signal; Q1 is a clean no at n=4 with zero within-cell variance to hide behind. What Q2 and Q3 reveal, stratified through Type A/B/C, is that the real axes of variation live in the **question-evidence pair**, not in the runtime stage context. And the per-item read of case_082 sharpens this further: Type C's failures are present in V1 — the "ideal" configuration — which means the problem is not routing (context) but binding (extractor-internal schema constraint).

- When the evidence is overdetermined (Type B), the extractor binds correctly regardless of what the prompt carries.
- When the target is abstract (Type A), the extractor needs the `current_target_path` as a semantic anchor or it falls off a parse cliff. Section alone does not substitute.
- When the evidence is factual but schema-weakly-constrained (Type C), neither target_path nor section is enough — the extractor is mis-bound under ideal conditions. It needs routing rules AND cardinality enforcement that live in the extractor itself, not in the prompt context. BINDING-01 carries both.

Era / pass / mode never enter this story. They are non-causal for extraction behavior on this sample; their job, if any, is observability.

This matches WO §8 PARK criteria: Q1=No, Q3=Yes-but-driven-by-target. ITERATE does not apply — §8 reserves it for "cross-run variance > cross-variant variance, re-run with n=8 because results are inconclusive"; our results had zero within-cell variance on 16 of 18 slots. ESCALATE does not apply — no new failure mode surfaced that wasn't already scoped. The operational consequence is that SECTION-EFFECT Phase 2's payload plumbing is load-bearing for observability only — `[extract][summary]` logs should keep era/pass/mode as a diagnostic breadcrumb, but SPANTAG Pass 2's controlled-prior prompt should drop them to save tokens.

One finding worth flagging outside the PARK box: **case_008's target-stripped behavior is a parse-or-fallback cliff**, not a shape drift. When target_path is absent the LLM produces output the parser rejects and the fallback emits zero items. This is a SILENT-OUTPUT-adjacent signal — it says explicit target_path anchoring is doing semantic work the LLM can't do on its own when the question is "early memories of family stories." Not a new failure mode per §8 ESCALATE (we already knew the subject-vs-section tension existed), but it reframes case_008's Phase 1 `dual_answer_defensible` label: without the target, it doesn't dual-answer — it single-answers nothing.

**Follow-ups:**

1. **Promote #90 WO-EX-SPANTAG-01 to active.** Pass 2's controlled-prior prompt keeps `current_section` + `current_target_path` as the anchor pair and **drops** `current_era` / `current_pass` / `current_mode` from the block. Rationale: Type A shows target_path is load-bearing; Q1 shows era/pass/mode are not. If a later evidence class pulls the dropped fields back in, reactivate conditional on that evidence. Existing spec already covers two-pass structure; this readout supplies the prompt-content delta. No new WO minted.
2. **New lane: WO-EX-BINDING-01.** Address schema-binding failures exposed by Type C case_082 as the Binding Layer fix in Architecture Spec v1 §7.1. Three conflation pairs: residence vs personal.placeOfBirth (movement-value leaking to birthplace-scalar); residence.period vs education.gradeLevel (duration-anchor schema slot); siblings vs narrative references. Plus a minimal scalar-cardinality guard for `personal.placeOfBirth` only (PATCH 4). Smoke-test target: case_082 V1 and V6 both. Sequencing: BINDING-01 runs **after** SPANTAG (not alongside), to preserve clean causal attribution between span-separation and binding deltas. Spec: `WO-EX-BINDING-01_Spec.md`.
3. **Sequencing (SPANTAG → BINDING, not coupled).** SPANTAG first, alone — measures pure span-separation lift under `r5f-spantag`. BINDING-01 layers on top as a separate eval (`r5g-binding`) via **Option A** — binding rules delivered inside the SPANTAG Pass 2 prompt / binding contract (PATCH 1–3 + optional PATCH 4 scalar guard + PATCH 5 `[extract][BINDING-01]` log marker). Coupling them into a single eval tag would confound the gate; the matrix set up clean causal attribution and distinct tags preserve it. Option B (standalone rule layer) is a conditional follow-up if SPANTAG lands cleanly but binding still fails.
4. **FIELD-CARDINALITY-01 minted as a deferred separate lane** (Architecture Spec v1 §7.3). BINDING-01 carries only a minimal scalar guard for `personal.placeOfBirth`; broader cardinality discipline across other scalars opens as its own WO if the minimal guard proves insufficient. Explicitly **not** FIELD-DISCIPLINE-01 — #142 owns "discipline."
5. **Observability (not a WO):** keep Phase 2's era/pass/mode log threading as-is in `[extract]` / `[extract][summary]` lines. Cost is ~10 chars per log line and it catches shifts that n=4 here can't.
6. **No ITERATE trigger.** Cross-run variance inside a cell was zero on 16 of 18 slots; the signal floor is below the between-cell deltas, so n=8 would not change the call. **No ESCALATE trigger** — no new failure mode surfaced that wasn't already scoped in Phase 1 adjudication + r5e1 silent-output Phase 1+2 work.

**Bumper sticker:** Extraction is semantics-driven, but errors are binding-driven.

---

## 5. Revision history

- 2026-04-23: Phase 3 matrix ran clean (72/72, 0 errors, tag `se_r5h_20260423`). Q1=NO, Q2=YES (target-driven), Q3=YES (target-driven). Disposition: PARK. Tasks #95 and #63 closed.
- 2026-04-23 (revision): Rewrote reasoning block around Type A/B/C question typology after three-agent triangulation. Q2 and Q3 wording upgraded from "case-dependent" / "target-driven" to "YES, stratified by Type A/B/C" with the same evidence. §2 case headers tagged with type. §4 reasoning reframed around "semantics-driven, not context-driven" — the real axes of variation live in the question-evidence pair, not in runtime stage context. Follow-ups restructured: (1) promote existing #90 SPANTAG with era/pass/mode dropped from Pass 2 prompt (no new SPANTAG WO), (2) mint WO-EX-BINDING-01 for schema-binding failures exposed by Type C (smoke-test case_082), (3) defer cardinality-lane naming until after BINDING-01 scoping — explicitly not FIELD-DISCIPLINE-01 (#142 collision). Disposition unchanged: PARK; ITERATE pushback sustained per §8 ("re-run with n=8" is not what happened here — within-cell variance was zero on 16 of 18 slots). Honored factual nit on case_082 per-item view: V1 already emits four personal.placeOfBirth items; the over-cardinality is prompt-invariant, not a V6 regression.
- 2026-04-23 (second revision, post-triangulation lock): Bumper sticker upgraded to **"Extraction is semantics-driven, but errors are binding-driven"** — the per-item read proves Type C's failures exist in V1 (the "ideal" configuration), which means the problem is extractor-internal binding, not routing. Follow-ups #2 and #3 consolidated: cardinality enforcement folded into BINDING-01 as Layer 2 (not deferred to a future lane), and SPANTAG↔BINDING coupling decision locked as **sequenced, not coupled** — SPANTAG first alone (r5f-spantag clean span-separation signal), BINDING-01 layered on top (r5l clean binding delta under `HORNELORE_BINDING=1`). Coupling them would confound the eval gate; matrix set up clean causal attribution and it will be preserved. Follow-up #4 renumbered (was deferred cardinality lane; now "no successor lane minted" — cardinality is inside BINDING-01). Observability + no-ITERATE items renumbered to 5 and 6.
- 2026-04-23 (third revision, re-lock after Chris's Boris-style BINDING WO + Architecture Spec v1 paste): Bumper sticker and Q1/Q2/Q3 answers unchanged. Follow-up #2 tightened: BINDING-01 now frames as the **Binding Layer** fix per Architecture Spec v1, with three routing conflation pairs plus a **minimal** scalar guard for `personal.placeOfBirth` only. Follow-up #3 rewritten around the re-lock: **Option A primary** (binding rules delivered inside the SPANTAG Pass 2 prompt / binding contract — PATCH 1–5), Option B standalone rule layer demoted to conditional follow-up, Option C fewshot-only rejected. Distinct eval tags retained — `r5f-spantag` then `r5g-binding` (replaces the prior `r5l` tag). Follow-up #4 replaced with **FIELD-CARDINALITY-01 minted as a deferred separate lane** (Architecture Spec v1 §7.3), taking broader cardinality enforcement out of BINDING-01's Layer 2 and leaving only the minimal scalar guard inside. Observability (#5) and no-ITERATE/ESCALATE (#6) unchanged.
