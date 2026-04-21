# LOOP-01 R5.5 — Weekly Work Order Checklist (Apr 21–27, 2026)

**Written:** Tuesday 2026-04-21 · **Author:** Claude (working with Chris)
**Live baseline:** r5d = 58/104, v2=30/62 · **Locked floor:** r4i = 55/104, v2=30/62
**Active decision:** r5e master eval in flight; scoring on return

This is the chronological plan for the rest of the week. Extractor lane stays primary; UI work is gated behind STT-LIVE-02 browser verification and r5e adoption.

---

## Standing rules (from CLAUDE.md)

- Chris owns stack start/stop (cold boot ~4 min).
- Agent reads logs/reports directly from the workspace mount; no paste-backs.
- Every eval after a code change gets the standard audit block: total / v2 / v3 / must_not_write / named flips / scorer-drift audit on every flip.
- Git is not accessible from sandbox — commit/branch/log commands go to Chris as copy-paste blocks.

---

## Tuesday — April 21 (today, in progress)

### Extractor lane

- [x] Phase 2 narrative tighten landed (commits `3fec639`, `9706a87`)
- [x] CLAIMS-02 role-exempt landed (commit `291cbb8`)
- [x] Phase 3 Fix A scorer alias landed (commit `77e5b52`)
- [x] Phase 3 Fix C date-range + role-abbrev fewshot landed (commit `74f7b0d`)
- [x] Code review of 5 stacked commits — verdict: clean, no lurking bugs
- [x] CLAUDE.md changelog + Current-phase block updated
- [x] WO-EX-NARRATIVE-FIELD-01_REPORT.md drafted with Phase 4 results stub
- [ ] **r5e master eval completes** (Chris kicks off on warm stack)
- [ ] Score r5e: topline / v2 / v3 / must_not_write / named flips
- [ ] **Scorer-drift audit on every flip** — attribute each flip as `extraction_change` vs `scorer_credit` (Fix A is the only measurement-side change; focus on `.role` flips)
- [ ] Fill in Phase 4 results section of WO-EX-NARRATIVE-FIELD-01_REPORT.md
- [ ] Call decision gate: **ADOPT** / **ADOPT-WITH-CAVEAT** / **ITERATE** / **REJECT**

### Decision gate rules

- **ADOPT** (flag default-on): ≥ +2 topline gains vs r5d AND 0 regressions AND case_040 OR case_049 green
- **ADOPT-WITH-CAVEAT**: +1 topline with regressions explained by scorer drift (not extraction)
- **ITERATE**: net-neutral flips or scorer-drift audit shows Fix A is doing all the work
- **REJECT**: topline below r5d floor (58/104) with no attribution story

### Close or iterate

- [ ] Tasks #115, #116, #117 → completed (if ADOPT) or → in_progress with next-step note (if ITERATE)
- [ ] Commit report updates via Chris (copy-paste block)

---

## Wednesday — April 22

### Depends on r5e outcome

**If ADOPT or ADOPT-WITH-CAVEAT:**

- [ ] `HORNELORE_NARRATIVE=1` promoted to default-on in `.env` (Chris does)
- [ ] NARRATIVE-FIELD-01 closed in CLAUDE.md
- [ ] Move to #119 — turnscope `allowed_branches` fix for greatGrandparents subtree. Small surgical patch. Quick targeted smoke + master r5f to confirm.

**If ITERATE:**

- [ ] Diagnose r5e regressions (likely scalar co-emission over-firing or date-range rule missing)
- [ ] Targeted smoke on regressed cases (no full master until smoke flips green)
- [ ] r5e' rerun after patch

**If REJECT:**

- [ ] Revert the 5-commit stack (or the offending subset) back to r5d/r5a state
- [ ] Reopen NARRATIVE-FIELD-01 Phase 2 design with three-agent input

### Parallel tracks (Chris)

