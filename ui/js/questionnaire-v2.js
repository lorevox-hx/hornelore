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
    "person.reported_count.marriages": "marriages",
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
    if (!can(concept)) return;                          // fail closed (C-4C)
    if (concept === "person.life_status" && subjectType === "person") {
      var dv = S.edits[vitalKey("death", subjectId)];
      if (dv && dv.deceased) {                          // C-4E: the death edit already sets Deceased
        S.formError = { topic: topic, text: "A death is recorded for this person in an unsaved change, " +
                        "which also records them as deceased — undo that first to change this." };
        return;
      }
    }
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
                                status: last ? last.status : null, accepted: !!answer.accepted } };
    }
    writeDraft();
  }

  /* What the operator has typed into a form but not yet added. Kept in
     memory (not the draft — it is not an edit yet) so that a repaint caused
     by another field never wipes a half-filled form. */
  function formKey(form) {
    return form.getAttribute("data-qv2-form") + ":" + (form.getAttribute("data-topic") ||
      form.getAttribute("data-rel") || form.getAttribute("data-person") || form.getAttribute("data-event") || "");
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
      date: get("date"), place: get("place"), newPlaceLabel: get("newPlaceLabel"),
      partner: get("partner"), occKind: get("occKind"),
      current: (function () { var el = form.querySelector('[data-f="current"]'); return el ? !!el.checked : null; })(),
      homeType: get("homeType"),
      // C-4F review: one selector per recorded participant, keyed by who is there now
      swaps: (function () { var o = {};
        Array.prototype.slice.call(form.querySelectorAll('[data-f^="swap:"]')).forEach(function (el) {
          o[el.getAttribute("data-f").slice(5)] = String(el.value || ""); });
        return o; })(),
      qualifiers: Array.prototype.slice.call(form.querySelectorAll('[data-f="q"]'))
        .filter(function (x) { return x.checked; }).map(function (x) { return x.value; }),
    };
  }

  /* C-4C: the editor offers a control that writes a concept ONLY when the
     model's capability declaration (QV2_CAPABILITIES) lists that concept.
     Fail closed: undeclared → the value is shown, never editable here. */
  function can(concept) { return model().isEditableConcept(concept); }

  /* A period's two ends are SINGLE dates (C-4 contract). A refused date or a
     range typed into one end is a form error — never silently downgraded.

     `prior` is the STORED period of an existing relationship. An end whose
     text the operator did not change is carried as the stored object, byte for
     byte — re-parsing it would silently rewrite a legacy date (C-3's
     {text:"about 1989", value:null} would become 1989~) during an unrelated
     edit, and the server would rightly accept that as a changed end. */
  function periodOf(f, prior) {
    var P = model().parseDateText;
    var kept = function (typed, stored) {   // the operator did not touch this end
      var t = String(typed == null ? "" : typed).trim();
      return !!(t && stored && typeof stored === "object" &&
                t === String(stored.text == null ? "" : stored.text).trim());
    };
    var pr = prior && typeof prior === "object" ? prior : {};
    var keepStart = kept(f.from, pr.start), keepEnd = kept(f.until, pr.end);
    var start = keepStart ? pr.start : P(f.from), end = keepEnd ? pr.end : P(f.until), out = {};
    // Only an end the operator CHANGED is held to the contract here — the
    // same rule the writer applies (writer._check_period).
    var fresh = [[start, "From", keepStart], [end, "Until", keepEnd]].filter(function (x) { return x[0] && !x[2]; });
    var bad = fresh.filter(function (x) { return x[0].refuse; })[0];
    if (bad) return { error: bad[1] + ": " + bad[0].refuse };
    var rng = fresh.filter(function (x) { return x[0].value && x[0].value.indexOf("/") >= 0; })[0];
    if (rng) return { error: rng[1] + " is one date, not a range." };
    if (start) out.start = start;
    if (end) out.end = end;
    return Object.keys(out).length ? { period: out } : { period: null };
  }

  /* A relationship as the writer stores it: "subject is <kind> of other". */
  function relValue(role, personId, f, per) {
    var R = model().ROLES[role], nid = S.view.narratorPersonId;
    var v = { subjectPersonId: R.narratorIs === "other" ? personId : nid,
              otherPersonId: R.narratorIs === "other" ? nid : personId, kind: R.kind };
    if (f.describedAs) v.describedAs = f.describedAs;
    if (f.qualifiers && f.qualifiers.length) v.qualifiers = f.qualifiers.slice();
    if (f.narratorLabel) v.narratorLabel = f.narratorLabel;
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
    if (!can("relationship.kind")) return;
    if (!f.person && !can("person.name.full")) return;
    if (!can("person.life_status")) f.lifeStatus = "";
    if (!can("relationship.qualifier.lineage_side")) f.lineage = "";
    if (!can("relationship.period")) { f.from = ""; f.until = ""; }
    if (!f.role || !model().ROLES[f.role]) return err("Choose how this person is related to the narrator.");
    if (f.role === "other" && !f.describedAs) return err("Describe the relationship when it is \"Other\".");
    var personId = f.person;
    if (!personId && !f.fullText) return err("Write the person's name as it is said — whole, as one line.");
    if (personId === nid) return err("That is the narrator.");
    var pd = periodOf(f);
    if (pd.error) return err(pd.error);
    var isNew = !personId;
    if (isNew) personId = newId("qv2p-");
    var value = relValue(f.role, personId, f, pd.period);
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
    // No period control is offered when relationship.period is not editable:
    // the stored period is then carried exactly as it is, never dropped.
    var pd = can("relationship.period") ? periodOf(f, r.raw.period) : { period: r.raw.period || null };
    if (pd.error) { S.formError = { topic: S.topic, text: pd.error }; paint(); return; }
    var after = {};
    Object.keys(r.raw).forEach(function (k) { after[k] = r.raw[k]; });
    ["describedAs", "qualifiers", "narratorLabel", "period"].forEach(function (k) { delete after[k]; });
    if (f.describedAs) after.describedAs = f.describedAs;
    if (f.qualifiers.length) after.qualifiers = f.qualifiers;
    if (f.narratorLabel) after.narratorLabel = f.narratorLabel;
    if (pd.period) after.period = pd.period;
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
    if (!can("person.name.full")) return;
    if (f.nameKind === "also_known_as" && !can("person.name.alias")) return;
    if (!f.fullText) { S.formError = { topic: S.topic, text: "Write the name whole, as it is said." }; paint(); return; }
    var nameId = newId("qv2n-");
    S.edits["newname:" + nameId] = { kind: "newname", topic: S.topic, personId: personId, nameId: nameId,
      fullText: f.fullText, nameKind: f.nameKind || "current" };
    S.formError = null;
    forget("name:" + personId);
    writeDraft(); paint();
  }

  function editName(personId, nameId, text) {
    var p = S.view.people[personId]; if (!p || !can("person.name.full")) return;
    var n = p.names.filter(function (x) { return x.id === nameId; })[0]; if (!n) return;
    var key = "nameedit:" + nameId, t = String(text || "").trim();
    if (!t || t === n.fullText) delete S.edits[key];     // an empty box is not a removal
    else S.edits[key] = { kind: "nameedit", topic: S.topic, personId: personId, nameId: nameId,
                          before: model().rawName(n), fullText: t };
    writeDraft();
  }

  function setPreferred(personId, nameId) {
    var p = S.view.people[personId]; if (!p || !can("person.name.preferred")) return;
    var key = "preferred:" + personId;
    if (nameId === p.preferredNameId) delete S.edits[key];
    else S.edits[key] = { kind: "preferred", topic: S.topic, personId: personId, nameId: nameId,
                          before: p.notYetInRecord ? null : (p.preferredNameId || null) };
    writeDraft();
  }

  /* ── Birth and death (C-4E) ─────────────────────────────────────────
     Both are canonical EVENTS whose subject is the person: the date is an
     assertion on the event (person.birth.date / person.death.date), the place
     is the event's place_id. An existing occurrence is EXTENDED, never
     duplicated (the writer refuses a second one: rule "one birth and one death
     per person"). A place is chosen by ID or created as a NEW place — a
     matching label never means the same place. Recording a death also records
     the person deceased, in the same Save, when they are not already; marking
     someone deceased never creates a death. */
  var VITAL = {
    birth: { date: "person.birth.date", place: "person.birth.place", ref: "birthEventRef", label: "Birth" },
    death: { date: "person.death.date", place: "person.death.place", ref: "deathEventRef", label: "Death" },
  };
  function vitalKey(kind, pid) { return "vital:" + kind + ":" + pid; }

  function keepVital(personId, kind, form) {
    var V = VITAL[kind], p = S.view.people[personId]; if (!V || !p) return;
    var f = readForm(form), cur = p[kind], key = vitalKey(kind, personId);
    var err = function (t) { S.formError = { topic: S.topic, text: V.label + ": " + t }; paint(); };
    // the date — a SINGLE date under the C-4 contract, or left as it is
    var date = null, typed = can(V.date) ? f.date : "";
    if (typed) {
      var stored = cur.date && cur.date.state === "value" ? cur.date.value : null;
      if (cur.date && cur.date.state === "unresolved")
        return err("two accounts of this date are recorded — decide between them in review first.");
      if (!(stored && String(stored.text || "").trim() === typed)) {        // an unchanged date is not re-parsed
        date = model().parseDateText(typed);
        if (date && date.refuse) return err(date.refuse);
        if (date && date.value && date.value.indexOf("/") >= 0) return err("a " + kind + " is one date, not a range.");
      }
    }
    // the place — chosen by ID, or created new; never matched by its label
    var place = { mode: "keep" }, sel = can(V.place) ? f.place : "";
    if (sel === "new") {
      var label = String(f.newPlaceLabel || "").trim();
      if (!label) return err("write the new place's name, as it is said.");
      place = { mode: "new", placeId: newId("qv2pl-"), label: label };
    } else if (sel && sel.indexOf("existing:") === 0) {
      var pid2 = sel.slice("existing:".length);
      if (!S.view.places[pid2]) return err("that place is not in this record.");
      if (pid2 !== cur.placeId) place = { mode: "existing", placeId: pid2 };
    }
    if (!date && place.mode === "keep") {            // nothing said: nothing to keep, nothing invented
      delete S.edits[key]; S.formError = null; forget("vital-" + kind + ":" + personId); writeDraft(); paint(); return;
    }
    // a death needs the person deceased — added in the same Save when they are not already
    var deceased = null;
    if (kind === "death") {
      var ls = p.lifeStatus, pend = S.edits[answerKey("person", personId, "person.life_status")];
      if (pend) {
        if (pend.value !== "deceased") return err("this person is set to “" + pend.value + "” in an unsaved change — " +
                                                  "make that Deceased, or undo it, first.");
      } else if (ls.state === "unresolved") {
        return err("two accounts of whether this person is living are recorded — decide between them in review first.");
      } else if (!(ls.state === "value" && ls.value === "deceased")) {
        deceased = { assertionId: newId("qv2a-"),
                     basis: { state: ls.state, assertionId: ls.assertionId || null,
                              status: ((ls.history || []).filter(function (a) { return a.id === ls.assertionId; })[0] || {}).status || null,
                              accepted: !!ls.accepted } };
      }
    }
    var dateBasis = cur.date && cur.date.state === "value"
      ? { state: "value", assertionId: cur.date.assertionId,
          status: ((cur.date.history || []).filter(function (a) { return a.id === cur.date.assertionId; })[0] || {}).status || null,
          accepted: !!cur.date.accepted }
      : { state: "blank", assertionId: null, status: null };
    S.edits[key] = { kind: "vital", vitalKind: kind, topic: S.topic, personId: personId,
                     eventId: cur.eventId || newId("qv2e-"), isNew: !cur.eventId, eventBefore: cur.raw || null,
                     date: date, dateBasis: dateBasis, dateAssertionId: date ? newId("qv2a-") : null,
                     place: place, deceased: deceased };
    S.formError = null;
    if (place.mode === "new") {                        // suggest — never merge
      var same = Object.keys(S.view.places || {}).filter(function (id) {
        return String(S.view.places[id].label || "").trim().toLowerCase() === place.label.toLowerCase(); });
      if (same.length) S.message = { kind: "info", text: "A place called “" + place.label + "” is already recorded. " +
        "This creates a SEPARATE place — if it is the same one, undo and choose it from the list instead." };
    }
    forget("vital-" + kind + ":" + personId);
    writeDraft(); paint();
  }

  function vitalOps(e, src) {
    var V = VITAL[e.vitalKind], ops = [];
    var placeId = e.place.mode === "keep" ? (e.eventBefore ? e.eventBefore.place || null : null) : e.place.placeId;
    if (e.place.mode === "new") ops.push({ op: "add", path: "places/" + e.place.placeId, value: { label: e.place.label } });
    if (e.isNew) {
      var v = { type: e.vitalKind, participants: [{ person: e.personId, role: "subject" }] };
      if (placeId) v.place = placeId;
      ops.push({ op: "add", path: "events/" + e.eventId, value: v });
      ops.push({ op: "set", path: "people/" + e.personId + "/" + V.ref, value: e.eventId, expectedPrevious: null });
    } else if (e.place.mode !== "keep") {
      var after = {}; Object.keys(e.eventBefore).forEach(function (k) { after[k] = e.eventBefore[k]; });
      after.place = placeId;
      ops.push({ op: "set", path: "events/" + e.eventId, value: after, expectedPrevious: e.eventBefore });
    }
    if (e.date) {
      ops = ops.concat(answerOps({ kind: "vital", newAssertionId: idOf(e, "dateAssertionId"), basis: e.dateBasis,
                                   subjectType: "event", subjectId: e.eventId, concept: V.date, value: e.date }, src));
    }
    if (e.deceased) {
      ops = ops.concat(answerOps({ kind: "vital", newAssertionId: e.deceased.assertionId, basis: e.deceased.basis,
                                   subjectType: "person", subjectId: e.personId, concept: "person.life_status",
                                   value: "deceased" }, src));
    }
    return ops;
  }

  /* ── Homes, unions and separations (C-4F) ────────────────────────────
     Each is its OWN occurrence — an event with its own id. A home is a `move`
     event (the narrator its resident): its place is the event's place, its
     period an event.residence.period assertion under the C-4 contract, where
     "to present" (`/..`) is stated as ongoing and "to ?" (`/`) is an unknown
     end — a missing end is never read as current. A union and a separation
     are separate events with the same two participants: the same pair NEVER
     means the same occurrence (married, divorced, remarried = three events),
     and a separation does not touch the union it ends. The relationship's own
     period is a different, stated fact and is not derived from these.
     Places are chosen by id or created new, never matched by name. */
  var OCC = {
    move:       { date: "event.residence.period", place: "event.residence.place", role: "resident",
                  interval: true, label: "Home" },
    union:      { date: "event.union.date", place: "event.union.place", role: "partner",
                  interval: false, label: "Union", partner: "event.union.participant" },
    separation: { date: "event.separation.date", place: null, role: "partner",
                  interval: false, label: "Separation", partner: "event.separation.participant" },
  };

  function occPlace(f, concept, currentId, err) {
    var sel = concept && can(concept) ? f.place : "";
    if (sel === "new") {
      var label = String(f.newPlaceLabel || "").trim();
      if (!label) return err("write the new place's name, as it is said.");
      return { mode: "new", placeId: newId("qv2pl-"), label: label };
    }
    if (sel && sel.indexOf("existing:") === 0) {
      var id = sel.slice("existing:".length);
      if (!S.view.places[id]) return err("that place is not in this record.");
      if (id !== currentId) return { mode: "existing", placeId: id };
    }
    return { mode: "keep" };
  }

  function keepOccurrence(form, eventId) {
    var f = readForm(form), nid = S.view.narratorPersonId;
    var ev = eventId ? S.view.events[eventId] : null;
    var kind = ev ? ev.type : (form.getAttribute("data-kind") || f.occKind);
    var C = OCC[kind]; if (!C) return;
    var err = function (t) { S.formError = { topic: S.topic, text: C.label + ": " + t }; paint(); return null; };
    var partnerId = null;
    if (!ev && C.partner) {
      if (!can(C.partner)) return;
      partnerId = f.partner;
      if (!partnerId || !S.view.people[partnerId] || partnerId === nid) return err("choose who this is with.");
    }
    // the date or period — under the C-4 contract; an unchanged stored text is not re-parsed
    var date = null, typed = can(C.date) ? f.date : "", cur = ev ? ev.date : null;
    if (typed) {
      var stored = cur && cur.state === "value" ? cur.value : null;
      if (cur && cur.state === "unresolved") return err("two accounts of this date are recorded — decide between them in review first.");
      if (!(stored && String(stored.text || "").trim() === typed)) {
        date = model().parseDateText(typed);
        if (date && date.refuse) { return err(date.refuse); }  // C-4F: never downgraded to words
        if (!C.interval && date && date.value && date.value.indexOf("/") >= 0) return err("this is one date, not a range.");
      }
    }
    var place = occPlace(f, C.place, ev ? ev.placeId : null, err);
    if (place === null) return;
    /* A home is current ONLY when the operator says so (the box), never from
       the period (C-4F). `current` is null when unchanged. What THIS edit
       states must not contradict itself: a current home with an ENDED period,
       or a period said to run "to present" on a home that is not current. A
       contradiction already stored, untouched by this edit, never blocks an
       unrelated change (no writer rule; several homes may be current). */
    var current = null;
    if (kind === "move" && f.current !== null && can(C.date)) {
      var was = !!(ev && ev.attributes && ev.attributes.current === true);
      if (f.current !== was) current = f.current;
      var isNow = f.current;
      var storedV = cur && cur.state === "value" && cur.value ? String(cur.value.value || "") : "";
      var pv = date ? String(date.value || "") : storedV;
      var slash = pv.indexOf("/"), end = slash >= 0 ? pv.slice(slash + 1) : null;
      if ((current === true || (date && isNow)) && end !== null && end !== "" && end !== "..")
        return err("a current home cannot have a period that has ended — correct the period, or untick current.");
      if (date && !isNow && end === "..")
        return err("a period that runs “to present” is a current home — tick Current, or give the period its end.");
      if (current === false && !date && /\/\.\.$/.test(storedV))
        return err("this home's period runs “to present” — correct the period as well, or keep it current.");
    }
    /* C-4F review — correcting who took part. One selector per recorded
       non-narrator participant; each changes ONLY that participant, every
       other participant and role is kept. Nobody may appear twice. */
    var swaps = {}, nSwaps = 0, derived = [];
    if (ev && C.partner && can(C.partner)) {
      var present = (ev.participants || []).map(function (x) { return x.personId; }), taken = {};
      var fs = f.swaps || {};
      for (var old in fs) {
        var nw = fs[old];
        if (!nw || nw === old || old === nid || present.indexOf(old) === -1) continue;
        if (!S.view.people[nw] || nw === nid) return err("choose who this is with.");
        if (present.indexOf(nw) !== -1 || taken[nw])
          return err(personName(nw) + " is already in this " + C.label.toLowerCase() + " — nobody is recorded in it twice.");
        taken[nw] = true; swaps[old] = nw; nSwaps++;
      }
      if (nSwaps) {
        // a relationship DERIVED from this occurrence follows the correction in the same Save
        var afterPeople = present.map(function (x) { return swaps[x] || x; }), stale = false;
        Object.keys(S.view.relationships || {}).forEach(function (rid) {
          var r = S.view.relationships[rid].raw;
          if (!r || r.basis !== "derived_from_event" || r.derivedFromEventId !== eventId) return;
          var a = swaps[r.subjectPersonId] || r.subjectPersonId, b = swaps[r.otherPersonId] || r.otherPersonId;
          if (a === b || afterPeople.indexOf(a) === -1 || afterPeople.indexOf(b) === -1) { stale = true; return; }
          if (a !== r.subjectPersonId || b !== r.otherPersonId) {
            var nr = {}; Object.keys(r).forEach(function (k) { nr[k] = r[k]; });
            nr.subjectPersonId = a; nr.otherPersonId = b;
            derived.push({ relId: rid, before: r, after: nr });
          }
        });
        if (stale) return err("a relationship derived from this " + C.label.toLowerCase() +
                              " would no longer match its people — resolve it in review first.");
      }
    }
    var homeType = null;
    if (!ev && kind === "move" && f.homeType && can("event.residence.type")) homeType = f.homeType;
    var key = "occ:" + (eventId || "");
    if (ev && !date && place.mode === "keep" && current === null && !nSwaps) {   // nothing changed on this occurrence
      delete S.edits[key]; S.formError = null; forget("occ:" + eventId); writeDraft(); paint(); return;
    }
    if (!ev && kind === "move" && !date && place.mode === "keep") return err("say where, or when, or both.");
    if (!ev && current === false) current = null;         // a new home is simply not marked current
    var id = eventId || newId("qv2e-");
    if (!ev) key = "occ:" + id;
    var basis = cur && cur.state === "value"
      ? { state: "value", assertionId: cur.assertionId, accepted: !!cur.accepted,
          status: ((cur.history || []).filter(function (a) { return a.id === cur.assertionId; })[0] || {}).status || null }
      : { state: "blank", assertionId: null, status: null };
    S.edits[key] = { kind: "occ", occKind: kind, topic: S.topic, eventId: id, isNew: !ev,
                     eventBefore: ev ? ev.raw : null, partnerId: partnerId,
                     date: date, dateBasis: basis, dateAssertionId: date ? newId("qv2a-") : null, place: place,
                     current: current, swaps: nSwaps ? swaps : null, derived: derived,
                     homeType: homeType, homeTypeAssertionId: homeType ? newId("qv2a-") : null };
    S.formError = null;
    if (place.mode === "new") {                        // suggest — never merge
      var same = Object.keys(S.view.places || {}).filter(function (pid) {
        return String(S.view.places[pid].label || "").trim().toLowerCase() === place.label.toLowerCase(); });
      if (same.length) S.message = { kind: "info", text: "A place called “" + place.label + "” is already recorded. " +
        "This creates a SEPARATE place — if it is the same one, undo and choose it from the list instead." };
    }
    forget(form.getAttribute("data-qv2-form") + ":" + (form.getAttribute("data-event") || form.getAttribute("data-topic") || ""));
    writeDraft(); paint();
  }

  function occOps(e, src) {
    var C = OCC[e.occKind], nid = S.view.narratorPersonId, ops = [];
    var placeId = e.place.mode === "keep" ? (e.eventBefore ? e.eventBefore.place || null : null) : e.place.placeId;
    if (e.place.mode === "new") ops.push({ op: "add", path: "places/" + e.place.placeId, value: { label: e.place.label } });
    if (e.isNew) {
      var parts = [{ person: nid, role: C.role }];
      if (e.partnerId) parts.push({ person: e.partnerId, role: C.role });
      var v = { type: e.occKind, participants: parts };
      if (placeId) v.place = placeId;
      if (e.current === true) v.attributes = { current: true };
      ops.push({ op: "add", path: "events/" + e.eventId, value: v });
    } else if (e.place.mode !== "keep" || (e.current !== null && e.current !== undefined) || e.swaps) {
      // ONE set on the SAME event (its id never changes — stories point at it),
      // carrying every other field and attribute exactly as it was
      var after = {}; Object.keys(e.eventBefore).forEach(function (k) { after[k] = e.eventBefore[k]; });
      after.place = placeId;
      if (!after.place) delete after.place;
      if (e.current !== null && e.current !== undefined) {
        var attrs = {}; Object.keys(e.eventBefore.attributes || {}).forEach(function (k) { attrs[k] = e.eventBefore.attributes[k]; });
        if (e.current) attrs.current = true; else delete attrs.current;
        if (Object.keys(attrs).length) after.attributes = attrs; else delete after.attributes;
      }
      if (e.swaps) {        // only the corrected participant changes; every other one, and every role, is kept
        after.participants = e.eventBefore.participants.map(function (x) {
          return { person: e.swaps[x.person] || x.person, role: x.role }; });
      }
      ops.push({ op: "set", path: "events/" + e.eventId, value: after, expectedPrevious: e.eventBefore });
      (e.derived || []).forEach(function (d) {     // the derived relationship follows its event, same Save
        ops.push({ op: "set", path: "relationships/" + d.relId, value: d.after, expectedPrevious: d.before });
      });
    }
    if (e.isNew && e.homeType) {                     // the new home's kind, in the same Save as the home
      ops.push(assertionOp(idOf(e, "homeTypeAssertionId"), "event", e.eventId, "event.residence.type", e.homeType, src));
    }
    if (e.date) {
      ops = ops.concat(answerOps({ kind: "occ", newAssertionId: idOf(e, "dateAssertionId"), basis: e.dateBasis,
                                   subjectType: "event", subjectId: e.eventId, concept: C.date, value: e.date }, src));
    }
    return ops;
  }

  function addPronoun(form) {
    var f = form.querySelector('[data-f="pronoun"]'), t = f ? String(f.value || "").trim() : "";
    if (!t || !can("person.pronouns")) return;
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
    var ops = [
      assertionOp(id, edit.subjectType, edit.subjectId, edit.concept, edit.value, src, { supersedes: old }),
      { op: "set", path: "assertions/" + old + "/supersededBy", value: id, expectedPrevious: null },
      { op: "set", path: "assertions/" + old + "/status", value: "superseded",
        expectedPrevious: edit.basis.status },
    ];
    // C-4E review: when the assertion being corrected is the one a human
    // EXPLICITLY ACCEPTED, the operator's correction moves that recorded
    // acceptance to the correction in the same Save — otherwise the decision
    // is left on a superseded assertion and the fact (a birth anchor, a life
    // status) resolves to nothing. Never inferred: only an acceptance that
    // exists is moved, and it carries the id it expects to replace.
    if (edit.basis.accepted) {
      ops.push({ op: "set", path: "acceptances/" + edit.subjectType + "/" + edit.subjectId + "/" + edit.concept,
                 value: id, expectedPrevious: old });
    }
    return ops;
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
      case "vital":
        return vitalOps(e, src);
      case "occ":
        return occOps(e, src);
    }
    return [];
  }

  // People before the names, relationships and answers that refer to them.
  var ORDER = { newperson: 0, newname: 1, nameedit: 2, preferred: 3, newrel: 4, reledit: 5, vital: 6, occ: 7, answer: 8, pronoun: 9 };

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
    var editable = ans.state !== "unresolved" && can(concept);
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
    if (ans.state === "unresolved" || !can(concept))
      return '<span class="qv2-field">' + esc(label) + " " + answerText(ans) + "</span>";
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
      return '<div class="qv2-name">' + (can("person.name.full")
          ? '<input type="text" data-qv2-name="' + esc(personId + ":" + n.id) + '" value="' +
            esc(pend ? pend.fullText : n.fullText) + '"' + (pend ? ' class="qv2-dirty"' : "") + ">"
          : esc(n.fullText)) + " <small>" +
        esc((NAME_KINDS.filter(function (k) { return k[0] === (n.kind || "current"); })[0] || [0, n.kind])[1]) +
        (n.use ? " · " + esc(n.use.replace(/_/g, " ")) : "") + "</small>" +
        (can("person.name.preferred")
          ? ' <label class="qv2-pref"><input type="radio" name="qv2pref-' + esc(personId) + '" data-qv2-preferred="' +
            esc(personId + ":" + n.id) + '"' + (pref === n.id ? " checked" : "") + "> preferred</label>"
          : (pref === n.id ? " <small>(preferred)</small>" : "")) + "</div>";
    }).join("");
    html += pendingOf("newname").filter(function (e) { return e.personId === personId; }).map(function (e) {
      return '<div class="qv2-name">' + esc(e.fullText) + " <small>" + esc(e.nameKind) + "</small>" +
        unsaved("newname:" + e.nameId) + "</div>";
    }).join("");
    var nk = "name:" + personId;
    if (!can("person.name.full")) return html;
    var kinds = NAME_KINDS.filter(function (k) { return k[0] !== "also_known_as" || can("person.name.alias"); });
    html += '<div class="qv2-form qv2-inline" data-qv2-form="name" data-person="' + esc(personId) + '">' +
      '<input type="text" data-f="fullText" value="' + esc(fv(nk, "fullText", "")) + '" placeholder="Another name, written whole"> ' +
      '<select data-f="nameKind">' + options(kinds, fv(nk, "nameKind", "current") || "current", null) + "</select> " +
      '<button type="button" data-qv2-action="add-name" data-person="' + esc(personId) + '">Add name</button></div>';
    return html;
  }

  /* Birth / death of one person (C-4E): what is recorded, and — when the
     capability declaration allows — a form for the date and the place. The
     place is chosen from the record BY ID (same-named places are told apart by
     their record id) or created new; nothing is matched by its label. */
  function placeChoices(currentId) {
    var P = S.view.places || {}, count = {};
    var norm = function (l) { return String(l || "").trim().toLowerCase(); };
    Object.keys(P).forEach(function (id) { count[norm(P[id].label)] = (count[norm(P[id].label)] || 0) + 1; });
    return Object.keys(P).map(function (id) {
      var l = P[id].label || "(unnamed place)";
      return ["existing:" + id, l + (count[norm(l)] > 1 ? " — record " + id.slice(-6) : "") +
                                (id === currentId ? " (current)" : "")];
    });
  }
  function vitalSummary(e) {
    var parts = [];
    if (e.date) parts.push(e.date.text);
    if (e.place.mode === "new") parts.push("new place “" + e.place.label + "”");
    if (e.place.mode === "existing") parts.push((S.view.places[e.place.placeId] || {}).label || e.place.placeId);
    if (e.deceased) parts.push("and recorded as deceased");
    return parts.join(" · ");
  }
  function vitalBlock(personId, kind) {
    var V = VITAL[kind], p = S.view.people[personId]; if (!p) return "";
    var cur = p[kind], key = vitalKey(kind, personId), pend = S.edits[key], fk = "vital-" + kind + ":" + personId;
    var html = "<h4>" + V.label + '</h4><p data-qv2-vital="' + esc(kind + ":" + personId) + '">' +
      (cur.date ? answerText(cur.date) : "not recorded") + (cur.placeLabel ? " · " + esc(cur.placeLabel) : "") + "</p>";
    if (pend) html += '<p class="qv2-pending-vital">' + esc(vitalSummary(pend)) + unsaved(key) + "</p>";
    var canDate = can(V.date), canPlace = can(V.place);
    if (!canDate && !canPlace) return html;
    var storedText = cur.date && cur.date.state === "value" && cur.date.value ? cur.date.value.text || "" : "";
    return html + '<div class="qv2-form qv2-inline" data-qv2-form="vital-' + kind + '" data-person="' + esc(personId) + '">' +
      (canDate ? '<label class="qv2-field">Date <input type="text" data-f="date" value="' + esc(fv(fk, "date", storedText)) +
                 '" placeholder="as said, e.g. 12 June 1939 or about 1939"></label>' : "") +
      (canPlace ? '<label class="qv2-field">Place <select data-f="place">' +
                  options([["new", "+ Create a new place (named below)"]].concat(placeChoices(cur.placeId)), fv(fk, "place", ""),
                          cur.placeId ? "— keep the current place —" : "— not recorded —") + "</select></label>" +
                  '<label class="qv2-field">New place <input type="text" data-f="newPlaceLabel" value="' +
                  esc(fv(fk, "newPlaceLabel", "")) + '" placeholder="only when creating a new place"></label>' : "") +
      (kind === "death" ? '<p class="qv2-hint">Recording a death also records this person as deceased.</p>' : "") +
      '<button type="button" data-qv2-action="keep-vital" data-person="' + esc(personId) + '" data-kind="' + kind +
      '">Keep ' + kind + "</button></div>";
  }

  /* Homes / unions / separations (C-4F): each stored occurrence with its own
     small form, then a form to add one. */
  function occOthers(ev) {             // every recorded non-narrator participant, none hidden
    var nid = S.view.narratorPersonId;
    return (ev.participants || []).filter(function (x) { return x.personId !== nid; })
      .map(function (x) { return x.personId; });
  }
  function occSummary(e) {
    var parts = [OCC[e.occKind].label];
    if (e.partnerId) parts.push("with " + personName(e.partnerId));
    if (e.swaps) Object.keys(e.swaps).forEach(function (o) {
      parts.push(personName(o) + " → " + personName(e.swaps[o])); });
    if (e.homeType) parts.push(e.homeType);
    if (e.date) parts.push(e.date.text);
    if (e.current === true) parts.push("current home");
    if (e.current === false) parts.push("no longer current");
    if (e.place.mode === "new") parts.push("new place “" + e.place.label + "”");
    if (e.place.mode === "existing") parts.push((S.view.places[e.place.placeId] || {}).label || e.place.placeId);
    return parts.join(" · ");
  }
  function occFields(C, fk, storedText, currentPlaceId, isCurrent) {
    return (C.interval && can(C.date) ? '<label class="qv2-field"><input type="checkbox" data-f="current"' +
             (fv(fk, "current", !!isCurrent) ? " checked" : "") + "> Current home (they live here now)</label>" : "") +
      (can(C.date) ? '<label class="qv2-field">' + (C.interval ? "Period" : "Date") +
             ' <input type="text" data-f="date" value="' + esc(fv(fk, "date", storedText)) + '" placeholder="' +
             (C.interval ? "as said, e.g. 1962 to 1975, or 1990 to present" : "as said, e.g. June 1961 or about 1961") +
             '"></label>' : "") +
      (C.place && can(C.place) ? '<label class="qv2-field">Place <select data-f="place">' +
             options([["new", "+ Create a new place (named below)"]].concat(placeChoices(currentPlaceId)), fv(fk, "place", ""),
                     currentPlaceId ? "— keep the current place —" : "— not recorded —") + "</select></label>" +
             '<label class="qv2-field">New place <input type="text" data-f="newPlaceLabel" value="' +
             esc(fv(fk, "newPlaceLabel", "")) + '" placeholder="only when creating a new place"></label>' : "");
  }
  function occCard(eid) {
    var ev = S.view.events[eid], C = OCC[ev.type]; if (!C) return "";
    var key = "occ:" + eid, pend = S.edits[key], fk = "occ:" + eid, others = occOthers(ev);
    var head = '<div class="qv2-card" data-qv2-occ="' + esc(eid) + '"><strong>' + esc(C.label) + "</strong>" +
      (others.length ? " — with " + others.map(function (x) { return esc(personName(x)); }).join(" and ") : "") + (ev.placeLabel ? " · " + esc(ev.placeLabel) : "") +
      (ev.date ? " · " + answerText(ev.date) : "") +
      (ev.attributes && ev.attributes.current === true ? ' · <span data-qv2-current>current home</span>' : "") + (pend ? '<p>' + esc(occSummary(pend)) + unsaved(key) + "</p>" : "");
    var canSwap = !!(C.partner && can(C.partner));
    if (!can(C.date) && !(C.place && can(C.place)) && !canSwap) return head + "</div>";
    var storedText = ev.date && ev.date.state === "value" && ev.date.value ? ev.date.value.text || "" : "";
    var nid = S.view.narratorPersonId, sw = fv(fk, "swaps", {}) || {};
    var swapFields = canSwap ? others.map(function (pid) {
      return '<label class="qv2-field">With <select data-f="swap:' + esc(pid) + '">' + options(Object.keys(S.view.people)
        .filter(function (id) { return id !== nid; }).map(function (id) { return [id, personName(id)]; }),
        sw[pid] || pid, null) + "</select></label>"; }).join("") : "";
    return head + '<div class="qv2-form qv2-inline" data-qv2-form="occ" data-event="' + esc(eid) + '">' + swapFields +
      occFields(C, fk, storedText, ev.placeId, ev.attributes && ev.attributes.current === true) +
      '<button type="button" data-qv2-action="keep-occ" data-event="' + esc(eid) + '">Keep</button></div>' +
      (ev.type === "move"
        ? answerInput("homes", "event", eid, "event.residence.type", "Kind of home (house, farm, apartment…)", ev.residenceType)
        : "") + "</div>";
  }
  function occSection(kinds, topic) {
    var nid = S.view.narratorPersonId;
    var ids = Object.keys(S.view.events).filter(function (id) {
      var e = S.view.events[id];
      return kinds.indexOf(e.type) !== -1 && (e.participants || []).some(function (x) { return x.personId === nid; });
    });
    var html = ids.length ? ids.map(occCard).join("") : '<p class="qv2-blank">None recorded yet.</p>';
    html += pendingOf("occ").filter(function (e) { return e.isNew && kinds.indexOf(e.occKind) !== -1; }).map(function (e) {
      return '<div class="qv2-card qv2-pending-occ">' + esc(occSummary(e)) + unsaved("occ:" + e.eventId) + "</div>";
    }).join("");
    var addable = kinds.filter(function (k) { var C = OCC[k];
      return C.partner ? can(C.partner) : (can(C.date) || (C.place && can(C.place))); });
    if (!addable.length) return html;
    var fk = "occ-new:" + topic, C0 = OCC[addable[0]];
    var chosen = fv(fk, "occKind", addable[0]);
    var sel = addable.length === 1 || addable.indexOf(chosen) === -1 ? addable[0] : chosen, Cs = OCC[sel];
    var partnerPicker = Cs.partner
      ? '<label class="qv2-field">With <select data-f="partner">' + options(Object.keys(S.view.people)
          .filter(function (id) { return id !== nid; }).map(function (id) { return [id, personName(id)]; }),
          fv(fk, "partner", ""), "— choose who —") + "</select></label>" : "";
    var kindPicker = addable.length > 1
      ? '<label class="qv2-field">What <select data-f="occKind">' + options(addable.map(function (k) {
          return [k, OCC[k].label]; }), fv(fk, "occKind", addable[0]), null) + "</select></label>" : "";
    return html + '<div class="qv2-form qv2-add" data-qv2-form="occ-new" data-topic="' + esc(topic) + '"' +
      (addable.length === 1 ? ' data-kind="' + addable[0] + '"' : "") + "><h4>Add " +
      (addable.length === 1 ? C0.label.toLowerCase() : "a union or separation") + "</h4>" +
      kindPicker + partnerPicker + occFields(Cs, fk, "", null) +
      (sel === "move" && can("event.residence.type") ? '<label class="qv2-field">Kind of home <input type="text" ' +
        'data-f="homeType" value="' + esc(fv(fk, "homeType", "")) + '" placeholder="house, farm, apartment…"></label>' : "") +
      (addable.indexOf("separation") !== -1 ? '<p class="qv2-hint">A separation is its own record: it never changes the union it ends, ' +
        "and the same two people can marry again.</p>" : "") +
      '<button type="button" data-qv2-action="keep-occ">Add</button></div>';
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
      (can("relationship.period")
        ? '<label class="qv2-field">From <input type="text" data-f="from" value="' + rv("from", per.start ? per.start.text : "") +
          '" placeholder="as said, e.g. 1962 or about 1962"></label>' +
          '<label class="qv2-field">Until <input type="text" data-f="until" value="' + rv("until", per.end ? per.end.text : "") + '"></label>'
        : "") +
      '<button type="button" data-qv2-action="keep-rel" data-rel="' + esc(r.id) + '">Keep these changes</button> ' +
      '<button type="button" data-qv2-action="close-rel">Close</button>' +
      '<p class="qv2-hint">To say this person is ALSO something else to the narrator (a grandmother who raised them), ' +
      "add that below and choose them from \"someone already recorded\" — they stay one person.</p></div>" +
      (p ? vitalBlock(r.withPersonId, "birth") + vitalBlock(r.withPersonId, "death") : "") + "</div>";
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
    if (!can("relationship.kind")) return "";
    return '<div class="qv2-form qv2-add" data-qv2-form="person" data-topic="' + esc(t) + '"><h4>Add someone</h4>' + err +
      '<label class="qv2-field">Who <select data-f="person"><option value="">— a new person —</option>' +
        options(everyonePickable(), fv(k, "person", ""), null) + "</select></label>" +
      (can("person.name.full") ? '<label class="qv2-field">Name (new person) <input type="text" data-f="fullText" value="' + g("fullText") +
        '" placeholder="Whole name, as it is said"></label>' : "") +
      '<label class="qv2-field">Relationship to the narrator <select data-f="role">' +
        options(roles, fv(k, "role", ""), "— choose —") + "</select></label>" +
      '<label class="qv2-field">Described as (for "Other") <input type="text" data-f="describedAs" value="' + g("describedAs") + '"></label>' +
      '<div class="qv2-field">Qualifiers ' + qualifierBoxes(fv(k, "qualifiers", [])) + "</div>" +
      (can("relationship.qualifier.lineage_side") ? '<label class="qv2-field">Side of the family <select data-f="lineage">' + options(LINEAGE, fv(k, "lineage", ""), "— not recorded —") + "</select></label>" : "") +
      '<label class="qv2-field">What the narrator calls them <input type="text" data-f="narratorLabel" value="' + g("narratorLabel") + '"></label>' +
      (can("person.life_status") ? '<label class="qv2-field">Living? (new person) <select data-f="lifeStatus">' + options(LIFE_STATUS, fv(k, "lifeStatus", ""), "— not recorded —") + "</select></label>" : "") +
      (can("relationship.period") ? '<label class="qv2-field">From <input type="text" data-f="from" value="' + g("from") + '" placeholder="as said"></label>' +
        '<label class="qv2-field">Until <input type="text" data-f="until" value="' + g("until") + '"></label>' : "") +
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
      html += "<h4>Unions and separations</h4>" + occSection(["union", "separation"], "partners");
      if (N) {
        html += answerInput(t, "person", N.id, "person.reported_count.children", "Number of children, as said",
                            N.reportedCounts.children) +
                answerInput(t, "person", N.id, "person.reported_count.grandchildren", "Number of grandchildren, as said",
                            N.reportedCounts.grandchildren) +
                // C-4F: a STATED count — "married three times" survives with two unions identified
                answerInput(t, "person", N.id, "person.reported_count.marriages",
                            "How many times the narrator says they married (a count, even if not every marriage is recorded)",
                            N.reportedCounts.marriages);
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
          (can("person.pronouns") ? '<div class="qv2-form qv2-inline" data-qv2-form="pronoun"><input type="text" data-f="pronoun" value="' +
            esc(fv("pronoun:", "pronoun", "")) + '" placeholder="Pronouns, as the narrator uses them"> ' +
            '<button type="button" data-qv2-action="add-pronoun">Add</button></div>' : "") +
          vitalBlock(N.id, "birth") + vitalBlock(N.id, "death") +
          answerInput("narrator", "person", N.id, "person.birth.order", "Birth order, as the narrator describes it",
                      N.birthOrder) +
          "<h4>Current home</h4><div data-qv2-current-homes>" + list(T.currentHomes.map(eventLine)) + "</div>";
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
      case "homes":
        return "<h4>Homes</h4>" + occSection(["move"], "homes");
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
      else if (act === "keep-occ") keepOccurrence(a.closest("[data-qv2-form]"), a.getAttribute("data-event") || null);
      else if (act === "keep-vital") keepVital(a.getAttribute("data-person"), a.getAttribute("data-kind"), a.closest("[data-qv2-form]"));
    });
    var remember = function (ev) {
      var fm = ev.target.closest && ev.target.closest("[data-qv2-form]");
      if (fm && ev.target.hasAttribute("data-f")) rememberForm(fm);
    };
    root_.addEventListener("input", remember);
    root_.addEventListener("change", function (ev) {
      remember(ev);
      if (ev.target.getAttribute && ev.target.getAttribute("data-f") === "occKind") { paint(); return; }
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
    if (subjectType === "event") {                     // C-4F: the kind of home
      var ev = S.view.events[subjectId];
      return ev && concept === "event.residence.type" ? ev.residenceType : null;
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
