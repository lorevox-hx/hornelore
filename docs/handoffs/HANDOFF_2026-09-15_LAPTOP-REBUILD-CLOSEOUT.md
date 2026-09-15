# Laptop rebuild — closeout

**Work order** `WO-LOREVOX-PORTABLE-NARRATOR-01`
**Date** 2026-09-15
**Repo** `/mnt/c/Users/chris/hornelore` at `786fc5d0386463b2cf9b8a38d5d6681d7a6be28f`
**Root** `/mnt/c/hornelore_data`, `hornelore.sqlite3`
**Procedure** `docs/handoffs/HANDOFF_2026-09-15_LAPTOP-REBUILD-RUNBOOK.md`

---

## Outcome: ACCEPTED

The laptop data root now holds exactly the three family narrators, restored from packages
exported from that same root hours earlier, and each one re-exports to a package
semantically equivalent to the one it came from.

| narrator | id | rows | files | round-trip |
|---|---|---:|---:|---|
| Christopher Todd Horne | `a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2` | 524 across 35 tables | 214 | **EQUIVALENT** `tables=60 rows=524 files=214` |
| Kent | `4aa0cc2b-1f27-433a-9152-203bb1f69a55` | 43 across 11 tables | 45 | **EQUIVALENT** `tables=60 rows=43 files=45` |
| Janice | `93479171-0b97-4072-bcf0-d44c7f9078ba` | 66 across 17 tables | 21 | **EQUIVALENT** `tables=60 rows=66 files=21` |
| | | | **280** | = `FILES_TOTAL` |

`family_root_verify.py`: `total: 3`, `--expect: 3 named, MATCHES`, all three `--expect-rows`
ticked, `foreign_key_check violations: 0`, three `complete` restore jobs.

**The acceptance contract was derived from the fresh export's own manifests**
(`$OUT/rebuild-contract.txt`), not typed from the historical 524/43/66/280. Those
historical numbers turned out to match, which is a useful coincidence and was not the test.

### Artifacts

| what | where |
|---|---|
| Full pre-erasure data root (local) | `/mnt/c/lorevox_preservation/laptop_20260915-103548/hornelore_data` |
| Full pre-erasure data root (USB) | `/mnt/d/Lorevox_Laptop_Preservation_20260915-103548/hornelore_data` |
| Authoritative packages + contract | `/mnt/d/Lorevox_Laptop_Fresh_20260915-105002` |
| Post-restore re-exports (proof only) | `/mnt/c/lorevox_packages/laptop-post-20260915-105002` |
| Pre-orphan-fix database copy | `/mnt/c/hornelore_data/db/hornelore.sqlite3.orphanfix-20260915-113135.bak` |
| Session state | `/mnt/c/lorevox_packages/laptop-rebuild-session.env` |

**Melanie Zollner was preserved as a package before erasure** at Chris's direction —
10 rows / 47 files, confirmed in the preservation verifier run. Del, Marvin Mann and mary
were disposable and are gone. 74 narrators were erased, 0 retried, 0 already gone.

**Do not delete the preservation copies or the USB packages yet.** Retirement is a
separate, deliberate step taken after the rebuilt root has been in real use.

---

## Two product defects, both latent, both found by doing it for real

Neither was reachable by any existing test. Both sit on the erase/restore path, which
nothing in normal operation exercises.

### 1 · `db.py:5746` — absolute import on the hard-delete path — **FIXED**

```diff
-    from api.services import narrator_data_inventory as _inv
+    from .services import narrator_data_inventory as _inv
```

The server runs as `code.api` (`python -m uvicorn code.api.main:app`), so there is no
top-level `api` package at runtime. Every one of the other eleven `services` imports in
that file is already relative (lines 27, 2375, 2439, 3875, 3987, 6166, 6410, 6555, 6791,
9544). This single absolute one worked in the CLI only because the CLI sets
`PYTHONPATH=server/code`.

Symptom: `DELETE /api/people/{id}?mode=hard` returned **HTTP 500, `No module named 'api'`**,
and rolled back. Hard erasure was impossible through the API and nothing had ever said so.

### 2 · `narrator_package.py:1392-1393` — restore's FK gate is table-scoped — **FILED, NOT FIXED**

`BUG-RESTORE-FK-GATE-TABLE-SCOPED-NOT-ROW-SCOPED-01`

```python
for table in inserted:      # only the tables this job wrote; pre-existing damage is not ours to judge
    bad += con.execute(f'PRAGMA foreign_key_check("{table}")').fetchall()
```

The comment states the correct rule. The code does not implement it: the pragma scans the
**whole table**, so pre-existing orphan rows in any table the package also writes fail the
job — pre-existing damage judged after all.

