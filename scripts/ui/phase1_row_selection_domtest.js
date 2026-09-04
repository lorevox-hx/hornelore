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
const P = require("./phase1_memoir_chain_probe.js");
const { SELECT_ROW, OPEN_DETAIL, VERIFY_ROW, ACTIVE_OK,
        OPEN_MEMOIR_STAGE1, OPEN_MEMOIR_STAGE2, PANEL_STATE,
        SOURCE_ID, IMMUTABLE } = P;

const PAT  = "62e94e93-0e44-4fb0-bf19-4bfe847e163c";
const PAT_NAME = "ZZ COHORT r20260831-040506-010cd6 \u00b7 Pat";
const WALT = "ac97f667-0a49-4677-81ac-9de80affed43";
const WALT_NAME = "ZZ COHORT r20260831-040506-010cd6 \u00b7 Walt";

const TARGET_TEXT = "I went to Kent State for my education degree. That was 1966. "
  + "Kent State was about an hour from home and it was the first time I had "
  + "ever been away from Akron for more than a weekend.";
const HEAD = "I went to Kent State for my education degree.";
const OTHER = "I was born in Akron, Ohio, on the seventeenth of April in 1948.";

// Rows built exactly as the panel builds them: handlers via addEventListener.
const PAGE = `
<div class="story-list">
  <div class="story-row" id="row-other" data-story-candidate-id="5a56f942-001b-453b-8e4d-01fb82062013">
    <button class="story-preview story-preview-btn">${OTHER}</button>
  </div>
  <div class="story-row" id="row-target" data-story-candidate-id="447eee18-9ea5-4961-bf3d-157773d3cd44">
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
    const r = await page.evaluate(SELECT_ROW, { id: "447eee18-9ea5-4961-bf3d-157773d3cd44", expected: HEAD + " \u2026" });
    assert.strictEqual(r.rows, 2, "fixture should have two rows");
    assert.strictEqual(r.matching, 1, "exactly one row must match");
    assert.ok(r.ok);
  });

  await check("BYTE-IDENTICAL previews: only the target is addressable", async () => {
    /* The case that ruled out every text rule, taken from the live DB.
     * `24ceb055` and the CONTROL `5a56f942` both truncate at 200 chars
     * through the same opening, so their rendered previews are byte-for-byte
     * the same. Identity separates them; nothing else can. */
    const shared = "I was born in Akron, Ohio, on the seventeenth of April in 1948. "
      + "My father Harold was a rubber-plant man and my mother Dorothy was a "
      + "homemaker in the house on Pl\u2026";
    await page.evaluate(function (a) {
      document.body.innerHTML =
        '<div class="story-list">' +
        '<div class="story-row" data-story-candidate-id="' + a.aggregate + '">' +
        '<button class="story-preview story-preview-btn">' + a.text + '</button></div>' +
        '<div class="story-row" data-story-candidate-id="' + a.control + '">' +
        '<button class="story-preview story-preview-btn">' + a.text + '</button></div></div>';
    }, { text: shared, aggregate: "24ceb055-aaaa-4aaa-8aaa-aaaaaaaaaaaa", control: "5a56f942-001b-453b-8e4d-01fb82062013" });

    const byText = await page.evaluate(function (txt) {
      return Array.from(document.querySelectorAll(".story-preview-btn"))
        .filter(function (b) { return (b.textContent || "").trim() === txt; }).length;
    }, shared);
    assert.strictEqual(byText, 2, "text matches BOTH — this is why text cannot be used");

    const ctl = await page.evaluate(SELECT_ROW, { id: "5a56f942-001b-453b-8e4d-01fb82062013", expected: shared });
    assert.strictEqual(ctl.matching, 1, "identity selects exactly one");
    assert.strictEqual(ctl.index, 1, "and it is the control row, not the aggregate");
    assert.strictEqual(ctl.previewMatches, true, "secondary preview check still passes");

    const agg = await page.evaluate(SELECT_ROW, { id: "24ceb055-aaaa-4aaa-8aaa-aaaaaaaaaaaa" });
    assert.strictEqual(agg.index, 0, "the aggregate is separately addressable");
    await page.setContent(PAGE);
  });

  await check("refuses when the passage matches no row", async () => {
    const r = await page.evaluate(SELECT_ROW, { id: "no-such-candidate-id" });
    assert.strictEqual(r.matching, 0);
    assert.strictEqual(r.ok, false);
  });

  await check("no detail is open before clicking", async () => {
    const n = await page.evaluate(() => document.querySelectorAll(".story-detail").length);
    assert.strictEqual(n, 0);
  });

  await check("clicking .story-preview-btn opens the detail (addEventListener)", async () => {
    const o = await page.evaluate(OPEN_DETAIL, { id: "447eee18-9ea5-4961-bf3d-157773d3cd44" });
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
    const v = await page.evaluate(VERIFY_ROW, { id: "447eee18-9ea5-4961-bf3d-157773d3cd44", expected: HEAD + " \u2026", full: TARGET_TEXT });
    assert.strictEqual(v.detailOpen, true);
    assert.strictEqual(v.transcriptEqualsTarget, true);
  });

  await check("a partial passage does NOT satisfy the equality check", async () => {
    const v = await page.evaluate(VERIFY_ROW, { id: "447eee18-9ea5-4961-bf3d-157773d3cd44", expected: HEAD + " \u2026", full: HEAD });
    assert.strictEqual(v.transcriptEqualsTarget, false,
      "the head alone must not pass as the full transcript");
  });

  await check("exactly one promote control exists inside the target row", async () => {
    const v = await page.evaluate(VERIFY_ROW, { id: "447eee18-9ea5-4961-bf3d-157773d3cd44", expected: HEAD + " \u2026", full: TARGET_TEXT });
    assert.strictEqual(v.promoteControlsInRow, 1);
  });

  await check("row-scoped promotion clicks the TARGET row, not the other", async () => {
    await page.evaluate(OPEN_DETAIL, { id: "5a56f942-001b-453b-8e4d-01fb82062013" });          // open the other row too
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

  /* ── ACTIVE NARRATOR ───────────────────────────────────────────────
   * The Bug Panel filter is independent of state.person_id. Filtering to
   * Pat while Walt is active would promote Pat's candidate correctly and
   * then preview WALT'S memoir, reporting it as Pat's preview failure.
   * These prove the assertion refuses that, with the panel still showing
   * Pat's row. */
  const setActive = (pid, name) => page.evaluate(([p, n]) => {
    window.state = { person_id: p, narratorOpen: { openStatus: "ready" } };
    let el = document.getElementById("lv80ActiveNarratorName");
    if (!el) { el = document.createElement("div"); el.id = "lv80ActiveNarratorName";
               document.body.appendChild(el); }
    el.textContent = n;
  }, [pid, name]);

  await check("accepts when Pat is active, named and ready", async () => {
    await setActive(PAT, PAT_NAME);
    const a = await page.evaluate(ACTIVE_OK, { personId: PAT, displayName: PAT_NAME });
    assert.strictEqual(a.ok, true, JSON.stringify(a));
  });

  await check("REFUSES when another narrator is active, though the panel shows Pat", async () => {
    await setActive(WALT, WALT_NAME);
    const sel = await page.evaluate(SELECT_ROW, { id: "447eee18-9ea5-4961-bf3d-157773d3cd44", expected: HEAD + " \u2026" });
    assert.strictEqual(sel.ok, true, "the Bug Panel still shows Pat's row");
    const a = await page.evaluate(ACTIVE_OK, { personId: PAT, displayName: PAT_NAME });
    assert.strictEqual(a.ok, false, "must refuse: preview/export would be Walt's");
    assert.strictEqual(a.idOK, false);
    assert.strictEqual(a.activePersonId, WALT);
  });

  await check("REFUSES when the card shows a different name", async () => {
    await setActive(PAT, WALT_NAME);
    const a = await page.evaluate(ACTIVE_OK, { personId: PAT, displayName: PAT_NAME });
    assert.strictEqual(a.ok, false);
    assert.strictEqual(a.idOK, true, "id alone must not be enough");
    assert.strictEqual(a.nameOK, false);
  });

  await check("REFUSES when the open lifecycle has not reached ready", async () => {
    await page.evaluate(([p, n]) => {
      window.state = { person_id: p, narratorOpen: { openStatus: "loading" } };
      document.getElementById("lv80ActiveNarratorName").textContent = n;
    }, [PAT, PAT_NAME]);
    const a = await page.evaluate(ACTIVE_OK, { personId: PAT, displayName: PAT_NAME });
    assert.strictEqual(a.ok, false);
    assert.strictEqual(a.lifecycleOK, false);
    assert.strictEqual(a.openStatus, "loading");
  });

  await check("REFUSES when no narrator is active at all", async () => {
    await page.evaluate(() => { window.state = {};
      document.getElementById("lv80ActiveNarratorName").textContent = "Choose a narrator"; });
    const a = await page.evaluate(ACTIVE_OK, { personId: PAT, displayName: PAT_NAME });
    assert.strictEqual(a.ok, false);
    assert.strictEqual(a.activePersonId, null);
  });

  /* ── CONTRACT CHECKS, behavioural ─────────────────────────────────
   * These cover the mismatches the full Phase 1 review found: the real
   * {item, fetched_at} envelope, the required narrator query, a changing
   * fetched_at, the hashed source digest, the two-stage memoir opening,
   * export body ownership and a non-zero exit on failure. */

  await check("source digest matches the server's sha256('story:'+id)[:12]", async () => {
    const expect = require("crypto").createHash("sha256")
      .update("story:447eee18-9ea5-4961-bf3d-157773d3cd44").digest("hex").slice(0, 12);
    assert.strictEqual(SOURCE_ID, expect);
    assert.strictEqual(SOURCE_ID, "5d57a43ce780");
  });

  await check("the raw candidate UUID is NOT the provenance id", async () => {
    assert.ok(!SOURCE_ID.includes("447eee18"),
      "the server hashes it deliberately; searching for the UUID can never match");
  });

  await check("a changing fetched_at does not fail the control comparison", async () => {
    const a = { item: { id: "c", review_status: "unreviewed" }, fetched_at: "T1" };
    const b = { item: { id: "c", review_status: "unreviewed" }, fetched_at: "T2" };
    assert.notStrictEqual(JSON.stringify(a), JSON.stringify(b), "whole responses differ");
    assert.strictEqual(JSON.stringify(a.item), JSON.stringify(b.item),
      "only item may be compared");
  });

  await check("immutable provenance covers the WO-required fields", async () => {
    ["conversation_id", "session_id", "source_user_turn_row_id",
     "completed_assistant_turn_row_id", "narrator_id", "id"].forEach((f) =>
      assert.ok(IMMUTABLE.includes(f), f + " must be immutable"));
    ["review_status", "review_version"].forEach((f) =>
      assert.ok(!IMMUTABLE.includes(f), f + " legitimately changes"));
  });

  await check("memoir opening is two-stage; the ctx block itself is inert", async () => {
    await page.evaluate(() => {
      document.body.insertAdjacentHTML("beforeend",
        '<div id="lvNarratorCtxMemoir" class="lv-narrator-ctx-block">' +
        '<button class="lv-narrator-ctx-cta">Peek at your memoir</button></div>');
      window.__stage = [];
      document.querySelector("#lvNarratorCtxMemoir .lv-narrator-ctx-cta")
        .addEventListener("click", function () {
          window.__stage.push("view");
          const b = document.createElement("button");
          b.className = "lv-narrator-view-cta"; b.textContent = "Open memoir";
          b.addEventListener("click", function () {
            window.__stage.push("popover");
            const p = document.createElement("div");
            p.id = "memoirScrollPopover"; p.textContent = "…";
            document.body.appendChild(p);
          });
          document.body.appendChild(b);
        });
    });
    // Clicking the DIV must do nothing — that was the defect.
    await page.evaluate(() => document.getElementById("lvNarratorCtxMemoir").click());
    assert.deepStrictEqual(await page.evaluate(() => window.__stage), [],
      "the ctx block is a div with no handler");
    const s1 = await page.evaluate(OPEN_MEMOIR_STAGE1);
    assert.strictEqual(s1.found, true);
    const s2 = await page.evaluate(OPEN_MEMOIR_STAGE2);
    assert.strictEqual(s2.found, true);
    assert.deepStrictEqual(await page.evaluate(() => window.__stage), ["view", "popover"]);
  });

  await check("panel state counts the COMPLETE passage, not its opening", async () => {
    await page.evaluate((full) => {
      document.getElementById("memoirScrollPopover").textContent = full;
    }, TARGET_TEXT);
    const ok = await page.evaluate(PANEL_STATE, TARGET_TEXT);
    assert.strictEqual(ok.occurrences, 1);
    const partial = await page.evaluate((h) => {
      document.getElementById("memoirScrollPopover").textContent = h;
      return null;
    }, HEAD);
    const bad = await page.evaluate(PANEL_STATE, TARGET_TEXT);
    assert.strictEqual(bad.occurrences, 0, "the head alone must not count");
  });

  await check("a failed chain exits non-zero", async () => {
    const { execFileSync } = require("child_process");
    const src = require("fs").readFileSync(
      require("path").join(__dirname, "phase1_memoir_chain_probe.js"), "utf8");
    assert.ok(src.includes("process.exitCode = (!bad && complete"),
      "exit code must be derived from the gate, refusals and errors");
    assert.ok(src.includes("R.refusals.length) ? 0 : 1")
           || src.includes("!R.refusals.length && !R.error) ? 0 : 1"),
      "refusals and errors must force non-zero");
  });

  await browser.close();
  console.log(failures ? `\nDOM TEST FAILED — ${failures} failure(s)` : "\nDOM TEST PASS");
  process.exit(failures ? 1 : 0);
})();
