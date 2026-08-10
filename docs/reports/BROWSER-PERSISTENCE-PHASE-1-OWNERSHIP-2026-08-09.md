# Phase 1 — ownership confirmation

**2026-08-09 · READ-ONLY.** No code changed. No table created. `pass1`, Profile Seed and
`LORI_INTERVIEW_DISCIPLINE` untouched.

**Decision applied:** production Lorevox uses **no persistent browser storage**. Category-C
cosmetics do **not** move to SQLite — they become volatile. Durable preference persistence
only where a product requirement asks for it.

---

## The headline: this is mostly wiring, not schema

The live database has **67 tables**, and **almost every category-A browser key already has a
server owner**. The shadow state did not grow because the database lacked a home for it; it
grew because the browser copy was written *alongside* the server one and then read *first*.

| category-A browser key | existing server owner | rows today |
|---|---|---:|
| `lorevox_facial_consent:<pid>` | **`consent_attestations`** *(narrator_id, attestation_type, attested_at, checked_by_operator, notes)* | **0** |
| `lorevox.spine.<pid>` | `timeline_events` / `life_phases` | 2 / **0** |
| `lv_done_<pid>`, `lv_segs_<pid>` | `interview_sessions`, `interview_sections` | 79 / **0** |
| `lorevox_offline_profile_<pid>` | `profiles` | 36 |
| `lorevox_proj_draft_<pid>` | `interview_projections` | 12 |
| `lorevox_qq_draft_<pid>` | `bio_builder_questionnaires` | 12 |
| `lorevox_ft_draft_<pid>` (Family Tree) | **`graph_persons` / `graph_relationships`** | **63 / 52** |
| `lorevox_lt_draft_<pid>` (Life Threads) | **`interview_threads`** | **0** |
| `lorevox_qc_draft_<pid>` (Quick Capture) | **no owner found** | — |
| curator identity (`ma_/pi_curator_user_id_v1`) | `media_archive_*`, `photos.uploaded_by_user_id` | populated |

**Two of my three "browser-only" suspicions from Phase 0 are withdrawn.** Family Tree maps
to `graph_persons`/`graph_relationships`, which hold **63 and 52 rows** — a populated server
owner. Life Threads maps to `interview_threads`. I flagged both as *suspicion, not
conclusion*, and the schema check retires them. **Quick Capture remains without an owner and
is now the only one of the three still open.**

---

## What the row counts say, and it is not comfortable reading

Three owners exist and are **empty**, while their browser counterparts are the live path:

- **`consent_attestations` — 0 rows.** Consent to affect analysis has been granted in this
  system, and the table designed to hold it has never been written. **The consent record
  exists only in Chrome.** This is exactly the failure ChatGPT promoted to first place, and
  the schema confirms it: there is a place for it and nothing is in it.
- **`interview_sections` — 0 rows**, while `lv_done_<pid>` / `lv_segs_<pid>` carry section
  progress in the browser.
- **`interview_threads` — 0 rows**, while Life Threads drafts live in `localStorage`.

**`life_phases` is also 0 and `timeline_events` holds 2 rows** — so the timeline spine that
promotes `pass1 → pass2a` is, in practice, a browser artifact with almost nothing behind it
server-side.

**This reframes the migration.** It is not "move data from browser to database." For at
least consent, sections and threads it is **"the database side was never populated at all."**
Phase 6 is therefore a genuine data rescue for those keys, not a copy.

---

## Consent: the two facts must be separated

ChatGPT's split is right and the schema supports it directly.

| fact | home | note |
|---|---|---|
| *"Janice consented to affect analysis under consent text version X"* | **`consent_attestations`** | durable, auditable, survives a cache clear |
| *"the camera is actually running right now"* | live session state | the browser necessarily knows `getUserMedia()` succeeded; that requires **no persistence** |

`consent_attestations` already carries `narrator_id`, `attestation_type`, `attested_at`,
`checked_by_operator`, `notes`. **Missing for a complete consent record:** consent text /
version, and `revoked_at`. Those are the smallest plausible delta — **and I am not proposing
them yet**, because the table has zero rows and the first question is why nothing writes it,
not what to add.

