# WO-BIOGRAPHY-CONFIRMATION-MODEL-01 — who said it, and who agreed

Rule stated by the project owner, 2026-09-18. This work order records it and
the two findings that block the questionnaire→projection writer until it
exists.

## The rule

  - An operator or narrator entering information **directly** into Bio
    Builder is CONFIRMED biography. Lori may use it as an established fact.

  - Lori proposing or auto-filling a value is an UNCONFIRMED SUGGESTION until
    an operator or narrator explicitly accepts it.

  - On acceptance it becomes confirmed — and the record still shows that Lori
    proposed it and **who** confirmed it.

  - "Confirmed" means accepted into the biography, not historically
    infallible. A later correction must preserve the original claim and its
    history.

  - Presence in the questionnaire is NOT confirmation. The system must know
    who entered or approved the value.

  - **Lori must not be able to mark her own suggestions as human-confirmed by
    writing them into the questionnaire.**

  - Enforced at the SERVER write boundary, not only in the browser.

  - Applies to every questionnaire field, not only identity fields.

## Finding 1 — the questionnaire cannot answer "who entered this?"

`bio_builder_questionnaires.questionnaire_json` is a plain document:

    {"parents": [{"occupation": "ore dock foreman"}]}

There is no per-field author, source, timestamp-by-actor or confirmed-by
anywhere in it. The table's columns are `person_id`, `questionnaire_json`,
`source`, `version`, `updated_at`, `revision` — and `source` is a whole-row
marker naming the last writer, not per-field provenance.

`bio_builder_questionnaire_revisions` (0058) records `changed_paths`,
`removed_paths` and `previous_values`, so WHAT changed and WHEN is
recoverable. WHO is not stored at all.

## Finding 2 — the questionnaire ALREADY holds values that came from Lori

Two paths write into `bb.questionnaire` without an operator typing:

**`_syncIdentityToBB(profile)`** — `ui/js/bio-builder-core.js:1118`, called
from `:1725`. Mirrors identity captures into `bb.questionnaire.personal`.
Those captures originate in the conversation (`app.js` identity onboarding
handlers), i.e. from Lori.

**`acceptSuggestion`** — `ui/js/projection-sync.js:606`:

    // Write directly to BB questionnaire (user accepted = authoritative)
    bb.questionnaire[parsed.section][parsed.field] = suggestion.value;

This one IS a legitimate acceptance — a person clicked accept. But the value
lands in the questionnaire as an ordinary answer, indistinguishable from one
typed by hand. Neither "Lori proposed this" nor "a person accepted it on this
date" survives.

## Why this blocks the questionnaire → projection writer

The plan was to write questionnaire answers into `interview_projections` with
`source: "human_edit"`, which the read contract classifies as tier 1,
operator_entered.

Under the rule that is laundering. A value Lori put into the questionnaire
via `_syncIdentityToBB` would arrive in the biography stamped as
human-confirmed, on no evidence beyond having passed through a document that
cannot tell the difference. That is the precise move the rule forbids, and
building it would undo the repair in BUG-LORI-SUGGESTION-READS-AS-FACT-01 by
a different route: the suggestion queue was sealed at the read boundary, and
this would open a write-side path around it.

**Do not build the writer until the questionnaire can distinguish a typed
answer from an auto-filled one.**

## Finding 3 — nothing is enforced server-side

Every gate that protects provenance today lives in `ui/js/projection-sync.js`:
the trusted-source allowlist (`:323-325`), the lock check (`:212-215`), the
confidence gate (`:256-266`), and the diversion of untrusted writes to
`pendingSuggestions` (`:238-247`).

The server stores field objects opaquely (`db.py:7074`) and validates nothing
— `mutations` is typed `Dict[str, Any]` (`routers/projection.py:74`). Any
client may claim `source: "human_edit"` on any path, and the server will
record it. `_projection_provenance` then honours that claim.

So the current provenance system describes what a client ASSERTED, not what
happened. That is acceptable while every writer is our own UI and the stakes
are a prompt bucket. It is not acceptable as the basis for "Lori may use this
as an established fact".

## What has to exist, in order

**1. Per-field provenance in the questionnaire.** Minimally, for each path:
who entered it (`operator` / `narrator` / `lori`), when, and — when it began
as a suggestion — that it did, plus who accepted it. A sidecar map keyed by
the same dotted paths the merge already uses is the obvious shape, because
`merge_whole_document` already flattens to those paths and
`bio_builder_questionnaire_revisions` already records them.

**2. Server-assigned provenance, not client-asserted.** The server knows
which route received a write and which session made it; it cannot know
whether a human's fingers were involved, but it can know that a write arrived
on the Bio Builder save path rather than the chat correction path. Provenance
should be stamped from the route, and a client-supplied `source` should be
treated as a hint at best.

   This changes `_projection_provenance` from "report what the field claims"
   to "report what the server recorded". Until then it should be documented —
   in code — as reporting an assertion.

**3. An acceptance record.** `acceptSuggestion` must write the acceptance,
not only the value: proposed-by, accepted-by, accepted-at. The suggestion
already carries `supersedes` after
BUG-PROJECTION-CORRECTION-OVERRIDES-OPERATOR-01; the acceptance side is
missing.

**4. `_syncIdentityToBB` must stamp its writes as Lori-derived**, or stop
writing into the questionnaire and route through the suggestion queue like
every other untrusted write. The second is more consistent with the rule; the
first is smaller. Deciding between them is part of this work order.

## Migration question, not to be answered by a script

Existing questionnaires contain values with no provenance. Some were typed;
some arrived via `_syncIdentityToBB`; nothing distinguishes them now.

Do NOT default them to confirmed — that asserts human approval that may not
have happened, for exactly the records that matter most. Do not default them
to unconfirmed either, which would demote an afternoon of hand-typed family
history to the status of a guess.

They need a third state: **provenance unknown, recorded before this
distinction existed**. Janice's 100 values, Kent's 86 and Christopher's 130
are all in it.

## Scope note

This work order was written after the read-boundary repairs
(BUG-LORI-SUGGESTION-READS-AS-FACT-01,
BUG-PROJECTION-CORRECTION-OVERRIDES-OPERATOR-01) and supersedes step D of
WO-BIOGRAPHY-READ-CONTRACT-01, which assumed the questionnaire could
legitimately claim tier 1.
