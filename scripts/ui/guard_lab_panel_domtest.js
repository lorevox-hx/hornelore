/* guard_lab_panel_domtest.js — the Guard Lab panel, tested by RENDERING it.
 *
 * WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01 Continuation A, section R.
 *
 * WHY THIS EXISTS. The API suite proves the server tells the truth about
 * 43 authorities. It stops one consumer short of proving the OPERATOR
 * sees that truth, and this lane has already paid for that gap twice:
 * `renderExtraction` had to be exported because a source-string check
 * could not tell whether the operator view rendered the values, and
 * `disabled: undefined` left every review button permanently dead while
 * the buttons, labels and handlers all read correctly in the source.
 *
 * So the assertions here are about a rendered tree and about the
 * requests a click actually issues.
 *
 * THE PAYLOAD IS A REAL SERVER RESPONSE. argv[2] is a JSON file written
 * by `tests/test_guard_lab_panel.py` from a live call to
 * `GET /api/operator/guard-lab/state`. A hand-built fixture would supply
 * the very shape under test — the doctrine failure CLAUDE.md records
 * nine instances of.
 *
 *   node scripts/ui/guard_lab_panel_domtest.js <state.json>
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..", "..");
const PAYLOAD_PATH = process.argv[2];
if (!PAYLOAD_PATH) {
  console.error("usage: node guard_lab_panel_domtest.js <state.json>");
  process.exit(2);
}
const REAL_STATE = JSON.parse(fs.readFileSync(PAYLOAD_PATH, "utf8"));

const failures = [];
let checks = 0;
function ok(cond, label, detail) {
  checks++;
  if (!cond) failures.push(label + (detail ? "  — " + detail : ""));
}
function eq(actual, expected, label) {
  ok(actual === expected, label,
     "expected " + JSON.stringify(expected) + ", got " + JSON.stringify(actual));
}

/* ── a DOM small enough to read, large enough to be honest ─────────────
   Only what the shipped module touches. It is a real tree with real
   listeners, so a click goes through the module's own handler rather
   than through a stub of it. */
