"""WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01 — Phase 2B orchestrator tests.

Covers the POST /api/people/intake fan-out endpoint:
  - All 9 nested intake-payload Pydantic models declared
  - NarratorIntakePayload carries identity + 7 optional section slots
  - Route validates pronoun enum + consent gate BEFORE create_person
  - Route calls update_profile_json with merge=True
  - Route calls _write_bio_fact_safe for each scalar field section
  - testing_only=True bypasses the consent gate but still runs
    create_person + the profile_json + bio_facts fan-out
  - _write_bio_fact_safe correctly drops unknown field_keys + empty
    values without raising

Source-inspection contracts keep the fan-out invariants honest if anyone
refactors the route or moves helpers. Direct DB-backed tests cover the
write helpers themselves where possible.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))


def _read_people_src() -> str:
    return (_SERVER_CODE / "api" / "routers" / "people.py").read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────
# Pydantic model contract — source-inspection
# ─────────────────────────────────────────────────────────────────────


class NestedModelDeclarationTest(unittest.TestCase):
    """Every nested IntakeXxx model the orchestrator promises must
    exist as a class declaration in people.py."""

    def setUp(self):
        self.src = _read_people_src()

    def test_intake_sibling_declared(self):
        self.assertIn("class IntakeSibling(_BaseModel):", self.src)

    def test_intake_spouse_declared(self):
        self.assertIn("class IntakeSpouse(_BaseModel):", self.src)

    def test_intake_child_declared(self):
        self.assertIn("class IntakeChild(_BaseModel):", self.src)

    def test_intake_family_of_origin_declared(self):
        self.assertIn("class IntakeFamilyOfOrigin(_BaseModel):", self.src)

    def test_intake_marriage_declared(self):
        self.assertIn("class IntakeMarriage(_BaseModel):", self.src)

    def test_intake_education_work_declared(self):
        self.assertIn("class IntakeEducationWork(_BaseModel):", self.src)

    def test_intake_military_declared(self):
        self.assertIn("class IntakeMilitary(_BaseModel):", self.src)

    def test_intake_faith_declared(self):
        self.assertIn("class IntakeFaith(_BaseModel):", self.src)

    def test_intake_today_declared(self):
        self.assertIn("class IntakeToday(_BaseModel):", self.src)

    def test_narrator_intake_payload_declared(self):
        self.assertIn("class NarratorIntakePayload(_BaseModel):", self.src)


class NarratorIntakePayloadShapeTest(unittest.TestCase):
    """NarratorIntakePayload must declare the identity floor + 7
    optional section slots in the right types."""

    def setUp(self):
        self.src = _read_people_src()
        # Slice from class start to the next top-level def (the
        # following fan-out helpers) so all NarratorIntakePayload field
        # declarations are inside the window.
        start = self.src.find("class NarratorIntakePayload(_BaseModel):")
        next_def = self.src.find("\ndef ", start)
        end = next_def if next_def > 0 else start + 4000
        self.body = self.src[start:end]

    def test_identity_required_fields(self):
        for fld in (
            "full_legal_name: str",
            "preferred_name: str",
            "date_of_birth: str",
            "place_of_birth: str",
            "pronouns: str",
            "current_residence: str",
        ):
            with self.subTest(field=fld):
                self.assertIn(fld, self.body)

    def test_consent_fields(self):
        for fld in (
            "consent_recording_agreement: bool",
            "consent_disclosure_reviewed: bool",
            "testing_only: bool",
        ):
            with self.subTest(field=fld):
                self.assertIn(fld, self.body)

    def test_optional_section_slots(self):
        for fld in (
            "family_of_origin: Optional[IntakeFamilyOfOrigin]",
            "marriage: Optional[IntakeMarriage]",
            "children: List[IntakeChild]",
            "education_work: Optional[IntakeEducationWork]",
            "military: Optional[IntakeMilitary]",
            "faith: Optional[IntakeFaith]",
            "today: Optional[IntakeToday]",
        ):
            with self.subTest(field=fld):
                self.assertIn(fld, self.body)


# ─────────────────────────────────────────────────────────────────────
# Orchestrator route contract — source-inspection
# ─────────────────────────────────────────────────────────────────────


class IntakeRouteValidationOrderTest(unittest.TestCase):
    """POST /api/people/intake must validate identity + pronoun +
    consent gates BEFORE calling create_person. Source-inspection
    keeps the gate ordering honest under refactors."""

    def setUp(self):
        self.src = _read_people_src()
        start = self.src.find("def api_create_person_intake(")
        self.assertGreater(start, 0, msg="intake route handler missing")
        # Slice ~20k chars to capture the full handler body
        self.body = self.src[start:start + 20000]

    def test_route_decorator_present(self):
        self.assertIn('@router.post("/intake"', self.src)

    def test_required_identity_gate_before_create(self):
        # "is required" appears in the identity field-required gate.
        identity_idx = self.body.find("is required")
        create_idx = self.body.find("person = create_person(")
        self.assertGreater(identity_idx, 0, msg="identity required gate missing")
        self.assertGreater(create_idx, 0, msg="create_person call missing")
        self.assertLess(identity_idx, create_idx)

    def test_pronoun_enum_gate_before_create(self):
        pron_idx = self.body.find("_PRONOUN_CHOICES")
        create_idx = self.body.find("person = create_person(")
        self.assertGreater(pron_idx, 0)
        self.assertLess(pron_idx, create_idx)

    def test_consent_gate_before_create(self):
        # Both consent gates must run before create_person
        rec_idx = self.body.find("consent_recording_agreement must be true")
        disc_idx = self.body.find("consent_disclosure_reviewed must be true")
        create_idx = self.body.find("person = create_person(")
        self.assertGreater(rec_idx, 0)
        self.assertGreater(disc_idx, 0)
        self.assertLess(rec_idx, create_idx)
        self.assertLess(disc_idx, create_idx)

    def test_testing_only_bypasses_consent(self):
        # The "if not payload.testing_only" guard must wrap the consent
        # gate (so consent is skipped for testing-only narrators).
        testing_idx = self.body.find("if not payload.testing_only")
        rec_idx = self.body.find("consent_recording_agreement must be true")
        self.assertGreater(testing_idx, 0)
        self.assertLess(testing_idx, rec_idx)


class IntakeRouteFanOutTest(unittest.TestCase):
    """The orchestrator route must touch the 4 expected writers:
    create_person, consent_attestation_create, update_profile_json,
    and bio_fact_create (via _write_bio_fact_safe)."""

    def setUp(self):
        self.src = _read_people_src()
        start = self.src.find("def api_create_person_intake(")
        self.body = self.src[start:start + 20000]

    def test_calls_create_person(self):
        self.assertIn("person = create_person(", self.body)

    def test_calls_consent_attestation_create(self):
        self.assertIn("consent_attestation_create(", self.body)

    def test_calls_update_profile_json_with_merge(self):
        self.assertIn("update_profile_json(", self.body)
        self.assertIn("merge=True", self.body)

    def test_calls_write_bio_fact_safe(self):
        # Either direct call or the local _try_write_fact helper that
        # routes to _write_bio_fact_safe
        self.assertTrue(
            "_write_bio_fact_safe(" in self.body
            or "_try_write_fact(" in self.body,
            msg="orchestrator must route scalar facts through "
                "_write_bio_fact_safe / _try_write_fact",
        )

    def test_returns_per_section_summary(self):
        for key in (
            "consent_attestations",
            "consent_errors",
            "bio_facts_written",
            "profile_json_error",
        ):
            with self.subTest(key=key):
                self.assertIn(key, self.body)


class IntakeFanOutSectionCoverageTest(unittest.TestCase):
    """Each of the 7 optional sections must show up in the fan-out
    body so a future refactor doesn't accidentally drop persistence
    for a whole section. Source-inspection only — we look for the
    payload accessor on each section."""

    def setUp(self):
        self.src = _read_people_src()
        start = self.src.find("def api_create_person_intake(")
        self.body = self.src[start:start + 20000]

    def test_family_of_origin_handled(self):
        self.assertIn("payload.family_of_origin", self.body)

    def test_marriage_handled(self):
        self.assertIn("payload.marriage", self.body)

    def test_children_handled(self):
        self.assertIn("payload.children", self.body)

    def test_education_work_handled(self):
        self.assertIn("payload.education_work", self.body)

    def test_military_served_gate(self):
        # Military section must only write its details when served=True
        self.assertIn("payload.military", self.body)
        self.assertIn("mil.served", self.body)

    def test_faith_handled(self):
        self.assertIn("payload.faith", self.body)

    def test_today_handled(self):
        self.assertIn("payload.today", self.body)


# ─────────────────────────────────────────────────────────────────────
# Direct helper tests — _split_name, _pronoun_label, _write_bio_fact_safe
# ─────────────────────────────────────────────────────────────────────


class SplitNameTest(unittest.TestCase):
    """_split_name handles the typical name shapes encountered in
    operator-entered family-of-origin data."""

    def _load(self):
        # Source-inspect the helper rather than import, since fastapi may
        # be unavailable in the test sandbox.
        src = _read_people_src()
        return src

    def test_split_name_helper_declared(self):
        src = self._load()
        self.assertIn("def _split_name(full_name: str) -> Dict[str, str]:", src)

    def test_split_name_three_token_uses_middle_name(self):
        # The 3+ token branch must emit middleName
        src = self._load()
        start = src.find("def _split_name(")
        body = src[start:start + 1500]
        self.assertIn('"middleName"', body)

    def test_pronoun_label_helper_declared(self):
        src = self._load()
        self.assertIn('def _pronoun_label(pron: str, other: str) -> str:', src)
        # All 4 enum branches must appear
        for slug in ('"she_her"', '"he_him"', '"they_them"', '"other"'):
            with self.subTest(slug=slug):
                self.assertIn(slug, src)


class WriteBioFactSafeContractTest(unittest.TestCase):
    """The Tier-4 bio_facts writer must skip unknown field_keys + empty
    values + bubble all failures into the per-call return (None)."""

    def setUp(self):
        self.src = _read_people_src()
        start = self.src.find("def _write_bio_fact_safe(")
        self.assertGreater(start, 0,
                           msg="_write_bio_fact_safe helper missing")
        self.body = self.src[start:start + 2500]

    def test_validates_field_key_via_bio_schema(self):
        # Must look the field up in the bio_schema seed first
        self.assertIn("get_field_by_key", self.body)
        self.assertIn("return None", self.body)

    def test_writes_status_operator_entered(self):
        self.assertIn('status="operator_entered"', self.body)

    def test_passes_operator_id_in_source(self):
        # source_payload must carry tier=4 + operator_id + via tag
        self.assertIn('"tier": 4', self.body)
        self.assertIn('"operator_id"', self.body)
        self.assertIn('"via": "intake_form"', self.body)

    def test_never_raises_on_exception(self):
        # Final guard: try/except wrapping must catch broadly so a
        # single field's failure can't break the fan-out loop.
        self.assertIn("except Exception:", self.body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
