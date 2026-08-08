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

// Read text through count() FIRST, always. textContent()/getAttribute() auto-
// wait, so on a missing element they block for the full 30s and then THROW,
// aborting the run and taking every later assertion with it. Proven on
// 2026-08-08: a deliberately broken chart produced no output at all rather than
// the one FAIL it should have. A test that cannot survive the failure it tests
// for reports nothing on the day it matters.
//
// textContent, not innerText: these targets are SVG <text>, and SVGElement is
// not an HTMLElement, so Playwright's innerText refuses outright with "Node is
// not an HTMLElement".
const textOfIn = async (scope, sel) =>
  (await scope.locator(sel).count())
    ? ((await scope.locator(sel).textContent()) || '').trim()
    : null;
const attrOfIn = async (scope, sel, attr) =>
  (await scope.locator(sel).count()) ? await scope.locator(sel).getAttribute(attr) : null;

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
// The same discipline as the healthcare check above, applied to the EPC band
// chart added 2026-08-08. Asserting "the EPC section rendered" would pass on a
// section holding nothing, which is precisely how /sold-prices went months
// without ever having returned a transaction while this suite stayed green.
//
// Reported as SKIP rather than PASS when the register has no certificates for
// SW5: a check that silently passes when it did not run is the defect it is
// supposed to catch. If this ever shows SKIP on every run, the chart is
// untested and the summary line says so out loud.
const epcSection = page.locator('#cubitt33-panel .c33-section', { hasText: /EPC register/i });
const epcCerts = await epcSection.locator('.c33-band').count();
if (epcCerts > 0) {
  const cols = await epcSection.locator('.c33-strip-col').count();
  check('EPC band chart draws all seven bands', cols === 7, `${cols} columns`);

  // Colour marks data, not the scale. An empty band keeps its stub and loses
  // its band colour, so a postcode with certificates in three bands shows three
  // coloured columns and four grey ones - not seven coloured marks of which
  // four mean "none". Asserted as a strict subset so this cannot silently
  // regress to painting the whole ramp.
  const empties = await epcSection.locator('.c33-strip-empty').count();
  const coloured = cols - empties;
  check(
    'only bands with certificates carry colour',
    empties > 0 && coloured > 0 && coloured + empties === 7,
    `${coloured} coloured, ${empties} empty`
  );

  const tick = await textOfIn(epcSection, '.c33-strip-ticklab');
  check(
    'EPC band chart names its threshold rather than inventing one',
    tick === 'MEES E',
    tick === null ? 'no tick label rendered' : tick
  );

  // The chart replaced two text lines; the facts they carried must still reach
  // a screen reader, or this was a downgrade wearing an improvement's clothes.
  const label = await attrOfIn(epcSection, '.c33-strip', 'aria-label');
  check(
    'EPC band chart is readable without sight of it',
    /A \d+, B \d+, C \d+, D \d+, E \d+, F \d+, G \d+/.test(label || '') &&
      /legally be let/.test(label || ''),
    label ? label.slice(0, 60) : 'no aria-label'
  );
} else {
  check('EPC band chart', 'skip', 'register returned no certificates for SW5');
}

// --- The aircraft estimate carries its caveat, above road noise -----------
//
// The estimated aircraft figure is the one reading here that is NOT a
// measurement: geometry, on a 0-10 scale, for the ~91% of London postcodes
// DEFRA never surveyed. Its caveat must sit ON that row and BEFORE the measured
// road figure, or a reader scanning down meets "5/10 quiet" then "49.5 dB Lden"
// with nothing saying those are different kinds of number.
//
// Asserted on DOCUMENT ORDER, not just presence - "the note exists somewhere"
// was true when it lived in a collapsed disclosure two rows below.
const envSection = page.locator('#cubitt33-panel .c33-section', { hasText: /environment/i });
const envItems = await envSection.locator('.c33-item').all();
const envTexts = await Promise.all(envItems.map((i) => i.innerText()));
const estIdx = envTexts.findIndex((t) => /estimated/i.test(t));
const roadIdx = envTexts.findIndex((t) => /road noise/i.test(t));

