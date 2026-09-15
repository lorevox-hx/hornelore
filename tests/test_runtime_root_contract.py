"""WO-LOREVOX-CLEAN-DATA-WORLD-01 (Phase 7) Part B — one root, or a refusal.

A reader audit on 2026-09-14 found the application resolving its data root in
at least seven independent places with three classes of disagreement, the
worst being that FOUR silently defaulted to a RELATIVE "data" while THREE
refused outright. With DATA_DIR unset the product did not fail — it
half-worked: the database landed under ./data/db/ while photos, media and
import staging refused. Two of those four also created the directory tree AT
IMPORT, so a stale or typo'd root was not an error, it was a new installation
that looked exactly like a real one.

These tests pin the contract and the two structural fixes it depends on:
nothing may invent a root, and nothing may create one as a side effect of
being imported.
"""
from __future__ import annotations

import importlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path


class _EnvCase(unittest.TestCase):
    _KEYS = ("DATA_DIR", "DB_NAME", "HORNELORE_DATA_DIR", "DB_PATH")

    def setUp(self):
        self._prev = {k: os.environ.get(k) for k in self._KEYS}
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "root"
        for key in self._KEYS:
            os.environ.pop(key, None)
        from api import runtime_root as _rr
        self.rr = _rr

    def tearDown(self):
        for key, value in self._prev.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class RootResolutionTests(_EnvCase):

    def test_unset_refuses_and_names_the_variable(self):
        with self.assertRaises(self.rr.RootContractError) as ctx:
            self.rr.runtime_root()
        self.assertIn("DATA_DIR", str(ctx.exception))

    def test_relative_root_refuses(self):
        # The exact shape of the old default. A relative root follows the
        # working directory, so two launchers resolve two installations.
        os.environ["DATA_DIR"] = "data"
        with self.assertRaises(self.rr.RootContractError) as ctx:
            self.rr.runtime_root()
        self.assertIn("relative", str(ctx.exception).lower())

    def test_there_is_no_fallback_root(self):
        # A default root is a guess about where somebody's life stories live.
        for value in ("", "   "):
            with self.subTest(value=repr(value)):
                os.environ["DATA_DIR"] = value
                with self.assertRaises(self.rr.RootContractError):
                    self.rr.runtime_root()

    def test_absolute_root_resolves_and_composes_the_db_path(self):
        os.environ["DATA_DIR"] = str(self.root)
        os.environ["DB_NAME"] = "lorevox.sqlite3"
        self.assertEqual(self.rr.runtime_root(), self.root)
        self.assertEqual(self.rr.db_path(), self.root / "db" / "lorevox.sqlite3")

    def test_resolution_is_not_cached_across_calls(self):
        os.environ["DATA_DIR"] = str(self.root)
        first = self.rr.runtime_root()
        other = self.root.parent / "other"
        os.environ["DATA_DIR"] = str(other)
        self.assertNotEqual(self.rr.runtime_root(), first)

    def test_resolving_creates_nothing(self):
        os.environ["DATA_DIR"] = str(self.root)
        self.rr.runtime_root()
        self.rr.db_path()
        self.rr.coherence_problems()
        self.assertFalse(
            self.root.exists(),
            "resolving a root brought it into existence — that is how a typo "
            "becomes a second installation")


