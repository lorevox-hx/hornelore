"""WO-LOREVOX-MULTI-ORIGIN-MERGE-REMAP-01 — the merge planner, on synthetic two-origin
packages built to contain every construct §6.1 names.

THE FIXTURES ARE REAL PACKAGES. They are built the way `export_narrator` builds one —
`bagit.make_bag(..., checksums=["sha256"])`, the Lorevox manifest written at the bag ROOT
afterwards, `bag.save(manifests=True)`, then zipped with arcnames relative to the staging
root (`narrator_package.py:798-819`) — and they are read back through the shipped
`validate_package`. A dict handed to an internal function would prove nothing about the
zip boundary the merge actually crosses.

AND THE FIXTURES DO NOT SUPPLY THE PROPERTIES BEING PROVEN. The manifest counts are
DERIVED from the rows and files actually written, the package format constants are
imported from production rather than retyped, every encoded reference is rendered by the
module under test and parsed back by the PRODUCTION parser, and the closure the merge
rewrites is the production declaration — held against the comparator's independently
discovered list by `test_closure_parity_with_the_independent_evidence_list`.

Run:
    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_narrator_merge
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "server" / "code"))

from api.services import cross_origin_identity as xid    # noqa: E402
from api.services import narrator_merge as nm            # noqa: E402
from api.services import narrator_data_inventory as inv  # noqa: E402
from api.services import narrator_package as npkg        # noqa: E402

NARRATOR = "11111111-2222-3333-4444-555555555555"
# package_id decides rank, and 'aaaa…' < 'bbbb…', so DESKTOP is rank 0 regardless of
# the order a caller passes the two packages in. Asserted, not assumed, below.
PKG_DESKTOP = "aaaa11112222"
PKG_LAPTOP = "bbbb33334444"

ARCHIVE = f"memory/archive/people/{NARRATOR}"


def _load_comparator():
    """Import scripts/two_origin_compare.py by path — it is a script, not a package."""
    spec = importlib.util.spec_from_file_location(
        "two_origin_compare", REPO / "scripts" / "two_origin_compare.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _build_package(dest: Path, package_id: str, records: dict, files: dict,
                   narrator_id: str = NARRATOR) -> Path:
    """Build a package exactly the way the exporter does."""
    import bagit

    staging = dest.parent / f"staging-{package_id}"
    if staging.exists():
        shutil.rmtree(staging)
    (staging / "records").mkdir(parents=True)
    (staging / "files").mkdir(parents=True)

    for table, rows in records.items():
        (staging / "records" / f"{table}.jsonl").write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
    for rel, blob in files.items():
        target = staging / "files" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)

    bag = bagit.make_bag(str(staging), checksums=["sha256"], bag_info={
        "Source-Organization": "Lorevox test",
        "External-Identifier": f"{npkg.PACKAGE_FORMAT}:{package_id}",
    })
    manifest = {
        "package_id": package_id,
        "narrator_id": narrator_id,
        "package_format": npkg.PACKAGE_FORMAT,
        "package_format_version": npkg.PACKAGE_FORMAT_VERSION,
        "package_kind": npkg.PACKAGE_KIND,
        # DERIVED from what was actually written — the fixture must not assert counts
        "record_counts_by_lane": {t: len(r) for t, r in records.items()},
        "file_counts_by_lane": {"payload": len(files)},
    }
    (staging / npkg.MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    bag.save(manifests=True)

    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(staging.rglob("*")):
            if f.is_file():
                zf.write(f, f.relative_to(staging).as_posix())
    shutil.rmtree(staging)
    return dest


def _desktop_records() -> dict:
    return {
        "people": [{"id": NARRATOR, "display_name": "Ada Lovelace"}],
        # same logical key (person_id), DIFFERENT content -> must refuse
        "profiles": [{"person_id": NARRATOR, "profile_json": '{"pob":"Williston"}',
                      "updated_at": "2026-01-01T00:00:00"}],
        "sessions": [{"conv_id": "c-both", "person_id": NARRATOR, "title": "shared",
                      "updated_at": "2026-01-01T00:00:00"},
                     {"conv_id": "c-desk", "person_id": NARRATOR, "title": "desktop only",
                      "updated_at": "2026-01-01T00:00:00"}],
        # ids 1 and 2; the laptop also has a 1 -> deliberate surrogate collision
        "turns": [{"id": 1, "conv_id": "c-both", "role": "user", "content": "desktop one"},
                  {"id": 2, "conv_id": "c-desk", "role": "user", "content": "desktop two"}],
        "turn_extraction_ledger": [{"id": 1, "narrator_id": NARRATOR, "turn_key": "turnrow:2"}],
        "turn_extraction_results": [{"id": 1, "narrator_id": NARRATOR, "ledger_id": 1,
                                     "turn_key": "turnrow:2"}],
        # A TEXT PRIMARY KEY that COLLIDES across origins with different content. The
        # product mints graph-person ids deterministically from narrator + name, so
        # this is the shape the real Christopher comparison actually reports.
        "graph_persons": [{"id": "gp-shared", "narrator_id": NARRATOR,
                           "display_name": "Kent Horne", "source": "manual"},
                          # same id on BOTH origins with BYTE-IDENTICAL content. This
                          # is the case the first implementation got wrong: in a
                          # NO_SAFE_CROSS_ORIGIN_KEY table, equal bytes do not make two
                          # rows the same record, so both must survive and the shared
                          # primary key must still be broken.
                          {"id": "gp-twin", "narrator_id": NARRATOR,
                           "display_name": "Ruth Horne", "source": "manual"}],
        "bio_facts": [
            # same key as the laptop's, and the ONLY difference is which turn it cites:
            # a reference difference is not a content conflict (§1)
            {"id": "f-desk-1", "narrator_id": NARRATOR, "field_key": "birthplace",
             "value": "Williston", "source": json.dumps({"tier": 1, "turn_key": "turnrow:2"})},
            # same key, genuinely different VALUE -> must refuse
            {"id": "f-desk-2", "narrator_id": NARRATOR, "field_key": "occupation",
             "value": "mathematician", "source": json.dumps({"tier": 1})},
            # TWO rows under one logical key on ONE origin — BACKLOG §5
            # (`questionnaire_put`) produces exactly this. Neither may be collapsed.
            {"id": "f-desk-3", "narrator_id": NARRATOR, "field_key": "nickname",
             "value": "Ada", "source": json.dumps({"tier": 1})},
            {"id": "f-desk-4", "narrator_id": NARRATOR, "field_key": "nickname",
             "value": "Ada", "source": json.dumps({"tier": 2})},
        ],
    }


def _laptop_records() -> dict:
    return {
        "people": [{"id": NARRATOR, "display_name": "Ada Lovelace"}],
        "profiles": [{"person_id": NARRATOR, "profile_json": '{"pob":"Williston, ND"}',
                      "updated_at": "2026-02-02T00:00:00"}],
        "sessions": [{"conv_id": "c-both", "person_id": NARRATOR, "title": "shared",
                      # volatile-only difference: must NOT be a conflict
                      "updated_at": "2026-09-09T00:00:00"},
                     {"conv_id": "c-lap", "person_id": NARRATOR, "title": "laptop only",
                      "updated_at": "2026-01-01T00:00:00"}],
        "turns": [{"id": 1, "conv_id": "c-both", "role": "user", "content": "LAPTOP one"},
                  {"id": 3, "conv_id": "c-lap", "role": "user", "content": "laptop three"}],
        "trip_turn_links": [{"id": "ttl-1", "trip_id": "trip-1", "conv_id": "c-lap",
                             "user_turn_row_id": 1, "assistant_turn_row_id": 3}],
        "story_candidates": [{"id": "sc-1", "narrator_id": NARRATOR,
                              "source_user_turn_row_id": 1,
                              "completed_assistant_turn_row_id": 3}],
        "turn_extraction_ledger": [{"id": 1, "narrator_id": NARRATOR, "turn_key": "turnrow:3"}],
        "turn_extraction_results": [{"id": 1, "narrator_id": NARRATOR, "ledger_id": 1,
                                     "turn_key": "turnrow:3"}],
        # same physical id as the desktop's, DIFFERENT content -> must be reallocated,
        # and the two relationships pointing at it must follow the reallocation
        "graph_persons": [{"id": "gp-shared", "narrator_id": NARRATOR,
                           "display_name": "Kenneth Horne", "source": "manual"},
                          {"id": "gp-twin", "narrator_id": NARRATOR,
                           "display_name": "Ruth Horne", "source": "manual"},
                          {"id": "gp-lap", "narrator_id": NARRATOR,
                           "display_name": "Janice Horne", "source": "manual"}],
        "graph_relationships": [{"id": "gr-1", "narrator_id": NARRATOR,
                                 "from_person_id": "gp-shared", "to_person_id": "gp-lap",
                                 "relationship_type": "spouse"}],
        "bio_facts": [
            {"id": "f-lap-1", "narrator_id": NARRATOR, "field_key": "birthplace",
             "value": "Williston", "source": json.dumps({"tier": 1, "turn_key": "turnrow:3"})},
            {"id": "f-lap-2", "narrator_id": NARRATOR, "field_key": "occupation",
             "value": "COUNTESS", "source": json.dumps({"tier": 1})},
            {"id": "f-lap-3", "narrator_id": NARRATOR, "field_key": "nickname",
             "value": "Ada", "source": json.dumps({"tier": 1})},
        ],
    }


class _Fixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="lorevox-merge-tests-")
        root = Path(cls._tmp.name)
        cls.desk = _build_package(
            root / "desktop.lorevox.zip", PKG_DESKTOP, _desktop_records(),
            {
                "memory/archive/photos/same.jpg": b"IDENTICAL PHOTO BYTES",
                f"{ARCHIVE}/index.json": b'{"sessions":["c-both","c-desk"]}',
                f"{ARCHIVE}/rolling_summary.json": b'{"summary":"desktop memory"}',
                "memory/archive/photos/desk-only.jpg": b"DESKTOP ONLY",
            })
        cls.lap = _build_package(
            root / "laptop.lorevox.zip", PKG_LAPTOP, _laptop_records(),
            {
                "memory/archive/photos/same.jpg": b"IDENTICAL PHOTO BYTES",
                f"{ARCHIVE}/index.json": b'{"sessions":["c-both","c-lap"]}',
                f"{ARCHIVE}/rolling_summary.json": b'{"summary":"LAPTOP memory"}',
                "memory/archive/photos/lap-only.jpg": b"LAPTOP ONLY",
            })
        cls.plan = nm.plan_merge(cls.desk, cls.lap, label_a="desktop", label_b="laptop")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _rewrites(self, kind=None):
        return [r for r in self.plan.reference_rewrites
                if kind is None or r["kind"] == kind]


class PackagesAreReal(_Fixtures):
    def test_the_fixtures_pass_the_shipped_validator(self):
        """If these were not real packages, nothing below would test the real path."""
        for p in (self.desk, self.lap):
            report = npkg.validate_package(p)
            self.assertTrue(report.ok, report.problems)

    def test_both_packages_name_the_same_narrator(self):
        self.assertEqual({o["label"] for o in self.plan.origins}, {"desktop", "laptop"})
        self.assertEqual(self.plan.narrator_id, NARRATOR)


class WritesNothing(_Fixtures):
    """Acceptance §6.3. A planner that cannot write cannot fail this by accident."""

    def test_the_plan_reports_writing_nothing(self):
        self.assertFalse(self.plan.wrote_anything)

    def test_the_source_packages_are_byte_identical_after_planning(self):
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.desk, self.lap)}
        nm.plan_merge(self.desk, self.lap, label_a="desktop", label_b="laptop")
        for p, digest in before.items():
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), digest,
                             f"{p.name} changed during planning")

    def test_planning_creates_no_new_path_beside_the_packages(self):
        here = self.desk.parent
        before = sorted(x.name for x in here.iterdir())
        nm.plan_merge(self.desk, self.lap, label_a="desktop", label_b="laptop")
        self.assertEqual(sorted(x.name for x in here.iterdir()), before)


class DeterministicRemap(_Fixtures):
    def test_the_same_inputs_produce_the_same_ids_every_run(self):
        again = nm.plan_merge(self.desk, self.lap, label_a="desktop", label_b="laptop")
        self.assertEqual(again.remap, self.plan.remap)

    def test_argument_order_does_not_change_the_remap(self):
        """Rank comes from package_id, never from the order a caller passed them or
        from a label a caller chose."""
        swapped = nm.plan_merge(self.lap, self.desk, label_a="laptop", label_b="desktop")
        self.assertEqual(swapped.remap, self.plan.remap)

    def test_every_colliding_surrogate_is_separated(self):
        for surrogate in ("turns.id", "turn_extraction_ledger.id", "turn_extraction_results.id"):
            new_ids = [v for per in self.plan.remap[surrogate].values() for v in per.values()]
            self.assertEqual(len(new_ids), len(set(new_ids)),
                             f"{surrogate} allocated a duplicate new id")

    def test_the_turns_collision_is_actually_present_in_the_fixture(self):
        """A collision test proves nothing if the fixture has no collision. Measured
        from the packages, not asserted in a comment."""
        a = nm.load_origin(self.desk, "desktop")
        b = nm.load_origin(self.lap, "laptop")
        ids_a = {r["id"] for r in a.records["turns"]}
        ids_b = {r["id"] for r in b.records["turns"]}
        self.assertTrue(ids_a & ids_b, "fixture has no turns.id collision to remap")
        self.assertEqual({r["id"] for r in a.records["turn_extraction_results"]},
                         {r["id"] for r in b.records["turn_extraction_results"]})


class ReferenceRewrite(_Fixtures):
    def test_zero_dangling_references_after_the_rewrite(self):
        """Acceptance §6.1's closing clause."""
        self.assertEqual(self.plan.dangling_after_rewrite, [])

    def test_all_seven_turn_reference_forms_are_covered_by_the_closure(self):
        sites = {(s.table, s.column) for s in nm.reference_sites("turns.id")}
        self.assertEqual(sites, {
            ("trip_turn_links", "user_turn_row_id"),
            ("trip_turn_links", "assistant_turn_row_id"),
            ("story_candidates", "source_user_turn_row_id"),
            ("story_candidates", "completed_assistant_turn_row_id"),
            ("turn_extraction_ledger", "turn_key"),
            ("turn_extraction_results", "turn_key"),
            ("bio_facts", "source"),
        })

    def test_integer_text_and_json_forms_were_each_actually_rewritten(self):
        """Three forms, three parse/render paths. If any one silently did nothing the
        merge would dangle on real data, so each is required to have FIRED."""
        touched = {(r["table"], r["column"]) for r in self._rewrites("reference")}
        for site in (("trip_turn_links", "user_turn_row_id"),
                     ("story_candidates", "completed_assistant_turn_row_id"),
                     ("turn_extraction_ledger", "turn_key"),
                     ("bio_facts", "source")):
            self.assertIn(site, touched, f"{site} was never rewritten")

    def test_the_real_sql_fk_into_the_ledger_is_rewritten_too(self):
        touched = {(r["table"], r["column"]) for r in self._rewrites("reference")}
        self.assertIn(("turn_extraction_results", "ledger_id"), touched)

    def test_nothing_references_turn_extraction_results_id(self):
        """§3d, measured rather than assumed — and it is why the one real collision in
        the family data is the cheapest one to resolve."""
        self.assertEqual(nm.reference_sites("turn_extraction_results.id"), [])

    def test_render_is_the_inverse_of_the_production_parser(self):
        """The oracle is production. Rendering is proven by feeding every rendered
        value back through `EncodedRef.parse` rather than by comparing to a literal."""
        for ref in inv.ENCODED_REFERENCES:
            seed = json.dumps({"tier": 1, ref.json_key: f"{ref.prefix}7"}) \
                if ref.form == inv.FORM_JSON_FIELD else f"{ref.prefix}7"
            rendered = nm.render_encoded(ref, seed, 4242)
            parsed, malformed = ref.parse(rendered)
            self.assertFalse(malformed, f"{ref.table}.{ref.column}")
            self.assertEqual(parsed, 4242, f"{ref.table}.{ref.column}")

    def test_rendering_a_json_reference_preserves_the_other_fields(self):
        ref = next(r for r in inv.ENCODED_REFERENCES if r.form == inv.FORM_JSON_FIELD)
        rendered = nm.render_encoded(
            ref, json.dumps({"tier": 3, "note": "keep me", ref.json_key: f"{ref.prefix}1"}), 99)
        blob = json.loads(rendered)
        self.assertEqual(blob["tier"], 3)
        self.assertEqual(blob["note"], "keep me")

    def test_a_deliberately_broken_reference_is_caught_by_the_validator(self):
        """The mutation. If the validator cannot fail, its passing means nothing."""
        records = {"turns": [{"id": 1}],
                   "turn_extraction_ledger": [{"id": 1, "turn_key": "turnrow:999"}]}
        dangling = nm.validate_semantic_references(records)
        self.assertTrue(dangling)
        self.assertEqual(dangling[0]["table"], "turn_extraction_ledger")

    def test_an_integer_reference_to_a_missing_turn_is_caught_too(self):
        records = {"turns": [{"id": 1}],
                   "trip_turn_links": [{"id": "x", "user_turn_row_id": 404}]}
        self.assertTrue(nm.validate_semantic_references(records))


