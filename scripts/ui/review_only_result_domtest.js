/* review_only_result_domtest.js — a review-only result must survive the browser.
 *
 * WO-LORI-ARCHIVE-TO-MEMOIR-02 Phase 3 (2026-09-04).
 *
 * Three exits stood between a preserved-but-unapplied meaning and the
 * operator, and a review-only result hit all three:
 *
 *   1. applyExtractionResultFrame's `!(m.items && m.items.length)` branch,
 *      which acknowledged and discarded BEFORE the handler ran — and once
 *      acknowledged the server stops offering the row, so it was gone;
 *   2. applyCompletedTurnExtractionResult's projection-module guards, which
 *      returned before anything ran even though a review entry needs no
 *      projection;
 *   3. its `items.length === 0` return, which sat before clarification
 *      handling.
 *
 * Runs the SHIPPED interview.js in a Node VM. It is a browser-global script,
 * not a module, so the harness supplies only what these two functions touch.
 *
 *   node scripts/ui/review_only_result_domtest.js
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..", "..");
const failures = [];
let checks = 0;
function ok(c, label, detail) {
  checks++;
  if (!c) failures.push(label + (detail ? "  — " + detail : ""));
}
function eq(a, b, label) {
  ok(a === b, label, "expected " + JSON.stringify(b) + ", got " + JSON.stringify(a));
}

const QUARANTINE = {
  kind: "unbound_relationship",
  value: "Otis",
  label: "Otis's relationship to you",
  proposed_fieldPath: "parents.firstName",
  repeatableGroup: "parents_0",
  reasons: ["identity_conflict", "relationship_unstated"],
  reason: "identity_conflict",
  not_applied: true
};

/* Load interview.js with a harness that RECORDS every write it attempts.
   `opts.projection:false` removes the projection modules entirely — a
   review-only result must still be handled without them. */
function load(opts) {
  opts = opts || {};
  const writes = [], acks = [], marked = [], logs = [];
  const S = {
    console: { log: (...a) => logs.push(a.join(" ")), warn() {}, error() {} },
    setTimeout, clearTimeout, Date, Math, JSON, Set, Array, Object, String,
    fetch: (url, init) => {
      writes.push({ kind: "fetch", url: String(url) });
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    },
    state: { person_id: "p1", chat: {}, interview: {}, session: {} },
    _markExtractionKeyApplied: (k) => marked.push(k),
    _ackExtractionResults: (keys) => acks.push(keys.slice()),
    _KNOWN_RESULT_STATUSES: { succeeded: 1, noop: 1, failed: 1, duplicate: 1 },
    requestLegacyFieldExtraction() {},
  };
  if (opts.projection !== false) {
    S.state.interviewProjection = { fields: {} };
    S.LorevoxProjectionMap = {
      getWriteMode: () => "candidate_only",
      parsePath: (fp) => { const p = fp.split("."); return { section: p[0], index: null, field: p[1] }; },
      REPEATABLE_TEMPLATES: {}
    };
    S.LorevoxProjectionSync = {
      projectValue(fp, v) { writes.push({ kind: "project", fp, v }); return true; }
    };
  }
  if (opts.handler) {
    S.HorneloreClarifyFragile = (entries) => {
      if (opts.handlerThrows) throw new Error("handler exploded");
      writes.push({ kind: "review_handler", n: entries.length });
    };
  }
  S.window = S;
  S.globalThis = S;
  vm.createContext(S);
  // interview.js declares functions with `function` at top level; running it
  // in the context makes them properties of the sandbox.
  let src = fs.readFileSync(path.join(ROOT, "ui", "js", "interview.js"), "utf8");
  try {
    vm.runInContext(src, S, { filename: "interview.js" });
  } catch (e) {
    failures.push("interview.js failed to evaluate in the harness: " + e.message);
  }
  // interview.js DECLARES _markExtractionKeyApplied and _ackExtractionResults
  // itself, so its declarations replace the harness stubs during evaluation.
  // Re-install them afterwards, otherwise the real ack fires a network call
  // and the recorders stay empty — which is how the first run of this test
  // reported "0 acknowledgements" for a path that had in fact acknowledged.
  S._markExtractionKeyApplied = (k) => marked.push(k);
  S._ackExtractionResults = (keys) => acks.push(keys.slice());
  return { S, writes, acks, marked, logs };
}

const REVIEW_ONLY_FRAME = {
  status: "succeeded", turn_key: "turnrow:2", person_id: "p1",
  items: [], clarification_required: [QUARANTINE], method: "llm"
};

/* ── 1. the frame is not discarded before the handler runs ───────────── */
{
  const H = load({ handler: true });
  const r = H.S.applyExtractionResultFrame(REVIEW_ONLY_FRAME, {});
  ok(r === true, "a review-only frame is HANDLED, not swallowed by the empty branch");
  ok(H.writes.some(w => w.kind === "review_handler"),
     "the review entry reached a handler", JSON.stringify(H.writes));
}

