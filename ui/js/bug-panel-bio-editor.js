// WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase E Bug Panel surface.
//
// Tier 4 operator bio editor. Per-narrator view, grouped by
// field_category. Each field shows current status (color-coded:
// green=approved, amber=needs_verify, gray=empty, red=conflicted);
// operator clicks to enter / edit / approve / mark-unanswerable.
//
// Pulls from GET /api/operator/bio-editor/facts (gated by
// HORNELORE_OPERATOR_BIO_EDITOR=1 server-side; 404 when off).
// Direct entries hit POST /api/operator/bio-editor/enter; approvals
// hit /approve; conflict resolution hits /resolve-conflict;
// mark-unanswerable hits /mark-unanswerable.
//
// NEVER narrator-visible — Bug Panel only.
(function () {
  'use strict';

  const MOUNT_ID = 'lv10dBpBioEditor';
  const _O = (typeof ORIGIN !== 'undefined' && ORIGIN) || 'http://localhost:8000';
  const BASE = _O + '/api/operator/bio-editor';

  let _state = {
    loading: false,
    enabled: null,
    narratorId: '',
    data: null,
    error: null,
    expandedFields: {},
  };

  function el(tag, attrs, children) {
    const n = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === 'class') n.className = attrs[k];
        else if (k === 'onclick') n.addEventListener('click', attrs[k]);
        else if (k === 'oninput') n.addEventListener('input', attrs[k]);
        else if (k === 'onkeydown') n.addEventListener('keydown', attrs[k]);
        else n.setAttribute(k, attrs[k]);
      });
    }
    if (children) {
      (Array.isArray(children) ? children : [children]).forEach(function (c) {
        if (c == null) return;
        n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
      });
    }
    return n;
  }

  function statusClass(statuses) {
    // statuses: array of strings for all rows under this field
    if (statuses.indexOf('conflicted') !== -1) return 'bp-bio-status-red';
    if (statuses.indexOf('approved') !== -1) return 'bp-bio-status-green';
    if (statuses.indexOf('operator_entered') !== -1) return 'bp-bio-status-green';
    if (statuses.indexOf('document_sourced') !== -1) return 'bp-bio-status-green';
    if (statuses.indexOf('extracted_needs_verify') !== -1) return 'bp-bio-status-amber';
    if (statuses.indexOf('anchored_asked_pending') !== -1) return 'bp-bio-status-amber';
    return 'bp-bio-status-gray';
  }

  function statusLabel(statuses) {
    if (statuses.indexOf('conflicted') !== -1) return 'conflict';
    if (statuses.indexOf('approved') !== -1) return 'approved';
    if (statuses.indexOf('operator_entered') !== -1) return 'operator';
    if (statuses.indexOf('document_sourced') !== -1) return 'document';
    if (statuses.indexOf('extracted_needs_verify') !== -1) return 'needs verify';
    if (statuses.indexOf('anchored_asked_pending') !== -1) return 'asked';
    return 'empty';
  }

  async function fetchFacts() {
    if (!_state.narratorId) {
      _state.data = null;
      _state.error = null;
      _state.enabled = null;
      render();
      return;
    }
    _state.loading = true;
    _state.error = null;
    render();
    try {
      const url = BASE + '/facts?narrator_id=' +
        encodeURIComponent(_state.narratorId);
      const res = await fetch(url);
      if (res.status === 404) {
        _state.enabled = false;
        _state.data = null;
      } else if (!res.ok) {
        _state.error = 'HTTP ' + res.status;
        _state.data = null;
      } else {
        _state.enabled = true;
        _state.data = await res.json();
      }
    } catch (e) {
      _state.error = String(e.message || e);
      _state.data = null;
    } finally {
      _state.loading = false;
      render();
    }
  }

  async function postJson(path, body) {
    const res = await fetch(BASE + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error('HTTP ' + res.status + ': ' + text);
    }
    return res.json();
  }

  async function directEntry(fieldKey) {
    if (!_state.narratorId) return;
    const value = window.prompt('Enter value for ' + fieldKey + ':');
    if (value == null || !value.trim()) return;
    try {
      await postJson('/enter', {
        narrator_id: _state.narratorId,
        field_key: fieldKey,
        value: value,
      });
      await fetchFacts();
    } catch (e) {
      window.alert('Entry failed: ' + e.message);
    }
  }

  async function approveRow(factId) {
    if (!window.confirm('Approve this row?')) return;
    try {
      await postJson('/approve', { fact_id: factId });
      await fetchFacts();
    } catch (e) {
      window.alert('Approve failed: ' + e.message);
    }
  }

  async function markUnanswerable(fieldKey) {
    if (!_state.narratorId) return;
    if (!window.confirm(
      'Mark ' + fieldKey + ' as known-unanswerable for this narrator?',
    )) return;
    try {
      await postJson('/mark-unanswerable', {
        narrator_id: _state.narratorId,
        field_key: fieldKey,
      });
      await fetchFacts();
    } catch (e) {
      window.alert('Mark failed: ' + e.message);
    }
  }

  async function resolveConflict(fieldKey, promoteId, supersedeIds) {
    if (!_state.narratorId) return;
    if (!window.confirm(
      'Promote row ' + promoteId + ' and supersede ' + supersedeIds.length +
      ' peer row(s)?',
    )) return;
    try {
      await postJson('/resolve-conflict', {
        narrator_id: _state.narratorId,
        field_key: fieldKey,
        promote_fact_id: promoteId,
        supersede_fact_ids: supersedeIds,
      });
      await fetchFacts();
    } catch (e) {
      window.alert('Resolve failed: ' + e.message);
    }
  }

  function renderRow(field, row) {
    return el('div', { class: 'bp-bio-row' }, [
      el('span', { class: 'bp-bio-row-value' }, [String(row.value || '—')]),
      el('span', { class: 'bp-bio-row-status' }, [row.status]),
      row.status !== 'approved' && row.status !== 'operator_entered'
        ? el('button', {
            class: 'bp-bio-row-btn',
            onclick: function () { approveRow(row.id); },
          }, ['Approve'])
        : null,
    ]);
  }

  function renderField(field) {
    const rows = field.rows || [];
    const statuses = rows.map(function (r) { return r.status; });
    const cls = 'bp-bio-field ' + statusClass(statuses);
    const isOpen = !!_state.expandedFields[field.field_key];

    const header = el('div', {
      class: 'bp-bio-field-header',
      onclick: function () {
        _state.expandedFields[field.field_key] = !isOpen;
        render();
      },
    }, [
      el('span', { class: 'bp-bio-field-label' }, [field.field_label]),
      el('span', { class: 'bp-bio-field-status' }, [statusLabel(statuses)]),
      el('span', { class: 'bp-bio-field-toggle' }, [isOpen ? '▾' : '▸']),
    ]);

    if (!isOpen) return el('div', { class: cls }, [header]);

    const body = el('div', { class: 'bp-bio-field-body' }, [
      rows.length
        ? el('div', null, rows.map(function (r) { return renderRow(field, r); }))
        : el('div', { class: 'bp-bio-empty' }, ['No rows yet.']),
      el('div', { class: 'bp-bio-actions' }, [
        el('button', {
          class: 'bp-bio-action-btn',
          onclick: function () { directEntry(field.field_key); },
        }, ['Direct entry']),
        el('button', {
          class: 'bp-bio-action-btn',
          onclick: function () { markUnanswerable(field.field_key); },
        }, ['Mark unanswerable']),
        statuses.indexOf('conflicted') !== -1 && rows.length > 1
          ? el('button', {
              class: 'bp-bio-action-btn bp-bio-resolve-btn',
              onclick: function () {
                // Simplest path: promote the first row, supersede the rest.
                // A more elaborate picker UI is deferred to follow-up UX work.
                const promote = rows[0].id;
                const supersede = rows.slice(1).map(function (r) { return r.id; });
                resolveConflict(field.field_key, promote, supersede);
              },
            }, ['Resolve (promote 1st)'])
          : null,
      ]),
    ]);

    return el('div', { class: cls }, [header, body]);
  }

  function renderCategory(cat, fields) {
    return el('div', { class: 'bp-bio-cat' }, [
      el('div', { class: 'bp-bio-cat-title' }, [cat]),
      el('div', null, fields.map(renderField)),
    ]);
  }

  function renderDisabled() {
    return el('div', { class: 'bp-bio-disabled' }, [
      'Bio editor surface disabled. Set ',
      el('code', null, ['HORNELORE_OPERATOR_BIO_EDITOR=1']),
      ' in the server env and reload the stack.',
    ]);
  }

  function render() {
    const mount = document.getElementById(MOUNT_ID);
    if (!mount) return;
    mount.innerHTML = '';
    mount.appendChild(el('div', { class: 'bp-bio-section-header' }, [
      el('strong', null, ['Bio editor']),
      el('input', {
        type: 'text', placeholder: 'narrator_id',
        value: _state.narratorId,
        class: 'bp-bio-narrator-input',
        oninput: function (e) { _state.narratorId = e.target.value.trim(); },
        onkeydown: function (e) { if (e.key === 'Enter') fetchFacts(); },
      }),
      el('button', {
        class: 'bp-bio-refresh', onclick: fetchFacts,
      }, [_state.loading ? '…' : 'Refresh']),
    ]));
    if (_state.enabled === false) {
      mount.appendChild(renderDisabled());
      return;
    }
    if (_state.error) {
      mount.appendChild(el('div', { class: 'bp-bio-error' },
        ['Error: ' + _state.error]));
      return;
    }
    if (!_state.data) {
      mount.appendChild(el('div', { class: 'bp-bio-empty' },
        ['Enter a narrator_id and press Refresh to load.']));
      return;
    }
    // Group fields by category in the existing seed-order rendered
    // by the server endpoint.
    const byCat = {};
    const catOrder = [];
    (_state.data.fields || []).forEach(function (f) {
      if (!byCat[f.field_category]) {
        byCat[f.field_category] = [];
        catOrder.push(f.field_category);
      }
      byCat[f.field_category].push(f);
    });
    catOrder.forEach(function (cat) {
      mount.appendChild(renderCategory(cat, byCat[cat]));
    });
  }

  window.lvBpBioEditorRefresh = fetchFacts;
  document.addEventListener('DOMContentLoaded', function () { render(); });
})();
