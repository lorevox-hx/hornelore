"""WO-LOREVOX-CLEAN-DATA-WORLD-01 (Phase 7) — the family lock must stay gone.

Modelled on tests/test_kawa_product_path_removed.py, and for the same reason:
the measure is ZERO REACHABLE PRODUCT PATH, not zero occurrences of a name.
Horne-named things REMAIN on purpose — the compatibility flag name
HORNELORE_OPERATOR_MODE, the `hornelore` log prefixes, the repository name
itself — and Phase 8 owns product naming. What may not come back is the
BEHAVIOUR:

  * seeding three hard-coded narrators from ui/templates/*-horne.json on boot,
    so a fresh Lorevox root could never stay empty;
  * a delete override that refused every deletion unless a flag was set;
  * a name allow-list deciding which narrators were real;
  * a canonicalizer rewriting a narrator's own name onto a family label, which
    is what manufactured BUG-NARRATOR-LABEL-COLLISION-01;
  * an identity-phase override that marked every narrator's onboarding
    complete because the seeded three already had identities;
  * HORNELORE_TRUST_PRELOAD_AS_TRUTH suppressing post-preload extraction;
  * a disabled new-narrator control.

These are source-level assertions, which the testing doctrine says are never
acceptance evidence BY THEMSELVES. They are not standing alone: the behaviour
is covered by tests/test_narrator_label_collision.py (disambiguation survives,
canonicalizer gone) and tests/test_purge_eligibility_authority.py (deletion
authority), and by the live disposable-root acceptance. These catch a
reintroduction cheaply, in the file where it would happen.
"""
from __future__ import annotations

import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_HTML = _REPO / "ui" / "hornelore1.0.html"
_APP = _REPO / "ui" / "js" / "app.js"
_PRELOAD = _REPO / "ui" / "js" / "narrator-preload.js"
_BBCORE = _REPO / "ui" / "js" / "bio-builder-core.js"


def _code_lines(path: Path):
    """Source lines with // comments and /* */ blocks stripped.

    Every removal in this lane left a comment EXPLAINING what was removed and
    why — those comments name the removed symbols, so a naive substring search
    finds its own tombstone and passes forever. The explanations are worth more
    than the convenience of a simpler search.
    """
    out, in_block = [], False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw
        if in_block:
            if "*/" in line:
                line = line.split("*/", 1)[1]
                in_block = False
            else:
                continue
        # A block comment is only recognized when the line STARTS with `/*`.
        #
        # This restriction is the fix for a real failure: matching `/*`
        # anywhere on the line desyncs on a 10,000-line file of interleaved
        # CSS, HTML and JS — a `/*` inside a string or a regex opens a block
        # that never closes, and everything after it vanishes. That silently
        # swallowed the entire settings-popover region, which made a passing
        # assertion fail and, worse, could have made a failing one pass by
        # hiding the code it was meant to inspect. Every block comment this
        # file needs to strip is written at the start of a line.
        if line.lstrip().startswith("/*"):
            head = line[:len(line) - len(line.lstrip())]
            rest = line.lstrip()[2:]
            if "*/" in rest:
                line = head + rest.split("*/", 1)[1]
            else:
                line, in_block = head, True
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("<!--"):
            continue
        if "//" in line and "://" not in line:
            line = line.split("//", 1)[0]
        if line.strip():
            out.append(line)
    return out


