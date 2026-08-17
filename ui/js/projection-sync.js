/* ═══════════════════════════════════════════════════════════════
   projection-sync.js — Lorevox 9.0 Interview Projection Sync Layer

   Owns:
     - Writing values into state.interviewProjection.fields
     - Syncing projection → Bio Builder questionnaire (via write modes)
     - Locking rules (human edits are sacred — AI cannot overwrite)
     - Candidate creation for candidate_only fields
     - Suggestion queue management for suggest_only fields
     - localStorage persistence of projection state
     - Narrator-switch reset and restore
     - Audit / sync log

   Locking model:
     1. AI writes:    source = "interview" | "preload" | "profile_hydrate"
        - prefill_if_blank: only if BB field is empty AND not locked
        - candidate_only:   always creates candidate, never writes BB field
        - suggest_only:     queues suggestion, user must accept
        - AI can upgrade its own value if confidence improves
     2. Human writes: source = "human_edit"
        - Always accepted, sets locked = true
        - Overwrites any AI value, preserves in history
        - locked fields are NEVER overwritten by AI

   Depends on:
     - state.js (state.interviewProjection)
     - projection-map.js (LorevoxProjectionMap)
     - bio-builder-core.js (LorevoxBioBuilderModules.core)

   Load order: AFTER projection-map.js, BEFORE interview.js updates
   Exposes: window.LorevoxProjectionSync
═══════════════════════════════════════════════════════════════ */

