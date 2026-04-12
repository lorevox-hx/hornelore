"""WO-13 Phase 8 — B2 edge test: flag-flip mid-session schema additivity.

Scenario: a client loads a narrator's profile with
HORNELORE_TRUTH_V2_PROFILE unset, caches it, and continues the session.
Sometime during the session (or between sessions, but with the same
cached state on the client) the operator flips the env var on. The
client's next fetch hits the same endpoint and now gets the promoted-
truth shape with sidecar keys. Then the operator rolls back by
unsetting the var, and the client fetches yet again.

The property we need: the schema transition is STRICTLY ADDITIVE. Every
key that exists in the flag-off response also exists in the flag-on
response, with the same type. The only keys that appear under flag-on
and not under flag-off are the two documented sidecars
(basics._qualifications, basics.truth). Kinship and pets structures
are invariant across all flag states. This is what lets
normalizeProfile on the client tolerate the flip without choking —
the client side is verified separately in B3 (jsdom).

B2 explicitly does NOT verify:
  - client-side normalizeProfile behaviour (that's B3)
  - any mutation of family_truth_* tables during the flip (there
    shouldn't be any; the flag is read-only)

B2 explicitly DOES verify:
  - strict additivity of flag-on over flag-off schema
  - round-trip stability: OFF → ON → OFF returns identical OFF shape
  - ON → OFF → ON also round-trips cleanly
  - source envelope transitions cleanly (legacy ↔ promoted_truth)
  - no FT table mutations happen as a side effect of reading
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

TEST_ROOT = Path(__file__).resolve().parent
os.environ["DATA_DIR"] = str(TEST_ROOT / "data")
os.environ["DB_NAME"] = "wo13_phase8_b2_flagflip_test.sqlite3"
os.environ.pop("HORNELORE_TRUTH_V2", None)
os.environ.pop("HORNELORE_TRUTH_V2_PROFILE", None)

db_file = TEST_ROOT / "data" / "db" / os.environ["DB_NAME"]
for f in (db_file, db_file.with_suffix(".sqlite3-wal"), db_file.with_suffix(".sqlite3-shm")):
    if f.exists():
        f.unlink()

HORNELORE_PY = Path("/sessions/nice-fervent-clarke/mnt/hornelore/server/code")
sys.path.insert(0, str(HORNELORE_PY))

# ── fastapi / pydantic stubs ────────────────────────────────────────────
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

from api import db as H                                     # noqa: E402
from api.routers import profiles as profiles_router          # noqa: E402


def ok(msg):
    print(f"  OK  {msg}")


def fail(msg):
    print(f"  FAIL  {msg}")
    sys.exit(1)


# The two sidecar keys that are legally allowed to appear on basics
# under flag-on but not flag-off. This set is load-bearing — adding
# anything here means widening the Phase 8 additive contract and
# should be a deliberate decision, not a silent creep.
ALLOWED_SIDECAR_KEYS = {"_qualifications", "truth"}


def _assert_additive(off_basics: dict, on_basics: dict, context: str):
    """Every key in off must be in on with the same type.
    on may have additional keys, but only from ALLOWED_SIDECAR_KEYS."""
    off_keys = set(off_basics.keys())
    on_keys  = set(on_basics.keys())
    missing_from_on = off_keys - on_keys
    assert not missing_from_on, (
        f"[{context}] keys disappeared when flag flipped on: {missing_from_on}"
    )
    new_in_on = on_keys - off_keys
    unexpected = new_in_on - ALLOWED_SIDECAR_KEYS
    assert not unexpected, (
        f"[{context}] unexpected new keys under flag ON: {unexpected}. "
        f"Allowed sidecar keys: {sorted(ALLOWED_SIDECAR_KEYS)}"
    )
    # Type invariance: every legacy key's type must match across flags.
    for k in off_keys:
        off_type = type(off_basics[k]).__name__
        on_type  = type(on_basics[k]).__name__
        assert off_type == on_type, (
            f"[{context}] basics.{k}: type changed {off_type}→{on_type}"
        )


print("=" * 62)
print("WO-13 Phase 8 B2 — flag-flip mid-session schema additivity")
print("=" * 62)

H.init_db()

# ── 1. Seed narrator with legacy + 2 promoted rows ────────────────────
lovelace = H.create_person(display_name="Ada Lovelace", narrator_type="live")
ada_id = lovelace["id"]

legacy_blob = {
    "basics": {
        "fullname":  "Augusta Ada King-Noel",
        "preferred": "Ada",
        "dob":       "1815-12-10",
        "pob":       "London, England",
        "birthOrder": "only",
        # Unmapped keys that must survive the flip intact.
        "culture":   "English",
        "country":   "United Kingdom",
        "pronouns":  "she/her",
    },
    "kinship": [
        {"relation": "mother", "name": "Anne Isabella Milbanke"},
        {"relation": "father", "name": "Lord Byron"},
    ],
    "pets": [{"name": "Puff", "kind": "cat"}],
}
H.ensure_profile(ada_id)
H.update_profile_json(ada_id, legacy_blob, merge=False, reason="B2 flagflip seed")

# Promote one protected field (preferredName) and one free-form field
# (employment, with qualification). That ensures flag-on will have BOTH
# sidecar keys populated, not just one.
note_pref = H.ft_add_note(person_id=ada_id, body="Goes by Ada",
                          source_kind="manual", created_by="chris")
row_pref = H.ft_add_row(
    person_id=ada_id, note_id=note_pref["id"],
    subject_name="Ada Lovelace", relationship="self",
    field="personal.preferredName",
    source_says="Ada", approved_value="Ada",
    status="needs_verify", extraction_method="manual",
)
H.ft_promote_row(row_pref["id"], reviewer="chris")

note_emp = H.ft_add_note(person_id=ada_id, body="Worked with Babbage",
                         source_kind="manual", created_by="chris")
row_emp = H.ft_add_row(
    person_id=ada_id, note_id=note_emp["id"],
    subject_name="Ada Lovelace", relationship="self",
    field="employment",
    source_says="worked with Babbage",
    approved_value="Collaborated with Charles Babbage on the Analytical Engine.",
    status="needs_verify", extraction_method="manual",
)
q_text = "Exact dates of the collaboration are disputed."
H.ft_promote_row(row_emp["id"], reviewer="chris", qualification=q_text)
ok("seed: Ada with legacy basics + 1 protected + 1 free-form promoted row")


# ── 2. Snapshot current FT table state so we can assert no mutations ──
def _ft_snapshot(pid: str) -> dict:
    return {
        "notes":    len(H.ft_list_notes(person_id=pid, limit=1000, offset=0)),
        "rows":     len(H.ft_list_rows(person_id=pid, limit=1000, offset=0)),
        "promoted": len(H.ft_list_promoted(pid, limit=1000, offset=0)),
    }

ft_before = _ft_snapshot(ada_id)
assert ft_before == {"notes": 2, "rows": 2, "promoted": 2}, \
    f"unexpected FT state: {ft_before}"
ok(f"FT snapshot: notes=2 rows=2 promoted=2 (baseline)")


# ── 3. Transition 1: OFF → ON ─────────────────────────────────────────
os.environ.pop("HORNELORE_TRUTH_V2_PROFILE", None)
resp_off_1 = profiles_router.api_get_profile(ada_id)
assert resp_off_1["source"] == "legacy"
off_basics_1 = resp_off_1["profile"]["basics"]
# Flag-off must not surface any sidecar keys
for k in ALLOWED_SIDECAR_KEYS:
    assert k not in off_basics_1, \
        f"flag-off leaked sidecar key basics.{k}: {off_basics_1[k]}"
ok("flag OFF (1st read): source='legacy', no sidecar keys")

os.environ["HORNELORE_TRUTH_V2_PROFILE"] = "1"
resp_on = profiles_router.api_get_profile(ada_id)
assert resp_on["source"] == "promoted_truth"
on_basics = resp_on["profile"]["basics"]
assert "_qualifications" in on_basics, "flag-on missing _qualifications sidecar"
assert "truth" in on_basics, "flag-on missing truth[] sidecar"
assert on_basics["_qualifications"]["employment"] == q_text
assert any(r["field"] == "employment" for r in on_basics["truth"])
ok("flag ON: source='promoted_truth', both sidecar keys populated")

# Additivity check for the OFF→ON transition.
_assert_additive(off_basics_1, on_basics, "OFF→ON")
ok("transition OFF→ON is strictly additive: legacy keys preserved, types invariant")


# ── 4. Transition 2: ON → OFF (rollback) ──────────────────────────────
os.environ.pop("HORNELORE_TRUTH_V2_PROFILE", None)
resp_off_2 = profiles_router.api_get_profile(ada_id)
assert resp_off_2["source"] == "legacy"
off_basics_2 = resp_off_2["profile"]["basics"]
for k in ALLOWED_SIDECAR_KEYS:
    assert k not in off_basics_2, \
        f"post-rollback flag-off leaked sidecar key basics.{k}"
ok("flag OFF (post-rollback): source='legacy', sidecar keys cleared")


# ── 5. OFF1 vs OFF2 byte-identical (flag flip is read-only) ───────────
import json as _json
off_1_json = _json.dumps(resp_off_1["profile"], sort_keys=True, default=str)
off_2_json = _json.dumps(resp_off_2["profile"], sort_keys=True, default=str)
assert off_1_json == off_2_json, (
    "flag flip mutated the legacy response shape — this is a regression"
)
ok("flag flip is read-only: OFF shape is byte-identical before and after ON")


# ── 6. Transition 3: OFF → ON → OFF → ON (rapid flip) ─────────────────
# Stress the flip. The client-side reality is that the env var can
# change at any moment between two fetches, and the server must
# always return a coherent response.
os.environ["HORNELORE_TRUTH_V2_PROFILE"] = "1"
resp_on_2 = profiles_router.api_get_profile(ada_id)
assert resp_on_2["source"] == "promoted_truth"
# Byte-equal to the previous ON read? It should be, because the
# underlying promoted rows haven't moved.
on_1_json = _json.dumps(resp_on["profile"], sort_keys=True, default=str)
on_2_json = _json.dumps(resp_on_2["profile"], sort_keys=True, default=str)
assert on_1_json == on_2_json, (
    "two ON reads produced different profiles — non-determinism"
)
ok("rapid flip: two ON reads are byte-identical (deterministic)")


# ── 7. Kinship + pets invariance across every transition ─────────────
for label, resp in [
    ("off_1", resp_off_1),
    ("on",    resp_on),
    ("off_2", resp_off_2),
    ("on_2",  resp_on_2),
]:
    k = resp["profile"]["kinship"]
    p = resp["profile"]["pets"]
    assert k == legacy_blob["kinship"], \
        f"[{label}] kinship mutated: {k}"
    assert p == legacy_blob["pets"], \
        f"[{label}] pets mutated: {p}"
ok("kinship + pets are invariant across all four flag transitions")


# ── 8. Envelope shape invariance ─────────────────────────────────────
# Every response must carry {person_id, profile, updated_at, source}.
REQUIRED_ENVELOPE = {"person_id", "profile", "updated_at", "source"}
for label, resp in [("off_1", resp_off_1), ("on", resp_on),
                    ("off_2", resp_off_2), ("on_2", resp_on_2)]:
    keys = set(resp.keys())
    missing = REQUIRED_ENVELOPE - keys
    assert not missing, f"[{label}] envelope missing keys: {missing}"
    assert resp["person_id"] == ada_id
ok("envelope: all 4 responses carry {person_id, profile, updated_at, source}")


# ── 9. No FT mutations — reading never writes ─────────────────────────
ft_after = _ft_snapshot(ada_id)
assert ft_after == ft_before, (
    f"FT state mutated during flag-flip reads: "
    f"before={ft_before}, after={ft_after}"
)
ok(f"FT snapshot unchanged: notes=2 rows=2 promoted=2 (no side effects)")


# ── 10. Value drift is documented, not silent ─────────────────────────
# Under the flag, basics.preferred comes from promoted truth. In this
# fixture both legacy and promoted are "Ada", so the value is the same
# — but we still assert the precedence explicitly, because the "no
# value drift under flip" claim is only true when they agree. When
# they disagree, the promoted value wins, and that's already tested
# in B1. B2's job is just to verify that B2 doesn't contradict B1.
assert off_basics_1["preferred"] == "Ada"
assert on_basics["preferred"] == "Ada"
# And the SOURCE of the value is different even though the value
# matches — under flag-on, it came from promoted truth; under
# flag-off, from the legacy blob. This is a contract distinction,
# not a test failure.
ok("value precedence: preferred='Ada' in both (B1 tested disagreement)")


# ── 11. Source field transitions cleanly ─────────────────────────────
transition_sequence = [
    (resp_off_1["source"], "legacy"),
    (resp_on["source"],    "promoted_truth"),
    (resp_off_2["source"], "legacy"),
    (resp_on_2["source"],  "promoted_truth"),
]
for actual, expected in transition_sequence:
    assert actual == expected, f"source transition wrong: {actual} != {expected}"
ok("source envelope: legacy → promoted_truth → legacy → promoted_truth")


# ── 12. Trace file for the B-round evidence packet ───────────────────
trace = {
    "narrator": {"person_id": ada_id, "display_name": "Ada Lovelace"},
    "transitions": [
        {"label": "off_1",  "source": resp_off_1["source"],
         "basics_key_count": len(off_basics_1),
         "sidecar_keys_present": sorted(set(off_basics_1.keys())
                                        & ALLOWED_SIDECAR_KEYS)},
        {"label": "on",     "source": resp_on["source"],
         "basics_key_count": len(on_basics),
         "sidecar_keys_present": sorted(set(on_basics.keys())
                                        & ALLOWED_SIDECAR_KEYS)},
        {"label": "off_2",  "source": resp_off_2["source"],
         "basics_key_count": len(off_basics_2),
         "sidecar_keys_present": sorted(set(off_basics_2.keys())
                                        & ALLOWED_SIDECAR_KEYS)},
        {"label": "on_2",   "source": resp_on_2["source"],
         "basics_key_count": len(resp_on_2["profile"]["basics"]),
         "sidecar_keys_present": sorted(set(resp_on_2["profile"]["basics"].keys())
                                        & ALLOWED_SIDECAR_KEYS)},
    ],
    "ft_snapshot_before": ft_before,
    "ft_snapshot_after":  ft_after,
    "allowed_sidecar_keys": sorted(ALLOWED_SIDECAR_KEYS),
}
trace_path = TEST_ROOT / "data" / "phase8_b2_flagflip_trace.json"
trace_path.write_text(_json.dumps(trace, indent=2, default=str))
ok(f"trace: saved to {trace_path.name}")


# Clean up env so downstream tests don't inherit a hot flag.
os.environ.pop("HORNELORE_TRUTH_V2_PROFILE", None)

print()
print("=" * 62)
print("  WO-13 Phase 8 B2 — ALL FLAG-FLIP ASSERTIONS PASSED")
print("=" * 62)
