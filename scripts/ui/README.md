# scripts/ui/ — UI verification harnesses

Playwright-based browser harnesses that exercise the Hornelore UI end-to-end.
These are **proof-side** harnesses — they don't replace product fixes, they
prove the fixes work in the running stack.

**There are two toolchains in this folder and they install separately.** The
`*.py` harnesses use Python Playwright; the `*.js` harnesses use Node
Playwright. Having one installed does not give you the other, and neither
arrives with `git pull` — the browser binaries live outside the repo in
`~/.cache/ms-playwright`, and the Node packages live under a gitignored
`node_modules/`.

## Setup (one-time)

### Python harnesses (`*.py`)

```bash
python -m pip install playwright
python -m playwright install chromium
```

The harness runs **headed Chromium by default** so you can watch what it does
and intervene if anything looks off. Add `--headless` for unattended runs.

The stack must already be warm before invoking — the harness does NOT start
or stop the API / UI / TTS processes. Cold-boot takes ~4 minutes; verify
`http://localhost:8082/ui/hornelore1.0.html` loads in your browser first.

### Node harnesses (`*.js`)

```bash
cd /mnt/c/Users/chris/hornelore
npm install
```

Driven by the repo-root `package.json`. Playwright is pinned there to an
**exact** version rather than a caret range, and that pin is load-bearing.
Browser binaries live in `~/.cache/ms-playwright` in folders named for a
revision tied to one exact Playwright release — 1.58.2 wants
`chromium-1208`, 1.62.0 wants `chromium-1234` — so a caret that drifts to a
newer release downloads a second full browser set (~500 MB) and strands the
one already on disk. `package-lock.json` is committed for the same reason.
**If `npm install` starts downloading browsers, stop and check the version
before letting it finish**; a correct install here fetches only JavaScript.

Unlike the Python harnesses these are **headless**, need **no warm stack**
and take **no arguments** — each starts its own static file server on an
ephemeral port and drives the real page off disk. Exit `0` is PASS, `1` is
FAIL, `2` means Playwright is not installed.

Two environment overrides both harnesses honour:

| Variable | Effect |
|---|---|
| `NODE_PATH` | Where `require("playwright")` resolves from. Lets you install once outside the repo instead of into `node_modules/`. |
| `PLAYWRIGHT_CHROMIUM_PATH` | Passed through as Playwright's `executablePath`, for a Chromium in a non-standard location. |

On WSL, writing `node_modules/` under `/mnt/c` crosses the 9p boundary and
is slow. To keep the repo tree clean and the install fast, put it in your
home directory instead and point `NODE_PATH` at it:

```bash
mkdir -p ~/pw-1582 && cd ~/pw-1582 && npm init -y >/dev/null
npm install playwright@1.58.2
```

```bash
cd /mnt/c/Users/chris/hornelore
NODE_PATH=$HOME/pw-1582/node_modules node scripts/ui/run_travel_doc_mount_liveness.js
```

---

## run_travel_doc_mount_liveness.js

WO-TRAVEL-DOC-UNIFY-01 Phase 1.1. Proves the **module**: that a Travel Doc
mount which has been destroyed cannot be repainted by a callback already in
flight, and that `destroy()` gives back everything the mount took.

```bash
node scripts/ui/run_travel_doc_mount_liveness.js
```

It loads `ui/travel-doc-lab.html` and replaces `window.fetch` with one that
parks every request until the test releases it. That is the whole trick:
with fetch parked, `boot()` paints nothing, because `renderAll()` lives
inside the `.then()`. So "host is empty" is the identical starting state for
all four scenarios, and the only difference between them is whether the
mount was destroyed before the parked request came back.

| Scenario | Destroyed first? | Host must |
|---|---|---|
| `control_live` | no, released | repaint |
| `destroyed_then` | yes, resolves 200 | stay empty |
| `destroyed_notok` | yes, resolves 500 | stay empty |
| `destroyed_reject` | yes, rejects | stay empty |

`control_live` is the load-bearing row. Without it, three "nothing happened"
results prove nothing — a harness that never delivers a callback also
produces three empty hosts.

The two census checks count BroadcastChannel subscriptions and
document-level keydown registrations at bind/unbind rather than observing
effects, because the keydown handler early-returns unless a lightbox is
open: an "assert no repaint on keypress" test would pass vacuously with the
listener still bound. Counting cannot go vacuous.

**14 checks.** Two negative controls are recorded in the file header and
should be re-run by hand if the guards ever change. A green suite that
cannot go red is decoration.

## run_travel_doc_shell_mount_liveness.js

The same question one level up: proves the **shell**. The module harness
mounts into a bare `<div>`, which is the right isolation for "can a dead
mount repaint" and the wrong one for "can the shell start a mount while an
older one is still live".

```bash
node scripts/ui/run_travel_doc_shell_mount_liveness.js
```

It loads the real `ui/hornelore1.0.html` and drives `lvShellShowTab()` the
way an operator would — first open, narrator switch, tab exit, re-entry.
Every one of those is a path where the shell could mount over a live mount,
and a live mount owns a BroadcastChannel, a document-level keydown listener
and a Lori socket. So a double mount is not cosmetic: it is doubled
cross-tab refresh traffic, two handlers fighting over Escape, and a spare
`/api/chat/ws` connection bound to a narrator nobody is looking at.

Phase 4 retired the fallback surface, so the `single_surface` probe now
asserts that absence directly — one host in the panel, no legacy host, no
toggle buttons, no surface setter, no retired asset tag in the live
document. The double-mount risk itself did not go away with the toggle,
which is why every census row survived Phase 4 unchanged.

**23 checks.**

The Python-side counterparts — `tests/test_travel_doc_lab.py::MountLivenessTest`
and `tests/test_travel_doc_shell_mount.py` — pin the *shape* of these guards
by reading the source. Static assertions cannot watch a stale callback land
on a dead host, and they cannot take a census. That is the entire reason
these two scripts exist, and it is why a green Python suite is not a
substitute for running them.

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
