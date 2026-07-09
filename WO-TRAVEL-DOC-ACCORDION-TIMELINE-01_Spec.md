# WO-TRAVEL-DOC-ACCORDION-TIMELINE-01 — Spec + landing note

**Status:** LANDED 2026-07-08 (frontend/CSS only, own logical pass).

## Goal

A read-only "visual schedule" of the trip in the Travel Doc right column,
without disrupting the editor. Toggle between **Editor** and **Timeline**.

## Design (as built)

- Right column gets a toggle: **[Editor] [Timeline]** (`viewEditor` /
  `viewTimeline`). `st.rightView` = `editor | timeline`; `applyRightView()`
  shows/hides the editor panel vs the timeline panel and marks the active
  tab. Default = editor.
- The Timeline is **read-only navigation + visibility**. It renders from the
  data already in memory — `st.tree` (regions → nested stops), plus
  `st.locationNotes`, `st.sources`, `st.photoLinks` for the badges/thumbnail.
  **No new backend table, no endpoints, no Lori/runtime71 changes.**
- Each accordion row (`renderTlRow`) shows:
  - first thumbnail for that region/stop if a linked photo exists (else an
    empty placeholder),
  - title,
  - date range if known,
  - the same `story · N notes · N docs · N photos` count badges as the tiles
    (reuses `regionIndicators` / `stopIndicators`).
- **Click a row → selects that region/stop in the editor** (`selectItem`)
  and flips the right column back to Editor view.
- Stops nest under regions with indentation; child/day-trip stops nest under
  their parent.
- The timeline re-renders whenever the tree refreshes (`renderTree` calls
  `renderTimeline` when the timeline is visible), so adds/edits/uploads show
  up immediately.

## Boundaries (honored)

- Read-only surface; the only mutation it triggers is selecting an item in
  the editor.
- Uses existing endpoints only (`/api/photos/{id}/thumb` for thumbnails).
- No Lori, runtime71, Travels-shelf, or session state touched — passes the
  Travel Doc boundary test unchanged.

## Files

- `ui/js/travel-documenter.js` — toggle state + `applyRightView` +
  `renderTimeline` / `renderTlRow` / `firstThumbFor`.
- `ui/css/travel-documenter.css` — `.td-right-toggle` / `.td-rtab` /
  `.td-timeline-*` / `.td-tl-*` (all `.td-root`-scoped).

## Future (not in this pass)

- Collapse/expand per region (currently always-expanded accordion).
- Date-axis / proportional layout (true "visual schedule" spacing).
- Cover-photo + photo-count once WO-TRIP-PHOTO-LIFEMAP-PROJECTION-01 lands.
