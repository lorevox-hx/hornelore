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
  '_memoirLoadCanonicalAndRender',
  '_memoirCanonicalLines',
  '_memoirRenderCanonical',
  '_memoirExportBlockedReason',
]);

/* ── Minimal DOM double ─────────────────────────────────────────────── */
function makeEl(tag) {
  return {
    tagName: tag, className: '', textContent: '', children: [], attrs: {},
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k]; },
    appendChild(c) { this.children.push(c); c.parent = this; return c; },
    remove() {
      if (!this.parent) return;
      const i = this.parent.children.indexOf(this);
      if (i >= 0) this.parent.children.splice(i, 1);
    },
    querySelector(sel) {
      const want = sel.replace(/^\./, '');
      for (const c of this.children) {
        if ((c.className || '').split(/\s+/).indexOf(want) >= 0) return c;
        const deep = c.querySelector ? c.querySelector(sel) : null;
        if (deep) return deep;
      }
      return null;
    },
    allText() {
      return [this.textContent].concat(
        this.children.map(c => (c.allText ? c.allText() : ''))).join('\n');
    },
  };
}

function freshCtx() {
  const content = makeEl('div');
  const ctx = {
    console,
    state: { person_id: null },
    document: {
      getElementById: id => (id === 'memoirScrollContent' ? content : null),
      createElement: makeEl,
      querySelector: sel => content.querySelector(sel),
    },
    AbortController: class { constructor() { this.signal = {}; } abort() { this.aborted = true; } },
    alert: msg => { ctx.__alerted = msg; },
    fetch: null,
    window: {},
    __content: content,
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
      ctx._memoirState = 'threads';
      ctx.lv80LogTurnDebug = () => {};
      vm.runInContext(exports, ctx);
      /* A THROW is not a refusal. Past the gate, both functions reach
         DOM and network the double does not provide, so an export that
         skipped the gate crashes here -- which must read as the failure
         it is, not as an aborted harness run. */
      let threw = null;
      try { await vm.runInContext(name + '()', ctx); }
      catch (e) { threw = (e && e.message) || String(e); }
      ok(name + ' refuses while the evidence is not ready',
         threw === null && ctx.__downloaded === false &&
         typeof ctx.__alerted === 'string',
         'downloaded=' + ctx.__downloaded + ' alert=' + ctx.__alerted +
         (threw ? ' threw=' + threw : ''));
    }
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
