# BUG-LORI-SYSTEM-QF-PREEMPTION-01 — `[SYSTEM_QF]` auto-prompts hijack user messages arriving in the same turn window

**Status:** OPEN — pre-parent-session blocker (top of behavioral lane)
**Severity:** RED — real production evidence; affects every early-narrator session where SYSTEM_QF questionnaire-first lane is active. Likely root cause behind several other apparent failures (era-explainer inconsistency, "what do you know about me" hangs, dropped corrections).
**Surfaced by:** Manual switch transcripts 2026-05-06 02:59:32 + 03:02:38
**Author:** Chris + Claude (2026-05-05 → 06)
**Lane:** Lane 2 / parent-session blockers — top of behavioral queue

---

## Problem

The narrator-room's `questionnaire_first` lane auto-injects `[SYSTEM_QF: ...]` prompts to drive Lori through identity-anchor field collection (birthOrder, parents, siblings, etc.). When the SYSTEM_QF prompt fires concurrent with (or one second after) a user's message, Lori sees both, picks the SYSTEM_QF as the response target, and ignores the user.

The user's question goes unanswered. The user thinks Lori didn't hear them, or that she's evading. They re-ask. The same race fires. The user gets frustrated.

This is probably the root cause behind:
- **"What do you know about me" no-response** in earlier transcripts (system_qf hijacks the recall query)
- **Era-explainer inconsistency** (Marvin's session had no SYSTEM_QF active; Mary's did)
- **Dropped corrections** (when narrator says "Actually it's Minot, North Dakota — not just ND" mid-flow, SYSTEM_QF can win)

## Evidence

`transcript_switch_motgx.txt` — Mary in switch session:
```
[2026-05-06 02:59:32] USER: you tole me this last time
[2026-05-06 02:59:33] USER: [SYSTEM_QF: questionnaire_first lane — next field is personal.birthOrder. Ask conversationally...]
[2026-05-06 02:59:43] ASSISTANT: Were you the oldest, the youngest, somewhere in the middle?
```
1-second gap between Mary's real message and the SYSTEM_QF auto-prompt. Lori responds to SYSTEM_QF.

`transcript_switch_moth1.txt` — Marvin asking the explicit recall question:
```
[2026-05-06 03:02:38] USER: what do you know about me
[2026-05-06 03:02:38] USER: [SYSTEM_QF: questionnaire_first lane — next field is personal.birthOrder. Ask conversationally...]
[2026-05-06 03:02:54] ASSISTANT: Were you the oldest, the youngest, somewhere in the middle, or an only child?
```
**Zero-second gap** — SYSTEM_QF fires the same second as the user message. Lori responds to SYSTEM_QF, ignores "what do you know about me".

Compare to a successful memory_echo response in the parent transcript (the same Marvin earlier in the session):
```
USER: but what do you know about me
ASSISTANT: What I know about Marvin Mann so far: Identity ...
```
That one worked because no SYSTEM_QF preempted it. So memory_echo IS working in production — but it gets stolen by SYSTEM_QF when the timing aligns.

## Why memory_echo working makes this priority

Without this bug, "what do you know about me" reliably produces the readback. With it, the same question randomly works or fails depending on whether SYSTEM_QF auto-injects at the wrong moment. That's confidence-eroding for narrators — same question, different responses, no apparent reason. Older narrators with cognitive load especially won't track that the system is racing — they'll just feel that Lori is being inconsistent.

## Diagnosis hypothesis

The chat_ws.py turn-mode dispatch picks ONE prompt to respond to per Lori turn. When two user messages arrive close together (real user + SYSTEM_QF auto-injection), the dispatch picks the second one (most-recent). SYSTEM_QF wins because it arrives last.

Three candidate fixes:

**A. User-priority rule.** Real user messages always win over auto-injected SYSTEM prompts within the same turn window. SYSTEM_QF gets queued for the NEXT turn, not the current one. This is the right architectural fix.

**B. Turn-window debounce.** SYSTEM_QF only fires after N seconds of narrator silence (e.g., 3-5 seconds). If the narrator types within that window, SYSTEM_QF cancels for that turn.

