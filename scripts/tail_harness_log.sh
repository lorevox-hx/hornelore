#!/usr/bin/env bash
# tail_harness_log.sh — useful-events-only tail of api.log + tts.log.
#
# Strips dashboard heartbeat, test-lab polling, ui-heartbeat, ping,
# safety-event polling, TTS voice lookups, and UI bundle fetches — the
# stuff that drowns out actual harness signals. Surfaces facts/add,
# bio-builder, profiles, chronology, family-truth, transcript, chat,
# extract, interview, ERROR, Traceback, and any 4xx/5xx HTTP responses.
#
# Output is tee'd to docs/reports/harness_filtered_<timestamp>.log so
# you have a captured copy of the run for review. Press Ctrl+C to stop.
#
# Banked 2026-06-17 from Chris's pasted filter pattern after the John
# Baldy Life Map harness analysis surfaced 5 real bugs hiding behind
# dashboard polling noise.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p docs/reports
OUT="docs/reports/harness_filtered_$(date +%Y%m%d_%H%M%S).log"

echo "Filtered harness log → $OUT"
echo "Press Ctrl+C to stop."
echo ""

tail -F .runtime/logs/api.log .runtime/logs/tts.log \
  | grep --line-buffered -Ev 'test-lab|stack-dashboard/(ui-heartbeat|summary|history|system-status)|/api/ping|/api/operator/safety-events|/api/operator/eval-harness/summary|/ui/hornelore1.0.html|/api/tts/voices' \
  | grep --line-buffered -E 'facts/add|bio-builder/questionnaire|profiles/|chronology|family-truth|transcript|chat|extract|interview|ERROR|Traceback|HTTP/1.1" [45][0-9][0-9]' \
  | tee "$OUT"