class ConflictsRefuseRatherThanResolve(_Fixtures):
    def _codes(self):
        return [r["code"] for r in self.plan.refusals]

    def test_same_key_different_content_refuses(self):
        self.assertIn(nm.R_SAME_KEY_DIFFERENT_CONTENT, self._codes())
        detail = " ".join(r["detail"] for r in self.plan.refusals)
        self.assertIn("profiles", detail)

    def test_a_reference_to_a_NON_corresponding_record_is_still_a_difference(self):
        """THE rule this module got wrong first time, and the more dangerous of the two
        bugs in the first draft.

        Both origins record birthplace 'Williston'. Every ordinary value matches. They
        differ only in which turn they cite — and `turns` has NO defensible
        cross-origin key, so desktop turn 2 and laptop turn 3 have never been shown to
        be the same evidence. The first draft blanked both citations to a sentinel
        before comparing, which declared the two facts identical on the strength of a
        correspondence nobody proved.

        Classification now runs on the REMAPPED rows, so two citations are equal only
        when they resolve to the same merged row. These do not, so the difference
        survives and is reported rather than silently collapsed.
        """
        detail = " ".join(r["detail"] for r in self.plan.refusals)
        self.assertIn("birthplace", detail,
                      "a citation of an unproven-corresponding turn was collapsed")

    def test_both_sides_of_that_row_are_still_carried(self):
        """Refusing is not dropping. Neither fact is lost while a human decides."""
        facts = [r for r in self.plan.merged_records["bio_facts"]
                 if r["field_key"] == "birthplace"]
        self.assertEqual(len(facts), 2)
        self.assertEqual({r["_origin"] for r in facts}, {"desktop", "laptop"})

    def test_a_row_proven_identical_is_represented_once_not_twice(self):
        """`people` carries one row per origin for the same narrator. Inserting both
        would give the merged root two narrators."""
        self.assertEqual(self.plan.carried_rows["people"], 1)
        self.assertEqual(self.plan.merged_records["people"][0]["_origin"], "both")

    def test_a_genuinely_different_value_still_refuses(self):
        detail = " ".join(r["detail"] for r in self.plan.refusals)
        self.assertIn("occupation", detail)

    def test_a_volatile_only_difference_is_not_a_conflict(self):
        """`sessions.updated_at` is the app's open-time write (BACKLOG §5), not
        narrator meaning."""
        detail = " ".join(r["detail"] for r in self.plan.refusals)
        self.assertNotIn("c-both", detail)

    def test_no_winner_is_ever_chosen(self):
        """V1 refuses; it does not resolve. The plan must carry the refusal rather
        than a decision."""
        self.assertTrue(self.plan.refused)

    def test_duplicate_logical_keys_within_one_origin_are_not_collapsed(self):
        """Two `nickname` rows on the desktop, one on the laptop. Correspondence
        within the key is not established, so pairing would be a guess — and a dict
        keyed by the logical key would have kept the last row and deleted the other
        on the quietest possible path."""
        facts = next(v for v in self.plan.keyed_verdicts if v["table"] == "bio_facts")
        self.assertIn(f"{NARRATOR}\x1fnickname", facts["duplicate_keys"])
        self.assertEqual(self.plan.carried_rows["bio_facts"], 7)
        detail = " ".join(r["detail"] for r in self.plan.refusals)
        self.assertNotIn("nickname", detail)

    def test_one_side_only_rows_are_carried_from_both_origins(self):
        sessions = next(v for v in self.plan.keyed_verdicts if v["table"] == "sessions")
        self.assertEqual(sessions["only_desktop"], 1)
        self.assertEqual(sessions["only_laptop"], 1)
        self.assertEqual(sessions["same"], 1)


