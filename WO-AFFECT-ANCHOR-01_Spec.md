# WO-AFFECT-ANCHOR-01 — Spec

**Status:** PARKED (architectural anchor; do not implement until BINDING-01 stabilizes)
**Type:** Multimodal affect-anchored memory preservation
**Date:** 2026-04-27
**Lab/gold posture:** Hornelore-side first. Promote to Lorevox after BINDING-01 lands and BUG-212 (Lori interview quality) closes. Multimodal anchor is a genuine differentiator for Lorevox; worth getting right in the lab before promoting.
**Blocked by:** BINDING-01 (extractor lane stays primary), then a clean parent-session readiness checklist (per CLAUDE.md gates).
**Conceptual anchor:** `docs/research/papers/22526_Latent_Speech_Text_Trans.pdf` — but see "Why we don't need that model" below.

---

## Core rule (read this first)

```
The facial-affect stack you already have, the audio archive you already have,
and Whisper word-timestamps you can turn on with one config flag are
collectively just as relevant as the joint speech-text model the research
paper proposes — IF they share a clock.

A new model architecture is NOT required to get multimodal affect anchoring.
Shared-clock fusion of existing signals captures ~80% of the value at
~10% of the engineering cost.
```

---

## Why this WO exists

Lorevox's product positioning is **memory preservation artifact for the narrator's family**, not just a fact-extraction tool. Grandchildren who never met Janice should be able to:

- Click an extracted fact in Peek at Memoir → hear her say it
- See her face in Tier 2 video moments → not just read the words
- Feel the weight of moments that mattered → affect cues anchor the prose

Today the system has the pieces but they don't talk to each other:

