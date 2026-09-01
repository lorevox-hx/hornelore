#!/usr/bin/env node
/*
 * Behavioural DOM test for the Phase 1 PLACEMENT workflow.
 *
 * WHY THIS EXISTS, AND WHY IT LOADS THE REAL FILE.
 *
 * The row-selection test builds a synthetic panel that imitates the
 * shipped one. That was enough to catch the addEventListener bug, but it
 * cannot catch a drift in the panel's own logic, because the fixture IS
 * the assertion -- if bug-panel-story-review.js changed how it builds a
 * PATCH body tomorrow, a hand-written imitation of yesterday's body would
 * still pass.
 *
 * So this test injects ui/js/bug-panel-story-review.js ITSELF into the
 * page, stubs only the network and the narrator, and then does what an
 * operator does: open the row, choose an era, press Save placement /
 * notes, and press Promote. The bodies asserted here are the bodies the
 * shipped panel actually produced.
 *
 * The three contracts under test, each of which has already been got
 * wrong once:
 *   1. Choosing an era must set placement_source=operator_set in the SAME
 *      action, and the save must NOT carry review_status.
 *   2. selectOption must fire the event the handler listens for. The
 *      handler is `oninput`; a test that dispatched `change` would pass
 *      while the live probe silently set nothing.
 *   3. Promote must send the version the PLACEMENT returned. The panel
 *      sends `item.review_version` -- the version it last rendered -- so a
 *      probe that promotes without refetching sends a stale number and
 *      takes a 409.
 *
 * Offline. No server, no narrator, no mutation of anything real.
 */
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const P = require("./phase1_memoir_chain_probe.js");
const { PLACEMENT_PATCH_OK, PROMOTION_PATCH_OK, UNRELATED_KEYS,
        PLACEMENT_ALLOWED, PROMOTION_ALLOWED, PLACEMENT_STATE_OK,
        UNPLACED_OK, VERSION_ADVANCED, RESUME_MODE, PATCH_BUDGET,
        RESUME_PROVENANCE_OK, RESUMED_WITHOUT_MUTATION,
        TARGET, CONTROL, PERSON, ERA } = P;

const PANEL_SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "ui", "js", "bug-panel-story-review.js"), "utf8");

const HEAD = "I went to Kent State for my education degree.";
const FULL = HEAD + " That was 1966. Kent State was about an hour from home and "
  + "it was the first time I had ever been away from Akron for more than a weekend.";
const OTHER = "I was born in Akron, Ohio, on the seventeenth of April in 1948.";

/* The candidate as capture leaves it: UNPLACED. This is the shape the
 * live read returned for 447eee18 on 2026-09-01 -- era_candidates [],
 * placement_source "unknown", no year range -- not an invented one. */
