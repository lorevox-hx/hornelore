# WO-LORI-CONFIRM-01 — Prep Pack (companion to Spec)

**Author:** Claude (LOOP-01 R5.5, overnight 2026-04-21→22)
**Parent:** `WO-LORI-CONFIRM-01_Spec.md` (parked, sequenced behind SECTION-EFFECT Phase 3 + SPANTAG decision)
**Status:** PREP ARTIFACT. Everything here is draft data + pseudocode, not landed. The point is to make the moment-SPANTAG-decides-and-LORI-opens a ~2-day implementation pickup, not a weeks-long spec-hardening exercise.
**Scope:** Fills the gaps the parent spec deliberately left — concrete JSON file drafts, dispatcher pseudocode, canon-collision reconciliation algorithm, per-field decision trees tied to real r5e1 cases, SPANTAG/SECTION-EFFECT integration matrix, 15-case pilot map, pilot acceptance criteria, implementation checklist.

> **v1 SCOPE UPDATE (Chris decision, 2026-04-22 morning read):**
> Date-range is **DESCOPED from LORI v1 pilot.** v1 ships as a **3-field confirm pass** — `personal.birthOrder`, `siblings.birthOrder`, `parents.relation`.
> Rationale: the corpus audit (`docs/reports/question_bank_tagging_audit.md`) found only **one** `date_range_confirm` case (case_071), and it is already passing. One passing corpus case does not justify carrying a fourth confirmation bank into the first pilot.
> The `dateRange.json` bank draft stays parked in this pack (§2.4). Reactivation is gated on **#111 corpus expansion adding ≥2 stubborn date-range cases**; if/when those land and at least one is failing under r5e1, the bank folds back into a v1.1 pilot.
> Revised implementation cost: **~2.25 days** (was 2.75). Revised pilot sub-pack: still 15 multi-turn cases, but the 1 date-range target case (`mt_case_006` → case_079) is held back as a control for v1.1 reactivation rather than a v1 primary target. Acceptance math for v1: PRIMARY_GREEN = ≥3 of 5 primary targets improved ≥0.3 AND 0 regressed (drops from 6 targets to 5; the 6th — `mt_case_006` — is re-classed CONTROL for v1).
> Everything downstream of this banner that still references "4-field" or "date-range" is preserved verbatim for the v1.1 reactivation; §2.4 and §6 already carry explicit DESCOPED markers.

This document does not change the spec. It's a below-the-line implementation pack so when LORI opens for implementation, the author can go directly from this file to PR-ready commits without re-deriving the data contracts.

---

## 1. Kinship skeleton — `data/interview/kinship_skeleton.json` draft

Fires once per narrator at the first interview session, before the first narrative turn. The UI walks the steps sequentially. Each step is skippable. Each completed step writes canon before the next Lori prompt is selected.

