"""WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 commit 1 — server projection authority.

Locks R1.3 (refuse a silent wipe), R1.4 (server-owned monotonic version) and
R1.5 (a deliberate wipe stays possible and is explicit), at the db layer and
through the HTTP route.

The defect this pins, from the L2 partial run: a browser could rewrite a
narrator's server projection row merely because the narrator was loaded, and
the server accepted it unconditionally. The row that was actually rewritten
happened to be byte-identical -- a fact about that payload, not about the
mechanism. These tests assert the MECHANISM: a protected row is left
byte-identical, and the refusal is reported rather than swallowed.

pytest is not installed in this repo. Run with:

    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_projection_server_authority
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from fastapi import FastAPI  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from api import db as _db  # noqa: E402
from api.routers import projection as projection_router  # noqa: E402


_POPULATED = {
    "fields": {
        "personal.fullName": {"value": "Test Narrator One", "confidence": 1.0},
        "personal.placeOfBirth": {"value": "Rivertown, Example", "confidence": 0.9},
    },
    "pendingSuggestions": [{"fieldPath": "personal.preferredName", "value": "Chris"}],
    "syncLog": [],
}

_EMPTY = {"fields": {}, "pendingSuggestions": [], "syncLog": []}


class _Base(unittest.TestCase):
    """Fresh temp DB, fresh app with only the projection router mounted."""

    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        self.db_path = Path(tmp.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()

        app = FastAPI()
        app.include_router(projection_router.router)
        self.client = TestClient(app, raise_server_exceptions=False)

        self.person_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, created_at, updated_at) "
            "VALUES (?, 'Test Narrator One', '1950-03-11', '2026-08-16', '2026-08-16')",
            (self.person_id,),
        )
        con.commit()
        con.close()

    def tearDown(self):
        self.client.close()
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    # -- helpers -----------------------------------------------------------
    def _raw_row(self):
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT projection_json, source, version, updated_at "
            "FROM interview_projections WHERE person_id = ?",
            (self.person_id,),
        ).fetchone()
        con.close()
        return dict(row) if row else None

    def _seed_populated(self):
        saved = _db.upsert_projection(self.person_id, _POPULATED, source="projection_sync")
        self.assertTrue(saved["write_applied"])
        return self._raw_row()


class EmptyEnvelopeDefinition(_Base):
    """R1.3 -- the definition of 'empty' is explicit and syncLog never counts."""

    def test_missing_and_blank_envelopes_are_empty(self):
        for blob in (None, {}, {"fields": {}}, {"fields": {}, "pendingSuggestions": []}, "nonsense"):
            with self.subTest(blob=blob):
                self.assertTrue(_db.projection_envelope_is_empty(blob))

    def test_synclog_alone_is_still_empty(self):
        # A payload carrying nothing but its own audit trail must not be
        # allowed to masquerade as content and overwrite a real row.
        self.assertTrue(
            _db.projection_envelope_is_empty(
                {"fields": {}, "pendingSuggestions": [], "syncLog": [{"t": "noise"}]}
            )
        )

    def test_fields_or_pending_alone_is_non_empty(self):
        self.assertFalse(_db.projection_envelope_is_empty({"fields": {"a": 1}}))
        self.assertFalse(_db.projection_envelope_is_empty({"pendingSuggestions": [{"a": 1}]}))


class RefusesSilentWipeAtDbLayer(_Base):
    """R1.3 -- the durable half. Every writer is protected, not just the browser."""

    def test_empty_over_populated_leaves_row_byte_identical(self):
        before = self._seed_populated()

        result = _db.upsert_projection(self.person_id, _EMPTY, source="projection_sync")

        self.assertFalse(result["write_applied"], "empty write must be refused")
        after = self._raw_row()
        # Byte-identical, and updated_at did not move either: a refused write
        # must leave NO trace, so a later forensic comparison stays meaningful.
        self.assertEqual(before["projection_json"], after["projection_json"])
        self.assertEqual(before["updated_at"], after["updated_at"])
        self.assertEqual(before["version"], after["version"])
        self.assertEqual(before["source"], after["source"])

    def test_refusal_returns_the_stored_content_not_the_rejected_one(self):
        self._seed_populated()
        result = _db.upsert_projection(self.person_id, _EMPTY)
        self.assertEqual(result["projection"], _POPULATED)

    def test_allow_empty_does_wipe(self):
        self._seed_populated()
        result = _db.upsert_projection(
            self.person_id, _EMPTY, source="bb_deep_reset", allow_empty=True
        )
        self.assertTrue(result["write_applied"])
        stored = json.loads(self._raw_row()["projection_json"])
        self.assertEqual(stored.get("fields"), {})
        self.assertEqual(self._raw_row()["source"], "bb_deep_reset")

    def test_empty_over_absent_row_is_not_an_error(self):
        # Nothing to protect. Creating an empty row is legitimate.
        result = _db.upsert_projection(self.person_id, _EMPTY)
        self.assertTrue(result["write_applied"])
        self.assertIsNotNone(self._raw_row())

    def test_empty_over_empty_row_is_applied(self):
        _db.upsert_projection(self.person_id, _EMPTY)
        result = _db.upsert_projection(self.person_id, _EMPTY)
        self.assertTrue(result["write_applied"])

    def test_non_empty_over_populated_still_applies(self):
        # The guard protects against erasure, not against ordinary editing.
        self._seed_populated()
        newer = {
            "fields": {"personal.fullName": {"value": "Test Narrator One-B"}},
            "pendingSuggestions": [],
            "syncLog": [],
        }
        result = _db.upsert_projection(self.person_id, newer)
        self.assertTrue(result["write_applied"])
        stored = json.loads(self._raw_row()["projection_json"])
        self.assertEqual(stored["fields"]["personal.fullName"]["value"], "Test Narrator One-B")


class ServerOwnedMonotonicVersion(_Base):
    """R1.4 -- version carries ordering information instead of a permanent 1."""

    def test_first_write_is_version_one(self):
        saved = _db.upsert_projection(self.person_id, _POPULATED, version=999)
        self.assertEqual(saved["version"], 1)
        self.assertEqual(self._raw_row()["version"], 1)

    def test_each_applied_write_increments(self):
        for expected in (1, 2, 3):
            saved = _db.upsert_projection(
                self.person_id,
                {"fields": {"k": {"value": str(expected)}}, "pendingSuggestions": []},
                version=1,  # what the browser hardcodes; advisory only
            )
            self.assertEqual(saved["version"], expected)

    def test_caller_version_cannot_pin_or_rewind_the_column(self):
        _db.upsert_projection(self.person_id, _POPULATED, version=1)
        _db.upsert_projection(self.person_id, _POPULATED, version=1)
        self.assertEqual(self._raw_row()["version"], 2)

    def test_refused_write_does_not_increment(self):
        self._seed_populated()
        v_before = self._raw_row()["version"]
        _db.upsert_projection(self.person_id, _EMPTY)
        self.assertEqual(self._raw_row()["version"], v_before)


class PutRouteContract(_Base):
    """R1.3/R1.5 through HTTP -- the shape the browser actually sends."""

    def _put(self, body):
        return self.client.put("/api/interview/projection", json=body)

    def test_body_omitting_projection_cannot_wipe_a_populated_row(self):
        # THE original hazard: `projection` has a default_factory, so a body
        # that omits it (as bio-builder's deep reset did, by putting `fields`
        # at the top level) validated fine and silently wrote an empty
        # envelope over real narrator content.
        before = self._seed_populated()
        r = self._put(
            {"person_id": self.person_id, "fields": {}, "source": "bb_deep_reset", "version": 1}
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["write_applied"])
        self.assertEqual(before["projection_json"], self._raw_row()["projection_json"])

    def test_allow_empty_ALONE_no_longer_wipes(self):
        """Supervisor review 2026-08-17.

        This test asserted that `allow_empty` alone wiped the row. That is
        retired: `allow_empty` guarded only the EMPTY case, so a non-empty
        stale envelope could still erase server-authored keys. Replacement
        now needs `replace=true` AND a matching `base_version`; without
        them the body is merged, and merging nothing changes nothing.
        """
        self._seed_populated()
        before = self._raw_row()
        r = self._put(
            {
                "person_id": self.person_id,
                "projection": {"fields": {}, "pendingSuggestions": [], "syncLog": []},
                "source": "bb_deep_reset",
                "version": 1,
                "allow_empty": True,
            }
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["write_applied"])
        self.assertEqual(before["projection_json"], self._raw_row()["projection_json"])

    def test_authorized_replacement_still_wipes(self):
        self._seed_populated()
        v = self._raw_row()["version"]
        r = self._put(
            {
                "person_id": self.person_id,
                "projection": {"fields": {}, "pendingSuggestions": [], "syncLog": []},
                "source": "bb_deep_reset",
                "version": 1,
                "allow_empty": True,
                "replace": True,
                "base_version": v,
            }
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["write_applied"])
        self.assertEqual(json.loads(self._raw_row()["projection_json"]).get("fields"), {})

    def test_refusal_response_echoes_the_protected_content(self):
        self._seed_populated()
        r = self._put({"person_id": self.person_id, "projection": _EMPTY})
        body = r.json()
        self.assertFalse(body["write_applied"])
        self.assertIn("personal.fullName", body["projection"]["fields"])

    def test_successful_put_reports_write_applied_and_version(self):
        r = self._put({"person_id": self.person_id, "projection": _POPULATED})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["write_applied"])
        self.assertEqual(r.json()["version"], 1)

    def test_blank_person_id_is_rejected(self):
        r = self._put({"person_id": "   ", "projection": _POPULATED})
        self.assertEqual(r.status_code, 400)

    def test_get_round_trips_what_put_stored(self):
        self._put({"person_id": self.person_id, "projection": _POPULATED})
        r = self.client.get(f"/api/interview/projection?person_id={self.person_id}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            r.json()["projection"]["fields"]["personal.fullName"]["value"],
            "Test Narrator One",
        )


class CorrectionWriterStillWorks(_Base):
    """The server's own correction path must not be caught by the guard."""

    def test_server_authored_non_empty_write_applies(self):
        self._seed_populated()
        corrected = json.loads(json.dumps(_POPULATED))
        corrected["fields"]["personal.placeOfBirth"]["value"] = "Hillford, Example"
        result = _db.upsert_projection(self.person_id, corrected, source="correction")
        self.assertTrue(result["write_applied"])
        stored = json.loads(self._raw_row()["projection_json"])
        self.assertEqual(stored["fields"]["personal.placeOfBirth"]["value"], "Hillford, Example")