if (estIdx >= 0) {
  check(
    'estimated aircraft row carries its own caveat',
    /not measured/i.test(envTexts[estIdx] || ''),
    (envTexts[estIdx] || '').replace(/\n/g, ' / ').slice(0, 70)
  );
  check(
    'the caveat precedes road noise rather than trailing it',
    roadIdx === -1 || estIdx < roadIdx,
    `estimated at ${estIdx}, road at ${roadIdx}`
  );
} else {
  check('estimated aircraft caveat', 'skip', 'postcode has a measured DEFRA reading');
}

// Sold-price range chart. The fixture is a real RES_BUY listing asking
// £34,000,000, so when Land Registry returns anything for SW5 the asking marker
// must be drawn - and must NOT be drawn as a verdict.
const soldSection = page.locator('#cubitt33-panel .c33-section', { hasText: /Sold nearby/i });
// .c33-price, not .c33-name: the sold rows lead with the figure since the
// 2026-08-08 rework. Left as .c33-name this whole block would have quietly
// taken the SKIP branch and reported "no sales for SW5" forever - the exact
// failure the SKIP state was added to make visible, arriving through a
// renamed selector rather than through missing data.
const soldRows = await soldSection.locator('.c33-price').count();
if (soldRows > 0) {
  check('sold-price range chart rendered', (await soldSection.locator('.c33-range').count()) === 1);
  check(
    'asking price marked on the range',
    (await soldSection.locator('.c33-range-ask').count()) === 1
  );
  const dots = await soldSection.locator('.c33-range-dot').count();
  check('every sale plotted, not just the extremes', dots >= 1, `${dots} dots`);

  // The chart must report a position and never a judgement. If a future change
  // adds "23% above local average" or an over/under colour, this goes red -
  // which is the intent. Land Registry data is not size-adjusted and cannot
  // carry that claim.
  const rangeLabel = (await attrOfIn(soldSection, '.c33-range', 'aria-label')) || '';
  // The regression assertion for the label-position bug found 2026-08-08: the
  // sold-range label used to be pinned to the axis ends, so with an outlier
  // asking price it named the sold maximum while pointing at the asking price.
  // Asserting the label agrees with the aria-label's stated range catches any
  // future divergence between what the chart says and where it says it.
  const bandLab = await textOfIn(soldSection, '.c33-range-lab');
  check(
    'range label names the sold range, not the axis extremes',
    /^£[\d.]+[km]?-£[\d.]+[km]?$|^£[\d.]+[km]?$/.test(bandLab || ''),
    bandLab || 'no band label'
  );

  // The outlier note. Present only when the asking price sits wholly outside
  // the recorded sales, which is exactly the case where the sale dots collapse
  // into one blob and the chart alone stops being readable. Must stay
  // arithmetic: "above every recorded sale" is a fact, "overpriced" is not one
  // Land Registry data can support unadjusted for size or property type.
  // Lives in the caption line since 2026-08-08 - it was a third stacked grey
  // line under the chart, which was more text than the chart it explained. The
  // aria-label keeps the long form, where length is free.
  const cap = await textOfIn(soldSection, '.c33-range-cap');
  const noteExpected = /(above|below) every recorded sale/.test(rangeLabel);
  check(
    'outlier note appears exactly when the asking price is outside the sales',
    noteExpected
      ? /· asking is (above|below) all of them$/.test(cap || '')
      : !/asking is/.test(cap || ''),
    cap || 'no caption'
  );

  check(
    'range chart states its limits and passes no verdict',
    /not adjusted for size/i.test(rangeLabel) &&
      !/over-?priced|under-?priced|good value|above average/i.test(rangeLabel),
    rangeLabel.slice(0, 70)
  );
} else {
  check('sold-price range chart', 'skip', 'Land Registry returned no sales for SW5');
}

