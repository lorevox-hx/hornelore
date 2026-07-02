# WO-TRIP-IMPORT-AND-CLUSTER-01

**Status:** ACTIVE — Phase 1+2 implementation opened 2026-07-02 (this session)
**Severity:** MEDIUM-HIGH (Chris's stated priority: test photo import + travel memoirs on real data)
**Parent spec:** `docs/wo/WO-TRIP-MEMOIR-01_Spec.md` (hierarchical schema — LOCKED; this WO implements it)
**UI reference:** `docs/mockups/trip_tab_ui_mockup.html`
**Canonical test data:** `fixtures/trips/trip_2019_france_italy_fixture.json` (small) + Spring 2026 Central Europe (23 days, 6 countries, 2,500–3,000 photos — the scale gate)

## Prerequisite check (all four from WO-TRIP-MEMOIR-01, adjudicated 2026-07-02)

1. WO-LORI-FACTUAL-CHAIN-CAPTURE-01 — **LANDED**, live harnesses GREEN (55/55 → 69/72/53/55 on 2026-07-02 run).
2. Memoir integration decision — **LOCKED** (sections-into-main + standalone view of same data).
3. Target-language propagation — language contract + detector overfire class fixed 2026-07-02; trip surfaces accept `target_language`.
4. EXIF clustering design — **THIS SPEC** (Phase 2 below); Pillow EXIF datetime+GPS already live in the Photo Intake lane (`photos` table carries `date_value`, `latitude`, `longitude`, `location_source='exif_gps'`).

Readiness-gate bugs from the mockup panel: DEEP-EUROPEAN-ROUTE-LANGUAGE-DRIFT (CLOSED), RESPONSE-STUB-COLLAPSE (it-2 + G4 threshold alignment 2026-07-02), CHAIN-ANCHOR-ECHO-STRENGTH (LANDED 2026-07-02), STORY-CANDIDATE-TEXT-CHAIN-PERSISTENCE (LANDED, migration 0014). Gate satisfied.

## Locked design choices (inherited + new)

- Hierarchical schema per parent spec: `trips → trip_regions → trip_stops (nested via parent_trip_stop_id) → trip_photo_links` + `trip_themes` + `trip_location_notes` + `trip_bio_suggestions` + `trip_story_links`.
- **Deviation from parent spec:** `trip_photo_links.photo_id → photos(id)`, NOT `media(id)`. The live photo authority table is `photos` (migration 0001) and it already carries EXIF datetime + GPS. `media_archive_items` is the document archive — wrong table for this.
- Past trips only; era auto-derived from `start_date`; no fuzzy DOB narrators on the Trip feature.
- Location-guide notes default `include_in_memoir=0` — interview context, never silent narrator memory.
- Feature gate: `HORNELORE_TRIPS=0` default-off; router 404s when off (mirrors `operator_eval_harness` posture). Parent spec's "no .env flags premature" is superseded — prerequisites have landed.
- Memoir render is deterministic (no LLM authoring): Part I chronological walk (regions → nested stops), Part II thematic walk, Part III photo appendix.

## Phases

### Phase 1 — schema + import (LANDED this session)

- Migration `0015_trip_tables.sql`: 8 tables + indexes.
- `services/trip_repository.py`: pure-sqlite accessors (create/read tree/update/photo-link CRUD), test-patchable via `db.DB_PATH`.
- `services/trip_import.py`: itinerary import from the fixture JSON shape (regions + string stops) AND the richer dict-stop shape (stop_type/dates/GPS/nesting/themes); CSV import (one row per stop: `region,location,stop_type,date_start,date_end,lat,lng,parent,title,notes,themes`).
- Router `routers/trips.py` (gated): `POST /api/trips/import-itinerary`, `POST /api/trips/import-csv`, `GET /api/trips?person_id=`, `GET /api/trips/{id}/tree`.

### Phase 2 — EXIF photo clustering (LANDED this session)

- `services/trip_photo_clustering.py` — pure spacetime assignment:
  - time score: inside stop date window = 1.0; ±1 day = 0.7; else `1/(1+days_out)` decay. Stops without dates score 0 on time.
  - GPS score: haversine to stop lat/lng — <2 km 1.0 / <10 km 0.8 / <50 km 0.5 / <200 km 0.2 / else 0.05.
  - combined: both signals `0.6*time + 0.4*gps`; time-only capped 0.8; GPS-only capped 0.7 (`assignment_method` = `exif_gps` when GPS contributed else `exif_time`).
  - `cluster_confidence < 0.50` → operator review queue.
- Router: `POST /api/trips/{id}/cluster-photos` (reads narrator's `photos` rows, writes `trip_photo_links`), `GET /api/trips/{id}/photo-links?max_confidence=`, `PATCH /api/trips/photo-links/{link_id}` (operator reassign/confirm → `assignment_method='operator'`, confidence 1.0).

### Phase 3 — Trip Tab UI (NEXT; blocked on Phase 1+2 live verify)

Read-only first: trip list + tree detail + review queue per the mockup's 3-column layout. Build as `WO-TRIP-TAB-DB-01`.

### Phase 4 — memoir render (preview endpoint LANDED this session; DOCX export NEXT)

- `GET /api/trips/{id}/memoir-preview` — deterministic dual-axis JSON (Part I regions→nested stops with photos; Part II themes with matching stops; Part III photo appendix counts). DOCX export wires into the existing memoir DOCX router in a follow-up commit, alongside main-memoir section proposals (couples to WO-MEMOIR-STORY-CANDIDATES-WIRE-01).

## Acceptance

1. Unit: import the 2019 fixture → tree read-back matches (3 regions, 12 stops, dates). CSV import round-trips. Clustering unit pack: in-window+near photo ≥0.9; out-of-window far photo <0.3 review-flagged; GPS-less photo falls back to time-only. ALL offline.
2. Live (Chris): flip `HORNELORE_TRIPS=1`, import 2019 fixture via curl, upload a handful of real Spring 2026 photos through the existing photo intake, run cluster-photos, eyeball review queue, hit memoir-preview.
3. Scale dry-run: Spring 2026 photo set (2,500–3,000) clusters in <60s with review queue <20% of photos.

## Stop conditions

- Clustering mis-assigns >30% on the real photo set → revisit scoring weights before UI work.
- Any trip surface leaks operator context into narrator memory without promotion → hard stop (parent-spec boundary).

## Revision history

- 2026-07-02 — Authored + Phase 1/2 implemented in the same session (Chris's priority call: photo import + travel memoir testing).