class MixedRootRefusalTests(_EnvCase):

    def setUp(self):
        super().setUp()
        os.environ["DATA_DIR"] = str(self.root)
        (self.root / "db").mkdir(parents=True)

    def test_a_coherent_root_passes(self):
        os.environ["DB_NAME"] = "lorevox.sqlite3"
        (self.root / "db" / "lorevox.sqlite3").write_bytes(b"x" * 4096)
        self.assertEqual(self.rr.coherence_problems(), [])
        self.assertEqual(self.rr.assert_coherent_root(), self.root)

    def test_two_databases_in_one_root_refuses(self):
        # The real split: hornelore.sqlite3 (WO-11) beside lorevox.sqlite3.
        # Both NON-EMPTY on purpose — zero-byte files are exempt (see
        # test_a_zero_byte_stray_does_not_make_a_root_ambiguous), so writing
        # b"" here would make this test pass without exercising anything.
        for name in ("lorevox.sqlite3", "hornelore.sqlite3"):
            (self.root / "db" / name).write_bytes(b"x" * 4096)
        problems = self.rr.coherence_problems()
        self.assertTrue(problems)
        joined = " ".join(problems)
        self.assertIn("hornelore.sqlite3", joined)
        self.assertIn("lorevox.sqlite3", joined)
        with self.assertRaises(self.rr.RootContractError):
            self.rr.assert_coherent_root()

    def test_a_zero_byte_stray_does_not_make_a_root_ambiguous(self):
        """Found live 2026-09-15 on the production root.

        /mnt/c/hornelore_data/db/ holds the live 21 MB hornelore.sqlite3 and a
        zero-byte lorevox.sqlite3 abandoned in April. Counting the stray made
        the gate refuse the real family installation. A zero-byte file has no
        schema and no rows — it cannot be the installation anybody meant.
        """
        os.environ["DB_NAME"] = "hornelore.sqlite3"
        (self.root / "db" / "hornelore.sqlite3").write_bytes(b"x" * 4096)
        (self.root / "db" / "lorevox.sqlite3").write_bytes(b"")
        self.assertEqual(
            self.rr.coherence_problems(), [],
            "a zero-byte stray was counted as a second installation and "
            "refused a root that is not ambiguous")

    def test_db_name_selecting_a_file_that_is_not_there_refuses(self):
        # Starting would create a SECOND empty database beside a populated one.
        (self.root / "db" / "hornelore.sqlite3").write_bytes(b"x")
        os.environ["DB_NAME"] = "lorevox.sqlite3"
        problems = self.rr.coherence_problems()
        self.assertTrue(problems, "a root with one DB under a different name "
                                  "than DB_NAME selects was accepted")
        self.assertIn("hornelore.sqlite3", " ".join(problems))

    def test_legacy_root_variable_disagreeing_refuses(self):
        # hornelore-serve.py:30 PREFERS HORNELORE_DATA_DIR, so a disagreement
        # means the UI server and the API server serve different installations.
        os.environ["HORNELORE_DATA_DIR"] = str(self.root.parent / "elsewhere")
        problems = self.rr.coherence_problems()
        self.assertTrue(problems)
        self.assertIn("HORNELORE_DATA_DIR", " ".join(problems))

    def test_legacy_root_variable_agreeing_is_fine(self):
        os.environ["HORNELORE_DATA_DIR"] = str(self.root)
        self.assertEqual(self.rr.coherence_problems(), [])

    def test_an_unread_db_path_refuses(self):
        # .env.example shipped exactly this: a DB_PATH with no /db/ segment,
        # which the application never reads and tooling did.
        os.environ["DB_PATH"] = str(self.root / "hornelore.sqlite3")
        problems = self.rr.coherence_problems()
        self.assertTrue(problems)
        self.assertIn("DB_PATH", " ".join(problems))

    def test_every_problem_is_reported_not_just_the_first(self):
        os.environ["HORNELORE_DATA_DIR"] = str(self.root.parent / "elsewhere")
        os.environ["DB_PATH"] = str(self.root / "wrong.sqlite3")
        self.assertGreaterEqual(len(self.rr.coherence_problems()), 2)

    def test_the_refusal_message_names_the_conflict(self):
        os.environ["HORNELORE_DATA_DIR"] = str(self.root.parent / "elsewhere")
        with self.assertRaises(self.rr.RootContractError) as ctx:
            self.rr.assert_coherent_root()
        message = str(ctx.exception)
        self.assertIn("HORNELORE_DATA_DIR", message)
        self.assertIn(str(self.root), message)


class ImportCreatesNothingTests(_EnvCase):
    """Importing a module must not bring a data root into existence."""

    def test_importing_db_does_not_create_the_root(self):
        os.environ["DATA_DIR"] = str(self.root)
        os.environ["DB_NAME"] = "test_import_side_effect.sqlite3"
        from api import db as _db
        importlib.reload(_db)
        self.addCleanup(lambda: importlib.reload(_db))
        try:
            self.assertFalse(
                self.root.exists(),
                "importing api.db created the data root. A tool that imports "
                "this module to READ something would silently found a new "
                "installation.")
        finally:
            for key, value in self._prev.items():
                if value is not None:
                    os.environ[key] = value

    def test_the_connection_path_still_creates_what_it_needs(self):
        # Removing the import-time mkdir must not make the DB unopenable:
        # sqlite3 creates the file but never its parent directory.
        os.environ["DATA_DIR"] = str(self.root)
        os.environ["DB_NAME"] = "test_connect_creates.sqlite3"
        from api import db as _db
        importlib.reload(_db)
        self.addCleanup(lambda: importlib.reload(_db))
        self.assertTrue(str(_db.DB_PATH).startswith(str(self.root)))
        _db.init_db()
        self.assertTrue(_db.DB_PATH.is_file())
        con = sqlite3.connect(str(_db.DB_PATH))
        try:
            con.execute("SELECT 1")
        finally:
            con.close()


