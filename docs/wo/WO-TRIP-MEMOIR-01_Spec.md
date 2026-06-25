# WO-TRIP-MEMOIR-01

**Status:** PARKED / DO NOT IMPLEMENT YET
**Severity:** MEDIUM (feature; not a parent-session blocker)
**Locked principle:** *Schema first. The flat trip_memoir MVP doesn't model real long-form trips. Build the storage that the canonical test case (Chris's Spring 2026 Central Europe trip — 23 days, 6 countries, 16+ stops with hierarchical nesting, 2,500–3,000 photos, multiple thematic threads) actually needs. Then close the elicitation gap. Then implement.*

## Why this WO exists

The original `trip_memoir_full_mvp` package proposed a flat schema: `trips → trip_stops → trip_photo_links` with each stop a single row. The first parked draft of this spec (2026-06-24 first pass) listed three prerequisites. Chris's review on 2026-06-24 (second pass) supplied a real-world test case — Spring 2026 Central Europe & Northern Italy — that breaks the flat model in three load-bearing ways:

1. **Hierarchical stops.** Mirano was a base for 6 day trips (Treviso, Padua, Cittadella, Chioggia, Mira, Venice). Pula was a base for Istrian coastal towns. The flat schema can't express "this stop is a day trip under that base."

2. **Regional structure.** The trip is one journey but reads naturally as five regional chapters plus a return journey (Czechia / Austria / Slovenia / Croatia / Italy / Return). The memoir output should mirror this — flat-stop-list is unreadable for trips of this scale.

3. **Thematic threads.** "Roman archaeology," "Venetian villas," "medieval walled towns," "regional food," "travel disruptions" each cross 6+ stops. The memoir output needs **dual-axis** rendering — chronological day-journal AND thematic chapters — not just stop-by-stop.

This spec captures the revised design. **The original MVP code is rejected as the implementation starting point;** it lives in `~/Downloads/trip_memoir_full_mvp/` as design raw material only. Implementation is blocked behind four prerequisites.

## Locked design choices

1. **Past-trips only.** No future trip planning. The narrator logs a trip that already happened.

2. **Era auto-assigned from trip start_date.** Trip belongs to ONE era — the era the narrator was in when it started. Spring 2026 → `today` era for Chris. Norway 2028 (hypothetical) → `today` for Kent. Era assignment requires a non-fuzzy narrator DOB. **No fuzzy DOBs allowed for any narrator using the Trip feature.**

3. **Both photo flow directions supported.** Narrator/operator can upload photos first and have Lori ask about them, OR Lori asks and narrator adds photos after. Same photo data either way.

4. **Both outputs from the same data.** Trip-derived sections inject into the **main memoir** as part of the narrator's overall life story, AND a **standalone trip memoir** renders the same data as its own document. The data sits in one place; the rendering surfaces are dual. **No parallel `trip_memoirs` authority table** — the standalone view is a rendering of the same canonical data the main memoir consumes.

5. **Location Guide notes stay as interview context only.** Operator-seeded place facts (Prague is famous for X, Istrian cuisine includes Y) shape Lori's prompts but **do not become narrator memory** unless explicitly promoted. `include_in_memoir=false` default. This is the most important boundary in the design and survives unchanged from the MVP.

## Revised schema (hierarchical, region-aware, theme-tagged)

```
trip
  └── trip_regions
        └── trip_stops  (nested via parent_trip_stop_id)
              └── trip_photo_links
        └── trip_themes  (cross-stop thematic threads)
trip_location_notes  (region/stop-aware operator context)
trip_bio_suggestions  (provisional bio facts, narrator-confirmed)
trip_story_links  (joins to story_candidates from chat sessions)
```

### `trips`

The full journey.

```
id              TEXT PRIMARY KEY (UUID)
person_id       TEXT NOT NULL → people(id) ON DELETE CASCADE
title           TEXT NOT NULL    -- "Spring 2026 Central Europe & Northern Italy"
start_date      TEXT             -- YYYY-MM-DD; required for era auto-derivation
end_date        TEXT
summary         TEXT             -- 1-3 sentence trip overview (operator or Lori-elicited)
status          TEXT             -- 'draft' / 'in_progress' / 'memoir_ready'
created_at      TEXT NOT NULL
updated_at      TEXT NOT NULL
meta_json       TEXT             -- {era_id (derived), narrator_age_at_start, ...}
```

### `trip_regions`

Major chapters inside the trip. One row per regional grouping.

```
id              TEXT PRIMARY KEY
trip_id         TEXT NOT NULL → trips(id) ON DELETE CASCADE
ord             INTEGER NOT NULL DEFAULT 0
title           TEXT NOT NULL    -- "Veneto / Northern Italy"
country_or_area TEXT             -- "Italy" / "Croatia (Istria)"
start_date      TEXT
end_date        TEXT
summary         TEXT
theme_json      TEXT             -- ["Venetian villas", "regional food"]
created_at      TEXT NOT NULL
updated_at      TEXT NOT NULL
```

