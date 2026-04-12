/* ═══════════════════════════════════════════════════════════════════════
   WO-13 Phase 8 B3 — lvxRefreshProfileFromServer shim test

   Phase 8 introduced a single client-side refresh shim in app.js that
   wo13-review.js calls after a successful promote. The shim is the ONLY
   way the downstream UI (profile form, obituary identity card, memoir
   source name, timeline spine, session payload) learns about promoted
   truth without a full page reload.

   B3 verifies the shim's contract in isolation:

     1. It issues a GET against API.PROFILE(pid)
     2. It normalises the returned profile and stashes it on state.profile
     3. It updates the offline localStorage snapshot
     4. It invokes hydrateProfileForm, updateObitIdentityCard, renderTimeline
     5. It updates memoirSourceName.textContent with preferred || fullname
     6. It posts to API.SESS_PUT with {conv_id, payload:{profile, person_id}}
        when state.chat.conv_id is present, and NOT when it is absent
     7. It short-circuits on falsy pid and on !r.ok
     8. It swallows fetch errors via console.warn (no throw propagation)

   This is a pure behaviour test. It does not load a browser, does not
   import the rest of app.js, and does not touch the network. The shim
   text is sliced out of app.js at test time so the test cannot drift
   out of sync with the implementation — any edit to app.js that breaks
   the slice markers will surface as a test failure.
   ═══════════════════════════════════════════════════════════════════════ */
"use strict";
const fs   = require("fs");
const path = require("path");
const vm   = require("vm");

const REPO_ROOT = path.resolve(__dirname, "..", "mnt", "hornelore");
const APP_JS    = path.join(REPO_ROOT, "ui", "js", "app.js");

let passed = 0, failed = 0;
function ok(label, cond, extra){
  if(cond){ passed++; console.log("  OK  " + label); }
  else    {
    failed++;
    console.log("  FAIL  " + label + (extra ? "  → " + extra : ""));
  }
}
function die(msg){
  console.log("\n  FATAL  " + msg);
  process.exit(1);
}

console.log("=".repeat(62));
console.log("WO-13 Phase 8 B3 — lvxRefreshProfileFromServer shim test");
console.log("=".repeat(62));

// ── 1. Slice the shim out of app.js ────────────────────────────────────
const src = fs.readFileSync(APP_JS, "utf8");
const startMarker = "window.lvxRefreshProfileFromServer = async function(pid)";
const startIdx = src.indexOf(startMarker);
if (startIdx < 0) die("could not locate lvxRefreshProfileFromServer in app.js");

// Find the matching end by walking braces from the function body.
const openIdx = src.indexOf("{", startIdx);
let depth = 0, endIdx = -1;
for (let i = openIdx; i < src.length; i++){
  const c = src[i];
  if (c === "{") depth++;
  else if (c === "}") {
    depth--;
    if (depth === 0) { endIdx = i + 1; break; }
  }
}
if (endIdx < 0) die("could not find end of shim function body");
// include the trailing semicolon if present
if (src[endIdx] === ";") endIdx++;

const shimSrc = src.slice(startIdx, endIdx);
ok("slice: extracted " + shimSrc.length + " chars of shim source from app.js",
   shimSrc.length > 200 && shimSrc.includes("state.profile"));

