# Kent floor-control — operator instructions for the morning session

Per Chris's locked rule: **Kent owns the floor until he or the
operator explicitly releases it.** Lori must not respond when Kent
pauses to breathe, thinks, or continues the same chapter.

This is operator discipline tomorrow + a defensive backend handler
that's already landed. The full claimed-floor UI buffer is a separate
WO that didn't ship tonight.

## Practical limits

| Talk duration | Word count | Behavior |
|---|---|---|
| 1-5 min | 100-700 words | Safe single turn |
| 5-10 min | 700-1,500 words | Safe single turn |
| 10-15 min | 1,500-2,500 words | Safe but lean prompt |
| 15-25 min | 2,500-4,000 words | RISKY — may hit context limit |
| 25+ min | 4,000+ words | DO NOT send as one turn — split |

For Kent's army-at-18 chapter tomorrow, target **5-10 minute chunks
of speech, ~700-1,500 words per Send press**. He can talk for 30
minutes total — just split it into 3-4 chapters with explicit
"that's the end of that part" beats between them.

## Operator workflow tomorrow (Chrome typed input)

The session is typed input, not microphone. You're the operator
listening to Kent, transcribing into the chat. Workflow:

**While Kent is talking:**
1. Type into the chat input as he speaks. Don't worry about
   formatting — get the words down.
2. **DO NOT press Send while Kent is mid-thought.** Even on long
   pauses. Even when he says "let me think for a second."
3. Watch his face. If he's still constructing, keep listening.

**When Kent says or signals he's done with this part:**
- "OK, that's the end of that part."
- "Then I went to..." (pivot to a new chapter)
- He looks up at you, asking for the next question.
- He goes silent for 30+ seconds with body language relaxing.

THEN press Send.

**After Lori responds (one receipt + one door):**
- Read her response to Kent.
- Wait for him to answer.
- He may go into another long chapter — same workflow.

**If Kent gives a short answer (≤7 words like "yeah, that's right"):**
- Press Send right away.
- Lori's bank-flush will fire, asking ONE banked question from
  earlier in the chapter.

## Defensive backend handler — already landed

Two protections live in code right now:

1. **Long-monologue flush guard.** If a narrator turn is ≥40 words,
   the bank-flush is HARD-BLOCKED — won't fire even if a cue word
   is present in the last sentence. So if Kent's chapter contains
   "I asked what else was available" mid-prose, that won't trigger
   a bank-flush interruption.

2. **`turn_final=false` defensive ack.** When the FE eventually adds
   claimed-floor buffering, it will send `turn_final=false` on
   partial chunks. Backend will respond "I'm listening." with no
   LLM call, no witness, no bank-flush. Forward-compat — the
   current FE doesn't send this flag yet, so the Send-button-as-
   release is the only mechanism today.

## Things that COULD interrupt Kent (mitigations)

| Risk | Mitigation |
|---|---|
| Operator presses Send mid-thought | OPERATOR DISCIPLINE — wait for explicit release |
| Kent says "what else?" rhetorically mid-chapter | Last-sentence + ≤8-word cue gate (landed) |
| Bank-flush selects junk question | Malformed-question filter (landed) |
| Mic STT auto-sends on silence | NOT applicable — typed input only |
| Multiple Send presses by accident | OPERATOR DISCIPLINE — single deliberate press |
| Page reload mid-chapter | Reconnect protocol resets — would lose buffer; avoid |

## What success looks like tomorrow morning

Kent's army-at-18 chapter, hypothetical:

> [Kent talks 8 minutes about Stanley → Fargo → induction → meal
>  tickets → conductor → Fort Ord → M1 → ASA-vs-Nike pivot. Operator
>  types as he speaks. Kent eventually says "...and that's how I
>  ended up in missile training instead."]

Operator presses Send.

> Lori: "You went from the Stanley depot to Fargo for induction,
>  scored high enough to be trusted with meal tickets for the train
>  west, pushed back on the conductor when the food was bad, then
>  finished basic at Fort Ord with M1 expert. The Army Security
>  Agency wait pushed you into Nike Ajax/Hercules training instead.
>  Where did the Army send you for that missile training?"

Bank now contains 5-8 unanswered doors:
- Fargo physical/mental exam process
- Meal-ticket responsibility detail
- Conductor confrontation
- GED testing connection
- Career-choice calculus (ASA-vs-Nike)
- Detroit/Selfridge training base
- ...

Kent answers. Several minutes more. Send. Lori responds. Bank fills more.

Eventually Kent says "yeah" or "that's all I remember about that."
Bank-flush fires: *"I want to come back to one detail you mentioned
earlier. What was the Fargo physical and mental exam process like?"*

That's the full patience layer working.

## Stop rules during live session

If Lori does ANY of these, hit pause and screenshot:

- Responds while you haven't pressed Send (impossible by design today,
  but flag it if it happens — would mean an FE bug).
- Asks scenery / sights / sounds / smells / camaraderie / teamwork.
- Speaks AS Kent ("we were", "our son", "my wife", "I went").
- Asks more than one question per response.
- Bank-flush interrupts a chapter (impossible — ≥40 word gate).
- Bank-flush asks a junk question ("you corrected to just" — filtered).
- Spanish or Spanglish anywhere.

Stop, paste back, we patch.

## Bottom line

For tomorrow:
- **Don't press Send until Kent is done with a chapter.**
- **5-10 minute chapters ≈ 700-1,500 words is the target.**
- **The patience layer + monologue gate + malformed filter are all
  in code as of 2026-05-10.**
- **The full claimed-floor FE buffer is the next WO** — for tonight,
  operator discipline is the floor-control mechanism.

Never interrupt the narrator to protect the model. Protect the
narrator by buffering, chunking, and banking follow-ups.