class NoSafeKeyTablesAreNeverPaired(_Fixtures):
    def test_turns_has_no_cross_origin_key(self):
        self.assertIn("turns", self.plan.no_safe_key_tables)

    def test_every_turn_from_both_origins_is_carried(self):
        """Four turns in, four turns out. `NO_SAFE_CROSS_ORIGIN_KEY` means
        correspondence could not be PROVEN — never that a row may be dropped."""
        self.assertEqual(self.plan.carried_rows["turns"], 4)

    def test_carried_rows_record_which_origin_they_came_from(self):
        """Provenance per record (§5): a narrator's history stays attributable after
        it is combined."""
        turns = self.plan.merged_records["turns"]
        self.assertEqual(sorted(r["_origin"] for r in turns),
                         ["desktop", "desktop", "laptop", "laptop"])
        self.assertEqual({r["_origin_package"] for r in turns}, {PKG_DESKTOP, PKG_LAPTOP})

    def test_the_two_colliding_turns_survive_as_two_distinct_rows(self):
        """Both origins held a turn with id 1 and different words. Neither may be
        dropped, and they may not end up sharing an id."""
        turns = self.plan.merged_records["turns"]
        contents = sorted(r["content"] for r in turns)
        self.assertIn("desktop one", contents)
        self.assertIn("LAPTOP one", contents)
        ids = [r["id"] for r in turns]
        self.assertEqual(len(ids), len(set(ids)))


