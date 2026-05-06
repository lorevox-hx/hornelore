# WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01 — Retire questionnaire-first from driving the live Lori interview; keep questionnaire as operator-side data entry

**Status:** OPEN — pre-parent-session blocker, ARCHITECTURAL. Promoted above BUG-LORI-SYSTEM-QF-PREEMPTION-01 (which becomes implementation evidence for this WO rather than an independent fix lane).
**Severity:** RED — affects every early-narrator session, race-conditions Lori against herself, fights memory_echo + Life Map + corrections + memoir-style recall, and reproduces an intake-form interrogation tone that's exactly wrong for older narrators.
**Surfaced by:** Chris (architectural decision, 2026-05-05), grounded in production evidence from manual switch transcripts 2026-05-06 02:59 + 03:02 (`transcript_switch_motgx.txt`, `transcript_switch_moth1.txt`) showing SYSTEM_QF auto-prompts hijacking real user messages.
**Author:** Chris + Claude (2026-05-05)
**Lane:** Lane 2 / parent-session blockers — TOP of behavioral queue. Supersedes the SYSTEM_QF preemption fix at architectural level.

---

## North Star

**Lori listens; Lorevox structures afterward.**

The narrator is the author of their own story. The interview is theirs to lead. Structured fields exist for the system's benefit, not the narrator's, and they belong on the operator's side of the seam — entered as data, not extracted by interrogation.

This WO implements that principle on the live-interview surface. It does not delete questionnaire data, schemas, fields, or operator tooling. It deletes the behavior of the questionnaire-first lane *driving Lori mid-conversation*.

## Locked rule (do not relitigate)

> **Live Lori session never auto-advances questionnaire fields.**

A live Lori interview is the narrator-led conversational surface — Lori reading, Lori listening, Lori reflecting, Lori asking ONE warm question grounded in narrator text. SYSTEM_QF prompts MUST NOT inject into this surface. Period.

Questionnaire-first remains available as:

1. **Operator-side form** — the existing BB / questionnaire UI for the operator to fill in directly.
2. **Pre-session setup** — operator may seed identity / family / structural fields before a session begins.
3. **Optional structured intake mode** — a manually-started, deliberately-entered mode where the operator (or a narrator who explicitly chose form-style intake) walks the questionnaire. NEVER auto-entered, NEVER mixed with normal conversation.
4. **Quiet capture from natural narrator speech** — when the narrator volunteers a fact ("I was the youngest of six"), the extractor + provisional-truth pipeline captures it as it does any other fact. Lori does not generate a SYSTEM_QF-style follow-up to drive remaining fields.

## Locked architecture (the upgrade)

```
Operator enters data into BioBuilder / questionnaire / profile
  → it becomes structured truth immediately (provisional or confirmed by source)
  → Lorevox stores it mechanically
  → Timeline renders it
  → memory_echo reads it
  → Life Map uses it
  → memoir export uses it

Lori does NOT re-discover it conversationally.
```

And in parallel:

```
Narrator-led speech
  → extractor / provisional truth
  → operator review / mirror
  → questionnaire gaps fill quietly when narrator volunteers
```

If a field is *gap* and the narrator never volunteers it, the field stays gap. Lori does not chase it. The operator can fill it directly if it matters.

## Acceptance rule (verbatim)

> **If narrator asks "what do you know about me," "what day is it," "what are the building years," or gives a correction, no SYSTEM_QF prompt may preempt the response.**

Generalized: no auto-injected SYSTEM_QF prompt may preempt ANY user message in a live Lori interview. The narrator's input is the only input the live loop responds to. SYSTEM_QF prompts have no entry point into the live narrator session.

## Bottom line (verbatim)

> **Do not delete questionnaire data. Delete questionnaire-driven interviewing from live Lori. And if the operator enters data into BB then it just is.**

The data layer is preserved. The schema is preserved. The operator-side surface is preserved. What is retired is the *runtime mechanism that has Lori asking the narrator structured-form questions during a memoir-style conversation.*

## Problem (current behavior)

The narrator-room currently runs a `questionnaire_first` lane that watches identity-anchor field state (`personal.birthOrder`, `personal.firstName`, `personal.dateOfBirth`, `personal.placeOfBirth`, `siblings.*`, `parents.*`, etc.) and auto-injects `[SYSTEM_QF: ...]` prompts to drive Lori through those fields. This produces three classes of failure:

