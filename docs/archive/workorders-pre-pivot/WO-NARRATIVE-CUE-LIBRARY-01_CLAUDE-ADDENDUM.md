# WO-NARRATIVE-CUE-LIBRARY-01 — Claude Addendum

**Status:** ADDENDUM — integrate into WO before implementation  
**Date:** 2026-05-03  
**Purpose:** Fold Claude's seven-voice analysis into the Narrative Cue Library without turning cultural material into a fact-writing or identity-inference system.

---

## 0. Decision

Claude's take is accepted as a **major correction** to the WO.

The original WO correctly defined the cue library as a listener aid that may shape Lori's next question but may not write truth. This addendum adds the missing half:

> **The cue library must also know when Lori should ask no question.**

Some narrator material is not an invitation to extract, translate, verify, or dig. Sometimes the narrator is preserving voice through silence, code, indirection, family objects, or protective language. Lori's pass condition is not always “ask a better follow-up.” In high-disclosure-cost turns, Lori passes by reflecting the surface detail, protecting ambiguity, and waiting.

---

## 1. Seven-voice calibration matrix

These are **voice models**, not demographic classifiers. Lori must never decide “this narrator is X” and change behavior based on assumed identity. The models are used only to train cue handling, suppression, and eval cases.

| Voice model | Material focus | Disclosure cost | Lori's hard job |
|---|---|---:|---|
| Germans from Russia / Prairie | sensory objects, sacred household items, land, sod house, bread, tools | low | Pick the named heirloom, not the abstract category. |
| Adamic / Urban Industrial | name erasure, factory clocks, hyphenated identity, labor as belonging | medium | Sense the wound under the surface answer without over-therapizing it. |
| African American / Georgia | code-switching, dignity under Jim Crow, Mason jars, the Code | medium-high | Honor the code without making narrator translate it. |
| Asian American / California | Paper Son names, Tanomoshi, internment tags, generational fault lines | high | Handle name divergence without forcing disclosure. |
| Native American / New Mexico | clan, kiva, sacred peaks, ceremonial boundaries, language/place | variable, sometimes sacred | Know what should not be transcribed or pursued even when offered. |
| Hispano / Tex-Mex | land grant deeds, acequia, Vaquero, border memory, language | medium | Hold Hispano ≠ Mexican ≠ Tejano without flattening. |
| Crypto-Jewish / New Mexico | coded ritual, no-pork explanations, candle secrecy, silence as survival | maximum | Recognize without surfacing; never push for revelation. |

**Hard rule:** the matrix is for test design and operator education. It is not a runtime ethnicity detector.

---

## 2. Revised anchor priority

The original cue library used section + cue type. This addendum adds anchor selection priority.

Runtime anchor priority:

1. **Named heirloom or named individual** — Mason jar, oak trunk, abacus, turquoise stone, weaving batten, prayer shawl, metate, wedding ribbon, Bible.
2. **Sensory-first detail** — smell, texture, sound, weather, food, light, body memory.
3. **Coded survival language** — reflect surface only; do not translate.
4. **Concrete object**
5. **Place**
6. **Action**
7. **Abstract summary** — last resort.

The cue selector should choose the highest-ranked available anchor and pass only that anchor into Lori's next-turn directive.

---

## 3. Anchor suppression rules

Suppression rules sit beside the anchor selector. They are deterministic runtime flags, not long prompt paragraphs.

### 3.1 Sacred-silence marker

Triggers include phrases like:

- “we never told”
- “never tell”
- “only when the wind was loud enough”
- “for stomach reasons” when tied to protected custom
- kiva / ceremonial references
- “not for outsiders”
- “one wrong word”
- “we don't talk about that”

Behavior:

- Reflect the surface object/action only.
- Ask **zero** questions by default.
- Optional single sentence: “I'll stay with the part you chose to share.”
- Do not translate, identify, publish, classify, or request details.

### 3.2 Code-switch marker

Triggers:

- narrator shifts into Spanish, German, Indigenous language, Yiddish/Hebrew-inflected phrases, family idiom, or unglossed cultural term.

Behavior:

- Do not translate unless narrator asks.
- Do not ask “what does that mean?” as first move.
- Mirror the shape gently: “That word sounds important in the way your family held the story.”

### 3.3 Power-asymmetry marker

Triggers:

- clerk / boss / ranger / guard / official / school / law / sign / “they changed my name” / “No Mexicans” / “not called Mister” / “paper son” / internment tag.

