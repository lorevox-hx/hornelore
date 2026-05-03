"""WO-LORI-SAFETY-INTEGRATION-01 Phase 6 — Friendship Line resource card.

Phase 6 adds the Friendship Line (Institute on Aging, 1-800-971-0016,
24/7 warmline for adults 60+) to safety.py's RESOURCE_CARDS so it has
a structured-data sibling to the literal mention in the Phase 4
INDIRECT IDEATION + DISTRESSED response template.

Composition rule (locked):
  - ACUTE suicidal_ideation: 988-first ONLY (no Friendship Line —
    warmline shape is wrong for explicit current self-harm)
  - suicidal_ideation_indirect (Phase 2 LLM tier): Friendship Line + 988
  - distress_call: Friendship Line + 988
  - cognitive_distress: Friendship Line + Alzheimer's + Eldercare + 988
  - all abuse tiers: unchanged (population-specific resources + 988)

Tests are pure function checks — no DB, no IO, no LLM.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

# safety.py depends on pydantic (for SafetyResult); skip gracefully if
# the import fails in the sandbox.
try:
    from api.safety import RESOURCE_CARDS, get_resources_for_category
    _IMPORT_OK = True
    _IMPORT_ERR = None
except Exception as _exc:
    RESOURCE_CARDS = []
    get_resources_for_category = None  # type: ignore[assignment]
    _IMPORT_OK = False
    _IMPORT_ERR = repr(_exc)


def _skip_if_no_import():
    if not _IMPORT_OK:
        raise unittest.SkipTest(f"safety import failed: {_IMPORT_ERR}")


# ── Phase 6: structural — card landed correctly ───────────────────────────

class FriendshipLineCardPresenceTest(unittest.TestCase):
    """Verify the card landed at the documented index + has all
    expected fields."""

    def setUp(self):
        _skip_if_no_import()

    def test_friendship_line_in_resource_cards(self):
        names = [c["name"] for c in RESOURCE_CARDS]
        self.assertIn("Friendship Line", names)

    def test_friendship_line_at_index_5(self):
        # Indexing is load-bearing — get_resources_for_category uses
        # integer indexes. If a future PR inserts a new card at the
        # wrong position, the routing logic silently breaks. Pin the
        # position with this test.
        self.assertEqual(RESOURCE_CARDS[5]["name"], "Friendship Line")

    def test_friendship_line_phone_number_literal(self):
        # The literal must match what's in the Phase 4 prompt template
        # (prompt_composer.py) so operator UI surfacing the card and
        # narrator-facing response surface the SAME number.
        self.assertEqual(RESOURCE_CARDS[5]["contact"], "1-800-971-0016")

    def test_friendship_line_description_mentions_60(self):
        desc = RESOURCE_CARDS[5]["description"].lower()
        self.assertIn("60", desc)

    def test_friendship_line_has_population_metadata(self):
        # Operator-facing description; useful for Bug Panel resource lists
        self.assertEqual(RESOURCE_CARDS[5].get("population"), "60+")
        self.assertEqual(RESOURCE_CARDS[5].get("operator"), "Institute on Aging")


# ── Phase 6: routing — get_resources_for_category composition ─────────────

class FriendshipLineRoutingTest(unittest.TestCase):
    """The composition rule encodes Phase 6's "warmline complements 988
    for older narrators" framing."""

    def setUp(self):
        _skip_if_no_import()

    def test_acute_suicidal_ideation_remains_988_only(self):
        # ACUTE must NOT include Friendship Line — warmline shape is
        # wrong for explicit current self-harm
        result = get_resources_for_category("suicidal_ideation")
        names = [c["name"] for c in result]
        self.assertEqual(names, ["Crisis & Suicide Prevention"])
        self.assertNotIn("Friendship Line", names)

    def test_indirect_suicidal_ideation_includes_friendship_line(self):
        result = get_resources_for_category("suicidal_ideation_indirect")
        names = [c["name"] for c in result]
        self.assertEqual(names, ["Friendship Line", "Crisis & Suicide Prevention"])

    def test_distress_call_includes_friendship_line(self):
        result = get_resources_for_category("distress_call")
        names = [c["name"] for c in result]
        self.assertIn("Friendship Line", names)
        self.assertIn("Crisis & Suicide Prevention", names)

    def test_cognitive_distress_friendship_line_first(self):
        result = get_resources_for_category("cognitive_distress")
        names = [c["name"] for c in result]
        # Friendship Line must lead — population fit
        self.assertEqual(names[0], "Friendship Line")
        # Plus Alzheimer's + Eldercare + 988 in some order after
        for required in ("Alzheimer's Association Helpline",
                         "Eldercare & Caregiver Abuse",
                         "Crisis & Suicide Prevention"):
            self.assertIn(required, names)

    def test_abuse_tiers_unchanged_no_friendship_line(self):
        # Abuse tiers stay as they were — Friendship Line is NOT for
        # abuse routing
        for cat in ("sexual_abuse", "child_abuse", "domestic_abuse",
                    "physical_abuse", "caregiver_abuse"):
            result = get_resources_for_category(cat)
            names = [c["name"] for c in result]
            self.assertNotIn(
                "Friendship Line", names,
                f"Friendship Line incorrectly routed to abuse category {cat}",
            )

    def test_unknown_category_returns_full_card_list(self):
        # Defensive: an unknown category falls through to the full list
        result = get_resources_for_category("not_a_real_category")
        self.assertEqual(len(result), len(RESOURCE_CARDS))

    def test_none_category_returns_full_card_list(self):
        result = get_resources_for_category(None)
        self.assertEqual(len(result), len(RESOURCE_CARDS))


# ── Phase 6: cross-file consistency ───────────────────────────────────────

class CrossFileConsistencyTest(unittest.TestCase):
    """The Friendship Line phone number appears literally in Phase 4
    prompt template (prompt_composer.py). This test ensures the
    structured-data surface stays in sync."""

    def setUp(self):
        _skip_if_no_import()

    def test_phone_number_matches_prompt_template(self):
        prompt = (_REPO_ROOT / "server" / "code" / "api" / "prompt_composer.py").read_text(encoding="utf-8")
        # Both the literal in prompt_composer.py and the card's contact
        # field must match — if they ever drift, narrator-facing
        # response and operator-facing resource list would surface
        # different numbers
        card_number = RESOURCE_CARDS[5]["contact"]
        self.assertIn(
            card_number, prompt,
            f"Friendship Line phone number {card_number} (from "
            "RESOURCE_CARDS[5].contact) is missing from the Phase 4 "
            "prompt block in prompt_composer.py — they must stay "
            "in sync.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
