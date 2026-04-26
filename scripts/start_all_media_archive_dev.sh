#!/usr/bin/env bash
# scripts/start_all_media_archive_dev.sh — Hornelore 1.0
#
# Wrapper around scripts/start_all.sh that enables the Document Archive
# backend (WO-MEDIA-ARCHIVE-01) by exporting HORNELORE_MEDIA_ARCHIVE_ENABLED=1
# in the env inherited by uvicorn.
#
# WHY THIS IS A SEPARATE SCRIPT:
#   The default parent stack should NOT auto-enable the media-archive
#   surface until the curator UI + operator workflow are stable. This
#   wrapper is the explicit opt-in for archive testing.
#
# USAGE:
#   bash scripts/start_all_media_archive_dev.sh
#
# Combined with photos (recommended for full curator-side testing):
#   HORNELORE_PHOTO_ENABLED=1 bash scripts/start_all_media_archive_dev.sh
# OR run the photos wrapper with the archive flag exported:
#   HORNELORE_MEDIA_ARCHIVE_ENABLED=1 bash scripts/start_all_photos_dev.sh
#
# Default stack (no flags) keeps both archives off — start_all.sh stays
# clean so production-shape probes don't hit the dev surfaces.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Force-enable the Document Archive router. Backend reads this from
# os.environ via flags.media_archive_enabled(), so it must be exported
# BEFORE the uvicorn child process is spawned.
export HORNELORE_MEDIA_ARCHIVE_ENABLED=1

printf '[archive-dev] HORNELORE_MEDIA_ARCHIVE_ENABLED=1 set.\n'
printf '[archive-dev] Document Archive routes /api/media-archive/* will respond instead of 404.\n'
printf '[archive-dev] Operator launcher: 📄 Document Archive (Media tab)\n'
printf '[archive-dev] Curator page:      /ui/media-archive.html\n'
printf '[archive-dev] Delegating to scripts/start_all.sh...\n\n'

exec bash "$ROOT_DIR/scripts/start_all.sh" "$@"
