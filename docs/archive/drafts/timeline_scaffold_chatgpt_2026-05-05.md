# Timeline Context Render Foundation Scaffold — ChatGPT, 2026-05-05

> **Status:** REFERENCE ONLY — design notes, NOT paste-ready.
>
> This scaffold was authored by ChatGPT during the timeline lane design conversation
> on 2026-05-05. It is preserved here as a record of the architectural shape that
> emerged from the conversation, NOT as an implementation guide.
>
> **Phase A implementation must come from the spec** (`WO-TIMELINE-RENDER-01_Spec.md`
> + `WO-TIMELINE-CONTEXT-EVENTS-01_Spec.md`), not from this file. The scaffold has
> bugs that would break on first run if pasted as-is — see "Known issues" at the
> bottom of this file.
>
> The scaffold's value is the architectural shape (separation of concerns, era
> assignment, narrator-aware filtering, JSON pack format, frontend accordion
> render). Future implementers should read this for context but build from the
> spec + the existing repo patterns (lv_eras.py, db.py `_connect()`, the
> photos-migration BEGIN/COMMIT pattern, the story_preservation isolation test
> pattern).

---

## What this file is

ChatGPT's foundational implementation scaffold covering:

- SQL migration for `timeline_context_events`
- repository layer
- timeline render service
- era mapping helper
- FastAPI endpoint
- frontend accordion renderer
- CSS
- sample regional/cohort context pack
- narrator-aware filtering architecture
- stored-not-retrieved render flow

Aligned with:

- WO-TIMELINE-RENDER-01
- WO-TIMELINE-CONTEXT-EVENTS-01
- existing `lv_eras.py` architecture
- read-only render discipline
- no-LLM render path

---

## 1. Migration

`server/code/db/migrations/0005_timeline_context_events.sql`

```sql
CREATE TABLE IF NOT EXISTS timeline_context_events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    year_start INTEGER,
    year_end INTEGER,
    scope TEXT NOT NULL CHECK (scope IN (
        'global',
        'national',
        'regional',
        'local',
        'cultural'
    )),
    region_tags TEXT NOT NULL,
    heritage_tags TEXT NOT NULL,
    source_kind TEXT NOT NULL CHECK (source_kind IN (
        'local_oral_history',
        'archived_newspaper',
        'historical_society',
        'academic',
        'reference_work',
        'web_resource',
        'family_archive',
        'operator_research_note'
    )),
    source_citation TEXT NOT NULL,
    narrator_visible INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_by TEXT,
    reviewed_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_tce_year_start ON timeline_context_events(year_start);
CREATE INDEX IF NOT EXISTS idx_tce_year_end   ON timeline_context_events(year_end);
CREATE INDEX IF NOT EXISTS idx_tce_visible    ON timeline_context_events(narrator_visible, deleted_at);
```

## 2. Era Mapping Helper

`server/code/api/lv_eras.py` (proposed addition):

```python
LV_ERAS = [
    ("earliest_years", 0, 5),
    ("early_school_years", 6, 12),
    ("adolescence", 13, 18),
    ("coming_of_age", 19, 30),
    ("building_years", 31, 60),
    ("later_years", 61, 200),
]

def year_to_era_id(year: int, birth_year: int) -> str:
    age = year - birth_year
    for era_id, low, high in LV_ERAS:
        if low <= age <= high:
            return era_id
    return "today"
```

## 3. Repository Layer

`server/code/api/services/timeline_context_events_repository.py`:

```python
import json
from api.db import get_db_connection

class TimelineContextEventRepository:
    def query_events_for_narrator(
        self,
        *,
        narrator_birth_year: int,
        narrator_current_year: int,
        narrator_region_tags: list[str],
        narrator_heritage_tags: list[str],
    ):
        conn = get_db_connection()
        rows = conn.execute(
            """
            SELECT *
            FROM timeline_context_events
            WHERE deleted_at IS NULL
              AND narrator_visible = 1
              AND year_start <= ?
              AND year_end >= ?
            ORDER BY year_start ASC
            """,
            (
                narrator_current_year,
                narrator_birth_year,
            ),
        ).fetchall()

        matched = []
        for row in rows:
            region_tags = json.loads(row["region_tags"])
            heritage_tags = json.loads(row["heritage_tags"])
            region_match = any(
                tag in narrator_region_tags
                for tag in region_tags
            )
            heritage_match = any(
                tag in narrator_heritage_tags
                for tag in heritage_tags
            )
            if (
                row["scope"] in ("global", "national")
                or region_match
                or heritage_match
            ):
                matched.append(dict(row))
        return matched
```

