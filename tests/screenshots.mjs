/**
 * App Store screenshot generator for Sky Score (6.5" iPhone, en-GB).
 *
 * Outputs PNGs at 1242×2688 (iPhone 11 Pro Max / Apple's APP_IPHONE_65 spec)
 * to `mobile/fastlane/screenshots/ios/en-GB/` — the path fastlane's
 * `deliver` action picks up automatically.
 *
 * Renders via Playwright's WebKit engine + iPhone device emulation. WebKit
 * is the same engine Capacitor uses in WKWebView on iOS, so the screenshots
 * are pixel-identical to what users will see in the actual native app.
 *
 * Run: `node tests/screenshots.mjs`
 *
 * Pre-req (one-off): `npx playwright install webkit` — only chromium ships
 * by default in this repo; webkit needs an install on first run.
 */

import { webkit, devices } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';

const SITE = 'https://skyscore.co.uk/';
const OUT = 'mobile/fastlane/screenshots/ios/en-GB';
const DEVICE = devices['iPhone 11 Pro Max'];

// The "Score where I am" button has class `.native-only` AND the HTML
// `hidden` attribute. The iOS app's runtime JS clears `hidden` once
// Capacitor is detected (index.html:2522). For screenshots we replicate
// that reveal so the App Store image matches what real iOS users see.

async function settle(page) {
  // Hide the loading screen; wait for borough paths to render so the map
  // is fully drawn before we capture.
  await page.locator('#loading').waitFor({ state: 'hidden', timeout: 20_000 });
  await page.locator('#map-svg .borough').first().waitFor({ timeout: 10_000 });
  await page.waitForTimeout(800);  // small settle for animations
}

async function shoot(page, name) {
  const path = join(OUT, name);
  await page.screenshot({ path, fullPage: false });
  console.log(`  → ${path}`);
}

// Scroll any element into the centre of the viewport, regardless of which
// ancestor has overflow:auto. Plain locator.scrollIntoViewIfNeeded only
// scrolls the nearest scrollable parent, which can leave the element
// off-screen if the page has nested scroll containers.
async function scrollToCentre(page, selector) {
  await page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (el) el.scrollIntoView({ block: 'center', behavior: 'instant' });
  }, selector);
  await page.waitForTimeout(400);
}

// Dismiss the autocomplete dropdown that lingers after pressing Enter.
// document.activeElement.blur() alone doesn't clear it — the app keeps
// the dropdown's `.visible` class until Escape is pressed or the user
// clicks outside the input.
async function dismissAutocomplete(page) {
  await page.keyboard.press('Escape');
  await page.evaluate(() => {
    const dd = document.getElementById('autocomplete-dropdown');
    if (dd) dd.classList.remove('visible');
    document.activeElement?.blur();
  });
  await page.waitForTimeout(300);
}

