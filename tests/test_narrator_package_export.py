"""WO-LOREVOX-PORTABLE-NARRATOR-01 Phase 2 — Package v1 exporter, proven on synthetic Ada.

THE INVARIANT UNDER TEST (WO §30): given ONE selected narrator id, the exporter
follows `narrator_data_inventory.py` and packages that narrator's complete
portable state — the complete travel domain when present — and NOTHING of any
other narrator's. No test here knows a real narrator; every count is measured
from the rows this suite seeds, never typed in from a real machine's audit.

The fixture is two synthetic narrators in one temp DATA_DIR built by the real
`init_db()` + migrations:

  ADA   — the narrator being exported. Conversations with saved audio, photos,
          two trips with the whole hierarchy (regions, stops, days, themes,
          notes, public context, photo links / context / day placements and a
          skip, turn links into her conversation, bio suggestions, story links),
          two trip source documents with files on disk, an import batch with
          one pending candidate (staged original on disk) and one accepted, a
          media-archive item tagged with the OTHER narrator (§13), family
          truth, graph, story candidates, a timeline event, an interview
          session with a thread.
  BEA   — a second narrator with her own trip, photo and session. Her ids must
          appear NOWHERE in Ada's package.

Rows are inserted with a generic filler that satisfies NOT NULL columns from
`PRAGMA table_info`, so the fixture cannot drift from the schema silently — an
unknown NOT NULL column fails at insert, with its name.

Refusals proven: dangling trip_turn_links.conv_id · missing trip_sources file ·
credential-shaped value · narrator files changing during collection · package
written into DATA_DIR · unknown narrator. Each is asserted by the reason code
the exporter names, through the real `export_narrator()`.

Run:
    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_narrator_package_export
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_CODE = REPO_ROOT / "server" / "code"
if str(SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(SERVER_CODE))

from api.services import narrator_data_inventory as inv  # noqa: E402
from api.services import narrator_package as pkg  # noqa: E402

try:
    import bagit  # noqa: F401
    _BAGIT = True
except ImportError:  # the suite must not pass vacuously without the library
    _BAGIT = False

T = "2026-09-10T12:00:00Z"

# Values for CHECK-constrained columns the generic filler cannot guess.
_ENUM_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "trip_stops": {"stop_type": "sight"},
    "trip_photo_links": {"assignment_method": "manual"},
    "trip_location_notes": {"source_type": "operator"},
    "trip_bio_suggestions": {"status": "suggested"},
    "trip_story_links": {"status": "suggested"},
    "trip_photo_context": {"context_type": "operator_photo_context"},
    "trip_public_context": {"source_type": None},
    "trip_sources": {"source_type": "ticket"},
    "trips": {"status": "draft"},
    "photos": {"date_precision": "unknown", "location_source": "unknown"},
    "photo_people": {"confidence": "high"},
    "photo_events": {"confidence": "high"},
    "import_batch": {"source": "google_photos_picker", "status": "open"},
    "import_candidate": {"state": "pending", "taken_at_source": "unknown", "location_source": "unknown"},
    "media_archive_items": {"document_type": "letter", "text_status": "not_started",
                            "transcription_status": "not_started", "extraction_status": "none",
                            "date_precision": "unknown"},
    "memory_archive_turns": {"role": "narrator"},
}


def _uid() -> str:
    return uuid.uuid4().hex


class _Fixture(unittest.TestCase):
    """Own DATA_DIR per test, built by the product's own init_db()."""

    def setUp(self):
        if not _BAGIT:
            self.fail("bagit is not importable in this interpreter — pin bagit==1.8.1 "
                      "(requirements-test.txt). This suite REFUSES to run without the "
                      "library the package format is defined by.")
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "data"
        self.root.mkdir()
        self.out = Path(self._tmp.name) / "packages"
        self.out.mkdir()
        self._prev = {k: os.environ.get(k) for k in ("DATA_DIR", "DB_NAME")}
        os.environ["DATA_DIR"] = str(self.root)
        os.environ["DB_NAME"] = "test_package.sqlite3"
        from api import db as _db
        importlib.reload(_db)
        self.db = _db
        self.db.init_db()
        self.assertTrue(str(self.db.DB_PATH).startswith(str(self.root)),
                        f"REFUSING: DB_PATH {self.db.DB_PATH} is not under the temp root")
        self.db_path = Path(self.db.DB_PATH)
        self.addCleanup(self._restore)
        self.con = self.db._connect()
        self.addCleanup(self.con.close)
        self._seed()

    def _restore(self):
        for k, v in self._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        from api import db as _db
        importlib.reload(_db)

    # ── generic row insert: NOT NULL columns filled from the live schema ──
    def ins(self, table: str, **values) -> str:
        info = self.con.execute(f'PRAGMA table_info("{table}")').fetchall()
        if not info:
            self.fail(f"FIXTURE: table {table!r} does not exist in the schema init_db() built")
        live_cols = {c["name"] for c in info}
        unknown = sorted(set(values) - live_cols)
        if unknown:
            self.fail(f"FIXTURE: {table} has no column(s) {unknown}; live columns are {sorted(live_cols)}")
        # explicit FK values must name a row that exists, or the message is just
        # 'FOREIGN KEY constraint failed' with no table in it
        for fk in self.con.execute(f'PRAGMA foreign_key_list("{table}")'):
            col, parent, pcol = fk["from"], fk["table"], fk["to"] or "id"
            v = values.get(col)
            if v in (None, ""):
                continue
            hit = self.con.execute(f'SELECT 1 FROM "{parent}" WHERE "{pcol}" = ?', (v,)).fetchone()
            if hit is None:
                self.fail(f"FIXTURE: {table}.{col}={v!r} names no row in {parent}.{pcol}")
        row: Dict[str, Any] = dict(_ENUM_DEFAULTS.get(table, {}))
        for c in info:
            name, ctype, notnull, dflt, pk = c["name"], (c["type"] or "").upper(), c["notnull"], c["dflt_value"], c["pk"]
            if name in values:
                continue
            if name in row:
                continue
            if pk and "INT" in ctype:
                continue  # autoincrement
            if pk:
                # SQLite reports notnull=0 for a TEXT PRIMARY KEY and will happily
                # store NULL there; the product never does. Always mint an id.
                row[name] = _uid()
                continue
            if notnull and dflt is None:
                if name == "id":
                    row[name] = _uid()
                elif name.endswith("_at") or name in ("ts", "date"):
                    row[name] = T if name != "date" else "2026-06-01"
                elif "INT" in ctype:
                    row[name] = 0
                elif "REAL" in ctype:
                    row[name] = 0.0
                else:
                    row[name] = f"{table}.{name}"
        row.update(values)
        row = {k: v for k, v in row.items() if v is not None or k in values}
        cols = ", ".join(f'"{k}"' for k in row)
        qs = ", ".join("?" for _ in row)
        self.con.execute(f'INSERT INTO "{table}" ({cols}) VALUES ({qs})', tuple(row.values()))
        return row.get("id") or row.get("conv_id") or ""

    def file(self, rel: str, content: bytes = b"x") -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        return p

    # ── the two narrators ──
    def _seed(self):
        c = self.con
        self.ada = self.db.create_person(display_name="Ada Pruitt", testing_only=True)["id"]
        self.bea = self.db.create_person(display_name="Bea Okafor", testing_only=True)["id"]
        A, B = self.ada, self.bea
        self.ids: Dict[str, List[str]] = {}

        def keep(table, rid):
            self.ids.setdefault(table, []).append(rid)
            return rid

        # conversations + turns (owned), and Bea's
        self.conv = keep("sessions", self.ins("sessions", conv_id="conv-ada-1", title="Rome", updated_at=T, person_id=A))
        self.ins("sessions", conv_id="conv-ada-2", title="Kyoto", updated_at=T, person_id=A)
        self.ids["sessions"].append("conv-ada-2")
        for conv in ("conv-ada-1", "conv-ada-2"):
            for role, text in (("user", "We took the night train to Rome."), ("assistant", "What do you remember of the station?")):
                self.ins("turns", conv_id=conv, role=role, content=text, ts=T)
        self.turn_ids = [r[0] for r in c.execute("SELECT id FROM turns WHERE conv_id LIKE 'conv-ada-%' ORDER BY id")]
        self.ins("sessions", conv_id="conv-bea-1", title="Bea", updated_at=T, person_id=B)
        self.ins("turns", conv_id="conv-bea-1", role="user", content="Bea's words.", ts=T)
        # an unowned session — §6 residue, must stay behind and be reported
        self.ins("sessions", conv_id="conv-nobody", title="legacy", updated_at=T)

        # memory archive with saved narrator audio
        mas = keep("memory_archive_sessions", self.ins(
            "memory_archive_sessions", person_id=A, conv_id="conv-ada-1",
            archive_dir=f"memory/archive/people/{A}/sessions/conv-ada-1", audio_enabled=1))
        keep("memory_archive_turns", self.ins("memory_archive_turns", person_id=A, conv_id="conv-ada-1", seq=1,
                                              role="narrator", content="We took the night train.",
                                              audio_ref="audio/t1.webm", ts=T))
        self.file(f"memory/archive/people/{A}/sessions/conv-ada-1/transcript.jsonl", b'{"seq":1}\n')
        self.file(f"memory/archive/people/{A}/sessions/conv-ada-1/audio/t1.webm", b"WEBM-ADA")
        self.file(f"memory/archive/people/{B}/sessions/conv-bea-1/audio/t9.webm", b"WEBM-BEA")

        # photos — ABSOLUTE image_path like the real rows (R3), files on disk
        self.photos = []
        for i in range(3):
            p = self.file(f"memory/archive/photos/{A}/p{i}.jpg", f"JPEG-ADA-{i}".encode())
            th = self.file(f"memory/archive/photos/{A}/thumbs/p{i}.jpg", f"TH-{i}".encode())
            self.photos.append(keep("photos", self.ins(
                "photos", narrator_id=A, image_path=str(p), thumbnail_path=str(th),
                file_hash=f"hash-ada-{i}")))
        bp = self.file(f"memory/archive/photos/{B}/b0.jpg", b"JPEG-BEA")
        self.bea_photo = self.ins("photos", narrator_id=B, image_path=str(bp), file_hash="hash-bea-0")
        keep("photo_people", self.ins("photo_people", photo_id=self.photos[0], person_id=A, person_label="Ada",
                                      source_type="operator", source_authority="operator"))

        # ── the travel domain, complete ──
        self.trips = []
        for t in range(2):
            trip = keep("trips", self.ins("trips", person_id=A, title=f"Trip {t}"))
            self.trips.append(trip)
            region = keep("trip_regions", self.ins("trip_regions", trip_id=trip, title="Lazio"))
            stop = keep("trip_stops", self.ins("trip_stops", trip_id=trip, trip_region_id=region, location_name="Roma Termini"))
            day = keep("trip_days", self.ins("trip_days", trip_id=trip, day_index=1, date="2026-06-01"))
            keep("trip_themes", self.ins("trip_themes", trip_id=trip, title="Trains", tag=f"trains-{t}"))
            keep("trip_location_notes", self.ins("trip_location_notes", trip_id=trip, trip_stop_id=stop,
                                                  note_title="Termini", note_text="Platform twelve, night train."))
            keep("trip_public_context", self.ins("trip_public_context", trip_id=trip, result_summary="Festa della Repubblica"))
            link = keep("trip_photo_links", self.ins("trip_photo_links", trip_id=trip, trip_stop_id=stop,
                                                      photo_id=self.photos[t], trip_day_id=day))
            keep("trip_photo_context", self.ins("trip_photo_context", trip_id=trip, photo_link_id=link,
                                                 photo_id=self.photos[t], result_summary="platform sign"))
            keep("trip_photo_day_placements", self.ins("trip_photo_day_placements", photo_link_id=link, trip_day_id=day))
            keep("trip_photo_day_placement_skips", self.ins("trip_photo_day_placement_skips", photo_link_id=link,
                                                             trip_id=trip, reason="legacy_day_missing", detected_at=T))
            # one persisted assistant turn links ONCE (0039:161 UNIQUE) — each trip
            # anchors to its own conversation's user/assistant pair
            keep("trip_turn_links", self.ins("trip_turn_links", trip_id=trip, trip_day_id=day,
                                              conv_id=f"conv-ada-{t + 1}",
                                              user_turn_row_id=self.turn_ids[2 * t],
                                              assistant_turn_row_id=self.turn_ids[2 * t + 1]))
            keep("trip_bio_suggestions", self.ins("trip_bio_suggestions", trip_id=trip, person_id=A,
                                                  field_key="residence", suggested_value="Rome"))
            src = keep("trip_sources", self.ins("trip_sources", trip_id=trip, title="Ticket",
                                                 storage_path=f"trip_sources/SRC{t}/ticket.pdf"))
            # trip_sources dir is keyed by the SOURCE ROW id — use it as the segment
            c.execute("UPDATE trip_sources SET storage_path=? WHERE id=?", (f"trip_sources/{src}/ticket.pdf", src))
            self.file(f"trip_sources/{src}/ticket.pdf", f"%PDF-ADA-{t}".encode())
        sc = keep("story_candidates", self.ins("story_candidates", narrator_id=A,
                                               transcript="The night train to Rome.", trigger_reason="manual"))
        keep("trip_story_links", self.ins("trip_story_links", trip_id=self.trips[0], story_candidate_id=sc))
        # Bea's own trip + source file, and an orphan source dir nobody references
        btrip = self.ins("trips", person_id=B, title="Bea's trip")
        bsrc = self.ins("trip_sources", trip_id=btrip, title="B ticket", storage_path="x")
        c.execute("UPDATE trip_sources SET storage_path=? WHERE id=?", (f"trip_sources/{bsrc}/b.pdf", bsrc))
        self.file(f"trip_sources/{bsrc}/b.pdf", b"%PDF-BEA")
        self.file("trip_sources/orphan-dir-0000/stray.pdf", b"%PDF-ORPHAN")

        # import provenance: one pending candidate with staged original, one accepted
        batch = keep("import_batch", self.ins("import_batch", person_id=A))
        pending = keep("import_candidate", self.ins("import_candidate", batch_id=batch, person_id=A, state="pending"))
        accepted = keep("import_candidate", self.ins("import_candidate", batch_id=batch, person_id=A,
                                                     state="accepted", photo_id=self.photos[2]))
        self.file(f"import_staging/{batch}/{pending}/original.jpg", b"STAGED-PENDING")
        self.file(f"import_staging/{batch}/{accepted}/original.jpg", b"STAGED-ACCEPTED")
        self.file(f"import_staging/.incoming/{batch}/partial.bin", b"INCOMING")
        self.batch, self.pending, self.accepted = batch, pending, accepted

        # media archive item owned by Ada, tagged with Bea (§13 external dependency)
        item = keep("media_archive_items", self.ins(
            "media_archive_items", person_id=A, title="Letter", original_filename="l.pdf", mime_type="application/pdf",
            storage_path=f"media/archive/people/{A}/letter.pdf"))
        self.file(f"media/archive/people/{A}/letter.pdf", b"%PDF-LETTER")
        keep("media_archive_people", self.ins("media_archive_people", archive_item_id=item, person_id=B, person_label="Bea"))
        keep("media_archive_links", self.ins("media_archive_links", archive_item_id=item, link_type="timeline_year", link_target="1962"))

        # structured memory, interview
        keep("family_truth_rows", self.ins("family_truth_rows", person_id=A))
        keep("graph_persons", self.ins("graph_persons", narrator_id=A))
        keep("timeline_events", self.ins("timeline_events", person_id=A))
        plan = self.ins("interview_plans", title="plan")
        isess = keep("interview_sessions", self.ins("interview_sessions", person_id=A, plan_id=plan))
        keep("interview_threads", self.ins("interview_threads", session_id=isess, thread_anchor="the train"))
        self.ins("interview_sessions", person_id=B, plan_id=plan)
        c.commit()

    # ── helpers over a built package ──
    def export(self, **kw):
        return pkg.export_narrator(self.ada, data_dir=self.root, db_path=self.db_path, out_dir=self.out,
                                   repo_root=REPO_ROOT, **kw)

    def open_pkg(self, res):
        zf = zipfile.ZipFile(res.package_path)
        self.addCleanup(zf.close)
        return zf

    def records(self, zf, table) -> List[Dict[str, Any]]:
        name = f"data/records/{table}.jsonl"
        if name not in zf.namelist():
            return []
        return [json.loads(l) for l in zf.read(name).decode("utf-8").splitlines() if l.strip()]


