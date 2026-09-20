# AUDIT — questionnaire data integrity and confirmation

2026-09-18. Source-level, with behavioural reproductions where stated.
No live narrator data was read, written or migrated. The fanout flag stayed
at 0. The questionnaire→projection writer was not started.

Every finding is classified:

  DEMONSTRATED DEFECT   reproduced by executing code (harness, unit test, or
                        live walkthrough)
  SOURCE-CONFIRMED GAP  established by reading the code path; not reproduced
  UNVERIFIED RISK       plausible from the design; not established either way

Findings already repaired in commits through `6639364` are listed for
completeness and marked FIXED, because the repair sequence at the end depends
on knowing what is closed.

---

## Part 1 — The three actions, end to end

The question the owner's rule asks: can the system tell apart

  (A) a person types an answer
  (B) Lori proposes an answer
  (C) a person accepts Lori's proposal

**Answer: only (B) on protected identity paths, and only in one of two lanes.
(A), (B) elsewhere, and (C) are the same bytes on the wire and the same row
in the database.**

Every questionnaire value lands through ONE endpoint,
`PUT /api/bio-builder/questionnaire` (`routers/questionnaire.py:134`). Its
request carries `person_id`, the whole document, a free-form `source` string,
and an `operator_id` that no client has ever sent. The document is plain
values. There is no per-field author, source, or status anywhere in it.

`_persistDrafts` has ~20 callers across five modules. All of them funnel
through `_persistQuestionnaire` (`bio-builder-core.js:386`), which emits the
literal `source: "ui_save"`. A typed answer, a Lori-derived identity capture,
an accepted suggestion, a model prefill, and a narrator-switch flush arrive
identically.

The API is unauthenticated (`main.py:98-110`; the CORS comment says so in
terms). The server cannot identify a session, a route beyond the endpoint, or
an actor. `bio_builder_questionnaire_revisions` records what changed and when,
and which `source` string replaced it — never who.

---

## Part 2 — Findings

### Cause A · The server does not know who wrote anything

**A1 · SOURCE-CONFIRMED GAP — no per-field provenance in the questionnaire.**
`questionnaire_json` is `{parents: [{occupation: "ore dock foreman"}]}`.
Nothing records who entered it, when by whom, or whether anyone confirmed it.
(`questionnaire_persistence.py:506-542` flattens to bare leaves.)

**A2 · SOURCE-CONFIRMED GAP — every persist route is `source: "ui_save"`.**
The one string that would distinguish routes is emitted by one function for
all of them. The four routes that DO send a distinct string
(`session_loop`, `bug227_identity_rescue`, `operator_intake_tab:*`,
`test_harness`) are client-chosen and unverifiable.

**A3 · SOURCE-CONFIRMED GAP — no actor identity exists to record.** No auth,
no session, `operator_id` never sent, no actor column on any questionnaire
table. The only `accepted_by` in the schema is `identity_change_log`, wired to
`people`/`profiles`, unrelated to the questionnaire.

**A4 · SOURCE-CONFIRMED GAP — projection provenance is client-asserted.** The
server stores field objects opaquely (`db.py:7074`); `mutations` is
`Dict[str, Any]` (`routers/projection.py:74`). Any client may claim
`source: "human_edit"` on any path. `_projection_provenance` now says so in
its docstring; it still honours the claim, because there is nothing else to
honour.

**A5 · SOURCE-CONFIRMED GAP — the fanout bridge would launder everything.**
With `HORNELORE_QUESTIONNAIRE_BIO_FACTS_WRITE=1`, `_write_bio_fact`
(`bio_questionnaire_writer.py:109-122`) stamps every questionnaire-derived
fact `status="operator_entered"`, `kind: "operator"`, `confidence: 1.0` —
including values Lori put there. And `update_profile_json` replaces
`parents` wholesale (`db.py:2977`). The flag stays 0.

### Cause B · Lori's writes walk around the gate that exists for them

**B1 · SOURCE-CONFIRMED GAP — `_syncIdentityToBB` bypasses protected
identity.** `app.js:6059-6064` calls `projectValue(..., source:"interview")`
on `personal.fullName/dateOfBirth/placeOfBirth` — protected paths — and is
correctly diverted to `pendingSuggestions`. Eight lines later
(`app.js:6072-6073`) `lvBbSyncIdentity` writes the same value straight into
the questionnaire and PUTs it as `"ui_save"`. Same values, same turn, gated
in one lane and not the other. Five call sites (`app.js:6072, 6113, 6208,
6237, 6294`).

