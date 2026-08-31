#!/usr/bin/env node
/*
 * Narrator-room layout evidence at three viewports.
 *
 * WHY THIS EXISTS AND WHY IT IS NOT A NEW HARNESS LAYER
 * ─────────────────────────────────────────────────────
 * `1066061` was verified live at 690px only, because the Chrome pane the
 * verification ran in is fixed at 690 — `resize_window` reports success
 * and `window.innerWidth` never moves. 900px and desktop were reported
 * as NOT VERIFIED rather than assumed. This closes that gap and nothing
 * else: it measures, screenshots, and asserts. It changes no product
 * code, creates no narrator, sends no model turn, and writes only into
 * its own report directory.
 *
 * Usage, from the repo root with the stack up:
 *
 *   node scripts/ui/run_narrator_room_viewports.js \
 *     --person-id c6f78b9b-612e-43d7-a518-9bc2fbc45995
 *
 * Optional: --ui <url>  --out <dir>  --headed
 */
"use strict";

const fs = require("fs");
const path = require("path");

const VIEWPORTS = [
  // The width the live session already proved. Re-run because the
  // topbar and drawer landed after that composer check.
  { name: "690",  width: 690,  height: 900,  expectDrawer: true  },
  // Inside the drawer breakpoint (1100) and inside the topbar
  // compaction breakpoint (900).
  { name: "900",  width: 900,  height: 900,  expectDrawer: true  },
  // Above both. The Life Map must come back as an ordinary column.
  { name: "1440", width: 1440, height: 900,  expectDrawer: false },
];

function parseArgs(argv) {
  const out = { ui: "http://localhost:8082/ui/hornelore1.0.html",
                out: ".runtime/eval/narrator-room-viewports", headed: false };
  for (let i = 0; i < argv.length; i += 1) {
    const k = argv[i];
    if (k === "--headed") { out.headed = true; continue; }
    if (!k.startsWith("--")) throw new Error(`unexpected argument: ${k}`);
    const v = argv[++i];
    if (!v || v.startsWith("--")) throw new Error(`missing value for ${k}`);
    out[k.slice(2).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = v;
  }
  if (!out.personId) throw new Error("--person-id is required (an exact UUID)");
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
        .test(out.personId)) {
    throw new Error("--person-id must be an exact UUID");
  }
  return out;
}

/* The narrator list re-renders, so the selector carries the UUID and is
 * re-resolved at click time. Same lesson as the cohort helper: a
 * collected elementHandle is stale by the time it is used. */
async function openNarrator(page, personId) {
  await page.waitForFunction(
    (pid) => Array.from(document.querySelectorAll("button")).some((b) =>
      b.textContent.trim() === "Open" &&
      (b.getAttribute("onclick") || "").includes(pid)),
    personId, { timeout: 30000 });
  await page.locator(`button[onclick*="${personId}"]`)
    .filter({ hasText: /^Open$/ }).click({ timeout: 30000 });
  await page.waitForFunction(
    (pid) => window.state && window.state.person_id === pid,
    personId, { timeout: 60000 });
}

async function measure(page) {
  return page.evaluate(() => {
    const box = (sel) => {
      const e = document.querySelector(sel);
      if (!e) return null;
      const r = e.getBoundingClientRect();
      return { w: Math.round(r.width), h: Math.round(r.height),
               display: getComputedStyle(e).display,
               visible: r.width > 0 && r.height > 0 };
    };
    const erasOnScreen = () => Array.from(
      document.querySelectorAll(".lv-interview-lifemap-era-btn"))
      .filter((b) => {
        const q = b.getBoundingClientRect();
        return q.width > 0 && q.right <= window.innerWidth + 1;
      }).length;
    return {
      innerWidth: window.innerWidth,
      topbar: box(".lv-narrator-topbar"),
      main: box(".lv-narrator-main"),
      chat: box("#chatMessages"),
      input: box("#chatInput"),
      send: box("#lv80SendBtn"),
      mic: box("#btnMic"),
      lifemap: box("#lvInterviewLifeMap"),
      drawerBtn: box("#lvLifeMapDrawerBtn"),
      psSection: box("#psOnboardingSection"),
      psBtn: box("#psPauseBtn"),
      erasOnScreen: erasOnScreen(),
      eraSelected: (window.state && window.state.session &&
                    window.state.session.currentEra) || null,
      clockHidden: (() => { const c = document.getElementById("lvClock");
                            return c ? c.hidden : "absent"; })(),
    };
  });
}

