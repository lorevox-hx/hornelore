"""WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01 — Guard Lab gate prerequisite.

`testing_only` was accepted by both narrator-creation paths and stored by
neither. It bypassed the consent gate, went into the response body, and
was dropped; `create_person()` had no such parameter and `db.py` had no
such field. After creation a testing-only narrator was DURABLY
INDISTINGUISHABLE from a real one.

That was harmless while nothing depended on it. It stops being harmless
the moment an experimental configuration — one that strips Lori's
narrator-facing interventions — is gated on "is this a test narrator?".
A flag that is not persisted cannot protect anybody.

FAIL-CLOSED IS THE WHOLE POINT of these tests. Every uncertain answer
must be False: unknown person, missing id, pre-migration row, failed
lookup. The cost of a false negative is an experiment that refuses to
apply; the cost of a false positive is a real narrator, possibly an
older adult with cognitive decline, talking to a deliberately degraded
Lori.
"""

import glob
import os
import sqlite3
import tempfile
import unittest


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MIGRATIONS_DIR = os.path.join(_REPO, "server", "code", "db", "migrations")


class ColumnOwnershipTests(unittest.TestCase):
    """One owner per people-column, and it is `init_db`.

    A migration must NOT add this column. Migration 0013's own header
    records why: an earlier version ALTERed `people` to add pronouns,
    SQLite has no "ADD COLUMN IF NOT EXISTS", and on every init_db retry
    the migration re-ran, failed with "duplicate column name", never
    marked itself complete, and knocked out every endpoint that consulted
    the schema.

    The runner is invoked FROM init_db, so the PRAGMA-guarded block
    always wins the race and a migration doing the same ALTER can only
    ever fail.
    """

    def test_no_migration_alters_people_for_this_column(self):
        offenders = []
        for path in glob.glob(os.path.join(_MIGRATIONS_DIR, "*.sql")):
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    stripped = line.strip()
                    if stripped.startswith("--"):
                        continue
                    if "ADD COLUMN testing_only" in stripped:
                        offenders.append(os.path.basename(path))
        self.assertEqual(
            offenders, [],
            f"{offenders} adds testing_only. People columns are owned by "
            f"init_db's PRAGMA-guarded block; see migration 0013's header "
            f"for the incident that established this.")

    def test_init_db_owns_the_column(self):
        with open(os.path.join(_REPO, "server", "code", "api", "db.py"),
                  encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn("ADD COLUMN testing_only", source)

    def test_no_source_comment_cites_a_migration_that_does_not_exist(self):
        """Don't leave a breadcrumb to a file nobody wrote.

        The first cut of this work DID add migration 0054, discovered it
        could never apply, and removed it — but left three comments
        saying "see migration 0054" behind. A reader following that
        reference finds nothing and has to reconstruct the reasoning
        from scratch, which is how a wrong assumption gets made twice.

        This is the general form: any `migration NNNN` reference in
        server source must name a file that is actually on disk.
        """
        import re

        existing = {
            re.match(r"(\d{4})", os.path.basename(p)).group(1)
            for p in glob.glob(os.path.join(_MIGRATIONS_DIR, "*.sql"))
            if re.match(r"\d{4}", os.path.basename(p))
        }
        pattern = re.compile(r"migration\s+(\d{4})", re.IGNORECASE)
        dangling = []
        for root, _dirs, files in os.walk(os.path.join(_REPO, "server")):
            for name in files:
                if not name.endswith((".py", ".sql")):
                    continue
                path = os.path.join(root, name)
                with open(path, encoding="utf-8", errors="replace") as fh:
                    for lineno, line in enumerate(fh, 1):
                        for number in pattern.findall(line):
                            if number not in existing:
                                dangling.append(
                                    f"{os.path.relpath(path, _REPO)}:{lineno} "
                                    f"cites migration {number}")
        self.assertEqual(dangling, [], "\n".join(dangling))


class _DbCase(unittest.TestCase):
    """Each test gets its own database file.

    ISOLATION IS LOAD-BEARING, and the first version of this got it
    wrong. `db.py` resolves `DB_PATH = Path(getenv("DATA_DIR", "data"))
    / "db" / getenv("DB_NAME", "lorevox.sqlite3")` AT IMPORT TIME, and
    it is RELATIVE to the working directory. Setting some other
    environment variable does nothing, so the suite happily created
    narrators in the developer's actual `data/db/lorevox.sqlite3` —
    which on Chris's machine holds Kent and Janice.

    So: point DATA_DIR at a temp directory, then reload the module so
    the module-level constants are recomputed, and restore both
    afterwards.
    """

    def setUp(self):
        import importlib

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._prev = {k: os.environ.get(k) for k in ("DATA_DIR", "DB_NAME")}

        os.environ["DATA_DIR"] = self._tmp.name
        os.environ["DB_NAME"] = "test_people_testing_only.sqlite3"

        from api import db as _db
        importlib.reload(_db)
        self.db = _db
        self.db.init_db()

        self.assertTrue(
            str(self.db.DB_PATH).startswith(self._tmp.name),
            f"Refusing to run against {self.db.DB_PATH} — this suite "
            f"creates narrators and must never touch a real database.")
        self.addCleanup(self._restore)

    def _restore(self):
        import importlib
        for key, value in self._prev.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        from api import db as _db
        importlib.reload(_db)


class CreationTests(_DbCase):

    def test_ordinary_narrator_is_not_testing_only(self):
        person = self.db.create_person(display_name="Walter O'Donnell")
        self.assertFalse(self.db.get_person(person["id"])["testing_only"])
        self.assertFalse(self.db.person_is_testing_only(person["id"]))

    def test_explicit_testing_narrator_persists(self):
        person = self.db.create_person(
            display_name="Synthetic Probe", testing_only=True)
        self.assertTrue(self.db.get_person(person["id"])["testing_only"])
        self.assertTrue(self.db.person_is_testing_only(person["id"]))

    def test_it_survives_reconnection(self):
        """The defect was that it did NOT survive creation at all."""
        person = self.db.create_person(
            display_name="Synthetic Probe", testing_only=True)
        pid = person["id"]

        # Reload against the SAME temp DATA_DIR — a new process would
        # see exactly this.
        import importlib
        from api import db as _db
        importlib.reload(_db)
        self.db = _db
        _db.init_db()
        self.assertTrue(str(_db.DB_PATH).startswith(self._tmp.name))
        self.assertTrue(_db.person_is_testing_only(pid))

    def test_the_flag_is_exposed_as_a_real_boolean(self):
        person = self.db.create_person(display_name="A", testing_only=True)
        value = self.db.get_person(person["id"])["testing_only"]
        self.assertIsInstance(value, bool)


class FailClosedTests(_DbCase):
    """Every uncertain answer is False."""

    def test_unknown_person_is_not_eligible(self):
        self.assertFalse(self.db.person_is_testing_only("no-such-person"))

    def test_missing_id_is_not_eligible(self):
        # `"   "[:0]` was here and is just another empty string — it
        # never exercised whitespace-only input at all.
        for value in (None, "", "   ", "\t\n"):
            with self.subTest(value=repr(value)):
                self.assertFalse(self.db.person_is_testing_only(value))

    def test_a_failing_lookup_is_not_eligible(self):
        """A read error must not be able to arm an experiment."""
        original = self.db.get_person

        def _boom(_pid):
            raise sqlite3.OperationalError("database is locked")

        self.db.get_person = _boom
        try:
            self.assertFalse(self.db.person_is_testing_only("anything"))
        finally:
            self.db.get_person = original


class ClientCannotManufactureEligibilityTests(_DbCase):
    """Eligibility is server-side person metadata, nothing else.

    It must not be derivable from anything a browser can send: not
    runtime71, not a params payload, not profile biography.
    """

    def test_it_is_a_people_column_not_profile_biography(self):
        con = sqlite3.connect(str(self.db.DB_PATH))
        try:
            people_cols = {r[1] for r in con.execute(
                "PRAGMA table_info(people)")}
            self.assertIn("testing_only", people_cols)
        finally:
            con.close()

    def test_writing_profile_json_does_not_confer_eligibility(self):
        """Actually write the key, then prove it changes nothing.

        The first version called `self.db.update_profile(...)` — which
        does not exist; the accessor is `update_profile_json()` — inside
        a bare `except Exception: pass`. So it could pass without ever
        putting `testing_only` into profile JSON, which is the entire
        property under test. A swallowed exception turns an assertion
        into a wish.
        """
        person = self.db.create_person(display_name="Real Narrator")
        pid = person["id"]

        self.db.update_profile_json(pid, {"testing_only": True}, merge=True)

        # The write really happened — otherwise the assertion below is
        # proving nothing.
        profile = self.db.get_profile(pid) or {}
        stored = profile.get("profile_json", profile)
        if isinstance(stored, str):
            import json
            stored = json.loads(stored)
        self.assertTrue(
            stored.get("testing_only"),
            "Fixture failed: testing_only was not written into profile "
            "JSON, so this test would prove nothing.")

        self.assertFalse(
            self.db.person_is_testing_only(pid),
            "Narrator biography must not be able to arm an experiment. "
            "Eligibility is people-table metadata, and profile JSON is "
            "narrator truth that reaches the memoir.")

    def test_ordinary_person_update_does_not_carry_the_flag(self):
        """A stale or hostile PATCH must not convert a real narrator.

        Read by AST rather than by importing the router. Importing it
        pulls fastapi, and CLAUDE.md records the stub-ordering artifact
        that makes that unreliable: `test_extract_claims_validators`
        installs a stub that wins whenever it loads first, so this
        passed alone and errored inside a larger run with
        "cannot import name 'Query' from 'fastapi'". The class
        declaration is what matters and the source has it.
        """
        import ast

        path = os.path.join(
            _REPO, "server", "code", "api", "routers", "people.py")
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())

        update_classes = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and "Update" in node.name
        ]
        self.assertTrue(
            update_classes,
            "No *Update model found in people.py — this guard has lost "
            "its subject and would pass vacuously.")

        for cls in update_classes:
            declared = {
                target.target.id if isinstance(target, ast.AnnAssign)
                else getattr(target.targets[0], "id", None)
                for target in cls.body
                if isinstance(target, (ast.AnnAssign, ast.Assign))
                and (isinstance(target, ast.AnnAssign)
                     or getattr(target.targets[0], "id", None))
            }
            with self.subTest(model=cls.name):
                self.assertNotIn(
                    "testing_only", declared,
                    f"{cls.name} must not be able to flip experiment "
                    f"eligibility. Converting a real narrator into an "
                    f"experiment target has to be an explicit act.")


if __name__ == "__main__":
    unittest.main()
