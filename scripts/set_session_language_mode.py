#!/usr/bin/env python3
"""BUG-LORI-SESSION-LANGUAGE-CONTRACT-01 — operator script.

Pin a narrator's session_language_mode in profile_json. Three values:

  english — Lori always replies in English. Spanish detection on
            narrator text is advisory log only.
  spanish — Lori always replies in Spanish.
  mixed   — Lori may follow per-turn narrator language (code-switching).

When unset (legacy narrators), chat_ws.py falls back to looks_spanish()
heuristic for backward compat with Spanish-tracked narrators that
pre-date the contract field. The pin is the operator's contract; Lori
never guesses for narrators with the field set.

Usage:

  # List all narrators + their current language mode
  python3 scripts/set_session_language_mode.py --list

  # Set Kent's narrator (by display_name match) to english
  python3 scripts/set_session_language_mode.py --name "Kent" --mode english

  # Set by exact person_id
  python3 scripts/set_session_language_mode.py --person-id <uuid> --mode english

  # Set Kent + Janice + Mary + Marvin all to english in one shot
  python3 scripts/set_session_language_mode.py --batch-english Kent Janice Mary Marvin

The script also writes primary_language ("en"/"es") and
allow_code_switching (bool) when --primary and --code-switching are
provided.

LAW: this is operator-side. It writes to profile_json via the standard
db.update_profile_json accessor. No schema changes, no migration
required — narrators without the field continue to behave as before
(falling back to looks_spanish heuristic).

Pre-Kent-session usage tonight:

  python3 scripts/set_session_language_mode.py --batch-english Kent Janice Mary Marvin

Then bounce the stack and re-run replay_kent_deep_witness.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _setup_paths() -> None:
    """Make the code.api module importable.

    db.py uses ``from ..db.migrations_runner import run_pending_migrations``
    which resolves up TWO package levels — so the import root must be
    ``server/`` (not ``server/code/``) for the package path to be
    ``code.api.db`` and `..db` to land at ``code.db``. This matches
    how launchers run uvicorn (cd server/ ; python -m uvicorn
    code.api.main:app).
    """
    repo_root = Path(__file__).resolve().parent.parent
    server_root = repo_root / "server"
    if str(server_root) not in sys.path:
        sys.path.insert(0, str(server_root))


def _normalize_mode(mode: str) -> str:
    m = (mode or "").strip().lower()
    if m in ("english", "en", "en-us", "en_us", "en-gb"):
        return "english"
    if m in ("spanish", "es", "es-mx", "es_mx", "es-es", "español", "espanol"):
        return "spanish"
    if m in ("mixed", "bilingual", "code-switching", "code_switching"):
        return "mixed"
    raise ValueError(
        f"Unknown mode {mode!r}. Use english / spanish / mixed."
    )


def _list_narrators() -> List[Dict[str, Any]]:
    from code.api import db as _db  # type: ignore[import-not-found]
    _db.init_db()
    con = _db._connect()
    # Schema: people.id = primary key, profiles.person_id = FK to people.id.
    # Column names differ across tables so the JOIN must be explicit.
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
        slm = prof.get("session_language_mode") or "(unset)"
        primary = prof.get("primary_language") or ""
        rows.append({
            "person_id": pid,
            "display_name": display or "(no name)",
            "session_language_mode": slm,
            "primary_language": primary,
        })
    con.close()
    return rows


def _resolve_person_id(name_or_id: str) -> Tuple[str, str]:
    """Return (person_id, display_name) from either UUID or display-name match."""
    from code.api import db as _db  # type: ignore[import-not-found]
    _db.init_db()
    if "-" in name_or_id and len(name_or_id) >= 32:
        # Looks like a UUID. people.id is the PK column.
        prof = _db.get_profile(name_or_id)
        if prof:
            con = _db._connect()
            cur = con.execute(
                "SELECT display_name FROM people WHERE id=?;",
                (name_or_id,),
            )
            row = cur.fetchone()
            con.close()
            display = row[0] if row else "(unknown)"
            return name_or_id, display
        raise ValueError(f"No narrator found for person_id={name_or_id}")
    # Otherwise match display_name (case-insensitive substring).
    # SELECT p.id (the PK on people) — this is the value other accessors
    # call "person_id" when working with profiles.
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


def _apply_mode(
    person_id: str,
    display_name: str,
    mode: str,
    primary: Optional[str] = None,
    code_switching: Optional[bool] = None,
) -> None:
    from code.api import db as _db  # type: ignore[import-not-found]
    _db.init_db()
    cur = _db.get_profile(person_id) or {}
    prof = dict(cur.get("profile_json") or {})
    prof["session_language_mode"] = mode
    if primary in ("en", "es"):
        prof["primary_language"] = primary
    if code_switching is not None:
        prof["allow_code_switching"] = bool(code_switching)
    _db.update_profile_json(
        person_id, prof, merge=False,
        reason=f"set_session_language_mode={mode}",
    )
    print(
        f"  ✓ {display_name} ({person_id[:8]}…) → "
        f"session_language_mode={mode}"
        + (f", primary_language={primary}" if primary else "")
        + (f", allow_code_switching={code_switching}" if code_switching is not None else "")
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pin a narrator's session_language_mode in profile_json.",
    )
    parser.add_argument("--list", action="store_true", help="List all narrators + current mode")
    parser.add_argument("--name", help="Display-name substring match")
    parser.add_argument("--person-id", help="Exact person_id (UUID)")
    parser.add_argument(
        "--mode", choices=["english", "spanish", "mixed", "en", "es"],
        help="Target mode",
    )
    parser.add_argument("--primary", choices=["en", "es"], help="Primary language hint (mixed mode)")
    parser.add_argument(
        "--code-switching", choices=["true", "false"],
        help="Allow code-switching in mixed mode",
    )
    parser.add_argument(
        "--batch-english", nargs="+", metavar="NAME",
        help="Set multiple narrators to english by name",
    )
    parser.add_argument(
        "--batch-spanish", nargs="+", metavar="NAME",
        help="Set multiple narrators to spanish by name",
    )
    args = parser.parse_args()

    _setup_paths()

    if args.list:
        rows = _list_narrators()
        if not rows:
            print("(no narrators found)")
            return 0
        print(f"{'person_id':<40} {'display_name':<30} {'mode':<12} {'primary':<8}")
        print("-" * 92)
        for r in rows:
            print(
                f"{r['person_id']:<40} {r['display_name']:<30} "
                f"{r['session_language_mode']:<12} {r['primary_language']:<8}"
            )
        return 0

    if args.batch_english:
        for name in args.batch_english:
            try:
                pid, display = _resolve_person_id(name)
                _apply_mode(pid, display, "english", primary="en", code_switching=False)
            except Exception as exc:
                print(f"  ✗ {name}: {exc}", file=sys.stderr)
        return 0

    if args.batch_spanish:
        for name in args.batch_spanish:
            try:
                pid, display = _resolve_person_id(name)
                _apply_mode(pid, display, "spanish", primary="es", code_switching=False)
            except Exception as exc:
                print(f"  ✗ {name}: {exc}", file=sys.stderr)
        return 0

    if not args.mode:
        parser.error("--mode is required (or use --list / --batch-english / --batch-spanish)")
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

    mode = _normalize_mode(args.mode)
    cs: Optional[bool] = None
    if args.code_switching:
        cs = (args.code_switching == "true")
    _apply_mode(pid, display, mode, primary=args.primary, code_switching=cs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
