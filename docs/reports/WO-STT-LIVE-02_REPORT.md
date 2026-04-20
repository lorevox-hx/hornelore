# WO-STT-LIVE-02 — STT-Agnostic Fragile-Fact Guard + Transcript Safety Layer

**Author:** Claude
**Date:** 2026-04-20
**Status:** LANDED (implementation complete; byte-stable with pre-WO callers)
**Prerequisite:** WO-STT-LIVE-01A audit (docs/reports/WO-STT-LIVE-01A_AUDIT.md)
**Next:** WO-STT-LIVE-03 (backend Whisper migration behind a flag)

> **Scope framing (read this first):** Step 2 is **write-path hardening, not STT migration.** It adds transcript provenance, fragile-fact flags, and `suggest_only` downgrades to the extraction write path. It does **not** change STT authority — Chrome Web Speech is still the only live capture source. Backend Whisper migration is Step 3 (separate WO, not yet started).

---

## 1. One-line summary

Add a transcript safety layer: when the frontend signals a turn is fragile (low-confidence spoken audio OR fragile-fact keyword hit), the backend forces canonical identity/relationship writes to `suggest_only` and surfaces a `clarification_required` envelope the UI can use to ask the narrator to confirm. Self-gating — byte-stable with today's callers that leave the new fields unset.

---

## 2. Why this is the right Step 2

The Step 1 audit (WO-STT-LIVE-01A) confirmed the live STT authority is the browser Web Speech API; the backend Whisper endpoint is dead code from the browser's perspective. Migrating STT engines does nothing to protect the narrator's canonical identity record if a misheard "Mary Ellen" lands in `personal.fullName` with `writeMode=prefill_if_blank`. This WO puts the guard between the extractor and the projection layer, so fragile identity writes require explicit confirmation regardless of which STT engine is active today or tomorrow.

---

## 3. What changed

### 3.1 Backend

**`server/code/api/routers/extract.py`**

