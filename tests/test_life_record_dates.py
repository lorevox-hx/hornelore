"""C-4B — the Life Record date contract, at its production boundaries.

One fixture corpus (tests/fixtures/life_record_dates_v1.json) is the
executable contract. Nothing here restates it:

  * the SERVER parser (services/life_record/dates.py) reproduces every case;
  * the BROWSER parser (ui/js/questionnaire-v2-model.js `parseDateText`)
    reproduces every case — run under node, the shipped file, no copy;
  * the WRITER (apply_changes, real SQLite migrated by init_db) accepts or
    refuses each `server_agreement` case on a real date assertion;
  * a LEGACY date (put in by SQL — the writer now refuses to create one) is
    read as stored and carried through an unrelated write unchanged.

Skips the browser half (and says so) when node is not installed.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))
sys.path.insert(0, str(REPO))

from api import db as _db  # noqa: E402
from api.services.life_record import dates as D  # noqa: E402
from api.services.life_record import rules as R  # noqa: E402
from api.services.life_record import writer as W  # noqa: E402
from tests.test_life_record_writer import NORA, _Db, date  # noqa: E402

CORPUS = json.loads((REPO / "tests" / "fixtures" / "life_record_dates_v1.json").read_text(encoding="utf-8"))
MODEL = REPO / "ui" / "js" / "questionnaire-v2-model.js"
NODE = shutil.which("node")


def _expected(case):
    e = case["expect"]
    return "refuse" if e == "refuse" else (e["value"], e["precision"])


def _py(text):
    r = D.parse(text)
    return "refuse" if r[0] == "refuse" else (r[1], r[2])


class CorpusIsReal(unittest.TestCase):
    """The corpus is not allowed to be thin: a parser that returns text-only
    for everything must not pass by agreeing with a corpus of text-only cases."""

    def test_the_corpus_exercises_every_outcome(self):
        outs = [_expected(c) for c in CORPUS["cases"]]
        self.assertGreaterEqual(len(outs), 60)
        self.assertGreaterEqual(sum(o == "refuse" for o in outs), 4)
        self.assertGreaterEqual(sum(o != "refuse" and o[0] is None for o in outs), 10)
        vals = [o[0] for o in outs if o != "refuse" and o[0]]
        for mark in ("~", "?", "%", "X", "/", "/.."):
            self.assertTrue(any(mark in v for v in vals), f"no case carries {mark!r}")
        self.assertEqual(sorted({o[1] for o in outs if o != "refuse"}), sorted(D.PRECISIONS))


class ServerParser(unittest.TestCase):
    def test_every_corpus_case(self):
        bad = [(c["id"], c["text"], _expected(c), _py(c["text"]))
               for c in CORPUS["cases"] if _py(c["text"]) != _expected(c)]
        self.assertEqual(bad, [], f"{len(bad)} of {len(CORPUS['cases'])} disagree")

    def test_every_agreement_case_through_check(self):
        for c in CORPUS["server_agreement"]["cases"]:
            got = "accept" if D.check(c["supplied"], allow_interval=True) is None else "refuse"
            self.assertEqual(got, c["expect"], c["id"])

    def test_precision_is_granularity_not_exactness(self):
        # Ruling 1 (2026-09-24): 192X is YEAR precision, and so is 1989~.
        self.assertEqual(D.parse("the 1920s"), ("value", "192X", "year"))
        self.assertEqual(D.parse("about 1989"), ("value", "1989~", "year"))
        q = D.qualifiers({"text": "about 1989", "value": "1989~", "precision": "year"})
        self.assertTrue(q["approximate"], "a consumer reading precision alone would call this exact")
        self.assertTrue(D.qualifiers({"value": "192X", "precision": "year"})["unspecified_digits"])
        self.assertIsNone(D.calendar_parts("192X"), "a decade is not a calendar point")
        self.assertIsNone(D.calendar_parts("1960/1965"), "a range is not a calendar point")

    def test_legacy_precision_words_still_read(self):
        for c in CORPUS["legacy_compatibility"]["cases"]:
            q = D.qualifiers(c["stored"])
            if c["stored"]["precision"] == "approximate":
                self.assertTrue(q["approximate"], c["id"])
            if c["stored"]["precision"] == "uncertain":
                self.assertTrue(q["uncertain"], c["id"])

    def test_a_legacy_word_alone_still_means_approximate(self):
        # Pre-C-4 writes could store the word with no normalised value; the
        # mark cannot carry it there, so the word must.
        q = D.qualifiers({"text": "around 1945", "value": None, "precision": "approximate"})
        self.assertTrue(q["approximate"])
        q = D.qualifiers({"text": "maybe 1938", "value": None, "precision": "uncertain"})
        self.assertTrue(q["uncertain"])

    def test_a_legacy_precision_word_is_refused_with_the_reason(self):
        # The operator is told WHERE approximation goes, not just "mismatch".
        why = D.check({"text": "about 1989", "value": "1989~", "precision": "approximate"},
                      allow_interval=False)
        self.assertIn("go in the value", why or "")

    def test_a_single_date_slot_refuses_a_range(self):
        r = D.check({"text": "1960 to 1965", "value": "1960/1965", "precision": "year"},
                    allow_interval=False)
        self.assertIsNotNone(r)
        self.assertIn("range", r)


@unittest.skipUnless(NODE, "node is not installed — the browser parser is shipped JS")
class BrowserParser(unittest.TestCase):
    def test_every_corpus_case_matches_the_server(self):
        script = (
            "const m = require(process.argv[1]);"
            "const cases = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8')).cases;"
            "const out = cases.map(c => { const r = m.parseDateText(c.text);"
            "  return [c.id, r === null ? null : (r.refuse ? 'refuse' : [r.value, r.precision, r.text])]; });"
            "process.stdout.write(JSON.stringify(out));")
        p = subprocess.run([NODE, "-e", script, str(MODEL),
                            str(REPO / "tests" / "fixtures" / "life_record_dates_v1.json")],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        got = dict((k, v) for k, v in json.loads(p.stdout))
        bad = []
        for c in CORPUS["cases"]:
            js = got[c["id"]]
            if js is None:
                bad.append((c["id"], "null for non-empty text"))
                continue
            if js != "refuse":
                if js[2] != c["text"].strip():
                    bad.append((c["id"], "text was rewritten", js[2]))
                js = (js[0], js[1])
            if js != _expected(c):
                bad.append((c["id"], c["text"], _expected(c), js))
            if js != _py(c["text"]):
                bad.append((c["id"], "browser and server disagree", js, _py(c["text"])))
        self.assertEqual(bad, [])


class _Birth(_Db):
    def birth(self, text, value, precision, eid="e-b", aid="a-dob"):
        return [
            {"op": "add", "path": f"events/{eid}",
             "value": {"type": "birth", "participants": [{"person": NORA, "role": "subject"}]}},
            self.assertion(aid, "event", eid, "person.birth.date", date(text, value, precision)),
            {"op": "set", "path": f"people/{NORA}/birthEventRef", "value": eid, "expectedPrevious": None},
        ]

    def _put(self, sql, *args):
        con = sqlite3.connect(str(_db.DB_PATH))
        con.execute(sql, args)
        con.commit()
        con.close()


class WriterHoldsChangedDates(_Birth):
    def test_every_agreement_case_on_a_real_date_assertion(self):
        # event.residence.period is a date_interval concept in the catalog.
        # One move per case: two accepted accounts of one event's date would
        # (rightly) trip the competing-claims rule, which is not under test.
        for i, c in enumerate(CORPUS["server_agreement"]["cases"]):
            self.ok([{"op": "add", "path": f"events/e-mv{i}",
                      "value": {"type": "move", "participants": [{"person": NORA, "role": "resident"}]}}])
            r = self.write([self.assertion(f"a-{i}", "event", f"e-mv{i}", "event.residence.period",
                                           c["supplied"])])
            self.assertEqual("accept" if r.get("ok") else "refuse", c["expect"], (c["id"], r))

    def test_a_single_date_concept_refuses_a_range_the_interval_concept_takes_it(self):
        r = self.write(self.birth("1960 to 1965", "1960/1965", "year"))
        self.assertFalse(r.get("ok"), "a birth is one date")
        self.ok([{"op": "add", "path": "events/e-sv",
                  "value": {"type": "service", "participants": [{"person": NORA, "role": "member"}]}},
                 self.assertion("a-sv", "event", "e-sv", "event.service.period",
                                date("1960 to 1965", "1960/1965", "year"))])

    def test_the_value_type_comes_from_the_catalog_not_the_concept_name(self):
        # animal.joined_household is a date concept whose name says nothing
        # about dates — only the catalog does.
        self.ok([{"op": "add", "path": "animals/an-1", "value": {"name": "Biscuit", "species": "dog"}}])
        r = self.write([self.assertion("a-j", "animal", "an-1", "animal.joined_household",
                                       {"text": "1987", "value": "1989", "precision": "year"})])
        self.assertFalse(r.get("ok"), r)
        self.ok([self.assertion("a-j2", "animal", "an-1", "animal.joined_household",
                                date("spring 1987", None, "unknown"))])

    def test_nothing_is_written_when_one_date_in_the_set_is_refused(self):
        r = self.write(self.birth("1989-02-30", None, "unknown"))
        self.assertFalse(r.get("ok"))
        self.assertEqual(self.count("lr_events"), 0)
        self.assertEqual(self.count("lr_assertions"), 0)

    def test_a_relationship_period_endpoint_is_one_date(self):
        self.ok([{"op": "add", "path": "people/p-s", "value": {}}])
        rel = lambda start: {"op": "add", "path": "relationships/r1", "value": {  # noqa: E731
            "subjectPersonId": "p-s", "otherPersonId": NORA, "kind": "spouse_of",
            "period": {"start": start}}}
        for bad in (date("1987", "1989", "year"), date("about 1989", "1989~", "approximate"),
                    date("1960 to 1965", "1960/1965", "unknown"), "1961"):
            self.assertFalse(self.write([rel(bad)]).get("ok"), bad)
        self.ok([rel(date("about 1989", "1989~", "year"))])

    def test_a_name_period_is_held_to_the_contract(self):
        r = self.write([self.name(NORA, "n1", "Nora Whitfield",
                                  period={"start": date("1987", "1989", "year")})])
        self.assertFalse(r.get("ok"))
        self.ok([self.name(NORA, "n1", "Nora Whitfield", period={"start": date("1960", "1960", "year")})])


class LegacyDatesAreCarriedNotRewritten(_Birth):
    def _legacy_relationship(self, period):
        self.ok([{"op": "add", "path": "people/p-s", "value": {}},
                 {"op": "add", "path": "relationships/r1", "value": {
                     "subjectPersonId": "p-s", "otherPersonId": NORA, "kind": "spouse_of"}}])
        self._put("UPDATE lr_relationships SET period_json = ? WHERE id = 'r1'",
                  json.dumps(period, sort_keys=True))
        return next(r for r in self.rec()["relationships"] if r["id"] == "r1")

    def test_every_legacy_case_carries_through_an_unrelated_relationship_edit(self):
        for c in CORPUS["legacy_compatibility"]["cases"]:
            with self.subTest(c["id"]):
                self.tearDown()
                self.setUp()
                period = {"start": c["stored"]}
                before = self._legacy_relationship(period)
                self.assertEqual(before["period"], period, "readable as stored")
                after = {k: before[k] for k in ("subjectPersonId", "otherPersonId", "kind", "period")}
                after["narratorLabel"] = "my first husband"      # the unrelated edit
                self.ok([{"op": "set", "path": "relationships/r1", "value": after,
                          "expectedPrevious": {k: v for k, v in before.items() if k != "id"}}])
                got = next(r for r in self.rec()["relationships"] if r["id"] == "r1")
                self.assertEqual(got["period"], period, "carried byte-for-byte, never rewritten")

    def test_changing_the_legacy_endpoint_is_held_to_the_contract(self):
        legacy = {"start": {"text": "about 1989", "value": None, "precision": "unknown"}}
        before = self._legacy_relationship(legacy)
        prev = {k: v for k, v in before.items() if k != "id"}
        base = {k: before[k] for k in ("subjectPersonId", "otherPersonId", "kind")}
        # changing the OTHER end validates only that end — the legacy start rides along
        ok_end = dict(base, period={"start": legacy["start"], "end": date("1995", "1995", "year")})
        self.ok([{"op": "set", "path": "relationships/r1", "value": ok_end, "expectedPrevious": prev}])
        # changing the legacy start itself must meet the contract
        bad = dict(base, period={"start": {"text": "about 1990", "value": None, "precision": "unknown"},
                                 "end": date("1995", "1995", "year")})
        now = next(r for r in self.rec()["relationships"] if r["id"] == "r1")
        r = self.write([{"op": "set", "path": "relationships/r1", "value": bad,
                         "expectedPrevious": {k: v for k, v in now.items() if k != "id"}}])
        self.assertIn("period start", json.dumps(r), "refused for the date, not for staleness")
        self.assertFalse(r.get("ok"), r)

    # ── the second structural owner: a NAME's period ──
    def _legacy_name(self, period):
        self.ok([self.name(NORA, "n1", "Nora Whitfield", kind="former")])
        self._put("UPDATE lr_names SET period_json = ? WHERE id = 'n1'",
                  json.dumps(period, sort_keys=True))
        me = next(p for p in self.rec()["people"] if p["id"] == NORA)
        return next(n for n in me["names"] if n["id"] == "n1")

    def test_every_legacy_case_carries_through_an_unrelated_name_edit(self):
        for c in CORPUS["legacy_compatibility"]["cases"]:
            with self.subTest(c["id"]):
                self.tearDown()
                self.setUp()
                period = {"end": c["stored"]}
                before = self._legacy_name(period)
                self.assertEqual(before["period"], period, "readable as stored")
                prev = {k: v for k, v in before.items() if k != "id"}
                after = dict(prev, pronunciation="NOR-uh")          # the unrelated edit
                self.ok([{"op": "set", "path": f"people/{NORA}/names/n1", "value": after,
                          "expectedPrevious": prev}])
                me = next(p for p in self.rec()["people"] if p["id"] == NORA)
                got = next(n for n in me["names"] if n["id"] == "n1")
                self.assertEqual(got["period"], period, "carried byte-for-byte, never rewritten")
                self.assertEqual(got["pronunciation"], "NOR-uh", "and the unrelated edit landed")

    def test_a_name_period_mixed_legacy_end_and_changed_start(self):
        legacy_end = {"text": "around 1962", "value": "1962~", "precision": "approximate"}
        before = self._legacy_name({"end": legacy_end})
        prev = {k: v for k, v in before.items() if k != "id"}
        # adding a NEW start is held to the contract; the legacy end rides along
        bad = dict(prev, period={"start": date("1987", "1989", "year"), "end": legacy_end})
        r = self.write([{"op": "set", "path": f"people/{NORA}/names/n1", "value": bad,
                         "expectedPrevious": prev}])
        self.assertFalse(r.get("ok"), r)
        self.assertIn("period start", json.dumps(r))
        good = dict(prev, period={"start": date("1955", "1955", "year"), "end": legacy_end})
        self.ok([{"op": "set", "path": f"people/{NORA}/names/n1", "value": good,
                  "expectedPrevious": prev}])
        me = next(p for p in self.rec()["people"] if p["id"] == NORA)
        got = next(n for n in me["names"] if n["id"] == "n1")
        self.assertEqual(got["period"]["end"], legacy_end, "the legacy end is not rewritten")
        # and changing the legacy end itself must now meet the contract
        prev2 = {k: v for k, v in got.items() if k != "id"}
        r = self.write([{"op": "set", "path": f"people/{NORA}/names/n1",
                         "value": dict(prev2, period={"start": got["period"]["start"],
                                                      "end": {"text": "around 1963", "value": "1963~",
                                                              "precision": "approximate"}}),
                         "expectedPrevious": prev2}])
        self.assertFalse(r.get("ok"), r)
        self.assertIn("period end", json.dumps(r))

    def test_a_legacy_dob_still_reads_and_ages_as_approximate(self):
        self.ok(self.birth("1945", "1945", "year"))
        self._put("UPDATE lr_assertions SET value_json = ? WHERE id = 'a-dob'",
                  json.dumps({"text": "around 1945", "value": "1945~", "precision": "approximate"}))
        rec = self.rec()
        self.assertEqual(rec["events"][0]["date"]["precision"], "approximate")
        age = R.age_at(rec["events"][0]["date"], date("1965", "1965", "year"))
        self.assertFalse(age["exact"])
        self.assertTrue(age["render"].startswith("about"))


class AgesReadTheValue(unittest.TestCase):
    """rules.age_at is the one consumer that computes from a date."""

    def test_new_form_approximation_propagates(self):
        a = R.age_at(date("about 1945", "1945~", "year"), date("1965", "1965", "year"))
        self.assertFalse(a["exact"])
        self.assertTrue(a["render"].startswith("about"))
        u = R.age_at(date("1939-08-30?", "1939-08-30?", "day"), date("1971-09-01", "1971-09-01", "day"))
        self.assertFalse(u["exact"], "an uncertain day is not an exact age")

    def test_no_age_from_a_decade_or_a_range(self):
        self.assertIsNone(R.age_at(date("the 1920s", "192X", "year"), date("1965", "1965", "year")))
        self.assertIsNone(R.age_at(date("1939", "1939", "year"),
                                   date("1960 to 1965", "1960/1965", "unknown")))

    def test_an_exact_pair_is_still_exact(self):
        a = R.age_at(date("1939-08-30", "1939-08-30", "day"), date("1971-08-29", "1971-08-29", "day"))
        self.assertEqual((a["exact"], a["render"]), (True, "31"))


class IdentityParsesByTheContract(_Db):
    def test_a_bad_dob_is_not_recorded_and_nothing_else_is_lost(self):
        from api.services.life_record.identity import establish_narrator
        r = establish_narrator(NORA, full_name="Nora Ann Whitfield", preferred_name="Nan",
                               pronouns="she/her", birth_date="1939-02-30", birth_place="Minot")
        # the Life Record write SUCCEEDED; one field was not recorded
        self.assertTrue(r["ok"], r)
        self.assertNotIn("refused", r)
        self.assertEqual(r["notRecorded"][0]["field"], "birth_date")
        self.assertIn("not a real date", r["notRecorded"][0]["reason"])
        rec = self.rec()
        me = rec["people"][0]
        self.assertEqual({n["fullText"] for n in me["names"]}, {"Nora Ann Whitfield", "Nan"})
        self.assertEqual([a["value"] for a in me["person.pronouns"]], ["she/her"])
        self.assertEqual(rec["places"][0]["label"], "Minot", "the place still lands")
        self.assertEqual(rec["events"][0]["place"], rec["places"][0]["id"])
        self.assertNotIn("date", rec["events"][0], "a refused date is not stored as words")
        self.assertEqual(self.count("lr_assertions"), 1, "pronouns only — no date assertion at all")

    def test_a_refused_date_alone_invents_no_birth_event(self):
        from api.services.life_record.identity import establish_narrator
        r = establish_narrator(NORA, full_name="Nora Whitfield", birth_date="1939-13-01")
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.rec()["events"], [])

    def test_a_good_dob_reports_nothing_not_recorded(self):
        from api.services.life_record.identity import establish_narrator
        r = establish_narrator(NORA, full_name="Nora Whitfield", birth_date="about 1939")
        self.assertTrue(r["ok"], r)
        self.assertNotIn("notRecorded", r)


try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routers import people as _people_router
    _HAVE_FASTAPI = True
except Exception:  # pragma: no cover
    _HAVE_FASTAPI = False


@unittest.skipUnless(_HAVE_FASTAPI, "fastapi is not importable under this interpreter")
class CreateRouteSaysWhatWasNotRecorded(_Db):
    """At the route: 'the DOB was not recorded' (ok, notRecorded) is a
    different answer from 'the Life Record write failed' (not ok, refused)."""

    def _post(self, **kw):
        app = FastAPI()
        app.include_router(_people_router.router)
        body = dict({"display_name": "Probe Fictional", "role": "", "narrator_type": "live",
                     "testing_only": True, "pronouns": "she_her"}, **kw)
        r = TestClient(app).post("/api/people", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_bad_dob_valid_place_is_ok_with_not_recorded(self):
        body = self._post(date_of_birth="1939-02-30", place_of_birth="Minot")
        lr = body["life_record"]
        self.assertTrue(lr["ok"], lr)
        self.assertNotIn("refused", lr)
        self.assertEqual([x["field"] for x in lr["notRecorded"]], ["birth_date"])
        rec = W.read_record(body["person_id"])
        self.assertEqual([n["fullText"] for n in rec["people"][0]["names"]], ["Probe Fictional"])
        self.assertEqual([a["value"] for a in rec["people"][0]["person.pronouns"]], ["she/her"])
        self.assertEqual(rec["places"][0]["label"], "Minot")
        # …and NOT recorded in the legacy people row either (review 2026-09-24:
        # _sanitise_dob checks shape only and used to keep 1939-02-30 there)
        self.assertEqual(self._legacy_dob(body["person_id"]), "")

    def _legacy_dob(self, pid):
        con = sqlite3.connect(str(_db.DB_PATH))
        try:
            return con.execute("SELECT date_of_birth FROM people WHERE id = ?", (pid,)).fetchone()[0]
        finally:
            con.close()

    def test_a_range_is_not_a_birth_date_in_the_legacy_row(self):
        body = self._post(date_of_birth="1939 to 1940")
        self.assertEqual([x["field"] for x in body["life_record"]["notRecorded"]], ["birth_date"])
        self.assertEqual(self._legacy_dob(body["person_id"]), "")

    def test_a_real_birth_date_still_reaches_the_legacy_row(self):
        body = self._post(date_of_birth="1939-08-30")
        self.assertNotIn("notRecorded", body["life_record"])
        self.assertEqual(self._legacy_dob(body["person_id"]), "1939-08-30")

    def test_the_intake_route_keeps_a_bad_dob_out_of_the_row_and_the_profile(self):
        app = FastAPI()
        app.include_router(_people_router.router)
        r = TestClient(app).post("/api/people/intake", json={
            "full_legal_name": "Probe Fictional", "preferred_name": "Probe",
            "date_of_birth": "1939-02-30", "place_of_birth": "Minot", "pronouns": "she_her",
            "current_residence": "Duluth", "testing_only": True})
        self.assertEqual(r.status_code, 200, r.text)
        pid = r.json()["person_id"]
        self.assertEqual(self._legacy_dob(pid), "")
        prof = _db.get_profile(pid) or {}
        blob = prof.get("profile_json", prof) if isinstance(prof, dict) else {}
        self.assertEqual((blob.get("personal") or {}).get("dateOfBirth"), "")

    def test_a_failed_life_record_write_is_not_ok_and_says_refused(self):
        from unittest import mock
        with mock.patch.object(W, "apply_changes",
                               return_value={"ok": False, "refused": [{"path": "", "reason": "probe"}]}):
            body = self._post(date_of_birth="1939-02-30", place_of_birth="Minot")
        lr = body["life_record"]
        self.assertFalse(lr["ok"], lr)
        self.assertEqual(lr["refused"], [{"path": "", "reason": "probe"}])
        self.assertNotIn("notRecorded", lr, "a failed write never also claims a partial success")


if __name__ == "__main__":
    unittest.main()
