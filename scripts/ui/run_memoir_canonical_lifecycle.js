/* Executed browser behaviour for the canonical memoir lifecycle.
 *
 * WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01 (2026-08-19).
 *
 * WHY THIS EXISTS RATHER THAN MORE SOURCE SCANS. The last review found
 * four defects that every source assertion had passed straight over,
 * because each was a property of the EXECUTION PATH rather than of the
 * text: the canonical load sat inside the branch that runs only when
 * `/api/facts/list` returns at least one fact (and the live database has
 * zero facts, so the one case the contract exists for was the case it
 * skipped); a review refreshed the list and the chronology but not the
 * memoir; the displayed evidence was harvested back out as operator
 * prose and then appended again; and an export could run before the
 * canonical read had finished or while the cache still belonged to the
 * previous narrator.
 *
 * None of those are visible in a grep. All of them are visible the
 * moment the functions actually run.
 *
 * No backend, no manual server, no arguments. Exits 0 / 1.
 *
 *   node scripts/ui/run_memoir_canonical_lifecycle.js
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const REPO = path.resolve(__dirname, '..', '..');
const SHELL = path.join(REPO, 'ui', 'hornelore1.0.html');

let pass = 0, fail = 0;
function ok(name, cond, detail) {
  if (cond) { pass++; console.log('  PASS  ' + name); }
  else { fail++; console.log('  FAIL  ' + name + (detail ? '  -- ' + detail : '')); }
}
function section(t) { console.log('\n' + t); }

/* Block and line comments out, string literals left alone. Enough for
   the one function this file scans, and it carries its own positive
   control below so a stripper that ate everything could not pass. */
function stripJsComments(src) {
  let out = '', i = 0, q = null;
  while (i < src.length) {
    const c = src[i], n = src[i + 1];
    if (q) {
      if (c === '\\') { out += c + (n || ''); i += 2; continue; }
      if (c === q) q = null;
      out += c; i++; continue;
    }
    if (c === '"' || c === "'" || c === '`') { q = c; out += c; i++; continue; }
    if (c === '/' && n === '*') { const e = src.indexOf('*/', i + 2); i = e < 0 ? src.length : e + 2; continue; }
    if (c === '/' && n === '/') { const e = src.indexOf('\n', i); i = e < 0 ? src.length : e; continue; }
    out += c; i++;
  }
  return out;
}
(function stripperIsNotVacuous() {
  const probe = 'const a = 1; /* await x */ // await y\nconst s = "/* await z */";';
  const got = stripJsComments(probe);
  ok('the comment stripper removes comments and keeps strings',
     got.indexOf('await x') < 0 && got.indexOf('await y') < 0 &&
     got.indexOf('await z') >= 0 && got.indexOf('const a = 1;') >= 0, got);
})();

/* ── Extract only the functions under test ───────────────────────────────
 * The shell's inline block is ~100KB and reaches for the whole app. We
 * lift the memoir-canonical lifecycle out by name and run it against a
 * minimal DOM double, so what executes is the SHIPPED source rather than
 * a paraphrase of it. */
function lift(src, names) {
  const out = [];
  names.forEach(function (n) {
    const patterns = [
      new RegExp('(?:^|\\n)(async function ' + n + '\\s*\\([\\s\\S]*?\\n\\})', 'm'),
      new RegExp('(?:^|\\n)(function ' + n + '\\s*\\([\\s\\S]*?\\n\\})', 'm'),
      new RegExp('(?:^|\\n)(window\\.' + n + ' = function[\\s\\S]*?\\n\\};)', 'm'),
    ];
    let found = null;
    for (const p of patterns) { const m = src.match(p); if (m) { found = m[1]; break; } }
    if (!found) { throw new Error('could not lift ' + n + ' from the shell'); }
    out.push(found);
  });
  return out.join('\n\n');
}

const html = fs.readFileSync(SHELL, 'utf8');
const blocks = html.match(/<script>([\s\S]*?)<\/script>/g) || [];
const inline = blocks
  .map(b => b.replace(/^<script>/, '').replace(/<\/script>$/, ''))
  .reduce((a, b) => (a.length > b.length ? a : b), '');