class FamilyLockRemovedTests(unittest.TestCase):

    def _refute(self, path: Path, token: str, why: str):
        hits = [ln.strip() for ln in _code_lines(path) if token in ln]
        self.assertEqual(hits, [], f"{token} is back in {path.name}: {why}\n"
                                   f"  {hits[:3]}")

    def test_no_boot_time_family_seeding(self):
        for token in ("HORNELORE_NARRATORS", "_horneloreEnsureNarrators"):
            self._refute(_HTML, token,
                         "a fresh Lorevox root must be able to stay empty")

    def test_no_horne_template_fetch(self):
        for name in ("christopher-todd-horne.json", "kent-james-horne.json",
                     "janice-josephine-horne.json"):
            self._refute(_HTML, name,
                         "the runtime must not fetch family templates")

    def test_no_narrator_name_allow_list(self):
        for token in ("_horneloreAllowedNarratorNames", "_horneloreIsCoreNarrator"):
            self._refute(_HTML, token,
                         "no list decides which narrators are real")

    def test_no_family_name_canonicalization(self):
        # The strings the canonicalizer mapped onto. Their presence in code
        # (not comments) means a narrator's own name is being rewritten again.
        for token in ('"Christopher Todd Horne"', '"Kent James Horne"',
                      '"Janice Josephine (Zarr) Horne"'):
            hits = [ln.strip() for ln in _code_lines(_HTML) if token in ln]
            self.assertEqual(
                hits, [],
                f"{token} appears in shipped UI code — the family "
                f"canonicalizer manufactured a label collision once already")

    def test_no_delete_override_and_no_identity_phase_override(self):
        for token in ("_origStageDelete", "_origSwitchPerson"):
            self._refute(_HTML, token,
                         "deletion and onboarding follow ordinary product "
                         "policy for every narrator")

    def test_no_preload_as_truth_exception(self):
        for path in (_HTML, _PRELOAD):
            self._refute(path, "HORNELORE_TRUST_PRELOAD_AS_TRUTH",
                         "a preloaded narrator is not thereby confirmed truth")

    def test_no_seeder_skip_list(self):
        for path in (_HTML, _APP):
            for token in ("hornelore_deleted_labels", "_horneloreGetDeletedLabels",
                          "_horneloreMarkDeletedNarrator"):
                self._refute(path, token,
                             "the skip list existed only to stop the seeder "
                             "resurrecting a deleted narrator")

    def test_no_purge_whitelist(self):
        self._refute(_BBCORE, "_CANONICAL_NARRATOR_NAMES",
                     "purge eligibility comes from people.testing_only")

    def test_new_narrator_control_is_enabled_and_wired(self):
        src = _HTML.read_text(encoding="utf-8")
        line = next((ln for ln in src.splitlines()
                     if 'id="lv80NewBtn"' in ln), None)
        self.assertIsNotNone(line, "#lv80NewBtn is missing entirely")
        self.assertNotIn("display:none", line,
                         "the new-narrator control is hidden again")
        self.assertNotIn("disabled", line,
                         "the new-narrator control is disabled again")
        # It was hidden AND handler-less: un-hiding alone ships a dead button.
        self.assertIn("lv80OpenNarratorCreate", line,
                      "#lv80NewBtn has no handler — visible and inert")

    def test_the_universal_disambiguator_survived(self):
        # The one thing that must NOT have been removed with the family lock.
        src = _HTML.read_text(encoding="utf-8")
        self.assertIn("function _horneloreDisambiguateLabels", src,
                      "duplicate-label disambiguation was removed — two "
                      "narrators can again render identically in the picker")


