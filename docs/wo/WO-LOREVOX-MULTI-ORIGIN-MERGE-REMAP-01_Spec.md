# WO-LOREVOX-MULTI-ORIGIN-MERGE-REMAP-01 — combining one narrator from two installations

**Status: BUILT AND HARDENED. NOT ON THE CRITICAL PATH FOR THE HORNE FAMILY, 2026-09-14.**

**The three narrators this work order was opened for no longer need it.** Chris decided
2026-09-14 that the **laptop** packages are the authoritative portable versions of
Christopher, Kent and Janice; the desktop copies are superseded development copies and are
not merge inputs. All three came from ONE laptop database, so their installation-local
integer surrogates cannot collide — the *same-origin packages coexist* case of
`WO-LOREVOX-PORTABLE-NARRATOR-01` §34 — and all three restored sequentially into one fresh
installation through the ordinary path and re-exported `EQUIVALENT`. That acceptance is
recorded in `HANDOFF.md` and checklist row 0.

**So §6's acceptance items 4 and 6 — the real-package rehearsal and family acceptance — are
withdrawn as gates for these three narrators.** The synthetic acceptance (items 1–3, 5)
stands and is met. **The desktop-vs-laptop comparisons and the Christopher adjudication
packet in `.runtime/` are historical engineering evidence; do not reconcile those pairs
further.**

**What is built and proven:** the read-only source planner, the read-only target-binding
stage, the executor with migration `0057`'s own merge ledger, `recover_merge_jobs`, and the
semantic reference validator. The real Christopher rehearsal ran and **REFUSED as designed**
— 5 conflicts, zero target mutation, both packages byte-identical afterwards — which is the
V1 acceptance result rather than a failure.

**It paid for itself on the way.** The real rehearsal exposed two production defects no
synthetic fixture had reached: a same-logical-record physical-collision misclassification
that would have put two `people` rows in one root, and a shared installation-dependency
helper that silently required `sqlite3.Row` while advertising a plain connection — a defect
on the **restore** path, which the family acceptance then depended on. Both fixed with
regression coverage.

**When it is the right tool:** genuinely combining two independently developed histories of
one narrator, or importing into an installation where installation-local ids actually do
collide. Both prerequisites were discharged before the pause — §3c, §3a and the full
surrogate + path closure hunt in §3d — and **§3 was corrected the same day**: the
declaration knows all seven `turns.id` reference sites, and the `PRAGMA foreign_key_list`
walk finds none of them rather than two.
Owed since the Portable Narrator Phase 4 finding (`WO-LOREVOX-PORTABLE-NARRATOR-01` §34)
and blocking the Phase 7 one-root cutover. Drafted from the two-origin comparison
evidence, not from expectation — the measured numbers live in
`.runtime/two_origin/reports/` (gitignored; real narrator content).

**One sentence:** given the same narrator packaged independently from two
installations, produce ONE narrator in a brand-new root without losing a row, without
duplicating a row, and without silently choosing between two versions of the truth.

---

## Mission alignment

Christopher's conversations and audio are on the desktop; his entire travel domain is
on the laptop (§31, §36.5). Neither machine holds him whole. Until these combine, the
family archive is two half-portraits, and Phase 7's clean installation cannot be built
without choosing which half to lose. This work order exists so nobody has to choose.

The narrator is the author of their own story. A merge that quietly drops a trip, or
silently prefers one machine's profile over the other's, edits that story on their
behalf. **Refusing is always available; guessing is not.**

## Non-regression requirements

This WO MUST NOT:

- reduce narrator dignity;
- introduce must_not_write violations or system-tone outputs;
- regress the locked extractor baseline (it touches no extractor, prompt or model);
- expand operator surfaces into narrator UI;
- add detectors that duplicate existing signals;
- **merge into, restore into, or modify either existing live `DATA_DIR`.** The merge
  target is always a brand-new root. Both origins are immutable inputs.

## Scope

**IS:** Christopher, Kent and Janice, each from their desktop package and their laptop
package, into one new root. Deterministic remap of installation-local surrogate ids
with a complete reference rewrite. A dry run that writes nothing. Provenance for every
retained, remapped and refused record.

**IS NOT:** Melanie — **explicitly out of scope by Chris's decision 2026-09-12**. The
desktop holds record `3fc781ae` and the laptop holds `d56900b5`; they are distinct
database records and logical-person equivalence is **unresolved and will not be
resolved here**, because Chris intends Melanie to be removed rather than migrated. Do
not design same-person cross-origin identity handling around her, do not include her
in any comparison, and do not delete either record as part of this work — deletion is
the ordinary narrator-erasure path, separately, later.

