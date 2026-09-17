/* The operator Bio Builder shows the COMPLETE record; narrator intake stays
   minimal. BUG-BIO-QUESTIONNAIRE-LOSSY-ROUNDTRIP-01.

   TWO JOBS THAT WERE SHARING ONE DEFAULT

     Narrator intake, conversational — a person answering Lori should not
     meet a sixteen-section form to begin. MINIMAL_SECTIONS is for that.

     Operator Bio Builder — somebody deliberately building a biography needs
     the whole record. Defaulting to minimal showed three sections of
     sixteen: grandparents, marriage, pets, traditions, early memories,
     education, later years, hobbies, technology and additional notes were
     present in the database and absent from the screen.

   WHY THIS IS DATA SAFETY AND NOT ONLY CONVENIENCE

     A form rendering six of eleven stored fields is how ten values of
     hand-typed family history were destroyed on 2026-09-15. The server-side
     merge now stops that from DELETING anything, but a section an operator
     cannot see is a section they cannot correct, and they were editing a
     record whose true extent was hidden from them.

   THE SEPARATION THIS PROTECTS

     `SECTIONS` — flipped by intakeMinimalEnabled() — is consumed only by
     the Bio Builder questionnaire tab. session-loop.js drives the
     narrator-facing walk from MINIMAL_SECTIONS **by name**, so the two
     cannot be coupled by accident. If a future edit makes the conversational
     loop read `SECTIONS`, this suite fails: that coupling would put the full
     sixteen-section form in front of a narrator.

   Run:  node tests/test_operator_questionnaire_scope.js
*/

"use strict";

const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");

const QQ = fs.readFileSync(
  process.env.LV_BBQQ_JS || path.join(ROOT, "ui/js/bio-builder-questionnaire.js"), "utf8");
const LOOP = fs.readFileSync(
  process.env.LV_LOOP_JS || path.join(ROOT, "ui/js/session-loop.js"), "utf8");

let failures = 0;
const check = (name, cond, detail) => {
  if (cond) console.log(`  ok    ${name}`);
  else { failures++; console.log(`  FAIL  ${name}\n        ${detail || ""}`); }
};
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "")
  .split("\n").filter((l) => !l.trim().startsWith("//")).join("\n");

const QQC = strip(QQ), LOOPC = strip(LOOP);

console.log("\noperator questionnaire scope\n");

/* Take a whole function by matching braces.

   The first version of this suite sliced from the declaration to the first
   `}` after the first `return`, which stopped inside the opening if-block
   and reported three failures against CORRECT code. That is the worst kind
   of test failure: it invites someone to change working behaviour to
   satisfy a broken assertion. Second time this session that a
   proximity-based slice has lied, so: brace matching, once, reused. */
function fnBody(src, decl) {
  const i = src.indexOf(decl);
  if (i === -1) return "";
  let depth = 0, started = false;
  for (let j = i; j < src.length; j++) {
    if (src[j] === "{") { depth++; started = true; }
    else if (src[j] === "}") { depth--; if (started && depth === 0) return src.slice(i, j + 1); }
  }
  return "";
}

/* ── the operator default ───────────────────────────────────────────── */
const fnIdx = QQC.indexOf("function intakeMinimalEnabled()");
check("intakeMinimalEnabled exists", fnIdx !== -1);
const fnBlock = fnBody(QQC, "function intakeMinimalEnabled()");

/* The LAST return in the function is the default — everything before it is
   an override that only fires when its condition matches. */
const lastReturn = (fnBlock.match(/return\s+(true|false)\s*;/g) || []).pop();
check("the default is the FULL record, not minimal",
  lastReturn === "return false;",
  "defaulting to minimal hides ten of sixteen sections from the operator " +
  "building the biography");

check("both overrides survive",
  /HORNELORE_INTAKE_MINIMAL/.test(fnBlock) &&
  /hornelore\.intake\.minimal/.test(fnBlock),
  "minimal must stay one setting away, not be deleted");

check("the window override still wins over localStorage",
  fnBlock.indexOf("HORNELORE_INTAKE_MINIMAL") < fnBlock.indexOf("hornelore.intake.minimal"));

/* ── both section lists still exist ─────────────────────────────────── */
check("FULL_SECTIONS is declared", /var\s+FULL_SECTIONS\s*=/.test(QQC));
check("MINIMAL_SECTIONS is declared", /var\s+MINIMAL_SECTIONS\s*=/.test(QQC),
  "narrator intake still needs it — this change is not its deletion");

check("SECTIONS chooses between them on the flag",
  /var\s+SECTIONS\s*=\s*intakeMinimalEnabled\(\)\s*\?\s*MINIMAL_SECTIONS\s*:\s*FULL_SECTIONS/.test(QQC));

/* ── the narrator-facing walk is NOT coupled to SECTIONS ────────────── */
check("session-loop drives its walk from MINIMAL_SECTIONS by name",
  /MINIMAL_SECTIONS/.test(LOOPC),
  "if the conversational loop ever read SECTIONS instead, flipping the " +
  "operator default would put a sixteen-section form in front of a narrator");

check("session-loop does not import the flag",
  !/intakeMinimalEnabled/.test(LOOPC),
  "the narrator walk must not depend on an operator-facing preference");

/* ── the full record really is larger ───────────────────────────────── */
const countIds = (src, varName) => {
  const i = src.indexOf(`var ${varName} = [`);
  if (i === -1) return 0;
  let depth = 0, j = src.indexOf("[", i), end = j;
  for (; j < src.length; j++) {
    if (src[j] === "[") depth++;
    else if (src[j] === "]") { depth--; if (depth === 0) { end = j; break; } }
  }
  return (src.slice(i, end).match(/^\s{4,6}id:\s*["']/gm) || []).length;
};
const nFull = countIds(QQC, "FULL_SECTIONS");
const nMin = countIds(QQC, "MINIMAL_SECTIONS");
check(`FULL_SECTIONS (${nFull}) is materially larger than MINIMAL_SECTIONS (${nMin})`,
  nFull > nMin && nMin > 0 && nFull >= 10,
  "if these converge, one of the two jobs has quietly lost its form");

/* ── MUTATIONS THAT MUST BREAK THIS SUITE ───────────────────────────────
   Verified 2026-09-17 via LV_BBQQ_JS / LV_LOOP_JS:
     1. the default returned to minimal          -> 2 checks fail
     2. SECTIONS hardcoded to MINIMAL_SECTIONS   -> 2 checks fail
     3. the localStorage override deleted        -> 3 checks fail
     4. the narrator walk coupled to SECTIONS    -> 2 checks fail
   Counts recorded by the run that verified them. */

console.log(failures === 0 ? "\n  all checks passed\n" : `\n  ${failures} FAILED\n`);
process.exit(failures === 0 ? 0 : 1);