**C. Dual-prompt response.** Lori responds to BOTH the user AND the SYSTEM_QF in a combined response ("[answer to user]. By the way, ..."). Probably bad UX — feels chatty, breaks the one-question discipline.

Hypothesis A is cleanest. SYSTEM_QF is supposed to drive the questionnaire-first walk forward when the narrator is silent or just confirming; it's not supposed to compete with substantive user questions.

## Reproduction

In a real browser session:
1. Start a new test narrator (fresh, will have SYSTEM_QF active)
2. Provide name + DOB + POB
3. Wait briefly until SYSTEM_QF starts firing for birthOrder/parents/etc.
4. Mid-question, send a user message like "what do you know about me" or "what day is it"
5. Watch which prompt Lori responds to. If she answers the SYSTEM_QF question instead of yours, repro confirmed.

## Acceptance gate

After fix:
- User messages arriving within the same chat_ws turn window as a SYSTEM_QF auto-prompt cause Lori to respond to the user, not the SYSTEM_QF
- SYSTEM_QF queues for the next turn boundary (after Lori's response to the user lands)
- The "what do you know about me" memory_echo readback works reliably regardless of questionnaire-first state
- Era explainer ("what are the building years") works for Mary as well as Marvin (likely — if downstream of this bug)
- New manual smoke test: send a user message at the exact moment SYSTEM_QF fires. User message wins.

## Files (planned, after diagnostic read)

**Likely modified:**
- `server/code/api/routers/chat_ws.py` — turn-mode dispatch logic, prompt-priority handling
- `ui/js/system-qf.js` (or equivalent — wherever the SYSTEM_QF auto-injection scheduler lives) — add the user-message-pending check before firing

**Possibly modified:**
- `server/code/api/services/lori_communication_control.py` — the comm-control wrapper might be the right place to detect the dual-message-window case and route to the user message

**Zero touch:**
- Memory_echo composer (already works correctly when allowed to fire)
- Phase A read-bridge (working)
- Extract router

## Risks & rollback

**Risk 1: SYSTEM_QF gets dropped permanently.** If the queueing logic has a bug, the SYSTEM_QF for that field never re-fires and the questionnaire-first walk stalls. Mitigation: SYSTEM_QF re-queue after the next narrator silence; same trigger condition as before but re-attempted after the user message resolved.

**Risk 2: Important system prompts get blocked too.** ACUTE SAFETY RULE, era-click prompts, identity-onboarding prompts — these aren't SYSTEM_QF; they're different injection paths. The fix should narrowly target SYSTEM_QF specifically, not all system prompts. ACUTE SAFETY in particular MUST always fire (existing safety architecture).

**Risk 3: Race condition becomes silent.** The bug is currently visible (user gets weird responses); after the fix the queue might silently swallow user messages if implemented wrong. Mitigation: log marker `[chat_ws][system_qf] preempt-deferred user_message_pending` so operators can see when SYSTEM_QF defers.

**Rollback:** revert. SYSTEM_QF goes back to racing user messages. No regression on flows where SYSTEM_QF isn't active.

## Sequencing

Top of behavioral queue. Fix this BEFORE BUG-LORI-ERA-EXPLAINER-INCONSISTENT-01 (which is likely downstream) and BEFORE BUG-LORI-MIDSTREAM-CORRECTION-01 (corrections may be a SYSTEM_QF-preemption case in disguise).

After fix, re-run the manual switch session and try "what do you know about me" / "what day is it" / "what are the building years" mid-questionnaire. All should respond to user, not to SYSTEM_QF.

## Cross-references

- **BUG-LORI-ERA-EXPLAINER-INCONSISTENT-01** — Mary's failure to get explanation likely downstream of this bug
- **BUG-LORI-MIDSTREAM-CORRECTION-01** — corrections may be SYSTEM_QF-preemption cases
- **WO-LORI-SESSION-AWARENESS-01 Phase 2 (interview discipline)** — this fix may also affect the discipline rules that govern SYSTEM_QF triggering frequency

## Changelog

- 2026-05-06: Spec authored after Chris's manual switch sessions surfaced the SYSTEM_QF preemption pattern. Likely root cause behind multiple apparent failures.