Also not in scope: merging three or more origins; conflict resolution UI (the first
implementation refuses and reports); any change to the ordinary single-origin restore.

---

## 1. The four questions, kept apart

The comparison evidence deliberately separates four things that are easy to conflate,
and this WO inherits the separation. **Similarity must never silently become identity.**

| concept | means | does NOT mean |
|---|---|---|
| `CROSS_ORIGIN_IDENTITY_UNKNOWN` | no defensible logical key exists for this table | that the rows are different |
| `PHYSICAL_ID_COLLISION` | the same installation-local integer carries different content | that the rows are related |
| `CONTENT_OVERLAP` | canonical row content is byte-equal | that the two rows are the same *record* |
| `REFERENCE_REWRITE_REQUIRED` | a stored value points at a surrogate being remapped | anything about the row's identity |

## 2. Identity model — three keys, derived separately

Established by the comparator (`scripts/two_origin_compare.py`) and binding here.

- **physical key** — what the schema says the PK is. `turns.id` is a real primary key
  *and* installation-local: the collision surface, never an identity.
- **ownership path** — how `narrator_data_inventory.py` says the row belongs to the
  narrator, including the `DirectOrExclusiveInbound` residue closure (§36.5).
  Reference metadata; the packages already contain exactly what the exporter selected,
  and this WO re-derives nothing from a live database.
- **cross-origin logical key** — table-specific, individually justified, and frequently
  **absent**. Two rules, both corrections to an earlier draft and both mandatory:
  1. **Content is never part of a logical key.** A key containing a compared value
     means a changed row changes its own key, and the one case worth finding — same
     record, different content — disappears into two one-side-only rows.
  2. **A UUID is not automatically a cross-origin identity.** UUID syntax is a minting
     format, not shared provenance. `people.id` earns a logical key because §31
     *measured* the same id on both machines; `photos.id` does not, and is
     `NO_SAFE_CROSS_ORIGIN_KEY` until someone establishes provenance.

`turns` has **no defensible cross-origin key**: the shipped table is
`(id AUTOINCREMENT, conv_id, role, content, ts, anchor_id, meta_json)` (`db.py:587`)
with no stable per-conversation ordinal. That is a useful answer, not a gap to fill —
turns are merged by **conversation**, never paired row-to-row.

## 3. The remap closure — the finding that shapes this WO

`turns.id` is stored in **seven** places. A `PRAGMA foreign_key_list` walk finds
**none of them**, and Lorevox's own semantic-reference declaration now knows **all
seven**.

