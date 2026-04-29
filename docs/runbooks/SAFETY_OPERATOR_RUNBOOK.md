# SAFETY Operator Runbook

**Owner:** Hornelore operator (Chris).
**Spec:** WO-LORI-SAFETY-INTEGRATION-01 Phase 9 acceptance gate (item 7).
**Status:** v1 — written 2026-04-29 for parent-session readiness.

> *Lori is a companion, not a clinician. Lori does not pretend not to hear.*

This document is for the operator running a Hornelore session — not for the narrator. It tells you what to do when Lori's safety layer fires during a session, how to read the operator banner, and how to debrief with the narrator afterward.

---

## Onboarding consent disclosure

Read this aloud (or show on screen) to **every** narrator before their first session, and again at the start of any session after a long gap. This is the spec's exact language and must not be paraphrased on the way in:

> *Lori is here to listen. If you ever say something that worries her, she will gently make sure you know about resources that can help, and she will let your operator know.*

If the narrator asks questions, the longer-form explanation:

- **Who is "your operator"?** It's the person who set up Hornelore — typically a family member, friend, or healthcare partner. Not a stranger, not a service.
- **What does "let your operator know" mean?** A short note appears on the operator's screen. It includes the category (worry, distress, etc.) and a brief excerpt of the moment, no scores, no judgments. The operator can check in with you later if they want to.
- **Will Lori share what I said with anyone else?** No. Hornelore runs entirely on this computer. Nothing goes to the cloud, no servers, no companies. The operator is the only other human who sees session content.
- **What if I don't want this?** Tell the operator. They can pause or end the session at any time. Lori will not push back.

**Acknowledgment.** For now, "narrator agreed" = operator hears the narrator say something like *"OK"* / *"that's fine"* / *"I understand"* before the first interview turn. Future versions will add a one-time modal acknowledgment with timestamp; for parent-session readiness today, the operator-side acknowledgment in conversation is sufficient.

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

## Cross-references

- Spec: `WO-LORI-SAFETY-INTEGRATION-01_Spec.md` Phase 9
- Backend safety scanner: `server/code/api/safety.py`
- Chat-path hook: `server/code/api/routers/chat_ws.py` L196-274
- Operator-event endpoints: `server/code/api/routers/safety_events.py`
- ACUTE SAFETY RULE prompt: `server/code/api/prompt_composer.py:108-193`

---

## Revision history

- 2026-04-29 — v1 written for parent-session readiness. Covers consent disclosure (item 8), operator banner decision tree (item 7), debrief guidance, and pre-session checklist.
