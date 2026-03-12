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

  test('all 8 layer toggle buttons exist', async ({ page }) => {
    await expect(page.locator('#loading')).toBeHidden({ timeout: 15_000 });
    const toggles = page.locator('.layer-toggle');
    await expect(toggles).toHaveCount(8);
  });

  test('search input is visible', async ({ page }) => {
    await expect(page.locator('#loading')).toBeHidden({ timeout: 15_000 });
    await expect(page.locator('#search-input')).toBeVisible();
  });
});
