# WO-TIMELINE-RENDER-01 — Mechanical Timeline Render (Read-Only v1)

**Status:** ACTIVE (parallel cleanup lane, parent-session-non-blocking)
**Pair WO:** WO-TIMELINE-CONTEXT-EVENTS-01 (curated world/local events that this renderer consumes)
**Ancestor:** HorneHX/Lifeline (PHP/MySQL) — `CalendarEvents` + `Media` tables + EXIF/GPS/geocode + `manage_locations.php`. Lorevox does NOT rebuild that codebase. It pulls forward the architectural pattern and reuses the schema bones already in-tree (migrations 0001 photos + 0004 story_candidates).
**Author:** Chris + Claude (2026-05-05)
**Flag:** `HORNELORE_TIMELINE_RENDER_V1=0` (default-off; endpoint 404s when off)

---

## North Star (do not relitigate)

**The Life Map is the interview engine. The Timeline is the visible artifact of the work.**

**Lori does not generate the timeline. She talks beside it.** The timeline is mechanically rendered from stored data. No LLM call at render time. No Lori opinion of where to put a fact.

The timeline is *cognitive scaffolding*, not decoration — it tells the narrator what they've covered, what's left, where they are in time. That's load-bearing for the interview, not optional polish. Future agents reading this spec must not deprioritize timeline correctness on the assumption that "it's just visual."

---

## Concept (locked)

```
Life Map / Accordion          Timeline
=========================     =========================
ACTIVE interview surface  →   PASSIVE rendered artifact
narrator clicks an era    →   visual chronological projection
Lori opens a warm prompt  →   confirmed memory + photos + context
```

Both are load-bearing. Different jobs. The accordion (per-era container in the timeline) mirrors how older adults recall life — in chunks, not exact dates. The timeline translates those chunks into a visible life arc.

---

## v1 Scope

**Read-only render endpoint** that pulls existing data into a per-era grouped timeline shape. Zero new authoring surfaces. Zero LLM calls. Zero Lori-write paths.

### Data sources (all already exist in-tree)

| Source | Table / surface | Notes |
|---|---|---|
| Narrator basics | `profiles.profile_json` (canonical) + `interview_projections.projection_json` (provisional, per Phase A read-bridge 2026-05-04) | Identity facts, family structure, key dates. Pin-able if dated. |
| Story pins (interview quotes) | `story_candidates` (migration 0004) where `review_status IN ('promoted', 'confirmed')` | Each candidate has `era_candidates`, `age_bucket`, `estimated_year_low/high`, `scene_anchors`, `transcript`. |
| Photos | `photos` (migration 0001) where `deleted_at IS NULL` | Has `date_value` / `date_precision` / `location_label` / `latitude` / `longitude`. EXIF + manual edits both flow here. |
| Photo memories | `photo_memories` (migration 0001) joined via `photo_session_shows` | Narrator-spoken stories about photos. Pin-able as quote-on-photo. |
| World/local events | `timeline_context_events` (NEW — see WO-TIMELINE-CONTEXT-EVENTS-01) | Operator-curated. v1 renderer accepts an empty table or sample-fixture and renders zero events gracefully. |

### Era derivation (load-bearing rule)

A timeline item lands in an era_id by computing the narrator's age at the item's date, then mapping that age to a canonical era via `LV_ERAS` (already in-tree at `server/code/api/lv_eras.py` + `ui/js/lv-eras.js`). The 7 canonical eras are:

```
earliest_years, early_school_years, adolescence,
coming_of_age, building_years, later_years, today
```

### Date precision rules (locked)

| Precision | Rendered as | Era assignment |
|---|---|---|
| `exact` | exact pin (e.g. "1944-08-12") | year → age → era_id |
| `month` | month-level pin (e.g. "August 1944") | year → age → era_id |
| `year` | year pin (e.g. "1944") | year → age → era_id |
| `decade` | **approximate decade band** rendered inside the era container with a visible uncertainty qualifier (`~1940s` / `circa 1950s` / `early 1960s`) | item lands inside the era container that overlaps the decade, but **must visibly preserve uncertainty** in the rendered string |
| `unknown` | "Undated Memories" collapsible section, rendered last | not assigned to any of the 7 eras |

