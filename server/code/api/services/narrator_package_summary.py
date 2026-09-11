"""Plain-language summary of a narrator package — WO-LOREVOX-PORTABLE-NARRATOR-01 §16.1.

PRESENTATION, NOT OWNERSHIP. `narrator_package.py` is pinned by test to name no
narrator-owned table: it consumes the declaration and nothing else. The operator
card, though, has to say "27 photos · 2 trips · 3 documents", and that sentence
has to name lanes. This module is where that mapping lives, so the exporter's
pin keeps meaning what it says. Every number here is a SUM over counts the
exporter or preflight already measured; nothing is re-derived from data.

Two front ends (§28.5) consume these: the router (for `summary`) and, through
it, the card — which computes nothing of its own.
"""
from __future__ import annotations

from typing import Any, Dict


def summarize_counts(records: Dict[str, int], files: Dict[str, Dict[str, int]]) -> Dict[str, Any]:
    """`records`: table -> row count (this narrator). `files`: lane -> {files, bytes}."""
    r = {k: v for k, v in records.items() if isinstance(v, int) and v > 0}
    return {
        "records": sum(r.values()),
        "conversations": r.get("sessions", 0),
        "turns": r.get("turns", 0),
        "photos": r.get("photos", 0),
        "documents": r.get("media_archive_items", 0) + r.get("trip_sources", 0),
        "trips": r.get("trips", 0),
        "stories": r.get("story_candidates", 0),
        "files": sum(v.get("files", 0) for v in files.values()),
        "bytes": sum(v.get("bytes", 0) for v in files.values()),
        "lanes_with_records": len(r),
    }


def summarize_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """The same shape, from a finished package's `lorevox-manifest.json`."""
    fc = manifest.get("file_counts_by_lane") or {}
    bb = manifest.get("bytes_by_lane") or {}
    files = {lane: {"files": fc.get(lane, 0), "bytes": bb.get(lane, 0)} for lane in set(fc) | set(bb)}
    s = summarize_counts(manifest.get("record_counts_by_lane") or {}, files)
    s["warnings"] = len(manifest.get("warnings") or [])
    s["residue_not_packaged"] = len(manifest.get("residue_not_packaged") or [])
    s["external_person_dependencies"] = sum(
        len(v) for v in (manifest.get("external_person_dependencies") or {}).values())
    return s


def human_bytes(n: int) -> str:
    n = int(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TB"


__all__ = ["summarize_counts", "summarize_manifest", "human_bytes"]
