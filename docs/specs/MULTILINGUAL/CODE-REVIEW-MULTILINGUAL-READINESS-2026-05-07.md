# Code Review — Multilingual Readiness Snapshot

**Date:** 2026-05-07
**Author:** Claude (dev computer)
**Scope:** Audit every surface in the Hornelore codebase that assumes English as the only language. Inventory what changes, what stays, and where new translation tables / language-tag fields need to land.

This doc is the foundation for `BILINGUAL-PROJECT-PLAN.md`. The plan references this audit; the build sequence follows from it.

---

## TL;DR — readiness state

| Surface | English-locked? | Effort to multilingualize | Phase |
|---|---|---|---|
| **Audio capture** (narrator-audio-recorder.js) | No (language-agnostic webm) | None | — |
| **STT runtime** (Web Speech API) | **Yes — `lang=en-US`** | Replace with Whisper backend | Phase 1 |
| **Whisper backend route** (/api/stt/transcribe) | **Already multilingual** (faster-whisper) | Wire FE to use it | Phase 1 |
| **Transcript JSONL** (archive.append_event) | UTF-8 strings, language-blind | Add `language` field | Phase 3 |
| **Story candidates** (story_preservation.py) | UTF-8 strings, language-blind | Add `language` field on row | Phase 3 |
| **profile_seed** (chat_ws + prompt_composer) | English keys (preferred_name etc.) | Keys stay; values are language-blind | — |
| **prompt_composer directives** (Lori behavior rules) | **Yes — heavily English** | Add multilingual directive + translation table | Phase 2 |
| **Era warm labels** (lv_eras.py) | **Yes — English warm labels** | Add `_LV_ERA_WARM_LABELS_BY_LOCALE` dict | Phase 3 |
| **Continuation paraphrase phrases** (lv_eras.py) | **Yes — English phrases** | Same translation table | Phase 3 |
| **Correction parser regex** (memory_echo.py) | **Yes — English patterns** | Multilingual variant per-language | Phase 5 (extraction lane) |
| **Safety classifier patterns** (safety.py) | **Yes — English regex** | High priority — safety must not regress in any language | Phase 4 |
| **Story-trigger anchor detection** (story_trigger.py) | **Yes — English place/time/person bigrams** | Multilingual variant | Phase 5 |
| **Memoir export templates** | **Yes — English headers/labels** | Template per language + bilingual side-by-side mode | Phase 4 |
| **Operator UI labels** | **Yes — English** | Out of scope for v1 (operator is the developer or family member) | Defer |
| **CLAUDE.md design principles** | English | Reference doc — translates as policy, not runtime | Defer |

**Net:** the **data layer is already language-neutral** (UTF-8 throughout). The **STT layer needs replacing** (1 frontend swap to existing Whisper backend). The **prompt + extraction layers need multilingual extension** (medium effort, language-by-language). The **memoir export** is template work.

---

## Detailed findings by file

### `ui/js/app.js`
Lines using Web Speech API (browser-side, en-US default):
- `L6185`: `const SR = window.SpeechRecognition || window.webkitSpeechRecognition;`
- `L6226`: `recognition.onend = () => { if(isRecording && !isLoriSpeaking) { try { recognition.start(); } catch(e) {} } };`
- `L7074, L7751`: `recognition.start();`
- `L8229`: `const hasSR = !!(window.SpeechRecognition || window.webkitSpeechRecognition);`
- `ui/js/photo-elicit.js:367`: `recognition.lang = (navigator.language || "en-US");` — defaults to navigator.language at least

**Assessment:** Web Speech is the runtime STT today. The `.env` has `STT_MODEL=large-v3` but it's not wired through to live capture — only to file-based transcription via `/api/stt/transcribe`.

**Action (Phase 1):** swap Web Speech for streaming-chunked uploads to `/api/stt/transcribe`. Audio recorder already chunks webm; the chunks just need to flow through Whisper instead of (or in addition to) Web Speech.

---

### `server/code/api/routers/stt.py`
Route already exists. Faster-whisper preferred, openai-whisper fallback. Model + device configurable via env. Multipart endpoint at `POST /api/stt/transcribe` accepts `file`, `lang`, `initial_prompt`.

**Assessment:** **Already multilingual.** Whisper-large-v3 transcribes 99 languages with auto-detection. No code change here for Phase 1.

