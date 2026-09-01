#!/usr/bin/env node
/*
 * Behavioural DOM test for the Phase 1 PLACEMENT workflow.
 *
 * WHY THIS EXISTS, AND WHY IT LOADS THE REAL FILE.
 *
 * The row-selection test builds a synthetic panel that imitates the
 * shipped one. That was enough to catch the addEventListener bug, but it
 * cannot catch drift in the panel's own logic, because the fixture IS the
 * assertion -- if bug-panel-story-review.js changed how it builds a PATCH
 * body tomorrow, a hand-written imitation of yesterday's body would still
 * pass.
 *
 * So this file injects ui/js/bug-panel-story-review.js ITSELF, stubs only
 * the network and the narrator, and then does what an operator does: open
 * the row, choose an era, press Save placement / notes, refresh, press
 * Promote. The bodies asserted here are the bodies the shipped panel
 * actually produced.
 *
 * NOTHING IS MANUFACTURED. This test never injects a `.story-row`, never
 * calls render() or any other internal, and never reaches into `_state`.
 * If the panel does not render, the test fails -- it does not build the
 * DOM it wanted to see.
 *
 * The contracts under test, each already got wrong once:
 *   1. Choosing an era must set placement_source=operator_set in the SAME
 *      action, and the save must NOT carry review_status.
 *   2. selectOption must fire the event the handler listens for. The
 *      handler is `oninput`; a test dispatching `change` would pass while
 *      the live probe silently set nothing.
 *   3. Promote sends `item.review_version` -- the version the panel last
 *      RENDERED -- so the panel must refetch after placement. The stale
 *      case is proven HERE, against a mock server, and never in the live
 *      probe, which always refetches first.
 *
 * TWO FIXTURE BUGS THIS FILE HAS ALREADY COST, both recorded because the
 * symptom was misleading rather than obvious:
 *
 *   a. `confidence: 0.8`. The field sounds like a float; the server types
 *      it Optional[str] and the live value is "low". The panel renders it
 *      as a text child, and `appendChild(0.8)` throws -- inside
 *      renderRow, for every row, from a .then() nobody awaits. The panel
 *      simply stayed empty, and the visible failure was "0 rows", which
 *      reads like a selector fault and is not.
 *   b. One fat shape served to BOTH endpoints. The list route returns
 *      _shape_for_operator's 24 keys; the detail route returns a richer
 *      body. Serving detail fields in the list hides a panel that depends
 *      on them.
 *
 * Hence: the shapes below are derived from the real ones, a page
 * exception fails the run at the point it happens, and a zero-row render
 * aborts immediately with diagnostics instead of producing a screenful of
 * cascading locator timeouts.
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

/* THE STORED ROW. Every field and every TYPE is copied from the live read
 * of 447eee18 in run 20260901T212134Z -- not invented, not simplified.
 * `confidence` is the string bucket the server actually sends. */
const storedRow = (id, transcript) => ({
  id, narrator_id: PERSON,
  trigger_reason: "chain_detection",
  scene_anchor_count: 1, word_count: 38,
  confidence: "low",                       // STRING bucket, never a float
  era_candidates: [], age_bucket: null,
  estimated_year_low: null, estimated_year_high: null,
  transcript,
  extraction_status: "pending",
  review_status: "unreviewed", review_version: 1,
  placement_source: "unknown",
  review_notes: null, reviewed_by: null, reviewed_at: null, updated_at: null,
  session_id: "switch_test_sess", conversation_id: "switch_test_conv",
  created_at: "2026-09-01 02:00:42",
  scene_anchors: [], extracted_fields: {},
  audio_present: false, audio_duration_sec: null,
  source_user_turn_row_id: 2094, completed_assistant_turn_row_id: 2095,
  turn_linked: true,
  extraction: { status: "succeeded", method: "llm", item_count: 0, items: [] },
});

/* THE LIST SHAPE: exactly _shape_for_operator's keys, in its order, with
 * its two derived fields. Serving anything richer here would hide a panel
 * that depends on a field the list route does not send. */
