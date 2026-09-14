# Session-ownership findings — laptop investigation, 2026-09-13

**`WO-LOREVOX-PORTABLE-NARRATOR-01`, between §36.5 (laptop origin accepted) and the
two-origin comparison.** Read-only throughout: no database write, no ownership
repair, no deletion, no erasure, no package re-export.

**What opened it.** The stronger semantic-reference validator found that
Christopher's accepted laptop package `a2f360689b58` carries **nine
`turn_extraction_ledger` rows whose `turnrow:<id>` keys name turns the package does
not contain**. The export had passed `EQUIVALENT` because
`turn_extraction_ledger → turns` is **not** in `COLUMN_ONLY_REFERENCES`, so §30's
unresolved-reference guard never examined that edge.

---

## A. The two-origin discovery

| | |
|---|---|
| dangling encoded references | **9**, all `turn_extraction_ledger` |
| affected conversations | **3**, all `sessions.person_id = NULL` |
| turns in those conversations | **28** (10 + 8 + 10) |
| dangling turn ids | 1455, 1461, 1467, 1471, 1477, 1515, 1517, 1529, 1579 |

The nine were the symptom. The three whole sessions were the omission.

## B. Ownership evidence

All three carry exactly one `interview_sessions` row, naming Christopher
`a4b2f07a`, unambiguous — the strongest of the recorded links migration 0044
accepts. **Ownership is settled structurally.**

**The first probe's `reached by: []` was a false negative and must not be cited.**
`inspect_dangling_turn_origins.py` guards its ledger reacher query with
`if "conv_id" in ledger columns`; the ledger's session column is named
**`session_id`**, so the check was skipped entirely. It reported "nothing reaches
these" when nine ledger rows, all Christopher's, reach them through the turns.

**No ownership was inferred from prose or from the filesystem.** All three
conversations do have transcripts under
`memory/archive/people/a4b2f07a…/sessions/<conv_id>/`, and 0044's header names
**"archive-directory proximity"** in its explicit refusal list alongside timestamp
adjacency and narrator prose. A signal too weak to write `person_id` from is too
weak to derive closure from; the `DirectOrExclusiveInbound` pattern does not give
it a second chance.

## C. Migration 0044

**Runner exonerated.** `server/code/db/migrations_runner.py:72-89` runs the whole
file through `executescript`, re-raises on failure leaving no tracking row, and
inserts the filename only after success. Partial application cannot produce a
recorded migration.

**`applied_at` proves the script did not raise. It proves nothing about whether any
UPDATE matched a row.** A backfill selecting zero rows and one repairing a thousand
record the identical success. `0044` applied **2026-08-17 03:06:39 UTC**; `0045`
**2026-08-18 01:31:22**.

**The literal pass predicates, run verbatim today:** pass 1 matches **81** rows,
pass 2 **0**, pass 3 **0**. All three named conversations satisfy pass 1, each
resolving to Christopher.

**Condition A is proven from code, not timestamps.** `ensure_interview_session`
(`db.py:3333-3338`) is `INSERT OR IGNORE` with no upsert clause, so it can never
fill a NULL `person_id` on an existing row — whatever those rows carry was supplied
at INSERT — and `started_at` is `_now_iso()` at that same INSERT. The three rows
are `plan_id='chat_ws'`, carry Christopher, and are dated 2026-07-30…08-01, before
0044 ran. **The qualifying evidence existed when the migration executed.**

**`0045` confirms the gap rather than closing it.** Its condition-5 comment reasons
*"Where a stronger source names exactly one narrator, 0044 has already written it
and condition 1 excludes the row."* These arrived still NULL with empty
`payload_json`, correctly failed its `legacy_id <> ''` test, and passed through.
0045 itself applied fine.

**The exact failure mechanism is NOT recovered, and is not claimed.** Of 104 owned
sessions, 95 are `explicit`, 8 `legacy_payload_json`, and **1** has a NULL source —
so 0044's backfill yielded at most one row across all three passes.

### Withdrawn, so it is not repeated

`migration_0044_verdict.py` computed its "pre-0044" rowid watermark as
`MAX(rowid) WHERE started_at <= applied_at`. **That is circular**: a row inserted
late bearing an old `started_at` satisfies the WHERE and raises the watermark
itself, concealing exactly the case the test existed to detect. Its
"INSERTED AFTER 0044: False" lines are **not evidence** and are withdrawn.

The non-circular replacement is order consistency. `interview_sessions.started_at`
shows **0 inversions across 178 rows** — real evidence, and that column is
write-once. `sessions.updated_at` shows 640 inversions and is **not evidence of
anything**: it is rewritten on every touch and was never an insertion clock.

## D. Writer and deployment

