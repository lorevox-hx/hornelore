#!/usr/bin/env node
/*
 * Behavioural DOM test for the Bug Panel launcher contract.
 *
 * WHY THIS EXISTS. The first authorized live run (20260901T232656Z)
 * performed zero mutations and refused safely -- but it refused for a
 * reason no offline test could see. The probe opened the Bug Panel with:
 *
 *   const el = document.getElementById("lv10dBugPanelBtn") ||
 *              document.querySelector('[onclick*="BugPanel"],[id*="ugPanel"]');
 *   if (el) el.click();
 *
 * Three faults, none of which announced itself:
 *   - `lv10dBugPanelBtn` exists NOWHERE in the product; the real launcher
 *     is `#lv10dBugBtn`.
 *   - The panel is a NATIVE POPOVER opened by `popovertarget`, so there is
 *     no onclick anywhere to match.
 *   - `[id*="ugPanel"]` matched `#lv10dBugPanel` -- the popover container
 *     itself, which is inert and hidden. Clicking it does nothing.
 *
 * Then `if (el)` swallowed the miss, so the run continued and died 30
 * seconds later retrying a click on the story-review section header, which
 * was present in the DOM and invisible because the panel behind it had
 * never opened. Every offline test passed throughout: the file parsed, the
 * self-test was green, and the selector string was syntactically perfect.
 * Only a live run or this file can see a selector that matches nothing.
 *
 * SO THIS TEST DOES NOT WRITE A BUTTON. It EXTRACTS the launcher element
 * and the popover's opening tag verbatim from ui/hornelore1.0.html and
 * mounts those exact strings. Writing a plausible button here would test
 * my idea of the launcher, which is precisely the thing that was wrong.
 *
 * Offline. No server, no narrator, no mutation.
 */
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");

const HTML_PATH = path.join(__dirname, "..", "..", "ui", "hornelore1.0.html");
const HTML = fs.readFileSync(HTML_PATH, "utf8");

const LAUNCHER_ID = "lv10dBugBtn";
const POPOVER_ID = "lv10dBugPanel";
const MOUNT_ID = "lv10dBpStoryReview";

/* Pull the real <button id="lv10dBugBtn" …>…</button> out of the shipped
 * page. If the markup ever changes shape, this throws here rather than
 * quietly testing a stale copy. */
function extractLauncher() {
  const i = HTML.indexOf(`id="${LAUNCHER_ID}"`);
  if (i < 0) throw new Error(`no id="${LAUNCHER_ID}" in hornelore1.0.html`);
  const start = HTML.lastIndexOf("<button", i);
  const end = HTML.indexOf("</button>", i);
  if (start < 0 || end < 0) throw new Error("launcher is not a <button> element");
  return HTML.slice(start, end + "</button>".length);
}

function extractPopoverOpenTag() {
  const i = HTML.indexOf(`id="${POPOVER_ID}"`);
  if (i < 0) throw new Error(`no id="${POPOVER_ID}" in hornelore1.0.html`);
  const start = HTML.lastIndexOf("<", i);
  const end = HTML.indexOf(">", i);
  return HTML.slice(start, end + 1);
}

