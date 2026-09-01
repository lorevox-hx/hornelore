#!/usr/bin/env node
/*
 * WO-LORI-ARCHIVE-TO-MEMOIR-02 — Phase 1 probe.
 *
 * Proves, or fails to prove, ONE existing synthetic story candidate through:
 *   archive -> provisional story -> operator promotion -> canonical memoir
 *   -> preview -> export
 *
 * MUST run from WSL. Both servers bind loopback INSIDE WSL, so a browser
 * outside it cannot reach them; that is a deliberate security posture
 * (hornelore-serve.py:129, "bind loopback only (was 0.0.0.0)") and this
 * probe does not change it.
 *
 * ONE authorized state change: promote 447eee18. Control 5a56f942 is read
 * before and after and must be identical. Nothing is created or deleted.
 *
 * The probe REFUSES before promoting unless every precondition holds. A
 * refusal is a result, not an error to be worked around.
 */
"use strict";
const fs = require("fs");
const path = require("path");
// Lazily resolved inside main(), matching the working cohort runners:
// a top-level require that throws gives a bare stack with no context.

const REPO = path.resolve(__dirname, "..", "..");
const UI  = "http://localhost:8082/ui/hornelore1.0.html";
const API = "http://localhost:8000";

const TARGET  = "447eee18-9ea5-4961-bf3d-157773d3cd44";
const CONTROL = "5a56f942-001b-453b-8e4d-01fb82062013";
const PERSON  = "62e94e93-0e44-4fb0-bf19-4bfe847e163c";
const ERA     = "building_years";
const PASSAGE_HEAD = "I went to Kent State for my education degree.";

/* ── RESUME ────────────────────────────────────────────────────────
 * A first run that promotes and then fails at preview leaves 447eee18
 * `promoted`. The precondition demands `provisional`, so without this the
 * probe could never run again after a preview fix — one attempt would
 * consume the only authorized candidate.
 *
 * A resumed run may accept `promoted` ONLY when the named prior report
 * proves THIS probe promoted THIS candidate. It never promotes twice and
 * never selects a different candidate. */
const ROOT = path.join(REPO, ".runtime", "eval", "phase1-memoir-chain");
const resumeId = (() => {
  const i = process.argv.indexOf("--resume");
  return i > -1 ? process.argv[i + 1] : null;
})();
let priorProof = null;
if (resumeId) {
  const f = path.join(ROOT, resumeId, "report.json");
  if (!fs.existsSync(f)) { console.error(`--resume ${resumeId}: no report.json`); process.exit(2); }
  const prior = JSON.parse(fs.readFileSync(f, "utf8"));
  const l3 = (prior.links || {})["3_promoted"];
  const ok = prior.promotedCandidateId === TARGET && l3 && l3.result === "PASS";
  if (!ok) {
    console.error(`--resume ${resumeId}: that report does not prove this probe promoted ${TARGET}.`);
    console.error("  A resumed run may only accept a promoted candidate this probe itself promoted.");
    process.exit(2);
  }
  priorProof = { runId: resumeId, promotedAt: prior.promotedAt || null };
}
const out = path.join(ROOT,
  new Date().toISOString().replace(/[-:.]/g, "").slice(0, 15) + "Z");
fs.mkdirSync(path.join(out, "downloads"), { recursive: true });
const R = { startedAt: new Date().toISOString(), outDir: out, links: {}, refusals: [],
            resumedFrom: priorProof, promotedCandidateId: null, promotedAt: null };

const save = () => fs.writeFileSync(path.join(out, "report.json"),
  JSON.stringify(R, null, 1) + "\n", "utf8");
const step = (k, v) => { R.links[k] = v; save();
  console.log(`  [${k}] ${v.result}${v.detail ? " — " + v.detail : ""}`); };

async function api(page, p) {
  return page.evaluate(async (u) => {
    const r = await fetch(u);
    let b = null; try { b = await r.json(); } catch (_) {}
    return { status: r.status, ok: r.ok, body: b };
  }, API + p);
}

