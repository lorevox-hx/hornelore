#!/usr/bin/env node
/*
 * WO-LORI-ARCHIVE-TO-MEMOIR-02 — Phase 1 probe.
 *
 * archive -> provisional story -> operator promotion -> canonical memoir
 * -> preview -> export, for ONE existing synthetic candidate.
 *
 * Written against the PUSHED contracts, verified in source:
 *   GET /api/operator/story-candidates/{id}?narrator_id=...  (narrator_id is
 *       Query(..., min_length=1) — omitting it returns 422)
 *   -> {"item": shaped, "fetched_at": _now_iso()}            (envelope; and
 *       fetched_at changes on EVERY read, so only `item` may be compared)
 *   memoir_contract.story_source_id = sha256("story:"+id)[:12]
 *       -> 5d57a43ce780. The raw UUID is deliberately absent: "a raw
 *       narrator or candidate UUID must not appear in a document a family
 *       reads". Searching for it was impossible by design.
 *   #lvNarratorCtxMemoir is a <div>; the control is
 *       .lv-narrator-ctx-cta -> lvNarratorShowView('memoir'), then the
 *       view's .lv-narrator-view-cta opens the popover. Clicking the div
 *       does nothing — a probe doing so would report "preview failed"
 *       having never opened a memoir.
 *
 * RUN FROM WSL. Both servers bind loopback inside WSL by deliberate
 * security posture. An earlier revision claimed no browser outside WSL can
 * reach them; that claim was WITHDRAWN — Windows normally reaches WSL
 * services through localhost forwarding. Only the isolated Claude browser
 * session was observed unable to.
 *
 * ONE authorized mutation: promote 447eee18 through the real UI control.
 * Control 5a56f942 must be unchanged, verified in `finally`.
 * A refusal is a result. Any refusal or failed link exits non-zero.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { execFileSync } = require("child_process");

const REPO = path.resolve(__dirname, "..", "..");
const UI  = "http://localhost:8082/ui/hornelore1.0.html";
const API = "http://localhost:8000";

const TARGET  = "447eee18-9ea5-4961-bf3d-157773d3cd44";
const CONTROL = "5a56f942-001b-453b-8e4d-01fb82062013";
const PERSON  = "62e94e93-0e44-4fb0-bf19-4bfe847e163c";
const DISPLAY_NAME = "ZZ COHORT r20260831-040506-010cd6 · Pat";
const ERA = "building_years";
const PASSAGE = "I went to Kent State for my education degree. That was 1966. "
  + "Kent State was about an hour from home and it was the first time I had "
  + "ever been away from Akron for more than a weekend.";
const PASSAGE_HEAD = "I went to Kent State for my education degree.";
const SOURCE_ID = crypto.createHash("sha256")
  .update("story:" + TARGET).digest("hex").slice(0, 12);   // 5d57a43ce780

/* Immutable across a review action. Only review_status, review_version,
 * reviewed_by/at and updated_at may move. */
const IMMUTABLE = ["id", "narrator_id", "conversation_id", "session_id",
                   "source_user_turn_row_id", "completed_assistant_turn_row_id",
                   "created_at", "trigger_reason", "word_count"];
const FORBIDDEN = ["father died", "my father, jim", "father jim",
                   "parents.deathdate", "harold died"];

// ── page-side helpers (passed DIRECTLY to evaluate; see EvaluateSerialisation)
const SELECT_ROW = function (head) {
  const rows = Array.from(document.querySelectorAll(".story-row"));
  const m = rows.filter(function (r) {
    const b = r.querySelector(".story-preview-btn");
    return b && (b.textContent || "").includes(head);
  });
  return { rows: rows.length, matching: m.length, ok: m.length === 1,
           preview: m[0] ? (m[0].querySelector(".story-preview-btn").textContent || "").slice(0, 160) : null };
};
const OPEN_DETAIL = function (head) {
  const rows = Array.from(document.querySelectorAll(".story-row"));
  const m = rows.filter(function (r) {
    const b = r.querySelector(".story-preview-btn");
    return b && (b.textContent || "").includes(head);
  });
  if (m.length !== 1) return { clicked: false, matching: m.length };
  m[0].querySelector(".story-preview-btn").click();   // addEventListener handler
  return { clicked: true, matching: 1 };
};
const VERIFY_ROW = function (args) {
  const row = Array.from(document.querySelectorAll(".story-row")).find(function (r) {
    const b = r.querySelector(".story-preview-btn");
    return b && (b.textContent || "").includes(args.head);
  });
  if (!row) return { found: false };
  const d = row.querySelector(".story-detail");
  const tr = d && d.querySelector(".story-transcript");
  const text = tr ? (tr.textContent || "").trim() : null;
  return { found: true, detailOpen: Boolean(d), transcriptEqualsTarget: text === args.full.trim(),
           transcriptLen: text ? text.length : 0,
           promoteControlsInRow: row.querySelectorAll(".story-act-promote").length };
};
const ACTIVE_OK = function (args) {
  const st = (typeof window !== "undefined" && window.state) || {};
  const names = Array.from(document.querySelectorAll("#lv80ActiveNarratorName"))
    .map(function (n) { return (n.textContent || "").trim(); });
  const status = (st.narratorOpen && st.narratorOpen.openStatus) || null;
  const idOK = st.person_id === args.personId;
  const nameOK = names.indexOf(args.displayName) > -1;
  const lifecycleOK = status === "ready";
  return { ok: idOK && nameOK && lifecycleOK, idOK: idOK, nameOK: nameOK,
           lifecycleOK: lifecycleOK, activePersonId: st.person_id || null,
           openStatus: status, names: names };
};
/* Two stages. #lvNarratorCtxMemoir is a DIV with no handler. */
const OPEN_MEMOIR_STAGE1 = function () {
  const b = document.querySelector("#lvNarratorCtxMemoir .lv-narrator-ctx-cta");
  if (!b) return { found: false };
  b.click(); return { found: true };
};
const OPEN_MEMOIR_STAGE2 = function () {
  const b = document.querySelector(".lv-narrator-view-cta");
  if (!b) return { found: false };
  b.click(); return { found: true, label: (b.textContent || "").trim() };
};
const PANEL_STATE = function (full) {
  const el = document.getElementById("memoirScrollPopover");
  const t = el ? (el.innerText || "") : "";
  return { present: Boolean(el), visible: Boolean(el && el.offsetParent !== null),
           occurrences: t.split(full).length - 1, chars: t.length, fullText: t };
};
/* ── Pure decision predicates ───────────────────────────────────────
 * Exported so the three resume/verdict rules can be tested by EXERCISING
 * them, not by grepping the source for their own assertion text. */
const RESUME_PROVENANCE_OK = function (priorImmutable, nowImmutable) {
  if (!priorImmutable) return false;          // nothing to compare against
  return JSON.stringify(priorImmutable) === JSON.stringify(nowImmutable);
};
const RESUMED_WITHOUT_MUTATION = function (patchCount, promotionAttempted) {
  return patchCount === 0 && promotionAttempted === false;
};
const PREVIEW_VERDICT = function (previewResult, wrongOrigin) {
  if (previewResult === "PASS") return "passed";
  // A step that never ran is NOT a failure. Reporting `not_reached` as
  // "failed" is how run 20260901T212134Z described a preview it had never
  // attempted -- the refusal was correct and the summary line was not.
  if (previewResult === "not_reached" || previewResult === undefined
      || previewResult === null) return "not reached";
  if (previewResult === "REFUSED") return "refused";
  // Only a 404 from OUTSIDE the API origin is a wrong-origin bug. A 404
  // from :8000 is a real canonical failure and must not be mislabelled.
  return wrongOrigin === true ? "failed — wrong API origin" : "failed";
};

