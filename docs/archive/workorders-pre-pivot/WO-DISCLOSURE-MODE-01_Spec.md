# WO-DISCLOSURE-MODE-01 — Per-entry disclosure-mode flag for narrator-volunteered material

**Status:** SPEC — scoped, ready for implementation Phase 1; Phases 2–4 gated behind Phase 1 evidence. **Today: spec only — DO NOT wire schema/extractor/export.** Phase 1 lands on a separate session after the WO-NARRATIVE-CUE-LIBRARY-01 cue detector is in place.
**Date:** 2026-05-03 (Claude base + ChatGPT Pipeline Rules integration)

---

## 0a. Retired metaphor note (DO NOT REINTRODUCE)

Do not use Kawa, river, rocks, driftwood, water, flow, or similar river-model language in this WO, schema fields, UI strings, log lines, or acceptance criteria. The active product language is:

- Life Map
- Review Queue
- Evidence Card
- Memoir Preview
- Archive
- History
- Promoted Truth
- disclosure mode
- export visibility

## 0b. Vocabulary

**`disclosure_mode`** — A structured provenance value attached to a candidate, proposal, or exportable memoir fragment. It does **not** classify the narrator. It classifies the system's permission to surface a derived claim.

**`derived claim`** — Any structured assertion, field value, memoir sentence, title, tag, summary, or Life Map node generated from narrator material.

**`protected implication`** — A pattern that may suggest cultural, religious, ethnic, trauma, legal, or identity context but was not explicitly named by the narrator.

Example of a protected implication:

> Narrator says: *"We did not eat pork, but mother said it was for stomach reasons."*
>
> Allowed derived claim: *"Family used a protective explanation around food habits."*
>
> Forbidden derived claim: *"Family was secretly Jewish / kosher."*

---
**Lane:** Schema + extractor + memoir export. Lives across multiple surfaces but is one cohesive WO because the enum value carries through all of them.
**Sequencing:** Independent of WO-NARRATIVE-CUE-LIBRARY-01 (which lives entirely on the Lori-side). This WO is the schema-side counterpart that captures *what disclosure looked like* per entry. Both WOs together are what allow Lorevox to honor the seven-voice library's disclosure-cost gradient.
**Blocks:** Should land before any narrator from Voice 7 (Crypto-Jewish, MAXIMUM disclosure cost) is brought into a live session — without this flag, every truth-write is treated as `narrator_consented` by default and there's no architectural place for sacred material to live.
**Lights up:** sd_047 (sacred silence), sd_049 (Paper Son name divergence), sd_050 (protective health language), and the entire Crypto-Jewish voice section of `docs/voice_models/VOICE_LIBRARY_v1.md`.

---

## What this WO is NOT

```
- NOT a Lori behavior change.
  Lori-side disclosure-cost handling is WO-NARRATIVE-CUE-LIBRARY-01
  + WO-LORI-SENTENCE-DIAGRAM-RESPONSE-01 territory. This WO adds
  the schema field that those Lori-side WOs need a place to write
  to.

- NOT a runtime ethnicity classifier.
  The enum captures HOW the entry was disclosed, not WHO the
  narrator is. "narrator_offered_no_consent" doesn't mean "the
  narrator is Crypto-Jewish"; it means "the narrator told us
  this but didn't authorize it for memoir."

- NOT a replacement for protected_identity / Bug-312 work.
  protected_identity governs WHICH FIELDS are protected at write
  time (fullName, dateOfBirth, etc.). disclosure_mode governs
  WHICH ENTRIES carry consent metadata. Different axes; both
  apply.

- NOT visible to the narrator.
  This is operator-side metadata. The narrator sees their memoir;
  the disclosure_mode value lives in the Bug Panel + Review Queue
  + memoir-export filter. The narrator never sees a label like
  "we have flagged this as 'sacred_do_not_persist'".

- NOT the mechanism for upgrading consent.
  An entry tagged narrator_offered_no_consent stays that way until
  the narrator EXPLICITLY consents in a future session. There is
  no "system upgrades to consented after N turns" rule.
```

## What this WO IS

```
A per-entry enum field that travels alongside truth-writes from
extraction → projection → review queue → memoir export. The enum
captures the disclosure context at write time and gates downstream
consumption (especially memoir export).

The single line: "the extractor extracts facts; Lori preserves
voice." This WO is the schema-side acknowledgment that those
two jobs produce different things and only one of them is
publishable by default.
```

## Why now

### Live evidence

From `docs/voice_models/VOICE_LIBRARY_v1.md` Voice 7 (Crypto-Jewish, MAXIMUM disclosure cost):

