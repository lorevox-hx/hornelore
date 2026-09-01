#!/usr/bin/env node
/*
 * Behavioural DOM test for the Phase 1 probe's row-selection contract.
 *
 * WHY THIS EXISTS. Every earlier guard was a source-string assertion, and
 * they all passed against code that could not work: the probe searched for
 * getAttribute("onclick") while bug-panel-story-review.js:168 attaches
 * handlers with addEventListener. A grep cannot see that. This builds a
 * synthetic Bug Panel with REAL addEventListener handlers, matching the
 * shipped class names, and runs the probe's OWN exported functions against
 * it. If the contract drifts, this fails; a grep would not.
 */
"use strict";
const assert = require("assert");
const { SELECT_ROW, OPEN_DETAIL, VERIFY_ROW } = require("./phase1_memoir_chain_probe.js");

const TARGET_TEXT = "I went to Kent State for my education degree. That was 1966. "
  + "Kent State was about an hour from home and it was the first time I had "
  + "ever been away from Akron for more than a weekend.";
const HEAD = "I went to Kent State for my education degree.";
const OTHER = "I was born in Akron, Ohio, on the seventeenth of April in 1948.";

// Rows built exactly as the panel builds them: handlers via addEventListener.
const PAGE = `
<div class="story-list">
  <div class="story-row" id="row-other">
    <button class="story-preview story-preview-btn">${OTHER}</button>
  </div>
  <div class="story-row" id="row-target">
    <button class="story-preview story-preview-btn">${HEAD} …</button>
  </div>
</div>
<script>
  // The shipped panel never sets an onclick ATTRIBUTE.
  document.querySelectorAll('.story-preview-btn').forEach(function (b) {
    b.addEventListener('click', function () {
      var row = b.closest('.story-row');
      if (row.querySelector('.story-detail')) return;
      var d = document.createElement('div'); d.className = 'story-detail';
      var t = document.createElement('div'); t.className = 'story-transcript';
      t.textContent = row.id === 'row-target'
        ? ${JSON.stringify(TARGET_TEXT)} : ${JSON.stringify(OTHER)};
      d.appendChild(t);
      var acts = document.createElement('div'); acts.className = 'story-actions';
      var p = document.createElement('button');
      p.className = 'story-act story-act-promote'; p.textContent = 'Promote';
      p.addEventListener('click', function () { window.__promotedRow = row.id; });
      acts.appendChild(p); d.appendChild(acts); row.appendChild(d);
    });
  });
</script>`;

(async () => {
  let chromium;
  try { ({ chromium } = require("playwright")); }
  catch (_) { ({ chromium } = require("@playwright/test")); }
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setContent(PAGE);
  let failures = 0;
  const check = async (name, fn) => {
    try { await fn(); console.log("  PASS  " + name); }
    catch (e) { failures++; console.log("  FAIL  " + name + " — " + e.message); }
  };

  await check("selects exactly one row by the target passage", async () => {
    const r = await page.evaluate(SELECT_ROW, HEAD);
    assert.strictEqual(r.rows, 2, "fixture should have two rows");
    assert.strictEqual(r.matching, 1, "exactly one row must match");
    assert.ok(r.ok);
  });

  await check("refuses when the passage matches no row", async () => {
    const r = await page.evaluate(SELECT_ROW, "a passage nobody spoke");
    assert.strictEqual(r.matching, 0);
    assert.strictEqual(r.ok, false);
  });

  await check("no detail is open before clicking", async () => {
    const n = await page.evaluate(() => document.querySelectorAll(".story-detail").length);
    assert.strictEqual(n, 0);
  });

  await check("clicking .story-preview-btn opens the detail (addEventListener)", async () => {
    const o = await page.evaluate(OPEN_DETAIL, HEAD);
    assert.strictEqual(o.clicked, true);
    const open = await page.evaluate(() =>
      document.querySelectorAll("#row-target .story-detail").length);
    assert.strictEqual(open, 1, "the TARGET row's detail must open");
  });

  await check("an onclick-attribute search would have found nothing", async () => {
    const attrs = await page.evaluate(() => Array.from(
      document.querySelectorAll(".story-preview-btn"))
      .filter((b) => b.getAttribute("onclick")).length);
    assert.strictEqual(attrs, 0,
      "the shipped panel uses addEventListener; the old approach was unworkable");
  });

  await check("the opened row's transcript equals the complete target passage", async () => {
    const v = await page.evaluate(([h, f]) => VERIFY_ROW(h, f), [HEAD, TARGET_TEXT]);
    assert.strictEqual(v.detailOpen, true);
    assert.strictEqual(v.transcriptEqualsTarget, true);
  });

  await check("a partial passage does NOT satisfy the equality check", async () => {
    const v = await page.evaluate(([h, f]) => VERIFY_ROW(h, f), [HEAD, HEAD]);
    assert.strictEqual(v.transcriptEqualsTarget, false,
      "the head alone must not pass as the full transcript");
  });

  await check("exactly one promote control exists inside the target row", async () => {
    const v = await page.evaluate(([h, f]) => VERIFY_ROW(h, f), [HEAD, TARGET_TEXT]);
    assert.strictEqual(v.promoteControlsInRow, 1);
  });

  await check("row-scoped promotion clicks the TARGET row, not the other", async () => {
    await page.evaluate(OPEN_DETAIL, OTHER);          // open the other row too
    const total = await page.evaluate(() =>
      document.querySelectorAll(".story-act-promote").length);
    assert.strictEqual(total, 2, "both rows now expose a promote control");
    // This is the defect the whole correction exists for: a global first()
    // would hit row-other. Row-scoped selection must hit row-target.
    await page.evaluate((h) => {
      const row = Array.from(document.querySelectorAll(".story-row")).find((r) =>
        (r.querySelector(".story-preview-btn").textContent || "").includes(h));
      row.querySelector(".story-act-promote").click();
    }, HEAD);
    const promoted = await page.evaluate(() => window.__promotedRow);
    assert.strictEqual(promoted, "row-target",
      "a global first() would have promoted row-other — the control candidate");
  });

  await browser.close();
  console.log(failures ? `\nDOM TEST FAILED — ${failures} failure(s)` : "\nDOM TEST PASS");
  process.exit(failures ? 1 : 0);
})();
