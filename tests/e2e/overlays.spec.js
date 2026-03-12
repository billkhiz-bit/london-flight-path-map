import { test, expect } from '@playwright/test';

test.describe('Overlay toggles', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('#loading')).toBeHidden({ timeout: 15_000 });
  });

  test('click road noise toggle, verify it gets active class', async ({ page }) => {
    const roadToggle = page.locator('.layer-toggle[data-layer="defra-road"]');
    // Road noise starts inactive
    await expect(roadToggle).not.toHaveClass(/active/);
    await roadToggle.click();
    await expect(roadToggle).toHaveClass(/active/);
  });

  test('road noise toggle shows legend-road-group', async ({ page }) => {
    const roadToggle = page.locator('.layer-toggle[data-layer="defra-road"]');
    const legend = page.locator('#legend-road-group');

    // Legend should start hidden
    await expect(legend).toBeHidden();
    await roadToggle.click();
    await expect(legend).toBeVisible();
  });

  test('flood toggle shows legend-flood-group', async ({ page }) => {
    const floodToggle = page.locator('.layer-toggle[data-layer="flood"]');
    const legend = page.locator('#legend-flood-group');

    await expect(legend).toBeHidden();
    await floodToggle.click();
    await expect(legend).toBeVisible();
  });

  test('air quality toggle shows legend-aq-group', async ({ page }) => {
    const aqToggle = page.locator('.layer-toggle[data-layer="air-quality"]');
    const legend = page.locator('#legend-aq-group');

    await expect(legend).toBeHidden();
    await aqToggle.click();
    await expect(legend).toBeVisible();
  });

  test('toggle off hides legend again', async ({ page }) => {
    const roadToggle = page.locator('.layer-toggle[data-layer="defra-road"]');
    const legend = page.locator('#legend-road-group');

    // Toggle on
    await roadToggle.click();
    await expect(legend).toBeVisible();

    // Toggle off
    await roadToggle.click();
    await expect(legend).toBeHidden();
    await expect(roadToggle).not.toHaveClass(/active/);
  });
});
