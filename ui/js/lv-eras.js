/* ─────────────────────────────────────────────────────────────────────
   Lorevox Canonical Life Spine — single source of truth for life-period
   taxonomy across Timeline, Life Map, Peek at Memoir, Lori's prompts,
   and TXT/DOCX export.

   IMPORTANT: This file uses IIFE / window.LorevoxEras pattern, NOT ES
   modules. The hornelore1.0.html UI loads plain scripts, not type=module.
   Existing files (life-map.js → window.LorevoxLifeMap) follow the same
   pattern. Adding `export const` here would break script-tag loading.

   Backend mirror: server/code/api/lv_eras.py — keep the two in sync.

   Architecture:
   - 7 buckets total: 6 historical eras + Today (separate current-life)
   - era_id      stable internal key (passed through runtime71, log lines,
                 prompts, state.session.currentEra, etc.) — NEVER prefixed
                 with "era:" or any other namespace at canonical boundary
   - label       warm display string (heading shown in UI)
   - memoirTitle literary subtitle (shown UNDER the warm heading in
                 Peek at Memoir, e.g. "Earliest Years / The Legend Begins")
   - ageStart    inclusive lower bound for historical-era lookup
   - ageEnd      inclusive upper bound; null = open-ended (Later Years)
   - loriFocus   user-facing description text shown in the Life Map click
                 confirmation popover and used in Lori's prompts to anchor
                 what's being asked about in this era
   - legacyKeys  old v7.1 era names retained as aliases only

   Today has ageStart=null, ageEnd=null and is NEVER returned by
   eraIdFromAge() — current-life is selected explicitly, not derived
   from birth-year math.

   Rationale grounded in:
   - Life Review Therapy (Butler 1963; Haight & Haight) — chronological
     spine with evaluation
   - Reminiscence Bump research — Adolescence + Coming of Age (ages
     10-30) carry disproportionate identity-formation weight
   - Dementia UK / Essex Provider Hub life-story templates — Today as a
     real bucket for current-life routines, preferences, hopes
   ───────────────────────────────────────────────────────────────────── */