```json
{
  "version": "v1-pilot-4field",
  "block_id": "kinship_skeleton_v1",
  "fire_condition": "narrator.onboarding_complete == false AND canon.parents.firstName == []",
  "skip_phrases": [
    "i'd rather get to the stories",
    "skip this",
    "can we move on",
    "not right now"
  ],
  "max_total_duration_s": 180,
  "steps": [
    {
      "step_id": "kin_01_mother",
      "prompt": "Let's start with your family. What was your mother's name?",
      "skip_ok": true,
      "capture": {
        "pattern": "firstname_optional_middle_lastname",
        "writes": [
          {"path": "parents.firstName", "from": "firstname", "writeMode": "write"},
          {"path": "parents.relation", "value": "mother", "writeMode": "write"}
        ]
      },
      "followups": {
        "if_maiden_name_mentioned": {
          "path": "parents.maidenName",
          "writeMode": "write"
        }
      }
    },
    {
      "step_id": "kin_02_father",
      "prompt": "And your father's name?",
      "skip_ok": true,
      "capture": {
        "pattern": "firstname_optional_middle_lastname",
        "writes": [
          {"path": "parents.firstName", "from": "firstname", "writeMode": "write", "index": "auto"},
          {"path": "parents.relation", "value": "father", "writeMode": "write", "index": "auto"}
        ]
      }
    },
    {
      "step_id": "kin_03_siblings_presence",
      "prompt": "Did you have any brothers or sisters growing up?",
      "skip_ok": true,
      "branch": {
        "yes": "kin_03a_siblings_roster",
        "no": "kin_04_narrator_order_solo"
      }
    },
    {
      "step_id": "kin_03a_siblings_roster",
      "prompt": "Tell me their names and whether they were older or younger than you.",
      "skip_ok": true,
      "capture": {
        "pattern": "roster_with_order_tokens",
        "order_tokens": {"older": "older", "younger": "younger", "big": "older", "little": "younger", "oldest": "older", "youngest": "younger"},
        "writes_per_entry": [
          {"path": "siblings.firstName", "from": "firstname", "writeMode": "write"},
          {"path": "siblings.relation", "from": "inferred_gender_or_brother_sister", "writeMode": "suggest_only", "needs_confirmation": true, "confirmation_reason": "gender_not_explicit_in_reply"},
          {"path": "siblings.birthOrder", "from": "order_token", "writeMode": "write"}
        ]
      },
      "confirm_inline": {
        "when": "relation emitted with confidence < 1.0",
        "prompt": "And {firstname} — brother or sister?",
        "writes": [{"path": "siblings.relation", "writeMode": "write"}]
      }
    },
    {
      "step_id": "kin_04_narrator_order_solo",
      "prompt": "And where did you fall — oldest, youngest, or somewhere in between?",
      "fire_when": "kin_03_siblings_presence.answer == no",
      "capture": {
        "writes": [{"path": "personal.birthOrder", "value": "1", "writeMode": "write"}]
      }
    },
    {
      "step_id": "kin_04_narrator_order",
      "prompt": "And where were you in that lineup?",
      "fire_when": "kin_03_siblings_presence.answer == yes AND kin_03a_siblings_roster.completed",
      "capture": {
        "pattern": "order_phrase_to_integer",
        "mapping": {
          "oldest": "1", "first": "1", "the oldest": "1",
          "middle": "compute_from_sibling_count",
          "youngest": "compute_from_sibling_count",
          "second": "2", "third": "3", "fourth": "4"
        },
        "compute_from_sibling_count": {
          "youngest": "sibling_count + 1",
          "middle_of_three": "2",
          "middle_of_five": "3"
        },
        "writes": [{"path": "personal.birthOrder", "writeMode": "write"}]
      }
    },
    {
      "step_id": "kin_05_spouse_gate",
      "prompt": "Are you or were you ever married?",
      "fire_when": "life_map.current_era in [early_adulthood, midlife, later_life]",
      "skip_ok": true,
      "branch": {
        "yes": "kin_05a_spouse_name",
        "no": "kin_06_children_gate"
      }
    },
    {
      "step_id": "kin_05a_spouse_name",
      "prompt": "What's their name?",
      "capture": {
        "writes": [
          {"path": "family.spouse.firstName", "from": "firstname", "writeMode": "write"},
          {"path": "family.spouse.maidenName", "from": "if_offered", "writeMode": "write"}
        ]
      }
    },
    {
      "step_id": "kin_06_children_gate",
      "prompt": "Do you have children?",
      "fire_when": "life_map.current_era in [early_adulthood, midlife, later_life]",
      "skip_ok": true,
      "branch": {
        "yes": "kin_06a_children_count",
        "no": "block_complete"
      }
    },
    {
      "step_id": "kin_06a_children_count",
      "prompt": "How many?",
      "capture": {
        "writes": [{"path": "family.children.count", "from": "integer", "writeMode": "write"}]
      },
      "followup_if_count_le_4": "kin_06b_children_names"
    },
    {
      "step_id": "kin_06b_children_names",
      "prompt": "What are their names?",
      "capture": {
        "pattern": "firstname_list",
        "writes_per_entry": [{"path": "family.children.firstName", "from": "firstname", "writeMode": "write"}]
      }
    }
  ],
  "on_complete": {
    "writes": [{"path": "narrator.onboarding_complete", "value": true}]
  }
}
```

**Design notes:**

- **Relation tags write deterministically.** `kin_01_mother` writes `parents.relation='mother'` as a canon fact, not as an extracted inference. This is the whole point of the skeleton: relation tags stop being a noisy extraction field and become pre-established canon. Case_002 (missing `parents.relation='mother'`) stops being a failure mode.
- **`siblings.relation` is the one skeleton field that can't be deterministic.** If narrator says "Vincent and Jason and Linda", we don't know Linda is a sister from name alone. The nested inline confirm (`kin_03a_siblings_roster.confirm_inline`) resolves it in one question per sibling. This is an inner confirm-pass, not a full mid-interview confirm-pass.
- **Birth-order arithmetic lands in `kin_04`.** The compute_from_sibling_count table resolves "middle of three → 2", "youngest of three → 3", which is the cluster-1 failure mode for case_002/014/024.
- **Era gating.** Spouse/children steps fire only if `life_map.current_era ∈ {early_adulthood, midlife, later_life}`. A narrator interviewed with `current_era=school_years` (memoir focus) won't get spouse-block interruptions.

## 2. Confirmation banks — `data/interview/confirmation_banks/*.json` drafts

### 2.1 `birthOrder.json` — `personal.birthOrder` confirm

Fires when the narrative pass stages `personal.birthOrder` as `suggest_only` (typically because narrator said "middle child" but sibling count is ambiguous).

