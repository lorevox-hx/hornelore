"""WO-LOREVOX-PORTABLE-NARRATOR-01 §36.4 — exclusive residue closure.

THE DEFECT. `trip_turn_links` is owned through `trips.person_id`; `sessions`
was owned only by `sessions.person_id`. On the laptop origin Christopher has
2 trips and 0 directly-owned sessions, so 20 narrator-owned travel links
named 9 sessions whose `person_id` is NULL (legacy residue, pre-0044). The
exporter selected the links, omitted the sessions and turns they require, and
the §30 unresolved-reference guard refused 60 references. The guard was right.

THE RULE. A residue row reached EXCLUSIVELY from one narrator's owned rows,
through a declared inbound reference, is that narrator's by derivation — for
BOTH verbs. Never by writing `sessions.person_id`.

TESTING DOCTRINE. Every assertion below runs the SHIPPED predicate against a
real SQLite database. Asserting on the generated SQL string would be a
fixture supplying the property being proven (CLAUDE.md), and would pass
against SQL that SQLite rejects — which is exactly how the DELETE-target
qualification bug would have escaped.
"""
import contextlib
import sqlite3
import unittest

from api.services import narrator_data_inventory as inv


@contextlib.contextmanager
def declaration(lanes):
    """Swap the declaration AND its import-time index together.

    `lane()` reads `_BY_TABLE`, which is built from `DB_LANES` ONCE at import.
    Patching only `DB_LANES` leaves every predicate reading the ORIGINAL
    declaration, which made two tests in this file silently vacuous: they
    passed a patched tuple nothing consumed, exercised the shipped lanes
    instead, and reported green. Swap both, or prove nothing.
    """
    old_lanes, old_index = inv.DB_LANES, inv._BY_TABLE
    lanes = tuple(lanes)
    try:
        inv.DB_LANES = lanes
        inv._BY_TABLE = {l.table: l for l in lanes}
        yield
    finally:
        inv.DB_LANES, inv._BY_TABLE = old_lanes, old_index


class DeclarationHarness(unittest.TestCase):
    """Non-vacuity guard on the harness itself.

    Without this, a future edit that patches only one of the two module
    globals reproduces the original defect and every test that depends on
    patching goes quietly green against the shipped declaration.
    """

    def test_patching_the_declaration_actually_changes_the_predicate(self):
        shipped = inv.owner_predicate("sessions")
        self.assertIn("trip_turn_links", shipped)
        plain = [inv.DbLane("sessions", inv.Direct("person_id"),
                            inv.CLASS_AUTHORITATIVE, "yes", True)
                 if l.table == "sessions" else l
                 for l in inv.DB_LANES]
        with declaration(plain):
            self.assertNotIn("trip_turn_links", inv.owner_predicate("sessions"))
        self.assertEqual(shipped, inv.owner_predicate("sessions"))

ALICE = "aaaaaaaa-0000-0000-0000-000000000001"
BOB = "bbbbbbbb-0000-0000-0000-000000000002"

SCHEMA = """
CREATE TABLE people (id TEXT PRIMARY KEY, display_name TEXT);
CREATE TABLE trips (id TEXT PRIMARY KEY, person_id TEXT);
CREATE TABLE trip_turn_links (
    id TEXT PRIMARY KEY, trip_id TEXT, conv_id TEXT DEFAULT '',
    user_turn_row_id INTEGER, assistant_turn_row_id INTEGER);
CREATE TABLE sessions (conv_id TEXT PRIMARY KEY, person_id TEXT,
                       person_id_source TEXT);
CREATE TABLE turns (id INTEGER PRIMARY KEY, conv_id TEXT, role TEXT);
"""


def _db():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    con.execute("INSERT INTO people VALUES (?,?)", (ALICE, "Alice"))
    con.execute("INSERT INTO people VALUES (?,?)", (BOB, "Bob"))
    return con


def _trip(con, tid, pid):
    con.execute("INSERT INTO trips VALUES (?,?)", (tid, pid))


def _session(con, conv, pid=None):
    con.execute("INSERT INTO sessions VALUES (?,?,?)", (conv, pid, None))


def _turns(con, conv, *ids):
    for i in ids:
        con.execute("INSERT INTO turns VALUES (?,?,?)", (i, conv, "user"))


def _link(con, lid, tid, conv):
    con.execute(
        "INSERT INTO trip_turn_links (id, trip_id, conv_id) VALUES (?,?,?)",
        (lid, tid, conv))


def _sel(con, table, pid):
    return {tuple(r) for r in con.execute(inv.select_sql(table), {"pid": pid})}


def _convs(con, pid):
    return {r["conv_id"] for r in con.execute(inv.select_sql("sessions"),
                                              {"pid": pid})}


