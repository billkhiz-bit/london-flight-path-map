import { chromium } from '@playwright/test';

// Verify the LIVE deployed redesign across phone widths (web context — what
// real skyscore.co.uk / PWA users see right now).
const URL = 'https://d1oe4ftwutjpf.cloudfront.net/index.html?cb=' + Date.now();
const widths = [
  { w: 360, h: 800, label: 'small Android (360)' },
  { w: 390, h: 844, label: 'iPhone 13 (390)' },
  { w: 414, h: 896, label: 'iPhone 11 Plus (414)' },
];

const browser = await chromium.launch();
for (const { w, h, label } of widths) {
  const ctx = await browser.newContext({
    viewport: { width: w, height: h },
    isMobile: true,
    hasTouch: true,
    deviceScaleFactor: 2,
  });
  const page = await ctx.newPage();
  await page.goto(URL, { waitUntil: 'networkidle' }).catch(() => {});
  await page.waitForTimeout(2500);
  const r = await page.evaluate(() => {
    const n = document.getElementById('mobile-nav');
    const navBox = n ? n.getBoundingClientRect() : null;
    return {
      navVisible: !!navBox && navBox.width > 0 && getComputedStyle(n).display !== 'none',
      navItems: [...document.querySelectorAll('.mobile-nav-btn')].map((b) => b.dataset.mview),
      overflowX: document.documentElement.scrollWidth - window.innerWidth,
      defaultView: document.querySelector('.app')?.dataset.mview ?? '(unset)',
    };
  });
  console.log(`${label}:`, JSON.stringify(r));
  await page.screenshot({ path: `tests/live-${w}.png` });
  await ctx.close();
}
await browser.close();
