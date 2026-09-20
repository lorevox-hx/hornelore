# WO-03B — propose and accept

Design, 2026-09-20. Nothing implemented. One schema question needs a
ruling before any code is written; everything else reuses what exists.

ENABLES: a value Lori believes can be shown to a person, accepted or
declined, and recorded as either — instead of being written into the
biography unannounced or queued where nobody can reach it.

## The finding that reframes this work order

WO-03B was scoped as "add propose/accept". Tracing the surface first
shows the propose half **already exists in three places**. It is the
accept half that was never built — and two of those three places carry a
comment asserting a review surface that does not exist.

  `projection-sync.js:238-247`   protected identity paths from an
                                 untrusted source are diverted to
                                 `_syncSuggestOnly`
  `projection-sync.js:402-403`   any `suggest_only` write mode
  `projection_writer.py:203-215` a model correction aimed at an
                                 operator-owned field is deferred

What consumes them:

  `acceptSuggestion(fieldPath)`   `projection-sync.js:588-627` —
                                  **zero callers**
  `dismissSuggestion(fieldPath)`  `:632-639` — **zero callers**
  a review UI                     **does not exist**

The only place `pendingSuggestions` is rendered anywhere in `ui/` is a
read-only debug dump behind the Projection Debug toggle
(`hornelore1.0.html:10648`). No buttons, no count, no badge.

Two comments in the codebase state otherwise and are wrong:

  `projection-sync.js:235-236` — protected identity must "be explicitly
  approved by the operator via the Shadow Review candidates queue".
  `shadow-review.js` never reads `pendingSuggestions`. Its queue is
  `bb.sourceCards`, WO-13 truth rows and `bb.candidates`.

  `projection_writer.py:190-192` — asserts the deferral mechanism has
  "an accept/dismiss UI … and a review surface".

Live consequence: **Christopher carries 15 pending suggestions and Kent
14. None of them is reachable by any person.** They were deferred to a
surface that was never built, and they will sit there until someone
resets the narrator.

## Where the authoritative queue lives — the ruling's prerequisite

Asked directly, because a server cannot verify a queue it cannot see.

**The queue is server-side**: `interview_projections.projection_json.
pendingSuggestions`, a real column with a real router
(`routers/projection.py`). So verification is possible and the
prerequisite is not a blocker.

**But the queue is receiving nothing from either producer**, and has not
for over a month.

    the client producer  `_syncSuggestOnly` (projection-sync.js:559)
                         pushes into browser state. `_persistProjection`
                         -> `_sendMutations` (:796-813) sends `mutations`,
                         `removals`, `base_version`, `base_fields` and
                         NOT `pendingSuggestions`. So nothing it queues
                         reaches the server. Worse, the next projection
                         load overwrites it: `proj.pendingSuggestions =
                         serverPending` (:952).

    the server producer  `projection_writer.py:203-215`. Zero rows on
                         this database. It has never fired.

Measured live, read-only, 2026-09-20:

    Christopher  15 suggestions      Kent  14 suggestions
    all 29 carry the CLIENT key-shape  {fieldPath, value, confidence,
                                        turnId, ts}
    none carries the server-only keys  {supersedes, reason}
    oldest  2026-04-28        newest  2026-08-12

The newest is 38 days old, and Christopher's projection row was last
touched 2026-08-17 — **the date the whole-envelope PUT was replaced by
the field-level PATCH** ("Supervisor review 2026-08-17",
`projection.py:39-48`). Before that cutover the client sent whole
envelopes, so its suggestions persisted. After it, the client writes
field-level and `pendingSuggestions` is simply never sent.

So the 29 are fossils from the previous write architecture. **Every
suggestion generated in the last 38 days — including every blocked
protected-identity capture — was written to browser memory and
discarded.** The gate does not merely queue to an unbuilt surface; it
queues to nothing durable at all.

Nobody noticed because nothing has ever read the queue.

### Consequence for the plan: a step 0

