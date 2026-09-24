/* Bio Builder consolidation — DOM harness (Batch C-2b).

   REAL: the #bioBuilderPopover and WO-13 review markup cut out of
   ui/hornelore1.0.html, and the shipped scripts loaded in the page's own
   order (state, api, the bio-builder modules, the authority guard, V2, the
   review surfaces). Driven by clicks on the rendered DOM; asserted on what
   the page shows and on EVERY request it makes.

   A FAKE SERVER answers reads with fixture values (a narrator named in the
   Life Record with one relative, a legacy questionnaire WITH content, one Lori
   suggestion). The
   legacy document has content on purpose: that is the condition under which
   the old Family Tree path sent `PUT /api/bio-builder/questionnaire`, so the
   no-legacy-write checks can fail.

   Prints {checks:[{name, ok, why}]} as JSON. Run by tests/test_bb_consolidation.py. */
"use strict";
const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

const ROOT = process.env.BB_HARNESS_ROOT || path.resolve(__dirname, "..");   // mutation runs point this at a copy
const HTML = fs.readFileSync(path.join(ROOT, "ui", "hornelore1.0.html"), "utf8");
const A = "narrator-a-fictional", B = "narrator-b-fictional", C = "narrator-c-unnamed";

function cut(startMarker, tag) {   // the element that starts at `startMarker`, balanced by `tag`
  const i = HTML.indexOf(startMarker);
  if (i < 0) throw new Error("marker not found in hornelore1.0.html: " + startMarker);
  let depth = 0, j = i;
  const re = new RegExp("<(/?)" + tag + "\\b", "g");
  re.lastIndex = i;
  let m;
  while ((m = re.exec(HTML))) {
    depth += m[1] ? -1 : 1;
    if (depth === 0) { j = HTML.indexOf(">", m.index) + 1; break; }
  }
  return HTML.slice(i, j);
}
const POPOVER = cut('<div id="bioBuilderPopover"', "div");
const WO13 = cut('<button id="wo13PromoteBtn"', "button");
const SHELL_INTAKE = cut('<button type="button" id="lvShellTabIntake"', "button");

const SCRIPTS = ["state.js", "api.js", "bio-builder-core.js", "projection-map.js", "projection-sync.js",
  "bio-builder-questionnaire.js", "bio-builder-sources.js", "bio-builder-candidates.js",
  "bio-builder-qc-pipeline.js", "bio-builder-graph.js", "bio-builder-family-tree.js",
  "bio-builder-life-threads.js", "life-record-authority.js", "questionnaire-v2-model.js",
  "questionnaire-v2.js", "bio-builder.js", "wo13-review.js", "bio-review.js", "shadow-review.js",
  "suggestion-review.js", "conflict-console.js"];

const checks = [];
const check = (name, ok, why) => checks.push({ name, ok: !!ok, why: ok ? "" : String(why) });
const tick = (ms) => new Promise((r) => setTimeout(r, ms || 0));
const settle = async () => { for (let i = 0; i < 30; i++) await tick(5); };

function record(pid, name, revision) {
  return { narrator_id: pid, narrator_person_id: pid, revision, schema_version: 1,
    people: [{ id: pid, names: [{ id: pid + "-name", fullText: name, kind: "current" }], preferredNameRef: pid + "-name" }],
    events: [], relationships: [], stories: [], places: [], animals: [], reportedCounts: {}, _storyCandidates: [] };
}

