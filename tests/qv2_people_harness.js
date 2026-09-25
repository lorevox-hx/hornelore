/* Questionnaire V2 — people and relationships (Batch C-3), DOM harness.

   REAL: ui/js/api.js, questionnaire-v2-model.js and questionnaire-v2.js in
   jsdom, driven through the rendered forms (typing, ticking, choosing,
   clicking). THE SERVER IS NOT A DOUBLE: every /api/life-record request goes
   to tests/qv2_bridge.py — the SHIPPED writer, rules and assembler on the real
   SQLite the Python test prepared. The database is then checked in Python.

   Driven by tests/test_qv2_people.py (env QV2_DB, QV2_PY, QV2_A).
   Prints {checks:[{name, ok, why}], facts:{…}} as JSON. */
"use strict";
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const { JSDOM, VirtualConsole } = require("jsdom");

const ROOT = process.env.QV2_ROOT || path.resolve(__dirname, "..");   // mutation runs point this at a copy
const SRC = ["ui/js/api.js", "ui/js/questionnaire-v2-model.js", "ui/js/questionnaire-v2.js"]
  .map((f) => fs.readFileSync(path.join(ROOT, f), "utf8"));
const DB = process.env.QV2_DB, PY = process.env.QV2_PY, A = process.env.QV2_A, B = process.env.QV2_B;

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

function openTab(sharedStorage) {
  const dom = new JSDOM('<!doctype html><div id="c"></div><div id="f"></div>',
    { url: "http://localhost/", runScripts: "outside-only", virtualConsole: new VirtualConsole() });
  const w = dom.window;
  const log = [];
  if (sharedStorage) Object.keys(sharedStorage).forEach((k) => w.localStorage.setItem(k, sharedStorage[k]));
  w.fetch = (url, opts) => {
    const method = (opts && opts.method) || "GET";
    log.push({ method, url: String(url), body: opts && opts.body ? JSON.parse(opts.body) : null });
    const m = String(url).match(/\/api\/life-record\/([^/?]+)$/);
    return (async () => {
      let status = 404, body = { detail: "not served by the harness" };
      if (m) ({ status, body } = await bridge(method, decodeURIComponent(m[1]), opts && opts.body));
      return { ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) };
    })();
  };
  SRC.forEach((s) => w.eval(s));
  const t = {
    w, log, c: w.document.getElementById("c"), f: w.document.getElementById("f"), V2: w.LorevoxQuestionnaireV2,
    writes() { return log.filter((r) => r.method !== "GET"); },
    storage() { const o = {}; for (let i = 0; i < w.localStorage.length; i++) { const k = w.localStorage.key(i); o[k] = w.localStorage.getItem(k); } return o; },
  };
  return t;
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
const dirty = (t) => Number($(t, "[data-qv2-dirty]").getAttribute("data-qv2-dirty"));
const text = (t) => $(t, ".qv2").textContent;

/* Fill the "Add someone" form on the current topic, as an operator would. */
function addSomeone(t, spec) {
  const form = $(t, '[data-qv2-form="person"]');
  const set = (f, v) => { const el = form.querySelector('[data-f="' + f + '"]'); el.value = v; };
  if (spec.person) set("person", spec.person);
  if (spec.name) set("fullText", spec.name);
  if (spec.role) set("role", spec.role);
  if (spec.describedAs) set("describedAs", spec.describedAs);
  if (spec.label) set("narratorLabel", spec.label);
  if (spec.lineage) set("lineage", spec.lineage);
  if (spec.living) set("lifeStatus", spec.living);
  if (spec.from) set("from", spec.from);
  if (spec.until) set("until", spec.until);
  (spec.q || []).forEach((q) => { form.querySelector('[data-f="q"][value="' + q + '"]').checked = true; });
  click(t, form.querySelector('[data-qv2-action="add-person"]'));
}
const pendingKinds = (t) => Object.values(t.V2._state().edits).map((e) => e.kind).sort();
const pendingPersonId = (t, name) => (Object.values(t.V2._state().edits)
  .find((e) => e.kind === "newperson" && e.fullText === name) || {}).personId;
const relCardFor = (t, name) => $$(t, "[data-qv2-rel]").find((c) => c.querySelector("strong").textContent === name);

