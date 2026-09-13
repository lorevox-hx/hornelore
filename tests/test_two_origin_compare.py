"""WO-LOREVOX-PORTABLE-NARRATOR-01 — the two-origin comparator, proven on synthetic packages.

This tool's output is what the Multi-Origin Merge/Remap work order will be DESIGNED
from, so every claim it makes is proven here against fixtures constructed to contain
the answer. The fixtures are real `.lorevox.zip` files written by this test, not
dictionaries handed to an internal function: the comparator crosses the same zip
boundary it will cross in production.

TWO OF THESE TESTS EXIST BECAUSE THE FIRST DRAFT GOT IT WRONG, and both mistakes
would have corrupted the merge design rather than failing loudly:

  * `test_a_changed_row_is_a_conflict_not_two_one_sided_rows` — the first draft keyed
    `turns` on (conv_id, role, ts, CONTENT). Content in a key means a changed row
    changes its own key, so the one case we are hunting would have been reported as
    two unrelated one-side-only rows.
  * `test_a_uuid_is_not_automatically_a_cross_origin_identity` — the first draft
    treated any UUID `id` as a cross-origin key. UUID syntax is a minting format,
    not shared provenance.

Run:
    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_two_origin_compare
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import two_origin_compare as toc  # noqa: E402

NARRATOR = "11111111-2222-3333-4444-555555555555"


def _pkg(path: Path, package_id: str, records: dict, files: dict) -> Path:
    """A structurally real package: bagit.txt, manifest, JSONL records, and a
    payload manifest whose digests are the real sha256 of the bytes."""
    manifest = {
        "package_id": package_id,
        "narrator_id": NARRATOR,
        "narrator_display_name": "ZZ Synthetic Narrator",
        "created_at": "2026-09-12T00:00:00Z",
        "source_commit": "deadbeef",
        "source_schema_fingerprint": "fp-" + package_id,
        "record_counts_by_lane": {t: len(r) for t, r in records.items()},
        "installation_dependencies": {"interview_plans": ["chat_ws"]},
        "external_person_dependencies": {},
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("bagit.txt", "BagIt-Version: 0.97\n")
        zf.writestr(toc.MANIFEST_NAME, json.dumps(manifest, indent=2))
        for table, rows in records.items():
            zf.writestr(f"{toc.RECORDS_PREFIX}{table}.jsonl",
                        "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
        lines = []
        for rel, content in files.items():
            member = f"{toc.FILES_PREFIX}{rel}"
            zf.writestr(member, content)
            lines.append(f"{hashlib.sha256(content).hexdigest()}  {member}")
        zf.writestr("manifest-sha256.txt", "\n".join(lines) + "\n")
    return path


class _TwoOrigins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        root = Path(cls._tmp.name)

        shared_session = {"conv_id": "conv-1", "person_id": NARRATOR, "title": "Rome", "updated_at": "T1"}

        desktop = {
            "people": [{"id": NARRATOR, "display_name": "ZZ Synthetic Narrator", "role": "subject"}],
            "sessions": [shared_session,
                         {"conv_id": "conv-desktop-only", "person_id": NARRATOR,
                          "title": "Desktop only", "updated_at": "T1"}],
            # same logical key (person_id), DIFFERENT content
            "profiles": [{"person_id": NARRATOR, "profile_json": '{"preferred":"Chris"}', "updated_at": "T1"}],
            # installation-local ids; id 41 means DIFFERENT content on the two sides
            "turns": [
                {"id": 41, "conv_id": "conv-1", "role": "user", "ts": "T1", "content": "desktop forty-one"},
                {"id": 42, "conv_id": "conv-1", "role": "user", "ts": "T2", "content": "shared turn"},
            ],
            "turn_extraction_ledger": [{"id": 5, "narrator_id": NARRATOR, "turn_key": "turnrow:41"}],
            "turn_extraction_results": [{"id": 9, "ledger_id": 5, "narrator_id": NARRATOR,
                                         "turn_key": "turnrow:41"}],
            # duplicate logical key WITHIN one origin (the questionnaire_put pattern)
            "bio_facts": [
                {"id": "f1", "narrator_id": NARRATOR, "field_key": "birth_place", "value": '"Fargo"'},
                {"id": "f2", "narrator_id": NARRATOR, "field_key": "birth_place", "value": '"Fargo"'},
                {"id": "f3", "narrator_id": NARRATOR, "field_key": "full_legal_name", "value": '"Chris"'},
            ],
            # a UUID-keyed table with NO registry entry: must be NO_SAFE_KEY
            "photos": [{"id": "aaaaaaaa-1111-2222-3333-444444444444", "narrator_id": NARRATOR, "file_hash": "h1"},
                       {"id": "dddddddd-1111-2222-3333-444444444444", "narrator_id": NARRATOR, "file_hash": "hd"}],
        }
        laptop = {
            "people": [{"id": NARRATOR, "display_name": "ZZ Synthetic Narrator", "role": "subject"}],
            "sessions": [shared_session,
                         {"conv_id": "conv-laptop-only", "person_id": NARRATOR,
                          "title": "Laptop only", "updated_at": "T9"}],
            "profiles": [{"person_id": NARRATOR, "profile_json": '{"preferred":"Christopher"}', "updated_at": "T9"}],
            "turns": [
                {"id": 41, "conv_id": "conv-1", "role": "user", "ts": "T7", "content": "LAPTOP forty-one"},
                {"id": 42, "conv_id": "conv-1", "role": "user", "ts": "T2", "content": "shared turn"},
            ],
            "turn_extraction_ledger": [{"id": 5, "narrator_id": NARRATOR, "turn_key": "turnrow:41"}],
            "turn_extraction_results": [{"id": 9, "ledger_id": 5, "narrator_id": NARRATOR,
                                         "turn_key": "turnrow:41"}],
            "bio_facts": [
                {"id": "g1", "narrator_id": NARRATOR, "field_key": "birth_place", "value": '"Fargo"'},
                {"id": "g2", "narrator_id": NARRATOR, "field_key": "full_legal_name", "value": '"Christopher Todd"'},
            ],
            "photos": [{"id": "aaaaaaaa-1111-2222-3333-444444444444", "narrator_id": NARRATOR, "file_hash": "h1"},
                       {"id": "bbbbbbbb-1111-2222-3333-444444444444", "narrator_id": NARRATOR, "file_hash": "hb"}],
        }
        shared_bytes = b"IDENTICAL PHOTO BYTES"
        cls.a = _pkg(root / "desktop.lorevox.zip", "aaaa1111", desktop, {
            "memory/archive/photos/same.jpg": shared_bytes,
            "memory/archive/photos/conflict.jpg": b"DESKTOP VERSION",
            "memory/archive/photos/desktop-only.jpg": b"DESKTOP ONLY",
        })
        cls.b = _pkg(root / "laptop.lorevox.zip", "bbbb2222", laptop, {
            "memory/archive/photos/same.jpg": shared_bytes,
            "memory/archive/photos/conflict.jpg": b"LAPTOP VERSION - DIFFERENT",
            "memory/archive/photos/laptop-only.jpg": b"LAPTOP ONLY",
        })
        cls.pa, cls.pb = toc.read_package(cls.a), toc.read_package(cls.b)
        cls.rep = toc.compare_packages(cls.pa, cls.pb, "desktop", "laptop")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def table(self, name):
        for t in self.rep["tables"]:
            if t["table"] == name:
                return t
        self.fail(f"table {name} missing from the report")


# ══════════════════════════════════════════════════════════════════════

class ReadOnly(_TwoOrigins):

    def test_packages_are_byte_identical_after_being_compared(self):
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.a, self.b)}
        toc.compare_packages(toc.read_package(self.a), toc.read_package(self.b), "desktop", "laptop")
        after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.a, self.b)}
        self.assertEqual(before, after)

    def test_package_hashes_are_recorded_in_the_report(self):
        for lbl in ("desktop", "laptop"):
            self.assertRegex(self.rep["origins"][lbl]["package_sha256"], r"^[0-9a-f]{64}$")

    def test_integrity_problems_are_detected_before_contents_are_interpreted(self):
        """A manifest that disagrees with the packaged rows is reported, not ignored."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.zip"
            _pkg(p, "bad", {"people": [{"id": "x"}]}, {})
            with zipfile.ZipFile(p) as zf:
                data = {n: zf.read(n) for n in zf.namelist()}
            man = json.loads(data[toc.MANIFEST_NAME])
            man["record_counts_by_lane"]["people"] = 99      # lie about the count
            data[toc.MANIFEST_NAME] = json.dumps(man).encode()
            with zipfile.ZipFile(p, "w") as zf:
                for n, b in data.items():
                    zf.writestr(n, b)
            got = toc.read_package(p)
        self.assertTrue(any("but 1 rows are packaged" in s for s in got["problems"]), got["problems"])


