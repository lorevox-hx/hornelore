/* ═══════════════════════════════════════════════════════════════
   suggestion-review.js — the review surface for Lori's proposals.

   WO-03B, step 1. This did not exist. Three producers queued
   suggestions and nothing consumed them: `acceptSuggestion` and
   `dismissSuggestion` in projection-sync.js had zero callers, and the
   only rendering of the queue anywhere was a read-only debug dump.
   Two comments in the codebase asserted a review surface that was
   never built.

   WHAT THIS IS. A list of the active narrator's queued proposals, each
   with what the model proposed, how sure it was, whether its cited
   turn checked out, how many times it has insisted — and two buttons.

   WHAT IT DOES NOT DO, by design:

     * it never writes the value itself. Accept and Decline are server
       operations on a proposal identified by its server-minted id; the
       server resolves the destination, checks for a conflict, and
       commits the answer, its provenance, the queue and the review
       record in one transaction. This file only asks and then re-reads.

     * it never calls the old client `acceptSuggestion`. That function
       rewrote the projection field as `source: "human_edit"` — it
       disguised Lori's proposal as something a person typed, which is
       the exact laundering WO-03 exists to end.

     * it never guesses which relative a proposal is about. A proposal
       aimed at a repeatable section arrives `destination_unresolved`,
       and the person picks the entry (or "add as new") before Accept
       is enabled. An ordinal is never inferred.

     * it never overwrites. If the record already holds a different
       value, the server answers 409 with both, and this shows both.
       The person can decline the proposal or enter the value by hand
       through the ordinary form — which correctly records it as theirs.

   Mounted like Shadow Review: bio-builder.js looks up
   `window.HorneloreSuggestionReview` lazily at render time, so this
   file loads after it.
═══════════════════════════════════════════════════════════════ */