*(**Both halves of that sentence were wrong until 2026-09-14** and they failed in
opposite directions. It said the FK walk finds "two" and the declaration knows "the
same two". The FK count conflated *declared in `COLUMN_ONLY_REFERENCES`* with *visible
to SQLite*: both `trip_turn_links` columns are bare `INTEGER` at `0039:135-136`, the
`0040` rebuild keeps them bare, and **no migration contains `REFERENCES turns` at
all**. The declaration count was overtaken by the 2026-09-12 repair, which added the
two `story_candidates` columns and all three encoded forms. Correcting the first
**strengthens** this section's conclusion rather than weakening it.)*

| where stored | form | declared by | how it must be rewritten |
|---|---|---|---|
| `trip_turn_links.user_turn_row_id` | INTEGER | `COLUMN_ONLY_REFERENCES` | join on the remap table |
| `trip_turn_links.assistant_turn_row_id` | INTEGER | `COLUMN_ONLY_REFERENCES` | join |
| `story_candidates.source_user_turn_row_id` | INTEGER (0047:68, no SQL FK) | `COLUMN_ONLY_REFERENCES` | join |
| `story_candidates.completed_assistant_turn_row_id` | INTEGER (0047:69) | `COLUMN_ONLY_REFERENCES` | join |
| `turn_extraction_ledger.turn_key` | TEXT `turnrow:<id>` (0038:62) | `ENCODED_REFERENCES` | parse, rebuild |
| `turn_extraction_results.turn_key` | TEXT `turnrow:<id>` (0041:71) | `ENCODED_REFERENCES` | parse, rebuild |
| `bio_facts.source` | JSON `.turn_key` (`bio_fact_router.py:367`) | `ENCODED_REFERENCES` | parse JSON, rewrite, re-serialise |

And `turn_extraction_ledger.id` → `turn_extraction_results.ledger_id` is a real SQL FK
(`0041:67-68`) that must be remapped with it. It is declared by **SQLite**, not by the
inventory tuples — those exist precisely for references the schema does *not* declare —
so a tool that decides "is this declared?" by reading only `COLUMN_ONLY_REFERENCES` and
`ENCODED_REFERENCES` will report this one undeclared and be wrong.

**Three consequences the implementation is built around:**

1. **A merged database can be SQL-valid and still broken — and the declaration being
   complete does not change that.** `PRAGMA foreign_key_check` passes over every row
   above, because SQLite cannot see a bare INTEGER, a `turnrow:` string or a JSON
   field. Production knowing about all seven means the **exporter** refuses to ship a
   dangling one; it does not give SQLite the ability to check a merge. The merge
   therefore still owes a **semantic reference validator** that understands Lorevox's
   own reference vocabulary, and acceptance is that validator passing — never SQLite's.
2. **Merge/Remap consumes the same production declaration** (`narrator_data_inventory`),
   as export integrity, restore validation and the two-origin comparator already do. A
   fifth private copy of this list is how the fourth one went stale.
3. **And it keeps an INDEPENDENT closure with a parity test.** The seven sites were
   found by reading migrations and writers, not by asking the declaration. That
   independence is the only thing that can catch the declaration being *wrong*, so the
   merge keeps its own discovered list and a test holds the two sets against each other
   — `discovered == declared == 7` at HEAD. A site discovered but undeclared is an
   **export gap**; a site declared but not discovered is **evidence drift**. Deriving
   the closure from the declaration would make the check tautological and must not be
   done.

**How this drifted, recorded so it is not repeated.** `scripts/two_origin_compare.py`
carried `declared` as a hand-written boolean per site. The 2026-09-12 repair made five
of them false, nothing updated the comparator, and on 2026-09-14 a real family
comparison reported that the exporter does not check references it had been checking
for two days — with a regression test pinning the stale answer. Fixed by deriving the
bit from the live declaration at run time and inverting the test.

**Owed before implementation — ✅ DISCHARGED 2026-09-14, recorded in §3d.** The hunt was
repeated for every other installation-local surrogate the packages carry and for path
components derived from row ids, by the method that found the first seven: read the
migrations and the writers, never the FK graph.

**Separately reportable finding — CLOSED 2026-09-12, kept because the mechanism
matters.** This paragraph read: *"because the two `story_candidates` turn columns are
undeclared, the exporter's §30 'refuse, never dangle' guard does not check them."*
That was true when written and was fixed the same day — both columns are now
`ColumnRef`s and all three encoded forms are `EncodedRef`s, so §30 covers the whole
closure. The comparator's `reference_integrity_audit` still measures every site
independently of whether it is declared, which is what let the audit find the nine
dangling laptop references in the first place; a dangle there is a Portable Narrator
defect and is fixed there, not here.

## 3a. Measured evidence — the real comparisons

Kent and Janice: 2026-09-12. **Christopher: re-run 2026-09-14 against the replacement
laptop package `24560db21dd6`** (the 2026-09-12 figures were against the superseded
`a2f360689b58`). Every substantive Christopher number below is **unchanged** between the
two runs — the repair removed nine stale ledger rows, which changed no keyed row, no
conflict, no file and no collision verdict. All packages byte-identical before and after
every run. Reports in `.runtime/two_origin/reports/` (gitignored).

**Authoritative merge inputs:** desktop `ea4ae5d6afc5` · laptop `24560db21dd6`
(Christopher), `451876ad9efa` / `f42a80afb420` (Kent), `74252b2e79c5` / `aca0cdfd9c13`
(Janice). Kent and Janice are **not** re-run: nothing in the repair touched them.

| | Christopher | Kent | Janice |
|---|---|---|---|
| keyed rows, desktop-only | 10 | 0 | 0 |
| keyed rows, laptop-only | 9 | 0 | 1 |
| same key, different content | 4 | 4 | 4 |
| `NO_SAFE_CROSS_ORIGIN_KEY` tables | 31 | 10 | 13 |
| surrogate id collisions | **remap required** | none measured | none measured |
| files desktop-only | 110 | 60 | 49 |
| files laptop-only | 212 | 43 | 19 |
| files same path, different bytes | 2 | 2 | 2 |
| files same path, same bytes | 0 | 0 | 0 |

**Near-total file disjointness** on all three: each machine recorded its own sessions, so
the file-level merge is overwhelmingly union, not reconciliation. The only same-path
collisions are the two derived archive files resolved in §3b.

**Zero dangling references on both origins, all three narrators**, under the expanded
reference audit. *(This paragraph read "Christopher's laptop package carries nine dangling
encoded turn references and is therefore not yet usable as a merge input" until 2026-09-14
— true of the superseded `a2f360689b58`, false of `24560db21dd6`. See §3c.)*

## 3d. The full surrogate and path closure hunt — completed 2026-09-14

Method: read every migration under `server/code/db/migrations/` and every writer under
`server/code/api/`, plus `ui/js`. **The FK graph was not consulted for discovery**, only
for classification. Every row is `verified_by_read` with the writing or reading line
cited.

**There are exactly THREE narrator-owned installation-local integer surrogates.** Nothing
else in a packaged lane is an `INTEGER PRIMARY KEY`; every other narrator-owned table uses
a TEXT/UUID primary key.

| surrogate | minted at | referenced by | what the merge must do |
|---|---|---|---|
| `turns.id` | `db.py:588` | the **seven** sites of §3 | renumber **and** rewrite all seven |
| `turn_extraction_ledger.id` | `0038:55` | `turn_extraction_results.ledger_id` **only** (`0041:67-68`, a real SQL FK; written `db.py:9911` from `db.py:9765` `lastrowid`) | renumber and rewrite that one join |
| `turn_extraction_results.id` | `0041:62` | **nothing at all** | renumber only — **no reference rewrite exists to get wrong** |

**`turn_extraction_results.id` has zero referents, and that is a measured finding rather
than an absence of evidence.** No column, no TEXT, no JSON key holds it anywhere in the
tree. Its only uses are ordering and a replay short-circuit (`db.py:9893`, `:9953`,
`:8743`, `:10056`), a return value its single caller discards (`turn_extraction.py:790-800`
ignores `db.py:9919`), and one outbound read-only API field (`db.py:10076` →
`operator_story_review.py:270`) that nothing writes back — the ack path is keyed by
`turn_key` (`extract.py:10695-10698`), and the browser holds `turn_key` only
(`interview.js:1793-1794`). **This matters because it is the ONLY physical collision
measured in the real family data** (Christopher, `id = 1`, different content on each
origin): the one collision we must actually resolve is also the cheapest.

**No eighth `turns.id` reference exists.** Four near-misses were ruled out by reading
their writers, and are recorded so they are not re-investigated: `follow_up_bank
.triggering_turn_index` / `.asked_at_turn` and `interview_threads.source_turn_index` are
per-session turn **counters** (`chat_ws.py:7999`, `:3343`), and `trip_location_notes
.source_ref` / `.source_turn_ref` and `trip_photo_context.source_ref` embed the **client's
TEXT** turn id under different grammars (`trip_story_capture.py:488`, `:495`, `:537`).
`turns.meta_json` never stores another turn's id — the only non-literal `meta` is
`chat_ws.py:7700-7702`, and `story_capture_decision` is field-whitelisted at
`story_trigger.py:888-899`. Of six `source_json` producers only `bio_facts.source` carries
a turn reference.

**`turnrow:<int>` is the only grammar that encodes an integer row id**, with one canonical
writer (`db.py:9693`). The other `<word>:<id>` grammars in the tree (`turn:`,
`modal_turn:`, `photo_link:`, `trip:`, `qb:`, `child_birth:`) all carry TEXT ids.

**NO path contains an integer row id — the merge rewrites columns, it renames no files.**
Every path-bearing value is keyed by a TEXT id, `person_id`, `conv_id`, a `uuid4`, or a
timestamp:

| path | keyed by | cite |
|---|---|---|
| `memory_archive_sessions.archive_dir` | `person_id` + `conv_id` | `utils/archive_paths.py:94-104` |
| `photos.image_path` / `.thumbnail_path` | `narrator_id` + `uuid4().hex` photo id | `photo_intake/storage.py:52-60`, `:86`, `:93`, `:101` |
| `media_archive_items.storage_path` | `person_id` + `uuid4().hex` item id | `media_archive/storage.py:97-109` |
| `trip_sources.storage_path` | `uuid4()` source id | `routers/trips.py:2113-2117` |
| archive audio `audio/<turn>.webm` | `memory_archive_turns.turn_id`, a **TEXT** uuid — **not** `turns.id` | `routers/memory_archive.py:563`, minted `:469` / `archive-writer.js:191-197` |
| `stories-captured/…` | `narrator_id` + `<ts>__<candidate_id[:8]>`, a TEXT uuid | `story_preservation.py:386-391` |
| `import_staging/…` | TEXT `batch_id` / `candidate_id` | `import_staging.py:130-139` |
| `memory/agents/…` | `slug(conv_id)` | `chat_memory_paths.py:37-60` |

The archive audio filename was the highest-risk candidate and is clean. All five
`lastrowid` sites in the tree (`db.py:2395`, `:2401`, `:9765`, `:9919`) feed columns or
handles, never a filename.

**A PHYSICAL ID COLLISION IS NOT AN INTEGER PROBLEM — corrected 2026-09-14 on review.**
The three integer surrogates above are the only *installation-local counters*, and the
first implementation drew the wrong conclusion from that: it remapped them and assumed a
TEXT/UUID primary key cannot collide across installations. **The real Christopher
comparison disproves that on its own evidence.** `graph_persons` is
`NO_SAFE_CROSS_ORIGIN_KEY`, holds 1 desktop row against 14 laptop rows, and reports
**one shared physical id whose content is not identical** — because the product mints
graph-person ids deterministically from narrator + name, so two installations that met
the same relative independently mint the same id for different rows. Two such rows
cannot both be inserted under one `TEXT PRIMARY KEY`, and V1's rule for a no-safe-key
table is that both sides are preserved. So:

- the collision hunt runs over **every packaged table that has an `id` column**, by
  comparing the actual values — never by assuming a UUID-shaped id is collision-free;
- reallocation is **type-agnostic**: integers renumber, TEXT ids become a deterministic
  `uuid5`, and only where they actually collide;
- `graph_relationships.from_person_id` and `.to_person_id` are **real table-level SQL
  foreign keys** (`db.py:7421-7423`, `ON DELETE CASCADE`) and must be rewritten with it;
- **a collision in a table whose reference closure has not been established is a
  REFUSAL**, never a guess — reallocating a row whose children cannot be enumerated
  would silently orphan them. "Established and empty" (`turn_extraction_results.id`) and
  "unknown" are different states and must stay distinguishable.

**AND EQUAL BYTES DO NOT MAKE A SHARED ID SAFE — corrected 2026-09-14 in review of
`2e10319`.** The first implementation reallocated a shared physical id only when the two
rows differed in content, and skipped it when they were byte-identical. That is right for
a table with a **proven** cross-origin logical key — `people.id` was measured identical on
both machines (§31), so an identical row there is one row and is represented once. It is
**wrong for a `NO_SAFE_CROSS_ORIGIN_KEY` table**, and `graph_persons` is exactly that:
correspondence was never established, §1 says `CONTENT_OVERLAP` does not mean two rows are
the same *record*, and V1 preserves both sides — so two byte-identical rows would have been
carried under one `TEXT PRIMARY KEY`, leaving the executor to fail on a duplicate key or
drop one of the narrator's rows. Letting content equality decide identity is the precise
failure this work order exists to prevent, and it survived the first review because the
test that covered it used `people`.

The rule is therefore split by what the table can prove:

| table | shared physical id | outcome |
|---|---|---|
| proven logical key | same logical record **and** same content | represent once, no reallocation |
| proven logical key | different logical record, or different content | reallocate (or the keyed conflict refuses) |
| `NO_SAFE_CROSS_ORIGIN_KEY` | **any** shared id, identical bytes included | **always reallocate**, or refuse if the closure is unknown |

**The hunt must also be generic over the key's NAME, not only its type.** It compares
whatever the schema declares as the primary key. Measured 2026-09-14: every narrator-owned
lane keys on a single `id` column and **no table anywhere uses a composite
`PRIMARY KEY (a, b)`** — both pinned by test, so a future `something_key TEXT PRIMARY KEY`
lane fails the guard instead of silently bypassing collision detection.

**Out of scope because it never enters a package:** the response trace embeds `turns.id`
and `turnrow:` keys (`chat_ws.py:7743-7748`, `:7782-7786`) but writes to
`.runtime/eval/response-trace` (`lori_response_trace.py:136-144`), which is under the
**repository**, not `DATA_DIR`, and which no `FsLane` declares. Merged roots therefore
carry no stale trace references. The same applies to
`scripts/repair_stale_ledger_references.py`'s recovery artifact.

**One NEW defect found, and it belongs to Portable Narrator, not here.** `media.filename`
stores a **full absolute path** (`routers/media.py:108`, whose own comment says so) while
`DbLane("media", …)` declares **no `path_columns`** (`narrator_data_inventory.py:250`) —
so §8.5's restore-time path rewrite does not normalise it, and a restored or merged root
would keep the origin machine's absolute path. **It is latent, not urgent: no `media` rows
appear in any of the six real packages**, so it gates nothing here. Registered as a
Portable Narrator obligation; do not fix it inside this WO (§3's rule — a dangle or a path
defect is fixed where it is created).

## 3b. The two same-path archive files — resolved from code, not from filenames

Both origins carry `memory/archive/people/<id>/index.json` and `rolling_summary.json` at
the same path with different bytes. They are **not the same kind of thing**, and treating
either by its filename would have been wrong:

| file | classification | evidence | merge policy |
|---|---|---|---|
| `index.json` | **derived registry, fully regenerable** | `_register_session_in_index` writes only `{session_id, title, mode, started_at}` (`archive.py:1217-1224`), and every one of those fields is already written into `sessions/<id>/meta.json` (`archive.py:90-96`) | **Regenerate after merge** by walking the merged `sessions/*/meta.json`. Different bytes are NOT a narrator-content conflict and must not be surfaced as one. |
| `rolling_summary.json` | **derived but NOT regenerable** | LLM-produced running memory, scored and **pruned** — lossy by construction — then contamination-filtered, carrying a `wo13_filtered` audit block and `last_updated` (`archive.py:654-687`, WO-13 Phase 5) | **A real divergence.** Each origin evolved its own memory of the narrator. V1 **refuses and reports both**; it is never silently overwritten and never merged by taking the newer `last_updated`, because pruning means neither side is a superset. |

## 3c. Reopened Portable Narrator obligation — **CLOSED 2026-09-14, this WO is UNBLOCKED**

**The blocker this section described is discharged. Implementation no longer waits on
anything.** The authoritative laptop Christopher package is
`Christopher_Todd_Horne_24560db21dd6.lorevox.zip` — **524 records / 214 files, zero
unresolved FK, `ColumnRef`, encoded-TEXT or encoded-JSON references** — and the
replacement two-origin comparison against desktop `ea4ae5d6afc5` is complete (§3a).

**What it was.** The full-reference audit found nine `turn_extraction_ledger` rows in the
**superseded** package `a2f360689b58` whose `turnrow:<turns.id>` keys named turns the
package did not contain: structurally valid under the old validator, semantically
incomplete under the newly discovered reference invariant — never a corrupted ZIP.

**What it turned out to be: stale derived bookkeeping, and only that.** Ledger ids
7, 8, 9, 10, 11, 17, 18, 19, 28 were removed from the authoritative laptop database and
nothing else, under one `BEGIN IMMEDIATE` requiring `rowcount == 9`, with the originals
written verbatim to a recovery artifact first. 533 → 524 records; files unchanged at 214.
The replacement package restored into a brand-new clean root with the narrator never
opened, re-exported, and compared `EQUIVALENT tables=60 rows=524 files=214`.

**Deliberately NOT done, and not to be resurrected:** no ownership was materialised, no
`trip_turn_links` touched, no session curated, no facts salvaged. `DirectOrExclusiveInbound`
carries Christopher's 9 sessions and 100 turns exactly as §36.5 proved — he has **zero
directly-owned sessions**, which is what makes that closure load-bearing for a real family
narrator. The superseded ownership-repair theory, the four candidate-session decisions and
the withdrawn 578/597/654 arithmetic are **history, not work**. The preservation/curation
analysis is Phase 7 input and gates nothing.

**What still stands from the original obligation:** the merge must not import missing
turns. A reference pointing outside the narrator-owned closure is a refusal, and only the
ownership declaration decides what belongs to a narrator (§30). `a2f360689b58` is retained
unmodified as historical evidence and is **not** a merge input.

## 4. Merge classes and their policies

| class | policy | needs a human? |
|---|---|---|
| one-origin-only, keyed | union; carry verbatim; record origin | no |
| identical content on both, keyed | represent once; record both origins | no |
| `SAME_LOGICAL_RECORD_DIFFERENT_CONTENT` | **refuse in V1**, report with the differing columns | yes |
| `NO_SAFE_CROSS_ORIGIN_KEY` | **preserve both sides independently**, scoped to their parent (turns by conversation); never pair, never deduplicate, never drop | no |
| duplicate logical keys within one origin | carry as-is; do not collapse | no |
| `PHYSICAL_ID_COLLISION` | remap deterministically; rewrite the full closure | no |
| file: same path, same hash | store once | no |
| file: same path, different bytes | **refuse in V1**, report both hashes | yes |
| file: one origin only | copy | no |
| identical bytes at different paths | copy both; note the dedupe opportunity | no |

**`NO_SAFE_CROSS_ORIGIN_KEY` must never become "drop one side."** It is the largest class
in the real evidence — 31 tables for Christopher — and it means *correspondence could not
be proven*, not *the rows are duplicates*. The merge preserves every such row from both
origins with its origin provenance. If that produces two records a human can see are the
same thing, a human decides later; a tool that guesses here would delete a narrator's
history on the strength of a similarity score.

**A DIFFERING REFERENCE IS "THE SAME" ONLY ONCE THE REFERENCED ROWS ARE PROVEN TO
CORRESPOND — corrected 2026-09-14 on review.** The first implementation normalised every
reference to a sentinel before comparing row content, so that two origins citing "their
own copy" of a conversation would not be reported as a conflict. **That was wrong in the
one direction this WO cannot afford.** `turns` has no defensible cross-origin key *by
design*, so desktop turn 17 and laptop turn 84 have never been shown to be the same
evidence; blanking both citations declared two facts identical on the strength of a
correspondence nobody proved — similarity silently becoming identity, §1's first rule.

The rule is therefore: **classify rows AFTER the remap, on the remapped values.** Two
references are equal if and only if they resolve to the same merged row, which is
exactly the condition under which ignoring the difference is safe. Where the parent
genuinely corresponds the ids converge and the difference disappears on its own; where
it does not, the difference survives and is reported. Refusing is not dropping — both
rows are still carried while a human decides.

**V1 refuses every conflict rather than resolving it.** A merge that picks a winner
without being told is exactly the silent edit this WO exists to prevent. Policies for
automatic resolution (last-writer-wins, per-field precedence, operator review UI) are a
V2 decision once the real conflict volume is known.

## 5. Determinism, provenance and refusal

- **Deterministic remap.** Same inputs, same output ids, every run. The remap table
  (`origin`, `table`, `old_id`, `new_id`) is written as evidence before any dependent
  row is inserted, and is part of the merged root's provenance.
- **Provenance per record.** Every merged row and file records which origin package it
  came from (package id and sha256) and whether its surrogate was remapped. A narrator's
  history must remain attributable after it is combined.
- **Refusal conditions** — the merge stops, writes nothing, and names the reason:
  unresolved conflict in any class marked "needs a human"; a dangling reference after
  rewrite; a package failing integrity; missing installation dependencies in the target;
  the target root not being empty; any attempt to target a live `DATA_DIR`; an encoded
  reference whose form is not in the closure table.
- **Transaction, rollback, crash recovery.** Reuse the Phase 3 shape that is already
  proven (§33, §33.1): files first with `O_EXCL`, a durable job row with a path→sha256
  manifest before the first byte, one `BEGIN IMMEDIATE` with `defer_foreign_keys`,
  `db_committed` written *inside* the transaction, and hash-gated cleanup below it.

## 5a. Executor preconditions and the V1 conflict policy — decided 2026-09-14

**THE PRODUCT INITIALISES THE ROOT; MERGE/REMAP POPULATES IT.** A hard precondition, not
a convenience. The canonical sequence is: the product creates a fresh `DATA_DIR` → normal
migrations / `init_db()` / seed state complete → Merge/Remap verifies that root
**read-only** → only then may the executor write into it. The executor never creates,
migrates, seeds or repairs a target, and the dry run may report NOT READY but never fixes
anything.

Phase 5a is the reason. A never-used clean installation refused every narrator with a
questionnaire because dependency lookup matched `bio_fields` on its primary key instead of
the column the narrator's rows reference, and a clean root had no `chat_ws` interview plan
until somebody had chatted. Both were fixed in ordinary product initialisation. **A merge
that built its own schema or seeded its own dependencies would be re-deciding what a clean
Lorevox installation is** — the one definition Phase 7 also depends on. Readiness therefore
consumes the product's own `dry_run_restore` per source package; the merge blocks on
`missing_dependencies`, and its own checks answer the merge-specific questions.

Verified before any write: the target is not a source or the live `DATA_DIR` (and the root
is the exact one supplied — **never an environment or default fallback**); the database
exists with current migrations; required installation-owned state is present; the planned
narrator absent; no planned file already on disk. Synthetic tests build their disposable
target through the real initialisation path, never hand-built SQL.

**A TARGET MAY ALREADY HOLD OTHER NARRATORS — corrected 2026-09-14 on review.** The first
executor draft refused any target containing a real narrator. That is right for the first
merge into a fresh root and **makes the family root impossible to build**: Christopher
lands holding `turns.id = 1..N`, and Kent's independently planned two-origin merge asks
for the same ids. Refusing the second narrator would mean the consolidated installation
this whole work order exists to produce could never contain more than one person. Only
*this* narrator already being present is a refusal.

**Binding is what makes accumulation safe, and it is its own read-only stage:**

    two packages → source merge plan → inspect initialised target
    → bind around occupied ids → execution plan → apply

The source planner stays pure and target-ignorant (which is what keeps it writer-free and
reviewable). Binding reads the ids the target already occupies and deterministically
allocates the lowest free positive integers for the three installation-local families, in
the plan's own order, then rewrites the complete established closure a second time. **An
empty target still yields 1..N** — binding changes nothing when there is nothing to avoid.
A non-integer physical key clashing with a row already in the target is reallocated when
its closure is established and **refused otherwise**; equal bytes are never proof of
cross-narrator identity, and nothing is ever overwritten.

**The binding is fingerprinted against the target state it was computed from** — schema,
migrations, installation dependencies, occupied physical keys for incoming tables, and
planned-path occupancy — and **deliberately not against the whole installation**, because
writing the merge job row would otherwise invalidate the merge's own basis. If that basis
moves between binding and execution, the executor **REFUSES and requires a fresh dry run**
rather than silently recomputing: the ids about to be written were chosen against a
specific target, and re-deriving them mid-apply would execute a plan nobody reviewed. The
job row records the BOUND execution fingerprint, because that is what actually lands.

**V1 REFUSES AND REPORTS. A REFUSAL IS AN ACCEPTANCE RESULT, NOT A FAILED MERGE.** The
first real Christopher rehearsal is *expected* to prove everything up to the conflict
boundary — package validity, deterministic remap, the complete reference rewrite, zero
dangling references, the safe union, file classification, target readiness — and then stop,
having written nothing, reporting **4 keyed row conflicts plus the `rolling_summary.json`
divergence**. `index.json` is regenerated and is not a conflict. That outcome is the proof
V1 works; it is not the completion of the family consolidation, and the two must not be
confused in any report.

**No automatic resolution is to be added to the executor, now or later.** The refusal
report is instead shaped so an explicit human adjudication artifact can be bound to it
**without changing the merge engine**: every conflict is individually addressable, both
origins' provenance is preserved, and the report names the exact package ids and sha256s
the decisions would apply to, so an adjudication cannot be replayed against different
source data. Building that artifact is separate work and is what actually completes
Christopher and unblocks Phase 7.

**Known boundary, stated rather than half-wired:** `recover_restore_jobs` is restore-only —
its `db_committed` branch verifies recorded files against *the* package, and a merge job
names two. An in-process failure is fully handled (the transaction rolls back and the job
removes only its own files, proven by test); recovery from a process kill is not yet
available for merge jobs. The job row is already crash-truthful and carries the same
0054/0055 shape, so that recovery can be added without changing what the executor writes.

## 6. Acceptance

1. **Synthetic two-origin fixtures first**, containing by construction: identical rows;
   same key, different content; one-side-only each way; a `turns.id` collision with
   different content; a file path collision with identical bytes; a file path collision
   with different bytes; an encoded `turnrow:` reference to a colliding id; a JSON
   `bio_facts.source` reference to a colliding id. The merge must remap, rewrite all
   seven reference sites, and leave zero dangling references.
2. **Semantic reference validator passes** on the merged root — not merely
   `PRAGMA foreign_key_check`.
3. **Dry run writes nothing**, and its plan matches what the real run then does.
4. **Rehearsal into a brand-new root** from the six real packages, both origins,
   Christopher first. Both existing installations untouched and hash-verified after.
5. **Post-merge export and comparison:** export the merged narrator and prove that
   every row and file from each origin is present exactly once, or explicitly refused
   with a reason.
6. **Family acceptance before Phase 7:** all three narrators, counts reconciled against
   both origins' preflights, travel domain resolving, transcripts and audio playable.

Only then does Phase 7 create the consolidated installation.

## 7. Explicit prohibitions

- Never merge into `/mnt/c/hornelore_data` on either machine.
- Never modify, rewrite, normalise, re-zip or delete a source package.
- Never resolve a conflict automatically in V1.
- Never treat a shared UUID, a shared physical id, or equal content as proof of
  identity without a stated justification.
- Never claim a merged root is sound on the strength of `foreign_key_check` alone.
