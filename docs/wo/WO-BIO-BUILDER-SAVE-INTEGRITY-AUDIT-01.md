# WO-BIO-BUILDER-SAVE-INTEGRITY-AUDIT-01 — one bounded audit, not ten work orders

Raised 2026-09-18 from a code review, after the two-parent walkthrough passed.

The walkthrough closed a specific reproduction. It did not establish that the
same machinery is correct everywhere it is used. Five surfaces can disagree
about what has been saved — the DOM, `bb.questionnaire`, the localStorage
draft, the server document, and the derived biography — and every defect
found on 17–18 September lived on one of those boundaries.

## Why one block rather than a work order per section

The repeatable sections do not each have a save path. They share one, in
`_saveSection`, and one add path in `_addRepeatEntry`. That is why
BUG-BIO-QUESTIONNAIRE-SECOND-ENTRY-DROPPED-01 was never a Parents bug: the
mechanism served every repeatable section, and Parents is simply where
somebody happened to enter two people.

So the repair is shared and belongs in one place. What must be *per section*
is the TEST. Ten sections that share one code path still need ten two-entry
tests, because "it works for Parents" is exactly the reasoning that let this
ship.

## 1. Confirmed, needs repair: downstream work runs before confirmation

`_saveSection` starts persistence and then, without awaiting it:

  - `_extractQuestionnaireCandidates(sectionId)`
  - `LorevoxProjectionSync.markHumanEdit(...)` for every non-empty field
  - `graphMod.fullSync()`
  - `closeCallback()`

A refused or failed PUT therefore leaves candidates extracted from answers
the database never accepted, projection fields marked human-edited on the
strength of a write that did not happen, a family graph showing a relative
who is not stored, and a closed form.

The marks are the dangerous part. A candidate that later reads as established
biography is how an unsaved answer becomes apparent fact — and a narrator
built on it would speak with confidence about something nobody ever saved.

**Repair:** a confirmed server save is the boundary. Everything that writes
derived or authoritative state waits behind it; only rendering may run early.

## 1b. Found by the harness on its first run — both fixed, both regressed

**A server read overwrote the operator's DRAFT.** The dirty guard correctly
declined to replace the in-memory document, but the localStorage mirror
beneath it ran unconditionally. Memory held the typed value; the draft held
the server's older copy. Worst on the path that matters most: when a save
FAILS the operator is relying on the draft, and this was rewriting it
underneath them. A reload then produced the overnight loss of 2026-09-17 all
over again, with no error, because the save had already reported its failure
honestly and the loss happened afterwards.
(BUG-BIO-QUESTIONNAIRE-DRAFT-CLOBBERED-BY-GET-01)

**A stale form cross-wrote another narrator.** `_saveSection` harvests the DOM
by id; the cross-narrator guard compares the pid ARGUMENT with `bb.personId`,
and after a switch those agree. Nothing checked that the rendered form
belonged to the current narrator. The harness stored narrator A's mother under
narrator B's id. The live app re-renders on switch, which is why this has not
been seen — a timing accident, not a guarantee, and the cost of being wrong is
one family's history filed under another's name. The form now carries the
narrator it was rendered for and the save refuses, visibly, rather than
merging afterwards.
(BUG-BIO-QUESTIONNAIRE-STALE-FORM-CROSS-WRITE-01)

## 1c. CLOSED — a UI default became a biographical assertion

BUG-BIO-QUESTIONNAIRE-DEFAULT-AS-ASSERTION-01. Two selects had no empty
option, so they were answered the moment the form was drawn:

| field | default | what it asserted |
|---|---|---|
| `parents.deceased` | `"No"` | a blank entry became a stored parent, recorded as living |
| `grandparents.side` | `"Paternal"` | a real grandparent was filed on the father's side |

The second is the worse one, and it shows why filtering out blank entries
would not have been enough: a grandparent with a correctly typed name still
acquires a wrong relationship. That is not a blank waiting to be filled — it
is a wrong answer that reads like a given one, and it propagates into the
family tree.

Both now offer an empty first option. An operator who deliberately chooses
"No" or "Paternal" is still recorded; what changed is that silence is no
longer mistaken for an answer. The suite enumerates every select from the
shipping SECTIONS rather than checking these two by name, so a select added
later cannot reintroduce the class unnoticed.

**Already-stored values are NOT migrated.** `deceased: "No"` from a
deliberate choice and from the old default are the identical string; nothing
in the record distinguishes them. Clearing them would destroy real answers to
remove imaginary ones. `lorevox_packages/audit_default_assertions.py` reports
which stored values match either old default, with names and enough context
for someone who knows the family to judge. It writes nothing.

## 1e. CLOSED — derived state ran before the server confirmed anything

