# BUG-LORI-FEWSHOT-EXEMPLAR-LEAK-01

**Status:** ACTIVE / NEXT (deferred until after stub-collapse + harness G4 ports land)
**Severity:** MEDIUM (real narrator-visible failure on certain seeds; not blocking Trip Tab work)
**Origin:** 2026-06-25 Harness A T2 — Lori emitted the Venice-balcony exemplar verbatim as her reply to a Prague/Salzburg narrator turn
**Depends on:** BUG-LORI-RESPONSE-STUB-COLLAPSE-01 (land that first — stub class affects MORE narrators more often)
**Blocks:** none (parallel polish lane)
**Locked principle:** Fewshot exemplars in the system prompt teach SHAPE, not content. Lori must never emit a "CORRECT" example verbatim as her own response. If the LLM copies the exemplar, the prompt structure failed.

---

## Why this bug exists

`WO-LORI-DEEP-EUROPEAN-ROUTE-LANGUAGE-DRIFT-01` Path A (2026-06-24) added 4 narrator/Lori exemplar pairs to the `ENGLISH_FIRST_RULE` block in `prompt_composer.py`. The exemplars carry a header that explicitly says:

> *"EXAMPLES — study the shape, do not echo verbatim:"*

Llama-3.1-8B ignored that instruction on Harness A T2 (2026-06-25 run):

```text
T2 narrator (17 words, Spring 2026 route):
  "We started in Prague, then went to Salzburg, then Ljubljana,
   then Pula, and finally into northern Italy."

T2 Lori (23 words — verbatim copy of exemplar #2):
  "Venice at sunset with the bells across the lagoon — that's a
   moment to hold onto. Who was beside you on that balcony?"
```

That's **exemplar #2 verbatim** — the "sensory European setting" CORRECT example. Lori pattern-completed by copying the most prominent positive example in the prompt instead of generating a response to the narrator's actual turn. Known fewshot failure class — model treats the most prominent positive example as something to emit, not just study.

The harness G1 row (`narrator_anchor_echo`) caught it (Lori echoed zero of Prague/Salzburg/Ljubljana/Pula), but the narrator still saw a Venice-balcony reply to a Prague/Salzburg question. **Narrator-visible failure, harness caught it partly via G1.**

---

## Goal

Lori never returns an exemplar verbatim. Specifically:

1. Lori's reply text must NEVER contain a verbatim substring of any "CORRECT" exemplar in the prompt (no 4+ consecutive words match).
2. Foreign-place narrator turns (Prague/Salzburg/etc) get responses about THOSE places, not about Venice or Mirano or whatever the prompt's first sensory example happens to use.
3. The fewshot block continues to provide directional learning (Lori stays English, echoes chain anchors, refuses sensory pivots on chain turns) — the SHAPE of the exemplars is still the teaching mechanism.

---

## Non-goals

This bug does NOT:

