# WORK AUDIT — 2026-07-05

Full reconciliation of every WO/BUG spec, report, handoff, and architecture doc
against code reality, run before opening the Trip Integration build (Phases A–D).
Three parallel doc sweeps + direct code verification of every contested claim.
**Trust order when documents disagree: code > tests > this audit > checklist > spec status lines.**

## Headline findings

1. **Gates 5 + 6 are LIVE.** `.env` carries `HORNELORE_SAFETY_LLM_LAYER=1` and
   `HORNELORE_SOFTENED_RESPONSE=1` (verified 2026-07-05). The checklist and the
   2026-07-02 adjudication both still frame the flag flip as the pending blocker —
   stale in the opposite direction now. Remaining Gate 5/6 work is a FORMAL
   verification record (red-team pack + softened-persistence harness on the live
   flags), not a flip.
2. **Spec status-line drift is systemic.** At least six specs carry status lines
   contradicted by code: the six pivot WOs still read "not started" in their own
   headers (all landed, verified again today: `safety_classifier.py`,
   `lori_softened_response.py`, `reflection_grounding.py`, `story_momentum.py`,
   `thread_bank.py`, `question_hierarchy.py`, `bio_anchored_asker.py`,
   oral_history default live in comm-control); BUG-LORI-RESPONSE-STUB-COLLAPSE
   still says detection-only (iteration-2 substitution + threshold-5 landed);
   WO-LORI-FACTUAL-CHAIN-CAPTURE says unclear (landed, harness-green);
   WO-STORY-CANDIDATE-TEXT-CHAIN-PERSISTENCE says queued (chain_rows persist in
   live harness runs). Doc-sync pass needed; do NOT re-implement from status lines.
3. **Lifecycle/deletion debt is broader than trips.** ~10 person-scoped tables are
   missing from `person_delete_inventory` / `hard_delete_person` coverage, most
   without FK constraints to people: photos, photo_sessions, memory_archive_sessions/
   turns, media_archive_items/people, story_candidates, bio_facts, and now the trip
   tables. Hard-deleting a narrator orphans all of it silently — locked principle 4
   violation at system scope, not a trip-lane nit. Fix once, for all tables.

## Verified DONE (recent, code-confirmed)

- Conversation layer 2026-07-01→02 batch: Spanish-detector overfire class (both
  detectors + phrase tier + lang-pin), thematic + enumeration chain cues,
  deterministic sensory-pivot-on-chain guard, anchor-echo Step 6b, junk-anchor
  blocklist, stub threshold G4 alignment, seeded-fact guard wiring (was dead in
  production until 2026-07-05 — status line said CLOSED since 06-17; the guard
  never received seeded_facts until the wiring fix).
- Trip lane Phases 1–4: schema 0015, import (JSON/CSV), EXIF clustering, review
  queue, stop-edit, delete, memoir preview + DOCX, operator console, top-level
  Trips shell tab (active-narrator scoped), narrator-safe room card + popover.
- All six pivot WOs code-complete with test suites; Gates 5/6 flags live (above).
- Six 2026-06-17 bug closures verified real (conv-FK, facts-422, scorer-hardening,
  anchor-cascade, meta-leak, phrase-as-name, child-abuse-false-positive).

## Genuinely OPEN — the ledger

### Lane 1 — Trip integration (the active build)
- Phase A: create/edit UX + missing region/stop create/delete/reorder ENDPOINTS
  (repo functions exist; router never exposes them).
- Phase B: era derivation from DOB; timeline projection (`trip_stops.timeline_event_id`
  is an orphan column — confirmed never written); chronology-accordion / era-click
  surfacing; lifecycle coverage (fold into the system-wide fix below).
- Phase C: photo flow at scale (in-surface upload, per-stop galleries, bulk review).
- Phase D: Lori + memoir (location-notes UI + runtime consumption;
  trip_story_links/trip_bio_suggestions writers — tables verified reader/writer-less;
  main-memoir section proposals).

### Lane 2 — System-wide lifecycle fix (principle 4)
- Extend delete-inventory + hard-delete + Reset Identity to ALL person-scoped
  tables (list in headline 3). One WO, one migration-free patch to db.py + reset
  path + inventory endpoint. Should land WITH trip Phase B.

### Lane 3 — Safety formalization
- Gate 5/6 formal verification on the live flags (red-team pack across chat +
  interview paths; softened-persistence harness). Flags are ON — evidence record missing.
- Gate 7 truth-pipeline observability: RED, never scoped. Needs a spec.

### Lane 4 — Open behavior bugs (spec exists, code missing or partial)
- BUG-LIFEMAP-COMM-CONTROL-TRIM-01 (open, options A+B unbuilt).
- BUG-LIFEMAP-CONTEXT-TRUNCATION-01 (open, layers 1+2 unbuilt).
- BUG-LORI-SPANISH-MISFIRE-ENGLISH-SESSION-01 — likely substantially closed by the
  07-02 detector + lang-pin work; needs re-adjudication against its repro, then
  close or narrow.
- BUG-LORI-DEEP-EUROPEAN-ROUTE-LANGUAGE-DRIFT-01 — Path A landed; Path B/C
  conditional on recurrence (watch harnesses).
