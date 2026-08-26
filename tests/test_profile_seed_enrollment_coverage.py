"""Every writer of a `people` row is classified. No reusable opt-out.

WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 1 (2026-08-26).

── HOW TO RUN THIS ───────────────────────────────────────────────────

    PYTHONPATH=server/code python3 -m unittest tests.test_profile_seed_enrollment_coverage

This module reads source text and needs no database, so `.venv` runs it
too. Everything else in Phase 1 needs fastapi.

── WHY THIS FILE EXISTS ──────────────────────────────────────────────

`db.create_person()` now enrolls the narrator in Profile Seed
onboarding inside the same transaction as the `people` row. A person
row inserted around that path is HISTORICAL BY DEFINITION — the
deliberate absence of an onboarding row is how the system says "do not
start a questionnaire on this person" (work order decision 3).

That makes every direct `INSERT INTO people` a decision about whether a
narrator can ever be onboarded, and an unclassified one is a decision
nobody made. So: an EXACT allowlist of synthetic fixtures, an explicit
local marker and reason at each insertion, and a sweep that FAILS when
a fourth appears.

── THE SWEEP THAT MISSED ONE ─────────────────────────────────────────

Worth recording, because it is the failure mode this test is most
likely to have. The first sweep matched `INSERT INTO people` and
`INSERT OR REPLACE INTO people`, reported three insertions, and was
wrong: `scripts/verify_chain_meta_persistence.py` uses
`INSERT OR IGNORE`. **A sweep that misses a writer reports a CLEAN
result, which is worse than no sweep at all** — it converts an unknown
into a false assurance. The pattern below therefore matches any
`INSERT [OR <verb>] INTO people`, and a test asserts the pattern
catches all three spellings.

── WHY THERE IS NO SWITCH ────────────────────────────────────────────

No `skip_enrollment=` argument, no environment variable, no narrator
type carve-out. Any of those would be REUSABLE, and a reusable
enrollment opt-out is how the real intake path eventually acquires one
— at which point new narrators become silently unonboardable through a
flag somebody set for a harness two years earlier. An allowlist keyed
on exact file paths cannot be reached by accident, and adding to it
requires editing a test a reviewer will see.

── THE SWEEP MUST READ CODE, NOT PROSE ───────────────────────────────

The first version of this file searched raw file text and immediately
failed on `scripts/set_narrator_overlay.py` — whose docstring EXPLAINS
that it used to run an `INSERT INTO people`. The explanation is the
most valuable thing in that file and must not be deleted to satisfy a
grep.

So the sweep parses each file with `ast` and searches only STRING
LITERALS USED AS VALUES: docstrings and comments are excluded by
construction, SQL is not. A guard that fires on the comment describing
the guarded thing measures the comment.
"""
from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _docstring_nodes(tree: ast.AST):
    """Every string node that is a docstring or a bare string statement."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                out.add(id(body[0].value))
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            out.add(id(node.value))
    return out


def code_string_literals(path: Path):
    """String literals used as VALUES. Comments and docstrings excluded.

    This is where SQL lives and prose does not.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, SyntaxError):
        return []
    skip = _docstring_nodes(tree)
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in skip]


