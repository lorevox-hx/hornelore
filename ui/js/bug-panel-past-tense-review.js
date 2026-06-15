// WO-LORI-SAFETY-LLM-CLASSIFIER-01 (2026-06-14) — Bug Panel past-tense
// flag review list.
//
// Read-only operator surface listing segment_flags with category
// "past_tense_ideation_acknowledged". Mirrors the bug-panel-story-
// review.js posture: gated server-side (HORNELORE_OPERATOR_PAST_
// TENSE_REVIEW=1), 404s → quiet "feature disabled" placeholder, no
// polling — operators click Refresh when they want to look.
//
// What the operator sees:
//   - count + scrollable list of past-tense flags, newest-first
//   - per-row: session_id (truncated) + amber category badge +
//             relative-or-absolute timestamp
//   - 3-decision row stub (no_action / follow_up_outside_session /
//             convert_to_active_concern) renders as DISABLED buttons
//             for v1; the state-transition endpoints land in a
//             follow-up WO. Operators can see the affordance without
//             being able to fire it (so the UI doesn't overpromise).
//
// NEVER narrator-visible — Bug Panel only.
(function () {
  'use strict';

  const MOUNT_ID = 'lv10dBpPastTenseReview';
  const _O = (typeof ORIGIN !== 'undefined' && ORIGIN) || 'http://localhost:8000';
  const ENDPOINT = _O + '/api/operator/past-tense-flags';
  const DEFAULT_LIMIT = 50;

  let _state = {
    loading: false,
    enabled: null, // null = unknown until first probe
    items: [],
    count: 0,
    fetchedAt: null,
    error: null,
  };

  function el(tag, attrs, children) {
    const n = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === 'class') n.className = attrs[k];
        else if (k === 'onclick') n.addEventListener('click', attrs[k]);
        else n.setAttribute(k, attrs[k]);
      });
    }
    (children || []).forEach(function (c) {
      if (c == null) return;
      n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return n;
  }

  function fmtTime(iso) {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return iso;
      return d.toLocaleString();
    } catch (_) { return iso; }
  }

  function fmtSession(sid) {
    if (!sid) return '<unknown>';
    if (sid.length > 24) return sid.slice(0, 8) + '…' + sid.slice(-4);
    return sid;
  }

  async function fetchFlags() {
    _state.loading = true;
    _state.error = null;
    render();

    const url = ENDPOINT + '?limit=' + DEFAULT_LIMIT;
    try {
      const resp = await fetch(url, { credentials: 'same-origin' });
      if (resp.status === 404) {
        _state.enabled = false;
        _state.items = [];
        _state.count = 0;
        return;
      }
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      _state.enabled = true;
      _state.items = data.items || [];
      _state.count = data.count || 0;
      _state.fetchedAt = data.fetched_at || null;
    } catch (e) {
      _state.enabled = true;
      _state.error = String(e && e.message ? e.message : e);
      _state.items = [];
      _state.count = 0;
    } finally {
      _state.loading = false;
      render();
    }
  }

  function renderDecisionStub() {
    // 3-decision affordance, disabled in v1 — visible so operators
    // see what the future state model will be, but not yet wired.
    const mk = function (label, title) {
      return el('button', {
        class: 'pt-decision-btn',
        disabled: 'true',
        title: title + ' (state transitions land in a follow-up WO)',
      }, [label]);
    };
    return el('div', { class: 'pt-decision-row' }, [
      mk('No action', 'Operator reviewed; no further action needed'),
      mk('Follow up outside session', 'Reach out to narrator in a separate channel'),
      mk('Convert to active concern', 'Escalate this past-tense disclosure to active monitoring'),
    ]);
  }

  function renderRow(item) {
    return el('div', { class: 'pt-row' }, [
      el('div', { class: 'pt-row-header' }, [
        el('span', { class: 'pt-badge' }, ['past-tense memoir ideation']),
        el('span', { class: 'pt-session', title: item.session_id || '' }, [
          fmtSession(item.session_id),
        ]),
        el('span', { class: 'pt-time' }, [fmtTime(item.created_at)]),
      ]),
      renderDecisionStub(),
    ]);
  }

  function render() {
    const root = document.getElementById(MOUNT_ID);
    if (!root) return;
    root.innerHTML = '';

    const title = el('div', { class: 'pt-title' }, ['Past-tense memoir flags']);
    const refresh = el('button', {
      class: 'pt-refresh-btn',
      onclick: function () { fetchFlags(); },
    }, [_state.loading ? 'Loading…' : 'Refresh']);
    const header = el('div', { class: 'pt-header' }, [title, refresh]);

    let body;
    if (_state.enabled === false) {
      body = el('div', { class: 'pt-placeholder' }, [
        'Past-tense review surface is disabled. ' +
        'Set HORNELORE_OPERATOR_PAST_TENSE_REVIEW=1 to enable.',
      ]);
    } else if (_state.error) {
      body = el('div', { class: 'pt-error' }, ['Error: ' + _state.error]);
    } else if (_state.loading && _state.items.length === 0) {
      body = el('div', { class: 'pt-placeholder' }, ['Loading…']);
    } else if (_state.items.length === 0) {
      body = el('div', { class: 'pt-placeholder' }, [
        'No past-tense flags. (None written this stack session, or ' +
        'classifier flag off.)',
      ]);
    } else {
      const list = el('div', { class: 'pt-list' }, _state.items.map(renderRow));
      const stamp = _state.fetchedAt
        ? el('div', { class: 'pt-stamp' }, ['Fetched ' + fmtTime(_state.fetchedAt)])
        : null;
      body = el('div', null, [list, stamp]);
    }

    root.appendChild(el('div', { class: 'pt-panel' }, [
      header,
      el('div', { class: 'pt-count' }, ['count: ' + _state.count]),
      body,
    ]));
  }

  // Initial fetch when DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', fetchFlags);
  } else {
    setTimeout(fetchFlags, 0);
  }

  // Expose for manual refresh from console
  window.lvBpPastTenseRefresh = fetchFlags;
})();