class SourceInvariantTests(unittest.TestCase):
    """The import-time mkdirs must not come back, and .env must not lie."""

    _REPO = Path(__file__).resolve().parent.parent

    def test_no_import_time_mkdir_of_the_data_root(self):
        offenders = []
        for rel in ("server/code/api/db.py", "server/code/api/api.py"):
            src = (self._REPO / rel).read_text(encoding="utf-8")
            # Module level = column zero. An indented mkdir is inside a
            # function, which is the durable boundary and is allowed.
            for line in src.splitlines():
                if line.startswith(("DB_DIR.mkdir", "DATA_DIR.mkdir",
                                    "MEMO_DIR.mkdir", "SESSION_FS_DIR.mkdir")):
                    offenders.append(f"{rel}: {line.strip()}")
        self.assertEqual(
            offenders, [],
            "an import-time mkdir of the data root is back: " + str(offenders))

    def test_env_example_does_not_advertise_an_unread_db_path(self):
        src = (self._REPO / ".env.example").read_text(encoding="utf-8")
        live = [ln for ln in src.splitlines()
                if ln.strip().startswith("DB_PATH=")]
        self.assertEqual(
            live, [],
            "DB_PATH is advertised in .env.example but read by nothing in the "
            "application — it points tooling at a different file from the one "
            "the server opens")

    def test_caller_exported_data_dir_survives_every_dotenv_load(self):
        """Two shells source .env with `set -a`; both must capture first.

        `set -a; source .env` re-exports every key over whatever the caller
        exported. scripts/common.sh does it before spawning the launchers, and
        launchers/hornelore_run_gpu_8000.sh does it again inside them. A
        capture in only one of the two still loses the value — this is the
        trace-flag bug (recorded at scripts/common.sh:10-20) in a variable
        where the cost is narrator data written to the wrong root.
        """
        for rel in ("scripts/common.sh",
                    "launchers/hornelore_run_gpu_8000.sh",
                    "launchers/hornelore_run_tts_8001.sh"):
            src = (self._REPO / rel).read_text(encoding="utf-8")
            dotenv = src.find("source \"$ROOT_DIR/.env\"")
            if dotenv < 0:
                dotenv = src.find("source \"$REPO_DIR/.env\"")
            # BOTH variables, because <DATA_DIR>/db/<DB_NAME> is the whole
            # address of an installation. Capturing only the directory lets a
            # caller point at a clean root and still receive .env's database
            # filename inside it — which is how a new Lorevox root comes to
            # hold a file called hornelore.sqlite3.
            for var in ("DATA_DIR_FROM_CALLER", "DB_NAME_FROM_CALLER"):
                with self.subTest(file=rel, var=var):
                    capture = src.find(var)
                    self.assertGreater(
                        capture, -1,
                        f"{rel} sources .env with `set -a` but never captures "
                        f"a caller-exported {var.split('_FROM')[0]} — the "
                        "caller's value is lost")
                    self.assertLess(
                        capture, dotenv,
                        f"{rel} captures {var.split('_FROM')[0]} AFTER loading "
                        ".env, by which point the caller's value is "
                        "indistinguishable from .env's own")

    def test_no_launcher_compiles_in_a_data_root(self):
        offenders = []
        for path in (self._REPO / "launchers").glob("*.sh"):
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "DATA_DIR" in stripped and ":-/" in stripped:
                    offenders.append(f"{path.name}: {stripped}")
        self.assertEqual(
            offenders, [],
            "a launcher supplies a fallback data root: " + str(offenders))


if __name__ == "__main__":
    unittest.main()
