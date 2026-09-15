"""WO-LOREVOX-MULTI-ORIGIN-MERGE-REMAP-01 — the executor, into a real Lorevox root.

THE TARGET IS BUILT BY THE PRODUCT, NOT BY THIS FILE. Every test initialises its
disposable root the way the product does — `DATA_DIR` / `DB_NAME`, reload `api.db`,
`init_db()` — which is the same path `tests/test_narrator_package_restore.py` uses and
the same definition of "clean installation" Phase 7 will use. Hand-built SQL would be a
fixture supplying the property under test: Phase 5a's two defects (dependency matching on
the wrong column, and a clean root having no `chat_ws` plan) were both defects OF
initialisation, and a test that writes its own schema cannot see them.

The rows below are schema-complete against the shipped DDL (`db.py:577-626`, `:7372-7424`)
rather than the planner suite's minimal shapes, because these actually reach SQLite.

Run:
    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_narrator_merge_apply
"""
from __future__ import annotations

import importlib
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "server" / "code"))

from tests.test_narrator_merge import NARRATOR, _build_package  # noqa: E402

from api.services import narrator_merge as nm                   # noqa: E402
from api.services import narrator_merge_apply as nma            # noqa: E402

TS = "2026-01-01T00:00:00"
ARCHIVE = f"memory/archive/people/{NARRATOR}"
PKG_A = "aaaa11112222"
PKG_B = "bbbb33334444"


def _archive(narrator: str) -> str:
    return f"memory/archive/people/{narrator}"


def _person(narrator: str = NARRATOR, name="Ada Lovelace"):
    return {"id": narrator, "display_name": name, "role": "",
            "date_of_birth": "", "place_of_birth": "", "created_at": TS,
            "updated_at": TS}


def _gp(pid, name, narrator: str = NARRATOR):
    return {"id": pid, "narrator_id": narrator, "display_name": name,
            "first_name": "", "middle_name": "", "last_name": "", "maiden_name": "",
            "birth_date": "", "birth_place": "", "occupation": "", "deceased": 0,
            "is_narrator": 0, "source": "manual", "provenance": "", "confidence": 1.0,
            "created_at": TS, "updated_at": TS}


def _records(conv: str, turn_id: int, gp_name: str, extra_graph=None,
             narrator: str = NARRATOR, gp_id: str = "gp-shared"):
    out = {
        "people": [_person(narrator)],
        "sessions": [{"conv_id": conv, "title": "a session", "updated_at": TS,
                      "payload_json": "{}", "person_id": narrator}],
        "turns": [{"id": turn_id, "conv_id": conv, "role": "user",
                   "content": f"words in {conv}", "ts": TS, "anchor_id": "",
                   "meta_json": "{}"}],
        # SAME id on both origins with IDENTICAL content, in a table with no defensible
        # cross-origin key: must be reallocated, and both rows must survive.
        "graph_persons": [_gp(gp_id, gp_name, narrator)],
    }
    if extra_graph:
        out.update(extra_graph)
    return out


def _meta(conv: str, narrator: str = NARRATOR) -> bytes:
    return json.dumps({"person_id": narrator, "session_id": conv, "mode": "oral_history",
                       "title": f"title {conv}", "started_at": TS,
                       "created_at": TS}).encode("utf-8")


