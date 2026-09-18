/* Content detection, conflict scope, and honest save reporting.

   BUG-BIO-QUESTIONNAIRE-NEW-NARRATOR-SAVE-LOCK-01
   BUG-BIO-QUESTIONNAIRE-SILENT-SAVE-FAILURE-01

   WHAT HAPPENED, 2026-09-17, in a live browser

     A disposable narrator was created to rehearse entering a real person's
     biography. Hydration reached "server" correctly at 16:40:16. Two seconds
     later a second restore moved it to "conflict" — four minutes before the
     operator typed anything. Every save from then on was refused, and the UI
     said nothing at all. Six typed values lived only in localStorage.

   THE FIRST DEFECT — detection

     The conflict branch asked _hasAnyValue(bb.questionnaire), a SHALLOW
     helper:

         Object.keys(obj).some(k => obj[k] && String(obj[k]).trim() !== "")

     String({}) is "[object Object]", a non-empty string. So any section key
     counted as operator content, and hydration itself creates section keys:

         {}                             -> false
         { personal: {} }               -> TRUE
         { personal: { fullName: "" } } -> TRUE

     Every narrator with no server questionnaire was therefore holding "a
     draft with content" before a keystroke, and was locked out of saving.

     The identity migration's bookkeeping compounded it: _legacyMigrationVersion
     is a plain string, so it too read as biography.

   THE SECOND DEFECT — reporting, independent of the first

     The PUT was fire-and-forget. Nothing returned to the caller on success,
     refusal, 409, or a dead server. _saveSection re-rendered regardless, and
     silence read as success.

   WHAT IS NOT WEAKENED

     The conflict guard exists because on 2026-09-15 a draft outlived a full
     database erasure and restore — narrator ids survive export verbatim, so
     the key lorevox_qq_draft_<pid> came back pointing at erased data. That
     draft held REAL ANSWERS. It still trips the guard. Check 4 below is the
     one that must never be "fixed" into passing by loosening the rule.

   Run:  node tests/test_questionnaire_save_outcome.js
*/

"use strict";

const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");

const CORE_PATH = process.env.LV_BBCORE_JS || path.join(ROOT, "ui/js/bio-builder-core.js");
const QQ_PATH   = process.env.LV_BBQQ_JS   || path.join(ROOT, "ui/js/bio-builder-questionnaire.js");
const CORE = fs.readFileSync(CORE_PATH, "utf8");
const QQ   = fs.readFileSync(QQ_PATH, "utf8");

let failures = 0;
const check = (name, cond, detail) => {
  if (cond) console.log(`  ok    ${name}`);
  else { failures++; console.log(`  FAIL  ${name}\n        ${detail || ""}`); }
};

/* Take a whole function by matching braces.

   Third time in this work that a proximity-based source slice has reported
   failures against CORRECT code. Brace matching, once, reused. A test that
   fails on working code invites someone to break the code to satisfy it. */
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

/* Lift _hasOperatorContent + _isBookkeepingKey out of the module and run
   them for real. Asserting on source text would only prove the words are
   present; these four cases are the actual behaviour that broke. */
function loadContentFns() {
  const a = fnBody(CORE, "function _isBookkeepingKey(");
  const b = fnBody(CORE, "function _hasOperatorContent(");
  if (!a || !b) return null;
  // eslint-disable-next-line no-new-func
  return new Function(`${a}\n${b}\nreturn { _isBookkeepingKey, _hasOperatorContent };`)();
}

console.log("\nquestionnaire save outcome + content detection\n");

const C = loadContentFns();
check("_hasOperatorContent and _isBookkeepingKey are defined", !!C,
  "the conflict branch has nothing correct to ask");

if (C) {
  const has = C._hasOperatorContent;

  const MARKERS = {
    _legacyMigrationVersion: "WO-INTAKE-IDENTITY-01",
    _legacyRemovedSections: { _version: "WO-INTAKE-IDENTITY-01", _capturedAt: "2026-09-17T21:44:19.738Z" }
  };
  const BLANK = { personal: { fullName: "", preferredName: "", dateOfBirth: "", placeOfBirth: "" } };
  const REAL  = { personal: { fullName: "Thorvald Lindqvist", dateOfBirth: "1934-06-15" } };

  /* ── the four cases named in the repair order ───────────────────────── */

  check("1. a blank form is NOT content",
    has(BLANK) === false,
    "this is the shape hydration creates; calling it content locks every " +
    "new narrator out of saving");

  check("2. a blank form PLUS migration markers is NOT content",
    has(Object.assign({}, BLANK, MARKERS)) === false,
    "_legacyMigrationVersion is the program's own bookkeeping, not biography");

  check("3. markers PLUS one real answer IS content",
    has(Object.assign({}, BLANK, MARKERS, REAL)) === true,
    "ignoring bookkeeping must not make real answers invisible");

  check("4. a draft of REAL answers is still content (erasure guard intact)",
    has(REAL) === true,
    "THE 2026-09-15 CASE. A draft that outlived a database erasure holds " +
    "real answers; it must still refuse to save silently over an empty " +
    "server. Never loosen this to make another check pass.");

  /* ── the specific shapes observed live ──────────────────────────────── */

  check("an empty section object alone is not content",
    has({ personal: {} }) === false);

  check("the bare migration marker string is not content",
    has({ _legacyMigrationVersion: "WO-INTAKE-IDENTITY-01" }) === false);

  check("nested real answers are found",
    has({ parents: [{ name: "" }, { name: "Ingrid" }] }) === true);

  check("nested blanks are not content",
    has({ parents: [{ name: "", birthPlace: "" }] }) === false);

  check("a repeated-entry array of empty objects is not content",
    has({ parents: [{}, {}] }) === false);

  check("zero and false are content, not emptiness",
    has({ facts: { siblings: 0 } }) === true && has({ facts: { living: false } }) === true,
    "a numeric answer of 0 is an answer");

  check("bookkeeping keys are identified by a leading underscore",
    C._isBookkeepingKey("_legacyMigrationVersion") === true &&
    C._isBookkeepingKey("personal") === false);
}