(function () {
  "use strict";

  var _root = null;
  var _pid = null;
  var _queue = [];
  var _busy = {};          // suggestion_id -> true while a request is in flight
  var _choice = {};        // suggestion_id -> chosen entry_id for unresolved ones
  var _conflict = {};      // suggestion_id -> {stored, proposed, path} after a 409

  var REPEATABLE = { parents: 1, grandparents: 1, siblings: 1, children: 1,
                     spouse: 1, marriage: 1, familyTraditions: 1, pets: 1 };

  function _esc(s) {
    return String(s == null ? "" : s).replace(/[<>&"']/g, function (c) {
      return { "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function _core() {
    return window.LorevoxBioBuilderModules && window.LorevoxBioBuilderModules.core;
  }

  function _bb() {
    var c = _core();
    return c && typeof c._bb === "function" ? c._bb() : null;
  }

  /* ── status banner — its OWN element, so it cannot clobber or be
     clobbered by the questionnaire save banner (they'd share a timer). ── */
  function _say(text, kind, sticky) {
    var el = document.getElementById("bbSuggestStatus");
    if (!el) {
      el = document.createElement("div");
      el.id = "bbSuggestStatus";
      el.setAttribute("role", "status");
      el.setAttribute("aria-live", "polite");
      el.style.cssText =
        "position:fixed;left:50%;transform:translateX(-50%);bottom:72px;z-index:99998;" +
        "max-width:min(680px,92vw);padding:12px 16px;border-radius:8px;" +
        "font:14px/1.45 system-ui,sans-serif;box-shadow:0 4px 16px rgba(0,0,0,.28);";
      document.body.appendChild(el);
    }
    var pal = {
      ok:   ["#123d1d", "#d8f5e0", "#2f7d4a"],
      info: ["#1e2633", "#c9d4e4", "#3d4d66"],
      warn: ["#4a3a11", "#ffeccc", "#a3782b"],
      err:  ["#4a1113", "#ffd9dc", "#a3272d"]
    }[kind || "info"];
    el.style.background = pal[0]; el.style.color = pal[1];
    el.style.border = "1px solid " + pal[2];
    el.textContent = text;
    el.hidden = false;
    clearTimeout(el._t);
    if (!sticky) el._t = setTimeout(function () { el.hidden = true; }, 8000);
  }

  /* ── data ─────────────────────────────────────────────────────── */

  function _load(pid) {
    if (typeof API === "undefined" || !API.IV_PROJ_GET) return Promise.resolve([]);
    return fetch(API.IV_PROJ_GET(pid))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        var p = (j && j.projection) || {};
        return Array.isArray(p.pendingSuggestions) ? p.pendingSuggestions : [];
      })
      .catch(function () { return null; });
  }

  function _split(fieldPath) {
    var parts = String(fieldPath || "").split(".");
    var head = parts[0].split("[")[0];
    return { section: head, field: parts.slice(1).join("."), repeatable: !!REPEATABLE[head] };
  }

  /* Entries the person can attach an unresolved proposal to, read from
     the in-memory questionnaire. Labelled by whatever identifies the
     person — never by index. */
  function _entriesFor(section) {
    var bb = _bb();
    var arr = bb && bb.questionnaire && bb.questionnaire[section];
    if (!Array.isArray(arr)) return [];
    var out = [];
    arr.forEach(function (e) {
      if (!e || typeof e !== "object" || !e._entryId) return;
      var label = [e.relation, e.firstName, e.lastName, e.name, e.side, e.description]
        .filter(function (x) { return x && String(x).trim(); }).join(" · ");
      out.push({ id: e._entryId, label: label || "(unnamed entry)" });
    });
    return out;
  }

  /* ── plain-language helpers ───────────────────────────────────── */

  /* Section and field labels come from the questionnaire's own
     definitions, so the card says "Personal Information → Notes" rather
     than "personal → notes". One source; nothing retyped here. */
  function _labels(section, field) {
    var q = window.LorevoxBioBuilderModules && window.LorevoxBioBuilderModules.questionnaire;
    var secs = (q && q.SECTIONS) || [];
    var sec = null;
    for (var i = 0; i < secs.length; i++) if (secs[i].id === section) { sec = secs[i]; break; }
    var fld = null;
    if (sec && sec.fields) for (var j = 0; j < sec.fields.length; j++) if (sec.fields[j].id === field) { fld = sec.fields[j]; break; }
    return {
      section: sec ? sec.label : section,
      field: fld ? fld.label : field,
      single: sec ? (sec.repeatLabel || sec.label) : section
    };
  }

  /* What the record holds at the proposal's destination right now.
     Returns {known:true, value} or {known:false} for a repeatable
     destination with no entry chosen yet. */
  function _current(d, chosen) {
    var bb = _bb();
    var qq = bb && bb.questionnaire;
    if (!qq) return { known: false };
    if (!d.repeatable) {
      var sec = qq[d.section];
      var v = sec && typeof sec === "object" ? sec[d.field] : undefined;
      return { known: true, value: (v == null ? "" : String(v)) };
    }
    if (!chosen || chosen === "__new__") return { known: chosen === "__new__", value: "" };
    var arr = qq[d.section];
    if (!Array.isArray(arr)) return { known: true, value: "" };
    for (var i = 0; i < arr.length; i++) {
      if (arr[i] && arr[i]._entryId === chosen) {
        var ev = arr[i][d.field];
        return { known: true, value: (ev == null ? "" : String(ev)) };
      }
    }
    return { known: true, value: "" };
  }

  /* ── render ───────────────────────────────────────────────────── */

  function _evidence(s) {
    var ev = s.turn_evidence || (s.suggestion_id ? "absent" : "pre-cutover");
    return {
      verified: {
        cls: "bb-badge-ok", short: "narrator said this",
        text: "The narrator said this in a conversation, and the conversation is on record as theirs."
      },
      unverified: {
        cls: "bb-badge-amber", short: "could not confirm source",
        text: "Lori pointed to a conversation as the source, but it could not be confirmed as this narrator's own words. Treat as Lori's inference."
      },
      absent: {
        cls: "bb-badge-muted", short: "Lori's inference",
        text: "No conversation was cited. This is something Lori worked out, not something the narrator said."
      },
      "pre-cutover": {
        cls: "bb-badge-muted", short: "older suggestion",
        text: "Queued before the system recorded where suggestions came from."
      }
    }[ev];
  }

  /* Does the questionnaire define this field? The server decides and
     records `destination_undefined`; this mirrors it from the same
     SECTIONS the form renders, so a card is never offered an Accept the
     server would refuse. Pre-cutover rows carry no flag, so they are
     checked here too. */
  function _undefinedDest(s, d) {
    if (s.destination_undefined === true) return true;
    if (s.destination_undefined === false) return false;
    var q = window.LorevoxBioBuilderModules && window.LorevoxBioBuilderModules.questionnaire;
    var secs = (q && q.SECTIONS) || [];
    for (var i = 0; i < secs.length; i++) {
      if (secs[i].id !== d.section) continue;
      var fs = secs[i].fields || [];
      for (var j = 0; j < fs.length; j++) if (fs[j].id === d.field) return false;
      return true;
    }
    return true;
  }

  function _card(s) {
    var d = _split(s.fieldPath);
    var L = _labels(d.section, d.field);
    var sid = s.suggestion_id || "";
    var legacy = !sid;
    var undef = _undefinedDest(s, d);
    var unresolved = !!s.destination_unresolved || (d.repeatable && !sid);
    var busy = !!_busy[sid];
    var conflict = _conflict[sid];
    var chosen = _choice[sid] || "";
    var entries = unresolved ? _entriesFor(d.section) : [];
    var ev = _evidence(s);
    var cur = _current(d, chosen);
    var differs = cur.known && cur.value && cur.value !== String(s.value == null ? "" : s.value);

    var h = '<div class="bb-candidate-card" data-sid="' + _esc(sid) + '">';
    h += '<div class="bb-candidate-body">';

    // WHERE it would go, in the questionnaire's own words.
    h += '<div class="bb-candidate-name">' +
         (undef ? _esc(s.fieldPath) : _esc(L.section) + ' → ' + _esc(L.field || "(section)")) +
         '</div>';

    // WHAT Lori proposes.
    h += '<div class="bb-candidate-detail" style="margin:6px 0 2px">' +
         '<span style="opacity:.7">Lori proposes:</span> ' +
         '<strong style="font-size:1.08em">' + _esc(s.value) + '</strong></div>';

    if (undef) {
      h += '<div class="bb-candidate-note" style="margin-top:8px;border-left:3px solid #a3272d;padding-left:8px">';
      h += '<strong>This cannot be added to the biography.</strong><br>';
      h += 'The questionnaire has no place for <code>' + _esc(s.fieldPath) + '</code>, ' +
           'so accepting it would store the answer where no form could show it — ' +
           'you would not be able to see or correct it afterwards.<br>';
      h += '<span style="opacity:.85">Lori worked this out from a conversation, and it is kept here ' +
           'so it is not lost. Declining records that you do not want it.</span>';
      h += '</div>';
    }

    // WHAT is there now — the thing a person needs before deciding.
    if (!undef && (!unresolved || chosen)) {
      if (cur.known && cur.value) {
        h += '<div class="bb-candidate-detail" style="margin:2px 0' + (differs ? ";color:#ffeccc" : "") + '">' +
             '<span style="opacity:.7">On record now:</span> <strong>' + _esc(cur.value) + '</strong>' +
             (differs ? ' <span class="bb-badge-amber">different</span>' : ' <span class="bb-badge-ok">same</span>') +
             '</div>';
      } else if (cur.known) {
        h += '<div class="bb-candidate-detail" style="margin:2px 0;opacity:.7">On record now: <em>nothing yet</em></div>';
      }
    }

    // WHERE it came from, in plain words.
    h += '<div class="bb-candidate-src" style="margin-top:6px">';
    h += '<span class="' + ev.cls + '" title="' + _esc(ev.text) + '">' + _esc(ev.short) + '</span>';
    if (s.confidence != null) h += ' <span class="bb-badge-muted" title="How sure Lori was">' + _esc(Math.round(Number(s.confidence) * 100)) + '% sure</span>';
    if ((s.repeats || 1) > 1) h += ' <span class="bb-badge-amber" title="Lori has proposed this exact value more than once">suggested ' + _esc(s.repeats) + ' times</span>';
    if (legacy) h += ' <span class="bb-badge-muted">from before 2026-08-17</span>';
    h += '</div>';
    h += '<div class="bb-hint-text" style="margin-top:4px;font-size:.9em">' + _esc(ev.text) + '</div>';

    if (unresolved && !undef) {
      h += '<div class="bb-candidate-note" style="margin-top:8px">';
      h += 'This is about one of the <em>' + _esc(L.section) + '</em>, but Lori did not say which one. ';
      h += 'Choose before accepting — nothing will be guessed.';
      h += '<div style="margin-top:6px"><select data-choose="' + _esc(sid) + '" ' + (busy ? "disabled" : "") + '>';
      h += '<option value="">— which ' + _esc(L.single).toLowerCase() + '? —</option>';
      entries.forEach(function (e) {
        h += '<option value="' + _esc(e.id) + '"' + (chosen === e.id ? " selected" : "") + '>' + _esc(e.label) + '</option>';
      });
      h += '<option value="__new__"' + (chosen === "__new__" ? " selected" : "") + '>+ add as a new ' + _esc(L.single).toLowerCase() + '</option>';
      h += '</select></div></div>';
    }

    if (conflict) {
      h += '<div class="bb-candidate-note" style="margin-top:8px;border-left:3px solid #a3782b;padding-left:8px">';
      h += '<strong>Not accepted — the record already says something different.</strong><br>';
      h += 'On record: <strong>' + _esc(conflict.stored) + '</strong><br>';
      h += 'Lori proposed: <strong>' + _esc(conflict.proposed) + '</strong><br>';
      h += '<span style="opacity:.85">Accepting would replace what is on record, so it was refused. ' +
           'Decline to keep the record, or enter the value yourself under ' +
           _esc(L.section) + ' — that records it as your entry.</span>';
      h += '</div>';
    } else if (differs && !unresolved) {
      // Tell them BEFORE they click: this Accept will be refused.
      h += '<div class="bb-hint-text" style="margin-top:6px;color:#ffeccc">' +
           'The record already holds a different value, so Accept will be refused. ' +
           'Decline to keep what is on record, or change it yourself under ' + _esc(L.section) + '.</div>';
    }

    h += '</div>';  // body

    h += '<div class="bb-candidate-actions">';
    if (legacy) {
      h += '<span class="bb-hint-text">Queued before proposals had ids; review and decline are ' +
           'available once it is re-proposed with one.</span>';
    } else if (undef) {
      // No Accept at all — not a disabled one. A greyed button invites
      // the question "why can't I?"; its absence plus the explanation
      // above answers it. Decline stays: refusing is still a decision a
      // person is entitled to record.
      h += '<button class="bb-btn-sm bb-ghost-btn" data-decline="' + _esc(sid) + '"' +
           (busy ? " disabled" : "") + '>Decline</button>';
    } else {
      var canAccept = !busy && !conflict && (!unresolved || !!chosen);
      h += '<button class="bb-btn-sm bb-btn-primary" data-accept="' + _esc(sid) + '"' +
           (canAccept ? "" : " disabled") + '>' + (busy ? "…" : "Accept") + '</button> ';
      h += '<button class="bb-btn-sm bb-ghost-btn" data-decline="' + _esc(sid) + '"' +
           (busy ? " disabled" : "") + '>Decline</button>';
    }
    h += '</div></div>';
    return h;
  }

  function _render() {
    if (!_root) return;
    if (_queue === null) {
      _root.innerHTML = '<div class="bb-empty-state">Could not read the suggestion queue from the server.</div>';
      return;
    }
    if (!_queue.length) {
      _root.innerHTML =
        '<div class="bb-section-title">Suggestions</div>' +
        '<div class="bb-empty-state">Nothing waiting for review. When Lori proposes something ' +
        'she is not sure about, it appears here instead of going into the biography.</div>';
      return;
    }
    /* TWO GROUPS, and the split is the point.
       A suggestion whose destination the questionnaire does not define
       cannot be added to the biography at all. Mixing those in with the
       actionable ones is how a person ends up clicking Accept on
       something that would vanish — which is exactly what happened on
       2026-09-20 with `personal.notes`. */
    var actionable = [], blocked = [];
    _queue.forEach(function (s) {
      (_undefinedDest(s, _split(s.fieldPath)) ? blocked : actionable).push(s);
    });

    var h = '<div class="bb-section-title">Suggestions <span class="bb-pill ' +
            (actionable.length ? "bb-pill--has" : "bb-pill--empty") + '">' +
            actionable.length + '</span></div>';
    h += '<p class="bb-hint-text">Things Lori believes about this narrator that nobody has confirmed. ' +
         'Each card shows what she proposes, where it would go, and what is on record there now. ' +
         '<strong>Accept</strong> records that <em>Lori proposed it and you agreed</em> — not that you said it. ' +
         '<strong>Decline</strong> records the refusal so it is not offered again. Neither changes anything ' +
         'already on record.</p>';

    if (actionable.length) {
      actionable.forEach(function (s) { h += _card(s); });
    } else {
      h += '<div class="bb-empty-state">Nothing waiting for your decision.</div>';
    }

    if (blocked.length) {
      h += '<div class="bb-section-title bb-section-title--mt">Cannot be added ' +
           '<span class="bb-pill bb-pill--empty">' + blocked.length + '</span></div>';
      h += '<p class="bb-hint-text">Lori worked these out, but the questionnaire has no field for them, ' +
           'so there is nowhere to put the answer where you could see or change it later. ' +
           'They are kept here rather than thrown away. Declining records that you do not want them.</p>';
      blocked.forEach(function (s) { h += _card(s); });
    }
    _root.innerHTML = h;
  }

  /* ── actions ──────────────────────────────────────────────────── */

  function _refreshQuestionnaire() {
    // The condition from the ruling: after accept the person must SEE
    // the resulting questionnaire state. Re-read it from the server
    // rather than patching memory — the server is the record.
    var c = _core();
    if (c && typeof c._restoreQuestionnaire === "function" && _pid) {
      try { c._restoreQuestionnaire(_pid); } catch (e) {}
    }
  }

  function _reload() {
    return _load(_pid).then(function (q) { _queue = q; _render(); });
  }

  function _accept(sid) {
    var s = _queue.filter(function (x) { return x.suggestion_id === sid; })[0];
    if (!s) return;
    _busy[sid] = true; _render();
    var body = { person_id: _pid, entry_id: _choice[sid] || "", reviewed_by: "" };
    fetch(API.IV_PROJ_SUGGEST_ACCEPT(sid), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (r) {
      return r.text().then(function (t) {
        var j = null; try { j = JSON.parse(t); } catch (e) {}
        delete _busy[sid];
        if (r.status === 409) {
          var d = (j && j.detail) || {};
          _conflict[sid] = { stored: d.stored, proposed: d.proposed, path: d.path };
          _say("Not accepted — the record already holds a different value. Both are shown.", "warn", true);
          _render();
          return;
        }
        if (r.status === 422) {
          var dd = (j && j.detail) || {};
          if (dd.error === "destination_undefined") {
            _say("Not accepted — " + (dd.detail || "the questionnaire has no such field") +
                 " Nothing was changed.", "err", true);
            _reload();   // re-read: the server knows more than this page did
            return;
          }
          _say("Choose which entry this belongs to before accepting.", "warn");
          _render();
          return;
        }
        if (!r.ok) {
          _say("Not accepted — the server refused (HTTP " + r.status + "). Nothing was changed.", "err", true);
          _render();
          return;
        }
        var d2 = _split(s.fieldPath);
        _say("Accepted as Lori's suggestion → " + d2.section + "." + d2.field +
             (j && j.revision !== undefined ? " (revision " + j.revision + ")" : "") + ".", "ok");
        delete _choice[sid]; delete _conflict[sid];
        _refreshQuestionnaire();
        _reload();
      });
    }).catch(function (e) {
      delete _busy[sid];
      _say("Could not reach the server. Nothing was changed.", "err", true);
      _render();
    });
  }

  function _decline(sid) {
    _busy[sid] = true; _render();
    fetch(API.IV_PROJ_SUGGEST_DECLINE(sid), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ person_id: _pid, reviewed_by: "" })
    }).then(function (r) {
      delete _busy[sid];
      if (!r.ok) {
        _say("Not declined — the server refused (HTTP " + r.status + "). The proposal is still queued.", "err", true);
        _render();
        return;
      }
      _say("Declined. Lori will not propose that value again.", "ok");
      delete _choice[sid]; delete _conflict[sid];
      _reload();
    }).catch(function () {
      delete _busy[sid];
      _say("Could not reach the server. The proposal is still queued.", "err", true);
      _render();
    });
  }

  function _onClick(ev) {
    var t = ev.target;
    if (!t || !t.getAttribute) return;
    var a = t.getAttribute("data-accept");
    var d = t.getAttribute("data-decline");
    if (a) { ev.preventDefault(); _accept(a); }
    else if (d) { ev.preventDefault(); _decline(d); }
  }

  function _onChange(ev) {
    var t = ev.target;
    if (!t || !t.getAttribute) return;
    var sid = t.getAttribute("data-choose");
    if (!sid) return;
    _choice[sid] = t.value || "";
    _render();
  }

  /* ── mount ────────────────────────────────────────────────────── */

  function init(rootId, pid) {
    _root = document.getElementById(rootId);
    if (!_root) return;
    _pid = pid || null;
    _queue = []; _busy = {}; _choice = {}; _conflict = {};
    if (!_pid) {
      _root.innerHTML = '<div class="bb-empty-state">No narrator selected.</div>';
      return;
    }
    _root.removeEventListener("click", _onClick);
    _root.removeEventListener("change", _onChange);
    _root.addEventListener("click", _onClick);
    _root.addEventListener("change", _onChange);
    _root.innerHTML = '<div class="bb-hint-text">Loading suggestions…</div>';
    _reload();
  }

  window.HorneloreSuggestionReview = { init: init, reload: _reload };
})();
