# WO-EX-EVAL-WRAPPER-01 — Spec

**Status:** ACTIVE (small, high-leverage; ships before next SPANTAG eval)
**Type:** Operational tooling — single-command extractor eval workflow
**Date:** 2026-04-27
**Lab/gold posture:** Hornelore-side first. The pattern (one-command eval with verification gates) is the kind of operator-experience improvement Lorevox should inherit.
**Blocked by:** nothing
**Blocks:** nothing critical, but every future SPANTAG / BINDING-01 eval cycle benefits

---

## Why this WO exists

Today's SPANTAG eval cycle takes six manual steps with three fragile points:

1. Edit `.env` to set `HORNELORE_SPANTAG=1`
2. Stop the stack (double-click `Stop Hornelore.bat`)
3. Start the stack (double-click `Start Hornelore.bat`)
4. Wait ~4 minutes for cold boot + LLM warmup
5. Manually verify SPANTAG is firing (grep api.log for `[extract][spantag] flag ON`)
6. Run the eval (`./scripts/archive/run_question_bank_extraction_eval.py ...`)

**Each step has a failure mode that costs 30+ minutes to discover:**

- `.env` flip silently misses if the file's value differs by whitespace or already changed
- Stack restart can silently fail (port occupied, model OOM, dependency missing)
- Cold boot timing is fuzzy; running eval too early times out the first case
- Flag verification grep can return STALE log lines from days ago — false confidence
- Eval timeout per case is 300s but cold-stack first case can exceed even that

The full failure mode looked like this multiple times today: flag set, stack restarted, eval ran for 30 min, came back with byte-identical r5h baseline because the flag never propagated. Wasted cycle, demoralizing, no signal banked.

**A single wrapper script eliminates this entire class of confusion.**

---

## Acceptance rule

```
PASS if a single command runs the full SPANTAG eval flow with explicit
verification at every gate, and refuses to proceed (with a clear error
message) when any gate fails.

The operator should never need to manually verify SPANTAG is firing,
manually wait for warmup, or manually check log timestamps for staleness.
```

---

## Decisions locked

```
1. ONE script, ONE command, ONE eval cycle.
   ./scripts/run_extractor_eval.sh <suffix> [--spantag on|off]

2. Refuses to proceed on gate failure.
   Each gate prints what failed + what to check + how to fix; exits
   non-zero. No silent "I'll just keep going" behavior.

3. Idempotent — safe to re-run.
   If the stack is already in the desired state, skip the restart.
   If SPANTAG is already on, don't re-flip .env.

4. Distinguishes fresh vs. stale log lines.
   Marks a "session start timestamp" before any restart; verification
   greps only for log lines AFTER that timestamp.

5. Preserves existing operator workflow.
   The .bat launchers keep working independently. This script is an
   alternative path for batch eval cycles, not a replacement for the
   normal stack lifecycle.

6. Honest about cold boot.
   Doesn't claim "ready" until extractor warmup probe roundtrip
   reports <30s. The HTTP listener being up is necessary but not
   sufficient.

7. Reports failure pack inline.
   At end of eval, prints topline + value-coerce grep + spantag grep
   + failure category counts + named regressions (if any) so operator
   doesn't need to manually parse JSON.

8. Reuses existing infrastructure.
   Wraps existing run_question_bank_extraction_eval.py, existing
   warmup probe, existing failure_pack output. Adds NO new eval logic.

9. Supports dry-run for safety.
   ./scripts/run_extractor_eval.sh --dry-run <suffix> prints what
   it WOULD do without changing anything.
```

---

## Phases

### Phase 1 — Build the wrapper script

`scripts/run_extractor_eval.sh` — the single entry point.

#### Behavior

```bash
./scripts/run_extractor_eval.sh r5g-binding
./scripts/run_extractor_eval.sh r5h-postpatch --spantag off
./scripts/run_extractor_eval.sh --dry-run r5g-binding
./scripts/run_extractor_eval.sh --skip-restart r5g-binding-rerun
```

#### Internal flow

