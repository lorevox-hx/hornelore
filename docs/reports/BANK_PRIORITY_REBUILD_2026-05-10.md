# Bank Priority Rebuild — Research Synthesis 2026-05-10

**Status:** SPEC. No code changes in this document. Awaiting Chris signoff.

**Why it exists:** The Fort Ord one-shot exposed that the follow-up bank
is treating itself like a spell-check queue (priority 1 = "did I get
Army Security Agency spelled right?") instead of an oral-history
listener-aid. Chris asked for a research review BEFORE more patching.

**Source documents read tonight:**
- `WO-LORI-ACTIVE-LISTENING-01_Spec.md` — one-question discipline
- `WO-LORI-SENTENCE-DIAGRAM-RESPONSE-01_Spec.md` — anchor selection
  (Alshenqeeti 2014 grounding: "always seek the particular")
- `WO-NARRATIVE-CUE-LIBRARY-01_Spec.md` — 12 locked cue types + safe
  follow-ups + forbidden moves
- `docs/voice_models/VOICE_LIBRARY_v1.md` — seven voices + Anchor
  Priority Table at §10A + cross-voice patterns at §10
- `docs/research/references.md` — research-to-WO mapping
- 2026-05-10 Kent harness + Fort Ord one-shot evidence

---

## 1. What the research says about good follow-ups

**Alshenqeeti (2014), via WO-LORI-SENTENCE-DIAGRAM-RESPONSE-01:**

> "Always seek the particular." (Richards 2003)
>
> "The shorter the interviewer's questions and the longer the
> subject's answers, the better an interview is." (Barbour & Schostak 2005)
>
> "As interviews are interactive, interviewers can press for complete,
> clear answers and can probe into any emerging topics."

Three load-bearing principles:
1. **Seek the particular.** Reflect the *specific concrete element*
   the narrator just said, not the abstract category.
2. **Short questions, long answers.** Lori speaks less; narrator
   speaks more.
3. **Probe emerging topics.** When narrator surfaces a detail, follow
   that thread — do not pivot back to a system agenda.

**Voice Library v1, §10 cross-voice patterns:**

> "Named heirlooms as the strongest anchors. Mason jar of nickels,
> oak trunk, silk wedding ribbon, abacus, turquoise stone, weaving
> batten, prayer shawl, ginger jar of gold coins, old metate, the
> Bible with a hundred years of births. **Highest anchor priority in
> WO-LORI-SENTENCE-DIAGRAM-RESPONSE-01.**"

**Voice Library v1, §10A — Anchor Priority Table (canonical):**

| Priority | Anchor type | Preferred | NOT preferred (abstract) |
|---|---|---|---|
| **1** | Named heirloom or named individual | "Mason jar" | poverty |
| 2 | Sensory-first detail (smell/texture/sound/weather/taste) | "yeast smell" | heritage |
| 3 | Coded survival language (reflect surface only, no translate) | "never told" | secret identity |
| 4 | Concrete object | "the clerk wrote Smith" | assimilation trauma |
| 5 | Place | "October arrival" | immigration status |
| 6 | Action | "father's hands" | hard life |
| 7 | Feeling named by narrator | "scared" | childhood trauma |
| 8 | Abstract summary | (last resort) | (any) |

**Voice Library v1, §11 locked principles:**

> "The extractor extracts FACTS. Lori preserves VOICE. These are
> different jobs."

This is the key architecture distinction my bank has been violating:
spelling-confirm is an extractor-field concern (fact integrity).
Active-listening follow-ups are a voice-preservation concern (story
continuity). My bank conflated them and put spelling-confirm at
priority 1.

---

## 2. What's wrong with the current bank

### Bug A — Wrong priority 1

Current model:
```
priority 1 = fragile-name spelling confirmation
priority 2 = communication/logistics
priority 3 = role transition
priority 4 = relationship/personality (BANK ONLY)
priority 5 = daily life (BANK ONLY)
priority 6 = medical/family (BANK ONLY)
```

Research says priority 1 should be **named heirloom / named individual
reflection** — a CONTENT question, not a META question. "What was
that meal-ticket responsibility actually like?" is priority 1.
"Did I get Army Security Agency spelled right?" is priority N
(LOW) and only when uncertainty marker fires.

### Bug B — Cue types are extractor-shaped, not oral-history-shaped

My current intents:
```
fragile_name_confirm_<name>
fragile_name_confirm_correction
communication_with_partner_overseas
spouse_travel_paperwork
role_pivot_photography
role_pivot_courier_bridge
career_choice_under_constraint
photography_work
working_relationship_boss
rank_asymmetry_relationship
daily_life_off_duty
medical_family_care
birth_paperwork
medical_career
education_to_profession
```

These are bespoke intent labels invented for Kent's specific arc.
The Narrative Cue Library (already in this codebase, parked
implementation-side) defines 12 LOCKED cue types from oral-history
methodology:

```
parent_character    elder_keeper       journey_arrival
home_place          work_survival      hearth_food
object_keepsake     language_name      identity_between
hard_times          hidden_custom      legacy_wisdom
```

Each cue_type carries `safe_followups` (one-question candidates),
`forbidden_moves` (guardrails), `scene_anchor_dimensions`, and
`operator_extract_hints` (NOT shown to runtime).

My bank reinvented a different, shallower vocabulary. The right
move is to **adopt the Cue Library's 12 cue types and map my
existing intents into them.**

### Bug C — Receipt is a sentence-fragment salad, not active listening

Current chronological-anchor extractor produces:

> "You went from Fort Ord to California, then Fargo, Sergeant Miller,
> Sergeant Mueller, GED, Janice, and Nike Ajax."

That's not a receipt — it's a noun-phrase concatenation with the
chronology reversed (Fort Ord came AFTER Stanley→Fargo, not before).

Research says the receipt should reflect ONE concrete particular
("the meal tickets" / "the M1 expert qualification") and use it
as the door-opener. Not list every proper noun.

### Bug D — No risk-level gating

Cue Library defines `risk_level: low | medium | sensitive |
safety_override`. `hidden_custom` is `sensitive` — Lori asks
zero questions when this fires. `hearth_food` is `low` — Lori
asks freely. My current bank has no risk-level concept; every
banked door is fair game. Crypto-Jewish "we never told outsiders"
would get banked as fragile-name-confirm-something rather than
recognized as `sensitive` and respected with silence.

---

## 3. The right priority model — REVISED 2026-05-10 per Chris's three signoff revisions

Three revisions to v1 of this synthesis, per Chris:

1. **Split record-critical corrections from generic spelling cleanup.** A
   self-correction with a record-critical fact ("not Lansdale,
   Landstuhl"; "his name was Schmick, not Smith") is IMMEDIATE
   (Tier 1B). Bare clear-institutional-name spelling cleanup
   ("Army Security Agency" / "Nike Ajax" said with confidence) is
   Tier N — NEVER immediate.
2. **Sensory-first detail does NOT win immediate by default. It banks.**
   Per Chris: "too much sensory. The first bank was OK with its
   direction but don't return to the sensory questions especially
   long narrations." For adult-competence narrators (Kent, most
   military / immigrant / labor-history voices), mechanism /
   responsibility / role-transition / practical-logistics beat
   sensory UNLESS the narrator dwells on the sensory detail
   themselves. The narrator-overlay concept (§3.5 below) controls
   this.
3. **"Named particular" is story-weighted, not just "any named
   person."** Meal tickets (mentioned 3x with development +
   conductor confrontation + oatmeal dispute + "first Army
   responsibility") BEATS Sergeant Miller/Mueller (mentioned once
   with uncertainty). Story-weight signals: repetition count,
   sentence-development depth, narrator's own emphasis ("that
   mattered to me", "still stands out"), preceding/following
   sentence count developing the entity.

