# LOOP-01 R5.5 — Weekly Work Order Checklist (Apr 21–27, 2026)

**Written:** Tuesday 2026-04-21 · **Author:** Claude (working with Chris) · **Last updated:** Tuesday 2026-04-21 (late evening)
**Clean floor:** r5d = 58/104, v2=30/62, must_not_write=0 · **Locked floor:** r4i = 55/104, v2=30/62
**r5e status:** REJECTED — 57/104, v3=35/62, v2=29/62, must_not_write=**2** (case_035, case_066).
**r5e1 status:** MEASURED (partial recovery) — 59/104, v3=38/62, v2=32/62, must_not_write=**2** (case_035, case_093). Surgical removal of NARRATOR-IDENTITY PRIORITY rule. Path: ITERATE chosen over ADOPT because of persistent mnw=2.
**r5e2 status:** MASTER EVAL RUNNING (late evening). ATTRIBUTION-BOUNDARY education-scope rule added (commits `bfefe8b`, `c24efa9`) targeting the 2 forbidden-write violations. 2-case smoke: mnw=0 both cases ✓ · case_093 pass at 0.90 · case_035 plateaued at 0.50 (`parents.education` hallucination persists — root cause: schema table L327 contradicts prompt rule). Master is the systemic-impact gate.

This is the chronological plan for the rest of the week. Extractor lane stays primary; UI work is gated behind STT-LIVE-02 browser verification and r5e adoption.

---

## Standing rules (from CLAUDE.md)

- Chris owns stack start/stop (cold boot ~4 min).
- Agent reads logs/reports directly from the workspace mount; no paste-backs.
- Every eval after a code change gets the standard audit block: total / v2 / v3 / must_not_write / named flips / scorer-drift audit on every flip.
- Git is not accessible from sandbox — commit/branch/log commands go to Chris as copy-paste blocks.

---

## Tuesday — April 21

### Extractor lane — morning

- [x] Phase 2 narrative tighten landed (commits `3fec639`, `9706a87`)
- [x] CLAIMS-02 role-exempt landed (commit `291cbb8`)
- [x] Phase 3 Fix A scorer alias landed (commit `77e5b52`)
- [x] Phase 3 Fix C date-range + role-abbrev fewshot landed (commit `74f7b0d`)
- [x] Code review of 5 stacked commits — verdict: clean, no lurking bugs
- [x] CLAUDE.md changelog + Current-phase block updated
- [x] WO-EX-NARRATIVE-FIELD-01_REPORT.md drafted with Phase 4 results stub

### Extractor lane — afternoon (r5e measurement)

- [x] r5e master eval completed (Chris, warm stack)
- [x] Scored r5e: **57/104, v3=35/62, v2=29/62, must_not_write=2** (case_035, case_066)
- [x] Diff vs r5d: **9 new green** (incl. case_049 Phase 2 target ✓), **10 new red** (7 of 10 dropped 1.00 → 0.50/0.00)
- [x] Scorer-drift audit: 0 of 10 reds involve `.role` fields → Fix A not credited for damage. Extraction-side regression, prompt-layer over-fire.
- [x] Three-agent convergence (Claude / ChatGPT / Chris): **REJECT r5e**. Floor breached; priority-rule "MUST/NEVER" language implicated.
- [x] r5e artifacts banked as commit `0bef492`

### Extractor lane — evening (r5e1 attribution + r5e2 boundary)

- [x] Attempt `git revert 9706a87` → conflict with Fix C (landed on top). Aborted cleanly.
- [x] Surgical edit instead: remove NARRATOR-IDENTITY PRIORITY rule block only. Preserve SCALAR CO-EMISSION v1 + amendment + Fix C. Commit `d2cfb31`.
- [x] r5e1 master eval completed (Chris, warm stack)
- [x] r5e1 scored: **59/104, v3=38/62, v2=32/62, must_not_write=2** (case_035 `education.schooling` + case_093 `education.higherEducation`)
- [x] Three-agent convergence: ITERATE (not ADOPT, not REJECT) — better extraction than r5d but mnw still at 2
- [x] r5e1 artifacts banked as commit `ad52e4a` (+ weekly checklist updates)

