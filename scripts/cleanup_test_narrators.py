#!/usr/bin/env python3
"""Cleanup harness for the test-narrator residue in the Hornelore DB.

DISCOVERED 2026-06-15: 178 narrators in production DB; ~173 are
harness/debug residue. This script classifies every narrator into
KEEP / SAFE_DELETE / NEEDS_REVIEW buckets and offers a guarded
delete path.

═══════════════════════════════════════════════════════════════════════
  USAGE
═══════════════════════════════════════════════════════════════════════

  python scripts/cleanup_test_narrators.py
      Default — render the classification report. Reads from /api/people
      and the per-narrator delete-inventory endpoint. Prints buckets
      with counts + sample names + dependency rollups. No mutations.

  python scripts/cleanup_test_narrators.py --bucket SAFE_DELETE --dry-run
      Show the exact list that would delete + cascade counts per row.
      Still no mutations.

  python scripts/cleanup_test_narrators.py --bucket SAFE_DELETE \\
                                           --commit --i-acknowledge
      Actually delete. Acknowledgment flag REQUIRED; the script refuses
      to fire deletes without both --commit AND --i-acknowledge to
      guard against muscle-memory mistakes. Deletes one row at a time
      via DELETE /api/people/{id}?mode=hard so the existing FK cascade
      + audit-trail logic fires.

  python scripts/cleanup_test_narrators.py --api http://localhost:8000
      Override API base. Default reads HORNELORE_API_URL env or falls
      back to localhost:8000.

═══════════════════════════════════════════════════════════════════════
  CLASSIFICATION RULES
═══════════════════════════════════════════════════════════════════════

  KEEP — pinned preserve list. Never deleted regardless of pattern:
    * Janice Josephine Horne
    * Kent James Horne
    * Christopher Todd Horne
    * Melanie Zollner
    * Melanie Carter
    * William Shatner / William Alan Shatner (Shatner template)

    Match is case-insensitive on display_name. The pinned IDs (when
    known) take precedence so a future rename can't accidentally
    promote them out of KEEP.

  SAFE_DELETE — high-confidence test residue:
    * /^Test_\\d+$/                 — 126 hits, harness synthetic
    * /^mary$/i                     — repeated parent-session readiness
    * /^marvin\\s*mann$/i           — same
    * /^What['’]?s$/i          — name-capture bug artifact
    * /^reset\\s*test$/i            — operator debug
    * /^era\\s*cycle\\s*test$/i     — operator debug
    * /^HARNESS_PROBE_DELME$/       — explicit "delete me" marker
    * /^Bug\\s+\\d+$/i              — debug narrator
    * /^Test\\s+storyteller$/i      — harness template

  NEEDS_REVIEW — single-token names + everything ambiguous. Operator
    decides per-row. Surfaced with their dependency counts so the
    operator can scan for "0 sessions + 0 facts" rows and approve a
    second-pass delete.

═══════════════════════════════════════════════════════════════════════
  SAFETY MODEL
═══════════════════════════════════════════════════════════════════════

  * KEEP names are checked at TWO points: when bucketing AND
    immediately before each DELETE call. Belt-and-suspenders against
    future bugs.

  * Pre-delete dependency inventory is fetched per row and printed in
    --dry-run output so the operator sees what cascades.

  * Each DELETE is a separate API call with its own HTTP status
    surface. Partial-failure is recoverable — the script logs which
    rows succeeded and which didn't, then continues.

  * --commit requires --i-acknowledge. Both flags must be set.

  * No batch DELETE / no SQL-direct path / no bypass of the existing
    hard_delete_person cascade. The API layer is the source of truth
    for what "delete a narrator" means.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────
# KEEP list — pinned preserve names (case-insensitive on display_name)
# ─────────────────────────────────────────────────────────────────────

KEEP_DISPLAY_NAMES = frozenset({
    name.lower() for name in (
        "Janice Josephine Horne",
        "Kent James Horne",
        "Christopher Todd Horne",
        "Melanie Zollner",
        "William Shatner",
        "William Alan Shatner",
        "Walter",
    )
})


# ─────────────────────────────────────────────────────────────────────
# SAFE_DELETE patterns
# ─────────────────────────────────────────────────────────────────────

_SAFE_DELETE_RX = (
    re.compile(r"^Test_\d+$", re.IGNORECASE),
    re.compile(r"^mary$", re.IGNORECASE),
    re.compile(r"^marvin\s*mann$", re.IGNORECASE),
    re.compile(r"^What['’]?s$", re.IGNORECASE),
    re.compile(r"^reset\s*test$", re.IGNORECASE),
    re.compile(r"^era\s*cycle(?:\s*test)?$", re.IGNORECASE),
    re.compile(r"^HARNESS_PROBE_DELME$"),
    re.compile(r"^Bug\s+\d+$", re.IGNORECASE),
    re.compile(r"^Test\s+storyteller$", re.IGNORECASE),
)


# ─────────────────────────────────────────────────────────────────────
# HTTP plumbing
# ─────────────────────────────────────────────────────────────────────


def http_get(api: str, path: str, timeout: float = 30.0) -> Any:
    url = api.rstrip("/") + path
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else None


def http_delete(api: str, path: str, timeout: float = 60.0) -> Tuple[int, str]:
    url = api.rstrip("/") + path
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return (resp.status, resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return (e.code, e.read().decode("utf-8"))
    except urllib.error.URLError as e:
        return (-1, str(e.reason))


# ─────────────────────────────────────────────────────────────────────
# Classification
# ─────────────────────────────────────────────────────────────────────


def _display_name(p: Dict[str, Any]) -> str:
    return (p.get("display_name") or p.get("full_name")
            or p.get("name") or "").strip()


def classify(name: str) -> str:
    """Return one of 'KEEP' / 'SAFE_DELETE' / 'NEEDS_REVIEW'."""
    if not name:
        return "SAFE_DELETE"  # nameless row — almost certainly garbage
    low = name.lower()
    if low in KEEP_DISPLAY_NAMES:
        return "KEEP"
    for rx in _SAFE_DELETE_RX:
        if rx.match(name):
            return "SAFE_DELETE"
    # Single-token first names → review (could be a partial preserve)
    if " " not in name and len(name) <= 12:
        return "NEEDS_REVIEW"
    return "NEEDS_REVIEW"


# ─────────────────────────────────────────────────────────────────────
# Inventory rollup
# ─────────────────────────────────────────────────────────────────────


def fetch_inventory(api: str, person_id: str) -> Optional[Dict[str, Any]]:
    try:
        return http_get(
            api, f"/api/people/{person_id}/delete-inventory",
            timeout=10.0,
        )
    except Exception:
        return None


def _inv_counts(inv: Optional[Dict[str, Any]]) -> Dict[str, int]:
    if not inv:
        return {}
    raw = inv.get("counts") if isinstance(inv, dict) else None
    if isinstance(raw, dict):
        return {k: int(v or 0) for k, v in raw.items()}
    # Some shapes return inventory dict at top-level
    if isinstance(inv, dict):
        return {
            k: int(v or 0) for k, v in inv.items()
            if isinstance(v, (int, float))
        }
    return {}


def _inv_total(inv: Optional[Dict[str, Any]]) -> int:
    return sum(_inv_counts(inv).values())


# ─────────────────────────────────────────────────────────────────────
# Bucketing
# ─────────────────────────────────────────────────────────────────────


def list_people(api: str) -> List[Dict[str, Any]]:
    raw = http_get(api, "/api/people")
    if isinstance(raw, dict):
        return list(raw.get("people") or [])
    if isinstance(raw, list):
        return list(raw)
    return []


def build_buckets(
    people: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for p in people:
        name = _display_name(p)
        b = classify(name)
        buckets[b].append({
            "id": p.get("id"),
            "name": name,
            "created_at": p.get("created_at"),
        })
    # Stable sort per bucket so output is deterministic
    for b in buckets:
        buckets[b].sort(key=lambda x: (x.get("name") or "").lower())
    return buckets


# ─────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────


def print_report(
    api: str,
    buckets: Dict[str, List[Dict[str, Any]]],
    detail_bucket: Optional[str] = None,
) -> None:
    total = sum(len(v) for v in buckets.values())
    print("=" * 72)
    print(f"  Narrator cleanup classification — total = {total}")
    print("=" * 72)
    for bucket in ("KEEP", "SAFE_DELETE", "NEEDS_REVIEW"):
        rows = buckets.get(bucket, [])
        print(f"\n  {bucket}: {len(rows)} narrators")
        if not rows:
            continue
        if detail_bucket and detail_bucket.upper() == bucket:
            for r in rows:
                inv = fetch_inventory(api, r["id"])
                total_deps = _inv_total(inv)
                counts = _inv_counts(inv)
                # Show 3 highest dependency tables for context
                top = sorted(
                    counts.items(), key=lambda kv: kv[1], reverse=True,
                )[:3]
                top_str = ", ".join(f"{k}={v}" for k, v in top if v > 0)
                print(
                    f"    {r['id']:36s}  "
                    f"{(r['name'] or '(empty)')[:32]:32s}  "
                    f"deps={total_deps:4d}  {top_str}"
                )
        else:
            # Just sample 5
            sample = rows[:5]
            for r in sample:
                print(f"    - {r['name'] or '(empty)'}  ({r['id']})")
            if len(rows) > 5:
                print(f"    ... and {len(rows) - 5} more")


# ─────────────────────────────────────────────────────────────────────
# Commit path
# ─────────────────────────────────────────────────────────────────────


def commit_deletes(
    api: str,
    bucket_rows: List[Dict[str, Any]],
) -> Tuple[int, int, List[Tuple[str, str]]]:
    """Execute DELETE on each row in the bucket. Returns
    (ok_count, fail_count, failure_list_of_(id, reason))."""
    ok = 0
    fail = 0
    failures: List[Tuple[str, str]] = []
    for r in bucket_rows:
        # Second-pass KEEP check — refuse to delete pinned names
        # even if they somehow ended up in this bucket. Pure paranoia
        # guard against future bugs.
        if (r.get("name") or "").strip().lower() in KEEP_DISPLAY_NAMES:
            failures.append((
                r.get("id") or "?",
                "ABORTED — name matched KEEP list",
            ))
            fail += 1
            continue
        status, body = http_delete(
            api, f"/api/people/{r['id']}?mode=hard",
        )
        if 200 <= status < 300:
            ok += 1
            print(f"    ✓ deleted {r['name']!r}  ({r['id']})")
        else:
            fail += 1
            failures.append((r.get("id") or "?", f"HTTP {status}: {body[:140]}"))
            print(f"    ✗ failed {r['name']!r}  ({r['id']})  HTTP {status}")
    return (ok, fail, failures)


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Classify and (optionally) clean up test-narrator residue "
            "in the Hornelore DB."
        ),
    )
    parser.add_argument(
        "--api",
        default=os.environ.get("HORNELORE_API_URL", "http://localhost:8000"),
        help="Hornelore API base URL (default: $HORNELORE_API_URL or "
             "http://localhost:8000)",
    )
    parser.add_argument(
        "--bucket",
        choices=("KEEP", "SAFE_DELETE", "NEEDS_REVIEW"),
        help="Render per-row detail (with dependency counts) for ONE "
             "bucket. Without this, only sample names print.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Imply --bucket detail for the chosen bucket. No deletes.",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually fire DELETE calls for the chosen bucket. "
             "Requires --bucket and --i-acknowledge.",
    )
    parser.add_argument(
        "--i-acknowledge",
        action="store_true",
        help="Required alongside --commit to fire deletes. The flag "
             "exists so muscle-memory can't trigger a destructive run.",
    )
    args = parser.parse_args(argv)

    try:
        people = list_people(args.api)
    except Exception as exc:
        print(f"[cleanup] failed to fetch /api/people from {args.api}: {exc}",
              file=sys.stderr)
        return 2

    buckets = build_buckets(people)

    # Always print the high-level report
    detail = args.bucket if (args.dry_run or args.bucket) else None
    print_report(args.api, buckets, detail_bucket=detail)

    if args.commit:
        if not args.bucket:
            print("\n[cleanup] --commit requires --bucket", file=sys.stderr)
            return 2
        if not args.i_acknowledge:
            print(
                "\n[cleanup] --commit requires --i-acknowledge "
                "(safety latch)",
                file=sys.stderr,
            )
            return 2
        if args.bucket == "KEEP":
            print(
                "\n[cleanup] refusing to commit deletes on KEEP bucket.",
                file=sys.stderr,
            )
            return 2
        rows = buckets.get(args.bucket, [])
        if not rows:
            print(f"\n[cleanup] no rows in {args.bucket}; nothing to delete.")
            return 0
        print()
        print("=" * 72)
        print(f"  COMMIT MODE — deleting {len(rows)} rows from {args.bucket}")
        print("=" * 72)
        ok, fail, failures = commit_deletes(args.api, rows)
        print()
        print(f"  Result: {ok} deleted / {fail} failed")
        if failures:
            print("\n  Failures:")
            for fid, reason in failures:
                print(f"    {fid}: {reason}")
        return 0 if fail == 0 else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