### Tier S — Sacred (zero questions, never auto-flush)

| Priority | Cue type | Why |
|---|---|---|
| S1 | `hidden_custom` (sensitive) — coded survival language | Crypto-Jewish "remember but never tell" — Lori asks zero |
| S2 | `sacred_silence` (suppression overlay) | Native ritual, kiva-protected memory |

These never become bank-flush questions. They sit in operator-only
review.

### Tier 1 — Story-weighted named particular (immediate)

| Priority | Anchor type | Source |
|---|---|---|
| 1A | **Story-weighted named particular** the narrator just said | Voice Library §10A row 1, weighted by repetition + development |
| 1B | **Record-critical self-correction** ("not Lansdale, was Landstuhl"; "his name was Schmick, not Smith") | Memoir record AT RISK if narrator's correction is lost |
| 1C | **Genuinely fragile name + uncertainty marker** ("Schmick, but I would not swear to that") | Foreign / hospital / record-critical name + explicit uncertainty |

**Tier 1 is the ONLY immediate-ask tier when one is available.**
Lori reflects the named particular and asks ONE concrete question
about it. The cue type defines the question shape via
`safe_followups`.

**Story-weight scoring for Tier 1A** (computed from utterance-frame
clauses + narrator text):

```
repetition_count    weight ×3 if anchor appears ≥3 times in turn
                    weight ×2 if appears 2 times
                    weight ×1 if appears once
development_depth   +2 if 2+ sentences develop the anchor
                    +1 if 1 sentence develops it
                    0 if anchor is in a list / by-name only
narrator_emphasis   +2 if narrator says "that mattered to me",
                       "still stands out", "I want it preserved",
                       "that was when..." near the anchor
                    +1 if narrator returns to the anchor at a later
                       sentence in the same turn
                    0 otherwise
sentence_count_around  +1 if anchor has ≥3 sentences in its semantic
                       neighborhood (not just listed)
```

