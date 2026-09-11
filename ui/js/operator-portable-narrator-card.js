// WO-LOREVOX-PORTABLE-NARRATOR-01 Phase 5a — Narrator Data Center entry (§16, §16.1, §35).
//
// The operator's one window into what Lorevox currently holds for the selected
// narrator, and the place a narrator moves between installations. Three plain
// views: View & Download (the Complete Data Check — what Lorevox recognises,
// from the same ownership declaration the exporter uses), Move or Restore (one
// complete, non-selective package; and Import), Activity (the durable export and
// restore ledgers). THIS CARD COMPUTES NOTHING: every count, stage, step and
// verdict arrives decided by the server and is rendered.
//
// TWO VERDICTS, NEVER ONE. Package integrity and Lorevox restore readiness are
// two server objects and two boxes. NO "RESTORE ANYWAY": the Restore control
// exists only while readiness is READY, and the confirmation dialog names the
// narrator and the consequences before anything runs.
//
// NOTHING HERE DELETES NARRATOR DATA. The only removal controls are "Discard
// upload" (a staged file that was never narrator state) and "Remove server copy"
// (the finished .lorevox.zip artifact outside DATA_DIR; the job record stays and
// says the copy was removed). Creating, downloading or removing a package never
// removes the narrator.
//
// Rich per-domain inspection (audio browser, live memoir, questionnaire
// completeness, cross-surface counts, drag/drop) is Phase 5b, after the clean
// cutover — deliberately not here. NEVER NARRATOR-VISIBLE. Operator tab only.
(function () {
  'use strict';

  var MOUNT_ID = 'lvOperatorPortableNarrator';
  var _O = (typeof ORIGIN !== 'undefined' && ORIGIN) || 'http://localhost:8000';
  var BASE = _O + '/api/operator/narrator-package';
  var POLL_MS = 1500;

  var _state = {
    enabled: null,        // null = not probed; false = 404 (feature off)
    error: null,
    view: 'view',         // 'view' | 'move' | 'activity'
    preflight: null,      // GET /preflight/{pid}
    preflightFor: null,
    exportJob: null,      // GET /export/jobs/{id}
    exportBusy: false,
    exportJobs: null,     // GET /export/jobs
    upload: null,         // POST /import/upload → GET /import/{id}
    uploadBusy: false,
    restoreJobs: null,    // GET /restore/jobs
    recoverBusy: false,
    lastRecover: null,
    status: '',           // polite live-region text: transitions only
  };

  // ── narrator-switch clamp ─────────────────────────────────────────
  var _switchGen = 0;
  function currentPersonId() {
    try { return (typeof state !== 'undefined' && state && state.person_id) ? String(state.person_id) : ''; }
    catch (_) { return ''; }
  }
  function _ctx() { return { gen: _switchGen, pid: currentPersonId() }; }
  function _stale(ctx) { return !ctx || ctx.gen !== _switchGen || ctx.pid !== currentPersonId(); }

  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
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

  function announce(text) { _state.status = text; }

  // ── transport ──────────────────────────────────────────────────────
  function request(path, options) {
    _state.error = null;
    return fetch(BASE + path, options || { credentials: 'same-origin' })
      .then(function (r) {
        if (r.status === 404 && path.indexOf('/export/jobs/') !== 0 && path.indexOf('/import/') !== 0) {
          _state.enabled = false;
          return null;
        }
        return r.json().catch(function () { return null; })
          .then(function (b) { return { status: r.status, body: b }; });
      })
      .then(function (res) {
        if (!res) return null;
        if (res.status >= 400) {
          var d = res.body && res.body.detail;
          _state.error = (d && (d.message || d.code)) ? (d.message || d.code) :
            (typeof d === 'string' ? d : 'HTTP ' + res.status);
          return { error: true, status: res.status, detail: d };
        }
        _state.enabled = true;
        return res.body;
      })
      .catch(function (e) {
        _state.enabled = true;
        _state.error = String((e && e.message) || e);
        return null;
      });
  }

  // ── export ─────────────────────────────────────────────────────────
  function refreshPreflight() {
    var ctx = _ctx();
    if (!ctx.pid) { _state.preflight = null; _state.preflightFor = null; render(); return Promise.resolve(); }
    return request('/preflight/' + encodeURIComponent(ctx.pid)).then(function (body) {
      if (_stale(ctx)) return;
      if (body && !body.error) { _state.preflight = body; _state.preflightFor = ctx.pid; }
      else { _state.preflight = null; _state.preflightFor = ctx.pid; }
      render();
    });
  }

  function startExport() {
    var ctx = _ctx();
    if (!ctx.pid || _state.exportBusy) return;
    _state.exportBusy = true; render();
    request('/export/' + encodeURIComponent(ctx.pid), { method: 'POST', credentials: 'same-origin' })
      .then(function (body) {
        if (!body || body.error) { _state.exportBusy = false; render(); return; }
        _state.exportJob = { job_id: body.job_id, state: body.state, progress: {} };
        announce('Creating the narrator package. You may leave this screen; the job continues.');
        render();
        pollExport(body.job_id);
      });
  }

  function pollExport(jobId) {
    request('/export/jobs/' + encodeURIComponent(jobId)).then(function (body) {
      if (!body || body.error) { _state.exportBusy = false; render(); return; }
      var prev = _state.exportJob && _state.exportJob.state;
      _state.exportJob = body;
      var done = body.state === 'complete' || body.state === 'failed' || body.state === 'refused';
      _state.exportBusy = !done;
      if (done && prev !== body.state) {
        announce(body.state === 'complete' ? 'Package ready and verified.' :
          body.state === 'refused' ? 'Package creation refused. Nothing was written.' : 'Package creation failed.');
        refreshExportJobs();
      }
      render();
      if (!done) setTimeout(function () { pollExport(jobId); }, POLL_MS);
    });
  }

  function downloadUrl(jobId) { return BASE + '/export/jobs/' + encodeURIComponent(jobId) + '/download'; }

  function removeServerCopy(jobId) {
    request('/export/jobs/' + encodeURIComponent(jobId) + '/remove-server-copy', { method: 'POST', credentials: 'same-origin' })
      .then(function (body) {
        if (body && !body.error) announce('Server copy removed. The narrator is untouched.');
        if (_state.exportJob && _state.exportJob.job_id === jobId) pollExport(jobId);
        refreshExportJobs();
      });
  }

  function refreshExportJobs() {
    return request('/export/jobs?limit=10').then(function (body) {
      if (body && !body.error) _state.exportJobs = body;
      render();
    });
  }

  // ── import ─────────────────────────────────────────────────────────
  function uploadPackage(file) {
    if (!file || _state.uploadBusy) return;
    _state.uploadBusy = true;
    _state.upload = { state: 'uploading', filename: file.name, bytes: file.size,
      stepper: { steps: stepsLocal(1), current: 2, total: 7 } };
    render();
    var fd = new FormData();
    fd.append('file', file, file.name);
    request('/import/upload', { method: 'POST', body: fd, credentials: 'same-origin' })
      .then(function (body) {
        _state.uploadBusy = false;
        if (!body || body.error) {
          _state.upload = body && body.error ? { state: 'upload_failed', filename: file.name, detail: body.detail,
            stepper: { steps: stepsLocal(1, true), current: 2, total: 7 } } : null;
          announce('Upload refused.');
          render(); return;
        }
        _state.upload = body;
        announce(body.integrity && body.integrity.ok
          ? (body.readiness && body.readiness.ready ? 'Package verified. Ready to restore.' : 'Package verified, but this installation cannot restore it.')
          : 'Package integrity failed.');
        render();
      });
  }

  // Local stepper ONLY for the two moments before the server has answered
  // (uploading / upload refused); every later step comes from the server.
  function stepsLocal(cur, failed) {
    var names = ['Choose package', 'Upload', 'Check package', 'Check restore readiness', 'Review', 'Restore', 'Verify'];
    return names.map(function (n, i) {
      return { n: i + 1, name: n, state: i < cur ? 'complete' : (i === cur ? (failed ? 'failed' : 'current') : 'pending') };
    });
  }

  function confirmRestore(u) {
    var name = u.narrator_display_name || u.narrator_id || 'this narrator';
    var text = 'This will add ' + name + "'s narrator records and files to this Lorevox installation.\n\n" +
      'Existing records will not be overwritten. A collision will stop the restore. Nothing is deleted.';
    var dlg = typeof document.createElement === 'function' ? document.createElement('dialog') : null;
    if (!dlg || typeof dlg.showModal !== 'function') {
      return Promise.resolve(typeof window.confirm === 'function' ? window.confirm('Restore ' + name + '?\n\n' + text) : false);
    }
    return new Promise(function (resolve) {
      dlg.className = 'opnc-dialog';
      var cancel = el('button', { class: 'opnc-btn', type: 'button', autofocus: 'autofocus' }, ['Cancel']);
      var go = el('button', { class: 'opnc-btn primary', type: 'button' }, ['Restore ' + name]);
      cancel.addEventListener('click', function () { dlg.close(); resolve(false); });
      go.addEventListener('click', function () { dlg.close(); resolve(true); });
      dlg.addEventListener('cancel', function () { resolve(false); });
      dlg.appendChild(el('h3', null, ['Restore ' + name + '?']));
      text.split('\n').forEach(function (line) { if (line) dlg.appendChild(el('p', null, [line])); });
      dlg.appendChild(el('div', { class: 'opnc-row' }, [cancel, go]));
      document.body.appendChild(dlg);
      dlg.addEventListener('close', function () { try { document.body.removeChild(dlg); } catch (_) {} });
      dlg.showModal();
      try { cancel.focus(); } catch (_) {}
    });
  }

  function startRestore() {
    var u = _state.upload;
    if (!u || !u.readiness || !u.readiness.ready || _state.uploadBusy) return;
    confirmRestore(u).then(function (yes) {
      if (!yes) return;
      _state.uploadBusy = true; render();
      request('/import/' + encodeURIComponent(u.upload_id) + '/restore', { method: 'POST', credentials: 'same-origin' })
        .then(function (body) {
          if (!body || body.error) {
            _state.uploadBusy = false;
            if (body && body.detail && body.detail.readiness) _state.upload.readiness = body.detail.readiness;
            announce('Restore refused. Nothing was changed.');
            render(); return;
          }
          _state.upload.state = 'restoring';
          announce('Restoring. Files first, then the records in one transaction.');
          render();
          pollUpload(u.upload_id);
        });
    });
  }

  function pollUpload(uploadId) {
    request('/import/' + encodeURIComponent(uploadId)).then(function (body) {
      if (!body || body.error) { _state.uploadBusy = false; render(); return; }
      _state.upload = body;
      var done = body.state !== 'restoring';
      _state.uploadBusy = !done;
      render();
      if (!done) setTimeout(function () { pollUpload(uploadId); }, POLL_MS);
      else {
        announce(body.state === 'restored' ? 'Restore complete. The narrator is available.' :
          body.state === 'refused' ? 'Restore refused. Nothing was changed.' : 'Restore failed; see the job record.');
        try { if (body.state === 'restored' && typeof refreshPeople === 'function') refreshPeople(); } catch (_) {}
        refreshRestoreJobs();
      }
    });
  }

  function discardUpload() {
    var u = _state.upload;
    if (!u || !u.upload_id || _state.uploadBusy) return;
    request('/import/' + encodeURIComponent(u.upload_id) + '/discard', { method: 'POST', credentials: 'same-origin' })
      .then(function () { _state.upload = null; render(); });
  }

  // ── restore jobs / recovery ────────────────────────────────────────
  function refreshRestoreJobs() {
    return request('/restore/jobs?limit=10').then(function (body) {
      if (body && !body.error) _state.restoreJobs = body;
      render();
    });
  }

  function runRecover() {
    if (_state.recoverBusy) return;
    _state.recoverBusy = true; render();
    request('/recover', { method: 'POST', credentials: 'same-origin' }).then(function (body) {
      _state.recoverBusy = false;
      if (body && !body.error) { _state.lastRecover = body; announce('Recovery finished; see the report.'); }
      refreshRestoreJobs();
    });
  }

  // ── render helpers ─────────────────────────────────────────────────
  function stat(label, value) {
    return el('span', { class: 'opnc-stat' }, [label + ' ', el('b', null, [String(value)])]);
  }
  function summaryRow(s) {
    if (!s) return null;
    return el('div', { class: 'opnc-row' }, [
      stat('conversations', s.conversations), stat('turns', s.turns), stat('photos', s.photos),
      stat('documents', s.documents), stat('trips', s.trips), stat('stories', s.stories),
      stat('records', s.records), stat('files', s.files), stat('size', s.size_human || (s.bytes + ' B')),
    ]);
  }
  function advanced(obj, label) {
    if (!obj) return null;
    return el('details', { class: 'opnc-advanced' }, [
      el('summary', null, [label || 'Advanced inventory']),
      el('pre', { class: 'opnc-pre' }, [JSON.stringify(obj, null, 2)]),
    ]);
  }
  function reasons(list, cls) {
    return (list || []).map(function (r) {
      var txt = typeof r === 'string' ? r : (r.code || r.kind || 'reason') +
        (r.table ? ' · ' + r.table : '') + (r.path ? ' · ' + r.path : '') +
        (r.detail ? ' — ' + r.detail : '') + (r.message ? ' — ' + r.message : '');
      return el('div', { class: cls || 'opnc-reason' }, [txt]);
    });
  }
  function mark(st) { return st === 'complete' ? '✓' : st === 'current' ? '●' : st === 'failed' ? '✕' : '○'; }

  function stageList(progress) {
    var p = progress || {};
    var list = el('ol', { class: 'opnc-stages', 'aria-busy': p.stage && p.stage !== 'complete' ? 'true' : null });
    var labels = { snapshot: 'Database snapshot', records: 'Collecting records', files: 'Collecting files',
      bag: 'Building archive', verify: 'Verifying archive', zip: 'Writing package' };
    (p.stages || []).forEach(function (s) {
      var t = mark(s.state) + ' ' + (labels[s.name] || s.name);
      if (s.name === 'files' && s.state === 'current' && p.total) t += ' — ' + p.done + ' of ' + p.total;
      list.appendChild(el('li', { class: 'opnc-stage ' + s.state }, [t]));
    });
    if (p.stage === 'files' && p.total) {
      var bar = el('progress', { max: String(p.total), value: String(p.done || 0), 'aria-label': 'files collected' });
      list.appendChild(el('li', { class: 'opnc-stage bar' }, [bar]));
    }
    return list;
  }

  function stepper(sp) {
    if (!sp || !sp.steps) return null;
    var list = el('ol', { class: 'opnc-steps' });
    sp.steps.forEach(function (s) {
      list.appendChild(el('li', { class: 'opnc-step ' + s.state }, [mark(s.state) + ' ' + s.n + '. ' + s.name]));
    });
    return list;
  }

  // ── views ──────────────────────────────────────────────────────────
  function renderHeader(mount, st) {
    var pid = currentPersonId();
    var p = st.preflight && st.preflightFor === pid ? st.preflight : null;
    mount.appendChild(el('div', { class: 'opnc-head' }, [
      el('div', { class: 'opnc-title' }, ['Narrator Data Center']),
      el('div', { class: 'opnc-sub' }, [p ? (p.narrator_display_name || pid) + ' — everything Lorevox currently holds for this narrator.'
        : (pid ? 'Loading what Lorevox holds for this narrator…' : 'Choose a narrator to see what Lorevox holds. Import is available without one.')]),
      p ? summaryRow(p.summary) : null,
      el('div', { class: 'opnc-sub' }, ['Creating or downloading a package does not remove this narrator.']),
    ]));
    var nav = el('div', { class: 'opnc-nav', role: 'tablist' });
    [['view', 'View & Download'], ['move', 'Move or Restore'], ['activity', 'Activity']].forEach(function (v) {
      nav.appendChild(el('button', {
        class: 'opnc-btn opnc-tab' + (st.view === v[0] ? ' active' : ''), role: 'tab',
        'aria-selected': st.view === v[0] ? 'true' : 'false',
        onclick: function () { _state.view = v[0]; if (v[0] === 'activity') { refreshExportJobs(); refreshRestoreJobs(); } render(); },
      }, [v[1]]));
    });
    mount.appendChild(nav);
    mount.appendChild(el('div', { class: 'opnc-status', role: 'status', 'aria-live': 'polite' }, [st.status || '']));
  }

  function renderView(mount, st) {
    var pid = currentPersonId();
    var block = el('div', { class: 'opnc-block' });
    block.appendChild(el('div', { class: 'opnc-title' }, ['Complete Data Check']));
    if (!pid) { block.appendChild(el('div', { class: 'opnc-sub' }, ['Choose a narrator.'])); mount.appendChild(block); return; }
    var p = st.preflight && st.preflightFor === pid ? st.preflight : null;
    if (!p) { block.appendChild(el('div', { class: 'opnc-sub' }, ['Not available for this narrator.'])); mount.appendChild(block); return; }
    block.appendChild(el('div', { class: 'opnc-sub' }, [
      'What Lorevox recognises as this narrator\'s, from the same ownership declaration the package is built from. ' +
      'If a screen elsewhere shows a different count, this is the number to check it against.']));
    block.appendChild(el('div', { class: 'opnc-row' }, [
      stat('authoritative records', p.summary.records), stat('narrator-owned files', p.summary.files), stat('size', p.summary.size_human),
      stat('Complete package coverage', 'Complete ✓'),
    ]));
    block.appendChild(el('div', { class: 'opnc-sub' }, [
      'Photos and their thumbnails are preserved files and travel in the package. Saved narrator audio travels; Lori\'s audio is not stored.']));
    if (p.lanes_absent_in_source && p.lanes_absent_in_source.length) {
      block.appendChild(el('div', { class: 'opnc-warn' }, ['Lanes absent in this installation\'s schema: ' + p.lanes_absent_in_source.length]));
    }
    block.appendChild(el('div', { class: 'opnc-sub' }, ['Per-domain browsing (recordings, current memoir, questionnaire completeness) arrives after the clean cutover — Phase 5b.']));
    block.appendChild(advanced({ record_counts_by_lane: p.record_counts_by_lane, files_by_lane: p.files_by_lane,
      lanes_absent_in_source: p.lanes_absent_in_source, out_dir: p.out_dir }));
    block.appendChild(el('div', { class: 'opnc-row' }, [el('button', { class: 'opnc-btn', onclick: refreshPreflight }, ['Refresh'])]));
    mount.appendChild(block);
  }

  function renderMove(mount, st) {
    var pid = currentPersonId();
    var p = st.preflight && st.preflightFor === pid ? st.preflight : null;
    // ── move this narrator to another Lorevox ──
    var out = el('div', { class: 'opnc-block' });
    out.appendChild(el('div', { class: 'opnc-title' }, ['Move this narrator to another Lorevox']));
    if (!pid) {
      out.appendChild(el('div', { class: 'opnc-sub' }, ['Choose a narrator to create a package.']));
    } else if (!p) {
      out.appendChild(el('div', { class: 'opnc-sub' }, ['Preflight not available for this narrator.']));
    } else {
      out.appendChild(el('div', { class: 'opnc-sub' }, ['Complete Narrator Package — everything below travels together; there is nothing to untick.']));
      var domains = ['Conversations & transcripts', 'Saved narrator voice', 'Photos and metadata', 'Biography & questionnaire',
        'Life Map & timeline', 'Current memoir / story state', 'Trips and travel evidence', 'Documents',
        'Relationships', 'Structured memory', 'Provenance / review state'];
      var ul = el('ul', { class: 'opnc-domains' });
      domains.forEach(function (d) { ul.appendChild(el('li', null, ['✓ ' + d])); });
      out.appendChild(ul);
      out.appendChild(summaryRow(p.summary));
      out.appendChild(el('div', { class: 'opnc-row' }, [
        el('button', { class: 'opnc-btn primary', disabled: st.exportBusy ? 'disabled' : null, onclick: startExport },
          [st.exportBusy ? 'Creating package…' : 'Create Complete Narrator Package']),
      ]));
    }
    var j = st.exportJob;
    if (j) {
      var cls = j.state === 'complete' ? 'ok' : (j.state === 'failed' || j.state === 'refused') ? 'bad' : 'pending';
      var v = el('div', { class: 'opnc-verdict ' + cls });
      if (j.state === 'complete') {
        v.appendChild(el('div', { class: 'opnc-verdict-title' }, ['✓ Package ready · ' + (j.package_filename || '')]));
        v.appendChild(summaryRow(j.summary));
        v.appendChild(el('div', { class: 'opnc-row' }, [
          stat('Integrity', 'Verified'), stat('Warnings', j.summary ? j.summary.warnings : 0),
          stat('Not packaged (shared / residue)', j.summary ? j.summary.residue_not_packaged : 0),
        ]));
        if (j.download_available) {
          v.appendChild(el('div', { class: 'opnc-row' }, [
            el('a', { class: 'opnc-btn primary', href: downloadUrl(j.job_id), download: j.package_filename || 'package.lorevox.zip' }, ['Download package']),
            el('button', { class: 'opnc-btn', onclick: function () { removeServerCopy(j.job_id); } }, ['Remove server copy']),
          ]));
        } else {
          v.appendChild(el('div', { class: 'opnc-sub' }, ['Server copy removed ' + (j.package_removed_at || '') + '.']));
        }
        v.appendChild(el('div', { class: 'opnc-sub' }, ['Retention: ' + (j.retention ? j.retention.policy : '') + '. ' + (j.retention ? j.retention.note : '')]));
        v.appendChild(advanced(j.advanced, 'Advanced details'));
      } else if (j.state === 'refused') {
        v.appendChild(el('div', { class: 'opnc-verdict-title' }, ['✕ Package creation refused — nothing was written']));
        reasons(j.refusal).forEach(function (n) { v.appendChild(n); });
      } else if (j.state === 'failed') {
        v.appendChild(el('div', { class: 'opnc-verdict-title' }, ['✕ Package creation failed']));
        v.appendChild(el('div', { class: 'opnc-reason' }, [j.error || '']));
      } else {
        v.appendChild(el('div', { class: 'opnc-verdict-title' }, ['● Creating package…']));
        v.appendChild(stageList(j.progress));
        v.appendChild(el('div', { class: 'opnc-sub' }, ['You may leave this screen. The job will continue.']));
      }
      out.appendChild(v);
    }
    mount.appendChild(out);

    // ── bring a narrator into this Lorevox ──
    var inb = el('div', { class: 'opnc-block' });
    inb.appendChild(el('div', { class: 'opnc-title' }, ['Bring a narrator into this Lorevox']));
    inb.appendChild(el('div', { class: 'opnc-sub' }, ['Accepted file: .lorevox.zip. Package integrity and restore readiness are checked separately; a refusal is final.']));
    var input = el('input', {
      type: 'file', id: 'opncPackageFile', accept: '.zip,application/zip', disabled: st.uploadBusy ? 'disabled' : null,
      onchange: function (ev) { var f = ev && ev.target && ev.target.files && ev.target.files[0]; if (f) uploadPackage(f); },
    });
    inb.appendChild(el('div', { class: 'opnc-row' }, [el('label', { for: 'opncPackageFile', class: 'opnc-btn' }, ['Choose Lorevox Package']), input]));
    var u = st.upload;
    if (u) {
      inb.appendChild(el('div', { class: 'opnc-sub' }, [(u.filename || 'package') + (u.bytes ? ' · ' + u.bytes + ' bytes' : '')]));
      inb.appendChild(stepper(u.stepper));
      if (u.state === 'uploading') { inb.appendChild(el('div', { class: 'opnc-verdict pending' }, ['● Uploading to staging…'])); mount.appendChild(inb); return; }
      if (u.state === 'upload_failed') {
        var uf = el('div', { class: 'opnc-verdict bad' }, [el('div', { class: 'opnc-verdict-title' }, ['✕ Upload refused'])]);
        reasons(u.detail ? [u.detail] : []).forEach(function (n) { uf.appendChild(n); });
        inb.appendChild(uf); mount.appendChild(inb); return;
      }
      var integ = u.integrity || {};
      var v1 = el('div', { class: 'opnc-verdict ' + (integ.ok ? 'ok' : 'bad') }, [
        el('div', { class: 'opnc-verdict-title' }, [(integ.ok ? '✓ ' : '✕ ') + 'Package integrity: ' + (integ.ok ? 'VERIFIED' : 'FAILED')]),
        el('div', { class: 'opnc-row' }, [
          stat('structure safe', integ.structure_safe ? 'yes' : 'no'), stat('BagIt valid', integ.bagit_valid ? 'yes' : 'no'),
          stat('manifest readable', integ.manifest_readable ? 'yes' : 'no'), stat('payload files', integ.payload_files || 0),
        ]),
      ]);
      reasons(integ.problems).forEach(function (n) { v1.appendChild(n); });
      inb.appendChild(v1);
      if (u.summary) {
        inb.appendChild(el('div', { class: 'opnc-sub' }, ['Narrator in package: ' + (u.narrator_display_name || u.narrator_id || '?')]));
        inb.appendChild(summaryRow(u.summary));
      }
      var r = u.readiness;
      if (integ.ok) {
        var v2 = el('div', { class: 'opnc-verdict ' + (r ? (r.ready ? 'ok' : 'bad') : 'pending') }, [
          el('div', { class: 'opnc-verdict-title' }, [(r ? (r.ready ? '✓ ' : '✕ ') : '● ') + 'Restore readiness: ' +
            (r ? (r.ready ? 'READY' : 'CANNOT RESTORE') : 'checking…')]),
        ]);
        if (r && !r.ready) v2.appendChild(el('div', { class: 'opnc-sub' }, ['Nothing has been changed.']));
        if (r) { reasons(r.reasons).forEach(function (n) { v2.appendChild(n); }); reasons(r.warnings, 'opnc-warn').forEach(function (n) { v2.appendChild(n); }); }
        inb.appendChild(v2);
      }
      if (u.state === 'restoring') {
        inb.appendChild(el('div', { class: 'opnc-verdict pending' }, ['● Restoring — files first, then the narrator\'s records in one transaction…']));
      } else if (u.state === 'restored') {
        var rr = u.restore_result || {};
        inb.appendChild(el('div', { class: 'opnc-verdict ok' }, [
          el('div', { class: 'opnc-verdict-title' }, ['✓ Restored — narrator available']),
          el('div', { class: 'opnc-row' }, [
            stat('records', Object.keys(rr.records_inserted || {}).reduce(function (a, k) { return a + rr.records_inserted[k]; }, 0)),
            stat('files', rr.files_created || 0), stat('job', (u.restore_job_id || '').slice(0, 8))]),
        ]));
      } else if (u.state === 'refused' || u.state === 'failed') {
        var rf = el('div', { class: 'opnc-verdict bad' }, [el('div', { class: 'opnc-verdict-title' }, [u.state === 'refused' ? '✕ Restore refused — nothing was changed' : '✕ Restore failed'])]);
        if (u.error) rf.appendChild(el('div', { class: 'opnc-reason' }, [u.error]));
        inb.appendChild(rf);
      }
      var row = el('div', { class: 'opnc-row' });
      if (u.state === 'checked' && integ.ok) {
        // the control EXISTS only while the SERVER says READY — there is no "restore anyway"
        if (r && r.ready) row.appendChild(el('button', { class: 'opnc-btn primary', disabled: st.uploadBusy ? 'disabled' : null, onclick: startRestore }, ['Restore this narrator…']));
        else row.appendChild(el('span', { class: 'opnc-sub' }, ['Restore is not offered: readiness refused.']));
      }
      if (u.state !== 'restoring' && u.state !== 'restored') row.appendChild(el('button', { class: 'opnc-btn', onclick: discardUpload }, ['Discard upload']));
      inb.appendChild(row);
      inb.appendChild(advanced(u.advanced, 'Advanced details'));
    }
    mount.appendChild(inb);
  }

  function renderActivity(mount, st) {
    var block = el('div', { class: 'opnc-block' });
    block.appendChild(el('div', { class: 'opnc-title' }, ['Activity']));
    block.appendChild(el('div', { class: 'opnc-sub' }, ['Durable records of package creation and restores on this installation.']));
    var ej = st.exportJobs;
    var list = el('div', { class: 'opnc-jobs' });
    if (ej && ej.jobs) {
      ej.jobs.forEach(function (j) {
        var line = el('div', { class: 'opnc-job' }, [
          (j.state === 'complete' ? '✓ ' : (j.state === 'refused' || j.state === 'failed') ? '✕ ' : '● ') +
          'Complete Narrator Package · ' + (j.narrator_display_name || j.narrator_id || '') + ' · ' + j.state +
          (j.summary ? ' · ' + j.summary.size_human : '') + ' · ' + (j.created_at || ''),
        ]);
        if (j.download_available) line.appendChild(el('a', { class: 'opnc-btn', href: downloadUrl(j.job_id), download: j.package_filename || '' }, ['Download']));
        else if (j.package_removed_at) line.appendChild(el('span', { class: 'opnc-sub' }, [' · server copy removed']));
        list.appendChild(line);
      });
    }
    var rj = st.restoreJobs;
    if (rj && rj.jobs) {
      rj.jobs.forEach(function (j) {
        list.appendChild(el('div', { class: 'opnc-job' }, [
          (j.state === 'complete' ? '✓ ' : j.state === 'failed' ? '✕ ' : '● ') + 'Restore · ' + (j.narrator_id || '').slice(0, 8) +
          ' · ' + j.state + ' · ' + (j.created_at || '') + (j.error ? ' · ' + j.error : '')]));
      });
    }
    if (!list.children || !list.children.length) list.appendChild(el('div', { class: 'opnc-sub' }, ['No activity yet.']));
    block.appendChild(list);
    if (rj && rj.incomplete > 0) {
      block.appendChild(el('div', { class: 'opnc-row' }, [
        el('button', { class: 'opnc-btn', disabled: st.recoverBusy ? 'disabled' : null, onclick: runRecover }, [st.recoverBusy ? 'Recovering…' : 'Recover incomplete restore jobs']),
        el('span', { class: 'opnc-sub' }, ['Finishes a committed restore or removes only what an unfinished one wrote; never deletes under a published narrator.']),
      ]));
    }
    if (st.lastRecover) block.appendChild(advanced(st.lastRecover, 'Recovery report'));
    mount.appendChild(block);
  }

  function renderInto(mount, st) {
    if (!mount) return;
    mount.innerHTML = '';
    if (st.enabled === false) {
      mount.appendChild(el('div', { class: 'opnc-off' }, ['Narrator Data Center is off. Set HORNELORE_OPERATOR_PORTABLE_NARRATOR=1 to enable.']));
      return;
    }
    if (st.enabled === null) { mount.appendChild(el('div', { class: 'opnc-off' }, ['Narrator Data Center — loading…'])); return; }
    if (st.error) mount.appendChild(el('div', { class: 'opnc-error' }, [String(st.error)]));
    renderHeader(mount, st);
    if (st.view === 'move') renderMove(mount, st);
    else if (st.view === 'activity') renderActivity(mount, st);
    else renderView(mount, st);
  }

  function render() { renderInto(document.getElementById(MOUNT_ID), _state); }

  // Exported so the card can be tested by RENDERING it against real server payloads.
  window.lvOperatorPortableNarratorRenderInto = renderInto;
  window.lvOperatorPortableNarratorState = function () { return _state; };
  window.lvOperatorPortableNarratorRefresh = function () { return refreshPreflight().then(refreshRestoreJobs).then(refreshExportJobs); };
  window.lvOperatorPortableNarratorOnNarratorSwitch = function () {
    _switchGen += 1;
    _state.preflight = null; _state.preflightFor = null; _state.exportJob = null; _state.exportBusy = false;
    if (_state.enabled !== false) refreshPreflight(); else render();
  };

  function tryInitialFetch() {
    if (!document.getElementById(MOUNT_ID)) return;
    refreshRestoreJobs().then(refreshPreflight);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', tryInitialFetch);
  else tryInitialFetch();
})();
