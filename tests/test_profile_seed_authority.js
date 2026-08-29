/* Profile Seed browser authority — promotion policy and late responses.
   WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 3, Commit B.

     node tests/test_profile_seed_authority.js

── WHAT THIS COVERS ─────────────────────────────────────────────────

The eight promotion sites all call `setPass()`, so the policy is tested
once at the choke point rather than eight times at the callers. The
three TRIGGER CLASSES are still exercised individually, because they
reach the choke point by different routes and a future change could
detach one of them:

  * chronology readiness — server spine, cached spine, seed spine;
  * era navigation — selectEra, roadmap click, accordion jump;
  * mode buttons — chronological / thematic.

The late-response cases are the ones worth the most: a narrator switch
during an in-flight hydrate is how one narrator's walk quietly becomes
another's.
*/
"use strict";

const assert = require("assert");
const path = require("path");

let passed = 0, failed = 0;

/* ── TESTS RUN SEQUENTIALLY, AND THAT IS NOT OPTIONAL ────────────────
   The module under test is a SINGLETON with one narrator-scoped state
   object — which is what it must be, because the browser has one
   operator looking at one narrator. Letting async tests interleave made
   them reset and hydrate each other's fixtures: the first run reported
   18 failures that were entirely cross-test interference, including a
   "late response updated narrator B" failure whose drift guard had in
   fact worked perfectly.

   So every test is queued and awaited in order. A harness that can
   corrupt its own subject proves nothing about the subject.
──────────────────────────────────────────────────────────────────── */
const QUEUE = [];
function test(name, fn) { QUEUE.push({ name, fn }); }
function atest(name, fn) { QUEUE.push({ name, fn }); }

async function runAll() {
  for (const t of QUEUE) {
    try { await t.fn(); console.log("  PASS  " + t.name); passed++; }
    catch (e) {
      console.log("  FAIL  " + t.name + "\n        " + e.message);
      failed++;
    }
  }
  console.log("\n  " + passed + " passed, " + failed + " failed\n");
  process.exit(failed ? 1 : 0);
}

/* ── Load the module under a minimal browser shim ─────────────────── */
global.window = global.window || {};
global.console = console;
const AUTH = require(path.join(__dirname, "..", "ui", "js",
                               "profile-seed-authority.js"));

/* ── NO STAND-IN. THE REAL FUNCTION. ────────────────────────────────
   *(This file used to carry its own copy of setPass's policy, described
   as "byte-for-byte in policy terms". Two implementations of one rule
   is precisely the drift this work order exists to remove, and the copy
   could not catch the production one changing — all 35 tests would have
   stayed green while `state.js` diverged.)*

   The policy body now lives in the authority module as `applyPass`, and
   `state.js::setPass()` delegates to it. This calls the same function
   production calls; `ProductionDelegationTests` below proves the
   delegation is still wired. */
function makeSession() { return { currentPass: "pass1" }; }
function setPass(session, p) { return AUTH.applyPass(session, p); }

function serverState(over) {
  return Object.assign({
    person_id: "p-1", enrolled: true, status: "active",
    active_topic_id: "childhood_home", version: 3,
    known_topics: [], remaining_topics: ["childhood_home", "siblings"],
    topic_state: { childhood_home: "unanswered", siblings: "unanswered" }
  }, over || {});
}
function fetchOK(body, opts) {
  opts = opts || {};
  return function () {
    return Promise.resolve({
      ok: true, status: 200,
      json: function () {
        return (opts.delay
          ? new Promise(r => setTimeout(() => r(body), opts.delay))
          : Promise.resolve(body));
      }
    });
  };
}

console.log("\nProfile Seed browser authority\n");

/* ── 1. Unresolved defers, never guesses ──────────────────────────── */
test("an unresolved authority DEFERS promotion rather than allowing it", () => {
  AUTH.reset("p-1");
  const s = makeSession();
  setPass(s, "pass2a");
  assert.strictEqual(s.currentPass, "pass1", "promoted before the server answered");
  assert.strictEqual(AUTH.deferredPass(), "pass2a", "the request was dropped, not deferred");
  assert.ok(s.passDeferredReason, "no reason exposed to the operator");
});

test("returning to pass1 is never blocked", () => {
  AUTH.reset("p-1");
  const s = makeSession(); s.currentPass = "pass2a";
  setPass(s, "pass1");
  assert.strictEqual(s.currentPass, "pass1", "the safe direction was blocked");
});