class Files(_Fixtures):
    def test_identical_bytes_at_the_same_path_are_stored_once(self):
        same = [f for f in self.plan.files_union if f["origin"] == "both"]
        self.assertEqual([f["path"] for f in same], ["memory/archive/photos/same.jpg"])

    def test_one_side_only_files_are_carried_with_their_origin(self):
        byp = {f["path"]: f["origin"] for f in self.plan.files_union}
        self.assertEqual(byp["memory/archive/photos/desk-only.jpg"], "desktop")
        self.assertEqual(byp["memory/archive/photos/lap-only.jpg"], "laptop")

    def test_index_json_is_regenerated_not_reported_as_a_conflict(self):
        """§3b, decided from code: `_register_session_in_index` writes only fields
        already in each session's `meta.json`, so different bytes here are not a
        narrator-content conflict and must not be surfaced as one."""
        self.assertIn(f"{ARCHIVE}/index.json", self.plan.files_regenerate)
        detail = " ".join(r["detail"] for r in self.plan.refusals)
        self.assertNotIn("index.json", detail)

    def test_rolling_summary_is_a_real_divergence_and_refuses(self):
        """§3b: LLM-produced, scored and PRUNED, so neither side is a superset and
        'take the newer last_updated' would silently destroy memory."""
        codes = [r["code"] for r in self.plan.refusals]
        self.assertIn(nm.R_FILE_PATH_DIFFERENT_BYTES, codes)
        detail = " ".join(r["detail"] for r in self.plan.refusals)
        self.assertIn("rolling_summary.json", detail)


