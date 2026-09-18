/* ═══════════════════════════════════════════════════════════════
   bio-builder-core.js — Shared foundation for Bio Builder modules
   Lorevox 9.0 — Phase 1 module split

   Owns:
     - state initialization and access (_ensureState, _bb)
     - narrator-scoped state reset and switch logic
     - localStorage persistence helpers (FT, LT, QQ)
     - shared utility helpers
     - active view tracking state

   Does NOT own:
     - questionnaire field definitions or rendering
     - extraction engine
     - FT/LT feature logic
     - candidate shaping

   Exposes: window.LorevoxBioBuilderModules.core
   Load order: BEFORE all other bio-builder-*.js modules
═══════════════════════════════════════════════════════════════ */

(function () {
  "use strict";

  window.LorevoxBioBuilderModules = window.LorevoxBioBuilderModules || {};

  /* ───────────────────────────────────────────────────────────
     STATE MODEL
     All Bio Builder state lives under state.bioBuilder.
     Scoped per narrator by personId.
     Never touches: state.archive, state.facts, state.timeline.
  ─────────────────────────────────────────────────────────── */

  /* ── BUG-208: Narrator-switch generation counter ─────────────
     Every reset/personChanged increments this.  Async restores stamp
     the value at call-time and verify it before applying — defends
     against a slow Christopher backend response landing AFTER a switch
     to Corky and overwriting Corky's questionnaire blob.
  ─────────────────────────────────────────────────────────── */
  var _narratorSwitchGen = 0;
  function _currentSwitchGen() { return _narratorSwitchGen; }

  function _ensureState() {
    if (typeof state === "undefined") return null;
    if (!state.bioBuilder) {
      state.bioBuilder = {
        personId:      null,
        quickItems:    [],   // [{id, text, type, ts}]  type: "fact"|"note"
        questionnaire: {},   // {sectionId: data}
        graph: { persons: {}, relationships: {} },  // Phase Q.1: canonical relationship graph
        sourceCards:   [],   // [{id, filename, fileSize, sourceType, ts, status,
                             //   extractedText, pastedText, detectedItems,
                             //   addedCandidateIds}]
                             //   status: "extracting"|"extracted"|"manual-only"|"failed"
        candidates: {
          people:        [],
          relationships: [],
          events:        [],
          memories:      [],
          places:        [],
          documents:     []
        }
      };
    }
    return state.bioBuilder;
  }

  function _bb() { return _ensureState(); }

  /* ───────────────────────────────────────────────────────────
     PERSISTENCE (v4+)
     Persist FT/LT/QQ drafts to localStorage per narrator.
     Keys: lorevox_ft_draft_{pid}, lorevox_lt_draft_{pid},
           lorevox_qq_draft_{pid}
     Schema version stamp for forward compat.
  ─────────────────────────────────────────────────────────── */

  var DRAFT_SCHEMA_VERSION = 1;

  /* ── QUESTIONNAIRE HYDRATION ────────────────────────────────────────
     BUG-BIO-QUESTIONNAIRE-LOSSY-ROUNDTRIP-01, browser-authority block.

       A cache may help the UI display something while authority is
       unavailable. It must never acquire authority merely because the
       authoritative read failed.

     `_restoreQuestionnaire` starts the backend fetch WITHOUT awaiting it
     and then returns the localStorage draft, so `bb.questionnaire` is the
     browser's copy for the whole in-flight window — and three paths left
     it there permanently: a failed fetch (the `.catch` only logged), an
     empty server response (ignored by a `Object.keys(q).length > 0`
     guard), and a failed PUT (localStorage was written regardless). A
     save then sent that copy to the server.

     The server can no longer be DESTROYED by this — merge_whole_document
     adds and modifies but cannot delete — but the browser could still
     show and submit a stale view, and on 2026-09-15 the browser held a
     damaged 7,046-byte draft that would have gone straight back over the
     repaired database the moment the UI opened.

     Four states. The difference between the last two is the entire point:

       "unhydrated"  no successful read. Writes refused.
       "cache"       the GET failed; localStorage is painting the screen.
                     Display only. Writes refused.
       "server"      a GET succeeded. The ONLY state that may write.
                     A confirmed-EMPTY server counts — empty is an answer.
       "conflict"    the server confirmed EMPTY while a local draft holds
                     content. Writes refused until resolved deliberately.
                     This is not paranoia: Janice's draft outlived a full
                     database erasure and restore, because the key is
                     `lorevox_qq_draft_<pid>` and narrator ids survive
                     export/restore verbatim. Auto-adopting it would have
                     resurrected erased data as a "save".

     Ported from projection-sync.js's `hydrated`, which has had this since
     WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01. */
  var _qqHydration = "unhydrated";
  function _qqHydrationState() { return _qqHydration; }
  function _setQqHydration(s, why) {
    if (_qqHydration === s) return;
    _qqHydration = s;
    console.log("[bb-core] questionnaire hydration -> " + s + (why ? " (" + why + ")" : ""));
  }

  var _LS_FT_PREFIX    = "lorevox_ft_draft_";
  var _LS_LT_PREFIX    = "lorevox_lt_draft_";
  var _LS_QQ_PREFIX    = "lorevox_qq_draft_";
  var _LS_QC_PREFIX    = "lorevox_qc_draft_";
  var _LS_DRAFT_INDEX  = "lorevox_draft_pids";

  /* ═══════════════════════════════════════════════════════════════════════
     BUG-BIO-QUESTIONNAIRE-NEW-NARRATOR-SAVE-LOCK-01  (2026-09-17)

     WHAT WENT WRONG

       Every narrator with no server questionnaire was locked out of saving,
       permanently, from the moment the form loaded. Observed live on a
       disposable narrator: hydration reached "server" correctly at 16:40:16,
       then moved to "conflict" at 16:40:18 — four minutes before the operator
       typed anything. Six typed values lived only in localStorage while the
       UI gave no sign anything was wrong.

     WHY

       The conflict branch asked _hasAnyValue(bb.questionnaire). That helper
       is SHALLOW:

           Object.keys(obj).some(k => obj[k] && String(obj[k]).trim() !== "")

       For a document shaped { personal: {...} } the value is an object, and
       String({}) === "[object Object]" — a non-empty string. So ANY section
       key counted as operator content:

           {}                                  -> false
           { personal: {} }                    -> TRUE
           { personal: { fullName: "" } }      -> TRUE

       Hydration itself creates that shape. So "the server says empty while
       this browser holds a draft with content" was true for every new
       narrator before a single keystroke.

     THE FIX HERE

       _hasOperatorContent — a DEEP check that means what the conflict branch
       always intended: is there a value a person typed? Blank strings are not
       content, and neither is bookkeeping. `_legacyMigrationVersion` and
       `_legacyRemovedSections` are written by the identity migration; they
       are the program talking to itself, and counting them as the operator's
       work is how a housekeeping marker came to veto a save.

     WHAT IS DELIBERATELY NOT WEAKENED

       The conflict guard exists for a real event: on 2026-09-15 a draft
       outlived a full database erasure and restore, because the key is
       lorevox_qq_draft_<pid> and narrator ids survive export verbatim.
       Adopting that draft would have resurrected erased data disguised as an
       ordinary save. That draft held REAL ANSWERS, so it still trips the
       guard after this change, and still requires a deliberate decision. An
       old draft is never promoted to authoritative on its own.

       A draft-provenance scheme was drafted here and removed. It would have
       distinguished never-persisted typing from previously-server-backed
       data, which sounds appealing but solves a problem this bug does not
       have: once the first save lands, the server is no longer empty and the
       branch cannot fire. The narrower fix is the correct one.

     THE SECOND, INDEPENDENT DEFECT — see _persistQuestionnaire below

       Fixing detection alone does NOT make the first save land. _saveSection
       calls _restoreQuestionnaire, which resets hydration to "unhydrated" and
       starts the GET WITHOUT awaiting it; _persistDrafts then runs
       synchronously, reads a state the in-flight GET has not yet settled, and
       refuses. Re-restoring on save is legitimate — it is how save guarantees
       fresh canonical state — but it must be awaited, not raced.
  ═══════════════════════════════════════════════════════════════════════ */

  /* Bookkeeping the program writes for itself. Not operator content, and
     never the basis for deciding a person has unsaved work. */
  function _isBookkeepingKey(k) {
    return typeof k === "string" && k.charAt(0) === "_";
  }

  /* Deep: does this document hold a value a person actually entered?

     Distinct from _hasAnyValue below, which is a shallow truthiness helper
     used elsewhere for other purposes and left alone on purpose. The conflict
     and blank-PUT decisions are about human work, so they ask this. */
  function _hasOperatorContent(doc) {
    if (doc === null || doc === undefined) return false;
    if (typeof doc === "string") return doc.trim() !== "";
    if (typeof doc === "number" || typeof doc === "boolean") return true;
    if (Array.isArray(doc)) {
      for (var i = 0; i < doc.length; i++) {
        if (_hasOperatorContent(doc[i])) return true;
      }
      return false;
    }
    if (typeof doc === "object") {
      var keys = Object.keys(doc);
      for (var j = 0; j < keys.length; j++) {
        if (_isBookkeepingKey(keys[j])) continue;
        if (_hasOperatorContent(doc[keys[j]])) return true;
      }
      return false;
    }
    return false;
  }

  /* The draft is written on EVERY path, including every failure path. Losing
     the operator's typing is the one outcome worse than refusing to save it. */
  function _writeQqDraft(pid, doc) {
    try {
      localStorage.setItem(_LS_QQ_PREFIX + pid,
        JSON.stringify({ v: DRAFT_SCHEMA_VERSION, d: doc }));
      return true;
    } catch (e) { return false; }
  }

  /* ── Hydration settle ────────────────────────────────────────────────
     _restoreQuestionnaireFromBackend resolves this for the pid it answered
     for. A save awaits it so it reads a settled state instead of racing the
     GET it just started. Never rejects: a failed GET settles as "cache", and
     the caller's job is to refuse the write, not to crash. */
  /* Each gate carries the TOKEN of the read that opened it.

     BUG-BIO-QUESTIONNAIRE-STALE-SETTLE-01 (2026-09-18) — this settled by
     narrator id alone. Restores overlap routinely: _sectionFillCount calls
     the canonical restore during render, and _saveSection calls it again
     immediately before saving. With two GETs in flight for one narrator, the
     FIRST response released the SECOND read's gate, and a save waiting on the
     newer read proceeded on the older answer. Worst case it reads "server"
     from a response that predates an erasure.

     A response may now only settle the gate it belongs to. A late response
     from a superseded read is ignored, exactly as its document already is by
     guards A/B/C. */
  var _qqSettle = Object.create(null);
  var _qqReadToken = 0;

  function _qqOpenGate(pid) {
    var token = ++_qqReadToken;
    var gate = { token: token, promise: null, resolve: null };
    gate.promise = new Promise(function (res) { gate.resolve = res; });
    _qqSettle[pid] = gate;
    return token;
  }

  function _qqHydrationSettled(pid) {
    if (!pid) return Promise.resolve(_qqHydration);
    if (!_qqSettle[pid]) _qqOpenGate(pid);
    return _qqSettle[pid].promise;
  }

  function _qqMarkSettled(pid, state, token) {
    if (!pid) return;
    var gate = _qqSettle[pid];
    if (!gate) {
      _qqSettle[pid] = { token: token || 0, promise: Promise.resolve(state), resolve: null };
      return;
    }
    // A superseded read must not release a newer read's gate.
    if (token !== undefined && gate.token !== token) {
      console.warn("[bb-drift] stale settle IGNORED for " + String(pid).slice(0, 8) +
        " (response token=" + token + " current gate=" + gate.token + ")");
      return;
    }
    if (gate.resolve) {
      gate.resolve(state);
      gate.resolve = null;
    }
  }

  /* ── Which empty server are we looking at? ────────────────────────────
     BUG-BIO-QUESTIONNAIRE-FIRST-SAVE-IMPOSSIBLE-01 (2026-09-18)

     With detection fixed, the guard still made the first save on a fresh
     narrator logically impossible:

         to save you must have typed something
         typed content + empty server = conflict
         conflict = refuse

     _saveSection re-restores before saving. The GET truthfully answers
     "this narrator has no questionnaire", the operator's new typing is in
     memory, and the branch fires. Observed live on ZZ WALKTHROUGH: a correct
     red banner, and a save that could never succeed no matter how many times
     it was attempted.

     The erasure case and this one differ in a fact we already hold. On
     2026-09-15 the page LOADED holding a draft of real answers and only then
     learned the server was empty — the content predates the knowledge, so it
     might be resurrected data. Here we confirmed the server was empty FIRST,
     with nothing in memory, and the content arrived afterwards by hand. Work
     typed after a confirmed-empty read cannot be a resurrection of anything.

     So: remember, per narrator and only for this page session, that we have
     already seen this narrator's questionnaire confirmed empty while holding
     nothing. A later empty answer for that narrator is then the same empty we
     already accepted, not a new discovery that should veto the operator's
     afternoon.

     Deliberately session-scoped and in memory. It is not written to
     localStorage, so it cannot itself outlive an erasure — which is the
     property that made the draft dangerous in the first place. A page reload
     between typing and saving clears it, and that genuinely ambiguous case
     goes back to conflict, where it belongs. */
  var _qqServerConfirmedEmpty = Object.create(null);

  /* ── Uncommitted operator edits ───────────────────────────────────────
     BUG-BIO-QUESTIONNAIRE-GET-CLOBBERS-EDITS-01.

     Set when a form commits typed values into bb.questionnaire; cleared when
     a save is CONFIRMED by the server. While set, an arriving server document
     is not allowed to replace what is in memory.

     Distinct from "there is content in memory", which a localStorage draft
     also satisfies — and a stale draft must NOT be allowed to override a
     newer server document. This flag means specifically: a person typed this,
     here, since the last confirmed save. */
  var _qqDirty = Object.create(null);

  function _markQuestionnaireEdited(pid) {
    if (pid) _qqDirty[pid] = true;
  }

  /* A new restore for a pid opens a fresh settle gate, so a save started
     after it waits for THAT read rather than an older resolved one. Returns
     the token the read must quote when it settles. */
  function _qqResetSettle(pid) {
    if (!pid) return 0;
    return _qqOpenGate(pid);
  }

  /* ═══════════════════════════════════════════════════════════════════════
     BUG-BIO-QUESTIONNAIRE-SILENT-SAVE-FAILURE-01  (2026-09-17)

     The questionnaire PUT was fire-and-forget:

         fetch(API.BB_QQ_PUT, {...}).catch(e => console.warn(...));

     Nothing was returned to the caller in the success path, the refusal path,
     or the HTTP-error path. _saveSection therefore could not tell a confirmed
     write from a refusal, a dead server, or a 409 from the merge layer — so it
     re-rendered and the operator read silence as success. Six typed values sat
     in localStorage for sixteen minutes while the UI showed a saved form.

     A save that cannot fail visibly is not a save. This returns a promise of
     an outcome, and the caller is expected to show it:

       saved        the server accepted the bytes and echoed a revision
       refused      hydration is not "server" — we will not write what we
                    could not first read
       conflict     409 from the merge layer; someone else changed these
                    paths
       http_error   the server answered, and said no
       network      the server could not be reached at all
       blocked      pid / active-narrator mismatch; never cross-write
       blank        nothing in the document to save

     Only "saved" may be reported to a person as saved.
  ═══════════════════════════════════════════════════════════════════════ */

  var _qqLastOutcome = null;

  function _persistQuestionnaire(pid, qq, ticket) {
    // Every outcome is stamped with the operation it belongs to, so a
    // caller can refuse an answer about somebody else's save.
    var _stamp = function (o) { o.pid = pid; o.ticket = ticket; return o; };
    // Wait for the read to settle before deciding. _saveSection calls
    // _restoreQuestionnaire immediately before this, which resets hydration
    // to "unhydrated" and starts a GET; reading the state synchronously here
    // raced that GET and refused every first save on a new narrator.
    return _qqHydrationSettled(pid).then(function (state) {
      if (state !== "server") {
        var why = (state === "conflict")
          ? "This browser holds unsaved answers for a narrator the server says has no questionnaire. That has to be resolved deliberately — saving would decide it silently."
          : "The server could not be read, so it is not safe to write over it. Check the connection and reload, then save again.";
        console.warn("[bb-core] REFUSED questionnaire PUT: hydration=" + state +
          " for pid=" + pid.slice(0, 8) + " — " + why);
        return _stamp({
          ok: false, outcome: "refused", saved: false, hydration: state,
          message: "Not saved. " + why
        });
      }
      return fetch(API.BB_QQ_PUT, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          person_id: pid, questionnaire: qq,
          source: "ui_save", version: DRAFT_SCHEMA_VERSION
        })
      }).then(function (r) {
        return r.text().then(function (body) {
          var j = null;
          try { j = JSON.parse(body); } catch (e) {}
          if (r.status === 409) {
            var paths = (j && j.conflicting_paths) || [];
            return _stamp({
              ok: false, outcome: "conflict", saved: false, status: 409,
              conflicting_paths: paths,
              message: "Not saved — the server has newer answers for " +
                (paths.length ? paths.length + " field(s)" : "this narrator") +
                ". Reload to see them before saving again."
            });
          }
          if (!r.ok) {
            return _stamp({
              ok: false, outcome: "http_error", saved: false, status: r.status,
              message: "Not saved — the server refused the write (HTTP " + r.status + ")."
            });
          }
          // Confirmed. This is the ONLY branch that may say saved.
          //
          // Both flags are cleared HERE and nowhere else on the success path,
          // because a confirmed write is the only event that makes either
          // premise false: the edits are no longer uncommitted, and the
          // server is no longer empty. Clearing them on an attempt rather
          // than on a confirmation would discard the protection at exactly
          // the moment a failed save needs it.
          delete _qqDirty[pid];
          delete _qqServerConfirmedEmpty[pid];
          // The server distinguishes a write from a no-op — merge_whole_document
          // returns write_applied:false when the incoming document is identical
          // to the stored one, and deliberately does not burn a revision or an
          // audit row on it. The UI was discarding that and reporting both
          // cases as "Saved", so an operator could not tell whether their edit
          // had actually gone in or whether the form had simply resubmitted
          // what was already there. Say which happened.
          var applied = !(j && j.write_applied === false);
          return _stamp({
            ok: true, saved: true, status: r.status,
            outcome: applied ? "saved" : "nochange",
            write_applied: applied,
            revision: j && j.revision,
            ignored_blank_paths: (j && j.ignored_blank_paths) || [],
            message: applied
              ? ("Saved" + (j && j.revision !== undefined ? " (revision " + j.revision + ")" : "") + ".")
              : ("No changes to save — this section already matches what is stored" +
                 (j && j.revision !== undefined ? " (revision " + j.revision + ")" : "") + ".")
          });
        });
      }).catch(function (e) {
        console.warn("[bb-core] Backend QQ persist failed", e);
        return _stamp({
          ok: false, outcome: "network", saved: false,
          message: "Not saved — could not reach the server. Your answers are kept in this browser; try again once it is back."
        });
      });
    });
  }

  /* The last questionnaire save's outcome, as a promise.

     _persistDrafts has around twenty callers across five modules, most of
     which persist family tree or life threads and have no interest in the
     questionnaire; changing its signature would touch all of them. Callers
     that DO care — the save buttons — read this.

     THE HAZARD, and why the ticket below exists. This is ONE shared slot. Two
     overlapping saves and the second overwrites the first's outcome, so a
     banner can report a result belonging to a different save. Raised in
     review 2026-09-18; not observed in Chrome, but it is a real property of
     the code and the comment above was a justification for convenience, not
     an argument that it is safe.

     Mitigated here rather than left to luck: every outcome now carries the
     pid and a monotonic ticket, and `_qqSaveOutcomeFor(pid, ticket)` refuses
     to hand back an outcome that does not belong to the operation asking.
     A caller that asks for its own ticket cannot be told about someone
     else's save. */
  var _qqSaveTicket = 0;

  function _qqSaveOutcome() {
    return _qqLastOutcome || Promise.resolve({
      ok: false, outcome: "none", saved: false,
      message: "No questionnaire save has been attempted."
    });
  }

  /* Ask about YOUR save, not the most recent one.

     Returns the outcome only if the slot still holds the operation identified
     by `ticket` for `pid`. If a newer save has replaced it, this reports
     "superseded" rather than another operation's verdict — the caller then
     says nothing rather than something confidently wrong about work it did
     not do. */
  function _qqSaveOutcomeFor(pid, ticket) {
    return _qqSaveOutcome().then(function (res) {
      if (!res || res.ticket === undefined) return res;
      if (res.ticket !== ticket || (pid && res.pid && res.pid !== pid)) {
        return {
          ok: false, outcome: "superseded", saved: false, ticket: ticket,
          message: "This save was overtaken by a newer one; its result is not known."
        };
      }
      return res;
    });
  }

  function _persistDrafts(pid) {
    if (!pid) return;
    var bb = _bb(); if (!bb) return;
    try {
      var ft = bb.familyTreeDraftsByPerson && bb.familyTreeDraftsByPerson[pid];
      var lt = bb.lifeThreadsDraftsByPerson && bb.lifeThreadsDraftsByPerson[pid];
      if (ft) localStorage.setItem(_LS_FT_PREFIX + pid, JSON.stringify({ v: DRAFT_SCHEMA_VERSION, d: ft }));
      if (lt) localStorage.setItem(_LS_LT_PREFIX + pid, JSON.stringify({ v: DRAFT_SCHEMA_VERSION, d: lt }));
      // Phase G: persist questionnaire to BACKEND (canonical authority)
      // FT/LT stay in localStorage; QQ goes backend-first with localStorage as transient fallback.
      // BUG-208: Hard-stop if the requested pid does not match the active
      // narrator — never cross-write one narrator's blob under another's id.
      if (pid !== bb.personId) {
        console.warn("[bb-drift] _persistDrafts BLOCKED: pid=" + (pid || "").slice(0, 8) +
          " !== bb.personId=" + ((bb.personId || "").slice(0, 8) || "null") +
          " — refusing to persist to avoid cross-narrator contamination");
        _qqLastOutcome = Promise.resolve({
          pid: pid, ticket: ++_qqSaveTicket,
          ok: false, outcome: "blocked", saved: false,
          message: "Not saved — the active narrator changed while saving. Reopen this narrator and save again."
        });
      } else {
        var qq = bb.questionnaire;
        // BUG-FE-HYDRATION-CROSS-NARRATOR-LEAK-01 (2026-06-16):
        // Refuse to PUT a questionnaire whose every section's every
        // field is empty. The previous narrator-switch persist path
        // would write {personal:{fullName:"",dob:"",...}} on top of
        // canonical truth, silently wiping the operator's intake data.
        // The shape's KEYS exist (because hydration created them) but
        // the VALUES are empty, so the legacy "Object.keys(qq).length"
        // guard wouldn't catch this. Walk the values and refuse the
        // PUT when there's nothing but blanks.
        // Was a 30-line inline copy of this walk, which had drifted from the
        // one the conflict branch used — two "is there anything here" answers
        // that could disagree about the same document. One function now, and
        // it ignores bookkeeping keys, so the identity migration's markers no
        // longer read as a reason to PUT (or to refuse one).
        var hasAnyValue = _hasOperatorContent(qq);
        // The draft is written FIRST, on every path. Whatever the server
        // does next, the operator's typing survives a refresh.
        if (qq && Object.keys(qq).length > 0) _writeQqDraft(pid, qq);

        if (qq && Object.keys(qq).length > 0 && hasAnyValue) {
          _qqLastOutcome = _persistQuestionnaire(pid, qq, ++_qqSaveTicket);
        } else if (qq && Object.keys(qq).length > 0) {
          console.warn("[bb-drift] _persistDrafts SKIPPED PUT: questionnaire " +
            "has keys but every field is empty — refusing to clobber " +
            "canonical truth with blanks (pid=" + pid.slice(0, 8) + ")");
          _qqLastOutcome = Promise.resolve({
            pid: pid, ticket: ++_qqSaveTicket,
            ok: false, outcome: "blank", saved: false,
            message: "Nothing to save — every field in this questionnaire is empty."
          });
        }
      }
      // Phase M: persist Quick Capture inbox
      if (pid === bb.personId && bb.quickItems && bb.quickItems.length > 0) {
        localStorage.setItem(_LS_QC_PREFIX + pid, JSON.stringify({ v: DRAFT_SCHEMA_VERSION, d: bb.quickItems }));
      }
      // Track which pids have drafts
      var idx = _getDraftIndex();
      if (idx.indexOf(pid) < 0) {
        idx.push(pid);
        localStorage.setItem(_LS_DRAFT_INDEX, JSON.stringify(idx));
      }
    } catch (e) {
      // localStorage full or unavailable — degrade silently
    }
  }

  function _loadDrafts(pid) {
    if (!pid) return;
    var bb = _bb(); if (!bb) return;
    if (!bb.familyTreeDraftsByPerson) bb.familyTreeDraftsByPerson = {};
    if (!bb.lifeThreadsDraftsByPerson) bb.lifeThreadsDraftsByPerson = {};
    // Phase M: restore Quick Capture inbox
    try {
      var qcRaw = localStorage.getItem(_LS_QC_PREFIX + pid);
      if (qcRaw) {
        var qcObj = JSON.parse(qcRaw);
        var qcD = qcObj && (qcObj.d || qcObj.data);
        if (qcD && Array.isArray(qcD) && qcD.length > 0) {
          bb.quickItems = qcD;
          console.log("[bb-core] ✅ Restored " + qcD.length + " Quick Capture items for " + pid.slice(0, 8));
        }
      }
    } catch (e) {
      console.warn("[bb-core] QC restore error for pid=" + pid, e);
    }
    // v8-fix: load questionnaire via canonical restore helper (Phase 1.1)
    _restoreQuestionnaire(pid);
    // Don't overwrite FT/LT if already in memory
    if (bb.familyTreeDraftsByPerson[pid] && bb.familyTreeDraftsByPerson[pid].nodes && bb.familyTreeDraftsByPerson[pid].nodes.length) return;
    try {
      var ftRaw = localStorage.getItem(_LS_FT_PREFIX + pid);
      if (ftRaw) {
        var ftObj = JSON.parse(ftRaw);
        var ftD = ftObj && (ftObj.d || ftObj.data);
        if (ftD && Array.isArray(ftD.nodes)) {
          bb.familyTreeDraftsByPerson[pid] = ftD;
        }
      }
      var ltRaw = localStorage.getItem(_LS_LT_PREFIX + pid);
      if (ltRaw) {
        var ltObj = JSON.parse(ltRaw);
        var ltD = ltObj && (ltObj.d || ltObj.data);
        if (ltD && Array.isArray(ltD.nodes)) {
          bb.lifeThreadsDraftsByPerson[pid] = ltD;
        }
      }
    } catch (e) {
      // Malformed data — ignore, let lazy init create fresh
    }
  }

  /* ── Phase L.1: Rehydrate candidates from questionnaire ────
     After narrator switch restores the questionnaire, re-run
     candidate extraction so the Candidates tab is never empty
     for a narrator that has questionnaire data.
     Idempotent — extraction dedup prevents doubling.
  ─────────────────────────────────────────────────────────── */
  function _rehydrateCandidates(pid) {
    var bb = _bb(); if (!bb) return;
    var qq = bb.questionnaire;
    if (!qq || Object.keys(qq).length === 0) return;

    var qqMod = window.LorevoxBioBuilderModules &&
                window.LorevoxBioBuilderModules.questionnaire;
    if (!qqMod || typeof qqMod._extractQuestionnaireCandidates !== "function") {
      console.log("[bb-core] Questionnaire module not loaded — skipping candidate rehydration");
      return;
    }

    // Ensure fresh candidate container
    if (!bb.candidates || !bb.candidates.people) {
      bb.candidates = {
        people: [], relationships: [], events: [],
        memories: [], places: [], documents: []
      };
    }

    // Phase Q+: added spouse to candidate rehydration pipeline
    var sections = ["parents", "grandparents", "siblings", "children", "spouse", "earlyMemories"];
    var before = bb.candidates.people.length + bb.candidates.relationships.length + bb.candidates.memories.length;
    sections.forEach(function (s) {
      if (qq[s]) qqMod._extractQuestionnaireCandidates(s);
    });
    var after = bb.candidates.people.length + bb.candidates.relationships.length + bb.candidates.memories.length;
    if (after > before) {
      console.log("[bb-core] ✅ Rehydrated " + (after - before) + " QQ candidates for " + pid);
    }

    // Phase M: also rehydrate candidates from persisted Quick Capture items
    var qcMod = window.LorevoxBioBuilderModules &&
                window.LorevoxBioBuilderModules._qcPipeline;
    if (qcMod && typeof qcMod.rehydrateQCCandidates === "function") {
      qcMod.rehydrateQCCandidates(bb);
    }
  }

  function _getDraftIndex() {
    try {
      var raw = localStorage.getItem(_LS_DRAFT_INDEX);
      if (raw) { var arr = JSON.parse(raw); if (Array.isArray(arr)) return arr; }
    } catch (e) {}
    return [];
  }

  function _clearDrafts(pid) {
    if (!pid) return;
    try {
      localStorage.removeItem(_LS_FT_PREFIX + pid);
      localStorage.removeItem(_LS_LT_PREFIX + pid);
      localStorage.removeItem(_LS_QQ_PREFIX + pid);
      localStorage.removeItem(_LS_QC_PREFIX + pid);
      var idx = _getDraftIndex().filter(function (p) { return p !== pid; });
      localStorage.setItem(_LS_DRAFT_INDEX, JSON.stringify(idx));
    } catch (e) {}
  }

  /* ── Phase G: Canonical questionnaire restore helper ─────────
     Single restore path for narrator-scoped questionnaire state.
     Backend is the authority; localStorage is transient fallback only.
     Returns the restored object.
     MUST be the only path that reads qq.
  ─────────────────────────────────────────────────────────── */
  function _restoreQuestionnaire(pid) {
    var bb = _bb(); if (!bb) return {};
    // Until the backend answers for THIS narrator we know nothing about
    // them. Reset first: without it the state survives a narrator switch,
    // and a "server" left over from the previous narrator would authorise
    // writing THIS one's cached draft — the same defect arriving through
    // the switch instead of the read.
    _setQqHydration("unhydrated", "restore started for " + String(pid).slice(0, 8));
    // Open a FRESH settle gate for this read. A save started after this
    // restore must wait for THIS answer, not be released by a stale one
    // resolved by an earlier restore of the same narrator.
    var _readToken = _qqResetSettle(pid);
    if (!pid) { bb.questionnaire = {}; return bb.questionnaire; }

    // Phase G: Try backend first (async, fire-and-forget for sync callers)
    // The backend load is async so we start it and also load localStorage
    // as immediate fallback. When backend responds it overwrites if non-empty.
    _restoreQuestionnaireFromBackend(pid, _readToken);

    // Immediate: read transient localStorage draft
    try {
      var raw = localStorage.getItem(_LS_QQ_PREFIX + pid);
      if (raw) {
        var parsed = JSON.parse(raw);
        var d = parsed && (parsed.d || parsed.data);
        // Guard against double-wrapped drafts: { v, d: { v, d: {sections} } }
        // If d looks like another envelope (has .v and .d), unwrap one more level
        if (d && typeof d === "object" && d.v !== undefined && d.d && typeof d.d === "object") {
          console.warn("[bb-core] Unwrapping double-wrapped localStorage draft for pid=" + pid);
          d = d.d;
          // Fix the localStorage so it doesn't happen again
          localStorage.setItem(_LS_QQ_PREFIX + pid, JSON.stringify({ v: DRAFT_SCHEMA_VERSION, d: d }));
        }
        if (d && typeof d === "object") {
          bb.questionnaire = d;
          // PAINTING THE SCREEN, NOT ACQUIRING AUTHORITY. The backend fetch
          // started above is still in flight; until it answers this copy may
          // be displayed and may not be saved.
          _setQqHydration("cache", "localStorage draft shown while the server is asked");
          _qqDebugSnapshot("restore_ls", pid, bb);
          return bb.questionnaire;
        }
      }
    } catch (e) {
      console.warn("[bb-core] _restoreQuestionnaire parse error for pid=" + pid, e);
    }
    // Fallback: keep current if non-empty, else reset
    if (!bb.questionnaire || Object.keys(bb.questionnaire).length === 0) {
      bb.questionnaire = {};
    }
    _qqDebugSnapshot("restore_fallback", pid, bb);
    return bb.questionnaire;
  }

  /* ── Phase G: Backend questionnaire restore (async) ────────
     Fetches canonical QQ from backend and overwrites in-memory
     state if the backend has data. Non-blocking.

     BUG-208: Stamps the narrator-switch generation + requested pid
     at call-time.  When the response resolves, three guards must all
     hold before the response is applied:
       (a) the switch generation hasn't advanced (no narrator switch
           happened during the in-flight request),
       (b) bb.personId still equals the requested pid,
       (c) the backend response's person_id field equals the requested pid.
     If any guard fails, log [bb-drift] and discard the response.
  ─────────────────────────────────────────────────────────── */
  function _restoreQuestionnaireFromBackend(pid, readToken) {
    if (!pid || typeof API === "undefined" || !API.BB_QQ_GET) {
      // Nothing will ever answer for this pid, so anything awaiting the gate
      // must be released rather than left hanging. It settles as the CURRENT
      // state, which is not "server", so a waiting save still refuses.
      _qqMarkSettled(pid, _qqHydration, readToken);
      return;
    }
    var stampedGen = _narratorSwitchGen;
    var stampedPid = pid;
    fetch(API.BB_QQ_GET(pid))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        // EVERY exit below settles the gate. A save that awaits hydration and
        // is never released would hang with the operator's work unsaved and
        // no message — which is the failure this whole repair exists to end.
        if (!j) { _qqMarkSettled(stampedPid, _qqHydration, readToken); return; }
        var bb = _bb(); if (!bb) { _qqMarkSettled(stampedPid, _qqHydration, readToken); return; }
        // Guard A: switch generation
        if (_narratorSwitchGen !== stampedGen) {
          console.warn("[bb-drift] backend QQ response DISCARDED: narrator switch happened during fetch " +
            "(stampedGen=" + stampedGen + " currentGen=" + _narratorSwitchGen + " stampedPid=" +
            stampedPid.slice(0, 8) + ")");
          _qqMarkSettled(stampedPid, _qqHydration, readToken);
          return;
        }
        // Guard B: in-memory pid
        if (bb.personId !== stampedPid) {
          console.warn("[bb-drift] backend QQ response DISCARDED: bb.personId moved during fetch " +
            "(stampedPid=" + stampedPid.slice(0, 8) + " bb.personId=" +
            ((bb.personId || "").slice(0, 8) || "null") + ")");
          _qqMarkSettled(stampedPid, _qqHydration, readToken);
          return;
        }
        // Guard C: backend echoed person_id matches request
        if (j.person_id && j.person_id !== stampedPid) {
          console.warn("[bb-drift] backend QQ response DISCARDED: response.person_id mismatch " +
            "(requested=" + stampedPid.slice(0, 8) + " response=" + (j.person_id || "").slice(0, 8) + ")");
          _qqMarkSettled(stampedPid, _qqHydration, readToken);
          return;
        }
        // THE SERVER ANSWERED. That is true even when the answer is "this
        // narrator has no questionnaire" — `get_questionnaire` returns an
        // empty document rather than failing, and "the server says there is
        // nothing" must never be confused with "I could not ask".
        var q = (j && j.questionnaire) || {};
        var serverEmpty = !(typeof q === "object" && Object.keys(q).length > 0);
        if (serverEmpty) {
          var localHas = (function () {
            try {
              var cur = bb.questionnaire;
              // BUG-BIO-QUESTIONNAIRE-NEW-NARRATOR-SAVE-LOCK-01.
              //
              // This asked _hasAnyValue, which is shallow: it stringifies
              // each top-level value, and String({}) is "[object Object]" —
              // a non-empty string. So { personal: {} } counted as content,
              // and hydration CREATES that shape. Every narrator without a
              // server questionnaire was therefore declared to be holding an
              // unsaved draft before a key was pressed, and locked out of
              // saving for the life of the page.
              //
              // _hasOperatorContent walks to the leaves and ignores the
              // bookkeeping the migration writes for itself. The question
              // this branch needs answered has always been "did a person
              // type something here", and now that is the question it asks.
              return !!(cur && typeof cur === "object" && _hasOperatorContent(cur));
            } catch (e) { return false; }
          })();
          if (localHas && _qqServerConfirmedEmpty[stampedPid]) {
            // We already established, earlier in THIS page session and while
            // holding nothing, that this narrator has no questionnaire. The
            // content in memory therefore arrived after that read — it was
            // typed, not resurrected. Same empty server, already accepted.
            _setQqHydration("server",
              "server still reports empty; the content in memory was typed after we confirmed that");
            _qqMarkSettled(stampedPid, "server", readToken);
          } else if (localHas) {
            // The dangerous case, and the reason this state exists. On
            // 2026-09-15 a draft outlived a full database erasure and
            // restore: the key is lorevox_qq_draft_<pid> and narrator ids
            // survive export/restore verbatim. Adopting it would resurrect
            // erased data under the name of an ordinary save, so writes are
            // refused until somebody decides on purpose.
            //
            // Reached when the page arrived ALREADY holding this content —
            // the content predates our knowledge of the server, so it cannot
            // be vouched for.
            _setQqHydration("conflict",
              "server reports EMPTY while a local draft holds real answers");
            _qqMarkSettled(stampedPid, "conflict", readToken);
            console.warn("[bb-core] questionnaire CONFLICT for " + stampedPid.slice(0, 8) +
              ": the server has no questionnaire for this narrator, but this browser " +
              "holds a draft with content. Saving is refused. The draft is still in " +
              "localStorage under " + _LS_QQ_PREFIX + stampedPid + " if it is wanted.");
          } else {
            _setQqHydration("server", "server confirms this narrator has no questionnaire");
            // Confirmed empty while holding NOTHING. Anything typed from here
            // on is this operator's own work, and a later empty answer for
            // this narrator must not be read as a fresh discovery.
            _qqServerConfirmedEmpty[stampedPid] = true;
            _qqMarkSettled(stampedPid, "server", readToken);
          }
          return;
        }
        if (typeof q === "object" && Object.keys(q).length > 0) {
          // Unwrap { v, d } envelope if present — backend stores { v:1, d:{sections} }
          // but bb.questionnaire expects flat sections { personal:{}, parents:[], ... }
          var sections = (q.d && typeof q.d === "object" && !Array.isArray(q.d)) ? q.d : q;

          // The server has a questionnaire, so an earlier "confirmed empty"
          // for this narrator is now false and must not keep authorising
          // anything. Left set, it would vouch for a localStorage draft after
          // a server-side erasure — the 2026-09-15 case, re-opened by a stale
          // flag. Clear it the moment the premise stops holding.
          delete _qqServerConfirmedEmpty[stampedPid];

          // BUG-BIO-QUESTIONNAIRE-GET-CLOBBERS-EDITS-01 (2026-09-18)
          //
          // This was an unconditional `bb.questionnaire = sections`. Every
          // restore that found a server document replaced whatever was in
          // memory — including edits the operator had typed while the GET was
          // in flight. _saveSection restores immediately before saving, so
          // the window is not theoretical: type, save, and the GET could land
          // between the two and quietly drop the edit.
          //
          // It matters most for records that ALREADY have a server document,
          // which is every real narrator. The new-narrator case never reached
          // this branch, which is why two days of testing on an empty record
          // never showed it.
          //
          // When the operator has uncommitted edits we keep THEIR document and
          // still record a successful read. Nothing is lost server-side by
          // doing so: merge_whole_document applies an incoming document as
          // mutations with no removals, so sections absent from the operator's
          // copy are left standing rather than deleted.
          if (_qqDirty[stampedPid] && _hasOperatorContent(bb.questionnaire)) {
            console.warn("[bb-core] server document NOT adopted for " +
              stampedPid.slice(0, 8) + ": this browser holds unsaved edits. " +
              "Keeping them; the save will merge against canonical server-side.");
          } else {
            bb.questionnaire = sections;
          }
          // The server answered with content and we have adopted it. This is
          // the only state in which a save may travel.
          _setQqHydration("server", "adopted the server document");
          _qqMarkSettled(stampedPid, "server", readToken);
          // WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 Phase 2 — capture
          // the per-field {status, source} metadata so the renderer can
          // surface status badges + a filled-skip counter. Legacy blob
          // responses have no _meta key; default to {} so callers can
          // always read `bb.questionnaire_meta[sectionId]` safely.
          bb.questionnaire_meta = (j._meta && typeof j._meta === "object")
            ? j._meta : {};
          bb.questionnaire_source = j.source || "legacy_blob";
          console.log("[bb-core] ✅ Questionnaire restored from backend for " + stampedPid.slice(0, 8)
            + " (source=" + bb.questionnaire_source + ")");
          // Update transient localStorage to match backend (wrap in { v, d } for localStorage format)
          try {
            localStorage.setItem(_LS_QQ_PREFIX + stampedPid, JSON.stringify({ v: DRAFT_SCHEMA_VERSION, d: sections }));
          } catch (e) {}
          // BUG-BIO-BUILDER-FALSE-DRIFT-WARNING-01 (2026-07-07): the
          // snapshot used to run BEFORE the setItem above, so mem/disk
          // key comparison fired KEY MISMATCH on every backend restore
          // (disk still empty at snapshot time). Snapshot AFTER the
          // mirror write so it only warns on real persistence drift.
          _qqDebugSnapshot("restore_backend", stampedPid, bb);
        }
        // Any shape that reached here without an explicit settle above.
        _qqMarkSettled(stampedPid, _qqHydration, readToken);
      })
      .catch(function (e) {
        console.warn("[bb-core] Backend QQ restore failed (using localStorage fallback)", e);
        // The GET failed. Hydration stays "cache" or "unhydrated" — either
        // way not "server" — so a waiting save will refuse and SAY SO.
        // Releasing the gate is what turns a hang into a message.
        _qqMarkSettled(stampedPid, _qqHydration, readToken);
      });
  }

  /* ── Phase 2.5: Questionnaire debug snapshot helper ────────
     Emits a compact console log showing in-memory vs persisted
     section counts. Active in dev mode (localhost or ?debug).
  ─────────────────────────────────────────────────────────── */
  var _qqDebugEnabled = (function () {
    try {
      var loc = window.location;
      return loc.hostname === "localhost" || loc.hostname === "127.0.0.1"
        || (loc.search && loc.search.indexOf("debug") >= 0);
    } catch (_) { return false; }
  })();

  function _qqDebugSnapshot(action, pid, bb) {
    if (!_qqDebugEnabled) return;
    if (!bb) bb = _bb();
    if (!bb) return;

    // Count in-memory sections
    var memCounts = {};
    var q = bb.questionnaire || {};
    Object.keys(q).forEach(function (k) {
      var v = q[k];
      memCounts[k] = Array.isArray(v) ? v.length : (v && typeof v === "object" ? Object.keys(v).filter(function (fk) { return v[fk] && String(v[fk]).trim(); }).length : 0);
    });

    // Count persisted sections
    var persCounts = {};
    try {
      var raw = localStorage.getItem(_LS_QQ_PREFIX + (pid || ""));
      if (raw) {
        var parsed = JSON.parse(raw);
        var d = parsed && (parsed.d || parsed.data);
        if (d && typeof d === "object") {
          Object.keys(d).forEach(function (k) {
            var v = d[k];
            persCounts[k] = Array.isArray(v) ? v.length : (v && typeof v === "object" ? Object.keys(v).filter(function (fk) { return v[fk] && String(v[fk]).trim(); }).length : 0);
          });
        }
      }
    } catch (_) {}

    console.log("[bb-debug] %c" + action, "color:#6366f1;font-weight:bold", {
      ts: new Date().toISOString().slice(11, 23),
      pid: (pid || "none").slice(0, 8),
      mem: memCounts,
      disk: persCounts,
      section: (_viewState && _viewState.activeSection) || null
    });

    // Phase 2.5.2: Mismatch warning
    var memKeys = Object.keys(memCounts).sort().join(",");
    var persKeys = Object.keys(persCounts).sort().join(",");
    if (memKeys !== persKeys) {
      console.warn("[bb-drift] KEY MISMATCH after '" + action + "': mem=[" + memKeys + "] disk=[" + persKeys + "]");
    } else {
      Object.keys(memCounts).forEach(function (k) {
        if (memCounts[k] !== persCounts[k]) {
          console.warn("[bb-drift] COUNT MISMATCH '" + k + "' after '" + action + "': mem=" + memCounts[k] + " disk=" + persCounts[k]);
        }
      });
    }
  }

  /* ── v8 Narrator-switch hard reset ─────────────────────────
     Called from app.js lvxSwitchNarratorSafe() BEFORE profile
     hydration.  Runs even when Bio Builder popover is closed.
  ─────────────────────────────────────────────────────────── */
  function _resetNarratorScopedState(newId) {
    var bb = _bb(); if (!bb) return;

    // BUG-208: bump generation FIRST so any in-flight async restores stamped
    // under the OLD pid see a stale generation when they resolve and discard.
    _narratorSwitchGen += 1;

    // v8-fix: persist outgoing narrator's questionnaire before clearing (WD-1 fix)
    // Phase M: also persists Quick Capture inbox
    var outgoingPid = bb.personId;
    if (outgoingPid) {
      // Persist QC inbox for outgoing narrator (even if QQ is empty)
      if (bb.quickItems && bb.quickItems.length > 0) {
        try { localStorage.setItem(_LS_QC_PREFIX + outgoingPid, JSON.stringify({ v: DRAFT_SCHEMA_VERSION, d: bb.quickItems })); } catch (e) {}
      }
      if (bb.questionnaire && Object.keys(bb.questionnaire).length > 0) {
        _persistDrafts(outgoingPid);
      }
    }

    bb.personId      = newId || null;
    bb.quickItems    = [];
    bb.questionnaire = {};
    bb.graph         = { persons: {}, relationships: {} };  // Phase Q.1
    bb.sourceCards   = [];
    bb.candidates    = {
      people: [], relationships: [], events: [], memories: [], places: [], documents: []
    };

    if (!bb.familyTreeDraftsByPerson)  bb.familyTreeDraftsByPerson  = {};
    if (!bb.lifeThreadsDraftsByPerson) bb.lifeThreadsDraftsByPerson = {};

    // v8-fix: restore incoming narrator's questionnaire from localStorage (WD-1 fix)
    _loadDrafts(newId);

    // Phase L.1: rehydrate candidates from restored questionnaire
    _rehydrateCandidates(newId);
  }

  /* ── v8 Explicit narrator-switch entry point ───────────────
     Called from app.js after loadPerson() completes.
     Resets narrator-scoped state, then re-hydrates from the
     newly loaded profile.
     NOTE: _hydrateQuestionnaireFromProfile lives in the questionnaire
     module. The core module calls it via the registered hook.
  ─────────────────────────────────────────────────────────── */

  // Hook: questionnaire module registers its hydration function here
  var _postSwitchHooks = [];

  function _registerPostSwitchHook(fn) {
    _postSwitchHooks.push(fn);
  }

  function _onNarratorSwitch(newId) {
    var bb = _bb(); if (!bb) return;
    _resetNarratorScopedState(newId);
    // Run registered hooks (e.g. questionnaire hydration)
    _postSwitchHooks.forEach(function (fn) { fn(bb); });
    // Phase 2.5.3: Narrator-switch drift validation
    _qqDebugSnapshot("narrator_switch", newId, bb);
  }

  /* ── BUG-226: Identity intake → Bio Builder questionnaire sync ──
     Called from app.js identity onboarding handlers (askName / askDob /
     askBirthplace) whenever the canonical identity captures land in
     state.profile.basics.  Mirrors the captures into
     bb.questionnaire.personal under the canonical MINIMAL_SECTIONS
     schema (camelCase: fullName / preferredName / dateOfBirth /
     placeOfBirth) so that Bio Builder reflects what Lori already knows
     instead of asking again.  Persists via the canonical _persistDrafts
     path (backend PUT + transient localStorage).
     Idempotent: only fills empty fields, never overwrites operator-edited values.
  ─────────────────────────────────────────────────────────── */
  function _syncIdentityToBB(profile) {
    var bb = _bb(); if (!bb) return false;
    var basics = (profile && profile.basics) || profile || {};
    if (!basics || typeof basics !== "object") return false;

    var pid = bb.personId || _currentPersonId();
    if (!pid) {
      console.warn("[bb-sync] _syncIdentityToBB: no active narrator pid — skipping");
      return false;
    }
    // Scope guard — never write under the wrong narrator
    if (bb.personId && bb.personId !== pid) {
      console.warn("[bb-sync] _syncIdentityToBB BLOCKED: bb.personId=" +
        (bb.personId || "").slice(0, 8) + " !== pid=" + (pid || "").slice(0, 8));
      return false;
    }

    if (!bb.questionnaire) bb.questionnaire = {};
    if (!bb.questionnaire.personal || typeof bb.questionnaire.personal !== "object") {
      bb.questionnaire.personal = {};
    }
    var personal = bb.questionnaire.personal;

    // Accept either camelCase or legacy snake/lowercase shapes from state.profile.basics
    var fullName = basics.fullname || basics.fullName ||
                   basics.preferred || basics.preferredName || null;
    var dob      = basics.dob || basics.dateOfBirth || null;
    var pob      = basics.pob || basics.placeOfBirth || null;

    var changed = false;
    if (fullName && !personal.fullName)        { personal.fullName        = fullName; changed = true; }
    if (fullName && !personal.preferredName)   { personal.preferredName   = fullName; changed = true; }
    if (dob      && !personal.dateOfBirth)     { personal.dateOfBirth     = dob;      changed = true; }
    if (pob      && !personal.placeOfBirth)    { personal.placeOfBirth    = pob;      changed = true; }

    if (!changed) return false;

    console.log("[bb-sync] identity → questionnaire.personal " +
      JSON.stringify({ fullName: !!fullName, dob: !!dob, pob: !!pob }) +
      " for pid=" + pid.slice(0, 8));

    // Persist via canonical path (backend PUT + transient localStorage).
    // _persistDrafts gates on bb.personId === pid so this is scope-safe.
    try { _persistDrafts(pid); } catch (e) {
      console.warn("[bb-sync] _persistDrafts threw:", e);
    }

    return true;
  }

  /* ── Person-change logic (called from render path) ──────── */
  function _personChanged(newId) {
    var bb = _bb(); if (!bb) return;
    if (bb.personId !== newId) {
      // BUG-208: bump generation FIRST so any in-flight async restores
      // stamped under the OLD pid see a stale generation when they resolve.
      _narratorSwitchGen += 1;
      // v8-fix: persist outgoing narrator's questionnaire before clearing
      // Phase M: also persists Quick Capture inbox
      var outgoingPid = bb.personId;
      if (outgoingPid) {
        if (bb.quickItems && bb.quickItems.length > 0) {
          try { localStorage.setItem(_LS_QC_PREFIX + outgoingPid, JSON.stringify({ v: DRAFT_SCHEMA_VERSION, d: bb.quickItems })); } catch (e) {}
        }
        if (bb.questionnaire && Object.keys(bb.questionnaire).length > 0) {
          _persistDrafts(outgoingPid);
        }
      }
      bb.personId      = newId;
      bb.quickItems    = [];
      bb.questionnaire = {};
      bb.graph         = { persons: {}, relationships: {} };  // Phase Q.1
      bb.sourceCards   = [];
      bb.candidates    = {
        people: [], relationships: [], events: [], memories: [], places: [], documents: []
      };
    }
    // v3: ensure per-person draft containers exist (lazy — never reset on switch)
    if (!bb.familyTreeDraftsByPerson)  bb.familyTreeDraftsByPerson  = {};
    if (!bb.lifeThreadsDraftsByPerson) bb.lifeThreadsDraftsByPerson = {};
    // v4: restore persisted drafts for this narrator
    _loadDrafts(newId);
    // v6-fix: hydrate questionnaire from active profile if empty
    _postSwitchHooks.forEach(function (fn) { fn(bb); });
    // Phase L.1: rehydrate candidates from restored questionnaire
    _rehydrateCandidates(newId);
    // Phase 2.5: debug snapshot after person change
    _qqDebugSnapshot("person_changed", newId, bb);
  }

  /* ───────────────────────────────────────────────────────────
     UTILITIES
  ─────────────────────────────────────────────────────────── */

  function _el(id) { return document.getElementById(id); }

  function _uid() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  }

  function _currentPersonId() {
    try { return (typeof state !== "undefined" && state.person_id) ? state.person_id : null; }
    catch (_) { return null; }
  }

  function _currentPersonName() {
    try {
      if (typeof state !== "undefined" && state.profile && state.profile.basics) {
        return state.profile.basics.preferredName || state.profile.basics.fullName || null;
      }
    } catch (_) {}
    return null;
  }

  function _esc(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function _formatBytes(bytes) {
    if (!bytes) return "";
    if (bytes < 1024)       return bytes + " B";
    if (bytes < 1048576)    return Math.round(bytes / 1024) + " KB";
    return (bytes / 1048576).toFixed(1) + " MB";
  }

  /* ── v7: Inline confirmation dialog (replaces native confirm()) ──
     Native popovers (popover="auto") render in the browser's top layer
     ABOVE position:fixed elements.  So if the caller is inside an open
     popover (e.g., Bug Panel), a fixed-position overlay appended to
     document.body will be hidden BEHIND the popover.
     Fix: detect the currently-open popover and append the overlay to
     it so it renders in the same top layer.  Falls back to bioBuilder
     popover or document.body. */
  function _showInlineConfirm(message, onConfirm) {
    var existing = document.getElementById("bbInlineConfirm");
    if (existing) existing.remove();
    var overlay = document.createElement("div");
    overlay.id = "bbInlineConfirm";
    overlay.style.cssText = "position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.45);z-index:2147483647;display:flex;align-items:center;justify-content:center;";
    var box = document.createElement("div");
    box.style.cssText = "background:#fff;border-radius:8px;padding:20px 24px;max-width:420px;box-shadow:0 8px 32px rgba(0,0,0,0.35);text-align:center;font-family:inherit;color:#1e293b;";
    box.innerHTML = '<div style="margin:0 0 16px;font-size:14px;color:#1e293b;line-height:1.5;">' + message + '</div>'
      + '<div style="display:flex;gap:8px;justify-content:center;">'
      + '<button id="bbConfirmCancel" style="padding:8px 18px;border:1px solid #cbd5e1;border-radius:4px;background:#f1f5f9;color:#1e293b;cursor:pointer;font-size:13px;">Cancel</button>'
      + '<button id="bbConfirmOk" style="padding:8px 18px;border:none;border-radius:4px;background:#ef4444;color:#fff;cursor:pointer;font-size:13px;font-weight:600;">Delete</button>'
      + '</div>';
    overlay.appendChild(box);
    // Find the currently-open popover (top layer).  Native popover spec:
    // :popover-open matches any open popover.  Append the overlay to it
    // so the overlay renders in the same top-layer as the popover above
    // all page content.
    var openPopover = null;
    try { openPopover = document.querySelector('[popover]:popover-open'); } catch (_) {}
    var bioPopover = document.getElementById("bioBuilderPopover");
    var target = openPopover || bioPopover || document.body;
    target.appendChild(overlay);
    console.log("[bb-confirm-dialog] shown (target=" + (target.id || target.tagName) + ")");
    var doneCancel = function () { overlay.remove(); console.log("[bb-confirm-dialog] cancelled"); };
    var doneOk     = function () { overlay.remove(); console.log("[bb-confirm-dialog] confirmed → running onConfirm"); onConfirm(); };
    document.getElementById("bbConfirmCancel").onclick = doneCancel;
    document.getElementById("bbConfirmOk").onclick     = doneOk;
    overlay.onclick = function (e) { if (e.target === overlay) doneCancel(); };
  }

  function _emptyStateHtml(title, message, actions) {
    var actionsHtml = (actions || []).map(function (a) {
      return '<button class="bb-ghost-btn" onclick="' + a.action + '">' + _esc(a.label) + '</button>';
    }).join("");
    return '<div class="bb-empty-state">'
      + '<div class="bb-empty-title">' + _esc(title) + '</div>'
      + '<div class="bb-empty-message">' + _esc(message) + '</div>'
      + (actionsHtml ? '<div class="bb-empty-actions">' + actionsHtml + '</div>' : '')
      + '</div>';
  }

  /* Check if an object has any non-empty string values */
  function _hasAnyValue(obj) {
    if (!obj || typeof obj !== "object") return false;
    if (Array.isArray(obj)) return obj.length > 0;
    return Object.keys(obj).some(function (k) {
      var v = obj[k];
      return v && String(v).trim() !== "";
    });
  }

  /* ───────────────────────────────────────────────────────────
     ACTIVE VIEW TRACKING
  ─────────────────────────────────────────────────────────── */

  var _viewState = {
    activeSection:      null,
    activeTab:          "capture",
    activeSourceCardId: null,
    ftViewMode:         "cards",
    ltViewMode:         "cards"
  };

  /* ───────────────────────────────────────────────────────────
     WO-BB-RESET-UTILITY-01 — Dev-only safety valve.
     Clears questionnaire / candidates / drafts / Quick Capture
     ONLY for the currently-active narrator.  Never touches another
     narrator's data.  Confirms via inline dialog before firing.
     Triggered from the Bug Panel button.
  ─────────────────────────────────────────────────────────── */
  function lvBbResetCurrentNarrator() {
    console.log("[bb-reset] button clicked — entering lvBbResetCurrentNarrator");
    var bb = _bb(); if (!bb) {
      console.warn("[bb-reset] ABORT — state.bioBuilder not initialized — nothing to reset");
      alert("Bio Builder state not initialized yet. Open the Bio Builder once or pick a narrator first.");
      return false;
    }
    var pid = bb.personId || _currentPersonId();
    if (!pid) {
      console.warn("[bb-reset] ABORT — no active narrator selected");
      alert("No active narrator selected. Pick a narrator first, then try again.");
      return false;
    }
    var name = _currentPersonName() || pid.slice(0, 8);
    // Pre-snapshot — counts of what's about to be cleared so the user can
    // see the reset DID something, even if the confirm dialog is hidden.
    var qq = bb.questionnaire || {};
    var qqSectionCount = Object.keys(qq).length;
    var qqFieldCount = 0;
    Object.keys(qq).forEach(function (sk) {
      var v = qq[sk];
      if (Array.isArray(v)) qqFieldCount += v.length;
      else if (v && typeof v === "object") qqFieldCount += Object.keys(v).filter(function (fk) { return v[fk] && String(v[fk]).trim(); }).length;
    });
    var candidateCount = 0;
    if (bb.candidates) {
      Object.keys(bb.candidates).forEach(function (k) {
        if (Array.isArray(bb.candidates[k])) candidateCount += bb.candidates[k].length;
      });
    }
    var qcCount = (bb.quickItems || []).length;
    console.log("[bb-reset] PRE-RESET snapshot for " + name + " (" + pid.slice(0,8) + "): " +
      qqSectionCount + " questionnaire section(s), " + qqFieldCount + " filled field(s), " +
      candidateCount + " candidate(s), " + qcCount + " quick-capture item(s)");
    _showInlineConfirm(
      "Reset Bio Builder data for <strong>" + _esc(name) + "</strong>?<br><br>" +
      "<div style='text-align:left;font-size:12px;color:#475569;'>" +
      "Will clear:<br>" +
      "&nbsp;&nbsp;• " + qqSectionCount + " questionnaire section(s) (" + qqFieldCount + " filled field" + (qqFieldCount === 1 ? "" : "s") + ")<br>" +
      "&nbsp;&nbsp;• " + candidateCount + " candidate" + (candidateCount === 1 ? "" : "s") + " across people / events / memories<br>" +
      "&nbsp;&nbsp;• " + qcCount + " Quick Capture item" + (qcCount === 1 ? "" : "s") + "<br>" +
      "&nbsp;&nbsp;• localStorage drafts for this narrator<br>" +
      "&nbsp;&nbsp;• Backend questionnaire blob (PUT empty)" +
      "</div>" +
      "<br><small>Other narrators are NOT affected. Cannot be undone.</small>",
      function () {
        // Bump generation to invalidate any in-flight async restores.
        _narratorSwitchGen += 1;
        // Clear in-memory state for active narrator only
        bb.quickItems    = [];
        bb.questionnaire = {};
        bb.graph         = { persons: {}, relationships: {} };
        bb.sourceCards   = [];
        bb.candidates    = {
          people: [], relationships: [], events: [], memories: [], places: [], documents: []
        };
        // Clear localStorage drafts for active narrator only
        try {
          localStorage.removeItem(_LS_FT_PREFIX + pid);
          localStorage.removeItem(_LS_LT_PREFIX + pid);
          localStorage.removeItem(_LS_QQ_PREFIX + pid);
          localStorage.removeItem(_LS_QC_PREFIX + pid);
          localStorage.removeItem(_LS_QC_PREFIX.replace("_qc_", "_qc_") + pid);
        } catch (e) {
          console.warn("[bb-reset] localStorage clear partial:", e);
        }
        // Best-effort backend wipe — PUT an empty questionnaire under this pid.
        // Backend echoes person_id; if mismatch, we don't write.
        if (typeof API !== "undefined" && API.BB_QQ_PUT) {
          try {
            fetch(API.BB_QQ_PUT, {
              method: "PUT",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                person_id: pid,
                questionnaire: {},
                source: "bb_reset_utility",
                version: DRAFT_SCHEMA_VERSION
              })
            }).catch(function (e) {
              console.warn("[bb-reset] backend wipe failed:", e);
            });
          } catch (e) {
            console.warn("[bb-reset] backend wipe threw:", e);
          }
        }
        console.log("[bb-reset] CLEARED for " + pid.slice(0, 8) + " (" + name + ") — was " +
          qqSectionCount + " section(s), " + qqFieldCount + " field(s), " +
          candidateCount + " candidate(s), " + qcCount + " QC item(s).");
        // Post-reset snapshot — confirms the wipe in console
        try {
          var bbAfter = _bb() || {};
          console.log("[bb-reset] POST-RESET snapshot:", {
            personId: bbAfter.personId,
            questionnaireSections: Object.keys(bbAfter.questionnaire || {}).length,
            candidates: bbAfter.candidates ? Object.values(bbAfter.candidates).reduce(function (s, a) { return s + (Array.isArray(a) ? a.length : 0); }, 0) : 0,
            quickItems: (bbAfter.quickItems || []).length,
          });
        } catch (_) {}
        // Update status line if Bug Panel is open
        var status = document.getElementById("lv10dBpBbResetStatus");
        if (status) {
          status.textContent = "✓ reset BB for " + name + " (" + pid.slice(0, 8) +
            ") — cleared " + qqFieldCount + " field(s), " + candidateCount + " candidate(s), at " +
            new Date().toLocaleTimeString();
        }
        // Visible top-of-viewport toast — operator sees success even when
        // the Bug Panel popover obscures the status line.  Append to the
        // currently-open popover so it renders in the same top layer.
        try {
          var openPopoverT = null;
          try { openPopoverT = document.querySelector('[popover]:popover-open'); } catch (_) {}
          var toast = document.createElement("div");
          toast.id = "bbResetToast";
          toast.style.cssText = "position:fixed;top:24px;left:50%;transform:translateX(-50%);" +
            "z-index:2147483647;background:#10b981;color:#fff;padding:14px 22px;border-radius:8px;" +
            "box-shadow:0 6px 24px rgba(0,0,0,0.35);font-size:14px;font-weight:600;font-family:inherit;" +
            "min-width:300px;text-align:center;line-height:1.4;";
          toast.innerHTML = "✓ Bio Builder reset for " + _esc(name) + "<br>" +
            "<span style='font-weight:400;font-size:12px;opacity:0.9;'>" +
            "cleared " + qqFieldCount + " field(s), " + candidateCount + " candidate(s), " +
            qcCount + " quick item(s)</span>";
          (openPopoverT || document.body).appendChild(toast);
          setTimeout(function () { try { toast.remove(); } catch (_) {} }, 8000);
        } catch (_) {}
      }
    );
    return true;
  }
  window.lvBbResetCurrentNarrator = lvBbResetCurrentNarrator;

  /* ───────────────────────────────────────────────────────────
     WO-DEEP-RESET — Dev/operator-only nuke for dirty narrator data.
     Extends the lvBbResetCurrentNarrator scope to ALSO clear the
     interview projection layer + state.profile family fields.

     Use case: Chris's runtime71.projection_family had pollution like
     "Stanley ND" as Father, "and dad" as Mother, dupe Janice rows —
     pre-existing data accumulated from old extraction errors.
     Reset BB clears the BB questionnaire blob but does NOT reach
     the projection layer; this reset does both.

     SCOPE — clears:
       1. Bio Builder substate (questionnaire / candidates / drafts /
          quick capture / family-graph) — same as lvBbResetCurrentNarrator
       2. localStorage drafts (FT / LT / QQ / QC) for active narrator
       3. interview projection (state.interviewProjection.fields +
          lorevox_proj_draft_<pid> localStorage key) via existing
          LorevoxProjectionSync.clearProjection(pid)
       4. state.profile.kinship + state.profile.pets (derived/polluted
          family rosters that might feed runtime71)
       5. Backend questionnaire blob (PUT empty)
       6. Backend projection (PUT empty fields)

     DOES NOT touch:
       - state.profile.basics (name/DOB/place — load-bearing for identity)
       - memory archive (transcripts + audio + meta.json + zips)
       - state.session (style, recordVoice, narrator-room state)
       - any OTHER narrator
       - WO-13 promoted truth pipeline (only the projection-derived view
         that feeds runtime71)
  ─────────────────────────────────────────────────────────── */
  function lvBbDeepResetCurrentNarrator() {
    console.log("[bb-deep-reset] button clicked — entering lvBbDeepResetCurrentNarrator");
    var bb = _bb(); if (!bb) {
      console.warn("[bb-deep-reset] ABORT — state.bioBuilder not initialized");
      alert("Bio Builder state not initialized. Pick a narrator first.");
      return false;
    }
    var pid = bb.personId || _currentPersonId();
    if (!pid) {
      console.warn("[bb-deep-reset] ABORT — no active narrator");
      alert("No active narrator selected. Pick a narrator first, then try again.");
      return false;
    }
    var name = _currentPersonName() || pid.slice(0, 8);

    // Pre-snapshot
    var qq = bb.questionnaire || {};
    var qqFieldCount = 0;
    Object.keys(qq).forEach(function (sk) {
      var v = qq[sk];
      if (Array.isArray(v)) qqFieldCount += v.length;
      else if (v && typeof v === "object") qqFieldCount += Object.keys(v).filter(function (fk) { return v[fk] && String(v[fk]).trim(); }).length;
    });
    var candidateCount = 0;
    if (bb.candidates) {
      Object.keys(bb.candidates).forEach(function (k) {
        if (Array.isArray(bb.candidates[k])) candidateCount += bb.candidates[k].length;
      });
    }
    // Projection field count
    var projFieldCount = 0;
    try {
      var iProj = (typeof state !== "undefined") ? state.interviewProjection : null;
      if (iProj && iProj.fields) projFieldCount = Object.keys(iProj.fields).length;
    } catch (_) {}
    // Kinship + pets count
    var kinshipCount = 0, petsCount = 0;
    try {
      var prof = (typeof state !== "undefined") ? state.profile : null;
      if (prof) {
        if (Array.isArray(prof.kinship)) kinshipCount = prof.kinship.length;
        if (Array.isArray(prof.pets))    petsCount    = prof.pets.length;
      }
    } catch (_) {}
    console.log("[bb-deep-reset] PRE-RESET snapshot for " + name + " (" + pid.slice(0, 8) + "): " +
      qqFieldCount + " BB field(s), " + candidateCount + " candidate(s), " +
      projFieldCount + " projection field(s), " + kinshipCount + " kinship row(s), " +
      petsCount + " pet(s)");

    _showInlineConfirm(
      "<strong style='color:#dc2626;'>Deep Reset</strong> for <strong>" + _esc(name) + "</strong>?<br><br>" +
      "<div style='text-align:left;font-size:12px;color:#475569;'>" +
      "Will clear:<br>" +
      "&nbsp;&nbsp;• " + qqFieldCount + " questionnaire field" + (qqFieldCount === 1 ? "" : "s") + "<br>" +
      "&nbsp;&nbsp;• " + candidateCount + " candidate" + (candidateCount === 1 ? "" : "s") + "<br>" +
      "&nbsp;&nbsp;• " + projFieldCount + " projection field" + (projFieldCount === 1 ? "" : "s") + " (the dirty parents/family roster)<br>" +
      "&nbsp;&nbsp;• " + kinshipCount + " kinship row" + (kinshipCount === 1 ? "" : "s") + "<br>" +
      "&nbsp;&nbsp;• " + petsCount + " pet" + (petsCount === 1 ? "" : "s") + "<br>" +
      "&nbsp;&nbsp;• localStorage QQ + projection draft<br>" +
      "&nbsp;&nbsp;• Backend questionnaire + projection blobs (PUT empty)" +
      "</div>" +
      "<br><strong style='color:#dc2626;'>Will NOT touch:</strong>" +
      "<div style='text-align:left;font-size:12px;color:#475569;'>" +
      "&nbsp;&nbsp;• Identity (name/DOB/place)<br>" +
      "&nbsp;&nbsp;• Memory archive (transcripts + audio + zips)<br>" +
      "&nbsp;&nbsp;• Session style + recordVoice toggle<br>" +
      "&nbsp;&nbsp;• Other narrators" +
      "</div>" +
      "<br><small>Other narrators are NOT affected. Cannot be undone.</small>",
      function () {
        // 1. Bump narrator-switch generation to invalidate any in-flight async
        _narratorSwitchGen += 1;

        // 2. Clear BB substate (in-memory)
        bb.quickItems    = [];
        bb.questionnaire = {};
        bb.graph         = { persons: {}, relationships: {} };
        bb.sourceCards   = [];
        bb.candidates    = {
          people: [], relationships: [], events: [], memories: [], places: [], documents: []
        };

        // 3. Clear projection layer via projection-sync's existing helper
        var projCleared = false;
        try {
          if (typeof LorevoxProjectionSync !== "undefined" && LorevoxProjectionSync.clearProjection) {
            LorevoxProjectionSync.clearProjection(pid);
            projCleared = true;
            console.log("[bb-deep-reset] LorevoxProjectionSync.clearProjection() called");
          } else {
            // Fallback: clear directly
            try { localStorage.removeItem("lorevox_proj_draft_" + pid); } catch (_) {}
            if (typeof state !== "undefined" && state.interviewProjection &&
                state.interviewProjection.personId === pid) {
              state.interviewProjection.fields = {};
              state.interviewProjection.pendingSuggestions = [];
              state.interviewProjection.syncLog = [];
            }
            projCleared = true;
            console.log("[bb-deep-reset] projection cleared via fallback path");
          }
        } catch (e) {
          console.warn("[bb-deep-reset] projection clear threw:", e && e.message || e);
        }

        // 4. Clear state.profile.kinship + pets (preserve basics — load-bearing for identity)
        var profileCleared = { kinship: 0, pets: 0 };
        try {
          if (typeof state !== "undefined" && state.profile) {
            if (Array.isArray(state.profile.kinship)) {
              profileCleared.kinship = state.profile.kinship.length;
              state.profile.kinship = [];
            }
            if (Array.isArray(state.profile.pets)) {
              profileCleared.pets = state.profile.pets.length;
              state.profile.pets = [];
            }
          }
        } catch (e) {
          console.warn("[bb-deep-reset] state.profile clear threw:", e);
        }

        // 5. Clear localStorage drafts (FT, LT, QQ, QC) for active narrator
        try {
          localStorage.removeItem(_LS_FT_PREFIX + pid);
          localStorage.removeItem(_LS_LT_PREFIX + pid);
          localStorage.removeItem(_LS_QQ_PREFIX + pid);
          localStorage.removeItem(_LS_QC_PREFIX + pid);
        } catch (e) {
          console.warn("[bb-deep-reset] localStorage clear partial:", e);
        }

        // 6. Backend QQ wipe (best-effort, fire-and-forget)
        if (typeof API !== "undefined" && API.BB_QQ_PUT) {
          try {
            fetch(API.BB_QQ_PUT, {
              method: "PUT",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                person_id: pid,
                questionnaire: {},
                source: "bb_deep_reset",
                version: DRAFT_SCHEMA_VERSION
              })
            }).then(function (r) {
              console.log("[bb-deep-reset] backend QQ wipe → " + r.status);
            }).catch(function (e) {
              console.warn("[bb-deep-reset] backend QQ wipe failed:", e);
            });
          } catch (e) { console.warn("[bb-deep-reset] backend QQ wipe threw:", e); }
        }

        // 7. Backend projection wipe (best-effort, fire-and-forget).
        //
        // WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 (2026-08-17). This is
        // the RESET operation, and it is the only caller entitled to
        // replace the whole envelope. It therefore has to earn it:
        //   * read the current version first, so the replacement runs
        //     under optimistic concurrency rather than blind;
        //   * say replace: true and allow_empty: true explicitly.
        // A stale base returns 409 and wipes nothing, which is correct --
        // if the row moved between the read and the write, the operator
        // is resetting something they have not seen.
        if (typeof API !== "undefined" && API.IV_PROJ_PUT && API.IV_PROJ_GET) {
          try {
            fetch(API.IV_PROJ_GET(pid))
              .then(function (r) { return r.ok ? r.json() : null; })
              .then(function (cur) {
                if (!cur) throw new Error("could not read current projection version");
                return fetch(API.IV_PROJ_PUT, {
                  method: "PUT",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    person_id: pid,
                    projection: { fields: {}, pendingSuggestions: [], syncLog: [] },
                    source: "bb_deep_reset",
                    version: 1,
                    replace: true,
                    allow_empty: true,
                    base_version: cur.version
                  })
                });
              })
              .then(function (r) {
                console.log("[bb-deep-reset] backend projection wipe → " + r.status);
                if (r.status === 409) {
                  console.warn("[bb-deep-reset] projection changed since it was read — " +
                               "nothing was wiped. Re-open and reset again to confirm.");
                }
              })
              .catch(function (e) {
                console.warn("[bb-deep-reset] backend projection wipe failed:", e);
              });
          } catch (e) { console.warn("[bb-deep-reset] backend projection wipe threw:", e); }
        }

        console.log("[bb-deep-reset] CLEARED for " + pid.slice(0, 8) + " (" + name + ") — was " +
          qqFieldCount + " BB fields, " + candidateCount + " candidates, " +
          projFieldCount + " projection fields, " + kinshipCount + " kinship rows, " +
          petsCount + " pets. projCleared=" + projCleared +
          " profileCleared=" + JSON.stringify(profileCleared));

        // Status line if Bug Panel is open
        var status = document.getElementById("lv10dBpDeepResetStatus");
        if (status) {
          status.textContent = "✓ deep reset for " + name + " (" + pid.slice(0, 8) +
            ") — cleared " + qqFieldCount + " BB + " + projFieldCount + " projection + " +
            kinshipCount + " kinship at " + new Date().toLocaleTimeString();
        }

        // Visible top-of-viewport toast
        try {
          var openPopoverT = null;
          try { openPopoverT = document.querySelector('[popover]:popover-open'); } catch (_) {}
          var toast = document.createElement("div");
          toast.id = "bbDeepResetToast";
          toast.style.cssText = "position:fixed;top:24px;left:50%;transform:translateX(-50%);" +
            "z-index:2147483647;background:#dc2626;color:#fff;padding:14px 22px;border-radius:8px;" +
            "box-shadow:0 6px 24px rgba(0,0,0,0.35);font-size:14px;font-weight:600;font-family:inherit;" +
            "min-width:340px;text-align:center;line-height:1.4;";
          toast.innerHTML = "✓ Deep Reset for " + _esc(name) + "<br>" +
            "<span style='font-weight:400;font-size:12px;opacity:0.95;'>" +
            "cleared " + qqFieldCount + " BB + " + projFieldCount + " projection + " +
            kinshipCount + " kinship row(s).<br>" +
            "Switch away/back or hard-refresh to verify runtime71.</span>";
          (openPopoverT || document.body).appendChild(toast);
          setTimeout(function () { try { toast.remove(); } catch (_) {} }, 10000);
        } catch (_) {}
      }
    );
    return true;
  }
  window.lvBbDeepResetCurrentNarrator = lvBbDeepResetCurrentNarrator;

  // BUG-226: expose identity → BB sync so app.js identity onboarding can call it
  // without depending on the LorevoxBioBuilderCore module export shape.
  window.lvBbSyncIdentity = function (profile) {
    try { return _syncIdentityToBB(profile); }
    catch (e) { console.warn("[bb-sync] lvBbSyncIdentity threw:", e); return false; }
  };

  /* ───────────────────────────────────────────────────────────
     BUG-228: RESET IDENTITY for current narrator

     Operational tool — wipes the polluted identity fields for the
     active narrator and re-opens identity onboarding.  Use when a
     narrator's bb.questionnaire.personal contains garbage from
     prior test sessions (refusal replies saved as fullName,
     wrong DOB, wrong birthplace, etc.) and the simple BUG-220A
     scope fix can't help because the data IS for this narrator.

     Scope (narrow on purpose):
       • bb.questionnaire.personal — wiped to {}
       • state.profile.basics.fullname / preferred / dob / pob — wiped
       • state.session.identityPhase — reset to "askName"
       • state.session.identityCapture — reset to fresh shape
       • backend BB QQ personal section — PUT empty
       • backend person row — PATCHed to clear date_of_birth + place_of_birth
       • identity onboarding — re-fired via startIdentityOnboarding()

     Out of scope:
       • Other narrators' data (not touched)
       • Memory archive (preserved — sessions stay intact)
       • Family tree, life threads, photos (preserved)
       • Other BB sections (parents, siblings) (preserved)
       • person_id (preserved — same narrator, just identity reset)
   ─────────────────────────────────────────────────────────── */
  function _setResetIdentityStatus(html) {
    try {
      const el = document.getElementById("lv10dBpResetIdentityStatus");
      if (el) el.innerHTML = html;
    } catch (_) {}
  }

  async function lvBbResetIdentityForCurrentNarrator() {
    const pid = (typeof state !== "undefined" && state.person_id) || null;
    if (!pid) {
      console.warn("[bb-reset-identity] ABORT — no active narrator");
      _setResetIdentityStatus('<span style="color:#f87171;">✗ FAIL — no narrator selected</span>');
      try { alert("No active narrator selected — pick a narrator first."); } catch (_) {}
      return false;
    }
    const bb = _bb();
    if (!bb || bb.personId !== pid) {
      console.warn("[bb-reset-identity] ABORT — bb.personId mismatch (bb=" +
        ((bb && bb.personId) || "null").slice(0, 8) + " state=" + pid.slice(0, 8) + ")");
      _setResetIdentityStatus('<span style="color:#f87171;">✗ FAIL — BB scope reconciling, try again</span>');
      try { alert("Bio Builder scope is reconciling — try again in a moment."); } catch (_) {}
      return false;
    }

    const currentName = (state.profile && state.profile.basics &&
      (state.profile.basics.preferred || state.profile.basics.fullname)) || "this narrator";

    // Confirm with the operator (popover-aware so it shows above bug panel).
    const ok = await _confirmIdentityReset(currentName, pid);
    if (!ok) {
      console.log("[bb-reset-identity] cancelled by operator");
      return false;
    }

    console.log("[bb-reset-identity] starting reset for pid=" + pid.slice(0, 8) +
      " name=" + currentName);

    // 1. Wipe in-memory bb.questionnaire.personal (preserve other sections).
    try {
      if (bb.questionnaire) bb.questionnaire.personal = {};
    } catch (e) { console.warn("[bb-reset-identity] bb wipe threw:", e); }

    // 2. Wipe state.profile.basics identity fields.
    try {
      if (state.profile && state.profile.basics) {
        delete state.profile.basics.fullname;
        delete state.profile.basics.fullName;
        delete state.profile.basics.preferred;
        delete state.profile.basics.preferredName;
        delete state.profile.basics.dob;
        delete state.profile.basics.dateOfBirth;
        delete state.profile.basics.pob;
        delete state.profile.basics.placeOfBirth;
      }
    } catch (e) { console.warn("[bb-reset-identity] basics wipe threw:", e); }

    // 3. Reset session identity machine.
    try {
      if (!state.session) state.session = {};
      state.session.identityPhase   = "askName";
      state.session.identityCapture = { name: null, dob: null, birthplace: null };
      state.session.speakerName     = null;
    } catch (e) { console.warn("[bb-reset-identity] session reset threw:", e); }

    // 3.5. WO-PARENT-SESSION-HARDENING-01 Phase 1.2 — clear projection layer
    //      for protected-identity fields. The current flow only wiped BB.personal
    //      but the projection layer can still hold polluted values written by
    //      chat extraction OR by the QF auto-save bypass before Phase 1.1's
    //      shape gate landed. Without this, peek/memoir/export would still
    //      surface the polluted strings until projection cache turned over.
    //      Janice's 2026-05-01 evidence (placeOfBirth + birthOrder pollution)
    //      survived a Reset Identity for exactly this reason.
    try {
      var _identityPaths = [
        "personal.fullName",
        "personal.preferredName",
        "personal.dateOfBirth",
        "personal.placeOfBirth",
        "personal.birthOrder",
        "personal.timeOfBirth",
      ];
      var _projCleared = 0;
      if (typeof state !== "undefined" && state.interviewProjection &&
          state.interviewProjection.fields) {
        _identityPaths.forEach(function (p) {
          if (state.interviewProjection.fields[p]) {
            delete state.interviewProjection.fields[p];
            _projCleared += 1;
          }
        });
      }
      // Drop pendingSuggestions for these paths so they don't re-promote
      // a corrupt value during the next sync turn.
      var _suggDropped = 0;
      if (typeof state !== "undefined" && state.interviewProjection &&
          Array.isArray(state.interviewProjection.pendingSuggestions)) {
        var _before = state.interviewProjection.pendingSuggestions.length;
        state.interviewProjection.pendingSuggestions =
          state.interviewProjection.pendingSuggestions.filter(function (s) {
            return !s || _identityPaths.indexOf(s.fieldPath) === -1;
          });
        _suggDropped = _before - state.interviewProjection.pendingSuggestions.length;
      }
      console.log("[bb-reset-identity] projection cleared: " + _projCleared +
        " identity field(s), " + _suggDropped + " pending suggestion(s) dropped");
    } catch (e) { console.warn("[bb-reset-identity] projection clear threw:", e); }

    // 3.6. WO-PARENT-SESSION-HARDENING-01 Phase 1.2 — clear localStorage
    //      projection draft for this narrator. The lorevox_proj_draft_<pid>
    //      key persists projection state across reload; without clearing it,
    //      a polluted value can rehydrate after reset. Clearing the whole
    //      draft is wider than identity-only, but localStorage shape doesn't
    //      support per-field surgical removal — acceptable: projection
    //      rebuilds from clean BB + backend.
    try {
      var _lsKey = "lorevox_proj_draft_" + pid;
      var _hadKey = (typeof localStorage !== "undefined" &&
        localStorage.getItem(_lsKey) !== null);
      if (_hadKey) {
        localStorage.removeItem(_lsKey);
        console.log("[bb-reset-identity] cleared localStorage " + _lsKey.slice(0, 30) + "…");
      }
    } catch (e) { console.warn("[bb-reset-identity] localStorage clear threw:", e); }

    // 4. Persist BB blob to backend (empty personal merges with whatever else is there).
    try { _persistDrafts(pid); } catch (e) { console.warn("[bb-reset-identity] persist threw:", e); }

    // 5. PATCH backend person row to clear DOB + place fields.
    try {
      if (typeof API !== "undefined" && API.PERSON) {
        const r = await fetch(API.PERSON(pid), {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ date_of_birth: null, place_of_birth: null }),
        });
        if (!r.ok) console.warn("[bb-reset-identity] PATCH person failed:", r.status);
        else console.log("[bb-reset-identity] PATCH person cleared DOB+POB");
      }
    } catch (e) { console.warn("[bb-reset-identity] PATCH person threw:", e); }

    // 6. Re-render BB if popover is open.
    try {
      if (window.LorevoxBioBuilder && typeof window.LorevoxBioBuilder.refresh === "function") {
        window.LorevoxBioBuilder.refresh();
      }
    } catch (_) {}

    // 7. Re-fire identity onboarding so Lori asks for the three anchors again.
    try {
      if (typeof window.startIdentityOnboarding === "function") {
        window.startIdentityOnboarding();
      } else if (typeof startIdentityOnboarding === "function") {
        startIdentityOnboarding();
      }
    } catch (e) { console.warn("[bb-reset-identity] startIdentityOnboarding threw:", e); }

    console.log("[bb-reset-identity] complete — Lori will re-ask name + DOB + birthplace");
    _setResetIdentityStatus(
      '<span style="color:#22c55e;">✓ PASS — identity cleared for ' +
      currentName.replace(/[<>&]/g, "") + ' (' + pid.slice(0, 8) + ')</span><br>' +
      '<span style="color:#94a3b8;">Identity cleared. Start Questionnaire First and re-enter name/DOB/birthplace.</span>');
    return true;
  }

  function _confirmIdentityReset(name, pid) {
    return new Promise(function (resolve) {
      const msg =
        "Reset identity for \"" + name + "\" (" + pid.slice(0, 8) + ")?\n\n" +
        "This will:\n" +
        "  • Wipe bb.questionnaire.personal (Full Name / Preferred / DOB / Birthplace / Time of Birth)\n" +
        "  • Clear state.profile.basics identity fields\n" +
        "  • Clear interview projection entries for the 6 identity paths\n" +
        "  • Drop any pending identity suggestions in the candidates queue\n" +
        "  • Clear lorevox_proj_draft_<pid> from localStorage\n" +
        "  • PATCH the backend person row to null DOB + birthplace\n" +
        "  • Re-fire identity onboarding (Lori will ask the three anchors again)\n\n" +
        "PRESERVED:\n" +
        "  • Memory archive (transcripts intact)\n" +
        "  • Other BB sections (parents, siblings, family tree)\n" +
        "  • Other narrators (untouched)\n" +
        "  • person_id (same narrator, just identity reset)\n\n" +
        "Continue?";
      let answer;
      try { answer = window.confirm(msg); } catch (_) { answer = false; }
      resolve(!!answer);
    });
  }

  window.lvBbResetIdentityForCurrentNarrator = lvBbResetIdentityForCurrentNarrator;

  /* ───────────────────────────────────────────────────────────
     BUG-221B: PURGE TEST NARRATORS (nuclear, dev-only)

     Walks the people list, identifies any narrator whose display_name
     does NOT match the 5 canonical Horne-family + trainer narrators,
     and removes them from BOTH localStorage AND backend (soft-delete).

     Purpose: clean up dev pollution accumulated across days of test
     sessions (Sarah/Walter/Test Harness/Corky variants/etc.) BEFORE
     real parent sessions start. The ad-hoc per-narrator cleanup
     (BUG-228 above) is too slow for "I have 14 stale test narrators
     in my list" cases.

     Preserved (whitelist, exact display_name match):
       - Kent James Horne
       - Janice Josephine Horne
       - Christopher Todd Horne
       - William Alan Shatner   (trainer)
       - Dolly Rebecca Parton   (trainer)

     For each non-canonical narrator the purge:
       - Wipes localStorage keys: lorevox_qq_draft_<pid>, lv_done_<pid>,
         lv_segs_<pid>, lorevox_offline_profile_<pid>,
         lorevox_proj_draft_<pid>, bb_qq_<pid> (legacy)
       - Soft-deletes the person row via DELETE /api/people/{id}?mode=soft

     NOT touched:
       - Photo + memory archive on disk (preserved for forensic restore)
       - The 5 canonical narrators (zero risk to real demo data)
       - Backend family_truth / projection tables (covered by soft-delete)

     The whitelist is hardcoded by display_name so renaming a real
     narrator would orphan it. That's a deliberate trade — the utility
     refuses to delete based on heuristics; it deletes only what isn't
     on the explicit whitelist.
  ─────────────────────────────────────────────────────────── */

  /* Phase 7 (WO-LOREVOX-CLEAN-DATA-WORLD-01) — _CANONICAL_NARRATOR_NAMES and
     _isCanonicalNarrator() are GONE, and the purge no longer has a whitelist.

     What they did: the purge defined "test narrator" as EVERY NARRATOR NOT ON
     A FIVE-NAME LIST (three Hornes and two trainers), then soft-deleted all of
     them. On the Horne laptop that read as a tidy-up. On any other Lorevox
     root it is a button that deletes every narrator in the installation,
     because nobody there is on the list — and a restored narrator whose
     display name differs by one character from the hard-coded string is not
     on the list either. The comment above used to call the hard-coding "a
     deliberate trade" on the grounds that the utility "refuses to delete
     based on heuristics"; inverting a name whitelist IS a heuristic, and it
     is the most dangerous kind, because everything unknown falls on the
     delete side.

     The authority is now people.testing_only — set explicitly at narrator
     creation, persisted, and not mutable through PersonUpdate. Only narrators
     whose persisted disposition says testing_only are eligible. Every other
     narrator is preserved BY DEFINITION, so there is no list to maintain and
     nothing to fall off. */

  // Eligibility for the bulk purge. Strict `=== true` on purpose: if the
  // server has not sent the field (an older build, a partial payload), the
  // answer is NO. Absence must never be read as permission to delete.
  function _isPurgeEligible(person) {
    return !!person && person.testing_only === true;
  }

  function _setPurgeStatus(html) {
    try {
      var el = document.getElementById("lv10dBpPurgeTestStatus");
      if (el) el.innerHTML = html;
    } catch (_) {}
  }

  function _wipeNarratorLocalStorage(pid) {
    if (!pid) return [];
    var prefixes = [
      "lorevox_qq_draft_",
      "lv_done_",
      "lv_segs_",
      "lorevox_offline_profile_",
      "lorevox_proj_draft_",
      "bb_qq_",                    // legacy pre-WO-INTAKE-IDENTITY-01
      "lv_active_person_v55_",     // edge case: stale active-pid pointers
    ];
    var wiped = [];
    for (var i = 0; i < prefixes.length; i += 1) {
      var key = prefixes[i] + pid;
      try {
        if (localStorage.getItem(key) !== null) {
          localStorage.removeItem(key);
          wiped.push(key);
        }
      } catch (_) {}
    }
    return wiped;
  }

  async function _softDeleteNarrator(pid) {
    if (typeof API === "undefined" || !API.PERSON) {
      throw new Error("API.PERSON helper not available");
    }
    var resp = await fetch(API.PERSON(pid) + "?mode=soft", { method: "DELETE" });
    if (!resp.ok) {
      throw new Error("DELETE /api/people/" + pid + " returned HTTP " + resp.status);
    }
    return true;
  }

  async function lvBbPurgeTestNarrators() {
    _setPurgeStatus('<span style="color:#94a3b8;">Fetching narrator list…</span>');

    // 1. Fetch all narrators from backend
    var allNarrators;
    try {
      var resp = await fetch(API.PEOPLE + "?limit=200");
      if (!resp.ok) {
        _setPurgeStatus('<span style="color:#f87171;">✗ FAIL — could not fetch narrators (HTTP ' + resp.status + ')</span>');
        return false;
      }
      var body = await resp.json();
      allNarrators = Array.isArray(body) ? body : (body && body.people) || [];
    } catch (e) {
      _setPurgeStatus('<span style="color:#f87171;">✗ FAIL — fetch threw: ' + (e.message || e) + '</span>');
      return false;
    }

    // 2. Select ONLY narrators whose persisted disposition says testing_only.
    //    This is a selection, not a partition: there is no "everyone else"
    //    bucket, because everyone else is simply not eligible.
    var tests = allNarrators.filter(_isPurgeEligible);

    if (!tests.length) {
      _setPurgeStatus('<span style="color:#22c55e;">✓ No testing-only narrators found. ' +
        'Nothing deleted.</span>');
      console.log("[bb-purge] no testing_only narrators; nothing to purge " +
        "(" + allNarrators.length + " narrators present, all preserved)");
      try {
        alert("No testing-only narrators to purge.\n\nNothing was deleted.\n\n" +
          "Only narrators created with testing_only are eligible. All " +
          allNarrators.length + " narrator(s) in this root are preserved.");
      } catch (_) {}
      return true;
    }

    // 3. Confirm with operator. The dialog names every narrator that is about
    //    to be soft-deleted, with its UUID prefix, so the operator verifies
    //    the actual victims rather than a count. There is deliberately no
    //    "will be preserved" list any more: preservation is the default, and
    //    printing a preserved-list invited the reader to check that the list
    //    looked right instead of checking that the DELETE list looked right.
    var testNames = tests.map(function (p) {
      return (p.display_name || p.name || "(unnamed)") + " — " + (p.id || "").slice(0, 8);
    });

    var msg =
      "PURGE " + tests.length + " testing-only narrator(s)?\n\n" +
      "Eligibility is the persisted testing_only disposition, set at creation.\n" +
      "Every other narrator in this root is preserved.\n\n" +
      "Will be DELETED (soft-delete + localStorage wipe):\n  • " + testNames.join("\n  • ") + "\n\n" +
      "Photos + memory archive on disk are NOT touched (preserved for restore).\n\n" +
      "This is irreversible from the UI. Continue?";

    var ok;
    try { ok = window.confirm(msg); } catch (_) { ok = false; }
    if (!ok) {
      _setPurgeStatus('<span style="color:#94a3b8;">Cancelled by operator.</span>');
      console.log("[bb-purge] cancelled by operator");
      return false;
    }

    // 4. Execute purge (sequential — protects backend from N parallel deletes)
    _setPurgeStatus('<span style="color:#94a3b8;">Purging ' + tests.length + ' narrators…</span>');
    console.log("[bb-purge] starting purge of " + tests.length + " test narrators");

    var succeeded = 0;
    var failed = 0;
    var ls_keys_total = 0;
    for (var i = 0; i < tests.length; i += 1) {
      var narrator = tests[i];
      var pid = narrator.id;
      if (!pid) {
        console.warn("[bb-purge] skipping narrator with no id:", narrator);
        failed += 1;
        continue;
      }

      // Re-assert eligibility immediately before anything destructive.
      // The selection above already did this; asserting again here means a
      // future edit that widens the selection, or that starts passing this
      // loop a caller-supplied list, still cannot delete a real narrator.
      // The check lives next to the delete, not only next to the filter.
      if (!_isPurgeEligible(narrator)) {
        console.error("[bb-purge] REFUSED — " + pid.slice(0, 8) +
          " is not testing_only; the purge loop was handed an ineligible " +
          "narrator. Nothing was deleted for this row.");
        failed += 1;
        continue;
      }

      // Wipe localStorage first (always succeeds)
      var wiped_keys = _wipeNarratorLocalStorage(pid);
      ls_keys_total += wiped_keys.length;

      // Soft-delete from backend
      try {
        await _softDeleteNarrator(pid);
        succeeded += 1;
        console.log("[bb-purge] purged " + (narrator.display_name || pid.slice(0, 8)) +
          " (" + pid.slice(0, 8) + ") — " + wiped_keys.length + " LS keys + 1 backend row");
      } catch (e) {
        failed += 1;
        console.warn("[bb-purge] backend delete FAILED for " +
          (narrator.display_name || pid.slice(0, 8)) + ": " + (e.message || e) +
          " — localStorage was still wiped");
      }
    }

    var summaryColor = failed ? "#fbbf24" : "#22c55e";
    var summaryIcon = failed ? "⚠" : "✓";
    _setPurgeStatus(
      '<span style="color:' + summaryColor + ';">' + summaryIcon + ' Purged ' +
      succeeded + '/' + tests.length + ' testing-only narrators (' + ls_keys_total + ' LS keys wiped' +
      (failed ? ', ' + failed + ' backend deletes failed' : '') + ').</span><br>' +
      '<span style="color:#94a3b8;">Refresh the page to see the cleaned narrator list.</span>'
    );
    console.log("[bb-purge] complete — " + succeeded + "/" + tests.length +
      " purged, " + ls_keys_total + " localStorage keys wiped, " +
      failed + " backend failures");
    return failed === 0;
  }

  window.lvBbPurgeTestNarrators = lvBbPurgeTestNarrators;
  // Exposed so the purge-eligibility boundary can be exercised against the
  // SHIPPED predicate rather than a copy of it in a test file.
  window._lvBbIsPurgeEligible = _isPurgeEligible;

  /* ───────────────────────────────────────────────────────────
     EXPORT MODULE
  ─────────────────────────────────────────────────────────── */

  window.LorevoxBioBuilderModules.core = {
    // State access
    _ensureState:             _ensureState,
    _bb:                      _bb,

    // Narrator scoping
    _resetNarratorScopedState: _resetNarratorScopedState,
    _onNarratorSwitch:         _onNarratorSwitch,
    _personChanged:            _personChanged,
    _registerPostSwitchHook:   _registerPostSwitchHook,

    // Persistence
    DRAFT_SCHEMA_VERSION:     DRAFT_SCHEMA_VERSION,
    _LS_FT_PREFIX:            _LS_FT_PREFIX,
    _LS_LT_PREFIX:            _LS_LT_PREFIX,
    _LS_QQ_PREFIX:            _LS_QQ_PREFIX,
    _LS_QC_PREFIX:            _LS_QC_PREFIX,
    _LS_DRAFT_INDEX:          _LS_DRAFT_INDEX,
    _persistDrafts:           _persistDrafts,
    _syncIdentityToBB:        _syncIdentityToBB,
    _loadDrafts:              _loadDrafts,
    _clearDrafts:             _clearDrafts,
    _getDraftIndex:           _getDraftIndex,
    _restoreQuestionnaire:    _restoreQuestionnaire,

    // BUG-208: Narrator-switch generation (in-flight async guard)
    _currentSwitchGen:        _currentSwitchGen,

    // Debug / drift detection (Phase 2.5)
    _qqDebugSnapshot:         _qqDebugSnapshot,

    // Utilities
    _el:                      _el,
    _uid:                     _uid,
    _esc:                     _esc,
    _currentPersonId:         _currentPersonId,
    _currentPersonName:       _currentPersonName,
    _formatBytes:             _formatBytes,
    _showInlineConfirm:       _showInlineConfirm,
    _emptyStateHtml:          _emptyStateHtml,
    _hasAnyValue:             _hasAnyValue,
    // BUG-BIO-QUESTIONNAIRE-LOSSY-ROUNDTRIP-01, browser-authority block.
    // Exposed so an operator can ask, from the console, why a save was
    // refused: "unhydrated" / "cache" = the server was never read;
    // "conflict" = the server says empty while this browser holds a draft.
    _qqHydrationState:        _qqHydrationState,
    _qqHydrationSettled:      _qqHydrationSettled,

    // BUG-BIO-QUESTIONNAIRE-SILENT-SAVE-FAILURE-01 — a save button must be
    // able to find out what actually happened.
    _qqSaveOutcome:           _qqSaveOutcome,
    _qqSaveOutcomeFor:        _qqSaveOutcomeFor,
    _qqCurrentSaveTicket:     function () { return _qqSaveTicket; },

    // BUG-BIO-QUESTIONNAIRE-NEW-NARRATOR-SAVE-LOCK-01 — deep content test.
    // Exported so the regression suite can drive it directly with the exact
    // documents that locked a live narrator out of saving.
    _hasOperatorContent:      _hasOperatorContent,

    // BUG-BIO-QUESTIONNAIRE-GET-CLOBBERS-EDITS-01 — a form declares that it
    // has just committed typed values, so an arriving server document does
    // not replace them.
    _markQuestionnaireEdited:  _markQuestionnaireEdited,

    // View state (shared mutable object — submodules read/write directly)
    _viewState:               _viewState
  };

})();