class _Merged(unittest.TestCase):
    """Two packages, a product-initialised empty root, and the plan between them."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="lorevox-merge-apply-")
        base = Path(self._tmp.name)
        self.src_dir = base / "packages"
        self.src_dir.mkdir()

        self.a = _build_package(
            self.src_dir / "a.lorevox.zip", PKG_A,
            _records("conv-a", 1, "Kent Horne"),
            {f"{ARCHIVE}/index.json": b'{"person_id":"x","sessions":[]}',
             f"{ARCHIVE}/sessions/conv-a/meta.json": _meta("conv-a"),
             "memory/archive/photos/a-only.jpg": b"A ONLY"})
        self.b = _build_package(
            self.src_dir / "b.lorevox.zip", PKG_B,
            _records("conv-b", 1, "Kent Horne", extra_graph={
                "graph_relationships": [{
                    "id": "gr-1", "narrator_id": NARRATOR,
                    "from_person_id": "gp-shared", "to_person_id": "gp-shared",
                    "relationship_type": "self", "subtype": "", "label": "",
                    "status": "active", "notes": "", "source": "manual",
                    "provenance": "", "confidence": 1.0, "start_date": "",
                    "end_date": "", "created_at": TS, "updated_at": TS,
                    "meta_json": "{}"}]}),
            {f"{ARCHIVE}/index.json": b'{"person_id":"y","sessions":[]}',
             f"{ARCHIVE}/sessions/conv-b/meta.json": _meta("conv-b"),
             "memory/archive/photos/b-only.jpg": b"B ONLY"})

        self.root = base / "target"
        self.root.mkdir()
        self.db = self._init_product_root(self.root)
        self.plan = nm.plan_merge(self.a, self.b, label_a="A", label_b="B")

    def tearDown(self):
        self._tmp.cleanup()

    def _init_product_root(self, root: Path) -> Path:
        """The product's own initialisation, exactly as the restore suite does it."""
        os.environ["DATA_DIR"] = str(root)
        os.environ["DB_NAME"] = "target.sqlite3"
        from api import db as _db
        importlib.reload(_db)
        _db.init_db()
        db_path = Path(_db.DB_PATH)
        self.assertTrue(str(db_path).startswith(str(root)), db_path)
        # DATA_DIR must not stay pointed at the target: `verify_target` forbids the LIVE
        # root, and leaving it set would make every target look like the live one.
        os.environ.pop("DATA_DIR", None)
        os.environ.pop("DB_NAME", None)
        return db_path

    def con(self):
        con = sqlite3.connect(str(self.db))
        con.row_factory = sqlite3.Row
        self.addCleanup(con.close)
        return con

    def bind(self, plan=None):
        return nma.bind_to_target(plan or self.plan, data_dir=self.root, db_path=self.db)

    def apply(self, bound=None, **kw):
        return nma.apply_merge(bound if bound is not None else self.bind(),
                               requested_by="test", **kw)

    def files_on_disk(self):
        return sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")
                      if p.is_file() and not p.name.startswith("target.sqlite3"))


class PlannerStaysWriterFree(_Merged):
    def test_the_planner_module_contains_no_writer(self):
        """The property a reviewer checked by reading `narrator_merge.py`. If a write
        primitive ever lands in it, the separation that made that review possible is
        gone — so it fails here instead of quietly."""
        src = (REPO / "server" / "code" / "api" / "services" / "narrator_merge.py"
               ).read_text(encoding="utf-8")
        # Write primitives only. The planner legitimately opens files for READING
        # (`path.open("rb")` when it hashes a package), so a bare `open(` would be a
        # guard pinned to the wrong thing — the failure mode CLAUDE.md names.
        for forbidden in ("sqlite3.connect", "os.open(", ".write_text(", ".write_bytes(",
                          "INSERT INTO", "shutil.copy", ".mkdir(", '"wb"', "'wb'",
                          '"w"', "'w'"):
            self.assertNotIn(forbidden, src,
                             f"the planner must not be able to write: found {forbidden!r}")


