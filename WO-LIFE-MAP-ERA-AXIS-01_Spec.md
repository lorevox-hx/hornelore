# WO-LIFE-MAP-ERA-AXIS-01 — Spec

**Status:** READY (review-first; multi-phase)
**Type:** Architectural unification + UI restructure + Lori behavior wire
**Date:** 2026-04-27
**Lab/gold posture:** Hornelore-side first. Promotion to Lorevox follows the lab/gold rule (this banks here, then promotes — NOT parallel-build). Era taxonomy is currently identical across both repos so the rename + rewire applies cleanly to Lorevox once Hornelore locks.
**Companion to:** `WO-ACCORDION-TIMELINE-FORENSIC-01_Spec.md` (accordion restoration). The accordion's era-banding (Phase 5 of this WO) presupposes the accordion is mounted; FORENSIC-01 must complete first.
**Three-agent convergence:** Chris / Claude / ChatGPT triangulated 2026-04-27. Decisions locked at top of WO.

---

## Core rule (read this first)

```
ERA       = primary spine (where in life)
MEANING   = secondary axis (what kind of story; UI grouping + question filter)
ARC GAP   = intelligence layer (priority signal within the era × meaning cell)
TODAY     = orthogonal vantage (bridge between life and memoir)
```

This WO does NOT introduce a third axis. Arc-gap stays demoted to a tie-breaker inside the era × meaning cell — the existing `prompt_composer.py:760–820` mechanism is preserved, not removed.

---

## Why this WO exists

Hornelore today carries **three competing structures** for organizing a narrator's life:

1. **Chronological timeline** (year-banded, in `chronology-accordion.js`)
2. **6-arc memoir narrative frames** (Legend Begins / Formative Years / Crossroads / Peaks & Valleys / Current Horizon / The Compass — in `hornelore1.0.html:6644` `lv80BuildMemoirSections`)
3. **8-bucket meaning taxonomy** (Turning Points / Hard Moments / Identity & Belonging / etc. — in `hornelore1.0.html:7183` `_LV80_MEMOIR_SECTIONS`)

Plus a **6-era life-map taxonomy** that's already wired in nine places (`app.js:5144`, `bio-builder-family-tree.js:67`, `interview.js:135`, `life-map.js:60`, `chronology-accordion.js`, `prompt_composer.py:722`, `run_question_bank_extraction_eval.py:1106`, etc.) but is **read-only as far as Lori's question selection is concerned**. Lori sees the era in her runtime block but doesn't act on it as a directive.

The cost of three competing structures: facts get tagged twice (once by era, once by meaning bucket), the memoir display fights the timeline, and Lori asks generic structured questions instead of era-contextualized ones. The 8-bucket meaning taxonomy ended up being a parallel display structure that makes facts homeless when they don't fit a bucket.

**The fix:** collapse to **one primary axis (era), one secondary axis (meaning), one orthogonal vantage (today), and one intelligence layer (arc gap)**. Era becomes the spine across timeline display, accordion banding, Life Map navigation, memoir organization, and Lori's question selection. One key, four uses.

---

## Decisions locked (three-agent convergence, 2026-04-27)

```
1. Era taxonomy: 6 first-class eras (existing codebase taxonomy, kept).
   No fold (adolescence stays separate from elementary years).
   No split (midlife stays one era; later_life stays one era).

2. School_years renames to elementary_years for routing-layer
   disambiguation against adolescence (which is also "school years"
   in lay English). Snake_case key precision matters because era keys
   appear in logs, error messages, eval reports, and the SECTION-EFFECT
   payload (#93).

3. Today is a 7th NON-ERA bucket — a separate axis, not part of the
   era spine. Today carries four sub-flavors: present-tense state,
   current life facts, reflection on past, identity now. Today is
   the bridge between life and memoir.

4. Question selection wire — Layer (Option 2):
   Era × Meaning defines the question pool.
   Arc gap prioritizes within the pool.
   NOT a triple-axis grid (288 cells rejected).

5. Frame reassignment:
   - "The Legend Begins" → header tile of Earliest Years (birth, name,
     identity).
   - "The Compass" → folds into Today as the wisdom/reflection layer
     (pets, traditions, unfinished dreams, messages-for-future-
     generations).
   - 6-arc warm labels lose their special status; some get repurposed
     as alternative warm labels for era keys.

6. Display: 8 meaning-bucket headings (Turning Points / Hard Moments /
   etc.) STOP being top-level memoir section headers. They become:
   - Sub-tags inside each era band (display sub-counts).
   - Question-narrowing filter inside the era × meaning cell (Lori).
   - Metadata on facts (filterable, queryable in lab/extraction view).
```

---

## Final taxonomy (locked)

