import { chromium } from '@playwright/test';

// Verify the LIVE deployed WEB layout across phone widths — what real
// skyscore.co.uk / PWA users see. As of the 2026-05-29 web/native split, the
// mobile redesign (bottom nav + map-as-background) is NATIVE-APP ONLY; the
// website serves the CLASSIC bottom-sheet layout. So on live web we expect NO
// bottom nav, no data-mview, and the sheet handle present. This goes green
// once the reverted index.html is deployed to CloudFront — until then live
// still carries the old v1 redesign and this will report FAIL (expected).
const URL = 'https://d1oe4ftwutjpf.cloudfront.net/index.html?cb=' + Date.now();
const widths = [
  { w: 360, h: 800, label: 'small Android (360)' },
  { w: 390, h: 844, label: 'iPhone 13 (390)' },
  { w: 414, h: 896, label: 'iPhone 11 Plus (414)' },
];

const browser = await chromium.launch();
let allOk = true;
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
    const vis = (el) => (el ? getComputedStyle(el).display !== 'none' : false);
    const n = document.getElementById('mobile-nav');
    const sheet = document.getElementById('sheet-handle');
    return {
      isNativeClass: document.documentElement.classList.contains('is-native'),
      navVisible: vis(n),
      sheetHandleVisible: vis(sheet),
      overflowX: document.documentElement.scrollWidth - window.innerWidth,
      defaultView: document.querySelector('.app')?.dataset.mview ?? '(unset)',
    };
  });
  // Classic web layout: redesign OFF, sheet handle present, no overflow.
  const ok =
    r.isNativeClass === false && r.navVisible === false && r.sheetHandleVisible === true && r.overflowX <= 1;
  allOk = allOk && ok;
  console.log(`${label}:`, JSON.stringify(r), ok ? 'PASS' : 'FAIL');
  await page.screenshot({ path: `tests/live-${w}.png` });
  await ctx.close();
}
await browser.close();
if (!allOk) {
  console.error('\nLive web is NOT on the classic layout — either the revert is not deployed yet, or the redesign leaked onto web.');
  process.exit(1);
}
console.log('\nAll widths: live web on CLASSIC layout — PASS');
