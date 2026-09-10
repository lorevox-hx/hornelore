# Laptop handoff — narrator data audit (WO-LOREVOX-PORTABLE-NARRATOR-01, between Phase 1 and Phase 2)

**Written 2026-09-10 on the desktop at `500d112`. Read this on the laptop. Every block
is copy-paste; run them in order; paste every console output back into the desktop
session (or ChatGPT) when done.**

## Why you are doing this

Phase 1 is landed and pushed (`9fc94ff` … `500d112`). The desktop has now been fully
audited, read-only, and **no real narrator on the desktop has ever had a trip row** —
not in the live DB, not in the July 23 backups (their one `trips` row belongs to the
placeholder id `PASTE_UU`), and `C:\lorevox_data` is an April root still to be
confirmed. Chris believes the travel work — trips, `trip_sources` documents, photo
placements — was done **on the laptop**. This handoff measures that.

**Nothing in this handoff changes laptop data.** The exporter that will bag it does not
exist yet (Phase 2); deleting anything comes only after a package has been restored and
verified on the desktop (Phase 7). Today is inventory.

## Desktop — fully audited 2026-09-10 (six reports under `.runtime/eval/`, all read-only PROVEN)

| root | audit label | trips | Chris |
|---|---|---|---|
| `C:\hornelore_data` (live) | `desktop-live-20260910T124545Z` | 0 | `a4b2f07a`: 3 sessions / 26 turns / 7 threads / 16 bio_facts / 4 photos / 1 import batch |
| `db/backup_real_pre_0035_20260723_080119` | `desktop-backup-0723-…` | 1 = `PASTE_UU` (placeholder, not a narrator) | subset of live |
| `C:\lorevox_data` (April 27) | `desktop-lorevox-root-0427-…` | no `trips` table | not present; 343 people incl. duplicate Kent/Janice/Christopher ids; 4768 turns with no `person_id` |
| `E:\ai\data\lorevox_data` (`/home/chris/lorevox_data` symlinks here) | `desktop-e-drive-live-…` | 0 | January ids `2a5b9286` / `efe51d9b` / `ac2204d6` with 10 interview answers; plus yesterday's stray Ada `85f52c6e` and a `4aa0cc2b (harness-pinned)` row |
| E: `lorevox.sqlite3.bak_20260215_082200` | `desktop-e-drive-bak-0215-…` | — | 13 tables, 4 people, January era |

**Conclusion: no real narrator has a trip or a travel document anywhere on the desktop.**
If the travel work exists, it is on the laptop.

## Rules that still apply on the laptop

* Do **not** copy desktop data over the laptop, and do not copy laptop data anywhere yet.
* Do **not** `git add` anything under `.runtime/`, `docs/reports/`, `.env`, narrator
  data, or the audit output. The audit writes only under `.runtime/eval/`, which is
  gitignored, and refuses any other destination.
* Chris starts and stops the stack. The audit runs **stack down**.
* Every block starts with `cd /mnt/c/Users/chris/hornelore`.

## Step 1 — bring the code to the pushed commit (code only)

```bash
cd /mnt/c/Users/chris/hornelore
git status --short
git pull
git log --oneline -1
```

Expected last line: `500d112 handoff: next-session queue for the two-machine narrator audit`.
If `git status --short` printed anything **before** the pull, stop and paste it — the
laptop has uncommitted work and pulling on top of it is how it gets lost.

## Step 2 — find the laptop's real data root (do not assume the desktop's)

```bash
cd /mnt/c/Users/chris/hornelore
grep -E '^(DATA_DIR|DB_NAME|AUTHORS_DIR|KNOWLEDGE_DIR|UPLOADS_DIR|MEDIA_DIR)=' .env
echo "exported: DATA_DIR=$DATA_DIR DB_NAME=$DB_NAME"
```

`.env` wins for the server (`scripts/common.sh:26-29` sources it under `set -a`). The
`exported:` line shows whether the WSL profile carries a stale export like the desktop
did (`/home/chris/lorevox_data`). **Use the `.env` values below**, not the export.

Then list every root and DB file the laptop has:

```bash
cd /mnt/c/Users/chris/hornelore
ls -la /mnt/c/hornelore_data/db/ 2>&1
ls -la /mnt/c/lorevox_data/db/ 2>&1
ls -la /home/chris/lorevox_data 2>&1
ls -la /mnt/c/hornelore_data/trip_sources 2>&1 | head
ls /mnt/c/hornelore_data 2>&1
```

