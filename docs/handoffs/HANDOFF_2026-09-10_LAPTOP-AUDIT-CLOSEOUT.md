# Laptop audit CLOSEOUT — WO-LOREVOX-PORTABLE-NARRATOR-01, Phase 1 → Phase 2

**Written 2026-09-10 on the laptop at `9ed7ad9`.** Supersedes the forward-looking
parts of `HANDOFF_2026-09-10_LAPTOP-NARRATOR-AUDIT.md`, which was written on the
desktop at `500d112` and expected `500d112` in its Step 1. That expectation is
stale; the laptop pulled to `9ed7ad9`.

**Everything below is read-only evidence.** No laptop narrator data was created,
modified, moved or deleted. Six report directories under `.runtime/eval/`
(gitignored) hold the detail.

---

## 1. Verdict

**STATUS: LAPTOP AUDIT CLOSED.** No further laptop database comparison is required.
Next work is report transfer and Phase 2 exporter implementation on the desktop.

**The laptop live root is the authoritative narrator source.** The desktop has no
travel data for any real narrator; the laptop has all of it.

**No narrator conversation content was found lost from the genuine laptop backups**
(§6.3). Attribution of pre-0044 conversations remains unavailable; row loss does not.

**Do not overwrite laptop data with desktop data. Do not merge the databases by
hand.** The exporter is the only sanctioned path.

---

## 2. Authoritative root

| | |
|---|---|
| `.env` `DATA_DIR` | `/mnt/c/hornelore_data` |
| `.env` `DB_NAME` | `hornelore.sqlite3` |
| Live DB | `/mnt/c/hornelore_data/db/hornelore.sqlite3` |
| Narrator | `a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2` — Christopher Todd Horne |

The WSL profile exports **nothing** (`exported: DATA_DIR= DB_NAME=`), so `.env` is
unambiguously authoritative here. The desktop's stale-export trap does not apply.

`/home/chris/lorevox_data/` exists as a March-era directory shell but its `db/` is
**empty** — no database, nothing to audit. `C:\lorevox_data\db\lorevox.sqlite3`
(April 8, 347 people, 25 tables) has no trip lane at all.

---

## 3. Audits completed — all `read-only: PROVEN`

Each opened `mode=ro`, set `PRAGMA query_only`, and **refused to proceed unless
SQLite rejected `BEGIN IMMEDIATE`**. Read-only is proven by the engine, not asserted.

* `phase0-ownership-audit-laptop-live-20260910T131717Z`
* `phase0-ownership-audit-laptop-backup-pre-christopher-wipe-0725-20260910T131734Z`
* `phase0-ownership-audit-laptop-backup-0037-0725-20260910T132010Z`
* `phase0-ownership-audit-laptop-backup-0730-20260910T131751Z`
* `phase0-ownership-audit-laptop-lorevox-root-20260910T131809Z`
* `phase0-christopher-id-comparison-20260910T151145Z` — **authoritative**

An earlier comparison run, `phase0-christopher-id-comparison-20260910T145015Z`, is
**SUPERSEDED**. Its coverage line was defective (it counted only live-side failures
and therefore read `0`) and it mislabelled schema-era table absence as
`"no stable primary key"`. Do not quote it.

**`hornelore_evalcopy.sqlite3` is not a backup.** It is a divergent working copy
(fork), and is never a recovery source. See §6.3.

---

## 4. Travel data — FOUND on the laptop

Christopher's trip lane in the **live** DB:

| lane | rows |
|---|---|
| `trips` | 2 |
| `trip_regions` | 7 |
| `trip_stops` | 21 |
| `trip_days` | 39 |
| `trip_themes` | 7 |
| `trip_location_notes` | 24 |
| `trip_bio_suggestions` | 2 |
| `trip_public_context` | 12 |
| `trip_photo_links` | 40 |
| `trip_photo_context` | 51 |
| `trip_photo_day_placements` | 3 |
| `trip_photo_day_placement_skips` | 0 |
| `trip_turn_links` | 20 |
| `trip_sources` | **0** |
| permanent photos | 27 |
| `interview_sessions` | 43 |

The two trips:

1. `e4a7a5aa-82e0-4d20-b8df-b8996f37ffd7` — **Spring 2026 Central Europe &
   Northern Italy**, 2026-05-12 → 06-13. `live_state: planning`.
2. `9538cd88-5c8b-4da4-b2a9-2a03f8db32a3` — **Bismarck Trip**, 2026-07-14 → 07-19.
   `live_state: active`.

Desktop Christopher, for contrast: 3 sessions, 26 turns, 7 threads, 16 bio facts,
4 photos, **zero trips**.

**Open question for Chris, not an agent's to settle:** trip 1 carries
`source_document: "WO-TRIP-MEMOIR-01 canonical test case"`. The content is real and
personal. Decide whether that provenance string travels with the package.

---

## 5. The Christopher wipe did NOT take the travel work

Both trips are present in every inspected database — both July 25 backups, the
July 30 backup, the eval copy, and live. The itinerary skeleton is **identical
across all five**: `trips` 2, `trip_regions` 7, `trip_stops` 21, `trip_days` 39,
`trip_themes` 7, `trip_public_context` 12.

