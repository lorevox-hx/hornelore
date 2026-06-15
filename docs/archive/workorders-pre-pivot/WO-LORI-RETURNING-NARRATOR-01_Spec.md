# WO-LORI-RETURNING-NARRATOR-01 — Welcome-back continuity for returning narrators

**Status:** PARKED (active design, not yet implemented)
**Origin:** 2026-05-04 — Chris (parent-session readiness work). Older narrators may not remember coming back; the system needs to do the remembering work memory used to do.
**Maps to:** SESSION-AWARENESS-01 Phase 1c (#284) — "promoted truth + transcript + Peek-at-Memoir read accessor." Extends Phase 1b-minimum (`profile_seed` runtime wiring, #327 LANDED) with returning-narrator-aware first-turn composition.
**Sequencing:** lands after v7 verifies Lane 1 (clear_direct + era framing) AND ideally alongside or after WO-PROMPT-BLOAT-AUDIT-01 Phase 0 so we have token-budget visibility before adding content.

---

## Problem statement

When a narrator returns to a session, Lori's current first turn is one of two existing paths:

1. **First-time intro path** (`startIdentityOnboarding`): warm welcome + "let me explain what I do + need your name, DOB, place." Fires for narrators with `identityPhase=askName`.
2. **No path at all** for returning narrators with complete identity — Lori just waits for the narrator to speak first, OR the QF/CD/WS style dispatcher kicks in with a generic next-question prompt.

Neither path acknowledges continuity. For Janice/Kent and similar older narrators, this is a real cognitive cost: they may have forgotten where they were, what they shared, or even that they came back at all. A warm "welcome back, last time we were in [era], you'd been telling me about [anchor]" does the orientation work the narrator's memory used to do.

**Equally important — what this WO is NOT:**

- Not a clinical re-orientation tool ("you forgot we talked about X")
- Not a fact-recital ("here are the 12 things I know about you")
- Not a forced agenda ("we should pick up where we left off")

It's a single warm sentence of continuity that lets the narrator pick the thread or change it.

---

## Three-state welcome behavior

| State | Detection | First-turn behavior |
|---|---|---|
| **First-time** | `identityPhase == "askName"` AND `transcript_history` empty AND BB has no populated personal-section fields | Existing intro path (`startIdentityOnboarding` directive). UNCHANGED. |
| **Returning, complete** | `identityPhase == "complete"` AND `state.profile.basics.preferred` populated AND prior transcript exists for `person_id` (not just current session) | NEW welcome-back: name + last-era + ONE high-confidence anchor + ONE open question. |
| **Returning, incomplete** | `identityPhase != "complete"` AND BB has SOME populated fields (e.g. partial identity from prior session) | Gentle continuation: "Welcome back, [name]. Last time we got as far as [last-completed-field]. Could I get [next missing field]?" — NOT a fresh intro. |

**Critical edge case (BUG-207 history):** WO-13 welcome-back already exists in some form and previously collided with QF dispatch. Phase 1c MUST verify it doesn't double-fire. Acceptance gate explicit below.

---

## Welcome-back content discipline (returning, complete state)

**Locked shape:**

```
Welcome back, [preferred_name].
Last time we were in your [warm_era_label] [years|times|era].
You'd been [verb_phrase] about [single specific anchor].
[ONE open question.]
```

**Word cap:** ≤45 words total. ≤4 sentences.
**Question count:** exactly 1. No menus, no compound, no nested.
**Tone:** warm, conversational, narrator-pace. Reads like a friend remembering, not a system reciting.

**Example (good):**

> Welcome back, William. Last time we were in your Coming of Age years — you'd been telling me about the silk ribbon your mother kept. What would you like to share today?

**Examples (bad — DO NOT produce):**

- "Welcome back. According to your profile, you previously discussed: silk ribbon, father's plant, etc." → fact-recital, system-tone
- "Welcome back, William! Would you like to continue from where we left off, or perhaps talk about something different?" → menu offer (banned per discipline)
- "Welcome back. We left off at the silk ribbon, the silver lake school, and your father's work at the plant." → cognitive overload, three anchors

---

## Anchor selection rules

The "single specific anchor" surfaces ONE memorable detail from BB, transcript, or projection. Selection rules (in priority order):

1. **Highest recency**: prefer the most-recently-touched anchor (last session's last topic).
2. **Confidence threshold**: only anchors with `confidence ≥ 0.85` AND `provenance ∈ {human_edit, narrator_consented, profile_hydrate}`. Weakly-attested anchors NEVER surface — Lori does not over-claim.
3. **Disclosure-mode respect** (cross-references WO-DISCLOSURE-MODE-01): anchors marked `sacred_do_not_persist`, `system_inferred_no_consent`, or `narrator_offered_no_consent` are NEVER surfaced in welcome-back, even at high confidence. Per locked principle: "Remember, but never tell."
4. **Sensory > abstract**: prefer concrete anchors (objects, places, named people, specific events) over abstract claims (relationships, feelings, era-summary). "The silk ribbon" beats "our relationship with your mother."
5. **Avoid identity scalars**: don't surface name/DOB/POB as anchors — those are already in `[preferred_name]` and the era framing. The anchor is a narrative detail.

**Fallback ladder when no anchor meets the bar:**

- Drop the anchor sentence entirely. Just: "Welcome back, [name]. Last time we were in your [era] years. What would you like to share today?"
- If last-era can't be determined either: "Welcome back, [name]. What would you like to share today?"
- If even name isn't available (corner case — should not happen for returning_complete state): use existing intro path. Should never reach this fallback if state detection is correct.

---

## Implementation pieces

### Piece 1 — Returning-narrator detector

**Location:** `server/code/api/prompt_composer.py` — new helper `_classify_session_state(runtime71) -> Literal["first_time", "returning_complete", "returning_incomplete"]`.

**Logic:**

```python
def _classify_session_state(runtime71):
    profile = runtime71.get("profile", {})
    basics = profile.get("basics", {}) if isinstance(profile, dict) else {}
    identity_phase = runtime71.get("identity_phase") or ""
    transcript_history = runtime71.get("transcript_history", [])
    has_identity = bool(basics.get("preferred") and basics.get("dob") and basics.get("pob"))
    has_partial_identity = bool(basics.get("preferred") or basics.get("dob"))
    is_session_start = bool(runtime71.get("is_session_start"))
    has_prior_conversation = bool(runtime71.get("has_prior_conversation"))

    if not is_session_start:
        return "in_session"  # not first turn — no welcome-back composition
    if identity_phase == "askName" and not has_partial_identity:
        return "first_time"
    if identity_phase == "complete" and has_identity and has_prior_conversation:
        return "returning_complete"
    if has_partial_identity and identity_phase != "complete":
        return "returning_incomplete"
    return "first_time"  # safe default
```

### Piece 2 — Welcome-back directive composer

**Location:** `server/code/api/prompt_composer.py` — new helper `_compose_welcome_back_directive(runtime71, anchor) -> str`.

For `returning_complete`:

```
WELCOME BACK MODE: This narrator returned to continue their Life Archive.
Compose a warm 3-4 sentence greeting following this exact shape:
  - "Welcome back, [preferred_name]."
  - "Last time we were in your [warm_era_label] [years|era]."
  - "You'd been [verb] about [anchor_phrase]."  (only if anchor provided)
  - "[ONE open question — not a menu — like 'What would you like to share today?']"
RULES: ≤45 words. ONE question. No menu choices. No "or we could" phrasing.
No compound questions. Warm and conversational, not system-tone.
```

For `returning_incomplete`:

```
WELCOME BACK MODE — INCOMPLETE IDENTITY: This narrator returned but
identity intake didn't finish last time. Compose a warm continuation:
  - "Welcome back, [preferred_name]." (use preferred_name if known, else "Welcome back")
  - Optional: "Last time we'd just gotten your [last_known_field]."
  - "Could I get [next_missing_field]?" (single question)
RULES: ≤35 words. ONE question. No menus. No re-introducing yourself.
Don't act like this is a first meeting.
```

### Piece 3 — Anchor selector

**Location:** new `server/code/api/services/welcome_back_anchor.py`.

**Function:** `select_welcome_back_anchor(person_id, db) -> Optional[Anchor]` — returns dict with `phrase`, `verb`, `era_id`, OR None if nothing meets the bar.

**Sources to query (in priority order):**

1. Last `interview_segment` row for `person_id` ordered by `created_at DESC` — gets last topic in last session
2. `bio_blob` populated narrative fields (e.g. `personal.notableLifeEvents.last`, `parents.notableLifeEvents`, `siblings.memorableMoments`) with confidence + provenance
3. `story_candidates` review_status=approved (from WO-LORI-STORY-CAPTURE-01 lane)

**Filter chain:**
- confidence ≥ 0.85 ✓
- provenance ∈ allowed set ✓
- disclosure_mode ∉ {sacred_do_not_persist, system_inferred_no_consent, narrator_offered_no_consent} ✓
- value is concrete (length 4-60 chars, contains a noun, not abstract phrase) ✓

If 0 anchors pass: return None. Composer drops the anchor sentence.

### Piece 4 — Frontend signal

**Location:** `ui/js/app.js lvNarratorRoomInit` (or wherever session-start fires).

When narrator-room paints AFTER a fresh session start (not just a tab switch), set a one-shot flag in the runtime71 payload:

```javascript
if (state.session.firstTurnAfterStart) {
  runtime71.is_session_start = true;
  runtime71.has_prior_conversation = !!(transcript_history_count_for_person > 0);
  state.session.firstTurnAfterStart = false;  // consume the flag
}
```

The `has_prior_conversation` count needs a backend query (reuse existing `/api/transcript/history` count) at narrator-room init time.

### Piece 5 — BUG-207 coordination

When `returning_complete` is detected AND session_style is `questionnaire_first`, the QF dispatcher's section-walk handoff (`_enterBioBuilderSectionWalk`) must NOT also fire its own opening prompt. The welcome-back IS the opening prompt for that turn; QF section walk picks up on the NEXT user turn.

Implementation: `_enterBioBuilderSectionWalk` checks if `state.session.firstTurnAfterStart` was just consumed by welcome-back — if so, skip the section-walk dispatch this turn, defer to next narrator input.

---

## Acceptance gates

Welcome-back ships when ALL of these pass:

1. **Three-state detection unit tests:**
   - First-time narrator (no BB, no transcript) → "first_time" classification
   - Returning complete (BB populated + transcript history) → "returning_complete"
   - Returning incomplete (partial BB, identityPhase != complete) → "returning_incomplete"

2. **Anchor selector behavioral tests:**
   - High-confidence concrete anchor → returned
   - Low-confidence anchor → filtered out (returns None)
   - sacred_do_not_persist anchor → filtered out (returns None)
   - Identity scalar (name/DOB/POB) → never returned as anchor
   - Multiple candidates → returns most-recently-touched

3. **Composer output tests:**
   - returning_complete with anchor → produces ≤45 words, exactly 1 question, no menu phrases
   - returning_complete without anchor → drops anchor sentence, still ≤30 words
   - returning_incomplete → no re-introduction, single missing-field ask

4. **Live integration tests (rehearsal harness, new pack):**
   - **TEST-WB-01:** Run two-session sequence on test narrator. Session 1: complete identity + 3 turns. Session 2: re-enter narrator. Expect welcome-back firing with name + last era + 1 anchor.
   - **TEST-WB-02:** Same as TEST-WB-01 but with sacred_do_not_persist marker on the would-be anchor. Expect anchor sentence to drop, NOT to surface the sacred content.
   - **TEST-WB-03:** Returning narrator with partial identity. Expect "Welcome back, [name]. Could I get your [next field]?" — NOT a fresh intro.
   - **TEST-WB-04:** First-time narrator. Expect EXISTING intro path unchanged.
   - **TEST-WB-05:** BUG-207 regression — QF returning narrator does NOT fire both welcome-back AND a section-walk question on the same turn.

5. **r5h-followup-guard-v1 baseline UNCHANGED.** This is a Lori-side change; extractor pipeline must not be affected.

6. **Three Lori-behavior eval packs UNCHANGED** on quality metrics: golfball, sentence-diagram-survey, lori_narrative_cue_eval.

7. **Token budget:** welcome-back directive adds ≤80 tokens to system prompt for the first turn only. Doesn't compound across the session.

---

## Non-negotiables

- **No fact recital.** Welcome-back surfaces ONE anchor, not three. Cognitive overload defeats the purpose.
- **No menu offers.** Single open question. "What would you like to share today?" — not "would you like to continue or talk about something new?"
- **No clinical re-orientation.** Lori does not say "you may not remember" or "let me remind you" or any phrase that frames the narrator's memory as deficient.
- **No over-claiming.** Confidence + provenance + disclosure-mode gates are mandatory. If those gates filter all candidates, drop the anchor sentence — better to be vague than wrong.
- **No double-firing with QF/CD/WS dispatchers.** BUG-207 history is real; the welcome-back IS the opening turn, not in addition to it.
- **No persistence of derived welcome-back content.** The composed greeting is not stored or replayed. It's always re-composed fresh from current BB + transcript state.

---

## Files this WO will touch

**Phase 1c (this WO):**
- `server/code/api/prompt_composer.py` — `_classify_session_state` + `_compose_welcome_back_directive` + dispatch in `compose_system_prompt`
- `server/code/api/services/welcome_back_anchor.py` (new) — anchor selector + filter chain
- `ui/js/app.js` — `lvNarratorRoomInit` flag emission + first-turn detection
- `ui/js/state.js` — `state.session.firstTurnAfterStart` flag
- `ui/js/session-style-router.js` — BUG-207 coordination guard in `_enterBioBuilderSectionWalk`
- `tests/test_welcome_back_anchor.py` (new) — unit tests
- `tests/test_compose_welcome_back.py` (new) — composer output tests
- `scripts/ui/run_parent_session_rehearsal_harness.py` — TEST-WB-01..05 pack

**Out of scope (separate lanes):**
- WO-DISCLOSURE-MODE-01 — disclosure_mode field on BB items (welcome-back READS this; doesn't write it)
- WO-LORI-STORY-CAPTURE-01 — story_candidates review status (welcome-back may READ approved stories as anchor candidates; doesn't write)
- WO-PROMPT-BLOAT-AUDIT-01 — overall token discipline (welcome-back is one new directive that lands within the budget but doesn't fix bloat)

---

## Phase plan

**Phase 1c.1 — Detection + composer (no anchor selector yet):**
- Implement `_classify_session_state`
- Implement `_compose_welcome_back_directive` with anchor=None always (just name + era + open question)
- Wire frontend signal
- TEST-WB-04 (first-time unchanged) + TEST-WB-03 (returning incomplete) acceptance

**Phase 1c.2 — Anchor selector:**
- Implement `welcome_back_anchor.py` with confidence + provenance + disclosure-mode filters
- Wire selector output into composer
- TEST-WB-01 (with anchor) + TEST-WB-02 (sacred_do_not_persist filtered) acceptance

**Phase 1c.3 — BUG-207 coordination:**
- Add guard in `_enterBioBuilderSectionWalk`
- TEST-WB-05 acceptance

Phase 1c.1 alone is shippable as v1 — name + era + open question, no anchor. Phase 1c.2 adds the anchor sentence. Phase 1c.3 closes the QF coordination gap.

---

## Acceptance summary

Phase 1c.1 closes when first-time narrators are unchanged AND returning-complete narrators get a name+era welcome (no anchor) without breaking r5h baseline or three Lori-behavior eval packs.

Phase 1c.2 closes when anchor selection works end-to-end with confidence/disclosure filters, verified by TEST-WB-01 + TEST-WB-02.

Phase 1c.3 closes the QF coordination loop. After all three phases land, the rehearsal harness's new TEST-WB pack passes 5/5.
