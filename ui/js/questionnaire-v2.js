/* Questionnaire V2 — the editor shell (Batch C-2, 2026-09-23).

   THE QUESTIONNAIRE IS AN EDITOR OF THE LIFE RECORD. It reads
   GET /api/life-record/{pid}, shows it as eleven topics through the read
   model (questionnaire-v2-model.js), and writes ONLY through
   PATCH /api/life-record/{pid} — the one writer — when the operator presses
   Save. There is no questionnaire document and no second authority.

   WHAT WRITES, AND WHEN (the C-2 contract):
     * opening, hydrating, switching topics, switching narrators: NOTHING —
       no network write, no draft write;
     * an operator edit: the browser draft for THAT narrator only
       (localStorage `lorevox_qv2_draft_<pid>`), stamped with the revision it
       was made against. A draft is never authoritative;
     * Save: one PATCH of explicit writer operations, each carrying the value
       it expects to replace. Never a whole-document replacement. Then the
       record is RE-READ from the server; the server is the truth.

   A 409 names the fields someone else changed; the draft is kept and the
   conflict is shown, never silently resolved by resending. A 422 shows what
   the record refused.

   Fields are added topic by topic (C-3 to C-5). C-2 ships the framework and
   one real field — the narrator's birth order, a one-valued assertion — so
   the whole path from a keystroke to the writer is real from the start. */

