/* Questionnaire V2 — capability harness (Batch C-4C).

   Drives EVERY control the shipped V2 editor offers, the way an operator
   would, and reports the Life Record changes the editor actually sent. The
   Python test (tests/test_qv2_capabilities.py) translates those changes into
   catalog concepts and compares them with a FROZEN expected set and with the
   model's QV2_CAPABILITIES declaration — three independent things.

   REAL: ui/js/api.js, questionnaire-v2-model.js and questionnaire-v2.js in
   jsdom. Every /api/life-record request goes to tests/qv2_bridge.py — the
   SHIPPED writer on the real SQLite the Python test prepared — so the changes
   reported here are changes the writer ACCEPTED, not merely changes proposed.

   It also opens a second tab with the declaration EMPTIED at runtime and
   counts the controls left: the editor must fail closed (no concept-writing
   control offered for an undeclared concept).

   Env: QV2_DB, QV2_PY, QV2_A (narrator), QV2_ROOT (mutation runs).
   Prints {patches:[changes…], saved:bool, closed:{…}, error?} as JSON. */
"use strict";
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const { JSDOM, VirtualConsole } = require("jsdom");

const ROOT = process.env.QV2_ROOT || path.resolve(__dirname, "..");
const SRC = ["ui/js/api.js", "ui/js/questionnaire-v2-model.js", "ui/js/questionnaire-v2.js"]
  .map((f) => fs.readFileSync(path.join(ROOT, f), "utf8"));
const DB = process.env.QV2_DB, PY = process.env.QV2_PY, A = process.env.QV2_A;
const tick = (ms) => new Promise((r) => setTimeout(r, ms || 0));

const BR = spawn(PY, [path.join(__dirname, "qv2_bridge.py"), DB, "--serve"], { stdio: ["pipe", "pipe", "inherit"] });
const waiting = new Map();
let nextId = 0, buf = "";
BR.stdout.on("data", (d) => {
  buf += d.toString();
  let i;
  while ((i = buf.indexOf("\n")) >= 0) {
    const line = buf.slice(0, i); buf = buf.slice(i + 1);
    if (!line.trim()) continue;
    const msg = JSON.parse(line);
    const w = waiting.get(msg.id); waiting.delete(msg.id);
    if (w) w(msg);
  }
});
function bridge(method, pid, body) {
  const id = ++nextId;
  return new Promise((res) => { waiting.set(id, res); BR.stdin.write(JSON.stringify({ id, method, pid, body }) + "\n"); });
}

function openTab() {
  const dom = new JSDOM('<!doctype html><div id="c"></div>',
    { url: "http://localhost/", runScripts: "outside-only", virtualConsole: new VirtualConsole() });
  const w = dom.window, log = [];
  w.fetch = (url, opts) => {
    const method = (opts && opts.method) || "GET";
    const body = opts && opts.body ? JSON.parse(opts.body) : null;
    const m = String(url).match(/\/api\/life-record\/([^/?]+)$/);
    return (async () => {
      let status = 404, rb = { detail: "not served by the harness" };
      if (m) ({ status, body: rb } = await bridge(method, decodeURIComponent(m[1]), opts && opts.body));
      log.push({ method, status, body });
      return { ok: status >= 200 && status < 300, status, json: () => Promise.resolve(rb) };
    })();
  };
  SRC.forEach((s) => w.eval(s));
  return { w, log, c: w.document.getElementById("c"), V2: w.LorevoxQuestionnaireV2,
           M: w.LorevoxQuestionnaireV2Model };
}
const $ = (t, sel) => t.c.querySelector(sel);
const $$ = (t, sel) => Array.from(t.c.querySelectorAll(sel));
async function settle() {
  let quiet = 0;
  for (let i = 0; i < 4000 && quiet < 10; i++) { await tick(5); quiet = waiting.size ? 0 : quiet + 1; }
}
const click = (t, el) => el.dispatchEvent(new t.w.MouseEvent("click", { bubbles: true }));
const change = (t, el) => el.dispatchEvent(new t.w.Event("change", { bubbles: true }));
const topic = (t, id) => click(t, $(t, '[data-qv2-topic="' + id + '"]'));
const need = (t, sel) => { const el = $(t, sel); if (!el) throw new Error("control not offered: " + sel); return el; };
const setField = (t, form, f, v) => { const el = form.querySelector('[data-f="' + f + '"]');
  if (!el) throw new Error("field not offered: " + f); el.value = v; change(t, el); };