/* ── 2. The three trigger classes, at the choke point ──────────────── */
const TRIGGERS = [
  ["chronology: server spine hydrated", "pass2a"],
  ["chronology: cached spine paint", "pass2a"],
  ["chronology: seed spine from birth facts", "pass2a"],
  ["era navigation: selectEra", "pass2a"],
  ["era navigation: roadmap click", "pass2a"],
  ["era navigation: accordion jump", "pass2a"],
  ["mode button: chronological", "pass2a"],
  ["mode button: thematic", "pass2b"]
];

TRIGGERS.forEach(([label, pass]) => {
  atest("BLOCKED during an active walk — " + label, async () => {
    AUTH.reset("p-1");
    await AUTH.hydrate("p-1", { fetchFn: fetchOK(serverState()) });
    const s = makeSession();
    setPass(s, pass);
    assert.strictEqual(s.currentPass, "pass1",
      label + " promoted while the walk was active");
    assert.ok(/active/.test(s.passBlockedReason || ""),
      "no operator-visible reason");
  });
});

TRIGGERS.forEach(([label, pass]) => {
  atest("ALLOWED once the walk is completed — " + label, async () => {
    AUTH.reset("p-1");
    await AUTH.hydrate("p-1", {
      fetchFn: fetchOK(serverState({ status: "completed", remaining_topics: [] })) });
    const s = makeSession();
    setPass(s, pass);
    assert.strictEqual(s.currentPass, pass, label + " was blocked after completion");
  });
});

/* ── 3. Server semantics, not JavaScript opinion ───────────────────── */
[["pending", true], ["paused", true], ["completed", true], ["active", false]]
  .forEach(([status, shouldAllow]) => {
    atest("server status " + status + " -> promotion " +
          (shouldAllow ? "allowed" : "blocked"), async () => {
      AUTH.reset("p-1");
      await AUTH.hydrate("p-1", { fetchFn: fetchOK(serverState({ status })) });
      const d = AUTH.promotionDecision("pass2a");
      assert.strictEqual(d.allow, shouldAllow,
        "status " + status + " decided the wrong way — plan_turn returns IDLE " +
        "for every status except active, so only active conducts a walk");
    });
  });

atest("a historical narrator with no row is not blocked", async () => {
  AUTH.reset("p-2");
  await AUTH.hydrate("p-2", {
    fetchFn: fetchOK({ person_id: "p-2", enrolled: false }) });
  const s = makeSession();
  setPass(s, "pass2a");
  assert.strictEqual(s.currentPass, "pass2a",
    "an unenrolled narrator was stranded in pass1");
});

/* ── 4. Deferred promotion applies exactly once ────────────────────── */
atest("a deferred promotion is applied once the server allows it", async () => {
  AUTH.reset("p-1");
  const s = makeSession();
  setPass(s, "pass2a");                       // deferred: unresolved
  assert.strictEqual(s.currentPass, "pass1");
  await AUTH.hydrate("p-1", {
    fetchFn: fetchOK(serverState({ status: "completed" })) });
  const applied = AUTH.applyDeferred(p => { s.currentPass = p; });
  assert.strictEqual(applied, "pass2a");
  assert.strictEqual(s.currentPass, "pass2a");
  assert.strictEqual(AUTH.applyDeferred(p => { s.currentPass = "AGAIN"; }), null,
    "the deferred promotion applied twice");
});

atest("a deferred promotion is DROPPED when the walk is active", async () => {
  AUTH.reset("p-1");
  const s = makeSession();
  setPass(s, "pass2a");
  await AUTH.hydrate("p-1", { fetchFn: fetchOK(serverState()) });
  const applied = AUTH.applyDeferred(p => { s.currentPass = p; });
  assert.strictEqual(applied, null, "a blocked promotion was replayed anyway");
  assert.strictEqual(s.currentPass, "pass1");
  assert.strictEqual(AUTH.deferredPass(), null, "the request was not consumed");
});

/* ── 5. Late responses — the corrupting case ───────────────────────── */
atest("a LATE response for narrator A never updates narrator B", async () => {
  AUTH.reset("A");
  const slow = AUTH.hydrate("A", {
    fetchFn: fetchOK(serverState({ person_id: "A", status: "active" }),
                     { delay: 30 }) });
  AUTH.reset("B");                              // operator switches
  await AUTH.hydrate("B", {
    fetchFn: fetchOK(serverState({ person_id: "B", status: "completed" })) });
  await slow;                                   // A's answer lands late
  const snap = AUTH.snapshot();
  assert.strictEqual(snap.personId, "B", "the authority is describing A");
  assert.strictEqual(snap.data && snap.data.person_id, "B",
    "narrator A's walk overwrote narrator B's state");
  assert.strictEqual(AUTH.promotionDecision("pass2a").allow, true,
    "B was blocked by A's active walk");
});