(function () {
  "use strict";

  var _map = window.LorevoxProjectionMap;
  if (!_map) throw new Error("projection-map.js must load before projection-sync.js");

  /* ───────────────────────────────────────────────────────────
     CONSTANTS
  ─────────────────────────────────────────────────────────── */

  var LS_PROJ_PREFIX   = "lorevox_proj_draft_";
  var SYNC_LOG_CAP     = 200;
  var SCHEMA_VERSION   = 1;

  /* ───────────────────────────────────────────────────────────
     SYNC STATE — WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 commit 1

     Four things this tracks, and why each is load-bearing:

     gen          A generation token. Every narrator load/switch bumps
                  it, so an in-flight load or a queued save that belongs
                  to the previous narrator can be identified and dropped
                  instead of landing on the new one.

     abort        AbortController for the in-flight hydration GET. A
                  fast switch cancels the request rather than racing it.

     hydrated     TRI-STATE, and the distinction matters more than it
                  looks. `true` = the server answered and we know what
                  it holds (INCLUDING "it holds nothing"). `false` = we
                  have not heard, or the request failed. WRITES ARE
                  BLOCKED WHILE false, which is what stops a
                  localStorage draft silently repopulating a server that
                  merely failed to answer. A confirmed-empty server is
                  hydrated=true and is allowed to stay empty.

     baseVersion  The version we hydrated from, sent with every write so
                  the server can reject a stale one.

     dirty        Field paths edited locally since the last successful
                  flush. Only these are sent — the write is field-level,
                  so server-authored keys we have never seen survive it.
  ─────────────────────────────────────────────────────────── */
  var _sync = {
    pid:         null,
    gen:         0,
    abort:       null,
    hydrated:    false,
    baseVersion: 0,
    dirty:       Object.create(null),
    removed:     Object.create(null),
    // PER-PATH concurrency base: what the server held for each path at
    // hydration. A global version proves only that SOMETHING moved, not
    // what -- which is the difference between a safe disjoint rebase and
    // silently overwriting a newer value on the same path.
    base:        Object.create(null),
    // Paths the server reported as contested. Held, never auto-retried.
    conflicts:   []
  };

  /* opts.keepDirty — a SAME-NARRATOR reload keeps the dirty set in place
     rather than re-filing it. A narrator SWITCH does not discard it
     either; see the person-scoped pending store immediately below.

     (This comment previously ended "A narrator SWITCH clears everything,
     because those edits belong to someone else." The first half was a
     data-loss bug and the second half is the argument against it: the
     edits belong to the OUTGOING narrator, which is why they are filed
     under that narrator rather than thrown away.) */
  /* PERSON-SCOPED PENDING STORE.

     An unsent edit belongs to the narrator it was made about. Discarding
     it on a switch loses a legitimate operator edit whenever the switch
     beats the 2s debounce -- which is exactly when someone is working
     quickly. So on leaving A we CANCEL A's network work and RETAIN A's
     dirty paths, removals and hydration base under A's id; returning to
     A restores them, hydrates from the server first, and lets the
     ordinary per-path conflict check decide whether they still apply.

     Nothing of A is ever handed to B: the store is keyed by person id,
     `_resetSyncState` installs only the incoming narrator's entry, and
     every response is dropped unless its generation token AND its pid
     still match. */
  var _pending = Object.create(null);

  function _stashPending(pid) {
    if (!pid) return;
    var hasWork = Object.keys(_sync.dirty).length || Object.keys(_sync.removed).length;
    if (!hasWork) { delete _pending[pid]; return; }
    _pending[pid] = { dirty: _sync.dirty, removed: _sync.removed, base: _sync.base };
    console.log("[projection-sync] retained " + Object.keys(_sync.dirty).length +
                " unsent edit(s) for " + pid + " across the switch");
  }

  function _restorePending(pid) {
    var held = pid ? _pending[pid] : null;
    if (!held) return false;
    _sync.dirty   = held.dirty;
    _sync.removed = held.removed;
    // What A last KNEW the server held, kept so the conflict check can
    // still tell "unchanged since I read it" from "someone moved it".
    _sync.base    = held.base;
    delete _pending[pid];
    console.log("[projection-sync] restored " + Object.keys(held.dirty).length +
                " retained edit(s) for " + pid);
    return true;
  }

  function _resetSyncState(pid, opts) {
    opts = opts || {};
    var outgoing = _sync.pid;
    _sync.gen += 1;
    // Cancel A's network work -- but ONLY the network work.
    if (_sync.abort) { try { _sync.abort.abort(); } catch (e) {} }
    _sync.abort = null;
    _sync.pid = pid || null;
    _sync.hydrated = false;
    _sync.baseVersion = 0;
    if (!opts.keepDirty) {
      // Retain, do not discard. The edit belongs to the outgoing
      // narrator and is filed under them.
      if (outgoing && outgoing !== pid) _stashPending(outgoing);
      _sync.dirty = Object.create(null);
      _sync.removed = Object.create(null);
      _sync.base = Object.create(null);
      _restorePending(pid);
    } else {
      _sync.base = Object.create(null);
    }
    _sync.conflicts = [];
    if (_persistTimer) { clearTimeout(_persistTimer); _persistTimer = null; }
    return _sync.gen;
  }

  function _markDirty(fieldPath) {
    if (!fieldPath) return;
    _sync.dirty[fieldPath] = true;
    delete _sync.removed[fieldPath];
  }

  /* ───────────────────────────────────────────────────────────
     STATE ACCESS
  ─────────────────────────────────────────────────────────── */

  function _proj() {
    return (typeof state !== "undefined") ? state.interviewProjection : null;
  }

  function _bb() {
    if (typeof state === "undefined" || !state.bioBuilder) return null;
    return state.bioBuilder;
  }

  /* ───────────────────────────────────────────────────────────
     CORE: PROJECT A VALUE
     Main entry point for writing a value into the projection.

     @param {string} fieldPath - e.g. "personal.fullName" or "parents[0].firstName"
     @param {string} value     - the extracted value
     @param {object} opts      - { source, turnId, confidence }
       source     : "interview" | "preload" | "human_edit" | "profile_hydrate"
       turnId     : interview turn ID (null for non-interview sources)
       confidence : float 0–1 (default 0.8 for interview, 1.0 for human_edit)
  ─────────────────────────────────────────────────────────── */

  function projectValue(fieldPath, value, opts) {
    var proj = _proj();
    if (!proj) return false;

    opts = opts || {};
    var source     = opts.source     || "interview";
    var turnId     = opts.turnId     || null;
    var confidence = opts.confidence != null ? opts.confidence : (source === "human_edit" ? 1.0 : 0.8);
    var now        = Date.now();

    var existing = proj.fields[fieldPath];

    // ── LOCK CHECK: human-edited fields cannot be overwritten by AI ──
    if (existing && existing.locked && source !== "human_edit") {
      _logSync(fieldPath, "blocked_locked", existing.value, value);
      return false;
    }

    // ── Phase G: PROTECTED IDENTITY CHECK ──
    // Protected identity fields (fullName, DOB, placeOfBirth, etc.) can ONLY
    // be written by trusted sources (human_edit / preload / profile_hydrate).
    // Any untrusted source (interview / backend_extract / projection /
    // backend_correction) ALWAYS routes through suggest_only — even on the
    // first write to a blank field.
    //
    // BUG-312 (2026-04-28): the prior gate only fired when existing.value
    // was already populated. That meant the FIRST extraction to a blank
    // protected field could write garbage directly (e.g. fullName=
    // "I asked you so what can you tell me about me..."), and the
    // overwrite-protection then locked the garbage in place. Result was
    // polluted identity fields surfaced in the Bio Builder questionnaire
    // and in Lori's "What I know about you" reply.
    //
    // The narrator's full name, DOB, and birthplace are too high-stakes
    // to come from chat extraction directly under any circumstance — they
    // must originate at intake (operator-entered preload or human_edit)
    // or be explicitly approved by the operator via the Shadow Review
    // candidates queue.
    var PM = window.LorevoxProjectionMap;
    if (PM && PM.isProtectedIdentity && PM.isProtectedIdentity(fieldPath)) {
      if (!_isTrustedSource(source)) {
        _logSync(fieldPath, "blocked_protected_identity", existing && existing.value, value);
        // Route to suggestion instead of direct write — operator approves
        // via Shadow Review.
        _syncSuggestOnly(fieldPath, value, confidence);
        console.warn("[projection-sync] ⛔ Protected identity write from untrusted source — routed to candidates: " +
          fieldPath + " value=" + JSON.stringify(value).slice(0, 80) + " source=" + source);
        return false;
      }
      // Trusted source path — log overwrites for audit.
      if (existing && existing.value && value !== existing.value) {
        console.info("[projection-sync] protected identity overwrite by trusted source " + source + ": " +
          fieldPath + " " + JSON.stringify(existing.value).slice(0, 60) + " -> " + JSON.stringify(value).slice(0, 60));
      }
    }

    // ── CONFIDENCE GATE: AI can only upgrade, not downgrade ──
    if (existing && existing.value && source !== "human_edit") {
      if (existing.source !== "human_edit" && confidence <= existing.confidence) {
        // Same or lower confidence — skip unless value is substantively different
        if (value === existing.value) return false;
        // Allow if value is longer/richer (heuristic: more chars = more info)
        if (value.length <= existing.value.length && confidence < existing.confidence) {
          _logSync(fieldPath, "blocked_confidence", existing.value, value);
          return false;
        }
      }
    }

    // ── BUILD HISTORY ENTRY ──
    var historyEntry = null;
    if (existing && existing.value) {
      historyEntry = {
        value:      existing.value,
        source:     existing.source,
        turnId:     existing.turnId,
        confidence: existing.confidence,
        ts:         existing.ts
      };
    }

    // ── WRITE THE PROJECTION ──
    proj.fields[fieldPath] = {
      value:      value,
      source:     source,
      turnId:     turnId,
      confidence: confidence,
      locked:     source === "human_edit",
      ts:         now,
      history:    existing ? (existing.history || []).concat(historyEntry ? [historyEntry] : []).slice(-10) : []
    };

    _logSync(fieldPath, "projected", existing ? existing.value : null, value);

    // ── SYNC TO BIO BUILDER ──
    _syncToBioBuilder(fieldPath, value, source, confidence);

    // ── AUTO-PERSIST ──
    // An EXPLICIT MUTATION, which is the only thing that may reach the
    // server. Loads, resets and switches do not come through here.
    _markDirty(fieldPath);
    _debouncedPersist();

    return true;
  }

  /* ───────────────────────────────────────────────────────────
     SYNC TO BIO BUILDER — Applies write mode rules
  ─────────────────────────────────────────────────────────── */

  function _isTrustedSource(source) {
    return source === "human_edit" || source === "preload" || source === "profile_hydrate";
  }

  function _syncToBioBuilder(fieldPath, value, source, confidence) {
    var writeMode = _map.getWriteMode(fieldPath);
    var parsed    = _map.parsePath(fieldPath);
    if (!parsed) return;

    var bb = _bb();
    if (!bb) return;

    // Hornelore rule:
    // trusted sources write directly into questionnaire,
    // even for repeatable people sections that are candidate_only in generic Lorevox.
    if (_isTrustedSource(source)) {
      _syncDirectTrustedWrite(parsed, value, source, bb);
      return;
    }

    // Provisional interview/LLM-derived sources keep existing review flow
    if (writeMode === "prefill_if_blank") {
      _syncPrefillIfBlank(parsed, value, source, bb);
    } else if (writeMode === "candidate_only") {
      _syncCandidateOnly(parsed, value, source, confidence, bb);
    } else if (writeMode === "suggest_only") {
      _syncSuggestOnly(fieldPath, value, confidence);
    }
  }

  /* ── prefill_if_blank: write to BB field only if currently empty ── */
  function _syncPrefillIfBlank(parsed, value, source, bb) {
    if (!bb.questionnaire) bb.questionnaire = {};

    if (parsed.index !== null) {
      // Repeatable section
      if (!Array.isArray(bb.questionnaire[parsed.section])) {
        bb.questionnaire[parsed.section] = [];
      }
      while (bb.questionnaire[parsed.section].length <= parsed.index) {
        bb.questionnaire[parsed.section].push({});
      }
      var entry = bb.questionnaire[parsed.section][parsed.index];
      if (!entry[parsed.field] || String(entry[parsed.field]).trim() === "") {
        entry[parsed.field] = value;
        _logSync(parsed.section + "[" + parsed.index + "]." + parsed.field, "bb_prefilled", "", value);
      }
    } else {
      // Non-repeatable section
      if (!bb.questionnaire[parsed.section]) bb.questionnaire[parsed.section] = {};
      var existing = bb.questionnaire[parsed.section][parsed.field];
      if (!existing || String(existing).trim() === "") {
        bb.questionnaire[parsed.section][parsed.field] = value;
        _logSync(parsed.section + "." + parsed.field, "bb_prefilled", "", value);
      }
    }

    // Trigger BB persistence
    _triggerBBPersist();
  }

  /* ── trusted_direct: write directly for trusted sources (human_edit, preload, profile_hydrate) ── */
  function _syncDirectTrustedWrite(parsed, value, source, bb) {
    if (!bb.questionnaire) bb.questionnaire = {};

    if (parsed.index !== null) {
      if (!Array.isArray(bb.questionnaire[parsed.section])) {
        bb.questionnaire[parsed.section] = [];
      }
      while (bb.questionnaire[parsed.section].length <= parsed.index) {
        bb.questionnaire[parsed.section].push({});
      }

      var entry = bb.questionnaire[parsed.section][parsed.index];
      var oldVal = entry[parsed.field];

      // Preserve meaningful existing value unless this is an explicit human edit
      if (source !== "human_edit" && oldVal && String(oldVal).trim() !== "") {
        _logSync(
          parsed.section + "[" + parsed.index + "]." + parsed.field,
          "trusted_skip_existing",
          oldVal,
          value,
          {
            source: source,
            writeMode: "trusted_direct",
            resultBucket: "skip_existing"
          }
        );
        return;
      }

      entry[parsed.field] = value;
      _logSync(
        parsed.section + "[" + parsed.index + "]." + parsed.field,
        "bb_trusted_write",
        oldVal || "",
        value,
        {
          source: source,
          writeMode: "trusted_direct",
          resultBucket: "bb"
        }
      );
    } else {
      if (!bb.questionnaire[parsed.section]) bb.questionnaire[parsed.section] = {};
      var oldVal2 = bb.questionnaire[parsed.section][parsed.field];

      if (source !== "human_edit" && oldVal2 && String(oldVal2).trim() !== "") {
        _logSync(
          parsed.section + "." + parsed.field,
          "trusted_skip_existing",
          oldVal2,
          value,
          {
            source: source,
            writeMode: "trusted_direct",
            resultBucket: "skip_existing"
          }
        );
        return;
      }

      bb.questionnaire[parsed.section][parsed.field] = value;
      _logSync(
        parsed.section + "." + parsed.field,
        "bb_trusted_write",
        oldVal2 || "",
        value,
        {
          source: source,
          writeMode: "trusted_direct",
          resultBucket: "bb"
        }
      );
    }

    _triggerBBPersist();
  }

  /* ── candidate_only: create candidate entry, never write to BB directly ── */
  function _syncCandidateOnly(parsed, value, source, confidence, bb) {
    if (!bb.candidates) return;
    var config = _map.getFieldConfig(
      parsed.index !== null
        ? _map.buildRepeatablePath(parsed.section, parsed.index, parsed.field)
        : parsed.section + "." + parsed.field
    );
    var candidateType = (config && config.candidateType) || "people";

    // For people candidates, accumulate fields into a single candidate per entry index
    if (candidateType === "people" && parsed.index !== null) {
      var candidateId = "proj_" + parsed.section + "_" + parsed.index;
      var existing = null;
      for (var i = 0; i < bb.candidates.people.length; i++) {
        if (bb.candidates.people[i].id === candidateId) { existing = bb.candidates.people[i]; break; }
      }
      if (!existing) {
        existing = {
          id: candidateId,
          source: "interview_projection",
          section: parsed.section,
          entryIndex: parsed.index,
          confidence: confidence,
          ts: Date.now(),
          data: {}
        };
        bb.candidates.people.push(existing);
      }
      existing.data[parsed.field] = value;
      existing.confidence = Math.max(existing.confidence || 0, confidence);
      existing.ts = Date.now();
      _logSync(candidateId + "." + parsed.field, "candidate_updated", "", value, {
        source: source,
        writeMode: "candidate_only",
        resultBucket: "candidate",
        confidence: confidence
      });
    }
  }

  /* ── suggest_only: queue suggestion for user review ── */
  function _syncSuggestOnly(fieldPath, value, confidence) {
    var proj = _proj();
    if (!proj) return;

    // Remove any existing suggestion for this path
    proj.pendingSuggestions = (proj.pendingSuggestions || []).filter(function (s) {
      return s.fieldPath !== fieldPath;
    });

    proj.pendingSuggestions.push({
      fieldPath:  fieldPath,
      value:      value,
      confidence: confidence,
      turnId:     proj.fields[fieldPath] ? proj.fields[fieldPath].turnId : null,
      ts:         Date.now()
    });

    _logSync(fieldPath, "suggestion_queued", "", value, {
      source: "interview",
      writeMode: "suggest_only",
      resultBucket: "suggestion",
      confidence: confidence
    });
  }

  /* ───────────────────────────────────────────────────────────
     ACCEPT SUGGESTION — User approves a pending suggestion
  ─────────────────────────────────────────────────────────── */

  function acceptSuggestion(fieldPath) {
    var proj = _proj();
    if (!proj) return false;

    var suggestion = null;
    var idx = -1;
    for (var i = 0; i < (proj.pendingSuggestions || []).length; i++) {
      if (proj.pendingSuggestions[i].fieldPath === fieldPath) {
        suggestion = proj.pendingSuggestions[i];
        idx = i;
        break;
      }
    }
    if (!suggestion) return false;

    // Remove from pending
    proj.pendingSuggestions.splice(idx, 1);

    // Write directly to BB questionnaire (user accepted = authoritative)
    var parsed = _map.parsePath(fieldPath);
    if (!parsed) return false;

    var bb = _bb();
    if (bb && bb.questionnaire) {
      if (!bb.questionnaire[parsed.section]) bb.questionnaire[parsed.section] = {};
      bb.questionnaire[parsed.section][parsed.field] = suggestion.value;
      _logSync(fieldPath, "suggestion_accepted", "", suggestion.value);
      _triggerBBPersist();
    }

    // Mark the projection field as human-accepted (locked)
    if (proj.fields[fieldPath]) {
      proj.fields[fieldPath].locked = true;
      proj.fields[fieldPath].source = "human_edit";
      proj.fields[fieldPath].ts = Date.now();
    }

    _debouncedPersist();
    return true;
  }

  /**
   * Dismiss a pending suggestion without applying it.
   */
  function dismissSuggestion(fieldPath) {
    var proj = _proj();
    if (!proj) return;
    proj.pendingSuggestions = (proj.pendingSuggestions || []).filter(function (s) {
      return s.fieldPath !== fieldPath;
    });
    _logSync(fieldPath, "suggestion_dismissed", "", "");
  }

  /* ───────────────────────────────────────────────────────────
     HUMAN EDIT AUTHORITY — Called when user manually edits a
     Bio Builder questionnaire field.
     Sets projection locked = true, preserves history.
  ─────────────────────────────────────────────────────────── */

  function markHumanEdit(fieldPath, value) {
    return projectValue(fieldPath, value, {
      source: "human_edit",
      turnId: null,
      confidence: 1.0
    });
  }

  /* ───────────────────────────────────────────────────────────
     BATCH PROJECT — For preload or profile hydration scenarios
     where many fields arrive at once.
  ─────────────────────────────────────────────────────────── */

  function batchProject(entries, source) {
    source = source || "preload";
    var count = 0;
    entries.forEach(function (entry) {
      if (projectValue(entry.path, entry.value, {
        source: source,
        turnId: entry.turnId || null,
        confidence: entry.confidence || 0.9
      })) {
        count++;
      }
    });
    return count;
  }

  /* ───────────────────────────────────────────────────────────
     NARRATOR SWITCH — Reset + restore from localStorage
  ─────────────────────────────────────────────────────────── */

  /* WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 commit 1 (2026-08-16) — R1.1.
     THE LOAD PATH NEVER WRITES.

     What this function used to do, and why it was a defect: two of its three
     branches called _persistProjection() and THEN _loadProjection() —
     upload-then-download. resetForNarrator is reached from four LOAD
     triggers and no save trigger (app.js loadPerson, app.js
     lvxSwitchNarratorSafe, narrator-preload.js, and this file's own
     _autoInitOnLoad IIFE at script-parse time). So merely putting a
     narrator on screen PUT the browser's in-memory state over the server's
     row before the browser had ever seen that row. L2 caught it doing
     exactly this to a family narrator on app auto-load; the payload
     happened to be byte-identical that time, which is a fact about the
     payload and not about the mechanism.

     The server is now the narrator of record on load. The identity-phase
     carry-over case is preserved in SUBSTANCE, not in mechanism: fields
     collected before a person existed are still adopted under the new pid
     IN MEMORY, and reach the server through the ordinary debounced edit
     path — after hydration, never before it.

     A PUT still happens on: a genuine local edit (projectValue →
     _debouncedPersist), forcePersist() after an applied extraction batch,
     and switching AWAY from a narrator that has in-memory fields. */
  function resetForNarrator(newPid) {
    var proj = _proj();
    if (!proj) return;

    var outgoingPid = proj.personId;
    var hasFields = Object.keys(proj.fields).length > 0;

    // Same narrator re-loaded (e.g. after the identity gate PATCH). Do not
    // wipe, and do not upload — just re-hydrate from the server.
    if (newPid && newPid === outgoingPid && hasFields) {
      console.log("[projection-sync] Same narrator reset — hydrating from server (no write)");
      _resetSyncState(newPid, { keepDirty: true });
      _loadProjection(newPid);
      return;
    }

    // Identity-phase fields with no outgoing pid: built during
    // askName/askDob/askBirthplace before the person existed, then
    // _resolveOrCreatePerson() created one and called loadPerson(newPid).
    // Adopt them in memory under the new pid. They persist via the normal
    // edit path; the load path itself stays read-only.
    if (!outgoingPid && newPid && hasFields) {
      console.log("[projection-sync] Identity-phase fields adopted in memory under new pid (no write on load):", newPid);
      proj.personId = newPid;
      _resetSyncState(newPid);
      _loadProjection(newPid, { keepLocalFields: true });
      return;
    }

    // Switching AWAY from a narrator that has state — this is a real
    // departure, not a load. Flush what is genuinely dirty BEFORE the
    // generation token moves, or the flush would be dropped as stale.
    if (outgoingPid) _persistProjection(outgoingPid);

    // Cancels the in-flight hydration and any queued save for the
    // narrator we are leaving.
    _resetSyncState(newPid || null);

    // Clear state
    proj.personId = newPid || null;
    proj.fields = {};
    proj.pendingSuggestions = [];
    proj.syncLog = [];

    // Hydrate incoming narrator from the server (localStorage paints first)
    if (newPid) _loadProjection(newPid);
  }

  /* ───────────────────────────────────────────────────────────
     LOCALSTORAGE PERSISTENCE
  ─────────────────────────────────────────────────────────── */

  /* FIELD-LEVEL, CONFLICT-AWARE WRITE.

     This used to PUT the whole envelope. That could not be made safe by
     guarding it, because the browser's envelope is not a superset of the
     server's: `projection_writer.apply_correction` rewrites `fields`
     mid-turn, and replacing the document erases those keys even when the
     replacement is fresh and non-empty. Only the locally-edited paths
     are sent now, so a key this browser has never seen survives.

     Three refusals to write, all deliberate:
       - not hydrated  -> we do not know what the server holds. A failed
                          request is NOT a licence to upload the cache.
       - nothing dirty -> nothing was explicitly mutated.
       - wrong pid     -> a queued flush for a narrator we left. */
  function _persistProjection(pid) {
    if (!pid) return;
    var proj = _proj();
    if (!proj) return;

    // localStorage mirror is always safe to refresh — it is a cache.
    _writeLocalMirror(pid, proj);

    if (pid !== _sync.pid) return;
    if (!_sync.hydrated) {
      console.warn("[projection-sync] write withheld — server state unknown for " + pid +
                   " (a failed load must not repopulate the server from cache)");
      return;
    }

    var mutations = {};
    var removals = [];
    var any = false;
    Object.keys(_sync.dirty).forEach(function (fp) {
      if (proj.fields[fp] !== undefined) { mutations[fp] = proj.fields[fp]; any = true; }
    });
    Object.keys(_sync.removed).forEach(function (fp) { removals.push(fp); any = true; });
    if (!any) return;

    _sendMutations(pid, mutations, removals, _sync.gen);
  }

  function _sendMutations(pid, mutations, removals, gen) {
    if (typeof API === "undefined" || !API.IV_PROJ_PATCH) return;
    // Only the paths this write touches. Sending the whole hydrated map
    // would make every concurrent edit anywhere look like a conflict.
    var baseFields = {};
    Object.keys(mutations).forEach(function (k) { baseFields[k] = _sync.base[k]; });
    removals.forEach(function (k) { baseFields[k] = _sync.base[k]; });

    fetch(API.IV_PROJ_PATCH, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        person_id: pid,
        mutations: mutations,
        removals: removals,
        source: "projection_sync",
        base_version: _sync.baseVersion,
        base_fields: baseFields
      })
    }).then(function (r) {
      return r.json().then(function (j) { return { status: r.status, body: j }; });
    }).then(function (res) {
      // A narrator switch overtook this write. Its answer is about
      // someone else's row now.
      if (gen !== _sync.gen || pid !== _sync.pid) return;

      if (res.status === 409 || (res.body && res.body.conflict)) {
        /* CONTESTED PATHS. THERE IS NO AUTOMATIC RETRY, and that is the
           whole correction (supervisor review 2026-08-17).

           The earlier design rebased onto the server record and retried
           once. That is safe only when the server changed DIFFERENT
           paths -- and for that case the server now merges in one round
           trip and never returns 409 at all. A 409 therefore means the
           server changed a path THIS browser is also writing, and
           retrying it would overwrite the newer value. The conflict
           would have been delayed, not resolved.

           So: keep the local mutation, keep it dirty, and surface the
           contested paths. A human decides, not a retry. */
        var paths = (res.body && res.body.conflicting_paths) || [];
        _sync.conflicts = paths;
        _sync.baseVersion = (res.body && res.body.version) != null
          ? res.body.version : _sync.baseVersion;
        console.warn("[projection-sync] CONFLICT — server changed " +
                     paths.length + " path(s) this browser is also editing; " +
                     "the local edit is kept and NOT retried: " + paths.join(", "));
        try {
          if (typeof window !== "undefined" && typeof window.dispatchEvent === "function") {
            window.dispatchEvent(new CustomEvent("lorevox:projection-conflict", {
              detail: { personId: pid, paths: paths, server: res.body && res.body.projection }
            }));
          }
        } catch (e) {}
        return;
      }

      if (res.body && res.body.write_applied) {
        _sync.baseVersion = res.body.version;
        _sync.conflicts = [];
        var srvFields = (res.body.projection && res.body.projection.fields) || {};
        Object.keys(mutations).forEach(function (k) {
          delete _sync.dirty[k];
          _sync.base[k] = srvFields[k];   // new concurrency base
        });
        removals.forEach(function (k) {
          delete _sync.removed[k];
          delete _sync.base[k];
        });
      }
    }).catch(function (e) {
      // Dirty set is deliberately NOT cleared — the edit is unsent, not lost.
      console.warn("[projection-sync] mutation flush failed (will retry on next edit)", e);
    });
  }

  function _writeLocalMirror(pid, proj) {
    try {
      localStorage.setItem(LS_PROJ_PREFIX + pid, JSON.stringify({
        v: SCHEMA_VERSION,
        d: { fields: proj.fields, pendingSuggestions: proj.pendingSuggestions }
        // syncLog intentionally NOT persisted (session-only audit)
      }));
    } catch (e) {
      // localStorage full — degrade silently
    }
  }

  /* opts.keepLocalFields — the identity-phase carry-over case. In-memory
     fields were collected before the person existed, so they are newer than
     anything the server can have; do not let the localStorage paint stomp
     them, and let server hydration MERGE under them rather than replace. */
  function _loadProjection(pid, opts) {
    if (!pid) return;
    var proj = _proj();
    if (!proj) return;
    opts = opts || {};

    // Backend is the authority (async — hydrates when ready)
    _loadProjectionFromBackend(pid, opts);

    if (opts.keepLocalFields) return;

    // Immediate paint: localStorage transient cache, superseded by the
    // hydration above the moment it lands. It is a CACHE, not a source of
    // truth, and R1.1 guarantees it is never re-uploaded by a load.
    try {
      var raw = localStorage.getItem(LS_PROJ_PREFIX + pid);
      if (!raw) return;
      var parsed = JSON.parse(raw);
      var d = parsed && (parsed.d || parsed.data);
      if (d && typeof d === "object") {
        proj.fields = d.fields || {};
        proj.pendingSuggestions = d.pendingSuggestions || [];
      }
    } catch (e) {
      // Malformed — ignore
    }
  }

  /* ── Backend projection hydration (async) ────────────────────
     R1.2 — HYDRATION IS UNCONDITIONAL. This used to overwrite in-memory
     state only when the server row was non-empty, which silently left a
     stale localStorage draft in charge whenever the server had nothing —
     and that stale draft was then uploaded by the load path. With the
     upload gone, "server wins, even when empty" is what makes the server
     authoritative rather than merely consulted. */
  function _loadProjectionFromBackend(pid, opts) {
    if (!pid || typeof API === "undefined" || !API.IV_PROJ_GET) return;
    opts = opts || {};
    var gen = _sync.gen;
    var ctl = null;
    try { ctl = new AbortController(); _sync.abort = ctl; } catch (e) {}
    fetch(API.IV_PROJ_GET(pid), ctl ? { signal: ctl.signal } : undefined)
      .then(function(r) { return r.ok ? r.json() : null; })
      .then(function(j) {
        if (!j || !j.projection) return;
        var proj = _proj(); if (!proj) return;
        // Late response for a narrator we have since switched away from.
        if (gen !== _sync.gen || pid !== _sync.pid) return;
        if (proj.personId && proj.personId !== pid) return;
        var p = j.projection;
        var serverFields = (p.fields && typeof p.fields === "object") ? p.fields : {};
        var serverPending = p.pendingSuggestions || [];

        if (opts.keepLocalFields) {
          // Identity-phase carry-over: server fills gaps, memory wins ties.
          var merged = {};
          Object.keys(serverFields).forEach(function (k) { merged[k] = serverFields[k]; });
          Object.keys(proj.fields).forEach(function (k) { merged[k] = proj.fields[k]; });
          proj.fields = merged;
          if (!proj.pendingSuggestions || !proj.pendingSuggestions.length) {
            proj.pendingSuggestions = serverPending;
          }
        } else {
          proj.fields = serverFields;
          proj.pendingSuggestions = serverPending;
        }
        // CONFIRMED server state — including a confirmed EMPTY one.
        // This is the flag that unblocks writing, and it is set only
        // here, on a real answer.
        _sync.hydrated = true;
        _sync.baseVersion = (j.version != null ? j.version : 0);
        // Snapshot what the server held, per path. This is the evidence
        // that later proves a write is safe -- or proves it is not.
        _sync.base = Object.create(null);
        Object.keys(serverFields).forEach(function (k) { _sync.base[k] = serverFields[k]; });
        console.log("[projection-sync] ✅ Projection hydrated from server for " + pid +
                    " (fields=" + Object.keys(proj.fields).length +
                    " v=" + _sync.baseVersion + ")");
        // Refresh the transient cache so the next paint matches the server.
        _writeLocalMirror(pid, proj);
        // Identity-phase fields carried in from before the person
        // existed are a real mutation and are flushed now -- AFTER
        // hydration, never before it.
        // Returning to a narrator with retained edits: the server is
        // hydrated FIRST, then the retained values are re-applied over it
        // in memory. They flush through the ordinary per-path check,
        // which is what decides whether they still apply.
        var retained = Object.keys(_sync.dirty);
        if (retained.length && !opts.keepLocalFields) {
          var cache = null;
          try {
            var raw = localStorage.getItem(LS_PROJ_PREFIX + pid);
            cache = raw ? (JSON.parse(raw).d || null) : null;
          } catch (e) { cache = null; }
          retained.forEach(function (k) {
            if (cache && cache.fields && cache.fields[k] !== undefined) {
              proj.fields[k] = cache.fields[k];
            }
          });
          Object.keys(_sync.removed).forEach(function (k) { delete proj.fields[k]; });
        }

        if (opts.keepLocalFields) {
          Object.keys(proj.fields).forEach(_markDirty);
          _debouncedPersist();
        } else if (Object.keys(_sync.dirty).length) {
          // A same-narrator reload carried unsent edits across. Now that
          // the server has answered, they are safe to flush -- after
          // hydration, never before it.
          _debouncedPersist();
        }
      })
      .catch(function(e) {
        if (e && e.name === "AbortError") return;   // superseded by a switch
        // NOT hydrated. Writing stays blocked: a failed request tells us
        // nothing about the server, and treating it as "server is empty"
        // is exactly how a cache silently repopulates a live row.
        console.warn("[projection-sync] Backend projection load failed — " +
                     "writes withheld, localStorage used for display only", e);
      });
  }

  function clearProjection(pid) {
    if (!pid) return;
    try { localStorage.removeItem(LS_PROJ_PREFIX + pid); } catch (e) {}
    var proj = _proj();
    if (proj && proj.personId === pid) {
      proj.fields = {};
      proj.pendingSuggestions = [];
      proj.syncLog = [];
    }
    // Drop any queued flush for this narrator — clearing is not an edit
    // to be uploaded, and a stale dirty set would resurrect the cleared
    // fields on the next mutation.
    if (_sync.pid === pid) _resetSyncState(pid);
  }

  // Debounced persistence (max once per 2s). The generation token is
  // captured when the timer is armed and rechecked when it fires, so a
  // narrator switch in between cancels the save instead of landing it on
  // the new narrator.
  var _persistTimer = null;
  function _debouncedPersist() {
    if (_persistTimer) return;
    var gen = _sync.gen;
    var pid = _sync.pid;
    _persistTimer = setTimeout(function () {
      _persistTimer = null;
      if (gen !== _sync.gen || pid !== _sync.pid) return;
      var proj = _proj();
      if (proj && proj.personId === pid) _persistProjection(pid);
    }, 2000);
  }

  /* ───────────────────────────────────────────────────────────
     BIO BUILDER PERSISTENCE TRIGGER
  ─────────────────────────────────────────────────────────── */

  function _triggerBBPersist() {
    try {
      var core = window.LorevoxBioBuilderModules && window.LorevoxBioBuilderModules.core;
      if (core && core._persistDrafts && core._currentPersonId) {
        var pid = core._currentPersonId();
        if (pid) core._persistDrafts(pid);
      }
    } catch (e) {}
  }

  /* ───────────────────────────────────────────────────────────
     SYNC LOG — Audit trail for debugging and transparency
  ─────────────────────────────────────────────────────────── */

  function _logSync(fieldPath, action, fromValue, toValue, meta) {
    var proj = _proj();
    if (!proj) return;
    meta = meta || {};

    proj.syncLog.push({
      fieldPath: fieldPath,
      action:    action,
      fromValue: fromValue || "",
      toValue:   toValue || "",
      ts:        Date.now(),
      source:       meta.source || null,
      writeMode:    meta.writeMode || null,
      resultBucket: meta.resultBucket || null,
      confidence:   meta.confidence != null ? meta.confidence : null,
      personId: (typeof state !== "undefined" ? state.person_id : null),
      // WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 2.
      // meta.convId FIRST, falling back to the current conversation.
      //
      // A backend extraction result can arrive seconds late and out of
      // order, so `state.chat.conv_id` is not necessarily the
      // conversation the fact came from. Reading it unconditionally
      // stamped the audit log with whatever was open at write time --
      // the one field in this record whose entire job is to say where a
      // value originated.
      convId:   (meta && meta.convId)
                  ? meta.convId
                  : ((typeof state !== "undefined" && state.chat)
                      ? state.chat.conv_id : null)
    });

    if (proj.syncLog.length > SYNC_LOG_CAP) {
      proj.syncLog = proj.syncLog.slice(-SYNC_LOG_CAP);
    }
  }

  /* ───────────────────────────────────────────────────────────
     QUERY HELPERS — For interview.js and UI
  ─────────────────────────────────────────────────────────── */

  /**
   * Get the projected value for a field, or null if not projected.
   */
  function getValue(fieldPath) {
    var proj = _proj();
    if (!proj || !proj.fields[fieldPath]) return null;
    return proj.fields[fieldPath].value || null;
  }

  /**
   * Check if a field is locked (human-edited).
   */
  function isLocked(fieldPath) {
    var proj = _proj();
    if (!proj || !proj.fields[fieldPath]) return false;
    return !!proj.fields[fieldPath].locked;
  }

  /**
   * Get all pending suggestions (for UI rendering).
   */
  function getPendingSuggestions() {
    var proj = _proj();
    return (proj && proj.pendingSuggestions) ? proj.pendingSuggestions : [];
  }

  /**
   * Get the full sync log (for dev/debug panel).
   */
  function getSyncLog() {
    var proj = _proj();
    return (proj && proj.syncLog) ? proj.syncLog : [];
  }

  /**
   * Get overall projection stats.
   */
  function getStats() {
    var proj = _proj();
    if (!proj) return { total: 0, locked: 0, pending: 0 };
    var fields = proj.fields;
    var keys = Object.keys(fields);
    var locked = keys.filter(function (k) { return fields[k].locked; }).length;
    return {
      total: keys.length,
      locked: locked,
      pending: (proj.pendingSuggestions || []).length
    };
  }

  /* ───────────────────────────────────────────────────────────
     EXPORT
  ─────────────────────────────────────────────────────────── */

  window.LorevoxProjectionSync = {
    // Core write
    projectValue:        projectValue,
    batchProject:        batchProject,
    markHumanEdit:       markHumanEdit,

    // Suggestions
    acceptSuggestion:    acceptSuggestion,
    dismissSuggestion:   dismissSuggestion,
    getPendingSuggestions: getPendingSuggestions,

    // Narrator lifecycle
    resetForNarrator:    resetForNarrator,
    clearProjection:     clearProjection,

    // Query
    getValue:            getValue,
    isLocked:            isLocked,
    getSyncLog:          getSyncLog,
    getStats:            getStats,

    // Persistence
    forcePersist:        function () {
      var proj = _proj();
      if (proj && proj.personId) _persistProjection(proj.personId);
    },

    // Constants (for external access)
    LS_PROJ_PREFIX:      LS_PROJ_PREFIX
  };

  console.log("[Lorevox] Projection sync layer loaded.");

  // v8.1: Auto-initialize projection on load if a person is already active.
  // This fixes the race condition where loadPerson() runs before projection-sync.js
  // loads. When this script loads, if state.person_id is already set, we restore
  // projection state from localStorage immediately.
  (function _autoInitOnLoad() {
    if (typeof state !== "undefined" && state.person_id) {
      var proj = _proj();
      if (proj && !proj.personId) {
        console.log("[projection-sync] Auto-initializing for active person: " + state.person_id);
        resetForNarrator(state.person_id);
      }
    }
  })();

})();