**B2 · DEMONSTRATED DEFECT (2026-09-20, read-only trace of live rows) —
machine extractions are committed directly as facts, and Lori reads them.**
On non-protected paths a `backend_extract` / `interview` value is written
straight into `interview_projections.fields` — no queue, no review. Seen in
real data: Kent's committed `education.schooling` is "induction physical and
testing in Fargo" and `education.earlyCareer` is "production photographer
for the Brigade", both `source: backend_extract`, both read into Lori's
profile seed as established biography. Christopher's education and career
buckets are the same shape. The suggestion queue only guards protected
identity paths; everywhere else the direct write IS the leak, and it is the
larger one. (`projection-sync.js:407-435`; callers `interview.js:1116, 1126,
1161, 1631`.) The questionnaire-side twin, `_syncPrefillIfBlank`, persists
the same values as `"ui_save"`.

  Evidence is reproducible: `lorevox_packages/suggestion_leak_trace.py`,
  read-only, prints per narrator what the pre-fix reader would have admitted,
  what the current reader admits, and each committed value with its source.
  Until its output has been reviewed this stands as a Claude-reported
  finding.

**B3 · SOURCE-CONFIRMED GAP — acceptance leaves no record, and has no
caller.** `acceptSuggestion` (`projection-sync.js:588-627`) deletes the
proposal (`:604`), writes the value into the questionnaire as an ordinary
answer (`:613`), rewrites the projection field to `source:"human_edit",
locked:true` (`:619-623`) with no history entry, and logs
`"suggestion_accepted"` to a `syncLog` that is explicitly never persisted
(`:875-877`). Nothing in the shipped UI calls it. Action (C) has no wired
entry point.

**B4 · DEMONSTRATED DEFECT, FIXED (`6639364`) — unreviewed suggestions
could reach Lori as facts.** Two readers flattened `pendingSuggestions` into
the committed namespace. Closed at the read boundary in both.

  Correction after tracing the real rows (2026-09-20): for Christopher (15
  suggestions) and Kent (14) this had NOT actually fired — every consulted
  path already held a committed field, so the `setdefault` never admitted a
  suggestion. "kind of scared" never became Christopher's name in a prompt;
  a committed `personal.fullName` shadowed it throughout. The fix changed
  nothing Lori says about the family today. Do not describe it as having.

  All 29 suggestions are intact, returned by `GET /api/interview/projection`,
  and surfaced by NO review UI: `app.js` loads and clears the array,
  `bio-builder-core.js` filters it on reset, `acceptSuggestion` has no
  caller. Retained, not reviewable. That control is WO-02B.