For the Spring 2026 trip:
```
1. Czechia — Prague
2. Austria — Salzburg / Graz
3. Slovenia — Ljubljana / drive routes
4. Croatia (Istria) — Pula / Medulin / Rovinj coast
5. Italy — Muggia / Trieste / Mirano + Veneto day trips / Venice
6. Return Journey — Venice → Dulles → Denver → Santa Fe
```

### `trip_stops`

Specific places, day trips, transit events, lodging changes, sights, memorable moments. **Supports nesting** via `parent_trip_stop_id` so day trips can hang off their base.

```
id                    TEXT PRIMARY KEY
trip_id               TEXT NOT NULL → trips(id) ON DELETE CASCADE
trip_region_id        TEXT NOT NULL → trip_regions(id) ON DELETE CASCADE
parent_trip_stop_id   TEXT          → trip_stops(id) ON DELETE SET NULL
ord                   INTEGER NOT NULL DEFAULT 0
stop_type             TEXT NOT NULL
                      -- enum: 'base' / 'day_trip' / 'transit' / 'lodging'
                      --     / 'meal' / 'disruption' / 'sight' / 'memory_anchor'
date_start            TEXT
date_end              TEXT          -- bases span multiple days
location_name         TEXT NOT NULL
latitude              REAL
longitude             REAL
title                 TEXT
notes                 TEXT
thematic_tags_json    TEXT          -- ["Roman archaeology", "medieval walled towns"]
timeline_event_id     TEXT          -- back-link into universal timeline spine
created_at            TEXT NOT NULL
updated_at            TEXT NOT NULL
meta_json             TEXT
```

Examples for Spring 2026:
```
Mirano (base, May 30 – June 8)
  ├── Treviso (day_trip)
  ├── Padua (day_trip)
  ├── Cittadella (day_trip)
  ├── Chioggia (day_trip)
  ├── Mira / Brenta villas (day_trip)
  └── Venice departure (transit)

Pula / Medulin (base, May 26 – May 30)
  ├── Pula Roman sites (sight)
  ├── Rovinj (day_trip)
  └── Istrian coastal towns (day_trip)
```

### `trip_themes`

Cross-stop thematic threads. **Important** — chronology alone is not enough for trips of this scale.

```
id              TEXT PRIMARY KEY
trip_id         TEXT NOT NULL → trips(id) ON DELETE CASCADE
ord             INTEGER NOT NULL DEFAULT 0
title           TEXT NOT NULL    -- "Roman archaeology"
description     TEXT             -- 1-2 sentences capturing the thread
tag             TEXT NOT NULL    -- machine key for joining: "roman_archaeology"
created_at      TEXT NOT NULL
```

For Spring 2026:
```
- Roman archaeology  (Pula amphitheatre, Trieste, scattered ruins)
- Venetian villas    (Brenta canal, Padua, Mira)
- Medieval walled towns  (Cittadella, Graz altstadt, Prague)
- Markets and food   (Prague markets, Istrian seafood, Veneto wine)
- Travel disruptions (train delay, airline delay at Venice)
- Return journey     (Dulles → Denver → Santa Fe arc)
- Family history interests  (the genealogical lane)
```

Stops link to themes via `thematic_tags_json` on `trip_stops` (the tag values match `trip_themes.tag`). Photos can also carry theme tags directly for memoir queries that span stops.

### `trip_photo_links`

Bulk-import and cluster-friendly. EXIF datetime + lat/lng auto-assigns each photo to nearest trip_stop by spacetime proximity; operator overrides via UI.

```
id                    TEXT PRIMARY KEY
trip_id                TEXT NOT NULL → trips(id) ON DELETE CASCADE
trip_region_id         TEXT          → trip_regions(id) ON DELETE SET NULL
trip_stop_id           TEXT          → trip_stops(id) ON DELETE SET NULL
media_id               TEXT NOT NULL → media(id) ON DELETE CASCADE
ord                    INTEGER NOT NULL DEFAULT 0
taken_at               TEXT          -- from EXIF
latitude               REAL          -- from EXIF GPS
longitude              REAL
assignment_method      TEXT NOT NULL
                       -- enum: 'manual' / 'exif_time' / 'exif_gps'
                       --     / 'album' / 'csv' / 'operator'
cluster_confidence     REAL          -- 0.0 – 1.0; lower = needs operator review
caption                TEXT
narrator_caption       TEXT
include_in_memoir      INTEGER NOT NULL DEFAULT 1
thematic_tags_json     TEXT
created_at             TEXT NOT NULL
updated_at             TEXT NOT NULL
```

### `trip_location_notes`

Region/stop-aware operator context. Bilingual.

