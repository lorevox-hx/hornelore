# WO-LIFEMAP-TRAVELS-SHELF-AND-NARRATION-01

**Status:** SPEC FOR REVIEW — authored 2026-07-05 (design conversation w/ Chris; research-grounded). Implementation does NOT start until Chris approves.
**Lane:** Trips / narrator experience (Lane 2 behavior + Lane trips)
**Severity:** HIGH — this is the surface that makes trips usable by narrators, not just the operator.
**Parent specs:** `WO-TRIP-IMPORT-AND-CLUSTER-01` (schema/CRUD/bridge), `WO-TRIP-PHOTO-STOP-UPLOAD-AND-ELICIT-01` (Phases C1–C3: metadata trust, upload-at-stop, trip-scoped photo sessions), WO-TRIP-MEMOIR-01 (locked hierarchical schema).
**Related landed machinery this WO rides:** Life Map era-click → deliberate Lori prompt (Lane E 2026-05-03), factual-chain capture w/ `thematic_trip_chain` + `place_enumeration_sequence` cues (2026-07-02), Step 6b anchor-echo, story capture (`story_candidates` + `trip_story_links` table), C2 ingest pipeline + EXIF cross-check, C3 stop-grounded photo prompts, WO-LORI-CONFIRM-01 confirm-pass pattern, oral-history-default session style (migration 0010).

---

## 1. What this builds (one paragraph)

A **"Travels" shelf on the Life Map** — below Later Years, above Today, visually distinct from the era spine — that opens a trip in the narrator's MAIN Lori conversation (not a separate page). Alongside the conversation, a **side panel** shows the trip's photos and a **live timeline that visibly assembles while the narrator talks**: the narrator says "I took a trip in May 2026 starting in Munich" and Munich appears on the panel as a provisional stop, written by a deterministic system-side parser — never by Lori. Lori's job is to walk the journey chronologically as a listener, follow every story detour, offer EXIF-known dates for *confirmation* rather than asking for recall, and (in the operator-selectable guided style) move through the route more briskly for capable narrators. Photos can be added from the panel; clicking a photo grounds the next Lori turn in that photo.

## 2. Why this design — reasons, with the failures and evidence behind each

### 2.1 Why a Life Map shelf and not a separate trips page/tab for narrators

- **Locked principle: Life Map is the only navigation surface.** A narrator-facing trips entry belongs ON the map or it fragments navigation (the same reason Memory River died).
- **The Lane E precedent already works:** era-click dispatching one deliberate, discipline-inlined Lori prompt is landed and live-verified. The Travels toggle is the same gesture class — no new interaction machinery, no new risk surface.
- **Chris's live finding (2026-07-05):** the operator Trip Tab is form-heavy and "not very easy to use" — correct tool for operator curation, wrong tool for narration. Two users, two surfaces, one database.

### 2.2 Why Travels is a SHELF, not an 8th era

- The 7-era spine is canonical (WO-CANONICAL-LIFE-SPINE-01) and a trip *belongs to* an era via DOB derivation (Phase B bridge — Spring 2026 → later_years). Rendering Travels as an era would (a) teach narrators a false life-stage, (b) risk contaminating every consumer that derives from the era registry (memoir section ordering, era prompts, `era_id_from_age`). **Hard rule: Travels never enters `LV_ERAS`;** it is a separate DOM element with its own styling between the later_years and today buttons.

### 2.3 Why Lori converses in the MAIN conversation, not a new chat surface

- Single-thread context is a WO-10C guarantee; the main conversation already carries TTS, mic state machine, silence ladder, safety hook (chat_ws scan + LLM second layer), reflection shaping, and language guards. A second chat surface would need all of it re-wired or would silently lack it — the exact class of gap that made the photo-elicit page a *separate deliberate* build. Reuse wins.

### 2.4 Why the timeline builds SYSTEM-SIDE from narration, and Lori never writes structure

