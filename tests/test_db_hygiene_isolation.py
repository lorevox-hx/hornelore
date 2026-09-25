"""C-4D — importing tests.test_db_connection_hygiene must not change which
`api.db` the rest of the process sees.

The defect (confirmed 2026-09-25): that suite deleted `api.db` from
sys.modules and imported a new one, leaving it installed. A suite loaded
before it kept the old module and set DB_PATH on it; product code resolving
`from .. import db` at call time (trips, trip_repository) got the new one and
looked in a different database. Reproduced by

    unittest tests.test_c1_trips_person_id_fk_migration tests.test_db_connection_hygiene

This test pins the repair at the boundary that matters — module identity and
process state — rather than through the trips suite alone.
"""
from __future__ import annotations

import importlib
import os
import shutil
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))
sys.path.insert(0, str(REPO))

HYGIENE = "tests.test_db_connection_hygiene"


class HygieneSuiteLeavesTheSharedDbAlone(unittest.TestCase):
    """Run with DATA_DIR UNSET (the usual test process)."""
    PRESET_DATA_DIR = None

    def setUp(self):
        import api.db as original
        self.original = original
        self._outer_data_dir = os.environ.get("DATA_DIR")
        if self.PRESET_DATA_DIR is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self.PRESET_DATA_DIR
        self.data_dir = os.environ.get("DATA_DIR")
        self.db_path = original.DB_PATH
        sys.modules.pop(HYGIENE, None)                 # import it fresh, as a suite loader would
        self.hygiene = importlib.import_module(HYGIENE)

    def tearDown(self):
        shutil.rmtree(self.hygiene._TMP, ignore_errors=True)
        sys.modules.pop(HYGIENE, None)
        if self._outer_data_dir is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._outer_data_dir

    def test_the_process_keeps_the_same_api_db_object(self):
        self.assertIs(sys.modules["api.db"], self.original, "sys.modules['api.db'] was replaced")
        self.assertIs(importlib.import_module("api").db, self.original,
                      "the api package's db attribute (what `from .. import db` reads) was replaced")
        alias = sys.modules.get("server.code.api.db")
        self.assertTrue(alias is None or alias is self.original, "server.code.api.db was replaced")

    def test_process_state_is_unchanged(self):
        self.assertEqual(os.environ.get("DATA_DIR"), self.data_dir, "DATA_DIR leaked")
        self.assertEqual(self.original.DB_PATH, self.db_path, "the shared DB_PATH changed")

    def test_the_hygiene_suite_still_has_its_own_isolated_db(self):
        iso = self.hygiene.db
        self.assertIsNot(iso, self.original, "the hygiene suite must test an isolated copy")
        self.assertTrue(str(iso.DB_PATH).startswith(self.hygiene._TMP),
                        f"isolated DB_PATH {iso.DB_PATH} is not under {self.hygiene._TMP}")


class HygieneSuiteRestoresAPresetDataDir(HygieneSuiteLeavesTheSharedDbAlone):
    """Run with DATA_DIR SET (an operator's shell, or another suite): the
    hygiene suite must put that exact value back, not merely remove its own."""
    PRESET_DATA_DIR = "/tmp/hornelore-preset-data-dir-sentinel"


if __name__ == "__main__":
    unittest.main()
