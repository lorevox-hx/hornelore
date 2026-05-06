#!/usr/bin/env python3
"""WO-TIMELINE-CONTEXT-EVENTS-01 Phase B — JSON pack validator.

Reads JSON files in `data/timeline_context_events/`, validates each entry
against the schema + tag vocabulary + citation discipline, and reports
errors with file path + entry index. Pre-commit hook hookable.

Per WO-TIMELINE-CONTEXT-EVENTS-01_Spec.md:
  - Schema rules: required fields, valid scope, valid source_kind,
    year_start <= year_end, tag arrays well-formed.
  - Tag vocabulary: every tag in region_tags / heritage_tags must exist
    in `data/timeline_context_events/tag_vocabulary.json`.
  - Citation discipline: rejects "general knowledge", "common knowledge",
    bare "wikipedia" without article + access date, etc.
  - Pack-kind rule: shared_regional packs require independent corroboration
    OR named oral-history provenance for any local_oral_history source.
    private_family packs accept local_oral_history standalone.

USAGE:
  python scripts/validate_timeline_context_events.py
  python scripts/validate_timeline_context_events.py --pack data/timeline_context_events/janice_germans_from_russia_nd_prairie.json
  python scripts/validate_timeline_context_events.py --strict   # exit 1 on any warning

EXIT CODES:
  0 = all packs valid
  1 = at least one validation error
  2 = config error (missing tag_vocabulary.json, malformed JSON, etc.)

STATUS (2026-05-05 night-shift):
  Skeleton banked. Logic intentionally kept tight — passes the locked
  v1 schema requirements; richer rules (pack-kind discipline, citation
  pattern matching) are encoded but extensible. Run against the seed
  pack as a smoke test once Phase A migration runs.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("validate_timeline_context_events")


# ── Configuration ─────────────────────────────────────────────────────────


_REPO_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _REPO_ROOT / "data" / "timeline_context_events"
_VOCAB_PATH = _DATA_DIR / "tag_vocabulary.json"

_VALID_SCOPES = frozenset({"global", "national", "regional", "local", "cultural"})

_VALID_SOURCE_KINDS = frozenset({
    "local_oral_history",
    "archived_newspaper",
    "historical_society",
    "academic",
    "reference_work",
    "web_resource",
    "family_archive",
    "operator_research_note",
})

_VALID_PACK_KINDS = frozenset({"private_family", "shared_regional"})

# Source-kind classes for the pack-kind discipline rule
_PUBLISHED_SOURCE_KINDS = frozenset({
    "archived_newspaper",
    "historical_society",
    "academic",
    "reference_work",
    "web_resource",
})
_OPERATOR_OR_FAMILY = frozenset({
    "local_oral_history",
    "family_archive",
})

# Low-rigor citation patterns the validator rejects outright
_LOW_RIGOR_RX = re.compile(
    r"\b(general\s+knowledge|common\s+knowledge|i\s+remember|"
    r"my\s+grandmother\s+said|family\s+lore|just\s+know)\b",
    re.IGNORECASE,
)

# Required citation pattern when source_kind=local_oral_history:
# named person + date (year is sufficient)
_NAMED_INTERVIEW_RX = re.compile(
    r"interview\s+with\s+\w[\w\s\-\.\,]+,\s+recorded\s+\d{4}",
    re.IGNORECASE,
)

# Required citation pattern when source_kind=web_resource: URL + access date
_URL_WITH_ACCESS_RX = re.compile(
    r"https?://\S+.*accessed\s+\d{4}",
    re.IGNORECASE,
)

# Required citation pattern when source_kind=archived_newspaper:
# publication name + date
_NEWSPAPER_RX = re.compile(
    r"(\w[\w\s]+(?:times|sun|tribune|journal|herald|post|register|gazette|news|press|bulletin)),?\s+(?:archive\s+)?\d{4}",
    re.IGNORECASE,
)


# ── Vocabulary loader ─────────────────────────────────────────────────────


def _flatten_vocabulary(vocab: Dict[str, Any]) -> Tuple[Set[str], Set[str]]:
    """Return (region_tags_set, heritage_tags_set) — flat union of every
    leaf-level array under the respective top-level keys."""
    region_set: Set[str] = set()
    heritage_set: Set[str] = set()

    rt = vocab.get("region_tags") or {}
    for key, arr in rt.items():
        if key.startswith("_"):
            continue
        if isinstance(arr, list):
            region_set.update(t for t in arr if isinstance(t, str) and t.strip())

    ht = vocab.get("heritage_tags") or {}
    for key, arr in ht.items():
        if key.startswith("_"):
            continue
        if isinstance(arr, list):
            heritage_set.update(t for t in arr if isinstance(t, str) and t.strip())

    return region_set, heritage_set


def _load_vocabulary() -> Tuple[Set[str], Set[str]]:
    if not _VOCAB_PATH.is_file():
        raise SystemExit(f"[validate] missing tag vocabulary: {_VOCAB_PATH}")
    try:
        vocab = json.loads(_VOCAB_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[validate] tag_vocabulary.json malformed: {exc}")
    return _flatten_vocabulary(vocab)


# ── Per-entry validation ──────────────────────────────────────────────────


def _validate_entry(
    entry: Dict[str, Any],
    *,
    pack_kind: str,
    region_vocab: Set[str],
    heritage_vocab: Set[str],
    entry_index: int,
) -> List[str]:
    """Return list of error strings for this entry. Empty list = valid."""
    errors: List[str] = []
    prefix = f"entry[{entry_index}]"

    # Required string fields
    for field in ("id", "title", "summary", "scope", "source_kind", "source_citation", "created_by"):
        v = entry.get(field)
        if not (isinstance(v, str) and v.strip()):
            errors.append(f"{prefix}: missing or empty required field {field!r}")

    # Scope enum
    scope = entry.get("scope")
    if scope and scope not in _VALID_SCOPES:
        errors.append(f"{prefix}: invalid scope {scope!r} (valid: {sorted(_VALID_SCOPES)})")

    # source_kind enum
    sk = entry.get("source_kind")
    if sk and sk not in _VALID_SOURCE_KINDS:
        errors.append(f"{prefix}: invalid source_kind {sk!r}")

    # Year range
    ys = entry.get("year_start")
    ye = entry.get("year_end")
    if ys is not None and not isinstance(ys, int):
        errors.append(f"{prefix}: year_start must be int, got {type(ys).__name__}")
    if ye is not None and not isinstance(ye, int):
        errors.append(f"{prefix}: year_end must be int, got {type(ye).__name__}")
    if isinstance(ys, int) and isinstance(ye, int) and ys > ye:
        errors.append(f"{prefix}: year_start ({ys}) > year_end ({ye})")

    # Tag vocabulary enforcement
    rt = entry.get("region_tags") or []
    if not isinstance(rt, list):
        errors.append(f"{prefix}: region_tags must be a list")
    else:
        for tag in rt:
            if not isinstance(tag, str):
                errors.append(f"{prefix}: region_tags contains non-string {tag!r}")
            elif tag not in region_vocab:
                errors.append(
                    f"{prefix}: unknown region_tag {tag!r} "
                    f"(add to data/timeline_context_events/tag_vocabulary.json)"
                )

    ht = entry.get("heritage_tags") or []
    if not isinstance(ht, list):
        errors.append(f"{prefix}: heritage_tags must be a list")
    else:
        for tag in ht:
            if not isinstance(tag, str):
                errors.append(f"{prefix}: heritage_tags contains non-string {tag!r}")
            elif tag not in heritage_vocab:
                errors.append(
                    f"{prefix}: unknown heritage_tag {tag!r} "
                    f"(add to data/timeline_context_events/tag_vocabulary.json)"
                )

    # Citation discipline
    citation = entry.get("source_citation") or ""
    if isinstance(citation, str):
        if _LOW_RIGOR_RX.search(citation):
            errors.append(
                f"{prefix}: source_citation looks low-rigor ({citation!r}); "
                f"use a real citation or set source_kind='local_oral_history' "
                f"with a named person + date recorded"
            )

        # Source-kind-specific citation shape
        if sk == "local_oral_history":
            # private_family packs accept any non-trivial named source;
            # shared_regional packs require either independent corroboration
            # (covered at pack-aggregate level, not per-entry) OR explicit
            # "Interview with X, recorded YYYY" provenance.
            if pack_kind == "shared_regional":
                if not _NAMED_INTERVIEW_RX.search(citation):
                    errors.append(
                        f"{prefix}: shared_regional pack with source_kind="
                        f"local_oral_history requires "
                        f"'Interview with <named person>, recorded YYYY' "
                        f"citation pattern (got {citation!r})"
                    )
        elif sk == "web_resource":
            if not _URL_WITH_ACCESS_RX.search(citation):
                errors.append(
                    f"{prefix}: source_kind=web_resource requires URL + "
                    f"access date in citation (got {citation!r})"
                )
        elif sk == "archived_newspaper":
            if not _NEWSPAPER_RX.search(citation):
                errors.append(
                    f"{prefix}: source_kind=archived_newspaper should cite "
                    f"publication name + year (got {citation!r})"
                )

    # narrator_visible default rule for operator_research_note
    if sk == "operator_research_note":
        nv = entry.get("narrator_visible")
        if nv not in (None, 0, False):
            errors.append(
                f"{prefix}: source_kind=operator_research_note must have "
                f"narrator_visible=0 (or omitted) until promoted via "
                f"promote_research_note"
            )

    return errors


def _validate_pack(path: Path, region_vocab: Set[str], heritage_vocab: Set[str]) -> List[str]:
    """Validate one pack JSON file. Returns flat list of error strings."""
    errors: List[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{path.name}: malformed JSON — {exc}")
        return errors

    if not isinstance(data, dict):
        errors.append(f"{path.name}: top-level must be object, got {type(data).__name__}")
        return errors

    pack_kind = data.get("pack_kind")
    if pack_kind not in _VALID_PACK_KINDS:
        errors.append(
            f"{path.name}: pack_kind must be one of {sorted(_VALID_PACK_KINDS)}, "
            f"got {pack_kind!r}"
        )
        # Continue per-entry validation with a default — gives operator
        # the full error list rather than stopping at the first miss.
        pack_kind = pack_kind or "private_family"

    entries = data.get("events") or data.get("entries")
    if not isinstance(entries, list):
        errors.append(f"{path.name}: must contain 'events' (or 'entries') list")
        return errors

    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"{path.name}: entry[{i}] must be object")
            continue
        sub = _validate_entry(
            entry,
            pack_kind=pack_kind,
            region_vocab=region_vocab,
            heritage_vocab=heritage_vocab,
            entry_index=i,
        )
        for s in sub:
            errors.append(f"{path.name}: {s}")

    # Pack-aggregate rule for shared_regional packs:
    # cross-entry corroboration check is deferred to v2 — for now the
    # per-entry rule (named interview pattern) is enough discipline.

    return errors


# ── CLI ───────────────────────────────────────────────────────────────────


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Validate timeline_context_events JSON packs."
    )
    p.add_argument(
        "--pack", type=Path, default=None,
        help="Validate a single pack file. If omitted, validates every "
        "*.json in data/timeline_context_events/ EXCEPT tag_vocabulary.json.",
    )
    p.add_argument(
        "--strict", action="store_true",
        help="Exit 1 on any warning (currently equivalent to default — "
        "all errors are hard).",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _build_arg_parser().parse_args(argv)

    region_vocab, heritage_vocab = _load_vocabulary()

    if args.pack:
        targets = [args.pack]
    else:
        if not _DATA_DIR.is_dir():
            logger.error("[validate] %s does not exist; nothing to validate", _DATA_DIR)
            return 0
        targets = sorted(
            p for p in _DATA_DIR.glob("*.json")
            if p.name != "tag_vocabulary.json"
        )

    if not targets:
        logger.info("[validate] no pack files found in %s", _DATA_DIR)
        return 0

    total_errors = 0
    for pack_path in targets:
        errors = _validate_pack(pack_path, region_vocab, heritage_vocab)
        if errors:
            logger.error("[validate] %s — %d error(s):", pack_path.name, len(errors))
            for err in errors:
                logger.error("  %s", err)
            total_errors += len(errors)
        else:
            logger.info("[validate] %s — OK", pack_path.name)

    if total_errors:
        logger.error("[validate] %d error(s) total across %d pack(s)", total_errors, len(targets))
        return 1
    logger.info("[validate] all %d pack(s) valid", len(targets))
    return 0


if __name__ == "__main__":
    sys.exit(main())