const LIST_KEYS = [
  "id", "narrator_id", "trigger_reason", "scene_anchor_count", "word_count",
  "confidence", "era_candidates", "age_bucket", "estimated_year_low",
  "estimated_year_high", "transcript_preview", "transcript_truncated",
  "extraction_status", "review_status", "review_version", "placement_source",
  "review_notes", "reviewed_by", "reviewed_at", "updated_at", "session_id",
  "conversation_id", "created_at",
];

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
  /* A missing control is a FAILED CONTRACT, not something to wait 30s for.
   * Nine cascading 30-second timeouts is how one root cause presented as
   * nine failures. */
  page.setDefaultTimeout(5000);

  /* SURFACE RENDER EXCEPTIONS. render() runs inside a .then(), so a throw
   * in renderRow rejects a promise nobody awaits: the panel stays empty
   * and every later locator times out. An exception now names itself. */
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(String(e && e.message || e)));
  page.on("console", (m) => {
    if (m.type() === "error") pageErrors.push("console.error: " + m.text());
  });

  let failures = 0;
  const check = async (name, fn) => {
    try { await fn(); console.log("  PASS  " + name); }
    catch (e) { failures++; console.log("  FAIL  " + name + " — " + e.message); }
  };

  // Everything needed to explain a zero-row render, gathered once.
  const diagnose = async () => {
    let dom = null;
    try {
      dom = await page.evaluate(() => {
        const m = document.getElementById("lv10dBpStoryReview");
        return {
          mountPresent: Boolean(m),
          mountHTML: m ? m.innerHTML.slice(0, 1200) : null,
          mountText: m ? (m.innerText || "").slice(0, 400) : null,
          errorText: (document.querySelector(".story-error") || {}).textContent || null,
          emptyText: (document.querySelector(".story-empty") || {}).textContent || null,
          rows: document.querySelectorAll(".story-row").length,
          filters: document.querySelectorAll(".story-filter-input").length,
          caret: (document.querySelector(".story-section-caret") || {}).textContent || null,
          narratorGlobal: (window.state || {}).person_id || null,
          filterValue: (document.querySelector(".story-filter-input") || {}).value || null,
          requests: window.__requests || [],
          lastListResponse: window.__lastListResponse || null,
        };
      });
    } catch (e) { dom = { evaluateFailed: e.message }; }
    return { pageErrors, dom };
  };

  const hardFail = async (name, message) => {
    failures++;
    console.log("  FAIL  " + name + " — " + message);
    console.log("\n  ── diagnostics ──────────────────────────────────────");
    console.log(JSON.stringify(await diagnose(), null, 2));
    console.log("\n  Aborting before the cascade: with no rows rendered, every");
    console.log("  later locator would time out and report the same fault again.");
    await browser.close();
    process.exit(1);
  };

  // ── the panel's real lifecycle ────────────────────────────────────────
  // Mount present BEFORE the module executes: tryInitialFetch() runs on
  // load and returns early if the mount is absent.
  await page.setContent(`<div id="lv10dBpStoryReview"></div>`);

  await page.evaluate((args) => {
    window.ORIGIN = args.origin;              // the module reads a bare ORIGIN
    window.state = { person_id: args.person }; // the narrator the panel scopes to
    window.__patches = [];
    window.__requests = [];
    window.__responses = [];
    window.__rows = {};
    args.rows.forEach((r) => { window.__rows[r.id] = JSON.parse(JSON.stringify(r)); });

    const listShape = (row) => {
      const t = row.transcript || "";
      const out = {};
      args.listKeys.forEach((k) => { out[k] = row[k]; });
      out.transcript_preview = t.slice(0, 200);
      out.transcript_truncated = t.length > 200;
      out.era_candidates = row.era_candidates || [];
      out.placement_source = row.placement_source || "unknown";
      out.review_version = parseInt(row.review_version || 1, 10);
      return out;
    };

    window.fetch = function (url, opts) {
      opts = opts || {};
      const u = String(url);
      window.__requests.push({ method: opts.method || "GET", url: u,
                               body: opts.body || null });
      const json = (body, status) => {
        if (u.indexOf("/story-candidates/review") >= 0) window.__lastListResponse = body;
        else if (u.indexOf("/story-candidates/") >= 0 && (opts.method || "GET") === "GET") {
          window.__lastDetailResponse = body;
        }
        window.__responses.push({ method: opts.method || "GET", url: u,
                                  status: status || 200, body });
        return Promise.resolve({
          ok: (status || 200) < 400, status: status || 200,
          json: () => Promise.resolve(body),
        });
      };
      if ((opts.method || "GET") === "PATCH") {
        const id = decodeURIComponent(u.split("?")[0].split("/").pop());
        const sent = JSON.parse(opts.body || "null");
        window.__patches.push({ id, sent, at: Date.now() });
        const row = window.__rows[id];
        if (!row) return json({ detail: "no such candidate" }, 404);
        // REAL optimistic concurrency: a stale version is a 409 and the
        // row is left exactly as it was.
        if (sent.review_version !== row.review_version) {
          return json({ detail: "version conflict", item: listShape(row) }, 409);
        }
        if (sent.era_candidates !== undefined) row.era_candidates = sent.era_candidates;
        if (sent.placement_source !== undefined) row.placement_source = sent.placement_source;
        if (sent.review_status !== undefined) row.review_status = sent.review_status;
        row.review_version += 1;
        return json({ item: listShape(row) });
      }
      if (u.indexOf("/story-candidates/review") >= 0) {
        // Narrator-scoped by contract: honour the scope the panel asked for.
        const m = /narrator_id=([^&]+)/.exec(u);
        const want = m ? decodeURIComponent(m[1]) : null;
        const items = Object.values(window.__rows)
          .filter((r) => !want || r.narrator_id === want)
          .map(listShape);
        return json({ items, count: items.length, counts: {},
                      projection: null, fetched_at: "2026-09-01 02:00:42" });
      }
      if (u.indexOf("/story-candidates/") >= 0) {
        const id = decodeURIComponent(u.split("?")[0].split("/").pop());
        const row = window.__rows[id];
        // The DETAIL route returns the richer body, transcript included.
        return row ? json({ item: JSON.parse(JSON.stringify(row)),
                            fetched_at: "2026-09-01 02:00:42" })
                   : json({ detail: "not found" }, 404);
      }
      return json({}, 404);
    };
  }, { person: PERSON, origin: "http://localhost:8000", listKeys: LIST_KEYS,
       rows: [storedRow(TARGET, FULL), storedRow(CONTROL, OTHER)] });

  await page.addScriptTag({ content: PANEL_SRC });
  // The module's own entry point, not an internal.
  await page.evaluate(() => window.lvStoryReviewRefresh());
  await page.waitForTimeout(400);

  /* Collapsed by default (bug-panel-story-review.js:116) -- render()
   * returns at :864 BEFORE renderControls(), so a collapsed section
   * exposes no filter input, no row and no promote control. The live
   * probe went straight for `.story-filter-input` and would have refused
   * with "0 filter inputs", reporting a missing operator control that was
   * only folded shut. Expanded through the header: the operator's own
   * gesture, never `_state`. */
  const header = page.locator("#lv10dBpStoryReview .story-section-header");
  if (await page.locator(".story-filter-input").count() === 0) {
    if (await header.count() !== 1) {
      await hardFail("the section header is addressable",
        `${await header.count()} .story-section-header in the mount`);
    }
    await header.click();
    await page.waitForTimeout(300);
  }

  // ── FAIL FAST: nothing below means anything if the panel is empty ─────
  if (pageErrors.length) {
    await hardFail("the panel rendered without throwing",
      "the shipped module threw while rendering the fixture: " + pageErrors[0]
      + " — fix the FIXTURE's field types against _shape_for_operator");
  }
  const rowCount = await page.locator(".story-row").count();
  if (rowCount !== 2) {
    await hardFail("real panel renders both rows from the review endpoint",
      `${rowCount} !== 2`);
  }
  console.log("  PASS  the panel rendered without throwing");
  console.log("  PASS  real panel renders both rows from the review endpoint");

  const row = () => page.locator(".story-row", { hasText: HEAD });
  const eraSelect = () => row().locator("label.story-field", { hasText: "Life era" })
                               .locator("select");
  const saveBtn = () => row().locator("button.story-act")
                             .filter({ hasText: /^Save placement \/ notes$/ });

  await check("the list response carried exactly the server's list shape", async () => {
    const body = await page.evaluate(() => window.__lastListResponse);
    assert.ok(body && Array.isArray(body.items) && body.items.length === 2);
    assert.deepStrictEqual(Object.keys(body.items[0]).sort(), LIST_KEYS.slice().sort(),
      "the mocked list must match _shape_for_operator exactly");
    assert.strictEqual(typeof body.items[0].confidence, "string",
      "confidence is a string bucket on the real API");
  });

  await check("the target row is uniquely addressable by its passage", async () => {
    assert.strictEqual(await row().count(), 1);
  });

  await check("capture's own shape reads as UNPLACED", async () => {
    assert.ok(UNPLACED_OK(storedRow(TARGET, FULL)));
    assert.ok(!PLACEMENT_STATE_OK(storedRow(TARGET, FULL), ERA));
  });

  await check("collapsing hides every control, and the header reopens it", async () => {
    await header.click();
    await page.waitForTimeout(250);
    assert.strictEqual(await page.locator(".story-filter-input").count(), 0);
    assert.strictEqual(await page.locator(".story-row").count(), 0);
    assert.strictEqual(await page.locator(".story-act-promote").count(), 0);
    await header.click();
    await page.waitForTimeout(250);
    assert.strictEqual(await page.locator(".story-row").count(), 2);
  });

  // ── opening the row ──────────────────────────────────────────────────
  await check("the real preview control opens the detail and the editor", async () => {
    await row().locator(".story-preview-btn").click();
    await page.waitForTimeout(400);
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

  // ── contracts 1 + 2: placement ───────────────────────────────────────
  await check("selectOption fires the event the handler listens for", async () => {
    await eraSelect().selectOption(ERA);
    await page.waitForTimeout(300);
    // Behavioural: the handler calls render(), and the re-rendered control
    // comes back carrying the choice. Had `input` not fired, it would have
    // reverted to '— not placed —'.
    assert.strictEqual(await eraSelect().inputValue(), ERA);
  });

  await check("Save placement / notes sends exactly the placement body", async () => {
    await saveBtn().click();
    await page.waitForTimeout(400);
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

  await check("the mock server advanced the version and left the status alone", async () => {
    const r = await page.evaluate((id) => window.__rows[id], TARGET);
    assert.ok(PLACEMENT_STATE_OK(r, ERA), "expected sole era + operator_set: "
      + JSON.stringify({ era: r.era_candidates, src: r.placement_source }));
    assert.strictEqual(r.review_status, "unreviewed", "placement changed the status");
    assert.ok(VERSION_ADVANCED(1, r.review_version), "version did not advance");
  });

  // ── contract 3: the version chain ────────────────────────────────────
  /* CORRECTED after the first green run. This step used to click Promote
   * straight after saving, expecting the panel to send its stale version
   * and take a 409. The control was not there, and the panel is right:
   * applyReview's success path (bug-panel-story-review.js:429-432) does
   *
   *     delete _state.edits[item.id];
   *     _state.conflict = null;
   *     _state.detail   = null;
   *     _state.openId   = null;
   *     return afterReviewApplied(pid);   // fetchReview()
   *
   * -- it CLOSES the detail and refetches the list. So the row's actions
   * vanish until it is reopened, and reopening necessarily yields the new
   * version. The stale-version promote is UNREACHABLE through this UI;
   * the panel forecloses it rather than merely discouraging it.
   *
   * The live probe's refetch-and-reopen is therefore not a workaround, it
   * is the panel's own flow followed honestly. */
  await check("a successful save closes the detail — no action survives it", async () => {
    assert.strictEqual(await row().locator(".story-act-promote").count(), 0,
      "the promote control must be gone until the row is reopened");
    assert.strictEqual(await eraSelect().count(), 0,
      "the editor must be gone with it");
    // The contract itself still rejects a stale body, proven purely.
    assert.ok(!PROMOTION_PATCH_OK({
      sent: { narrator_id: PERSON, review_version: 1, review_status: "promoted" },
      person: PERSON, version: 2 }),
      "a promotion at the pre-placement version must be rejected by contract");
  });

  /* THE VERSION CHAIN, END TO END. The live probe refuses unless the
   * refreshed LIST row and the reopened DETAIL body both carry the
   * verified post-placement version before Promote is clicked. Those are
   * the two reads that feed `item.review_version` into the promotion
   * body, so they are asserted here against the real panel rather than
   * assumed. */
  await check("the refreshed list carries the post-placement version", async () => {
    await page.evaluate(() => { window.__patches = []; });
    await page.evaluate(() => window.lvStoryReviewRefresh());
    await page.waitForTimeout(400);
    const body = await page.evaluate(() => window.__lastListResponse);
    const listRow = (body.items || []).find((i) => i.id === TARGET);
    assert.ok(listRow, "the target must be present in the refreshed list");
    assert.strictEqual(listRow.review_version, 2,
      "the list must show the version the placement produced");
    assert.deepStrictEqual(listRow.era_candidates, [ERA]);
    assert.strictEqual(listRow.placement_source, "operator_set");
  });

  await check("the reopened detail carries the post-placement version", async () => {
    await row().locator(".story-preview-btn").click();   // reopen the detail
    await page.waitForTimeout(400);
    const det = await page.evaluate(() => window.__lastDetailResponse);
    assert.ok(det && det.item, "reopening must issue a detail read");
    assert.strictEqual(det.item.id, TARGET);
    assert.strictEqual(det.item.review_version, 2,
      "the detail the panel renders its actions from must be current");
    assert.ok(PLACEMENT_STATE_OK(det.item, ERA),
      "the reopened detail must show the placement");
  });

  await check("after the panel refetches, Promote carries the new version", async () => {
    await row().locator(".story-act-promote").click();
    await page.waitForTimeout(400);
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

  /* THE 409 THAT IS ACTUALLY REACHABLE. Not "the operator forgot to
   * refresh" -- the panel prevents that -- but "someone else reviewed
   * this story while the row was open", which is the case optimistic
   * concurrency exists for and the case the probe's `.story-conflict`
   * check watches for. The version is moved in the MOCK SERVER's store,
   * never in the panel's state. */
  await check("a version moved underneath produces a 409 and the conflict banner",
    async () => {
      await page.evaluate(() => { window.__patches = []; });
      await row().locator(".story-preview-btn").click();     // reopen
      await page.waitForTimeout(400);
      const opened = await page.evaluate((id) => window.__rows[id].review_version, TARGET);
      // Another operator gets there first.
      await page.evaluate((id) => { window.__rows[id].review_version = 9; }, TARGET);
      await row().locator(".story-act-promote").click();
      await page.waitForTimeout(400);

      const patches = await page.evaluate(() => window.__patches);
      assert.strictEqual(patches.length, 1, "exactly one PATCH attempted");
      assert.strictEqual(patches[0].sent.review_version, opened,
        "the panel sends the version it rendered, which is now stale");
      assert.strictEqual(await page.locator(".story-conflict").count(), 1,
        "the operator must be told, not silently ignored");
      const r = await page.evaluate((id) => window.__rows[id], TARGET);
      assert.strictEqual(r.review_version, 9, "a refused PATCH must not bump the version");
      assert.ok(PLACEMENT_STATE_OK(r, ERA), "a refused PATCH must not touch the placement");
      // The staged edit is kept on purpose so the operator can re-apply.
      const stillOpen = await page.locator(".story-conflict").textContent();
      assert.ok(stillOpen && stillOpen.length > 0);
    });

  await check("the control candidate was never addressed", async () => {
    const all = await page.evaluate(() => window.__requests);
    const hist = await page.evaluate((id) => window.__rows[id], CONTROL);
    const patched = all.filter((r) => r.method === "PATCH");
    assert.ok(patched.every((r) => r.url.indexOf(TARGET) >= 0),
      "a PATCH reached a foreign candidate");
    assert.strictEqual(hist.review_status, "unreviewed");
    assert.deepStrictEqual(hist.era_candidates, []);
    assert.strictEqual(hist.placement_source, "unknown");
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

  await check("no page exception was raised at any point in the workflow", async () => {
    assert.deepStrictEqual(pageErrors, []);
  });

  await browser.close();
  if (pageErrors.length) {
    console.log("\n  page exceptions:");
    pageErrors.forEach((e) => console.log("    " + e));
  }
  console.log(failures
    ? `\n${failures} FAILED`
    : "\nALL PASS — placement workflow verified against the real panel module");
  process.exit(failures ? 1 : 0);
})();