- Remove the ENGLISH_FIRST_RULE prompt directive (that's the right teaching mechanism; only the verbatim copy is the failure)
- Touch the chain-aware drift repair fallback in `lori_response_guards.py`
- Touch the stub-collapse substitution path (separate lane — BUG-LORI-RESPONSE-STUB-COLLAPSE-01)
- Reintroduce the destructive "Sorry — let's continue" boilerplate
- Block legitimate echoing of narrator place names (only "CORRECT EXAMPLE → Lori reply" plagiarism)

---

## Implementation strategy (candidates — pick after diagnosis pass)

### Path A — Placeholder names in the exemplars

Replace specific city/place names in the exemplars with PLACEHOLDER tokens that the LLM can't possibly emit as real content:

```text
Narrator: "We stood on a balcony in [CITY_A] at sunset. The lagoon
           was glassy and the bells were ringing across the water."
Lori (CORRECT, English): "[CITY_A] at sunset with the bells across
the lagoon — that's a moment to hold onto. Who was beside you on
that balcony?"
```

If Lori copies verbatim, the reply contains `[CITY_A]` literal which would be obviously broken — easy to detect post-LLM and either repair or alarm. Cheapest fix. Risk: LLM may not learn the place-name-echo pattern as well.

### Path B — Move exemplars to end of prompt

The current ENGLISH_FIRST_RULE block sits near the TOP of `DEFAULT_CORE`. Recent-context bias suggests the model weighs late context more heavily during generation. Moving exemplars to the very end of the system prompt (or interleaving them with the narrator turn?) may reduce the "first conspicuous positive example" pull.

Risk: late position means the directive itself (Lori MUST respond in English) is also late, weakening its effect. Test required.

### Path C — Shorten exemplars

Current exemplars are 2-3 sentences each. Shorten to single-sentence shapes:

```text
Long route, English reply, anchor echo:
  USR: "From Prague through Salzburg, Graz, and Ljubljana to Italy."
  LORI: "Prague, Salzburg, and Graz — that's a real arc. What stood
         out between Salzburg and Graz?"
```

Shorter exemplars are less attractive to copy verbatim and reduce prompt size. Risk: may be too terse to teach the right shape.

### Path D — Post-LLM detection + repair

Add a `detect_exemplar_leak()` function in `lori_response_guards.py`. When Lori's reply matches a stored exemplar phrase ≥4 consecutive words, replace the reply with the chain-aware English fallback (same path as `repair_language_drift`).

Risk: false positives if narrators legitimately discuss Venice/balcony/etc. Mitigation: only match against full sentence patterns from the exemplars, not single phrases.

### Recommended order

1. **Path A first** (placeholders) — cheapest, easiest to verify, addresses the failure structurally
2. **Path D second** (post-LLM guard) — safety net catching anything that slips through
3. Path B/C deferred unless Path A+D don't move the needle

---

## Acceptance criteria

The bug is closed when:

```text
1. Run scripts/run_factual_chain_live_harness.py 5 times with the
   same harness seed (or rotating WS conv_id). On all 5 runs:
   - T2 Lori echoes ≥2 of {Prague, Salzburg, Ljubljana, Pula} in her
     reply
   - T2 Lori never contains "Venice at sunset" / "bells across the
     lagoon" / "Who was beside you on that balcony" verbatim phrases

2. Same 5-run check on scripts/run_trip_route_canary_harness.py
   T1-T5 — exemplar-leak class doesn't fire on European narration

3. ENGLISH_FIRST_RULE prompt block still produces the desired
   English-first behavior (Spring 2026 trip canary G3 row 100%
   across all 5 graded turns)

4. compose_system_prompt size doesn't grow beyond 1.5x current
   (Path A + D combined keep size manageable)
```

---

## Stop conditions

Stop and reassess if:

- Path A placeholders cause Lori to literally emit "[CITY_A]" in a real narrator reply (placeholder leakage class)
- Path D post-LLM guard fires on legitimate Venice/balcony narrator discussions (false positives)
- Removing the exemplar pull breaks the original English-first behavior on European routes (regression on the Path A win)
- ENGLISH_FIRST_RULE block becomes large enough to push other prompt sections out of context window

---

## Files likely to touch

```text
server/code/api/prompt_composer.py
    L77-180 — ENGLISH_FIRST_RULE block. Either reshape exemplars
    (Path A/B/C) or just trim them while adding Path D.
server/code/api/services/lori_response_guards.py
    Optional Path D — detect_exemplar_leak() + repair path.
scripts/run_factual_chain_live_harness.py
    Add explicit verbatim-substring check as a new graded row.
scripts/run_trip_route_canary_harness.py
    Same verbatim-substring check.
```

---

## Revision history

- 2026-06-25 — Created from Harness A T2 evidence (Venice-balcony exemplar emitted verbatim as Lori reply to Prague/Salzburg narrator turn). Deferred behind stub-collapse + harness G4 ports.
