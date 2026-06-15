# SAFETY Operator Runbook

**Owner:** Hornelore operator (Chris).
**Spec:** WO-LORI-SAFETY-INTEGRATION-01 Phase 9 acceptance gate (item 7); WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01 (2026-06-14 — three-tier safety + oral-history default).
**Status:** v2 — extended for post-SAFETY-LLM-CLASSIFIER-01 / SOFTENED-MODE-PERSISTENCE-01 behavior.

> *Lori is a companion, not a clinician. Lori does not pretend not to hear.*

This document is for the operator running a Hornelore session — not for the narrator. It contains the consent disclosure to read with the narrator's family, the operational guidance for the three-tier safety state machine, and the debrief flow for after a session.

---

## Onboarding consent disclosure

Read this with the family BEFORE the first session, and again before any session after a long gap. The language below is the v2 disclosure; it describes the actual behavior of the system as of 2026-06-14. **Do not paraphrase on the way in** — the consent has to land on what Lori actually does.

If the family asks questions while you read, the Q&A block at the end of this section is the longer-form answer set. Take the time. The consent is what makes the rest of this OK.

### What Lori does

> Lori is built to conduct an oral-history conversation. She is not a questionnaire and not a chatbot. Her job is to listen to the stories your family member wants to tell, follow chapters at their pace, and gently help them stay oriented in time and place. She remembers what she has been told and uses it later in conversation, the way a good interviewer would.
>
> Lori is patient. Long pauses are welcome. Long stories are welcome. If your family member wants to sit quietly for a moment, Lori will sit quietly with them.

### What Lori does not do

> Lori is not a therapist and not a medical professional. She does not provide medical or psychological advice.
>
> Lori does not redirect away from difficult subjects. Older adults often reflect on loss, mortality, and difficult periods of their lives as part of telling their story. Lori is built to receive these reflections as memoir material, not as problems to be managed.
>
> Lori does not pretend not to hear. If your family member shares something heavy, Lori will acknowledge it briefly and stay present. She does not flee from difficult moments, and she does not perform concern she does not have.

### How Lori handles difficult moments

> Older adults sometimes share things with a calm listener that they would not say to family directly. Lori is configured to be capable of receiving these disclosures. This is intentional. The behavior is divided into three tiers, each handled differently.
>
> **Mortality reflection.** When your family member talks about their own death in the ordinary way that older adults do — outliving friends, making peace with the end of life, planning what to leave behind — Lori treats this as memoir content. She does not interrupt the conversation. She does not offer crisis resources. She listens. This material is part of the life story and belongs in the memoir.
>
> **Past difficulty narrated as memoir.** When your family member describes a hard period in their past, including past thoughts of not wanting to go on, Lori will acknowledge it briefly with one short, calm sentence. She will not ask follow-up questions about it. She will let your family member choose whether to continue the thread or move on. The operator will see a quiet flag in the post-session review so any appropriate follow-up can happen outside the session if needed. Nothing happens during the session beyond the acknowledgment.
>
> **Present concern.** When your family member expresses present-tense thoughts of self-harm or not wanting to be alive, Lori will pause the interview, acknowledge what was shared, and provide the number for the 988 Suicide and Crisis Lifeline. The operator will receive an immediate notification. For the next several turns of conversation, Lori will stay quiet and gentle — she will not ask interview questions and will not return to earlier topics. The conversation will only return to its normal shape when your family member is ready.
>
> **What this means for families.** Lori can be a trusted listener for difficult disclosures. We do not know in advance which conversations will go to difficult places. Some never do. Some do briefly, in past tense, and pass. A small number may involve present concern, and Lori is built to respond to those appropriately. If you would prefer that Lori be configured for a more structured questionnaire-style conversation that minimizes open-ended exploration, the operator can switch to that mode at any time.

### How Lori is configured for your family member

> Lori has several conversation styles. By default, she is in **oral-history** mode — she listens long, asks little, follows the narrator's chapters at the narrator's pace. This is the right mode for narrators who can carry a chapter and want to.
>
> If your family member has memory difficulty, finds open-ended conversation tiring, or prefers a more structured experience, the operator can switch Lori to a different mode:
>
> - **Warm storytelling** — shorter exchanges, more frequent reflection, gentler pacing
> - **Memory exercise** — companion mode designed for narrators with mild cognitive variability; listens first, prompts sparingly
> - **Companion** — minimal interview structure; Lori is mostly a present listener
> - **Questionnaire first** — structured biographical questions in sequence; for narrators who want a clearer scaffold
>
> The operator can switch modes during a session if a different mode is working better. The narrator does not need to choose; the operator chooses.

