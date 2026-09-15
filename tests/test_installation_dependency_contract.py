"""The shared installation-dependency helper must honour its own signature.

WO-LOREVOX-MULTI-ORIGIN-MERGE-REMAP-01, executor block. One focused regression.

`narrator_package.missing_installation_dependencies` is shared by restore's dry run and
by Merge/Remap's target verification, and it advertises a plain `sqlite3.Connection`.
Until 2026-09-14 three helpers beneath it read `PRAGMA` output by column name directly,
which silently required `row_factory = sqlite3.Row`. Restore's dry run happens to set it.
The first REAL Christopher merge rehearsal did not, and it raised

    TypeError: tuple indices must be integers or slices, not str

from four frames below the call — after ninety-five synthetic tests had passed, because
every one of them reached the helper through a caller that had already set the factory.

That is a contract defect, not a caller mistake, so this test calls the public helper
the way its signature says it may be called.

Run:
    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest \\
        tests.test_installation_dependency_contract
"""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "server" / "code"))

from api.services import narrator_package as pkg  # noqa: E402


def _schema(con: sqlite3.Connection) -> None:
    """The shape that made this matter: the ids a package declares name a REFERENCED
    column that is not the primary key — `bio_facts.field_key` → `bio_fields.field_key`,
    while `bio_fields.id` is a UUID. Resolving them needs the FK graph, which is what
    reads PRAGMA output."""
    con.executescript(
        """
        CREATE TABLE bio_fields (
            id         TEXT PRIMARY KEY,
            field_key  TEXT NOT NULL UNIQUE
        );
        CREATE TABLE bio_facts (
            id         TEXT PRIMARY KEY,
            field_key  TEXT NOT NULL REFERENCES bio_fields(field_key)
        );
        INSERT INTO bio_fields (id, field_key) VALUES
            ('8f14e45fceea167a5a36dedd4bea2543', 'birth_date');
        """
    )


class TheHelperAcceptsTheConnectionItAdvertises(unittest.TestCase):

    def test_it_works_with_a_default_connection_and_with_sqlite3_Row(self):
        """Both row factories, same answers — the default one is the regression.

        Asserted on the ANSWER, not merely on "it did not raise": a helper that returned
        an empty list for every input would also not raise, and would report every clean
        installation as ready for a package it cannot actually satisfy.
        """
        for factory in (None, sqlite3.Row):
            with self.subTest(row_factory=getattr(factory, "__name__", "default")):
                con = sqlite3.connect(":memory:")
                con.row_factory = factory
                self.addCleanup(con.close)
                _schema(con)

                # the seeded dependency resolves through the REFERENCED column
                self.assertEqual(
                    pkg.missing_installation_dependencies(
                        con, {"bio_fields": ["birth_date"]}),
                    [])

                # an absent one is named, by the value the package declared
                missing = pkg.missing_installation_dependencies(
                    con, {"bio_fields": ["birth_date", "place_of_birth"]})
                self.assertEqual([m["table"] for m in missing], ["bio_fields"])
                self.assertEqual(missing[0]["ids"], ["place_of_birth"])

                # a table the destination does not have at all
                absent = pkg.missing_installation_dependencies(
                    con, {"interview_plans": ["chat_ws"]})
                self.assertEqual([m["table"] for m in absent], ["interview_plans"])
                self.assertIn("absent", absent[0]["detail"])

                # and the PK fallback, which `_dependency_key_columns` reaches when
                # nothing references the parent — `_pk_columns` carried the same latent
                # defect and is only reachable on this branch
                self.assertEqual(
                    pkg.missing_installation_dependencies(
                        con, {"bio_facts": ['8f14e45fceea167a5a36dedd4bea2543']}),
                    [{"table": "bio_facts",
                      "ids": ['8f14e45fceea167a5a36dedd4bea2543'],
                      "detail": "installation-owned rows this narrator references; "
                                "create them here first"}])


if __name__ == "__main__":
    unittest.main()
