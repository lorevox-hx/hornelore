#!/usr/bin/env python3
"""WO-TIMELINE-CONTEXT-EVENTS-01 Phase B — seed loader.

Reads JSON pack files in `data/timeline_context_events/`, validates each
entry via the same discipline rules as `validate_timeline_context_events.py`,
and inserts/updates rows in the live `timeline_context_events` table via
the repository module.

Idempotent: re-running is a no-op for already-loaded entries (matched by
`id`). Existing entries are LEFT ALONE unless `--update-existing` is set
— in which case the row is patched with the JSON values.

USAGE:
  # Validate-only, no DB writes
  python scripts/seed_timeline_context_events.py --dry-run

  # Load all packs in data/timeline_context_events/
  python scripts/seed_timeline_context_events.py

  # Load one pack
  python scripts/seed_timeline_context_events.py --pack data/timeline_context_events/janice_germans_from_russia_nd_prairie.json

  # Update existing rows in addition to inserting new ones
  python scripts/seed_timeline_context_events.py --update-existing

  # Specify operator user_id for created_by/updated_by audit columns
  python scripts/seed_timeline_context_events.py --operator chris@lorevox

EXIT CODES:
  0 = all rows loaded (or --dry-run validation passed)
  1 = validation failure (no DB writes performed)
  2 = config error (missing tag vocabulary, etc.)
  3 = DB write error (some rows landed; some failed — check log)

STATUS (2026-05-05 night-shift):
  Skeleton banked. NOT yet wired into any startup hook. Operator runs
  manually after the migration applies. Idempotent so a second run is
  safe.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("seed_timeline_context_events")


_REPO_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _REPO_ROOT / "data" / "timeline_context_events"


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Seed the timeline_context_events table from JSON packs."
    )
    p.add_argument("--pack", type=Path, default=None,
                   help="Single pack to load. Defaults to every *.json in data/timeline_context_events/ except tag_vocabulary.json.")
    p.add_argument("--dry-run", action="store_true",
                   help="Validate only — no DB writes.")
    p.add_argument("--update-existing", action="store_true",
                   help="Patch existing rows instead of skipping them.")
    p.add_argument("--operator", default="seed_loader",
                   help="Operator user_id for created_by/edited_by audit "
                   "columns when entries don't carry one. Default: seed_loader.")
    return p


def _load_pack(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[seed] {path.name}: malformed JSON — {exc}")


def _validate_or_die(pack_paths: List[Path]) -> None:
    """Run the validator script's main() over the given packs; exit
    non-zero if any error surfaces.
    """
    # Lazy import to keep the seed loader's sys.path setup local to this
    # module — allows running standalone without installing the package.
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    try:
        import validate_timeline_context_events as _val  # noqa: I001
    except ImportError as exc:
        raise SystemExit(f"[seed] validator import failed: {exc}")

    region_vocab, heritage_vocab = _val._load_vocabulary()
    total_errors = 0
    for path in pack_paths:
        errors = _val._validate_pack(path, region_vocab, heritage_vocab)
        if errors:
            logger.error("[seed] %s — %d validation error(s):", path.name, len(errors))
            for err in errors:
                logger.error("  %s", err)
            total_errors += len(errors)

    if total_errors:
        raise SystemExit(1)


def _load_one_pack(
    path: Path,
    *,
    update_existing: bool,
    default_operator: str,
    dry_run: bool,
) -> Dict[str, int]:
    """Returns counts dict: {inserted, updated, skipped, failed}."""
    data = _load_pack(path)
    entries = data.get("events") or data.get("entries") or []
    counts = {"inserted": 0, "updated": 0, "skipped": 0, "failed": 0}

    if dry_run:
        logger.info("[seed] DRY-RUN — %s: %d entries (validated)", path.name, len(entries))
        return counts

    # Lazy import the repository — keeps the script's import surface tiny
    # so it works as both a standalone CLI and as a module.
    sys.path.insert(0, str(_REPO_ROOT / "server" / "code"))
    try:
        from api.services.timeline_context_events_repository import (
            add_event, update_event, get_event,
        )
    except ImportError as exc:
        raise SystemExit(f"[seed] repository import failed: {exc}")

    for i, entry in enumerate(entries):
        event_id = entry.get("id")
        if not event_id:
            counts["failed"] += 1
            logger.error("[seed] %s entry[%d]: missing id — skip", path.name, i)
            continue

        created_by = entry.get("created_by") or default_operator
        # Strip the "created_by" key out before passing patches/inserts —
        # add_event takes it as a kwarg, update_event doesn't accept it.
        payload = {k: v for k, v in entry.items() if k != "created_by"}

        try:
            existing = get_event(event_id)
            if existing is None:
                add_event({"created_by": created_by, **payload}, created_by_user_id=created_by)
                counts["inserted"] += 1
            elif update_existing:
                update_event(event_id, payload, edited_by_user_id=default_operator)
                counts["updated"] += 1
            else:
                counts["skipped"] += 1
        except (ValueError, RuntimeError) as exc:
            counts["failed"] += 1
            logger.error("[seed] %s entry[%d] (id=%s): %s",
                         path.name, i, event_id, exc)

    return counts


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _build_arg_parser().parse_args(argv)

    if args.pack:
        targets = [args.pack]
    else:
        if not _DATA_DIR.is_dir():
            logger.info("[seed] %s does not exist; nothing to seed", _DATA_DIR)
            return 0
        targets = sorted(
            p for p in _DATA_DIR.glob("*.json")
            if p.name != "tag_vocabulary.json"
        )

    if not targets:
        logger.info("[seed] no pack files found in %s", _DATA_DIR)
        return 0

    # Validate every pack before writing anything. Validation failure is
    # a hard stop — no DB writes happen.
    _validate_or_die(targets)

    total = {"inserted": 0, "updated": 0, "skipped": 0, "failed": 0}
    for path in targets:
        counts = _load_one_pack(
            path,
            update_existing=args.update_existing,
            default_operator=args.operator,
            dry_run=args.dry_run,
        )
        for k in total:
            total[k] += counts.get(k, 0)
        logger.info(
            "[seed] %s: inserted=%d updated=%d skipped=%d failed=%d",
            path.name,
            counts["inserted"],
            counts["updated"],
            counts["skipped"],
            counts["failed"],
        )

    logger.info(
        "[seed] TOTAL: inserted=%d updated=%d skipped=%d failed=%d",
        total["inserted"], total["updated"], total["skipped"], total["failed"],
    )
    return 3 if total["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