def _turn_ids(con, pid):
    return {r["id"] for r in con.execute(inv.select_sql("turns"), {"pid": pid})}


class ExclusiveResidueClosure(unittest.TestCase):
    """1. One narrator exclusively reaches a residue session."""

    def setUp(self):
        self.con = _db()
        _trip(self.con, "trip-a", ALICE)
        _session(self.con, "residue-1", None)       # residue: person_id NULL
        _turns(self.con, "residue-1", 100, 101)
        _link(self.con, "link-1", "trip-a", "residue-1")

    def test_residue_session_enters_select_closure(self):
        self.assertIn("residue-1", _convs(self.con, ALICE))

    def test_turns_follow_without_a_special_case(self):
        """5. `turns` is Parent('conv_id','sessions','conv_id'). It must
        compose from the corrected session predicate with no change of its
        own — proven by running the turns selector, not by reading the lane."""
        self.assertEqual(inv.lane("turns").owner,
                         inv.Parent("conv_id", "sessions", "conv_id"))
        self.assertEqual({100, 101}, _turn_ids(self.con, ALICE))

    def test_residue_session_enters_delete_closure(self):
        """6. select/delete parity on the same fixture."""
        before = _convs(self.con, ALICE)
        self.con.execute(inv.delete_sql("sessions"), {"pid": ALICE})
        after = {r["conv_id"] for r in self.con.execute(
            "SELECT conv_id FROM sessions")}
        self.assertIn("residue-1", before)
        self.assertNotIn("residue-1", after,
                         "a row that travels with the narrator must also die "
                         "with the narrator (no export-only ownership)")

    def test_ownership_is_derived_never_written(self):
        """The predicate must not depend on, or cause, a person_id write."""
        _convs(self.con, ALICE)
        row = self.con.execute(
            "SELECT person_id, person_id_source FROM sessions "
            "WHERE conv_id='residue-1'").fetchone()
        self.assertIsNone(row["person_id"])
        self.assertIsNone(row["person_id_source"])


class AmbiguousResidueRefused(unittest.TestCase):
    """2. Two narrators reach the same residue session -> neither owns it."""

    def setUp(self):
        self.con = _db()
        _trip(self.con, "trip-a", ALICE)
        _trip(self.con, "trip-b", BOB)
        _session(self.con, "shared", None)
        _turns(self.con, "shared", 200, 201)
        _link(self.con, "link-a", "trip-a", "shared")
        _link(self.con, "link-b", "trip-b", "shared")

    def test_neither_narrator_claims_it(self):
        self.assertNotIn("shared", _convs(self.con, ALICE))
        self.assertNotIn("shared", _convs(self.con, BOB))

    def test_its_turns_are_claimed_by_neither(self):
        self.assertEqual(set(), _turn_ids(self.con, ALICE))
        self.assertEqual(set(), _turn_ids(self.con, BOB))

    def test_neither_delete_closure_removes_it(self):
        for pid in (ALICE, BOB):
            self.con.execute(inv.delete_sql("sessions"), {"pid": pid})
        remaining = {r["conv_id"] for r in self.con.execute(
            "SELECT conv_id FROM sessions")}
        self.assertIn("shared", remaining,
                      "an ambiguous residue session must never be deleted by "
                      "either narrator's erasure")

    def test_exclusivity_is_evaluated_across_every_declared_inbound_path(self):
        """A second `via` lane pointing at the same row must disqualify it,
        even though the FIRST lane reaches it exclusively.

        Constructed by declaring a real second inbound lane, not by asserting
        the intent: the predicate is generated from `via` and run against SQL.
        """
        con = _db()
        con.executescript(
            "CREATE TABLE trip_story_notes (id TEXT PRIMARY KEY, "
            "trip_id TEXT, conv_id TEXT DEFAULT '');")
        _trip(con, "trip-a", ALICE)
        _trip(con, "trip-b", BOB)
        _session(con, "two-paths", None)
        _link(con, "link-a", "trip-a", "two-paths")     # Alice, via links
        con.execute("INSERT INTO trip_story_notes VALUES (?,?,?)",
                    ("note-b", "trip-b", "two-paths"))  # Bob, via notes

        lanes = inv.DB_LANES + (
            inv.DbLane("trip_story_notes",
                       inv.Parent("trip_id", "trips"),
                       inv.CLASS_DERIVED, "yes", True),)
        patched = []
        for l in lanes:
            if l.table == "sessions":
                o = l.owner
                l = inv.DbLane(
                    l.table,
                    inv.DirectOrExclusiveInbound(
                        o.column, o.key,
                        o.via + (inv.InboundRef("trip_story_notes", "conv_id"),)),
                    l.klass, l.portable, l.erasable,
                    l.path_columns, l.external_person_columns, l.note)
            patched.append(l)

        with declaration(patched):
            alice = {r["conv_id"] for r in con.execute(
                inv.select_sql("sessions"), {"pid": ALICE})}

        self.assertNotIn(
            "two-paths", alice,
            "Alice reaches it exclusively through trip_turn_links, but Bob "
            "reaches it through a second declared inbound lane; exclusivity "
            "must be evaluated across ALL of `via`")


