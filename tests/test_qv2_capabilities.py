"""Batch C-4C — what Questionnaire V2 can write TODAY, measured three ways.

    actual writes   — tests/qv2_capability_harness.js drives every shipped V2
                      control; the Life Record changes it sends (and the real
                      writer accepts) are translated here into catalog concepts
    FROZEN_EXPECTED — written below, by hand, in this file
    declaration     — QV2_CAPABILITIES in ui/js/questionnaire-v2-model.js

All three must be equal, and the compiled catalog's `questionnaire: editable`
set must equal them too. The frozen set is NOT read from the declaration: a
declaration that hides a control and also supplies the expected answer would
make both sides shrink together and pass. Deleting a concept from the
declaration hides its control (fail closed), so the actual set shrinks and no
longer equals FROZEN_EXPECTED. Declaring a concept with no control (a C-4E–G
concept, early) makes the declaration larger than the actual set.

Supervisor ruling (C-4C): TODAY ONLY. When a later slice ships a control, it
adds the concept to the declaration AND to FROZEN_EXPECTED, and this test
proves the control writes it.

Structural translation (the editor writes structure, not only assertions):
    add   people/<p>/names/<n>        → person.name.full; kind also_known_as
                                         → also person.name.alias (a `variant`
                                         is a whole variant name, NOT an alias)
    set   people/<p>/names/<n>        → person.name.full
    set   people/<p>/preferredNameRef → person.name.preferred
    add   relationships/<r>           → relationship.kind (+ relationship.period
                                         when it carries a period)
    set   relationships/<r>           → relationship.period when the period
                                         changed; other fields have no concept
    add   assertions/<a>              → its conceptId
    add   people/<p>                  → (person existence is not a concept)
Anything else is UNTRANSLATED and fails the test — a write this file does not
understand is a write nobody has classified.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))
sys.path.insert(0, str(REPO))

from api import db as _db  # noqa: E402
from tests.test_life_record_writer import NORA, _Db  # noqa: E402

NODE = shutil.which("node")
HAVE_JSDOM = bool(NODE) and subprocess.run(
    [NODE, "-e", "require('jsdom')"], cwd=REPO, capture_output=True).returncode == 0
MODEL = REPO / "ui" / "js" / "questionnaire-v2-model.js"
CATALOG = REPO / "server" / "code" / "api" / "services" / "concept_catalog_v1.json"

# ── FROZEN. Edit only when a shipped control is added or removed. ────────
FROZEN_EXPECTED = frozenset({
    "person.name.full",
    "person.name.preferred",
    "person.name.alias",
    "person.life_status",
    "person.pronouns",
    "person.birth.order",
    "person.reported_count.siblings",
    "person.reported_count.children",
    "person.reported_count.grandchildren",
    "relationship.kind",
    "relationship.period",
    "relationship.qualifier.lineage_side",
})
# Displayed by V2 today, NOT editable (C-4E–G / C-5 own their editors).
READ_ONLY_TODAY = ("person.death.date", "person.death.reported_age", "person.languages",
                   "person.education", "person.military_service", "story.desired",
                   "story.life_today.routine", "story.name_origin", "story.reading",
                   "person.birth.date", "event.union.date", "event.residence.period",
                   "event.service.period")
FUTURE_EVENT_DATES = ("event.work.period", "event.education.period", "event.separation.date",
                      "event.activity.period")
SPLIT_NAME_PARTS = ("person.name.given", "person.name.family", "person.name.birth_family")


def translate(changes):
    """Life Record changes → (concepts, untranslated). The rules are the
    module docstring's; nothing here reads the declaration."""
    concepts, untranslated = set(), []
    for ch in changes:
        op, p, v = ch.get("op"), ch.get("path", "").split("/"), ch.get("value")
        if op == "add" and len(p) == 2 and p[0] == "people":
            continue
        if len(p) == 4 and p[0] == "people" and p[2] == "names" and op in ("add", "set"):
            concepts.add("person.name.full")
            if op == "add" and (v or {}).get("kind") == "also_known_as":
                concepts.add("person.name.alias")
            continue
        if op == "set" and len(p) == 3 and p[0] == "people" and p[2] == "preferredNameRef":
            concepts.add("person.name.preferred")
            continue
        if len(p) == 2 and p[0] == "relationships" and op == "add":
            concepts.add("relationship.kind")
            if (v or {}).get("period"):
                concepts.add("relationship.period")
            continue
        if len(p) == 2 and p[0] == "relationships" and op == "set":
            before = (ch.get("expectedPrevious") or {}).get("period")
            if (v or {}).get("period") != before:
                concepts.add("relationship.period")
            continue
        if op == "add" and len(p) == 2 and p[0] == "assertions":
            concepts.add(v["conceptId"])
            continue
        untranslated.append(ch)
    return concepts, untranslated


