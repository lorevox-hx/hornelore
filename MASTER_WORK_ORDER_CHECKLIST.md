# MASTER_WORK_ORDER_CHECKLIST

**Active as of:** 2026-07-02 (code-vs-checklist adjudication — ALL six build-sequence WOs verified LANDED in-tree; statuses below corrected. Also: trip-lane conversation layer at 62/72→GREEN pending harness re-verify; Spanish-detection overfire class fixed)
**Previously:** 2026-06-16 (post Phase 3+4+5+6+7.5 of QUESTIONNAIRE-BIO-FACTS-MIGRATE), 2026-06-14 (post-universal-pivot)
**Supersedes:** Pre-pivot checklist (archived at `docs/archive/handoffs-pre-pivot/MASTER_WORK_ORDER_CHECKLIST.md`)
**Read first:** [`docs/architecture/HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md`](docs/architecture/HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md), [`docs/architecture/LORI-RUNTIME-ARCHITECTURE.md`](docs/architecture/LORI-RUNTIME-ARCHITECTURE.md)

---

## Posture

Hornelore is Lorevox. The Horne family is tenant zero, not a special case in the architecture. Every WO from this date forward is written against the universal assumption: Lori must work for narrators she has never met. Pre-pivot WOs (114 specs, locked-narrator framing) are archived at `docs/archive/workorders-pre-pivot/` for traceability — they are not the active source of truth.

Interview default is moving from questionnaire-first to **oral-history-as-default**. Structured styles become operator-selectable overrides.

---

## Build sequence — one Cowork session per WO, in order

Each WO gets its own Cowork session with the WO spec as the brief. Do NOT start more than one at a time.

| # | WO | File | Closes / Introduces |
|---|---|---|---|
| 1 | SAFETY-LLM-CLASSIFIER | [`docs/wo/WO-LORI-SAFETY-LLM-CLASSIFIER-01_Spec.md`](docs/wo/WO-LORI-SAFETY-LLM-CLASSIFIER-01_Spec.md) | Closes Gate 5 (soft-trigger safety) — **LANDED (verified in-tree 2026-07-02):** `safety_classifier.py` 3-dim taxonomy + LLM layer + confidence floor + 44 tests; gated `HORNELORE_SAFETY_LLM_LAYER=0` |
| 2 | SOFTENED-MODE-PERSISTENCE | [`docs/wo/WO-LORI-SOFTENED-MODE-PERSISTENCE-01_Spec.md`](docs/wo/WO-LORI-SOFTENED-MODE-PERSISTENCE-01_Spec.md) | Closes Gate 6 (post-safety recovery) — **LANDED (verified in-tree 2026-07-02):** `lori_softened_response.py` 3-state machine + per-trigger caps (30/35/50) + 32 tests; gated `HORNELORE_SOFTENED_RESPONSE=0` |
| — | **Flip flag** | `HORNELORE_SAFETY_LLM_LAYER=1` | **NOW THE LIVE BLOCKER for Gates 5+6** — code for #1+#2 is in-tree; remaining work is live-harness GREEN verification then the flip. Only after #1 + #2 both GREEN (acute-without-softened reproduces Turn 07 drift) |
| 3 | PHASE-9-DISCLOSURE-UPDATE | [`docs/wo/WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01_Spec.md`](docs/wo/WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01_Spec.md) | Consent disclosure edits — **LANDED (verified in-tree 2026-07-02):** three-tier disclosure + style descriptions in `docs/runbooks/SAFETY_OPERATOR_RUNBOOK.md` (docs-only WO) |
| 4 | STORY-FIRST-PHASE-1 | [`docs/wo/WO-LORI-STORY-FIRST-PHASE-1-01_Spec.md`](docs/wo/WO-LORI-STORY-FIRST-PHASE-1-01_Spec.md) | Oral-history behavior engine — **LANDED (verified in-tree 2026-07-02):** `reflection_grounding.py` + `story_momentum.py` + `thread_bank.py` + `question_hierarchy.py` + chat_ws wiring + 66 tests; REPORT-ONLY behind `HORNELORE_STORY_FIRST_PHASE_1=0` |
| 5 | ORAL-HISTORY-DEFAULT | [`docs/wo/WO-LORI-ORAL-HISTORY-DEFAULT-01_Spec.md`](docs/wo/WO-LORI-ORAL-HISTORY-DEFAULT-01_Spec.md) | Introduces `oral_history` style + makes it default — **LANDED AND ACTIVE (verified in-tree 2026-07-02):** style @ 90-word cap, system default in comm-control signatures, picker + 29 tests |
| 6 | BIO-BUILDER-UNIVERSAL | [`docs/wo/WO-LORI-BIO-BUILDER-UNIVERSAL-01_Spec.md`](docs/wo/WO-LORI-BIO-BUILDER-UNIVERSAL-01_Spec.md) | Four-tier Bio Builder — **LANDED (verified in-tree 2026-07-02):** `bio_fact_router.py` + `document_authority.py` + `bio_anchored_asker.py` + `bio_gap_map.py` + 3 creep defenses + 66 tests; gated `HORNELORE_BIO_*=0` |
| 6a | OPERATOR-NEW-NARRATOR-INTAKE-FORM-01 | (root WO, 2026-06-15) | 9-section intake form + Phase 2B orchestrator + Phase 2C modal — **LANDED** |
| 6b | QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 | [`docs/wo/WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01_Spec.md`](docs/wo/WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01_Spec.md) | Phase 1 read swap + Phase 2 FE badges + Phase 3 write fan-out + Phase 4 primary_career bug + Phase 5 23-test pack + Phase 6 self-review + Phase 7.5 backfill readiness — **LANDED 2026-06-16**, Phase 7 live verify pending |
| 7 | MEMORY-EXERCISE-IMPLEMENTATION | (not yet drafted) | Specced in [`docs/architecture/MEMORY-EXERCISE-DECISION.md`](docs/architecture/MEMORY-EXERCISE-DECISION.md) |