# ─────────────────────────────────────────────────────────────────────────────
# Supervisor requirements, 2026-08-16: field-level mutation and
# conflict-aware merging, not a timestamp check around the same unsafe
# whole-document replacement.
# ─────────────────────────────────────────────────────────────────────────────


class FieldLevelMergePreservesServerOnlyKeys(_Base):
    """The reason a guarded PUT was not good enough."""

    def test_a_key_the_writer_never_saw_survives(self):
        # This is the whole point. `projection_writer.apply_correction`
        # writes into `fields` mid-turn; a browser that replaces the
        # document erases that correction even when its own payload is
        # fresh, non-empty and authorised.
        self._seed_populated()
        _db.merge_projection_fields(
            self.person_id,
            mutations={"personal.correctedByServer": {"value": "Hillford, Example"}},
            source="correction",
        )
        _db.merge_projection_fields(
            self.person_id,
            mutations={"personal.preferredName": {"value": "Chris"}},
            source="projection_sync",
        )
        stored = json.loads(self._raw_row()["projection_json"])["fields"]
        self.assertIn("personal.correctedByServer", stored)
        self.assertIn("personal.preferredName", stored)
        self.assertIn("personal.fullName", stored)

    def test_untouched_paths_are_left_alone(self):
        self._seed_populated()
        before = json.loads(self._raw_row()["projection_json"])["fields"]["personal.placeOfBirth"]
        _db.merge_projection_fields(
            self.person_id, mutations={"personal.fullName": {"value": "T. N. One-B"}}
        )
        after = json.loads(self._raw_row()["projection_json"])["fields"]["personal.placeOfBirth"]
        self.assertEqual(before, after)

    def test_pending_suggestions_are_carried_through(self):
        self._seed_populated()
        _db.merge_projection_fields(self.person_id, mutations={"a.b": {"value": "x"}})
        stored = json.loads(self._raw_row()["projection_json"])
        self.assertEqual(len(stored["pendingSuggestions"]), 1)

    def test_removal_drops_only_the_named_path(self):
        self._seed_populated()
        _db.merge_projection_fields(self.person_id, removals=["personal.placeOfBirth"])
        fields = json.loads(self._raw_row()["projection_json"])["fields"]
        self.assertNotIn("personal.placeOfBirth", fields)
        self.assertIn("personal.fullName", fields)

    def test_a_merge_onto_an_absent_row_creates_it(self):
        r = _db.merge_projection_fields(self.person_id, mutations={"a.b": {"value": "x"}})
        self.assertTrue(r["write_applied"])
        self.assertEqual(r["version"], 1)

    def test_an_empty_merge_writes_nothing_and_is_not_a_conflict(self):
        self._seed_populated()
        before = self._raw_row()
        r = _db.merge_projection_fields(self.person_id)
        self.assertFalse(r["write_applied"])
        self.assertFalse(r["conflict"])
        self.assertEqual(before["updated_at"], self._raw_row()["updated_at"])


