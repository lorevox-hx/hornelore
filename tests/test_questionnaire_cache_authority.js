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

/* ── reset on narrator switch ───────────────────────────────────────── */
const restoreIdx = CODE.indexOf("function _restoreQuestionnaire(pid)");
check("_restoreQuestionnaire exists", restoreIdx !== -1);
const restoreBlock = CODE.slice(restoreIdx, restoreIdx + 1800);
const resetIdx = restoreBlock.indexOf('_setQqHydration("unhydrated"');
const backendCallIdx = restoreBlock.indexOf("_restoreQuestionnaireFromBackend(pid)");
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
const beIdx = CODE.indexOf("function _restoreQuestionnaireFromBackend(pid)");
const beBlock = CODE.slice(beIdx, beIdx + 5200);

/* The empty-server branch, taken as a whole rather than by proximity — the
   conflict arm carries a long console.warn, and an earlier version of this
   assertion used a fixed character window that the warning pushed the `else`
   out of. It failed against correct code, which is the worse kind of test
   failure: it invites someone to "fix" working behaviour. */
const emptyIdx = beBlock.indexOf("if (serverEmpty) {");
const emptyBlock = emptyIdx === -1 ? "" : beBlock.slice(emptyIdx, emptyIdx + 2000);

check("the empty-server branch exists and is explicit", emptyIdx !== -1,
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
  /bb\.questionnaire\s*=\s*sections;[\s\S]{0,300}?_setQqHydration\("server"/.test(beBlock));

/* ── the writer is gated ────────────────────────────────────────────── */
const persistIdx = CODE.indexOf("function _persistDrafts(pid)");
const persistBlock = CODE.slice(persistIdx, persistIdx + 5000);
const gateIdx = persistBlock.search(/_qqHydration\s*!==\s*["']server["']/);
const putIdx = persistBlock.indexOf("API.BB_QQ_PUT");

check("_persistDrafts refuses the PUT unless hydration is server",
  gateIdx !== -1);

check("the refusal is checked BEFORE the PUT is reached",
  gateIdx !== -1 && putIdx !== -1 && gateIdx < putIdx);

check("a refused save still keeps the draft in localStorage",
  /_qqHydration\s*!==\s*["']server["'][\s\S]{0,1400}?localStorage\.setItem\(_LS_QQ_PREFIX/.test(persistBlock),
  "refusing to transmit must not also discard what the operator typed");

/* ── MUTATIONS THAT MUST BREAK THIS SUITE ───────────────────────────────
   Verified 2026-09-17 against mutated copies via LV_BBCORE_JS:

     1. the _persistDrafts gate disabled            -> 4 checks fail
     2. the cache path claiming "server"            -> 3 checks fail
     3. the default changed to "server"             -> 2 checks fail
     4. "conflict" downgraded to "server"           -> 2 checks fail
     5. the reset-on-switch removed                 -> 2 checks fail
     6. the empty-server branch bypassed            -> 4 checks fail

   If a future edit makes any of these pass, this suite has stopped testing
   the thing it is named after. */

console.log(failures === 0
  ? "\n  all checks passed\n"
  : `\n  ${failures} FAILED\n`);
process.exit(failures === 0 ? 0 : 1);
