# Hornelore repository archive audit

**Audit date:** 2026-08-28  
**Reviewed authority:** clean `origin/main` at `ea3ab271b42e2151397b6ca7991125b5e9ea94d3`  
**Action taken:** read-only review; no repository files moved, edited, deleted, committed, or pushed

## 1. Supervisory ruling

Hornelore has two different kinds of bloat:

1. **Authority bloat:** completed work, retired wording, old handoffs, and current status repeated across several documents. This is the main source of confusion and rework.
2. **Checkout bloat:** academic source files and one unused MediaPipe binary account for a large share of the tracked bytes.

The working product code and the main `tests/` tree are not archive candidates. Parked safety code, inert directive code, frozen Kawa code, compatibility readers, and accepted tests remain executable preservation boundaries until separately retired.

The correct cleanup is an indexed reorganization. It is not a deletion sweep.

## 2. Evidence-derived repository baseline

| Measure | Derived result |
|---|---:|
| Tracked files | 1,196 |
| Tracked bytes | 59,882,663 |
| Current checkout excluding `.git` | 63,650,684 bytes |
| Git common directory | 33,204,077 bytes |
| Markdown files | 281 |
| Python files | 549 |
| JavaScript files | 117 |
| SQL migration files | 50 |
| Commits across all refs | 1,280 |
| Commit span | 2026-04-10 through 2026-08-27 |
| Existing `docs/archive/` | 130 files, 2,097,967 bytes |
| Existing pre-pivot work orders | 113 files |
| Existing pre-pivot handoffs | 16 files |
| Root work-order/bug specs | 29 files, 175,358 bytes |
| `docs/wo/` | 51 files, 1,142,222 bytes |
| `scripts/` outside its archive | 95 files, 1,923,367 bytes |
| `scripts/archive/` | 32 files, 577,047 bytes |
| Main `tests/` tree | 295 tracked files |

Commit counts were derived from Git, not read by eye: April 347, May 218, June 108, July 347, August 260.

## 3. Full-Git findings

- There are no tags. A pre-cleanup tag should be created before any moves.
- Eight old remote development branches remain besides `main`.
- Seven are ancestors of `origin/main`.
- `origin/claude/sad-ramanujan-9c6032` is not structurally merged, but `git cherry` marks all four of its unique commits `-`, meaning patch-equivalent changes exist on `main`.
- Remote branch deletion is optional housekeeping and must occur only after the pre-cleanup tag and explicit authorization.
- `git fsck` reports unreachable historical objects and a 4 KiB worktree-ref garbage item. This is not a working-tree defect and does not justify manual deletion.
- A history rewrite is not part of this cleanup. The parked privacy/history-purge work order remains the authority for that separate operation.

## 4. Existing archive is not one thing

### `docs/archive/`

This is a genuine historical archive:

- `docs/archive/workorders-pre-pivot/`: 113 files
- `docs/archive/handoffs-pre-pivot/`: 16 files
- `docs/archive/handoffs/`: 1 file

The count in `CLAUDE.md` says 114 pre-pivot work-order files; Git derives 113. That number should be corrected or replaced with a command-derived instruction.

### `scripts/archive/`

This is **not** a genuine inert archive. It contains:

- currently documented eval runners;
- backup and restore tools;
- a retired evaluator retained for reproduction;
- Test Lab files whose current location is known to be broken;
- one-time import/setup utilities;
- historical diagnostics.

Nothing under `scripts/archive/` may be bulk-deleted or assumed dead. It needs an executable-status index and later separation into supported legacy tools versus inert historical scripts.

## 5. Current authority that must remain visible

The cleanup must preserve a short, explicit path to:

- `HANDOFF.md` — current state and next action only;
- `MASTER_WORK_ORDER_CHECKLIST.md` — active, next, deferred, and separately authorized work only;
- `CLAUDE.md` — durable agent doctrine and prohibitions;
- `README.md` — product and operator documentation, not a commit ledger;
- `docs/wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_Spec.md`;
- `docs/wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_PHASE2_TRANSPORT_MAP.md`;
- `docs/architecture/LORI-RUNTIME-ARCHITECTURE.md`;
- `docs/architecture/TRAVEL_DOCUMENT_DOCTRINE.md`;
- `docs/decisions/2026-08-04-park-safety-feature.md`;
- the parked privacy work order and other explicitly preserved future decisions.

