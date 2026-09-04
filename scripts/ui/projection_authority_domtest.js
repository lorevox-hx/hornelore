/* projection_authority_domtest.js — the server's downgrade must bind the browser.
 *
 * WO-LORI-ARCHIVE-TO-MEMOIR-02 Phase 3 (2026-09-04).
 *
 * WHY THIS EXISTS. The server could return writeMode="suggest_only" +
 * needs_confirmation=true and the browser would still prefill the
 * questionnaire, because interview.js read `item.writeMode` and never passed
 * it on, and projection-sync.js re-derived authority from its own schema. The
 * API-level tests proved the response carried the downgrade; they stopped one
 * consumer short of proving the downgrade PROTECTED anything.
 *
 * Runs the SHIPPED modules under Node with a minimal window/state harness —
 * no Playwright, so it produces evidence in any environment rather than
 * skipping. A skipped guard is not a guard.
 *
 *   node scripts/ui/projection_authority_domtest.js
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..", "..");
const failures = [];
let checks = 0;

function ok(cond, label, detail) {
  checks++;
  if (!cond) failures.push(label + (detail ? "  — " + detail : ""));
}
function eq(actual, expected, label) {
  ok(actual === expected, label, "expected " + JSON.stringify(expected) +
     ", got " + JSON.stringify(actual));
}

/* ── harness ─────────────────────────────────────────────────────────────
   Only what projection-sync.js actually touches. Deliberately NOT a mock of
   the sync layer itself: the module under test is the shipped file. */
