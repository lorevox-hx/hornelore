# WO-EX-DISCIPLINE-01 — Run-report discipline header on master eval (#142)

**Status:** DRAFT (2026-04-22, authored after r5h adopt)
**Owner:** eval-harness lane (Claude)
**Priority:** parallel cleanup lane — does not block main sequence
**Blocks:** nothing
**Blocked by:** nothing
**Eval tag:** N/A (harness-side, byte-stable scoring)
**Task:** #142

---

## 1. Problem statement

When a master eval produces movement (case_081 flipped in r5h; +10 cases in r5f; r5e2's 7-case regression), reconstructing *what the system state was at run time* requires combining signals that aren't in the eval output: git SHA at HEAD, flag state (`HORNELORE_NARRATIVE`, `HORNELORE_ATTRIB_BOUNDARY`, `HORNELORE_PROMPTSHRINK`, `HORNELORE_SILENT_DEBUG`, `HORNELORE_SPANTAG`, `HORNELORE_INTAKE_MINIMAL`, etc.), model hash / fingerprint, api.log freshness window (was the stack cold-booted 30s before the run?), stack uptime.

This information is currently reconstructed from memory or by correlating timestamps against `.runtime/logs/`. It's the difference between "r5e2 regressed vs r5e1" and "r5e2 regressed vs r5e1 with `HORNELORE_ATTRIB_BOUNDARY=1` and no other flags toggled."

## 2. Proposal

Extend `scripts/run_question_bank_extraction_eval.py` to write a **discipline header** — the first ~20 lines of `master_loop01_<SUFFIX>.console.txt` and a top-level `"run_metadata"` key on `master_loop01_<SUFFIX>.json`. Harness-side only; no scoring change.

**Discipline-header content:**

```
[discipline] eval_tag=r5h
[discipline] started_at=2026-04-22T21:14:03Z
[discipline] git_sha=<7-char> git_dirty=<bool> branch=<branch>
[discipline] flags:
  HORNELORE_NARRATIVE=1
  HORNELORE_ATTRIB_BOUNDARY=0 (default)
  HORNELORE_PROMPTSHRINK=0 (default)
  HORNELORE_SILENT_DEBUG=0 (default)
  HORNELORE_SPANTAG=0 (default)
  HORNELORE_INTAKE_MINIMAL=0 (default)
[discipline] api_endpoint=http://localhost:8000
[discipline] api_model=<model_name>  api_model_hash=<sha256-12>
[discipline] api_uptime_seconds=<N>
[discipline] api_log_last_line_age_seconds=<N>  (freshness check — was the stack idle?)
[discipline] warmup_probe:
  post_extract_roundtrip_ms=<N>
  classification: cold|warming|hot  (<30s hot, <90s warming, else cold)
[discipline] scorer_version=<hash-of-run_question_bank_extraction_eval.py>
[discipline] case_bank_version=<hash-of-question_bank_extraction_cases.json>
```

**JSON metadata key** mirrors the same fields structured.

**Warmup probe:** issue one trivial `/extract/fields` call before the eval loop starts. Record the round-trip. Classify per CLAUDE.md cold-boot rule (<30s hot, <90s warming, else cold). Report in header. If `cold` and the eval is being run from a combined start+eval block (env hint or CLI flag), fail-fast with a helpful message; otherwise just note the classification and proceed.

## 3. Acceptance

- Every master eval produces a discipline header as the first ~20 lines of `.console.txt` + a `run_metadata` top-level key in the JSON
- `git_sha` captured (even from the eval harness process, which IS git-accessible from WSL; sandbox limitation doesn't apply here because Chris runs the eval, not the agent)
- `git_dirty=true` visible when HEAD has uncommitted changes — a load-bearing signal (per the git-hygiene gate)
- Flag state reflects *actual* runtime env-var values at the time the harness spawned, not defaults
- Warmup probe round-trip <30s ⇒ header says `hot`, and if the first case subsequently times out or regresses unexpectedly, the header is unambiguous evidence that the stack was ready
- Zero impact on scoring (run_metadata is additive)

## 4. Integration with WO-EX-FAILURE-PACK-01 (#141)

Once both #141 and #142 land, the full per-eval artifact set is:

1. `master_loop01_<SUFFIX>.json` — score body (existing)
2. `master_loop01_<SUFFIX>.console.txt` — topline + per-case readout (existing, extended with discipline header)
3. `master_loop01_<SUFFIX>.failure_pack.json` — cluster rollup (new, #141)
4. `master_loop01_<SUFFIX>.failure_pack.console.txt` — cluster rendering (new, #141)

The discipline header applies to #1 + #2. #141 sidecar files do NOT need a discipline header (they're derived from #1 which already has it).

## 5. Scope-out

- Does NOT perform any autonomy ("don't run eval if api.log stale"). The agent MAY add fail-fast on cold stack only when invoked from a combined block (a CLI flag like `--fail-on-cold`). Default: proceed.
- Does NOT capture api.log contents into the header (too large). `api_log_last_line_age_seconds` is the freshness signal.
- Does NOT touch extract.py, the scorer, or the case bank.

## 6. Implementation note

Most of the fields come from: `git rev-parse`, `git status`, `os.environ.get('HORNELORE_*', '0')`, a small HTTP GET to `/health` or `/status` endpoint (if the api exposes uptime/model info — otherwise `api_uptime_seconds` is omitted gracefully), `os.path.getmtime('.runtime/logs/api.log')`, and the warmup probe.

The model hash requires a `/status` or `/model` endpoint that returns a stable identifier. If absent, this field is omitted gracefully with a one-line note in the header (`api_model_hash=unavailable — endpoint not exposed`).

## 7. Rollback

Remove the header-write block at the top of `run_question_bank_extraction_eval.py` and the `run_metadata` key emission.

## 8. Not required to land before main sequence

This is a triage-hygiene WO. It does not block #144 / #97 / #95 / #90 / LORI / INTAKE-IDENTITY. Land it whenever convenient; first beneficiary will be the next eval where the system state at run-time matters for attribution.