class TextPrimaryKeyCollisions(_Fixtures):
    """A physical id collision is not an integer problem.

    The first draft remapped only the three INTEGER surrogates, assuming a TEXT/UUID
    primary key could not collide across installations. The real Christopher comparison
    disproves that on its own evidence: `graph_persons` reports one shared physical id
    with non-identical content, because the product mints graph-person ids
    deterministically from narrator + name.
    """

    def _graph_collision(self):
        return next(c for c in self.plan.physical_collisions
                    if c["table"] == "graph_persons")

    def test_the_collision_hunt_runs_over_every_table_not_just_integers(self):
        tables = {c["table"] for c in self.plan.physical_collisions}
        self.assertIn("graph_persons", tables)
        self.assertEqual(self._graph_collision()["shared_different_content"], ["gp-shared"])

    def test_an_IDENTICAL_row_sharing_a_physical_id_is_STILL_reallocated(self):
        """THE defect this class was extended for, caught in review of `2e10319`.

        `gp-twin` exists on both origins with byte-identical content. The first
        implementation skipped reallocation whenever the bytes matched, so both rows
        were carried unchanged under one `TEXT PRIMARY KEY` — leaving an executor to
        either fail on a duplicate key or drop one of the narrator's rows.

        §1 is explicit: `CONTENT_OVERLAP` does not mean the two rows are the same
        RECORD. `graph_persons` has no defensible cross-origin key at all, so
        correspondence was never established and equal bytes prove nothing about it.
        """
        coll = self._graph_collision()
        self.assertIn("gp-twin", coll["shared_same_content"])
        self.assertIn("gp-twin", coll["must_reallocate"],
                      "an identical-content collision was treated as the same record")
        self.assertEqual(coll["safe_same_record"], [],
                         "a table with no logical key can have no safe shared id")
        self.assertIn("gp-twin", self.plan.remap["graph_persons.id"]["laptop"])

    def test_both_copies_of_the_identical_row_survive(self):
        rows = [r for r in self.plan.merged_records["graph_persons"]
                if r["display_name"] == "Ruth Horne"]
        self.assertEqual(len(rows), 2, "an identical row was silently deduplicated")
        self.assertNotEqual(rows[0]["id"], rows[1]["id"])
        self.assertEqual({r["_origin"] for r in rows}, {"desktop", "laptop"})

    def test_the_colliding_text_id_is_reallocated_for_exactly_one_origin(self):
        mapping = self.plan.remap["graph_persons.id"]
        self.assertEqual(mapping["desktop"], {}, "the lower-ranked origin keeps its id")
        for old in ("gp-shared", "gp-twin"):
            self.assertIn(old, mapping["laptop"])
            self.assertNotEqual(mapping["laptop"][old], old)
        self.assertNotIn("gp-lap", mapping["laptop"], "a non-colliding id was churned")

    def test_every_graph_person_survives_with_a_unique_primary_key(self):
        rows = self.plan.merged_records["graph_persons"]
        self.assertEqual(len(rows), 5)          # 2 desktop + 3 laptop, none collapsed
        ids = [r["id"] for r in rows]
        self.assertEqual(len(ids), len(set(ids)), "a merged root would refuse this insert")
        self.assertEqual(sorted(r["display_name"] for r in rows),
                         ["Janice Horne", "Kenneth Horne", "Kent Horne",
                          "Ruth Horne", "Ruth Horne"])

    def test_the_relationship_follows_the_reallocated_id(self):
        """Both FK columns, not just the one that happens to be listed first."""
        new_id = self.plan.remap["graph_persons.id"]["laptop"]["gp-shared"]
        rel = self.plan.merged_records["graph_relationships"][0]
        self.assertEqual(rel["from_person_id"], new_id)
        self.assertEqual(rel["to_person_id"], "gp-lap")

    def test_no_dangling_graph_reference_after_the_reallocation(self):
        self.assertEqual(
            nm.validate_semantic_references(self.plan.merged_records,
                                            parents=["graph_persons.id"]), [])

    def test_the_reallocated_id_is_deterministic(self):
        again = nm.plan_merge(self.lap, self.desk, label_a="laptop", label_b="desktop")
        self.assertEqual(again.remap["graph_persons.id"],
                         self.plan.remap["graph_persons.id"])

    def test_a_PROVEN_logical_key_still_lets_an_identical_row_be_represented_once(self):
        """The other half of the rule, and it must NOT be weakened by the fix above.

        `people.id` has a measured cross-origin identity (§31: the same id on both
        machines), so a shared id carrying the same logical record and the same content
        IS one row. Reallocating it would give the merged root two narrators.
        """
        people = next(c for c in self.plan.physical_collisions if c["table"] == "people")
        self.assertEqual(people["logical_key_kind"], "declared_logical_key")
        self.assertEqual(people["safe_same_record"], [NARRATOR])
        self.assertEqual(people["must_reallocate"], [])
        self.assertNotIn("people.id", self.plan.remap)
        self.assertEqual(self.plan.carried_rows["people"], 1)

    def test_a_collision_in_a_table_with_no_established_closure_REFUSES(self):
        """Remapping a row whose children cannot be enumerated would orphan them, so
        the planner refuses instead of guessing. `photos.id` has no established
        closure: nothing has read the schema and the writers for it yet."""
        rows_a = {"people": [{"id": NARRATOR, "display_name": "Ada"}],
                  "photos": [{"id": "p-1", "narrator_id": NARRATOR, "caption": "A"}]}
        rows_b = {"people": [{"id": NARRATOR, "display_name": "Ada"}],
                  "photos": [{"id": "p-1", "narrator_id": NARRATOR, "caption": "B"}]}
        with tempfile.TemporaryDirectory() as tmp:
            a = _build_package(Path(tmp) / "a.lorevox.zip", "dddd11112222", rows_a, {"x": b"x"})
            b = _build_package(Path(tmp) / "b.lorevox.zip", "eeee33334444", rows_b, {"y": b"y"})
            plan = nm.plan_merge(a, b, label_a="a", label_b="b")
        codes = [r["code"] for r in plan.refusals]
        self.assertIn(nm.R_UNKNOWN_COLLISION_CLOSURE, codes)
        self.assertNotIn("photos.id", plan.remap)


