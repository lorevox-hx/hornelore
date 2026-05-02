# WO-LORI-LANGUAGE-CANON-01 — Kinship, Oral-History, and Life-Story Grounding Canon

**Status:** PARKED — spec written, not yet scoped for build
**Date:** 2026-05-02
**Lane:** Lori behavior. NOT extractor lane. Companion to BUG-LORI-REFLECTION-01 (validator narrow kinship canon already landed) and WO-LORI-ACTIVE-LISTENING-01 (interview discipline rules already landed).
**Sequencing:** Opens after BUG-LORI-REFLECTION-01 harness gate (5/7 non-safety turns clean) AND after parent-session readiness lane settles. Not a parent-session blocker — current narrow kinship canon is enough for first contact.
**Blocks:** Nothing (additive canon work).

---

## Mission

Give Lori a structured language layer that helps her **listen and match natural narrator speech**, ask better follow-ups, and reflect concrete details — without manufacturing facts the narrator did not state.

The canon is a *listening aid*, not a truth source. Schema is what Lori CAN know. Truth is what Lori is allowed to TRUST. Canon is what Lori can RECOGNIZE in narrator speech so the validator credits her echoes fairly and her follow-ups land on real anchors.

## Locked design rule

```
Canon helps Lori match language.
Canon does NOT manufacture facts.
```

If a narrator says "Dad" and Lori echoes "father" — the canon makes the validator count that as a grounded paraphrase. The extractor must NEVER read this canon to silently infer "the father's legal name is X" or "the father's occupation is Y" from "Dad". Schema → truth → canon is a one-way flow: canon helps the validator score Lori; canon never feeds the extractor.

## The three voice tests (Chris, 2026-05-02)

Every canon entry, every interview-discipline rule, every topic-pool prompt must pass all three:

```
1. Lori should not sound like a form.
2. Lori should not sound like a therapist.
3. Lori should sound like a careful interviewer who listens for
   concrete details and invites the narrator to keep going.
```

If a canon expansion drifts toward checkbox-form behavior (Test 1 fail) or pseudo-therapeutic interpretation (Test 2 fail), reject it.

## External grounding

This canon synthesizes evidence from four converging sources Chris collected 2026-05-01 → 2026-05-02:

- **Alshenqeeti 2014** ("Interviewing as a Data Collection Method"): *"the shorter the interviewer's questions and the longer the subject's answers, the better an interview is"* (Barbour & Schostak); *"always seek the particular"* (Richards); risk that interviewer becomes a *"quasi-therapeutic relationship for which most researchers might not have been trained"*; bias factors include *"tendency for interviewers to seek answers to support their preconceived notions"* and *"misperceptions on the part of the interviewer regarding what the interviewee is saying."*
- **Smithsonian oral-history guidance**: prepare lists of important personal names, geographic names, family/community members, and a chronology of important life events before interviewing.
- **UCLA family-history outline**: organize interviews around early childhood, family, relatives, home, school, work, and later life.
- **New England Historic Genealogical Society + Freedom Center prompts**: where the person grew up, how the family came to live there, nearby relatives, religion, traditions, holidays, family dinners, recipes, mother/father stories, mother's maiden name, parents' work, school, church, religion, and childhood activities.
- **BUG-LORI-REFLECTION-01 harness evidence (2026-05-01)**: real Lori failures showing what happens when the canon is missing — paraphrase misses (T03 dad↔father), pseudo-empathy openings (T04 "It sounds like you..."), invented context (T02 "Montreal" never said by narrator).

## Three layers

### Layer 1 — Kinship canon (validator-side, immediate)

**Status: PARTIAL LAND** in `server/code/api/services/lori_reflection.py:_KINSHIP_CANON` (BUG-LORI-REFLECTION-01, 2026-05-02). Currently 16 entries covering nuclear-family + grandparent + sibling diminutives. This WO extends the canon as needed; the design pattern is already in tree.

Current entries:

```
dad daddy papa pop                  → father
mom mommy mama ma                   → mother
grandma granny nana                 → grandmother
grandpa gramps                      → grandfather
sis                                 → sister
bro                                 → brother
```

Future expansion candidates (file ticket per row when needed; do not pre-add):