A review surface built now would display 29 fossils over a dead queue.
The propose path has to persist before the accept path is worth
building.

### And propose should become server-owned

The obvious repair is to add `pendingSuggestions` to what
`_sendMutations` sends. That works, and it puts the client in charge of
the whole array: `ProjectionPatchRequest.pendingSuggestions` is
`Optional[List[Any]]` and "supplied -> that array is replaced", with no
validation of the contents.

If the client owns the array, then "the server verifies the acceptance
against the stored queue" verifies against whatever the client last
wrote — a client could file a suggestion and accept it in two calls.

That is the same trust shape WO-03A removed from the questionnaire
write, and the same answer applies: **a dedicated server endpoint that
APPENDS one suggestion**, rather than a client that replaces the array.
The server then owns the queue, and an acceptance checked against it
means something.

Proposed: `POST /api/interview/projection/suggestion`, appending a
single entry with a server-assigned `suggestion_id` and server `ts`.
The existing array-replacing PATCH field stays for the reset path only.

Being precise about what this buys, consistent with WO-03A: there is no
authentication on any of these routes, so this is not a boundary against
a hostile client. It is a boundary against the ACCIDENTAL case — a stale
client, a race, a resubmission — and it makes "accept" denote a real
prior proposal instead of an arbitrary write wearing an acceptance's
provenance. That is worth having and is not the same as security.

## The live defect this exposes

The identity gate is bypassed by the statement after it.

`app.js:6059` projects `personal.fullName` with `source: "interview"`.
That is a protected identity path from an untrusted source, so
`projectValue` blocks it, logs `blocked_protected_identity`, queues a
suggestion and returns false (`projection-sync.js:238-247`).

Thirteen lines later, `app.js:6072` calls `lvBbSyncIdentity`, which
writes the same name straight into `bb.questionnaire.personal.fullName`
(`bio-builder-core.js:1196`) and PUTs it through the unclassified legacy
route (`:1209`).

So the gate fires, warns, files a suggestion nobody can see — and the
value it was built to withhold reaches the biography anyway, by a second
route, carrying no provenance. The same pattern holds at `:6113`,
`:6208`, `:6237` and `:6294`.

This is not a new risk introduced by WO-03B. It is the existing
behaviour, now visible because WO-03A made the routes distinguishable.

## Ordering — and why it is not negotiable

The obvious plan is to reroute `_syncIdentityToBB` and
`_syncPrefillIfBlank` through propose. **Doing that first would be
destructive.**

Both currently fill blank fields in the operator's form. Route them to
propose while no review surface exists, and their values stop appearing
in the questionnaire and land in an invisible queue. The operator loses
prefill and gains nothing, with no way to recover the values. That is
strictly worse than today.

So, with the step 0 the queue trace forces:

    0. make propose PERSIST           server-owned append endpoint; the
                                      client's suggestions have not
                                      reached the server since 2026-08-17
    1. the review surface             the accept half that is missing
    2. accept and decline             server-side, provenance-recording,
                                      verified against the stored queue
    3. exercise on a disposable       including repeatable entries, per
       narrator                       the ruling: a person must review,
                                      accept or decline, and see the
                                      correct resulting questionnaire
    4. THEN reroute the two writers   they finally have somewhere to go
    5. then the correction path       `projection_writer`'s deferrals
                                      become reachable (they never fired)

The step the work order was named for is fifth in dependency order.

