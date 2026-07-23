"""BUG-EX-VAGUE-TEMPORAL-FRAGMENT-01 — vague temporal hedges must not bind.

Live junk-rate audit (2026-07, /extract-fields battery on realistic narrator
turns) found the single dominant junk class: vague temporal/frequency HEDGES
binding to structured scalar fields —

    residence.period = "on and off for a while"
    residence.region = "here and there over the years"   (a PLACE field)
    residence.period = "mostly"  /  "over the years"

The extractor is otherwise strong on realistic turns (17/18 clean in the
audit); this was the one recurring miss. The discriminator is clean: a real
period/place value carries a NUMBER ("four years", "1985-2003", "2026") or a
content noun ("Bismarck", "the war"); a junk hedge is built ENTIRELY of
temporal-filler tokens.

Offline fastapi/pydantic stub pattern (same as the other extract-guard tests).
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

for _m in ("fastapi", "pydantic"):
    if _m not in sys.modules:
        sys.modules[_m] = types.ModuleType(_m)
sys.modules["fastapi"].APIRouter = lambda *a, **k: type(
    "R", (), {"get": lambda *a, **k: (lambda f: f),
              "post": lambda *a, **k: (lambda f: f)})()
sys.modules["fastapi"].HTTPException = Exception
sys.modules["fastapi"].Query = lambda *a, **k: None
sys.modules["pydantic"].BaseModel = object
sys.modules["pydantic"].Field = lambda *a, **k: None
sys.modules["pydantic"].field_validator = lambda *a, **k: (lambda f: f)
sys.modules["pydantic"].ConfigDict = dict

from api.routers.extract import (  # noqa: E402
    _drop_vague_temporal_fragment as _drop,
    _value_is_all_temporal_filler as _filler,
)


def _item(field, value):
    return {"fieldPath": field, "value": value}


class VagueTemporalDropTest(unittest.TestCase):
    def test_the_live_junk_drops(self):
        for field, val in (
            ("residence.period", "on and off for a while"),
            ("residence.region", "here and there over the years"),
            ("residence.period", "over the years"),
            ("residence.period", "mostly"),
            ("residence.period", "most of the time"),
            ("residence.period", "now and then"),
        ):
            self.assertTrue(_drop(_item(field, val)), "%s=%r" % (field, val))


class CleanValuesSurviveTest(unittest.TestCase):
    def test_numbers_and_dates_survive(self):
        for field, val in (
            ("residence.period", "1985-2003"),
            ("military.yearsOfService", "four years"),
            ("education.period", "twenty years"),
            ("laterYears.retirement", "2026"),
        ):
            self.assertFalse(_drop(_item(field, val)), "%s=%r" % (field, val))

    def test_content_nouns_survive(self):
        for field, val in (
            ("residence.place", "Bismarck"),
            ("residence.region", "North Dakota"),
            ("military.significantEvent", "during the war"),
        ):
            self.assertFalse(_drop(_item(field, val)), "%s=%r" % (field, val))


class NarrativeFieldsAreExemptTest(unittest.TestCase):
    """A story/note MAY be mostly filler and must never be dropped here."""

    def test_narrative_prose_kept_even_if_fillerish(self):
        for field, val in (
            ("grandparents.memorableStory", "over the years we drifted apart"),
            ("laterYears.dailyRoutine", "started traveling more"),
            ("community.reflection", "here and there, now and then"),
        ):
            self.assertFalse(_drop(_item(field, val)), "%s=%r" % (field, val))


class FillerClassifierTest(unittest.TestCase):
    def test_all_filler_true(self):
        self.assertTrue(_filler("on and off for a while"))
        self.assertTrue(_filler("over the years"))

    def test_digit_defeats_filler(self):
        self.assertFalse(_filler("1985-2003"))
        self.assertFalse(_filler("for 5 years"))

    def test_content_word_defeats_filler(self):
        self.assertFalse(_filler("four years"))   # "four" is content
        self.assertFalse(_filler("Bismarck"))

    def test_empty_is_not_filler(self):
        self.assertFalse(_filler(""))
        self.assertFalse(_filler("   "))


if __name__ == "__main__":
    unittest.main()
