"""WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01 Continuation A, sections Q+R.

The operator control surface, exercised THROUGH THE ROUTER. Every
assertion here crosses the HTTP boundary, because the properties that
matter are properties of what an operator's browser receives, and the
resolver-level suite already proves the resolution itself.

That distinction is the doctrine in CLAUDE.md — *a fixture may not
supply the property being proven* — applied to this slice. It would be
easy and worthless to build an override map by hand, resolve it, and
assert the panel "would" show it. So the overrides in these tests are
created by POSTing to the route, and read back out of a subsequent
GET: the two production paths that will actually be used.

THE THREE PROPERTIES THAT COST THE MOST IF THEY ARE WRONG

  ONE ACTION IS ONE REVISION. `All Switchable Off` moving the revision
  by 37 would mean a turn could acquire a half-applied configuration no
  operator ever chose, and every transcript taken during the window
  would name a generation that never existed. Asserted as an exact
  delta, not as "it changed".

  A PROTECTED AUTHORITY IS REFUSED, AND SAYS WHY. Not silently ignored,
  and not answered with a bare 403 — the operator has to be able to tell
  "cannot, for safety" from "cannot, until somebody splits a string".

  A STALE VIEW LOSES, AND IS TOLD WHAT WON. The 409 carries the live
  configuration so a second browser tab corrects itself instead of
  overwriting a newer selection.
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "server" / "code"))

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    _READY, _WHY = True, ""
except Exception as exc:               # pragma: no cover - env dependent
    _READY, _WHY = False, str(exc)

from api.services import lori_guard_registry as registry


ENV_GATE = "HORNELORE_OPERATOR_GUARD_LAB"


@unittest.skipUnless(_READY, f"fastapi unavailable: {_WHY}")
class _GuardLabRouteCase(unittest.TestCase):
    """A temp database and a freshly bound router for every test.

    ISOLATION IS LOAD-BEARING HERE FOR THE SAME REASON IT WAS IN
    `test_people_testing_only_persistence`. `db.DB_PATH` resolves AT
    IMPORT TIME from `DATA_DIR`, relative to the working directory, so a
    suite that creates narrators without redirecting it writes them into
    the developer's real `data/db/lorevox.sqlite3` — which on this
    machine holds Kent and Janice.

    The router must be reloaded TOO, and that is easy to miss: it binds
    `from .. import db as _db` at module scope, so reloading `api.db`
    alone leaves the router holding the previous module object and
    writing to the previous database. The setUp assertion below refuses
    to run at all unless the path really moved.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._prev = {k: os.environ.get(k)
                      for k in ("DATA_DIR", "DB_NAME", ENV_GATE)}
        os.environ["DATA_DIR"] = self._tmp.name
        os.environ["DB_NAME"] = "test_guard_lab_api.sqlite3"
        os.environ[ENV_GATE] = "1"

        from api import db as _db
        importlib.reload(_db)
        self.db = _db
        self.db.init_db()
        self.assertTrue(
            str(self.db.DB_PATH).startswith(self._tmp.name),
            f"Refusing to run against {self.db.DB_PATH} — this suite "
            f"writes narrators and guard configuration.")

        from api.routers import operator_guard_lab as _router
        importlib.reload(_router)
        self.router_module = _router

        app = FastAPI()
        app.include_router(_router.router)
        self.client = TestClient(app)
        self.addCleanup(self._restore)

    def _restore(self):
        for key, value in self._prev.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        from api import db as _db
        importlib.reload(_db)
        from api.routers import operator_guard_lab as _r
        importlib.reload(_r)

    # ── helpers that go through the wire, never around it ──────────────

    def state(self):
        resp = self.client.get("/api/operator/guard-lab/state")
        self.assertEqual(200, resp.status_code, resp.text)
        return resp.json()

    def row(self, payload, authority_id):
        for item in payload["authorities"]:
            if item["id"] == authority_id:
                return item
        self.fail(f"authority {authority_id} missing from the payload")

    def a_switchable_id(self):
        return registry.switchable()[0].id

    def a_protected_id(self):
        return registry.protected()[0].id