function boot(opts) {
  opts = opts || {};
  const dom = new JSDOM("<!doctype html><body>" + POPOVER + "<div>" + WO13 + SHELL_INTAKE + "</div></body>",
    { url: "http://localhost/", runScripts: "dangerously",
      virtualConsole: new VirtualConsole() });   // inline onclick="" handlers need "dangerously"; page logs stay off stdout
  const w = dom.window;
  const log = [];
  w.fetch = (url, o) => {
    const method = (o && o.method) || "GET";
    const u = String(url);
    log.push({ method, url: u, body: o && o.body ? String(o.body).slice(0, 300) : null });
    let body = {};
    let m;
    if ((m = u.match(/\/api\/life-record\/([^/?]+)$/))) {
      body = record(decodeURIComponent(m[1]), m[1] === A ? "Maren Holt (fictional)" : "Owen Marsh (fictional)", 2);
      if (m[1] === C) { body.people = []; body.revision = 0; }   // in the people table, nothing in the Life Record
      if (m[1] === A) {                                           // one relative, so Family has someone to derive
        body.people.push({ id: "p-astrid", names: [{ id: "n-astrid", fullText: "Astrid Holt", kind: "current" }] });
        body.relationships.push({ id: "r-astrid", subjectPersonId: "p-astrid", otherPersonId: A, kind: "parent_of",
                                  basis: "stated", qualifiers: ["adoptive"] });
      }
    } else if (u.indexOf("/api/bio-builder/questionnaire") !== -1) {
      body = { questionnaire: { personal: { fullName: "Maren Holt", placeOfBirth: "Tromsø" } }, _meta: {}, source: "ui_save", version: 3 };
    } else if (u.indexOf("/api/graph/") !== -1) {
      body = { narrator_id: A, revision: 0, persons: [], relationships: [] };
    } else if (u.indexOf("/suggestion") !== -1 && method === "GET") {
      body = { suggestions: [{ suggestion_id: "sug-1", fieldPath: "personal.placeOfBirth", value: "Bergen",
        confidence: 0.8, source: "projection_sync", repeats: 1, turnId: "t1" }] };
    } else if (u.indexOf("/api/interview/projection") !== -1 && method === "GET") {
      body = { projection: { fields: {}, pendingSuggestions: [{ suggestion_id: "sug-1", fieldPath: "personal.placeOfBirth",
        value: "Bergen", confidence: 0.8, turnId: "t1" }] }, version: 1 };
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body), text: () => Promise.resolve(JSON.stringify(body)) });
  };
  w.alert = () => {}; w.confirm = () => true; w.prompt = () => null;
  if (!w.HTMLElement.prototype.showPopover) {
    w.HTMLElement.prototype.showPopover = function () {}; w.HTMLElement.prototype.hidePopover = function () {};
  }
  // The operator has the popover open: render() returns early otherwise, and
  // jsdom implements neither :popover-open nor showPopover. The page's own
  // check accepts the `open` attribute.
  w.document.getElementById("bioBuilderPopover").setAttribute("open", "");
  const skip = opts.skip || [];
  for (const f of SCRIPTS) {
    if (skip.indexOf(f) !== -1) continue;
    // A real <script> element, as the page loads them: top-level `const API`
    // and friends must be shared across files. (window.eval does NOT share
    // lexical globals in jsdom — the first version of this harness ran with
    // API undefined, so every module that guards on it silently did nothing.)
    const el = w.document.createElement("script");
    el.textContent = fs.readFileSync(path.join(ROOT, "ui", "js", f), "utf8") + "\n//# sourceURL=" + f;
    w.document.body.appendChild(el);
  }
  if (w.eval("typeof API") !== "object" || w.eval("typeof state") !== "object")
    throw new Error("page globals not shared: API=" + w.eval("typeof API") + " state=" + w.eval("typeof state"));
  const t = {
    w, log, doc: w.document,
    writes: () => log.filter((r) => r.method !== "GET"),
    $: (s) => w.document.querySelector(s), $$: (s) => Array.from(w.document.querySelectorAll(s)),
    storageKeys: () => { const k = []; for (let i = 0; i < w.localStorage.length; i++) k.push(w.localStorage.key(i)); return k; },
  };
  return t;
}

async function openFor(t, pid) {
  t.w.eval("state.person_id = " + JSON.stringify(pid));
  const BB = t.w.LorevoxBioBuilder;
  if (BB.onNarratorSwitch) BB.onNarratorSwitch(pid);
  await settle();
  BB.render();
  await settle();
}
const clickTab = async (t, tab) => {
  t.w.LorevoxBioBuilder._switchTab(tab); await settle();
};

