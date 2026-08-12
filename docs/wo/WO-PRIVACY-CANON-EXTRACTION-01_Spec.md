# WO-PRIVACY-CANON-EXTRACTION-01 — Canon extraction, fictionalization, and history purge

**Status:** PARKED — deliberately deferred. Opened 2026-08-12 after the public-repository privacy audit (`HANDOFF_CODE_REVIEW_2026-08-12.md` §1/§11.4). Product work (Travel Doc) takes priority; this WO exists so the remaining privacy work is a planned job, not a lost thread.

**Context.** The repo is public by requirement (ChatGPT reviews it over the web). Commit `a87e865` (2026-08-12) already untracked the raw private artifacts — `transfer/hornelore_data.zip` (3 SQLite DBs + transcripts), `wo12b_evidence/`, wo13 proof dirs, 767 `docs/reports/` files, the three real-person templates, the live-test docx, and the Janice timeline pack — with `.gitignore` rules so they cannot return. That commit fixed the *visible tree only*. Two things remain:

1. **~250 tracked files still embed real family data** (names, DOBs 1939-09-30 / 1962-12-24, birthplaces Spokane/Stanley/Lima, story details) inside working code, tests, evals, and prose. They cannot be untracked without breaking the product.
2. **Everything ever committed is still fetchable from git history** on the public repo, including the artifacts removed by `a87e865`.

## Phase 1 — Canon extraction (machine-readable data)

Move real data out of the repo into a private "canon" store; commit fictional replacements. **Canon lives OUTSIDE the repo at `C:\hornelore_data\canon\`** — not gitignored-inside (the `.env` backup sprawl showed how that pattern drifts).

Lanes, in order of coupling risk:

- `data/qa/question_bank_extraction_cases.json` (+ canon-grounded corpus): copy verbatim to `canon/qa/` (baselines like 78/114 stay valid against it — the canon file is byte-identical to today's); author a fictional public corpus for the committed path. Eval runner already takes `--cases`/paths, so canon runs are an argument, not a code change. The scorer's truth zones are keyed to exact strings — fictional cases need their own truth zones, not find-and-replace.
- `ui/templates/*-horne.json` (already untracked): move to `canon/templates/`; template loader checks canon dir first, falls back to committed fictional examples. Dolly/Shatner/narrator-template stay committed.
- Harness/replay scripts with embedded transcripts (`scripts/replay_kent_*.py`, `one_shot_kent_fort_ord_long.py`, regional harnesses, etc.): lift transcript text into `canon/transcripts/`; scripts keep logic only and load from canon (skip with a clear message when canon is absent, so public contributors aren't broken).
- `docs/voice_models/`, fixtures, timeline context packs: same split — pattern stays public, real quotes go to canon.

## Phase 2 — Prose redaction (cannot be extracted)

`CLAUDE.md`, `README.md`, `MASTER_WORK_ORDER_CHECKLIST.md`, WO specs and archived handoffs quote live sessions verbatim. These need text edits: replace identifying details with fictional stand-ins or neutral phrasing ("the narrator", "a 1939 birthdate") while preserving the operational meaning of each entry. Per repo doctrine, correct in place — do not silently rewrite history entries' technical content.

## Phase 3 — History purge (the actual closure)

Only after Phases 1–2, so history is rewritten **once**:

1. `git filter-repo` removing the `a87e865`-untracked paths AND the pre-fictionalization versions of the Phase 1/2 files from all history. Force-push.
2. Contact GitHub support to drop cached views of old commits.
3. Verify no forks exist (a fork keeps the old history regardless).
4. Coordinate with the ChatGPT web-review workflow: a rewritten history invalidates its cached clone state.

## Acceptance

- Public tree and full public history contain no real family names, DOBs, birthplaces, transcripts, or databases.
- Evals: canon lane reproduces the locked baseline; fictional public lane runs green for a contributor with no canon dir.
- All harness scripts either run from canon or skip cleanly.
- No product behavior change; Travel Doc and interview lanes untouched.

## Explicitly out of scope

Auth tokens (none leaked — verified), `hornelore_data` (audited separately 2026-08-12), and any product feature work.
