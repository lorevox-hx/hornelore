#!/usr/bin/env node
/**
 * WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 Phase 2, Part B —
 * behaviour a source scan cannot judge.
 *
 * `tests/test_surface_narrator_context.py` pins that every launcher goes
 * through the helper and that no surface writes the shell key. Neither of
 * those answers the question the operator's data depends on:
 *
 *   * does an explicit narrator that does NOT exist fail closed, or does
 *     it quietly fall back to whatever this surface remembered?
 *
 * That fallback is the actual harm. Photo Intake stamps every upload with
 * the narrator it believes in, so "the link was wrong, so I used the last
 * one" writes one family's photographs into another's library.
 *
 * This executes the SHIPPED ui/js/narrator-context.js against a fake
 * window, localStorage and fetch. A reimplementation of the rules here
 * would keep passing after somebody changed the product.
 *
 * Usage:  node scripts/ui/run_narrator_context_behaviour.js
 * Exit 0 all green, 1 otherwise. No server, no browser, no arguments.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SRC = path.resolve(__dirname, "..", "..", "ui", "js", "narrator-context.js");

const R = [];
function check(name, ok, detail) {
  R.push({ name, ok: !!ok, detail: detail === undefined ? "" : String(detail) });
}

const ALICE = "11111111-1111-1111-1111-111111111111";
const BOB = "22222222-2222-2222-2222-222222222222";
const GHOST = "99999999-9999-9999-9999-999999999999";

/* One sandbox per scenario: a shared one would let a remember() from an
   earlier case decide a later one, which is precisely the cross-talk
   being tested. */
function load(opts) {
  opts = opts || {};
  const store = Object.assign({}, opts.storage || {});
  const warnings = [];
  const calls = [];
  const localStorage = {
    getItem: k => (Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: k => { delete store[k]; },
  };
  const sandbox = {
    window: { location: { search: opts.search || "" } },
    localStorage,
    URLSearchParams,
    console: { warn: m => warnings.push(String(m)), log: () => {} },
    fetch: function (url) {
      calls.push(url);
      if (opts.peopleFails) return Promise.reject(new Error("network down"));
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          people: [
            { id: ALICE, display_name: "Alice Example" },
            { id: BOB, display_name: "Bob Example" },
          ],
        }),
      });
    },
    Promise,
  };
  sandbox.window.localStorage = localStorage;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(SRC, "utf8"), sandbox);
  return {
    NC: sandbox.window.LorevoxNarratorContext,
    store, warnings, calls,
    apiBase: "http://x",
  };
}

const LEGACY = "pi_narrator_id_v1";

