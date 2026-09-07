/* operator_guard_lab_card_domtest.js — the Operator card, by RENDERING it.
 *
 * WO-LORI-ARCHIVE-TO-MEMOIR-02 Block A.
 *
 * The API suite proves the server decides eligibility and names the
 * configuration. This proves the OPERATOR sees that verdict, and — the
 * property the whole card exists for — that it never computes one of
 * its own.
 *
 * argv[2] is a real `GET /state` response written by
 * tests/test_operator_guard_lab_card.py. A hand-built payload would
 * supply the shape under test.
 *
 *   node scripts/ui/operator_guard_lab_card_domtest.js <state.json>
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..", "..");
const PAYLOAD_PATH = process.argv[2];
if (!PAYLOAD_PATH) {
  console.error("usage: node operator_guard_lab_card_domtest.js <state.json>");
  process.exit(2);
}
const REAL_STATE = JSON.parse(fs.readFileSync(PAYLOAD_PATH, "utf8"));

const failures = [];
let checks = 0;
function ok(cond, label, detail) {
  checks++;
  if (!cond) failures.push(label + (detail ? "  — " + detail : ""));
}
function eq(a, b, label) {
  ok(a === b, label, "expected " + JSON.stringify(b) + ", got " + JSON.stringify(a));
}

function makeDocument() {
  function node(tag) {
    return {
      tagName: String(tag).toUpperCase(), nodeType: 1, className: "",
      attributes: {}, children: [], _listeners: {},
      appendChild(c) { this.children.push(c); return c; },
      setAttribute(k, v) { this.attributes[k] = String(v); },
      getAttribute(k) { return this.attributes[k]; },
      addEventListener(e, f) { (this._listeners[e] = this._listeners[e] || []).push(f); },
      click() { (this._listeners.click || []).forEach(f => f()); },
      matches() { return false; },
      scrollIntoView() {},
      showPopover() { this._shown = true; },
      set innerHTML(v) { if (v === "") this.children = []; },
      get innerHTML() { return ""; },
    };
  }
  const mounts = {};
  return {
    readyState: "complete",
    createElement: node,
    createTextNode(t) { return { nodeType: 3, text: String(t), children: [] }; },
    getElementById(id) { return mounts[id] || null; },
    addEventListener() {},
    _mount(id) { const n = node("div"); mounts[id] = n; return n; },
  };
}

function textOf(n) {
  if (!n) return "";
  if (n.nodeType === 3) return n.text;
  return (n.children || []).map(textOf).join(" ");
}
function walk(n, out) {
  out = out || [];
  if (!n || n.nodeType !== 1) return out;
  out.push(n);
  (n.children || []).forEach(c => walk(c, out));
  return out;
}
function byClass(root, cls) {
  return walk(root).filter(n =>
    String(n.className || "").split(/\s+/).indexOf(cls) !== -1);
}
function buttonWith(root, label) {
  return walk(root).find(n => n.tagName === "BUTTON" && textOf(n).trim() === label);
}

function load(fetchImpl, personId) {
  const document = makeDocument();
  const mount = document._mount("lvOperatorGuardLabCard");
  document._mount("lv10dBugPanel");
  document._mount("lv10dBpGuardLab");
  const sandbox = {
    console: { log() {}, warn() {}, error() {} },
    document, fetch: fetchImpl,
    state: { person_id: personId },
    JSON, String, Object, Array, Math, Date, Promise, encodeURIComponent,
    setTimeout, clearTimeout,
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(
    fs.readFileSync(path.join(ROOT, "ui", "js", "operator-guard-lab-card.js"), "utf8"),
    sandbox, { filename: "operator-guard-lab-card.js" });
  return { sandbox, mount };
}

function jsonResponse(status, body) {
  return Promise.resolve({ status, json: () => Promise.resolve(body) });
}
function recorder(responder) {
  const calls = [];
  const fn = (url, options) => {
    const entry = { url, options: options || {} };
    try { entry.body = options && options.body ? JSON.parse(options.body) : null; }
    catch (e) { entry.body = null; }
    calls.push(entry);
    return responder(entry, calls.length);
  };
  fn.calls = calls;
  return fn;
}
const tick = () => new Promise(r => setTimeout(r, 0));

/* Build the two narrator verdicts from the REAL payload's own shape,
   changing only the fields the server itself varies. */
