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
// Select a city through BOTH tiers. The chip row shows only the active
// country's cities, so clicking `.city-btn[data-city="nyc"]` while the UK tab
// is active waits 30s for an element that does not exist - which is exactly
// how this test failed when the country tier landed. Country first, then chip.
async function selectCity(id) {
  const want = await page.evaluate((c) => window.cityOf(c).country, id);
  const have = await page.evaluate(
    () => document.querySelector('.country-btn.active')?.dataset.country
  );
  if (want !== have) {
    await page.click(`.country-btn[data-country="${want}"]`);
    // switchCountry() routes through switchCity(), which awaits a boundary
    // fetch, so the chip row is rebuilt asynchronously.
    await page.waitForSelector(`.city-btn[data-city="${id}"]`, { timeout: 20000 });
  }
  await page.click(`.city-btn[data-city="${id}"]`);
}

const londonRequestCount = requests.length;
await selectCity('nyc');

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

// --- Greater Manchester, added 2026-08-09 ---
// The reason written above for NYC applied again, unchanged: nothing that
// loads the page had ever rendered this city. The site agreed with /v1/score
// on all ten boroughs only because someone diffed them by hand - the first cut
// drew ten correct outlines, the right airport and both approach corridors
// while disagreeing with the API on EVERY borough by up to 1.5 points, and
// nothing errored. A map that looks correct is not evidence.
//
// This also guards the git trap: data/* is gitignored and un-ignored file by
// file, so these boundaries lived on disk and outside git for a whole session.
// Asserting the local fetch here means a fresh clone fails the gate instead of
// the deploy serving "outlines could not be loaded".
const nycRequestCount = requests.length;
// Via selectCity too: this one crosses BACK from USA to UK, so the Manchester
// chip does not exist at the moment this line runs either.
await selectCity('manchester');

let manBoroughCount = 0;
try {
  // Coming from NYC's 5 paths, so waiting for >= 10 is a real wait rather than
  // a condition that is already true.
  await page.waitForFunction(() => document.querySelectorAll('path.borough').length >= 10, {
    timeout: 20000,
  });
  manBoroughCount = await page.locator('path.borough').count();
} catch {
  manBoroughCount = await page.locator('path.borough').count();
}

const manRequests = requests.slice(nycRequestCount);
const manAskedGithub = manRequests.some((u) => u.includes('raw.githubusercontent.com'));
const manAskedLocalGeo = manRequests.some((u) => u.includes('/data/manchester-boroughs.json'));

const manNames = await page.evaluate(() => {
  const out = [];
  document.querySelectorAll('path.borough').forEach((el) => {
    const d = el.__data__;
    if (d && d.properties && d.properties.name) out.push(d.properties.name);
  });
  return out;
});
// The boundary branch used to be `if london ... else <NYC>`, which meant a
// third city silently loaded New York's outlines. Asserting the names is what
// separates "drew ten shapes" from "drew the right ten shapes".
const MAN_EXPECTED = [
  'Bolton',
  'Bury',
  'Manchester',
  'Oldham',
  'Rochdale',
  'Salford',
  'Stockport',
  'Tameside',
  'Trafford',
  'Wigan',
];
const manNamesOk = MAN_EXPECTED.every((n) => manNames.includes(n));

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
console.log('--- after switch to Greater Manchester ---');
console.log('GM borough paths:        ', manBoroughCount, '(expect 10)');
console.log('GM names all present:    ', manNamesOk, manNamesOk ? '' : JSON.stringify(manNames));
console.log('requested gm geojson:    ', manAskedLocalGeo);
console.log('requested github raw:    ', manAskedGithub, '(must be false)');
console.log('console errors:          ', consoleErrors.length);
consoleErrors.slice(0, 12).forEach((e) => console.log('   !', e));
console.log('failed requests:         ', failedRequests.length);
failedRequests.slice(0, 12).forEach((e) => console.log('   x', e));

// --- City registry: an unknown city must FAIL, not silently become London ---
//
// Added 2026-08-08 with the CITY_DATA refactor. Twenty-six binary ternaries
// (`city === 'nyc' ? NYC_X : X`) were correct for exactly two cities and
// silently wrong for three: anything not 'nyc' inherited London's airports,
// flight paths and borough data under another city's name. This asserts the new
// behaviour directly, because "London still renders" cannot distinguish the fix
// from its absence — that passed before the refactor too.
const registry = await page.evaluate(() => {
  const out = {
    known: [],
    throwsOnUnknown: false,
    londonOk: false,
    nycOk: false,
    manchesterOk: false,
    keysMatch: false,
    missing: [],
  };
  try {
    out.known = Object.keys(CITY_DATA);
    out.londonOk = typeof cityOf('london').boroughData() === 'object';
    out.nycOk = typeof cityOf('nyc').boroughData() === 'object';
    out.manchesterOk = typeof cityOf('manchester').boroughData() === 'object';

    // Every city must declare the SAME keys. Added 2026-08-09 with the prose
    // fields (healthSource, searchNotFound, noiseAuthority and the rest), which
    // replaced inline `currentCity === 'nyc' ? ... : ...` ternaries.
    //
    // The ternaries at least forced both branches to exist. A registry does
    // not: adding a field to london and forgetting nyc yields `undefined`,
    // which renders as the literal string "undefined" in a template rather
    // than throwing. This is the coverage assertion for the registry - it
    // fails on the field that was forgotten, not on the city that was.
    const union = new Set(out.known.flatMap((c) => Object.keys(CITY_DATA[c])));
    for (const city of out.known) {
      for (const key of union) {
        if (CITY_DATA[city][key] === undefined) out.missing.push(`${city}.${key}`);
      }
    }
    out.keysMatch = out.missing.length === 0;
  } catch {
    // Reported through the flags above rather than thrown, so a broken
    // registry fails this test instead of aborting the whole run.
  }
  // A city that will never exist. This probe used 'manchester', which was a
  // fine choice for one day and then became a real city on 2026-08-09 - at
  // which point the assertion started failing for the best possible reason and
  // would have been "fixed" by deleting it. A placeholder that names a PLANNED
  // thing is a scheduled false alarm; name something impossible instead.
  try {
    cityOf('__no_such_city__');
  } catch {
    out.throwsOnUnknown = true;
  }
  return out;
});

console.log('');
console.log('--- city registry ---');
console.log('registered cities:        ', registry.known.join(', '));
console.log('london resolves:          ', registry.londonOk);
console.log('nyc resolves:             ', registry.nycOk);
console.log('manchester resolves:      ', registry.manchesterOk);
console.log('unknown city throws:      ', registry.throwsOnUnknown, '(must be true)');
console.log('every city declares same keys:', registry.keysMatch);
if (registry.missing.length) console.log('  MISSING:', registry.missing.join(', '));

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
  !nycAskedGithub &&
  manBoroughCount === 10 &&
  manNamesOk &&
  manAskedLocalGeo &&
  !manAskedGithub &&
  registry.londonOk &&
  registry.nycOk &&
  registry.manchesterOk &&
  registry.throwsOnUnknown &&
  registry.keysMatch;

console.log('\nRESULT:', ok ? 'PASS' : 'FAIL');
process.exit(ok ? 0 : 1);