- [ ] **STT-LIVE-02 browser round-trip verification** (#99 completion)
  - Open Hornelore in Chrome, start interview, speak, confirm:
    - `ui/js/transcript-guard.js` populates `state.lastTranscript` on `recognition.onresult`
    - Fragile-fact classifier fires for narrator identity / spouse / parents / siblings
    - `[extract] Attempting` log line shows `stt_src=mic_min_over_segments`, `stt_conf=<num>`, `confirm_req=<bool>`
    - Clarification envelope dispatches when `confirmation_required=True`
  - File: `docs/reports/WO-STT-LIVE-02_VERIFICATION.md` short memo with PASS/FAIL per checkpoint

### SECTION-EFFECT Phase 3 prep

- [ ] Design causal matrix spec — pick 2-3 stubborn cases (likely `case_008`, `case_009`, `case_082`), vary `currentEra` / `currentPass` / `currentMode` combinatorially (3×3×2 = 18 cells, or narrow to 6 cells on the diagonal)
- [ ] Write matrix harness — either extend `run_stubborn_pack_eval.py` or new standalone
- [ ] Output: `docs/reports/WO-EX-SECTION-EFFECT-01_CAUSAL.md` (path already reserved in CLAUDE.md file table)

---

## Thursday — April 23

### SECTION-EFFECT Phase 3 execution

- [ ] Land causal matrix harness
- [ ] Run matrix against r4i baseline (or r5e+NARRATIVE if ADOPT landed)
- [ ] Analyze: which stage-context axis (era / pass / mode) actually shifts extraction on the stubborn cases?
- [ ] If clean causal signal found → SECTION-EFFECT-01 closes, unblocks SPANTAG
- [ ] Close task #95, #63 → completed
- [ ] Update CLAUDE.md: SPANTAG moves from blocked to active

### Contingency: if r5e still iterating

- [ ] Postpone Phase 3 causal matrix to Friday
- [ ] Focus on getting NARRATIVE-FIELD signed off before opening a new lane

---

## Friday — April 24

### One of two paths

**Path A — SPANTAG implementation (preferred if SECTION-EFFECT Phase 3 closed Thursday):**

- [ ] Audit existing SPANTAG scaffold (Pass 1 = commit from #90, Pass 2 scaffold = #103)
- [ ] Fill in Pass 2 bind/project logic with explicit controlled priors (`current_section` / `current_target_path` / `currentEra` / `currentPass` / `currentMode`)
- [ ] Implement subject-beats-section rule
- [ ] Implement dual-path emission
- [ ] Flag behind `HORNELORE_SPANTAG=1`, off by default — byte-stability with current path
- [ ] Commit as WO-EX-SPANTAG-01 Commit 3

**Path B — WO-12A Lite (if STT-LIVE-02 browser verification is GREEN and SPANTAG isn't unblocked):**

- [ ] Two read-only header status indicators (`#hdrMicStatus`, `#hdrCamStatus`)
- [ ] Single render helper `renderCaptureStatusIndicators()` in `app.js`
- [ ] Hook into recognition start/stop/error + camera start/stop/permission paths
- [ ] Styling: inactive / active / blocked via classes
- [ ] Acceptance: mic truth / camera truth / blocked-state truth / STT-LIVE-02 preserved
- [ ] ~1-2 hour job; do NOT touch `toggleRecording()`, Focus Canvas interception, or perm toggles

**Do NOT do Path B until STT-LIVE-02 browser verification has passed.** The files overlap (`app.js`, `state.js`) and attribution breaks if both are in motion.

---

## Weekend — April 25 (Sat) & April 26 (Sun)

Low-bandwidth, no blocking work. Pick any of these as energy allows:

### Documentation/writing

- [ ] Update `WO-EX-SPANTAG-01_Spec.md` if Pass 2 assumptions changed after SECTION-EFFECT Phase 3 results
- [ ] Close stale tasks in the task tree (sweep completed items, delete any never-run)
- [ ] Update `POST-R4-BASELINE-LOCK.md` footer with r5e adoption decision

### Canon/eval corpus

- [ ] #111 — expand canon-grounded corpus toward ~24 cases (in_progress). Light additions only; no structural changes.
- [ ] #110 already closed (Kent occupation canon); verify no template regressions surfaced in last 2 weeks

### Reading/prep (no-code)

- [ ] Review #96 Truncation Lane Spec draft for Monday discussion
- [ ] Review #97 alt_defensible_values spec (075, 088 only)

### Do NOT do on weekend

- Live extractor evals (no master runs, save GPU)
- Multi-file refactors
- Anything requiring Chris to restart the stack

---

## Monday — April 27

### SPANTAG first eval

- [ ] Run stubborn-pack eval against SPANTAG on the **4-case primary sub-pack** from SECTION-EFFECT Phase 1 adjudication (case_008, case_009, case_018, case_082 per the `alt_defensible_paths` patches)
- [ ] Score against adjudicated labels
- [ ] Decision: does SPANTAG move the needle on the 4-case pack?
  - ≥ 2 flips → promote to full stubborn-15 eval
  - 0-1 flips → diagnose, iterate, or park

### If SPANTAG doesn't unblock

- [ ] Reopen full WO-12A review with new context
- [ ] Or pivot to #96 truncation lane work

---

## Open WOs — status at top of week

| # | WO / Task | Status | Gate |
|---|---|---|---|
| 116 | NARRATIVE-FIELD Phase 4 eval | IN PROGRESS | r5e result today |
| 117 | NARRATIVE-FIELD final report | PENDING | Phase 4 close |
| 115 | Phase 3 scorer alias relax | PENDING | Phase 4 close |
| 99 | STT-LIVE-02 | IN PROGRESS | Browser round-trip (Chris) |
| 63/95 | SECTION-EFFECT Phase 3 | IN PROGRESS | Phase 2 landed; Phase 3 causal matrix next |
| 119 | turnscope greatGrandparents | PENDING | Small surgical; Wed or Thu |
| 90 | SPANTAG-01 | PAUSED | Unblocks after #95 |
| 96 | Truncation lane spec | PENDING | Not active; reading this week |
| 97 | alt_defensible_values (075, 088) | PENDING | Not active |
| 111 | Canon-grounded corpus expansion | IN PROGRESS | Weekend low-priority |
| 124 | case_049 tighten | IN PROGRESS | Closes with Phase 4 adoption |

## Closed / deferred

- **#72 TURNSCOPE** — closed (r4h)
- **#67 PATCH-H-DATEFIELD** — closed (r4i)
- **#68 case_053 wrong-entity** — deferred R6
- **#81 PROMPTSHRINK** — measured, not adopted; flag in-tree
- **#35 V4 scope axes** — backlog, R6
- **Full WO-12A** — deferred; reopen only after STT-LIVE-02 + extractor sequence complete. If WO-12A Lite solves the trust problem, full WO-12A may be downgraded or deleted.

---

## Sequencing rationale (why this order)

1. **r5e tonight, nothing else today.** 5 commits stacked for one measurement; we already took the attribution risk — finish scoring before opening anything new.
2. **STT-LIVE-02 browser verify Wed.** Required before any `app.js` / `state.js` / `interview.js` work can start attribution-clean. Chris owns this.
3. **SECTION-EFFECT Phase 3 Thu.** This is the real bottleneck — SPANTAG can't ship without the causal matrix. Do not let UI work distract from this.
4. **SPANTAG Fri OR WO-12A Lite Fri.** If Phase 3 unblocks SPANTAG, extractor gains momentum — stay on that lane. If not, WO-12A Lite is a clean low-risk 1-hour palate cleanser (but only if STT-LIVE-02 is verified first).
5. **Weekend = writing and corpus, not code.** Save the GPU, save Chris's focus. The next active code block is Monday.
6. **Full WO-12A deferred, not dead.** Reopen only with evidence that Lite didn't fix the trust problem, and only when no extractor WO is mid-flight.

## Risk register for the week

- **Highest**: r5e lands with unattributable flips (mix of extraction and scorer credits). Mitigation: scorer-drift audit is already scripted in the report stub; run it strictly.
- **High**: STT-LIVE-02 browser verify surfaces a real bug. Mitigation: revert path is clean; `transcript_guard.js` is a standalone IIFE, easy to disable.
- **Medium**: SECTION-EFFECT Phase 3 causal matrix shows no clean signal. Mitigation: SPANTAG can still ship with best-available priors; the matrix is validation, not a blocker in principle.
- **Low**: SPANTAG Pass 2 implementation slips past Friday. Mitigation: Monday Apr 27 already reserved for first eval; one day slip doesn't cascade.

---

*This checklist lives at `docs/reports/LOOP-01_R5.5_WEEKLY_CHECKLIST_20260421.md`. A copy is at `Desktop/Horne/WEEKLY_CHECKLIST_20260421.md`. Update both when decisions land.*
