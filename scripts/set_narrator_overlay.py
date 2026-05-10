#!/usr/bin/env python3
"""BANK_PRIORITY_REBUILD 2026-05-10 — operator script.

Pin a narrator's narrator_voice_overlay in profile_json. Four values:

  adult_competence — Kent overlay. Sensory questions are bank-only;
                     responsibility/mechanism/role-transition wins
                     immediate. Logistics > scenery, mechanism >
                     atmosphere. Per Chris's 2026-05-10 lock.
  hearth_sensory   — Prairie / domestic / homemaker overlay. Sensory
                     and atmospheric questions are first-class
                     immediates. Janice candidate (TBD by operator).
  shield_protected — Sensitive narrator overlay. No immediate
                     question; bank only. Operator review surface.
  default          — No overlay (current Lori behavior). Sensory and
                     responsibility doors compete on raw priority +
                     story_weight without overlay-specific filtering.

When unset (legacy narrators), `_build_profile_seed` defaults to
"default" and the bank selector treats every door equally on
priority + story_weight. The overlay is the operator's declaration;
Lori never guesses.

Usage:

  # List all narrators + their current overlay
  python3 scripts/set_narrator_overlay.py --list

  # Set Kent's narrator (by display_name match) to adult_competence
  python3 scripts/set_narrator_overlay.py --name "Kent" --overlay adult_competence

  # Set by exact person_id
  python3 scripts/set_narrator_overlay.py --person-id <uuid> --overlay adult_competence

  # Set Kent + Marvin in one shot (both adult_competence)
  python3 scripts/set_narrator_overlay.py --batch-adult-competence Kent Marvin

LAW: this is operator-side. It writes to profile_json via the standard
db.update_profile_json accessor. No schema changes, no migration
required — narrators without the field continue to behave as before
(default overlay). The overlay is read by `_build_profile_seed` in
prompt_composer.py and threaded through chat_ws → bank selector.

Pre-Kent-session usage tonight:

  python3 scripts/set_narrator_overlay.py --name "Kent" --overlay adult_competence

Then no stack restart required — the overlay is read from profile_json
on every turn; next turn picks it up.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_VALID_OVERLAYS = (
    "adult_competence",
    "hearth_sensory",
    "shield_protected",
    "default",
)

# Aliases mirror prompt_composer._build_profile_seed normalization.
_OVERLAY_ALIASES = {
    "competence": "adult_competence",
    "kent": "adult_competence",
    "military": "adult_competence",
    "labor": "adult_competence",
    "prairie": "hearth_sensory",
    "domestic": "hearth_sensory",
    "homemaker": "hearth_sensory",
    "hearth": "hearth_sensory",
    "sensitive": "shield_protected",
    "protected": "shield_protected",
    "shield": "shield_protected",
    "none": "default",
    "off": "default",
    "": "default",
}


def _setup_paths() -> None:
    """Make code.api importable. Mirrors set_session_language_mode.py."""
    repo_root = Path(__file__).resolve().parent.parent
    server_root = repo_root / "server"
    if str(server_root) not in sys.path:
        sys.path.insert(0, str(server_root))


def _normalize_overlay(overlay: str) -> str:
    o = (overlay or "").strip().lower()
    if o in _VALID_OVERLAYS:
        return o
    if o in _OVERLAY_ALIASES:
        return _OVERLAY_ALIASES[o]
    raise ValueError(
        f"Unknown overlay {overlay!r}. Use one of: "
        + ", ".join(_VALID_OVERLAYS)
    )


def _list_narrators() -> List[Dict[str, Any]]:
    from code.api import db as _db  # type: ignore[import-not-found]
    _db.init_db()
    con = _db._connect()
    cur = con.execute(
        "SELECT p.id, p.display_name, pr.profile_json "
        "FROM people p LEFT JOIN profiles pr ON pr.person_id = p.id "
        "ORDER BY p.display_name;"
    )
    rows = []
    for pid, display, blob in cur.fetchall():
        prof = {}
        if blob:
            try:
                import json
                prof = json.loads(blob) if isinstance(blob, str) else blob
            except Exception:
                prof = {}
        overlay = prof.get("narrator_voice_overlay") or "(unset)"
        slm = prof.get("session_language_mode") or "(unset)"
        rows.append({
            "person_id": pid,
            "display_name": display or "(no name)",
            "narrator_voice_overlay": overlay,
            "session_language_mode": slm,
        })
    con.close()
    return rows


def _resolve_person_id(name_or_id: str) -> Tuple[str, str]:
    """Return (person_id, display_name). Mirrors set_session_language_mode."""
    from code.api import db as _db  # type: ignore[import-not-found]
    _db.init_db()
    if "-" in name_or_id and len(name_or_id) >= 32:
        con = _db._connect()
        cur = con.execute(
            "SELECT display_name FROM people WHERE id=?;",
            (name_or_id,),
        )
        row = cur.fetchone()
        con.close()
        display = row[0] if row else "(no people row yet)"
        return name_or_id, display
    con = _db._connect()
    cur = con.execute(
        "SELECT id, display_name FROM people "
        "WHERE LOWER(display_name) LIKE ? "
        "ORDER BY display_name;",
        (f"%{name_or_id.lower()}%",),
    )
    matches = cur.fetchall()
    con.close()
    if not matches:
        raise ValueError(f"No narrator matches name {name_or_id!r}")
    if len(matches) > 1:
        names = ", ".join(d for _, d in matches)
        raise ValueError(
            f"Multiple narrators match {name_or_id!r}: {names}. "
            "Use --person-id to disambiguate."
        )
    return matches[0]


def _ensure_people_row(person_id: str, display_name: str) -> None:
    """Ensure a row exists in the `people` table for `person_id`.

    Harness UUIDs (e.g. Kent's `4aa0cc2b-…`) are sometimes used by
    test scripts that run BEFORE the FE has had a chance to create
    the people row via the normal new-narrator flow. Without this
    row, `update_profile_json → ensure_profile` fails with
    `FOREIGN KEY constraint failed` because `profiles.person_id`
    has a FK to `people.id`.

    This function is the operator-side equivalent of the chat_ws
    auto-create path: idempotent INSERT OR IGNORE with sensible
    defaults. Re-running is safe.
    """
    from code.api import db as _db  # type: ignore[import-not-found]
    _db.init_db()
    con = _db._connect()
    try:
        cur = con.execute(
            "SELECT 1 FROM people WHERE id=? LIMIT 1;", (person_id,),
        )
        if cur.fetchone():
            return  # already exists
        # Insert minimal row mirroring db.create_person() shape.
        # Use display_name when known; "(harness-pinned)" otherwise.
        # narrator_type=primary as a safe default.
        now = _db._now_iso()
        nt = _db._normalise_narrator_type("primary")
        dn = display_name if display_name and display_name != "(no people row yet)" \
            else "(harness-pinned)"
        con.execute(
            """
            INSERT INTO people(
                id, display_name, role, date_of_birth, place_of_birth,
                created_at, updated_at, narrator_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (person_id, dn, "", "", "", now, now, nt),
        )
        con.commit()
        print(
            f"  + created people row for {person_id[:8]}… "
            f"display_name={dn!r}"
        )
    finally:
        con.close()


def _apply_overlay(
    person_id: str,
    display_name: str,
    overlay: str,
) -> None:
    from code.api import db as _db  # type: ignore[import-not-found]
    _db.init_db()
    # 2026-05-10 fix — prevent FOREIGN KEY constraint failed when the
    # operator pins an overlay on a harness-only UUID that never had
    # a `people` row created (e.g. Kent's harness UUID). The chat_ws
    # write path has the same FK issue; creating the people row here
    # also unblocks softened/turn_count writes during live sessions.
    _ensure_people_row(person_id, display_name)
    cur = _db.get_profile(person_id) or {}
    prof = dict(cur.get("profile_json") or {})
    prev = prof.get("narrator_voice_overlay") or "(unset)"
    prof["narrator_voice_overlay"] = overlay
    _db.update_profile_json(
        person_id, prof, merge=False,
        reason=f"set_narrator_overlay={overlay}",
    )
    print(
        f"  ✓ {display_name} ({person_id[:8]}…) → "
        f"narrator_voice_overlay={overlay} (was {prev})"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Pin a narrator's narrator_voice_overlay in profile_json. "
            "Per BANK_PRIORITY_REBUILD 2026-05-10."
        ),
    )
    parser.add_argument("--list", action="store_true",
                        help="List all narrators + current overlay")
    parser.add_argument("--name", help="Display-name substring match")
    parser.add_argument("--person-id", help="Exact person_id (UUID)")
    parser.add_argument(
        "--overlay", choices=list(_VALID_OVERLAYS) + list(_OVERLAY_ALIASES.keys()),
        help="Target overlay",
    )
    parser.add_argument(
        "--batch-adult-competence", nargs="+", metavar="NAME",
        help="Set multiple narrators to adult_competence by name",
    )
    parser.add_argument(
        "--batch-hearth-sensory", nargs="+", metavar="NAME",
        help="Set multiple narrators to hearth_sensory by name",
    )
    parser.add_argument(
        "--batch-default", nargs="+", metavar="NAME",
        help="Reset multiple narrators to default overlay by name",
    )
    args = parser.parse_args()

    _setup_paths()

    if args.list:
        rows = _list_narrators()
        if not rows:
            print("(no narrators found)")
            return 0
        print(
            f"{'person_id':<40} {'display_name':<30} "
            f"{'overlay':<18} {'lang_mode':<10}"
        )
        print("-" * 100)
        for r in rows:
            print(
                f"{r['person_id']:<40} {r['display_name']:<30} "
                f"{r['narrator_voice_overlay']:<18} "
                f"{r['session_language_mode']:<10}"
            )
        return 0

    if args.batch_adult_competence:
        for name in args.batch_adult_competence:
            try:
                pid, display = _resolve_person_id(name)
                _apply_overlay(pid, display, "adult_competence")
            except Exception as exc:
                print(f"  ✗ {name}: {exc}", file=sys.stderr)
        return 0

    if args.batch_hearth_sensory:
        for name in args.batch_hearth_sensory:
            try:
                pid, display = _resolve_person_id(name)
                _apply_overlay(pid, display, "hearth_sensory")
            except Exception as exc:
                print(f"  ✗ {name}: {exc}", file=sys.stderr)
        return 0

    if args.batch_default:
        for name in args.batch_default:
            try:
                pid, display = _resolve_person_id(name)
                _apply_overlay(pid, display, "default")
            except Exception as exc:
                print(f"  ✗ {name}: {exc}", file=sys.stderr)
        return 0

    if not args.overlay:
        parser.error(
            "--overlay is required (or use --list / "
            "--batch-adult-competence / --batch-hearth-sensory / "
            "--batch-default)"
        )
        return 2
    if not (args.name or args.person_id):
        parser.error("--name or --person-id is required")
        return 2

    target = args.person_id or args.name
    try:
        pid, display = _resolve_person_id(target)
    except Exception as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2

    overlay = _normalize_overlay(args.overlay)
    _apply_overlay(pid, display, overlay)
    return 0


if __name__ == "__main__":
    sys.exit(main())
