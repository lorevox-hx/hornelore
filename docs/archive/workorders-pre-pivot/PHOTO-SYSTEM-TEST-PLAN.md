# Photo System Test Plan

**Status:** Phase 1 (WO-LORI-PHOTO-SHARED-01) live + Phase 2 partial (EXIF auto-fill, multi-file batch upload, view/edit modal — landed 2026-04-25 night).
**Owner:** Chris
**Gates this protects:** photo-surface readiness for parent demo (~3 days out).

---

## Why this exists

The photo system has three interacting layers that each fail differently:

1. **Backend** — `/api/photos` router gated by `HORNELORE_PHOTO_ENABLED`. EXIF auto-fill gated by `HORNELORE_PHOTO_INTAKE`. Storage to `DATA_DIR/photos/`. SQLite via `photo_repo`.
2. **Curator UI** — `photo-intake.html` single-photo form + batch upload card + view/edit modal.
3. **Narrator UI** — `narrator-room` Photos view, filtered by `narrator_ready=true` (BUG-238 fix).

A passing demo requires all three green for **two real-world inputs**: phone photos with full EXIF (Lima trip-style), and scanned old prints with no EXIF (parents' childhood photos).

---

## Pre-test setup (one-time)

`.env` must contain:

```
HORNELORE_PHOTO_ENABLED=1
HORNELORE_PHOTO_INTAKE=1
```

Stack must be cycled after editing `.env` (the env-var read is per-request, but the value is captured from the uvicorn child's environment at fork time).

Quick verify the flags are live:

```bash
curl -s http://localhost:8000/api/photos/health | jq
# Expected: {"ok":true,"enabled":true}

grep -c '\[photos\]\[exif\]' /mnt/c/Users/chris/hornelore/.runtime/logs/api.log || echo "no EXIF fires yet (expected before any upload)"
```

---

## Manual smoke test (15 minutes)

Run all 8 cases. PASS = matches expected. FAIL = anything else.

### Case 1 — Single photo with full EXIF (phone-camera roundtrip)

**Setup:** Pick a recent phone photo with both date and GPS in EXIF (e.g. the Lima photo).

**Steps:**
1. Operator tab → 📷 Photo Intake → standalone tab opens
2. Pick narrator from dropdown
3. "Add a Photo" form: leave date and location BLANK
4. Choose file
5. Check "Ready to show"
6. Save Photo

**Expected:**
- Status: "Saved." (green)
- Saved Photos panel shows new card within ~1s
- Card subtitle reads `<EXIF date>` · `<location_label or "GPS lat,lng">`
- `grep '\[photos\]\[exif\]' .runtime/logs/api.log | tail -1` shows `auto-filled date,gps for photo_id=...`

**Why it matters:** Confirms EXIF parser, flag plumbing, dedupe, and storage all work end-to-end.

---

### Case 2 — Single photo with NO EXIF (scanned print simulation)

**Setup:** Take any phone photo and either (a) screenshot it, or (b) save-as a PNG (PNGs typically strip EXIF), or (c) use a known scanned-from-print JPG.

**Steps:**
1. Same flow as Case 1, but this file has no EXIF date/GPS
2. Save with all date/location fields blank

**Expected:**
- Status: "Saved." (green) — no error from EXIF parse failure
- Saved Photos card subtitle is empty (no date · no location)
- `grep '\[photos\]\[exif\]' .runtime/logs/api.log | tail -1` shows NO new line (auto-fill log only fires when something was filled)
- Click the thumbnail → modal opens → source-attribution pills show `date · MISSING`, `location · MISSING`
- Modal "Raw EXIF" details panel says "(no EXIF metadata in this file...)"

**Why it matters:** Confirms graceful no-EXIF fallback. This is the parents' childhood-photos case.

---

### Case 3 — Add metadata to an old/no-EXIF photo via the modal (BUG-239)

**Steps (continuing from Case 2):**
1. Modal still open from Case 2
2. Type "1962" in Date, choose "year" precision
3. Type "Williston, ND" in Location, choose "spoken_place"
4. Type a description: "Mom's family home in 1962"
5. Click Save Changes

**Expected:**
- Status: "Saved." (green)
- Source-attribution pills update: `date · typed by curator`, `location · typed by curator`
- Completeness pills all flip green
- Closing the modal and reopening shows fields persisted
- Saved Photos card subtitle now shows `1962 (year) · Williston, ND`

**Why it matters:** This is THE flow for old scanned photos. Without this, the demo for Mom's photos fails.

---

### Case 4 — Multi-file batch upload (5+ photos, mixed EXIF)

**Steps:**
1. Quick Batch Upload section → Pick narrator (auto-syncs with single-photo dropdown)
2. Drag a folder of 5+ photos into the drop zone (or click "choose files")
3. Click Upload All

**Expected:**
- Each card flips queued → uploading → saved sequentially
- Status: "Done. N saved" (green)
- Photos with EXIF show `Saved — <date> · GPS <lat>, <lng>` on the card meta line
- Photos without EXIF show `Saved.` only
- Saved Photos panel populates with all of them

**Why it matters:** This is the bulk-import path for ingesting a phone camera roll for a narrator.

---

### Case 5 — Duplicate dedup (same file twice)

**Steps:**
1. Upload the Lima photo (Case 1)
2. Upload it AGAIN

**Expected:**
- Single-photo flow: Status shows "This photo is already saved for this narrator."
- Batch flow: Card pill shows "duplicate" (yellow), meta says "Already saved for this narrator (dedup match by file hash)."
- Saved Photos panel does NOT get a duplicate row

**Why it matters:** Operators will re-drop the same folder accidentally. Dedup means no garbage in the archive.

---

### Case 6 — Non-image file rejected

**Steps:**
1. Try to upload a .txt or .pdf file via the batch picker

**Expected:**
- Batch UI: file is filtered out client-side (skipped count in batch status)
- If it gets past the client filter, server returns 415 Unsupported Media Type
- No row in Saved Photos

**Why it matters:** Operator might drag a misc folder; we shouldn't store non-images.

---

### Case 7 — Narrator-ready filter (BUG-238)

**Steps:**
1. Upload a photo with `narrator_ready=false` (uncheck the box)
2. Switch to Narrator Session tab → Photos view
3. Verify the unready photo is NOT shown
4. Go back to Photo Intake → click "Mark ready" on that photo
5. Refresh the Narrator Session Photos view

**Expected:**
- Step 3: photo absent
- Step 5: photo now visible

**Why it matters:** Mom/Dad must only see vetted photos during the session. Without this, in-progress curator entries leak into the conversation.

---

### Case 9 — Review File Info preview (visualschedulebot-style prefill)

**Setup:** Same Lima photo (or any phone JPEG with EXIF date + GPS).

**Steps:**
1. Single-photo "Add a Photo" form
2. Pick narrator from dropdown
3. Choose file → **thumbnail preview appears below the file picker**
4. Click the big blue **Review File Info** button
5. Wait ~1-3 sec (Nominatim reverse-geocode round-trip)

**Expected:**
- Status reads `Found: date, GPS, city, Plus Code, 48 EXIF tags` (counts depend on file)
- Description field auto-fills with sentence like `"This image is from Tuesday, April 21, 2026 at 2:10 PM at RWRJ+2V Watrous, NM, USA"` + small blue "auto-generated" pill next to label
- Date field shows `2026-04-21`, precision dropdown set to `exact` + blue "from EXIF" pill
- Location field shows `RWRJ+2V Watrous, NM, USA` + green "from phone GPS" pill, source dropdown set to `exif_gps`
- All three fields are still editable — curator can override anything before clicking Save Photo

**Then click Save Photo:**
- Existing upload flow runs (upload-time EXIF auto-fill is now no-op because curator already supplied date/location)
- Saved Photos card shows the auto-generated description as title

**Why it matters:** This is the curator's primary path for ingesting phone photos with full metadata in one click. Matches Chris's existing visualschedulebot photo admin UX.

**Failure modes:**
- "Review failed: HTTP 500" → backend error, check `grep '\[photos\]\[preview\]' .runtime/logs/api.log`
- Description fills but location is just `Watrous, NM, USA` (no Plus Code) → Plus Code generator failed silently; check Pillow installed
- Description fills but no city, just GPS coords → Nominatim was unreachable; expected when offline; falls back gracefully
- Pills don't appear → CSS hadn't loaded; hard-refresh

---

### Case 8 — Edit cycle (round-trip persistence)

**Steps:**
1. Click any saved photo → modal opens
2. Edit date, location, description
3. Save
4. Close modal
5. Hard refresh the browser
6. Click the same photo

**Expected:**
- All edits survived the refresh
- Source-attribution pills stay correct after reload (date · typed by curator, etc.)

**Why it matters:** Confirms PATCH endpoint + UI rehydration are both correct.

---

## Acceptance criteria for parent-demo green light

All 8 cases must PASS. Additionally:

- `grep -E 'ERROR|Traceback' /mnt/c/Users/chris/hornelore/.runtime/logs/api.log | grep -i photo | tail -10` returns no recent entries
- `du -sh /mnt/c/hornelore_data/photos/` shows growth proportional to uploaded count (sanity check that files actually landed on disk)
- A test session with the test narrator (Corky), with 3 photos marked ready, shows them in the narrator-room Photos view in the order they were uploaded

---

## Automated EXIF unit test (optional, ~5 min run)

A small Python script validates the EXIF parser handles the common cases without round-tripping through the full upload flow. Useful when iterating on `services/photo_intake/exif.py`.

Run from repo root:

```bash
cd /mnt/c/Users/chris/hornelore
python3 scripts/test_photo_exif.py
```

The script writes a synthesized JPEG with known EXIF tags (date, GPS), reads it back through `extract_exif()`, and asserts the round-trip values match. It also tests the no-EXIF case (PNG without EXIF) and the corrupt-EXIF fail-soft path.

Expected output: `OK 3/3` (round-trip, no-EXIF, corrupt). Any FAIL means the parser regressed.

---

## What's NOT covered (deferred to Phase 2 proper)

- **Reverse geocoding** — GPS coords are stored as raw lat/lng but no city/country lookup happens. The location_label field stays whatever the curator typed. Phase 2 (`WO-LORI-PHOTO-INTAKE-01` full release) wires `geocode_real.py` for this.
- **Conflict detector** — when a narrator says "this photo was 1968" but EXIF says 2018, we don't surface that conflict yet. Phase 2's conflict_detector.py + review queue handle this.
- **People / event editing post-upload** — modal edits the metadata fields but not the people/events lists. Use the single-photo form's people/events on the way in, or hit the API directly for post-upload edits.
- **Photo elicit / narrator-side memory capture** — Phase 2 (`WO-LORI-PHOTO-ELICIT-01`) wires Lori's reactions and the per-show memory write.
- **Multi-narrator sharing** — each photo lives under exactly one narrator. Sharing a photo across multiple family members would need `photo_people` rows + a separate UI flow. Not needed for the demo (per-narrator albums are fine).

---

## Failure-mode debug map

| Symptom | First check |
|---|---|
| `Upload failed: {"detail":"photo surface disabled"}` | `.env` missing `HORNELORE_PHOTO_ENABLED=1`; cycle stack |
| Upload succeeds but EXIF doesn't fill | `.env` missing `HORNELORE_PHOTO_INTAKE=1`; OR file has no EXIF (open in any phone gallery to verify); OR `grep '\[photos\]\[exif\]' .runtime/logs/api.log` shows no fire |
| Narrator dropdown empty | `/api/people` issue, unrelated to photo router |
| Save fails with 500 | `grep -A 20 'photo' .runtime/logs/api.log \| tail -40` for the traceback |
| Modal won't open | Hard refresh (cache); check console for JS error |
| Narrator sees unready photos | BUG-238 fix not deployed; verify `app.js` line ~575 has `&narrator_ready=true` in the fetch URL |

---

## Revision history

| Date | What changed |
|---|---|
| 2026-04-25 | Initial test plan, post-EXIF-auto-fill + multi-file batch + view/edit modal landing. |