```json
{
  "version": "v1-pilot",
  "field_path": "personal.birthOrder",
  "fire_conditions": [
    "staged writeMode == suggest_only",
    "staged confidence < 0.8",
    "canon.personal.birthOrder == null"
  ],
  "micro_flow": [
    {
      "step": "count_probe",
      "fire_when": "canon.siblings.firstName.length == 0",
      "prompt": "How many children were in your family?",
      "capture": {"pattern": "integer"},
      "store_as": "sibling_count_plus_self"
    },
    {
      "step": "position_probe",
      "prompt": "What number were you in that lineup — first, second, and so on?",
      "capture": {"pattern": "ordinal_or_integer"},
      "writes": [{"path": "personal.birthOrder", "writeMode": "write"}],
      "promote_staged": true
    }
  ],
  "skip_phrases": ["i don't remember", "can we come back to that", "skip"],
  "on_skip": {"action": "keep_suggest_only", "log": "confirm_pass_skipped"}
}
```

### 2.2 `siblingsBirthOrder.json` — `siblings.birthOrder` per-sibling confirm

Fires when narrative pass stages sibling records where `birthOrder` is the wrong canonical form (e.g. `'youngest'` / `'first'` when scorer wants `'older'` / `'younger'`).

```json
{
  "version": "v1-pilot",
  "field_path": "siblings.birthOrder",
  "fire_conditions": [
    "staged writeMode == suggest_only",
    "staged value NOT in ['older', 'younger']"
  ],
  "micro_flow": [
    {
      "step": "relative_probe",
      "prompt": "Was {siblings.firstName} older or younger than you?",
      "capture": {"pattern": "older_younger_token"},
      "writes": [{"path": "siblings.birthOrder", "value": "{token}", "writeMode": "write", "index": "match_firstName"}],
      "promote_staged": true
    }
  ],
  "per_sibling": true,
  "max_per_section": 2,
  "skip_phrases": ["i don't remember", "skip"],
  "on_skip": {"action": "keep_suggest_only"}
}
```

### 2.3 `parentsRelation.json` — `parents.relation` confirm

Fires when narrative pass stages `parents.firstName=NAME` without a paired `parents.relation`.

```json
{
  "version": "v1-pilot",
  "field_path": "parents.relation",
  "fire_conditions": [
    "canon.parents.firstName.length > canon.parents.relation.length",
    "at least one parents.firstName has no paired relation"
  ],
  "micro_flow": [
    {
      "step": "role_probe",
      "prompt": "And {parents.firstName} — was that your mother or your father?",
      "capture": {"pattern": "mother_father_token"},
      "writes": [{"path": "parents.relation", "value": "{token}", "writeMode": "write", "index": "match_firstName"}]
    }
  ],
  "per_parent": true,
  "max_per_section": 2,
  "skip_phrases": ["skip", "come back to that"],
  "on_skip": {"action": "keep_null"}
}
```

### 2.4 `dateRange.json` — `*.yearsActive` / `*.dateRange` / `*.servicePeriod` confirm

**STATUS: DESCOPED FROM LORI v1 PILOT (Chris decision, 2026-04-22 morning read).** Question-bank tagging audit surfaced only 1 corpus case carrying `date_range_confirm` and 0 failing — not enough target volume to justify shipping the bank in v1. The draft below stays parked in-tree for v1.5 reactivation conditional on corpus expansion: author 3 date-range cases in #111 (patterns in `docs/reports/question_bank_tagging_audit.md` §Date-range corpus gap). When those cases land and at least 2 are stubborn failures, reactivate this bank. Until then, LORI v1 pilot is a **3-field confirm-pass** (birthOrder / siblingsBirthOrder / parentsRelation), not 4-field.

Fires when narrative pass stages a duration phrase ("twenty-five years") instead of an explicit range.

```json
{
  "version": "v1-pilot",
  "field_path_glob": ["*.yearsActive", "*.dateRange", "*.servicePeriod"],
  "fire_conditions": [
    "staged writeMode == suggest_only",
    "staged value matches duration_phrase (e.g. 'X years', 'a decade')",
    "life_map.current_era is set"
  ],
  "micro_flow": [
    {
      "step": "end_anchor_probe",
      "prompt": "When you say {staged_value}, when did that stretch end?",
      "capture": {"pattern": "year_integer"},
      "store_as": "end_year"
    },
    {
      "step": "compute_start",
      "if_duration_parseable": true,
      "store_as": "start_year",
      "formula": "end_year - duration_years"
    },
    {
      "step": "confirm_range",
      "prompt": "So roughly {start_year} to {end_year}?",
      "capture": {"pattern": "yes_no_correction"},
      "on_yes": {"writes": [{"path": "{field_path}", "value": "{start_year}-{end_year}", "writeMode": "write"}], "promote_staged": true},
      "on_correction": {"capture": {"pattern": "year_range"}, "writes": [{"path": "{field_path}", "writeMode": "write"}]}
    }
  ],
  "skip_phrases": ["i don't remember the years", "skip"],
  "on_skip": {"action": "keep_suggest_only"}
}
```

## 3. Dispatcher pseudocode

### 3.1 Session start — kinship skeleton dispatcher

Invoked from `ui/js/interview.js` on new narrator session.