/* ── 2. no projection modules: still handled, still nothing written ──── */
{
  const H = load({ projection: false, handler: true });
  const r = H.S.applyCompletedTurnExtractionResult(REVIEW_ONLY_FRAME, {});
  ok(r === true, "handled with NO projection modules present");
  ok(!H.writes.some(w => w.kind === "project"),
     "nothing was projected", JSON.stringify(H.writes));
}

/* ── 3. NO profile / questionnaire / suggestion / family-truth write ─── */
{
  const H = load({ handler: true });
  H.S.applyExtractionResultFrame(REVIEW_ONLY_FRAME, {});
  ok(!H.writes.some(w => w.kind === "project"),
     "a quarantine entry must never be projected");
  ok(!H.writes.some(w => w.kind === "fetch" && /family-truth/.test(w.url)),
     "no family_truth write", JSON.stringify(H.writes));
  ok(!H.writes.some(w => w.kind === "fetch"),
     "no network write at all from a review-only result",
     JSON.stringify(H.writes));
}

/* ── 4. acknowledge exactly once, and only on success ────────────────── */
{
  const H = load({ handler: true });
  H.S.applyExtractionResultFrame(REVIEW_ONLY_FRAME, {});
  eq(H.acks.length, 1, "acknowledged exactly once on successful handling");
  eq(H.marked.length, 1, "marked applied exactly once");
}
{
  // No handler of any kind AND no TranscriptGuard: handling fails.
  const H = load({ handler: false });
  delete H.S.TranscriptGuard;
  const r = H.S.applyExtractionResultFrame(REVIEW_ONLY_FRAME, {});
  ok(r === false, "unhandled review-only result reports failure");
  eq(H.acks.length, 0,
     "FAILED HANDLING MUST NOT ACKNOWLEDGE — the row stays pending");
  eq(H.marked.length, 0, "and is not marked applied");
}

/* ── 5. a genuine no-op is still acknowledged and discarded ──────────── */
{
  const H = load({ handler: true });
  const r = H.S.applyExtractionResultFrame(
    { status: "noop", turn_key: "turnrow:3", person_id: "p1",
      items: [], clarification_required: [] }, {});
  ok(r === false, "a true no-op applies nothing");
  eq(H.acks.length, 1, "and IS acknowledged, so the server stops offering it");
}

/* ── 6. an items result still behaves as before ──────────────────────── */
{
  const H = load({ handler: true });
  const r = H.S.applyExtractionResultFrame({
    status: "succeeded", turn_key: "turnrow:4", person_id: "p1",
    items: [{ fieldPath: "personal.notes", value: "v", confidence: 0.9 }],
    clarification_required: []
  }, {});
  ok(r === true, "an ordinary items result is applied");
  ok(H.writes.some(w => w.kind === "project"), "and IS projected");
  eq(H.acks.length, 1, "and acknowledged once");
}

/* ── 7. THE MIXED SHAPE — items AND a quarantined relationship ────────
   What the kinship guard actually produces. Found in review of 3026388:
   handledReview was computed and then ignored on the item path, so a result
   whose quarantine the browser could NOT handle was projected, acknowledged
   and retired anyway. */
const MIXED_FRAME = {
  status: "succeeded", turn_key: "turnrow:5", person_id: "p1",
  items: [{ fieldPath: "residence.place", value: "Plymouth Road", confidence: 0.9 }],
  clarification_required: [QUARANTINE], method: "llm"
};
{
  // 7a. review handling FAILS alongside a perfectly good item.
  const H = load({ handler: false });
  delete H.S.TranscriptGuard;
  const r = H.S.applyExtractionResultFrame(MIXED_FRAME, {});
  ok(r === false, "mixed result with failed review handling reports failure");
  ok(!H.writes.some(w => w.kind === "project"),
     "NOTHING is projected — no partial write while the quarantine is unhandled",
     JSON.stringify(H.writes));
  eq(H.acks.length, 0, "mixed result remains UNACKNOWLEDGED");
  eq(H.marked.length, 0, "mixed result remains unmarked");
}
{
  // 7b. review handling succeeds: both halves proceed, exactly once.
  const H = load({ handler: true });
  const r = H.S.applyExtractionResultFrame(MIXED_FRAME, {});
  ok(r === true, "mixed result with successful review handling succeeds");
  ok(H.writes.some(w => w.kind === "review_handler"), "the review was handled");
  ok(H.writes.some(w => w.kind === "project"), "and the safe item WAS projected");
  eq(H.acks.length, 1, "acknowledged exactly once");
  eq(H.marked.length, 1, "marked applied exactly once");
}

/* ── report ─────────────────────────────────────────────────────────── */
if (failures.length) {
  console.error("FAIL  " + failures.length + " of " + checks + " checks");
  failures.forEach(f => console.error("  ✗ " + f));
  process.exit(1);
}
console.log("OK    " + checks + " checks passed");