class TargetPreconditions(_Merged):
    def test_a_product_initialised_empty_root_is_ready(self):
        rep = nma.verify_target(data_dir=self.root, db_path=self.db, plan=self.plan)
        self.assertTrue(rep.ready, rep.reasons)

    def test_an_uninitialised_root_is_refused_and_NOT_created(self):
        """Merge/Remap populates a root; it never initialises one. Phase 5a's defects
        were defects of initialisation, and a merge that built its own schema would be
        re-deciding what a clean Lorevox installation is."""
        empty = Path(self._tmp.name) / "never-initialised"
        empty.mkdir()
        rep = nma.verify_target(data_dir=empty, db_path=empty / "target.sqlite3",
                                plan=self.plan)
        self.assertFalse(rep.ready)
        self.assertIn(nma.R_TARGET_DB_MISSING, [r["code"] for r in rep.reasons])
        self.assertEqual(list(empty.iterdir()), [], "verify_target created something")

    def test_the_live_data_dir_is_refused_as_a_target(self):
        os.environ["DATA_DIR"] = str(self.root)
        try:
            rep = nma.verify_target(data_dir=self.root, db_path=self.db, plan=self.plan)
        finally:
            os.environ.pop("DATA_DIR", None)
        self.assertFalse(rep.ready)
        self.assertIn(nma.R_TARGET_IS_A_SOURCE, [r["code"] for r in rep.reasons])

    def test_a_root_holding_ANOTHER_narrator_is_still_ready(self):
        """The correction. Refusing here would have made the family root impossible to
        build: Christopher lands first, and Kent and Janice must then be able to join
        the SAME installation. Their occupied ids are handled by binding, not by
        keeping the root empty."""
        con = sqlite3.connect(str(self.db))
        con.execute("INSERT INTO people (id, display_name, created_at, updated_at) "
                    "VALUES (?,?,?,?)", ("someone-else", "Someone", TS, TS))
        con.commit()
        con.close()
        rep = nma.verify_target(data_dir=self.root, db_path=self.db, plan=self.plan)
        self.assertTrue(rep.ready, rep.reasons)
        self.assertEqual(rep.checks["other_narrators"], ["someone-else"])

    def test_a_root_already_holding_THIS_narrator_is_refused(self):
        con = sqlite3.connect(str(self.db))
        con.execute("INSERT INTO people (id, display_name, created_at, updated_at) "
                    "VALUES (?,?,?,?)", (NARRATOR, "Ada", TS, TS))
        con.commit()
        con.close()
        rep = nma.verify_target(data_dir=self.root, db_path=self.db, plan=self.plan)
        self.assertFalse(rep.ready)
        self.assertIn(nma.R_TARGET_NARRATOR_PRESENT, [r["code"] for r in rep.reasons])

    def test_a_planned_file_already_present_is_refused_before_any_write(self):
        """O_EXCL would fail mid-run otherwise, and a half-populated root is the one
        outcome that must never exist."""
        dest = self.root / "memory" / "archive" / "photos"
        dest.mkdir(parents=True)
        (dest / "a-only.jpg").write_bytes(b"SOMETHING ELSE")
        rep = nma.verify_target(data_dir=self.root, db_path=self.db, plan=self.plan)
        self.assertFalse(rep.ready)
        self.assertIn(nma.R_TARGET_PAYLOAD_PRESENT, [r["code"] for r in rep.reasons])


