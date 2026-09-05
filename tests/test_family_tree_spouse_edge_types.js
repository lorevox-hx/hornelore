/* tests/test_family_tree_spouse_edge_types.js
   WO-LORI-ARCHIVE-TO-MEMOIR-02 Phase 5B item 7.

   ── WHAT THIS PINS ───────────────────────────────────────────────────

   Both Family Tree seeding paths hardcoded `relType = "marriage"` for
   every spouse-ish word. `partnership` and `former_marriage` were in
   FT_REL_TYPES and nothing ever chose them, so the draft tree drew a
   marriage for an unmarried partner and drew a divorced ex-wife as a
   current spouse — while `late wife` came out right by accident.

   Phase 5B made the narrator's wording decide the lane server-side.
   This is the same rule at the surface that renders it.

   ── HOW IT RUNS ──────────────────────────────────────────────────────

   `_ftSpouseEdgeType` is sliced out of the SHIPPED file and evaluated,
   following `tests/test_normalize_profile_passthrough.js`. Asserting on
   source text would prove the words are present, not that the function
   returns them — and a source-string assertion is never acceptance
   evidence by itself (CLAUDE.md, "a fixture may not supply the property
   being proven").

   Run:  node tests/test_family_tree_spouse_edge_types.js
*/
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.resolve(__dirname, '..');
const SRC_PATH = path.join(REPO_ROOT, 'ui', 'js', 'bio-builder-family-tree.js');
const SRC = fs.readFileSync(SRC_PATH, 'utf8');

function sliceFunction(src, marker) {
  const start = src.indexOf(marker);
  if (start < 0) throw new Error('marker not found: ' + marker);
  const openBrace = src.indexOf('{', start);
  let depth = 0;
  for (let i = openBrace; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') {
      depth--;
      if (depth === 0) return src.slice(start, i + 1);
    }
  }
  throw new Error('unbalanced braces after: ' + marker);
}

const body = sliceFunction(SRC, 'function _ftSpouseEdgeType');
// eslint-disable-next-line no-eval
const _ftSpouseEdgeType = eval('(' + body + ')');

let checks = 0;
function is(input, expected, why) {
  const got = _ftSpouseEdgeType(input);
  assert.strictEqual(
    got, expected,
    `_ftSpouseEdgeType(${JSON.stringify(input)}) → ${got}, expected ${expected}` +
    (why ? ` — ${why}` : ''));
  checks++;
}

/* ── current spouse: unchanged, and these are the positive controls ── */
is('wife', 'marriage');
is('husband', 'marriage');
is('spouse', 'marriage');
is('Wife', 'marriage', 'case must not decide the edge');

/* ── a partner is not a marriage ───────────────────────────────────── */
is('partner', 'partnership', 'the defect: an unmarried partner drew a marriage');
is('life partner', 'partnership');

/* ── divorce ends a marriage; it does not un-marry it ──────────────── */
is('ex-wife', 'former_marriage');
is('ex husband', 'former_marriage');
is('former wife', 'former_marriage');
is('previous husband', 'former_marriage');

/* ── the lane name, which is what the profile actually carries ─────── */
is('priorPartners', 'former_marriage',
   'the lane contains the word `partner`; it is not a partner relation');
is('family.priorPartners.relation', 'former_marriage');
is('prior_partners', 'former_marriage');

/* ── widowhood is not divorce ──────────────────────────────────────── */
is('late wife', 'marriage',
   'a widow\'s marriage was not dissolved');
is('late husband', 'marriage');

/* ── a former unmarried partner has no destination; do not invent ──── */
is('ex-partner', 'other',
   '`partnership` would claim it is current, `former_marriage` invents a wedding');
is('former partner', 'other');

/* ── non-vacuity: the function must DISCRIMINATE, not return one value ── */
const distinct = new Set(['wife', 'partner', 'ex-wife', 'ex-partner']
  .map(_ftSpouseEdgeType));
assert.strictEqual(
  distinct.size, 4,
  'four different relationships collapsed onto ' + [...distinct].join('/') +
  ' — a constant would pass every test above');

/* ── every value it can return is a legal FT_REL_TYPE ──────────────── */
const typesLine = SRC.match(/var FT_REL_TYPES\s*=\s*\[([^\]]+)\]/);
assert.ok(typesLine, 'FT_REL_TYPES not found — the vocabulary moved');
const legal = typesLine[1].split(',').map(s => s.trim().replace(/^["']|["']$/g, ''));
for (const rel of ['wife', 'husband', 'spouse', 'partner', 'ex-wife',
                   'ex-partner', 'late wife', 'priorPartners', '']) {
  const got = _ftSpouseEdgeType(rel);
  assert.ok(legal.includes(got),
            `_ftSpouseEdgeType(${JSON.stringify(rel)}) → ${got}, which is not in FT_REL_TYPES`);
  checks++;
}

/* ── both seeding paths must actually CALL it ─────────────────────────
   The function being right is worth nothing if a caller still carries
   the hardcoded string. Counted, not just searched: two call sites. */
const calls = (SRC.match(/relType\s*=\s*_ftSpouseEdgeType\(/g) || []).length;
assert.strictEqual(calls, 2,
  `expected both spouse-branch seeders to call _ftSpouseEdgeType, found ${calls}`);
assert.strictEqual(
  (SRC.match(/role\s*=\s*"spouse";\s*relType\s*=\s*"marriage"/g) || []).length, 0,
  'a seeding path still hardcodes relType = "marriage" for the spouse branch');

console.log(`OK — test_family_tree_spouse_edge_types: ${checks} checks, ` +
            `2 call sites wired`);