The active Profile Seed transport map currently has no incoming filename reference from the governing documents. That should be corrected in the new handoff.

## 6. Pre-Step-6 product obligations that cleanup must not erase

Step 5 remains accepted, but the fresh supervisory audit found a bounded correction checkpoint before WebSocket Step 6:

1. Repair mutation instruments M1 and M8 so each is caught by a discriminating behavioral assertion rather than an errors-only `BROKEN` result.
2. Make `expected_version` a strict integer at both API and database boundaries; reject booleans, floats, and strings; add tests and a mutation.
3. Correct the Phase 2 transport map from six to nine persisted deterministic paths by adding `floor_buffer`, `past_tense_acknowledge`, and `bank_flush`.
4. Define server-authoritative control/system-directive behavior so control turns hold onboarding state and suppress the legacy pass block without asking, stamping, or advancing a Profile Seed topic.
5. Stop hard-coding a self-invalidating “current main” commit in `HANDOFF.md`; retain stable acceptance hashes and derive current HEAD with Git.

This checkpoint remains separate from the repository-hygiene commits and from Step 6 implementation.

## 7. Safe first archive cohort

These are proven historical or misplaced artifacts. Moving them changes navigation, not product behavior.

### Root-level historical/control artifacts

- `HANDOFF_2026-07-01.md`
- `HANDOFF_CODE_REVIEW_2026-08-12.md`
- `PLAN_2026-07-13.md`
- `clock_mockups_v1.html`
- all 29 root `WO-*` / `BUG-*` specs listed in Appendix A

The 29 specs may all leave the repository root, but unresolved obligations must first be summarized in one backlog registry. “Archived” must not mean “decided complete.”

### Historical document cohorts

- `docs/handoffs/` — 4 files
- `docs/drafts/` — 3 files
- `docs/mockups/` — 16 files
- `ui/mockups/` — 3 files
- `docs/wo-qa/` — 11 April-era files, after updating the one `.env.example` rationale link
- `shadow/` — 5 unreferenced April DOCX design packets

### Singular legacy test tree

- `test/` — 9 files

This tree is outside the documented `tests/` runner, its Python module instructs use of pytest even though pytest is not installed, and it has not changed since the initial import. Its cognitive-support assertions overlap newer tests, but equivalence must be mapped before moving it.

### Giant changelog

- `docs/CHANGELOG-AGENT.md` — 614,130 bytes, 1,407 very long lines

Preserve a dated snapshot under the archive and replace the live file with a small indexed decision history. `CLAUDE.md` should point agents to current architecture/ADRs first, not ask them to load a 600 KiB chronological narrative.

## 8. Files that may leave the current checkout after preservation

### Academic source binaries

`docs/references/` contains 16 files totaling 19,075,035 bytes. The repository's own `docs/research/references.md` says retained paper copies belong under gitignored `docs/research/papers/`, with canonical citations and external links in Git.

Recommended treatment:

1. Copy the 16 files to the operator's local research archive.
2. Verify SHA-256 values against the current tree.
3. Keep citations, URLs, local-copy notes, and checksums in Git.
4. Remove the binaries from the current tree in a separate reviewed commit.

This reduces the checkout, not existing Git history. Copyright/redistribution review is an additional reason not to carry publisher PDFs in the source repository.

### Unused SIMD hold binary

- `ui/vendor/mediapipe/face_mesh/_simd_hold/face_mesh_solution_simd_wasm_bin.wasm` — 6,161,697 bytes

Current production code explicitly redirects all SIMD asset requests to the non-SIMD bundle and describes the held SIMD asset as unusable. Removal requires a focused asset-path test but is a strong candidate.

