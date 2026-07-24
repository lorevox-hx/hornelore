# `.env.example` flag audit — cross-reference report (2026-07-23)

**Read-only. No edits made. No defaults flipped. No renames.**

## Method (collection sources)

- `.env.example` keys: active `KEY=` lines (134) + commented defaults `# KEY=` (8) = **136 documented**.
- Server reads: `os.getenv` / `os.environ.get` / `os.environ[...]` across `server/code/**/*.py` = **154 literal reads**, plus flags read via helper indirection (`flags.py`, wrapped getenv) confirmed by whole-file reference.
- Shell/launcher reads: `launchers/`, `scripts/` (`.sh`/`.bat`/harness `.py`).
- UI/localStorage flags: tracked **separately** (browser-side, not server env).
- README / MASTER: treated as documentation only, not runtime reads.

There is **no pydantic `Settings`/`BaseSettings` module** — all server config is `os.getenv`.

## Headline counts

| Category | Count |
|---|---|
| 1 — documented **and** read by code | **102** |
| 2 — read by code but **missing** from `.env.example` | **77** |
| 3 — documented but **not read by server code** | **34** |
| 4 — duplicated / contradictory doc lines | **6** (active + commented pairs) |
| 5 — safety-sensitive (must stay explicit) | subset, all accounted for below |

