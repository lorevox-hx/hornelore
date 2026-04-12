"""WO-13 Phase 8 — Downstream Rewiring test harness.

Verifies the flag-gated read seam at GET /api/profiles/{person_id}, the
hybrid-read builder (promoted truth for mapped protected fields + legacy
passthrough for everything else), the cold-start backfill, and the
reference-narrator defense.

Sections:
  1.  Shared flag helper: flags.truth_v2_enabled()
  2.  Empty-promoted fallback: build_profile_from_promoted returns
      legacy shape unchanged when a narrator has zero promoted rows
  3.  Basics mapping: the 5 protected fields land in basics.*
  4.  Free-form rows go into basics.truth[]
  5.  Qualification preservation into basics._qualifications
  6.  rules_fallback protected field is blocked before it can reach
      the builder (Phase 7 invariant still holds)
  7.  Unmapped legacy basics.* keys pass through when the flag is on
  8.  GET /api/profiles/{id}: flag OFF → source='legacy'
  9.  GET /api/profiles/{id}: flag ON  → source='promoted_truth'
 10.  GET /api/profiles/{id}: builder raises → source='legacy_fallback'
      (profile still returned, no 500)
 11.  Backfill: seeds needs_verify rows from profile_json; NOT promoted
 12.  Backfill: idempotent — second call creates zero new rows
 13.  Reference narrator: build_profile_from_promoted falls through to
      legacy; backfill refuses; router backfill raises 403
 14.  Regression: Phase 4 legacy /facts/add freeze still returns 410
      under HORNELORE_TRUTH_V2=1
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

TEST_ROOT = Path(__file__).resolve().parent
os.environ["DATA_DIR"] = str(TEST_ROOT / "data")
os.environ["DB_NAME"] = "wo13_phase8_test.sqlite3"
# Start with both flags off — individual sections flip them as needed.
os.environ.pop("HORNELORE_TRUTH_V2", None)
os.environ.pop("HORNELORE_TRUTH_V2_PROFILE", None)

db_file = TEST_ROOT / "data" / "db" / os.environ["DB_NAME"]
for f in (db_file, db_file.with_suffix(".sqlite3-wal"), db_file.with_suffix(".sqlite3-shm")):
    if f.exists():
        f.unlink()

HORNELORE_PY = Path("/sessions/nice-fervent-clarke/mnt/hornelore/server/code")
sys.path.insert(0, str(HORNELORE_PY))

# ── fastapi / pydantic stubs so router imports work ────────────────────
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
from api import flags as F                                  # noqa: E402
from api.routers import profiles as profiles_router         # noqa: E402
from api.routers import family_truth as ft_router           # noqa: E402
from api.routers import facts as facts_router               # noqa: E402


def ok(msg):
    print(f"  OK  {msg}")


def fail(msg):
    print(f"  FAIL  {msg}")
    sys.exit(1)


print("=" * 62)
print("WO-13 Phase 8 — Downstream rewiring (flag seam + hybrid read)")
print("=" * 62)

H.init_db()


# ── 1. Shared flag helper ──────────────────────────────────────────────
os.environ.pop("HORNELORE_TRUTH_V2", None)
os.environ.pop("HORNELORE_TRUTH_V2_PROFILE", None)
assert F.truth_v2_enabled("facts_write") is False
assert F.truth_v2_enabled("profile") is False
assert F.truth_v2_enabled("bogus_consumer") is False
os.environ["HORNELORE_TRUTH_V2"] = "1"
assert F.truth_v2_enabled("facts_write") is True
assert F.truth_v2_enabled("profile") is False  # separate flag
os.environ["HORNELORE_TRUTH_V2_PROFILE"] = "yes"
assert F.truth_v2_enabled("profile") is True
os.environ["HORNELORE_TRUTH_V2_PROFILE"] = "off"
assert F.truth_v2_enabled("profile") is False
# Clean slate.
os.environ.pop("HORNELORE_TRUTH_V2", None)
os.environ.pop("HORNELORE_TRUTH_V2_PROFILE", None)
ok("flags: truth_v2_enabled('facts_write'|'profile'|unknown) honours env")


# ── 2. Seed narrators + legacy profile_json ────────────────────────────
ada = H.create_person(display_name="Ada Lovelace", narrator_type="live")
ada_id = ada["id"]
shatner = H.create_person(display_name="William Shatner", narrator_type="reference")
shatner_id = shatner["id"]

# Legacy profile_json blob — 5 mapped protected fields + several unmapped
# basics that must pass through under the flag.
legacy_blob = {
    "basics": {
        "fullname":  "Augusta Ada King-Noel",
        "preferred": "Ada",
        "dob":       "1815-12-10",
        "pob":       "London, England",
        "birthOrder": "only",
        # Unmapped — must pass through untouched when flag is on.
        "culture":    "English",
        "country":    "United Kingdom",
        "pronouns":   "she/her",
        "language":   "English",
        "legalFirstName":  "Augusta",
        "legalMiddleName": "Ada",
        "legalLastName":   "King-Noel",
    },
    "kinship": [
        {"relation": "mother", "name": "Anne Isabella Milbanke"},
        {"relation": "father", "name": "Lord Byron"},
    ],
    "pets": [{"name": "Puff", "kind": "cat"}],
}
H.ensure_profile(ada_id)
H.update_profile_json(ada_id, legacy_blob, merge=False, reason="phase8 harness seed")
stored = H.get_profile(ada_id)
assert stored["profile_json"]["basics"]["fullname"] == "Augusta Ada King-Noel"
ok("seed: Ada (live) + Shatner (reference) + legacy profile_json")


# ── 3. Empty-promoted fallback ─────────────────────────────────────────
# Ada has zero promoted rows. build_profile_from_promoted must return
# the legacy shape unchanged (no truth[], no _qualifications).
empty_profile = H.build_profile_from_promoted(ada_id)
assert empty_profile["basics"]["fullname"] == "Augusta Ada King-Noel"
assert empty_profile["basics"]["culture"] == "English"
assert empty_profile["basics"].get("truth") is None
assert empty_profile["basics"].get("_qualifications") is None
assert empty_profile["kinship"] == legacy_blob["kinship"]
assert empty_profile["pets"] == legacy_blob["pets"]
ok("builder: zero promoted rows → returns legacy shape verbatim (no sidecar keys)")


# ── 4. Seed promoted rows: basics mapping + truth[] + qualification ───
# (a) Protected identity field — preferredName, manual method.
note_a = H.ft_add_note(person_id=ada_id, body="I go by Ada, not Augusta.",
                       source_kind="chat", source_ref="sess1:0", created_by="Ada Lovelace")
row_a = H.ft_add_row(
    person_id=ada_id, note_id=note_a["id"],
    subject_name="Ada Lovelace", relationship="self",
    field="personal.preferredName",
    source_says="Ada",
    approved_value="Ada",
    status="needs_verify",
    extraction_method="manual",
)
res_a = H.ft_promote_row(row_a["id"], reviewer="chris")
assert res_a["promoted"]["op"] == "created"

# (b) Free-form field — employment with qualification (approve_q).
note_b = H.ft_add_note(person_id=ada_id, body="I worked with Babbage on the Analytical Engine.",
                       source_kind="chat", source_ref="sess1:1", created_by="Ada Lovelace")
row_b = H.ft_add_row(
    person_id=ada_id, note_id=note_b["id"],
    subject_name="Ada Lovelace", relationship="self",
    field="employment",
    source_says="worked with Babbage on the Analytical Engine",
    approved_value="Collaborated with Charles Babbage on the Analytical Engine, 1840s.",
    status="needs_verify",
    extraction_method="manual",
)
q_text = "Exact dates of the collaboration are disputed between sources."
res_b = H.ft_promote_row(row_b["id"], reviewer="chris", qualification=q_text)
assert res_b["row"]["status"] == "approve_q"
assert res_b["promoted"]["record"]["qualification"] == q_text

# (c) Protected + rules_fallback → promote call BLOCKED
note_c = H.ft_add_note(person_id=ada_id, body="Born 1815",
                       source_kind="chat", source_ref="sess1:2")
row_c = H.ft_add_row(
    person_id=ada_id, note_id=note_c["id"],
    subject_name="Ada Lovelace", relationship="self",
    field="personal.dateOfBirth",
    source_says="1815",
    approved_value="1815-12-10",
    status="approve",
    extraction_method="rules_fallback",
    provenance={"identity_conflict": True, "protected_field": "personal.dateOfBirth"},
)
res_c = H.ft_promoted_upsert(row_c["id"], reviewer="chris")
assert res_c["op"] == "blocked", f"expected op=blocked, got {res_c['op']}"

# (d) Free-form — residence
row_d = H.ft_add_row(
    person_id=ada_id,
    subject_name="Ada Lovelace", relationship="self",
    field="residence",
    source_says="Lived in London for most of her life.",
    approved_value="Lived in London, England.",
    status="approve",
    extraction_method="manual",
)
H.ft_promote_row(row_d["id"], reviewer="chris")
ok(f"seed: promoted truth populated for Ada (2 protected + 2 freeform; 1 blocked)")


# ── 5. Basics mapping ──────────────────────────────────────────────────
built = H.build_profile_from_promoted(ada_id)
assert built["basics"]["preferred"] == "Ada", \
    f"basics.preferred should come from promoted truth, got {built['basics'].get('preferred')}"
# dob was NEVER promoted (the only attempt was blocked), so it must fall
# through from the legacy blob.
assert built["basics"]["dob"] == "1815-12-10"
# fullname / pob / birthOrder never had promoted rows → fall through from legacy.
assert built["basics"]["fullname"] == "Augusta Ada King-Noel"
assert built["basics"]["pob"] == "London, England"
assert built["basics"]["birthOrder"] == "only"
ok("builder: 5 protected basics.* fields — promoted wins, legacy fills gaps")


# ── 6. Free-form rows in basics.truth[] ────────────────────────────────
truth = built["basics"].get("truth") or []
assert len(truth) == 2, f"expected 2 truth rows, got {len(truth)}"
fields_in_truth = sorted(r["field"] for r in truth)
assert fields_in_truth == ["employment", "residence"], fields_in_truth
emp = next(r for r in truth if r["field"] == "employment")
assert "Babbage" in emp["value"]
assert emp["status"] == "approve_q"
assert emp["qualification"] == q_text
assert emp["subject_name"] == "Ada Lovelace"
assert emp["relationship"] == "self"
ok("builder: free-form rows land in basics.truth[] with subject/relation/value/status")


# ── 7. Qualification preserved in basics._qualifications ───────────────
quals = built["basics"].get("_qualifications") or {}
assert quals.get("employment") == q_text, (
    f"employment qualification missing or wrong: {quals!r}"
)
ok("builder: qualification surfaces in basics._qualifications[<field>]")


# ── 8. Blocked protected field does NOT leak ──────────────────────────
# The dob attempt was blocked by ft_promoted_upsert; the builder must
# NOT surface any trace of it in basics.truth[] or _qualifications.
for r in truth:
    assert r["field"] != "personal.dateOfBirth", \
        "blocked protected field leaked into basics.truth[]"
assert "personal.dateOfBirth" not in quals
# And the legacy dob is still rendering.
assert built["basics"]["dob"] == "1815-12-10"
ok("builder: rules_fallback-blocked protected field never leaks into output")


# ── 9. Unmapped legacy basics keys pass through under the flag ────────
for k, v in [
    ("culture", "English"),
    ("country", "United Kingdom"),
    ("pronouns", "she/her"),
    ("language", "English"),
    ("legalFirstName", "Augusta"),
    ("legalMiddleName", "Ada"),
    ("legalLastName", "King-Noel"),
]:
    assert built["basics"].get(k) == v, f"unmapped basics.{k} did not pass through"
# kinship + pets still present.
assert built["kinship"] == legacy_blob["kinship"]
assert built["pets"] == legacy_blob["pets"]
ok("builder: unmapped basics.*, kinship, pets pass through under the flag")


# ── 10. Endpoint: flag OFF → source='legacy' ───────────────────────────
os.environ.pop("HORNELORE_TRUTH_V2_PROFILE", None)
resp_off = profiles_router.api_get_profile(ada_id)
assert resp_off["person_id"] == ada_id
assert resp_off["source"] == "legacy", f"source={resp_off['source']!r}"
# Legacy blob — preferred still the legacy value? Ada's legacy has
# preferred='Ada', and the promoted row also set 'Ada', so pick a field
# that differs under the flag. Use basics.truth absence.
assert "truth" not in (resp_off["profile"].get("basics") or {})
assert "_qualifications" not in (resp_off["profile"].get("basics") or {})
ok("endpoint: flag OFF → source='legacy', no promoted sidecar")


# ── 11. Endpoint: flag ON → source='promoted_truth' ───────────────────
os.environ["HORNELORE_TRUTH_V2_PROFILE"] = "1"
resp_on = profiles_router.api_get_profile(ada_id)
assert resp_on["source"] == "promoted_truth", f"source={resp_on['source']!r}"
assert resp_on["profile"]["basics"]["preferred"] == "Ada"
assert "truth" in resp_on["profile"]["basics"]
assert "_qualifications" in resp_on["profile"]["basics"]
assert resp_on["profile"]["basics"]["_qualifications"]["employment"] == q_text
# Unmapped passthrough survives the endpoint.
assert resp_on["profile"]["basics"]["culture"] == "English"
assert resp_on["profile"]["kinship"] == legacy_blob["kinship"]
ok("endpoint: flag ON → source='promoted_truth' + sidecar + passthrough")


# ── 12. Endpoint: builder raises → source='legacy_fallback' ───────────
# Monkey-patch build_profile_from_promoted to raise. The endpoint must
# serve the legacy blob and tag source='legacy_fallback' instead of 500.
original_builder = H.build_profile_from_promoted

def _boom(person_id):
    raise RuntimeError("simulated phase 8 builder failure")

H.build_profile_from_promoted = _boom
try:
    resp_fallback = profiles_router.api_get_profile(ada_id)
    assert resp_fallback["source"] == "legacy_fallback", \
        f"source={resp_fallback['source']!r}"
    # And the legacy blob still reaches the caller.
    assert resp_fallback["profile"]["basics"]["fullname"] == "Augusta Ada King-Noel"
    assert "truth" not in (resp_fallback["profile"].get("basics") or {})
finally:
    H.build_profile_from_promoted = original_builder
ok("endpoint: builder exception → source='legacy_fallback', no 500")


# ── 13. Cold-start backfill: seeds needs_verify rows, not promoted ────
# Fresh narrator, legacy blob only, no FT rows yet.
byron = H.create_person(display_name="George Gordon Byron", narrator_type="live")
byron_id = byron["id"]
byron_blob = {
    "basics": {
        "fullname":  "George Gordon Byron, 6th Baron Byron",
        "preferred": "Byron",
        "dob":       "1788-01-22",
        "pob":       "London, England",
        "birthOrder": "",  # empty — should be skipped by backfill
        "culture":   "English",  # unmapped — backfill ignores
    },
    "kinship": [],
    "pets": [],
}
H.ensure_profile(byron_id)
H.update_profile_json(byron_id, byron_blob, merge=False, reason="phase8 harness byron")

result = H.ft_backfill_from_profile_json(byron_id)
assert result["reference_refused"] is False
assert result["created_rows"] == 4, f"created_rows={result['created_rows']}"
assert result["skipped_empty"] == 1, f"skipped_empty={result['skipped_empty']}"
assert result["skipped_existing"] == 0

# All 4 created rows should be status='needs_verify' and NOT promoted.
rows_byron = H.ft_list_rows(person_id=byron_id, limit=100, offset=0)
assert len(rows_byron) == 4, f"expected 4 FT rows, got {len(rows_byron)}"
for r in rows_byron:
    assert r["status"] == "needs_verify", f"backfill wrote non-needs_verify row: {r}"
    assert r["extraction_method"] == "manual"
    assert r["subject_name"] == "George Gordon Byron"
    assert r["relationship"] == "self"

promoted_byron = H.ft_list_promoted(byron_id)
assert len(promoted_byron) == 0, "backfill leaked into promoted truth!"

# And with the flag ON, the profile still renders from the legacy blob
# because the backfill did NOT auto-promote.
os.environ["HORNELORE_TRUTH_V2_PROFILE"] = "1"
resp_byron = profiles_router.api_get_profile(byron_id)
assert resp_byron["source"] == "promoted_truth"
# But since nothing was promoted, the builder fell through to legacy values.
assert resp_byron["profile"]["basics"]["fullname"] == \
    "George Gordon Byron, 6th Baron Byron"
ok("backfill: seeds 4 needs_verify rows + 1 skipped_empty; promoted empty")


# ── 14. Backfill idempotency ──────────────────────────────────────────
result2 = H.ft_backfill_from_profile_json(byron_id)
assert result2["created_rows"] == 0, f"re-run created {result2['created_rows']} rows"
assert result2["skipped_existing"] == 4, f"skipped_existing={result2['skipped_existing']}"
assert result2["skipped_empty"] == 1
# Still exactly 4 rows on Byron.
rows_byron2 = H.ft_list_rows(person_id=byron_id, limit=100, offset=0)
assert len(rows_byron2) == 4
ok("backfill: idempotent — second call creates 0, skips 4 existing")


# ── 15. Reference narrator guard on backfill (db + router) ────────────
# db-level helper: returns reference_refused=True, no rows created
H.ensure_profile(shatner_id)
H.update_profile_json(shatner_id, {"basics": {"fullname": "William Shatner",
                                                "preferred": "Bill",
                                                "dob": "1931-03-22",
                                                "pob": "Montreal, Quebec"}},
                      merge=False, reason="phase8 harness shatner")
shat_result = H.ft_backfill_from_profile_json(shatner_id)
assert shat_result["reference_refused"] is True
assert shat_result["created_rows"] == 0
shat_rows = H.ft_list_rows(person_id=shatner_id, limit=100, offset=0)
assert len(shat_rows) == 0, "backfill wrote to reference narrator!"

# router-level: raises 403
try:
    ft_router.api_backfill(ft_router.BackfillRequest(person_id=shatner_id))
    raise AssertionError("router api_backfill did not refuse reference narrator")
except ft_router.HTTPException as e:
    assert e.status_code == 403, f"expected 403, got {e.status_code}"
ok("backfill guards: db returns reference_refused; router raises 403")


# ── 16. Reference narrator profile read under the flag ────────────────
# Shatner has no FT rows at all, so build_profile_from_promoted must
# fall through to legacy. Router api_get_profile should NOT blow up.
os.environ["HORNELORE_TRUTH_V2_PROFILE"] = "1"
resp_shat = profiles_router.api_get_profile(shatner_id)
assert resp_shat["profile"]["basics"]["fullname"] == "William Shatner"
# Source will be 'promoted_truth' because the flag is on and the builder
# succeeded; the empty-promoted fallback path inside the builder still
# returns the legacy shape, just tagged as promoted_truth by the endpoint.
assert resp_shat["source"] == "promoted_truth"
ok("reference narrator: profile read under flag falls through to legacy data")


# ── 17. Regression — Phase 4 legacy facts-write freeze still works ────
os.environ["HORNELORE_TRUTH_V2"] = "1"
try:
    facts_router.api_add_fact(facts_router.FactAddRequest(
        person_id=ada_id, statement="unit test", fact_type="general",
        date_text="", date_normalized="", confidence=0.0, status="extracted",
        inferred=False, session_id=None, source_turn_index=None,
        meta={}, meaning_tags=[], narrative_role=None,
        experience=None, reflection=None,
    ))
    raise AssertionError("facts.add should be 410 under HORNELORE_TRUTH_V2")
except facts_router.HTTPException as e:
    assert e.status_code == 410, f"expected 410, got {e.status_code}"
os.environ.pop("HORNELORE_TRUTH_V2", None)
ok("regression: Phase 4 /facts/add 410 Gone still enforced via shared flag helper")


# ── 18. End-to-end trace for the proof packet ─────────────────────────
import json as _json
e2e = {
    "narrator": {"person_id": ada_id, "display_name": "Ada Lovelace"},
    "legacy_basics": legacy_blob["basics"],
    "flag_off_source": resp_off["source"],
    "flag_on_source":  "promoted_truth",
    "flag_on_basics":  {
        "preferred": built["basics"]["preferred"],
        "fullname":  built["basics"]["fullname"],
        "dob":       built["basics"]["dob"],
        "culture":   built["basics"]["culture"],
    },
    "truth_rows":     truth,
    "qualifications": built["basics"].get("_qualifications"),
    "blocked_field":  "personal.dateOfBirth (rules_fallback)",
    "backfill_result": result,
    "backfill_idempotent_result": result2,
    "reference_refused": {
        "db":    shat_result["reference_refused"],
        "router": 403,
    },
}
trace_path = TEST_ROOT / "data" / "phase8_e2e_trace.json"
trace_path.write_text(_json.dumps(e2e, indent=2, default=str))
ok(f"end-to-end trace: saved to {trace_path.name}")


# ── 19. Regression — earlier-phase invariants still hold ──────────────
# Phase 1/3 tables still exist
con = H._connect()
for t in ("family_truth_notes", "family_truth_rows", "family_truth_promoted",
          "profiles", "people"):
    r = con.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{t}';").fetchone()
    assert r is not None, f"table missing: {t}"
con.close()
# Phase 7 protected-field set unchanged
assert len(H.FT_PROTECTED_IDENTITY_FIELDS) == 5
# Phase 7 content-hash UPSERT still idempotent
again = H.ft_promote_row(row_a["id"], reviewer="chris")
assert again["promoted"]["op"] == "noop"
ok("regression: FT tables present, protected set unchanged, UPSERT still idempotent")


print()
print("=" * 62)
print("  WO-13 Phase 8 — ALL ASSERTIONS PASSED")
print("=" * 62)