1. **Race conditions** — when the narrator types a real message and SYSTEM_QF fires within the same turn window (0–1 second observed), Lori responds to SYSTEM_QF, not the narrator. Real evidence: Mary's "you tole me this last time" and Marvin's "what do you know about me" both lost to a birth-order question. (BUG-LORI-SYSTEM-QF-PREEMPTION-01.)
2. **Tone collapse** — even when the race resolves cleanly, the SYSTEM_QF prompts shape Lori into an intake-form interviewer ("Were you the oldest, the youngest, somewhere in the middle, or an only child?"), which is exactly the *not-a-companion* register Lorevox is trying to avoid for older narrators.
3. **Architectural fight** — SYSTEM_QF competes with memory_echo (turn-mode dispatch), with the Life Map era-click warm prompt, with WO-LORI-CONFIRM-01's planned confirm pass, with corrections mid-flow, and with the upcoming era-story readback (Phase 1c). Each new behavioral lane has had to negotiate with SYSTEM_QF rather than just compose.

The questionnaire-first design was reasonable as a way to ensure identity anchors got captured. But the *implementation choice* — drive it from inside the live conversational surface — has become the wrong shape. The right shape is operator-side data entry + quiet capture from natural speech.

## Evidence

`transcript_switch_motgx.txt` 02:59:32–02:59:43 — Mary types "you tole me this last time"; SYSTEM_QF fires 1 second later; Lori responds to SYSTEM_QF. Mary's actual message is dropped. Mary correctly identifies that Lori is treating her as a stranger and re-trying material she's already covered.

`transcript_switch_moth1.txt` 03:02:38 — Marvin types "what do you know about me"; SYSTEM_QF fires *the same second*; Lori responds to SYSTEM_QF. The recall question — which provably works in production when SYSTEM_QF doesn't fire — is lost.

Production transcripts (Mary + Marvin earlier in the same session) where memory_echo successfully read identity, computed age, recalled wife letters, and answered "what day is it" cleanly — proving the underlying capability is healthy. Only SYSTEM_QF preemption breaks it.

`OPERATOR-LOG-2026-05-06-03-02-57.md` carries 8 AMBER + 1 RED at session start, none related to QF — reinforcing that QF is silently active even on stack states the operator considers degraded; it doesn't gracefully sit out, it pushes through.

## Hypothesis-free fix shape

This is not a hypothesis-driven debug. The architectural decision is the fix.

**A. Detection.** Identify every entry point where SYSTEM_QF can inject into a live narrator chat path. Likely surfaces (verify before edit):

- The `questionnaire_first` lane scheduler (frontend, wherever it watches BB state and dispatches SYSTEM_QF prompts).
- Any backend chat_ws path that injects SYSTEM_QF directives as user-role messages.
- Any prompt_composer turn-mode dispatcher that routes to a SYSTEM_QF response template.
- Any `interview.js` / `app.js` boot path that auto-starts the QF lane on session_start.

**B. Suppress on the live narrator path.** All SYSTEM_QF auto-injection in the live narrator interview loop is gated OFF. Default: OFF. No env flag to turn it back ON in the live loop — this is a permanent retirement of that behavior. The operator-side intake mode + the natural-speech quiet capture replace it.

**C. Preserve the data layer.** The `personal.birthOrder`, `siblings.*`, `parents.*`, etc. schema fields stay. The questionnaire UI in the operator's BB stays. The questionnaire JSON shapes stay. Anything that *reads* these fields (memory_echo, Life Map, memoir, timeline render, projection sync) keeps working — it just stops being driven by an interview-time loop that *demands* they get filled.

**D. Operator-side data entry path.** Confirm the operator can fill BB fields directly and have those values flow into:
- `profiles.profile_json` (canonical confirmed truth)
- `interview_projections.projection_json` (provisional truth, when entered as such)
- `_build_profile_seed` (so Lori sees the values immediately on next turn)
- Timeline render
- Memory_echo readback

This path almost certainly already works — Phase A read-bridge (landed 2026-05-04) reads from both surfaces. This WO's job is to confirm operator-entered data behaves identically to narrator-volunteered data downstream, and document any gap as a sub-task.

