# WO-EVAL-MULTITURN-01 — Multi-turn eval harness for confirm-pass validation

**Author:** Claude (LOOP-01 R5.5, overnight pack, 2026-04-21)
**Status:** PARKED. Drafted as the measurement counterpart to `WO-LORI-CONFIRM-01_Spec.md`. Opens for implementation when WO-LORI-CONFIRM-01 opens (i.e. after SECTION-EFFECT Phase 3 + SPANTAG decision).
**Depends on:** (a) WO-LORI-CONFIRM-01 is scheduled or at least has a concrete pilot scope. (b) STT-LIVE-02 plumbing in-tree (landed 2026-04-20): `ExtractedItem.needs_confirmation`, `ExtractFieldsResponse.clarification_required`, `writeMode=suggest_only`. (c) The existing single-turn harness `scripts/run_question_bank_extraction_eval.py` stays as the extractor-side decision gate.
**Blocks:** WO-LORI-CONFIRM-01 cannot close with *quantitative* validation until this harness exists. WO-LORI-CONFIRM-01 can still open and pass qualitative validation without this harness — the pilot report is explicitly scoped as qualitative-only until multi-turn benchmark is available.

---

## 1. What this is and why it's parked

WO-LORI-CONFIRM-01 (parked spec, repo root) wires two interview-engine features on top of the existing extractor: a kinship-skeleton block at narrator onboarding, and a section-boundary confirm pass that converts staged `suggest_only` writes into confirmed `write`s via a short directed follow-up. Both features interact with the narrator across multiple turns.

The existing eval harness is single-turn: one `narratorReply` → one `POST /extract/fields` → one score. It cannot measure whether *the system as a whole* resolves ambiguous scalars correctly, because the confirm pass is a second exchange and the harness never reaches the second exchange.

**The problem is not just harness shape.** It is attribution:

- If we fold confirm-pass cases into the existing master eval, a case that "passes only because confirm-pass ran" looks the same as a case that "passes because the extractor got better." We lose the ability to attribute extractor regressions to the extractor.
- Therefore the confirm-pass must be measured on a **separate lane** that keeps the extractor-only baseline clean.

That lane is what this WO specs. It is **parked** because:

1. The confirm-pass itself isn't implemented yet (WO-LORI-CONFIRM-01 is the pilot, scheduled behind SECTION-EFFECT Phase 3 and SPANTAG decision).
2. Building the multi-turn harness before confirm-pass ships would bake assumptions about confirm-pass shape that might not survive implementation contact.
3. WO-LORI-CONFIRM-01 is explicitly scoped with **qualitative validation only** in v1, so the pilot can run without this harness.

What this spec does: pins down the measurement contract and the schema bump so that when the pilot turns out to need quantitative validation, we don't discover the eval design in a rush.

---

## 2. Scope

### In scope

- A **new eval lane**, not a modification of the single-turn master. Distinct script (`scripts/run_multiturn_eval.py`), distinct case file (`data/qa/multiturn_cases.json`), distinct report shape.
- A **case schema** that models a multi-turn session: a list of `(lori_prompt, narrator_reply, expected_emission_state)` triplets plus a terminal `expected_final_canon` state.
- A **simulated-narrator** contract: canned responses keyed to confirm-pass micro-flows. The harness does not call an LLM for narrator replies; that would be a moving target. Narrator replies are fixtures.
- A **canon-diff** measurement per turn and at session close: which fields landed, which stayed staged, which were skipped.
- A **pass/fail rubric** with both per-field assertions and session-level coherence checks.
- Integration with the existing scorer (`score_case`, `_confidence_stats`) where possible, so scoring conventions don't fork.

### Out of scope

- Live WebSocket simulation. The harness talks to the same `/extract/fields` endpoint plus whatever the confirm-pass endpoint is (TBD by WO-LORI-CONFIRM-01 implementation). It does not boot a UI or a browser.
- LLM-generated narrator simulation. Canned fixtures only. If we ever need LLM-simulated narrators (for coverage-stress), that's a separate WO.
- Full-session life-map stage replay. Cases sit in a single `current_era` / `current_pass` / `current_mode` triple per turn; stage transitions across turns are modeled via the case schema, not via an interview runtime.
- Replacing the single-turn master. The master stays the extractor decision gate. This is a sibling lane.