# ══════════════════════════════════════════════════════════════════════

class ExportCarriesTheWholeNarrator(_Fixture):

    def test_package_is_valid_bagit_and_manifest_consistent(self):
        res = self.export()
        self.assertTrue(res.package_path.name.endswith(".lorevox.zip"))
        rep = pkg.validate_package(res.package_path)
        self.assertTrue(rep.ok, rep.problems)
        zf = self.open_pkg(res)
        names = set(zf.namelist())
        for required in ("bagit.txt", "bag-info.txt", "manifest-sha256.txt", "tagmanifest-sha256.txt", pkg.MANIFEST_NAME):
            self.assertIn(required, names)
        self.assertTrue(any(n.startswith("data/records/") for n in names))
        self.assertTrue(any(n.startswith("data/files/") for n in names))
        # every payload file is hashed in manifest-sha256.txt
        hashed = {l.split(maxsplit=1)[1] for l in zf.read("manifest-sha256.txt").decode().splitlines() if l.strip()}
        payload = {n for n in names if n.startswith("data/")}
        self.assertEqual(payload, hashed)

    def test_every_seeded_row_of_ada_travels_and_none_of_bea(self):
        res = self.export()
        zf = self.open_pkg(res)
        for table, seeded in self.ids.items():
            got = self.records(zf, table)
            got_ids = {str(r.get("id") or r.get("conv_id")) for r in got}
            missing = set(seeded) - got_ids
            self.assertEqual(missing, set(), f"{table}: Ada's rows missing from the package: {missing}")
        # Bea: nothing of hers appears in ANY record file...
        all_text = b"".join(zf.read(n) for n in zf.namelist() if n.startswith("data/records/")).decode("utf-8")
        for bad in ("conv-bea-1", self.bea_photo, "Bea's trip", "Bea's words", "conv-nobody"):
            self.assertNotIn(bad, all_text, f"{bad!r} leaked into Ada's package")
        # ...and her id appears ONLY in the one declared external-person column (§13),
        # recorded as a dependency, never pulled
        without_tags = b"".join(zf.read(n) for n in zf.namelist()
                                if n.startswith("data/records/") and not n.endswith("media_archive_people.jsonl")).decode("utf-8")
        self.assertNotIn(self.bea, without_tags, "Bea's id leaked outside the declared external-person column")
        tags = self.records(zf, "media_archive_people")
        self.assertEqual([t["person_id"] for t in tags], [self.bea])
        deps = res.manifest["external_person_dependencies"]
        self.assertEqual([d["person_id"] for d in deps["media_archive_people"]], [self.bea])
        self.assertEqual(self.records(zf, "people")[0]["id"], self.ada)
        self.assertEqual(len(self.records(zf, "people")), 1)

    def test_complete_travel_domain_is_carried_generically(self):
        res = self.export()
        counts = res.manifest["record_counts_by_lane"]
        travel = [l.table for l in inv.DB_LANES if l.table.startswith("trip")]
        self.assertEqual(len(travel), 15, travel)
        for table in travel:
            self.assertEqual(counts.get(table), len(self.ids.get(table, [])),
                             f"{table}: package has {counts.get(table)} rows, fixture seeded {len(self.ids.get(table, []))}")
        # both trip_sources files travel; Bea's and the orphan directory do not
        zf = self.open_pkg(res)
        files = [n for n in zf.namelist() if n.startswith("data/files/trip_sources/")]
        self.assertEqual(len(files), 2, files)
        self.assertFalse(any("orphan-dir-0000" in n for n in files))
        self.assertEqual(res.manifest["file_counts_by_lane"]["trip_sources"], 2)
        # turn links point at turns that ARE in the package
        turn_ids = {r["id"] for r in self.records(zf, "turns")}
        for l in self.records(zf, "trip_turn_links"):
            self.assertIn(l["assistant_turn_row_id"], turn_ids)
            self.assertIn(l["conv_id"], {r["conv_id"] for r in self.records(zf, "sessions")})

    def test_paths_are_rewritten_to_data_dir_relative_and_files_exist_in_package(self):
        res = self.export()
        zf = self.open_pkg(res)
        for p in self.records(zf, "photos"):
            self.assertFalse(Path(p["image_path"]).is_absolute(), p["image_path"])
            self.assertTrue(p["image_path"].startswith("memory/archive/photos/"), p["image_path"])
            self.assertIn("data/files/" + p["image_path"], zf.namelist())
            self.assertIn("data/files/" + p["thumbnail_path"], zf.namelist())
        self.assertEqual(res.manifest["path_basis"], "DATA_DIR-relative")
        # saved narrator audio rides the memory_archive lane (§9)
        self.assertIn(f"data/files/memory/archive/people/{self.ada}/sessions/conv-ada-1/audio/t1.webm", zf.namelist())
        self.assertNotIn(f"data/files/memory/archive/people/{self.bea}/sessions/conv-bea-1/audio/t9.webm", zf.namelist())

    def test_import_staging_is_conditional_and_incoming_never_travels(self):
        res = self.export()
        zf = self.open_pkg(res)
        names = zf.namelist()
        self.assertIn(f"data/files/import_staging/{self.batch}/{self.pending}/original.jpg", names)
        self.assertNotIn(f"data/files/import_staging/{self.batch}/{self.accepted}/original.jpg", names)
        self.assertFalse(any("/.incoming/" in n for n in names))
        # and the non-travelling bytes are REPORTED as residue, honestly
        residue = res.manifest["residue_not_packaged"]
        self.assertTrue(any(r["lane"] == "import_staging" for r in residue), residue)
        self.assertTrue(any(r["lane"] == "import_staging_incoming" for r in residue), residue)
        self.assertTrue(any(r["lane"] == "sessions" and r["rows_with_no_owner_on_source"] == 1 for r in residue), residue)

    def test_manifest_records_provenance_and_installation_dependencies(self):
        res = self.export()
        m = res.manifest
        self.assertEqual(m["narrator_id"], self.ada)
        self.assertEqual(m["package_kind"], pkg.PACKAGE_KIND)
        self.assertTrue(m["source_schema_migrations"])
        self.assertRegex(m["source_schema_fingerprint"], r"^[0-9a-f]{16}$")
        self.assertIn("interview_plans", m["installation_dependencies"])
        self.assertEqual(m["ownership_declaration"], "api.services.narrator_data_inventory")
        # ids and current values preserved verbatim (§10.1)
        zf = self.open_pkg(res)
        trips = {r["id"]: r for r in self.records(zf, "trips")}
        self.assertEqual(set(trips), set(self.trips))
        self.assertEqual(trips[self.trips[0]]["title"], "Trip 0")

    def test_export_is_read_only_against_the_source(self):
        def listing():
            # SQLite's own -wal / -shm sidecars come and go with connections; they are not data
            return sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")
                          if p.is_file() and not p.name.endswith(("-wal", "-shm", "-journal")))
        before = self.db_path.read_bytes()
        files_before = listing()
        self.export()
        self.assertEqual(self.db_path.read_bytes(), before, "the source database changed during export")
        files_after = listing()
        self.assertEqual(files_before, files_after, "the source data root changed during export")