(async function run() {
  /* 0 — C-3 follow-up: a draft written BEFORE C-3 (same draft version) has an
     answer edit with no newAssertionId. Hydration must assign it ONCE and
     persist it before any Save; every Save built from it uses that id. */
  {
    const oldDraft = { v: 1, pid: B, baseRevision: 1, provenance: "operator", edits: {
      ["person:" + B + ":person.birth.order"]: { kind: "answer", topic: "narrator", subjectType: "person",
        subjectId: B, concept: "person.birth.order", value: "the eldest",
        basis: { state: "blank", assertionId: null, value: null, status: null } } } };
    const key = "lorevox_qv2_draft_" + B;
    const o = openTab({ [key]: JSON.stringify(oldDraft) });
    o.V2.render(o.c, B); await settle();
    const stored = JSON.parse(o.storage()[key] || "null");
    const id = stored && Object.values(stored.edits)[0].newAssertionId;
    check("an old draft's missing assertion id is assigned at hydration and PERSISTED before any Save",
      !!id && /^qv2a-/.test(id) && o.writes().length === 0 && stored.baseRevision === 1 && stored.v === 1,
      JSON.stringify(stored));
    const b1 = o.V2._buildChanges(), b2 = o.V2._buildChanges();
    check("...every Save built from it uses that same id (no id minted at Save)",
      b1[0].path === "assertions/" + id && b2[0].path === "assertions/" + id, JSON.stringify([b1[0].path, b2[0].path]));
    const o2 = openTab(o.storage());                       // a second tab / reload reads the upgraded draft
    o2.V2.render(o2.c, B); await settle();
    check("...and a reload keeps it (the upgrade is not repeated with a new id)",
      o2.V2._buildChanges()[0].path === "assertions/" + id, o2.V2._buildChanges()[0].path);
    click(o, $(o, '[data-qv2-action="save"]')); await settle();
    const p = o.writes()[0];
    const again = await bridge("PATCH", B, JSON.stringify(p.body));
    check("...the Save lands under that id, and a retry of it is refused whole",
      p && p.body.changes[0].path === "assertions/" + id && again.status === 422 &&
      /already exists/.test(JSON.stringify(again.body)), JSON.stringify(again).slice(0, 200));
    facts.oldDraftId = id;
  }

  /* 0b — C-3 follow-up: a stored `child_of` (never written by the editor) is
     read in both directions. */
  {
    const M = openTab().w.LorevoxQuestionnaireV2Model;
    check("narrator child_of P reads as P the PARENT; P child_of narrator reads as P the CHILD",
      M.detailedRole({ subjectPersonId: "N", otherPersonId: "P", kind: "child_of" }, "N") === "parent" &&
      M.detailedRole({ subjectPersonId: "P", otherPersonId: "N", kind: "child_of" }, "N") === "child",
      [M.detailedRole({ subjectPersonId: "N", otherPersonId: "P", kind: "child_of" }, "N"),
       M.detailedRole({ subjectPersonId: "P", otherPersonId: "N", kind: "child_of" }, "N")].join());
    const r = openTab();
    r.w.fetch = () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({
      narrator_id: "N", narrator_person_id: "N", revision: 5, events: [], stories: [], places: [], animals: [],
      people: [{ id: "N", names: [{ id: "n", fullText: "Narrator", kind: "current" }] },
               { id: "M", names: [{ id: "m", fullText: "Mother Older", kind: "current" }] },
               { id: "K", names: [{ id: "k", fullText: "Kid Older", kind: "current" }] }],
      relationships: [{ id: "r1", subjectPersonId: "N", otherPersonId: "M", kind: "child_of", basis: "stated" },
                      { id: "r2", subjectPersonId: "K", otherPersonId: "N", kind: "child_of", basis: "stated" }] }) });
    r.V2.renderFamilyView(r.f, "N"); await settle();
    const txt = r.f.innerHTML;
    check("Family shows an old child_of record under Parents and under Children, the right way round",
      /Parents<\/h4><ul><li>Mother Older/.test(txt) && /Children<\/h4><ul><li>Kid Older/.test(txt), r.f.textContent.slice(0, 200));
    // ...and the editor treats it as the parent_of it would write: adding the
    // same mother as a parent again is caught on the form, not refused at Save.
    r.V2.render(r.c, "N"); await settle();
    topic(r, "family");
    check("the editor lists the old child_of mother as a Parent", !!relCardFor(r, "Mother Older") &&
      /Parent/.test(relCardFor(r, "Mother Older").textContent), text(r).slice(0, 300));
    addSomeone(r, { person: "M", role: "parent" });
    check("...and adding her again as a parent is recognised as already recorded",
      /already recorded/.test(($(r, "[data-qv2-form-error]") || {}).textContent || "") &&
      Object.keys(r.V2._state().edits).length === 0, ($(r, "[data-qv2-form-error]") || {}).textContent);
  }

  const t = openTab();
  t.V2.render(t.c, A); await settle();
  const opened = t.log.length;

  /* 1 — nothing is preselected, and the form refuses what it cannot honestly store */
  topic(t, "family");
  const form = $(t, '[data-qv2-form="person"]');
  check("the add form preselects no relationship, no qualifier, no side, no life status",
    form.querySelector('[data-f="role"]').value === "" && form.querySelector('[data-f="lineage"]').value === "" &&
    form.querySelector('[data-f="lifeStatus"]').value === "" &&
    Array.from(form.querySelectorAll('[data-f="q"]')).every((x) => !x.checked), form.innerHTML.slice(0, 200));
  addSomeone(t, { name: "Astrid Lund" });
  check("no relationship chosen → refused on the form, nothing pending",
    $(t, "[data-qv2-form-error]") && dirty(t) === 0, text(t).slice(0, 200));
  topic(t, "wider");
  addSomeone(t, { name: "Mrs. Pike", role: "other" });
  check("'Other' without a description → refused on the form", $(t, "[data-qv2-form-error]") && dirty(t) === 0,
    text(t).slice(0, 200));

  /* 2 — add people with the details a family actually has */
  topic(t, "family");
  addSomeone(t, { name: "Astrid Maj Lund", role: "parent", q: ["adoptive"], lineage: "maternal",
                  label: "Mor", living: "deceased", from: "1950" });
  addSomeone(t, { name: "Greta Lund", role: "grandparent", lineage: "maternal" });
  const greta = pendingPersonId(t, "Greta Lund");
  addSomeone(t, { person: greta, role: "caregiver" });
  check("the same person added as grandparent AND caregiver is ONE person with two relationships",
    Object.values(t.V2._state().edits).filter((e) => e.kind === "newperson" && e.fullText === "Greta Lund").length === 1 &&
    Object.values(t.V2._state().edits).filter((e) => e.kind === "newrel" && e.personId === greta).length === 2,
    JSON.stringify(pendingKinds(t)));
  addSomeone(t, { person: greta, role: "grandparent" });
  check("adding the same relationship again is refused on the form (the writer would refuse it too)",
    /already recorded/.test(($(t, "[data-qv2-form-error]") || {}).textContent || "") &&
    Object.values(t.V2._state().edits).filter((e) => e.kind === "newrel" && e.personId === greta).length === 2,
    ($(t, "[data-qv2-form-error]") || {}).textContent);
  addSomeone(t, { name: "Chidi Okafor", role: "sibling", q: ["half", "older"] });
  // two relatives with the SAME name are two people — told apart by id, never merged
  addSomeone(t, { name: "Erik Lund", role: "grandparent", lineage: "paternal" });
  addSomeone(t, { name: "Erik Lund", role: "grandparent", lineage: "maternal" });
  const eriks = Object.values(t.V2._state().edits).filter((e) => e.kind === "newperson" && e.fullText === "Erik Lund");
  check("two relatives with the same name are two people with two ids",
    eriks.length === 2 && eriks[0].personId !== eriks[1].personId, JSON.stringify(eriks));
  const sib = $(t, '[data-qv2-answer$=":person.reported_count.siblings"]');
  sib.value = "six"; change(t, sib);
  check("a count that is not a whole number is refused, not stored as text",
    /whole number/.test(text(t)) && !Object.keys(t.V2._state().edits).some((k) => /reported_count/.test(k)), text(t).slice(0, 200));
  $(t, '[data-qv2-answer$=":person.reported_count.siblings"]').value = "6";
  change(t, $(t, '[data-qv2-answer$=":person.reported_count.siblings"]'));

  topic(t, "partners");
  addSomeone(t, { name: "Tomas Berg", role: "spouse", q: ["former"], from: "1971", until: "about 1989" });
  addSomeone(t, { name: "Nils Berg", role: "child" });
  // a grandchild with no parent recorded in between — nothing is inferred to connect them
  addSomeone(t, { name: "Liv Berg", role: "grandchild" });
  // duplicate = EQUAL periods (the writer's rule): the same span again is refused …
  const tomasId = pendingPersonId(t, "Tomas Berg");
  const relsOf = (pid) => Object.values(t.V2._state().edits).filter((e) => e.kind === "newrel" && e.personId === pid);
  addSomeone(t, { person: tomasId, role: "spouse", from: "1971", until: "about 1989" });
  check("the same marriage with the same span is refused as already recorded",
    /already recorded/.test(($(t, "[data-qv2-form-error]") || {}).textContent || "") && relsOf(tomasId).length === 1,
    ($(t, "[data-qv2-form-error]") || {}).textContent);
  // … but a marriage with dates unknown beside a dated one is a second relationship (a remarriage)
  addSomeone(t, { person: tomasId, role: "spouse" });
  const second = relsOf(tomasId).find((e) => !e.value.period);
  check("a marriage with unknown dates beside a dated one is accepted as a second relationship",
    relsOf(tomasId).length === 2 && !!second && !$(t, "[data-qv2-form-error]"), JSON.stringify(relsOf(tomasId)));
  if (second) click(t, $(t, '[data-qv2-rel="' + second.relId + '"] [data-qv2-undo]'));
  check("...(undone again here; the writer side of this is pinned in the writer tests)", relsOf(tomasId).length === 1,
    relsOf(tomasId).length);
  topic(t, "wider");
  addSomeone(t, { name: "Mrs. Pike", role: "other", describedAs: "the neighbour who taught her to read" });

  /* an unsaved person can be undone, and takes their relationships with them */
  topic(t, "family");
  addSomeone(t, { name: "Someone Mistaken", role: "sibling" });
  const mistaken = pendingPersonId(t, "Someone Mistaken");
  const beforeUndo = dirty(t);
  const card = relCardFor(t, "Someone Mistaken");
  click(t, card.querySelector("[data-qv2-undo]"));
  check("undoing an unsaved person's only relationship undoes the person too — nobody left behind",
    dirty(t) === beforeUndo - 2 && !t.V2._state().edits["newperson:" + mistaken], dirty(t) + " vs " + beforeUndo);

  topic(t, "narrator");
  const nf = $(t, '[data-qv2-form="name"]');
  nf.querySelector('[data-f="fullText"]').value = "Ines Okafor";
  nf.querySelector('[data-f="nameKind"]').value = "former";
  click(t, nf.querySelector('[data-qv2-action="add-name"]'));
  const nv = $(t, '[data-qv2-form="name"]');
  nv.querySelector('[data-f="fullText"]').value = "Inès Okafor-Lund";
  nv.querySelector('[data-f="nameKind"]').value = "variant";
  click(t, nv.querySelector('[data-qv2-action="add-name"]'));
  const pf = $(t, '[data-qv2-form="pronoun"]');
  pf.querySelector('[data-f="pronoun"]').value = "she/her";
  click(t, pf.querySelector('[data-qv2-action="add-pronoun"]'));
  const prov = $(t, "[data-qv2-provenance]");
  prov.value = "narrator"; change(t, prov);

  check("all of that is local: no request beyond the opening GET", t.log.length === opened && t.writes().length === 0,
    JSON.stringify(t.log.map((r) => r.method)));
  const draft = JSON.parse(t.storage()["lorevox_qv2_draft_" + A] || "null");
  check("...kept in this narrator's draft, with the ids it will be saved under", draft &&
    Object.keys(draft.edits).some((k) => k === "newperson:" + greta) && draft.provenance === "narrator",
    Object.keys((draft || {}).edits || {}));

  /* a reload brings the unsaved people back with the SAME ids */
  const t2 = openTab(t.storage());
  t2.V2.render(t2.c, A); await settle();
  check("a reload restores the unsaved people with the same ids (no duplicate on the next Save)",
    pendingPersonId(t2, "Greta Lund") === greta && dirty(t2) === dirty(t), dirty(t2) + " vs " + dirty(t));

  /* a narrator switch with an unsaved structural draft: nothing written,
     nothing carried across, and the draft comes back with the same ids */
  const pendingBefore = dirty(t), writesBefore = t.writes().length;
  t.V2.render(t.c, B); await settle();
  check("switching narrators with unsaved people pending: B shows none of A's, nothing is written",
    dirty(t) === 0 && $(t, ".qv2-head strong").textContent === "Owen Marsh" && t.writes().length === writesBefore &&
    !/Greta Lund/.test(text(t)), $(t, ".qv2-head").textContent);
  t.V2.render(t.c, A); await settle();
  check("...and switching back restores A's unsaved people with the same ids",
    dirty(t) === pendingBefore && pendingPersonId(t, "Greta Lund") === greta, dirty(t) + " vs " + pendingBefore);
  // the provenance chosen before the switch came back with the draft
  check("...including the chosen provenance", $(t, "[data-qv2-provenance]").value === "narrator",
    $(t, "[data-qv2-provenance]").value);

  /* 3 — Save: ONE PATCH of writer operations, people before what refers to them */
  const n0 = t.log.length;
  click(t, $(t, '[data-qv2-action="save"]')); await settle();
  const sent = t.log.slice(n0), patch = sent.find((r) => r.method === "PATCH");
  facts.firstPatch = patch && patch.body;
  check("Save sends exactly one PATCH, then re-reads the record",
    sent.length === 2 && patch && sent[1].method === "GET", JSON.stringify(sent.map((r) => r.method)));
  const ch = (patch && patch.body.changes) || [];
  const firstRel = ch.findIndex((c) => c.path.startsWith("relationships/"));
  const lastPerson = ch.map((c) => /^people\/[^/]+$/.test(c.path)).lastIndexOf(true);
  check("...every person is added before any relationship that names them",
    firstRel > lastPerson && lastPerson >= 0, JSON.stringify(ch.map((c) => c.op + " " + c.path)));
  check("...only adds: nothing existing is overwritten, and no document is sent",
    ch.every((c) => c.op === "add") && !("questionnaire" in patch.body), JSON.stringify(ch.map((c) => c.op)));
  const relVal = (pid) => ch.filter((c) => c.path.startsWith("relationships/") && JSON.stringify(c.value).indexOf(pid) !== -1)
    .map((c) => c.value);
  const nils = (ch.find((c) => c.value && c.value.fullText === "Nils Berg") || { path: "" }).path.split("/")[1];
  check("...a child is stored as 'the narrator is parent_of the child' (direction, not a second kind)",
    relVal(nils).length === 1 && relVal(nils)[0].subjectPersonId === A && relVal(nils)[0].kind === "parent_of",
    JSON.stringify(relVal(nils)));
  /* a network-ambiguous retry: the SAME operations sent again (as a resend
     of the kept draft would) must not create a second mother or spouse */
  const again = await bridge("PATCH", A, JSON.stringify(patch.body));
  check("re-sending the same Save is refused whole — every id already exists; nothing is duplicated",
    again.status === 422 && /already exists/.test(JSON.stringify(again.body)), JSON.stringify(again).slice(0, 300));
  check("...because every id in it was minted before Save (people, names, relationships AND assertions)",
    ch.every((c) => c.op !== "add" || /\/(qv2[pnra]-[a-z0-9]+)$/.test(c.path)) &&
    ch.filter((c) => c.path.startsWith("assertions/")).every((c) =>
      JSON.stringify(t2.V2._state().edits).indexOf(c.path.split("/")[1]) !== -1),
    JSON.stringify(ch.map((c) => c.path)));
  check("the save landed: the new people are on screen from the SERVER, nothing pending",
    dirty(t) === 0 && $(t, '[data-qv2-msg="ok"]') && t.V2._state().baseRevision === 2, text(t).slice(0, 300));
  topic(t, "narrator");
  const names = $$(t, "[data-qv2-name]").map((i) => i.value);
  check("after the save every name of the narrator is on the editor, whole: current, former and variant",
    ["Ines Maribel Okafor-Lund", "Ines Okafor", "Inès Okafor-Lund"].every((x) => names.indexOf(x) !== -1),
    JSON.stringify(names));
  topic(t, "family");
  check("...Greta appears twice on Family (grandparent, and raised the narrator) as one name",
    $$(t, "[data-qv2-rel] strong").filter((s) => s.textContent === "Greta Lund").length === 2, text(t).slice(0, 400));

  /* 4 — change a saved relationship's details, a life status and a name */
  const stale = openTab(); stale.V2.render(stale.c, A); await settle();       // opened before the next save
  prov.value = "operator";
  change(t, $(t, "[data-qv2-provenance]"));
  $(t, "[data-qv2-provenance]").value = "operator"; change(t, $(t, "[data-qv2-provenance]"));
  click(t, relCardFor(t, "Astrid Maj Lund").querySelector('[data-qv2-action="open-rel"]'));
  const rf = $(t, '[data-qv2-form="rel"]');
  // typed and ticked as a person would: each field fires its own event
  const tickBox = (el, on) => { el.checked = on; change(t, el); };
  tickBox(rf.querySelector('[data-f="q"][value="adoptive"]'), false);
  tickBox(rf.querySelector('[data-f="q"][value="biological"]'), true);
  const lab = rf.querySelector('[data-f="narratorLabel"]');
  lab.value = "Mamma"; lab.dispatchEvent(new t.w.Event("input", { bubbles: true }));
  // …then a field that repaints the card. The half-made changes above must survive it.
  const ls = rf.querySelector('[data-qv2-answer$=":person.life_status"]');
  ls.value = "unknown"; change(t, ls);
  const nameBox = $(t, '[data-qv2-form="rel"] [data-qv2-name]');
  nameBox.value = "Astrid M. Lund"; change(t, nameBox);
  click(t, $(t, '[data-qv2-form="rel"] [data-qv2-action="keep-rel"]'));
  check("details kept as three pending edits: relationship, life status, name", dirty(t) === 3 &&
    JSON.stringify(pendingKinds(t)) === JSON.stringify(["answer", "nameedit", "reledit"]), JSON.stringify(pendingKinds(t)));
  const n1 = t.log.length;
  click(t, $(t, '[data-qv2-action="save"]')); await settle();
  const p2 = t.log.slice(n1).find((r) => r.method === "PATCH");
  facts.secondPatch = p2 && p2.body;
  const setRel = p2 && p2.body.changes.find((c) => c.op === "set" && c.path.startsWith("relationships/"));
  check("a relationship change is one `set` carrying exactly the value it replaces",
    setRel && JSON.stringify(setRel.expectedPrevious.qualifiers) === '["adoptive"]' &&
    JSON.stringify(setRel.value.qualifiers) === '["biological"]' && setRel.value.narratorLabel === "Mamma" &&
    setRel.value.kind === "parent_of" && setRel.value.subjectPersonId === setRel.expectedPrevious.subjectPersonId,
    JSON.stringify(setRel));
  check("...and it saved", t.V2._state().baseRevision === 3 && dirty(t) === 0, text(t).slice(0, 200));

  /* 5 — the stale tab changes the same relationship: a conflict, shown, draft kept */
  stale.V2.render(stale.c, A); topic(stale, "family");
  click(stale, relCardFor(stale, "Astrid Maj Lund").querySelector('[data-qv2-action="open-rel"]'));
  const sl = stale.c.querySelector('[data-qv2-form="rel"] [data-f="narratorLabel"]');
  sl.value = "Mother"; sl.dispatchEvent(new stale.w.Event("input", { bubbles: true }));
  click(stale, stale.c.querySelector('[data-qv2-form="rel"] [data-qv2-action="keep-rel"]'));
  const sn = stale.log.length;
  click(stale, stale.c.querySelector('[data-qv2-action="save"]')); await settle();
  check("a stale relationship edit is a 409 naming that relationship; nothing is resent; the edit is kept",
    stale.log.slice(sn).length === 1 && stale.c.querySelector("[data-qv2-conflict]") &&
    /relationships\//.test(stale.c.querySelector("[data-qv2-conflict]").textContent) && dirty(stale) === 1,
    stale.c.querySelector(".qv2").textContent.slice(0, 300));

  /* 6 — Family, derived: the saved record, read-only */
  const f = openTab();
  let edited = null;
  f.V2.renderFamilyView(f.f, A, (tp) => { edited = tp; }); await settle();
  const ft = f.f.textContent;
  check("Family is drawn from the record: parents, carers, siblings, spouses, children, others",
    /Astrid M\. Lund/.test(ft) && /Raised or cared for the narrator/.test(ft) && /Greta Lund/.test(ft) &&
    /Chidi Okafor/.test(ft) && /Tomas Berg/.test(ft) && /Nils Berg/.test(ft) && /Mrs\. Pike/.test(ft) &&
    /6 siblings \(as said\)/.test(ft), ft.slice(0, 500));
  check("...with nothing on it that can write", f.f.querySelectorAll("input, select, textarea").length === 0 &&
    f.writes().length === 0 && Array.from(f.f.querySelectorAll("button")).map((b) => b.textContent).join() === "Edit in Questionnaire",
    f.f.innerHTML.slice(0, 200));
  click(f, f.f.querySelector("[data-qv2-family-edit]"));
  check("...and 'Edit in Questionnaire' asks for the Family topic", edited === "family", String(edited));

  /* Family, A → B → A: a slow FIRST answer for A must not paint over the
     SECOND answer for A (the narrator's box exists again by then). Fetches
     are held and released in the worst order. */
  {
    const r = openTab();
    const held = [];
    r.w.fetch = (url) => new Promise((res, rej) => held.push({ url: String(url), res, rej }));
    const rec = (pid, name) => ({ narrator_id: pid, narrator_person_id: pid, revision: name === "SECOND" ? 7 : 1,
      people: [{ id: pid, names: [{ id: "n", fullText: "N", kind: "current" }] },
               { id: "p1", names: [{ id: "m", fullText: name + " Relative", kind: "current" }] }],
      relationships: [{ id: "r1", subjectPersonId: "p1", otherPersonId: pid, kind: "parent_of", basis: "stated" }],
      events: [], stories: [], places: [], animals: [] });
    const ok = (body) => ({ ok: true, status: 200, json: () => Promise.resolve(body) });
    r.V2.renderFamilyView(r.f, A);           // A1
    r.V2.renderFamilyView(r.f, B);           // B
    r.V2.renderFamilyView(r.f, A);           // A2
    held[2].res(ok(rec(A, "SECOND"))); await settle();
    held[1].res(ok(rec(B, "OTHER"))); await settle();
    held[0].res(ok(rec(A, "FIRST"))); await settle();
    const ft = r.f.textContent;
    check("Family A → B → A: the older answer for A does not repaint over the newer one",
      /SECOND Relative/.test(ft) && !/FIRST Relative/.test(ft) && !/OTHER Relative/.test(ft) && /revision 7/.test(ft),
      ft.slice(0, 200));
    // and a late FAILURE of an old request does not replace the newer view with an error
    r.V2.renderFamilyView(r.f, A);           // A3
    r.V2.renderFamilyView(r.f, A);           // A4
    held[4].res(ok(rec(A, "SECOND"))); await settle();
    held[3].rej(new Error("late failure")); await settle();
    check("...and an old request that fails late does not replace it with an error",
      /SECOND Relative/.test(r.f.textContent) && !/could not be read/.test(r.f.textContent), r.f.textContent.slice(0, 200));
  }

  /* the only writes of the whole run: PATCH /api/life-record — no legacy
     questionnaire PUT, no graph call, no profile or bio_facts write */
  const all = [t, t2, stale, f].reduce((acc, x) => acc.concat(x.writes()), []);
  check("every write in the run was a PATCH to the Life Record — nothing else was touched",
    all.length === 3 && all.every((r) => r.method === "PATCH" && /\/api\/life-record\/[^/]+$/.test(r.url)),
    JSON.stringify(all.map((r) => r.method + " " + r.url)));
  check("no inverse row is ever sent: one relationship per stated relationship",
    (facts.firstPatch.changes || []).filter((c) => c.path.startsWith("relationships/")).length ===
    Object.values(facts.firstPatch.changes).filter((c) => c.value && c.value.conceptId === "relationship.kind").length,
    "mismatch");
  facts.eriks = eriks.map((e) => e.personId);
  facts.greta = greta;
  process.stdout.write(JSON.stringify({ checks, facts }));
})().catch((e) => { process.stdout.write(JSON.stringify({ checks, facts, error: String(e && e.stack || e) })); })
  .finally(() => BR.stdin.end());