Here, six `harness-test-gate7p2-*` rows in `interview_sessions` (rowids 74–79) pointed at
`people` rows that no longer existed. They had survived the erasure precisely because they
belonged to no narrator. Every family package writes `interview_sessions`, so all three
restores failed identically.

**The failure was clean.** `_fail()` → `_cleanup_files()` unlinked every copied file and
all three jobs landed on `failed`, not `cleanup_required` — no residue, nothing half-done.
Correct rollback behaviour, confirmed under a real failure rather than a seam test.

Resolved operationally by `scripts/clear_orphan_interview_sessions.py`, which deletes only
rows orphaned by `person_id` and refuses if any of them is not recognisable test residue.
**That script is a workaround, not the fix.** A root carrying legitimate orphaned data
needs the gate corrected; deleting the data would be the wrong move there.

Suggested fix: compare the pragma's reported rowids against the rowids this job inserted,
and fail only on the intersection.

---

## Three pre-existing problems, deliberately not chased

Established by running `family_root_verify.py` against the **preservation copy** (74
narrators, pre-erasure) and against the live root after erasure:

| | preservation, pre-erasure | live, post-erasure | live, post-restore |
|---|---:|---:|---:|
| orphaned owners | 3 | 3 | **1** |
| FK violations | 6 | 6 | **0** |
| dangling references | 6 | 2 | **2** |

The erasure **created nothing** — orphans and FK violations were identical before and
after, and dangling references *fell* from 6 to 2. Everything the verifier reports today
is inherited debt, and the rebuild reduced it rather than adding to it.

What remains:

- `turn_extraction_ledger.narrator_id = '4e07e36f-93ec-4668-88bd-fea7730b9137'` — belongs
  to no narrator in this root.
- `turn_extraction_ledger.turn_key` = **1663** and **1665** → `turns.id`, no such parent
  row. Same family as the nine repaired on 2026-09-14; these are survivors of that set.
  SQLite cannot see them because no migration declares `REFERENCES turns` — only the
  semantic closure check finds them.

These are recorded, not fixed. They predate this work and nothing in the rebuild depends
on them.

### The three `failed` restore jobs stay in the ledger

`e3438e70…`, `f8ccad86…`, `bf113321…` are the first, blocked attempt. They are true
history and `family_root_verify.py` will flag them on every future run, because its rule is
"every restore job `complete`" and it has no concept of *superseded*.

**Leave them.** Deleting accurate history to turn a check green is the wrong instinct. The
gap is in the verifier — it should distinguish a failed job that was later succeeded by a
complete job for the same narrator and package — and is worth a small follow-up.

---

## Runbook changes made after execution

- **Correction 5** added to the corrections table.
- **Step 0 · Dependency preflight** — proves `bagit`, `narrator_package`,
  `narrator_data_inventory`, `narrator_merge` and both scripts load **before** step 13.
  `bagit` was missing from `.venv` on this run; it was caught at export, when nothing had
  been destroyed. The same discovery at step 15 would have stranded an empty root.
  `PREFLIGHT CLEAN` is now a precondition of erasure.
- **Step 14½ · Clear orphan rows** — the FK-gate blocker, with the script and the reasoning
  for why deleting those particular rows was right.
- **The preservation rule was rewritten.** It said the preservation drive and the package
  USB must be *different external devices*, with a hard stop if only one was available.
  Chris corrected that during execution — *"One external drive is enough. I made the safety
  rule stricter than it needed to be."* The rule is now **two independent physical-device
  recovery paths**: `C:` and `D:` each carried a full-root preservation copy *and* a package
  set, so either alone rebuilds everything. The old form was not merely over-strict, it
  described a layout this run did not produce, which would have left the runbook
  contradicting its own record.
- **Hard stop 13 no longer demands `CLEAN`.** It required the restore verification to print
  `MATCHES` / `CLEAN`; `CLEAN` is unreachable on a root with inherited debt, so as written
  it would have halted this successful rebuild. It now compares the verdict against what
  step 14½ recorded rather than against zero.

---

## Open, not blocking

`BUG-BIO-QUESTIONNAIRE-LOSSY-ROUNDTRIP-01` is live: a Bio Builder spouse/child save drops
`maidenName`, `birthPlace`, `notes` and `relation`. Unrelated to the rebuild, but it is in
the way of the actual work that follows.

## To commit

| file | state |
|---|---|
| `server/code/api/db.py` | modified — the one product fix |
| `scripts/clear_orphan_interview_sessions.py` | new |
| `docs/handoffs/HANDOFF_2026-09-15_LAPTOP-REBUILD-RUNBOOK.md` | modified |
| `docs/handoffs/HANDOFF_2026-09-15_LAPTOP-REBUILD-CLOSEOUT.md` | new |

Conclusions only — no database, no packages, no preservation copies, nothing under
`/mnt/c/lorevox_packages` or `/mnt/d`.