**E. Natural-speech quiet capture.** When narrator volunteers a fact in normal conversation ("I was the youngest of six"), the existing extractor pipeline catches it as a candidate, writes provisional truth, mirrors to BB. No SYSTEM_QF response. Lori may *naturally* later say "you mentioned growing up as the youngest of six" if it's relevant — but that's narrative-aware composer behavior (existing prompt scaffolding), not a structured-field follow-up.

**F. Optional structured intake mode (manual start).** If we want the structured walk preserved as a *capability*, it lives behind an explicit operator gesture — a menu item like "Start structured intake" that switches the session into a clearly-different mode (different UI affordance, possibly different tone preset) and never auto-enters. Out of scope for this WO's first phase; flag the design space and defer.

## Implementation note — the smoking gun on switch-back greetings

A 2026-05-05 code review uncovered the concrete mechanism behind Mary's and Marvin's cold-start "Hi, I'm Lori" greetings on switch-back. The system already has a continuation-opener path:

- `server/code/api/routers/interview.py:495-547` — `/api/interview/opener?person_id=...` endpoint, branches `first_time` / `welcome_back` / `onboarding_incomplete` based on `user_turn_count` and `_identity_complete()`.
- Welcome-back template at `interview.py:486-489`: `"Welcome back, {name}. Where would you like to continue today?"`
- Frontend wires it on narrator open at `ui/hornelore1.0.html:5184-5204`.

But there is a **second gate at `ui/hornelore1.0.html:5179-5183`** that explicitly suppresses both the welcome-back SYSTEM prompt AND the opener fetch when `sessionStyle === "questionnaire_first"`. The comment from WO-13 / #207 reads:

> "questionnaire_first override — skipping welcome-back/opener so session-loop owns first prompt"
> "Firing the welcome-back here races the loop dispatch and Lori responds to whichever prompt was queued first — usually the welcome-back."

That gate is the precise reason both Mary and Marvin received cold-start greetings on switch-back: the operator session style was `questionnaire_first`, which intentionally suppresses the existing welcome-back composer so the QF lane can own first-prompt dispatch — and the QF lane fires its identity-onboarding cold-start template instead.

**Retiring QF from the live loop inverts this gate by construction.** Once `_ssIsQF` can never be true on the live path, the welcome-back composer fires correctly without needing any new continuation-greeting code. Phase 1's first concrete edit is therefore at `hornelore1.0.html:5179` — either remove the `_ssIsQF` branch entirely or reduce it to a no-op when the live narrator path is in use.

This same finding partially resolves BUG-LORI-SWITCH-FRESH-GREETING-01 — the basic continuation greeting starts working as soon as Phase 1 lands. The active-listening continuation paraphrase (era + last story + unfinished thread) remains a separate gap and is the proper scope for that BUG's Phase 2.

## Phases

**Phase 1 — Audit + suppress.** Find all SYSTEM_QF injection sites; gate them OFF on the live narrator path. **Concrete starting line:** `ui/hornelore1.0.html:5179` (`_ssIsQF` welcome-back/opener suppression). Verify with manual session: every test message Mary or Marvin sends produces a Lori response addressed to that message, never a SYSTEM_QF-shaped birth-order question. After Phase 1 lands, the existing welcome-back composer at `interview.py:486-489` should fire correctly on switch-back without any new code. Phase 1 is the parent-session blocker.

**Phase 2 — Operator data-entry verification.** Manual test: operator opens BB, enters birth order + siblings count + parent names; saves; verifies Lori's next memory_echo readback includes those values; verifies Lori does not re-ask any of them in subsequent turns. Document any seam that drops operator-entered data.

**Phase 3 — Natural-speech capture verification.** Manual test: narrator volunteers a quiet fact ("I was the youngest of six") in casual conversation; verify extractor catches it; verify provisional truth populates; verify it appears on next memory_echo readback; verify Lori does NOT respond with a SYSTEM_QF-style follow-up.

**Phase 4 — Optional structured intake mode (parked).** Design the manually-started intake mode as a separate surface. Do not implement until parent sessions are running cleanly without it.

## Acceptance gates