| Asset | Where it lives | Gap |
|---|---|---|
| Per-turn audio | `WO-ARCHIVE-AUDIO-01` (#191) | No word-level timestamps |
| Per-turn transcript | Same | No alignment to audio |
| Facial affect signal | `emotion.js` MediaPipe stack | No wall-clock timestamps |
| Extracted facts | `extract.py` SPANTAG / singlepass | No anchor to source moment |
| Camera consent flow | `facial-consent.js` | Already in place |
| 7-tier authority ladder | WO-13 | Doesn't yet carry audio/video provenance |

The WO joins these on a shared clock and produces **affect anchors** — small JSON objects attached to extracted facts that tell the memoir consumer: "this fact was said at audio time 4.2s–4.8s, narrator looked moved, voice softened, paused 1.8s before saying it."

Do this and the memoir stops being a transcript and becomes a multimodal artifact.

---

## Decisions locked (this WO)

```
1. Shared-clock fusion, NOT a new joint model.
   Whisper word-timestamps + MediaPipe affect with wall-clock + light
   acoustic-feature extraction (librosa or webrtcvad) + optional Tier 2
   video. All four streams join on the audio capture clock.

2. Local-first ALWAYS. No external APIs for any modality.
   Every model used here runs on the narrator's machine. STT (Whisper local),
   facial signal (MediaPipe local), acoustic features (librosa local).
   This is a standing commitment, not a default we might revisit.

3. Three-tier video model:
   Tier 1 (default ON):  audio + facial affect signals + light acoustic features
   Tier 2 (opt-in):      curated video moments per session, narrator/family
                         deliberately chooses what gets visually preserved
   Tier 3 (middle path): low-res thumbnail strip (1 frame per 30s) during
                         audio sessions for visual context without full video

4. Affect anchor is a structured field on extracted items, not a sidecar.
   Items gain `audio_anchor`, optional `video_anchor`, `affect_label`, and
   `acoustic_features` fields. Memoir export consumes them; legacy code
   ignores them (additive only).

5. Authority ladder integration: promoted truth carries the affect anchor
   that originally produced it. Reviewers can play back the source moment
   when adjudicating any candidate.

6. Modular signal layer: each modality is a swappable component.
   Today MediaPipe (rule-based, coarse). Tomorrow possibly a learned visual
   emotion model. Today Whisper (open-source, local). Tomorrow possibly
   the latent speech-text model from the paper. The fusion layer's
   contract stays stable; only the upstream signal extractors change.
```

---

## Architecture overview

```
─── INPUT (already exists / minor add) ────────────────────────────

  Audio capture          ─→ Whisper(word_timestamps=True)        ─→ words + ts
  Video capture (Tier 2) ─→ file storage + frame ts              ─→ video + ts
  MediaPipe FaceMesh     ─→ affect_state + NEW wall_clock_ms     ─→ affect + ts
  Audio analysis         ─→ NEW: librosa/webrtcvad pitch/pause   ─→ acoustic + ts

─── SHARED CLOCK ─────────────────────────────────────────────────

  All four streams timestamped against the same audio capture clock.
  Synchronization happens at the recording layer (single canonical
  start_ms per turn; relative offsets per signal).

─── FUSION LAYER (new, ~150-200 LOC) ─────────────────────────────

  Per word/phrase, build affect_anchor:
  {
    ts_range_ms: [4200, 4800],
    words: ["Germany"],
    audio_path: "audio/turn_00042.wav",
    video_path: "video/turn_00042.mp4",   # if Tier 2 active
    facial_affect: "moved",                # MediaPipe label at this ts
    facial_confidence: 0.78,
    acoustic: {
      pitch_break: true,                   # voice quavered
      pause_before_ms: 1800,               # narrator paused before this word
      speaking_rate: 0.7,                  # slower than baseline (0=slow, 1=fast)
      volume_drop: false                   # not whispering
    },
    fusion_label: "emotionally_weighted_recall"  # combined judgment
  }

─── OUTPUT (new field on extracted items) ────────────────────────

  ExtractedItem gains:
    audio_anchor: AffectAnchor
    video_anchor: Optional[AffectAnchor]   # Tier 2 only
    affect_label: str (denormalized fusion_label for fast filtering)

─── CONSUMER ─────────────────────────────────────────────────────

  Memoir export:    play audio at ts_range / show video / display affect cue
  Peek at Memoir:   click any fact → playback its source moment
  Life Map:         click an era band → play affect-anchored highlights
  Authority ladder: review queue shows audio/video alongside candidate
```

---

## Scope — IN

1. **Whisper word-timestamps wire-in.** STT router gets `word_timestamps=True`; transcript schema gains per-word `start_ms` / `end_ms`.
2. **MediaPipe wall-clock emission.** `emotion.js` includes `wall_clock_ms` in every affect_state event so the signal can be joined to audio time.
3. **Light acoustic feature extractor.** Per-turn audio gets a librosa or webrtcvad pass producing pitch contour + pause segments + speaking rate + volume envelope, all with timestamps.
4. **Shared-clock recording layer.** Audio capture, MediaPipe stream, and (optional) video capture share a single `turn_start_wall_clock_ms` and emit relative offsets.
5. **Fusion layer.** New module (`affect_anchor.py` or similar) that takes the four timestamped streams and produces `AffectAnchor` objects per word/phrase.
6. **Schema additions.** `ExtractedItem` gains `audio_anchor`, optional `video_anchor`, `affect_label`. Schema migration with default-null backward compat.
7. **Tier 1/2/3 consent UX.** Three explicit consent surfaces (Tier 1 default-on, Tier 2 per-session opt-in, Tier 3 thumbnail-strip toggle).
8. **Memoir playback UI.** Peek at Memoir items become clickable → audio/video player with word-level highlight + affect cue overlay.
9. **Authority ladder pass-through.** Promoted truth retains its source affect_anchor so reviewers can play back the originating moment.
10. **Modular signal contracts.** Each upstream signal extractor (MediaPipe, Whisper, acoustic) implements a small contract so future swaps don't touch the fusion layer.

---

## Scope — OUT (deferred / not this WO)

- **Joint speech-text model from the paper.** That's months of work for the marginal upgrade over shared-clock fusion. Park as future direction.
- **Real visual emotion model (replacing MediaPipe).** Hardware-dependent. Add when GPU headroom allows. Modular signal contract makes the swap small.
- **Continuous video archival as Tier 1 default.** Privacy posture says routine sessions stay audio + thumbnail. Video is opt-in deliberate choice.
- **Server-side audio storage** beyond what `WO-ARCHIVE-AUDIO-01` already does.
- **Cross-session affect aggregation.** "Janice's overall emotional pattern across all sessions" is a future analytics concern.
- **External APIs.** No Google Cloud Speech, no AWS, no Hume.ai, no online emotion services. Ever. (See "Local-first commitment" below.)
- **Lori using affect anchors at runtime to drive question selection.** That's WO-AFFECT-DRIVE-LORI-02 territory; this WO produces the anchors, doesn't consume them in real time.

---

## Phase breakdown

### Phase 1 — Whisper word-timestamps (mechanical)

Add `word_timestamps=True` to the Whisper config in stt.py. Update transcript schema to include per-word `start_ms` / `end_ms`. Backfill existing transcripts is OUT of scope (only new sessions get word timing).

**Files:** `server/code/api/routers/stt.py`, transcript schema in archive layer.
**Effort:** ~1-2 hours including schema migration.

### Phase 2 — MediaPipe wall-clock emission

`emotion.js` currently emits `{affect_state, confidence, duration}`. Add `wall_clock_ms` (Date.now() at signal emission). Backend receives the timestamp and stores it. Existing affect-state consumers (cognitive_auto.js) ignore the new field — pure additive.

**Files:** `ui/js/emotion.js`, affect-state ingestion endpoint.
**Effort:** ~2-3 hours including small frontend test.

### Phase 3 — Light acoustic feature extractor

New module: `server/code/api/audio_features.py`. Takes a per-turn audio file path, returns:

```python
{
  "duration_ms": int,
  "pitch_contour": [(ts_ms, hz), ...],
  "pause_segments": [(start_ms, end_ms), ...],   # silences > 300ms
  "speaking_rate": float,                         # words per second
  "volume_envelope": [(ts_ms, db), ...]
}
```

Use **librosa** (pip-installable, pure Python with C deps, fully local) for pitch and volume. Use **webrtcvad** (small, fast, local) for voice activity detection → pause segments.

**Files:** `server/code/api/audio_features.py` (new), requirements.txt update.
**Effort:** ~4-6 hours including unit tests.

### Phase 4 — Shared-clock recording layer

Today audio capture, MediaPipe stream, and (future) video capture each have their own clock. Need single `turn_start_wall_clock_ms` for each turn that all three reference.

**Files:** Audio capture layer (existing), MediaPipe stream wiring, archive metadata schema.
**Effort:** ~1 day. Real architectural work because it touches the recording boundary.

### Phase 5 — Fusion layer

New module: `server/code/api/affect_anchor.py`. Takes timestamped streams from Phases 1-4 + extracted items with `sourceSpan`. Produces `AffectAnchor` objects. Contract is stable; future signal upgrades plug in as new extractors that implement the same per-modality interface.

**Files:** `server/code/api/affect_anchor.py` (new), Pydantic schema `AffectAnchor`.
**Effort:** ~2-3 days including tests.

### Phase 6 — ExtractedItem schema additions

Add `audio_anchor: Optional[AffectAnchor]`, `video_anchor: Optional[AffectAnchor]`, `affect_label: Optional[str]`. Default null for backward compat. Migrator for existing extracted items leaves them null (only new extractions get anchors).

**Files:** Pydantic models, schema migration, downstream consumer null-tolerance audit.
**Effort:** ~4 hours.

### Phase 7 — Tier 1/2/3 consent UX

Three explicit consent surfaces:
- **Tier 1 (default ON):** "Audio + affect signals" — same level as today's facial consent
- **Tier 2 (per-session opt-in):** "This session, also record video for the family memoir" — explicit per-session toggle, never sticky
- **Tier 3 (thumbnail strip):** "Save a low-res photo every 30 seconds" — for memoir visual context without full video

**Files:** `ui/js/facial-consent.js` extension, consent UI pages, audit trail of consent state per session.
**Effort:** ~2-3 days including operator-facing review of UX.

### Phase 8 — Memoir playback UI

Peek at Memoir items become clickable → audio/video player overlay with:
- Word-level transcript highlight synchronized to playback
- Affect cue badge (e.g. "moved · paused 1.8s before")
- Tier 2 video frame display when available

**Files:** `ui/hornelore1.0.html` Peek section, new audio/video player component.
**Effort:** ~3-4 days for a polished version.

### Phase 9 — Authority ladder pass-through

Promoted truth records carry `source_affect_anchor`. Review queue UI shows the playback widget alongside the candidate. Approving a candidate optionally inherits the affect_anchor into the promoted truth.

**Files:** Authority ladder data model, review queue UI.
**Effort:** ~2 days.

### Phase 10 — Acceptance tests

Live narrator session captures all four streams. Fusion layer produces sensible affect_anchors. Memoir playback works. Tier 2 opt-in records and replays cleanly. Authority ladder review shows audio playback for a candidate.

---

## Local-first commitment (standing rule)

**Every model and every signal extractor in this pipeline runs on the narrator's machine. No external APIs. Ever.**

This is a product-level commitment, not a defensive default. The Hornelore family use case — narrators with possible cognitive decline, recordings that may include sensitive personal information, archival material that should outlive the narrator — is incompatible with sending the data to an external service for any processing step.

Concretely:

| Modality | Today (local) | Future upgrade path (still local) |
|---|---|---|
| Speech-to-text | Whisper (open-source, local GPU) | Faster-Whisper, distil-whisper, or successor open models |
| Facial affect signal | MediaPipe FaceMesh + geometry rules | Learned visual emotion model (e.g. EmoNet, OpenFace successor) running on local GPU |
| Acoustic features | librosa + webrtcvad (CPU) | More sophisticated feature extractors (HuBERT-derived, etc.) — still local |
| Multimodal fusion | Shared-clock join (custom) | Eventually possibly the latent speech-text model from the paper, when an open weights version is available and runs on consumer GPUs |
| Extraction LLM | Llama-3.1-8B-Instruct local + 4-bit quant | Whatever local model Hornelore standardizes on; never an API |

**The architecture's modular signal contracts mean every entry in the right column is a drop-in replacement when:**
1. Open weights are available (no API-only models)
2. The model fits in narrator-class hardware (currently ~16GB VRAM, will grow over time)
3. The accuracy improvement is meaningful for the memoir use case

This local-first posture is also why Hornelore can credibly say to a 87-year-old narrator: "Your memories stay on your computer. They never go to a server we don't own. They never train someone else's model."

---

## Future model exploration (open invitation for contributions)

This WO sets up the architecture so that **future model improvements drop in cleanly without rewriting the application.** Some candidates worth tracking:

**Speech-to-text upgrades (Whisper successors):**
- `faster-whisper` (CTranslate2-based, 4x faster) — drop-in
- `distil-whisper` (smaller, faster, slight quality loss) — drop-in
- `whisper-large-v3-turbo` (higher quality, similar speed) — drop-in
- Future open-source successors

**Visual emotion upgrades (MediaPipe successors):**
- `OpenFace 2.x` (learned facial action units; CPU/GPU)
- `EmoNet` and its descendants (continuous valence/arousal output)
- Multimodal foundation models with vision capability (LLaVA-style, when small enough to run alongside the extraction LLM)
- Custom narrator-fine-tuned visual model (per-narrator calibration, future research)

**Acoustic feature upgrades:**
- HuBERT / wav2vec2 features (richer than librosa pitch+pause)
- Speech emotion recognition models (SER) running on local GPU
- Prosody analysis tools (Praat-Python integration for academic-grade features)

**Joint speech-text model (the actual paper's contribution):**
- When an open-source implementation exists that runs on consumer GPUs
- Becomes a drop-in for the fusion layer's role
- Until then, shared-clock fusion is the right approach

**Hardware advances enable richer signal:**
- Today: 16GB VRAM = Llama-3.1-8B + Whisper + MediaPipe coexist tight
- 2-3 years: 32GB+ consumer GPUs make a learned visual emotion model viable alongside the extraction LLM
- 5 years: locally-runnable joint multimodal foundation models become realistic

**Contribution invitation.** Anyone reading this who wants to:
- Replace MediaPipe with a learned visual emotion model
- Add a more sophisticated acoustic feature extractor
- Try a faster STT backend
- Implement the actual joint speech-text model when open weights exist

— is invited to do so via the contributor agreement (`CONTRIBUTING.md`). The signal contracts in this WO are designed to make these swaps small, isolated changes that don't touch the application logic. **Please don't add anything that requires an external API.** That's the line.

---

## Risks

1. **Phase 4 shared-clock layer is the load-bearing piece.** If clocks drift between modalities, the fusion is unreliable. Mitigation: single canonical `turn_start_wall_clock_ms` set at recording start; all signal extractors emit offsets relative to it, not absolute timestamps.

2. **MediaPipe affect quality is coarse** (rule-based on facial geometry). Acceptable for "this moment mattered" anchoring; insufficient for "the narrator was specifically experiencing X micro-emotion." Mitigation: modular signal contract makes future swap to a learned visual emotion model trivial. Don't over-design around MediaPipe specifically.

3. **Storage cost grows with Tier 2 adoption.** Each opt-in video session ≈ 1-2GB at 720p. If a family does 50 sessions over a year, that's 50-100GB. Mitigation: Tier 2 is deliberate per-session opt-in; thumbnail-strip Tier 3 is the always-on visual baseline (~5MB per session).

4. **Older narrator self-consciousness with video.** Real concern. Mitigation: Tier 1 (audio default) is the routine session posture; Tier 2 is for moments the narrator/family CHOSE to record.

5. **Fusion-layer affect labels could be wrong.** "moved" might be the model's call when the narrator was actually irritated. Mitigation: the affect_label is metadata, never authoritative truth. Reviewers always have the playable source clip.

6. **Local-first commitment under pressure.** "It would be so much faster if we used Hume.ai for emotion." This WO documents the standing rule: no external APIs ever. If pressure mounts later, point at this commitment.

---

## Stop conditions

```
STOP if any phase introduces an external-API dependency for any signal.
        Local-first is non-negotiable.

STOP if MediaPipe wall-clock timestamps don't match the audio capture clock
        within ±50ms. Fusion is unreliable above that drift.

STOP if Tier 2 video recording auto-enables without explicit per-session
        opt-in. The deliberate choice is the whole point of Tier 2.

STOP if extracted items become brittle to null affect_anchor (e.g. memoir
        export crashes when anchor is missing). Anchor is additive metadata,
        not required.

STOP if storage cost projections exceed reasonable narrator-machine limits.
        Tier 2 video is opt-in for a reason.
```

---

## Acceptance criteria

```
1. A narrator turn produces: audio file with word-timestamps, MediaPipe
   affect events with wall-clock timestamps, acoustic feature record.
   All three timestamped on the same clock within ±50ms.

2. An extracted item from that turn carries an audio_anchor with:
   - ts_range_ms covering the source span's audio range
   - facial_affect from MediaPipe at that ts
   - acoustic features (pitch_break, pause_before_ms, etc.) at that ts
   - fusion_label combining the multimodal signals

3. Peek at Memoir item is clickable → audio plays from ts_range_ms,
   transcript word-highlights synchronized, affect cue badge displays.

4. Tier 2 opt-in for one session captures video; same Peek item now also
   has video_anchor; clicking item plays video.

5. Tier 2 NOT opt-in for next session captures audio only; affect anchors
   still work; video_anchor is null.

6. Authority ladder review queue shows the playable source moment for a
   candidate before promotion.

7. Schema is backward-compatible: existing extracted items without anchors
   continue to work; consumers handle null anchors gracefully.

8. Live test on three real narrators (Janice, Kent, Christopher): each
   produces affect anchors that "feel right" subjectively when played
   back — the affect_label matches what the family member observes.

9. Zero external API calls during entire session capture/extraction/playback.

10. A future contributor can swap MediaPipe for a learned visual emotion
    model by implementing the per-modality signal contract — fusion layer
    and consumers don't change.
```

---

## Final directive

```
Local-first. Always.
Shared-clock fusion, not a new joint model.
Modular signal contracts so future improvements drop in cleanly.
Tier 1 audio routine; Tier 2 opt-in video for what the family chooses.
Memoir as multimodal artifact, not transcript.

The narrator's voice belongs on their computer.
The narrator's face belongs on their computer.
The narrator's stories belong to the family.

Everything else is engineering.
```

---

## Cross-references

- Existing audio capture: `WO-AUDIO-NARRATOR-ONLY-01` (#234, completed)
- Existing audio archive: `WO-ARCHIVE-AUDIO-01` (#191, completed)
- Existing facial stack: `emotion.js` MediaPipe FaceMesh + `cognitive-auto.js` v7.4C
- Existing facial consent flow: `facial-consent.js`
- Authority ladder: WO-13 four-layer truth pipeline
- Cognitive support mode: `WO-10C` (six behavioral guarantees)
- Research note: `docs/research/papers/22526_Latent_Speech_Text_Trans.pdf`
- Architecture spec: `docs/specs/LOREVOX-EXTRACTOR-ARCHITECTURE-v1.md` (extraction lane; this WO is a parallel preservation lane)
- Era axis WO: `WO-LIFE-MAP-ERA-AXIS-01_Spec.md` (memoir consumer side; era bands could surface affect-anchored highlights)

---

## Revision history

| Date | What changed |
|---|---|
| 2026-04-27 | Created. Captures the multimodal affect-anchor architecture using shared-clock fusion (Whisper word-timestamps + MediaPipe wall-clock + light acoustic features + optional Tier 2 video) instead of the latent speech-text joint model from the paper. Locks local-first commitment. Three-tier video model. Modular signal contracts for future model upgrades. Open contribution invitation for upstream signal-extractor improvements. Sequenced AFTER BINDING-01 + parent-session readiness. |
