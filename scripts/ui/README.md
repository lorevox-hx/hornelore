# scripts/ui/ — UI verification harnesses

Playwright-based browser harnesses that exercise the Hornelore UI end-to-end.
These are **proof-side** harnesses — they don't replace product fixes, they
prove the fixes work in the running stack.

## Setup (one-time)

```bash
python -m pip install playwright
python -m playwright install chromium
```

The harness runs **headed Chromium by default** so you can watch what it does
and intervene if anything looks off. Add `--headless` for unattended runs.

The stack must already be warm before invoking — the harness does NOT start
or stop the API / UI / TTS processes. Cold-boot takes ~4 minutes; verify
`http://localhost:8082/ui/hornelore1.0.html` loads in your browser first.

---

## run_parent_session_readiness_harness.py

Automates `docs/test-packs/PARENT-SESSION-READINESS-V1.md` (10 tests). Any
RED result blocks live sessions with Kent or Janice.

**One-command invocation:**

```bash
cd /mnt/c/Users/chris/hornelore
python scripts/ui/run_parent_session_readiness_harness.py \
  --base-url http://localhost:8082/ui/hornelore1.0.html \
  --api http://localhost:8000 \
  --output docs/reports/parent_session_readiness_v1.json
```

**What it does:**

1. Opens Chrome at the base URL, hard-reloads, captures console + page errors.
2. Clicks Operator → Life Story → Ready for Session as preconditions.
3. Runs the 10 tests in cold-priority order: TEST-07 / TEST-08 / TEST-09
   first (Life Map + Today, fastest signal), then validators TEST-01–04,
   then reset + cross-narrator TEST-05/06, then memoir export TEST-10.
4. Each test creates its own disposable TEST narrator via the trainer-seed
   buttons inside the narrator switcher (the actual current UI path —
   there is no "+ Add Test Narrator" button).
5. Writes a timestamped JSON report + a console summary + a screenshots
   folder + a downloads folder under `docs/reports/`.

**Outputs (per run):**

```
docs/reports/parent_session_readiness_v1_<YYYYMMDD_HHMMSS>.json
docs/reports/parent_session_readiness_v1_<YYYYMMDD_HHMMSS>.console.txt
docs/reports/parent_session_readiness_v1_<YYYYMMDD_HHMMSS>.screenshots/
docs/reports/parent_session_readiness_v1_<YYYYMMDD_HHMMSS>.downloads/
```

The console.txt ends with a per-test PASS / AMBER / FAIL roll-up plus the
overall GREEN / AMBER / RED verdict and any hard-stop labels that fired.

**Acceptance gate (per WO):**

| Roll-up | Meaning |
|---|---|
| GREEN  | All 10 PASS. Parent-session ready. |
| AMBER  | All 10 PASS or AMBER, no FAIL. Eligible for parent session with operator caveat. |
| RED    | Any FAIL or hard-stop fired. Parent sessions BLOCKED until fixed. |

**Hard-stop conditions (RED) — mirror the manual pack:**

- Bad birthplace value writes into `personal.placeOfBirth` as truth
- Bad birthOrder value writes into `personal.birthOrder` as truth
- Rejected text appears in Peek at Memoir as a confirmed fact
- Life Map missing on cold start
- Life Map era buttons go visually-active-but-behaviorally-dead
- Lori claims she cannot tell the date
- Operator-only controls visible in narrator flow
- Cross-narrator data leak
- DB lock event during a normal turn

**Safety / dignity constraints (enforced by code):**

- Never operates on Kent / Janice / Christopher or any narrator without
  the trainer-seed entry path.
- Never deletes FAMILY narrators.
- Never resets identity on a narrator that wasn't created by this run.
- Disposable TEST narrators only — running the harness twice does NOT
  require manual cleanup, the harness creates fresh narrators each run.

---

## CLI flags

