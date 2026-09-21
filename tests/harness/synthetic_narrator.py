"""Synthetic narrators, built to order, on a database of their own.

WHY THIS EXISTS
---------------
Readiness directive §3:

    Use synthetic narrators and disposable database copies for
    development and testing. Existing family information must be
    preserved.
    …
    Do not use Janice's or Kent's actual records as experimental
    fixtures.

`verify_legacy_review_flow.py` and `verify_review_ui_contract.py` were
built the other way round: they snapshot the live database and drive
Christopher's and Kent's own queued proposals through accept, correct
and decline. Nothing reaches the real file — every write lands on a
copy — but the instruction is about what the fixtures ARE, not only
about where the bytes go. Using a family's record as a test input means
every run depends on that record continuing to look a particular way,
and it means a mistake in the harness is a mistake aimed at them.

So the shapes are reproduced from scratch here. What made those rows
useful as fixtures was never that they belonged to anyone — it was that
they were LEGACY (no id, no destination check), that some were aimed at
sections WO-04 created and some at destinations that existed all along,
that some sat at fields already holding a better answer, and that their
turn citations do not resolve. All of that is constructible.

WHAT THE SHAPES ARE, AND WHERE EACH CAME FROM
----------------------------------------------
Measured from the live queue on 2026-09-20, then reproduced with
invented values:

  29 pre-cutover rows carrying exactly five keys — fieldPath, value,
     confidence, turnId, ts — and no `suggestion_id`
  turn ids of the form `turn-<ms>`, which do not resolve to any row in
     `turns`, so `verify_turn` returns `unverified`
  12 of 29 aimed at repeatable sections
  11 at destinations the questionnaire still does not define
   9 at fields that already hold a different, better answer

A narrator built here has no family resemblance to anyone. The point is
the SHAPE.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))

# Invented people. Names chosen to be obviously fictional so a row that
# escapes into a real database is recognisable on sight.
ALDA = "p-synthetic-alda-quillfeather"
BRENNIG = "p-synthetic-brennig-oxhollow"


def legacy(field_path, value, ts=1777339161106, turn="turn-1777339141496"):
    """The pre-cutover shape: five keys, no id, no destination check.

    This is what `_is_unchecked_legacy` keys on — the ABSENCE of
    `destination_undefined` — so adding any key here changes what the
    guard sees. Do not "tidy" it.
    """
    return {"fieldPath": field_path, "value": value, "confidence": 0.9,
            "turnId": turn, "ts": ts}


def modern(field_path, value, sid="sg_synthetic00000", **kw):
    """What today's append route produces."""
    e = {"suggestion_id": sid, "fieldPath": field_path, "value": value,
         "confidence": 0.9, "origin": "extraction",
         "source_turn_id": None, "turn_evidence": "absent",
         "ts": "2026-09-20T00:00:00", "repeats": 1,
         "destination_undefined": False, "destination_unresolved": False}
    e.update(kw)
    return e


# The fixture set. Each entry names the property it exists to exercise,
# so a test can ask for a shape rather than an index.
QUEUE = [
    # ACKNOWLEDGE tier: legacy, destination existed all along, empty.
    ("ack_empty", legacy("education.gradeLevel", "4th grade")),
    # ACKNOWLEDGE tier, but the destination already holds a better
    # answer — ruling C3 refuses these before either tier is consulted.
    ("ack_occupied", legacy("education.schooling", "school")),
    # CORRECT tier: legacy, aimed at a section WO-04 created, and
    # repeatable, so it also needs an entry chosen.
    ("correct_repeatable", legacy("military.branch", "Ferrous Gate battery")),
    # CORRECT tier, flat.
    ("correct_flat", legacy("faith.denomination", "Thursday")),
    # Refused outright: the questionnaire defines no such field.
    ("undefined_dest", legacy("personal.notes", "a note with no home")),
    # Ordinary: made by today's route, nothing required.
    ("modern_clean", modern("personal.middleName", "Quill")),
]

# Answers already on record for ALDA. `education.schooling` is occupied
# ON PURPOSE, to reproduce the nine-of-nineteen conflict case.
ANSWERS = {
    "education": {
        "schooling": "Finished at Marrow Bay Comprehensive, 1974",
    },
}


def _schema(con):
    """Only the tables this harness touches, built from the real
    migrations where they exist so a column rename breaks a test rather
    than silently passing."""
    sys.path.insert(0, str(REPO / "tests"))
    from test_suggestion_flags import SCHEMA, _ddl
    con.executescript(SCHEMA)
    con.executescript(_ddl("0059_answer_provenance.sql",
                           "CREATE TABLE IF NOT EXISTS bio_builder_answer_provenance",
                           ["ALTER TABLE"]))
    con.executescript(_ddl("0060_suggestion_reviews.sql",
                           "CREATE TABLE IF NOT EXISTS suggestion_reviews"))
    con.executescript("ALTER TABLE suggestion_reviews ADD COLUMN corrected_value TEXT;")
    con.executescript("ALTER TABLE suggestion_reviews ADD COLUMN correction_reason TEXT;")
    con.executescript("ALTER TABLE suggestion_reviews ADD COLUMN accept_mode TEXT;")
    con.executescript(_ddl("0061_suggestion_flags.sql",
                           "CREATE TABLE IF NOT EXISTS suggestion_flags",
                           ["ALTER TABLE"]))


def build(dest_dir=None):
    """A fresh database with two synthetic narrators. Returns its path.

    ALDA carries the queue shapes; BRENNIG exists so a test can prove
    one narrator's information never appears in another's context.
    """
    d = Path(dest_dir or tempfile.mkdtemp(prefix="synthetic_"))
    d.mkdir(parents=True, exist_ok=True)
    path = d / "synthetic.sqlite3"
    con = sqlite3.connect(path)
    _schema(con)
    for pid, name in ((ALDA, "Alda Quillfeather"), (BRENNIG, "Brennig Oxhollow")):
        con.execute("INSERT INTO people (id, display_name) VALUES (?,?)", (pid, name))
    con.execute(
        "INSERT INTO interview_projections"
        "(person_id, projection_json, source, version, updated_at) VALUES (?,?,?,?,?)",
        (ALDA, json.dumps({"fields": {}, "pendingSuggestions": [e for _n, e in QUEUE]}),
         "synthetic", 1, "2026-09-20T00:00:00"))
    con.execute(
        "INSERT INTO bio_builder_questionnaires "
        "(person_id, questionnaire_json, revision, updated_at) VALUES (?,?,?,?)",
        (ALDA, json.dumps(ANSWERS), 1, "2026-09-20T00:00:00"))
    # BRENNIG gets a different answer at the SAME path, so a leak
    # between narrators is visible rather than inferred.
    con.execute(
        "INSERT INTO bio_builder_questionnaires "
        "(person_id, questionnaire_json, revision, updated_at) VALUES (?,?,?,?)",
        (BRENNIG, json.dumps({"education": {"schooling": "Taught at home by an aunt"}}),
         1, "2026-09-20T00:00:00"))
    con.commit()
    con.close()
    return path


def use(path):
    """Point `api.db` at this database. Returns a restore callable."""
    from api import db as _db
    real = (_db._connect, _db.init_db)

    def _c():
        c = sqlite3.connect(path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        return c

    _db._connect = _c
    _db.init_db = lambda *a, **k: None

    def _restore():
        _db._connect, _db.init_db = real

    return _restore


def entry(name):
    """One fixture by the property it exercises."""
    for n, e in QUEUE:
        if n == name:
            return json.loads(json.dumps(e))
    raise KeyError(name)