class StaleWritesConflict(_Base):
    """A stale write must be refused and the NEWER server record preserved."""

    def test_merge_with_a_stale_base_is_refused(self):
        self._seed_populated()  # version 1
        _db.merge_projection_fields(self.person_id, mutations={"x.y": {"value": "server"}})  # v2
        before = self._raw_row()

        r = _db.merge_projection_fields(
            self.person_id, mutations={"x.y": {"value": "stale browser"}}, base_version=1
        )
        self.assertTrue(r["conflict"])
        self.assertFalse(r["write_applied"])
        after = self._raw_row()
        self.assertEqual(before["projection_json"], after["projection_json"])
        self.assertEqual(before["updated_at"], after["updated_at"])

    def test_the_conflict_hands_back_the_newer_record(self):
        self._seed_populated()
        _db.merge_projection_fields(self.person_id, mutations={"x.y": {"value": "server"}})
        r = _db.merge_projection_fields(
            self.person_id, mutations={"x.y": {"value": "stale"}}, base_version=1
        )
        self.assertEqual(r["projection"]["fields"]["x.y"]["value"], "server")
        self.assertEqual(r["version"], 2)

    def test_a_matching_base_applies(self):
        self._seed_populated()
        r = _db.merge_projection_fields(
            self.person_id, mutations={"x.y": {"value": "ok"}}, base_version=1
        )
        self.assertTrue(r["write_applied"])
        self.assertFalse(r["conflict"])

    def test_no_base_claimed_means_no_check(self):
        self._seed_populated()
        r = _db.merge_projection_fields(self.person_id, mutations={"x.y": {"value": "ok"}})
        self.assertTrue(r["write_applied"])

    def test_whole_document_put_also_honours_the_base(self):
        self._seed_populated()
        _db.merge_projection_fields(self.person_id, mutations={"x.y": {"value": "server"}})
        before = self._raw_row()
        r = _db.upsert_projection(self.person_id, _POPULATED, base_version=1)
        self.assertTrue(r["conflict"])
        self.assertEqual(before["projection_json"], self._raw_row()["projection_json"])


