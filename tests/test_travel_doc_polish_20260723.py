"""P1/P2 polish from the 2026-07-23 live verification:

1. Trip create surfaces days_created so the UI can tell the operator the day
   cards exist (the Bismarck days looked missing because the response never
   said they were made, and the Trips tab does not render days).

2. Public-lookup drafts read cleanly to the narrator:
   - the page-title site suffix ("- Wikipedia") is stripped at the source;
   - Lori speaks only a short lead of the context, not a 500-char article.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

class LookupTitleCleanTest(unittest.TestCase):
    def setUp(self):
        from api.services.travel_doc_public_lookup import _clean_title
        self.clean = _clean_title

    def test_strips_known_site_suffixes(self):
        self.assertEqual(self.clean("Augustiner-Bräu - Wikipedia"),
                         "Augustiner-Bräu")
        self.assertEqual(self.clean("Prague Castle | Wikivoyage"),
                         "Prague Castle")
        self.assertEqual(self.clean("Foo – Britannica"), "Foo")

    def test_keeps_real_place_suffix(self):
        # "- Munich" is a real place, NOT a site name — must not be stripped.
        self.assertEqual(
            self.clean("The German Hunting and Fishing Museum - Munich"),
            "The German Hunting and Fishing Museum - Munich")

    def test_plain_title_unchanged(self):
        self.assertEqual(self.clean("Augustiner-Bräu"), "Augustiner-Bräu")


class SpokenContextTrimTest(unittest.TestCase):
    def setUp(self):
        from api.services.travel_doc_lori_modal import _spoken_context_trim
        self.trim = _spoken_context_trim

    def test_short_context_kept_whole(self):
        s = "The German Hunting and Fishing Museum in Munich."
        self.assertEqual(self.trim(s), s)

    def test_long_context_trimmed_to_first_sentence(self):
        long = ("Augustiner-Bräu — The Augustinian Hermits arrived in Munich "
                "in 1294, called there by Bishop Emicho of Freising. They came "
                "from Regensburg and settled on open meadow land outside the "
                "old town walls, where they built a monastery and a brewery "
                "that still bears the name today, centuries later.")
        out = self.trim(long)
        self.assertLess(len(out), len(long))
        self.assertTrue(out.endswith((".", "!", "?", "…")))
        self.assertIn("Augustiner", out)

    def test_no_sentence_boundary_word_caps(self):
        run_on = "word " * 80
        out = self.trim(run_on.strip())
        self.assertLessEqual(len(out), 200)
        self.assertTrue(out.endswith("…"))


# Runs in its OWN interpreter. Importing api.routers.trips needs fastapi +
# pydantic stubs; keeping them here (not at module scope) means they can never
# leak into the parent test process — the sys.modules-pollution class this
# suite has already been bitten by.
_HELPER_CONTRACT_SUBPROCESS = r'''
import sys, types
SERVER_CODE = sys.argv[1]
sys.path.insert(0, SERVER_CODE)

fa = types.ModuleType("fastapi")
class _R:
    def __getattr__(self, _):
        return lambda *a, **k: (lambda f: f)
fa.APIRouter = lambda *a, **k: _R()
fa.HTTPException = type("HTTPException", (Exception,), {})
fa.Query = lambda *a, **k: None
fa.File = lambda *a, **k: None
fa.Form = lambda *a, **k: None
fa.UploadFile = object
sys.modules["fastapi"] = fa
pd = types.ModuleType("pydantic")
pd.BaseModel = object
pd.Field = lambda *a, **k: None
pd.field_validator = lambda *a, **k: (lambda f: f)
pd.validator = lambda *a, **k: (lambda f: f)
pd.ConfigDict = dict
sys.modules["pydantic"] = pd

from api.routers import trips

results = []
def check(name, ok):
    results.append((name, bool(ok)))

# no dates -> (None, None)
r = trips._auto_generate_days_for_new_trip("t", None, None)
check("no_dates", isinstance(r, tuple) and r == (None, None))

# success -> (created_count, None), using result["created"]
trips.trip_repository.trip_days_generate = lambda _t: {"created": 3, "total": 3}
r = trips._auto_generate_days_for_new_trip("t", "2026-08-01", "2026-08-03")
check("success_created_count", isinstance(r, tuple) and r == (3, None))

# bad-date ValueError -> (None, warning str)
def _ve(_t):
    raise ValueError("end_date is before start_date")
trips.trip_repository.trip_days_generate = _ve
r = trips._auto_generate_days_for_new_trip("t", "2026-08-03", "2026-08-01")
check("valueerror_warning", isinstance(r, tuple) and r[0] is None
      and isinstance(r[1], str) and "could not be generated" in r[1])

# unexpected exception (DB lock) -> (None, warning str), NOT a bare string
class _Lock(Exception):
    sqlite_errorname = "SQLITE_BUSY"
    sqlite_errorcode = 5
def _boom(_t):
    raise _Lock("database is locked")
trips.trip_repository.trip_days_generate = _boom
r = trips._auto_generate_days_for_new_trip("t", "2026-08-01", "2026-08-03")
check("broad_exc_tuple", isinstance(r, tuple) and len(r) == 2
      and r[0] is None and isinstance(r[1], str))

for name, ok in results:
    print(("ok   " if ok else "FAIL ") + name)
sys.exit(0 if all(ok for _, ok in results) else 1)
'''


class AutoDaysReturnContractTest(unittest.TestCase):
    """Every return path of _auto_generate_days_for_new_trip must be a two-item
    tuple. create_trip does `days_created, days_warning = helper(...)`, so a
    single-value return (the old warning-string on the broad except) raises on
    unpack and turns a survivable day-gen failure (DB lock, missing migration)
    into a 500 on the whole trip create. Covers no-dates, success, bad-date
    warning, and unexpected-exception warning."""

    def test_all_return_paths_are_two_tuples(self):
        import subprocess
        out = subprocess.run(
            [sys.executable, "-c", _HELPER_CONTRACT_SUBPROCESS,
             str(_SERVER_CODE)],
            capture_output=True, text=True, timeout=60)
        checks = [l for l in out.stdout.splitlines()
                  if l.startswith(("ok ", "FAIL"))]
        self.assertTrue(
            checks, "subprocess produced no checks:\n"
            + out.stdout + "\n" + out.stderr)
        self.assertEqual(
            out.returncode, 0,
            "a return path is not a proper 2-tuple:\n"
            + "\n".join(l for l in checks if l.startswith("FAIL")))


if __name__ == "__main__":
    unittest.main()
