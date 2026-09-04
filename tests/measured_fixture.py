"""Fixtures that MEASURE their own properties against the shipped code.

WHY THIS EXISTS
===============
On 2026-09-04 a fixture in ``tests/test_phase2_verify_ledger.py`` was
written to carry three scene anchors. It carried two. The author reasoned
"it names a place, a person and a year, so anchors=3" and wrote that down
as a comment. A bare year is not a TIME anchor -- ``story_trigger``
matches RELATIVE time phrasing ("when I was little"), not absolute dates
(``story_trigger.py:706`` calls ``_matches_relative_time``). The test
that depended on the fixture taking the deterministic path was therefore
testing the chain-dependent path, and passing.

That failure has a shape, and the shape is general: **a property the
author ASSERTS about a fixture is not a property the fixture HAS.** A
comment cannot fail. Neither can a docstring, a variable name, or a
memory of how the classifier behaved last month.

WHAT THIS DOES
==============
``measured()`` takes the text, the properties the author believes it has,
and a callable that computes those properties USING THE SHIPPED CODE. It
runs the callable at import time and raises if the belief and the
measurement disagree, naming both.

Three consequences, in descending order of value:

  1. A wrong assumption fails AT THE FIXTURE with the measured values in
     the message, instead of surfacing as a confusing failure in some
     downstream assertion -- or, worse, as a passing test of the wrong
     path.

  2. When the shipped classifier's behaviour CHANGES, every fixture that
     depends on the old behaviour fails loudly and immediately. Without
     this, those tests keep passing while silently asserting against a
     classifier that no longer does what they describe.

  3. The declaration is documentation that CANNOT go stale, because the
     harness re-derives it on every run.

It is deliberately not a mock, a snapshot or a golden file. It calls the
real shipped function; a fixture whose properties come from a recorded
value would reintroduce exactly the drift this prevents.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


class FixtureMeasurementError(AssertionError):
    """A fixture's declared properties disagree with the shipped code."""


def measured(text: str, *, measure: Callable[[str], Dict[str, Any]],
             name: str = "", **declared: Any) -> str:
    """Return ``text`` after proving it has the ``declared`` properties.

    ``measure`` is called with the text and must return a mapping. Every
    key in ``declared`` must be present in that mapping and compare equal.
    Keys the mapping carries but the caller did not declare are ignored --
    a fixture declares what it depends on, not everything the shipped
    function happens to compute.

    Raises ``FixtureMeasurementError`` on any mismatch, listing the
    declared value AND the measured one for each key that differs, plus
    the full measurement so the author can see what the text actually is.
    """
    if not declared:
        raise FixtureMeasurementError(
            f"{name or 'fixture'}: declares no properties, so it measures "
            "nothing. Either declare what the test depends on or use a "
            "plain string."
        )
    observed = measure(text)
    if not isinstance(observed, dict):
        raise FixtureMeasurementError(
            f"{name or 'fixture'}: measure() returned "
            f"{type(observed).__name__}, expected a mapping"
        )

    missing = [k for k in declared if k not in observed]
    if missing:
        raise FixtureMeasurementError(
            f"{name or 'fixture'}: declared {missing} but the measurement "
            f"does not compute {'it' if len(missing) == 1 else 'them'}. "
            f"Measured keys: {sorted(observed)}"
        )

    wrong = {k: (v, observed[k]) for k, v in declared.items()
             if observed[k] != v}
    if wrong:
        lines = [f"{name or 'fixture'}: DECLARED properties do not match "
                 "the shipped code."]
        for k, (want, got) in sorted(wrong.items()):
            lines.append(f"  {k}: declared {want!r}, measured {got!r}")
        lines.append(f"  full measurement: {observed!r}")
        lines.append(f"  text: {text[:120]!r}")
        lines.append("  Fix the DECLARATION to match reality, or change the "
                     "text until it has the property the test needs. Do not "
                     "relax the check.")
        raise FixtureMeasurementError("\n".join(lines))
    return text


def story_trigger_measure(text: str) -> Dict[str, Any]:
    """Measure a transcript with the SHIPPED story trigger, no chain context.

    ``chain_ctx=None`` on purpose: the chain-detection path depends on
    runtime context that is persisted nowhere, so a fixture can only
    honestly declare properties of the DETERMINISTIC paths.
    """
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    code = str(root / "server" / "code")
    if code not in sys.path:
        sys.path.insert(0, code)
    from api.services import story_trigger as st

    diag = st.trigger_diagnostic(
        audio_duration_sec=None, transcript=text, chain_ctx=None)
    return {
        "trigger": diag.get("trigger"),
        "word_count": diag.get("word_count"),
        "anchors": diag.get("anchor_count"),
        "place_anchor": diag.get("place_anchor"),
        "time_anchor": diag.get("time_anchor"),
        "person_anchor": diag.get("person_anchor"),
    }
