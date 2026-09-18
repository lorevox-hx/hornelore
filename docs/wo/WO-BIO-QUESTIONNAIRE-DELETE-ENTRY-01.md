# WO-BIO-QUESTIONNAIRE-DELETE-ENTRY-01 — a family member cannot be removed

Raised 2026-09-18 by code review, demonstrated in the behavioural harness the
same day.

## The finding

There is no way to delete a repeatable entry.

**No control exists.** `bio-builder-questionnaire.js` has `_addRepeatEntry`
and no counterpart. The rendered section offers "+ Add another <entry>" and a
Save button. Nothing removes.

**And clearing the fields does nothing.** Demonstrated:

    after entering two parents      ["Ingrid", "Bertil"]
    after clearing EVERY field of entry 2
                                    [{...Ingrid...},
                                     {"relation":"Father","firstName":"Bertil"}]

The operator erased Bertil and he is untouched on the server.

## Why blanking does nothing, and why that is not a bug to "fix"

`merge_whole_document` applies an incoming document's populated leaves as
mutations with NO removals. A key the client omits is left standing.

That is deliberate, and it is the repair that stopped
BUG-BIO-QUESTIONNAIRE-LOSSY-ROUNDTRIP-01. On 2026-09-15 a form that rendered
six of eleven stored fields wrote back what it could see, and the five it
could not see were deleted — ten hand-typed values across two of Janice's
parents, several hundred words of family history with no other copy at full
length.

So omission MUST NOT mean deletion. The cost is that the only gesture an
operator has — clearing the boxes — is now a no-op, and they are not told.

The server already has the mechanism: the PUT accepts `removals`, and there
are explicit `replace_questionnaire` / `reset_questionnaire` paths. The UI has
never sent any of them.

## What this is worth

A biography accumulates mistakes: a parent entered twice, a name typed into
the wrong entry, a relative who turns out to be an in-law. Before today's
`deceased` repair it could also accumulate phantom entries created by nothing
more than clicking Add. Every one of those is permanent.

Records may already contain them. Christopher and Kent both have stored
grandparents; whether any entry is unwanted is a question for somebody who
knows the family, and right now the answer cannot be acted on either way.

## The design

**An explicit Remove control per entry**, which sends an explicit removal
rather than relying on omission. It must:

  - name who is being removed, in the confirmation — "Remove Bertil
    Lindqvist from Parents?" and not "Remove entry 2?". The operator is
    deleting a person from a family record, and the prompt should read like
    it
  - require confirmation, and not offer an undo it cannot honour
  - wait for the server to confirm, and report failure like any other save
    (BUG-BIO-QUESTIONNAIRE-SILENT-SAVE-FAILURE-01 applies: a deletion that
    silently fails is worse than one that visibly fails)
  - write a revision-history row. Deletion is the change most worth being
    able to trace back, and `bio_builder_questionnaire_revisions` already
    carries `removed_paths` and `previous_values`

**Blanking every field must not be a silent no-op.** Either tell the
operator that clearing fields does not remove an entry and point them at
Remove, or treat a fully-cleared entry as an explicit removal request and
confirm it. The first is safer and should be the default; the second is a
convenience that can be added later if the first proves annoying.

**Positional identity is the hazard.** Entries are addressed as
`parents[0]`, `parents[1]`. Removing index 0 renumbers index 1, so a removal
and a concurrent edit can apply to different people. This is the same
limitation already documented as deferred in
BUG-BIO-QUESTIONNAIRE-LOSSY-ROUNDTRIP-01_Spec.md — stable per-entry ids.
Deletion is the operation where it stops being theoretical, because the
consequence is not a lost field but the wrong person removed.

**Do not implement removal by sending the whole array minus one entry.**
That is omission-as-deletion wearing a different hat, and it re-opens the
2026-09-15 defect for every other field in the document.

## Tests

  - an entry removed through the control is gone from the stored document
  - the entry BEFORE it and the entry AFTER it are unchanged, field for field
  - a removal that the server refuses leaves the entry present and says so
  - a revision-history row records the removal with its previous values
  - clearing every field does not silently remove, and does not silently do
    nothing either
  - no OTHER section is touched by a removal

## Sequencing

Do with WO-BIO-QUESTIONNAIRE-PER-ENTRY-SAVE-01: both change the repeatable
entry controls and want one round of testing. Both depend on the confirmed-
save contract that already exists.

Not urgent for entering Janice's biography — nothing needs deleting yet — but
it becomes urgent the first time something is entered wrongly, which on a
sixteen-section family record is a matter of when.
