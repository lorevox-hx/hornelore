/* Questionnaire cache authority — BUG-BIO-QUESTIONNAIRE-LOSSY-ROUNDTRIP-01,
   browser-authority block. Companion to test_profile_cache_authority.js.

   THE RULE UNDER TEST
     A cache may help the UI display something while authority is
     unavailable. It must never acquire authority merely because the
     authoritative read failed.

   WHY THIS EXISTS
     _restoreQuestionnaire starts the backend fetch WITHOUT awaiting it and
     then returns the localStorage draft, so bb.questionnaire is the
     browser's copy for the whole in-flight window. Three paths left it
     there permanently: a failed fetch (the .catch only logged), an empty
     server response (ignored by an Object.keys(q).length > 0 guard), and a
     failed PUT (localStorage was written regardless). _persistDrafts then
     sent that copy to the server.

     On 2026-09-15 this browser held a damaged 7,046-byte draft of Janice's
     questionnaire, leaf-for-leaf identical to the row a bad save had just
     produced. Had the database been restored and the UI opened, it would
     have gone straight back over the repair.

   THE FOURTH STATE
     "conflict" — the server confirms EMPTY while a local draft holds
     content — is not defensive padding. That same draft outlived a full
     erase-and-restore of the database, because the key is
     lorevox_qq_draft_<pid> and narrator ids survive export/restore
     verbatim. Auto-adopting a draft in that situation would resurrect
     erased data under the name of an ordinary save.

   WHY A SOURCE TEST
     Same reasoning as the profile suite, and the same admission: this
     reads the shipped source and asserts control flow. It cannot prove
     the browser behaves this way at runtime. The live proof is the
     operator walkthrough. This stops silent regression between them.

   Run:  node tests/test_questionnaire_cache_authority.js
*/

"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
/* Overridable so the suite can be run against a deliberately mutated copy. */
const SRC = fs.readFileSync(
  process.env.LV_BBCORE_JS || path.join(ROOT, "ui/js/bio-builder-core.js"), "utf8");

let failures = 0;
function check(name, cond, detail) {
  if (cond) console.log(`  ok    ${name}`);
  else { failures++; console.log(`  FAIL  ${name}\n        ${detail || ""}`); }
}

/* Strip comments so a tombstone naming a removed pattern cannot satisfy an
   assertion about live code. */
