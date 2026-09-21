# Pre-shutdown handoff — 2026-09-20

Recorded with the stack **still running**, before any stop. Every figure
below is measured, not inferred from configuration.

## 1. Which database the running process is actually using

Not read from `.env`. Read from what the process itself logged when it
started:

```
.runtime/logs/api.log
2026-09-20 17:47:38,208 [code.api.db] INFO: Lorevox DB: /mnt/c/hornelore_data/db/hornelore.sqlite3
```

`[launcher] DATA_DIR=/mnt/c/hornelore_data` on the same startup.

That agrees with the configured path — `.env:53` `DATA_DIR=/mnt/c/hornelore_data`,
`.env:56` `DB_NAME=hornelore.sqlite3`, composed by `db.py` as
`DATA_DIR/db/DB_NAME` — but the agreement is the finding, not the
source. A config file can be edited after a process starts.

**Current process started 17:47:38.** The file's mtime is 19:23, which
is the last write, not a restart.

## 2. State of that database, now

```
journal_mode      wal            <- matters for the backup; see §5
integrity_check   ok
foreign_key_check 0 violations
migrations        0062_accept_mode, 0061_suggestion_flags,
                  0060_suggestion_reviews, 0059_answer_provenance

people                          4
bio_builder_questionnaires      4
bio_builder_answer_provenance   4
interview_projections           4
suggestion_reviews             12      all ZZ WALKTHROUGH
suggestion_flags                0      nothing seeded
turns                        1487
sessions                      951
queued suggestions             31      30 legacy + 1 ZZ probe
```

Saved biographies:

| narrator | size | revision |
|---|---|---|
| Christopher Todd Horne | 10417 bytes | 1 |
| Janice | 9114 bytes | 0 |
| Kent | 8225 bytes | 0 |
| ZZ WALKTHROUGH 20260917 | 1287 bytes | 10 |

These numbers are the comparison point. After the restart they should be
identical except where an approved operation deliberately changed
something.

## 3. What has been done to this database during development

Nothing. Every verification ran on synthetic narrators or on a snapshot;
the live file was opened `mode=ro` or through SQLite's backup API. No
backfill, no flag seeding, no UI use.

Migrations 0059–0062 DID apply to it, and not by anyone's decision at
the time: `init_db()` runs pending migrations on nearly every DB call,
so each landed as soon as its file existed. That is worth knowing before
the next migration is written. All four are additive — three new tables
and one new column — and `integrity_check` is clean.

## 4. Is the pushed work ready for the transition

The code is pushed and reviewed in two batches: the queue-integrity
repair, and the questionnaire-to-Lori read path. Focused suites and the
acceptance scripts pass.

**What that does NOT establish**, and should be said plainly before the
stack goes down:

- **Nothing has been exercised through a browser.** Every result comes
  from Python and jsdom. The review UI's new controls, and the
  biography reaching Lori in a real conversation, have not been seen by
  a person.
- **The live walkthrough named in WO-QUESTIONNAIRE-REACHES-LORI-01 as
  its own acceptance** — enter a parent, restart, ask Lori about them —
  has not been run.
- **The 30 legacy suggestions are protected, not resolved.** They are
  refused at the write and can now be declined; none has been.

None of those is a reason to delay the shutdown. They are the reason
the restart is not the end of the work.

## 5. Backup — the one thing that must not be improvised

`journal_mode` is **wal**. A backup taken by copying `hornelore.sqlite3`
while the stack runs can capture a torn state, because the recent writes
live in the `-wal` file and the two are copied at different moments.
This is the defect an outside review found in the rehearsal scripts and
it applies just as much to a hand-rolled `cp`.

Two safe options, in order of preference:

1. **Stop the stack first, then copy.** A clean shutdown checkpoints the
   WAL. After `stop_all.sh`, `hornelore.sqlite3` is self-contained.
2. **Use the backup API while running** — what
   `backfill_suggestion_ids.snapshot()` does.

Note the `db/` directory already holds a dozen `.fuse_hidden*` files and
several older `.bak` copies. Do not rely on any of them; they are
artifacts, not a backup taken for this transition.

## 6. Sequence

Stopping the stack is safe now. Nothing below it requires approval:

```
stop -> verify backup -> rehearse on the copy -> PRESENT RESULTS
```

and then, only with explicit authorization:

```
-> apply identity backfill -> apply reviewed flags -> start -> verify
```

The legacy-data scripts are **not** part of the shutdown. A successful
rehearsal is a prerequisite for the decision, not the decision.

## 7. After the restart, before calling anything ready

1. `Lorevox DB:` in the new api.log names the same path as §1.
2. The counts in §2 are unchanged.
3. Hard-reload the browser so the UI matches the reviewed server. This
   also clears the `SchemaUnavailable` state the running process has
   been in since the WO-04 commit — it currently cannot read the
   questionnaire schema at all, which is why it refuses every proposal.
4. Then the walkthroughs that have never been run: a real review action
   in the Suggestions tab, and a biography fact reaching Lori in a real
   conversation.