/* ── the conflict branch asks the DEEP function ───────────────────────── */

const backend = fnBody(CORE, "function _restoreQuestionnaireFromBackend(");
check("the conflict branch calls _hasOperatorContent, not _hasAnyValue",
  /_hasOperatorContent\(cur\)/.test(backend) && !/_hasAnyValue\(cur\)/.test(backend),
  "_hasAnyValue is shallow; String({}) is truthy; that is the whole bug");

check("the conflict state still exists and can still be entered",
  /_setQqHydration\(\s*"conflict"/.test(backend),
  "the erasure guard must survive this repair");

/* ── hydration settle: the save must not race the read it started ─────── */

check("a hydration settle gate exists",
  /function _qqHydrationSettled\(/.test(CORE) && /function _qqMarkSettled\(/.test(CORE));

check("a new restore opens a FRESH settle gate",
  /_qqResetSettle\(pid\)/.test(fnBody(CORE, "function _restoreQuestionnaire(")),
  "otherwise a save waits on a stale resolved promise from an earlier read");

/* Every exit from the backend restore must release the gate, or a save that
   awaits it hangs forever with the operator's work unsaved and no message. */
const settleCount = (backend.match(/_qqMarkSettled\(/g) || []).length;
check(`every exit from the backend restore settles the gate (${settleCount} call sites)`,
  settleCount >= 7,
  "an unreleased gate turns a refusal into a silent hang, which is worse");

check("the GET failure path settles too",
  /\.catch\(function \(e\) \{[\s\S]*?_qqMarkSettled/.test(backend),
  "a dead server must produce a refusal message, not a hang");

/* ── the save reports a real outcome ──────────────────────────────────── */

const persistQq = fnBody(CORE, "function _persistQuestionnaire(");
check("_persistQuestionnaire exists and awaits hydration before deciding",
  persistQq && /_qqHydrationSettled\(pid\)\.then/.test(persistQq),
  "reading hydration synchronously races the GET _saveSection just started — " +
  "that is why the first save on a new narrator was always refused");

check("the PUT response is inspected rather than discarded",
  /r\.status === 409/.test(persistQq) && /if \(!r\.ok\)/.test(persistQq),
  "the old code was fetch(...).catch(log) — a 409 or a 500 was indistinguishable " +
  "from success");

check("a 409 is reported as a conflict, distinctly",
  /outcome: "conflict"/.test(persistQq));

check("a network failure is reported, distinctly",
  /outcome: "network"/.test(persistQq));

check("only an ok response yields saved:true",
  (persistQq.match(/saved: true/g) || []).length === 1 &&
  /ok: true, outcome: "saved", saved: true/.test(persistQq),
  "exactly one branch may claim a save, and it is the one after !r.ok returned");

check("the draft is written before the PUT is attempted",
  /_writeQqDraft\(pid, qq\)/.test(fnBody(CORE, "function _persistDrafts(")),
  "the operator's typing must survive every failure path");

/* ── the UI surfaces it ───────────────────────────────────────────────── */

const report = fnBody(QQ, "function _reportSaveOutcome(");
check("_reportSaveOutcome exists", !!report);

check("the save path calls it",
  /_reportSaveOutcome\(section, pid\)/.test(fnBody(QQ, "function _saveSection(")),
  "a save that cannot fail visibly is not a save");

check("success is shown only when the outcome says ok",
  /if \(res\.ok\)/.test(report),
  "never render 'saved' without server confirmation");

check("the failure banner does NOT auto-dismiss",
  (() => {
    const i = report.indexOf("} else {");
    return i !== -1 && !/setTimeout/.test(report.slice(i));
  })(),
  "a banner that disappears can be missed, and being missed IS the defect");

check("the failure banner tells the operator where their work is",
  /still in this browser/.test(report),
  "'not saved' without 'and here is where it went' invites retyping from memory");

/* ── MUTATIONS THAT MUST BREAK THIS SUITE ───────────────────────────────
   Verified 2026-09-17 via LV_BBCORE_JS / LV_BBQQ_JS against mutated copies:

     1. _hasOperatorContent stringifies instead of recursing
        (back to the shallow bug)                          -> 6 checks fail
     2. the bookkeeping skip removed                        -> 2 checks fail
     3. conflict branch restored to _hasAnyValue(cur)       -> 1 check  fails
     4. _persistQuestionnaire reads _qqHydration directly
        instead of awaiting the settle gate                 -> 1 check  fails
     5. the PUT returns to fire-and-forget                  -> 5 checks fail
     6. the failure banner given a setTimeout dismiss       -> 1 check  fails
     7. _qqMarkSettled removed from the .catch              -> 1 check  fails

   Counts are those observed by the run that verified them, not predictions.
   Mutation 3 is the one that matters most: it is the exact line that locked
   a live narrator, and a suite that still passes with it reverted is not
   protecting anything.
*/

console.log(failures === 0 ? "\n  all checks passed\n" : `\n  ${failures} FAILED\n`);
process.exit(failures === 0 ? 0 : 1);
