# Master Work Order Checklist — LOOP-01 R4 cleanup

**As of:** 2026-04-19
**Baseline:** r4h post-TURNSCOPE close. 53/104 pass, v3 32/62, must_not_write 0%.
**Next physical action:** Chris runs **r4i** live eval. Everything else is blocked on that or on #81 signoff.

---

## Phase A — close #67 (case_011 date un-normalisation)

Code + tests + report all in-tree. Needs eval confirmation.

- [x] Three-edit fix to `server/code/api/routers/extract.py` (suffix set + holiday map + regex).
- [x] `tests/test_extract_holiday_normalisation.py` — 40 tests, 5 classes, green.
- [x] `docs/reports/WO-EX-PATCH-H-DATEFIELD-01_REPORT.md` — root cause + expected r4i deltas.
- [ ] **#84 — Chris runs r4i eval.** Standard block from `CLAUDE.md`. Output: `docs/reports/master_loop01_r4i.json`.
- [ ] Verify case_011 flips 0.50 → 1.00; topline 53 → 54/104; must_not_write stays 0%; no regressions on case_094/060/062/null_clarify suite.
- [ ] Watch case_012 and case_020 as noise controls. If they flip back to pass, confirms r4g→r4h drift was stochastic.
- [ ] **#85 — Commit #67** (extract.py + test file + WO report as one change). Only after eval passes.
- [ ] Tick last two boxes in `WO-EX-PATCH-H-DATEFIELD-01_REPORT.md` closeout checklist.
- [ ] Update `CLAUDE.md` current-phase block to move past #67.

## Phase B — close out #68 (case_053 wrong-entity)

Disposition written. Needs a re-check after r4i.

- [x] `docs/reports/WO-CASE-053-DISPOSITION.md` — defer to R5 Pillar 2, three tactical fixes explicitly rejected.
- [ ] After r4i lands: re-check case_053. Two outcomes to handle:
  - **Still fails same way** → disposition stands; no code change; mark #68 deferred-to-R5 and move on.
  - **Flips to pass** → verify with a tighter adversarial case (word order reversed) before counting the win. R5 Pillar 2 still needs to land regardless.

## Phase C — #81 WO-EX-PROMPTSHRINK-01

Spec drafted. Blocked on Chris signoff before any code lands.

- [x] `WO-EX-PROMPTSHRINK-01_Spec.md` — three workstreams (A: catalog scoping, B: few-shot prune, C: structured catalog presentation), ablation plan, measurement plan.
- [ ] **#86 — Chris signoff on 4 open questions** in the spec:
  - [ ] (1) Always-on-core list scope: identity-only, or include common relational roots?
  - [ ] (2) Branch-sibling inclusion rule: full branch, or just sibling-of-target?
  - [ ] (3) `extractPriority=None` fallback: full catalog, or phase-based scoping?
  - [ ] (4) Ablation ordering: A-first (as drafted) or B-first?
- [ ] Implement Workstream A — `_scope_catalog_for_targets()` + wire into `_build_extraction_prompt`. Eval `r4j-a`.
- [ ] Implement Workstream B — audit api.log for few-shot usage, prune 33 → ~18–22, archive dropped few-shots as commented block. Eval `r4j-ab`.
- [ ] Implement Workstream C — per-branch structured catalog presentation. Eval `r4j-abc`.
- [ ] Final WO report `docs/reports/WO-EX-PROMPTSHRINK-01_REPORT.md` with 4-way comparison table (r4i → r4j-a → r4j-ab → r4j-abc).

## Phase D — #63 should_pass drift audit

Parallel to #81. Low-churn, can be started any time after r4i lands.

- [ ] Grep `docs/reports/master_loop01_*.json` for cases where `should_pass` prediction diverges from actual pass across runs.
- [ ] Retag `guard_false_positive` category → `scope_escape` now that #72 is closed.
- [ ] Short audit doc in `docs/reports/` if patterns emerge.

## Phase E — freeze post-R4 baseline + #82 memo

Blocked on #67, #68 disposition, #81, #63 all resolved.

- [ ] Confirm master eval pass rate + per-axis scores are stable across 3 consecutive runs.
- [ ] Declare baseline frozen in `CLAUDE.md` changelog.
- [ ] **#82 — Write post-R4 memo + R5.5 citation-grounding spec.** Memo includes:
  - [ ] Per-axis R2/R3/R3b/R4 deltas with keep/rollback calls.
  - [ ] Case_053 + case_068 + case_088 as R5 Pillar 2 reference suite.
  - [ ] Related-work paragraph: Kiwi-LLaMA (Hu et al., JAMIA 2026) + KORIE (Kasem et al., Mathematics 2026).
  - [ ] Hermes 3 A/B hypothesis as a model-swap candidate — evidence from KORIE (Qwen2.5-3B tying Llama-3.1-8B at 25% F1) that newer-instruction-tuning closes ground.
- [ ] R5.5 citation-grounding spec, consuming the span-tag primitive queued in Phase F.

## Phase F — R5.5 execution (after freeze)

Not in active queue. Stub landed so the idea doesn't rot.

- [x] `WO-EX-SPANTAG-01_Spec.md` stub — deferred, parked for R5.5. Framed as provenance primitive, not hallucination cure. Four open questions inside.
- [ ] After #81 ships: revisit SPANTAG stub's open questions (class naming, catalog interaction, emission shape, scorer path).
- [ ] Decide: ship span-tag output contract as the R5.5 primitive, or stick with JSON + an offset-map sidecar.

## Deferred / backlog

- [ ] **#35** — V4 eval scope (log density + intent-class + topic-shift axes). Not R4 scope. Revisit post-freeze.
- [ ] **WO-EX-NORMALIZE-EXPAND-01** (unwritten) — extend Patch H's write-time normalization pattern to phone/address/other format-sensitive fields. Low-priority cleanup, not an R4 blocker. KORIE §4.3.4 supports the pattern.

---

## Standing reminders

- Chris runs / stops the API himself. Don't include `start_all.sh` or `stop_all.sh` in command blocks.
- Every eval that follows a code change must report the standard post-eval audit block from `CLAUDE.md`.
- Each WO must report the audit block before being called done.
- When three agents (Claude/Gemini/ChatGPT) converge, act — don't re-argue.

---

## Quick file reference

| Kind | Path |
|---|---|
| Active spec: #81 | `WO-EX-PROMPTSHRINK-01_Spec.md` |
| Parked stub: R5.5 | `WO-EX-SPANTAG-01_Spec.md` |
| Report: #67 | `docs/reports/WO-EX-PATCH-H-DATEFIELD-01_REPORT.md` |
| Memo: #68 | `docs/reports/WO-CASE-053-DISPOSITION.md` |
| Report: #72 (closed) | `docs/reports/WO-EX-TURNSCOPE-01_REPORT.md` |
| Tests: #67 | `tests/test_extract_holiday_normalisation.py` |
| CLAUDE.md | `CLAUDE.md` |
