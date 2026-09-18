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

## 2. Verify per section: two entries, not one

Every repeatable section needs a two-entry round trip through the real form
and the real database, not a source assertion:

  - parents, grandparents, siblings, children, spouse/partner
  - marriages / unions, traditions, pets
  - and the remaining repeatable sections — enumerate them from the
    declarations rather than guessing; the review that raised this counted
    ten and could name eight

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
