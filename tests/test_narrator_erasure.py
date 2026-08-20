"""Deletion erases the narrator's files, or says it did not.

WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01 — deletion integrity
(2026-08-20).

THE DEFECT. The synthetic live acceptance hard-deleted a narrator,
received HTTP 200 `{"status": "hard_deleted"}`, and found eight files
still on disk -- five of them containing the narrator's verbatim
speech. Only the Kawa directory was removed, because it was the only
one anybody had named. The database was clean and the answer was
truthful about the database and about nothing else.

The tests here are in three groups, and the order is the argument:

  * SAFETY first -- a deletion path that can be pointed at the wrong
    directory is worse than one that under-deletes;
  * COMPLETENESS second -- every narrator-owned location goes;
  * HONESTY third -- what survives is named, and a partial result may
    never be reported as complete.

Run with:

    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_narrator_erasure
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
for _p in (str(_SERVER_CODE), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.services import narrator_erasure as _ne  # noqa: E402


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)
        self.pid = str(uuid.uuid4())
        self._orig_env = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(self.root)
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        if self._orig_env is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._orig_env

    def _seed(self, parts, name="transcript.txt", body="narrator speech"):
        d = self.root.joinpath(*parts, self.pid, "inner")
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(body, encoding="utf-8")
        return d


# ── Safety ──────────────────────────────────────────────────────────────

class NoCallerCanNameATargetTests(_Base):

    def test_a_traversal_id_is_refused_before_any_path_is_built(self):
        for bad in ("../../etc", "..", "a/b", "/absolute", "", "  ",
                    "x", "with\x00nul", ".hidden"):
            with self.subTest(bad=bad):
                with self.assertRaises(_ne.UnsafePersonId):
                    _ne.erase_person_files(bad, root=self.root)

    def test_a_normal_uuid_is_accepted(self):
        res = _ne.erase_person_files(self.pid, root=self.root)
        self.assertTrue(res.ok)

    def test_a_harness_style_id_is_accepted(self):
        res = _ne.erase_person_files(
            "harness-test-gate7p2-" + uuid.uuid4().hex, root=self.root)
        self.assertTrue(res.ok)

    def test_the_targets_are_derived_and_take_no_path_argument(self):
        """A path parameter is the one way this could delete the wrong
        thing, so its ABSENCE is the property under test."""
        import inspect
        sig = inspect.signature(_ne.erase_person_files)
        self.assertEqual(list(sig.parameters), ["person_id", "root"],
                         "erasure takes an id and a test root, nothing else")
        for _key, parts in _ne.ERASURE_TARGETS:
            with self.subTest(parts=parts):
                self.assertNotIn(self.pid, parts,
                                 "a target template must not embed an id")

    def test_a_symlink_that_escapes_the_root_is_refused(self):
        """The id pattern cannot see a symlink. The containment check
        runs on the RESOLVED path for exactly this case."""
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(outside,
                                                            ignore_errors=True))
        (outside / "keep.txt").write_text("not this narrator's", encoding="utf-8")
        holder = self.root / "memory" / "archive" / "people"
        holder.mkdir(parents=True, exist_ok=True)
        try:
            (holder / self.pid).symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable in this environment")
        res = _ne.erase_person_files(self.pid, root=self.root)
        self.assertTrue((outside / "keep.txt").exists(),
                        "a symlinked target outside the root was followed")
        self.assertTrue(any(f["target"] == "memory_archive" for f in res.failed))
        self.assertFalse(res.ok)


class TheDataRootIsValidatedTests(_Base):

    def test_an_unset_data_dir_refuses(self):
        os.environ.pop("DATA_DIR", None)
        with self.assertRaises(_ne.UnsafeDataRoot):
            _ne.data_root()

    def test_a_relative_data_dir_refuses(self):
        os.environ["DATA_DIR"] = "data"
        with self.assertRaises(_ne.UnsafeDataRoot):
            _ne.data_root()

    def test_the_filesystem_root_refuses(self):
        os.environ["DATA_DIR"] = os.path.abspath(os.sep)
        with self.assertRaises(_ne.UnsafeDataRoot):
            _ne.data_root()

    def test_a_missing_directory_refuses(self):
        os.environ["DATA_DIR"] = str(self.root / "nope")
        with self.assertRaises(_ne.UnsafeDataRoot):
            _ne.data_root()

    def test_a_real_absolute_directory_is_accepted(self):
        self.assertEqual(_ne.data_root(), self.root)


# ── Completeness ────────────────────────────────────────────────────────

class EveryNarratorOwnedLocationGoesTests(_Base):

    def test_the_five_live_locations_are_all_erased(self):
        """The measured live residue, reproduced and then removed."""
        self._seed(("memory", "archive", "people"))
        self._seed(("stories-captured",))
        self._seed(("memory", "archive", "photos"), name="original.jpg")
        self._seed(("kawa", "people"), name="segment.json")
        res = _ne.erase_person_files(self.pid, root=self.root)
        self.assertTrue(res.ok, res.as_dict())
        self.assertEqual(sorted(r["target"] for r in res.removed),
                         ["kawa_segments", "memory_archive", "photo_archive",
                          "stories_captured"])
        self.assertEqual(res.files_removed, 4)
        self.assertEqual(_ne.person_file_residue(self.pid, root=self.root), [])

    def test_the_transcript_is_really_gone_from_disk(self):
        d = self._seed(("memory", "archive", "people"),
                       body="the Wabash River in Terre Haute")
        f = d / "transcript.txt"
        self.assertTrue(f.exists())
        _ne.erase_person_files(self.pid, root=self.root)
        self.assertFalse(f.exists())
        self.assertFalse(f.parent.parent.exists())

    def test_another_narrators_files_are_untouched(self):
        other = str(uuid.uuid4())
        keep = self.root / "memory" / "archive" / "people" / other
        keep.mkdir(parents=True)
        (keep / "transcript.txt").write_text("someone else", encoding="utf-8")
        self._seed(("memory", "archive", "people"))
        _ne.erase_person_files(self.pid, root=self.root)
        self.assertTrue((keep / "transcript.txt").exists())

    def test_the_inventory_covers_the_archive_and_the_stories(self):
        keys = {k for k, _ in _ne.ERASURE_TARGETS}
        for required in ("memory_archive", "stories_captured"):
            self.assertIn(required, keys,
                          "the two locations the live run found still on "
                          "disk must be in the inventory")


class ErasureIsIdempotentTests(_Base):

    def test_a_second_run_is_clean_not_an_error(self):
        self._seed(("stories-captured",))
        first = _ne.erase_person_files(self.pid, root=self.root)
        second = _ne.erase_person_files(self.pid, root=self.root)
        self.assertTrue(first.ok)
        self.assertTrue(second.ok, "a repeat run must not report failure")
        self.assertIn("stories_captured", second.absent)
        self.assertEqual(second.removed, [])

    def test_a_partial_failure_can_be_retried_to_completion(self):
        """One target locked, the rest removed; on the retry the
        already-removed ones are `absent` and the last one goes."""
        import shutil as _shutil
        self._seed(("memory", "archive", "people"))
        self._seed(("stories-captured",))
        real = _shutil.rmtree
        state = {"boom": True}

        def _flaky(path, *a, **kw):
            if state["boom"] and "stories-captured" in str(path):
                raise OSError("locked")
            return real(path, *a, **kw)

        _ne.shutil.rmtree = _flaky
        self.addCleanup(setattr, _ne.shutil, "rmtree", real)
        first = _ne.erase_person_files(self.pid, root=self.root)
        self.assertFalse(first.ok)
        self.assertEqual([f["target"] for f in first.failed],
                         ["stories_captured"])
        self.assertEqual([r["target"] for r in first.removed],
                         ["memory_archive"])
        state["boom"] = False
        second = _ne.erase_person_files(self.pid, root=self.root)
        self.assertTrue(second.ok)
        self.assertIn("memory_archive", second.absent)
        self.assertEqual([r["target"] for r in second.removed],
                         ["stories_captured"])
        self.assertEqual(_ne.person_file_residue(self.pid, root=self.root), [])


# ── Honesty ─────────────────────────────────────────────────────────────

class WhatSurvivesIsNamedTests(_Base):

    def test_media_is_reported_as_retained_and_as_residue(self):
        """Retained-by-design still means narrator bytes on disk.

        It appears in BOTH lists on purpose: `retained_by_design`
        explains the decision, `residue` is what makes `ok` False so no
        caller can answer "complete" while the files are there.
        """
        self._seed(("media",), name="upload.jpg")
        res = _ne.erase_person_files(self.pid, root=self.root)
        self.assertEqual([r["target"] for r in res.retained], ["media_uploads"])
        self.assertEqual([r["target"] for r in res.residue], ["media_uploads"])
        self.assertFalse(res.ok)
        self.assertIn("SET NULL", res.retained[0]["reason"])

    def test_no_media_means_nothing_is_claimed_to_be_retained(self):
        res = _ne.erase_person_files(self.pid, root=self.root)
        self.assertEqual(res.retained, [])
        self.assertTrue(res.ok)

    def test_a_failure_is_reported_rather_than_swallowed(self):
        import shutil as _shutil
        self._seed(("memory", "archive", "people"))
        real = _shutil.rmtree
        _ne.shutil.rmtree = lambda *a, **kw: (_ for _ in ()).throw(
            OSError("permission denied"))
        self.addCleanup(setattr, _ne.shutil, "rmtree", real)
        res = _ne.erase_person_files(self.pid, root=self.root)
        self.assertFalse(res.ok)
        self.assertEqual(res.failed[0]["target"], "memory_archive")
        self.assertEqual(res.failed[0]["reason"], "OSError")

    def test_the_residue_reader_does_not_trust_the_erasure_report(self):
        """`person_file_residue` re-reads the disk.

        A harness that checked only the response body would have passed
        on the very defect this module closes -- the body said
        `hard_deleted` and the files were there.
        """
        self._seed(("memory", "archive", "people"))
        before = _ne.person_file_residue(self.pid, root=self.root)
        self.assertEqual([r["target"] for r in before], ["memory_archive"])
        self.assertEqual(before[0]["files"], 1)
        _ne.erase_person_files(self.pid, root=self.root)
        self.assertEqual(_ne.person_file_residue(self.pid, root=self.root), [])
