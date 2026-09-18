/* Behavioural harness for the real Bio Builder save and restore paths.

   WO-BIO-BUILDER-SAVE-INTEGRITY-AUDIT-01.

   WHY THIS EXISTS

     test_questionnaire_save_outcome.js has 56 checks. Eleven execute code;
     forty-five read source text. None runs a save. It cannot express a
     SEQUENCE, and every defect that reached the operator on 17-18 September
     was a sequence:

       enter a mother, save, add a father, save  -> the father was discarded
       load, type, save                          -> refused, silently
       type, save while a GET is in flight       -> the edit was replaced

     BUG-BIO-QUESTIONNAIRE-SECOND-ENTRY-DROPPED-01 survived 45 source checks
     and two days of live testing. What caught it was the operator typing a
     name into a form and asking why it was gone.

   WHAT IS REAL HERE, AND WHAT IS NOT

     REAL: ui/js/bio-builder-core.js and ui/js/bio-builder-questionnaire.js,
     loaded unmodified and executed. The SECTIONS definitions. The renderer —
     the form under test is built by _renderSectionDetail, so the input ids
     come from the shipping renderer rather than from this file's assumptions
     about them. _saveSection, _addRepeatEntry, _restoreQuestionnaire,
     _persistDrafts and _persistQuestionnaire are the shipping functions.

     A TEST DOUBLE: the server. It records every payload it is given and
     answers however the test tells it to. Its merge mimics the contract of
     merge_whole_document (populated leaves applied as mutations, no
     removals) but it IS NOT that code, which is Python. Assertions about
     server-side merging belong in test_questionnaire_persistence_integrity.py
     and in the live walkthrough. What this harness is authoritative about is
     the BROWSER: what was rendered, what was collected, and what was sent.

     NOT PRESENT: the real network, the real database, Lori, the family tree.
     A green run here is not a claim that Bio Builder works. It is a claim
     that these sequences behave as intended.

   Requires jsdom (devDependency). If it is missing:  npm install
*/

"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..", "..");

let JSDOM;
try {
  ({ JSDOM } = require("jsdom"));
} catch (e) {
  console.error(
    "\n  jsdom is not installed, so the behavioural harness cannot run.\n" +
    "  This suite drives the real form; there is no source-text fallback,\n" +
    "  because a source-text fallback is what missed the defects it targets.\n\n" +
    "    npm install\n");
  process.exit(2);
}

/* ── the server double ────────────────────────────────────────────────── */

function makeServer() {
  const docs = Object.create(null);      // pid -> { doc, revision, history[] }
  const puts = [];                       // every payload, in order
  const gets = [];

  const srv = {
    puts, gets, docs,

    /* Response control. Each is consumed by the NEXT matching request unless
       `sticky`. Tests set these to make a save fail on purpose. */
    nextPutStatus: null,
    nextPutBody: null,
    putSticky: false,
    holdGet: null,       // a resolve fn parked here when getPaused is true
    getPaused: false,

    seed(pid, doc, revision) {
      docs[pid] = { doc: JSON.parse(JSON.stringify(doc)), revision: revision || 0, history: [] };
    },
    stored(pid) { return docs[pid] ? docs[pid].doc : null; },
    revision(pid) { return docs[pid] ? docs[pid].revision : 0; },
    history(pid) { return docs[pid] ? docs[pid].history : []; },
    lastPut() { return puts.length ? puts[puts.length - 1] : null; },
  };

  /* Populated leaves only — the same exclusion the Python flatten uses:
     "", null, [] and {} are not values. */
  function leaves(obj, prefix, out) {
    out = out || {};
    if (obj === null || obj === undefined) return out;
    if (Array.isArray(obj)) {
      obj.forEach((v, i) => leaves(v, prefix + "[" + i + "]", out));
      return out;
    }
    if (typeof obj === "object") {
      Object.keys(obj).forEach((k) => leaves(obj[k], prefix ? prefix + "." + k : k, out));
      return out;
    }
    if (obj === "" ) return out;
    out[prefix] = obj;
    return out;
  }

  function setPath(root, p, value) {
    const parts = p.replace(/\[(\d+)\]/g, ".$1").split(".");
    let cur = root;
    for (let i = 0; i < parts.length - 1; i++) {
      const key = parts[i];
      const nextIsIndex = /^\d+$/.test(parts[i + 1]);
      if (cur[key] === undefined || typeof cur[key] !== "object") cur[key] = nextIsIndex ? [] : {};
      cur = cur[key];
    }
    cur[parts[parts.length - 1]] = value;
  }

  /* merge_whole_document's CONTRACT, not its code: apply the incoming
     document's populated leaves as mutations, with NO removals, so a key the
     client omitted is left standing rather than deleted. A no-op writes
     nothing and burns neither a revision nor a history row. */
  srv.applyMerge = function (pid, incoming) {
    if (!docs[pid]) docs[pid] = { doc: {}, revision: 0, history: [] };
    const rec = docs[pid];
    const before = JSON.stringify(rec.doc);
    const next = JSON.parse(before);
    const flat = leaves(incoming, "", {});
    Object.keys(flat).forEach((p) => setPath(next, p, flat[p]));
    const after = JSON.stringify(next);
    if (after === before) {
      return { write_applied: false, revision: rec.revision };
    }
    rec.doc = next;
    rec.revision += 1;
    rec.history.push({ revision: rec.revision, changed: Object.keys(flat).length });
    return { write_applied: true, revision: rec.revision };
  };

  return srv;
}

