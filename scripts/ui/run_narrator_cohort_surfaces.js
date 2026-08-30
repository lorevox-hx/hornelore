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
 * UUID.  Every other outcome throws rather than guessing. */
async function exactOpenButton(page, personId) {
  await page.waitForFunction(
    (pid) => Array.from(document.querySelectorAll("button")).some((button) => {
      const handler = button.getAttribute("onclick") || "";
      return button.textContent.trim() === "Open" && handler.includes(pid);
    }),
    personId,
    { timeout: 30000 },
  );
  const handles = await page.locator("button", { hasText: /^Open$/ }).elementHandles();
  const matches = [];
  for (const handle of handles) {
    const details = await handle.evaluate((button, pid) => ({
      text: button.textContent.trim(),
      onclick: button.getAttribute("onclick") || "",
      disabled: Boolean(button.disabled),
      containsPerson: (button.getAttribute("onclick") || "").includes(pid),
    }), personId);
    if (details.containsPerson) matches.push({ handle, details });
  }
  if (matches.length !== 1) {
    throw new Error(`expected one semantic Open for ${personId}; found ${matches.length}`);
  }
  const { details, handle } = matches[0];
  if (details.text !== "Open" || details.disabled) {
    throw new Error("the exact narrator action is not an enabled Open button");
  }
  if (DESTRUCTIVE.test(`${details.text} ${details.onclick}`)) {
    throw new Error(`REFUSED: destructive verb on the narrator action: ${details.onclick}`);
  }
  if (!OPEN_HANDLER.test(details.onclick.trim())) {
    throw new Error(`unexpected Open handler: ${details.onclick}`);
  }
  return handle;
}

async function openExactNarrator(page, personId, expectedName) {
  const button = await exactOpenButton(page, personId);
  await button.click();
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

function classifyTravel(page) {
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
          await page.screenshot({
            path: path.join(args.screenshots, `${tab.tab}.png`), fullPage: true,
          });
        }
      } catch (error) {
        record.error = String((error && error.message) || error);
      }
      evidence.tabs.push(record);
    }

    const travelTab = evidence.tabs.find((tab) => tab.tab === "traveldoc" || tab.tab === "trips");
    if (travelTab && travelTab.clicked && !travelTab.error) {
      const travelState = await classifyTravel(page);
      evidence.travel = {
        ok: travelState.classification !== "unknown", tab: travelTab, ...travelState,
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

    evidence.ok = evidence.nonVacuity.ok
      && evidence.isolation.ok
      && evidence.persistence.ok
      && evidence.tabs.every((tab) => !tab.error);
    evidence.finishedAt = new Date().toISOString();
    writeJson(args.output, evidence);
    await context.close();
  } catch (error) {
    evidence.error = String((error && error.stack) || error);
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
