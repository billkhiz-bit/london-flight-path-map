// Local smoke test for the 2026-07-30 asset-vendoring change.
// Verifies the app still paints when d3 and the borough boundaries come from
// our own origin, and that no CSP rule blocks them.
import { chromium } from '@playwright/test';

// Defaults to a static server on 8123 in the repo root — `python -m
// http.server 8123`, or `npx serve -l 8123` on a machine without Python. Point
// it at CloudFront with SMOKE_BASE to verify a deploy:
//   SMOKE_BASE=https://d1oe4ftwutjpf.cloudfront.net node tests/smoke-local.mjs
const BASE = process.env.SMOKE_BASE || 'http://127.0.0.1:8123';

const consoleErrors = [];
const failedRequests = [];
const requests = [];

const browser = await chromium.launch();
const page = await browser.newPage();

page.on('console', (msg) => {
  if (msg.type() === 'error') consoleErrors.push(msg.text());
});
page.on('requestfailed', (req) => {
  failedRequests.push(`${req.url()} :: ${req.failure()?.errorText}`);
});
page.on('request', (req) => requests.push(req.url()));

await page.goto(`${BASE}/index.html`, { waitUntil: 'domcontentloaded' });

// init() reveals #app only after loadGeoJson() resolves, so this waiting at
// all is the real assertion: it proves the local boundary file was parsed.
let appVisible = false;
try {
  await page.waitForSelector('#app', { state: 'visible', timeout: 20000 });
  appVisible = true;
} catch {
  appVisible = false;
}

const boroughCount = await page.locator('path.borough').count();
const d3Loaded = await page.evaluate(() => typeof window.d3 !== 'undefined' && !!window.d3.version);
const d3Version = await page.evaluate(() => (window.d3 ? window.d3.version : null));

const askedGithub = requests.some((u) => u.includes('raw.githubusercontent.com'));
const askedD3Cdn = requests.some((u) => u.includes('d3js.org'));
const askedLocalGeo = requests.some((u) => u.includes('/data/london-boroughs.json'));
const askedLocalD3 = requests.some((u) => u.includes('/js/vendor/d3.v7.min.js'));

// Borough names actually rendered — the Brentwood check.
const renderedNames = await page.evaluate(() => {
  const out = [];
  document.querySelectorAll('path.borough').forEach((el) => {
    const d = el.__data__;
    if (!d) return;
    const p = d.properties || {};
    out.push(p.LAD13NM || p.name || p.NAME || '');
  });
  return out;
});

// --- NYC, added 2026-07-30 ---
// The github-raw assertion below is only meaningful for the path the test
// actually walks, and until now that was London alone. NYC kept its 2.67 MB
// cross-origin fetch for another wave precisely because nothing exercised the
// city switch. Everything above this line is London; everything after the
// click is NYC.
const londonRequestCount = requests.length;
await page.click('.city-btn[data-city="nyc"]');

let nycBoroughCount = 0;
try {
  // switchCity() awaits the boundary fetch before rendering, so polling for
  // the paths is what proves the local file was fetched, parsed and drawn.
  await page.waitForFunction(() => document.querySelectorAll('path.borough').length >= 5, {
    timeout: 20000,
  });
  nycBoroughCount = await page.locator('path.borough').count();
} catch {
  nycBoroughCount = await page.locator('path.borough').count();
}

const nycRequests = requests.slice(londonRequestCount);
const nycAskedGithub = nycRequests.some((u) => u.includes('raw.githubusercontent.com'));
const nycAskedLocalGeo = nycRequests.some((u) => u.includes('/data/nyc-boroughs.json'));

// renderNycBoroughs() looks data up by `properties.name`, so a build that
// renamed or dropped that key would still draw outlines but make every click
// a no-op. Assert the names, not just the count.
const nycNames = await page.evaluate(() => {
  const out = [];
  document.querySelectorAll('path.borough').forEach((el) => {
    const d = el.__data__;
    if (d && d.properties && d.properties.name) out.push(d.properties.name);
  });
  return out;
});
const NYC_EXPECTED = ['Queens', 'Brooklyn', 'Manhattan', 'Bronx', 'Staten Island'];
const nycNamesOk = NYC_EXPECTED.every((n) => nycNames.includes(n));

console.log('--- LOCAL SMOKE ---');
console.log('#app visible:            ', appVisible);
console.log('d3 loaded:               ', d3Loaded, d3Version);
console.log('borough paths rendered:  ', boroughCount);
console.log('requested /js/vendor/d3: ', askedLocalD3);
console.log('requested local geojson: ', askedLocalGeo);
console.log('requested d3js.org:      ', askedD3Cdn, '(must be false)');
console.log('requested github raw:    ', askedGithub, '(must be false)');
console.log('Brentwood rendered:      ', renderedNames.includes('Brentwood'), '(must be false)');
console.log('--- after switch to NYC ---');
console.log('NYC borough paths:       ', nycBoroughCount, '(expect 5)');
console.log('NYC names all present:   ', nycNamesOk, nycNamesOk ? '' : JSON.stringify(nycNames));
console.log('requested nyc geojson:   ', nycAskedLocalGeo);
console.log('requested github raw:    ', nycAskedGithub, '(must be false)');
console.log('console errors:          ', consoleErrors.length);
consoleErrors.slice(0, 12).forEach((e) => console.log('   !', e));
console.log('failed requests:         ', failedRequests.length);
failedRequests.slice(0, 12).forEach((e) => console.log('   x', e));

await browser.close();

const ok =
  appVisible &&
  d3Loaded &&
  boroughCount >= 30 &&
  askedLocalD3 &&
  askedLocalGeo &&
  !askedD3Cdn &&
  !askedGithub &&
  !renderedNames.includes('Brentwood') &&
  nycBoroughCount === 5 &&
  nycNamesOk &&
  nycAskedLocalGeo &&
  !nycAskedGithub;

console.log('\nRESULT:', ok ? 'PASS' : 'FAIL');
process.exit(ok ? 0 : 1);