/* ── The two-mutation workflow ───────────────────────────────────────
 *
 * RUNTIME ERA IS NOT A PLACEMENT. The conversation Pat was in when she
 * spoke carried era `building_years`; her story candidate carried none.
 * Capture deliberately refuses to promote the one into the other -- an
 * era candidate nobody confirmed is not a placement, and filing a story
 * into a memoir chapter on the strength of which screen the narrator
 * happened to be on is exactly the wrong-chapter bug that refusal
 * prevents. Run 20260901T212134Z is preserved as the proof of that.
 *
 * So Phase 1 exercises the OPERATOR workflow: place, then promote. Two
 * PATCHes to the same endpoint, and the second must carry the version the
 * first returned. */
const RESUME_MODE = function (prior) {
  if (!prior) return "full";                 // fresh: place, then promote
  if (prior.promotionProven) return "promoted";   // both done: zero PATCHes
  if (prior.placementProven) return "placed";     // place done: promote only
  return null;                                    // unusable prior -> refuse
};
const PATCH_BUDGET = function (mode) {
  return mode === "full" ? 2 : mode === "placed" ? 1 : mode === "promoted" ? 0 : -1;
};
/* The target must arrive UNPLACED in a fresh run. A candidate that is
 * already placed when no prior report accounts for it is not a shortcut
 * past step one -- it is an unexplained mutation, and the probe refuses
 * rather than adopting a placement whose author it cannot name. */
const UNPLACED_OK = function (item) {
  const e = (item && item.era_candidates) || [];
  return Array.isArray(e) && e.length === 0
      && (item.placement_source === "unknown" || item.placement_source == null)
      && item.estimated_year_low == null && item.estimated_year_high == null;
};
const PLACEMENT_STATE_OK = function (item, era) {
  const e = (item && item.era_candidates) || [];
  return Array.isArray(e) && e.length === 1 && e[0] === era
      && item.placement_source === "operator_set";
};
const VERSION_ADVANCED = function (before, after) {
  return typeof before === "number" && typeof after === "number" && after > before;
};
/* Body contracts. The panel builds the placement body from the era
 * control alone (era_candidates + placement_source, set in one gesture)
 * and the promotion body from the action button alone (review_status).
 * Neither may carry the other's field, and neither may carry an edit
 * nobody asked for. */
const PLACEMENT_PATCH_OK = function (args) {
  const sent = args && args.sent;
  if (!sent || typeof sent !== "object") return false;
  if ("review_status" in sent) return false;   // placement must not restatus
  return sent.narrator_id === args.person
      && sent.review_version === args.version
      && sent.placement_source === "operator_set"
      && Array.isArray(sent.era_candidates)
      && sent.era_candidates.length === 1
      && sent.era_candidates[0] === args.era;
};
const PROMOTION_PATCH_OK = function (args) {
  const sent = args && args.sent;
  if (!sent || typeof sent !== "object") return false;
  if ("era_candidates" in sent || "placement_source" in sent) return false;
  return sent.narrator_id === args.person
      && sent.review_status === "promoted"
      && sent.review_version === args.version;
};
const UNRELATED_KEYS = function (sent, allowed) {
  return Object.keys(sent || {}).filter((k) => allowed.indexOf(k) < 0);
};
const PLACEMENT_ALLOWED = ["narrator_id", "review_version",
                           "era_candidates", "placement_source"];
const PROMOTION_ALLOWED = ["narrator_id", "review_version", "review_status"];

if (typeof module !== "undefined") {
  module.exports = { SELECT_ROW, OPEN_DETAIL, VERIFY_ROW, ACTIVE_OK,
                     RESUME_PROVENANCE_OK, RESUMED_WITHOUT_MUTATION, PREVIEW_VERDICT,
                     OPEN_MEMOIR_STAGE1, OPEN_MEMOIR_STAGE2, PANEL_STATE,
                     RESUME_MODE, PATCH_BUDGET, UNPLACED_OK, PLACEMENT_STATE_OK,
                     VERSION_ADVANCED, PLACEMENT_PATCH_OK, PROMOTION_PATCH_OK,
                     UNRELATED_KEYS, PLACEMENT_ALLOWED, PROMOTION_ALLOWED,
                     SOURCE_ID, IMMUTABLE, TARGET, CONTROL, PERSON, ERA,
                     PASSAGE, DISPLAY_NAME };
}

// ── self-test ────────────────────────────────────────────────────────
if (require.main === module && process.argv.includes("--self-test")) {
  const a = require("assert"); const src = fs.readFileSync(__filename, "utf8");
  const N = (x) => x.join("");
  a.strictEqual(SOURCE_ID, "5d57a43ce780", "source digest must match the server's");
  a.ok(!src.includes(N([".story-act-promote", '")', ".fir", "st()"])), "no first() promote");
  a.ok(src.includes("narrator_id=") , "candidate reads must pass narrator_id");
  a.ok(src.includes('env.item'), "must unwrap the {item, fetched_at} envelope");
  a.ok(src.includes("OPEN_MEMOIR_STAGE2"), "memoir opening must be two-stage");
  a.ok(src.includes(N(["const refuseForeign", "Patch = async"])), "PATCH guard");
  a.ok(src.includes("pathname"), "PATCH guard must match the pathname, not substring");
  a.ok(src.includes("process.exitCode"), "a failed chain must exit non-zero");
  a.ok(src.includes("WITHDRAWN"), "withdrawn networking claim corrected");
  // The two-mutation workflow, exercised rather than grepped.
  a.strictEqual(RESUME_MODE(null), "full");
  a.strictEqual(RESUME_MODE({ placementProven: true, promotionProven: false }), "placed");
  a.strictEqual(RESUME_MODE({ placementProven: true, promotionProven: true }), "promoted");
  a.strictEqual(PATCH_BUDGET("full"), 2);
  a.strictEqual(PATCH_BUDGET("placed"), 1);
  a.strictEqual(PATCH_BUDGET("promoted"), 0);
  a.ok(UNPLACED_OK({ era_candidates: [], placement_source: "unknown",
                     estimated_year_low: null, estimated_year_high: null }));
  a.ok(!UNPLACED_OK({ era_candidates: [ERA], placement_source: "operator_set" }));
  a.ok(PLACEMENT_STATE_OK({ era_candidates: [ERA], placement_source: "operator_set" }, ERA));
  a.ok(!PLACEMENT_STATE_OK({ era_candidates: [ERA, "today"],
                             placement_source: "operator_set" }, ERA), "two eras is not a placement");
  a.ok(!PLACEMENT_STATE_OK({ era_candidates: [ERA], placement_source: "unknown" }, ERA));
  a.ok(PLACEMENT_PATCH_OK({ sent: { narrator_id: PERSON, review_version: 1,
        era_candidates: [ERA], placement_source: "operator_set" },
        era: ERA, person: PERSON, version: 1 }));
  a.ok(!PLACEMENT_PATCH_OK({ sent: { narrator_id: PERSON, review_version: 1,
        era_candidates: [ERA], placement_source: "operator_set", review_status: "promoted" },
        era: ERA, person: PERSON, version: 1 }), "placement must not carry review_status");
  a.ok(PROMOTION_PATCH_OK({ sent: { narrator_id: PERSON, review_version: 2,
        review_status: "promoted" }, person: PERSON, version: 2 }));
  a.ok(!PROMOTION_PATCH_OK({ sent: { narrator_id: PERSON, review_version: 1,
        review_status: "promoted" }, person: PERSON, version: 2 }), "stale version rejected");
  a.ok(VERSION_ADVANCED(1, 2) && !VERSION_ADVANCED(2, 2) && !VERSION_ADVANCED(2, 1));
  a.strictEqual(PREVIEW_VERDICT("not_reached"), "not reached",
                "a step that never ran is not a failure");
  a.strictEqual(PREVIEW_VERDICT("PASS"), "passed");
  a.strictEqual(PREVIEW_VERDICT("FAIL", true), "failed — wrong API origin");
  console.log("SELF-TEST PASS — envelope, digest, two-stage memoir, pathname guard,"
    + " exit code, resume modes, PATCH budgets, body contracts, preview verdict");
  process.exit(0);
}
if (require.main !== module) { return; }

