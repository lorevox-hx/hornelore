"""The Life Record's key contract, on a database built by the product's own
init_db (every migration). Guards the shape the writer, the package lanes and
the merge collision hunt all depend on: every lr_* table keyed on ONE column.

Written 2026-09-24 after a draft 0063 with composite keys reached a live root
(see scripts/check_schema_drift.py for the live-database side of the check).
"""
import sqlite3
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))
sys.path.insert(0, str(REPO))

from tests.test_life_record_writer import _migrated_template  # noqa: E402

EXPECTED_KEY = {t: ["id"] for t in (
    "lr_people", "lr_names", "lr_places", "lr_events", "lr_event_participants", "lr_relationships",
    "lr_animals", "lr_stories", "lr_story_refs", "lr_sources", "lr_assertions", "lr_acceptances",
    "lr_revisions")}
EXPECTED_KEY["lr_record"] = ["narrator_id"]


class LifeRecordKeys(unittest.TestCase):
    def test_every_life_record_table_has_its_single_column_key(self):
        con = sqlite3.connect(str(_migrated_template()))
        try:
            tables = sorted(r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'lr\\_%' ESCAPE '\\'"))
            self.assertEqual(tables, sorted(EXPECTED_KEY), "the set of lr_* tables changed")
            for t in tables:
                pk = [r[1] for r in sorted(con.execute(f"PRAGMA table_info({t})"), key=lambda r: r[5]) if r[5]]
                self.assertEqual(pk, EXPECTED_KEY[t], f"{t} is keyed on {pk}")
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