- BUG-LORI-FEWSHOT-EXEMPLAR-LEAK-01 — Path A landed; Path D conditional on recurrence.
- BUG-LORI-FACTUAL-OVER-SENSORY-PROBE-01 — chain class closed; era-click /
  narrative-cue scope still open.
- 2019 T8 M1/M2 meta-feedback lookback miss (detector only checks last assistant
  turn) — known, unfixed, unspec'd.

### Lane 5 — Forgotten (promised, then buried in the pre-pivot archive)
These three were banked 2026-05-07 from the Melanie Zollner live test, archived in
the pivot sweep, and never resurrected despite being REAL product gaps:
- BUG-LORI-CORRECTION-ABSORBED-NOT-APPLIED-01 Phase 3 (corrections acknowledged
  but data layer keeps the wrong story).
- BUG-LORI-MIC-MODAL-NO-LIVE-TRANSCRIPT-01 (mic-driven narrators can't see their
  own words; FocusCanvas skeleton exists).
- BUG-STT-PHANTOM-PROPER-NOUNS-01 layers 2–3 ("hold my hand" → "Hannah").
Also forgotten: **WO-MEMOIR-STORY-CANDIDATES-WIRE-01 was never written** — story
candidates still reach NO memoir surface (main memoir exports from FE-built
sections only). This is a prerequisite for trips Phase D and for the memoir being
honest about captured stories. Write it next.

### Lane 6 — Parked with conditions (deliberate, keep parked; verify conditions)
- Utterance-frame Phases 3–6 consumers (opens after BINDING-01 second-iteration
  evidence). Narrative-cue runtime consumption (instrumentation-only by design).
- Extractor lane: BINDING-01 iteration 2, SPANTAG re-enable gate, #144 Lane 2,
  #97 value-alt-credit, LORI-CONFIRM v1 (+dateRange v1.1 unlocked), MULTITURN
  harness, Pheno, AFFECT-ANCHOR, KORIE, model A/Bs.
- Memory-exercise implementation WO (row 7 — style exists at 60-word cap, picker
  entry shelved; ADR says keep; WO still undrafted).
- WO-INTAKE-IDENTITY-01 v3 (pending two Chris decisions from 2026-04-22).

### Lane 7 — Ops / docs hygiene
- Master extraction eval stale since 2026-05-01 (75/110) despite extractor guard
  changes since; re-run wanted.
- Orphaned eval packs without active runners: cultural-humility (12), code-switching
  live-behavior (12), sentence-diagram cultural (22).
- Vestigial flags (LV_SHOW_DEBUG_PILLS / LV_ENABLE_AFFECT / LV_ENABLE_CAMERA /
  LV_ENABLE_TTS): wire-or-delete decision still open (since 2026-04-27).
- UI dead code: lvNarratorReturnToOperator(); the retired .lv-narrator-view-tabs
  strip (contains unreachable Photos + Trips buttons — remove strip + my dead
  Trips button); Photos room view now unreachable by any visible control (decide:
  Photos card in Life Map column, or retire renderer).
- Narrator list still carries harness TEST rows; cleanup script run pending.
- Spec status-line sync pass (headline 2) + checklist Gates 5/6 correction +
  README historical-section cleanup.
- QUESTIONNAIRE-BIO-FACTS-MIGRATE Phase 7 live verify still pending.

### Lane 8 — Strategy (Chris's decisions, not code)
- The seven pre-rebrand decisions from HORNELORE-UNIVERSAL-PIVOT-STRATEGY
  (deployment model, operator model, family surfaces, tenant model, data
  portability, memoir deliverable shape, Tier 3 keep/delete) — all still open.

## Corrections to the sweep-agent reports (for the record)
- Agent 1's "SPEC-ONLY" verdicts on the six pivot WOs are wrong (read status
  headers, not code). Its DONE verdict on ASKS-WHAT-OPERATOR-SEEDED predates the
  dead-wiring discovery. Stub-collapse and text-chain-persistence verdicts stale.
- Agent 2's tier list included three items already closed 07-02 (Spanish accents,
  thematic detection, trip WOs "unwritten").
- Agent 3's claim that data/evals + data/qa + data/lori don't exist is false
  (wrong working directory); its lifecycle-gap and orphan-column findings were
  verified and stand.

## Recommended order from here
1. **Trip Phase A + B**, with the lifecycle fix broadened to ALL missing tables
   (Lane 2 rides along — one deletion-coverage patch instead of a trips-only one).
2. **WO-MEMOIR-STORY-CANDIDATES-WIRE-01** — write + build; unblocks trips Phase D
   and makes the memoir honest about captured stories.
3. Gate 5/6 formal verification run (flags are already live — get the evidence).
4. Behavior-bug batch: M1/M2 lookback, LIFEMAP trim/truncation pair, re-adjudicate
   SPANISH-MISFIRE.
5. Resurrect the Melanie trio (correction-applied first — it's a trust issue).
6. Docs-sync pass (status lines, checklist, README) — half a session, prevents the
   next agent from re-implementing landed work.
