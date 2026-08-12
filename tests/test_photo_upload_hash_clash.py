"""S2 — photo upload vs the table-wide UNIQUE(file_hash) constraint.

SECURITY/STABILITY-REVIEW-2026-08-12 finding S2. ``photos.file_hash``
carries a table-wide UNIQUE constraint (migration 0001) and soft-deleted
rows keep their hash, but the upload dedup check was narrator-scoped and
live-rows-only. Two real operator workflows therefore fell through it
into an unhandled IntegrityError — HTTP 500 with no explanation — AND
left an orphaned image in the archive, because ``store_photo_file()``
MOVES the bytes before the row is inserted:

  (a) re-uploading a photo that was soft-deleted — the exact recovery
      path BUG-PHOTO-DEDUP-IGNORES-SOFTDELETE was fixed to enable;
  (b) a second narrator uploading a file the first narrator already has.

``import_repository.candidate_promote`` already refused both by name;
this suite covers that guard ported to the upload lane, plus the
cleanup net for the residual check-then-insert race.

BEHAVIORAL, not source-shape: every test drives the real route function
with real bytes against a real sqlite DB and a real archive directory,
then asserts on the DB rows and the filesystem. Per repo doctrine a
source scan would not have caught this defect — the bug lives in the
relationship between the dedup query and the schema constraint.

Run per-module:
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_photo_upload_hash_clash

Import strategy is copied from tests/test_photo_show_next_scope_failure.py:
the photos router uses `from ...services...` relative imports that only
resolve under the production package layout, so we mirror production and
import `code.api.routers.photos`.
"""
from __future__ import annotations

# (asyncio no longer needed — requests go through TestClient)
import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_REPO_ROOT / "server" / "code"),
           str(_REPO_ROOT / "server"),
           str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# The stdlib `code` module shadows the production `server/code` package
# if something imported it first (pdb does).
if "code" in sys.modules and not hasattr(sys.modules["code"], "__path__"):
    del sys.modules["code"]

# Sibling suites install fake fastapi/pydantic stubs and never remove
# them; the real packages are needed here.
for _stub_name in ("fastapi", "pydantic"):
    _stub = sys.modules.get(_stub_name)
    if _stub is not None and not hasattr(_stub, "__path__"):
        for _k in [k for k in list(sys.modules)
                   if k == _stub_name or k.startswith(_stub_name + ".")]:
            del sys.modules[_k]

# Point DATA_DIR at a temp tree BEFORE importing anything that resolves
# it, so neither the live DB nor the live archive is touched.
_TMP = tempfile.mkdtemp(prefix="hl-s2-")
os.environ["DATA_DIR"] = _TMP
os.environ["HORNELORE_PHOTO_ENABLED"] = "1"
os.environ["HORNELORE_PHOTO_INTAKE"] = "0"   # skip EXIF/Pillow work

for _m in [m for m in list(sys.modules)
           if m.endswith("api.db") or m == "api.db"]:
    del sys.modules[_m]

from code.api.routers import photos as photos_router  # noqa: E402
from code.services.photos import repository as photo_repo  # noqa: E402
from code.services.photo_intake.storage import photo_dir_for  # noqa: E402
import code.api.db as db  # noqa: E402


# A 1x1 PNG — real image bytes, so nothing downstream has to be faked.
_PNG_A = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
_PNG_B = _PNG_A[:-4] + b"ZZZZ"   # different bytes -> different hash


# A real multipart request through TestClient, NOT a direct call to the
# route function: calling it directly leaves FastAPI's Form(...) defaults
# as FieldInfo objects, which the enum validator then rejects — an
# artifact of the harness rather than the product. Going over the wire
# also exercises form parsing and the JSONResponse status codes exactly
# as the browser does.
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_app = FastAPI()
# The router already declares prefix="/api/photos"; adding another here
# would double it and every request would 404.
_app.include_router(photos_router.router)
_client = TestClient(_app)


