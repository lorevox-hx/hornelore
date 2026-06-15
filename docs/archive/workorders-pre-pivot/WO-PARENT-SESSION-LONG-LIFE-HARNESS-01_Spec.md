# WO-PARENT-SESSION-LONG-LIFE-HARNESS-01

**Status:** PARKED — opens after lifemap_state_alias_v1 confirms Life Map state-write reaches the harness
**Severity:** Parent-session readiness probe — closest synthetic to a real Janice/Kent session
**Owner:** TBD
**Authored:** 2026-05-03 evening
**Lane:** Parent-session readiness harness expansion
**Test ID:** TEST-22

---

## Why this WO exists

Today's harness validates a **fresh narrator with no story content**:
- `run_voice("hearth")` runs 8 canned turns then ends
- `run_life_map_cycle` clicks one or all 7 eras with a brand-new narrator
- `run_silence_test` exercises one quiet pause
- `run_shatner_cascade` (TEST-21) exercises identity intake + 2 era clicks

None of these probe what happens when the narrator has **already shared dozens of stories spanning multiple chapters of a real life**. That's the actual parent-session shape — Janice and Kent are 86 and 86; their first session will not be an empty-state test, and their second session even less so.

TEST-22 builds a **synthetic 200-year-old composite narrator** using stories sourced from the existing voice library (`docs/voice_models/VOICE_LIBRARY_v1.md`) and the diagram cases (`data/qa/sentence_diagram_story_cases.json` sd_001-sd_043 + `data/evals/sentence_diagram_cultural_context_cases_sd044_sd065.json`), seeded across all 7 eras. Then puts the FULL UI through its paces — Lori, Timeline, Life Map, Peek at Memoir, archive/DB.

**Locked principle:** *Lori is a companion, not an instrument.* The synthetic narrator is a stress test of OUR pipeline, not a stand-in for a real elder. The test fails not when Lori produces "wrong" content but when she **violates the contracts we've already locked**: discipline, voice respect, era-anchored framing, no-menu-offers, sacred-silence on cues that warrant it.

---

## Synthetic narrator design

### Composite identity

A single narrator profile that serves as the data anchor:

```
fullName:       "Esther Ridley-Yamamoto-Cordova"
preferredName:  "Esther"
dateOfBirth:    "1825-07-14"
placeOfBirth:   "Charleston, South Carolina"
birthOrder:     "youngest"
```

The 200-year-old framing is intentionally absurd — it's a synthetic composite, not a fiction. The hyphenated surname signals *"this narrator carries multiple inherited lineages"* and primes the reader/operator that the per-era voice shifts are by design.

### Voice arc across eras

Each era cluster sources its turn data from a different voice in `docs/voice_models/VOICE_LIBRARY_v1.md`. This is a **stress test** of whether Lori (a) picks up era context cleanly on click, (b) does not collapse multiple voices into a single tone, (c) respects cultural humility per voice, and (d) maintains continuity in memory_echo across the whole arc.

| Era cluster | Voice | Source cases | Sample turns |
|---|---|---|---|
| **Earliest Years** + **Early School Years** | Hearth (Janice baseline) | `sd_001` (birth/place/date "I was born in Cedar Falls, Iowa, on August 30, 1939..."), `sd_002`-`sd_018` (12 earliest_years + 21 early_school_years cases — heavy distribution) | "Mother had a silk ribbon from her wedding she'd take out once a year..."; "I had mastoid surgery when I was four..." |
| **Adolescence** + **Coming of Age** | Field (African American Georgia, coded survival) | `sd_019`-`sd_028` (2 adolescence + 2 coming_of_age) plus `sd_044`, `sd_046`, `sd_048` (Field cases from cultural-context pack) | Coded survival language; "Sunday voice / Monday voice"; Ellis Island clerk renaming |
| **Building Years** | Bridge (Asian American California) | `sd_029`-`sd_032` (4 building_years) plus `sd_050`, `sd_052`, `sd_054` (Bridge cases) | Paper Son arrival; family business across generations |
| **Later Years** + **Today** | Shield (Crypto-Jewish New Mexico, MAX SUPPRESSION) | `sd_041`-`sd_043` (2 later_years) plus `sd_058`-`sd_065` (Shield cases — sacred silence, "Remember but never tell") | Coded sacred silence; protective health language; deathbed hand-off |