> *"My grandmother told me, on her deathbed, 'Remember, but never tell.'"*

Without this WO, if the narrator says this line in a Lori session, the extractor has no architectural way to flag the entry as "preserved but not publishable." The current default is implicit consent — every truth-write is assumed to be authorized for memoir.

From sentence-diagram-survey case sd_050 (protective health language):

> *"My father never ate pork, but he said it was because his stomach was sensitive."*

Without this WO, even with WO-NARRATIVE-CUE-LIBRARY-01's `protective_health_language` suppression marker preventing Lori from asking the wrong question, there's no schema slot to record that the entry exists at lower-than-default consent.

From sentence-diagram-survey case sd_049 (Paper Son name):

> *"My father was a Paper Son. He memorized a whole family history just to walk through the gates of Angel Island."*

The name on the Paper Son's papers is one fact; the original family name is a different fact at a different consent level. Today the schema has nowhere to express that distinction.

### Architectural pressure

WO-NARRATIVE-CUE-LIBRARY-01 v2 + addendum already added:
- `disclosure_cost: low|medium|high|maximum` on cue types
- Suppression markers (sacred_silence, code_switch, coded_survival_language, power_asymmetry, imposed_name, protective_health_language)
- New followup modes (question / statement / zero_question / offramp)

But all of that is **Lori-side** — it shapes what Lori asks. There's no schema-side counterpart that captures *what was actually written* and *under what consent*. This WO adds the receiving end so the two surfaces compose cleanly.

WO-SCHEMA-DIVERSITY-RESTORE-01 Phase 3 (sensitive identity capture) was scoped to add `visibility/provenance` state to identity fields. That work is largely the same problem viewed from the identity-field angle. **This WO supersedes the Phase 3 visibility/provenance design** and provides the unified field that identity, faith, ancestry, family-secret, and any other sensitive entry can use.

## Scope

### Phase 1 — Schema + extractor default + persistence (READY)

**Schema additions:**

```python
# Per-entry enum carried alongside ExtractedItem
class DisclosureMode(str, Enum):
    NARRATOR_CONSENTED = "narrator_consented"
    NARRATOR_OFFERED_NO_CONSENT = "narrator_offered_no_consent"
    SYSTEM_INFERRED_NO_CONSENT = "system_inferred_no_consent"
    SACRED_DO_NOT_PERSIST = "sacred_do_not_persist"
```

**Field semantics:**

- **`narrator_consented`** (default) — Narrator volunteered the fact in ordinary publishable form. Memoir export includes this entry. Examples: "I was born in Spokane in 1939", "My father worked at the aluminum plant".
- **`narrator_offered_no_consent`** — Narrator volunteered the fact but in a context that signals it should NOT be published. Examples: a sacred-silence cue marker fired on the turn; the narrator coded the truth in protective language; the narrator's surrounding language signals "this is for you to know, not for the memoir." Memoir export filters these by default; operator review surfaces them with a clear "narrator-offered, no consent" badge.
- **`system_inferred_no_consent`** — System derived the fact (e.g., extractor inferred "father was Jewish" from "no pork because sensitive stomach"). Inferred entries NEVER reach the narrator's view, NEVER reach memoir, and are review-only. **This category should fire rarely** — its existence is itself a signal that the extractor is overstepping. If `system_inferred_no_consent` count exceeds 1% of entries, that's a BINDING-01 signal.
- **`sacred_do_not_persist`** — Material the narrator volunteered but the system recognizes (via cue library suppression markers, especially `sacred_silence` from the Crypto-Jewish/Native voice contexts) as sacred. Persisted to raw archive ONLY for the operator's reference; NEVER to memoir, NEVER to projection, NEVER to family_truth. The narrator's session continues normally; the sacred frame is honored architecturally.

**Default rule:**

Every existing extracted item that doesn't carry an explicit `disclosure_mode` defaults to `narrator_consented`. This preserves byte-stable behavior for the master 114-case eval and all existing surfaces. The new enum only changes behavior when an entry is explicitly tagged with one of the other three values.

**Tagging mechanism (Phase 1):**

The extractor itself does NOT auto-tag in Phase 1 — that's Phase 2 (when the cue library's suppression markers thread through). Phase 1 is just the schema field + persistence + operator-review surface. Initial tagging happens via:

1. Operator manual flag (Bug Panel Story Review surface gets a "tag this entry" affordance).
2. Future Phase 2: cue library's `suppression_markers` map to disclosure_mode values.

