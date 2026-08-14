# HORNELORE HANDOFF

**Updated:** 2026-08-14  
**Repository:** `lorevox-hx/hornelore`  
**Branch:** `main`

## 1. Read this first

This file is the current operational starting point. When documents disagree, use:

```text
current code
> current tests and live evidence
> accepted closeout records and ADRs
> this handoff
> MASTER_WORK_ORDER_CHECKLIST.md
> old work-order status lines
> archived history
```

Do not restart work from an old status line. Read the current implementation, its tests,
and its latest live evidence first.

## 2. Current project state

| Lane | State | Next decision |
|---|---|---|
| Google Photos Picker | **BANKED** | Reopen only for a demonstrated defect. |
| Travel Document core/export | **CLOSED on live evidence** | Preserve the editable timeline → DOCX projection rule. |
| Multi-day trip-photo placement | **COMPLETE; Gate 3 accepted 2026-08-14** | Close documentation; do not begin legacy-column removal. |
| Test-artifact cleanup | **DONE — classified in Palette P0** | Inventory complete; genuine memories preserved; nothing deleted. |
| Photo Palette | **COMPLETE; P4 and P5 accepted 2026-08-14** | Close the work order; do not reopen for polish without a demonstrated defect. |
| Legacy photo-day scalar retirement | **DEFERRED / separate authorization — now unblocked** | SQLite rebuild proposal. **Palette acceptance does not authorize it.** |
| Lean Lori | **PARKED BEHIND CURRENT TRAVEL-DOCUMENT SEQUENCE** | Resume only by Chris's explicit priority decision. |
| Runtime safety | **PARKED, server-authoritative** | Never reactivate through environment values. |
| Model / 8,192-token window | **LOCKED** | Any proposed model change is stop-and-report. |
| Privacy canon extraction/history purge | **PARKED work order** | Not on the current product critical path. |

## 3. Multi-day placement closeout

`WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01` changed the authoritative model from one
nullable day on `trip_photo_links` to a set of placement rows in
`trip_photo_day_placements`.

Binding behavior now proven live:

- one permanent photo and one trip membership may have zero, one, or many day placements;
- one day may hold many photos;
- **Add to this day**, **Remove from this day**, and **Move** are distinct;
- removing one occurrence preserves every other placement, membership, original,
  thumbnail, caption, approval and context;
- the compatibility scalar is `null` for zero or multiple placements and must never be
  used to decide whether a photo is unplaced;
- explicit placements and taken-date suggestions are counted separately;
- shared captions project consistently across placements and do not grant Lori approval;
- bounded thumbnail windows keep every item reachable without unbounded DOM growth.

Live evidence, Bismarck Trip, 2026-08-14:

- Stage B persistence: **83 passed, 0 failed, 0 not exercised, 1 attested**;
- restoration: **45 passed, 0 failed, 0 not exercised**;
- photo links remained 4 → 4; placement total restored 3 → 3;
- conversation link and turn rows survived byte-identically;
- original placement sets were restored with no duplicate links;
- rail counts matched timeline rows on all six days.

Phase 6 is not implied by this acceptance. Dropping `trip_photo_links.trip_day_id`
requires a separately reviewed SQLite rebuild and rollback plan.

## 4. Immediate execution order

Items 1–5 are **complete as of 2026-08-14**; item 6 is the next decision.

1. Record the multi-day closeout. **Done.**
2. Inventory contaminated acceptance/test artifacts. **Done in Palette P0** — no genuine
   family material deleted, and the contamination proved not to reach the Palette at all
   (22 of 36 narrators are harness residue and none owns a trip).
3. Execute the Photo Palette work order. **Done — P0 through P5.**
4. Run one consolidated Palette regression gate. **Done** — 584 tests plus four harnesses
   at 113 / 32 / 16 / 56, verified in `.venv`.
5. Start once for live acceptance, restart once for persistence. **Done** — P4 final PASS
   after one correction; P5 persistence 14/14 and restoration 22/22.
6. **NEXT: decide separately whether to authorize legacy-column retirement.** Palette
   acceptance does **not** imply it.

### 4.1 Photo Palette closeout

Reports: [`P4`](docs/reports/WO-TRIP-PHOTO-PALETTE-01_P4_LIVE_ACCEPTANCE.md) ·
[`P5`](docs/reports/WO-TRIP-PHOTO-PALETTE-01_P5_PERSISTENCE.md). Both are local-only under
the `docs/reports/` privacy rule and carry live narrator data.