- **Locked principle 6:** Lorevox is the memory system; Lori is the conversational interface. Letting Lori carry structural reasoning is the path back to chatbot-memoir-generator failure modes.
- **Locked principle (2026-05-02, Patch B postmortem):** prompt-heavy rules make Lori worse; runtime/code shaping is the answer. Structure extraction = code (`trip_narration_capture` parser), not prompt paragraphs instructing Lori to collect fields.
- **Locked principle 7:** mechanical truth must visibly project — the live panel IS this principle doing UX work. Polarsteps' core loop (say it / see it pinned) is the commercial validation of visible assembly.
- **Locked principle 5:** parser writes are provisional (`source: narration` in row meta); the operator Trip Tab remains the promote/edit surface.

### 2.5 Why not questionnaire-first — and what we keep from Chris's challenge

Chris asked directly: what's wrong with QF for a separate, opt-in section? Honest adjudication against the four things that actually killed QF:

| QF failure | Applies to trips? |
|---|---|
| Interrogating for operator-seeded facts (principle 8) | **No** — a new trip is genuinely unknown. Point conceded to QF. |
| Turn-ownership races (SYSTEM_QF vs memory_echo/corrections/era-clicks) | Implementation disease; we would not reuse that machinery either way. Neutral. |
| **Steamrolling story disclosures (BUG-212, the mastoidectomy)** | **Worse for trips.** Trip narration is denser with stories than any intake; a next-field loop plows past exactly the material the system exists for. Fatal. |
| **Date questions are memory tests** | **Worse for our population.** "What date did you leave Munich?" is a lookup for Chris and a failable test for an 86-year-old recalling 1975 — violates WO-10C's never-put-the-narrator-in-a-position-to-fail posture. |

What we keep from the challenge: the pivot framing already allows **structured styles as operator-selectable overrides** of the oral-history default — so a guided walk isn't forbidden, it's a style. See §2.6.

### 2.6 What the research says (gathered 2026-07-05) — and what it changed