```
--base-url URL          UI URL (required, e.g. http://localhost:8082/ui/hornelore1.0.html)
--api URL               API URL (required, e.g. http://localhost:8000)
--output PATH           Report stem path (required, timestamp added automatically)
--test-pack PATH        Manual test pack reference (default docs/test-packs/PARENT-SESSION-READINESS-V1.md)
--only IDS              Comma-separated test IDs to run (e.g. TEST-07,TEST-09)
--stop-on-red           Abort on first hard-stop
--headless              Run Chromium headless (default: headed)
--slow-mo-ms N          Insert N ms delay between Playwright actions (debug aid)
```

**Examples:**

Run only the Life Map + Today cold-priority pack:

```bash
python scripts/ui/run_parent_session_readiness_harness.py \
  --base-url http://localhost:8082/ui/hornelore1.0.html \
  --api http://localhost:8000 \
  --output docs/reports/parent_session_readiness_v1_lifemap.json \
  --only TEST-07,TEST-08,TEST-09
```

Run validator pack with stop-on-red:

```bash
python scripts/ui/run_parent_session_readiness_harness.py \
  --base-url http://localhost:8082/ui/hornelore1.0.html \
  --api http://localhost:8000 \
  --output docs/reports/parent_session_readiness_v1_validator.json \
  --only TEST-01,TEST-02,TEST-03,TEST-04 \
  --stop-on-red
```

---

## Architecture

The harness is a single self-contained Python file:

- **`SEL` dict** — visible-label-first selectors for every UI surface the
  harness touches. Centralized so a UI rename only requires editing this
  one block.
- **`ConsoleCollector`** — captures `console.{log,warn,error}` + `pageerror`
  + `requestfailed` and exposes `.matches(pattern, since_ts)` so tests can
  confirm specific log markers fired (e.g. `[bb-drift] qf_walk validation
  REJECTED personal.placeOfBirth`).
- **`DbLockCounter`** — reads `.runtime/logs/api.log` (or
  `/mnt/c/hornelore_data/logs/api.log`) and counts `database is locked` /
  `OperationalError` / `sqlite.*locked` matches. Each test reads `.delta()`
  to detect new lock events introduced by that test's actions.
- **`UI` class** — wraps Playwright with the helpers from the WO:
  `boot / ensure_life_story_posture / ready_for_session / add_test_narrator
  / session_start / wrap_session / send_chat / wait_for_lori_turn /
  open_bio_builder / read_bb_field / open_peek_memoir / read_peek_memoir_text
  / download_memoir_txt / click_life_map_era / assert_life_map_visible /
  assert_no_memory_river / click_reset_identity`.
- **`Harness` class** — one method per test, plus `run_all()` which invokes
  them in cold-priority order, captures per-test results, and computes the
  overall verdict.

Test results are dataclasses → JSON; the console summary is generated from
the same dataclasses so JSON and console.txt cannot diverge.

---

## Extending the pack

When a new bug surfaces that should be covered:

1. Add a new `test_NN_*` method on `Harness`.
2. Add a `("TEST-NN", self.test_NN_*)` entry to `Harness.run_all`'s `steps`.
3. Add a row to the `name_map` in `write_report`.
4. If the test introduces a new console marker, add a new `HARD_STOP_LABELS`
   entry if the marker should hard-stop.

Keep tests narrow, observable, and tied to a specific bug or design
principle the manual pack already names.

---

## When tests fail

- **PASS** — every Expected line was observed.
- **AMBER** — primary expectation met, secondary detail off (e.g. Lori's
  reply lacked the explicit weekday but contained the date). Document in
  `notes` so the operator knows what to watch for.
- **FAIL** — any Expected line not observed, or a hard-stop fired.
- **SKIP** — filtered out via `--only`.

A FAIL with `hard_stop=true` means parent sessions are blocked. A FAIL
without `hard_stop` is a per-test failure but the overall verdict can
still be AMBER if no hard-stop fired.

Screenshots and downloads land under the timestamped folder for any
failing test. Review `*.console.txt` first — it's the human-readable
summary; the JSON has the full per-test observations dict.
