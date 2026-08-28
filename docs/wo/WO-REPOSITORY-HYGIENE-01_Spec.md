# WO-REPOSITORY-HYGIENE-01 — indexed reorganization, not a deletion sweep

**Status:** ACTIVE — **Step 1 ACCEPTED `5f6b01b`; Step 2 ACCEPTED `db0c5e7`. Step 2b is
the current step and is not started.** Steps 3–5 not started. No file has moved.
**Opened:** 2026-08-28
**Authority:** [`../reviews/HORNELORE_REPOSITORY_ARCHIVE_AUDIT_2026-08-28.md`](../reviews/HORNELORE_REPOSITORY_ARCHIVE_AUDIT_2026-08-28.md)
and its [verification addendum](../reviews/HORNELORE_REPOSITORY_ARCHIVE_AUDIT_2026-08-28_VERIFICATION_ADDENDUM.md)
**Pre-hygiene rollback point:** tag `archive/pre-hygiene-2026-08-28` at `d0e5294`
**Blocks:** Phase 2 Step 6

---

## 1. The ruling this work order implements

Hornelore has two kinds of bloat, and only one of them is about bytes:

1. **Authority bloat.** Completed work, retired wording and current status repeated across
   several live documents. **This is the main source of confusion and rework**, and it is
   what has twice produced a stale current-work list that read as an instruction to
   rebuild finished work.
2. **Checkout bloat.** Academic PDFs and one unused MediaPipe binary — 25,236,732 bytes,
   about 42% of all tracked bytes.

**The correct cleanup is an indexed reorganization. It is not a deletion sweep.** Working
product code and the main `tests/` tree are not archive candidates.

---

## 2. Boundaries — these do not expire with a commit

**Do not, at any point in this work order:**

* touch **production source**, UI, schemas or migrations;
* start **WebSocket Step 6** or any onboarding wiring;
* change **product behaviour** in any way;
* **bulk delete** anything;
* assume `scripts/archive/`, `docs/wo/`, or the singular `test/` directory is dead;
* archive the main `tests/` tree;
* remove parked runtime safety, frozen Kawa, the inert directive registry, compatibility
  readers, or preserved future work;
* casually "repair" Test Lab — it is a separate bounded lane, and repointing it at
  `scripts/archive/` is known to **fail after returning a false success**;
* **combine product corrections, indexing, file moves and deletion in one commit.**

That last one is the rule the others depend on. A commit that moves files *and* changes
behaviour cannot be reverted on the strength of either.

**A history rewrite is not part of this work order.** `WO-PRIVACY-CANON-EXTRACTION-01`
remains the authority for that, and it is parked.

---

## 3. Sequence

Each numbered step is one commit, pushed, and **stopped for supervisory review** before the
next begins.

| # | Commit | Contents | State |
|---|---|---|---|
| 0 | Safety marker | Annotated tags `archive/pre-hygiene-2026-08-28` → `d0e5294` and `audit/repository-baseline-2026-08-28` → `ea3ab27` — the second is the audited baseline and **not the rollback point** | **DONE — both published on GitHub and peel correctly** |
| 1 | **Indexes only** | This file, `docs/INDEX.md`, `docs/BACKLOG.md`, `docs/archive/INDEX.md`, `scripts/INDEX.md`, the audit verbatim, the verification addendum. **No moves** | **ACCEPTED `5f6b01b`** |
| 2 | Control authority | `HANDOFF.md` → current state and next action. Checklist → active/next/deferred. README → product and operation, not commit history. `CLAUDE.md` → durable doctrine, with the corrections in `BACKLOG.md` §4 | **ACCEPTED `db0c5e7`** |
| 2b | Changelog | Archive a dated snapshot of `docs/CHANGELOG-AGENT.md` and establish a small live decision index. **Split from step 2 deliberately: it is a MOVE**, and §2's standing rule forbids combining a documentation rewrite with a file move in one commit | 🔵 **CURRENT — not started** |
| 3 | Historical moves | Small, separately reviewable **cohorts**. Links updated and validated after **every** cohort | not started |
| 4 | Legacy tests and scripts | Map the singular `test/` tree's coverage to current tests **before** moving it. Move only tools whose purpose and replacement are both named | not started |
| 5 | Tracked-byte reduction | Preserve and checksum research documents outside Git, then remove the tracked binaries. Remove the unused SIMD asset behind a focused gate. Remove empty `wsl`, the old result JSON, the duplicate cue candidate | not started |
| — | Verification checkpoint | §6 below | not started |

