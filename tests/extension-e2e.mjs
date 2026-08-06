// End-to-end test for the browser extension, in a real Chromium with the
// extension actually loaded.
//
// WHAT MAKES THIS POSSIBLE WITHOUT TOUCHING RIGHTMOVE. The fixture is served
// AT the rightmove.co.uk URL via request interception, so the content script's
// match pattern fires and the extension behaves exactly as it would in the
// wild — but no request ever leaves for rightmove.co.uk. Their terms prohibit
// automated access, and the extension's whole defensible posture is that it
// reads the DOM in a user's own browser. A test suite that scraped them to
// prove that would be arguing against itself.
//
// It DOES call the live /transport and /nhs endpoints, deliberately: those are
// ours, the two calls cost about $0.00002, and mocking them would leave the
// integration between panel and API untested — which is the half most likely
// to break.
//
// HEADLESS DOES NOT WORK HERE. Playwright's headless mode uses
// chromium_headless_shell, which does not support extensions at all: no service
// worker starts and no content script runs, so every assertion fails for a
// reason unrelated to the code. Verified both ways. --headless=new does support
// extensions, so it is passed as an arg with headless:false.
//
//   node tests/extension-e2e.mjs

import { chromium } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { readFileSync } from 'node:fs';

const HERE = dirname(fileURLToPath(import.meta.url));
const EXT = join(HERE, '..', 'extension');
const fixture = readFileSync(join(HERE, 'fixtures', 'rightmove-listing.html'), 'utf8');

// Battersea, matching the fixture's PAGE_MODEL.
const LAT = '51.4713';

const results = [];
const check = (name, ok, detail = '') => results.push([name, ok, detail]);

// Empty path = a fresh throwaway profile per run. A reused profile carries
// extension state between runs, which makes failures depend on what the last
// run left behind — and the cache assertions below would pass against a
// six-hour-old entry rather than the one this run created.
const ctx = await chromium.launchPersistentContext(
  '',
  {
    headless: false,
    args: [
      '--headless=new',
      `--disable-extensions-except=${EXT}`,
      `--load-extension=${EXT}`,
    ],
  }
);

const page = await ctx.newPage();
await page.route('**://www.rightmove.co.uk/**', (route) =>
  route.fulfill({ status: 200, contentType: 'text/html', body: fixture })
);

const pageErrors = [];
page.on('pageerror', (e) => pageErrors.push(e.message));

await page.goto('https://www.rightmove.co.uk/properties/123456789');
await page.locator('#cubitt33-badge').waitFor({ timeout: 15000 });

check('badge injected', true);
check('no panel before badge click', (await page.locator('#cubitt33-panel').count()) === 0);
check('service worker running', ctx.serviceWorkers().length === 1);

const clickedAt = Date.now();
await page.locator('#cubitt33-badge').click();

check('panel appears on click', (await page.locator('#cubitt33-panel').count()) === 1);
check('badge removed when panel opens', (await page.locator('#cubitt33-badge').count()) === 0);

// THE REGRESSION ASSERTION. Transport must paint without waiting for /nhs.
// Before the incremental-render fix the panel did Promise.all over both, so a
// slow or dead Overpass — which is its normal state often enough to matter —
// held TfL's answer hostage for up to 30 seconds.
await page
  .locator('#cubitt33-panel .c33-section', { hasText: /transport/i })
  .locator('.c33-name')
  .first()
  .waitFor({ timeout: 20000 });
const transportMs = Date.now() - clickedAt;

check('transport paints without waiting for /nhs', transportMs < 12000, `${transportMs} ms`);

const stationCount = await page
  .locator('#cubitt33-panel .c33-section', { hasText: /transport/i })
  .locator('.c33-item')
  .count();
check('real stations returned', stationCount > 0, `${stationCount} stations`);

// Let /nhs settle so attribution and the debug line land.
await page.locator('#cubitt33-panel .c33-foot').waitFor({ timeout: 45000 });
const text = await page.locator('#cubitt33-panel').innerText();

check('address echoed back', text.includes('Battersea Park Road'));
check('healthcare section present', /HEALTHCARE/i.test(text));
check('no stale Loading text', !text.includes('Loading'));
check('TfL attribution', /TfL Open Data/i.test(text));
check('OSM/ODbL attribution', /OpenStreetMap/i.test(text));
check('debug reports page-model', text.includes('page-model'));
check('debug reports outcode', text.includes('SW11'));
check('debug reports coordinates', text.includes(LAT));
check('no uncaught page errors', pageErrors.length === 0, pageErrors.join('; '));