class ClosureIntegrity(_Fixtures):
    """The independence that makes the parity check meaningful."""

    def test_closure_parity_with_the_independent_evidence_list(self):
        """The merge consumes the PRODUCTION declaration; the comparator keeps its own
        list discovered by reading migrations and writers. They are derived separately
        and must agree. Deriving both from the declaration would make this tautological.
        """
        toc = _load_comparator()
        discovered = {(r["table"], r["column"]) for r in toc.SURROGATE_REFERENCES["turns.id"]}
        merge_sites = {(s.table, s.column) for s in nm.reference_sites("turns.id")}
        self.assertEqual(merge_sites, discovered)
        self.assertEqual(len(merge_sites), 7)

    def test_the_shared_logical_key_registry_has_exactly_one_home(self):
        """The comparator and the merge must not be able to disagree about what makes
        a row the same row."""
        toc = _load_comparator()
        from api.services import cross_origin_identity as x
        self.assertIs(toc.LOGICAL_KEYS, x.LOGICAL_KEYS)
        self.assertIs(toc.VOLATILE_COLUMNS, x.VOLATILE_COLUMNS)

    def test_every_real_sql_fk_into_a_remappable_parent_is_declared(self):
        """The production-boundary companion to `SQL_FK_REFERENCES`.

        SQLite declares these and the inventory deliberately does not, so the merge
        names them locally — which means the list can go stale exactly the way the
        comparator's `declared` booleans did. This re-derives them from the shipped
        schema and refuses any that the merge would not rewrite. It is what makes
        `CLOSURE_ESTABLISHED` a claim rather than an assertion.
        """
        sources = list((REPO / "server" / "code" / "db" / "migrations").glob("*.sql"))
        sources.append(REPO / "server" / "code" / "api" / "db.py")
        table_rx = re.compile(
            r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\)\s*;",
            re.S | re.I)
        found = set()
        for parent in nm.CLOSURE_ESTABLISHED:
            ptable = parent.split(".")[0]
            explicit = re.compile(
                r"FOREIGN\s*KEY\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*"
                r"REFERENCES\s+" + ptable + r"\b", re.S | re.I)
            inline = re.compile(
                r"([A-Za-z_][A-Za-z0-9_]*)\s+(?:INTEGER|TEXT|REAL|BLOB|NUMERIC)"
                r"[^,;()]*REFERENCES\s+" + ptable + r"\b", re.S | re.I)
            for src in sources:
                text = src.read_text(encoding="utf-8", errors="ignore")
                for child, body in table_rx.findall(text):
                    for rx in (explicit, inline):
                        for col in rx.findall(body):
                            found.add((parent, child, col))
        self.assertTrue(found, "the FK scan found nothing — the scan itself is broken")
        declared = {(p, s.table, s.column)
                    for p in nm.CLOSURE_ESTABLISHED for s in nm.reference_sites(p)}
        self.assertEqual(found - declared, set(),
                         f"real SQL FKs the merge would not rewrite: {sorted(found - declared)}")

    def test_the_graph_person_foreign_keys_are_among_them(self):
        """Named explicitly because they are the reason this class exists: they were
        missing from the first draft and only the real comparison exposed the gap."""
        sites = {(s.table, s.column) for s in nm.reference_sites("graph_persons.id")}
        self.assertEqual(sites, {("graph_relationships", "from_person_id"),
                                 ("graph_relationships", "to_person_id")})

    def test_an_established_closure_may_legitimately_be_empty(self):
        """`turn_extraction_results.id` has no referents at all. 'Established and empty'
        and 'unknown' must stay distinguishable — treating unknown as empty is how a
        remap silently orphans rows."""
        self.assertIn("turn_extraction_results.id", nm.CLOSURE_ESTABLISHED)
        self.assertEqual(nm.reference_sites("turn_extraction_results.id"), [])

    def test_every_no_safe_key_table_is_covered_by_the_collision_hunt(self):
        """"Generic physical-primary-key collision hunt" has to mean it.

        The hunt compares whatever `physical_key_columns()` says the key is, which
        defaults to a single `id` column. That is true of every narrator-owned lane in
        the shipped schema today — but "today" is the operative word, and a future
        `something_key TEXT PRIMARY KEY` lane would bypass the hunt silently, which for
        a NO_SAFE_CROSS_ORIGIN_KEY table means two preserved rows colliding on a
        primary key nobody checked.

        So this derives each table's real primary key from the schema and holds the
        declaration against it. A new lane that keys on anything else fails HERE, and
        the fix is an entry in `PHYSICAL_KEYS` rather than a silently unscanned table.
        """
        sources = list((REPO / "server" / "code" / "db" / "migrations").glob("*.sql"))
        sources.append(REPO / "server" / "code" / "api" / "db.py")
        table_rx = re.compile(
            r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\)\s*;",
            re.S | re.I)
        pk_rx = re.compile(
            r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s+(?:TEXT|INTEGER|REAL|BLOB|NUMERIC)"
            r"[^,]*?PRIMARY\s+KEY", re.I | re.M)
        scanned: dict = {}
        for src in sources:
            text = src.read_text(encoding="utf-8", errors="ignore")
            for name, body in table_rx.findall(text):
                # 0018/0021/0034/0037-style rebuilds create `<table>_new` and rename it
                base = re.sub(r"__?new$", "", name)
                pk = pk_rx.findall(body)
                if pk and base not in scanned:
                    scanned[base] = (pk[0],)

        no_safe = [t for t in inv.narrator_owned_tables() if t not in xid.LOGICAL_KEYS]
        self.assertTrue(no_safe, "the inventory returned no no-safe-key lanes")

        unscanned = sorted(t for t in no_safe if t not in scanned)
        self.assertEqual(unscanned, [],
                         f"packaged lanes whose primary key could not be read from the "
                         f"schema — the hunt cannot be proven to cover them: {unscanned}")

        mismatched = {t: (scanned[t], nm.physical_key_columns(t)) for t in no_safe
                      if scanned[t] != nm.physical_key_columns(t)}
        self.assertEqual(mismatched, {},
                         f"tables whose real primary key is not what the collision hunt "
                         f"compares — add a PHYSICAL_KEYS entry: {mismatched}")

    def test_no_table_anywhere_uses_a_composite_primary_key(self):
        """The hunt supports composite keys, but nothing uses one — so if that changes,
        the support is exercised for the first time on real data. Fail instead."""
        sources = list((REPO / "server" / "code" / "db" / "migrations").glob("*.sql"))
        sources.append(REPO / "server" / "code" / "api" / "db.py")
        hits = [p.name for p in sources
                if re.search(r"PRIMARY\s+KEY\s*\(", p.read_text(encoding="utf-8",
                                                                errors="ignore"), re.I)]
        self.assertEqual(hits, [], f"a composite PRIMARY KEY now exists in: {hits}")

    def test_remap_targets_cover_every_narrator_owned_integer_surrogate(self):
        """§3d pinned against the shipped schema. If a future migration gives a
        narrator-owned lane an INTEGER PRIMARY KEY, this fails rather than the merge
        silently carrying two origins' ids into one column."""
        owned = set(inv.narrator_owned_tables())
        targets = {t.split(".")[0] for t in nm.REMAP_TARGETS}
        found = set()
        sources = list((REPO / "server" / "code" / "db" / "migrations").glob("*.sql"))
        sources.append(REPO / "server" / "code" / "api" / "db.py")
        pattern = re.compile(
            r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\)\s*;",
            re.S | re.I)
        for src in sources:
            text = src.read_text(encoding="utf-8", errors="ignore")
            for name, body in pattern.findall(text):
                if name in owned and re.search(r"INTEGER\s+PRIMARY\s+KEY", body, re.I):
                    found.add(name)
        self.assertTrue(found, "the schema scan found nothing — the scan itself is broken")
        self.assertEqual(found - targets, set(),
                         f"narrator-owned integer surrogates missing from REMAP_TARGETS: "
                         f"{sorted(found - targets)}")


