/* Questionnaire V2 — the editor shell (Batch C-2, 2026-09-23; people and
   relationships, Batch C-3, 2026-09-24).

   THE QUESTIONNAIRE IS AN EDITOR OF THE LIFE RECORD. It reads
   GET /api/life-record/{pid}, shows it as eleven topics through the read
   model (questionnaire-v2-model.js), and writes ONLY through
   PATCH /api/life-record/{pid} — the one writer — when the operator presses
   Save. There is no questionnaire document and no second authority.

   WHAT WRITES, AND WHEN (the C-2 contract, unchanged by C-3):
     * opening, hydrating, switching topics, switching narrators: NOTHING —
       no network write, no draft write;
     * an operator edit: the browser draft for THAT narrator only
       (localStorage `lorevox_qv2_draft_<pid>`), stamped with the revision it
       was made against. A draft is never authoritative;
     * Save: one PATCH of explicit writer operations, each `set` carrying the
       value it expects to replace. Never a whole-document replacement. Then
       the record is RE-READ from the server; the server is the truth.

   A 409 names the fields someone else changed; the draft is kept and the
   conflict is shown, never silently resolved by resending. A 422 shows what
   the record refused.

   C-3 — PEOPLE AND RELATIONSHIPS. Every person has a stable record id,
   minted once when the operator adds them and kept in the draft, so a
   person entered once is ONE person however many relationships they have
   (a grandmother who raised the narrator is family AND caregiver — two
   relationships, one id). Names are stored whole, never split. Nothing is
   preselected: no relationship kind, no qualifier, no life status. A blank
   is the absence of an answer, never "no". Removing a person or a
   relationship is C-6 (a recoverable removal state), not here. */

