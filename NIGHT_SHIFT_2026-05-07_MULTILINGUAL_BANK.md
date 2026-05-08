# Night-shift 2026-05-07 — Multilingual phase 5 + bug hunt

**Status:** complete, ready for Chris to commit + push from `/mnt/c/Users/chris/hornelore`. Stack down throughout night-shift. All test packs green.

---

## Summary

Banked 5 multilingual phases + 4 bug specs + a README update + a comprehensive code review during one autonomous block. Live testing pending stack restart.

| Item | Type | Files | Tests |
|---|---|---|---|
| BUG-ML-LORI-SPANISH-FRAGMENT-REPAIR-02 | bug fix | `lori_spanish_guard.py` + tests | 9 new (57 total green) |
| BUG-ML-SHADOW-EXTRACT-PLACE-AS-BIRTHPLACE-01 | bug fix | `extract.py` + new test file | 26 new |
| Phase 5C completion (verified) | already-banked | `app.js` | 28-case node probe green |
| Phase 5D — Spanish phantom-noun whitelist | feature | `lori_communication_control.py` + new test file | 15 new |
| Phase 5E — compose_correction_ack Spanish | feature | `prompt_composer.py` + `lori_spanish_guard.py` (extended detection) + new test file | 9 new |
| Phase 5F — Code-switching test fixtures | feature | `data/evals/lori_code_switching_eval.json` + new test file | 14 new |
| README — Multilingual section | doc | `README.md` | n/a |
| BUG-ML-LORI-CORRECTION-PARSER-VALUE-OVERCAPTURE-01 | spec only | `BUG-...-01_Spec.md` (new) | n/a |
| BUG-ML-LORI-DETERMINISTIC-COMPOSERS-ENGLISH-ONLY-01 | spec only | `BUG-...-01_Spec.md` (new) | n/a |
| BUG-ML-LORI-SPANISH-FRAGMENT-REPAIR-02 spec | doc | `BUG-...-02_Spec.md` (new) | n/a |
| BUG-ML-SHADOW-EXTRACT-PLACE-AS-BIRTHPLACE-01 spec | doc | `BUG-...-01_Spec.md` (new) | n/a |

**Net test count:** 261 tests across the 7 packs touched, all green.

---

## What landed (in commit-able order)

### Commit 1 — BUG-ML-LORI-SPANISH-FRAGMENT-REPAIR-02

Add demonstrative determiners (`esas, esos, esa, ese, estas, estos, esta, este, aquellas, aquellos, aquella, aquel`) and additional possessives (`mi, mis, tu, tus, nuestra, nuestro, nuestras, nuestros`) to the fragment guard's `_FRAGMENT_CONNECTORS`. New `_has_unclosed_spanish_question(text)` helper counts `¿` vs `?` openers; the fragment guard now closes a trimmed fragment with `?` when there's an unclosed `¿` upstream, otherwise `.` (existing behavior). Live failure: *"¿Qué recuerdas de cómo sonaba su voz cuando contaba esas."* now repairs to *"¿Qué recuerdas de cómo sonaba su voz cuando contaba?"*.

Files:
- `server/code/api/services/lori_spanish_guard.py`
- `tests/test_lori_spanish_guard.py` (+9 tests)
- `BUG-ML-LORI-SPANISH-FRAGMENT-REPAIR-02_Spec.md` (new)

### Commit 2 — BUG-ML-SHADOW-EXTRACT-PLACE-AS-BIRTHPLACE-01

Post-LLM regex guard mirroring BUG-EX-PLACE-LASTNAME-01 architecture. Drops `*.birthPlace` / `*.placeOfBirth` candidates whose value appears in source text only after narrative-connection verbs (English: `talked about, missed, remembered, stories of`; Spanish: `hablaba de, extrañaba, recordaba, contaba historias de`) and never with explicit birth-evidence (English: `was born in/at/near`; Spanish: `nació en, era de, originario de, vino al mundo en`). Whisper accent-strip variants included. Sibling lane to PLACE-LASTNAME-01; runs independently (no SPANTAG flag).

Files:
- `server/code/api/routers/extract.py` (+~150 lines: `_NARRATIVE_CONNECTION_PHRASES` + `_BIRTH_EVIDENCE_PHRASES` + 3 helpers + drop-call wire)
- `tests/test_extract_place_birthplace_guard.py` (new, +26 tests)
- `BUG-ML-SHADOW-EXTRACT-PLACE-AS-BIRTHPLACE-01_Spec.md` (new)