def code_names(path: Path):
    """Identifiers the code actually uses — names, attributes, defs, args."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, SyntaxError):
        return set()
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                               ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.arg):
            out.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            out.add(node.arg)
    return out

#: Matches `INSERT INTO people`, `INSERT OR IGNORE INTO people`,
#: `INSERT OR REPLACE INTO people`, and any other conflict verb.
_INSERT_PEOPLE = re.compile(
    r"INSERT\s+(?:OR\s+\w+\s+)?INTO\s+people\b", re.IGNORECASE)

#: The marker each exempted insertion must carry, next to its reason.
_MARKER = "PROFILE_SEED_ENROLLMENT_EXEMPT"

#: THE EXACT ALLOWLIST. Repo-relative POSIX paths. Three synthetic
#: fixtures and the one sanctioned product writer.
_SYNTHETIC_EXEMPT = {
    # Fixed-id eval narrators, upserted at hard-coded UUIDs. Meant to
    # behave like pre-migration narrators so an eval's prompt never
    # depends on onboarding state.
    "scripts/archive/seed_test_narrators.py",
    # A disposable acceptance-harness narrator, created and torn down
    # inside one run.
    "scripts/gate7_phase2_acceptance.py",
    # Synthetic, temporary, deleted by `_cleanup_test_rows()` in the
    # same run. Uses `INSERT OR IGNORE`, which the first sweep missed.
    "scripts/verify_chain_meta_persistence.py",
}

#: The one place a real narrator may be created. Not "exempt" — it is
#: the path that DOES enroll.
_PRODUCT_WRITER = "server/code/api/db.py"

_SEARCH_ROOTS = ("server", "scripts", "tools")


def _iter_non_test_python():
    for root_name in _SEARCH_ROOTS:
        root = _REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            parts = set(path.parts)
            if "__pycache__" in parts or "tests" in parts:
                continue
            if path.name.startswith("test_"):
                continue
            yield path


def _files_inserting_people():
    found = set()
    for path in _iter_non_test_python():
        for literal in code_string_literals(path):
            if _INSERT_PEOPLE.search(literal):
                found.add(path.relative_to(_REPO_ROOT).as_posix())
                break
    return found


class SweepTests(unittest.TestCase):

    def test_the_pattern_catches_every_spelling(self):
        """A positive control on the instrument itself.

        Without this, a pattern that matched nothing would produce a
        clean sweep and a green suite.
        """
        for sql in ("INSERT INTO people (id) VALUES (?)",
                    "INSERT OR IGNORE INTO people (id, display_name)",
                    "INSERT OR REPLACE INTO people(id)",
                    "insert into people(id)",
                    "INSERT INTO\n            people("):
            with self.subTest(sql=sql):
                self.assertTrue(_INSERT_PEOPLE.search(sql), sql)

    def test_the_pattern_does_not_match_unrelated_tables(self):
        for sql in ("INSERT INTO people_archive (id)",
                    "INSERT INTO photo_people (id)",
                    "SELECT * FROM people"):
            with self.subTest(sql=sql):
                self.assertIsNone(_INSERT_PEOPLE.search(sql), sql)

    def test_the_extractor_reads_code_and_not_prose(self):
        """A positive control on the stripper, which is easy to make
        vacuous.

        The upper half proves docstrings and comments are EXCLUDED —
        the failure that made the first version of this sweep fire on
        the overlay script's own explanation of the insert it removed.
        The lower half proves real SQL literals are still INCLUDED,
        because a stripper that dropped every string would report a
        clean repository forever.
        """
        import tempfile
        sample = (
            '"""Module docstring mentioning INSERT INTO people."""\n'
            "# A comment mentioning INSERT INTO people.\n"
            "def f():\n"
            '    """Docstring mentioning INSERT INTO people."""\n'
            '    "a bare string statement with INSERT INTO people"\n'
            '    return run("INSERT INTO people (id) VALUES (?)")\n'
        )
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(sample)
            tmp = Path(fh.name)
        self.addCleanup(lambda: tmp.unlink(missing_ok=True))

        literals = code_string_literals(tmp)
        hits = [s for s in literals if _INSERT_PEOPLE.search(s)]
        self.assertEqual(
            len(hits), 1,
            "expected exactly the executable SQL literal; got " + repr(hits))
        self.assertIn("VALUES (?)", hits[0])
        self.assertNotIn("_ensure", " ".join(literals))

    def test_no_unclassified_direct_insertion_exists(self):
        """The gate. A fourth insertion fails here by name."""
        found = _files_inserting_people()
        allowed = _SYNTHETIC_EXEMPT | {_PRODUCT_WRITER}
        unclassified = sorted(found - allowed)
        self.assertEqual(
            unclassified, [],
            "these files insert a `people` row directly and are not "
            "classified. A person row created outside `db.create_person()` "
            "gets no Profile Seed onboarding row and is HISTORICAL "
            "forever — silently unable to be onboarded. Either route the "
            "creation through `create_person()`, or add the file to "
            "`_SYNTHETIC_EXEMPT` with a local "
            f"{_MARKER} marker and a reason:\n  "
            + "\n  ".join(unclassified))

    def test_the_allowlist_has_not_gone_stale(self):
        """An allowlist entry for a file that no longer inserts is a
        standing permission nobody is watching."""
        found = _files_inserting_people()
        stale = sorted(_SYNTHETIC_EXEMPT - found)
        self.assertEqual(
            stale, [],
            "allowlisted files that no longer insert a people row: "
            + ", ".join(stale))

    def test_every_exempt_file_carries_the_marker_and_a_reason(self):
        for rel in sorted(_SYNTHETIC_EXEMPT):
            with self.subTest(path=rel):
                body = (_REPO_ROOT / rel).read_text(encoding="utf-8")
                self.assertIn(
                    _MARKER, body,
                    f"{rel} is allowlisted but carries no local marker, so a "
                    "reader of the file cannot tell the bypass is deliberate")
                self.assertIn(
                    "WO-LORI-PROFILE-SEED-REACHABILITY-01", body,
                    f"{rel} carries the marker with no reason attached")


class NoReusableOptOutTests(unittest.TestCase):

    def test_no_enrollment_switch_exists_anywhere(self):
        """A switch is worse than three exemptions.

        Exemptions are three named files a reviewer can read. A switch
        is reachable from anywhere, including the real intake path.
        """
        banned = {"skip_enrollment", "SKIP_ENROLLMENT", "skip_profile_seed",
                  "SKIP_PROFILE_SEED", "HORNELORE_SKIP_ENROLL", "no_enroll",
                  "skip_onboarding"}
        offenders = []
        for path in _iter_non_test_python():
            rel = path.relative_to(_REPO_ROOT).as_posix()
            # Identifiers the code USES, plus string literals it evaluates
            # (an env-var name lives in a literal). Comments and docstrings
            # are excluded — several files legitimately EXPLAIN that no
            # such switch exists, and a guard that fires on that
            # explanation is measuring the explanation.
            used = code_names(path) | set(code_string_literals(path))
            for token in sorted(banned & used):
                offenders.append(f"{rel}: {token}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_create_person_takes_no_enrollment_argument(self):
        import inspect
        from api import db as _db
        params = set(inspect.signature(_db.create_person).parameters)
        for banned in ("enroll", "skip_enrollment", "profile_seed",
                       "onboarding"):
            self.assertNotIn(banned, params)

    def test_narrator_type_is_not_an_enrollment_predicate(self):
        """Work order decision 2, checked in the source rather than
        asserted in prose.

        Read from code only — the module's own docstring is allowed to
        say that narrator type plays no part, and a guard that fired on
        that sentence would be measuring the sentence.
        """
        from api.services import profile_seed as _ps
        path = (_REPO_ROOT / "server" / "code" / "api" / "services"
                / "profile_seed.py")
        used = code_names(path) | set(code_string_literals(path))
        for token in ("narrator_type", "NARRATOR_TYPES", "live", "reference"):
            self.assertNotIn(
                token, used,
                f"the resolver uses {token!r} in executable code — narrator "
                "type is neither an activation nor a completion predicate")
        self.assertTrue(_ps.TOPIC_IDS)


class EnrollmentIsAdjacentToTheInsertTests(unittest.TestCase):

    def test_create_person_enrolls_before_it_commits(self):
        """Order in source, because the ordering IS the atomicity.

        An `enroll()` after the commit would be the "person created,
        onboarding best-effort" partial success work order 4.2 refuses,
        and it would still look correct at a glance.
        """
        body = (_REPO_ROOT / "server" / "code" / "api" / "db.py").read_text(
            encoding="utf-8")
        start = body.index("def create_person(")
        end = body.index("def profile_seed_resolve(", start)
        fn = body[start:end]

        begin_at = fn.index("BEGIN IMMEDIATE")
        insert_at = fn.index("INSERT INTO people")
        enroll_at = fn.index("_profile_seed.enroll(")
        commit_at = fn.index("con.commit()")

        self.assertLess(begin_at, insert_at,
                        "the people insert is outside the transaction")
        self.assertLess(insert_at, enroll_at)
        self.assertLess(enroll_at, commit_at,
                        "enrollment happens after the commit — the people "
                        "row would survive a failed enrollment")
        self.assertIn("con.rollback()", fn,
                      "no rollback: both rows or neither is aspirational")


class OverlayScriptRefusesToCreateTests(unittest.TestCase):
    """`scripts/set_narrator_overlay.py` is NOT harness-only.

    Its own module docstring tells the operator to run it before a live
    session, and `--person-id` accepts any UUID. It used to create the
    narrator when one was missing, which made a documented operator tool
    quietly into a narrator-creation tool — and after Phase 1 a
    mistyped UUID would have produced a real, nameless, permanently
    unonboardable narrator with one line of stdout as the only sign.
    """

    def setUp(self):
        self.path = _REPO_ROOT / "scripts" / "set_narrator_overlay.py"
        self.body = self.path.read_text(encoding="utf-8")
        self.literals = code_string_literals(self.path)
        self.names = code_names(self.path)

    def test_it_no_longer_inserts_a_people_row(self):
        hits = [s for s in self.literals if _INSERT_PEOPLE.search(s)]
        self.assertEqual(
            hits, [], "the overlay script inserts a people row again")

    def test_it_is_not_on_the_synthetic_allowlist(self):
        self.assertNotIn("scripts/set_narrator_overlay.py", _SYNTHETIC_EXEMPT)

    def test_the_creating_helper_is_gone_from_the_code(self):
        """Asserted against identifiers, not raw text.

        `_require_people_row`'s docstring deliberately NAMES the helper
        it replaced, because a reader who finds the refusal needs to
        know what used to happen and why it stopped. Deleting that
        sentence to satisfy a substring search would trade the most
        useful part of the file for a green test.
        """
        self.assertIn("_require_people_row", self.names)
        self.assertNotIn(
            "_ensure_people_row", self.names,
            "the creating helper is still defined or called")
        # ...and it IS still explained.
        self.assertIn("_ensure_people_row", self.body,
                      "the history of the removal was deleted along with it")

    def test_it_refuses_with_a_remedy_rather_than_a_traceback(self):
        self.assertIn("MissingNarrator", self.names)
        refusal = " ".join(self.literals).lower()
        self.assertIn("intake", refusal,
                      "the refusal does not tell the operator what to do "
                      "instead")

    def test_the_refusal_is_caught_and_exits_non_zero(self):
        tree = ast.parse(self.body)
        handlers = [h for h in ast.walk(tree) if isinstance(h, ast.ExceptHandler)]
        caught = [h for h in handlers
                  if isinstance(h.type, ast.Name)
                  and h.type.id == "MissingNarrator"]
        self.assertTrue(caught, "MissingNarrator is never caught")
        returns = [n.value.value for h in caught for n in ast.walk(h)
                   if isinstance(n, ast.Return)
                   and isinstance(n.value, ast.Constant)]
        self.assertIn(2, returns, "the refusal does not exit non-zero")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
