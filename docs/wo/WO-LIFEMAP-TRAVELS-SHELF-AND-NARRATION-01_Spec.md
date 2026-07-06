# WO-LIFEMAP-TRAVELS-SHELF-AND-NARRATION-01

**Status:** ALL PHASES LANDED 2026-07-05 (same day as v2 approval). Live-tested Phase 1 mid-build; three live findings + three review findings fixed en route.

**Landing summary (2026-07-05):**
- **Phase 1 + 1.5** — Travels shelf (amber, between Later Years and Today, structurally never an era), picker, trip open → ONE deterministic Lori prompt in the main conversation (identity-gated, dedup'd per session), live trip outline panel (human labels only), photo strip → lightbox + metadata-only grounded prompt, "+ Add photos" (trip-level endpoint), runtime71 carries `active_trip_id`/`trip_style`.
- **Phase 2** — `services/trip_narration_capture.py`: deterministic parser (start/sequence/duration/month-year, negation suppression, uncertainty→observation, order + start corrections, place blocklist), chat_ws hook gated `HORNELORE_TRIP_NARRATION` (0 / **log** = dry-run / 1 = writes) — fires ONLY when a trip is open on the shelf; general chat is never trip-parsed.
- **Phase 3** — `apply_trip_narration`: provisional writes (stops with incrementing ord + `meta_json.source="narration"`), find-or-create "Journey" region, deterministic Untitled-trip birth (Lori never titles), duplicate-trip guard (needs_disambiguation, no create), reorders touch narration rows only, NEVER deletes; 8s panel auto-refresh while open so the outline visibly assembles.
- **Phase 4** — `GET /api/trips/{id}/date-confirmations` (metadata_trust full/time_only ONLY), FE offers ONE recognition confirmation per stop ever (localStorage offered-ledger — a shrug is never re-asked), order confirm pass fires ONCE per session after ≥2 narration-added stops ("did I get the order right?" — confirming what was heard).
- **Phase 5** — `guided_trip_walk` operator-selectable via `localStorage["lv_trip_style"]` (never default): hook-anchored directive variant with stories-win + shrug-once rules inline. NOTE: story-wins is directive-level in this landing; the runtime scheduler-suppression version (spec §3.5 REV 6) awaits a server-side route scheduler — tracked as the ONE open item, revisit after live narration evidence.
- **Live findings fixed en route:** Mirano order-confabulation (directive forbids sequence claims), double dispatch on shelf re-toggle (dedup), silent photo upload (ack prompt).
- **Review findings fixed en route:** BUG-TRIP-LEVEL-UPLOAD-OPERATOR-CONFIRMS-UNPLACED-PHOTO-01 (trip-level drops now `assignment_method='trip_upload'` conf 0.3 unconfirmed — cluster-placeable; migration 0018 extends the CHECK), BUG-TRAVELS-DISPATCH-BYPASSES-WO9-WARMUP-QUEUE-01 (queue-first dispatch), BUG-TRAVELS-DIRECTIVE-VALUE-SANITIZE-01 (`_promptSafe` on all interpolated values).
- **Tests:** 19 parser/writes (incl. Munich verbatim, negation-Vienna, maybe-Brno, operator-rows-never-moved, never-delete, duplicate guard, Untitled birth), 8 isolation/directive-discipline (comment-aware), 4 trip-level upload lock-ins.

v2 revision notes below preserved for design history.
**Lane:** Trips / narrator experience (Lane 2 behavior + Lane trips)
**Severity:** HIGH — the surface that makes trips usable by narrators, not just the operator.
**Parent specs:** `WO-TRIP-IMPORT-AND-CLUSTER-01` (schema/CRUD/bridge), `WO-TRIP-PHOTO-STOP-UPLOAD-AND-ELICIT-01` (Phases C1–C3), WO-TRIP-MEMOIR-01 (locked hierarchical schema).
**Related landed machinery this WO rides:** Life Map era-click → deliberate Lori prompt (Lane E 2026-05-03), factual-chain capture w/ `thematic_trip_chain` + `place_enumeration_sequence` cues (2026-07-02), Step 6b anchor-echo, story capture (`story_candidates` + `trip_story_links` table), C2 ingest pipeline + EXIF cross-check, C3 stop-grounded photo prompts, WO-LORI-CONFIRM-01 confirm-pass pattern, oral-history-default session style (migration 0010).

**Division of labor (locked by review):**
```
Operator Trip Tab   = curation / structure / photo management / provenance
Life Map Travels    = narrator entry point / storytelling
Same trip database underneath
```

---

## 1. What this builds (one paragraph)

A **"Travels" shelf on the Life Map** — below Later Years, above Today, visually distinct from the era spine — that opens a trip in the narrator's MAIN Lori conversation (not a separate page). Alongside the conversation, a **live trip outline panel** (★REV 1: not called "timeline" — that word is reserved for `timeline_events` / chronology surfaces; the canonical timeline bridge remains a separate deterministic projection) shows provisional stops, order, dates when known, and linked photos — visibly assembling while the narrator talks. The narrator says "I took a trip in May 2026 starting in Munich" and Munich appears on the panel, written by a deterministic system-side parser — never by Lori. Lori walks the journey chronologically as a listener, follows every story detour, offers EXIF-known dates for *confirmation* rather than asking for recall, and (in the operator-selectable guided style) moves through the route more briskly for capable narrators. Photos can be added from the panel; clicking a photo grounds the next Lori turn in that photo's trusted metadata only.

## 2. Why this design — reasons, with the failures and evidence behind each

### 2.1 Why a Life Map shelf and not a separate trips page/tab for narrators

- **Locked principle: Life Map is the only navigation surface.** A narrator-facing trips entry belongs ON the map or it fragments navigation (the same reason Memory River died).
- **The Lane E precedent already works:** era-click dispatching one deliberate, discipline-inlined Lori prompt is landed and live-verified. The Travels toggle is the same gesture class — no new interaction machinery.
- **Chris's live finding (2026-07-05):** the operator Trip Tab is form-heavy — correct tool for operator curation, wrong tool for narration.

### 2.2 Why Travels is a SHELF, not an 8th era

- The 7-era spine is canonical (WO-CANONICAL-LIFE-SPINE-01) and a trip *belongs to* an era via DOB derivation (Phase B bridge). Rendering Travels as an era would (a) teach narrators a false life-stage, (b) risk contaminating every consumer that derives from the era registry (memoir section ordering, era prompts, `era_id_from_age`). **Hard rule: Travels never enters `LV_ERAS`;** it is a separate DOM element with its own styling between the later_years and today buttons.

### 2.3 Why Lori converses in the MAIN conversation, not a new chat surface

- Single-thread context is a WO-10C guarantee; the main conversation already carries TTS, mic state machine, silence ladder, safety hook (chat_ws scan + LLM second layer), reflection shaping, language guards, and chain capture. A second chat surface would need all of it re-wired or would silently lack it. Reuse wins.

### 2.4 Why structure builds SYSTEM-SIDE from narration, and Lori never writes it

- **Locked principle 6:** Lorevox is the memory system; Lori is the conversational interface. Letting Lori carry structural reasoning is the path back to chatbot-memoir-generator failure modes.
- **Locked principle (2026-05-02, Patch B postmortem):** prompt-heavy rules make Lori worse; runtime/code shaping is the answer. Structure extraction = code (`trip_narration_capture`), not prompt paragraphs.
- **Locked principle 7:** mechanical truth must visibly project — the live panel IS this principle doing UX work (Polarsteps' say-it/see-it-pinned loop is the commercial validation).
- **Locked principle 5:** parser output is provisional; the operator Trip Tab remains the promote/edit surface.

### 2.5 Why not questionnaire-first — and what we keep from Chris's challenge

| QF failure | Applies to trips? |
|---|---|
| Interrogating for operator-seeded facts (principle 8) | **No** — a new trip is genuinely unknown. Point conceded to QF. |
| Turn-ownership races (SYSTEM_QF vs memory_echo/corrections/era-clicks) | Implementation disease; not reused either way. Neutral. |
| **Steamrolling story disclosures (BUG-212)** | **Worse for trips** — trip narration is denser with stories than any intake. Fatal. |
| **Date questions are memory tests** | **Worse for our population** — "what date did you leave Munich?" is a failable test for an 86-year-old recalling 1975 (WO-10C posture). |

Kept from the challenge: structured styles are operator-selectable overrides of the oral-history default (pivot framing) — see §3.5.

### 2.6 What the research says (gathered 2026-07-05) — and what it changed

1. **Conversational structured collection beats forms decisively** — SUS 80.2 vs 61.9 ([JMIR 2024](https://www.jmir.org/2024/1/e55164)); higher completion + more detail ([MDPI Computers 2025](https://www.mdpi.com/2073-431X/14/1/21)). → guided mode is a first-class, evidence-backed style.
2. **GoodTimes** asked direct W-questions, 92% positive ([JMIR Aging 2024](https://aging.jmir.org/2024/1/e49415)) — but scoped to *cognitively intact* adults and every question anchors on a photo physically present. → structured questions are safe **when anchored on something concrete**.
3. **Oral-history practice** ([Smithsonian](https://siarchives.si.edu/history/how-do-oral-history), [OHA](https://oralhistory.org/best-practices/), [PHMC](https://www.phmc.state.pa.us/portal/communities/oral-history/conduct.html)): chronological scaffold; follow the jumps and return; memories hang on hooks; **the interviewer supplies known dates rather than asking for them** → EXIF-seeded confirmations (§3.4).
4. **Commercial travel journals bound their prompting** — Journalfy's 6 prompts/entry ([Journalfy](https://journalfy.co/pages/about-the-journalfy-travel-journal-app)); Polarsteps step canvas ([Polarsteps](https://www.polarsteps.com/)). → guided mode uses a small per-stop prompt family.

## 3. Design contract (the rules the build is graded against)

### 3.1 Travels shelf
- Renders between Later Years and Today; distinct icon/color/label ("Travels"); NEVER in the era registry; zero effect on memoir section ordering, era prompts, or `era_id_from_age` (lock-in test).
- Click → one trip: open it. Multiple: warm picker. Zero trips: warm invitation to tell about one — no empty-form state, **but trip creation is deterministic** (★REV 4): the first parser-created trip is born with `title="Untitled trip"`, `meta_json.source="narration"`, `meta_json.status="provisional"`, `person_id=<active narrator>`, `meta_json.created_from_surface="travels_shelf"`. Title updates when the narrator names it ("Italy in 2026"). **Lori never invents the trip title.**

### 3.2 Trip conversation dispatch + session state
- Deterministic system directive (era-click pattern): trip title, date span, region names — mechanical truth only — plus interview discipline rules inlined (word cap, ONE question, no menus, ANTI-CONFABULATION applies).
- ★REV (order): trip session state lands as its own phase — `active_trip_id` (+ optional `active_trip_stop_id`) in the main conversation runtime + session style `trip_listening` / `guided_trip_walk` — BEFORE any parser work.
- Turn flow stays owned by the existing chat_ws pipeline; no new dispatcher, no first-prompt suppression (the QF lesson).

### 3.3 Narration capture (the new service) — staged, conservative, provisional
- `services/trip_narration_capture.py` — pure, deterministic, LAW 3-isolated (own isolation test). Per-turn parse for: month/year + day dates, trip-start markers ("starting in X", "flew into X"), sequence markers ("then we went to Y"), duration ("three nights in Z").
- ★REV 3 (staging before mutation): the parser **emits candidates first**. Dry-run phase renders candidates on the panel as "heard" items (session state + `[trip-narration]` log lines; optional debug table) with **zero trip-row mutation**. Only after the dry-run proves itself do provisional writes open, and then under hard conservatism:
  - **create only obvious stops** (high-confidence parse);
  - **NEVER delete from narration** (explicit rule);
  - **never overwrite operator-entered fields**;
  - **never auto-confirm**;
  - **never move/reorder operator-promoted rows** (reorders touch provisional rows only);
  - all writes carry `meta_json.source="narration"`, `status="provisional"`.
- ★REV 7 (low-confidence no-write): negations suppress entirely ("we never made it to Vienna" → no Vienna); uncertainty ("maybe Brno?", "I think it was somewhere near Munich", "not sure if that was this trip") emits a **parser observation / session note only — no row mutation**.
- Corrections: "no, Salzburg was before Vienna" → reorder against provisional stops only.
- ★REV 5 (duplicate-trip protection — named requirement): before creating a provisional trip from narration, the parser checks the narrator's existing trips for approximate match (same year, same place anchor, same month, title-token overlap, photo-cluster date-range overlap). On ambiguity it does NOT create; Lori asks one deterministic disambiguation: "I see the Spring 2026 Europe trip already here. Are you adding to that trip, or starting a different one?" **Requirement: no duplicate trip creation from ambiguous narration.**
- Gate: `HORNELORE_TRIP_NARRATION=0` default-off until live-verified.

### 3.4 EXIF-seeded confirmation (recognition over recall)
- When linked photos give a stop a trusted date (`metadata_trust ∈ {full, time_only}` only), Lori's directive includes ONE confirmation offer: "Your pictures from Munich are from around May 22nd — does that sound right?" Yes → date promoted provisional → confirmed-by-narrator; no/shrug → stays provisional, never re-asked.
- ★REV (precise ban): **Lori never asks the narrator to recall calendar dates.** Banned class: "what date / what day / what year / when exactly / when did you leave X". Natural non-testing "when" clauses remain allowed ("When you got there, who was with you?"). Dates enter via narration, EXIF confirmation, or operator entry.

### 3.5 Asking styles
- `trip_listening` (default): follows the story; chronology emerges; parser does all structure.
- `guided_trip_walk` (operator-selectable, same storage as existing session styles): route-forward, hook-anchored questions ("How did the trip begin?", "Where did the road take you after Prague?"; per-stop family ≤4 prompts: arrival / a meal or moment / who was there / onward). Not the default; Janice does not get it unless it proves safe.
- ★REV 6 (story-wins is RUNTIME, not directive-only — per the locked Patch B lesson): when a narrator turn carries `story_candidate` / `factual_chain` / `thematic_trip_chain` cues, the **dispatcher/session state suppresses the next scheduled route question** and follows the story. Enforced in code (comm-control / session scheduler), tested, with the directive as the soft layer on top.
- "I don't remember" accepted once per slot; slot marked asked-and-declined in session state; never re-asked.

### 3.6 Live trip outline panel (photos + provisional stops)
- Right-column panel (no modal). Refetch trip tree after turns with parser events; new/changed items render with a soft "just added" cue; candidates (dry-run) render as gently-styled "heard" items distinct from saved stops.
- ★REV 2 (hard narrator/operator boundary — the panel NEVER shows): confidence scores, `assignment_method`, `cluster_confidence`, `metadata_trust` labels, provisional/system jargon, parser warnings, review-queue language. Narrator sees normal human labels; the operator sees provenance in the Trip Tab. Enforced as a render-layer rule + acceptance check.
- Photos strip: linked, narrator-ready photos; "+ add photos" → C2 pipeline (trust, EXIF cross-check, sidecar pairing inherited).
- ★REV 9 (narrator uploads): default `narrator_ready=1` (their own act = self-vetting) AND stamped `metadata_json.uploaded_from_surface="travels_shelf"`, `needs_operator_review=1`, `review_reason="narrator_uploaded"` → operator queue item. Narrator keeps flowing; operator curates later.
- ★REV 8 (photo-click grounding safety): the injected photo prompt may use ONLY operator/photo metadata — stop name, trusted-or-confirmed date, visible caption/description, people labels on narrator-ready rows. It must NOT infer emotion, relationship, event meaning, or identity from image content (confabulation class; extends C3's grounding rule).

### 3.7 Confirm pass
- At natural pauses (silence past cue threshold with ≥2 new provisional stops, or session close), ONE summary confirmation: "So far I have Munich, then Prague, then Vienna — did I get the order right?" — confirming what was heard (WO-LORI-CONFIRM-01 pattern), never asking for what's missing.

## 4. Phases (★REV: parser proves itself before any DB mutation)

- **Phase 1 — Travels shelf read-only** (~1 day): shelf + picker + open existing trip in main conversation + panel rendering trip tree/photos + photo-click grounding + "+ add photos" wire. No parser.
- **Phase 1.5 — trip session state** (~0.25 day): `active_trip_id` / optional `active_trip_stop_id` in main-chat runtime; session style plumbing (`trip_listening` / `guided_trip_walk`). No writes.
- **Phase 2 — parser DRY-RUN** (~1 day): `trip_narration_capture.py` + isolation test + fixture pack (Chris's Munich sentence verbatim; a Janice-style meandering narration; negation; uncertainty; correction; duplicate-trip reference) + `[trip-narration]` event logging + candidates rendered as "heard" items on the panel. **Zero trip-row mutation.**
- **Phase 3 — provisional writes** (~0.75 day): create provisional trip/stops per §3.3 conservatism (create-only-obvious, never-delete, never-overwrite-operator, reorder-provisional-only) + duplicate-trip guard + deterministic first-trip creation.
- **Phase 4 — EXIF confirmations + confirm pass** (~0.75 day): trusted-date recognition offers, order confirmation, shrug ledger.
- **Phase 5 — guided mode** (~0.5 day): `guided_trip_walk` directive variant + story-wins RUNTIME guard in dispatcher/session state + per-stop prompt family.

## 5. Acceptance

1. **Shelf isolation:** Travels is not present in `LV_ERAS` and does not alter `era_id_from_age`, memoir section ordering, or era prompts (lock-in tests).
2. **Session state:** clicking Travels with one existing trip sets `active_trip_id` in the main chat session.
3. **Parser fixtures (offline):**
   - "I started in Munich, then Prague, but we never made it to Vienna" → Munich + Prague candidates only; Vienna suppressed.
   - "maybe Brno?" → no stop row (observation only).
   - "No, Salzburg was before Vienna" → reorders provisional stops only.
   - Operator-promoted stops are never moved by the parser.
   - "our Europe trip in 2026" with Spring 2026 existing → NO duplicate trip; disambiguation prompt emitted.
   - First narration-created trip carries title="Untitled trip" + narration provenance fields; Lori never titles it.
3. **Directive discipline (string-level tests):** no calendar-date-recall question in either style's directive; photo-click prompt composed from trusted metadata only (stop/date/caption/people-labels), no inferred emotion/identity.
4. **Runtime story-wins:** a turn carrying chain/story cues in guided mode suppresses the next scheduled route question (unit test on the scheduler, not just prompt text).
5. **Panel boundary:** narrator panel renders no confidence/method/trust/provisional/system vocabulary (render test + eyeball).
6. **Narrator uploads:** `narrator_ready=1` + `needs_operator_review=1` + `review_reason="narrator_uploaded"` + surface stamp; row appears in operator queue.
7. **Live (Chris):** open Travels → Spring 2026 → panel shows stops+photos; narrate a NEW small trip in guided mode → watch candidates then provisional stops assemble; one wrong-order correction → panel reorders; one "I don't remember" → never re-asked. Janice-style test in listening mode when parent sessions resume.

## 6. Stop conditions
- Lori asks a calendar-date-recall question → hard stop (memory-test class).
- Any parser write landing as confirmed/promoted truth without narrator confirmation or operator action → hard stop (principle 5).
- Parser deletes anything, ever → hard stop.
- Duplicate trip created from ambiguous narration → hard stop until the guard is fixed.
- Guided mode re-asks a declined slot or plows past a story disclosure → hard stop, back to listening-only (BUG-212 class).
- Narrator panel observed showing operator vocabulary (confidence/trust/provisional/etc.) → hard stop (principle 2, no operator leakage).

## 7. Sources
- GoodTimes AI photo album (W-questions; 92% positive; cognitively-intact scope): https://aging.jmir.org/2024/1/e49415
- Conversational collection vs forms, SUS 80.2 vs 61.9: https://www.jmir.org/2024/1/e55164
- Chatbots improve completion + data detail vs web forms: https://www.mdpi.com/2073-431X/14/1/21
- Smithsonian oral history guide (interviewer supplies known dates; hooks): https://siarchives.si.edu/history/how-do-oral-history
- Oral History Association best practices: https://oralhistory.org/best-practices/
- PHMC conducting oral history interviews: https://www.phmc.state.pa.us/portal/communities/oral-history/conduct.html
- Journalfy bounded per-entry prompt model: https://journalfy.co/pages/about-the-journalfy-travel-journal-app
- Polarsteps step model: https://www.polarsteps.com/
- Chorus of the Past, CHI 2025 (future reading for Phase 5+): https://dl.acm.org/doi/10.1145/3706598.3713810
- In-repo: CLAUDE.md locked principles 2/5/6/7/8; WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01; BUG-212; WO-LORI-CONFIRM-01; 2026-05-02 Patch B postmortem; WO-LORI-STORY-CAPTURE-01 golfball LAWs.

## Revision history
- 2026-07-05 — v1 authored for review after the Travels-shelf design conversation + QF adjudication + research pass.
- 2026-07-05 — v2 per review ("SPEC GOOD — APPROVE AFTER SMALL REVISION"): (1) "timeline" renamed to live trip outline panel (word reserved for timeline_events surfaces); (2) hard narrator-panel vocabulary boundary; (3) parser staged — dry-run candidates before provisional writes, never-delete explicit; (4) deterministic first-trip creation fields, Lori never titles; (5) duplicate-trip protection requirement + disambiguation prompt; (6) story-wins moved to runtime enforcement; (7) low-confidence no-write mode; (8) photo-click metadata-only grounding rule; (9) narrator-upload review metadata; (10) date ban precised to calendar-date recall; phases reordered 1 / 1.5 / 2-dry-run / 3-writes / 4 / 5; acceptance tests expanded per review list.
