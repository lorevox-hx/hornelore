# HORNELORE — FULL REPOSITORY REVIEW & HANDOFF

> **STATUS UPDATE (same day, later):** the top code fixes are now APPLIED — see §11.
> Chris ruled the GitHub repo must stay public (ChatGPT reads it over the web), so
> C1 (published family PII) is now the single most urgent open item: untrack the
> PII paths (block in §11.4) and purge history. ChatGPT does not need those data
> directories to read code.

**Date:** 2026-08-12
**Scope:** Complete review — server (`server/code`), UI (`ui/`), tests, scripts, config, docs, git/secrets hygiene.
**Method:** Four parallel deep-review passes (server core, server services, UI, repo hygiene) with findings verified against source. All claims below carry file:line evidence.
**Named separately from `HANDOFF.md`** so the project's own operational handoff is not overwritten. Read that file for project-state doctrine; read this one for defects and risk.

---

## 0. Executive summary

Hornelore is a local-first FastAPI + vanilla-JS oral-history/memoir system (~164K lines of first-party code) in substantially better internal shape than its size suggests: SQL is almost everywhere parameterized, the photo-import provenance pipeline is genuinely well-engineered, OAuth secret handling in `google_picker` is exemplary, and hard concurrency problems in the chat websocket have been solved with visible care. Requirements pinning and `.gitignore` coverage are excellent.

The risks cluster in four places:

1. **CRITICAL — Real family personal data is published on the public internet.** The GitHub repo (`lorevox-hx/hornelore`) is publicly readable and contains tracked interview transcripts, DOBs, and life-story prose of named real people.
2. **No authentication anywhere** + wildcard CORS + `0.0.0.0` bind: every endpoint, including hard person-delete and an unauthenticated websocket that accepts destructive commands, is open to the LAN.
3. **A systemic SQLite connection-leak pattern in `db.py`** whose consequence (a live "database is locked" incident) the team already diagnosed — and fixed in exactly one of 75 affected functions.
4. **XSS-by-default in older UI panels**: narrator/LLM text interpolated raw into `innerHTML` in the operator panels and shell page.

Everything else is important but secondary: god-files (5,368-line websocket function; 9,030-line router), a diverged 2,755-line legacy UI module still shipping, brittle regex language guards with a documented regression treadmill, broken E2E plumbing, and a 601KB `CLAUDE.md` that cannot be loaded whole by the agents it exists to instruct.

---

## 1. CRITICAL — act before any feature work

### C1. Family PII is on the public internet
- `wo12b_evidence/` (38 tracked files) and `wo13_phase5_proof/` (8 files) contain full interview transcripts, facts, profiles and memoir exports for real named people (e.g. `wo12b_evidence/janice/transcript_history.json` opens with a name, DOB 1939-09-30, and birthplace). Verified fetchable **without auth** at `raw.githubusercontent.com/lorevox-hx/hornelore/main/...` (HTTP 200).
- Same data class in tracked `data/timeline_context_events/*.json`, `data/qa/*.json`, `test/live test one no camera.docx`, and narrator prose quoted inside `CLAUDE.md` / `README.md` / `MASTER_WORK_ORDER_CHECKLIST.md`.
- **Action:** make the repo private immediately; then purge these paths from history (`git filter-repo`) before any re-publication. This outranks every other item in this document.

### C2. Secrets status (verified — partly good news)
- The `HUGGINGFACE_HUB_TOKEN` in `.env` and in git history is the **placeholder** `hf_REPLACE_WITH_YOUR_TOKEN` — no real HF leak.
- `.env` **does** hold a real `GOOGLE_PICKER_CLIENT_SECRET` (`GOCSPX…`) and `GOOGLE_PICKER_REFRESH_TOKEN` (`1//04x…`). Both were added **after** `.env` was untracked (commit `b294fd4`) and are **not in git history** — verified. All 10 env files (`.env` + 9 backups) are correctly gitignored.
- Residual risk is local sprawl: 10 copies of live Google credentials in the repo root, oldest from May, never rotated. **Action:** delete the 9 `.env.bak*` files (secrets live in one place), and rotate the Google refresh token as cheap insurance.

