"""`.env` decides the database, not a stale shell export.

Phase 6. Pins the exact failure of 2026-09-09.

WHAT HAPPENED. `scripts/phase6_populated_narrator.py` resolved
`DATA_DIR` and `DB_NAME` by reading `.env` only for keys NOT already in
the environment, and its docstring said an exported value winning was
"the server's own precedence." That was false. `scripts/common.sh:26-29`
sources `.env` under `set -a`, which OVERWRITES an exported value — so
the server takes `.env` and the script took the shell.

A WSL profile carried stale values, and the two disagreed:

    shell env    /home/chris/lorevox_data   lorevox.sqlite3
    .env         /mnt/c/hornelore_data      hornelore.sqlite3
    api.log      /mnt/c/hornelore_data/db/hornelore.sqlite3

Ada was created in the first, which nothing serves. The script printed
PASS. `GET /api/operator/guard-lab/narrators` returned `count: 0`.

WHY THE EXISTING GUARD DID NOT CATCH IT. `--create` refuses when the
resolved database does not exist, reasoning that being about to create
one proves you are pointing where the product does not read. A stale
database was already sitting there, so the refusal passed. Existence
was never the property worth checking; agreement with `.env` is.

SCOPE. These tests pin ONLY the database-configuration precedence in
this one script. They make no claim about environment precedence
anywhere else in Hornelore, and nothing here should be read as a
general rule.

Run:

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=.:server/code .venv/bin/python -m unittest \\
        tests.test_phase6_populated_narrator_env
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Importing this module is inert: `_load_env()` is called inside main()
# and `from api import db` is deferred to the line after it, so nothing
# here binds a real DB_PATH or touches a database.
from scripts import phase6_populated_narrator as pn  # noqa: E402


LIVE_DATA_DIR = "/mnt/c/hornelore_data"
LIVE_DB_NAME = "hornelore.sqlite3"
STALE_DATA_DIR = "/home/chris/lorevox_data"
STALE_DB_NAME = "lorevox.sqlite3"


class _EnvHarness(unittest.TestCase):
    """Point the module at a temporary .env instead of the real one."""

    def _run_load_env(self, env_text, environ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            if env_text is not None:
                (root / ".env").write_text(env_text, encoding="utf-8")
            with mock.patch.object(pn, "REPO_ROOT", root), \
                    mock.patch.dict(os.environ, environ, clear=False):
                for key in ("DATA_DIR", "DB_NAME"):
                    if key not in environ:
                        os.environ.pop(key, None)
                pn._load_env()
                return dict(
                    DATA_DIR=os.environ.get("DATA_DIR"),
                    DB_NAME=os.environ.get("DB_NAME"),
                )


class DotEnvWinsOverAStaleExportTests(_EnvHarness):

    LIVE_ENV = (
        f"DATA_DIR={LIVE_DATA_DIR}\n"
        f"DB_NAME={LIVE_DB_NAME}\n"
    )

    def test_the_2026_09_09_failure_cannot_recur(self):
        """The regression. Stale exports present, .env names the live DB."""
        resolved = self._run_load_env(
            self.LIVE_ENV,
            {"DATA_DIR": STALE_DATA_DIR, "DB_NAME": STALE_DB_NAME},
        )
        self.assertEqual(
            resolved["DATA_DIR"], LIVE_DATA_DIR,
            "a stale exported DATA_DIR beat .env — this is the defect that "
            "created Ada in a database nothing serves")
        self.assertEqual(resolved["DB_NAME"], LIVE_DB_NAME)

    def test_the_override_is_announced_not_silent(self):
        """A silent correction would be as invisible as the silent failure.

        The whole reason this went unnoticed is that nothing said which
        of two disagreeing sources had won.
        """
        with mock.patch("sys.stderr") as err:
            self._run_load_env(
                self.LIVE_ENV,
                {"DATA_DIR": STALE_DATA_DIR, "DB_NAME": STALE_DB_NAME},
            )
        written = "".join(
            str(c.args[0]) for c in err.write.call_args_list if c.args)
        self.assertIn(STALE_DATA_DIR, written)
        self.assertIn(LIVE_DATA_DIR, written)

    def test_no_export_still_takes_the_env_value(self):
        resolved = self._run_load_env(self.LIVE_ENV, {})
        self.assertEqual(resolved["DATA_DIR"], LIVE_DATA_DIR)
        self.assertEqual(resolved["DB_NAME"], LIVE_DB_NAME)

    def test_agreement_produces_no_warning(self):
        """Don't cry wolf when the two sources already agree."""
        with mock.patch("sys.stderr") as err:
            resolved = self._run_load_env(
                self.LIVE_ENV,
                {"DATA_DIR": LIVE_DATA_DIR, "DB_NAME": LIVE_DB_NAME},
            )
        written = "".join(
            str(c.args[0]) for c in err.write.call_args_list if c.args)
        self.assertEqual(resolved["DATA_DIR"], LIVE_DATA_DIR)
        self.assertNotIn("overrides", written)

    def test_a_missing_env_leaves_the_environment_alone(self):
        """No .env is not an invitation to invent a destination."""
        resolved = self._run_load_env(
            None, {"DATA_DIR": STALE_DATA_DIR, "DB_NAME": STALE_DB_NAME})
        self.assertEqual(resolved["DATA_DIR"], STALE_DATA_DIR)
        self.assertEqual(resolved["DB_NAME"], STALE_DB_NAME)

    def test_only_these_two_keys_are_touched(self):
        """Scope guard: this fix is about the database, nothing else.

        If a future edit broadens this into general .env precedence, an
        unrelated exported value would start being overwritten and this
        test says so.
        """
        env_text = self.LIVE_ENV + "HORNELORE_OPERATOR_GUARD_LAB=1\n"
        with mock.patch.dict(
            os.environ, {"HORNELORE_OPERATOR_GUARD_LAB": "0"}, clear=False
        ):
            self._run_load_env(env_text, {"DATA_DIR": STALE_DATA_DIR})
            self.assertEqual(
                os.environ.get("HORNELORE_OPERATOR_GUARD_LAB"), "0",
                "_load_env reached beyond DATA_DIR/DB_NAME")


class TheServerPrecedenceClaimMatchesCommonShTests(unittest.TestCase):
    """The false docstring is what made the failure look impossible.

    A comment cannot fail, so this asserts the actual shell behaviour the
    docstring now cites, against the shipped file.
    """

    def test_common_sh_sources_env_under_set_a(self):
        common = REPO_ROOT / "scripts" / "common.sh"
        self.assertTrue(common.is_file(), f"missing {common}")
        body = common.read_text(encoding="utf-8", errors="replace")
        self.assertIn("set -a", body)
        self.assertIn('source "$ROOT_DIR/.env"', body)


if __name__ == "__main__":
    unittest.main()
