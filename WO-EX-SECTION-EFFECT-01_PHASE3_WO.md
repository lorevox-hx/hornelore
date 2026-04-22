# WO-EX-SECTION-EFFECT-01 Phase 3 — Causal matrix on life-map stage signals

**Author:** Claude (LOOP-01 R5.5, overnight pack, 2026-04-21)
**Status:** DRAFT — execution pack for task #95. Phase 1 + Phase 2 landed (#92, #93, #94). This WO scopes the Phase 3 causal matrix referenced in `WO-EX-SECTION-EFFECT-01_Spec.md` §Scope (Phase 3) and §Implementation plan (Commit 5).
**Blocks:** WO-EX-SPANTAG-01 Pass 2 eval measurement #10 (section-effect causal chain). SPANTAG can still *ship code* behind the flag without Phase 3; it can't *claim causal attribution* without it.
**Does NOT block:** the r5e1 extractor path; default live behavior is untouched by this WO. All matrix runs are diagnostic-mode eval invocations with varied payload — no extract.py change.

---

## 1. Why this Phase exists (one paragraph)

Phase 1 adjudicated the stubborn-15. Phase 2 threaded `current_era` / `current_pass` / `current_mode` into the extraction payload and `[extract]` logs. What we *still do not know*: does the life-map stage actually do work? That is, when we hold the narrator reply and the `current_target_path` fixed but vary era/pass/mode, does the model emit differently? Or is the load-bearing upstream signal entirely captured by `current_section` + `current_target_path`, with era/pass/mode along for the ride? Until we run this matrix, every SPANTAG Pass 2 eval report will hand-wave that question.

---

## 2. Scope

### In scope

- Run a **targeted 2–3-case diagnostic matrix** (not a full 104-case sweep) that varies stage context around the dual-answer-defensible cases adjudicated in Phase 1.
- Record emissions per variant into a small JSON + a short human readout (`WO-EX-SECTION-EFFECT-01_CAUSAL.md`).
- Answer three attribution questions, each Yes/No/Indeterminate with evidence:
  1. When `current_target_path` is held fixed, does varying `current_era` / `current_pass` / `current_mode` change emissions?
  2. When `current_section` is held fixed, does varying `current_target_path` change emissions?
  3. When stage context is withheld entirely (all five fields absent), do emissions degrade toward the baseline "scatter-shoot the catalog" behavior the section prior was designed to prevent?
- **Cost box:** ≤ 60 extraction calls total (3 cases × 5 variants × 4 runs). One session on the live stack, no restart required.

### Out of scope

- Modifying extractor behavior based on matrix findings. Phase 3 is a measurement; any changes it motivates will be a separate WO (SPANTAG Pass 2 design consumer, or a new section-prior-weighting WO if the matrix says era/pass/mode are doing real work).
- The 7 truncation-starved stubborn cases (080/081/083/084/085/086/087). Section-effect is not their bottleneck; running them through this matrix would bury the signal in noise. They are the target pack of #96 / WO-EX-TRUNCATION-LANE-01, a separate lane.
- Full master eval. The matrix is per-case at high variant resolution; we do not re-run 104.

### Explicit non-goals

- No prompt rewrite. No few-shot additions or removals.
- No scorer change. Phase 1's `alt_defensible_paths` / Phase 2's `alt_defensible_values` policy is already in place and stays untouched.
- No interview-runtime change. We synthesize stage-context payloads from the eval harness, not from the live UI.

---

## 3. Case pack — which 2–3 cases and why

Pick from the four `dual_answer_defensible` cases: **008, 009, 018, 082**. The Phase 1 adjudication already argued each has a subject-driven path and a section-driven path that both preserve the fact. That is exactly the tension the matrix needs to expose.

**Recommended pack (pick 2 for tier-1, 1 for tier-2 control):**

| Tier | Case | Why | Primary axis to vary |
|---|---|---|---|
| 1 | **case_008** | "mom's brother James born in a car" — expected `parents.notableLifeEvents`; `developmental_foundations / family_stories_and_lore` section. Classic section-vs-subject tension where section won on r4j. | section_prior vs subject_cue |
| 1 | **case_018** | "lived in Germany… Vincent was born there" — expected `residence.place`; `midlife / middle_moves` section. Counter-example to 008: here subject beat section on r4j. | relation_cue vs section_prior |
| 2 (control) | **case_082** | "born in Spokane because dad was working at aluminum factory…" — has multi-value truth zone (Spokane, Dodge, Glen Ulin…) and a `personal.placeOfBirth` alt. Useful as a control because the answer is dense enough to catch truncation confounds that 008 / 018 won't surface. | target_path specificity |