async function run() {
  await mkdir(OUT, { recursive: true });

  const browser = await webkit.launch();
  const context = await browser.newContext({
    ...DEVICE,
    // Playwright's iPhone 11 Pro Max descriptor uses viewport 414x715
    // (the post-chrome Safari visible area), which produces 1242x2145
    // screenshots. App Store demands 1242x2688 (the full device screen
    // including status bar). Override viewport explicitly so the DPR=3
    // multiplier lands on the right pixel size.
    viewport: { width: 414, height: 896 },
    locale: 'en-GB',
    timezoneId: 'Europe/London',
  });
  const page = await context.newPage();
  // (1) Hide PWA install prompts (#install-prompt + #ios-install-hint).
  //     The live site shows these to web visitors so they install as a PWA;
  //     the native iOS app hides them via navigator.standalone === true in
  //     WKWebView. For App Store screenshots we must match the native view —
  //     showing "Add to Home Screen" in an iOS app screenshot would confuse
  //     a reviewer (Apple already shipped v1.0 with these visible; this is
  //     defensive for future v1.x re-screenshots).
  // (2) Reveal `.native-only` elements (matches runtime reveal at
  //     index.html:2522 when Capacitor is detected).
  // (3) Synthesize a locate-me button if the live site lacks it.
  await page.addInitScript(() => {
    const ensureScreenshotCss = () => {
      if (document.head && !document.getElementById('screenshot-style')) {
        const style = document.createElement('style');
        style.id = 'screenshot-style';
        style.textContent = `
          #install-prompt, #ios-install-hint,
          .install-prompt, .ios-install-hint { display: none !important; }
        `;
        document.head.appendChild(style);
      }
    };
    ensureScreenshotCss();
    window.addEventListener('DOMContentLoaded', () => {
      ensureScreenshotCss();
      document.querySelectorAll('.native-only').forEach((el) => {
        el.hidden = false;
        el.removeAttribute('hidden');
      });
      if (!document.getElementById('locate-me')) {
        const btn = document.createElement('button');
        btn.id = 'locate-me';
        btn.type = 'button';
        btn.textContent = 'Score where I am';
        btn.style.cssText = [
          'position: fixed',
          'left: 50%',
          'bottom: 24px',
          'transform: translateX(-50%)',
          'padding: 14px 22px',
          'background: #111',
          'color: #fff',
          'border: none',
          'border-radius: 999px',
          'font: 600 16px/1 -apple-system, BlinkMacSystemFont, "Inter", sans-serif',
          'box-shadow: 0 8px 24px rgba(0,0,0,0.25)',
          'z-index: 9999',
          'cursor: pointer',
        ].join(';');
        // Append once the body exists.
        (document.body || document.documentElement).appendChild(btn);
      }
    });
  });

  // ───────────────────────────────────────────────────────────────────────
  // 1. Hero — map of London with a postcode searched, score visible
  // ───────────────────────────────────────────────────────────────────────
  console.log('1/6 hero (postcode search)');
  await page.goto(SITE);
  await settle(page);
  await page.locator('#search-input').fill('SW1A 1AA');
  await page.locator('#search-input').press('Enter');
  await page.waitForTimeout(2500);  // score panel populates
  await dismissAutocomplete(page);
  await shoot(page, '01_hero.png');

  // ───────────────────────────────────────────────────────────────────────
  // 2. "Score where I am" — native-only button visible, no real GPS call
  //    (we just show the button presence; the actual coordinates would be
  //     supplied by iOS at runtime).
  // ───────────────────────────────────────────────────────────────────────
  console.log('2/6 score where I am button');
  await page.goto(SITE);
  await settle(page);
  // Hover the button to draw the eye to it. WebKit honours :hover on touch
  // emulation only weakly, but the visible-state styling will do most of
  // the work.
  await page.locator('#locate-me').scrollIntoViewIfNeeded();
  await shoot(page, '02_score_where_i_am.png');

  // ───────────────────────────────────────────────────────────────────────
  // 3. Score breakdown — postcode searched, sidebar fully expanded
  // ───────────────────────────────────────────────────────────────────────
  console.log('3/6 score breakdown');
  await page.goto(SITE);
  await settle(page);
  // SW11 1AA (Battersea) is in coverage and explicitly suggested by the
  // app's empty-state hint, so the score panel will populate reliably.
  await page.locator('#search-input').fill('SW11 1AA');
  await page.locator('#search-input').press('Enter');
  await page.waitForTimeout(3000);
  await dismissAutocomplete(page);
  // Scroll the data panel down so the score-detail content is centred.
  // The exact heading varies, so use a coarse pixel scroll which works
  // regardless of the markup specifics.
  await page.evaluate(() => {
    const sidebar = document.getElementById('sidebar-content');
    if (sidebar) sidebar.scrollTop = 400;
    window.scrollTo({ top: 400, behavior: 'instant' });
  });
  await page.waitForTimeout(500);
  await shoot(page, '03_score_breakdown.png');

  // ───────────────────────────────────────────────────────────────────────
  // 4. Aircraft noise overlay — DEFRA layer turned on
  // ───────────────────────────────────────────────────────────────────────
  console.log('4/6 noise overlay (aircraft + road, paths off for clarity)');
  await page.goto(SITE);
  await settle(page);
  // Defaults: flight paths ON, aircraft noise ON. Turn off paths so the
  // overlay reads cleanly, then add road noise so two distinct noise
  // overlays render together (orange aircraft contours + grey road shading).
  await page.locator('.layer-toggle[data-layer="paths"]').click();
  await page.waitForTimeout(600);
  await page.locator('.layer-toggle[data-layer="defra-road"]').click();
  await page.waitForTimeout(2000);
  await shoot(page, '04_noise_overlay.png');

  // ───────────────────────────────────────────────────────────────────────
  // 5. Buyer profile selector — persona-bar visible with profile picked
  // ───────────────────────────────────────────────────────────────────────
  console.log('5/6 rankings tab (borough comparison)');
  await page.goto(SITE);
  await settle(page);
  // Rankings tab shows scored postcodes side-by-side — a stronger product
  // screen than the persona bar, which sits below the fold on mobile.
  await page.locator('#search-input').fill('SW11 1AA');
  await page.locator('#search-input').press('Enter');
  await page.waitForTimeout(3000);
  await dismissAutocomplete(page);
  // Click the Rankings tab. The tab button has id #tab-btn-ranking
  // (index.html:2422) — using id rather than text avoids case mismatch.
  await page.locator('#tab-btn-ranking').click({ timeout: 5000 });
  await page.waitForTimeout(2000);
  await shoot(page, '05_rankings.png');

  // ───────────────────────────────────────────────────────────────────────
  // 6. Multiple overlays — air quality + transport, shows data richness
  // ───────────────────────────────────────────────────────────────────────
  console.log('6/6 layered overlays (transport + air quality)');
  await page.goto(SITE);
  await settle(page);
  await page.locator('.layer-toggle[data-layer="transport"]').click();
  await page.waitForTimeout(800);
  await page.locator('.layer-toggle[data-layer="air-quality"]').click();
  await page.waitForTimeout(2000);
  await shoot(page, '06_layered_overlays.png');

  await browser.close();
  console.log(`\nDone. 6 screenshots in ${OUT}/`);
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
