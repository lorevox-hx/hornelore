# Verification addendum — repository archive audit, 2026-08-28

**Companion to:** [`HORNELORE_REPOSITORY_ARCHIVE_AUDIT_2026-08-28.md`](HORNELORE_REPOSITORY_ARCHIVE_AUDIT_2026-08-28.md)
**Audit's inspected baseline:** `ea3ab271b42e2151397b6ca7991125b5e9ea94d3`
**This addendum's baseline:** `d0e52946aa77096841612df176f4cbb70d4edacd`
**Written:** 2026-08-28, before any file was moved, renamed, archived or deleted

---

## 0. What this document is, and what it deliberately is not

The audit is recorded **verbatim**, byte-identical to the report as delivered
(`sha256 0ebce5ab7cf4620d03d930fae177c1eeed38a3004fdc35710fd8d54d8b4c181a`, 372 lines). **No
figure in it has been edited.**

That is a deliberate choice and it is worth stating why, because the alternative looks
tidier. A measurement is only evidence if you can tell *when* and *against what* it was
taken. Editing the audit's numbers to today's values would produce a document that agrees
with the current tree and can never again be checked against the tree it actually
described — the same defect this repository has corrected twice in its own control
documents, where a hard-coded "current `main`" hash was true on the day it was written
and misleading by the next commit.

So the original stands, and everything below is **dated, scoped, and reproducible**.

---

## 1. The three figures that did not reproduce, and what each one actually means

### 1.1 "SQL migration files: 50" — **the report was right; the wording is the only thing to sharpen**

```bash
git ls-tree -r --name-only d0e5294 | grep -c '\.sql$'                            # 51
git ls-tree -r --name-only d0e5294 | grep -c '^server/code/db/migrations/.*\.sql$' # 50
git ls-tree -r --name-only d0e5294 | grep -c '^server/schema/.*\.sql$'             # 1
```

**50 migration files is accurate.** 51 is the count of *all* tracked `.sql` files, and the
extra one is `server/schema/`, which is not a migration. Two different questions, two
correct answers. Nothing to correct in the report; this row exists so a future reader who
runs the obvious `grep -c '\.sql$'` and gets 51 does not think the audit was wrong.

### 1.2 "Commits across all refs: 1,280" — **correct at its snapshot; the number is time-sensitive by construction**

| Measurement | Value |
|---|---:|
| Audit's figure at `ea3ab27` | 1,280 |
| All refs, measured 2026-08-28 | 1,286 |
| Reachable from `d0e5294` | 1,279 |
| Reachable from `ea3ab27` | 1,276 |

Three commits landed after the audit (`157af46`, `34cdf54`, `d0e5294`), and the remaining
gap is ref scope: `--all` includes eight old remote branches carrying seven commits not
reachable from `main`.

**A later all-ref count does not disprove an earlier one.** This row is not a correction.
It records that "commits across all refs" is a moving measurement and must always be
quoted with its date and its ref scope, which the audit's own Appendix B commands do.

### 1.3 The per-month commit table — **qualified, not corrected**

The audit's monthly rows do not reproduce from any single command, because they mix two
ref scopes. Measured on **committer** date, 2026-08-28:

| Month | Audit | All refs | Reachable from `ea3ab27` |
|---|---:|---:|---:|
| 2026-04 | 347 | 347 | 347 |
| 2026-05 | 218 | 218 | 214 |
| 2026-06 | 108 | 108 | 108 |
| 2026-07 | 347 | 347 | 347 |
| 2026-08 | 260 | 264 | 260 |

April, June and July agree under both scopes. **May 218 matches `--all`; August 260
matches `ea3ab27`-only.** So the table is internally consistent (it sums to its stated
1,280) but is not the output of one command.

The audit used **committer** date, not author date — `git log --all --format=%ad`
returns May 220, and `%cd` returns 218. That is worth recording because the two differ
for real commits in this history, and a future reader reproducing the table with the
wrong flag will find a discrepancy that is not there.

**Disposition:** the table is qualified here rather than rewritten there. Its
conclusion — that development is concentrated in April and July with a sustained August
— is unaffected.

---

## 2. Everything that DID reproduce exactly at `ea3ab27`

Every one of these was re-derived from Git, not read across from the report.

