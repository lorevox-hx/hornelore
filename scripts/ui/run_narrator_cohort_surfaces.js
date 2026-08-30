#!/usr/bin/env node
/*
 * Browser half of run_narrator_cohort_acceptance.py.
 *
 * Safety is structural: this helper accepts one exact synthetic UUID, finds
 * the corresponding semantic Open button, verifies its text and its handler,
 * and clicks that element.  It never clicks coordinates, never resolves a
 * narrator by list position, and never invokes a destructive action.  The
 * product tabs it walks are read from the live DOM rather than hard-coded.
 *
 * Ported from the Codex cohort harness staged at
 * .runtime/incoming/codex-cohort-2026-08-30 on 2026-08-29.  The DOM contract
 * below was verified against the running UI before this file landed:
 *
 *   - six shell tabs match button[role='tab'][data-tab] with ids lvShellTab*
 *   - all eight Open buttons carry exactly lv80ConfirmNarratorSwitch('<uuid>')
 *   - #lv80ActiveNarratorName and #lvTravelDocTab both exist
 *
 * One behavioural change from the staged original, marked NON-VACUITY below:
 * the staged version computed its verdict with Array.prototype.every over the
 * collected tabs.  On an empty array every() is true, so a selector drift that
 * collected nothing would have reported a PASSING ui lane having tested no
 * tab at all.  A run that measures nothing must fail, not pass.
 */
"use strict";

const fs = require("fs");
const path = require("path");

/* The UI must expose at least this many shell tabs for the lane to mean
 * anything.  Verified as six; six is the floor rather than the equality so
 * that adding a product tab does not fail the lane spuriously. */
const MIN_SHELL_TABS = 6;

const OPEN_HANDLER = /^lv80ConfirmNarratorSwitch\(['"][0-9a-f-]+['"]\)$/i;
const DESTRUCTIVE = /delete|erase|remove|destroy|purge/i;

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    if (!key.startsWith("--")) throw new Error(`unexpected argument: ${key}`);
    const value = argv[++i];
    if (!value || value.startsWith("--")) throw new Error(`missing value for ${key}`);
    out[key.slice(2)] = value;
  }
  for (const key of ["ui", "person-id", "expected-name", "output", "screenshots"]) {
    if (!out[key]) throw new Error(`--${key} is required`);
  }
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(out["person-id"])) {
    throw new Error("person-id must be an exact UUID, not a prefix or a name");
  }
  return out;
}