# ══════════════════════════════════════════════════════════════════════

class ExportRefusesRatherThanDangles(_Fixture):

    def _refused(self, code, **kw) -> Dict[str, Any]:
        with self.assertRaises(pkg.ExportRefused) as cm:
            self.export(**kw)
        reasons = [r for r in cm.exception.reasons if r["code"] == code]
        self.assertTrue(reasons, f"expected refusal {code!r}, got {[r['code'] for r in cm.exception.reasons]}")
        self.assertEqual(list(self.out.glob("*.lorevox.zip")), [], "a refused export left a package behind")
        return reasons[0]

    def test_turn_link_to_an_omitted_conversation_refuses_and_names_the_row(self):
        # the conversation exists but is not Ada's — the package would omit it
        self.con.execute("UPDATE trip_turn_links SET conv_id='conv-bea-1' WHERE trip_id=?", (self.trips[0],))
        self.con.commit()
        r = self._refused("unresolved_reference")
        self.assertEqual((r["table"], r["column"], r["parent"]), ("trip_turn_links", "conv_id", "sessions"))
        self.assertEqual(r["value"], "conv-bea-1")

    def test_turn_link_to_a_turn_that_does_not_exist_refuses(self):
        self.con.execute("UPDATE trip_turn_links SET assistant_turn_row_id=999999 WHERE trip_id=?", (self.trips[1],))
        self.con.commit()
        r = self._refused("unresolved_reference")
        self.assertEqual((r["table"], r["column"], r["parent"]), ("trip_turn_links", "assistant_turn_row_id", "turns"))

    def test_missing_trip_source_file_refuses_but_orphan_dirs_never_block(self):
        src = self.ids["trip_sources"][0]
        (self.root / "trip_sources" / src / "ticket.pdf").unlink()
        r = self._refused("referenced_file_missing")
        self.assertEqual((r["table"], r["column"]), ("trip_sources", "storage_path"))
        # restore it: the orphan dir is still there and the export succeeds
        self.file(f"trip_sources/{src}/ticket.pdf", b"%PDF-ADA-0")
        self.assertTrue((self.root / "trip_sources" / "orphan-dir-0000").is_dir())
        self.assertTrue(self.export().package_path.is_file())

    def test_photo_path_outside_data_dir_refuses(self):
        self.con.execute("UPDATE photos SET image_path='/etc/passwd' WHERE id=?", (self.photos[0],))
        self.con.commit()
        r = self._refused("path_outside_data_dir")
        self.assertEqual(r["table"], "photos")

    def test_credential_shaped_value_refuses(self):
        self.con.execute("UPDATE trip_public_context SET result_summary=? WHERE trip_id=?",
                         ("fetched with Authorization: Bearer ya29.a0AfH6SMBxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", self.trips[0]))
        self.con.commit()
        r = self._refused("credential_shaped_value")
        self.assertEqual(r["table"], "trip_public_context")

    def test_narrator_files_changing_during_collection_refuses(self):
        def mutate(root):
            (root / "memory/archive/people" / self.ada / "sessions/conv-ada-1/audio/t1.webm").write_bytes(b"CHANGED!!")
        self._refused("refused_changed_during_snapshot", _after_collect_hook=mutate)

    def test_package_inside_data_dir_refuses(self):
        with self.assertRaises(pkg.ExportRefused) as cm:
            pkg.export_narrator(self.ada, data_dir=self.root, db_path=self.db_path, out_dir=self.root / "exports")
        self.assertEqual(cm.exception.reasons[0]["code"], "out_dir_inside_data_dir")

    def test_unknown_narrator_refuses(self):
        with self.assertRaises(pkg.ExportRefused) as cm:
            pkg.export_narrator("no-such-person", data_dir=self.root, db_path=self.db_path, out_dir=self.out)
        self.assertEqual(cm.exception.reasons[0]["code"], "narrator_not_found")

    def test_validator_rejects_a_tampered_package(self):
        res = self.export()
        # flip one payload byte in place
        tampered = self.out / "tampered.lorevox.zip"
        with zipfile.ZipFile(res.package_path) as src, zipfile.ZipFile(tampered, "w") as dst:
            for info in src.infolist():
                data = src.read(info.filename)
                if info.filename.endswith("/trips.jsonl"):
                    data = data.replace(b"Trip 0", b"Trip X")
                dst.writestr(info, data)
        rep = pkg.validate_package(tampered)
        self.assertFalse(rep.ok)
        self.assertTrue(any("bagit validation failed" in p for p in rep.problems), rep.problems)


# ══════════════════════════════════════════════════════════════════════

class ExporterConsumesTheDeclarationOnly(unittest.TestCase):
    """No narrator name, no table list, no path list lives in the exporter."""

    def test_exporter_source_names_no_table_and_no_narrator(self):
        import inspect
        src = inspect.getsource(pkg)
        for forbidden in ("Horne", "Christopher", "Kent", "Janice", "a4b2f07a", "4aa0cc2b", "93479171",
                          '"trips"', '"trip_sources"', '"photos"', '"memory_archive', "trip_photo_links"):
            self.assertNotIn(forbidden, src, f"exporter hard-codes {forbidden!r}; ownership belongs to the declaration")
        # the only table names it may know are the identity and residue anchors
        self.assertIn('"people"', src)
        self.assertIn('"sessions"', src)

    def test_conditional_lane_and_column_refs_are_declared_not_coded(self):
        self.assertTrue(inv.fs_lane("import_staging").conditional_sql)
        self.assertTrue(any(r.table == "trip_turn_links" and r.column == "conv_id" for r in inv.COLUMN_ONLY_REFERENCES))


if __name__ == "__main__":
    unittest.main()
