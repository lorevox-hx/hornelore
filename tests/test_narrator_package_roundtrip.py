"""WO-LOREVOX-PORTABLE-NARRATOR-01 Phase 4 — round-trip equivalence (§28.4), synthetic only.

    export A (source root) → restore into an empty destination root → export B → compare

Equivalence is SEMANTIC, never outer bytes: narrator records by stable id, every
payload file's SHA-256, counts by lane, path-column basis, dependency
declarations. `package_id`, `created_at`, ZIP order, residue, warnings and
source provenance are excluded by design — a restore deliberately does not
carry source-only residue, so A and B may differ there and still be the same
narrator.

Also proven here, because a round trip that quietly changed something ELSE
would not be a round trip:
  * a sentinel narrator already living in the destination is byte-for-byte and
    row-for-row unchanged by restoring Ada;
  * installation-owned state is unchanged except `narrator_package_jobs`, which
    is expected operational history;
  * the comparator is not vacuous: one changed database value and one changed
    payload byte, each still a perfectly valid BagIt package, are detected.

No real narrator. Christopher, Kent and Janice are Phase 6.

Run:
    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_narrator_package_roundtrip
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
import zipfile
from pathlib import Path
from typing import Dict

from tests.test_narrator_package_restore import _RoundTrip  # noqa: F401
from tests.test_narrator_package_export import REPO_ROOT  # noqa: F401
from api.services import narrator_data_inventory as inv  # noqa: E402
from api.services import narrator_package as pkg  # noqa: E402


class _Trip(_RoundTrip):
    """Destination gains a SENTINEL narrator (Cal) before Ada is restored."""

    def setUp(self):
        super().setUp()
        self.out_b = Path(self._tmp.name) / "packages_b"
        self.out_b.mkdir()
        # `self.db` was reloaded onto the destination by _RoundTrip.setUp, so this
        # creates Cal in the DESTINATION through the product's own path.
        self.cal = self.db.create_person(display_name="Cal Nwosu", testing_only=True)["id"]
        con = sqlite3.connect(str(self.dest_db))
        try:
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("INSERT INTO trips (id, person_id, title) VALUES (?, ?, ?)", (uuid.uuid4().hex, self.cal, "Cal's trip"))
            p = self.dest_root / "memory/archive/photos" / self.cal / "c0.jpg"
            p.parent.mkdir(parents=True)
            p.write_bytes(b"JPEG-CAL")
            con.execute("INSERT INTO photos (id, narrator_id, image_path, file_hash) VALUES (?, ?, ?, ?)",
                        (uuid.uuid4().hex, self.cal, str(p), "hash-cal-0"))
            con.execute("INSERT INTO sessions (conv_id, title, updated_at, person_id) VALUES ('conv-cal-1', 't', 't', ?)", (self.cal,))
            # turns.id is INTEGER PRIMARY KEY AUTOINCREMENT — the ONE narrator-owned key that is
            # not a UUID. A fresh destination would number Cal's turn 1, exactly Ada's first
            # turn id, and §10.2 would (correctly) refuse the restore. Place Cal's turn out of
            # range here; the collision itself is pinned by RestoreOnlyV1Boundary below.
            con.execute("INSERT INTO turns (id, conv_id, role, content, ts) VALUES (900001, 'conv-cal-1', 'user', 'Cal speaks.', 't')")
            con.commit()
        finally:
            con.close()

    # ── snapshots of what must NOT change ──
    def narrator_state(self, pid: str) -> Dict[str, str]:
        con = self.dest()
        out: Dict[str, str] = {}
        for table in inv.narrator_owned_tables():
            rows = con.execute(f'SELECT * FROM "{table}" WHERE {inv.owner_predicate(table)} ORDER BY 1', {"pid": pid}).fetchall()
            out[table] = json.dumps([dict(r) for r in rows], sort_keys=True, default=str)
        return out

    def installation_state(self) -> Dict[str, str]:
        con = self.dest()
        out: Dict[str, str] = {}
        for table in inv.installation_tables():
            if table == "narrator_package_jobs":
                continue
            rows = con.execute(f'SELECT * FROM "{table}" ORDER BY 1').fetchall()
            out[table] = json.dumps([dict(r) for r in rows], sort_keys=True, default=str)
        return out

    def files_under(self, pid: str) -> Dict[str, str]:
        return {str(p.relative_to(self.dest_root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.dest_root.rglob("*") if p.is_file() and pid in str(p)}

    def export_b(self, out=None):
        return pkg.export_narrator(self.ada, data_dir=self.dest_root, db_path=self.dest_db,
                                   out_dir=out or self.out_b, repo_root=REPO_ROOT)


class RoundTrip(_Trip):

    def test_export_restore_export_is_semantically_equivalent(self):
        self.assertNotEqual(str(self.root), str(self.dest_root))
        self.restore()
        b = self.export_b()
        rep = pkg.compare_packages_semantically(self.res.package_path, b.package_path)
        self.assertTrue(rep.equivalent, json.dumps(rep.differences, indent=1, default=str)[:4000])
        # the comparison was not vacuous
        self.assertGreater(rep.compared["tables"], 20)
        self.assertGreater(rep.compared["rows"], 40)
        self.assertEqual(rep.compared["files"], sum(self.res.manifest["file_counts_by_lane"].values()))
        # the two packages are NOT byte-identical — equivalence is semantic
        self.assertNotEqual(self.res.package_path.read_bytes(), b.package_path.read_bytes())
        self.assertNotEqual(self.res.manifest["package_id"], b.manifest["package_id"])

    def test_path_columns_stay_equivalent_across_different_roots(self):
        self.restore()
        b = self.export_b()
        rep = pkg.compare_packages_semantically(self.res.package_path, b.package_path)
        self.assertTrue(rep.equivalent, rep.differences[:5])
        self.assertEqual(self.res.manifest["path_column_basis"], b.manifest["path_column_basis"])
        self.assertEqual(self.res.manifest["path_column_basis"]["photos"]["image_path"], "absolute")
        # inside both packages the value is relative, and identical, though the live rows
        # point at two different absolute roots
        con = self.dest()
        live = con.execute("SELECT image_path FROM photos WHERE narrator_id=?", (self.ada,)).fetchone()[0]
        self.assertTrue(live.startswith(str(self.dest_root)))
        self.assertFalse(live.startswith(str(self.root)))

    def test_complete_travel_domain_and_references_are_equivalent(self):
        self.restore()
        b = self.export_b()
        rep = pkg.compare_packages_semantically(self.res.package_path, b.package_path)
        self.assertTrue(rep.equivalent)
        travel = [l.table for l in inv.DB_LANES if l.table.startswith("trip")]
        for t in travel:
            self.assertEqual(self.res.manifest["record_counts_by_lane"][t], b.manifest["record_counts_by_lane"][t], t)
        self.assertEqual(self.res.manifest["installation_dependencies"], b.manifest["installation_dependencies"])
        self.assertEqual(self.res.manifest["external_person_dependencies"], b.manifest["external_person_dependencies"])

    def test_sentinel_narrator_is_untouched_by_restoring_ada(self):
        rows_before = self.narrator_state(self.cal)
        files_before = self.files_under(self.cal)
        self.assertTrue(files_before, "fixture: Cal must have a file to protect")
        self.restore()
        self.assertEqual(self.narrator_state(self.cal), rows_before)
        self.assertEqual(self.files_under(self.cal), files_before)
        con = self.dest()
        self.assertEqual(con.execute("SELECT COUNT(*) FROM trips").fetchone()[0], 3)   # Cal's 1 + Ada's 2

    def test_installation_state_is_untouched_except_the_job_ledger(self):
        before = self.installation_state()
        self.restore()
        self.assertEqual(self.installation_state(), before)
        con = self.dest()
        self.assertEqual(con.execute("SELECT COUNT(*) FROM narrator_package_jobs WHERE state='complete'").fetchone()[0], 1)


class RestoreOnlyV1Boundary(_RoundTrip):
    """Found by Phase 4's first run, 2026-09-11, and pinned so nobody rediscovers it on a
    real narrator: `turns.id` is an installation-local INTEGER AUTOINCREMENT surrogate,
    preserved verbatim by Restore (§10.1). Packages from the SAME installation share one
    sequence and coexist; packages from DIFFERENT installations have no shared namespace
    and may collide even for unrelated narrators — V1 refuses (§10.2) rather than remaps
    (§10.3, deferred to its own WO). Dry run is authoritative."""

    def test_second_narrator_with_overlapping_turn_ids_is_refused_not_remapped(self):
        con = sqlite3.connect(str(self.dest_db))
        try:
            con.execute("PRAGMA foreign_keys=ON")
            cal = self.db.create_person(display_name="Cal Nwosu", testing_only=True)["id"]
            con.execute("INSERT INTO sessions (conv_id, title, updated_at, person_id) VALUES ('conv-cal-1', 't', 't', ?)", (cal,))
            con.execute("INSERT INTO turns (conv_id, role, content, ts) VALUES ('conv-cal-1', 'user', 'Cal speaks.', 't')")
            con.commit()
            cal_turn = con.execute("SELECT id FROM turns").fetchone()[0]
        finally:
            con.close()
        self.assertEqual(cal_turn, 1, "fixture: a fresh installation numbers its first turn 1")
        rep = self.dry_run()
        self.assertFalse(rep.ready)
        hits = [c for c in rep.collisions if c["kind"] == "row_id_exists" and c["table"] == "turns"]
        self.assertEqual(len(hits), 1, rep.collisions)
        self.assertEqual(hits[0]["example"], ["1"])
        with self.assertRaises(pkg.RestoreRefused):
            self.restore()
        # nothing was written, and Cal's turn is untouched
        con = self.dest()
        self.assertEqual(con.execute("SELECT content FROM turns WHERE id=1").fetchone()[0], "Cal speaks.")
        self.assertIsNone(con.execute("SELECT 1 FROM people WHERE id=?", (self.ada,)).fetchone())


class ComparatorIsNotVacuous(_Trip):
    """Both mutated packages are valid BagIt bags. Only semantics catch them."""

    def test_one_changed_database_value_is_detected(self):
        self.restore()
        con = sqlite3.connect(str(self.dest_db))
        con.execute("UPDATE trips SET title='Trip X' WHERE id=?", (self.trips[0],))
        con.commit()
        con.close()
        b = self.export_b()
        self.assertTrue(pkg.validate_package(b.package_path).ok)
        rep = pkg.compare_packages_semantically(self.res.package_path, b.package_path)
        self.assertFalse(rep.equivalent)
        hits = [d for d in rep.differences if d["kind"] == "row_differs"]
        self.assertEqual(len(hits), 1, rep.differences)
        self.assertEqual((hits[0]["table"], hits[0]["id"], hits[0]["columns"]), ("trips", self.trips[0], ["title"]))
        self.assertEqual(hits[0]["b"]["title"], "Trip X")
        self.assertEqual(len(rep.differences), 1)

    def test_one_changed_payload_byte_is_detected(self):
        self.restore()
        con = self.dest()
        live = con.execute("SELECT image_path FROM photos WHERE narrator_id=? ORDER BY id", (self.ada,)).fetchone()[0]
        p = Path(live)
        data = bytearray(p.read_bytes())
        data[0] ^= 0x01
        p.write_bytes(bytes(data))
        b = self.export_b()
        self.assertTrue(pkg.validate_package(b.package_path).ok)
        rep = pkg.compare_packages_semantically(self.res.package_path, b.package_path)
        self.assertFalse(rep.equivalent)
        hits = [d for d in rep.differences if d["kind"] == "file_hash_differs"]
        self.assertEqual(len(hits), 1, rep.differences)
        self.assertEqual(hits[0]["path"], str(p.relative_to(self.dest_root)).replace("\\", "/"))
        self.assertEqual(len(rep.differences), 1)

    def test_duplicate_id_less_row_is_a_difference_not_a_collapse(self):
        """Multiplicity: the same id-less row twice in A and once in B is a difference.
        `profiles` has no `id` column (PK `person_id`), so its rows take the whole-row
        identity. The mutated package is re-bagged with the real library so it stays a
        VALID bag — only semantics can tell the two apart."""
        import bagit  # type: ignore
        import tempfile
        self.restore()
        b = self.export_b()
        a_dup = self.out_b / "a_dup.lorevox.zip"
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            with zipfile.ZipFile(self.res.package_path) as zf:
                zf.extractall(tmp)        # our own package, in a test temp dir
            rp = tmp / "data" / "records" / "profiles.jsonl"
            lines = [l for l in rp.read_text(encoding="utf-8").splitlines() if l.strip()]
            self.assertEqual(len(lines), 1)
            self.assertNotIn("id", json.loads(lines[0]), "fixture: profiles rows must carry no `id` for this test to mean anything")
            rp.write_text(lines[0] + "\n" + lines[0] + "\n", encoding="utf-8")
            man = json.loads((tmp / pkg.MANIFEST_NAME).read_text(encoding="utf-8"))
            man["record_counts_by_lane"]["profiles"] = 2
            (tmp / pkg.MANIFEST_NAME).write_text(json.dumps(man, indent=2), encoding="utf-8")
            bagit.Bag(str(tmp)).save(manifests=True)     # regenerates manifests and Payload-Oxum
            with zipfile.ZipFile(a_dup, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for f in sorted(tmp.rglob("*")):
                    if f.is_file():
                        zf.write(f, f.relative_to(tmp).as_posix())
        self.assertTrue(pkg.validate_package(a_dup).ok, pkg.validate_package(a_dup).problems)
        rep = pkg.compare_packages_semantically(a_dup, b.package_path)
        self.assertFalse(rep.equivalent)
        extra = [d for d in rep.differences if d["kind"] == "row_only_in_a" and d["table"] == "profiles"]
        self.assertEqual(len(extra), 1, rep.differences)
        # and the manifest count difference is reported too — two independent signals
        self.assertTrue(any(d["kind"] == "manifest" and d["field"] == "record_counts_by_lane" for d in rep.differences))

    def test_an_empty_lane_and_an_absent_lane_are_the_same_narrator_state(self):
        """Phase 6 first real compare (2026-09-11): the desktop manifest carried
        `kawa_segments: 0` (lane present on that root, nothing in it) and the clean
        root's manifest omitted the lane (absent in source). Same narrator state; the
        comparator must not call that a difference. Re-bagged with the real library so
        the mutated package stays a VALID bag."""
        import bagit  # type: ignore
        import tempfile
        self.restore()
        b = self.export_b()
        a_zero = self.out_b / "a_zero.lorevox.zip"
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            with zipfile.ZipFile(self.res.package_path) as zf:
                zf.extractall(tmp)
            man = json.loads((tmp / pkg.MANIFEST_NAME).read_text(encoding="utf-8"))
            for field in ("file_counts_by_lane", "bytes_by_lane"):   # the observed case: a file lane
                self.assertNotIn("zz_lane_nobody_has", man[field])
                man[field]["zz_lane_nobody_has"] = 0
            (tmp / pkg.MANIFEST_NAME).write_text(json.dumps(man, indent=2), encoding="utf-8")
            bagit.Bag(str(tmp)).save(manifests=True)
            with zipfile.ZipFile(a_zero, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for f in sorted(tmp.rglob("*")):
                    if f.is_file():
                        zf.write(f, f.relative_to(tmp).as_posix())
        self.assertTrue(pkg.validate_package(a_zero).ok, pkg.validate_package(a_zero).problems)
        rep = pkg.compare_packages_semantically(a_zero, b.package_path)
        self.assertTrue(rep.equivalent, rep.differences)

    def test_an_invalid_package_is_a_difference_not_a_crash(self):
        bad = self.out_b / "bad.lorevox.zip"
        bad.write_bytes(b"not a zip")
        rep = pkg.compare_packages_semantically(self.res.package_path, bad)
        self.assertFalse(rep.equivalent)
        self.assertEqual(rep.differences[0]["kind"], "package_invalid")
        self.assertEqual(rep.differences[0]["package"], "B")


if __name__ == "__main__":
    import unittest
    unittest.main()