class ConflictOverHttp(_Base):
    def _patch(self, body):
        return self.client.patch("/api/interview/projection", json=body)

    def test_patch_applies_field_level(self):
        self._seed_populated()
        r = self._patch(
            {"person_id": self.person_id, "mutations": {"a.b": {"value": "x"}}}
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["write_applied"])
        fields = json.loads(self._raw_row()["projection_json"])["fields"]
        self.assertIn("a.b", fields)
        self.assertIn("personal.fullName", fields)

    def test_stale_patch_is_409_with_the_server_record(self):
        self._seed_populated()
        self._patch({"person_id": self.person_id, "mutations": {"x.y": {"value": "server"}}})
        r = self._patch(
            {
                "person_id": self.person_id,
                "mutations": {"x.y": {"value": "stale"}},
                "base_version": 1,
            }
        )
        self.assertEqual(r.status_code, 409)
        body = r.json()
        self.assertTrue(body["conflict"])
        self.assertFalse(body["write_applied"])
        self.assertEqual(body["projection"]["fields"]["x.y"]["value"], "server")

    def test_stale_put_is_409(self):
        self._seed_populated()
        r = self.client.put(
            "/api/interview/projection",
            json={"person_id": self.person_id, "projection": _POPULATED, "base_version": 99},
        )
        self.assertEqual(r.status_code, 409)

    def test_blank_person_id_on_patch_is_400(self):
        self.assertEqual(self._patch({"person_id": "  "}).status_code, 400)


