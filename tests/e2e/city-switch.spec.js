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
//
// THIS SPEC RUNS AGAINST THE LIVE SITE, AND THAT CUTS BOTH WAYS (2026-09-08).
//
// The documented hazard is a live-pointed gate going red on a tree that has
// already fixed the defect, and staying red until deploy - which is why
// `responsive` and `a11y` were split into a blocking source-pointed half and an
// advisory live one. The inverse bit here: when #country-selector's attribute
// changed in SOURCE, this spec went on passing, because it was still reading
// the previously-deployed index.html. A full preflight reported 43 of 43 on a
// tree whose contract these assertions contradicted, and the stage only turned
// red AFTER the deploy made the site match the source.
//
// So a green here says the DEPLOYED site is good; it says nothing about the
// working tree. tests/city-switch.mjs is the source-pointed sibling and does
// gate the tree - but it asserts rendering and outline counts, not ARIA, so it
// could not have caught this either. Before changing an attribute the frontend
// publishes, grep this directory as well as tests/*.mjs.
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
    //
    // aria-pressed since 2026-09-08, not aria-selected. #country-selector
    // stopped being a role="tablist": there was no panel any tab could name,
    // because switchCountry() swaps the whole application rather than a region
    // of it. It is a group of toggle buttons now, exactly like the city chips -
    // and note this file was ALREADY asserting aria-pressed on chip('nyc')
    // below, so the two tiers now agree here as well as in the markup.
    await expect(page.locator(UK)).toHaveAttribute('aria-pressed', 'true');
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
    await expect(page.locator(UK)).toHaveAttribute('aria-pressed', 'true');
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
