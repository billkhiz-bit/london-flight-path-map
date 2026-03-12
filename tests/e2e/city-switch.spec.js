import { test, expect } from '@playwright/test';

test.describe('City switching', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('#loading')).toBeHidden({ timeout: 15_000 });
  });

  test('click NYC button, subtitle changes to contain NEW YORK', async ({ page }) => {
    const nycBtn = page.locator('.city-btn[data-city="nyc"]');
    await nycBtn.click();
    await expect(page.locator('#map-subtitle')).toContainText('NEW YORK');
  });

  test('click London button, subtitle changes to contain LONDON', async ({ page }) => {
    // Switch to NYC first, then back to London
    await page.locator('.city-btn[data-city="nyc"]').click();
    await expect(page.locator('#map-subtitle')).toContainText('NEW YORK');

    await page.locator('.city-btn[data-city="london"]').click();
    await expect(page.locator('#map-subtitle')).toContainText('LONDON');
  });

  test('NYC map should have borough paths rendered', async ({ page }) => {
    await page.locator('.city-btn[data-city="nyc"]').click();
    // Wait for NYC boroughs to render
    const boroughs = page.locator('#map-svg .borough');
    await expect(boroughs.first()).toBeAttached({ timeout: 10_000 });
    const count = await boroughs.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });
});
