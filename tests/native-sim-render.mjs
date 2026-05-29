// Renders index.html in three contexts to prove the web/native split:
//   1. mobile()    — native sim (Capacitor shim) → expects the REDESIGN
//   2. webMobile()  — plain web/PWA (no shim)      → expects the CLASSIC sheet
//   3. desktop()    — 1440px                        → expects the two-col grid
// The redesign is gated behind the is-native class (set only in the Capacitor
// app), so (1) and (2) must diverge. See MOBILE_REDESIGN_PLAN.md.
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

  for (const view of ['search', 'ranking', 'saved']) {
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
      mapVisible: (() => {
        const m = document.getElementById('map-container');
        return m ? getComputedStyle(m).visibility === 'visible' : null;
      })(),
      searchBoxVisible: (() => {
        const i = document.getElementById('search-input');
        if (!i) return false;
        const r = i.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
      })(),
      activeNav: [...document.querySelectorAll('.mobile-nav-btn.active')].map((b) => b.dataset.mview),
      navCount: document.querySelectorAll('.mobile-nav-btn').length,
    }));
    console.log(`view=${view}:`, JSON.stringify(m));
    await page.screenshot({ path: `tests/mview-${view}.png` });
  }
  await browser.close();
}

// Web/PWA context: NO Capacitor shim, so window.Capacitor is undefined,
// setupNativeFeatures() bails, the is-native class is never added, and the
// redesign rules must stay dormant. The site should fall back to the classic
// bottom-sheet layout: no bottom nav, no data-mview, sheet handle present.
async function webMobile() {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ ...iPhone }); // no addInitScript -> plain web
  const page = await ctx.newPage();
  await page.goto(fileUrl, { waitUntil: 'load' }).catch(() => {});
  await page.waitForTimeout(2500);
  const r = await page.evaluate(() => {
    const vis = (el) => (el ? getComputedStyle(el).display !== 'none' : null);
    const nav = document.getElementById('mobile-nav');
    const sheet = document.getElementById('sheet-handle');
    const map = document.getElementById('map-container');
    return {
      isNativeClass: document.documentElement.classList.contains('is-native'),
      navVisible: vis(nav),
      mview: document.querySelector('.app')?.dataset.mview ?? '(unset)',
      sheetHandleVisible: vis(sheet),
      mapVisible: map ? getComputedStyle(map).visibility === 'visible' : null,
      overflowX: document.documentElement.scrollWidth - window.innerWidth,
    };
  });
  console.log('\n=== WEB MOBILE (no Capacitor, iPhone 13) — expect CLASSIC layout ===');
  console.log(JSON.stringify(r));
  await page.screenshot({ path: 'tests/web-mobile-classic.png' });
  await browser.close();
  const ok =
    r.isNativeClass === false &&
    r.navVisible === false &&
    r.mview === '(unset)' &&
    r.sheetHandleVisible === true &&
    r.overflowX <= 1;
  console.log(ok ? 'WEB-MOBILE CLASSIC: PASS' : 'WEB-MOBILE CLASSIC: FAIL');
  return ok;
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

console.log('=== MOBILE (native sim, iPhone 13) — expect REDESIGN ===');
await mobile();
const webOk = await webMobile();
await desktop();
if (!webOk) {
  console.error('\nFAIL: web mobile is not on the classic layout (the redesign leaked onto web).');
  process.exit(1);
}