| Snake_case (routing) | Warm UI label | Age range | Notes |
|---|---|---|---|
| `early_childhood` | **Earliest Years (0–5)** | 0–5 | Receives Legend-Begins content as header tile (birth, name, identity). |
| `elementary_years` | **Early School Years (6–12)** | 6–12 | Renamed from `school_years` for disambiguation. Warm label is "Early School Years" not "Elementary School Years" — less institutional, more globally readable. |
| `adolescence` | **Adolescence (13–18)** | 13–18 | First-class era (not folded into elementary). High-school years. |
| `early_adulthood` | **Coming of Age (19–30)** | 19–30 | Departure / first-big-choices era. |
| `midlife` | **Building Years (31–55)** | 31–55 | Career / family / home. |
| `later_life` | **Later Years (56+)** | 56+ | Plain label. Avoids "Looking Back" implication and "Current Horizon" collision with Today. |
| `today` *(non-era axis)* | **Today** | (no age range) | Bridge between life and memoir. Receives Compass content. |

**Alternative warm labels (operator preference, not locked):**
- `early_adulthood` → "Crossroads (19–30)"
- `midlife` → "Peaks & Valleys (31–55)"
- `later_life` → "Looking Back (56+)" or "Current Horizon (56+)"

The snake_case keys are LOCKED; warm UI labels are tuneable in `data.js` / `interview.js` without touching routing.

---

## Scope — IN

1. **Snake_case rename** `school_years` → `elementary_years` across 9 files (UI + server + eval + Lorevox mirror).
2. **Today bucket scaffolding** — new non-era surface in state, prompt composer, UI, and question pool. 4 sub-flavors with their own question stems.
3. **Era × Meaning question pool authoring** — 48 question stems (6 eras × 8 meaning sub-tags) plus today's stems.
4. **Wire from era-click to Lori question selection** — convert `interview.js:135–142` `ERA_PROMPTS` from anchoring cards to question-pool drivers; convert `prompt_composer.py:722, 779` era line from descriptive to directive; layer arc-gap as priority within era × meaning cell.
5. **Accordion era-banding** — switch `chronology-accordion.js` from year-band primary grouping to era-band primary grouping with year tiles inside. Engine already supports it (`cr-active-era` highlighting + `yearGroup.era` tags exist today).
6. **Life Map mini/popout single-component refactor** — one mind-elixir instance rendered at two zoom levels for right-rail mini and Peek-popout. Today node added as separate marker.
7. **Compass-into-Today data migration** — migrate `additionalNotes` / `technology` / `pets` / `familyTraditions` content from `lv80RenderCompass` into Today's structured surface.
8. **Frame reassignment — Legend Begins** — birth/name/identity content moves from `lv80RenderLegend` to top-tile of Earliest Years era band.
9. **Memoir display restructure** — `lv80BuildMemoirSections` switches from 6-arc warm labels to 6 era sections + Today section. The 8-bucket meaning taxonomy (`_LV80_MEMOIR_SECTIONS`) stops being top-level structure; becomes sub-grouping inside each era section.
10. **Acceptance tests** — 12 acceptance tests covering rename byte-stability, era-click question selection, accordion era-banding, Life Map sync, Compass migration, today bucket activation, arc-gap layering preservation.

---

## Scope — OUT (deferred / not this WO)

- **Schema additions for new fact metadata** (`era` and `meaning_tag[]` already exist on facts via SECTION-EFFECT Phase 2 + the Phase A meaning-tagging pipeline). No schema changes in this WO.
- **Narrative-arc beat tagging** — already running (`prompt_composer.py:760–820`). Demoted to priority signal, not removed. No code change to the arc mechanism itself.
- **Rewriting the kinship-projection matrix** (`bio-builder-family-tree.js:67–82`) — under the locked 6 eras (no splits), the matrix is unchanged. Era-keyword tuning at L77–82 is the only change (one keyword set rename).
- **Photo/document era re-tagging** — photos and docs already era-tagged via `current_era` plumbing. No retag pass needed.
- **Memory River / Kawa** — out of scope. WO-ACCORDION-TIMELINE-FORENSIC-01 handles its narrator-room demotion separately.
- **Lorevox promotion** — happens after Hornelore banks. Promotion is a separate single-commit pass once the WO closes here.

---

## Phase breakdown

### Phase 1 — Snake_case rename `school_years` → `elementary_years` (mechanical, byte-stable except rename)

**Goal:** clean rename across all 9 touchpoints. No behavior change. Old-key compatibility shim for any persisted data.

**Files:**

| File | Lines | Change |
|---|---|---|
| `ui/js/app.js` | 5145, 5154 | era array + age band map |
| `ui/js/state.js` | 111 (type comment) | union-type doc string |
| `ui/js/interview.js` | 137 (`ERA_PROMPTS`), 375 (`eraZoneMap`) | rename keys |
| `ui/js/bio-builder-family-tree.js` | 68, 78 | kinship weights row + era keywords row |
| `ui/js/life-map.js` | ~60–65 (`_DEFAULT_ERA_DEFS`) | rename label entry |
| `ui/js/chronology-accordion.js` | era-tag handling | rename emitted label |
| `server/code/api/prompt_composer.py` | (no hardcoded era strings; reads from `runtime71`) | byte-stable, no change |
| `scripts/archive/run_question_bank_extraction_eval.py` | 1118 (`_phase_to_era` mapping) | rename mapping value |
| `data/qa/question_bank_extraction_cases.json` | any `phase: school_years` cases | sed-replace; verify with grep |
| **Lorevox mirror** | same files in `lorevox/ui/js/` | identical rename, separate commit |