class KeyModel(_TwoOrigins):
    """Physical key, ownership path and logical key are three separate facts."""

    def test_every_table_reports_all_three_keys_with_a_justification(self):
        for t in self.rep["tables"]:
            self.assertIn("physical_key", t)
            self.assertIn("ownership_path", t)
            self.assertIn("logical_key", t)
            self.assertTrue(t["logical_key_justification"])

    def test_a_uuid_is_not_automatically_a_cross_origin_identity(self):
        """`photos.id` is a UUID and is NOT in the registry. UUID syntax proves a
        minting format, not shared provenance — two installations can mint different
        UUIDs for the same logical photo. Verdict must be refusal, and the shared-id
        count is reported separately as evidence for the merge design to weigh."""
        t = self.table("photos")
        self.assertEqual(t["verdict"], toc.NO_SAFE_KEY)
        self.assertEqual(t["logical_key"], [])
        self.assertIn("UUID", t["physical_key"])
        self.assertEqual(t["shared_physical_ids"]["shared"], 1)
        self.assertIn("not asserted here to mean the same record",
                      t["shared_physical_ids"]["note"])

    def test_a_uuid_earns_a_logical_key_only_with_stated_provenance(self):
        """`people.id` IS a logical key — because §31 MEASURED the same id on both
        machines, not because it is a UUID."""
        t = self.table("people")
        self.assertEqual(t["logical_key"], ["id"])
        self.assertIn("§31", t["logical_key_justification"])

    def test_turns_has_no_defensible_cross_origin_key(self):
        """The shipped `turns` table is (id AUTOINCREMENT, conv_id, role, content, ts,
        anchor_id, meta_json) — db.py:587. There is no stable per-conversation ordinal,
        so there is nothing to key on that is independent of the content."""
        t = self.table("turns")
        self.assertEqual(t["verdict"], toc.NO_SAFE_KEY)
        self.assertIn("INTEGER surrogate", t["physical_key"])
        self.assertEqual(t["logical_key"], [])

    def test_no_logical_key_contains_a_content_column(self):
        """The rule, enforced over the whole registry: a key may never include a value
        being compared, or a changed row changes its own key."""
        contentish = {"content", "value", "text", "body", "profile_json",
                      "questionnaire_json", "title", "summary", "transcript"}
        for table, (cols, _why) in toc.LOGICAL_KEYS.items():
            self.assertFalse(set(cols) & contentish,
                             f"{table} logical key {cols} contains a content column")

    def test_volatile_exclusions_are_table_specific_and_each_states_a_reason(self):
        """Not a blanket "ignore timestamps": a timestamp can be narrator meaning."""
        self.assertIn("profiles", toc.VOLATILE_COLUMNS)
        for table, cols in toc.VOLATILE_COLUMNS.items():
            for col, reason in cols.items():
                self.assertTrue(reason and len(reason) > 10, f"{table}.{col} needs a stated reason")
        # `turns.ts` is NOT excluded anywhere: it can be narrator meaning
        self.assertNotIn("turns", toc.VOLATILE_COLUMNS)