### Commit 3 — Phase 5D: Spanish phantom-noun whitelist

Extended `_PHANTOM_NOUN_WHITELIST` with Spanish kinship (`Mamá, Abuela, Tía, Hijo`), calendar (`Lunes, Enero, Verano`), religious (`Dios, Cristo, Virgen`), holiday (`Navidad, Pascua`), and Q-word (`Qué, Cuándo, Dónde`) tokens. Crucially did NOT whitelist real personal names (`María, José, Núñez`) or country names (`México, España, Perú, Cuba`) — those go through the narrator-corpus / profile-seed verification gate instead. Mid-sentence proper-noun detection regex now accepts Spanish accent capitals (`Á É Í Ó Ú Ñ`) so multi-word Spanish names get detected; the whitelist filters out culturally-frequent kinship/calendar tokens after detection.

Files:
- `server/code/api/services/lori_communication_control.py` (whitelist + regex extensions)
- `tests/test_phantom_noun_spanish.py` (new, +15 tests)

### Commit 4 — Phase 5E: compose_correction_ack Spanish

Added `looks_spanish()` detection at the top of `compose_correction_ack`. When narrator's correction text is Spanish, emits Spanish acknowledgments instead of code-switched English: *"Lo entiendo — dos hijos, no el número que tenía. Disculpa la confusión."* / *"Gracias por corregirme — no debí haber dicho 3."* / *"Oí eso como una corrección. ¿Podrías decirme qué te gustaría que cambie?"* (no-parse fallback). Number words emit Spanish (`uno, dos, tres, ...`). Field labels translate (`tu padre era X` / `tu madre era X` / `naciste en X` / `nunca te jubilaste del todo`).

To support detection on Spanish text without accents, extended `looks_spanish()`'s function-word list with high-confidence Spanish-only tokens: present-tense verbs (`tengo, tienes, tenemos, tienen`), preterite (`dijo, vine, hice, quiso`), imperfect (`vivía, hablaba, decía`), infinitives (`decir, hablar, vivir, escribir`), and number words 2-15 + 20/30/100/1000 (`dos, tres, cuatro, ..., quince, veinte, cien, mil`).

Files:
- `server/code/api/prompt_composer.py` (Spanish branch in `compose_correction_ack`)
- `server/code/api/services/lori_spanish_guard.py` (extended `_SPANISH_FUNCTION_WORDS` list)
- `tests/test_compose_correction_ack_spanish.py` (new, +9 tests)

### Commit 5 — Phase 5F: Code-switching test fixtures

12-case eval pack covering EN→ES intro, ES→EN emotional shift, ES correction after EN Lori turn, pure-Spanish birthplace + father-name + mother-name + meant-pattern corrections, ES grandmother-narrative (BUG-ML-SHADOW-EXTRACT-PLACE-AS-BIRTHPLACE-01 evidence case), code-switch with kinship-term gloss, phantom-noun avoidance, short Spanish "sí" confirmation, mid-sentence language flip, dangling demonstrative question close, full Spanish multi-detail intro. Each case carries `expected_*` assertions covering the full multilingual pipeline.

Files:
- `data/evals/lori_code_switching_eval.json` (new, 12 cases)
- `tests/test_code_switching_eval_fixtures.py` (new, +14 tests)

### Commit 6 — README multilingual section + bug specs

Added "Multilingual narrator support" section to `README.md` covering all wired surfaces (STT auto-detect, LANGUAGE MIRRORING RULE, perspective + fragment + question-quality guards, phantom-noun guard, name extraction, correction parser, correction acknowledgments, place-as-birthplace guard, story trigger anchors, memoir export, pluggable TTS). Documents what's NOT yet wired (Spanish-monolingual eval suite, Kokoro TTS runtime patches).

