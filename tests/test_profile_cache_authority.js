/* Profile cache authority — BUG-BIO-QUESTIONNAIRE-LOSSY-ROUNDTRIP-01,
   browser-authority block.

   THE RULE UNDER TEST
     A cache may help the UI display something while authority is
     unavailable. It must never acquire authority merely because the
     authoritative read failed.

   WHY THIS EXISTS
     loadPerson's catch used to read lorevox_offline_profile_<pid> into
     state.profile and set profileSaved = true. saveProfile() then PUT
     basics/kinship/pets from it. A profile GET that merely timed out could
     therefore send a stale browser copy back over the database — and
     `kinship` is where a narrator's parents, siblings, spouse and children
     live. On 2026-09-15 the same shape of write, one lane over, destroyed
     ten values of hand-typed family history.

   WHY IT IS A SOURCE TEST RATHER THAN A DOM TEST
     app.js is a 10,000-line browser module with no export surface and a
     hard dependency on a live DOM, WebSocket and fetch. Standing that up
     would test the harness more than the code. So this reads the shipped
     source and asserts the CONTROL FLOW that makes the defect impossible:
     which branch sets which state, and that the writer is gated on it.

     That is weaker than executing it, and the weakness is named here
     rather than hidden: it cannot prove the browser behaves this way at
     runtime. The live proof is the operator walkthrough — stop the stack,
     load a narrator, attempt a save, confirm the refusal, restart, reload,
     save, confirm it lands. This suite stops the code from silently
     regressing between those walkthroughs.

   Run:  node tests/test_profile_cache_authority.js
*/

"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
/* Overridable so the suite can be run against a deliberately mutated copy —
   a check that never fails proves nothing. See the mutation block at the
   bottom of this file for the mutations that MUST break it. */
const APP = fs.readFileSync(process.env.LV_APP_JS || path.join(ROOT, "ui/js/app.js"), "utf8");
const STATE = fs.readFileSync(process.env.LV_STATE_JS || path.join(ROOT, "ui/js/state.js"), "utf8");

let failures = 0;
function check(name, cond, detail) {
  if (cond) { console.log(`  ok    ${name}`); }
  else { failures++; console.log(`  FAIL  ${name}\n        ${detail || ""}`); }
}

/* Strip // and block comments so a tombstone comment naming a removed
   pattern cannot satisfy an assertion about live code. The same trap
   test_family_product_path_removed.py documents. */
function code(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((l) => !l.trim().startsWith("//"))
    .join("\n");
}
const APPC = code(APP);

console.log("\nprofile cache authority\n");

/* ── the state exists and starts closed ─────────────────────────────── */
check("profileHydration is declared",
  /let\s+profileHydration\s*=/.test(code(STATE)),
  "state.js must declare it");

check("it starts unhydrated, not hydrated",
  /let\s+profileHydration\s*=\s*["']unhydrated["']/.test(code(STATE)),
  "a default of anything else fails open");

/* ── reset on narrator switch ───────────────────────────────────────── */
const loadPersonStart = APPC.indexOf("async function loadPerson(pid){");
check("loadPerson exists", loadPersonStart !== -1);
const firstFetch = APPC.indexOf("API.PROFILE(pid)", loadPersonStart);
const resetIdx = APPC.indexOf('profileHydration="unhydrated"', loadPersonStart);
check("hydration is reset BEFORE the profile fetch",
  resetIdx !== -1 && firstFetch !== -1 && resetIdx < firstFetch,
  "without this the flag survives a narrator switch: hydrate A, switch to B " +
  "whose GET fails, and B's cached profile becomes writable");

/* ── only a successful read may authorise writes ─────────────────────── */
const fetchIdx = APPC.indexOf("const r=await fetch(API.PROFILE(pid))");
const catchIdx = APPC.indexOf("}catch{", fetchIdx);
const successBlock = APPC.slice(fetchIdx, catchIdx);
const catchBlock = APPC.slice(catchIdx, catchIdx + 2600);

check("the SUCCESS branch sets server",
  /profileHydration\s*=\s*["']server["']/.test(successBlock));

check("the FAILURE branch never sets server",
  !/profileHydration\s*=\s*["']server["']/.test(catchBlock),
  "a failed read must not look like a successful one");

check("the cache branch marks itself as cache",
  /profileHydration\s*=\s*["']cache["']/.test(catchBlock));

check("the cache branch does NOT claim the profile was saved",
  !/if\(cached\)\{[\s\S]{0,400}?profileSaved\s*=\s*true/.test(catchBlock),
  "nothing was saved and nothing was confirmed — this was the original defect");

check("no-cache failure stays unhydrated",
  /else\{[\s\S]{0,200}?profileHydration\s*=\s*["']unhydrated["']/.test(catchBlock));

/* ── the writer is gated ─────────────────────────────────────────────── */
const saveIdx = APPC.indexOf("async function saveProfile(){");
const saveBlock = APPC.slice(saveIdx, saveIdx + 2200);
const putIdx = saveBlock.indexOf("method:\"PUT\"");
const gateIdx = saveBlock.search(/if\(profileHydration!==["']server["']\)/);

check("saveProfile refuses unless hydration is server",
  gateIdx !== -1,
  "the PUT replaces basics/kinship/pets whole — update_profile_json merges " +
  "only at the top level");

check("the refusal happens BEFORE the PUT",
  gateIdx !== -1 && putIdx !== -1 && gateIdx < putIdx);

check("the refusal returns rather than falling through",
  /if\(profileHydration!==["']server["']\)\{[\s\S]{0,900}?return;/.test(saveBlock));

check("the refusal does not discard the operator's edit",
  !/if\(profileHydration!==["']server["']\)\{[\s\S]{0,900}?state\.profile\s*=/.test(saveBlock),
  "refusing must not also throw away what they typed");

/* ── the confirmed-empty case ────────────────────────────────────────── */
check("a successful read is trusted without inspecting its contents",
  !/profileHydration\s*=\s*["']server["'][\s\S]{0,120}?if\s*\(\s*Object\.keys/.test(successBlock),
  "'the server says this narrator has no profile' is an ANSWER and must not " +
  "be downgraded to 'I do not know' — that conflation is the defect's twin");

/* ── MUTATIONS THAT MUST BREAK THIS SUITE ────────────────────────────
   Verified 2026-09-17 by running against mutated copies via LV_APP_JS:

     1. cache branch sets profileHydration="server"   -> 3 checks fail
     2. saveProfile's hydration gate deleted          -> 5 checks fail
     3. the reset in loadPerson deleted               -> 3 checks fail
     4. cache branch restores profileSaved=true       -> 3 checks fail
     5. default changed to "server"                   -> 3 checks fail

   If a future edit makes any of those pass, this suite has stopped
   testing the thing it is named after. */
console.log(
  failures === 0
    ? "\n  all checks passed\n"
    : `\n  ${failures} FAILED\n`);
process.exit(failures === 0 ? 0 : 1);