### The operator's role

> The operator is the person who set up Hornelore — typically a family member, friend, or healthcare partner. Not a stranger, not a service. When Lori receives something that may need attention, the operator sees a short note on their screen. The operator decides what to do with it — including doing nothing, if the disclosure was memoir content and nothing further is needed.
>
> Hornelore runs entirely on the operator's computer. Nothing goes to the cloud, no servers, no companies. The operator is the only other human who sees session content.

### Family questions (Q&A)

If the family asks questions while you read, here are the longer-form answers:

- **Who is "the operator"?** It's the person who set up Hornelore — typically a family member, friend, or healthcare partner. Not a stranger, not a service.
- **What does "the operator will see a flag" mean?** A short note appears on the operator's screen showing the category and a brief excerpt of the moment — no scores, no judgments. The operator decides what to do with it, including doing nothing.
- **Will Lori share what my family member said with anyone else?** No. Hornelore runs entirely on this computer. Nothing goes to the cloud, no servers, no companies. The operator is the only other human who sees session content.
- **What if my family member doesn't want this?** Tell the operator. They can pause or end the session at any time. Lori will not push back.
- **What if Lori gets it wrong?** She will sometimes. The operator can flip the past-tense flag to "no action," switch modes mid-session, or stop the session entirely. The system is designed assuming the operator is in the loop.

### Acknowledgment

> *I understand that Lori is configured for oral-history conversation by default, and that she will receive mortality reflection and past-tense difficulty as memoir content rather than redirecting away from them. I understand the present-concern safety path: pause, acknowledge, 988 reference, operator notification, several quieter turns after. I understand the operator can switch conversation modes at any time.*

For now, "family agreed" = the operator hears the family member say something like *"OK"* / *"that's fine"* / *"I understand"* after the disclosure. Future versions will add a one-time written acknowledgment with timestamp; the operator-side verbal acknowledgment is sufficient for v2.

---

## When the operator banner fires

Hornelore's safety layer (`server/code/api/safety.py`) scans every narrator turn for category-specific language. When something matches, the operator gets a banner card in the Bug Panel showing:

- **Category** — `suicidal_ideation`, `distress_call`, `cognitive_distress`, `sexual_abuse`, `physical_abuse`, `domestic_violence`, `caregiver_concern`, etc.
- **Matched phrase** — up to 60 chars of what the regex matched
- **Turn excerpt** — up to 200 chars of the narrator's message for context
- **Time + narrator + session id**

The banner does NOT include a severity score, risk rank, or trend line. It's just: *what fired, when, in what context.* You decide what to do with it.

### Decision tree

| Category | Acuity | Operator action |
|---|---|---|
| `suicidal_ideation` (active, present-tense) | **CRITICAL** | Be physically present with the narrator NOW if safe. If they describe a plan, immediate access to means, or are alone and accelerating: **call 911**. Otherwise dial 988 with them or for them — do not leave them to dial it themselves. Stay with them through the call. |
| `suicidal_ideation` (past, reflective — "When I was younger I thought about it") | **REFLECTIVE** | Lori already responded warmly. No emergency action needed. Sit with the narrator quietly; ask if they want to keep going or take a break. Don't pivot back to interview questions immediately. The banner can be acknowledged after the session settles. |
| `distress_call` ("I can't take this", "I want it to stop") | **HIGH** | Pause the interview. Ask "Are you OK to keep talking, or do you want a quiet moment?" Listen, don't problem-solve. If distress escalates, treat as `suicidal_ideation` ACUTE. If it settles, the banner can wait. |
| `cognitive_distress` ("I can't remember", "I'm losing it") | **MEDIUM** | This is often elder-narrator frustration, not crisis. Lower the cognitive load — switch to memory_echo, take a break, offer to come back tomorrow. Don't add complexity. |
| `sexual_abuse` / `physical_abuse` / `domestic_violence` | **HIGH** (operator awareness, not 911 unless active) | The narrator may be disclosing for the first time. Sit with it. Do NOT promise confidentiality you can't keep — if a child is at risk, you may have mandatory reporting obligations. After the session ends, decide privately whether to follow up. The Friendship Line (1-800-971-0016, 60+ specific) is a warm-line option you can mention later, not in the moment. |
| `caregiver_concern` (about another person) | **MEDIUM** | Listen. The narrator may be processing fear about their parent / sibling / partner. Acknowledge. Don't move to action unless they ask. |

