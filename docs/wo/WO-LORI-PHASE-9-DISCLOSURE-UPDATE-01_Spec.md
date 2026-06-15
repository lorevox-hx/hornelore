# WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01

**Status:** SPEC — not yet started; depends on WO-LORI-SAFETY-PAST-TENSE-ACKNOWLEDGE-01
and WO-LORI-SOFTENED-MODE-PERSISTENCE-01 reaching GREEN
**Severity:** HIGH (consent honesty; required before oral-history default flip)
**Locked principle:** *The consent disclosure describes what Lori actually
does. Not what we wish she did. Not what is easier to say. What she does.*

## Why this WO exists

The Phase 9 onboarding consent disclosure and operator runbook were
written against the questionnaire-first / cognitive-support default
posture and the original SAFETY-INTEGRATION-01 Phase 0+1 acute-only
safety model. With:

- past-tense acknowledgment (new state machine)
- mortality reflection as classified non-safety (new state)
- softened-mode persistence after acute (N=5)
- brief softened after past-tense (N=2)
- oral-history posture as default (sibling WO)

...the existing consent language no longer matches behavior. Families
reading the v9 disclosure will form expectations that the system will
violate, in either direction:

- They may expect a chatbot disclaimer that flees from any mortality
  mention, and be surprised when Lori sits with it
- They may expect a casual conversational partner with no safety
  infrastructure, and be surprised when 988 dispatches

Both surprises damage trust. The disclosure must be edited to describe
the actual three-state behavior honestly.

**This is an edit WO, not a rewrite.** The v9 disclosure structure
stays. Specific sections are revised, three new short sections are
inserted, and one operator-runbook section is extended.

## Scope of edit

Three documents are touched:

1. **Onboarding consent disclosure** (family-facing, shown at narrator
   intake) — edit existing sections + insert three new short sections.
2. **Operator runbook safety chapter** — extend with past-tense and
   softened-mode operational guidance.
3. **`docs/golfball/` lineage doc** — add a single paragraph
   cross-referencing this WO and the two sibling WOs so the
   disclosure → code mapping is traceable.

## Document 1 — Onboarding consent disclosure

**Source file:** existing Phase 9 disclosure (locate in repo;
likely `docs/PHASE-9-CONSENT-DISCLOSURE.md` or similar — confirm
during build).

**Editing principles:**