```python
def dispatch_kinship_skeleton(narrator, session, canon):
    if narrator.onboarding_complete:
        return
    if canon.parents.firstName:  # user pre-populated or previous run, skip
        return
    block = load_json("data/interview/kinship_skeleton.json")
    for step in block.steps:
        if step.get("fire_when") and not evaluate(step.fire_when, canon, life_map):
            continue
        if step.get("skip_ok") and user_said_skip():
            log("skeleton.step_skipped", step.step_id)
            continue
        reply = ask_lori(step.prompt)
        if is_skip_phrase(reply, block.skip_phrases):
            log("skeleton.skip_requested_at", step.step_id)
            break
        captures = apply_pattern(step.capture, reply)
        for write in captures.writes:
            canon_write(write.path, write.value, write.writeMode, write.index)
        if step.get("branch"):
            next_step = step.branch[captures.branch_key]
            continue_from(next_step)
        if step.get("confirm_inline"):
            dispatch_inline_confirm(step.confirm_inline, captures, canon)
    canon_write("narrator.onboarding_complete", True)
```

### 3.2 Section boundary — confirm-pass dispatcher

Invoked from `ui/js/interview.js` after `subTopic` completion signal (last anchor question asked + narrator reply received + no followup queued).

```python
def dispatch_section_confirms(section_id, canon_diff, banks):
    staged = [item for item in canon_diff if item.writeMode == "suggest_only" and item.needs_confirmation]
    if not staged:
        return
    fired_count = 0
    MAX_PER_SECTION = 2
    priority_order = ["personal.birthOrder", "parents.relation", "siblings.birthOrder", "dateRange"]
    staged.sort(key=lambda x: priority_order.index(match_bank(x)) if match_bank(x) in priority_order else 999)
    for item in staged:
        if fired_count >= MAX_PER_SECTION:
            log("confirm_pass.max_per_section_reached", section_id, carried_forward=len(staged) - fired_count)
            break
        bank_key = match_bank(item.fieldPath)
        if not bank_key:
            continue
        bank = banks[bank_key]
        if not evaluate_all(bank.fire_conditions, item, canon):
            continue
        # High-confidence extractor writes exempt
        if item.confidence >= 0.8 and item.writeMode == "write":
            continue
        resolved = run_micro_flow(bank.micro_flow, item, canon)
        if resolved.success:
            for write in resolved.writes:
                canon_promote(item, write)
            log("confirm_pass.resolved", item.fieldPath, bank_key)
        else:
            log("confirm_pass.skipped_or_unresolved", item.fieldPath, resolved.reason)
        fired_count += 1
```

### 3.3 Match logic — field path → bank key

```python
BANK_ROUTES = {
    "personal.birthOrder": "birthOrder",
    "siblings.birthOrder": "siblingsBirthOrder",
    "parents.relation": "parentsRelation",
    # Glob-style for date ranges
    "*.yearsActive": "dateRange",
    "*.dateRange": "dateRange",
    "*.servicePeriod": "dateRange",
}

def match_bank(field_path: str) -> Optional[str]:
    if field_path in BANK_ROUTES:
        return BANK_ROUTES[field_path]
    for glob, bank in BANK_ROUTES.items():
        if glob.startswith("*.") and field_path.endswith(glob[2:]):
            return bank
    return None
```

## 4. Canon-collision reconciliation algorithm

The spec flags canon collision (skeleton already wrote `parents.firstName=Janice`, narrative pass tries to write the same) but doesn't specify the algorithm. This is the missing piece.

### 4.1 Rule set (deterministic, in order)

```python
def reconcile_narrative_write(incoming: ExtractedItem, canon: Canon) -> ReconciliationResult:
    existing = canon.lookup(incoming.fieldPath, incoming.index)

    # Rule 1: Nothing in canon yet → normal write.
    if existing is None:
        return ReconciliationResult(action="write", reason="no_collision")

    # Rule 2: Exact match (normalized) → skip write, log for telemetry.
    if normalize(existing.value) == normalize(incoming.value):
        return ReconciliationResult(
            action="skip",
            reason="already_in_canon",
            telemetry={"collision_type": "exact_match", "source_existing": existing.source}
        )

    # Rule 3: Existing from skeleton, incoming from narrative → skeleton wins, emit drift warning.
    if existing.source == "kinship_skeleton" and incoming.source == "narrative_extract":
        return ReconciliationResult(
            action="skip",
            reason="skeleton_authoritative",
            telemetry={"collision_type": "narrative_drift_vs_skeleton", "existing": existing.value, "incoming": incoming.value, "severity": "warn"}
        )

    # Rule 4: Existing from narrative, incoming from confirm-pass → confirm-pass wins (it's the resolution).
    if existing.source == "narrative_extract" and incoming.source == "confirm_pass":
        return ReconciliationResult(action="overwrite", reason="confirm_resolves_narrative")

    # Rule 5: Existing from confirm-pass, incoming from narrative → confirm wins; log drift.
    if existing.source == "confirm_pass" and incoming.source == "narrative_extract":
        return ReconciliationResult(
            action="skip",
            reason="confirm_authoritative",
            telemetry={"collision_type": "narrative_contradicts_confirm", "severity": "warn"}
        )

    # Rule 6: Two narrative writes collide → higher confidence wins; tie → first-writer-wins; log.
    if existing.source == "narrative_extract" and incoming.source == "narrative_extract":
        if incoming.confidence > existing.confidence + 0.1:
            return ReconciliationResult(action="overwrite", reason="higher_confidence_overwrite")
        return ReconciliationResult(action="skip", reason="first_writer_wins")

    # Rule 7: Unknown source pair → default safe (skip + log).
    return ReconciliationResult(action="skip", reason="unknown_source_pair", telemetry={"severity": "error"})
```

