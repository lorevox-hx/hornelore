# Multilingual Project Plan — Hornelore / Lorevox

**Filed:** 2026-05-07
**Author:** Claude (dev computer), with Chris's go-ahead 2026-05-07
**Status:** spec + research grounding, then immediate Phase 1 build

This is the master plan for taking Hornelore from English-only to multilingual. Reads alongside the code-review snapshot at `CODE-REVIEW-MULTILINGUAL-READINESS-2026-05-07.md` and the HuggingFace shopping list at `HUGGINGFACE-MODELS-MULTILINGUAL.md`.

---

## What this unlocks

Today: Hornelore captures memory + life-story from English-speaking narrators. Works fairly well.

After this project: Hornelore captures memory + life-story from narrators in **99 languages** (Whisper's coverage), **including code-switching narrators** who naturally mix two languages within a single thought. Tested first on en + es because that's the primary New Mexico use case; extends to other major elder populations (French, German, Portuguese, Mandarin, Cantonese, Vietnamese, Tagalog, etc.) with mostly per-language safety + extraction work.

Why this transformation matters: Lorevox's mission is "preserve the voice of the people who shaped a family." A monolingual-English product fails most American families with grandparents who immigrated from Spanish-speaking countries. ~30M Spanish-speaking elders in NM/AZ/CA/TX/FL alone. Beyond Spanish, there are ~50M elder-population native speakers of other languages in the US who currently can't use this product as themselves.

The product after this lands isn't "Hornelore but with Spanish added." It's **"the only memory product that respects how grandparents actually speak."**

---

## Research grounding, corrected

> **Source discipline (locked 2026-05-07).** This plan now relies only on supplied, verified papers. An earlier draft cited a "Pak et al. 2018" reference that could not be verified — that and any other uncited references have been removed. Anything not in this ledger should be treated as design rationale, not research-backed.

### 1. Multilingual speech robustness (noisy, in-the-wild audio)
- **Sidon — Nakata, Saito, Ueda, Saruwatari, 2026** — "Fast and Robust Open-Source Multilingual Speech Restoration for Large-Scale Dataset Cleansing." ICASSP 2026, IEEE DOI 10.1109/ICASSP55912.2026.11460553. Open-source. w2v-BERT 2.0 + HiFi-GAN; 2,219 hours across 104 languages; ~500x real-time on a single H200 GPU.
  - **Supports**: Lorevox's need to treat real home audio as degraded, variable, and multilingual rather than assuming studio conditions. Not the live STT engine. Future option for cleaning narrator audio before downstream extraction or memoir export.

### 2. Cross-lingual semantic memory (long-term retrieval)
- **OmniSONAR — Omnilingual SONAR Team (FAIR at Meta), 2026** — "Cross-Lingual and Cross-Modal Sentence Embeddings Bridging Massively Multilingual Text and Speech." arXiv:2603.16606v2. Shared cross-lingual + cross-modal embedding space, 200 high-resource languages extended to thousands of varieties, speech modality covering 177 languages. Reports 43% lower cross-modal error rate vs SeamlessM4T.
  - **Supports**: long-term plan for multilingual memory retrieval, cross-language story search, and semantic matching across narrator languages. Not v1.

### 3. Multilingual spoken output (future Lori voice)
- **OmniVoice — Zhu et al. (Xiaomi), 2026** — "Towards Omnilingual Zero-Shot Text-to-Speech with Diffusion Language Models." arXiv:2604.00688v3. 600+ languages, 581k-hour multilingual dataset, single-stage discrete NAR architecture, code at github.com/k2-fsa/OmniVoice.
  - **Supports**: validates that multilingual spoken output is a real research direction. Belongs in the future "Lori speaks back in narrator language" roadmap. **Not a near-term dependency.**

### 4. Home voice interaction (older-adult / home-deployment rationale)
- **DIRHA — Arisio, Manione, Cristoforetti, Matassoni, Omologo et al., 2012** — "User study, analysis of requirements and definition of the application task." FP7-ICT-2011-7 project #288121, Deliverable 1.1. Distant-speech interaction for robust home applications; user requirements; structured interviews with users in home contexts; explicitly addresses always-listening mode in domestic settings.
  - **Supports**: Hornelore's parent-laptop / kiosk path and the design need for simple, reliable voice interaction in a home setting.

### 5. Always-listening privacy and consent
- **Tabassum, Kosiński, Frik, Malkin, Wijesekera, Egelman, Lipford, 2019** — "Investigating Users' Preferences and Expectations for Always-Listening Voice Assistants." Proc. ACM IMWUT 3(4), Article 153, DOI 10.1145/3369807. 178-participant survey. Reports that participants are more willing to share a conversation with a voice assistant when they see benefit, feel comfortable, and do not perceive the conversation as sensitive.
- **Malkin, Egelman, Wagner, 2019** — "Privacy Controls for Always-Listening Devices." NSPW '19, DOI 10.1145/3368860.3368867. Develops the threat model for passively-listening assistants and argues content-aware privacy controls are necessary, not just microphone permission.
  - **Together support** Lorevox's design rules: no always-listening by default; click-to-speak / visible listening state; narrator controls recording; operator-visible privacy controls; no third-party audio sharing; local-first processing.

### 6. Privacy-aware ASR (narrator-controlled redaction)
- **Roy & Vu, 2026** — "Listen, But Don't Leak: Sensitive Data Protection for Privacy Aware Automatic Speech Recognition with Acoustic Triggers." ICASSP 2026, IEEE DOI 10.1109/ICASSP55912.2026.11461572. Introduces Protective Acoustic Triggering — a user-controlled acoustic signal that causes Whisper-style ASR to redact utterances or sensitive phrases directly in the transcription pipeline. Reports 99.47% utterance-level and 97.7% phrase-level redaction success while preserving transcription utility on non-sensitive speech.
  - **Supports**: future Lorevox privacy lane where narrators can intentionally mark speech as private before it enters the archive. Pairs with `sacred_do_not_persist` in WO-DISCLOSURE-MODE-01. Becomes its own work order — **WO-ML-PRIVACY-ASR-01** (see below). Not Phase 1.

### 7. Memory augmentation and minimal disruption
- **Memoro — Zulfikar, Chan, Maes, 2024** — "Using Large Language Models to Realize a Concise Interface for Real-Time Memory Augmentation." CHI '24, DOI 10.1145/3613904.3642450. MIT Media Lab. N=20 within-subject study; LLM-driven memory augmentation in conversational settings; Query Mode (push-to-talk) vs Queryless Mode comparison; emphasis on minimal disruption and concise responses; 15 of 20 participants preferred Query Mode.
  - **Supports**: Lori's design pattern — short responses, minimal interruption, context-aware recall, memory echo, conversation quality preserved. Reinforces the "Lori should not overtalk" and "one useful memory cue, not a database dump" rules.

### 8. Just-in-time nudges with caution
- **Gupta, Aritonang, Rajendran, Danry, Maes, Nanayakkara, 2026** — "Feeling the Facts: Real-time wearable fact-checkers can use nudges to reduce user belief in false information." CHI '26, DOI 10.1145/3772318.3791679. NUS + MIT. N=34 controlled study. Subtle, body-integrated, just-in-time cues improve discernment; the same study warns about over-reliance when the system makes errors (false positives, missed false claims).
  - **Supports** — and cautions — the operator/nudge lane: gentle cues, show uncertainty, do not overclaim, do not make Lori a fact-correction authority over the narrator, avoid over-reliance. Already informs the visual-only posture in WO-LORI-SESSION-AWARENESS-01 Phase 3.

### Build-plan citation map
| Work order | Cited support |
|---|---|
| WO-ML-01 — Live Whisper STT wiring | Sidon (audio quality), DIRHA (home interaction), Tabassum + Malkin (privacy posture) |
| WO-ML-02 — Language metadata in Archive | OmniSONAR (cross-lingual schema), Sidon (multilingual audio reality) |
| WO-ML-03 — Lori language mirror directive | Memoro (minimal disruption), OmniSONAR (cross-modal foundation) |
| WO-ML-04 — Narrator-facing Spanish UI labels | DIRHA, Tabassum, Malkin |
| WO-ML-05 — Spanish safety floor | privacy/ASR papers indirectly; primary grounding will come from the Spanish-speaking clinician's review (lined up) and Spanish clinical/safety sources to be added when reviewed |
| WO-ML-06 — Bilingual memoir / export shell | OmniSONAR (cross-lingual semantic bridge); OmniVoice (later, spoken output) |
| WO-ML-PRIVACY-ASR-01 — Narrator-controlled redaction (NEW, future) | Roy & Vu (Listen, But Don't Leak) |

---

## Phased build (sequencing locked)

### Phase 1 — Whisper STT integration (~3 days)

**What:** Replace Web Speech API in the frontend with backend calls to existing `/api/stt/transcribe` route. Audio chunks already flow to backend via `narrator-audio-recorder.js`; this phase splits off the recognition step from the storage step.

**Why first:** This is the foundation. Without Whisper as the live STT, narrators speaking Spanish are mistranscribed by Web Speech (which assumes en-US). Every other phase is amplification of this base.

**Spec:**

#### 1A — Backend route audit + extension
- Verify `/api/stt/transcribe` returns the detected language code in the response. faster-whisper's `info.language` is per-segment; the route should bubble it up.
- Add a `lang` request param that ACCEPTS `auto` (default) or a specific 2-letter code (`en`, `es`, etc.). When `auto`, Whisper auto-detects.
- Add a `prompt` param for biasing context. Useful for ELL narrators where the operator can pass "narrator is Spanish-speaking" to nudge Whisper.

#### 1B — Frontend audio streaming to Whisper
- New module `ui/js/whisper-stt.js`:
  - Replaces the `_ensureRecognition()` factory in app.js
  - Accumulates webm chunks every ~2s
  - POSTs each chunk to `/api/stt/transcribe` with `lang=auto`
  - Emits events that mimic Web Speech's `onresult` shape: `{interim, final, language, confidence}`
  - When `final` arrives, fires the same `_appendVoiceTurnChunk` logic
- Feature flag: `LV_USE_WHISPER_STT=1` (default off). When off, behavior is unchanged Web Speech. When on, Whisper is the engine.
- Operator UI toggle: per-narrator setting "Speech recognition: Web Speech (English only) / Whisper (any language)".

#### 1C — Latency + UX
- Web Speech is faster (interim results within 200ms). Whisper-large-v3 round-trip is 1-3s for a 2s chunk. Compensate with:
  - Larger interim buffer (Whisper-tiny for live preview, Whisper-large for final)
  - OR: chunked Whisper (Whisper handles streaming via `transcribe_streaming` in faster-whisper)
- For first-time narrators, default to Whisper-medium (better en than Web Speech, latency ~500ms-1s).

**Acceptance gates:**
- Smoke: 5 Spanish utterances from a recorded sample → Whisper transcribes correctly → emits `language=es` in response → frontend renders text in Spanish
- Smoke: 5 code-switched utterances → Whisper handles mid-utterance language change correctly
- Existing English narrators (Mary, Marvin) work unchanged (regression check)

**Files modified:**
- `server/code/api/routers/stt.py` — confirm/extend response shape
- `ui/js/whisper-stt.js` — NEW
- `ui/js/app.js` — feature-flagged STT swap in `_ensureRecognition` / `toggleRecording`
- `.env` — `LV_USE_WHISPER_STT` flag added

---

### Phase 2 — Multilingual Lori directive (~half day)

**What:** Single rule added to the system prompt instructing Lori to respond in the language the narrator just used.

**Why:** Llama-3.1-8B already handles Spanish + English fluently. The model just needs to know it should mirror narrator's language choice.

**Spec:**

#### 2A — Composer directive
In `compose_system_prompt` (prompt_composer.py), at the top of the directive block:

```
LANGUAGE MIRRORING RULE:
- Respond in the language the narrator most recently used.
- If the narrator code-switches between languages within a single
  message, mirror their pattern naturally — do not "correct" them
  back to a single language.
- Never translate the narrator's own words back at them. If they
  said "mi mamá," reflect that as "mi mamá" in your response, not
  "your mom."
- Apply your existing behavioral rules (warmth, brevity, one
  question per turn) regardless of language.
```

#### 2B — Smoke verification
- Mary in English → English response (regression check)
- Spanish prompt → Spanish response from Lori
- Mid-conversation switch → Lori switches with the narrator

**Acceptance:** 5/5 Spanish-language narrator turns produce Spanish responses; 5/5 English regression cases unchanged.

**Files modified:**
- `server/code/api/prompt_composer.py` — add directive block

---

### Phase 3 — Storage + UI labels (~3 days)

**What:** Add `language` field to every transcript turn and story_candidate row. Translate era warm labels + continuation phrases for en/es. Add `primary_language` to profile_seed.

**Spec:**

#### 3A — Database migration
New migration `0006_story_language.sql`:
```sql
ALTER TABLE story_candidates ADD COLUMN language TEXT;
ALTER TABLE turns ADD COLUMN language TEXT;
```

#### 3B — Archive turn shape
`archive.append_event()` accepts optional `language` kwarg. Written to JSONL turn record.

#### 3C — Story preservation
`preserve_turn()` accepts `language` kwarg. Written to story_candidate row + `metadata.json` in stories-captured/.

#### 3D — Era label translations
`lv_eras.py` adds `_LV_ERA_WARM_LABELS_BY_LOCALE` and `_LV_ERA_CONTINUATION_PHRASES_BY_LOCALE` dicts. Both functions accept optional `locale` parameter. Initial locales: `en`, `es`.

```python
_LV_ERA_WARM_LABELS_BY_LOCALE = {
    "en": {
        "earliest_years": "Earliest Years",
        "early_school_years": "Early School Years",
        "adolescence": "Adolescence",
        "coming_of_age": "Coming of Age",
        "building_years": "Building Years",
        "later_years": "Later Years",
        "today": "Today",
    },
    "es": {
        "earliest_years": "Primeros Años",
        "early_school_years": "Años de Escuela Primaria",
        "adolescence": "Adolescencia",
        "coming_of_age": "Mayoría de Edad",
        "building_years": "Años de Construcción",
        "later_years": "Años Posteriores",
        "today": "Hoy",
    },
}
```

#### 3E — profile_seed
Add `primary_language` field set by operator at narrator creation. Auto-detected from first 5 turns if not set explicitly. Determines:
- Operator UI labels for that narrator
- Memoir export default language
- Era warm labels in Lori's responses

**Acceptance gates:**
- Schema migration applies cleanly to existing DB
- New transcript turns carry `language` field
- Era warm labels render in Spanish when `locale=es`
- Existing English narrators unchanged

**Files modified:**
- `server/code/db/migrations/0006_story_language.sql` — NEW
- `server/code/api/archive.py` — `language` kwarg
- `server/code/api/services/story_preservation.py` — `language` kwarg + write to row + metadata
- `server/code/api/lv_eras.py` — locale-aware label/phrase lookup
- `server/code/api/db.py` — story_candidate_insert + turn writers accept language

---

### Phase 4 — Safety patterns + memoir export (~5-7 days)

**What:** Spanish acute-pattern set in safety.py (highest-risk surface). Bilingual memoir export templates.

**Spec:**

#### 4A — Spanish safety patterns (HIGHEST PRIORITY)
- **Authored from scratch with Spanish-speaking mental-health clinician's review.** Not a literal translation of English patterns; idiomatic expressions vary by region. Clinician contact lined up by Chris (confirmed 2026-05-07).
- Test corpus: ~30 cases across Mexican / Caribbean / Castilian Spanish, authored by the agent and verified by the clinician before production landing.
- LLM second-layer classifier (already in place from #3 SAFETY-INTEGRATION-01 Phase 2) handles deterministic-pattern misses; it currently fails-OPEN (routes to safety mode under parse failure), which is the right posture for this surface.
- Verified clinical/safety sources for Spanish-speaking elders TO BE ADDED to this section when the clinician's review surfaces them. Until then, **the clinician's review IS the citation** — no placeholder academic refs.

#### 4B — Multilingual memoir export
- Template per language: `memoir_template_en.docx`, `memoir_template_es.docx`
- Bilingual side-by-side mode: render narrator content in primary language, with optional translation in secondary column
- Operator UI at export time: "Export language: English / Spanish / Bilingual side-by-side"
- Language inference from `primary_language` if not specified

**Acceptance gates:**
- Spanish safety pattern set reviewed + approved by clinician
- 30/30 Spanish acute test cases route to safety mode
- Zero false-positives on the "tired of life" / passive-death-wish class (those should NOT route to acute — see `WO-LORI-SAFETY-PASSIVE-DEATH-WISH-01_Spec.md` for the distinction already locked for English)
- Memoir exports in en, es, and bilingual modes render cleanly

---

### Phase 5 — Extraction multilingualization (~5-7 days)

**What:** Spanish variants of correction parser, story_trigger anchors, name extraction, era explainer, phantom-noun whitelist.

**Spec:**

#### 5A — Correction parser Spanish patterns
Already documented in code-review snapshot. Direct mapping of English patterns to Spanish:
- "nací en X" — I was born in X
- "mi padre se llamaba X" — my father's name was X
- "tuvimos N hijos" — we had N kids
- "sólo tuvimos N hijos, no M" — only had N kids, not M (Melanie's exact pattern in Spanish)
- "no había X" — there was no X
- "nunca dije X" — I never said X
- "quería decir X, no Y" — I meant X, not Y

#### 5B — Story trigger Spanish anchors
- Place patterns: "en X" (in X), "fui a X" (went to X), "vivíamos en X" (we lived in X)
- Time patterns: "cuando era niña/o" (when I was a child), "en aquel tiempo" (at that time), "durante la guerra" (during the war)
- Person patterns: "mi mamá" / "mi papá" / "mi abuela" / "mi hermano" / etc.

#### 5C — Phantom-noun whitelist Spanish
- Days: Lunes, Martes, Miércoles, etc.
- Months: Enero, Febrero, etc.
- Family: Mamá, Papá, Abuela, Abuelo, Hermana, Hermano, Tía, Tío, etc.
- Religious: Dios, Jesús, María, Cristo
- Holidays: Navidad, Pascua, Día de los Muertos
- Place: México, España, Cuba, Argentina, los Estados Unidos

#### 5D — compose_correction_ack Spanish
Translate the value-aware acknowledgments:
- "Got it — N children, not the number I had down" → "Entendido — N hijos, no el número que tenía"
- "Thanks for catching that" → "Gracias por corregirme"

**Acceptance:** 30/30 Spanish correction smokes pass; story_trigger fires for 5/5 Spanish anchored stories; existing English regression tests pass unchanged.

---

## Future / parked work order

### WO-ML-PRIVACY-ASR-01 — narrator-controlled redaction
**Status:** parked (not v1).
**Grounded in:** Roy & Vu (2026), "Listen, But Don't Leak" (ICASSP 2026, IEEE DOI 10.1109/ICASSP55912.2026.11461572).
**Concept:** narrator can mark speech as private — via UI button or acoustic trigger — before it enters the archive. Whisper substitutes a `<Redacted>` token at the ASR layer, transcript stores the redaction, audio file is either dropped or stored under the `sacred_do_not_persist` policy from WO-DISCLOSURE-MODE-01. Roy & Vu report 99.47% utterance-level / 97.7% phrase-level redaction success with negligible degradation on non-sensitive speech, which is the proof-of-concept this WO would build on.
**Why parked:** v1 multilingual scope (Phases 1–5 above) does not need narrator-controlled redaction at the ASR layer. The current `sacred_do_not_persist` enum + clinician-reviewed safety patterns + LLM second-layer classifier give the safety floor a defensible posture. WO-ML-PRIVACY-ASR-01 is a Phase 6+ feature that lets a narrator deliberately keep a memory off the record without operator intervention — useful, but not blocking.
**Trigger to reactivate:** first real narrator request for a "don't transcribe this" surface; OR clinician review of Phase 4 Spanish patterns surfaces a category where pre-archive redaction is the only safe path.

---

## Total scope + timing

| Phase | Days | What it unlocks |
|---|---|---|
| 1 — Whisper STT | 3 | 99-language transcription, code-switching, ELL accuracy |
| 2 — Multilingual Lori | 0.5 | Lori responds in narrator's language |
| 3 — Storage + UI labels | 3 | Persistent language tagging, narrator-friendly era labels |
| 4 — Safety + memoir | 5-7 | Safety floor in Spanish (HIGH RISK if skipped), bilingual memoir export |
| 5 — Extraction multilingualization | 5-7 | Story trigger + correction + phantom-noun work in Spanish |
| **Total** | **~3 weeks** | **End-to-end multilingual Lorevox** |

Each additional language beyond es: ~1-2 weeks (mostly safety patterns + extraction; STT, storage, prompt are language-agnostic after Phases 1-3).

---

## What we ship after each phase

After Phase 1: Spanish/French/German/etc. narrators can SPEAK and have it correctly transcribed. Lori still responds in English.

After Phase 2 (4 days total): Lori responds in narrator's language. End-to-end voice-in voice-out works for any of Whisper's 99 languages, modulo safety risks (Phase 4).

After Phase 3 (1 week total): Persistent language tagging + narrator-friendly era labels. Operator can see narrator's language in the UI.

After Phase 4 (~2 weeks total): Safety floor in Spanish. Bilingual memoir export. **Production-ready for Spanish-speaking narrators.**

After Phase 5 (~3 weeks total): Story-trigger + correction-applied + phantom-noun guard work in Spanish. Edge-case extraction polish. **Production-ready for ELL Spanish-speaking elders specifically (Melanie's use case).**

---

## Risks + mitigations

1. **Whisper accent quality variance.** Cuban Spanish vs Mexican Spanish vs Castilian Spanish transcribe slightly differently. **Mitigation:** narrator profile field `accent_family` set at creation; Whisper takes a `lang` hint that includes regional variant when available. Per-narrator confidence threshold tunable.

2. **Code-switching mistagging.** Whisper occasionally tags a single Spanish-sounding English word as Spanish. **Mitigation:** confidence threshold; below 0.7 fields are flagged for operator review.

3. **Safety regression in Spanish.** False-negatives on suicidal ideation = harm. **Mitigation:** Phase 4 BLOCKS production for Spanish-speaking narrators until clinician review of patterns is complete.

4. **Memoir family-readability.** Grandkids who don't speak Spanish need a translation. **Mitigation:** LLM-generated translation (Llama-3.1-8B competent for memoir-quality output) + operator review checkbox at export time.

5. **Cultural kinship preservation.** Phase 5 Spanish whitelist alone doesn't preserve cultural nuance ("mi tía" used as character name in Lori's response is fine; "your aunt" loses warmth). **Mitigation:** Phase 5D composer translations preserve narrator-volunteered terms verbatim; voice-library cultural-context cases (already in repo) exercise this.

6. **GPU contention.** Whisper-large-v3 + Llama-Q4 share the 16GB RTX 5080. Concurrent inference could push memory limits. **Mitigation:** verify VRAM with current models loaded; if needed, downgrade Whisper to medium for live STT (still better than Web Speech) and reserve large-v3 for batch / archival re-transcription.

---

## Success metrics

**Phase 1 success:** 5/5 Spanish utterances from a recorded test set transcribe correctly with `language=es` in response. Latency under 2s on the laptop.

**Phase 2 success:** 5/5 Spanish-language narrator turns produce Spanish responses. Mary + Marvin English regression unchanged.

**Phase 3 success:** Schema migration clean. Era labels display in Spanish for narrators with `primary_language=es`.

**Phase 4 success:** Spanish safety pattern set reviewed and approved by Spanish-speaking clinician. Zero false-positives on the passive-death-wish / "tired of life" class (per the English distinction already locked in `WO-LORI-SAFETY-PASSIVE-DEATH-WISH-01_Spec.md`, ported to Spanish). Bilingual memoir export rendering cleanly.

**Phase 5 success:** All Spanish extraction smokes pass; English regression unchanged.

**Whole-project success:** Melanie Zollner does a 30-minute session in Spanish + English code-switched, ends with a memoir draft her family can read. End-to-end works as designed.

---

## Sequencing relative to other ongoing work

- **#50 mic-modal Phase B + C** (~5 hrs) ships first — completes the dictation UX foundation that Whisper STT plugs into. Parent-session readiness benefit.
- **Auto-punctuation + auto-cap** (~2 days) ships in parallel with Phase 1+2 — different code paths, language-agnostic.
- **Bilingual Phase 1+2** (~4 days) — start immediately after #50 Phase B+C lands.
- **WO-ENV-SPLIT-SHARED-01** (~1-2 hrs) — quality-of-life improvement, slot in whenever convenient.

Total active build through end-of-month: ~3 weeks of focused work to ship Lorevox-Multilingual v1 (en + es). Ambitious but tractable — most of the heavy lifting is hooking up models that already exist (Whisper, Llama-3.1-8B), not building new ones.

---

## What I need from Chris

- Approval on this plan
- Spanish-speaking mental-health clinician contact for Phase 4 safety review (you'll need this lined up before Phase 4 starts; that's ~2 weeks out from today)
- Confirmation of test narrator pool: Melanie Zollner is one; ideally we'd have 2-3 more native Spanish speakers willing to record 30-min sessions for QA. Their families benefit from the memoir output as compensation.
- Decision on Phase 5 scope: do we ship Spanish-only extraction polish, or build a parallel French / German skeleton at the same time? Marginal cost is small if we structure the lookup tables right.

The next concrete move: start Phase 1 build (Whisper STT integration, ~3 days). The route exists; the work is wiring the FE and verifying latency targets on the laptop's GPU.