Highest-scoring named particular wins Tier 1A. Other named
particulars from the turn bank as Tier 4-5.

For Kent's Fort Ord monologue, the story-weighted scoring on
candidate named particulars produces:

| Candidate | Repetition | Development | Emphasis | Neighborhood | Total |
|---|---:|---:|---:|---:|---:|
| meal tickets | ×3 | +2 (conductor, oatmeal, "first Army responsibility") | +2 ("that was my first Army responsibility, before Fort Ord") | +1 | **9** |
| M1 expert | ×1 | +1 ("not just luck. It showed I could follow instruction") | +2 ("that mattered to me") | 0 | **4** |
| Sergeant Miller/Mueller | ×1 | 0 (one sentence) | 0 | 0 | **1** |
| Army Security Agency | ×3 | +1 (development is the wait + pivot) | 0 | 0 | **4** |

**Meal tickets wins Tier 1A.** Lori reflects meal tickets, asks
the cue-library `work_survival` follow-up. Sergeant Miller/Mueller
goes to Tier 1C (uncertainty present, low story-weight) — banked,
flushed late only if no higher-tier door.

### Tier 2 — Concrete object / place / action / coded survival (immediate or bank, NARRATOR-OVERLAY GATED)

| Priority | Anchor type | Cue types |
|---|---|---|
| 2A | Coded survival language (reflect surface only) | `coded_survival_language` (suppression overlay) |
| 2B | Concrete object | `object_keepsake` |
| 2C | Place | `home_place`, `journey_arrival` |
| 2D | Action / event mechanism | `work_survival`, `journey_arrival` |

**Tier 2 wins immediate when Tier 1 has no entries AND narrator-
overlay (§3.5) permits.** For Kent (adult-competence), Tier 2D
(action / mechanism) is the strongest sub-tier. For sensory-first
narrators (Voice 1 Prairie / Voice 4 California-hearth), Tier 2A/B
get elevated.