function newSandbox(schemaModes) {
  const sandbox = {
    console: { log() {}, warn() {}, error() {} },
    setTimeout, clearTimeout, Date, Set, Math, JSON, String, Array, Object,
    localStorage: {
      _d: {},
      getItem(k) { return this._d[k] === undefined ? null : this._d[k]; },
      setItem(k, v) { this._d[k] = String(v); },
      removeItem(k) { delete this._d[k]; }
    },
    fetch: () => Promise.resolve({ status: 200, json: () => Promise.resolve({}) }),
    state: {
      person_id: "p1",
      interviewProjection: { personId: "p1", fields: {}, syncLog: [] },
      bioBuilder: { questionnaire: {} }
    },
    LorevoxProjectionMap: {
      getWriteMode(fp) { return schemaModes[fp] || "candidate_only"; },
      parsePath(fp) {
        const m = /^([A-Za-z]+)\[(\d+)\]\.(.+)$/.exec(fp);
        if (m) return { section: m[1], index: parseInt(m[2], 10), field: m[3] };
        const p = fp.split(".");
        return p.length >= 2
          ? { section: p[0], index: null, field: p.slice(1).join(".") }
          : null;
      },
      REPEATABLE_TEMPLATES: { parents: {}, siblings: {} }
    }
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  const src = fs.readFileSync(
    path.join(ROOT, "ui", "js", "projection-sync.js"), "utf8");
  vm.runInContext(src, sandbox, { filename: "projection-sync.js" });
  return sandbox;
}

const SPOUSE = "family.spouse.firstName";
const SCHEMA = { [SPOUSE]: "prefill_if_blank", "personal.notes": "candidate_only" };

/* ── 1. the pure reduction ───────────────────────────────────────────── */
{
  const S = newSandbox(SCHEMA);
  const eff = S.LorevoxProjectionSync.effectiveWriteMode;

  eq(eff(SPOUSE, {}), "prefill_if_blank",
     "no override leaves the schema mode untouched");
  eq(eff(SPOUSE, { writeMode: "suggest_only" }), "suggest_only",
     "server may reduce prefill_if_blank -> suggest_only");
  eq(eff(SPOUSE, { writeMode: "candidate_only" }), "candidate_only",
     "server may reduce prefill_if_blank -> candidate_only");
  eq(eff("personal.notes", { writeMode: "suggest_only" }), "suggest_only",
     "server may reduce candidate_only -> suggest_only");

  // THE ONE-WAY PROPERTY. An item asking for MORE authority than the schema
  // grants must be ignored, or a response body could widen a write.
  eq(eff("personal.notes", { writeMode: "prefill_if_blank" }), "candidate_only",
     "ELEVATION REFUSED: candidate_only must not become prefill_if_blank");
  eq(eff(SPOUSE, { writeMode: "nonsense" }), "prefill_if_blank",
     "an unrecognised server mode contributes nothing");

  // Defensive floor.
  eq(eff(SPOUSE, { needsConfirmation: true }), "suggest_only",
     "needs_confirmation alone forces suggest_only");
  eq(eff(SPOUSE, { writeMode: "prefill_if_blank", needsConfirmation: true }),
     "suggest_only",
     "needs_confirmation wins over a permissive server mode");
}

/* ── 2. the behaviour that matters: does it stop the prefill? ─────────── */
// The questionnaire's exact nesting is projection-map's business, not this
// test's. Asking "did the value land anywhere in the questionnaire" MEASURES
// the property under test; asserting a nested shape would only prove I
// guessed parsePath's output correctly, which on the first draft I did not.
function landedInQuestionnaire(sandbox, value) {
  return JSON.stringify(sandbox.state.bioBuilder.questionnaire || {})
    .indexOf(value) >= 0;
}

{
  const S = newSandbox(SCHEMA);
  S.LorevoxProjectionSync.projectValue(SPOUSE, "Otis", {
    source: "backend_extract", confidence: 0.9
  });
  ok(landedInQuestionnaire(S, "Otis"),
     "CONTROL: with no override the spouse value prefills as before",
     "questionnaire = " + JSON.stringify(S.state.bioBuilder.questionnaire));
}
{
  const S = newSandbox(SCHEMA);
  S.LorevoxProjectionSync.projectValue(SPOUSE, "Otis", {
    source: "backend_extract", confidence: 0.9,
    writeMode: "suggest_only", needsConfirmation: true
  });
  ok(!landedInQuestionnaire(S, "Otis"),
     "A DOWNGRADED SPOUSE ITEM MUST NOT PREFILL THE QUESTIONNAIRE",
     "questionnaire = " + JSON.stringify(S.state.bioBuilder.questionnaire));

  const log = S.state.interviewProjection.syncLog || [];
  ok(log.some(e => e && e.action === "authority_reduced"),
     "the reduction is recorded in the sync log",
     "actions: " + log.map(e => e && e.action).join(","));
  ok(log.some(e => e && String(e.action).indexOf("suggest") >= 0),
     "the item reaches the suggestion / review path",
     "actions: " + log.map(e => e && e.action).join(","));
}

/* ── 3. an elevation attempt cannot widen a write ─────────────────────── */
{
  const S = newSandbox({ "personal.notes": "candidate_only" });
  S.LorevoxProjectionSync.projectValue("personal.notes", "ELEVATED", {
    source: "backend_extract", confidence: 0.9, writeMode: "prefill_if_blank"
  });
  ok(!landedInQuestionnaire(S, "ELEVATED"),
     "ELEVATION REFUSED end to end: candidate_only did not prefill",
     "questionnaire = " + JSON.stringify(S.state.bioBuilder.questionnaire));
}

/* ── 4. interview.js actually forwards the decision ───────────────────── */
{
  const src = fs.readFileSync(path.join(ROOT, "ui", "js", "interview.js"), "utf8");
  const call = src.slice(src.indexOf('source: "backend_extract"'));
  const block = call.slice(0, call.indexOf("});"));
  ok(/writeMode:\s*writeMode/.test(block),
     "interview.js passes item.writeMode into projectValue");
  ok(/needsConfirmation:\s*item\.needs_confirmation/.test(block),
     "interview.js passes needs_confirmation into projectValue");
}

/* ── 5. _syncToBioBuilder must not re-derive ──────────────────────────── */
{
  const src = fs.readFileSync(path.join(ROOT, "ui", "js", "projection-sync.js"), "utf8");
  const fn = src.slice(src.indexOf("function _syncToBioBuilder"));
  const body = fn.slice(0, fn.indexOf("\n  /* ──"));
  ok(/effectiveMode \|\| _map\.getWriteMode/.test(body),
     "_syncToBioBuilder prefers the resolved mode and only falls back",
     "re-deriving unconditionally is the defect this commit closes");
}

/* ── 6. the UI renders the ordered list, falling back to the scalar ───── */
{
  const sandbox = { console: { log() {} }, window: {}, JSON, Array, String, Date, Math };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(
    fs.readFileSync(path.join(ROOT, "ui", "js", "transcript-guard.js"), "utf8"),
    sandbox, { filename: "transcript-guard.js" });
  const TG = sandbox.TranscriptGuard;

  // Legacy server: scalar only, no list. Must still render.
  eq(JSON.stringify(TG.confirmationReasons({ reason: "low_confidence" })),
     JSON.stringify(["low_confidence"]),
     "falls back to the legacy scalar when no list is present");
  eq(JSON.stringify(TG.confirmationReasons({})), JSON.stringify([]),
     "no reasons at all is empty, not a crash");

  // Updated server: the list wins and its ORDER is preserved, not re-sorted.
  const both = { reasons: ["identity_conflict", "low_confidence"],
                 reason: "identity_conflict" };
  eq(JSON.stringify(TG.confirmationReasons(both)),
     JSON.stringify(["identity_conflict", "low_confidence"]),
     "the list is preferred over the scalar, in server order");

  const prompt = TG.buildConfirmationPrompt(
    { label: "your father's name", value: "Otis", reasons: ["identity_conflict", "low_confidence"] });
  ok(prompt.indexOf("already on record") >= 0 && prompt.indexOf("audio was unclear") >= 0,
     "BOTH reasons reach the narrator prompt", prompt);
  ok(prompt.indexOf("identity_conflict") < 0,
     "raw tags are not leaked to the narrator", prompt);

  const legacyPrompt = TG.buildConfirmationPrompt(
    { label: "your father's name", value: "Otis", reason: "fragile_field" });
  ok(legacyPrompt.indexOf("easy detail to mishear") >= 0,
     "a scalar-only entry still explains itself", legacyPrompt);

  const unknown = TG.buildConfirmationPrompt(
    { label: "x", value: "y", reasons: ["zz_future_tag"] });
  ok(unknown.indexOf("zz_future_tag") < 0 && unknown.indexOf("is that right?") >= 0,
     "an unrecognised tag is omitted rather than shown raw", unknown);
}

/* ── 7. the OPERATOR view renders every reason, not just the scalar ───── */
{
  // bug-panel-story-review.js is a large module with its own dependencies, so
  // this asserts the rendering expression rather than booting the panel. The
  // defect was precisely that the expression read one field.
  const src = fs.readFileSync(
    path.join(ROOT, "ui", "js", "bug-panel-story-review.js"), "utf8");
  const block = src.slice(src.indexOf("clarification_required"),
                          src.indexOf("Nothing here has been applied"));
  ok(/Array\.isArray\(c\.reasons\)/.test(block),
     "Bug Panel prefers the ordered reasons list");
  ok(/c\.reason \|\| c\.confirmation_reason/.test(block),
     "Bug Panel still falls back to the legacy scalar");
  ok(/reasons\.join\(/.test(block),
     "Bug Panel renders ALL reasons, not reasons[0]");
}

/* ── 8. the operator sees the WHOLE quarantined group — BY RENDERING IT ─
   Source-string checks used to stand here. They cannot tell whether the
   operator actually sees the values, only that some code mentions them, so
   this now runs the SHIPPED renderer against a minimal DOM and reads the
   resulting text. */
{
  function textOf(node) {
    if (node == null) return "";
    if (typeof node === "string") return node;
    return (node.children || []).map(textOf).join(" ");
  }
  const doc = {
    createElement(tag) {
      return { tag, attrs: {}, children: [],
               setAttribute(k, v) { this.attrs[k] = v; },
               appendChild(c) { this.children.push(c); return c; },
               set textContent(v) { this.children = [String(v)]; },
               get textContent() { return textOf(this); } };
    },
    createTextNode: (t) => String(t),
    getElementById: () => null,
    addEventListener() {},
    readyState: "complete",
  };
  const S = { console: { log() {}, warn() {}, error() {} }, document: doc,
              JSON, Array, Object, String, Date, Math, Set,
              setTimeout, clearTimeout, fetch: () => Promise.resolve({ json: () => ({}) }),
              addEventListener() {}, removeEventListener() {},
              localStorage: { getItem: () => null, setItem() {}, removeItem() {} } };
  S.window = S; S.globalThis = S;
  vm.createContext(S);
  try {
    vm.runInContext(fs.readFileSync(
      path.join(ROOT, "ui", "js", "bug-panel-story-review.js"), "utf8"),
      S, { filename: "bug-panel-story-review.js" });
  } catch (e) {
    failures.push("bug-panel-story-review.js failed to evaluate: " + e.message);
  }

  const render = S.lvStoryReviewRenderExtraction;
  ok(typeof render === "function", "the panel exports its extraction renderer");
  if (typeof render === "function") {
    // SHAPE READ FROM THE RENDERER, NOT GUESSED. renderExtraction(d) takes
    // d.extraction and short-circuits on status none/not_linked/unavailable.
    // The first draft of this fixture passed a bare result object and every
    // assertion failed — the same "supply the property" mistake the audit
    // that prompted this test exists to catch.
    const rendered = textOf(render({ extraction: {
      status: "succeeded",
      items: [],
      clarification_required: [{
        kind: "unbound_relationship", value: "Otis",
        label: "Otis's relationship to you",
        proposed_fieldPath: "parents.firstName",
        proposed_items: [
          { fieldPath: "parents.firstName", value: "Otis", confidence: 0.9,
            grounding: "spoken" },
          { fieldPath: "parents.birthDate", value: "1922", confidence: 0.7,
            grounding: "unsupported",
            grounding_detail: { year: 1922, spoken_years: [2005] } },
          { fieldPath: "parents.deathDate", value: "2005", confidence: 0.9,
            grounding: "spoken" },
          { fieldPath: "parents.dateOfBirth", value: "1942", confidence: 0.7,
            grounding: "derived",
            grounding_detail: { rule: "anchor_year_minus_age",
                                operands: { anchor_year: 2005, age: 63 } } },
        ],
        reasons: ["identity_conflict", "relationship_unstated"],
        reason: "identity_conflict", not_applied: true,
      }],
    }}));
    ok(/Otis's relationship to you/.test(rendered),
       "the operator sees the neutral label", rendered);
    ok(/1922/.test(rendered) && /2005/.test(rendered),
       "the operator sees EVERY proposed value, not just the subject",
       rendered);
    ok(/parents\.birthDate/.test(rendered),
       "each proposed field path is shown", rendered);
    ok(/identity_conflict/.test(rendered) && /relationship_unstated/.test(rendered),
       "every reason is shown", rendered);
    ok((rendered.match(/not applied/g) || []).length >= 2,
       "the entry AND each proposed value are marked not applied", rendered);
    ok(!/^\s*parents\.firstName\s*=/.test(rendered),
       "no proposed path is presented as an executable destination");

    // WHICH value is ungrounded — per value, visibly.
    const bad = rendered.slice(rendered.indexOf("parents.birthDate"),
                               rendered.indexOf("parents.deathDate"));
    ok(/NOT FOUND/.test(bad),
       "the operator sees WHICH value the narrator did not say", bad);
    const good = rendered.slice(rendered.indexOf("parents.deathDate"));
    ok(!/NOT FOUND/.test(good.slice(0, 60)),
       "a spoken value is NOT flagged merely for sharing the group", good);
    ok(/DERIVED, not spoken/.test(rendered) &&
       /anchor_year_minus_age/.test(rendered) &&
       /anchor_year=2005/.test(rendered) && /age=63/.test(rendered),
       "a derived value shows its rule and operands, not narrator authority",
       rendered);
  }
}

/* ── report ──────────────────────────────────────────────────────────── */
if (failures.length) {
  console.error("FAIL  " + failures.length + " of " + checks + " checks");
  failures.forEach(f => console.error("  ✗ " + f));
  process.exit(1);
}
console.log("OK    " + checks + " checks passed");
