import { test, expect } from '@playwright/test';

test.describe('Core loading', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('page loads and loading screen disappears', async ({ page }) => {
    // The loading screen should eventually hide and the app should appear
    await expect(page.locator('#loading')).toBeHidden({ timeout: 15_000 });
    await expect(page.locator('#app')).toBeVisible();
  });

  test('map SVG has at least 20 borough paths', async ({ page }) => {
    await expect(page.locator('#loading')).toBeHidden({ timeout: 15_000 });
    const boroughs = page.locator('#map-svg .borough');
    await expect(boroughs.first()).toBeAttached({ timeout: 10_000 });
    const count = await boroughs.count();
    expect(count).toBeGreaterThanOrEqual(20);
  });

  test('title shows "Sky Score"', async ({ page }) => {
    await expect(page.locator('#loading')).toBeHidden({ timeout: 15_000 });
    await expect(page.locator('#map-title-text')).toHaveText('Sky Score');
  });

  test('the layer toggles are exactly the layers that render', async ({ page }) => {
    // ASSERTS THE SET, NOT A COUNT. This was `toHaveCount(7)` and went red on
    // 2026-08-12 when the transport layer was removed — its markers could not
    // be clicked, because the borough path underneath took the event. A bare
    // count tells you a number changed; it does not say WHICH layer appeared
    // or vanished, and the fix it invites is to edit the number, which is the
    // least informative thing a failing test can ask for.
    //
    // Naming them means a removed layer fails with its own name in the diff,
    // and a new toggle added without a renderer fails too.
    //
    // History: the "live flights" toggle went with the live_flights Lambda in
    // May 2026 (OpenSky licensing); transport went on 2026-08-12.
    await expect(page.locator('#loading')).toBeHidden({ timeout: 15_000 });
    const layers = await page
      .locator('.layer-toggle')
      .evaluateAll((els) => els.map((e) => e.dataset.layer).sort());
    expect(layers).toEqual([
      'air-quality',
      'defra-aircraft',
      'defra-road',
      'flood',
      'labels',
      'paths',
    ]);
  });

  test('search input is visible', async ({ page }) => {
    await expect(page.locator('#loading')).toBeHidden({ timeout: 15_000 });
    await expect(page.locator('#search-input')).toBeVisible();
  });
});