### C3. No authentication, LAN-exposed, wildcard CORS
- `server/code/api/main.py:65-79`: `allow_origins=["*"]`; `launchers/hornelore_run_gpu_8000.sh:21`: `HOST=${HOST:-0.0.0.0}`. No token/auth check exists anywhere in the server. `tts_service.py:20` repeats the wildcard.
- Any device on the LAN can call person hard-delete (`DELETE /api/people/{id}?mode=hard`, `people.py:238-252` — no confirmation token), transcript export, safety-event surfaces, and the DB inspector.
- `chat_ws.py:483-485, 5766-5811`: the websocket accepts with no origin/token check, and `sync_session` calls `clear_turns()` on a **client-supplied** conversation id. Websockets are not subject to CORS — any web page can open `ws://<host>:8000/api/chat/ws` and flush turn history.
- **Action:** default bind `127.0.0.1`; add a shared-token check (header + WS query param) and an Origin allowlist. Half a day of work; closes the whole class.

---

## 2. Bugs (server)

| # | Sev | Location | Bug |
|---|-----|----------|-----|
| S1 | HIGH | `db.py` — 74 of ~142 `_connect()` call sites | Connection opened, `con.close()` unreachable on exception; the held write lock makes the *next* connection fail `database is locked`. The repo's own comment at `db.py:2224-2243` documents this as the root cause of the 2026-07-22 live-test flake — the fix landed in one function only (`add_timeline_event`). Model fix already exists in-repo: `persist_turn_transaction` (`db.py:1715-1753`). Sweep with a contextmanager `_connect()`. |
| S2 | HIGH | `routers/photos.py:478-497` vs `migrations/0001:22` | `photos.file_hash` is table-wide `UNIQUE`, but upload dedup checks live-rows-for-this-narrator only. Re-uploading a soft-deleted photo (the exact workflow a prior BUG fix intended to enable), or the same file for a second narrator, hits the constraint → 500, **and** `store_photo_file()` has already moved bytes into the archive with no cleanup → orphan file every failure. `import_repository.py:2043-2066` already solves this correctly (`CrossPersonError`); port that guard. |
| S3 | MED | `chat_ws.py:5757-5850` | Receive loop catches only `WebSocketDisconnect`. A malformed frame raises `json.JSONDecodeError`, skipping the cleanup that sets the cancel event — the daemon `model.generate` thread keeps burning GPU for a dead socket. |
| S4 | MED | `api.py:792-793` | REST `/api/chat/stream` creates a stop event that **nothing ever sets** (no `ev.set()` in the file). Client disconnect leaves generation running to `max_new` tokens; the assistant turn is also never persisted. Dead wiring — wire it or delete it. |
| S5 | MED | `chat_ws.py:5607, 5651-5659, 5769` | Blocking DB and whole-transcript rewrite (`archive_rebuild_txt`) run directly on the event loop inside the async WS handler; with `busy_timeout=5000` (`db.py:82`) one lock contention freezes **all** sockets and HTTP for up to 5s. |
| S6 | MED | `api.py:666` | REST chat persists `msgs[-1]` as `role='user'` regardless of what it is — the same misattribution class WO-SYSTEM-DIRECTIVE-PERSISTENCE-01 exists to prevent. |
| S7 | MED | `photos.py:823-867` + `repository.py:494-515` | PATCH people/events is delete-all-then-re-add across separate connections/commits. A failure mid-sequence silently strips a photo's saved tags with no rollback — violates the repo's own "reversible, not destructive" doctrine. |
| S8 | MED | `chronology_accordion.py:749-761` | Unlogged `except Exception: trip_items = []` — any trips-schema error silently renders as "narrator has no trips." |
| S9 | MED | `archive.py:309, 1198, 214-216` | `index.json` read-modify-write with no locking and no temp-file rename; concurrent sessions can lose entries, crash mid-write truncates the index. |
| S10 | MED | `photos.py:329-337, 466-473` | No size cap on direct photo upload/preview (picker lane enforces 50MB; the direct lane it "matches" enforces nothing). `trips.py:2126-2131` also reads whole uploads into memory. |
| S11 | LOW | `db.py:403-1434` | `init_db()` (1,031 lines) re-runs on virtually every DB call; no `PRAGMA user_version` — migration correctness rests on every DDL staying idempotent forever, plus per-request overhead. |
| S12 | LOW | `db.py:4941-4990` | `hard_delete_person`: post-commit disk cleanup outside the transaction; crash between COMMIT and file removal orphans per-person files. |
| S13 | LOW | `chat_ws.py:41, 2818` | `_SAFETY_LLM_PARSE_FAILURES` grows unbounded per conv_id (the trip caches got a 500-entry cap for exactly this reason). |
| S14 | LOW | `repository.py:87-105` | `_json_dumps` trusts any string as pre-serialized JSON; read side masks corruption as `{}` — garbage in, silent empty-dict out. |
| S15 | LOW | `stack_monitor.py:545-547` | Log-timestamp conversion via local-naive `time.mktime` skews warm/idle classification across DST. |

