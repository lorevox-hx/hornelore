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
  /* ── FAILED IS ITS OWN STATE, NOT A RESOLVED EMPTY ONE ─────────────
     The first cut folded network errors and non-OK responses into
     RESOLVED with `data: null`, which `promotionDecision` then read as
     "no walk" and ALLOWED. That directly contradicted the comment
     sitting above it saying a failed read is not an absent walk — the
     prose was right and the code did the opposite.

     A 500 or a dropped connection tells us NOTHING about whether a walk
     is running, so it must not authorize a promotion. FAILED defers
     like UNKNOWN does, keeps the pass safe, and carries an error the
     operator can see and retry. */
  var FAILED = "failed";

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
      .then(function (r) {
        if (!r.ok) {
          // A non-OK response is a FAILURE, not an empty answer. 404 is
          // included deliberately: the GET returns 200 with
          // `enrolled: false` for a real unenrolled narrator, so a 404
          // means the id names nobody — which is not permission to
          // promote either.
          var err = new Error("http " + r.status);
          err.__httpStatus = r.status;
          throw err;
        }
        return r.json();
      })
      .then(function (j) {
        if (!_stillOurs(stampedGen, stampedSwitchGen, stampedPid, j)) {
          return snapshot();
        }
        if (!j) {
          _auth = { status: FAILED, personId: stampedPid, data: null,
                    error: "empty response body" };
        } else {
          _auth = { status: RESOLVED, personId: stampedPid,
                    data: j, error: null };
        }
        _emit();
        return snapshot();
      })
      .catch(function (err) {
        if (!_stillOurs(stampedGen, stampedSwitchGen, stampedPid, null)) {
          return snapshot();
        }
        // A FAILED READ IS NOT AN ABSENT WALK — and now the code agrees.
        // FAILED stops the UI waiting and shows the operator a reason
        // and a retry, while `promotionDecision` keeps deferring, so a
        // 500 cannot become permission to promote past an active walk.
        _auth = { status: FAILED, personId: stampedPid, data: null,
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
    if (_auth.status === FAILED) {
      // Defer, not allow. The request is remembered so a successful
      // retry can honour it, and the pass stays where it safely is.
      return { allow: false, defer: true, retry: true,
               reason: "onboarding state could not be read (" +
                       (_auth.error || "unknown error") + ") — retry" };
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
    // ── THE PATCH CARRIES THE SAME GUARDS AS A HYDRATE, Phase 3B ─────
    //
    // *(It did not, and the gap was reachable: pause narrator A, switch
    // to B, A's PATCH returns 409, the handler called `hydrate(A)` —
    // and `hydrate` sets `_auth.personId` to its argument BEFORE its own
    // drift checks run. So recovering from A's conflict overwrote B's
    // authority with A's. That is precisely the cross-narrator failure
    // this module exists to prevent, arriving through the one path that
    // had no guards.)*
    var stampedGen = _gen;
    var stampedSwitchGen = _switchGen();
    var stampedPid = pid;
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
          // GUARD BEFORE RECOVERING. A conflict for a narrator we have
          // already left is not ours to repair; re-reading them here is
          // what corrupted the current narrator's state.
          if (!_stillOurs(stampedGen, stampedSwitchGen, stampedPid, null)) {
            return { ok: false, conflict: true, stale: true, detail: body };
          }
          // THE SERVER WON. Re-read rather than retrying blindly: the
          // row moved for a reason this client cannot see.
          return hydrate(stampedPid, opts).then(function () {
            return { ok: false, conflict: true, detail: body };
          });
        });
      }
      if (!r.ok) return { ok: false, reason: "http " + r.status };
      return r.json().then(function (fresh) {
        if (!_stillOurs(stampedGen, stampedSwitchGen, stampedPid, fresh)) {
          return { ok: false, stale: true, reason: "narrator moved" };
        }
        _auth = { status: RESOLVED, personId: stampedPid, data: fresh,
                  error: null };
        _emit();
        return { ok: true, data: fresh };
      });
    });
  }

  /* ── The promotion choke point's actual body ──────────────────────
     `state.js::setPass()` DELEGATES here.

     *(The policy used to live in `state.js` and the Node suite carried a
     second copy of it, described as "byte-for-byte in policy terms".
     Two implementations of one rule is the drift this work order exists
     to remove, and the test copy could not catch the production one
     changing — 35 green tests would have kept reporting green. The rule
     lives here, once; `state.js` calls it; a source assertion proves the
     delegation is still wired.)* */
  function applyPass(session, requestedPass) {
    if (!session) return { applied: false, reason: "no session" };
    var decision = promotionDecision(requestedPass);
    if (decision.defer) {
      rememberDeferred(requestedPass);
      session.passDeferredReason = decision.reason;
      return { applied: false, deferred: true, reason: decision.reason };
    }
    session.passDeferredReason = null;
    if (!decision.allow) {
      session.passBlockedReason = decision.reason;
      try {
        console.info("[profile-seed][promotion] " + requestedPass +
                     " BLOCKED: " + decision.reason);
      } catch (e) {}
      return { applied: false, blocked: true, reason: decision.reason };
    }
    session.passBlockedReason = null;
    session.currentPass = requestedPass;
    return { applied: true, reason: decision.reason };
  }

  /**
   * Pull an ALREADY-PROMOTED browser pass back to safety.
   *
   * Blocking future promotions is not enough on its own. The browser can
   * already be sitting in `pass2a` — restored from persisted state, or
   * promoted while the walk was paused and then resumed. Reconciling is
   * what makes the guard true of the CURRENT view rather than only of
   * the next click.
   */
  function reconcile(session) {
    if (!session || !session.currentPass || session.currentPass === "pass1") {
      return { changed: false };
    }
    var decision = promotionDecision(session.currentPass);
    if (decision.allow || decision.defer) return { changed: false };
    var was = session.currentPass;
    session.currentPass = "pass1";
    session.passBlockedReason = decision.reason;
    try {
      console.info("[profile-seed][promotion] demoted " + was +
                   " -> pass1: " + decision.reason);
    } catch (e) {}
    _emit();
    return { changed: true, from: was, reason: decision.reason };
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
    FAILED: FAILED,
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
    applyPass: applyPass,
    reconcile: reconcile,
    onChange: onChange
  };
})();

/* Node test harness support. The browser ignores this. */
if (typeof module !== "undefined" && module.exports) {
  module.exports = window.LorevoxProfileSeedAuthority;
}
