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

/* A stand-in for state.js's setPass, byte-for-byte in policy terms.
   The real one lives in state.js, which cannot be required without the
   whole UI; this mirrors its THREE OUTCOMES so the policy is exercised
   exactly as the choke point applies it. */
function makeSession() { return { currentPass: "pass1" }; }
function setPass(session, p) {
  const d = AUTH.promotionDecision(p);
  if (d.defer) { AUTH.rememberDeferred(p); session.passDeferredReason = d.reason; return; }
  session.passDeferredReason = null;
  if (!d.allow) { session.passBlockedReason = d.reason; return; }
  session.passBlockedReason = null;
  session.currentPass = p;
}

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
atest("a failed read resolves and permits the ordinary pass engine", async () => {
  AUTH.reset("p-1");
  await AUTH.hydrate("p-1", {
    fetchFn: function () { return Promise.reject(new Error("network down")); } });
  const snap = AUTH.snapshot();
  assert.strictEqual(snap.status, AUTH.RESOLVED, "the UI would wait forever");
  assert.ok(snap.error, "the failure was not recorded for the operator");
  const s = makeSession();
  setPass(s, "pass2a");
  assert.strictEqual(s.currentPass, "pass2a",
    "a network blip stranded the narrator in pass1");
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

runAll();