// ── 2. Build a sandbox with every dependency mocked ────────────────────
function makeSandbox(opts = {}){
  const log = {
    fetches:          [],    // URLs fetched
    sessPosts:        [],    // bodies posted to SESS_PUT
    localStorageSets: [],    // keys written
    hydrateCalls:     0,
    obitCalls:        [],    // basics passed
    timelineCalls:    0,
    warns:            [],
  };

  const state = {
    profile: null,
    chat: opts.conv_id ? { conv_id: opts.conv_id } : {},
  };

  const memoirEl = { textContent: "(initial)" };
  const doc = {
    getElementById(id){
      if (id === "memoirSourceName") return memoirEl;
      return null;
    },
  };

  const API = {
    PROFILE(pid){ return "/api/profiles/" + pid; },
    SESS_PUT: "/api/session/put",
  };

  const localStorage = {
    _store: {},
    setItem(k, v){
      log.localStorageSets.push(k);
      // Throw on the first call if the caller wants to test the try/catch.
      if (opts.localStorageThrows){
        throw new Error("quota exceeded");
      }
      this._store[k] = v;
    },
  };

  // Fake fetch: first call is the GET profile, second is the session POST.
  const fakeFetch = async (url, init) => {
    log.fetches.push({ url, method: init?.method || "GET" });
    if (url === API.SESS_PUT){
      log.sessPosts.push(init?.body);
      return { ok: true, json: async () => ({}) };
    }
    // profile GET
    if (opts.profileFetchThrows){
      throw new Error("network down");
    }
    if (opts.profileNotOk){
      return { ok: false, status: 500, json: async () => ({}) };
    }
    return {
      ok: true,
      json: async () => opts.profilePayload || {
        profile: {
          basics: {
            fullname: "Ada Lovelace",
            preferred: "Ada",
            dob: "1815-12-10",
          },
          kinship: [],
          pets: [],
        },
      },
    };
  };

  const sandbox = {
    console: {
      warn: (...args) => log.warns.push(args.map(String).join(" ")),
      log:  () => {},
    },
    // shim reaches these via bare identifier lookup:
    fetch:              fakeFetch,
    API,
    state,
    normalizeProfile:   (x) => { return Object.assign({ _normalized: true }, x); },
    localStorage,
    hydrateProfileForm: () => { log.hydrateCalls++; },
    updateObitIdentityCard: (basics) => { log.obitCalls.push(basics); },
    document:           doc,
    renderTimeline:     () => { log.timelineCalls++; },
    ctype:              () => ({ "Content-Type": "application/json" }),
    // window binding — shim writes window.lvxRefreshProfileFromServer
    window:             {},
  };
  sandbox.global = sandbox;
  vm.createContext(sandbox);

  // Evaluate the shim source inside this sandbox. The shim assigns to
  // window.lvxRefreshProfileFromServer, so we grab it afterwards.
  vm.runInContext(shimSrc, sandbox, { filename: "lvxRefreshProfileFromServer.slice.js" });
  const fn = sandbox.window.lvxRefreshProfileFromServer;
  if (typeof fn !== "function"){
    die("shim did not register as a function on window");
  }

  return { fn, log, state, memoirEl, sandbox };
}

