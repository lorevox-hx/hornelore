/* Questionnaire V2 shell — DOM harness (Batch C-2).

   REAL: ui/js/api.js, ui/js/questionnaire-v2-model.js and
   ui/js/questionnaire-v2.js, loaded unmodified into jsdom and driven by
   clicks and change events on the rendered DOM. What is asserted is what the
   page actually sent.

   THE SERVER IS NOT A DOUBLE: every /api/life-record request is handed to
   tests/qv2_bridge.py, which runs the SHIPPED writer and assembler on the
   real SQLite file the Python test prepared. A PATCH the UI builds either
   passes the real writer or it does not.

   Driven by tests/test_qv2_shell.py (env QV2_DB, QV2_PY, QV2_A, QV2_B).
   Prints {checks:[{name, ok, why}], facts:{…}} as JSON. */
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");
const { JSDOM } = require("jsdom");

const ROOT = path.resolve(__dirname, "..");
const SRC = ["ui/js/api.js", "ui/js/questionnaire-v2-model.js", "ui/js/questionnaire-v2.js"]
  .map((f) => fs.readFileSync(path.join(ROOT, f), "utf8"));
const DB = process.env.QV2_DB, PY = process.env.QV2_PY, A = process.env.QV2_A, B = process.env.QV2_B;

const checks = [], facts = {};
const check = (name, ok, why) => checks.push({ name, ok: !!ok, why: ok ? "" : String(why) });
const tick = (ms) => new Promise((r) => setTimeout(r, ms || 0));

function bridge(method, pid, body) {
  const args = [path.join(ROOT, "tests", "qv2_bridge.py"), DB, method, pid];
  if (body !== undefined) {
    const f = path.join(os.tmpdir(), "qv2-body-" + process.pid + "-" + Date.now() + ".json");
    fs.writeFileSync(f, body);
    args.push(f);
  }
  return JSON.parse(execFileSync(PY, args, { encoding: "utf8" }));
}

/* One browser "tab": its own window, storage, request log and module state. */
function openTab(sharedStorage) {
  const dom = new JSDOM('<!doctype html><div id="c"></div>', { url: "http://localhost/", runScripts: "outside-only" });
  const w = dom.window;
  const log = [], held = [];
  let storageWrites = 0;
  if (sharedStorage) Object.keys(sharedStorage).forEach((k) => w.localStorage.setItem(k, sharedStorage[k]));
  const proto = w.Storage.prototype, set = proto.setItem, rem = proto.removeItem;
  proto.setItem = function (k, v) { storageWrites++; return set.call(this, k, v); };
  proto.removeItem = function (k) { storageWrites++; return rem.call(this, k); };
  const tab = {
    w, log, held, hold: null,
    get storageWrites() { return storageWrites; },
    doc: w.document, c: w.document.getElementById("c"),
    V2: null,
    writes() { return log.filter((r) => r.method !== "GET"); },
    release(i) { const h = held.splice(i || 0, 1)[0]; h.go(); },
    storage() { const o = {}; for (let i = 0; i < w.localStorage.length; i++) { const k = w.localStorage.key(i); o[k] = w.localStorage.getItem(k); } return o; },
  };
  w.fetch = (url, opts) => {
    const method = (opts && opts.method) || "GET";
    log.push({ method, url: String(url), body: opts && opts.body ? JSON.parse(opts.body) : null });
    const m = String(url).match(/\/api\/life-record\/([^/?]+)$/);
    const respond = () => {
      let status = 404, body = { detail: "not served by the harness" };
      if (m) ({ status, body } = bridge(method, decodeURIComponent(m[1]), opts && opts.body));
      else if (String(url).indexOf("/api/bio-builder/questionnaire") !== -1 && method === "GET") {
        status = 200; body = { questionnaire: { personal: { fullName: "Ines Okafor", placeOfBirth: "Lagos" },
                                                  siblings: [{ firstName: "Chidi" }] } };
      }
      return { ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) };
    };
    if (tab.hold && tab.hold(method, String(url))) {
      return new Promise((res) => held.push({ url: String(url), go: () => res(respond()) }));
    }
    return Promise.resolve(respond());
  };
  SRC.forEach((s) => w.eval(s));
  tab.V2 = w.LorevoxQuestionnaireV2;
  return tab;
}
const $ = (t, sel) => t.c.querySelector(sel);
const $$ = (t, sel) => Array.from(t.c.querySelectorAll(sel));
async function settle() { for (let i = 0; i < 20; i++) await tick(5); }
function edit(t, value) {
  const inp = $(t, '[data-qv2-answer$=":person.birth.order"]');
  inp.value = value;
  inp.dispatchEvent(new t.w.Event("change", { bubbles: true }));
}
const click = (t, sel) => $(t, sel).dispatchEvent(new t.w.MouseEvent("click", { bubbles: true }));
const header = (t) => ($(t, ".qv2-head strong") || {}).textContent;

