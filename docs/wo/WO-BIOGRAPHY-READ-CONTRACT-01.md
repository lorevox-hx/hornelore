# WO-BIOGRAPHY-READ-CONTRACT-01 — source precedence, written down before code

Phase 1 deliverable. Source inspection 2026-09-18, stack down. Every claim
below is from the code as it stands; nothing here has been run.

Supersedes the "which store wins" question left open in
WO-QUESTIONNAIRE-REACHES-LORI-01.

## The decision: extend `interview_projections`, repair the READ boundary

`interview_projections` already has what a biography read surface needs on the
write side:

  - per-path provenance — `source`, `locked`, `confidence`, `history[]`
    (`ui/js/projection-sync.js:281-289`)
  - per-path optimistic concurrency via `base_fields`
    (`db.py:7038-7041`)
  - atomic compare-and-write under `BEGIN IMMEDIATE` (`db.py:7025`)
  - a trusted-source allowlist and a pending-suggestion queue for untrusted
    writes to protected paths (`projection-sync.js:238-247, 323-325`)

That is the same contract built for the questionnaire in
BUG-BIO-QUESTIONNAIRE-LOSSY-ROUNDTRIP-01, and it was here first. Building a
fifth store would duplicate it.

**The failure is not the store. It is one function at the read boundary.**

## What the read boundary does today

`prompt_composer._build_profile_seed`, `prompt_composer.py:1143-1159`:

    for fp, v in proj_fields:      provisional[fp] = v.strip()
    for s  in proj_suggestions:    provisional.setdefault(fp, v.strip())

Three consequences, all of them the reason this work order exists.

**1. Provenance is discarded.** Only `entry["value"]` is read. `source`,
`locked`, `confidence`, `turnId`, `ts`, `history` never leave the database.
The result is typed `Dict[str, str]`.

**2. Unreviewed suggestions become established facts.** `pendingSuggestions`
is the queue for UNTRUSTED writes to protected identity paths — a model's
guess, deliberately held back from the record pending review
(`projection-sync.js:552-582`). It is merged into the same flat namespace as
operator-typed values. The only difference that survives is collision
precedence.

So a model's unconfirmed guess about a narrator's birthplace reaches Lori's
prompt indistinguishable from something the operator typed. The queue is
built correctly and then flattened on the way out. `services/profile_seed.py:
588-599` does the same thing independently.

This is live today and unrelated to the questionnaire. It should be fixed
first, on its own, because it is a correctness defect in the current product
rather than a gap in a planned one.

**3. Only ten paths reach the prompt.** `prompt_composer.py:1241-1394`
consults exactly: `personal.preferredName`, `personal.fullName`,
`personal.placeOfBirth`, `personal.culture`, `personal.dateOfBirth`,
`education.schooling`, `education.higherEducation`,
`education.careerProgression`, `education.earlyCareer`, `community.role`.

Everything else is read into `provisional` and silently ignored.
`parents[1].occupation` is not in that set. Writing questionnaire facts into
projections, on its own, would NOT deliver Bertil's occupation to Lori.

`services/profile_seed.py:237-294` keeps a SECOND, different registry of
which projection paths count as evidence. The two do not match.

## THE PRECEDENCE RULE

Stated before any code, as required. Applies wherever a biography fact is
resolved for a consumer.

### Tier order, highest authority first

    1. OPERATOR ENTERED     source == "human_edit", OR locked == true
                            Someone deliberately typed this into Bio Builder.
                            `locked` counts on its own and is STICKY: a later
                            writer only got to touch a locked field by not
                            conflicting with it, so the claim stands even
                            though the last `source` names that writer. It is
                            exactly as client-asserted as source ==
                            "human_edit" is, so honouring both adds no new
                            trust.

    2. NARRATOR STATED      RESERVED. No producer today.
                            The narrator's own assertion, unmediated. Every
                            "the narrator said it" path in the codebase is a
                            MACHINE PARSE of speech, so nothing may claim this
                            tier yet.

    3. DOCUMENT SOURCED     RESERVED. No producer today.
                            Evidence from a document. Nothing in the
                            projection layer produces one; `document_authority`
                            writes bio_facts, not projections.

    4. MODEL INFERRED       interview, backend_extract, backend_correction,
                            projection, correction
                            A machine's reading. `correction` belongs here:
                            apply_correction has one caller (chat_ws.py:5093,
                            the correction turn-mode) and its input is a
                            model's parse of something said in conversation.
                            No document is involved.

    5. SEEDED / HYDRATED    preload, profile_hydrate, profile_seed
                            Derived from another store; never authority over
                            its own source.

    NOT A TIER — pendingSuggestions. An unreviewed candidate is not a fact at
    any tier. It must never resolve as a value. It may be OFFERED to a
    consumer that knows it is a suggestion; it may not be flattened into the
    fact namespace.