## 4. Timeline Render Service

`server/code/api/services/timeline_render.py`:

```python
from collections import defaultdict
from api.lv_eras import year_to_era_id
from api.services.timeline_context_events_repository import (
    TimelineContextEventRepository,
)

class TimelineRenderService:
    def __init__(self):
        self.events_repo = TimelineContextEventRepository()

    def build_timeline(
        self,
        *,
        narrator_id: str,
        narrator_birth_year: int,
        narrator_region_tags: list[str],
        narrator_heritage_tags: list[str],
        narrator_current_year: int,
    ):
        eras = defaultdict(list)
        events = self.events_repo.query_events_for_narrator(
            narrator_birth_year=narrator_birth_year,
            narrator_current_year=narrator_current_year,
            narrator_region_tags=narrator_region_tags,
            narrator_heritage_tags=narrator_heritage_tags,
        )

        for event in events:
            year = event["year_start"]
            era_id = year_to_era_id(
                year,
                narrator_birth_year,
            )
            eras[era_id].append({
                "kind": "event",
                "title": event["title"],
                "summary": event["summary"],
                "year_start": event["year_start"],
                "year_end": event["year_end"],
                "scope": event["scope"],
                "source_citation": event["source_citation"],
            })

        return {
            "narrator_id": narrator_id,
            "eras": eras,
        }
```

## 5. FastAPI Router

`server/code/api/routers/timeline.py`:

```python
from fastapi import APIRouter
from api.services.timeline_render import TimelineRenderService

router = APIRouter()
service = TimelineRenderService()

@router.get("/api/narrator/{narrator_id}/timeline")
def get_timeline(narrator_id: str):
    # Placeholder.
    # Replace with real narrator/profile lookup.
    narrator_birth_year = 1939
    narrator_region_tags = [
        "north_dakota",
        "great_plains",
    ]
    narrator_heritage_tags = [
        "germans_from_russia",
        "rural_us",
    ]
    narrator_current_year = 2026

    result = service.build_timeline(
        narrator_id=narrator_id,
        narrator_birth_year=narrator_birth_year,
        narrator_region_tags=narrator_region_tags,
        narrator_heritage_tags=narrator_heritage_tags,
        narrator_current_year=narrator_current_year,
    )
    return result
```

## 6. Register Router

`server/code/api/main.py`:

```python
from api.routers.timeline import router as timeline_router
app.include_router(timeline_router)
```

## 7. Frontend Accordion Renderer

`ui/js/timeline-render.js`:

```javascript
(function () {
    async function loadTimeline(narratorId) {
        const response = await fetch(
            `/api/narrator/${narratorId}/timeline`
        );
        const data = await response.json();
        renderTimeline(data);
    }

    function renderTimeline(data) {
        const root = document.getElementById("timeline-root");
        root.innerHTML = "";
        Object.entries(data.eras).forEach(([eraId, items]) => {
            const section = document.createElement("div");
            section.className = "timeline-era";

            const header = document.createElement("button");
            header.className = "timeline-era-header";
            header.innerText = prettifyEra(eraId);

            const body = document.createElement("div");
            body.className = "timeline-era-body";

            items.forEach(item => {
                const card = document.createElement("div");
                card.className = "timeline-card";
                card.innerHTML = `
                    <div class="timeline-year">
                        ${item.year_start}
                    </div>
                    <div class="timeline-title">
                        ${item.title}
                    </div>
                    <div class="timeline-summary">
                        ${item.summary}
                    </div>
                `;
                body.appendChild(card);
            });

            header.addEventListener("click", () => {
                body.classList.toggle("open");
            });

            section.appendChild(header);
            section.appendChild(body);
            root.appendChild(section);
        });
    }

    function prettifyEra(eraId) {
        return eraId
            .split("_")
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join(" ");
    }

    window.LVTimeline = {
        loadTimeline,
    };
})();
```

## 8. Timeline CSS

`ui/css/timeline.css`:

```css
.timeline-era {
    border: 1px solid #444;
    border-radius: 8px;
    margin-bottom: 12px;
    overflow: hidden;
}

.timeline-era-header {
    width: 100%;
    padding: 14px;
    background: #1f1f1f;
    color: white;
    border: none;
    text-align: left;
    font-size: 18px;
    cursor: pointer;
}

.timeline-era-body {
    display: none;
    padding: 12px;
    background: #2b2b2b;
}

.timeline-era-body.open {
    display: block;
}

.timeline-card {
    border-left: 3px solid #888;
    padding-left: 12px;
    margin-bottom: 18px;
}

.timeline-year {
    font-weight: bold;
    margin-bottom: 6px;
}

.timeline-title {
    font-size: 16px;
    margin-bottom: 4px;
}

.timeline-summary {
    opacity: 0.9;
    line-height: 1.4;
}
```

## 9. Narrator Mount Point

`ui/hornelore1.0.html`:

```html
<link rel="stylesheet" href="ui/css/timeline.css">
<script src="ui/js/timeline-render.js"></script>

<div id="timeline-root"></div>

<script>
    LVTimeline.loadTimeline("janice");
</script>
```

## 10. Sample Context Pack

`data/timeline_context_events/janice_germans_from_russia_nd_prairie.json`:

```json
[
    {
        "id": "nd_1954_drought",
        "title": "North Dakota drought years",
        "summary": "Extended drought conditions affected prairie farming communities across North Dakota and the Great Plains.",
        "year_start": 1954,
        "year_end": 1957,
        "scope": "regional",
        "region_tags": [
            "north_dakota",
            "great_plains"
        ],
        "heritage_tags": [
            "germans_from_russia",
            "rural_us"
        ],
        "source_kind": "historical_society",
        "source_citation": "North Dakota Historical Society Prairie Climate Archive, 2018",
        "created_by": "operator_chris"
    },
    {
        "id": "nd_1953_grain_elevator_fire",
        "title": "Stanley grain elevator fire",
        "summary": "A major grain elevator fire disrupted local agricultural operations and became a remembered community event.",
        "year_start": 1953,
        "year_end": 1953,
        "scope": "local",
        "region_tags": [
            "north_dakota",
            "stanley_nd"
        ],
        "heritage_tags": [
            "germans_from_russia",
            "rural_us"
        ],
        "source_kind": "archived_newspaper",
        "source_citation": "Stanley Sun newspaper archive, 1953-08-14",
        "created_by": "operator_chris"
    }
]
```

## 11. Why This Architecture Matters

This architecture:

- removes historical-context pressure from Lori
- grounds memory in stored structured context
- reduces hallucination
- creates narrator-visible cognitive scaffolding
- supports family inheritance artifacts
- separates conversation from chronology

The timeline becomes the visible artifact of memory while Lori becomes the conversational companion beside it instead of trying to generate the entire historical structure dynamically.

---

## Known issues with this scaffold (audit 2026-05-05)

The scaffold above does not match the existing repo and would break on first run if pasted as-is. Phase A implementation must come from the spec, not this scaffold. The audit below is preserved so future implementers don't repeat these mistakes.

### Bugs that break before any test passes

**1. `LV_ERAS` redefinition collides with existing canonical registry.** `server/code/api/lv_eras.py` already defines `LV_ERAS` as a list of dicts with `era_id` / `label` / `memoirTitle` / `ageStart` / `ageEnd` / `loriFocus` / `legacyKeys`. The scaffold's tuple-based `LV_ERAS = [(era_id, age_low, age_high), ...]` would replace that and break every importer (prompt_composer, chronology_accordion, extract.py, life_spine/engine.py — listed at top of the existing module). **Don't add LV_ERAS.** Use the existing module.

**2. Wrong age boundaries in 4 of 6 eras.** Scaffold: `adolescence: 13-18`, `coming_of_age: 19-30`, `building_years: 31-60`, `later_years: 61-200`. Canonical (`lv_eras.py:43-107`): `adolescence: 13-17`, `coming_of_age: 18-30`, `building_years: 31-59`, `later_years: 60-None`. A 60-year-old lands in `later_years` per canonical and `building_years` per scaffold — real classification error.

**3. `year_to_era_id` is redundant — the helper already exists.** `lv_eras.py:233` defines `era_id_from_year(year, dob)` with the exact signature the scaffold wants. **Replace `from api.lv_eras import year_to_era_id` with `from api.lv_eras import era_id_from_year`** and adjust callers. The existing function never returns `"today"` (today is current-life, not derived from age) — scaffold's `"today"` fallback for out-of-range ages is wrong.

**4. `from api.db import get_db_connection` does not exist.** `db.py:54` defines `_connect()` (private, underscore-prefixed). Import path must be relative — per the chat_ws import-fix landing 2026-04-27, the canonical pattern is `from ..db` for code inside `server/code/api/services/`. Replace with:

