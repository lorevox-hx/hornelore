# WO-KAWA-02A REPORT

**Date:** 2026-04-17
**Scope:** Deeper Kawa integration into Lori questioning + memoir organization

## FILES EDITED
- `ui/js/state.js` — added `kawaPromptCooldown`, `lastKawaSegmentId`, `memoirMode` to session; added `questionContext`, `memoir` blocks + extended metrics in `state.kawa`
- `ui/js/lori-kawa.js` — added hybrid follow-up logic (7 functions), memoir overlay helpers (2 functions), updated `_ensureKawa()` for new state shape
- `ui/js/interview.js` — added `maybeApplyKawaFollowup()`, `normalizeKawaLanguageForUser()`, patched question assignment to intercept with Kawa follow-ups
- `ui/js/app.js` — added `setInterviewMode()`, `setMemoirMode()`, `applyKawaToMemoirChapters()`, patched `generateMemoirDraft()` for river context, added `kawa_mode` to `buildRuntime71()`, added memoir mode + river-informed badge to `renderKawaUI()`
- `ui/hornelore1.0.html` — added interview mode selector, memoir mode selector, plain-language toggle inside River popover header; added `.lv-mode-group` and `.river-informed-badge` CSS
- `server/code/api/routers/kawa.py` — added `_compute_kawa_weight()` helper, wired into `post_kawa_build` and `put_kawa_segment` responses
- `server/code/api/prompt_composer.py` — added Kawa mode directives for `kawa_reflection` and `hybrid` modes, plus universal Kawa safety rule
- `data/prompts/kawa_prompts.json` — added `kawa_hybrid_followups` (5 construct types × 2 prompts) and `kawa_memoir_templates` (6 sentence templates)

## ADAPTATION NOTES
The patch pack assumed `lori9.0.html` with `state.session.currentMode` for Kawa. Actual repo uses:
- `hornelore1.0.html` with popover-based panels
- `state.session.kawaMode` (separate from `currentMode` which is the cognitive mode engine)
- `buildRuntime71()` for passing state to `prompt_composer.py` (not `interview_engine.py`)

Adaptations made:
- All mode selectors placed inside existing River popover (matching 01A pattern)
- `kawaMode` used throughout instead of overloading `currentMode`
- `kawa_mode` field added to `buildRuntime71()` → read by `prompt_composer.py`
- Memoir overlay injected into `generateMemoirDraft()` prompt builder (Hornelore uses LLM-driven memoir generation, not a `finalChapters` variable)
- `applyKawaToMemoirChapters()` available for future use by `renderMemoirChapters()` if chapter rendering goes client-side

## QUESTIONING
- chronological mode unchanged: PASS (code complete — no Kawa interception when `kawaMode === "chronological"`)
- hybrid mode implemented: PASS (triggers on high-meaning anchors with 3-turn cooldown)
- kawa_reflection mode implemented: PASS (always offers Kawa follow-up)
- Kawa prompts remain narrator-led: PASS (backend safety rule appended to system prompt)
- cooldown prevents metaphor spam: PASS (3-turn cooldown after each Kawa prompt)

## MEMOIR
- chronology mode unchanged: PASS (no Kawa context injected when `memoirMode === "chronology"`)
- chronology + river overlay mode implemented: PASS (appends river overlay for confirmed segments)
- river-organized mode implemented: PASS (groups by flow/rocks/driftwood/banks/spaces)
- Kawa never changes dates/places/facts: PASS (overlay is additive text only)

## WEIGHTING
- confirmed Kawa affects memoir weighting: PASS (`integration.narrative_weight` computed on save)
- unconfirmed Kawa does not overrule chronology: PASS (weight score +2 only for confirmed)

## UI
- interview mode selector added: PASS (inside River popover header)
- memoir mode selector added: PASS (inside River popover header)
- plain-language toggle added: PASS (checkbox replaces river metaphors with plain equivalents)
- river-informed badge shows for confirmed segments: PASS

## BACKEND
- prompt_composer.py reads `kawa_mode` from runtime71: PASS
- `kawa_reflection` directive added: PASS
- `hybrid` directive added: PASS
- Kawa safety rule (no silent interpretation): PASS

## SAFETY
- chronology unaffected: PASS — no chronology code touched
- canonical fact layer unaffected: PASS — no extraction code touched
- cognitive mode engine unaffected: PASS — `currentMode` untouched; uses separate `kawaMode`
- Kawa state fully parallel: PASS — all new state in `state.kawa.*` or `state.session.kawa*`

## DEFERRED ITEMS
- SVG river drawing (WO-KAWA-UI-01B)
- LLM-driven Kawa proposals (WO-KAWA-01 Phase 1)
- Kawa storage promotion to canonical (WO-KAWA-02 Phase 4)
- Chapter weighting UI in memoir panel (WO-KAWA-02 Phase 5)
- Kawa eval hooks (WO-KAWA-02 Phase 9)
- `renderMemoirChapters()` client-side Kawa overlay (future — currently LLM handles this via prompt context)

## NEXT WO
- WO-KAWA-01 Phase 1: Wire LLM into `kawa_projection.py` for real proposals
- WO-KAWA-02 Phase 4+: Storage promotion, chapter weighting, eval hooks