Together, the research binaries and held SIMD file are 25,236,732 bytes, about 42% of all tracked bytes.

### Other small proven candidates

- empty root file `wsl` — recorded by the prior review as an accidental redirect artifact;
- `server/code/test_model_results.json` — initial-import result file with no current references;
- `data/lori/narrative_cue_library.candidate_class_b_v1.json` — byte-identical to the promoted `narrative_cue_library.v1.seed.json`, while current code and tests read the seed;
- old mockups and shadow packets after indexing.

## 9. Work that requires backlog adjudication before archival

Old status headers are not reliable enough to make decisions. The 29 root specs contain:

- 14 headers containing `CLOSED` or `LANDED`, but one is explicitly only partially landed;
- 9 headers saying open/active/filed;
- 3 banked/spec-only items;
- 3 with no clear status in the opening block.

The following root items visibly retain unresolved or unclear obligations and must be represented in `docs/BACKLOG.md` before their full specs move:

- `BUG-LIFEMAP-COMM-CONTROL-TRIM-01_Spec.md`
- `BUG-LIFEMAP-CONTEXT-TRUNCATION-01_Spec.md`
- `BUG-LORI-DEEP-EUROPEAN-ROUTE-LANGUAGE-DRIFT-01_Spec.md`
- `BUG-LORI-FACTUAL-OVER-SENSORY-PROBE-01_Spec.md`
- `BUG-LORI-FEWSHOT-EXEMPLAR-LEAK-01_Spec.md`
- `BUG-LORI-META-PREAMBLE-LEAK-01_Spec.md`
- `BUG-LORI-RESPONSE-GUARDS-STALE-TRIP-SURFACE-DOCSTRING-01_Spec.md`
- `BUG-LORI-RESPONSE-STUB-COLLAPSE-01_Spec.md`
- `BUG-LORI-SPANISH-MISFIRE-ENGLISH-SESSION-01_Spec.md`
- `BUG-LORI-TRIP-DIRECT-QUESTION-DODGE-01_Spec.md`
- `WO-LORI-ENGLISH-FIRST-SESSION-MODE-01_Spec.md`
- `WO-TRAVEL-DOC-OPERATOR-DRAFT-ASSISTANT-01_Spec.md`
- `WO-TRIP-INTERVIEW-CONTEXT-01_Spec.md`
- `WO-TRIP-LORI-ANSWER-CAPTURE-01_Spec.md`
- `WO-TRIP-PHOTO-CONTEXT-ENRICHMENT-FOR-LORI-01_Spec.md`
- `WO-TRIP-PHOTO-LIFEMAP-PROJECTION-01_Spec.md`

`docs/wo/` also contains completed, superseded, parked, partially landed, future-only, and stale-“active” documents together. Twenty-nine of its 51 files are not named by the four governing documents or current architecture/runbook set. That is a triage signal, not proof of deadness: the active Profile Seed transport map itself demonstrates that missing links can be a documentation defect.

The correct disposition is:

- active current implementation specs stay in `docs/wo/`;
- durable decisions move or remain under `docs/decisions/` or `docs/architecture/`;
- accepted/completed work orders move to `docs/archive/workorders/completed/`;
- superseded work orders move to `docs/archive/workorders/superseded/`;
- unfinished but non-current designs are summarized in `docs/BACKLOG.md`, with full specs under `docs/archive/workorders/banked/`.

## 10. Scripts and tests

### Tests

Do not archive the main `tests/` tree based on age. It is the preservation contract for accepted behavior. Source-shape tests may be maintenance-heavy, but they must be replaced behaviorally before removal.

### Scripts

The 95 scripts outside `scripts/archive/` divide by last-change month as follows: April 13, May 20, June 30, July 11, August 21. Eighteen non-package files have no incoming current-tree reference. That is not enough evidence to delete a command-line tool.

Required action:

- add `scripts/INDEX.md` with `operational`, `current acceptance`, `supported legacy`, `one-time`, `historical`, and `broken` states;
- keep launcher dependencies in place;
- keep current mutation and acceptance gates in place;
- repair or archive `scripts/ui/run_test23_two_person_resume.py`, which currently has an `IndentationError` at line 2082;
- restore Test Lab only as a separate bounded lane—the archived harness is not location-aware;
- move only tools whose purpose and replacement are both named.