**Sourcing notes:**
- The sd_001-sd_043 pack has no explicit voice tags — they're generic narrator turns. Group them by `current_era` field (already verified: 12 earliest_years, 21 early_school_years, 2 adolescence, 2 coming_of_age, 4 building_years, 2 later_years).
- The sd_044-sd_065 pack DOES have `voice_reference` field. Filter by Hearth / Field / Bridge / Shield.
- Where the diagram pack underweights an era (e.g., adolescence has only 2), the harness can rotate through them or pad with cases from `data/lori/lori_narrative_cue_eval.json` and `data/evals/lori_cultural_humility_eval.json`.

### Total turn budget

~30–40 narrator turns across all eras:
- Earliest + Early School: ~12 turns (high case density)
- Adolescence + Coming of Age: ~6 turns (lower density; 4 cases + 2-4 cultural)
- Building Years: ~6 turns (4 cases + 2 cultural)
- Later Years + Today: ~6–8 turns (2 cases + 6 cultural; the Today seed is special — see "Memory recall test")

Each turn fired via `self.ui.send_chat(text)`, with `_wait_for_fresh_lori_turn` between sends. Total wall-clock: ~10–15 minutes including all the era clicks + checks.

---

## Pipeline checks per era click

For each of the 7 eras, the harness clicks the era button and captures **12 strict + 8 informational** observations. Strict failures drive RED; informational ones surface as notes.

### STRICT (drives RED severity)

1. `clicked_ok` — button click landed
2. `era_click_log_seen` — `[life-map][era-click] era=X` console marker fired
3. `lori_prompt_log_seen` — `[life-map][era-click] Lori prompt dispatched for era=X` marker fired
4. `state_currentEra` — `state.session.currentEra === era_id` (now visible via window.state alias from BUG-LIFEMAP-STATE-VISIBILITY-01)
5. `state_activeFocusEra` — same era_id
6. `lori_replied` — fresh Lori turn arrived within 45s
7. `lori_era_anchored` — Lori reply mentions the era's warm label OR is era-shape appropriate (present-tense for Today, past-tense for historical)
8. `question_count >= 1` — at least one question
9. `nested_question_count == 0`
10. `menu_offer_count == 0`
11. `voice_rule_violations.length == 0` — voice-specific rules from VOICE_LIBRARY_v1.md (Field T3 must NOT ask "what was the Code?"; Shield T3 must have `expected_question_count_t3=0` per sacred_silence override)
12. `kawa_mode_absent_in_runtime71` — confirms Lane C (Kawa retirement) holds across the era arc

### INFORMATIONAL (reported, never RED)

13. `timeline_active_era_id` — chronology accordion's `.cr-active-era` element matches clicked era_id (will report stale until WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01)
14. `timeline_anchored_stories_count` — count of memory items the timeline has rendered for this era
15. `memoir_section_present` — does the memoir popover have a `[data-era-id="X"]` section?
16. `memoir_top_visible_heading` — top heading inside the open memoir popover (will not match active era until WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01 + scroll-to-section)
17. `memoir_section_text_excerpt` — first 200 chars of the active era's section content (proves stories ARE being persisted to the memoir even if the popover doesn't auto-scroll)
18. `archive_turn_count_for_era` — query `/api/operator/story-candidates?narrator_id=X&era=Y` (or equivalent) — how many story_candidate rows exist tagged with this era
19. `db_archive_total_for_narrator` — total story_candidates rows for the synthetic narrator across all eras
20. `bb_field_count_populated` — how many BB personal-section fields have non-null values (proves identity intake stuck)

---

## Memory recall test (end-of-arc)

After all 7 era clicks complete, the harness:

1. Clicks "Today" one more time (or sends `[SYSTEM: navigate to Today]`)
2. Sends `"what do you know about me"` via `self.ui.send_chat`
3. Captures Lori's memory_echo response
4. Asserts the response references **at least 3 era-distinct facts** seeded earlier:
   - One Hearth-era fact (e.g., birthplace from sd_001 or the silk ribbon)
   - One Field-era fact (e.g., a coded survival anchor or the Sunday/Monday register shift)
   - One Bridge-or-Shield fact (e.g., Building Years occupation or the sacred-silence theme)

