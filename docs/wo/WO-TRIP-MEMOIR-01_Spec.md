# WO-TRIP-MEMOIR-01

**Status:** PARKED / DO NOT IMPLEMENT YET
**Severity:** MEDIUM (feature; not a parent-session blocker)
**Locked principle:** *The Trip idea is right. Build the storage after Lori can elicit the stories that fill it. Don't ship a data structure that nothing can populate.*

## Why this WO exists

A `trip_memoir_full_mvp` package was authored externally (Trips tab + backend API + DB tables + photo links + Bio Builder suggestions + a deterministic memoir-draft generator + a Location Guide lane for Prague-style place/food/culture context). The architecture is sound and aligns with CLAUDE.md design principles 1, 5, 6, and 8 — particularly the explicit separation of guide-context (operator-seeded place facts) from narrator-memory (narrator's lived experience).

The MVP is **not being applied to `main`** because three prerequisites are unresolved. Shipping the storage layer ahead of the elicitation layer would produce a data structure that nothing reliably fills, and a parallel memoir authority that competes with the existing memoir pipeline.

This spec captures the design intent so it survives in the WO directory until the prerequisites land. The package itself stays in `~/Downloads/trip_memoir_full_mvp/` (or wherever Chris keeps it) — it is **NOT** copied into the repo's backend / router / UI tree.

## What to keep from the MVP

These design choices are correct and should carry forward into whatever implementation eventually lands:

1. **Trips as a separate tab** in the narrator/operator UI. Trips have internal structure (multi-stop, photos-per-stop, date range, primary location) that a flat list of timeline events cannot model. A dedicated tab is the right surface.

2. **Trip stops bridge into the timeline.** Each `trip_stop` with a date writes a `trip_stop` event into the universal timeline spine, so the trip milestones appear in the canonical chronological view alongside everything else. The trip-specific structure (ordering, location, captions, photo links) stays in trip tables; the timeline only sees the milestone.

3. **Photos and media linked to the trip** (overall) and to specific stops. Existing `media` rows are referenced via `trip_photo_links`; the trip lane does not duplicate media storage.

4. **Location Guide as interview context only.** Operator-seeded notes about general place / food / culture / history facts shape Lori's interview prompts but **do not become narrator memory** unless explicitly promoted. `include_in_memoir=false` default. This is the most important design choice in the MVP and must survive any revision.

5. **Bio Builder suggestions as provisional.** Trip-derived candidate facts (e.g., "narrator visited Prague in 2018") are stored with `status="suggested"` and require narrator/operator confirmation before promotion — async HITL review consistent with CLAUDE.md provisional-truth principle 5.

6. **Source-linked trip material.** Every memoir section produced from a trip carries `source_links` back to the originating trip / trip_stop / media / story_candidate. No orphaned text; full provenance.

## What to revise before implementation

1. **Trip memoir output should become main-memoir SECTION PROPOSALS, not a parallel memoir authority.** The MVP's `trip_memoirs` + `trip_memoir_sections` tables create a second memoir document per narrator, competing with the existing main memoir pipeline (memoir export harvests `story_candidates` + `projection_family` + structured fields — pending wiring in WO-MEMOIR-STORY-CANDIDATES-WIRE-01). The redesign: trips emit candidate sections that the main memoir composer can accept / decline / edit, not a standalone document. One memoir per narrator, with trip-derived sections inside it.

2. **All narrator-facing trip prompts need `target_language` propagation.** The MVP's `/api/trips/{id}/location-prompts` and the deterministic memoir generator both produce English-only output. After WO-SPANISH-LIVE-READINESS-01 (landed 2026-06-17), every composer that touches narrator-facing strings honors a language pin. Trip prompts and trip memoir sections must do the same. If Melanie tells a Spanish story about a trip to Mexico, the system must not switch her back to English.

3. **Implementation blocked by BUG-LORI-FACTUAL-OVER-SENSORY-PROBE-01.** Kent's session 2026-05-09 was the proof: a perfect trip-shaped narrative (Stanley → Fargo → admissions test → top score → meal tickets → West Coast) was not captured because Lori pivoted to sensory probes (scenery, camaraderie, sights/sounds/smells) instead of following the factual chain. Building the trip data structure without first fixing the elicitation layer ships empty `trip_stops` rows.

## Prerequisites (must land before any code from this WO touches `main`)

1. **Fix Lori's factual-chain capture for trip-shaped stories.** Filed as `BUG-LORI-FACTUAL-OVER-SENSORY-PROBE-01` (see `transcript_switch_moyt6.txt` 2026-05-09 lines 38–82 for the canonical evidence: Kent's Army induction story, five facts ignored, sensory probe doubled-down after explicit narrator correction at line 80). Fix architecture: factual-narrative cue type in the narrative cue library; era-click directive permits event-list framing; comprehension guard on meta-feedback turns (narrator says "not X" → composer must not propose more X).

