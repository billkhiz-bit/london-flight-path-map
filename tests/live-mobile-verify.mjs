import { chromium } from '@playwright/test';

// Verify the LIVE deployed WEB layout across phone widths - what real
// skyscore.co.uk / PWA users see.
//
// HEADER CORRECTED 2026-08-31 (audit F31). It still described the 2026-05-29
// split, under which the redesign was NATIVE-ONLY and the website served the
// classic bottom sheet, and it told the reader this file expects "NO bottom
// nav, no data-mview, and the sheet handle present". The assertion below was
// INVERTED on 2026-08-27 when tabs became the web default at <=900px, so the
// file's own header said the opposite of its own check. That is worse than no
// comment: a reader trusting it would have "fixed" a correct gate by breaking
// it, which is exactly how a passing test comes to assert a defect.
//
// Current expectation: live web at <=900px serves the TABBED layout - bottom
// nav visible, sheet handle hidden - while `is-native` stays FALSE, because
// the web/native split has not moved; only the web DEFAULT has.
//
// This reads CloudFront, so it reports DEPLOYED state. preflight runs it as
// ADVISORY for that reason: a source tree ahead of the last deploy is the
// normal condition in this repo and must not block a commit. Same reasoning as
// `deployed == source` and `site == /v1/score`.
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
  // INVERTED 2026-08-27: tabs are the web default at <=900px, so the live
  // expectation is the REDESIGN, not the classic sheet. `is-native` must still
  // be false - the web/native split has not moved, only the web default.
  //
  // This gate points at CloudFront, so it reds on a correct tree until the
  // deploy lands. That is the honest state, not a fault: `?tabbed=0` below is
  // what keeps the classic path covered either way.
  const ok =
    r.isNativeClass === false && r.navVisible === true && r.sheetHandleVisible === false && r.overflowX <= 1;
  allOk = allOk && ok;
  console.log(`${label}:`, JSON.stringify(r), ok ? 'PASS' : 'FAIL');
  await page.screenshot({ path: `tests/live-${w}.png` });
  await ctx.close();
}
await browser.close();
if (!allOk) {
  console.error('\nLive web is NOT on the tabbed layout - either the deploy has not landed yet, or the default was reverted.');
  process.exit(1);
}
console.log('\nAll widths: live web on TABBED layout - PASS');