// ── 3. Happy path: logged-in chat session, normal profile ──────────────
(async () => {
  try {
    {
      const { fn, log, state, memoirEl } = makeSandbox({ conv_id: "conv-abc" });
      await fn(42);

      ok("happy: fetched GET /api/profiles/42",
         log.fetches.length >= 1 && log.fetches[0].url === "/api/profiles/42");

      ok("happy: state.profile normalised and populated",
         state.profile && state.profile._normalized === true &&
         state.profile.basics?.preferred === "Ada");

      ok("happy: localStorage snapshot written under lorevox_offline_profile_42",
         log.localStorageSets.includes("lorevox_offline_profile_42"));

      ok("happy: hydrateProfileForm called exactly once",
         log.hydrateCalls === 1);

      ok("happy: updateObitIdentityCard received basics",
         log.obitCalls.length === 1 &&
         log.obitCalls[0].fullname === "Ada Lovelace");

      ok("happy: memoirSourceName populated from preferred name",
         memoirEl.textContent === "Ada");

      ok("happy: renderTimeline called exactly once",
         log.timelineCalls === 1);

      const sessPost = log.fetches.find(f => f.url === "/api/session/put");
      ok("happy: session POST issued to SESS_PUT",
         !!sessPost && sessPost.method === "POST");

      const body = JSON.parse(log.sessPosts[0]);
      ok("happy: session POST body carries {conv_id, payload:{profile, person_id}}",
         body.conv_id === "conv-abc" &&
         body.payload?.person_id === 42 &&
         body.payload?.profile?._normalized === true);

      ok("happy: no warnings emitted", log.warns.length === 0);
    }

    // ── 4. Falsy pid → early return, no fetches ───────────────────────
    {
      const { fn, log } = makeSandbox({ conv_id: "conv-xyz" });
      await fn(null);
      ok("falsy pid: no fetches issued", log.fetches.length === 0);
      ok("falsy pid: no DOM updates",
         log.hydrateCalls === 0 && log.timelineCalls === 0);
      await fn(undefined);
      await fn(0);
      await fn("");
      ok("falsy pid: all falsy values short-circuit",
         log.fetches.length === 0);
    }

    // ── 5. Non-OK profile response → silent return ─────────────────────
    {
      const { fn, log, state } = makeSandbox({
        conv_id: "conv-xyz",
        profileNotOk: true,
      });
      await fn(7);
      ok("!r.ok: the profile GET was attempted",
         log.fetches.length === 1);
      ok("!r.ok: state.profile left untouched (null)",
         state.profile === null);
      ok("!r.ok: no hydrate/obit/timeline side effects",
         log.hydrateCalls === 0 &&
         log.obitCalls.length === 0 &&
         log.timelineCalls === 0);
      ok("!r.ok: no session POST issued",
         log.sessPosts.length === 0);
      ok("!r.ok: no warning emitted (this path is a silent return)",
         log.warns.length === 0);
    }

    // ── 6. fetch() throws → caught, warned, never rethrows ─────────────
    {
      const { fn, log, state } = makeSandbox({
        conv_id: "conv-xyz",
        profileFetchThrows: true,
      });
      let threw = false;
      try { await fn(9); } catch (e) { threw = true; }
      ok("fetch throws: shim did not propagate the error", !threw);
      ok("fetch throws: console.warn emitted", log.warns.length === 1);
      ok("fetch throws: warn message mentions 'refresh profile'",
         /refresh profile/.test(log.warns[0]));
      ok("fetch throws: state.profile left null", state.profile === null);
    }

    // ── 7. localStorage.setItem throws → still runs rest of pipeline ──
    {
      const { fn, log, state, memoirEl } = makeSandbox({
        conv_id: "conv-xyz",
        localStorageThrows: true,
      });
      await fn(42);
      ok("localStorage throws: state.profile still populated",
         state.profile?.basics?.preferred === "Ada");
      ok("localStorage throws: hydrate/obit/timeline still ran",
         log.hydrateCalls === 1 &&
         log.obitCalls.length === 1 &&
         log.timelineCalls === 1);
      ok("localStorage throws: memoir source name still updated",
         memoirEl.textContent === "Ada");
      ok("localStorage throws: session POST still issued",
         log.sessPosts.length === 1);
      ok("localStorage throws: no warning surfaced (inner try/catch)",
         log.warns.length === 0);
    }

    // ── 8. No chat.conv_id → skip session POST ─────────────────────────
    {
      const { fn, log, state, memoirEl } = makeSandbox({ /* no conv_id */ });
      await fn(11);
      ok("no conv_id: state.profile populated",
         state.profile?.basics?.preferred === "Ada");
      ok("no conv_id: hydrate/obit/timeline all ran",
         log.hydrateCalls === 1 &&
         log.obitCalls.length === 1 &&
         log.timelineCalls === 1);
      const sessPost = log.fetches.find(f => f.url === "/api/session/put");
      ok("no conv_id: session POST was NOT issued", !sessPost);
      ok("no conv_id: memoir source name updated",
         memoirEl.textContent === "Ada");
    }

    // ── 9. Fallback memoir name: no preferred, uses fullname ───────────
    {
      const { fn, memoirEl } = makeSandbox({
        conv_id: "c1",
        profilePayload: {
          profile: {
            basics: { fullname: "Lord Byron" /* no preferred */ },
            kinship: [], pets: [],
          },
        },
      });
      await fn(12);
      ok("memoir fallback: uses fullname when preferred is absent",
         memoirEl.textContent === "Lord Byron");
    }

    // ── 10. Fallback memoir name: neither present → default string ────
    {
      const { fn, memoirEl } = makeSandbox({
        conv_id: "c1",
        profilePayload: {
          profile: { basics: {}, kinship: [], pets: [] },
        },
      });
      await fn(13);
      ok("memoir fallback: default 'No person selected' when both empty",
         memoirEl.textContent === "No person selected");
    }

    // ── 11. Payload shape tolerance: bare profile object (no wrapper) ──
    {
      const { fn, state } = makeSandbox({
        conv_id: "c1",
        // Shim does: j.profile || j || {} — so passing a bare profile
        // without a .profile key should still be accepted.
        profilePayload: {
          basics: { preferred: "Bare" },
          kinship: [],
          pets: [],
        },
      });
      await fn(14);
      ok("payload tolerance: bare profile object (no .profile wrapper) accepted",
         state.profile?.basics?.preferred === "Bare");
    }

    // ── 12. wo13-review.js still calls the shim post-promote ───────────
    // Regression check: if somebody renames/deletes the call site in
    // wo13-review.js, B3 should shout. This is a pure string check
    // against the current wo13-review.js.
    {
      const reviewSrc = fs.readFileSync(
        path.join(REPO_ROOT, "ui", "js", "wo13-review.js"), "utf8");
      ok("wiring: wo13-review.js invokes lvxRefreshProfileFromServer",
         reviewSrc.includes("lvxRefreshProfileFromServer"));
    }

    // ── 13. Summary ────────────────────────────────────────────────────
    console.log();
    console.log("=".repeat(62));
    if (failed === 0){
      console.log(`  WO-13 Phase 8 B3 — ALL SHIM ASSERTIONS PASSED  (${passed}/${passed})`);
    } else {
      console.log(`  WO-13 Phase 8 B3 — ${failed} FAILED / ${passed} passed`);
    }
    console.log("=".repeat(62));
    process.exit(failed === 0 ? 0 : 1);
  } catch (e) {
    console.error("\n  UNCAUGHT  " + (e && e.stack || e));
    process.exit(1);
  }
})();
