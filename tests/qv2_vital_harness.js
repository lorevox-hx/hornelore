/* Questionnaire V2 — birth, death and places (Batch C-4E), DOM harness.

   REAL: ui/js/api.js, questionnaire-v2-model.js and questionnaire-v2.js in
   jsdom, driven through the rendered forms. Every /api/life-record request goes
   to tests/qv2_bridge.py — the SHIPPED writer, rules and assembler on the real
   SQLite tests/test_qv2_vital.py prepared. The database is checked in Python.

   Env: QV2_DB, QV2_PY, QV2_A (narrator), QV2_ROOT (mutation runs).
   Prints {checks:[{name, ok, why}], facts:{…}} as JSON. */
"use strict";
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const { JSDOM, VirtualConsole } = require("jsdom");

const ROOT = process.env.QV2_ROOT || path.resolve(__dirname, "..");
const SRC = ["ui/js/api.js", "ui/js/questionnaire-v2-model.js", "ui/js/questionnaire-v2.js"]
  .map((f) => fs.readFileSync(path.join(ROOT, f), "utf8"));
const DB = process.env.QV2_DB, PY = process.env.QV2_PY, A = process.env.QV2_A;
const checks = [], facts = {};
const check = (name, ok, why) => checks.push({ name, ok: !!ok, why: ok ? "" : String(why) });
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
      log.push({ method, status, body, reply: rb });
      return { ok: status >= 200 && status < 300, status, json: () => Promise.resolve(rb) };
    })();
  };
  SRC.forEach((s) => w.eval(s));
  return { w, log, c: w.document.getElementById("c"), V2: w.LorevoxQuestionnaireV2 };
}
const $ = (t, sel) => t.c.querySelector(sel);
async function settle() {
  let quiet = 0;
  for (let i = 0; i < 4000 && quiet < 10; i++) { await tick(5); quiet = waiting.size ? 0 : quiet + 1; }
}
const click = (t, el) => el.dispatchEvent(new t.w.MouseEvent("click", { bubbles: true }));
const change = (t, el) => el.dispatchEvent(new t.w.Event("change", { bubbles: true }));
const topic = (t, id) => click(t, $(t, '[data-qv2-topic="' + id + '"]'));
const dirty = (t) => Number($(t, "[data-qv2-dirty]").getAttribute("data-qv2-dirty"));
const text = (t) => $(t, ".qv2").textContent;
const need = (t, sel) => { const el = $(t, sel); if (!el) throw new Error("control not offered: " + sel); return el; };
const vform = (t, kind, pid) => need(t, '[data-qv2-form="vital-' + kind + '"][data-person="' + pid + '"]');
const setF = (t, form, f, v) => { const el = form.querySelector('[data-f="' + f + '"]');
  if (!el) throw new Error("field not offered: " + f); el.value = v; change(t, el); };
const keep = (t, form) => click(t, form.querySelector('[data-qv2-action="keep-vital"]'));
const formError = (t) => ($(t, "[data-qv2-form-error]") || {}).textContent || "";
const openRel = (t, rid) => {                  // open the card's details unless they are already open
  const b = $(t, '[data-qv2-rel="' + rid + '"] [data-qv2-action="open-rel"]');
  if (b) click(t, b);
  else need(t, '[data-qv2-form="rel"][data-rel="' + rid + '"]');
};
const answer = (t, concept, v) => { const el = need(t, '[data-qv2-answer$=":' + concept + '"]'); el.value = v; change(t, el); };
const patches = (t, from) => t.log.slice(from).filter((r) => r.method === "PATCH");