Also noted: `check_same_thread=False` on every connection (`db.py:66`), a hardcoded narrator UUID as an "emergency English lock" with a TODO (`chat_ws.py:221-236`), dead `_lf()` in `api.py:182`, and 76 fully-silent `except Exception: pass` handlers out of 246 in the core files (notable: `_ws_send` swallows failed `done`/`error` frames — `chat_ws.py:239-243` — so a client can hang on a send that silently failed).

## 3. Bugs (UI)

| # | Sev | Location | Bug |
|---|-----|----------|-----|
| U1 | HIGH | `app.js:7992-8054` | XSS: narrator speech, LLM output, thread summaries interpolated raw into `innerHTML` in the WO-10 resume panel (`${(t.content||"").slice(0,150)}`). A narrator sentence containing markup executes in the operator panel. |
| U2 | HIGH | `app.js:8017-8020` | XSS attribute injection: `onclick="wo10SelectThread('${t.thread_id}')"` and `title="${t.summary...}"` — a quote in server data breaks out of the attribute. |
| U3 | HIGH | `hornelore1.0.html:6196-6202` | XSS: narrator profile name injected raw into the "record incomplete" card (`<strong>${label}</strong>`); `app.js:3272` escapes the same data correctly — the gap is inconsistency, not absence of a helper. |
| U4 | MED | `hornelore1.0.html:9334-9338` | Memoir editor save injects unescaped textarea content (`<p>${p}</p>`) **and** replaces the structured DOM that `_lv80AssembleNarrativeStructure()` depends on — one save wipes narrative-role metadata. |
| U5 | MED | `app.js:7942, 8123, 7962, 8056, 8130` | More unescaped interpolation: session titles, timeline topics, and `e.message` into `innerHTML`. |
| U6 | MED | `app.js:7913-7963` | Stale-narrator race: `pid` captured once, 3 awaited fetches, no re-check of `state.person_id`, no AbortController — switching narrators mid-load paints the previous narrator's transcript. |
| U7 | MED | `travel-documenter.js:2515-2535` | The legacy Documenter (still live via `travel-documenter.html`) lacks the `destroyed` flag and socket-identity pin that its fork `travel-doc-lab.js:8645-8676` added specifically to stop cross-trip token bleed. Known-fixed race, alive in the un-fixed copy. |
| U8 | MED | `app.js:6687-6691` | WS: infinite 4s reconnect with no backoff; `catch{}` on `onmessage` silently drops malformed frames and handler exceptions — invisible message loss. |
| U9 | MED | `hornelore1.0.html:9612` + `test-narrator-lab.js:355-356` | Production shell unconditionally starts test-lab polling: two never-cleared intervals (3s/2s) hitting `/api/test-lab/*` for every operator session; test/QA scripts ship in the production page. |
| U10 | MED | `app.js:9660`, `travels-shelf.js:879` | Uncleared module-level `setInterval`s run forever regardless of visible tab (22 setInterval vs 14 clearInterval repo-wide). |
| U11 | LOW | `safety-ui.js:151` | Sensitive-segment flags persisted plaintext in localStorage (cleaned on narrator delete, but unencrypted per browser profile). |
| U12 | LOW | `app.js:2328-2335` vs `3815-3829` | Per-narrator localStorage keys cleaned by two duplicated hand-written removal lists; adding a key means remembering both sites or leaking stale state. |