**case_009 excluded** on purpose: its defensible-alt is an intra-catalog neighbor (`education.earlyCareer` vs `education.careerProgression`), which exercises finer-grained binding that is more SPANTAG's job than stage-context's. Keep it for SPANTAG's measurement pack, not this one.

---

## 4. The matrix

For each chosen case, run **5 variants × 4 runs per variant = 20 extractions per case**. 2-case tier-1 + 1-case control = 60 extractions total. All variants use the same `narrator_reply` from the case.

| Variant | current_section | current_target_path | current_era | current_pass | current_mode | Purpose |
|---|---|---|---|---|---|---|
| V1 | baseline from case | first item of extractPriority | correct era per `_phase_to_era()` | `pass1` | `open` | Reproduce r5e1 / r4j behavior; anchor point. |
| V2 | baseline | baseline | **era shifted ±1 tier** (e.g. school_years → adolescence) | pass1 | open | Hold section + target fixed, vary era. |
| V3 | baseline | baseline | baseline | **`pass2a`** | baseline | Hold section + target + era fixed, vary pass. |
| V4 | baseline | baseline | baseline | pass1 | **`recognition`** | Hold section + target + era fixed, vary mode. |
| V5 | **None** | **None** | None | None | None | Strip stage context entirely. Anchor for "how much does the prior actually do?" |

4 runs per variant gives us n=4 for stability per cell — enough to spot stochastic flips vs stage-driven flips at coarse resolution. If run-to-run variance swamps between-variant variance, that is itself a finding ("stage context signal is below the model's output noise floor").

**Why not vary target_path too?** We already have Phase 1 evidence that target_path changes outcomes (case_008 emits at `earlyMemories.significantEvent`, not `parents.notableLifeEvents`, when the first-item target is earlyMemories). Adding a target_path axis explodes the matrix without new information. Question 2 ("does varying target_path change emissions when section is held") is answered by comparing V1 and V5: V1 has a target_path, V5 does not; V5's section stays the same.

Correction on the above, now that I look at V5's design: V5 strips **section** too, not just target_path. To answer question 2 cleanly we need a sixth variant that keeps section but drops target_path. Add:

| Variant | current_section | current_target_path | current_era | current_pass | current_mode | Purpose |
|---|---|---|---|---|---|---|
| V6 | baseline | **None** | baseline | baseline | baseline | Hold section + era/pass/mode, strip target_path. |

**Final matrix: 6 variants × 4 runs = 24 extractions per case × 3 cases = 72 total.** Still tractable for one session.

---

## 5. Files to touch

All changes are additive and local to the matrix script. **Zero touches to `server/code/api/routers/extract.py`.** Zero touches to the live eval harness `scripts/run_question_bank_extraction_eval.py`. The matrix rides on top via a new diagnostic-only script.

### 5a. New files

- **`scripts/run_section_effect_matrix.py`** — new standalone diagnostic script, ~200 LOC. Modeled after `scripts/run_stubborn_pack_eval.py` (same pattern: load cases JSON, POST /extract/fields, collect, emit JSON + console). Key differences:
  - Accepts `--cases case_008,case_018,case_082` (default = that pack).
  - Accepts `--variants V1,V2,V3,V4,V5,V6` (default = all).
  - Accepts `--runs 4` (default). `--api http://localhost:8000` (default).
  - For each (case, variant) pair, builds the payload by taking the case's baseline payload (the exact dict `run_question_bank_extraction_eval.py` builds at L687–703) and overriding the 5 stage fields per the variant table.
  - Writes `docs/reports/section_effect_matrix_<tag>_<case>_<variant>_run<N>.json` per run and a consolidated `docs/reports/section_effect_matrix_<tag>_summary.json` + `.console.txt` at the end.
  - Consolidated summary includes: per-(case, variant) emission-path set, emission-count distribution, shape-change flag across the 4 runs, and a cross-variant comparison matrix.
  - Re-uses `score_case` from the eval harness for per-variant scoring so the pass/fail axis is apples-to-apples with the master.

- **`docs/reports/WO-EX-SECTION-EFFECT-01_CAUSAL.md`** — the final short readout. One page, not a dissertation. Sections: §1 Question/hypothesis/method, §2 Per-case matrix table (one table per case), §3 Rollup answers to the three attribution questions, §4 Decision gate (see §8 below), §5 Revision history.

### 5b. Read-only references (script imports)

- `scripts/run_question_bank_extraction_eval.py` — import `score_case`, `_phase_to_era`, `_confidence_stats`, `_stubborn_partition_for`. These are module-level functions and are reusable without refactor.
- `data/qa/question_bank_extraction_cases.json` — case source, read-only.
- `.runtime/logs/api.log` — optional: grep `[extract][turnscope]` lines per run for attribution sanity-checks.

