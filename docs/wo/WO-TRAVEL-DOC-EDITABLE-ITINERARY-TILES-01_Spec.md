# WO-TRAVEL-DOC-EDITABLE-ITINERARY-TILES-01

**Status:** LANDED 2026-07-07 (built by Chris + ChatGPT while agent was down; reviewed by Claude same day — GREEN, pending live UI test).
**Lane:** Trips / operator tooling
**Parent:** `WO-TRAVEL-DOCUMENTER-NATIVE-PANEL-01` (the panel this makes editable), `WO-TRIP-IMPORT-AND-CLUSTER-01` (schema + endpoints).

## Goal

Turn the Travel Doc from an add-only documentation panel into a real editable itinerary board: trips/regions/stops as tiles that can be edited, deleted, moved up/down, inserted before/after, moved between regions, and nested/promoted — with **tile order as the route authority** (dates are metadata), persisted through the existing `ord` column.

## What landed

**Frontend (`ui/js/travel-documenter.js` + css):** DOM-built tile rendering (`renderStopTile`/`renderRegionTile`/`tileBtn`) replacing string-built tree; per-tile actions (move up/down, add before/after, edit, delete; regions also add-stop); right-side selected-item editor panel (`renderTripEditor`/`renderRegionEditor`/`renderStopEditor`); stop editor can move a stop to another region or under another parent (own subtree excluded from the parent dropdown); insert-before/after via `insertContext` → create-then-move fallback path; blank editor field sends explicit `clear_*` flags (editor represents full state — blank means erase, and blank WITHOUT the flag never erases). CSS tile/editor styles stay scoped under `.td-root` / `body.td-standalone`.

**Backend (`routers/trips.py` + `services/trip_repository.py`):**

- `PATCH /api/trips/{trip_id}` (new) — title/dates/summary with clear flags + life-record sync.
- `RegionPatch`/`StopPatch` clear flags (`clear_dates` or per-side, `clear_notes`, region optional fields); `region_update`/`stop_update`/`trip_update` write NULL only on the flag — None still means unchanged.
- Region patch now syncs life-record (parity with trip/stop patch + region create/delete).
- `POST /{trip_id}/regions/reorder` — full-permutation validation (exact id set, no dups) before renumbering 0..n; row-count asserted.
- `POST /{trip_id}/stops/reorder` — ONE sibling group (trip + region + parent scope); same exact-membership validation.
- `POST /{trip_id}/stops/{stop_id}/move` — ownership, target-region/parent validation, self-parent + cycle walk (hop-capped), before/after refs must live in the target group; repository move is one transaction: subtree (all descendants, trip-scoped walk) follows region changes, descendant photo-links' denormalized `trip_region_id` follows, target group renumbered with positional insert, old group gap-closed.
- `create_stop` child ord computed from the parent's sibling group (was region top-level count — collision bug).
- `delete_stop` captures child ids pre-delete and renumbers the top-level group after FK SET NULL promotion (no ord collisions on promoted children).

## Review notes (Claude, 2026-07-07)

165 trip-lane tests green (incl. `test_trip_reorder_move` 18, `test_trip_editable_fixes` 15, `test_trip_patch` 4). Router validation is defence-in-depth with repository WHERE-scoping behind it. Boundary gate intact (panel still never references Lori/Travels state; endpoints all sanctioned). Non-blocking observations: (a) stop-editor save issues PATCH then MOVE → life-record syncs twice per save (harmless); (b) cycle walk hop cap 50 — fine at realistic depths; (c) region `summary` not editable from the FE editor (deliberate field selection); (d) same-region move still touches the moved stop's photo-link region (no-op value, `updated_at` churn only).

## Live test results (2026-07-07, Claude-in-Chrome — PASS)

Ran against the Spring 2026 Central Europe fixture on the live stack: label reads active narrator ("Documenting trips for Chris") not the hidden select ✓ · Munich inserted BEFORE Prague via +Before → ord 0/1, persisted ✓ · memoir preview Part One lists Munich then Prague ✓ · move-up button renumbers cleanly ✓ · cross-region move appends + gap-closes source ✓ · Mirano (6 children) moved Italy→Slovenia and back — entire subtree followed both ways, gap-closed both sides ✓ · delete removes + persists across reload ✓ · trip-session scope untouched by all Travel Doc actions (state.session trip keys never set) ✓. Photo-link-follows not exercisable live (fixture has no photo links) — unit-covered.

**Live finding fixed same day:** deleting a CHILDLESS stop left an ord gap (Salzburg:0, Graz:2) — delete_stop only renumbered on child promotion. Patched to renumber unconditionally (child-group renumber when the deleted stop was itself a child); 2 new tests in DeleteGapCloseTest. Requires stack restart to go live.

## Original live test checklist

Open Spring 2026 Europe → add Munich before Prague → reload, order persists → memoir preview follows route order → edit + clear one field at each level → move a stop between regions → move a parent stop with a nested day-trip (subtree + photo links follow) → delete a test stop (children promote, order clean) → confirm no Lori/runtime71/Travels-shelf behavior changed.

## Revision history

- 2026-07-07 — Landed (Chris-led build); spec + review notes banked by Claude.