### Extractor lane — late evening (r5e2 attribution-boundary build)

- [x] 2-case forbidden-write audit on case_035 + case_093 → converged attribution-boundary diagnosis (education.* is narrator-only; both cases route non-narrator schooling to narrator-scope fields)
- [x] ATTRIBUTION-BOUNDARY rule landed behind `HORNELORE_NARRATIVE=1` (commit `bfefe8b`) — 4-exemplar block (faith-thematic + mother-detail + spouse-follow-up + narrator-owned control); inserted after DATE-RANGE PREFERENCE in `_NARRATIVE_FIELD_FEWSHOTS`
- [x] 2-case smoke r5e2: **mnw=0 both cases** ✓ · case_093 PASS at 0.90 ✓ · case_035 PARTIAL at 0.50 — `education.schooling` cleared but `faith.significantMoment` missing and LLM improvised invalid path `parents.education`
- [x] Faith exemplar retighten (commit `c24efa9`): added path-validity negation ("parents.education does not exist") + explicit thematic-turn preference
- [x] 1-case re-smoke on case_035: still 0.50, mnw=0 held, `parents.education` hallucination PERSISTS. Root cause traced: `parents.education` IS in schema table L327 (`writeMode: suggest_only`), so prompt rule contradicts schema. Alias L3711 exists (→ `parents.notableLifeEvents`) but fires post-scoring.
- [x] Three-agent convergence: run r5e2 master to measure systemic impact despite case_035 plateau
- [ ] **r5e2 master eval running** (Chris, warm stack)
- [ ] Score r5e2 per ChatGPT-sharpened audit (below)
- [ ] Decision gate (below)

### r5e2 post-master audit block (standard + specific)

Standard: total pass / v2 contract / v3 contract / must_not_write count / named flips (every pass↔fail) / scorer-drift audit on every flip / truncation rate.

Specific to r5e2:
- **`parents.education` drift audit**: grep raw_items across all 104 cases for `parents.education` emissions. If only case_035 → contained carryover. If ≥3 other cases → systemic schema-drift introduced by r5e2.
- **case_093 retention**: does it hold as PASS at master scale?
- **case_035 non-regression**: stays at 0.50 (no return to `education.schooling`)
- **case_049 fragility watch**: known to swing across runs
- **case_020 path-drift watch**: persistent drift case
- **case_005 volatility watch**: has swung hard recently

### r5e2 decision gate (tonight or tomorrow morning)

- **ADOPT r5e2** (strong): **total ≥ 60/104 AND mnw == 0 AND v3 ≥ 38 AND v2 ≥ 32 AND `parents.education` offenders ≤ 1 (case_035 only) AND case_093 stays green**
- **ADOPT r5e2** (bank-it): total ∈ [59, 60] AND mnw == 0 AND v3 ≥ 38 AND v2 ≥ 32. case_035 may stay at 0.50; acceptable.
- **ITERATE r5e2b/c**: mnw == 1 OR `parents.education` appears on ≥3 new cases (systemic drift) — triage the leak, decide between (a) hard-delete schema entry L327, (b) fix alias ordering, (c) extractor-layer attribution filter
- **REJECT r5e2**: total < 58 OR mnw ≥ 2 OR v3 < 38 OR v2 < 32 — roll back `bfefe8b`+`c24efa9`, r5e1 stays floor

### Close or iterate

- [ ] Tasks #115, #116, #117 → completed (if ADOPT) or → in_progress with next-step note (if ITERATE / REJECT)
- [ ] Fill in Phase 4 results section of WO-EX-NARRATIVE-FIELD-01_REPORT.md with r5e + r5e1 + r5e2 numbers + carryover list (case_035 parents.education, faith.significantMoment routing, family.children.* sister misroute)
- [ ] Commit report + master artifacts via Chris (copy-paste block)