function makeDocument() {
  function node(tag) {
    return {
      tagName: String(tag).toUpperCase(),
      nodeType: 1,
      className: "",
      attributes: {},
      children: [],
      _listeners: {},
      appendChild(c) { this.children.push(c); return c; },
      setAttribute(k, v) { this.attributes[k] = String(v); },
      getAttribute(k) { return this.attributes[k]; },
      addEventListener(evt, fn) {
        (this._listeners[evt] = this._listeners[evt] || []).push(fn);
      },
      click() { (this._listeners.click || []).forEach(function (f) { f(); }); },
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
  (n.children || []).forEach(function (c) { walk(c, out); });
  return out;
}
function byClass(root, cls) {
  return walk(root).filter(function (n) {
    return String(n.className || "").split(/\s+/).indexOf(cls) !== -1;
  });
}
function buttonsWithText(root, label) {
  return walk(root).filter(function (n) {
    return n.tagName === "BUTTON" && textOf(n).trim() === label;
  });
}

/* ── load the SHIPPED module ────────────────────────────────────────── */
function load(fetchImpl) {
  const document = makeDocument();
  const mount = document._mount("lv10dBpGuardLab");
  const sandbox = {
    console: { log() {}, warn() {}, error() {} },
    document,
    fetch: fetchImpl,
    JSON, String, Object, Array, Math, Date, Promise, encodeURIComponent,
    setTimeout, clearTimeout,
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(
    fs.readFileSync(path.join(ROOT, "ui", "js", "bug-panel-guard-lab.js"), "utf8"),
    sandbox, { filename: "bug-panel-guard-lab.js" });
  return { sandbox: sandbox, mount: mount };
}

function jsonResponse(status, body) {
  return Promise.resolve({
    status: status,
    json: function () { return Promise.resolve(body); },
  });
}

/* A fetch that RECORDS. The count is the point: `All Switchable Off`
   must be one request, not thirty-seven. */
function recorder(responder) {
  const calls = [];
  const fn = function (url, options) {
    const entry = { url: url, options: options || {} };
    try {
      entry.body = options && options.body ? JSON.parse(options.body) : null;
    } catch (e) { entry.body = null; }
    calls.push(entry);
    return responder(entry, calls.length);
  };
  fn.calls = calls;
  return fn;
}

const tick = () => new Promise(function (r) { setTimeout(r, 0); });

async function main() {
  /* ── 1. the real payload renders every authority, truthfully ─────── */
  {
    const fetchFn = recorder(function () { return jsonResponse(200, REAL_STATE); });
    const app = load(fetchFn);
    await tick(); await tick();
    app.sandbox.lvGuardLabState().collapsed = false;
    app.sandbox.lvGuardLabRenderInto(app.mount, app.sandbox.lvGuardLabState());

    const rendered = textOf(app.mount);
    const missing = REAL_STATE.authorities.filter(function (a) {
      return rendered.indexOf(a.display || a.name) === -1;
    });
    eq(missing.length, 0, "every registered authority is rendered",
       missing.map(function (a) { return a.id; }).join(","));

    eq(byClass(app.mount, "gl-row").length, REAL_STATE.authorities.length,
       "one row per authority");

    // The EFFECTIVE state must be on screen, not inferred by the reader
    // from a checkbox that shows an override.
    const running = REAL_STATE.authorities.filter(function (a) { return a.effective; });
    const shown = byClass(app.mount, "gl-eff").filter(function (n) {
      return textOf(n).trim() === "RUNNING";
    });
    eq(shown.length, running.length,
       "RUNNING is rendered for exactly the effective authorities");

    // And the reason that decided the row.
    ok(byClass(app.mount, "gl-reason").length === REAL_STATE.authorities.length,
       "every row states the reason for its effective state");

    // The three inputs stay separate. A row whose effective state differs
    // from canonical is the one an operator would otherwise misread.
    const differing = REAL_STATE.authorities.filter(
      function (a) { return a.differs_from_canonical; });
    eq(byClass(app.mount, "gl-differs").length, differing.length,
       "rows that differ from canonical say so");
  }

  /* ── 2. protected rows are explained, not just disabled ──────────── */
  {
    const app = load(recorder(function () { return jsonResponse(200, REAL_STATE); }));
    await tick(); await tick();
    app.sandbox.lvGuardLabState().collapsed = false;
    app.sandbox.lvGuardLabRenderInto(app.mount, app.sandbox.lvGuardLabState());

    const protectedRows = REAL_STATE.authorities.filter(function (a) {
      return !a.switchable;
    });
    ok(protectedRows.length > 0, "the real registry has protected authorities");
    eq(byClass(app.mount, "gl-locked").length, protectedRows.length,
       "every non-switchable row renders as locked, with its policy");
    eq(byClass(app.mount, "gl-policy").length, protectedRows.length,
       "the POLICY is named — 'cannot for safety' vs 'cannot yet' are "
       + "different truths");

    const switchableCount = REAL_STATE.authorities.filter(
      function (a) { return a.switchable; }).length;
    eq(buttonsWithText(app.mount, "Off").length, switchableCount,
       "an Off control exists for exactly the switchable authorities");
  }

  /* ── 3. one action, ONE request ──────────────────────────────────── */
  {
    const fetchFn = recorder(function () { return jsonResponse(200, REAL_STATE); });
    const app = load(fetchFn);
    await tick(); await tick();
    app.sandbox.lvGuardLabState().collapsed = false;
    app.sandbox.lvGuardLabRenderInto(app.mount, app.sandbox.lvGuardLabState());

    const before = fetchFn.calls.length;
    buttonsWithText(app.mount, "All Switchable Off")[0].click();
    await tick(); await tick();

    const issued = fetchFn.calls.slice(before);
    eq(issued.length, 1,
       "All Switchable Off is ONE request — 37 writes would be 37 "
       + "revisions and a window where a turn acquires a mixture");
    ok(/\/all-switchable-off$/.test(issued[0].url),
       "it calls the atomic preset route", issued[0].url);
    eq(issued[0].body.expected_revision, REAL_STATE.revision,
       "it carries the revision the operator was looking at");
  }

  /* ── 4. a row write carries the observed revision ────────────────── */
  {
    const fetchFn = recorder(function () { return jsonResponse(200, REAL_STATE); });
    const app = load(fetchFn);
    await tick(); await tick();
    app.sandbox.lvGuardLabState().collapsed = false;
    app.sandbox.lvGuardLabRenderInto(app.mount, app.sandbox.lvGuardLabState());

    const before = fetchFn.calls.length;
    buttonsWithText(app.mount, "Off")[0].click();
    await tick(); await tick();
    const issued = fetchFn.calls.slice(before);
    eq(issued.length, 1, "one row change is one request");
    ok(/\/authorities\/\d+$/.test(issued[0].url), "posted to the authority route",
       issued[0].url);
    eq(issued[0].body.enabled, false, "Off means enabled:false");
    eq(issued[0].body.expected_revision, REAL_STATE.revision,
       "the observed revision travels with the write");
  }

  /* ── 5. the panel adopts the server's answer, never its own guess ── */
  {
    // The server's response DISAGREES with the click: the clicked
    // authority comes back still RUNNING. A panel that patched its own
    // row locally would show EXCLUDED and be wrong. This is the
    // mutation-resistant form of "never re-derives state".
    const target = REAL_STATE.authorities.filter(
      function (a) { return a.switchable && a.effective; })[0];
    const contradicting = JSON.parse(JSON.stringify(REAL_STATE));
    contradicting.revision = REAL_STATE.revision + 1;

    let n = 0;
    const fetchFn = recorder(function () {
      n += 1;
      return jsonResponse(200, n === 1 ? REAL_STATE : contradicting);
    });
    const app = load(fetchFn);
    await tick(); await tick();
    app.sandbox.lvGuardLabState().collapsed = false;
    app.sandbox.lvGuardLabRenderInto(app.mount, app.sandbox.lvGuardLabState());

    const idx = REAL_STATE.authorities.filter(
      function (a) { return a.switchable; }).indexOf(target);
    buttonsWithText(app.mount, "Off")[idx].click();
    await tick(); await tick();

    const rows = byClass(app.mount, "gl-row");
    const rendered = rows.filter(function (r) {
      return textOf(r).indexOf(target.display || target.name) !== -1;
    })[0];
    ok(rendered && textOf(rendered).indexOf("RUNNING") !== -1,
       "the panel renders what the SERVER returned, not what the click "
       + "intended");
    eq(app.sandbox.lvGuardLabState().data.revision, REAL_STATE.revision + 1,
       "the whole configuration was adopted from the response");
  }

  /* ── 6. a stale view is refused, told so, and CORRECTED ──────────── */
  {
    const live = JSON.parse(JSON.stringify(REAL_STATE));
    live.revision = REAL_STATE.revision + 5;
    live.authorities.forEach(function (a) {
      if (a.switchable) { a.effective = false; a.operator_override = false;
                          a.reason = "operator_override"; }
    });

    let n = 0;
    const fetchFn = recorder(function () {
      n += 1;
      if (n === 1) return jsonResponse(200, REAL_STATE);
      return jsonResponse(409, {
        detail: {
          error: "stale_revision",
          message: "configuration changed underneath this request",
          expected_revision: REAL_STATE.revision,
          current_revision: live.revision,
          current: live,
        },
      });
    });
    const app = load(fetchFn);
    await tick(); await tick();
    app.sandbox.lvGuardLabState().collapsed = false;
    app.sandbox.lvGuardLabRenderInto(app.mount, app.sandbox.lvGuardLabState());

    buttonsWithText(app.mount, "All Switchable Off")[0].click();
    await tick(); await tick();

    ok(byClass(app.mount, "gl-conflict").length === 1,
       "the refusal is shown, not swallowed");
    eq(app.sandbox.lvGuardLabState().data.revision, live.revision,
       "the live configuration attached to the 409 is adopted");
    const stillRunning = byClass(app.mount, "gl-eff").filter(function (nd) {
      return textOf(nd).trim() === "RUNNING";
    }).length;
    eq(stillRunning,
       live.authorities.filter(function (a) { return a.effective; }).length,
       "the corrected configuration is what the operator now sees");
  }

  /* ── 7. the gate is reported, so an inert selection says so ──────── */
  {
    const shut = JSON.parse(JSON.stringify(REAL_STATE));
    shut.gate.can_apply_to_a_turn = false;
    const app = load(recorder(function () { return jsonResponse(200, shut); }));
    await tick(); await tick();
    app.sandbox.lvGuardLabState().collapsed = false;
    app.sandbox.lvGuardLabRenderInto(app.mount, app.sandbox.lvGuardLabState());

    ok(byClass(app.mount, "gl-gate-shut").length === 1,
       "a configuration that cannot reach a turn says so");
    const text = textOf(app.mount);
    (shut.gate.conditions || []).forEach(function (c) {
      ok(text.indexOf(c.name) !== -1, "gate condition rendered: " + c.name);
    });
    ok(text.indexOf("NEXT narrator turn") !== -1,
       "next-turn semantics are on screen, in the server's words");
  }

  /* ── 8. the disabled backend renders a placeholder, not an error ─── */
  {
    const app = load(recorder(function () { return jsonResponse(404, null); }));
    await tick(); await tick();
    app.sandbox.lvGuardLabRenderInto(app.mount, app.sandbox.lvGuardLabState());
    ok(textOf(app.mount).indexOf("HORNELORE_OPERATOR_GUARD_LAB") !== -1,
       "an off backend tells the operator how to turn it on");
  }

  if (failures.length) {
    console.error(failures.length + " of " + checks + " checks FAILED:");
    failures.forEach(function (f) { console.error("  ✗ " + f); });
    process.exit(1);
  }
  console.log(checks + " checks passed");
}

main().catch(function (e) {
  console.error("harness error: " + (e && e.stack || e));
  process.exit(2);
});
