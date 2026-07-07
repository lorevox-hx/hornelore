# BUG-LORI-META-PREAMBLE-LEAK-01

**Filed:** 2026-07-07 (live Travels-shelf test, Claude-in-Chrome).
**Severity:** P2 — narrator-visible system tone (design principle 3: no system-tone outputs).
**Lane:** Lori response guards (`lori_response_guards.py` / `lori_communication_control.py`).

## Live evidence

Trip-open deterministic prompt for "Spring 2026 Central Europe & Northern Italy" produced this narrator-visible reply:

> Here is the response in the requested format: "Prague and Salzburg stand out from that spring trip to Central Europe and Northern Italy. What comes to mind as you look back on those travels?"

The LLM leaked instruction-following meta-framing ("Here is the response in the requested format:") plus wrapping quotes. api.log shows comm_control ran **validate-only** on that turn (failures: atomicity=hidden_second_target, reflection=echo_not_grounded) and passed the text through.

## Fix sketch

Deterministic post-LLM repair (locked principle: runtime shaping, not prompt paragraphs): strip leading meta-preamble patterns — `^\s*(?:Here(?:'s| is) (?:the|a|your|my) (?:response|reply|answer|question)[^:"]*:)\s*` and close cousins ("Sure, here's…", "As requested…", Spanish equivalents) — then unwrap a full-message quote pair when the preamble was stripped. Belongs beside the existing perspective/fragment/phantom-noun guards so bubble/TTS/archive all see the repaired final_text. Regression fixture = the verbatim live line above.

## Acceptance

- Live line repairs to: `Prague and Salzburg stand out from that spring trip to Central Europe and Northern Italy. What comes to mind as you look back on those travels?`
- Legitimate narrator-facing quotes (Lori quoting the narrator's own words mid-sentence) unaffected.
- Guard fires log marker `[lori][meta-preamble-strip]`.