No hard bugs. This is documentation drift, not runtime risk — but category 2 is a real ops gap (operators can't discover 77 live flags).

---

## Category 2 — READ by code, NOT documented (add to `.env.example`)

Grouped by the file that reads them:

| Reading file | Undocumented flags |
|---|---|
| `services/stack_monitor.py` | `DASH_ARCHIVE_STALE_AMBER_SEC` `DASH_ARCHIVE_STALE_RED_SEC` `DASH_CPU_AMBER` `DASH_CPU_RED` `DASH_DISK_AMBER` `DASH_DISK_RED` `DASH_EVAL_STALE_AMBER_SEC` `DASH_EVAL_STALE_RED_SEC` `DASH_GPU_TEMP_AMBER` `DASH_GPU_TEMP_RED` `DASH_RAM_AMBER` `DASH_RAM_RED` `DASH_SVC_LATENCY_AMBER_MS` `DASH_SVC_LATENCY_RED_MS` `DASH_UI_HEARTBEAT_TTL_SEC` `DASH_VRAM_FREE_AMBER_MB` `DASH_VRAM_FREE_RED_MB` |
| `routers/extract.py` | `HORNELORE_ATTRIB_BOUNDARY` `HORNELORE_NARRATIVE` `HORNELORE_PROMPTSHRINK` `HORNELORE_PROMPTSHRINK_MAX_EXAMPLES` `HORNELORE_SILENT_DEBUG` `HORNELORE_TWOPASS_DEBUG` `SPANTAG_PASS1_MAX_NEW` `SPANTAG_PASS1_TEMP` `SPANTAG_PASS1_TOP_P` `SPANTAG_PASS2_MAX_NEW` `SPANTAG_PASS2_TEMP` `SPANTAG_PASS2_TOP_P` |
| `services/travel_doc_photo_ocr.py` | `HORNELORE_OCR_EARLY_EXIT` `HORNELORE_OCR_MAX_DIM` `HORNELORE_OCR_MIN_CONF` `HORNELORE_OCR_MIN_RATIO` `HORNELORE_OCR_MIN_WORDS` `HORNELORE_OCR_PSM` |
| `flags.py` | `HORNELORE_ARCHIVE_ENABLED` `HORNELORE_CLAIMS_VALIDATORS` `HORNELORE_MEDIA_ARCHIVE_ENABLED` `HORNELORE_PHOTO_INTAKE` `HORNELORE_SPANTAG` |
| `routers/chat_ws.py` | `HORNELORE_FACTUAL_CHAIN` `VRAM_GUARD_BASE_MB` `VRAM_GUARD_ENABLED` `VRAM_GUARD_PER_TOKEN_MB` |
| `services/lori_communication_control.py` | `HORNELORE_PHANTOM_NOUN_GUARD` `HORNELORE_PHANTOM_NOUN_SCRUB` |
| `routers/operator_harness.py` | `HORNELORE_API_LOG_PATH` `HORNELORE_INTERNAL_WS_HOST` `HORNELORE_INTERNAL_WS_PORT` |
| `routers/memory_archive.py` | `HORNELORE_ARCHIVE_MAX_MB_PER_PERSON` `HORNELORE_ARCHIVE_WARN_AT` |
| `prompt_composer.py` | `HORNELORE_INTERVIEW_DISCIPLINE` `HORNELORE_MEMORY_ECHO_ERA_STORIES` |
| `routers/stt.py` | `STT_COMPUTE` `STT_DEVICE` |
| `api.py` | `BASE_MODEL_ID` `LORA_ADAPTER_ID` `USE_TTS` |
| `services/story_preservation.py` | `HORNELORE_STORIES_CAPTURED_FS` |
| `services/translation.py` | `LOREVOX_TRANSLATION_ENDPOINT` |
| `phase_aware_composer.py` | `HORNELORE_QUESTION_BANK_PATH` |
| `llm_interview.py` | `MAX_NEW_TOKENS_SUMMARY` |
| `db.py` | `HORNELORE_REFERENCE_NARRATORS` |
| `log_filter.py` | `HORNELORE_API_ACCESS_LOG_VERBOSE` |
| **scripts / harnesses only** (not server app) | `HORNELORE_API` `HORNELORE_API_BASE` `HORNELORE_API_LOG` `HORNELORE_API_URL` `HORNELORE_CHAT_WS` `HORNELORE_DB_PATH` `HORNELORE_REPORTS_DIR` `HORNELORE_SKIP_SEVEN_ERA` `HORNELORE_SKIP_UNIT_TESTS` `HORNELORE_WS_URL` `LLM_BASE` `LV_WS_URL` `TTS_BASE` |

**Recommendation:** add the app-flag rows to `.env.example` with a one-line comment + safe default each. The "scripts/harnesses only" block can be documented under a clearly-labelled *harness/dev* section (or noted as intentionally not in the runtime env).

---

## Category 3 — documented but NOT read by server code (subcategorized)

### 3a — Frontend / localStorage-documented (KEEP — not stale)
- `LOREVOX_NARRATOR_LOCATION` — server-render injection is Phase-2 pending; today the clock reads `window.LV_NARRATOR_LOCATION` / `localStorage["lvNarratorLocation"]`. Documented forward-declaration.
- localStorage keys documented as comments (not env keys): `lv_qf_live_ownership`, `lv_use_whisper_stt`, `lv_trip_style`, `lvNarratorLocation`, `lvClockVariant`. **Correctly documentation-only — do not treat as stale.**

### 3b — External library / launcher / shell-consumed (KEEP — Python never calls `os.getenv`, by design)
- HF / Torch / CUDA: `HF_HUB_ENABLE_HF_TRANSFER` `HF_HUB_ENABLE_XET` `HUGGINGFACE_HUB_TOKEN` `PYTORCH_ALLOC_CONF` `TRANSFORMERS_CACHE`
- TTS libs: `TTS_HOME` `TTS_DEVICE` (Coqui path; note Coqui retired in favor of Kokoro, but cache/paths still library-consumed)
- Launcher-consumed: `MODEL_DIR` (5 refs in `launchers/`)
- External search creds, written by `scripts/setup/*`: `BRAVE_SEARCH_API_KEY` `HORNELORE_SEARXNG_URL`

### 3c — Deprecated/vestigial but intentionally retained (KEEP; separate decision, do not auto-delete)
- `LV_ENABLE_AFFECT` `LV_ENABLE_CAMERA` `LV_ENABLE_TTS` `LV_SHOW_DEBUG_PILLS` — changelog (2026-04-27) confirms vestigial (only in `.env.example`). Prior decision: *either* wire as kill-switches *or* delete. **Needs an explicit call; not this pass.**
- `HORNELORE_PUBLIC_LOOKUP_AUTO` `HORNELORE_PHOTO_CONTEXT_AUTO_DRAFT` — forward-declared feature flags; written into `.env` by `scripts/setup/install_travel_doc_evidence.sh` (default `0`), not yet read by app code. Retain (the AUTO lanes aren't wired yet). `HORNELORE_PUBLIC_LOOKUP_AUTO` is on the do-not-touch list.

### 3d — Remove-candidate (VERIFY subsystem is retired before any deletion)
- **RAG/embeddings** (subsystem appears dormant — no `os.getenv` in current server code): `AUTHORS_DIR` `KNOWLEDGE_DIR` `FAISS_PATH` `MEMORY_K` `EMBED_MODEL` `EMBED_DEVICE`
- **Legacy/unclear**: `APP_ENV` `AUTO_NEXT` `AUTO_NEXT_STRATEGY` `FANOUT` `HEARTBEAT_INTERVAL` `LOG_RETENTION_DAYS` `MEDIA_DIR` `TEMPERATURE` `LORI_SESSION_HARD_CAP_MIN` `LORI_SESSION_SOFT_WARN_MIN`
- **Security-relevant — verify, do NOT blindly remove**: `CORS_ORIGINS` (if unread, CORS is hardcoded/wide — confirm the actual CORS config before touching), `APP_ENV`.

None of 3d should be removed in the first reconciliation pass — each needs a one-line confirmation that its subsystem is truly gone.

---

## Category 4 — documented twice (active + commented): verify no contradictory default

Six keys have both an active `KEY=` line and a commented `# KEY=` example:
`HORNELORE_OCR_LANGS` `HORNELORE_OCR_PROVIDER` `HORNELORE_PHOTO_OCR` `HORNELORE_PUBLIC_LOOKUP` `HORNELORE_PUBLIC_LOOKUP_PROVIDER` `HORNELORE_TRIP_INTERVIEW_CONTEXT`.

Likely benign (active default + commented alternate-value example), but each should be eyeballed so the active default and the commented example don't disagree in a confusing way.

---

## Category 5 — safety-sensitive / do-not-touch (all present & correct)

| Flag | Documented | Read by code | Notes |
|---|---|---|---|
| `LV_ENABLE_SAFETY` | yes | yes | keep explicit |
| `HORNELORE_SAFETY_LLM_LAYER` | yes | yes (`safety_classifier.py`, `chat_ws.py`) | keep explicit |
| `HORNELORE_SAFETY_LLM_CONFIDENCE_FLOOR` | yes | yes (`safety_classifier.py`) | keep explicit |
| `HORNELORE_SOFTENED_RESPONSE` | yes | yes (`chat_ws.py`, indirect) | keep explicit |
| `HORNELORE_TRIPS` | yes | yes | keep |
| `HORNELORE_PHOTO_OCR` | yes | yes | keep |
| `HORNELORE_PUBLIC_LOOKUP` | yes | yes | keep |
| `HORNELORE_PUBLIC_LOOKUP_AUTO` | yes | forward-declared (setup script) | keep (do-not-touch) |
| `HORNELORE_DB_INSPECTOR` | yes | yes | keep |
| `HORNELORE_OPERATOR_*` gates | yes | yes (`main.py`) | keep |
| `DB_PATH` / `DATA_DIR` / model+cache paths | yes | yes | keep |

No safety flag is missing or mis-documented.

---

## Proposed smallest safe edit (Deliverable 2 — NOT yet applied)

1. **Add category-2 app flags** to `.env.example` under their existing section headers (OCR tuning, extractor/SPANTAG, dashboard thresholds, archive caps, VRAM guard, phantom-noun guard, STT device) with a one-line comment + the current in-code default as the value. No behavior change (defaults already live in code).
2. **Label the harness/dev connection vars** (`HORNELORE_API_URL`, `LV_WS_URL`, `HORNELORE_SKIP_UNIT_TESTS`, …) in a clearly-marked *harness/dev-only* block so they aren't mistaken for runtime server config.
3. **Category 4:** eyeball the 6 active+commented pairs; align any contradictory default/comment.
4. **Category 3d:** leave in place; open a separate one-line-per-flag verification task before any deletion.
5. **Drift gate:** add a lightweight test (`tests/test_env_example_drift.py`) that fails if a `server/code` `os.getenv("HORNELORE_*"/"SPANTAG_*"/"DASH_*"/"VRAM_GUARD_*")` app flag is missing from `.env.example` (allowlist for harness/library/localStorage vars). Prevents recurrence.

Nothing above changes runtime behavior; it's documentation + a guard test.
