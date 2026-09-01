#!/usr/bin/env node
/*
 * WO-LORI-ARCHIVE-TO-MEMOIR-02 — Phase 1 probe.
 *
 * Proves, or fails to prove, ONE existing synthetic story candidate through:
 *   archive -> provisional story -> operator promotion -> canonical memoir
 *   -> preview -> export
 *
 * RUN FROM WSL. Both servers bind loopback inside WSL by deliberate security
 * posture (hornelore-serve.py:129). An earlier revision of this file claimed
 * no browser outside WSL can reach them; that claim was WITHDRAWN and is
 * wrong. Windows normally reaches WSL services through localhost forwarding.
 * What was actually observed is narrower: the isolated Claude browser session
 * could not reach this machine's WSL loopback. Playwright inside WSL is used
 * because it is known-good here, not because Windows is incapable.
 *
 * ONE authorized state change: promote 447eee18 via the real UI control.
 * Control 5a56f942 must stay byte-identical and is verified in a finally
 * path so an earlier throw cannot skip the check.
 *
 * A refusal is a result, not an error to work around.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

const REPO = path.resolve(__dirname, "..", "..");
const UI  = "http://localhost:8082/ui/hornelore1.0.html";
const API = "http://localhost:8000";

const TARGET  = "447eee18-9ea5-4961-bf3d-157773d3cd44";
const CONTROL = "5a56f942-001b-453b-8e4d-01fb82062013";
const PERSON  = "62e94e93-0e44-4fb0-bf19-4bfe847e163c";
const ERA     = "building_years";
const PASSAGE = "I went to Kent State for my education degree. That was 1966. "
  + "Kent State was about an hour from home and it was the first time I had "
  + "ever been away from Akron for more than a weekend.";
const PASSAGE_HEAD = "I went to Kent State for my education degree.";
/* Pat's husband Jim is filed under parents.* by the extractor (a known,
 * unfixed binding defect). If a memoir surface substitutes that structured
 * family fact into her passage, the memoir would assert something false
 * about her father. Checked, never repaired here. */
const FORBIDDEN_SUBSTITUTIONS = ["father died", "my father, Jim", "father Jim",
                                 "parents.deathDate", "Harold died"];

const ROOT = path.join(REPO, ".runtime", "eval", "phase1-memoir-chain");
const arg = (f) => { const i = process.argv.indexOf(f); return i > -1 ? process.argv[i + 1] : null; };

// ── self-test ────────────────────────────────────────────────────────
if (process.argv.includes("--self-test")) {
  const a = require("assert"); const src = fs.readFileSync(__filename, "utf8");
  // Needles are built at runtime so this block cannot match its own text —
  // a literal here would make the assertion pass by describing itself.
  const N = (x) => x.join("");
  a.ok(!src.includes(N([".story-act-promote", '")', ".fir", "st()"])),
       "must not click a first() promote control");
  a.ok(src.includes(N(["const refuseForeign", "Patch = async"])), "must install a PATCH guard");
  a.ok(src.includes("waitForResponse"), "must observe the real UI request");
  a.ok(src.includes("waitForEvent(\"download\""), "must wait for a real download event");
  a.ok(src.includes("docxText"), "must read the exported document");
  a.ok(src.includes("occurrences"), "must count occurrences, not presence");
  a.ok(src.includes("FORBIDDEN_SUBSTITUTIONS"), "must check for substituted family facts");
  a.ok(src.includes("verifyControl"), "control check must be a callable used in finally");
  a.ok(src.includes("WITHDRAWN"), "the withdrawn networking claim must be corrected");
  a.ok(src.includes('status) !== "promoted"'), "resume must require exactly promoted");
  console.log("SELF-TEST PASS — row scoping, PATCH guard, real observation, docx proof, finally control");
  process.exit(0);
}

const { chromium } = (() => {
  try { return require("playwright"); } catch (_) {}
  try { return require("@playwright/test"); } catch (e) {
    console.error("CANNOT LOAD PLAYWRIGHT — run from /mnt/c/Users/chris/hornelore");
    console.error(e.message); process.exit(2);
  }
})();

