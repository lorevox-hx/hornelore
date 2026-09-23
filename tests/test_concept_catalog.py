"""WO-HORNELORE-INTEGRATED-LIFE-RECORD-01 Batch A1 — the concept catalog.

WHAT THIS PROVES, AND AT WHICH BOUNDARY (docs/TESTING-DOCTRINE.md).

  1. COVERAGE is checked against the REAL producers, imported independently
     of the compiler: `EXTRACTABLE_FIELDS` from the extract router itself,
     `questionnaire_schema.load_schema()`, `bio_schema.iter_seed()`, and
     `profile_seed.TOPIC_REGISTRY`. The compiler measures the same things by
     its own route (regex over extract.py); if the two disagree, this fails —
     a coverage test that reused the compiler's parse would inherit its bugs.
  2. The COMMITTED catalog equals a fresh compile. It cannot drift from its
     sources without this test going red.
  3. The LOADER refuses malformed catalogs — each rule is mutated below and
     must be caught. A validator nothing tries to break proves nothing.
  4. The COMPILER refuses — an unbound path, an undefined concept, an
     unapproved decision — rather than writing a partial catalog.
  5. The DECIDED SEMANTICS hold in the shipped file: each assertion names
     the decision it enforces.

Run (per CLAUDE.md — per module, and read the skip count):
    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_concept_catalog
"""
import copy
import importlib.util
import json
import os
import re
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "server", "code"))

# The extract router needs fastapi/pydantic to IMPORT; only its data is used
# here. Stub them when absent, exactly as test_extract_schema_coverage does,
# so this suite runs (and does not silently skip) on every interpreter.
if "fastapi" not in sys.modules:
    try:
        import fastapi  # noqa: F401
    except ImportError:
        fa = types.ModuleType("fastapi")

        class _APIRouter:
            def __init__(self, *a, **kw): pass
            def post(self, *a, **kw): return lambda fn: fn
            def get(self, *a, **kw): return lambda fn: fn
        fa.APIRouter = _APIRouter
        fa.HTTPException = type("HTTPException", (Exception,), {})
        sys.modules["fastapi"] = fa
if "pydantic" not in sys.modules:
    try:
        import pydantic  # noqa: F401
    except ImportError:
        pd = types.ModuleType("pydantic")

        class _BaseModel:
            def __init__(self, **kw):
                for k, v in kw.items():
                    setattr(self, k, v)
        pd.BaseModel = _BaseModel
        pd.Field = lambda *a, **kw: None
        sys.modules["pydantic"] = pd

from api.services import concept_catalog as cc  # noqa: E402