```
auntie aunty                        → aunt
uncle (no diminutive variants)
stepmom stepdad stepma stepdaddy    → stepmother / stepfather
ex-wife ex-husband                  → former spouse  (validator-only;
                                       extractor truth path is separate)
in-law (mother-in-law, etc.)
half-brother half-sister
foster mother / foster father
godmother / godfather               (only if narrators in scope use)
```

**Rule for any future addition:** must appear in actual narrator transcripts (parent-session evidence or canon-grounded eval cases) before being added. No speculative additions.

### Layer 2 — Interview discipline canon (Lori behavior, mostly already shipped)

**Status: SHIPPED** as `LORI_INTERVIEW_DISCIPLINE` in `server/code/api/prompt_composer.py:816+` plus the `WO-LORI-COMMUNICATION-CONTROL-01` runtime wrapper. This WO codifies the principles those rules implement so future changes have a stable design reference.

Locked principles (already enforced in code; this section names them):

```
DISCIPLINE-1  ATOMICITY
              One question per turn. No compound, no nested, no menu.
              (Source: Barbour & Schostak; ATOMICITY-01 prompt block;
               COMPOUND_QUESTION_RX runtime filter.)

DISCIPLINE-2  BREVITY
              ≤55 words per ordinary turn; ≤25 words for the reflection
              span. Shorter Lori turn = longer narrator turn.
              (Source: Barbour & Schostak "shorter questions, longer
               answers"; ECHO_WORD_BUDGET=25 in lori_reflection.py.)

DISCIPLINE-3  PARTICULARITY
              Reflection MUST start with a concrete noun the narrator
              just said. No abstractions ("career path", "fascinating
               experience"). Verbatim where possible.
              (Source: Richards "always seek the particular"; BUG-LORI-
               REFLECTION-01 A.1 EXPLICIT REFLECTION DISCIPLINE block.)

DISCIPLINE-4  NO PSEUDO-EMPATHY
              Never open with "It sounds like you...", "It seems like
              you...", "That sounds like you...". Use "You mentioned X"
              or just name the detail.
              (Source: Alshenqeeti's "quasi-therapeutic" warning;
               BUG-LORI-REFLECTION-01 A.1.)

DISCIPLINE-5  NO INVENTED CONTEXT
              Never add places, feelings, durations, or interpretations
              the narrator did not just say.
              (Source: Cohen et al's bias factors — "misperceptions on
               the part of the interviewer regarding what the interviewee
               is saying"; BUG-LORI-REFLECTION-01 A.1.)

DISCIPLINE-6  NO LEADING QUESTIONS
              Don't pre-load the question with the desired answer.
              (Source: Alshenqeeti §7 "avoiding asking leading questions";
               not yet enforced as a runtime rule — gap candidate.)

DISCIPLINE-7  END-OF-SESSION INVITATION
              Give the narrator a chance to bring up comments or ask
              questions before closing. Re-express gratitude.
              (Source: Talmy 2010 in Alshenqeeti §4.1; not yet
               implemented — gap candidate, see Acceptance Gate B.)
```

Two gaps surfaced by external grounding (DISCIPLINE-6, DISCIPLINE-7) — file as separate sub-tasks when this WO opens.

### Layer 3 — Life-story topic canon (future question-pool / grounding)

**Status: NOT BUILT.** Spec only. Implementation lives in a future WO that consumes this canon.

The topic canon is a *recognition layer* (helps Lori detect what topic the narrator just opened) AND a *follow-up layer* (gives Lori a vocabulary of next-question prompts within each topic). It is NOT a checklist Lori must walk through. The narrator drives; the canon helps Lori recognize where they're driving.

Topics, organized by life-stage cluster (synthesized from UCLA + NEHGS + Freedom Center):

```
EARLIEST YEARS / EARLY SCHOOL
  birthplace · parents · siblings · birth-order
  childhood home · neighborhood · church · school
  food · holidays · family dinners · recipes
  relatives nearby · who raised you · who else lived there

ADOLESCENCE / COMING OF AGE
  school continued · first job · first crush · friendships
  hobbies · sports · music · books
  moves · houses · summers · weekends
  conflict at home · what you wanted to be

BUILDING YEARS
  work · identity through work · career changes
  marriage · meeting partner · wedding day
  children · parenting · houses lived in
  faith · community · service · military

LATER YEARS
  retirement · grandchildren · loss · widowhood
  illness · diagnoses · caregiving · being cared for
  what you'd tell your younger self · regrets · pride
  what mattered most · what surprised you

CROSS-CUTTING (any era)
  objects · houses · food · holidays
  turning points · before-and-after moments
  lessons · regrets · unfinished business
  the people you wish were still here
```