class GateTests(_GuardLabRouteCase):
    """404, not 403, so an outside probe learns nothing."""

    def test_every_route_is_404_when_the_feature_is_off(self):
        os.environ[ENV_GATE] = "0"
        checks = (
            ("get", "/api/operator/guard-lab/state", None),
            ("get", "/api/operator/guard-lab/narrators", None),
            ("post", "/api/operator/guard-lab/all-switchable-off",
             {"expected_revision": 0}),
            ("post", "/api/operator/guard-lab/restore-defaults",
             {"expected_revision": 0}),
            ("post", f"/api/operator/guard-lab/authorities/{self.a_switchable_id()}",
             {"enabled": False, "expected_revision": 0}),
        )
        for method, path, body in checks:
            with self.subTest(path=path):
                resp = (self.client.get(path) if method == "get"
                        else self.client.post(path, json=body))
                self.assertEqual(404, resp.status_code, resp.text)

    def test_a_disabled_gate_does_not_write(self):
        """The refusal must come BEFORE the store is touched."""
        before = self.state()["revision"]
        os.environ[ENV_GATE] = "0"
        self.client.post("/api/operator/guard-lab/all-switchable-off",
                         json={"expected_revision": before})
        os.environ[ENV_GATE] = "1"
        self.assertEqual(before, self.state()["revision"])


class StateShapeTests(_GuardLabRouteCase):
    """What the panel is given must be enough to render the truth."""

    def test_every_registered_authority_appears_exactly_once(self):
        payload = self.state()
        ids = [a["id"] for a in payload["authorities"]]
        self.assertEqual(sorted(ids), sorted(i.id for i in registry.REGISTRY))
        self.assertEqual(len(ids), len(set(ids)))

    def test_rows_arrive_in_canonical_pipeline_order(self):
        """Selection controls membership; POSITION decides order, and the
        operator reads the pipeline in the order it executes."""
        positions = [a["position"] for a in self.state()["authorities"]]
        self.assertEqual(positions, sorted(positions))

    def test_the_four_states_travel_separately(self):
        """The defect this shape exists to prevent is collapsing them.

        A single ON/OFF field could not distinguish 'the registry says
        so', 'the .env says so', 'you said so' and 'this is what the next
        turn gets'.
        """
        for a in self.state()["authorities"]:
            with self.subTest(id=a["id"]):
                for key in ("canonical_default", "deployment_default",
                            "operator_override", "effective", "reason"):
                    self.assertIn(key, a)
                self.assertIsInstance(a["canonical_default"], bool)
                self.assertIsInstance(a["effective"], bool)
                self.assertIn(a["reason"], (
                    "canonical_default", "operator_override", "protected",
                    "pending_seam", "system_parked", "deployment_default"))

    def test_one_row_can_hold_three_different_answers_at_once(self):
        """The four fields must be genuinely independent, not aliases.

        Presence and type prove nothing here — three fields all wired to
        the effective state would satisfy a shape check and still tell
        the operator the same lie three times. So this drives a row into
        a state where the correct values DISAGREE: canonically ON, the
        operator set it OFF, and OFF is what the next turn gets.
        """
        candidate = next(i for i in registry.switchable() if i.default_on)
        rev = self.state()["revision"]
        self.client.post(
            f"/api/operator/guard-lab/authorities/{candidate.id}",
            json={"enabled": False, "expected_revision": rev})

        row = self.row(self.state(), candidate.id)
        self.assertTrue(row["canonical_default"], "the registry says ON")
        self.assertEqual(False, row["operator_override"], "the operator said OFF")
        self.assertFalse(row["effective"], "the next turn gets OFF")
        self.assertTrue(row["differs_from_canonical"],
                        "the panel must mark this row as explained")

    def test_a_locked_row_carries_its_policy_reason(self):
        """'Cannot, for safety' must be distinguishable on screen from
        'cannot, until somebody splits a string'."""
        payload = self.state()
        for item in registry.protected():
            with self.subTest(id=item.id):
                row = self.row(payload, item.id)
                self.assertFalse(row["switchable"])
                self.assertEqual("PROTECTED", row["policy"])
                self.assertTrue(
                    row["policy_reason"],
                    "a protected row with no reason tells the operator "
                    "nothing they can act on")

    def test_identity_travels_with_the_configuration(self):
        payload = self.state()
        self.assertEqual(64, len(payload["registry_fingerprint"]))
        self.assertEqual(64, len(payload["selection_fingerprint"]))
        self.assertIsInstance(payload["revision"], int)

    def test_next_turn_semantics_are_stated_by_the_SERVER(self):
        """The promise the operator reads is the one the server keeps.

        If the panel composed this sentence itself, the wording and the
        behaviour could drift apart with nothing to notice.
        """
        payload = self.state()
        self.assertEqual("next_turn", payload["applies"])
        self.assertIn("NEXT", payload["applies_note"])

    def test_the_gate_names_all_four_conditions(self):
        """Without this the panel is a trap: a selection that cannot
        reach any turn looks identical to one that can."""
        gate = self.state()["gate"]
        names = {c["name"] for c in gate["conditions"]}
        self.assertEqual(names, {
            "armed_evaluation", "trace_recording", "testing_only_narrator",
            "real_narrators_never_eligible"})
        self.assertIn("can_apply_to_a_turn", gate)

    def test_pending_seam_is_reported_even_when_empty(self):
        """`All Switchable Off` is only truthful while this is empty, so
        the panel is given the list rather than the assumption."""
        payload = self.state()
        self.assertEqual(
            [p["id"] for p in payload["pending_seam"]],
            [i.id for i in registry.pending_seam()])