const CODE = SRC.replace(/\/\*[\s\S]*?\*\//g, "")
  .split("\n").filter((l) => !l.trim().startsWith("//")).join("\n");

console.log("\nquestionnaire cache authority\n");

/* ── the state exists and starts closed ─────────────────────────────── */
check("_qqHydration is declared",
  /var\s+_qqHydration\s*=/.test(CODE));

check("it starts unhydrated, not hydrated",
  /var\s+_qqHydration\s*=\s*["']unhydrated["']/.test(CODE),
  "any other default fails open");

check("the state is readable from outside the module",
  /_qqHydrationState/.test(CODE),
  "an operator must be able to ask why a save was refused");

/* ── reset on narrator switch ─────────────────────────────────────────

   These used FIXED CHARACTER WINDOWS — slice(idx, idx + 1800), + 5200,
   + 2000 — and a literal "_restoreQuestionnaireFromBackend(pid)" that stopped
   matching when the function took a second parameter. Adding comments and a
   token argument pushed the code these assertions look for outside their
   windows, and five checks failed against CORRECT behaviour.

   The block above this one already recorded that a fixed window had lied
   once, and then chose a different fixed window. That is the whole lesson
   missed: the problem is not the size, it is measuring source by distance.
   Brace-match, everywhere, and match signatures by name only. */
check("_restoreQuestionnaire exists",
  CODE.indexOf("function _restoreQuestionnaire(pid)") !== -1);
const restoreBlock = fnBody(CODE, "function _restoreQuestionnaire(");
const resetIdx = restoreBlock.indexOf('_setQqHydration("unhydrated"');
const backendCallIdx = restoreBlock.search(/_restoreQuestionnaireFromBackend\(/);
check("hydration resets BEFORE the backend call",
  resetIdx !== -1 && backendCallIdx !== -1 && resetIdx < backendCallIdx,
  "otherwise the flag survives a narrator switch and authorises the NEXT " +
  "narrator's cached draft");

/* ── the cache path does not claim authority ────────────────────────── */
check("the localStorage path marks itself as cache",
  /_setQqHydration\("cache"/.test(restoreBlock));

check("the localStorage path never claims server",
  !/_setQqHydration\("server"/.test(restoreBlock),
  "reading a draft is not hearing from the server");

/* ── the backend response drives server / conflict ──────────────────── */
const beBlock = fnBody(CODE, "function _restoreQuestionnaireFromBackend(");
const emptyBlock = fnBody(beBlock, "if (serverEmpty) {");

check("the empty-server branch exists and is explicit", emptyBlock !== "",
  "'the server says this narrator has nothing' needs its own branch — " +
  "falling through would make it indistinguishable from a failed read");

check("a confirmed-EMPTY server still counts as hydrated",
  /_setQqHydration\("server"/.test(emptyBlock),
  "'the server says this narrator has nothing' is an ANSWER; conflating it " +
  "with 'I could not ask' is the same defect wearing a different hat");

check("empty server + local content raises conflict rather than adopting",
  /_setQqHydration\("conflict"/.test(emptyBlock),
  "a draft can outlive an erasure; adopting it would resurrect erased data");

check("adopting the server document sets server",
  /bb\.questionnaire = sections;/.test(beBlock) &&
  /_setQqHydration\("server", "adopted the server document"\)/.test(beBlock),
  "the adopt path must record that it heard from the server");

/* The adopt is now conditional — BUG-BIO-QUESTIONNAIRE-GET-CLOBBERS-EDITS-01.
   An unconditional assignment replaced whatever was in memory, including
   edits typed while the GET was in flight. This check exists so nobody
   restores the unconditional form to make the assertion above simpler. */
check("adopting does NOT clobber uncommitted operator edits",
  /_qqDirty\[stampedPid\] && _hasOperatorContent\(bb\.questionnaire\)/.test(beBlock),
  "every real narrator already has a server document, so this branch runs on " +
  "every restore of a record that matters");

/* ── the writer is gated ──────────────────────────────────────────────

   BUG-BIO-QUESTIONNAIRE-SILENT-SAVE-FAILURE-01 moved the gate. It used to
   live inline in _persistDrafts, where the decision was made SYNCHRONOUSLY
   against a hydration state that the GET _saveSection had just started had
   not yet settled — so the first save on any new narrator was refused by a
   race. The gate now lives in _persistQuestionnaire, after awaiting the
   settle, and returns an outcome the UI is required to show.

   These three checks previously sliced 5000 characters from the front of
   _persistDrafts and searched the window. That is proximity slicing, which
   has produced false failures three times in this work; brace-match the
   functions instead and ask each one the question that belongs to it. The
   REQUIREMENT is unchanged: never transmit what we could not first read,
   and never discard the operator's typing when refusing. */
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

/* Match declarations by NAME, never by full signature.

   These named the whole parameter list. `_persistQuestionnaire(pid, qq)`
   gained a `ticket` argument and three checks failed against correct code —
   the same lesson as the fixed character windows above, one level up: any
   assertion that depends on source staying textually still will eventually
   report a failure that is not there. */
const persistBlock = fnBody(CODE, "function _persistDrafts(");
const putBlock     = fnBody(CODE, "function _persistQuestionnaire(");
const gateIdx = putBlock.search(/state\s*!==\s*["']server["']/);
const putIdx  = putBlock.indexOf("API.BB_QQ_PUT");

check("the save path refuses the PUT unless hydration is server",
  gateIdx !== -1,
  "the fail-closed rule must survive the move out of _persistDrafts");

check("the refusal is checked BEFORE the PUT is reached",
  gateIdx !== -1 && putIdx !== -1 && gateIdx < putIdx);

check("the gate reads a SETTLED hydration state, not a racing one",
  /_qqHydrationSettled\(pid\)\.then\(function \(state\)/.test(putBlock),
  "reading _qqHydration synchronously refused every first save on a new " +
  "narrator, because _saveSection restores immediately beforehand");

check("a refused save still keeps the draft in localStorage",
  /_writeQqDraft\(pid, qq\)/.test(persistBlock) &&
  persistBlock.indexOf("_writeQqDraft(pid, qq)") < persistBlock.indexOf("_persistQuestionnaire("),
  "refusing to transmit must not also discard what the operator typed — the " +
  "draft is now written BEFORE the PUT is attempted, so every failure path " +
  "keeps it");

/* ── MUTATIONS THAT MUST BREAK THIS SUITE ───────────────────────────────
   Verified 2026-09-17 against mutated copies via LV_BBCORE_JS:

     2. the cache path claiming "server"            -> 3 checks fail
     3. the default changed to "server"             -> 2 checks fail
     4. "conflict" downgraded to "server"           -> 2 checks fail
     5. the reset-on-switch removed                 -> 2 checks fail
     6. the empty-server branch bypassed            -> 4 checks fail

   Mutation 1 was "the _persistDrafts gate disabled -> 4 checks fail". The
   gate moved to _persistQuestionnaire in
   BUG-BIO-QUESTIONNAIRE-SILENT-SAVE-FAILURE-01, so it was re-run against the
   new location and re-counted rather than left as a stale prediction:

     1a. the hydration gate disabled (if (false))    -> 2 checks fail
     1b. the draft no longer written before the PUT  -> 1 check  fails
     1c. the gate reading a racing state instead of
         the settled one                             -> 1 check  fails

   Counts are those observed by the run that verified them. If a future edit
   makes any of these pass, this suite has stopped testing the thing it is
   named after. */

console.log(failures === 0
  ? "\n  all checks passed\n"
  : `\n  ${failures} FAILED\n`);
process.exit(failures === 0 ? 0 : 1);