// Second listing at the same coordinates must hit the rounded-coordinate cache.
await page.locator('#cubitt33-panel .c33-close').click();
await page.goto('https://www.rightmove.co.uk/properties/987654321');
await page.locator('#cubitt33-badge').waitFor({ timeout: 15000 });
const cacheClick = Date.now();
await page.locator('#cubitt33-badge').click();
await page.locator('#cubitt33-panel .c33-foot').waitFor({ timeout: 45000 });
const cachedMs = Date.now() - cacheClick;
const text2 = await page.locator('#cubitt33-panel').innerText();

check('second view served from cache', text2.includes('cached'), `${cachedMs} ms`);
check('cached view still renders stations', /TRANSPORT/i.test(text2));

// --- Degraded paths -------------------------------------------------------
//
// decidePresentation() is the honesty gate: it decides what the panel is
// ALLOWED to show at a given precision, and until now it had never run in a
// browser. Both cases below are ones where showing the obvious thing would
// state more than we know.

// Outside Greater London, TfL has no coverage, so /transport returns zero
// stations. Rendering that as "no stations nearby" would assert an absence of
// TRANSPORT while only knowing an absence of DATA.
const manchester = readFileSync(join(HERE, 'fixtures', 'rightmove-manchester.html'), 'utf8');
await page.locator('#cubitt33-panel .c33-close').click();
await page.unroute('**://www.rightmove.co.uk/**');
await page.route('**://www.rightmove.co.uk/**', (route) =>
  route.fulfill({ status: 200, contentType: 'text/html', body: manchester })
);
await page.goto('https://www.rightmove.co.uk/properties/555000111');
await page.locator('#cubitt33-badge').waitFor({ timeout: 15000 });
await page.locator('#cubitt33-badge').click();
await page.locator('#cubitt33-panel .c33-foot').waitFor({ timeout: 45000 });
const mcr = await page.locator('#cubitt33-panel').innerText();

check('non-London: caveat shown', (await page.locator('#cubitt33-panel .c33-caveat').count()) === 1);

// Assert on STRUCTURE, not free text. A /transport/i match over innerText also
// hits the caveat ("Transport data covers Greater London only...") and the TfL
// attribution line, so the loose version failed while the code was correct.
// Counting section headings is what "the section is absent" actually means.
const transportHeadings = await page
  .locator('#cubitt33-panel .c33-section h3')
  .filter({ hasText: /^\s*transport\s*$/i })
  .count();
check('non-London: transport section suppressed', transportHeadings === 0, `${transportHeadings} headings`);
check('non-London: healthcare still shown', /HEALTHCARE/i.test(mcr));
check('non-London: outcode parsed', mcr.includes('M1'));

// No coordinates anywhere. The panel must render NOTHING — not an empty card,
// not a "couldn't find anything" message. An inert badge is a promise we then
// break, and an empty panel invites the reader to conclude the area has no GPs
// and no stations.
const noCoords = readFileSync(join(HERE, 'fixtures', 'rightmove-no-coords.html'), 'utf8');
await page.unroute('**://www.rightmove.co.uk/**');
await page.route('**://www.rightmove.co.uk/**', (route) =>
  route.fulfill({ status: 200, contentType: 'text/html', body: noCoords })
);
await page.goto('https://www.rightmove.co.uk/properties/555000222');
await page.waitForTimeout(3000);

check('unlocatable: no badge rendered', (await page.locator('#cubitt33-badge').count()) === 0);
check('unlocatable: no panel rendered', (await page.locator('#cubitt33-panel').count()) === 0);

console.log('\n--- panel (non-London) ---');
console.log(mcr.split('\n').filter(Boolean).slice(0, 10).map((l) => '  ' + l).join('\n'));

console.log('\n--- panel (first view) ---');
console.log(
  text.split('\n').filter(Boolean).map((l) => '  ' + l).join('\n')
);

console.log('\n--- results ---');
let failed = 0;
for (const [name, ok, detail] of results) {
  if (!ok) failed += 1;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `   [${detail}]` : ''}`);
}
console.log(
  failed === 0 ? `\nAll ${results.length} checks passed.` : `\n${failed} of ${results.length} FAILED.`
);

await ctx.close();
process.exit(failed === 0 ? 0 : 1);