class SingleAuthorityTests(_GuardLabRouteCase):

    def test_excluding_one_authority_shows_through_a_fresh_read(self):
        """Written through the route, read back through the route."""
        aid = self.a_switchable_id()
        before = self.state()
        resp = self.client.post(
            f"/api/operator/guard-lab/authorities/{aid}",
            json={"enabled": False, "expected_revision": before["revision"]})
        self.assertEqual(200, resp.status_code, resp.text)

        fresh = self.row(self.state(), aid)
        self.assertFalse(fresh["effective"])
        self.assertEqual(False, fresh["operator_override"])
        self.assertEqual("operator_override", fresh["reason"])

    def test_the_write_response_is_the_whole_new_state(self):
        """This is what makes the panel restart-free and reload-free.

        A response that only said 'ok' would force the panel to re-derive
        or re-fetch, and re-deriving locally is how a panel and a server
        drift apart.
        """
        aid = self.a_switchable_id()
        rev = self.state()["revision"]
        body = self.client.post(
            f"/api/operator/guard-lab/authorities/{aid}",
            json={"enabled": False, "expected_revision": rev}).json()
        for key in ("revision", "registry_fingerprint",
                    "selection_fingerprint", "authorities", "counts",
                    "gate", "applies"):
            self.assertIn(key, body)
        self.assertEqual(len(registry.REGISTRY), len(body["authorities"]))

    def test_reset_deletes_the_override_rather_than_pinning_a_value(self):
        """Reset must leave the canonical default LIVE IN CODE.

        Writing today's default in would freeze it into this
        installation: change the registry default afterwards and this
        deployment silently keeps the old one.
        """
        aid = self.a_switchable_id()
        rev = self.state()["revision"]
        self.client.post(f"/api/operator/guard-lab/authorities/{aid}",
                         json={"enabled": False, "expected_revision": rev})
        rev = self.state()["revision"]
        resp = self.client.post(
            f"/api/operator/guard-lab/authorities/{aid}",
            json={"enabled": None, "expected_revision": rev})
        self.assertEqual(200, resp.status_code, resp.text)

        row = self.row(self.state(), aid)
        self.assertIsNone(row["operator_override"])
        self.assertNotEqual("operator_override", row["reason"])

    def test_a_protected_authority_is_refused_with_its_reason(self):
        aid = self.a_protected_id()
        before = self.state()
        resp = self.client.post(
            f"/api/operator/guard-lab/authorities/{aid}",
            json={"enabled": False, "expected_revision": before["revision"]})
        self.assertEqual(400, resp.status_code, resp.text)
        detail = resp.json()["detail"]
        self.assertEqual("not_switchable", detail["error"])
        self.assertEqual("PROTECTED", detail["policy"])

        after = self.state()
        self.assertEqual(before["revision"], after["revision"],
                         "a refused write must not consume a revision")
        self.assertEqual(self.row(before, aid)["effective"],
                         self.row(after, aid)["effective"])

    def test_an_unregistered_id_is_404(self):
        resp = self.client.post(
            "/api/operator/guard-lab/authorities/9999",
            json={"enabled": False, "expected_revision": 0})
        self.assertEqual(404, resp.status_code)


