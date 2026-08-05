#!/usr/bin/env node
/**
 * LLR-20 / WO-LEAN-LORI-RUNTIME-01 Phase 1D — the safety latch has an exit.
 *
 * WHY A FUNCTIONAL HARNESS AND NOT A SOURCE SCAN
 * ----------------------------------------------
 * The property under test is a SEQUENCE property: what happens to the
 * posture across four consecutive narrator turns. A source scan can see
 * that a decay counter exists; it cannot see that the counter resets on
 * a genuine re-trigger, that the objection guard is unreachable on a
 * first detection, or that three quiet turns actually release the latch.
 * Those are the things that were wrong, so those are the things this
 * drives.
 *
 * It extracts the real functions from ui/hornelore1.0.html rather than
 * restating them, so it cannot drift from the shipped code. Runs with
 * plain node, no dependencies, no browser, no stack, no TTS.
 *
 *     node scripts/ui/run_safety_latch_exit_check.js
 *
 * Exit 0 = all checks pass. Exit 1 = a check failed.
 */
"use strict";

const fs = require("fs");
const path = require("path");

const REPO = path.resolve(__dirname, "..", "..");
const HTML = fs.readFileSync(path.join(REPO, "ui", "hornelore1.0.html"), "utf8");

// ── extract the real source of the pieces under test ──────────────────
function slice(startMarker, endMarker, label) {
  const a = HTML.indexOf(startMarker);
  if (a < 0) throw new Error(`could not find start of ${label}: ${startMarker}`);
  const b = HTML.indexOf(endMarker, a);
  if (b < 0) throw new Error(`could not find end of ${label}: ${endMarker}`);
  return HTML.slice(a, b);
}

const patternsSrc = slice("const _LV80_SAFETY_PATTERNS = [",
                          "function _lv80ScanSafety", "_LV80_SAFETY_PATTERNS");
const latchSrc = slice("const _LV80_SAFETY_MAX_CLEAR_TURNS",
                       "function _lv80InstallSafetyHook", "the latch block");
const scanSrc = slice("function _lv80ScanSafety(text) {",
                      "// ── LLR-20", "_lv80ScanSafety");

// Minimal stand-ins for the browser globals the extracted code touches.
// Deliberately dumb: this harness is about the latch, not about the badge.
const prelude = `
let _lv80SafetyModeActive = false;
let _lv80NonMemoirModeActive = false;
let _lv80InteractionMode = "life_story";
let _lv80IdleWasThinking = false;
const transitions = [];
function lv80ClearIdle() {}
function lv80UpdatePostureBadge() {}
function lv80LogModeTransition(from, to, why) { transitions.push({from, to, why}); }
function _lv80GetInteractionMode() {
  if (_lv80SafetyModeActive) return "safety";
  if (_lv80NonMemoirModeActive) return "companion";
  return _lv80InteractionMode;
}
`;

// The send-hook decision, transcribed as the ONE thing this harness does
// restate. It is four lines and reproducing them is safer than executing
// the whole 100KB inline script; a guard below pins them against the file
// so a divergence fails loudly instead of silently testing fiction.
const decide = `
function turn(text) {
  const safetyMatched = !!(text && _lv80ScanSafety(text));
  _lv80SafetyLatch.requestedThisTurn = safetyMatched;
  const objectingToTheAlarm =
    safetyMatched && _lv80SafetyModeActive && _lv80ScanSafetyObjection(text);
  const safetyTriggered = safetyMatched && !objectingToTheAlarm;
  if (safetyTriggered) {
    _lv80OnSafetyDetected();
    _lv80NonMemoirModeActive = false;
  } else if (text && _lv80SafetyModeActive) {
    _lv80SafetyNoteClearTurn(objectingToTheAlarm ? "objection" : "no_trigger");
  }
  return _lv80GetInteractionMode();
}
`;