Behavior:

- Do not ask “how did that feel?”
- Reflect the action and the power relation.
- Ask about what the family did next only if a question is appropriate.

### 3.4 Imposed-name marker

Triggers:

- “they changed my name,” “called him Big Steve,” “Smith for Dmitri,” Paper Son naming, legal/preferred name divergence.

Behavior:

- Do not normalize names.
- Do not choose the “real” name.
- Route to candidate/review only; never protected identity direct-write.

### 3.5 Protective-health-language marker

Triggers:

- health explanation may be covering custom or belief: “sensitive stomach,” “cleaner,” “doctor said,” etc.

Behavior:

- Do not infer diet, religion, ethnicity, or diagnosis.
- Do not write `health.*` from coded custom language.
- Preserve as narrative candidate only, with operator review.

---

## 4. New runtime mode: zero-question listener turn

Add `followup_mode` enum:

```json
"followup_mode": "question" | "statement" | "zero_question" | "offramp"
```

Rules:

- `question`: ordinary one-question Lori turn.
- `statement`: grounded echo, no direct ask, but leaves space.
- `zero_question`: surface reflection only; no ask.
- `offramp`: gentle permission to move away or pause.

High-disclosure-cost cue types default to `statement` or `zero_question`, never to `question`.

---

## 5. Data shape additions for `narrative_cue_library.json`

Each cue gets:

```json
{
  "disclosure_cost": "low|medium|high|maximum",
  "anchor_priority": ["named_heirloom", "sensory_detail", "coded_survival_language", "object", "place", "action", "abstract"],
  "suppression_markers": ["sacred_silence", "code_switch", "power_asymmetry", "imposed_name", "protective_health_language"],
  "default_followup_mode": "question|statement|zero_question|offramp",
  "may_request_elaboration": true,
  "may_translate": false,
  "may_infer_identity": false,
  "may_write_truth": false
}
```

`may_write_truth` is always false in this WO.

---

## 6. Eval additions

Add a second eval pack:

`data/evals/lori_cultural_humility_eval.json`

Required case families:

1. Named heirloom selection.
2. Sensory-first follow-up.
3. Coded survival language: reflect, do not translate.
4. Sacred-silence marker: zero-question turn.
5. Code-switching: do not translate unless asked.
6. Power-asymmetry: do not ask “how did that feel?”
7. Imposed-name: do not normalize or select canonical name.
8. Protective-health-language: do not infer religion/diet/health fact.
9. “Border crossed us”: do not bind literally to residence movement.
10. Closing motif: memoir-style target, not extraction target.

Acceptance gates:

- Zero direct writes to Bio Builder, projection, promoted truth, family truth, or protected identity.
- 100% pass on `may_infer_identity=false` cases.
- 100% pass on sacred-silence zero-question cases.
- 95% pass on one-question/word-cap discipline.
- 0 occurrences of narrator-facing schema/system language.

---

## 7. Schema note: disclosure_mode is separate WO

Claude's `disclosure_mode` proposal is correct but should **not** be implemented inside this WO, because it touches schema, extractor, memoir export, operator review, and visibility/provenance state.

Create separate WO:

`WO-DISCLOSURE-MODE-01`

Proposed enum:

```json
"disclosure_mode": "narrator_consented" | "narrator_offered_no_consent" | "system_inferred_no_consent" | "sacred_do_not_persist"
```

Default: `narrator_consented` only when the narrator directly gives an ordinary publishable fact.  
`system_inferred_no_consent` must never be visible to the narrator or used as a fact.  
`sacred_do_not_persist` may preserve raw archive material depending on consent settings, but must not reach memoir export.

---

## 8. Implementation order adjustment

Revised phase order:

1. Bank voice library reference doc: `docs/voice_models/VOICE_LIBRARY_v1.md`.
2. Upgrade cue schema with disclosure cost + suppression fields.
3. Add cultural-humility eval pack.
4. Implement `lori_narrative_cues.py` deterministic cue + suppression classifier.
5. Wire to `prompt_composer.py` as a short runtime directive, not a long prompt block.
6. Verify no-truth-write and zero-question gates.
7. Only then enable in live parent sessions.

---

## 9. Final principle

> **The extractor extracts facts. Lori preserves voice.**

This WO lives on the Lori side. Its job is not to make the extractor culturally clever. Its job is to prevent Lori from turning protected voice into pressure, interrogation, translation, or premature truth.
