/* ═══════════════════════════════════════════════════════════════════
   profile-seed-authority.js — the browser's view of who owns the walk
   WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 3, Commit B.
   Load order: BEFORE state.js (setPass consults this).
══════════════════════════════════════════════════════════════════════

── WHAT THIS IS FOR ─────────────────────────────────────────────────

Eight UI sites promote `pass1 → pass2a`. Three fire when chronology
looks ready, three on an era click, two on a mode button — and **none of
them knows anything about Profile Seed onboarding**. They conflate
"chronology is ready" and "the operator clicked something" with
"onboarding is finished", which are different facts.

Phase 2 already stopped that from breaking the walk server-side: the
composer ignores the browser's pass while a validated plan is active.
This module is the other half — the browser stops *asserting* a pass it
has no basis for, and can show the operator what the server actually
says.

── THE ONE RULE ─────────────────────────────────────────────────────

**Promotion is blocked only while the SERVER says the walk is active.**

That is not a rule invented here. `profile_seed_turn.plan_turn` returns
`IDLE` for every status except `active`, so `pending`, `paused` and
`completed` are all states in which the server is conducting nothing and
the ordinary pass engine is free to run. Encoding anything else in
JavaScript would be a second definition of onboarding state, which is
the defect this whole work order exists to remove.

── UNRESOLVED IS NOT "ALLOWED" ──────────────────────────────────────

Before hydration answers, the browser genuinely does not know. It
therefore DEFERS the promotion rather than guessing — remembering what
was requested and applying it once, if and when the server says it may.
Guessing "allowed" would race the very defect this closes; guessing
"blocked" would strand a narrator whose walk finished months ago.

── LATE RESPONSES ARE THE REAL HAZARD ───────────────────────────────

A narrator switch during an in-flight hydrate is the case that corrupts
state quietly: A's answer arrives after the operator moved to B, and B
is now described by A's walk. Three guards, the same shape BUG-208 uses
in `bio-builder-core.js`, all of which must hold before a response is
applied:

  (a) this module's own generation has not advanced;
  (b) the app-wide narrator-switch generation has not advanced;
  (c) the person the response is ABOUT is still the person we asked for.

Guard (b) reads `LorevoxBioBuilderModules.core._currentSwitchGen()`,
which already exists and is already the app's answer to this question.
Reusing it beats minting a second counter that can disagree with it.
*/
window.LorevoxProfileSeedAuthority = (function () {
  "use strict";

  var UNKNOWN = "unknown", LOADING = "loading", RESOLVED = "resolved";

  //: Mirrors `services/profile_seed.py`. Only `active` blocks promotion.
  var SERVER_ACTIVE = "active";

  var _auth = { status: UNKNOWN, personId: null, data: null, error: null };
  var _gen = 0;
  var _deferredPass = null;

  function _switchGen() {
    try {
      var mods = window.LorevoxBioBuilderModules;
      var core = mods && mods.core;
      if (core && typeof core._currentSwitchGen === "function") {
        return core._currentSwitchGen();
      }
    } catch (e) { /* module absent — guard (b) simply abstains */ }
    return null;
  }

  /* ── Lifecycle ───────────────────────────────────────────────── */

  function reset(personId) {
    _gen += 1;                       // invalidate anything in flight
    _deferredPass = null;
    _auth = { status: UNKNOWN, personId: personId || null,
              data: null, error: null };
    _emit();
    return _gen;
  }

  function snapshot() {
    return { status: _auth.status, personId: _auth.personId,
             data: _auth.data ? JSON.parse(JSON.stringify(_auth.data)) : null,
             error: _auth.error, deferredPass: _deferredPass };
  }

  /**
   * Fetch the server's answer for `personId`.
   *
   * Resolves to the snapshot either way — a REFUSED response is still an
   * answer about the world, and callers must not treat a rejected
   * promise as "no walk".
   */
  function hydrate(personId, opts) {
    opts = opts || {};
    var fetchFn = opts.fetchFn ||
      (typeof fetch === "function" ? fetch.bind(window) : null);
    if (!personId || !fetchFn) {
      _auth = { status: RESOLVED, personId: personId || null,
                data: null, error: "no person or no fetch" };
      _emit();
      return Promise.resolve(snapshot());
    }

    var stampedGen = _gen;
    var stampedSwitchGen = _switchGen();
    var stampedPid = personId;

    _auth = { status: LOADING, personId: personId, data: null, error: null };
    _emit();

    var url = (opts.url ||
      (window.ORIGIN || "http://localhost:8000") +
      "/api/interview/profile-seed?person_id=" +
      encodeURIComponent(personId));

    return fetchFn(url)
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (!_stillOurs(stampedGen, stampedSwitchGen, stampedPid, j)) {
          return snapshot();
        }
        _auth = { status: RESOLVED, personId: stampedPid,
                  data: j || null, error: j ? null : "no body" };
        _emit();
        return snapshot();
      })
      .catch(function (err) {
        if (!_stillOurs(stampedGen, stampedSwitchGen, stampedPid, null)) {
          return snapshot();
        }
        // A FAILED READ IS NOT AN ABSENT WALK. It resolves the lifecycle
        // so the UI stops waiting, and records the error so the operator
        // can see why — but `promotionDecision` treats an errored
        // resolution as "no server opinion", which permits the ordinary
        // pass engine rather than stranding the narrator on a network
        // blip.
        _auth = { status: RESOLVED, personId: stampedPid, data: null,
                  error: String((err && err.message) || err) };
        _emit();
        return snapshot();
      });
  }

  function _stillOurs(stampedGen, stampedSwitchGen, stampedPid, body) {
    if (_gen !== stampedGen) {
      _drift("this module's generation advanced", stampedPid);
      return false;
    }
    var now = _switchGen();
    if (stampedSwitchGen !== null && now !== null && now !== stampedSwitchGen) {
      _drift("narrator-switch generation advanced", stampedPid);
      return false;
    }
    if (_auth.personId !== stampedPid) {
      _drift("personId moved during the fetch", stampedPid);
      return false;
    }
    if (body && body.person_id && body.person_id !== stampedPid) {
      _drift("response is about a different narrator", stampedPid);
      return false;
    }
    return true;
  }

  function _drift(why, pid) {
    try {
      console.warn("[profile-seed][drift] response DISCARDED: " + why +
                   " (requested=" + String(pid).slice(0, 8) + ")");
    } catch (e) { /* console is not load-bearing */ }
  }

  /* ── Promotion policy — the ONLY place that decides ───────────── */

  /**
   * May the pass engine move to `requestedPass`?
   *
   * Returns `{ allow, defer, reason }`. `defer` means "ask again once
   * the server has answered"; the caller records the request rather than
   * dropping it.
   */
  function promotionDecision(requestedPass) {
    // Returning to pass1 is the SAFE direction and is never blocked. A
    // guard that refused it could strand the UI in a promoted pass it
    // was told to leave.
    if (!requestedPass || requestedPass === "pass1") {
      return { allow: true, defer: false, reason: "not a promotion" };
    }
    if (_auth.status === UNKNOWN || _auth.status === LOADING) {
      return { allow: false, defer: true,
               reason: "onboarding authority not resolved yet" };
    }
    var d = _auth.data;
    if (!d || d.enrolled === false) {
      return { allow: true, defer: false,
               reason: "narrator is not enrolled in a walk" };
    }
    if (d.status === SERVER_ACTIVE) {
      return { allow: false, defer: false,
               reason: "Profile Seed walk is active (topic: " +
                       (d.active_topic_id || "?") + ")" };
    }
    // pending / paused / completed — the server conducts nothing, so the
    // ordinary pass engine owns the turn. Derived from plan_turn's rule,
    // not decided here.
    return { allow: true, defer: false,
             reason: "server status is " + String(d.status) };
  }

  function rememberDeferred(pass) { _deferredPass = pass || null; }
  function deferredPass() { return _deferredPass; }
  function clearDeferred() { _deferredPass = null; }

  /**
   * Apply a deferred promotion ONCE, if the server now allows it.
   *
   * Called after hydration resolves. Returns the pass applied, or null.
   */
  function applyDeferred(applyFn) {
    if (!_deferredPass) return null;
    var decision = promotionDecision(_deferredPass);
    if (decision.defer) return null;          // still unresolved
    var pass = _deferredPass;
    _deferredPass = null;                     // once, either way
    if (!decision.allow) {
      try {
        console.info("[profile-seed][promotion] deferred " + pass +
                     " DROPPED: " + decision.reason);
      } catch (e) {}
      _emit();
      return null;
    }
    if (typeof applyFn === "function") applyFn(pass);
    _emit();
    return pass;
  }

  /* ── Progress, for the operator ───────────────────────────────── */

  function progress() {
    var d = _auth.data;
    if (_auth.status !== RESOLVED || !d || d.enrolled === false) return null;
    var remaining = (d.remaining_topics || []).length;
    var ts = d.topic_state || {};
    var total = Object.keys(ts).length;
    return {
      status: d.status || null,
      activeTopic: d.active_topic_id || null,
      version: d.version,
      total: total,
      remaining: remaining,
      answered: total ? (total - remaining) : 0
    };
  }

  /* ── Pause / resume — versioned, through the existing endpoint ── */

  /**
   * `action` is "pause" or "resume". The version is the one the last
   * hydrate READ, which is what makes this optimistic concurrency rather
   * than a blind write: a stale operator command loses to whatever moved
   * the row, and the 409 body carries the current state.
   */
  function setPaused(action, opts) {
    opts = opts || {};
    var fetchFn = opts.fetchFn ||
      (typeof fetch === "function" ? fetch.bind(window) : null);
    var d = _auth.data;
    if (!fetchFn || !d || _auth.status !== RESOLVED) {
      return Promise.resolve({ ok: false, reason: "authority not resolved" });
    }
    var pid = _auth.personId;
    var url = (opts.url || (window.ORIGIN || "http://localhost:8000") +
               "/api/interview/profile-seed");
    return fetchFn(url, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ person_id: pid,
                             expected_version: d.version,
                             action: action })
    }).then(function (r) {
      if (r.status === 409) {
        return r.json().then(function (body) {
          // THE SERVER WON. Re-read rather than retrying blindly: the
          // row moved for a reason this client cannot see.
          return hydrate(pid, opts).then(function () {
            return { ok: false, conflict: true, detail: body };
          });
        });
      }
      if (!r.ok) return { ok: false, reason: "http " + r.status };
      return r.json().then(function (fresh) {
        if (_auth.personId !== pid) return { ok: false, reason: "narrator moved" };
        _auth = { status: RESOLVED, personId: pid, data: fresh, error: null };
        _emit();
        return { ok: true, data: fresh };
      });
    });
  }

  /* ── Change notification, for the progress UI ─────────────────── */

  var _listeners = [];
  function onChange(fn) { if (typeof fn === "function") _listeners.push(fn); }
  function _emit() {
    for (var i = 0; i < _listeners.length; i++) {
      try { _listeners[i](snapshot()); } catch (e) { /* one bad listener
        must not break the others, or the walk */ }
    }
  }

  return {
    UNKNOWN: UNKNOWN, LOADING: LOADING, RESOLVED: RESOLVED,
    SERVER_ACTIVE: SERVER_ACTIVE,
    reset: reset,
    hydrate: hydrate,
    snapshot: snapshot,
    promotionDecision: promotionDecision,
    rememberDeferred: rememberDeferred,
    deferredPass: deferredPass,
    clearDeferred: clearDeferred,
    applyDeferred: applyDeferred,
    progress: progress,
    setPaused: setPaused,
    onChange: onChange
  };
})();

/* Node test harness support. The browser ignores this. */
if (typeof module !== "undefined" && module.exports) {
  module.exports = window.LorevoxProfileSeedAuthority;
}