```python
from ..db import _connect

# inside repository method:
conn = _connect()
try:
    rows = conn.execute("...", params).fetchall()
finally:
    conn.close()
```

Following the rollback-hygiene pattern from BUG-DBLOCK-01 (try/finally close).

### Spec violations

**5. No `HORNELORE_TIMELINE_RENDER_V1=0` flag check.** Endpoint must 404 when flag is off (per spec north-star). Add at top of router:
```python
import os
from fastapi import HTTPException
if os.environ.get("HORNELORE_TIMELINE_RENDER_V1") != "1":
    raise HTTPException(status_code=404)
```

**6. No build-gate isolation tests.** Spec calls for `tests/test_timeline_context_events_isolation.py` AND `tests/test_timeline_render_isolation.py` per LAW 3 INFRASTRUCTURE pattern from `test_story_preservation_isolation.py`. Without these, the architectural wall (no extractor / Lori imports) is enforced only by convention.

**7. No unit tests at all.** Spec requires `tests/test_timeline_render.py` and `tests/test_timeline_context_events_repository.py`. Acceptance gates can't be verified without them.

**8. No validator + seed loader + tag vocabulary.** Spec's Phase B is missing entirely — `scripts/validate_timeline_context_events.py`, `scripts/seed_timeline_context_events.py`, `data/timeline_context_events/tag_vocabulary.json`. The sample pack will load via raw SQL inserts but won't pass schema/tag-vocabulary validation.

**9. JSON pack missing `pack_kind` annotation.** Spec says each pack file carries `pack_kind: "private_family" | "shared_regional"` at top level so the validator applies stricter rules to shared_regional. Wrap as `{ "pack_kind": "private_family", "events": [ ... ] }`.

### Code quality issues

**10. `innerHTML` interpolation is an XSS pattern.** Even with operator-curated content, this is a bad habit. A title containing `<script>` or even `<` breaks rendering. Replace with `textContent` per element:

```javascript
const yearEl = document.createElement("div");
yearEl.className = "timeline-year";
yearEl.textContent = item.year_start;
```

More verbose but defensive.

**11. Empty-era handling.** Scaffold returns `defaultdict(list)` and only emits eras that have items. Spec says all 7 canonical eras render with empty `items` arrays so the narrator sees "Adolescence — no memories yet for this era" rather than a missing section. Iterate through `lv_eras.LV_ERAS` and seed each era key.

**12. Migration missing `BEGIN; ... COMMIT;` wrap.** Photos migration `0001_lori_photo_shared.sql` wraps with BEGIN/COMMIT for atomicity. Match the pattern.

**13. Router placeholder narrator data will silently ship if TODO doesn't get replaced.** Make it a hard blocker (`raise NotImplementedError`) until the real profile lookup wires through.

**14. Frontend hardcoded `LVTimeline.loadTimeline("janice")`.** Same comment — placeholder needs an explicit TODO and a real wire to `state.person_id` from the existing app state.

### Coverage gaps (acceptable as "phase 1 of Phase A" scope, but explicit scoping helps)

**15. Render service handles only events.** Spec returns 5 item kinds (`fact` / `quote` / `photo` / `memory` / `event`). Scaffold has only events. Document as deliberate first-cut scope or ship the other kinds in subsequent Phase A commits.

**16. No operator-citation-toggle UI logic.** Scaffold renders the same view to all users. Spec has narrator view (no citations / provenance) vs operator view (additionally sees citations / provenance / debug). Acceptable for first-cut as long as `source_citation` is NOT visible in the narrator view (scaffold doesn't render it at all, so accidentally OK).

---

## Recommendation

Do NOT paste this scaffold. Treat it as design notes capturing the architectural shape. Phase A implementation should:

1. Read the spec (`WO-TIMELINE-RENDER-01_Spec.md` + `WO-TIMELINE-CONTEXT-EVENTS-01_Spec.md`)
2. Use existing repo patterns (`lv_eras.era_id_from_year` / `db._connect()` / story-preservation isolation test / photos-migration BEGIN/COMMIT)
3. Build the test infrastructure first (isolation gate + unit tests) so the architectural walls stay enforced
4. Wire the env flag check into the router from line 1
5. Then build the repository + render service + frontend accordion in that order, against the test pack

Sprint 1 timing stays at ~half a session per WO; the time-savings of pasting this scaffold are illusory because the four breakage bugs would consume more time fixing than building from spec.