class AbsentRowIsDistinguishableFromVersionOne(_Base):
    """base_version is unusable if 'no row' and 'version 1' look alike."""

    def test_absent_row_reports_version_zero(self):
        r = self.client.get(f"/api/interview/projection?person_id={self.person_id}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["version"], 0)
        self.assertEqual(r.json()["source"], "empty")

    def test_first_write_then_reports_version_one(self):
        _db.merge_projection_fields(self.person_id, mutations={"a.b": {"value": "x"}})
        r = self.client.get(f"/api/interview/projection?person_id={self.person_id}")
        self.assertEqual(r.json()["version"], 1)


# ─────────────────────────────────────────────────────────────────────────────
# Supervisor review 2026-08-17. A global version proves only that SOMETHING
# moved. These pin the per-path distinction, and the two conflict shapes
# separately, because collapsing them is exactly the hole.
# ─────────────────────────────────────────────────────────────────────────────


class SamePathConflictIsRefused(_Base):
    """The dangerous shape: both surfaces changed the SAME path."""

    def test_same_path_conflict_writes_nothing(self):
        self._seed_populated()
        base = json.loads(self._raw_row()["projection_json"])["fields"]
        # The server (a correction) moves the very path the browser is editing.
        _db.merge_projection_fields(
            self.person_id,
            mutations={"personal.placeOfBirth": {"value": "SERVER — newer"}},
            source="correction",
        )
        before = self._raw_row()

        r = _db.merge_projection_fields(
            self.person_id,
            mutations={"personal.placeOfBirth": {"value": "BROWSER — stale"}},
            base_fields={"personal.placeOfBirth": base["personal.placeOfBirth"]},
        )
        self.assertTrue(r["conflict"])
        self.assertFalse(r["write_applied"])
        self.assertEqual(r["conflicting_paths"], ["personal.placeOfBirth"])
        after = self._raw_row()
        self.assertEqual(before["projection_json"], after["projection_json"])
        self.assertEqual(before["updated_at"], after["updated_at"])

    def test_the_newer_server_value_survives_the_refusal(self):
        self._seed_populated()
        base = json.loads(self._raw_row()["projection_json"])["fields"]
        _db.merge_projection_fields(
            self.person_id,
            mutations={"personal.placeOfBirth": {"value": "SERVER — newer"}},
            source="correction",
        )
        _db.merge_projection_fields(
            self.person_id,
            mutations={"personal.placeOfBirth": {"value": "BROWSER — stale"}},
            base_fields={"personal.placeOfBirth": base["personal.placeOfBirth"]},
        )
        stored = json.loads(self._raw_row()["projection_json"])["fields"]
        self.assertEqual(stored["personal.placeOfBirth"]["value"], "SERVER — newer")

    def test_a_removal_of_a_contested_path_is_refused_too(self):
        self._seed_populated()
        base = json.loads(self._raw_row()["projection_json"])["fields"]
        _db.merge_projection_fields(
            self.person_id,
            mutations={"personal.placeOfBirth": {"value": "SERVER — newer"}},
            source="correction",
        )
        r = _db.merge_projection_fields(
            self.person_id,
            removals=["personal.placeOfBirth"],
            base_fields={"personal.placeOfBirth": base["personal.placeOfBirth"]},
        )
        self.assertTrue(r["conflict"])
        self.assertIn("personal.placeOfBirth", r["conflicting_paths"])
        self.assertIn("personal.placeOfBirth",
                      json.loads(self._raw_row()["projection_json"])["fields"])

    def test_one_contested_path_refuses_the_WHOLE_write(self):
        # Partial application would leave the browser unable to say what
        # landed. All or nothing.
        self._seed_populated()
        base = json.loads(self._raw_row()["projection_json"])["fields"]
        _db.merge_projection_fields(
            self.person_id,
            mutations={"personal.placeOfBirth": {"value": "SERVER"}},
            source="correction",
        )
        r = _db.merge_projection_fields(
            self.person_id,
            mutations={
                "personal.placeOfBirth": {"value": "stale"},
                "personal.preferredName": {"value": "safe"},
            },
            base_fields={
                "personal.placeOfBirth": base["personal.placeOfBirth"],
                "personal.preferredName": None,
            },
        )
        self.assertTrue(r["conflict"])
        self.assertNotIn("personal.preferredName",
                         json.loads(self._raw_row()["projection_json"])["fields"])


class DisjointPathRebaseIsApplied(_Base):
    """The safe shape: the server changed a DIFFERENT path."""

    def test_a_disjoint_edit_applies_despite_a_moved_version(self):
        self._seed_populated()
        base = json.loads(self._raw_row()["projection_json"])["fields"]
        _db.merge_projection_fields(
            self.person_id,
            mutations={"server.only": {"value": "written by a correction"}},
            source="correction",
        )
        stale_version = 1
        r = _db.merge_projection_fields(
            self.person_id,
            mutations={"personal.preferredName": {"value": "Chris"}},
            base_version=stale_version,
            base_fields={"personal.preferredName": base.get("personal.preferredName")},
        )
        self.assertTrue(r["write_applied"], "a disjoint edit must not be refused")
        self.assertFalse(r["conflict"])
        stored = json.loads(self._raw_row()["projection_json"])["fields"]
        self.assertEqual(stored["personal.preferredName"]["value"], "Chris")
        self.assertIn("server.only", stored, "the server's own key must survive")

    def test_the_rebase_happens_server_side_in_one_round_trip(self):
        # Which is why the client needs no retry: the only 409 it can see
        # is a genuinely contested one.
        self._seed_populated()
        _db.merge_projection_fields(
            self.person_id, mutations={"a.b": {"value": "srv"}}, source="correction"
        )
        r = _db.merge_projection_fields(
            self.person_id,
            mutations={"c.d": {"value": "browser"}},
            base_version=0,
            base_fields={"c.d": None},
        )
        self.assertTrue(r["write_applied"])
        self.assertEqual(r["conflicting_paths"], [])


class UnprovableIsNotSafe(_Base):
    def test_no_base_fields_plus_moved_version_contests_everything(self):
        self._seed_populated()
        _db.merge_projection_fields(
            self.person_id, mutations={"x.y": {"value": "srv"}}, source="correction"
        )
        r = _db.merge_projection_fields(
            self.person_id, mutations={"p.q": {"value": "browser"}}, base_version=1
        )
        self.assertTrue(r["conflict"])
        self.assertEqual(r["conflicting_paths"], ["p.q"])


class PendingSuggestionsAndRemovals(_Base):
    def test_pending_suggestions_are_left_alone_when_omitted(self):
        self._seed_populated()
        _db.merge_projection_fields(self.person_id, mutations={"a.b": {"value": "x"}})
        stored = json.loads(self._raw_row()["projection_json"])
        self.assertEqual(len(stored["pendingSuggestions"]), 1)

    def test_pending_suggestions_are_replaced_when_supplied(self):
        self._seed_populated()
        _db.merge_projection_fields(
            self.person_id, pending_suggestions=[{"fieldPath": "x", "value": "y"}]
        )
        stored = json.loads(self._raw_row()["projection_json"])
        self.assertEqual(stored["pendingSuggestions"], [{"fieldPath": "x", "value": "y"}])

    def test_clearing_pending_suggestions_is_possible(self):
        self._seed_populated()
        _db.merge_projection_fields(self.person_id, pending_suggestions=[])
        self.assertEqual(json.loads(self._raw_row()["projection_json"])["pendingSuggestions"], [])

    def test_a_pending_only_change_is_a_real_write(self):
        self._seed_populated()
        r = _db.merge_projection_fields(self.person_id, pending_suggestions=[])
        self.assertTrue(r["write_applied"])
        self.assertEqual(r["version"], 2)

    def test_a_removal_does_not_disturb_neighbours(self):
        self._seed_populated()
        _db.merge_projection_fields(self.person_id, removals=["personal.placeOfBirth"])
        fields = json.loads(self._raw_row()["projection_json"])["fields"]
        self.assertNotIn("personal.placeOfBirth", fields)
        self.assertIn("personal.fullName", fields)


class ServerCorrectionPlusBrowserMutation(_Base):
    """The live interleaving the whole lane exists for."""

    def test_a_correction_mid_turn_survives_a_later_browser_edit(self):
        self._seed_populated()
        base = json.loads(self._raw_row()["projection_json"])["fields"]
        # Lori corrects a field the browser is not touching.
        _db.merge_projection_fields(
            self.person_id,
            mutations={"personal.correctedByLori": {"value": "two children, not three"}},
            source="correction",
        )
        # The browser flushes an unrelated edit it queued before that.
        _db.merge_projection_fields(
            self.person_id,
            mutations={"personal.preferredName": {"value": "Chris"}},
            base_fields={"personal.preferredName": base.get("personal.preferredName")},
        )
        stored = json.loads(self._raw_row()["projection_json"])["fields"]
        self.assertEqual(stored["personal.correctedByLori"]["value"], "two children, not three")
        self.assertEqual(stored["personal.preferredName"]["value"], "Chris")
        self.assertEqual(stored["personal.fullName"]["value"], "Test Narrator One")


class WholeDocumentPutCannotErase(_Base):
    """Item 4 — the replacement route is closed unless explicitly authorized."""

    def _put(self, body):
        return self.client.put("/api/interview/projection", json=body)

    def test_a_nonempty_stale_envelope_does_not_erase_a_server_key(self):
        # THE hole: allow_empty guarded only the empty case, so a
        # non-empty but stale envelope still wiped server-authored fields.
        self._seed_populated()
        _db.merge_projection_fields(
            self.person_id,
            mutations={"server.only": {"value": "written by a correction"}},
            source="correction",
        )
        r = self._put({"person_id": self.person_id, "projection": _POPULATED})
        self.assertEqual(r.status_code, 200)
        stored = json.loads(self._raw_row()["projection_json"])["fields"]
        self.assertIn("server.only", stored, "PUT must not erase an unmentioned key")

    def test_replace_requires_a_base_version(self):
        self._seed_populated()
        r = self._put({"person_id": self.person_id, "projection": _EMPTY,
                       "replace": True, "allow_empty": True})
        self.assertEqual(r.status_code, 400)

    def test_replace_with_a_stale_base_is_409(self):
        self._seed_populated()
        _db.merge_projection_fields(self.person_id, mutations={"x.y": {"value": "srv"}})
        before = self._raw_row()
        r = self._put({"person_id": self.person_id, "projection": _EMPTY,
                       "replace": True, "allow_empty": True, "base_version": 1})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(before["projection_json"], self._raw_row()["projection_json"])

    def test_authorized_replacement_with_a_matching_base_does_replace(self):
        self._seed_populated()
        v = self._raw_row()["version"]
        r = self._put({"person_id": self.person_id, "projection": _EMPTY,
                       "replace": True, "allow_empty": True, "base_version": v})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["write_applied"])
        self.assertEqual(json.loads(self._raw_row()["projection_json"])["fields"], {})