const constants = `
const MEMOIR_CANON_IDLE = "idle";
const MEMOIR_CANON_LOADING = "loading";
const MEMOIR_CANON_READY = "ready";
const MEMOIR_CANON_UNAVAILABLE = "unavailable";
let _memoirCanonical = null;
let _memoirCanonicalStatus = MEMOIR_CANON_IDLE;
let _memoirCanonicalPerson = null;
let _memoirCanonicalGen = 0;
let _memoirCanonicalAbort = null;
let _memoirFactsGen = 0;
let _memoirFactsAbort = null;
`;

const lifted = lift(inline, [
  '_memoirActivePerson',
  '_memoirCanonicalReady',
  '_memoirResetForNarratorSwitch',
  '_memoirLoadCanonical',
  '_memoirPaintCanonicalIfCurrent',
  '_memoirLoadCanonicalAndRender',
  '_memoirCanonicalLinesRaw',
  '_memoirCanonicalRecords',
  '_memoirCanonicalLines',
  '_memoirRenderCanonical',
  '_memoirEvaluateState',
  '_memoirBuildTxtContent',
  '_memoirExportBlockedReason',
  '_memoirLoadStoredFacts',
  '_memoirLoadFactsLane',
]);

/* ── Minimal DOM double ───────────────────────────────────────────────
 * Enough CSS to run the SHIPPED selectors: tag, .class, [attr] and
 * :not(...) of either. Written out rather than stubbed because the
 * defects under test live IN those selectors -- `hasDraftProse`
 * counting reviewed evidence as operator prose, and the evidence
 * recognition that has to tell an item apart from an outage notice. */
function matches(el, sel) {
  const parts = sel.trim().match(/(:not\([^)]*\)|\[[^\]]*\]|\.[^.\[:\s]+|^[a-zA-Z]+)/g) || [];
  for (const p of parts) {
    if (p.startsWith(':not(')) {
      if (matches(el, p.slice(5, -1))) return false;
    } else if (p.startsWith('[')) {
      const name = p.slice(1, -1).split('=')[0];
      if (el.attrs[name] === undefined) return false;
    } else if (p.startsWith('.')) {
      if ((el.className || '').split(/\s+/).indexOf(p.slice(1)) < 0) return false;
    } else {
      if ((el.tagName || '').toLowerCase() !== p.toLowerCase()) return false;
    }
  }
  return parts.length > 0;
}

function makeEl(tag) {
  return {
    tagName: tag, className: '', textContent: '', children: [], attrs: {},
    dataset: {}, hidden: false, disabled: false,
    set innerHTML(v) { if (v === '') this.children = []; },
    get innerHTML() { return this.children.length ? '<...>' : ''; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k]; },
    appendChild(c) { this.children.push(c); c.parent = this; return c; },
    remove() {
      if (!this.parent) return;
      const i = this.parent.children.indexOf(this);
      if (i >= 0) this.parent.children.splice(i, 1);
    },
    descendants() {
      const out = [];
      for (const c of this.children) {
        out.push(c);
        if (c.descendants) out.push(...c.descendants());
      }
      return out;
    },
    querySelectorAll(sel) { return this.descendants().filter(e => matches(e, sel)); },
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; },
    allText() {
      return [this.textContent].concat(
        this.children.map(c => (c.allText ? c.allText() : ''))).join('\n');
    },
  };
}

function freshCtx() {
  const content = makeEl('div');
  const els = {
    memoirScrollContent: content,
    memoirScrollPopover: makeEl('div'),
    memoirScrollIntro: makeEl('div'),
    memoirScrollHeading: makeEl('h3'),
    memoirPanelSubtitle: makeEl('p'),
    memoirThreadsHint: makeEl('p'),
    memoirEditBtn: makeEl('button'),
    memoirExportTxtBtn: makeEl('button'),
    memoirExportDocxBtn: makeEl('button'),
  };
  const ctx = {
    console: { log() {}, warn() {}, error() {} },
    state: { person_id: null },
    document: {
      getElementById: id => els[id] || null,
      createElement: makeEl,
      querySelector: sel => content.querySelector(sel),
      querySelectorAll: () => [],
    },
    AbortController: class { constructor() { this.signal = {}; } abort() { this.aborted = true; } },
    alert: msg => { ctx.__alerted = msg; },
    fetch: null,
    window: {},
    __content: content,
    __els: els,
    /* Adjacent features the panel touches. Stubbed because they are not
       what is under test -- but `lv80HasStructuredMemoirData` returns
       FALSE on purpose, so nothing but reviewed evidence can make the
       panel non-empty in these runs. */
    API: { FACTS_LIST: pid => '/api/facts/list?person_id=' + pid },
    _memoirState: 'empty',
    _memoirQualityFilter: () => true,
    _lv80AssignMemoirSection: () => 'story_details',
    _LV80_MEMOIR_SECTIONS: [],
    lv80HasStructuredMemoirData: () => false,
    lv80RenderStructuredMemoirPreview: () => {},
    _memoirRenderFragments: () => {},
    _memoirIsDraft: () => false,
    _memoirShowPromotionCue: () => {},
    setTimeout, clearTimeout, Blob: class {}, URL: { createObjectURL: () => '', revokeObjectURL: () => {} },
  };
  vm.createContext(ctx);
  vm.runInContext(constants + '\n' + lifted, ctx);
  return ctx;
}