const { chromium } = (() => {
  try { return require("playwright"); } catch (_) {}
  try { return require("@playwright/test"); } catch (e) {
    console.error("CANNOT LOAD PLAYWRIGHT — run from /mnt/c/Users/chris/hornelore");
    console.error(e.message); process.exit(2);
  }
})();

const ROOT = path.join(REPO, ".runtime", "eval", "phase1-memoir-chain");
const arg = (f) => { const i = process.argv.indexOf(f); return i > -1 ? process.argv[i + 1] : null; };
const resumeId = arg("--resume");
let prior = null;
if (resumeId) {
  const f = path.join(ROOT, resumeId, "report.json");
  if (!fs.existsSync(f)) { console.error(`--resume ${resumeId}: no report.json`); process.exit(2); }
  const p = JSON.parse(fs.readFileSync(f, "utf8"));
  const L = p.links || {};
  const pass = (k) => Boolean(L[k] && L[k].result === "PASS");
  /* A MUTATION IS PROVEN BY THE NAMED REPORT THAT PERFORMED IT, NEVER BY
   * THE DATABASE. "The row is already promoted" says nothing about who
   * promoted it, when, or against which provenance -- and a probe that
   * accepts the row's own state as evidence of its own prior work can be
   * satisfied by any mutation from any source. Each claim below is
   * carried by a link that recorded a request and a response. */
  const placementProven = pass("3a_placed") && p.placedCandidateId === TARGET;
  const promotionProven = pass("3b_promoted") && p.promotedCandidateId === TARGET;
  if (!pass("7_control_unchanged")) {
    console.error(`--resume ${resumeId}: prior run did not prove the control unchanged`);
    process.exit(2);
  }
  if (!placementProven && !promotionProven) {
    console.error(`--resume ${resumeId}: proves neither placement (3a_placed) nor`
      + " promotion (3b_promoted) of the target; nothing to resume from");
    process.exit(2);
  }
  if (promotionProven && !placementProven) {
    console.error(`--resume ${resumeId}: claims promotion without placement — a promoted`
      + " story with no proven placement is the state this phase exists to prevent");
    process.exit(2);
  }
  prior = { runId: resumeId,
            placementProven, promotionProven,
            placedCandidateId: p.placedCandidateId || null, placedAt: p.placedAt || null,
            promotedCandidateId: p.promotedCandidateId || null, promotedAt: p.promotedAt || null,
            placement: p.placementAfter || null,
            immutable: p.immutableBefore || null,
            chain: ((p.resumedFrom && p.resumedFrom.chain) || []).concat(resumeId) };
}
const MODE = RESUME_MODE(prior);
const BUDGET = PATCH_BUDGET(MODE);
if (MODE === null || BUDGET < 0) {
  console.error("unusable resume state — refusing"); process.exit(2);
}

const out = path.join(ROOT, new Date().toISOString().replace(/[-:.]/g, "").slice(0, 15) + "Z");
fs.mkdirSync(path.join(out, "downloads"), { recursive: true });
const R = { startedAt: new Date().toISOString(), outDir: out, links: {}, refusals: [],
            resumedFrom: prior, mode: MODE, patchBudget: BUDGET,
            placedCandidateId: prior ? prior.placedCandidateId : null,
            placedAt: prior ? prior.placedAt : null,
            placementAfter: prior ? prior.placement : null,
            promotedCandidateId: prior ? prior.promotedCandidateId : null,
            promotedAt: prior ? prior.promotedAt : null,
            mutations: [],
            expectedSourceId: SOURCE_ID, blockedPatches: [], observed: {} };
const save = () => fs.writeFileSync(path.join(out, "report.json"), JSON.stringify(R, null, 1) + "\n", "utf8");
const step = (k, v) => { R.links[k] = v; save();
  console.log(`  [${k}] ${v.result}${v.detail ? " — " + v.detail : ""}`); };
const pick = (o, keys) => keys.reduce((a, k) => (a[k] = o ? o[k] : undefined, a), {});

function docxText(file) {
  const xml = execFileSync("unzip", ["-p", file, "word/document.xml"],
                           { maxBuffer: 64 * 1024 * 1024 }).toString("utf8");
  return xml.replace(/<w:p[ >]/g, "\n<w:p ").replace(/<[^>]+>/g, "")
            .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
            .replace(/[ \t]+/g, " ");
}

