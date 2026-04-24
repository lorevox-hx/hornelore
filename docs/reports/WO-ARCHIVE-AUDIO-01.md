# WO-ARCHIVE-AUDIO-01 — Memory Archive Filesystem + Transcript Store

**Status:** code landed, awaiting live smoke run after next stack cold-boot.
**Canonical rule:** `archive session_id == conv_id`.

## Files changed

- `server/code/api/flags.py` — add `archive_enabled()` (new `HORNELORE_ARCHIVE_ENABLED` env flag; default off).
- `server/code/utils/__init__.py` — new package for shared, side-effect-free helpers.
- `server/code/utils/archive_paths.py` — new. Path helpers: `DATA_DIR`, `safe_id`, `get_person_archive_dir`, `get_session_archive_dir`, `get_session_audio_dir`, `ensure_session_archive_dirs`, `get_person_archive_usage_bytes/mb`, `iter_session_dirs`.
- `server/code/db/migrations/0002_memory_archive.sql` — new migration. Two tables (`memory_archive_sessions`, `memory_archive_turns`) with role / audio_ref CHECK constraints enforcing the no-Lori-audio invariant at the DB layer.
- `server/code/api/routers/memory_archive.py` — new. Seven endpoints: `GET /health`, `POST /session/start`, `POST /turn`, `POST /audio`, `GET /session/{conv_id}`, `GET /people/{pid}/export`, `DELETE /people/{pid}`.
- `server/code/api/main.py` — import + mount `memory_archive.router`.
- `ui/js/api.js` — seven constants under `API.MEMORY_ARCHIVE_*`.
- `scripts/run_memory_archive_smoke.py` — new. End-to-end smoke test for A–H acceptance.

## Implemented

### Archive paths
`DATA_DIR/memory/archive/people/<pid>/sessions/<conv_id>/` with `meta.json`, `transcript.jsonl`, `transcript.txt`, and `audio/<turn_id>.<ext>`. `safe_id` sanitizes identifiers (keeps `[a-zA-Z0-9_.-]`, caps at 120 chars). `ensure_session_archive_dirs` is idempotent — safe to call on every `session/start`.

### DB migration
`memory_archive_sessions(id, person_id, conv_id, archive_dir, audio_enabled, video_enabled, session_style, created_at, updated_at)` with unique index on `(person_id, conv_id)`.

`memory_archive_turns(id, person_id, conv_id, seq, role, content, audio_ref, confirmed, meta_json, ts)` with two CHECK constraints:
- `role IN ('narrator','user','lori','assistant')`
- `audio_ref IS NULL OR role IN ('narrator','user')`

Validated locally against a temp SQLite: lori+audio_ref rejected at DB layer, narrator+audio_ref accepted, lori+null accepted, bogus role rejected. Defense-in-depth beyond the router's 400.

### Router
All handlers gate on `flags.archive_enabled()` via `_require_enabled()`. `/health` is the sole exception — it returns `{ok:true, enabled:bool, data_dir, archive_root, max_mb_per_person, warn_at}` regardless of flag state so the UI can preflight.

- `POST /session/start` — idempotent. Creates folder tree, writes/updates `meta.json` (preserves `started_at`, refreshes `updated_at`), upserts the SQLite row, also calls `ensure_session(conv_id)` to keep the chat-layer `sessions` table honest (opt-out via `ensure_chat_session=false`).
- `POST /turn` — appends to `transcript.jsonl` + `transcript.txt`, inserts into `memory_archive_turns`. **Role gate:** if `role ∈ {lori, assistant}`, `audio_ref` is forced to `None` before persistence regardless of what the client sent. `seq` auto-advances per `(person_id, conv_id)` if not provided.
- `POST /audio` — multipart. **Hard rejects** `role ∈ {lori, assistant}` with 400. Also 413 if the person's archive usage is already over the configured cap. Writes `audio/<turn_id>.<ext>`; if the corresponding turn row exists, patches `audio_ref` on it.
- `GET /session/{conv_id}?person_id=...` — returns `{meta, turns[], archive_dir}`. For each turn with an `audio_ref`, stats the file and stamps `audio_lost: true` when missing. Transcript rows are **never dropped** for missing audio.
- `GET /people/{pid}/export` — streams a zip of the narrator's entire archive. Paths in the zip are relative to the narrator root (`sessions/<conv_id>/…`).
- `DELETE /people/{pid}` — explicit archive wipe. **Decoupled from narrator-delete cascade by design** — operator must call this separately. Removes filesystem tree + DB rows in both tables.

