# WO-BIO-QUESTIONNAIRE-PER-ENTRY-SAVE-01 — save each family member, not the section

Raised 2026-09-18 by the operator during the Bio Builder walkthrough, after
BUG-BIO-QUESTIONNAIRE-SECOND-ENTRY-DROPPED-01 silently discarded a second
parent.

> "so after entering parent it should be save and exit or save and add
> another or similar?"

## The problem

Repeatable sections render every entry at once, offer a single
`+ Add another <entry>` ghost button, and one `Save <Section>` in the footer.
Nothing is durable until the operator has typed EVERY entry and pressed that
one button.

Two failures follow from this, and both have now happened on real data.

**Nothing is saved while the operator is still working.** On 2026-09-17 a
refused save left six typed values in localStorage; the machine was shut down
overnight and they were gone by morning. A flow that asks for two complete
parent biographies before anything reaches the server is that same exposure,
held open for as long as the typing takes.

**The moment of durability is invisible.** The operator cannot tell which
entries are saved and which are only on screen. There is one button and it
means "all of it, maybe".

## The design

Two controls at the foot of EACH entry, not one at the foot of the section:

    Save & add another parent        Save & close

`Save & add another` — persist THIS entry, wait for the server to confirm,
and only then open a blank entry. The new entry must not appear before the
confirmation; an empty form arriving is the operator's signal that the last
one is safe.

`Save & close` — persist this entry, wait for confirmation, return to the
Parents overview showing every stored entry.

On failure, in either case:

  - the form stays open, with everything the operator typed still in it
  - the error is shown, in the words the outcome gives
    (refused / conflict / http_error / network — see `_persistQuestionnaire`)
  - no navigation happens, and no new entry is opened

Applies to every repeatable family-member section: parents, grandparents,
siblings, children, spouse/partner.

`Save & close` must not close until the server has answered. Closing on the
attempt puts the operator back at an overview that looks finished while the
request is still in flight — and if it fails, the form they would need is
already gone.

## The banner is not enough — the status must persist

Added 2026-09-18 after the operator saved, left Bio Builder, and could not
read the result:

> "i did not get a chance to see the banner it was too quickly gone"

The toast was extended from 4s to 8s, which helps and does not fix it. A
transient message is the wrong shape for "did my work reach the database" —
the operator is entering a parent's biography from memory and from paper, and
looks up at the screen when they look up, not when a timer says to.

Each repeatable section's overview row must carry the last save's state,
durably:

    Changes saved · Revision 4        server confirmed a write
    Already up to date · No changes   server returned write_applied: false
    NOT SAVED · <reason>              the request failed; values retained

It stays until another save replaces it or the operator dismisses it, and it
survives closing the entry and leaving Bio Builder. The distinction between
the first two matters: without it the operator cannot tell an edit that
landed from a form that resubmitted what was already there.

`_persistQuestionnaire` already returns exactly these three outcomes with the
revision, so this is a display of state we hold, not new plumbing.

## Hard requirement: adding must not refresh over unfinished work

`_addRepeatEntry` currently calls `_restoreQuestionnaire`, which starts a GET.
That GET can land while the operator is mid-entry, and before
BUG-BIO-QUESTIONNAIRE-GET-CLOBBERS-EDITS-01 was fixed it would replace the
in-memory document with the server's copy — discarding a half-typed entry
still visible on screen. That is now blocked by `_qqDirty`, and this work
order must not reopen it.

The new flow makes the window smaller rather than merely guarded: the entry
is on the server BEFORE the next one exists, so there is nothing unsaved for
a refresh to lose.

## Dependencies and sequencing

Requires the save-outcome contract from
BUG-BIO-QUESTIONNAIRE-SILENT-SAVE-FAILURE-01 — `_persistQuestionnaire`
returning saved / refused / conflict / http_error / network. "Confirm success,
and only then open a blank entry" is unimplementable without it, and the old
fire-and-forget PUT would have made these buttons LIE more confidently than
the single one did: two chances per entry to report a save that never
happened.

Do together with WO-BIO-QUESTIONNAIRE-DEATH-DATE-01. Both change the same
repeatable sections and want the same round of testing.

Both were deliberately held until the current repair was proven against the
live database, so that a failing test would implicate one change rather than
three at once.

## Tests

  - a failed save leaves the form open with every typed value intact
  - `Save & add another` does not render the blank entry until the outcome is
    `saved`
  - a refused save opens no new entry
  - entry N+1 is captured when entry N is already stored
    (the 2026-09-18 regression — must stay covered)
  - a GET landing mid-entry does not discard an unfinished one
