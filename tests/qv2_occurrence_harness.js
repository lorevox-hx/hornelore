/* Questionnaire V2 — homes, unions and separations (Batch C-4F), DOM harness.

   REAL: ui/js/api.js, questionnaire-v2-model.js and questionnaire-v2.js in
   jsdom, driven through the rendered forms. Every /api/life-record request goes
   to tests/qv2_bridge.py — the SHIPPED writer, rules and assembler on the real
   SQLite tests/test_qv2_occurrences.py prepared. The database is checked in Python.

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
const setF = (t, form, f, v) => { const el = form.querySelector('[data-f="' + f + '"]');
  if (!el) throw new Error("field not offered: " + f); el.value = v; change(t, el); };
const formError = (t) => ($(t, "[data-qv2-form-error]") || {}).textContent || "";
const openRel = (t, rid) => {                  // open the card's details unless they are already open
  const b = $(t, '[data-qv2-rel="' + rid + '"] [data-qv2-action="open-rel"]');
  if (b) click(t, b);
  else need(t, '[data-qv2-form="rel"][data-rel="' + rid + '"]');
};
const answer = (t, concept, v) => { const el = need(t, '[data-qv2-answer$=":' + concept + '"]'); el.value = v; change(t, el); };
const patches = (t, from) => t.log.slice(from).filter((r) => r.method === "PATCH");

const oform = (t, eid) => need(t, '[data-qv2-form="occ"][data-event="' + eid + '"]');
const nform = (t) => need(t, '[data-qv2-form="occ-new"]');
const keep = (t, form) => click(t, form.querySelector('[data-qv2-action="keep-occ"]'));
const edits = (t) => Object.values(t.V2._state().edits);
const msg = (t) => ($(t, '[data-qv2-msg="info"]') || {}).textContent || "";
const setCurrent = (t, form, on) => { const b = form.querySelector('[data-f="current"]');
  if (!b) throw new Error("field not offered: current"); b.checked = on; change(t, b); };

(async function run() {
  const t = openTab();
  t.V2.render(t.c, A); await settle();
  let n;

  /* ── homes ─────────────────────────────────────────────────────── */
  topic(t, "homes");
  check("each stored home has its own form, with its stored period shown as said",
    oform(t, "e-h1").querySelector('[data-f="date"]').value === "1962 to 1975" &&
    oform(t, "e-h2").querySelector('[data-f="date"]').value === "about 1989 to 1995",
    oform(t, "e-h1").querySelector('[data-f="date"]').value);
  check("the stored current home shows as current, and its box is ticked",
    !!$(t, '[data-qv2-occ="e-h3"] [data-qv2-current]') && oform(t, "e-h3").querySelector('[data-f="current"]').checked &&
    !oform(t, "e-h1").querySelector('[data-f="current"]').checked, text(t).slice(0, 300));
  check("a home with a co-resident names them in its header",
    /Rosa Lund/.test(($(t, '[data-qv2-occ="e-h5"]') || {}).textContent || ""), ($(t, '[data-qv2-occ="e-h5"]') || {}).textContent);

  // an impossible period is refused on the form; nothing pending
  let f = oform(t, "e-h1");
  setF(t, f, "date", "1962-02-30 to 1975"); keep(t, f);
  check("an impossible period is refused on the form; nothing pending",
    /not a real date/.test(formError(t)) && dirty(t) === 0, formError(t) + " dirty=" + dirty(t));
  // a home whose period has ENDED cannot be marked current
  f = oform(t, "e-h1"); setF(t, f, "date", "1962 to 1975");
  setCurrent(t, f, true); keep(t, f);
  check("a home with an ended period cannot be marked current; nothing pending",
    /period that has ended/.test(formError(t)) && dirty(t) === 0, formError(t) + " dirty=" + dirty(t));
  // unticking a current home whose stored period runs "to present" is refused unless the period changes too
  f = oform(t, "e-h4"); setCurrent(t, f, false); keep(t, f);
  check("unticking current while the stored period runs “to present” is refused; nothing pending",
    /runs “to present”/.test(formError(t)) && dirty(t) === 0, formError(t) + " dirty=" + dirty(t));

  // e-h1: the period corrected (its stored period is EXPLICITLY ACCEPTED)
  f = oform(t, "e-h1"); setCurrent(t, f, false); setF(t, f, "date", "1962 to 1976"); keep(t, f);
  // e-h2: the place ONLY — the legacy period text is left exactly as shown
  f = oform(t, "e-h2");
  const opts = Array.from(f.querySelectorAll('[data-f="place"] option')).map((o) => o.value + "=" + o.textContent);
  check("same-named places are offered separately, each by its own record id",
    opts.filter((o) => /^existing:pl-[ab]=Minot — record /.test(o)).length === 2, opts.join(" | "));
  setF(t, f, "place", "existing:pl-b"); keep(t, f);
  check("two homes edited are two pending changes — one does not overwrite the other",
    dirty(t) === 2 && edits(t).filter((e) => e.kind === "occ").map((e) => e.eventId).sort().join() === "e-h1,e-h2",
    JSON.stringify(edits(t)));
  const e2 = edits(t).find((e) => e.eventId === "e-h2");
  check("a place-only edit does not re-parse the unchanged legacy period", e2 && e2.date === null, JSON.stringify(e2));
  // e-h3: they no longer live there — untick current (no period is invented)
  f = oform(t, "e-h3"); setCurrent(t, f, false); keep(t, f);
  const e3 = edits(t).find((e) => e.eventId === "e-h3");
  check("unticking current is its own change, and invents no period", e3 && e3.current === false && e3.date === null,
    JSON.stringify(e3));
  // LEGACY contradictions already stored never block an unrelated edit
  f = oform(t, "e-h5"); setF(t, f, "place", "existing:pl-c"); keep(t, f);
  f = oform(t, "e-h6"); setF(t, f, "place", "existing:pl-c"); keep(t, f);
  check("a stored current home with an ended period, and a stored “to present” home that is not current, still take a place edit",
    !formError(t) && dirty(t) === 5 && ["e-h5", "e-h6"].every((id) => edits(t).some((e) => e.eventId === id)),
    formError(t) + " " + dirty(t));
  // the kind of home, on a stored home with none recorded
  answer(t, "event.residence.type", "farmhouse");
  check("the kind of home is an ordinary answer on that home", dirty(t) === 6 &&
    edits(t).some((e) => e.kind === "answer" && e.subjectType === "event" && e.subjectId === "e-h1" && e.value === "farmhouse"),
    JSON.stringify(edits(t)));

  // a new home with nothing said is refused
  f = nform(t); keep(t, f);
  check("a new home with neither place nor period is refused", /say where/.test(formError(t)) && dirty(t) === 6, formError(t));
  // a new home "to present" that is NOT ticked current contradicts itself
  f = nform(t); setF(t, f, "date", "2001 to present"); keep(t, f);
  check("a new “to present” home left un-ticked is refused", /tick Current/.test(formError(t)) && dirty(t) === 6, formError(t));
  // a new home "to present", CURRENT, in a NEW place that shares a recorded name, with its kind — one Keep
  f = nform(t);
  setF(t, f, "date", "1990 to present"); setF(t, f, "place", "new"); setF(t, f, "newPlaceLabel", "Minot");
  setF(t, f, "homeType", "apartment"); setCurrent(t, f, true); keep(t, f);
  check("a new place with a recorded name is SUGGESTED to be the same, never merged",
    /already recorded/.test(msg(t)) && dirty(t) === 7, msg(t) + " " + formError(t));
  const nh = edits(t).find((e) => e.kind === "occ" && e.isNew);
  check("the new home: its own place, current as said, and its kind — in one pending change",
    nh && nh.place.mode === "new" && !["pl-a", "pl-b"].includes(nh.place.placeId) && nh.current === true &&
    nh.homeType === "apartment", JSON.stringify(nh));
  // a new home with an UNKNOWN end, at an existing place chosen by id, NOT ticked
  f = nform(t);
  setF(t, f, "date", "1980 to ?"); setF(t, f, "place", "existing:pl-a"); keep(t, f);
  check("eight changes pending on Homes", dirty(t) === 8 && !formError(t), formError(t) + " " + dirty(t));

  /* ── unions and separations ───────────────────────────────────── */
  topic(t, "partners");
  check("the stored union has its own form", !!$(t, '[data-qv2-form="occ"][data-event="e-u1"]'), text(t).slice(0, 200));
  check("a three-person union names BOTH other participants, with a selector each",
    /Ana Cruz/.test($(t, '[data-qv2-occ="e-u3"]').textContent) && /Ben Cruz/.test($(t, '[data-qv2-occ="e-u3"]').textContent) &&
    oform(t, "e-u3").querySelectorAll('[data-f^="swap:"]').length === 2, $(t, '[data-qv2-occ="e-u3"]').textContent);
  // the add form follows the SELECTED kind: Separation never offers a Place
  f = nform(t); setF(t, f, "partner", "p-s"); setF(t, f, "occKind", "separation");
  f = nform(t);
  check("choosing Separation re-renders the form WITHOUT a Place control, keeping the partner chosen",
    !f.querySelector('[data-f="place"]') && f.querySelector('[data-f="partner"]').value === "p-s",
    f.innerHTML.slice(0, 300));
  setF(t, f, "occKind", "union"); f = nform(t);
  check("choosing Union offers the Place control again", !!f.querySelector('[data-f="place"]'), f.innerHTML.slice(0, 200));
  setF(t, f, "partner", "");
  setF(t, f, "date", "1980"); keep(t, f);
  n = dirty(t);
  check("a new union with no partner chosen is refused", /choose who/.test(formError(t)) && n === 8, formError(t));
  f = nform(t);
  setF(t, f, "occKind", "union"); f = nform(t);
  setF(t, f, "partner", "p-s"); setF(t, f, "date", "1961 to 1962"); keep(t, f);
  check("a range is refused as a union date", /one date, not a range/.test(formError(t)) && dirty(t) === 8, formError(t));
  // the separation — the SAME pair as the stored union
  f = nform(t); setF(t, f, "occKind", "separation"); f = nform(t);
  setF(t, f, "partner", "p-s"); setF(t, f, "date", "1975"); keep(t, f);
  // and a LATER union with the same pair
  f = nform(t); setF(t, f, "occKind", "union"); f = nform(t);
  setF(t, f, "partner", "p-s"); setF(t, f, "date", "1980"); setF(t, f, "place", "existing:pl-a"); keep(t, f);
  check("a separation and a second union with the same pair are both pending, as NEW occurrences",
    dirty(t) === 10 && edits(t).filter((e) => e.kind === "occ" && e.isNew && e.partnerId === "p-s").length === 2,
    formError(t) + " " + JSON.stringify(edits(t)));
  // an UNRELATED edit to the three-person union (its date)
  f = oform(t, "e-u3"); setF(t, f, "date", "2001"); keep(t, f);
  // "I was married three times" — the count is STATED
  answer(t, "person.reported_count.marriages", "3");
  check("the stated marriage count is its own answer, not computed from the unions", dirty(t) === 12 &&
    edits(t).some((e) => e.kind === "answer" && e.concept === "person.reported_count.marriages" && e.value === 3),
    JSON.stringify(edits(t)));

  /* ── Save 1 ───────────────────────────────────────────────────── */
  let n0 = t.log.length;
  click(t, need(t, '[data-qv2-action="save"]')); await settle();
  let p = patches(t, n0);
  facts.firstPatch = p.length ? p[0].body.changes : null;
  check("Save 1 is ONE PATCH, and the writer accepts it", p.length === 1 && p[0].status === 200,
    JSON.stringify(p.map((x) => [x.status, x.reply])).slice(0, 600));
  let ch = facts.firstPatch || [];
  const adds = ch.filter((c) => c.op === "add" && /^events\//.test(c.path));
  check("four NEW events: two homes, a separation, a union",
    JSON.stringify(adds.map((c) => c.value.type).sort()) === '["move","move","separation","union"]', JSON.stringify(adds));
  check("only the ticked new home carries current",
    adds.filter((c) => c.value.attributes && c.value.attributes.current === true).length === 1, JSON.stringify(adds));
  const newHome = adds.find((c) => c.value.attributes && c.value.attributes.current === true);
  check("the new home's kind is written in the SAME Save, on that new event",
    !!newHome && ch.some((c) => c.op === "add" && /^assertions\//.test(c.path) && c.value.conceptId === "event.residence.type" &&
      c.value.subjectId === newHome.path.split("/")[1] && c.value.value === "apartment"), JSON.stringify(ch).slice(0, 400));
  const sets = ch.filter((c) => c.op === "set" && /^events\//.test(c.path));
  const s2 = sets.find((c) => c.path === "events/e-h2"), s3 = sets.find((c) => c.path === "events/e-h3");
  const s5 = sets.find((c) => c.path === "events/e-h5");
  check("stored homes change by ONE set each on the SAME event, guarded by the previous value",
    sets.length === 4 && s2 && s2.value.place === "pl-b" && s2.expectedPrevious.place === "pl-a" &&
    s3 && !("attributes" in s3.value) && s3.expectedPrevious.attributes.current === true && s3.value.place === "pl-c",
    JSON.stringify(sets));
  check("an unrelated edit to a home with a co-resident keeps every participant and role exactly",
    s5 && JSON.stringify(s5.value.participants) === JSON.stringify(s5.expectedPrevious.participants) &&
    s5.value.participants.length === 2, JSON.stringify(s5));
  check("an unrelated DATE edit on the three-person union writes no set on the event (participants untouched)",
    !sets.some((c) => c.path === "events/e-u3") &&
    ch.some((c) => c.op === "add" && c.value.conceptId === "event.union.date" && c.value.subjectId === "e-u3"),
    JSON.stringify(ch.filter((c) => /e-u3/.test(JSON.stringify(c)))));
  check("nothing in Save 1 touches the stored union, a relationship or a story",
    !ch.some((c) => /e-u1|relationships\/|stories\//.test(c.path)), JSON.stringify(ch.map((c) => c.path)));
  const acc = ch.filter((c) => /^acceptances\//.test(c.path));
  check("the accepted period's acceptance moves to its correction, guarded by the id it replaces",
    acc.length === 1 && acc[0].path === "acceptances/event/e-h1/event.residence.period" && acc[0].expectedPrevious === "d-h1",
    JSON.stringify(acc));

  /* ── read back from the SERVER ────────────────────────────────── */
  topic(t, "narrator");
  const cur = ($(t, "[data-qv2-current-homes]") || {}).textContent || "";
  check("CURRENT homes are exactly the ones said to be — several may be; never an unknown end or an unticked one",
    /1990 to present/.test(cur) && /1985 to present/.test(cur) && /1950 to 1955/.test(cur) &&
    !/1980 to \?/.test(cur) && !/1970 to present/.test(cur) && !/1962/.test(cur), cur);
  topic(t, "homes");
  check("after Save the homes read back as eight separate homes",
    t.c.querySelectorAll('[data-qv2-form="occ"]').length === 8, t.c.querySelectorAll('[data-qv2-form="occ"]').length);
  const ty = $(t, '[data-qv2-answer="event:e-h1:event.residence.type"]');
  check("after Save the kind of home reads back", ty && ty.value === "farmhouse", ty && ty.value);
  topic(t, "partners");
  check("after Save: five union / separation occurrences, each its own",
    t.c.querySelectorAll("[data-qv2-occ]").length === 5, text(t).slice(0, 400));
  const mc = $(t, '[data-qv2-answer$=":person.reported_count.marriages"]');
  check("after Save the stated marriage count reads back as 3", mc && mc.value === "3", mc && mc.value);

  /* ── Save 2: correcting who took part ─────────────────────────── */
  f = oform(t, "e-u3"); setF(t, f, "swap:p-a2", "p-b2"); keep(t, f);
  check("correcting a participant TO someone already in the occurrence is refused; nothing pending",
    /already in this union/.test(formError(t)) && dirty(t) === 0, formError(t) + " dirty=" + dirty(t));
  f = oform(t, "e-u3"); setF(t, f, "swap:p-a2", "p-c2"); keep(t, f);
  f = oform(t, "e-u2"); setF(t, f, "swap:p-alex", "p-t"); keep(t, f);
  check("two corrections pending", dirty(t) === 2 && !formError(t), formError(t) + " " + dirty(t));
  n0 = t.log.length;
  click(t, need(t, '[data-qv2-action="save"]')); await settle();
  p = patches(t, n0);
  facts.secondPatch = p.length ? p[0].body.changes : null;
  check("Save 2 is ONE PATCH, and the writer accepts it", p.length === 1 && p[0].status === 200,
    JSON.stringify(p.map((x) => [x.status, x.reply])).slice(0, 600));
  ch = facts.secondPatch || [];
  const u3 = ch.find((c) => c.path === "events/e-u3"), u2 = ch.find((c) => c.path === "events/e-u2");
  check("the three-person union: ONE set on the same event; only the corrected participant changed, roles kept",
    u3 && u3.op === "set" && JSON.stringify(u3.value.participants) ===
      JSON.stringify(u3.expectedPrevious.participants.map((x) => x.person === "p-a2" ? { person: "p-c2", role: x.role } : x)),
    JSON.stringify(u3));
  const rd = ch.find((c) => c.path === "relationships/r-d");
  check("the relationship DERIVED from the corrected union follows it in the same Save, guarded, nothing else changed",
    u2 && rd && rd.op === "set" && rd.expectedPrevious.subjectPersonId === "p-alex" && rd.value.subjectPersonId === "p-t" &&
    JSON.stringify(Object.assign({}, rd.value, { subjectPersonId: "p-alex" })) === JSON.stringify(rd.expectedPrevious),
    JSON.stringify(rd));
  check("the STATED relationship with the old participant is not touched",
    !ch.some((c) => c.path === "relationships/r-alex"), JSON.stringify(ch.map((c) => c.path)));
  topic(t, "partners");
  check("after Save 2 the union reads back with the corrected person, under the same event",
    /Taylor Reed/.test(($(t, '[data-qv2-occ="e-u2"]') || {}).textContent || "") &&
    /Ben Cruz/.test($(t, '[data-qv2-occ="e-u3"]').textContent) && /Cole Park/.test($(t, '[data-qv2-occ="e-u3"]').textContent),
    ($(t, '[data-qv2-occ="e-u2"]') || {}).textContent);

  process.stdout.write(JSON.stringify({ checks, facts }));
})().catch((e) => { process.stdout.write(JSON.stringify({ checks, facts, error: String(e && e.stack || e) })); })
  .finally(() => { BR.kill(); });