### Phase 2 — Cue library → extractor wiring

**File touched:** `server/code/api/services/lori_narrative_cues.py` + `server/code/api/routers/extract.py`.

When WO-NARRATIVE-CUE-LIBRARY-01 fires a cue with suppression markers, the cue context flows into the extractor's runtime state. If the cue carries:
- `sacred_silence` → all entries from this turn default to `sacred_do_not_persist`
- `coded_survival_language` → all entries from this turn default to `narrator_offered_no_consent`
- `protective_health_language` → entries that bind to faith/health/ancestry fields default to `narrator_offered_no_consent`
- `imposed_name` → name divergence creates two entries with different disclosure_mode (paper-son name = narrator_consented; original name = narrator_offered_no_consent if surfaced)

Default-OFF behind `HORNELORE_DISCLOSURE_MODE_AUTO=0` until eval shows the gate is right.

### Phase 3 — Memoir export filter

**File touched:** `server/code/api/routers/memoir_export.py` (or wherever DOCX/PDF export lives).

Memoir export defaults to filter:
```python
EXPORTABLE_DISCLOSURE_MODES = {DisclosureMode.NARRATOR_CONSENTED}
```

Operator can opt-in to include `narrator_offered_no_consent` entries via a per-export checkbox ("Include entries the narrator offered but did not formally consent to publish"), but the default is consent-only. `system_inferred_no_consent` and `sacred_do_not_persist` are NEVER exportable, regardless of operator preference.

### Phase 4 — Operator review surface

**Files touched:** `ui/js/bug-panel-story-review.js` + `ui/css/bug-panel-story-review.css`.

Each story candidate / extracted item in the Bug Panel review queue shows its `disclosure_mode` as a colored badge:
- 🟢 narrator_consented — green
- 🟡 narrator_offered_no_consent — yellow (operator may upgrade after narrator confirmation in a later session)
- 🟠 system_inferred_no_consent — orange (review and likely discard)
- 🔴 sacred_do_not_persist — red (preservation only; never publish)

Operator can:
- View the entry + narrator's verbatim words
- Adjust the disclosure_mode (with audit log entry)
- Mark for narrator confirmation in next session (narrator_offered_no_consent → narrator_consented)
- Discard (system_inferred_no_consent → null entry)

## Locked design rules

```
1. Every truth-write entry carries a disclosure_mode value.
   No null. Default narrator_consented preserves byte-stable
   behavior; explicit tagging only changes behavior at the four
   downstream consumers (memoir export, projection, family_truth,
   operator review).

2. Disclosure_mode is OPERATOR-VISIBLE, NEVER NARRATOR-VISIBLE.
   The narrator's session sees only their own material. The
   disclosure_mode badge lives in the operator surface only.
   The narrator never sees "we have flagged this as 'sacred'".

3. Memoir export defaults to narrator_consented only.
   Operator can opt in to narrator_offered_no_consent entries via
   per-export checkbox. system_inferred and sacred categories are
   NEVER exportable, regardless of operator preference.

4. Sacred material is preserved, never published.
   sacred_do_not_persist entries stay in raw archive (so the
   operator can see the conversation history) but never reach
   memoir / projection / family_truth / promoted_truth.

5. Inferred entries are a BINDING signal.
   If system_inferred_no_consent count exceeds 1% of total
   extracted entries on the master 114-case eval, that's evidence
   the extractor binding layer is overstepping. Audit BINDING-01.

6. Consent upgrades require explicit narrator action.
   No "system upgrades to consented after N turns" rule. The
   only path narrator_offered_no_consent → narrator_consented is
   the operator marking for narrator confirmation, the narrator
   confirming in a later session, and the operator manually
   upgrading.

7. The schema field is additive, not replacing.
   protected_identity (Bug-312) still governs which FIELDS need
   trusted source for any write. disclosure_mode governs which
   ENTRIES carry what consent. Both apply.

8. Voice library is reference, not classifier.
   docs/voice_models/VOICE_LIBRARY_v1.md is operator education.
   It does NOT auto-tag entries by inferred narrator ethnicity /
   culture / faith. Auto-tagging fires only on cue library
   suppression markers (Phase 2).
```

## What this WO does NOT do

- **No Lori behavior change.** Lori-side handling lives in WO-NARRATIVE-CUE-LIBRARY-01 + WO-LORI-SENTENCE-DIAGRAM-RESPONSE-01.
- **No runtime ethnicity / culture / faith classifier.** Disclosure mode is about CONSENT and PUBLICATION CONTEXT, not narrator identity.
- **No auto-upgrade of consent.** The system never flips an entry from `narrator_offered_no_consent` to `narrator_consented` automatically.
- **No backfill of historical entries** in Phase 1. All pre-existing entries default to `narrator_consented`. Operator can manually re-tag if needed.
- **No memoir export rewrite.** Phase 3 adds a filter; the export pipeline itself is unchanged.

