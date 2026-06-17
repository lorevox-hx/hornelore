# John Baldy Life Map Era-Click Harness — Run Report 2026-06-17

**Operator:** Chris (via Chrome MCP agent)
**Narrator:** John Baldy
**person_id:** `d11572d4-57a1-4100-8426-cfd7293a7441`
**Session style:** `oral_history` (default)
**Stack:** localhost:8000 (api) + localhost:8082 (ui)
**Outcome:** STOPPED AT ERA 1 — one real bug surfaced, one false alarm
self-corrected before filing.

## Preflight API readback (PASS)

```
GET /api/bio-builder/questionnaire?person_id=d11572d4-...
→ http 200
→ source: bio_facts_merged                ✓ (Phase 1 read swap active)
→ personal.fullName: John Baldy           ✓
→ personal.dateOfBirth: 1960-12-31        ✓
→ personal.placeOfBirth: "west St. Paul Minnestota"   (typo in seed,
                                                       not a runtime bug)
→ personal.pronouns: he/him               ✓
→ personal.currentResidence: Las Vegas NM ✓
→ military.served: false                  ✓ (critical guard intact)
→ _meta sections: personal, parents, siblings, spouses, children,
                  education, military, faith, today  ✓
```

## What happened

1. Started narrator session via Operator tab → `Start Narrator Session`.
2. Lori greeted John with a clean warm oral-history opener (visible in
   bubble 0).
3. Clicked Life Map button "Earliest Years" → era-confirm popover
   appeared ("LORI WILL NOW ASK ABOUT: Earliest Years — Birth, first
   home, parents and siblings, the places that shaped early childhood.")
   Clicked Continue.
4. Era confirmed: `state.session.currentEra = "earliest_years"`,
   `activeFocusEra = "earliest_years"`, Earliest Years button green-
   highlighted on Life Map. Header reads "Active Focus: Earliest Years".
5. Auto-warm-prompt fired from `_lvInterviewSelectEra` → produced
   bubble 2 (Spanish-misfire, see Bug below).
6. Lori auto-emitted a second short bubble (3) — "Take your time,
   John." — consistent with the WO-10C / silence-ladder behavior
   (idle cue when narrator hasn't spoken). NOT a stub-collapse —
   see "False alarm" below.
7. Operator-agent attempted to paste the Era 1 prompt via setting
   `#chatInput.value` (731 chars) and clicking Send at screen
   coordinate (877, 879). **Send click did not dispatch** — the
   coordinate landed below the actual `#lv80SendBtn` button center
   (895, 847). Textarea retained the 731-char prompt; no user bubble
   rendered.
8. Operator-agent decided to stop, file the one real bug, and
   document the false alarm.

## Bubbles captured

```
[0] bubble bubble-ai
    Lori: Hi John, I'm Lori. I'm here to help you capture your life
    story — the memories, the people, the places that mattered to
    you. There's no wrong way to do this. We can go in order of your
    life, or jump around to whatever you want to talk about today.
    What would you like to start with?

[1] bubble bubble-sys
    💡 Camera is on — tap the microphone button when you're ready to
    talk.

[2] bubble bubble-ai      ← THE BUG
    Lori: Let me say that in English. What would you like to tell me
    next?

[3] bubble bubble-ai      ← false alarm — this is WO-10C silence cue
    Lori: Take your time, John.
```

No user bubbles rendered because the Send click missed the button.

## Post-run API readback (PASS — no data corruption)

```
GET /api/bio-builder/questionnaire?person_id=d11572d4-...
→ source: bio_facts_merged                ✓
→ personal.fullName: John Baldy           ✓ (unchanged)
→ personal.dateOfBirth: 1960-12-31        ✓ (unchanged)
→ personal.placeOfBirth: west St. Paul Minnestota   ✓
→ military.served: false                  ✓ (critical guard held)
```

John's identity stayed intact across the partial harness run. The era
click + auto-warm-prompt did not write garbage to any protected field
on the people/profile/bio_facts side.

## The real bug

**`BUG-LORI-SPANISH-MISFIRE-ENGLISH-SESSION-01`** — see spec at repo
root.

Lori emitted "Let me say that in English. What would you like to tell
me next?" on bubble 2, immediately after the Earliest Years era click,
on a session where:

- Narrator is John Baldy, an English-language profile
- No Spanish content in narrator turns (narrator had not spoken yet)
- No Spanish content in profile_seed or projection
- All identity fields are English-text

The 2026-05-07 multilingual lane wired `looks_spanish()` detection
into `compose_memory_echo` and the chat WS path. The detector appears
to be firing a false-positive on the era-auto-warm-prompt's system
input, causing Lori to start in Spanish, course-correct mid-sentence
back to English, and effectively skip the warm-question content.

This is exactly the failure mode the 2026-05-04 listener-arc work was
supposed to prevent.

## False alarm

When the operator-agent first saw "Take your time, John." right after
the era click, the read was "Lori stub-collapsed on a substantive
operator prompt — BUG-LORI-RESPONSE-STUB-COLLAPSE-01 class." Closer
inspection of the textarea state (still holding the 731-char prompt
verbatim) and the bubble structure (no user bubble exists) proved
the prompt was never actually sent. "Take your time, John." is
consistent with the WO-10C / WO-10B silence-ladder cue Lori emits
when the narrator hasn't spoken yet after a deliberate handoff (the
era click). That's expected behavior, not a stub.

Two takeaways for harness future-proofing:

1. **Do not click Send by screen coordinate.** Use
   `window.sendUserMessage()` or
   `document.getElementById('lv80SendBtn').click()` to dispatch
   reliably. Send button center moves around as the viewport changes.
2. **Diagnose before filing.** The "stub" diagnosis was based on a
   bubble that was actually a normal silence cue. Verify the user
   bubble exists in the transcript before concluding Lori
   stub-collapsed.

## Harness items not exercised

These were on the harness plan but not run because of the early stop:

- Era 2 Early School Years (military-school-as-education guard test)
- Era 3 Adolescence
- Era 4 Coming of Age
- Era 5 Building Years
- Era 6 Later Years
- Era 7 Today
- Final Life Map synthesis
- Final checklist (red-flag verification)

The `military.served=false` guard was confirmed via the post-run API
curl, independent of whether Era 2 ran. The military-school-as-
education guard test still wants to run when Lori is actually
emitting full era responses again.

## Next session pickup

1. Land the Spanish-misfire fix (see bug spec for proposed gating)
2. Re-run the harness end-to-end with the fix
3. Use `sendUserMessage()` for prompt dispatch instead of coordinate
   clicks
4. Verify all 7 eras + final synthesis
5. Verify all 12 red-flag items from the harness checklist
