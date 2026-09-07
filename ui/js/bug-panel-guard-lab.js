// WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01 — Guard Lab operator control.
//
// The 43 registered narrator-facing authorities, with the switches that
// make them an experiment instead of an argument. Lives INSIDE the
// existing Bug Panel — deliberately not a second application. A separate
// experimental console would be one more surface to keep truthful, and
// the operator would have to decide which of two pages was right.
//
// Server: /api/operator/guard-lab (HORNELORE_OPERATOR_GUARD_LAB=1; 404
// when off and this section renders a quiet disabled placeholder).
//
// FOUR THINGS THIS PANEL WILL NOT DO
//
//   IT NEVER SHOWS ONE TOGGLE PER ROW. Canonical default, deployment
//   default, operator override and effective state are four different
//   facts and the reason names which one decided the row. Id 2 is
//   canonically ON, never overridable, and effectively PARKED; a green
//   ON switch would be wrong three ways at once.
//
//   IT NEVER LOOPS. `All Switchable Off` is ONE request. Thirty-seven
//   clicks, or thirty-seven fetches behind one click, would produce 37
//   revisions and let a turn start on a mixture nobody chose.
//
//   IT NEVER RE-DERIVES STATE. Every mutation returns the whole
//   configuration and the panel adopts it wholesale. Patching a row
//   locally from what we hoped the server did is how a panel and a
//   server drift apart, and this one exists to be believed.
//
//   IT NEVER CLAIMS A CHANGE REACHED A TURN. The gate block reports all
//   four conditions by name. Without it an operator selects a lean
//   baseline, talks to Lori, receives canonical production and concludes
//   the switches do nothing — when the gate refused, silently and
//   correctly, because nothing was armed.
//
// OPTIMISTIC REVISION. Every write carries the revision the operator was
// LOOKING AT. A 409 comes back with the live configuration attached; the
// panel adopts it and says what happened, rather than overwriting a
// newer configuration or silently discarding the click.
//
// NEVER narrator-visible.
(function () {
  'use strict';

  var MOUNT_ID = 'lv10dBpGuardLab';
  // Bare relative URLs hit 8082 (UI), not 8000 (API) — BUG-224.
  var _O = (typeof ORIGIN !== 'undefined' && ORIGIN) || 'http://localhost:8000';
  var BASE = _O + '/api/operator/guard-lab';

  var CLASS_ORDER = ['PROMPT', 'ROUTE', 'TRANSFORM', 'VALIDATE',
                     'REPLACE', 'FINAL_WRITER', 'LOCKED'];

  // The server owns this vocabulary; this only decides how it reads.
  var REASON_LABELS = {
    canonical_default: 'registry default',
    operator_override: 'you set this',
    deployment_default: '.env deployment default',
    protected: 'protected — not overridable',
    pending_seam: 'not separable in code yet',
    system_parked: 'server-parked feature',
  };

  var _state = {
    enabled: null,      // null = not probed yet
    loading: false,
    collapsed: true,    // a 43-row table is not what most sessions want open
    error: null,
    conflict: null,     // {message, expected, actual}
    busy: null,         // authority id, 'all-off', or 'restore'
    data: null,         // the whole server payload, adopted wholesale
    showDocs: {},       // authority id -> expanded evidence
  };

  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        // A key present with an undefined value reaches setAttribute and
        // stringifies: `disabled="undefined"` DISABLES the element by mere
        // presence. bug-panel-story-review.js shipped every action button
        // permanently dead that way, and no source scan could see it.
        if (attrs[k] === undefined || attrs[k] === null) return;
        if (k === 'class') n.className = attrs[k];
        else if (k === 'onclick') n.addEventListener('click', attrs[k]);
        else if (k === 'onchange') n.addEventListener('change', attrs[k]);
        else n.setAttribute(k, attrs[k]);
      });
    }
    (children || []).forEach(function (c) {
      if (c === null || c === undefined) return;
      n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return n;
  }

  function shortFp(fp) {
    return fp ? String(fp).slice(0, 12) : '—';
  }

  function tri(value) {
    // Three-valued and rendered as three values. `false` and "unset" are
    // different operator decisions and must not both read as off.
    if (value === true) return 'ON';
    if (value === false) return 'OFF';
    return 'unset';
  }

  // ── Network ────────────────────────────────────────────────────────

  function adopt(body) {
    _state.data = body;
    _state.enabled = true;
    _state.error = null;
  }

  function request(path, options) {
    _state.error = null;
    return fetch(BASE + path, options)
      .then(function (r) {
        if (r.status === 404) { _state.enabled = false; return null; }
        return r.json().catch(function () { return null; })
          .then(function (b) { return { status: r.status, body: b }; });
      })
      .then(function (res) {
        if (!res) return null;
        if (res.status === 409) {
          var d = (res.body && res.body.detail) || {};
          _state.conflict = {
            message: d.message ||
              'The configuration changed underneath this request.',
            expected: d.expected_revision,
            actual: d.current_revision,
          };
          // THE REFUSAL CARRIES THE TRUTH. Adopting it here is what makes
          // a stale second tab correct itself instead of insisting.
          if (d.current) adopt(d.current);
          return null;
        }
        if (res.status >= 400) {
          var detail = (res.body && res.body.detail);
          _state.error = (detail && detail.message) ||
            (typeof detail === 'string' ? detail : 'HTTP ' + res.status);
          return null;
        }
        _state.conflict = null;
        adopt(res.body);
        return res.body;
      })
      .catch(function (e) {
        _state.enabled = true;   // reachable enough to fail
        _state.error = String((e && e.message) || e);
        return null;
      });
  }

  function refresh() {
    _state.loading = true; render();
    return request('/state', { credentials: 'same-origin' })
      .then(function () { _state.loading = false; render(); });
  }

  function _revision() {
    return _state.data ? _state.data.revision : 0;
  }

  function post(path, body, busyToken) {
    _state.busy = busyToken; render();
    return request(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(body),
    }).then(function () { _state.busy = null; render(); });
  }

  function setAuthority(id, enabled) {
    // The revision the operator was LOOKING AT. Deliberately not re-read
    // from anywhere: re-reading it here would defeat the whole check.
    return post('/authorities/' + encodeURIComponent(id),
                { enabled: enabled, expected_revision: _revision() }, id);
  }

  // ONE request. Not a loop over 37 ids — that would be 37 revisions and
  // a window in which a turn could acquire a half-applied configuration.
  function allSwitchableOff() {
    return post('/all-switchable-off', { expected_revision: _revision() },
                'all-off');
  }

  function restoreDefaults() {
    return post('/restore-defaults', { expected_revision: _revision() },
                'restore');
  }

  // ── Render ─────────────────────────────────────────────────────────

  function renderIdentity(d) {
    var box = el('div', { class: 'gl-identity' }, [
      el('div', { class: 'gl-id-row' }, [
        el('span', { class: 'gl-id-key' }, ['revision']),
        el('span', { class: 'gl-id-val' }, [String(d.revision)]),
        el('span', { class: 'gl-id-note' }, [
          'the generation the next eligible turn consumes']),
      ]),
      el('div', { class: 'gl-id-row' }, [
        el('span', { class: 'gl-id-key' }, ['registry']),
        el('span', { class: 'gl-id-val gl-mono', title: d.registry_fingerprint },
           [shortFp(d.registry_fingerprint)]),
        el('span', { class: 'gl-id-note' }, ['which authority map this code has']),
      ]),
      el('div', { class: 'gl-id-row' }, [
        el('span', { class: 'gl-id-key' }, ['selection']),
        el('span', { class: 'gl-id-val gl-mono', title: d.selection_fingerprint },
           [shortFp(d.selection_fingerprint)]),
        el('span', { class: 'gl-id-note' }, ['which effective selection']),
      ]),
    ]);
    return box;
  }

  function renderGate(gateInfo) {
    if (!gateInfo) return null;
    var cls = gateInfo.can_apply_to_a_turn ? 'gl-gate gl-gate-open' : 'gl-gate gl-gate-shut';
    var head = gateInfo.can_apply_to_a_turn
      ? 'An eligible turn WILL receive this configuration.'
      : 'No turn can receive this configuration yet.';
    var rows = (gateInfo.conditions || []).map(function (c) {
      return el('li', { class: c.met ? 'gl-cond-met' : 'gl-cond-unmet' }, [
        el('span', { class: 'gl-cond-mark' }, [c.met ? '✓' : '✗']),
        el('span', { class: 'gl-cond-name' }, [c.name]),
        el('span', { class: 'gl-cond-detail' }, [c.detail || '']),
      ]);
    });
    var narrators = (gateInfo.testing_only_narrators || []).map(function (n) {
      return el('li', { class: 'gl-narrator' }, [
        el('span', { class: 'gl-mono' }, [String(n.id || '')]),
        ' ', (n.display_name || ''),
      ]);
    });
    return el('div', { class: cls }, [
      el('div', { class: 'gl-gate-head' }, [head]),
      el('ul', { class: 'gl-cond-list' }, rows),
      narrators.length
        ? el('div', { class: 'gl-narrators' }, [
            el('div', { class: 'gl-narrators-head' }, ['test-only narrators']),
            el('ul', {}, narrators),
          ])
        : el('div', { class: 'gl-narrators-none' }, [
            'No test-only narrator exists. An experiment has nobody it is ' +
            'allowed to reach — create one with testing_only set at ' +
            'creation; it cannot be granted afterwards.']),
    ]);
  }

  function renderControls(d) {
    var busy = _state.busy;
    return el('div', { class: 'gl-controls' }, [
      el('button', {
        class: 'gl-btn gl-btn-primary',
        disabled: busy ? 'disabled' : undefined,
        onclick: allSwitchableOff,
      }, [busy === 'all-off' ? 'Applying…' : 'All Switchable Off']),
      el('button', {
        class: 'gl-btn',
        disabled: busy ? 'disabled' : undefined,
        onclick: restoreDefaults,
      }, [busy === 'restore' ? 'Restoring…' : 'Restore Defaults']),
      el('button', {
        class: 'gl-btn',
        disabled: busy ? 'disabled' : undefined,
        onclick: refresh,
      }, ['Refresh']),
      el('span', { class: 'gl-controls-note' }, [
        'One request, one revision — never 37 writes.']),
    ]);
  }

  function renderRow(a) {
    var busy = _state.busy === a.id;
    var cells = [
      el('span', { class: 'gl-cell gl-num' }, [String(a.id)]),
      el('span', { class: 'gl-cell gl-name' }, [a.display || a.name]),
      el('span', { class: 'gl-cell gl-class' }, [a.cls]),
      el('span', {
        class: 'gl-cell gl-eff ' + (a.effective ? 'gl-on' : 'gl-off'),
      }, [a.effective ? 'RUNNING' : 'EXCLUDED']),
      el('span', { class: 'gl-cell gl-reason' }, [
        REASON_LABELS[a.reason] || a.reason]),
    ];

    // The three inputs to the effective state, always shown separately.
    var states = el('div', { class: 'gl-states' }, [
      el('span', { class: 'gl-state' }, ['canonical ' + tri(a.canonical_default)]),
      a.deployment_default === null || a.deployment_default === undefined
        ? null
        : el('span', { class: 'gl-state gl-state-deploy' },
             ['deployment ' + tri(a.deployment_default)]),
      el('span', {
        class: 'gl-state' + (a.operator_override === null ||
                             a.operator_override === undefined
                             ? '' : ' gl-state-set'),
      }, ['override ' + tri(a.operator_override)]),
      a.differs_from_canonical
        ? el('span', { class: 'gl-differs' }, ['differs from canonical'])
        : null,
    ]);

    var actions;
    if (a.switchable) {
      actions = el('div', { class: 'gl-actions' }, [
        el('button', {
          class: 'gl-mini' + (a.effective ? ' gl-mini-active' : ''),
          disabled: _state.busy ? 'disabled' : undefined,
          onclick: function () { setAuthority(a.id, true); },
        }, ['On']),
        el('button', {
          class: 'gl-mini' + (!a.effective ? ' gl-mini-active' : ''),
          disabled: _state.busy ? 'disabled' : undefined,
          onclick: function () { setAuthority(a.id, false); },
        }, ['Off']),
        el('button', {
          class: 'gl-mini gl-mini-reset',
          // Reset DELETES the override. It is not "set it back to the
          // default value" — the default stays live in code, so changing
          // it later moves this row with it.
          disabled: (_state.busy ||
                     a.operator_override === null ||
                     a.operator_override === undefined) ? 'disabled' : undefined,
          onclick: function () { setAuthority(a.id, null); },
        }, ['Reset']),
        busy ? el('span', { class: 'gl-row-busy' }, ['…']) : null,
      ]);
    } else {
      // NOT a disabled checkbox. "Cannot, for safety" and "cannot, until
      // somebody splits a string" are different truths and the operator
      // is told which one they are looking at.
      actions = el('div', { class: 'gl-actions gl-locked' }, [
        el('span', { class: 'gl-policy gl-policy-' + String(a.policy).toLowerCase() },
           [a.policy]),
        el('span', { class: 'gl-policy-reason' }, [
          a.policy_reason || 'not overridable from this panel']),
      ]);
    }

    var docsOpen = !!_state.showDocs[a.id];
    var docs = docsOpen ? el('div', { class: 'gl-docs' }, [
      a.purpose ? el('p', { class: 'gl-purpose' }, ['Purpose: ' + a.purpose]) : null,
      a.motivating_failure
        ? el('p', { class: 'gl-motive' }, ['Created by: ' + a.motivating_failure])
        : null,
      a.known_harm
        ? el('p', { class: 'gl-harm' }, ['Measured harm: ' + a.known_harm])
        : null,
      a.location ? el('p', { class: 'gl-loc gl-mono' }, [a.location]) : null,
      el('p', { class: 'gl-cf' }, ['counterfactual: ' + a.counterfactual]),
    ]) : null;

    return el('div', { class: 'gl-row' + (a.effective ? '' : ' gl-row-off') }, [
      el('div', { class: 'gl-row-head' }, cells.concat([
        el('button', {
          class: 'gl-why',
          onclick: function () {
            _state.showDocs[a.id] = !_state.showDocs[a.id];
            render();
          },
        }, [docsOpen ? 'hide' : 'why']),
      ])),
      states,
      actions,
      docs,
    ]);
  }

  function renderGroups(d) {
    var byClass = {};
    (d.authorities || []).forEach(function (a) {
      (byClass[a.cls] = byClass[a.cls] || []).push(a);
    });
    var order = CLASS_ORDER.filter(function (c) { return byClass[c]; })
      .concat(Object.keys(byClass).filter(function (c) {
        return CLASS_ORDER.indexOf(c) === -1;
      }));
    return order.map(function (cls) {
      var rows = byClass[cls];
      var running = rows.filter(function (a) { return a.effective; }).length;
      return el('div', { class: 'gl-group' }, [
        el('div', { class: 'gl-group-head' }, [
          el('span', { class: 'gl-group-name' }, [cls]),
          el('span', { class: 'gl-group-count' }, [
            running + ' running / ' + rows.length]),
        ]),
        el('div', { class: 'gl-group-rows' }, rows.map(renderRow)),
      ]);
    });
  }

  // Exported and called with an explicit mount + payload so the operator
  // view can be tested by RENDERING it. A source-string check cannot tell
  // whether the operator actually sees the effective state or the reason
  // that produced it — the export exists for the same reason
  // `lvStoryReviewRenderExtraction` does.
  function renderInto(mount, s) {
    if (!mount) return;
    mount.innerHTML = '';

    if (s.enabled === false) {
      mount.appendChild(el('div', { class: 'gl-empty' }, [
        'Guard Lab is off. Set HORNELORE_OPERATOR_GUARD_LAB=1 on the API ' +
        'to enable the control surface.']));
      return;
    }

    mount.appendChild(el('div', { class: 'gl-head' }, [
      el('span', { class: 'gl-title' }, ['Guard Lab — narrator-facing authorities']),
      el('button', {
        class: 'gl-collapse',
        onclick: function () { _state.collapsed = !_state.collapsed; render(); },
      }, [s.collapsed ? 'show' : 'hide']),
    ]));

    if (s.collapsed) {
      var summary = s.data
        ? (s.data.counts.selected + ' running / ' + s.data.counts.total +
           ' · revision ' + s.data.revision)
        : 'not loaded';
      mount.appendChild(el('div', { class: 'gl-collapsed' }, [summary]));
      return;
    }

    if (s.error) {
      mount.appendChild(el('div', { class: 'gl-error' }, [String(s.error)]));
    }
    if (s.conflict) {
      // The click is refused and SAID SO. The live configuration has
      // already been adopted above, so what is on screen is now true.
      mount.appendChild(el('div', { class: 'gl-conflict' }, [
        el('div', { class: 'gl-conflict-head' }, ['Change refused — stale view']),
        el('div', {}, [s.conflict.message]),
        el('div', { class: 'gl-conflict-rev' }, [
          'you were looking at revision ' + s.conflict.expected +
          '; the live configuration is revision ' + s.conflict.actual +
          '. The panel now shows the live one — re-apply if you still want it.']),
      ]));
    }
    if (s.loading && !s.data) {
      mount.appendChild(el('div', { class: 'gl-empty' }, ['Loading…']));
      return;
    }
    if (!s.data) {
      mount.appendChild(el('div', { class: 'gl-empty' }, [
        'No configuration loaded. Press Refresh.']));
      return;
    }

    var d = s.data;
    mount.appendChild(renderIdentity(d));
    mount.appendChild(el('div', { class: 'gl-applies' }, [d.applies_note || '']));
    var gateBlock = renderGate(d.gate);
    if (gateBlock) mount.appendChild(gateBlock);

    if (d.pending_seam && d.pending_seam.length) {
      // While this is non-empty the button's label is not the whole
      // truth: a pending-seam authority stays RUNNING through the preset.
      mount.appendChild(el('div', { class: 'gl-pending' }, [
        'All Switchable Off leaves ' + d.pending_seam.length +
        ' authority(ies) RUNNING — not yet separable in code: ' +
        d.pending_seam.map(function (p) { return p.display; }).join(', ')]));
    }

    mount.appendChild(renderControls(d));
    var body = el('div', { class: 'gl-body' }, renderGroups(d));
    mount.appendChild(body);

    if (d.fetched_at) {
      mount.appendChild(el('div', { class: 'gl-fetched' }, [
        'fetched ' + d.fetched_at]));
    }
  }

  function render() {
    renderInto(document.getElementById(MOUNT_ID), _state);
  }

  window.lvGuardLabRenderInto = renderInto;
  window.lvGuardLabRefresh = refresh;
  window.lvGuardLabState = function () { return _state; };

  function tryInitialFetch() {
    if (!document.getElementById(MOUNT_ID)) return;
    // Cheap: the collapsed summary needs the counts, and one read of a
    // 43-row table costs nothing next to being wrong about it.
    refresh();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', tryInitialFetch);
  } else {
    tryInitialFetch();
  }
})();