### What NOT to do when a banner fires

- Don't say to the narrator "you've been flagged" or "the system noticed."
- Don't read the banner content aloud to the narrator. It's for you.
- Don't change Lori's tone mid-turn. She's already in softened mode by the time you see the banner.
- Don't treat the matched phrase as gospel. Regex matches can be reflective ("I used to feel like that"), idiomatic ("kill me now I forgot the milk"), or quoting someone else. The category is a hint, not a verdict.
- Don't pivot back to interview questions for at least 2-3 turns after a high-acuity event. Memory echo or a gentle silence is the right move.

### Acknowledging the banner

When you click "Acknowledge" on a banner card:
- The card disappears from your active view
- A timestamp + your acknowledgment is recorded in `safety_events.acknowledged_at` / `acknowledged_by`
- The event stays in the historical digest — you can scroll back later

Acknowledge **after** you've decided what to do, not before. If you ack and walk away, you've taken responsibility for the moment without acting on it.

---

## Past-tense acknowledgment flag

If a narrator shares past-tense memoir ideation during a session — *"after Mom died, there was a year I didn't want to go on"* — Lori will acknowledge it briefly from a small fixed phrase bank and continue listening. No 988 is dispatched and no in-session notification is sent.

A flag of type `past_tense_ideation_acknowledged` appears in your post-session review queue with an amber-bordered card. The card shows the narrator turn, Lori's acknowledgment, and three decision options:

- **No action** — the disclosure was memoir content; nothing further is needed
- **Follow up outside session** — flag for a real conversation with the narrator or family outside the Hornelore session
- **Convert to active concern** — escalate this disclosure for immediate attention as if it were present-tense

Most past-tense flags will be "no action." The flag exists so that you, as the operator, see the disclosure and choose, rather than the system choosing for you.

The card lives in the Bug Panel's past-tense review surface (gated behind `HORNELORE_OPERATOR_PAST_TENSE_REVIEW=1`). Without that env flag the endpoint 404s and the card doesn't render — which is the safe default if you're not yet ready to triage these flags.

---

## Softened mode after a safety moment

After Lori dispatches an acute safety response, the session enters softened mode for approximately 5 turns. After a past-tense acknowledgment, the session enters brief softened mode for 2 turns. Both windows are env-tunable via `HORNELORE_SOFTENED_N_ACUTE` and `HORNELORE_SOFTENED_N_PAST_TENSE`; the defaults are 5 and 2.

During softened mode, Lori will:

- Not ask questions
- Not return to the previous topic
- Not summarize or analyze what was shared
- Stay short, calm, and present
- Let the narrator's pace determine the next move

When the softened window expires, Lori does NOT snap back to interview cadence. She enters a one-turn recovery state where she will follow the narrator into chapter only if the narrator is clearly back in chapter themselves. She will not say *"where were we"* or anything that resumes the interview before the narrator does.

You will see this as quieter Lori turns for several minutes after a safety moment, even when the narrator seems to have moved on. **This is intentional.** If the narrator wants to keep going, they will, and Lori will follow.

If a second acute event occurs during softened mode, the window extends rather than restarting — the system takes the longer of the two windows. A short nested past-tense flag during a longer acute window cannot shorten the acute recovery.

The `[chat_ws][softened]` log lines in `api.log` show the state machine in real time: `state=softened trigger=acute turns_remaining=5` while in softened, `state=softened_exiting` on the bridge turn, then an `inactive` line when the session returns to normal cadence.

---

## Mortality reflection is not flagged

Ordinary mortality reflection from older narrators — *"most everyone I served with is gone,"* *"I won't be around much longer,"* *"I've made peace with it"* — is classified as memoir content. No flag is written. No softened state is entered. Lori listens and the chapter continues.

You may still see these moments in the session transcript and may want to note them for memoir editing purposes, but the system does NOT surface them for review. They are part of the story, not a signal of crisis.

If you ever see mortality reflection routed acute (988 in the response, banner card on screen), that is a system error — the classifier mis-tagged it. Acknowledge the banner, switch to memory_echo or pause the session if the narrator is rattled, and report the misclassification for prompt tuning. The 15-case `SpecificitySetTest` in `tests/test_safety_classifier_three_dim.py` is the unit-test floor that's supposed to prevent this; a live miss means the prompt needs work.

---

## Debriefing with the narrator afterward

If a banner fired during a session, a check-in conversation is part of the operator's job. Suggested timing:

