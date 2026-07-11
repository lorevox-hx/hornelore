#!/usr/bin/env bash
set -euo pipefail

cd /mnt/c/Users/chris/hornelore

echo "=== Fix Travel Doc Evidence Setup ==="

# ------------------------------------------------------------
# 1) Install Tesseract language packs
# ------------------------------------------------------------
echo ""
echo "=== Installing Tesseract + language packs ==="

sudo apt update
sudo apt install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-deu tesseract-ocr-ita

if apt-cache show tesseract-ocr-hrv >/dev/null 2>&1; then
  sudo apt install -y tesseract-ocr-hrv
else
  echo "NOTE: tesseract-ocr-hrv not available from apt on this machine"
fi

if apt-cache show tesseract-ocr-slv >/dev/null 2>&1; then
  sudo apt install -y tesseract-ocr-slv
else
  echo "NOTE: tesseract-ocr-slv not available from apt on this machine"
fi

# ------------------------------------------------------------
# 2) Select venv
# ------------------------------------------------------------
echo ""
echo "=== Selecting venv ==="

if [ -d ".venv-gpu" ]; then
  VENV=".venv-gpu"
elif [ -d ".venv" ]; then
  VENV=".venv"
else
  echo "ERROR: no .venv-gpu or .venv found"
  exit 1
fi

echo "Using venv: $VENV"

# ------------------------------------------------------------
# 3) Update requirements-gpu.txt cleanly
# ------------------------------------------------------------
echo ""
echo "=== Updating requirements-gpu.txt ==="

REQ="requirements-gpu.txt"

add_req() {
  PKG="$1"
  if grep -Eq "^[[:space:]]*${PKG}([=<>~![:space:]]|$)" "$REQ"; then
    echo "OK already in requirements: $PKG"
  else
    echo "$PKG" >> "$REQ"
    echo "ADDED to requirements: $PKG"
  fi
}

add_req "pytesseract"
add_req "httpx"
add_req "beautifulsoup4"
add_req "readability-lxml"
add_req "lxml_html_clean"

# ------------------------------------------------------------
# 4) Install Python packages into the venv
# ------------------------------------------------------------
echo ""
echo "=== Installing Python packages into $VENV ==="

"$VENV/bin/python" -m pip install --upgrade pip

"$VENV/bin/python" -m pip install \
  pytesseract \
  httpx \
  beautifulsoup4 \
  readability-lxml \
  lxml_html_clean

# ------------------------------------------------------------
# 5) Backup and update .env
# ------------------------------------------------------------
echo ""
echo "=== Updating .env ==="

if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    cp .env.example .env
    echo "Created .env from .env.example"
  else
    touch .env
    echo "Created empty .env"
  fi
fi

cp .env ".env.backup.$(date +%Y%m%d_%H%M%S)"
echo "Backed up .env"

# Determine OCR languages actually installed.
OCR_LANGS="eng"

if tesseract --list-langs 2>/dev/null | grep -qx "deu"; then
  OCR_LANGS="${OCR_LANGS}+deu"
fi

if tesseract --list-langs 2>/dev/null | grep -qx "ita"; then
  OCR_LANGS="${OCR_LANGS}+ita"
fi

if tesseract --list-langs 2>/dev/null | grep -qx "hrv"; then
  OCR_LANGS="${OCR_LANGS}+hrv"
fi

if tesseract --list-langs 2>/dev/null | grep -qx "slv"; then
  OCR_LANGS="${OCR_LANGS}+slv"
fi

echo "Using OCR languages: $OCR_LANGS"

set_env() {
  KEY="$1"
  VALUE="$2"
  TMP="$(mktemp)"
  grep -v -E "^${KEY}=" .env > "$TMP" || true
  printf "%s=%s\n" "$KEY" "$VALUE" >> "$TMP"
  mv "$TMP" .env
}

set_env "HORNELORE_TRIPS" "1"
set_env "HORNELORE_TRIP_INTERVIEW_CONTEXT" "1"
set_env "HORNELORE_TRIP_STORY_CAPTURE" "1"

set_env "HORNELORE_PHOTO_ENABLED" "1"
set_env "HORNELORE_PHOTO_INTAKE" "1"

set_env "HORNELORE_PHOTO_OCR" "1"
set_env "HORNELORE_OCR_PROVIDER" "tesseract"
set_env "HORNELORE_OCR_LANGS" "$OCR_LANGS"
set_env "HORNELORE_OCR_CMD" ""

set_env "HORNELORE_PUBLIC_LOOKUP" "1"
set_env "HORNELORE_PUBLIC_LOOKUP_PROVIDER" "url_only"
set_env "HORNELORE_PUBLIC_LOOKUP_AUTO" "0"
set_env "HORNELORE_PUBLIC_LOOKUP_CMD" ""
set_env "HORNELORE_SEARXNG_URL" ""
set_env "BRAVE_SEARCH_API_KEY" ""

set_env "HORNELORE_PHOTO_VISION" "0"
set_env "HORNELORE_VISION_PROVIDER" "off"
set_env "HORNELORE_VISION_CMD" ""

set_env "HORNELORE_PHOTO_CONTEXT_AUTO_DRAFT" "0"

# ------------------------------------------------------------
# 6) Final verification
# ------------------------------------------------------------
echo ""
echo "=== Tesseract version ==="
tesseract --version | head -1

echo ""
echo "=== Tesseract languages ==="
tesseract --list-langs

echo ""
echo "=== Python imports ==="
"$VENV/bin/python" -c "import pytesseract, httpx, bs4, readability, PIL, lxml; print('imports OK')"

echo ""
echo "=== Evidence flags ==="
grep -E "HORNELORE_TRIPS|HORNELORE_TRIP_INTERVIEW_CONTEXT|HORNELORE_TRIP_STORY_CAPTURE|HORNELORE_PHOTO_ENABLED|HORNELORE_PHOTO_INTAKE|HORNELORE_PHOTO_OCR|HORNELORE_OCR_PROVIDER|HORNELORE_OCR_LANGS|HORNELORE_PUBLIC_LOOKUP|HORNELORE_PUBLIC_LOOKUP_PROVIDER|HORNELORE_PUBLIC_LOOKUP_AUTO|HORNELORE_PHOTO_VISION|HORNELORE_VISION_PROVIDER|HORNELORE_PHOTO_CONTEXT_AUTO_DRAFT" .env

echo ""
echo "=== Requirements evidence packages ==="
grep -nE "pytesseract|httpx|beautifulsoup4|readability-lxml|lxml_html_clean" requirements-gpu.txt

echo ""
echo "DONE. Restart the Hornelore stack before testing OCR in Travel Doc Lab."
