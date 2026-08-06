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
const fixture = readFileSync(join(HERE, 'fixtures', 'rightmove-real-sw5.html'), 'utf8');

// Collingham Road SW5, from the real saved listing the fixture carries.
const LAT = '51.4942';

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

// THE REGRESSION ASSERTION. A fast section must paint without waiting for the
// slow one. The panel used to Promise.all over every endpoint, so a slow or
// dead Overpass — its normal state often enough to matter — held everything
// else hostage for up to 30 seconds.
//
// Anchored on Environment now that Transport is gone. Transport was dropped on
// 2026-08-06: Rightmove already prints nearest stations with distances on every
// listing, so that section duplicated the page it sat on.
await page
  .locator('#cubitt33-panel .c33-section', { hasText: /environment/i })
  .locator('.c33-name, .c33-caveat')
  .first()
  .waitFor({ timeout: 20000 });
const firstPaintMs = Date.now() - clickedAt;

check('environment paints without waiting for /nhs', firstPaintMs < 12000, `${firstPaintMs} ms`);

check(
  'transport section is gone',
  (await page
    .locator('#cubitt33-panel .c33-section h3')
    .filter({ hasText: /^\s*transport\s*$/i })
    .count()) === 0
);

// Let /nhs settle so attribution and the debug line land.
await page.locator('#cubitt33-panel .c33-foot').waitFor({ timeout: 45000 });
const text = await page.locator('#cubitt33-panel').innerText();

check('address echoed back', text.includes('Collingham Road'));
check('healthcare section present', /HEALTHCARE/i.test(text));

// NOT just "the section rendered". On 2026-08-06 this suite passed 24/24 while
// /nhs was falling back to nhs.uk links on every single request — the section
// was present, the panel looked fine, and the check could not tell the
// difference between real data and a graceful failure. A named facility with a
// distance is what "healthcare works" actually means.
check(
  'healthcare returns real facilities, not fallback links',
  /\d+\s*m\b/.test(text) && !/Search NHS .* on nhs\.uk/i.test(text),
  text.includes('nhs.uk') ? 'fallback links present' : ''
);
check('no stale Loading text', !text.includes('Loading'));
check('OSM/ODbL attribution', /OpenStreetMap/i.test(text));
check('debug reports rightmove-page-model', text.includes('rightmove-page-model'));
check('debug reports outcode', text.includes('SW5'));
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
check('cached view still renders sections', /ENVIRONMENT/i.test(text2));

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

// Assert the SPECIFIC caveat, not a count. This counted `.c33-caveat === 1`
// until the Environment section began rendering its own coverage notices with
// the same class, at which point a passing count became an accident of how many
// unrelated caveats happened to be on screen. Matching the text keeps the
// assertion tied to the thing it was written for: transport being suppressed
// outside TfL's coverage.
check(
  'non-London: coverage caveat shown',
  (await page
    .locator('#cubitt33-panel .c33-caveat')
    .filter({ hasText: /coverage is strongest in London/i })
    .count()) === 1
);

// EPC and sold prices are postcode-keyed, so they only appear once
// /v1/environment has reverse-geocoded one. Outside London that still works —
// the postcode resolves, the data may simply be sparse — so the sections must
// be PRESENT rather than suppressed.
const mcrSections = await page.locator('#cubitt33-panel .c33-section h3').allInnerTexts();
check('non-London: EPC section still attempted', mcrSections.some((h) => /EPC/i.test(h)), mcrSections.join(','));
check('non-London: healthcare still shown', /HEALTHCARE/i.test(mcr));
check('non-London: outcode parsed', mcr.includes('M1'));

// A postcode DEFRA actually measured. The SW5 fixture above exercises only the
// "nothing measured, here is why" path; without this the Environment section
// could stop rendering values entirely and the suite would stay green.
const heathrow = readFileSync(join(HERE, 'fixtures', 'rightmove-heathrow.html'), 'utf8');
await page.locator('#cubitt33-panel .c33-close').click();
await page.unroute('**://www.rightmove.co.uk/**');
await page.route('**://www.rightmove.co.uk/**', (route) =>
  route.fulfill({ status: 200, contentType: 'text/html', body: heathrow })
);
await page.goto('https://www.rightmove.co.uk/properties/555000333');
await page.locator('#cubitt33-badge').waitFor({ timeout: 15000 });
await page.locator('#cubitt33-badge').click();
await page.locator('#cubitt33-panel .c33-foot').waitFor({ timeout: 45000 });
const lhr = await page.locator('#cubitt33-panel').innerText();

const aircraftRow = (lhr.split('\n').find((l) => /Aircraft noise/i.test(l)) || '').trim();
check(
  'measured postcode shows an aircraft dB figure',
  /Aircraft noise/i.test(lhr) && /58\.2 dB Lden/.test(lhr),
  aircraftRow || 'no aircraft row'
);
check('measured postcode carries no "not measured" notice', !/not measured/i.test(lhr));

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
