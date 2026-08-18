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
// PHASE 3 (2026-08-17), WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01:
// this section is UPGRADED IN PLACE rather than replaced by a second
// queue. It now defaults to the CURRENT narrator, filters by review
// status with counts, opens the full preserved transcript, edits
// placement and private notes, and applies Promote / Memoir only /
// Needs review / Discard through the atomic review route.
//
// Every mutation carries the `review_version` it observed. A stale
// version comes back 409 and the operator's typed edit is KEPT on
// screen with the conflict shown beside it -- losing somebody's work
// to a race is worse than refusing the save.
//
// NEVER narrator-visible — this surface lives in the Bug Panel only.
(function () {
  'use strict';

  const MOUNT_ID = 'lv10dBpStoryReview';
  // BUG-224 fix (2026-05-01): see bug-panel-dashboard.js comment.
  // Bare relative URL hits port 8082 (UI), not 8000 (API).
  const _O = (typeof ORIGIN !== 'undefined' && ORIGIN) || 'http://localhost:8000';
  const ENDPOINT = _O + '/api/operator/story-candidates';
  const REVIEW_ENDPOINT = _O + '/api/operator/story-candidates/review';
  const DEFAULT_LIMIT = 50;

  // Review status -> operator-facing label. The server owns the
  // vocabulary; this only decides how it reads on screen.
  const STATUS_LABELS = {
    unreviewed: 'Needs review',
    in_review: 'In review',
    promoted: 'Promoted',
    memoir_only: 'Memoir only',
    discarded: 'Discarded',
  };
  const STATUS_ORDER = ['unreviewed', 'in_review', 'promoted', 'memoir_only', 'discarded'];

  // The canonical taxonomy, read from the shared era registry rather than
  // restated here. Six historical eras plus the separate `today` bucket.
  // A free-text era field let an operator typo produce a story the server
  // considered PLACED and that appeared in no Life Map era.
  function _eraOptions() {
    try {
      var reg = window.LorevoxEras && window.LorevoxEras.LV_ERAS;
      if (Array.isArray(reg) && reg.length) {
        return reg.map(function (e) { return e.era_id; }).filter(Boolean);
      }
    } catch (e) { /* fall through */ }
    return ['earliest_years', 'early_school_years', 'adolescence',
            'coming_of_age', 'building_years', 'later_years', 'today'];
  }

  // NARRATOR-SWITCH GUARD (added 2026-08-17 after review).
  //
  // fetchReview() and openDetail() captured a narrator and then applied
  // their responses without re-checking it, and the default scope stayed
  // on A after the shell switched to B. A delayed A response could
  // therefore paint A's stories into B's operator context -- and, worse, a
  // staged edit belonging to A could be addressed to B.
  //
  // Every read carries the generation it was issued under, and every
  // response is discarded unless BOTH the generation and the narrator
  // still match. Deliberately NOT person-scoped edit retention: this is a
  // low-frequency operator switch, so cancelling and clearing is the safe
  // answer and the simple one.
  let _gen = 0;
  function _bumpGen() { _gen += 1; return _gen; }

  let _state = {
    loading: false,
    enabled: null, // null = unknown until first probe
    items: [],
    count: 0,
    fetchedAt: null,
    narratorFilter: '',
    collapsed: true,   // historical backlog — collapsed by default
    error: null,
    // ── Phase 3 ──────────────────────────────────────────────────
    statusFilter: [],      // [] = every status
    counts: null,          // per-status totals from the server
    projection: null,      // canonical approved/provisional totals
    openId: null,          // candidate whose detail is expanded
    detail: null,          // full row incl. transcript
    detailBusy: false,
    // The operator's UNSAVED edits, keyed by candidate id. Deliberately
    // survives a 409: a conflict must not cost them what they typed.
    edits: {},
    conflict: null,        // {id, message, current}
    actionBusy: null,      // candidate id with a write in flight
  };

  function _currentPersonId() {
    try {
      return (typeof state !== 'undefined' && state && state.person_id)
        ? String(state.person_id) : '';
    } catch (_) { return ''; }
  }

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

  // ── Phase 3: the review lane ─────────────────────────────────────

  function _narrator() {
    return (_state.narratorFilter || '').trim() || _currentPersonId();
  }

  function fetchReview() {
    const pid = _narrator();
    const gen = _bumpGen();
    if (!pid) {                      // narrator-scoped by contract
      _state.items = []; _state.counts = null; _state.projection = null;
      _state.error = 'Choose a narrator to review their stories.';
      render(); return Promise.resolve();
    }
    _state.loading = true; _state.error = null; render();
    const stale = function () { return gen !== _gen || pid !== _narrator(); };
    let url = REVIEW_ENDPOINT + '?narrator_id=' + encodeURIComponent(pid) +
      '&limit=' + DEFAULT_LIMIT;
    if (_state.statusFilter.length) {
      url += '&status=' + encodeURIComponent(_state.statusFilter.join(','));
    }
    return fetch(url, { credentials: 'same-origin' })
      .then(function (resp) {
        if (resp.status === 404) { _state.enabled = false; return null; }
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        _state.enabled = true;
        return resp.json();
      })
      .then(function (body) {
        if (!body || stale()) return;
        _state.items = body.items || [];
        _state.count = body.count || 0;
        _state.counts = body.counts || null;
        _state.projection = body.projection || null;
        _state.fetchedAt = body.fetched_at || null;
      })
      .catch(function (err) {
        if (stale()) return;
        _state.enabled = true;
        _state.error = String(err && err.message || err);
      })
      .then(function () {
        if (stale()) return;
        _state.loading = false; render();
      });
  }

  function openDetail(id) {
    if (_state.openId === id) { _state.openId = null; _state.detail = null; render(); return; }
    const pid = _narrator();
    const gen = _bumpGen();
    const stale = function () { return gen !== _gen || pid !== _narrator(); };
    _state.openId = id; _state.detail = null; _state.detailBusy = true; render();
    fetch(ENDPOINT + '/' + encodeURIComponent(id) +
          '?narrator_id=' + encodeURIComponent(pid), { credentials: 'same-origin' })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (b) { if (stale()) return; _state.detail = b.item || null; })
      .catch(function (e) { if (stale()) return; _state.error = 'Detail failed: ' + e.message; })
      .then(function () {
        if (stale()) return;
        _state.detailBusy = false; render();
      });
  }

  /* Called by app.js on every narrator switch.
     Cancels in-flight reads by moving the generation, clears everything
     that belonged to the previous narrator, and re-scopes to the new one.

     STAGED EDITS ARE DISCARDED, deliberately. Keeping them would mean
     either carrying A's typed text into B's context, or building
     person-scoped retention for a low-frequency operator action. Losing an
     unsaved note on a deliberate narrator switch is a smaller harm than
     either, and it can never address A's edit to B. */
  function onNarratorSwitch(pid) {
    _bumpGen();
    _state.narratorFilter = String(pid || '');
    _state.openId = null;
    _state.detail = null;
    _state.detailBusy = false;
    _state.conflict = null;
    _state.edits = {};
    _state.actionBusy = null;
    _state.items = [];
    _state.counts = null;
    _state.projection = null;
    _state.error = null;
    if (_state.enabled !== false) fetchReview();
    else render();
  }

  function _edit(id) {
    if (!_state.edits[id]) _state.edits[id] = {};
    return _state.edits[id];
  }

  function applyReview(item, patch) {
    const pid = _narrator();
    const edit = _edit(item.id);
    const body = {
      narrator_id: pid,
      // The version the operator OBSERVED. Not re-read from anywhere:
      // re-reading it here would defeat the whole check.
      review_version: item.review_version,
    };
    if (edit.review_notes !== undefined) body.review_notes = edit.review_notes;
    if (edit.era_candidates !== undefined) {
      // One era or none. The selector cannot produce anything else, and
      // the server refuses an unknown value regardless.
      const one = String(edit.era_candidates || '').trim();
      body.era_candidates = one ? [one] : [];
    }
    if (edit.year_low !== undefined && String(edit.year_low).trim() !== '') {
      body.estimated_year_low = parseInt(edit.year_low, 10);
    }
    if (edit.year_high !== undefined && String(edit.year_high).trim() !== '') {
      body.estimated_year_high = parseInt(edit.year_high, 10);
    }
    if (edit.placement_source !== undefined) body.placement_source = edit.placement_source;
    Object.keys(patch || {}).forEach(function (k) { body[k] = patch[k]; });

    const gen = _gen;
    const stale = function () { return gen !== _gen || pid !== _narrator(); };
    _state.actionBusy = item.id; _state.conflict = null; render();
    return fetch(ENDPOINT + '/' + encodeURIComponent(item.id), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(body),
    })
      .then(function (r) {
        return r.json().catch(function () { return null; }).then(function (b) {
          return { status: r.status, body: b };
        });
      })
      .then(function (res) {
        // A switch landed while this write was in flight. The write itself
        // was narrator-scoped on the wire and cannot have hit the wrong
        // person; what must not happen is repainting B with A's outcome.
        if (stale()) return;
        if (res.status === 409) {
          // THE EDIT IS KEPT. _state.edits is untouched on purpose, so
          // the operator can re-apply against the fresh version rather
          // than retype what they wrote.
          const d = (res.body && res.body.detail) || {};
          _state.conflict = {
            id: item.id,
            message: d.message || 'Someone else reviewed this story first.',
            current: d.current || null,
          };
          return;
        }
        if (res.status !== 200) {
          _state.error = 'Review failed: HTTP ' + res.status;
          return;
        }
        // Applied: drop only THIS candidate's staged edit.
        delete _state.edits[item.id];
        _state.conflict = null;
        _state.detail = null;
        _state.openId = null;
        return afterReviewApplied(pid);
      })
      .catch(function (e) {
        if (stale()) return;
        _state.error = 'Review failed: ' + e.message;
      })
      .then(function () {
        if (stale()) return;
        _state.actionBusy = null; render();
      });
  }

  /* After a successful review: reload the candidate list, refresh the
     canonical chronology, and repaint the CURRENT narrator only.

     It issues no Lori prompt and no projection PUT/PATCH -- a reviewer
     approving a story must not make Lori say anything -- and it refuses
     to touch a narrator the shell has since switched away from. */
  function afterReviewApplied(pid) {
    return fetchReview().then(function () {
      if (pid !== _narrator()) return;          // switched away mid-flight
      if (typeof window.lvRefreshNarratorChronology === 'function') {
        return window.lvRefreshNarratorChronology(pid, 'story_reviewed');
      }
    });
  }

  function renderStatusFilters() {
    const chips = [el('span', { class: 'story-meta' }, ['Status:'])];
    STATUS_ORDER.forEach(function (st) {
      const on = _state.statusFilter.indexOf(st) >= 0;
      const n = (_state.counts && _state.counts[st] != null) ? _state.counts[st] : null;
      chips.push(el('button', {
        class: 'story-chip' + (on ? ' story-chip-on' : ''),
        onclick: function () {
          const i = _state.statusFilter.indexOf(st);
          if (i >= 0) _state.statusFilter.splice(i, 1);
          else _state.statusFilter.push(st);
          fetchReview();
        },
      }, [STATUS_LABELS[st] + (n != null ? ' (' + n + ')' : '')]));
    });
    if (_state.projection && _state.projection.counts) {
      const c = _state.projection.counts;
      chips.push(el('span', { class: 'story-meta' }, [
        '· canonical: ' + c.approved + ' approved, ' + c.provisional +
        ' provisional, ' + c.unplaced + ' unplaced',
      ]));
    }
    return el('div', { class: 'story-chiprow' }, chips);
  }

  function renderActions(item) {
    const busy = _state.actionBusy === item.id;
    function act(label, status, cls) {
      return el('button', {
        class: 'story-act' + (cls ? ' ' + cls : ''),
        disabled: busy ? 'disabled' : undefined,
        onclick: function () { applyReview(item, { review_status: status }); },
      }, [label]);
    }
    return el('div', { class: 'story-actions' }, [
      act('Promote', 'promoted', 'story-act-promote'),
      act('Memoir only', 'memoir_only'),
      act('Needs review', 'unreviewed'),
      act('Discard', 'discarded', 'story-act-discard'),
      el('button', {
        class: 'story-act',
        disabled: busy ? 'disabled' : undefined,
        onclick: function () { applyReview(item, {}); },
      }, ['Save placement / notes']),
      // A story wrongly filed in an era is worse than one that is
      // unplaced, so taking a placement back OFF has to be possible --
      // not merely replaceable. This clears era, year range and returns
      // placement_source to `unknown` in one atomic action.
      el('button', {
        class: 'story-act',
        disabled: busy ? 'disabled' : undefined,
        onclick: function () {
          delete _edit(item.id).era_candidates;
          delete _edit(item.id).year_low;
          delete _edit(item.id).year_high;
          delete _edit(item.id).placement_source;
          applyReview(item, { clear_placement: true });
        },
      }, ['Clear placement']),
    ]);
  }

  function renderEditor(item) {
    const edit = _edit(item.id);
    function field(label, key, value, placeholder) {
      return el('label', { class: 'story-field' }, [
        el('span', { class: 'story-meta' }, [label]),
        el('input', {
          class: 'story-input',
          type: 'text',
          value: edit[key] !== undefined ? edit[key] : (value == null ? '' : String(value)),
          placeholder: placeholder || '',
          oninput: function (e) { edit[key] = e.target.value; },
        }),
      ]);
    }
    const sourceSel = el('select', {
      class: 'story-input',
      oninput: function (e) { edit.placement_source = e.target.value; },
    }, ['unknown', 'narrator_stated', 'operator_set', 'dob_derived'].map(function (v) {
      const cur = edit.placement_source !== undefined
        ? edit.placement_source : (item.placement_source || 'unknown');
      return el('option', { value: v, selected: v === cur ? 'selected' : undefined }, [v]);
    }));
    // CANONICAL ERA SELECTOR, not a free-text field (2026-08-17 fix).
    // The comma-separated input let a typo produce a story the server
    // considered PLACED and that appeared in no Life Map era. The server
    // now refuses an unknown era; this makes one impossible to type.
    //
    // ONE era, because an operator-set placement must resolve to exactly
    // one -- two is a pair of guesses, and the Life Map would have to pick.
    const curEra = edit.era_candidates !== undefined
      ? edit.era_candidates
      : ((item.era_candidates || [])[0] || '');
    const eraSel = el('select', {
      class: 'story-input',
      oninput: function (e) { edit.era_candidates = e.target.value; },
    }, [el('option', { value: '', selected: curEra ? undefined : 'selected' },
           ['— not placed —'])].concat(_eraOptions().map(function (v) {
      return el('option', {
        value: v, selected: v === curEra ? 'selected' : undefined,
      }, [v]);
    })));

    return el('div', { class: 'story-editor' }, [
      el('label', { class: 'story-field' }, [
        el('span', { class: 'story-meta' }, ['Life era']), eraSel,
      ]),
      field('Year from', 'year_low', item.estimated_year_low, 'e.g. 1962'),
      field('Year to', 'year_high', item.estimated_year_high, 'e.g. 1964'),
      el('label', { class: 'story-field' }, [
        el('span', { class: 'story-meta' }, ['Placement source']), sourceSel,
      ]),
      field('Private review notes', 'review_notes', item.review_notes,
            'operator-only; never narrator-visible'),
    ]);
  }

  function renderConflict(item) {
    if (!_state.conflict || _state.conflict.id !== item.id) return null;
    const cur = _state.conflict.current || {};
    return el('div', { class: 'story-conflict' }, [
      el('div', {}, ['⚠ ' + _state.conflict.message]),
      el('div', { class: 'story-meta' }, [
        'It is now: ' + (STATUS_LABELS[cur.review_status] || cur.review_status || '?') +
        ' (version ' + (cur.review_version != null ? cur.review_version : '?') + ').',
      ]),
      el('div', { class: 'story-meta' }, [
        'Your edits are still here. Refresh to see the current version, ' +
        'then apply again.',
      ]),
    ]);
  }

  function renderDetail(item) {
    if (_state.openId !== item.id) return null;
    if (_state.detailBusy) return el('div', { class: 'story-detail' }, ['Loading…']);
    const d = _state.detail;
    if (!d) return null;
    const bits = [
      el('div', { class: 'story-transcript' }, [d.transcript || '(empty)']),
    ];
    if (d.audio_present) {
      // Presence, never the path -- the archive layout is not the
      // browser's business.
      bits.push(el('div', { class: 'story-meta' }, [
        'audio captured' + (d.audio_duration_sec ? ' (' + d.audio_duration_sec + 's)' : ''),
      ]));
    }
    bits.push(renderEditor(d));
    bits.push(renderActions(d));
    const conflict = renderConflict(d);
    if (conflict) bits.push(conflict);
    return el('div', { class: 'story-detail' }, bits);
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

    meta.push(el('span', { class: 'story-status story-status-' + (item.review_status || 'unreviewed') }, [
      STATUS_LABELS[item.review_status] || item.review_status || '?',
    ]));
    if (item.placement_source && item.placement_source !== 'unknown') {
      meta.push(el('span', { class: 'story-meta' }, ['placed=' + item.placement_source]));
    }

    const kids = [
      headerLine,
      el('div', { class: 'story-meta-line' }, meta),
      el('button', {
        class: 'story-preview story-preview-btn',
        onclick: function () { openDetail(item.id); },
      }, [previewText || '(empty transcript)']),
    ];
    const detail = renderDetail(item);
    if (detail) kids.push(detail);
    return el('div', { class: 'story-row' }, kids);
  }

  function renderControls() {
    const refreshBtn = el('button', {
      class: 'story-refresh-btn',
      onclick: function () { fetchReview(); },
    }, ['Refresh']);

    const filterInput = el('input', {
      class: 'story-filter-input',
      type: 'text',
      placeholder: 'narrator_id (optional)',
      value: _state.narratorFilter || '',
      oninput: function (e) { _state.narratorFilter = e.target.value; },
      onkeydown: function (e) {
        if (e.key === 'Enter') { e.preventDefault(); fetchReview(); }
      },
    });

    return el('div', { class: 'story-controls' }, [
      filterInput, refreshBtn, renderStatusFilters(),
    ]);
  }

  const _SECTION_TITLE = 'Historical unreviewed story candidates \u2014 not live Lori context';

  function renderHeader() {
    let countText;
    if (_state.loading) countText = 'Loading\u2026';
    else if (_state.error) countText = 'Error';
    else countText = _state.count + ' unreviewed';

    return el('div', {
      class: 'story-section-header',
      onclick: function () { _state.collapsed = !_state.collapsed; render(); },
      title: 'Operator backlog from past sessions \u2014 NOT what Lori saw or '
        + 'said live today. Click to ' + (_state.collapsed ? 'expand' : 'collapse') + '.',
    }, [
      el('span', { class: 'story-section-caret' }, [_state.collapsed ? '\u25b8' : '\u25be']),
      el('span', { class: 'story-section-title' }, [_SECTION_TITLE]),
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
        el('span', { class: 'story-section-title' }, [_SECTION_TITLE]),
        el('span', { class: 'story-section-count' }, ['feature disabled']),
      ]));
      mount.appendChild(el('div', { class: 'story-empty' }, [
        'Set HORNELORE_OPERATOR_STORY_REVIEW=1 in .env and restart to enable.',
      ]));
      return;
    }

    mount.appendChild(renderHeader());

    // Collapsed by default — this is a historical operator backlog, not the
    // live Lori-chat capture surface (that is Travel Doc \u2192 Story notes).
    if (_state.collapsed) {
      mount.appendChild(el('div', { class: 'story-empty' }, [
        'These are historical operator candidates. Lori did not '
        + 'necessarily see or say these today. Click the header to expand.',
      ]));
      return;
    }

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
  window.lvStoryReviewRefresh = fetchReview;
  window.lvStoryReviewOnNarratorSwitch = onNarratorSwitch;

  // Auto-load when the Bug Panel becomes visible. Cheap polling-free
  // approach: fire on first DOMContentLoaded + when the bug panel is
  // opened (best-effort hook on .bug-panel toggle if present).
  function tryInitialFetch() {
    if (document.getElementById(MOUNT_ID)) {
      // Default the filter to the ACTIVE narrator so old test-narrator
      // candidates don't show by default. Operator can clear it to see all.
      // Phase 3: current-narrator by default. The review lane is
      // narrator-scoped by contract, so an unscoped default would be a
      // cross-narrator read.
      if (!_state.narratorFilter) _state.narratorFilter = _currentPersonId();
      fetchReview();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', tryInitialFetch);
  } else {
    tryInitialFetch();
  }

  // Refresh when the window regains focus (cheap freshness signal).
  window.addEventListener('focus', function () {
    if (_state.enabled !== false) fetchReview();
  });
})();