atest("a response whose body names a DIFFERENT narrator is discarded", async () => {
  AUTH.reset("B");
  await AUTH.hydrate("B", {
    fetchFn: fetchOK(serverState({ person_id: "A", status: "active" })) });
  const snap = AUTH.snapshot();
  assert.ok(!snap.data || snap.data.person_id !== "A",
    "a response about narrator A was applied to narrator B");
});

atest("a narrator switch mid-flight leaves the new narrator unresolved-safe",
  async () => {
    AUTH.reset("A");
    const slow = AUTH.hydrate("A", {
      fetchFn: fetchOK(serverState({ person_id: "A" }), { delay: 20 }) });
    AUTH.reset("B");
    const s = makeSession();
    setPass(s, "pass2a");
    assert.strictEqual(s.currentPass, "pass1",
      "B promoted off A's in-flight answer");
    await slow;
    assert.strictEqual(AUTH.snapshot().status, AUTH.UNKNOWN,
      "A's late answer resolved B's authority");
  });

/* ── 6. Failure is not absence ─────────────────────────────────────── */
atest("a failed read is FAILED, not resolved-empty", async () => {
  /* *(This test formerly asserted the opposite — that a failed read
     resolved and PERMITTED promotion, on the reasoning that a network
     blip should not strand a narrator. That reasoning is wrong: a 500
     tells us nothing about whether a walk is running, so treating it as
     "no walk" hands out permission the server never gave. The narrator
     is not stranded either, because FAILED defers and retries.)* */
  AUTH.reset("p-1");
  await AUTH.hydrate("p-1", {
    fetchFn: function () { return Promise.reject(new Error("network down")); } });
  const snap = AUTH.snapshot();
  assert.strictEqual(snap.status, AUTH.FAILED,
    "a failed read was recorded as an answer about the world");
  assert.ok(snap.error, "the failure was not recorded for the operator");
  assert.notStrictEqual(snap.status, AUTH.LOADING, "the UI would wait forever");
});

/* ── 7. Progress, for the operator ─────────────────────────────────── */
atest("progress is derived from the server payload", async () => {
  AUTH.reset("p-1");
  await AUTH.hydrate("p-1", {
    fetchFn: fetchOK(serverState({
      remaining_topics: ["siblings"],
      topic_state: { childhood_home: "addressed", siblings: "unanswered" } })) });
  const p = AUTH.progress();
  assert.strictEqual(p.total, 2);
  assert.strictEqual(p.remaining, 1);
  assert.strictEqual(p.answered, 1);
  assert.strictEqual(p.activeTopic, "childhood_home");
  assert.strictEqual(p.status, "active");
});

test("progress is null before the server answers", () => {
  AUTH.reset("p-1");
  assert.strictEqual(AUTH.progress(), null);
});

/* ── 8. Pause / resume, versioned ──────────────────────────────────── */
atest("pause sends the version the client last READ", async () => {
  AUTH.reset("p-1");
  await AUTH.hydrate("p-1", { fetchFn: fetchOK(serverState({ version: 7 })) });
  let sent = null;
  await AUTH.setPaused("pause", {
    fetchFn: function (url, init) {
      sent = JSON.parse(init.body);
      return Promise.resolve({ ok: true, status: 200,
        json: () => Promise.resolve(serverState({ status: "paused", version: 8 })) });
    } });
  assert.strictEqual(sent.expected_version, 7, "a blind write, not a versioned one");
  assert.strictEqual(sent.action, "pause");
  assert.strictEqual(AUTH.snapshot().data.status, "paused");
});

atest("a 409 conflict re-reads instead of retrying blindly", async () => {
  AUTH.reset("p-1");
  await AUTH.hydrate("p-1", { fetchFn: fetchOK(serverState({ version: 7 })) });
  let calls = 0;
  const res = await AUTH.setPaused("pause", {
    fetchFn: function (url, init) {
      calls++;
      if (init && init.method === "PATCH") {
        return Promise.resolve({ ok: false, status: 409,
          json: () => Promise.resolve({ detail: { error: "version_conflict" } }) });
      }
      return Promise.resolve({ ok: true, status: 200,
        json: () => Promise.resolve(serverState({ version: 9, status: "active" })) });
    } });
  assert.strictEqual(res.ok, false);
  assert.strictEqual(res.conflict, true, "the conflict was swallowed");
  assert.strictEqual(AUTH.snapshot().data.version, 9, "the client kept a stale version");
});