**B6 · REGRESSION OF MINE, specific repair owed (WO-02).** `prompt_composer.py:
5174-5186` records a deliberate May design: when a pending suggestion exists
for the field Lori is about to ask about, she should CONFIRM ("already on
record, provisionally: X — is that right?") rather than ask cold. The
6639364 fix removed suggestions from `provisional` and built a separate
`suggested` map — but never returned it in the seed, so `_known_childhood_home`
(`:5153`) lost its provisional input. No effect on Christopher or Kent, whose
birthplaces are committed. Repair: return `suggested` in the seed; have the
confirm-hint read from it, labelled provisional, never as fact. Test with a
synthetic narrator holding a pending suggestion and NO committed answer at
that path. The suggestion may be offered for confirmation; it must not be
presented as established.

**B5 · DEMONSTRATED DEFECT, FIXED (`6639364`) — a correction could overwrite
an operator's value and erase its history.** Now deferred to the suggestion
queue with `supersedes`; history and `locked` carried forward.

### Cause C · One value, two paths

**C1 · DEMONSTRATED DEFECT — the legacy migration duplicates six sections on
the server.** `_migrateRemovedSectionsToLegacy` runs unconditionally on every
restore and every save (`bio-builder-questionnaire.js:139-172`) and moves
`grandparents, auntsUncles, childhoodPlaces, schools, trips, memoryNotes`
under `_legacyRemovedSections`. `_saveSection` writes back to the top level.
Reproduced in the harness: save grandparents, then save personal — the PUT
carries only `_legacyRemovedSections.grandparents`; the server, correctly
applying no removals, keeps top-level `grandparents` too. Ervin Horne now
exists at two paths. `getSectionData` prefers the top-level copy, so a stale
top-level copy wins over a fresher legacy one after any cross-client or
restore cycle. This is also why value counts in the probe overstate: a
document with grandparents entered carries them twice.

**C2 · DEMONSTRATED DEFECT, FIXED (this commit) — my bookkeeping skip made
those six sections invisible.** `_hasOperatorContent` skipped every
`_`-prefixed key, so a narrator whose only content was grandparents was
classified EMPTY after the migration ran, and the blank-PUT guard refused to
save them. Reproduced: `_hasOperatorContent({_legacyRemovedSections:
{grandparents:[{firstName:"Ervin"}]}})` returned `false`. A regression I
introduced on the 17th. The rule is now about the value's shape, not the key
name.

**C3 · SOURCE-CONFIRMED GAP — positional entry identity.** `parents[0]`,
`parents[1]`. A removal renumbers; a concurrent edit and a removal can apply
to different people. Already acknowledged as deferred in the lossy-roundtrip
spec. Deletion (D1) is where it stops being theoretical.

**C4 · SOURCE-CONFIRMED GAP — two incompatible projection field shapes.**
Browser writes `turnId/ts/confidence:float`; `projection_writer` wrote
`turn_id/applied_at/confidence:"high"`. The writer now emits both spellings;
existing rows still carry one or the other.

### Cause D · Omission is not deletion, so nothing can delete

**D1 · DEMONSTRATED DEFECT — a family member cannot be removed.** No control
exists; clearing every field is a no-op. Reproduced in the harness and pinned
by assertion. Specced in WO-BIO-QUESTIONNAIRE-DELETE-ENTRY-01, deliberately
not built pending C3.

**D2 · DEMONSTRATED DEFECT — a single field cannot be retracted.** Same
mechanism, narrower case: an operator cannot clear a wrong occupation without
replacing it. Not only repeatable entries; every field. The server accepts
`removals`; the UI never sends any. Needs its own contract — the review is
right that the deletion WO is too narrow.

### Cause E · The read boundary

**E1 · SOURCE-CONFIRMED GAP — the questionnaire does not reach Lori.** Three
readers, all operator-facing. Fanout off. (WO-QUESTIONNAIRE-REACHES-LORI-01.)

**E2 · SOURCE-CONFIRMED GAP — only ten projection paths reach the prompt.**
`prompt_composer.py:1241-1394`. `parents[].occupation` is not among them. A
second, different registry in `profile_seed.py:237-294`.

**E3 · DEMONSTRATED DEFECT, FIXED (`6639364`, this commit) — provenance died
at the read boundary, then the vocabulary invented authority.** Tier now
carried alongside value; `correction` reclassified `model_inferred`;
`narrator_stated` and `document_sourced` defined but empty; `locked` sticky.

### Cause F · Conflicts vanish

**F1 · SOURCE-CONFIRMED GAP — a 409 discards the losing value.**
`db.py:7046-7057`; no row, marker, or log survives the request.

**F2 · SOURCE-CONFIRMED GAP — a retraction deletes the field outright.**
`projection_writer.py:229-241`; no persisted trace.

### Cause G · What is already stored

**G1 · SOURCE-CONFIRMED GAP — existing values have no provenance and cannot
be assigned any.** Janice's 100, Kent's 86, Christopher's 130. Some typed;
some via B1. Nothing distinguishes them. Defaulting to confirmed asserts
approval that may not have happened; defaulting to unconfirmed demotes
hand-typed history to a guess. They need a third state.

**G2 · Reviewed, resolved by the owner — six historical default matches.**
Kent and Janice alive; Ervin and Leila are Kent's parents; George and
Elizabeth are Ervin's. All six correct. No change. A formal "reviewed" state
for such values is part of G1's third-state work, so the review is recorded
rather than re-derived.

### UNVERIFIED RISKS — not established either way

**U1** Two people editing different fields of the same relative concurrently.
`base_fields` gives per-path concurrency on projections; the questionnaire's
`base_revision`/`base_fields` exist on the PUT model but no client sends
them.

**U2** A human editing an AI-proposed value: does it become confirmed without
falsely claiming the proposal was human? Unanswerable until provenance
exists; moot today because nothing is distinguishable.

**U3** Reset, restore, import preserving provenance — nothing to preserve
yet. BagIt export carries `bio_builder_questionnaire_revisions` (portable
"yes"); whether a future sidecar would need its own lane is a design input.

**U4** Cross-system disagreement after a partial operation — questionnaire
vs projection vs graph vs candidates. The confirmation boundary repair
(`5357b42`) means derived state now waits for a confirmed questionnaire
write; whether the projection PATCH that follows can fail independently and
leave the two apart is not tested.

**U5** Which live narrators hold `pendingSuggestions`, and therefore what
Lori stops seeing after `6639364`. Needs the stack.

---

## Part 3 — Consolidated repair sequence

Grouped by cause. Symptoms in the same group are fixed by the same change.

**R1 · Origin the server can vouch for — for the questionnaire AND for
projection writes.**  (A2, A4, B1, B2, B3, B4-adjacent, B6)

Expanded 2026-09-20 after the live trace: machine extraction currently
writes straight into `interview_projections.fields` on non-protected paths
and Lori reads it as fact (B2). Separating operations at the questionnaire
endpoint alone would leave that path open. R1 must trace and separate five
things wherever they write: machine extraction, narrator-direct statements,
operator entry, proposals, explicit acceptance — and the pending-suggestion
review control (accept / dismiss, with an acceptance record) belongs here.
The "confirm rather than ask cold" hint (B6) is restored here on the explicit
`suggested` channel.
Stamp origin from the ROUTE, not the payload: the Bio Builder save path, the
chat correction path, the session-loop answer path, the intake path. That is
knowable without authentication. Add a per-field provenance sidecar keyed by
the same dotted paths the merge already flattens to — `{origin, origin_at,
proposed_by?, confirmed_by?, confirmed_at?}` — written by the server on every
merge. Route `_syncIdentityToBB` and `_syncPrefillIfBlank` through the
suggestion queue like every other untrusted write. Wire `acceptSuggestion` to
a real control and make it write an acceptance record instead of deleting the
proposal.
  Depends on: nothing. Blocks: the questionnaire→projection writer.
  Does NOT solve: "who" as a person. That needs identity, which needs auth
  (A3), which is a product decision, not a repair.

**R2 · One path per value.**  (C1, C2-done, C3, C4)
Decide the canonical home for the six migrated sections and stop the
oscillation — either finish the migration server-side once, or stop it
running on every save. Then stable per-entry ids, because R3 cannot be built
safely on positions.
  Depends on: nothing. Blocks: R3.

**R3 · Explicit removal.**  (D1, D2)
One contract for clearing a field and removing an entry, both sending
explicit `removals`, both confirmed, both in revision history. Never
omission-as-deletion.
  Depends on: R2.

**R4 · Widen the read.**  (E2, then E1)
Replace the ten hardcoded paths with a registry shared with `profile_seed`,
so `parents[].occupation` can be consumed with its tier. Then, and only after
R1, the questionnaire→projection writer via `merge_projection_fields` with
`base_fields`.
  E2 depends on: nothing. E1 depends on: R1.

**R5 · Conflicts that survive the request.**  (F1, F2)
A durable record for a contested path — `identity_change_log` has the shape.
  Depends on: nothing. Independent.

**R6 · The third state for what already exists.**  (G1, G2)
`provenance: unknown, pre-dates distinction` on every existing leaf, with an
explicit reviewed flag the owner can set. No bulk relabel in either
direction.
  Depends on: R1's sidecar existing.

**Order, revised 2026-09-19/20 and agreed:** WO-01 (done, `31d229d`) →
stable entry ids (R2b) BEFORE any provenance, so the provenance sidecar is
keyed correctly from its first row rather than by position → R1, expanded
above → R3 removal → R6 third state → R4's E1 half, the bridge, last. R4's
E2 half (the path registry) and R5 (durable conflicts) are independent and
can slot in wherever.

**What this does NOT include, by design:** authentication. The rule says
"who entered or approved". Without a signed-in actor the system can say
"from the Bio Builder save route, on this session, at this time" and no more.
That is enough to stop Lori laundering her own suggestions, which is the rule's
sharp edge. It is not enough to distinguish two operators. Whether that
matters is the owner's call.
