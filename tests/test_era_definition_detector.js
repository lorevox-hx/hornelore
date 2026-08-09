/* tests/test_era_definition_detector.js — WO-LEAN-LORI-RUNTIME-01
   Phase 8, the era-definition intent detector.

   Extracts `_looksLikeEraDefinitionQuestion` from ui/js/app.js and pins
   its truth table. These sixteen cases were run during development and
   caught two real misses; they are persisted here because development
   evidence that lives only in a terminal is not regression coverage.

   WHY THE DETECTOR IS ALLOWED TO READ THE NARRATOR'S TEXT AT ALL.
   Because it produces a FACT ABOUT the turn, not the turn's IDENTITY.
   The result is carried as `runtime71.era_definition_requested`;
   `turn_mode` stays "interview", so extraction and trip placement --
   whose eligibility sets are both frozenset({"interview"}) -- are
   untouched. A wrong answer here costs 272 tokens on one turn. A wrong
   answer in `lvRouteTurn` would cost the narrator's biography.

   THE CONJUNCTION IS THE SAFETY PROPERTY. An era WORD is necessary but
   not sufficient; a definition-shaped QUESTION is also required. That
   is what keeps "Coming of age was in Bismarck." out.

   Run:  node tests/test_era_definition_detector.js
   ────────────────────────────────────────────────────────────────── */
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.resolve(__dirname, '..');
const SRC = fs.readFileSync(
  path.join(REPO_ROOT, 'ui', 'js', 'app.js'), 'utf8'
);

function sliceDetector(src) {
  const startMarker = 'function _looksLikeEraDefinitionQuestion(text){';
  const start = src.indexOf(startMarker);
  if (start < 0) {
    throw new Error(
      'Could not find _looksLikeEraDefinitionQuestion — renamed or removed? ' +
      'If the detector moved, move this test with it; do not delete the ' +
      'truth table.'
    );
  }
  const end = src.indexOf('\n}', start);
  if (end < 0) throw new Error('Could not find the detector end brace');
  return src.slice(start, end + 2);
}

// `_lvText` is app.js's own string coercion; supplied rather than
// re-implemented so the slice runs against the real dependency shape.
const detector = new Function(
  '_lvText',
  sliceDetector(SRC) + '\nreturn _looksLikeEraDefinitionQuestion;'
)((x) => String(x == null ? '' : x));

/* [text, expected, why] */
const CASES = [
  // ── MUST fire: an era word AND a request for its meaning ──────────
  ['What do you mean by Coming of Age?', true, 'the canonical phrasing'],
  ['What do you mean by Coming of Age? I moved to Denver when I was 22.',
   true,
   'THE MIXED CASE. A question and a piece of biography in one turn. ' +
   'The glossary must be available AND the turn must stay an ordinary ' +
   'interview turn so Denver is still extracted. This case is the ' +
   'reason the result is not a turn_mode.'],
  ['whats adolescence again?', true,
   'MISSED BY THE FIRST CUT: it required whitespace straight after ' +
   '"what", so "whats" never matched.'],
  ['What are the building years?', true, 'plain definition request'],
  ['Can you explain what earliest years means', true, '"explain" branch'],
  ['which years count as later years', true, '"which years" branch'],
  ['what era is that', true,
   'MISSED BY THE FIRST CUT: the era word sits BETWEEN "what" and ' +
   '"is", so an adjacency-based pattern could not see it.'],
  ['What does early school years mean?', true, '"what does … mean"'],

  // ── MUST NOT fire: an era word MENTIONED, not asked about ─────────
  ['I was in my building years then', false,
   'a narrator placing themselves in an era is not asking what it is'],
  ['When I was 22 I moved to Denver.', false, 'no era word at all'],
  ['My adolescence was hard.', false, 'mention, and no question shape'],
  ['Coming of age was in Bismarck.', false,
   'contains "was", but no "what" — the question conjunct fails'],
  ['That was during my later years working at the plant.', false,
   'mention inside ordinary narration'],
  ['What was my mother like?', false,
   'a real question with "what" and "was" — blocked by the ERA WORD ' +
   'conjunct alone. This is the case that proves the conjunction ' +
   'carries the safety, not the question pattern.'],
  ['We moved to Denver in the building years and it rained.', false,
   'era word inside a story, no request'],
  ['', false, 'empty input'],
];

let failures = 0;
for (const [text, expected, why] of CASES) {
  const got = detector(text);
  if (got !== expected) {
    failures += 1;
    console.error(
      `FAIL want=${expected} got=${got}\n      text: ${JSON.stringify(text)}` +
      `\n      why:  ${why}`
    );
  }
}

assert.strictEqual(
  failures, 0,
  `${failures} of ${CASES.length} detector cases failed`
);

// The conjunction itself, asserted structurally: a future edit that
// drops the era-word requirement would make every "what … is" turn ship
// the glossary, and the truth table above would still mostly pass.
const body = sliceDetector(SRC);
assert.ok(
  body.includes('if (!ERA_WORDS.test(t)) return false;'),
  'the era-word early return is gone — the detector is no longer a ' +
  'conjunction, and a bare question shape can now fire it'
);

// And the detector must stay out of turn routing. Duplicated from the
// Python suite deliberately: this is the assertion whose failure would
// cost a narrator their words, and it should fail in whichever suite
// somebody happens to run.
const routeStart = SRC.indexOf('function lvRouteTurn(text){');
assert.ok(routeStart > 0, 'lvRouteTurn not found');
const routeBody = SRC.slice(routeStart, SRC.indexOf('\n}', routeStart));
assert.ok(
  !routeBody.includes('_looksLikeEraDefinitionQuestion'),
  'the era detector was wired into lvRouteTurn. That would give era ' +
  'questions their own turn_mode, and both EXTRACTION_ELIGIBLE_TURN_MODES ' +
  'and PLACEMENT_ELIGIBLE_TURN_MODES are frozenset({"interview"}) — so ' +
  'the biography in a mixed turn would stop being captured.'
);

console.log(`ok — ${CASES.length} era-definition detector cases`);