### Quota
`HORNELORE_ARCHIVE_MAX_MB_PER_PERSON` (default 500) and `HORNELORE_ARCHIVE_WARN_AT` (default 0.8). Over-cap behavior: new audio uploads return 413. Transcript keeps flowing (text is cheap).

### Transcript format
`transcript.jsonl` — one JSON row per turn:
```
{"turn_id": "...", "seq": 3, "role": "narrator|user|lori|assistant",
 "content": "...", "ts": "...", "audio_ref": "audio/<turn_id>.webm"|null,
 "confirmed": true|false, "meta": {}}
```

`transcript.txt` — human-readable, grouped by speaker:
```
Narrator:
I was born in Williston in 1962.

Lori:
You were born in Williston in 1962. What do you remember?
```

### Role label normalization
`narrator` and `user` both print as `Narrator:` in `transcript.txt`. `lori` and `assistant` both print as `Lori:`. Internally both forms are preserved in `role` on the jsonl row so downstream consumers can distinguish.

## Acceptance (to be run live)

Restart the stack with the flag on, then:

```bash
cd /mnt/c/Users/chris/hornelore
HORNELORE_ARCHIVE_ENABLED=1  # also export in the shell that launches start_all.sh
./scripts/run_memory_archive_smoke.py
```

Expected A–H:

| | |
|---|---|
| **A health** | `{ok:true, enabled:true, data_dir, archive_root, cap}` |
| **B session/start** | archive_dir created, meta.json written, audio/ dir exists, DB row upserted |
| **C transcript append** | narrator turn keeps audio_ref; Lori turn forces audio_ref=null |
| **D narrator audio upload** | 200, file lands at `audio/<turn_id>.webm`, turn row patched |
| **E Lori audio rejected** | 400 with `"never saved"` detail |
| **F session read + audio_lost** | narrator turn → audio_lost:false; injected missing-audio turn → audio_lost:true, transcript row preserved |
| **G export** | streams zip; contains transcript.jsonl + meta.json + audio/turn_narr_01.webm |
| **H delete** | 200 with removed_files>0; subsequent session read → 404 |

Smoke script cleans up after itself (creates throwaway narrator, deletes archive at end) so repeated runs don't leave test data behind.

## Hard invariants enforced

1. **Lori audio is never persisted.** Defense in depth:
   - Router 400 on `role ∈ {lori, assistant}` audio upload.
   - Router forces `audio_ref=None` on Lori/assistant transcript turns regardless of client input.
   - DB CHECK constraint rejects Lori rows with non-null `audio_ref`.
2. **Two-sided transcript is always saved.** Both narrator and Lori text land in `transcript.jsonl` + `transcript.txt`.
3. **Missing audio ≠ missing transcript.** `GET /session/{conv_id}` stamps `audio_lost:true` but keeps the row.
4. **Archive delete is explicit.** Narrator-delete cascade does NOT touch `memory/archive`. Operator must hit `DELETE /people/{pid}` deliberately.

## Known limitations