### Explicit non-goals

- Does not attempt to benchmark interview-engine UX quality (pacing, empathy, rhythm). Those are qualitative product questions, not extraction correctness.
- Does not score the confirm-pass prompts themselves (are they well-written questions). Only their *effect* on final canon.

---

## 3. Case schema

A multi-turn case is a JSON object. Schema proposal:

```json
{
  "id": "mt_case_001",
  "narratorId": "janice-josephine-horne",
  "pilot_field": "personal.birthOrder",
  "phase": "developmental_foundations",
  "description": "Narrator says 'middle of three' — extractor emits wrong canonical form; confirm-pass should resolve.",
  "initial_canon": {
    "parents.firstName": "Pete",
    "parents.relation": "father"
  },
  "turns": [
    {
      "turn_index": 0,
      "lori_prompt": "Where did you fall in your family growing up?",
      "narrator_reply": "I was the middle of three.",
      "current_section": "childhood_origins",
      "current_target_path": "personal.birthOrder",
      "current_era": "early_childhood",
      "current_pass": "pass1",
      "current_mode": "open",
      "expected_emission": {
        "writes": [],
        "staged": [
          {
            "fieldPath": "personal.birthOrder",
            "confirmation_reason": "canonical_form_ambiguous"
          }
        ]
      }
    },
    {
      "turn_index": 1,
      "lori_prompt": "So when you say middle of three — were you born second, between an older and a younger sibling?",
      "narrator_reply": "Yes, that's right. My brother Jim was older and my sister Ruthie was younger.",
      "current_section": "childhood_origins",
      "current_target_path": "personal.birthOrder",
      "current_era": "early_childhood",
      "current_pass": "pass2a",
      "current_mode": "recognition",
      "confirm_of": "personal.birthOrder",
      "expected_emission": {
        "writes": [
          {"fieldPath": "personal.birthOrder", "value": "2"}
        ],
        "bonus_writes_accepted": [
          {"fieldPath": "siblings.firstName", "value": "Jim"},
          {"fieldPath": "siblings.firstName", "value": "Ruthie"}
        ]
      }
    }
  ],
  "expected_final_canon": {
    "personal.birthOrder": "2",
    "parents.firstName": "Pete",
    "parents.relation": "father"
  },
  "expected_final_staged": [],
  "disposition": "confirm_pass_resolves"
}
```

Key schema choices:

- **`initial_canon`** — fields already written before this session starts (e.g. by the kinship-skeleton block at onboarding, or by previous turns in a larger simulated session). Lets us test "extraction against a populated canon."
- **`turns[n].confirm_of`** — optional pointer indicating this turn is a confirm-pass follow-up for a specific staged field. Lets the scorer know that this turn's `narrator_reply` is specifically answering the confirm. Harness doesn't rely on this for dispatch; the real confirm-pass dispatcher decides when to confirm. The field is scoring metadata only.
- **`expected_emission`** — per turn, what the extractor should have emitted. `writes` is the committed-list; `staged` is the `suggest_only + needs_confirmation` list. `bonus_writes_accepted` is a soft-pass set — the confirm turn may legitimately extract additional fields (Jim, Ruthie) that aren't the confirm's subject.
- **`expected_final_canon` / `expected_final_staged`** — end-of-session state. The gate.
- **`disposition`** — one of the fixed values in §4. Describes what the case is *testing*.

### Disposition vocabulary

| Value | Meaning |
|---|---|
| `confirm_pass_resolves` | Staged field gets committed via confirm. Happy path. |
| `confirm_pass_rejects` | Narrator rejects / corrects the confirm; staged field stays staged OR gets a different value. Tests the correction path. |
| `confirm_pass_skipped` | Narrator says "come back to that" or equivalent; staged stays, session continues. |
| `skeleton_only` | Tests kinship-skeleton block (multi-turn onboarding) without in-narrative confirm. |
| `skeleton_then_narrative` | Skeleton block runs, then a narrative turn re-emits something already in canon — expected behavior is `already_in_canon` no-op, not double-write. |
| `no_confirm_triggered` | Case where the extractor is confident enough (confidence ≥ 0.8) that no confirm fires; tests the guardrail against over-confirming. |

