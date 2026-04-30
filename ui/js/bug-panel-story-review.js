// WO-LORI-STORY-CAPTURE-01 Phase 1B — Bug Panel story-candidates list.
//
// Read-only operator surface for unreviewed story_candidate rows.
// Pulls from GET /api/operator/story-candidates (gated by
// HORNELORE_OPERATOR_STORY_REVIEW=1 server-side; if off the endpoint
// returns 404 and we render a quiet placeholder).
//
// Phase 1B is intentionally minimal:
//   - count + scrollable list of unreviewed candidates
//   - per-row: narrator + trigger_reason + first 200 chars of transcript
//             + scene_anchor_count + confidence + created_at
//   - Refresh button (manual; no polling — operators choose when to look)
//   - Optional narrator filter (text input; empty = all narrators)
//   - NO actions (promote/refine/discard land in Phase 3)
//
// NEVER narrator-visible — this surface lives in the Bug Panel only.
(function () {
  'use strict';

  const MOUNT_ID = 'lv10dBpStoryReview';
  const ENDPOINT = '/api/operator/story-candidates';
  const DEFAULT_LIMIT = 50;

  let _state = {
    loading: false,
    enabled: null, // null = unknown until first probe
    items: [],
    count: 0,
    fetchedAt: null,
    narratorFilter: '',
    error: null,
  };

  function el(tag, attrs, children) {
    const n = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === 'class') {
          n.className = attrs[k];
        } else if (k === 'onclick') {
          n.addEventListener('click', attrs[k]);
        } else if (k === 'oninput') {
          n.addEventListener('input', attrs[k]);
        } else if (k === 'onkeydown') {
          n.addEventListener('keydown', attrs[k]);
        } else {
          n.setAttribute(k, attrs[k]);
        }
      });
    }
    (children || []).forEach(function (c) {
      if (c == null) return;
      if (typeof c === 'string') {
        n.appendChild(document.createTextNode(c));
      } else {
        n.appendChild(c);
      }
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

  function fmtNarrator(narratorId) {
    if (!narratorId) return '<unknown>';
    // Bug Panel users typically deal with full narrator-id strings;
    // if the id is a UUID prefix we keep it short for readability.
    if (narratorId.length > 24) return narratorId.slice(0, 8) + '…';
    return narratorId;
  }

  function fmtTriggerBadge(reason) {
    const cls = (reason === 'full_threshold')
      ? 'story-badge-full'
      : (reason === 'borderline_scene_anchor')
        ? 'story-badge-borderline'
        : 'story-badge-other';
    return el('span', { class: 'story-badge ' + cls }, [reason || '?']);
  }

  function fmtConfidence(c) {
    const cls = 'story-conf story-conf-' + (c || 'unknown');
    return el('span', { class: cls }, [c || 'unknown']);
  }

  async function fetchCandidates() {
    _state.loading = true;
    _state.error = null;
    render();

    let url = ENDPOINT + '?limit=' + DEFAULT_LIMIT;
    if (_state.narratorFilter && _state.narratorFilter.trim()) {
      url += '&narrator_id=' + encodeURIComponent(_state.narratorFilter.trim());
    }

    try {
      const resp = await fetch(url, { credentials: 'same-origin' });
      if (resp.status === 404) {
        _state.enabled = false;
        _state.items = [];
        _state.count = 0;
        return;
      }
      if (!resp.ok) {
        throw new Error('HTTP ' + resp.status);
      }
      const data = await resp.json();
      _state.enabled = true;
      _state.items = data.items || [];
      _state.count = data.count || 0;
      _state.fetchedAt = data.fetched_at || null;
    } catch (e) {
      _state.enabled = true; // endpoint reachable enough to error
      _state.error = String(e && e.message ? e.message : e);
      _state.items = [];
      _state.count = 0;
    } finally {
      _state.loading = false;
      render();
    }
  }

  function renderRow(item) {
    const meta = [];
    meta.push(fmtTriggerBadge(item.trigger_reason));
    meta.push(el('span', { class: 'story-meta' }, [
      'anchors=' + (item.scene_anchor_count != null ? item.scene_anchor_count : '?'),
    ]));
    meta.push(el('span', { class: 'story-meta' }, [
      'words=' + (item.word_count != null ? item.word_count : '?'),
    ]));
    meta.push(fmtConfidence(item.confidence));
    if (item.era_candidates && item.era_candidates.length) {
      meta.push(el('span', { class: 'story-meta' }, [
        'eras=' + item.era_candidates.join(','),
      ]));
    }
    if (item.estimated_year_low != null && item.estimated_year_high != null) {
      meta.push(el('span', { class: 'story-meta' }, [
        'years=' + item.estimated_year_low + '–' + item.estimated_year_high,
      ]));
    }

    const previewText =
      (item.transcript_preview || '') +
      (item.transcript_truncated ? '…' : '');

    const headerLine = el('div', { class: 'story-row-header' }, [
      el('span', { class: 'story-narrator', title: item.narrator_id || '' }, [
        fmtNarrator(item.narrator_id),
      ]),
      el('span', { class: 'story-time' }, [fmtTime(item.created_at)]),
    ]);

    return el('div', { class: 'story-row' }, [
      headerLine,
      el('div', { class: 'story-meta-line' }, meta),
      el('div', { class: 'story-preview' }, [previewText || '(empty transcript)']),
    ]);
  }

  function renderControls() {
    const refreshBtn = el('button', {
      class: 'story-refresh-btn',
      onclick: function () { fetchCandidates(); },
    }, ['Refresh']);

    const filterInput = el('input', {
      class: 'story-filter-input',
      type: 'text',
      placeholder: 'narrator_id (optional)',
      value: _state.narratorFilter || '',
      oninput: function (e) { _state.narratorFilter = e.target.value; },
      onkeydown: function (e) {
        if (e.key === 'Enter') { e.preventDefault(); fetchCandidates(); }
      },
    });

    return el('div', { class: 'story-controls' }, [
      filterInput, refreshBtn,
    ]);
  }

  function renderHeader() {
    let countText;
    if (_state.loading) countText = 'Loading…';
    else if (_state.error) countText = 'Error';
    else countText = _state.count + ' unreviewed';

    return el('div', { class: 'story-section-header' }, [
      el('span', { class: 'story-section-title' }, ['Story Candidates']),
      el('span', { class: 'story-section-count' }, [countText]),
    ]);
  }

  function render() {
    const mount = document.getElementById(MOUNT_ID);
    if (!mount) return;
    mount.innerHTML = '';

    // Backend gate is off → quiet placeholder, no controls.
    if (_state.enabled === false) {
      mount.appendChild(el('div', { class: 'story-section-header' }, [
        el('span', { class: 'story-section-title' }, ['Story Candidates']),
        el('span', { class: 'story-section-count' }, ['feature disabled']),
      ]));
      mount.appendChild(el('div', { class: 'story-empty' }, [
        'Set HORNELORE_OPERATOR_STORY_REVIEW=1 in .env and restart to enable.',
      ]));
      return;
    }

    mount.appendChild(renderHeader());
    mount.appendChild(renderControls());

    if (_state.error) {
      mount.appendChild(el('div', { class: 'story-error' }, [
        'fetch failed: ' + _state.error,
      ]));
      return;
    }

    if (_state.loading) {
      mount.appendChild(el('div', { class: 'story-empty' }, ['Loading…']));
      return;
    }

    if (!_state.items.length) {
      const msg = _state.narratorFilter && _state.narratorFilter.trim()
        ? 'No unreviewed candidates for narrator "' + _state.narratorFilter.trim() + '".'
        : 'No unreviewed story candidates yet. Stories captured during sessions will appear here.';
      mount.appendChild(el('div', { class: 'story-empty' }, [msg]));
      return;
    }

    const list = el('div', { class: 'story-list' },
      _state.items.map(renderRow));
    mount.appendChild(list);

    if (_state.fetchedAt) {
      mount.appendChild(el('div', { class: 'story-fetched-at' }, [
        'fetched ' + fmtTime(_state.fetchedAt),
      ]));
    }
  }

  // Public manual-refresh hook so operators can trigger from console.
  window.lvStoryReviewRefresh = fetchCandidates;

  // Auto-load when the Bug Panel becomes visible. Cheap polling-free
  // approach: fire on first DOMContentLoaded + when the bug panel is
  // opened (best-effort hook on .bug-panel toggle if present).
  function tryInitialFetch() {
    if (document.getElementById(MOUNT_ID)) {
      fetchCandidates();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', tryInitialFetch);
  } else {
    tryInitialFetch();
  }

  // Refresh when the window regains focus (cheap freshness signal).
  window.addEventListener('focus', function () {
    if (_state.enabled !== false) fetchCandidates();
  });
})();
