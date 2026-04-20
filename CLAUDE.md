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
  --output docs/reports/master_loop01_<SUFFIX>.json \
  2>&1 | tee docs/reports/master_loop01_<SUFFIX>.console.txt
grep "\[extract\]\[turnscope\]" .runtime/logs/api.log | tail -40
```

Suffix convention: `r4f` = Patch F narrowing, `r4g` = WO-EX-TURNSCOPE-01 v1 (target hit but +2 compound-extract regressions), `r4h` = TURNSCOPE v2 (multi-target fix), then r4i, etc.

The grep at the end rotates — change the tag to whatever filter is being tested (`turnscope`, `negation-guard`, `R4-E`, etc.) or drop it when not needed.

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

**LOOP-01 R4 cleanup.** Remaining open tasks:
- #67 — case_011 Patch H date un-normalisation regression
- #68 — case_053 wrong-entity regression
- #72 — WO-EX-TURNSCOPE-01 (follow-up scope filter) — code landed 2026-04-19, pending r4g confirmation eval
- Prompt/schema catalog shrink (unassigned)
- #63 — eval-harness audit (retag `guard_false_positive` → `scope_escape` after #72 lands)

R4 freeze gate: clean confirmation eval, then write the post-R4 memo. Only then pivot to **R5.5 citation grounding** (the real attack on the `dense_truth 0/8` and `large chunks 0/4` cliffs). See `docs/reports/loop01_research_synthesis.md` for the full R5+ action map.

## Chris's working preferences

- Honest critique over flattery. Push back on ideas when warranted.
- Tight readouts, not walls of text.
- Do NOT relitigate things already decided.
- When three agents (Claude/Gemini/ChatGPT) converge on the same answer, act on it; don't re-argue.
- Do not regenerate command blocks from memory — copy from this file.
- Read logs and reports directly from the workspace mount; don't ask Chris to paste.

## Changelog

- 2026-04-19: Created. Captures WSL path correction and eval-command template.
