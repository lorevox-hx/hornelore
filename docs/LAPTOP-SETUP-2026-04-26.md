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

# Document Archive lane — WO-MEDIA-ARCHIVE-01 (LANDED 2026-04-26).
# When 1, /api/media-archive/* serves live; when 0, every endpoint
# returns 404 except /health (always reports {ok:true, enabled:bool}).
# Curator page: /ui/media-archive.html (launchable from Media tab).
HORNELORE_MEDIA_ARCHIVE_ENABLED=1

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
# Expected to show at least:
#   HORNELORE_PHOTO_ENABLED=1
#   HORNELORE_PHOTO_INTAKE=1
#   HORNELORE_MEDIA_ARCHIVE_ENABLED=1
```

**Note on `.env` not riding git:** `.env` is gitignored (it carries the HuggingFace token), so `git pull` on a fresh laptop won't bring these flag additions. If you're rebuilding an existing laptop and the flags are missing, append them:
```bash
cat >> .env <<'EOF'

HORNELORE_PHOTO_ENABLED=1
HORNELORE_PHOTO_INTAKE=1
HORNELORE_MEDIA_ARCHIVE_ENABLED=1
EOF
grep -n '^HORNELORE' .env
```

## 6. Data directory bootstrap

```bash
mkdir -p /mnt/c/hornelore_data/db
mkdir -p /mnt/c/hornelore_data/memory/archive/photos
mkdir -p /mnt/c/hornelore_data/memory/archive/sessions
# Document Archive root (auto-created by services/media_archive/storage.py
# on first upload, but creating it up-front avoids a one-time race).
mkdir -p /mnt/c/hornelore_data/media/archive
```

The DB schema initializes itself on first server start (per `server/code/api/db.py:init_db()` + `server/code/db/migrations/`). The migrations runner at `server/code/db/migrations_runner.py` auto-applies any new `NNNN_*.sql` file in `server/code/db/migrations/` exactly once (tracked in the `schema_migrations` table). On first boot after a `git pull` that includes new migration files, expect a `[migrations]` log line for each newly-applied file. **For WO-MEDIA-ARCHIVE-01 specifically, `0003_media_archive.sql` creates 4 tables (items + people + family_lines + links) with locked enums — applies automatically, no manual SQL needed.**

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

# 2. Document Archive surface live (WO-MEDIA-ARCHIVE-01)
curl -s http://localhost:8000/api/media-archive/health | jq
# Expected: {"ok":true,"enabled":true,"storage_root":"/mnt/c/hornelore_data/media/archive/..."}

# 3. Pillow loaded by uvicorn (the loud-warning check from P2.2)
grep '\[photos\]\[startup\]' /mnt/c/Users/chris/hornelore/.runtime/logs/api.log | tail -1
# Expected: [photos][startup] Pillow available: version=12.2.0
grep '\[media_archive\]\[startup\]' /mnt/c/Users/chris/hornelore/.runtime/logs/api.log | tail -3
# Expected: 3 lines — Pillow available, pdf2image available (or NOT INSTALLED),
# pypdf available (or NOT INSTALLED). Missing pdf2image/pypdf is non-fatal;
# missing Pillow IS fatal for thumbnails.

# 4. Migration applied
sqlite3 /mnt/c/hornelore_data/db/hornelore.sqlite3 \
  "SELECT filename, applied_at FROM schema_migrations ORDER BY filename;"
# Expected: at least 0003_media_archive.sql in the list with a timestamp.

# 5. EXIF parser smoke (no live photos needed — synthesizes its own JPEG)
.venv-gpu/bin/python3 scripts/test_photo_exif.py
# Expected: OK 3/3
```

If all five pass, the install is good. Open the UI:

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

## 11. Document Archive (WO-MEDIA-ARCHIVE-01) bring-up

The Document Archive lane is a separate curator surface from Photo Intake. It accepts PDFs / scanned documents / handwritten notes / genealogy outlines / letters / certificates / clippings — anything that's source material rather than a memory-prompt photo. Photo Intake stays image-only; PDFs go here.

Locked product rule: **Preserve first. Tag second. Transcribe / OCR third. Extract candidates only after that. NEVER auto-promote to truth.**

### What you need installed

All three are pinned in `requirements-gpu.txt` so a fresh `pip install -r requirements-gpu.txt` covers everything. If you're rebuilding an existing venv:

```bash
.venv-gpu/bin/pip install Pillow==12.2.0 pypdf==6.4.1 pdf2image==1.17.0
```

Roles:

| Package | Required? | What breaks if missing |
|---|---|---|
| `Pillow==12.2.0` | YES | Image thumbnails fail silently; uploads still succeed but list shows broken-image icons |
| `pypdf==6.4.1` | RECOMMENDED | PDF page-count detection becomes NULL (curator can't see "18 pgs" in the list) |
| `pdf2image==1.17.0` | OPTIONAL | PDF first-page thumbnails fall back to inline SVG file-icon placeholder |
| `poppler-utils` (apt) | OPTIONAL | pdf2image installs but produces no output; same fallback as above |

Install poppler-utils for real PDF thumbnails:
```bash
sudo apt install -y poppler-utils
```

The startup self-check logs all four states loudly to api.log on uvicorn boot, so you can verify after restart:
```bash
grep '\[media_archive\]\[startup\]' /mnt/c/Users/chris/hornelore/.runtime/logs/api.log | tail -3
```

Expected good state:
```
[media_archive][startup] Pillow available: version=12.2.0
[media_archive][startup] pdf2image available; PDF thumbnails enabled
[media_archive][startup] pypdf available; PDF page-count detection enabled
```

### What gets created on first boot

The migrations runner auto-applies `0003_media_archive.sql` once on first stack start after pull. Verify:

```bash
sqlite3 /mnt/c/hornelore_data/db/hornelore.sqlite3 \
  ".tables" | tr ' ' '\n' | grep -i archive
# Expected: media_archive_items, media_archive_people,
#           media_archive_family_lines, media_archive_links
```

Storage root for uploaded files (auto-created on first upload, but pre-creating is harmless):
```
/mnt/c/hornelore_data/media/archive/
├── people/<person_id>/documents/<item_id>/   (when narrator is set)
├── family/<family_line>/documents/<item_id>/  (when family_line is set, no person)
└── unattached/<item_id>/                      (when neither is set)
```

Each `<item_id>/` directory contains the original file, a `meta.json` mirror of the DB row, and a `thumb.jpg` (when Pillow + pdf2image succeed).

### UI live verification (~2 min)

1. **Operator tab → Media tab.** A new launcher card shows: **📄 Document Archive**.
2. **Click Document Archive** → standalone curator page opens at `/ui/media-archive.html`.
3. **Pick a narrator (optional)** OR leave blank — many archive items aren't bound to a specific person.
4. **Drop or pick a PDF** (the Shong family genealogy is the canonical test fixture).
5. **Required fields**: Title + Document type. Everything else is optional.
6. **Click Save Archive Item** → status flips green to `"Saved · 18 pages · text: image_only_needs_ocr"` (page count requires `pypdf`; `text_status` is heuristic).
7. **Item appears in Saved Archive Items** with a generic PDF placeholder thumbnail (or a real first-page render if `pdf2image` + `poppler-utils` are installed).
8. **Click the thumbnail** → View / Edit modal opens with all metadata fields editable, plus **Open Original** button that opens the preserved PDF in a new tab.
9. **Edit any field, click Save Changes** → modal updates in place; refresh the page and confirm metadata persisted.

If steps 6 and 8 work, the Document Archive lane end-to-end is verified.

### Operator launcher entry points

Two ways to reach the curator page:

- **From the shell:** Operator tab → Media tab → 📄 Document Archive
- **Direct URL:** `http://localhost:8082/ui/media-archive.html`

The shell route also runs a health probe that disables the launcher if `HORNELORE_MEDIA_ARCHIVE_ENABLED=0`.

### Health-harness checks

The Bug Panel UI health harness now includes a `Document Archive` category with 4 checks:
- `/api/media-archive/health` reachable + enabled-flag readout
- archive list endpoint returns 200 (when enabled)
- `/ui/media-archive.html` page reachable
- Operator launcher card present in the Media tab

If any fail, the Bug Panel surfaces a FAIL row with the specific diagnostic.

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

**Document Archive (WO-MEDIA-ARCHIVE-01, landed 2026-04-26):**
- Separate curator lane parallel to /api/photos for PDFs / scanned docs / genealogy outlines / handwritten notes / letters / certificates / clippings
- POST /api/media-archive (multipart) with PDF + image + text MIME acceptance
- GET /api/media-archive (filters: person_id, family_line, document_type, candidate_ready, include_deleted)
- PATCH /api/media-archive/{id} with replace-all on people + family_lines + links
- DELETE /api/media-archive/{id}?actor_id=… (soft-delete, original file preserved on disk)
- GET /api/media-archive/{id}/file (serves original) + /thumb (Pillow + pdf2image when available, placeholder otherwise)
- Curator page at /ui/media-archive.html with upload form + saved list + View/Edit modal
- Operator launcher card in Media tab (📄 Document Archive)
- 4 new health-harness checks (route, list, page, launcher card)
- Locked product rule: archive-only default ON, candidate-ready opt-in, NEVER auto-promote to truth

**Pending (queued for build):**
- **WO-AUDIO-NARRATOR-ONLY-01 frontend** — per-turn webm capture via MediaRecorder, ~3 hrs live build with Chris in browser.
- **WO-MEDIA-WATCHFOLDER-01** — auto-import from `C:\Users\chris\Hornelore Scans\` straight into the Document Archive intake queue.
- **WO-MEDIA-OCR-01** — Tesseract-based OCR for scanned documents in the Document Archive (text_status auto-promotes from `image_only_needs_ocr` → `ocr_partial`/`ocr_complete`).
- **WO-MEDIA-ARCHIVE-CANDIDATES-01** — harvest items flagged `candidate_ready=true` and surface to Bio Builder review queue (no auto-promotion).

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
| 2026-04-26 (post-archive) | WO-MEDIA-ARCHIVE-01 landed. Added §11 Document Archive bring-up section (deps table, migration verification, UI smoke, health checks). Flipped `HORNELORE_MEDIA_ARCHIVE_ENABLED=1` from commented-future to active in §5. Updated §6 to pre-create the `media/archive/` directory + explain the migrations runner mechanic. Added curl + sqlite3 verification steps in §9. Added `pypdf==6.4.1` and `pdf2image==1.17.0` to requirements-gpu.txt for PDF page-count + first-page thumbnails (both fail-soft if missing). Moved WO-MEDIA-ARCHIVE-01 from Pending to Shipped inventory; minted WO-MEDIA-ARCHIVE-CANDIDATES-01 as a future lane for the candidate harvest workflow. |