### Why two tiers are deliberately empty

The first version of this contract mapped `correction` to document_sourced,
and the implementation then classified a model's parse of a conversational
correction as documentary evidence. That is the exact distinction this whole
repair exists to create, inverted.

What the code can actually distinguish today is three things: a person typed
it, a machine parsed it, or it was copied from another store. Tiers 2 and 3
stay DEFINED because they are what a future writer should claim, and stay
EMPTY so nothing claims them by accident.

A genuinely documentary correction path must introduce its own source string.
It must not reuse "correction", which now means only "a model's reading of a
correction".

### Resolution

  - Highest tier present wins.
  - Within a tier, most recent `ts` wins.
  - A `locked` field is never overwritten by a lower tier. This gate exists
    in the browser (`projection-sync.js:212-215`) and is NOT enforced
    server-side; the server stores field objects opaquely (`db.py:7074`).
    Moving it server-side is in scope.
  - Resolution returns the value AND its tier and source. A consumer that
    wants only the string may take it; a consumer that renders provenance has
    it. The flattening happens at the caller, never in the resolver.

### Disagreement

Two sources disagreeing at the SAME tier is a conflict, not a race. Today it
produces a 409 and the losing value is discarded — not persisted as a row, a
marker or a log entry (`db.py:7046-7057`, `projection_writer.py:289-301`).
The code comments point at an operator review queue that does not exist for
projections; `identity_change_log` (`db.py:6753-6774`) has the right shape —
`status`, `accepted_by`, `resolved_at` — but is wired to `people`/`profiles`.

A disagreement between a questionnaire fact and a chat-extracted one is
exactly the case this system exists to handle well: the operator typed what
their mother told them; the narrator said something different on a Tuesday.
Neither should silently win, and neither should vanish.

Retaining conflicts is therefore in scope, and is the one place this work
order adds storage rather than reusing it.

### Correction history

`history[]` is browser-authored, capped at 10, and destroyed by the server
correction writer, which builds a fresh field dict with no `history` and no
`locked` (`projection_writer.py:160-166`). A retraction deletes the field
outright with no persisted trace (`:229-241`). There is no revisions table;
the row is overwritten in place (`db.py:7092-7102`).

`bio_builder_questionnaire_revisions` (`0058_questionnaire_revisions.sql:
72-113`) already stores prior document, `changed_paths`, `removed_paths`,
`previous_values`, `write_kind` and `superseded_by_source`. That is the shape
projections need and do not have.

## What "authoritative" means here, precisely

The questionnaire stays the authoritative record of **what the operator
entered**. It is not the authoritative record of **what is true about the
narrator** — the narrator's own statements and documentary evidence can
outrank it, and the tier order says so.

`interview_projections` is classified `CLASS_DERIVED` in
`narrator_data_inventory.py:206`. If it becomes the resolution surface that
question must be revisited deliberately, because a derived lane is erasable
and rebuildable by definition, and a store holding conflict records is
neither.

## Smallest safe first slice

In order, each independently useful:

**A. Stop unreviewed suggestions reaching the prompt as facts.**
`prompt_composer.py:1150-1159` and `profile_seed.py:592-599`. Standalone
correctness fix, no new storage, no questionnaire involvement.

**B. Carry provenance through the read.** Return tier and source alongside
value; let callers flatten. Keeps every current consumer working.

**C. Widen the path set, or make it data-driven.** Ten hardcoded paths in
`prompt_composer` and a different registry in `profile_seed` is the reason a
new fact silently goes nowhere.

**D. Then, and only then, a questionnaire → projection writer**, using
`merge_projection_fields` with `base_fields` — mutations, no removals. Never
`update_profile_json`, whose top-level `merged.update()` (`db.py:2977`)
replaces a whole array and is the lossy-roundtrip defect in another table.

## Explicitly out of scope here

Server-side enforcement of the trust/lock/confidence gates that currently
live only in `projection-sync.js`; conflict-record storage; a projection
revisions table. All three are named because they are missing, and should be
separate work orders rather than smuggled into a read-path change.
