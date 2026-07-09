# BUG-LORI-TRIP-DIRECT-QUESTION-DODGE-01

**Status:** FILED 2026-07-09 (not started). Separate from trip story capture —
this is a Lori *behavior* issue, not a data-capture issue.

## Symptom (live, 2026-07-09 Spring 2026 trip session)

In trip mode, the narrator asked Lori a direct question and Lori deflected
twice instead of answering:

```
Narrator: what can you tell me about the weather story that i was told,
          do you know of anything
Lori:     "You mentioned a weather story that was shared with you. Take your
          time, I can wait. What specifically comes to mind…"
Narrator: i asked you a question about it.
Lori:     "You'd like to revisit the topic. Let's go back to the story of your
          trip. Earlier, you mentioned Munich's Father's Day…"
```

The interview-discipline steering ("ask one question, don't explore") is so
strong that Lori ignores a direct question aimed at her. To an older narrator
this reads as not listening.

## Desired behavior (trip mode, direct narrator question)

1. **Answer briefly IF the answer is grounded** in approved trip context
   (trip title/dates/route, `include_in_interview_context=1` notes,
   narrator-ready photo captions — the same surface `trip_interview_context`
   already provides). No invention, no browsing.
2. **If not known**, say so honestly and hand the thread back, e.g.:
   > "I don't have that specific explanation in the trip notes yet. I only
   > know you were told there was a regional weather pattern around
   > Regensburg. What did the person call it, if you remember?"
3. Then optionally return to ONE short follow-up. Never fabricate a fact,
   never claim to have looked something up.

## Hard boundaries

- No invented facts, no web/browse, no image inference.
- Only surface trip facts that are already in approved trip context.
- Stays within the one-question / short-turn discipline otherwise.

## Notes

- This does NOT touch trip story capture. Capture already (as of the
  2026-07-09 hotfix) SKIPS these direct-question turns with
  `reason=direct_question_or_command`, so they never become memoir notes.
  This bug is only about Lori's *reply* to such a question.
- Likely lands in the interview/trip prompt-composer path (an
  "answer-first when the narrator asks a direct trip question" rule),
  composing with the existing ACTIVE-LISTENING / discipline rules. Scope +
  eval before wiring.

## First fix — 2026-07-09 (directive in the trip-context block)

The trip-context block header (`trip_interview_context._BLOCK_HEADER`) used to
say only "use it to ask ONE warm question," which actively pushed Lori to
deflect direct questions. Rewrote it to lead with: *if the narrator asks what
you know/remember about the trip, ANSWER directly from these facts (name +
dates + a few places), do not deflect, do not answer a question with a
question; OTHERWISE ask one warm question.* Since the block is appended last to
the system prompt it is the most salient guidance. 18 context tests still green.

**If this prompt directive proves insufficient** (Lori still deflects under the
strong interview-discipline steering), the robust fix per this codebase's own
locked pattern is a **deterministic intercept**: detect a trip-info question
when a trip is open + owned, compose a warm answer from
`build_trip_interview_context`, and send it deterministically (mirroring
`lori_meta_question`). Scope + eval before wiring that.