**Compatibility shim:** add a one-time migrator at narrator-load that converts persisted `currentEra: "school_years"` → `currentEra: "elementary_years"` in localStorage and bio-builder blob. Lives in `state.js` narrator-load path. Logged once per migration.

**Acceptance:**
- `grep -rn "school_years"` returns zero hits in code paths (only in changelogs / historical reports / migration shim).
- One clean full-master eval run with `r5h` baseline parity (no regressions; eval byte-stable except for the era key string in logs).
- Persisted narrator data with old key auto-migrates without user action.

**Reversibility:** rename is reversible via reverse rename. No flag needed for this phase — it's a pure mechanical change.

---

### Phase 2 — Today bucket scaffolding (additive, default-off)

**Goal:** introduce `today` as a first-class non-era bucket with state, UI surface, and prompt-composer wiring. Default off behind `HORNELORE_TODAY_BUCKET=1` flag until Phase 3 question pool lands.

**State changes (`ui/js/state.js`):**
- `state.session.todayActive: boolean` — true when narrator is in today-vantage mode.
- `state.session.todaySubFlavor: 'state' | 'current_life' | 'reflection' | 'identity_now' | null` — which of today's four sub-flavors is active.

**Today detection (`ui/js/app.js` + `interview.js`):**
- Add `_detectTodaySignal(utterance)` — heuristic classifier on narrator's most recent turn. Triggers on present-tense markers ("today," "right now," "these days," "lately," "looking back now," "I think now that…"). Returns `{active: boolean, sub_flavor: ...}`.
- When today signal detected, `state.session.todayActive = true` and Lori's next question is pulled from today pool, NOT from active era's pool.

**Prompt composer (`server/code/api/prompt_composer.py:722–820`):**
- Add `today_active: bool` and `today_sub_flavor: str` keys to `runtime71`.
- New runtime line: `today_active: true (sub_flavor: reflection)` injected after the existing era line when active.
- Today directive block (parallel to existing `memoir_arc_gaps` block): "When the narrator is reflecting on the present, ask present-tense questions that bridge their life story to their current sense of self. Sub-flavor X suggests …"

**UI surface:**
- Right-rail Life Map: add Today node (visually distinct — not on the era ring, separate marker).
- Memoir Peek: add Today section after the 6 era sections.
- Accordion left rail: Today appears as a top-of-rail strip ("Today · 4 entries"), distinct from era bands.

**Acceptance:**
- With `HORNELORE_TODAY_BUCKET=1`: today signal detection fires on test phrases; `today_active: true` appears in api.log runtime block; Today UI surfaces render.
- With flag off: zero new behavior; no today UI; no new runtime lines.
- Today section in memoir renders empty placeholder until Phase 7 migration lands content.

**Reversibility:** flag-gated. Off = byte-stable.

---

### Phase 3 — Era × Meaning question pool authoring (content authoring beat)

**Goal:** author the question stems for the era × meaning matrix and today's four sub-flavors. Content lives in a new `data/question_pool/` directory.

**Structure:**

```
data/question_pool/
├── era_x_meaning.json       (48 cells: 6 eras × 8 meaning sub-tags)
├── today_pool.json          (4 sub-flavors: state, current_life, reflection, identity_now)
└── README.md                (authoring conventions)
```

**Schema for `era_x_meaning.json`:**

```json
{
  "early_childhood": {
    "turning_points": ["Was there a moment in your earliest years that everything changed after?", "..."],
    "hard_moments":   ["Was there a loss when you were small that you still carry?", "..."],
    "identity_belonging": [...],
    "change_transition": [...],
    "family_relationships": [...],
    "work_daily": [],          // empty for early_childhood — no work yet
    "education": [],            // empty for early_childhood — no school yet
    "story_details": [...]
  },
  "elementary_years": {
    ...
  },
  ...
}
```

Cells legitimately empty for an era leave `[]`. Lori's question selector skips empty cells and falls back to non-empty cells in the same era.

**Authoring conventions (in `README.md`):**
- 3–6 stems per non-empty cell.
- Each stem is era-specific and meaning-specific (no generic "tell me about your family").
- Stems use second-person ("you," "your") and warm tone consistent with WO-10C cognitive support voice.
- Variables in `{}` for Lori's runtime substitution: `{narrator_first_name}`, `{era_label}`, `{age_range}`.

**Today pool schema (`today_pool.json`):**

