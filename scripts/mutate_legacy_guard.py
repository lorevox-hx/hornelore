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

SUITES = ("tests/test_suggestion_flags.py", "tests/test_suggestion_identity.py")

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

    # ── the second producer ──────────────────────────────────────────
    # Mutates the constructor itself rather than swapping in a stand-in.
    # An earlier version needed a `_legacy_shape` helper in the shipping
    # module to mutate INTO — test scaffolding living in production
    # source, which is its own defect.
    ("the correction path goes back to queuing without an id",
     "server/code/api/services/projection_writer.py",
     '        "suggestion_id": "sg_" + uuid.uuid4().hex[:16],\n',
     ''),

    ("the writer claims a destination is fine when the schema is unreadable",
     "server/code/api/services/projection_writer.py",
     '        entry["destination_undefined"] = True\n    return entry',
     '        entry["destination_undefined"] = False\n    return entry'),

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

    survivors = 0
    for i, (name, rel, old, new) in enumerate(MUTATIONS, 1):
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
    if survivors:
        print(f"  {R}{survivors} of {len(MUTATIONS)} survived.{X}\n")
    else:
        print(f"  {G}All {len(MUTATIONS)} caught.{X}\n")
    shutil.rmtree(base, ignore_errors=True)
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
