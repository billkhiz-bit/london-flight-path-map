import { chromium, devices } from '@playwright/test';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';

const fileUrl = pathToFileURL(resolve('index.html')).href;
const iPhone = devices['iPhone 13'];

async function mobile() {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ ...iPhone });
  const page = await ctx.newPage();
  await page.addInitScript(() => {
    window.Capacitor = { isNativePlatform: () => true, getPlatform: () => 'ios', Plugins: {} };
  });
  await page.goto(fileUrl, { waitUntil: 'load' }).catch(() => {});
  await page.waitForTimeout(2500);

  const navVisible = await page.evaluate(() => {
    const n = document.getElementById('mobile-nav');
    if (!n) return false;
    const r = n.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(n).display !== 'none';
  });
  console.log('mobile-nav visible:', navVisible);

  for (const view of ['search', 'map', 'ranking', 'saved']) {
    await page.evaluate((v) => window.setMobileView(v), view);
    await page.waitForTimeout(800);
    const m = await page.evaluate(() => ({
      mview: document.querySelector('.app').dataset.mview,
      overflowX: document.documentElement.scrollWidth - window.innerWidth,
      installVisible: (() => {
        const el = document.getElementById('install-prompt');
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && getComputedStyle(el).display !== 'none';
      })(),
      activeNav: [...document.querySelectorAll('.mobile-nav-btn.active')].map((b) => b.dataset.mview),
    }));
    console.log(`view=${view}:`, JSON.stringify(m));
    await page.screenshot({ path: `tests/mview-${view}.png` });
  }
  await browser.close();
}

async function desktop() {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await page.goto(fileUrl, { waitUntil: 'load' }).catch(() => {});
  await page.waitForTimeout(2000);
  const d = await page.evaluate(() => {
    const n = document.getElementById('mobile-nav');
    const navShown = n ? getComputedStyle(n).display !== 'none' : null;
    const cols = getComputedStyle(document.querySelector('.app')).gridTemplateColumns;
    return { navShown, gridCols: cols, overflowX: document.documentElement.scrollWidth - window.innerWidth };
  });
  console.log('\nDESKTOP 1440px:', JSON.stringify(d));
  await page.screenshot({ path: 'tests/desktop-regression.png' });
  await browser.close();
}

console.log('=== MOBILE (native sim, iPhone 13) ===');
await mobile();
await desktop();
