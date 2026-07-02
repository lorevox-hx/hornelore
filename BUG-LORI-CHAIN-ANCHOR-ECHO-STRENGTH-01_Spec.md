# BUG-LORI-CHAIN-ANCHOR-ECHO-STRENGTH-01

**Status:** LANDED 2026-07-02 (Path A directive sentence + Path B deterministic Step 6b injection in `lori_communication_control.py`, gated on is_factual_chain AND >=3 anchors AND echo<2 AND reply<=80 words; `chain_anchor_echo_injected` warning marker. Unit tests green; live-harness verification pending next stack cycle). Path A and Path B shipped together because the 2026-07-02 live run proved directive-only fixes underdeliver (T6 atmosphere pivot survived the strengthened directive).
**Severity:** LOW-MEDIUM (chain-preservation hygiene; doesn't break Lori, weakens memoir quality)
**Origin:** 2026-06-24 factual-chain live harness T3 (Venice/Dulles disruption)
**Depends on:** none
**Blocks:** `WO-TRIP-IMPORT-AND-CLUSTER-01`, `WO-TRIP-TAB-DB-01`
**Locked principle:** For route, disruption, and event-chain narration, Lori must echo ≥ 2 narrator anchors before asking the follow-up. Single-anchor echoes lose the chain shape — the narrator gave a sequence; the response must reflect the sequence, not just one stop.

---

## Why this bug exists

WO-LORI-FACTUAL-CHAIN-CAPTURE-01 Phase 2 composer directive tells Lori to reflect the chain briefly before asking the next-link factual question. In practice the LLM sometimes echoes only ONE anchor and asks a follow-up about that one stop, losing the chain shape.

Harness A T3 evidence (2026-06-24, post English-first iteration 2):

```text
T3 narrator:
  "The flight out of Venice was delayed, then we had to get through
   Dulles, then Denver, then Santa Fe."

T3 Lori:
  "Can you tell me about the airport delays and multiple stops can
   be frustrating. You mentioned getting through Dulles. How was that
   airport, do you remember, during your layover there?"

Chain anchors detected: [Venice, Dulles, Denver, Santa Fe]
Anchors echoed in reply:  [Dulles]   ← only 1 of 4
```

G1 row failed: required ≥ 2 of 4 echoed. Lori's question is reasonable in isolation (Dulles layover) but the route shape — Venice → Dulles → Denver → Santa Fe — is lost. Memoir export from this conversation later would be impoverished because the operator-side context of "this was a multi-leg return journey with a delay" isn't carried through the response.

The same class would weaken Trip Tab readiness: trip routes ARE multi-leg sequences by construction. A Lori that only echoes one leg per turn would force the operator to manually splice the route from raw narrator turns instead of letting Lori's reflections carry the structure.

---

## Goal

For factual-chain narrator turns (any of `multi_place_sequence`, `travel_leg_sequence`, `disruption_sequence`, `event_outcome_sequence`, `job_school_military_sequence`, `medical_sequence`, `family_migration_sequence`, `operator_trip_sequence`):

1. Lori's reply echoes ≥ 2 of the narrator's detected anchors as substrings
2. The first sentence of Lori's reply references the chain shape (not just a single stop)
3. The follow-up question is anchored on either the chain-as-a-whole OR a specific link in it (not a random sensory pivot)

The 2-anchor floor is the bare minimum. For long chains (≥ 5 anchors like Chris's Prague→Italy outbound), echoing 3 anchors is the preferred shape.

---

## Non-goals

This bug does NOT:

- Block legitimate one-link follow-ups when the narrator's turn has only ONE detected anchor (single-anchor turn → single-anchor echo is fine; G1 already handles this case).
- Modify the chain-detection regex set (`factual_chain_capture.py` orthogonal lane).
- Force a verbose response — "From Venice to Dulles to Santa Fe — what stopped you in Denver?" is a 12-word reply that echoes 3 anchors AND asks a single next-link question. That shape is the target.
- Change F4 sensory-pivot detection (orthogonal).

---

## Implementation strategy (candidates)

### Path A — Strengthen the Phase 2 composer directive

Current `factual_chain_capture.build_factual_chain_followup_context` produces a `composer_directive` that says "Briefly reflect the known sequence and ask for the next factual link." Tighten to: "Echo at least TWO concrete anchors from the narrator's sequence in your first sentence — e.g. 'From X to Y to Z' or 'After A, B, then C'. Then ask one factual next-link question."

Cost: directive-text-only change in `factual_chain_capture.py`. Risk: prompt-bloat.

### Path B — Post-LLM anchor-injection rewrite (parallel to reflection_shaping)

When `_chain_ctx.is_factual_chain` is True AND `anchor_echo_count(lori_reply, anchors) < 2`, prepend a deterministic "From X to Y — " phrase using the first 2 detected anchors. Run after `lori_reflection.shape_reflection` and before persist.

Cost: ~30 lines in `lori_communication_control.py`. Risk: produces wooden openings if used too aggressively; gate behind `len(anchors) >= 3` so it only fires on genuine routes.

Phase 1 = Path A first (cheap, low-risk). Phase 2 = Path B if Path A doesn't move the needle.

---

## Acceptance criteria

The bug is closed when:

```text
1. scripts/run_factual_chain_live_harness.py G1 row passes on all
   chain-typed turns (T1, T2, T3, T4, T6):
     - T3 specifically: reply echoes ≥ 2 of {Venice, Dulles, Denver,
       Santa Fe}
     - T1 Kent: ≥ 2 of {Stanley, Fargo, top score, meal tickets}
     - T2 Chris route: ≥ 2 of {Prague, Salzburg, Ljubljana, Pula, Italy}

2. scripts/run_trip_route_canary_harness.py G1 row passes on all
   trip turns:
     - T1 outbound: ≥ 3 of 8 outbound cities echoed
     - T2 Mirano: ≥ 2 of {Mirano, Treviso, Padua, Cittadella, ...}
     - T3 Pula: ≥ 2 of {Pula, Medulin, Rovinj, Istrian}
     - T5 return: ≥ 3 of {Venice, Dulles, Denver, Santa Fe}

3. No regression on existing GREEN baselines (Harness A ≥ 46/49,
   Harness B ≥ 44/49)

4. No new F4 sensory-pivot violations introduced by the anchor-echo
   strengthening
```

---

## Stop conditions

Stop and reassess if:

- The anchor-injection rewrite produces wooden / repetitive openers ("From X to Y" on every chain turn).
- Boris quality suite regresses on non-chain narrator turns.
- The directive strengthening starves the budget for the next-link question and Lori starts producing chain-echo-only replies with no question.

---

## Files likely to touch

```text
server/code/api/services/factual_chain_capture.py
    — composer_directive text (Path A)
server/code/api/services/lori_communication_control.py
    — Path B anchor-injection step (only if Path A insufficient)
scripts/run_factual_chain_live_harness.py
    — acceptance verification
scripts/run_trip_route_canary_harness.py
    — acceptance verification
```

---

## Revision history

- 2026-06-24 — Created from Harness A T3 (Venice/Dulles, 1-of-4 anchor echo).