⚠ Step 0 was not in the approved plan. It is not scope creep — without
it steps 1-2 are built over a queue that receives nothing, and the
acceptance condition in the ruling ("a person must be able to review
them") cannot be met for anything generated after 2026-08-17.

## Accept must be a server operation

The existing client `acceptSuggestion` cannot be the accept path, for
three reasons.

**It launders.** `projection-sync.js:619-623` sets
`proj.fields[fieldPath].source = "human_edit"` and `locked = true`. That
rewrites a machine suggestion as a human edit — the exact laundering
WO-03A exists to prevent, and the reason `origin` is permanent in 0059.
An acceptance must ADD `confirmed_via` / `confirmed_at` to a row whose
`origin` stays `ai_suggested`.

**It is client-declared.** Same trust problem as the operator route:
whoever posts decides its own authority. Accept belongs on a dedicated
server endpoint, and the origin comes from the endpoint.

**It is broken for repeatable sections.** `:600-618` handles only the
non-repeatable branch — it ignores `parsed.index`, so accepting
`parents[0].occupation` writes to the wrong shape.

Proposed: `POST /api/bio-builder/questionnaire/accept-suggestion`,
carrying `person_id`, the `fieldPath`, and the value being accepted.
Server-side it resolves the path against the stored document, writes the
value through the same `_write` transaction, and stamps provenance with
`origin='ai_suggested'`, `proposed_by='lori'`,
`confirmed_via='acceptance'`, `confirmed_at=now`.

The value is echoed back in the request and **compared** server-side
against the queued suggestion. A mismatch is refused rather than
accepted — otherwise "accept" becomes an arbitrary write wearing an
acceptance's provenance.

An operator who wants a DIFFERENT value is not accepting. That is an
ordinary operator entry through the WO-03A route, and it correctly
records `operator_direct`.

## Declines — RULED: option B, a separate table

Approved 2026-09-20 with four requirements. Shape proposed against them:

```sql
CREATE TABLE IF NOT EXISTS declined_suggestions (
  person_id     TEXT NOT NULL,
  section       TEXT NOT NULL,
  entry_id      TEXT NOT NULL DEFAULT '',   -- WO-02 _entryId
  field         TEXT NOT NULL,
  value_hash    TEXT NOT NULL,              -- sha256 of the canonical form

  -- REQUIREMENT 4b: "retain enough information to explain what was
  -- declined without depending solely on an opaque hash." The hash
  -- answers "is this the same proposal again"; it cannot answer "what
  -- did we turn down", which is the question a person asks a year later.
  declined_value TEXT NOT NULL,             -- as proposed, verbatim
  field_path     TEXT NOT NULL,             -- the dotted path proposed
  proposed_at    TEXT,                      -- the suggestion's own ts
  source_turn_id TEXT,

  declined_at   TEXT NOT NULL,
  declined_by   TEXT NOT NULL DEFAULT '',   -- unverified, as elsewhere

  PRIMARY KEY (person_id, section, entry_id, field, value_hash),
  FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE
);
```

Against the four requirements:

**Match on narrator, entry id, field and value.** The primary key is
exactly that. `entry_id` not ordinal, so a reorder cannot make a
declined proposal look like a fresh one about a different relative —
same reasoning as 0059.

**Canonical value before hashing.** Proposed canonicalisation:
`NFC` normalise, strip leading/trailing whitespace, collapse internal
runs of whitespace to one space, casefold. So "Minot , ND " and
"minot , nd" hash alike. Deliberately NOT normalising punctuation or
word order: "Minot, ND" and "ND, Minot" are different claims and a
person declining one has not declined the other. The canonical form is
computed by one function, used by both the decline write and the
re-proposal check, so the two cannot drift.

**Record durably BEFORE removing from the visible queue.** The decline
endpoint writes this row and removes the queue entry in one server-side
transaction. A decline that vanishes from the queue without a record
would re-offer itself on the next extraction, which is the failure the
table exists to prevent.

**Identical suppressed, materially different still reviewable.** The
propose path checks the canonical hash before appending. Same hash →
not queued, and the attempt is counted rather than silently dropped so
"Lori keeps trying to tell you X" stays observable. Different value →
queued normally. A person who declined "6th grade" still gets asked
about "7th grade".

**Exports and erasure.** `FOREIGN KEY ... ON DELETE CASCADE` plus a
`DbLane` in `narrator_data_inventory`. Class AUTHORITATIVE, portable
YES — a narrator restored elsewhere without their declines would be
re-asked everything they have already refused.

**Not a biographical fact.** The table records that a proposal was
refused. It does not record that the opposite is true: declining
"born in Duluth" does not establish where they were born, and nothing
may read it that way. Stated here because a `declined_suggestions` row
is exactly the kind of record a later feature would be tempted to mine
for negative facts.

Also to decide during implementation, flagged not assumed: a decline is
scoped to a questionnaire answer `(section, entry_id, field)`, but a
suggestion arrives as a dotted `fieldPath`. `identify_path` resolves one
to the other only against a document — and for an indexed path with no
stored entry yet, there is no `entry_id` to key on. Proposal: such a
suggestion declines against `entry_id=''` and the dotted path, which
suppresses re-proposal at the section level. Narrower than ideal and
honest about it.

## The original options, retained for the record

**A declined suggestion currently leaves no trace.** `dismissSuggestion`
filters the entry out of the array and logs to the console
(`:632-639`). Nothing records that a person saw it and said no.

That has a cost: the same extraction will re-propose the same value on
the next turn that mentions it, and the person declines it again, and
again. A queue that cannot remember a refusal is a queue that nags.

Three options:

  A. **Keep declines in the provenance table.** A row with
     `origin='ai_suggested'`, `confirmed_via='declined'`, and no value
     written to the questionnaire. No migration — 0059's columns already
     carry it. Cost: a provenance row that describes a value which is
     deliberately NOT in the document, so `load_provenance` consumers
     must handle "provenance for an absent answer". That is a real
     semantic wrinkle in a table whose current invariant is that every
     row describes a stored value.

  B. **A small `declined_suggestions` table**, keyed
     `(person_id, section, entry_id, field, value_hash)`. Keeps 0059's
     invariant intact. Costs a migration.

  C. **Do not record declines at this stage.** Re-proposal remains
     possible. Smallest change; defers the nagging problem.

RULED: **B**, for the reason given — the provenance table keeps meaning
one thing, and a declined proposal is a different kind of record from
the origin of a stored answer.

## Scope

IN: the review surface; the server accept and decline operations;
rerouting `_syncIdentityToBB` and `_syncPrefillIfBlank` through propose
once the surface exists; making `projection_writer`'s deferred
corrections reachable; correcting the two false comments.

OUT: the REST chat session-ownership defect (`api.py:799-800`) — a
tracked defect, resolved before integrated acceptance of narrator
evidence across transports, not absorbed here. The fanout flag stays 0.
Narrator-storage separation.

NOT CLAIMED: the operator endpoint establishes which operation was
invoked, not who invoked it. There is no operator authentication, and
`actor_id` is an unverified claim. An acceptance records that an
acceptance arrived on the accept route — not that a named person agreed.

## Ruled, 2026-09-20

1. **Declines — option B.** Separate table, four requirements, shaped
   above.
2. **Rerouting lands separately**, after the surface has been exercised
   on a disposable narrator including repeatable entries. The acceptance
   condition is not that suggestions appear: a person must review,
   accept or decline, and see the correct resulting questionnaire state.
3. **The existing 29 are reviewed, not bulk-handled.** Values and
   origins preserved. No auto-acceptance, no silent deletion, no
   inferred confirmation.
4. **Accept must act on the queued suggestion that actually exists** —
   verified for identity, current value, narrator ownership and
   destination field against stored state before the answer and
   provenance commit together. Declines likewise act on an identifiable
   proposal, never on a client's assertion that something was offered.

## One thing the ruling asked that the trace answers differently

The ruling said: "If `pendingSuggestions` exists only in browser state,
that is a prerequisite to resolve."

It does not exist only in browser state — the column is real and
server-side, so verification is possible. But the client has not written
to it since 2026-08-17 and the server producer has never written to it
at all. So the prerequisite is not "move the queue to the server". It is
"**make the queue receive anything**", which is step 0 above.

The 29 existing suggestions are reviewable as soon as a surface exists.
Anything generated since 2026-08-17 is already gone and cannot be
recovered — it was never persisted anywhere but a browser.
