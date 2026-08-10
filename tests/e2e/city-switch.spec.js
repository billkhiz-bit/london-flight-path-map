import { test, expect } from '@playwright/test';

// The switcher is TWO TIERS as of 2026-08-09: country tabs above city chips,
// both generated from CITY_DATA by renderCountrySelector() / renderCitySelector().
//
// This spec used to click `.city-btn[data-city="nyc"]` directly, which encoded
// the one-tier assumption: renderCitySelector(country) only emits chips for the
// ACTIVE country, so that button does not exist while the UK tab is selected.
// Three tests here went red against a correctly working site.
//
// Rewritten to drive the tiers rather than to route around them, which also
// makes it the gate that catches a city landing in the wrong country tab - the
// failure mode that matters while the Core Cities rollout adds regions.
const UK = '.country-btn[data-country="United Kingdom"]';
const USA = '.country-btn[data-country="United States"]';
const chip = (id) => `.city-btn[data-city="${id}"]`;

test.describe('City switching', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('#loading')).toBeHidden({ timeout: 15_000 });
  });

  test('country tabs gate which city chips render', async ({ page }) => {
    // UK is the default country, so its cities are the ones on screen.
    await expect(page.locator(UK)).toHaveAttribute('aria-selected', 'true');
    await expect(page.locator(chip('london'))).toBeVisible();
    await expect(page.locator(chip('manchester'))).toBeVisible();
    // And NYC is genuinely absent, not merely hidden - that is the tier working.
    await expect(page.locator(chip('nyc'))).toHaveCount(0);

    await page.locator(USA).click();
    await expect(page.locator(chip('nyc'))).toBeVisible();
    await expect(page.locator(chip('london'))).toHaveCount(0);
  });

  test('switch to USA, subtitle changes to contain NEW YORK', async ({ page }) => {
    // Selecting the country switches to its city on its own (switchCountry
    // picks lastCityInCountry, or the first city of that country).
    await page.locator(USA).click();
    await expect(page.locator('#map-subtitle')).toContainText('NEW YORK');
    await expect(page.locator(chip('nyc'))).toHaveAttribute('aria-pressed', 'true');
  });

  test('switch back to the UK, subtitle changes to contain LONDON', async ({ page }) => {
    await page.locator(USA).click();
    await expect(page.locator('#map-subtitle')).toContainText('NEW YORK');

    await page.locator(UK).click();
    await page.locator(chip('london')).click();
    await expect(page.locator('#map-subtitle')).toContainText('LONDON');
  });

  test('a third UK city is reachable without leaving the UK tab', async ({ page }) => {
    // Manchester is the case the one-tier spec could not have covered, and the
    // shape every further Core City will take: same tab, different chip.
    await page.locator(chip('manchester')).click();
    await expect(page.locator('#map-subtitle')).toContainText('MANCHESTER');
    await expect(page.locator(UK)).toHaveAttribute('aria-selected', 'true');
  });

  test('NYC map should have borough paths rendered', async ({ page }) => {
    await page.locator(USA).click();
    await page.locator(chip('nyc')).click();
    const boroughs = page.locator('#map-svg .borough');
    await expect(boroughs.first()).toBeAttached({ timeout: 10_000 });
    const count = await boroughs.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });
});