**Action (Phase 1):** confirm route is mounted in `main.py`; verify it returns language code in response (need to inspect — likely already does via faster-whisper's `info.language` field).

---

### `server/code/api/archive.py` — `append_event()`
JSONL turn shape (lines 146-167):
```json
{
  "ts": "2026-05-07T...",
  "role": "user|assistant",
  "content": "<UTF-8 text>",
  "current_era": "...",
  "audio_id": "..."
}
```

**Assessment:** content is UTF-8, era_id is canonical English (which is correct — era_id is a programmatic identifier, not a display label).

**Action (Phase 3):** add optional `language` field (`"en"`, `"es"`, `"fr"`, etc., or `"mixed"` for code-switching). Backward-compatible: turns without `language` are still readable; downstream consumers default to operator's language preference.

---

### `server/code/api/services/story_preservation.py`
DB row fields per `story_candidate_insert()`: candidate_id, narrator_id, transcript, audio_clip_path, audio_duration_sec, word_count, trigger_reason, scene_anchor_count, era_candidates, age_bucket, etc.

**Assessment:** transcript is UTF-8 string. No language field today.

**Action (Phase 3):** add `language` column to `story_candidates` table (migration `0006_story_language.sql`). Default `NULL` (= unknown / mixed). story_preservation.preserve_turn() accepts `language` kwarg, passes to insert.

---

### `server/code/api/services/story_trigger.py`
Anchor detection looks for English place / relative-time / person bigrams. Per `_PLACE_NOUNS` / `_PLACE_ALIAS_PREP_RX_TEMPLATE` etc.

**Assessment:** **Heavily English-locked.** A Spanish story like "Cuando vivíamos en Lima, mi abuela hacía pan los domingos" has place + person + relative-time anchors but the English bigram detector won't fire. The story_trigger fails to fire → no story_candidate row, no audio.webm copy in stories-captured/.

**Action (Phase 5 — extraction lane):** add per-language anchor patterns. Spanish first (en/es covers ~95% of NM use case), then French / German / Portuguese as demand surfaces. ~2-3 days per language.

---

### `server/code/api/memory_echo.py` — `parse_correction_rule_based()`
Patterns added today (#56 Phase 3):
- `i was born in <X>$`
- `my father was <X>` / `my father's name was <X>`
- `i had N children`
- `we only had N children, not M`
- `there was no <X>`
- `i never said <X>`
- `i meant X not Y`

**Assessment:** **All English regex.** A Spanish narrator saying "no tuvimos tres niños, sólo dos" hits zero patterns.

**Action (Phase 5):** Spanish variants:
- `nací en <X>$` (I was born in)
- `mi padre se llamaba <X>` / `mi madre se llamaba <X>`
- `tuvimos N hijos`
- `sólo tuvimos N hijos, no M` (only had N kids, not M — MELANIE'S EXACT PATTERN IN SPANISH)
- `no había <X>` / `nunca había <X>` (there was no X)
- `nunca dije <X>` (I never said X)
- `quería decir X, no Y` (I meant X, not Y)

---

### `server/code/api/safety.py` (and related safety_classifier)
Acute-pattern set per CLAUDE.md: 50+ regex patterns, 7 categories (suicidal_ideation, self_harm, abuse, etc.).

**Assessment:** **All English.** This is the highest-risk monolingual surface. A Spanish-speaking narrator expressing suicidal ideation in Spanish would be invisible to the deterministic safety layer. The LLM second-layer classifier (#3 SAFETY-INTEGRATION-01 Phase 2) catches some cases but isn't a substitute for the deterministic floor.

**Action (Phase 4 — HIGHEST PRIORITY):** Spanish acute patterns first. Coordinate with subject-matter expert (Spanish-speaking mental health clinician) — the patterns aren't direct translations; they're idiomatic expressions of distress that vary by region (Mexican Spanish vs Caribbean Spanish vs Castilian).

Reference: clinician-led pattern authoring is the primary grounding (Spanish-speaking mental-health clinician confirmed lined up by Chris, 2026-05-07). Verifiable Spanish clinical/safety sources will be added to this section when the clinician's review surfaces them. The fail-OPEN posture of the LLM second-layer classifier (SAFETY-INTEGRATION-01 Phase 2) routes parse failures to safety mode by default — that is the right posture during the gap between English-only patterns landing and Spanish patterns being clinician-reviewed.

---

### `server/code/api/lv_eras.py` — era labels + continuation phrases
- `era_id_to_warm_label("earliest_years")` → "Earliest Years"
- `era_id_to_continuation_phrase("building_years")` → "your building years"

**Assessment:** **English-locked** but cleanly factored — a single dict `_LV_ERA_WARM_LABELS` (and continuation phrase dict) controls the full surface.

**Action (Phase 3):** add `_BY_LOCALE` variants:
```python
_LV_ERA_WARM_LABELS_BY_LOCALE = {
    "en": {"earliest_years": "Earliest Years", ...},
    "es": {"earliest_years": "Primeros Años", ...},
    "fr": {"earliest_years": "Premières Années", ...},
}
```
Function takes optional `locale` parameter, defaults to `en`. Operator UI sets locale per narrator.

---

### `server/code/api/prompt_composer.py`
The big one. Lori's behavioral directives are written in English throughout. Examples:
- "TRANSPARENCY RULE — If the narrator directly asks whether..."
- "IDENTITY MODE: Lori is gently gathering who the narrator is..."
- "RULE — EMOTIONAL STATEMENTS: If the narrator's message expresses sadness..."
- "GROUNDING RULE: When narrator's profile_seed has childhood_home..."

**Assessment:** Llama-3.1-8B handles English directives + Spanish narrator content well — the LLM does language-mirroring naturally. Adding ONE meta-directive at the top of the system prompt unlocks bilingual response without translating every rule:

> "RESPOND IN THE LANGUAGE THE NARRATOR JUST USED. If the narrator code-switches naturally between languages, mirror their pattern in your response. Never translate the narrator's words back at them — preserve the language they chose."

**Action (Phase 2):** add this single directive. Test with 5-narrator Spanish sample. The existing English directives stay; they instruct Lori's BEHAVIOR, not her output language.

The few-shots in `_NARRATIVE_FIELD_FEWSHOTS` and similar are extraction-time, not chat-time — they affect what the extractor recognizes as a fact, not what Lori says back. Multilingual extraction is Phase 5.

---

### `server/code/api/services/lori_communication_control.py`
- `_PHANTOM_NOUN_WHITELIST` (just landed) — English whitelist (Tuesday, Mom, Christmas, etc.)
- `_truncate_to_word_limit` / sentence-boundary walk — language-agnostic regex
- `compose_correction_ack` — English prose

**Assessment:** Whitelist needs Spanish equivalents (Lunes, Mamá, Navidad). Sentence-boundary walk works in any language with `.!?`. Composer is English-locked.

**Action (Phase 5):** multilingual whitelist + composer translations.

---

### Memoir export
File: `server/code/api/services/peek_at_memoir.py` exists but is the read accessor. Actual memoir generation may live elsewhere (need to grep for docx/pdf templates).

**Assessment:** Likely English templates (.docx). Would need bilingual layout for descendant audiences.

**Action (Phase 4):** language-aware memoir templates + bilingual side-by-side option. Operator picks single-language or bilingual at export time.

---

## Summary by phase

**Phase 1 (3 days) — Whisper STT integration:** Replace Web Speech with backend Whisper. Existing route is the target. FE work is ~80% of this; backend is already there.

**Phase 2 (half day) — Multilingual Lori directive:** Single rule added to prompt_composer top of system prompt. Smoke-test with Spanish narrator turns.

**Phase 3 (3 days) — Storage + UI labels:** `language` field on transcript turns + story_candidates. Era warm labels translated for `en`/`es` first. profile_seed gets `primary_language` field.

**Phase 4 (5-7 days) — Safety + memoir:** Spanish acute-pattern set in safety.py (highest risk surface). Bilingual memoir export templates. Operator UI for language selection per narrator.

**Phase 5 (5-7 days, extraction lane) — Extraction multilingualization:** Spanish variants of correction parser, story_trigger anchors, name extraction, era explainer, phantom-noun whitelist. Per-language unit smokes.

**Total:** ~3 weeks engineering for solid bilingual support (en + es). Each additional language: ~1-2 weeks (mostly safety pattern + extraction work; STT and storage and prompt are language-agnostic after Phase 1+2).

---

## What this DOESN'T need

- New database. SQLite + UTF-8 handles any language already.
- New model. Whisper-large-v3 is in `.env` already; Llama-3.1-8B-Instruct is multilingual.
- New compute. 16GB RTX 5080 fits Whisper-large-v3 on the GPU alongside Llama (~5GB Whisper + ~5GB Llama-Q4 + ~2GB headroom).
- New auth / privacy model. Per-narrator consent already in place; doesn't change with language.
- Internationalized operator UI. The operator (Chris, eventually family members) is bilingual or works in their own language. v1 keeps operator UI English.

---

## Risks worth naming

1. **Whisper quality varies by accent.** Cuban Spanish vs Mexican Spanish vs Castilian Spanish vs Argentinian Spanish all transcribe slightly differently. The narrator's `accent_family` should be a profile field; STT uses it to weight model bias if available (Whisper supports `language` hint but not regional dialect bias directly).

2. **Code-switching edge cases.** Whisper occasionally mis-tags the language on a single word that "sounds like" the other language. Example: "I went to la tienda" might come back tagged as Spanish if "I went to la" sounds like Spanish prosody. The transcript turn carries Whisper's confidence; below 0.7 should be flagged for operator review.

3. **Cultural kinship terms.** Spanish narrators often say "mi tía" (my aunt) or "mi nana" (grandma — regional). If Lori's rules expand to include these as proper-noun candidates without context, the phantom-noun guard could flag them. Phase 5 work + cultural-context corpus (already partly in CLAUDE.md voice library work) handles this.

4. **Memoir family-readability.** Grandkids who don't speak Spanish need a translation. LLM-generated translation is competent but not perfect; needs human review by the operator (or a bilingual family member) before final memoir ships.

5. **Safety regression.** Spanish patterns must be vetted by a native Spanish-speaking clinician before they reach production. False negatives in safety = real harm.

---

## What we'll know after Phase 1+2 (1 week)

- Does Whisper transcribe Melanie Zollner's actual recorded turns better than Web Speech did? (Compare against the 30+ webm files we already have from her session.)
- Does Llama-3.1-8B respond fluently in Spanish when narrator speaks Spanish?
- Does code-switching work end-to-end on a real session?

These are testable on the laptop within a week of Phase 1+2 landing. That data informs whether Phase 3+4+5 are worth the full investment OR whether we want to scope down to en + es only.
