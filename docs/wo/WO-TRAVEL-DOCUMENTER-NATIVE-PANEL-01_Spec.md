# WO-TRAVEL-DOCUMENTER-NATIVE-PANEL-01

**Status:** LANDED 2026-07-06 (same session as authoring, per Chris's directive from the design thread).
**Lane:** Trips / operator tooling
**Parent:** `WO-TRIP-IMPORT-AND-CLUSTER-01` (endpoints), `WO-LIFEMAP-TRAVELS-SHELF-AND-NARRATION-01` (the narrator surface this must NOT touch).

## Goal

Refactor the standalone Travel Documenter prototype (`ui/travel-documenter.html` + `ui/js/travel-documenter.js`, authored 2026-07-06) into a **native operator-only panel** inside the main Hornelore UI. No iframe. No narrator-room placement. No effect on Lori chat, runtime71, chat_ws, trip_narration_capture, or the Life Map Travels shelf.

**The locked division rule:**
```
Travel Documenter = operator tool for editing trips.
Travels shelf     = narrator/Lori conversation surface.
Do not mix their state.
```

## What landed

1. **Mountable module** — `ui/js/travel-documenter.js` rewritten around `window.lvTravelDocumenterMount(hostEl, {person_id, person_label, apiBase, standalone})`. The module renders its own template (single source of truth — the old page markup is gone), scopes all DOM lookups to the host via `data-td` attributes (no id collisions with app.js), and returns `{person_id, reload, destroy}`.
2. **Native "Travel Doc" shell tab** — new tab between Trips and Media in `hornelore1.0.html` (`lvShellTabTravelDoc` → `lvTravelDocTab` → `lvTravelDocHost`). `lvShellShowTab("traveldoc")` mounts with the CURRENTLY selected narrator: `state.person_id` + the display name from `lv80PersonSelect`. No pasted ids. "Choose a narrator first." when none selected. Remounts automatically when the selected narrator changed since last open (`_lvTravelDocMountedFor`).
3. **Interview-mode boundary inherited** — the whole shell tab strip is already hidden during interview mode (`body.lv-interview-mode-active #lvShellTabs` in lori80.css), so the panel is unreachable by narrators; verified by test.
4. **Standalone page kept as thin wrapper** — `ui/travel-documenter.html` now just mounts the module with `{standalone:true}` (connection inputs + `?api=`/`?person_id=` query params preserved as fallback/demo).
5. **CSS scoped** — `travel-documenter.css` element-level rules (`:root`, `*`, `body`, `button`, `input`, …) all moved under `.td-root`; body styles apply only to `body.td-standalone`. Native embedding cannot bleed into app CSS.
6. **Prototype bugs fixed during refactor:** stop-type list offered `travel_day` which the DB CHECK rejects — replaced with the schema-legal set (base/sight/day_trip/transit/lodging/meal/disruption/memory_anchor), locked by a test that diffs the offered list against migration 0015's CHECK.

## Safety boundaries (regression-tested in `tests/test_travel_documenter_panel.py`)

- Module source (comment-stripped) must never reference: `activeTripId`, `travelsShelfOpen`, `activeTripStopId`, `tripStyle`, `runtime71`, `sendSystemPrompt`, `wo9SendOrQueueSystemPrompt`, `state.session`.
- Native mount uses `state.person_id` / `opts.person_id` — no paste path in native mode.
- Endpoints used are the sanctioned trips/photos set only (`/api/trips*`, `/api/photos/{id}/thumb`).
- Standalone page carries no duplicated panel markup (single template source).
- Shell tab + panel + CSS + script wiring present; interview-mode hiding rule present.

## API use (existing endpoints only — nothing new server-side)

GET /api/trips?person_id= · POST /api/trips · GET /api/trips/{id}/tree · POST /api/trips/{id}/regions · POST /api/trips/{id}/regions/{rid}/stops · POST /api/trips/{id}/photos (trip-level, `trip_upload` method — cluster-placeable) · POST /api/trips/{id}/cluster-photos · GET /api/trips/{id}/narrator-photo-links · GET /api/trips/{id}/memoir-preview

## Acceptance

- Offline: 8/8 boundary tests green; `node --check` green on travel-documenter.js + app.js; all existing trip/travels packs unaffected.
- Live (Chris): select Christopher → Travel Doc tab → his trips load with no pasted id; switch narrator → tab shows that narrator's trips; create trip/region/stop, upload photos, cluster, memoir preview all work; tab absent during interview mode; Travels shelf behavior unchanged.

## Revision history

- 2026-07-06 — Authored + landed. Prototype (ChatGPT-designed standalone page) refactored per the native-panel directive from the design thread.
