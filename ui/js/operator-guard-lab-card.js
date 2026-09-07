// WO-LORI-ARCHIVE-TO-MEMOIR-02 Block A — Lori Configuration card.
//
// The compact Guard Lab status/control card on the ORDINARY Operator
// tab. The full 43-row table stays in the Bug Panel and is deliberately
// NOT duplicated here: two renderings of one configuration is how they
// drift, and an operator preparing a session does not need the pipeline,
// they need to know what Lori is running and whether it reaches the
// person they are about to interview.
//
// THE GAP THIS CLOSES, found during the live acceptance on 2026-09-07.
// The Guard Lab could say an eligible narrator EXISTS. It could not say
// whether the narrator being interviewed was that narrator. So an
// operator could select a lean baseline, talk to an ordinary narrator,
// receive canonical Lori, and find nothing on screen to explain it —
// the gate refusing correctly and silently.
//
// THE VERDICT IS THE SERVER'S, ALWAYS. This card sends the selected
// narrator's ID and renders the answer. It does NOT decide eligibility
// by testing whether that id appears in a list of testing-only
// narrators — that would put an authority decision in the browser, where
// a stale page or a hostile one could arrange it. `testing_only` is read
// from the durable people row by fail-closed server code, which is IC-7.
//
// Nor does it compute the configuration label. `Defaults` / `Lean` /
// `Custom` arrives already decided, because a browser counting 43 rows
// would be a second implementation of a rule the server owns.
//
// NEVER NARRATOR-VISIBLE. Operator tab only; nothing here renders into
// the Narrator Session surface.
(function () {
  'use strict';

  var MOUNT_ID = 'lvOperatorGuardLabCard';
  var _O = (typeof ORIGIN !== 'undefined' && ORIGIN) || 'http://localhost:8000';
  var BASE = _O + '/api/operator/guard-lab';

  var _state = {
    enabled: null,     // null = not probed yet
    loading: false,
    error: null,
    conflict: null,
    busy: null,
    data: null,
    // True while a verdict for the PREVIOUS narrator has been discarded
    // and the replacement has not arrived. The card says so rather than
    // showing the old one for a few hundred milliseconds.
    resolving: false,
  };

  // ── THE NARRATOR-SWITCH CLAMP ──────────────────────────────────────
  //
  // Found in review of the pushed Block A. The card refreshes
  // asynchronously on narrator switch and bound nothing to the request
  // that produced a response, so this sequence made it lie:
  //
  //   A selected -> request A starts
  //   switch to B -> request B starts
  //   B returns first -> card correctly shows B
  //   A returns LATE -> _state.data replaced with A's answer, and the
  //                     card shows A's eligibility under B
  //
  // The runtime gate is unaffected — eligibility is still decided
  // server-side per turn — so this was never an experiment-security
  // hole. It was worse in a quieter way: an OPERATOR-TRUTH defect in
  // the one card built to answer "does THIS narrator receive the
  // configuration?", which is exactly the false reassurance it exists
  // to remove.
  //
  // Every read now carries the generation and the narrator id it was
  // issued under, and nothing writes state unless BOTH still match.
  var _switchGen = 0;

  function _context(extra) {
    var ctx = { gen: _switchGen, pid: currentPersonId() };
    if (extra) Object.keys(extra).forEach(function (k) { ctx[k] = extra[k]; });
    return ctx;
  }

  function _stale(ctx) {
    return !ctx || ctx.gen !== _switchGen || ctx.pid !== currentPersonId();
  }

  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        // undefined would stringify: `disabled="undefined"` disables by
        // mere presence. bug-panel-story-review.js shipped every action
        // button dead that way and no source scan could see it.
        if (attrs[k] === undefined || attrs[k] === null) return;
        if (k === 'class') n.className = attrs[k];
        else if (k === 'onclick') n.addEventListener('click', attrs[k]);
        else n.setAttribute(k, attrs[k]);
      });
    }
    (children || []).forEach(function (c) {
      if (c === null || c === undefined) return;
      n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return n;
  }

  // The narrator the operator is actually working with. Identity only —
  // it travels to the server, which decides what it means.
  function currentPersonId() {
    try {
      return (typeof state !== 'undefined' && state && state.person_id)
        ? String(state.person_id) : '';
    } catch (_) { return ''; }
  }

  function adopt(body, ctx) {
    if (!body) return;
    if (_stale(ctx)) {
      // A LATE ANSWER ABOUT THE PREVIOUS NARRATOR.
      //
      // The configuration half is a global truth and stays
      // authoritative — a revision the server reported really did
      // happen. The `current_narrator` half answered about somebody who
      // is no longer selected, and showing it under the new narrator is
      // the whole defect. So a stale READ is discarded outright, and a
      // stale MUTATION keeps its configuration while its verdict is
      // dropped and re-resolved for the narrator now on screen.
      if (ctx && ctx.mutation) {
        var kept = {};
        Object.keys(body).forEach(function (k) { kept[k] = body[k]; });
        kept.current_narrator = null;
        _state.data = kept;
        _state.enabled = true;
        _state.resolving = true;
        refresh();
      }
      return;
    }
    _state.data = body;
    _state.enabled = true;
    _state.error = null;
    _state.resolving = false;
  }

  function request(path, options, ctx) {
    _state.error = null;
    return fetch(BASE + path, options)
      .then(function (r) {
        if (r.status === 404) {
          if (!_stale(ctx)) _state.enabled = false;
          return null;
        }
        return r.json().catch(function () { return null; })
          .then(function (b) { return { status: r.status, body: b }; });
      })
      .then(function (res) {
        if (!res) return null;
        if (res.status === 409) {
          var d = (res.body && res.body.detail) || {};
          if (!_stale(ctx)) {
            _state.conflict = {
              message: d.message || 'The configuration changed underneath this request.',
              expected: d.expected_revision,
              actual: d.current_revision,
            };
          }
          // Adopt the live configuration the refusal carried, exactly as
          // the Bug Panel does — through the same clamp, so a stale
          // conflict cannot repaint a newer narrator either.
          if (d.current) adopt(d.current, ctx);
          return null;
        }
        if (res.status >= 400) {
          if (!_stale(ctx)) {
            var detail = res.body && res.body.detail;
            _state.error = (detail && detail.message) ||
              (typeof detail === 'string' ? detail : 'HTTP ' + res.status);
          }
          return null;
        }
        if (!_stale(ctx)) _state.conflict = null;
        adopt(res.body, ctx);
        return res.body;
      })
      .catch(function (e) {
        // A STALE NETWORK ERROR MUST NOT REPLACE NEWER STATE EITHER.
        // The first version of this clamp guarded the success path and
        // left the failure path writing unconditionally, which would
        // have put narrator A's timeout on narrator B's card.
        if (_stale(ctx)) return null;
        _state.enabled = true;
        _state.error = String((e && e.message) || e);
        return null;
      });
  }

  function refresh() {
    _state.loading = true; render();
    var ctx = _context();
    var q = ctx.pid ? ('?narrator_id=' + encodeURIComponent(ctx.pid)) : '';
    return request('/state' + q, { credentials: 'same-origin' }, ctx)
      .then(function () {
        if (_stale(ctx)) return;      // a newer read owns the card now
        _state.loading = false; render();
      });
  }

  function revision() { return _state.data ? _state.data.revision : 0; }

  function post(path, token) {
    _state.busy = token; render();
    var ctx = _context({ mutation: true });
    return request(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({
        expected_revision: revision(),
        narrator_id: ctx.pid || null,
      }),
    }, ctx).then(function () { _state.busy = null; render(); });
  }

  // ONE request each. Never a loop over the switchable population.
  function allSwitchableOff() { return post('/all-switchable-off', 'all-off'); }
  function restoreDefaults() { return post('/restore-defaults', 'restore'); }

  function openFullGuardLab() {
    // The Bug Panel is a NATIVE POPOVER opened declaratively by
    // popovertarget; there is no onclick to call. Use the platform API,
    // then scroll the Guard Lab section into view.
    try {
      var panel = document.getElementById('lv10dBugPanel');
      if (panel && !panel.matches(':popover-open')) panel.showPopover();
      var section = document.getElementById('lv10dBpGuardLab');
      if (section) {
        if (window.lvGuardLabState && window.lvGuardLabRenderInto) {
          var st = window.lvGuardLabState();
          st.collapsed = false;
          window.lvGuardLabRenderInto(section, st);
        }
        section.scrollIntoView({ block: 'start' });
      }
    } catch (e) { /* the card must not break on a popover refusal */ }
  }

  // ── Render ─────────────────────────────────────────────────────────

  function field(label, value, cls) {
    return el('div', { class: 'oglc-field' }, [
      el('span', { class: 'oglc-label' }, [label]),
      el('span', { class: 'oglc-value' + (cls ? ' ' + cls : '') }, [value]),
    ]);
  }

  function renderInto(mount, s) {
    if (!mount) return;
    mount.innerHTML = '';

    if (s.enabled === false) {
      mount.appendChild(el('div', { class: 'oglc-off' }, [
        'Lori Configuration — Guard Lab is off. Set ' +
        'HORNELORE_OPERATOR_GUARD_LAB=1 on the API to enable it.']));
      return;
    }
    if (!s.data) {
      mount.appendChild(el('div', { class: 'oglc-off' }, [
        s.loading ? 'Lori Configuration — loading…'
                  : 'Lori Configuration — not loaded.']));
      return;
    }

    var d = s.data;
    var cfg = d.configuration || {};
    var narrator = d.current_narrator || {};
    var gate = d.gate || {};
    // The server always sends `current_narrator`. It is null ONLY when
    // this card cleared it after a narrator switch, so null means "not
    // yet resolved for the narrator now selected" and nothing else.
    var unresolved = !d.current_narrator || s.resolving;

    mount.appendChild(el('div', { class: 'oglc-head' }, [
      el('span', { class: 'oglc-title' }, ['Lori Configuration']),
      el('span', {
        class: 'oglc-chip oglc-chip-' + (cfg.id || 'unknown'),
      }, [cfg.label || 'Unknown']),
    ]));

    if (cfg.detail) {
      mount.appendChild(el('div', { class: 'oglc-detail' }, [cfg.detail]));
    }

    var grid = el('div', { class: 'oglc-grid' }, [
      field('Revision', String(d.revision)),
      field('Running', (d.counts ? d.counts.selected : '?') + ' / ' +
                       (d.counts ? d.counts.total : '?')),
      field('Evaluation', gate.experiment_armed ? 'Armed' : 'Off',
            gate.experiment_armed ? 'oglc-ok' : 'oglc-muted'),
      field('Trace', gate.trace_recording ? 'Recording' : 'Off',
            gate.trace_recording ? 'oglc-ok' : 'oglc-muted'),
      field('Narrator', unresolved ? 'checking…'
            : (narrator.display_name ||
               (narrator.requested_id ? '(unknown)' : '(none selected)'))),
      // UNRESOLVED IS NOT "NOT ELIGIBLE". The card discarded a verdict
      // that belonged to a narrator who is no longer selected, and the
      // replacement has not arrived. Printing either answer here would
      // be a guess, and a guess is what the clamp exists to stop.
      field('Experimental narrator',
            unresolved ? 'checking…'
            : (narrator.can_receive_experiment ? 'Eligible' : 'Not eligible'),
            unresolved ? 'oglc-muted'
            : (narrator.can_receive_experiment ? 'oglc-ok' : 'oglc-warn')),
    ]);
    mount.appendChild(grid);

    // THE SENTENCE THE LIVE RUN SHOWED WAS MISSING. The server writes
    // it, because the reason it gives and the behaviour it describes
    // have to come from the same place.
    if (unresolved) {
      mount.appendChild(el('div', { class: 'oglc-verdict oglc-verdict-warn' }, [
        'Re-checking whether the selected narrator can receive this '
        + 'configuration…']));
    } else if (narrator.message) {
      mount.appendChild(el('div', {
        class: 'oglc-verdict ' + (narrator.can_receive_experiment
          ? 'oglc-verdict-ok' : 'oglc-verdict-warn'),
      }, [narrator.message]));
    }

    if (s.conflict) {
      mount.appendChild(el('div', { class: 'oglc-conflict' }, [
        'Change refused — you were looking at revision ' + s.conflict.expected +
        '; the live configuration is revision ' + s.conflict.actual +
        '. This card now shows the live one.']));
    }
    if (s.error) {
      mount.appendChild(el('div', { class: 'oglc-error' }, [String(s.error)]));
    }

    var busy = s.busy;
    mount.appendChild(el('div', { class: 'oglc-actions' }, [
      el('button', {
        class: 'oglc-btn oglc-btn-primary',
        disabled: busy ? 'disabled' : undefined,
        onclick: allSwitchableOff,
      }, [busy === 'all-off' ? 'Applying…' : 'All Switchable Off']),
      el('button', {
        class: 'oglc-btn',
        disabled: busy ? 'disabled' : undefined,
        onclick: restoreDefaults,
      }, [busy === 'restore' ? 'Restoring…' : 'Restore Defaults']),
      el('button', {
        class: 'oglc-btn',
        disabled: busy ? 'disabled' : undefined,
        onclick: refresh,
      }, ['Refresh']),
      el('button', {
        class: 'oglc-btn oglc-btn-link',
        onclick: openFullGuardLab,
      }, ['Open Full Guard Lab']),
    ]));

    mount.appendChild(el('div', { class: 'oglc-applies' }, [
      d.applies_note || '']));
  }

  function render() {
    renderInto(document.getElementById(MOUNT_ID), _state);
  }

  // Exported so the card can be tested by RENDERING it against a real
  // server payload, not by grepping this file.
  window.lvOperatorGuardLabRenderInto = renderInto;
  window.lvOperatorGuardLabRefresh = refresh;
  window.lvOperatorGuardLabState = function () { return _state; };
  // app.js calls this on narrator switch: the eligibility verdict is
  // about a specific person and is stale the moment that changes.
  window.lvOperatorGuardLabOnNarratorSwitch = function () {
    // Moving the generation CANCELS every read already in flight: their
    // context no longer matches, so none of them can write state.
    _switchGen += 1;
    _state.conflict = null;
    _state.error = null;
    _state.resolving = true;
    if (_state.data) _state.data.current_narrator = null;
    if (_state.enabled !== false) refresh(); else render();
  };

  function tryInitialFetch() {
    if (document.getElementById(MOUNT_ID)) refresh();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', tryInitialFetch);
  } else {
    tryInitialFetch();
  }
})();