/* ── the harness ──────────────────────────────────────────────────────── */

function createHarness(options) {
  options = options || {};
  const server = makeServer();

  const dom = new JSDOM(
    '<!doctype html><html><body><div id="bbMount"></div></body></html>',
    { runScripts: "outside-only", url: "http://localhost:8082/ui/hornelore1.0.html" });

  const win = dom.window;
  const ctx = dom.getInternalVMContext();

  const ORIGIN = "http://localhost:8000";
  win.API = {
    BB_QQ_PUT: ORIGIN + "/api/bio-builder/questionnaire",
    BB_QQ_GET: (pid) => ORIGIN + "/api/bio-builder/questionnaire?person_id=" + pid,
  };

  win.state = {
    person_id: options.personId || null,
    profile: { basics: {} },
  };

  /* Controllable fetch. Every request is recorded BEFORE any configured
     failure is applied, so a test can assert on what the browser tried to
     send even when the server refused it. */
  win.fetch = function (url, init) {
    const u = String(url);
    const method = (init && init.method) || "GET";

    if (method === "PUT") {
      let payload = null;
      try { payload = JSON.parse(init.body); } catch (e) { payload = { _unparseable: init.body }; }
      server.puts.push(payload);

      const status = server.nextPutStatus;
      if (status !== null) {
        if (!server.putSticky) server.nextPutStatus = null;
        const body = server.nextPutBody || {};
        if (!server.putSticky) server.nextPutBody = null;
        if (status === "network") return Promise.reject(new Error("simulated network failure"));
        return Promise.resolve(makeResponse(status, body));
      }
      const res = server.applyMerge(payload.person_id, payload.questionnaire || {});
      return Promise.resolve(makeResponse(200, {
        ok: true, person_id: payload.person_id,
        revision: res.revision, write_applied: res.write_applied,
      }));
    }

    // GET
    const pid = decodeURIComponent((u.split("person_id=")[1] || "").split("&")[0]);
    server.gets.push(pid);
    const rec = server.docs[pid];
    const body = {
      ok: true, person_id: pid,
      questionnaire: rec ? JSON.parse(JSON.stringify(rec.doc)) : {},
      revision: rec ? rec.revision : 0,
      source: rec ? "stored" : "empty",
    };
    if (server.getPaused) {
      // Park it. The test releases it with releaseGet(), which is how an
      // "a GET lands while the operator is typing" sequence is expressed.
      return new Promise((resolve) => { server.holdGet = () => resolve(makeResponse(200, body)); });
    }
    return Promise.resolve(makeResponse(200, body));
  };

  function makeResponse(status, body) {
    const text = JSON.stringify(body);
    return {
      ok: status >= 200 && status < 300,
      status: status,
      json: () => Promise.resolve(JSON.parse(text)),
      text: () => Promise.resolve(text),
    };
  }

  /* Load the REAL modules, unmodified. */
  const files = [
    "ui/js/bio-builder-core.js",
    "ui/js/bio-builder-questionnaire.js",
  ];
  for (const rel of files) {
    const src = fs.readFileSync(
      process.env[rel.indexOf("core") !== -1 ? "LV_BBCORE_JS" : "LV_BBQQ_JS"] || path.join(ROOT, rel),
      "utf8");
    vm.runInContext(src, ctx, { filename: rel });
  }

  /* The modules log heavily on localhost, which is the origin the harness
     deliberately keeps so that _qqDebugEnabled behaves exactly as it does in
     the real app. Quiet the output instead of changing the condition — the
     logging paths still run, they just do not drown the test report.
     LV_HARNESS_VERBOSE=1 to see them; useful when a sequence fails. */
  if (!process.env.LV_HARNESS_VERBOSE) {
    const sink = () => {};
    win.console.log = sink;
    win.console.warn = sink;
    win.console.info = sink;
    win.console.debug = sink;
    // console.error stays: an unexpected error in the code under test should
    // never be hidden by a convenience in the harness.
  }

  const mods = win.LorevoxBioBuilderModules;
  if (!mods || !mods.core || !mods.questionnaire) {
    throw new Error("the Bio Builder modules did not load into the harness");
  }

  const core = mods.core;
  const qq = mods.questionnaire;

  /* bio-builder.js publishes the namespace the rendered HTML's onclick
     attributes call into. The harness invokes functions directly, but the
     renderer emits those attributes, so the namespace must exist. */
  win.LorevoxBioBuilder = win.LorevoxBioBuilder || {};
  win.LorevoxBioBuilder._saveSection = qq._saveSection;
  win.LorevoxBioBuilder._addRepeatEntry = qq._addRepeatEntry;

  const h = {
    window: win, document: win.document, core, qq, server,

    /* Select a narrator the way the application does.
       _onNarratorSwitch resets narrator-scoped state, sets bb.personId and
       runs the post-switch hooks. Setting state.person_id alone leaves
       bb.personId null, and every save is then correctly BLOCKED by the
       cross-narrator guard — which is what the first run of this harness
       hit. A harness that skipped the real switch would have been testing a
       state the application never reaches. */
    setNarrator(pid) {
      win.state.person_id = pid;
      core._onNarratorSwitch(pid);
      return h;
    },

    /* Render a section with the SHIPPING renderer, so the ids under test are
       the ids the application actually produces. A harness that invented its
       own id scheme would pass while the real form failed. */
    render(sectionId) {
      if (!qq.SECTIONS.some((s) => s.id === sectionId)) {
        throw new Error("no such section: " + sectionId);
      }
      // _renderSectionDetail(container, activeSection, renderActiveTab) —
      // it writes into the container rather than returning markup. The first
      // version of this harness called it as if it returned HTML, rendered
      // nothing, and reported every sequence as failing. A harness that gets
      // the call wrong accuses working code.
      const mount = win.document.getElementById("bbMount");
      qq._renderSectionDetail(mount, sectionId, function () {});
      return h;
    },

    /* What the operator sees: every input the rendered form actually has. */
    fields(sectionId) {
      return Array.from(win.document.querySelectorAll("[id^='bbQ_']")).map((el) => el.id);
    },

    entryCount() {
      const ids = h.fields();
      let n = 0;
      while (ids.some((id) => id.indexOf("bbQ_" + n + "_") === 0)) n++;
      return n;
    },

    type(id, value) {
      const el = win.document.getElementById(id);
      if (!el) throw new Error("no such field on the rendered form: " + id);
      el.value = value;
      return h;
    },

    typeEntry(idx, fieldId, value) { return h.type("bbQ_" + idx + "_" + fieldId, value); },

    valueOf(id) {
      const el = win.document.getElementById(id);
      return el ? el.value : undefined;
    },

    save(sectionId) { qq._saveSection(sectionId); return h; },
    addEntry(sectionId) { qq._addRepeatEntry(sectionId, function () {}); return h; },
    restore(pid) { return core._restoreQuestionnaire(pid); },

    memory() { return (core._bb() || {}).questionnaire; },

    draft(pid) {
      try {
        const raw = win.localStorage.getItem("lorevox_qq_draft_" + pid);
        return raw ? JSON.parse(raw).d : null;
      } catch (e) { return null; }
    },

    /* Write the localStorage draft directly. _saveSection restores before it
       collects, and the restore re-reads the draft — so a test that shrinks
       only the in-memory document has its change undone before the code under
       test ever sees it. */
    setDraft(pid, doc) {
      win.localStorage.setItem("lorevox_qq_draft_" + pid,
        JSON.stringify({ v: core.DRAFT_SCHEMA_VERSION, d: doc }));
      return h;
    },

    banner() {
      const el = win.document.getElementById("bbSaveStatus");
      if (!el || el.hidden) return null;
      return { text: el.textContent, background: el.style.background };
    },

    pauseGets() { server.getPaused = true; return h; },
    releaseGet() {
      server.getPaused = false;
      if (server.holdGet) { server.holdGet(); server.holdGet = null; }
      return h;
    },

    failNextPut(status, body) {
      server.nextPutStatus = status;
      server.nextPutBody = body || {};
      return h;
    },

    /* Let every queued promise callback run. The save path awaits the
       hydration gate and then the PUT, so a test must drain more than one
       turn of the microtask queue before asserting. */
    settle(turns) {
      let p = Promise.resolve();
      for (let i = 0; i < (turns || 12); i++) p = p.then(() => new Promise((r) => setImmediate(r)));
      return p;
    },
  };

  return h;
}

module.exports = { createHarness };