(async () => {
  let chromium;
  try { ({ chromium } = require("playwright")); }
  catch (_) {
    try { ({ chromium } = require("@playwright/test")); }
    catch (e) {
      console.error("CANNOT LOAD PLAYWRIGHT — run from /mnt/c/Users/chris/hornelore");
      process.exit(2);
    }
  }

  let failures = 0;
  const check = async (name, fn) => {
    try { await fn(); console.log("  PASS  " + name); }
    catch (e) { failures++; console.log("  FAIL  " + name + " — " + e.message); }
  };

  // ── the contract, pinned against the shipped page ────────────────────
  const launcherHTML = extractLauncher();
  const popoverTag = extractPopoverOpenTag();

  await check("the launcher is a real button carrying popovertarget", async () => {
    assert.ok(/^<button/.test(launcherHTML), "must be a <button>");
    assert.ok(launcherHTML.includes(`popovertarget="${POPOVER_ID}"`),
      "the launcher must drive the popover declaratively: " + launcherHTML);
    assert.ok(!/onclick=/.test(launcherHTML),
      "there is no onclick — a probe searching for one finds nothing");
  });

  await check("the popover container is inert, not a control", async () => {
    assert.ok(popoverTag.includes(" popover"),
      "the panel must carry the popover attribute: " + popoverTag);
    assert.ok(!popoverTag.includes("popovertarget"),
      "the container is NOT its own launcher; clicking it does nothing");
  });

  await check("the guessed id exists nowhere in the shipped page", async () => {
    assert.ok(!HTML.includes("lv10dBugPanelBtn"),
      "if this id ever appears, the probe's launcher choice must be revisited");
  });

  await check("exactly one launcher carries this id", async () => {
    const n = HTML.split(`id="${LAUNCHER_ID}"`).length - 1;
    assert.strictEqual(n, 1, `expected 1 #${LAUNCHER_ID}, found ${n}`);
  });

  await check("a second launcher exists elsewhere and is not the one to use",
    async () => {
      const n = HTML.split(`popovertarget="${POPOVER_ID}"`).length - 1;
      assert.strictEqual(n, 2,
        "two launchers are expected: the always-visible header button and"
        + " 'Open Full Bug Panel' in the operator launcher section");
      assert.ok(HTML.includes("Open Full Bug Panel"),
        "the second launcher should be the operator-launcher one");
    });

  // ── the behaviour, in a real browser ─────────────────────────────────
  const browser = await chromium.launch();
  const page = await browser.newPage();
  page.setDefaultTimeout(5000);
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(String(e && e.message || e)));

  // The REAL launcher markup and the REAL popover tag, nothing invented.
  await page.setContent(`
    <div id="shell">
      ${launcherHTML}
      ${popoverTag}
        <div id="${MOUNT_ID}">
          <div class="story-section-header">Story review</div>
        </div>
      </div>
    </div>`);

  const launcher = page.locator(`#${LAUNCHER_ID}`);
  const popoverState = () => page.evaluate((id) => {
    const p = document.getElementById(id);
    try { return { present: Boolean(p), open: p ? p.matches(":popover-open") : null }; }
    catch (e) { return { present: Boolean(p), open: null, error: String(e.message || e) }; }
  }, POPOVER_ID);

  await check("the browser supports :popover-open at all", async () => {
    const st = await popoverState();
    assert.strictEqual(st.present, true);
    assert.notStrictEqual(st.open, null,
      "this test is meaningless if the selector throws: " + JSON.stringify(st));
  });

  await check("the panel starts closed and its contents are not visible", async () => {
    const st = await popoverState();
    assert.strictEqual(st.open, false, "the popover must start closed");
    assert.strictEqual(await page.locator(`#${MOUNT_ID}`).isVisible(), false,
      "a closed popover's contents must not be visible");
    assert.strictEqual(
      await page.locator(`#${MOUNT_ID} .story-section-header`).isVisible(), false,
      "THE EXACT STATE THAT COST 30 SECONDS: present in the DOM, invisible");
  });

  await check("the section header resolves while still being unclickable", async () => {
    // The distinction the live failure turned on.
    assert.strictEqual(
      await page.locator(`#${MOUNT_ID} .story-section-header`).count(), 1,
      "it RESOLVES — which is why a count check passed and the click did not");
  });

  await check("clicking the inert popover container opens nothing", async () => {
    await page.evaluate((id) => {
      const el = document.getElementById(id);
      if (el) el.click();          // exactly what the old fallback did
    }, POPOVER_ID);
    const st = await popoverState();
    assert.strictEqual(st.open, false,
      "clicking the container must NOT open it — the old fallback's whole problem");
  });

  await check("clicking the real launcher opens the popover", async () => {
    assert.strictEqual(await launcher.count(), 1);
    assert.ok(await launcher.isVisible(), "the launcher must be visible");
    assert.ok(await launcher.isEnabled(), "the launcher must be enabled");
    await launcher.click();
    await page.waitForFunction((id) => {
      const p = document.getElementById(id);
      try { return Boolean(p && p.matches(":popover-open")); } catch (_) { return false; }
    }, POPOVER_ID, { timeout: 5000 });
    const st = await popoverState();
    assert.strictEqual(st.open, true);
  });

  await check("the section header becomes visible once the panel is open", async () => {
    assert.strictEqual(
      await page.locator(`#${MOUNT_ID} .story-section-header`).isVisible(), true,
      "only now is it a control the probe may click");
  });

  await check("offsetParent is NULL on an OPEN native popover — :popover-open is not",
    async () => {
      /* The false negative that cost Phase 1 a run. `#memoirScrollPopover`
       * is `<div popover="auto">`; native popovers render in the TOP LAYER,
       * which the UA stylesheet positions `fixed`, and `offsetParent` is
       * null for every fixed element. PANEL_STATE tested
       * `offsetParent !== null` and reported a visible panel as shut while
       * reading 1408 characters out of it. */
      const st = await page.evaluate((id) => {
        const p = document.getElementById(id);
        const r = p.getBoundingClientRect();
        return {
          open: p.matches(":popover-open"),
          offsetParentIsNull: p.offsetParent === null,
          hasBox: r.width > 0 || r.height > 0,
          position: getComputedStyle(p).position,
        };
      }, POPOVER_ID);
      assert.strictEqual(st.open, true, "the popover is open at this point");
      assert.strictEqual(st.position, "fixed",
        "native popovers are fixed-position in the top layer");
      assert.strictEqual(st.offsetParentIsNull, true,
        "THE TRAP: offsetParent is null even though the popover is open");
      assert.strictEqual(st.hasBox, true, "and it genuinely occupies a box");
    });

  await check("the probe no longer infers popover visibility from offsetParent",
    async () => {
      const src = fs.readFileSync(
        path.join(__dirname, "phase1_memoir_chain_probe.js"), "utf8");
      const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
      assert.ok(!code.includes("offsetParent"),
        "offsetParent must not decide visibility anywhere in the probe");
      assert.ok(code.includes('matches(":popover-open")'),
        "the platform's own open-state must be the basis");
    });

  await check("no page exception was raised", async () => {
    assert.deepStrictEqual(pageErrors, []);
  });

  await browser.close();
  console.log(failures
    ? `\n${failures} FAILED`
    : "\nALL PASS — launcher contract pinned against hornelore1.0.html");
  process.exit(failures ? 1 : 0);
})();