```
Step 0: parse args (suffix, --spantag on|off, --dry-run, --skip-restart)
        defaults: --spantag preserves current .env state; no --dry-run; no --skip-restart

Step 1: discover current .env state
        - read HORNELORE_SPANTAG from .env
        - if --spantag arg differs, prepare a flip
        - if --dry-run, print intended flip and exit

Step 2: capture session_start timestamp
        - record now() in ISO format
        - all subsequent log greps use this as a "fresh-only" filter

Step 3: flip .env if needed
        - sed -i with the explicit transform
        - verify the file actually changed (re-grep value, not just exit code)
        - if value didn't flip as expected, abort with diagnostic

Step 4: stack restart (unless --skip-restart)
        - pkill -f "uvicorn.*${PORT}" || true
        - call existing start_api_visible.sh in background
        - else: skip and assume stack is up

Step 5: wait for HTTP listener (max 90s)
        - poll http://localhost:8000/health every 3s
        - if not up after 90s, abort with diagnostic

Step 6: wait for LLM warmup (max 240s additional)
        - run a trivial extract POST
        - measure roundtrip
        - if roundtrip <30s, mark "warm"
        - else loop with backoff until warm or timeout
        - if timeout, abort with diagnostic

Step 7: verify SPANTAG state matches intent
        - grep api.log for "[launcher] SPANTAG: enabled=" lines AFTER session_start
        - if intent was on but log says enabled=0, abort with "stack didn't pick up .env flip"
        - if intent was off but log says enabled=1, abort with "stack still using old config"

Step 8: run the eval
        - exec ./scripts/archive/run_question_bank_extraction_eval.py
              --mode live
              --api http://localhost:8000
              --output docs/reports/master_loop01_${SUFFIX}.json
        - exit immediately on non-zero from eval

Step 9: post-eval inline report
        - parse the JSON report
        - print: topline (passed/total), v3 contract subset, v2 contract subset, mnw count
        - print: method_distribution (look for http_500, error_*)
        - print: parse_success_rate, truncation_rate
        - print: fresh greps for [extract][value-coerce] and [extract][spantag] lines from this run only
        - print: top 5 invalid-fieldpath hallucinations
        - print: stubborn pack status (primary/secondary/truncation_starved)
        - print: 1-line conclusion ("baseline preserved" / "regression detected" / "improvement detected")

Step 10: exit 0 on clean run, non-zero on any internal failure
```

#### File targets

```
NEW:
  scripts/run_extractor_eval.sh         (the wrapper)
  scripts/_eval_helpers.sh              (shared helpers — gate functions)

MODIFIED:
  scripts/archive/run_question_bank_extraction_eval.py  (only if needed —
                                                         possibly add --quiet flag)
```

#### Phase 1 acceptance

- `./scripts/run_extractor_eval.sh --dry-run r5x` prints the intended actions without changing anything
- `./scripts/run_extractor_eval.sh r5x --spantag off` runs cleanly when stack is already in SPANTAG=0 state (no unnecessary restart)
- `./scripts/run_extractor_eval.sh r5x --spantag on` flips .env, restarts stack, verifies firing, runs eval, prints summary
- Each gate failure exits with clear diagnostic (not a silent skip)
- Inline summary at end matches CLAUDE.md's standard post-eval audit block

---

### Phase 2 — Optional: extend to stubborn-pack runs

Same pattern, different inner script:

```bash
./scripts/run_stubborn_eval.sh r5g-binding-stubborn --runs 3
```

Wraps existing `scripts/archive/run_stubborn_pack_eval.py`. Same gates. Same inline report at end.

#### Phase 2 acceptance

- Stubborn-pack flow works through the same wrapper pattern
- Cross-run stability summary is included in inline output

---

## What this WO does NOT do

- Does NOT change extractor behavior in any way
- Does NOT modify the existing eval scripts (or modifies them only minimally for `--quiet` support)
- Does NOT replace the .bat launchers — they keep working
- Does NOT add new eval scoring logic
- Does NOT auto-commit eval reports (operator commits manually after review)

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Wrapper script masks a real underlying problem | Each gate prints diagnostic + exits non-zero; never silently continues |
| Stack restart inside wrapper conflicts with .bat launcher state | `--skip-restart` flag for when stack is already up; pkill is idempotent |
| Warmup probe gives false-positive (looks warm but extractor not really ready) | Probe exercises the actual extract path with a trivial POST, not just `/health`; roundtrip threshold is the gate |
| Operator tries to use both wrapper and .bat launcher simultaneously | Wrapper checks if a stack process exists; refuses to restart if `--skip-restart` not passed and process detected |
| .env flip fails silently due to whitespace / already-changed value | Phase 1 Step 3 re-greps after the flip; aborts if value isn't what was expected |
| Inline report parse fails on malformed JSON | Try/except with fallback to pointing operator at the file path |

---

## Stop conditions

Stop work and reconvene with Chris if:

1. Existing `run_question_bank_extraction_eval.py` needs significant modification to support the wrapper — this WO should be wrapper-only; modify the inner script only if absolutely necessary.
2. Stack restart logic needs to differ from what `start_api_visible.sh` already does — investigate whether the right move is to fix the existing script instead of duplicating its logic.
3. The "fresh log lines only" filter requires more than a timestamp grep (e.g., needs a session marker injected into api.log) — escalate before adding marker logic to the launcher.

---

## Final directive

Build the smallest possible wrapper that eliminates the multi-step ritual. Don't add new eval logic. Don't modify the extractor. Don't replace the .bat launchers. Just wrap what exists with verification gates so the operator can run a SPANTAG eval as one command and trust the result.

Estimated effort: 3–5 hours including testing.

Lab/gold: pattern (one-command eval with verification gates) promotes to Lorevox.