The syntax sweep found exactly one Python parse failure: `scripts/ui/run_test23_two_person_resume.py`. All tracked shell scripts passed `bash -n`; all tracked JavaScript files passed `node --check`.

## 11. Tooling repair, not archival

The following are current configuration defects:

- `package.json` names nonexistent `tailwind.config.js` as `main`;
- `package.json` says `ISC` while the repository has a proprietary/source-available `LICENSE`;
- five npm scripts name nonexistent Playwright specs;
- `playwright.config.ts` names nonexistent `scripts/start-lorevox-audit.sh`;
- the live Test Lab router points at nonexistent root script paths, while simply repointing it to `scripts/archive/` is known to fail after returning a false success.

These should be repaired in bounded tooling commits. They should not be hidden by moving the configuration into an archive.

## 12. Control-document simplification

Current sizes:

| File | Bytes | Lines | Profile Seed / Step 6 / Phase 2 matches |
|---|---:|---:|---:|
| `CLAUDE.md` | 42,808 | 424 | 1 |
| `HANDOFF.md` | 42,438 | 463 | 24 |
| `MASTER_WORK_ORDER_CHECKLIST.md` | 21,738 | 107 | 12 |
| `README.md` | 23,314 | 342 | 7 |
| `docs/CHANGELOG-AGENT.md` | 614,130 | 1,407 | n/a |

The repeated current-state narrative is the mechanism behind the repeated stale-status corrections. The replacement should be:

- one authoritative current-state table in `HANDOFF.md`;
- one short ordered queue in the checklist;
- README links to current state without duplicating commit ledgers;
- CLAUDE contains durable doctrine only;
- one archive ledger for completed work;
- Git-derived commands for current HEAD and counts.

Retirement notes do not need to be repeated indefinitely in every live control document. Git history and the archive ledger preserve them more accurately.

## 13. Recommended cleanup sequence

### Commit 0 — safety marker

- Create and push an annotated tag at `ea3ab27`, e.g. `archive/pre-hygiene-2026-08-28`.
- Confirm clean tree and remote parity.

### Commit 1 — indexes only

- Add `docs/INDEX.md`.
- Add `docs/BACKLOG.md` with every unresolved obligation and its evidence/status.
- Add `docs/archive/INDEX.md` with exact manifests and original paths.
- Add `scripts/INDEX.md` with executable status.
- Add a short repository-hygiene work order with explicit no-product-code boundary.

No moves yet.

### Commit 2 — control authority

- Reduce `HANDOFF.md` to current state, the pre-Step-6 correction checkpoint, and the next action.
- Reduce the checklist to active/next/deferred/separately-authorized work.
- Remove duplicated lane status from README.
- Keep CLAUDE doctrine durable and command-derived.
- Archive the giant changelog snapshot and expose a small current index.

### Commit 3 — historical moves

- Move the 29 root specs.
- Move dated handoffs, plan, drafts, mockups, and shadow documents.
- Move completed/superseded work orders according to the index.
- Update every local link and run a broken-link check.

### Commit 4 — legacy tests and scripts

- Map the singular `test/` coverage to current tests, then archive it.
- Add script states and move only proven historical tools.
- Keep Test Lab repair separate.
- Do not touch production source.

### Commit 5 — tracked-byte reduction

- Preserve and checksum research documents outside Git, then remove tracked binaries.
- Remove the unused SIMD hold asset after its focused gate.
- Remove the empty `wsl`, old result JSON, and duplicate cue candidate.

### Verification checkpoint

- clean tree;
- path/link validation;
- Python/shell/JavaScript syntax sweep;
- current focused test suites;
- current mutation gate status reported honestly;
- launcher paths verified;
- no `server/` or live UI behavior changes except the separately gated unused-asset removal.