(async function run() {

  // ── the rule that matters most ─────────────────────────────────────
  {
    const s = load({
      search: "?narrator_id=" + GHOST,
      storage: { [LEGACY]: BOB },
    });
    const res = await s.NC.resolve({ apiBase: s.apiBase, legacyKey: LEGACY });
    check("an INVALID explicit narrator selects nobody",
      res.personId === "" && res.source === "query_invalid",
      res.source + " -> " + res.personId);
    check("...and CANNOT fall back to this surface's cached narrator",
      res.personId !== BOB,
      "cache held " + BOB + ", resolver returned " + (res.personId || "(none)"));
    check("...and says so in words the operator can act on",
      /does not exist/i.test(res.error), res.error);
    check("...and leaves the cache alone rather than clearing it",
      s.store[LEGACY] === BOB);
  }

  // ── explicit beats cache ───────────────────────────────────────────
  {
    const s = load({
      search: "?narrator_id=" + ALICE,
      storage: { [LEGACY]: BOB },
    });
    const res = await s.NC.resolve({ apiBase: s.apiBase, legacyKey: LEGACY });
    check("a VALID explicit narrator wins over the cache",
      res.personId === ALICE && res.source === "query", res.source);
    check("the people list comes back with it, so the picker needs no second fetch",
      res.people.length === 2 && s.calls.length === 1,
      "fetches=" + s.calls.length);
  }

  // ── the person_id alias ────────────────────────────────────────────
  {
    const s = load({ search: "?person_id=" + ALICE });
    const res = await s.NC.resolve({ apiBase: s.apiBase, legacyKey: LEGACY });
    check("the historical ?person_id= spelling is accepted too",
      res.personId === ALICE && res.source === "query");
  }

  // ── direct load may use a validated cache ──────────────────────────
  {
    const s = load({ search: "", storage: { [LEGACY]: BOB } });
    const res = await s.NC.resolve({ apiBase: s.apiBase, legacyKey: LEGACY });
    check("a direct load with no query may use its own cache",
      res.personId === BOB && res.source === "cache");
  }
  {
    const s = load({ search: "", storage: { [LEGACY]: GHOST } });
    const res = await s.NC.resolve({ apiBase: s.apiBase, legacyKey: LEGACY });
    check("a STALE cache selects nobody and is dropped",
      res.personId === "" && res.source === "cache_invalid" &&
      s.store[LEGACY] === undefined,
      res.source + " store=" + String(s.store[LEGACY]));
  }
  {
    const s = load({ search: "" });
    const res = await s.NC.resolve({ apiBase: s.apiBase, legacyKey: LEGACY });
    check("no query and no cache is an empty state, not an error",
      res.personId === "" && res.source === "none" && res.error === "");
  }

  // ── a failed lookup is not permission to trust ─────────────────────
  {
    const s = load({
      search: "?narrator_id=" + ALICE,
      storage: { [LEGACY]: BOB },
      peopleFails: true,
    });
    const res = await s.NC.resolve({ apiBase: s.apiBase, legacyKey: LEGACY });
    check("when /api/people cannot be read, NOTHING is selected",
      res.personId === "" && res.source === "unvalidated" &&
      res.peopleOk === false, res.source);
    check("...not even the id that was explicitly asked for",
      res.personId !== ALICE);
  }

  // ── the shell key is structurally out of reach ─────────────────────
  {
    const s = load({});
    const ok = s.NC.remember(LEGACY, ALICE);
    check("a surface may write its OWN cache",
      ok === true && s.store[LEGACY] === ALICE);

    const refused = s.NC.remember(s.NC.SHELL_KEY, BOB);
    check("a surface may NOT write the shell's key",
      refused === false && s.store[s.NC.SHELL_KEY] === undefined);
    check("...and the refusal is announced rather than silent",
      s.warnings.some(w => /refusing to write the shell key/.test(w)),
      JSON.stringify(s.warnings));
  }
  {
    // Nothing in the module may READ the shell key either: a standalone
    // page inheriting the shell's selection through localStorage would
    // reintroduce the ambient authority this contract removes.
    const s = load({ storage: { "lv_active_person_v55": ALICE } });
    const res = await s.NC.resolve({ apiBase: s.apiBase, legacyKey: LEGACY });
    check("the shell key is never read as a fallback",
      res.personId === "" && res.source === "none", res.source);
    check("readCache refuses the shell key outright",
      s.NC.readCache(s.NC.SHELL_KEY) === "");
  }

  // ── link building ──────────────────────────────────────────────────
  {
    const s = load({});
    check("withNarrator appends the narrator",
      s.NC.withNarrator("photo-intake.html", ALICE) ===
      "photo-intake.html?narrator_id=" + ALICE);
    check("withNarrator preserves an existing query string",
      s.NC.withNarrator("photo-elicit.html?trip_id=T1", ALICE) ===
      "photo-elicit.html?trip_id=T1&narrator_id=" + ALICE);
    check("withNarrator with no narrator returns the page unchanged",
      s.NC.withNarrator("trip-tab.html", "") === "trip-tab.html");
    check("an id needing escaping is encoded",
      s.NC.withNarrator("x.html", "a b&c") === "x.html?narrator_id=a%20b%26c");
  }

  // ── /api/people shape tolerance ────────────────────────────────────
  {
    const s = load({});
    const shapes = [
      [{ id: ALICE, display_name: "A" }],
      { people: [{ id: ALICE, display_name: "A" }] },
      { items: [{ person_id: ALICE, name: "A" }] },
    ];
    const ok = shapes.every(function (shape) {
      const out = s.NC.normalizePeople(shape);
      return out.length === 1 && out[0].id === ALICE;
    });
    check("all three historical /api/people shapes normalise to one", ok);
    check("a row with no id is dropped rather than becoming a blank narrator",
      s.NC.normalizePeople([{ display_name: "nameless" }]).length === 0);
  }

  // ── report ──────────────────────────────────────────────────────────
  let failed = 0;
  R.forEach(function (r) {
    if (!r.ok) failed++;
    console.log((r.ok ? "PASS  " : "FAIL  ") + r.name +
      (r.detail ? "  [" + r.detail + "]" : ""));
  });
  console.log("");
  console.log(R.length - failed + " passed, " + failed + " failed");
  process.exit(failed ? 1 : 0);
})();
