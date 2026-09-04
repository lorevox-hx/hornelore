#!/usr/bin/env node
/*
 * Behavioural DOM test for the MEMOIR popover contract.
 *
 * WHY THIS EXISTS. Phase 1 resume `20260904T125523Z` reported
 * `popoverVisible=false` while the same call read `occurrences=1` and 1408
 * characters of the passage out of the panel. The passage was on screen and
 * the probe said the panel was shut.
 *
 * `#memoirScrollPopover` is `<div popover="auto">`. Native popovers render
 * in the TOP LAYER, which the UA stylesheet positions `fixed`, and
 * `offsetParent` is `null` for every fixed-position element. So
 * `offsetParent !== null` is a guaranteed FALSE NEGATIVE on an OPEN popover.
 *
 * The same rule had already been learned once, on the Bug Panel, and written
 * into CLAUDE.md. It was applied there and not here — which is how one
 * defect surfaced twice a fortnight apart. This file exists so the memoir
 * popover has its own proof rather than inheriting an assumption.
 *
 * NOTHING IS INVENTED. The popover's opening tag and a real shipped control
 * that opens it are EXTRACTED verbatim from ui/hornelore1.0.html. Writing a
 * plausible popover here would test this author's idea of one, which is
 * exactly the class of mistake being corrected.
 *
 * Offline. No server, no narrator, no mutation.
 */
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const P = require("./phase1_memoir_chain_probe.js");
const { PANEL_STATE } = P;

const HTML_PATH = path.join(__dirname, "..", "..", "ui", "hornelore1.0.html");
const HTML = fs.readFileSync(HTML_PATH, "utf8");

const POPOVER_ID = "memoirScrollPopover";
const PASSAGE = "I went to Kent State for my education degree. That was 1966. "
  + "Kent State was about an hour from home and it was the first time I had "
  + "ever been away from Akron for more than a weekend.";

function extractPopoverOpenTag() {
  const i = HTML.indexOf(`id="${POPOVER_ID}"`);
  if (i < 0) throw new Error(`no id="${POPOVER_ID}" in hornelore1.0.html`);
  return HTML.slice(HTML.lastIndexOf("<", i), HTML.indexOf(">", i) + 1);
}

/* A real shipped control that opens it. `#lv80PeekBtn` carries
 * popovertarget="memoirScrollPopover" — declarative, no script needed. */
function extractPeekButton() {
  const i = HTML.indexOf(`popovertarget="${POPOVER_ID}"`);
  if (i < 0) throw new Error("no popovertarget control for the memoir popover");
  const start = HTML.lastIndexOf("<button", i);
  const end = HTML.indexOf("</button>", i);
  if (start < 0 || end < 0) throw new Error("the memoir control is not a <button>");
  return HTML.slice(start, end + "</button>".length);
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

  const popoverTag = extractPopoverOpenTag();
  const peekButton = extractPeekButton();

  await check("the memoir panel is a NATIVE popover in the shipped page", async () => {
    assert.ok(popoverTag.includes("popover"),
      "if this stops being a popover, PANEL_STATE's basis must be revisited: " + popoverTag);
    assert.ok(/popover="auto"/.test(popoverTag), "expected popover=\"auto\": " + popoverTag);
  });

  await check("a real shipped control drives it declaratively", async () => {
    assert.ok(/^<button/.test(peekButton));
    assert.ok(peekButton.includes(`popovertarget="${POPOVER_ID}"`),
      "the control must target the popover: " + peekButton);
  });

  const browser = await chromium.launch();
  const page = await browser.newPage();
  page.setDefaultTimeout(5000);
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(String(e && e.message || e)));

  // Shipped markup only, plus the passage as canonical would render it.
  await page.setContent(`
    <div id="shell">
      ${peekButton}
      ${popoverTag}
        <div class="memoir-body"><p>${PASSAGE}</p></div>
      </div>
    </div>`);

  const raw = () => page.evaluate((id) => {
    const p = document.getElementById(id);
    const r = p.getBoundingClientRect();
    return {
      open: p.matches(":popover-open"),
      offsetParentIsNull: p.offsetParent === null,
      position: getComputedStyle(p).position,
      hasBox: r.width > 0 || r.height > 0,
    };
  }, POPOVER_ID);

  await check("it starts closed, and PANEL_STATE agrees", async () => {
    const st = await raw();
    assert.strictEqual(st.open, false);
    const ps = await page.evaluate(PANEL_STATE, PASSAGE);
    assert.strictEqual(ps.present, true, "the element exists even when closed");
    assert.strictEqual(ps.visible, false);
    assert.strictEqual(ps.popoverOpen, false);
  });

  await check("the shipped control OPENS it and it matches :popover-open", async () => {
    await page.locator(`[popovertarget="${POPOVER_ID}"]`).click();
    await page.waitForFunction((id) => {
      const p = document.getElementById(id);
      try { return Boolean(p && p.matches(":popover-open")); } catch (_) { return false; }
    }, POPOVER_ID, { timeout: 5000 });
    const st = await raw();
    assert.strictEqual(st.open, true);
  });

  await check("THE TRAP: offsetParent is null on the OPEN popover", async () => {
    const st = await raw();
    assert.strictEqual(st.open, true, "precondition: it is open");
    assert.strictEqual(st.position, "fixed",
      "native popovers are fixed-position in the top layer");
    assert.strictEqual(st.offsetParentIsNull, true,
      "offsetParent is null even though the popover is OPEN — the false negative "
      + "that made run 20260904T125523Z report a visible panel as shut");
    assert.strictEqual(st.hasBox, true, "and it genuinely occupies a box");
  });

  await check("PANEL_STATE reports it VISIBLE, with the passage exactly once",
    async () => {
      const ps = await page.evaluate(PANEL_STATE, PASSAGE);
      assert.strictEqual(ps.visible, true,
        "the old offsetParent basis returned false here");
      assert.strictEqual(ps.popoverOpen, true);
      assert.strictEqual(ps.occurrences, 1, "the passage must appear exactly once");
      assert.ok(ps.chars > 0);
    });

  await check("closing it makes :popover-open false and PANEL_STATE follow",
    async () => {
      await page.evaluate((id) => document.getElementById(id).hidePopover(), POPOVER_ID);
      await page.waitForFunction((id) => {
        const p = document.getElementById(id);
        return p && !p.matches(":popover-open");
      }, POPOVER_ID, { timeout: 5000 });
      const ps = await page.evaluate(PANEL_STATE, PASSAGE);
      assert.strictEqual(ps.visible, false, "a closed popover is not visible");
      assert.strictEqual(ps.popoverOpen, false);
      assert.strictEqual(ps.present, true, "but the element is still present");
      // The text is still in the DOM: presence of text is NOT openness.
      assert.strictEqual(ps.occurrences, 1,
        "the passage remains in the closed panel — which is precisely why "
        + "occurrences cannot be used as an openness signal either");
    });

  await check("offsetParent is not the verdict anywhere in the probe", async () => {
    const src = fs.readFileSync(
      path.join(__dirname, "phase1_memoir_chain_probe.js"), "utf8");
    const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
    assert.ok(!code.includes("offsetParent"),
      "offsetParent must not decide visibility anywhere in the probe");
    assert.ok(code.includes('el.matches(":popover-open")'));
  });

  await check("no page exception was raised", async () => {
    assert.deepStrictEqual(pageErrors, []);
  });

  await browser.close();
  console.log(failures
    ? `\n${failures} FAILED`
    : "\nALL PASS — memoir popover contract pinned against hornelore1.0.html");
  process.exit(failures ? 1 : 0);
})();