UI counts: 311 `innerHTML` sites (escaping used in ~10 of app.js's 58), 299 empty catches, 45 hardcoded `http://localhost:8000` fallbacks across ~30 files, 4+ separate escape helpers. Chat rendering, bio-builder, and travel-doc-lab are the clean baseline — the XSS findings are all in panels added after the helpers existed.

---

## 4. Areas of concern

**Concentration.** `ws_chat` is a 5,368-line function containing a 4,621-line nested closure — effectively the whole product in one untestable scope, with state threaded through closure variables and `params` dict side-channels; its own comments admit the shape is dangerous (`chat_ws.py:5643-5645`). `extract.py` is 9,030 lines behind one route with five parallel extraction strategies behind env flags, several dead in production config. `compose_system_prompt` is 1,323 lines; `trip_repository.py` is a 5,140-line god-module; `travel-doc-lab.js` and `app.js` are ~10K lines each coupled through one global `state` object and hand-ordered `<script>` tags.

**The regex-guard treadmill.** The Lori guard stack is ~142 hand-tuned compiled regexes (language detection, drift guards, response guards) with 29+ in-code `BUG-` markers documenting production overfires ("fiancée" pinned a session to Spanish; "Palais de Chaillot" counted as Spanish; the no-accent threshold has moved 3→2→3). The drift guard *replaces Lori's entire reply* when it fires, so every false positive is narrator-visible. Each incident adds a token to a frozenset. This is the highest-entropy maintenance surface in the codebase and is intrinsically un-finishable in its current form.

**Layering inversion.** `services/turn_extraction.py:383,431` lazily imports from `routers/extract.py` because the only extraction implementation lives in a router. Any future module-scope import closes a circular dependency; router-owned request models force `Any`-typed service signatures.

**Trust model is implicit.** Fail-closed 500s embed raw `str(exc)` in responses (`photos.py:986`, `import_provenance.py:206-219`); harness pages accept `?api=` origin override and ship next to production pages; f-string SQL in ~28 `db.py` sites is currently safe (identifiers from constants) but one refactor away from taking a caller-supplied name.

**Timestamp lottery.** Three repositories emit three timestamp shapes (naive, `Z`-suffixed, and a parser that silently drops numeric offsets — documented in `acquire.py:67-77`); the contract lives only in comments.

## 5. Areas of need

1. **Test execution is tribal knowledge.** 212 Python test files (211 unittest, 0 pytest), **no** pytest.ini/pyproject/conftest anywhere, and the documented rule is per-module runs because whole-tree discovery has known cross-suite contamination (HANDOFF.md §7). No script encodes the "focused" strategy; nothing fails if the 10 node-script JS tests are never run. Need: one committed runner script + the missing conftest-level isolation fix.
2. **E2E plumbing is broken.** `playwright.config.ts` points at nonexistent `scripts/start-lorevox-audit.sh`; 5 of 12 npm scripts reference spec files that don't exist (`tests/e2e/` has 4 files, not 9). Works only against an already-running server.
3. **No lint/build/typecheck for ~93K lines of UI JS.** No ESLint, no bundler; cache-busting `?v=` is manual and absent on `app.js`/`state.js` — a real stale-cache hazard given hand-maintained load-order coupling.
4. **~45% of Python tests are source-shape scans** (95/212 read source text/AST rather than execute behavior). The newer ones are well-engineered isolation gates with tested helpers, but the older regex-slicing style breaks on refactor and passes on marker drift. HANDOFF.md §7 already states the doctrine; the backlog of pre-doctrine tests remains.
5. **One documented entrypoint.** Three overlapping boot mechanisms (9 root `.bat`, 4 `launchers/*.sh`, ~15 `scripts/*.sh`) with proven drift (the Playwright script is one instance).

## 6. Areas of improvement (repo hygiene)

- **Root clutter (untracked, safe to delete):** 9 `.env.bak*`, 7 `.git-commit-msg-*.txt`, 3 `webstack_*.log`, `_to_delete/` (contains stale git-index.lock backups), `CLAUDE.md.bak` (434KB), `MASTER_WORK_ORDER_CHECKLIST.md.bak`, `.pytest_cache/`.
- **Root clutter (tracked — needs a commit):** empty `wsl` file (accidental redirect artifact, published), `clock_mockups_v1.html`, 29 `*_Spec.md` at root duplicating `docs/wo/` (at least one exact-name duplicate), stray `HANDOFF_2026-07-01.md`/`PLAN_2026-07-13.md`, the singular `test/` directory (10 files, unreachable by any runner, includes a live-session `.docx`), and the `wo12b_evidence`/`wo13_*` proof dirs (see C1).
- **Control-doc size:** `CLAUDE.md` is 601KB (~150K tokens) — it cannot be loaded whole by the agent tooling it instructs, which its own HANDOFF already flags as an operational bug. `MASTER_WORK_ORDER_CHECKLIST.md` 235KB, `README.md` 125KB. These need aggressive split/archive, not more appending.
- **docs/ sprawl:** 1,402 files; `docs/reports/` alone is 1,116 with no index.
- **`.runtime/logs/api.log`** is 12.6MB with thousands of lines of narrator prose; `LOG_RETENTION_DAYS=30` is evidently not enforced. Local-only, but a privacy hazard for any machine sync/transfer.
- **package.json rot:** `main` points at tailwind config; license `ISC` contradicts the repo LICENSE; Playwright in both dependencies and devDependencies.
- Positive: `.gitignore` verified in good shape; requirements files fully `==`-pinned with exemplary rationale comments; `node_modules`/venvs untracked.

## 7. What is genuinely good (preserve these patterns)

- `persist_turn_transaction` (`db.py:1715-1753`) — the correct BEGIN/COMMIT/ROLLBACK/finally-close model the other 74 functions should copy.
- Per-turn cancel events, bounded dual-generation refusal, buffer-until-guards-pass streaming, fail-closed guard fallback (`chat_ws.py:508-518, 4498-4534, 4564-4577, 5574-5598`).
- The import provenance pipeline: sha256 re-verification before promotion, magic-byte sniffing that distrusts provider MIME, atomic `os.replace` staging, partial-file cleanup on every exit path.
- `google_picker/oauth.py`: env-only credentials, never persisted, presence-only health, secret-safe error surfacing.
- `memoir_export.py:303-378`: server-side media resolution with strict path containment — no client path reaches `doc.add_picture()`.
- `travel-doc-lab.js` liveness design (destroyed flag, socket pinning, teardown discipline) and consistent `textContent`/`_esc()` in chat + bio-builder.
- Prompt-budget refusal instead of silent truncation; token budgeting that preserves the system message and never splits a turn pair.

## 8. Recommended order of work

1. **Today:** make the GitHub repo private. Rotate the Google refresh token. Delete `.env` backups.
2. **This week:** history purge of PII paths; bind `127.0.0.1` + shared-token auth + WS origin check; contextmanager sweep of `db.py` `_connect()`; escape-helper sweep of the six XSS sites (U1-U5 are a few hours total).
3. **Next:** port the hash-clash guard into the photo upload path (S2); catch-all + cancel-in-finally around the WS receive loop (S3); wire or delete the REST stop event (S4); delete or fix `travel-documenter.js` (U7); stop test-lab polling in production (U9).
4. **Then:** one boot entrypoint, one test-runner script, fix/remove dead npm scripts and the Playwright webServer, add ESLint.
5. **Structural (schedule deliberately, one lane at a time):** extract the turn pipeline out of `ws_chat`; move extraction out of the router; split `CLAUDE.md`; introduce `PRAGMA user_version` migrations; decide the long-term fate of the regex guard stack (the treadmill will not converge on its own).

## 9. Handoff notes for the next contributor

- Read the project's own `HANDOFF.md` (2026-08-09) first — its source-of-truth ordering (code > tests/evidence > reports > checklist > old WO headers) is correct and hard-won. Do not restart closed lanes (Google Picker, Travel Document) from stale checklist text.
- The model is locked (Llama 3.1 8B 4-bit, 8,192-token window). Model changes are a stop-and-report condition.
- Safety classification is deliberately **PARKED** server-side after false-positive evidence. Do not reactivate via stale env values.
- `.venv` = test env, `.venv-gpu` = serving env, Python 3.12 under WSL2. Run tests per-module (`.venv/bin/python -m unittest tests.<module>`); whole-tree discovery is known-unreliable. Beware stale pycache (use an external pycache prefix; `-B` is insufficient).
- Work on `main`, explicit file paths only, never `git add -A` (generated logs contain narrator prose — see §6).
- Key numbers: 1,923 tracked files; 246 `except Exception` in the 7 core server files (76 silent); 311 `innerHTML` sites; 142 `_connect()` sites (74 unprotected); largest units: `ws_chat` 5,368 ln, `extract.py` 9,030 ln, `travel-doc-lab.js` 10,217 ln, `app.js` 9,969 ln, `hornelore1.0.html` 10,426 ln.

---

## 10. `C:\hornelore_data` audit (added 2026-08-12)

Reviewed the live data directory for privacy and hygiene. DB inspected read-only from a copy; no live files were opened for write.

### Privacy — verified clean
- **No secrets anywhere in the data tree.** The live DB (67 tables) has zero credential-shaped columns and zero token-shaped values in any row scanned; the agent-transfer tarballs (`_agent_bundle_*.tar.gz`, 425 files each) contain no `.env` or secret files; the `_xfer`/`_to_delete` doc snapshots mention words like `client_secret` in prose only — no actual token values. Matches the "no raw Google tokens in SQLite" doctrine.
- All narrator data (DB, 93MB `memory/` archive, DB backups) is plaintext on disk — expected for local-first, but it means physical access to the machine or any drive this folder syncs/copies to is full access. Worth remembering when the laptop travels or is retired.

### Privacy — gaps found
| Sev | Finding |
|-----|---------|
| HIGH | **Hard-deleted narrators persist in `memory/archive/people/`.** 53 person directories on disk vs 36 people in the DB → **21 orphan directories (424 files)** holding transcripts/rolling summaries of deleted narrators (including wiped test rows and the 2026-07-26 Christopher wipe). `hard_delete_person` removes DB rows and the Kawa dir but evidently not the filesystem memory archive. This contradicts the "No partial resets" doctrine — a reset that leaves transcripts on disk isn't a reset. Needs a sweep + a fix in the delete path. |
| MED | **7 orphan photo directories** under `memory/archive/photos/` (29 on disk vs 22 in DB) — the known doctrine-3.12 orphan class, now measurable. |
| LOW | The wiped narrator (`e7fdb578`) still exists in `db/backup_pre_christopher_wipe_20260725_205530.sqlite3` — by design (that's what the backup is for), but if the wipe was meant to be complete, decide a retention date for that backup. |

### Hygiene / other
| Sev | Finding |
|-----|---------|
| MED | **No backup strategy evident.** The `backups/` dir referenced in April notes no longer exists; the only backups are ad-hoc `db/*.sqlite3` snapshots (8 files, two from April likely obsolete, one with stray `-shm`/`-wal` sidecars). The 93MB memory archive — the irreplaceable part — has no backup at all. |
| LOW | Scratch owed deletion (already flagged in CLAUDE.md as housekeeping): 4 agent tarballs (~7MB), `_ui_snapshot_r1.js`, `_xfer/` (~1.9MB), `_to_delete/` (~1.4MB). Verified secret-free; safe to delete. |
| LOW | Stray **0-byte `hornelore.sqlite3` at the data root** (Jun 24) — a decoy next to the real `db/hornelore.sqlite3`; delete to prevent a future tool opening the wrong path. |
| LOW | `import_staging/` holds 7 staged Picker originals from the Jul 28 batch; 6 candidates still `pending` in the DB. Fine, but they're family photos sitting in a staging dir with no expiry. |
| INFO | Empty dead structure: `logs/`, `uploads/`, `cache_audio/`, `interview/`, `projects/`, `voices/`, `templates/`, `test_lab/` (0 files each). `tts_cache` ~152MB is model cache, fine. Actual runtime logs with narrator prose live in the repo at `.runtime/logs/api.log` (12.6MB), not here. |

---

## 11. Fixes applied 2026-08-12 (same session as the review)

All edits are on disk, uncommitted. Syntax-verified (`py_compile`/`ast` clean on all Python; `node --check` clean on `app.js` and both inline blocks of `hornelore1.0.html`). The new db test module runs 5/5 green with a non-vacuous negative control; `tests.test_bio_facts_crud` and `tests.test_age_arithmetic` re-run green. **A stack restart is required for the server changes to take effect**, and per repo doctrine these should be re-verified in `.venv` on the laptop.

### 11.1 Network exposure (was §1 C3)
- **NEW `server/code/api/net_guard.py`** — single source of truth for the browser-origin allowlist. Default = the six local origins (`localhost`/`127.0.0.1` × ports 8082/8000/8001); override via `HORNELORE_ALLOWED_ORIGINS` (comma-separated; a literal `*` restores the wildcard deliberately; add `null` only if the UI is opened via `file://`). `origin_permitted(None)` is True so non-browser harnesses/eval scripts keep working.
- `server/code/api/main.py` — CORS `allow_origins=["*"]` → the allowlist.
- `server/code/api/tts_service.py` — same, and the spec-forbidden `allow_credentials=True`+wildcard combination corrected to `False`.
- `server/code/api/routers/chat_ws.py` — the websocket now refuses (close 4403, logged `[chat_ws][origin-guard]`) any socket whose Origin header is present and not allowlisted. Closes the hostile-web-page → `sync_session` → `clear_turns` hole; websockets are not subject to CORS so the CORS fix alone was insufficient.
- `launchers/hornelore_run_gpu_8000.sh`, `launchers/hornelore_run_tts_8001.sh` — default bind `0.0.0.0` → `127.0.0.1` (`HOST` env still overrides; WSL2 localhost forwarding still reaches it from the Windows browser — if your WSL networking mode ever breaks this, set `HOST=0.0.0.0` in `.env`).
- `hornelore-serve.py` — UI server binds `127.0.0.1` (override `HORNELORE_UI_HOST`).
- `.env.example` — new documented block for all of the above.
- **NOT done (deliberate):** shared-token authentication. The origin+loopback combination closes the browser and LAN attack classes; a token would additionally require touching every fetch site in ~30 UI files. Filed as follow-up.

### 11.2 db.py connection-leak class (was §2 S1)
- `server/code/api/db.py` — `_connect()` now registers each connection in a thread-local list; a `_closes_connections_on_error` decorator rolls back + closes every connection a call opened before any exception propagates; an auto-wrap block at module bottom applies it to **all 159 public functions** (verified: the module has no generator/async functions, so semantics are preserved; private helpers register to their wrapped caller). Success paths byte-identical. This kills the 2026-07-22 `database is locked` incident class without hand-editing 74 functions.
- **NEW `tests/test_db_connection_hygiene.py`** — behavioral: reproduces the incident shape (write, then raise, traceback held) and asserts a second writer succeeds immediately; includes a negative control proving the unwrapped shape really does hold the lock (non-vacuity per §7 doctrine); wrap-coverage and success-path checks. 5/5 green. Run: `PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_db_connection_hygiene`.

### 11.3 UI XSS (was §3 U1–U5)
- `ui/js/app.js` — all interpolation of server/narrator/LLM data in the WO-10 panels now goes through the existing `esc()`/`escAttr()` helpers: transcript role names + session titles (U-transcript), resume preview confidence reasons / thread topic / subtopic / era / summary / memory items / recent-turn role+content (U1), thread-chip `class`/`onclick`/`title` attributes (U2 — `status` and `thread_id` sanitized to safe charsets because entity-escaping is insufficient in class/inline-JS contexts), timeline topic/era (U-timeline), and all three `e.message` error paths.
- `ui/hornelore1.0.html` — narrator profile name escaped in the "Narrator record incomplete" card (U3); memoir editor save now escapes each paragraph (U4 escaping half). **U4's structural half remains open** (the save still replaces the structured `<section>/<mark data-narrative-role>` DOM — noted in a comment at the site; needs its own WO).

### 11.4 Ready-made block: untrack the published family PII (C1 — still open)
The repo stays public, so this is now the top open item. Step 1 removes the files from the *current* tree (they stay on disk locally):

```bash
cd /mnt/c/Users/chris/hornelore
git rm -r --cached wo12b_evidence wo13_phase5_proof "test/live test one no camera.docx"
git rm --cached data/timeline_context_events/janice_germans_from_russia_nd_prairie.json
printf '\n# family PII — never publish\nwo12b_evidence/\nwo13_phase5_proof/\ntest/live test one no camera.docx\ndata/timeline_context_events/\n' >> .gitignore
git add .gitignore
git commit -m "privacy: untrack family PII evidence dirs from the public repo" -m "Transcripts/DOBs/profiles of real family members were fetchable unauthenticated from raw.githubusercontent.com. Files remain on local disk; also purge from history (git filter-repo) before treating this as closed. Review data/qa/*.json and prose in CLAUDE.md/README for the same class."
```
Step 2 (separate, deliberate): history purge with `git filter-repo` + force-push — coordinate with ChatGPT usage since it rewrites clone history.

### 11.5 hornelore_data cleanup (was §10) — DONE
- 21 orphan narrator archive dirs + 7 orphan photo dirs **moved** (not deleted) to `C:\hornelore_data\_review_2026-08-12\` with `MANIFEST.json` (original paths, restore = move back) and `REPORT.md`. Post-move verification: every remaining archive dir maps to a live DB row.
- **Deleted** (verified secret-free): 4 agent tarballs, `_ui_snapshot_r1.js`, `_xfer/`, `_to_delete/`, and the stray 0-byte `hornelore.sqlite3` at the data root.
- Root cause NOT yet fixed: `hard_delete_person` still leaves `memory/archive/people/<id>` behind — needs a small WO (delete the archive dir inside the same operation that already removes the Kawa dir, plus an audit-log line).

### 11.6 Suggested commit plan (Chris runs from /mnt/c/Users/chris/hornelore)
```bash
cd /mnt/c/Users/chris/hornelore
# 1 — network exposure hardening
git add server/code/api/net_guard.py server/code/api/main.py server/code/api/tts_service.py server/code/api/routers/chat_ws.py launchers/hornelore_run_gpu_8000.sh launchers/hornelore_run_tts_8001.sh hornelore-serve.py .env.example
git commit -m "security: loopback bind + CORS/WS origin allowlist (SECURITY-REVIEW-2026-08-12)" -m "No-auth API was LAN-bound with allow_origins=['*'] and an unauthenticated WS accepting destructive commands. New net_guard.py allowlist (HORNELORE_ALLOWED_ORIGINS override), WS refuses non-allowlisted browser origins (close 4403), launchers + UI server default to 127.0.0.1."
# 2 — db connection hygiene
git add server/code/api/db.py tests/test_db_connection_hygiene.py
git commit -m "fix(db): close-on-exception guarantee for all public db functions" -m "74 of 142 _connect() sites had no try/finally; a leaked connection held the write lock (2026-07-22 incident class). Thread-local tracking in _connect + module-wide wrap; behavioral test with negative control."
# 3 — XSS escapes
git add ui/js/app.js ui/hornelore1.0.html
git commit -m "security(ui): escape server/narrator/LLM data in WO-10 panels, incomplete-card, memoir save" -m "Six innerHTML sites interpolated untrusted data raw (text, attribute and inline-JS contexts). Now routed through esc()/escAttr() or safe-charset sanitizers. Memoir save structural DOM loss still open."
# 4 — review handoff doc
git add HANDOFF_CODE_REVIEW_2026-08-12.md
git commit -m "docs: full repo review handoff + applied-fixes record (2026-08-12)"
```
After committing: **restart the stack** (server changes are inert until then) and hard-reload the browser (`app.js`/`hornelore1.0.html` have no cache-buster). Then verify in `.venv`: `PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_db_connection_hygiene`.
