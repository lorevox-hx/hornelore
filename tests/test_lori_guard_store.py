"""WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01 Continuation A, section F.

Covers the work order's named negative cases:

    V6  "All Switchable Off" implemented as sequential non-atomic changes
    V7  a protected authority can be changed through the API
    V8  restart loses Operator overrides / revision
    V9  reset copies the canonical default into an override

THE MIGRATION FILE IS EXECUTED, NOT MIRRORED. `ensure_schema()` exists
for convenience, but a test that only ever ran the Python mirror would
pass while the shipped `.sql` was broken — the fixture would be
supplying the property being proven. Every test below builds its
database by running `0053_lori_guard_authority_overrides.sql`.
"""

import os
import sqlite3
import unittest

from api.services import lori_guard_authority as auth
from api.services import lori_guard_registry as reg
from api.services import lori_guard_store as store


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MIGRATION = os.path.join(
    _REPO, "server", "code", "db", "migrations",
    "0053_lori_guard_authority_overrides.sql")


def _db():
    """A connection with the REAL migration applied."""
    con = sqlite3.connect(":memory:")
    with open(_MIGRATION, encoding="utf-8") as fh:
        con.executescript(fh.read())
    con.commit()
    return con


def _a_switchable_id():
    return reg.by_name("cc_word_limit").id          # 35


class MigrationTests(unittest.TestCase):

    def test_migration_file_exists_and_applies(self):
        self.assertTrue(os.path.exists(_MIGRATION))
        con = _db()
        names = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("lori_guard_authority_override", names)
        self.assertIn("lori_guard_control_state", names)

    def test_singleton_seeded_at_revision_zero(self):
        con = _db()
        self.assertEqual(store.read_revision(con), 0)

    def test_control_state_really_is_a_singleton(self):
        con = _db()
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute(
                "INSERT INTO lori_guard_control_state (id, revision) "
                "VALUES (2, 0)")

    def test_enabled_is_constrained_to_a_boolean(self):
        con = _db()
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute(
                "INSERT INTO lori_guard_authority_override "
                "(authority_id, enabled) VALUES (35, 7)")

    def test_no_narrator_column_exists(self):
        """These are installation controls, not narrator facts.

        A person_id here would put an operator's Tuesday experiment
        beside somebody's family relationships.
        """
        con = _db()
        cols = {r[1] for r in con.execute(
            "PRAGMA table_info(lori_guard_authority_override)")}
        for forbidden in ("person_id", "narrator_id", "conv_id", "session_id"):
            self.assertNotIn(forbidden, cols)

    def test_reapplying_the_migration_is_idempotent(self):
        con = _db()
        store.apply_changes(con, {_a_switchable_id(): False})
        with open(_MIGRATION, encoding="utf-8") as fh:
            con.executescript(fh.read())
        self.assertEqual(store.read_overrides(con), {_a_switchable_id(): False})


class WriteGuardTests(unittest.TestCase):

    def test_protected_authority_cannot_be_overridden(self):
        """V7."""
        con = _db()
        for item in reg.protected():
            with self.subTest(id=item.id):
                with self.assertRaises(store.NotSwitchableError):
                    store.apply_changes(con, {item.id: False})

    def test_unknown_authority_is_refused(self):
        con = _db()
        with self.assertRaises(store.NotSwitchableError):
            store.apply_changes(con, {9999: False})

    def test_a_refused_id_writes_nothing_at_all(self):
        """Validation happens before the transaction opens."""
        con = _db()
        good = _a_switchable_id()
        protected_id = reg.protected()[0].id
        with self.assertRaises(store.NotSwitchableError):
            store.apply_changes(con, {good: False, protected_id: False})
        self.assertEqual(store.read_overrides(con), {})
        self.assertEqual(store.read_revision(con), 0)


class ResetSemanticsTests(unittest.TestCase):

    def test_reset_deletes_the_row_rather_than_pinning_the_default(self):
        """V9.

        A copied default freezes today's value into this installation
        and silently detaches the authority from the registry.
        """
        con = _db()
        wid = _a_switchable_id()
        store.apply_changes(con, {wid: False})
        self.assertEqual(store.read_overrides(con), {wid: False})

        store.reset_authority(con, wid)
        self.assertEqual(store.read_overrides(con), {},
                         "Reset must leave NO row behind.")
        rows = con.execute(
            "SELECT COUNT(*) FROM lori_guard_authority_override").fetchone()[0]
        self.assertEqual(rows, 0)

    def test_after_reset_the_resolver_reports_canonical_not_override(self):
        con = _db()
        wid = _a_switchable_id()
        store.apply_changes(con, {wid: False})
        store.reset_authority(con, wid)
        overrides, revision = store.read_state(con)
        state = auth.resolve(overrides, revision=revision,
                             safety_parked_probe=lambda: False).state(wid)
        self.assertIsNone(state.operator_override)
        self.assertEqual(state.reason, auth.REASON_CANONICAL_DEFAULT)

    def test_restore_defaults_clears_every_override(self):
        con = _db()
        store.all_switchable_off(con)
        self.assertTrue(store.read_overrides(con))
        store.restore_canonical_defaults(con)
        self.assertEqual(store.read_overrides(con), {})