Only after this checkpoint should the pre-Step-6 correction block and then WebSocket Step 6 begin.

## Appendix A — all 29 root specifications

1. `BUG-CHATWS-CONV-FK-01_Spec.md`
2. `BUG-DEPRECATION-DATETIME-UTCNOW-01_Spec.md`
3. `BUG-FE-FACTS-ADD-PAYLOAD-SHAPE-422-01_Spec.md`
4. `BUG-HARNESS-SCORER-TOO-LENIENT-CONTENT-QUALITY-01_Spec.md`
5. `BUG-LIFEMAP-COMM-CONTROL-TRIM-01_Spec.md`
6. `BUG-LIFEMAP-CONTEXT-TRUNCATION-01_Spec.md`
7. `BUG-LORI-ANCHOR-CASCADE-DUMP-01_Spec.md`
8. `BUG-LORI-ASKS-WHAT-OPERATOR-SEEDED-01_Spec.md`
9. `BUG-LORI-CHAIN-ANCHOR-ECHO-STRENGTH-01_Spec.md`
10. `BUG-LORI-DEEP-EUROPEAN-ROUTE-LANGUAGE-DRIFT-01_Spec.md`
11. `BUG-LORI-FACTUAL-OVER-SENSORY-PROBE-01_Spec.md`
12. `BUG-LORI-FEWSHOT-EXEMPLAR-LEAK-01_Spec.md`
13. `BUG-LORI-META-PREAMBLE-LEAK-01_Spec.md`
14. `BUG-LORI-META-RESPONSE-LEAK-01_Spec.md`
15. `BUG-LORI-PHRASE-AS-NAME-CONFIRMATION-01_Spec.md`
16. `BUG-LORI-RESPONSE-GUARDS-STALE-TRIP-SURFACE-DOCSTRING-01_Spec.md`
17. `BUG-LORI-RESPONSE-STUB-COLLAPSE-01_Spec.md`
18. `BUG-LORI-SPANISH-MISFIRE-ENGLISH-SESSION-01_Spec.md`
19. `BUG-LORI-THEMATIC-TRIP-CHAIN-DETECTION-01_Spec.md`
20. `BUG-LORI-TRIP-DIRECT-QUESTION-DODGE-01_Spec.md`
21. `BUG-ML-SPANISH-DETECT-FRENCH-PLACE-OVERFIRE-01_Spec.md`
22. `BUG-SAFETY-CHILD-ABUSE-FALSE-POSITIVE-DEATH-CAR-01_Spec.md`
23. `WO-LORI-ENGLISH-FIRST-SESSION-MODE-01_Spec.md`
24. `WO-TRAVEL-DOC-ACCORDION-TIMELINE-01_Spec.md`
25. `WO-TRAVEL-DOC-OPERATOR-DRAFT-ASSISTANT-01_Spec.md`
26. `WO-TRIP-INTERVIEW-CONTEXT-01_Spec.md`
27. `WO-TRIP-LORI-ANSWER-CAPTURE-01_Spec.md`
28. `WO-TRIP-PHOTO-CONTEXT-ENRICHMENT-FOR-LORI-01_Spec.md`
29. `WO-TRIP-PHOTO-LIFEMAP-PROJECTION-01_Spec.md`

## Appendix B — commands that reproduce the principal counts

```bash
git rev-parse origin/main
git status --short --branch
git ls-files | wc -l
git ls-files -z | xargs -0 wc -c | tail -1
git rev-list --all --count
git branch -r --merged origin/main
git branch -r --no-merged origin/main
git cherry -v origin/main origin/claude/sad-ramanujan-9c6032
git ls-files 'docs/archive/workorders-pre-pivot/**' | wc -l
git ls-files 'docs/archive/handoffs-pre-pivot/**' | wc -l
git ls-files | rg '^(WO-|BUG-).*(_Spec\.md|\.md)$' | wc -l
git ls-files 'docs/wo/**' | wc -l
git ls-files 'scripts/**' ':!scripts/archive/**' | wc -l
git ls-files 'scripts/archive/**' | wc -l
```
