# WO-KAWA-UI-01A REPORT

**Date:** 2026-04-17
**Scope:** River View UI exact patch pack — Kawa visible and editable in UI

## FILES EDITED
- `ui/js/state.js` — added `state.kawa` block + `session.kawaMode` / `session.lastKawaMode`
- `ui/js/api.js` — added 4 Kawa API constants + 4 fetch helper functions
- `ui/js/app.js` — added `kawaRefreshList()` init call, `renderKawaUI()`, helper renderers, list item CRUD
- `ui/js/interview.js` — added `setKawaMode()`, `getKawaMode()`, `shouldOfferKawaReflection()`
- `ui/hornelore1.0.html` — added script tag, River button, popover, toggle listener, CSS
- `server/code/api/main.py` — registered Kawa router

## FILES CREATED
- `ui/js/lori-kawa.js` — Kawa UI behavior (refresh, select, build, save, confirm, dirty tracking)
- `server/code/kawa_store.py` — local-first JSON segment storage
- `server/code/kawa_projection.py` — provisional Kawa proposal builder
- `server/code/api/routers/kawa.py` — REST endpoints (list, get, build, save)
- `data/prompts/kawa_prompts.json` — narrative framing, definitions, followups, routing examples

## ADAPTATION NOTES
The patch pack assumed `lori9.0.html` with a tab-pane layout. Actual repo uses:
- `hornelore1.0.html` with a **popover**-based panel system
- `tabs.js` with `showTab()` for an older panel system
- `currentMode` already used by cognitive mode engine

Adaptations made:
- River View implemented as a **popover** (matching Life Map, Bio Builder pattern)
- Used `kawaMode` / `lastKawaMode` instead of overloading `currentMode`
- Script inserted between `interview.js` and `app.js` (correct load order)
- Popover toggle listener added alongside existing Life Map / Bio Builder listeners

## UI
- River button visible in header: NEEDS LIVE TEST
- River popover opens: NEEDS LIVE TEST
- River segment list implemented: PASS (code complete)
- River detail pane implemented: PASS (code complete)
- River strip implemented: PASS (code complete)

## DATA BINDING
- list endpoint wired: PASS
- detail endpoint wired: PASS
- build endpoint wired: PASS
- save endpoint wired: PASS

## EDITING
- flow editable: PASS (select + textarea)
- rocks editable: PASS (add/edit/delete)
- driftwood editable: PASS (add/edit/delete)
- banks editable: PASS (4 categories, add/edit/delete)
- spaces editable: PASS (add/edit/delete)

## STATUS
- proposed badge works: PASS (code complete)
- confirmed badge works: PASS (code complete)

## SAFETY
- chronology unaffected: PASS — no chronology code touched
- canonical fact layer unaffected: PASS — no extraction code touched
- Kawa state fully parallel: PASS — `state.kawa` is separate from all other state

## DEFERRED ITEMS
- SVG river drawing (WO-KAWA-UI-01B or later)
- Drag/drop rocks
- Memoir rewrite integration (WO-KAWA-02)
- LLM-driven proposal enrichment (WO-KAWA-01 Phase 2+)
- Hybrid questioning mode behavior (WO-KAWA-02)

## NEXT WO
- WO-KAWA-01 Phase 1: Wire LLM into `kawa_projection.py` for real proposals
- WO-KAWA-02: Deeper integration into Lori questioning + memoir organization
