# BUG-LORI-SPANISH-MISFIRE-ENGLISH-SESSION-01

**Status:** OPEN — observed 2026-06-17
**Severity:** MEDIUM (narrator-visible artifact, breaks first-turn
warmth; not data-corrupting)
**Narrator generality:** UNIVERSAL — affects any English-only narrator
when the multilingual lane misclassifies an LLM input as Spanish

## Reproduction

1. Create a fresh English-only narrator. Tested with John Baldy
   (`d11572d4-57a1-4100-8426-cfd7293a7441`), but the failure mode is
   not John-specific.
2. Operator clicks `Start Narrator Session` from the Operator tab.
3. Lori's warm opener fires normally. Narrator has not spoken yet.
4. Operator clicks a Life Map era button (tested: "Earliest Years").
   The era-confirm popover appears; operator clicks Continue.
5. `_lvInterviewSelectEra` fires `sendSystemPrompt(...)` to produce
   the auto-warm-prompt for the selected era.
6. **Observed:** Lori's next bubble reads:

   > *"Let me say that in English. What would you like to tell me
   > next?"*

7. **Expected:** A warm oral-history-shaped question about earliest
   memories, anchored to John's seeded `personal.placeOfBirth = "west
   St. Paul Minnestota"`, e.g. *"Take me back to West St. Paul — what
   are the earliest things you remember about that place?"*

## Diagnosis sketch

The 2026-05-07 multilingual lane wired `looks_spanish()` (in
`server/code/api/services/lori_spanish_guard.py` or similar) into:

- `compose_memory_echo` Spanish locale pack (Phase 1 landing)
- `compose_correction_ack` Spanish branch (Phase 5E)
- `chat_ws.py` memory_echo call site, target_language detection

Mary's Spanish-session 2026-05-09 verify confirmed the detector
works on real Spanish narrator turns. The failure mode here is the
detector firing on the SYSTEM-side era-warm-prompt input rather than
the narrator's own text.

Likely culprits to grep, in order:

1. The `_NARRATIVE_FIELD_FEWSHOTS` / Spanish fewshots accidentally
   priming an English LLM response with Spanish text when the
   composer is dispatched for an era-walk turn (`turn_mode` is
   not `memory_echo` for this path).
2. `looks_spanish()` being applied to non-narrator strings (the era
   directive's "Earliest Years — Birth, first home, parents and
   siblings, the places that shaped early childhood." string contains
   tokens like "first home" that may falsely tokenize as Spanish
   under a permissive detector).
3. The 2026-05-08 Kokoro TTS lang sniff in `app.js` (`_lvSniffTtsLang`)
   could have set `_ttsCurrentLang = "es"` on a prior input and not
   reset on language flip back to English, but that's TTS-side, not
   LLM-content-side — would produce wrong-voice audio, not
   English-content-with-Spanish-flavor.

Most likely #1 or #2 based on the LLM emitting an English-language
correction phrase ("Let me say that in English") — that's the model
mid-stream noticing it started in Spanish and pivoting.

## Why this matters

CLAUDE.md design principle 7: *"Mechanical truth must visibly project."*
The era-walk grounding work (Lori speaks the seeded place name,
asks the narrator about it) assumes Lori actually emits a coherent
warm prompt. When the multilingual misfire intercepts, Lori loses the
seeded grounding AND the era's warm content in a single turn.
That's load-bearing for the parent-session readiness work.

CLAUDE.md design principle 6 corollary: *"Lori does not pretend not
to hear."* The current artifact — meta-commentary about Lori's own
language choice — is exactly the kind of mechanical-stage-direction
output the principle forbids.

## Evidence

`docs/reports/john_baldy_era_harness_2026-06-17.md` — full bubble
capture, pre/post API readback, session state.

Live bubble text verbatim:

```
[bubble bubble-ai] Lori: Let me say that in English. What would
                        you like to tell me next?
```

This was bubble index 2 in the chat transcript, immediately following
Lori's clean warm opener (bubble 0) and the system "camera on" hint
(bubble 1). No narrator input had been issued yet — confirming the
trigger source is the era-auto-warm-prompt system input, not any
Spanish content from the narrator.

## Proposed gating

Two-layer fix:

### Layer 1 — narrator-text-only gate on `looks_spanish()`

The detector should fire ONLY against text the narrator authored
(narrator turn content), never against:

- System composer prompts
- Era directive strings
- Profile-seed values used in directive context
- Internal LLM scaffolding tokens

Find every `looks_spanish(...)` call site and audit what string is
being passed. Anything that isn't `user_text` from a chat turn should
be gated off.

### Layer 2 — single-direction language lock during era-walk turns

When `state.session.currentEra` is set AND the composer is
dispatching an era-warm-prompt directive, force
`target_language = "en"` (or the narrator's profile-declared
language, defaulting to `en`) regardless of what `looks_spanish()`
would return. The era-walk path is operator-driven, not
narrator-driven, so language detection has no signal to work with.

### Layer 3 (optional) — runtime guard

Post-LLM regex check: if Lori's emitted text starts with English
correction phrases ("Let me say that in English", "In English",
"Sorry, in English"), strip the prefix and re-issue the substantive
content. Belt-and-suspenders only.

## Acceptance gates

1. Replay the harness with the same John Baldy profile. Click
   Earliest Years. The auto-warm-prompt produces a warm English
   question that references the seeded `west St. Paul Minnestota`.
2. No "Let me say that in English" / "In English" / "Sorry, in
   English" prefixes appear in Lori's output for any English-only
   narrator across all 7 era clicks.
3. Mary's Spanish session (2026-05-09 regression case) still works
   correctly — `looks_spanish()` still fires for narrator-authored
   Spanish content, `compose_memory_echo` still emits Spanish
   readback when narrator language is Spanish.
4. All existing multilingual tests (114-case master pack, code-
   switching eval pack `sd_044`-`sd_065`, cultural-humility eval pack)
   still pass.

## Files likely touched (estimate, audit will refine)

- `server/code/api/prompt_composer.py` — `looks_spanish()` call sites
  in `compose_memory_echo` and any era-walk composer
- `server/code/api/services/lori_spanish_guard.py` (or wherever
  `looks_spanish` lives)
- `server/code/api/routers/chat_ws.py` — target_language detection
  at composer dispatch
- `tests/test_compose_memory_echo_spanish.py` — add regression case
  for English-only narrator with English era directive

## Related lanes

- 2026-05-07 multilingual Phase 1+5 — original Spanish locale work
- 2026-05-08 Kokoro TTS engine swap — `_lvSniffTtsLang` FE-side
  language detection (separate layer, not implicated here)
- 2026-05-09 Mary's session triage — original landing for
  `looks_spanish` confidence floor work
- 2026-05-03 listener-arc polish — ERA EXPLAINER + REFRAME RULE +
  GROUNDING RULE in `prompt_composer.py`; the era-walk path that
  misfired here should be using these blocks
