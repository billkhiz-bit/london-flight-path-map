/**
 * Run an area search in a NON-LONDON UK city and assert it gets UK content.
 *
 * Why this exists
 * ---------------
 * `updateSidebarPostcode()` branched `currentCity === 'london' ? … : …` and the
 * ELSE-BRANCH WAS NEW YORK'S. So an area search in Manchester, Birmingham,
 * Leeds, Sheffield, Liverpool, Newcastle, Bristol, Leicester or Teesside
 * answered:
 *
 *     NEAREST SUBWAY STATIONS
 *     NYC subway data coming soon. Check MTA.info for schedules.
 *
 * A heading naming one city over a page showing another. Those nine also lost
 * EPC and sold prices, under a comment reading "London only - these APIs are
 * UK-specific", which is the reverse of true: EPC and HM Land Registry are
 * UK-wide. And because the sold-prices CONTAINER is emitted by
 * buildPropertyLinks() for every UK city while the FETCH was London-gated, all
 * nine sat on "Loading from Land Registry..." that could never resolve.
 *
 * The 1,771 NaPTAN stations built on 2026-08-12 to fix exactly this were
 * unreachable: nearestStations() had one call site, inside renderTransportData(),
 * which was only ever called from the London branch. The data shipped, the
 * renderer shipped, nothing joined them.
 *
 * Why NOTHING caught it
 * ---------------------
 * The audit of 2026-08-21 put it plainly: no gate had ever exercised the
 * non-London area-search path. `borough-score-parity` compares boroughs by
 * SCORE, `city-switch` clicks the chip and checks the MAP. Both pass with this
 * panel showing another continent's transit system, because neither one ever
 * types a postcode.
 *
 * What it asserts, and why each one
 * ---------------------------------
 *   - no New York text in a UK city      the defect itself, stated directly
 *   - stations render with real NAMES    "the section exists" is satisfied by a
 *                                        spinner; only a name proves NaPTAN was
 *                                        reached. Assert on DATA, not shape -
 *                                        the /transport lesson from the same day
 *   - nothing is still "Loading..."      an unresolved spinner is the same lie
 *                                        as a confident empty list, just slower
 *   - London is UNCHANGED                the fix must not cost London its live
 *                                        TfL panel
 *   - NYC still gets its own copy        the NYC message was never wrong FOR
 *                                        NYC; NaPTAN is UK-only and NYC_STATIONS
 *                                        is legitimately empty
 *
 * Driven off CITY_DATA's `country`, not a hardcoded city list - a list is one
 * more place to forget, and forgetting is what shipped this.
 *
 *   node tests/uk-city-panel.mjs
 *   node tests/uk-city-panel.mjs https://skyscore.co.uk/   (verify a deploy)
 */
import { chromium } from '@playwright/test';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';

const ROOT = process.cwd();
// 8123, 8921, 8922, 8923 and 8924 are taken by the other harnesses and preflight
// runs these in one block; a shared port dies with EADDRINUSE, which reads as a
// panel failure and is not one.
const PORT = 8925;
const TYPES = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  // A module served as anything else is refused by the browser. Missing until the full map
  // started importing js/flight_geometry.mjs for its plane altitude (A1, 2026-10-07): the
  // import failed here, the row stayed "N/A", and the site itself (served .mjs as
  // application/javascript by web-deploy) was fine.
  '.mjs': 'text/javascript',
  '.json': 'application/json',
  '.css': 'text/css',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.woff2': 'font/woff2',
  '.webmanifest': 'application/manifest+json',
};

const TARGET = process.argv[2] || null;

const server = createServer(async (req, res) => {
  const raw = decodeURIComponent(req.url.split('?')[0]);
  const p = join(ROOT, normalize(raw === '/' ? '/index.html' : raw));
  if (!p.startsWith(ROOT)) return res.writeHead(403).end();
  try {
    const body = await readFile(p);
    res.writeHead(200, { 'content-type': TYPES[extname(p)] || 'application/octet-stream' });
    res.end(body);
  } catch {
    res.writeHead(404).end();
  }
});
if (!TARGET) await new Promise((r) => server.listen(PORT, r));
const url = TARGET || `http://localhost:${PORT}/index.html`;

