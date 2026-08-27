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
    // The `unroute` below can land while this handler is still sleeping: the
    // autocomplete fires several postcodes.io requests as the field fills, and
    // each takes its own 9s nap. Playwright auto-handles outstanding routes on
    // unroute, so aborting one here throws "Route is already handled!" - an
    // unhandled rejection, which Node 24 turns into a FATAL.
    //
    // The file then exited 1 having never run the checks below, which reads as
    // a FAILING gate rather than a crashed one. Same shape as the undrained
    // `fetch` body that had `responsive, source` reporting FAIL on zero pages
    // (2026-08-26); this is the sibling instance, and it hid because nothing
    // in preflight or package.json has ever run this file.
    try {
      await route.abort('timedout');
    } catch {
      /* already handled by unroute - the stall has served its purpose */
    }
    return;
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
// TWO TIERS since 2026-08-11: the chip row renders only the ACTIVE country's
// cities, so `.city-btn[data-city="nyc"]` does not exist in the DOM until the
// USA tab is selected. This check predated that change and had been clicking a
// selector matching nothing - and the bare `catch` then reported London's 33
// boroughs, which reads as "the switch was attempted and painted the wrong
// city". A MISSING CONTROL was being rendered as a MEASUREMENT of broken
// offline behaviour, and it was neither: verified by hand 2026-08-27 against
// CloudFront, offline NYC paints all 5 via the real user path.
//
// `nycStep` is why this is not just a selector edit. Swallowing the throw into
// a borough count is what let a stale selector masquerade as a finding for
// sixteen days, so the failure now NAMES the step it died on.
let offlineNyc = 0;
let nycStep = '';
try {
  nycStep = 'country tab';
  await page2.click('.country-btn[data-country="United States"]', { timeout: 10000 });
  nycStep = 'city chip';
  await page2.click('.city-btn[data-city="nyc"]', { timeout: 10000 });
  nycStep = 'paint';
  await page2.waitForFunction(() => document.querySelectorAll('path.borough').length === 5, {
    timeout: 20000,
  });
  nycStep = '';
  offlineNyc = await page2.locator('path.borough').count();
} catch {
  offlineNyc = await page2.locator('path.borough').count();
}
record(
  'offline switch to NYC still paints',
  offlineNyc === 5,
  nycStep ? `died at "${nycStep}" (borough paths=${offlineNyc})` : `borough paths=${offlineNyc}`
);
await context.setOffline(false);

// ---------------------------------------------------------------------------
// 3. Partial TfL outage: stations resolve, line status does not
// ---------------------------------------------------------------------------
// The transport Lambda has published `lineStatusAvailable` since 2026-08-24 to
// separate "TfL answered and nothing near you is disrupted" from "we could not
// ask". Nothing read it until 2026-08-27, so a 403 on the Status route
// rendered as NO SECTION AT ALL, indistinguishable from a clean network.
//
// Asserted in ALL THREE directions on purpose. A test that only proves the
// notice APPEARS cannot catch a change that makes it appear always, which
// would be the same defect pointing the other way: a false outage claim on
// every good-service response.
const tfl = await browser.newContext({ serviceWorkers: 'block' });
const page3 = await tfl.newPage();

let transportBody = null;
let stubHits = 0;
// A URL PREDICATE, not a glob. `'**/transport?**'` silently matched nothing
// here, so every case below was quietly answered by the REAL TfL API - and it
// looked fine, because the stub values were realistic: SW11 1AA really is
// ~420m from Clapham Junction on Southern. A fixture chosen to look plausible
// cannot tell you it was never used, so `stubHits` is asserted below.
await page3.route(
  (url) => url.pathname.endsWith('/transport'),
  async (route) => {
    if (!transportBody) return route.continue();
    stubHits++;
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'access-control-allow-origin': '*' },
      body: JSON.stringify(transportBody),
    });
  }
);

