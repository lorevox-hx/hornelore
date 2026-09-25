"""C-4D — migration 0065 admits the `activity` event type without losing a byte.

A scratch database is built by the product's own init_db with every migration
UP TO 0064 (0065 hidden), a real Life Record is written into it through the one
writer — events of several types, participants, a place, dates, a relationship
derived from an event — and only then is 0065 applied by the real runner. The
test compares the database before and after. No persistent database is used.
"""
from __future__ import annotations

import re
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))
sys.path.insert(0, str(REPO))

from api import db as _db  # noqa: E402
from api.services.life_record import writer as W  # noqa: E402
from db import migrations_runner as R  # noqa: E402

MIG_DIR = REPO / "server" / "code" / "db" / "migrations"
M0065 = "0065_life_record_activity_event.sql"
NORA = "narrator-nora-fictional"
T0 = "2026-09-25T00:00:00Z"
OLD_TYPES = ("birth", "death", "union", "separation", "move", "education", "work", "service",
             "arrival", "loss", "milestone", "other")


def d(text, value, precision):
    return {"text": text, "value": value, "precision": precision}


class Migration0065(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        # every shipped migration except 0065
        self.pre = t / "migrations_pre"
        self.pre.mkdir()
        for f in MIG_DIR.glob("*.sql"):
            if f.name != M0065:
                shutil.copy(f, self.pre / f.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = t / "scratch.sqlite3"
        # init_db imports the runner under whichever name resolves
        # (db.migrations_runner / server.code.db.migrations_runner), so the
        # 0065-less directory is set on EVERY loaded copy, then restored.
        import importlib
        try:
            importlib.import_module("server.code.db.migrations_runner")
        except ImportError:
            pass
        runners = [m for n, m in list(sys.modules.items())
                   if n.endswith("migrations_runner") and hasattr(m, "_MIGRATIONS_DIR")]
        saved = [(m, m._MIGRATIONS_DIR) for m in runners]
        for m in runners:
            m._MIGRATIONS_DIR = self.pre
        try:
            _db.init_db()
        finally:
            for m, v in saved:
                m._MIGRATIONS_DIR = v
        con = self.con()
        con.execute("INSERT INTO people(id, display_name, created_at, updated_at) VALUES (?,?,?,?)",
                    (NORA, "Nora Whitfield", T0, T0))
        con.commit()
        con.close()
        self.populate()

    def tearDown(self):
        _db.DB_PATH = self._orig_db
        self.tmp.cleanup()

    def con(self):
        c = sqlite3.connect(str(_db.DB_PATH))
        c.execute("PRAGMA foreign_keys=ON")
        return c

    def write(self, changes):
        return W.apply_changes(NORA, None, changes, "operator:test")

    def ok(self, changes):
        r = self.write(changes)
        self.assertTrue(r.get("ok"), r)

    def ev(self, eid, etype, parts, place=None, **attrs):
        v = {"type": etype, "participants": [{"person": p, "role": r} for p, r in parts]}
        if place:
            v["place"] = place
        if attrs:
            v["attributes"] = attrs
        return {"op": "add", "path": f"events/{eid}", "value": v}

    def a(self, aid, eid, concept, value):
        return {"op": "add", "path": f"assertions/{aid}", "value": {
            "subjectType": "event", "subjectId": eid, "conceptId": concept, "value": value,
            "source": "operator", "assertedBy": "narrator", "status": "operator_entered"}}

    def populate(self):
        N = NORA
        self.ok([
            {"op": "add", "path": f"people/{N}/names/n1", "value": {"fullText": "Nora Whitfield"}},
            {"op": "add", "path": "people/p-s", "value": {}},
            {"op": "add", "path": "people/p-s/names/ns", "value": {"fullText": "Tom Whitfield"}},
            {"op": "add", "path": "places/pl-1", "value": {"label": "Minot, North Dakota"}},
            self.ev("e-birth", "birth", [(N, "subject")], place="pl-1"),
            self.a("a-birth", "e-birth", "person.birth.date", d("1939-08-30", "1939-08-30", "day")),
            {"op": "set", "path": f"people/{N}/birthEventRef", "value": "e-birth", "expectedPrevious": None},
            self.ev("e-union", "union", [(N, "partner"), ("p-s", "partner")], place="pl-1", ceremony="church"),
            self.a("a-union", "e-union", "event.union.date", d("June 1961", "1961-06", "month")),
            {"op": "add", "path": "relationships/r-u", "value": {
                "subjectPersonId": "p-s", "otherPersonId": N, "kind": "spouse_of",
                "basis": "derived_from_event", "derivedFromEventId": "e-union"}},
            self.ev("e-edu", "education", [(N, "student")]),
            self.a("a-edu", "e-edu", "event.education.period", d("1953 to 1957", "1953/1957", "year")),
            self.ev("e-work", "work", [(N, "worker")], employer="the county"),
            self.a("a-work", "e-work", "event.work.period", d("1960 to 1975", "1960/1975", "year")),
            self.ev("e-svc", "service", [(N, "member"), ("p-s", "member")]),
        ])

    def snapshot(self):
        c = self.con()
        try:
            return {
                "events": c.execute("SELECT id, narrator_id, type, place_id, attributes_json, created_at, "
                                    "updated_at FROM lr_events ORDER BY id").fetchall(),
                "participants": c.execute("SELECT * FROM lr_event_participants ORDER BY id").fetchall(),
                "assertions": c.execute("SELECT * FROM lr_assertions ORDER BY id").fetchall(),
                "relationships": c.execute("SELECT * FROM lr_relationships ORDER BY id").fetchall(),
                "columns": c.execute("PRAGMA table_info(lr_events)").fetchall(),
                "fks": c.execute("PRAGMA foreign_key_list(lr_events)").fetchall(),
                "child_fks": c.execute("PRAGMA foreign_key_list(lr_event_participants)").fetchall(),
                "indexes": sorted(r[1] for r in c.execute("PRAGMA index_list(lr_events)")),
                "sql": c.execute("SELECT sql FROM sqlite_master WHERE name='lr_events'").fetchone()[0],
            }
        finally:
            c.close()

    def migrate(self):
        c = sqlite3.connect(str(_db.DB_PATH))
        c.execute("PRAGMA foreign_keys=ON")
        try:
            return R.run_pending_migrations(c), c.execute("PRAGMA foreign_keys").fetchone()[0]
        finally:
            c.close()

    # ── the migration ────────────────────────────────────────────────────
    def test_the_populated_record_survives_unchanged(self):
        before = self.snapshot()
        self.assertEqual(len(before["events"]), 5)
        with self.assertRaises(sqlite3.IntegrityError):              # precondition: refused at 0064
            c = self.con()
            try:
                c.execute("INSERT INTO lr_events VALUES ('x', ?, 'activity', NULL, NULL, ?, ?)", (NORA, T0, T0))
            finally:
                c.close()
        applied, fk = self.migrate()
        self.assertEqual(applied, [M0065])
        self.assertEqual(fk, 1, "foreign keys are back on after the rebuild")
        after = self.snapshot()
        for k in ("events", "participants", "assertions", "relationships", "columns", "fks",
                  "child_fks", "indexes"):
            self.assertEqual(after[k], before[k], k)
        # the ONLY schema difference is `activity` in the type list. (SQLite
        # stores a table created by ALTER … RENAME with its name quoted —
        # `CREATE TABLE "lr_events"` — the one cosmetic change normalised here.)
        norm = lambda q: re.sub(r"\s+", " ", q.replace('CREATE TABLE "lr_events"', "CREATE TABLE lr_events"))
        self.assertIn("'activity'", after["sql"])
        self.assertEqual(norm(after["sql"].replace("'activity', ", "")), norm(before["sql"]))

    def test_references_resolve_and_the_database_is_clean(self):
        self.migrate()
        c = self.con()
        try:
            self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(c.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(c.execute("SELECT count(*) FROM lr_event_participants p LEFT JOIN lr_events e "
                                       "ON e.id = p.event_id WHERE e.id IS NULL").fetchone()[0], 0)
            self.assertEqual(c.execute("SELECT count(*) FROM lr_events e JOIN lr_places pl ON pl.id = e.place_id")
                             .fetchone()[0], 2)
            with self.assertRaises(sqlite3.IntegrityError):          # the child FK is still enforced
                c.execute("INSERT INTO lr_event_participants VALUES ('px', ?, 'no-such-event', ?, 'x')",
                          (NORA, NORA))
        finally:
            c.close()
        rec = W.read_record(NORA)
        self.assertEqual(next(e for e in rec["events"] if e["id"] == "e-work")["date"],
                         d("1960 to 1975", "1960/1975", "year"), "the store still reads the dates")

    def test_activity_is_admitted_every_old_type_still_works_and_bogus_is_refused(self):
        self.migrate()
        self.ok([self.ev("e-act", "activity", [(NORA, "member")], organization="the choir"),
                 self.a("a-act", "e-act", "event.activity.period", d("1970 to present", "1970/..", "unknown"))])
        self.assertEqual(next(e for e in W.read_record(NORA)["events"] if e["id"] == "e-act")["date"]["value"],
                         "1970/..")
        for i, t in enumerate(OLD_TYPES):
            if t == "death":        # a death needs the person deceased, in the same Save (model rule)
                self.ok([self.ev(f"e-{i}", t, [(NORA, "subject")]),
                         {"op": "add", "path": "assertions/a-dead", "value": {
                             "subjectType": "person", "subjectId": NORA, "conceptId": "person.life_status",
                             "value": "deceased", "source": "operator", "assertedBy": "operator",
                             "status": "operator_entered"}}])
            else:
                self.ok([self.ev(f"e-{i}", t, [(NORA, "subject")])])
        r = self.write([self.ev("e-bogus", "hobby", [(NORA, "subject")])])
        self.assertFalse(r.get("ok"), "an unknown event type is still refused")

    def test_rerunning_is_a_no_op(self):
        self.migrate()
        before = self.snapshot()
        applied, _ = self.migrate()
        self.assertEqual(applied, [])
        self.assertEqual(self.snapshot(), before)

    def test_a_fresh_database_builds_with_activity(self):
        with tempfile.TemporaryDirectory() as t:
            orig = _db.DB_PATH
            _db.DB_PATH = Path(t) / "fresh.sqlite3"
            try:
                _db.init_db()
                c = sqlite3.connect(str(_db.DB_PATH))
                try:
                    self.assertIn("'activity'", c.execute(
                        "SELECT sql FROM sqlite_master WHERE name='lr_events'").fetchone()[0])
                    self.assertIn(M0065, {r[0] for r in c.execute("SELECT filename FROM schema_migrations")})
                    self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(), [])
                finally:
                    c.close()
            finally:
                _db.DB_PATH = orig

    def test_the_file_is_runner_managed_with_the_foreign_key_directive(self):
        sql = (MIG_DIR / M0065).read_text(encoding="utf-8")
        self.assertTrue(R.wants_foreign_keys_off(sql))
        self.assertFalse(R.is_self_managed(sql), "no BEGIN/COMMIT of its own — the runner owns the transaction")


if __name__ == "__main__":
    unittest.main()