if (process.argv.includes("--self-test")) {
  const a = require("assert");
  const src = fs.readFileSync(__filename, "utf8");
  a.ok(src.includes('page.locator(".story-act-promote")'), "must use the real promote control");
  a.ok(src.includes("acceptancePath: \"UI control #memoirExportDocxBtn\""),
       "export acceptance must be the UI control");
  a.ok(src.includes("diagnosisOnly_directPOST"), "direct POST must be labelled diagnosis-only");
  a.ok(!src.includes("result: downloads.length ? \"PASS\" : (direct"),
       "direct POST must not be able to satisfy the export gate");
  a.ok(src.includes("neverSubstituted"), "preview must not be satisfied by injected content");
  a.ok(src.includes("prior.promotedCandidateId === TARGET"), "resume must verify the prior report");
  a.ok(src.includes("NOT re-promoting"), "resume must not promote twice");
  a.ok(src.includes("failed — wrong API origin"), "verdict must name a wrong-origin preview failure");
  a.strictEqual(CONTROL, "5a56f942-001b-453b-8e4d-01fb82062013");
  a.strictEqual(TARGET, "447eee18-9ea5-4961-bf3d-157773d3cd44");
  console.log("SELF-TEST PASS — promote control, acceptance paths, resume guard, verdict shape");
  process.exit(0);
}

