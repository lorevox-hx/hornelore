#!/usr/bin/env python3
"""Direct Phase 4 persistence verification — preserve_turn → DB
roundtrip for chain_meta_json.

WO-LORI-FACTUAL-CHAIN-CAPTURE-01 Phase 4 wires chain_meta_json into
story_candidates via:

    chat_ws → story_preservation.preserve_turn(chain_meta=...) →
    db.story_candidate_insert(chain_meta_json=...) →
    sqlite story_candidates row

The live chat-WS harnesses (run_factual_chain_live_harness.py and
run_trip_route_canary_harness.py) can NOT prove this wire because
their narrator turns are typed text. story_trigger.classify_story_
candidate requires either:

  * audio_duration_sec ≥ 30s AND words ≥ 60 AND ≥1 anchor (full_threshold)
  * ≥3 dimension-anchors (borderline_scene_anchor)
  * audio_duration_sec ≥ 10s AND words ≥ 15 AND place+(person|time)
    (rich_short_narrative)

None of those fire on short text-only WS turns, so chat_ws never
calls preserve_turn, so no story_candidate row is created, so
chain_meta_json can't be observed. The live harnesses correctly
report D1=False but that's a story_trigger design boundary, NOT a
chain_meta wiring failure.

This script verifies the Phase 4 wire directly by calling preserve_
turn with an explicit chain_meta payload (bypassing story_trigger)
and reading back the row to assert the JSON roundtrip + shape.

Usage:

    cd /mnt/c/Users/chris/hornelore
    .venv-gpu/bin/python scripts/verify_chain_meta_persistence.py

Stack does NOT need to be running. The script imports db.py and
story_preservation.py directly and operates on the sqlite file at
DATA_DIR/db/DB_NAME.

Exit code 0 = GREEN, 1 = RED.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))

from api import db  # noqa: E402
from api.services import story_preservation  # noqa: E402


# Test narrator id — fixed UUID prefix so the test narrator's rows are
# easy to identify + clean up. The full uuid varies per run to avoid
# unique-constraint collisions on re-runs.
_TEST_NARRATOR_PREFIX = "00000000-test-chain"


def _make_test_narrator_id() -> str:
    """Build a per-run UUID-shaped id under the test prefix."""
    suffix = uuid.uuid4().hex[:12]
    return f"{_TEST_NARRATOR_PREFIX}-{suffix[:4]}-{suffix[4:]}"


def _db_path() -> Path:
    """Use db.py's own DB_PATH constant as the single source of truth.
    Computing the path from os.getenv directly diverges when the
    script is run without .env sourcing — db.py defaults to
    DATA_DIR='data' and DB_NAME='lorevox.sqlite3', while our manual
    computation defaulted to '/mnt/c/hornelore_data'/'hornelore.sqlite3'.
    The mismatch made db.story_candidate_insert go to one file and
    raw sqlite queries hit another (2026-06-24 persistence-test RED
    on the raw-column row, despite all dict-shape assertions PASSing
    via db.story_candidate_get)."""
    return db.DB_PATH


def _ensure_test_narrator(narrator_id: str) -> None:
    """Insert a minimal person row so the FK on story_candidates is
    satisfied. Idempotent — uses INSERT OR IGNORE."""
    con = sqlite3.connect(str(_db_path()))
    try:
        # Schema for the people table is opaque to this script — only
        # narrator_id is required for the FK. If the people table has
        # NOT NULL columns this insert will fail loud and we'll know.
        con.execute(
            "INSERT OR IGNORE INTO people (id, display_name) VALUES (?, ?);",
            (narrator_id, "Chain Persistence Test"),
        )
        con.commit()
    finally:
        con.close()


def _cleanup_test_rows(narrator_id: str) -> None:
    """Delete the test narrator's story_candidates rows + people row
    + filesystem-mirror folder so the test doesn't accumulate state
    across runs. story_preservation also writes a per-story folder
    under DATA_DIR/stories-captured/<narrator_id>/ when HORNELORE_
    STORIES_CAPTURED_FS=1 (Chris's .env default); without this cleanup
    those folders pile up at ~2 files per run (audio + json metadata)
    and show in `git status` as untracked even though they're runtime
    garbage. .gitignore entry was added 2026-06-24 to prevent
    accidental commits."""
    con = sqlite3.connect(str(_db_path()))
    try:
        con.execute(
            "DELETE FROM story_candidates WHERE narrator_id = ?;",
            (narrator_id,),
        )
        con.execute("DELETE FROM people WHERE id = ?;", (narrator_id,))
        con.commit()
    except sqlite3.Error:
        pass
    finally:
        con.close()

    # FS mirror cleanup
    import shutil
    data_dir = os.getenv("DATA_DIR", str(getattr(db, "DATA_DIR", "data")))
    fs_mirror = Path(data_dir) / "stories-captured" / narrator_id
    if fs_mirror.exists() and fs_mirror.is_dir():
        try:
            shutil.rmtree(fs_mirror)
        except Exception:
            pass


def _assert(name: str, ok: bool, detail: str = "") -> Tuple[bool, str]:
    if ok:
        return True, f"  [PASS] {name}"
    return False, f"  [FAIL] {name} — {detail}"


def run() -> int:
    print("=" * 78)
    print("Phase 4 direct persistence verification (chain_meta_json)")
    print("=" * 78)

    db_path = _db_path()
    if not db_path.exists():
        print(f"\n✗ RED — db file not found at {db_path}")
        return 1

    narrator_id = _make_test_narrator_id()
    print(f"\nTest narrator id: {narrator_id}")
    print(f"DB: {db_path}\n")

    rows_out: List[Tuple[bool, str]] = []

    try:
        # Step 1 — ensure the test narrator exists (FK requirement).
        try:
            _ensure_test_narrator(narrator_id)
        except Exception as exc:
            print(f"✗ RED — could not insert test narrator: {exc}")
            return 1

        # Step 2 — preserve_turn with an explicit chain_meta payload.
        chain_meta_payload: Dict[str, Any] = {
            "chain_story_candidate": True,
            "chain_anchors": ["Prague", "Salzburg", "Ljubljana"],
            "chain_cue_labels": [
                "multi_place_sequence",
                "travel_leg_sequence",
            ],
            "chain_confidence": 0.85,
            "chain_blocked_probe_types": [
                "sensory",
                "atmosphere",
                "camaraderie",
            ],
            "chain_preferred_followup_type": "next_factual_link",
            "chain_missing_links": [],
        }
        turn_id_for_test = f"persist-test-{uuid.uuid4().hex[:8]}"
        try:
            candidate_id = story_preservation.preserve_turn(
                narrator_id=narrator_id,
                transcript=(
                    "Direct Phase 4 persistence canary — Prague then "
                    "Salzburg then Ljubljana."
                ),
                trigger_reason="manual",
                scene_anchor_count=3,
                turn_id=turn_id_for_test,
                chain_meta=chain_meta_payload,
            )
        except Exception as exc:
            print(f"✗ RED — preserve_turn raised: {exc}")
            return 1
        rows_out.append(_assert(
            "preserve_turn returned a candidate id",
            bool(candidate_id),
            f"got {candidate_id!r}",
        ))

        # Step 3 — read the row back via the canonical accessor.
        row = db.story_candidate_get(candidate_id)
        rows_out.append(_assert(
            "story_candidate_get returned the row",
            row is not None,
            "row is None",
        ))
        if row is None:
            for _, line in rows_out:
                print(line)
            return 1

        # Step 4 — chain_meta keys round-tripped from JSON.
        chain_meta_out = row.get("chain_meta")
        rows_out.append(_assert(
            "row.chain_meta is a dict",
            isinstance(chain_meta_out, dict),
            f"got {type(chain_meta_out).__name__}",
        ))
        if isinstance(chain_meta_out, dict):
            rows_out.append(_assert(
                "chain_story_candidate == True",
                chain_meta_out.get("chain_story_candidate") is True,
                repr(chain_meta_out.get("chain_story_candidate")),
            ))
            rows_out.append(_assert(
                "chain_anchors preserved",
                chain_meta_out.get("chain_anchors")
                == ["Prague", "Salzburg", "Ljubljana"],
                repr(chain_meta_out.get("chain_anchors")),
            ))
            rows_out.append(_assert(
                "chain_cue_labels preserved",
                chain_meta_out.get("chain_cue_labels")
                == ["multi_place_sequence", "travel_leg_sequence"],
                repr(chain_meta_out.get("chain_cue_labels")),
            ))
            rows_out.append(_assert(
                "chain_confidence ≈ 0.85",
                abs(
                    float(chain_meta_out.get("chain_confidence") or 0.0)
                    - 0.85
                ) < 1e-6,
                repr(chain_meta_out.get("chain_confidence")),
            ))
            rows_out.append(_assert(
                "chain_blocked_probe_types preserved",
                chain_meta_out.get("chain_blocked_probe_types")
                == ["sensory", "atmosphere", "camaraderie"],
                repr(chain_meta_out.get("chain_blocked_probe_types")),
            ))
            rows_out.append(_assert(
                "chain_preferred_followup_type preserved",
                chain_meta_out.get("chain_preferred_followup_type")
                == "next_factual_link",
                repr(chain_meta_out.get("chain_preferred_followup_type")),
            ))

        # Step 5 — raw column has the JSON shape we expect.
        con = sqlite3.connect(str(db_path))
        try:
            cur = con.execute(
                "SELECT chain_meta_json FROM story_candidates "
                "WHERE id = ?;",
                (candidate_id,),
            )
            raw = cur.fetchone()
        finally:
            con.close()
        rows_out.append(_assert(
            "chain_meta_json column is non-empty",
            raw is not None and raw[0] and raw[0] != "{}",
            repr(raw[0] if raw else None),
        ))

        # Step 6 — second preserve_turn with empty chain_meta defaults
        # to '{}' (byte-stable for non-chain callers).
        try:
            cid2 = story_preservation.preserve_turn(
                narrator_id=narrator_id,
                transcript=(
                    "Direct Phase 4 byte-stability canary — no chain meta."
                ),
                trigger_reason="manual",
                scene_anchor_count=0,
                turn_id=f"persist-empty-{uuid.uuid4().hex[:8]}",
            )
            row2 = db.story_candidate_get(cid2)
            rows_out.append(_assert(
                "default chain_meta is empty dict",
                row2 is not None and row2.get("chain_meta") == {},
                repr(row2.get("chain_meta") if row2 else None),
            ))
        except Exception as exc:
            rows_out.append(_assert(
                "default chain_meta byte-stability",
                False, str(exc),
            ))

    finally:
        # Always clean up the test narrator rows.
        try:
            _cleanup_test_rows(narrator_id)
        except Exception as exc:
            print(f"[WARN] cleanup failed: {exc}", file=sys.stderr)

    all_pass = all(ok for ok, _ in rows_out)
    for _, line in rows_out:
        print(line)
    print()
    if all_pass:
        print(f"GREEN chain_meta_persistence  ({len(rows_out)}/{len(rows_out)})")
        return 0
    passed = sum(1 for ok, _ in rows_out if ok)
    print(f"RED chain_meta_persistence  ({passed}/{len(rows_out)})")
    return 1


if __name__ == "__main__":
    sys.exit(run())
