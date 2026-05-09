#!/usr/bin/env bash
# apply_kokoro_safety_env.sh — 2026-05-09
#
# One-shot, idempotent .env updater for today's two changes:
#   1. TTS engine swap to Kokoro (per LAPTOP_HANDOFF_KOKORO_INSTALL.md
#      Step 8b/8c). Coqui retired 2026-05-08; Kokoro is sole engine.
#      Sets: LORI_TTS_ENGINE, LORI_TTS_KOKORO_VOICE_EN/ES,
#            HF_HUB_CACHE, HUGGINGFACE_HUB_CACHE
#   2. Safety LLM tuning (per HANDOFF.md 2026-05-09 — Mary's-session
#      988 false-positive fix).
#      Sets: HORNELORE_SAFETY_LLM_LAYER=1
#            HORNELORE_SAFETY_LLM_CONFIDENCE_FLOOR=0.65
#
# Idempotent: each key is grep -q'd; existing line → sed-rewritten,
# missing line → appended. Run again later and nothing changes.
#
# Run from repo root in WSL:
#   bash scripts/setup/apply_kokoro_safety_env.sh
#
# Reads $USER (or `whoami`) to derive the HF cache path so this works
# on either MAG-Chris or the laptop without editing the script.

set -e

REPO_DIR="${REPO_DIR:-/mnt/c/Users/chris/hornelore}"
cd "$REPO_DIR"

if [ ! -f .env ]; then
    echo "FAIL: no .env at $REPO_DIR — copy from .env.example first" >&2
    exit 1
fi

USER_NAME="${USER:-$(whoami)}"
HF_CACHE_PATH="/home/${USER_NAME}/.cache/huggingface/hub"

# ── 0. Backup ────────────────────────────────────────────────────────────
TS="$(date +%Y%m%d_%H%M%S)"
BACKUP=".env.bak_${TS}_pre_kokoro_safety"
cp .env "$BACKUP"
echo "[0/3] Backup: $BACKUP"

# ── Helper: idempotent set-or-append (key=value) ─────────────────────────
# Usage: _setenv KEY VALUE
# Existing line → sed-rewrites in place. Missing → appends to end.
_setenv() {
    local key="$1"
    local val="$2"
    if grep -q "^${key}=" .env; then
        # Use | as sed delimiter so paths with / don't break it.
        sed -i "s|^${key}=.*|${key}=${val}|" .env
        echo "  rewrote: ${key}=${val}"
    else
        echo "${key}=${val}" >> .env
        echo "  appended: ${key}=${val}"
    fi
}

# ── 1. Kokoro TTS block ─────────────────────────────────────────────────
echo "[1/3] Kokoro TTS block (Coqui retired 2026-05-08)..."
_setenv LORI_TTS_ENGINE kokoro
_setenv LORI_TTS_KOKORO_VOICE_EN af_heart
_setenv LORI_TTS_KOKORO_VOICE_ES ef_dora
_setenv HF_HUB_CACHE "$HF_CACHE_PATH"
_setenv HUGGINGFACE_HUB_CACHE "$HF_CACHE_PATH"

# HF_HUB_OFFLINE should already be 1 from the existing Llama setup, but
# don't trust it — verify and pin.
_setenv HF_HUB_OFFLINE 1

# ── 2. Safety LLM flags (Mary's-session fix, 2026-05-09) ─────────────────
echo "[2/3] Safety LLM flags (BUG-LORI-SAFETY-FALSE-POSITIVE-EXTERNAL-FEAR-01)..."
_setenv HORNELORE_SAFETY_LLM_LAYER 1
_setenv HORNELORE_SAFETY_LLM_CONFIDENCE_FLOOR 0.65

# ── 3. Verify ────────────────────────────────────────────────────────────
echo "[3/3] Verify — final state of the 8 keys touched:"
grep -E "^(LORI_TTS|HF_HUB_CACHE|HUGGINGFACE_HUB_CACHE|HF_HUB_OFFLINE|HORNELORE_SAFETY_LLM)" .env

echo
echo "=== DONE ==="
echo "  Backup: $BACKUP"
echo "  Restore with:  cp $BACKUP .env"
echo
echo "Stack restart not triggered by this script — Chris owns lifecycle."
echo "Cycle the stack manually when ready."
