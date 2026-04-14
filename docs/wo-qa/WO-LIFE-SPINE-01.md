# WO-LIFE-SPINE-01 — DOB-derived life-phase projection (school catalog v1)

**Status:** Complete (school catalog only; framework ready for additional eras)
**Owner area:** `server/code/api/life_spine/`, `server/code/api/routers/chronology_accordion.py`, `ui/hornelore1.0.html`

---

## What this WO does

Adds a generic life-spine derivation engine to Hornelore. From a narrator's
DOB (and optional confirmed events), the engine produces probabilistic
life-phase anchors that render as ghost entries in the **existing** Chronology
Accordion. No new timeline view, no canonical-truth writes, no parallel
rendering surface.

This WO ships **only the school catalog** (kindergarten → HS graduation).
The engine is structured so future catalogs (adolescence, early_adulthood,
midlife, later_life, family) plug in by adding one file and registering it
in `engine.py`'s `CATALOGS` dict. Per the corrected execution path, ship
school first, see it in the UI, then expand.

## Why this exists

Two motivations from upstream conversation:

1. **Structural answer to the WO-EX-01 extraction bug.** Chris's School-Years
   statement *"we lived in west Fargo in a trailer court"* proposed
   `personal.placeOfBirth = west Fargo`. WO-EX-01 stops the immediate
   bleeding (regex tightening + era guard). The structural fix is giving
   the extractor a model of *where the narrator is in their own life at
   the moment they speak* — that's what this spine is for. With the spine
   in place, future WOs can pass `current_phase` to the extractor so a
   "lived in [place]" statement during 1968 (kindergarten phase) routes to
   `residence.school_years` instead of `personal.placeOfBirth`.

2. **Chronological intelligence as a product capability.** Lori currently
   asks generically. With phase awareness, prompts become specific to the
   narrator's age window, which is what the WO-QA-02 results predicted
   would lower suppression. That integration is a future WO; this WO ships
   the data layer it depends on.

## Architecture

Generic engine + pluggable per-era catalogs. Same authority contract as
the rest of the Chronology Accordion: projection layer, never canonical
truth, dedup against promoted facts.

```
server/code/api/life_spine/
  __init__.py        — public API: derive_life_spine(dob, confirmed_events=None)
  engine.py          — dispatcher + CATALOGS registry + override application
  school.py          — first concrete catalog (this WO)
  overrides.py       — generic offset propagation (downstream-only, confirmed-locked)
```

## The school catalog — Dec-birthday correction

The single most-reported mistake of naive school-spine implementations is
using `dob.year + 5` for kindergarten. That's wrong for Sept–Dec birthdays
in the US. `school.py:kindergarten_start_year` does the correct math:

```python
def kindergarten_start_year(dob):
    if dob.month >= 9:
        return dob.year + 6
    return dob.year + 5
```

Validated against real DOBs:

| Narrator | DOB | Naive `+5` | Corrected | Real grad | Spine grad |
|---|---|---|---|---|---|
| Chris | 1962-12-24 | K=1967, grad=1980 | **K=1968, grad=1981** | 1981 | **1981** ✓ |
| Janice | 1939-08-30 | K=1944, grad=1957 | K=1944, grad=1957 | (n/a) | 1957 |
| Kent | 1939-12-24 | K=1944, grad=1957 | **K=1945, grad=1958** | (n/a) | 1958 |

The naive rule would have shown Chris's graduation a year early on day one
of using the feature, eroding trust before the spine had a chance to earn it.

## Catalog output shape

Each catalog returns `List[ChronologyItem]` ready to merge into Lane B:

```python
{
    "year": 1968,
    "label": "Started kindergarten (estimated)",
    "lane": "personal",
    "event_kind": "school_kindergarten",       # stable id for dedup + override
    "dedup_key": "school_kindergarten:self",   # accordion dedup compatibility
    "source": "derived",                        # provenance — UI renders ghost
    "confidence": "estimated",                  # flips to "confirmed" on override
}
```

The school catalog produces 5 entries: kindergarten start, 1st grade
(elementary begins), 6th grade (middle), 9th grade (high school), and
HS graduation. Intentionally sparse — one anchor per school phase, not
one per year — so the accordion stays readable.

## Override propagation (the critical part)

`overrides.apply_overrides(spine, confirmed_events)` shifts spine entries
when a narrator confirms an event. Two guards make it safe:

1. **Confirmed entries are locked.** If a spine entry already has
   `confidence != 'estimated'` (because a previous override or a promoted
   truth row anchored it), no later override can shift it.
2. **Propagation is downstream-only.** When confirming event X moves it
   by offset N, only entries whose original year was *later than X's
   original year* shift. Earlier estimates are independent — confirming
   "graduation was 1982" does NOT retroactively rewrite when kindergarten
   started.

Validated:

```
Chris confirmed school_graduation = 1981  → offset 0, only the anchor
                                              flips to confirmed.

Chris confirmed school_graduation = 1982  → offset +1, ONLY graduation
                                              moves to 1982. Earlier
                                              estimates (K=1968 etc.) stay
                                              put.

Chris confirmed school_kindergarten = 1969  → offset +1, downstream
                                                estimates (1st grade,
                                                middle, HS, graduation)
                                                ALL shift by +1.
```

## Accordion integration (`chronology_accordion.py`)

Three small additions in `build_chronology_accordion_payload`:

1. **Build a `confirmed_events` list** from existing Lane B items whose
   `event_kind` could anchor a spine entry. This means promoted-truth and
   profile entries naturally serve as override anchors with no extra wiring.
2. **Call `derive_life_spine(dob, confirmed_events=...)`** to get the
   spine items.
3. **Dedup against existing Lane B `event_kind`s** before merging — a
   spine item is dropped if a real entry of the same kind already exists.
   This means a promoted `school_graduation` row replaces (rather than
   ghosts alongside) the derived estimate.

The `lane_counts` payload field gains a `personal_derived` count so the
operator can see at a glance how many ghost entries the spine contributed.

## UI rendering (`hornelore1.0.html` CSS)

One new CSS rule in the existing `cr-event` style block:

```css
.cr-event[data-lane="personal"][data-source="derived"] {
  border-left: 3px dashed rgba(34,197,94,0.55);
  background: rgba(34,197,94,0.05);
  color: rgba(187,247,208,0.78);
  opacity: 0.78;
  font-weight: 500;
  font-style: italic;
}
```

Dashed left border, italic, lower opacity than promoted/profile/questionnaire
items — operator-readable as "this is an estimate, not a fact." Hover
lifts opacity to 0.95 for inspection. No JS or HTML changes — the existing
accordion render path already emits `data-source` per item.

## Live verification (against real DB)

Ran end-to-end against Chris's profile in the live database
(`/mnt/c/hornelore_data/db/hornelore.sqlite3`):

```
Chris basics: dob=1962-12-24  pob=Williston, North Dakota

Lane counts: {'world': 0, 'personal': 6, 'personal_derived': 5, 'ghost': 5}

Personal items in decades 1960s/70s/80s:
  [1962] src=profile  kind=birth                       Born — Williston, North Dakota
  [1968] src=derived  kind=school_kindergarten         Started kindergarten (estimated)
  [1969] src=derived  kind=school_elementary_start     1st grade — elementary begins (estimated)
  [1974] src=derived  kind=school_middle_start         Middle school begins (estimated)
  [1977] src=derived  kind=school_highschool_start     High school begins (estimated)
  [1981] src=derived  kind=school_graduation           High school graduation (estimated)
```

Birth anchor preserved (source=profile, real fact). Five spine entries
appended at correct years. **Graduation in 1981 matches Chris's actual
real-life year.**

## What this WO does NOT do

Per the corrected execution path (ship → observe → refine):

- ❌ No new era catalogs (adolescence, midlife, later_life, family) — those
  are WO-LIFE-SPINE-02 / 03 after this lands and gets observed in real use
- ❌ No extractor wiring of `current_phase` — would naturally be a follow-up
  WO once the spine is shipping data
- ❌ No prompt-composer wiring — Lori still asks generically. Phase-aware
  prompt selection is its own future WO measurable via WO-QA-02 suppression
- ❌ No relationship/career/geography catalogs — those need extractor
  patterns to populate `facts.*` first; punted
- ❌ No new timeline renderer — by design. The accordion is the canonical view

## Acceptance test (manual)

After deploying:

1. Open the Chronology Accordion for Chris in the UI
2. Expand the 1960s decade
3. **Expected:** 1962 shows "Born — Williston, North Dakota" in solid green
   (existing profile anchor, unchanged). 1968 shows "Started kindergarten
   (estimated)" in dashed-italic ghost style.
4. Expand 1970s and 1980s
5. **Expected:** dashed-italic ghost entries at 1969, 1974, 1977, 1981
6. **Expected:** 1981 reads "High school graduation (estimated)"

Counter-test (override):

1. Promote a `school_graduation` truth row for Chris with year 1981 (matches
   the estimate)
2. Refresh the accordion
3. **Expected:** the 1981 entry now renders as solid promoted-truth styling
   (the spine entry is deduped against the promoted row)

## Follow-up WOs (not in scope)

- **WO-LIFE-SPINE-02** — adolescence + early_adulthood catalogs (driver's
  license, voting age, college estimate). Only legal/societal anchors;
  drop vague entries like "midlife transition."
- **WO-LIFE-SPINE-03** — midlife + later_life with REAL anchors only
  (Medicare 65, Social Security 62/67, retirement window).
- **WO-LIFE-SPINE-04** — extractor receives `current_phase` from spine via
  `/api/extract-fields` request body. Birth-related extractions skipped
  outside `pre_school` / `elementary` early phase. Structural answer
  to the class of bug WO-EX-01 patched tactically.
- **WO-LIFE-SPINE-05** — Lori's prompt composer reads `current_phase` and
  selects from phase-specific question banks. Validate the suppression
  reduction with a fresh WO-QA-02 matrix run.
