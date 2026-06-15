# Pillow Required in GPU Venv

**Status:** Required.
**Symptom if missing:** Photo upload silently produces broken-image thumbnails AND empty EXIF metadata. Both fail-soft branches swallow the missing-Pillow error, so the only signal is downstream — no thumbnail, no auto-filled date/GPS.
**Discovered:** 2026-04-25 night. ~90 minutes lost diagnosing before the root cause was found.

---

## Why this doc exists

The Hornelore photo system uses Pillow (`PIL`) for two things:

1. **Thumbnail generation** — `server/code/services/photo_intake/thumbnail.py` opens the source image, applies EXIF orientation, resizes to 400px longest edge, writes `thumb_400.jpg`.
2. **EXIF parsing** — `server/code/services/photo_intake/exif.py` reads `DateTimeOriginal` + GPS coordinates from the upload to auto-fill date/location fields.

Both modules **defer** their `from PIL import ...` to inside the function body, so the server starts even when Pillow isn't installed. And both modules **fail-soft** — thumbnail returns `None`, EXIF returns the empty-shape dict — so upload doesn't 500. The result is a working-looking system that silently does nothing useful.

If you're seeing photos upload but the Saved Photos card has a broken-image icon and no date/GPS, this is your bug.

---

## Fix

Pillow needs to be installed in the **GPU venv** (the one that uvicorn runs from), not the system Python.

```bash
cd /mnt/c/Users/chris/hornelore
.venv-gpu/bin/pip install --upgrade Pillow
```

Then verify:

```bash
.venv-gpu/bin/python3 -c "from PIL import __version__ as v; print('Pillow', v)"
# Expected: Pillow 12.x.x or later
```

**No stack restart needed** — both `thumbnail.py` and `exif.py` use deferred imports (PIL is imported inside the function, not at module top), so the next upload picks up the new Pillow without a uvicorn cycle.

---

## Verification

After installing, run the EXIF parser smoke test against any phone JPEG with EXIF:

```bash
.venv-gpu/bin/python3 scripts/test_photo_exif.py /path/to/any/phone-photo.jpg
```

Expected: 4/4 PASS, with the real-photo case showing `date=...`, `gps=(lat,lng)`, `raw_exif_keys=N` where N is typically 30-60 for modern phone cameras.

If the test still says "missing dependency: No module named 'PIL'", the install went into the wrong venv. Make sure you used the full path `.venv-gpu/bin/pip` and not bare `pip`.

---

## Why isn't this in `requirements.txt`?

There IS a partial `requirements.txt` for the venv, but it doesn't currently include Pillow because the photo system shipped after the venv was last reset. Until that's reconciled, the install is manual on fresh laptop bring-up.

**Long-term fix tracked as:** add Pillow + the other photo deps (`urllib.request` is stdlib, no install needed; `requests` was avoided intentionally) to `requirements.txt` so `pip install -r requirements.txt` covers it.

---

## Other photo-system deps to know about

| Dep | Why | Status |
|---|---|---|
| **Pillow** | Thumbnails + EXIF parser | **Manual install required** (this doc) |
| `urllib.request` (stdlib) | Nominatim reverse-geocode | Always available |
| `sqlite3` (stdlib) | DB | Always available |
| `openlocationcode` (PyPI) | OPTIONAL — official Plus Code lib | Not used; we have a pure-Python implementation in `services/photo_intake/plus_code.py` |
| Google Maps API key | OPTIONAL — alternative reverse-geocoder | Not used; Nominatim (free, OSM) is the default |

---

## Defensive recommendation

The fail-soft behavior in `thumbnail.py` and `exif.py` is deliberate (the photo system shouldn't 500 just because Pillow is missing) — but the silent disablement is dangerous. A future cleanup pass should:

1. Log a single ERROR-level line at server startup if Pillow can't be imported, so the operator sees it in api.log.
2. Surface the disablement in `/api/photos/health` so the UI can show a banner like "thumbnails + EXIF auto-fill disabled".

These would have saved 90 minutes during the 2026-04-25 night smoke test.

---

## Revision history

| Date | What changed |
|---|---|
| 2026-04-25 | Created. Captures the silent-Pillow-missing trap that bit the 8-case smoke test. |