atest("pausing a walk UNBLOCKS promotion, per server semantics", async () => {
  AUTH.reset("p-1");
  await AUTH.hydrate("p-1", { fetchFn: fetchOK(serverState()) });
  assert.strictEqual(AUTH.promotionDecision("pass2a").allow, false);
  await AUTH.setPaused("pause", {
    fetchFn: () => Promise.resolve({ ok: true, status: 200,
      json: () => Promise.resolve(serverState({ status: "paused" })) }) });
  assert.strictEqual(AUTH.promotionDecision("pass2a").allow, true,
    "a paused walk still blocked promotion — the server conducts nothing " +
    "while paused, so the ordinary pass engine owns the turn");
});

/* ── 9. Non-vacuity ────────────────────────────────────────────────── */
atest("the active fixture really does block, so the ALLOW cases mean something",
  async () => {
    AUTH.reset("p-1");
    await AUTH.hydrate("p-1", { fetchFn: fetchOK(serverState()) });
    assert.strictEqual(AUTH.promotionDecision("pass2a").allow, false);
    assert.strictEqual(AUTH.promotionDecision("pass2b").allow, false);
  });

/* ── 10. The corrections of 2026-08-29 ─────────────────────────────── */

atest("a NETWORK FAILURE does not authorize promotion", async () => {
  AUTH.reset("p-1");
  await AUTH.hydrate("p-1", {
    fetchFn: () => Promise.reject(new Error("network down")) });
  assert.strictEqual(AUTH.snapshot().status, AUTH.FAILED,
    "a failed read was recorded as resolved");
  const s = makeSession();
  setPass(s, "pass2a");
  assert.strictEqual(s.currentPass, "pass1",
    "a network failure became permission to promote past a possibly-active walk");
  assert.strictEqual(AUTH.deferredPass(), "pass2a",
    "the request was dropped rather than held for retry");
});

[500, 503, 404].forEach(code => {
  atest("HTTP " + code + " does not authorize promotion", async () => {
    AUTH.reset("p-1");
    await AUTH.hydrate("p-1", {
      fetchFn: () => Promise.resolve({ ok: false, status: code,
                                       json: () => Promise.resolve(null) }) });
    assert.strictEqual(AUTH.snapshot().status, AUTH.FAILED);
    const d = AUTH.promotionDecision("pass2a");
    assert.strictEqual(d.allow, false, "HTTP " + code + " allowed a promotion");
    assert.strictEqual(d.defer, true, "no retry path was offered");
    assert.ok(d.retry, "the operator is not told this is retryable");
  });
});

atest("a successful RETRY after a failure honours the deferred promotion",
  async () => {
    AUTH.reset("p-1");
    await AUTH.hydrate("p-1", {
      fetchFn: () => Promise.reject(new Error("network down")) });
    const s = makeSession();
    setPass(s, "pass2a");
    assert.strictEqual(s.currentPass, "pass1");
    await AUTH.hydrate("p-1", {
      fetchFn: fetchOK(serverState({ status: "completed" })) });
    AUTH.applyDeferred(pass => { s.currentPass = pass; });
    assert.strictEqual(s.currentPass, "pass2a", "the retry did not honour the request");
  });

atest("a LATE 409 for narrator A never rehydrates over narrator B", async () => {
  AUTH.reset("A");
  await AUTH.hydrate("A", { fetchFn: fetchOK(serverState({ person_id: "A" })) });
  let hydrateCalls = 0;
  const patch = AUTH.setPaused("pause", {
    fetchFn: function (url, init) {
      if (init && init.method === "PATCH") {
        return new Promise(r => setTimeout(() => r({
          ok: false, status: 409,
          json: () => Promise.resolve({ detail: { error: "version_conflict" } })
        }), 25));
      }
      hydrateCalls++;
      return Promise.resolve({ ok: true, status: 200,
        json: () => Promise.resolve(serverState({ person_id: "A" })) });
    } });
  AUTH.reset("B");                                   // operator switches
  await AUTH.hydrate("B", {
    fetchFn: fetchOK(serverState({ person_id: "B", status: "completed" })) });
  const res = await patch;                           // A's 409 lands late
  assert.strictEqual(res.stale, true, "a stale conflict was processed as current");
  assert.strictEqual(hydrateCalls, 0,
    "the 409 handler re-read narrator A while the operator was on B");
  const snap = AUTH.snapshot();
  assert.strictEqual(snap.personId, "B", "A's conflict overwrote B's authority");
  assert.strictEqual(snap.data.person_id, "B");
});