This proves **per-narrator memory works across the full arc**, even before per-era recall (WO-LORI-ERA-RECALL-01) lands. If Lori only references Today-era facts, that's a per-era-recall gap — INFORMATIONAL, not RED, because it's an unbuilt feature.

The strict assertion is: Lori's memory_echo response must reference facts from MULTIPLE eras. The lower bar (1 fact per voice cluster) is the real proof point — facts persisted, summary read them back.

---

## Report sections

The harness output extends the existing `RehearsalReport` markdown with one new top-level section:

```
## TEST-22 — Long-Life Multi-Voice Narrator Cascade

### Setup
- narrator: Esther Ridley-Yamamoto-Cordova
- person_id: <uuid>
- voices used: Hearth, Field, Bridge, Shield
- total turns sent: <N>
- total time: <mm:ss>

### STRICT — Era click chain (per era)
| Era | Clicked | Click log | Prompt log | currentEra | activeFocus | Lori | Era-anchored | Q | Nest | Menu | Voice rule | Kawa | Severity |
|---|...

### INFORMATIONAL — Downstream cohesion (per era)
| Era | Timeline active | Stories | Memoir section | Memoir heading | Memoir excerpt | Archive turns | DB total | BB fields | Notes |
|---|...

### Memory Recall (end-of-arc)
| Probe | Lori response (excerpt) | Eras referenced | Strict pass |
|---|---|---|---|
| "what do you know about me" | ... | Earliest Years; Field; Building Years | ✓ |

### Voice arc divergence
- Hearth-era turns: <N>, voice_rule_violations: 0
- Field-era turns: <N>, voice_rule_violations: 0
- Bridge-era turns: <N>, voice_rule_violations: 0
- Shield-era turns: <N>, voice_rule_violations: 0
- Cross-voice contamination check: <Lori's tone in era N+1 must NOT echo the voice template from era N>
```

The cross-voice contamination check is a soft heuristic — does Lori's Building Years response use vocabulary from the immediately-prior Coming of Age (Field) cluster? If yes, that's a context-bleed flag (INFORMATIONAL). True voice-isolation would need adversarial probes outside this WO.

---

## Implementation outline

**File:** `scripts/ui/run_parent_session_rehearsal_harness.py` (extend; do NOT fork)

**New dataclasses** (~80 lines):
- `LongLifeEraStep` — one era's strict + informational fields
- `LongLifeMemoryRecall` — recall probe result
- `LongLifeCascadeResult` — narrator setup + per-era steps + recall + voice divergence

**New constants** (~30 lines):
- `LONG_LIFE_NARRATOR_IDENTITY` — name/dob/place/order
- `LONG_LIFE_ERA_VOICE_MAP` — { era_id: voice_name, ... }
- `LONG_LIFE_TURN_PLAN` — list of (era_id, voice_name, source_case_id, narrator_text) tuples in playback order