```
id                              TEXT PRIMARY KEY
trip_id                          TEXT NOT NULL → trips(id) ON DELETE CASCADE
trip_region_id                   TEXT          → trip_regions(id) ON DELETE SET NULL
trip_stop_id                     TEXT          → trip_stops(id) ON DELETE SET NULL
location_name                    TEXT
question                         TEXT
answer                           TEXT
source_type                      TEXT          -- 'operator' / 'lori' / 'external'
include_in_interview_context     INTEGER NOT NULL DEFAULT 1
include_in_memoir                INTEGER NOT NULL DEFAULT 0
target_language                  TEXT NOT NULL DEFAULT 'en'
                                 -- bilingual; respects narrator's session language
                                 -- when surfaced to Lori or in memoir output
created_at                       TEXT NOT NULL
updated_at                       TEXT NOT NULL
```

### `trip_bio_suggestions` and `trip_story_links`

Carry forward from MVP unchanged — provisional bio facts and join rows into the existing `story_candidates` lane. Both remain `status='suggested'` until narrator/operator promotes.

## Revised memoir output — dual-axis

Trip output is **section proposals for the main memoir**, not a standalone authority. The same data renders into:

### A. Main memoir injection

Trip-derived sections become part of the narrator's overall life story memoir, anchored to the trip's era. For Chris's Spring 2026 trip, sections appear under "Today" era of the main memoir alongside other 2026 life events.

### B. Standalone trip memoir view

Same data, different render. The standalone trip memoir is a view of the canonical trip rows, not a separate document. Structure:

```
Part I — The Journey in Order  (chronological axis)
  1. Czechia — Prague
  2. Austria — Salzburg / Graz
  3. Slovenia — Ljubljana
  4. Croatia (Istria) — Pula / Medulin
  5. Italy — Muggia → Trieste → Mirano + Veneto day trips
  6. Return Journey

Part II — Themes That Ran Through the Trip  (thematic axis)
  - Roman Trail (Pula / Trieste / scattered ruins)
  - Venetian Villas (Brenta / Padua / Mira)
  - Medieval Walled Towns (Cittadella / Prague / Graz)
  - Markets and Food
  - Travel Disruptions
  - Family History Threads

Part III — Photo Appendix / Map / Timeline
```

Memoir generation stays deterministic (no LLM authoring of narrator voice). The generator walks `trip_regions` → `trip_stops` (respecting nesting) for Part I, walks `trip_themes` for Part II, and emits a photo grid + map render + timeline mini-spine for Part III.

## Prerequisites (must land before any code from this WO touches `main`)

1. **WO-LORI-FACTUAL-CHAIN-CAPTURE-01** (renamed from BUG-LORI-FACTUAL-OVER-SENSORY-PROBE-01). Lori must preserve factual chains like Stanley → Fargo → exam → meal tickets → West Coast (Kent) or Prague → Salzburg → Ljubljana → Pula (Chris). Without this, the trip elicitation lane fills the database with sensory fragments instead of trip-shaped narratives.

2. **Canonical memoir integration decision LOCKED.** Resolved in this revision: trip-derived sections inject into the main memoir pipeline as section proposals; standalone trip-memoir view is a rendering of the same data, not a parallel authority table. No `trip_memoirs` document table.

