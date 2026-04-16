# WO-GREETING-01 — Lori self-introduces on session open

## Status: PARTIAL IMPLEMENTATION (backend endpoint + tests shipped, frontend wiring pending operator review)

## Rationale

Live observation 2026-04-15: narrators have to type "Hello" before Lori
says anything. Quote from operator:

> "Lori does not speak first until spoken too she should start with who
> and what she is maybe and about the questions and ansers for what etc"

That's a fixable UX contract. A memoir tool whose AI interviewer waits
passively for the narrator to initiate is backwards — the narrator
often doesn't know what this thing is or what they're supposed to do.

## Discovery — what already exists

The architecture has partial infrastructure:

- `GET /api/narrator/state-snapshot` returns `user_turn_count` (used to
  gate "welcome back" UX)
- `prompt_composer.py` has a `assistant_role == "onboarding"` branch that
  handles the very-first-session case when narrator identity is
  incomplete (no name / DOB / birthplace yet)

What's missing:

- No opener path for established narrators who already have identity
  complete. Janice, Kent, and Chris all have complete profiles and
  fall through the onboarding branch with no greeting.
- No frontend trigger that fires a first Lori utterance on session open.

## Scope

### Shipped in this WO (autonomous)

- New backend endpoint `GET /api/interview/opener?person_id=X`
- Returns narrator-aware opener text with `kind` metadata
- Unit tests covering first-time / returning / unknown-narrator cases
- No behavior change until frontend calls the endpoint

### Pending operator review / approval

- Frontend change to call `/api/interview/opener` on session open
- Display the returned text as a Lori turn before user input enabled
- Configuration: auto-fire vs operator-triggered

## Design

### Endpoint

```
GET /api/interview/opener?person_id=<uuid>

Response:
{
  "person_id": "<uuid>",
  "narrator_name": "Janice",
  "kind": "first_time" | "welcome_back" | "onboarding_incomplete",
  "opener_text": "Hi Janice, I'm Lori. I'm here to help you capture...",
  "context": {                        // optional — operator UI may surface
    "user_turn_count": 0,
    "has_prior_session": false,
    "last_topic": null
  }
}
```

### Template logic

Three cases based on narrator state:

**Case 1 — `onboarding_incomplete`:** narrator missing name, DOB, or
birthplace. Fall through to the existing prompt_composer onboarding
flow — don't emit a custom opener. Return empty `opener_text` with
`kind="onboarding_incomplete"` so the UI knows to skip.

**Case 2 — `first_time`:** narrator has complete identity but zero prior
user turns. Emit the full introduction:

```
Hi {name}, I'm Lori.

I'm here to help you capture your life story — the memories, the
people, the places that mattered to you. There's no wrong way to do
this. We can go in order of your life, or jump around to whatever
you want to talk about today.

What would you like to start with?
```

**Case 3 — `welcome_back`:** narrator has complete identity and non-zero
prior user turns. Emit a shorter greeting:

```
Welcome back, {name}. Where would you like to continue today?
```

Optionally enriched with last-topic context if available from transcript
summaries:

```
Welcome back, {name}. Last time we were talking about {last_topic}.
Want to pick up there, or go somewhere new?
```

### Narrator-name handling

Use `preferredName` if set, else `firstName`, else `fullName`, else
"friend" (safe fallback). Never use the full name + last name in the
greeting — feels clinical.

## Implementation

### File: `server/code/api/routers/interview.py`

New endpoint added alongside the existing interview routes. Reads
from `db.get_narrator_state_snapshot` to check identity completeness
and turn count. No new DB columns, no schema changes.

### Tests: `tests/test_interview_opener.py`

- `test_first_time_full_intro` — complete profile, zero turns → full intro
- `test_welcome_back_short` — complete profile, N turns → welcome back
- `test_onboarding_incomplete_empty` — missing identity → empty opener
- `test_unknown_narrator_404` — bad person_id → 404
- `test_name_fallback_chain` — preferredName > firstName > fullName > "friend"

## Frontend wiring (for operator review — NOT shipped in this WO)

When narrator card "Open" button is clicked:

1. Session initializes (existing flow)
2. Fetch `GET /api/interview/opener?person_id={narrator.id}`
3. If `kind == "onboarding_incomplete"`, skip and let existing flow
   drive
4. Otherwise, inject `opener_text` as an initial Lori turn in the
   chat UI BEFORE enabling user input
5. Optionally: fade in the input field 1 second after the opener
   renders, so narrator has time to read

Estimated frontend work: 1 hour.

## Acceptance criteria (backend only, this WO)

- [ ] Endpoint returns 200 with narrator-aware opener for valid
  person_id with complete profile, zero turns → full intro
- [ ] Endpoint returns 200 with short welcome-back opener for valid
  person_id with complete profile, > 0 turns
- [ ] Endpoint returns 200 with empty opener_text + kind="onboarding_incomplete"
  for narrator missing name/DOB/birthplace
- [ ] Endpoint returns 404 for unknown person_id
- [ ] Name fallback chain works
- [ ] All tests pass
- [ ] No regressions in existing interview endpoints

## Out of scope

- Frontend wiring (operator to review + wire)
- Voice / TTS synthesis of opener (separate — TTS already handles
  outgoing Lori text if wired)
- Configurable greeting templates (could be a .env-driven template
  later; for now templates are hardcoded)
- Per-narrator greeting preferences (future)