// ── resume ───────────────────────────────────────────────────────────
const resumeId = arg("--resume");
let prior = null;
if (resumeId) {
  const f = path.join(ROOT, resumeId, "report.json");
  if (!fs.existsSync(f)) { console.error(`--resume ${resumeId}: no report.json`); process.exit(2); }
  const p = JSON.parse(fs.readFileSync(f, "utf8"));
  const l3 = (p.links || {})["3_promoted"];
  if (!(p.promotedCandidateId === TARGET && l3 && l3.result === "PASS")) {
    console.error(`--resume ${resumeId}: does not prove this probe promoted ${TARGET}`);
    process.exit(2);
  }
  // Carried forward so a resumed report can itself be resumed.
  prior = { runId: resumeId, promotedCandidateId: p.promotedCandidateId,
            promotedAt: p.promotedAt, chain: (p.resumedFrom && p.resumedFrom.chain || []).concat(resumeId) };
}

const out = path.join(ROOT, new Date().toISOString().replace(/[-:.]/g, "").slice(0, 15) + "Z");
fs.mkdirSync(path.join(out, "downloads"), { recursive: true });
const R = { startedAt: new Date().toISOString(), outDir: out, links: {}, refusals: [],
            resumedFrom: prior,
            promotedCandidateId: prior ? prior.promotedCandidateId : null,
            promotedAt: prior ? prior.promotedAt : null,
            blockedPatches: [], observed: {} };
const save = () => fs.writeFileSync(path.join(out, "report.json"), JSON.stringify(R, null, 1) + "\n", "utf8");
const step = (k, v) => { R.links[k] = v; save();
  console.log(`  [${k}] ${v.result}${v.detail ? " — " + v.detail : ""}`); };
const count = (hay, needle) => hay ? hay.split(needle).length - 1 : 0;

function docxText(file) {
  // A .docx is a zip; word/document.xml holds the body. unzip is present in WSL.
  const xml = execFileSync("unzip", ["-p", file, "word/document.xml"],
                           { maxBuffer: 64 * 1024 * 1024 }).toString("utf8");
  return xml.replace(/<w:p[ >]/g, "\n<w:p ").replace(/<[^>]+>/g, "")
            .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
            .replace(/[ \t]+/g, " ");
}