class ConflictOverHttpPerPath(_Base):
    def _patch(self, body):
        return self.client.patch("/api/interview/projection", json=body)

    def test_same_path_conflict_names_the_paths_over_the_wire(self):
        self._seed_populated()
        base = json.loads(self._raw_row()["projection_json"])["fields"]
        _db.merge_projection_fields(
            self.person_id, mutations={"personal.fullName": {"value": "SERVER"}},
            source="correction",
        )
        r = self._patch({
            "person_id": self.person_id,
            "mutations": {"personal.fullName": {"value": "browser"}},
            "base_fields": {"personal.fullName": base["personal.fullName"]},
        })
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["conflicting_paths"], ["personal.fullName"])

    def test_disjoint_patch_succeeds_over_the_wire(self):
        self._seed_populated()
        _db.merge_projection_fields(
            self.person_id, mutations={"server.only": {"value": "s"}}, source="correction"
        )
        r = self._patch({
            "person_id": self.person_id,
            "mutations": {"brand.new": {"value": "b"}},
            "base_fields": {"brand.new": None},
        })
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["write_applied"])

    def test_patch_can_replace_pending_suggestions(self):
        self._seed_populated()
        r = self._patch({"person_id": self.person_id, "pendingSuggestions": []})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(json.loads(self._raw_row()["projection_json"])["pendingSuggestions"], [])