**Locked rule (do not relitigate):** *Never silently midpoint a decade-precision item.* A `1950s` photo must not become `1955` in the rendered string. Approximate items render with their approximation visible. The narrator and operator both see "circa 1950s" — never an invented exact year.

**Era assignment for approximate items:** when a decade overlaps two eras (e.g., a 1940s decade item for a narrator born 1944 spans both `earliest_years` and `early_school_years`), the renderer places the item inside whichever era container contains the midpoint of the narrator's overlap with that decade — but the rendered label retains the `~1940s` qualifier. This is a placement decision, not a date assertion.

**Rule:** items NEVER write `era_id` back to source rows. The era is computed at render time from date + narrator DOB. This keeps the timeline read-only in both directions — source rows don't gain timeline-only metadata that would later need to be migrated.

### Endpoint shape

`GET /api/narrator/{narrator_id}/timeline`

Query params:
- `era_id` (optional) — return only items in this era; omit for full timeline
- `include` (optional) — comma-separated list: `facts,quotes,photos,memories,events,undated` (default: all)

Response:
```json
{
  "narrator_id": "...",
  "narrator_birth_year": 1944,
  "narrator_lifetime_year_range": [1944, 2026],
  "eras": [
    {
      "era_id": "earliest_years",
      "label": "Earliest Years",
      "year_range": [1944, 1949],
      "items": [
        {
          "kind": "fact",
          "year": 1944,
          "year_range": [1944, 1944],
          "title": "Born in Spokane, Washington",
          "source": "profiles.profile_json:personal.placeOfBirth+dateOfBirth",
          "confidence": "confirmed",
          "payload": { "place": "Spokane, Washington", "date": "1944-08-12" }
        },
        {
          "kind": "photo",
          "year": 1947,
          "year_range": [1947, 1947],
          "title": "Family photo",
          "source": "photos:abc123",
          "confidence": "high",
          "payload": {
            "photo_id": "abc123",
            "thumbnail_url": "...",
            "media_url": "...",
            "description": "...",
            "location_label": "...",
            "date_precision": "year"
          }
        },
        {
          "kind": "event",
          "year_range": [1947, 1947],
          "title": "Spokane Expo",
          "source": "timeline_context_events:nd_..." ,
          "confidence": "operator_curated",
          "payload": { "scope": "regional", "region_tags": [...], "description": "...", "citation": "..." }
        }
      ]
    },
    ...
  ],
  "undated": { "items": [...] }
}
```

**Item kinds:** `fact` / `quote` / `photo` / `memory` / `event`. Each carries `kind`, `year` (or `year_range`), `title`, `source` (string identifying the row), `confidence` (`confirmed` / `provisional` / `high` / `medium` / `low` / `operator_curated`), and a `payload` shaped for that kind.

**Sort within era:** ascending year, then `kind` priority order: `fact`, `quote`, `memory`, `photo`, `event`. Items with `year_range` sort by `year_range[0]`.

### What's NOT in v1

- No timeline editing (drag-to-rearrange, re-date, etc.)
- No promoting / refining / discarding items from the timeline UI (review queue stays on Bug Panel surfaces)
- No memoir export integration (lands in v2 — embeds the rendered timeline into the .docx export)
- No real-time updates (page refresh re-fetches; no WebSocket / SSE)
- No interactive zoom / decade strip / day strip — v1 renders the per-era accordion at one density level
- No Lori contribution path (none, ever — Lori does not write to the timeline; world events come from operator curation per WO-TIMELINE-CONTEXT-EVENTS-01)

---

## Implementation phases

### Phase A — backend endpoint (read-only)