def declared(root=None):
    js = ("const m=require(process.argv[1]);"
          "process.stdout.write(JSON.stringify(m.CAPABILITIES.editableConcepts));")
    model = Path(root or REPO) / "ui" / "js" / "questionnaire-v2-model.js"
    out = subprocess.run([NODE, "-e", js, str(model)], capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise AssertionError(out.stderr[-1500:])
    return json.loads(out.stdout)


def run_harness(root=None):
    env = {"QV2_DB": str(_db.DB_PATH), "QV2_PY": sys.executable, "QV2_A": NORA,
           "PATH": os.environ.get("PATH", "")}
    if root:
        env["QV2_ROOT"] = str(root)
    out = subprocess.run([NODE, str(REPO / "tests" / "qv2_capability_harness.js")], cwd=REPO, env=env,
                         capture_output=True, text=True, timeout=180)
    if out.returncode != 0:
        raise AssertionError(out.stderr[-2000:])
    return json.loads(out.stdout)


@unittest.skipUnless(HAVE_JSDOM, "node + jsdom are required — npm install")
class CapabilityParity(unittest.TestCase):
    """ONE measurement per class (the harness is slow on /mnt/c), taken on the
    shipped files against a real migrated SQLite; every test reads it."""

    @classmethod
    def setUpClass(cls):
        db = _Db("run")
        db.setUp()
        cls._db = db
        try:
            db.ok([db.name(NORA, "n1", "Ines Okafor-Lund"),
                   db.name(NORA, "n2", "Ines Okafor", kind="former"),
                   {"op": "set", "path": f"people/{NORA}/preferredNameRef", "value": "n1",
                    "expectedPrevious": None},
                   {"op": "add", "path": "people/p-m", "value": {}},
                   db.name("p-m", "nm", "Ada Okafor"),
                   {"op": "add", "path": "relationships/r1", "value": {
                       "subjectPersonId": "p-m", "otherPersonId": NORA, "kind": "parent_of",
                       "period": {"start": {"text": "1939", "value": "1939", "precision": "year"}}}}])
            root = os.environ.get("QV2_ROOT")
            cls.r = run_harness(root)
            cls.decl = declared(root)
        except Exception:
            db.tearDown()
            raise
        cls.changes = [c for p in cls.r.get("patches", []) for c in p["changes"]]
        cls.actual, cls.untranslated = translate(cls.changes)

    @classmethod
    def tearDownClass(cls):
        cls._db.tearDown()

    def test_the_harness_ran(self):
        self.assertNotIn("error", self.r, self.r.get("error"))

    def test_the_editor_saved_one_patch_the_writer_accepted(self):
        self.assertTrue(self.r["saved"], self.r["patches"])

    def test_every_write_is_translated(self):
        self.assertEqual(self.untranslated, [], "a V2 write this test cannot classify")

    def test_actual_writes_equal_the_frozen_set(self):
        self.assertEqual(sorted(self.actual), sorted(FROZEN_EXPECTED),
                         f"missing {sorted(FROZEN_EXPECTED - self.actual)}, "
                         f"extra {sorted(self.actual - FROZEN_EXPECTED)}")

    def test_the_declaration_equals_the_frozen_set(self):
        self.assertEqual(len(self.decl), len(set(self.decl)), "duplicates in the declaration")
        self.assertEqual(sorted(self.decl), sorted(FROZEN_EXPECTED))

    def test_every_declared_concept_has_a_real_write_path(self):
        self.assertEqual(sorted(set(self.decl) - self.actual), [],
                         "declared editable, but no shipped control writes it")

    def test_every_real_write_is_declared(self):
        self.assertEqual(sorted(self.actual - set(self.decl)), [],
                         "a shipped control writes a concept the declaration omits")

    def test_relationship_period_is_a_structural_write(self):
        rel = [c for c in self.changes if c["path"].startswith("relationships/")]
        self.assertTrue(any(c["op"] == "set" and c["value"].get("period") != c["expectedPrevious"].get("period")
                            for c in rel), "the period change on r1 is a `set` of the relationship")
        self.assertFalse(any(c["path"].startswith("assertions/") and c["value"]["conceptId"] == "relationship.period"
                             for c in self.changes), "the period is structure, not an assertion")
        # the EDIT of an existing relationship's period, translated on its own
        # (the added relationship also carries a period, which would otherwise
        # hide a translator that stopped recognising the edit)
        edits = [c for c in rel if c["op"] == "set"]
        self.assertEqual(translate(edits)[0], {"relationship.period"})

    def test_names_are_whole_and_only_also_known_as_is_an_alias(self):
        names = [c for c in self.changes if "/names/" in c["path"]]
        added = sorted(c["value"].get("kind") for c in names
                       if c["op"] == "add" and c["path"].startswith(f"people/{NORA}/"))
        self.assertEqual(added, ["also_known_as", "variant"], "the narrator's two added names")
        for c in names:
            for part in ("givenParts", "family", "birthFamily"):
                self.assertNotIn(part, c["value"], f"a whole-name edit wrote {part}")
        variant_only, _ = translate([c for c in names if c["value"].get("kind") == "variant"])
        self.assertEqual(variant_only, {"person.name.full"}, "a variant is not an alias")
        self.assertTrue(self.actual.isdisjoint(SPLIT_NAME_PARTS))

    def test_read_only_and_future_concepts_are_not_editable(self):
        for c in READ_ONLY_TODAY + FUTURE_EVENT_DATES:
            self.assertNotIn(c, self.decl, c)
            self.assertNotIn(c, self.actual, c)

    def test_the_editor_fails_closed_with_an_empty_declaration(self):
        for tp, census in self.r["closed"].items():
            self.assertEqual(census, {k: 0 for k in census}, f"{tp}: controls offered with nothing declared")


@unittest.skipUnless(NODE, "node is required")
class EventDateMapsAgree(unittest.TestCase):
    """The browser read model's EVENT_DATE_CONCEPT mirrors the server's."""

    def test_browser_and_server_maps_are_identical(self):
        from api.services.life_record import store
        js = ("const m=require(process.argv[1]);"
              "process.stdout.write(JSON.stringify(m.EVENT_DATE_CONCEPT));")
        out = subprocess.run([NODE, "-e", js, str(MODEL)], capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout), store.EVENT_DATE_CONCEPT)
        for etype in ("work", "education", "separation", "activity"):
            self.assertIn(etype, store.EVENT_DATE_CONCEPT, etype)


