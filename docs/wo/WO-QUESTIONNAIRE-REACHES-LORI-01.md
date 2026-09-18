# WO-QUESTIONNAIRE-REACHES-LORI-01 — the biography does not reach the narrator

Source trace, 2026-09-18, with the stack down. Read paths only; no live
conversation was run. Findings are from the code as it stands in the working
tree.

## The finding

An operator saves `parents[1].occupation = "ore dock foreman"`. It is durably
stored, versioned, audited and recoverable — and **Lori cannot see it.**

    written   questionnaire_persistence.py:465  -> bio_builder_questionnaires
    read by   db.get_questionnaire (db.py:6816) -> and nothing else

The three callers of `get_questionnaire` are all operator-facing:

  - `routers/questionnaire.py:112`          the Bio Builder GET
  - `routers/chronology_accordion.py:1335`  the accordion UI payload
  - `db.get_narrator_state_snapshot:7247`   emitted as `"questionnaire"`

And of the snapshot's three consumers, the two on the conversation side drop
the key without reading it:

  - `routers/interview.py:671-677`  uses person / profile / user_turn_count
  - `routers/extract.py:10150`      uses protected_identity

Lori's prompt is assembled by `prompt_composer._compose_prompt_assembly`
(`prompt_composer.py:3979`) from `profiles.profile_json`,
`interview_projections.projection_json`, the `people` row, the client
`runtime71` payload, and transcripts. **It never reads
`bio_builder_questionnaires`.**

## Two breaks, not one

**Break 1 — the bridge is off.** `_fanout_writes_enabled()`
(`routers/questionnaire.py:93`) defaults to `"0"`; the live `.env:183` sets
`HORNELORE_QUESTIONNAIRE_BIO_FACTS_WRITE=0`. So
`bio_questionnaire_writer.apply_questionnaire_writes` never runs.

**Break 2 — the bridge would not carry this fact anyway.** With the flag on,
`_apply_parents` (`bio_questionnaire_writer.py:185-240`) writes exactly three
bio_facts keys: `father_name`, `mother_name`, `mother_maiden_name`. An
occupation is not among them. It would travel only inside
`profile_json.parents[]`, reaching Lori as `seed["parents_work"]`
(`prompt_composer.py:1282-1307`) — a memory-echo readback and a
topic-suppression signal, not a fact she can answer a question from.

So "turn the flag on" is not the fix, and would produce a misleading partial
success: some names arrive, the biography does not.

## DO NOT SIMPLY ENABLE THE FLAG

`db.update_profile_json` (`db.py:2970-2991`) merges at the TOP LEVEL only:

    merged.update(profile_json)        # db.py:2977

A patch containing `parents` therefore REPLACES the whole parents array. That
is the same shape as BUG-BIO-QUESTIONNAIRE-LOSSY-ROUNDTRIP-01 — a partial view
written back over a fuller record — pointed at `profile_json` instead of the
questionnaire. Two days were spent removing that behaviour from one table; the
bridge would reintroduce it into another.

Whatever carries questionnaire data forward must use the merge contract
already built for this: populated leaves applied as mutations, no removals
(`questionnaire_persistence.merge_whole_document`). Not `update(...)`.

## A stale comment that asserts the opposite

`prompt_composer.py:1075-1077`:

> "Bio Builder questionnaire state — folded into profile_json by the
> questionnaire endpoint already"

True only at flag=1. The accurate note is at `prompt_composer.py:2875-2876`:
the questionnaire "exists at /api/bio-builder/questionnaire but isn't threaded
today." Fix the first comment regardless of what else is decided — it is the
kind of note that persuades a future reader not to check.

## What has to be decided, not just implemented

**Which representation is authoritative for Lori.** There are three candidate
stores — `bio_facts` (flat, typed, status-bearing), `profile_json` (nested,
narrator-shaped), `interview_projections` (per-path, versioned, with
provenance). The questionnaire is a fourth. Adding a fifth path without
deciding which one wins is how a fact comes to exist in two versions.

**Provenance must survive the hop.** An operator-entered fact and a
model-inferred suggestion must remain distinguishable at the point Lori reads
them, or an unconfirmed candidate becomes a confident statement about somebody
alive. `interview_projections` already carries per-path source and
`markHumanEdit`; `profile_json` does not.

**Facts are not recollections.** Lori knowing Bertil was an ore dock foreman
must let her ask about it. It must not let her narrate it as Thorvald's
memory. That distinction lives in prompt construction, not in the data layer,
and needs stating wherever the fact is injected.

**Narrator isolation.** Every read path traced is `WHERE person_id = ?` and no
cross-narrator read was found. Any new path must keep that.

## Scope of this trace

Read paths only, from source, stack down. NOT established here: the memoir
planning/drafting/assembly paths, what happens to a corrected fact already used
in a draft, and the behaviour of any of this at run time. The live walkthrough
(enter Bertil, restart, ask Lori about Thorvald's father) remains the
acceptance and has not been run.

## Priority

This outranks deletion, per-entry save, durable status and death dates. Those
improve a biography the operator is entering. This is about whether entering it
accomplishes anything at all.