class RowVerdicts(_TwoOrigins):

    def test_identical_row_counted_once_as_shared(self):
        s = self.table("sessions")
        self.assertEqual(s["on_both_identical"], 1)

    def test_a_changed_row_is_a_conflict_not_two_one_sided_rows(self):
        """THE regression this suite exists for. `profiles` has the same logical key
        on both origins and different content; it must be ONE conflict naming the
        column, not two one-side-only rows."""
        p = self.table("profiles")
        self.assertEqual(len(p["on_both_conflicting"]), 1)
        self.assertEqual(p["only_a"], [])
        self.assertEqual(p["only_b"], [])
        c = p["on_both_conflicting"][0]
        self.assertEqual(c["verdict"], toc.SAME_DIFF)
        self.assertEqual(c["columns"], ["profile_json"])
        self.assertIn("Chris", c["a"]["profile_json"])
        self.assertIn("Christopher", c["b"]["profile_json"])

    def test_one_side_only_rows_are_attributed_to_the_right_origin(self):
        s = self.table("sessions")
        self.assertEqual([k["key"] for k in s["only_a"]], [["conv-desktop-only"]])
        self.assertEqual([k["key"] for k in s["only_b"]], [["conv-laptop-only"]])
        self.assertEqual(s["only_a"][0]["verdict"], toc.ONLY_A)
        self.assertEqual(s["only_b"][0]["verdict"], toc.ONLY_B)

    def test_volatile_column_alone_does_not_make_a_row_conflict(self):
        """The shared session differs only in `updated_at`, the app's open-time write."""
        self.assertEqual(self.table("sessions")["on_both_identical"], 1)
        self.assertEqual(self.table("sessions")["on_both_conflicting"], [])

    def test_duplicate_logical_keys_within_one_origin_are_reported(self):
        b = self.table("bio_facts")
        dup = [d for d in b["duplicate_keys_a"] if d["key"] == [NARRATOR, "birth_place"]]
        self.assertEqual(len(dup), 1)
        self.assertEqual(dup[0]["n"], 2)

    def test_a_conflicting_fact_value_is_surfaced_not_silently_unioned(self):
        keys = [c["key"] for c in self.table("bio_facts")["on_both_conflicting"]]
        self.assertIn([NARRATOR, "full_legal_name"], keys)

    def test_no_safe_key_tables_are_multiset_compared_and_never_called_conflicts(self):
        t = self.table("turns")
        self.assertEqual(t["on_both_conflicting"], [])
        m = t["multiset"]
        self.assertEqual(m["identical_content_rows_on_both"], 1)   # the shared turn
        self.assertEqual(m["content_only_in_a"], 1)
        self.assertEqual(m["content_only_in_b"], 1)
        self.assertTrue(m["surrogate_id_excluded_from_content"])
        self.assertIn("NOT identity", m["note"])