### 5c. Files that must NOT change

- `server/code/api/routers/extract.py` — any change here invalidates the matrix (you'd be measuring the new code, not the current behavior).
- `scripts/run_question_bank_extraction_eval.py` — the master is the decision gate for everything else; don't perturb it to satisfy a diagnostic lane.
- `data/qa/question_bank_extraction_cases.json` — don't re-adjudicate during Phase 3. If matrix findings suggest a re-adjudication is warranted, file it as a Phase 4 or a follow-up, separate commit.

---

## 6. Acceptance criteria

A Phase 3 deliverable is considered complete when **all** of:

1. **Matrix ran clean.** 72 extractions (3 cases × 6 variants × 4 runs) completed; zero HTTP errors, zero timeouts, zero `method=error_*`. If the stack hiccupped on a run, re-run that specific (case, variant, run) slot; do not half-report.
2. **Per-case matrix table filed** in `WO-EX-SECTION-EFFECT-01_CAUSAL.md` §2, with columns: variant, era, pass, mode, section, target_path, emitted fieldPaths (set), emission_count (4-run median), method (4-run modal), pass@alt_defensible, shape_change_across_runs (bool).
3. **Attribution Q1 answered** (varying era/pass/mode when target fixed): Yes / No / Indeterminate with evidence in the form of a signed count of path-set differences across V1 vs V2/V3/V4.
4. **Attribution Q2 answered** (varying target_path when section fixed): Yes / No / Indeterminate from V1 vs V6.
5. **Attribution Q3 answered** (baseline scatter when stage context stripped): Yes / No / Indeterminate from V1 vs V5.
6. **Decision gate called** per §8. One of: ADOPT, PARK, ITERATE, ESCALATE.
7. **CLAUDE.md current-phase block updated** with the answer and the decision. Task #95 closed, task #63 closed (it has been the umbrella for this whole WO).
8. **Matrix JSON + script committed** to the repo so the measurement is reproducible.

If any of 1–5 fails the gate check in §8 triggers ITERATE — don't force a premature ADOPT.

---

## 7. Guard cases — what not to conclude from the matrix

Phase 3 is a **small-n** study with n=4 per cell. Things it cannot conclude:

- **"era has no effect."** n=4 is insufficient to claim null. The correct claim is "era did not produce a path-set change > the run-to-run stochastic variance on this pack." Write it that way.
- **"SPANTAG will flip case_008."** SPANTAG is a different lever (explicit dual-path emission). The matrix only tells you whether stage context *could* be the lever. If Q1 answers No, it's evidence SPANTAG's path-binding has to carry the load; not evidence SPANTAG will work.
- **"The truncation frontier moves with stage context."** The matrix deliberately excludes the 7 truncation-starved cases. Any claim about dense genealogy has to come from #96 / WO-EX-TRUNCATION-LANE-01, not this report.
- **Cross-run noise = stage-effect noise.** If V1-run1 and V1-run2 disagree by a wider margin than V1 vs V2, that's a stability floor finding — call it out as its own bullet, not a null result on stage context.

Document these guards explicitly in `WO-EX-SECTION-EFFECT-01_CAUSAL.md` §1 so the reader does not over-interpret.

---

## 8. Decision gate (how the report ends)

After filling the matrix and answering Q1/Q2/Q3, call one of four dispositions:

### ADOPT — stage context is load-bearing

- Q1 = Yes (era/pass/mode flips emission shape when target is held) AND Q3 = Yes (stripping stage context degrades toward scatter).
- Action: SPANTAG Pass 2 should consume era/pass/mode as **explicit controlled priors** (already in `WO-EX-SPANTAG-01_Spec.md` §Pass 2 design). Matrix is evidence the design is justified.
- Follow-up: file an observability ticket to surface era/pass/mode in the existing `[extract][summary]` log lines if they're not already (Phase 2 landed that; confirm it held through r5e1).

### PARK — stage context carries signal but not shape

- Q1 = No, Q3 = Yes (stripping stage helps the catalog-scatter case but era/pass/mode alone doesn't flip paths).
- Action: SPANTAG Pass 2 should keep `current_section` and `current_target_path` as its controlled priors, but treat era/pass/mode as **observability-only** fields — log them, don't weight them. Drop era/pass/mode from SPANTAG's Pass 2 prompt if it adds token cost without lift.
- Follow-up: none. Phase 3 closes clean.

### ITERATE — signal is below run-noise floor

- Cross-run variance (V1 run1 vs V1 run2) > cross-variant variance (V1 vs V2/3/4). We cannot make any claim without more n.
- Action: re-run with n=8 per cell (144 extractions total) after Chris signs off on the cost. If n=8 is still indeterminate, call PARK by default — the signal is too weak to justify SPANTAG Pass 2 paying for era/pass/mode.

### ESCALATE — matrix surfaces a new failure mode

- Any variant produces a categorically novel emission (new wrong_entity_bind class, silent-drop where baseline emits, etc.) that wasn't in the Phase 1 adjudication.
- Action: stop Phase 3 closeout. File a sibling WO describing the new failure. SPANTAG and the decision gate above are both deferred until the new mode is understood.

Chris signoff required for ADOPT / PARK / ITERATE / ESCALATE before SPANTAG Pass 2 consumes the finding.

---

## 9. Report format — exact contents of `WO-EX-SECTION-EFFECT-01_CAUSAL.md`

```
# WO-EX-SECTION-EFFECT-01 Phase 3 — Causal matrix readout

**Author:** <author>
**Date:** <date>
**Source run tag:** <tag>   # e.g. se_matrix_r5e1_20260422
**Pack:** case_008, case_018, case_082
**Stack state:** <r5e1 floor, HORNELORE_NARRATIVE=1, HORNELORE_ATTRIB_BOUNDARY=0>

## 1. Question, method, guards

(two paragraphs: what Q1/Q2/Q3 are asking, how the matrix answers, what
the matrix CANNOT tell us — copied from §7 of this WO verbatim is fine.)

## 2. Per-case matrix

### case_008

| Variant | era | pass | mode | section | target_path | emitted (4-run union) | emission_count (median) | method (modal) | pass@alt | shape_change |
|---|---|---|---|---|---|---|---|---|---|---|
| V1 | ... |
| V2 | ... |
| V3 | ... |
| V4 | ... |
| V5 | ... |
| V6 | ... |

### case_018

(same shape)

### case_082

(same shape)

## 3. Attribution answers

- **Q1 (era/pass/mode effect when target held):** YES | NO | INDETERMINATE.
  Evidence: <signed count of path-set diffs V1 vs {V2,V3,V4}>.
- **Q2 (target_path effect when section held):** YES | NO | INDETERMINATE.
  Evidence: <V1 vs V6>.
- **Q3 (stage-strip degrades to scatter):** YES | NO | INDETERMINATE.
  Evidence: <V1 vs V5>.

## 4. Decision

**Disposition:** ADOPT | PARK | ITERATE | ESCALATE

**Reasoning:** <one short paragraph>

**Follow-ups:** <bulleted>

## 5. Revision history

- <date>: Phase 3 matrix ran; disposition called.
```

No long narrative. The decision is the load-bearing part; the table is the evidence.

---

## 10. Post-eval audit block (required)

On matrix completion, emit this to chat / stand-up:

- 72 extractions: all clean | N retries
- Per-case V1 score vs master r5e1 baseline (smoke test: V1 should ≈ master)
- Q1 / Q2 / Q3 YES/NO/IND
- Decision: ADOPT | PARK | ITERATE | ESCALATE
- Any ESCALATE triggers — if yes, link the sibling WO that caught it
- Task state: #95 closed, #63 closed

---

## 11. Sequencing

- Phase 3 can run anytime the stack is up and r5e1 floor is locked. It does not require the SECTION-EFFECT Phase 2 payload to be surfaced in UI — it only requires the payload to round-trip in logs and back in the response. That is already true as of #93.
- Phase 3 should run **before** SPANTAG Pass 2 eval lands, so SPANTAG's measurement #10 has a citable source. If SPANTAG Pass 2 code ships first, that's fine; we can still back-fill the eval report with Phase 3's answer.
- Phase 3 is **not** a prerequisite for the SPANTAG default-on/off decision. The SPANTAG decision is driven by SPANTAG Pass 2's own eval on the 4-case dual-answer pack. Phase 3 is supporting evidence, not the gate.

---

## 12. Related work

- `WO-EX-SECTION-EFFECT-01_Spec.md` — parent spec.
- `docs/reports/WO-EX-SECTION-EFFECT-01_ADJUDICATION.md` — Phase 1 output; source of the case pack and the `dual_answer_defensible` label set.
- `WO-EX-SPANTAG-01_Spec.md` — downstream consumer of the Phase 3 disposition.
- `scripts/run_stubborn_pack_eval.py` — template for the new matrix script.
- `scripts/run_question_bank_extraction_eval.py` L628 / L683–703 / L791 (`_phase_to_era`) — payload synthesis to copy.

---

## 13. Revision history

- 2026-04-21: Drafted as execution pack for task #95. Matrix shape finalized at 3 cases × 6 variants × 4 runs = 72 extractions. Decision gate formalized (ADOPT / PARK / ITERATE / ESCALATE). Case_009 excluded from pack on purpose (wrong axis for this matrix).