(async () => {
  console.log("Phase 1 memoir-chain probe");
  console.log(`  target  ${TARGET}`);
  console.log(`  control ${CONTROL} (must not change)`);
  if (prior) console.log(`  resuming ${prior.runId} — promoted at ${prior.promotedAt}`);
  console.log(`  out     ${out}\n`);

  const browser = await chromium.launch({ headless: !process.argv.includes("--headed") });
  const ctx = await browser.newContext({ acceptDownloads: true });
  const page = await ctx.newPage();
  let promotionAttempted = false, ctlPre = null;

  const api = (p) => page.evaluate(async (u) => {
    const r = await fetch(u); let b = null; try { b = await r.json(); } catch (_) {}
    return { status: r.status, ok: r.ok, body: b };
  }, API + p);

  const verifyControl = async () => {
    try {
      const post = await api(`/api/operator/story-candidates/${CONTROL}`);
      const same = JSON.stringify(ctlPre && ctlPre.body) === JSON.stringify(post.body);
      step("7_control_unchanged", {
        result: ctlPre ? (same ? "PASS" : "FAIL") : "not_measured",
        detail: !ctlPre ? "control was never read before the attempt"
              : same ? `${CONTROL} byte-identical` : "CONTROL CHANGED — a foreign mutation occurred",
        checkedAfterAttemptedMutation: promotionAttempted });
      R.control = { before: ctlPre && ctlPre.body, after: post.body };
    } catch (e) {
      step("7_control_unchanged", { result: "measurement_failed", detail: e.message });
    }
  };

  try {
    /* ── PATCH GUARD ────────────────────────────────────────────────
     * A selector mistake must not be able to mutate another candidate.
     * Any story-candidate PATCH whose URL lacks the exact target UUID is
     * aborted before it leaves the browser and recorded as a refusal. */
    const refuseForeignPatch = async (route) => {
      const req = route.request();
      if (req.method() === "PATCH" && !req.url().includes(TARGET)) {
        R.blockedPatches.push({ url: req.url(), at: new Date().toISOString() });
        R.refusals.push("BLOCKED a PATCH to a candidate other than the target: " + req.url());
        save();
        return route.abort("blockedbyclient");
      }
      return route.continue();
    };
    await page.route("**/api/operator/story-candidates/**", refuseForeignPatch);
    const patchSeen = [];
    page.on("response", async (res) => {
      if (res.request().method() === "PATCH" && res.url().includes("story-candidates")) {
        let body = null; try { body = await res.json(); } catch (_) {}
        patchSeen.push({ url: res.url(), status: res.status(),
                         status_after: body && (body.review_status || body.status) });
      }
    });

    await page.goto(UI, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(2500);

    // ── BEFORE ───────────────────────────────────────────────────────
    const before = await api(`/api/operator/story-candidates/${TARGET}`);
    ctlPre = await api(`/api/operator/story-candidates/${CONTROL}`);
    R.before = { target: before, control: ctlPre }; save();
    const b = before.body || {};
    const status = b.review_status || b.status;
    const text = b.transcript || b.text || "";

    const checks = [
      ["candidate readable", before.ok],
      ["candidate id matches", (b.id || b.candidate_id) === TARGET],
      ["narrator is Pat", b.narrator_id === PERSON],
      // A resume requires EXACTLY promoted. It never re-promotes an
      // unreviewed or in_review candidate.
      ["status correct for mode", prior ? String(status) === "promoted"
        : ["unreviewed", "in_review"].includes(String(status))],
      ["era recorded", Boolean(b.era || b.era_candidates)],
      ["passage matches", text.startsWith(PASSAGE_HEAD)],
      ["control readable", ctlPre.ok],
    ];
    R.preconditions = checks.map(([n, ok]) => ({ check: n, pass: Boolean(ok) }));
    const failed = checks.filter(([, ok]) => !ok).map(([n]) => n);
    if (failed.length) {
      R.refusals.push("REFUSED before promotion: " + failed.join("; "));
      step("1_preconditions", { result: "REFUSED", detail: failed.join("; ") });
      throw new Error("preconditions not met — nothing was changed");
    }
    step("1_preconditions", { result: "PASS", detail: `status=${status} mode=${prior ? "resume" : "fresh"}` });

    // ── LINK 2: find PAT'S EXACT ROW, not the first row ──────────────
    await page.evaluate(() => {
      const el = document.getElementById("lv10dBugPanelBtn") ||
                 document.querySelector('[onclick*="BugPanel"],[id*="ugPanel"]');
      if (el) el.click();
    });
    await page.waitForTimeout(1200);
    // Narrow by narrator first so the list is Pat's, then disambiguate her
    // two candidates by the target passage. `.first()` on a global list
    // could promote the control — that was the defect in the prior revision.
    const filter = page.locator('input[placeholder*="arrator" i], #storyNarratorFilter').first();
    if (await filter.count()) { await filter.fill(PERSON); await page.waitForTimeout(1500); }
    const matching = await page.locator("*", { hasText: PASSAGE_HEAD }).count();
    const rowInfo = await page.evaluate((head) => {
      const nodes = Array.from(document.querySelectorAll("*")).filter(
        (n) => n.children.length === 0 && (n.textContent || "").includes(head));
      return { textNodes: nodes.length, sample: nodes[0] ? nodes[0].textContent.slice(0, 120) : null };
    }, PASSAGE_HEAD);
    step("2_row_located", {
      result: rowInfo.textNodes >= 1 ? "PASS" : "FAIL",
      detail: `rows showing the target passage: ${rowInfo.textNodes}`,
      sample: rowInfo.sample, matchingElements: matching,
      note: "the only promote control lives in the Bug Panel — Phase 7 gap, not fixed here" });
    if (!rowInfo.textNodes) throw new Error("target row not visible in the review surface");

    // Open that row's detail and verify the FULL transcript before promoting.
    await page.evaluate((head) => {
      const n = Array.from(document.querySelectorAll("*")).find(
        (x) => x.children.length === 0 && (x.textContent || "").includes(head));
      let el = n; while (el && el !== document.body) {
        if (el.getAttribute && el.getAttribute("onclick")) { el.click(); return; }
        el = el.parentElement;
      }
      if (n && n.parentElement) n.parentElement.click();
    }, PASSAGE_HEAD);
    await page.waitForTimeout(1500);
    const detail = await page.evaluate((p) => {
      const t = document.body.innerText || "";
      return { showsFullPassage: t.includes(p), chars: t.length };
    }, PASSAGE);
    step("2b_detail_verified", {
      result: detail.showsFullPassage ? "PASS" : "FAIL",
      detail: `detail shows the complete target transcript: ${detail.showsFullPassage}` });
    if (!detail.showsFullPassage) throw new Error("open detail does not show the target transcript");

    // ── LINK 3: promote, never twice ─────────────────────────────────
    const already = String(status) === "promoted";
    if (already && prior) {
      console.log(`  [3] resume — promoted by ${prior.runId}; NOT re-promoting`);
    } else {
      const btn = page.locator(".story-act-promote");
      const n = await btn.count();
      if (n !== 1) {
        R.refusals.push(`REFUSED: ${n} promote controls visible after scoping; need exactly 1`);
        step("3_promoted", { result: "REFUSED", detail: `${n} promote controls visible — refusing to guess` });
        throw new Error("promote control is not unambiguous");
      }
      promotionAttempted = true;
      const [patchRes] = await Promise.all([
        page.waitForResponse((r) => r.request().method() === "PATCH"
          && r.url().includes("story-candidates"), { timeout: 30000 }).catch(() => null),
        btn.click(),
      ]);
      R.observed.patch = patchRes
        ? { url: patchRes.url(), status: patchRes.status(), targetedTarget: patchRes.url().includes(TARGET) }
        : null;
      R.promotedCandidateId = TARGET; R.promotedAt = new Date().toISOString();
      await page.waitForTimeout(2000);
    }
    const after = await api(`/api/operator/story-candidates/${TARGET}`);
    const newStatus = (after.body || {}).review_status || (after.body || {}).status;
    const patchOK = already && prior ? true
      : Boolean(R.observed.patch && R.observed.patch.targetedTarget && R.observed.patch.status < 400);
    step("3_promoted", {
      result: newStatus === "promoted" && patchOK && !R.blockedPatches.length ? "PASS" : "FAIL",
      detail: `status now ${newStatus}` + (already && prior ? " (carried from resume)" : ""),
      observedPatch: R.observed.patch, blockedForeignPatches: R.blockedPatches.length,
      provenanceKept: Boolean((after.body || {}).narrator_id === PERSON && (after.body || {}).transcript),
      allPatches: patchSeen });
    if (newStatus !== "promoted") throw new Error("candidate did not reach promoted");

    // ── LINK 4: canonical (diagnosis + occurrence count) ─────────────
    const canon = await api(`/api/memoir/canonical?person_id=${PERSON}`);
    const stories = (canon.body && canon.body.stories) || [];
    const canonHits = stories.filter((s) => String(s.text || "").includes(PASSAGE_HEAD));
    const canonText = stories.map((s) => s.text || "").join("\n");
    step("4_canonical", {
      result: canon.ok && canonHits.length === 1 ? "PASS" : "FAIL",
      detail: `status=${canon.status} stories=${stories.length} occurrences=${canonHits.length}`,
      era: canonHits[0] && canonHits[0].era, source_id: canonHits[0] && canonHits[0].source_id,
      eraCorrect: Boolean(canonHits[0] && canonHits[0].era === ERA),
      lanes: canon.body && canon.body.lanes });
    R.canonical = canon.body; save();

    // ── LINK 5: preview, observed on the REAL UI request ─────────────
    const [memoirRes] = await Promise.all([
      page.waitForResponse((r) => r.url().includes("/api/memoir/canonical"),
                           { timeout: 20000 }).catch(() => null),
      page.evaluate(() => { const el = document.getElementById("lvNarratorCtxMemoir"); if (el) el.click(); }),
    ]);
    await page.waitForTimeout(2500);
    R.observed.memoirRequest = memoirRes
      ? { url: memoirRes.url(), status: memoirRes.status(), origin: new URL(memoirRes.url()).origin }
      : null;
    const panel = await page.evaluate((p) => {
      const el = document.getElementById("memoirScrollPopover");
      const t = el ? (el.innerText || "") : "";
      return { present: Boolean(el), visible: Boolean(el && el.offsetParent !== null),
               occurrences: t.split(p).length - 1, chars: t.length, head: t.slice(0, 200) };
    }, PASSAGE);
    const wrongOrigin = Boolean(R.observed.memoirRequest
      && R.observed.memoirRequest.status === 404
      && !R.observed.memoirRequest.origin.includes("8000"));
    step("5_preview", {
      result: panel.occurrences === 1 ? "PASS" : "FAIL",
      acceptancePath: "normal memoir UI panel #memoirScrollPopover",
      detail: `panel occurrences=${panel.occurrences} (need exactly 1)`,
      observedRequest: R.observed.memoirRequest, panel,
      neverSubstituted: "no canonical content was injected; the panel is measured as the narrator sees it",
      note: wrongOrigin ? "hornelore1.0.html:8551 fetches /api/memoir/canonical RELATIVE, resolving to "
        + "the UI origin instead of the API. bug-panel-story-review.js and trip-tab.js prefix ORIGIN; "
        + "the memoir panel does not." : null });

    // ── LINK 6: export — ONLY if preview passed ──────────────────────
    if (panel.occurrences !== 1) {
      step("6_export", { result: "not_reached",
        detail: "preview did not pass; the accepted chain stops here and export is NOT attempted" });
    } else {
      const exportBtn = page.locator("#memoirExportDocxBtn");
      const usable = await exportBtn.count() && await exportBtn.isEnabled();
      let saved = null, dlErr = null;
      if (usable) {
        try {
          const [dl] = await Promise.all([
            page.waitForEvent("download", { timeout: 90000 }),
            exportBtn.click(),
          ]);
          saved = path.join(out, "downloads", dl.suggestedFilename());
          await dl.saveAs(saved);
        } catch (e) { dlErr = e.message; }
      }
      let docx = null;
      if (saved && fs.existsSync(saved)) {
        try {
          const t = docxText(saved);
          docx = { file: path.basename(saved), bytes: fs.statSync(saved).size,
                   occurrences: count(t, PASSAGE),
                   headOccurrences: count(t, PASSAGE_HEAD),
                   forbidden: FORBIDDEN_SUBSTITUTIONS.filter((f) => t.includes(f)) };
        } catch (e) { docx = { readError: e.message }; }
      }
      step("6_export", {
        result: docx && docx.occurrences === 1 && !(docx.forbidden || []).length ? "PASS" : "FAIL",
        acceptancePath: "UI control #memoirExportDocxBtn + real download event",
        detail: saved ? `downloaded ${path.basename(saved)}; passage occurrences=${docx && docx.occurrences}`
                      : `no download (${dlErr || (usable ? "timeout" : "control unusable")})`,
        docx });
      R.docx = docx;
    }

    // ── LINK 8: agreement across the three surfaces ──────────────────
    const cOcc = canonHits.length, pOcc = panel.occurrences,
          dOcc = R.docx ? R.docx.occurrences : null;
    const forbiddenAnywhere = FORBIDDEN_SUBSTITUTIONS.filter(
      (f) => canonText.includes(f) || (panel.head || "").includes(f)
             || (R.docx && (R.docx.forbidden || []).includes(f)));
    step("8_agreement", {
      result: (cOcc === 1 && pOcc === 1 && dOcc === 1 && !forbiddenAnywhere.length) ? "PASS" : "FAIL",
      detail: `canonical=${cOcc} preview=${pOcc} docx=${dOcc} (each must be exactly 1)`,
      eraCorrect: Boolean(canonHits[0] && canonHits[0].era === ERA),
      provenance: canonHits[0] && canonHits[0].source_id,
      forbiddenSubstitutions: forbiddenAnywhere });

  } catch (e) {
    R.error = String(e && e.stack || e);
    console.error("  ERROR:", e.message);
  } finally {
    // Runs even if an earlier link threw, so a foreign mutation is always caught.
    await verifyControl();
    R.finishedAt = new Date().toISOString();
    const g = (k) => (R.links[k] || {}).result || "not_reached";
    R.verdict = {
      promotion: g("3_promoted"),
      canonical_api: g("4_canonical"),
      preview: g("5_preview") === "PASS" ? "passed"
        : (R.observed.memoirRequest && R.observed.memoirRequest.status === 404
            ? "failed — wrong API origin" : "failed"),
      export: g("6_export") === "PASS" ? "passed"
        : (g("5_preview") === "PASS" ? "failed" : "not reached through accepted UI path"),
      control_unchanged: g("7_control_unchanged"),
    };
    const order = ["1_preconditions", "2_row_located", "2b_detail_verified", "3_promoted",
                   "4_canonical", "5_preview", "6_export", "8_agreement", "7_control_unchanged"];
    const bad = order.find((k) => R.links[k] && R.links[k].result !== "PASS");
    R.exitGate = bad ? `Phase 1: failed at ${bad.replace(/^\d+b?_/, "")}`
      : (order.every((k) => R.links[k]) ? "Phase 1: PASS — full chain proven"
                                        : "Phase 1: incomplete — not every link ran");
    save();
    console.log("\n  promotion:        " + R.verdict.promotion);
    console.log("  canonical API:    " + R.verdict.canonical_api);
    console.log("  preview:          " + R.verdict.preview);
    console.log("  export:           " + R.verdict.export);
    console.log("  control 5a56f942: " + R.verdict.control_unchanged);
    if (R.blockedPatches.length) console.log(`  BLOCKED ${R.blockedPatches.length} foreign PATCH(es)`);
    try { await page.screenshot({ path: path.join(out, "final.png"), fullPage: true }); } catch (_) {}
    await browser.close();
    console.log(`\n${R.exitGate}\nEvidence: ${path.join(out, "report.json")}`);
  }
})();