atest("a LATE PATCH SUCCESS for narrator A never overwrites narrator B",
  async () => {
    AUTH.reset("A");
    await AUTH.hydrate("A", { fetchFn: fetchOK(serverState({ person_id: "A" })) });
    const patch = AUTH.setPaused("pause", {
      fetchFn: () => new Promise(r => setTimeout(() => r({
        ok: true, status: 200,
        json: () => Promise.resolve(serverState({ person_id: "A", status: "paused" }))
      }), 25)) });
    AUTH.reset("B");
    await AUTH.hydrate("B", {
      fetchFn: fetchOK(serverState({ person_id: "B", status: "active" })) });
    const res = await patch;
    assert.strictEqual(res.ok, false, "a stale PATCH success was applied");
    assert.strictEqual(AUTH.snapshot().data.person_id, "B");
    assert.strictEqual(AUTH.snapshot().data.status, "active",
      "A's pause landed on B");
  });

atest("A -> B -> A generation drift: the FIRST A response is still discarded",
  async () => {
    AUTH.reset("A");
    const first = AUTH.hydrate("A", {
      fetchFn: fetchOK(serverState({ person_id: "A", status: "completed" }),
                       { delay: 30 }) });
    AUTH.reset("B");
    AUTH.reset("A");                       // back to A — a NEW generation
    await AUTH.hydrate("A", {
      fetchFn: fetchOK(serverState({ person_id: "A", status: "active" })) });
    await first;                           // the stale A response lands
    assert.strictEqual(AUTH.snapshot().data.status, "active",
      "a stale response for the SAME narrator overwrote the current read — " +
      "person id alone cannot catch this, only the generation can");
  });

atest("a REAL resume() demotes an already-promoted pass", async () => {
  /* *(The previous version of this test never called setPaused. It
     hydrated an active state by hand and called reconcile by hand, so it
     proved the helper worked while the production resume path did not
     call it at all. This drives the actual pause/resume function.)* */
  AUTH.reset("p-1");
  await AUTH.hydrate("p-1", { fetchFn: fetchOK(serverState({ status: "paused" })) });
  const s = makeSession();
  setPass(s, "pass2a");
  assert.strictEqual(s.currentPass, "pass2a", "paused should have allowed it");

  // The real resume: PATCH returns the row now ACTIVE.
  const res = await AUTH.setPaused("resume", {
    fetchFn: () => Promise.resolve({ ok: true, status: 200,
      json: () => Promise.resolve(serverState({ status: "active" })) }) });
  assert.strictEqual(res.ok, true, "resume did not succeed");

  // What the button handler does next, and must do.
  const r = AUTH.reconcile(s);
  assert.strictEqual(r.changed, true, "the stale promotion was left standing");
  assert.strictEqual(s.currentPass, "pass1",
    "the browser stayed in pass2a while the server conducted a walk");
  assert.ok(/active/.test(s.passBlockedReason || ""));
});

atest("reconcile does NOT demote when the server permits the pass", async () => {
  AUTH.reset("p-1");
  await AUTH.hydrate("p-1", { fetchFn: fetchOK(serverState({ status: "completed" })) });
  const s = makeSession(); s.currentPass = "pass2a";
  assert.strictEqual(AUTH.reconcile(s).changed, false);
  assert.strictEqual(s.currentPass, "pass2a", "a legitimate pass was demoted");
});

atest("a FAILED read DEMOTES an already-promoted pass", async () => {
  AUTH.reset("p-1");
  await AUTH.hydrate("p-1", { fetchFn: fetchOK(serverState({ status: "completed" })) });
  const s = makeSession();
  setPass(s, "pass2a");
  assert.strictEqual(s.currentPass, "pass2a");
  await AUTH.hydrate("p-1", {
    fetchFn: () => Promise.reject(new Error("network down")) });
  const r = AUTH.reconcile(s);
  assert.strictEqual(r.changed, true,
    "a failed read left an already-promoted pass standing — 'the pass stays " +
    "safe' was only true for a session that began at pass1");
  assert.strictEqual(s.currentPass, "pass1");
  assert.strictEqual(AUTH.deferredPass(), "pass2a",
    "the operator's position was lost rather than held for retry");
});