---

## Superseded / history

The two docs below land for design-history traceability. Do NOT build from them.

- [`docs/wo/superseded/WO-LORI-SAFETY-PAST-TENSE-ACKNOWLEDGE-01_Spec.md`](docs/wo/superseded/WO-LORI-SAFETY-PAST-TENSE-ACKNOWLEDGE-01_Spec.md) — merged into #1 SAFETY-LLM-CLASSIFIER
- [`docs/wo/superseded/PRE-BUILD-ADDITIONS.md`](docs/wo/superseded/PRE-BUILD-ADDITIONS.md) — changelog of edits already folded into the strategy + WO specs
- [`docs/wo/superseded/REDESIGN-DOC-HEADER-TO-PREPEND.md`](docs/wo/superseded/REDESIGN-DOC-HEADER-TO-PREPEND.md) — header block for `WO-INTERVIEW-PROCESS-REDESIGN-01`; target doesn't exist in repo, header was not applied

---

## Parent-session readiness gates (locked checklist)

Inherited from pre-pivot work. Pre-pivot evidence in `docs/archive/`; post-pivot evidence as it lands.

| Gate | State | Lane |
|------|-------|------|
| 1. DB lock fix | 🟢 GREEN | landed pre-pivot |
| 2. Atomicity discipline | 🟢 GREEN | landed pre-pivot |
| 3. Story preservation | 🟢 GREEN | landed pre-pivot |
| 4. Safety acute path | 🟢 GREEN | landed pre-pivot |
| 5. Safety soft-trigger | 🟡 CODE LANDED, flag off | WO #1 SAFETY-LLM-CLASSIFIER — needs live-harness GREEN then `HORNELORE_SAFETY_LLM_LAYER=1` |
| 6. Post-safety recovery | 🟡 CODE LANDED, flag off | WO #2 SOFTENED-MODE-PERSISTENCE — needs live-harness GREEN then flag flip (lockstep with Gate 5) |
| 7. Truth-pipeline observability | 🔴 RED | scoped separately; not in the 6-WO sequence |

---

## Where things live now

```
docs/
  architecture/                      strategic ADRs + this session's brief
    HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md
    LORI-RUNTIME-ARCHITECTURE.md
    MEMORY-EXERCISE-DECISION.md
    COWORK-HANDOFF.md
  wo/                                active WO specs (build from these)
    WO-LORI-SAFETY-LLM-CLASSIFIER-01_Spec.md
    WO-LORI-SOFTENED-MODE-PERSISTENCE-01_Spec.md
    WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01_Spec.md
    WO-LORI-STORY-FIRST-PHASE-1-01_Spec.md
    WO-LORI-ORAL-HISTORY-DEFAULT-01_Spec.md
    WO-LORI-BIO-BUILDER-UNIVERSAL-01_Spec.md
    superseded/
  archive/
    workorders-pre-pivot/            114 pre-pivot specs (history only)
    handoffs-pre-pivot/              pre-pivot HANDOFF / MORNING / LAPTOP / CHECKLIST docs
  reports/                           eval reports, WO completion reports, .docx history
  (existing subtrees preserved: research/, specs/, observations/, voice_models/, …)
```

Root carries operational files only: `README.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `AGENT_CONTRACT.md`, `LICENSE`, this checklist, `.env`, `*.bat` launchers, top-level dirs (`launchers/`, `scripts/`, `server/`, `ui/`, `data/`, `docs/`, `tests/`).