const CANON = personId => ({
  person_id: personId,
  stories: [{ source_id: 'srcA1', text: 'The porch and the peas.',
              era: 'adolescence', placement: 'operator_set', language: 'en' }],
  trip_notes: [], lanes: { captured_stories: 'read', trip_notes: 'not_attempted' },
  complete: true,
});

function respond(ctx, body, opts) {
  opts = opts || {};
  ctx.fetch = () => new Promise((res, rej) => {
    const go = () => {
      if (opts.reject) return rej(new Error('network down'));
      res({ ok: opts.ok !== false, json: () => Promise.resolve(body) });
    };
    opts.delay ? setTimeout(go, opts.delay) : go();
  });
}

/* Two lanes, answered independently, so the COMPLETION ORDER can be
   controlled. That order is the defect this file exists to catch: the
   panel used to show a different thing depending on which request won
   the race. */
function routes(ctx, spec) {
  ctx.fetch = (url) => {
    const which = String(url).indexOf('/api/memoir/canonical') >= 0
      ? 'canonical' : 'facts';
    const s = spec[which] || {};
    return new Promise((res, rej) => {
      const go = () => {
        if (s.reject) return rej(new Error('network down'));
        res({ ok: s.ok !== false, json: () => Promise.resolve(s.body) });
      };
      s.delay ? setTimeout(go, s.delay) : go();
    });
  };
}

const NO_FACTS = { items: [] };

