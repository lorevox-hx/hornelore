#!/usr/bin/env bash
# apply_june_env_parity.sh — 2026-06-21
#
# Sister script to apply_kokoro_safety_env.sh. Brings the laptop's .env
# to parity with .env.example for the 16 post-May flags landed during
# the desktop's June work (story-first phase 1, bio-fact routing,
# operator past-tense review, operator follow-up bank, etc.).
#
# All flags default to OFF (or to .env.example's default) so the gated
# routes return 404 until the operator explicitly turns them on — this
# script just brings the laptop's documentation/declaration of the flags
# into parity with what the codebase reads.
#
# Idempotent: each key is grep -q'd; existing line → sed-rewritten,
# missing line → appended.
#
# Run from repo root in WSL:
#   bash scripts/setup/apply_june_env_parity.sh

set -e

REPO_DIR="${REPO_DIR:-/mnt/c/Users/chris/hornelore}"
cd "$REPO_DIR"

if [ ! -f .env ]; then
    echo "FAIL: no .env at $REPO_DIR — copy from .env.example first" >&2
    exit 1
fi

# ── 0. Backup ────────────────────────────────────────────────────────────
TS="$(date +%Y%m%d_%H%M%S)"
BACKUP=".env.bak_${TS}_pre_june_parity"
cp .env "$BACKUP"
echo "[0/3] Backup: $BACKUP"

# ── Helper: idempotent set-or-append (key=value) ─────────────────────────
# Existing line → sed-rewrites in place. Missing → appends to end.
# Uses | as sed delimiter so paths/decimals don't break it.
_setenv() {
    local key="$1"
    local val="$2"
    if grep -q "^${key}=" .env; then
        sed -i "s|^${key}=.*|${key}=${val}|" .env
        echo "  rewrote: ${key}=${val}"
    else
        echo "${key}=${val}" >> .env
        echo "  appended: ${key}=${val}"
    fi
}

# ── 1. Operator review surfaces (post-May, all default-off gated routes) ─
echo "[1/3] Operator review surfaces..."
_setenv HORNELORE_OPERATOR_PAST_TENSE_REVIEW 0
_setenv HORNELORE_OPERATOR_FOLLOWUP_BANK 0
_setenv HORNELORE_OPERATOR_BIO_EDITOR 0
_setenv HORNELORE_OPERATOR_BIO_GAP_MAP 0

# ── 2. Questionnaire / Bio facts routing ────────────────────────────────
echo "[2/3] Questionnaire + Bio facts routing..."
_setenv HORNELORE_QUESTIONNAIRE_BIO_FACTS_READ 0
_setenv HORNELORE_QUESTIONNAIRE_BIO_FACTS_WRITE 0
# Legacy blob write default-ON per .env.example (legacy fallback)
_setenv HORNELORE_QUESTIONNAIRE_LEGACY_BLOB_WRITE 1
_setenv HORNELORE_BIO_FACT_ROUTING 0
_setenv HORNELORE_BIO_DOC_ROUTING 0
_setenv HORNELORE_BIO_ANCHORED_ASKER 0

# ── 3. Softened-mode + story-first + momentum tuning ────────────────────
echo "[3/3] Softened-mode + story-first + momentum..."
_setenv HORNELORE_SOFTENED_N_ACUTE 5
_setenv HORNELORE_SOFTENED_N_PAST_TENSE 2
_setenv HORNELORE_STORY_FIRST_PHASE_1 0
_setenv HORNELORE_STORY_FIRST_PHASE_1_LLM_CLASSIFY 0
_setenv HORNELORE_MOMENTUM_STORY 0.60
_setenv HORNELORE_MOMENTUM_EMERGING 0.40

# ── Verify ───────────────────────────────────────────────────────────────
echo
echo "=== Final state of the 16 keys touched ==="
grep -E "^(HORNELORE_OPERATOR_PAST_TENSE_REVIEW|HORNELORE_OPERATOR_FOLLOWUP_BANK|HORNELORE_OPERATOR_BIO_EDITOR|HORNELORE_OPERATOR_BIO_GAP_MAP|HORNELORE_QUESTIONNAIRE_BIO_FACTS_READ|HORNELORE_QUESTIONNAIRE_BIO_FACTS_WRITE|HORNELORE_QUESTIONNAIRE_LEGACY_BLOB_WRITE|HORNELORE_BIO_FACT_ROUTING|HORNELORE_BIO_DOC_ROUTING|HORNELORE_BIO_ANCHORED_ASKER|HORNELORE_SOFTENED_N_ACUTE|HORNELORE_SOFTENED_N_PAST_TENSE|HORNELORE_STORY_FIRST_PHASE_1|HORNELORE_STORY_FIRST_PHASE_1_LLM_CLASSIFY|HORNELORE_MOMENTUM_STORY|HORNELORE_MOMENTUM_EMERGING)=" .env

echo
echo "=== DONE ==="
echo "  Backup: $BACKUP"
echo "  Restore with:  cp $BACKUP .env"
echo
echo "All 16 flags are default-OFF (or .env.example's default). No"
echo "runtime behavior changes from this script. To enable a specific"
echo "operator surface or feature, edit .env and flip the relevant flag."
echo
echo "Stack restart not triggered by this script — Chris owns lifecycle."
