// Exercises the two demo fallbacks that were shipped untested on 2026-07-30:
//   1. a stalled network must render CONNECTION ISSUE + a working retry,
//      not "NOT FOUND"
//   2. the service worker must install and an offline reload must still
//      paint a map (cache.addAll is all-or-nothing, so a single missing
//      SHELL_ASSET silently prevents the SW installing at all)
import { chromium } from '@playwright/test';

const BASE = process.env.SMOKE_BASE || 'https://d1oe4ftwutjpf.cloudfront.net';
const results = [];
const record = (name, pass, detail = '') => {
  results.push({ name, pass, detail });
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`);
};

const browser = await chromium.launch();
const context = await browser.newContext();
const page = await context.newPage();

// ---------------------------------------------------------------------------
// 1. Timeout path
// ---------------------------------------------------------------------------
await page.goto(`${BASE}/index.html`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('#app', { state: 'visible', timeout: 30000 });

// Stall postcodes.io past the 5s SEARCH_TIMEOUT_MS without failing it, so we
// hit AbortSignal.timeout (TimeoutError) rather than a transport error.
let stall = true;
await page.route('**api.postcodes.io/**', async (route) => {
  if (stall) {
    await new Promise((r) => setTimeout(r, 9000));
    return route.abort('timedout');
  }
  return route.continue();
});

const input = page.locator('#search-input');
await input.fill('TW3 1AA');
await input.press('Enter');

let title = '';
for (let i = 0; i < 60; i++) {
  await page.waitForTimeout(250);
  title = ((await page.locator('#sidebar-title').textContent()) || '').trim();
  if (title && !/SEARCHING/i.test(title)) break;
}
record('stalled network does NOT say NOT FOUND', !/NOT FOUND/i.test(title), `title="${title}"`);
record('stalled network says CONNECTION ISSUE', /CONNECTION ISSUE/i.test(title), `title="${title}"`);

const bodyText = ((await page.locator('#sidebar-content').textContent()) || '').replace(/\s+/g, ' ');
record(
  'copy explains it is a connection problem',
  /connection problem, not a bad search/i.test(bodyText),
  bodyText.slice(0, 90)
);

const retry = page.locator('#search-retry-btn');
const retryVisible = await retry.isVisible().catch(() => false);
record('retry button is present', retryVisible);

// Retry with the network restored — this is the exact on-stage recovery move.
if (retryVisible) {
  stall = false;
  await retry.click();
  let recovered = '';
  for (let i = 0; i < 60; i++) {
    await page.waitForTimeout(250);
    recovered = ((await page.locator('#sidebar-title').textContent()) || '').trim();
    if (recovered && !/SEARCHING|CONNECTION/i.test(recovered)) break;
  }
  record('retry recovers the search', /TW3/i.test(recovered), `title="${recovered}"`);
}

await page.unroute('**api.postcodes.io/**');

// ---------------------------------------------------------------------------
// 2. Service worker + offline launch
// ---------------------------------------------------------------------------
const page2 = await context.newPage();
await page2.goto(`${BASE}/index.html`, { waitUntil: 'load' });

const swState = await page2.evaluate(async () => {
  if (!('serviceWorker' in navigator)) return 'unsupported';
  const reg = await navigator.serviceWorker.getRegistration();
  if (!reg) return 'none';
  // Wait for it to reach activated.
  for (let i = 0; i < 40; i++) {
    const w = reg.active || reg.installing || reg.waiting;
    if (reg.active) return 'activated';
    if (w && w.state === 'redundant') return 'redundant';
    await new Promise((r) => setTimeout(r, 250));
  }
  return 'timeout-waiting';
});
record('service worker activates', swState === 'activated', `state=${swState}`);

// Did the precache actually take? addAll rejects atomically, so verify the two
// newly-added entries are really there.
const cached = await page2.evaluate(async () => {
  const keys = await caches.keys();
  const out = { keys, d3: false, geo: false, nycGeo: false };
  for (const k of keys) {
    const c = await caches.open(k);
    if (await c.match('/js/vendor/d3.v7.min.js')) out.d3 = true;
    if (await c.match('/data/london-boroughs.json')) out.geo = true;
    if (await c.match('/data/nyc-boroughs.json')) out.nycGeo = true;
  }
  return out;
});
record('d3 is precached', cached.d3, cached.keys.join(','));
record('borough geojson is precached', cached.geo);
record('nyc geojson is precached', cached.nycGeo);

// Now go offline and reload. This is the "tether dies mid-demo" scenario.
await context.setOffline(true);
let offlineOk = false;
let offlineBoroughs = 0;
try {
  await page2.reload({ waitUntil: 'domcontentloaded', timeout: 30000 });
  await page2.waitForSelector('#app', { state: 'visible', timeout: 25000 });
  offlineBoroughs = await page2.locator('path.borough').count();
  offlineOk = offlineBoroughs >= 30;
} catch (e) {
  offlineOk = false;
  offlineBoroughs = -1;
}
record('offline reload still paints the map', offlineOk, `borough paths=${offlineBoroughs}`);

// Still offline: switch city. Until 2026-07-30 this fetched 2.67 MB from
// raw.githubusercontent.com at click time, so the one interaction most likely
// to be performed on stage was also the one guaranteed to fail without a
// network.
//
// CAVEAT — this check only bites against a REMOTE base. Chromium's offline
// emulation does not apply to loopback, so under the localhost harness the
// same-origin fetch succeeds on its own and this passes even with the asset
// absent from SHELL_ASSETS (verified: it lands in RUNTIME_CACHE instead).
// 'nyc geojson is precached' above is the assertion that actually goes red
// locally. Run this against CloudFront to exercise the offline path for real.
let offlineNyc = 0;
try {
  await page2.click('.city-btn[data-city="nyc"]');
  await page2.waitForFunction(() => document.querySelectorAll('path.borough').length === 5, {
    timeout: 20000,
  });
  offlineNyc = await page2.locator('path.borough').count();
} catch {
  offlineNyc = await page2.locator('path.borough').count();
}
record('offline switch to NYC still paints', offlineNyc === 5, `borough paths=${offlineNyc}`);
await context.setOffline(false);

await browser.close();

const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
if (failed.length) {
  console.log('FAILED:');
  failed.forEach((f) => console.log(`  - ${f.name} ${f.detail}`));
}
process.exit(failed.length ? 1 : 0);