class AtomicityTests(unittest.TestCase):

    def test_all_switchable_off_is_one_revision(self):
        """V6.

        Thirty-seven sequential writes would create 37 revisions and let
        a turn begin on a mixture no operator ever chose.
        """
        con = _db()
        before = store.read_revision(con)
        after = store.all_switchable_off(con)
        self.assertEqual(after, before + 1)
        self.assertEqual(store.read_revision(con), before + 1)
        self.assertEqual(len(store.read_overrides(con)),
                         len(reg.switchable()))

    def test_all_switchable_off_covers_exactly_the_switchable_set(self):
        con = _db()
        store.all_switchable_off(con)
        self.assertEqual(set(store.read_overrides(con)),
                         {i.id for i in reg.switchable()})

    def test_restore_defaults_is_one_revision(self):
        con = _db()
        r1 = store.all_switchable_off(con)
        r2 = store.restore_canonical_defaults(con)
        self.assertEqual(r2, r1 + 1)

    def test_an_empty_change_still_advances_the_revision(self):
        """A generation that produced turns deserves an identity."""
        con = _db()
        self.assertEqual(store.apply_changes(con, {}), 1)


class StaleRevisionTests(unittest.TestCase):
    """Section P — protection against a stale panel in another tab."""

    def test_matching_revision_is_accepted(self):
        con = _db()
        store.apply_changes(con, {_a_switchable_id(): False},
                            expected_revision=0)
        self.assertEqual(store.read_revision(con), 1)

    def test_stale_revision_is_refused(self):
        con = _db()
        store.apply_changes(con, {_a_switchable_id(): False})   # -> 1
        with self.assertRaises(store.StaleRevisionError) as caught:
            store.apply_changes(con, {_a_switchable_id(): True},
                                expected_revision=0)
        self.assertEqual(caught.exception.expected, 0)
        self.assertEqual(caught.exception.actual, 1)

    def test_a_refused_write_changes_nothing(self):
        con = _db()
        wid = _a_switchable_id()
        store.apply_changes(con, {wid: False})
        with self.assertRaises(store.StaleRevisionError):
            store.apply_changes(con, {wid: True}, expected_revision=0)
        self.assertEqual(store.read_overrides(con), {wid: False})
        self.assertEqual(store.read_revision(con), 1)

    def test_omitting_the_expected_revision_skips_the_check(self):
        con = _db()
        store.apply_changes(con, {_a_switchable_id(): False})
        store.apply_changes(con, {_a_switchable_id(): True})
        self.assertEqual(store.read_revision(con), 2)


class PersistenceAcrossRestartTests(unittest.TestCase):
    """V8 — a restart must not silently return Lori to defaults."""

    def test_overrides_and_revision_survive_reconnection(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "guard.sqlite3")

            con = sqlite3.connect(path)
            with open(_MIGRATION, encoding="utf-8") as fh:
                con.executescript(fh.read())
            revision = store.all_switchable_off(con)
            overrides = store.read_overrides(con)
            con.close()

            # A new process would do exactly this.
            con2 = sqlite3.connect(path)
            self.assertEqual(store.read_revision(con2), revision)
            self.assertEqual(store.read_overrides(con2), overrides)

            restored_overrides, restored_revision = store.read_state(con2)
            snap = auth.resolve(restored_overrides,
                                revision=restored_revision,
                                safety_parked_probe=lambda: False)
            self.assertEqual(snap.revision, revision)
            for item in reg.switchable():
                with self.subTest(id=item.id):
                    self.assertFalse(
                        snap.is_selected(item.id),
                        "A restart returned Lori to defaults silently.")
            con2.close()