const sandbox = {};
const runner = new Function(
  prelude + patternsSrc + scanSrc + latchSrc + decide +
  "return { turn, state: () => ({ active: _lv80SafetyModeActive, " +
  "latch: JSON.parse(JSON.stringify(_lv80SafetyLatch)), transitions }), " +
  "reset: () => { _lv80SafetyModeActive = false; " +
  "_lv80SafetyLatch = { active:false, clearTurns:0, requestedThisTurn:false, " +
  "reason:null, armedAtIso:null }; transitions.length = 0; }, " +
  "MAX: _LV80_SAFETY_MAX_CLEAR_TURNS };"
)();

let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log(`  PASS  ${name}`); }
  else { fail++; console.log(`  FAIL  ${name}${detail ? "  — " + detail : ""}`); }
}

console.log("LLR-20 — safety latch exit, driven as turn sequences\n");

// 1. Detection itself is unchanged.
runner.reset();
check("a real disclosure still arms safety mode",
      runner.turn("I don't want to live anymore") === "safety");

// 2. The false alarm Chris actually hit.
runner.reset();
check("a correction containing the word arms it (detection NOT weakened)",
      runner.turn("no, my uncle died by suicide in 1962, not my father") === "safety");

// 3. The objection guard: cannot suppress a FIRST detection.
runner.reset();
// NOTE the tense. `_lv80ScanSafety` matches "want to die", not "wanted
// to die" -- the first cut of this harness used the past tense, matched
// nothing, and reported a failure that was entirely its own. The phrase
// below genuinely trips BOTH the safety pattern and the objection
// pattern, which is what makes it a real test of precedence.
check("an objection alone, with no prior latch, STILL arms safety mode",
      runner.turn("I never said I want to die") === "safety",
      "the guard must be unreachable when the latch is cold");

// 4. Objecting to a live false alarm does not re-latch, and decays it.
runner.reset();
runner.turn("no, my uncle died by suicide in 1962");
const afterObjection = runner.turn("I never said I want to die, why did you bring that up");
check("objecting does not RESET the decay counter",
      runner.state().latch.clearTurns === 1,
      `clearTurns=${runner.state().latch.clearTurns}`);
check("requested vs effective is visible to the operator",
      runner.state().latch.requestedThisTurn === true && afterObjection === "safety",
      "requested should be true while the latch is merely being held");

// 5. Three quiet turns release it.
runner.reset();
runner.turn("my uncle died by suicide in 1962");
check("turn 1 after the alarm: still safety", runner.turn("he was a carpenter") === "safety");
check("turn 2 after the alarm: still safety", runner.turn("he had four children") === "safety");
const t3 = runner.turn("the funeral was in Bismarck");
check("turn 3 after the alarm: latch RELEASED", t3 === "life_story", `got ${t3}`);
check("the release is logged with a reason",
      runner.state().transitions.some(t => String(t.why).startsWith("safety_latch_")),
      JSON.stringify(runner.state().transitions));

// 6. A person who keeps disclosing keeps the posture. This is the one
//    that matters most: decay must not out-run genuine distress.
runner.reset();
runner.turn("I don't want to be here anymore");
runner.turn("nothing feels worth it");
check("a genuine re-trigger RESETS the counter",
      runner.turn("I still want to die") === "safety" &&
      runner.state().latch.clearTurns === 0,
      `clearTurns=${runner.state().latch.clearTurns}`);
runner.turn("I don't know");
runner.turn("maybe");
check("and the latch then holds through the following quiet turns",
      runner.state().active === true);

// 7. The harness is not testing fiction: its transcribed decision must
//    match the file. Compare against the real send hook's source.
const hook = HTML.slice(HTML.indexOf("const safetyMatched"),
                        HTML.indexOf("if (!safetyTriggered && nonMemoirPattern)"));
for (const needle of [
  "_lv80SafetyLatch.requestedThisTurn = safetyMatched",
  "safetyMatched && _lv80SafetyModeActive && _lv80ScanSafetyObjection(text)",
  "const safetyTriggered  = safetyMatched && !objectingToTheAlarm",
  "_lv80SafetyNoteClearTurn(",
]) {
  check(`the shipped hook still contains: ${needle.slice(0, 46)}…`,
        hook.includes(needle));
}

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail === 0 ? 0 : 1);