class SurrogateCollisionsAndClosure(_TwoOrigins):

    def test_the_same_turn_id_holding_different_content_requires_remap(self):
        c = [x for x in self.rep["surrogate_id_collisions"] if x["table"] == "turns"][0]
        self.assertEqual(c["shared_id_DIFFERENT_content"], 1)
        self.assertIn(41, c["colliding_ids_sample"])
        self.assertEqual(c["verdict"], toc.PHYSICAL_COLLISION)
        self.assertTrue(c["remap_required"])

    def test_a_shared_id_holding_the_same_content_is_not_called_a_collision(self):
        c = [x for x in self.rep["surrogate_id_collisions"] if x["table"] == "turns"][0]
        self.assertEqual(c["shared_id_same_content"], 1)

    def test_the_remap_closure_names_every_reference_including_string_embedded_ones(self):
        """`turn_key` is literally 'turnrow:<turns.id>' (0038:62). A foreign-key graph
        walk cannot see it, so the closure has to declare it or a merge dangles."""
        c = [x for x in self.rep["surrogate_id_collisions"] if x["table"] == "turns"][0]
        refs = {(r["table"], r["column"]): r["form"] for r in c["reference_closure"]}
        self.assertIn(("trip_turn_links", "user_turn_row_id"), refs)
        self.assertIn(("trip_turn_links", "assistant_turn_row_id"), refs)
        self.assertIn(("turn_extraction_ledger", "turn_key"), refs)
        self.assertIn(("turn_extraction_results", "turn_key"), refs)
        self.assertIn(("bio_facts", "source"), refs)
        self.assertIn("TEXT", refs[("turn_extraction_ledger", "turn_key")])
        self.assertIn("JSON", refs[("bio_facts", "source")])

    def test_string_embedded_turn_references_are_measured_not_just_asserted(self):
        tr = self.rep["turnrow_string_references"]
        self.assertEqual(tr["a"], {"turn_extraction_ledger": 1, "turn_extraction_results": 1})
        self.assertEqual(tr["b"], {"turn_extraction_ledger": 1, "turn_extraction_results": 1})
        self.assertEqual(tr["total"], 4)

    def test_the_ledger_surrogate_has_its_own_closure(self):
        c = [x for x in self.rep["surrogate_id_collisions"] if x["table"] == "turn_extraction_ledger"]
        self.assertTrue(c)
        refs = {(r["table"], r["column"]) for r in c[0]["reference_closure"]}
        self.assertIn(("turn_extraction_results", "ledger_id"), refs)


