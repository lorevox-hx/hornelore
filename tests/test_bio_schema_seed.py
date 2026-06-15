"""WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase A seed tests.

Covers acceptance gates #1 (schema seeded with universal fields) and
#11 (universal applicability — no Horne-specific assumptions). The
db.py CRUD layer is tested separately under test_bio_facts_crud.py
once Phase B lands — these tests focus on the seed itself.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services.bio_schema import (  # noqa: E402
    BIO_SCHEMA_SEED,
    FIELD_CATEGORIES,
    FIELD_TYPES,
    NARRATIVE_VALUES,
    LIFE_STAGE_RANGES,
    get_field_by_key,
    get_fields_by_category,
    get_field_keys,
    get_high_value_fields,
    iter_seed,
    validate_seed,
)


class SeedIntegrityTest(unittest.TestCase):
    def test_seed_validates_clean(self):
        # Every field passes enum + shape checks
        errors = validate_seed()
        self.assertEqual(errors, [], msg=f"Validation failures: {errors}")

    def test_seed_size_reasonable(self):
        # Spec says ~80 fields; assert at least 60 (allow room for
        # future additions without immediately breaking the test).
        self.assertGreaterEqual(len(BIO_SCHEMA_SEED), 60)

    def test_field_keys_unique(self):
        keys = [fd.field_key for fd in BIO_SCHEMA_SEED]
        self.assertEqual(len(keys), len(set(keys)))

    def test_iter_seed_returns_all_entries(self):
        self.assertEqual(list(iter_seed()), list(BIO_SCHEMA_SEED))

    def test_get_field_keys_returns_full_set(self):
        keys = get_field_keys()
        self.assertEqual(keys, {fd.field_key for fd in BIO_SCHEMA_SEED})


class CategoryCoverageTest(unittest.TestCase):
    def test_every_category_has_at_least_one_field(self):
        # Per acceptance gate #1: ~80 fields across all 8 categories
        for cat in FIELD_CATEGORIES:
            with self.subTest(category=cat):
                fields = get_fields_by_category(cat)
                self.assertGreater(
                    len(fields), 0,
                    msg=f"Category {cat} has zero seeded fields",
                )

    def test_unknown_category_returns_empty(self):
        self.assertEqual(get_fields_by_category("not_a_category"), [])

    def test_category_distribution_is_balanced(self):
        # No single category dominates >50% of the seed (heuristic
        # check that the universal coverage isn't lopsided toward
        # one life domain).
        total = len(BIO_SCHEMA_SEED)
        for cat in FIELD_CATEGORIES:
            count = len(get_fields_by_category(cat))
            ratio = count / total if total else 0
            with self.subTest(category=cat):
                self.assertLess(
                    ratio, 0.50,
                    msg=f"Category {cat} dominates ({count}/{total})",
                )


class NarrativeValueDistributionTest(unittest.TestCase):
    def test_at_least_some_high_value_fields(self):
        # Tier 3 (anchored asker) only fires on narrative_value=high
        # fields. If the seed has zero of these, Tier 3 is structurally
        # disabled. Sanity check that this isn't the case.
        highs = get_high_value_fields()
        self.assertGreater(len(highs), 10)

    def test_every_narrative_value_present(self):
        seen = {fd.narrative_value for fd in BIO_SCHEMA_SEED}
        # high + medium + low all must appear so the operator picker
        # surfaces field-prioritization controls meaningfully
        self.assertEqual(seen, set(NARRATIVE_VALUES))

    def test_low_value_fields_have_no_anchors(self):
        # narrative_value=low means "operator-entry only". Anchors on
        # a low-value field would be misleading — the anchored asker
        # filters by narrative_value AND falls back on anchor presence
        # as the deactivation signal. Belt + suspenders: keep them
        # consistent in the seed.
        for fd in BIO_SCHEMA_SEED:
            if fd.narrative_value == "low":
                with self.subTest(field=fd.field_key):
                    self.assertEqual(
                        fd.asking_anchors, (),
                        msg=f"low-value field {fd.field_key} has anchors",
                    )


class AskingAnchorsWellFormedTest(unittest.TestCase):
    def test_high_value_fields_have_anchors_when_eligible(self):
        # WO §0a: high-value fields without anchors are deactivation
        # signals (Tier 3 cannot match them). Most high-value fields
        # should have at least one anchor; a small number of
        # high-value-but-explicitly-non-askable fields (e.g.,
        # field captured only by extraction) may exist.
        highs = [fd for fd in BIO_SCHEMA_SEED if fd.narrative_value == "high"]
        with_anchors = [fd for fd in highs if len(fd.asking_anchors) > 0]
        # At least 80% of high-value fields should be Tier 3 eligible.
        self.assertGreater(
            len(with_anchors) / len(highs),
            0.80,
            msg=f"Only {len(with_anchors)}/{len(highs)} high-value fields "
                f"have anchors",
        )

    def test_anchors_are_lowercase(self):
        for fd in BIO_SCHEMA_SEED:
            for anchor in fd.asking_anchors:
                with self.subTest(field=fd.field_key, anchor=anchor):
                    self.assertEqual(anchor, anchor.lower())

    def test_anchors_are_short(self):
        # Anchors > 60 chars are probably whole sentences, which means
        # they almost never match. Cap as a sanity guard.
        for fd in BIO_SCHEMA_SEED:
            for anchor in fd.asking_anchors:
                with self.subTest(field=fd.field_key, anchor=anchor):
                    self.assertLessEqual(len(anchor), 60)

    def test_asking_anchors_json_roundtrip(self):
        for fd in BIO_SCHEMA_SEED:
            recovered = json.loads(fd.asking_anchors_json())
            self.assertEqual(recovered, list(fd.asking_anchors))


class UniversalApplicabilityTest(unittest.TestCase):
    """Acceptance gate #11: the seed contains zero Horne-family-specific
    fields. Verified by checking that no field_key or field_label
    references Horne family names or locations the seed shouldn't
    privilege."""

    def test_no_horne_specific_keys(self):
        forbidden_substrings = (
            "horne", "janice", "kent", "christopher_horne",
            "stanley", "pasco_high",
        )
        for fd in BIO_SCHEMA_SEED:
            joined = (fd.field_key + " " + fd.field_label).lower()
            for sub in forbidden_substrings:
                with self.subTest(field=fd.field_key, sub=sub):
                    self.assertNotIn(sub, joined)

    def test_no_horne_specific_anchors(self):
        # Asking anchors are universal patterns. They should never
        # name a specific person, family, or non-generic place.
        forbidden = ("horne", "janice", "kent", "christopher", "stanley")
        for fd in BIO_SCHEMA_SEED:
            for anchor in fd.asking_anchors:
                for sub in forbidden:
                    with self.subTest(field=fd.field_key, anchor=anchor):
                        self.assertNotIn(sub, anchor.lower())

    def test_military_fields_marked_military_only(self):
        # Narrators without military service should not be asked about
        # rank or decorations even if anchors accidentally match. The
        # life_stage_range='military_only' marker is the structural
        # block.
        for fd in BIO_SCHEMA_SEED:
            if fd.field_category == "military":
                with self.subTest(field=fd.field_key):
                    self.assertEqual(fd.life_stage_range, "military_only")


class FieldLookupTest(unittest.TestCase):
    def test_lookup_known_field(self):
        fd = get_field_by_key("birth_date")
        self.assertIsNotNone(fd)
        self.assertEqual(fd.field_category, "identity")

    def test_lookup_unknown_field_returns_none(self):
        self.assertIsNone(get_field_by_key("not_a_field_key_anywhere"))


class EnumConstraintsTest(unittest.TestCase):
    def test_categories_enum_is_eight_entries(self):
        # Per WO §2 bio_fields schema: 8 categories
        self.assertEqual(len(FIELD_CATEGORIES), 8)

    def test_field_types_includes_all_documented(self):
        for ft in ("date", "date_range", "place", "person",
                   "text", "enum", "integer"):
            self.assertIn(ft, FIELD_TYPES)

    def test_narrative_values_three_tier(self):
        self.assertEqual(set(NARRATIVE_VALUES), {"high", "medium", "low"})

    def test_life_stage_ranges_present(self):
        for r in ("childhood", "adult", "all", "military_only"):
            self.assertIn(r, LIFE_STAGE_RANGES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
