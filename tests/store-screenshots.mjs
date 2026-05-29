// Generate App Store iPhone screenshots of the NATIVE redesign.
//
// Renders the LIVE app (CloudFront) with a Capacitor shim injected, so the
// is-native gate activates and the bottom-nav redesign shows — exactly what
// the native build displays (same index.html in the WebView). Loading from the
// live origin (not file://) means the score/ranking API calls have valid CORS
// and the screenshots carry real data.
//
// Output sizes are App Store Connect-exact portrait resolutions (physical px =
// logical viewport * deviceScaleFactor 3). This listing's iPhone slot is the
// 6.5-inch display (established by the v1.0 set), which ASC accepts ONLY at:
//   6.5"      -> 1242 x 2688  (iPhone 11 Pro Max)   <- the slot ASC is asking for
//   6.7" alt  -> 1284 x 2778  (iPhone 13 Pro Max)   <- also accepted in that slot
// NOTE: 1290x2796 (newer 6.7") and 1320x2868 (6.9") are DIFFERENT slots and are
// rejected here — match the dimensions ASC actually requests, not Apple's
// newest device sizes.
//
// Caveat: these are Chromium renders of the WebView content — UI-accurate and
// dimension-correct, but without the iOS status bar / Dynamic Island safe-area
// inset a real device adds. Good enough to upload; for status-bar-perfect shots
// capture from the device (TestFlight) or an iOS Simulator (Mac/Codemagic).
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';

const URL = 'https://d1oe4ftwutjpf.cloudfront.net/index.html?shot=1';
const devices = [
  { name: 'iphone-6.5-1242x2688', w: 414, h: 896, dsf: 3 }, // 1242 x 2688 (iPhone 11 Pro Max) <- ASC slot
  { name: 'iphone-6.7-1284x2778', w: 428, h: 926, dsf: 3 }, // 1284 x 2778 (iPhone 13 Pro Max) — also accepted
];

for (const d of devices) {
  const dir = `store-screenshots/${d.name}`;
  mkdirSync(dir, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: d.w, height: d.h },
    deviceScaleFactor: d.dsf,
    isMobile: true,
    hasTouch: true,
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148',
  });
  const page = await ctx.newPage();
  // Inject the native bridge BEFORE any page script runs -> is-native added.
  await page.addInitScript(() => {
    window.Capacitor = { isNativePlatform: () => true, getPlatform: () => 'ios', Plugins: {} };
  });
  await page.goto(URL, { waitUntil: 'networkidle' }).catch(() => {});
  await page.waitForTimeout(3500);

  const nativeOn = await page.evaluate(() => document.documentElement.classList.contains('is-native'));
  const px = `${d.w * d.dsf}x${d.h * d.dsf}`;
  console.log(`\n=== ${d.name} (${px}) — is-native:${nativeOn} ===`);

  // Scene 1: hero — full-screen map + floating search card (empty search view).
  await page.evaluate(() => window.setMobileView && window.setMobileView('search'));
  await page.waitForTimeout(2500);
  await page.screenshot({ path: `${dir}/01-search-map.png` });
  console.log('  01-search-map.png');

  // Scene 2: a real score result over the map (click a quick-search chip ->
  // triggers a live API lookup -> result card slides up).
  const how = await page.evaluate(() => {
    const chip = document.querySelector('.quicksearch-chip');
    if (chip) {
      chip.click();
      return 'chip:' + (chip.dataset.quicksearch || '?');
    }
    const inp = document.getElementById('search-input');
    if (inp && typeof window.triggerSearch === 'function') {
      inp.value = 'SE10 8XJ';
      window.triggerSearch('SE10 8XJ');
      return 'input';
    }
    return 'none';
  });
  await page.waitForTimeout(5000); // live API + render
  await page.evaluate(() => window.setMobileView && window.setMobileView('search'));
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${dir}/02-score-result.png` });
  console.log(`  02-score-result.png (search via ${how})`);

  // Scene 3: rankings league table.
  await page.evaluate(() => window.setMobileView && window.setMobileView('ranking'));
  await page.waitForTimeout(3500);
  await page.screenshot({ path: `${dir}/03-rankings.png` });
  console.log('  03-rankings.png');

  await browser.close();
}
console.log('\nDone — see store-screenshots/<size>/*.png');