(function (root) {
  "use strict";

  var DRAFT_PREFIX = "lorevox_qv2_draft_";
  var DRAFT_VERSION = 1;

  var S = null;          // { pid, status, view, baseRevision, topic, edits, provenance, message, conflict, refused, openRel, formError }
  var _gen = 0;          // bumped by every hydrate; a late response for an older gen is dropped
  var _container = null;

  /* Who a fact comes from. The default is the operator — nothing typed here
     is labelled the narrator's own words unless the operator says so. */
  var PROVENANCE = {
    operator: { label: "Entered by the operator", source: "operator", assertedBy: "operator" },
    narrator: { label: "The narrator told me", source: "narrator_stated", assertedBy: "narrator" },
    document: { label: "From a document", source: "document", assertedBy: "operator" },
  };
  var LIFE_STATUS = [["explicitly_living", "Living"], ["deceased", "Deceased"], ["unknown", "Not known"]];
  var LINEAGE = [["maternal", "Mother's side"], ["paternal", "Father's side"]];
  var NAME_KINDS = [["current", "current"], ["former", "former"], ["variant", "variant spelling"],
                    ["also_known_as", "also known as"]];
  var TOPIC_ROLES = {
    family:   ["parent", "sibling", "grandparent", "caregiver"],
    partners: ["spouse", "partner", "child", "grandchild"],
    wider:    ["chosen_family", "friend", "mentor", "cared_for", "other"],
  };
  var COUNT_CONCEPTS = {
    "person.reported_count.siblings": "siblings", "person.reported_count.children": "children",
    "person.reported_count.grandchildren": "grandchildren",
  };

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
        v: DRAFT_VERSION, pid: S.pid, baseRevision: S.baseRevision, edits: S.edits,
        provenance: S.provenance }));
    } catch (e) { /* a full or blocked store loses only the local copy */ }
  }

  /* C-3 follow-up — a draft written before C-3 (same draft version) can hold
     edits with no pre-minted assertion id. The id must exist BEFORE Save, so
     a retried Save re-sends the same id and is refused whole instead of
     storing a second account. Assign any missing id ONCE, here, and persist
     the upgraded draft immediately — keeping its own baseRevision and
     provenance. The draft is not discarded and its version is not bumped. */
  function upgradeDraftIds(pid, d) {
    var changed = false;
    var need = function (e, field, when) {
      if (when && !e[field]) { e[field] = newId("qv2a-"); changed = true; }
    };
    Object.keys(d.edits).forEach(function (k) {
      var e = d.edits[k];
      if (!e || typeof e !== "object") return;
      if (e.kind === "answer") need(e, "newAssertionId", true);
      if (e.kind === "newperson") need(e, "lifeStatusAssertionId", !!e.lifeStatus);
      if (e.kind === "newrel") { need(e, "kindAssertionId", true); need(e, "lineageAssertionId", !!e.lineage); }
    });
    if (!changed) return;
    try {
      root.localStorage.setItem(DRAFT_PREFIX + pid, JSON.stringify({
        v: DRAFT_VERSION, pid: pid, baseRevision: d.baseRevision, edits: d.edits,
        provenance: d.provenance }));
    } catch (e) { /* storage refused: the ids still hold for this page's Save */ }
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
        // Batch C-2b: tell the Bio Builder header which record/revision is
        // on screen (a notification, not a write).
        try {
          var me = S.view.people[S.view.narratorPersonId];
          root.dispatchEvent(new root.CustomEvent("lorevox:life-record-shown", { detail: {
            pid: pid, revision: S.view.revision, name: me && me.names[0] ? me.names[0].fullText : null } }));
        } catch (_) {}
        S.status = "ready";
        if (!keepMessage) S.message = null;
        var d = readDraft(pid);
        if (d && d.edits && Object.keys(S.edits).length === 0) {
          upgradeDraftIds(pid, d);                                     // C-3 follow-up: before anything can Save
          S.edits = d.edits;
          if (d.provenance && PROVENANCE[d.provenance]) S.provenance = d.provenance;
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
  function render(container, pid, opts) {
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
    var wantTopic = opts && opts.topic;
    if (!S || S.pid !== pid) {
      // Narrator switch: the outgoing narrator's draft is already on disk
      // (it is written on every edit), so nothing is written here.
      S = { pid: pid, status: "loading", view: null, baseRevision: null, topic: wantTopic || "narrator",
            edits: {}, provenance: "operator", message: null, conflict: null, refused: null,
            openRel: null, formError: null };
      paint();
      hydrate(pid);
      return;
    }
    if (wantTopic) S.topic = wantTopic;
    paint();
  }

  /* ════════════════════════════════════════════════════════════════════
     EDITS — each keyed by what it changes, each carrying what it replaces
     ════════════════════════════════════════════════════════════════════ */
  function answerKey(subjectType, subjectId, concept) { return subjectType + ":" + subjectId + ":" + concept; }

  function coerce(concept, value) {
    if (COUNT_CONCEPTS[concept]) {
      if (!/^\d+$/.test(value)) return { error: "A count is a whole number (0 is an answer; leave it blank if nobody said)." };
      return { value: parseInt(value, 10) };
    }
    return { value: value };
  }

  function setAnswerEdit(topic, subjectType, subjectId, concept, answer, rawValue) {
    var key = answerKey(subjectType, subjectId, concept);
    var value = typeof rawValue === "string" ? rawValue.trim() : rawValue;
    var current = answer.state === "value" ? answer.value : undefined;
    if (value === "" || value === undefined || value === current || String(value) === String(current)) {
      // Clearing a field is not a removal (omission never deletes), and
      // typing the stored value back is no change.
      delete S.edits[key];
    } else {
      var c = coerce(concept, value);
      if (c.error) { S.formError = { topic: topic, text: c.error }; return; }
      var last = (answer.history || []).filter(function (a) { return a.id === answer.assertionId; })[0];
      // The new assertion's id is minted HERE, once, and kept in the draft —
      // never at Save. A retried Save then re-sends the SAME id, which the
      // writer refuses as "already exists" instead of storing a second account.
      var keepId = S.edits[key] && S.edits[key].newAssertionId;
      S.edits[key] = { kind: "answer", topic: topic, subjectType: subjectType, subjectId: subjectId,
                       concept: concept, value: c.value, newAssertionId: keepId || newId("qv2a-"),
                       basis: { state: answer.state, assertionId: answer.assertionId || null,
                                value: current === undefined ? null : current,
                                status: last ? last.status : null } };
    }
    writeDraft();
  }

  /* What the operator has typed into a form but not yet added. Kept in
     memory (not the draft — it is not an edit yet) so that a repaint caused
     by another field never wipes a half-filled form. */
  function formKey(form) {
    return form.getAttribute("data-qv2-form") + ":" + (form.getAttribute("data-topic") ||
      form.getAttribute("data-rel") || form.getAttribute("data-person") || "");
  }
  function rememberForm(form) {
    if (!S.forms) S.forms = {};
    var f = readForm(form), p = form.querySelector('[data-f="pronoun"]');
    if (p) f.pronoun = String(p.value || "");
    S.forms[formKey(form)] = f;
  }
  function fv(key, field, dflt) {
    var f = S.forms && S.forms[key];
    return f && f[field] !== undefined ? f[field] : dflt;
  }
  function forget(key) { if (S.forms) delete S.forms[key]; }

  function pendingOf(kind) {
    return Object.keys(S.edits).filter(function (k) { return S.edits[k].kind === kind; })
      .map(function (k) { return S.edits[k]; });
  }

  /* Read one of the add/edit forms. Values only; nothing is inferred. */
  function readForm(form) {
    var get = function (f) { var el = form.querySelector('[data-f="' + f + '"]'); return el ? String(el.value || "").trim() : ""; };
    return {
      person: get("person"), fullText: get("fullText"), role: get("role"), describedAs: get("describedAs"),
      narratorLabel: get("narratorLabel"), lineage: get("lineage"), lifeStatus: get("lifeStatus"),
      from: get("from"), until: get("until"), nameKind: get("nameKind"),
      qualifiers: Array.prototype.slice.call(form.querySelectorAll('[data-f="q"]'))
        .filter(function (x) { return x.checked; }).map(function (x) { return x.value; }),
    };
  }

  function periodOf(f) {
    var P = model().parseDateText, start = P(f.from), end = P(f.until), out = {};
    if (start) out.start = start;
    if (end) out.end = end;
    return Object.keys(out).length ? out : null;
  }

  /* A relationship as the writer stores it: "subject is <kind> of other". */
  function relValue(role, personId, f) {
    var R = model().ROLES[role], nid = S.view.narratorPersonId;
    var v = { subjectPersonId: R.narratorIs === "other" ? personId : nid,
              otherPersonId: R.narratorIs === "other" ? nid : personId, kind: R.kind };
    if (f.describedAs) v.describedAs = f.describedAs;
    if (f.qualifiers && f.qualifiers.length) v.qualifiers = f.qualifiers.slice();
    if (f.narratorLabel) v.narratorLabel = f.narratorLabel;
    var per = periodOf(f);
    if (per) v.period = per;
    return v;
  }

  /* Would this relationship already exist (saved or pending)? The writer
     refuses a duplicate (rule "no relationship stored twice"); saying so here
     is kinder than a refused Save. */
  function duplicateOf(v) {
    var sym = { sibling_of: 1, spouse_of: 1, partner_of: 1, friend_of: 1, chosen_family_of: 1 };
    // A stored `child_of` is the parent_of the editor writes, seen from the
    // other end — compare it in the editor's direction.
    var norm = function (x) {
      if (x.kind !== "child_of") return x;
      var y = {}; Object.keys(x).forEach(function (k) { y[k] = x[k]; });
      y.kind = "parent_of"; y.subjectPersonId = x.otherPersonId; y.otherPersonId = x.subjectPersonId;
      return y;
    };
    var same = function (x) {
      x = norm(x);
      if (x.kind !== v.kind || (x.describedAs || "") !== (v.describedAs || "")) return false;
      var a = x.subjectPersonId === v.subjectPersonId && x.otherPersonId === v.otherPersonId;
      var b = sym[v.kind] && x.subjectPersonId === v.otherPersonId && x.otherPersonId === v.subjectPersonId;
      if (!(a || b)) return false;
      // The SAME rule as the writer (rules.rule_no_duplicate_relationship):
      // a duplicate only when the periods are EQUAL — both absent, or the same
      // span. One period absent and one known, or two different spans, are two
      // relationships (married Pat once, dates unknown; remarried Pat in 1992).
      return JSON.stringify(sortKeys(x.period || null)) === JSON.stringify(sortKeys(v.period || null));
    };
    var saved = Object.keys(S.view.relationships).map(function (id) { return S.view.relationships[id].raw; });
    var pending = pendingOf("newrel").map(function (e) { return e.value; });
    return saved.concat(pending).some(same);
  }

  function addPersonOrRelationship(topic, form) {
    var f = readForm(form), nid = S.view.narratorPersonId;
    var err = function (t) { S.formError = { topic: topic, text: t }; paint(); };
    if (!f.role || !model().ROLES[f.role]) return err("Choose how this person is related to the narrator.");
    if (f.role === "other" && !f.describedAs) return err("Describe the relationship when it is \"Other\".");
    var personId = f.person;
    if (!personId && !f.fullText) return err("Write the person's name as it is said — whole, as one line.");
    if (personId === nid) return err("That is the narrator.");
    var isNew = !personId;
    if (isNew) personId = newId("qv2p-");
    var value = relValue(f.role, personId, f);
    if (!isNew && duplicateOf(value)) return err("That relationship is already recorded.");
    if (isNew) {
      S.edits["newperson:" + personId] = { kind: "newperson", topic: topic, personId: personId,
        nameId: newId("qv2n-"), fullText: f.fullText, lifeStatus: f.lifeStatus || null,
        lifeStatusAssertionId: f.lifeStatus ? newId("qv2a-") : null };
    }
    var relId = newId("qv2r-");
    // Every id this relationship will be saved under is minted now, not at Save.
    S.edits["newrel:" + relId] = { kind: "newrel", topic: topic, relId: relId, personId: personId,
      role: f.role, value: value, lineage: f.lineage || null,
      kindAssertionId: newId("qv2a-"), lineageAssertionId: f.lineage ? newId("qv2a-") : null };
    S.formError = null;
    forget("person:" + topic);
    writeDraft();
    paint();
  }

  /* Changing a relationship's details. Its kind and its two people do not
     change here — a different relationship is a new one (removal is C-6). */
  function keepRelationshipEdit(relId, form) {
    var r = S.view.relationships[relId]; if (!r) return;
    var f = readForm(form);
    if (r.kind === "other" && !f.describedAs) { S.formError = { topic: S.topic, text: "\"Other\" needs its description." }; paint(); return; }
    var after = {};
    Object.keys(r.raw).forEach(function (k) { after[k] = r.raw[k]; });
    ["describedAs", "qualifiers", "narratorLabel", "period"].forEach(function (k) { delete after[k]; });
    if (f.describedAs) after.describedAs = f.describedAs;
    if (f.qualifiers.length) after.qualifiers = f.qualifiers;
    if (f.narratorLabel) after.narratorLabel = f.narratorLabel;
    var per = periodOf(f);
    if (per) after.period = per;
    var key = "reledit:" + relId;
    if (JSON.stringify(sortKeys(after)) === JSON.stringify(sortKeys(r.raw))) delete S.edits[key];
    else S.edits[key] = { kind: "reledit", topic: S.topic, relId: relId, before: r.raw, after: after };
    S.openRel = null; S.formError = null;
    forget("rel:" + relId);
    writeDraft();
    paint();
  }
  function sortKeys(o) {            // deep, so {text,value} and {value,text} compare equal
    if (Array.isArray(o)) return o.map(sortKeys);
    if (!o || typeof o !== "object") return o;
    var x = {}; Object.keys(o).sort().forEach(function (k) { x[k] = sortKeys(o[k]); }); return x;
  }

  function addName(personId, form) {
    var f = readForm(form);
    if (!f.fullText) { S.formError = { topic: S.topic, text: "Write the name whole, as it is said." }; paint(); return; }
    var nameId = newId("qv2n-");
    S.edits["newname:" + nameId] = { kind: "newname", topic: S.topic, personId: personId, nameId: nameId,
      fullText: f.fullText, nameKind: f.nameKind || "current" };
    S.formError = null;
    forget("name:" + personId);
    writeDraft(); paint();
  }

  function editName(personId, nameId, text) {
    var p = S.view.people[personId]; if (!p) return;
    var n = p.names.filter(function (x) { return x.id === nameId; })[0]; if (!n) return;
    var key = "nameedit:" + nameId, t = String(text || "").trim();
    if (!t || t === n.fullText) delete S.edits[key];     // an empty box is not a removal
    else S.edits[key] = { kind: "nameedit", topic: S.topic, personId: personId, nameId: nameId,
                          before: model().rawName(n), fullText: t };
    writeDraft();
  }

  function setPreferred(personId, nameId) {
    var p = S.view.people[personId]; if (!p) return;
    var key = "preferred:" + personId;
    if (nameId === p.preferredNameId) delete S.edits[key];
    else S.edits[key] = { kind: "preferred", topic: S.topic, personId: personId, nameId: nameId,
                          before: p.notYetInRecord ? null : (p.preferredNameId || null) };
    writeDraft();
  }

  function addPronoun(form) {
    var f = form.querySelector('[data-f="pronoun"]'), t = f ? String(f.value || "").trim() : "";
    if (!t) return;
    var id = newId("qv2a-");
    S.edits["pronoun:" + id] = { kind: "pronoun", topic: "narrator", assertionId: id,
                                 personId: S.view.narratorPersonId, value: t };
    forget("pronoun:");
    writeDraft(); paint();
  }

  function undo(key) {
    var e = S.edits[key]; if (!e) return;
    delete S.edits[key];
    // An unsaved new person exists only for their relationships: undoing the
    // last of them undoes the person too (nobody is left behind, unrelated).
    if (e.kind === "newrel" && S.edits["newperson:" + e.personId] &&
        !pendingOf("newrel").some(function (x) { return x.personId === e.personId; })) {
      e = S.edits["newperson:" + e.personId];
      delete S.edits["newperson:" + e.personId];
    }
    if (e.kind === "newperson") {        // their relationships and names go with them
      Object.keys(S.edits).forEach(function (k) {
        var x = S.edits[k];
        if ((x.kind === "newrel" || x.kind === "newname") && x.personId === e.personId) delete S.edits[k];
        if (x.kind === "answer" && x.subjectId === e.personId) delete S.edits[k];
      });
    }
    writeDraft(); paint();
  }

  /* ════════════════════════════════════════════════════════════════════
     WRITER OPERATIONS — one Save, one PATCH
     ════════════════════════════════════════════════════════════════════ */
  function assertionOp(id, subjectType, subjectId, concept, value, src, extra) {
    var v = { subjectType: subjectType, subjectId: subjectId, conceptId: concept, value: value,
              source: src.source, assertedBy: src.assertedBy, status: "operator_entered" };
    if (extra) Object.keys(extra).forEach(function (k) { v[k] = extra[k]; });
    return { op: "add", path: "assertions/" + id, value: v };
  }

  /* An answer edit. A first answer is an `add`; a changed answer is a NEW
     assertion that supersedes the old one, which is kept (a correction never
     erases). Every `set` carries the value it expects to replace, so someone
     else's newer change is a 409. */
  /* Every id is minted before Save (at edit time, or by upgradeDraftIds at
     hydration). Minting one HERE would give a retried Save a different id —
     so a missing id stops the Save instead. */
  function idOf(e, field) {
    if (!e[field]) throw new Error("an unsaved change has no id (" + e.kind + "." + field + ") — reload to repair the draft");
    return e[field];
  }

  function answerOps(edit, src) {
    var id = idOf(edit, "newAssertionId");
    if (edit.basis.state === "blank") {
      return [assertionOp(id, edit.subjectType, edit.subjectId, edit.concept, edit.value, src)];
    }
    var old = edit.basis.assertionId;
    return [
      assertionOp(id, edit.subjectType, edit.subjectId, edit.concept, edit.value, src, { supersedes: old }),
      { op: "set", path: "assertions/" + old + "/supersededBy", value: id, expectedPrevious: null },
      { op: "set", path: "assertions/" + old + "/status", value: "superseded",
        expectedPrevious: edit.basis.status },
    ];
  }

  function opsFor(e, src) {
    switch (e.kind) {
      case "answer": return answerOps(e, src);
      case "newperson": {
        var ops = [{ op: "add", path: "people/" + e.personId, value: {} },
                   { op: "add", path: "people/" + e.personId + "/names/" + e.nameId,
                     value: { fullText: e.fullText, kind: "current" } }];
        if (e.lifeStatus) ops.push(assertionOp(idOf(e, "lifeStatusAssertionId"), "person", e.personId,
                                               "person.life_status", e.lifeStatus, src));
        return ops;
      }
      case "newname":
        return [{ op: "add", path: "people/" + e.personId + "/names/" + e.nameId,
                  value: { fullText: e.fullText, kind: e.nameKind || "current" } }];
      case "nameedit": {
        var v = {}; Object.keys(e.before).forEach(function (k) { v[k] = e.before[k]; });
        v.fullText = e.fullText;
        return [{ op: "set", path: "people/" + e.personId + "/names/" + e.nameId, value: v,
                  expectedPrevious: e.before }];
      }
      case "preferred":
        return [{ op: "set", path: "people/" + e.personId + "/preferredNameRef", value: e.nameId,
                  expectedPrevious: e.before }];
      case "newrel": {
        var out = [{ op: "add", path: "relationships/" + e.relId, value: e.value },
                   // who said so: the relationship's provenance, as an assertion
                   assertionOp(idOf(e, "kindAssertionId"), "relationship", e.relId, "relationship.kind",
                               e.value.kind, src)];
        if (e.lineage) out.push(assertionOp(idOf(e, "lineageAssertionId"), "relationship", e.relId,
                                            "relationship.qualifier.lineage_side", e.lineage, src));
        return out;
      }
      case "reledit":
        return [{ op: "set", path: "relationships/" + e.relId, value: e.after, expectedPrevious: e.before }];
      case "pronoun":
        return [assertionOp(e.assertionId, "person", e.personId, "person.pronouns", e.value, src)];
    }
    return [];
  }

  // People before the names, relationships and answers that refer to them.
  var ORDER = { newperson: 0, newname: 1, nameedit: 2, preferred: 3, newrel: 4, reledit: 5, answer: 6, pronoun: 7 };

  function buildChanges() {
    var src = PROVENANCE[S.provenance] || PROVENANCE.operator;
    var edits = Object.keys(S.edits).map(function (k) { return S.edits[k]; })
      .sort(function (a, b) { return ORDER[a.kind] - ORDER[b.kind]; });
    var changes = [];
    edits.forEach(function (e) { changes = changes.concat(opsFor(e, src)); });
    return changes;
  }

  function save() {
    if (!S || S.status !== "ready" || !Object.keys(S.edits).length) return Promise.resolve();
    var pid = S.pid;
    var changes;
    try { changes = buildChanges(); }
    catch (err) {
      S.message = { kind: "error", text: "Not saved: " + err.message + ". Your changes are kept here." };
      paint();
      return Promise.resolve();
    }
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
    S.edits = {}; S.conflict = null; S.refused = null; S.openRel = null; S.formError = null;
    writeDraft();
    S.message = { kind: "info", text: "Unsaved changes discarded." };
    paint();
  }

  /* ════════════════════════════════════════════════════════════════════
     PAINTING
     ════════════════════════════════════════════════════════════════════ */
  function answerText(ans) {
    if (!ans || ans.state === "blank") return '<span class="qv2-blank">not recorded</span>';
    if (ans.state === "unresolved") {
      return "unresolved: " + ans.alternatives.map(function (x) { return esc(valueText(x.value)); }).join(" / ");
    }
    return esc(valueText(ans.value));
  }
  function valueText(v) {
    if (v && typeof v === "object" && "text" in v) return v.text;
    var lab = LIFE_STATUS.concat(LINEAGE).filter(function (o) { return o[0] === v; })[0];
    if (lab) return lab[1];
    return v === 0 ? "0" : String(v);
  }
  function pendingPerson(pid) { return S.edits["newperson:" + pid] || null; }
  function personName(pid) {
    var np = pendingPerson(pid);
    if (np) return np.fullText;
    var p = S.view.people[pid];
    if (!p || !p.names[0]) return "(name not yet in the Life Record)";   // never an internal id
    return p.names[0].fullText;
  }
  function list(items) {
    return items.length ? "<ul>" + items.map(function (x) { return "<li>" + x + "</li>"; }).join("") + "</ul>"
                        : '<p class="qv2-blank">Nothing recorded yet.</p>';
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
  function unsaved(key) {
    return ' <span class="qv2-unsaved">unsaved</span> <button type="button" class="qv2-undo" data-qv2-undo="' +
      esc(key) + '" title="Undo this unsaved change">undo</button>';
  }
  function options(pairs, selected, blankLabel) {
    return (blankLabel !== null ? '<option value="">' + esc(blankLabel || "— not recorded —") + "</option>" : "") +
      pairs.map(function (o) {
        return '<option value="' + esc(o[0]) + '"' + (o[0] === selected ? " selected" : "") + ">" + esc(o[1]) + "</option>";
      }).join("");
  }

  function answerInput(topic, subjectType, subjectId, concept, label, ans) {
    var key = answerKey(subjectType, subjectId, concept);
    var pending = S.edits[key];
    var editable = ans.state !== "unresolved";
    var shown = pending ? String(pending.value) : (ans.state === "value" ? valueText(ans.value) : "");
    return '<label class="qv2-field">' + esc(label) +
      (editable
        ? ' <input type="text" data-qv2-answer="' + esc(key) + '" data-topic="' + esc(topic) +
          '" value="' + esc(shown) + '"' + (pending ? ' class="qv2-dirty"' : "") + ">"
        : " " + answerText(ans)) +
      "</label>";
  }
  /* A closed set as a select. Blank = no answer. An unresolved answer is
     shown, never picked for the operator. */
  function answerSelect(topic, subjectType, subjectId, concept, label, ans, pairs) {
    var key = answerKey(subjectType, subjectId, concept);
    var pending = S.edits[key];
    if (ans.state === "unresolved") return '<span class="qv2-field">' + esc(label) + " " + answerText(ans) + "</span>";
    var cur = pending ? pending.value : (ans.state === "value" ? ans.value : "");
    return '<label class="qv2-field">' + esc(label) + ' <select data-qv2-answer="' + esc(key) +
      '" data-topic="' + esc(topic) + '"' + (pending ? ' class="qv2-dirty"' : "") + ">" +
      options(pairs, cur, "— not recorded —") + "</select></label>";
  }

  function qualifierBoxes(checked) {
    return '<span class="qv2-quals">' + model().QUALIFIERS.map(function (q) {
      return '<label><input type="checkbox" data-f="q" value="' + esc(q[0]) + '"' +
        ((checked || []).indexOf(q[0]) !== -1 ? " checked" : "") + "> " + esc(q[1]) + "</label>";
    }).join(" ") + "</span>";
  }
  function periodText(p) {
    if (!p) return "";
    return (p.start ? "from " + p.start.text : "") + (p.start && p.end ? " " : "") + (p.end ? "until " + p.end.text : "");
  }

  /* The names of one person: each editable in place (whole), one preferred,
     and an "add a name" row. Former names are kept and marked. */
  function namesBlock(personId) {
    var p = S.view.people[personId];
    var saved = p ? p.names : [];
    var html = saved.map(function (n) {
      var pend = S.edits["nameedit:" + n.id];
      var pref = S.edits["preferred:" + personId] ? S.edits["preferred:" + personId].nameId : (p.preferredNameId || null);
      return '<div class="qv2-name"><input type="text" data-qv2-name="' + esc(personId + ":" + n.id) + '" value="' +
        esc(pend ? pend.fullText : n.fullText) + '"' + (pend ? ' class="qv2-dirty"' : "") + "> <small>" +
        esc((NAME_KINDS.filter(function (k) { return k[0] === (n.kind || "current"); })[0] || [0, n.kind])[1]) +
        (n.use ? " · " + esc(n.use.replace(/_/g, " ")) : "") + "</small>" +
        ' <label class="qv2-pref"><input type="radio" name="qv2pref-' + esc(personId) + '" data-qv2-preferred="' +
        esc(personId + ":" + n.id) + '"' + (pref === n.id ? " checked" : "") + "> preferred</label></div>";
    }).join("");
    html += pendingOf("newname").filter(function (e) { return e.personId === personId; }).map(function (e) {
      return '<div class="qv2-name">' + esc(e.fullText) + " <small>" + esc(e.nameKind) + "</small>" +
        unsaved("newname:" + e.nameId) + "</div>";
    }).join("");
    var nk = "name:" + personId;
    html += '<div class="qv2-form qv2-inline" data-qv2-form="name" data-person="' + esc(personId) + '">' +
      '<input type="text" data-f="fullText" value="' + esc(fv(nk, "fullText", "")) + '" placeholder="Another name, written whole"> ' +
      '<select data-f="nameKind">' + options(NAME_KINDS, fv(nk, "nameKind", "current") || "current", null) + "</select> " +
      '<button type="button" data-qv2-action="add-name" data-person="' + esc(personId) + '">Add name</button></div>';
    return html;
  }

  /* One relationship to the narrator, saved or pending. */
  function relCard(rel) {
    var R = model().ROLES, v = S.view;
    if (rel.pending) {
      var e = rel.edit;
      return '<div class="qv2-card" data-qv2-rel="' + esc(e.relId) + '"><strong>' + esc(personName(e.personId)) +
        "</strong> — " + esc(R[e.role].label) +
        (e.value.describedAs ? " (" + esc(e.value.describedAs) + ")" : "") +
        (e.value.qualifiers ? " · " + esc(e.value.qualifiers.join(", ")) : "") +
        (e.value.narratorLabel ? " · called “" + esc(e.value.narratorLabel) + "”" : "") +
        (e.value.period ? " · " + esc(periodText(e.value.period)) : "") +
        (e.lineage ? " · " + esc(valueText(e.lineage)) : "") + unsaved("newrel:" + e.relId) + "</div>";
    }
    var r = rel.rel, p = v.people[r.withPersonId], ed = S.edits["reledit:" + r.id];
    var shown = ed ? ed.after : r.raw;
    var head = '<div class="qv2-card" data-qv2-rel="' + esc(r.id) + '"><strong>' + esc(personName(r.withPersonId)) +
      "</strong> — " + esc((R[r.detailedRole] || { label: r.kind }).label) +
      (shown.describedAs ? " (" + esc(shown.describedAs) + ")" : "") +
      (shown.qualifiers ? " · " + esc(shown.qualifiers.join(", ")) : "") +
      (shown.narratorLabel ? " · called “" + esc(shown.narratorLabel) + "”" : "") +
      (shown.period ? " · " + esc(periodText(shown.period)) : "") +
      (p ? " · " + answerText(p.lifeStatus) : "") + (ed ? unsaved("reledit:" + r.id) : "");
    if (S.openRel !== r.id) {
      return head + ' <button type="button" data-qv2-action="open-rel" data-rel="' + esc(r.id) + '">Details</button></div>';
    }
    var per = shown.period || {}, rk = "rel:" + r.id;
    var rv = function (f, d) { return esc(fv(rk, f, d)); };
    return head + '<div class="qv2-form" data-qv2-form="rel" data-rel="' + esc(r.id) + '">' +
      "<h5>Names</h5>" + namesBlock(r.withPersonId) +
      (p ? answerSelect(S.topic, "person", r.withPersonId, "person.life_status", "Living?", p.lifeStatus, LIFE_STATUS) : "") +
      answerSelect(S.topic, "relationship", r.id, "relationship.qualifier.lineage_side", "Side of the family",
                   r.lineageSide, LINEAGE) +
      '<div class="qv2-field">Qualifiers ' + qualifierBoxes(fv(rk, "qualifiers", shown.qualifiers || [])) + "</div>" +
      (r.kind === "other" ? '<label class="qv2-field">Described as <input type="text" data-f="describedAs" value="' +
        rv("describedAs", shown.describedAs || "") + '"></label>' : "") +
      '<label class="qv2-field">What the narrator calls them <input type="text" data-f="narratorLabel" value="' +
        rv("narratorLabel", shown.narratorLabel || "") + '"></label>' +
      '<label class="qv2-field">From <input type="text" data-f="from" value="' + rv("from", per.start ? per.start.text : "") +
        '" placeholder="as said, e.g. 1962 or about 1962"></label>' +
      '<label class="qv2-field">Until <input type="text" data-f="until" value="' + rv("until", per.end ? per.end.text : "") + '"></label>' +
      '<button type="button" data-qv2-action="keep-rel" data-rel="' + esc(r.id) + '">Keep these changes</button> ' +
      '<button type="button" data-qv2-action="close-rel">Close</button>' +
      '<p class="qv2-hint">To say this person is ALSO something else to the narrator (a grandmother who raised them), ' +
      "add that below and choose them from \"someone already recorded\" — they stay one person.</p></div></div>";
  }

  function relsForTopic(t) {
    var roles = TOPIC_ROLES[t] || [], out = [];
    Object.keys(S.view.relationships).forEach(function (id) {
      var r = S.view.relationships[id];
      if (roles.indexOf(r.detailedRole) !== -1 || (t === "wider" && r.detailedRole === "mentee")) out.push({ rel: r });
    });
    pendingOf("newrel").forEach(function (e) { if (roles.indexOf(e.role) !== -1) out.push({ pending: true, edit: e }); });
    return out;
  }

  function everyonePickable() {
    var nid = S.view.narratorPersonId, out = [];
    Object.keys(S.view.people).forEach(function (id) { if (id !== nid) out.push([id, personName(id)]); });
    pendingOf("newperson").forEach(function (e) { out.push([e.personId, e.fullText + " (unsaved)"]); });
    return out;
  }

  function addForm(t) {
    var R = model().ROLES;
    var roles = TOPIC_ROLES[t].map(function (k) { return [k, R[k].label]; });
    var err = S.formError && S.formError.topic === t ? '<div class="qv2-msg qv2-error" data-qv2-form-error>' +
      esc(S.formError.text) + "</div>" : "";
    var k = "person:" + t, g = function (f) { return esc(fv(k, f, "")); };
    return '<div class="qv2-form qv2-add" data-qv2-form="person" data-topic="' + esc(t) + '"><h4>Add someone</h4>' + err +
      '<label class="qv2-field">Who <select data-f="person"><option value="">— a new person —</option>' +
        options(everyonePickable(), fv(k, "person", ""), null) + "</select></label>" +
      '<label class="qv2-field">Name (new person) <input type="text" data-f="fullText" value="' + g("fullText") +
        '" placeholder="Whole name, as it is said"></label>' +
      '<label class="qv2-field">Relationship to the narrator <select data-f="role">' +
        options(roles, fv(k, "role", ""), "— choose —") + "</select></label>" +
      '<label class="qv2-field">Described as (for "Other") <input type="text" data-f="describedAs" value="' + g("describedAs") + '"></label>' +
      '<div class="qv2-field">Qualifiers ' + qualifierBoxes(fv(k, "qualifiers", [])) + "</div>" +
      '<label class="qv2-field">Side of the family <select data-f="lineage">' + options(LINEAGE, fv(k, "lineage", ""), "— not recorded —") + "</select></label>" +
      '<label class="qv2-field">What the narrator calls them <input type="text" data-f="narratorLabel" value="' + g("narratorLabel") + '"></label>' +
      '<label class="qv2-field">Living? (new person) <select data-f="lifeStatus">' + options(LIFE_STATUS, fv(k, "lifeStatus", ""), "— not recorded —") + "</select></label>" +
      '<label class="qv2-field">From <input type="text" data-f="from" value="' + g("from") + '" placeholder="as said"></label>' +
      '<label class="qv2-field">Until <input type="text" data-f="until" value="' + g("until") + '"></label>' +
      '<button type="button" data-qv2-action="add-person" data-topic="' + esc(t) + '">Add</button></div>';
  }

  function peopleTopic(t, N) {
    var cards = relsForTopic(t).map(relCard);
    var html = cards.length ? cards.join("") : '<p class="qv2-blank">Nobody recorded yet.</p>';
    if (t === "family" && N) {
      html += answerInput(t, "person", N.id, "person.reported_count.siblings",
                          "How many siblings the narrator says they had (a count, even if not all are named)",
                          N.reportedCounts.siblings);
    }
    if (t === "partners") {
      html += "<h4>Unions</h4>" + list(S.view.topics.partners.unions.map(eventLine));
      if (N) {
        html += answerInput(t, "person", N.id, "person.reported_count.children", "Number of children, as said",
                            N.reportedCounts.children) +
                answerInput(t, "person", N.id, "person.reported_count.grandchildren", "Number of grandchildren, as said",
                            N.reportedCounts.grandchildren);
      }
    }
    if (t === "wider") {
      var T = S.view.topics.wider;
      var others = T.otherPeople.map(function (id) { return esc(personName(id)); });
      var indirect = Object.keys(S.view.relationships).filter(function (id) {
        return S.view.relationships[id].detailedRole === "indirect"; }).map(function (id) {
        var r = S.view.relationships[id];
        return esc(personName(r.subjectPersonId)) + " → " + esc(r.kind.replace(/_of$/, "").replace(/_/g, " ")) +
          " of " + esc(personName(r.otherPersonId)); });
      html += "<h4>Other people in the record</h4>" + list(others.concat(indirect)) +
        "<h4>Animals</h4>" + list(T.animals.map(function (id) {
          var a = S.view.animals[id]; return esc(a.name || "(unnamed)") + (a.species ? " · " + esc(a.species) : ""); }));
    }
    return html + addForm(t);
  }

  function topicBody(t) {
    var v = S.view, N = v.people[v.narratorPersonId] || null, T = v.topics[t];
    switch (t) {
      case "narrator":
        if (!N) return '<p class="qv2-blank">Nothing recorded yet.</p>';
        return (N.notYetInRecord ? '<p class="qv2-new" data-qv2-new-narrator>This narrator has nothing in the ' +
                 "Life Record yet. The first Save creates their record.</p>" : "") +
          "<h4>Names</h4>" + namesBlock(N.id) +
          "<h4>Pronouns</h4>" + list(N.pronouns.map(function (p) { return esc(p.value); }).concat(
            pendingOf("pronoun").map(function (e) { return esc(e.value) + unsaved("pronoun:" + e.assertionId); }))) +
          '<div class="qv2-form qv2-inline" data-qv2-form="pronoun"><input type="text" data-f="pronoun" value="' +
            esc(fv("pronoun:", "pronoun", "")) + '" placeholder="Pronouns, as the narrator uses them"> ' +
            '<button type="button" data-qv2-action="add-pronoun">Add</button></div>' +
          "<h4>Birth</h4><p>" + answerText(N.birth.date) +
            (N.birth.placeLabel ? " · " + esc(N.birth.placeLabel) : "") + "</p>" +
          answerInput("narrator", "person", N.id, "person.birth.order", "Birth order, as the narrator describes it",
                      N.birthOrder) +
          "<h4>Current home</h4>" + list(T.currentHomes.map(eventLine));
      case "family":
      case "partners":
      case "wider":
        return peopleTopic(t, N);
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
    ".qv2-head button,.qv2 button{padding:.3rem .8rem;border-radius:4px;border:1px solid #475569;background:#1e293b;color:#e2e8f0;cursor:pointer}",
    ".qv2-head button[data-qv2-action=save]:not([disabled]){background:#2563eb;border-color:#2563eb}",
    ".qv2-head button[disabled]{opacity:.45;cursor:default}",
    ".qv2-msg,.qv2-conflict,.qv2-refused{grid-column:1/-1;padding:.45rem .7rem;border-radius:4px}",
    ".qv2-ok{background:#064e3b}.qv2-info{background:#1e3a5f}.qv2-error,.qv2-refused{background:#7f1d1d}",
    ".qv2-conflict-msg,.qv2-conflict{background:#78350f}",
    ".qv2-nav{display:flex;flex-direction:column;gap:.2rem}",
    ".qv2-nav button{text-align:left;padding:.4rem .6rem;border:0;border-radius:4px;background:transparent;color:#cbd5e1;cursor:pointer}",
    ".qv2-nav button.qv2-active{background:#1e293b;color:#fff;font-weight:600}.qv2-dot{color:#fbbf24}",
    ".qv2-topic h3{margin:.2rem 0 .6rem}.qv2-topic h4{margin:.8rem 0 .3rem;color:#94a3b8;font-size:.8rem;text-transform:uppercase}",
    ".qv2-field{display:block;margin:.5rem 0}.qv2-field input,.qv2-field select,.qv2-name input,.qv2-inline input,.qv2-inline select{margin-left:.5rem;padding:.25rem .4rem;min-width:14rem;background:#0f172a;color:#e2e8f0;border:1px solid #475569;border-radius:4px}",
    ".qv2-quals label{margin-right:.6rem;white-space:nowrap}.qv2-quals input{min-width:0;margin:0}",
    ".qv2-dirty{border-color:#fbbf24!important}.qv2-blank{color:#64748b;font-style:italic}",
    ".qv2-card{padding:.5rem .6rem;margin:.35rem 0;border:1px solid #334155;border-radius:6px}",
    ".qv2-form{margin-top:.5rem}.qv2-add{margin-top:1rem;padding:.6rem;border:1px dashed #475569;border-radius:6px}",
    ".qv2-unsaved{color:#fbbf24;font-size:.78rem}.qv2 .qv2-undo{padding:0 .4rem;font-size:.75rem}",
    ".qv2-hint{color:#94a3b8;font-size:.8rem}.qv2-name{margin:.25rem 0}.qv2-pref{margin-left:.6rem;font-size:.8rem}",
    ".qv2-new{color:#93c5fd}.qv2-nav button[disabled]{opacity:.45;cursor:default}",
    ".qv2-legacy-table th{text-align:left;color:#94a3b8;padding-right:1rem;font-weight:normal}",
    ".qv2-family ul{margin:.2rem 0 .6rem}",
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
      ' <label class="qv2-rev">These changes come from <select data-qv2-provenance>' +
        Object.keys(PROVENANCE).map(function (k) {
          return '<option value="' + k + '"' + (k === S.provenance ? " selected" : "") + ">" + esc(PROVENANCE[k].label) + "</option>";
        }).join("") + "</select></label>" +
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
      (S.formError && S.formError.topic === S.topic && ["family", "partners", "wider"].indexOf(S.topic) === -1
        ? '<div class="qv2-msg qv2-error" data-qv2-form-error>' + esc(S.formError.text) + "</div>" : "") +
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
      if (t) { S.topic = t.getAttribute("data-qv2-topic"); S.openRel = null; S.formError = null; paint(); return; }   // navigation writes nothing
      var u = ev.target.closest("[data-qv2-undo]");
      if (u) { undo(u.getAttribute("data-qv2-undo")); return; }
      var a = ev.target.closest("[data-qv2-action]");
      if (!a || a.disabled) return;
      var act = a.getAttribute("data-qv2-action");
      if (act === "save") save();
      else if (act === "discard") discard();
      else if (act === "add-person") addPersonOrRelationship(a.getAttribute("data-topic"), a.closest("[data-qv2-form]"));
      else if (act === "open-rel") { S.openRel = a.getAttribute("data-rel"); forget("rel:" + S.openRel); S.formError = null; paint(); }
      else if (act === "close-rel") { forget("rel:" + S.openRel); S.openRel = null; paint(); }
      else if (act === "keep-rel") keepRelationshipEdit(a.getAttribute("data-rel"), a.closest("[data-qv2-form]"));
      else if (act === "add-name") addName(a.getAttribute("data-person"), a.closest("[data-qv2-form]"));
      else if (act === "add-pronoun") addPronoun(a.closest("[data-qv2-form]"));
    });
    var remember = function (ev) {
      var fm = ev.target.closest && ev.target.closest("[data-qv2-form]");
      if (fm && ev.target.hasAttribute("data-f")) rememberForm(fm);
    };
    root_.addEventListener("input", remember);
    root_.addEventListener("change", function (ev) {
      remember(ev);
      var prov = ev.target.closest("[data-qv2-provenance]");
      if (prov) { S.provenance = PROVENANCE[prov.value] ? prov.value : "operator"; writeDraft(); return; }
      var nm = ev.target.closest("[data-qv2-name]");
      if (nm) { var np = nm.getAttribute("data-qv2-name").split(":"); editName(np[0], np[1], nm.value); paint(); return; }
      var pr = ev.target.closest("[data-qv2-preferred]");
      if (pr) { var pp = pr.getAttribute("data-qv2-preferred").split(":"); setPreferred(pp[0], pp[1]); paint(); return; }
      var inp = ev.target.closest("[data-qv2-answer]"); if (!inp) return;
      var parts = inp.getAttribute("data-qv2-answer").split(":");
      var ans = lookupAnswer(parts[0], parts[1], parts[2]);
      if (!ans) return;
      S.formError = null;
      setAnswerEdit(inp.getAttribute("data-topic"), parts[0], parts[1], parts[2], ans, inp.value);
      paint();
    });
  }

  function lookupAnswer(subjectType, subjectId, concept) {
    if (subjectType === "relationship") {
      var r = S.view.relationships[subjectId];
      return r && concept === "relationship.qualifier.lineage_side" ? r.lineageSide : null;
    }
    if (subjectType !== "person") return null;
    var p = S.view.people[subjectId]; if (!p) return null;
    var map = { "person.birth.order": p.birthOrder, "person.life_status": p.lifeStatus };
    if (COUNT_CONCEPTS[concept]) return p.reportedCounts[COUNT_CONCEPTS[concept]];
    return map[concept] || null;
  }

  /* ── Family: a DERIVED view of the Life Record (Batch C-3) ───────────
     Read-only. Family is no longer an editor: every person and relationship
     on it comes from GET /api/life-record, and "Edit in Questionnaire"
     opens the editor that writes the record. Nothing here writes. */
  /* Every Family render is a generation. A response is painted only if it
     belongs to the NEWEST request: checking that the narrator's box still
     exists is not enough, because A → B → A re-creates A's box and a slow
     first answer for A would then paint over the second (C-3 review). */
  var _famGen = 0;
  function renderFamilyView(container, pid, onEdit) {
    ensureCss();
    var myGen = ++_famGen;
    if (!pid) { container.innerHTML = '<p class="qv2-blank">Choose a narrator.</p>'; return; }
    container.innerHTML = '<div class="qv2-family" data-qv2-family="' + esc(pid) + '">Reading the Life Record…</div>';
    root.fetch(lifeRecordUrl(pid), { method: "GET" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (record) {
      if (myGen !== _famGen) return;                                   // a newer Family request owns the screen
      var box = container.querySelector('[data-qv2-family="' + pid + '"]'); if (!box) return;   // switched away
      var M = model(), v = M.fromRecord(record), R = M.ROLES;
      var name = function (id) { var p = v.people[id]; return p && p.names[0] ? p.names[0].fullText : "(name not yet in the Life Record)"; };
      var groups = [["Parents", ["parent"]], ["Raised or cared for the narrator", ["caregiver"]], ["Siblings", ["sibling"]],
                    ["Grandparents", ["grandparent"]], ["Spouses and partners", ["spouse", "partner"]],
                    ["Children", ["child"]], ["Grandchildren", ["grandchild"]],
                    ["Chosen family, friends and others", ["chosen_family", "friend", "mentor", "mentee", "cared_for", "other"]]];
      var html = "";
      groups.forEach(function (g) {
        var rows = Object.keys(v.relationships).map(function (id) { return v.relationships[id]; })
          .filter(function (r) { return g[1].indexOf(r.detailedRole) !== -1; })
          .map(function (r) {
            var p = v.people[r.withPersonId];
            return esc(name(r.withPersonId)) + (g[1].length > 1 ? " — " + esc((R[r.detailedRole] || {}).label || r.kind) : "") +
              (r.describedAs ? " (" + esc(r.describedAs) + ")" : "") +
              (r.qualifiers ? " · " + esc(r.qualifiers.join(", ")) : "") +
              (r.narratorLabel ? " · “" + esc(r.narratorLabel) + "”" : "") +
              (r.lineageSide.state === "value" ? " · " + esc(valueText(r.lineageSide.value)) : "") +
              (r.period ? " · " + esc(periodText(r.period)) : "") +
              (p && p.lifeStatus.state === "value" ? " · " + esc(valueText(p.lifeStatus.value)) : "");
          });
        if (rows.length) html += "<h4>" + esc(g[0]) + "</h4><ul>" + rows.map(function (x) { return "<li>" + x + "</li>"; }).join("") + "</ul>";
      });
      var nid = v.narratorPersonId;
      var counts = v.people[nid] ? v.people[nid].reportedCounts : null;
      if (counts) {
        var c = [["siblings", counts.siblings], ["children", counts.children], ["grandchildren", counts.grandchildren]]
          .filter(function (x) { return x[1].state === "value"; })
          .map(function (x) { return esc(x[1].value) + " " + x[0] + " (as said)"; });
        if (c.length) html += "<p>" + c.join(" · ") + "</p>";
      }
      box.innerHTML = '<p class="qv2-hint">Everyone here comes from the Life Record, revision ' + esc(v.revision) +
        '. To add or change someone, use the Questionnaire.</p>' +
        (html || '<p class="qv2-blank">No family or other people are recorded yet.</p>') +
        '<button type="button" data-qv2-family-edit>Edit in Questionnaire</button>';
      var b = box.querySelector("[data-qv2-family-edit]");
      if (b && onEdit) b.addEventListener("click", function () { onEdit("family"); });
    }).catch(function (e) {
      if (myGen !== _famGen) return;
      var box = container.querySelector('[data-qv2-family="' + pid + '"]');
      if (box) box.textContent = "The Life Record could not be read (" + e.message + "). Nothing was changed.";
    });
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

  var api_ = { render: render, renderEarlierAnswers: renderEarlierAnswers, renderFamilyView: renderFamilyView,
               _state: function () { return S; }, _save: save, _buildChanges: function () { return buildChanges(); } };
  if (typeof module !== "undefined" && module.exports) module.exports = api_;
  if (root) root.LorevoxQuestionnaireV2 = api_;
})(typeof window !== "undefined" ? window : this);
