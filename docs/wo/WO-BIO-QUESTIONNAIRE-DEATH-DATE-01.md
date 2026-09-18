# WO-BIO-QUESTIONNAIRE-DEATH-DATE-01 — capture a death date, not a yes/no

Raised 2026-09-18 by the operator during the Bio Builder walkthrough, while
entering a parent's record on the disposable narrator ZZ WALKTHROUGH 20260917.

> "it just has a drop down for deceased yes or no and yes does not give a
> place to put a date it should and more than just a year that should be for
> all family members"

## The finding

`deceased` is a two-option select and nothing records WHEN.

    ui/js/bio-builder-questionnaire.js:386   parents      { id: "deceased", type: "select", options: ["No","Yes"] }
    ui/js/bio-builder-questionnaire.js:453   grandparents { id: "deceased", type: "select", options: ["","No","Yes"] }

This is not simply an absent field. Three layers already disagree about
whether a death date exists.

**The family tree reads one that is never written.**

    ui/js/bio-builder-family-tree.js:572   deathYear: (p.dateOfDeath || "").substring(0, 4)   parents
    ui/js/bio-builder-family-tree.js:595   deathYear: (s.dateOfDeath || "").substring(0, 4)   siblings
    ui/js/bio-builder-family-tree.js:616   deathYear: (g.dateOfDeath || "").substring(0, 4)   grandparents
    ui/js/bio-builder-family-tree.js:764   deathYear: (e.dod || e.dateOfDeath || "").substring(0, 4)

Every one of those resolves to `""` today, and each truncates to four
characters — so even once a date IS captured, the tree keeps only the year.

**The server already has a slot for it.**

    server/code/api/routers/chronology_accordion.py:591   "dateOfDeath": {"event_kind": "death", "label": "Died", "date": True, ...}
    server/code/api/routers/chronology_accordion.py:732   # Profile-level dateOfDeath (forward-compat slot — not populated today).

So the chronology can already place a death event on a timeline. It has
never received one, because no form asks.

## Why this matters beyond tidiness

A yes/no answers whether someone is alive. A biography needs when they died:
it orders a life against its siblings' lives, it decides which stories the
narrator could have been told directly and which arrived second-hand, and for
a narrator in their nineties it is often the single most load-bearing date in
a family's account of itself.

"Yes" also decays. It is true on the day it is entered and silently wrong
afterwards; a date never becomes wrong.

## Scope

Add a death date to every family-member section that has `deceased`, and to
those that should have both:

  - parents, grandparents, siblings, spouse/partner, children

Requirements:

1. **A full date, not a year.** Same treatment as `birthDate`: exact dates
   normalized to YYYY-MM-DD, approximate dates preserved verbatim
   ("around 1968", "spring 1979"). Reuse `normalizeDateSafe` — grandparents
   already use it for birth, precisely because those dates are often fuzzy.

   **Partial and unknown must be first-class, not a degraded case.** The
   field must accept a year alone, a month and year, a season, "unknown",
   or nothing at all, and store what was said. A form that demands a day and
   a month to accept a death forces the operator to invent two facts in order
   to record one they actually have — and an invented day is indistinguishable
   from a remembered one a year later. Precision this record cannot support
   must never be required as the price of entry.
2. **Consistent field name.** `dateOfDeath`, because that is what the family
   tree and the chronology already read. Do not invent a third spelling.
3. **Stop truncating.** The four `substring(0, 4)` calls should keep the full
   date and let the renderer decide what to show.
4. **`deceased` and `dateOfDeath` must not contradict each other.** A date
   present with `deceased: "No"` is a data error the form should not be able
   to produce. Deciding which one wins is part of this work order, not an
   implementation detail to settle in passing.
5. Grandparents' `deceased` includes `""` in its options and parents' does
   not. Unexplained, probably accidental; resolve it while here.

## Explicitly NOT part of this

Do not backfill. Janice, Kent and Christopher have hand-entered records; a
migration that guesses a death date from a "Yes" would be inventing family
history. The field arrives empty and is filled by a person.

## Sequencing

Raised during the walkthrough and deliberately not fixed mid-walkthrough —
per the walkthrough's own instruction to record what cannot be entered rather
than work around it. The questionnaire write path was under repair that same
day (BUG-BIO-QUESTIONNAIRE-NEW-NARRATOR-SAVE-LOCK-01 and others); adding
fields while the save path was being proved would have confounded both.

Safe to schedule once the walkthrough is accepted. Adding a field is exactly
the change the repaired merge is supposed to tolerate: an older client that
does not send `dateOfDeath` must leave a stored one standing, which
`merge_whole_document` gives us. Worth asserting in this work order's tests
rather than assuming.