function withNarrator(base, narrator) {
  const copy = JSON.parse(JSON.stringify(base));
  copy.current_narrator = narrator;
  return copy;
}
const ELIGIBLE = {
  requested_id: "p-test", exists: true, display_name: "Guard Lab Test Narrator",
  testing_only: true, can_receive_experiment: true, reason: "eligible",
  message: "Guard Lab Test Narrator will receive the selected configuration on their next turn.",
};
const ORDINARY = {
  requested_id: "p-real", exists: true, display_name: "Ordinary Narrator",
  testing_only: false, can_receive_experiment: false, reason: "not_testing_only",
  message: "Ordinary Narrator is an ordinary narrator. Experimental selections will NOT affect this session — Lori runs canonically for them whatever is selected here.",
};

async function main() {
  /* ── 1. the selected narrator's id goes to the SERVER ─────────────── */
  {
    const fetchFn = recorder(() => jsonResponse(200, withNarrator(REAL_STATE, ELIGIBLE)));
    const app = load(fetchFn, "p-test");
    await tick(); await tick();
    ok(fetchFn.calls.length >= 1, "the card reads /state on load");
    ok(/narrator_id=p-test/.test(fetchFn.calls[0].url),
       "the selected narrator id is sent to the server", fetchFn.calls[0].url);
  }

  /* ── 2. an ORDINARY narrator is warned about, in the server's words ── */
  {
    const payload = withNarrator(REAL_STATE, ORDINARY);
    const app = load(recorder(() => jsonResponse(200, payload)), "p-real");
    await tick(); await tick();
    app.sandbox.lvOperatorGuardLabRenderInto(app.mount, app.sandbox.lvOperatorGuardLabState());
    const text = textOf(app.mount);
    ok(text.indexOf("Not eligible") !== -1,
       "an ordinary narrator reads as Not eligible");
    ok(byClass(app.mount, "oglc-verdict-warn").length === 1,
       "the warning verdict is rendered");
    ok(text.indexOf("will NOT affect this session") !== -1,
       "the operator is told plainly that the selection will not reach them");
    ok(text.indexOf("Ordinary Narrator") !== -1,
       "the SERVER's display name is shown");
  }

  /* ── 3. an eligible narrator reads as eligible ────────────────────── */
  {
    const payload = withNarrator(REAL_STATE, ELIGIBLE);
    const app = load(recorder(() => jsonResponse(200, payload)), "p-test");
    await tick(); await tick();
    app.sandbox.lvOperatorGuardLabRenderInto(app.mount, app.sandbox.lvOperatorGuardLabState());
    const text = textOf(app.mount);
    ok(text.indexOf("Eligible") !== -1, "an eligible narrator reads as Eligible");
    ok(byClass(app.mount, "oglc-verdict-ok").length === 1,
       "the ok verdict is rendered");
  }

  /* ── 4. the card NEVER decides eligibility itself ─────────────────── */
  {
    // The server says NOT eligible for a narrator that IS testing-only
    // and IS in the eligible list — an environmental condition failed.
    // A card doing its own list lookup would contradict it.
    const contradicting = withNarrator(REAL_STATE, {
      requested_id: "p-test", exists: true, display_name: "Guard Lab Test Narrator",
      testing_only: true, can_receive_experiment: false, reason: "trace_not_recording",
      message: "This narrator is eligible and an evaluation is armed, but the response trace is not recording.",
    });
    // The narrator IS in the eligible list and IS testing-only. Only the
    // server knows an environmental condition failed. A card doing its
    // own lookup would print Eligible here and contradict it.
    contradicting.gate = Object.assign({}, contradicting.gate, {
      testing_only_narrators: [{ id: "p-test", display_name: "Guard Lab Test Narrator" }],
      experiment_armed: true, trace_recording: false, can_apply_to_a_turn: false,
    });
    const app = load(recorder(() => jsonResponse(200, contradicting)), "p-test");
    await tick(); await tick();
    app.sandbox.lvOperatorGuardLabRenderInto(app.mount, app.sandbox.lvOperatorGuardLabState());
    const text = textOf(app.mount);
    ok(text.indexOf("Not eligible") !== -1,
       "the card renders the SERVER's verdict even when the narrator is "
       + "testing-only and present in the eligible list");
    ok(text.indexOf("not recording") !== -1, "and the server's reason with it");
  }

  /* ── 5. the configuration label is the server's, not computed ─────── */
  {
    // The payload's rows say every switchable authority is running,
    // while the server labels it "Lean". A card computing the label
    // from the rows would print Defaults.
    const mislabelled = JSON.parse(JSON.stringify(withNarrator(REAL_STATE, ELIGIBLE)));
    // Every row reads like untouched defaults: no override anywhere, and
    // every switchable authority effective. Any label computed from the
    // rows is "Defaults". The server says Lean.
    mislabelled.authorities.forEach(a => {
      if (a.switchable) { a.operator_override = null; a.effective = true; }
    });
    mislabelled.configuration = { id: "lean", label: "Lean (All Switchable Off)",
                                  detail: "server says lean" };
    const app = load(recorder(() => jsonResponse(200, mislabelled)), "p-test");
    await tick(); await tick();
    app.sandbox.lvOperatorGuardLabRenderInto(app.mount, app.sandbox.lvOperatorGuardLabState());
    ok(textOf(app.mount).indexOf("Lean (All Switchable Off)") !== -1,
       "the configuration label comes from the server, not from the rows");
    ok(byClass(app.mount, "oglc-chip-lean").length === 1,
       "and the chip follows the server's classification");
  }

  /* ── 6. the 43-row table is NOT duplicated here ───────────────────── */
  {
    const app = load(recorder(() => jsonResponse(200, withNarrator(REAL_STATE, ELIGIBLE))), "p-test");
    await tick(); await tick();
    app.sandbox.lvOperatorGuardLabRenderInto(app.mount, app.sandbox.lvOperatorGuardLabState());
    const text = textOf(app.mount);
    const leaked = (REAL_STATE.authorities || []).filter(a =>
      text.indexOf(a.display) !== -1);
    eq(leaked.length, 0,
       "no authority row is rendered on the Operator card — the 43-row "
       + "table stays in the Bug Panel",
       leaked.map(a => a.id).join(","));
  }

  /* ── 7. one action, ONE request, carrying the observed revision ───── */
  {
    const fetchFn = recorder(() => jsonResponse(200, withNarrator(REAL_STATE, ELIGIBLE)));
    const app = load(fetchFn, "p-test");
    await tick(); await tick();
    app.sandbox.lvOperatorGuardLabRenderInto(app.mount, app.sandbox.lvOperatorGuardLabState());
    const before = fetchFn.calls.length;
    buttonWith(app.mount, "All Switchable Off").click();
    await tick(); await tick();
    const issued = fetchFn.calls.slice(before);
    eq(issued.length, 1, "All Switchable Off is ONE request from the card too");
    ok(/\/all-switchable-off$/.test(issued[0].url), "the atomic preset route",
       issued[0].url);
    eq(issued[0].body.expected_revision, REAL_STATE.revision,
       "it carries the revision the operator was looking at");
    eq(issued[0].body.narrator_id, "p-test",
       "and names the narrator the verdict should answer for");
  }

  /* ── 8. a 409 is adopted, not argued with ─────────────────────────── */
  {
    const live = JSON.parse(JSON.stringify(withNarrator(REAL_STATE, ORDINARY)));
    live.revision = REAL_STATE.revision + 7;
    live.configuration = { id: "custom", label: "Custom", detail: "moved" };
    let n = 0;
    const fetchFn = recorder(() => {
      n += 1;
      if (n === 1) return jsonResponse(200, withNarrator(REAL_STATE, ELIGIBLE));
      return jsonResponse(409, { detail: {
        error: "stale_revision", message: "changed underneath this request",
        expected_revision: REAL_STATE.revision, current_revision: live.revision,
        current: live } });
    });
    const app = load(fetchFn, "p-test");
    await tick(); await tick();
    app.sandbox.lvOperatorGuardLabRenderInto(app.mount, app.sandbox.lvOperatorGuardLabState());
    buttonWith(app.mount, "Restore Defaults").click();
    await tick(); await tick();
    eq(app.sandbox.lvOperatorGuardLabState().data.revision, live.revision,
       "the live configuration attached to the 409 is adopted");
    ok(byClass(app.mount, "oglc-conflict").length === 1,
       "the refusal is shown, not swallowed");
    ok(textOf(app.mount).indexOf("Custom") !== -1,
       "and the corrected configuration is what the operator now sees");
  }

  /* ── 9. OUT-OF-ORDER NARRATOR RESPONSES ──────────────────────────── */
  {
    // The defect found in review of the pushed Block A. A slow answer
    // about narrator A must never repaint a card that now shows B.
    const app = (() => {
      let personId = "p-test";
      const resolvers = [];
      const fetchFn = recorder((entry) => new Promise(resolve => {
        resolvers.push({ url: entry.url, resolve });
      }));
      const document = makeDocument();
      const mount = document._mount("lvOperatorGuardLabCard");
      document._mount("lv10dBugPanel"); document._mount("lv10dBpGuardLab");
      const sandbox = {
        console: { log() {}, warn() {}, error() {} },
        document, fetch: fetchFn,
        get state() { return { person_id: personId }; },
        JSON, String, Object, Array, Math, Date, Promise, encodeURIComponent,
        setTimeout, clearTimeout,
      };
      sandbox.window = sandbox; sandbox.globalThis = sandbox;
      vm.createContext(sandbox);
      vm.runInContext(fs.readFileSync(
        path.join(ROOT, "ui", "js", "operator-guard-lab-card.js"), "utf8"),
        sandbox, { filename: "operator-guard-lab-card.js" });
      return { sandbox, mount, resolvers, fetchFn,
               setPerson: (v) => { personId = v; } };
    })();

    await tick();
    ok(app.resolvers.length === 1, "request A is in flight");
    ok(/narrator_id=p-test/.test(app.resolvers[0].url), "and it names A");

    // The operator switches to B while A is still outstanding.
    app.setPerson("p-real");
    app.sandbox.lvOperatorGuardLabOnNarratorSwitch("p-real");
    await tick();
    ok(app.resolvers.length === 2, "the switch issues a request for B");
    ok(/narrator_id=p-real/.test(app.resolvers[1].url), "naming B");

    // B answers FIRST, then A arrives late.
    app.resolvers[1].resolve({ status: 200,
      json: () => Promise.resolve(withNarrator(REAL_STATE, ORDINARY)) });
    await tick(); await tick();
    app.resolvers[0].resolve({ status: 200,
      json: () => Promise.resolve(withNarrator(REAL_STATE, ELIGIBLE)) });
    await tick(); await tick();

    const st = app.sandbox.lvOperatorGuardLabState();
    eq(st.data.current_narrator.requested_id, "p-real",
       "the LATE answer about A did not replace B — this is the defect");
    st.collapsed = false;
    app.sandbox.lvOperatorGuardLabRenderInto(app.mount, st);
    const text = textOf(app.mount);
    ok(text.indexOf("Ordinary Narrator") !== -1,
       "the card still shows the narrator who is selected", text);
    ok(text.indexOf("Guard Lab Test Narrator") === -1,
       "and never the one who is not", text);
  }

  /* ── 10. a stale ERROR does not overwrite newer state either ──────── */
  {
    let personId = "p-test";
    const resolvers = [];
    const fetchFn = recorder(() => new Promise((resolve, reject) => {
      resolvers.push({ resolve, reject });
    }));
    const document = makeDocument();
    const mount = document._mount("lvOperatorGuardLabCard");
    const sandbox = {
      console: { log() {}, warn() {}, error() {} },
      document, fetch: fetchFn,
      get state() { return { person_id: personId }; },
      JSON, String, Object, Array, Math, Date, Promise, encodeURIComponent,
      setTimeout, clearTimeout,
    };
    sandbox.window = sandbox; sandbox.globalThis = sandbox;
    vm.createContext(sandbox);
    vm.runInContext(fs.readFileSync(
      path.join(ROOT, "ui", "js", "operator-guard-lab-card.js"), "utf8"),
      sandbox, { filename: "operator-guard-lab-card.js" });
    await tick();

    personId = "p-real";
    sandbox.lvOperatorGuardLabOnNarratorSwitch("p-real");
    await tick();
    resolvers[1].resolve({ status: 200,
      json: () => Promise.resolve(withNarrator(REAL_STATE, ORDINARY)) });
    await tick(); await tick();
    resolvers[0].reject(new Error("A timed out"));
    await tick(); await tick();

    const st = sandbox.lvOperatorGuardLabState();
    ok(!st.error,
       "narrator A's timeout is not shown on narrator B's card",
       String(st.error));
    eq(st.data.current_narrator.requested_id, "p-real",
       "and B's state survives it");
  }

  /* ── 11. an off backend renders a placeholder ─────────────────────── */
  {
    const app = load(recorder(() => jsonResponse(404, null)), "p-test");
    await tick(); await tick();
    app.sandbox.lvOperatorGuardLabRenderInto(app.mount, app.sandbox.lvOperatorGuardLabState());
    ok(textOf(app.mount).indexOf("HORNELORE_OPERATOR_GUARD_LAB") !== -1,
       "an off backend tells the operator how to turn it on");
  }

  if (failures.length) {
    console.error(failures.length + " of " + checks + " checks FAILED:");
    failures.forEach(f => console.error("  ✗ " + f));
    process.exit(1);
  }
  console.log(checks + " checks passed");
}

main().catch(e => {
  console.error("harness error: " + ((e && e.stack) || e));
  process.exit(2);
});