class ConcurrencyTests(unittest.TestCase):
    """The snapshot is only trustworthy if its acquisition is coherent.

    Commit 4 freezes this state before route detection and carries it
    through the whole turn. An immutable dataclass built from a torn
    read is still wrong — it just fails to admit it.
    """

    def _file_db(self, tmp):
        path = os.path.join(tmp, "guard.sqlite3")
        con = sqlite3.connect(path)
        with open(_MIGRATION, encoding="utf-8") as fh:
            con.executescript(fh.read())
        con.commit()
        con.close()
        return path

    def test_two_writers_on_the_same_base_revision_do_not_both_win(self):
        """Section P, under real concurrency rather than in sequence.

        Both callers believe revision 0. Exactly one may commit as
        revision 1; the loser must surface the stale/conflict condition
        after serialization, never silently overwrite the winner.
        """
        import tempfile
        import threading

        with tempfile.TemporaryDirectory() as tmp:
            path = self._file_db(tmp)
            wid_a = reg.by_name("cc_word_limit").id
            wid_b = reg.by_name("cc_chain_anchor_opener").id
            barrier = threading.Barrier(2)
            results = {}

            def attempt(label, authority_id):
                con = sqlite3.connect(path, timeout=10)
                try:
                    barrier.wait(timeout=10)
                    results[label] = store.apply_changes(
                        con, {authority_id: False}, expected_revision=0)
                except store.StaleRevisionError as exc:
                    results[label] = exc
                except Exception as exc:                 # pragma: no cover
                    results[label] = exc
                finally:
                    con.close()

            threads = [
                threading.Thread(target=attempt, args=("a", wid_a)),
                threading.Thread(target=attempt, args=("b", wid_b)),
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=20)

            winners = [v for v in results.values() if isinstance(v, int)]
            losers = [v for v in results.values()
                      if isinstance(v, store.StaleRevisionError)]
            self.assertEqual(
                len(winners), 1,
                f"exactly one write may succeed; got {results}")
            self.assertEqual(winners[0], 1)
            self.assertEqual(
                len(losers), 1,
                f"the loser must raise StaleRevisionError; got {results}")

            con = sqlite3.connect(path)
            overrides, revision = store.read_state(con)
            self.assertEqual(revision, 1)
            self.assertEqual(
                len(overrides), 1,
                "The loser must not have written alongside the winner.")
            con.close()

    def test_read_state_never_mixes_two_generations(self):
        """A torn read would pair one generation's rows with another's
        revision number.

        The writer alternates between two configurations whose override
        COUNT is a function of the revision, so any incoherent pair is
        detectable: odd revisions have every switchable authority
        overridden, even revisions have none.
        """
        import tempfile
        import threading

        switchable = len(reg.switchable())
        with tempfile.TemporaryDirectory() as tmp:
            path = self._file_db(tmp)
            stop = threading.Event()
            failures = []

            def writer():
                con = sqlite3.connect(path, timeout=10)
                try:
                    for _ in range(40):
                        store.all_switchable_off(con)
                        store.restore_canonical_defaults(con)
                finally:
                    stop.set()
                    con.close()

            def reader():
                con = sqlite3.connect(path, timeout=10)
                try:
                    while not stop.is_set():
                        overrides, revision = store.read_state(con)
                        if revision == 0:
                            expected = 0
                        else:
                            expected = switchable if revision % 2 else 0
                        if len(overrides) != expected:
                            failures.append(
                                f"revision {revision} carried "
                                f"{len(overrides)} overrides, expected "
                                f"{expected} — the read was torn")
                            return
                finally:
                    con.close()

            threads = [threading.Thread(target=writer),
                       threading.Thread(target=reader)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)
            self.assertEqual(failures, [], failures[:3])

    def test_read_state_is_a_single_statement(self):
        """Structural guard on the fix.

        Re-deriving read_state from read_overrides() + read_revision()
        would silently restore the tear, and no behavioural test can be
        relied on to catch a race every run.
        """
        import ast
        import inspect

        source = inspect.getsource(store.read_state)
        tree = ast.parse(source.lstrip())
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertNotIn("read_overrides", called)
        self.assertNotIn("read_revision", called)
        executes = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
        ]
        self.assertEqual(
            len(executes), 1,
            "read_state must issue exactly one statement.")

    def test_writes_serialize_before_reading_the_revision(self):
        """The write lock must precede the revision read, not follow it."""
        import ast
        import inspect

        source = inspect.getsource(store._WriteTransaction.__enter__)
        self.assertIn("BEGIN IMMEDIATE", source)

        body = inspect.getsource(store.apply_changes)
        tree = ast.parse(body.lstrip())
        withs = [n for n in ast.walk(tree) if isinstance(n, ast.With)]
        self.assertTrue(
            withs, "apply_changes must run inside a write transaction.")
        self.assertNotIn(
            "with con:", body,
            "`with con:` defers BEGIN to the first DML, which is the race "
            "this fix removes.")


class StoreFeedsResolverTests(unittest.TestCase):

    def test_read_state_drives_a_snapshot_end_to_end(self):
        con = _db()
        wid = _a_switchable_id()
        store.apply_changes(con, {wid: False})
        overrides, revision = store.read_state(con)
        snap = auth.resolve(overrides, revision=revision,
                            safety_parked_probe=lambda: False)
        self.assertEqual(snap.revision, revision)
        self.assertFalse(snap.is_selected(wid))
        self.assertEqual(snap.state(wid).reason, auth.REASON_OPERATOR_OVERRIDE)

    def test_orphaned_row_for_a_retired_id_cannot_break_a_turn(self):
        """Ids are permanent and reserved, so orphans are possible."""
        con = _db()
        con.execute("INSERT INTO lori_guard_authority_override "
                    "(authority_id, enabled) VALUES (9999, 0)")
        con.commit()
        self.assertEqual(store.read_overrides(con), {})
        auth.resolve(store.read_overrides(con),
                     safety_parked_probe=lambda: False)


if __name__ == "__main__":
    unittest.main()