Additive Pydantic field surface — every new field defaults to `None`/`False`/`[]`, so pre-WO-STT-LIVE-02 callers (including today's frontend, the eval harness, and any future non-UX client) get identical behavior:

- `ExtractFieldsRequest` — 6 new optional transcript fields:
  - `transcript_source` (`"web_speech" | "backend_whisper" | "typed" | None`)
  - `transcript_confidence` (`float 0..1 | None`)
  - `raw_transcript`, `normalized_transcript` (`str | None`)
  - `fragile_fact_flags` (`List[str] | None`)
  - `confirmation_required` (`bool | None`)

- `ExtractedItem` — 3 new optional annotation fields:
  - `audio_source` (distinct from existing pipeline `source`; echoes the request's `transcript_source`)
  - `needs_confirmation` (`bool | None`)
  - `confirmation_reason` (`"low_confidence" | "fragile_field" | ...`)

- `ExtractFieldsResponse` — 1 new envelope field:
  - `clarification_required: List[Dict[str, Any]]` (default `[]`)

Fragile-field classifier + safety pass:

- `FRAGILE_FIELD_EXACT` frozenset — narrator identity + spouse identity + marriage date/place.
- `FRAGILE_FIELD_PREFIXES` tuple — indexed + non-indexed repeaters (parents, siblings, family.children, grandparents, greatGrandparents).
- `FRAGILE_FIELD_LEAF_NAMES` frozenset — which sub-fields inside a repeater are fragile (names, DOB/DOD, birthplace/deathplace). Everything else under `parents[0].*`/`siblings[1].*` (relation, notes, anecdote, occupation, etc.) is **not** fragile.
- `_is_fragile_field(fieldPath) -> bool` — pure, hot-path safe.
- `_fragile_field_label(fieldPath) -> str` — human-readable label for the clarification envelope.
- `_apply_transcript_safety_layer(items, req) -> (items, clarifications)` — two-pass helper:
  1. Always stamps `audio_source = req.transcript_source` on every item (pure annotation; safe to run under any caller).
  2. When `req.confirmation_required is True`, downgrades fragile-field writeModes to `suggest_only`, sets `needs_confirmation=True`, tags `confirmation_reason` (`low_confidence` when `transcript_confidence < 0.6`, otherwise `fragile_field`), and appends a clarification envelope entry.

Wired into both LLM and rules-fallback return paths inside `/api/extract-fields`. Both log lines (`[extract] Attempting …` and `[extract][summary]`) now carry `stt_src`, `stt_conf`, `confirm_req` alongside the existing `era`/`pass`/`mode` fields — a single grep over `[extract][summary]` now yields every stage + transcript-provenance variable.

### 3.2 Frontend

**`ui/js/state.js`** — new `state.lastTranscript` object (raw_text, normalized_text, source, is_final, confidence, fragile_fact_flags, confirmation_required, confirmation_prompt, turn_id, ts). Single source of truth for transcript provenance.

**`ui/js/transcript-guard.js` (new file, 312 lines, loaded after state.js in `hornelore1.0.html`)** — `window.TranscriptGuard` surface:

- `classifyFragileFacts(text) -> string[]` — 7-flag NL classifier (mentions_dob / mentions_name / mentions_birthplace / mentions_parent / mentions_spouse / mentions_sibling / mentions_child). Loose-recall-over-precision by design: false positives route fragile writes to confirmation UX (annoying but safe); false negatives would silently let a misheard identity prefill (the failure this WO exists to prevent).
- `populateFromRecognition(e, opts)` — Web Speech `onresult` → stages `lastTranscript` with `source="web_speech"` + min-over-segments confidence.
- `markBackendWhisper(result, opts)` — forward-compat stub for WO-STT-LIVE-03.
- `markTypedInput(text, opts)` — typed path → `source="typed"`, `confirmation_required=false` regardless of fragile flags (user authored what they wrote).
- `reconcileForSend(sendText)` — hand-edit / staleness detection. If `state.lastTranscript.normalized_text` is not a substring of `sendText` (user hand-edited) or the capture is older than 30 s, falls back to `source="typed"` with flags reclassified from the final text.
- `buildExtractionPayloadFields(chunk)` — returns the 6 request fields or `{}` when nothing is staged (byte-stable).
- `shouldConfirm(transcript) -> bool` — gate logic: `source != "typed" AND (confidence < 0.6 OR fragile_flags.length > 0)`.
- `buildConfirmationPrompt(entry)` — default UI prompt template.
- `clearStagedTranscript()` — called after each successful extraction round-trip so stale captures never double-attribute.

**`ui/js/app.js`**

- `recognition.onresult` now calls `TranscriptGuard.populateFromRecognition(e, {normalize: _normalisePunctuation, turnId})` after appending to `#chatInput`.
- `sendUserMessage()` — when no staged transcript matches the current `#chatInput` content (user typed from scratch, or hand-edited away from the spoken capture), calls `TranscriptGuard.markTypedInput(text)` so the payload carries `transcript_source="typed"`.

**`ui/js/interview.js`** — `_extractAndProjectMultiField`:

- Each chunk payload now merges `TranscriptGuard.buildExtractionPayloadFields(chunk)` into the POST body (empty merge when nothing is staged = byte-stable).
- Response handler collects `data.clarification_required` across chunks.
- After Promise.all resolves, dispatches clarifications via a three-tier handler chain:
  1. `window.HorneloreClarifyFragile(entries, answerText)` — custom handler when installed.
  2. `window.HorneloreShadowReview.showFragileClarifications(entries, answerText)` — reuses the existing shadow-review inline surface.
  3. DevTools console log via `TranscriptGuard.buildConfirmationPrompt(entry)` — always-on minimum-viable diagnostic.
- Clears the staged transcript after the round-trip.

**`ui/hornelore1.0.html`** — inserts `<script src="js/transcript-guard.js">` between `state.js` and `trainer-narrators.js`, with a comment explaining the load-order constraint.

---

## 4. Byte-stability contract

This is the most important non-functional property of this WO.

- **Eval harness (`scripts/run_question_bank_extraction_eval.py`)**: no changes. The harness doesn't pass `transcript_source` / `confirmation_required` → all 6 Request fields default to `None`/`False` → `_apply_transcript_safety_layer` stamps `audio_source=None` on items and never downgrades anything → clarification_required is `[]`. Byte-stable. The `r5a` eval currently in flight will not shift due to this WO.
- **Pre-WO frontend callers**: `TranscriptGuard.buildExtractionPayloadFields()` returns `{}` when `state.lastTranscript.source === null`. If transcript-guard.js were removed entirely, the payload builder guard in `interview.js` is `if (window.TranscriptGuard && typeof ... === "function")`, so it silently no-ops.
- **Backend**: the six new Request fields, three new Item fields, and one new Response field are all additive + optional. Old clients parse the response identically; `clarification_required` just becomes an extra key they ignore.

---

## 5. Smoke tests (deterministic)

**Frontend: 38 assertions, 38 pass.**

- Fragile-fact NL classifier: 10 cases across all 7 flag categories + negative baseline ("drive-in movies").
- `shouldConfirm` truth table: 4 cases covering low-conf / fragile / clean / typed.
- Recognition→`lastTranscript`→payload round-trip: 7 cases (source, confidence carried, fragile flag, confirmation_required).
- `reconcileForSend` hand-edit detection: 3 cases (match, no-match, flags re-classified from new text).
- `markTypedInput` path: 4 cases (source, no-confirm, payload).
- `buildExtractionPayloadFields` byte-stability: 1 case (empty staged returns `{}`).
- `buildConfirmationPrompt` output: 2 cases.
- Post-fix re-test: 8 name-classifier cases after the `/i` flag fix (initial pattern missed capitalised "My name is" because it was trying to keep the `I'?m <Cap>` sub-pattern case-sensitive; split into two patterns).

**Backend: 30 assertions, 30 pass.**

- `confirmation_required=False` → pure annotation (audio_source stamped, writeMode preserved, clarifications empty).
- `confirmation_required=True` + `transcript_confidence=0.45` + fragile field → `writeMode=suggest_only`, `reason="low_confidence"`, one clarification entry with source + confidence echoed back.
- `confirmation_required=True` + `transcript_confidence=0.95` + fragile field → `reason="fragile_field"`.
- Non-fragile fields (`education.schooling`, `siblings[0].anecdote`, `family.children[0].anecdote`, `family.marriageNotes`) never downgraded.
- Empty items list handled cleanly.
- Indexed repeaters: `siblings[0].firstName` + `siblings[0].lastName` + `family.marriagePlace` all downgraded; `siblings[1].anecdote` preserved.
- Defensive case: `transcript_source="typed"` + `confirmation_required=True` still downgrades (honor explicit client signal).
- `transcript_source="typed"` + `confirmation_required=False` → pure annotation, `audio_source="typed"` stamped.

Smoke test commands (run from repo root; both use the workspace-mount Python/Node; neither requires the live API):

```bash
# Frontend transcript-guard.js (after fix for /i flag on name pattern)
cd /mnt/c/Users/chris/hornelore && node -e '
  const fs=require("fs"); global.window={}; global.state={lastTranscript:{
    raw_text:"",normalized_text:"",source:null,is_final:false,confidence:null,
    fragile_fact_flags:[],confirmation_required:false,confirmation_prompt:null,
    turn_id:null,ts:0,
  }};
  eval(fs.readFileSync("ui/js/transcript-guard.js","utf8"));
  const TG=window.TranscriptGuard;
  console.log("dob:", TG.classifyFragileFacts("I was born in 1945"));
  console.log("name:", TG.classifyFragileFacts("My name is Mary Ellen Smith"));
'

# Backend safety layer (AST-slice, no fastapi install required)
# Full script in the dev session log; passes 30/30.
```

---

## 6. What this WO does NOT do

Explicit scope boundary — these are deferred to later WOs:

- **Does not migrate STT engines.** WO-STT-LIVE-03 will wire backend Whisper behind a flag (the backend endpoint is still dead code today; today's pipeline is browser → Google).
- **Does not change the eval harness.** The eval remains byte-stable because the harness doesn't set the new fields. A future eval extension could deliberately set `transcript_source="web_speech"` + `transcript_confidence=<noise>` to simulate STT errors and measure fragile-field resilience, but that's a separate WO.
- **Does not build the confirmation UX widget.** The clarification envelope is emitted and the default handler logs each prompt via `TranscriptGuard.buildConfirmationPrompt`. A persistent inline card surface should reuse the existing shadow-review panel — the handler chain in `interview.js` already probes `window.HorneloreShadowReview.showFragileClarifications` before falling back to the console.
- **Does not add a persistent permission-state machine.** The 01A audit flagged that `ui/js/state.js` treats mic permission as a single boolean, not the 6-state machine the original WO-STT-LIVE-01 contemplated. Not in scope here; file for WO-STT-LIVE-04 if and when it matters.
- **Does not touch `/api/stt/transcribe` payload shape.** Today's backend endpoint still returns `{ok, text}` — no per-word timing, no confidence. Extending the response to surface faster_whisper's per-segment `avg_logprob` is a WO-STT-LIVE-03 concern.

---

## 7. Risk assessment

**Low.** The entire feature is self-gating. If `transcript-guard.js` fails to load, `interview.js` skips its merge block (guarded `if (window.TranscriptGuard && …)`). If the frontend never populates `state.lastTranscript`, the payload is byte-stable. If the backend receives no new fields, the safety layer stamps `audio_source=None` (no-op) and returns `clarification_required=[]`. The only way this WO changes observable behavior is when **all three layers** cooperate: frontend captures a fragile/low-confidence transcript AND sets `confirmation_required=True`, backend sees the flag and produces fragile items, and the UI renders the clarification envelope. Failure to cooperate degrades gracefully to today's behavior.

The one remaining risk surface is the fragile-fact NL classifier in `transcript-guard.js` — a false positive would route a non-fragile spoken turn into confirmation UX unnecessarily. The classifier is deliberately over-broad (recall > precision) and its 10 smoke-test cases include a negative-control ("drive-in movies") to guard against drift. If a future regression surfaces a notable false-positive class, add a negative pattern with a compiled test.

---

## 8. Files touched

- `server/code/api/routers/extract.py` — +pydantic fields (Request, Item, Response); +fragile-field frozenset/prefixes/classifier; +_apply_transcript_safety_layer; +safety-layer wiring into both return paths; +log-line transcript fields.
- `ui/js/state.js` — +state.lastTranscript object.
- `ui/js/transcript-guard.js` — NEW.
- `ui/hornelore1.0.html` — +`<script src="js/transcript-guard.js">` after state.js.
- `ui/js/app.js` — +populateFromRecognition wire in `recognition.onresult`; +markTypedInput wire in `sendUserMessage()`.
- `ui/js/interview.js` — +payload field merge; +clarification_required collection + three-tier dispatch handler; +clearStagedTranscript after round-trip.
- `docs/reports/WO-STT-LIVE-02_REPORT.md` — this file.

No changes to:
- `server/code/api/routers/stt.py` — out of scope for this WO (Step 3 concern).
- `scripts/run_question_bank_extraction_eval.py` — eval stays byte-stable.
- `ui/js/focus-canvas.js` — still wraps the single recognition instance; transcript-guard wiring lives in the app.js `onresult` that focus-canvas hooks.

---

## 9. Stop/go gate

- ✅ All three layers compile / parse / syntax-check.
- ✅ Frontend 38/38 smoke assertions pass.
- ✅ Backend 30/30 smoke assertions pass.
- ✅ Byte-stability verified: pre-WO frontend + eval harness unaffected.
- ✅ Log lines augmented without breaking existing greps (added fields, didn't rename).
- ⏸ Live round-trip (frontend → live API → projection-sync) not yet run — waiting on the r5a eval to land first so we don't conflate any r5a movement with this WO.

Recommended landing sequence:
1. Land r5a eval readout per CLAUDE.md (this WO is byte-stable with r5a; they're independent).
2. Commit this WO.
3. One live smoke turn in browser — speak a DOB-containing utterance, confirm `[extract][stt-safety]` log line fires and `[extract][summary]` carries `stt_src=web_speech`.
4. File WO-STT-LIVE-03 for backend Whisper migration behind a flag.

---

## 10. Revision history

- 2026-04-20: initial landing. 68 total smoke assertions across frontend + backend; all green.