class UnrelatedResidueUntouched(unittest.TestCase):
    """3. Residue nobody reaches stays residue."""

    def setUp(self):
        self.con = _db()
        _trip(self.con, "trip-a", ALICE)
        _session(self.con, "orphan", None)
        _turns(self.con, "orphan", 300)
        _session(self.con, "reached", None)
        _link(self.con, "link-1", "trip-a", "reached")

    def test_unreached_residue_is_not_selected(self):
        convs = _convs(self.con, ALICE)
        self.assertIn("reached", convs)
        self.assertNotIn("orphan", convs)

    def test_unreached_residue_survives_erasure(self):
        self.con.execute(inv.delete_sql("sessions"), {"pid": ALICE})
        remaining = {r["conv_id"] for r in self.con.execute(
            "SELECT conv_id FROM sessions")}
        self.assertEqual({"orphan"}, remaining)

    def test_unreached_residue_turns_survive(self):
        self.assertNotIn(300, _turn_ids(self.con, ALICE))


class DirectOwnershipUnchanged(unittest.TestCase):
    """4. Ordinary directly-owned sessions behave exactly as before."""

    def setUp(self):
        self.con = _db()
        _session(self.con, "alice-own", ALICE)
        _turns(self.con, "alice-own", 400, 401)
        _session(self.con, "bob-own", BOB)
        _turns(self.con, "bob-own", 500)

    def test_direct_selection_unchanged(self):
        self.assertEqual({"alice-own"}, _convs(self.con, ALICE))
        self.assertEqual({"bob-own"}, _convs(self.con, BOB))

    def test_direct_turns_unchanged(self):
        self.assertEqual({400, 401}, _turn_ids(self.con, ALICE))

    def test_direct_delete_unchanged(self):
        self.con.execute(inv.delete_sql("sessions"), {"pid": ALICE})
        remaining = {r["conv_id"] for r in self.con.execute(
            "SELECT conv_id FROM sessions")}
        self.assertEqual({"bob-own"}, remaining)

    def test_another_narrators_session_is_never_claimed_as_residue(self):
        """A session owned by Bob must not become Alice's even if Alice's
        travel link names it — it is not residue, so the residue branch
        must not fire."""
        _trip(self.con, "trip-a", ALICE)
        _link(self.con, "link-1", "trip-a", "bob-own")
        self.assertNotIn("bob-own", _convs(self.con, ALICE))


class SelectDeleteParity(unittest.TestCase):
    """6. Whatever select admits, delete removes — on one fixture, both verbs."""

    def test_parity_over_a_mixed_fixture(self):
        con = _db()
        _trip(con, "trip-a", ALICE)
        _trip(con, "trip-b", BOB)
        _session(con, "alice-direct", ALICE)
        _session(con, "alice-residue", None)
        _session(con, "shared-residue", None)
        _session(con, "orphan-residue", None)
        _session(con, "bob-direct", BOB)
        _link(con, "l1", "trip-a", "alice-residue")
        _link(con, "l2", "trip-a", "shared-residue")
        _link(con, "l3", "trip-b", "shared-residue")

        selected = _convs(con, ALICE)
        self.assertEqual({"alice-direct", "alice-residue"}, selected)

        con.execute(inv.delete_sql("sessions"), {"pid": ALICE})
        remaining = {r["conv_id"] for r in con.execute(
            "SELECT conv_id FROM sessions")}
        self.assertEqual({"shared-residue", "orphan-residue", "bob-direct"},
                         remaining)
        self.assertEqual(selected, {"alice-direct", "alice-residue"} & selected)


class DerivedOwnershipMayNotChain(unittest.TestCase):
    """A lane whose own ownership is derived may not confer ownership."""

    def test_chained_derivation_refuses_to_generate(self):
        patched = [
            inv.DbLane(l.table,
                       inv.DirectOrExclusiveInbound("person_id", "conv_id", ()),
                       l.klass, l.portable, l.erasable)
            if l.table == "trip_turn_links" else l
            for l in inv.DB_LANES]
        with declaration(patched):
            with self.assertRaises(ValueError):
                inv._owner_chain_sql("trip_turn_links")
            # and the whole sessions predicate must fail closed, not silently
            # generate ownership SQL from a derived chain
            with self.assertRaises(ValueError):
                inv.owner_predicate("sessions")


if __name__ == "__main__":
    unittest.main()