(async function run() {
  const t = boot();
  // An EARLIER Family Tree draft already in this browser (C-2b kept them).
  // C-3: it must be neither promoted into the Life Record nor shown as family.
  const GHOST = JSON.stringify({ v: 1, d: { nodes: [{ id: "ft-ghost", role: "sibling", displayName: "Ghost Relative" }], edges: [] } });
  t.w.localStorage.setItem("lorevox_ft_draft_" + A, GHOST);
  await openFor(t, A);

  /* 1 — navigation */
  const tabs = t.$$("#bioBuilderPopover .bb-tabs [role=tab]").map((b) => b.textContent.trim());
  check("Bio Builder shows exactly five areas", JSON.stringify(tabs) ===
    JSON.stringify(["Questionnaire", "Sources & Notes", "Review", "Family", "⋯ Legacy"]), JSON.stringify(tabs));
  check("no Life Threads, no Reset Identity in Bio Builder",
    !/Life Threads/.test(t.$("#bioBuilderPopover").textContent) && !t.$("#bbResetIdentityBtn"),
    t.$("#bioBuilderPopover .bb-header").textContent.slice(0, 200));
  check("Operator Intake is gone from the shell navigation", t.$("#lvShellTabIntake").hidden, "not hidden");
  t.w.LorevoxBioBuilder._switchTab("lifeThreads"); await settle();
  check("the retired Life Threads name cannot open Life Threads",
    t.$("#bbTabQuestionnaire").classList.contains("bb-tab-active") && !/Life Threads/i.test(t.$("#bbTabContent").textContent),
    t.$("#bbTabContent").textContent.slice(0, 120));

  /* 2 — header from the Life Record */
  await settle();
  const sub = t.$("#bbSubtitle").textContent;
  check("header names the narrator from the Life Record, with its revision, never an id",
    sub === "Maren Holt (fictional) · Life Record revision 2" && sub.indexOf(A) === -1, sub);

  /* 3 — every area and every review section: reads only */
  const before = t.writes().length;
  const qqBefore = t.storageKeys().filter((k) => k.indexOf("lorevox_qq_draft_") === 0).length;
  for (const tab of ["questionnaire", "sourcesNotes", "review", "familyTree", "legacy"]) await clickTab(t, tab);
  await clickTab(t, "review");
  for (const sec of ["candidates", "suggestions", "shadowReview", "conflicts"]) {
    const b = t.$('[data-review-section="' + sec + '"]'); if (b) b.dispatchEvent(new t.w.MouseEvent("click", { bubbles: true }));
    await settle();
  }
  check("opening every area and review section writes nothing",
    t.writes().length === before, JSON.stringify(t.writes().slice(before)));

  /* 4 — each area says what it is */
  await clickTab(t, "sourcesNotes");
  const sn = t.$("#bbTabContent");
  check("Sources & Notes is labelled DRAFT and says nothing here is in the Life Record",
    t.$('[data-bb-status="draft"]') && /not part of the Life Record/.test(sn.textContent), sn.textContent.slice(0, 200));
  check("no 'Save Note' / 'Add Fact' — staging words only",
    !/Save Note|Add Fact/.test(sn.innerHTML) && /Stage note/.test(sn.innerHTML) && /Stage fact/.test(sn.innerHTML),
    (sn.innerHTML.match(/>[^<]*(Note|Fact)[^<]*</g) || []).join(" | "));
  await clickTab(t, "review");
  check("candidate approval is not presented as saved biography",
    !/structured biography/i.test(t.$("#bbTabContent").innerHTML), "found 'structured biography'");
  await clickTab(t, "legacy");
  const lg = t.$("#bbTabContent");
  check("Legacy: 'Earlier Questionnaire Answers', READ ONLY · LEGACY, and no control that could change them",
    /Earlier Questionnaire Answers/.test(lg.textContent) && /READ ONLY · LEGACY/.test(lg.textContent) &&
    lg.querySelectorAll("input, textarea, select, button").length === 0, lg.innerHTML.slice(0, 200));
  await clickTab(t, "familyTree");
  const fam = t.$("#bbTabContent");
  check("Family is DERIVED FROM THE LIFE RECORD and shows the record's people (C-3)",
    /DERIVED FROM THE LIFE RECORD/.test(fam.textContent) && /Astrid Holt/.test(fam.textContent) &&
    /revision 2/.test(fam.textContent), fam.textContent.slice(0, 300));
  check("...with no family editor: no Add / Edit / Connect / Seed / Delete, only 'Edit in Questionnaire'",
    fam.querySelectorAll("input, textarea, select").length === 0 &&
    t.$$("#bbTabContent button").map((b) => b.textContent.trim()).join("|") === "Edit in Questionnaire",
    t.$$("#bbTabContent button").map((b) => b.textContent.trim()).join("|"));
  check("an earlier Family Tree draft is neither shown on Family nor sent anywhere — and it is kept",
    !/Ghost Relative/.test(fam.textContent) && !t.log.some((r) => /Ghost Relative/.test(r.body || "")) &&
    t.w.localStorage.getItem("lorevox_ft_draft_" + A) !== null, fam.textContent.slice(0, 200));
  check("...and its old handlers are no longer exported",
    ["_ftAddNode", "_ftSaveNode", "_ftAddEdge", "_ftSaveEdge", "_ftDeleteNode", "_ftSeedFromProfile",
     "_ftSeedFromQuestionnaire", "_ftSeedFromCandidates", "_ltAddNode", "_ltSeedThemes"]
      .every((k) => t.w.LorevoxBioBuilder[k] === undefined), "still exported");
  const editBtn = t.$("#bbTabContent [data-qv2-family-edit]");
  if (editBtn) editBtn.dispatchEvent(new t.w.MouseEvent("click", { bubbles: true }));
  await settle();
  check("'Edit in Questionnaire' opens the Questionnaire on Family and caregivers",
    t.$("#bbTabQuestionnaire").classList.contains("bb-tab-active") &&
    !!t.$('#bbTabContent [data-qv2-panel="family"]'), (t.$("#bbTabContent [data-qv2-panel]") || {}).outerHTML);

  /* 5 — the earlier Family Tree code is kept but unreachable. Its persistence
         seam is still pinned (C-2b), driven through the module itself: local
         draft only, never the old questionnaire PUT. The legacy document HAS
         content, the condition the old path fired on. */
  const FT = t.w.LorevoxBioBuilderModules.familyTree;
  const w0 = t.writes().length;
  FT._ftAddNode("other"); await settle();
  const nameIn = t.$("#ftEditName");
  if (nameIn) nameIn.value = "Ada Holt";
  const nodeId = (t.w.state.bioBuilder.familyTreeDraftsByPerson[A].nodes.slice(-1)[0] || {}).id;
  nodeId && FT._ftSaveNode(nodeId); await settle();
  check("a Family Tree add-and-save really ran (module)", !!(nameIn && nodeId) &&
    t.w.state.bioBuilder.familyTreeDraftsByPerson[A].nodes.some((n) => n.displayName === "Ada Holt"), "did not run");
  check("...and sent no request at all (no PUT /api/bio-builder/questionnaire)",
    t.writes().length === w0, JSON.stringify(t.writes().slice(w0)));
  nodeId && FT._ftAddEdge(nodeId); await settle();
  nodeId && FT._ftSaveEdge && FT._ftSaveEdge(nodeId); await settle();
  FT._ftSeedFromQuestionnaire(); await settle();
  FT._ftSeedFromProfile(); await settle();
  nodeId && FT._ftDeleteNode(nodeId, true); await settle();
  check("Family Connect, Seed (questionnaire/profile) and Delete send no request either",
    !!nodeId && t.writes().length === w0, JSON.stringify({ nodeId, writes: t.writes().slice(w0) }));
  check("...the draft stayed in this browser",
    t.storageKeys().indexOf("lorevox_ft_draft_" + A) !== -1, JSON.stringify(t.storageKeys()));

  /* 6 — Review actions that wrote the earlier system are held */
  await clickTab(t, "review");
  const sg = t.$('[data-review-section="suggestions"]'); if (sg) sg.dispatchEvent(new t.w.MouseEvent("click", { bubbles: true }));
  await settle();
  const pane = t.$("#bbTabContent");
  check("Lori's suggestion is listed with no Accept, a held note, and Decline kept",
    pane.querySelector("[data-accept-held]") && !pane.querySelector("[data-accept]") && pane.querySelector("[data-decline]"),
    pane.innerHTML.replace(/<div class="bb-status-banner[\s\S]*?<\/div>/, "").slice(0, 900));
  const declineBtn = pane.querySelector("[data-decline]");
  const wD = t.writes().length;
  if (declineBtn) declineBtn.dispatchEvent(new t.w.MouseEvent("click", { bubbles: true }));
  await settle();
  check("Decline still works: it posts the review decision",
    t.writes().slice(wD).some((r) => r.method === "POST" && /\/suggestion\/sug-1\/decline$/.test(r.url)),
    JSON.stringify(t.writes().slice(wD)));
  const projected = [];
  t.w.LorevoxProjectionSync = { projectValue: function () { projected.push([].slice.call(arguments)); } };
  t.w.HorneloreShadowReview._getState().conflicts.push({ id: "c1", claimId: "x", fieldPath: "personal.placeOfBirth",
    proposedValue: "Bergen", existingValue: "Tromsø", sourceType: "note" });
  const CC = t.w.HorneloreConflictConsole;
  const ccs = CC._ensureState();
  ccs.resolutions.c1 = { action: "replace" };
  const w1 = t.writes().length;
  await CC._commitConflictResolutions(CC._getConflicts());
  await settle();
  check("Conflicts → Replace is held: no projection write, no request, and the conflict is not closed",
    projected.length === 0 && t.writes().length === w1 && ccs.committed.indexOf("c1") === -1 &&
    CC._getConflicts().some((c) => c.id === "c1"),
    JSON.stringify({ projected, writes: t.writes().slice(w1), committed: ccs.committed }));
  t.w.HorneloreShadowReview._getState().conflicts.push({ id: "c2", claimId: "y", fieldPath: "personal.placeOfBirth",
    proposedValue: "Oslo", existingValue: "Tromsø", sourceType: "note" });
  ccs.resolutions.c2 = { action: "keep" };
  await CC._commitConflictResolutions(CC._getConflicts());
  await settle();
  check("Conflicts → Keep current still resolves (review state only), while the held Replace stays open",
    ccs.committed.indexOf("c2") !== -1 && ccs.committed.indexOf("c1") === -1 && projected.length === 0,
    JSON.stringify({ committed: ccs.committed, projected }));
  const SR = t.w.HorneloreShadowReview;
  const srs = SR._ensureState();
  const srcs = [{ id: "s1", claims: [{ id: "k1", fieldPath: "personal.birthOrder", displayValue: "first", sourceType: "note" }] }];
  srs.resolutions.k1 = "correct";
  srs.corrections.k1 = { value: "second", note: "" };
  const wS = t.writes().length, pS = projected.length;
  await SR._commitResolutions(srcs);
  await settle();
  check("Source claims → Correct is held: no projection write, no request, and the claim is not closed",
    projected.length === pS && t.writes().length === wS && srs.committed.indexOf("k1") === -1,
    JSON.stringify({ projected: projected.slice(pS), writes: t.writes().slice(wS), committed: srs.committed }));
  srs.resolutions.k2 = "reject";
  srcs[0].claims.push({ id: "k2", displayValue: "noise", sourceType: "note" });
  await SR._commitResolutions(srcs);
  await settle();
  check("Source claims → Reject still resolves",
    srs.committed.indexOf("k2") !== -1 && srs.committed.indexOf("k1") === -1, JSON.stringify(srs.committed));
  const w2 = t.writes().length;
  const pr = await t.w.wo13PromoteApproved(A);
  check("WO-13 'Promote approved' is held and its button disabled",
    pr && pr.held && t.writes().length === w2 && t.$("#wo13PromoteBtn").disabled,
    JSON.stringify(pr) + " disabled=" + t.$("#wo13PromoteBtn").disabled);
  check("the earlier editor's save/add handlers are not exported",
    !t.w.LorevoxBioBuilder._saveSection && !t.w.LorevoxBioBuilder._addRepeatEntry, "still exported");

  /* 6b — old tab names land in the new areas; none reopens a retired surface */
  const BBns = t.w.LorevoxBioBuilder;
  const where = () => ({ tab: (t.$(".bb-tabs .bb-tab-active") || {}).id,
    sec: (t.$("[data-review-section].bb-tab-active") || {}).getAttribute ? t.$("[data-review-section].bb-tab-active").getAttribute("data-review-section") : null });
  const routes = { shadowReview: ["bbTabReview", "shadowReview"], conflicts: ["bbTabReview", "conflicts"],
    suggestions: ["bbTabReview", "suggestions"], candidates: ["bbTabReview", "candidates"],
    capture: ["bbTabSourcesNotes", null], sources: ["bbTabSourcesNotes", null],
    earlierAnswers: ["bbTabLegacy", null], lifeThreads: ["bbTabQuestionnaire", null] };
  const bad = [];
  for (const [name, [tab, sec]] of Object.entries(routes)) {
    BBns._switchTab(name); await settle();
    const got = where();
    if (got.tab !== tab || (sec && got.sec !== sec)) bad.push(name + "→" + JSON.stringify(got));
  }
  check("every old tab name routes to its new area and review section (Life Threads to Questionnaire)",
    bad.length === 0, bad.join("; "));
  BBns._switchTab("questionnaire"); await settle();
  check("Questionnaire opens the Life Record editor, not the earlier one",
    !!t.$("#bbTabContent [data-qv2-state], #bbTabContent .qv2-shell, #bbTabContent [data-qv2-topic]") &&
    !t.w.LorevoxBioBuilder._openSection, t.$("#bbTabContent").innerHTML.slice(0, 200));
  const subBefore = t.$("#bbSubtitle").textContent;
  t.w.dispatchEvent(new t.w.CustomEvent("lorevox:life-record-shown",
    { detail: { pid: B, name: "Owen Marsh (fictional)", revision: 9 } }));
  await settle();
  check("a Life Record event for another narrator does not change the header",
    t.$("#bbSubtitle").textContent === subBefore && /Maren Holt/.test(subBefore), t.$("#bbSubtitle").textContent);

  /* 7 — narrator switch manufactures no old-questionnaire draft */
  const qqKeysBefore = t.storageKeys().filter((k) => k.indexOf("lorevox_qq_draft_") === 0);
  await openFor(t, B);
  await openFor(t, A);
  const qqKeysAfter = t.storageKeys().filter((k) => k.indexOf("lorevox_qq_draft_") === 0);
  check("switching narrators creates no old-questionnaire draft",
    JSON.stringify(qqKeysAfter) === JSON.stringify(qqKeysBefore) && qqBefore === qqKeysBefore.length,
    JSON.stringify({ before: qqKeysBefore, after: qqKeysAfter }));
  check("...and sends no write", t.writes().length === w2, JSON.stringify(t.writes().slice(w2)));
  t.w.eval("state.profile = state.profile || {}; state.profile.basics = { fullName: 'Profile Only Name', preferred: 'Profile Only Name' };");
  await openFor(t, C);
  await settle();
  const subC = t.$("#bbSubtitle").textContent;
  check("a narrator with no name in the Life Record: the header says so — no id, no earlier-profile name",
    /Name not yet in the Life Record/.test(subC) && subC.indexOf(C) === -1 && subC.indexOf(C.slice(0, 8)) === -1 &&
    !/Profile Only Name/.test(subC), subC);
  await openFor(t, A);

  /* 8 — the guard fails CLOSED when its module is missing: every protected
         write, driven at its write call, still changes nothing. */
  const t2 = boot({ skip: ["life-record-authority.js"] });
  check("(fail-closed boot really has no authority module)", t2.w.LorevoxAuthority === undefined, "module present");
  await openFor(t2, A);
  const proj2 = [];
  t2.w.LorevoxProjectionSync = { projectValue: function () { proj2.push([].slice.call(arguments)); } };
  const pr2 = await t2.w.wo13PromoteApproved(A);
  const SR2 = t2.w.HorneloreShadowReview, CC2 = t2.w.HorneloreConflictConsole;
  const srs2 = SR2._ensureState();
  srs2.resolutions.k1 = "correct_fu"; srs2.corrections.k1 = { value: "second", note: "" };
  await SR2._commitResolutions([{ id: "s", claims: [{ id: "k1", fieldPath: "personal.birthOrder", displayValue: "first" }] }]);
  srs2.conflicts.push({ id: "r1", claimId: "a", fieldPath: "personal.birthOrder", proposedValue: "x", existingValue: "y" },
                      { id: "m1", claimId: "b", fieldPath: "personal.birthOrder", proposedValue: "x", existingValue: "y" });
  const ccs2 = CC2._ensureState();
  ccs2.resolutions.r1 = { action: "replace" }; ccs2.resolutions.m1 = { action: "merge", mergedValue: "x / y" };
  await CC2._commitConflictResolutions(CC2._getConflicts());
  await clickTab(t2, "review");
  const sg2 = t2.$('[data-review-section="suggestions"]'); if (sg2) sg2.dispatchEvent(new t2.w.MouseEvent("click", { bubbles: true }));
  await settle();
  await settle();
  check("without life-record-authority.js: Promote, Correct + Follow-up, Replace, Merge write nothing and stay open; no Accept is offered",
    pr2 && pr2.held && proj2.length === 0 && t2.writes().length === 0 &&
    srs2.committed.indexOf("k1") === -1 && ccs2.committed.indexOf("r1") === -1 && ccs2.committed.indexOf("m1") === -1 &&
    !t2.$("#bbTabContent [data-accept]") && !!t2.$("#bbTabContent [data-accept-held]"),
    JSON.stringify({ pr2, proj2, writes: t2.writes(), sc: srs2.committed, cc: ccs2.committed }));

  /* 9 — stale authority phrases are gone from what the operator can see */
  const visible = t.$("#bioBuilderPopover").innerHTML;
  const cc = fs.readFileSync(path.join(ROOT, "ui", "js", "conflict-console.js"), "utf8");
  check("no 'Questionnaire always wins' / 'approved truth' / 'questionnaire truth' in Bio Builder or the conflict console",
    !/always wins|approved truth|questionnaire truth/i.test(visible + cc), "stale phrase present");

  const br = fs.readFileSync(path.join(ROOT, "ui", "js", "bio-review.js"), "utf8");
  check("candidate staging says session-only / not the Life Record (source wording)",
    !/structured biography/i.test(br) && /not part of the Life Record/.test(br) && /Mark merge/.test(br),
    "bio-review.js wording");
  check("no 'truth model' claim in the rendered Bio Builder", !/truth model/i.test(t.$("#bioBuilderPopover").textContent), "found");

  /* 10 — questionnaire_first: retired, not selectable, a stale value loads as oral_history.
     The three functions are cut out of the shipped app.js and run against the
     shipped radio markup. */
  const APP = fs.readFileSync(path.join(ROOT, "ui", "js", "app.js"), "utf8");
  const fnSrc = (sig) => { const i = APP.indexOf(sig); if (i < 0) throw new Error("not in app.js: " + sig);
    let d = 0, j = APP.indexOf("{", i); for (let k = j; k < APP.length; k++) { if (APP[k] === "{") d++; else if (APP[k] === "}") { d--; if (!d) return APP.slice(i, k + 1); } } };
  const constSrc = (name) => { const m = APP.match(new RegExp("const " + name + " = [\\s\\S]*?;\\n")); if (!m) throw new Error(name); return m[0]; };
  const radiosHtml = (HTML.match(/<input type="radio" name="lvSessionStyle"[\s\S]*?>/g) || []).join("");
  const q = new JSDOM("<!doctype html><body>" + radiosHtml + "</body>", { url: "http://localhost/", runScripts: "dangerously", virtualConsole: new VirtualConsole() });
  const qs = q.window.document.createElement("script");
  qs.textContent = "var state = {session:{}};" + constSrc("LV_SESSION_STYLE_KEY") + constSrc("LV_VALID_SESSION_STYLES") +
    fnSrc("function _lvQfLegacyOptIn") + fnSrc("function lvSetSessionStyle") + fnSrc("function _lvHydrateSessionStyle");
  q.window.localStorage.setItem("hornelore_session_style_v1", "questionnaire_first");
  q.window.document.body.appendChild(qs);
  q.window.eval("_lvHydrateSessionStyle()");
  const qf = q.window.document.querySelector('input[value="questionnaire_first"]');
  check("a stored questionnaire_first loads as oral_history, and storage is left as it was",
    q.window.eval("state.session.sessionStyle") === "oral_history" &&
    q.window.localStorage.getItem("hornelore_session_style_v1") === "questionnaire_first" && qf && !qf.checked,
    q.window.eval("state.session.sessionStyle"));
  q.window.eval("lvSetSessionStyle('questionnaire_first')");
  check("questionnaire_first cannot be selected: radio disabled, selection refused",
    qf.disabled && q.window.eval("state.session.sessionStyle") === "oral_history", "disabled=" + (qf && qf.disabled));
  q.window.localStorage.setItem("lv_qf_live_ownership", "1");
  q.window.eval("_lvHydrateSessionStyle()");
  check("...but the explicit testing opt-in still restores it",
    q.window.eval("state.session.sessionStyle") === "questionnaire_first" && !qf.disabled, q.window.eval("state.session.sessionStyle"));

  process.stdout.write(JSON.stringify({ checks }));
})().catch((e) => { process.stdout.write(JSON.stringify({ checks, error: String(e && e.stack || e) })); });
