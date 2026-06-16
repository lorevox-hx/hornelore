# WO-OPERATOR-NEW-NARRATOR-INTAKE-FORM-01

**Status:** SPEC — designed 2026-06-15
**Severity:** MEDIUM-HIGH (parent-session readiness blocker — surfaced
during the Walter live test when the "+ Add Test Narrator" button
created a row with only a name and no DOB, leaving Lori unable to
anchor any age-based question)
**Narrator generality:** UNIVERSAL
**Locked principle:** *The operator side seeds what they know before
Lori starts. The narrator's chapters carry the rest. Pre-data should
ground Lori's first turn, not pre-populate her conclusions.*

## Why this WO exists

Today the narrator switcher's "+ Add Test Narrator" button creates a
`people` row from a single text input — display name only. No DOB, no
pronouns, no place of birth, no consent attestation. The resulting
record is unusable for any age-grounded behavior:

- Life Map era buttons (Earliest Years / Early School Years /
  Adolescence / Coming of Age / Building Years / Later Years / Today)
  do age math against DOB. Without DOB every era click silently fails
  or surfaces the wrong era.
- Lori cannot anchor "when you were eight" / "the war years" / "your
  school years" because she has no idea what year any of those would
  have been.
- The projection map shows blank relationship slots so the timeline
  surfaces render as empty placeholders.
- The pronouns Lori uses on every reflection turn default to operator-
  guessed defaults, getting them wrong is a respect failure visible to
  the narrator and the family later.
- No consent is captured. Recording an older adult's life story
  without an explicit consent attestation is the legal / ethical
  floor; the current flow has no floor.