const STATIONS = [{ name: 'Clapham Junction Rail Station', lines: ['southern'], distance: 420 }];
const NOTICE = /could not be checked just now/i;

async function transportPanelText(body) {
  transportBody = body;
  stubHits = 0;
  await page3.goto(`${BASE}/index.html`, { waitUntil: 'domcontentloaded' });
  await page3.waitForSelector('#app', { state: 'visible', timeout: 30000 });
  await page3.fill('#search-input', 'SW11 1AA');
  await page3.press('#search-input', 'Enter');

  // Poll until the text STOPS CHANGING, not until it stops saying "Loading".
  // The panel settles in stages, so "first non-loading read" caught it with
  // the stations painted and the status section not yet appended - which is
  // indistinguishable from the defect this section exists to catch. A gate
  // that reads a half-rendered panel manufactures its own red.
  //
  // Read via getElementById, NOT page.locator(): the postcode panel has three
  // template branches that each declare #postcode-transport-data, so a
  // locator is strict-mode ambiguous and its throw would be swallowed by the
  // catch below into an empty string.
  const read = () =>
    page3
      .evaluate(() => {
        const el = document.getElementById('postcode-transport-data');
        return el ? el.innerText.trim() : '';
      })
      .catch(() => '');

  let prev = null;
  for (let i = 0; i < 40; i++) {
    await page3.waitForTimeout(300);
    const t = await read();
    if (t && !/Finding nearest|Loading/i.test(t) && t === prev) return t;
    prev = t;
  }
  return (await read()) || '';
}

// Reads the panel AND proves the stub answered it. Without this the whole
// section degrades into an assertion about live TfL, which is the
// self-authored-fixture trap one level up: the fixture existed, looked right,
// and was never exercised.
async function stubbedPanel(name, body) {
  const text = await transportPanelText(body);
  record(`${name}: the stub actually answered /transport`, stubHits > 0, `hits=${stubHits}`);
  return text;
}

// (a) the defect case: statuses were never fetched.
const unavailable = await stubbedPanel('partial outage', {
  stations: STATIONS,
  lineStatus: [],
  lineStatusAvailable: false,
  available: true,
});
record('partial TfL outage says line status was not checked', NOTICE.test(unavailable), unavailable.slice(0, 120));
record(
  'partial TfL outage still lists the stations it did get',
  /Clapham Junction/i.test(unavailable),
  unavailable.slice(0, 120)
);
// Asserted on the DOM, not on the panel text. The notice deliberately
// contains the words "not a report of good service", so a /Good Service/
// substring test matches the fix itself and reds on a correct tree - the
// assertion and the copy it checks were one edit away from each other.
// A status ROW is the thing that must not exist.
const statusRows = await page3.evaluate(
  () => document.querySelectorAll('#postcode-transport-data .line-status').length
);
record('partial TfL outage renders no status rows', statusRows === 0, `rows=${statusRows}`);

// (b) the inverse: TfL answered, nothing disrupted. Must NOT cry outage.
const checkedEmpty = await stubbedPanel('checked-and-quiet', {
  stations: STATIONS,
  lineStatus: [],
  lineStatusAvailable: true,
  available: true,
});
record('checked-and-quiet does NOT show the outage notice', !NOTICE.test(checkedEmpty), checkedEmpty.slice(0, 120));

// (c) a response cached before the field existed. `undefined` meant "checked"
// under the old contract, so a truthiness test here would flip every stale
// cached response into a false outage notice.
const legacy = await stubbedPanel('legacy shape', { stations: STATIONS, lineStatus: [], available: true });
record('pre-2026-08-24 response shape does NOT show the outage notice', !NOTICE.test(legacy), legacy.slice(0, 120));

await tfl.close();

await browser.close();

const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
if (failed.length) {
  console.log('FAILED:');
  failed.forEach((f) => console.log(`  - ${f.name} ${f.detail}`));
}
process.exit(failed.length ? 1 : 0);