- After Phase 1: No SYSTEM_QF auto-prompt fires during a live narrator session. Verified by 30 minutes of manual testing across both narrators with provoked-questions ("what do you know about me", "what day is it", "what are the building years", a correction, a story disclosure).
- BUG-LORI-SYSTEM-QF-PREEMPTION-01's reproduction case (user message + SYSTEM_QF same second → Lori responds to SYSTEM_QF) is structurally impossible because SYSTEM_QF doesn't fire on the live path.
- Operator-entered BB data is reflected in Lori's runtime knowledge (memory_echo readback) within one turn.
- Narrator-volunteered facts are still captured to provisional truth (extractor unchanged).
- Lori never asks "Were you the oldest, the youngest, somewhere in the middle?" or any structurally-equivalent intake-form question, in a live session.
- Era-explainer ("what are the building years") works consistently — likely improves once SYSTEM_QF stops competing for the turn.
- Mid-stream corrections route correctly without SYSTEM_QF preempting.
- Memory_echo continues to work for "what do you know about me" reliably.

## Files (planned, after diagnostic read)

**Likely modified:**

- `ui/js/system-qf.js` (or wherever the QF auto-injection scheduler lives) — disable auto-dispatch on the live narrator interview path.
- `ui/js/interview.js` / `ui/js/app.js` — remove session_start hooks that auto-start the QF lane. If the QF UI affordance survives as a manual-start mode, gate it behind an explicit operator gesture.
- `server/code/api/routers/chat_ws.py` — verify no backend path is injecting SYSTEM_QF as user-role messages; if it is, gate it off on the live path.
- `server/code/api/prompt_composer.py` — verify no turn_mode branches into a SYSTEM_QF-shaped composer in the live path; if so, route those branches to the regular interview composer instead.
- `server/code/api/routers/interview.py` — verify no questionnaire-first state-machine ticks during a live session.

**Possibly modified:**

- `server/code/api/db.py` — verify operator-entered BB writes flow to `profiles.profile_json` correctly (probably fine; verify path).
- `ui/js/projection-sync.js` — verify operator-entered values don't get blocked by the BUG-312 protected-identity gate (operator entry is `human_edit` source = trusted).

**Zero touch:**

- Schema (`personal.*`, `siblings.*`, `parents.*` field definitions stay).
- BB UI on the operator side (the form keeps existing).
- Extractor (continues to capture from natural speech).
- memory_echo (continues to read both surfaces via Phase A read-bridge).
- Provisional-truth pipeline.
- Life Map.
- Timeline render (WO-TIMELINE-RENDER-01 pending — unaffected).

## Risks & rollback

**Risk 1: identity anchors don't get captured for narrators who don't volunteer them.** The QF-driven loop existed because some narrators won't say their own birth order, parents' names, etc. Without it, those fields stay gap.

*Mitigation:* this is the right outcome. If operator wants those fields populated, operator enters them directly in BB. If narrator never volunteers and operator never enters, the fields stay gap — Lorevox handles gap gracefully via "(not on record yet)" / blank rendering, and the memoir export tolerates gaps. The narrator dignity principle outranks completeness — better to have a clean memoir of what the narrator actually said than a complete questionnaire form filled by interrogation.

**Risk 2: existing narrator records have partially-filled QF state from prior sessions and the system expects QF to keep advancing.** Verify that any code reading `state.bioBuilder.questionnaire.next_field` or equivalent gracefully handles "no current target field" (returns null / no-op).

*Mitigation:* in Phase 1 audit, find and remove or null-check every consumer of QF next-field state.

**Risk 3: operator workflow regression — operator was relying on QF auto-advancement to remind them which fields to fill.** Possible but low; operator has BB UI which already shows field state visually.

*Mitigation:* the operator review surface already shows gap fields. If we want a "next gap" indicator, that's an operator-side UI feature, not a narrator-side prompt injection.

**Risk 4: tests / harnesses depend on QF firing.** TEST-23 / golfball / parent-session-rehearsal harnesses may have assertions that depend on a SYSTEM_QF prompt arriving.

*Mitigation:* Phase 1 includes a harness audit; any assertion that requires SYSTEM_QF in a live-session shape is wrong and gets removed or moved to a structured-intake-mode harness.

**Rollback:** restore QF auto-injection in the live loop. Race conditions return; Mary and Marvin start losing their messages to birth-order questions again. Not a path we'd want to take, but it's a single-flag-flip recovery if Phase 1 unexpectedly breaks something more critical.

