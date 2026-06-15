# Morning Brief — 2026-04-26 night2

**Overnight pass #2 complete.** Two commits ready.

---

## What landed

### 1. WO-PHOTO-PEOPLE-EDIT-01 (#267) — full stack
The View/Edit modal now lets the curator add/remove **people** + **events** post-upload. Critical for batch-imported scanned photos where the operator needs to add "this is Mom and Grandma" or "Easter 2026" after the fact. Was previously single-photo-form-only (had to delete and re-upload to add people).

- **Backend:** `_PhotoPatch` model accepts `people` + `events` arrays. PATCH endpoint uses **replace-all semantics** (server delete_all + add_back). Empty array = wipe. Absent = leave untouched. New repository helpers `delete_all_photo_people()` / `delete_all_photo_events()`.
- **Frontend:** modal renders existing people/events on open, +Add buttons mirror the single-photo form pattern, Save sends current state. Source-attribution + completeness pills update after save.

### 2. P1.1 — silent EXIF corrupt-tag flag (defensive)
`exif.py` now distinguishes "no GPS tag" from "GPS tag present but unparseable" (zero-denominator DMS / partial triple / out-of-range coords). Modal shows new red **"location · GPS UNREADABLE"** pill with hover-tooltip explaining the data was there but corrupted, so the curator types the location manually instead of assuming the phone didn't capture metadata. Backend `gps.present_unparseable: bool` flows through `metadata_json["exif_gps"]` and pops out in the modal.

### 3. P1.3 — PATCH location_label recalc (defensive)
PATCH endpoint now recomputes `needs_confirmation` when `location_label` OR `location_source` changes (was only `location_source`). Fixes the edge where a curator hand-edits the label of an EXIF-GPS-derived photo and `needs_confirmation` stays stale at False. Uses the existing row's source authority if the patch only touches the label.

### 4. BUG-PHOTO-DELETE-ACTOR — modal + list DELETE was broken
Both `deletePhoto()` (Saved Photos list) and `deletePhotoFromModal()` were calling `DELETE /api/photos/{id}` without `?actor_id=...`, but the backend requires it (`actor_id: str = Query(..., alias="actor_id")`). Every soft-delete attempt would 422. Both fixed to pass `getCuratorId()` as the query param.

### 5. requirements-gpu.txt — Pillow pinned
`Pillow==12.2.0` added with explanatory comment so fresh-laptop installs auto-pull it. Closes the loop on `docs/PILLOW-VENV-INSTALL.md` — that doc remains as the diagnostic reference, but the install step is now automatic.

### 6. Stale task housekeeping
Three in_progress tasks marked completed (real status, not aspirational): #219 BUG-208 (BB Walk 38/0 closes it), #228 BUG-209 (archive-writer auto-chain disabled), #153 SPANTAG (Commit 3 promoted active per CLAUDE.md changelog).

---

## Two commits, in order — run from `/mnt/c/Users/chris/hornelore`

### Commit 1 — Photo system improvements (5 files)

```bash
cd /mnt/c/Users/chris/hornelore
git add server/code/services/photos/repository.py server/code/api/routers/photos.py server/code/services/photo_intake/exif.py ui/photo-intake.html ui/js/photo-intake.js

git commit -m "feat(photos): people/event post-upload editing + 3 polish fixes

WO-PHOTO-PEOPLE-EDIT-01: View/Edit modal now lets curator add/remove
people + events on saved photos. Was previously single-photo-form-only,
forcing delete+reupload for any post-hoc tagging.

Backend (replace-all semantics on the join tables):
  - _PhotoPatch model accepts people / events arrays
  - PATCH endpoint diffs internally: delete_all + add_back
  - New repository helpers delete_all_photo_people / delete_all_photo_events
  - Empty array = wipe all. Absent = leave untouched (matches existing
    field-level semantics).

Frontend:
  - Modal renders existing people / events on open
  - +Add buttons mirror single-photo form pattern
  - Save sends current state, repopulates after round-trip

Plus 3 polish fixes from the overnight code review:

P1.1 silent EXIF corrupt-tag flag: exif.py now distinguishes 'no GPS
tag' from 'GPS tag present but unparseable' (zero-denominator DMS /
out-of-range coords). Modal shows new GPS UNREADABLE pill with
tooltip so curator knows to type location manually instead of
assuming phone didn't capture it.

P1.3 PATCH location_label recalc: needs_confirmation now recomputes
when location_label OR location_source changes (was only source).
Closes edge where hand-editing the EXIF-GPS-derived label leaves
needs_confirmation stale at False.

BUG-PHOTO-DELETE-ACTOR: both delete paths (Saved Photos list +
modal Delete) were calling DELETE /api/photos/{id} without the
required ?actor_id= query param. Backend was 422-ing every attempt.
Fixed both to pass getCuratorId() as the param.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Commit 2 — Pillow in requirements + morning brief

```bash
git add requirements-gpu.txt docs/MORNING-2026-04-26-night2.md

git commit -m "chore(deps): pin Pillow in requirements-gpu + overnight brief