| event | UTC |
|---|---|
| `fea94bc` ownership fix in this laptop's tree (reflog) | 2026-08-16 13:49 |
| Del session `switch_mswiby0y_2kws` | 2026-08-17 00:41 |
| 0044 applied | 2026-08-17 03:06:39 |
| **first row proving the fixed writer actually ran** (`person_id_source='explicit'`) | **2026-08-18 01:36** |

**Del does NOT prove an active writer regression.** The fix was in the tree eleven
hours earlier, but a commit landing in the working tree says nothing about what the
running uvicorn process had imported, and the stack is started by hand.
**Classified: historical / pre-deployment-indeterminate.** The classifier's
"ACTIVE WRITER DEFECT INDICATED" line is withdrawn.

**Writers that still drop the owner** (neither currently UI-reachable, both able to
create an ownerless session if called):

* `prompt_composer.py:4024` — `db.ensure_session(conv_id)`, no owner.
* `api.py:790` and `:1006` — `upsert_session(conv_id, title, payload)` with no
  `person_id`, three lines after extracting `_deferred_profile.get('person_id')`
  into `payload['active_person_id']`. The owner is in hand and goes into a JSON
  blob instead of the column that exists for it.

`ensure_session`/`upsert_session` themselves are correct: `person_id =
COALESCE(sessions.person_id, excluded.person_id)` means **first non-NULL wins**, so
these rows are NULL because no writer ever passed one.

## E. The 81-session classification

912 of 1016 sessions have no owner; **81** have exactly one accepted owner.
They are not 81 lost conversations.

**Structural provenance outranks autobiographical vocabulary.** The tests were
written to sound real, so sounding real is evidence of nothing. Two earlier
classifiers failed on this and are superseded, with their failures recorded in
their own headers:

* keyword version — counted `[SYSTEM: …]` injections as narrator speech
  (one session reported 2,170 "narrator chars" where Christopher typed **"hi"**),
  missed byte-identical replay, promoted seven Walt replays and four
  `factual_chain_live_*` replays to "narrator history";
* identity-only version — fixed identity and whole-session replay but still let
  vocabulary decide *inside* the family set.

**36 of the 81 belong to synthetic personas** — Walt ×7 at exactly 14,420 chars
each, `trip_canary` ×9, `factual_chain_live` ×4, `spanish_smoke` ×2, `gate7p2`
harness ×6, Amelia ×8. Byte-identical narrator input across sessions is a harness
fingerprint; a person does not retype 14,420 characters identically.

**Christopher's 42** reflect the period he was building the travel-document, photo,
guard and safety systems using himself as the narrator:

| disposition | n |
|---|---|
| UNCLEAR — human review | 9 |
| DEVELOPMENT/TEST — unique content to salvage | 9 |
| DEVELOPMENT/TEST — content duplicated elsewhere | 8 |
| MIXED development + real content | 7 |
| EMPTY/STRUCTURAL SHELL | 6 |
| CANONICAL NARRATOR HISTORY | 3 |

The three canonical candidates: `switch_mrb7cut9_04pi`, `switch_ms8z59ie_xakt`,
`switch_msaiqgs2_a1mu`.

Turn-level replay detection resolved the confusing July cluster:
`switch_mrkt2k62_1h3v` reads autobiographically (father, mother, Rusty, school) and
contains **zero unique narrator content** — all five turns replay fixtures from
`guardsmoke`/`guardtest`.

## F. Family disposition

| narrator | finding | package implication |
|---|---|---|
| **Janice** | `switch_ms18e7zp_z62u` — 2 turns, the only user row is an injected `[SYSTEM: Janice is returning…]`, **zero narrator-authored speech**. EMPTY/STRUCTURAL SHELL | **no replacement needed** |
| **Kent** | `harness-1785381831` — test-prefixed, content duplicated in `harness-1785381790` | **no replacement needed** |
| **Del** | duplicated development material; pre-deployment-indeterminate | none |
| **Christopher** | 42 sessions as above; salvage list refined to the table below | **new authoritative package required** |

### The final salvage list — adjudicated by Chris, 2026-09-13

Twelve candidates were re-judged; the automated pass returned four "genuine", and
**Chris corrected two of them**. The corrections are recorded because both are
limits of the method, not of the data:

