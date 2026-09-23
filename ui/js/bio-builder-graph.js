/* ═══════════════════════════════════════════════════════════════
   bio-builder-graph.js — Phase Q.1: Relationship Graph Layer
   Lorevox 9.0

   The canonical relationship graph that sits UNDER the questionnaire
   and family tree.  The questionnaire is an input/editor surface;
   this graph is the truth model.

   Owns:
     - In-memory graph state: bb.graph = { persons: {}, relationships: {} }
     - Questionnaire → graph sync (writes graph records from QQ sections)
     - Profile kinship → graph sync
     - Graph → backend persistence (backend-first, same pattern as QQ)
     - Graph → family tree seeding bridge

   Relationship types:
     parent, child, sibling, spouse, partner, former_spouse,
     grandparent, grandchild, guardian, chosen_family, other

   Subtypes:
     biological, adoptive, step, half, foster, legal_guardian,
     spouse, former_spouse, partner, chosen_family, domestic_partner,
     life_partner, common_law

   Exposes: window.LorevoxBioBuilderModules.graph
   Load order: AFTER bio-builder-core.js, BEFORE bio-builder-family-tree.js
═══════════════════════════════════════════════════════════════ */

(function () {
  "use strict";

  var coreMod = window.LorevoxBioBuilderModules && window.LorevoxBioBuilderModules.core;
  if (!coreMod) {
    console.error("[bb-graph] core module not loaded — graph layer disabled");
    return;
  }

  var _bb   = coreMod._bb;
  var _uid  = coreMod._uid;

  /* ───────────────────────────────────────────────────────────
     CONSTANTS
  ─────────────────────────────────────────────────────────── */

  var RELATIONSHIP_TYPES = [
    "parent", "child", "sibling", "spouse", "partner",
    "former_spouse", "grandparent", "grandchild",
    "guardian", "chosen_family", "other"
  ];

  var SUBTYPES = [
    "biological", "adoptive", "step", "half", "foster",
    "legal_guardian", "spouse", "former_spouse", "partner",
    "chosen_family", "domestic_partner", "life_partner", "common_law"
  ];

  // Map questionnaire relationshipType labels → graph subtypes
  var _LABEL_TO_SUBTYPE = {
    "Spouse":           "spouse",
    "Partner":          "partner",
    "Former Spouse":    "former_spouse",
    "Domestic Partner": "domestic_partner",
    "Life Partner":     "life_partner",
    "Common-Law Spouse":"common_law",
    "Chosen Family":    "chosen_family",
    "Other":            ""
  };

  // Map questionnaire parent/sibling relation labels → subtypes
  var _RELATION_TO_SUBTYPE = {
    "Father":           "biological",
    "Mother":           "biological",
    "Parent":           "biological",
    "Stepfather":       "step",
    "Stepmother":       "step",
    "Step-Parent":      "step",
    "Adoptive Father":  "adoptive",
    "Adoptive Mother":  "adoptive",
    "Foster Father":    "foster",
    "Foster Mother":    "foster",
    "Legal Guardian":   "legal_guardian",
    "Brother":          "biological",
    "Sister":           "biological",
    "Sibling":          "biological",
    "Half-Brother":     "half",
    "Half-Sister":      "half",
    "Stepbrother":      "step",
    "Stepsister":       "step",
    "Adopted Brother":  "adoptive",
    "Adopted Sister":   "adoptive"
  };

  /* ───────────────────────────────────────────────────────────
     GRAPH STATE HELPERS
  ─────────────────────────────────────────────────────────── */

  /** Ensure bb.graph exists with proper structure */
  function _ensureGraph() {
    var bb = _bb(); if (!bb) return null;
    if (!bb.graph) {
      bb.graph = { persons: {}, relationships: {} };
    }
    return bb.graph;
  }

  /** Generate a stable ID for a person based on narrator + name */
  function _stablePersonId(narratorId, name) {
    // Simple hash: narrator prefix + name lowercase
    var key = (narratorId || "").slice(0, 8) + ":" + (name || "").toLowerCase().trim();
    // Use a deterministic approach for idempotent upserts
    var hash = 0;
    for (var i = 0; i < key.length; i++) {
      hash = ((hash << 5) - hash + key.charCodeAt(i)) | 0;
    }
    return "gp_" + Math.abs(hash).toString(36) + "_" + key.replace(/[^a-z0-9]/g, "").slice(0, 16);
  }

  /** Generate a stable ID for a relationship */
  function _stableRelId(fromId, toId, relType) {
    return "gr_" + (fromId || "").slice(0, 12) + "_" + (toId || "").slice(0, 12) + "_" + (relType || "");
  }

  /* ───────────────────────────────────────────────────────────
     GRAPH PERSON OPERATIONS
  ─────────────────────────────────────────────────────────── */

  /* ── IDENTITY RESOLUTION ───────────────────────────────────────────
     WO-BIO-VIEW-SAFETY-01 (2026-09-21).

     A PERSON'S NAME CAN CHANGE. THEIR IDENTITY MUST NOT CHANGE WITH IT.

     `_stablePersonId` hashes the narrator id and the NAME, so correcting a
     spelling minted a different id. While the sync still cleared and
     rebuilt, that was invisible: the old record was deleted and a new one
     created. Now that a routine sync deletes nothing, the same correction
     left the misspelling standing and added a second person. Measured on a
     fictional narrator: "Sigrid Lindquist" corrected to "Sigrid Lindqvist"
     produced BOTH.

     The questionnaire already mints a stable per-entry id (`_entryId`,
     WO-02) that survives edits, reorders and reloads. That is the identity
     to resolve through. Three rules, and EXISTING GRAPH IDS ARE PRESERVED
     throughout — a record keeps the id it has, gaining the entry id as a
     resolution key in `meta`. Relationship ids are built from person ids
     (`_stableRelId`), so preserving person ids keeps every relationship
     intact without touching the relationship code.

       1. The entry id is already on a record  -> update THAT record.
          A later rename updates the same person.
       2. The entry id is new, and the name still resolves to an existing
          unclaimed record -> ADOPT it: update in place, keep its id, write
          the entry id onto it.
       3. Otherwise -> create a new record, carrying the entry id.

     Rule 2 is deliberately narrow. It adopts only an UNAMBIGUOUS match:
     a record not already claimed by a different entry in this same sync.
     Two entries sharing a name therefore do not fight over one record.

     WHAT THIS DOES NOT DO, on purpose. A legacy entry with no stored entry
     id that is RENAMED in the same save cannot be matched — the entry id
     is new and the name lookup uses the new name. Both records are then
     kept and flagged for reconciliation. Guessing by position is the one
     thing not attempted: this codebase already has a reorder test proving
     position is not identity. */

  /* Ids claimed during the current sync pass, so rule 2 cannot adopt a
     record another entry has already taken. Null outside a sync. */
  var _syncClaimedIds = null;

  function _resolvePersonId(g, opts, name) {
    // Rule 1 — this entry already owns a record.
    if (opts.entryId) {
      var ids = Object.keys(g.persons);
      for (var i = 0; i < ids.length; i++) {
        var p = g.persons[ids[i]];
        if (p && p.meta && p.meta.entryId === opts.entryId) return ids[i];
      }
    }

    var nameId = _stablePersonId(opts.narratorId, name);

    // No entry id: legacy behaviour, unchanged.
    if (!opts.entryId) return nameId;

    var candidate    = g.persons[nameId];
    var claimed      = !!(_syncClaimedIds && _syncClaimedIds[nameId]);
    var heldByAnother = !!(candidate && candidate.meta && candidate.meta.entryId &&
                           candidate.meta.entryId !== opts.entryId);

    // Rule 2 — adopt an UNAMBIGUOUS match, or take a free id.
    if (!claimed && !heldByAnother) {
      if (candidate) {
        console.log("[bb-graph] adopting existing record " + nameId.slice(0, 18) +
          " for entry " + String(opts.entryId).slice(0, 12) +
          " — id and relationships preserved");
      }
      return nameId;
    }

    /* Rule 3 — the name-derived id belongs to somebody else, so this entry
       gets one of its own.

       Falling through to `nameId` here was a defect, caught by the
       same-name case: two entries with distinct entry ids and one shared
       name both resolved to the same id, and the second silently
       overwrote the first. Two grandmothers called Sigrid Lindqvist became
       one person.

       Derived from the name AND the entry id so it is deterministic across
       syncs; rule 1 finds it by entry id from then on. */
    return _stablePersonId(opts.narratorId, name + "\u001f" + opts.entryId);
  }

  /* EXPLICIT REMOVAL — the half of the trade in syncFromQuestionnaire that
     was owed. A routine sync never deletes; an operator's deliberate removal
     of an entry does, and it must STAY removed: not re-added by a later sync
     from a stale browser draft that still carries the entry. So a removal
     leaves a tombstone keyed by entry id, and upsertPerson refuses to
     resurrect a tombstoned entry within this graph's lifetime.

     The tombstone lives in memory and in the persisted graph (the person is
     gone from the PUT, so a later graph GET cannot bring them back). It does
     NOT reach the questionnaire document on the server: the PUT route has
     no `removals` field yet (questionnaire.py:42-66), although
     merge_whole_document already accepts one. Until that field and a UI
     control land (Batch C), a page reload re-hydrates the entry from the
     questionnaire and the graph will show it again. Stated so nobody reads
     this as "delete works end to end". */
  /* Yes / No / not said. A questionnaire field that is ABSENT is not "No":
     mapping it to `false` marked every relative with an unanswered deceased
     field as explicitly living, and then a restore merge could not tell an
     operator's deliberate "No" from nobody having said anything. Returns
     true, false, or undefined — and undefined means "leave it alone". */
  function _triState(v) {
    if (v === true) return true;
    if (v === false) return false;
    var t = String(v === undefined || v === null ? "" : v).trim().toLowerCase();
    if (t === "yes" || t === "true") return true;
    if (t === "no" || t === "false") return false;
    return undefined;
  }

  function _tombstones(g) {
    if (!g._removedEntryIds) g._removedEntryIds = {};
    return g._removedEntryIds;
  }

  function upsertPerson(opts) {
    var g = _ensureGraph(); if (!g) return null;
    if (opts.entryId && _tombstones(g)[opts.entryId]) {
      /* Detached, not stored, and recognisable — callers dereference `.id`
         unconditionally, so null here would throw mid-sync. */
      return { id: "tombstoned:" + opts.entryId, _tombstoned: true,
               displayName: "", meta: { entryId: opts.entryId } };
    }
    var name = [opts.firstName, opts.middleName, opts.lastName].filter(Boolean).join(" ");
    var id = opts.id || _resolvePersonId(g, opts, name);
    if (_syncClaimedIds) _syncClaimedIds[id] = true;
    /* Record WHICH FIELDS this write actually supplied, not just that the
       record was touched. A pending restore must not overwrite them — and
       must still fill every field this write did not supply. A boolean is
       supplied when it is defined, so an explicit false (a deliberate "No")
       counts; an empty string is not a value. */
    var _t = _touchedSinceRestore[id] || (_touchedSinceRestore[id] = {});
    Object.keys(opts).forEach(function (k) {
      var v = opts[k];
      if (k === "id" || k === "entryId" || k === "narratorId") return;
      if (typeof v === "boolean" || (v !== undefined && v !== null && v !== "")) _t[k] = true;
    });

    var existing = g.persons[id] || {};
    g.persons[id] = {
      id:           id,
      narratorId:   opts.narratorId || existing.narratorId || "",
      displayName:  name || opts.displayName || existing.displayName || "",
      firstName:    opts.firstName   || existing.firstName   || "",
      middleName:   opts.middleName  || existing.middleName  || "",
      lastName:     opts.lastName    || existing.lastName     || "",
      maidenName:   opts.maidenName  || existing.maidenName   || "",
      birthDate:    opts.birthDate   || existing.birthDate    || "",
      birthPlace:   opts.birthPlace  || existing.birthPlace   || "",
      occupation:   opts.occupation  || existing.occupation   || "",
      deceased:     opts.deceased !== undefined ? !!opts.deceased : (existing.deceased || false),
      isNarrator:   opts.isNarrator !== undefined ? !!opts.isNarrator : (existing.isNarrator || false),
      source:       opts.source      || existing.source       || "manual",
      provenance:   opts.provenance  || existing.provenance   || "",
      confidence:   opts.confidence !== undefined ? opts.confidence : (existing.confidence || 1.0),
      /* meta carries the entry id, which is the resolution key. Merged
         rather than replaced: an adopted legacy record keeps whatever meta
         it had and GAINS the entry id, and a record that already has one
         never loses it to a caller that forgot to pass it. */
      meta:         (function () {
        var m = Object.assign({}, existing.meta || {}, opts.meta || {});
        if (opts.entryId) m.entryId = opts.entryId;
        else if (existing.meta && existing.meta.entryId) m.entryId = existing.meta.entryId;
        return m;
      })()
    };
    return g.persons[id];
  }

  function removePerson(personId) {
    var g = _ensureGraph(); if (!g) return;
    var p = g.persons[personId];
    if (p && p.meta && p.meta.entryId) _tombstones(g)[p.meta.entryId] = true;
    delete g.persons[personId];
    // Remove any edges referencing this person
    Object.keys(g.relationships).forEach(function (rid) {
      var r = g.relationships[rid];
      if (r.fromPersonId === personId || r.toPersonId === personId) {
        delete g.relationships[rid];
      }
    });
  }

  /* The operator removed a questionnaire ENTRY; find the person it resolved
     to and remove them, edges and all. Returns the graph id removed, or null
     when nothing carried that entry id (already gone, or never synced). The
     tombstone is written either way, so a stale draft cannot bring the entry
     back on the next sync. */
  function removeByEntryId(entryId) {
    var g = _ensureGraph(); if (!g || !entryId) return null;
    _tombstones(g)[entryId] = true;
    var hit = Object.keys(g.persons).find(function (id) {
      var m = g.persons[id].meta;
      return m && m.entryId === entryId;
    });
    if (hit) removePerson(hit);
    return hit || null;
  }

  function findPersonByName(name) {
    var g = _ensureGraph(); if (!g) return null;
    var needle = (name || "").toLowerCase().trim();
    if (!needle) return null;
    var persons = Object.values(g.persons);
    for (var i = 0; i < persons.length; i++) {
      if ((persons[i].displayName || "").toLowerCase().trim() === needle) return persons[i];
    }
    return null;
  }

  /* ───────────────────────────────────────────────────────────
     GRAPH RELATIONSHIP OPERATIONS
  ─────────────────────────────────────────────────────────── */

  /**
   * Phase Q.2: Detect impossible lineage cycles.
   * Returns true if adding an edge of relType from→to would create
   * a direct parent-child cycle (A is both parent and child of B).
   */
  function _wouldCreateCycle(g, fromId, toId, relType) {
    if (!g || !fromId || !toId) return false;
    // Self-loop: a person cannot be their own parent or child
    if (fromId === toId && (relType === "parent" || relType === "child")) return true;
    // Only check lineage-sensitive types
    if (relType !== "parent" && relType !== "child") return false;

    var rels = Object.values(g.relationships);
    if (relType === "parent") {
      // Adding fromId as parent of toId — check if toId is already a parent of fromId
      var reverse = rels.some(function (r) {
        return r.relationshipType === "parent" && r.fromPersonId === toId && r.toPersonId === fromId;
      });
      if (reverse) return true;
      // Also check child direction: is fromId already a child of toId?
      var childReverse = rels.some(function (r) {
        return r.relationshipType === "child" && r.fromPersonId === toId && r.toPersonId === fromId;
      });
      if (childReverse) return true;
    }
    if (relType === "child") {
      // Adding fromId as parent-of-child toId — check reverse
      var reverse = rels.some(function (r) {
        return r.relationshipType === "child" && r.fromPersonId === toId && r.toPersonId === fromId;
      });
      if (reverse) return true;
      var parentReverse = rels.some(function (r) {
        return r.relationshipType === "parent" && r.fromPersonId === toId && r.toPersonId === fromId;
      });
      if (parentReverse) return true;
    }
    return false;
  }

  function upsertRelationship(opts) {
    var g = _ensureGraph(); if (!g) return null;
    /* An edge to a tombstoned entry would be an edge to nobody — and it
       would carry the removed person's id back into the PUT. */
    if (String(opts.fromPersonId).indexOf("tombstoned:") === 0 ||
        String(opts.toPersonId).indexOf("tombstoned:") === 0) {
      return null;
    }
    var id = opts.id || _stableRelId(opts.fromPersonId, opts.toPersonId, opts.relationshipType);
    var _tr = _touchedSinceRestore[id] || (_touchedSinceRestore[id] = {});
    Object.keys(opts).forEach(function (k) {
      var v = opts[k];
      if (k === "id" || k === "narratorId") return;
      if (typeof v === "boolean" || (v !== undefined && v !== null && v !== "")) _tr[k] = true;
    });

    // Phase Q.2: Block impossible lineage cycles
    if (_wouldCreateCycle(g, opts.fromPersonId, opts.toPersonId, opts.relationshipType)) {
      console.warn("[bb-graph] ⚠ BLOCKED: impossible cycle detected — " +
        opts.fromPersonId + " → " + opts.toPersonId + " as " + opts.relationshipType +
        ". A direct parent-child cycle is not allowed.");
      return null;
    }

    var existing = g.relationships[id] || {};
    g.relationships[id] = {
      id:               id,
      narratorId:       opts.narratorId       || existing.narratorId       || "",
      fromPersonId:     opts.fromPersonId     || existing.fromPersonId     || "",
      toPersonId:       opts.toPersonId       || existing.toPersonId       || "",
      relationshipType: opts.relationshipType || existing.relationshipType || "",
      subtype:          opts.subtype          || existing.subtype          || "",
      label:            opts.label            || existing.label            || "",
      status:           opts.status           || existing.status           || "active",
      notes:            opts.notes !== undefined ? opts.notes : (existing.notes || ""),
      source:           opts.source           || existing.source           || "manual",
      provenance:       opts.provenance       || existing.provenance       || "",
      confidence:       opts.confidence !== undefined ? opts.confidence : (existing.confidence || 1.0),
      startDate:        opts.startDate        || existing.startDate        || "",
      endDate:          opts.endDate          || existing.endDate          || "",
      meta:             opts.meta             || existing.meta             || {}
    };
    return g.relationships[id];
  }

  function removeRelationship(relId) {
    var g = _ensureGraph(); if (!g) return;
    delete g.relationships[relId];
  }

  /** Find relationships involving a person */
  function getRelationshipsFor(personId) {
    var g = _ensureGraph(); if (!g) return [];
    return Object.values(g.relationships).filter(function (r) {
      return r.fromPersonId === personId || r.toPersonId === personId;
    });
  }

  /* ───────────────────────────────────────────────────────────
     QUESTIONNAIRE → GRAPH SYNC
     Reads questionnaire sections and writes graph records.
     This is the canonical mapping from editor surface → truth model.
  ─────────────────────────────────────────────────────────── */

  function syncFromQuestionnaire() {
    var bb = _bb(); if (!bb) return;
    var qq = bb.questionnaire; if (!qq) return;
    var pid = bb.personId; if (!pid) return;
    var g = _ensureGraph();

    /* One claim set per sync pass, so identity adoption cannot hand the
       same existing record to two different entries. See _resolvePersonId. */
    _syncClaimedIds = {};

    /* NOTHING IS CLEARED HERE. A ROUTINE SYNC DOES NOT DELETE PEOPLE.
       WO-BIO-VIEW-SAFETY-01 (2026-09-21).

       This line used to be `_clearBySource(g, "questionnaire")`, which
       removed every questionnaire-sourced person and relationship before
       rebuilding from whatever document was in memory. Anything the
       document did not mention was therefore deleted and not recreated,
       and `persistToBackend()` sent that as a full replacement.

       Measured: under HORNELORE_QUESTIONNAIRE_BIO_FACTS_READ=1 the
       hydrating GET returns a three-leaf projection, so one deliberate
       save put four of a real narrator's grandparents one step from
       deletion, with four relationships.

       AND THE FIRST FIX FOR IT WAS ALSO WRONG. It cleared only sections
       the document could rebuild — which still deleted a father when the
       document carried the mother alone, because both are
       `questionnaire:parents`. Section granularity against person-level
       records is the same omission-as-deletion defect at a smaller radius.
       An entry id with no name counted as content too. Caught on review,
       reproduced, and removed rather than patched again.

       The rule that actually holds is the one `merge_whole_document`
       already enforces a layer down: an omitted record is UNTOUCHED, not
       deleted. So this is now a pure upsert, which is what
       `syncFromProfile` has always been — `_clearBySource` never had a
       second caller, so the questionnaire lane was the only one deleting.

       THE TRADE, STATED. Removing a relative from the questionnaire no
       longer removes them from the graph; a stale node survives until an
       explicit removal. `removePerson` and `deleteRelationship` already
       exist for that, and an explicit questionnaire-driven removal
       operation is owed. A visible stale record is recoverable. A silently
       deleted grandparent is not, and nobody would know to look. */

    // 1. Create narrator person node
    var narratorName = "";
    if (qq.personal) {
      narratorName = qq.personal.fullName || qq.personal.preferredName || "";
    }
    if (!narratorName && typeof state !== "undefined" && state.profile && state.profile.basics) {
      narratorName = state.profile.basics.fullname || state.profile.basics.preferred || "";
    }
    var narratorNode = upsertPerson({
      id: "gp_narrator_" + pid.slice(0, 8),
      narratorId: pid,
      firstName: (qq.personal && qq.personal.fullName) ? qq.personal.fullName.split(" ")[0] : "",
      lastName: (qq.personal && qq.personal.fullName) ? qq.personal.fullName.split(" ").slice(-1)[0] : "",
      displayName: narratorName,
      isNarrator: true,
      source: "questionnaire",
      provenance: "questionnaire:personal"
    });

    // 2. Parents
    if (qq.parents && Array.isArray(qq.parents)) {
      qq.parents.forEach(function (p) {
        var name = [p.firstName, p.middleName, p.lastName].filter(Boolean).join(" ");
        if (!name) return;
        var parentNode = upsertPerson({
          narratorId: pid,
          firstName: p.firstName || "",
          middleName: p.middleName || "",
          lastName: p.lastName || "",
          maidenName: p.maidenName || "",
          birthDate: p.birthDate || "",
          birthPlace: p.birthPlace || "",
          occupation: p.occupation || "",
          deceased: _triState(p.deceased),
          source: "questionnaire",
          provenance: "questionnaire:parents",
          entryId: p._entryId || ""
        });
        var subtype = _RELATION_TO_SUBTYPE[p.relation] || "biological";
        upsertRelationship({
          narratorId: pid,
          fromPersonId: parentNode.id,
          toPersonId: narratorNode.id,
          relationshipType: "parent",
          subtype: subtype,
          label: p.relation || "Parent",
          source: "questionnaire",
          provenance: "questionnaire:parents"
        });
      });
    }

    // 3. Grandparents
    if (qq.grandparents && Array.isArray(qq.grandparents)) {
      qq.grandparents.forEach(function (gp) {
        var name = [gp.firstName, gp.middleName, gp.lastName].filter(Boolean).join(" ");
        if (!name) return;
        var gpNode = upsertPerson({
          narratorId: pid,
          firstName: gp.firstName || "",
          middleName: gp.middleName || "",
          lastName: gp.lastName || "",
          maidenName: gp.maidenName || "",
          birthDate: gp.birthDate || "",
          birthPlace: gp.birthPlace || "",
          source: "questionnaire",
          provenance: "questionnaire:grandparents",
          entryId: gp._entryId || ""
        });
        upsertRelationship({
          narratorId: pid,
          fromPersonId: gpNode.id,
          toPersonId: narratorNode.id,
          relationshipType: "grandparent",
          subtype: "biological",
          label: (gp.side || "") + " Grandparent",
          source: "questionnaire",
          provenance: "questionnaire:grandparents",
          meta: { side: gp.side || "", ancestry: gp.ancestry || "", culturalBackground: gp.culturalBackground || "" }
        });
      });
    }

    // 4. Siblings
    if (qq.siblings && Array.isArray(qq.siblings)) {
      qq.siblings.forEach(function (s) {
        var name = [s.firstName, s.middleName, s.lastName].filter(Boolean).join(" ");
        if (!name) return;
        var sibNode = upsertPerson({
          narratorId: pid,
          firstName: s.firstName || "",
          middleName: s.middleName || "",
          lastName: s.lastName || "",
          maidenName: s.maidenName || "",
          source: "questionnaire",
          provenance: "questionnaire:siblings",
          entryId: s._entryId || ""
        });
        var subtype = _RELATION_TO_SUBTYPE[s.relation] || "biological";
        upsertRelationship({
          narratorId: pid,
          fromPersonId: narratorNode.id,
          toPersonId: sibNode.id,
          relationshipType: "sibling",
          subtype: subtype,
          label: s.relation || "Sibling",
          source: "questionnaire",
          provenance: "questionnaire:siblings"
        });
      });
    }

    // 5. Children
    if (qq.children && Array.isArray(qq.children)) {
      qq.children.forEach(function (c) {
        var name = [c.firstName, c.middleName, c.lastName].filter(Boolean).join(" ");
        if (!name) return;
        var childNode = upsertPerson({
          narratorId: pid,
          firstName: c.firstName || "",
          middleName: c.middleName || "",
          lastName: c.lastName || "",
          birthDate: c.birthDate || "",
          birthPlace: c.birthPlace || "",
          source: "questionnaire",
          provenance: "questionnaire:children",
          entryId: c._entryId || ""
        });
        upsertRelationship({
          narratorId: pid,
          fromPersonId: narratorNode.id,
          toPersonId: childNode.id,
          relationshipType: "child",
          subtype: _RELATION_TO_SUBTYPE[c.relation] || "biological",
          label: c.relation || "Child",
          source: "questionnaire",
          provenance: "questionnaire:children"
        });
      });
    }

    // 6. Spouse / Partner (array-first)
    if (qq.spouse) {
      var spouseArr = Array.isArray(qq.spouse) ? qq.spouse : [qq.spouse];
      spouseArr.forEach(function (sp) {
        var name = [sp.firstName, sp.middleName, sp.lastName].filter(Boolean).join(" ");
        if (!name) return;
        var relLabel = sp.relationshipType || "Spouse";
        var relType = (relLabel === "Former Spouse") ? "former_spouse"
                    : (relLabel === "Partner" || relLabel === "Life Partner" || relLabel === "Domestic Partner") ? "partner"
                    : (relLabel === "Chosen Family") ? "chosen_family"
                    : "spouse";
        var subtype = _LABEL_TO_SUBTYPE[relLabel] || "spouse";

        var spNode = upsertPerson({
          narratorId: pid,
          firstName: sp.firstName || "",
          middleName: sp.middleName || "",
          lastName: sp.lastName || "",
          maidenName: sp.maidenName || "",
          birthDate: sp.birthDate || "",
          birthPlace: sp.birthPlace || "",
          occupation: sp.occupation || "",
          deceased: _triState(sp.deceased),
          source: "questionnaire",
          provenance: "questionnaire:spouse",
          entryId: sp._entryId || ""
        });
        upsertRelationship({
          narratorId: pid,
          fromPersonId: narratorNode.id,
          toPersonId: spNode.id,
          relationshipType: relType,
          subtype: subtype,
          label: relLabel,
          notes: sp.narrative || "",
          source: "questionnaire",
          provenance: "questionnaire:spouse"
        });
      });
    }

    // 7. Marriage (event overlay on spouse relationships)
    if (qq.marriage) {
      var marriageArr = Array.isArray(qq.marriage) ? qq.marriage : [qq.marriage];
      marriageArr.forEach(function (m) {
        if (!m.spouseReference && !m.marriageDate && !m.proposalStory && !m.weddingDetails) return;
        // Find the spouse person node by reference
        var spRef = m.spouseReference || "";
        var spNode = spRef ? findPersonByName(spRef) : null;
        if (spNode) {
          // Find the existing relationship and add marriage metadata
          var rels = getRelationshipsFor(spNode.id);
          rels.forEach(function (r) {
            if (r.fromPersonId === narratorNode.id || r.toPersonId === narratorNode.id) {
              r.startDate = m.marriageDate || r.startDate || "";
              r.meta = r.meta || {};
              r.meta.proposalStory = m.proposalStory || "";
              r.meta.weddingDetails = m.weddingDetails || "";
            }
          });
        }
      });
    }

    var personCount = Object.keys(g.persons).length;
    var relCount = Object.keys(g.relationships).length;
    _syncClaimedIds = null;
    console.log("[bb-graph] Synced from questionnaire: " + personCount + " persons, " + relCount + " relationships");

    return g;
  }

  /** Clear all graph records from a specific source */
  /* `_clearBySource` IS GONE, AND SO IS ITS REPLACEMENT.
     WO-BIO-VIEW-SAFETY-01 (2026-09-21).

     It removed every graph record of a given source so a sync could
     rebuild them. Its only caller was the questionnaire sync, which is
     now a pure upsert — see the note in syncFromQuestionnaire. A
     section-scoped variant was written as the fix, reviewed, reproduced
     as still-destructive (a document carrying only the mother deleted the
     father, both being `questionnaire:parents`), and deleted.

     Not kept as a helper for a future explicit-removal operation. A
     function whose whole job is to delete a narrator's relatives in bulk,
     sitting unused next to a sync that used to call it, is an invitation
     to wire it back up. Explicit removal has `removePerson` and
     `deleteRelationship`, which act on one named record at a time — and
     a questionnaire-driven removal operation, when it is built, should be
     written deliberately against a validated instruction rather than
     inherited from here. */

  /* ───────────────────────────────────────────────────────────
     PROFILE KINSHIP → GRAPH SYNC
     Reads profile.kinship and writes graph records.
     Used as a secondary source alongside questionnaire.
  ─────────────────────────────────────────────────────────── */

  function syncFromProfile() {
    var bb = _bb(); if (!bb) return;
    if (typeof state === "undefined" || !state.profile) return;
    var pid = bb.personId; if (!pid) return;
    var g = _ensureGraph();

    var kinship = state.profile.kinship || [];
    if (!kinship.length) return;

    // Ensure narrator node exists
    var narratorId = "gp_narrator_" + pid.slice(0, 8);
    if (!g.persons[narratorId]) {
      var basics = state.profile.basics || {};
      upsertPerson({
        id: narratorId,
        narratorId: pid,
        displayName: basics.fullname || basics.preferred || "",
        isNarrator: true,
        source: "profile",
        provenance: "profile:basics"
      });
    }

    kinship.forEach(function (k) {
      if (!k.name) return;
      var rel = (k.relation || k.relationshipType || "").toLowerCase();
      var relType = "other";
      var subtype = "";
      var label = k.relation || k.relationshipType || "";

      // Map relation string to graph type + subtype
      if (/father|mother|parent/i.test(rel)) {
        relType = "parent";
        subtype = /step/i.test(rel) ? "step" : /adopt/i.test(rel) ? "adoptive" : /foster/i.test(rel) ? "foster" : "biological";
      } else if (/brother|sister|sibling/i.test(rel)) {
        relType = "sibling";
        subtype = /half/i.test(rel) ? "half" : /step/i.test(rel) ? "step" : /adopt/i.test(rel) ? "adoptive" : "biological";
      } else if (/spouse|wife|husband/i.test(rel)) {
        relType = /former/i.test(rel) ? "former_spouse" : "spouse";
        subtype = /former/i.test(rel) ? "former_spouse" : "spouse";
      } else if (/partner/i.test(rel)) {
        relType = "partner";
        subtype = /domestic/i.test(rel) ? "domestic_partner" : /life/i.test(rel) ? "life_partner" : /common/i.test(rel) ? "common_law" : "partner";
      } else if (/child|son|daughter/i.test(rel)) {
        relType = "child";
        subtype = /step/i.test(rel) ? "step" : /adopt/i.test(rel) ? "adoptive" : "biological";
      } else if (/grandparent|grandfather|grandmother/i.test(rel)) {
        relType = "grandparent";
        subtype = "biological";
      } else if (/grandchild|grandson|granddaughter/i.test(rel)) {
        relType = "grandchild";
        subtype = "biological";
      } else if (/guardian/i.test(rel)) {
        relType = "guardian";
        subtype = "legal_guardian";
      } else if (/chosen|intentional/i.test(rel)) {
        relType = "chosen_family";
        subtype = "chosen_family";
      }

      var parts = (k.name || "").trim().split(/\s+/);
      var personNode = upsertPerson({
        narratorId: pid,
        firstName: parts[0] || "",
        lastName: parts.length > 1 ? parts[parts.length - 1] : "",
        middleName: parts.length > 2 ? parts.slice(1, -1).join(" ") : "",
        maidenName: k.maidenName || "",
        displayName: k.name || "",
        birthDate: k.birthDate || "",
        birthPlace: k.pob || "",
        occupation: k.occupation || "",
        deceased: _triState(k.deceased),
        source: "profile",
        provenance: "profile:kinship"
      });

      // For parent/grandparent: from=person to=narrator
      // For child/grandchild: from=narrator to=person
      // For sibling/spouse/partner: from=narrator to=person
      var fromId, toId;
      if (relType === "parent" || relType === "grandparent" || relType === "guardian") {
        fromId = personNode.id;
        toId = narratorId;
      } else {
        fromId = narratorId;
        toId = personNode.id;
      }

      upsertRelationship({
        narratorId: pid,
        fromPersonId: fromId,
        toPersonId: toId,
        relationshipType: relType,
        subtype: subtype,
        label: label,
        notes: k.narrative || k.notes || "",
        source: "profile",
        provenance: "profile:kinship"
      });
    });

    // Also sync pets if present
    var pets = state.profile.pets || [];
    pets.forEach(function (pet) {
      if (!pet.name) return;
      upsertPerson({
        narratorId: pid,
        displayName: pet.name,
        firstName: pet.name,
        source: "profile",
        provenance: "profile:pets",
        meta: { species: pet.species || "", breed: pet.breed || "", isPet: true }
      });
    });

    console.log("[bb-graph] Synced from profile kinship: " + Object.keys(g.persons).length + " persons, " + Object.keys(g.relationships).length + " relationships");
  }

  /* ───────────────────────────────────────────────────────────
     BACKEND PERSISTENCE
     Backend is the truth authority. Graph is persisted as a
     full replace (PUT) and restored on narrator switch.
  ─────────────────────────────────────────────────────────── */

  /* THE RESTORE/PERSIST RACE. The server PUT is a full replacement scoped
     only by narrator (db.py:7958-7959) with no version check. fullSync()
     never waited for restoreFromBackend(), so a save that fired while the
     hydrating GET was still in flight PUT whatever happened to be in memory
     — usually just what the current card produced — and the server replaced
     the stored graph with it. The generation counter stops narrator A's
     data landing on narrator B; it did nothing for this.

     So: while a restore for THIS narrator and THIS generation is pending,
     the PUT waits for it. If the generation moves while waiting (a switch),
     the PUT is dropped, because it would be for a narrator who is no longer
     loaded. When nothing is pending the PUT goes synchronously, as before —
     the test harness and deriveStoredGraph read it immediately, and nothing
     about the no-race case should change. */
  var _restoreInFlight = null;    // { gen, pid, promise, outcome } or null
  var _restoreFailedFor = null;   // narrator whose LAST restore did not hydrate
  var _touchedSinceRestore = {};  // ids written locally since the restore began

  /* THREE MORE HOLES IN THE SAME BOUNDARY, found on external review of the
     first version of this gate (2026-09-22), each reproduced against the
     exported functions before being fixed:

       1. The restore OVERWROTE an edit made while it was pending. Operator
          types a new occupation, the GET returns the old one, the handler
          did `g.persons[id] = serverRecord`, the queued PUT sent OLD.
          → a record written locally since the restore began keeps its
            non-empty local fields; the server fills what is empty.
       2. A FAILED restore (503) still released the queued PUT, which sent
          the partial in-memory graph as a full replacement — the original
          data-loss mechanism, back through a different door.
          → the queued PUT runs only if the restore hydrated; and a graph
            whose last restore failed refuses to persist at all, queued or
            not, until a restore succeeds.
       3. A narrator change WITHOUT the switch hook (generation unmoved)
          sent narrator B's in-memory graph to narrator A's endpoint.
          → the queued PUT re-checks the ACTIVE NARRATOR ID, not only the
            generation, and _putGraph checks it again at the moment of
            sending. */

  function persistToBackend() {
    var bb = _bb(); if (!bb) return;
    var pid = bb.personId; if (!pid) return;

    if (_restoreInFlight && _restoreInFlight.pid === pid &&
        _restoreInFlight.gen === _graphRestoreGen) {
      var myGen = _graphRestoreGen;
      var inflight = _restoreInFlight;
      return inflight.promise.then(function () {
        var now = _bb();
        if (myGen !== _graphRestoreGen || !now || now.personId !== pid) {
          console.warn("[bb-graph] DROPPING a persist queued behind a restore: the " +
            "active narrator is no longer " + String(pid).slice(0, 8) +
            ", so the queued graph is not theirs.");
          return;
        }
        if (inflight.outcome !== "ok") {
          console.warn("[bb-graph] DROPPING a persist queued behind a restore that " +
            inflight.outcome + ": sending the in-memory graph now would replace " +
            "the stored family with a partial one.");
          return;
        }
        return _putGraph(pid);
      });
    }
    if (_restoreFailedFor === pid) {
      console.warn("[bb-graph] REFUSING to persist for " + String(pid).slice(0, 8) +
        ": the graph never hydrated (last restore failed), and the server PUT " +
        "is a full replacement. Nothing was sent.");
      return Promise.resolve();
    }
    return _putGraph(pid);
  }

  function _putGraph(pid) {
    var bbNow = _bb();
    if (!bbNow || bbNow.personId !== pid) {
      console.warn("[bb-graph] REFUSING to send " + String(pid).slice(0, 8) +
        "'s PUT: the active narrator is " +
        String((bbNow && bbNow.personId) || "none").slice(0, 8) + ".");
      return Promise.resolve();
    }
    var g = _ensureGraph();

    // Convert in-memory maps to arrays for API
    var persons = Object.values(g.persons).map(function (p) {
      return {
        id: p.id,
        display_name: p.displayName || "",
        first_name: p.firstName || "",
        middle_name: p.middleName || "",
        last_name: p.lastName || "",
        maiden_name: p.maidenName || "",
        birth_date: p.birthDate || "",
        birth_place: p.birthPlace || "",
        occupation: p.occupation || "",
        deceased: !!p.deceased,
        is_narrator: !!p.isNarrator,
        source: p.source || "manual",
        provenance: p.provenance || "",
        confidence: p.confidence || 1.0,
        meta: p.meta || {}
      };
    });

    var relationships = Object.values(g.relationships).map(function (r) {
      return {
        id: r.id,
        from_person_id: r.fromPersonId || "",
        to_person_id: r.toPersonId || "",
        relationship_type: r.relationshipType || "",
        subtype: r.subtype || "",
        label: r.label || "",
        status: r.status || "active",
        notes: r.notes || "",
        source: r.source || "manual",
        provenance: r.provenance || "",
        confidence: r.confidence || 1.0,
        start_date: r.startDate || "",
        end_date: r.endDate || "",
        meta: r.meta || {}
      };
    });

    return fetch(API.GRAPH_PUT(pid), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ persons: persons, relationships: relationships })
    })
    .then(function (r) {
      if (r.ok) console.log("[bb-graph] Graph persisted to backend for " + pid.slice(0, 8));
      else console.warn("[bb-graph] Backend persist failed: " + r.status);
    })
    .catch(function (e) {
      console.warn("[bb-graph] Backend persist error", e);
    });
  }

  /* Monotonic, bumped by every restore and every narrator switch. An
     in-flight graph GET carries the value it started under and discards
     itself if the number has moved. WO-BIO-VIEW-SAFETY-01 (2026-09-21). */
  var _graphRestoreGen = 0;

  function restoreFromBackend(pid) {
    if (!pid || typeof API === "undefined" || !API.GRAPH_GET) return;
    var bb = _bb(); if (!bb) return;

    /* A LATE GRAPH RESPONSE MUST NOT LAND ON ANOTHER NARRATOR.
       WO-BIO-VIEW-SAFETY-01, raised on review of the Operator Intake fix:
       the same defect lived here untouched.

       The handler below writes `g.persons[p.id] = …` into whatever graph
       is in memory when the response arrives, with no recheck of who is
       loaded. onNarratorSwitch resets bb.graph and starts this fetch, so
       switching A → B leaves A's request in flight; if it resolves after
       the switch, A's relatives are inserted into B's graph — and the next
       fullSync() would persist that mixed graph under B's id.

       Checked at the point of USE, like Operator Intake's refresh():
       cancelling the request cannot guarantee this, because a response
       already in flight completes regardless. */
    var _myGen = ++_graphRestoreGen;
    var _myPid = pid;
    _touchedSinceRestore = {};
    var inflight = { gen: _myGen, pid: _myPid, promise: null, outcome: "pending" };

    /* A record the operator wrote while this GET was pending keeps what
       they wrote. The server's copy is older by definition — it predates
       the edit — so it fills only what is locally empty. */
    function _mergeUnderLocal(serverRecord, local, fields) {
      /* Field-by-field, by WHAT WAS WRITTEN — not by what the value looks
         like. The first version kept a local value only if it was not "",
         null, undefined or false, so an operator's deliberate "No" to
         deceased (false) lost to an older server `true`. Now every field the
         local write actually supplied wins, false included; every field it
         did not supply comes from the server. (External review, 2026-09-22.) */
      if (!local || !fields) return serverRecord;
      var out = Object.assign({}, serverRecord);
      Object.keys(fields).forEach(function (k) {
        if (k === "meta") return;
        if (Object.prototype.hasOwnProperty.call(local, k)) out[k] = local[k];
      });
      out.meta = Object.assign({}, serverRecord.meta || {}, local.meta || {});
      return out;
    }

    var _p = fetch(API.GRAPH_GET(pid))
      .then(function (r) {
        if (!r.ok) { inflight.outcome = "failed (HTTP " + r.status + ")"; return null; }
        return r.json();
      })
      .then(function (j) {
        if (!j) { if (inflight.outcome === "pending") inflight.outcome = "returned nothing"; return; }
        var _bbNow = _bb();
        if (_myGen !== _graphRestoreGen ||
            (_bbNow && _bbNow.personId && _bbNow.personId !== _myPid)) {
          inflight.outcome = "was discarded as stale";
          console.warn("[bb-graph] DISCARDING a late graph response for " +
            String(_myPid).slice(0, 8) + " — the active narrator is now " +
            String((_bbNow && _bbNow.personId) || "none").slice(0, 8) +
            ". Merging it would put one narrator's relatives in another's graph.");
          return;
        }
        var g = _ensureGraph();

        // Restore persons
        if (j.persons && Array.isArray(j.persons)) {
          j.persons.forEach(function (p) {
            var local = _touchedSinceRestore[p.id] ? g.persons[p.id] : null;
            var localFields = _touchedSinceRestore[p.id] || null;
            g.persons[p.id] = _mergeUnderLocal({
              id:           p.id,
              narratorId:   p.narrator_id || pid,
              displayName:  p.display_name || "",
              firstName:    p.first_name || "",
              middleName:   p.middle_name || "",
              lastName:     p.last_name || "",
              maidenName:   p.maiden_name || "",
              birthDate:    p.birth_date || "",
              birthPlace:   p.birth_place || "",
              occupation:   p.occupation || "",
              deceased:     !!p.deceased,
              isNarrator:   !!p.is_narrator,
              source:       p.source || "manual",
              provenance:   p.provenance || "",
              confidence:   p.confidence || 1.0,
              meta:         p.meta || {}
            }, local, localFields);
          });
        }

        // Restore relationships
        if (j.relationships && Array.isArray(j.relationships)) {
          j.relationships.forEach(function (r) {
            var localR = _touchedSinceRestore[r.id] ? g.relationships[r.id] : null;
            var localRFields = _touchedSinceRestore[r.id] || null;
            g.relationships[r.id] = _mergeUnderLocal({
              id:               r.id,
              narratorId:       r.narrator_id || pid,
              fromPersonId:     r.from_person_id || "",
              toPersonId:       r.to_person_id || "",
              relationshipType: r.relationship_type || "",
              subtype:          r.subtype || "",
              label:            r.label || "",
              status:           r.status || "active",
              notes:            r.notes || "",
              source:           r.source || "manual",
              provenance:       r.provenance || "",
              confidence:       r.confidence || 1.0,
              startDate:        r.start_date || "",
              endDate:          r.end_date || "",
              meta:             r.meta || {}
            }, localR, localRFields);
          });
        }

        inflight.outcome = "ok";
        if (_restoreFailedFor === _myPid) _restoreFailedFor = null;

        var pc = Object.keys(g.persons).length;
        var rc = Object.keys(g.relationships).length;
        if (pc > 0 || rc > 0) {
          console.log("[bb-graph] ✅ Graph restored from backend: " + pc + " persons, " + rc + " relationships for " + pid.slice(0, 8));
        }
      })
      .catch(function (e) {
        inflight.outcome = "threw (" + (e && e.message ? e.message : String(e)) + ")";
        console.warn("[bb-graph] Backend graph restore failed", e);
      })
      .then(function () {
        /* Settled — success, discard or failure alike — so a persist queued
           behind this restore is released in every case (and decides for
           itself from `outcome`). A failed hydration is remembered for this
           narrator so no later persist sends a partial full-replacement. */
        if (inflight.outcome !== "ok" && inflight.outcome !== "was discarded as stale") {
          _restoreFailedFor = _myPid;
        }
        if (_restoreInFlight && _restoreInFlight.gen === _myGen) _restoreInFlight = null;
      });

    inflight.promise = _p;
    _restoreInFlight = inflight;
    return _p;
  }

  /* ───────────────────────────────────────────────────────────
     GRAPH → FAMILY TREE BRIDGE
     Provides graph data in the format family tree seeding expects.
  ─────────────────────────────────────────────────────────── */

  function getGraphForFamilyTree() {
    var g = _ensureGraph(); if (!g) return { nodes: [], edges: [] };

    var nodes = Object.values(g.persons).map(function (p) {
      var role = "other";
      if (p.isNarrator) role = "narrator";
      else {
        // Determine role from relationships
        var rels = getRelationshipsFor(p.id);
        for (var i = 0; i < rels.length; i++) {
          var r = rels[i];
          if (r.relationshipType === "parent" && r.fromPersonId === p.id) { role = "parent"; break; }
          if (r.relationshipType === "child" && r.toPersonId === p.id) { role = "child"; break; }
          if (r.relationshipType === "sibling") { role = "sibling"; break; }
          if (r.relationshipType === "spouse" || r.relationshipType === "partner") { role = "spouse"; break; }
          if (r.relationshipType === "former_spouse") { role = "spouse"; break; }
          if (r.relationshipType === "grandparent" && r.fromPersonId === p.id) { role = "grandparent"; break; }
          if (r.relationshipType === "grandchild" && r.toPersonId === p.id) { role = "grandchild"; break; }
          if (r.relationshipType === "guardian") { role = "guardian"; break; }
          if (r.relationshipType === "chosen_family") { role = "chosen_family"; break; }
        }
      }

      // Extract birth year from birthDate
      var birthYear = "";
      if (p.birthDate) {
        var m = p.birthDate.match(/\d{4}/);
        if (m) birthYear = m[0];
      }

      return {
        id: "ft_" + p.id,
        graphPersonId: p.id,
        role: role,
        displayName: p.displayName || "",
        preferredName: "",
        birthYear: birthYear,
        deathYear: "",
        notes: "",
        source: "graph",
        sourceRef: p.id,
        deceased: p.deceased || false
      };
    });

    var edges = Object.values(g.relationships).map(function (r) {
      return {
        id: "fte_" + r.id,
        graphRelId: r.id,
        from: "ft_" + r.fromPersonId,
        to: "ft_" + r.toPersonId,
        relType: _mapRelTypeToFT(r.relationshipType, r.subtype),
        label: r.label || r.relationshipType || "",
        notes: r.notes || "",
        source: "graph"
      };
    });

    return { nodes: nodes, edges: edges };
  }

  /** Map graph relationship types to family tree edge types */
  function _mapRelTypeToFT(relType, subtype) {
    if (relType === "parent" || relType === "child" || relType === "grandparent" || relType === "grandchild") {
      if (subtype === "adoptive") return "adoptive";
      if (subtype === "step") return "step";
      if (subtype === "half") return "half";
      if (subtype === "foster") return "foster";
      return "biological";
    }
    if (relType === "spouse") return "marriage";
    if (relType === "former_spouse") return "former_marriage";
    if (relType === "partner") return "partnership";
    if (relType === "guardian") return "guardian";
    if (relType === "chosen_family") return "chosen_family";
    if (relType === "sibling") {
      if (subtype === "half") return "half";
      if (subtype === "step") return "step";
      return "biological";
    }
    return "other";
  }

  /* ───────────────────────────────────────────────────────────
     FULL SYNC PIPELINE
     Orchestrates a complete sync: questionnaire + profile → graph → backend
  ─────────────────────────────────────────────────────────── */

  /* `opts.removedEntryIds` — entry ids the operator deliberately removed
     this save. Applied AFTER the syncs, so a removal is never undone by the
     same pass that carries it, and BEFORE the persist, so the PUT is the
     first thing to reflect it. Returns the persist promise so a caller that
     cares can wait for the write; the questionnaire's caller today does not. */
  function fullSync(opts) {
    var bb = _bb(); if (!bb || !bb.personId) return;
    _ensureGraph();
    syncFromQuestionnaire();
    syncFromProfile();
    if (opts && Array.isArray(opts.removedEntryIds)) {
      opts.removedEntryIds.forEach(removeByEntryId);
    }
    var p = persistToBackend();
    console.log("[bb-graph] Full sync complete for " + bb.personId.slice(0, 8));
    return p;
  }

  /* ───────────────────────────────────────────────────────────
     NARRATOR SWITCH INTEGRATION
     Register as a post-switch hook so graph restores on narrator change.
  ─────────────────────────────────────────────────────────── */

  function onNarratorSwitch(bb) {
    if (!bb || !bb.personId) return;
    /* Bump FIRST, so any graph GET already in flight for the outgoing
       narrator is stamped stale and discards itself rather than merging
       into the incoming narrator's graph. WO-BIO-VIEW-SAFETY-01. */
    _graphRestoreGen += 1;
    // Clear graph for new narrator
    bb.graph = { persons: {}, relationships: {} };
    // Restore from backend (async, overwrites when data arrives)
    restoreFromBackend(bb.personId);
  }

  // Register hook
  if (coreMod._registerPostSwitchHook) {
    coreMod._registerPostSwitchHook(onNarratorSwitch);
  }

  /* ───────────────────────────────────────────────────────────
     GRAPH STATISTICS (for debug/verification)
  ─────────────────────────────────────────────────────────── */

  function getStats() {
    var g = _ensureGraph(); if (!g) return {};
    var persons = Object.values(g.persons);
    var rels = Object.values(g.relationships);

    var typeCounts = {};
    rels.forEach(function (r) {
      typeCounts[r.relationshipType] = (typeCounts[r.relationshipType] || 0) + 1;
    });

    var sourceCounts = {};
    persons.forEach(function (p) {
      sourceCounts[p.source] = (sourceCounts[p.source] || 0) + 1;
    });

    return {
      personCount: persons.length,
      relationshipCount: rels.length,
      typeCounts: typeCounts,
      sourceCounts: sourceCounts,
      narratorNode: persons.find(function (p) { return p.isNarrator; }) || null
    };
  }

  /* ───────────────────────────────────────────────────────────
     EXPORT MODULE
  ─────────────────────────────────────────────────────────── */

  window.LorevoxBioBuilderModules.graph = {
    // State
    _ensureGraph:           _ensureGraph,

    // Person CRUD
    upsertPerson:           upsertPerson,
    removePerson:           removePerson,
    removeByEntryId:        removeByEntryId,
    findPersonByName:       findPersonByName,

    // Relationship CRUD
    upsertRelationship:     upsertRelationship,
    removeRelationship:     removeRelationship,
    getRelationshipsFor:    getRelationshipsFor,

    // Sync pipelines
    syncFromQuestionnaire:  syncFromQuestionnaire,
    syncFromProfile:        syncFromProfile,
    fullSync:               fullSync,

    // Backend persistence
    persistToBackend:       persistToBackend,
    restoreFromBackend:     restoreFromBackend,

    // Family tree bridge
    getGraphForFamilyTree:  getGraphForFamilyTree,

    // Debug
    getStats:               getStats,

    // Constants
    RELATIONSHIP_TYPES:     RELATIONSHIP_TYPES,
    SUBTYPES:               SUBTYPES
  };

  console.log("[bb-graph] Phase Q.1 Relationship Graph Layer loaded");

})();