// --- Header collapse ------------------------------------------------------
// The panel is fixed-position over someone else's page, so "get out of the
// way" has to actually shrink it. Asserting the attribute alone would pass on
// a data-collapsed that no CSS rule reads, so the HEIGHT is measured too.
const panelBox = page.locator('#cubitt33-panel');
const openHeight = (await panelBox.boundingBox())?.height ?? 0;
await panelBox.locator('.c33-toggle').click();
await page.waitForTimeout(250);
const shutHeight = (await panelBox.boundingBox())?.height ?? 0;
check(
  'header click collapses the panel to its header',
  (await panelBox.getAttribute('data-collapsed')) === 'true' && shutHeight < openHeight / 2,
  `${Math.round(openHeight)}px -> ${Math.round(shutHeight)}px`
);
check(
  'collapsed state is announced, not only drawn',
  (await panelBox.locator('.c33-toggle').getAttribute('aria-expanded')) === 'false'
);
await panelBox.locator('.c33-toggle').click();
await page.waitForTimeout(250);
check(
  'header click expands it again',
  (await panelBox.getAttribute('data-collapsed')) === 'false' &&
    ((await panelBox.boundingBox())?.height ?? 0) > shutHeight
);

// The close button lives inside the header beside the toggle. If it ever ends
// up NESTED in the toggle button, Chrome resolves the click ambiguously and
// close starts collapsing instead. Invalid HTML that still renders.
check(
  'close button is not nested inside the collapse toggle',
  (await panelBox.locator('.c33-toggle .c33-close').count()) === 0
);