---

## Wednesday — April 22

### Depends on r5e2 outcome (measured overnight or first thing Wed)

**If ADOPT r5e2 (strong or bank-it):**

- [ ] `HORNELORE_NARRATIVE=1` promoted to default-on in `.env` (Chris does)
- [ ] NARRATIVE-FIELD-01 closed in CLAUDE.md
- [ ] File carryover items as separate backlog tasks:
  - case_035 `parents.education` schema contradiction → new WO or #115-adjacent
  - case_035 `faith.significantMoment` thematic routing → R5.5 Pillar 2 or SPANTAG territory
  - `family.children.*` sister-to-children misroute → pre-existing bug, R6 relation-router work
- [ ] Move to #119 — turnscope `allowed_branches` fix for greatGrandparents subtree. Small surgical patch. Quick targeted smoke + master r5f to confirm.

**If ITERATE (r5e2b/c — mnw leaked or parents.education systemic):**

- Single triage decision before committing any code:
  - If mnw leaked back in on any new case → diagnose which (not case_035/093), then targeted fix
  - If `parents.education` ≥3 new cases → hard-delete schema entry L327 (safest first move, alias L3711 catches stragglers). Commit + targeted smoke on affected cases + master rerun as r5e2b
- [ ] r5e2b master rerun after fix+smoke

**If REJECT r5e2:**

- [ ] Revert `bfefe8b` + `c24efa9` (two-commit revert, no conflicts expected)
- [ ] r5e1 stays floor (59/104, mnw=2)
- [ ] NARRATIVE-FIELD-01 paused at r5e1 pending deeper redesign (extractor-layer attribution filter is the likely next move, not prompt iteration)

### Parallel tracks (Chris — if r5e2 adopted or running independently)