def _upload(data: bytes, narrator_id: str, filename: str = "x.png"):
    resp = _client.post(
        "/api/photos",
        files={"file": (filename, data, "image/png")},
        data={"narrator_id": narrator_id,
              "uploaded_by_user_id": "operator-test"},
    )
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, {"_raw": resp.text[:400]}


def _ensure_person(person_id: str) -> None:
    """photos.narrator_id REFERENCES people(id) since migration 0037, so
    a test narrator must be a real row or every insert fails the FK."""
    con = db._connect()
    try:
        now = db._now_iso()
        con.execute(
            "INSERT OR IGNORE INTO people"
            " (id, display_name, created_at, updated_at) VALUES (?,?,?,?)",
            (person_id, person_id, now, now))
        con.commit()
    finally:
        con.close()


def _photo_rows():
    con = db._connect()
    try:
        return con.execute(
            "SELECT id, narrator_id, file_hash, deleted_at FROM photos"
        ).fetchall()
    finally:
        con.close()


def _archive_dirs(narrator_id: str):
    root = Path(_TMP) / "memory" / "archive" / "photos" / narrator_id
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


class UploadHashClashTest(unittest.TestCase):
    NARRATOR = "narrator-one"
    OTHER = "narrator-two"
    _PEOPLE = ("narrator-one", "narrator-two")

    def setUp(self):
        db.init_db()
        con = db._connect()
        try:
            con.execute("DELETE FROM photos")
            con.commit()
        finally:
            con.close()
        for _nid in getattr(self, "_PEOPLE", ()):
            _ensure_person(_nid)
        for nid in (self.NARRATOR, self.OTHER):
            root = Path(_TMP) / "memory" / "archive" / "photos" / nid
            if root.is_dir():
                import shutil
                shutil.rmtree(root, ignore_errors=True)

    # ---- happy path stays exactly as it was -------------------------

    def test_first_upload_succeeds(self):
        status, body = _upload(_PNG_A, self.NARRATOR)
        self.assertIn(status, (200, 201), body)
        self.assertEqual(len(_photo_rows()), 1)
        self.assertEqual(len(_archive_dirs(self.NARRATOR)), 1)

    def test_two_different_files_both_succeed(self):
        _upload(_PNG_A, self.NARRATOR)
        status, body = _upload(_PNG_B, self.NARRATOR, "y.png")
        self.assertIn(status, (200, 201), body)
        self.assertEqual(len(_photo_rows()), 2)

    def test_same_live_photo_still_returns_plain_duplicate(self):
        """Pre-existing narrator-scoped behaviour must not change."""
        _upload(_PNG_A, self.NARRATOR)
        status, body = _upload(_PNG_A, self.NARRATOR)
        self.assertEqual(status, 409)
        self.assertEqual(body.get("error"), "duplicate_file")
        self.assertEqual(len(_photo_rows()), 1)

    # ---- workflow (a): re-upload after soft delete ------------------

    def test_reupload_of_soft_deleted_photo_is_named_not_500(self):
        _, first = _upload(_PNG_A, self.NARRATOR)
        photo_id = first.get("id") or first.get("photo", {}).get("id")
        photo_repo.soft_delete_photo(photo_id, actor_id="operator-test")

        status, body = _upload(_PNG_A, self.NARRATOR)
        self.assertEqual(status, 409, body)
        self.assertEqual(body.get("error"), "duplicate_file_deleted")
        self.assertEqual(body.get("photo_id"), photo_id)
        self.assertIn("restore", body.get("detail", ""))

    def test_reupload_after_soft_delete_leaves_no_orphan_bytes(self):
        """The half that used to strand a complete image on disk."""
        _, first = _upload(_PNG_A, self.NARRATOR)
        photo_id = first.get("id") or first.get("photo", {}).get("id")
        photo_repo.soft_delete_photo(photo_id, actor_id="operator-test")
        dirs_before = _archive_dirs(self.NARRATOR)

        _upload(_PNG_A, self.NARRATOR)

        self.assertEqual(_archive_dirs(self.NARRATOR), dirs_before,
                         "refused upload created an archive directory")
        self.assertEqual(len(_photo_rows()), 1)

    # ---- workflow (b): cross-narrator --------------------------------

    def test_other_narrator_uploading_same_bytes_is_named_not_500(self):
        _, first = _upload(_PNG_A, self.NARRATOR)
        photo_id = first.get("id") or first.get("photo", {}).get("id")

        status, body = _upload(_PNG_A, self.OTHER)
        self.assertEqual(status, 409, body)
        self.assertEqual(body.get("error"), "duplicate_file_other_narrator")
        self.assertEqual(body.get("photo_id"), photo_id)

    def test_cross_narrator_refusal_writes_nothing_anywhere(self):
        _upload(_PNG_A, self.NARRATOR)
        _upload(_PNG_A, self.OTHER)
        self.assertEqual(len(_photo_rows()), 1)
        self.assertEqual(_archive_dirs(self.OTHER), [],
                         "refused cross-narrator upload left archive bytes")