---

## 4. Harness contract

### Entry point

```
./scripts/run_multiturn_eval.py \
    --cases data/qa/multiturn_cases.json \
    --api http://localhost:8000 \
    --tag mtv01 \
    --output docs/reports/multiturn_eval_mtv01.json
```

### Per-case runtime sketch

```
For each case:
  canon = deepcopy(case.initial_canon)
  staged = []
  session_id = f"multiturn_{case.id}_{uuid}"
  for turn in case.turns:
    payload = build_payload(turn, canon, staged, session_id)
    resp = POST /extract/fields  (or /extract/confirm if turn.confirm_of present)
    observed_emission = summarize(resp)
    compare(observed_emission, turn.expected_emission)  → per-turn score
    canon = apply_writes(canon, resp.items where writeMode=write)
    staged = merge_staging(staged, resp.items where writeMode=suggest_only)
    if resp.clarification_required:
      # expected by schema; if turn.expected_emission.staged is empty and clar is
      # non-empty, that's a finding. Record.
      ...
  compare(canon, case.expected_final_canon)        → session-final canon score
  compare(staged, case.expected_final_staged)      → session-final staged score
```

### Scoring axes

Per case, emit five booleans and a score:

- `per_turn_writes_match` — for every turn, observed writes match `expected_emission.writes` exactly (fieldPath + value under fuzzy match identical to single-turn scorer).
- `per_turn_staging_match` — for every turn, observed staging (fieldPaths only — values may differ by intent) matches `expected_emission.staged`.
- `final_canon_exact` — end-of-session canon matches `expected_final_canon` exactly.
- `final_staged_exact` — end-of-session staged list matches `expected_final_staged` (useful for `confirm_pass_skipped` cases).
- `no_unexpected_clarifications` — no extra `clarification_required` envelopes beyond what the case expected.

Case passes if **final_canon_exact AND final_staged_exact AND no_unexpected_clarifications**. Per-turn asserts are diagnostic.

### Report shape

`docs/reports/multiturn_eval_<tag>.json` + `.console.txt`. Topline block:

```
Multi-turn eval <tag>
Cases total:            NN
Cases pass:             NN / NN  (XX.X%)
By disposition:
  confirm_pass_resolves:   XX / XX
  confirm_pass_rejects:    XX / XX
  confirm_pass_skipped:    XX / XX
  skeleton_only:           XX / XX
  skeleton_then_narrative: XX / XX
  no_confirm_triggered:    XX / XX
Per-axis:
  per_turn_writes_match:        XX / NN
  per_turn_staging_match:       XX / NN
  final_canon_exact:            XX / NN
  final_staged_exact:           XX / NN
  no_unexpected_clarifications: XX / NN
```

Console readout mirrors the JSON, with per-case status lines listing which axis failed.

---

## 5. Simulated-narrator contract

The `narrator_reply` field in each turn is the *canned answer*. The harness does not generate it. Why:

- LLM-simulated narrators introduce variance that swamps the mechanism under test. We'd be measuring the simulator.
- Canned answers are easy to author once per case and stay stable across eval runs.
- Real-user variation (different phrasings of "middle of three" / "I was the second kid") gets coverage by authoring multiple cases, not by stochastic sampling.

**For `confirm_pass_rejects` cases**, the canned answer for the confirm turn explicitly pushes back: `"No, actually I was the youngest"` or `"Come back to that later."` The harness does not attempt to simulate the narrator "thinking"; it plays the fixture and measures what the system does with it.

**For kinship-skeleton cases**, each step has its own `(lori_prompt, narrator_reply)` pair. The skeleton's 6 steps (mother / father / siblings / narrator-spot / spouse-maybe / children-maybe) become 6 turns in the case.

---

## 6. First target pack

The pilot field set from WO-LORI-CONFIRM-01 §Pilot scope:

- `personal.birthOrder`
- `siblings.birthOrder` (per sibling)
- `parents.relation`
- Date-range fields (`*.yearsActive`, `*.dateRange`, `*.servicePeriod`)

Per WO-LORI-CONFIRM-01 §Measurement §qualitative scope, the pilot targets 12–15 cases from the r5e1 rundown. Translate those into multi-turn cases:

| r5e1 case class | Multi-turn case count | Dispositions covered |
|---|---|---|
| Birth-order arithmetic (cases 002, 014, 024, 047) | 4 cases | `confirm_pass_resolves` × 3, `confirm_pass_rejects` × 1 |
| Sibling birth-order canonical form (cases 028, 031, 070) | 3 cases | `confirm_pass_resolves` × 2, `no_confirm_triggered` × 1 |
| Parent-relation tag drop (from FAILURE_CLUSTERS_r5e1.md Pack 2 selection) | 3 cases | `confirm_pass_resolves` × 2, `confirm_pass_skipped` × 1 |
| Date-range preference (case 023 variants, plus new synthetic) | 2 cases | `confirm_pass_resolves` × 1, `no_confirm_triggered` × 1 |
| Kinship skeleton coverage | 3 cases | `skeleton_only`, `skeleton_then_narrative`, `skeleton_only` with era gate off |

Total first pack: 15 cases. Stable fixture set, versioned in git.

---

## 7. What this WO does NOT build

- A conversational state machine that could replace the live `interview.js` runtime. Out of scope by a wide margin.
- A way to A/B confirm-pass on/off at eval time. The harness assumes confirm-pass is on (or its off-behavior is testable by just not including confirm turns in the case).
- A coverage-stress suite. First pack is 15 hand-curated cases. Scaling to hundreds of multi-turn cases needs an authoring tool that is itself a separate WO.
- Real-user replay (transcript → multi-turn case). Interesting future direction, not in this WO.
- Scoring hooks for the STT confidence / fragile-fact guard lane — those are tested separately by the existing `writeMode=suggest_only` unit tests.

---

## 8. Implementation plan (when this opens)

Four commits, each reversible.

### Commit 1 — Case schema + fixtures

- Draft `data/qa/multiturn_cases.json` with 3 hand-authored cases (one `confirm_pass_resolves`, one `skeleton_only`, one `no_confirm_triggered`).
- Write `docs/qa/multiturn_schema.md` — formal schema documentation.
- JSON-schema validation script: `scripts/validate_multiturn_cases.py` — catches malformed fixtures.

### Commit 2 — Harness skeleton

- `scripts/run_multiturn_eval.py` — entry point, argument parsing, case loading, per-turn loop, no scoring yet (just dumps raw emissions per turn).
- Smoke-test: script runs 3 fixtures clean, writes raw JSON, no crash.

### Commit 3 — Scoring + report

- Implement `score_multiturn_case(case, per_turn_emissions)` → five booleans + pass/fail.
- Wire into harness; emit JSON + console report.
- Smoke-test: 3 fixtures produce a report with expected axis pass/fails.

### Commit 4 — First target pack

- Expand fixtures to 15 cases covering the §6 distribution.
- Run end-to-end; report lands in `docs/reports/multiturn_eval_mtv01.json`.
- Decision gate per §9.

### Commit 5 (optional) — CI-eligibility polish

- Add `--fixture-smoke` mode that runs the 3-case smoke pack fast (< 30s total) for tight iteration.
- Document harness in `docs/qa/multiturn_eval.md`.

---

## 9. Decision gate (when first pack runs)

The harness itself is a measurement tool; the gate applies to *what the pack says about WO-LORI-CONFIRM-01 pilot quality*:

- **GREEN** — ≥ 12 / 15 cases pass. Confirm-pass resolves ambiguities as designed, kinship skeleton writes canon cleanly, no surprise clarifications. Pilot is validated; WO-LORI-CONFIRM-01 can move to "default-on" consideration.
- **YELLOW** — 8–11 / 15 cases pass. Pilot works but has holes. Author a short follow-up spec with per-case fixes.
- **RED** — ≤ 7 / 15 cases pass. Pilot has a systemic issue. Do not ship confirm-pass default-on; revisit WO-LORI-CONFIRM-01 design.

