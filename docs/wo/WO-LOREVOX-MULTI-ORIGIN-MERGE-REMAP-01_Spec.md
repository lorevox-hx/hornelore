# WO-LOREVOX-MULTI-ORIGIN-MERGE-REMAP-01 — combining one narrator from two installations

**Status: DESIGN DRAFT 2026-09-12. NOT APPROVED, NOT STARTED, NOTHING IMPLEMENTED.**
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
**two**, and the ownership declaration knows about the same two.

| where stored | form | declared? | how it must be rewritten |
|---|---|---|---|
| `trip_turn_links.user_turn_row_id` | INTEGER | yes | join on the remap table |
| `trip_turn_links.assistant_turn_row_id` | INTEGER | yes | join |
| `story_candidates.source_user_turn_row_id` | INTEGER | **no** (0047:68, no SQL FK) | join |
| `story_candidates.completed_assistant_turn_row_id` | INTEGER | **no** (0047:69) | join |
| `turn_extraction_ledger.turn_key` | TEXT `turnrow:<id>` | **no** (0038:62) | parse, rebuild |
| `turn_extraction_results.turn_key` | TEXT `turnrow:<id>` | **no** (0041:71) | parse, rebuild |
| `bio_facts.source` | JSON `.turn_key` | **no** (`bio_fact_router.py:367`) | parse JSON, rewrite, re-serialise |

And `turn_extraction_ledger.id` → `turn_extraction_results.ledger_id` is a real FK that
must be remapped with it.

**Two consequences the implementation is built around:**

1. **A merged database can be SQL-valid and still broken.** `PRAGMA foreign_key_check`
   passes over every TEXT and JSON form above. The merge therefore owes a **semantic
   reference validator** that understands Lorevox's own reference vocabulary, and
   acceptance is that validator passing — not SQLite's.
2. **The closure is a maintained artifact, not a one-off reading.** Any future writer
   that serialises a local id into a string, a JSON payload or a path joins this table.
   A test asserts the closure matches what the code actually does, so a new encoded
   reference fails a test rather than corrupting a merge.

**Owed before implementation:** repeat the closure hunt for every other
installation-local surrogate the packages carry (the extraction ledger ids, and any
`INTEGER PRIMARY KEY AUTOINCREMENT` in a narrator-owned lane), and for path components
derived from row ids. The hunt method is the one that found these: grep the migrations
and the writers, not the FK graph.

**Separately reportable finding, outside this WO's scope to fix:** because the two
`story_candidates` turn columns are undeclared, the exporter's §30 "refuse, never
dangle" guard does not check them. The comparator's `reference_integrity_audit`
measures whether any real package actually dangles there. If it does, that is a
Portable Narrator defect and is fixed there, not here.

## 3a. Measured evidence — the real comparison, 2026-09-12

All three pairs compared read-only from the six staged packages; all six byte-identical
before and after. Reports in `.runtime/two_origin/reports/` (gitignored).

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

**Christopher's laptop package carries nine dangling encoded turn references** and is
therefore **not yet usable as a merge input** — see §3c.

## 3b. The two same-path archive files — resolved from code, not from filenames

Both origins carry `memory/archive/people/<id>/index.json` and `rolling_summary.json` at
the same path with different bytes. They are **not the same kind of thing**, and treating
either by its filename would have been wrong:

| file | classification | evidence | merge policy |
|---|---|---|---|
| `index.json` | **derived registry, fully regenerable** | `_register_session_in_index` writes only `{session_id, title, mode, started_at}` (`archive.py:1217-1224`), and every one of those fields is already written into `sessions/<id>/meta.json` (`archive.py:90-96`) | **Regenerate after merge** by walking the merged `sessions/*/meta.json`. Different bytes are NOT a narrator-content conflict and must not be surfaced as one. |
| `rolling_summary.json` | **derived but NOT regenerable** | LLM-produced running memory, scored and **pruned** — lossy by construction — then contamination-filtered, carrying a `wo13_filtered` audit block and `last_updated` (`archive.py:654-687`, WO-13 Phase 5) | **A real divergence.** Each origin evolved its own memory of the narrator. V1 **refuses and reports both**; it is never silently overwritten and never merged by taking the newer `last_updated`, because pruning means neither side is a superset. |

## 3c. Reopened Portable Narrator obligation — the laptop Christopher package

The full-reference audit found **nine** `turn_extraction_ledger` rows in the laptop's
Christopher package whose `turnrow:<turns.id>` keys name turns the package does not
contain. The package is **structurally valid under the old validator and semantically
incomplete under the newly discovered reference invariant** — it is not a corrupted ZIP
or an invalid bag, and its Phase 6 export→restore→export equivalence remains historically
true under the validator that existed then.

**This is a Portable Narrator integrity obligation, not something the merge compensates
for.** The merge must not import the missing turns: a reference pointing outside the
narrator-owned closure is a refusal, and only the ownership declaration decides what
belongs to a narrator (§30).

**What the package proves** and **what it cannot** are separated in
`scripts/dangling_turn_reference_report.py`. It cannot establish whether those turns ever
existed in the laptop's live database, whether they belong to this narrator, or whether
the ledger rows are simply stale — a ledger records extraction *attempts*, which can
outlive the turn they were about. Distinguishing an ownership/declaration gap from stale
derived rows from legacy residue needs **one read-only query against the laptop's live
database**, and the laptop is available for exactly that bounded step.

**Consequence for this WO:** design continues; implementation waits on the disposition.
A corrected authoritative Christopher-laptop package is re-exported only after the cause
is known, using the extended checker — which now refuses rather than shipping the same
gap. The current package is retained unmodified as evidence.

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