class RemapClosure(_TwoOrigins):
    """The closure is built by READING the shipped migrations and writers. A
    `PRAGMA foreign_key_list` walk finds none of the TEXT/JSON forms and only two
    of the seven — which is exactly why a merge can pass `foreign_key_check` and
    still be internally broken."""

    def test_the_closure_covers_all_seven_storage_sites(self):
        refs = {(r["table"], r["column"]) for r in toc.SURROGATE_REFERENCES["turns.id"]}
        for expected in (("trip_turn_links", "user_turn_row_id"),
                         ("trip_turn_links", "assistant_turn_row_id"),
                         ("story_candidates", "source_user_turn_row_id"),
                         ("story_candidates", "completed_assistant_turn_row_id"),
                         ("turn_extraction_ledger", "turn_key"),
                         ("turn_extraction_results", "turn_key"),
                         ("bio_facts", "source")):
            self.assertIn(expected, refs)

    def test_every_declared_reference_record_satisfies_the_schema(self):
        """THE regression this pins. An earlier revision renamed `kind` to `form` in
        the declaration but not in the renderer, and the mismatch surfaced as a
        KeyError in the middle of a real family comparison. The renderer must never
        guess at a record's fields, and the producer must refuse to build a
        malformed one."""
        for surrogate, refs in toc.SURROGATE_REFERENCES.items():
            for r in refs:
                toc.validate_reference_record(r)          # raises if a field is missing
                for f in toc.REFERENCE_RECORD_FIELDS:
                    self.assertIn(f, r, f"{surrogate} {r.get('table')}.{r.get('column')} missing {f}")

    def test_the_producer_refuses_to_build_a_malformed_reference_record(self):
        with self.assertRaises(ValueError):
            toc._ref("t", "c", "", True, "cite")          # empty form
        with self.assertRaises(ValueError):
            toc._ref("t", "c", "INTEGER column", True, "")  # no citation

    def test_every_emitted_audit_record_satisfies_the_audit_schema(self):
        for lbl in ("desktop", "laptop"):
            for c in self.rep["reference_integrity"][lbl]["checks"]:
                toc.validate_reference_record(c, audit=True)

    def test_the_renderer_reads_only_schema_fields(self):
        """Rendering the real report must not raise — the failure mode that stopped
        Christopher's comparison halfway through a live run."""
        md = toc.summarize(self.rep, "desktop", "laptop")
        self.assertIn("Remap closure for `turns.id`", md)
        self.assertIn("Reference integrity inside each package", md)

    def test_the_undeclared_references_are_flagged_as_undeclared(self):
        """`story_candidates` turn columns (0047) are bare INTEGERs with no SQL FK and
        no COLUMN_ONLY_REFERENCES entry, so the exporter's §30 guard does not check
        them. Recording that is the point."""
        by = {(r["table"], r["column"]): r["declared"] for r in toc.SURROGATE_REFERENCES["turns.id"]}
        self.assertFalse(by[("story_candidates", "source_user_turn_row_id")])
        self.assertFalse(by[("story_candidates", "completed_assistant_turn_row_id")])
        self.assertFalse(by[("turn_extraction_ledger", "turn_key")])
        self.assertFalse(by[("bio_facts", "source")])
        self.assertTrue(by[("trip_turn_links", "user_turn_row_id")])

    def test_a_package_whose_turn_references_all_resolve_is_reported_clean(self):
        ri = self.rep["reference_integrity"]["desktop"]
        self.assertEqual(ri["total_dangling"], 0, ri["checks"])
        self.assertIn("resolve inside the package", ri["verdict"])

    def test_a_dangling_reference_in_an_UNDECLARED_column_is_caught(self):
        """The case the exporter's guard would miss: a story candidate pointing at a
        turn that is not in the package. Read-only detection, and a finding either way."""
        recs = {
            "turns": [{"id": 1, "conv_id": "c", "role": "user", "ts": "T", "content": "x"}],
            "story_candidates": [{"id": "s1", "narrator_id": NARRATOR,
                                  "source_user_turn_row_id": 999,          # not packaged
                                  "completed_assistant_turn_row_id": 1}],
            "bio_facts": [{"id": "b1", "narrator_id": NARRATOR, "field_key": "k",
                           "source": json.dumps({"turn_key": "turnrow:777"})}],  # not packaged
        }
        with tempfile.TemporaryDirectory() as d:
            p = toc.read_package(_pkg(Path(d) / "x.zip", "x", recs, {}))
        ri = toc.reference_integrity_audit(p)
        self.assertEqual(ri["total_dangling"], 2, ri["checks"])
        self.assertIn("DANGLING", ri["verdict"])
        for c in ri["checks"]:
            toc.validate_reference_record(c, audit=True)
        got = {(c["table"], c["column"]): c["dangling"] for c in ri["checks"]}
        self.assertEqual(got[("story_candidates", "source_user_turn_row_id")], 1)
        self.assertEqual(got[("bio_facts", "source")], 1)
        self.assertEqual(got[("story_candidates", "completed_assistant_turn_row_id")], 0)

    def test_json_embedded_references_are_parsed_not_pattern_matched_on_the_whole_blob(self):
        recs = {"turns": [{"id": 5, "conv_id": "c", "role": "user", "ts": "T", "content": "x"}],
                "bio_facts": [{"id": "b", "narrator_id": NARRATOR, "field_key": "k",
                               "source": json.dumps({"tier": 1, "turn_key": "turnrow:5"})}]}
        with tempfile.TemporaryDirectory() as d:
            p = toc.read_package(_pkg(Path(d) / "y.zip", "y", recs, {}))
        ri = toc.reference_integrity_audit(p)
        got = {(c["table"], c["column"]): c for c in ri["checks"]}
        self.assertEqual(got[("bio_facts", "source")]["references_found"], 1)
        self.assertEqual(ri["total_dangling"], 0)


