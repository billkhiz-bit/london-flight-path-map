import { test, expect } from '@playwright/test';

test.describe('Search', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/map/'); // the full map, at /map/ since 2026-10-06
    await expect(page.locator('#loading')).toBeHidden({ timeout: 15_000 });
  });

  test('type "Chelsea" in search, autocomplete dropdown appears', async ({ page }) => {
    const searchInput = page.locator('#search-input');
    const dropdown = page.locator('#autocomplete-dropdown');

    await searchInput.fill('Chelsea');
    // Trigger input event to activate autocomplete
    await searchInput.dispatchEvent('input');

    await expect(dropdown).toHaveClass(/visible/, { timeout: 5_000 });
  });

  test('type postcode and press Enter, sidebar updates', async ({ page }) => {
    const searchInput = page.locator('#search-input');
    const sidebarContent = page.locator('#sidebar-content');

    // Confirm the initial state is the empty panel, by its marker (its words are each city's own since 2026-11-11)
    await expect(sidebarContent.locator('.no-result-yet')).toHaveCount(1);

    await searchInput.fill('SW11 1AA');
    await searchInput.press('Enter');

    // After search, sidebar should no longer show the empty state
    await expect(sidebarContent.locator('.no-result-yet')).toHaveCount(0, { timeout: 10_000 });
  });
});