class SuccessfulMerge(_Merged):
    def setUp(self):
        super().setUp()
        self.assertFalse(self.plan.refused, self.plan.refusals)
        # keep the BoundPlan that was actually executed: the durable ledger records the
        # BOUND decision, and asserting against a freshly derived one would be asserting
        # against something the run never used
        self.bound = self.bind()
        self.result = self.apply(self.bound)

    def test_execution_matches_the_plan_exactly(self):
        """Acceptance §6.3: the plan the dry run produced is what the run performs."""
        expected = {t: len(rows) for t, rows in self.plan.merged_records.items() if rows}
        self.assertEqual(self.result.records_inserted, expected)
        self.assertEqual(sorted(self.result.files_created),
                         sorted(e["path"] for e in self.plan.files_union))

    def test_both_narrator_rows_became_one_narrator(self):
        rows = self.con().execute("SELECT id FROM people").fetchall()
        self.assertEqual([r["id"] for r in rows], [NARRATOR])

    def test_every_turn_from_both_origins_landed_with_a_unique_id(self):
        rows = self.con().execute("SELECT id, conv_id FROM turns ORDER BY id").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["conv_id"] for r in rows}, {"conv-a", "conv-b"})
        self.assertEqual(len({r["id"] for r in rows}), 2)

    def test_the_identical_colliding_graph_rows_both_survive(self):
        """The review defect, end to end in a real database: two byte-identical rows
        under one TEXT PRIMARY KEY would have made this insert impossible."""
        rows = self.con().execute("SELECT id, display_name FROM graph_persons").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["display_name"] for r in rows}, {"Kent Horne"})
        self.assertEqual(len({r["id"] for r in rows}), 2)

    def test_the_relationship_points_at_the_reallocated_row(self):
        rel = self.con().execute(
            "SELECT from_person_id, to_person_id FROM graph_relationships").fetchone()
        ids = {r["id"] for r in self.con().execute("SELECT id FROM graph_persons")}
        self.assertIn(rel["from_person_id"], ids)
        self.assertIn(rel["to_person_id"], ids)
        self.assertEqual(rel["from_person_id"],
                         self.plan.remap["graph_persons.id"]["B"]["gp-shared"])

    def test_sqlite_foreign_keys_are_intact(self):
        self.assertEqual(self.con().execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_the_semantic_validator_passes_on_what_actually_landed(self):
        """Read back from the DATABASE, not from the plan. `foreign_key_check` above
        cannot see the encoded and bare-column references at all."""
        con = self.con()
        records = {}
        for parent in nm.CLOSURE_ESTABLISHED:
            for table in {parent.split(".")[0]} | {s.table for s in nm.reference_sites(parent)}:
                try:
                    records[table] = [dict(r) for r in con.execute(f'SELECT * FROM "{table}"')]
                except sqlite3.Error:
                    pass
        self.assertEqual(nm.validate_semantic_references(records), [])

    def test_every_planned_file_landed_with_the_planned_bytes(self):
        for entry in self.plan.files_union:
            dest = self.root / entry["path"]
            self.assertTrue(dest.is_file(), entry["path"])

    def test_index_json_was_regenerated_from_the_merged_sessions(self):
        """§3b: a derived registry, rebuilt from both origins' `meta.json`, never
        surfaced as a conflict."""
        self.assertIn(f"{ARCHIVE}/index.json", self.result.index_files_regenerated)
        data = json.loads((self.root / ARCHIVE / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(s["session_id"] for s in data["sessions"]),
                         ["conv-a", "conv-b"])

    def test_the_job_row_is_complete_in_the_MERGE_ledger(self):
        """0057, not 0054. The restore ledger's `CHECK (kind IN ('restore'))` refused
        the first draft's write, and it was right to: a merge is two packages plus a
        plan, which singular `package_id` / `package_path` columns cannot express."""
        row = self.con().execute(
            "SELECT * FROM narrator_merge_jobs WHERE id=?",
            (self.result.job_id,)).fetchone()
        self.assertEqual(row["state"], "complete")
        self.assertEqual(row["narrator_id"], NARRATOR)
        self.assertEqual({row["source_a_package_id"], row["source_b_package_id"]},
                         {PKG_A, PKG_B})
        self.assertEqual(len(row["source_a_sha256"]), 64)
        self.assertEqual(len(row["source_b_sha256"]), 64)
        # The durable fingerprint is the BOUND one — what actually landed — not the
        # pre-target source plan. The ledger reads end to end:
        #   source packages + source planning → target_basis (the exact target state
        #   inspected) → target remap → execution fingerprint (the bound decision applied)
        self.assertEqual(row["plan_fingerprint"], self.bound.execution_fingerprint)
        self.assertEqual(row["target_basis"], self.bound.basis_fingerprint)

    def test_the_ledger_records_the_target_basis_it_was_bound_against(self):
        """The defect this test exists for: `_merge_job_write` inserts only the keys in
        `_MERGE_JOB_COLUMNS`, so a column missing from that tuple is silently dropped.
        `target_basis` was, and nothing noticed, because no assertion read it back."""
        row = self.con().execute(
            "SELECT target_basis FROM narrator_merge_jobs WHERE id=?",
            (self.result.job_id,)).fetchone()
        self.assertTrue(row["target_basis"], "the basis fingerprint was computed and lost")
        self.assertEqual(len(row["target_basis"]), 64)

    def test_the_bound_fingerprint_is_not_the_source_fingerprint(self):
        """They answer different questions and must not be interchangeable: one is 'what
        did these two packages decide', the other 'what was applied to THIS target'."""
        self.assertNotEqual(self.bound.execution_fingerprint,
                            nma.plan_fingerprint(self.plan))

    def test_the_ledger_writer_covers_every_column_of_0057(self):
        """A production-boundary guard, not a restatement. Asks the SHIPPED table what
        its columns are and holds the writer's tuple against them — so a future column
        added to 0057 fails here instead of being written nowhere."""
        cols = {r["name"] for r in self.con().execute(
            "PRAGMA table_info('narrator_merge_jobs')")}
        self.assertEqual(set(nma._MERGE_JOB_COLUMNS), cols,
                         "the merge ledger writer and migration 0057 disagree; a column "
                         "missing from _MERGE_JOB_COLUMNS is silently dropped")

    def test_the_restore_ledger_was_not_touched(self):
        """Restore remains restore-only."""
        n = self.con().execute(
            "SELECT COUNT(*) c FROM narrator_package_jobs").fetchone()["c"]
        self.assertEqual(n, 0)

    def test_the_SOURCE_plan_fingerprint_is_deterministic(self):
        """Still valid, and deliberately separate from the durable ledger assertions
        above: this pins that two packages produce the same decision every time, which
        is what a later human adjudication of refused conflicts would bind to. It is not
        the fingerprint the ledger stores."""
        again = nm.plan_merge(self.a, self.b, label_a="A", label_b="B")
        self.assertEqual(nma.plan_fingerprint(again), nma.plan_fingerprint(self.plan))


class RefusalsWriteNothing(_Merged):
    def _assert_untouched(self):
        self.assertEqual(self.con().execute("SELECT COUNT(*) c FROM people").fetchone()["c"], 0)
        self.assertEqual(self.files_on_disk(), [])

    def test_a_plan_with_unresolved_conflicts_is_never_executed(self):
        """The expected Christopher outcome: everything up to the conflict boundary is
        proven, and then nothing is written. That is a V1 acceptance result."""
        self.plan.refusals.append({"code": nm.R_SAME_KEY_DIFFERENT_CONTENT,
                                   "detail": "profiles key=… differs"})
        with self.assertRaises(nma.MergeApplyRefused) as ctx:
            self.apply()
        self.assertEqual(ctx.exception.code, nma.R_PLAN_UNRESOLVED)
        self._assert_untouched()

    def test_the_refusal_report_can_carry_a_human_adjudication_later(self):
        """Not resolution — addressability. Each conflict is named, and the report binds
        to the exact package ids and hashes, so a decision cannot be replayed against
        different source data."""
        self.plan.refusals.append({"code": nm.R_FILE_PATH_DIFFERENT_BYTES,
                                   "detail": "rolling_summary.json"})
        with self.assertRaises(nma.MergeApplyRefused) as ctx:
            self.apply()
        report = ctx.exception.report
        self.assertTrue(report["refusals"])
        self.assertEqual({o["package_id"] for o in report["origins"]}, {PKG_A, PKG_B})
        self.assertTrue(all(o["sha256"] for o in report["origins"]))

    def test_a_changed_source_package_refuses(self):
        """A plan is a decision about specific bytes."""
        self.plan.origins[0]["sha256"] = "0" * 64
        with self.assertRaises(nma.MergeApplyRefused) as ctx:
            self.apply()
        self.assertEqual(ctx.exception.code, nma.R_SOURCE_CHANGED)
        self._assert_untouched()

    def test_a_target_that_moved_after_binding_refuses_instead_of_replanning(self):
        """The ids about to be written were chosen against a specific target state.
        Re-deriving them mid-apply would execute a plan nobody dry-ran."""
        bound = self.bind()
        con = sqlite3.connect(str(self.db))
        con.execute("INSERT INTO people (id, display_name, created_at, updated_at) "
                    "VALUES (?,?,?,?)", ("arrived-late", "Late", TS, TS))
        con.commit()
        con.close()
        with self.assertRaises(nma.MergeApplyRefused) as ctx:
            self.apply(bound)
        self.assertEqual(ctx.exception.code, nma.R_TARGET_CHANGED)
        self.assertEqual(self.files_on_disk(), [])

    def test_writing_the_merge_job_does_not_invalidate_the_binding(self):
        """The basis must exclude operational churn, or a merge would invalidate its
        own basis the moment it recorded that it had started."""
        bound = self.bind()
        before = bound.basis_fingerprint
        self.apply(bound)
        self.assertEqual(before, bound.basis_fingerprint)
        self.assertTrue(self.con().execute(
            "SELECT COUNT(*) c FROM narrator_merge_jobs").fetchone()["c"])

    def test_a_failure_inside_the_transaction_leaves_no_partial_root(self):
        """Zero rows, zero files, and a job row that says so."""
        with self.assertRaises(RuntimeError):
            self.apply(_crash_seam=lambda point: (_ for _ in ()).throw(
                ValueError("forced")) if point == "after_first_file" else None)
        self.assertEqual(self.con().execute(
            "SELECT COUNT(*) c FROM people").fetchone()["c"], 0)
        self.assertEqual(self.files_on_disk(), [])
        states = [r["state"] for r in self.con().execute(
            "SELECT state FROM narrator_merge_jobs")]
        self.assertTrue(states and all(s in ("failed", "cleanup_required") for s in states), states)


class SequentialFamilyAccumulation(_Merged):
    """Christopher → Kent → Janice, in miniature, into ONE installation.

    This is the test the architecture exists for. Each narrator's two-origin plan
    independently allocates installation-local integers from 1, because the source
    planner knows nothing about targets — so the second and third narrators ask for ids
    the first already occupies. Binding is what makes that safe, and nothing else here
    would catch it: every earlier test merges into an empty root, where binding is a
    no-op and a completely unbound executor would pass.
    """

    NARRATOR_B = "22222222-3333-4444-5555-666666666666"
    NARRATOR_C = "33333333-4444-5555-6666-777777777777"

    def _origins_for(self, narrator: str, tag: str, pkg_a: str, pkg_b: str):
        arch = _archive(narrator)
        a = _build_package(
            self.src_dir / f"{tag}-a.lorevox.zip", pkg_a,
            _records(f"{tag}-conv-a", 1, "Relative One", narrator=narrator,
                     gp_id=f"{tag}-gp"),
            {f"{arch}/sessions/{tag}-conv-a/meta.json": _meta(f"{tag}-conv-a", narrator),
             f"memory/archive/photos/{tag}-a.jpg": f"{tag} A".encode()},
            narrator_id=narrator)
        b = _build_package(
            self.src_dir / f"{tag}-b.lorevox.zip", pkg_b,
            _records(f"{tag}-conv-b", 1, "Relative One", narrator=narrator,
                     gp_id=f"{tag}-gp"),
            {f"{arch}/sessions/{tag}-conv-b/meta.json": _meta(f"{tag}-conv-b", narrator),
             f"memory/archive/photos/{tag}-b.jpg": f"{tag} B".encode()},
            narrator_id=narrator)
        return a, b

    def _merge_narrator(self, narrator: str, tag: str, pkg_a: str, pkg_b: str):
        a, b = self._origins_for(narrator, tag, pkg_a, pkg_b)
        plan = nm.plan_merge(a, b, label_a=f"{tag}A", label_b=f"{tag}B")
        self.assertFalse(plan.refused, plan.refusals)
        # the source plan really does start from 1 — otherwise this proves nothing
        self.assertEqual(sorted(r["id"] for r in plan.merged_records["turns"]), [1, 2])
        bound = nma.bind_to_target(plan, data_dir=self.root, db_path=self.db)
        self.assertFalse(bound.refused, bound.refusals + bound.target.reasons)
        return plan, bound, nma.apply_merge(bound, requested_by="test")

    def setUp(self):
        super().setUp()
        # narrator A is the fixture's own pair, merged first
        self.res_a = self.apply()
        self.a_turns = {r["id"]: r["conv_id"] for r in
                        self.con().execute("SELECT id, conv_id FROM turns")}

    def test_the_second_narrator_receives_target_safe_ids(self):
        plan, bound, res = self._merge_narrator(self.NARRATOR_B, "kent",
                                                "cccc55556666", "dddd77778888")
        self.assertTrue(bound.target_remap.get("turns.id"),
                        "binding allocated nothing — the second narrator would collide")
        rows = self.con().execute("SELECT id, conv_id FROM turns").fetchall()
        ids = [r["id"] for r in rows]
        self.assertEqual(len(ids), len(set(ids)), "two narrators share a turns.id")
        self.assertEqual(len(rows), 4)

    def test_the_first_narrator_is_untouched_by_the_second(self):
        self._merge_narrator(self.NARRATOR_B, "kent", "cccc55556666", "dddd77778888")
        after = {r["id"]: r["conv_id"] for r in
                 self.con().execute("SELECT id, conv_id FROM turns")}
        for tid, conv in self.a_turns.items():
            self.assertEqual(after.get(tid), conv, f"turn {tid} moved or changed")

    def test_the_second_narrators_references_follow_its_new_ids(self):
        plan, bound, res = self._merge_narrator(self.NARRATOR_B, "kent",
                                                "cccc55556666", "dddd77778888")
        con = self.con()
        kent_turns = {r["id"] for r in con.execute(
            "SELECT t.id FROM turns t JOIN sessions s ON s.conv_id=t.conv_id "
            "WHERE s.person_id=?", (self.NARRATOR_B,))}
        self.assertTrue(kent_turns)
        self.assertEqual(kent_turns & set(self.a_turns), set(),
                         "the second narrator reused the first narrator's turn ids")

    def test_both_narrators_are_present_and_valid(self):
        self._merge_narrator(self.NARRATOR_B, "kent", "cccc55556666", "dddd77778888")
        con = self.con()
        self.assertEqual({r["id"] for r in con.execute("SELECT id FROM people")},
                         {NARRATOR, self.NARRATOR_B})
        self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])
        records = {}
        for parent in nm.CLOSURE_ESTABLISHED:
            for table in {parent.split(".")[0]} | {s.table for s in nm.reference_sites(parent)}:
                try:
                    records[table] = [dict(r) for r in con.execute(f'SELECT * FROM "{table}"')]
                except sqlite3.Error:
                    pass
        self.assertEqual(nm.validate_semantic_references(records), [])

    def test_a_third_narrator_accumulates_too(self):
        """Christopher → Kent → Janice. Three independently planned merges, one root."""
        self._merge_narrator(self.NARRATOR_B, "kent", "cccc55556666", "dddd77778888")
        self._merge_narrator(self.NARRATOR_C, "janice", "eeee99990000", "ffff11112222")
        con = self.con()
        self.assertEqual({r["id"] for r in con.execute("SELECT id FROM people")},
                         {NARRATOR, self.NARRATOR_B, self.NARRATOR_C})
        ids = [r["id"] for r in con.execute("SELECT id FROM turns")]
        self.assertEqual(len(ids), 6)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_each_merge_has_its_own_complete_job(self):
        self._merge_narrator(self.NARRATOR_B, "kent", "cccc55556666", "dddd77778888")
        rows = self.con().execute(
            "SELECT narrator_id, state, plan_fingerprint FROM narrator_merge_jobs").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["state"] == "complete" for r in rows), [dict(r) for r in rows])
        self.assertEqual(len({r["plan_fingerprint"] for r in rows}), 2)

    def test_an_empty_target_still_yields_one_to_N(self):
        """Binding must change nothing when there is nothing to avoid — otherwise every
        first merge would churn ids for no reason."""
        fresh = Path(self._tmp.name) / "fresh"
        fresh.mkdir()
        db = self._init_product_root(fresh)
        bound = nma.bind_to_target(self.plan, data_dir=fresh, db_path=db)
        self.assertEqual(bound.target_remap.get("turns.id", {}), {})
        self.assertEqual(sorted(r["id"] for r in bound.merged_records["turns"]), [1, 2])