def _load_file(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


COMPILER = _load_file("compile_concept_catalog", "scripts/catalog/compile_concept_catalog.py")
CAT = cc.load()
with open(cc.CATALOG_PATH, encoding="utf-8") as _fh:
    RAW = json.load(_fh)


def _base(p):
    return re.sub(r"\[\d*\]", "", p)


# ── 1. coverage against the real producers ────────────────────────────────
class CoverageAgainstRealProducers(unittest.TestCase):

    def test_every_extractable_field_is_bound(self):
        from api.routers.extract import EXTRACTABLE_FIELDS
        unbound = sorted(k for k in EXTRACTABLE_FIELDS if CAT.binding(k) is None)
        self.assertEqual(unbound, [], "extraction targets the catalog does not know")
        # and the compiler's regex measured the same set the router holds
        compiled = {r["path"] for r in RAW["bindings"]["paths"] if r["extraction_member"]}
        self.assertEqual(compiled, {_base(k) for k in EXTRACTABLE_FIELDS},
                         "the compiler's view of EXTRACTABLE_FIELDS differs from the router's")

    def test_every_questionnaire_field_is_bound(self):
        from api.services import questionnaire_schema as qs
        schema = qs.load_schema()
        paths = [f"{sid}.{f}" for sid, sec in schema.items() for f in sec.get("fields", {})]
        self.assertTrue(paths, "questionnaire_schema returned nothing")
        self.assertEqual(sorted(p for p in paths if CAT.binding(p) is None), [])

    def test_every_asking_key_is_bound(self):
        from api.services import bio_schema
        keys = [f.field_key for f in bio_schema.iter_seed()]
        self.assertEqual(len(keys), 84, "bio_schema's seed size changed; recompile and review")
        self.assertEqual(sorted(k for k in keys if CAT.asking_binding(k) is None), [])

    def test_every_profile_seed_evidence_path_is_bound(self):
        from api.services import profile_seed
        bound = {(r["topic_id"], r["path"]) for r in RAW["bindings"]["profile_seed"]}
        missing = []
        for t in profile_seed.TOPIC_REGISTRY:
            for p in tuple(t.profile_paths) + tuple(t.projection_paths) + tuple(t.bio_keys):
                if (t.topic_id, p) not in bound:
                    missing.append((t.topic_id, p))
        self.assertEqual(missing, [], "Profile Seed reads evidence the catalog cannot resolve")


# ── 2. the committed catalog is what the sources produce ─────────────────
class CommittedEqualsFreshCompile(unittest.TestCase):

    def test_no_drift(self):
        fresh = COMPILER.render(COMPILER.compile_catalog())
        with open(cc.CATALOG_PATH, encoding="utf-8") as fh:
            committed = fh.read()
        self.assertEqual(fresh, committed,
                         "concept_catalog_v1.json is stale — run "
                         "scripts/catalog/compile_concept_catalog.py and review the diff")


# ── 3. the loader refuses malformed catalogs ─────────────────────────────
class LoaderRefuses(unittest.TestCase):

    def _mutant(self, fn):
        m = copy.deepcopy(RAW)
        fn(m)
        return cc.validate(m)

    def _concept(self, m, cid):
        return next(c for c in m["concepts"] if c["concept_id"] == cid)

    def test_the_shipped_catalog_is_valid(self):
        self.assertEqual(cc.validate(RAW), [])

    def test_a_missing_property_is_refused_not_defaulted(self):
        # The SPECIFIC message is asserted. The first version accepted any
        # problem mentioning the property's name, and a mutation that deleted
        # the explicit-statement rule survived: the value checks ("lori.askable
        # =None") reported the absence as a bad value instead. D1f's rule is
        # that every property is STATED, so absence must be reported as absence.
        for prop in ("questionnaire", "extraction", "lori", "narrative_value"):
            probs = self._mutant(lambda m: self._concept(m, "person.occupation").pop(prop))
            self.assertTrue(any(f"does not state `{prop}`" in p for p in probs),
                            f"omitting `{prop}` was not reported as a missing statement: {probs}")

    def test_eligible_with_no_scope_is_refused(self):
        def f(m):
            self._concept(m, "person.occupation")["extraction"]["scope"] = []
        self.assertTrue(any("no scope" in p for p in self._mutant(f)))

    def test_a_derived_concept_may_not_be_asked(self):
        def f(m):
            self._concept(m, "person.zodiac_sign")["lori"]["askable"] = "proactive"
        self.assertTrue(any("derived concept" in p for p in self._mutant(f)))

    def test_a_retirement_without_a_decision_is_refused(self):
        def f(m):
            r = next(r for r in m["bindings"]["paths"] if r["disposition"] == "retired")
            r["decision_ids"] = []
        self.assertTrue(any("without a decision" in p for p in self._mutant(f)))

    def test_an_undefined_concept_is_refused(self):
        def f(m):
            r = next(r for r in m["bindings"]["paths"] if r["disposition"] == "bind")
            r["concept_id"] = "made.up.concept"
        self.assertTrue(any("not defined" in p for p in self._mutant(f)))

    def test_a_path_bound_twice_is_refused(self):
        def f(m):
            m["bindings"]["paths"].append(copy.deepcopy(m["bindings"]["paths"][0]))
        self.assertTrue(any("bound twice" in p for p in self._mutant(f)))

    def test_loading_a_bad_catalog_raises(self):
        bad = copy.deepcopy(RAW)
        bad["concepts"][0].pop("lori")
        with self.assertRaises(cc.CatalogInvalid):
            cc.Catalog(bad)


# ── 4. the compiler refuses rather than writing a partial catalog ────────
class CompilerRefuses(unittest.TestCase):

    def _compile_with(self, mutate_source=None, mutate_decisions=None):
        real_load = COMPILER._load

        def patched(name, rel):
            mod = real_load(name, rel)
            if name == "concept_catalog_source" and mutate_source:
                mutate_source(mod)
            if name == "seeds" and mutate_decisions:
                orig = mod.decisions

                def decisions():
                    d = orig()
                    mutate_decisions(d)
                    return d
                mod.decisions = decisions
            return mod
        COMPILER._load = patched
        try:
            return COMPILER.compile_catalog()
        finally:
            COMPILER._load = real_load

    def test_an_unbound_field_refuses(self):
        def f(src):
            src.CONCEPT_BY_FIELD = {k: v for k, v in src.CONCEPT_BY_FIELD.items()
                                    if k != "occupation"}
        with self.assertRaises(COMPILER.CompileRefused) as cm:
            self._compile_with(mutate_source=f)
        self.assertTrue(any("UNBOUND path" in p for p in cm.exception.args[0]))

    def test_a_retirement_of_a_nonexistent_path_refuses(self):
        def f(src):
            src.RETIRED = dict(src.RETIRED, **{"parents.notez": "D1d"})
        with self.assertRaises(COMPILER.CompileRefused):
            self._compile_with(mutate_source=f)

    def test_an_alias_between_different_facts_refuses(self):
        real = COMPILER._appendix_alias_pairs

        def bad_pairs():
            p = real()
            p["family.spouse.firstName"] = ("spouse.birthDate", "A04")   # a name → a date
            return p
        COMPILER._appendix_alias_pairs = bad_pairs
        try:
            with self.assertRaises(COMPILER.CompileRefused) as cm:
                COMPILER.compile_catalog()
        finally:
            COMPILER._appendix_alias_pairs = real
        self.assertTrue(any("not the same fact" in p for p in cm.exception.args[0]))

    def test_an_unapproved_decision_refuses(self):
        def f(d):
            for r in d["rows"]:
                if r["decision_id"] == "D3":
                    r["state"] = "pending"
        with self.assertRaises(COMPILER.CompileRefused) as cm:
            self._compile_with(mutate_decisions=f)
        self.assertTrue(any("D3" in p and "not buildable" in p for p in cm.exception.args[0]))


# ── 5. the decided semantics, in the shipped file ────────────────────────
class DecidedSemantics(unittest.TestCase):

    def test_birth_date_is_one_concept_for_every_subject(self):
        subjects = {r["subject"] for r in RAW["bindings"]["paths"]
                    if r["concept_id"] == "person.birth.date"}
        self.assertTrue({"narrator", "parent", "sibling", "child", "spouse",
                         "grandparent", "great_grandparent"} <= subjects)

    def test_D1a_singular_and_plural_grandparent_story_are_one_fact(self):
        self.assertEqual(CAT.concept_for_path("grandparents.memorableStory"),
                         CAT.concept_for_path("grandparents.memorableStories"))

    def test_D1c_age_at_death_is_a_reported_assertion(self):
        self.assertEqual(CAT.concept_for_path("parents.ageAtDeath"), "person.death.reported_age")
        self.assertIsNone(CAT.concept("person.death.age"), "a stored derived age exists")

    def test_D1d_notes_retired_and_undecided_notes_are_not(self):
        for p in ("family.children.notes", "health.notes", "hobbies.notes"):
            self.assertTrue(CAT.is_retired(p), p)
        for p in ("parents.notes", "faith.notes", "travel.notes"):
            self.assertFalse(CAT.is_retired(p), f"{p} was retired without a decision")

    def test_D3_no_clinical_extraction(self):
        for p in ("health.majorCondition", "health.currentMedications"):
            self.assertTrue(CAT.is_retired(p), p)
        self.assertEqual(CAT.concept_for_path("health.cognitiveChange"), "story.health.reflection")

    def test_D3_sensitive_topics_are_never_proactive(self):
        for key in ("major_illness", "major_loss", "military_combat"):
            b = CAT.asking_binding(key)
            self.assertEqual(CAT.askable(b["concept_id"], b["subject"]), "responsive_only", key)

    def test_D1f_life_status_extractable_where_decided(self):
        c = CAT.concept("person.life_status")
        self.assertTrue(c["extraction"]["eligible"])
        self.assertEqual(c["extraction"]["scope"], ["parents", "spouse"])
        self.assertEqual(CAT.prompt_role("person.life_status", subject_is_narrator=False),
                         "turn_scoped", "a mentioned relative's life status must reach the turn")

    def test_D1f_askability_is_per_subject(self):
        self.assertEqual(CAT.askable("person.name.given", "parent:father"), "proactive")
        self.assertEqual(CAT.askable("person.name.given", "friend"), "responsive_only")

    def test_D1f_zodiac_is_derived_and_never_asked(self):
        c = CAT.concept("person.zodiac_sign")
        self.assertEqual(c["questionnaire"], "derived_readonly")
        self.assertEqual(c["lori"]["askable"], "never")

    def test_D5_life_span_anchors(self):
        self.assertEqual(CAT.concept("person.birth.date")["special_projection"]["supplies"],
                         "life_span.start")
        self.assertEqual(CAT.concept("person.death.date")["special_projection"]["supplies"],
                         "life_span.end")

    def test_trips_stay_in_the_trip_domain(self):
        for c in CAT.concepts():
            if c["concept_id"].startswith("trip."):
                self.assertEqual(c["storage"]["owner"], "trip_domain", c["concept_id"])

    def test_story_attribution_comes_from_the_record(self):
        for c in CAT.concepts():
            if c["concept_id"].startswith("story."):
                self.assertEqual(c["memoir"]["route"], "from_record_origin", c["concept_id"])

    def test_D1a_D1b_decided_aliases_are_recorded_path_by_path(self):
        aliases = {r["path"]: r["alias_of"] for r in RAW["bindings"]["paths"] if r["alias_of"]}
        self.assertEqual(len(aliases), 13, aliases)
        self.assertEqual(aliases["family.children.dateOfBirth"], "children.birthDate")
        self.assertEqual(aliases["grandparents.memorableStory"], "grandparents.memorableStories")
        for ext, form in aliases.items():
            self.assertEqual((CAT.binding(ext)["concept_id"], CAT.binding(ext)["subject"]),
                             (CAT.binding(form)["concept_id"], CAT.binding(form)["subject"]),
                             f"{ext} → {form} is not the same fact")

    def test_a_shared_concept_alone_is_not_an_alias(self):
        # spouse.firstName and spouse.middleName are both person.name.given:
        # concept equality must never produce a redirect by itself.
        self.assertIsNone(CAT.alias_target("spouse.middleName"))
        self.assertEqual(CAT.alias_target("family.spouse.middleName"), "spouse.middleName")

    def test_extraction_scope_offers_only_that_section(self):
        offered = CAT.extraction_paths_for_scope("parents")
        self.assertTrue(offered)
        self.assertTrue(all(p.startswith("parents.") for p in offered), offered)
        self.assertNotIn("health.currentMedications", CAT.extraction_paths_for_scope("health"))


if __name__ == "__main__":
    unittest.main()