(async () => {
  console.log("Phase 1 memoir-chain probe");
  console.log(`  target  ${TARGET}  (source_id ${SOURCE_ID})`);
  console.log(`  control ${CONTROL} (must not change)`);
  if (prior) console.log(`  resuming ${prior.runId}`);
  console.log(`  out     ${out}\n`);

  const browser = await chromium.launch({ headless: !process.argv.includes("--headed") });
  const ctx = await browser.newContext({ acceptDownloads: true });
  const page = await ctx.newPage();
  let promotionAttempted = false, ctlPreItem = null;

  const api = (p) => page.evaluate(async (u) => {
    const r = await fetch(u); let b = null; try { b = await r.json(); } catch (_) {}
    return { status: r.status, ok: r.ok, body: b };
  }, API + p);
  // narrator_id is REQUIRED (Query(..., min_length=1)); omitting it -> 422.
  const candidate = async (id) => {
    const res = await api(`/api/operator/story-candidates/${id}?narrator_id=${PERSON}`);
    const env = res.body || {};
    return { status: res.status, ok: res.ok, item: env.item || null, fetched_at: env.fetched_at || null };
  };

  const verifyControl = async () => {
    try {
      const post = await candidate(CONTROL);
      // Compare ONLY item: fetched_at is _now_iso() on every read, so a
      // whole-response comparison would always report a change.
      const same = JSON.stringify(ctlPreItem) === JSON.stringify(post.item);
      step("7_control_unchanged", {
        result: ctlPreItem ? (same ? "PASS" : "FAIL") : "not_measured",
        detail: !ctlPreItem ? "control never read before the attempt"
              : same ? `${CONTROL} item identical (fetched_at excluded by design)`
                     : "CONTROL ITEM CHANGED",
        checkedAfterAttemptedMutation: promotionAttempted });
      R.control = { beforeItem: ctlPreItem, afterItem: post.item };
    } catch (e) { step("7_control_unchanged", { result: "measurement_failed", detail: e.message }); }
  };

  try {
    /* PATCH guard. Two independent refusals, both enforced BEFORE the
     * request leaves the browser, because a PATCH observed after the fact
     * is a finding and a PATCH stopped in flight is a protection:
     *   1. foreign candidate  — exact pathname match, never a substring
     *   2. over budget        — full=2, placed=1, promoted=0
     * The budget is what makes "a resumed run mutates nothing" a
     * guarantee rather than a hope: in `promoted` mode the allowance is
     * zero, so any PATCH at all is aborted and recorded. */
    let patchesAllowed = BUDGET;
    const refuseForeignPatch = async (route) => {
      const req = route.request();
      if (req.method() === "PATCH") {
        const seg = new URL(req.url()).pathname.split("/").filter(Boolean).pop();
        if (seg !== TARGET) {
          R.blockedPatches.push({ url: req.url(), pathnameCandidate: seg,
                                  reason: "foreign candidate", at: new Date().toISOString() });
          R.refusals.push("BLOCKED a PATCH to candidate " + seg);
          save(); return route.abort("blockedbyclient");
        }
        if (patchesAllowed <= 0) {
          R.blockedPatches.push({ url: req.url(), pathnameCandidate: seg,
                                  reason: `over budget (mode=${MODE}, budget=${BUDGET})`,
                                  at: new Date().toISOString() });
          R.refusals.push(`BLOCKED PATCH #${BUDGET + 1} to the target — budget for`
            + ` mode ${MODE} is ${BUDGET}`);
          save(); return route.abort("blockedbyclient");
        }
        patchesAllowed -= 1;
      }
      return route.continue();
    };
    await page.route("**/api/operator/story-candidates/**", refuseForeignPatch);
    const patchSeen = [];
    page.on("response", async (res) => {
      if (res.request().method() === "PATCH" && res.url().includes("story-candidates")) {
        let body = null; try { body = await res.json(); } catch (_) {}
        let sent = null; try { sent = JSON.parse(res.request().postData() || "null"); } catch (_) {}
        patchSeen.push({ url: res.url(), status: res.status(), sent: sent,
                         item: body && body.item ? pick(body.item,
                           ["id", "narrator_id", "review_status", "review_version"]) : null });
      }
    });
    const canonicalSeen = [];
    page.on("response", (res) => {
      if (res.url().includes("/api/memoir/canonical")) {
        canonicalSeen.push({ url: res.url(), status: res.status(),
                             origin: new URL(res.url()).origin,
                             forPat: res.url().includes(PERSON), at: Date.now() });
      }
    });

    await page.goto(UI, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(2500);

    // ── 1a: candidate detail, real envelope, full provenance ─────────
    const before = await candidate(TARGET);
    const ctlPre = await candidate(CONTROL);
    ctlPreItem = ctlPre.item;
    R.before = { target: before, controlItem: ctlPre.item }; save();
    const it = before.item || {};
    R.immutableBefore = pick(it, IMMUTABLE);
    const status = it.review_status;
    const versionBefore = it.review_version;
    R.observed.placementBefore = pick(it, ["era_candidates", "placement_source",
      "estimated_year_low", "estimated_year_high", "review_status", "review_version"]);

    const checks = [
      ["detail readable (narrator_id supplied)", before.ok && Boolean(before.item)],
      ["candidate id exact", it.id === TARGET],
      ["narrator is Pat", it.narrator_id === PERSON],
      ["conversation_id recorded", Boolean(it.conversation_id)],
      ["session_id recorded", Boolean(it.session_id)],
      ["source user turn row recorded", it.source_user_turn_row_id != null],
      ["completed assistant turn row recorded", it.completed_assistant_turn_row_id != null],
      ["review_version present", versionBefore != null],
      ["control readable", ctlPre.ok && Boolean(ctlPre.item)],
    ];

    /* MODE-SPECIFIC ENTRY STATE.
     *
     * `full` demands an UNPLACED, unpromoted candidate. That is the state
     * capture leaves behind, and it is the state run 20260901T212134Z
     * proved this candidate was in. A row found already placed with no
     * prior report to account for it is refused rather than adopted --
     * the probe will not inherit a placement whose author it cannot name.
     *
     * The resume modes demand the prior report's exact placement AND its
     * exact provenance, so a resumed run cannot silently continue against
     * a different row, a re-placed row, or a re-captured story. */
    if (MODE === "full") {
      checks.push(["target is unplaced (era_candidates=[], source=unknown, no years)",
                   UNPLACED_OK(it)]);
      checks.push(["target is not yet promoted",
                   ["unreviewed", "in_review"].includes(String(status))]);
    } else {
      const priorImm = prior.immutable || null;
      const provenanceSame = RESUME_PROVENANCE_OK(priorImm, R.immutableBefore);
      R.observed.resumeProvenance = { prior: priorImm, now: R.immutableBefore, same: provenanceSame };
      checks.push(["resumed provenance identical to the prior report", provenanceSame]);
      checks.push([`placement from ${prior.runId} still holds (${ERA}, operator_set)`,
                   PLACEMENT_STATE_OK(it, ERA)]);
      if (prior.placement && prior.placement.review_version != null) {
        checks.push(["review version matches the prior report's post-placement version",
                     versionBefore === prior.placement.review_version]);
      }
      checks.push([MODE === "promoted" ? "status is promoted, as the prior report recorded"
                                       : "status is still unpromoted, awaiting this run",
                   MODE === "promoted" ? status === "promoted"
                                       : ["unreviewed", "in_review"].includes(String(status))]);
    }
    R.preconditions = checks.map(([n, ok]) => ({ check: n, pass: Boolean(ok) }));
    const failed = checks.filter(([, ok]) => !ok).map(([n]) => n);
    if (failed.length) {
      R.refusals.push("REFUSED before promotion: " + failed.join("; "));
      step("1_preconditions", { result: "REFUSED", detail: failed.join("; "),
        observedItemKeys: Object.keys(it) });
      throw new Error("preconditions not met — nothing was changed");
    }
    step("1_preconditions", { result: "PASS",
      detail: `mode=${MODE} budget=${BUDGET} status=${status} version=${versionBefore}`
            + ` placement=${(it.era_candidates || []).join(",") || "none"}/${it.placement_source}`,
      mode: MODE, patchBudget: BUDGET,
      placementBefore: R.observed.placementBefore,
      provenance: pick(it, ["conversation_id", "session_id",
        "source_user_turn_row_id", "completed_assistant_turn_row_id"]) });

    // ── 1b: Pat active, via the real switcher ────────────────────────
    await page.waitForFunction((pid) => Array.from(document.querySelectorAll("button"))
      .some((b) => b.textContent.trim() === "Open" && (b.getAttribute("onclick") || "").includes(pid)),
      PERSON, { timeout: 45000 });
    const openBtn = page.locator(`button[onclick*="${PERSON}"]`).filter({ hasText: /^Open$/ });
    if (await openBtn.count() !== 1) throw new Error("exact Open button for Pat is not unique");
    await openBtn.click();
    await page.waitForFunction((pid) => window.state?.person_id === pid, PERSON, { timeout: 60000 });
    await page.waitForFunction(() => {
      const s = window.state?.narratorOpen?.openStatus; return s && s !== "loading" && s !== "idle";
    }, null, { timeout: 60000 });
    await page.waitForFunction((n) => Array.from(document.querySelectorAll("#lv80ActiveNarratorName"))
      .some((x) => (x.textContent || "").trim() === n), DISPLAY_NAME, { timeout: 60000 }).catch(() => {});
    const active = await page.evaluate(ACTIVE_OK, { personId: PERSON, displayName: DISPLAY_NAME });
    step("1b_narrator_active", {
      result: active.ok ? "PASS" : "FAIL",
      detail: `id=${active.idOK} card=${active.nameOK} lifecycle=${active.lifecycleOK}`,
      observed: active, why: "preview and export read state.person_id, not the Bug Panel filter" });
    if (!active.ok) throw new Error("Pat is not the active narrator");

    // ── 2a: Bug Panel, unique filter, Pat-scoped successful list ─────
    await page.evaluate(() => {
      const el = document.getElementById("lv10dBugPanelBtn") ||
                 document.querySelector('[onclick*="BugPanel"],[id*="ugPanel"]');
      if (el) el.click();
    });
    await page.waitForTimeout(1200);
    const filters = page.locator(".story-filter-input");
    const nF = await filters.count();
    if (nF !== 1) {
      R.refusals.push(`REFUSED: ${nF} .story-filter-input; need exactly 1`);
      step("2a_filter", { result: "REFUSED", detail: `${nF} filter inputs` });
      throw new Error("narrator filter is not unique");
    }
    await filters.first().fill(PERSON);
    const [listRes] = await Promise.all([
      page.waitForResponse((r) => r.url().includes("/story-candidates/review"),
                           { timeout: 20000 }).catch(() => null),
      filters.first().press("Enter"),
    ]);
    const listOK = Boolean(listRes && listRes.status() < 400 && listRes.url().includes(PERSON));
    R.observed.reviewList = listRes
      ? { url: listRes.url(), status: listRes.status(), forPat: listRes.url().includes(PERSON) } : null;
    step("2a_filter", { result: listOK ? "PASS" : "FAIL",
      detail: listRes ? `status=${listRes.status()} scopedToPat=${listRes.url().includes(PERSON)}`
                      : "no /story-candidates/review response observed",
      observed: R.observed.reviewList });
    if (!listOK) throw new Error("review list for Pat was not observed to succeed");
    await page.waitForTimeout(1200);

    // ── 2/2b: exact row, real detail, row-scoped control ─────────────
    const sel = await page.evaluate(SELECT_ROW, PASSAGE_HEAD);
    step("2_row_located", { result: sel.ok ? "PASS" : "FAIL",
      detail: `.story-row=${sel.rows} matching=${sel.matching} (need exactly 1)`,
      preview: sel.preview,
      note: "review controls live in the Bug Panel: era selector, Save placement / notes,"
          + " Promote and Clear placement are all row-scoped there" });
    if (!sel.ok) throw new Error(`row selection ambiguous: ${sel.matching}`);
    const opened = await page.evaluate(OPEN_DETAIL, PASSAGE_HEAD);
    await page.waitForTimeout(2000);
    const rowState = await page.evaluate(VERIFY_ROW, { head: PASSAGE_HEAD, full: PASSAGE });
    step("2b_detail_verified", {
      result: (opened.clicked && rowState.detailOpen && rowState.transcriptEqualsTarget
               && rowState.promoteControlsInRow === 1) ? "PASS" : "FAIL",
      detail: `detailOpen=${rowState.detailOpen} transcriptEqual=${rowState.transcriptEqualsTarget}`
            + ` promoteInRow=${rowState.promoteControlsInRow}`, rowState });
    if (!rowState.transcriptEqualsTarget || rowState.promoteControlsInRow !== 1) {
      throw new Error("row detail or promote control did not satisfy the contract");
    }

    // ── 3a: PLACE, through the real era control ──────────────────────
    /* The era <select> writes BOTH era_candidates and placement_source in
     * one gesture (`choosing an era IS an operator placement`), so the
     * probe selects an era and saves -- it never composes the body. Any
     * field the panel does not put there is a field this workflow does
     * not set. */
    const row = () => page.locator(".story-row", { hasText: PASSAGE_HEAD });
    let versionAfterPlacement = versionBefore;

    if (MODE !== "full") {
      console.log(`  [3a] resume — placed by ${prior.runId}; NOT re-placing`);
      step("3a_placed", { result: "carried_forward",
        detail: `placement proven by ${prior.runId}; verified above as ${ERA}/operator_set`,
        provenBy: prior.runId, placementNow: R.observed.placementBefore });
      R.placedCandidateId = prior.placedCandidateId;
      R.placedAt = prior.placedAt;
    } else {
      const eraSel = row().locator("label.story-field", { hasText: "Life era" }).locator("select");
      const saveBtn = row().locator("button.story-act")
                           .filter({ hasText: /^Save placement \/ notes$/ });
      const nEra = await eraSel.count(), nSave = await saveBtn.count();
      if (nEra !== 1 || nSave !== 1) {
        R.refusals.push(`REFUSED placement: era selects=${nEra} save buttons=${nSave}; need exactly 1 each`);
        step("3a_placed", { result: "REFUSED",
          detail: `eraSelects=${nEra} saveButtons=${nSave} in the target row` });
        throw new Error("placement controls in the target row are not unique");
      }
      const options = await eraSel.locator("option").evaluateAll(
        (els) => els.map((e) => e.value));
      if (options.indexOf(ERA) < 0) {
        R.refusals.push(`REFUSED placement: '${ERA}' is not offered by the era control`);
        step("3a_placed", { result: "REFUSED", detail: `options=${options.join(",")}` });
        throw new Error("target era is not selectable");
      }
      // selectOption fires the real `input` event the handler listens for.
      await eraSel.selectOption(ERA);
      await page.waitForTimeout(600);          // the handler calls render()

      const [plr] = await Promise.all([
        page.waitForResponse((r) => r.request().method() === "PATCH"
          && r.url().includes("story-candidates"), { timeout: 30000 }).catch(() => null),
        row().locator("button.story-act").filter({ hasText: /^Save placement \/ notes$/ }).click(),
      ]);
      let sent = null, resItem = null;
      if (plr) {
        try { sent = JSON.parse(plr.request().postData() || "null"); } catch (_) {}
        try { const jb = await plr.json(); resItem = jb && jb.item; } catch (_) {}
      }
      const seg = plr ? new URL(plr.url()).pathname.split("/").filter(Boolean).pop() : null;
      const unrelated = UNRELATED_KEYS(sent, PLACEMENT_ALLOWED);
      const bodyOK = PLACEMENT_PATCH_OK({ sent, era: ERA, person: PERSON, version: versionBefore });
      const mutation = {
        n: 1, kind: "placement", at: new Date().toISOString(),
        url: plr ? plr.url() : null, pathnameCandidate: seg,
        status: plr ? plr.status() : null,
        request: sent,
        response: resItem ? pick(resItem, ["id", "narrator_id", "review_status",
          "review_version", "era_candidates", "placement_source"]) : null,
        versionTransition: { from: versionBefore,
                             to: resItem ? resItem.review_version : null },
        bodyConforms: bodyOK, unrelatedEdits: unrelated,
      };
      R.mutations.push(mutation); R.observed.placementPatch = mutation; save();

      const conflict = await page.locator(".story-conflict").count();
      const placedOK = Boolean(plr) && seg === TARGET && plr.status() < 400 && bodyOK
        && !unrelated.length && !conflict
        && resItem && resItem.id === TARGET && resItem.narrator_id === PERSON;
      if (placedOK) {
        R.placedCandidateId = TARGET; R.placedAt = mutation.at;
        versionAfterPlacement = resItem.review_version;
        save();
      } else {
        R.refusals.push("no placement proof recorded: PATCH missing, foreign,"
          + (conflict ? " version-conflicted," : "") + " or non-conforming");
      }
      step("3a_placed", {
        result: placedOK ? "PASS" : "FAIL",
        acceptancePath: "row era <select> ('Life era') -> row 'Save placement / notes'",
        detail: `status=${mutation.status} body=${bodyOK} unrelated=${unrelated.join(",") || "none"}`
              + ` conflictBanner=${conflict} version ${versionBefore}->`
              + `${mutation.versionTransition.to}`,
        mutation });
      if (!placedOK) throw new Error("placement did not satisfy the contract");
      await page.waitForTimeout(1500);
    }

    // ── 3a-verify: re-read and prove the placement landed cleanly ────
    const placedRead = await candidate(TARGET);
    const pi = placedRead.item || {};
    const placementImmutable = pick(pi, IMMUTABLE);
    const provenanceHeld = JSON.stringify(R.immutableBefore) === JSON.stringify(placementImmutable);
    const soleEra = PLACEMENT_STATE_OK(pi, ERA);
    const versionMoved = MODE === "full"
      ? VERSION_ADVANCED(versionBefore, pi.review_version) : true;
    const statusUntouched = MODE === "full"
      ? String(pi.review_status) === String(status) : true;
    if (MODE === "full") versionAfterPlacement = pi.review_version;
    R.placementAfter = pick(pi, ["era_candidates", "placement_source",
      "estimated_year_low", "estimated_year_high", "review_status", "review_version"]);
    step("3a_verify_placement", {
      result: (soleEra && provenanceHeld && versionMoved && statusUntouched) ? "PASS" : "FAIL",
      detail: `era=[${(pi.era_candidates || []).join(",")}] source=${pi.placement_source}`
            + ` version=${versionBefore}->${pi.review_version} status=${pi.review_status}`
            + ` provenanceUnchanged=${provenanceHeld}`,
      soleEraIsTarget: soleEra, placementSourceOperatorSet: pi.placement_source === "operator_set",
      versionAdvanced: versionMoved, reviewStatusUnchangedByPlacement: statusUntouched,
      provenanceUnchanged: provenanceHeld,
      immutableBefore: R.immutableBefore, immutableAfterPlacement: placementImmutable,
      placementAfter: R.placementAfter });
    if (!soleEra) throw new Error(`placement is not the sole era ${ERA}/operator_set`);
    if (!provenanceHeld) throw new Error("immutable provenance changed during placement");
    if (!versionMoved) throw new Error("review version did not advance after placement");
    if (!statusUntouched) throw new Error("placement changed review_status");

    // ── 3b: promote, on the REFETCHED row, at the NEW version ────────
    /* applyReview sends `review_version: item.review_version` -- the
     * version the operator OBSERVED, deliberately not re-read. So the
     * panel must be refetched after placement or Promote would send the
     * stale version and the server would answer 409. The refetch is the
     * operator's own gesture, not a shortcut around it. */
    const already = MODE === "promoted";
    if (already) {
      console.log(`  [3b] resume — promoted by ${prior.runId}; NOT re-promoting`);
    } else {
      if (MODE === "full") {
        await filters.first().press("Enter");
        await page.waitForResponse((r) => r.url().includes("/story-candidates/review"),
                                   { timeout: 20000 }).catch(() => null);
        await page.waitForTimeout(1200);
        const reopened = await page.evaluate(OPEN_DETAIL, PASSAGE_HEAD);
        await page.waitForTimeout(1500);
        const reState = await page.evaluate(VERIFY_ROW, { head: PASSAGE_HEAD, full: PASSAGE });
        step("3b_row_refetched", {
          result: (reopened.clicked && reState.detailOpen && reState.transcriptEqualsTarget
                   && reState.promoteControlsInRow === 1) ? "PASS" : "FAIL",
          detail: `detailOpen=${reState.detailOpen} transcriptEqual=${reState.transcriptEqualsTarget}`
                + ` promoteInRow=${reState.promoteControlsInRow}`,
          why: "the panel must carry the post-placement version before Promote is clicked",
          rowState: reState });
        if (!reState.transcriptEqualsTarget || reState.promoteControlsInRow !== 1) {
          throw new Error("refetched row did not satisfy the contract");
        }
      }
      const reassert = await page.evaluate(ACTIVE_OK, { personId: PERSON, displayName: DISPLAY_NAME });
      if (!reassert.ok) throw new Error("active narrator changed before promotion");
      const btn = row().locator(".story-act-promote");
      if (await btn.count() !== 1) {
        R.refusals.push("REFUSED: promote control in the target row is not unique");
        step("3b_promoted", { result: "REFUSED", detail: "promote control not unique" });
        throw new Error("promote control not unique");
      }
      promotionAttempted = true;
      const [pr] = await Promise.all([
        page.waitForResponse((r) => r.request().method() === "PATCH"
          && r.url().includes("story-candidates"), { timeout: 30000 }).catch(() => null),
        btn.click(),
      ]);
      let sent = null, resItem = null;
      if (pr) {
        try { sent = JSON.parse(pr.request().postData() || "null"); } catch (_) {}
        try { const jb = await pr.json(); resItem = jb && jb.item; } catch (_) {}
      }
      const seg = pr ? new URL(pr.url()).pathname.split("/").filter(Boolean).pop() : null;
      const unrelated = UNRELATED_KEYS(sent, PROMOTION_ALLOWED);
      /* The version is the one the PLACEMENT returned, never the one this
       * run started with. A probe that reasserts the opening version here
       * would send a stale number, take a 409, and report a broken chain
       * that is really its own bookkeeping. */
      const bodyOK = PROMOTION_PATCH_OK({ sent, person: PERSON, version: versionAfterPlacement });
      const conflict = await page.locator(".story-conflict").count();
      const mutation = {
        n: R.mutations.length + 1, kind: "promotion", at: new Date().toISOString(),
        url: pr ? pr.url() : null, pathnameCandidate: seg,
        status: pr ? pr.status() : null,
        request: sent,
        response: resItem ? pick(resItem, ["id", "narrator_id", "review_status",
          "review_version", "era_candidates", "placement_source"]) : null,
        versionTransition: { from: versionAfterPlacement,
                             to: resItem ? resItem.review_version : null },
        bodyConforms: bodyOK, unrelatedEdits: unrelated,
      };
      R.mutations.push(mutation); R.observed.patch = mutation; save();
      if (pr && seg === TARGET && pr.status() < 400 && bodyOK && !unrelated.length
          && !conflict && resItem && resItem.id === TARGET
          && resItem.narrator_id === PERSON
          && resItem.review_status === "promoted") {
        R.promotedCandidateId = TARGET; R.promotedAt = mutation.at; save();
      } else {
        R.refusals.push("no promotion proof recorded: PATCH missing, foreign,"
          + (conflict ? " version-conflicted," : "") + " or non-conforming");
      }
      await page.waitForTimeout(2000);
    }
    const after = await candidate(TARGET);
    const ai = after.item || {};
    const immutableAfter = pick(ai, IMMUTABLE);
    const immutableSame = JSON.stringify(R.immutableBefore) === JSON.stringify(immutableAfter);
    /* A resumed run must prove it mutated NOTHING. Skipping the Promote
     * click is not the same as demonstrating no PATCH left the browser. */
    const resumedCleanly = MODE === "promoted"
      ? RESUMED_WITHOUT_MUTATION(patchSeen.length, promotionAttempted) : null;
    /* THE PATCH LEDGER IS THE PROOF. Each mode has an exact expected
     * count and an exact expected order; anything else -- an extra PATCH,
     * a missing one, placement after promotion -- is a refusal, because
     * the whole claim of this phase is that exactly the authorised
     * mutations happened and nothing else did. */
    const kinds = R.mutations.map((m) => m.kind).join(">");
    const expectedKinds = MODE === "full" ? "placement>promotion"
                        : MODE === "placed" ? "promotion" : "";
    const budgetHeld = patchSeen.length === BUDGET && kinds === expectedKinds;
    // Also verify the placement survived the promotion untouched.
    const placementHeld = PLACEMENT_STATE_OK(ai, ERA);
    step("3b_promoted", {
      result: (ai.review_status === "promoted" && immutableSame && placementHeld
               && budgetHeld && !R.blockedPatches.length
               && (MODE === "promoted" ? resumedCleanly === true
                                       : Boolean(R.promotedCandidateId)))
        ? "PASS" : "FAIL",
      detail: `status=${ai.review_status} placement=[${(ai.era_candidates || []).join(",")}]`
            + `/${ai.placement_source} immutableProvenanceUnchanged=${immutableSame}`
            + ` patches=${patchSeen.length}/${BUDGET} order=${kinds || "none"}`
            + (MODE !== "full" ? ` (resume mode=${MODE})` : ""),
      mode: MODE, patchBudget: BUDGET,
      patchesObservedThisRun: patchSeen.length,
      mutationOrder: kinds, expectedMutationOrder: expectedKinds, budgetHeld,
      placementSurvivedPromotion: placementHeld,
      resumedWithoutMutation: resumedCleanly,
      promotionAttemptedThisRun: promotionAttempted,
      mutations: R.mutations, blockedForeignPatches: R.blockedPatches.length,
      immutableBefore: R.immutableBefore, immutableAfter: immutableAfter, allPatches: patchSeen });
    R.immutableAfter = immutableAfter;
    if (!budgetHeld) {
      R.refusals.push(`PATCH ledger violated: observed ${patchSeen.length} (budget ${BUDGET}),`
        + ` order '${kinds || "none"}' (expected '${expectedKinds || "none"}')`);
      throw new Error("PATCH ledger did not match the authorised mutations");
    }
    if (!placementHeld) throw new Error("promotion disturbed the placement");
    if (ai.review_status !== "promoted") throw new Error("candidate did not reach promoted");
    if (!immutableSame) throw new Error("immutable provenance changed during promotion");

    // ── 4: canonical, full contract ──────────────────────────────────
    const canon = await api(`/api/memoir/canonical?person_id=${PERSON}`);
    const cb = canon.body || {};
    const stories = cb.stories || [];
    const hits = stories.filter((s) => String(s.text || "").includes(PASSAGE));
    const hit = hits[0] || null;
    const canonOK = canon.ok && cb.person_id === PERSON && cb.complete === true
      && (cb.lanes || {}).captured_stories === "read" && hits.length === 1
      && hit && hit.era === ERA && hit.source_id === SOURCE_ID
      && hit.review_status === "promoted" && hit.lane === "captured_story";
    step("4_canonical", {
      result: canonOK ? "PASS" : "FAIL",
      detail: `status=${canon.status} complete=${cb.complete} lane=`
            + `${(cb.lanes || {}).captured_stories} occurrences=${hits.length}`
            + ` era=${hit && hit.era} source_id=${hit && hit.source_id}`,
      expected: { person_id: PERSON, complete: true, captured_stories: "read",
                  era: ERA, source_id: SOURCE_ID, review_status: "promoted",
                  lane: "captured_story" },
      observedStory: hit ? pick(hit, ["era", "source_id", "review_status", "lane", "year"]) : null,
      lanes: cb.lanes });
    R.canonical = cb; save();
    const canonText = stories.map((s) => s.text || "").join("\n");

    // ── 5: preview through the REAL two-stage UI ─────────────────────
    const beforePreview = await page.evaluate(ACTIVE_OK, { personId: PERSON, displayName: DISPLAY_NAME });
    if (!beforePreview.ok) {
      R.refusals.push("REFUSED preview: active narrator is no longer Pat");
      step("5_preview", { result: "REFUSED", detail: `active=${beforePreview.activePersonId}` });
      throw new Error("active narrator changed before preview");
    }
    // The canonical request comes from narrator load / promotion refresh —
    // NOT from opening the popover. It is read from what was observed.
    const patCanonical = canonicalSeen.filter((c) => c.forPat);
    const s1 = await page.evaluate(OPEN_MEMOIR_STAGE1);
    await page.waitForTimeout(1500);
    const s2 = await page.evaluate(OPEN_MEMOIR_STAGE2);
    await page.waitForTimeout(2000);
    const panel = await page.evaluate(PANEL_STATE, PASSAGE);
    R.observed.canonicalRequests = canonicalSeen;
    const previewOK = s1.found && s2.found && panel.visible && panel.occurrences === 1;
    const wrongOrigin = patCanonical.length > 0
      && patCanonical.every((c) => c.status === 404 && !c.origin.includes("8000"));
    // Recorded so the verdict in `finally` reuses THIS test rather than
    // re-deriving a looser one. A 404 from the API origin is a genuine
    // canonical failure, not a wrong-origin bug, and must not be
    // mislabelled as one.
    R.observed.previewWrongOrigin = wrongOrigin;
    step("5_preview", {
      result: previewOK ? "PASS" : "FAIL",
      acceptancePath: "#lvNarratorCtxMemoir .lv-narrator-ctx-cta -> .lv-narrator-view-cta",
      detail: `stage1=${s1.found} stage2=${s2.found} popoverVisible=${panel.visible}`
            + ` occurrences=${panel.occurrences} (need exactly 1)`,
      stage1: s1, stage2: s2, panelVisible: panel.visible, panelChars: panel.chars,
      canonicalRequestsForPat: patCanonical,
      neverSubstituted: "no canonical content injected; the panel is measured as the narrator sees it",
      note: wrongOrigin ? "every observed canonical request for Pat 404'd off the API origin — "
        + "hornelore1.0.html:8551 fetches it relative, resolving to the UI server" : null });

    // ── 6: export, only if preview passed ────────────────────────────
    if (!previewOK) {
      step("6_export", { result: "not_reached",
        detail: "preview did not pass; export is NOT attempted" });
    } else {
      const beforeExport = await page.evaluate(ACTIVE_OK, { personId: PERSON, displayName: DISPLAY_NAME });
      if (!beforeExport.ok) {
        R.refusals.push("REFUSED export: active narrator is no longer Pat");
        step("6_export", { result: "REFUSED", detail: `active=${beforeExport.activePersonId}` });
        throw new Error("active narrator changed before export");
      }
      const btn = page.locator("#memoirExportDocxBtn");
      let saved = null, dlErr = null, exportPost = null;
      if (await btn.count() && await btn.isEnabled()) {
        try {
          const [dl, res] = await Promise.all([
            page.waitForEvent("download", { timeout: 90000 }),
            page.waitForResponse((r) => r.url().includes("/api/memoir/export-docx"),
                                 { timeout: 90000 }).catch(() => null),
            btn.click(),
          ]);
          if (res) {
            let sent = null; try { sent = JSON.parse(res.request().postData() || "null"); } catch (_) {}
            exportPost = { url: res.url(), status: res.status(), sentBody: sent,
                           bodyPersonIsPat: Boolean(sent && sent.person_id === PERSON) };
          }
          saved = path.join(out, "downloads", dl.suggestedFilename());
          await dl.saveAs(saved);
        } catch (e) { dlErr = e.message; }
      }
      let docx = null;
      if (saved && fs.existsSync(saved)) {
        try {
          const t = docxText(saved); R.docxFullText = t;
          const tl = t.toLowerCase();
          docx = { file: path.basename(saved), bytes: fs.statSync(saved).size,
                   occurrences: t.split(PASSAGE).length - 1,
                   containsSourceId: t.includes(SOURCE_ID),
                   forbidden: FORBIDDEN.filter((f) => tl.includes(f)) };
        } catch (e) { docx = { readError: e.message }; }
      }
      R.observed.exportPost = exportPost;
      step("6_export", {
        result: (docx && docx.occurrences === 1 && !(docx.forbidden || []).length
                 && exportPost && exportPost.bodyPersonIsPat) ? "PASS" : "FAIL",
        acceptancePath: "UI #memoirExportDocxBtn + real download + POST body ownership",
        detail: saved ? `downloaded ${path.basename(saved)} occurrences=${docx && docx.occurrences}`
                      + ` bodyPersonIsPat=${exportPost && exportPost.bodyPersonIsPat}`
                      : `no download (${dlErr || "control unusable"})`,
        exportPost, docx });
      R.docx = docx;
    }

    // ── 8: agreement ─────────────────────────────────────────────────
    const dOcc = R.docx ? R.docx.occurrences : null;
    const hay = [canonText, panel.fullText, R.docxFullText || ""].join("\n").toLowerCase();
    const forbiddenAnywhere = FORBIDDEN.filter((f) => hay.includes(f));
    step("8_agreement", {
      result: (hits.length === 1 && panel.occurrences === 1 && dOcc === 1
               && !forbiddenAnywhere.length) ? "PASS" : "FAIL",
      detail: `canonical=${hits.length} preview=${panel.occurrences} docx=${dOcc} (each exactly 1)`,
      era: hit && hit.era, sourceId: hit && hit.source_id, expectedSourceId: SOURCE_ID,
      forbiddenSubstitutions: forbiddenAnywhere });

  } catch (e) {
    R.error = String(e && e.stack || e);
    console.error("  ERROR:", e.message);
  } finally {
    await verifyControl();
    R.finishedAt = new Date().toISOString();
    const g = (k) => (R.links[k] || {}).result || "not_reached";
    R.verdict = {
      placement: g("3a_placed"), placement_verified: g("3a_verify_placement"),
      promotion: g("3b_promoted"), canonical_api: g("4_canonical"),
      preview: PREVIEW_VERDICT(g("5_preview"), R.observed.previewWrongOrigin),
      export: g("6_export") === "PASS" ? "passed"
        : g("6_export") === "not_reached" ? "not reached through accepted UI path"
        : (g("5_preview") === "PASS" ? "failed" : "not reached through accepted UI path"),
      control_unchanged: g("7_control_unchanged"),
    };
    /* `3a_placed` is `carried_forward` in a resumed run and PASS in a
     * fresh one; both are acceptable, and only those two. */
    const OK = (k) => (k === "3a_placed"
      ? ["PASS", "carried_forward"].indexOf(g(k)) >= 0 : g(k) === "PASS");
    const order = ["1_preconditions", "1b_narrator_active", "2a_filter", "2_row_located",
                   "2b_detail_verified", "3a_placed", "3a_verify_placement",
                   "3b_promoted", "4_canonical", "5_preview",
                   "6_export", "8_agreement", "7_control_unchanged"];
    // 3b_row_refetched only exists in a fresh run; required exactly there.
    if (MODE === "full") order.splice(order.indexOf("3b_promoted"), 0, "3b_row_refetched");
    const bad = order.find((k) => R.links[k] && !OK(k));
    const complete = order.every((k) => R.links[k]);
    R.exitGate = bad ? `Phase 1: failed at ${bad.replace(/^\d+[ab]?_/, "")}`
      : (complete ? "Phase 1: PASS — full chain proven" : "Phase 1: incomplete — not every link ran");
    save();
    console.log("\n  mode:             " + MODE + `  (PATCH budget ${BUDGET}, observed `
      + `${R.mutations.length})`);
    R.mutations.forEach((m) => console.log(`    #${m.n} ${m.kind}: HTTP ${m.status} `
      + `v${m.versionTransition.from}->v${m.versionTransition.to} conforms=${m.bodyConforms}`));
    console.log("  placement:        " + R.verdict.placement
      + " / verified " + R.verdict.placement_verified);
    console.log("  promotion:        " + R.verdict.promotion);
    console.log("  canonical API:    " + R.verdict.canonical_api);
    console.log("  preview:          " + R.verdict.preview);
    console.log("  export:           " + R.verdict.export);
    console.log("  control 5a56f942: " + R.verdict.control_unchanged);
    if (R.blockedPatches.length) console.log(`  BLOCKED ${R.blockedPatches.length} foreign PATCH(es)`);
    if (R.refusals.length) R.refusals.forEach((r) => console.log("  REFUSAL: " + r));
    try { await page.screenshot({ path: path.join(out, "final.png"), fullPage: true }); } catch (_) {}
    await browser.close();
    // A refusal, incomplete chain or failed link must exit non-zero.
    process.exitCode = (!bad && complete && !R.refusals.length && !R.error) ? 0 : 1;
    console.log(`\n${R.exitGate}\nEvidence: ${path.join(out, "report.json")}`);
    console.log(`Exit code: ${process.exitCode}`);
  }
})();
