#!/usr/bin/env bash
# WO-ML-TTS-EN-ES-01 Phase 1 — Kokoro install helper.
#
# Run from /mnt/c/Users/chris/hornelore root:
#   bash scripts/setup/install_kokoro.sh
#
# Installs the pip packages + system espeak-ng (for non-English G2P).
# Does NOT flip LORI_TTS_ENGINE — that's a manual step after smoke-
# probing the install.
#
# Prerequisites:
#   - Python venv where Coqui TTS already runs (the same one that
#     uvicorn uses for the port-8001 TTS service)
#   - WSL Ubuntu OR macOS (Windows-native works too but espeak-ng
#     install differs — see Windows note below)
#
# Sequencing reminder per CLAUDE.md:
#   The locked WO posture is "live-verify the perspective + fragment
#   guards on a real Spanish session BEFORE flipping LORI_TTS_ENGINE
#   to kokoro". This script does the install only — it does NOT
#   activate Kokoro. See scripts/setup/smoke_kokoro.py for verification.

set -euo pipefail

echo "=== WO-ML-TTS-EN-ES-01 Phase 1: Kokoro install ==="
echo

# 1. System package: espeak-ng (used by phonemizer for non-EN G2P)
echo "[1/5] Installing espeak-ng (system package)..."
if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo apt-get install -y espeak-ng
elif command -v brew >/dev/null 2>&1; then
    brew install espeak-ng
else
    echo "  WARNING: Couldn't auto-detect package manager."
    echo "  Install espeak-ng manually:"
    echo "    Ubuntu/Debian/WSL : sudo apt-get install espeak-ng"
    echo "    macOS             : brew install espeak-ng"
    echo "    Windows native    : https://github.com/espeak-ng/espeak-ng/releases"
    echo "  Then re-run this script."
    exit 1
fi
echo "  espeak-ng: $(espeak-ng --version 2>&1 | head -1)"

# 2. Find or create repo venv
#    Ubuntu 23.04+ ships PEP 668 protection on system Python (rightly so).
#    Hornelore's TTS service should use a project-scoped venv to keep
#    Kokoro/phonemizer/soundfile separated from the system Python. If a
#    .venv or venv already exists, reuse it; otherwise create .venv.
echo
echo "[2/5] Locating / creating repo venv..."
if [ -x ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
    echo "  Reusing existing .venv"
elif [ -x "venv/bin/python" ]; then
    PYTHON="venv/bin/python"
    echo "  Reusing existing venv"
else
    echo "  No venv found — creating .venv ..."
    if ! python3 -m venv .venv; then
        echo "  FAIL: python3 -m venv failed."
        echo "  On Ubuntu/WSL you may need: sudo apt install python3-venv python3-full"
        exit 2
    fi
    PYTHON=".venv/bin/python"
fi
$PYTHON --version
$PYTHON -c "import sys; print(f'  venv python: {sys.executable}')"

# 3. Verify the venv pip works (PEP 668 only blocks the SYSTEM python;
#    a venv is exempt, so no --break-system-packages needed).
echo
echo "[3/5] Upgrading pip / setuptools / wheel inside venv..."
$PYTHON -m pip install --upgrade pip setuptools wheel

# 4. pip install kokoro + soundfile + numpy + web-server deps
#    NOTE: Do NOT install standalone `phonemizer` here. Kokoro's misaki
#    dependency requires `phonemizer-fork` which provides
#    EspeakWrapper.set_data_path(). The PyPI `phonemizer` (no -fork) is
#    older and lacks that method. Both register the same `phonemizer`
#    namespace, so installing both produces a conflict where the older
#    package can win the import resolution and Kokoro crashes with:
#      AttributeError: type object 'EspeakWrapper' has no attribute 'set_data_path'
#    Kokoro pulls in `phonemizer-fork` transitively via misaki — let pip
#    resolve it from the kokoro install line alone.
#
#    fastapi + uvicorn + python-multipart are required because the
#    Hornelore TTS service (server/code/api/tts_service.py) is a FastAPI
#    app served via uvicorn. The launcher activates this venv and runs
#    `python -m uvicorn code.api.tts_service:app --port 8001`, so without
#    these the service can't even start. .venv-tts (the legacy Coqui venv)
#    had them via Coqui's transitive deps; the fresh .venv doesn't.
echo
echo "[4/5] Installing kokoro + soundfile + numpy + fastapi + uvicorn..."
$PYTHON -m pip install kokoro soundfile numpy fastapi 'uvicorn[standard]' python-multipart

# Defensive repair: if a previous (buggy) run installed standalone
# `phonemizer`, remove it AND force-reinstall phonemizer-fork +
# espeakng-loader. Reason: phonemizer 3.3.0 and phonemizer-fork 3.3.2
# both write into the same `phonemizer/` namespace dir; whichever
# wrote LAST wins on file content but pip metadata tracks both.
# A bare `pip uninstall phonemizer` removes files listed in
# phonemizer-3.3.0/RECORD — some of which were overwritten by the
# fork — leaving phonemizer-fork's RECORD pointing at missing files.
# Force-reinstall restores the correct fork files. Idempotent: if no
# phonemizer is present, uninstall is a no-op and the reinstall
# upgrades fork + loader to their latest compatible versions.
echo
echo "[4a/5] Defensive repair: drop standalone phonemizer; force-reinstall fork + loader..."
$PYTHON -m pip uninstall -y phonemizer 2>/dev/null || echo "  phonemizer not installed (OK)"
$PYTHON -m pip install --upgrade --force-reinstall phonemizer-fork espeakng-loader

# 5. Verify imports + that the fork's API surface is actually present
echo
echo "[5/5] Verifying imports..."
$PYTHON -c "
from kokoro import KPipeline
import phonemizer
import soundfile
import numpy as np
# Confirm we got phonemizer-fork (has set_data_path), not the old one.
from phonemizer.backend.espeak.wrapper import EspeakWrapper
assert hasattr(EspeakWrapper, 'set_data_path'), \\
    'phonemizer is missing set_data_path() — phonemizer-fork is required'
assert hasattr(EspeakWrapper, 'set_library'), \\
    'phonemizer is missing set_library() — phonemizer-fork is required'
print('  kokoro:          ' + str(KPipeline.__module__))
print('  phonemizer:      ' + phonemizer.__version__ + '  (fork verified)')
print('  soundfile:       ' + soundfile.__version__)
print('  numpy:           ' + np.__version__)
print()
print('  All imports OK.')
"

echo
echo "=== Install complete ==="
echo
echo "venv python: $PYTHON"
echo
echo "Next steps:"
echo "  1. Run the smoke probe USING THE SAME VENV PYTHON:"
echo "       $PYTHON scripts/setup/smoke_kokoro.py"
echo
echo "  2. Listen to the WAVs:"
echo "       Linux/WSL with alsa: aplay /tmp/kokoro_smoke_en.wav"
echo "       Windows (from WSL):  explorer.exe \"\$(wslpath -w /tmp/kokoro_smoke_en.wav)\""
echo
echo "  3. After Melanie's next Spanish session live-verifies the"
echo "     guards landed today, flip LORI_TTS_ENGINE in .env:"
echo "       LORI_TTS_ENGINE=kokoro"
echo
echo "  4. Restart the TTS service (port 8001) — make sure start_all.sh"
echo "     uses $PYTHON, NOT /usr/bin/python, so the service has the"
echo "     kokoro package available."
echo
echo "  5. Tail the log to confirm Kokoro warmed:"
echo "       grep -E '\\[tts\\](.*kokoro|.*warmed)' .runtime/logs/api.log"