const answer = (t, concept, v) => { const el = need(t, '[data-qv2-answer$=":' + concept + '"]'); el.value = v; change(t, el); };

(async function run() {
  const out = { patches: [], saved: false, closed: null };
  const t = openTab();
  t.V2.render(t.c, A); await settle();

  /* narrator: names (edit whole, add also-known-as, add variant), preferred,
     pronouns, birth order */
  topic(t, "narrator");
  const nm = need(t, '[data-qv2-name="' + A + ':n1"]'); nm.value = "Ines Maribel Okafor-Lund"; change(t, nm);
  for (const [text, kind] of [["Nessa", "also_known_as"], ["Inez Okafor-Lund", "variant"]]) {
    const f = need(t, '[data-qv2-form="name"][data-person="' + A + '"]');
    setField(t, f, "fullText", text); setField(t, f, "nameKind", kind);
    click(t, f.querySelector('[data-qv2-action="add-name"]'));
  }
  const pref = need(t, '[data-qv2-preferred="' + A + ':n2"]'); pref.checked = true; change(t, pref);
  const pf = need(t, '[data-qv2-form="pronoun"]'); setField(t, pf, "pronoun", "she/her");
  click(t, pf.querySelector('[data-qv2-action="add-pronoun"]'));
  answer(t, "person.birth.order", "the middle one");

  /* family: sibling count; add a new person with every relationship control */
  topic(t, "family");
  answer(t, "person.reported_count.siblings", "4");
  const af = need(t, '[data-qv2-form="person"]');
  setField(t, af, "fullText", "Tomas Lund"); setField(t, af, "role", "sibling");
  setField(t, af, "lineage", "paternal"); setField(t, af, "lifeStatus", "explicitly_living");
  setField(t, af, "from", "1941"); setField(t, af, "until", "1990");
  click(t, af.querySelector('[data-qv2-action="add-person"]'));

  /* an existing relationship: life status of the person, period changed */
  click(t, need(t, '[data-qv2-rel="r1"] [data-qv2-action="open-rel"]'));
  const rf = need(t, '[data-qv2-form="rel"]');
  answer(t, "person.life_status", "deceased");
  const rf2 = need(t, '[data-qv2-form="rel"]');
  setField(t, rf2, "until", "1995");
  click(t, rf2.querySelector('[data-qv2-action="keep-rel"]'));
  void rf;

  /* partners: children and grandchildren counts */
  topic(t, "partners");
  answer(t, "person.reported_count.children", "2");
  answer(t, "person.reported_count.grandchildren", "0");

  const n0 = t.log.length;
  click(t, need(t, '[data-qv2-action="save"]')); await settle();
  t.log.slice(n0).filter((r) => r.method === "PATCH").forEach((r) => {
    out.patches.push({ status: r.status, changes: r.body.changes });
  });
  out.saved = out.patches.length === 1 && out.patches[0].status === 200;

  /* fail closed: the SAME shipped editor with the declaration emptied */
  const c = openTab();
  c.M.CAPABILITIES.editableConcepts.length = 0;
  c.V2.render(c.c, A); await settle();
  const census = {};
  for (const tp of ["narrator", "family", "partners", "wider"]) {
    topic(c, tp);
    const r1 = $(c, '[data-qv2-rel="r1"] [data-qv2-action="open-rel"]'); if (r1) click(c, r1);
    census[tp] = {
      answers: $$(c, "[data-qv2-answer]").length, names: $$(c, "[data-qv2-name]").length,
      preferred: $$(c, "[data-qv2-preferred]").length, addName: $$(c, '[data-qv2-form="name"]').length,
      pronoun: $$(c, '[data-qv2-form="pronoun"]').length, addPerson: $$(c, '[data-qv2-form="person"]').length,
      period: $$(c, '[data-f="from"], [data-f="until"]').length,
    };
  }
  out.closed = census;
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { process.stdout.write(JSON.stringify({ error: String(e && e.stack || e) })); })
  .finally(() => { BR.kill(); });