What accrued afterward is the annotation layer:

| snapshot | notes | photo_links | turn_links | placements |
|---|---|---|---|---|
| pre-wipe · Jul 25 20:55 | 11 | 13 | *(table absent)* | *(table absent)* |
| pre_0037 · Jul 25 21:07 | 11 | 13 | *(table absent)* | *(table absent)* |
| pre_0039 · Jul 30 11:53 | 12 | 15 | *(table absent)* | *(table absent)* |
| evalcopy · Jul 31 22:41 | 18 | 16 | 8 | *(table absent)* |
| **live · Sep 8** | **24** | **40** | **20** | **3** |

A narrator deletion did occur between the two July 25 backups — `people` 37 → 36
and the whole-table `photos` count 22 → 16. **Christopher's trip lane is identical
on both sides of that 12-minute window.** Whoever the wipe named, it did not touch
his travel work.

---

## 6. Identity comparison — verdict and its exact scope

`phase0-christopher-id-comparison-20260910T151145Z`, driven by
`narrator_data_inventory.py` ownership selectors across 60 narrator-owned lanes.

### 6.1 Verdict

> **Live is a complete superset across all narrator-owned lanes that could be
> identity-compared. No backup-only Christopher IDs were found. Historical
> `sessions`/`turns` cannot be ownership-compared because the backups predate
> `sessions.person_id`.**

This is an identity comparison. It is **not** inferred from row counts.

### 6.2 Coverage — honest, per pair

| pair | ownership-compared | not |
|---|---|---|
| `backup_pre_christopher_wipe_0725` | 52 of 60 | 8 |
| `backup_pre_0037_0725` | 52 of 60 | 8 |
| `backup_pre_0039_0730` | 53 of 60 | 7 |
| `hornelore_evalcopy` | 55 of 60 | 5 |

Two distinct reasons, never conflated:

* **`ownership_path_absent` (2 lanes):** `sessions`, `turns` — `sessions.person_id`
  was added by ALTER in migration 0044 (`narrator_data_inventory.py:116`), so
  July-era files carry no ownership path for conversations.
* **`table_absent`:** `profile_seed_onboarding`, `turn_extraction_ledger` (pre-0730),
  `turn_extraction_results`, `trip_photo_day_placements` (0043),
  `trip_photo_day_placement_skips`, `trip_turn_links` (0039). **The feature did not
  exist yet.** This is a schema-era limitation, not discovered backup-only data.

### 6.3 Unscoped containment — the conversations gap, closed

Ownership cannot be established for old `sessions`/`turns`, but **id containment
can**, irrespective of owner. If every backup id also exists in live, no row was
lost — whoever owned it.

| pair | `sessions` | `turns` |
|---|---|---|
| pre_christopher_wipe | all 498 present in live | all 1391 present |
| pre_0037 | all 498 present in live | all 1391 present |
| pre_0039 | all 566 present in live | all 1411 present |
| `hornelore_evalcopy` | **4 of 632 absent** | all 1541 present |

**All three genuine backups are fully contained. No conversation was lost.**

The 4 eval-copy exclusives were investigated and are **resolved as fork artifacts**:

* Directionality: eval copy holds **632** sessions, live holds **1,013**;
  eval-only **4**, live-only **385**. Both directions non-zero proves divergence —
  the eval copy is a fork, not an ancestor of live.
* All four are empty shells — `title` blank, `payload_json` `{}`, **zero turns** —
  created 2026-08-01 03:39–04:40, after the fork.
* They contain no narrator content of any kind, so attribution is moot.

**Therefore: no data is missing from live.** What remains unprovable is narrower
than it first appeared — not "a conversation might be missing", but "conversations
in pre-0044 files cannot be attributed to a specific narrator from those files
alone." Every such row is still present in live.

### 6.4 Same-id changes — ordinary editing, one design consequence

`trip_days` prose (`title`, `main_location`, `morning_notes`, `afternoon_notes`,
`lodging_base`), `trip_location_notes.note_text`, `trip_photo_links.caption`,
`trips.live_state` / `active_trip_day_id`, `interview_projections.projection_json`,
`interview_sessions.turn_count`, `trip_turn_links.placement_source`.

**Design consequence:** `trip_photo_links` shows `trip_day_id`,
`assignment_method` and `cluster_confidence` changing on existing rows. Photo-to-day
placement is **mutable**. A round-trip test must compare placements by current value
and must not assume a photo stays on the day it was first assigned.

---

## 7. `trip_sources` — no real travel documents exist

Zero `trip_sources` rows in all five databases. Three orphan directories on disk
contain only:

```
6b99468c…/p3c_smoke_source.txt   323 B   Jul 24 21:37
699d5188…/p4-smoke-source.txt     31 B   Jul 25 10:38
06c38d6c…/p6-smoke-source.txt     79 B   Jul 25 17:32
```

433 bytes total; `du -sh` reports `0`. Phase smoke-test fixtures. **There are no
persisted travel-source documents to recover.** The travel work is the structured
trip rows, photos, context, placements and narration links — not documents.