class CapabilityDeclarationParser(unittest.TestCase):
    """The compiler reads the declaration fail-closed (C-4C §4)."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "ccc", REPO / "scripts" / "catalog" / "compile_concept_catalog.py")
        cls.cc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.cc)
        from api.services import concept_catalog_source as src
        cls.src = src
        cls.text = MODEL.read_text(encoding="utf-8")

    def read(self, text):
        return self.cc.read_qv2_capabilities(text, self.src.CONCEPTS, self.src.DERIVED_CONCEPTS)

    def refused(self, text, why):
        with self.assertRaises(self.cc.CompileRefused) as cm:
            self.read(text)
        self.assertIn(why, " ".join(cm.exception.args[0]))

    def test_the_shipped_block_is_one_strict_json_literal(self):
        ids, sha = self.read(self.text)
        self.assertEqual(set(ids), FROZEN_EXPECTED)
        self.assertEqual(len(sha), 64)
        self.assertEqual(self.text.count(self.cc.QV2_BEGIN), 1)
        self.assertEqual(self.text.count(self.cc.QV2_END), 1)

    def test_malformations_refuse(self):
        B, E = self.cc.QV2_BEGIN, self.cc.QV2_END
        self.refused(self.text.replace(B, ""), "begin marker missing")
        self.refused(self.text.replace(E, ""), "end marker missing")
        self.refused(self.text + "\n" + B + " var QV2_CAPABILITIES = {}; " + E, "more than one")
        self.refused(self.text.replace('"version": 1,', '"version": 1, // note'), "not strict JSON")
        self.refused(self.text.replace('"relationship.qualifier.lineage_side"\n',
                                       '"relationship.qualifier.lineage_side",\n'), "not strict JSON")
        self.refused(self.text.replace('"version": 1,', '"version": 1, "extra": 2,'), "exactly")
        self.refused(self.text.replace('"person.pronouns",', '"person.pronouns", "person.pronouns",'),
                     "duplicate")
        self.refused(self.text.replace('"person.pronouns",', '"person.pronouns", 7,'), "must be a string")
        self.refused(self.text.replace('"person.pronouns",', '"person.pronouns", "person.shoe_size",'),
                     "not a concept")
        self.refused(self.text.replace('"person.pronouns",', '"person.pronouns", "person.zodiac_sign",'),
                     "derived_readonly")


class CompiledCatalogAgrees(unittest.TestCase):
    """The committed catalog's concept-level `questionnaire` property is the
    declaration — and the old form's path membership is still recorded."""

    @classmethod
    def setUpClass(cls):
        cls.cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        cls.q = {c["concept_id"]: c["questionnaire"] for c in cls.cat["concepts"]}

    def test_editable_is_exactly_the_frozen_set(self):
        self.assertEqual(sorted(k for k, v in self.q.items() if v == "editable"), sorted(FROZEN_EXPECTED))

    def test_the_old_form_no_longer_decides_but_is_still_recorded(self):
        paths = self.cat["bindings"]["paths"]
        legacy = {r["concept_id"] for r in paths if "questionnaire" in r["in"]}
        for c in SPLIT_NAME_PARTS + ("person.birth.date", "event.union.date"):
            self.assertIn(c, legacy, f"{c}: its legacy form path must stay recorded")
            self.assertEqual(self.q[c], "not_offered", f"{c}: the old form must not make it editable")
        prov = {c["concept_id"]: c["provenance"] for c in self.cat["concepts"]}
        self.assertIn("QV2_CAPABILITIES", prov["person.pronouns"]["questionnaire"])
        self.assertIn("questionnaire_schema", prov["person.pronouns"]["legacy_questionnaire_paths"])

    def test_derived_stays_derived(self):
        self.assertEqual(self.q["person.zodiac_sign"], "derived_readonly")

    def test_new_event_date_concepts(self):
        con = {c["concept_id"]: c for c in self.cat["concepts"]}
        for cid, vt, card in (("event.work.period", "date_interval", "many"),
                              ("event.education.period", "date_interval", "many"),
                              ("event.separation.date", "date", "one")):
            self.assertEqual((con[cid]["value_type"], con[cid]["cardinality"], con[cid]["questionnaire"]),
                             (vt, card, "not_offered"), cid)
        bound = {(r["event_type"], r["concept_id"]) for r in self.cat["bindings"]["event_dates"]}
        for pair in (("work", "event.work.period"), ("education", "event.education.period"),
                     ("separation", "event.separation.date"), ("activity", "event.activity.period")):
            self.assertIn(pair, bound)


if __name__ == "__main__":
    unittest.main()
