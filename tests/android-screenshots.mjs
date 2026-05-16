/**
 * Google Play screenshot generator for Sky Score (Android phone, en-GB).
 *
 * Outputs PNGs at 1080×1920 (Play Store minimum, 9:16 portrait) to
 * `mobile/fastlane/metadata/android/en-GB/images/phoneScreenshots/` —
 * the path fastlane's `supply` action reads from when running
 * `bundle exec fastlane android publish`.
 *
 * Renders via Playwright's Chromium engine. Chromium matches the
 * WebView Capacitor uses on Android (Android System WebView is
 * Chromium-derived), so the screenshots are pixel-faithful to what
 * users will see in the native app.
 *
 * Same five product surfaces as the iOS generator (tests/screenshots.mjs).
 * Sixth iOS frame (layered overlays) skipped — Play only requires 2
 * minimum and showing the same scene twice (3 overlays vs 2) adds
 * little new information.
 *
 * Run: `node tests/android-screenshots.mjs`
 *
 * Pre-req: Playwright Chromium is bundled with this repo's node_modules
 * (`npx playwright install` if first run on a fresh machine).
 */

import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';

const SITE = 'https://skyscore.co.uk/';
const OUT = 'mobile/fastlane/metadata/android/en-GB/images/phoneScreenshots';

// Play Store minimum: 320 dp width, 9:16 (or up to 19.5:9). 1080×1920 is
// the standard target — equivalent to a Pixel phone at 360×640 with DPR=3,
// which Playwright produces natively if we set viewport 360×640 and
// deviceScaleFactor 3.
const VIEWPORT = { width: 360, height: 640 };
const DEVICE_SCALE_FACTOR = 3;

async function settle(page) {
  await page.locator('#loading').waitFor({ state: 'hidden', timeout: 20_000 });
  await page.locator('#map-svg .borough').first().waitFor({ timeout: 10_000 });
  await page.waitForTimeout(800);
}

async function shoot(page, name) {
  const path = join(OUT, name);
  await page.screenshot({ path, fullPage: false });
  console.log(`  → ${path}`);
}

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

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: DEVICE_SCALE_FACTOR,
    isMobile: true,
    hasTouch: true,
    userAgent:
      'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 ' +
      '(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36',
    locale: 'en-GB',
    timezoneId: 'Europe/London',
  });
  const page = await context.newPage();

  // Reveal `.native-only` elements (matches the runtime reveal at
  // index.html:2522 when Capacitor is detected). If the live site lacks
  // the locate-me button (web deploy not yet caught up), inject one so
  // the Play Store screenshot matches what Android users will see.
  await page.addInitScript(() => {
    window.addEventListener('DOMContentLoaded', () => {
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
          'font: 600 16px/1 Roboto, "Segoe UI", system-ui, sans-serif',
          'box-shadow: 0 8px 24px rgba(0,0,0,0.25)',
          'z-index: 9999',
          'cursor: pointer',
        ].join(';');
        (document.body || document.documentElement).appendChild(btn);
      }
    });
  });

  // 1. Hero — map of London with a postcode searched
  console.log('1/5 hero (postcode search)');
  await page.goto(SITE);
  await settle(page);
  await page.locator('#search-input').fill('SW1A 1AA');
  await page.locator('#search-input').press('Enter');
  await page.waitForTimeout(2500);
  await dismissAutocomplete(page);
  await shoot(page, '01_hero.png');

  // 2. "Score where I am" — native-only GPS button visible
  console.log('2/5 score where I am button');
  await page.goto(SITE);
  await settle(page);
  await page.locator('#locate-me').scrollIntoViewIfNeeded();
  await shoot(page, '02_score_where_i_am.png');

  // 3. Score breakdown — sidebar populated
  console.log('3/5 score breakdown');
  await page.goto(SITE);
  await settle(page);
  await page.locator('#search-input').fill('SW11 1AA');
  await page.locator('#search-input').press('Enter');
  await page.waitForTimeout(3000);
  await dismissAutocomplete(page);
  await page.evaluate(() => {
    const sidebar = document.getElementById('sidebar-content');
    if (sidebar) sidebar.scrollTop = 400;
    window.scrollTo({ top: 400, behavior: 'instant' });
  });
  await page.waitForTimeout(500);
  await shoot(page, '03_score_breakdown.png');

  // 4. Aircraft noise overlay + road
  console.log('4/5 noise overlay (aircraft + road)');
  await page.goto(SITE);
  await settle(page);
  await page.locator('.layer-toggle[data-layer="paths"]').click();
  await page.waitForTimeout(600);
  await page.locator('.layer-toggle[data-layer="defra-road"]').click();
  await page.waitForTimeout(2000);
  await shoot(page, '04_noise_overlay.png');

  // 5. Rankings tab — borough comparison
  console.log('5/5 rankings (borough comparison)');
  await page.goto(SITE);
  await settle(page);
  await page.locator('#search-input').fill('SW11 1AA');
  await page.locator('#search-input').press('Enter');
  await page.waitForTimeout(3000);
  await dismissAutocomplete(page);
  await page.locator('#tab-btn-ranking').click({ timeout: 5000 });
  await page.waitForTimeout(2000);
  await shoot(page, '05_rankings.png');

  await browser.close();
  console.log(`\nDone. 5 screenshots in ${OUT}/ (1080×1920 each)`);
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