### 4.2 Source-provenance requirement

To make Rules 3–5 implementable, every canon entry needs a `source` field. Three provenance values for v1:

- `kinship_skeleton` — written by the onboarding block.
- `narrative_extract` — written by the normal extractor pass.
- `confirm_pass` — written by a confirm-pass micro-flow resolution.

This is a small canon-schema bump (one new field per write), not a re-architecture.

### 4.3 Implicit attribution-boundary guard (second-order benefit)

Rule 3 (existing source=skeleton, incoming source=narrative_extract → skip) is also an implicit attribution-boundary guard for the r5e2-class failures.

Concrete example from case_093 (kent-james-horne, spouse_detail turn):

- Skeleton canon has `parents.firstName=[Leila, Ervin]` (Kent's parents, established at onboarding).
- Narrator says *"Her dad Pete worked all kinds of jobs — Garrison Dam, carpentry, steam boiler work"* (Janice's father, not Kent's).
- Narrative pass tries to write `parents.firstName=Pete` (attribution error — this is Janice's parent, not Kent's).
- Canon-collision reconciler: existing `Leila/Ervin` from skeleton, incoming `Pete` from narrative, not an exact match, Rule 3 fires → skip write + log `narrative_drift_vs_skeleton severity=warn`.
- Net effect: `parents.firstName=Pete` never writes to canon. The mnw violation on this specific path drops without any extractor-side ATTRIBUTION-BOUNDARY rule.

This is not a replacement for SPANTAG subject-beats-section logic, but it is a backstop that catches attribution errors on pre-established canon paths. Worth noting in the pilot report: **track how many narrative_drift_vs_skeleton events correspond to would-have-been mnw violations.** If the count is non-trivial, this reframes part of the LORI value proposition — it's not just confirmation resolution, it's also a canon-anchored attribution gate.

### 4.4 Audit trail

Every reconciliation decision writes a line to `.runtime/logs/canon_reconcile.log`:

```
2026-04-21T23:14:02Z narrator=janice-josephine-horne path=parents.relation index=0 action=skip reason=skeleton_authoritative existing=mother incoming=mother source_existing=kinship_skeleton source_incoming=narrative_extract
```

Post-pilot analysis: `grep action=overwrite` gives the confirm-pass win rate; `grep severity=warn` gives the extractor-vs-skeleton drift rate (a telemetry signal for how much the extractor is still hallucinating on fields skeleton already knows).

## 5. Per-field decision trees — tied to real r5e1 cases

### 5.1 `personal.birthOrder` (cases 002, 014, 024)

```
Narrator reply: "I was the middle child. My older sister Sharon, then me, then Linda."
                                  │
                                  ▼
Narrative pass emits:  siblings.firstName=Sharon (older), siblings.firstName=Linda (younger)
                       personal.birthOrder = MISSING (or "middle", staged suggest_only)
                                  │
                                  ▼
Dispatcher fires birthOrder.json at section boundary
                                  │
                                  ▼
If canon.siblings.firstName.length == 2, skip count_probe.
                                  │
                                  ▼
Ask: "What number were you in that lineup — first, second, and so on?"
Narrator: "I was the middle one" OR "second"
                                  │
                                  ▼
Token map: "middle" + sibling_count=2 → 2; "second" → 2.
                                  │
                                  ▼
Canon write: personal.birthOrder=2  source=confirm_pass
```

Expected pilot outcome on case_014: overall 0.333 → 1.00 (the one missing field resolves cleanly).

### 5.2 `siblings.birthOrder` (cases 002, 014, 024, 047)

```
Narrator reply: "I had two older brothers — Vincent and Jason"
                                  │
                                  ▼
Narrative pass emits: siblings.firstName=Vincent, siblings.firstName=Jason
                     siblings.birthOrder=oldest,second,third  (compound, wrong canonical)
                                  │
                                  ▼
Scorer expects: siblings.birthOrder=older (for the oldest sibling entry)
                                  │
                                  ▼
Dispatcher detects compound-value OR wrong-token-form → downgrade to suggest_only
                                  │
                                  ▼
Fires siblingsBirthOrder.json, per-sibling, capped at 2 per section
                                  │
                                  ▼
Ask: "Was Vincent older or younger than you?" → "older"
Ask: "Was Jason older or younger than you?" → "older"
                                  │
                                  ▼
Canon writes:
  siblings[0].birthOrder = older  source=confirm_pass
  siblings[1].birthOrder = older  source=confirm_pass
```

Expected pilot outcome on case_047: overall 0.667 → 1.00.

### 5.3 `parents.relation` (cases 002, 077 and variants)

```
Narrator reply: "It was my mom Janice and my dad Kent, and my two older brothers..."
                                  │
                                  ▼
Narrative pass emits: parents.firstName=Janice, parents.firstName=Kent
                     parents.relation = NOTHING or partial
                                  │
                                  ▼
Dispatcher: canon.parents.firstName has 2 entries, canon.parents.relation has 0 → fire parentsRelation.json
                                  │
                                  ▼
Ask: "And Janice — was that your mother or your father?" → "mother"
Ask: "And Kent — was that your mother or your father?" → "father"
                                  │
                                  ▼
Canon writes:
  parents[0].relation = mother  source=confirm_pass
  parents[1].relation = father  source=confirm_pass
```

Expected pilot outcome on case_002: overall 0.4 → 0.8+ (the relation + birthOrder fields resolve; sibling.birthOrder also resolves via the sibling bank; schema_gap is unrelated to these confirm flows and stays).

**Note for SPANTAG interaction:** if SPANTAG ships default-on and its evidence-pass picks up the `mom=Janice`, `dad=Kent` NL cues cleanly, the bind-pass should emit `parents.relation='mother'` paired with `parents.firstName='Janice'` with high confidence. Dispatcher would then see `writeMode=write confidence>=0.8` and **skip** the confirm. This is the intended compositional behavior — confirm-pass only fires when SPANTAG couldn't resolve.

### 5.4 Date-range fields

```
Narrator reply: "I worked there for twenty-five years."
                                  │
                                  ▼
Narrative pass emits: *.yearsActive="twenty-five years"  (staged suggest_only, triggers dateRange bank)
                                  │
                                  ▼
Dispatcher: fires dateRange.json
                                  │
                                  ▼
Parse duration_years = 25 (from "twenty-five")
Ask: "When you say twenty-five years, when did that stretch end?" → "2022"
Compute: start_year = 2022 - 25 = 1997
Ask: "So roughly 1997 to 2022?" → "Yes" OR "No, actually 1996"
                                  │
                                  ▼
Canon write: *.yearsActive = "1997-2022"  source=confirm_pass
```

## 6. SPANTAG integration matrix

If SPANTAG ships default-on, LORI's scope changes case-by-case. This table documents the expected overlap.

| Pilot field | SPANTAG effect (if default-on) | LORI scope if SPANTAG ships |
|---|---|---|
| `personal.birthOrder` | SPANTAG Pass 1 picks up `NARRATOR` + `ORDER(middle)` tags. Pass 2 bind with sibling count should emit integer. | If stubborn pack 4-case eval shows ≥2 birth-order flips on SPANTAG alone, **narrow LORI pilot** to 3 fields (drop birthOrder bank). If SPANTAG doesn't move birth-order, **keep all 4**. |
| `siblings.birthOrder` | SPANTAG Pass 1 tags sibling names with `RELATIVE_ORDER` attributes. Pass 2 bind should emit canonical older/younger. | Similar triage: if SPANTAG resolves the "compound value → canonical token" drift, LORI bank becomes belt-and-suspenders. **Keep for first pilot**, measure interaction in pilot report. |
| `parents.relation` | SPANTAG Pass 1 tags `mom Janice` → `NAME` + `ROLE(mother)`. Pass 2 bind co-emits firstName + relation. | **LORI bank stays in any scenario** — skeleton writes this deterministically at onboarding, and confirm bank only fires for mid-interview name mentions where skeleton didn't cover. These are different surfaces. |
| Date-range | SPANTAG doesn't target temporal normalization in current spec. | **DESCOPED from v1 pilot** (Chris 2026-04-22). Parked in-tree, reactivates conditional on #111 corpus expansion adding ≥2 stubborn date-range cases. |

**Go/no-go interaction:** the LORI spec says the pilot's value drops and may re-park if SPANTAG moves the 4 pilot-field classes. This matrix makes that branch concrete: re-park is partial, not total. Date-range and skeleton-side relation are unaffected by SPANTAG regardless of outcome.

## 7. SECTION-EFFECT integration — era/pass/mode gating

The skeleton block is the only place SECTION-EFFECT fields materially gate LORI behavior. Already reflected in `kinship_skeleton.json` (`kin_05_spouse_gate.fire_when`, `kin_06_children_gate.fire_when`).

The confirm-pass banks themselves are era-agnostic — a staged birth-order suggest_only is worth confirming regardless of which era the narrator is in. No era gating needed on Feature B.

**One exception:** the `dateRange.json` bank's `compute_start` step uses `end_year - duration_years`. If `life_map.current_era=school_years` and the duration is "25 years", the plausible start-year is decades before the narrator was alive — flag and skip the compute, ask narrator for both endpoints. Add this as a guard in v1.5, not v1.

## 8. Pilot case sourcing — 15-case map from r5e1 failing set

Selected from `docs/reports/FAILING_CASES_r5e1_RUNDOWN.md` and `data/qa/question_bank_extraction_cases.json`. Each case is mapped to the confirm bank(s) that would fire, the expected canon diff after confirm, and the expected single-turn baseline delta (from r5e1 JSON).

| # | case_id | narrator | subTopic | r5e1 score | Confirm banks that fire | Expected post-LORI score |
|---|---|---|---|---:|---|---:|
| 1 | case_002 | christopher | early_caregivers | 0.400 | skeleton (at onboarding) + siblingsBirthOrder | 1.000 |
| 2 | case_014 | kent | early_caregivers | 0.333 | birthOrder + siblingsBirthOrder | 1.000 |
| 3 | case_024 | janice | early_caregivers | 0.333 | birthOrder + siblingsBirthOrder | 0.900+ |
| 4 | case_028 | janice | family_rituals_and_holidays | 0.000 | (none — schema_gap class; **control case**) | 0.000 (baseline) |
| 5 | case_035 | janice | family_rituals_and_holidays | 0.300 | (none — attribution class, LORI doesn't target) | 0.300 (baseline) |
| 6 | case_047 | christopher | sibling_dynamics | 0.667 | siblingsBirthOrder | 1.000 |
| 7 | case_049 | janice | origin_point | 0.500 | (none — date-missing, narrative class) | 0.500 (baseline) |
| 8 | case_068 | kent | family_loss | 0.525 | (none — notableLifeEvents is narrative, LORI doesn't target) | 0.525 (baseline) |
| 9 | case_077 | kent | siblings_childhood | 0.000 | skeleton (already walked, provides siblings) → this case then becomes "reconcile with existing canon" | 0.900+ |
| 10 | case_079 | christopher | siblings | 0.567 | siblingsBirthOrder (for Vincent/Vince name normalization, edge) | 0.750+ |
| 11 | case_093 | kent | spouse_detail | mnw=1 | (none — attribution class; mnw violation stays unless ATTRIBUTION-BOUNDARY is on) | unchanged |
| 12 | case_025 | janice | childhood_pets | 0.000 | (none — pets out of pilot; **control case**) | 0.000 (baseline) |
| 13 | case_045 | christopher | childhood_pets | 0.000 | (none — pets out of pilot; **control case**) | 0.000 (baseline) |
| 14 | case_046 | janice | childhood_pets | 0.000 | (none — pets out of pilot; **control case**) | 0.000 (baseline) |
| 15 | case_066 | janice | childhood_pets | 0.000 | (none — pets out of pilot; **control case**) | 0.000 (baseline) |

**Why 5 control cases (28, 35, 49, 68, 093 + pets 25/45/46/66):**

The pilot needs a negative control — if LORI "helps" on cases outside its target classes, something is wrong (friendly-fire, r5e2-style). Five of the fifteen cases are explicitly expected to be unchanged. If any control case flips, it's a signal to tighten fire_conditions, not claim a win.

**Pets (4 control cases):** pet salience is flagged for a future micro-flow in the LORI spec's "out of scope" section. Keeping 4 pets cases in the pilot eval lets us track whether future pets-specific work is worth prioritizing.

## 9. Pilot acceptance criteria (quantitative, post-multiturn-harness)

Once WO-EVAL-MULTITURN-01 ships and the multi-turn harness runs, these are the gates:

**PRIMARY (target-class cases, 6 total: 002, 014, 024, 047, 077, 079):**

| Criterion | Gate | Rationale |
|---|---|---|
| ≥4 of 6 target cases score improved by ≥0.3 | GREEN | The confirm mechanism is materially resolving ambiguity on its designed target class |
| 2–3 of 6 improved | YELLOW | Partial — investigate which bank underperformed, tighten before landing default-on |
| ≤1 of 6 improved | RED | Mechanism isn't moving the needle; reconsider pilot scope or implementation |
| Any target case regresses | AUTO-RED | Must not happen — confirm should not hurt |

**CONTROL (non-target cases, 9 total: 028, 035, 049, 068, 093, 025, 045, 046, 066):**

| Criterion | Gate |
|---|---|
| 0 of 9 control cases change by more than ±0.05 | REQUIRED. Any drift = bug in bank routing or canon-collision reconciliation |

**MASTER EVAL (separate lane):**

| Criterion | Gate |
|---|---|
| Master single-turn eval `r5?` delta vs locked floor: ±0 | REQUIRED. LORI adds no single-turn code; master tag must be byte-stable if run on the same extractor commit |

**TELEMETRY:**

| Metric | Target |
|---|---|
| Canon-collision Rule 3 (narrative drift vs skeleton) rate | <10% of narrative-pass writes against skeleton-established paths. If >20%, extractor is still hallucinating despite canon — investigate separately, not LORI's problem to solve |
| Confirm-pass max-per-section hit rate | <30% of sections. If >50%, extractor is staging too much — raise `suggest_only` threshold |
| Narrator skip rate on confirms | <25%. If >40%, interview feel is too scripted — consider LLM dispatcher |

## 10. Implementation checklist — when LORI opens

**Gate:** SECTION-EFFECT Phase 3 closed (#95) AND SPANTAG decision made (#90 default-on or default-off landed).

**Phase 0: Prerequisite verification (0.5 day)**

- [ ] Confirm `ExtractedItem.writeMode`, `needs_confirmation`, `confirmation_reason`, `ExtractFieldsResponse.clarification_required` all reachable in the current extract.py HEAD (landed 2026-04-20, WO-STT-LIVE-02).
- [ ] Confirm TURNSCOPE `current_target_path` enforceable on confirm-pass follow-up turns.
- [ ] Confirm SECTION-EFFECT `current_era/pass/mode` reachable in interview runtime.

**Phase 1: Data files (0.5 day)**

- [ ] `data/interview/kinship_skeleton.json` from §1 draft.
- [ ] `data/interview/confirmation_banks/birthOrder.json` from §2.1.
- [ ] `data/interview/confirmation_banks/siblingsBirthOrder.json` from §2.2.
- [ ] `data/interview/confirmation_banks/parentsRelation.json` from §2.3.
- [ ] `data/interview/confirmation_banks/dateRange.json` from §2.4.

**Phase 2: Frontend dispatcher (1 day)**

- [ ] `ui/js/interview.js` — `dispatchKinshipSkeleton()` at session start.
- [ ] `ui/js/interview.js` — `dispatchSectionConfirms()` at subTopic completion.
- [ ] `ui/js/interview.js` — `matchBank()` routing.
- [ ] `ui/js/canon.js` (or equivalent) — `reconcileNarrativeWrite()` from §4.1 with source-field bump.
- [ ] `ui/js/canon.js` — audit log to `.runtime/logs/canon_reconcile.log`.

**Phase 3: Extractor hook (0.25 day)**

- [ ] `server/code/api/routers/extract.py` — extend `_fragile_field_classifier` catchment to include the 4 pilot fields when `confidence < 0.8` and not already stamped by STT layer.
- [ ] Smoke: verify flag `HORNELORE_LORI_CONFIRM=1` gates the catchment extension; default off = byte-stable.

**Phase 4: Qualitative validation (0.5 day)**

- [ ] Hand-run 15 pilot cases through UI with confirm-pass active. Inspect canon diffs. Write `docs/reports/WO-LORI-CONFIRM-01_PILOT_REPORT.md`.

**Phase 5: Multi-turn harness validation (blocked by WO-EVAL-MULTITURN-01)**

- [ ] Run 15-case multi-turn eval through harness. Check acceptance matrix §9.
- [ ] Ship default-off first, then promote based on gate.

**Estimated total implementation cost (Phase 0–4): ~2.75 days one-person.** Phase 5 gates on separate WO.

## 11. Risk register (additions beyond parent spec)

- **Kinship skeleton interview feel.** 6 questions before the first narrative turn may feel bureaucratic. Mitigation: pilot with one narrator first (christopher-todd-horne has the smallest canon), if the skip rate on kin_03+ steps is >40%, shorten skeleton to mother/father/sibling roster only.
- **Sibling roster pattern-parse brittleness.** "Vincent and Jason, both older, and Linda who's younger" is parseable; "I had Vincent and Jason and Linda" without order tokens forces inline confirms. v1 should log unparseable-roster cases for a v1.5 pattern refresh.
- **Confirm-pass interaction with user typing.** If narrator types a reply instead of speaking, the reply bypasses STT fragile-fact classifier. LORI catchment extension (Phase 3) is the handle — ensures the staged-suggest downgrade still triggers for typed input when confidence signals are unavailable.
- **Source-provenance schema bump.** Adding `source` to every canon entry touches existing canon data. Migration path: default `source="legacy"` on all existing writes; Rule 7 (unknown source pair) handles legacy collisions safely. Migration is one JSON pass, not a code change.

## 12. Non-goals (reinforcing the parent spec)

- LORI does not fix the truncation-starved cluster (7 stubborn cases on the `#96` truncation lane).
- LORI does not fix the schema_gap dominant failure category (28/45 failures in r5e1). Schema_gap is extractor-side.
- LORI does not replace SPANTAG. If SPANTAG ships default-on and materially moves the target classes, LORI narrows; it does not deprecate.
- LORI is not a measurement upgrade. The master eval stays single-turn. Multi-turn eval is WO-EVAL-MULTITURN-01.

---

## Summary

This prep pack takes WO-LORI-CONFIRM-01 from parked-conceptual to implementation-ready. The spec establishes the why, when, and guardrails; this pack fills the what (data files as code blocks, dispatcher pseudocode, reconciliation algorithm, per-field trees, pilot case map, acceptance matrix). When SECTION-EFFECT Phase 3 signs off and SPANTAG reaches a decision, opening LORI is now a ~2.75-day implementation pickup rather than another round of specification.

The pilot case map (§8) is the link point to WO-EVAL-MULTITURN-01 — those 15 cases are the multi-turn pack.