class CorrectionWriterCannotEraseAConcurrentEdit(_Base):
    """`projection_writer.apply_correction` was the last whole-document writer.

    The HTTP PUT was hardened first, which left this INTERNAL path able to
    erase a browser mutation landing between its read and its write -- and
    a correction turn and a narrator edit are the pair most likely to
    overlap, because they happen in the same seconds.
    """

    def _writer(self):
        from api.services import projection_writer
        return projection_writer

    def test_the_writer_no_longer_whole_document_replaces(self):
        # Asserted over the AST, not the text: this function's own
        # comments explain WHY upsert_projection was retired, and a
        # substring scan would fire on the explanation.
        import ast
        import inspect

        src = inspect.getsource(self._writer().apply_correction)
        tree = ast.parse(inspect.cleandoc("\n".join(src.split("\n")[0:])).replace(
            "def apply_correction", "def apply_correction", 1))
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = getattr(fn, "attr", None) or getattr(fn, "id", None)
                if name:
                    called.add(name)
        self.assertIn("merge_projection_fields", called)
        self.assertNotIn(
            "upsert_projection", called,
            "the correction path must not whole-document replace",
        )

    def test_a_correction_leaves_a_concurrent_browser_field_intact(self):
        self._seed_populated()
        # What the correction writer read before the browser interleaved.
        base = json.loads(self._raw_row()["projection_json"])["fields"]
        # The browser writes a field the correction will not touch.
        _db.merge_projection_fields(
            self.person_id,
            mutations={"browser.only": {"value": "typed by the operator"}},
            source="projection_sync",
        )
        # The correction turn then rewrites a DIFFERENT path, claiming the
        # base it actually read. Disjoint, so it applies.
        _db.merge_projection_fields(
            self.person_id,
            mutations={"personal.fullName": {"value": "corrected by Lori"}},
            source="correction",
            base_fields={"personal.fullName": base["personal.fullName"]},
        )
        stored = json.loads(self._raw_row()["projection_json"])["fields"]
        self.assertIn("browser.only", stored,
                      "the correction path must not erase a concurrent edit")
        self.assertEqual(stored["personal.fullName"]["value"], "corrected by Lori")

    def test_a_correction_that_contests_a_browser_path_is_refused(self):
        self._seed_populated()
        base = json.loads(self._raw_row()["projection_json"])["fields"]
        # Browser moves the path first.
        _db.merge_projection_fields(
            self.person_id,
            mutations={"personal.fullName": {"value": "typed by the operator"}},
            source="projection_sync",
        )
        # Correction read the OLD value and now tries to write.
        r = _db.merge_projection_fields(
            self.person_id,
            mutations={"personal.fullName": {"value": "corrected by Lori"}},
            source="correction",
            base_fields={"personal.fullName": base["personal.fullName"]},
        )
        self.assertTrue(r["conflict"])
        stored = json.loads(self._raw_row()["projection_json"])["fields"]
        self.assertEqual(stored["personal.fullName"]["value"], "typed by the operator")