```json
{
  "state":         ["How are you feeling today?", "What's on your mind right now?", "..."],
  "current_life":  ["What does a typical day look like for you these days?", "..."],
  "reflection":    ["Looking back now, is there something you'd tell your younger self?", "..."],
  "identity_now":  ["When you think about who you are now, what feels most true?", "..."]
}
```

**Loading:**
- `interview.js` adds `_loadQuestionPool()` — fetches both JSONs at narrator-room init, caches in `state.questionPool`.
- Lori's question selector reads from cache, not direct file (allows hot-reload during dev).

**Acceptance:**
- 48 era × meaning cells authored with at least one stem each, OR explicitly marked empty (`[]`) with rationale comment.
- 4 today sub-flavors authored with 3+ stems each.
- `data/question_pool/README.md` documents conventions.
- Unit test: cache loads cleanly; selector returns era-appropriate stem for any (era, meaning) input.

**Reversibility:** content-only addition. Removing the JSONs falls back to current generic question behavior.

---

### Phase 4 — Wire era-click → Lori question selection (behavioral change, flag-gated)

**Goal:** convert `interview.js:135–142` `ERA_PROMPTS` from memory-anchoring UI cards into Lori question-pool drivers. Layer arc-gap as priority signal within the era × meaning cell.

**Flag:** `HORNELORE_ERA_AXIS=1`. Off = current narrative-arc-gap-driven behavior unchanged.

**Files:**

| File | Lines | Change |
|---|---|---|
| `ui/js/interview.js` | 135–142 (`ERA_PROMPTS`), question selector | Replace ERA_PROMPTS with question-pool dispatcher; add era × meaning × arc-gap selection logic. |
| `ui/js/state.js` | session block | Add `state.session.activeEra`, `state.session.eraOverride` (manual click vs system-inferred). |
| `ui/js/life-map.js` | era node click handler | Click → `setActiveEra(eraKey)` → triggers question-pool reload + accordion focus. |
| `ui/js/chronology-accordion.js` | era band click | Same handler — clicking an era band on the accordion = clicking the Life Map era node. |
| `server/code/api/prompt_composer.py` | 722–820 | Convert `era:` line from descriptive to directive: "Ask within the {era_label} era × {meaning_focus} cell. The narrator's narrative-arc gap is {arc_gap} — prefer questions that surface this beat." |

**Selection algorithm (in `interview.js`):**

```javascript
function _selectNextQuestion() {
  // 1. If today signal active → pull from today pool by sub-flavor
  if (state.session.todayActive) {
    return _pickFromTodayPool(state.session.todaySubFlavor);
  }
  // 2. Active era — explicit click or system-inferred
  const era = state.session.activeEra || _inferCurrentEra();
  // 3. Meaning gap detection — which sub-tag is thinnest in this era's facts
  const meaningFocus = _detectMeaningGap(era);
  // 4. Pull pool from era × meaning cell
  const pool = state.questionPool.era_x_meaning[era][meaningFocus] || [];
  // 5. Arc-gap priority — within pool, prefer stems that surface unfilled arc beat
  const arcGap = _getArcGap();  // existing prompt_composer logic, mirrored client-side
  return _prioritizeByArcGap(pool, arcGap);
}
```