1. **Conversational structured collection beats forms decisively** — a family-health-history chatbot scored SUS 80.2 vs 61.9 for the form equivalent ([JMIR 2024](https://www.jmir.org/2024/1/e55164)); chatbot collection on citizen-science platforms gets higher completion and more detail than web forms ([MDPI Computers 2025](https://www.mdpi.com/2073-431X/14/1/21)). → **Chris's instinct is evidence-backed: a chat that collects structure is a good pattern**, and validates guided mode as a first-class style, not a grudging concession.
2. **GoodTimes** asked direct Who-What-When-Where questions and got 92% positive from older adults ([JMIR Aging 2024](https://aging.jmir.org/2024/1/e49415)) — BUT the study scoped to *cognitively intact* participants, and every W-question anchors on a photo physically in front of the person (perceptual anchor), never abstract recall. → structured questions are safe **when anchored on something concrete**; that's the design line, not "questions bad."
3. **Oral-history practice** ([Smithsonian](https://siarchives.si.edu/history/how-do-oral-history), [OHA](https://oralhistory.org/best-practices/), [PHMC](https://www.phmc.state.pa.us/portal/communities/oral-history/conduct.html)): chronological structure is the right scaffold; memory jumps and the interviewer follows and returns; memories hang on "substantial hooks" (arrival, meal, typical day — not dates); and **the interviewer supplies known names/dates to jog memory rather than asking for them**. → The single biggest design change from research: **EXIF-seeded confirmations** (§3.4). We have the dates; recognition beats recall; Lori offers, never asks.
4. **Commercial travel journals bound their prompting** — Journalfy uses six fixed prompts per entry, ~5 minutes ([Journalfy](https://journalfy.co/pages/about-the-journalfy-travel-journal-app)); Polarsteps pins a canvas to time+place per step ([Polarsteps](https://www.polarsteps.com/)). → guided mode uses a small per-stop prompt family, not an open checklist crawl.

### 2.7 Why two asking styles over one extraction engine

- Default `trip_listening` (oral-history default, pivot-locked) for narrators like Janice; operator-selectable `guided_trip_walk` for capable, goal-oriented narrators like Chris (pivot framing: "structured styles become operator-selectable overrides of that default"). Same parser, same writes, same panel — only the directive differs, so the second style costs ~half a day.

## 3. Design contract (the rules the build is graded against)

### 3.1 Travels shelf
- Renders between Later Years and Today; distinct icon/color/label ("Travels"); NEVER in the era registry; zero effect on memoir section ordering, era prompts, or `era_id_from_age`.
- Click → one trip: open it. Multiple: warm picker (reuses narrator trip-card styling). Zero trips: warm invitation to tell about one ("guided by what the narrator says," creates a provisional trip on first narration — no empty-form state).

### 3.2 Trip conversation dispatch
- Deterministic system directive (era-click pattern): trip title, date span, region names — mechanical truth only — plus interview discipline rules inlined (≤ word cap, ONE question, no menus, ANTI-CONFABULATION applies).
- Turn flow stays owned by the existing chat_ws pipeline; no new dispatcher, no first-prompt suppression (the QF lesson).

### 3.3 Narration capture (the new service)
- `services/trip_narration_capture.py` — pure, deterministic, LAW 3-isolated (no imports from extract/chat_ws/prompt_composer; own isolation test). Per-turn parse of narrator text for: month/year + day dates ("in May 2026", "on the 22nd"), trip-start markers ("starting in X", "flew into X"), sequence markers ("then we went to Y", "after that", "on the way to"), duration ("three nights in Z").
- Writes through `trip_repository` as **provisional** (`meta_json.source="narration"`, `meta_json.status="provisional"`); trip/region/stop creation mirrors what the C2/Phase A endpoints do; `sync_trip_to_life_record` fires after mutations (era + timeline event come free).
- Negations and uncertainty suppress writes ("we never made it to Vienna" must NOT create Vienna; "maybe Brno?" → note, not stop) — utterance-frame negation machinery is the reference pattern.
- Corrections flow: "no, Salzburg was before Vienna" → parser emits a reorder against provisional stops only; operator-promoted stops are never auto-moved (operator truth wins, same rule as photo links).
- Gate: `HORNELORE_TRIP_NARRATION=0` default-off until live-verified.

### 3.4 EXIF-seeded confirmation (recognition over recall — the research addition)
- When clustered/linked photos give a stop a trusted date (`metadata_trust ∈ {full, time_only}` only — never suspect_scan), Lori's directive includes ONE confirmation offer: "Your pictures from Munich are from around May 22nd — does that sound right?" Yes → date promoted from provisional to confirmed-by-narrator; no/shrug → stays provisional, never re-asked.
- Hard rule: Lori never asks an open "when" question in either style. Dates enter via narration, EXIF confirmation, or operator entry. Full stop.

### 3.5 Asking styles
- `trip_listening` (default): follows the story; chronology emerges; parser does all structure.
- `guided_trip_walk` (operator-selectable per narrator/session, same storage as existing session styles): Lori moves route-forward with hook-anchored questions ("How did the trip begin?", "Where did the road take you after Prague?", per-stop family ≤4 prompts: arrival / a meal or moment / who was there / onward). Two QF-proof rules baked into the directive AND enforced by comm-control: (a) any story disclosure wins over the next structural question — chain/story cues already detect this; (b) "I don't remember" is accepted once and that slot is never re-asked (parser marks it asked-and-declined in session state).

### 3.6 Side panel (photos + live timeline)
- Right-column panel (no modal — no modal pattern exists in the narrator flow and overlays disorient older narrators). Poll or refetch trip tree after turns with parser writes; new/changed provisional stops render with a soft "just added" cue.
- Photos strip: linked, narrator-ready photos; click → grounded photo prompt injected as the next Lori turn (C3 template, stop-grounded); "+ add photos" → C2 stop/trip upload pipeline (trust badges, EXIF cross-check, sidecar pairing all inherited). Narrator uploads default `narrator_ready=1` (their own act = self-vetting) AND surface in the operator review queue (agreed 2026-07-05).
- Everything on the panel is narrator-designed: no confidence scores, no "provisional" system-tone labels — provisional shows as normal entries; the operator sees provenance in the Trip Tab.

### 3.7 Confirm pass (Phase 3)
- At natural pauses (narrator silence past cue threshold with ≥2 new provisional stops, or session close), Lori may offer ONE summary confirmation: "So far I have Munich, then Prague, then Vienna — did I get the order right?" — confirming what was heard (allowed, WO-LORI-CONFIRM-01 pattern) vs asking for what's missing (forbidden).

## 4. Phases

- **Phase 1 — Travels shelf + trip open + side panel (read-only)** (~1 day): shelf element + picker + trip directive dispatch + panel rendering photos/tree + photo-click grounding + "+ add photos" wire. No parser yet — panel shows the operator-built trip. Live-testable immediately against Spring 2026.
- **Phase 2 — narration capture** (~1.5 days): parser service + isolation test + chat_ws consumer hook (gated) + provisional writes + live panel assembly + negation/uncertainty suppression + fixture pack (Chris's Munich sentence verbatim as the first fixture; a Janice-style meandering narration as the second; negation case; correction case).
- **Phase 3 — EXIF confirmations + confirm pass + guided style** (~1 day): trusted-date confirmation offers, order-confirmation at pauses, `guided_trip_walk` directive variant + accepted-shrug ledger.
- **Phase 4 — polish after live test** (sized later): correction robustness, multi-trip disambiguation in narration ("on our OTHER trip to Germany"), chain-capture → suggested-stops merge (ties to the competitive-gaps ledger item 1).

## 5. Acceptance
1. Offline: shelf never appears in era registry consumers (lock-in test); parser fixture pack green incl. negation + correction + shrug-once; provisional writes carry narration provenance; operator-promoted rows never auto-moved; discipline: zero open "when" questions in either style's directive (string-level test).
2. Live (Chris): open Travels → Spring 2026 → panel shows stops+photos; narrate a NEW small trip in guided mode → watch it assemble; give one wrong-order correction → panel reorders; one "I don't remember" → never re-asked; Janice-style test in listening mode when parent sessions resume.
3. Principle sweep: no operator leakage on the panel, no system-tone, no confabulated attribution, all parser writes provisional, safety + language guards untouched.

## 6. Stop conditions
- Lori asks for a date in the open form → hard stop (memory-test class).
- Any parser write that lands as confirmed/promoted truth without narrator confirmation or operator action → hard stop (principle 5).
- Guided mode observed re-asking a declined slot or plowing past a story disclosure → hard stop, back to listening-only until fixed (BUG-212 class).

## 7. Sources
- GoodTimes AI photo album, older adults, W-question design + 92% positive (cognitively-intact scope): https://aging.jmir.org/2024/1/e49415
- Conversational collection vs forms, SUS 80.2 vs 61.9 (family health history chatbot): https://www.jmir.org/2024/1/e55164
- Chatbots improve completion + data detail vs web forms (citizen science): https://www.mdpi.com/2073-431X/14/1/21
- Smithsonian oral history guide (chronology as scaffold; interviewer supplies known dates; hooks): https://siarchives.si.edu/history/how-do-oral-history
- Oral History Association best practices: https://oralhistory.org/best-practices/
- PHMC conducting oral history interviews (memories hang on substantial hooks): https://www.phmc.state.pa.us/portal/communities/oral-history/conduct.html
- Journalfy bounded per-entry prompt model (6 prompts / ~5 min): https://journalfy.co/pages/about-the-journalfy-travel-journal-app
- Polarsteps step model (canvas pinned to time+place; Travel Book): https://www.polarsteps.com/
- Chorus of the Past, CHI 2025 (multi-agent conversational reminiscence w/ artifacts — future reading for Phase 4): https://dl.acm.org/doi/10.1145/3706598.3713810
- In-repo: CLAUDE.md locked principles 5/6/7/8; WO-QUESTIONNAIRE-FIRST-RETIRE-LIVE-01 (QF retirement rationale); BUG-212 (story steamroll); WO-LORI-CONFIRM-01 (confirm-pass pattern); 2026-05-02 Patch B postmortem (runtime shaping over prompt rules); WO-LORI-STORY-CAPTURE-01 golfball LAWs (Path-1-must-succeed pattern for the parser lane).

## Revision history
- 2026-07-05 — Authored for Chris's review after the Travels-shelf design conversation + QF adjudication + research pass. NOT yet approved for build.
