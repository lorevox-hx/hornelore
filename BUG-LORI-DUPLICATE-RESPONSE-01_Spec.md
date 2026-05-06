# BUG-LORI-DUPLICATE-RESPONSE-01 — Lori repeats prior turn verbatim when narrator re-asks

**Status:** OPEN — pre-parent-session blocker (UX confidence)
**Severity:** AMBER — narrator-visible. Older narrators tracking conversation flow notice the repetition; younger narrators may not catch it but the system feels mechanical.
**Surfaced by:** Manual switch transcript 2026-05-06 03:00:18–03:00:31 (`transcript_switch_motgx.txt`). Mary asked "what are the building years"; Lori responded with the EXACT BIT-IDENTICAL text she had emitted 13 seconds earlier in response to a different prompt.
**Author:** Chris + Claude (2026-05-05; filed during night-shift Phase 0 BUG sweep)
**Lane:** Lane 2 / parent-session blockers — orthogonal to QF-RETIRE; needs independent investigation.

---

## Problem

When the narrator's turn input doesn't trigger any other dispatch path (memory_echo / safety / correction / era-click / SYSTEM_QF / Life-Map system prompt) AND the LLM context shape happens to be identical to a prior turn (or near-identical with low-temperature sampling), Lori produces a bit-identical response to the prior turn.

The narrator experiences this as Lori not listening — same answer, different question.

## Evidence

`transcript_switch_motgx.txt` lines 13–26:

```
[2026-05-06 03:00:13] USER: [SYSTEM: The narrator just selected 'Building
Years' on the Life Map — they want to talk about this era of their life.
Ask ONE warm, open question about this period. Frame the question in
PAST TENSE...]

[2026-05-06 03:00:18] ASSISTANT: During your building years, what do you
remember about your daily routine when you were working and raising your
family?

[2026-05-06 03:00:26] USER: what are the building years

[2026-05-06 03:00:31] ASSISTANT: During your building years, what do you
remember about your daily routine when you were working and raising your
family?
```

The 03:00:18 response was generated for the SYSTEM era-click directive at 03:00:13.

The 03:00:31 response was generated for Mary's actual user message at 03:00:26 — a different prompt asking for an explanation, not a question to answer.

The two responses are **bit-identical**. Same wording, same punctuation, same length. That's not coincidence — it's either a cached response, a re-fired composer with cached LLM context, or an LLM sampling at low temperature that produced identical output for similar context.

## Diagnosis hypotheses (ranked)

**Hypothesis 1 (most likely): LLM context shape is too similar across turns.** Lori's context window includes the era-click system prompt + Mary's "what are the building years" — which the LLM may treat as Mary affirming the era selection rather than asking for a definition. With temperature low + identical-feeling input, the LLM emits the same response token-by-token.

**Hypothesis 2: Response cache / dedupe failure.** If `chat_ws.py` or `lori_communication_control.py` has a per-session response cache keyed on a similarity hash, the cache might be returning a cached prior response. (Quick check needed: grep for `response_cache` / `last_response` / similar in chat_ws path.)

**Hypothesis 3: composer dispatcher misroutes.** The era-click system prompt at 03:00:13 lingers in the turn-mode state; when Mary's 03:00:26 turn arrives, the dispatcher reads a stale "era_click_active" flag and re-fires the same era-click composer with the same inputs, producing the same output. Probably falsifiable with a `[lori][turn-mode] selected=era_click` log marker check.

**Hypothesis 4: missing turn-uniqueness guard.** A simple "if response_text == last_response_text, regenerate with higher temperature" guard would catch verbatim repetitions before they reach the narrator. None currently exists. This is a cheap defense-in-depth fix even if root cause is hypothesis 1 or 2.

## Reproduction

In a real browser:

1. Open Mary (returning narrator with prior turns).
2. Click "Building Years" on Life Map → Lori asks an era-anchored question.
3. Wait for Lori's response to land.
4. Type any short message like "what are the building years" or "yes" or "tell me more."
5. Failure mode: Lori's second response is bit-identical (or near-identical with only minor word swaps) to her prior response.

Run 5 times. Track how often verbatim repetition fires.

## Fix shape

**Phase 1 — Diagnose root cause.** Before fixing, instrument:
- Add `[lori][response-hash] turn=N hash=...` log marker in `chat_ws.py` after every LLM response is captured.
- Read api.log; count how often two consecutive turns produce the same hash.
- Cross-reference with `[lori][turn-mode]` log to see if the dispatcher is misrouting OR if turn-mode is correct but LLM is producing identical output.

**Phase 2 — Fix per diagnosis.**

If hypothesis 1 (LLM sampling): bump temperature one notch when a response would match the prior turn's hash. Or: add narrator's most recent message to the system prompt's "do not repeat" list explicitly.