Live evidence: 2026-06-15 Walter session showed Lori producing clean
oral-history posture text (WO #5 working) but unable to anchor
chapter-1 in any historical era. The narrator's content carried the
turn; the system's grounding contributed nothing. That's the failure
mode this WO closes.

The May 11 2026 Kent transcript also surfaces the consequence of
under-seeded intake: Lori asked Kent "What does Adolescence mean?"
because she had no age math to map era labels onto concrete years.
A populated DOB removes that failure class entirely.

## Scope

Replace the bare-name "+ Add Test Narrator" flow with a structured
intake form that captures:

- **6 required identity fields** + **2 required consent checkboxes**
- **6 optional sections** the operator may fill or skip per row /
  per section — family of origin, marriage and partners, children,
  education and work, military service (collapsed behind Yes/No),
  faith and heritage, today / living situation

Preserve a "Skip — add narrator for testing only" path that maintains
the current zero-field behavior for stress-test scenarios (Walter,
Jake), but visually demote it so it's clearly the exception.

## Form structure

### Identity *(required)*

| Field | Type | Notes |
|---|---|---|
| Full legal name | text | Memoir front matter; appears on exports |
| Preferred name | text | Single name Lori uses out loud |
| Date of birth | date | Live UI helper text below the field |
| Place of birth | text | Anchors early-era questions |
| Pronouns | radio + other | she/her, he/him, they/them, other (free text) |
| Currently lives in | text | Anchors today-era + situational framing |

**DOB helper text** is computed UI feedback, not a form field. As the
operator types a valid date, an italicized line appears beneath the
field showing the parsed date, age today, and a brief historical
orientation phrase ("school-age during the early Cold War", "born
just before the Depression", "came of age in the late 1970s"). The
helper:

- Runs entirely client-side from the date input
- Is a parsing-confirmation signal (operator sees the system read the
  date the way they meant it)
- Primes the operator to think about which Life Map eras will activate
- Is never persisted; it's display-only feedback

### Family of origin *(optional)*

| Field | Type | Notes |
|---|---|---|
| Father's name | text | |
| Father's date of birth | date | Year-only accepted (validation parses "1908" as January 1, 1908 with year-only flag set) |
| Mother's name | text | |
| Mother's maiden name | text | |
| Mother's date of birth | date | Year-only accepted |

**Siblings table** — operator adds rows one per sibling. Including
the narrator in the birth order is encouraged so the table is
self-anchoring.

| Column | Type | Notes |
|---|---|---|
| Name | text | |
| Birth date | date | Year-only accepted |
| Birth order | small int picker | 1st / 2nd / 3rd / ... |

### Marriage and partners *(optional)*

| Field | Type | Notes |
|---|---|---|
| Marital status | radio | Married / Widowed / Divorced / Single / Partnered / Other |
| Number of marriages | small int | Defaults to 0 if Single; defaults to 1 otherwise; operator may override |

**Spouses / long-term partners table** — operator adds one row per
spouse / partner across the narrator's life.

| Column | Type | Notes |
|---|---|---|
| Name | text | |
| Year married | year picker | |
| Status | radio | Current / Deceased / Divorced |

### Children *(optional)*

Operator adds one row per child.

| Column | Type | Notes |
|---|---|---|
| Name | text | |
| Birth date | date | Year-only accepted |

### Education and work *(optional)*

| Field | Type | Notes |
|---|---|---|
| Highest education level reached | radio | 10 options: Some primary / Primary completed / Some high school / High school / GED / Some college / Associate / trade / Bachelor's / Master's / Doctorate / professional / Other |
| Primary occupation / career | text | Single line — "Restaurant owner", "Schoolteacher", "Carpenter" |
| Years working | text | Date range — "1962–1997" |

Per adjacent-field research, institution names + graduation years are
intentionally NOT collected here. They surface in the chapter ("I
went to Central High in Pueblo and Mrs. Pederson kept lemon drops on
her desk") and pre-typing them strips that storytelling material.

### Military service *(optional, collapsed by default)*

**Gate:** *Did the narrator serve in the military?* — radio Yes / No.
Default selection: No. Selecting Yes expands the structured block
below; selecting No keeps it collapsed and unseen.

Structured fields when expanded:

| Field | Type | Notes |
|---|---|---|
| Branch | radio | Army / Navy / Air Force / Marines / Coast Guard / Space Force / National Guard / Reserve / Other |
| Service dates | text | Date range — "1959–1965" |
| Highest rank reached | text | "Sergeant E-5" |
| Unit(s) | text | "4th Missile Battalion, Nike Hercules" |
| Locations served | text | Free-form list separated by ` · ` |
| Wars / conflicts | text | "Cold War (no combat deployment)" |
| Decorations / awards | text | Free-form list |
| Service-connected experience notes | textarea | Optional 200-word free-text capture |

Indexable structured fields match the Library of Congress Veterans
History Project pattern so the eventual archive surface (deferred WO)
can search by branch / dates / unit / location / conflict.

### Faith and heritage *(optional)*

| Field | Type | Notes |
|---|---|---|
| Religion / faith tradition raised in | text | Single line — "Catholic", "Lutheran", "Reform Jewish", "None" |
| Current faith / practice | text | May differ from raised-in |
| Cultural / ethnic heritage | text | Free-form — narrator's own framing preserved |
| Languages spoken at home growing up | text | Comma-separated list |

### Today *(optional)*

| Field | Type | Notes |
|---|---|---|
| Living situation | radio | Independent in own home / With family / Assisted living / Memory care / Other |
| Health considerations Lori should know | textarea | Operator-side context, NOT shown to narrator. Feeds into Lori's runtime71 as sensitivity notes (hearing, fatigue, mobility, recent diagnoses). |

### Consent *(required)*

Both checkboxes must be ticked before the form will save. The
checkboxes are physically ticked while the narrator is present at
the screen; the lines read in the narrator's first-person voice
("I agree", "I have reviewed").

| | |
|---|---|
| ▣ | I agree to be recorded and to have my stories preserved as a memoir. |
| ▣ | I have reviewed (or had read to me) the disclosure of how Lori behaves around safety topics. |

If the narrator cannot operate the mouse / touchscreen and the
operator physically clicks on their behalf, the form should support
a "checked on narrator's behalf by [operator name]" attestation
appearing beneath each checkbox, so the audit trail is honest about
who moved the cursor.

### Save buttons

Two side-by-side primary buttons at the bottom:

- **Save and start session** — saves the record + jumps directly to
  Interview Mode for the new narrator
- **Save and continue to Bio Builder** — saves the record + opens the
  Bio Builder lane for deep family-tree / heritage / career entry

Plus a tertiary visually-demoted link:

- **Skip — add narrator for testing only** — current zero-field
  behavior preserved for stress-test scenarios. Bypasses required
  fields entirely. Visible but clearly the exception.

## Backend schema additions

The bio_schema seed already contains roughly half these field_keys
from WO-LORI-BIO-BUILDER-UNIVERSAL-01 Phase A. Audit the existing
seed before writing migrations. Likely additions:

- `personal.legalFullName` (if not already covered by existing
  `personal.fullName`)
- `personal.currentResidence` (geography category)
- `marriage.count`
- `military.served` (boolean gate)
- `military.warsConflicts`
- `military.decorations`
- `military.experienceNotes`
- `today.livingSituation`
- `today.healthConsiderations`
- `consent.recordingAgreement` (boolean, timestamped)
- `consent.disclosureReviewed` (boolean, timestamped)
- `consent.checkedOnBehalfBy` (optional operator id)

Pronouns may need a structured enum + other free-text column rather
than dropping into a single text field, because Lori reads pronouns
on every reflection turn and needs unambiguous routing (she/him/them/
they) — the "other" path should write to a free-text column the
prompt composer reads separately.

## Acceptance gates

1. **Required block enforced.** Save buttons disabled until all 6
   identity fields + both consent checkboxes are filled. Visible
   field-level validation messages on attempted save with missing
   data.

2. **DOB helper renders live.** As the operator types a valid
   date, the helper line appears beneath the field with parsed
   date, age, and historical orientation phrase. Updates within
   200ms of keystroke. Helper disappears or shows a parse error
   message for invalid dates.

3. **Year-only DOB accepted for parents / siblings / children.**
   Operator types "1942" in those fields; system stores it as
   year-only flagged so downstream consumers know to skip month /
   day in display ("born 1942" not "born January 1, 1942").

4. **Military section collapsed by default.** Loading the form
   shows the Yes/No gate with No pre-selected; the structured
   military block is not in the DOM until Yes is selected. Field
   tab order skips the collapsed block.

5. **Skip path bypasses required fields.** Clicking the demoted
   "Skip — add narrator for testing only" link creates a row with
   just the display name (current behavior) and immediately closes
   the form. Consent is not required on this path; the row carries
   a `testing_only=true` flag so downstream operator dashboards can
   filter / warn.

6. **Save and start session lands in Interview Mode.** Successful
   save + button click writes the record and navigates the operator
   directly to the narrator's first Interview Mode screen. Lori's
   greeting already reflects the captured name + pronouns.

7. **Save and continue to Bio Builder lands in Bio Builder.**
   Successful save + button click writes the record and opens the
   Bio Builder lane with the new narrator selected. Family-of-origin
   data already captured here pre-populates the corresponding Bio
   Builder rows so the operator doesn't re-enter it.

8. **Lori's runtime71 carries all required identity fields on the
   first turn.** Spot-check: a narrator created via the new form,
   then loaded into Interview Mode, results in Lori's prompt
   composer receiving full identity + pronoun + age context. The
   verifiable log line `[composer] runtime71 identity_complete=true`
   fires on every chat turn for the new narrator.

9. **Lori's first response respects pronouns.** A she/her narrator
   gets she/her pronouns in Lori's reflection on turn 1, not he/him
   or they/them or no pronoun.

10. **Lori's first response anchors at least one age era.** A
    narrator with DOB 1942 receives a turn-1 response from Lori
    that references either an age range, an era label, or a
    historical period appropriate to their childhood. The exact
    phrasing varies but the era anchor is present.

11. **Consent attestation persisted with timestamps.** The two
    consent checkboxes write timestamped rows to a new
    `consent_attestations` table; the narrator's record carries a
    foreign key to those rows. Operator dashboards surface
    consent-pending warnings for any narrator missing either
    attestation.

12. **Existing narrators (Janice / Kent / Christopher / Walter)
    not broken.** Existing rows render in the switcher and load
    into Interview Mode unchanged. The new form only governs
    narrator-creation; existing narrators pass through their
    template-preload path as before.

## Test coverage

- `tests/test_intake_form_validation.py` (~12 tests) — required
  field enforcement, DOB parsing edge cases (year-only, invalid,
  future date, before 1900), pronoun other-text routing, military
  Yes/No expansion behavior, consent checkbox required state
- `tests/test_intake_form_schema_writes.py` (~10 tests) — each
  section's fields land in the correct DB column / bio_facts row,
  testing_only flag set correctly on skip path, consent
  attestations timestamped and linked
- `tests/test_intake_form_routes.py` (~6 tests) — POST /api/people
  with full intake payload, with required-only payload, with skip
  payload, malformed payload returns 422, consent missing returns
  422
- `tests/ui/test_intake_form_e2e.py` (Playwright, ~4 cases) —
  full form fill creates narrator with all fields present,
  required-only fill works, skip path works, DOB helper renders

Target: ~32 new tests across 4 files, all green before merge.

## Files changed

- `ui/hornelore1.0.html` (~200 lines added) — new intake form
  modal mounted from the "+ Add Narrator" button in the switcher
- `ui/js/narrator-intake.js` (new, ~350 lines) — form state
  management, validation, DOB helper computation, save handlers
- `ui/css/narrator-intake.css` (new, ~120 lines) — form layout
  and styling
- `server/code/api/routers/people.py` (+50 lines) — extended
  POST /api/people to accept full intake payload
- `server/code/api/db.py` (+150 lines) — new accessor helpers
  for consent attestations + the bio_facts inserts that route
  intake fields into the right bio_fields rows
- `server/code/db/migrations/0012_consent_attestations.sql` (new)
  — `consent_attestations` table + indexes
- `server/code/api/services/bio_schema.py` (+10 fields) — new
  bio_fields entries for military.served, today.livingSituation,
  today.healthConsiderations, consent surfaces, etc.
- `server/code/api/prompt_composer.py` (+30 lines) — runtime71
  emits the new identity fields so Lori's first turn grounds on
  them

## Related lanes

- **WO-LORI-BIO-BUILDER-UNIVERSAL-01** Phase A schema (already
  shipped) — half the field_keys this form writes are already
  seeded
- **WO-LORI-BIO-BUILDER-UNIVERSAL-01** Phase E (already shipped) —
  the bio editor exists and "Save and continue to Bio Builder"
  routes there
- **WO-LORI-STORY-FIRST-PHASE-1-01** — Phase 1 momentum +
  thread bank benefit from rich identity context but do not
  depend on it; the form makes Phase 1 perform better but Phase
  1 ships without it
- **WO-LORI-ORAL-HISTORY-DEFAULT-01** — the oral-history posture
  block in prompt_composer reads runtime71.identity_complete; this
  form is what populates that field
- **Future: VHP-style military archive surface** — the structured
  military fields enable a searchable veterans-content surface but
  that's a deferred WO, not this one
- **Future: per-narrator template library** — the form output is
  essentially a per-narrator template; future work may load
  community-contributed templates as defaults

## Out of scope (deferred)

- **Multi-language form support.** Form is English-only in v1;
  Spanish + other languages deferred to a separate localization WO
- **Audio-recorded consent.** v1 is checkbox-only; future work may
  record an audio consent statement
- **Operator authentication.** "Checked on narrator's behalf by"
  field assumes an operator account model that doesn't fully exist
  yet; v1 stores the field as a free-text string until the
  operator account model lands
- **Form auto-save / draft persistence.** Form state lives in
  browser memory only; navigating away loses progress. Future work
  may add session-bound drafts
- **Pre-fill from address book / contact import.** Manual entry only
- **Photograph upload.** Avatar / portrait upload deferred to the
  existing media archive lane
- **Family-tree visualization in the intake form itself.** v1 captures
  family of origin + spouse + children as flat lists; tree
  visualization lives in Bio Builder, not here