The harness itself does not need its own gate — its acceptance criterion is that it runs the 15 cases reproducibly and outputs a report matching §4.

---

## 10. Costs and timeline

Rough effort estimate (when implementation opens):

- Commits 1 + 2 + 3: 2 days (schema + harness + scorer, end-to-end on 3 fixtures).
- Commit 4: 1–2 days (authoring 12 additional cases, running end-to-end, writing the decision readout).
- Commit 5: 0.5 days (polish).

Total: 3.5–4.5 days of implementation work, not counting WO-LORI-CONFIRM-01's own implementation cost. This is *in addition* to the confirm-pass pilot build.

Cost argument for parking:

- WO-LORI-CONFIRM-01 §Measurement explicitly accepts qualitative validation for v1 of the pilot.
- Investing 4+ days of harness work before confirm-pass itself is built is high-risk — the case schema could need revision once the confirm-pass endpoint shape solidifies.
- If WO-LORI-CONFIRM-01 pilot qualitative validation is `go`, this WO opens and the harness work is justified.
- If WO-LORI-CONFIRM-01 pilot validation is `no-go` (e.g. SPANTAG moved the 4 pilot-field classes adequately), this WO stays parked indefinitely.

---

## 11. Risks

- **R-A (MEDIUM) — case schema rot.** WO-LORI-CONFIRM-01 implementation may surface emission shapes this spec did not anticipate. Mitigation: schema versioned (`schema_version: 1`), migration script stubbed when needed.
- **R-B (LOW) — scorer divergence.** Single-turn scorer uses fuzzy value matching; multi-turn scorer needs the same. Mitigation: import `score_field_match` from the single-turn harness, don't re-implement.
- **R-C (MEDIUM) — fixture bias.** 15 hand-authored cases can accidentally overfit to the confirm-pass's actual behavior (since the author knows what the pass does). Mitigation: author fixtures from `FAILING_CASES_r5e1_RUNDOWN.md` text, not from the confirm-pass prompts. Read the narrator reply → predict the confirm → write the fixture reply before looking at the confirm-pass's actual question bank. Author bias is a known confound; declaring it is half the mitigation.
- **R-D (LOW) — API endpoint drift.** WO-LORI-CONFIRM-01 may land with a different endpoint shape than the current `/extract/fields`. Mitigation: harness uses a wrapper `post_extraction(payload, confirm=bool)` that can switch endpoints without touching the per-case loop.

---

## 12. What this WO makes possible (once built)

- Quantitative `go/no-go` call on WO-LORI-CONFIRM-01 pilot.
- Regression coverage for the kinship-skeleton block and confirm pass — catches any extractor or interview-engine change that breaks multi-turn attribution.
- Foundation for scaling confirm-pass beyond the 4 pilot fields. New fields get new cases, scored the same way.
- Evidence base for the WO-LORI-CONFIRM-01 post-pilot decision (expand / park / roll back).

---

## 13. Related work

- `WO-LORI-CONFIRM-01_Spec.md` — the pilot this harness measures. Primary consumer.
- `scripts/run_question_bank_extraction_eval.py` — single-turn master; source of `score_field_match`, `score_case`, and the scoring conventions this harness inherits.
- `docs/reports/WO-STT-LIVE-02_REPORT.md` — plumbing for `writeMode=suggest_only` + `needs_confirmation` + `clarification_required`. This harness asserts those primitives are in-tree.
- `docs/reports/FAILING_CASES_r5e1_RUNDOWN.md` — case source for first-pack authoring.
- `docs/reports/FAILURE_CLUSTERS_r5e1.md` — Pack 1 (birth-order) and Pack 2 (attribution) are the multi-turn pilot's domain.

---

## 14. Revision history

- 2026-04-21: Drafted as parked spec. Scoped to 15-case first pack, 4 pilot fields from WO-LORI-CONFIRM-01. Implementation opens when WO-LORI-CONFIRM-01 implementation opens. Schema, harness, scoring, and decision gate all pinned.