- Same day if possible, ideally before bed or before they sit alone with what came up
- Phone, in-person, or a written note — narrator's choice
- Don't make it clinical. *"I noticed you brought up your brother today. How are you sitting with that?"* is enough.

If the narrator asks whether Hornelore "told you" something, be honest:
> *"Yes — when you say something Lori thinks I should know about, she sends me a short note. That's how the system works. I wanted to check in with you about it."*

That answer is consistent with the consent disclosure they heard at session start.

---

## Resource library (curated; no improvisation)

Lori is allowed to mention **only** these resources. She will never invent a hotline or service.

| Resource | Number | When |
|---|---|---|
| 988 Suicide & Crisis Lifeline | **988** (call, text, or chat) | Active suicidal ideation, crisis. Available 24/7 nationwide. |
| 911 | **911** | Imminent danger, medical emergency, active means + plan + access. |
| Poison Control | **1-800-222-1222** | Suspected overdose / ingestion. Available 24/7. |
| Friendship Line (60+) | **1-800-971-0016** | Loneliness, distress, non-acute support for older adults. Warm-line, not crisis-line. |

If the narrator names a resource not on this list, Lori may listen but will not endorse it. The operator can make their own judgment outside the session.

---

## Operator's pre-session checklist

Before opening a narrator session for Kent / Janice / Christopher:

- [ ] Stack restarted within last 4 hrs (so warmup is current)
- [ ] `HORNELORE_OPERATOR_SAFETY_EVENTS=1` in `.env` so the Bug Panel banner can render
- [ ] Bug Panel open in a separate tab/window OR within reach
- [ ] Phone with 911 + 988 in recents, OR a printed copy of the resource list above
- [ ] If first-ever session: read the consent disclosure aloud to the narrator
- [ ] Narrator has acknowledged consent (verbal "OK" is sufficient for v1)
- [ ] You have ~30 quiet uninterrupted minutes ahead of you

Don't start a session if any of those are missing. The narrator can wait; the system needs you present.

---

## What to watch for during a session

In addition to the banner cards in the Bug Panel, these are the operational signals that the system is behaving correctly (as opposed to malfunctioning):

- Quieter Lori turns following an acute or past-tense moment are softened-mode working correctly, not a malfunction. Expect 5 turns of brief, present responses after acute and 2 turns after past-tense, followed by a one-turn bridge before normal cadence resumes.
- Mortality reflection received calmly — no 988 dispatch, no banner — is the system behaving correctly, not a missed safety signal. The classifier distinguishes mortality reflection (memoir) from present-concern ideation (acute) by design.

---

## Cross-references

- Specs: `docs/wo/WO-LORI-SAFETY-LLM-CLASSIFIER-01_Spec.md` (3-dim classifier + 4-route dispatch), `docs/wo/WO-LORI-SOFTENED-MODE-PERSISTENCE-01_Spec.md` (3-state softened machine), `docs/wo/WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01_Spec.md` (this runbook update). Original Phase 9 acceptance gate: `docs/archive/workorders-pre-pivot/WO-LORI-SAFETY-INTEGRATION-01_Spec.md`.
- Backend safety scanner: `server/code/api/safety.py`
- LLM classifier + routing: `server/code/api/safety_classifier.py`
- Past-tense acknowledgment bank: `server/code/api/safety_acknowledgments.py`
- Softened-state directive picker: `server/code/api/services/lori_softened_response.py`
- Chat-path hook + 4-route dispatch + softened write/read: `server/code/api/routers/chat_ws.py`
- Operator-event endpoints: `server/code/api/routers/safety_events.py`
- Past-tense flag review endpoint: `server/code/api/routers/operator_past_tense_review.py`
- ACUTE SAFETY RULE prompt: `server/code/api/prompt_composer.py:108-193`
- Lineage doc: `docs/golfball/README.md`

---

## Revision history

- 2026-04-29 — v1 written for parent-session readiness. Covers consent disclosure (item 8), operator banner decision tree (item 7), debrief guidance, and pre-session checklist.
- 2026-06-14 — v2 extension under WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01. Consent disclosure rewritten against the actual post-SAFETY-LLM-CLASSIFIER-01 / SOFTENED-MODE-PERSISTENCE-01 behavior — three-tier safety description, oral-history default posture, mode-picker, expanded acknowledgment. Three new runbook subsections added: past-tense acknowledgment flag, softened mode after a safety moment, mortality reflection is not flagged. Pre-session checklist gains a "what to watch for" appendix. Existing acute-path content preserved unchanged.