| turn | text | verdict |
|---|---|---|
| `tdlab_9538…` [1482] | "I went to my grandparents gravesite and my old schools with Melanie." | **GENUINE — salvage.** The strongest unique life/travel fact found, and the only one naming Melanie |
| `switch_mre0txvh_tb7w` [1182] | "I was not in the outfit it is a picture of men in lederhosen" | **PHOTO CORRECTION.** Belongs in photo context/metadata, not memoir prose — so preserving it does NOT require keeping the session |
| `switch_mrkpipjr_twr7` [1218] | "My mother sewed all our clothes. She was patient with me." | **CHRIS REVIEW.** The first clause is a fixture used repeatedly elsewhere; only "She was patient with me" is novel. Not automatically canonical |
| `tdlab_9538…` [1448] | "We spent the morning walking… the light looked on the water…" | **UNCERTAIN / likely fixture.** Repeated three times inside one lab session. Does not migrate automatically |
| `tdlab_9538…` [1532] | "Gravesite of my mom's parents, in Bismarck." | **ALREADY SURVIVES.** `trip_location_notes` holds "i went to visit my moms parents gravesite in Bismarck." Token Jaccard scored 0.43 and the script called it genuine; **that was the algorithm being conservative about two sentences that state the same fact.** Corrected by Chris |

**Net position: at most one genuine family fact plus one photo correction require
deliberate salvage**, from an investigation that began with 28 "missing" turns and
nine dangling references. Two further items await Chris's judgement.

Two method limits worth carrying forward: token-overlap scoring cannot recognise a
paraphrase, and "unique text" is not "memoir content" — a photo correction is
genuinely valuable and genuinely not narrator history.

**Do not rebuild Janice's or Kent's package on account of these sessions.** Only an
independent defect would justify it.

## G. The three dangling-reference sessions

**"Content safe to discard" and "referentially safe to delete" are different
questions.** A session whose information survives elsewhere may still be named by
ledger rows that a package carries.

| session | turns | dangling turn ids | content preservation | semantic reference |
|---|---|---|---|---|
| `switch_ms81wxvv_pxxh` | 10 | 1455, 1461, 1467, 1471, 1477 | whole session safe to discard — the gravesite/schools material survives in `trip_location_notes`; the rest is capability probing | **OPEN** — 5 ledger rows |
| `switch_ms8xrcuw_adlz` | 8 | 1515, 1517, 1529 | human review; 94 chars, both turns capability questions about seeing trip photos | **OPEN** — 3 ledger rows |
| `switch_msaedccx_fkm1` | 10 | 1579 | essentially empty — narrator typed **"hi"**; 4 injected system turns | **OPEN** — 1 ledger row |

The 28 turns are not themselves precious, which lowers the stakes on the repair
choice: removing stale derived references may be preferable to forcing all 28 into
the final package. **That decision is not made here.**

## H. Next actions, on returning to the desktop

1. Bank the already-green semantic-reference production repair (20/20 focused,
   133/133 bank).
2. Bring this findings document into the desktop branch if needed.
3. Design the laptop source-data repair from these findings.
4. **Do not blindly backfill all 81 sessions.**
5. Repair only the family data actually intended to survive.
6. Produce a new authoritative Christopher laptop package.
7. Rerun Christopher's clean-root restore / re-export semantic proof.
8. Rerun **only** Christopher's two-origin comparison.
9. Only then begin Merge/Remap.

Open and deliberately unresolved: whether `turn_extraction_ledger → turns` should
join `COLUMN_ONLY_REFERENCES`; whether `interview_sessions.id → sessions.conv_id`
should become a declared `DirectOrExclusiveInbound` path; and the exact mechanism by
which 0044's pass 1 matched nothing.

## Tooling (all read-only, all under `scripts/`)

In the order they were used:

| script | what it established |
|---|---|
| `inspect_dangling_turn_origins.py` | the nine turns exist, in NULL-owner sessions. **Its `reached by: []` is a false negative** — see §B |
| `inspect_residue_session_provenance.py` | 0044's three recorded links, per conversation; pass 1 names Christopher |
| `audit_null_owner_sessions.py` | chronology, and the blast radius: 81 of 912 |
| `classify_null_owner_sessions.py` | the 81 by narrator, writer prefix and date; raised the Del post-fix question |
| `migration_0044_verdict.py` | runner semantics. **Its rowid watermark is circular and withdrawn** — see §C |
| `migration_0044_literal_predicate.py` | the literal pass predicates, and order-consistency in place of the withdrawn test |
| `del_deployment_chronology.py` | Del is pre-deployment-indeterminate, not a live regression |
| `classify_sessions_for_preservation.py` | **superseded** — keyword heuristic, counted `[SYSTEM:]` as speech |
| `classify_sessions_structural.py` | **superseded** — fixed identity, still let vocabulary decide inside the family set |
| `preservation_plan.py` | the classification that holds: structural provenance outranks vocabulary |
| `christopher_salvage_map.py` | per-turn survival against clean destinations |
| `christopher_salvage_final.py` | the adjudicated list; **two of its four "genuine" verdicts were corrected by Chris** |

Reports are written under `.runtime/two_origin/reports/`, which is **gitignored**.
They quote bounded excerpts of real narrator speech and must not be committed or
published.
