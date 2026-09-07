#!/usr/bin/env node
/**
 * Phase 6 turn-set preflight — WHICH TURNS EVEN REACH THE LLM.
 *
 *   cd /mnt/c/Users/chris/hornelore
 *   node scripts/ui/phase6_turn_route_preflight.js
 *
 * WHY THIS RUNS BEFORE A SINGLE LIVE TURN
 * =======================================
 *
 * `turn_mode` is assigned in the BROWSER, by `lvRouteTurn` at
 * `ui/js/app.js:2704`, and a turn routed to `correction` or `age_recall`
 * takes a DETERMINISTIC path — no LLM generation at all. A conversational
 * baseline built from turns that were quietly deterministic would not be
 * a measurement of Lori; it would be a measurement of a regex.
 *
 * That is not a hypothetical. `CLAUDE.md` already records a run lost to
 * exactly this: Stefi's "cannot reach the correction branch" claim was
 * wrong because the server classifier was read while the BROWSER was the
 * thing assigning the mode, and its detector fires on the words
 * "not the".
 *
 * The detector at `app.js:2600` is still broad:
 *
 *     \b(?:not|wasn't|weren't|didn't|...)\s+
 *     (?:\d+|that|him|her|them|me|my|the|a|an|in|on)\b
 *
 * so ordinary narration — "it wasn't the same after that", "not a big
 * house", "not that it matters" — routes as a CORRECTION. Every turn in
 * the Phase 6 set is therefore checked against the SHIPPED functions
 * before the set is used.
 *
 * IT LOADS THE REAL SOURCE. The detector block is read out of `app.js`
 * and evaluated. Nothing here reimplements the regexes — a copy would
 * drift from the shipped one, and a preflight that disagrees with the
 * product is worse than none.
 *
 * EXPECTATION: exactly ONE turn (the deliberate correction) routes to
 * `correction`; every other turn routes to `interview`. Any other result
 * is a REFUSAL — fix the wording, do not run the session.
 */
"use strict";

const fs = require("fs");
const path = require("path");

const REPO = path.resolve(__dirname, "..", "..");
const APP = path.join(REPO, "ui", "js", "app.js");

// The turn router and its four detectors, lifted from the shipped file.
const FIRST_LINE = 2526;   // const TURN_INTERVIEW
const LAST_LINE = 2719;    // closing brace of lvRouteTurn

const SRC = fs.readFileSync(APP, "utf8").split("\n");
const BLOCK = SRC.slice(FIRST_LINE - 1, LAST_LINE).join("\n");

