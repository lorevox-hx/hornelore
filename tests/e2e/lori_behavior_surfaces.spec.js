// Lori behavior story-surface probe.
// Run from repo root after installing Playwright and starting UI/API:
//   npx playwright test tests/e2e/lori_behavior_surfaces.spec.js --headed
//
// This is intentionally selector-light because Hornelore UI has changed often.
// Tighten selectors after the current 3-column layout stabilizes.

const { test, expect } = require('@playwright/test');

const UI_URL = process.env.HORNELORE_UI_URL || 'http://localhost:8082/hornelore1.0.html';

test('Sarah Reed facts appear across Timeline, Life Map, and Peek at Memoir', async ({ page }) => {
  await page.goto(UI_URL, { waitUntil: 'domcontentloaded' });

  // Basic UI smoke: canonical life labels must exist somewhere after load.
  await expect(page.getByText(/Earliest Years/i).first()).toBeVisible({ timeout: 15000 });
  await expect(page.getByText(/Today/i).first()).toBeVisible({ timeout: 15000 });

  // If a test narrator picker exists, select/open Sarah Reed. This block is intentionally soft:
  // the harness should not fail just because the picker wording changed.
  const sarah = page.getByText(/Sarah Reed/i).first();
  if (await sarah.count()) {
    await sarah.click();
  }

  // Peek at Memoir should use canonical warm headings and literary subtitles.
  const peek = page.getByRole('button', { name: /peek at memoir/i }).first();
  if (await peek.count()) {
    await peek.click();
    await expect(page.getByText(/Earliest Years/i).first()).toBeVisible({ timeout: 5000 });
    await expect(page.getByText(/The Legend Begins/i).first()).toBeVisible({ timeout: 5000 });
    await expect(page.getByText(/Today/i).first()).toBeVisible({ timeout: 5000 });
  }

  // Life Map canonical labels.
  await expect(page.getByText(/Early School Years/i).first()).toBeVisible({ timeout: 5000 });
  await expect(page.getByText(/Coming of Age/i).first()).toBeVisible({ timeout: 5000 });

  // Timeline text is a soft assertion because timeline may be empty until seed data loads.
  const timelineText = await page.locator('body').innerText();
  const hasCanonicalMismatch = /Early childhood|school years|midlife|later life/i.test(timelineText);
  expect(hasCanonicalMismatch, 'Old era labels should not appear in UI text').toBeFalsy();
});
