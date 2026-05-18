/**
 * Sky Score iPad-layout verification.
 *
 * Renders the local index.html via a local HTTP server at iPad Air 11"
 * M3 (Apple's review device) plus a desktop and phone for regression.
 *
 * Run: `node tests/ipad-verify.mjs`
 * Output: mobile/.preview/{ipad-landscape,ipad-portrait,desktop,phone}.png
 */

import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';

const URL = 'http://localhost:8765/index.html';
const OUT = 'mobile/.preview';

const VIEWPORTS = [
  { name: 'ipad-landscape', width: 1180, height: 820, touch: true },
  { name: 'ipad-portrait', width: 820, height: 1180, touch: true },
  { name: 'desktop', width: 1440, height: 900, touch: false },
  { name: 'phone', width: 390, height: 844, touch: true },
];

async function settle(page) {
  await page.locator('#loading').waitFor({ state: 'hidden', timeout: 20_000 });
  await page.locator('#map-svg .borough').first().waitFor({ timeout: 10_000 });
  await page.waitForTimeout(600);
}

async function main() {
  await mkdir(OUT, { recursive: true });
  const browser = await chromium.launch();
  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      hasTouch: vp.touch,
      isMobile: false,
      deviceScaleFactor: 2,
    });
    const page = await ctx.newPage();
    await page.goto(URL, { waitUntil: 'domcontentloaded' });
    await settle(page);

    const diag = await page.evaluate(() => {
      const sidebar = document.querySelector('.sidebar');
      const cs = sidebar ? getComputedStyle(sidebar) : null;
      return {
        w: window.innerWidth,
        h: window.innerHeight,
        sidebarH: cs?.height,
        sidebarPos: cs?.position,
        sheetOpen: sidebar?.classList.contains('sheet-open'),
      };
    });
    console.log(`  ${vp.name.padEnd(15)}: ${JSON.stringify(diag)}`);

    const path = join(OUT, `${vp.name}.png`);
    await page.screenshot({ path, fullPage: false });
    await ctx.close();
  }
  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
