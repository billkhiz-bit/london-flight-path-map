/**
 * Generates the Google Play feature graphic (1024×500 PNG, no alpha) into
 * `mobile/fastlane/metadata/android/en-GB/images/featureGraphic/`.
 *
 * Functional rather than ornate — the feature graphic is the banner Play
 * shows at the top of the listing page. It needs to be 1024×500, on-brand,
 * and readable. For v1.0 this script renders branded text + tagline + the
 * radar logo to a small data-URL HTML page, then screenshots it via
 * Playwright. The user can replace with a more designed graphic later
 * (Figma export) without touching this script — just drop a 1024×500
 * `featureGraphic.png` into the same dir.
 *
 * Run: `node tests/android-feature-graphic.mjs`
 */

import { chromium } from '@playwright/test';
import { mkdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';

const OUT_DIR = 'mobile/fastlane/metadata/android/en-GB/images/featureGraphic';
const OUT_FILE = 'featureGraphic.png';
const LOGO = 'mobile/assets/logo.png';
const SIZE = { width: 1024, height: 500 };

async function run() {
  await mkdir(OUT_DIR, { recursive: true });

  // Inline the logo as a data URL so the rendered page has no network
  // dependency. base64-encoded PNG is large but fits trivially in a
  // chromium goto.
  const logoBytes = await readFile(LOGO);
  const logoDataUrl = `data:image/png;base64,${logoBytes.toString('base64')}`;

  const html = `<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8"><title>Sky Score</title>
<style>
  html, body { margin: 0; padding: 0; width: 1024px; height: 500px; }
  body {
    background: radial-gradient(circle at 25% 50%, #0e2746 0%, #061427 60%, #03101e 100%);
    color: #ffffff;
    font-family: -apple-system, "Inter", "Segoe UI", Roboto, system-ui, sans-serif;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 64px;
    box-sizing: border-box;
  }
  .text {
    max-width: 580px;
  }
  h1 {
    font-size: 84px;
    font-weight: 800;
    letter-spacing: -0.02em;
    line-height: 0.95;
    margin: 0 0 18px 0;
    background: linear-gradient(180deg, #ffffff 0%, #c9d6e6 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  p.tag {
    font-size: 28px;
    font-weight: 500;
    line-height: 1.25;
    margin: 0 0 24px 0;
    color: #cdd9e8;
  }
  p.sub {
    font-size: 18px;
    font-weight: 400;
    line-height: 1.4;
    margin: 0;
    color: #8aa0bb;
  }
  .logo {
    width: 320px;
    height: 320px;
    flex-shrink: 0;
    filter: drop-shadow(0 12px 40px rgba(255,140,0,0.35));
  }
  .logo img { width: 100%; height: 100%; object-fit: contain; display: block; }
</style></head>
<body>
  <div class="text">
    <h1>Sky&nbsp;Score</h1>
    <p class="tag">UK postcode noise &amp; livability — score where you are.</p>
    <p class="sub">DEFRA noise maps · HM Land Registry · NHS · TfL · independent, open methodology</p>
  </div>
  <div class="logo"><img src="${logoDataUrl}" alt=""></div>
</body></html>`;

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: SIZE,
    deviceScaleFactor: 1, // 1024×500 exact; Play wants the exact spec, no DPR multiplier
  });
  const page = await context.newPage();
  await page.setContent(html, { waitUntil: 'networkidle' });
  await page.waitForTimeout(300); // settle webfonts/repaints

  const outPath = join(OUT_DIR, OUT_FILE);
  await page.screenshot({
    path: outPath,
    type: 'png',
    omitBackground: false,
    clip: { x: 0, y: 0, ...SIZE },
  });
  await browser.close();

  console.log(`Done. Feature graphic at: ${outPath}`);
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
