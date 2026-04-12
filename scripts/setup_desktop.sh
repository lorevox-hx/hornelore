#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────
# setup_desktop.sh — Set up Hornelore on a new/cloned machine
#
# Run from WSL inside the hornelore repo:
#   cd /mnt/c/Users/chris/hornelore
#   bash scripts/setup_desktop.sh
#
# What it does:
#   1. Creates hornelore_data directory (DB + TTS cache)
#   2. Copies .env.example → .env (if .env doesn't exist)
#   3. Creates .venv-gpu and installs requirements-gpu.txt
#   4. Creates .venv-tts and installs requirements-tts.txt
#   5. Installs Playwright + Chromium (for trainer preload)
#   6. Optionally copies the model from the source machine
#
# Prerequisites:
#   - WSL2 with Ubuntu 22.04
#   - Python 3.12 (python3.12 on PATH)
#   - NVIDIA CUDA drivers installed in WSL
# ──────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="/mnt/c/hornelore_data"
MODEL_DIR="/mnt/c/models/hornelore"

echo "═══════════════════════════════════════════════════"
echo "  Hornelore Desktop Setup"
echo "  Repo: $REPO_DIR"
echo "═══════════════════════════════════════════════════"
echo ""

# ── Step 1: Create data directories ──────────────────────────────
echo "▸ Step 1: Creating data directories..."
mkdir -p "$DATA_DIR"
mkdir -p "$DATA_DIR/tts_cache"
mkdir -p "$MODEL_DIR"
mkdir -p "$MODEL_DIR/hf_home"
echo "  ✓ $DATA_DIR"
echo "  ✓ $MODEL_DIR"
echo ""

# ── Step 2: .env file ────────────────────────────────────────────
echo "▸ Step 2: Setting up .env..."
if [ -f "$REPO_DIR/.env" ]; then
    echo "  ✓ .env already exists — skipping"
else
    cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
    echo "  ✓ Copied .env.example → .env"
    echo "  ⚠ EDIT .env and set your real HUGGINGFACE_HUB_TOKEN"
fi
echo ""

# ── Step 3: GPU venv ─────────────────────────────────────────────
echo "▸ Step 3: Creating .venv-gpu..."
if [ -d "$REPO_DIR/.venv-gpu" ]; then
    echo "  .venv-gpu already exists. Recreate? (y/N)"
    read -r REPLY
    if [[ "$REPLY" =~ ^[Yy]$ ]]; then
        rm -rf "$REPO_DIR/.venv-gpu"
    else
        echo "  ✓ Keeping existing .venv-gpu"
        SKIP_GPU=1
    fi
fi
if [ "${SKIP_GPU:-0}" != "1" ]; then
    python3.12 -m venv "$REPO_DIR/.venv-gpu"
    source "$REPO_DIR/.venv-gpu/bin/activate"
    pip install --upgrade pip
    pip install -r "$REPO_DIR/requirements-gpu.txt"
    deactivate
    echo "  ✓ .venv-gpu created and packages installed"
fi
echo ""

# ── Step 4: TTS venv ─────────────────────────────────────────────
echo "▸ Step 4: Creating .venv-tts..."
if [ -d "$REPO_DIR/.venv-tts" ]; then
    echo "  .venv-tts already exists. Recreate? (y/N)"
    read -r REPLY
    if [[ "$REPLY" =~ ^[Yy]$ ]]; then
        rm -rf "$REPO_DIR/.venv-tts"
    else
        echo "  ✓ Keeping existing .venv-tts"
        SKIP_TTS=1
    fi
fi
if [ "${SKIP_TTS:-0}" != "1" ]; then
    python3.12 -m venv "$REPO_DIR/.venv-tts"
    source "$REPO_DIR/.venv-tts/bin/activate"
    pip install --upgrade pip
    pip install -r "$REPO_DIR/requirements-tts.txt"
    deactivate
    echo "  ✓ .venv-tts created and packages installed"
fi
echo ""

# ── Step 5: Playwright ───────────────────────────────────────────
echo "▸ Step 5: Installing Playwright..."
pip install -r "$REPO_DIR/scripts/requirements.txt" --break-system-packages 2>/dev/null || \
    pip install -r "$REPO_DIR/scripts/requirements.txt"
python3 -m playwright install chromium
echo "  ✓ Playwright + Chromium installed"
echo ""

# ── Step 6: Unpack transfer bundle (DB + memory) ────────────────
TRANSFER_ZIP="$REPO_DIR/transfer/hornelore_data.zip"
echo "▸ Step 6: Checking for transfer bundle..."
if [ -f "$TRANSFER_ZIP" ]; then
    echo "  Found: $TRANSFER_ZIP"
    if [ -f "$DATA_DIR/db/hornelore.sqlite3" ]; then
        echo "  ⚠ Database already exists at $DATA_DIR/db/hornelore.sqlite3"
        echo "  Overwrite with transfer bundle? (y/N)"
        read -r REPLY
        if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
            echo "  ✓ Keeping existing data"
            SKIP_UNPACK=1
        fi
    fi
    if [ "${SKIP_UNPACK:-0}" != "1" ]; then
        unzip -o "$TRANSFER_ZIP" -d "$DATA_DIR"
        echo "  ✓ Unpacked to $DATA_DIR"
    fi
else
    echo "  No transfer bundle found at $TRANSFER_ZIP"
    echo "  The DB will be created fresh on first startup."
    echo "  To transfer from another machine, copy hornelore_data.zip"
    echo "  into the transfer/ folder and re-run this script."
fi
echo ""

# ── Step 7: Model check ─────────────────────────────────────────
MODEL_PATH="$MODEL_DIR/Meta-Llama-3.1-8B-Instruct"
echo "▸ Step 7: Checking for model..."
if [ -d "$MODEL_PATH" ] && [ "$(ls -A "$MODEL_PATH" 2>/dev/null)" ]; then
    echo "  ✓ Model found at $MODEL_PATH"
else
    echo "  ⚠ Model NOT found at $MODEL_PATH"
    echo ""
    echo "  Option A — Copy from source machine:"
    echo "    Copy the folder C:\\models\\hornelore\\Meta-Llama-3.1-8B-Instruct"
    echo "    to the same path on this machine."
    echo ""
    echo "  Option B — Download from HuggingFace (~16 GB):"
    echo "    huggingface-cli login"
    echo "    huggingface-cli download meta-llama/Meta-Llama-3.1-8B-Instruct \\"
    echo "      --local-dir $MODEL_PATH"
fi
echo ""

# ── Step 7: Database check ───────────────────────────────────────
DB_PATH="$DATA_DIR/hornelore.sqlite3"
echo "▸ Step 8: Checking for database..."
if [ -f "$DB_PATH" ]; then
    echo "  ✓ Database found at $DB_PATH"
else
    echo "  ⚠ Database NOT found at $DB_PATH"
    echo "  The DB will be created automatically on first API startup."
    echo "  To copy an existing DB, run:"
    echo "    cp /path/to/source/hornelore.sqlite3 $DB_PATH"
fi
echo ""

# ── Done ─────────────────────────────────────────────────────────
echo "═══════════════════════════════════════════════════"
echo "  Setup complete!"
echo ""
echo "  Remaining manual steps:"
echo "  1. Edit .env — set HUGGINGFACE_HUB_TOKEN"
echo "  2. Copy or download the model (if not present)"
echo "  3. Copy the database (if migrating from another machine)"
echo "  4. Start: bash start_hornelore.bat"
echo "  5. Load narrators: python3 scripts/import_kent_james_horne.py"
echo "═══════════════════════════════════════════════════"