- Preserve the existing tone (calm, plain, no clinical jargon)
- Preserve the existing structure (intro → what Lori does → what
  Lori doesn't do → safety → operator role → questions)
- Insert new material in the safety section, not at the top
- No marketing language. No softening of difficult facts. Families
  reading this are choosing whether to let an aging parent talk
  to an AI; they get the truth.

### Edit 1.1 — "What Lori does" section

EXISTING (paraphrased — confirm exact text during build):
> Lori asks questions about your family member's life and listens
> to their stories. She is designed to be gentle and patient.

REVISED:
> Lori is built to conduct an oral-history conversation. She is
> not a questionnaire and not a chatbot. Her job is to listen to
> the stories your family member wants to tell, follow chapters
> at their pace, and gently help them stay oriented in time and
> place. She remembers what she has been told and uses it later
> in conversation, the way a good interviewer would.
>
> Lori is patient. Long pauses are welcome. Long stories are
> welcome. If your family member wants to sit quietly for a moment,
> Lori will sit quietly with them.

Rationale: existing language understates what Lori does; oral-history
default needs to be set as the expectation at the top.

### Edit 1.2 — "What Lori does not do" section

EXISTING (paraphrased):
> Lori is not a therapist and not a medical professional. She does
> not provide medical or psychological advice.

REVISED (preserves existing language, adds two clauses):
> Lori is not a therapist and not a medical professional. She does
> not provide medical or psychological advice.
>
> Lori does not redirect away from difficult subjects. Older
> adults often reflect on loss, mortality, and difficult periods
> of their lives as part of telling their story. Lori is built to
> receive these reflections as memoir material, not as problems
> to be managed.
>
> Lori does not pretend not to hear. If your family member shares
> something heavy, Lori will acknowledge it briefly and stay
> present. She does not flee from difficult moments, and she does
> not perform concern she does not have.

Rationale: families need to know upfront that Lori will not deflect
mortality content. Without this, the first time Lori receives a
mortality reflection calmly instead of redirecting, the family may
read it as malfunction.

### Edit 1.3 — Safety section (substantial revision)

This is the largest edit. The existing safety section likely
describes acute-only behavior (988, operator notification). Replace
with a three-tier description that matches the actual state machine.

REVISED safety section:

> **How Lori handles difficult moments**
>
> Older adults sometimes share things with a calm listener that
> they would not say to family directly. Lori is configured to be
> capable of receiving these disclosures. This is intentional.
> The behavior is divided into three tiers, each handled
> differently.
>
> **Mortality reflection.** When your family member talks about
> their own death in the ordinary way that older adults do —
> outliving friends, making peace with the end of life, planning
> what to leave behind — Lori treats this as memoir content. She
> does not interrupt the conversation. She does not offer crisis
> resources. She listens. This material is part of the life story
> and belongs in the memoir.
>
> **Past difficulty narrated as memoir.** When your family member
> describes a hard period in their past, including past thoughts
> of not wanting to go on, Lori will acknowledge it briefly with
> one short, calm sentence. She will not ask follow-up questions
> about it. She will let your family member choose whether to
> continue the thread or move on. The operator will see a quiet
> flag in the post-session review so any appropriate follow-up
> can happen outside the session if needed. Nothing happens during
> the session beyond the acknowledgment.
>
> **Present concern.** When your family member expresses
> present-tense thoughts of self-harm or not wanting to be alive,
> Lori will pause the interview, acknowledge what was shared, and
> provide the number for the 988 Suicide and Crisis Lifeline. The
> operator will receive an immediate notification. For the next
> several turns of conversation, Lori will stay quiet and gentle —
> she will not ask interview questions and will not return to
> earlier topics. The conversation will only return to its normal
> shape when your family member is ready.
>
> **What this means for families.** Lori can be a trusted listener
> for difficult disclosures. We do not know in advance which
> conversations will go to difficult places. Some never do. Some
> do briefly, in past tense, and pass. A small number may involve
> present concern, and Lori is built to respond to those
> appropriately. If you would prefer that Lori be configured for
> a more structured questionnaire-style conversation that minimizes
> open-ended exploration, the operator can switch to that mode at
> any time.

Rationale: this is the load-bearing edit. Every clause maps to a
specific state in the architecture:
- "Mortality reflection" paragraph → `mortality_reflection`
  classifier state (sibling WO)
- "Past difficulty" paragraph → `past_tense_acknowledge` state +
  N=2 softened (sibling WOs)
- "Present concern" paragraph → existing acute path + N=5 softened
  (this WO + sibling)
- Final paragraph → operator override to questionnaire_first style
  (oral-history default WO, not yet shipped — phrasing future-proofs)

### Edit 1.4 — New section: "How Lori is configured for your
family member"

INSERT after the safety section, before operator role:

> Lori has several conversation styles. By default, she is in
> oral-history mode — she listens long, asks little, follows the
> narrator's chapters at the narrator's pace. This is the right
> mode for narrators who can carry a chapter and want to.
>
> If your family member has memory difficulty, finds open-ended
> conversation tiring, or prefers a more structured experience,
> the operator can switch Lori to a different mode:
>
> - **Warm storytelling** — shorter exchanges, more frequent
>   reflection, gentler pacing
> - **Memory exercise** — companion mode designed for narrators
>   with mild cognitive variability; listens first, prompts
>   sparingly
> - **Companion** — minimal interview structure; Lori is mostly a
>   present listener
> - **Questionnaire first** — structured biographical questions in
>   sequence; for narrators who want a clearer scaffold
>
> The operator can switch modes during a session if a different
> mode is working better. The narrator does not need to choose;
> the operator chooses.

Rationale: families need to know the modes exist and what they
mean. This section also handles the cognitive-support fallback
honestly — naming it without making it the default.

### Edit 1.5 — Signature / acknowledgment block

EXISTING signature block likely confirms understanding of the
disclosure. Add one new acknowledgment line:

> I understand that Lori is configured for oral-history conversation
> by default, and that she will receive mortality reflection and
> past-tense difficulty as memoir content rather than redirecting
> away from them. I understand the present-concern safety path.

Rationale: the consent has to land on the actual new behaviors,
or it isn't real consent.

## Document 2 — Operator runbook safety chapter

**Source file:** existing operator runbook (locate during build).

### Edit 2.1 — Existing acute-path section

EXISTING content describes acute path (988, notification). PRESERVE.
No changes — the acute path itself is unchanged by this trio.

### Edit 2.2 — New subsection: Past-tense acknowledgment flag

INSERT after acute-path section:

> **Past-tense acknowledgment flag**
>
> If a narrator shares past-tense memoir ideation during a session
> ("after Mom died, there was a year I didn't want to go on"), Lori
> will acknowledge it briefly from a small fixed phrase bank and
> continue listening. No 988 is dispatched and no in-session
> notification is sent.
>
> A flag of type `past_tense_ideation_acknowledged` will appear
> in your post-session review queue with an amber-bordered card.
> The card shows the narrator turn, Lori's acknowledgment, and
> three decision options:
>
> - **No action** — the disclosure was memoir content; nothing
>   further is needed
> - **Follow up outside session** — flag for a real conversation
>   with the narrator or family outside the Hornelore session
> - **Convert to active concern** — escalate this disclosure for
>   immediate attention as if it were present-tense
>
> Most past-tense flags will be "no action." The flag exists so
> that you, as the operator, see the disclosure and choose, rather
> than the system choosing for you.

### Edit 2.3 — New subsection: Softened-mode behavior

INSERT after the past-tense subsection:

> **Softened mode after a safety moment**
>
> After Lori dispatches an acute safety response, the session
> enters softened mode for approximately 5 turns. After a
> past-tense acknowledgment, the session enters brief softened
> mode for 2 turns.
>
> During softened mode, Lori will:
>
> - Not ask questions
> - Not return to the previous topic
> - Not summarize or analyze what was shared
> - Stay short, calm, and present
> - Let the narrator's pace determine the next move
>
> When the softened window expires, Lori does not snap back to
> interview cadence. She enters a one-turn recovery state where
> she will follow the narrator into chapter only if the narrator
> is clearly back in chapter themselves. She will not say "where
> were we" or anything that resumes the interview before the
> narrator does.
>
> You will see this as quieter Lori turns for several minutes
> after a safety moment, even when the narrator seems to have
> moved on. This is intentional. If the narrator wants to keep
> going, they will, and Lori will follow.
>
> If a second acute event occurs during softened mode, the window
> extends rather than restarting — the system takes the longer
> of the two windows.

### Edit 2.4 — New subsection: Mortality reflection is not flagged

INSERT after softened-mode subsection:

> **Mortality reflection is not flagged**
>
> Ordinary mortality reflection from older narrators — "most
> everyone I served with is gone," "I won't be around much
> longer," "I've made peace with it" — is classified as memoir
> content. No flag is written. No softened state is entered.
> Lori listens and the chapter continues.
>
> You may still see these moments in the session transcript and
> may want to note them for memoir editing purposes, but the
> system does not surface them for review. They are part of the
> story.

### Edit 2.5 — Existing "what to watch for during a session" checklist

Existing checklist likely focuses on session start, narrator
distress signals, technical issues. PRESERVE existing items.
APPEND two new items:

> - Quieter Lori turns following an acute or past-tense moment
>   are softened-mode working correctly, not a malfunction
> - Mortality reflection received calmly is the system behaving
>   correctly, not a missed safety signal

## Document 3 — `docs/golfball/` lineage cross-reference

INSERT one short paragraph in the existing lineage doc index, in
the safety lane section:

> **Past-tense and softened-mode lane (WO trio).**
> WO-LORI-SAFETY-PAST-TENSE-ACKNOWLEDGE-01 introduces the
> three-dimension classifier (category × tense × subject) and
> the deterministic acknowledgment path for past-tense self-directed
> ideation narrated as memoir. WO-LORI-SOFTENED-MODE-PERSISTENCE-01
> implements the N-turn softened state machine that consumes the
> brief softened state from past-tense and the longer state from
> acute. WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01 edits the consent
> disclosure and operator runbook to honestly describe the
> resulting behavior. Together these three WOs close parent-session
> readiness Gate 6 and enable the oral-history-default flip in
> WO-LORI-ORAL-HISTORY-DEFAULT-01.

Rationale: trace from disclosure language back to code is critical
when (not if) someone asks "why does Lori behave this way" six
months from now.

## Acceptance gates

1. **Disclosure describes actual three-tier behavior.**
   - Mortality reflection, past-tense, present concern all
     named and described
   - Each tier's family-facing description matches the
     code-level state machine in the sibling WOs

2. **Disclosure names operator override to questionnaire_first.**
   - Family knows that oral-history is default and that the
     operator can switch modes
   - Mode names match the existing operator picker exactly
     (`oral_history`, `warm_storytelling`, `memory_exercise`,
     `companion`, `questionnaire_first`)

3. **Consent signature block explicitly acknowledges new behaviors.**
   - Signature line references oral-history default and the three
     safety tiers
   - Cannot be skipped or shortened — the consent is on the
     actual behavior, not the old behavior

4. **Operator runbook covers four new operational scenarios.**
   - Past-tense flag handling with three decision options
   - Softened-mode behavior (acute N=5, past-tense N=2)
   - Mortality reflection NOT flagged (counter-intuitive — must
     be explicit)
   - Softened-mode extension on nested acute

5. **Lineage doc traces disclosure language to code.**
   - The three sibling WOs are named in `docs/golfball/` lineage
     index
   - Someone reading the disclosure can find the code in <2
     hops

6. **No clinical or marketing language introduced.**
   - Tone-matched to existing v9 disclosure (calm, plain,
     no jargon)
   - No "we care about your family" softening
   - No "this is a safe space" claims that we cannot enforce

7. **Existing acute-path language preserved unchanged.**
   - The acute path itself didn't change in this trio; the
     disclosure language about the acute path doesn't change
     either. Only additions and contextualizing edits.

## Test coverage

Disclosure is a document, not code, but the changes need
verification:

- **Diff review by operator** before merge. The operator running
  parent sessions reads the entire new disclosure aloud and
  confirms it matches what they would tell a family in person.
- **Cross-reference check** — every behavior described in the
  disclosure must be verifiable in the sibling WO acceptance
  gates. If a sentence in the disclosure describes behavior that
  isn't in code, that sentence is wrong and must be edited or
  the code added.
- **Tone diff** — read existing v9 disclosure and new disclosure
  back-to-back. Tone must be indistinguishable. If the new sections
  read as more clinical, more marketing, or more legalistic, edit
  before merge.
- **Operator runbook walkthrough** — operator runs through
  golfball harness with new runbook open and confirms each new
  operational scenario is covered by clear guidance.

## Live verification

1. After both sibling WOs are GREEN, print updated disclosure
   and runbook
2. Walk through with operator who has run prior parent sessions
3. Specifically pressure-test:
   - "What if Janice talks about Dad's death and starts crying?"
     → disclosure should answer: Lori receives, brief acknowledgment
     possible if it lands as care, no flag, no softened
   - "What if Kent says he sometimes thinks about not being here
     anymore?" → disclosure should answer: depends on tense.
     Past tense → acknowledgment + flag. Present tense → acute.
   - "What if the operator thinks Lori responded wrong?" →
     runbook should answer: thumbs-down feedback, manual flag
     conversion, or mode switch — no in-session intervention to
     Lori's response itself

## Files changed

- `docs/PHASE-9-CONSENT-DISCLOSURE.md` (or equivalent — confirm
  during build) — substantial edits per Section 1.1-1.5
- `docs/OPERATOR-RUNBOOK.md` (or equivalent — confirm during build)
  — additions per Section 2.2-2.5
- `docs/golfball/INDEX.md` (or equivalent lineage doc) — one
  paragraph addition per Section 3

NO code changes. This WO is documentation only.

## Related lanes

- **WO-LORI-SAFETY-PAST-TENSE-ACKNOWLEDGE-01** (precedes;
  required GREEN before this WO can be honestly written)
- **WO-LORI-SOFTENED-MODE-PERSISTENCE-01** (precedes; required
  GREEN before this WO can be honestly written)
- **WO-LORI-ORAL-HISTORY-DEFAULT-01** (follows; requires this
  WO GREEN before the default flip — families must consent on
  the actual behavior before that behavior becomes default)
- **SAFETY-INTEGRATION-01 Phase 9** (predecessor; this WO is
  the v9 → v10 disclosure update; the original Phase 9
  groundwork stays in place and is extended, not replaced)

## Out of scope (deferred)

- Translation of disclosure to Spanish. Hornelore narrators are
  English-primary; translation is a separate localization lane.
- Disclosure for trainer narrators (Shatner, Dolly). They are
  reference data, not real subjects; no consent surface needed.
- Family-facing dashboard showing past-tense flags or session
  events. Considered and rejected — family is not in the operator
  loop by design; operator briefs family outside the system.
- Audio/video version of consent disclosure for narrators with
  low literacy. Park; speak with operator about whether real
  Hornelore narrators need this.
- Pre-session reminder of disclosure terms at each session start.
  Considered — would create friction for daily-driver usage by
  operator. Disclosure is at intake; session start is operational.