class OperatorModePreservedTests(unittest.TestCase):
    """Removing family protection must not remove operator capability."""

    def test_the_resume_gate_consumers_are_intact(self):
        html = _HTML.read_text(encoding="utf-8")
        app = _APP.read_text(encoding="utf-8")
        self.assertIn("wo10b_operator_resume_gate", html,
                      "the WO-10B resume gate toggle is gone")
        self.assertIn("window.HORNELORE_OPERATOR_MODE", app,
                      "the WO-10B resume gate read is gone")

    def test_the_flag_has_exactly_one_initialization_authority(self):
        """One DEFAULT. Runtime state changes are a different thing entirely.

        An earlier version of this test counted every `window.X = ...` line as
        a declaration and failed on `window.HORNELORE_OPERATOR_MODE = true` in
        the WO-10B resume-gate restore. That is not a declaration — it is the
        universal operator behaviour Phase 7 exists to PRESERVE, and deleting
        it to make a test green would have removed the feature to satisfy the
        regression guarding it.

        The real contract:
          1. exactly one initialization/default, and it is in app.js;
          2. the removed family-lock block does not re-declare or reset it;
          3. no Horne delete bypass writes it;
          4. WO-10B may set it true or false at runtime, freely.
        """
        # 1 — the default is the `|| false` idiom, and only that.
        defaults = [
            f"{path.name}:{i}: {line.strip()}"
            for path in (_HTML, _APP)
            for i, line in enumerate(_code_lines(path), 1)
            if "HORNELORE_OPERATOR_MODE" in line
            and "HORNELORE_OPERATOR_MODE ||" in line
        ]
        self.assertEqual(
            len(defaults), 1,
            "the operator-mode flag must have ONE initialization authority; a "
            "second one re-assigned it at script-eval time and clobbered the "
            "first: " + str(defaults))
        self.assertTrue(
            defaults[0].startswith("app.js"),
            "the default belongs in app.js, not inside the removed "
            "family-lock block: " + defaults[0])

        # 2 — the family-lock block's bare reset (`= false;`) is gone. WO-10B
        #     turns the gate off through the toggle's `= this.checked`, never
        #     through a literal, so a bare false assignment is a remnant.
        resets = [ln.strip() for ln in _code_lines(_HTML)
                  if "HORNELORE_OPERATOR_MODE = false" in ln]
        self.assertEqual(
            resets, [],
            "a bare `HORNELORE_OPERATOR_MODE = false` is back — that was the "
            "family-lock block's script-eval reset and the delete override's "
            "'reset after use', both of which silently turned off a resume "
            "gate the operator had deliberately enabled")

        # 3 — the operator delete path no longer arms the flag to get past a
        #     family guard. Deletion is ordinary product policy now.
        #
        # Searched against CODE, not raw source. The removal left a comment
        # explaining what used to be here, and that comment necessarily quotes
        # `HORNELORE_OPERATOR_MODE = true` — so a raw substring search finds
        # its own tombstone and reports the defect it is describing. Same trap
        # _code_lines() was written for at the top of this file.
        # Belt and braces: comment-stripped source AND a line-anchored
        # assignment pattern, so the assertion does not depend on _code_lines()
        # parsing this particular file correctly.
        code = "\n".join(_code_lines(_HTML))
        start = code.index("function lv80OperatorDeleteCurrent")
        body = code[start:code.index("\n}", start)]
        self.assertNotRegex(
            body,
            r"(?m)^\s*(?:window\.)?HORNELORE_OPERATOR_MODE\s*=\s*true\s*;",
            "lv80OperatorDeleteCurrent assigns the operator-mode flag again — "
            "that was the Horne delete bypass, and because the same flag is "
            "the WO-10B resume gate it also flipped an unrelated setting")

    def test_wo10b_may_still_change_the_flag_at_runtime(self):
        # The positive half of the rule above: these writes MUST exist. A
        # future tidy-up that removes them has removed the operator feature.
        #
        # Line-anchored on RAW source, rejecting only lines that ARE comments.
        #
        # Two wrong approaches were tried first and both are worth recording.
        # A plain substring search on raw source PASSED on the removal comment,
        # so it would have kept passing after somebody deleted the resume gate
        # entirely — a test that cannot fail. Switching to _code_lines() then
        # FAILED on working code: its /* */ state machine desyncs on a
        # 10,000-line file of interleaved CSS, HTML and JS and silently
        # swallowed the whole settings-popover region, toggle included.
        #
        # A comment on these lines starts with // (or * inside a block); the
        # real toggle sits inside an HTML onchange attribute, indented, and the
        # real restore is an ordinary indented statement. Excluding
        # comment-leading lines is enough, and it cannot desync.
        src = _HTML.read_text(encoding="utf-8")
        for pattern, why in (
            (r"(?m)^(?!\s*(?://|\*))"
             r".*window\.HORNELORE_OPERATOR_MODE\s*=\s*this\.checked",
             "the WO-10B resume-gate toggle no longer sets the flag"),
            (r"(?m)^(?!\s*(?://|\*))"
             r".*window\.HORNELORE_OPERATOR_MODE\s*=\s*true\s*;",
             "the WO-10B resume-gate restore no longer sets the flag"),
        ):
            with self.subTest(pattern=pattern):
                self.assertRegex(src, pattern, why)


if __name__ == "__main__":
    unittest.main()