class OptimisticRevisionTests(_GuardLabRouteCase):
    """The stale-client clamp, at the boundary a stale client crosses."""

    def test_a_stale_revision_is_refused_and_does_not_write(self):
        aid = self.a_switchable_id()
        stale = self.state()["revision"]

        # Somebody else acts first.
        self.client.post("/api/operator/guard-lab/all-switchable-off",
                         json={"expected_revision": stale})
        moved = self.state()["revision"]
        self.assertNotEqual(stale, moved)

        resp = self.client.post(
            f"/api/operator/guard-lab/authorities/{aid}",
            json={"enabled": True, "expected_revision": stale})
        self.assertEqual(409, resp.status_code, resp.text)
        self.assertEqual(moved, self.state()["revision"],
                         "a refused write must not advance the revision")
        self.assertFalse(
            self.row(self.state(), aid)["effective"],
            "the stale write must not have landed")

    def test_the_conflict_carries_the_live_configuration(self):
        """So the panel corrects itself instead of insisting.

        A 409 that only complained would leave the operator to guess what
        changed, and their next click would be based on the same stale
        view that just lost.
        """
        stale = self.state()["revision"]
        self.client.post("/api/operator/guard-lab/all-switchable-off",
                         json={"expected_revision": stale})
        resp = self.client.post("/api/operator/guard-lab/restore-defaults",
                                json={"expected_revision": stale})
        self.assertEqual(409, resp.status_code)
        detail = resp.json()["detail"]
        self.assertEqual("stale_revision", detail["error"])
        self.assertEqual(stale, detail["expected_revision"])
        self.assertEqual(self.state()["revision"], detail["current_revision"])
        self.assertIsNotNone(detail["current"])
        self.assertEqual(len(registry.REGISTRY),
                         len(detail["current"]["authorities"]))

    def test_presets_also_honour_the_expected_revision(self):
        for path in ("all-switchable-off", "restore-defaults"):
            with self.subTest(path=path):
                resp = self.client.post(
                    f"/api/operator/guard-lab/{path}",
                    json={"expected_revision": 999})
                self.assertEqual(409, resp.status_code, resp.text)