3. **Target-language propagation.** Every narrator-facing surface (Lori's trip questions, location guide prompts surfaced as Lori prompts, memoir output) accepts a `target_language` kwarg and resolves it from the same source the rest of the codebase uses (`looks_spanish()` probe → recent-turns smoothing → optional `profile_json.session_language_mode` pin). If the trip happened while the narrator was speaking Spanish, the system speaks Spanish about it.

4. **EXIF photo clustering design.** Bulk-import + auto-assignment by EXIF datetime + lat/lng to nearest trip_stop by spacetime proximity. Cluster confidence scoring. Operator review surface for low-confidence assignments. **Hand-linking 2,500–3,000 photos one at a time is unworkable.** Pillow + GPS EXIF extraction is already in the tree (landed 2026-04-26 in the Photo Intake lane); needs the clustering pass on top.

## Recommended WO sequence (after prerequisites land)

```
1. WO-TRIP-MEMOIR-01_Spec.md  (this spec — schema + boundaries)
2. WO-LORI-FACTUAL-CHAIN-CAPTURE-01  (closes Lori's factual-chain gap)
3. WO-TRIP-IMPORT-AND-CLUSTER-01  (CSV/album itinerary import + EXIF clustering)
4. WO-TRIP-MEMOIR-SECTIONS-01  (chronological + thematic section proposals into main memoir pipeline)
```

The Trip tab UI is built incrementally across (1) → (3) so each WO has a runnable demo surface.

## What is NOT in scope

- **Do NOT copy backend / router / UI files from the original `trip_memoir_full_mvp` package into `main`.** The package's flat schema is rejected; its router + UI was built on top of that flat schema and would need to be rewritten regardless.
- No `app.include_router(trips.router)` patches into `main.py`.
- No `data/` seeding from the MVP.
- No `.env` flag additions for trip features (premature; flag set is finalized when prerequisites land).

## Acceptance — when this WO can flip from PARKED to ACTIVE

The unblock sequence:

1. WO-LORI-FACTUAL-CHAIN-CAPTURE-01 lands and shows GREEN on a Kent-style replay harness (factual chain ≥4 turns preserved without sensory pivot).
2. Main memoir pipeline can ingest external section proposals cleanly (couples to WO-MEMOIR-STORY-CANDIDATES-WIRE-01).
3. Target-language propagation is verified on at least one bilingual narrator end-to-end (Melanie / Chris-as-Spanish-narrator).
4. EXIF clustering design is sketched in WO-TRIP-IMPORT-AND-CLUSTER-01 with a small-scale dry-run on Chris's Spring 2026 photo set.

When all four are GREEN, this spec flips to ACTIVE with an implementation breakdown that respects the revised hierarchical schema.

## Canonical test case

**Spring 2026 Central Europe & Northern Italy.** 23 days, May 22 – June 13, 2026. Six countries. 16+ stops with hierarchical nesting (Mirano base + 6 day trips; Pula base + 3 day trips). 2,500–3,000 photos. Multiple thematic threads (Roman archaeology, Venetian villas, medieval walled towns, markets and food, travel disruptions, return journey, family history). Coherent arc (Prague start → Veneto middle → Venice airline delay + tight Dulles connection → Denver → Santa Fe end).

If the system can organize this trip and generate a polished dual-axis memoir from it, the architecture scales down cleanly to simpler trips — Kent's hypothetical Norway trip (1 region), Janice's old Florida vacations (1 region, few stops), Melanie's Mexico family visits (1 region, Spanish narration).

## Bottom line

Schema first. The flat trip_memoir MVP is the wrong starting point. Build the hierarchical model — `trip → trip_regions → trip_stops (nested) → trip_photo_links` plus `trip_themes` and region-aware location notes — and the rest follows.

## Source artifacts

- Original MVP package (REJECTED as implementation start, retained as design raw material): `~/Downloads/trip_memoir_full_mvp/`
- First-pass parked spec (this file's predecessor): superseded 2026-06-24
- Canonical test case: Chris's Spring 2026 Central Europe & Northern Italy trip (described in §Canonical test case above)
- Reference inspiration cited by Chris: `https://visualschedulebot.com/index.php` (UX / schedule semantics)
- Prerequisite #1 evidence: `transcript_switch_moyt6.txt` 2026-05-09 (Kent's Army induction sensory-pivot failure)
- **UI mockup (banked 2026-06-25):** `docs/mockups/trip_tab_ui_mockup.html` — operator-facing 3-column layout (Trip list / Trip Overview + Regions + Themes + Memoir Preview / Readiness Gates + Photo Import + Location Guide + Timeline Bridge). Validates the hierarchical schema visually (6 regions, nested base→day-trip stops, themes as cross-cutting strips). Readiness Gates panel encodes the 4-spec dependency queue (BUG-LORI-DEEP-EUROPEAN-ROUTE-LANGUAGE-DRIFT-01 / BUG-LORI-RESPONSE-STUB-COLLAPSE-01 / BUG-LORI-CHAIN-ANCHOR-ECHO-STRENGTH-01 / WO-STORY-CANDIDATE-TEXT-CHAIN-PERSISTENCE-01) that must land before `WO-TRIP-TAB-DB-01` can flip from UNWRITTEN to ACTIVE. Reference this file when writing `WO-TRIP-IMPORT-AND-CLUSTER-01_Spec.md` and `WO-TRIP-TAB-DB-01_Spec.md`.

## Revision history

- 2026-06-24 (first pass) — Authored as parked spec. Flat MVP schema captured, three prerequisites listed.
- 2026-06-24 (second pass, this revision) — Replaced flat schema with hierarchical `trip → trip_regions → trip_stops (nested) → trip_photo_links` + `trip_themes`. Added Spring 2026 Central Europe trip as canonical test case. Locked memoir integration decision (sections-into-main + standalone view as render of same data, NOT parallel authority). Added EXIF clustering as prerequisite. Added target_language to location notes. Bumped recommended WO sequence: this spec → factual-chain capture → import-and-cluster → memoir-sections.
- 2026-06-25 — UI mockup banked at `docs/mockups/trip_tab_ui_mockup.html`. Visual validates hierarchical schema (6 regions, nested base→day-trip stops, themes), encodes the 4-spec readiness gate dependency, frames Location Guide as operator-assistive multilingual help (not narrator-triggered language switch — aligned with English-first product call).