async function run() {
  const args = parseArgs(process.argv.slice(2));
  let chromium;
  try { ({ chromium } = require("playwright")); }
  catch (_) { ({ chromium } = require("@playwright/test")); }

  const outDir = path.resolve(args.out);
  const shots = path.join(outDir, "screenshots");
  fs.mkdirSync(shots, { recursive: true });

  const report = { startedAt: new Date().toISOString(), ui: args.ui,
                   personId: args.personId, viewports: [], problems: [] };
  const browser = await chromium.launch({ headless: !args.headed });

  try {
    for (const vp of VIEWPORTS) {
      const ctx = await browser.newContext({
        viewport: { width: vp.width, height: vp.height } });
      const page = await ctx.newPage();
      const consoleErrors = [];
      page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });

      const row = { viewport: vp.name, expected: vp, checks: {}, consoleErrors };
      try {
        await page.goto(args.ui, { waitUntil: "domcontentloaded", timeout: 60000 });
        await openNarrator(page, args.personId);
        await page.locator("#lvShellTabNarrator").click();
        await page.waitForTimeout(1500);

        row.closed = await measure(page);
        await page.screenshot({ path: path.join(shots, `${vp.name}-closed.png`),
                                fullPage: false });

        // ── The drawer, if this width has one ──────────────────────
        const hasToggle = row.closed.drawerBtn && row.closed.drawerBtn.visible;
        row.checks.drawerToggleVisible = hasToggle;
        row.checks.drawerToggleExpected = vp.expectDrawer;
        row.checks.drawerToggleCorrect = hasToggle === vp.expectDrawer;

        if (hasToggle) {
          const eraBefore = row.closed.eraSelected;
          await page.locator("#lvLifeMapDrawerBtn").click();
          await page.waitForTimeout(400);
          row.opened = await measure(page);
          await page.screenshot({ path: path.join(shots, `${vp.name}-open.png`) });
          await page.locator("#lvLifeMapDrawerBtn").click();
          await page.waitForTimeout(400);
          const after = await measure(page);
          row.checks.erasReachableWhenOpen = row.opened.erasOnScreen;
          row.checks.eraPreserved = eraBefore === after.eraSelected;
          row.checks.closedHidesLifeMap = row.closed.lifemap.display === "none";
        } else {
          // Above the breakpoint the Life Map is an ordinary column.
          row.checks.lifeMapIsColumn =
            !!row.closed.lifemap && row.closed.lifemap.visible &&
            row.closed.lifemap.display !== "none";
          row.checks.erasReachableAsColumn = row.closed.erasOnScreen;
        }

        // ── REAL TYPING. No programmatic value injection. ──────────
        const probe = `viewport ${vp.name} typing probe`;
        await page.locator("#chatInput").click();
        await page.locator("#chatInput").type(probe, { delay: 8 });
        const typed = await page.inputValue("#chatInput");
        row.checks.typedChars = typed.length;
        row.checks.typingWorks = typed === probe;
        // Cleared, NOT sent: this instrument sends no model turn.
        await page.fill("#chatInput", "");

        /* ── THE PROFILE SEED CARD IS ON THE OPERATOR TAB ──────────
         *
         * The first run reported it "not visible" at all three widths
         * and that was THIS SCRIPT's error, not the product's: every
         * measurement above is taken on the Narrator Session tab, where
         * operator chrome is correctly absent. Progress like "7 of 10"
         * must never appear in the narrator's room — design principle 2
         * — so checking for it there was asking the product to fail.
         *
         * Switch tabs, measure it where it lives, and switch back. */
        await page.locator("#lvShellTabOperator").click();
        await page.waitForTimeout(800);
        row.operator = await page.evaluate(() => {
          const b = (sel) => { const e = document.querySelector(sel);
            if (!e) return null; const r = e.getBoundingClientRect();
            return { w: Math.round(r.width), h: Math.round(r.height),
                     visible: r.width > 0 && r.height > 0 }; };
          const btn = document.getElementById("psPauseBtn");
          return {
            psSection: b("#psOnboardingSection"),
            psBtn: b("#psPauseBtn"),
            psLabel: btn ? btn.textContent.trim() : null,
            psAria: btn ? btn.getAttribute("aria-label") : null,
            psKeyboardReachable: btn ? btn.tabIndex >= 0 : false,
            progress: (document.getElementById("psProgress") || {}).textContent || null,
          };
        });
        await page.screenshot({ path: path.join(shots, `${vp.name}-operator.png`) });
        await page.locator("#lvShellTabNarrator").click();
        await page.waitForTimeout(600);

        row.checks.composerUsable = row.closed.input.w >= 240;
        row.checks.sendVisible = !!row.closed.send && row.closed.send.visible;
        row.checks.micVisible = !!row.closed.mic && row.closed.mic.visible;
        row.checks.psVisible = !!row.operator.psBtn && row.operator.psBtn.visible;
        row.checks.psLabelled = /Profile Seed/.test(row.operator.psLabel || "");
        row.checks.psKeyboardReachable = row.operator.psKeyboardReachable;
        row.checks.topbarShare = row.closed.main && row.closed.topbar
          ? +(row.closed.topbar.h /
              (row.closed.topbar.h + row.closed.main.h)).toFixed(2) : null;
      } catch (err) {
        row.error = String((err && err.stack) || err);
        report.problems.push(`${vp.name}: ${err && err.message}`);
      }
      report.viewports.push(row);
      await ctx.close();
    }
  } finally {
    await browser.close();
  }

  report.finishedAt = new Date().toISOString();
  const failed = [];
  for (const r of report.viewports) {
    const c = r.checks || {};
    if (r.error) { failed.push(`${r.viewport}: threw`); continue; }
    if (c.drawerToggleCorrect === false) failed.push(`${r.viewport}: drawer toggle visibility wrong`);
    if (c.typingWorks === false) failed.push(`${r.viewport}: real typing failed`);
    if (c.composerUsable === false) failed.push(`${r.viewport}: composer too narrow`);
    if (c.sendVisible === false) failed.push(`${r.viewport}: Send not visible`);
    if (c.micVisible === false) failed.push(`${r.viewport}: mic not visible`);
    if (c.psVisible === false) failed.push(`${r.viewport}: Profile Seed button not visible on the Operator tab`);
    if (c.psLabelled === false) failed.push(`${r.viewport}: Profile Seed button is not labelled as such`);
    if (c.psKeyboardReachable === false) failed.push(`${r.viewport}: Profile Seed button not keyboard reachable`);
    if (c.eraPreserved === false) failed.push(`${r.viewport}: drawer changed the selected era`);
    if (c.erasReachableWhenOpen === 0) failed.push(`${r.viewport}: no eras reachable in the open drawer`);
    if (c.lifeMapIsColumn === false) failed.push(`${r.viewport}: Life Map did not return as a column`);
  }
  report.failures = failed;
  report.ok = failed.length === 0;

  fs.writeFileSync(path.join(outDir, "viewports.json"),
                   `${JSON.stringify(report, null, 2)}\n`, "utf8");

  for (const r of report.viewports) {
    const c = r.checks || {};
    console.log(`\n── ${r.viewport}px ─────────────────────────────`);
    if (r.error) { console.log("  THREW:", r.error.split("\n")[0]); continue; }
    console.log(`  topbar ${r.closed.topbar.h}px / conversation ${r.closed.main.h}px` +
                `  (topbar share ${c.topbarShare})`);
    console.log(`  chat ${r.closed.chat.w}px · composer ${r.closed.input.w}px` +
                ` · typed ${c.typedChars} chars`);
    console.log(`  drawer toggle ${c.drawerToggleVisible ? "visible" : "hidden"}` +
                ` (expected ${c.drawerToggleExpected ? "visible" : "hidden"})`);
    if (c.erasReachableWhenOpen !== undefined)
      console.log(`  eras in open drawer: ${c.erasReachableWhenOpen}` +
                  ` · era preserved: ${c.eraPreserved}`);
    if (c.erasReachableAsColumn !== undefined)
      console.log(`  eras in column: ${c.erasReachableAsColumn}`);
    console.log(`  Profile Seed (Operator tab): visible ${c.psVisible}` +
                ` · "${(r.operator||{}).psLabel}" · keyboard ${c.psKeyboardReachable}`);
    console.log(`  console errors: ${r.consoleErrors.length}`);
  }
  console.log(`\n${report.ok ? "PASS" : "FAIL"} — report: ${path.join(outDir, "viewports.json")}`);
  if (!report.ok) failed.forEach((f) => console.log("  ✗", f));
  process.exitCode = report.ok ? 0 : 1;
}

run().catch((e) => { process.stderr.write(`${(e && e.stack) || e}\n`); process.exitCode = 2; });
