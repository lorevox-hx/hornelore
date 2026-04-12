"""WO-13 Phase 8 — B1 edge test: legacy vs promoted conflict precedence.

The existing Phase 8 harness (run_phase8_test.py) uses an Ada Lovelace
fixture where the legacy blob and the promoted truth rows either
*agree* (preferred='Ada' in both) or the legacy value is the only one
present (fullname, dob, pob, birthOrder never got promoted). That means
the "promoted wins" rule was never actually stressed with conflicting
values.

B1 fills that hole. For each of the five protected identity fields,
legacy and promoted disagree, and the builder must return the promoted
value, not the legacy one. In addition:

  - partial conflict: only a subset of protected fields have promoted
    rows; the rest must fall through to legacy
  - kinship and pets are always passthrough and are never overridden
    even if promoted truth rows exist with matching field names
  - unmapped basics.* fields are never touched by promoted rows
  - source_row_id on each merged field points back to the FT row that
    provided it
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

TEST_ROOT = Path(__file__).resolve().parent
os.environ["DATA_DIR"] = str(TEST_ROOT / "data")
os.environ["DB_NAME"] = "wo13_phase8_b1_conflict_test.sqlite3"
os.environ.pop("HORNELORE_TRUTH_V2", None)
os.environ.pop("HORNELORE_TRUTH_V2_PROFILE", None)

db_file = TEST_ROOT / "data" / "db" / os.environ["DB_NAME"]
for f in (db_file, db_file.with_suffix(".sqlite3-wal"), db_file.with_suffix(".sqlite3-shm")):
    if f.exists():
        f.unlink()

HORNELORE_PY = Path("/sessions/nice-fervent-clarke/mnt/hornelore/server/code")
sys.path.insert(0, str(HORNELORE_PY))

# ── fastapi / pydantic stubs (same as other Phase 8 harnesses) ─────────
import types as _types  # noqa: E402

if "fastapi" not in sys.modules:
    _fastapi = _types.ModuleType("fastapi")
    class _StubAPIRouter:
        def __init__(self, *a, **kw): pass
        def post(self, *a, **kw):  return lambda fn: fn
        def get(self, *a, **kw):   return lambda fn: fn
        def patch(self, *a, **kw): return lambda fn: fn
        def delete(self, *a, **kw):return lambda fn: fn
        def put(self, *a, **kw):   return lambda fn: fn
    class _StubHTTPException(Exception):
        def __init__(self, status_code=500, detail=""):
            self.status_code = status_code
            self.detail = detail
            super().__init__(f"HTTP {status_code}: {detail}")
    def _stub_query(default=None, *a, **kw): return default
    _fastapi.APIRouter     = _StubAPIRouter
    _fastapi.HTTPException = _StubHTTPException
    _fastapi.Query         = _stub_query
    sys.modules["fastapi"] = _fastapi

if "pydantic" not in sys.modules:
    _pyd = _types.ModuleType("pydantic")
    class _BaseModel:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)
    def _Field(default=None, **kw):
        if default is ...:
            return None
        return default
    _pyd.BaseModel = _BaseModel
    _pyd.Field     = _Field
    sys.modules["pydantic"] = _pyd

from api import db as H                                    # noqa: E402


def ok(msg):
    print(f"  OK  {msg}")


def fail(msg):
    print(f"  FAIL  {msg}")
    sys.exit(1)


print("=" * 62)
print("WO-13 Phase 8 B1 — legacy vs promoted conflict precedence")
print("=" * 62)

H.init_db()

# ── 1. Seed a narrator with legacy values for all 5 protected fields ──
kent = H.create_person(display_name="Kent James Horne", narrator_type="live")
kent_id = kent["id"]

# Every legacy value is deliberately WRONG and every promoted value is
# deliberately the intended corrected form. If "promoted wins" holds,
# the builder must emit the promoted values end-to-end.
legacy_blob = {
    "basics": {
        "fullname":  "Kent J. Horne",                 # legacy (wrong)
        "preferred": "KJ",                            # legacy (wrong)
        "dob":       "1943-01-01",                    # legacy (wrong day)
        "pob":       "Stoneycreek, NS",               # legacy (abbr)
        "birthOrder": "oldest",                       # legacy (wrong wording)
        # Unmapped basics — must pass through untouched.
        "culture":   "Scots-Canadian",
        "country":   "Canada",
        "pronouns":  "he/him",
        "legalFirstName":  "Kent",
        "legalMiddleName": "James",
        "legalLastName":   "Horne",
    },
    "kinship": [
        {"relation": "spouse",   "name": "Janice Ann Horne"},
        {"relation": "daughter", "name": "Emma Horne"},
    ],
    "pets": [{"name": "Buddy", "kind": "dog"}],
}
H.ensure_profile(kent_id)
H.update_profile_json(kent_id, legacy_blob, merge=False, reason="B1 conflict seed")
stored = H.get_profile(kent_id)
assert stored["profile_json"]["basics"]["fullname"] == "Kent J. Horne"
ok("seed: Kent with deliberately-wrong legacy values for all 5 protected fields")


# ── 2. Promote corrected values for all 5 protected fields ────────────
# Every promoted row uses extraction_method='manual' so none of them
# are blocked by the Phase 7 rules_fallback gate.
PROMOTED_FIXTURES = [
    ("personal.fullName",      "Kent James Horne"),
    ("personal.preferredName", "Kent"),
    ("personal.dateOfBirth",   "1943-01-03"),
    ("personal.placeOfBirth",  "Stoneycreek, Nova Scotia"),
    ("personal.birthOrder",    "eldest of three"),
]
promoted_row_ids = {}
for field, value in PROMOTED_FIXTURES:
    note = H.ft_add_note(
        person_id=kent_id,
        body=f"Corrected {field}: {value}",
        source_kind="manual",
        source_ref=f"b1_seed:{field}",
        created_by="chris",
    )
    row = H.ft_add_row(
        person_id=kent_id,
        note_id=note["id"],
        subject_name="Kent James Horne",
        relationship="self",
        field=field,
        source_says=value,
        approved_value=value,
        status="needs_verify",
        extraction_method="manual",
    )
    result = H.ft_promote_row(row["id"], reviewer="chris")
    assert result["promoted"]["op"] == "created", \
        f"{field} promotion op={result['promoted']['op']}, expected created"
    promoted_row_ids[field] = row["id"]

# Sanity: all 5 protected rows in family_truth_promoted
promoted = H.ft_list_promoted(kent_id)
protected_in_promoted = {
    r["field"]: r for r in promoted if r["field"] in dict(PROMOTED_FIXTURES)
}
assert len(protected_in_promoted) == 5, \
    f"expected 5 protected rows promoted, got {len(protected_in_promoted)}"
ok(f"seed: 5 corrected protected-field rows promoted via manual extraction")


# ── 3. Build profile and assert promoted wins on EVERY protected field ─
built = H.build_profile_from_promoted(kent_id)
basics = built["basics"]

# Mapping between promoted-truth field names and legacy basics keys.
EXPECTED = {
    "fullname":   ("Kent James Horne",         "Kent J. Horne"),
    "preferred":  ("Kent",                      "KJ"),
    "dob":        ("1943-01-03",                "1943-01-01"),
    "pob":        ("Stoneycreek, Nova Scotia",  "Stoneycreek, NS"),
    "birthOrder": ("eldest of three",           "oldest"),
}
for key, (promoted_value, legacy_value) in EXPECTED.items():
    actual = basics.get(key)
    assert actual == promoted_value, (
        f"basics.{key}: promoted-wins violated — "
        f"got {actual!r}, expected {promoted_value!r} "
        f"(legacy was {legacy_value!r})"
    )
    # And crucially, the legacy value is NOT present anywhere in basics.
    assert legacy_value not in str(actual), \
        f"legacy value leaked into basics.{key}: {actual!r}"
ok("builder: all 5 protected fields — promoted wins over conflicting legacy")


# ── 4. Unmapped legacy basics still pass through untouched ────────────
for unmapped_key, expected in [
    ("culture",        "Scots-Canadian"),
    ("country",        "Canada"),
    ("pronouns",       "he/him"),
    ("legalFirstName", "Kent"),
    ("legalMiddleName","James"),
    ("legalLastName",  "Horne"),
]:
    got = basics.get(unmapped_key)
    assert got == expected, \
        f"unmapped basics.{unmapped_key}: expected {expected!r}, got {got!r}"
ok("builder: unmapped legacy basics.* pass through untouched during conflict")


# ── 5. Kinship + pets pass through regardless of promoted truth ────────
# We seed a "promoted" free-form row with field='spouse' as a trap —
# kinship is not governed by promoted truth today, and the builder
# must not try to override legacy kinship with it.
trap_note = H.ft_add_note(
    person_id=kent_id,
    body="Spouse trap value",
    source_kind="manual",
    created_by="chris",
)
H.ft_add_row(
    person_id=kent_id,
    note_id=trap_note["id"],
    subject_name="Janice Ann Horne",
    relationship="spouse",
    field="spouse",   # note: not a mapped protected field, goes into truth[]
    source_says="Janice — definitely not her real name",
    approved_value="DECOY VALUE (test)",
    status="approve",
    extraction_method="manual",
)
# NOTE: we are not promoting this. Even if it were promoted, it would
# only end up in basics.truth[], never in kinship. We assert both.
built2 = H.build_profile_from_promoted(kent_id)
assert built2["kinship"] == legacy_blob["kinship"], \
    f"kinship was altered: {built2['kinship']}"
assert built2["pets"] == legacy_blob["pets"], \
    f"pets was altered: {built2['pets']}"
# And the trap value should not appear anywhere in kinship
kinship_values = [v for entry in built2["kinship"] for v in entry.values()]
assert "DECOY VALUE (test)" not in kinship_values
ok("builder: kinship + pets pass through untouched regardless of FT rows")


# ── 6. Partial conflict: remove one promoted row, legacy fills gap ────
# Simulate a narrator who has only reviewed 4 of the 5 protected fields.
# For the unreviewed one, the builder must fall through to legacy.
# We achieve this by creating a fresh narrator rather than mutating
# Kent's promoted table.
janice = H.create_person(display_name="Janice Ann Horne", narrator_type="live")
janice_id = janice["id"]
janice_legacy = {
    "basics": {
        "fullname":  "Janice A. Horne",           # legacy (wrong)
        "preferred": "Jan",                        # legacy (wrong — should be "Janice")
        "dob":       "1944-07-12",                 # legacy (correct, not promoted)
        "pob":       "Halifax, NS",                # legacy (correct, not promoted)
        "birthOrder": "second of four",
    },
    "kinship": [],
    "pets": [],
}
H.ensure_profile(janice_id)
H.update_profile_json(janice_id, janice_legacy, merge=False, reason="B1 partial")

# Promote ONLY fullname and preferred. Leave dob, pob, birthOrder as legacy.
for field, value in [
    ("personal.fullName",      "Janice Ann Horne"),
    ("personal.preferredName", "Janice"),
]:
    note = H.ft_add_note(person_id=janice_id, body=value,
                         source_kind="manual", created_by="chris")
    row = H.ft_add_row(
        person_id=janice_id, note_id=note["id"],
        subject_name="Janice Ann Horne", relationship="self",
        field=field, source_says=value, approved_value=value,
        status="needs_verify", extraction_method="manual",
    )
    H.ft_promote_row(row["id"], reviewer="chris")

jbuilt = H.build_profile_from_promoted(janice_id)
jbasics = jbuilt["basics"]
# Promoted fields win
assert jbasics["fullname"] == "Janice Ann Horne",  f"got {jbasics['fullname']!r}"
assert jbasics["preferred"] == "Janice",            f"got {jbasics['preferred']!r}"
# Un-promoted fields fall through to legacy — including ones that
# happen to agree with reality. The test here is "legacy passthrough",
# NOT "correctness of legacy".
assert jbasics["dob"] == "1944-07-12",               f"got {jbasics['dob']!r}"
assert jbasics["pob"] == "Halifax, NS",              f"got {jbasics['pob']!r}"
assert jbasics["birthOrder"] == "second of four",    f"got {jbasics['birthOrder']!r}"
ok("builder: partial conflict — 2 promoted fields win, 3 unreviewed fall through")


# ── 7. Verify source_row_id traceability on each promoted field ───────
# The Phase 8 contract does not currently expose a per-field
# provenance sidecar (that's a Phase 9 feature — basics._provenance).
# What we CAN verify today is that ft_list_promoted returns rows with
# source_row_id populated and that they match what ft_promote_row
# returned. This is the traceability floor B1 guarantees.
for field, row_id in promoted_row_ids.items():
    promoted_rec = H.ft_get_promoted(kent_id, "Kent James Horne", field)
    assert promoted_rec is not None, f"missing promoted record for {field}"
    assert promoted_rec["source_row_id"] == row_id, (
        f"{field}: source_row_id mismatch — "
        f"promoted={promoted_rec['source_row_id']!r}, expected={row_id!r}"
    )
ok("traceability: every promoted protected field points back to its FT row_id")


# ── 8. Conflict is content-addressable — re-running is idempotent ─────
# Re-promote all 5 protected rows. They should all come back as op=noop
# because the content hash hasn't changed. This is Phase 7 territory
# but we re-verify here because a B1 regression would look exactly like
# a "promoted wins but the row got re-created" bug.
import time as _time
_time.sleep(1.1)   # force a distinct _now_iso() tick if anything wrote
for field, row_id in promoted_row_ids.items():
    rec_before = H.ft_get_promoted(kent_id, "Kent James Horne", field)
    res = H.ft_promote_row(row_id, reviewer="chris")
    assert res["promoted"]["op"] == "noop", (
        f"{field}: re-promote was op={res['promoted']['op']}, expected noop"
    )
    rec_after = H.ft_get_promoted(kent_id, "Kent James Horne", field)
    assert rec_after["updated_at"] == rec_before["updated_at"], (
        f"{field}: updated_at advanced on a noop re-promote "
        f"({rec_before['updated_at']} → {rec_after['updated_at']})"
    )
ok("conflict is content-addressable: re-promoting all 5 rows → all noop")


# ── 9. Builder output after noop is byte-identical ─────────────────────
# One more safety net: build the profile again after the noop re-promote
# round and compare to the pre-noop version. Nothing should have drifted.
import json as _json
before = _json.dumps(built, sort_keys=True, default=str)
rebuilt = H.build_profile_from_promoted(kent_id)
# Pop the basics.truth entry we added in step 5 (it was seeded between
# the two builds as a trap) so the comparison is apples-to-apples.
rebuilt_cmp = dict(rebuilt)
rebuilt_cmp["basics"] = {k: v for k, v in rebuilt["basics"].items()
                         if k != "truth" and k != "_qualifications"}
original_cmp = _json.loads(before)
original_cmp["basics"] = {k: v for k, v in original_cmp["basics"].items()
                          if k != "truth" and k != "_qualifications"}
assert _json.dumps(rebuilt_cmp, sort_keys=True) == \
       _json.dumps(original_cmp, sort_keys=True), (
    "builder output drifted between pre-noop and post-noop rebuild"
)
ok("builder: output is stable across a no-op re-promote round")


print()
print("=" * 62)
print("  WO-13 Phase 8 B1 — ALL CONFLICT ASSERTIONS PASSED")
print("=" * 62)