(async function run() {
  /* 1 — opening writes nothing, and hydration is not an edit */
  {
    const t = openTab();
    t.V2.render(t.c, A); await settle();
    check("open: exactly one request, a GET of this narrator's Life Record",
      t.log.length === 1 && t.log[0].method === "GET" && /\/api\/life-record\//.test(t.log[0].url) &&
      t.log[0].url.endsWith(encodeURIComponent(A)), JSON.stringify(t.log));
    check("open: no browser storage written", t.storageWrites === 0, t.storageWrites + " writes");
    check("hydration is not dirty: Save disabled, nothing pending",
      $(t, '[data-qv2-action="save"]').disabled && $(t, "[data-qv2-dirty]").getAttribute("data-qv2-dirty") === "0",
      $(t, ".qv2-head").textContent);
    const tabs = $$(t, "[data-qv2-topic]").map((b) => b.textContent.trim());
    check("all eleven topics are on screen, in order", tabs.length === 11 &&
      tabs[0].startsWith("1. The narrator") && tabs[10].startsWith("11. Memories, lessons and legacy"),
      JSON.stringify(tabs));
    check("the narrator is shown from the Life Record", header(t) === "Ines Maribel Okafor-Lund", header(t));
    check("the stored birth order is shown in its field",
      $(t, '[data-qv2-answer$=":person.birth.order"]').value === "second of four",
      $(t, '[data-qv2-answer$=":person.birth.order"]').value);

    /* 2 — moving through all eleven topics writes nothing */
    const ids = $$(t, "[data-qv2-topic]").map((b) => b.getAttribute("data-qv2-topic"));
    const seen = [];
    for (const id of ids) { click(t, '[data-qv2-topic="' + id + '"]'); seen.push($(t, "[data-qv2-panel]").getAttribute("data-qv2-panel")); }
    check("navigation renders each topic's panel", JSON.stringify(seen) === JSON.stringify(ids), JSON.stringify(seen));
    check("navigation: no request of any kind, no storage write",
      t.log.length === 1 && t.storageWrites === 0, t.log.length + " requests, " + t.storageWrites + " writes");
  }

  /* 3 — switching narrators writes nothing, and a late response for the
         old narrator cannot land on the new one */
  {
    const t = openTab();
    t.hold = (m, url) => m === "GET";
    t.V2.render(t.c, A);                 // A's GET in flight
    t.V2.render(t.c, B);                 // switch before it answers
    t.release(1); await settle();        // B answers first
    t.release(0); await settle();        // A answers late
    check("switch: a late response for narrator A does not populate narrator B",
      header(t) === "Owen Marsh" && t.c.textContent.indexOf("Okafor") === -1, header(t));
    check("switch: only two GETs, nothing written", t.log.length === 2 && t.writes().length === 0 &&
      t.storageWrites === 0, JSON.stringify(t.log.map((r) => r.method)) + " / " + t.storageWrites);
  }

  /* 4 — an edit is dirty and drafted for THIS narrator only; a switch
         afterwards writes nothing more */
  {
    const t = openTab();
    t.V2.render(t.c, A); await settle();
    edit(t, "the middle child");
    const draft = JSON.parse(t.storage()["lorevox_qv2_draft_" + A] || "null");
    check("an edit marks the form dirty and enables Save",
      $(t, "[data-qv2-dirty]").getAttribute("data-qv2-dirty") === "1" && !$(t, '[data-qv2-action="save"]').disabled &&
      $(t, '[data-qv2-topic="narrator"] .qv2-dot'), $(t, ".qv2-head").textContent);
    check("the draft is narrator-scoped and stamped with the revision it was made against",
      draft && draft.pid === A && draft.baseRevision === t.V2._state().baseRevision &&
      Object.keys(t.storage()).every((k) => k.indexOf(B) === -1), JSON.stringify(t.storage()));
    for (const b of $$(t, "[data-qv2-topic]").map((x) => x.getAttribute("data-qv2-topic"))) {
      click(t, '[data-qv2-topic="' + b + '"]');
    }
    await settle();
    check("navigating with an unsaved change pending sends nothing — only Save saves",
      t.writes().length === 0 && $(t, "[data-qv2-dirty]").getAttribute("data-qv2-dirty") === "1",
      JSON.stringify(t.writes().map((r) => r.method)));
    const writesBefore = t.storageWrites;
    t.V2.render(t.c, B); await settle();
    check("a switch after an edit sends nothing and writes no storage",
      t.writes().length === 0 && t.storageWrites === writesBefore, t.storageWrites - writesBefore + " extra writes");
    facts.draftForReload = t.storage();
  }

  /* 5 — a reload restores the draft beside the SERVER value; the server is not overwritten */
  {
    const t = openTab(facts.draftForReload);
    t.V2.render(t.c, A); await settle();
    check("reload: the unsaved change comes back, flagged, still unsaved",
      $(t, "[data-qv2-dirty]").getAttribute("data-qv2-dirty") === "1" && $(t, '[data-qv2-msg="info"]') &&
      t.writes().length === 0, $(t, ".qv2-head").textContent);
    click(t, '[data-qv2-action="discard"]');
    check("discard empties the draft and sends nothing",
      !t.storage()["lorevox_qv2_draft_" + A] && t.writes().length === 0, JSON.stringify(t.storage()));
  }

  /* 6 — Save is one PATCH of writer operations; the server is then re-read */
  {
    const stale = openTab();                         // opened BEFORE the save below
    stale.V2.render(stale.c, A); await settle();

    const t = openTab();
    t.V2.render(t.c, A); await settle();
    edit(t, "the middle child");
    const nBefore = t.log.length;
    click(t, '[data-qv2-action="save"]'); await settle();
    const sent = t.log.slice(nBefore);
    const patch = sent.find((r) => r.method === "PATCH");
    check("Save sends exactly one PATCH to this narrator's Life Record, then re-reads it",
      sent.length === 2 && patch && patch.url.endsWith("/api/life-record/" + encodeURIComponent(A)) &&
      sent[1].method === "GET", JSON.stringify(sent.map((r) => r.method + " " + r.url)));
    const ops = patch ? patch.body.changes.map((c) => c.op + " " + c.path.replace(/qv2a-[a-z0-9]+/, "NEW")) : [];
    check("...a correction, as writer operations: add the new account, supersede the old",
      patch && patch.body.baseRevision === 1 && patch.body.actor === "operator" &&
      JSON.stringify(ops) === JSON.stringify(["add assertions/NEW", "set assertions/bo/supersededBy",
                                              "set assertions/bo/status"]) &&
      patch.body.changes[2].expectedPrevious === "operator_entered" &&
      patch.body.changes[0].value.assertedBy === "operator", JSON.stringify(patch && patch.body));
    check("...never a whole document", patch && !("questionnaire" in patch.body) && !("persons" in patch.body),
      Object.keys((patch && patch.body) || {}));
    check("after Save the field shows the server's value and nothing is pending",
      $(t, '[data-qv2-answer$=":person.birth.order"]').value === "the middle child" &&
      $(t, "[data-qv2-dirty]").getAttribute("data-qv2-dirty") === "0" && !t.storage()["lorevox_qv2_draft_" + A] &&
      $(t, '[data-qv2-msg="ok"]'), $(t, ".qv2").textContent.slice(0, 200));
    facts.savedRevision = t.V2._state().baseRevision;

    /* 7 — the stale tab edits the same field: refused as a conflict, draft kept */
    edit(stale, "the eldest");
    const sBefore = stale.log.length;
    click(stale, '[data-qv2-action="save"]'); await settle();
    const res = stale.log.slice(sBefore);
    check("a stale same-field save is refused and SHOWN as a conflict — not resent, not 'save failed'",
      res.length === 1 && res[0].method === "PATCH" && $(stale, "[data-qv2-conflict]") &&
      $(stale, '[data-qv2-msg="conflict"]') && $(stale, "[data-qv2-conflict]").textContent.indexOf("assertions/bo/") !== -1,
      $(stale, ".qv2").textContent.slice(0, 300));
    check("...and the operator's unsaved change is kept",
      $(stale, "[data-qv2-dirty]").getAttribute("data-qv2-dirty") === "1" &&
      JSON.parse(stale.storage()["lorevox_qv2_draft_" + A]).edits, JSON.stringify(stale.storage()));
  }

  /* 8 — a first answer is a plain add */
  {
    const t = openTab();
    t.V2.render(t.c, B); await settle();
    edit(t, "only child");
    click(t, '[data-qv2-action="save"]'); await settle();
    const patch = t.log.find((r) => r.method === "PATCH");
    check("a first answer is one `add`, nothing superseded",
      patch && patch.body.changes.length === 1 && patch.body.changes[0].op === "add" &&
      $(t, '[data-qv2-answer$=":person.birth.order"]').value === "only child",
      JSON.stringify(patch && patch.body));
  }

  /* 9 — Earlier answers: read-only, nothing that can write */
  {
    const t = openTab();
    t.V2.renderEarlierAnswers(t.c, A); await settle();
    check("Earlier answers shows the legacy values with no control that could change them",
      t.c.textContent.indexOf("Lagos") !== -1 && $$(t, "input, textarea, select, button").length === 0,
      t.c.innerHTML.slice(0, 300));
    check("...and only reads", t.writes().length === 0 && t.storageWrites === 0 &&
      t.log.every((r) => /\/api\/bio-builder\/questionnaire\?/.test(r.url)), JSON.stringify(t.log));
  }

  process.stdout.write(JSON.stringify({ checks, facts }));
})().catch((e) => { process.stdout.write(JSON.stringify({ checks, facts, error: String(e && e.stack || e) })); });