(function (root) {
  "use strict";

  var DRAFT_PREFIX = "lorevox_qv2_draft_";
  var DRAFT_VERSION = 1;

  var S = null;          // { pid, gen, status, view, baseRevision, topic, edits, message, conflict, refused }
  var _gen = 0;          // bumped by every hydrate; a late response for an older gen is dropped
  var _container = null;

  function model() { return root.LorevoxQuestionnaireV2Model; }
  function api() { return root.API || (typeof API !== "undefined" ? API : null); }
  function lifeRecordUrl(pid) {
    var a = api();
    if (a && a.LIFE_RECORD) return a.LIFE_RECORD(pid);
    return (root.LOREVOX_API || "http://localhost:8000") + "/api/life-record/" + encodeURIComponent(pid);
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function newId(prefix) {
    return prefix + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  }

  /* ── drafts: per narrator, revision-stamped, never authoritative ─── */
  function readDraft(pid) {
    try {
      var raw = root.localStorage.getItem(DRAFT_PREFIX + pid);
      if (!raw) return null;
      var d = JSON.parse(raw);
      return d && d.v === DRAFT_VERSION && d.pid === pid ? d : null;
    } catch (e) { return null; }
  }
  function writeDraft() {
    if (!S) return;
    try {
      if (!Object.keys(S.edits).length) { root.localStorage.removeItem(DRAFT_PREFIX + S.pid); return; }
      root.localStorage.setItem(DRAFT_PREFIX + S.pid, JSON.stringify({
        v: DRAFT_VERSION, pid: S.pid, baseRevision: S.baseRevision, edits: S.edits }));
    } catch (e) { /* a full or blocked store loses only the local copy */ }
  }

  /* ── hydrate: GET only; a response for another narrator or an older
        request is discarded at the point of use ────────────────────── */
  function hydrate(pid, keepMessage) {
    var myGen = ++_gen;
    S.status = "loading";
    paint();
    return root.fetch(lifeRecordUrl(pid), { method: "GET" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (record) {
        if (myGen !== _gen || !S || S.pid !== pid) return;     // stale: not this narrator, not this request
        S.view = model().fromRecord(record);
        S.baseRevision = S.view.revision;
        S.status = "ready";
        if (!keepMessage) S.message = null;
        var d = readDraft(pid);
        if (d && d.edits && Object.keys(S.edits).length === 0) {
          S.edits = d.edits;
          S.draftRevision = d.baseRevision;
          S.message = { kind: "info", text: "Unsaved changes from this browser were restored" +
            (d.baseRevision !== S.baseRevision ? " (made against an earlier version — Save checks each one)." : ".") };
        }
        paint();
      })
      .catch(function (e) {
        if (myGen !== _gen || !S || S.pid !== pid) return;
        S.status = "error";
        S.message = { kind: "error", text: "Could not load this narrator's record (" + e.message + "). Nothing was changed." };
        paint();
      });
  }

  /* ── public entry: bio-builder.js renders the Questionnaire tab here ── */
  function render(container, pid) {
    _container = container;
    if (!pid) {
      // The questionnaire's SHAPE is visible before any narrator exists, so
      // it never looks as if it failed to load. Nothing here is live.
      S = null;
      ensureCss();
      container.innerHTML = '<div class="qv2 qv2-no-narrator" data-qv2-state="no-narrator">' +
        '<div class="qv2-head"><strong>Questionnaire</strong> <span class="qv2-rev">No narrator selected</span></div>' +
        '<div class="qv2-msg qv2-info" data-qv2-msg="info">Create or select a narrator to begin. ' +
        'The questionnaire edits that narrator\'s Life Record.</div>' +
        '<nav class="qv2-nav" role="tablist">' + model().TOPICS.map(function (t) {
          return '<button type="button" role="tab" disabled data-qv2-topic="' + t.id + '">' +
            t.n + ". " + esc(t.title) + "</button>"; }).join("") + "</nav>" +
        '<section class="qv2-topic"><p class="qv2-blank">No narrator selected.</p></section></div>';
      return;
    }
    if (!S || S.pid !== pid) {
      // Narrator switch: the outgoing narrator's draft is already on disk
      // (it is written on every edit), so nothing is written here.
      S = { pid: pid, status: "loading", view: null, baseRevision: null, topic: "narrator",
            edits: {}, message: null, conflict: null, refused: null };
      paint();
      hydrate(pid);
      return;
    }
    paint();
  }

  /* ── edits: keyed by what they change, stamped with what they replace ── */
  function answerKey(subjectType, subjectId, concept) { return subjectType + ":" + subjectId + ":" + concept; }

  function setAnswerEdit(topic, subjectType, subjectId, concept, answer, rawValue) {
    var key = answerKey(subjectType, subjectId, concept);
    var value = typeof rawValue === "string" ? rawValue.trim() : rawValue;
    var current = answer.state === "value" ? answer.value : undefined;
    if (value === "" || value === undefined || value === current) {
      // Clearing a field is not a removal (omission never deletes), and
      // typing the stored value back is no change.
      delete S.edits[key];
    } else {
      var last = (answer.history || []).filter(function (a) { return a.id === answer.assertionId; })[0];
      S.edits[key] = { kind: "answer", topic: topic, subjectType: subjectType, subjectId: subjectId,
                       concept: concept, value: value,
                       basis: { state: answer.state, assertionId: answer.assertionId || null,
                                value: current === undefined ? null : current,
                                status: last ? last.status : null } };
    }
    writeDraft();
  }

  /* An answer edit, as writer operations. A first answer is an `add`; a
     changed answer is a NEW assertion that supersedes the old one, which
     is kept (a correction never erases). Every `set` carries the value it
     expects to replace, so someone else's newer change is a 409. */
  function changesFor(edit, source) {
    var id = newId("qv2a-");
    var a = { subjectType: edit.subjectType, subjectId: edit.subjectId, conceptId: edit.concept,
              value: edit.value, source: source.source, assertedBy: source.assertedBy,
              status: "operator_entered" };
    if (edit.basis.state === "blank") return [{ op: "add", path: "assertions/" + id, value: a }];
    var old = edit.basis.assertionId;
    a.supersedes = old;
    return [
      { op: "add", path: "assertions/" + id, value: a },
      { op: "set", path: "assertions/" + old + "/supersededBy", value: id, expectedPrevious: null },
      { op: "set", path: "assertions/" + old + "/status", value: "superseded",
        expectedPrevious: edit.basis.status },
    ];
  }

  function save() {
    if (!S || S.status !== "ready" || !Object.keys(S.edits).length) return Promise.resolve();
    var pid = S.pid;
    var source = { source: "operator", assertedBy: "operator" };   // never labelled the narrator's by default
    var changes = [];
    Object.keys(S.edits).forEach(function (k) { changes = changes.concat(changesFor(S.edits[k], source)); });
    S.status = "saving"; S.conflict = null; S.refused = null; S.message = null;
    paint();
    return root.fetch(lifeRecordUrl(pid), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ baseRevision: S.baseRevision, actor: "operator", changes: changes }),
    }).then(function (r) {
      return r.json().then(function (body) { return { status: r.status, body: body }; },
                           function () { return { status: r.status, body: null }; });
    }).then(function (res) {
      if (!S || S.pid !== pid) return;                                // narrator changed mid-save
      if (res.status === 200) {
        S.edits = {};
        writeDraft();                                                  // clears it
        S.message = { kind: "ok", text: "Saved." };
        return hydrate(pid, true);                                     // the server is the truth
      }
      S.status = "ready";
      var detail = res.body && res.body.detail;
      if (res.status === 409 && detail && detail.conflict) {
        S.conflict = detail.conflict;
        S.message = { kind: "conflict", text: "Someone else changed this record since you opened it. " +
          "Your changes are kept here and nothing was saved." };
      } else if (res.status === 422 && detail && detail.refused) {
        S.refused = detail.refused;
        S.message = { kind: "error", text: "The record refused these changes. Nothing was saved." };
      } else {
        S.message = { kind: "error", text: "Save failed (HTTP " + res.status + "). Your changes are kept here." };
      }
      paint();
    }).catch(function (e) {
      if (!S || S.pid !== pid) return;
      S.status = "ready";
      S.message = { kind: "error", text: "Save failed (" + e.message + "). Your changes are kept here." };
      paint();
    });
  }

  function discard() {
    if (!S) return;
    S.edits = {}; S.conflict = null; S.refused = null;
    writeDraft();
    S.message = { kind: "info", text: "Unsaved changes discarded." };
    paint();
  }

  /* ── painting ───────────────────────────────────────────────────── */
  function answerText(ans) {
    if (!ans || ans.state === "blank") return '<span class="qv2-blank">not recorded</span>';
    if (ans.state === "unresolved") {
      return "unresolved: " + ans.alternatives.map(function (x) { return esc(valueText(x.value)); }).join(" / ");
    }
    return esc(valueText(ans.value));
  }
  function valueText(v) {
    if (v && typeof v === "object" && "text" in v) return v.text;
    return v === 0 ? "0" : String(v);
  }
  function personName(pid) {
    var p = S.view.people[pid];
    if (!p || !p.names[0]) return "(name not yet in the Life Record)";   // never an internal id
    return p.names[0].fullText;
  }
  function list(items) {
    return items.length ? "<ul>" + items.map(function (x) { return "<li>" + x + "</li>"; }).join("") + "</ul>"
                        : '<p class="qv2-blank">Nothing recorded yet.</p>';
  }
  function relLine(rid) {
    var r = S.view.relationships[rid];
    var p = S.view.people[r.withPersonId];
    return esc(r.role) + ": " + esc(personName(r.withPersonId)) +
      (p ? " — " + answerText(p.lifeStatus) : "");
  }
  function eventLine(eid) {
    var e = S.view.events[eid];
    return esc(e.type) + (e.placeLabel ? " · " + esc(e.placeLabel) : "") +
      (e.date ? " · " + answerText(e.date) : "");
  }
  function storyLine(sid) {
    var s = S.view.stories[sid];
    return esc(s.kind) + (s.title ? " · " + esc(s.title) : "") +
      (s.origin === "captured" ? " · the narrator's recorded words" : " · written");
  }

  function answerInput(topic, subjectType, subjectId, concept, label, ans) {
    var key = answerKey(subjectType, subjectId, concept);
    var pending = S.edits[key];
    var editable = ans.state !== "unresolved";
    var shown = pending ? pending.value : (ans.state === "value" ? valueText(ans.value) : "");
    return '<label class="qv2-field">' + esc(label) +
      (editable
        ? ' <input type="text" data-qv2-answer="' + esc(key) + '" data-topic="' + esc(topic) +
          '" value="' + esc(shown) + '"' + (pending ? ' class="qv2-dirty"' : "") + ">"
        : " " + answerText(ans)) +
      "</label>";
  }

  function topicBody(t) {
    var v = S.view, N = v.people[v.narratorPersonId] || null, T = v.topics[t];
    switch (t) {
      case "narrator":
        if (!N) return '<p class="qv2-blank">Nothing recorded yet.</p>';
        return (N.notYetInRecord ? '<p class="qv2-new" data-qv2-new-narrator>This narrator has nothing in the ' +
                 "Life Record yet. The first Save creates their record.</p>" : "") +
          "<h4>Names</h4>" + list(N.names.map(function (n) {
                 return esc(n.fullText) + " <small>(" + esc(n.kind || "current") + ")</small>"; })) +
          "<h4>Pronouns</h4>" + list(N.pronouns.map(function (p) { return esc(p.value); })) +
          "<h4>Birth</h4><p>" + answerText(N.birth.date) +
            (N.birth.placeLabel ? " · " + esc(N.birth.placeLabel) : "") + "</p>" +
          answerInput("narrator", "person", N.id, "person.birth.order", "Birth order, as the narrator describes it",
                      N.birthOrder) +
          "<h4>Current home</h4>" + list(T.currentHomes.map(eventLine));
      case "family":
        return list(T.relationships.map(relLine));
      case "partners":
        return "<h4>Partners</h4>" + list(T.relationships.map(relLine)) +
          "<h4>Unions</h4>" + list(T.unions.map(eventLine)) +
          "<h4>Children</h4>" + list(T.children.map(relLine)) +
          "<h4>Grandchildren</h4>" + list(T.grandchildren.map(relLine));
      case "wider":
        return list(T.relationships.map(relLine).concat(
          T.otherPeople.map(function (id) { return esc(personName(id)); }))) +
          "<h4>Animals</h4>" + list(T.animals.map(function (id) {
            var a = v.animals[id]; return esc(a.name || "(unnamed)") + (a.species ? " · " + esc(a.species) : ""); }));
      case "heritage":
        return !N ? "" : "<h4>Heritage</h4>" + list(N.heritage.map(function (x) { return esc(x.value); })) +
          "<h4>Languages</h4>" + list(N.languages.map(function (x) { return esc(x.value); })) +
          "<p>Faith raised in: " + answerText(N.faithRaised) + "</p><p>Faith now: " + answerText(N.faithCurrent) + "</p>";
      case "service":
        return (N ? "<p>Military service: " + answerText(N.militaryService) + "</p>" : "") +
          list((T.events || []).map(eventLine));
      case "experiences":
        return (N ? "<h4>Interests</h4>" + list(N.interests.map(function (x) { return esc(x.value); })) : "") +
          list((T.events || []).map(eventLine)) +
          "<h4>Trips</h4>" + list((T.trips || []).map(function (x) { return esc(x.label || x.tripId); }));
      default:
        return list((T.events || []).map(eventLine));
    }
  }

  var CSS = [
    ".qv2{display:grid;grid-template-columns:15rem 1fr;gap:.75rem 1rem;font-size:.92rem;color:#e2e8f0}",
    ".qv2-head{grid-column:1/-1;display:flex;flex-wrap:wrap;align-items:center;gap:.6rem;padding:.4rem 0;border-bottom:1px solid #334155}",
    ".qv2-rev{color:#94a3b8;font-size:.8rem}.qv2-dirty-count{color:#fbbf24;margin-left:auto}",
    ".qv2-head button{padding:.3rem .8rem;border-radius:4px;border:1px solid #475569;background:#1e293b;color:#e2e8f0;cursor:pointer}",
    ".qv2-head button[data-qv2-action=save]:not([disabled]){background:#2563eb;border-color:#2563eb}",
    ".qv2-head button[disabled]{opacity:.45;cursor:default}",
    ".qv2-msg,.qv2-conflict,.qv2-refused{grid-column:1/-1;padding:.45rem .7rem;border-radius:4px}",
    ".qv2-ok{background:#064e3b}.qv2-info{background:#1e3a5f}.qv2-error,.qv2-refused{background:#7f1d1d}",
    ".qv2-conflict-msg,.qv2-conflict{background:#78350f}",
    ".qv2-nav{display:flex;flex-direction:column;gap:.2rem}",
    ".qv2-nav button{text-align:left;padding:.4rem .6rem;border:0;border-radius:4px;background:transparent;color:#cbd5e1;cursor:pointer}",
    ".qv2-nav button.qv2-active{background:#1e293b;color:#fff;font-weight:600}.qv2-dot{color:#fbbf24}",
    ".qv2-topic h3{margin:.2rem 0 .6rem}.qv2-topic h4{margin:.8rem 0 .3rem;color:#94a3b8;font-size:.8rem;text-transform:uppercase}",
    ".qv2-field{display:block;margin:.6rem 0}.qv2-field input{margin-left:.5rem;padding:.25rem .4rem;min-width:16rem;background:#0f172a;color:#e2e8f0;border:1px solid #475569;border-radius:4px}",
    ".qv2-field input.qv2-dirty{border-color:#fbbf24}.qv2-blank{color:#64748b;font-style:italic}",
    ".qv2-new{color:#93c5fd}.qv2-nav button[disabled]{opacity:.45;cursor:default}",
    ".qv2-legacy-table th{text-align:left;color:#94a3b8;padding-right:1rem;font-weight:normal}",
  ].join("");
  function ensureCss() {
    var d = root.document;
    if (!d || d.getElementById("qv2-css")) return;
    var s = d.createElement("style"); s.id = "qv2-css"; s.textContent = CSS;
    (d.head || d.documentElement).appendChild(s);
  }

  function paint() {
    if (!_container || !S) return;
    ensureCss();
    var M = model();
    var html = ['<div class="qv2" data-qv2-pid="' + esc(S.pid) + '">'];
    if (S.status === "loading" && !S.view) {
      html.push('<div class="qv2-status">Loading the Life Record…</div></div>');
      _container.innerHTML = html.join("");
      return;
    }
    if (!S.view) {
      html.push('<div class="qv2-status qv2-error">' + esc(S.message ? S.message.text : "Not loaded.") + "</div></div>");
      _container.innerHTML = html.join("");
      return;
    }
    var n = Object.keys(S.edits).length;
    var dirtyTopics = {};
    Object.keys(S.edits).forEach(function (k) { dirtyTopics[S.edits[k].topic] = true; });
    html.push('<div class="qv2-head"><strong>' + esc(personName(S.view.narratorPersonId)) + "</strong>" +
      ' <span class="qv2-rev">record revision ' + esc(S.baseRevision) + "</span>" +
      ' <span class="qv2-dirty-count" data-qv2-dirty="' + n + '">' +
      (n ? n + " unsaved change" + (n > 1 ? "s" : "") : "No unsaved changes") + "</span>" +
      ' <button type="button" data-qv2-action="save"' + (n && S.status === "ready" ? "" : " disabled") +
      ">Save</button>" +
      ' <button type="button" data-qv2-action="discard"' + (n ? "" : " disabled") + ">Discard changes</button></div>");
    if (S.message) html.push('<div class="qv2-msg qv2-' + esc(S.message.kind) + '" data-qv2-msg="' +
      esc(S.message.kind) + '">' + esc(S.message.text) + "</div>");
    if (S.conflict) html.push('<div class="qv2-conflict" data-qv2-conflict><ul>' + S.conflict.map(function (c) {
      return "<li>" + esc(c.path) + ": now <code>" + esc(JSON.stringify(c.current)) + "</code></li>"; }).join("") + "</ul></div>");
    if (S.refused) html.push('<div class="qv2-refused" data-qv2-refused><ul>' + S.refused.map(function (c) {
      return "<li>" + esc(c.reason || c.rule) + "</li>"; }).join("") + "</ul></div>");
    html.push('<nav class="qv2-nav" role="tablist">');
    M.TOPICS.forEach(function (t) {
      html.push('<button type="button" role="tab" data-qv2-topic="' + t.id + '" aria-selected="' +
        (t.id === S.topic) + '"' + (t.id === S.topic ? ' class="qv2-active"' : "") + ">" +
        t.n + ". " + esc(t.title) + (dirtyTopics[t.id] ? ' <span class="qv2-dot" title="unsaved">●</span>' : "") +
        "</button>");
    });
    html.push("</nav>");
    var T = S.view.topics[S.topic];
    html.push('<section class="qv2-topic" data-qv2-panel="' + esc(S.topic) + '"><h3>' + esc(T.title) + "</h3>" +
      topicBody(S.topic) +
      (T.stories && T.stories.length ? "<h4>Stories</h4>" + list(T.stories.map(storyLine)) : "") +
      "</section></div>");
    _container.innerHTML = html.join("");
    wire();
  }

  function wire() {
    var root_ = _container.querySelector(".qv2"); if (!root_) return;
    root_.addEventListener("click", function (ev) {
      var t = ev.target.closest("[data-qv2-topic]");
      if (t) { S.topic = t.getAttribute("data-qv2-topic"); paint(); return; }   // navigation writes nothing
      var a = ev.target.closest("[data-qv2-action]");
      if (!a || a.disabled) return;
      if (a.getAttribute("data-qv2-action") === "save") save();
      if (a.getAttribute("data-qv2-action") === "discard") discard();
    });
    root_.addEventListener("change", function (ev) {
      var inp = ev.target.closest("[data-qv2-answer]"); if (!inp) return;
      var parts = inp.getAttribute("data-qv2-answer").split(":");
      var ans = lookupAnswer(parts[0], parts[1], parts[2]);
      if (!ans) return;
      setAnswerEdit(inp.getAttribute("data-topic"), parts[0], parts[1], parts[2], ans, inp.value);
      paint();
    });
  }

  function lookupAnswer(subjectType, subjectId, concept) {
    if (subjectType !== "person") return null;
    var p = S.view.people[subjectId]; if (!p) return null;
    var map = { "person.birth.order": p.birthOrder };
    return map[concept] || null;
  }

  /* ── Earlier answers: the legacy questionnaire, READ-ONLY ───────────
     Kept exactly as saved, with no input and no Save. It is not the Life
     Record; nothing here writes. */
  function renderEarlierAnswers(container, pid) {
    if (!pid) { container.innerHTML = '<div class="qv2-empty">Choose a narrator.</div>'; return; }
    container.innerHTML = '<div class="qv2-legacy" data-qv2-legacy="' + esc(pid) + '">Loading earlier answers…</div>';
    var a = api();
    var url = a && a.BB_QQ_GET ? a.BB_QQ_GET(pid)
      : (root.LOREVOX_API || "http://localhost:8000") + "/api/bio-builder/questionnaire?person_id=" + encodeURIComponent(pid);
    root.fetch(url, { method: "GET" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
      var box = container.querySelector('[data-qv2-legacy="' + pid + '"]'); if (!box) return;   // switched away
      var doc = (j && (j.questionnaire || j.data || j)) || {};
      var rows = [];
      (function walk(node, path) {
        if (node === null || node === undefined || node === "") return;
        if (Array.isArray(node)) { node.forEach(function (x, i) { walk(x, path + "[" + (i + 1) + "]"); }); return; }
        if (typeof node === "object") { Object.keys(node).forEach(function (k) {
          if (k.charAt(0) !== "_") walk(node[k], path ? path + " › " + k : k); }); return; }
        rows.push("<tr><th>" + esc(path) + "</th><td>" + esc(node) + "</td></tr>");
      })(doc, "");
      box.innerHTML = "<p>Answers saved by the earlier questionnaire. They are kept exactly as they were and are " +
        "<strong>not</strong> part of the Life Record; nothing on this page can change them.</p>" +
        (rows.length ? '<table class="qv2-legacy-table">' + rows.join("") + "</table>" : "<p>No earlier answers.</p>");
    }).catch(function () {
      var box = container.querySelector('[data-qv2-legacy="' + pid + '"]');
      if (box) box.textContent = "Earlier answers could not be loaded. Nothing was changed.";
    });
  }

  var api_ = { render: render, renderEarlierAnswers: renderEarlierAnswers,
               _state: function () { return S; }, _save: save };
  if (typeof module !== "undefined" && module.exports) module.exports = api_;
  if (root) root.LorevoxQuestionnaireV2 = api_;
})(typeof window !== "undefined" ? window : this);