**New helpers** (~150 lines):
- `_load_long_life_turns()` — reads sd_001-sd_065 + voice library, builds `LONG_LIFE_TURN_PLAN`
- `_seed_synthetic_narrator()` — adds narrator + completes identity (reuse Shatner cascade's inlined intake)
- `_play_era_arc(era_id, voice_name, turns)` — sends each turn, waits for Lori, scores
- `_query_archive_for_narrator(person_id, era_id=None)` — hits the operator endpoint for story_candidate counts
- `_probe_memoir_section_for_era(era_id)` — returns `(present, heading, excerpt)`

**New method** `run_long_life_cascade(self) -> LongLifeCascadeResult` (~200 lines):
1. Add narrator + complete identity with `LONG_LIFE_NARRATOR_IDENTITY`
2. For each era in canonical order: play that era's voice arc (~5 turns) → click era button → run STRICT + INFO captures
3. After all 7 eras: run Memory Recall test
4. Compute voice arc divergence stats
5. Return cascade result

**Wire into `main()` runner** (~10 lines):
- Add `--include-long-life` CLI flag (default off — this is a heavyweight test, opt-in)
- When flag set, call `runner.run_long_life_cascade()` after Shatner cascade
- Roll into severity rollup (only STRICT failures count toward RED)

**Markdown rendering** (~80 lines):
- New top-level section per the spec above

**Total sized:** ~600 lines harness + ~30 KB seed data file (the turn plan can be inline since it references existing case IDs)

---

## Acceptance — what GREEN looks like

After lifemap_state_alias_v1 + Shatner cascade are GREEN + WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01 lands:

```
TEST-22 Setup: PASS (narrator + identity)
Era arcs: 7 eras × ~5 turns each, all voice_rule_violations=0
STRICT click chain: 7/7 eras PASS
INFO downstream:
  - Timeline active matches clicked era (after subscribers WO)
  - Memoir section present for each era (always — sections render top-to-bottom)
  - Archive turn counts > 0 for each era
Memory Recall: PASS (Lori references ≥3 era-distinct facts)
Voice arc divergence: cross-voice contamination flag = 0
Overall: PASS or AMBER
```

If any STRICT row fails:
- `state_currentEra` mismatch → state-write or alias regression
- `voice_rule_violation` → cultural humility regression
- `menu_offer_count > 0` → discipline filter regression
- `lori_era_anchored = false` → backend prompt_composer not consuming current_era (regression of pass-2A directive)

---

## Prerequisites — must land BEFORE building

1. **lifemap_state_alias_v1** — confirms `window.state` exposes the real state object so the harness's STRICT checks (state_currentEra, state_activeFocusEra) actually read the real values.
2. **Shatner cascade identity intake works** — currently fails because BB fields don't save. Either narrator session_style needs to be `questionnaire_first` for synthetic narrators, or there's a deeper QF dispatcher gap. Resolve before building TEST-22 because TEST-22's much larger turn count will multiply the failure mode.
3. **WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01** — Timeline + Memoir don't auto-react to era click today. Without those subscribers, INFORMATIONAL rows 13-16 are uniformly stale and lose signal value.
4. **Operator story-candidates endpoint accessible** — `HORNELORE_OPERATOR_STORY_REVIEW=1` must be set OR the harness needs DB query alternative. Verify the endpoint shape returns era-filterable results before designing the archive probe.

---

## NOT in scope (separate WOs)

- **Audio capture per era** — TEST-22 is text-only. Audio adds another stochastic surface and isn't blocking parent-session readiness.
- **Multi-narrator switch test** — switching from Shatner to Esther mid-test would surface narrator-bleed bugs but multiplies harness complexity. Park as TEST-23.
- **Long-form story trigger validation** — the synthetic turns are short by design. Long-form story-trigger tests live in `tests/test_story_trigger.py` already.
- **Per-era memory recall** — requires WO-LORI-ERA-RECALL-01 backend work (era-scoped DB query). TEST-22's memory recall probe is per-NARRATOR not per-era.
- **Photo arc** — synthetic narrator has no photos. Photo cascade is its own WO (WO-PHOTO-ANCHOR-LIFE-MAP-CASCADE-01 if/when authored).

---

## Cross-references

- **VOICE_LIBRARY_v1.md** — source of voice templates + voice-rule definitions for cultural humility checks
- **sentence_diagram_story_cases.json (sd_001-sd_043)** — extractor-grounded narrator turns with explicit `current_era` field
- **sentence_diagram_cultural_context_cases_sd044_sd065.json** — cultural-context cases with `voice_reference` field
- **lori_cultural_humility_eval.json** — additional voice-rule cases for fallback when sd cases don't cover an era
- **WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01** — prerequisite for INFO rows 13-16 to be useful
- **WO-LORI-ERA-RECALL-01** — would unlock per-era memory recall as a STRICT check (currently an informational/aspirational note)
- **WO-EX-UTTERANCE-FRAME-01** — utterance frames already wire era context to extractor. TEST-22 will exercise this at scale across 30+ turns and surface any binding regressions.
- **CLAUDE.md design principles** — TEST-22 is the closest synthetic to "a real Janice/Kent session." The locked principle "Lori is a companion, not an instrument" is the test's north star: failures are pipeline contracts violated, not Lori's content judged.

---

## Bottom line

TEST-22 is the harness that tells you whether Lori, Timeline, Life Map, Memoir, and the DB hold their contracts when a narrator has actually shared a life across multiple chapters. It's the closest you can get to parent-session realism without putting Janice or Kent in front of the system.

Build AFTER the prerequisites land. Estimate ~1.5 days from spec → first GREEN run.
