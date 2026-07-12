#!/usr/bin/env bash
set -u

ROOT="${1:-/mnt/c/Users/chris/hornelore}"

echo "=== Travel Doc Evidence Setup Audit ==="
echo "Root: $ROOT"
echo ""

if [ ! -d "$ROOT" ]; then
  echo "FAIL: Repo folder not found: $ROOT"
  exit 1
fi

cd "$ROOT" || exit 1

# ------------------------------------------------------------
# Repo files
# ------------------------------------------------------------
echo "=== Repo files ==="

if [ -f "requirements-gpu.txt" ]; then
  echo "OK: requirements-gpu.txt exists"
else
  echo "MISSING: requirements-gpu.txt"
fi

if [ -f ".env" ]; then
  echo "OK: .env exists"
else
  echo "MISSING: .env"
fi

if [ -f ".env.example" ]; then
  echo "OK: .env.example exists"
else
  echo "MISSING: .env.example"
fi

echo ""

# ------------------------------------------------------------
# Venv
# ------------------------------------------------------------
echo "=== Python venv ==="

VENV=""

if [ -d ".venv-gpu" ]; then
  VENV=".venv-gpu"
elif [ -d ".venv" ]; then
  VENV=".venv"
fi

if [ -n "$VENV" ]; then
  echo "OK: using $VENV"
  "$VENV/bin/python" --version || true
else
  echo "MISSING: no .venv-gpu or .venv found"
fi

echo ""

# ------------------------------------------------------------
# Tesseract
# ------------------------------------------------------------
echo "=== Tesseract OCR system install ==="

if command -v tesseract >/dev/null 2>&1; then
  echo "OK: tesseract found"
  tesseract --version | head -1
else
  echo "MISSING: tesseract binary"
fi

echo ""

echo "=== Tesseract languages ==="

NEEDED_LANGS="eng deu ita hrv slv"

if command -v tesseract >/dev/null 2>&1; then
  INSTALLED_LANGS="$(tesseract --list-langs 2>/dev/null | tail -n +2 || true)"
  echo "$INSTALLED_LANGS"

  for lang in $NEEDED_LANGS; do
    if echo "$INSTALLED_LANGS" | grep -qx "$lang"; then
      echo "OK: OCR language $lang"
    else
      echo "MISSING: OCR language $lang"
    fi
  done
else
  echo "SKIP: tesseract not installed"
fi

echo ""

# ------------------------------------------------------------
# Requirements
# ------------------------------------------------------------
echo "=== requirements-gpu.txt evidence packages ==="

REQ="requirements-gpu.txt"
REQS="pytesseract httpx beautifulsoup4 readability-lxml lxml_html_clean"

if [ -f "$REQ" ]; then
  for pkg in $REQS; do
    if grep -Eq "^[[:space:]]*${pkg}([=<>~![:space:]]|$)" "$REQ"; then
      echo "OK: $pkg in $REQ"
    else
      echo "MISSING: $pkg in $REQ"
    fi
  done
else
  echo "SKIP: requirements-gpu.txt missing"
fi

echo ""

# ------------------------------------------------------------
# Python imports
# ------------------------------------------------------------
echo "=== Python import check ==="

if [ -n "$VENV" ]; then
  "$VENV/bin/python" - <<'PY'
mods = [
    ("pytesseract", "pytesseract"),
    ("httpx", "httpx"),
    ("bs4", "beautifulsoup4"),
    ("readability", "readability-lxml"),
    ("PIL", "Pillow"),
    ("lxml", "lxml"),
]
ok = True
for mod, name in mods:
    try:
        __import__(mod)
        print(f"OK: import {mod} ({name})")
    except Exception as e:
        ok = False
        print(f"FAIL: import {mod} ({name}) -> {e}")
if ok:
    print("Python imports OK")
else:
    print("Python imports need attention")
PY
else
  echo "SKIP: no venv"
fi

echo ""

# ------------------------------------------------------------
# .env flags
# ------------------------------------------------------------
echo "=== .env evidence flags ==="

ENV=".env"

KEYS="
HORNELORE_TRIPS
HORNELORE_TRIP_INTERVIEW_CONTEXT
HORNELORE_TRIP_STORY_CAPTURE
HORNELORE_PHOTO_ENABLED
HORNELORE_PHOTO_INTAKE
HORNELORE_PHOTO_OCR
HORNELORE_OCR_PROVIDER
HORNELORE_OCR_LANGS
HORNELORE_OCR_CMD
HORNELORE_PUBLIC_LOOKUP
HORNELORE_PUBLIC_LOOKUP_PROVIDER
HORNELORE_PUBLIC_LOOKUP_AUTO
HORNELORE_PUBLIC_LOOKUP_CMD
HORNELORE_SEARXNG_URL
BRAVE_SEARCH_API_KEY
HORNELORE_PHOTO_VISION
HORNELORE_VISION_PROVIDER
HORNELORE_VISION_CMD
HORNELORE_PHOTO_CONTEXT_AUTO_DRAFT
"

if [ -f "$ENV" ]; then
  for key in $KEYS; do
    if grep -q "^${key}=" "$ENV"; then
      val="$(grep "^${key}=" "$ENV" | tail -1)"
      count="$(grep -c "^${key}=" "$ENV")"
      if [ "$count" -gt 1 ]; then
        echo "DUPLICATE: $key appears $count times"
      else
        echo "OK: $val"
      fi
    else
      echo "MISSING: $key"
    fi
  done
else
  echo "SKIP: .env missing"
fi

echo ""

# ------------------------------------------------------------
# Recommended values
# ------------------------------------------------------------
echo "=== Recommended test values ==="
cat <<'EOF'
HORNELORE_TRIPS=1
HORNELORE_TRIP_INTERVIEW_CONTEXT=1
HORNELORE_TRIP_STORY_CAPTURE=1
HORNELORE_PHOTO_ENABLED=1
HORNELORE_PHOTO_INTAKE=1

HORNELORE_PHOTO_OCR=1
HORNELORE_OCR_PROVIDER=tesseract
HORNELORE_OCR_LANGS=eng+deu+ita+hrv+slv

HORNELORE_PUBLIC_LOOKUP=1
HORNELORE_PUBLIC_LOOKUP_PROVIDER=url_only
HORNELORE_PUBLIC_LOOKUP_AUTO=0

HORNELORE_PHOTO_VISION=0
HORNELORE_VISION_PROVIDER=off
HORNELORE_PHOTO_CONTEXT_AUTO_DRAFT=0
EOF

echo ""
echo "=== Audit complete ==="
echo "This script did not change anything."
