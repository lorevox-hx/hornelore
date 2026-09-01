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
if (typeof module !== "undefined") {
  module.exports = { SELECT_ROW, OPEN_DETAIL, VERIFY_ROW, ACTIVE_OK,
                     OPEN_MEMOIR_STAGE1, OPEN_MEMOIR_STAGE2, PANEL_STATE,
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
  console.log("SELF-TEST PASS — envelope, digest, two-stage memoir, pathname guard, exit code");
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
  const l3 = (p.links || {})["3_promoted"], l7 = (p.links || {})["7_control_unchanged"];
  if (!(p.promotedCandidateId === TARGET && l3 && l3.result === "PASS"
        && l7 && l7.result === "PASS")) {
    console.error(`--resume ${resumeId}: needs a prior run with target promotion PASS`
      + " AND control-unchanged PASS"); process.exit(2);
  }
  prior = { runId: resumeId, promotedCandidateId: p.promotedCandidateId,
            promotedAt: p.promotedAt, immutable: p.immutableBefore || null,
            chain: ((p.resumedFrom && p.resumedFrom.chain) || []).concat(resumeId) };
}

const out = path.join(ROOT, new Date().toISOString().replace(/[-:.]/g, "").slice(0, 15) + "Z");
fs.mkdirSync(path.join(out, "downloads"), { recursive: true });
const R = { startedAt: new Date().toISOString(), outDir: out, links: {}, refusals: [],
            resumedFrom: prior, promotedCandidateId: prior ? prior.promotedCandidateId : null,
            promotedAt: prior ? prior.promotedAt : null,
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
    // PATCH guard: exact pathname match, not a substring anywhere in the URL.
    const refuseForeignPatch = async (route) => {
      const req = route.request();
      if (req.method() === "PATCH") {
        const seg = new URL(req.url()).pathname.split("/").filter(Boolean).pop();
        if (seg !== TARGET) {
          R.blockedPatches.push({ url: req.url(), pathnameCandidate: seg, at: new Date().toISOString() });
          R.refusals.push("BLOCKED a PATCH to candidate " + seg);
          save(); return route.abort("blockedbyclient");
        }
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
    const eraList = it.era_candidates || [];
    const eraOK = Array.isArray(eraList)
      ? eraList.some((e) => (e && (e.era_id || e.era || e)) === ERA)
      : eraList === ERA;

    const checks = [
      ["detail readable (narrator_id supplied)", before.ok && Boolean(before.item)],
      ["candidate id exact", it.id === TARGET],
      ["narrator is Pat", it.narrator_id === PERSON],
      ["conversation_id recorded", Boolean(it.conversation_id)],
      ["session_id recorded", Boolean(it.session_id)],
      ["source user turn row recorded", it.source_user_turn_row_id != null],
      ["completed assistant turn row recorded", it.completed_assistant_turn_row_id != null],
      ["placement is building_years", eraOK],
      ["review_version present", it.review_version != null],
      ["status correct for mode", prior ? status === "promoted"
        : ["unreviewed", "in_review"].includes(String(status))],
      ["control readable", ctlPre.ok && Boolean(ctlPre.item)],
    ];
    R.preconditions = checks.map(([n, ok]) => ({ check: n, pass: Boolean(ok) }));
    const failed = checks.filter(([, ok]) => !ok).map(([n]) => n);
    if (failed.length) {
      R.refusals.push("REFUSED before promotion: " + failed.join("; "));
      step("1_preconditions", { result: "REFUSED", detail: failed.join("; "),
        observedItemKeys: Object.keys(it) });
      throw new Error("preconditions not met — nothing was changed");
    }
    step("1_preconditions", { result: "PASS",
      detail: `status=${status} version=${it.review_version} era=${ERA}`,
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
      note: "the only promote control lives in the Bug Panel — Phase 7 gap, not fixed here" });
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

    // ── 3: promote, verify body and immutability ─────────────────────
    const already = status === "promoted";
    if (already && prior) {
      console.log(`  [3] resume — promoted by ${prior.runId}; NOT re-promoting`);
    } else {
      const reassert = await page.evaluate(ACTIVE_OK, { personId: PERSON, displayName: DISPLAY_NAME });
      if (!reassert.ok) throw new Error("active narrator changed before promotion");
      const btn = page.locator(".story-row", { hasText: PASSAGE_HEAD }).locator(".story-act-promote");
      if (await btn.count() !== 1) {
        R.refusals.push("REFUSED: promote control in the target row is not unique");
        step("3_promoted", { result: "REFUSED", detail: "promote control not unique" });
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
      const unrelated = sent ? Object.keys(sent).filter((k) =>
        !["review_status", "review_version", "narrator_id"].includes(k)) : [];
      R.observed.patch = pr ? { url: pr.url(), pathnameCandidate: seg, status: pr.status(),
        sentBody: sent, responseItem: resItem ? pick(resItem,
          ["id", "narrator_id", "review_status", "review_version"]) : null,
        bodyNarratorIsPat: Boolean(sent && sent.narrator_id === PERSON),
        bodyStatusPromoted: Boolean(sent && sent.review_status === "promoted"),
        bodyVersionMatches: Boolean(sent && sent.review_version === it.review_version),
        unrelatedEdits: unrelated } : null;
      const p = R.observed.patch;
      if (p && seg === TARGET && p.status < 400 && p.bodyNarratorIsPat
          && p.bodyStatusPromoted && p.bodyVersionMatches && !unrelated.length
          && p.responseItem && p.responseItem.id === TARGET
          && p.responseItem.narrator_id === PERSON
          && p.responseItem.review_status === "promoted") {
        R.promotedCandidateId = TARGET; R.promotedAt = new Date().toISOString(); save();
      } else {
        R.refusals.push("no promotion proof recorded: PATCH missing, foreign or non-conforming");
      }
      await page.waitForTimeout(2000);
    }
    const after = await candidate(TARGET);
    const ai = after.item || {};
    const immutableAfter = pick(ai, IMMUTABLE);
    const immutableSame = JSON.stringify(R.immutableBefore) === JSON.stringify(immutableAfter);
    step("3_promoted", {
      result: (ai.review_status === "promoted" && immutableSame
               && !R.blockedPatches.length
               && (already && prior ? true : Boolean(R.promotedCandidateId))) ? "PASS" : "FAIL",
      detail: `status=${ai.review_status} immutableProvenanceUnchanged=${immutableSame}`
            + (already && prior ? " (carried from resume)" : ""),
      observedPatch: R.observed.patch, blockedForeignPatches: R.blockedPatches.length,
      immutableBefore: R.immutableBefore, immutableAfter: immutableAfter, allPatches: patchSeen });
    R.immutableAfter = immutableAfter;
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
      promotion: g("3_promoted"), canonical_api: g("4_canonical"),
      preview: g("5_preview") === "PASS" ? "passed"
        : ((R.observed.canonicalRequests || []).some((c) => c.forPat && c.status === 404)
            ? "failed — wrong API origin" : "failed"),
      export: g("6_export") === "PASS" ? "passed"
        : (g("5_preview") === "PASS" ? "failed" : "not reached through accepted UI path"),
      control_unchanged: g("7_control_unchanged"),
    };
    const order = ["1_preconditions", "1b_narrator_active", "2a_filter", "2_row_located",
                   "2b_detail_verified", "3_promoted", "4_canonical", "5_preview",
                   "6_export", "8_agreement", "7_control_unchanged"];
    const bad = order.find((k) => R.links[k] && R.links[k].result !== "PASS");
    const complete = order.every((k) => R.links[k]);
    R.exitGate = bad ? `Phase 1: failed at ${bad.replace(/^\d+[ab]?_/, "")}`
      : (complete ? "Phase 1: PASS — full chain proven" : "Phase 1: incomplete — not every link ran");
    save();
    console.log("\n  promotion:        " + R.verdict.promotion);
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