(async function main() {
  section('Loading is independent of the facts lane');
  {
    const ctx = freshCtx();
    ctx.state.person_id = 'A';
    respond(ctx, CANON('A'));
    await vm.runInContext('_memoirLoadCanonicalAndRender("A")', ctx);
    ok('zero facts + one approved story still renders evidence',
       ctx.__content.allText().indexOf('The porch and the peas.') >= 0);
    ok('status is ready', vm.runInContext('_memoirCanonicalStatus', ctx) === 'ready');
    ok('the evidence block is export-excluded',
       (ctx.__content.querySelector('.memoir-canonical-evidence') || {}).attrs
         ['data-export-exclude'] === 'true');
    const box = ctx.__content.querySelector('.memoir-canonical-evidence');
    const withId = (box ? box.children : []).filter(c => c.attrs['data-source-id']);
    ok('the story line carries its source id',
       withId.length === 1 && withId[0].attrs['data-source-id'] === 'srcA1');
  }

  section('A delayed narrator-A answer cannot alter narrator B');
  {
    const ctx = freshCtx();
    ctx.state.person_id = 'A';
    respond(ctx, CANON('A'), { delay: 30 });
    const p = vm.runInContext('_memoirLoadCanonicalAndRender("A")', ctx);
    ctx.state.person_id = 'B';                       // operator switches
    vm.runInContext('_memoirResetForNarratorSwitch()', ctx);
    await p;
    ok('A\'s delayed SUCCESS does not paint',
       ctx.__content.allText().indexOf('The porch and the peas.') < 0);
    ok('A\'s delayed success does not populate the cache',
       vm.runInContext('_memoirCanonical === null', ctx));
  }
  {
    const ctx = freshCtx();
    ctx.state.person_id = 'A';
    respond(ctx, null, { reject: true, delay: 30 });
    const p = vm.runInContext('_memoirLoadCanonical("A")', ctx);
    ctx.state.person_id = 'B';
    vm.runInContext('_memoirResetForNarratorSwitch()', ctx);
    await p;
    ok('A\'s delayed FAILURE does not mark B unavailable',
       vm.runInContext('_memoirCanonicalStatus', ctx) !== 'unavailable');
  }
  {
    const ctx = freshCtx();
    ctx.state.person_id = 'A';
    respond(ctx, CANON('SOMEONE-ELSE'));            // server disagrees
    await vm.runInContext('_memoirLoadCanonical("A")', ctx);
    ok('a response about another narrator is discarded',
       vm.runInContext('_memoirCanonicalStatus', ctx) === 'unavailable');
  }

  section('The narrator switch clears the previous evidence');
  {
    const ctx = freshCtx();
    ctx.state.person_id = 'A';
    respond(ctx, CANON('A'));
    await vm.runInContext('_memoirLoadCanonicalAndRender("A")', ctx);
    ok('painted first', ctx.__content.allText().indexOf('The porch') >= 0);
    vm.runInContext('_memoirResetForNarratorSwitch()', ctx);
    ok('the DOM block is removed on switch',
       ctx.__content.querySelector('.memoir-canonical-evidence') === null);
    ok('the cache is dropped', vm.runInContext('_memoirCanonical === null', ctx));
    ok('the status returns to idle',
       vm.runInContext('_memoirCanonicalStatus', ctx) === 'idle');
  }

  section('Export refuses until the evidence is ready for THIS narrator');
  {
    const ctx = freshCtx();
    ctx.state.person_id = 'A';
    ok('idle refuses',
       typeof vm.runInContext('_memoirExportBlockedReason()', ctx) === 'string');

    respond(ctx, CANON('A'), { delay: 30 });
    const p = vm.runInContext('_memoirLoadCanonical("A")', ctx);
    const midflight = vm.runInContext('_memoirExportBlockedReason()', ctx);
    ok('loading refuses', typeof midflight === 'string' &&
       /still loading/i.test(midflight), midflight);
    await p;
    ok('ready permits',
       vm.runInContext('_memoirExportBlockedReason()', ctx) === null);

    ctx.state.person_id = 'B';                       // cache belongs to A
    const wrong = vm.runInContext('_memoirExportBlockedReason()', ctx);
    ok('a cache belonging to another narrator refuses',
       typeof wrong === 'string', String(wrong));
  }
  {
    const ctx = freshCtx();
    ctx.state.person_id = 'A';
    respond(ctx, null, { ok: false });
    await vm.runInContext('_memoirLoadCanonical("A")', ctx);
    const why = vm.runInContext('_memoirExportBlockedReason()', ctx);
    ok('unavailable refuses', typeof why === 'string' &&
       /could not be read/i.test(why), String(why));
    ok('and the preview says so',
       vm.runInContext('_memoirCanonicalLines().join("|")', ctx)
         .indexOf('UNAVAILABLE') >= 0);
  }
  {
    const ctx = freshCtx();
    ctx.state.person_id = 'A';
    const partial = CANON('A');
    partial.lanes.trip_notes = 'partial';
    partial.complete = false;
    respond(ctx, partial);
    await vm.runInContext('_memoirLoadCanonical("A")', ctx);
    ok('an incomplete read refuses the export',
       typeof vm.runInContext('_memoirExportBlockedReason()', ctx) === 'string');
  }

  section('Evidence appears once, and is never harvested as operator prose');
  {
    const ctx = freshCtx();
    ctx.state.person_id = 'A';
    respond(ctx, CANON('A'));
    await vm.runInContext('_memoirLoadCanonicalAndRender("A")', ctx);
    await vm.runInContext('_memoirLoadCanonicalAndRender("A")', ctx);
    const text = ctx.__content.allText();
    const count = text.split('The porch and the peas.').length - 1;
    ok('a repeated load does not duplicate the block', count === 1,
       'found ' + count);
    const boxes = ctx.__content.children.filter(
      c => (c.className || '').indexOf('memoir-canonical-evidence') >= 0);
    ok('exactly one evidence block exists', boxes.length === 1);
    const lines = boxes[0] ? boxes[0].children : [];
    ok('every evidence line is export-excluded',
       lines.length > 0 && lines.every(l => l.attrs['data-export-exclude'] === 'true'));
  }

  /* ADDED after mutation testing, 2026-08-19. The three checks below
     each exist because a mutant SURVIVED the first cut of this harness:
     deleting the active-narrator half of `stale()`, deleting the
     identity clear from the reset, and stopping both export entry
     points from consulting the gate all left 23/23 green. A suite that
     stays green on the defect it was written for is decoration. */

  section('A switch that does not go through the reset is still caught');
  {
    /* `_memoirResetForNarratorSwitch()` bumps the generation, so the
       generation check alone kills every switch that goes through it.
       The second half of `stale()` is for the switch that does NOT --
       any path that moves `state.person_id` without calling the reset,
       which is exactly the shape the shell had before this commit. */
    const ctx = freshCtx();
    ctx.state.person_id = 'A';
    respond(ctx, CANON('A'), { delay: 30 });
    const p = vm.runInContext('_memoirLoadCanonicalAndRender("A")', ctx);
    ctx.state.person_id = 'B';                  // NO reset call
    await p;
    ok('a delayed A answer does not paint into B',
       ctx.__content.allText().indexOf('The porch and the peas.') < 0);
    ok('...and does not populate the cache',
       vm.runInContext('_memoirCanonical === null', ctx));
  }
  {
    const ctx = freshCtx();
    ctx.state.person_id = 'A';
    respond(ctx, null, { reject: true, delay: 30 });
    const p = vm.runInContext('_memoirLoadCanonical("A")', ctx);
    ctx.state.person_id = 'B';                  // NO reset call
    await p;
    ok('a delayed A failure does not mark B unavailable',
       vm.runInContext('_memoirCanonicalStatus', ctx) !== 'unavailable');
  }

  section('The reset leaves no trace of the previous narrator');
  {
    const ctx = freshCtx();
    ctx.state.person_id = 'A';
    respond(ctx, CANON('A'));
    await vm.runInContext('_memoirLoadCanonicalAndRender("A")', ctx);
    vm.runInContext('_memoirResetForNarratorSwitch()', ctx);
    ok('the remembered owner is cleared, not merely the payload',
       vm.runInContext('_memoirCanonicalPerson === null', ctx),
       'still ' + vm.runInContext('String(_memoirCanonicalPerson)', ctx));
  }

  section('Both export entry points consult the gate');
  {
    /* Testing `_memoirExportBlockedReason()` directly proves the gate
       computes the right answer. It does not prove anything CALLS it,
       and a gate nobody calls is a comment. */
    const exports = lift(inline, ['memoirExportTXT', 'memoirExportDOCX']);
    for (const name of ['memoirExportTXT', 'memoirExportDOCX']) {
      const ctx = freshCtx();
      ctx.state.person_id = 'A';                 // status is idle => blocked
      ctx.__downloaded = false;
      ctx._memoirBuildTxtFilename = () => 'x.txt';
      ctx._memoirBuildTxtContent = () => 'body';
      ctx._memoirDownloadTxt = () => { ctx.__downloaded = true; };
      /* NOT 'empty'. `memoirExportDOCX` returns early on the empty
         state, BEFORE it reaches anything the gate protects -- so a
         mutant that skipped the gate entirely still did nothing here,
         and this check passed on the defect it was written for. The
         state has to be one where the export would otherwise proceed. */
      ctx._memoirState = 'evidence';
      ctx.lv80LogTurnDebug = () => {};
      /* A REQUEST IS THE TELL. `memoirExportDOCX` catches its own
         failures and alerts, so "something was alerted and nothing
         downloaded" is ALSO what a skipped gate looks like once the
         server call fails -- which is how a mutant that deleted the
         gate outright passed the first version of this check. Counting
         requests separates refusing from trying and failing. */
      let requests = 0;
      ctx.fetch = () => { requests++; return Promise.reject(new Error('no server')); };
      vm.runInContext(exports, ctx);
      let threw = null;
      try { await vm.runInContext(name + '()', ctx); }
      catch (e) { threw = (e && e.message) || String(e); }
      ok(name + ' refuses while the evidence is not ready',
         threw === null && requests === 0 && ctx.__downloaded === false &&
         /reviewed/i.test(String(ctx.__alerted)),
         'requests=' + requests + ' downloaded=' + ctx.__downloaded +
         ' alert=' + ctx.__alerted + (threw ? ' threw=' + threw : ''));
    }
  }

  /* ── THE ENTRY POINT, NOT THE HELPER ─────────────────────────────
     Everything above drives `_memoirLoadCanonicalAndRender()`. The
     product does not: it calls `_memoirLoadStoredFacts()`, which runs
     BOTH lanes, and every facts branch begins by clearing the panel.
     Driving only the helper is why the coordination defect survived a
     green harness. These run the real entry point. */

  async function bothOrders(label, spec) {
    const ctx = freshCtx();
    ctx.state.person_id = 'A';
    routes(ctx, spec);
    await vm.runInContext('_memoirLoadStoredFacts("A")', ctx);
    const text = ctx.__content.allText();
    ok(label + ': the story is in the DOM',
       text.indexOf('The porch and the peas.') >= 0);
    ok(label + ': exactly once',
       text.split('The porch and the peas.').length - 1 === 1);
    ok(label + ': the panel is visible, not hidden',
       ctx.__els.memoirScrollContent.hidden === false);
    ok(label + ': the memoir state is not empty',
       vm.runInContext('_memoirState', ctx) !== 'empty',
       vm.runInContext('_memoirState', ctx));
    ok(label + ': DOCX is offered',
       ctx.__els.memoirExportDocxBtn.disabled === false);
    return ctx;
  }

  section('Zero facts + one approved story — facts lane answers FIRST');
  await bothOrders('facts first', {
    facts: { body: NO_FACTS, delay: 5 },
    canonical: { body: CANON('A'), delay: 40 },
  });

  section('Zero facts + one approved story — canonical answers FIRST');
  {
    const ctx = await bothOrders('canonical first', {
      facts: { body: NO_FACTS, delay: 40 },
      canonical: { body: CANON('A'), delay: 5 },
    });
    /* Same visible result either way. That equivalence IS the fix: the
       operator must not see a different memoir because one request was
       slower. */
    ok('canonical first: TXT carries the story exactly once',
       vm.runInContext('_memoirBuildTxtContent()', ctx)
         .split('The porch and the peas.').length - 1 === 1);
  }

  section('A canonical-only memoir reaches the DOCX request');
  {
    const ctx = freshCtx();
    ctx.state.person_id = 'A';
    routes(ctx, { facts: { body: NO_FACTS }, canonical: { body: CANON('A') } });
    await vm.runInContext('_memoirLoadStoredFacts("A")', ctx);
    /* The DOCX route returns early on `_memoirState === "empty"`. A
       narrator whose only content is reviewed evidence used to sit in
       exactly that state, so the one thing they had said could not be
       exported at all. */
    ok('the empty-state guard does not fire',
       vm.runInContext('_memoirState', ctx) !== 'empty');
    ok('and the export gate permits it',
       vm.runInContext('_memoirExportBlockedReason()', ctx) === null,
       String(vm.runInContext('_memoirExportBlockedReason()', ctx)));
    /* The state must be `evidence`, not `threads` or `draft`. "Not
       empty" is too weak a claim: counting reviewed evidence as
       operator prose ALSO produces a non-empty panel -- it just
       presents the narrator's approved words back to the operator as
       something they wrote, under a heading that says so. Content, but
       not their authorship. */
    ok('the evidence is recognised as evidence, not as their draft',
       vm.runInContext('_memoirState', ctx) === 'evidence',
       vm.runInContext('_memoirState', ctx));
    ok('and the panel heading says whose words these are',
       ctx.__els.memoirScrollHeading.textContent === 'In Their Own Words',
       ctx.__els.memoirScrollHeading.textContent);
  }

  section('An unreadable lane is SEEN, not hidden behind the empty state');
  {
    /* The export was already blocked correctly. What was wrong is that
       a narrator with no facts, no structured profile and an unreadable
       story lane landed in `empty` -- which HIDES the panel -- so the
       notice explaining the refusal was rendered into a hidden element.
       The operator saw an intro screen and a refusal with no reason. */
    const ctx = freshCtx();
    ctx.state.person_id = 'A';
    routes(ctx, { facts: { body: NO_FACTS }, canonical: { ok: false } });
    await vm.runInContext('_memoirLoadStoredFacts("A")', ctx);
    ok('the canonical read is unavailable',
       vm.runInContext('_memoirCanonicalStatus', ctx) === 'unavailable');
    ok('the panel is NOT hidden',
       ctx.__els.memoirScrollContent.hidden === false,
       'state=' + vm.runInContext('_memoirState', ctx));
    ok('the notice is on screen',
       /UNAVAILABLE/.test(ctx.__content.allText()));
    ok('the heading does not promise stories it does not have',
       ctx.__els.memoirScrollHeading.textContent !== 'In Their Own Words',
       ctx.__els.memoirScrollHeading.textContent);
    ok('the export is still refused',
       typeof vm.runInContext('_memoirExportBlockedReason()', ctx) === 'string');
    ok('and the notice is not counted as evidence',
       ctx.__content.querySelectorAll('[data-source-id]').length === 0);
  }

  section('Identical tellings keep separate provenance');
  {
    const ctx = freshCtx();
    ctx.state.person_id = 'A';
    const twin = CANON('A');
    twin.stories = [
      { source_id: 'srcTWIN1', text: 'We walked to church.', era: 'adolescence',
        placement: 'operator_set', language: 'en' },
      { source_id: 'srcTWIN2', text: 'We walked to church.', era: 'later_years',
        placement: 'operator_set', language: 'en' },
    ];
    routes(ctx, { facts: { body: NO_FACTS }, canonical: { body: twin } });
    await vm.runInContext('_memoirLoadStoredFacts("A")', ctx);
    const ids = ctx.__content.querySelectorAll('[data-source-id]')
      .map(p => p.attrs['data-source-id']);
    ok('two identical texts render two paragraphs', ids.length === 2,
       JSON.stringify(ids));
    ok('...each keeping its own source id',
       ids[0] === 'srcTWIN1' && ids[1] === 'srcTWIN2', JSON.stringify(ids));
  }
  {
    /* The retired renderer attached ids by scanning each line for a
       substring of a known text, so a story CONTAINING another's words
       inherited the wrong id. */
    const ctx = freshCtx();
    ctx.state.person_id = 'A';
    const nested = CANON('A');
    nested.stories = [
      { source_id: 'srcSHORT', text: 'We walked.', era: 'adolescence',
        placement: 'operator_set', language: 'en' },
      { source_id: 'srcLONG', text: 'We walked. Then it rained.',
        era: 'later_years', placement: 'operator_set', language: 'en' },
    ];
    routes(ctx, { facts: { body: NO_FACTS }, canonical: { body: nested } });
    await vm.runInContext('_memoirLoadStoredFacts("A")', ctx);
    const ids = ctx.__content.querySelectorAll('[data-source-id]')
      .map(p => p.attrs['data-source-id']);
    ok('a containing story does not steal the shorter one\'s id',
       ids[0] === 'srcSHORT' && ids[1] === 'srcLONG', JSON.stringify(ids));
  }

  /* HONESTY NOTE, from the mutation pass. `_memoirCanonicalReady()`
     reads `status === READY && !!owner && !!active && active === owner`.
     Deleting the `!!owner` clause does NOT fail this harness, and that
     is not a hole in the checks -- it is redundant by construction:
     `!!active && active === owner` cannot be true with a null owner,
     and no reachable path sets READY without first setting the owner.
     It is kept as defence in depth, and recorded here as unproven by
     mutation rather than left to look covered. */

  section('Ownership is required, not merely non-contradicted');
  {
    const ctx = freshCtx();
    ctx.state.person_id = 'A';
    const anonymous = CANON('A');
    delete anonymous.person_id;                 // says nothing about whose
    routes(ctx, { facts: { body: NO_FACTS }, canonical: { body: anonymous } });
    await vm.runInContext('_memoirLoadStoredFacts("A")', ctx);
    ok('a response with no owner is rejected',
       vm.runInContext('_memoirCanonicalStatus', ctx) === 'unavailable');
    ok('...and nothing of it is painted',
       ctx.__content.allText().indexOf('The porch and the peas.') < 0);
  }
  {
    const ctx = freshCtx();
    ctx.state.person_id = 'A';
    routes(ctx, { facts: { body: NO_FACTS }, canonical: { body: CANON('A') } });
    await vm.runInContext('_memoirLoadStoredFacts("A")', ctx);
    ctx.state.person_id = null;                 // no narrator selected
    ok('with no narrator selected the export is refused',
       typeof vm.runInContext('_memoirExportBlockedReason()', ctx) === 'string');
  }

  section('The central switch resets before the incoming narrator loads');
  {
    /* `lvxSwitchNarratorSafe()` in app.js is the only place every
       narrator switch passes through. The reset used to sit in the
       shell AFTER that call returned, and three other call sites never
       reached it -- so the shell was the sole protection for a switch
       it does not own. */
    const appSrc = fs.readFileSync(
      path.join(REPO, 'ui', 'js', 'app.js'), 'utf8');
    const fn = appSrc.slice(appSrc.indexOf('async function lvxSwitchNarratorSafe'));
    /* COMMENTS STRIPPED FIRST. The first cut of this check fired on the
       word `await` inside the comment that EXPLAINS why the reset moved
       -- the sixth time in this repository that a guard has matched the
       prose describing the thing it guards. A guard has to match what
       the browser executes. */
    const body = stripJsComments(fn.slice(0, fn.indexOf('\n}\n')));
    /* The EXECUTABLE form, not merely the identifier. Asserting the
       name appears is satisfied by `if (false) { …reset… }` -- which is
       exactly the mutant this check exists to kill. */
    const guarded = /if\s*\(\s*typeof\s+window\._memoirResetForNarratorSwitch\s*===\s*"function"\s*\)[\s\S]{0,200}?window\._memoirResetForNarratorSwitch\(\);/;
    const resetAt = body.search(guarded);
    ok('the central switch calls the reset, behind a real guard',
       resetAt > 0, body.slice(0, 200));
    const firstAwait = body.indexOf('await ');
    ok('...before it awaits any hydration',
       resetAt > 0 && (firstAwait < 0 || resetAt < firstAwait),
       'reset@' + resetAt + ' firstAwait@' + firstAwait);
    ok('the shell no longer carries the only copy',
       (inline.match(/^\s*_memoirResetForNarratorSwitch\(\);/gm) || []).length === 0);
    ok('and the reset is exported on purpose',
       inline.indexOf(
         'window._memoirResetForNarratorSwitch = _memoirResetForNarratorSwitch;') > 0);
  }
  {
    /* Executed, not only read: A's evidence is on screen, the reset
       runs, and B hydrates. */
    const ctx = freshCtx();
    ctx.state.person_id = 'A';
    routes(ctx, { facts: { body: NO_FACTS }, canonical: { body: CANON('A') } });
    await vm.runInContext('_memoirLoadStoredFacts("A")', ctx);
    ok('A is painted first',
       ctx.__content.allText().indexOf('The porch and the peas.') >= 0);
    ctx.state.person_id = 'B';
    vm.runInContext('_memoirResetForNarratorSwitch()', ctx);
    ok('A\'s evidence is gone before B loads',
       ctx.__content.allText().indexOf('The porch and the peas.') < 0);
    ok('...and so is the cache that would have exported it',
       vm.runInContext('_memoirCanonical === null', ctx) &&
       typeof vm.runInContext('_memoirExportBlockedReason()', ctx) === 'string');
    const forB = CANON('B');
    forB.stories = [{ source_id: 'srcB1', text: 'B\'s own story.',
                      era: 'today', placement: 'operator_set', language: 'en' }];
    routes(ctx, { facts: { body: NO_FACTS }, canonical: { body: forB } });
    await vm.runInContext('_memoirLoadStoredFacts("B")', ctx);
    const t = ctx.__content.allText();
    ok('B sees only B', t.indexOf('B\'s own story.') >= 0 &&
       t.indexOf('The porch and the peas.') < 0);
  }

  section('The shipped harvesters exclude the block');
  {
    const excluded = (inline.match(
      /querySelectorAll\("p:not\(\.memoir-placeholder\):not\(\[data-export-exclude\]\)"\)/g)
      || []).length;
    const bare = (inline.match(
      /querySelectorAll\("p:not\(\.memoir-placeholder\)"\)/g) || []).length;
    ok('every paragraph harvest excludes displayed evidence',
       excluded > 0 && bare === 0,
       'excluded=' + excluded + ' bare=' + bare);
  }

  console.log('\n' + pass + ' passed, ' + fail + ' failed');
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
