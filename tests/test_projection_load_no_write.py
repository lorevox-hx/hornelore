"""WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 commit 1 -- the load path never writes.

Locks R1.1 (resetForNarrator issues no projection PUT), R1.2 (server hydration
is unconditional) and R1.5 (bio-builder's deep reset asks for a wipe explicitly
and in the right shape).

Why a source scan rather than a behavioural test: the defect lives in browser
JavaScript that has no node harness in this repo, and the thing being asserted
is structural -- "this code path contains no write" -- which is exactly what a
scan can prove and a behavioural test would only sample. Comments are stripped
with tests.source_scan_helpers.strip_js_comments first, so prose describing the
retired behaviour can neither satisfy nor trip a guard. That stripper is
string/template/regex-literal aware; the naive regex it replaced ate everything
after a "//" inside a string literal.

pytest is not installed in this repo. Run with:

    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_projection_load_no_write
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tests.source_scan_helpers import strip_js_comments  # noqa: E402

_SYNC_JS = _REPO_ROOT / "ui" / "js" / "projection-sync.js"
_BB_CORE_JS = _REPO_ROOT / "ui" / "js" / "bio-builder-core.js"
_APP_JS = _REPO_ROOT / "ui" / "js" / "app.js"


def _extract_function(src: str, name: str) -> str:
    """Return the body of `function <name>(...) { ... }` by brace matching."""
    m = re.search(r"\bfunction\s+" + re.escape(name) + r"\s*\([^)]*\)\s*\{", src)
    if not m:
        raise AssertionError(f"function {name} not found -- did it get renamed?")
    i = m.end() - 1
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i : j + 1]
    raise AssertionError(f"unbalanced braces while extracting {name}")


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sync = strip_js_comments(_SYNC_JS.read_text(encoding="utf-8"))
        cls.bb = strip_js_comments(_BB_CORE_JS.read_text(encoding="utf-8"))
        cls.app = strip_js_comments(_APP_JS.read_text(encoding="utf-8"))


class ResetForNarratorDoesNotWrite(_Base):
    """R1.1 -- merely loading a narrator must not upload browser state."""

    def setUp(self):
        self.body = _extract_function(self.sync, "resetForNarrator")

    def test_exactly_one_persist_call_remains(self):
        calls = re.findall(r"_persistProjection\s*\(", self.body)
        self.assertEqual(
            len(calls),
            1,
            "resetForNarrator must persist only when switching AWAY from a "
            "narrator. It previously called _persistProjection on two LOAD "
            "branches, which is how a narrator's server row was rewritten "
            "merely by being loaded (L2, 2026-08-16).",
        )

    def test_the_one_persist_is_the_switch_away_guard(self):
        self.assertRegex(
            self.body,
            r"if\s*\(\s*outgoingPid\s*\)\s*_persistProjection\s*\(\s*outgoingPid\s*\)",
            "the surviving persist must be the `if (outgoingPid)` departure "
            "case, not a load case",
        )

    def test_same_narrator_branch_has_no_write(self):
        branch = self._branch_after(r"newPid\s*&&\s*newPid\s*===\s*outgoingPid\s*&&\s*hasFields")
        self.assertNotIn("_persistProjection", branch)
        self.assertIn("_loadProjection", branch)

    def test_identity_carryover_branch_has_no_write(self):
        branch = self._branch_after(r"!outgoingPid\s*&&\s*newPid\s*&&\s*hasFields")
        self.assertNotIn("_persistProjection", branch)
        self.assertIn("_loadProjection", branch)

    def test_identity_carryover_still_adopts_fields_in_memory(self):
        # The substance of the old behaviour is preserved: fields collected
        # before the person existed are not thrown away, they are just not
        # uploaded before hydration.
        branch = self._branch_after(r"!outgoingPid\s*&&\s*newPid\s*&&\s*hasFields")
        self.assertRegex(branch, r"proj\.personId\s*=\s*newPid")
        self.assertIn("keepLocalFields", branch)

    def test_no_raw_put_smuggled_into_the_function(self):
        self.assertNotIn("IV_PROJ_PUT", self.body)
        self.assertNotRegex(self.body, r'method\s*:\s*["\']PUT["\']')

    # -- helper ------------------------------------------------------------
    def _branch_after(self, cond_regex: str) -> str:
        m = re.search(r"if\s*\(\s*" + cond_regex + r"\s*\)\s*\{", self.body)
        self.assertIsNotNone(m, f"branch guard not found: {cond_regex}")
        i = m.end() - 1
        depth = 0
        for j in range(i, len(self.body)):
            if self.body[j] == "{":
                depth += 1
            elif self.body[j] == "}":
                depth -= 1
                if depth == 0:
                    return self.body[i : j + 1]
        self.fail("unbalanced branch braces")


class HydrationIsUnconditional(_Base):
    """R1.2 -- the server wins on load, even when it has nothing."""

    def setUp(self):
        self.body = _extract_function(self.sync, "_loadProjectionFromBackend")

    def test_no_non_empty_gate_on_hydration(self):
        # The retired gate: `if (Object.keys(fields).length > 0) { ...assign }`
        # meant an empty server row left a stale localStorage draft in charge,
        # and that draft was then uploaded by the load path.
        self.assertNotRegex(
            self.body,
            r"Object\.keys\s*\(\s*fields\s*\)\.length\s*>\s*0",
            "hydration must not be gated on the server row being non-empty",
        )

    def test_assigns_server_fields_unconditionally(self):
        self.assertRegex(self.body, r"proj\.fields\s*=\s*serverFields")

    def test_late_response_for_a_switched_away_narrator_is_dropped(self):
        self.assertRegex(self.body, r"proj\.personId\s*!==\s*pid")

    def test_hydration_does_not_write_back_to_the_server(self):
        self.assertNotIn("IV_PROJ_PUT", self.body)
        self.assertNotIn("_persistProjection", self.body)


class LocalStorageIsACacheNotAnAuthority(_Base):
    def test_load_helper_does_not_persist(self):
        body = _extract_function(self.sync, "_loadProjection")
        self.assertNotIn("_persistProjection", body)
        self.assertIn("_loadProjectionFromBackend", body)

    def test_edit_path_still_persists(self):
        # R1.1 removes writes from the LOAD path only. A real edit must still
        # reach the server, or the fix would be data loss wearing a fix's hat.
        body = _extract_function(self.sync, "_debouncedPersist")
        self.assertIn("_persistProjection", body)


class DeepResetAsksForTheWipe(_Base):
    """R1.5 -- explicit, and in the shape the server actually parses."""

    def setUp(self):
        m = re.search(r"API\.IV_PROJ_PUT", self.bb)
        self.assertIsNotNone(m, "bio-builder deep reset no longer PUTs the projection")
        self.region = self.bb[max(0, m.start() - 1200) : m.start() + 1400]

    def test_sends_allow_empty(self):
        self.assertRegex(self.region, r"allow_empty\s*:\s*true")

    def test_asks_for_authorized_replacement(self):
        # allow_empty alone no longer replaces -- it guarded only the
        # empty case, so a non-empty stale envelope could still erase
        # server-authored keys.
        self.assertRegex(self.region, r"replace\s*:\s*true")

    def test_runs_under_optimistic_concurrency(self):
        self.assertRegex(self.region, r"base_version\s*:\s*cur\.version")

    def test_reads_the_current_version_before_replacing(self):
        self.assertIn("IV_PROJ_GET", self.bb)

    def test_sends_the_envelope_under_projection(self):
        self.assertRegex(self.region, r"projection\s*:\s*\{")

    def test_does_not_send_fields_at_the_top_level(self):
        # The original body put `fields` at the top level, which
        # ProjectionPutRequest ignores entirely -- the row was wiped only
        # because `projection` defaulted to an empty envelope. It worked by
        # accident, and the accident is now a refusal.
        self.assertNotRegex(
            self.region,
            r"person_id\s*:\s*pid\s*,\s*fields\s*:\s*\{\s*\}",
            "top-level `fields` is not part of the PUT contract",
        )


class LoadTriggersStillExist(_Base):
    """Guard against 'fixing' this by deleting the load path instead."""

    def test_app_still_resets_projection_on_person_load(self):
        self.assertIn("_ivResetProjectionForNarrator", self.app)

    def test_auto_init_on_load_survives(self):
        self.assertIn("_autoInitOnLoad", self.sync)


# ─────────────────────────────────────────────────────────────────────────────
# Supervisor requirements, 2026-08-16.
# ─────────────────────────────────────────────────────────────────────────────


class WritesAreFieldLevel(_Base):
    """Not a guarded whole-document replacement."""

    def setUp(self):
        self.body = _extract_function(self.sync, "_persistProjection")
        self.send = _extract_function(self.sync, "_sendMutations")

    def test_the_ordinary_write_path_is_patch_not_put(self):
        self.assertIn("IV_PROJ_PATCH", self.send)
        self.assertRegex(self.send, r'method\s*:\s*["\']PATCH["\']')
        self.assertNotIn("IV_PROJ_PUT", self.send)
        self.assertNotIn("IV_PROJ_PUT", self.body)

    def test_only_dirty_paths_are_sent(self):
        # The whole document is never the payload, so a server-authored
        # key this browser has never seen cannot be erased by a save.
        self.assertIn("_sync.dirty", self.body)
        self.assertRegex(self.body, r"mutations\[fp\]\s*=\s*proj\.fields\[fp\]")
        self.assertNotRegex(self.body, r"fields\s*:\s*proj\.fields")

    def test_a_base_version_accompanies_every_write(self):
        self.assertRegex(self.send, r"base_version\s*:\s*_sync\.baseVersion")

    def test_only_explicit_mutation_marks_dirty(self):
        # projectValue is the explicit-mutation entry point. Loads,
        # resets and switches must not reach _markDirty.
        pv = _extract_function(self.sync, "projectValue")
        self.assertIn("_markDirty", pv)
        reset = _extract_function(self.sync, "resetForNarrator")
        self.assertNotIn("_markDirty", reset)


class ConflictsAreSurfacedNeverRetried(_Base):
    """Supervisor review 2026-08-17.

    An earlier cut rebased onto the server record and retried once. That
    is safe only for a DISJOINT edit -- and the server now merges those
    itself, in one round trip, so a 409 can only mean a genuinely
    contested path. Retrying one would overwrite the newer value and
    delay the conflict rather than resolve it.
    """

    def setUp(self):
        self.send = _extract_function(self.sync, "_sendMutations")

    def test_409_is_detected(self):
        self.assertRegex(self.send, r"res\.status\s*===\s*409")

    def test_there_is_no_automatic_retry(self):
        self.assertNotIn("isRetry", self.send)
        # _sendMutations must not call itself.
        self.assertEqual(
            len(re.findall(r"_sendMutations\s*\(", self.send)), 0,
            "a conflict must not be retried automatically",
        )

    def test_the_contested_paths_are_recorded(self):
        self.assertIn("conflicting_paths", self.send)
        self.assertRegex(self.send, r"_sync\.conflicts\s*=\s*paths")

    def test_the_local_edit_is_kept_dirty_on_conflict(self):
        # The dirty deletions live only on the write_applied branch.
        conflict_branch = self.send[self.send.index("409"):self.send.index("write_applied")]
        self.assertNotIn("delete _sync.dirty", conflict_branch)

    def test_the_conflict_is_surfaced_rather_than_swallowed(self):
        self.assertIn("lorevox:projection-conflict", self.send)

    def test_a_failed_flush_keeps_the_edit_queued(self):
        self.assertRegex(self.send, r"catch[\s\S]*retry on next edit")


class ConcurrencyIsPerPath(_Base):
    """A global version proves only that SOMETHING moved, not what."""

    def test_base_fields_accompany_every_write(self):
        send = _extract_function(self.sync, "_sendMutations")
        self.assertRegex(send, r"base_fields\s*:\s*baseFields")

    def test_only_the_touched_paths_are_claimed(self):
        # Sending the whole hydrated map would make every concurrent edit
        # anywhere look like a conflict.
        send = _extract_function(self.sync, "_sendMutations")
        self.assertRegex(send, r"Object\.keys\(mutations\)\.forEach")
        self.assertNotRegex(send, r"base_fields\s*:\s*_sync\.base\b")

    def test_the_base_is_snapshotted_at_hydration(self):
        body = _extract_function(self.sync, "_loadProjectionFromBackend")
        self.assertRegex(body, r"_sync\.base\[k\]\s*=\s*serverFields\[k\]")

    def test_the_base_advances_only_on_an_applied_write(self):
        send = _extract_function(self.sync, "_sendMutations")
        applied = send[send.index("write_applied"):]
        self.assertRegex(applied, r"_sync\.base\[k\]\s*=\s*srvFields\[k\]")


class DirtyStateSurvivesASameNarratorReload(_Base):
    def test_reset_can_keep_the_dirty_set(self):
        body = _extract_function(self.sync, "_resetSyncState")
        self.assertIn("opts.keepDirty", body)

    def test_the_same_narrator_branch_asks_to_keep_it(self):
        reset = _extract_function(self.sync, "resetForNarrator")
        self.assertRegex(reset, r"keepDirty:\s*true")

    def test_a_narrator_switch_does_NOT_keep_it(self):
        # Those edits belong to someone else. Sliced from the departure
        # persist, which is the code the switch path runs -- not from a
        # comment, because the scan strips comments before asserting.
        reset = _extract_function(self.sync, "resetForNarrator")
        i = reset.index("if (outgoingPid) _persistProjection(outgoingPid)")
        self.assertNotIn("keepDirty", reset[i:])

    def test_carried_dirty_state_flushes_after_hydration(self):
        body = _extract_function(self.sync, "_loadProjectionFromBackend")
        self.assertRegex(body, r"Object\.keys\(_sync\.dirty\)\.length")


class CancellationOnNarratorSwitch(_Base):
    def test_hydration_uses_an_abort_controller(self):
        body = _extract_function(self.sync, "_loadProjectionFromBackend")
        self.assertIn("AbortController", body)
        self.assertIn("signal", body)

    def test_a_switch_aborts_the_in_flight_load(self):
        body = _extract_function(self.sync, "_resetSyncState")
        self.assertRegex(body, r"_sync\.abort\.abort\(\)")

    def test_a_switch_cancels_the_queued_save(self):
        body = _extract_function(self.sync, "_resetSyncState")
        self.assertIn("clearTimeout(_persistTimer)", body)

    def test_the_debounced_save_rechecks_the_generation_token(self):
        body = _extract_function(self.sync, "_debouncedPersist")
        self.assertRegex(body, r"gen\s*!==\s*_sync\.gen")

    def test_a_late_write_response_is_dropped(self):
        body = _extract_function(self.sync, "_sendMutations")
        self.assertRegex(body, r"gen\s*!==\s*_sync\.gen")

    def test_an_abort_is_not_reported_as_a_failure(self):
        body = _extract_function(self.sync, "_loadProjectionFromBackend")
        self.assertIn("AbortError", body)


class FailedLoadIsNotAnEmptyServer(_Base):
    """The distinction that stops a cache repopulating a live row."""

    def test_writes_are_blocked_until_hydration_succeeds(self):
        body = _extract_function(self.sync, "_persistProjection")
        self.assertRegex(body, r"if\s*\(\s*!_sync\.hydrated\s*\)")

    def test_hydrated_is_set_only_on_a_real_answer(self):
        body = _extract_function(self.sync, "_loadProjectionFromBackend")
        self.assertRegex(body, r"_sync\.hydrated\s*=\s*true")
        # ...and specifically NOT in the catch block.
        catch = body[body.rindex(".catch("):]
        self.assertNotIn("_sync.hydrated = true", catch)

    def test_a_confirmed_empty_server_is_allowed_to_stay_empty(self):
        # Hydration assigns unconditionally, so an empty server row
        # clears local fields rather than being papered over by the cache.
        body = _extract_function(self.sync, "_loadProjectionFromBackend")
        self.assertRegex(body, r"proj\.fields\s*=\s*serverFields")

    def test_the_local_mirror_is_display_only(self):
        # It is written by the cache helper and read on paint; it is never
        # itself the thing uploaded.
        mirror = _extract_function(self.sync, "_writeLocalMirror")
        self.assertNotIn("fetch(", mirror)


class OutgoingNarratorEditsAreRetainedNotDiscarded(_Base):
    """A -> switch to B -> return to A must lose nothing, and leak nothing.

    The failure this closes: an operator edits A and switches to B before
    the 2s debounce fires. Discarding A's dirty set there loses a
    legitimate edit precisely when someone is working quickly -- and the
    edit belongs to A, which is the reason to keep it under A rather than
    the reason to drop it.
    """

    def test_a_person_scoped_pending_store_exists(self):
        self.assertIn("var _pending = Object.create(null)", self.sync)

    def test_leaving_a_narrator_stashes_rather_than_discards(self):
        body = _extract_function(self.sync, "_resetSyncState")
        self.assertRegex(body, r"_stashPending\(outgoing\)")
        self.assertRegex(body, r"outgoing\s*&&\s*outgoing\s*!==\s*pid")

    def test_the_stash_is_keyed_by_person_id(self):
        body = _extract_function(self.sync, "_stashPending")
        self.assertRegex(body, r"_pending\[pid\]\s*=")
        # dirty, removals AND the hydration base all travel together --
        # without the base the conflict check cannot tell "unchanged since
        # I read it" from "someone moved it".
        for key in ("dirty:", "removed:", "base:"):
            self.assertIn(key, body)

    def test_returning_restores_only_that_narrators_work(self):
        body = _extract_function(self.sync, "_restorePending")
        self.assertRegex(body, r"_pending\[pid\]")
        self.assertRegex(body, r"delete _pending\[pid\]")

    def test_restore_happens_for_the_incoming_pid_only(self):
        body = _extract_function(self.sync, "_resetSyncState")
        self.assertRegex(body, r"_restorePending\(pid\)")
        self.assertNotRegex(body, r"_restorePending\(outgoing\)")

    def test_only_the_network_work_is_cancelled(self):
        body = _extract_function(self.sync, "_resetSyncState")
        self.assertRegex(body, r"_sync\.abort\.abort\(\)")
        self.assertRegex(body, r"clearTimeout\(_persistTimer\)")

    def test_a_returned_narrator_hydrates_from_the_server_first(self):
        # Server first, retained values re-applied over it -- not the
        # other way round, which would be the load-path write all over
        # again.
        body = _extract_function(self.sync, "_loadProjectionFromBackend")
        i_server = body.index("proj.fields = serverFields")
        i_retained = body.index("var retained = Object.keys(_sync.dirty)")
        self.assertLess(i_server, i_retained,
                        "hydration must precede re-applying retained edits")

    def test_retained_values_are_re_applied_from_that_narrators_own_cache(self):
        body = _extract_function(self.sync, "_loadProjectionFromBackend")
        self.assertRegex(body, r"LS_PROJ_PREFIX \+ pid")
        self.assertRegex(body, r"proj\.fields\[k\]\s*=\s*cache\.fields\[k\]")

    def test_retained_edits_flush_only_after_hydration(self):
        body = _extract_function(self.sync, "_loadProjectionFromBackend")
        self.assertRegex(body, r"Object\.keys\(_sync\.dirty\)\.length")

    def test_no_cross_narrator_write_is_possible(self):
        # Every response is dropped unless BOTH the generation token and
        # the pid still match, on the load and the write path alike.
        for fn in ("_loadProjectionFromBackend", "_sendMutations"):
            body = _extract_function(self.sync, fn)
            with self.subTest(fn=fn):
                self.assertRegex(body, r"gen\s*!==\s*_sync\.gen")
                self.assertRegex(body, r"pid\s*!==\s*_sync\.pid")

    def test_the_write_guard_still_refuses_a_foreign_pid(self):
        body = _extract_function(self.sync, "_persistProjection")
        self.assertRegex(body, r"if\s*\(pid\s*!==\s*_sync\.pid\)\s*return")


if __name__ == "__main__":
    unittest.main()