1. New router `server/code/api/routers/timeline.py` exposing `GET /api/narrator/{narrator_id}/timeline`
2. Service module `server/code/api/services/timeline_render.py` with pure functions:
   - `assemble_timeline(narrator_id, *, include=...) → TimelineRenderResult`
   - `_pull_facts(profile_json, projection_json) → list[FactItem]`
   - `_pull_quotes(narrator_id) → list[QuoteItem]` (reads `story_candidates` where `review_status IN ('promoted', 'confirmed')`)
   - `_pull_photos(narrator_id) → list[PhotoItem]` (reads `photos` where `deleted_at IS NULL`)
   - `_pull_memories(narrator_id) → list[MemoryItem]` (reads `photo_memories` joined via `photo_session_shows`)
   - `_pull_events(narrator_lifetime_range, region_tags, heritage_tags) → list[EventItem]` (reads `timeline_context_events` — see pair WO; v1 returns `[]` if table is empty)
   - `_assign_era(item, narrator_dob) → era_id | "undated"` using `lv_eras.year_to_era_id(year, dob)` helper (NEW small helper)
3. Build-gate isolation test (`tests/test_timeline_render_isolation.py`) following the LAW 3 INFRASTRUCTURE pattern from `test_story_preservation_isolation.py`. Forbidden imports for `timeline_render.py`: `api.routers.extract`, `api.prompt_composer`, `api.memory_echo`, `api.routers.llm_*`, `api.routers.chat_ws`, `api.services.story_trigger`, `api.services.lori_*`. Allowlist: `api.lv_eras`, `api.db` (read-only accessors only).
4. Unit tests (`tests/test_timeline_render.py`) covering: era assignment with each precision level, undated bucket, empty narrator, narrator with only facts (no photos / no quotes), narrator with photos but no DOB (graceful — items render but era_id falls to undated), `include` filter behavior.
5. Endpoint gated behind `HORNELORE_TIMELINE_RENDER_V1=0` env flag — returns 404 when off, mirrors `operator_eval_harness` posture.

### Phase B — frontend accordion render

1. New JS module `ui/js/timeline-render.js` (IIFE) — fetches `/api/narrator/{narrator_id}/timeline`, renders 7 era accordions + 1 undated bucket
2. CSS in `ui/css/timeline.css` — single density level for v1, era headers + items list per era, photo thumbnails inline
3. Mount point in `ui/hornelore1.0.html` — new tab in the narrator-room or a dedicated route under the operator surface (not narrator-facing yet for v1; operator-eyes-only behind `HORNELORE_TIMELINE_RENDER_V1`)
4. v1 photo lightbox can reuse the existing narrator-room photo lightbox (WO-LORI-PHOTO-* trail); quotes render as text bubbles; events render as small italic background pins

### Phase C — sample / fixture data

For development before WO-TIMELINE-CONTEXT-EVENTS-01 ships real curation, ship a `data/timeline_context_events/sample_pack.json` with 10–20 hand-authored events covering Janice's lifetime (German-Russian / ND prairie tags) so the renderer has visible data to render against. Sample pack documents that real events come from operator-curated researched sources, not this fixture.

### Phase D — accordion polish (optional, post-v1)

- Density bands (decade strip vs era strip vs day strip) when item count exceeds a threshold per era
- Mini-map / scrub bar showing relative density across the lifetime
- Photo cluster collapse (multiple photos same year → single cluster card)

---

## Acceptance gates

**Phase A passes when:**

- Endpoint returns 200 with empty narrator → `{ "narrator_id": ..., "eras": [...7 eras with empty items...], "undated": { "items": [] } }`
- Endpoint returns 200 with seeded narrator → eras populated correctly per fixture
- Era assignment correct for each `date_precision` level (`exact` / `month` / `year` / `decade` / `unknown`)
- Photos with `deleted_at IS NOT NULL` excluded
- Story_candidates with `review_status NOT IN ('promoted', 'confirmed')` excluded
- World_events filtered by overlap of narrator's lifetime range and event's year/year_range
- Build-gate isolation test passes (negative-test verified: temporarily inject a forbidden import, confirm gate fails, revert)
- Endpoint 404s when `HORNELORE_TIMELINE_RENDER_V1=0`

**Phase B passes when:**