**Sensory anchors (smell / texture / sound / weather / taste) are
DEMOTED to Tier 5 by default.** They bank, never auto-immediate
unless overlay says otherwise. Per Chris's 2026-05-10 lock: don't
return to sensory questions especially on long narrations.

### Tier 3 — Logistics / mechanism (bank, immediate only when narrator-cued)

| Priority | Cue type | Maps from current intent |
|---|---|---|
| 3A | `journey_arrival` (sub: communication-from-overseas) | `communication_with_partner_overseas` |
| 3B | `journey_arrival` (sub: travel-paperwork-housing) | `spouse_travel_paperwork` |
| 3C | `work_survival` (sub: role-transition-mechanism) | `role_pivot_*` |
| 3D | `work_survival` (sub: career-choice-under-constraint) | `career_choice_under_constraint` |

Banks unless the narrator explicitly cues the question (e.g. "1959,
not like today where you text"). If cued, gets promoted to
IMMEDIATE — even over Tier 2 — because the narrator opened the
specific door.

### Tier 4 — Relationship / role (BANK ONLY)

| Priority | Cue type | Maps from current intent |
|---|---|---|
| 4A | `parent_character` (rank asymmetry, working relationship) | `rank_asymmetry_relationship` |
| 4B | `elder_keeper` (mentor / boss as memory-keeper) | `working_relationship_boss` |

Per Chris's locked rule: rank-asymmetry "private working as photographer
for a General" is a banked door, never immediate. Asked LATER on
flush trigger.

### Tier 5 — Daily life / sensory texture (BANK ONLY)

`home_place`, `hearth_food` texture, sensory anchors (smell /
texture / sound / weather / taste). Per Chris's 2026-05-10 lock:
sensory NEVER auto-immediate without explicit overlay permission.
Banks for later, used sparingly even in flush.

### Tier 6 — Medical / family events (BANK ONLY, careful)

`hard_times` (sub: medical / family-event). Premature birth, CP,
illness. Asked carefully later, never jammed into a fragile-name
turn.

### Tier 7 — Reflection / feeling (only if narrator opens it)

`legacy_wisdom`, `identity_between`. Only fires when narrator says
"looking back" / "I tell my grandkids" / "I am proud and sad at
once" / etc.

### Tier N (LOW) — Mechanical record cleanup (BANK ONLY, lowest urgency)

| Priority | Trigger | Action |
|---|---|---|
| N1 | Foreign-language place name on first appearance WITHOUT correction or uncertainty marker | Bank as `record_correction_pending`. NEVER asked immediately. Auto-flushed only at end-of-session record-cleanup turn or operator click. |
| N2 | Clear institutional name said with confidence (Army Security Agency, Nike Ajax, Fort Ord, Stanley, Fargo, Bismarck) | Do NOT bank as fragile-confirm. Only stored as factual-anchor metadata for the operator review surface — NEVER surfaced to narrator as a spelling question. |
| N3 | Narrator self-correction on a non-record-critical anchor (e.g., "actually it was Tuesday, not Monday") | Bank low-priority; only flushed at session end. |

**Tier N is record-cleanup, not active listening.** What was
priority 1 in the broken model lives here.

## 3.5. Narrator overlay rules

**Per Chris's 2026-05-10 revision:** the priority model has a
narrator-overlay layer that adjusts which Tier 2 sub-tier wins
immediate when no Tier 1 fires.

### Adult-competence overlay (Kent, most military/labor narrators)

```
Strongest immediate door:  Tier 1A (story-weighted named particular —
                                    object-of-responsibility / role-pivot anchor)
                           Tier 2D (action / mechanism)
                           Tier 3D (career choice under constraint)
                           Tier 3C (role transition)

Weakest immediate door:    Tier 2A (coded survival — only when narrator
                                    explicitly volunteers)
                           Tier 5 (sensory) — DEMOTED, banked only

Narrator-emphasis signal:  responsibility, decision, pivot, achievement,
                           tested, sorted, qualified, scored, mattered

Cue family preference:     work_survival, journey_arrival, identity_between
```

#### LOCKED PRODUCT RULE FOR KENT — 2026-05-10 Chris signoff

**For Kent / adult-competence overlay, sensory questions are
BANK-ONLY unless Kent himself clearly wants to stay with sensory
detail.** Even though the research says sensory-first details can
be high-value in some oral histories, Kent has already told us
that for him this feels wrong.

For Kent specifically:

```
Meal-ticket responsibility   BEATS  oatmeal smell
M1 expert qualification      BEATS  rifle sound
ASA-vs-Nike decision         BEATS  barracks smell
Janice communication logistics  BEATS  "what was Germany like?"
Photography role transition  BEATS  Kaiserslautern atmosphere
```

This is the locked product rule. Code enforces it via the
`adult_competence` overlay sensory-demotion logic. The override
("Kent himself wants sensory detail") fires only when Kent's own
turn explicitly dwells on a sensory anchor for ≥2 sentences with
narrator-emphasis ("I can still smell..." / "the smell of X always
brings back...") — not just because the narrator mentioned a smell
in passing.

**Acceptance criterion:** the Fort Ord one-shot scorer must FAIL
the old chronological-list / spelling-confirm output and PASS the
target meal-ticket / sorting-point response. The scorer is the
mechanical lock; this product rule is its rationale.

### Hearth/sensory-first overlay (Voice 1 Prairie, Voice 4 California-hearth)

```
Strongest immediate door:  Tier 1A named heirloom (often a domestic
                                 object — yeast crock, oak trunk, ginger jar)
                           Tier 2A coded language
                           Tier 2B concrete object

Weakest immediate door:    Tier 3 (mechanism) — banked unless cued

Narrator-emphasis signal:  smell, taste, kitchen, hands, ribbon, jar,
                           Sunday, Christmas, recipe, smell-of, taste-of

Cue family preference:     hearth_food, object_keepsake, parent_character,
                           home_place
```

### Shield-overlay (Voice 7 Crypto-Jewish, suppression-marker active)

```
Strongest response:        Tier S — zero questions
                           Reflective acknowledgment, no probe
                           Operator-only Review Queue

Weakest response:          ANY direct question about the protected
                           material

Cue family preference:     hidden_custom, sacred_silence, protective_health_language
```

### Default overlay (no profile match)

```
Strongest immediate door:  Tier 1A story-weighted named particular
                           Tier 2D action / mechanism

Reasonable next:           Tier 3 logistics if narrator-cued
                           Tier 2C place

Banked:                    Tier 5 sensory, Tier 4 relationship,
                           Tier 6 medical
```

### How the overlay is selected

Operator-side narrator-style setting at session start (extends
the existing `session_language_mode` pin pattern):

```
profile_json.narrator_voice_overlay =
    "adult_competence"     // Kent, Marvin, military/labor
    "hearth_sensory"       // Janice (likely), prairie/recipe-rich
    "shield_protected"     // Crypto-Jewish, sacred-silence narrators
    "default"              // unknown / mixed
```

When unset, defaults to "default" (story-weighted named particular
+ action/mechanism). The overlay does NOT change cue-library
content — it changes WHICH Tier 2 sub-tier and WHICH cue family
gets promoted to immediate when no Tier 1 fires.

For tomorrow's Kent session: pin `narrator_voice_overlay =
"adult_competence"` on Kent's profile. The hardcoded UUID lock
already exists for Spanish — same posture for the overlay.

## 3.6. Self-correction split (per Chris's revision 1)

The previous v1 of this synthesis conflated two different self-
correction cases. They split:

### Tier 1B — Record-critical correction (IMMEDIATE)

Triggers ALL of:
- Self-correction pattern matched: "not X, was Y" / "actually it
  was Y" / "I meant Y"
- Y is a foreign / hospital / base / unit / person-with-rank /
  date-or-year / record-critical name
- Y appears as multi-word OR matches the TIER A canonical fragile-
  name set OR ≥7 chars uppercase-start

Examples:
- "It was not Lansdale Army Hospital. It was Landstuhl Air Force
  Hospital." → IMMEDIATE confirm Landstuhl
- "His name was Schmick, not Smith." → IMMEDIATE confirm Schmick
- "Not 1958, it was 1959 when I shipped." → IMMEDIATE confirm 1959

### Tier N3 — Generic correction cleanup (BANK ONLY)

Self-correction on a non-record-critical anchor:
- "Actually it was Tuesday, not Monday." → bank
- "I went to Fargo — I mean Bismarck." (common American place) →
  bank only if narrator volunteers uncertainty about it
- Common-word false positives ("not just thinking, it was the
  Army taking…") → REJECTED via blocklist (already implemented)

### How the detector decides

```python
def classify_correction(self_correction_match) -> "tier_1b" | "tier_n3" | None:
    corrected = m.group(2)  # the "Y" side
    if not corrected or len(corrected) < 3:
        return None
    if corrected.lower() in _SELF_CORRECTION_VALUE_BLOCKLIST:
        return None
    if corrected.lower() in _FRAGILE_NAMES_TIER_A:
        return "tier_1b"  # foreign / record-critical
    if _is_multiword_proper_noun(corrected):
        return "tier_1b"  # multi-word name = likely record-critical
    if _is_year_or_date(corrected):
        return "tier_1b"  # year corrections matter for memoir
    return "tier_n3"  # bank, low priority
```

So Lansdale → Landstuhl correction stays IMMEDIATE. Bare clear-
institutional-name "Army Security Agency" without correction goes
Tier N (BANK ONLY, never asked).

---

## 4. What this would have produced on Kent's Fort Ord monologue

Re-running the 2,401-word Fort Ord monologue mentally through the
revised priority model with the **adult-competence overlay** active:

**Anchor candidates from utterance-frame:**

| Candidate | Story-weight score | Tier verdict |
|---|---:|---|
| **the meal tickets** | 9 | **Tier 1A** ← wins immediate |
| Army Security Agency (in pivot context) | 4 | Tier 3D (career-choice) — banks |
| M1 expert qualification | 4 | Tier 2D (action/mechanism) — banks |
| Sergeant Miller/Mueller (uncertain) | 1 | Tier 1C — banks (story-weight too low for immediate) |
| Stanley / Fargo / Bismarck / Fort Ord | n/a — clear institutional | Tier N (factual anchor metadata only) |
| barracks smells (wool blankets, floor polish) | n/a — adult-competence overlay demotes sensory | Tier 5 — banked, never auto-immediate |

**Tier 1A wins immediate.** Meal tickets has story-weight 9 (×3
repetition, +2 development across conductor/oatmeal/"first Army
responsibility", +2 narrator emphasis "still stands out", +1
neighborhood). Sergeant Miller/Mueller's story-weight is 1 — banks
to Tier 1C, asked late only if no higher-tier door.

**Adult-competence overlay confirms** that Tier 2D action/mechanism
(M1, GED, ASA-vs-Nike) is the strongest banked door, and sensory
texture (Tier 5) banks but does NOT auto-immediate.

**Cue type:** `work_survival`.

**Lori's correct immediate response (one of these target shapes
per Chris's two acceptable variants, 2026-05-10):**

Variant A — meal-tickets anchor (story-weighted Tier 1A):
> "You said the Army had already trusted you with meal tickets
> before basic training — accounting for meals on a trainload of
> recruits and pushing back when the oatmeal was bad. Then Fort
> Ord became the place where they tested, trained, and sorted you
> toward the next path. What happened when basic training started?"

Variant B — sorting-point anchor (Tier 2D action/mechanism summary):
> "You described Fort Ord as the sorting point: basic training,
> GED testing, M1 expert qualification, and then the choice
> between waiting for Army Security Agency or moving into Nike
> Ajax/Nike Hercules. How did they explain that choice to you?"

This is:
- **One reflection** anchored to story-weighted detail
- **One question** that's mechanism/responsibility/role-transition,
  NOT sensory and NOT spelling-confirm
- **Zero spelling-confirms** on Army Security Agency / Nike Ajax /
  Fort Ord — all stay as factual anchors only
- **Zero abstract summaries** — both variants ground in Kent's
  own framing ("trusted you with meal tickets" / "sorting point")

**Bank fills with these (priority order):**

```
Tier 1B: (none — no record-critical self-corrections in this turn)
Tier 1C: Sergeant Miller/Mueller name (uncertain, low story-weight)
         — flush at end if no higher-tier
Tier 2D: M1 expert qualification — concrete-achievement, banked
Tier 3A: communication with home/Janice "1959 not like today" —
         high priority because narrator literally cued it
Tier 3D: career-choice-under-constraint (ASA-vs-Nike) — banked
         (didn't win immediate because Tier 1A had a story-weighted
         winner; Tier 3D becomes a strong flush candidate)
Tier 4A: drill-instructor relationship — banked, never immediate
Tier 5:  Fort Ord barracks sensory ("wool blankets and floor
         polish") — DEMOTED per adult-competence overlay; banked
         only, won't be flushed for Kent unless he opens sensory
         himself
Tier 5:  Fort Ord daily routine — texture-bank
Tier N:  Stanley/Fargo/Bismarck/Fort Ord/Army Security Agency/
         Nike Ajax/Nike Hercules/32nd Brigade — factual anchors
         metadata only, NEVER surfaced as spelling-confirm
```

**Bank flush on later "yeah, that's right" or "what else?" picks
the highest-Tier unanswered, respecting overlay:**

> "I want to come back to one detail you mentioned earlier. How did
> you and Janice keep in touch in 1959 — letters, phone calls,
> telegrams?" (Tier 3A, narrator-cued, highest unanswered)

OR (if no narrator-cued Tier 3 entry):

> "I want to come back to one detail you mentioned earlier. How did
> they explain the choice between waiting for Army Security Agency
> and moving into Nike Ajax/Nike Hercules?" (Tier 3D, career-choice)

NEVER (per adult-competence overlay):

> "What did the barracks smell like?" (Tier 5 sensory, BANKED but
> not auto-flushed for Kent)

NEVER (per Tier N rule):

> "Did I get Army Security Agency spelled right?" (Tier N, never
> surfaced)

The overlay is what guarantees Lori sounds like an oral-historian
of adult-competence narratives, not a sensory-probe interviewer.

---

## 5. The migration plan (no code yet — spec only)

### Phase 1 — Adopt Cue Library cue_types in the bank schema

- Replace `intent` field's free-form labels with cue-library
  `cue_type` enum + an optional `cue_subtype` for finer-grained
  Kent-specific patterns (e.g., `cue_type=work_survival,
  cue_subtype=career-choice-under-constraint`).
- Keep `triggering_anchor` and `why_it_matters` — those remain.
- Add `risk_level` (low/medium/sensitive/safety_override).
- Add `tier` (S, 1, 2, 3, 4, 5, 6, 7, N) — the priority tier.
- Maintain backward-compat: existing intent labels migrate via a
  one-time mapping table.

### Phase 2 — Replace door-detector with cue-library trigger matching

- Drop my hand-coded TIER A / TIER B name lists for spelling-confirm
  immediate doors. Replace with:
  - Tier 1A detector reading utterance_frame for named entities
    + named heirlooms (using §10A priority order)
  - Tier 1C detector reading utterance_frame for uncertainty
    markers near foreign-name candidates
  - Tier 1B detector reading for self-correction patterns (the
    only piece of my current code that survives intact)
- For Tier 2-7: load `data/lori/narrative_cue_library.json`
  (already a planned artifact in WO-NARRATIVE-CUE-LIBRARY-01) and
  match trigger_terms against narrator text. The library carries
  the safe_followups; my code just selects the right one.
- Spelling-confirm becomes Tier N — only fires when narrator
  self-corrects OR uncertainty marker is within 200 chars of a
  foreign-name token.

### Phase 3 — Replace receipt composer with named-particular reflection

- Drop the chronological-anchor list ("You went from X to Y, then Z").
- Replace with **named-particular reflection**:
  > "You said {anchor}: {brief detail}. {one question from cue library}"
- The anchor comes from utterance-frame Tier 1 picker.
- The question comes from cue library `safe_followups`, NOT from
  the LLM and NOT from a generated chronological summary.
- Length target: 35-60 words (per ACTIVE-LISTENING-01 ≤ 90, target
  ≤ 55).

### Phase 4 — Bank-flush selection respects tier order, not just priority number

- Current code: `ORDER BY priority ASC, triggering_turn_index DESC`.
- New: ORDER BY tier (1B → 1A → 1C → 3A-cued → 3B-cued → 2A → 2C →
  3C → 3D → 4A → 4B → 5 → 6 → 7 → N), then most-recently-banked
  among ties.
- Tier S entries are NEVER selected for flush — they live in the
  operator review queue only.

### Phase 5 — Risk-level routing

- `safety_override` cue → defer to safety classifier (already exists).
- `sensitive` cue → flush composer outputs zero questions; only
  reflective acknowledgment.
- `medium` cue → flush asks with permission shape ("would you like
  to stay with that, or…").
- `low` cue → flush asks directly per safe_followups.

### Phase 6 — Update tests

- The 9 KentStressTestLongMonologueTests already test correct
  shape — most stay valid.
- Add tests asserting Tier 1A wins over Tier N when both fire
  (named heirloom > spelling-confirm).
- Add cue-library trigger-match tests using the seed cue records
  from WO-NARRATIVE-CUE-LIBRARY-01.

---

## 6. Acceptance gates before the rebuild ships

Before I touch code:

- [ ] Chris reviews this synthesis doc and signs off on the tier
      model + named-particular receipt direction + Cue Library
      adoption.
- [ ] Chris confirms the Fort Ord example response shape (§4) is
      what he wants Lori to actually say.
- [ ] Chris approves the migration phasing OR revises it.
- [ ] (Optional) ChatGPT reviews this doc as triangulation.

After signoff, the rebuild lands as a single WO-LORI-WITNESS-FOLLOWUP-
BANK-02 (or rename/extend the existing 01) with phased commits and
re-run the Fort Ord one-shot at each phase boundary.

---

## 7. What to DO RIGHT NOW (no code)

Park the current bank patches as-landed. They're behaviorally
correct on the seven hard gates Chris specified earlier
(zero Spanish, floor-hold deterministic, etc.) and won't degrade
Kent's session if used carefully. The receipt-noise + spelling-
confirm priority issues are real but cosmetic (don't break Kent's
trust the way Spanglish would).

For the morning Kent session if Chris still wants to try:
- Operator-side workflow doc `KENT_FLOOR_CONTROL_2026-05-10.md` is
  the active mitigation: don't press Send until Kent finishes a
  chapter; keep chapters under 5-10 min / 700-1500 words.
- Lori will produce stitched chronological receipts and may
  occasionally ask "Did I get X spelled right?" — these are
  awkward but not damaging if operator coaches Kent through.

For the proper rebuild: this synthesis doc gates it. Once Chris
signs off on the tier model + Cue Library adoption, the rebuild is
~6 phased commits across one focused session, not the 8-hour
patch-bounce we've been doing.

---

## 8. Bumper sticker

**Old bank:** spell-check queue. Priority 1 = "did I get the name
right?" — a META question that breaks active-listening flow.

**New bank:** oral-history listener-aid. Priority 1 = "what about
the named-particular detail you just gave me?" — a CONTENT question
that follows the narrator's own thread.

The extractor extracts FACTS. Lori preserves VOICE. The bank stores
DOORS, not spellings.