class Files(_TwoOrigins):

    def test_same_path_same_bytes_is_shared(self):
        self.assertEqual(self.rep["files"]["same_path_same_hash"], 1)

    def test_same_path_different_bytes_is_a_conflict_naming_the_path(self):
        f = self.rep["files"]
        self.assertEqual(f["same_path_DIFFERENT_hash"], 1)
        self.assertIn("memory/archive/photos/conflict.jpg", f["same_path_different_hash_paths"])

    def test_one_side_only_files_are_attributed(self):
        f = self.rep["files"]
        self.assertEqual(f["only_a"], ["memory/archive/photos/desktop-only.jpg"])
        self.assertEqual(f["only_b"], ["memory/archive/photos/laptop-only.jpg"])

    def test_hashes_come_from_the_bag_manifest_not_from_rehashing(self):
        self.assertEqual(self.pa["files"]["memory/archive/photos/same.jpg"],
                         hashlib.sha256(b"IDENTICAL PHOTO BYTES").hexdigest())
        self.assertIn("manifest-sha256.txt", self.rep["files"]["hash_source"])


class ReportShape(_TwoOrigins):

    def test_markdown_aggregates_before_it_lists_examples(self):
        md = toc.summarize(self.rep, "desktop", "laptop")
        self.assertIn("## Key model", md)
        self.assertIn("## Keyed tables", md)
        self.assertIn("## No safe cross-origin key", md)
        self.assertIn("## What this means for Merge/Remap", md)
        self.assertIn("It is not a merge", md)

    def test_the_summary_states_the_remap_verdict(self):
        md = toc.summarize(self.rep, "desktop", "laptop")
        self.assertIn("**Remap required:** YES", md)


class DifferentNarratorIdIsNotAnIdentityJudgement(unittest.TestCase):
    def test_the_report_refuses_to_conclude_sameness_or_difference_of_person(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            a = toc.read_package(_pkg(d / "a.zip", "a", {"people": [{"id": "x"}]}, {}))
            b = toc.read_package(_pkg(d / "b.zip", "b", {"people": [{"id": "y"}]}, {}))
            b["manifest"]["narrator_id"] = "99999999-9999-9999-9999-999999999999"
            rep = toc.compare_packages(a, b, "desktop", "laptop")
        self.assertFalse(rep["same_narrator_id"])
        note = rep["identity_note"].lower()
        self.assertIn("not the same narrator record", note)
        self.assertIn("same person", note)
        self.assertIn("must not be assumed", note)


if __name__ == "__main__":
    unittest.main()