## Acceptance gates

```
Phase 1  [ ] Schema migration adds disclosure_mode column to story_candidates,
             extracted_items, and projection_items tables (with default
             value 'narrator_consented')
         [ ] ExtractedItem Pydantic model gains disclosure_mode field
             (default: NARRATOR_CONSENTED)
         [ ] Master 114-case eval is byte-stable with v3 / v2 / mnw all
             unchanged (the default value preserves prior behavior)
         [ ] Bug Panel Story Review surface shows the colored badge
             per entry
         [ ] Operator can manually re-tag an entry's disclosure_mode
             (with audit log)
         [ ] All four enum values supported in DB and API responses

Phase 2  [ ] HORNELORE_DISCLOSURE_MODE_AUTO=0 flag added (default-off)
         [ ] Cue library suppression markers map to disclosure_mode
             values per the Phase 2 spec table above
         [ ] Master 114-case eval is byte-stable when flag off
         [ ] Cultural-humility eval (lori_cultural_humility_eval.json)
             cases sd_047/sd_050 (sacred silence + protective health
             language) produce sacred_do_not_persist or
             narrator_offered_no_consent entries when flag on
         [ ] system_inferred_no_consent count is < 1% of total
             entries on the 114-case master (if higher, audit BINDING-01)

Phase 3  [ ] Memoir export defaults to narrator_consented only
         [ ] Per-export operator checkbox to include
             narrator_offered_no_consent
         [ ] system_inferred_no_consent and sacred_do_not_persist
             never appear in exported memoir, regardless of
             operator preference
         [ ] DOCX + PDF export both honor the filter

Phase 4  [ ] Operator review surface shows colored badges per entry
         [ ] Operator can adjust disclosure_mode with audit log
         [ ] "Mark for narrator confirmation" workflow shipped
         [ ] Narrator confirmation in a follow-up session triggers
             operator-upgrade affordance
         [ ] No narrator-visible badge or label leaks
```

## Pipeline rules (per-stage)

The disclosure_mode value flows through the system at multiple surfaces. Each stage has explicit allowed / forbidden behaviors per enum value.

### Cue library stage

The narrative cue library may emit a `disclosure_hint` alongside its cue decision:

```json
{
  "cue_family": "hidden_custom",
  "suppression_markers": ["protective_health_language"],
  "followup_mode": "offramp",
  "disclosure_hint": "system_inferred_no_consent"
}
```

The cue library MAY NOT emit field writes. The hint is a recommendation that downstream extraction can adopt as the entry's `disclosure_mode` default.

### Extractor stage

The extractor may propose a candidate with `disclosure_mode`, but it may not promote restricted disclosure modes.

Rules per value:
- **`narrator_consented`** can follow normal Review Queue path.
- **`narrator_offered_no_consent`** goes to private Review Queue only.
- **`system_inferred_no_consent`** cannot become a claim unless a human explicitly converts it after narrator consent in a follow-up session.
- **`sacred_do_not_persist`** blocks all derivative structured output. The cue library's `sacred_silence` suppression marker should map here by default.

### Review Queue stage

Evidence Cards must show disclosure mode clearly to the operator with the colored badge from Phase 4.

Operator actions (badge-gated):
- **Approve as normal fact** — allowed only if disclosure_mode permits (i.e., only `narrator_consented`).
- **Keep private** — flips to or maintains `narrator_offered_no_consent`.
- **Exclude from memoir** — operator-side decision regardless of disclosure_mode.
- **Request narrator confirmation later** — schedules a follow-up; if narrator confirms in next session, operator can manually upgrade `narrator_offered_no_consent` → `narrator_consented`.
- **Redact / remove derivative candidate** — `system_inferred_no_consent` → null entry.

The "Approve as normal fact" button is **disabled** for `sacred_do_not_persist` entries. The button can never be re-enabled programmatically; only operator manual override (with audit log + double-confirm) can change a sacred entry's disclosure_mode, and even then only to `narrator_offered_no_consent` — never directly to `narrator_consented`.

### Memoir export stage

Memoir export filter:

```python
EXPORTABLE = (
    entry.disclosure_mode == DisclosureMode.NARRATOR_CONSENTED
    and entry.review_status == "approved"
    and not entry.private_or_sensitive_flag
)
```

