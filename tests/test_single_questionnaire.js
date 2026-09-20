/* There is one questionnaire, and every answer has one home.

   WO-01, 2026-09-19. Replaces test_operator_questionnaire_scope.js, which
   guarded the arrangement this work order removed: two section definitions
   selected by a flag, and a migration that moved six sections under
   `_legacyRemovedSections` on every restore and save.

   That suite also asserted that session-loop.js "drives its walk from
   MINIMAL_SECTIONS by name". Reading the code, it never did — it probed a
   window global that was never set and fell back to a hardcoded list. The
   test was guarding a coupling that existed only in comments. Retired.

   SOURCE-CONTRACT checks. The behavioural proof — all sixteen sections
   render, two-entry sections survive save/reload/switch, no save emits a
   legacy key — is in test_bio_builder_save_sequences.js.

   Run:  node tests/test_single_questionnaire.js
*/

"use strict";

const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");
const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "")
  .split("\n").filter((l) => !l.trim().startsWith("//")).join("\n");

const QQ   = strip(fs.readFileSync(process.env.LV_BBQQ_JS   || path.join(ROOT, "ui/js/bio-builder-questionnaire.js"), "utf8"));
const LOOP = strip(fs.readFileSync(process.env.LV_LOOP_JS   || path.join(ROOT, "ui/js/session-loop.js"), "utf8"));
const CORE = strip(fs.readFileSync(process.env.LV_BBCORE_JS || path.join(ROOT, "ui/js/bio-builder-core.js"), "utf8"));

let failures = 0;
const check = (name, cond, detail) => {
  if (cond) console.log(`  ok    ${name}`);
  else { failures++; console.log(`  FAIL  ${name}\n        ${detail || ""}`); }
};
function fnBody(src, decl) {
  const i = src.indexOf(decl); if (i === -1) return "";
  let depth = 0, started = false;
  for (let j = i; j < src.length; j++) {
    if (src[j] === "{") { depth++; started = true; }
    else if (src[j] === "}") { depth--; if (started && depth === 0) return src.slice(i, j + 1); }
  }
  return "";
}
function countSections(src) {
  const i = src.indexOf("var SECTIONS = ["); if (i === -1) return -1;
  let depth = 0, j = src.indexOf("[", i), end = j;
  for (; j < src.length; j++) { if (src[j] === "[") depth++; else if (src[j] === "]") { depth--; if (depth === 0) { end = j; break; } } }
  return (src.slice(i, end).match(/^\s{4,6}id:\s*["']/gm) || []).length;
}

console.log("\none questionnaire\n");

check("SECTIONS is the only section definition",
  /var\s+SECTIONS\s*=\s*\[/.test(QQ) && !/FULL_SECTIONS|MINIMAL_SECTIONS/.test(QQ),
  "two definitions selected by a flag is the arrangement WO-01 removed");

check("it is the full record (16 sections)", countSections(QQ) === 16, "found " + countSections(QQ));

check("the minimal-mode flag reader is gone",
  !/intakeMinimalEnabled|HORNELORE_INTAKE_MINIMAL|hornelore\.intake\.minimal/.test(QQ),
  "a toggle that can hide ten sections from the operator is how ten values were lost on 2026-09-15");

check("the legacy migration is gone",
  !/_migrateRemovedSectionsToLegacy/.test(QQ) && !/_legacyMigrationVersion/.test(QQ),
  "it moved six sections to a second path on every restore and save");

check("no code path reads or writes _legacyRemovedSections",
  !/_legacyRemovedSections/.test(QQ) && !/_legacyRemovedSections/.test(CORE),
  "a compatibility read is a second location for a value to live at");

const gsd = fnBody(QQ, "function getSectionData(");
check("getSectionData reads the canonical top-level key only",
  gsd !== "" && /questionnaire\[id\]/.test(gsd) && !/_legacy/.test(gsd));

check("the narrator walk has no dependency on a questionnaire section list",
  !/MINIMAL_SECTIONS|window\.SECTIONS/.test(LOOP),
  "session-loop.js uses its own fixed personal-field list; that was always what ran");

check("the walk's personal fields still mirror the questionnaire's",
  (() => {
    const body = fnBody(LOOP, "function _findNextEmptyPersonalField(");
    const loopFields = (body.match(/id:\s*"(\w+)"/g) || []).map((m) => m.replace(/id:\s*"/, "").slice(0, -1));
    const sec = QQ.slice(QQ.indexOf('id: "personal"'), QQ.indexOf('id: "parents"'));
    return loopFields.length >= 6 && loopFields.every((f) => sec.indexOf(`id: "${f}"`) !== -1);
  })(),
  "if the questionnaire renames a personal field, the narrator walk must follow");

/* MUTATIONS THAT MUST BREAK THIS SUITE — verified 2026-09-19 via LV_BBQQ_JS / LV_LOOP_JS:
     1. a second definition reintroduced (FULL_SECTIONS)    -> 1 check fails
     2. the flag reader reintroduced                        -> 1
     3. getSectionData given a legacy fallback again        -> 2
     4. the walk reads a questionnaire global               -> 1
   Counts are observed, below, not predicted. */

console.log(failures === 0 ? "\n  all checks passed\n" : `\n  ${failures} FAILED\n`);
process.exit(failures === 0 ? 0 : 1);
