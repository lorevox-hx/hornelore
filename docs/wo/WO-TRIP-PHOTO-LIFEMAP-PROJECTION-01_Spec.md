# WO-TRIP-PHOTO-LIFEMAP-PROJECTION-01 — Spec (NOT YET IMPLEMENTED)

**Status:** SPEC ONLY (banked 2026-07-08 from Chris's review). Photos are
already uploaded + linked; this WO promotes them to *visible in the
timeline / Life Map projection* without making unvetted photos
narrator-visible.

## Goal

Make uploaded/linked trip photos visible in the trip's Life Map / timeline
projection (cover thumbnail + counts) while keeping non-narrator-ready
photos off narrator surfaces.

## Current state (verified)

- Photo uploads go through `photo_intake.ingest`, writing `photos` rows.
- `trip_photo_links` connects photos to trip/region/stop.
- Travels shelf shows narrator-ready linked photos.
- `trip_timeline_bridge.sync_trip_to_life_record` writes one
  `timeline_events` row per trip — date/title/body/meta counts only, **no
  photo metadata**.

## Tasks

1. **Travel Doc photo endpoint fix — DONE 2026-07-08.**
   Travel Doc now loads `/api/trips/{trip_id}/photo-links` (operator,
   unfiltered), not `/narrator-photo-links`. Travels shelf keeps
   `/narrator-photo-links`.

2. **Photo controls in the Photos tab — DONE 2026-07-08 (partial).**
   Photo cards now show thumbnail, placement, editable caption, and an
   **In memoir** checkbox (`PATCH /api/trips/photo-links/{link_id}`).
   STILL TODO: `narrator_caption` field, "Use as trip cover" control,
   optional "Confirm placement" button.

3. **Region-level photo support — DONE 2026-07-08.**
   `POST /api/trips/{trip_id}/regions/{region_id}/photos` creates links
   with `trip_region_id` set + `trip_stop_id` NULL, method `trip_upload`
   (cluster-placeable to a stop later).

4. **Extend `trip_timeline_bridge` — TODO.**
   Compute and add to `timeline_events.meta`:
   ```
   { trip_id, era_id, cover_photo_id,
     narrator_ready_photo_count, memoir_photo_count }
   ```
   `cover_photo_id` = explicit `trips.meta_json.cover_photo_id` if set,
   else first narrator-ready linked photo.

5. **Call `sync_trip_to_life_record` after — TODO.**
   trip/stop/region photo upload, cluster-photos, and photo-link patch
   when `include_in_memoir` / placement / caption changes. (Upload
   endpoints already call sync; the patch path does not yet.)

6. **Life Map / timeline renderer — TODO.**
   For `timeline_events` kind="trip": if `meta.cover_photo_id`, show
   thumbnail + a photo-count badge; click opens Travels shelf / Travel
   Doc. Narrator surfaces use only `narrator_ready` photos.

## Boundaries

- Non-narrator-ready photos never appear on narrator-visible Life Map.
- Operator Travel Doc can see all linked photos.
- Photo metadata may ground prompts, but Lori must not infer
  who/what/emotion in photos.

## Done in this batch (2026-07-08)

Tasks 1, 2 (partial), 3 landed with the Travel Doc photo-card + review-fix
batch. Remaining: cover-photo control (task 2), timeline-bridge photo meta
(task 4), sync-on-patch (task 5), Life Map render (task 6).
