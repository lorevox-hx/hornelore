# Handoff — desktop (MAG-Chris) → laptop, 2026-06-17

Chris is moving operations to the laptop due to a house issue. Everything
relevant to today's work is in this doc. Read this first when a new
session opens on the laptop.

---

## Where we landed at end of desktop session

### Origin/main is current

All work from today is committed and pushed. No drafted-but-uncommitted
state on either machine. Recent commits (most recent first):

1. **WO-SPANISH-LIVE-READINESS-01** — six patches for Spanish live
   readiness + new `scripts/run_spanish_live_smoke.py` harness.
2. **Post-Boris broad-suite noise cleanup** — four surgical test
   fixes (db.py migration cascade, harness_lib seeded-fact gate,
   test_interview_opener stub cleanup, test_chatws kwargs).
3. **2026-06-17 post-Boris evidence batch** — 32 docs/reports from
   the post-Boris testing session (boris baselines + John diagnostic
   runs + full-family live-narrator harness reports).
4. **Earlier today (pre-handoff)**: Boris quality test suite drop-in
   (40/40 GREEN), Boris contract symbols for `lori_response_guards`,
   harness scorer matrix completion, facts/add Truth-v2 pre-Pydantic
   gate + IntakeSpouse coerce + FK comment cleanup.

### Boris quality suite status

- **40/40 GREEN** on `.venv-gpu/bin/python -m unittest discover -s
  tests/boris_quality -v`. Locks the failure patterns from the
  2026-06-17 full-family run (cascade dump, phrase-as-name, meta-leak
  preamble, seeded-fact intake, broken code-mix).
- The suite is purely scoring. **Boris detects but runtime does NOT
  prevent** — same cascade dumps / phrase-as-name confirmations / broken
  Spanish code-mix still appear live for narrators. Real fix is wiring
  guards into the chat WS response pipeline. WO-SPANISH-LIVE-READINESS-01
  did this only for the Spanish-relevant subset (meta-leak ES + broken
  code-mix runtime guard). The English equivalents are not wired yet —
  parked for a follow-up.

### Broad unit suite status (.venv-gpu run)

- 2169 tests. After today's noise cleanup, expect ~46 → ~13 errors and
  ~25 → ~20 failures (haven't re-run since the four surgical patches
  landed; Chris skipped the re-run). The big delta drops should be:
  - Story preservation: 22 errors gone (language column migration now
    applies on test DBs)
  - Peek/safety mock paths: 8 errors gone (test_interview_opener stubs
    don't leak anymore)
  - chatws_conv_fk_hygiene: 3 errors gone (dob → date_of_birth)
- Remaining real correctness shortlist (NOT addressed today):
  - LAW 3 isolation violation: `story_preservation` transitively imports
    `api.routers.extract`
  - `lori_witness_mode` multi-anchor formatter caps at 2 (tests expect 3)
  - `/api/people` POST returns 422 (test fixture drift OR real route
    regression — unverified)
  - `safety_compound_accident_guard` over-suppressing acute ideation when
    biographical accident context is in the same turn

These are tomorrow's work, not blockers for Spanish live readiness.

---

## WO-SPANISH-LIVE-READINESS-01 — what landed and what to expect

Goal: make Hornelore usable for Spanish live testing on the laptop.

### Audit finding (going in)

Surprising amount of Spanish foundation already wired:
- LANGUAGE MIRRORING / SPANISH PERSPECTIVE / SPANISH SENTENCE COMPLETENESS
  / SPANISH ACTIVE LISTENING rules all in `compose_system_prompt`
- `compose_memory_echo` full ES locale pack (30 keys + translate_relation)
- `compose_correction_ack` ES branch
- `lori_meta_question` EN+ES locale pack (5 categories)
- `lori_spanish_guard.looks_spanish()` with documented overfire fix
  (BUG-LORI-SPANISH-DETECT-OVER-TRIGGER-01)
- Kokoro TTS: `af_heart` (en) / `ef_dora` (es), per-language pipeline cache
- FE `_lvSniffTtsLang` routes language to TTS endpoint
- `extract.py` Spanish place-as-birthplace guard
- `memory_echo.py` Spanish correction parser (8 regexes, 14 overcapture
  tests)
- `story_trigger.py` Spanish anchors (place / person / time / rich_short)
- `lori_response_guards.repair_meta_response_leak` already had ES fallback

### Six gaps closed in this WO

1. **Spanish meta-leak detection patterns**
   `_META_PREAMBLE_ES_RX`, `_META_POSTAMBLE_ES_RX`, `_FAKE_WARMTH_ES_RX`
   added to `lori_response_guards.py`. Catches "Qué descripción tan
   rica...", "Esta respuesta refleja...", "Déjame capturar...", "Gracias
   por compartir...". Wired into both `detect_meta_response_leak()` and
   `repair_meta_response_leak()`.

2. **Runtime broken-code-mix guard**
   `detect_broken_code_mix()` + `repair_broken_code_mix()` ported from
   the harness scorer (`scripts/harness_lib.py:_detect_broken_code_mix`)
   into `lori_response_guards.py`. Catches "Tú had..." / "Capté X y David.
   ¿Qué pasó después?" before reaching the narrator. Wired into
   `apply_response_guards()` after meta-leak, before dangling-determiner.
   Repair substitutes a short deterministic continuation in target_language
   ("Cuéntame más sobre eso." / "Tell me more about that.") — we can't
   safely auto-repair mid-mix output.

3. **`compose_age_recall` ES branch**
   New `target_language` kwarg + `_AGE_RECALL_MONTHS_ES` table. Three
   shapes covered (full DOB / year-only / unknown). Spanish narrator
   asking "¿qué edad tengo?" now gets a Spanish answer.

4. **`compose_continuation_paraphrase` ES branch**
   New `target_language` kwarg. Uses existing
   `_LV_ERA_CONTINUATION_PHRASES_BY_LOCALE["es"]` table. Tier C + Tier D
   both bilingual. Special-case for "hoy" so "estábamos en hoy" never
   renders. Returning Spanish narrator gets a Spanish welcome-back.

5. **`chat_ws.py` `_apply_guards()` narrator-language detection**
   Replaced hardcoded `target_language="en"` (line 3575) with
   `looks_spanish(user_text)` + recent-turns smoothing. Two other "en"
   lines at 3378 / 3505 are correctly hardcoded in context (inside an
   `if _witness_receipt_lang == "en":` branch and an es-repair path).

6. **Live laptop smoke harness — `scripts/run_spanish_live_smoke.py`**
   Drives Chris's 6-turn script. Per-turn 6-row scoring (language match
   / no code-mix / no meta-leak / word budget ≤90 / one question max
   / TTS voice correct). Verdict thresholds: GREEN ≥ 33/36, AMBER 30-32,
   RED < 30. Creates fresh narrator via `/api/people/intake`, opens
   chat WS, sends turns, captures verbatim Lori responses, greps
   `api.log` for TTS language tags. Single-page report to
   `docs/reports/spanish_live_smoke_<conv>_<stamp>.txt`.

