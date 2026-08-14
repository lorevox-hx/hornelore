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
| Test-artifact cleanup | **NEXT, bounded cleanup gate** | Inventory first; preserve genuine memories; hide noise reversibly. |
| Photo Palette | **NEXT PRODUCT BUILD after cleanup map** | Execute `docs/wo/WO-TRIP-PHOTO-PALETTE-01_Spec.md`. |
| Legacy photo-day scalar retirement | **DEFERRED / separate authorization** | SQLite rebuild proposal only after Palette acceptance. |
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

1. Record the multi-day closeout and perform one final F12/API-log review.
2. Inventory contaminated acceptance/test artifacts. Do not delete genuine family material.
3. Execute the Photo Palette work order.
4. Run one consolidated Palette regression gate.
5. Start the stack once for Palette live acceptance; restart once at the end for persistence.
6. Decide separately whether to authorize legacy-column retirement.

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
- Claude commits; Chris pushes; Chris and ChatGPT review the pushed block.

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