Candidate extraction, `markHumanEdit` and the family-graph sync ran
immediately after `_persistDrafts`, without awaiting it. A refused or failed
PUT left candidates extracted from answers the database never accepted,
projection fields marked human-edited on the strength of a write that did not
happen, and a graph showing a relative who is not stored.

The marks are the dangerous part, and they are the direct link to Lori: a
candidate that later reads as established biography is how an unsaved answer
becomes an apparent fact, and a narrator built on it would speak with
confidence about something nobody ever saved.

All three now run in `_afterConfirmedSave`, behind a confirmed outcome. A
no-op counts as confirmed — the stored document is exactly what they would be
derived from. `closeCallback` still runs immediately: it renders and does not
write, and the failure banner does not auto-dismiss, so a closed form does not
hide a failed save.

## 1f. Open finding — the phantom family member

RESOLVED by 1c, and worth recording how. The first instinct was a rule about
what makes an entry "real" — count the touched fields, ignore defaults. That
would have been a filter bolted on top of the symptom.

The actual defect was upstream: a select with no empty option is answered
before anyone looks at it. Once "unanswered" is expressible, a blank entry
has no populated leaves, contributes nothing to the flattened document, and
is not stored — without any rule about what counts as real, and without
discarding `deceased: "No"` when somebody means it.

A regression asserts that a blank added entry is not stored.

## 1d. Why `rendered > stored` is believed closed, and why the test stays

`_renderSectionDetail` renders from memory, so rendered always equals memory.
The only thing that shrank memory below the form was the adopt branch in
`_restoreQuestionnaireFromBackend`, and `_qqDirty` now blocks it. On that
reading the DIRTY fix closes the original data-loss path and the COUNT fix is
defence in depth.

Stated as a hypothesis, not a proof: it holds for the render / restore / add /
save paths as they stand today, and has not been checked against every caller
of `_persistDrafts` across the five modules that use it.

So the count invariant keeps its own test, deliberately white-box and
labelled as such — it constructs the mismatch rather than reaching it through
the UI. Verified to fail when the count fix alone is reverted, with the dirty
fix intact. If any future change re-opens a path that replaces memory
mid-edit, that assertion is what stops an entry being dropped silently a
second time.

## 2. Verify per section: two entries, not one

Every repeatable section needs a two-entry round trip through the real form
and the real database, not a source assertion:

  - parents, grandparents, siblings, children, spouse/partner
  - marriage, familyTraditions, pets

  EIGHT, not ten — enumerated from the shipping SECTIONS. The earlier count
  in this work order was a guess and was wrong. test_bio_builder_save_sequences.js
  reads the list at run time rather than restating it, so a section added
  later is covered without anyone remembering to add it here.

  DONE: all eight pass a two-entry round trip.

Each: enter one, save, add a second, save, reopen, save unchanged. Assert
values and revision, not exit codes.

## 3. Audit targets — to examine, not yet proven defective

| Area | The failure to look for |
|---|---|
| single-entry sections | a GET arrives mid-typing; displayed and saved values diverge |
| family tree | a relative appears in the graph though persistence failed |
| candidate extraction | an unsaved answer becomes an apparent established fact |
| projection sync | `markHumanEdit` runs for a write the server rejected |
| browser drafts | a stale draft reappears after erasure; a failed save reads as durable |
| narrator switching | an in-flight read, write or banner attributed to the wrong narrator |
| partial forms | saving a form changes fields it does not display |

The last one is BUG-BIO-QUESTIONNAIRE-LOSSY-ROUNDTRIP-01 and is fixed for the
questionnaire. It is listed because the same shape can exist in any other
surface that rebuilds an object from a rendered view.

## Method

1. **Baseline first.** Diff the working tree against the pushed commit and
   record both. A review of an older pushed copy reported two defects as
   present that had already been fixed locally; wasted effort either way.
2. **Inventory the mutation paths** — Add, Save, Close, Remove, narrator
   switch, restore, migration — and for each state what is read from the DOM,
   held in memory, sent to the server, and written before confirmation.
3. **Repair shared mechanisms once.**
4. **Test by sequence, not by pattern.** Two entries; successive saves; Add
   while a GET is pending; a failed PUT; reload; narrator switch; unchanged
   save.
5. **One live disposable-narrator walkthrough**, then check whether the
   family tree and other derived views agree with SQLite.

Janice, Kent and Christopher stay untouched until the preservation checks
pass.

## Sequencing against the other two work orders

This comes FIRST. WO-BIO-QUESTIONNAIRE-DEATH-DATE-01 and
WO-BIO-QUESTIONNAIRE-PER-ENTRY-SAVE-01 both add to the form. Better buttons
over an operation that can still lose an entry would conceal the defect
rather than remove it — clearer labels on a save that silently drops work is
worse than an unclear one, because it earns trust it has not got.
