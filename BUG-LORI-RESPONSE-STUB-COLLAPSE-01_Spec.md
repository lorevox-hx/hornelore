# BUG-LORI-RESPONSE-STUB-COLLAPSE-01

**Status:** ACTIVE (active rewrite of pre-pivot spec)
**Severity:** MEDIUM (intermittent narrator-experience failure; high-visibility when it fires)
**Origin:** Mary's session 2026-05-09 (original detection-only Step 6 in `lori_communication_control.py`) + 2026-06-24 Spring 2026 trip canary T6 (live recurrence)
**Pre-pivot reference:** `docs/archive/workorders-pre-pivot/BUG-LORI-RESPONSE-STUB-COLLAPSE-01_Spec.md`
**Depends on:** none
**Blocks:** `WO-TRIP-IMPORT-AND-CLUSTER-01`, `WO-TRIP-TAB-DB-01`
**Locked principle:** Lori never returns a one-word or fragment reply on a substantive narrator memory turn. A real narrator deserves a real response, not "Roman." / "AI." / "Spokane." — even if her composer or shaper truncated her intended response somewhere upstream.

---

## Why this bug exists

Mary's 2026-05-09 session surfaced two literal evidence cases:

```text
Mary: "what is an AI?"
Lori: "AI."

Mary: "what is an AI?"  (re-asked)
Lori: "AI."  (byte-identical)
```

BUG-LORI-IDENTITY-META-QUESTION-DETERMINISTIC-ROUTE-01 (landed 2026-05-09) closes the specific Mary class via deterministic meta-question intercept. Step 6 in `lori_communication_control.py` added operator-visible detection — `response_stub_collapse` failure appended when final response is ≤ 3 words AND narrator's input was substantive (≥ 4 words AND not safety-triggered).

**The 2026-06-24 Spring 2026 trip canary T6 turn proves the class is still live:**

```text
T6 narrator (35 words, factual chain + meta-feedback):
  "No, not the atmosphere — what mattered was the thread across
   the trip. We saw the Roman amphitheater at Pula, then the
   Scrovegni frescoes at Padua, then the medieval walls at
   Cittadella. Those three connect."

T6 Lori:
  "Roman."
```

That's a substantive narrator memory turn — three concrete factual anchors, clear thematic thread, explicit meta-feedback rejecting sensory probes — and Lori returned ONE WORD.

Step 6 detection caught it (Bug Panel would flag `response_stub_collapse`), but DETECTION-ONLY isn't enough. The narrator received "Roman." and has no idea what happened.

---

## Goal

When a substantive narrator turn (≥ 4 words, not safety-triggered) produces a Lori reply ≤ 3 words, the response pipeline MUST:

1. Detect the stub-collapse (already done — Step 6 in `lori_communication_control.py`)
2. **Substitute a meaningful continuation that uses the narrator's anchors**, OR retry the LLM call with explicit anti-truncation guidance

Acceptable substitution shapes (one only; pick by chain detection state):

- **Factual-chain narrator turn**: chain-aware English continuation referencing ≥ 2 detected anchors
- **Memoir-grade narrator turn**: anchor-shaped reflection using `extract_safe_anchors` from `lori_structured_narrative_fallback`
- **Generic narrator turn**: "Tell me more about that. What's standing out for you in this memory?"

Unacceptable shapes (do NOT use):

- The Sorry — let's continue boilerplate (banned by 2026-06-24 product call)
- A second stub ("OK." / "Yes.")
- A meta-explanation ("I noticed my response was short — would you like me to try again?") — leaks operator-side state

---

## Non-goals

This bug does NOT:

- Change the meta-question deterministic intercept (BUG-LORI-IDENTITY-META-QUESTION-DETERMINISTIC-ROUTE-01 is the right lane for those).
- Add a "regenerate the LLM call" retry loop (out of scope — too risky without throughput evidence; revisit if substitution proves insufficient).
- Touch the response-cap headroom logic (different lane).
- Modify the existing detection in `lori_communication_control.py` Step 6 beyond hooking the substitution path into it.

---

## Implementation strategy

Phase 1 — **substitution path** in `lori_communication_control.py`:

When Step 6 detects `response_stub_collapse`, instead of just appending the warning, replace `final_text` with a substitution that uses the narrator turn's detected anchors. Inputs available in the same scope:

- `user_text` — narrator turn
- `_chain_ctx` — factual_chain_capture output for the narrator turn (if active)
- `extract_safe_anchors` — anchor extraction helper from `lori_structured_narrative_fallback`

Substitution decision tree:

```text
if _chain_ctx and _chain_ctx.is_factual_chain:
    use chain-aware substitution with chain_anchors
elif extract_safe_anchors(user_text) returns ≥ 2 anchors:
    use anchor-shaped reflection
else:
    use generic "Tell me more about that" continuation
```

Phase 2 — **harness verification**: extend Harness B T6 acceptance to assert reply has ≥ 5 words AND ≥ 2 anchors echoed. The existing G1 row already catches some of this; add a new G4 row specifically for stub-collapse: `lori_reply_not_stub_collapse` → fails when reply ≤ 3 words on substantive narrator input.

---

## Acceptance criteria

The bug is closed when:

```text
1. scripts/run_trip_route_canary_harness.py T6 returns:
   - Lori reply has ≥ 5 words
   - ≥ 2 of {Pula, Padua, Cittadella, Roman, Scrovegni} echoed
   - No emotion vocab (existing M2 row)
   - English only (G3 row)

2. scripts/run_factual_chain_live_harness.py T1-T6 each:
   - Lori reply has ≥ 5 words on substantive narrator turns
   - No regression on the existing 46/49 GREEN baseline

3. Mary's K1/K2/K10 verbatim turns (re-replayed via canary harness):
   - Lori "AI." class — caught by deterministic meta-question intercept
     OR the new substitution path; no bare "AI." reaches narrator

4. Operator-visible warning still fires on the Bug Panel
   (substitution does NOT silence the operator surface)
```

---

## Stop conditions

Stop and reassess if:

- Substitution starts replacing legitimate short responses ("Yes." in answer to a yes/no narrator question).
- Boris quality suite regresses on legitimate-short-reply cases.
- Substitution loops the LLM call (was explicitly out of scope; if Phase 1 isn't enough, escalate to Phase 2 retry path).
- The substitution shape leaks operator-side state to narrator.

---

## Files likely to touch

```text
server/code/api/services/lori_communication_control.py    — Step 6 substitution
server/code/api/services/lori_structured_narrative_fallback.py
                                                          — anchor extraction helper
scripts/run_trip_route_canary_harness.py                  — add G4 stub-collapse row
scripts/run_factual_chain_live_harness.py                 — add G4 stub-collapse row
tests/test_lori_communication_control.py                  — extend StubCollapseDetectionTest
```

---

## Revision history

- 2026-05-09 — Pre-pivot spec created from Mary "AI." evidence; detection-only Step 6 landed.
- 2026-06-24 — Active rewrite: trip canary T6 "Roman." proves detection-only is insufficient; substitution path added as Phase 1.