// One real postcode per city under test. Real because the panel resolves them
// through postcodes.io, and an invented postcode fails for a reason that has
// nothing to do with what is being tested.
// TAKEN FROM scripts/check_score_sanity.py, which probes one postcode per city
// against the live API on every preflight - so these are known to resolve and
// known to belong to the city claimed. Inventing plausible ones instead cost a
// run here: `B1 1AA` and `LS1 1AA` look like Birmingham and Leeds city centre
// and postcodes.io 404s both, which failed this file for a reason that had
// nothing to do with the panel it tests.
const CASES = [
  { city: 'manchester', postcode: 'M1 1AE', uk: true },
  { city: 'westmidlands', postcode: 'B15 2TT', uk: true },
  { city: 'westyorkshire', postcode: 'LS1 4DY', uk: true },
  { city: 'london', postcode: 'SW11 1AA', uk: true, london: true },
  { city: 'nyc', postcode: '10001', uk: false },
];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));

await page.goto(url, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(3000);

// WARM THE /transport LAMBDA BEFORE THE LONDON CASE RUNS (2026-09-18).
//
// The London row asserts "stations have real names" against LIVE TfL data,
// and the page gives that fetch PANEL_TIMEOUT_MS = 8000. A cold /transport
// invocation measured 4.2 s before TfL was even asked, and the fetch-site
// comment in index.html records production samples of 7.6 s and 10.8 s - so
// on a cold Lambda the panel legitimately renders "temporarily unavailable"
// and this gate went red on a tree that had not touched transport at all.
// One throwaway call here takes the cold start out of the page's budget; a
// stub would take the live path out of the gate, which is the thing worth
// keeping. If TfL itself is slow this can still red, and that is a real
// signal, not a flaky one: the page would show the same to a user.
const API = await page.evaluate(() => window.API_BASE || null);
if (API) {
  try {
    await fetch(`${API}/transport?lat=51.4613&lon=-0.1673`, { signal: AbortSignal.timeout(20000) });
  } catch {
    // A failure here is reported by the London case below, with the panel text.
  }
}

const failures = [];
function check(name, pass, detail) {
  console.log(`  ${pass ? 'PASS' : 'FAIL'}  ${name}${detail ? '  ' + detail : ''}`);
  if (!pass) failures.push(`${name}: ${detail}`);
}

console.log('\nNon-London area-search panel\n============================\n');

// AIR MEASURED NEARBY (2026-10-19): the panel names the nearest Breathe London sensor and the
// nearest official monitor within 5 km, from the front page's functions. The expected names are
// worked out HERE, from postcodes.io's position and the two data files with this test's own
// distance maths, so the shared functions cannot pass by agreeing with themselves. SW11 1AA has
// both (London shows both: Bill, 2026-10-19); M1 1AE, B15 2TT and LS1 4DY a monitor and no sensor.
const AIR_SENSORS = JSON.parse(await readFile(join(ROOT, 'data', 'breathe-london-sensors.json'), 'utf8'));
const AIR_MONITORS = JSON.parse(await readFile(join(ROOT, 'data', 'aurn-sites.json'), 'utf8'));
const kmBetween = (lat1, lon1, lat2, lon2) => {
  const r = Math.PI / 180, dLat = (lat2 - lat1) * r, dLon = (lon2 - lon1) * r;
  return 2 * 6371.0088 * Math.asin(Math.sqrt(Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(dLon / 2) ** 2));
};
const nearestWithin5 = (sites, lat, lon) => {
  const best = sites.reduce((a, s) => (kmBetween(lat, lon, s.lat, s.lon) < kmBetween(lat, lon, a.lat, a.lon) ? s : a));
  return kmBetween(lat, lon, best.lat, best.lon) <= 5 ? best : null;
};
async function expectedAir(postcode) {
  const resp = await fetch(`https://api.postcodes.io/postcodes/${encodeURIComponent(postcode)}`, { signal: AbortSignal.timeout(20000) });
  const { result } = await resp.json();
  return {
    sensor: nearestWithin5(AIR_SENSORS.sites, result.latitude, result.longitude),
    monitor: nearestWithin5(AIR_MONITORS.sites, result.latitude, result.longitude),
  };
}

for (const c of CASES) {
  await page.evaluate((city) => window.switchCity(city), c.city);
  await page.waitForTimeout(1200);
  await page.fill('#search-input', c.postcode);
  await page.press('#search-input', 'Enter');

  // WAIT FOR THE STATE, NOT THE CLOCK (2026-09-08).
  //
  // This was `waitForTimeout(6000)`, under a comment reading "6s is what the
  // slowest of those needs from a cold container". Measured the day it was
  // changed: ONE leg, /transport, took 6.16s by itself - it makes TWO TfL
  // calls, unregistered, behind a cold Lambda. So the clock had drifted under
  // the real latency and this stage went red on a defect-free tree, reporting
  // `transport panel reads "Loading from TfL API..."` - which reads as a broken
  // panel rather than a slow one, and sends the reader hunting for a defect in
  // the panel.
  //
  // Both recorded failure modes at once: a blocking gate riding on a live
  // third party's latency (fifth instance here), and a number in a justifying
  // comment that was correct when written and had nothing to make it stale.
  // Same fix panel-contrast.mjs took on 2026-09-01.
  //
  // The short settle stays and is doing a different job: it lets the fetches
  // START and paint their spinners. Without it the poll below can satisfy
  // itself on the instant before any request is in flight, which would be a
  // check that passes by arriving early.
  await page.waitForTimeout(1500);
  await page
    .waitForFunction(
      () => {
        const sb = document.querySelector('#sidebar') || document.body;
        // TERMINAL means "no longer fetching", NOT "succeeded". An error or
        // empty state resolves this and then meets the checks below, which
        // fail with their own message. This cannot mask what the stage exists
        // to catch - a panel that never resolves still reds, at the bound.
        return !/Loading from|Finding nearest/i.test(sb.innerText);
      },
      { timeout: 25000 },
    )
    .catch(() => {});

  const panel = await page.evaluate(() => {
    const sb = document.querySelector('#sidebar') || document.body;
    const t = document.getElementById('postcode-transport-data');
    return {
      text: sb.innerText,
      transport: t ? t.innerText.trim() : null,
      stationNames: t
        ? Array.from(t.querySelectorAll('.station-name')).map((n) => n.textContent.trim())
        : [],
      epc: !!document.getElementById('postcode-epc-data'),
      nhs: !!document.getElementById('postcode-nhs-data'),
      // THE WHOLE PANEL, ASKED FOR THE WORD (2026-09-13, audit C1). This gate
      // has rendered updateSidebarPostcode() for non-London cities on every
      // run since it was written and asserted station names, EPC presence and
      // NYC copy - never whether the panel printed `undefined`. It did, on
      // every postcode result in nine cities, from three unguarded
      // interpolations (`property`, `crime`, `schoolNote`) that exist on
      // London and NYC records alone; and ratingBadgeClass(undefined) wrapped
      // an EMPTY pill in the worst-crime colour. The 11 Sep F1 fix guarded the
      // borough panel and widened panel-caveat.mjs to that panel; this is the
      // sibling panel and its gate, one function and one file over.
      undefinedCount: (sb.innerText.match(/undefined/g) || []).length,
      emptyBadges: Array.from(sb.querySelectorAll('.rating-badge')).filter((b) => !b.textContent.trim()).length,
    };
  });

  console.log(`${c.city} (${c.postcode})`);

  // Every city, London and NYC included: a fabricating default is a defect
  // wherever it renders, and a record with every field is exactly where a
  // regression would hide.
  check(
    `  ${c.city}: panel prints no "undefined"`,
    panel.undefinedCount === 0,
    panel.undefinedCount ? `${panel.undefinedCount} occurrence(s) in the rendered panel` : '',
  );
  check(
    `  ${c.city}: no empty rating badge`,
    panel.emptyBadges === 0,
    panel.emptyBadges ? `${panel.emptyBadges} badge(s) with a colour class and no text` : '',
  );

  if (c.uk) {
    check(
      `  ${c.city}: no New York content`,
      !/subway|MTA\.info/i.test(panel.text),
      /subway|MTA\.info/i.test(panel.text) ? 'panel mentions the NYC subway' : '',
    );
    // DATA, not shape. A rendered section with a spinner in it satisfies
    // "the element exists"; only a station NAME proves the register was read.
    check(
      `  ${c.city}: stations have real names`,
      panel.stationNames.length > 0,
      panel.stationNames.length
        ? `${panel.stationNames.length}: ${panel.stationNames.slice(0, 2).join(', ')}`
        : `transport panel reads "${(panel.transport || '').slice(0, 60)}"`,
    );
    check(
      `  ${c.city}: nothing stuck loading`,
      !/Loading from|Finding nearest/i.test(panel.text),
      /Loading from|Finding nearest/i.test(panel.text) ? 'a spinner never resolved' : '',
    );
    check(`  ${c.city}: EPC section present`, panel.epc, '');
    // London keeps its NHS panel; the others do not have one yet, and an
    // ABSENT section is the honest state while /nhs has an open concurrency
    // fault. Asserted in both directions so "we quietly enabled it" and "we
    // quietly lost it" both fail.
    check(
      `  ${c.city}: NHS present iff London`,
      panel.nhs === Boolean(c.london),
      `nhs=${panel.nhs} london=${Boolean(c.london)}`,
    );
    const want = await expectedAir(c.postcode);
    if (want.sensor || want.monitor) {
      await page
        .waitForFunction(() => {
          const s = document.getElementById('postcode-air-section');
          return s && !s.hidden;
        }, null, { timeout: 15000 })
        .catch(() => {});
    }
    const air = await page.evaluate(() => {
      const s = document.getElementById('postcode-air-section');
      if (!s) return null;
      // Where it sits: AFTER "Additional insights" (whose Air Quality card is DEFRA's modelled figure),
      // so the panel reads modelled first, then measured (Bill, 2026-10-19).
      const insights = Array.from(document.querySelectorAll('#sidebar h3')).find((h) => /ADDITIONAL INSIGHTS/.test(h.textContent));
      const insightsSection = insights && insights.closest('.sidebar-section');
      return {
        hidden: s.hidden,
        text: s.innerText,
        names: Array.from(s.querySelectorAll('.station-name')).map((n) => n.textContent.trim()),
        links: Array.from(s.querySelectorAll('a')).map((a) => a.textContent.trim()),
        afterInsights: insightsSection ? Boolean(insightsSection.compareDocumentPosition(s) & Node.DOCUMENT_POSITION_FOLLOWING) : null,
        aqCard: Boolean(insightsSection && /AIR QUALITY/i.test(insightsSection.innerText)),
      };
    });
    const wantNames = [want.sensor && want.sensor.name, want.monitor && want.monitor.name].filter(Boolean);
    const wantCredits = [want.sensor && AIR_SENSORS.attribution, want.monitor && AIR_MONITORS.attribution].filter(Boolean);
    check(
      `  ${c.city}: air measured nearby lists ${wantNames.length ? wantNames.join(' and ') : 'nothing (none within 5 km)'}, each saying what it is`,
      wantNames.length
        ? Boolean(air) && !air.hidden && JSON.stringify(air.names) === JSON.stringify(wantNames) &&
            Boolean(want.sensor) === /Breathe London sensor \(low-cost\), /.test(air.text) &&
            Boolean(want.monitor) === /Official DEFRA monitor, /.test(air.text)
        : !air || air.hidden,
      air ? `${JSON.stringify(air.names)} | ${air.text.slice(0, 160)}` : 'no air section',
    );
    if (wantNames.length) {
      check(
        `  ${c.city}: it comes after "Additional insights", and names the Air Quality card above only when it is there`,
        Boolean(air) && air.afterInsights !== false &&
          air.aqCard === /The Air Quality card above is DEFRA's modelled average/.test(air.text),
        JSON.stringify(air && { afterInsights: air.afterInsights, aqCard: air.aqCard }),
      );
    }
    if (wantNames.length) {
      check(
        `  ${c.city}: each reading carries its publisher's credit, word for word`,
        Boolean(air) && wantCredits.every((t) => air.links.includes(t)) && air.links.length === wantCredits.length,
        JSON.stringify(air && air.links),
      );
    }
  } else {
    check(
      `  ${c.city}: keeps its own transit copy`,
      /subway/i.test(panel.text),
      'NYC must still say subway - NaPTAN is UK-only',
    );
    const air = await page.evaluate(() => Boolean(document.getElementById('postcode-air-section')));
    check(`  ${c.city}: no air-measured-nearby section (UK sources only)`, !air, air ? 'section rendered' : '');
  }
  console.log('');
}

// THE PLANE ALTITUDE IS THE GLIDE PATH'S (website audit A1, 2026-10-07).
//
// For TW9 3PZ this row read "4,000-6,000 ft", a hand ladder by distance to the
// airport, while the front page and the street report said about 1,800 ft on
// Heathrow's 27R approach. The bound below is PHYSICS, not a copy of the code:
// the postcode is about 10 km from the runway on a 3-degree glide path, and
// 10.2 km x tan(3 deg) is about 535 m, about 1,750 ft. The old ladder fails it,
// and so does a lost height ("N/A", the row's not-loaded state).
console.log('Plane altitude under an approach');
{
  await page.evaluate((city) => window.switchCity(city), 'london');
  await page.waitForTimeout(1200);
  await page.fill('#search-input', 'TW9 3PZ');
  await page.press('#search-input', 'Enter');
  const row = await page
    .waitForFunction(
      () => {
        const label = [...document.querySelectorAll('.noise-detail-label')].find((l) => l.textContent.trim() === 'Plane altitude');
        const value = label?.parentElement?.querySelector('.noise-detail-value')?.textContent.trim();
        return value && value !== 'N/A' ? value : false;
      },
      { timeout: 25000 },
    )
    .then((h) => h.jsonValue())
    .catch(() => 'N/A (never resolved)');
  const ft = Number((row.match(/^About ([\d,]+) ft \(Heathrow 27R final approach\)$/) || [])[1]?.replace(/,/g, ''));
  check('TW9 3PZ: plane altitude is the 27R glide path, about 1,750 ft (not a ladder by distance)', ft >= 1500 && ft <= 2100, `row: "${row}"`);
  // THE AIRPORT CODE ONCE (2026-10-13). Every flight-path name carries its code, and the row
  // put the code in front again, reading "LHR LHR 27R final approach" on every city since the
  // names came from the AIP (found re-reading the LGM demo from the live site).
  const pathRow = await page.evaluate(
    () => [...document.querySelectorAll('.noise-detail-label')].find((l) => l.textContent.trim() === 'Nearest flight path')?.parentElement?.querySelector('.noise-detail-value')?.textContent.trim() || 'absent',
  );
  check('TW9 3PZ: nearest flight path names the airport once', pathRow === 'LHR 27R final approach', `row: "${pathRow}"`);

  // THE SAME FROM A DEEP LINK, in a fresh page that never touches the search box. The
  // typed search above preloads the geometry when the box takes focus; a link to
  // /map/?postcode= does not, and the first version analysed before the geometry
  // arrived and printed N/A (found retaking the LGM demo screenshot, 7 Oct).
  const deep = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await deep.goto(`${url}${url.includes('?') ? '&' : '?'}city=london&postcode=TW9%203PZ`, { waitUntil: 'domcontentloaded' });
  const deepRow = await deep
    .waitForFunction(
      () => {
        const label = [...document.querySelectorAll('.noise-detail-label')].find((l) => l.textContent.trim() === 'Plane altitude');
        const value = label?.parentElement?.querySelector('.noise-detail-value')?.textContent.trim();
        return value && value !== 'N/A' ? value : false;
      },
      { timeout: 25000 },
    )
    .then((h) => h.jsonValue())
    .catch(async () => `never resolved (row reads: ${await deep.evaluate(() => [...document.querySelectorAll('.noise-detail-label')].find((l) => l.textContent.trim() === 'Plane altitude')?.parentElement?.querySelector('.noise-detail-value')?.textContent.trim() || 'absent')})`);
  const deepFt = Number((deepRow.match(/^About ([\d,]+) ft \(Heathrow 27R final approach\)$/) || [])[1]?.replace(/,/g, ''));
  check('TW9 3PZ from a deep link: the same glide-path altitude, not N/A', deepFt >= 1500 && deepFt <= 2100, `row: "${deepRow}"`);
  // THE FIRST-RUN HINT GOES WHEN AN ANSWER ARRIVES BY ANY ROUTE (2026-10-08). It went only
  // when the search box took focus, so a deep link left "Type a postcode..." over the
  // answer. Read from what is painted, not from the class the fix sets.
  const deepHint = await deep.evaluate(() => {
    const h = document.getElementById('first-hint');
    return h ? getComputedStyle(h).display : 'absent';
  });
  check('TW9 3PZ from a deep link: the first-run hint is not painted over the answer', deepHint === 'none' || deepHint === 'absent', `#first-hint display: ${deepHint}`);
  await deep.close();
  console.log('');
}

// A BOROUGH CLICK IS AN ANSWER TOO. The hint says "or click a borough", and clicking one
// left it in place. A fresh page, so no saved "seen" flag: the hint must be painted first.
console.log('First-run hint after a borough click');
{
  const fresh = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await fresh.goto(url, { waitUntil: 'domcontentloaded' });
  await fresh.waitForSelector('path.borough', { timeout: 20000 });
  const painted = () => fresh.evaluate(() => getComputedStyle(document.getElementById('first-hint')).display);
  const before = await painted();
  await fresh.locator('path.borough').first().dispatchEvent('click');
  await fresh.waitForTimeout(500);
  const after = await painted();
  check('a borough click takes the first-run hint away (it was showing before)', before !== 'none' && after === 'none', `before: ${before}, after: ${after}`);
  await fresh.close();
  console.log('');
}

// THE PANEL'S DISTANCES ARE THE FRONT PAGE'S (2026-10-08). For TW3 1ES the panel said
// Heathrow 6.3 km and a flight path 0.6 km away - the airport's reference point, and the
// nearest corridor POINT (1 km apart) - while the front page said 4.9 km, and 0.3 km from
// the 27L centreline. The expected figures are computed here from js/flight_geometry.mjs
// and the AIP record, the front page's own source, at postcodes.io's coordinates (the
// map's source too). The path allows 0.1 km: the map draws the record's lines resampled.
console.log('Distances agree with the front page');
{
  const g = await import(new URL('../js/flight_geometry.mjs', import.meta.url).href);
  const proc = JSON.parse(await readFile(join(ROOT, 'data', 'flight-procedures.json'), 'utf-8'));
  const where = (await (await fetch('https://api.postcodes.io/postcodes/TW3%201ES')).json()).result;
  const near = g.routesNear(proc, g.plane(where.latitude, where.longitude), Infinity);
  const wantAirport = near.scope.find((x) => x.code === 'LHR').dist.toFixed(1);
  const wantLine = Math.min(...near.finals.map((f) => f.dist), ...near.departures.map((d) => d.dist));

  await page.evaluate((city) => window.switchCity(city), 'london');
  await page.waitForTimeout(1200);
  await page.fill('#search-input', 'TW3 1ES');
  await page.press('#search-input', 'Enter');
  const rows = await page
    .waitForFunction(
      () => {
        const read = (name) => [...document.querySelectorAll('.noise-detail-label')].find((l) => l.textContent.trim() === name)?.parentElement?.querySelector('.noise-detail-value')?.textContent.trim();
        const alt = read('Plane altitude');
        // The altitude resolving means the geometry has loaded and the panel was redrawn from it.
        if (!alt || alt === 'N/A' || !/TW3 1ES/i.test(document.getElementById('sidebar-content')?.textContent || '')) return false;
        const note = [...document.querySelectorAll('.property-note')].map((n) => n.textContent).find((t) => /km away/.test(t)) || '';
        return { airport: read('Nearest airport'), path: read('Path distance'), note };
      },
      { timeout: 25000 },
    )
    .then((h) => h.jsonValue())
    .catch(() => ({ airport: 'never resolved', path: 'never resolved', note: '' }));
  const gotLine = parseFloat(rows.path);
  check(`TW3 1ES: nearest airport is the front page's runway-strip figure, Heathrow (${wantAirport} km)`, rows.airport === `Heathrow (${wantAirport} km)`, `row: "${rows.airport}"`);
  check(`TW3 1ES: path distance is to the drawn line, about ${wantLine.toFixed(1)} km`, Math.abs(gotLine - wantLine) <= 0.1, `row: "${rows.path}"`);
  check('TW3 1ES: the noise summary says the same two figures', rows.note.includes(`${wantAirport}km away`) && rows.note.includes(`within ${gotLine.toFixed(1)}km`), `summary: "${rows.note.slice(0, 160)}"`);
  console.log('');
}

// A CITY WITH NO FLIGHT PATH SAYS SO. South Yorkshire has no airport, so no path was ever
// nearest and "Path distance" printed "Infinity km" (found 2026-10-08).
console.log('No flight path in South Yorkshire');
{
  await page.evaluate((city) => window.switchCity(city), 'southyorkshire');
  await page.waitForTimeout(1200);
  await page.fill('#search-input', 'S1 2HH');
  await page.press('#search-input', 'Enter');
  const row = await page
    .waitForFunction(
      () => [...document.querySelectorAll('.noise-detail-label')].find((l) => l.textContent.trim() === 'Path distance')?.parentElement?.querySelector('.noise-detail-value')?.textContent.trim() || false,
      { timeout: 25000 },
    )
    .then((h) => h.jsonValue())
    .catch(() => 'never resolved');
  check('S1 2HH: path distance says there is none, not "Infinity km"', row === 'No flight path in this area', `row: "${row}"`);
  console.log('');
}

// NEW YORK READS THE FAA'S GLIDE PATHS (2026-10-07). Its row was a ladder by distance
// to the airport ("1,000-2,500 ft" for anything within 5 km of JFK). Woodhaven's ZIP,
// typed from LONDON so the city switch and the FAA record's lazy load are both on the
// path: its point is 0.1 km off JFK 13L's centreline about 6.8 km out, and 6.8 km x
// tan(3 deg) is about 360 m, about 1,180 ft. Chelsea (10001) is under no final, and
// must say so rather than print a band.
console.log('Plane altitude in New York');
{
  // The previous search's row is overwritten with a marker BEFORE the next search, and the
  // poll waits for a row that is neither the marker nor the pre-geometry N/A: poll for the
  // state you want, never one already true. It waited for a value DIFFERENT from the last
  // one until 2026-10-11, which could never resolve when two places rightly read the same,
  // so the Howard Beach check reported "never resolved" on the old tree, not what it read.
  const STALE = 'stale: the previous search';
  const altitudeRow = (pg) =>
    pg
      .waitForFunction(
        (stale) => {
          const label = [...document.querySelectorAll('.noise-detail-label')].find((l) => l.textContent.trim() === 'Plane altitude');
          const value = label?.parentElement?.querySelector('.noise-detail-value')?.textContent.trim();
          return value && value !== 'N/A' && value !== stale ? value : false;
        },
        STALE,
        { timeout: 25000 },
      )
      .then((h) => h.jsonValue())
      .catch(() => 'N/A (never resolved)');
  const searchFor = async (q) => {
    await page.evaluate((stale) => {
      const label = [...document.querySelectorAll('.noise-detail-label')].find((l) => l.textContent.trim() === 'Plane altitude');
      const cell = label?.parentElement?.querySelector('.noise-detail-value');
      if (cell) cell.textContent = stale;
    }, STALE);
    await page.fill('#search-input', q);
    await page.press('#search-input', 'Enter');
    return altitudeRow(page);
  };
  await page.evaluate((city) => window.switchCity(city), 'london');
  await page.waitForTimeout(1200);
  const row = await searchFor('11421');
  const ft = Number((row.match(/^About ([\d,]+) ft \(JFK 13L final approach\)$/) || [])[1]?.replace(/,/g, ''));
  check("11421 (Woodhaven): the FAA's JFK 13L glide path, about 1,180 ft (not a ladder by distance)", ft >= 1000 && ft <= 1400, `row: "${row}"`);
  const chelsea = await searchFor('10001');
  check('10001 (Chelsea): under no final approach, and says so', chelsea === 'Not under a final approach', `row: "${chelsea}"`);
  // A GAP IN THE RECORD IS NOT "NOT UNDER" (audit 2026-10-09 I-5). Howard Beach's point is
  // about 3 km out and 0.3 km beside JFK 13R's extended centreline. The FAA publishes an
  // approach to 13R that this cycle does not code, so the record holds no glide angle,
  // 13R's final never entered the test, and the row read "Not under a final approach" in
  // the panel whose own Queens note puts Howard Beach "under JFK paths".
  const howard = await searchFor('11414');
  check('11414 (Howard Beach): beside JFK 13R, which has no glide path on record, says so rather than "not under"', howard === 'N/A (no glide path in the FAA record for JFK 13R)', `row: "${howard}"`);
  console.log('');
}

// SOLD PRICES: EACH ABSENCE SAYS WHICH ABSENCE IT IS (2026-09-25).
//
// The panel printed "cannot be loaded directly due to browser security
// restrictions" for a postcode with NO RECORDED SALES - the endpoint had
// answered 200 with an empty list. The live path above only ever reaches
// whichever state Land Registry happens to return for the probe postcode, and
// a state reached by chance is not gated, so each one is FORCED here by
// fulfilling /sold-prices with the Lambda's own shapes.
console.log('Sold prices, forced states');
const SOLD_STATES = [
  {
    name: 'no recorded sales (200, empty)',
    fulfil: { status: 200, body: { postcode: 'M1 1AE', transactions: [] } },
    want: /no recorded sales at this exact postcode/i,
  },
  {
    name: 'upstream outage (503)',
    fulfil: { status: 503, body: { error: 'Sold-prices upstream temporarily unavailable.' } },
    want: /could not be loaded just now/i,
  },
  {
    name: 'rows',
    fulfil: {
      status: 200,
      body: {
        postcode: 'M1 1AE',
        transactions: [{ price: 250000, date: '2025-03-14', address: '12', street: 'TEST STREET', type: 'Flat' }],
      },
    },
    want: /£250,000/,
  },
  {
    // The Kew rows Bill found (TW9 3PZ, 2026-10-19): a £20,000 sale of Land Registry property type
    // 'other' (a shop or its lease) listed beside £1.475m flats with nothing to tell them apart.
    // Types exactly as the Lambda sends them (`_pref_label`: 'other', 'flat-maisonette').
    name: 'a sale that is not a home says so',
    fulfil: {
      status: 200,
      body: {
        postcode: 'TW9 3PZ',
        transactions: [
          { price: 20000, date: '2025-09-11', address: '16', street: 'STATION PARADE', type: 'other' },
          { price: 1475000, date: '2025-05-09', address: '4A', street: 'STATION PARADE', type: 'flat-maisonette' },
        ],
      },
    },
    want: /£20,000\s*not a home · 16 STATION PARADE[\s\S]*£1,475,000\s*flat · 4A STATION PARADE[\s\S]*"Not a home": Land Registry records the sale as another kind of property/,
    absent: /Not a standard sale|leasehold|freehold/i, // a Lambda without the new fields: rows exactly as before
  },
  {
    // The same Kew rows with the fields the Lambda sends from 2026-10-20 (category, estate, saon,
    // as Land Registry answered for TW9 3PZ): the shop stays "not a home" and gains nothing, the 1997
    // sale shows its flat and tenure. A category-B row of type 'other' must not raise the second note.
    name: 'tenure and flat shown, a shop still not a home',
    fulfil: {
      status: 200,
      body: {
        postcode: 'TW9 3PZ',
        transactions: [
          { price: 20000, date: '2025-09-11', saon: '', address: '16', street: 'STATION PARADE', type: 'other', category: 'B', estate: 'leasehold' },
          { price: 79500, date: '1997-08-20', saon: 'FLAT 2', address: 'THE CAFE, 2', street: 'STATION PARADE', type: 'flat-maisonette', category: 'A', estate: 'leasehold' },
        ],
      },
    },
    want: /£20,000\s*not a home · 16 STATION PARADE[\s\S]*£79,500\s*leasehold flat · FLAT 2, THE CAFE, 2 STATION PARADE/,
    absent: /Not a standard sale/i,
  },
  {
    // A HOME sold outside category A (a repossession, a company, a mortgaged buy-to-let): the type
    // alone called it a plain flat. Constructed row in the Lambda's shape; no TW9 3PZ sale is one.
    name: 'a home sold outside the standard category says so',
    fulfil: {
      status: 200,
      body: {
        postcode: 'TW9 3PZ',
        transactions: [
          { price: 310000, date: '2024-02-01', saon: 'FLAT 5', address: '4A', street: 'STATION PARADE', type: 'flat-maisonette', category: 'B', estate: 'leasehold' },
        ],
      },
    },
    want: /£310,000\s*leasehold flat, not a standard sale · FLAT 5, 4A STATION PARADE[\s\S]*"Not a standard sale": Land Registry records the sale outside its standard category/,
    absent: /"Not a home"/,
  },
];
await page.evaluate((city) => window.switchCity(city), 'manchester');
await page.waitForTimeout(1200);
for (const s of SOLD_STATES) {
  await page.route('**/sold-prices?**', (route) =>
    route.fulfill({
      status: s.fulfil.status,
      contentType: 'application/json',
      headers: { 'access-control-allow-origin': '*' },
      body: JSON.stringify(s.fulfil.body),
    }),
  );
  // Blank the container first: the previous state's text satisfies the poll
  // below otherwise, and every reading comes back one state stale.
  await page.evaluate(() => {
    const el = document.getElementById('sold-prices-data');
    if (el) el.innerHTML = '';
  });
  await page.fill('#search-input', '');
  await page.fill('#search-input', 'M1 1AE');
  await page.press('#search-input', 'Enter');
  const text = await page
    .waitForFunction(
      () => {
        const el = document.getElementById('sold-prices-data');
        const t = el ? el.innerText : '';
        return t && !/Loading/i.test(t) ? t : false;
      },
      { timeout: 15000 },
    )
    .then((h) => h.jsonValue())
    .catch(() => '');
  await page.unroute('**/sold-prices?**');
  check(`  sold prices, ${s.name}`, s.want.test(text), `reads "${text.replace(/\s+/g, ' ').slice(0, 90)}"`);
  if (s.absent) check(`  sold prices, ${s.name}: nothing extra`, text !== '' && !s.absent.test(text), `reads "${text.replace(/\s+/g, ' ').slice(0, 120)}"`);
  // The false cause must never come back, in any state.
  check(`  sold prices, ${s.name}: no "browser security"`, !/browser security/i.test(text), '');
}
console.log('');

check('no page errors', errors.length === 0, errors.slice(0, 2).join(' | '));

await browser.close();
if (!TARGET) server.close();

if (failures.length) {
  console.error(`\nFAIL: ${failures.length} check(s) failed`);
  for (const f of failures) console.error(`  - ${f}`);
  process.exit(1);
}
console.log('\nOK: every UK city gets UK content, NYC keeps its own\n');
