"""Break the legacy guard and the identity work fourteen ways.

Every break must be caught.

A test that passes against broken code is decoration. These are the
mistakes most likely to be made while editing this later — each is
applied to a COPY of the tree, the focused suite is run against it, and
a mutation that SURVIVES is reported as a hole in the tests.

Completion is checked, not assumed: a run that crashes before reaching
the assertions would otherwise read as "survived".

    python3 scripts/mutate_legacy_guard.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
G, R, Y, X = "\033[32m", "\033[31m", "\033[33m", "\033[0m"

FLAGS = "server/code/api/services/suggestion_flags.py"
REVIEW = "server/code/api/services/suggestion_review.py"
IDENT = "scripts/backfill_suggestion_ids.py"

ENTRY = "server/code/api/services/suggestion_entry.py"
DBMOD = "server/code/api/db.py"
WRITER = "server/code/api/services/projection_writer.py"

SUITES = ("tests/test_suggestion_flags.py",
          "tests/test_suggestion_identity.py",
          "tests/test_suggestion_queue_persistence.py",
          "tests/test_projection_read_safety.py")

MUTATIONS = [
    ("the acknowledge tier is removed entirely",
     FLAGS,
     """    # A destination that existed all along. The proposal may well be
    # right — and this tier says nothing about whether it is. It says
    # only that it is old and unreviewed, and that someone should read
    # it before it becomes permanent.
    return SuggestionFlagged(""",
     """    return None
    return SuggestionFlagged("""),

    ("a checkbox satisfies a CORRECTION requirement",
     REVIEW,
     "        _satisfied = corrected or (\n"
     "            blocker.requirement == _flags.REQUIRE_ACKNOWLEDGE and acknowledge_legacy)",
     "        _satisfied = corrected or acknowledge_legacy"),

    ("the FIRST requirement found wins, not the strongest",
     FLAGS,
     "    return b if _STRENGTH.index(b.requirement) > _STRENGTH.index(a.requirement) else a",
     "    return a"),

    # Layer 2's tier test. The pre-check catches every ordinary case, so
    # only a requirement that appears MID-FLIGHT can expose this.
    ("the in-transaction check stops distinguishing the two tiers",
     REVIEW,
     "            if not (corrected or (_blocker2.requirement == _flags.REQUIRE_ACKNOWLEDGE\n"
     "                                  and acknowledge_legacy)):\n"
     "                raise _blocker2",
     "            if not (corrected or acknowledge_legacy):\n"
     "                raise _blocker2"),

    ("a re-run erases a suggestion_id it already knew",
     FLAGS,
     "        \"  suggestion_id=COALESCE(suggestion_flags.suggestion_id, excluded.suggestion_id), \"",
     "        \"  suggestion_id=excluded.suggestion_id, \""),

    ("legacy_unreviewed becomes recordable",
     FLAGS,
     'REASONS = (\n    "queued_before_home",',
     'REASONS = (\n    "legacy_unreviewed",\n    "queued_before_home",'),

    # ── the identity operation ───────────────────────────────────────
    ("identity is derived from content alone, so duplicates collide",
     IDENT,
     '        str(person_id), str(index),',
     '        str(person_id),'),

    ("the backfill writes destination_undefined too",
     IDENT,
     '            adds = {"suggestion_id": sid}',
     '            adds = {"suggestion_id": sid, "destination_undefined": False}'),

    ("repeatable sections stop getting destination_unresolved",
     IDENT,
     '            if "destination_unresolved" not in s and sec in REPEATABLE_SECTIONS:\n'
     '                adds["destination_unresolved"] = True',
     '            pass'),

    ("turn_evidence is assumed absent instead of measured",
     IDENT,
     '                adds["turn_evidence"] = verify_turn(con, r["pid"], s.get("turnId"))',
     '                adds["turn_evidence"] = "absent"'),

    ("an entry that already has an id is re-identified",
     IDENT,
     '            if not isinstance(s, dict) or s.get("suggestion_id"):\n'
     '                continue',
     '            if not isinstance(s, dict):\n                continue'),

    # ── the shared constructor ───────────────────────────────────────
    # Mutates the constructor itself rather than swapping in a stand-in.
    # An earlier version needed a `_legacy_shape` helper in the shipping
    # module to mutate INTO — test scaffolding living in production
    # source, which is its own defect.
    ("no producer mints an id at all",
     ENTRY,
     '        "suggestion_id": mint_id(),\n',
     ''),

    ("the constructor claims a destination is fine when the schema is unreadable",
     ENTRY,
     '        entry["destination_undefined"] = True\n        # Unknown',
     '        entry["destination_undefined"] = False\n        # Unknown'),

    ("an indexed path stops being marked unresolved",
     ENTRY,
     '    section = head.split("[")[0]',
     '    section = head'),

    # ── the queue-replacement paths (outside review, 2026-09-20) ─────
    ("the correction writer goes back to sending a stale whole array",
     WRITER,
     "            pending_mutator=(_replay if (_queue_edits or _retract_tokens) else None),",
     "            pending_suggestions=(pending if _pending_changed else None),"),

    ("the mutator is handed the caller's snapshot instead of stored state",
     DBMOD,
     '            merged["pendingSuggestions"] = list(pending_mutator(current_pending))',
     '            merged["pendingSuggestions"] = list(pending_mutator(\n'
     '                list(pending_suggestions or [])))'),

    ("a stale base_pending is accepted instead of contested",
     DBMOD,
     "            if base_pending is not None and \\\n"
     "                    json.dumps(base_pending, sort_keys=True) != \\\n"
     "                    json.dumps(current_pending, sort_keys=True):",
     "            if False:"),

    ("the backfill stops checking the projection version under the lock",
     IDENT,
     '            if int(row["version"]) != items[0]["version"]:',
     "            if False:"),

    ("collisions are skipped instead of refusing the operation",
     IDENT,
     '            if sid in taken or sid in proposed:\n'
     '                raise SystemExit(',
     '            if False:\n                raise SystemExit('),
]


def run(tree: Path):
    """Both suites. A mutation caught by either is caught."""
    rc, tails, total = 0, [], 0
    complete = True
    for suite in SUITES:
        p = subprocess.run([sys.executable, suite],
                           cwd=tree, capture_output=True, text=True, timeout=300)
        lines = p.stderr.strip().splitlines()
        ran = [l for l in lines if l.startswith("Ran ")]
        if not ran:
            complete = False
        else:
            total += int(ran[0].split()[1])
        rc = rc or p.returncode
        tails += lines
    return rc, (f"Ran {total} tests" if complete else ""), tails


def main() -> int:
    base = Path(tempfile.mkdtemp(prefix="mut_"))
    src = base / "clean"
    # Only what the focused suite touches. Copying the whole repo off a
    # mounted filesystem takes minutes and copies it seven times.
    src.mkdir(parents=True)
    ign = shutil.ignore_patterns("__pycache__", "node_modules", "*.sqlite3", "*.pyc")
    for part in ("server/code", "tests", "ui/js", "scripts"):
        shutil.copytree(REPO / part, src / part, ignore=ign)

    rc, ran, tail = run(src)
    if rc != 0:
        print(f"{R}The suite does not pass unmutated. Nothing below means anything.{X}")
        print("\n".join(tail[-15:]))
        return 1
    print(f"\n  baseline: {G}{ran}, all pass{X}\n")

    # Chunking. The whole matrix is ~7 minutes and some runners cap a
    # single invocation well below that, so a run that cannot finish
    # reports nothing at all — which reads exactly like a run that found
    # nothing. `--slice 0:5` runs a window; the caller is responsible
    # for covering the range.
    lo, hi = 0, len(MUTATIONS)
    for a in sys.argv[1:]:
        if a.startswith("--slice"):
            spec = a.split("=", 1)[1] if "=" in a else sys.argv[sys.argv.index(a) + 1]
            lo, hi = (int(x) if x else d for x, d in
                      zip(spec.split(":"), (0, len(MUTATIONS))))
    window = list(enumerate(MUTATIONS, 1))[lo:hi]
    if (lo, hi) != (0, len(MUTATIONS)):
        print(f"  running mutations {lo}..{hi} of {len(MUTATIONS)}\n")

    survivors = 0
    for i, (name, rel, old, new) in window:
        tree = base / f"m{i}"
        shutil.copytree(src, tree)
        f = tree / rel
        text = f.read_text(encoding="utf-8")
        if old not in text:
            print(f"  {Y}{i}. SKIPPED{X}  {name}")
            print(f"        the anchor text is gone — this mutation no longer "
                  f"describes the code")
            survivors += 1
            continue
        f.write_text(text.replace(old, new, 1), encoding="utf-8")

        rc, ran, tail = run(tree)
        if not ran:
            print(f"  {Y}{i}. INCOMPLETE{X}  {name}")
            print(f"        the run did not finish — that is not the same as caught")
            print("        " + "\n        ".join(tail[-6:]))
            survivors += 1
            continue
        if rc == 0:
            print(f"  {R}{i}. SURVIVED{X}  {name}")
            print(f"        {ran} and nothing failed — the tests do not cover this")
            survivors += 1
        else:
            fails = [l for l in tail if l.startswith(("FAIL:", "ERROR:"))]
            print(f"  {G}{i}. caught{X}    {name}")
            print(f"        {ran}, {len(fails)} failed")
            for l in fails[:3]:
                print(f"          {l.split('(')[0].strip()}")

    print()
    if (lo, hi) != (0, len(MUTATIONS)):
        print(f"  window {lo}..{hi}: {len(window) - survivors}/{len(window)} caught"
              + (f", {R}{survivors} SURVIVED{X}" if survivors else "") + "\n")
        shutil.rmtree(base, ignore_errors=True)
        return 1 if survivors else 0
    if survivors:
        print(f"  {R}{survivors} of {len(MUTATIONS)} survived.{X}\n")
    else:
        print(f"  {G}All {len(MUTATIONS)} caught.{X}\n")
    shutil.rmtree(base, ignore_errors=True)
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