(async function run() {
  const t = openTab();
  t.V2.render(t.c, A); await settle();
  topic(t, "narrator");

  /* 13 — an impossible date and a range are refused on the form; nothing pending */
  let nb = vform(t, "birth", A);
  setF(t, nb, "date", "1939-02-30"); keep(t, nb);
  check("an impossible birth date is refused on the form; nothing pending",
    /not a real date/.test(formError(t)) && dirty(t) === 0, formError(t) + " dirty=" + dirty(t));
  nb = vform(t, "birth", A);
  setF(t, nb, "date", "1939 to 1940"); keep(t, nb);
  check("a range is refused as a birth date; nothing pending",
    /one date, not a range/.test(formError(t)) && dirty(t) === 0, formError(t));

  /* 1, 5 — the narrator's birth: date + an EXISTING place chosen by id (the SECOND "Minot") */
  nb = vform(t, "birth", A);
  const opts = Array.from(nb.querySelectorAll('[data-f="place"] option')).map((o) => o.value + "=" + o.textContent);
  check("same-named places are offered separately, each by its own record id",
    opts.some((o) => o.startsWith("existing:pl-a=")) && opts.some((o) => o.startsWith("existing:pl-b=")) &&
    opts.filter((o) => /=Minot — record /.test(o)).length === 2, opts.join(" | "));
  setF(t, nb, "date", "30 August 1939"); setF(t, nb, "place", "existing:pl-b"); keep(t, nb);
  check("the narrator's birth is kept as one pending change", dirty(t) === 1 && !formError(t), formError(t));

  /* family: Ada — her existing birth is EXTENDED; her death recorded with a NEW same-named place */
  topic(t, "family");
  openRel(t, "r1");
  const ab = vform(t, "birth", "p-m");
  check("her stored birth date is shown in the form, as said",
    ab.querySelector('[data-f="date"]').value === "1915", ab.querySelector('[data-f="date"]').value);
  setF(t, ab, "date", "about 1915"); keep(t, ab);
  openRel(t, "r1");
  const ad = vform(t, "death", "p-m");
  setF(t, ad, "date", "unknown"); setF(t, ad, "place", "new"); setF(t, ad, "newPlaceLabel", "Minot"); keep(t, ad);
  check("a new place with a recorded name is SUGGESTED to be the same, never merged",
    /already recorded/.test(($(t, '[data-qv2-msg="info"]') || {}).textContent || "") && dirty(t) === 3,
    text(t).slice(0, 300));
  const pend = Object.values(t.V2._state().edits).find((e) => e.kind === "vital" && e.vitalKind === "death");
  check("recording her death carries 'deceased' in the same change (she is recorded living)",
    pend && pend.deceased && pend.place.mode === "new" && !["pl-a", "pl-b"].includes(pend.place.placeId),
    JSON.stringify(pend));

  /* C-4E review — Greta: an EXPLICITLY ACCEPTED birth date is corrected, and
     her EXPLICITLY ACCEPTED "living" is replaced by a death, in this same Save */
  openRel(t, "r3");
  const gb = vform(t, "birth", "p-g");
  check("the accepted birth date is what the form shows", gb.querySelector('[data-f="date"]').value === "1920",
    gb.querySelector('[data-f="date"]').value);
  setF(t, gb, "date", "1922"); keep(t, gb);
  openRel(t, "r3");
  const gd = vform(t, "death", "p-g");
  setF(t, gd, "date", "2001"); keep(t, gd);
  check("Greta's two changes are kept without a form error", !formError(t) && dirty(t) === 5, formError(t) + " " + dirty(t));

  /* 11 — Olaf: DECEASED ALONE, through the life-status control only */
  openRel(t, "r2");
  answer(t, "person.life_status", "deceased");
  check("six pending changes before Save", dirty(t) === 6, dirty(t));

  /* 9 — one Save, one PATCH, accepted */
  const n0 = t.log.length;
  click(t, need(t, '[data-qv2-action="save"]')); await settle();
  const p1 = patches(t, n0);
  facts.firstPatch = p1.length ? p1[0].body.changes : null;
  check("one Save is ONE PATCH, and the writer accepts it", p1.length === 1 && p1[0].status === 200,
    JSON.stringify(p1.map((p) => [p.status, p.reply])).slice(0, 400));
  const ch = facts.firstPatch || [];
  const deathEvents = ch.filter((c) => c.op === "add" && /^events\//.test(c.path) && c.value.type === "death");
  check("death events are created ONLY for Ada and Greta — not for Olaf, marked deceased alone",
    JSON.stringify(deathEvents.map((e) => e.value.participants[0].person).sort()) === '["p-g","p-m"]',
    JSON.stringify(deathEvents));
  const accMoves = ch.filter((c) => c.op === "set" && /^acceptances\//.test(c.path));
  check("both explicit acceptances move with their corrections, each guarded by the id it replaces",
    accMoves.length === 2 &&
    accMoves.some((c) => c.path === "acceptances/event/e-gb/person.birth.date" && c.expectedPrevious === "g-A") &&
    accMoves.some((c) => c.path === "acceptances/person/p-g/person.life_status" && c.expectedPrevious === "gls"),
    JSON.stringify(accMoves));
  check("Ada's birth is extended, not duplicated: no new birth event for her",
    !ch.some((c) => c.op === "add" && /^events\//.test(c.path) && c.value.type === "birth" &&
      c.value.participants[0].person === "p-m"), JSON.stringify(ch.filter((c) => /^events\//.test(c.path))));

  /* 16 — read back from the SERVER after Save */
  topic(t, "narrator");
  const nline = ($(t, '[data-qv2-vital="birth:' + A + '"]') || {}).textContent || "";
  check("after Save the narrator's birth reads back from the record", /30 August 1939/.test(nline) && /Minot/.test(nline), nline);
  topic(t, "family"); openRel(t, "r1");
  const dline = ($(t, '[data-qv2-vital="death:p-m"]') || {}).textContent || "";
  check("after Save Ada's death reads back — date as said, the new place", /unknown/.test(dline) && /Minot/.test(dline), dline);

  /* 2, 5 — change the narrator's birth PLACE to the FIRST Minot: a set on the same event */
  topic(t, "narrator");
  nb = vform(t, "birth", A);
  setF(t, nb, "place", "existing:pl-a"); keep(t, nb);
  const n1 = t.log.length;
  click(t, need(t, '[data-qv2-action="save"]')); await settle();
  const p2 = patches(t, n1);
  facts.secondPatch = p2.length ? p2[0].body.changes : null;
  const setEv = (facts.secondPatch || []).filter((c) => /^events\//.test(c.path));
  check("changing a stored birth's place is ONE set on the same event, carrying its previous value",
    p2.length === 1 && p2[0].status === 200 && setEv.length === 1 && setEv[0].op === "set" &&
    setEv[0].value.place === "pl-a" && setEv[0].expectedPrevious.place === "pl-b", JSON.stringify(facts.secondPatch));

  /* death + a pending life-status edit that is NOT deceased: refused on the form */
  topic(t, "family"); openRel(t, "r2");
  answer(t, "person.life_status", "unknown");
  openRel(t, "r2");
  const od = vform(t, "death", "p-f");
  setF(t, od, "date", "1980"); keep(t, od);
  check("a death beside an unsaved non-deceased life status is refused on the form",
    /unsaved change/.test(formError(t)) && !Object.values(t.V2._state().edits).some((e) => e.kind === "vital"),
    formError(t));

  process.stdout.write(JSON.stringify({ checks, facts }));
})().catch((e) => { process.stdout.write(JSON.stringify({ checks, facts, error: String(e && e.stack || e) })); })
  .finally(() => { BR.kill(); });