Proven live and across a restart: placement identity preserved byte-for-byte; the derived
compatibility scalar correct at zero, one and many placements while the stored column is
never written; membership rendered once however many placements it has; filter counts equal
to their cards on every chip; batch Add, eligibility-checked Remove, source-named Move, and
reversible Hide/Restore; caption and Lori approval kept apart on the wire; dirty guards;
thumbnail-only grid with deferred loading on the modal's real scrollport; no duplicate
writes, no originals in the grid, no legacy-scalar writes.

**One defect was found live and fixed inside P4** (`b991353` code, `88429cc` tests): Add,
Remove, Move and a caption save refreshed the visible photo pool but not the Palette's own
hidden pool, so a hidden card kept showing a day it no longer had. `reloadPalettePhotoPools`
now owns that rule in one place, wired into five sites; eight mutations, eight killed.

Eight genuine Bismarck photographs were uploaded during acceptance and are **preserved** —
memberships only, no day placements, no approvals granted. Every temporary acceptance
caption, placement and hidden flag was restored afterwards and re-verified against the
original baseline.

**Two things carried forward, neither blocking:**

- **Region-only placement has no operator route.** `PhotoLinkPatch` carries no
  `trip_region_id` field and no clear-stop flag, so nothing in the Travel Document can
  create a region-only photo link. The Palette renders the badge; the state is
  unreachable. A product decision, not a defect.
- **Scale evidence is the harness's.** The trip holds 12 memberships, so 49/50/51/200/500/
  1,000, `Load more` and the mounted-window distinction remain proven by
  `run_photo_palette_behaviour.js` and `run_photo_window_arithmetic.js`. No rows were
  manufactured to change that.

## 5. Photo Palette product boundary

The Palette is a mode inside the existing Travel Document workspace, not a second product
or nested modal. It reuses the photo inventory, thumbnails, placement APIs, bounded window
helpers, current trip and selected-day state already landed.

The authoritative unplaced rule is:

```text
zero trip_photo_day_placements
```

Never use `trip_day_id IS NULL`; that is also the compatibility representation of a photo
placed on multiple days.

The Palette MVP includes filters, selection, batch Add, per-placement Remove/Move,
caption/approval separation, hidden/review states, and honest partial-failure reporting.
It does not include destructive deletion, face recognition, AI photo interpretation,
duplicate originals, or a schema rewrite.

Canonical plan:

- `docs/wo/WO-TRIP-PHOTO-PALETTE-01_Spec.md`
- `docs/wo/WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01_Spec.md`
- `docs/architecture/TRAVEL_DOCUMENT_DOCTRINE.md` ruling 1.16

## 6. Efficient work and verification policy

- Work in coherent product blocks, not one-line review cycles.
- Focused tests while coding; one consolidated regression run at the end of the block.
- Mutation/non-vacuity tests only for load-bearing behavior.
- Do not restart for documentation, tests, or harness-only changes.
- Keep the stack down through an implementation block.
- Start once for live acceptance and restart once for final persistence proof.
- Stop early only for schema risk, destructive live-data action, security boundary,
  model/configuration change, or a real design decision.
- **Claude prepares copy-paste `git add` + `git commit` blocks; Chris runs them and pushes;
  Chris and ChatGPT review the pushed block.** Agents do not run git here. The reason is in
  `CLAUDE.md`: a sandbox git command that hits the agent timeout on the `/mnt/c` 9p mount
  leaves `.git/index.lock` behind and silently blocks GitHub Desktop and Chris's own WSL
  git, presenting as "add succeeded, commit says nothing to commit, Desktop still shows N
  changed files." Read-only git (`log`, `status`, `diff`, `rev-parse`) is fine.

## 7. Known separate issues—not Palette scope

- six pre-existing `interview_sessions → people` foreign-key violations from old harness
  narrators;
- hard-delete filesystem residue root cause;
- legacy-column retirement;
- privacy canon extraction and public-history purge;
- broad `ws_chat`/extract-router decomposition;
- giant control-document archival;
- model, prompt-window, STT, TTS and runtime-safety changes.

Do not fold these into Palette implementation.

## 8. Required document set

| Document | Purpose |
|---|---|
| `HANDOFF.md` | Truthful current state and next action. |
| `MASTER_WORK_ORDER_CHECKLIST.md` | Small active/next/deferred coordination list. |
| `docs/wo/WO-TRIP-PHOTO-PALETTE-01_Spec.md` | Executable researched Palette plan. |
| `docs/wo/WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01_Spec.md` | Landed placement authority and acceptance history. |
| `docs/architecture/TRAVEL_DOCUMENT_DOCTRINE.md` | Binding Travel Document rulings. |

Historical handoffs and long status narratives remain in git history or `docs/archive/`;
they must not be appended back into this operational brief.