class CompareAndWriteIsOneTransaction(_Base):
    """Otherwise two requests can both pass the check before either writes."""

    def test_merge_opens_an_immediate_write_transaction(self):
        import inspect
        src = inspect.getsource(_db.merge_projection_fields)
        i_begin = src.index('BEGIN IMMEDIATE')
        i_select = src.index("SELECT projection_json")
        self.assertLess(i_begin, i_select,
                        "the write lock must be taken BEFORE the read, or the "
                        "comparison is made against a row another writer can "
                        "still change")

    def test_upsert_opens_one_too(self):
        import inspect
        src = inspect.getsource(_db.upsert_projection)
        self.assertLess(src.index('BEGIN IMMEDIATE'), src.index("SELECT projection_json"))

    def test_a_refusal_rolls_back_rather_than_leaving_a_lock(self):
        import inspect
        src = inspect.getsource(_db.merge_projection_fields)
        head = src[: src.index("next_version")]
        self.assertGreaterEqual(head.count("con.rollback()"), 2,
                                "every early return inside the transaction must "
                                "release it")

    def test_a_refused_write_leaves_the_row_writable_afterwards(self):
        # The behavioural half: if a refusal leaked the write lock, this
        # next write would block until busy_timeout and then fail.
        self._seed_populated()
        _db.merge_projection_fields(
            self.person_id, mutations={"x.y": {"value": "srv"}}, source="correction"
        )
        refused = _db.merge_projection_fields(
            self.person_id, mutations={"x.y": {"value": "stale"}},
            base_fields={"x.y": None},
        )
        self.assertTrue(refused["conflict"])
        ok = _db.merge_projection_fields(
            self.person_id, mutations={"z.w": {"value": "after"}}, source="projection_sync"
        )
        self.assertTrue(ok["write_applied"])

    def test_extra_envelope_keys_are_carried_but_named(self):
        # last_correction_at is how the correction writer keeps its own
        # envelope key without carrying a whole document.
        self._seed_populated()
        _db.merge_projection_fields(
            self.person_id,
            mutations={"a.b": {"value": "x"}},
            extra_keys={"last_correction_at": "2026-08-17T00:00:00"},
        )
        stored = json.loads(self._raw_row()["projection_json"])
        self.assertEqual(stored["last_correction_at"], "2026-08-17T00:00:00")
        self.assertIn("personal.fullName", stored["fields"])


if __name__ == "__main__":
    unittest.main()