// Pin the extraction to the real anchors. If app.js shifts, this refuses
// instead of silently evaluating some other part of the file.
const ANCHORS = [
  ["const TURN_INTERVIEW", /const\s+TURN_INTERVIEW\s*=/],
  ["_looksLikeStrongCorrection", /function\s+_looksLikeStrongCorrection\s*\(/],
  ["_looksLikeMemoryEchoRequest", /function\s+_looksLikeMemoryEchoRequest\s*\(/],
  ["_looksLikeAgeQuestion", /function\s+_looksLikeAgeQuestion\s*\(/],
  ["lvRouteTurn", /function\s+lvRouteTurn\s*\(/],
];
let anchorFailure = null;
for (const [name, re] of ANCHORS) {
  if (!re.test(BLOCK)) anchorFailure = name;
}
if (anchorFailure) {
  console.error(
    `REFUSING: lines ${FIRST_LINE}-${LAST_LINE} of app.js no longer ` +
    `contain ${anchorFailure}. The file moved; re-pin the range rather ` +
    `than trusting this preflight.`);
  process.exit(2);
}

// `lvRouteTurn` reads `state?.session?.lastTurnMode` for the weak
// post-echo branch. A fresh conversational turn has no memory_echo
// before it, which is the condition this baseline runs under.
let state = { session: { lastTurnMode: null } };
const scope = {};
// eslint-disable-next-line no-eval
const routeTurn = eval(`${BLOCK}\n;lvRouteTurn;`);

/** The Phase 6 turn set. Category names are Chris's. */
const TURNS = [
  ["childhood / family",
   "My brother Dennis used to walk me to school through the cemetery " +
   "because it was the fast way."],
  ["place / move",
   "We left Currier Street the summer I turned eleven and moved out " +
   "toward Websterville."],
  ["daily routine",
   "These days I'm up before Warren. I make the coffee and do the " +
   "crossword while the house is quiet."],
  ["work",
   "At the practice I ended up building the schedule for both dentists. " +
   "Nobody ever asked me to. I just started doing it."],
  ["emotionally meaningful memory",
   "My father came home from the quarry one afternoon and told us his " +
   "hands had stopped working right. He was fifty-two."],
  ["correction (DELIBERATE — must route to correction)",
   "Actually, he was fifty-four, not fifty-two. I keep getting that wrong."],
  ["multiple possible threads",
   "Claire moved out to California the same year we lost the house on " +
   "Berlin Street."],
  ["detail Lori should NOT over-interpret",
   "There was a green glass dish on the hall table. I have no idea why " +
   "I remember it."],
  ["place / leisure",
   "We used to drive up to Groton Pond on Sundays in the summer, all " +
   "four of us in the wagon."],
  ["resists date pressure",
   "I couldn't tell you what year we got the camp. Somewhere in the " +
   "seventies."],
];

const EXPECT_CORRECTION = 5;   // zero-based index of the deliberate one

let failures = 0;
console.log(`Routing ${TURNS.length} turns through the shipped ` +
            `lvRouteTurn (app.js:${FIRST_LINE}-${LAST_LINE})\n`);
TURNS.forEach(([category, text], i) => {
  const mode = routeTurn(text);
  const want = i === EXPECT_CORRECTION ? "correction" : "interview";
  const ok = mode === want;
  if (!ok) failures += 1;
  console.log(`${ok ? "  ok  " : "  FAIL"}  T${i + 1}  ${mode.padEnd(12)}` +
              ` ${category}`);
  if (!ok) {
    console.log(`        wanted ${want}`);
    console.log(`        "${text}"`);
  }
});

// ── HAZARD WITNESS ──────────────────────────────────────────────────
//
// The turns above were WORDED AROUND app.js:2600. These five show what
// that wording avoided: four are ordinary narration and route as
// CORRECTION anyway, so they would never reach the model.
//
// This block is a characterization, not a pass/fail. If the detector is
// ever narrowed, these stop routing to `correction` and the note below
// says so — which is the outcome we would want, recorded rather than
// discovered by surprise.
console.log("");
console.log("Hazard witness — ordinary narration vs app.js:2600");
const WITNESS = [
  ["a passing aside",
   "There was a green glass dish on the hall table. I do not know why " +
   "I remember it, not that it matters."],
  ["a plain description",
   "It was not a big house, but we managed."],
  ["a sentence about loss",
   "It wasn't the same after that."],
  ["the same turn, reworded to survive",
   "We used to drive up to Groton Pond on Sundays."],
];
let caught = 0;
for (const [label, text] of WITNESS) {
  const mode = routeTurn(text);
  if (mode === "correction") caught += 1;
  console.log(`  ${mode.padEnd(12)} ${label}`);
}
console.log(`  -> ${caught} of ${WITNESS.length} route deterministically ` +
            `and never reach the model.`);
if (caught === 0) {
  console.log("  NOTE: none of them did. The browser correction detector " +
              "has been narrowed since this witness was written — update " +
              "it, and revisit whether the Phase 6 turns still need to be " +
              "worded around it.");
}

console.log("");
if (failures) {
  console.log(`${failures} turn(s) route to a mode the baseline did not ` +
              `intend. A turn that routes deterministically never reaches ` +
              `the model, so it cannot be evidence about Lori. Reword and ` +
              `rerun — do NOT start the session.`);
  process.exit(1);
}
console.log("All 10 turns route as intended: nine reach the model, one " +
            "exercises the correction path on purpose.");
