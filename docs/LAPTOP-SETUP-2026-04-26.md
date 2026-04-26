# Hornelore Laptop Setup — 2026-04-26

**Audience:** operator (Chris) bringing Hornelore up on a fresh laptop, OR rebuilding the existing laptop after deeper cleanup.
**Time:** 30–45 min for software, +10 min for the Canon scanner.
**Prerequisites:** Windows 11 + WSL2 Ubuntu, NVIDIA RTX-class GPU (RTX 5080 Laptop matches the production setup), Python 3.12, ~30GB free disk.

---

## 1. Repo + system prerequisites (WSL Ubuntu shell)

```bash
# WSL Ubuntu shell. From your home directory.
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip git curl jq sqlite3 build-essential

# Optional but recommended for image/PDF tooling that future
# Media Archive features will need (poppler for PDF previews,
# tesseract for the eventual OCR lane).
sudo apt install -y poppler-utils tesseract-ocr libheif-dev
```

## 2. Clone the repo

```bash
mkdir -p /mnt/c/Users/chris && cd /mnt/c/Users/chris
git clone <YOUR_REPO_URL> hornelore
cd hornelore
git checkout feature/wo-archive-audio-01      # or whichever branch is current
```

(If you're rebuilding existing, just `cd /mnt/c/Users/chris/hornelore && git pull`.)

## 3. GPU venv + Python deps

```bash
cd /mnt/c/Users/chris/hornelore

# Create venv (Python 3.12 to match production)
python3.12 -m venv .venv-gpu
source .venv-gpu/bin/activate

# 3a. PyTorch nightly for Blackwell sm_100 — MUST come first (not in requirements.txt
#     because nightly index breaks pip resolver if mixed with stable wheels).
pip install --pre torch torchvision torchaudio \
  --index-url https://download.pytorch.org/whl/nightly/cu128

# 3b. Everything else pinned in requirements-gpu.txt. INCLUDES Pillow 12.2.0
#     as of 2026-04-26 — was previously a manual install step that bit us
#     for ~90 minutes of silent thumbnail failures. See docs/PILLOW-VENV-INSTALL.md.
pip install -r requirements-gpu.txt

# 3c. Sanity check
python -c "import torch, transformers, bitsandbytes; print(torch.cuda.get_device_name(0))"
# Expected: NVIDIA GeForce RTX 5080 Laptop GPU
python -c "from PIL import __version__ as v; print('Pillow', v)"
# Expected: Pillow 12.2.0 (or higher)
```

**If `pip install -r requirements-gpu.txt` fails on Pillow specifically**, install manually:
```bash
.venv-gpu/bin/pip install --upgrade Pillow
```
Both the thumbnail generator and EXIF parser fail-soft when Pillow is missing — silent failures that ate 90 minutes of diagnosis on 2026-04-25. The doc `docs/PILLOW-VENV-INSTALL.md` is the canonical reference for that trap.

## 4. TTS venv (separate, smaller)

```bash
cd /mnt/c/Users/chris/hornelore
python3.12 -m venv .venv-tts
source .venv-tts/bin/activate
pip install -r requirements-tts.txt
deactivate
```

## 5. `.env` configuration

Create or edit `/mnt/c/Users/chris/hornelore/.env`:

```
# Data directory — where photos, archive, DB, audio, etc. live
DATA_DIR=/mnt/c/hornelore_data

# === FEATURE FLAGS ===
# Photo system (curator photo intake, Review File Info, narrator-room photo view)
HORNELORE_PHOTO_ENABLED=1
HORNELORE_PHOTO_INTAKE=1

# Future: Media Archive lane (PDFs, scanned documents, genealogy outlines).
# Uncomment ONCE WO-MEDIA-ARCHIVE-01 ships.
# HORNELORE_MEDIA_ARCHIVE_ENABLED=1

# === EXTRACTOR LANE FLAGS (defaults safe) ===
# These are off by default; the master eval baseline assumes default behavior.
# Only set when running specific eval flights — see CLAUDE.md "Standard eval command".
# HORNELORE_NARRATIVE=0
# HORNELORE_SPANTAG=0
# HORNELORE_PROMPTSHRINK=0
# HORNELORE_ATTRIB_BOUNDARY=0
# HORNELORE_AGE_VALIDATOR=0

# === OPTIONAL EXTERNAL SERVICES ===
# Google Maps geocoder (alternative to default Nominatim — needs billing).
# Leave commented unless you've set up Google Cloud + API key.
# GOOGLE_MAPS_API_KEY=
```

Verify the .env loads correctly:
```bash
cd /mnt/c/Users/chris/hornelore
grep '^HORNELORE' .env
# Expected to show at least: HORNELORE_PHOTO_ENABLED=1 and HORNELORE_PHOTO_INTAKE=1
```

## 6. Data directory bootstrap

```bash
mkdir -p /mnt/c/hornelore_data/db
mkdir -p /mnt/c/hornelore_data/memory/archive/photos
mkdir -p /mnt/c/hornelore_data/memory/archive/sessions
# Future Media Archive (created automatically by WO-MEDIA-ARCHIVE-01 storage layer):
# mkdir -p /mnt/c/hornelore_data/media/archive
```

The DB schema initializes itself on first server start (per `server/code/api/db.py:init_db()` + `server/code/db/migrations/`).

## 7. Desktop Hornelore folder (Windows side)

The Horne folder on the desktop holds the operator launchers (.bat files):
```
C:\Users\chris\Desktop\Horne\
  Start Hornelore.bat
  Stop Hornelore.bat
  Status.bat
  Reload API.bat
  Logs.bat
```

These are the operator-facing controls that wrap `scripts/start_all.sh` etc. Pull them from the existing Horne folder on the production laptop, or recreate via the templates in `scripts/`.

## 8. First start (cold boot ~4 min)

From your operator launcher OR manually:
```bash
cd /mnt/c/Users/chris/hornelore
bash scripts/start_all.sh
```

**Cold boot takes ~4 minutes**: the HTTP listener comes up in 60–70s, then the LLM weights + extractor warm up for another 2–3 minutes. A `curl /api/ping` only proves the socket is live, not that extraction is ready.

Wait until you see in `.runtime/logs/api.log`:
```
[readiness] Model warm and ready. Latency: ~0.7s
```

## 9. Verify install — three quick checks

```bash
# 1. API + photo surface live
curl -s http://localhost:8000/api/ping | jq
curl -s http://localhost:8000/api/photos/health | jq
# Expected: {"ok":true,"enabled":true} for both

# 2. Pillow loaded by uvicorn (the loud-warning check from P2.2)
grep '\[photos\]\[startup\]' /mnt/c/Users/chris/hornelore/.runtime/logs/api.log | tail -1
# Expected: [photos][startup] Pillow available: version=12.2.0

# 3. EXIF parser smoke (no live photos needed — synthesizes its own JPEG)
.venv-gpu/bin/python3 scripts/test_photo_exif.py
# Expected: OK 3/3
```

If all three pass, the install is good. Open the UI:

```
http://localhost:8082/ui/hornelore1.0.html
```

## 10. UI live verification (~2 min)

1. **Operator tab loads.** Dropdown shows the 3 narrators (Kent, Janice, Christopher).
2. **Pick Christopher Todd Horne.**
3. **Click "📷 Photo Intake"** launcher → standalone photo intake page opens.
4. **Pick a phone JPG with EXIF** → thumbnail preview appears + Review File Info button enables.
5. **Click "Review File Info"** → ~1–3s later, description / date / location auto-fill with attribution pills.
6. **Click "Save Photo"** → card appears in Saved Photos panel with a real thumbnail (not broken-image icon).

If steps 5 and 6 work, the entire photo system end-to-end is verified.

---

## Canon imageFORMULA R10 scanner setup

The R10 is the planned scanner for the Media Archive lane. It runs Windows-side via Canon's bundled software — Hornelore consumes the resulting files via the upcoming WO-MEDIA-ARCHIVE-01 import flow.

### Hardware connection

1. USB-C cable from R10 to laptop USB-A or USB-C port (R10 ships with both ends).
2. Power: the R10 is bus-powered — no AC adapter needed.
3. First connection: Windows installs the driver automatically. Wait for "Setting up device" toast to complete.

### Canon software install

The R10 ships with two pieces of self-contained software on the device itself:

1. **CaptureOnTouch Lite** — runs from the device when first connected (autorun popup or open This PC → R10 drive). This is the one-button scan-to-PDF tool — perfect for the genealogy-document use case.
2. **CaptureOnTouch (full)** — downloadable from the bundled link, adds OCR, batch profiles, output destinations.

Recommended for Hornelore: install the **full CaptureOnTouch** because it lets you set a default output folder (which Hornelore will watch in the future via `WO-MEDIA-WATCHFOLDER-01`).

Direct download (verify URL — Canon updates these):
https://www.usa.canon.com/support/p/imageformula-r10

### Configure the output folder

In CaptureOnTouch:
1. **Settings → Output Destination → Folder**
2. Set to: `C:\Users\chris\Hornelore Scans\`
3. Create that folder if it doesn't exist:
   ```
   mkdir "C:\Users\chris\Hornelore Scans"
   ```
4. **File naming**: set to include date + sequential number, e.g. `scan_{YYYY-MM-DD}_{0001}.pdf`. Makes it easy to find recent scans.
5. **Output format**: PDF (multi-page) for most documents; JPG for single-page photos that should go to the Photo Intake lane instead.

### Operator workflow (current — manual import)

Until WO-MEDIA-WATCHFOLDER-01 ships, the workflow is:

1. Place document on the R10's feed tray
2. Press the scanner's physical button (or click Scan in CaptureOnTouch)
3. R10 scans (~2-3 seconds per page; 18-page Shong PDF ≈ 1 minute)
4. PDF lands in `C:\Users\chris\Hornelore Scans\`
5. Open Hornelore → Operator tab → **Document Archive** (after WO-MEDIA-ARCHIVE-01 ships)
6. Drag the PDF from the Hornelore Scans folder into the Document Archive intake page
7. Tag with narrator / family line / document type / description
8. Save

### Operator workflow (after WO-MEDIA-WATCHFOLDER-01)

1. Same scan steps as above
2. Hornelore detects the new file in `Hornelore Scans/` and queues it under "Incoming Scans" in the Document Archive page
3. Operator reviews + tags + saves (or discards)

### Scanner cleaning + maintenance

The R10 has a feed roller that picks up dust quickly. Canon includes a cleaning kit; run it monthly with heavy use. If pages start jamming or scanning crooked, clean first before assuming hardware fault.

---

## Common pitfalls (lessons from real bring-ups)

### Pitfall 1: Pillow not in venv → silent thumbnail + EXIF failures
- **Symptom:** uploads succeed but no thumbnails show, no EXIF auto-fill happens, no errors in api.log.
- **Diagnosis:** `.venv-gpu/bin/python3 -c "from PIL import __version__; print(__version__)"` — if ImportError, that's the bug.
- **Fix:** `.venv-gpu/bin/pip install --upgrade Pillow`. As of 2026-04-26 this is in `requirements-gpu.txt` so a fresh install via `pip install -r requirements-gpu.txt` covers it. Full diagnostic: `docs/PILLOW-VENV-INSTALL.md`.

### Pitfall 2: `.env` env vars not propagating to uvicorn
- **Symptom:** `HORNELORE_PHOTO_ENABLED=1` in `.env` but `/api/photos/health` returns `{"enabled":false}`.
- **Cause:** stack was started before `.env` edit, OR shell that ran `start_all.sh` didn't source `.env`.
- **Fix:** `scripts/common.sh` sources `.env` with `set -a` so newly-launched stacks pick it up. If still failing, restart the stack and grep `[photos][startup]` in api.log.

### Pitfall 3: Stale uvicorn bytecode after a fix
- **Symptom:** code on disk has the fix but the running server still throws the old error.
- **Cause:** Python doesn't hot-reload imports. A module loaded at uvicorn boot stays in memory until the process restarts.
- **Fix:** stop and restart the stack via your operator launcher. No need to truncate logs first; new entries append.

### Pitfall 4: CORS spec violation (fixed 2026-04-25)
- `allow_origins=["*"]` + `allow_credentials=True` is invalid per CORS spec — browsers refuse the wildcard. As of 2026-04-25, `main.py` uses `allow_credentials=False` with the wildcard.
- If you ever need cookie-based cross-origin auth, switch to an explicit origins list AND flip credentials back to True. Both must change together.

### Pitfall 5: WSL filesystem path confusion
- Hornelore lives at `/mnt/c/Users/chris/hornelore` (Windows-mounted) NOT `~/hornelore`. Editing files in `~/hornelore` won't affect the running server.

### Pitfall 6: `git status` is git's truth, not the disk
- After any `git add`/`git commit`, always check `git status` to confirm the working tree is clean before launching new work. Per CLAUDE.md, the agent will refuse to start code-changing work on a dirty tree.

---

## Currently-shipped feature inventory (what this install gets you)

**Companion app (parent demo target):**
- Three-tab shell (Operator / Narrator Session / Media)
- Bio Builder Walk Test passing 38/0
- Narrator-switch hardening (BUG-208 generation guards + 5 follow-up bugs all closed)
- Two-sided text transcript per session (`/api/memory-archive/turn`)
- Per-session zip export
- WO-10C dementia-safe pacing (120s/300s/600s silence ladder)

**Photo system (WO-LORI-PHOTO-SHARED-01 + Phase 2 partial):**
- POST /api/photos with EXIF auto-fill (HORNELORE_PHOTO_INTAKE flag)
- POST /api/photos/preview (Review File Info — Nominatim reverse-geo + Plus Code + auto-description)
- GET/PATCH/DELETE /api/photos/{id} with full metadata + people + events editing
- GET /api/photos/{id}/image and /thumb (file-serving from disk)
- Multi-file batch upload with sequential save + per-file source attribution
- View/Edit modal with completeness pills + GPS map link + raw EXIF inspector
- Narrator-room photo lightbox (BUG-240) with full-screen view + caption + ESC close
- Bug Panel: Reset Identity (BUG-228) + Purge Test Narrators (BUG-221B)

**Pending (queued for build):**
- **WO-MEDIA-ARCHIVE-01** — separate Document Archive lane for PDFs / scanned documents / genealogy outlines / handwritten notes / certificates / clippings. Spec at `WO-MEDIA-ARCHIVE-01_Spec.md`. Build ETA: next session.
- **WO-AUDIO-NARRATOR-ONLY-01 frontend** — per-turn webm capture via MediaRecorder, ~3 hrs live build with Chris in browser.
- **WO-MEDIA-WATCHFOLDER-01** — auto-import from `C:\Users\chris\Hornelore Scans\` (post-MEDIA-ARCHIVE-01).
- **WO-MEDIA-OCR-01** — Tesseract-based OCR for scanned documents (post-MEDIA-ARCHIVE-01).

---

## Branch + version notes (as of 2026-04-26)

**Active branch:** `feature/wo-archive-audio-01`
**Master extractor lane baseline:** `r5h` — 70/104 v3=41/62, v2=35/62, mnw=2 (per CLAUDE.md changelog)

The branch is ahead of `main` because the parent-demo work has stayed on the audio archive feature branch. Merging back to main is parked until after the first parent session (so we can land the post-demo cleanup batch in one merge).

---

## Where to look when something breaks

| Symptom | First check |
|---|---|
| Photo upload fails | `tail -100 .runtime/logs/api.log` for traceback |
| No thumbnails anywhere | Pillow in venv (Pitfall 1) |
| Stack won't start | `bash scripts/status_all.sh` — see what's missing |
| GPU OOM at boot | restart, check `nvidia-smi` for stale processes |
| `/api/photos/health` returns disabled | `.env` flags + restart stack |
| Browser shows CORS error | the underlying request is probably 500 — check api.log |
| Stale uvicorn bytecode | restart stack (Pitfall 3) |

---

## Revision history

| Date | What changed |
|---|---|
| 2026-04-26 | Initial laptop setup doc. Captures all current install requirements + the Canon R10 scanner setup + the bring-up pitfalls accumulated through 2026-04-26 night. |