const unplacedItem = (id, transcript) => ({
  id, narrator_id: PERSON,
  transcript, transcript_preview: transcript.slice(0, 200),
  era_candidates: [], placement_source: "unknown",
  estimated_year_low: null, estimated_year_high: null, age_bucket: null,
  review_status: "unreviewed", review_version: 1,
  trigger_reason: "chain_detection", scene_anchor_count: 2, confidence: 0.8,
  conversation_id: "conv-1", session_id: "sess-1",
  source_user_turn_row_id: 11, completed_assistant_turn_row_id: 12,
  created_at: "2026-08-31T04:05:06Z", updated_at: "2026-08-31T04:05:06Z",
  scene_anchors: [], extracted_fields: {}, review_notes: null,
});

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
  const browser = await chromium.launch();
  const page = await browser.newPage();
  let failures = 0;
  const check = async (name, fn) => {
    try { await fn(); console.log("  PASS  " + name); }
    catch (e) { failures++; console.log("  FAIL  " + name + " — " + e.message); }
  };

  await page.setContent(`<div id="lv10dBpStoryReview"></div>`);

  // ── stub ONLY the network and the narrator ────────────────────────────
  await page.evaluate((args) => {
    window.state = { person_id: args.person };
    window.__patches = [];
    // The server's version counter, so the promote step is tested against
    // a version that genuinely moved rather than one the test asserted.
    window.__rows = {};
    args.items.forEach((it) => { window.__rows[it.id] = JSON.parse(JSON.stringify(it)); });

    window.fetch = function (url, opts) {
      opts = opts || {};
      const u = String(url);
      const json = (body, status) => Promise.resolve({
        ok: (status || 200) < 400, status: status || 200,
        json: () => Promise.resolve(body),
      });
      if (opts.method === "PATCH") {
        const id = decodeURIComponent(u.split("?")[0].split("/").pop());
        const sent = JSON.parse(opts.body || "null");
        window.__patches.push({ id, sent: sent, at: Date.now() });
        const row = window.__rows[id];
        if (!row) return json({ detail: "no such candidate" }, 404);
        // REAL optimistic-concurrency behaviour: a stale version is a 409.
        if (sent.review_version !== row.review_version) {
          return json({ detail: "version conflict", item: row }, 409);
        }
        if (sent.era_candidates !== undefined) row.era_candidates = sent.era_candidates;
        if (sent.placement_source !== undefined) row.placement_source = sent.placement_source;
        if (sent.review_status !== undefined) row.review_status = sent.review_status;
        row.review_version += 1;
        return json({ item: JSON.parse(JSON.stringify(row)) });
      }
      if (u.indexOf("/story-candidates/review") >= 0) {
        return json({ items: Object.values(window.__rows).map(
                        (r) => JSON.parse(JSON.stringify(r))),
                      count: Object.keys(window.__rows).length,
                      counts: {}, projection: null, fetched_at: "now" });
      }
      if (u.indexOf("/story-candidates/") >= 0) {
        const id = decodeURIComponent(u.split("?")[0].split("/").pop());
        const row = window.__rows[id];
        return row ? json({ item: JSON.parse(JSON.stringify(row)), fetched_at: "now" })
                   : json({ detail: "not found" }, 404);
      }
      return json({}, 404);
    };
  }, { person: PERSON,
       items: [unplacedItem(TARGET, FULL), unplacedItem(CONTROL, OTHER)] });

  await page.addScriptTag({ content: PANEL_SRC });
  await page.evaluate(() => window.lvStoryReviewRefresh());
  await page.waitForTimeout(300);

  const row = () => page.locator(".story-row", { hasText: HEAD });
  const eraSelect = () => row().locator("label.story-field", { hasText: "Life era" })
                               .locator("select");
  const saveBtn = () => row().locator("button.story-act")
                             .filter({ hasText: /^Save placement \/ notes$/ });

  // ── the fixture itself ───────────────────────────────────────────────
  await check("real panel renders both rows from the review endpoint", async () => {
    assert.strictEqual(await page.locator(".story-row").count(), 2);
  });

  await check("the target row is uniquely addressable by its passage", async () => {
    assert.strictEqual(await row().count(), 1);
  });

  await check("capture's own shape reads as UNPLACED", async () => {
    assert.ok(UNPLACED_OK(unplacedItem(TARGET, FULL)));
    assert.ok(!PLACEMENT_STATE_OK(unplacedItem(TARGET, FULL), ERA));
  });

  // ── opening the row ──────────────────────────────────────────────────
  await check("the real preview control opens the detail and the editor", async () => {
    await row().locator(".story-preview-btn").click();
    await page.waitForTimeout(300);
    assert.strictEqual(await eraSelect().count(), 1, "one era select in the open row");
    assert.strictEqual(await saveBtn().count(), 1, "one save control in the open row");
  });

  await check("the era control offers building_years and starts unplaced", async () => {
    const opts = await eraSelect().locator("option").evaluateAll((e) => e.map((o) => o.value));
    assert.ok(opts.indexOf(ERA) >= 0, "building_years must be selectable: " + opts.join(","));
    assert.strictEqual(await eraSelect().inputValue(), "", "starts at '— not placed —'");
  });

  await check("operator_set is NOT hand-selectable from the source control", async () => {
    const src = row().locator("label.story-field", { hasText: "Placement source" })
                     .locator("select");
    const opts = await src.locator("option").evaluateAll((e) => e.map((o) => o.value));
    assert.ok(opts.indexOf("operator_set") < 0,
      "choosing an era is what sets operator_set; offering it separately allowed"
      + " the contradictory pair. Observed: " + opts.join(","));
  });

  // ── contract 1 + 2: placement ────────────────────────────────────────
  await check("selectOption fires the event the handler listens for", async () => {
    await eraSelect().selectOption(ERA);
    await page.waitForTimeout(300);
    // Proven behaviourally: the handler calls render(), and the re-rendered
    // control comes back carrying the choice. If `input` had not fired,
    // the value would have reverted.
    assert.strictEqual(await eraSelect().inputValue(), ERA);
  });

  await check("Save placement / notes sends exactly the placement body", async () => {
    await saveBtn().click();
    await page.waitForTimeout(300);
    const patches = await page.evaluate(() => window.__patches);
    assert.strictEqual(patches.length, 1, "exactly one PATCH");
    assert.strictEqual(patches[0].id, TARGET, "addressed to the target");
    const sent = patches[0].sent;
    assert.ok(PLACEMENT_PATCH_OK({ sent, era: ERA, person: PERSON, version: 1 }),
      "body did not satisfy the placement contract: " + JSON.stringify(sent));
    assert.deepStrictEqual(UNRELATED_KEYS(sent, PLACEMENT_ALLOWED), [],
      "unrelated edit travelled with the placement: " + JSON.stringify(sent));
    assert.ok(!("review_status" in sent), "placement must not restatus the candidate");
  });

  await check("the server-side row is now placed, and its status is untouched", async () => {
    const r = await page.evaluate((id) => window.__rows[id], TARGET);
    assert.ok(PLACEMENT_STATE_OK(r, ERA), "expected sole era + operator_set: "
      + JSON.stringify({ era: r.era_candidates, src: r.placement_source }));
    assert.strictEqual(r.review_status, "unreviewed", "placement changed the status");
    assert.ok(VERSION_ADVANCED(1, r.review_version), "version did not advance");
  });

  // ── contract 3: the version chain ────────────────────────────────────
  await check("promoting WITHOUT refetching sends the stale version and 409s", async () => {
    // The panel still holds the version it rendered before the save.
    await row().locator(".story-act-promote").click();
    await page.waitForTimeout(300);
    const patches = await page.evaluate(() => window.__patches);
    const last = patches[patches.length - 1];
    assert.strictEqual(last.sent.review_version, 1,
      "the panel is expected to send the version it OBSERVED");
    const r = await page.evaluate((id) => window.__rows[id], TARGET);
    assert.strictEqual(r.review_status, "unreviewed",
      "a stale-version promote must NOT take effect");
    assert.ok(!PROMOTION_PATCH_OK({ sent: last.sent, person: PERSON, version: 2 }),
      "the predicate must reject a promotion at the pre-placement version");
  });

  await check("after a refetch, Promote carries the post-placement version", async () => {
    await page.evaluate(() => { window.__patches = []; });
    await page.evaluate(() => window.lvStoryReviewRefresh());
    await page.waitForTimeout(300);
    await row().locator(".story-preview-btn").click();   // reopen the detail
    await page.waitForTimeout(300);
    await row().locator(".story-act-promote").click();
    await page.waitForTimeout(300);
    const patches = await page.evaluate(() => window.__patches);
    assert.strictEqual(patches.length, 1, "exactly one PATCH");
    const sent = patches[0].sent;
    assert.ok(PROMOTION_PATCH_OK({ sent, person: PERSON, version: 2 }),
      "promotion body wrong: " + JSON.stringify(sent));
    assert.deepStrictEqual(UNRELATED_KEYS(sent, PROMOTION_ALLOWED), []);
    const r = await page.evaluate((id) => window.__rows[id], TARGET);
    assert.strictEqual(r.review_status, "promoted");
    assert.ok(PLACEMENT_STATE_OK(r, ERA), "promotion disturbed the placement");
  });

  await check("the control candidate was never addressed", async () => {
    const all = await page.evaluate(() => window.__patches);
    const hist = await page.evaluate((id) => window.__rows[id], CONTROL);
    assert.ok(all.every((p) => p.id === TARGET), "a PATCH reached a foreign candidate");
    assert.strictEqual(hist.review_status, "unreviewed");
    assert.deepStrictEqual(hist.era_candidates, []);
    assert.strictEqual(hist.review_version, 1);
  });

  // ── the resume state machine, exercised ──────────────────────────────
  await check("resume modes and their PATCH budgets", async () => {
    assert.strictEqual(RESUME_MODE(null), "full");
    assert.strictEqual(PATCH_BUDGET(RESUME_MODE(null)), 2);
    assert.strictEqual(RESUME_MODE({ placementProven: true, promotionProven: false }), "placed");
    assert.strictEqual(PATCH_BUDGET("placed"), 1);
    assert.strictEqual(RESUME_MODE({ placementProven: true, promotionProven: true }), "promoted");
    assert.strictEqual(PATCH_BUDGET("promoted"), 0,
      "a fully resumed run must be allowed to mutate nothing at all");
  });

  await check("a resumed run refuses changed provenance", async () => {
    const a = { id: TARGET, conversation_id: "conv-1", session_id: "sess-1" };
    assert.ok(RESUME_PROVENANCE_OK(a, { ...a }));
    assert.ok(!RESUME_PROVENANCE_OK(a, { ...a, session_id: "sess-2" }),
      "a different session is a different story");
    assert.ok(!RESUME_PROVENANCE_OK(null, a), "nothing to compare against is not a pass");
  });

  await check("a fully resumed run proves zero mutation, not merely no click", async () => {
    assert.ok(RESUMED_WITHOUT_MUTATION(0, false));
    assert.ok(!RESUMED_WITHOUT_MUTATION(1, false), "a PATCH still left the browser");
    assert.ok(!RESUMED_WITHOUT_MUTATION(0, true));
  });

  await browser.close();
  console.log(failures ? `\n${failures} FAILED` : "\nALL PASS — placement workflow verified"
    + " against the real panel module");
  process.exit(failures ? 1 : 0);
})();