class AtomicPresetTests(_GuardLabRouteCase):
    """One operator action is ONE revision. This is the whole point."""

    def test_all_switchable_off_moves_the_revision_exactly_once(self):
        before = self.state()["revision"]
        resp = self.client.post("/api/operator/guard-lab/all-switchable-off",
                                json={"expected_revision": before})
        self.assertEqual(200, resp.status_code, resp.text)
        self.assertEqual(
            before + 1, resp.json()["revision"],
            "37 sequential writes would produce 37 revisions and let a "
            "turn acquire a mixture no operator chose")

    def test_all_switchable_off_excludes_every_switchable_authority(self):
        """IC-11 at the operator boundary — the label must be truthful."""
        payload = self.client.post(
            "/api/operator/guard-lab/all-switchable-off",
            json={"expected_revision": self.state()["revision"]}).json()
        still_running = [a["id"] for a in payload["authorities"]
                         if a["switchable"] and a["effective"]]
        self.assertEqual([], still_running)

    def test_all_switchable_off_leaves_protected_authorities_alone(self):
        """It excludes the switchable population and NOTHING else, which
        is precisely what the label claims and no more."""
        before = self.state()
        after = self.client.post(
            "/api/operator/guard-lab/all-switchable-off",
            json={"expected_revision": before["revision"]}).json()
        for item in registry.protected():
            with self.subTest(id=item.id):
                self.assertEqual(self.row(before, item.id)["effective"],
                                 self.row(after, item.id)["effective"])

    def test_the_preset_and_the_row_count_agree(self):
        """Two independent paths through the API, cross-checked.

        The count of rows the panel would render as switchable must equal
        the count the preset actually excluded. Deriving both from
        `policy_counts()` would prove nothing; these come from the
        rendered rows and from the applied effect.
        """
        before = self.state()
        switchable_rows = [a["id"] for a in before["authorities"] if a["switchable"]]
        after = self.client.post(
            "/api/operator/guard-lab/all-switchable-off",
            json={"expected_revision": before["revision"]}).json()
        excluded = [a["id"] for a in after["authorities"]
                    if a["operator_override"] is False]
        self.assertEqual(sorted(switchable_rows), sorted(excluded))

    def test_restore_defaults_clears_every_override_in_one_revision(self):
        rev = self.state()["revision"]
        self.client.post("/api/operator/guard-lab/all-switchable-off",
                         json={"expected_revision": rev})
        rev = self.state()["revision"]
        payload = self.client.post(
            "/api/operator/guard-lab/restore-defaults",
            json={"expected_revision": rev}).json()
        self.assertEqual(rev + 1, payload["revision"])
        self.assertEqual(
            [], [a["id"] for a in payload["authorities"]
                 if a["operator_override"] is not None])


class TestingOnlyNarratorTests(_GuardLabRouteCase):
    """Eligibility is shown, never granted."""

    def test_only_testing_only_narrators_are_listed(self):
        real = self.db.create_person(display_name="Real Narrator")
        probe = self.db.create_person(display_name="Synthetic Probe",
                                      testing_only=True)
        listed = {n["id"] for n in
                  self.client.get("/api/operator/guard-lab/narrators")
                  .json()["items"]}
        self.assertIn(probe["id"], listed)
        self.assertNotIn(
            real["id"], listed,
            "a real narrator must never appear as an experiment target")

    def test_the_gate_block_reports_the_same_population(self):
        self.db.create_person(display_name="Synthetic Probe", testing_only=True)
        gate = self.state()["gate"]
        self.assertTrue(gate["testing_only_narrators"])
        met = {c["name"]: c["met"] for c in gate["conditions"]}
        self.assertTrue(met["testing_only_narrator"])

    def test_the_router_offers_no_way_to_grant_eligibility(self):
        """Read by AST over the ROUTER's own code.

        A substring search would match this docstring, which is the
        comment-matching failure CLAUDE.md records four instances of.
        The property is that no route function in this module calls
        anything that writes the flag.
        """
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(self.router_module))
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Attribute):
                    called.add(fn.attr)
                elif isinstance(fn, ast.Name):
                    called.add(fn.id)
        for forbidden in ("create_person", "update_person",
                          "set_testing_only", "update_profile_json"):
            with self.subTest(call=forbidden):
                self.assertNotIn(
                    forbidden, called,
                    f"{forbidden}() is called from the Guard Lab router. "
                    f"This surface may show eligibility and must never "
                    f"confer it.")


if __name__ == "__main__":
    unittest.main()