Never include in memoir export, regardless of operator preference:
- `narrator_offered_no_consent`
- `system_inferred_no_consent`
- `sacred_do_not_persist`

The per-export operator checkbox to include `narrator_offered_no_consent` is a Phase 3+ enhancement; default for Phase 1 is consent-only.

### Life Map stage

Life Map can show normal approved facts. It must NOT show restricted sensitive implications.

Allowed operator-only diagnostic on the Bug Panel:

> Protected context encountered — hidden from narrator/memoir unless explicitly approved later.

Forbidden narrator-facing label:

> Secret Jewish custom detected.

### Archive stage (the critical clarification)

`sacred_do_not_persist` blocks **derived persistence** — field values, tags, summaries, memoir sentences, Life Map nodes. It does **NOT** silently delete raw transcript or audio if the narrator has enabled recording. Raw archive material remains governed by the existing Archive privacy controls and sensitive/private segment flags from WO-LORI-SAFETY-INTEGRATION-01.

The principle: **the narrator's words are preserved (so the operator can see the conversation history); only derived claims are blocked from publication.**

If the narrator wants raw archive deleted too, that's a separate operator action under existing Archive privacy controls — not automatic from this WO.

---

## Sequencing relative to other lanes

```
WO-NARRATIVE-CUE-LIBRARY-01            ← Lori-side cue + suppression layer
  + Claude Addendum
WO-LORI-SENTENCE-DIAGRAM-RESPONSE-01   ← Lori-side anchor selection
WO-DISCLOSURE-MODE-01                  ← THIS (schema-side counterpart)
WO-SCHEMA-DIVERSITY-RESTORE-01 Phase 3 ← SUPERSEDED by this WO; close
                                         after this WO Phase 1 lands
WO-EX-BINDING-01 second iter           ← extractor binding (parallel)
WO-LORI-SAFETY-INTEGRATION-01          ← safety routing (parallel)
```

WO-SCHEMA-DIVERSITY-RESTORE-01 Phase 3 explicitly proposed `visibility/provenance` state for identity fields. This WO provides the unified mechanism that handles identity + faith + ancestry + family-secret + any other sensitive entry. **Phase 3 of WO-SCHEMA-DIVERSITY-RESTORE-01 should be marked superseded by this WO** once WO-DISCLOSURE-MODE-01 Phase 1 lands.

## Cost estimate

```
Phase 1 (schema + persistence + operator badge):
  ~150 lines: SQLite migration (1 column × 3 tables), Pydantic
  enum + field, db.py accessor updates, Bug Panel Story Review
  badge JS + CSS, operator re-tag endpoint. ~10 unit tests.
  Master 114 verification + Bug Panel manual test.
  = ~1 session.

Phase 2 (cue library wiring):
  ~80 lines: cue → extractor runtime state plumb, suppression
  marker → disclosure_mode mapping, ~6 cultural-humility eval
  fixture verifications. Default-off flag.
  = ~half a session.

Phase 3 (memoir export filter):
  ~50 lines: filter in DOCX export + PDF export, operator
  checkbox UI, manual export verification.
  = ~half a session.

Phase 4 (full operator review surface):
  ~120 lines: badge UI, re-tag affordance, audit log entry,
  narrator-confirmation workflow.
  = ~1 session.

Total Phase 1-4: ~3 sessions across calendar week, with measurement
gates between each.
```

## Bumper sticker

```
The extractor extracts facts.
Lori preserves voice.
This WO is the schema field that says:
"yes, that's a fact, AND that's a fact the narrator never asked
the world to know."

Memoir is for what was meant to be told.
Archive is for what was meant to be remembered.
The grandmother who said "Remember, but never tell" was teaching
us a schema we hadn't designed yet.
```

## Citation context

Voice library reference: `docs/voice_models/VOICE_LIBRARY_v1.md`, especially Voice 7 (Crypto-Jewish, MAXIMUM disclosure cost).
Cue library reference: `data/lori/narrative_cue_library.json` (v2 with suppression markers).
Cultural humility eval: `data/evals/lori_cultural_humility_eval.json` (cases that exercise this WO's enum values).
Sentence-diagram-survey cases that exercise this WO: sd_047 (sacred silence), sd_049 (Paper Son), sd_050 (protective health language) — `data/qa/sentence_diagram_story_cases.json`.

The Crypto-Jewish narrator's deathbed line — *"Remember, but never tell."* — is the canonical use case. Everything in this WO is in service of giving Lorevox an architectural way to honor that instruction.