## Sequencing

**This WO supersedes BUG-LORI-SYSTEM-QF-PREEMPTION-01 at the architectural level.** That BUG becomes evidence for this WO rather than an independent fix lane — the preemption race is structurally impossible if SYSTEM_QF isn't firing. After Phase 1 lands, BUG-LORI-SYSTEM-QF-PREEMPTION-01 can be closed as "resolved by retirement-WO landing."

This WO also probably resolves or substantially mitigates:

- **BUG-LORI-ERA-EXPLAINER-INCONSISTENT-01** — Mary's era-explainer failure is likely downstream of SYSTEM_QF preemption.
- **BUG-LORI-MIDSTREAM-CORRECTION-01** — corrections were getting hijacked by SYSTEM_QF; with QF gone, corrections route cleanly.
- **BUG-LORI-DUPLICATE-RESPONSE-01** — pending filing; verify whether QF preemption was causal.

This WO does **not** resolve:

- **BUG-LORI-SWITCH-FRESH-GREETING-01** — that's a separate cold-start-vs-continuation greeting bug; orthogonal to QF.
- **BUG-EX-DOB-LEAP-YEAR-FALLBACK-01** — extractor-side leap-year fallback; orthogonal.
- **BUG-EX-NAME-EXTRACTION-NOW-01** / **BUG-EX-POB-CORRECTION-WRONG-PATH-01** / **BUG-EX-LLM-COMMENTARY-AS-VALUE-01** — extractor-side, orthogonal.

Lands BEFORE BUG-LORI-SWITCH-FRESH-GREETING-01 because the resume greeting path is downstream of the live-interview path, and we want SYSTEM_QF gone first so the new continuation-greeting flow doesn't have to negotiate with it.

After this WO + BUG-LORI-SWITCH-FRESH-GREETING-01 + Phase 1c era-stories land, the live narrator session is structurally clean for parent sessions: no QF interruptions, continuation-shaped greetings on switch-back, and era-story readback wired into memory_echo.

## Cross-references

- **BUG-LORI-SYSTEM-QF-PREEMPTION-01** — implementation evidence for this WO; closes when this WO Phase 1 lands.
- **BUG-LORI-ERA-EXPLAINER-INCONSISTENT-01** — likely downstream of QF preemption; verify resolution after Phase 1.
- **BUG-LORI-MIDSTREAM-CORRECTION-01** — likely downstream; verify resolution after Phase 1.
- **BUG-LORI-SWITCH-FRESH-GREETING-01** — orthogonal but sequenced after this WO.
- **WO-LORI-CONFIRM-01** — parked. The 3-field confirm pilot was always orthogonal to QF auto-advancement (confirm pilot was about narrator-led confirmation of extracted candidates, not interrogation). Reactivates on its own evidence after this WO lands.
- **WO-PROVISIONAL-TRUTH-01 Phase A** — landed 2026-05-04; this WO depends on the Phase A read-bridge so operator-entered BB data flows into Lori's runtime knowledge. Phase E (write-back symmetry) is the partner that closes the visible-projection principle for operator entry.
- **WO-LORI-MEMORY-ECHO-ERA-STORIES-01 (Phase 1c)** — independent; lands after this WO so era-story readback isn't competing with SYSTEM_QF for the turn.
- **CLAUDE.md design principle 2** ("No operator leakage") — QF auto-injection was effectively operator-driven structure leaking into a narrator-facing surface. Retiring it tightens compliance with principle 2.
- **CLAUDE.md design principle 6** ("Lorevox is the memory system; Lori is the conversational interface to it") — this WO is the cleanest implementation of principle 6 to date. QF was Lori carrying the system's structure; retirement moves that structure to where it belongs (operator-side data entry + extractor-side capture).
- **CLAUDE.md design principle 7** ("Mechanical truth must visibly project") — operator-entered values must mirror visibly into Lori's runtime knowledge and Lori's outputs. Phase 2 of this WO verifies that path; any gap found is a separate sub-task.

## Changelog

- 2026-05-05: Spec authored after Chris's architectural decision to retire questionnaire-first from driving the live Lori interview. Locked rule + acceptance rule + bottom line all captured verbatim. Supersedes BUG-LORI-SYSTEM-QF-PREEMPTION-01 at architectural level.
