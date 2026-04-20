# CLAUDE.md — Hornelore Agent Env Notes

**Read this first at the start of every session.** These are persistent operational facts, not a task log.

## Environment

- **OS**: Windows 11 + WSL2 (Ubuntu). Chris works from WSL.
- **Repo path (WSL)**: `/mnt/c/Users/chris/hornelore` — NOT `~/hornelore`.
- **Agent workspace mount**: `/sessions/<session-id>/mnt/hornelore`. Edits here are live on Chris's repo.
- **GPU**: NVIDIA RTX 50-series (Blackwell). Local LLM serves from this machine.

## Stack ownership

- **Chris starts and stops the API and full stack himself.** Do NOT include `./scripts/start_all.sh` or `./scripts/stop_all.sh` in copy-paste blocks.
- The API is assumed to be running at `http://localhost:8000` whenever an eval is asked for.

## Standard eval command (copy-paste ready)

When asked to run or re-run a master eval, emit exactly this block, rotating the output suffix:

```bash
cd /mnt/c/Users/chris/hornelore
./scripts/run_question_bank_extraction_eval.py --mode live \
  --api http://localhost:8000 \
  --output docs/reports/master_loop01_<SUFFIX>.json
grep "\[extract\]\[turnscope\]" .runtime/logs/api.log | tail -40
```

The eval script auto-writes `docs/reports/master_loop01_<SUFFIX>.console.txt` next to the JSON — no shell `| tee` needed (was silently producing 0-byte files under WSL pipe-buffer conditions; r4h's empty console triggered the fix on 2026-04-19).

Suffix convention: `r4f` = Patch F narrowing, `r4g` = WO-EX-TURNSCOPE-01 v1 (target hit, +2 compound-extract regressions), `r4h` = TURNSCOPE v2 (target hit, 060/062 restored, must_not_write=0 — **#72 CLOSED**; case_012/020 newly missing fields are LLM stochasticity, filter is provably no-op when extractPriority=None). Next: `r4i` = #67 holiday-date fix land.

The grep at the end rotates — change the tag to whatever filter is being tested (`turnscope`, `negation-guard`, `R4-E`, etc.) or drop it when not needed.

## Standard post-eval audit block

After every eval that follows a code change, report this exact block before declaring any movement real:

- total pass count
- v2 contract subset
- v3 contract subset
- must_not_write violations
- named affected cases (newly passed, newly failed)
- pass↔fail flips
- scorer-drift audit on every flip (eyeball the truth zones — does the score change reflect a real extraction change, or a scorer/expectation drift?)

## Where files live

| Kind | Path |
|---|---|
| API log | `/mnt/c/Users/chris/hornelore/.runtime/logs/api.log` |
| Eval JSON reports | `/mnt/c/Users/chris/hornelore/docs/reports/master_loop01_*.json` |
| Eval console readouts | `/mnt/c/Users/chris/hornelore/docs/reports/master_loop01_*.console.txt` |
| Eval case source | `/mnt/c/Users/chris/hornelore/data/qa/question_bank_extraction_cases.json` |
| Extract router | `/mnt/c/Users/chris/hornelore/server/code/api/routers/extract.py` |
| WO specs | `/mnt/c/Users/chris/hornelore/WO-*_Spec.md` (repo root) |
| WO reports | `/mnt/c/Users/chris/hornelore/docs/reports/WO-*_REPORT.md` |

All of these are readable from the agent workspace mount via the session prefix. After an eval runs, read the console + JSON directly — do not ask Chris to paste them.

## Current phase

**LOOP-01 R4 cleanup — post-r4h baseline.** Sequence:

1. **#67** — case_011 Patch H date un-normalisation. Patch staged (holiday-phrase normaliser + suffix expansion + `St. Patrick's Day` period regex). 27/27 unit tests green. Pending: pytest regression test + `WO-EX-PATCH-H-DATEFIELD-01_REPORT.md` + r4i live eval.
2. **#68** — case_053 wrong-entity. Disposition: defer to R5 Pillar 2 (OTS/entity-binding bias is architectural, not a tactical patch). Re-check after #67 lands to see if it indirectly shifted; if not, write disposition memo.
3. **#81** — WO-EX-PROMPTSHRINK-01 spec.
4. **#63** — eval-harness should_pass drift audit, in parallel to #81; retag `guard_false_positive` → `scope_escape` now that #72 is closed.
5. **Freeze post-R4 baseline.**
6. **#82** — post-R4 memo + R5.5 citation-grounding spec.
7. Pivot to **R5.5** (the real attack on `dense_truth 0/8` and `large chunks 0/4` cliffs). See `docs/reports/loop01_research_synthesis.md`.

Each WO above must report the standard audit block before being called done.

**Closed:** #72 / WO-EX-TURNSCOPE-01 (r4h hit gate: case_094 pass, 060/062 restored, must_not_write=0, no follow-up regressions). Note: r4h did NOT lift the topline (53/104 vs r4f 54/104 — within stochastic noise). Net-master movement now has to come from #67 / #68 / #81, not further turn-scope iteration.

## Chris's working preferences

- Honest critique over flattery. Push back on ideas when warranted.
- Tight readouts, not walls of text.
- Do NOT relitigate things already decided.
- When three agents (Claude/Gemini/ChatGPT) converge on the same answer, act on it; don't re-argue.
- Do not regenerate command blocks from memory — copy from this file.
- Read logs and reports directly from the workspace mount; don't ask Chris to paste.

## Changelog

- 2026-04-19: Created. Captures WSL path correction and eval-command template.
- 2026-04-19 (late): r4h confirms WO-EX-TURNSCOPE-01 closes. Eval script now auto-writes `.console.txt` (shell `| tee` dropped after r4h produced an empty file). Standard post-eval audit block codified. #67 staged but not yet landed.
