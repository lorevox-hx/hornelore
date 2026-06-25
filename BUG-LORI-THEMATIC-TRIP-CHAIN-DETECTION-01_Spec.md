# BUG-LORI-THEMATIC-TRIP-CHAIN-DETECTION-01

**Status:** ACTIVE / PARKED (queued behind stub-collapse + harness G4 ports + fewshot-leak)
**Severity:** LOW-MEDIUM (Lori responds well; detector misclassifies the turn class)
**Origin:** 2026-06-25 Spring 2026 trip canary T6 + 2019 France/Italy T8 — both thematic-recall narrator turns scored `is_chain=False conf=0.35` despite being clearly chain-shaped
**Depends on:** none
**Blocks:** none (response is already correct; only the detector class label is wrong)
**Locked principle:** A chain narrator turn is a chain regardless of whether the cohesion is route-shaped or thematic. The factual-chain classifier should recognize both.

---

## Why this bug exists

`factual_chain_capture.detect_factual_chain` is calibrated for ROUTE chains. Its scoring buckets fire on:

- multi_place_sequence (≥2 proper nouns + ≥1 sequence connector)
- travel_leg_sequence (travel verbs + ≥2 proper nouns)
- disruption_sequence (delay / cancellation markers)
- institution_process_result (process + outcome markers)
- event_outcome_sequence
- job_school_military_sequence / medical_sequence / family_migration_sequence
- date_place_action

It does NOT have a cue for THEMATIC recall — "the thread across the trip was X then Y then Z" style. On those turns the classifier sees:

- ≥2 proper nouns ✓
- Sequence connectors ("then" × 2) ✓
- multi_place_sequence ✓ (+ ≥3 anchors bonus ✓)
- **No travel verbs** ✗
- **No disruption** ✗
- **No outcome marker** ✗
- **No institution/process** ✗

Score: 0.20 + 0.15 = 0.35. Below the 0.50 chain floor → `is_chain=False`.

But the narrator turn IS structurally a chain. The only thing distinguishing it from a route chain is the absence of travel verbs.

---

## Canonical evidence

### Spring 2026 trip canary T6 (2026-06-25 GREEN run)

```text
Narrator: "No, not the atmosphere — what mattered was the thread
           across the trip. We saw the Roman amphitheater at Pula,
           then the Scrovegni frescoes at Padua, then the medieval
           walls at Cittadella. Those three connect."

Detector: is_chain=False  conf=0.35  cues=['multi_place_sequence']
Lori reply (correct): "Can you tell me about the Roman amphitheater,
                       the Scrovegni frescoes, and the medieval walls
                       — connecting those experiences. What did you
                       learn..."

Harness scored F1 = False (chain not classified) but Lori's response
echoes 3 anchors and asks a thoughtful follow-up. F1 is the only fail
on this turn; G1/G3/F4/M1/M2 all pass. Lori behaved RIGHT, detector
class was WRONG.
```

### 2019 France/Italy T8 (2026-06-25 RED run on stub-collapse, but T8 specifically)

```text
Narrator: "No, not the market atmosphere — the thread I want is how
           the trip moved from Paris museums to Provence history to
           Rome at the end. The Louvre, Avignon, Arles, and Rome
           connect for me."

Detector: missed
Lori reply (decent): "Can you tell me about the Louvre in Paris,
                      Avignon, Arles, and Rome - those destinations
                      seem to be connected in your memory..."
```

Same pattern: explicit "thread / connect" language + ≥3 named places + no travel verbs = misclassified.

---

## Goal

Add a `thematic_trip_chain` cue label to `factual_chain_capture.CUE_LABELS` and a corresponding scoring branch that fires when:

1. Narrator text contains a thematic-thread marker (regex below), AND
2. ≥3 distinct proper nouns appear (or ≥2 anchors with explicit sequence connectors), AND
3. Optional supporting signal: meta-feedback rejecting sensory probes (often paired)

The branch adds enough score (+0.30 - +0.40) to push `is_factual_chain` above the 0.50 floor for genuine thematic chains.

### Trigger pattern candidates

```text
THEMATIC_THREAD_RX patterns:
  - "thread across (?:the )?trip"
  - "(?:the |a )?thread (?:I want|that mattered|was)"
  - "those (?:three|four|five) connect"
  - "(?:these|those) (?:landmarks|places|stops|moments) (?:do |all )?connect"
  - "the trip moved from ?(?:[A-Z][a-z]+) ?to ?(?:[A-Z][a-z]+)"
  - "what (?:mattered|connected|tied) (?:was )?(?:the )?(?:thread|connection|link)"
  - "from (?:X) to (?:Y) to (?:Z) and (?:then |finally )?(?:W|to W)"  # generic
```