| Measure | Audit | Re-derived at `ea3ab27` |
|---|---:|---:|
| Tracked files | 1,196 | **1,196** |
| Tracked bytes | 59,882,663 | **59,882,663** |
| Markdown files | 281 | **281** |
| Python files | 549 | **549** |
| JavaScript files | 117 | **117** |
| `docs/archive/` | 130 files, 2,097,967 bytes | **130 / 2,097,967** |
| `docs/archive/workorders-pre-pivot/` | 113 | **113** |
| `docs/archive/handoffs-pre-pivot/` | 16 | **16** |
| `docs/wo/` | 51 files, 1,142,222 bytes | **51 / 1,142,222** |
| Root work-order/bug specs | 29 files, 175,358 bytes | **29 / 175,358** |
| `scripts/` outside its archive | 95 files, 1,923,367 bytes | **95 / 1,923,367** |
| `scripts/archive/` | 32 files, 577,047 bytes | **32 / 577,047** |
| Main `tests/` tree | 295 | **295** |
| `docs/references/` | 16 files, 19,075,035 bytes | **16 / 19,075,035** |
| Held SIMD wasm | 6,161,697 bytes | **6,161,697** |
| References + SIMD | 25,236,732 | **25,236,732** |
| `docs/CHANGELOG-AGENT.md` | 614,130 bytes | **614,130** |
| Tags | none | **0** |
| Remote branches besides `main` | 8 | **8** |
| — of those, ancestors of `main` | 7 | **7** |
| `sad-ramanujan` unique commits, all `-` under `git cherry` | 4 | **4** |

Also confirmed:

* **`CLAUDE.md` says 114 pre-pivot work orders; Git derives 113.** The audit flagged this
  and it is real. Recorded in `docs/BACKLOG.md` for the control-document simplification
  commit — not fixed here, because this commit adds indexes and changes nothing else.
* `data/lori/narrative_cue_library.candidate_class_b_v1.json` is **the same Git blob** as
  the promoted `narrative_cue_library.v1.seed.json` — not merely equal in size.
* Root `wsl` is **0 bytes**; `server/code/test_model_results.json` is 4,225 bytes.
* `scripts/ui/run_test23_two_person_resume.py` is **the only Python parse failure** in the
  tracked tree — `IndentationError` at line 2082. Confirmed by byte-compiling every
  tracked `.py`.
* Every §11 tooling defect reproduced: `package.json` `main` names a nonexistent
  `tailwind.config.js`; its `license` says `ISC` while `LICENSE` is the Lorevox
  Source-Available Proprietary License; **7 npm script entries reference 4 distinct
  nonexistent Playwright specs**; `playwright.config.ts` invokes a nonexistent
  `scripts/start-lorevox-audit.sh`.

  *(The audit says "five npm scripts". Measured: seven entries — `test:break`,
  `test:break:headed`, `test:timeline`, `test:memory`, `test:projection`, `test:q3`,
  `test:q3:headed` — naming four missing spec files. The defect is the audit's; only the
  count is sharpened.)*

---

## 3. Re-derived at `d0e5294`, which is the tree the hygiene work actually starts from

```bash
git rev-parse origin/main            # d0e52946aa77096841612df176f4cbb70d4edacd
git status --porcelain               # empty
git ls-tree -r --name-only d0e5294 | wc -l
git ls-tree -r -l d0e5294 | awk '{s+=$4} END{print s}'
```

| Measure | `ea3ab27` (audited) | `d0e5294` (now) | Δ |
|---|---:|---:|---:|
| Tracked files | 1,196 | **1,200** | +4 |
| Tracked bytes | 59,882,663 | **60,013,341** | +130,678 |
| Markdown | 281 | **282** | +1 |
| Python | 549 | **552** | +3 |
| JavaScript | 117 | **117** | 0 |
| SQL (total / migrations) | 51 / 50 | **51 / 50** | 0 |
| `docs/archive/` | 130 | **130** | 0 |
| `docs/wo/` | 51 | **51** | 0 |
| **Root WO/BUG specs** | 29 | **30** | **+1** |
| `scripts/` non-archive | 95 | **95** | 0 |
| `scripts/archive/` | 32 | **32** | 0 |
| `tests/` | 295 | **297** | +2 |
| Commits reachable | 1,276 | **1,279** | +3 |

### The +1 root specification, named

`BUG-HARNESS-TEST23-INDENTATION-01_Spec.md` — filed at `157af46` for the Test 23
`IndentationError` the audit itself found. **It was written deliberately rather than
repaired in place**, so an unrelated UI-harness fix would not ride inside a Profile Seed
correction commit.

**Consequence for the archive plan:** Appendix A of the audit lists 29 root
specifications. There are now **30**, and the thirtieth is *open, bounded and unscheduled*
— so when the root specs are archived it belongs in `docs/BACKLOG.md` as unresolved work,
not in a completed cohort. Appendix A is not edited; this paragraph is the amendment.

### The +4 files and +2 tests, named