- 7 era accordions render with correct labels (`Earliest Years` / `Early School Years` / `Adolescence` / `Coming of Age` / `Building Years` / `Later Years` / `Today`) + Undated section
- Each item kind renders distinctly (fact = bold text, quote = italic with quote marks, photo = thumbnail + caption, memory = quote attached to photo, event = small italic pin)
- Empty era renders gracefully ("No memories yet for this era") — no broken DOM
- Photo lightbox opens on thumbnail click (reuses existing lightbox if present)

**Phase C passes when:**

- `data/timeline_context_events/sample_pack.json` loads cleanly
- Renderer surfaces sample events on Janice's timeline at the right years (e.g., 1944 birth, 1957 prairie drought, 1969 moon landing if globally tagged, etc.)
- Operators can see "this is a sample pack — replace with curated regional pack from WO-TIMELINE-CONTEXT-EVENTS-01" notice somewhere in the dev surface

---

## Risks & rollback

**Risk 1: era_id derivation drift.** If `lv_eras.year_to_era_id()` disagrees with `state.js _canonicalEra()` or other call sites, items land in wrong eras. Mitigation: add a parity test (`tests/test_lv_eras_parity.py`) that asserts the Python helper and the JS helper produce identical era_id mappings for a fixed test set of (year, dob) tuples. This becomes the canonical regression net for future era refactors.

**Risk 2: photo date precision misuse.** A photo with `date_precision='decade'` has an ambiguous era home (e.g., 1940s photo for a 1944-born narrator could span both `earliest_years` and `early_school_years`). **v1 rule (locked): never silently midpoint.** The item renders inside whichever era contains the midpoint of the narrator's overlap with that decade — but the rendered string preserves uncertainty as `~1940s` / `circa 1950s` / `early 1960s`. The narrator sees an approximate decade, never an invented exact year. Operators can refine to year/month/exact precision if they have evidence; the renderer never guesses on their behalf.

**Risk 3: BB-state firstName=None blocking timeline render.** Per the v6 audit memo, BB state mirror is missing. Timeline render reads canonical truth from `profiles.profile_json` directly (NOT from `state.bioBuilder`), so this risk does NOT apply to the timeline. Document explicitly in the render code comment that timeline does NOT consume BB-state surfaces. This is intentional — the timeline is the source-of-truth render, not a UI-mirror render.

**Rollback:** flip `HORNELORE_TIMELINE_RENDER_V1=0`. Endpoint 404s. Frontend module gracefully handles 404 (renders "Timeline not available" placeholder). Zero impact on interview / extractor / Lori-behavior lanes when disabled.

---

## Files (planned)

**New:**

- `server/code/api/routers/timeline.py`
- `server/code/api/services/timeline_render.py`
- `tests/test_timeline_render.py`
- `tests/test_timeline_render_isolation.py`
- `tests/test_lv_eras_parity.py` (Risk 1 mitigation)
- `ui/js/timeline-render.js`
- `ui/css/timeline.css`
- `data/timeline_context_events/sample_pack.json` (Phase C)

**Modified:**

- `server/code/api/main.py` (router include)
- `server/code/api/lv_eras.py` (add `year_to_era_id(year, dob_year)` helper)
- `ui/js/lv-eras.js` (add matching JS helper)
- `ui/hornelore1.0.html` (mount point + script tag)
- `.env.example` (`HORNELORE_TIMELINE_RENDER_V1=0` documentation block)
- `MASTER_WORK_ORDER_CHECKLIST.md` (add timeline lane row)

**Zero touch:**

- Extract router (`server/code/api/routers/extract.py`)
- Prompt composer (`server/code/api/prompt_composer.py`)
- Lori behavior (`lori_*.py`)
- Memory echo composer
- Chat WebSocket router
- Story trigger / preservation services

---

## Sequencing within the lane