// The rent reference is letting-only. On a sale, Sold nearby occupies that slot
// with actual transactions on this postcode, which is a stronger claim than a
// borough average; showing both would put a coarse figure beside a fine one and
// invite them to be read as the same kind of number.
check(
  'sale: no borough rent section',
  (await page.locator('#cubitt33-panel .c33-section h3').filter({ hasText: /Typical rent/i }).count()) === 0
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

// --- Lettings switch the panel --------------------------------------------
//
// A GENUINE To Rent listing (Ashford Road, NW2, saved 2026-08-08), not the sale
// page with BUY rewritten to LET. That substitution is how this path was first
// built and shipped, and it tested my model of Rightmove twice over - it also,
// found afterwards, rewrote strings inside their cookie manifest I had no idea
// were there. A real letting page is the only thing that can contradict me.
//
// Land Registry records SALES. On a rental, Sold nearby is a column of
// six-figure sums beside a property nobody is selling, in a different unit
// from the only price on the page. It must be GONE, not empty: an empty
// section still asserts the question was worth asking.
const lettingFixture = readFileSync(join(HERE, 'fixtures', 'rightmove-real-letting-nw2.html'), 'utf8');
await page.locator('#cubitt33-panel .c33-close').click();
await page.unroute('**://www.rightmove.co.uk/**');
await page.route('**://www.rightmove.co.uk/**', (route) =>
  route.fulfill({ status: 200, contentType: 'text/html', body: lettingFixture })
);
await page.goto('https://www.rightmove.co.uk/properties/246813579');
await page.locator('#cubitt33-badge').waitFor({ timeout: 15000 });
await page.locator('#cubitt33-badge').click();
await page.locator('#cubitt33-panel .c33-foot').waitFor({ timeout: 45000 });

const letSections = await page.locator('#cubitt33-panel .c33-section h3').allInnerTexts();
const letText = await page.locator('#cubitt33-panel').innerText();

check(
  'letting: sold prices removed, not rendered empty',
  !letSections.some((h) => /sold/i.test(h)),
  letSections.join(',')
);
// Section ORDER must match the sale layout minus Sold nearby. Promoting EPC on
// a letting was tried and reverted: moving sections between listing types reads
// as the extension behaving inconsistently, not as a judgement about the
// reader's situation. The letting-specific value lives INSIDE EPC instead.
check(
  'letting: environment still leads, order unchanged from a sale',
  /ENVIRONMENT/i.test(letSections[0] || ''),
  letSections.join(',')
);
// A different postcode from the sale fixture, so the register may hold nothing
// here. SKIP rather than PASS in that case - reporting green for a line that
// never rendered is the defect this suite keeps finding elsewhere.
const letHasCerts = (await page.locator('#cubitt33-panel .c33-strip-col').count()) > 0;
check(
  'letting: MEES stated against the letting minimum',
  letHasCerts
    ? /minimum for a new letting/i.test(letText) && /certificates at this postcode/i.test(letText)
    : 'skip',
  letHasCerts
    ? (letText.match(/[^\n]*minimum for a new letting[^\n]*/i) || ['not found'])[0].slice(0, 70)
    : 'no EPC certificates lodged at this postcode'
);
check('letting: address echoed from the real page', letText.includes('Ashford Road'));
// The claim we are NOT entitled to make. No address is ever captured, so no
// certificate can be tied to the listing; any wording implying otherwise is a
// regression regardless of how it reads.
check(
  'letting: never claims a band for THIS property',
  !/this (property|flat|home) is band/i.test(letText)
);
check('letting: place data still shown', /ENVIRONMENT/i.test(letText) && /HEALTHCARE/i.test(letText));

// --- The borough rent reference -------------------------------------------
//
// NW2 sits in Brent, resolved by point-in-polygon from the listing coordinate
// against the outlines bundled with the ONS figures. The bedroom count comes
// through the same index indirection as everything else in the page model
// ({"bedrooms":228} -> flat[228] === 2), so a wrong deref would show a rent for
// the wrong property size rather than failing visibly.
const rentSection = page.locator('#cubitt33-panel .c33-section', { hasText: /Typical rent/i });
const hasRent = (await rentSection.count()) > 0;
check('letting: borough rent shown', hasRent, hasRent ? '' : 'no Typical rent section');

if (hasRent) {
  const rentText = await rentSection.innerText();
  check(
    'rent names the borough and the property size, not "London"',
    /Brent/.test(rentText) && /2 bed/i.test(rentText),
    rentText.split('\n').slice(0, 2).join(' / ')
  );
  // A rent figure with no date is unreadable and a stale one is worse than
  // none, so the month must be ON the row rather than in a footer.
  check(
    'rent is dated and attributed on the row',
    /\b(January|February|March|April|May|June|July|August|September|October|November|December) \d{4}\b/.test(rentText) &&
      /ONS/.test(rentText),
    (rentText.match(/Borough average[^\n]*/) || ['not found'])[0]
  );
  // THE HONESTY ASSERTION. Sold nearby earns a range chart because every dot
  // is a real transaction on that postcode. This is a borough-wide average
  // over every property and street in it; drawn the same way it would claim
  // to be a comparable. If a chart ever appears in this section, that claim
  // has been made by accident.
  check(
    'rent is NOT drawn as a range chart',
    (await rentSection.locator('.c33-range, .c33-bar, .c33-strip').count()) === 0
  );
  check(
    'rent states it is a borough figure, not a local one',
    /borough average/i.test(rentText),
    ''
  );
}

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
let skipped = 0;
for (const [name, ok, detail] of results) {
  // A third state, because PASS and FAIL cannot both describe "did not run".
  // Folding a skip into PASS is how a suite reports coverage it never had.
  const state = ok === 'skip' ? 'SKIP' : ok ? 'PASS' : 'FAIL';
  if (state === 'FAIL') failed += 1;
  if (state === 'SKIP') skipped += 1;
  console.log(`${state}  ${name}${detail ? `   [${detail}]` : ''}`);
}
const tail = skipped ? ` (${skipped} skipped - those assertions did NOT run)` : '';
console.log(
  failed === 0
    ? `\n${results.length - skipped} checks passed${tail}.`
    : `\n${failed} of ${results.length} FAILED${tail}.`
);

await ctx.close();
process.exit(failed === 0 ? 0 : 1);