If hypothesis 2 (response cache): find the cache, fix the eviction key, invalidate on any narrator turn.

If hypothesis 3 (dispatcher misroute): clear the era-click / system-directive state after the directive's response lands. Subsequent narrator turns route through normal interview composer.

**Phase 3 — Defense-in-depth guard.** Regardless of root cause, add a deterministic post-LLM check in `lori_communication_control.py` Step 5 (after shape_reflection, before send): if `shaped_text` matches the last assistant response in the session by ≥80% similarity (Jaccard / Levenshtein normalized), regenerate once with higher temperature. If the regenerated response also matches, prepend a small acknowledgment fragment ("To answer your earlier question — ...") and emit anyway. The regenerate-once budget keeps cost predictable; the acknowledgment fallback prevents infinite loops.

## Acceptance gate

After fix:
- 0 of 10 attempts at the reproduction produces bit-identical consecutive responses.
- ≤ 1 of 10 attempts produces ≥80%-similar consecutive responses (residual is acceptable when narrator's question genuinely warrants a similar answer; the regenerate guard catches the actual-bug cases).
- The defense-in-depth guard fires fewer than once per 50 turns on average — false positives matter (narrator asking "tell me more" twice in a row legitimately gets a similar follow-up).
- No new latency tax: regenerate-once budget bounds the worst case at 2× LLM cost on the rare flagged turn.

## Files (planned)

**Phase 1 (diagnose):**
- `server/code/api/routers/chat_ws.py` — add `[lori][response-hash]` log marker + `[lori][last-response]` history accessor.

**Phase 2 (fix per diagnosis):**
- One of:
  - `server/code/api/prompt_composer.py` — temperature bump path
  - `server/code/api/routers/chat_ws.py` — cache invalidation fix
  - `server/code/api/services/lori_communication_control.py` — turn-mode state clearing

**Phase 3 (defense-in-depth, optional):**
- `server/code/api/services/lori_communication_control.py` — new Step 5.5 similarity check.
- `tests/test_lori_response_uniqueness.py` — 10+ unit tests covering same-vs-similar discrimination, regenerate-once budget, acknowledgment fallback.

## Risks and rollback

**Risk 1: regenerate-once tax in cost / latency.** When the guard fires, the LLM runs twice for that turn. Mitigation: budget bound is 2×; the guard fires <2% of turns based on observed frequency; total session cost change is <4%.

**Risk 2: false-positive on legitimate similar follow-ups.** Narrator asks "tell me more" three times in a row → all three should get similar follow-up prompts; the guard might over-trigger and produce weird off-topic regenerations. Mitigation: similarity threshold tuned to 80%+; legitimate follow-ups typically diverge at 70-75% Jaccard which stays below the trigger. The acknowledgment fallback is graceful even when the regenerate doesn't help.

**Risk 3: acknowledgment fallback feels patronizing.** "To answer your earlier question — " before every flagged response. Mitigation: only prepend on explicit-question turns (narrator text contains a question word); for affirmative narrator turns, just emit the regenerated response without the prefix.

**Rollback:** revert the guard. Verbatim repetitions return at the observed frequency. No data harm.

## Sequencing

Land **after** WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01 Phase 1 — QF retirement may reduce the frequency of this BUG by removing one source of identical-context turns. Re-measure repetition rate after Phase 1; if it's already <1%, Phase 2 of THIS BUG can be deferred.

Land **alongside** BUG-LORI-ERA-EXPLAINER-INCONSISTENT-01 — both BUGs may share a single underlying composer-dispatch fix (hypothesis 3 of this BUG overlaps with hypothesis 2 of the era-explainer BUG).

## Cross-references

- **BUG-LORI-ERA-EXPLAINER-INCONSISTENT-01** — same Mary transcript; the verbatim repetition at 03:00:31 IS the era-explainer's second-attempt failure. Both BUGs may share a fix.
- **WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01** — Phase 1 may reduce this BUG's frequency by removing SYSTEM_QF turns from the live path; verify after Phase 1 lands.
- **BUG-LORI-REFLECTION-02 Patch C (LANDED 2026-05-05)** — runtime shaping at `lori_reflection.shape_reflection()`. This BUG's Phase 3 guard would slot into the same Step 5 pipeline; can compose with Patch C.
- **WO-LORI-RESPONSE-HARNESS-01** — response-quality test harness can include a `verbatim_repetition_rate` metric to track this BUG's frequency over time.

## Changelog

- 2026-05-05: Spec authored during night-shift Phase 0 BUG sweep after `transcript_switch_motgx.txt` re-read surfaced the bit-identical 03:00:18 → 03:00:31 response pair. Sequenced after QF-RETIRE Phase 1 + alongside BUG-LORI-ERA-EXPLAINER-INCONSISTENT-01 since both may share a composer-dispatch root cause.
