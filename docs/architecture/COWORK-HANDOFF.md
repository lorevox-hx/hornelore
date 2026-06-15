# COWORK HANDOFF — Land the Universal Pivot + Safety Specs

**From:** Planning session (Claude chat, 30 days of architecture work)
**To:** Cowork session operating on `lorevox-hx/hornelore`
**Date prepared:** 2026-06-14
**Session work order:** WO-DOCS-UNIVERSAL-PIVOT-LANDING-01
**Branch to create:** `docs/universal-pivot-and-safety-specs`

---

## What this session is (and is not)

**IS:** Landing finished documentation into the repo and running the
already-specced docs reorg. Pure docs + file-moves. No runtime code.
No test runs. No touching the three RED gates.

**IS NOT:** Building any of the WOs. The WO specs being landed describe
future build work; this session only commits the specs themselves, the
strategy ADRs, and a README/CLAUDE.md reframe. Building happens in
later, separately-scoped Cowork sessions — one WO at a time.

If at any point this session is tempted to start implementing a
classifier, a prompt block, or a migration: stop. That is not this
session's job. This session lands paper.

---

## The one-paragraph context

Hornelore is being reframed: it is not a locked-to-the-Horne-family
fork of Lorevox, it is Lorevox itself, with the Horne family as
"tenant zero." The interview posture is moving from questionnaire-first
to **oral-history-as-default** (narrator tells chapters, Lori listens
and follows; structured styles become operator-selectable overrides).
This session lands the strategy documents and work-order specs that
define that reframe and the safety/behavior work it depends on. The
rename to "Lorevox" is a future packaging event, not part of this
session.

---

## Files to land (in the bundle accompanying this handoff)

All files are FINAL. They have been reviewed and edited across the
planning session. Do not regenerate or rewrite them — commit them
as-is except where this handoff explicitly says to edit.

### Strategic ADRs (architecture decision records — not work orders)

1. `HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md` — the anchor doc. Establishes
   Hornelore-is-Lorevox, tenant-zero framing, the universal audit table,
   the "high-context completeness" principle, and the pre-rebrand
   decision list.
2. `LORI-RUNTIME-ARCHITECTURE.md` — the nine-stage runtime pipeline
   synthesis. Names each stage, maps stages to the WOs that implement
   them, defines the diagnostic contract.
3. `MEMORY-EXERCISE-DECISION.md` — small ADR; keeps memory_exercise as
   a real style and specs a follow-up implementation WO.

### Work-order specs (describe FUTURE build work; landed here as specs)

4. `WO-LORI-SAFETY-LLM-CLASSIFIER-01_Spec.md` — the live safety WO.
   Merged Phase 2 + past-tense classifier. Closes Gate 5. **Build first
   of the WOs, in a LATER session.**
5. `WO-LORI-SOFTENED-MODE-PERSISTENCE-01_Spec.md` — closes Gate 6.
6. `WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01_Spec.md` — consent disclosure
   edits.
7. `WO-LORI-STORY-FIRST-PHASE-1-01_Spec.md` — the oral-history behavior
   engine (reflection grounding, story momentum, thread bank, question
   hierarchy).
8. `WO-LORI-ORAL-HISTORY-DEFAULT-01_Spec.md` — introduces the
   `oral_history` style and makes it default.
9. `WO-LORI-BIO-BUILDER-UNIVERSAL-01_Spec.md` — four-tier Bio Builder
   with the anchored-asking creep defense.

### History / superseded (land them, but clearly marked)

10. `WO-LORI-SAFETY-PAST-TENSE-ACKNOWLEDGE-01_Spec.md` — **SUPERSEDED**
    (banner at top of file). Merged into #4. Land it for design-history
    traceability only; do not build from it.
11. `PRE-BUILD-ADDITIONS.md` — **ALREADY APPLIED** (banner at top of
    file). A changelog of edits already folded into #1, #3, #9. Land it
    as history; do not re-apply.
12. `REDESIGN-DOC-HEADER-TO-PREPEND.md` — a header block to prepend to
    `WO-INTERVIEW-PROCESS-REDESIGN-01` IF that file exists in the repo.
    See "Open question" below.

---

## Sequence for this session

### Step 1 — Create the branch
```
git checkout main
git pull
git checkout -b docs/universal-pivot-and-safety-specs
```

### Step 2 — Read and run WO-DOCS-REORG-01
The repo root is cluttered (50+ BUG-*_Spec.md, 20+ Hornelore-*.docx,
multiple HANDOFF/MASTER_WORK_ORDER markdowns). `WO-DOCS-REORG-01_Spec.md`
already exists in the repo root and specifies the target directory
structure. Read it, then execute the moves it specifies. This MUST
happen before committing the new docs so they land in the right
directories rather than adding to root clutter.

If WO-DOCS-REORG-01 does not specify where strategy ADRs and new WO
specs go, use this convention (and note the choice in the PR
description):
- Strategic ADRs → `docs/architecture/`
- WO specs → `docs/work-orders/` (or wherever existing WO-*.md specs
  are moved to by the reorg)
- History/superseded → `docs/work-orders/superseded/`

### Step 3 — Commit the strategic ADRs
Place files 1-3 in `docs/architecture/` (or reorg-specified location).

### Step 4 — Commit the WO specs
Place files 4-9 in the reorg-specified WO location. Place files 10-11
in a `superseded/` or `history/` subdirectory — they carry banners
explaining their status.