function writeJson(filename, value) {
  fs.mkdirSync(path.dirname(filename), { recursive: true });
  const temp = `${filename}.tmp`;
  fs.writeFileSync(temp, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  fs.renameSync(temp, filename);
}

/* Exactly one enabled button whose text is "Open" and whose handler names this
 * UUID.  Every other outcome throws rather than guessing.
 *
 * ── A LOCATOR, NOT AN elementHandle, 2026-08-30 ─────────────────────────
 *
 * This collected `elementHandles()` and clicked one of them, and the live
 * run failed on BOTH narrators with "Element is not attached to the DOM":
 * the narrator list re-renders between collecting the handles and clicking,
 * so every handle is stale by the time it is used.  `tabs` came back empty
 * and the whole UI lane — tabs, Travel Document, isolation, reload — never
 * ran at all.
 *
 * A locator re-resolves its selector at click time, which is exactly the
 * property a re-rendering list needs.  The safety contract is unchanged and
 * is if anything tighter: the selector itself carries the exact UUID, and
 * the text, handler shape and destructive-verb checks all still run — they
 * now run against the freshly resolved element rather than a stale one.
 */
function openLocator(page, personId) {
  // Exact UUID in the selector. Never a position, never an index.
  return page.locator(`button[onclick*="${personId}"]`).filter({ hasText: /^Open$/ });
}

async function exactOpenButton(page, personId) {
  await page.waitForFunction(
    (pid) => Array.from(document.querySelectorAll("button")).some((button) => {
      const handler = button.getAttribute("onclick") || "";
      return button.textContent.trim() === "Open" && handler.includes(pid);
    }),
    personId,
    { timeout: 30000 },
  );
  const locator = openLocator(page, personId);
  const count = await locator.count();
  if (count !== 1) {
    throw new Error(`expected one semantic Open for ${personId}; found ${count}`);
  }
  const details = await locator.evaluate((button, pid) => ({
    text: button.textContent.trim(),
    onclick: button.getAttribute("onclick") || "",
    disabled: Boolean(button.disabled),
    containsPerson: (button.getAttribute("onclick") || "").includes(pid),
  }), personId);
  if (!details.containsPerson) {
    throw new Error(`the resolved Open does not name ${personId}`);
  }
  if (details.text !== "Open" || details.disabled) {
    throw new Error("the exact narrator action is not an enabled Open button");
  }
  if (DESTRUCTIVE.test(`${details.text} ${details.onclick}`)) {
    throw new Error(`REFUSED: destructive verb on the narrator action: ${details.onclick}`);
  }
  if (!OPEN_HANDLER.test(details.onclick.trim())) {
    throw new Error(`unexpected Open handler: ${details.onclick}`);
  }
  return locator;
}

async function openExactNarrator(page, personId, expectedName) {
  const button = await exactOpenButton(page, personId);
  // Re-resolved at click time, so a list that re-rendered since the checks
  // above is clicked correctly rather than throwing on a detached node.
  await button.click({ timeout: 30000 });
  await page.waitForFunction(
    ({ pid, name }) => {
      const current = window.state && window.state.person_id;
      const label = document.getElementById("lv80ActiveNarratorName");
      return current === pid && label && label.textContent.includes(name);
    },
    { pid: personId, name: expectedName },
    { timeout: 60000 },
  );
  return page.evaluate(() => ({
    personId: window.state && window.state.person_id,
    displayName: document.getElementById("lv80ActiveNarratorName")?.textContent?.trim() || "",
    profileSeed: window.LorevoxProfileSeedAuthority?.snapshot?.() || null,
  }));
}

/* Console errors, failed requests and 4xx/5xx responses, summarized where a
 * reader cannot miss them.
 *
 * ── EXPLICIT, AND DELIBERATELY NOT PART OF THE VERDICT, 2026-08-30 ──────
 *
 * The live run r20260830-011413-fa48c7 recorded three console errors, two
 * aborted requests and three 4xx responses, and still reported `ok: true`
 * with nothing at the top level saying so. They were in the file; they were
 * buried under `tabs`, and the one field a reader looks at did not mention
 * them.
 *
 * They are summarized here rather than folded into `ok` on purpose. Two of
 * the observed 404s — /api/operator/past-tense-flags and the port-8082
 * /api/memoir/canonical — look like standing product conditions rather than
 * anything this narrator did. Failing every run on them would paint the lane
 * permanently red, which is how a real signal gets ignored. `clean` states
 * the fact; a human decides what it means. If these turn out to be defects
 * they get their own bug, and this block is the evidence for it.
 */
function summarizeDiagnostics(evidence) {
  const urls = new Set();
  for (const row of evidence.failedRequests) urls.add(row.url);
  for (const row of evidence.responses4xx5xx) urls.add(`${row.status} ${row.url}`);
  return {
    clean: evidence.consoleErrors.length === 0
      && evidence.failedRequests.length === 0
      && evidence.responses4xx5xx.length === 0,
    consoleErrorCount: evidence.consoleErrors.length,
    failedRequestCount: evidence.failedRequests.length,
    http4xx5xxCount: evidence.responses4xx5xx.length,
    distinctUrls: Array.from(urls).sort(),
    note: "Reported, not gated. A non-clean run is not automatically a failing run.",
  };
}

async function collectShellTabs(page) {
  return page.evaluate(() => Array.from(
    document.querySelectorAll("button[role='tab'][data-tab]"),
  ).filter((button) => button.id.startsWith("lvShellTab")).map((button) => ({
    id: button.id,
    tab: button.dataset.tab,
    text: button.textContent.trim(),
    disabled: Boolean(button.disabled),
  })));
}

/* Classify the Travel Document surface.
 *
 * ── THE TAB MUST BE ACTIVE WHEN THIS READS IT, 2026-08-30 ──────────────
 *
 * This ran after the tab loop, which ends on Media — so the Travel
 * Document panel was HIDDEN, and `innerText` returns "" for a hidden
 * element (it is the rendered text; `textContent` would not care). The
 * live run therefore classified a perfectly healthy surface as "unknown"
 * off an empty string, while the screenshot taken moments earlier showed
 * "No trips yet for this narrator" rendered correctly.
 *
 * `unknown` is not a pass, so this reported failure rather than inventing
 * a verdict — the right behaviour on bad evidence, but the evidence
 * should not have been bad. Re-activate the tab, then read it.
 */
async function classifyTravel(page, tabId) {
  if (tabId) {
    await page.locator(`#${tabId}`).click();
    await page.waitForTimeout(400);
  }
  return page.evaluate(() => {
    const host = document.getElementById("lvTravelDocTab");
    const text = (host?.innerText || "").replace(/\s+/g, " ").trim();
    const unavailable = /unavailable|failed to load/i.test(text);
    const empty = /no trips (yet|found|recorded)|choose a narrator|select a trip/i.test(text);
    const populated = Boolean(host?.querySelector(
      "[data-trip-id], [data-td-trip-id], .tdl-trip-card, .td-trip-card, .trip-card",
    ));
    return {
      classification: unavailable ? "unavailable" : populated ? "populated" : empty ? "empty" : "unknown",
      textExcerpt: text.slice(0, 1200),
    };
  });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  let chromium;
  try {
    ({ chromium } = require("playwright"));
  } catch (error) {
    ({ chromium } = require("@playwright/test"));
  }
  const evidence = {
    schemaVersion: 1,
    ok: false,
    personId: args["person-id"],
    expectedName: args["expected-name"],
    startedAt: new Date().toISOString(),
    consoleErrors: [],
    failedRequests: [],
    responses4xx5xx: [],
    tabs: [],
    isolation: {},
    travel: {},
    persistence: {},
    nonVacuity: {},
  };
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext();
    const page = await context.newPage();
    page.on("console", (message) => {
      if (message.type() === "error") evidence.consoleErrors.push(message.text());
    });
    page.on("requestfailed", (request) => {
      evidence.failedRequests.push({
        url: request.url(), error: request.failure()?.errorText || "unknown",
      });
    });
    page.on("response", (response) => {
      if (response.status() >= 400) {
        evidence.responses4xx5xx.push({ status: response.status(), url: response.url() });
      }
    });
    await page.goto(args.ui, { waitUntil: "domcontentloaded", timeout: 60000 });
    const opened = await openExactNarrator(page, args["person-id"], args["expected-name"]);
    evidence.isolation.opened = opened;
    fs.mkdirSync(args.screenshots, { recursive: true });

    const tabs = await collectShellTabs(page);
    for (const tab of tabs) {
      const record = { ...tab, clicked: false, selected: false, activePersonId: null, error: "" };
      try {
        if (!tab.disabled) {
          await page.locator(`#${tab.id}`).click();
          await page.waitForTimeout(350);
          record.clicked = true;
          const shell = await page.evaluate((tabId) => ({
            activePersonId: window.state && window.state.person_id,
            selected: document.getElementById(tabId)?.getAttribute("aria-selected") === "true",
            activeName: document.getElementById("lv80ActiveNarratorName")?.textContent?.trim() || "",
          }), tab.id);
          record.activePersonId = shell.activePersonId;
          record.selected = shell.selected;
          record.activeName = shell.activeName;
          if (shell.activePersonId !== args["person-id"]) {
            throw new Error(`active narrator drifted to ${shell.activePersonId}`);
          }
          /* ── A CLICKED TAB MUST BECOME THE SELECTED TAB, 2026-08-30 ──
           *
           * `selected` was read and stored and then never asserted, so a
           * tab whose click silently did nothing — a handler that threw, a
           * panel that never mounted — was recorded as `clicked: true,
           * selected: false` and counted toward a passing lane. Walking a
           * tab strip proves nothing if the strip does not move. */
          if (!shell.selected) {
            throw new Error(
              `clicked ${tab.id} but aria-selected never became true`);
          }
          await page.screenshot({
            path: path.join(args.screenshots, `${tab.tab}.png`), fullPage: true,
          });
        }
      } catch (error) {
        record.error = String((error && error.message) || error);
      }
      evidence.tabs.push(record);
    }

    /* ── ONLY A CLASSIFIED SURFACE PASSES, 2026-08-30 ────────────────────
     *
     * This read `classification !== "unknown"`, which passed `unavailable`
     * — the one classification that positively means the surface did not
     * load. Two of the four outcomes describe a Travel Document that
     * rendered ("populated", "empty") and two describe an absent verdict
     * ("unknown") or a broken one ("unavailable"). The lane passes on the
     * first two and nothing else.
     *
     * And the result is now part of `evidence.ok`. It was computed,
     * written to the file and then left out of the verdict entirely, so a
     * Travel Document that failed to load could not fail the run. */
    const TRAVEL_PASSING = new Set(["populated", "empty"]);
    const travelTab = evidence.tabs.find((tab) => tab.tab === "traveldoc" || tab.tab === "trips");
    if (travelTab && travelTab.clicked && !travelTab.error) {
      const travelState = await classifyTravel(page, travelTab.id);
      evidence.travel = {
        ok: TRAVEL_PASSING.has(travelState.classification),
        tab: travelTab,
        ...travelState,
      };
    } else {
      evidence.travel = {
        ok: false,
        classification: "unavailable",
        reason: "no usable Travel Document or trips shell tab in the live DOM",
      };
    }

    /* NON-VACUITY.  every() over an empty array is true, so the collected
     * count is asserted before any verdict derived from it is believed. */
    const clickedCount = evidence.tabs.filter((tab) => tab.clicked).length;
    evidence.nonVacuity = {
      tabsCollected: evidence.tabs.length,
      tabsClicked: clickedCount,
      minimumRequired: MIN_SHELL_TABS,
      ok: evidence.tabs.length >= MIN_SHELL_TABS && clickedCount > 0,
      note: "A lane that walked no tab reports failure, never an empty pass.",
    };

    evidence.isolation.ok = evidence.nonVacuity.ok && evidence.tabs.every(
      (tab) => !tab.clicked || tab.activePersonId === args["person-id"],
    );

    // Reload is the persistence smoke.  Startup may reopen the narrator
    // picker, so select the same UUID semantically again and re-read the
    // authority view rather than assuming the reload restored it.
    await page.reload({ waitUntil: "domcontentloaded", timeout: 60000 });
    const reopened = await openExactNarrator(page, args["person-id"], args["expected-name"]);
    evidence.persistence = { ok: reopened.personId === args["person-id"], reopened };

    /* Every enabled tab was clicked AND became selected. `record.error`
     * already carries the selection failure thrown above; this states the
     * property directly so the report does not require reading errors to
     * learn it. */
    const enabled = evidence.tabs.filter((tab) => !tab.disabled);
    evidence.tabSelection = {
      enabled: enabled.length,
      clicked: enabled.filter((tab) => tab.clicked).length,
      selected: enabled.filter((tab) => tab.selected).length,
      ok: enabled.length > 0
        && enabled.every((tab) => tab.clicked && tab.selected && !tab.error),
    };

    evidence.diagnostics = summarizeDiagnostics(evidence);

    evidence.ok = evidence.nonVacuity.ok
      && evidence.isolation.ok
      && evidence.persistence.ok
      && evidence.tabSelection.ok
      && evidence.travel.ok
      && evidence.tabs.every((tab) => !tab.error);
    evidence.finishedAt = new Date().toISOString();
    writeJson(args.output, evidence);
    await context.close();
  } catch (error) {
    evidence.error = String((error && error.stack) || error);
    // Whatever the browser managed to record before the throw is still the
    // best evidence about why it threw.
    evidence.diagnostics = summarizeDiagnostics(evidence);
    evidence.finishedAt = new Date().toISOString();
    writeJson(args.output, evidence);
  } finally {
    await browser.close();
  }
  process.exitCode = evidence.ok ? 0 : 1;
}

main().catch((error) => {
  process.stderr.write(`${(error && error.stack) || error}\n`);
  process.exitCode = 2;
});
