# BUG-LORI-DEEP-EUROPEAN-ROUTE-LANGUAGE-DRIFT-01

**Status:** ACTIVE / NEXT
**Severity:** HIGH (Trip Tab readiness blocker)
**Origin:** 2026-06-24 Spring 2026 Central Europe trip canary
**Depends on:** none
**Blocks:** `WO-TRIP-IMPORT-AND-CLUSTER-01`, `WO-TRIP-TAB-DB-01`
**Locked principle:** Narrator chat is English-first. Foreign place names, European routes, food terms, and accented words in an English narrator turn do NOT imply a language change. Lori must respond in English unless the narrator explicitly asks for translation of a specific word.

---

## Why this bug exists

Spring 2026 trip-route canary (`scripts/run_trip_route_canary_harness.py`) exposed that Llama-3.1-8B pattern-completes into Spanish on long European place-name pile-ups. The first ENGLISH_FIRST_RULE prompt-directive iteration (2026-06-24) reduced the drift surface — most trip turns now stay English — but **deep European routes (8+ cities in one turn) AND pure-sensory turns about European places** still drift, requiring the chain-aware repair to fire.

Without this fix, the Trip Tab feature would inherit a conversation layer that switches Lori to Spanish whenever a narrator describes a long European itinerary. The chain-aware repair fallback is substantive but it's still a deterministic substitute — Lori is not actually composing a response, the safety net is.

---

## Canonical evidence

2026-06-24 trip-route canary run (post English-first iteration 2):

```text
T1 narrator (40 words, 8 European places):
  "On the outbound, we flew into Prague, then drove to Salzburg,
   then Graz, then crossed into Slovenia at Ljubljana, then down
   to Pula on the Istrian coast, then over to Muggia and Trieste,
   and finally settled outside Venice at Mirano."

T1 Lori (drift-repair fired):
  "Let's stay with that in English — you were telling me about
   Prague, Salzburg, and Graz. What happened next?"
```

```text
T4 narrator (sensory setup, ungraded, Venice balcony):
  "We stood on a balcony in Venice at sunset. The lagoon was glassy
   and the bells were ringing across the water."

T4 Lori (drift-repair fired):
  "Let's stay with that in English — you were telling me about Venice.
   What happened next?"
```

Drift-repair firing on T1+T4 means the LLM produced Spanish output despite the ENGLISH_FIRST_RULE directive. T2/T3/T5 stayed English with no drift, confirming the directive partially works — but not on long routes (T1) or pure-sensory turns (T4).

Earlier evidence (pre-iteration-2): every trip turn drifted to fully Spanish replies (full text logged at 2026-06-24 20:09 harness run). The iteration-2 repair caught those; this BUG is about preventing them at generation time so the safety net rarely fires.

---

## Goal

Lori stays in English on European trip narration. The chain-aware drift-repair fallback should be a SAFETY NET that rarely fires, not the primary response path for deep routes.

When the narrator's last turn is in English and contains:

- Multi-city European travel sequences (≥ 3 European place names)
- Accented or foreign words (Cittadella, Padova, Ljubljana, Trieste)
- European food / cultural terms (gelato, prosciutto, fresco)
- Sensory descriptions of European places (Venice balcony, Italian sunset)

Lori must respond in English with:

1. ≥ 2 narrator anchors echoed
2. A next-link factual question OR an English memoir-grade follow-up
3. No Spanish/Italian/French vocabulary
4. The drift-repair safety net does NOT fire

---

## Non-goals

This bug does NOT:

- Re-enable the destructive `"Sorry — let's continue"` boilerplate.
- Disable LANGUAGE MIRRORING for genuine Spanish narrators.
- Block Lori from explaining or translating a SPECIFIC word when the narrator explicitly asks ("what does Trieste mean?").
- Touch the Trip Tab feature itself (still parked behind `WO-TRIP-IMPORT-AND-CLUSTER-01`).

---

## Implementation strategy (candidates — not locked)

Three plausible paths to evaluate in this WO:

### Path A — Strengthen ENGLISH_FIRST_RULE with fewshots

Add 3-4 narrator/Lori exemplar pairs to the prompt directive showing the exact desired behavior on long European routes + sensory European turns. Cost: prompt-side only, no extractor/composer code changes. Risk: prompt-bloat.

### Path B — Restate the rule mid-prompt

Reinforce the directive late in the prompt (after per-pass/per-era blocks) when the narrator turn contains ≥ 3 detected proper nouns. Cost: small composer change. Risk: per-turn prompt size grows.

### Path C — Anti-pattern-completion fewshots in the LLM call

Inject 1-2 explicit "narrator in English about European route → Lori in English" examples directly above the user message in the chat completion call. Cost: chat path change. Risk: throws off other turn types.

Pick after running the trip canary with each option on the same conversation seed (deterministic via fixed temperature).

---

## Acceptance criteria

The bug is closed when `scripts/run_trip_route_canary_harness.py` reports:

```text
GREEN factual_chain_live  (≥ 47/49)

Verdict-level hard clamps:
  G2_not_drift_repair_boilerplate: ZERO firings across 5 graded turns
  G3_lori_reply_is_english:        100% pass across 5 graded turns

Per-turn shape:
  T1 outbound:        anchor_echo ≥ 3 of {Prague, Salzburg, Graz, Ljubljana,
                      Pula, Muggia, Trieste, Mirano, Venice}; English; no
                      drift-repair; next-link factual question
  T2 Mirano hub:      anchor_echo ≥ 2 of {Mirano, Treviso, Padua, Cittadella,
                      Chioggia, Mira, Venice}; English; no drift-repair
  T3 Pula hub:        anchor_echo ≥ 2 of {Pula, Medulin, Rovinj, Istrian}; English
  T5 return:          anchor_echo ≥ 3 of {Venice, Dulles, Denver, Santa Fe}; English
  T6 meta-feedback:   anchor_echo ≥ 2 of {Pula, Padua, Cittadella}; English;
                      no emotion pivot
```

Plus regression check — `scripts/run_factual_chain_live_harness.py` must stay GREEN and Boris quality suite (if available) must show no regression on existing narrator-tab behavior.

---

## Stop conditions

Stop and reassess if:

- Spanish narrators stop receiving Spanish replies (LANGUAGE MIRRORING broken).
- Lori starts refusing to translate a specific word when explicitly asked.
- Boris quality suite regresses.
- Prompt size grows past a level the LLM truncates on long turns.
- The fix requires SPANTAG / NARRATIVE / BINDING re-enablement (out of scope).

---

## Files likely to touch

```text
server/code/api/prompt_composer.py            — ENGLISH_FIRST_RULE block
server/code/api/services/lori_response_guards.py  — possibly tighten _looks_spanish
server/code/api/routers/chat_ws.py            — only if Path B/C wiring needed
scripts/run_trip_route_canary_harness.py      — acceptance verification
```

Do NOT modify `factual_chain_capture.py` (orthogonal lane).

---

## Revision history

- 2026-06-24 — Created from Spring 2026 trip canary T1+T4 drift evidence.