(async () => {
  console.log("Phase 1 memoir-chain probe");
  console.log(`  target  ${TARGET}`);
  console.log(`  control ${CONTROL} (must not change)`);
  console.log(`  out     ${out}`);

  let chromium;
  try { ({ chromium } = require("playwright")); }
  catch (_) {
    try { ({ chromium } = require("@playwright/test")); }
    catch (e2) {
      console.error("\nCANNOT LOAD PLAYWRIGHT — run from /mnt/c/Users/chris/hornelore");
      console.error(e2.message); process.exit(2);
    }
  }
  console.log("  playwright loaded — launching browser…");
  const browser = await chromium.launch({ headless: !process.argv.includes("--headed") });
  const ctx = await browser.newContext({ acceptDownloads: true });
  const page = await ctx.newPage();
  const downloads = [];
  page.on("download", async (d) => {
    const f = path.join(out, "downloads", d.suggestedFilename());
    try { await d.saveAs(f); downloads.push(f); } catch (e) { downloads.push("ERR:" + e.message); }
  });

  try {
    // A page on the UI origin is used only to host fetches; every API read
    // below is issued to the API origin explicitly. The UI's own memoir
    // panel does NOT do this — see link 5.
    console.log("  opening the UI…");
    await page.goto(UI, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(2500);
    console.log("  UI loaded — reading before-state from the API origin…");

    // ── BEFORE ────────────────────────────────────────────────────────
    const before  = await api(page, `/api/operator/story-candidates/${TARGET}`);
    const ctlPre  = await api(page, `/api/operator/story-candidates/${CONTROL}`);
    const memoPre = await api(page, `/api/memoir/canonical?person_id=${PERSON}`);
    R.before = { target: before, control: ctlPre, memoir: memoPre };
    save();

    // ── PRECONDITIONS — refuse rather than proceed ────────────────────
    const b = before.body || {};
    const status = b.review_status || b.status;
    const text   = b.transcript || b.text || "";
    const checks = [
      ["candidate readable",     before.ok],
      ["candidate id matches",   (b.id || b.candidate_id) === TARGET],
      ["narrator is Pat",        b.narrator_id === PERSON],
      // `promoted` is acceptable ONLY on a resume whose prior report proves
      // this probe promoted this candidate. Otherwise provisional is required.
      ["status is promotable", priorProof
        ? ["unreviewed", "in_review", "promoted"].includes(String(status))
        : ["unreviewed", "in_review"].includes(String(status))],
      ["era recorded",           Boolean(b.era || b.era_candidates)],
      ["passage matches",        text.startsWith(PASSAGE_HEAD)],
      ["control readable",       ctlPre.ok],
    ];
    R.preconditions = checks.map(([n, ok]) => ({ check: n, pass: Boolean(ok) }));
    const failed = checks.filter(([, ok]) => !ok).map(([n]) => n);
    if (failed.length) {
      R.refusals.push("REFUSED before promotion: " + failed.join("; "));
      step("1_preconditions", { result: "REFUSED", detail: failed.join("; ") });
      throw new Error("preconditions not met — nothing was changed");
    }
    step("1_preconditions", { result: "PASS", detail: `status=${status}` });

    // ── LINK 2: the real review surface + real Promote control ────────
    const opened = await page.evaluate(() => {
      const el = document.getElementById("lv10dBugPanelBtn") ||
                 document.querySelector('[onclick*="BugPanel"],[id*="ugPanel"]');
      if (el) { el.click(); return true; } return false;
    });
    await page.waitForTimeout(1500);
    const promoteBtn = page.locator(".story-act-promote").first();
    const found = await page.locator(".story-act-promote").count();
    step("2_review_surface", {
      result: found ? "PASS" : "FAIL",
      detail: `bugPanelOpened=${opened} promoteControls=${found}`,
      note: "the ONLY promote control lives in the Bug Panel — Phase 7 gap, not fixed here",
    });
    if (!found) throw new Error("no story-act-promote control reachable");

    // ── LINK 3: click the REAL control (never twice) ──────────────────
    const alreadyPromoted = String(status) === "promoted";
    if (alreadyPromoted && priorProof) {
      console.log("  [3] resume — already promoted by run " + priorProof.runId + "; NOT re-promoting");
    } else {
      await promoteBtn.click();   // the real story-act-promote control
      await page.waitForTimeout(3000);
      R.promotedCandidateId = TARGET;
      R.promotedAt = new Date().toISOString();
    }
    const after = await api(page, `/api/operator/story-candidates/${TARGET}`);
    const newStatus = (after.body || {}).review_status || (after.body || {}).status;
    step("3_promoted", {
      result: newStatus === "promoted" ? "PASS" : "FAIL",
      detail: `status now ${newStatus}` + (alreadyPromoted && priorProof
        ? " (carried from resumed run — not promoted twice)" : " (promoted via story-act-promote)"),
      promotedThisRun: !(alreadyPromoted && priorProof),
      provenance_kept: Boolean((after.body || {}).narrator_id === PERSON &&
                               (after.body || {}).transcript),
    });
    R.after = { target: after }; save();

    // ── LINK 4: canonical, at the API origin ──────────────────────────
    const canon = await api(page, `/api/memoir/canonical?person_id=${PERSON}`);
    const stories = (canon.body && canon.body.stories) || [];
    const hits = stories.filter((s) => String(s.text || "").includes(PASSAGE_HEAD));
    step("4_canonical", {
      result: canon.ok && hits.length === 1 ? "PASS" : "FAIL",
      detail: `status=${canon.status} stories=${stories.length} passageOccurrences=${hits.length}`,
      era: hits[0] && hits[0].era, source_id: hits[0] && hits[0].source_id,
      lanes: canon.body && canon.body.lanes,
    });
    R.canonical = canon.body; save();

    // ── LINK 5: the NORMAL preview, exactly as the UI does it ─────────
    const relative = await page.evaluate(async (pid) => {
      const r = await fetch("/api/memoir/canonical?person_id=" + encodeURIComponent(pid));
      return { status: r.status, url: r.url };
    }, PERSON);
    await page.evaluate(() => {
      const el = document.getElementById("lvNarratorCtxMemoir"); if (el) el.click();
    });
    await page.waitForTimeout(2500);
    const panel = await page.evaluate((head) => {
      const p = document.getElementById("memoirScrollPopover");
      const t = p ? (p.innerText || "") : "";
      return { present: Boolean(p), visible: Boolean(p && p.offsetParent !== null),
               containsPassage: t.includes(head), chars: t.length,
               head: t.slice(0, 220) };
    }, PASSAGE_HEAD);
    step("5_preview", {
      result: panel.containsPassage ? "PASS" : "FAIL",
      detail: `UI relative fetch -> ${relative.status} at ${relative.url}`,
      panel,
      acceptancePath: "normal memoir UI panel #memoirScrollPopover",
      requestedUrl: relative.url, requestedStatus: relative.status,
      neverSubstituted: "canonical content was NOT injected into the panel; "
        + "the panel is measured as the narrator would see it",
      note: relative.status === 404
        ? "hornelore1.0.html:8551 fetches /api/memoir/canonical RELATIVE, resolving to the UI "
        + "origin (8082) instead of the API (8000). Other panels prefix ORIGIN; this one does not."
        : null,
    });

    // ── LINK 6: the real export control ───────────────────────────────
    const exportClicked = await page.evaluate(() => {
      const el = document.getElementById("memoirExportDocxBtn");
      if (!el) return "missing";
      if (el.disabled) return "disabled";
      el.click(); return "clicked";
    });
    await page.waitForTimeout(8000);
    const direct = await page.evaluate(async (o) => {
      const r = await fetch(o + "/api/memoir/export-docx", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ person_id: "62e94e93-0e44-4fb0-bf19-4bfe847e163c" }) });
      return { status: r.status, type: r.headers.get("content-type"),
               len: (await r.arrayBuffer()).byteLength };
    }, API);
    /* ACCEPTANCE IS THE UI CONTROL ONLY. The direct POST below is
     * supplemental diagnosis — it distinguishes "the UI never reached the
     * API" from "the API refused" — and can NEVER satisfy this gate. A
     * 200 from the direct POST with no UI download is still a FAIL. */
    step("6_export", {
      result: downloads.length ? "PASS" : "FAIL",
      acceptancePath: "UI control #memoirExportDocxBtn",
      detail: `control=${exportClicked} uiDownloads=${downloads.length}`,
      diagnosisOnly_directPOST: direct,
      downloads,
      classification: direct.status === 503
        ? "EXPORT DEPENDENCY FAILURE — python-docx unavailable to the serving venv. "
        + "NOT a memoir-content failure."
        : null,
    });

    // ── LINK 7: control candidate untouched ───────────────────────────
    const ctlPost = await api(page, `/api/operator/story-candidates/${CONTROL}`);
    const same = JSON.stringify(ctlPre.body) === JSON.stringify(ctlPost.body);
    step("7_control_unchanged", {
      result: same ? "PASS" : "FAIL",
      detail: same ? "5a56f942 byte-identical before and after" : "CONTROL CHANGED",
    });
    R.control = { before: ctlPre.body, after: ctlPost.body };

  } catch (e) {
    R.error = String(e && e.stack || e);
    console.error("  ERROR:", e.message);
  } finally {
    R.finishedAt = new Date().toISOString();
    /* The verdict names the link that failed. "Phase 1 failed" without a
     * link is the kind of summary this work order exists to prevent. */
    const g = (k) => (R.links[k] || {}).result || "not_reached";
    R.verdict = {
      promotion:    g("3_promoted"),
      canonical_api: g("4_canonical"),
      preview:      g("5_preview") === "PASS" ? "passed"
        : ((R.links["5_preview"] || {}).requestedStatus === 404
            ? "failed — wrong API origin" : "failed"),
      export:       g("6_export") === "PASS" ? "passed"
        : (g("5_preview") === "PASS" ? "failed" : "not reached through accepted UI path"),
      control_unchanged: g("7_control_unchanged"),
    };
    const order = ["3_promoted", "4_canonical", "5_preview", "6_export", "7_control_unchanged"];
    const firstBad = order.find((k) => R.links[k] && R.links[k].result !== "PASS");
    R.exitGate = firstBad
      ? `Phase 1: failed at ${firstBad.replace(/^\d+_/, "")}`
      : (order.every((k) => R.links[k]) ? "Phase 1: PASS — full chain proven"
                                        : "Phase 1: incomplete — not every link ran");
    save();
    console.log("\n  promotion:     " + R.verdict.promotion);
    console.log("  canonical API: " + R.verdict.canonical_api);
    console.log("  preview:       " + R.verdict.preview);
    console.log("  export:        " + R.verdict.export);
    console.log("  control 5a56f942: " + R.verdict.control_unchanged);
    try { await page.screenshot({ path: path.join(out, "final.png"), fullPage: true }); } catch (_) {}
    await browser.close();
    console.log(`\n${R.exitGate}\nEvidence: ${path.join(out, "report.json")}`);
  }
})();