### Six-turn script the harness runs

1. EN with Spanish proper nouns ("Antonio", "Las Vegas, New Mexico")
   → Lori must reply EN. Tests looks_spanish overfire.
2. Pure ES childhood memory ("Mi mamá encendía velas en el sótano...")
   → reply ES.
3. ES correction ("Quise decir que mi hermano se llamaba Antonio, no
   Alberto.") → parse retraction + ack ES.
4. ES age memory ("Yo tenía ocho años cuando nos mudamos...")
   → reply ES with lived-experience follow-up.
5. ES sensory family memory ("Mi abuela siempre decía que algunas
   cosas se recuerdan en silencio.")
   → ES, warm, NO fake-praise meta-preamble.
6. Explicit EN switch ("Now I want to continue in English.")
   → must follow narrator back to EN.

### How to read the smoke report

The report writes a per-turn breakdown + a final 6x6 matrix:

```
turn | L1 | L2 | L3 | L4 | L5 | L6
  1  | ✓  | ✓  | ✓  | ✓  | ✓  | ✓
  2  | ✓  | ✓  | ✓  | ✓  | ✓  | ✓
  ...
```

- **L1 expected_language_matches** — Lori's response language matches
  the per-turn expectation
- **L2 no_broken_code_mix** — `detect_broken_code_mix()` returns None
- **L3 no_meta_response_leak** — `detect_meta_response_leak()` returns
  False for both EN and ES patterns
- **L4 word_budget_honored** — ≤ 90 words
- **L5 one_question_max** — ≤ 1 question mark or ¿
- **L6 tts_voice_correct** — api.log shows `af_heart` for EN turns,
  `ef_dora` for ES turns; missing log lines are treated as PASS (not
  every TTS log line carries conv_id)

### If smoke run is RED — most likely failure modes in priority order

1. **looks_spanish overfire on Turn 1** — English narrator with
   "Antonio" + "Las Vegas, New Mexico" trips Spanish detection.
   Threshold tightening lives in `lori_spanish_guard.py:116`. Threshold
   was already lowered to 2 function words; may need raise back to 3
   for this specific case OR add proper-noun blocklist. Don't guess —
   wait for report evidence.
2. **TTS voice misroute** — Turn 2-5 should show `lang=es` in api.log
   with `voice=ef_dora`; if not, the chain is:
   `_lvSniffTtsLang` (FE app.js) → chat_ws WS payload `language=` →
   `kokoro.py.synthesize()`. Each link logs its decision.
3. **Spanish meta-preamble slips through** — new regex patterns are
   tight; if Llama produces a variant we haven't seen, add it to
   `_META_PREAMBLE_ES_RX`/`_FAKE_WARMTH_ES_RX`.
4. **Code-mix runtime guard over-firing** — substituting "Cuéntame
   más sobre eso." when legitimate Spanish includes English words.
   Density threshold currently 0.30; tunable.
5. **Word budget exceeded** — clear_direct cap is 55; we allow 90 in
   the smoke. If Spanish Lori turns blow past 90, check
   lori_communication_control word-cap routing.
6. **One-question rule** — Spanish ACTIVE LISTENING rule directs
   "ONE open question." If Lori still asks multiple, the directive
   isn't holding under Spanish; might need runtime trim regex.

### ChatGPT review follow-up (Patches 7-9, also on origin/main)

ChatGPT independently audited the same codebase after Patches 1-6
landed and confirmed the plan was right. Found three small gaps:

- **Patch 7**: `compose_age_recall` call site at `chat_ws.py:2482`
  wasn't passing `target_language`. Spanish narrator asking
  "¿qué edad tengo?" still got English even though the composer's
  ES branch was wired. Fixed — looks_spanish probe on user_text
  inline, threads through to the composer call.

- **Patch 8**: `compose_continuation_paraphrase` call site at
  `interview.py:525` wasn't passing `target_language`. Returning
  Spanish narrator still got English welcome-back. Fixed — uses the
  Layer 2 profile pin (`profile_json.session_language_mode`) since
  the opener path has no incoming user_text. Operator can set the
  Spanish pin via `scripts/set_session_language_mode.py`.

- **Patch 9**: Translation-refusal preamble patterns. If Llama drifts
  and emits "Let me say that in English" / "Déjame decir eso en
  inglés" as a preamble before continuing, the meta-leak guard was
  missing these specific shapes. Added `_TRANSLATION_REFUSAL_RX`
  covering both EN and ES variants. Wired into both
  `detect_meta_response_leak()` and the strip path of
  `repair_meta_response_leak()`.

All three landed alongside an updated `LAPTOP_CHECKLIST` step 5b that
documents ChatGPT's recommended focused unit gates (Boris suite +
four Spanish packs) for fast pre-live verification.

### What this WO did NOT cover (parked)

- VRAM-GUARD context-budget fix (operational, separate concern)
- Broader runtime wiring of English Boris guards into chat WS
- Safety accident-guard vs acute-ideation rewrite
- /api/people 422 cascade investigation
- LAW 3 isolation violation (story_preservation imports extract)
- lori_witness_mode multi-anchor formatter (test cap mismatch)

---

## Laptop environment quick facts

- Path on laptop: `/mnt/c/Users/chris/hornelore` (same as desktop)
- Venv: `.venv-gpu/bin/python` — same path as desktop
- Stack: starts via `./scripts/start_all.sh`; ~4 min cold-boot for
  warmup (HTTP listener up in ~60-70s but extractor warmup continues
  for another 2-3 min)
- API: `localhost:8000`
- TTS: Kokoro engine, `af_heart` (en) / `ef_dora` (es). Voice fallback
  patch in `kokoro.py` handles legacy Coqui voice IDs gracefully.
- Required `.env` keys (per LAPTOP_HANDOFF_KOKORO_INSTALL.md):
  - `LORI_TTS_ENGINE=kokoro`
  - `LORI_TTS_KOKORO_VOICE_EN=af_heart`
  - `LORI_TTS_KOKORO_VOICE_ES=ef_dora`
  - `HF_HUB_CACHE` + `HUGGINGFACE_HUB_CACHE` both pinned to user's
    HF cache directory (`/home/$(whoami)/.cache/huggingface/hub`)
  - `HF_HUB_OFFLINE=1` after first successful fetch

### File creation gotcha

`scripts/run_spanish_live_smoke.py` imports two helpers at module load
time:

```python
from api.services.lori_spanish_guard import looks_spanish
from api.services.lori_response_guards import (
    detect_broken_code_mix, detect_meta_response_leak,
)
```

These imports require `server/code` on `sys.path`. The script adds it:

```python
sys.path.insert(0, str(_REPO / "server" / "code"))
```

So invocation must be from the repo root:
```
cd /mnt/c/Users/chris/hornelore
python3 scripts/run_spanish_live_smoke.py
```

NOT from inside `scripts/` directory.

### websockets package requirement

The harness uses `websockets` package. Verify available in the venv:

```
.venv-gpu/bin/python -c "import websockets; print(websockets.__version__)"
```

If not present, install it: `.venv-gpu/bin/pip install websockets`.

---

## Open tasks heading into laptop session (relevant subset)

Completed today: #117-#124 (Boris noise cleanup + WO-SPANISH-LIVE-
READINESS-01 audit, spec, harness, implementation).

Still pending (none are Spanish-readiness blockers):
- #72 "What's" name-capture artifact in extractor / onboarding
- #73 parent-session readiness harness creates new narrator per run
- #76 LLM extractor chatty preamble triggers parse_drop
- #88 "Got it — [Title Cased]. Did I get that name right?" template
  on first 2 turns
- #96 Phase 7 live verify with flag ON for Jake + Kent
- #101 / #102 Stage C / D from BUG-FE work
- #105 / #106 / #107 UX polish items

---

## What I should do at start of next session

1. Read this handoff doc.
2. Wait for Chris to run the smoke harness and paste the report.
3. Diagnose any RED cells using the priority-order list above.
4. Patch the failures in place, one at a time, with verification per
   patch. NO scope creep into the parked items unless they're directly
   blocking Spanish live readiness.

Stay narrow. The goal is: Chris sits at the laptop, speaks or types
Spanish to Lori, gets clean Spanish responses without code-mix, fake
translation, or English contamination. That's the bar.