class NonVacuityTest(unittest.TestCase):
    """Prove the guard is load-bearing and the cleanup net really fires.

    Neutralising the new clash lookup reproduces the ORIGINAL defect:
    the insert raises on the UNIQUE constraint. With the cleanup net in
    place the bytes no longer survive that failure, so this test asserts
    both halves at once — if either the guard or the net were
    decorative, one of these assertions would fail.
    """

    NARRATOR = "narrator-vac"
    _PEOPLE = ("narrator-vac",)

    def setUp(self):
        db.init_db()
        con = db._connect()
        try:
            con.execute("DELETE FROM photos")
            con.commit()
        finally:
            con.close()
        for _nid in getattr(self, "_PEOPLE", ()):
            _ensure_person(_nid)
        root = Path(_TMP) / "memory" / "archive" / "photos" / self.NARRATOR
        if root.is_dir():
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    def test_without_the_guard_the_insert_still_raises_but_leaves_no_orphan(self):
        _, first = _upload(_PNG_A, self.NARRATOR)
        photo_id = first.get("id") or first.get("photo", {}).get("id")
        photo_repo.soft_delete_photo(photo_id, actor_id="operator-test")
        dirs_before = _archive_dirs(self.NARRATOR)

        original = photo_repo.find_any_photo_by_hash
        photo_repo.find_any_photo_by_hash = lambda _h: None  # neutralise
        try:
            status, body = _upload(_PNG_A, self.NARRATOR)
        finally:
            photo_repo.find_any_photo_by_hash = original

        # The constraint really does fire without the guard — so the
        # guard in the shipped path is doing the work, not the schema.
        self.assertEqual(status, 409, body)
        self.assertEqual(body.get("error"), "duplicate_file_race")
        # ...and the cleanup net removed the bytes the move had staged.
        self.assertEqual(_archive_dirs(self.NARRATOR), dirs_before,
                         "cleanup net did not remove the orphaned archive dir")
        self.assertEqual(len(_photo_rows()), 1)


class CleanupHelperSafetyTest(unittest.TestCase):
    """The cleanup helper must never delete someone else's bytes."""

    def test_refuses_a_directory_that_is_not_the_new_photo(self):
        victim = Path(_TMP) / "memory" / "archive" / "photos" / "n" / "keep-me"
        victim.mkdir(parents=True, exist_ok=True)
        (victim / "original.png").write_bytes(_PNG_A)

        photos_router._discard_orphaned_archive_dir(
            {"image_path": str(victim / "original.png"),
             "photo_id": "a-different-id"},
            "n", RuntimeError("boom"))

        self.assertTrue(victim.is_dir(), "helper removed a mismatched dir")
        self.assertTrue((victim / "original.png").is_file())

    def test_tolerates_a_missing_image_path(self):
        photos_router._discard_orphaned_archive_dir(
            {}, "n", RuntimeError("boom"))  # must not raise


if __name__ == "__main__":
    unittest.main()