**Acceptance:**
- With `HORNELORE_ERA_AXIS=1`: clicking an era node on Life Map changes the active era; next Lori question comes from that era × meaning cell; arc-gap prioritizes within pool.
- With flag off: zero behavior change; arc-gap-gap-driven Lori behavior (today's mechanism) preserved byte-stable.
- Smoke test: 6 eras × 3 meaning gaps × 2 arc-gap states = 36 question selections produce 36 era-appropriate stems with correct prioritization.
- Live test on Janice narrator: click Adolescence era → next question references "your teenage years" or similar era marker.

**Reversibility:** flag-gated. Off = byte-stable to today's behavior.

---

### Phase 5 — Accordion era-banding (UI restructure)

**Goal:** switch `chronology-accordion.js` primary grouping from year-bands to era-bands with year tiles nested inside.

**Engine support:** `chronology-accordion.js` already has `cr-active-era` class handling and emits `yearGroup.era` tags per item. Phase 5 changes how the rail GROUPS, not what data flows through.

**Files:**

| File | Change |
|---|---|
| `ui/js/chronology-accordion.js` | Restructure render loop: top-level group is era band (Earliest Years 1939–1944, Elementary 1945–1951, etc.). Each era band contains year tiles (1939, 1940, …). Year tiles contain individual fact tiles. |
| `ui/css/chronology-accordion.css` (or wherever CSS lives) | New `.cr-era-band` class with era-color accent. Existing `.cr-year` class becomes nested inside era band. |
| `ui/js/chronology-accordion.js` | Era band header click → expand/collapse era. Year click → expand/collapse year. Tile click → existing fact-detail flow. |
| `server/code/api/routers/chronology_accordion.py` | (Verify response schema already supports era tags; if so, no change. If not, add era field per item.) |

**Active-era highlighting:**
- When `state.session.activeEra` is set (via Life Map click), accordion auto-expands that era band and scrolls to it.
- Click on accordion era band header → `setActiveEra(eraKey)` (same handler as Life Map era click).

**Today strip:**
- Today appears as a thin strip ABOVE all era bands, distinct visual treatment (no expand/collapse — always visible).
- Tile clicks route to today section in Peek memoir.

**Acceptance:**
- Accordion renders 6 era bands + 1 today strip.
- Active era band auto-expanded; others collapsed by default.
- Year tiles nested inside era bands; clicking a year tile expands its facts.
- Era band click syncs to Life Map (same `setActiveEra` call).
- Smoke test on Shatner narrator: birth (1931) lands in Earliest Years band; Star Trek casting (1966) lands in Building Years.

**Reversibility:** non-flag-gated UI restructure. Reversion via the layout commit. Pre-existing year-banded behavior is preserved in git history.

---

### Phase 6 — Life Map mini/popout single-component refactor

**Goal:** one mind-elixir instance rendered at two zoom levels — right-rail mini + Peek-popout — instead of two separate components. Add Today as a non-era marker.

**Files:**

| File | Change |
|---|---|
| `ui/js/life-map.js` | Refactor `_DEFAULT_ERA_DEFS` to expose era nodes as a reusable component. Add `today` as a separate marker (NOT in `_DEFAULT_ERA_DEFS` — sits orthogonal). |
| `ui/lori80.css` (or where Life Map CSS lives) | Two CSS contexts: `.lifemap-mini` (right rail, ~300px wide) and `.lifemap-popout` (Peek view, full panel). Same DOM, different sizing. |
| `ui/hornelore1.0.html` | Both surfaces reference the same `lifeMapContainer` instance — render twice with size class. |
| `ui/js/life-map.js` | Era node click → `setActiveEra` + propagate to all surfaces (mini, popout, accordion). |

**Today marker on Life Map:**
- Visually distinct from era nodes (different color, off-the-spine position).
- Click → `state.session.todayActive = true` → today question pool activates.

**Acceptance:**
- Right-rail mini and popout render the same Life Map data.
- Click on era node in mini = click on era node in popout (single source of truth).
- Today marker present and clickable on both.
- Visual styling: mini fits ~300px wide; popout fills its panel.

**Reversibility:** UI refactor. Pre-existing two-component behavior is preserved in git history.

---

### Phase 7 — Compass-into-Today data migration

**Goal:** migrate `lv80RenderCompass` content into Today's structured surface. Compass retires as a memoir section.

**Files:**

| File | Lines | Change |
|---|---|---|
| `ui/hornelore1.0.html` | `lv80RenderCompass` (~6625) | Function deprecated; renamed to `lv80RenderTodayFromCompass` and re-purposed to populate today section instead of memoir Compass. |
| `ui/hornelore1.0.html` | `lv80BuildMemoirSections` (~6644) | Remove `lv80RenderCompass` from renderer chain. Add `lv80RenderToday` instead (which calls the renamed Compass renderer + new today-content sources). |
| `ui/hornelore1.0.html` | `lv80MapCaptureTypeToMemoirSection` (~6710) | Update mapping: `feeling` type maps to `today` not `the_compass`. Other type mappings unchanged. |

**Today's data sources (after migration):**
- `additionalNotes.unfinishedDreams` → today/reflection
- `additionalNotes.messagesForFutureGenerations` → today/reflection
- `technology.culturalPractices` → today/identity_now
- `pets[]` → today/current_life
- `familyTraditions[]` → today/current_life
- New: any fact tagged `today` via Phase 4 question selection during a session.

**Acceptance:**
- Compass section disappears from memoir Peek.
- Today section renders Compass content, organized by sub-flavor.
- Existing narrator data (e.g., Shatner with Compass content) round-trips cleanly into Today.
- No data loss — all Compass content surfaces in Today.

**Reversibility:** if rolled back, Compass renderer is restored from git; Today renderer falls back to empty placeholder.

---

### Phase 8 — Frame reassignment: Legend Begins → Earliest Years header

**Goal:** retire `lv80RenderLegend` as a separate memoir section. Birth/name/identity content becomes the top tile of Earliest Years.

**Files:**

| File | Lines | Change |
|---|---|---|
| `ui/hornelore1.0.html` | `lv80RenderLegend` (~6500–6516) | Function retires from renderer chain. Logic moves into `lv80RenderEarlyChildhood` as a header-tile preamble. |
| `ui/hornelore1.0.html` | `lv80BuildMemoirSections` (~6644) | Remove `lv80RenderLegend` from chain. Earliest Years renderer (new) replaces the existing Formative-Years-as-second renderer. |
| `ui/hornelore1.0.html` | `lv80RenderFormativeYears` (~6518) | Splits into `lv80RenderEarlyChildhood` (era 0–5, with Legend content as header) and `lv80RenderElementaryYears` (era 6–12). The 7→6 collapse goes away. |

**New renderer set (final memoir build chain):**

```
lv80BuildMemoirSections() = [
  lv80RenderEarlyChildhood,       // 0–5, with Legend birth/identity header
  lv80RenderElementaryYears,      // 6–12
  lv80RenderAdolescence,          // 13–18
  lv80RenderEarlyAdulthood,       // 19–30 (was Crossroads)
  lv80RenderMidlife,              // 31–55 (was Peaks & Valleys)
  lv80RenderLaterLife,            // 56+ (was Current Horizon)
  lv80RenderToday,                // non-era, includes Compass migration
]
```

**Acceptance:**
- Memoir Peek shows 6 era sections + 1 today section (7 total, vs current 6 narrative-arc sections + sometimes 8 meaning buckets).
- Earliest Years section opens with a header tile (birth, name, identity, birth order) — visually distinct from regular era content.
- Legend's content (DOB, birthplace, birth order) is preserved.
- No section labeled "The Legend Begins" exists anywhere in UI.

**Reversibility:** UI refactor. Reversal via git.

---

### Phase 9 — Acceptance tests + verification

**The flagship test (this proves the whole hierarchy works):**

```
GIVEN:
  state.session.activeEra      = "elementary_years"
  state.session.todayActive     = false
  meaning_gap_in_active_era     = "family_relationships"
  arc_gap                       = "turning_point" (climax beat unfilled)
  HORNELORE_ERA_AXIS            = 1

WHEN Lori selects her next question

THEN the question must satisfy ALL THREE of:
  - era-marked: refers to "school years," "ages 6–12," "back when you
    were in elementary," or equivalent age-range marker
  - meaning-aligned: about family or family relationships
  - arc-prioritized: framed toward change / turning point / "something
    that changed after"

EXAMPLE PASSING QUESTION (from ChatGPT's mockup, 2026-04-27):
  "During your school years, was there a moment where something
   changed in your family?"

If this test fails, the era-axis system is not coherent.
Phase 4 flag stays default-off until this passes on three real narrators.
```

**12 phase-bounded acceptance tests:**

```
1. Phase 1 byte-stability: r5h master eval re-runs with rename only,
   produces identical 70/104 score. School_years grep returns zero
   hits in active code paths.

2. Phase 1 migration: persisted narrator with old key auto-migrates.

3. Phase 2 default-off: HORNELORE_TODAY_BUCKET=0 produces zero today
   surface and zero new prompt-composer lines.

4. Phase 2 default-on: HORNELORE_TODAY_BUCKET=1 — today signal fires
   on test phrases ("right now," "these days," "looking back now").

5. Phase 3 question pool: 48 era × meaning cells loaded; selector
   returns era-appropriate stem for (era, meaning) input across all
   non-empty cells.

6. Phase 4 default-off: HORNELORE_ERA_AXIS=0 produces today's
   narrative-arc-gap-driven Lori behavior unchanged.

7. Phase 4 default-on: HORNELORE_ERA_AXIS=1 — clicking Adolescence
   on Life Map produces era-marked Lori question on next turn.

8. Phase 4 arc-gap layering: with arc-gap = "climax," Lori prefers
   turning_points sub-tag stems within active era × meaning cell.

9. Phase 5 accordion era-banding: 6 era bands + 1 today strip render;
   active era auto-expanded; clicking a year tile inside era band
   expands its facts.

10. Phase 6 Life Map sync: clicking era node on right-rail mini =
    clicking era node on popout. Today marker present on both.

11. Phase 7 Compass migration: Shatner's Compass content (pets,
    traditions, unfinished dreams) round-trips into Today section.

12. Phase 8 Legend reassignment: Earliest Years section opens with
    birth/identity header tile. No "Legend Begins" label exists in UI.
```

**Live verification narrators:**
- **Shatner** — has rich Compass content; tests Phase 7 cleanly.
- **Janice** (Horne family) — tests memoir correction round-trip + DOB factual edit per Memoir Correction Rule (cross-WO with FORENSIC-01).
- **Test fixture narrator** — empty narrator; tests empty-state rendering of all 7 sections.

---

## Consolidated file touchpoint table

| File | Phase(s) | Change type |
|---|---|---|
| `ui/js/app.js` | 1 | Rename keys at L5145, L5154 |
| `ui/js/state.js` | 1, 2, 4 | Type comment rename + new today/activeEra session keys |
| `ui/js/interview.js` | 1, 3, 4 | Rename keys + question-pool dispatcher + ERA_PROMPTS rewire |
| `ui/js/bio-builder-family-tree.js` | 1 | Rename keys at L68, L78 + light keyword tuning |
| `ui/js/life-map.js` | 1, 4, 6 | Rename + click handler + single-component refactor + today marker |
| `ui/js/chronology-accordion.js` | 1, 5 | Rename + era-banding restructure + click-sync |
| `ui/css/*.css` (and `ui/lori80.css`) | 5, 6 | Era band styling + Life Map mini/popout sizing |
| `ui/hornelore1.0.html` | 5, 6, 7, 8 | Memoir section refactor + Life Map dual-mount + Compass-into-Today + Legend reassignment |
| `server/code/api/prompt_composer.py` | 2, 4 | Today directive block + era directive line |
| `scripts/archive/run_question_bank_extraction_eval.py` | 1 | `_phase_to_era` mapping rename |
| `data/qa/question_bank_extraction_cases.json` | 1 | Sed `school_years` → `elementary_years` |
| `data/question_pool/era_x_meaning.json` | 3 | NEW — 48 cells |
| `data/question_pool/today_pool.json` | 3 | NEW — 4 sub-flavors |
| `data/question_pool/README.md` | 3 | NEW — authoring conventions |
| **Lorevox mirror** | 1 (post-bank) | Identical rename in `lorevox/ui/js/`, `lorevox/server/`, `lorevox/data/` |

**Total: 13 Hornelore files changed + 3 new files + Lorevox mirror commit.**

---

## Stop conditions

The WO's design is violated and work must HALT for review if any of the following are observed at any phase:

```
STOP if Lori starts ignoring the active era when HORNELORE_ERA_AXIS=1
        — questions are generic, not era-marked.

STOP if arc-gap logic is removed instead of demoted.
        Arc-gap stays alive as priority signal inside the era × meaning
        cell. Removing it loses Lori's story-shaping behavior.

STOP if meaning re-emerges as a top-level memoir display structure.
        Meaning is sub-grouping inside era bands and a question filter.
        Top-level "Turning Points" / "Hard Moments" sections are gone.

STOP if Today gets merged into later_life or any other era.
        Today is orthogonal vantage. A 30-year-old narrator's "today"
        belongs in Today, not in early_adulthood.

STOP if a third axis is introduced (era × meaning × arc-gap as cell
        coordinates instead of selection priority). Cell count must
        stay 6 × 8 = 48, not 288.

STOP if the flagship test fails on any of three live narrators after
        Phase 4 flag flip. Roll back, fix, retest.
```

## Risks

1. **Phase 4 wire is the highest-risk phase.** Replacing Lori's question driver is a real behavioral change. Mitigation: flag-gated; live narrator A/B (Janice on, test narrator off); rollback = single env-var flip.

2. **Question pool content quality.** 48 cells × 3+ stems = 150+ question stems to author. Risk = generic stems that don't actually feel era-specific. Mitigation: review pass with three real narrators (Shatner / Janice / a third) before flag flip; reject any stem that doesn't surface an era-specific marker.

3. **Today signal classifier false positives.** Phrases like "I lived in Bismarck right now" (STT error) could trigger today mode incorrectly. Mitigation: classifier requires confidence ≥0.7 on present-tense markers; ambiguous phrases default to era pool not today.

4. **Compass migration data shape mismatch.** Some narrators may have Compass content in formats the today renderer doesn't expect. Mitigation: Phase 7 includes a one-time validator pass on existing narrator JSONs; logs migration warnings without dropping data.

5. **Accordion era-banding loses year-precision feel.** Year-banded display has been the rail's identity since WO-CR-01. Era-banding may feel coarser to operators used to scanning by year. Mitigation: year tiles still visible inside each era band; collapsed era band still shows year range in header ("Building Years · 1962–1986").

6. **Lorevox promotion timing.** If Hornelore lands phases 1–9 over multiple sessions, Lorevox sits at the old taxonomy until promotion. Mitigation: Phase 1 (rename) promotes early as a clean atomic commit; phases 2–8 promote together as a feature commit once Hornelore acceptance tests pass.

---

## Sequencing decisions

```
Phase 1 (rename)        → land first, no flag, byte-stable
Phase 2 (today scaffold) → land second, flag-gated default-off
Phase 3 (question pool)  → land third, content-only addition
Phase 4 (era wire)       → land fourth, flag-gated default-off
Phase 5 (accordion)      → land fifth, UI restructure (no flag)
Phase 6 (Life Map)       → land sixth, UI refactor (no flag)
Phase 7 (Compass→Today)  → land seventh, data migration (no flag)
Phase 8 (Legend → header) → land eighth, UI refactor (no flag)
Phase 9 (acceptance)      → run after Phase 8 with all flags on
```

**Phase 4 flag flip is the green-light moment.** Until then, default behavior is byte-stable to today's narrative-arc-gap-driven Lori. Phase 4 flip activates the era × meaning wire with arc-gap layering.

**Block on FORENSIC-01 (accordion restoration).** Phase 5 presupposes the accordion is mounted as the persistent narrator-room rail. If WO-ACCORDION-TIMELINE-FORENSIC-01 hasn't landed Phase 1 (forensic) + Phase 2 (restore mount), Phase 5 of THIS WO has nothing to restructure.

**Each phase reports the standard audit block before proceeding** — pass count, v2/v3 deltas, mnw, named flips, and (for Phase 4 onward) Lori-question-quality smoke on the three live narrators.

---

## Lorevox promotion notes

Once this WO closes in Hornelore (all 12 acceptance tests pass; Phase 4 flag default-on for ≥1 week without rollback), promote to Lorevox in two atomic commits:

```
Commit A — Lorevox era taxonomy alignment
  - Apply Phase 1 rename to lorevox/ui/js/ (5 files)
  - Apply Phase 1 rename to lorevox/server/code/ (1 file if any era keys
    are hardcoded server-side; verify via grep)
  - Apply Phase 1 rename to lorevox/data/ (any era-keyed test fixtures)

Commit B — Lorevox era × meaning + today + UI restructure
  - Mirror Phases 2–8 changes
  - Mirror new data/question_pool/ JSONs
  - Mirror UI restructure (memoir, Life Map, accordion, prompt composer)
  - Run Lorevox boot test before push (4 health endpoints)
```

The lab/gold rule: Hornelore proves it; Lorevox inherits it. No parity backport during development. No parallel-build.

---

## What this WO does NOT do

- Does not modify the schema for facts, photos, documents, or memoir content. Era and meaning_tag fields already exist via SECTION-EFFECT Phase 2 + Phase A meaning-tagging.
- Does not change the kinship-projection matrix in `bio-builder-family-tree.js` (no era splits or merges; matrix preserved).
- Does not touch the extraction pipeline (extract.py, SPANTAG, BINDING). The era × meaning question pool is consumer of fact metadata, not a producer.
- Does not remove the narrative-arc beat tagging mechanism. Demoted to priority signal; not deleted.
- Does not introduce a third axis. Era × Meaning is the cell grid; arc-gap is selection priority; today is orthogonal vantage. 6 × 8 = 48 cells; not 288.
- Does not change Lorevox's external behavior until promotion commits land separately.

---

## Cross-references

- Companion WO: `WO-ACCORDION-TIMELINE-FORENSIC-01_Spec.md` (accordion restoration; Phase 5 of this WO depends on it)
- Architecture spec: `docs/specs/LOREVOX-EXTRACTOR-ARCHITECTURE-v1.md` (era is a Control Layer concept; this WO doesn't change architecture, only how era is consumed)
- Research note: `docs/research/nested-extraction-architecture.md` (NESTED-BINDING is parallel work on the extraction side; era × meaning is the consumer side)
- Existing era-prompt mechanism: `ui/js/interview.js:135–142` (`ERA_PROMPTS`)
- Existing era injection: `server/code/api/prompt_composer.py:722, 779` (era line in runtime block)
- Existing meaning-tag pipeline: Phase A of memoir promotion, emits `meaning_tags` and `narrative_role` on facts
- 6-arc memoir frames being retired: `ui/hornelore1.0.html:6644` (`lv80BuildMemoirSections`)
- 8-bucket meaning sections being demoted: `ui/hornelore1.0.html:7183` (`_LV80_MEMOIR_SECTIONS`)

---

## Final directive

```
Implement era-driven system.

Era defines structure.
Meaning refines questions.
Arc-gap prioritizes.
Today handles present + reflection.

Do not create competing systems.
Do not collapse layers.
Do not add a third axis.

The flagship test is the proof:
  era × meaning × arc-gap → one coherent question.
  Pass it on three real narrators or roll back.
```

---

## Visual reference

ChatGPT's UI mockup (`ui/mockups/hornelore-era-axis-architecture.html`, 2026-04-27) is the visual lock for this WO. It demonstrates:

- **Left rail (timeline):** era-banded (Earliest Years / Early School Years / Adolescence) with year tiles inside each band (1939 / 1952, 1956 / 1962). This is the Phase 5 target shape.
- **Center stage:** Active Focus header showing era + meaning ("Early School Years · Family & Relationships"). Lori bubble demonstrates the flagship triple-axis question: *"During your school years, was there a moment where something changed in your family?"* — elementary_years × family_relationships × turning_point.
- **Right rail (Life Map):** 6 era nodes (Earliest Years / Early School Years (active) / Adolescence / Coming of Age / Building Years / Later Years) plus a separate "Today" node below. This is the Phase 6 target shape.
- **Floating Peek at Memoir:** paper-feel popout with sample memoir text. This is the Phase 7+8 target output.

The mockup confirms the architecture is coherent end-to-end across all four UI surfaces.

---

## Revision history

| Date | What changed |
|---|---|
| 2026-04-27 | Created. Captures three-agent convergence on Era × Meaning × Arc-Gap × Today architecture. 9 phases, 13 file touchpoints + 3 new files, 12 acceptance tests, Lorevox promotion plan. Phase 4 (Lori question-selection wire) is the green-light moment. |
| 2026-04-27 (later) | Folded ChatGPT's tightening pass: added flagship triple-axis acceptance test (era × meaning × arc-gap composite), Stop Conditions section, Final Directive closing block, Visual Reference section pointing to ChatGPT's mockup. ChatGPT signed off on the snake_case=elementary_years / warm-label=Early School Years (6–12) compromise. WO is locked for execution. |