Each topic in this canon eventually maps to:

1. A **recognition pattern** (regex / keyword cluster) so Lori detects "the narrator is talking about X" during a turn.
2. A **follow-up vocabulary** (3-5 concrete-noun question stems) that Lori can use to invite continuation without imposing an agenda.
3. A **closure cue** (how to acknowledge and let go of the topic when the narrator signals they're done).

Implementation is deferred — this layer becomes a separate WO once Layer 1 + Layer 2 prove stable through 2-3 parent sessions and the gap candidates from Layer 2 (DISCIPLINE-6, DISCIPLINE-7) are addressed.

## Acceptance gates

```
Gate A — Layer 1 (kinship canon expansion)
  [ ] New kinship entry justified by ≥1 narrator transcript or
      canon-grounded eval case
  [ ] Validator unit-test added for the new entry's overlap path
  [ ] No extractor change (canon stays validator-side)

Gate B — Layer 2 (gaps DISCIPLINE-6, DISCIPLINE-7)
  [ ] DISCIPLINE-6 leading-question runtime rule scoped + landed
  [ ] DISCIPLINE-7 end-of-session invitation pattern scoped + landed
      (likely in WO-LORI-SESSION-AWARENESS-01 Phase 5)
  [ ] Both verified through golfball harness or live narrator session

Gate C — Layer 3 (topic canon)
  [ ] Recognition pattern + follow-up vocabulary for ≥3 topics
      per life-stage cluster
  [ ] Per-topic closure cue defined
  [ ] No auto-promotion to truth — recognition is for follow-up
      generation only
  [ ] Live-tested across all three Horne narrators before any
      generalization to Lorevox
```

## Out of scope

- **Extractor truth rules.** The kinship canon must NEVER feed the extractor. "Dad" → "father" is a validator-side normalization for grounding overlap; it must NOT trigger the extractor to write `parents.firstName=Father` or any similar inference.
- **Schema-level kinship inference.** Canon does not let Lori conclude "narrator said 'mom' so the mother field is non-null" — that's a separate inference the extractor handles via its own rules.
- **Auto-promotion of recognized topics.** Layer 3's topic recognition fires for follow-up generation only. Lori may follow up on "school" because she recognized the topic; she may NOT mark "narrator went to school = true" in any data store from recognition alone.
- **Therapeutic interpretation.** No canon entry maps narrator words to clinical/diagnostic categories ("loss" → "grief stage 3", "illness" → "diagnosed condition"). Lori is a companion, not a clinician — Alshenqeeti §8 is explicit on this risk and the values clause in WO-LORI-SAFETY-INTEGRATION-01 codifies it.
- **Demographic auto-fill from canon.** "Mom" doesn't tell Lori the mother's age, occupation, or living/deceased status. Canon helps Lori speak; it doesn't help her fill forms.

## Sequencing relative to other Lori-behavior WOs

```
BUG-LORI-REFLECTION-01            (Layer 1 partial land — kinship canon
                                   in validator; Layer 2 partial — A.1
                                   prompt rules)
                                   ↓
WO-LORI-LANGUAGE-CANON-01         (this WO — formalizes Layer 1, names
                                   Layer 2 principles, drafts Layer 3)
                                   ↓
WO-LORI-LANGUAGE-CANON-01 Gate B  (DISCIPLINE-6 + DISCIPLINE-7 gaps —
                                   leading-question rule, end-of-session
                                   invitation; likely fold into
                                   WO-LORI-SESSION-AWARENESS-01 Phase 5)
                                   ↓
WO-LORI-LANGUAGE-CANON-01 Gate C  (topic canon — separate WO when ready)
```

## The product rule (echoes WO-LORI-ACTIVE-LISTENING-01)

```
Schema    = what Lori CAN know.
Truth     = what Lori is allowed to TRUST.
Canon     = how Lori can RECOGNIZE narrator speech.
Behavior  = how Lori SPEAKS in response.

Brevity     = respect for the narrator's cognitive load.
Singular    = respect for the narrator's autonomy.
Particular  = proof Lori was actually listening.
No therapy  = respect for the narrator's wholeness.
```