- [ ] **STT-LIVE-02 browser round-trip verification** (#99 completion)
  - Open Hornelore in Chrome, start interview, speak, confirm:
    - `ui/js/transcript-guard.js` populates `state.lastTranscript` on `recognition.onresult`
    - Fragile-fact classifier fires for narrator identity / spouse / parents / siblings
    - `[extract] Attempting` log line shows `stt_src=mic_min_over_segments`, `stt_conf=<num>`, `confirm_req=<bool>`
    - Clarification envelope dispatches when `confirmation_required=True`
  - File: `docs/reports/WO-STT-LIVE-02_VERIFICATION.md` short memo with PASS/FAIL per checkpoint

### UI palate-cleanser option (if master is running and Chris wants to work in a different lane)

Chris raised: "thinking of working on the UI and mic and camera thing if need be." Gate analysis:

- **OK to touch now**: read-only CSS/HTML polish, narrator-picker spacing, memoir-mode label clarity. Anything in `ui/css/` or `ui/*.html` that doesn't touch JS.
- **Blocked until STT-LIVE-02 verify passes**: anything in `app.js`, `state.js`, `interview.js`, or `transcript-guard.js`. Mic/camera indicator work (WO-12A Lite) is Path B on Friday per sequencing — doing it before verification destroys attribution.
- **Reasonable Wednesday tasks if master is queued**: review `docs/reports/WO-STT-LIVE-02_REPORT.md`, design WO-12A Lite indicator styling offline on paper (no code), or do the browser round-trip itself (verification is gating work).

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

### Contingency: if r5e1/r5e2 still iterating

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
| 116 | NARRATIVE-FIELD Phase 4 eval | IN PROGRESS | r5e rejected, r5e1 ITERATE, r5e2 master running late Tue |
| 117 | NARRATIVE-FIELD final report | PENDING | r5e2 close (audit r5e + r5e1 + r5e2) |
| 115 | Phase 3 scorer alias relax | PENDING | r5e2 close; Fix A kept through all rollbacks |
| 99 | STT-LIVE-02 | IN PROGRESS | Browser round-trip (Chris, Wed) |
| 63/95 | SECTION-EFFECT Phase 3 | IN PROGRESS | Phase 2 landed; Phase 3 causal matrix Thu |
| 119 | turnscope greatGrandparents | PENDING | Small surgical; Wed if mnw cleared |
| 90 | SPANTAG-01 | PAUSED | Unblocks after #95 (Thu) |
| 96 | Truncation lane spec | PENDING | Not active; reading this week |
| 97 | alt_defensible_values (075, 088) | PENDING | Not active |
| 111 | Canon-grounded corpus expansion | IN PROGRESS | Weekend low-priority |
| 124 | case_049 tighten | IN PROGRESS | Closes with Phase 4 adoption |
| (new) | case_035 parents.education schema contradiction | PENDING | File post-r5e2 if ADOPT; root cause identified (L327 + L3711 alias ordering) |
| (new) | case_035 faith.significantMoment thematic routing | PENDING | Deeper than prompt; R5.5 Pillar 2 / SPANTAG territory |
| (new) | family.children.* sister misroute (case_035) | PENDING | Pre-existing relation-router bug, R6 |

## Closed / deferred

- **#72 TURNSCOPE** — closed (r4h)
- **#67 PATCH-H-DATEFIELD** — closed (r4i)
- **#68 case_053 wrong-entity** — deferred R6
- **#81 PROMPTSHRINK** — measured, not adopted; flag in-tree
- **#35 V4 scope axes** — backlog, R6
- **Full WO-12A** — deferred; reopen only after STT-LIVE-02 + extractor sequence complete. If WO-12A Lite solves the trust problem, full WO-12A may be downgraded or deleted.

---

## Sequencing rationale (why this order)

1. **r5e1 tonight, nothing else today.** r5e landed and was rejected (57/104, 2 must_not_write). Surgical NARRATOR-IDENTITY PRIORITY removal gives one-variable attribution. Finish scoring r5e1 before opening anything new. Do NOT start another lane until the priority rule is isolated as cause-or-not-cause.
2. **STT-LIVE-02 browser verify Wed.** Required before any `app.js` / `state.js` / `interview.js` work can start attribution-clean. Chris owns this.
3. **SECTION-EFFECT Phase 3 Thu.** This is the real bottleneck — SPANTAG can't ship without the causal matrix. Do not let UI work distract from this.
4. **SPANTAG Fri OR WO-12A Lite Fri.** If Phase 3 unblocks SPANTAG, extractor gains momentum — stay on that lane. If not, WO-12A Lite is a clean low-risk 1-hour palate cleanser (but only if STT-LIVE-02 is verified first).
5. **Weekend = writing and corpus, not code.** Save the GPU, save Chris's focus. The next active code block is Monday.
6. **Full WO-12A deferred, not dead.** Reopen only with evidence that Lite didn't fix the trust problem, and only when no extractor WO is mid-flight.

## Risk register for the week

- **Highest**: r5e1 still below 58/104 — priority rule was not the sole culprit, deeper rollback needed. Mitigation: ESCALATE path already scoped (revert `3fec639`); single additional commit, single additional master run.
- **High (retired)**: r5e unattributable flips — addressed by r5e1 one-variable surgical removal.
- **High**: STT-LIVE-02 browser verify surfaces a real bug. Mitigation: revert path is clean; `transcript_guard.js` is a standalone IIFE, easy to disable.
- **Medium**: SECTION-EFFECT Phase 3 causal matrix shows no clean signal. Mitigation: SPANTAG can still ship with best-available priors; the matrix is validation, not a blocker in principle.
- **Low**: SPANTAG Pass 2 implementation slips past Friday. Mitigation: Monday Apr 27 already reserved for first eval; one day slip doesn't cascade.

---

*This checklist lives at `docs/reports/LOOP-01_R5.5_WEEKLY_CHECKLIST_20260421.md`. A copy is at `Desktop/Horne/WEEKLY_CHECKLIST_20260421.md`. Update both when decisions land.*