(function () {
  "use strict";

  var LV_ERAS = [
    {
      era_id:      "earliest_years",
      legacyKeys:  ["early_childhood"],
      label:       "Earliest Years",
      memoirTitle: "The Legend Begins",
      ageStart:    0,
      ageEnd:      5,
      loriFocus:   "birth, first home, parents and siblings, the places that shaped early childhood",
    },
    {
      era_id:      "early_school_years",
      legacyKeys:  ["school_years"],
      label:       "Early School Years",
      memoirTitle: "Formative Years",
      ageStart:    6,
      ageEnd:      12,
      loriFocus:   "elementary school, teachers, neighborhood, family routines, early friendships",
    },
    {
      era_id:      "adolescence",
      legacyKeys:  ["adolescence"],
      label:       "Adolescence",
      memoirTitle: "Adolescence",
      ageStart:    13,
      ageEnd:      17,
      loriFocus:   "teen years, identity, friends, high school, growing independence",
    },
    {
      era_id:      "coming_of_age",
      legacyKeys:  ["early_adulthood"],
      label:       "Coming of Age",
      memoirTitle: "Crossroads",
      ageStart:    18,
      ageEnd:      30,
      loriFocus:   "leaving home, first work, marriage, moves, finding your adult self",
    },
    {
      era_id:      "building_years",
      legacyKeys:  ["midlife"],
      label:       "Building Years",
      memoirTitle: "Peaks & Valleys",
      ageStart:    31,
      ageEnd:      59,
      loriFocus:   "work, family, responsibility, caregiving, community",
    },
    {
      era_id:      "later_years",
      legacyKeys:  ["later_life"],
      label:       "Later Years",
      memoirTitle: "The Compass",
      ageStart:    60,
      ageEnd:      null,
      loriFocus:   "retirement, reflection, health, family, lessons, and what matters most now",
    },
    {
      era_id:      "today",
      legacyKeys:  ["current_horizon"],
      label:       "Today",
      memoirTitle: "Current Horizon",
      ageStart:    null,
      ageEnd:      null,
      loriFocus:   "current life, routines, the people you see most, hopes, unfinished stories",
    },
  ];

  /* ── Internal lookups ─────────────────────────────────────────── */

  function _findById(eraId) {
    if (!eraId) return null;
    var raw = String(eraId).trim();
    for (var i = 0; i < LV_ERAS.length; i++) {
      if (LV_ERAS[i].era_id === raw) return LV_ERAS[i];
    }
    return null;
  }

  function _findByLegacy(legacy) {
    if (!legacy) return null;
    var raw = String(legacy).trim();
    for (var i = 0; i < LV_ERAS.length; i++) {
      var keys = LV_ERAS[i].legacyKeys || [];
      for (var j = 0; j < keys.length; j++) {
        if (keys[j] === raw) return LV_ERAS[i];
      }
    }
    return null;
  }

  /* ── Public helpers ───────────────────────────────────────────── */

  function _slugify(s) {
    // Lowercase + replace runs of non-alphanum with single underscore +
    // strip leading/trailing underscores. Lets "Earliest-Years" /
    // "EARLIEST YEARS" / "earliest years" all collapse to "earliest_years".
    return String(s).toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
  }

  /**
   * Normalize any era identifier to canonical era_id. Defensive against
   * every transitional form we know about. Resolution order:
   *   1. trim
   *   2. strip leading "era:" prefix if present
   *   3. exact canonical era_id match  (e.g. "earliest_years")
   *   4. legacy v7.1 key match         (e.g. "early_childhood")
   *   5. warm label match              (e.g. "Earliest Years", case-insensitive)
   *   6. memoir title match            (e.g. "The Legend Begins", case-insensitive)
   *   7. normalized slug match         (e.g. "Earliest-Years" → "earliest_years")
   *   8. return cleaned input unchanged (forwards-compat for unknown
   *      values; callers wanting strict validation should check
   *      `LV_ERAS.find(e => e.era_id === result)`)
   *
   * Returns null for null/empty input.
   */
  function legacyKeyToEraId(id) {
    if (id == null) return null;
    var raw = String(id).trim();
    if (raw === "") return null;
    // Step 2: strip transitional "era:" prefix (case-insensitive — handles
    // ERA:Today, Era:Earliest Years, etc.).
    if (raw.toLowerCase().indexOf("era:") === 0) raw = raw.slice(4).trim();
    if (raw === "") return null;
    // Step 3: canonical era_id direct.
    var direct = _findById(raw);
    if (direct) return direct.era_id;
    // Step 4: legacy v7.1 key.
    var legacy = _findByLegacy(raw);
    if (legacy) return legacy.era_id;
    // Step 5: warm label (case-insensitive).
    var rawLower = raw.toLowerCase();
    for (var i = 0; i < LV_ERAS.length; i++) {
      if (LV_ERAS[i].label.toLowerCase() === rawLower) return LV_ERAS[i].era_id;
    }
    // Step 6: memoir title (case-insensitive).
    for (var k = 0; k < LV_ERAS.length; k++) {
      var mt = LV_ERAS[k].memoirTitle;
      if (mt && mt.toLowerCase() === rawLower) return LV_ERAS[k].era_id;
    }
    // Step 7: slug match (handles "Earliest-Years", "EARLIEST YEARS", etc.).
    var slug = _slugify(raw);
    if (slug) {
      var slugDirect = _findById(slug);
      if (slugDirect) return slugDirect.era_id;
      var slugLegacy = _findByLegacy(slug);
      if (slugLegacy) return slugLegacy.era_id;
    }
    // Step 8: forwards-compat passthrough.
    return raw;
  }

  function eraIdToWarmLabel(id) {
    var eraId = legacyKeyToEraId(id);
    var era = _findById(eraId);
    return era ? era.label : (id ? String(id) : "");
  }

  function eraIdToMemoirTitle(id) {
    var eraId = legacyKeyToEraId(id);
    var era = _findById(eraId);
    return era ? era.memoirTitle : "";
  }

  function eraIdToLoriFocus(id) {
    var eraId = legacyKeyToEraId(id);
    var era = _findById(eraId);
    return era ? era.loriFocus : "";
  }

  /**
   * Map age in years to a canonical era_id.
   * IMPORTANT: never returns "today" — Today is a current-life bucket
   * selected explicitly, not derived from birth-year math.
   */
  function eraIdFromAge(age) {
    if (age == null) return null;
    var n = Number(age);
    if (!isFinite(n)) return null;
    for (var i = 0; i < LV_ERAS.length; i++) {
      var e = LV_ERAS[i];
      if (e.era_id === "today") continue;          // never derive today from age
      if (e.ageStart == null) continue;            // defensive — non-historical entries skipped
      if (e.ageEnd == null) {
        if (n >= e.ageStart) return e.era_id;
      } else {
        if (n >= e.ageStart && n <= e.ageEnd) return e.era_id;
      }
    }
    return null;
  }

  /**
   * Map a calendar year + DOB to a canonical era_id.
   * Year is the year being asked about; dob is the narrator's birth
   * date (any string/Date with a YYYY in it). Returns null if either
   * is missing or non-parseable. Like eraIdFromAge, never returns today.
   */
  function eraIdFromYear(year, dob) {
    var birthYear = null;
    if (dob != null) {
      var m = String(dob).match(/\b(18|19|20)\d{2}\b/);
      if (m) birthYear = parseInt(m[0], 10);
    }
    var yearN = Number(year);
    if (!birthYear || !isFinite(yearN)) return null;
    return eraIdFromAge(yearN - birthYear);
  }

  /** Return a shallow copy of LV_ERAS for safe iteration. */
  function allEras() {
    return LV_ERAS.slice();
  }

  /* ── Expose as window.LorevoxEras (matches life-map.js pattern) ── */

  window.LorevoxEras = {
    LV_ERAS:             LV_ERAS,
    legacyKeyToEraId:    legacyKeyToEraId,
    eraIdToWarmLabel:    eraIdToWarmLabel,
    eraIdToMemoirTitle:  eraIdToMemoirTitle,
    eraIdToLoriFocus:    eraIdToLoriFocus,
    eraIdFromAge:        eraIdFromAge,
    eraIdFromYear:       eraIdFromYear,
    allEras:             allEras,
  };
})();