atest("a demoted-on-failure pass is RESTORED by a successful retry", async () => {
  AUTH.reset("p-1");
  await AUTH.hydrate("p-1", { fetchFn: fetchOK(serverState({ status: "completed" })) });
  const s = makeSession();
  setPass(s, "pass2a");
  await AUTH.hydrate("p-1", {
    fetchFn: () => Promise.reject(new Error("network down")) });
  AUTH.reconcile(s);
  assert.strictEqual(s.currentPass, "pass1");
  await AUTH.hydrate("p-1", { fetchFn: fetchOK(serverState({ status: "completed" })) });
  AUTH.applyDeferred(pass => { s.currentPass = pass; });
  assert.strictEqual(s.currentPass, "pass2a", "the retry did not restore the pass");
});

atest("RESET demotes immediately, before any hydrate resolves", async () => {
  AUTH.reset("A");
  await AUTH.hydrate("A", {
    fetchFn: fetchOK(serverState({ person_id: "A", status: "completed" })) });
  const s = makeSession();
  setPass(s, "pass2a");
  assert.strictEqual(s.currentPass, "pass2a",
    "the fixture did not resolve — check person_id matches the hydrate target");
  AUTH.reset("B");                       // switch — nothing awaited
  const r = AUTH.reconcile(s);
  assert.strictEqual(r.changed, true,
    "narrator A's pass2a carried into narrator B's session");
  assert.strictEqual(s.currentPass, "pass1");
});

atest("RESET clears the previous narrator's progress immediately", async () => {
  AUTH.reset("A");
  await AUTH.hydrate("A", {
    fetchFn: fetchOK(serverState({ person_id: "A", status: "active" })) });
  assert.ok(AUTH.progress(), "narrator A has no progress to clear");
  AUTH.reset("B");
  assert.strictEqual(AUTH.progress(), null,
    "narrator A's progress survived the switch and would render under B's name");
  assert.strictEqual(AUTH.snapshot().personId, "B");
});

atest("a PATCH NETWORK REJECTION resolves instead of throwing", async () => {
  AUTH.reset("p-1");
  await AUTH.hydrate("p-1", { fetchFn: fetchOK(serverState({ status: "paused" })) });
  let threw = false;
  const res = await AUTH.setPaused("resume", {
    fetchFn: () => Promise.reject(new Error("connection reset"))
  }).catch(() => { threw = true; return null; });
  assert.strictEqual(threw, false,
    "setPaused rejected — the button handler's .then never runs, so " +
    "pause/resume stays disabled and the browser logs an unhandled rejection");
  assert.ok(res, "no result to render");
  assert.strictEqual(res.ok, false);
  assert.ok(/connection reset/.test(res.reason || ""),
    "the operator is not told why it failed");
});

atest("a PATCH non-OK status also resolves with a reason", async () => {
  AUTH.reset("p-1");
  await AUTH.hydrate("p-1", { fetchFn: fetchOK(serverState({ status: "paused" })) });
  const res = await AUTH.setPaused("resume", {
    fetchFn: () => Promise.resolve({ ok: false, status: 500,
                                     json: () => Promise.resolve({}) }) });
  assert.strictEqual(res.ok, false);
  assert.ok(res.reason, "no reason for the operator");
});

/* ── 11. The production choke point really delegates ────────────────── */
const fs = require("fs");
test("state.js::setPass delegates to applyPass and keeps no second policy", () => {
  const src = fs.readFileSync(
    path.join(__dirname, "..", "ui", "js", "state.js"), "utf8");
  const body = src.slice(src.indexOf("function setPass(p)"),
                         src.indexOf("function setPass(p)") + 900);
  assert.ok(/auth\.applyPass\(/.test(body),
    "state.js no longer delegates to the shared policy");
  assert.ok(!/promotionDecision\(/.test(body),
    "state.js has grown its own copy of the promotion policy again — " +
    "that is the drift this delegation exists to prevent");
});

test("applyPass is exported, so the delegation target exists", () => {
  assert.strictEqual(typeof AUTH.applyPass, "function");
  assert.strictEqual(typeof AUTH.reconcile, "function");
});

runAll();