Tunable: each pattern adds +0.30 to score; ≥3 distinct proper nouns also contributes +0.15 (already exists). Together easily clears 0.50.

---

## Non-goals

This bug does NOT:

- Lower the existing 0.50 floor (would create false positives on conversational responses)
- Modify the meta-feedback detection — that's already firing correctly on these turns (M1/M2 pass)
- Add a "memoir-grade thematic question" cue type — the existing `next_factual_link` followup type still works for thematic chains
- Touch Lori's response behavior — she already handles these turns well; only the harness scoring (F1 row) gets caught misclassifying

---

## Implementation

### Phase 1 — pattern + scoring branch

In `factual_chain_capture.py`:

```python
CUE_LABELS = (
    "multi_place_sequence",
    "date_place_action",
    "event_outcome_sequence",
    "institution_process_result",
    "travel_leg_sequence",
    "disruption_sequence",
    "job_school_military_sequence",
    "medical_sequence",
    "family_migration_sequence",
    "operator_trip_sequence",
    "thematic_trip_chain",          # NEW
)

_THEMATIC_THREAD_RX = re.compile(
    r"\b(?:"
    r"thread\s+(?:across|that|of)\s+(?:the\s+)?(?:trip|journey)|"
    r"(?:those|these)\s+(?:three|four|five|landmarks|places|moments)\s+(?:do\s+|all\s+)?connect|"
    r"what\s+(?:mattered|connected)\s+(?:was\s+)?(?:the\s+)?thread|"
    r"the\s+trip\s+moved\s+from\s+\w+\s+to\s+\w+\s+to\s+\w+"
    r")\b",
    re.IGNORECASE,
)
```

In `detect_factual_chain`, after the existing branches:

```python
# Thematic trip chain — narrator naming the "thread" / "connection"
# across a multi-anchor recall. Often paired with meta-feedback
# rejecting sensory framing.
if _THEMATIC_THREAD_RX.search(text) and len(proper_anchors) >= 3:
    cue_labels.append("thematic_trip_chain")
    score += 0.35  # enough to clear 0.50 floor with the existing
                   # multi_place + 3+ anchor bonus
```

### Phase 2 — unit tests

`tests/test_factual_chain_capture.py` — add `ThematicTripChainTest` class:

- Spring 2026 T6 narrator text → `is_factual_chain=True`, `cue_labels` includes `thematic_trip_chain`
- 2019 T8 narrator text → same
- Negative control: narrator says "the trip was beautiful" (no thematic-thread marker, no chain) → `is_factual_chain=False`
- Pattern-only without anchors ("the thread of the trip was nice") → does NOT fire (needs ≥3 proper nouns)

### Phase 3 — harness verification

Re-run all 3 live harnesses after Phase 1+2 land:

- Harness B T6 F1 row should flip True (chain classification)
- 2019 T8 F1 row should flip True
- No regression on other turns

---

## Acceptance criteria

```text
1. ThematicTripChainTest unit tests all GREEN (4+ tests).

2. Re-run scripts/run_factual_chain_live_harness.py — no regression
   on 47/49 baseline.

3. Re-run scripts/run_trip_route_canary_harness.py — T6 F1 row now
   PASSes (was the lone fail in the 2026-06-25 48/49 GREEN run);
   score becomes 49/49.

4. Re-run scripts/run_trip_2019_france_italy_canary_harness.py — T8
   F1 row PASSes (was 2 of 4 T8 fails).

5. No new false positives on the existing 8 canary cases in
   scripts/run_factual_chain_capture_smoke.py.
```

---

## Stop conditions

Stop and reassess if:

- The thematic_trip_chain pattern fires on conversational narrator turns ("the conversation moved from X to Y to Z") where Lori shouldn't preserve a chain
- Score weight overshoots and turns where Lori legitimately pivots to sensory get misclassified as chains
- Pattern matches on Lori-side text inadvertently (would corrupt meta-feedback detection)

---

## Files likely to touch

```text
server/code/api/services/factual_chain_capture.py
    - CUE_LABELS tuple (add thematic_trip_chain)
    - _THEMATIC_THREAD_RX pattern
    - detect_factual_chain — thematic scoring branch
tests/test_factual_chain_capture.py
    - ThematicTripChainTest class
scripts/run_factual_chain_capture_smoke.py
    - optional: add canonical Spring 2026 T6 + 2019 T8 cases
```

No changes to chat_ws.py / prompt_composer.py / lori_communication_control.py — detection-only fix.

---

## Revision history

- 2026-06-25 — Created from Spring 2026 trip canary T6 (Lori's response was correct; F1 was the only fail) + 2019 France/Italy T8 (same misclassification). Queued behind stub-collapse + harness G4 ports + fewshot-leak — Lori's response is already correct on these turns; only the harness scoring catches the detector class miss.