Pillow==12.2.0 added to requirements-gpu.txt with explanatory comment
referencing docs/PILLOW-VENV-INSTALL.md. Closes the fresh-laptop
trap that ate ~90 minutes 2026-04-25 night — install is now
automatic via pip install -r requirements-gpu.txt instead of
needing the operator to remember the manual install step.

docs/MORNING-2026-04-26-night2.md: handoff brief covering
overnight #2 work (PEOPLE-EDIT + P1 polish + DELETE actor_id +
Pillow pin + stale task housekeeping).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"

git push
git status
git log --oneline -8
```

---

## Verification sequence

**Stack cycle required** for backend changes (PATCH endpoint + exif.py + repository.py).

After cycle + hard refresh:

### PEOPLE-EDIT verify (~3 min)
1. Photo Intake → click any saved photo → modal opens
2. **New: People + Events sections visible** under the Ready checkbox
3. Click **+ Add person** → empty input row appears → type "Mom" → click Save Changes
4. Status: "Saved." → close + reopen modal → "Mom" should still be there
5. Click **Remove** on the Mom row → click Save → reopen → person is gone
6. Repeat with Events ("Easter 2026" or similar)
7. Quick log check: `grep '\[photos\]\[patch\]\[people\]' .runtime/logs/api.log | tail -3` → should show `deleted=N added=M` per save

### P1.1 GPS UNREADABLE verify (low-priority — only fires on photos with corrupted EXIF GPS)
- Hard to reproduce naturally. Expected behavior: a photo where the EXIF GPS block exists but has `(0, 0, None)` DMS or out-of-range coords gets a red "location · GPS UNREADABLE" pill in the modal source-attribution row instead of the default "MISSING" pill.

### Modal Delete verify
1. Upload a throwaway photo via Quick Batch Upload
2. Click View / Edit on it → click **Delete** in modal
3. Confirm soft-delete
4. Photo should disappear from Saved Photos panel
5. **Before this fix**, the request 422'd silently and the photo stayed
6. `grep 'DELETE /api/photos' .runtime/logs/api.log | tail -3` should show 200 status

### Pillow loud warning verify
- Already verified yesterday — log line `[photos][startup] Pillow available: version=12.2.0` should appear at server boot. Now also auto-installs on fresh laptop via `pip install -r requirements-gpu.txt`.

---

## What's NOT done (next session)

- **WO-AUDIO-NARRATOR-ONLY-01 frontend** (~3 hrs live with you in browser; gate 3 of the 7-gate readiness checklist)
- **Photo automated test harness** modeled on BB Walk Test (would catch class of regressions like PRECISION-DAY before they ship). Synthesizing JPEGs in the browser is non-trivial — would need base64-encoded fixtures. Stretch goal, not a blocker.
- **P2 cleanups** from the code review (redundant null checks in repository, localStorage-full toast in bio-builder-core).
- **BUG-217** narrator-room topbar style pill desync (cosmetic).
- **BUG-225** [bb-drift] KEY MISMATCH console spam (noise; legacy migration leftover).
- **BUG-193** camera not working post-restart on archive branch (covered by recent camera fixes but not formally verified).

---

## Files I touched this overnight pass

Backend (3):
- `server/code/services/photos/repository.py` (delete_all_photo_people + delete_all_photo_events)
- `server/code/api/routers/photos.py` (PATCH model + handler extended for people/events; P1.3 location_label recalc)
- `server/code/services/photo_intake/exif.py` (P1.1 GPS unparseable flag)

Frontend (2):
- `ui/photo-intake.html` (modal People/Events sections)
- `ui/js/photo-intake.js` (modal helpers, populate, save arrays, +Add wiring, DELETE actor_id fix x2, P1.1 pill)

Config + docs (2):
- `requirements-gpu.txt` (Pillow pinned)
- `docs/MORNING-2026-04-26-night2.md` (this brief)

All Python AST-parses clean. JS parses clean (node -c). HTML balanced (8 tag categories, all matched).

---

## Rollup — five days of photo work

Where the photo system is now:

**Live + tested in browser:**
- POST /api/photos (upload) with EXIF auto-fill
- POST /api/photos/preview (Review File Info) — Nominatim + Plus Code + auto-description
- GET /api/photos (list) with narrator_ready filter
- PATCH /api/photos/{id} — full metadata + people + events (NEW tonight)
- DELETE /api/photos/{id} — soft-delete with actor_id (FIXED tonight)
- View/Edit modal with full metadata editing including people/events
- Multi-file batch upload (sequential, narrator-id snapshot at queue time)
- Narrator-room photo lightbox (BUG-240, full-screen view)

**Bugs closed in the photo lane:** BUG-238 (narrator_ready filter), BUG-239 (modal), BUG-240 (lightbox), BUG-221B (purge utility), BUG-PHOTO-CORS-01 (CORS spec violation), BUG-PHOTO-LIST-500 (import depth), BUG-PHOTO-PRECISION-DAY (DB CHECK constraint), BUG-PHOTO-DELETE-ACTOR (missing query param). 8 bugs total, all named root cause.

**Phase 2 deferred (post-demo):** photo elicit / narrator memory write, conflict detector, review queue UI, Google Maps geocoder swap.

Stack is down per yesterday's handoff — start when you're ready. Good morning Chris.