1. **Sprint 1 (this lane's first session):** Phase A backend endpoint + tests + isolation gate. Stack restart not required to test (endpoint behind flag). ~half a session.
2. **Sprint 2:** Phase C sample pack + frontend Phase B render against sample data. ~one session.
3. **Sprint 3 (after WO-TIMELINE-CONTEXT-EVENTS-01 ships first real pack):** swap sample pack for curated table read; add the mini-map / cluster collapse polish if needed.

Phase D items (density bands, scrub bar) are explicitly deferred to a successor WO once the v1 render has narrator + operator eyeballs on it.

---

## Locked principles (do not relitigate)

1. **Lori does not write to the timeline.** Not even via an operator-approval queue. World events come from operator-curated research only (per WO-TIMELINE-CONTEXT-EVENTS-01). Narrator-truth pins come from canonical DB rows or promoted story_candidates.

2. **Stored, not retrieved.** No LLM generation at render time. No web fetch at render time. The timeline is a read-only projection of stored memory artifacts. Render-time is pure DB read.

3. **Era derivation is render-time, not authoring-time.** Source rows never gain era_id columns. The same row could land in different eras for different narrators if the row is shared (it isn't currently — each narrator's data is private — but the discipline matters).

4. **Approximate memories remain approximate.** A `1950s` photo renders as "circa 1950s," never as "1955." The renderer never invents precision the source row doesn't carry. This is the most common silent-failure mode for timeline UIs and the rule that prevents it.

5. **The timeline is read-only in v1.** Editing / re-dating / promoting / discarding happens on existing operator review surfaces. Adding edit affordances to the timeline is its own future WO and must be scoped carefully against the "Lori does not write" wall.

6. **The timeline embeds in memoir export, not the other way around.** Memoir is the document; timeline is the visual layer of the document. Future memoir-export work consumes the timeline render JSON and embeds it; the timeline does NOT consume memoir prose.

7. **The timeline is cognitive scaffolding, not decorative UI.** It serves the narrator (orienting themselves during interview), the operator (seeing the work-product), and the family (inheriting the artifact). All three are load-bearing audiences. Operator metadata never leaks into narrator view.

---

## Narrator surface vs operator surface

**Narrator-visible from v1.** The timeline is cognitive scaffolding for the narrator during interview, not just an artifact for the family at the end. Narrator-facing render is the v1 target, not a deferred v2.

What the narrator sees per item:
- photo (thumbnail + caption + date qualifier if approximate)
- quote (narrator's own words, verbatim, dated to the era)
- memory (narrator-told story attached to a photo)
- world/context event (operator-curated regional or global pin, rendered as italic background context)
- chronological progression across the 7 eras + Undated section

What the operator additionally sees (toggleable, not narrator-visible):
- citations (full `source_citation` from timeline_context_events; `source_kind` for photo/quote/memory rows)
- provenance (`uploaded_by_user_id`, `last_edited_by_user_id`, `uploaded_at` for photos; `review_status` and `reviewed_by` for promoted story_candidates)
- debug metadata (raw row IDs, era-assignment derivation steps, alt-era candidates if a decade overlaps two eras)
- source rows (the actual JSON payload from the underlying DB row, expandable)
- confidence detail (the underlying `confidence` enum value before render-time mapping)

The toggle defaults to OFF (narrator view). Operator flips it via a small operator-only control elsewhere in the surface (Bug Panel, settings, or a hidden hotkey). Operator metadata never leaks into narrator view, ever.

## Open questions for next session

- Where does the timeline mount in narrator-room? New tab, subordinate to Life Map? Behind a popover from the existing chronology accordion? Defer until Phase B implementation has eyes on the existing narrator-room layout.
- Operator-toggle UI shape — Bug Panel section, settings dropdown, or a key combo? Defer until Phase B implementation lands and we see how operators actually want to switch views.

---

## Changelog

- 2026-05-05: Spec authored after the timeline-vs-Life-Map architectural conversation. Builds on the 2026-05-01 Memory River retirement and the 2026-05-03 voice-library + cultural-humility groundwork. Pulls forward the HorneHX/Lifeline architectural pattern (mechanical render from DB + photos + curated context) without rebuilding the PHP codebase. Pair WO authored same day: WO-TIMELINE-CONTEXT-EVENTS-01.
