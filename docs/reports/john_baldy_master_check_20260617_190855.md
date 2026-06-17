# John Baldy Master Check — 20260617_190855

Bundled run of (1) fast unit tests, (2) Test Lab availability probe, and (3) seven-era backend walk against the live stack at `http://localhost:8000`.

## Topline

- Unit tests: **FAIL**
- Test Lab: **DEGRADED — Test Lab runs will likely 500**
- Seven-era walk: **PASS**

## Unit tests

- ✗ `tests.test_lori_communication_control` rc=1 (0.3s)
      ----------------------------------------------------------------------
      Ran 24 tests in 0.030s
      
      FAILED (failures=1)
- ✓ `tests.test_compose_memory_echo_spanish` rc=0 (0.3s)
      ----------------------------------------------------------------------
      Ran 32 tests in 0.003s
      
      OK
- ✓ `tests.test_bio_questionnaire_writer` rc=0 (0.3s)
      ----------------------------------------------------------------------
      Ran 18 tests in 0.146s
      
      OK

## Test Lab availability

- `scripts/run_test_lab.sh` present: `False`
- GET `/api/test-lab/status` → HTTP `200`
- GET `/api/test-lab/system` → HTTP `200`
- GET `/api/test-lab/results` → HTTP `200`
- Verdict: **DEGRADED — Test Lab runs will likely 500**

## Seven-era walk

- returncode: `0`  duration: `78.8s`

## Open bugs in scope this run

From the 2026-06-17 Chrome-MCP run + api.log evidence + operator log:

- **BUG-LORI-SPANISH-MISFIRE-ENGLISH-SESSION-01** — confirmed in api.log L235170: `[chat_ws][response-guards] fired=language_drift ... before='Durante tus años más tempranos en West St. Paul...' after='Let me say that in English.'`
- **BUG-LIFEMAP-CONTEXT-TRUNCATION-01** — VRAM-GUARD trimmed input from 12138 → 8192 tokens on a Life-Map-era turn.
- **BUG-LIFEMAP-COMM-CONTROL-TRIM-01** — comm_control fired `reflection=echo_not_grounded` warnings; multiple eras in the Chrome run came back as single-question stubs.
- **BUG-FE-FACTS-ADD-PAYLOAD-SHAPE-422-01** — `POST /api/facts/add` continues to return 422 every turn; FE swallows the failure.
- **BUG-CHATWS-CONV-FK-01** — `[chat_ws][softened] turn_count increment failed` FOREIGN KEY constraint fires on switch_* conv_ids.

## Operator log items needing follow-up

From OPERATOR-LOG-2026-06-17-18-54-54.md (RED block):

- session_style picker radio count is 5 but validator expects 4 (clear_direct was added; validator missed the update).
- Media launcher cards count is 4 but validator expects 3.
- state.session.sessionStyle returns `oral_history` but a validator gate expected `undefined` — likely a stale guard.

AMBER block flagged Memory River tab as missing — that's the retired Kawa metaphor per CLAUDE.md design principle 1, so the operator-log gate itself is stale and should be removed, not the feature restored.

## Recommended next action

Seven-era walk passed end-to-end. Open the per-era report at `docs/reports/john_baldy_seven_era_*.md` for the matrix score per era. Then triage the open bugs above in priority order: facts/add 422 is the silent-data-loss fix and should land first.