class CrashRecovery(_Merged):
    """A process death is not an exception. `_fail` never runs, so the ledger alone has
    to decide what may exist — which is the whole reason the manifest is durable before
    the first byte."""

    def _kill_after_first_file(self):
        class _Killed(BaseException):
            """Not an Exception: nothing in the executor catches it, exactly as a real
            process death would not be caught."""

        with self.assertRaises(_Killed):
            self.apply(_crash_seam=lambda point: (_ for _ in ()).throw(_Killed())
                       if point == "after_first_file" else None)
        row = self.con().execute("SELECT * FROM narrator_merge_jobs").fetchone()
        self.assertIsNotNone(row, "the job row must be durable before the first byte")
        self.assertIn(row["state"], ("validated", "files_copied"))
        self.assertTrue(json.loads(row["file_manifest_json"]),
                        "the job must name every file it MAY create, before it creates one")
        return row

    def test_a_crash_before_commit_is_recovered_to_failed_with_no_files_left(self):
        self._kill_after_first_file()
        self.assertTrue(self.files_on_disk(), "the crash should have left a file behind")
        out = nma.recover_merge_jobs(data_dir=self.root, db_path=self.db)
        self.assertEqual([r["now"] for r in out], ["failed"], out)
        self.assertEqual(self.files_on_disk(), [])
        self.assertEqual(self.con().execute(
            "SELECT COUNT(*) c FROM people").fetchone()["c"], 0)

    def test_recovery_NEVER_deletes_a_file_it_did_not_create(self):
        """Hash-gated, not path-gated. Something else at a planned path is left alone and
        named — deleting it would be recovery destroying a stranger's data."""
        row = self._kill_after_first_file()
        landed = json.loads(row["files_json"]) or self.files_on_disk()
        victim = self.root / landed[0]
        victim.write_bytes(b"SOMEBODY ELSE'S BYTES")
        out = nma.recover_merge_jobs(data_dir=self.root, db_path=self.db)
        self.assertEqual(out[0]["now"], "cleanup_required")
        self.assertIn(landed[0], out[0]["left"])
        self.assertTrue(victim.is_file(), "recovery deleted a file it did not create")
        self.assertEqual(victim.read_bytes(), b"SOMEBODY ELSE'S BYTES")

    def test_recovery_after_a_committed_merge_finishes_it_and_deletes_nothing(self):
        """`db_committed` means the rows ARE published. Recovery must never roll a
        published narrator back by guessing."""
        class _Killed(BaseException):
            pass

        with self.assertRaises(_Killed):
            self.apply(_crash_seam=lambda point: (_ for _ in ()).throw(_Killed())
                       if point == "after_commit" else None)
        before = self.files_on_disk()
        self.assertEqual(self.con().execute(
            "SELECT state FROM narrator_merge_jobs").fetchone()["state"], "db_committed")
        out = nma.recover_merge_jobs(data_dir=self.root, db_path=self.db)
        self.assertEqual(out[0]["now"], "complete")
        self.assertEqual(out[0]["action"], "finished")
        self.assertEqual(self.files_on_disk(), before, "recovery removed published files")
        self.assertEqual(self.con().execute(
            "SELECT COUNT(*) c FROM people").fetchone()["c"], 1)

    def test_recovery_is_idempotent(self):
        self._kill_after_first_file()
        first = nma.recover_merge_jobs(data_dir=self.root, db_path=self.db)
        second = nma.recover_merge_jobs(data_dir=self.root, db_path=self.db)
        self.assertEqual(first[0]["now"], "failed")
        self.assertEqual(second[0]["action"], "none")

    def test_recovery_skips_a_job_that_belongs_to_another_root(self):
        self._kill_after_first_file()
        other = Path(self._tmp.name) / "other-root"
        other.mkdir()
        out = nma.recover_merge_jobs(data_dir=other, db_path=self.db)
        self.assertEqual(out[0]["action"], "skipped")
        self.assertTrue(self.files_on_disk(), "a skipped job must leave its files alone")


if __name__ == "__main__":
    unittest.main()
