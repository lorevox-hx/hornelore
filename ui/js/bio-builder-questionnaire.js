/* ═══════════════════════════════════════════════════════════════
   bio-builder-questionnaire.js — Structured questionnaire intake
   Lorevox 9.0 — Phase 2 module split

   Owns:
     - SECTIONS definitions and option constants
     - questionnaire section rendering
     - repeatable entry handling
     - save / load logic
     - profile → questionnaire hydration
     - normalization helpers (DOB, time, place, zodiac)
     - canonical basics builder
     - questionnaire → candidate extraction

   Depends on:
     - bio-builder-core.js (_bb, _el, _uid, _esc, _currentPersonId,
       _currentPersonName, _persistDrafts, _hasAnyValue, _emptyStateHtml,
       _registerPostSwitchHook)

   Exposes: window.LorevoxBioBuilderModules.questionnaire
   Load order: after bio-builder-core.js, before bio-builder.js
═══════════════════════════════════════════════════════════════ */

(function () {
  "use strict";

  var _core = window.LorevoxBioBuilderModules && window.LorevoxBioBuilderModules.core;
  if (!_core) throw new Error("bio-builder-core.js must load before bio-builder-questionnaire.js");

  // Pull core aliases
  var _bb                  = _core._bb;
  var _el                  = _core._el;
  var _uid                 = _core._uid;
  var _esc                 = _core._esc;
  var _currentPersonId     = _core._currentPersonId;
  var _currentPersonName   = _core._currentPersonName;
  var _persistDrafts       = _core._persistDrafts;
  var _hasAnyValue         = _core._hasAnyValue;
  var _emptyStateHtml      = _core._emptyStateHtml;
  var _restoreQuestionnaire = _core._restoreQuestionnaire;
  var _qqDebugSnapshot     = _core._qqDebugSnapshot;

  /* ───────────────────────────────────────────────────────────
     OPTION CONSTANTS
  ─────────────────────────────────────────────────────────── */

  var ZODIAC_OPTIONS = [
    "", "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
  ];

  var BIRTH_ORDER_OPTIONS = [
    "", "First child", "Second child", "Third child", "Fourth child",
    "Fifth child", "Sixth child", "Seventh child", "Eighth child",
    "Ninth child", "Tenth child", "Only child", "Twin", "Triplet", "Other/custom"
  ];

  var RELATION_OPTIONS = [
    "", "Mother", "Father", "Stepmother", "Stepfather",
    "Adoptive mother", "Adoptive father", "Guardian",
    "Grandmother", "Grandfather", "Other"
  ];

  var SIBLING_RELATION_OPTIONS = [
    "", "Sister", "Brother", "Half-sister", "Half-brother",
    "Stepsister", "Stepbrother", "Adoptive sister", "Adoptive brother", "Other"
  ];

  var CHILD_RELATION_OPTIONS = [
    "", "Son", "Daughter", "Stepson", "Stepdaughter",
    "Adoptive son", "Adoptive daughter", "Foster child", "Other"
  ];

  /* ───────────────────────────────────────────────────────────
     WO-INTAKE-IDENTITY-01 — minimal intake gate + legacy helpers
  ─────────────────────────────────────────────────────────── */

  /* ONE QUESTIONNAIRE. WO-01, 2026-09-19.

     There used to be two definitions of this form — a sixteen-section one
     and a three-section one — selected at load time by a flag reader that
     consulted a window variable and a localStorage key. The three-section
     form was an initial development arrangement from WO-INTAKE-IDENTITY-01,
     not a product requirement, and it came with a migration that moved six
     real sections under `_legacyRemovedSections` on every restore and save.
     That migration produced duplicate copies of a section on the server
     (AUDIT-QUESTIONNAIRE-INTEGRITY-AND-CONFIRMATION-01, C1) and, for one
     day, made a narrator whose only content was grandparents look empty (C2).

     The narrator-facing chat walk in session-loop.js never read the
     three-section list at runtime — it tried a window global that was never
     set and used its own hardcoded six-field list. So retiring the minimal
     form changes the operator console and nothing else.

     There is now one definition, SECTIONS, and it is the full record. A
     section the operator cannot see is a section they cannot correct, and
     on 2026-09-15 that is how ten hand-typed values were destroyed. */

  /* ── WO-02: stable entry ids ─────────────────────────────────────────
     Every hop in this system identified a repeatable entry by its array
     index and nothing else — render, collect, transport, flatten, merge and
     the revision history alike. `questionnaire_persistence.py:75-100` names
     that limitation and defers the fix; this is the fix, for the identity
     half of it.

     The id lives INSIDE the entry, not in the path. The server's path
     grammar admits only integers between brackets, so an id-keyed path space
     would mean rewriting the split/get/set/unset machinery and leaving every
     `changed_paths` row already written unresolvable. In-band gives the
     identity without the migration.

     WHAT THIS DOES AND DOES NOT DO. Entries become identifiable, so a save
     can apply an edit to the person it was made against rather than to
     whoever occupies that position now. Paths do NOT become stable: the
     flattened path space and the revision history are still positional, and
     a reorder still renames every path after it. Nor does this close the
     two-tab race — the server's per-path concurrency check (`base_fields`)
     exists and no UI client sends it. Both remain recorded gaps. */
  var ENTRY_ID_KEY = "_entryId";

  /* Does this entry hold an answer, as opposed to only bookkeeping?
     Reuses the core's rule so there is one definition of "real content"
     rather than a second that can drift from it. */
  function _hasEntryContent(entry) {
    if (!entry || typeof entry !== "object") return false;
    var core = window.LorevoxBioBuilderModules && window.LorevoxBioBuilderModules.core;
    if (core && typeof core._hasOperatorContent === "function") {
      return core._hasOperatorContent(entry);
    }
    return Object.keys(entry).some(function (k) {
      if (k.charAt(0) === "_") return false;
      var v = entry[k];
      return v !== null && v !== undefined && String(v).trim() !== "";
    });
  }

  /* One location per section. WO-01, 2026-09-19.

     This used to fall back to `questionnaire._legacyRemovedSections[id]`
     when the top-level key was absent, because a migration — now removed —
     moved six sections there on every restore and save. Both the migration
     and the fallback are gone, together, as one change.

     Why no fallback is kept "just in case": the read-only divergence probe
     run on 2026-09-18 against the live database found the six sections at
     the top level only, for every narrator — zero legacy-only, zero
     duplicated, zero conflicting — and the one browser draft in existence
     held no legacy sections either. A compatibility read guarding nothing is
     not caution; it is a second path for a value to live at, which is the
     defect that was being cleaned up. Any `_legacyRemovedSections` key that
     still exists on a server document is inert: nothing writes to it and
     nothing reads it, and WO-03B's explicit removal can drop it when that
     lands.

     If a legacy-only section is ever found, the answer is the probe and the
     baseline backups in lorevox_packages/, not a resurrected fallback. */
  function getSectionData(questionnaire, id) {
    if (!questionnaire) return null;
    return questionnaire[id] != null ? questionnaire[id] : null;
  }

  /* Phase Q+: Unified relationship type options for spouse/partner section */
  var RELATIONSHIP_TYPE_OPTIONS = [
    "", "Spouse", "Partner", "Former Spouse", "Domestic Partner",
    "Life Partner", "Common-Law Spouse", "Chosen Family", "Other"
  ];

  /* ── Birth-order normalization map ──────────────────────────
     Maps numeric template values to the UI select labels.
     Also handles ordinals like "1st", "2nd", etc.
     Pass-through if the value already matches a known label.
  ──────────────────────────────────────────────────────────── */
  var _BIRTH_ORDER_MAP = {
    "1": "First child",   "1st": "First child",   "first": "First child",
    "2": "Second child",  "2nd": "Second child",  "second": "Second child",
    "3": "Third child",   "3rd": "Third child",   "third": "Third child",
    "4": "Fourth child",  "4th": "Fourth child",  "fourth": "Fourth child",
    "5": "Fifth child",   "5th": "Fifth child",   "fifth": "Fifth child",
    "6": "Sixth child",   "6th": "Sixth child",   "sixth": "Sixth child",
    "7": "Seventh child", "7th": "Seventh child", "seventh": "Seventh child",
    "8": "Eighth child",  "8th": "Eighth child",  "eighth": "Eighth child",
    "9": "Ninth child",   "9th": "Ninth child",   "ninth": "Ninth child",
    "10": "Tenth child",  "10th": "Tenth child",  "tenth": "Tenth child",
    "only": "Only child", "twin": "Twin", "triplet": "Triplet"
  };

  // Phase L: ordinal-word → digit map for descriptive string extraction
  var _ORDINAL_WORD_MAP = {
    "first":"1","second":"2","third":"3","fourth":"4","fifth":"5",
    "sixth":"6","seventh":"7","eighth":"8","ninth":"9","tenth":"10"
  };

  function normalizeBirthOrder(raw) {
    if (!raw) return "";
    var s = String(raw).trim();
    if (!s) return "";
    // Already a valid label? Pass through.
    if (BIRTH_ORDER_OPTIONS.indexOf(s) >= 0) return s;
    // Look up in map (case-insensitive)
    var mapped = _BIRTH_ORDER_MAP[s.toLowerCase()];
    if (mapped) return mapped;

    // Phase L: extract leading digit from descriptive strings
    // e.g., "2 (middle of three children)" → "2" → "Second child"
    var leadDigit = s.match(/^(\d{1,2})\b/);
    if (leadDigit) {
      var digitMapped = _BIRTH_ORDER_MAP[leadDigit[1]];
      if (digitMapped) return digitMapped;
    }

    // Phase L: extract ordinal word from strings like "sixth of eleven children"
    var firstWord = s.toLowerCase().split(/[\s,]+/)[0];
    var ordNum = _ORDINAL_WORD_MAP[firstWord];
    if (ordNum) {
      var ordMapped = _BIRTH_ORDER_MAP[ordNum];
      if (ordMapped) return ordMapped;
    }

    // Unknown value — preserve as-is so nothing is silently lost.
    // The UI select will fall back to default display, but the value is stored.
    return s;
  }

  /* ── US state abbreviation map (for place-of-birth normalization) ── */
  var US_STATES = {
    AL:"Alabama",AK:"Alaska",AZ:"Arizona",AR:"Arkansas",CA:"California",
    CO:"Colorado",CT:"Connecticut",DE:"Delaware",FL:"Florida",GA:"Georgia",
    HI:"Hawaii",ID:"Idaho",IL:"Illinois",IN:"Indiana",IA:"Iowa",KS:"Kansas",
    KY:"Kentucky",LA:"Louisiana",ME:"Maine",MD:"Maryland",MA:"Massachusetts",
    MI:"Michigan",MN:"Minnesota",MS:"Mississippi",MO:"Missouri",MT:"Montana",
    NE:"Nebraska",NV:"Nevada",NH:"New Hampshire",NJ:"New Jersey",
    NM:"New Mexico",NY:"New York",NC:"North Carolina",ND:"North Dakota",
    OH:"Ohio",OK:"Oklahoma",OR:"Oregon",PA:"Pennsylvania",RI:"Rhode Island",
    SC:"South Carolina",SD:"South Dakota",TN:"Tennessee",TX:"Texas",UT:"Utah",
    VT:"Vermont",VA:"Virginia",WA:"Washington",WV:"West Virginia",
    WI:"Wisconsin",WY:"Wyoming",DC:"District of Columbia"
  };

  /* ───────────────────────────────────────────────────────────
     SECTION DEFINITIONS  (Janice Personal Information model)
  ─────────────────────────────────────────────────────────── */

  /* ── WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 Phase 2 ──────
     Status badge helpers — read bb.questionnaire_meta (populated
     by bio-builder-core._restoreQuestionnaireFromBackend from the
     new bio_questionnaire_view service `_meta` blob) and emit:

       (a) per-field <span class="bb-status-badge"> next to the
           field label in the section-detail view,
       (b) per-section "X of Y already known" counter on the
           section-card grid (the filled-skip counter — answers
           the operator's "what does the system already know"
           question at a glance).

     LEGACY-SAFE: when the backend returns a legacy blob response
     with no _meta key, bb.questionnaire_meta is {} and every
     helper falls through to "no badge". The questionnaire still
     renders exactly as before.
  ─────────────────────────────────────────────────────────── */

  // status → {label, css class}. Keys match bio_schema.FACT_STATUSES.
  var _BB_STATUS_LABELS = {
    "approved":               { label: "Approved",      cls: "bb-badge-ok" },
    "operator_entered":       { label: "Entered",       cls: "bb-badge-known" },
    "document_sourced":       { label: "From document", cls: "bb-badge-known" },
    "anchored_asked":         { label: "Asked",         cls: "bb-badge-known" },
    "extracted_needs_verify": { label: "Needs verify",  cls: "bb-badge-amber" },
    "anchored_asked_pending": { label: "Pending",       cls: "bb-badge-amber" },
    "conflicted":             { label: "Conflicted",    cls: "bb-badge-red" },
    "superseded":             { label: "Replaced",      cls: "bb-badge-muted" },
    "empty":                  { label: "",              cls: "" }
  };

  // Statuses counted as "already known" for the filled-skip counter
  // — mirror server-side _FILLED_STATUSES in bio_gap_map.py exactly.
  // anchored_asked_pending + conflicted DO NOT count as known.
  var _BB_KNOWN_STATUSES = {
    "extracted_needs_verify": true,
    "document_sourced":       true,
    "anchored_asked":         true,
    "operator_entered":       true,
    "approved":               true
  };

  // Resolve a meta entry for (sectionId, fieldId). Handles two shapes:
  //   personal: {fieldId: {status, source}}     ← per-field meta
  //   siblings: {_section: {status, source}}    ← section-level meta
  // Returns null when no entry exists or meta block is missing.
  function _bbMetaEntry(meta, sectionId, fieldId) {
    if (!meta || typeof meta !== "object") return null;
    var sec = meta[sectionId];
    if (!sec || typeof sec !== "object") return null;
    if (fieldId && sec[fieldId] && typeof sec[fieldId] === "object") {
      return sec[fieldId];
    }
    return null;
  }

  // Render a status badge for one (sectionId, fieldId). Returns ""
  // when no meta is available. Designed to be safely concatenated into
  // an existing innerHTML string (escapes its own label).
  function _bbStatusBadgeHtml(sectionId, fieldId) {
    var bb = _bb(); if (!bb) return "";
    var entry = _bbMetaEntry(bb.questionnaire_meta, sectionId, fieldId);
    if (!entry || !entry.status || entry.status === "empty") return "";
    var spec = _BB_STATUS_LABELS[entry.status] || null;
    if (!spec || !spec.label) return "";
    var src = (entry.source || "").trim();
    var tooltip = "Status: " + entry.status + (src ? " · Source: " + src : "");
    return '<span class="bb-status-badge ' + spec.cls
      + '" title="' + _esc(tooltip) + '" aria-label="' + _esc(tooltip) + '">'
      + _esc(spec.label) + '</span>';
  }

  // For a given sectionId, count how many slots in bb.questionnaire_meta
  // carry a "known" status. Returns 0 when no meta present.
  function _bbKnownFieldCount(sectionId) {
    var bb = _bb(); if (!bb) return 0;
    var meta = bb.questionnaire_meta || {};
    var sec = meta[sectionId];
    if (!sec || typeof sec !== "object") return 0;
    var n = 0;
    Object.keys(sec).forEach(function (k) {
      if (k === "_section") return;  // section-level rollup, not a field
      var entry = sec[k];
      if (entry && typeof entry === "object" && _BB_KNOWN_STATUSES[entry.status]) {
        n++;
      }
    });
    return n;
  }

  // Pill-style "X already known · Y still open" badge for a section card.
  // Returns "" when no meta present OR no known fields (so legacy blob
  // narrators see no extra pill — byte-stable rendering).
  function _bbKnownPillHtml(section) {
    var known = _bbKnownFieldCount(section.id);
    if (known <= 0) return "";
    var total = section.fields ? section.fields.length : 0;
    var openLabel = (total > 0 && total > known)
      ? " · " + (total - known) + " still open"
      : "";
    return '<span class="bb-pill bb-pill--known" title="Fields already known to Lorevox; you don’t have to re-ask">'
      + known + ' already known' + openLabel + '</span>';
  }

  var SECTIONS = [
    {
      id: "personal", label: "Personal Information", icon: "\u{1F464}",
      hint: "Full name, preferred name, birth date, birth place",
      fields: [
        { id: "fullName",      label: "Full Name",      type: "text",     placeholder: "Enter full name" },
        { id: "preferredName", label: "Preferred Name", type: "text",     placeholder: "Enter preferred name" },
        { id: "birthOrder",    label: "Birth Order",    type: "select",   options: BIRTH_ORDER_OPTIONS },
        { id: "dateOfBirth",   label: "Date of Birth",  type: "text",     placeholder: "Enter date of birth", helperText: "Use YYYY-MM-DD when known. Common formats are normalized automatically.", inputHelper: "normalizeDob" },
        { id: "timeOfBirth",   label: "Time of Birth",  type: "text",     placeholder: "Enter time of birth", helperText: "Common shorthand like 1250p is normalized automatically.", inputHelper: "normalizeTime" },
        { id: "placeOfBirth",  label: "Place of Birth", type: "text",     placeholder: "Enter place of birth", helperText: "Short place names like abbreviations are normalized automatically.", inputHelper: "normalizePlace" },
        { id: "zodiacSign",    label: "Zodiac Sign",    type: "select",   options: ZODIAC_OPTIONS, autoDerive: "zodiacFromDob" }
      ]
    },
    {
      id: "parents", label: "Parents", icon: "\u{1F331}",
      hint: "Mother and father \u2014 names, dates, occupation, notable life events",
      repeatable: true, repeatLabel: "parent",
      fields: [
        { id: "relation",          label: "Relation",                      type: "select",   options: RELATION_OPTIONS },
        { id: "firstName",         label: "First Name",                    type: "text" },
        { id: "middleName",        label: "Middle Name",                   type: "text" },
        { id: "lastName",          label: "Last Name",                     type: "text" },
        { id: "maidenName",        label: "Maiden / Birth Name",           type: "text",     placeholder: "if different from last name" },
        { id: "birthDate",         label: "Birth Date",                    type: "text",     placeholder: "Enter birth date", helperText: "Use YYYY-MM-DD when known.", inputHelper: "normalizeDob" },
        { id: "birthPlace",        label: "Birth Place",                   type: "text",     inputHelper: "normalizePlace" },
        { id: "occupation",        label: "Occupation",                    type: "text" },
        /* BUG-BIO-QUESTIONNAIRE-DEFAULT-AS-ASSERTION-01 (2026-09-18) —
           found by the behavioural harness.

           This was ["No","Yes"]. A select with no empty option is answered
           the moment it is drawn: an untouched entry carried deceased:"No",
           which is a populated leaf, so clicking "+ Add another parent" and
           saving filed a parent whose only recorded fact was that they were
           alive. A phantom family member, and one the family tree renders.

           A default the interface DISPLAYS must not become a biographical
           assertion the record HOLDS. The empty option makes "unanswered"
           expressible, while an operator who deliberately chooses No is
           still recorded — which is the distinction that matters, because
           "not dead" is real information when somebody states it.

           Grandparents already had the empty option. The inconsistency was
           noted in WO-BIO-QUESTIONNAIRE-DEATH-DATE-01 as probably accidental;
           it was, and this is which way it should have gone. */
        { id: "deceased",          label: "Deceased",                      type: "select",   options: ["","No","Yes"] },
        { id: "notableLifeEvents", label: "Notable Life Events / Stories", type: "textarea" },
        { id: "notes",             label: "Additional Notes",              type: "textarea" }
      ]
    },
    {
      id: "grandparents", label: "Grandparents", icon: "\u{1F333}",
      hint: "Ancestry, cultural background, memorable stories",
      repeatable: true, repeatLabel: "grandparent",
      fields: [
        /* BUG-BIO-QUESTIONNAIRE-DEFAULT-AS-ASSERTION-01. Same defect, worse
           consequence: an untouched entry filed every grandparent as
           Paternal. A maternal grandmother recorded on the father's side is
           not a blank to be filled in later — it is a wrong answer that
           looks like a given one, and it propagates into the family tree.

           "Unknown" already existed in the list but was never the default,
           so it could only be reached by choosing it. The empty option is
           what makes "nobody has said yet" distinct from "somebody said
           unknown"; both are worth keeping. */
        { id: "side",                label: "Side",                type: "select",   options: ["","Paternal","Maternal","Paternal-maternal","Paternal-paternal","Maternal-maternal","Maternal-paternal","Unknown"] },
        { id: "firstName",           label: "First Name",          type: "text" },
        { id: "middleName",          label: "Middle Name",         type: "text" },
        { id: "lastName",            label: "Last Name",           type: "text" },
        { id: "maidenName",          label: "Maiden / Birth Name", type: "text",     placeholder: "if different from last name" },
        { id: "birthDate",           label: "Birth Date",          type: "text",     placeholder: "Enter birth date", helperText: "Use YYYY-MM-DD when known.", inputHelper: "normalizeDob" },
        { id: "birthPlace",          label: "Birth Place",         type: "text",     inputHelper: "normalizePlace" },
        { id: "ancestry",            label: "Ancestry",            type: "text" },
        { id: "culturalBackground",  label: "Cultural Background", type: "text" },
        { id: "memorableStories",    label: "Memorable Stories",   type: "textarea" }
      ]
    },
    {
      id: "siblings", label: "Siblings", icon: "\u{1F46B}",
      hint: "Birth order, unique characteristics, shared experiences, memories",
      repeatable: true, repeatLabel: "sibling",
      fields: [
        { id: "relation",              label: "Relation",               type: "select",   options: SIBLING_RELATION_OPTIONS },
        { id: "firstName",             label: "First Name",             type: "text" },
        { id: "middleName",            label: "Middle Name",            type: "text" },
        { id: "lastName",              label: "Last Name",              type: "text" },
        { id: "maidenName",            label: "Maiden / Birth Name",    type: "text",     placeholder: "if different from last name" },
        { id: "birthOrder",            label: "Birth Order",            type: "select",   options: BIRTH_ORDER_OPTIONS },
        { id: "uniqueCharacteristics", label: "Unique Characteristics", type: "textarea" },
        { id: "sharedExperiences",     label: "Shared Experiences",     type: "textarea" },
        { id: "memories",              label: "Memories",               type: "textarea" },
        { id: "notes",                 label: "Additional Notes",       type: "textarea" }
      ]
    },
    {
      id: "children", label: "Children", icon: "\u{1F476}",
      hint: "Sons and daughters \u2014 names, dates, notes",
      repeatable: true, repeatLabel: "child",
      fields: [
        { id: "relation",   label: "Relation",    type: "select",   options: CHILD_RELATION_OPTIONS },
        { id: "firstName",  label: "First Name",  type: "text" },
        { id: "middleName", label: "Middle Name",  type: "text" },
        { id: "lastName",   label: "Last Name",    type: "text" },
        { id: "birthDate",  label: "Birth Date",   type: "text",     placeholder: "Enter birth date", helperText: "Use YYYY-MM-DD when known.", inputHelper: "normalizeDob" },
        { id: "birthPlace", label: "Birth Place",  type: "text",     inputHelper: "normalizePlace" },
        { id: "narrative",  label: "Notes / Narrative", type: "textarea" }
      ]
    },
    /* ── Phase Q+: New sections ─── spouse, marriage, familyTraditions, pets, health, technology ─── */
    {
      id: "spouse", label: "Spouse / Partner", icon: "\u{1F491}",
      hint: "Spouses, partners, and significant relationships",
      repeatable: true, repeatLabel: "partner",
      fields: [
        { id: "relationshipType", label: "Relationship Type",    type: "select",   options: RELATIONSHIP_TYPE_OPTIONS },
        { id: "firstName",        label: "First Name",           type: "text" },
        { id: "middleName",       label: "Middle Name",          type: "text" },
        { id: "lastName",         label: "Last Name",            type: "text" },
        { id: "maidenName",       label: "Maiden / Birth Name",  type: "text",     placeholder: "if different from last name" },
        { id: "birthDate",        label: "Birth Date",           type: "text",     placeholder: "Exact or approximate (e.g. around 1945)", helperText: "Exact dates normalized to YYYY-MM-DD. Approximate dates preserved as-is.", inputHelper: "normalizeDateSafe" },
        { id: "birthPlace",       label: "Birth Place",          type: "text",     inputHelper: "normalizePlace" },
        { id: "occupation",       label: "Occupation",           type: "text" },
        { id: "deceased",         label: "Deceased",             type: "select",   options: ["","No","Yes"] },
        { id: "narrative",        label: "Narrative / Notes",    type: "textarea" }
      ]
    },
    {
      id: "marriage", label: "Marriage & Union Details", icon: "\u{1F48D}",
      hint: "Proposal stories, wedding details, partnership milestones",
      repeatable: true, repeatLabel: "marriage/union",
      fields: [
        { id: "spouseReference",  label: "Spouse / Partner Name", type: "text",    placeholder: "Who is this marriage/union with?" },
        { id: "marriageDate",     label: "Date",                  type: "text",    placeholder: "Exact or approximate", inputHelper: "normalizeDateSafe" },
        /* WO-04. "Cathedral of the Holy Spirit" was arriving with
           nowhere to go but `weddingDetails`, which would have merged a
           place into a prose paragraph. A place deserves a field that
           is what it is. */
        { id: "marriagePlace",    label: "Where",                 type: "text",    inputHelper: "normalizePlace" },
        { id: "proposalStory",    label: "Proposal Story",        type: "textarea" },
        { id: "weddingDetails",   label: "Wedding / Union Details", type: "textarea" }
      ]
    },
    {
      id: "familyTraditions", label: "Family Traditions", icon: "\u{1F38A}",
      hint: "Holiday customs, recipes, cultural practices, family rituals",
      repeatable: true, repeatLabel: "tradition",
      fields: [
        { id: "description",  label: "Tradition Description",  type: "textarea" },
        { id: "occasion",     label: "Occasion / Context",     type: "text" }
      ]
    },
    {
      id: "pets", label: "Pets & Animals", icon: "\u{1F43E}",
      hint: "Beloved animals throughout life",
      repeatable: true, repeatLabel: "pet",
      fields: [
        { id: "name",         label: "Name",          type: "text" },
        { id: "species",      label: "Species",       type: "text",     placeholder: "Dog, Cat, Horse, etc." },
        { id: "breed",        label: "Breed",         type: "text" },
        { id: "birthDate",    label: "Birth Date",    type: "text",     inputHelper: "normalizeDateSafe" },
        { id: "adoptionDate", label: "Adoption Date", type: "text",     inputHelper: "normalizeDateSafe" },
        { id: "notes",        label: "Notes / Memories", type: "textarea" }
      ]
    },
    /* ── WO-04: four destinations that did not exist ──────────────────
       Military service, the homes someone lived in, the trips they took
       and what they believed are ordinary parts of a life, and the form
       could not record any of them. Kent served in Germany and there
       was nowhere in his biography to say so.

       DATES ARE TWO FIELDS, NOT A PERIOD. A single free-text "period"
       is exactly where "temporal context implies short stay, exact
       dates unknown" lands — the model's own hedging stored as an
       answer. Two date fields cannot hold that sentence comfortably,
       and an unknown date stays BLANK.

       ⚠ MEASURED, NOT ASSUMED: `normalizeDob` and `normalizeDateSafe`
       do NOT reject anything. They normalise formats they recognise and
       return the input unchanged otherwise — verified 2026-09-20
       against the real values. So the helper here is a convenience, and
       the rejection of model-uncertainty happens at the extraction
       boundary. Do not read `inputHelper` as a validator. */
    {
      id: "military", label: "Military Service", icon: "\u{1F396}",
      hint: "Postings, units, ranks, where you served and what happened there",
      repeatable: true, repeatLabel: "posting",
      fields: [
        /* Free text, not a select. A select would have refused "Nike
           Ajax Nike Hercules missile site" at the form, which is
           tempting — but this is a family archive and not every
           family's service was in one country's five branches. The
           refusal belongs at extraction, not in the form. */
        { id: "branch",        label: "Branch of Service",  type: "text",     placeholder: "Army, Navy, Royal Air Force…" },
        { id: "unit",          label: "Unit",               type: "text",     placeholder: "e.g. 32nd Artillery Brigade" },
        { id: "rank",          label: "Rank",               type: "text",     helperText: "Rank held during this posting." },
        { id: "serviceStart",  label: "Started",            type: "text",     placeholder: "YYYY-MM-DD or year", helperText: "Leave blank if unknown — do not guess.", inputHelper: "normalizeDob" },
        { id: "serviceEnd",    label: "Ended",              type: "text",     placeholder: "YYYY-MM-DD or year", helperText: "Leave blank if unknown.", inputHelper: "normalizeDob" },
        { id: "location",      label: "Where Stationed",    type: "text",     inputHelper: "normalizePlace" },
        { id: "role",          label: "Duties / Role",      type: "text",     placeholder: "e.g. document courier" },
        { id: "notableEvents", label: "Notable Events",     type: "textarea" },
        { id: "notes",         label: "Additional Notes",   type: "textarea" }
      ]
    },
    {
      id: "residence", label: "Places Lived", icon: "\u{1F3E1}",
      hint: "The homes and towns of a life, and what each one was like",
      repeatable: true, repeatLabel: "home",
      fields: [
        { id: "place",       label: "Place",                type: "text",     placeholder: "City, town or address", inputHelper: "normalizePlace" },
        { id: "periodStart", label: "Moved In",             type: "text",     placeholder: "YYYY-MM-DD or year", helperText: "Leave blank if unknown.", inputHelper: "normalizeDob" },
        { id: "periodEnd",   label: "Moved Out",            type: "text",     placeholder: "YYYY-MM-DD or year", helperText: "Leave blank if unknown.", inputHelper: "normalizeDob" },
        { id: "homeType",    label: "Type of Home",         type: "text",     placeholder: "house, farm, apartment, base housing…" },
        { id: "memories",    label: "Memories of This Home", type: "textarea" }
      ]
    },
    {
      id: "travel", label: "Travel", icon: "\u{2708}",
      hint: "Trips taken — where, why, who with, and what happened",
      repeatable: true, repeatLabel: "trip",
      fields: [
        { id: "destination",   label: "Destination",     type: "text",     inputHelper: "normalizePlace" },
        { id: "year",          label: "When",            type: "text",     placeholder: "Year or date", helperText: "Leave blank if unknown.", inputHelper: "normalizeDateSafe" },
        /* A closed list because "ate our first Germany meal" is not a
           purpose. What happened on the trip has its own field below,
           so the distinction the extractor keeps collapsing is held
           open by the form itself. */
        { id: "purpose",       label: "Purpose",         type: "select",   options: ["", "Vacation", "Work", "Family", "Military", "Pilgrimage", "Study", "Other"] },
        { id: "companions",    label: "Who Went",        type: "text" },
        { id: "whatHappened",  label: "What Happened",   type: "textarea" },
        { id: "notes",         label: "Additional Notes", type: "textarea" }
      ]
    },
    {
      id: "faith", label: "Faith & Beliefs", icon: "\u{1F54A}",
      hint: "Entirely optional — leave any of this blank if you would rather not say",
      fields: [
        { id: "denomination",       label: "Denomination or Tradition", type: "text",     helperText: "Optional. Only what you choose to record — nothing is inferred." },
        { id: "raisedIn",           label: "Raised In",                 type: "text",     helperText: "Optional." },
        { id: "communityRole",      label: "Role in a Faith Community", type: "text",     placeholder: "choir, deacon, usher…" },
        { id: "significantMoments", label: "Significant Moments",       type: "textarea" },
        { id: "notes",              label: "Additional Notes",          type: "textarea" }
      ]
    },
    {
      id: "health", label: "Health & Wellness", icon: "\u{1FA7A}",
      hint: "Health milestones, lifestyle changes, wellness reflections",
      fields: [
        { id: "healthMilestones", label: "Health Milestones",   type: "textarea" },
        { id: "lifestyleChanges", label: "Lifestyle Changes",   type: "textarea" },
        { id: "wellnessTips",     label: "Wellness Tips",       type: "textarea" }
      ]
    },
    {
      /* WO-04: the label was "Technology & Beliefs". Beliefs now have
         their own section, and two homes for one subject is how an
         answer ends up in neither. The field IDS AND STORED DATA ARE
         UNCHANGED — `culturalPractices` keeps its name and every
         narrator's value; only the heading a person reads is different. */
      id: "technology", label: "Technology", icon: "\u{1F4F1}",
      hint: "Tech experiences, gadgets, cultural practices",
      fields: [
        { id: "firstTechExperience", label: "First Tech Experience",  type: "textarea" },
        { id: "favoriteGadgets",     label: "Favorite Gadgets",       type: "textarea" },
        { id: "culturalPractices",   label: "Cultural Practices",     type: "textarea" }
      ]
    },
    {
      id: "earlyMemories", label: "Early Memories", icon: "\u{1F319}",
      hint: "First memory, favorite toy, significant early events",
      fields: [
        { id: "firstMemory",      label: "First Memory",            type: "textarea" },
        { id: "favoriteToy",      label: "Favorite Toy / Object",   type: "textarea" },
        { id: "significantEvent", label: "Significant Early Event", type: "textarea" }
      ]
    },
    {
      id: "education", label: "Education & Career", icon: "\u{1F393}",
      hint: "Schooling, higher education, career, community involvement",
      fields: [
        { id: "schooling",             label: "Schooling",              type: "textarea" },
        /* WO-04, correction 1. A grade level and a schooling history
           are different kinds of information, so "6th grade" gets its
           own labelled field rather than being folded into the prose.
           The existing queued suggestion is NOT rewritten to this path
           — it stays where it is until a person reviews it. */
        { id: "gradeLevel",            label: "Highest Grade Completed", type: "text",    placeholder: "e.g. 8th grade, high school diploma" },
        { id: "higherEducation",       label: "Higher Education",       type: "textarea" },
        { id: "earlyCareer",           label: "Early Career",           type: "textarea" },
        { id: "careerProgression",     label: "Career Progression",     type: "textarea" },
        { id: "communityInvolvement",  label: "Community Involvement",  type: "textarea" },
        { id: "mentorship",            label: "Mentorship",             type: "textarea" }
      ]
    },
    {
      id: "laterYears", label: "Later Years", icon: "\u{1F305}",
      hint: "Retirement, life lessons, advice for future generations",
      fields: [
        { id: "retirement",                     label: "Retirement",                      type: "textarea" },
        { id: "lifeLessons",                    label: "Life Lessons",                    type: "textarea" },
        { id: "adviceForFutureGenerations",     label: "Advice for Future Generations",   type: "textarea" }
      ]
    },
    {
      id: "hobbies", label: "Hobbies & Interests", icon: "\u{1F3A8}",
      hint: "Hobbies, world events, personal challenges, travel",
      fields: [
        { id: "hobbies",             label: "Hobbies",             type: "textarea" },
        { id: "worldEvents",         label: "World Events",        type: "textarea" },
        { id: "personalChallenges",  label: "Personal Challenges", type: "textarea" },
        { id: "travel",              label: "Travel",              type: "textarea" }
      ]
    },
    {
      id: "additionalNotes", label: "Additional Notes", icon: "\u{1F4DD}",
      hint: "Unfinished dreams, messages for future generations",
      fields: [
        { id: "unfinishedDreams",              label: "Unfinished Dreams",                type: "textarea" },
        { id: "messagesForFutureGenerations",  label: "Messages for Future Generations",  type: "textarea" }
      ]
    }
  ];


  /* ───────────────────────────────────────────────────────────
     NORMALIZATION HELPERS
  ─────────────────────────────────────────────────────────── */

  var _MONTH_NAMES = {
    jan:1,january:1,feb:2,february:2,mar:3,march:3,apr:4,april:4,
    may:5,jun:6,june:6,jul:7,july:7,aug:8,august:8,sep:9,sept:9,september:9,
    oct:10,october:10,nov:11,november:11,dec:12,december:12
  };

  function normalizeDobInput(raw) {
    if (!raw) return "";
    var s = raw.trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
    var m, mm, dd, yyyy;
    if (/^\d{8}$/.test(s)) {
      mm = parseInt(s.slice(0, 2), 10); dd = parseInt(s.slice(2, 4), 10); yyyy = parseInt(s.slice(4), 10);
      if (mm >= 1 && mm <= 12 && dd >= 1 && dd <= 31 && yyyy >= 1800 && yyyy <= 2100)
        return yyyy + "-" + String(mm).padStart(2, "0") + "-" + String(dd).padStart(2, "0");
    }
    m = s.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})$/);
    if (m) {
      mm = parseInt(m[1], 10); dd = parseInt(m[2], 10); yyyy = parseInt(m[3], 10);
      if (mm >= 1 && mm <= 12 && dd >= 1 && dd <= 31)
        return yyyy + "-" + String(mm).padStart(2, "0") + "-" + String(dd).padStart(2, "0");
    }
    m = s.match(/^([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})$/);
    if (m) {
      var mon = _MONTH_NAMES[m[1].toLowerCase()];
      if (mon) {
        dd = parseInt(m[2], 10); yyyy = parseInt(m[3], 10);
        return yyyy + "-" + String(mon).padStart(2, "0") + "-" + String(dd).padStart(2, "0");
      }
    }
    m = s.match(/^(\d{1,2})\s+(\d{1,2})\s+(\d{4})$/);
    if (m) {
      mm = parseInt(m[1], 10); dd = parseInt(m[2], 10); yyyy = parseInt(m[3], 10);
      if (mm >= 1 && mm <= 12 && dd >= 1 && dd <= 31)
        return yyyy + "-" + String(mm).padStart(2, "0") + "-" + String(dd).padStart(2, "0");
    }
    return s;
  }

  function normalizeTimeOfBirthInput(raw) {
    if (!raw) return "";
    var s = raw.trim().toLowerCase().replace(/\s+/g, "");
    var m, h, min, ampm;
    m = s.match(/^(\d{3,4})(a|am|p|pm)$/);
    if (m) {
      var digits = m[1].padStart(4, "0");
      h = parseInt(digits.slice(0, 2), 10); min = parseInt(digits.slice(2), 10);
      ampm = m[2].charAt(0) === "a" ? "AM" : "PM";
      if (h >= 1 && h <= 12 && min >= 0 && min <= 59)
        return h + ":" + String(min).padStart(2, "0") + " " + ampm;
    }
    m = s.match(/^(\d{1,2}):(\d{2})\s*(a|am|p|pm)$/);
    if (m) {
      h = parseInt(m[1], 10); min = parseInt(m[2], 10);
      ampm = m[3].charAt(0) === "a" ? "AM" : "PM";
      if (h >= 1 && h <= 12 && min >= 0 && min <= 59)
        return h + ":" + String(min).padStart(2, "0") + " " + ampm;
    }
    m = s.match(/^(\d{1,2}):(\d{2})$/);
    if (m) {
      h = parseInt(m[1], 10); min = parseInt(m[2], 10);
      if (h >= 0 && h <= 23 && min >= 0 && min <= 59) {
        ampm = h >= 12 ? "PM" : "AM";
        var h12 = h === 0 ? 12 : (h > 12 ? h - 12 : h);
        return h12 + ":" + String(min).padStart(2, "0") + " " + ampm;
      }
    }
    m = s.match(/^(\d{4})$/);
    if (m) {
      h = parseInt(s.slice(0, 2), 10); min = parseInt(s.slice(2), 10);
      if (h >= 0 && h <= 23 && min >= 0 && min <= 59) {
        ampm = h >= 12 ? "PM" : "AM";
        var h12b = h === 0 ? 12 : (h > 12 ? h - 12 : h);
        return h12b + ":" + String(min).padStart(2, "0") + " " + ampm;
      }
    }
    return raw.trim();
  }

  var _US_STATE_NAMES = {};
  (function () {
    for (var abbr in US_STATES) {
      _US_STATE_NAMES[US_STATES[abbr].toLowerCase()] = US_STATES[abbr];
    }
  })();

  function normalizePlaceInput(raw) {
    if (!raw) return "";
    var s = raw.trim();
    // BUG-211: strip trailing STT fillers / dangling prepositions before
    // running the state-name match.  Live evidence: Jake's pob came in
    // as "Elbowoods on" because voice input captured a trailing
    // preposition (probably " on a farm" cut off by STT).  Causes Lori
    // to render "It's wonderful that you were born in Elbowoods on."
    // — confusing for older-adult narrators.
    var TRAILING_FILLERS = /\s+(on|in|at|of|the|a|an|and|or|but|um|uh|oh|so|like|just|with|by)$/i;
    var TRAILING_PUNCT = /[\s,.;:!?\-]+$/;
    s = s.replace(TRAILING_PUNCT, "");
    // strip up to 2 trailing fillers in case STT dropped multiple
    for (var k = 0; k < 2; k++) {
      var stripped = s.replace(TRAILING_FILLERS, "");
      if (stripped === s) break;
      s = stripped.replace(TRAILING_PUNCT, "");
    }
    var m, full;
    m = s.match(/^(.+?),\s*([A-Z]{2})$/i);
    if (m) { full = US_STATES[m[2].toUpperCase()]; if (full) return m[1].trim() + ", " + full; }
    m = s.match(/^(.+?)\s+([A-Z]{2})$/i);
    if (m) { full = US_STATES[m[2].toUpperCase()]; if (full) return m[1].trim().replace(/,\s*$/, "") + ", " + full; }
    var words = s.split(/\s+/);
    for (var i = words.length - 1; i >= 1; i--) {
      var candidateState = words.slice(i).join(" ").toLowerCase();
      var fullState = _US_STATE_NAMES[candidateState];
      if (fullState) { return words.slice(0, i).join(" ").replace(/,\s*$/, "") + ", " + fullState; }
    }
    return s;
  }

  function deriveZodiacFromDob(isoDate) {
    if (!isoDate) return "";
    var parts = isoDate.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!parts) return "";
    var mm = parseInt(parts[2], 10), dd = parseInt(parts[3], 10);
    if (mm < 1 || mm > 12 || dd < 1 || dd > 31) return "";
    if ((mm===1 && dd<=19) || (mm===12 && dd>=22)) return "Capricorn";
    if ((mm===1 && dd>=20) || (mm===2 && dd<=18)) return "Aquarius";
    if ((mm===2 && dd>=19) || (mm===3 && dd<=20)) return "Pisces";
    if ((mm===3 && dd>=21) || (mm===4 && dd<=19)) return "Aries";
    if ((mm===4 && dd>=20) || (mm===5 && dd<=20)) return "Taurus";
    if ((mm===5 && dd>=21) || (mm===6 && dd<=20)) return "Gemini";
    if ((mm===6 && dd>=21) || (mm===7 && dd<=22)) return "Cancer";
    if ((mm===7 && dd>=23) || (mm===8 && dd<=22)) return "Leo";
    if ((mm===8 && dd>=23) || (mm===9 && dd<=22)) return "Virgo";
    if ((mm===9 && dd>=23) || (mm===10 && dd<=22)) return "Libra";
    if ((mm===10 && dd>=23) || (mm===11 && dd<=21)) return "Scorpio";
    if ((mm===11 && dd>=22) || (mm===12 && dd<=21)) return "Sagittarius";
    return "";
  }

  /* Phase Q+: Uncertainty-safe date normalizer
     Normalizes exact dates (YYYY-MM-DD, MM/DD/YYYY etc.) but preserves
     approximate/uncertain dates like "around 1945", "early 1960s",
     "approximately 1914", "mid-1970s", year-only values like "1966" etc.
  */
  function normalizeDateSafe(raw) {
    if (!raw) return "";
    var s = raw.trim();
    if (!s) return "";
    // Already ISO? pass through
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
    // Approximate markers — preserve as-is
    if (/^(around|about|approximately|approx\.?|circa|ca\.?|c\.?|early|mid|late|before|after)\s/i.test(s)) return s;
    // Decade references — preserve as-is
    if (/\d{4}s/.test(s)) return s;
    // Year-only — preserve as-is (don't force to YYYY-01-01)
    if (/^\d{4}$/.test(s)) return s;
    // Try exact normalization
    var normalized = normalizeDobInput(s);
    return normalized;
  }

  function _splitFullName(full) {
    if (!full) return { first: "", middle: "", last: "" };
    var parts = full.trim().split(/\s+/);
    if (parts.length === 1) return { first: parts[0], middle: "", last: "" };
    if (parts.length === 2) return { first: parts[0], middle: "", last: parts[1] };
    return { first: parts[0], middle: parts.slice(1, -1).join(" "), last: parts[parts.length - 1] };
  }

  function buildCanonicalBasicsFromBioBuilder() {
    var bb = _bb(); if (!bb) return null;
    var q = bb.questionnaire.personal;
    if (!q) return null;
    var dob = normalizeDobInput(q.dateOfBirth || "");
    var zodiac = q.zodiacSign || "";
    if (!zodiac && dob) zodiac = deriveZodiacFromDob(dob);
    var rawPlace = q.placeOfBirth || "";
    var normPlace = normalizePlaceInput(rawPlace);
    var nameParts = _splitFullName(q.fullName || "");
    var birthOrder = q.birthOrder || "";
    var birthOrderCustom = "";
    if (birthOrder === "Other/custom") { birthOrderCustom = ""; }
    return {
      fullname:               q.fullName      || "",
      preferred:              q.preferredName || "",
      legalFirstName:         nameParts.first,
      legalMiddleName:        nameParts.middle,
      legalLastName:          nameParts.last,
      dob:                    dob,
      timeOfBirth:            normalizeTimeOfBirthInput(q.timeOfBirth || ""),
      timeOfBirthDisplay:     normalizeTimeOfBirthInput(q.timeOfBirth || ""),
      pob:                    normPlace,
      placeOfBirthRaw:        rawPlace,
      placeOfBirthNormalized: normPlace,
      birthOrder:             birthOrder,
      birthOrderCustom:       birthOrderCustom,
      zodiacSign:             zodiac
    };
  }

  /* ───────────────────────────────────────────────────────────
     PROFILE → QUESTIONNAIRE HYDRATION (v6-fix)
     One-way: only fills empty questionnaire sections from profile.
     NEVER overwrites existing Bio Builder questionnaire data.
  ─────────────────────────────────────────────────────────── */

  // Phase 3.3: Track whether hydration has already run for this narrator
  var _lastHydratedPid = null;

  function _hydrateQuestionnaireFromProfile(bb) {
    if (!bb) return;
    try {
      if (typeof state === "undefined" || !state.profile || !state.profile.basics) return;
    } catch (_) { return; }
    var basics = state.profile.basics;

    // Phase 3.3: Make hydration idempotent — skip if already hydrated for this narrator
    var currentPid = bb.personId || null;
    if (currentPid && currentPid === _lastHydratedPid) {
      // Already hydrated this narrator — don't re-run (protects manual edits)
      return;
    }

    // BUG-FE-HYDRATION-CROSS-NARRATOR-LEAK-01 (2026-06-16):
    // Refuse to hydrate when state.profile is for a DIFFERENT narrator
    // than the current bb.personId. The state.profile pin is set in
    // app.js loadPerson() after the async /api/profiles fetch
    // completes; if hydration fires during the narrator-switch window
    // before that completes, state.profile.person_id may still be the
    // previous narrator's id (or absent on first cold start). Either
    // way, refusing to copy stale basics into bb.questionnaire.personal
    // prevents the autosave path from writing the wrong narrator's
    // data under the current pid.
    if (currentPid && state.profile.person_id &&
        state.profile.person_id !== currentPid) {
      console.warn("[bb-hydrate] BLOCKED: state.profile.person_id=" +
        (state.profile.person_id || "").slice(0, 8) +
        " !== bb.personId=" + currentPid.slice(0, 8) +
        " — refusing cross-narrator hydration");
      return;
    }
    if (currentPid && !state.profile.person_id) {
      console.warn("[bb-hydrate] BLOCKED: state.profile has no person_id pin " +
        "— treating as stale to avoid cross-narrator leak (bb.personId=" +
        currentPid.slice(0, 8) + ")");
      return;
    }

    var q = bb.questionnaire.personal;
    var personalEmpty = !q || !_hasAnyValue(q);
    if (personalEmpty) {
      // Phase 3.1: Fix full-name hydration — prefer display name, then composed full name
      var fullName = "";
      if (basics.fullname && basics.fullname.trim()) {
        fullName = basics.fullname.trim();
      } else {
        // Compose from parts: first + middle + last
        var parts = [basics.legalFirstName, basics.legalMiddleName, basics.legalLastName].filter(Boolean);
        if (parts.length > 0) {
          fullName = parts.join(" ").trim();
        } else if (basics.preferred && basics.preferred.trim()) {
          // Fallback to preferred name only if nothing else exists
          fullName = basics.preferred.trim();
        }
      }

      bb.questionnaire.personal = {
        fullName:      fullName,
        preferredName: basics.preferred             || "",
        birthOrder:    normalizeBirthOrder(basics.birthOrder),
        dateOfBirth:   basics.dob                   || "",
        timeOfBirth:   basics.timeOfBirth           || basics.timeOfBirthDisplay || "",
        placeOfBirth:  basics.placeOfBirthNormalized || basics.pob || basics.placeOfBirthRaw || "",
        zodiacSign:    basics.zodiacSign            || ""
      };
      if (bb.questionnaire.personal.dateOfBirth && !bb.questionnaire.personal.zodiacSign) {
        var derived = deriveZodiacFromDob(bb.questionnaire.personal.dateOfBirth);
        if (derived) bb.questionnaire.personal.zodiacSign = derived;
      }
    }

    // v8-fix LV-009: profile.kinship is a flat array [{name, relation, ...}],
    // not an object with .parents/.siblings sub-arrays.  Filter by relation.
    var kinArr = Array.isArray(state.profile.kinship) ? state.profile.kinship : [];
    var _PARENT_RELS = /^(father|mother|parent|dad|mom|step.?father|step.?mother|adoptive.?father|adoptive.?mother)$/i;
    var _SIBLING_RELS = /^(brother|sister|sibling|half.?brother|half.?sister|step.?brother|step.?sister)$/i;

    if (kinArr.length) {
      // --- Parents from flat kinship ---
      // Phase 3.2: only hydrate if section is truly empty (no manual content)
      var kinParents = kinArr.filter(function (k) { return _PARENT_RELS.test(k.relation || ""); });
      if (kinParents.length) {
        var existingParents = bb.questionnaire.parents;
        var parentsEmpty = !existingParents || (Array.isArray(existingParents) && existingParents.length === 0)
          || (!Array.isArray(existingParents) && !_hasAnyValue(existingParents));
        if (parentsEmpty) {
          bb.questionnaire.parents = kinParents.map(function (p) {
            var parts = (p.name || "").split(/\s+/);
            return {
              relation: p.relation || "", firstName: parts[0] || "",
              middleName: parts.length > 2 ? parts.slice(1, -1).join(" ") : "",
              lastName: parts.length > 1 ? parts[parts.length - 1] : "",
              maidenName: "", birthDate: p.dob || "", birthPlace: p.pob || "",
              occupation: p.occupation || "", notableLifeEvents: "", notes: ""
            };
          });
        }
      }

      // --- Siblings from flat kinship ---
      // Phase 3.2: only hydrate if section is truly empty
      var kinSiblings = kinArr.filter(function (k) { return _SIBLING_RELS.test(k.relation || ""); });
      if (kinSiblings.length) {
        var existingSiblings = bb.questionnaire.siblings;
        var siblingsEmpty = !existingSiblings || (Array.isArray(existingSiblings) && existingSiblings.length === 0)
          || (!Array.isArray(existingSiblings) && !_hasAnyValue(existingSiblings));
        if (siblingsEmpty) {
          bb.questionnaire.siblings = kinSiblings.map(function (s) {
            var parts = (s.name || "").split(/\s+/);
            return {
              relation: s.relation || "", firstName: parts[0] || "",
              middleName: parts.length > 2 ? parts.slice(1, -1).join(" ") : "",
              lastName: parts.length > 1 ? parts[parts.length - 1] : "",
              birthOrder: "", uniqueCharacteristics: "", sharedExperiences: "",
              memories: "", notes: ""
            };
          });
        }
      }
    }

    // Phase 3.3: Mark this narrator as hydrated so reopens don't re-run
    _lastHydratedPid = currentPid;
  }

  // Register hydration as a post-switch hook in core
  _core._registerPostSwitchHook(_hydrateQuestionnaireFromProfile);

  /* ───────────────────────────────────────────────────────────
     CANDIDATE EXTRACTION FROM QUESTIONNAIRE
  ─────────────────────────────────────────────────────────── */

  function _extractQuestionnaireCandidates(sectionId) {
    var bb = _bb(); if (!bb) return;
    var q  = bb.questionnaire[sectionId]; if (!q) return;

    if (sectionId === "parents") {
      var parents = Array.isArray(q) ? q : [q];
      parents.forEach(function (parent) {
        var name = [parent.firstName, parent.middleName, parent.lastName].filter(Boolean).join(" ");
        if (!name) return;
        if (_candidateExists(bb, "people", name, "questionnaire:parents")) return;
        bb.candidates.people.push({
          id: _uid(), type: "person", source: "questionnaire:parents",
          sourceId: sectionId, sourceFilename: null,
          data: { name: name, birthDate: parent.birthDate || "",
                  birthPlace: parent.birthPlace || "", occupation: parent.occupation || "",
                  maidenName: parent.maidenName || "",
                  notes: [parent.notableLifeEvents, parent.notes].filter(Boolean).join("\n\n") },
          status: "pending"
        });
        var narratorName = _currentPersonName();
        var relLabel = parent.relation || "parent";
        if (narratorName && name) {
          if (!_relCandidateExists(bb, narratorName, name)) {
            bb.candidates.relationships.push({
              id: _uid(), type: "relationship", source: "questionnaire:parents",
              sourceId: sectionId, sourceFilename: null,
              data: { personA: narratorName, personB: name, relation: relLabel },
              status: "pending"
            });
          }
        }
      });
    }

    if (sectionId === "grandparents") {
      var gps = Array.isArray(q) ? q : [q];
      gps.forEach(function (gp) {
        // Phase P: include middleName in candidate name, add enriched fields
        var name = [gp.firstName, gp.middleName, gp.lastName].filter(Boolean).join(" ");
        if (!name) return;
        if (_candidateExists(bb, "people", name, "questionnaire:grandparents")) return;
        bb.candidates.people.push({
          id: _uid(), type: "person", source: "questionnaire:grandparents",
          sourceId: sectionId, sourceFilename: null,
          data: { name: name, side: gp.side || "", maidenName: gp.maidenName || "",
                  birthDate: gp.birthDate || "", birthPlace: gp.birthPlace || "",
                  ancestry: gp.ancestry || "",
                  culturalBackground: gp.culturalBackground || "",
                  notes: gp.memorableStories || "" },
          status: "pending"
        });
      });
    }

    if (sectionId === "siblings") {
      var sibs = Array.isArray(q) ? q : [q];
      sibs.forEach(function (sib) {
        var name = [sib.firstName, sib.middleName, sib.lastName].filter(Boolean).join(" ");
        if (!name) return;
        if (_candidateExists(bb, "people", name, "questionnaire:siblings")) return;
        bb.candidates.people.push({
          id: _uid(), type: "person", source: "questionnaire:siblings",
          sourceId: sectionId, sourceFilename: null,
          data: { name: name, relation: sib.relation || "", birthOrder: sib.birthOrder || "",
                  notes: [sib.uniqueCharacteristics, sib.sharedExperiences, sib.memories, sib.notes].filter(Boolean).join("\n\n") },
          status: "pending"
        });
      });
    }

    // Phase K: children candidate extraction
    if (sectionId === "children") {
      var kids = Array.isArray(q) ? q : [q];
      kids.forEach(function (ch) {
        var name = [ch.firstName, ch.middleName, ch.lastName].filter(Boolean).join(" ");
        if (!name) return;
        if (_candidateExists(bb, "people", name, "questionnaire:children")) return;
        bb.candidates.people.push({
          id: _uid(), type: "person", source: "questionnaire:children",
          sourceId: sectionId, sourceFilename: null,
          data: { name: name, relation: ch.relation || "Child", birthDate: ch.birthDate || "",
                  birthPlace: ch.birthPlace || "",
                  notes: ch.narrative || "" },
          status: "pending"
        });
        var narratorName = _currentPersonName();
        if (narratorName && name) {
          if (!_relCandidateExists(bb, narratorName, name)) {
            bb.candidates.relationships.push({
              id: _uid(), type: "relationship", source: "questionnaire:children",
              sourceId: sectionId, sourceFilename: null,
              data: { personA: narratorName, personB: name, relation: ch.relation || "Child" },
              status: "pending"
            });
          }
        }
      });
    }

    // Phase Q+: Spouse/Partner candidate extraction
    if (sectionId === "spouse") {
      var spouses = Array.isArray(q) ? q : [q];
      spouses.forEach(function (sp) {
        var name = [sp.firstName, sp.middleName, sp.lastName].filter(Boolean).join(" ");
        if (!name) return;
        if (_candidateExists(bb, "people", name, "questionnaire:spouse")) return;
        bb.candidates.people.push({
          id: _uid(), type: "person", source: "questionnaire:spouse",
          sourceId: sectionId, sourceFilename: null,
          data: { name: name, relationshipType: sp.relationshipType || "Spouse",
                  maidenName: sp.maidenName || "",
                  birthDate: sp.birthDate || "", birthPlace: sp.birthPlace || "",
                  occupation: sp.occupation || "", notes: sp.narrative || "" },
          status: "pending"
        });
        var narratorName = _currentPersonName();
        if (narratorName && name) {
          if (!_relCandidateExists(bb, narratorName, name)) {
            bb.candidates.relationships.push({
              id: _uid(), type: "relationship", source: "questionnaire:spouse",
              sourceId: sectionId, sourceFilename: null,
              data: { personA: narratorName, personB: name, relation: sp.relationshipType || "Spouse" },
              status: "pending"
            });
          }
        }
      });
    }

    if (sectionId === "earlyMemories") {
      var memFields = [
        { key: "firstMemory",      label: "First Memory" },
        { key: "favoriteToy",      label: "Favorite Toy / Object" },
        { key: "significantEvent", label: "Significant Early Event" }
      ];
      memFields.forEach(function (mf) {
        if (!q[mf.key]) return;
        if (_memCandidateExists(bb, q[mf.key])) return;
        bb.candidates.memories.push({
          id: _uid(), type: "memory", source: "questionnaire:earlyMemories",
          sourceId: sectionId, sourceFilename: null,
          data: { label: mf.label, text: q[mf.key] },
          status: "pending"
        });
      });
    }
  }

  function _candidateExists(bb, bucket, name, source) {
    return bb.candidates[bucket].some(function (c) {
      return c.data.name === name && c.source === source;
    });
  }
  function _relCandidateExists(bb, personA, personB) {
    return bb.candidates.relationships.some(function (c) {
      return c.data.personA === personA && c.data.personB === personB;
    });
  }
  function _memCandidateExists(bb, text) {
    return bb.candidates.memories.some(function (c) {
      return c.data && c.data.text === text;
    });
  }

  /* ───────────────────────────────────────────────────────────
     SECTION FILL PROGRESS
  ─────────────────────────────────────────────────────────── */

  function _sectionFillCount(section) {
    var bb = _bb(); if (!bb) return 0;
    // Phase 1.2: ensure canonical state is current before counting
    var pid = _currentPersonId();
    if (pid && (!bb.questionnaire || Object.keys(bb.questionnaire).length === 0)) {
      _restoreQuestionnaire(pid);
    }
    var q  = getSectionData(bb.questionnaire, section.id); if (!q) return 0;
    if (section.repeatable) { return (Array.isArray(q) ? q : [q]).length; }
    return section.fields.filter(function (f) { return q[f.id] && String(q[f.id]).trim(); }).length;
  }

  /* ───────────────────────────────────────────────────────────
     QUESTIONNAIRE TAB RENDERING
  ─────────────────────────────────────────────────────────── */

  // _activeSection is managed by the caller (bio-builder.js) and passed in
  // via the render functions.  These functions receive a renderCallback to
  // trigger re-renders through the parent's _renderActiveTab.

  function _renderQuestionnaireTab(container, pid, activeSection, renderActiveTab) {
    if (!pid) {
      container.innerHTML = _emptyStateHtml("No narrator selected", "Select a narrator to start the structured questionnaire.", []);
      return;
    }
    // BUG-220A: fail-closed scope guard. If bb.personId still points at
    // the previous narrator (async race or missing _personChanged hop),
    // refuse to paint stale data. Caller (_renderActiveTab) also guards
    // this; belt-and-suspenders here protects any direct call paths
    // (e.g., section-detail re-render after edit).
    var bb = _bb();
    if (bb && bb.personId && bb.personId !== pid) {
      console.warn("[bb-scope] questionnaire tab render blocked — bb.personId=" +
        (bb.personId || "").slice(0, 8) + " active=" + pid.slice(0, 8));
      container.innerHTML = _emptyStateHtml(
        "Loading active narrator questionnaire…",
        "Scope reconciling. If this persists, switch narrators again.",
        []);
      return;
    }
    // Phase 1.2: ensure canonical questionnaire state is loaded before any render
    if (bb && (!bb.questionnaire || Object.keys(bb.questionnaire).length === 0)) {
      _restoreQuestionnaire(pid);
    }
    _qqDebugSnapshot("tab_render", pid);
    if (activeSection) { _renderSectionDetail(container, activeSection, renderActiveTab); return; }

    var sectionCards = SECTIONS.map(function (s) {
      var fillCount = _sectionFillCount(s);
      // Phase Q+: sparse-safe rendering — "No information yet" instead of hidden/broken
      var progressHtml = s.repeatable
        ? (fillCount > 0 ? '<span class="bb-pill bb-pill--has">' + fillCount + ' entr' + (fillCount === 1 ? "y" : "ies") + '</span>' : '<span class="bb-pill bb-pill--empty">No information yet</span>')
        : (fillCount > 0 ? '<span class="bb-pill bb-pill--has">' + fillCount + " / " + s.fields.length + ' filled</span>' : '<span class="bb-pill bb-pill--empty">No information yet</span>');
      // WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 Phase 2 — append the
      // filled-skip pill when bio_facts already knows fields in this
      // section. Empty string when no meta or no known fields, so the
      // section card is byte-stable for legacy-blob narrators.
      var knownPillHtml = _bbKnownPillHtml(s);
      return '<div class="bb-section-card" onclick="window.LorevoxBioBuilder._openSection(\'' + s.id + '\')">'
        + '<div class="bb-section-card-icon">' + s.icon + '</div>'
        + '<div class="bb-section-card-body">'
        +   '<div class="bb-section-card-title">' + _esc(s.label) + '</div>'
        +   '<div class="bb-section-card-hint">' + _esc(s.hint) + '</div>'
        + '</div>'
        + '<div class="bb-section-card-progress">' + progressHtml + knownPillHtml + '</div>'
        + '</div>';
    }).join("");

    container.innerHTML =
      '<div class="bb-section-title">Questionnaire Sections</div>'
      + '<p class="bb-hint-text">Fill in any section to capture biographical material. Answers become candidate items you can review.</p>'
      + '<div class="bb-section-grid">' + sectionCards + '</div>';
  }

  function _renderSectionDetail(container, activeSection, renderActiveTab) {
    var section = SECTIONS.find(function (s) { return s.id === activeSection; });
    if (!section) { return; }
    var bb = _bb();
    // Phase 1.2: ensure canonical state before rendering detail
    var pid = _currentPersonId();
    if (pid && (!bb.questionnaire || Object.keys(bb.questionnaire).length === 0)) {
      _restoreQuestionnaire(pid);
    }
    var existing = getSectionData(bb.questionnaire, section.id);
    var fieldsHtml;

    if (section.repeatable) {
      var entries = Array.isArray(existing) ? existing : (existing ? [existing] : [{}]);
      fieldsHtml = entries.map(function (entry, idx) {
        /* WO-02 — carry the entry's id into the form.
           The save matches on this, not on position. Rendering it is what
           makes that possible: without it the collect path has nothing but
           the index, which is the whole problem. A hidden input rather than
           a data attribute only because the collect path reads the DOM
           through `_el(id)` and this keeps it to one mechanism.
           Empty for an entry that has none yet — one is minted on save. */
        var eid = (entry && entry[ENTRY_ID_KEY]) || "";
        return '<div class="bb-repeat-entry" data-lv-entry-id="' + _esc(eid) + '">'
          + '<input type="hidden" id="bbQ_' + idx + '__entryId" value="' + _esc(eid) + '">'
          + '<div class="bb-repeat-label">' + _esc(section.repeatLabel || "entry") + " " + (idx + 1) + '</div>'
          + section.fields.map(function (f) { return _fieldHtml(f, "bbQ_" + idx + "_" + f.id, entry[f.id] || "", section.id); }).join("")
          + '</div>';
      }).join("")
      + '<button class="bb-ghost-btn bb-add-entry-btn" onclick="event.stopPropagation();event.preventDefault();window.LorevoxBioBuilder._addRepeatEntry(\'' + section.id + '\')">'
      + '+ Add another ' + _esc(section.repeatLabel || "entry") + '</button>';
    } else {
      var q = existing || {};
      fieldsHtml = section.fields.map(function (f) { return _fieldHtml(f, "bbQ_" + f.id, q[f.id] || "", section.id); }).join("");
    }

    /* BUG-BIO-QUESTIONNAIRE-STALE-FORM-CROSS-WRITE-01 (2026-09-18) \u2014
       found by the behavioural harness.

       Stamp the narrator this form was rendered for. _saveSection reads the
       DOM; the cross-narrator guard in _persistDrafts compares the pid
       ARGUMENT against bb.personId, and after a switch those agree \u2014 so a
       save driven from a form still showing the PREVIOUS narrator wrote that
       narrator's visible answers into the new one's record. Reproduced in the
       harness: narrator A's mother was stored under narrator B's id.

       The live app re-renders on switch, which is why this has not been seen.
       That is a timing accident, not a guarantee, and the cost of being wrong
       is one family's history appearing in another's record. */
    container.innerHTML =
      '<input type="hidden" id="bbQ__renderedFor" value="' + _esc(pid || "") + '">'
      + '<div class="bb-section-nav"><button class="bb-ghost-btn bb-back-btn" onclick="window.LorevoxBioBuilder._closeSection()">\u2190 Back to Sections</button></div>'
      + '<div class="bb-section-title">' + section.icon + " " + _esc(section.label) + '</div>'
      + '<p class="bb-hint-text">' + _esc(section.hint) + '</p>'
      + '<div class="bb-fields-list">' + fieldsHtml + '</div>'
      + '<div class="bb-section-footer"><button class="bb-btn-primary" onclick="window.LorevoxBioBuilder._saveSection(\'' + section.id + '\')">Save ' + _esc(section.label) + '</button></div>';
  }

  function _fieldHtml(field, domId, value, sectionId) {
    var va = _esc(value);
    // WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 Phase 2 — status badge.
    // sectionId is optional; legacy call sites that don't pass it still
    // work (no badge shown). _bbStatusBadgeHtml returns "" when no meta
    // entry is found, so this is byte-stable for repeatable entries
    // (which have no per-entry meta in the current design — section-
    // level _section rollup is rendered separately in the card view).
    var badgeHtml = sectionId ? _bbStatusBadgeHtml(sectionId, field.id) : "";
    var labelHtml = '<label class="bb-label" for="' + domId + '">' + _esc(field.label) + badgeHtml + '</label>';

    if (field.type === "select" && Array.isArray(field.options)) {
      var optsHtml = field.options.map(function (opt) {
        var ov = _esc(opt);
        var sel = (opt === value) ? ' selected' : '';
        return '<option value="' + ov + '"' + sel + '>' + (ov || '\u2014 select \u2014') + '</option>';
      }).join("");
      return '<div class="bb-field">' + labelHtml
        + '<select id="' + domId + '" class="bb-select">' + optsHtml + '</select></div>';
    }

    if (field.type === "textarea") {
      return '<div class="bb-field">' + labelHtml
        + '<textarea id="' + domId + '" class="bb-textarea" rows="3" placeholder="' + _esc(field.placeholder || "") + '">' + va + '</textarea></div>';
    }

    var blurAttr = "";
    if (field.inputHelper === "normalizeDob") {
      blurAttr = ' onblur="window.LorevoxBioBuilder._onNormalizeBlur(this,\'dob\')"';
    } else if (field.inputHelper === "normalizeTime") {
      blurAttr = ' onblur="window.LorevoxBioBuilder._onNormalizeBlur(this,\'time\')"';
    } else if (field.inputHelper === "normalizePlace") {
      blurAttr = ' onblur="window.LorevoxBioBuilder._onNormalizeBlur(this,\'place\')"';
    } else if (field.inputHelper === "normalizeDateSafe") {
      blurAttr = ' onblur="window.LorevoxBioBuilder._onNormalizeBlur(this,\'dateSafe\')"';
    }

    var deriveAttr = "";
    if (field.inputHelper === "normalizeDob") {
      deriveAttr = ' data-derive-zodiac="true"';
    }

    var helperHtml = "";
    if (field.helperText) {
      helperHtml = '<div class="bb-helper-text">\u24D8 ' + _esc(field.helperText) + '</div>';
    }

    return '<div class="bb-field">' + labelHtml
      + '<input id="' + domId + '" class="bb-input" type="text" value="' + va
      + '" placeholder="' + _esc(field.placeholder || "") + '"' + blurAttr + deriveAttr + ' />'
      + helperHtml + '</div>';
  }

  function _onNormalizeBlur(inputEl, kind) {
    if (!inputEl) return;
    var raw = inputEl.value;
    var normalized;
    if (kind === "dob") {
      normalized = normalizeDobInput(raw);
      inputEl.value = normalized;
      _tryAutoZodiac(normalized);
    } else if (kind === "time") {
      normalized = normalizeTimeOfBirthInput(raw);
      inputEl.value = normalized;
    } else if (kind === "place") {
      normalized = normalizePlaceInput(raw);
      inputEl.value = normalized;
    } else if (kind === "dateSafe") {
      // Phase Q+: uncertainty-safe date normalization
      normalized = normalizeDateSafe(raw);
      inputEl.value = normalized;
    }
  }

  function _tryAutoZodiac(isoDob) {
    var zodiacEl = _el("bbQ_zodiacSign");
    if (!zodiacEl) return;
    if (zodiacEl.value) return;
    var sign = deriveZodiacFromDob(isoDob);
    if (sign) zodiacEl.value = sign;
  }

  /* ───────────────────────────────────────────────────────────
     QUESTIONNAIRE ACTION HANDLERS
     These are called from bio-builder.js (which owns _activeSection
     and _renderActiveTab).  They receive callbacks for re-rendering.
  ─────────────────────────────────────────────────────────── */

  /* ── Save result banner ──────────────────────────────────────────────
     BUG-BIO-QUESTIONNAIRE-SILENT-SAVE-FAILURE-01.

     Deliberately asymmetric. Success is a quiet, self-dismissing line;
     failure is loud, stays on screen until the next save, and always says
     where the work currently lives. The operator is entering a parent's
     biography from memory and from paper — the cost of a missed failure is
     retyping an afternoon, or never noticing at all. */
  function _reportSaveOutcome(section, pid, onConfirmed) {
    var label = (section && section.label) || "section";
    // `_core` — window.LorevoxBioBuilderModules.core — resolved at the top of
    // this module, the same handle every other function here uses.
    //
    // This first read window.LorevoxBioBuilderCore, which does not exist. The
    // guard below then returned silently, so the banner never rendered and a
    // failed save was invisible AGAIN — the precise defect this function was
    // added to end, reintroduced by the fix for it. Found only because the
    // operator tried the namespace by hand in the console.
    //
    // Hence the loud branch: a reporting channel that fails quietly is worse
    // than none, because it reads as "nothing went wrong".
    if (!_core || typeof _core._qqSaveOutcome !== "function") {
      console.error("[bb-qq] SAVE OUTCOME UNAVAILABLE — cannot confirm whether " +
        label + " reached the server. Treat this save as unconfirmed.");
      try { window.alert("Could not confirm whether \"" + label + "\" saved. " +
        "Check the narrator before entering more."); } catch (e) {}
      return;
    }
    // Ask about THIS save. _qqLastOutcome is a single shared slot, so with two
    // overlapping saves the second replaces the first and a plain read would
    // report a verdict belonging to a different operation — raised in review
    // 2026-09-18. The ticket was taken by _persistDrafts a moment ago; if a
    // newer save has since claimed the slot we are told "superseded" and say
    // nothing, rather than something confident about work we did not do.
    var _ticket = (typeof _core._qqCurrentSaveTicket === "function")
      ? _core._qqCurrentSaveTicket() : undefined;
    var _ask = (typeof _core._qqSaveOutcomeFor === "function")
      ? _core._qqSaveOutcomeFor(pid, _ticket)
      : _core._qqSaveOutcome();
    _ask.then(function (res) {
      if (res && res.outcome === "superseded") {
        console.warn("[bb-qq] save outcome superseded for " + String(pid).slice(0, 8) +
          " — a newer save claimed the slot; not reporting a result for this one.");
        return;
      }
      res = res || { ok: false, outcome: "unknown", message: "Save outcome unknown." };
      var el = document.getElementById("bbSaveStatus");
      if (!el) {
        el = document.createElement("div");
        el.id = "bbSaveStatus";
        el.setAttribute("role", "status");
        el.setAttribute("aria-live", "polite");
        el.style.cssText =
          "position:fixed;left:50%;transform:translateX(-50%);bottom:24px;z-index:99999;" +
          "max-width:min(680px,92vw);padding:12px 16px;border-radius:8px;" +
          "font:14px/1.45 system-ui,sans-serif;box-shadow:0 4px 16px rgba(0,0,0,.28);";
        document.body.appendChild(el);
      }
      if (res.ok && typeof onConfirmed === "function") {
        // The server accepted these answers — or confirmed it already holds
        // them. Either way the stored document now matches what derived
        // state would be built from, so it is safe to build it. This runs
        // BEFORE the banner so that a throw in downstream work cannot leave
        // the operator with no result shown at all.
        try { onConfirmed(); }
        catch (e) { console.error("[bb-qq] downstream work after a confirmed save threw:", e); }
      }
      if (res.ok && _pendingIdCollisions.length) {
        /* The save succeeded and every answer was kept — but two entries
           share one identity, which means a later correction cannot be aimed
           at one of them. That outranks "saved" as the thing to say. */
        _reportEntryIdCollision(section, _pendingIdCollisions);
        _pendingIdCollisions = [];
        return;
      }
      if (res.ok) {
        // A no-op is a success, but it is NOT the same event as a write, and
        // an operator entering a biography needs to tell them apart — "did my
        // edit go in, or did I just resubmit what was already there?". Green
        // for a write, neutral for a no-op, and the revision number in both
        // so it can be read off the screen rather than remembered.
        var wrote = res.outcome !== "nochange";
        el.style.background = wrote ? "#123d1d" : "#1e2633";
        el.style.color      = wrote ? "#d8f5e0" : "#c9d4e4";
        el.style.border     = "1px solid " + (wrote ? "#2f7d4a" : "#3d4d66");
        el.textContent = wrote
          ? (label + " saved. " + (res.message || ""))
          : (label + " — " + (res.message || "no changes."));
        el.hidden = false;
        clearTimeout(el._t);
        // Eight seconds, not four. The operator reported missing the
        // confirmation entirely: "i did not get a chance to see the banner it
        // was too quickly gone". A confirmation nobody reads confirms nothing.
        el._t = setTimeout(function () { el.hidden = true; }, 8000);
      } else {
        // Failure does not time out. A banner that disappears is a banner
        // that can be missed, and being missed is the entire defect.
        el.style.background = "#4a1113";
        el.style.color = "#ffd9dc";
        el.style.border = "1px solid #a3272d";
        // Wording matters here and was wrong once already.
        //
        // This said the answers "are still in this browser and will reappear
        // if you reload". On 2026-09-17 a refused save left six typed values
        // in localStorage; the machine was shut down overnight and they were
        // gone by morning. localStorage is not durable storage — Chrome
        // flushes it lazily, and a clear-on-exit setting discards it outright.
        //
        // Telling an operator their unsaved work is safe, when the only copy
        // is in a browser that has not promised to keep it, is how somebody
        // closes the laptop on an afternoon of a parent's history. Say what
        // is true: it is held here for now, and it is not backed up.
        el.textContent = "NOT SAVED — " + label + ". " + (res.message || "") +
          " Your answers are held in this browser only and are NOT backed up — " +
          "do not close the browser or shut down until this saves. For anything " +
          "long, keep a copy outside Lorevox until it does.";
        el.hidden = false;
        clearTimeout(el._t);
        console.error("[bb-qq] save failed for " + String(pid).slice(0, 8) +
          " outcome=" + res.outcome, res);
      }
    });
  }

  /* A refusal the operator can see. BUG-BIO-QUESTIONNAIRE-STALE-FORM-CROSS-
     WRITE-01: silently declining would be its own defect — the form would sit
     there looking saved, which is the failure this whole repair exists to
     end. Reuses the banner element so the message cannot be missed. */
  function _reportStaleForm(section, renderedFor, activePid) {
    var label = (section && section.label) || "section";
    var el = document.getElementById("bbSaveStatus");
    if (!el) {
      el = document.createElement("div");
      el.id = "bbSaveStatus";
      el.setAttribute("role", "status");
      el.setAttribute("aria-live", "polite");
      el.style.cssText =
        "position:fixed;left:50%;transform:translateX(-50%);bottom:24px;z-index:99999;" +
        "max-width:min(680px,92vw);padding:12px 16px;border-radius:8px;" +
        "font:14px/1.45 system-ui,sans-serif;box-shadow:0 4px 16px rgba(0,0,0,.28);";
      document.body.appendChild(el);
    }
    el.style.background = "#4a1113";
    el.style.color = "#ffd9dc";
    el.style.border = "1px solid #a3272d";
    el.textContent = "NOT SAVED — " + label + ". This form was opened for a " +
      "different narrator than the one now active, so saving it would file " +
      "one person's answers under another's name. Reopen the section for the " +
      "current narrator. Nothing was written.";
    el.hidden = false;
    clearTimeout(el._t);
  }

  /* A duplicated entry id, shown to the operator and not dismissed.
     WO-02. The save succeeded and both people kept their answers — but two
     entries share one identity, so a later correction cannot be aimed at one
     of them reliably. That is worth interrupting for. */
  var _pendingIdCollisions = [];

  function _reportEntryIdCollision(section, ids) {
    var label = (section && section.label) || "section";
    var el = document.getElementById("bbSaveStatus");
    if (!el) {
      el = document.createElement("div");
      el.id = "bbSaveStatus";
      el.setAttribute("role", "status");
      el.setAttribute("aria-live", "polite");
      el.style.cssText =
        "position:fixed;left:50%;transform:translateX(-50%);bottom:24px;z-index:99999;" +
        "max-width:min(680px,92vw);padding:12px 16px;border-radius:8px;" +
        "font:14px/1.45 system-ui,sans-serif;box-shadow:0 4px 16px rgba(0,0,0,.28);";
      document.body.appendChild(el);
    }
    el.style.background = "#4a3a11";
    el.style.color = "#ffeccc";
    el.style.border = "1px solid #a3782b";
    el.textContent = "Saved, but " + label + " has two entries sharing one " +
      "identity (" + ids.join(", ") + "). Every answer was kept and nothing was " +
      "merged — but until one of them is given a separate identity, a later " +
      "correction cannot be aimed at just one of these people.";
    el.hidden = false;
    clearTimeout(el._t);
  }

  function _saveSection(sectionId, closeCallback) {
    var section = SECTIONS.find(function (s) { return s.id === sectionId; });
    if (!section) return;
    var bb = _bb(); if (!bb) return;

    // WO-INTAKE-IDENTITY-01: restore before migrate — symmetric with _addRepeatEntry
    // Covers code paths that invoke save without a prior render pass.
    var pid = _currentPersonId();

    /* BUG-BIO-QUESTIONNAIRE-STALE-FORM-CROSS-WRITE-01.
       Refuse to harvest a form that was rendered for a different narrator.
       Everything below reads the DOM by id and writes it under `pid`; if the
       narrator changed after this form was drawn, those values belong to
       somebody else. The existing guard cannot catch it — it compares the pid
       argument with bb.personId, and after a switch both are the NEW narrator.
       Absent stamp means a legacy or programmatic call site, which is allowed
       through rather than broken. */
    var _stamp = _el("bbQ__renderedFor");
    if (_stamp && pid && _stamp.value && _stamp.value !== pid) {
      console.error("[bb-qq] SAVE REFUSED: this form was rendered for narrator " +
        _stamp.value.slice(0, 8) + " but the active narrator is " + pid.slice(0, 8) +
        ". Reopen the section for the current narrator before saving.");
      _reportStaleForm(section, _stamp.value, pid);
      return;
    }

    if (pid) _restoreQuestionnaire(pid);

    // Phase 1.3: Step 1 — read DOM values; Step 2 — write into canonical bb.questionnaire
    // BUG-BIO-QUESTIONNAIRE-LOSSY-ROUNDTRIP-01, second mechanism (2026-09-17).
    //
    // These two branches used to build `var obj = {}` and fill it ONLY from
    // section.fields, then assign that over the stored entry. Any stored field
    // the rendered form does not declare was therefore DELETED by the act of
    // saving — the spec's own invariant ("a surface that rebuilds an object
    // from a rendered view and writes it back inherits the read path's
    // omissions as deletions"), reached without the bio_questionnaire_view
    // projection being involved at all.
    //
    // It fired on real family data. The since-retired three-section form's
    // parents section declared six fields; the full form declares eleven.
    // With that form as the default, one save of Janice's parents section destroyed ten stored
    // values across her two parents — birthDate, birthPlace, deceased,
    // notableLifeEvents and notes, including several hundred words of family
    // history that had been typed in by hand. Recovered from a snapshot taken
    // an hour earlier; there was no other copy at full length.
    //
    // The fix: start from what is already stored and let the rendered fields
    // overwrite only themselves. A form can only edit what it shows.
    //
    // `getSectionData` is the one read path for a section. It once carried a
    // fallback to a legacy container that a since-removed migration wrote to;
    // that container and its migration are gone (WO-01). Keeping the single
    // accessor means the next storage change happens in one place.
    if (section.repeatable) {
      var stored = getSectionData(bb.questionnaire, sectionId);
      var existing = Array.isArray(stored) ? stored : (stored ? [stored] : [{}]);

      // BUG-BIO-QUESTIONNAIRE-SECOND-ENTRY-DROPPED-01 (2026-09-18)
      //
      // This mapped over `existing` — the STORED entries — and read the DOM
      // by index. So the save could only ever see as many entries as storage
      // already held. Enter a mother, save, add a father, save: the father's
      // fields are on screen, filled, and `existing.length === 1`, so index 1
      // is never visited. The entry is not rejected or reported; it is simply
      // never looked at.
      //
      // Found live on ZZ WALKTHROUGH 20260917 — "why is the dad missing i did
      // mom and then dad and then save parents only one is there".
      //
      // A form can only edit what it shows. It must also SAVE what it shows.
      // Count the entries actually rendered and iterate those; storage is the
      // base to merge onto, not the limit of what may be read.
      var rendered = 0;
      if (section.fields.length) {
        var probe = section.fields[0].id;
        while (_el("bbQ_" + rendered + "_" + probe)) rendered++;
      }
      var count = Math.max(existing.length, rendered);

      /* ── WO-02: match the rendered entry to the stored one by ID ────────
         This used `existing[i]` — the stored entry at the same ordinal. That
         is safe only while the DOM and storage agree about order, which they
         do the instant after a render and not necessarily a moment later. If
         the stored array changes underneath an open form — another tab, a
         restore, any future reorder control — then index 1 on screen and
         index 1 in storage are two different people, and the save writes one
         person's answers onto the other.

         An id carried in the entry does not fix that by existing. It fixes it
         by being what the merge matches on. So: find the stored entry whose
         id equals the one this rendered entry carries, and merge onto THAT,
         wherever it now sits.

         Entries with no id fall back to the ordinal — that is every entry
         written before this work order, and the fallback is what lets them
         keep their values while gaining an id below. */
      /* A DUPLICATED ID IS AN INTEGRITY ERROR, NOT A PUZZLE TO SOLVE.

         An earlier version healed it: the first row kept the id, the second
         was minted a fresh one. That is the system deciding, unprompted, that
         one of two real people is now somebody else. If a correction had
         already been made against that id, it would silently attach to
         whichever row happened to be first.

         So: an id that appears more than once — among the rendered rows or
         among the stored entries — is UNUSABLE for matching. Those rows fall
         back to their ordinal, which is what the operator is looking at, both
         entries keep every answer they have, neither id is changed, and the
         collision is reported. Resolving it is a person's decision. */
      var seen = Object.create(null), ambiguous = Object.create(null);
      function _noteId(id) {
        if (!id) return;
        if (seen[id]) ambiguous[id] = true;
        seen[id] = true;
      }
      for (var e = 0; e < existing.length; e++) {
        var ex = existing[e];
        if (ex && typeof ex === "object") _noteId(ex[ENTRY_ID_KEY]);
      }
      /* One detector, over the stored entries. A second pass over the
         rendered rows was written here and removed: the form is rendered
         FROM these same entries, so a duplicate on screen is always a
         duplicate in memory, and the extra pass could not see anything the
         first missed. It did, however, keep a mutation of the real detector
         from failing anything — two checks of the same fact, one of them
         invisible. */

      var byId = Object.create(null);
      for (var e2 = 0; e2 < existing.length; e2++) {
        var ex2 = existing[e2];
        if (ex2 && typeof ex2 === "object" && ex2[ENTRY_ID_KEY] && !ambiguous[ex2[ENTRY_ID_KEY]]) {
          byId[ex2[ENTRY_ID_KEY]] = ex2;
        }
      }
      var claimed = Object.create(null);
      var collisions = Object.keys(ambiguous);

      var out = [];
      for (var i = 0; i < count; i++) {
        var idEl = _el("bbQ_" + i + "__entryId");
        var domId = idEl ? (idEl.value || "") : "";
        var prev = null;
        if (domId && ambiguous[domId]) {
          /* Unusable id. Fall back to the ordinal — what the operator is
             looking at — which also carries the stored entry's own id
             forward untouched. The first version let this fall through to
             no match at all, so BOTH entries were minted fresh ids: the
             renaming this guard exists to prevent, caused by the guard. */
          prev = existing[i];
        } else if (domId && byId[domId] && !claimed[domId]) {
          prev = byId[domId];
          claimed[domId] = true;
        } else if (!domId) {
          prev = existing[i];
        }
        var obj = (prev && typeof prev === "object") ? Object.assign({}, prev) : {};
        /* eslint-disable no-loop-func */
        (function (idx, target) {
          section.fields.forEach(function (f) {
            var el = _el("bbQ_" + idx + "_" + f.id);
            if (el) target[f.id] = el.value || "";
          });
        })(i, obj);
        /* eslint-enable no-loop-func */

        /* WO-02 decisions B and C, in one line.

           MINT ONLY HERE — in the save path, never on render and never on
           open. Viewing a family record must not write to it.

           AND ONLY FOR AN ENTRY THAT HOLDS AN ANSWER. flatten_document does
           not skip bookkeeping keys, so an id is a populated leaf: giving one
           to a blank row would make the server store a person whose single
           recorded fact is an identifier — BUG-BIO-QUESTIONNAIRE-DEFAULT-AS-
           ASSERTION-01 arriving by a new road. Withholding the id is the
           whole guard. A contentless entry stays `{}`, flattens to nothing,
           and is not stored.

           The blank row is deliberately KEPT in memory so it keeps its place
           on screen — the operator clicked "add another" and expects the row
           to still be there. The first version of this dropped it and the
           row disappeared from under them.

           An entry that already has an id keeps it, unchanged, for life. */
        if (!obj[ENTRY_ID_KEY] && _hasEntryContent(obj)) {
          obj[ENTRY_ID_KEY] = "e_" + _uid();
        }

        out.push(obj);
      }
      bb.questionnaire[sectionId] = out;

      /* Report the collision. The save still happens — both people keep
         their answers, which is the priority — but nobody is told the
         record is ambiguous unless we say so, and an ambiguous id means a
         later correction cannot be aimed reliably. */
      if (collisions.length) {
        console.error("[bb-qq] DUPLICATE ENTRY IDS in " + sectionId + ": " +
          collisions.join(", ") + ". Both entries were preserved and matched " +
          "by position for this save. Neither id was changed and no entries " +
          "were merged — resolving which person owns the id is a decision for " +
          "a person, not this code.");
        _pendingIdCollisions = collisions;
      } else {
        _pendingIdCollisions = [];
      }
    } else {
      var storedObj = getSectionData(bb.questionnaire, sectionId);
      var obj = (storedObj && typeof storedObj === "object" && !Array.isArray(storedObj))
        ? Object.assign({}, storedObj) : {};
      section.fields.forEach(function (f) {
        var el = _el("bbQ_" + f.id);
        if (el) obj[f.id] = el.value || "";
      });
      bb.questionnaire[sectionId] = obj;
    }

    // Phase 1.3: Step 3 — persist narrator-scoped state to localStorage AFTER in-memory update
    var pid = _currentPersonId();
    if (pid) {
      // BUG-BIO-QUESTIONNAIRE-GET-CLOBBERS-EDITS-01.
      //
      // The DOM values have just been committed into bb.questionnaire above.
      // Say so, before anything async can start: a server GET landing from
      // here on must not replace this document with canonical and drop what
      // was typed. Records that already HAVE a server questionnaire — which
      // is every real narrator — take that branch on every restore.
      if (_core && typeof _core._markQuestionnaireEdited === "function") {
        _core._markQuestionnaireEdited(pid);
      }
      /* WO-03A — this save goes to the human-entry route, and names the
         section it actually saved.

         The section list is the important half. This form sends the WHOLE
         document on every save, so without a scope the operator's
         authority would be stamped on every path that happened to move in
         the same request — a draft mirror, a prefill, an identity sync —
         crediting them with answers they never gave. The server stamps
         only changed paths within the sections named here. */
      _persistDrafts(pid, { sections: [sectionId] });
      // BUG-BIO-QUESTIONNAIRE-SILENT-SAVE-FAILURE-01.
      //
      // This line used to be the whole of "saving". _persistDrafts returned
      // nothing, the PUT was fire-and-forget, and the function carried on to
      // re-render — so a refusal, a 409 and a dead server all looked exactly
      // like success. On 2026-09-17 a live narrator's six typed values stayed
      // in localStorage while the form showed them saved, and the only trace
      // was a console warning nobody was watching.
      //
      // Nothing may tell the operator this was saved until the server says so.
      _reportSaveOutcome(section, pid, function onConfirmed() {
        _afterConfirmedSave(section, sectionId, pid);
      });
    }

    // Phase 2.5: debug snapshot after save
    _qqDebugSnapshot("save_section:" + sectionId, pid, bb);

    // Phase 1.3: Step 4 — rerender/update badges from canonical state.
    // Rendering only; it reads canonical state and paints. Everything that
    // WRITES derived or authoritative state now waits for confirmation, in
    // _afterConfirmedSave below.
    if (closeCallback) closeCallback();
  }

  /* ── Derived state, only after the server has accepted the answers ────
     WO-BIO-BUILDER-SAVE-INTEGRITY-AUDIT-01, section 1.

     These three used to run immediately after _persistDrafts, without
     awaiting it. A refused or failed PUT therefore left:

       - candidates extracted from answers the database never accepted
       - projection fields marked human-edited on the strength of a write
         that did not happen
       - a family graph showing a relative who is not stored

     The marks are the dangerous part. A candidate that later reads as
     established biography is how an unsaved answer becomes an apparent fact,
     and a narrator built on it would speak with confidence about something
     nobody ever saved. That is the failure mode this whole repair exists to
     prevent, arriving one layer downstream.

     A confirmed server save is the boundary. A no-op counts as confirmed:
     the stored document is exactly what these would be derived from. */
  function _afterConfirmedSave(section, sectionId, pid) {
    var bb = _bb(); if (!bb) return;

    _extractQuestionnaireCandidates(sectionId);

    // v8: mark saved fields as human-edited in projection layer
    if (window.LorevoxProjectionSync && window.LorevoxProjectionMap) {
      if (section.repeatable) {
        var entries = bb.questionnaire[sectionId] || [];
        entries.forEach(function (entry, idx) {
          section.fields.forEach(function (f) {
            var val = entry[f.id];
            if (val && String(val).trim() !== "") {
              var path = window.LorevoxProjectionMap.buildRepeatablePath(sectionId, idx, f.id);
              window.LorevoxProjectionSync.markHumanEdit(path, val);
            }
          });
        });
      } else {
        var data = bb.questionnaire[sectionId] || {};
        section.fields.forEach(function (f) {
          var val = data[f.id];
          if (val && String(val).trim() !== "") {
            window.LorevoxProjectionSync.markHumanEdit(sectionId + "." + f.id, val);
          }
        });
      }
    }

    // Phase Q.1: Sync graph from questionnaire after save
    var graphMod = window.LorevoxBioBuilderModules && window.LorevoxBioBuilderModules.graph;
    if (graphMod && typeof graphMod.fullSync === "function") {
      graphMod.fullSync();
    }
  }

  function _addRepeatEntry(sectionId, renderCallback) {
    var bb = _bb(); if (!bb) return;
    var pid = _currentPersonId();
    var section = SECTIONS.find(function (s) { return s.id === sectionId; });

    // Phase 2.2 Step 1: restore canonical questionnaire state
    if (pid) _restoreQuestionnaire(pid);


    // Phase 2.3: guard — ensure repeatable array exists
    if (!Array.isArray(bb.questionnaire[sectionId])) {
      bb.questionnaire[sectionId] = bb.questionnaire[sectionId] ? [bb.questionnaire[sectionId]] : [{}];
    }

    // Phase 2.2 Step 2: commit current DOM edits into canonical state
    //
    // BUG-BIO-QUESTIONNAIRE-SECOND-ENTRY-DROPPED-01: same shape as the save
    // path — iterating the stored array means a rendered entry beyond its
    // length is never read. Adding a third parent after two are stored would
    // have dropped whatever was typed into the second while the button was
    // clicked. Count what is on screen.
    if (section) {
      var entries = bb.questionnaire[sectionId];
      var renderedN = 0;
      if (section.fields.length) {
        var probeId = section.fields[0].id;
        while (_el("bbQ_" + renderedN + "_" + probeId)) renderedN++;
      }
      var total = Math.max(entries.length, renderedN);

      /* WO-02 — match by id here too, not by ordinal. This path commits the
         operator's in-progress typing before appending a blank entry, so it
         writes DOM values onto stored entries exactly as the save does, and
         carries exactly the same risk of putting one person's answers on
         another if the stored order moved under the open form. Same rule:
         id first, ordinal only for an entry that has none yet. */
      var idIndex = Object.create(null);
      for (var q = 0; q < entries.length; q++) {
        var en = entries[q];
        if (en && typeof en === "object" && en[ENTRY_ID_KEY]) idIndex[en[ENTRY_ID_KEY]] = q;
      }
      for (var ei = 0; ei < total; ei++) {
        var idNode = _el("bbQ_" + ei + "__entryId");
        var domEid = idNode ? (idNode.value || "") : "";
        var target = (domEid && idIndex[domEid] !== undefined) ? idIndex[domEid] : ei;
        if (!entries[target]) entries[target] = {};
        /* eslint-disable no-loop-func */
        (function (idx, slot) {
          section.fields.forEach(function (f) {
            var el = _el("bbQ_" + idx + "_" + f.id);
            if (el) entries[slot][f.id] = el.value || "";
          });
        })(ei, target);
        /* eslint-enable no-loop-func */
      }
      // Declare the edits BEFORE the async GET started by the restore above
      // can land. Without this, _qqDirty is false — the last successful save
      // cleared it — and the adopt branch replaces this document with the
      // server's, discarding a half-typed entry while it is still on screen.
      if (pid && _core && typeof _core._markQuestionnaireEdited === "function") {
        _core._markQuestionnaireEdited(pid);
      }
    }

    /* WO-03A — "+ Add another" is human entry too, and had to be.
       ────────────────────────────────────────────────────────────
       The design said the operator route would have exactly one caller.
       Tracing the no-op rule showed that leaving this one out opens a
       hole rather than closing one:

         the operator fills in the mother
         clicks "+ Add another parent"  -> this persists her answers
         clicks Save                    -> nothing CHANGED, so it is a
                                           no-op, and a no-op writes no
                                           provenance

       The mother's answers would then stay unclassified forever, having
       been entered by a person at a keyboard through the Bio Builder
       form. The scope rule still applies — one named section — so this
       claims no more than the save below it would have. */
    var _entry = { sections: [sectionId] };

    // Phase 2.2 Step 3: persist canonical state (with committed DOM edits)
    if (pid) _persistDrafts(pid, _entry);

    // Phase 2.2 Step 4: append empty repeatable entry to canonical state
    bb.questionnaire[sectionId].push({});

    // Phase 2.2 Step 5: persist again (with new entry)
    if (pid) _persistDrafts(pid, _entry);

    // Phase 2.5: debug snapshot after add
    _qqDebugSnapshot("add_repeat:" + sectionId, pid, bb);

    // Phase 2.2 Step 6: rerender from canonical state
    if (renderCallback) renderCallback();
  }

  /* ───────────────────────────────────────────────────────────
     EXPORT MODULE
  ─────────────────────────────────────────────────────────── */

  window.LorevoxBioBuilderModules.questionnaire = {
    // Section definitions
    SECTIONS:                      SECTIONS,

    // Rendering
    _renderQuestionnaireTab:       _renderQuestionnaireTab,
    _renderSectionDetail:          _renderSectionDetail,
    _fieldHtml:                    _fieldHtml,
    _sectionFillCount:             _sectionFillCount,

    // Actions
    _saveSection:                  _saveSection,
    _addRepeatEntry:               _addRepeatEntry,
    _extractQuestionnaireCandidates: _extractQuestionnaireCandidates,

    // Normalization
    normalizeDobInput:             normalizeDobInput,
    normalizeTimeOfBirthInput:     normalizeTimeOfBirthInput,
    normalizePlaceInput:           normalizePlaceInput,
    normalizeDateSafe:             normalizeDateSafe,
    normalizeBirthOrder:           normalizeBirthOrder,
    deriveZodiacFromDob:           deriveZodiacFromDob,
    buildCanonicalBasicsFromBioBuilder: buildCanonicalBasicsFromBioBuilder,
    _onNormalizeBlur:              _onNormalizeBlur,

    // WO-INTAKE-IDENTITY-01 helpers
    getSectionData:                getSectionData,

    // Hydration
    _hydrateQuestionnaireFromProfile: _hydrateQuestionnaireFromProfile,

    // Candidate helpers (used by questionnaire extraction)
    _candidateExists:              _candidateExists,
    _relCandidateExists:           _relCandidateExists,
    _memCandidateExists:           _memCandidateExists
  };

})();