---

## 8. Photo and staged-byte integrity — GOOD

* Christopher permanent photos: **27**. Missing originals: **0**. Missing
  thumbnails: **0**.
* Paths are absolute under `/mnt/c/hornelore_data/memory/archive/photos/…`.
  **Restore path rewriting (WO §8.5) is required.**

### Live Google Photos batch `8b5b47cb-4298-43fc-8ea6-827a5916e460`

`google_photos_picker`, status `open`, `trip_id` = Bismarck Trip, staging present.
7 candidates: 5 `pending`, 2 `accepted`.

**All 5 pending candidates have exactly one non-empty `original.jpg` in staging and
their computed SHA-256 equals `import_candidate.file_hash` — verified byte-for-byte.**
Both accepted candidates have intact permanent archive files with agreeing hashes.

**These staged bytes must travel with the package.** They are the verified source
for unresolved candidates.

### Historical residue — preserve, do not repair

| batch | status | staging | disposition |
|---|---|---|---|
| `ad12488e…` | closed | absent | **residue** — see below |
| `cdb00d5d…` | closed | absent | rejected candidate; no staged source needed |
| `2d7e559d…` | closed | absent | accepted; permanent photo exists |
| `202718fb…` | open | absent | zero candidates; no bytes implicated |

Batch `ad12488e-0ca3-4fd2-aef2-99665bb19b08` retains one `pending` candidate
`1e235ee8-1d49-475f-a640-433ed4b3632c` with `file_hash=smokehash02` and no staging.

**`smokehash02` is 11 characters. A SHA-256 is 64.** The value cannot be a real
digest, so this classifies as test residue on the shape of the data itself — not on
the name merely looking test-ish. The exporter can make that determination
mechanically.

**Do not repair, synthesize or delete this row.** The package preserves the DB
record and reports:

> unresolved import candidate; no verified staged source available

That is correct behaviour. Inventing bytes, or silently dropping history, is not.

---

## 9. Phase 2 acceptance case

The portable narrator implementation must carry, without inventing missing bytes:

1. Two trips and every trip child — 7 regions, 21 stops, 39 days, 7 themes,
   24 location notes, 12 public-context rows, 40 photo links, 51 photo contexts,
   3 day placements, 20 turn links.
2. 27 permanent photos with originals and thumbnails, **absolute paths rewritten**.
3. The 5 unresolved staged Google Photos originals with SHA-256 preserved and
   re-verifiable after restore.
4. Conversations, interviews (43 sessions), structured memory, bio / family truth /
   timeline, extraction ledger, provenance.
5. The historical smoke residue — **preserved and honestly reported**, not repaired.

Round-trip acceptance must compare **mutable placement by value** (§6) and must
re-verify staged hashes rather than trusting the manifest.

---

## 10. Next steps

1. Copy the six `.runtime/eval/` report directories to the desktop's
   `.runtime/eval/` — the five ownership audits plus
   `phase0-christopher-id-comparison-20260910T151145Z`. **Reports only — not the
   database, not `hornelore_data`, not audio, not `.env`.** They stay gitignored on
   both machines. The superseded `…-145015Z` run need not travel; if it does, it
   must carry its SUPERSEDED status with it.
2. Desktop: write the read-only Desktop↔Laptop comparator over the JSONs.
3. Build the Phase 2 `.lorevox.zip` BagIt exporter and prove it on synthetic Ada
   **on the desktop**.
4. Only after export/restore is proven synthetically, push the code to the laptop
   and export the real **Christopher, Kent and Janice** packages there.
5. Restore each package into a clean desktop root, re-export, and compare semantic
   DB state plus payload hashes (Phases 3–4).
6. **No laptop deletion** until *each* real narrator package has restored and
   independently verified. Deletion is last, not first.

### Smoke-residue decision — DECIDED 2026-09-10

> **PRESERVE + WARN. Do not clean it first.**

The four smoke-test import batches in Christopher's real narrator data travel with
the package exactly as historical residue. The unresolved candidate
`1e235ee8-1d49-475f-a640-433ed4b3632c` (`file_hash=smokehash02`, no staging) is
preserved as a DB record and reported as:

> unresolved import candidate; no verified staged source available

**Rationale:** cleaning first would be a write to real narrator data undertaken only
to make the acceptance case tidier. That would weaken the very thing Phase 2 exists
to prove. Phase 2 stays purely about proving portability.

**This decision is closed.** Do not reopen it as a side effect of exporter work, and
do not delete, repair, or synthesise bytes for this row.

---

## 11. Standing constraints

* Agents do not run git. Blocks are copy-paste; Chris runs them; every block starts
  with `cd /mnt/c/Users/chris/hornelore`.
* No `git add -A`; nothing staged under `.runtime/` or `docs/reports/`.
* Audits run **stack down**.
* No copying narrator data between machines. No deletions.
* Audit commands are copied from the source file, never regenerated from memory.
  Flags are `--db`, `--data-root`, `--label`, optional `--out`, optional `--repo`.