| File | Commit |
|---|---|
| `BUG-HARNESS-TEST23-INDENTATION-01_Spec.md` | `157af46` |
| `server/code/api/services/conversation_control.py` | `157af46` |
| `tests/test_profile_seed_deterministic_paths.py` | `157af46` |
| `tests/test_profile_seed_expected_version_strict.py` | `157af46` |

---

## 4. The audit's §6 is now HISTORICAL and is superseded by this section

§6 of the report — "Pre-Step-6 product obligations that cleanup must not erase" — lists
five corrections as **owed**. That was true at `ea3ab27`. **All five are closed and
accepted at `d0e5294`.** Reading §6 as a live work list would rebuild finished work, which
is the exact failure `CLAUDE.md` records twice in its own history.

| § 6 item | State at `d0e5294` |
|---|---|
| 1. Repair mutation instruments `M1` and `M8` | **Accepted.** `M1` returned the defective ACKNOWLEDGE plan instead of crashing; `M8` gained a conflict-once recorder so the illicit second apply is observable. Both fail by assertion |
| 2. Strict-integer `expected_version` at API and database | **Accepted.** `StrictInt` on the request model, an explicit type check in `db.profile_seed_apply`, 22 tests, mutation `P11` |
| 3. Transport map from six to nine deterministic paths | **Accepted.** §6 of the map rewritten; `floor_buffer`, `past_tense_acknowledge`, `bank_flush` each guarded; mutations `D1`–`D4` |
| 4. Hold/suppression for control and system-directive turns | **Accepted.** `HOLD` action; one shared detector in `services/conversation_control.py`; mutations `H1`–`H7` |
| 5. Stop hard-coding "current `main`" in `HANDOFF.md` | **Accepted.** Replaced with `git rev-parse origin/main`; `9127adb` retained as a fixed acceptance checkpoint |

Two **acceptance-instrument** defects were then found reviewing that work and are also
closed, at `34cdf54` and `d0e5294`: the strict-version suite's route-stack guard (it
checked `pydantic` and not `fastapi`, then still caught bare `ImportError` in the outer
sweep), and the deterministic inventory's duplicate collapse (a dict keyed by `turn_mode`
counted distinct modes while claiming to count paths).

**Acceptance evidence at `d0e5294`:** full clean-tree gate at `34cdf54` 63/63 caught with
all nine baselines green; targeted gate at `d0e5294` `P11` + `D4` 2/2; focused tests 65
`OK` with five expected FastAPI skips under generic Python; `.venv-gpu` 22/22 zero skips;
`.venv` 22/22 zero skips; truthful shipped-design count **24**; tree clean; journal clear.

---

## 5. Two verification-posture findings, recorded and NOT acted on

Both surfaced while producing the evidence above. Neither is repaired here — this commit
adds indexes and changes nothing else — and both are in `docs/BACKLOG.md`.

1. **`CLAUDE.md`'s Environment bullet is stale about `.venv`.** It asserts, measured
   2026-08-20, that `.venv` is Python 3.10.12 with **no fastapi**, and that route tests
   skip there silently while `unittest` still prints `OK`. On 2026-08-28 `.venv` ran the
   strict suite **22/22 with zero skips**, which is only possible if `fastapi` imports.
   The bullet whose whole purpose is warning that "`OK` with skips is not a pass" is
   itself now inaccurate.

2. **The mutation gate runs on the interpreter least able to exercise route tests.** Its
   documented command is `python3`; on that interpreter the strict suite reports
   `22 ran, 5 SKIPPED` and `tests.test_profile_seed_rest_read_authority` reports
   `48 ran, 6 SKIPPED`. The `S`-series mutations target `api.py` and
   `profile_seed_rest.py`. `P11` is unaffected — it mutates the accessor, and all
   accessor and guard tests ran — but whether the gate should now run under `.venv` is a
   real question, and it is the same class of defect this checkpoint spent two rounds
   correcting.

---

## 6. Reproduction

```bash
cd /mnt/c/Users/chris/hornelore
git rev-parse origin/main
git status --short --branch
git ls-tree -r --name-only d0e5294 | wc -l
git ls-tree -r -l d0e5294 | awk '{s+=$4} END{print s}'
git rev-list --count d0e5294
git rev-list --all --count
git log --all --format=%cd --date=format:%Y-%m | sort | uniq -c
git ls-tree -r --name-only d0e5294 | grep -cE '^(WO-|BUG-)[^/]*\.md$'
git diff --stat ea3ab27..d0e5294
```

Appendix B of the audit remains the reproduction for its own `ea3ab27` figures; run those
against `ea3ab27` explicitly, not against `HEAD`.