Filed two bug specs from the night's bug hunt:
- `BUG-ML-LORI-CORRECTION-PARSER-VALUE-OVERCAPTURE-01` — parser captures `"Lima, no en Cuzco"` as full birthplace value instead of stopping at `, no `
- `BUG-ML-LORI-DETERMINISTIC-COMPOSERS-ENGLISH-ONLY-01` — `compose_memory_echo`, `compose_age_recall`, `compose_continuation_paraphrase` emit English directly to narrator (no LLM round-trip; LANGUAGE MIRRORING RULE doesn't apply); Spanish narrators get English memory-echo / age-recall / welcome-back. Three-phase fix sequenced behind live verification of tonight's Spanish guard work.

Files:
- `README.md` (added multilingual section)
- `BUG-ML-LORI-CORRECTION-PARSER-VALUE-OVERCAPTURE-01_Spec.md` (new)
- `BUG-ML-LORI-DETERMINISTIC-COMPOSERS-ENGLISH-ONLY-01_Spec.md` (new)

---

## Live verification queue (after stack restart)

Before declaring tonight's work closed, run these checks on a real Spanish narrator session:

1. **Fragment-repair-02:** Lori turn ending on a question — verify it closes with `?`, NOT `.` — when narrator has used Spanish triggers in prior turn.
2. **Place-as-birthplace guard:** narrator says "mi abuela hablaba de Perú" — verify Shadow Review does NOT show `grandparents.birthPlace = Peru`.
3. **Phase 5D phantom-noun:** narrator says "Mi mamá tomaba mi mano" — verify Lori does NOT invent "Hannah" / "Mona" / phantom Spanish proper noun.
4. **Phase 5E correction-ack:** narrator says "no, tengo dos hijos, no tres" — verify Lori responds "Lo entiendo — dos hijos..." (not "Got it...").
5. **Phase 5F fixtures:** spot-check 3-5 representative cases against live extractor / Lori behavior.

If any of these fails: rollback is single-commit revert + re-test.

---

## Known limitations (intentional, deferred)

1. **Single-Spanish-word in English context** — "I had dos hijos" without accents falls below `looks_spanish` threshold ≥2. The parser still catches the correction, but the ack-language detection misses. Filed under low-priority refinement.

2. **Deterministic-composer English-only** — `compose_memory_echo`, `compose_age_recall`, `compose_continuation_paraphrase` are all still English-only. Spec at `BUG-ML-LORI-DETERMINISTIC-COMPOSERS-ENGLISH-ONLY-01_Spec.md` — three-phase fix planned, sequenced behind live verification of tonight's Spanish guard work.

3. **Correction parser value overcapture** — Spanish parser captures `"Lima, no en Cuzco"` instead of stopping at the retraction clause. Filed as `BUG-ML-LORI-CORRECTION-PARSER-VALUE-OVERCAPTURE-01`. Affects `identity.place_of_birth` + parent-name fields.

4. **TTS runtime patches** — Kokoro engine spec landed but runtime not yet wired. Gated on perspective + fragment fix live verification per the WO.

---

## Pre-commit verification

Tree clean precondition required (sandbox cannot run git). When Chris is ready to commit:

```bash
cd /mnt/c/Users/chris/hornelore
git status && git diff --stat
```

Suggested commit grouping (6 commits, code isolated from docs):

```bash
# Commit 1 — Fragment repair-02
git add server/code/api/services/lori_spanish_guard.py tests/test_lori_spanish_guard.py BUG-ML-LORI-SPANISH-FRAGMENT-REPAIR-02_Spec.md
git commit -m "$(cat <<'EOF'
fix(lori): BUG-ML-LORI-SPANISH-FRAGMENT-REPAIR-02 — demonstratives + question-aware close

Add esas/esos/esa/ese/estas/estos/aquellas/aquellos/etc. to _FRAGMENT_CONNECTORS;
new _has_unclosed_spanish_question helper closes trimmed fragments with "?"
when ¿ is unbalanced upstream, "." otherwise. Live evidence: "...cuando
contaba esas." now → "...cuando contaba?".

9 new fragment tests + 4 looks_spanish edge tests; 57 total tests green.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"

# Commit 2 — Place-as-birthplace guard
git add server/code/api/routers/extract.py tests/test_extract_place_birthplace_guard.py BUG-ML-SHADOW-EXTRACT-PLACE-AS-BIRTHPLACE-01_Spec.md
git commit -m "$(cat <<'EOF'
fix(extract): BUG-ML-SHADOW-EXTRACT-PLACE-AS-BIRTHPLACE-01 — narrative-connection guard

Post-LLM regex guard mirroring PLACE-LASTNAME-01. Drops *.birthPlace
candidates whose value appears only after narrative-connection verbs
(EN: talked about / missed / remembered; ES: hablaba de / extrañaba /
recordaba) without explicit birth-evidence. Sibling lane; ships
independently of SPANTAG.

26 new tests; live failure (grandparents.birthPlace=Peru from "hablaba
de Perú") repaired.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"

# Commit 3 — Phase 5D phantom-noun whitelist
git add server/code/api/services/lori_communication_control.py tests/test_phantom_noun_spanish.py
git commit -m "$(cat <<'EOF'
feat(lori): WO-ML-05D — Spanish phantom-noun whitelist + accent detection

Extends _PHANTOM_NOUN_WHITELIST with Spanish kinship/calendar/religious/
holiday/Q-word tokens. Detector regex accepts Spanish accent capitals
(Á É Í Ó Ú Ñ) for multi-word names like María/Núñez. Real personal +
country names deliberately NOT whitelisted (corpus/profile gate handles
those).

15 new tests including regression checks for María/country names NOT
in whitelist.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"

# Commit 4 — Phase 5E correction-ack Spanish
git add server/code/api/prompt_composer.py server/code/api/services/lori_spanish_guard.py tests/test_compose_correction_ack_spanish.py
git commit -m "$(cat <<'EOF'
feat(lori): WO-ML-05E — compose_correction_ack Spanish path

Spanish narrator corrections get Spanish acknowledgments via looks_spanish
detection at composer entry. Field paths emit Spanish prose ("Lo entiendo
— dos hijos, no el número que tenía. Disculpa la confusión."). Extended
looks_spanish function-word list with Spanish-only verb conjugations,
infinitives, and number words 2-15 to catch unaccented Spanish text.

9 new ack tests + regression-safe English path. 57 prior tests still green.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"

# Commit 5 — Phase 5F code-switching fixtures
git add data/evals/lori_code_switching_eval.json tests/test_code_switching_eval_fixtures.py
git commit -m "$(cat <<'EOF'
feat(eval): WO-ML-05F — code-switching test fixtures

12 cases covering EN→ES, ES→EN, code-switching, pure Spanish corrections,
narrative-connection birthplace guard, phantom noun avoidance, dangling
demonstrative repair, full multi-detail intro. Each case carries
expected_* assertions covering perspective/fragment/parser/extractor
across the multilingual pipeline.

14 new fixture-shape tests + functional probes via parser/looks_spanish.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"

# Commit 6 — README + bug specs + night-shift bank
git add README.md BUG-ML-LORI-CORRECTION-PARSER-VALUE-OVERCAPTURE-01_Spec.md BUG-ML-LORI-DETERMINISTIC-COMPOSERS-ENGLISH-ONLY-01_Spec.md NIGHT_SHIFT_2026-05-07_MULTILINGUAL_BANK.md
git commit -m "$(cat <<'EOF'
docs: README multilingual section + 2 bug specs from night-shift hunt

README "Multilingual narrator support" section documents the wired
EN/ES surfaces (STT auto-detect, LANGUAGE MIRRORING, guards, name
extraction, correction parser+ack, place-as-birthplace guard, memoir
export, pluggable TTS) + what's not yet wired.

BUG-ML-LORI-CORRECTION-PARSER-VALUE-OVERCAPTURE-01: parser captures
"Lima, no en Cuzco" instead of stopping at retraction clause.

BUG-ML-LORI-DETERMINISTIC-COMPOSERS-ENGLISH-ONLY-01: compose_memory_echo,
compose_age_recall, compose_continuation_paraphrase emit English to
narrator directly (no LLM round-trip → LANGUAGE MIRRORING RULE doesn't
apply). Three-phase fix sequenced behind live verification.

Night-shift bank doc summarizes the 6-commit night ledger.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"

git status
```

---

## Architecture posture preserved

All five locked principles from CLAUDE.md held:

1. **No dual metaphors** ✓ (no Kawa/river additions)
2. **No operator leakage** ✓ (all narrator-facing additions stay narrator-shaped)
3. **No system-tone outputs** ✓ (Spanish acks read as a person talking, not a database query result)
4. **No partial resets** ✓ (no reset surface added or modified)
5. **Provisional truth persists** ✓ (no in-session shadow-review surface added; place-as-birthplace guard drops candidates BEFORE provisional write, never lets them die in a queue)
6. **Lori is the conversational interface; system is the memory** ✓ (deterministic guards don't add memory load to Lori — they shape her output post-LLM and gate extractor inputs at the boundary)
7. **Mechanical truth must visibly project** ✓ (no projection-mirror gap introduced; the place-as-birthplace guard PREVENTS bad data from reaching projection in the first place)
8. **Operator seeds known structure; Lori reflects what is there** ✓ (no new interrogation surface; all multilingual additions are listening + mirroring, not asking)

The Patch B postmortem locked principle held: *"prompt-heavy reflection rules made Lori worse, not better."* Detector-only paths (`detect_question_quality`) log to operator console without rewriting content.
