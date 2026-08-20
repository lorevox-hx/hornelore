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
        # REPOINTED 2026-08-20: `plan` and `con` were added so the plan
        # can be BUILT before the database authority is destroyed and
        # RE-EXECUTED afterwards. Neither is a path. The property is
        # unchanged: no parameter names a directory.
        self.assertEqual(list(sig.parameters),
                         ["person_id", "root", "plan", "con"])
        for _key, parts in _ne.FIXED_TARGETS:
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


class AnInternalSymlinkCannotDeleteAnotherNarratorTests(_Base):
    """THE DEFECT REVIEW FOUND, and the reason the containment check
    was necessary but nowhere near sufficient.

    `Path.resolve()` answers where a path ENDS UP; it does not answer
    what it passed through. So

        stories-captured/A -> stories-captured/B

    resolved to a directory INSIDE the data root, satisfied
    containment, and `rmtree` then deleted narrator B. Every component
    is `lstat`-ed now and a link is refused wherever it points.
    """

    def _link(self, parts, other):
        holder = self.root.joinpath(*parts)
        holder.mkdir(parents=True, exist_ok=True)
        victim = holder / other
        victim.mkdir(parents=True, exist_ok=True)
        (victim / "transcript.txt").write_text(
            "narrator B's own words", encoding="utf-8")
        try:
            (holder / self.pid).symlink_to(victim, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable in this environment")
        return victim

    def test_narrator_b_survives_byte_identical(self):
        other = str(uuid.uuid4())
        victim = self._link(("stories-captured",), other)
        before = (victim / "transcript.txt").read_bytes()
        res = _ne.erase_person_files(self.pid, root=self.root)
        self.assertTrue(victim.exists(), "narrator B's directory was deleted")
        self.assertEqual((victim / "transcript.txt").read_bytes(), before)
        self.assertIn("stories_captured", [f["target"] for f in res.failed])
        self.assertFalse(res.active_data_erased)

    def test_the_refusal_says_it_is_a_symlink(self):
        self._link(("memory", "archive", "people"), str(uuid.uuid4()))
        res = _ne.erase_person_files(self.pid, root=self.root)
        why = [f for f in res.failed if f["target"] == "memory_archive"][0]
        self.assertEqual(why["reason"], "refused")
        self.assertIn("symlink", why["detail"])

    def test_a_link_on_an_INTERMEDIATE_component_is_refused_too(self):
        """Not only the last segment. A link two levels up carries
        every target beneath it somewhere else."""
        other = self.root / "elsewhere"
        (other / "people").mkdir(parents=True)
        (other / "people" / self.pid).mkdir()
        (other / "people" / self.pid / "keep.txt").write_text(
            "not this narrator's", encoding="utf-8")
        archive = self.root / "memory" / "archive"
        archive.mkdir(parents=True)
        try:
            (archive / "people").symlink_to(other / "people",
                                            target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable in this environment")
        res = _ne.erase_person_files(self.pid, root=self.root)
        self.assertTrue((other / "people" / self.pid / "keep.txt").exists())
        self.assertIn("memory_archive", [f["target"] for f in res.failed])

    def test_a_refused_target_is_reported_as_residue(self):
        self._link(("stories-captured",), str(uuid.uuid4()))
        residue = _ne.person_file_residue(self.pid, root=self.root)
        self.assertIn("stories_captured", [r["target"] for r in residue])


class TheExplicitRootIsValidatedTooTests(_Base):
    """Internal code deserves the same safety contract as the
    environment. The `root=` argument used to skip these checks
    entirely, which meant a caller inside a `rmtree` had weaker
    guarantees than a deployment did."""

    def test_a_relative_explicit_root_refuses(self):
        with self.assertRaises(_ne.UnsafeDataRoot):
            _ne.erase_person_files(self.pid, root="data")

    def test_the_filesystem_root_refuses(self):
        with self.assertRaises(_ne.UnsafeDataRoot):
            _ne.erase_person_files(self.pid, root=os.path.abspath(os.sep))

    def test_a_nonexistent_explicit_root_refuses(self):
        with self.assertRaises(_ne.UnsafeDataRoot):
            _ne.erase_person_files(self.pid, root=str(self.root / "nope"))

    def test_an_empty_explicit_root_refuses(self):
        with self.assertRaises(_ne.UnsafeDataRoot):
            _ne.erase_person_files(self.pid, root="")


class TheHistoricalStoresAreReportedNotErasedTests(_Base):

    def test_backups_are_named_and_left_alone(self):
        b = self.root / "backups"
        b.mkdir()
        (b / "2026-08-01.sqlite3").write_text("snapshot", encoding="utf-8")
        res = _ne.erase_person_files(self.pid, root=self.root)
        self.assertTrue((b / "2026-08-01.sqlite3").exists(),
                        "a shared backup was rewritten by a per-person delete")
        self.assertEqual([h["store"] for h in res.historical], ["backups"])
        self.assertTrue(res.historical_residue_present)
        self.assertTrue(res.active_data_erased,
                        "historical residue is not an active-erasure failure")

    def test_exports_are_named_too(self):
        e = self.root / "exports"
        e.mkdir()
        (e / "memoir.docx").write_bytes(b"PK\x03\x04")
        res = _ne.erase_person_files(self.pid, root=self.root)
        self.assertIn("exports", [h["store"] for h in res.historical])

    def test_no_backups_means_no_historical_residue(self):
        res = _ne.erase_person_files(self.pid, root=self.root)
        self.assertEqual(res.historical, [])
        self.assertFalse(res.historical_residue_present)


class TheTranslationCacheIsPurgedTests(_Base):
    """Shared, disposable, and NOT attributable per narrator: entries
    are keyed by content hash, so this person's translated sentences
    cannot be selected out. It is a cache, so the honest answer is to
    drop all of it rather than leave narrator text nobody can trace."""

    def test_the_whole_cache_goes(self):
        c = self.root / "translations-cache"
        c.mkdir()
        (c / "deadbeef.json").write_text("translated narrator text",
                                         encoding="utf-8")
        res = _ne.erase_person_files(self.pid, root=self.root)
        self.assertFalse(c.exists())
        self.assertIn("translation_cache", [r["target"] for r in res.removed])


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

    def test_the_inventory_covers_every_named_store(self):
        """EXTENDED 2026-08-20 after review found the inventory was a
        quarter of the surface: personal media archive, media uploads,
        trip-source documents, import staging and legacy agent
        transcript exports all held narrator content and none were
        named."""
        keys = {k for k, _ in _ne.FIXED_TARGETS}
        for required in ("memory_archive", "stories_captured",
                         "photo_archive", "kawa_segments",
                         "personal_media_archive", "media_uploads"):
            self.assertIn(required, keys)
        # …and the DB-derived lanes are in the planner.
        import inspect
        planner = inspect.getsource(_ne._dynamic_plan)
        for lane in ("trip_sources", "import_batch", "sessions"):
            self.assertIn(lane, planner)


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

    def test_media_uploads_are_now_ERASED_not_retained(self):
        """REVERSED 2026-08-20 by Chris's ruling.

        This test previously asserted the opposite -- that media was
        reported as retained-by-design and left on disk, because
        `media.person_id` is ON DELETE SET NULL. The ruling: that may
        remain as a database fallback, but a confirmed hard erasure
        must not preserve identifiable photographs. The old assertions
        were:

            assertEqual([r["target"] for r in res.retained],
                        ["media_uploads"])
            assertFalse(res.ok)
        """
        f = self._seed(("media",), name="upload.jpg")
        res = _ne.erase_person_files(self.pid, root=self.root)
        self.assertIn("media_uploads", [r["target"] for r in res.removed])
        self.assertFalse((f / "upload.jpg").exists())
        self.assertTrue(res.active_data_erased)

    def test_the_personal_media_archive_goes_too(self):
        f = self._seed(("media", "archive", "people"), name="document.pdf")
        _ne.erase_person_files(self.pid, root=self.root)
        self.assertFalse((f / "document.pdf").exists())

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
