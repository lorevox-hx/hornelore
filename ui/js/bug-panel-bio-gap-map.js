// WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase F Bug Panel surface.
//
// Operator gap map dashboard. Polls /api/operator/bio-gap-map/summary
// for a narrator and renders five sections per WO §Bio gap map:
//   - Completeness (per-category fill rates + overall percentage)
//   - Recently asked (last anchored asks + outcomes)
//   - Suggested asks (high-value gaps without chapter anchor)
//   - Conflicts pending (conflicted bio_facts pairs)
//   - Creep telemetry banner (Defense 1 — green / amber / red)
//
// Pulls from GET /api/operator/bio-gap-map/summary (gated by
// HORNELORE_OPERATOR_BIO_GAP_MAP=1 server-side; if off, the endpoint
// returns 404 and we render a quiet placeholder).
//
// NEVER narrator-visible — Bug Panel only.
(function () {
  'use strict';

  const MOUNT_ID = 'lv10dBpBioGapMap';
  const _O = (typeof ORIGIN !== 'undefined' && ORIGIN) || 'http://localhost:8000';
  const SUMMARY_ENDPOINT = _O + '/api/operator/bio-gap-map/summary';

  let _state = {
    loading: false,
    enabled: null,
    narratorId: '',
    summary: null,
    error: null,
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

  function fmtPct(v) {
    if (v == null || isNaN(v)) return '—';
    return Number(v).toFixed(1) + '%';
  }

  function fmtDelta(v) {
    if (v == null || isNaN(v)) return '—';
    const n = Number(v);
    return (n >= 0 ? '+' : '') + n.toFixed(3);
  }

  async function fetchSummary() {
    if (!_state.narratorId) {
      _state.summary = null;
      _state.error = null;
      _state.enabled = null;
      render();
      return;
    }
    _state.loading = true;
    _state.error = null;
    render();
    try {
      const url = SUMMARY_ENDPOINT + '?narrator_id=' +
        encodeURIComponent(_state.narratorId);
      const res = await fetch(url);
      if (res.status === 404) {
        _state.enabled = false;
        _state.summary = null;
      } else if (!res.ok) {
        _state.error = 'HTTP ' + res.status;
        _state.summary = null;
      } else {
        _state.enabled = true;
        _state.summary = await res.json();
      }
    } catch (e) {
      _state.error = String(e.message || e);
      _state.summary = null;
    } finally {
      _state.loading = false;
      render();
    }
  }

  function renderTelemetryBanner(t) {
    if (!t || !t.sample_size) {
      return el('div', { class: 'bp-bio-telemetry bp-bio-telemetry-green' },
        ['Creep telemetry — green (no anchored asks yet)']);
    }
    const warning = t.warning || 'green';
    const cls = 'bp-bio-telemetry bp-bio-telemetry-' + warning;
    const lines = [
      'Creep telemetry — ' + warning.toUpperCase(),
      ' • Continuation delta avg: ' + fmtDelta(t.rolling_continuation_delta_avg) +
        ' (amber at ' + fmtDelta(t.delta_amber_threshold) + ')',
      ' • Chapter-end rate: ' + fmtPct((t.ask_caused_chapter_end_rate || 0) * 100) +
        ' (red at ' + fmtPct((t.chapter_end_red_threshold || 0) * 100) + ')',
      ' • Sample size: ' + (t.sample_size || 0),
    ];
    return el('div', { class: cls },
      lines.map(function (l) { return el('div', null, [l]); }));
  }

  function renderCompleteness(c) {
    if (!c) return el('div', null, ['no data']);
    const head = el('div', { class: 'bp-bio-section-head' },
      ['Overall: ' + fmtPct(c.overall_percentage) +
       ' (' + (c.filled_fields || 0) + ' / ' + (c.total_fields || 0) + ')']);
    const rows = (c.by_category || []).map(function (cc) {
      return el('div', { class: 'bp-bio-cat-row' }, [
        el('span', { class: 'bp-bio-cat-name' }, [cc.category]),
        el('span', { class: 'bp-bio-cat-pct' }, [fmtPct(cc.percentage)]),
        el('span', { class: 'bp-bio-cat-count' },
          ['(' + (cc.filled_fields || 0) + '/' + (cc.total_fields || 0) + ')']),
      ]);
    });
    return el('div', null, [head].concat(rows));
  }

  function renderRecentlyAsked(items) {
    if (!items || !items.length) {
      return el('div', { class: 'bp-bio-empty' },
        ['No anchored asks yet for this narrator.']);
    }
    return el('div', null, items.map(function (r) {
      const outcomeCls = 'bp-bio-outcome bp-bio-outcome-' + (r.outcome || 'unknown');
      return el('div', { class: 'bp-bio-ask-row' }, [
        el('span', { class: 'bp-bio-ask-label' }, [r.field_label || r.field_key]),
        el('span', { class: outcomeCls }, [r.outcome || 'unknown']),
        el('span', { class: 'bp-bio-ask-anchor' }, ['anchor: ' + (r.matched_anchor || '')]),
      ]);
    }));
  }

  function renderSuggested(items, total) {
    if (!items || !items.length) {
      return el('div', { class: 'bp-bio-empty' },
        ['All high-value fields are filled or asked.']);
    }
    const head = total && total > items.length
      ? el('div', { class: 'bp-bio-section-sub' },
          ['Showing top ' + items.length + ' of ' + total + ' gaps.'])
      : null;
    const rows = items.map(function (s) {
      return el('div', { class: 'bp-bio-suggest-row' }, [
        el('span', { class: 'bp-bio-suggest-cat' }, [s.field_category]),
        el('span', { class: 'bp-bio-suggest-label' }, [s.field_label || s.field_key]),
      ]);
    });
    return el('div', null, [head].concat(rows));
  }

  function renderConflicts(items) {
    if (!items || !items.length) {
      return el('div', { class: 'bp-bio-empty' }, ['No conflicts pending.']);
    }
    return el('div', null, items.map(function (c) {
      return el('div', { class: 'bp-bio-conflict-row' }, [
        el('div', { class: 'bp-bio-conflict-label' }, [c.field_label || c.field_key]),
        el('div', { class: 'bp-bio-conflict-rows' }, (c.rows || []).map(function (r) {
          return el('div', { class: 'bp-bio-conflict-value' },
            [r.value + ' (' + r.status + ')']);
        })),
      ]);
    }));
  }

  function renderDisabled() {
    return el('div', { class: 'bp-bio-disabled' }, [
      'Bio gap map surface disabled. Set ',
      el('code', null, ['HORNELORE_OPERATOR_BIO_GAP_MAP=1']),
      ' in the server env and reload the stack.',
    ]);
  }

  function render() {
    const mount = document.getElementById(MOUNT_ID);
    if (!mount) return;
    mount.innerHTML = '';
    const header = el('div', { class: 'bp-bio-section-header' }, [
      el('strong', null, ['Bio gap map']),
      el('input', {
        type: 'text', placeholder: 'narrator_id',
        value: _state.narratorId,
        class: 'bp-bio-narrator-input',
        oninput: function (e) { _state.narratorId = e.target.value.trim(); },
        onkeydown: function (e) { if (e.key === 'Enter') fetchSummary(); },
      }),
      el('button', {
        class: 'bp-bio-refresh', onclick: fetchSummary,
      }, [_state.loading ? '…' : 'Refresh']),
    ]);
    mount.appendChild(header);
    if (_state.enabled === false) {
      mount.appendChild(renderDisabled());
      return;
    }
    if (_state.error) {
      mount.appendChild(el('div', { class: 'bp-bio-error' },
        ['Error: ' + _state.error]));
      return;
    }
    if (!_state.summary) {
      mount.appendChild(el('div', { class: 'bp-bio-empty' },
        ['Enter a narrator_id and press Refresh to load.']));
      return;
    }
    const s = _state.summary;
    mount.appendChild(renderTelemetryBanner(s.creep_telemetry));
    mount.appendChild(el('div', { class: 'bp-bio-section' }, [
      el('div', { class: 'bp-bio-section-title' }, ['Completeness']),
      renderCompleteness(s.completeness),
    ]));
    mount.appendChild(el('div', { class: 'bp-bio-section' }, [
      el('div', { class: 'bp-bio-section-title' }, ['Recently asked']),
      renderRecentlyAsked(s.recently_asked),
    ]));
    mount.appendChild(el('div', { class: 'bp-bio-section' }, [
      el('div', { class: 'bp-bio-section-title' }, ['Suggested asks']),
      renderSuggested(s.suggested_asks, s.suggested_asks_total),
    ]));
    mount.appendChild(el('div', { class: 'bp-bio-section' }, [
      el('div', { class: 'bp-bio-section-title' }, ['Conflicts pending']),
      renderConflicts(s.conflicts),
    ]));
  }

  window.lvBpBioGapMapRefresh = fetchSummary;
  document.addEventListener('DOMContentLoaded', function () {
    render();
  });
})();