class Refusals(_Fixtures):
    def test_two_different_narrators_refuse(self):
        """Same-person equivalence across origins is never inferred here.

        The second package is BUILT for a different narrator rather than having its
        manifest edited afterwards: `lorevox-manifest.json` is written before
        `bag.save(manifests=True)`, so it is covered by the tagmanifest and an edit
        would refuse as a broken bag — the right refusal for the wrong reason, which
        would have left this clause untested.
        """
        stranger = "99999999-9999-9999-9999-999999999999"
        with tempfile.TemporaryDirectory() as tmp:
            other = _build_package(
                Path(tmp) / "other.lorevox.zip", "cccc55556666",
                {"people": [{"id": stranger, "display_name": "Someone Else"}]},
                {"x.txt": b"x"}, narrator_id=stranger)
            self.assertTrue(npkg.validate_package(other).ok)
            with self.assertRaises(nm.MergeRefused) as ctx:
                nm.plan_merge(self.desk, other, label_a="desktop", label_b="other")
            self.assertEqual(ctx.exception.code, nm.R_DIFFERENT_NARRATORS)

    def test_a_package_that_fails_integrity_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "broken.lorevox.zip"
            broken.write_bytes(b"not a zip at all")
            with self.assertRaises(nm.MergeRefused) as ctx:
                nm.load_origin(broken, "broken")
            self.assertEqual(ctx.exception.code, nm.R_PACKAGE_INTEGRITY)


if __name__ == "__main__":
    unittest.main()