---

## Capability honesty: my Phase 0 claim was too strong, and the correct target is different

I asserted `lv_use_whisper_stt` / `lv_mic_modal_enabled` are the toggle behind Lori's
recording answer. **The census proved those keys exist and that the directive says "answer
based on the toggle state." It did not prove those keys are that toggle.** Withdrawn as
stated.

The corrected requirement is stronger than relocating a boolean:

```text
mic_enabled = true              ≠   voice_audio_is_being_saved = true
save_voice_requested = true     ≠   the recorder started
the recorder started            ≠   an audio artifact was persisted
```

**Lori's capability statement should derive from what the system actually did**, not from a
setting that records an intention. The honest surface is closer to `voice_capture_active`,
`voice_persistence_enabled`, `last_voice_artifact_persisted`, `camera_active`,
`affect_analysis_active` — generated from runtime and server state.

**Still to trace (not done here):** the real producer chain from
`narrator-audio-recorder.js` → WS `audio_id` → `archive.append_event(audio_id=…)` → the
persisted artifact, and which of those the directive should be reading. That trace is the
next unit of Phase 1, and it should finish before anything in this area is moved.

---

## Progression: derive, do not persist — probably

The third category ChatGPT names — **derived state** — likely applies to `effective_pass`.

The browser today decides `pass2a` from *the presence of a `localStorage` key*. The server
already holds the facts that condition could be computed from: `profiles` (36),
`timeline_events`, `life_phases`, `interview_sessions` (79). A server-side progression
resolver returning `effective_pass` may need **no new column at all**.

**This should be established, not assumed.** The open question is the deterministic condition
that ought to yield `pass1` / `pass2a` / `pass2b` — and `life_phases` being empty while
`timeline_events` holds 2 rows suggests the canonical spine may not currently be reconstructible
server-side. **If it is not, that is a finding about the timeline lane, not a licence to
persist `current_pass` as a new mutable truth.**

---

## What I am explicitly not doing

- **No tables created, no columns proposed as decided.** Every gap above is named as a gap.
- **No deletion of any browser key.** Nothing goes until the live values are read per narrator
  and each is proven migrated or empty — Quick Capture first.
- **No production fallback.** Concession accepted in full: a dev flag may select old-vs-new
  hydration while building, and the browser-authoritative path is **deleted** after
  acceptance. `DB unavailable → operator-facing error`, never `→ Chrome remembers`.
- **No Profile Seed or `LORI_INTERVIEW_DISCIPLINE` work** until progression authority is
  corrected.

---

## Next unit of Phase 1, in order

1. **Read the live browser values** on Chris's machine per narrator — especially
   `lorevox_qc_draft_<pid>`. If Quick Capture holds narrator-authored words with no server
   owner, that is life-story material in one Chrome profile, and README says the Archive is
   the immutable record of raw material. **That check outranks the rest of this phase.**
2. **Trace the voice/capture truth chain** end to end, per above.
3. **Trace why `consent_attestations` is empty** — is there a writer that never fires, or no
   writer at all?
4. **Determine the deterministic progression condition** and whether `effective_pass` is
   derivable from canonical facts.
5. **Then** produce the owner/migration map with minimal schema/API deltas, and stop for
   review.

---

## Corrections to my own earlier reports, recorded

| claim | status |
|---|---|
| "Family Tree, Life Threads and Quick Capture appear browser-only" (Phase 0 §3) | **two withdrawn** — FT → `graph_persons`/`graph_relationships` (63/52 rows); LT → `interview_threads`. QC stands. |
| "`lv_use_whisper_stt` / `lv_mic_modal_enabled` are the toggle behind Lori's recording claim" (Phase 0 §1) | **withdrawn as stated** — the directive-reads-a-toggle finding stands; the identification of *which* toggle does not. |
| "keep the old hydration path behind a flag" (Phase 0 sequencing) | **withdrawn** — it would preserve the architecture being removed, and would leave a stale-data fallback in production. |
| "`current_pass: pass2a` means the conflict is not occurring" (Phase 8 §10) | **already corrected** — that measured a browser, not a narrator. |