2. **Decide canonical memoir integration.** Trip-derived sections live INSIDE the main memoir pipeline, not in a parallel `trip_memoirs` table. Couples to WO-MEMOIR-STORY-CANDIDATES-WIRE-01 (memoir export harvests story_candidates) — the trip lane joins through that same harvest path.

3. **Add `target_language` propagation for trip and location prompts.** Every narrator-facing composer touched by this WO accepts a `target_language` kwarg and resolves it from the same source the rest of the codebase uses (narrator `looks_spanish()` probe → recent-turns smoothing → optional `profile_json.session_language_mode` pin).

4. **Add consent / private flags before trip notes can enter memoir output.** Couples to WO-DISCLOSURE-MODE-01 (parked). Per-entry consent state (`narrator_consented` / `narrator_offered_no_consent` / `system_inferred_no_consent` / `sacred_do_not_persist`) must be representable on `trip_stops.notes`, `trip_photo_links.narrator_caption`, and any Location Guide note that an operator promotes. `sacred_do_not_persist` blocks derived persistence to the memoir output; raw transcript / audio remains governed by existing Archive privacy controls.

## What is NOT in scope

- **Do NOT copy backend / router / UI files into `main`.** No `server/code/api/routers/trips.py`, no `server/code/api/routers/trip_location_notes.py`, no `ui/js/trips-tab.js`, no `ui/js/trip-location-guide-overlay.js`, no `apply_trip_memoir_*.py` execution, no schema migrations.
- No `app.include_router(trips.router)` patches into `main.py`.
- No `data/` seeding.
- No `.env` flag additions for trip features (premature; the flag set is finalized when prerequisites land).

## Acceptance — when this WO can flip from PARKED to ACTIVE

The unblock sequence:

1. `BUG-LORI-FACTUAL-OVER-SENSORY-PROBE-01` lands and shows GREEN on a Kent-style replay harness (trip-shaped narrative produces ≥4 factual follow-ups out of 5 turns; zero sensory pivots when narrator provides explicit factual content).
2. WO-MEMOIR-STORY-CANDIDATES-WIRE-01 lands and the main memoir export harvests `story_candidates` cleanly.
3. ChatGPT / Claude / Chris triangulate on the canonical-memoir-integration question (sections-into-main vs. parallel-document) and lock the answer.
4. WO-DISCLOSURE-MODE-01 Phase 1 lands (per-entry consent state on at least the schema level).

When all four are GREEN, this spec flips to ACTIVE with an implementation breakdown that respects the revised architecture (trip sections proposed into main memoir pipeline, bilingual prompts, consent gating).

## Bottom line

The Trip idea is still right. Build the elicitation layer first, then the storage layer that fills it. Park the code, keep the design.

## Source artifacts

- External MVP package: `~/Downloads/trip_memoir_full_mvp/` (NOT in repo)
  - `README.md` — apply instructions
  - `apply_trip_memoir_full_mvp.py` — combined patcher
  - `apply_trip_memoir_mvp.py` — Trips-only patcher
  - `apply_trip_location_guide_overlay.py` — Location Guide patcher
  - `server/code/api/routers/trips.py` (~330 lines, 6 tables + 18 endpoints)
  - `server/code/api/routers/trip_location_notes.py`
  - `ui/js/trips-tab.js`, `ui/js/trip-location-guide-overlay.js`
  - `scripts/run_trip_memoir_smoke.py`
  - `docs/wo/WO-TRIP-MEMOIR-01_MVP.md`, `docs/wo/WO-TRIP-GUIDE-LOCATION-CONTEXT-01.md`
- Kent transcript evidence for prerequisite #1: `transcript_switch_moyt6.txt` 2026-05-09, lines 38–82.

## Revision history

- 2026-06-21 — Authored as parked spec. MVP package received but not applied. Prerequisites listed.