**Step 6 begins only after that checkpoint is accepted.**

---

## 4. Cohorts for step 3, in the order they should go

Proven historical or misplaced. Moving them changes navigation, not behaviour.

| Cohort | Files | Precondition |
|---|---:|---|
| Root dated artifacts — `HANDOFF_2026-07-01.md`, `HANDOFF_CODE_REVIEW_2026-08-12.md`, `PLAN_2026-07-13.md`, `clock_mockups_v1.html` | 4 | none |
| `docs/handoffs/` | 4 | none |
| `docs/drafts/` | 3 | none |
| `docs/mockups/` + `ui/mockups/` | 19 | none |
| `shadow/` — April DOCX design packets | 5 | confirm unreferenced |
| `docs/wo-qa/` | 11 | update the one `.env.example` rationale link **first** |
| **Root `WO-*` / `BUG-*` specs** | **30** | **every unresolved obligation already in `BACKLOG.md`** — §2 there covers 16 of the 30 |
| `docs/wo/` completed / superseded | — | per `docs/archive/INDEX.md` §4 destinations |

**Not in this step, and each belongs to exactly one:**

| Not here | Owned by |
|---|---|
| `docs/CHANGELOG-AGENT.md` | **Step 2b** |
| Singular `test/` tree — 9 files | **Step 4**, and only after coverage equivalence is mapped to current `tests/` |

*(Both appeared here **and** in their own step, so each was scheduled twice. A cohort table
that repeats a dedicated step is how two commits both believe they own a move, and how one
of them does it without the precondition the other recorded. Corrected 2026-08-28.)*

The root-spec cohort is **30, not the audit's 29** — `BUG-HARNESS-TEST23-INDENTATION-01`
was filed at `157af46`, and it is **open**, so it belongs in the backlog as unresolved
work rather than in a completed cohort.

---

## 5. Files that may leave the checkout after preservation — step 5 only

**Research binaries** — `docs/references/`, 16 files, 19,075,035 bytes. The repository's own
`docs/research/references.md` already says retained copies belong under gitignored
`docs/research/papers/`, with citations and links in Git. Copy to the operator's local
archive → verify SHA-256 against the current tree → keep citations, URLs, local-copy notes
and checksums in Git → remove the binaries in a separate reviewed commit. Copyright and
redistribution are an additional reason not to carry publisher PDFs in a source repository.

**Unused SIMD hold binary** — `ui/vendor/mediapipe/face_mesh/_simd_hold/face_mesh_solution_simd_wasm_bin.wasm`,
6,161,697 bytes. Production code explicitly redirects all SIMD asset requests to the
non-SIMD bundle and describes the held asset as unusable (`emotion.js` L348, a load-bearing
redirect). **Requires a focused asset-path test before removal** — this is the one step
that touches something the UI could reach.

**Small proven candidates** — empty root `wsl`; `server/code/test_model_results.json`;
`data/lori/narrative_cue_library.candidate_class_b_v1.json`, which is **the same Git blob**
as the promoted seed that code and tests actually read.

**This reduces the checkout, not Git history.** Every byte remains recoverable from the
tag.

---

## 6. Verification checkpoint

Run at the end, reported honestly:

* clean tree and cleared mutation journal;
* path and link validation across the whole tree;
* Python / shell / JavaScript syntax sweep — `bash -n`, `node --check`, byte-compile every
  tracked `.py`;
* current focused test suites, **with skip counts stated** — `OK` with skips is not a pass;
* current mutation gate status, stated with the interpreter it ran on;
* launcher paths verified;
* **no `server/` or live UI behaviour change**, except the separately gated unused-asset
  removal.

---

## 7. What "done" looks like

* One authoritative current-state table, in `HANDOFF.md`.
* One short ordered queue, in the checklist.
* `CLAUDE.md` carrying durable doctrine only.
* README describing the product and its operation, not a commit ledger.
* One archive ledger for completed work.
* Counts and heads **derived by command**, never transcribed into prose.

Retirement notes do not need repeating in every live control document. Git history and the
archive ledger preserve them more accurately than a paragraph that has to be maintained.