## Step 3 — look at Chris's narrator in the UI (human check, not evidence)

Start the stack your usual way. Open Hornelore, select **Christopher Todd Horne**, and
write down what is visible for: conversations / interviews · stories · Bio / Family Truth /
Life Map · photos · **trips and travel documents** · media / documents · saved narrator
audio · memoir / review. Especially: **how many trips, and do the travel documents open?**

Then **stop the stack**. The next step needs it down.

## Step 4 — the audit, against the `.env` root

Replace the two placeholders with the values `grep` printed in Step 2. If `.env` says
`DATA_DIR=/mnt/c/hornelore_data` and `DB_NAME=hornelore.sqlite3`, the block is exactly:

```bash
cd /mnt/c/Users/chris/hornelore
python3 scripts/phase0_narrator_ownership_audit.py \
  --db /mnt/c/hornelore_data/db/hornelore.sqlite3 \
  --data-root /mnt/c/hornelore_data --label laptop-live
ls -d .runtime/eval/phase0-ownership-audit-laptop-*
```

It prints `wrote …/ownership-audit.md`, one summary line (`tables=… people=…
dynamic_lane_refs=…`), and `read-only: PROVEN`. **If it does not say PROVEN it did not
run; paste the error.**

If Step 2 showed backup files under `db/` (`*.bak`, `backup_*.sqlite3`), audit the
newest one too, same `--data-root`, with `--label laptop-backup-<date>`.

If `C:\lorevox_data` exists on the laptop with a `db/lorevox.sqlite3`, audit it as well:

```bash
cd /mnt/c/Users/chris/hornelore
python3 scripts/phase0_narrator_ownership_audit.py \
  --db /mnt/c/lorevox_data/db/lorevox.sqlite3 \
  --data-root /mnt/c/lorevox_data --label laptop-lorevox-root
```

## Step 5 — what to read before leaving the laptop

Open the report (`.runtime/eval/phase0-ownership-audit-laptop-live-<ts>/ownership-audit.md`)
and paste these sections back:

1. The header (machine, label, commit, database, data root).
2. `## Per-narrator row counts` → the `Christopher Todd Horne` block, and Kent's and
   Janice's.
3. The `trips`, `trip_sources`, `trip_days`, `trip_photo_links`,
   `trip_photo_day_placements`, `photos`, `import_batch` rows of the ownership matrix
   (the row counts are the second column).
4. `## Dynamic lanes` — the `trip_sources` table: **every row must show `dir exists =
   True` with a non-zero file count.** A row with `False` is a document the DB
   remembers and the disk has lost; that has to be known before anything is bagged.
5. `## Path-like columns` — whether `photos.image_path` and `trip_sources.storage_path`
   are absolute (`/mnt/c/…`) or relative. Absolute paths are rewritten on Restore
   (WO §8.5); we need to know which.

## Step 6 — bring the report to the desktop

Copy the whole folder `.runtime/eval/phase0-ownership-audit-laptop-live-<ts>/` (and any
`laptop-backup-*` / `laptop-lorevox-root-*` folders) to the desktop's
`C:\Users\chris\hornelore\.runtime\eval\` — same route as the `Desktop\Horne` transfer.
It is counts and paths, not narrator files, and it stays gitignored on both machines.
**Do not copy the database, `hornelore_data`, audio, or `.env`.**

## What happens next on the desktop

The agent writes a read-only comparator over the desktop and laptop JSONs: per narrator,
per lane, Desktop / Laptop / Backup columns, flagging what exists on only one side. Then
Phase 2 (the exporter) is built and proven on synthetic Ada on the desktop; then Chris's
narrator is exported **on the laptop**, restored into a clean root on the desktop,
re-exported and hash-compared (Phases 3–4). Deletion from the laptop is the last step, not
the first.

## If ChatGPT is helping from the web

Give it this file and the pasted outputs. Constraints it must respect: no `git add -A`, no
staging under `.runtime/` or `docs/reports/`, no `start_all.sh`/`stop_all.sh` in blocks,
no copying narrator data between machines, no deleting anything, and audit commands are
copied from this file — not regenerated from memory (the script's flags are `--db`,
`--data-root`, `--label`, optional `--out`).