### Step 5 — Reframe the README
Add a header section near the top of `README.md` that:
- States Hornelore is Lorevox; the Horne family is tenant zero
- Points to `docs/architecture/HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md`
  and `docs/architecture/LORI-RUNTIME-ARCHITECTURE.md`
- Reclassifies the existing "locked to the Horne family" language as
  tenant-zero context, not an architectural commitment

Do NOT delete the existing README content (the status sections, the
narrator tables, the architecture notes are all still accurate for the
current state). Add the reframe as a new top section; leave the
detailed status history intact below it.

### Step 6 — Update CLAUDE.md
`CLAUDE.md` exists in the repo root and is read by every future Cowork
and Claude Code session. Add a short pointer near the top so future
sessions operate under the universal framing:
- Note that Hornelore is Lorevox (tenant-zero framing)
- Point to the two architecture ADRs
- Note that oral-history is the target default posture (with the
  oral_history style introduced by WO-LORI-ORAL-HISTORY-DEFAULT-01,
  not yet built)

### Step 7 — Stop and report; open the PR only after Chris approves
Do NOT open the PR automatically. When all prior steps are done:

1. Commit everything to the branch `docs/universal-pivot-and-safety-specs`.
2. Produce a summary for Chris to review: the reorg performed (with the
   before/after file tree), every doc added and its location, the
   README and CLAUDE.md edits (show the diffs), and how the redesign-doc
   header question was resolved.
3. STOP and wait for Chris to review the branch and explicitly approve.
4. ONLY after Chris says to proceed, open the PR with this title:
   `WO-DOCS-UNIVERSAL-PIVOT-LANDING-01: land universal pivot strategy +
   safety/behavior specs + docs reorg`
   PR description should list the reorg, the docs added with locations,
   the README/CLAUDE.md edits, and the explicit note that NO runtime
   code changed and NO WO was built.
5. Leave the PR for Chris to merge. Do not merge to main automatically.

---

## Open question this session must resolve

**Does `WO-INTERVIEW-PROCESS-REDESIGN-01` exist in the repo?**
It was NOT in the repo root file listing as of the last review. It was
a vision document authored in the planning chat. Two cases:

- **If it exists in the repo:** prepend the contents of
  `REDESIGN-DOC-HEADER-TO-PREPEND.md` to the top of it, marking it as
  historical context superseded by the runtime architecture.
- **If it does NOT exist:** skip the header step. Do not create the
  redesign doc just to header it. Note in the PR description that the
  header file was not applied because the target doesn't exist in-repo,
  and leave `REDESIGN-DOC-HEADER-TO-PREPEND.md` in the history
  subdirectory for reference.

---

## Critical facts about the current repo state (for orientation)

- README dated 2026-05-01; 559 commits; `main` branch
- Three RED parent-session gates: #5 (safety soft-trigger),
  #6 (post-safety recovery), #7 (truth-pipeline observability)
- 211 unit tests passing
- Live session styles (in `services/lori_communication_control.py`
  word-cap table): `clear_direct=55 / warm_storytelling=90 /
  questionnaire_first=70 / companion=80`. NOTE: `oral_history` and
  `memory_exercise` do NOT exist in the runtime yet — they are
  introduced by future WOs, not by this session.
- `set_softened()` already exists in `db.py`
- Migrations use numbered SQL files via `migrations_runner.py`
  (pattern: `0003_media_archive.sql`)
- Relevant code files for the FUTURE build sessions (not this one):
  `prompt_composer.py`, `services/lori_communication_control.py`,
  `services/safety.py`, `chat_ws.py`, `db.py`

---

## The build sequence AFTER this session (for context, not for now)

Once the docs are landed and the PR merged, build sessions run one WO
at a time in this order. Each gets its own Cowork session with the WO
spec as the brief:

1. `WO-LORI-SAFETY-LLM-CLASSIFIER-01` → closes Gate 5
2. `WO-LORI-SOFTENED-MODE-PERSISTENCE-01` → closes Gate 6
3. Flip `HORNELORE_SAFETY_LLM_LAYER=1` for real sessions ONLY after
   both gates GREEN (acute-without-softened reproduces Turn 07 drift)
4. `WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01`
5. `WO-LORI-STORY-FIRST-PHASE-1-01`
6. `WO-LORI-ORAL-HISTORY-DEFAULT-01` (introduces oral_history style)
7. `WO-LORI-BIO-BUILDER-UNIVERSAL-01`
8. `WO-LORI-MEMORY-EXERCISE-IMPLEMENTATION-01` (not yet drafted; specced
   in MEMORY-EXERCISE-DECISION.md)

DO NOT start any of these in this session.

---

## Definition of done for THIS session

- [ ] Branch `docs/universal-pivot-and-safety-specs` created
- [ ] WO-DOCS-REORG-01 read and executed
- [ ] Files 1-3 (ADRs) committed to architecture docs location
- [ ] Files 4-9 (live WO specs) committed to WO specs location
- [ ] Files 10-11 (superseded/history) committed to history subdir with
      banners intact
- [ ] README reframed (new top section; history preserved below)
- [ ] CLAUDE.md updated with universal-framing pointer
- [ ] `WO-INTERVIEW-PROCESS-REDESIGN-01` header question resolved
      (applied or noted-as-skipped)
- [ ] Branch committed; summary + diffs reported to Chris for review
- [ ] STOPPED and waited for Chris's approval before opening any PR
- [ ] PR opened ONLY after Chris approved; left for Chris to merge
- [ ] NO runtime code changed; NO WO built; NO tests run