- **Safari/iPad MediaRecorder** isn't in scope for this WO — that lives in WO-AUDIO-NARRATOR-ONLY-01. The archive accepts whatever mime the client uploads; the router doesn't validate container format. Phase 1 is Chrome-first.
- **Zip export buffers in memory.** Fine at family scale (per-person cap defaults to 500 MB). If a narrator ever blows past that we'd switch to a temp-file streamer. Not a near-term concern.
- **Chat-layer `sessions` row is optional.** `session/start` calls `ensure_session(conv_id)` by default, but the archive will persist even if the underlying chat session row is missing. This is deliberate — archive must outlast DB-row weirdness.
- **No audit trail on DELETE.** `DELETE /people/{pid}` returns `removed_files` + `removed_bytes` but doesn't write a deletion log. Good enough for the family-operator use case; belt-and-suspenders logging is a follow-up if we ever add GDPR-style compliance requirements.
- **Per-session delete.** Only per-narrator delete exists. If you want to wipe a single session, you currently have to `rm -rf` it manually. Low priority — the common use is "wipe this narrator" or "export this narrator."
- **No mount for `/api/memory-archive/health` in dev-only toolbars.** The existing Bug Panel doesn't surface archive status. Add if/when it becomes operationally useful.

## Follow-up WOs

- **WO-AUDIO-NARRATOR-ONLY-01** — MediaRecorder segment capture, TTS gate, upload on confirm, Chrome-only.
- **WO-STT-HANDSFREE-01** — browser STT + review card (owns the "I heard you say…" UI) + typed fallback + long-pause ladder.
- **WO-STT-LOCAL-01** (later) — local Whisper / faster-whisper behind the same hands-free adapter.
- **WO-ARCHIVE-SESSION-DELETE-01** (if needed) — per-session delete endpoint.
- **WO-ARCHIVE-AUDIT-LOG-01** (if needed) — deletion audit trail.

## Commit plan

Single commit — all server changes are tightly coupled; archive + migration + router + main.py + api.js constants land together or not at all.

```bash
cd /mnt/c/Users/chris/hornelore
git checkout -b feature/wo-archive-audio-01

git add \
  server/code/api/flags.py \
  server/code/utils/__init__.py \
  server/code/utils/archive_paths.py \
  server/code/db/migrations/0002_memory_archive.sql \
  server/code/api/routers/memory_archive.py \
  server/code/api/main.py \
  ui/js/api.js \
  scripts/run_memory_archive_smoke.py \
  docs/reports/WO-ARCHIVE-AUDIO-01.md

git commit -m "feat(archive): add memory archive transcript and audio storage

WO-ARCHIVE-AUDIO-01.  Filesystem-backed narrator-only audio + two-sided
transcript archive at DATA_DIR/memory/archive/people/<pid>/sessions/
<conv_id>/.  Archive session_id = conv_id (canonical — fixes the
session-id ambiguity between chat conv_id and interview.session_id).

Router /api/memory-archive/* — 7 endpoints, all flag-gated behind
HORNELORE_ARCHIVE_ENABLED except /health (which reports enabled state
so the UI can preflight).  Hard invariants:
  - Lori / assistant audio upload → 400 at router layer
  - Lori / assistant audio_ref → forced null at router layer
  - Lori / assistant + non-null audio_ref → rejected by DB CHECK
  - Missing audio file + present transcript row → audio_lost:true,
    transcript preserved

Quota: HORNELORE_ARCHIVE_MAX_MB_PER_PERSON (default 500) + WARN_AT
(0.8).  Over cap → 413 on audio; transcript keeps flowing.

Narrator delete does NOT cascade to archive delete — explicit
DELETE /people/{pid} endpoint required.  Export endpoint streams a
zip of the full narrator archive.

No audio capture in this WO — that's WO-AUDIO-NARRATOR-ONLY-01.
scripts/run_memory_archive_smoke.py exercises A-H acceptance against
a live stack; expects HORNELORE_ARCHIVE_ENABLED=1 in the server env.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"

git status
```

Stack restart needed post-commit to pick up the new router + migration (migrations auto-apply in `init_db()`).
