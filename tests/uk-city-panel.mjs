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
import { keepPanelOpen } from './panel-fold.mjs';

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
await keepPanelOpen(page);
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
  // DEFRA's model for the postcode's 1 km square (2026-11-03, refined B), asked of the API HERE too, so the panel's
  // figure is checked against an answer this test got for itself. Null when the API does not answer: the case then
  // checks only that the panel names its yardstick honestly.
  let square = null;
  try {
    const env = await (await fetch(`${API}/v1/environment?lat=${result.latitude}&lon=${result.longitude}`, { signal: AbortSignal.timeout(20000) })).json();
    if (env && env.environment && env.provenance?.['environment.no2AnnualMeanUgm3']?.method === 'modelled') {
      square = { no2: env.environment.no2AnnualMeanUgm3 ?? null, pm25: env.environment.pm25AnnualMeanUgm3 ?? null };
    }
  } catch {
    square = null;
  }
  return {
    sensor: nearestWithin5(AIR_SENSORS.sites, result.latitude, result.longitude),
    monitor: nearestWithin5(AIR_MONITORS.sites, result.latitude, result.longitude),
    square,
  };
}
// What the panel's charts show, measured from the DOM: per pollutant, each row's kind and printed value, and where
// its mark's centre sits along the drawn axis (0 at its start, 1 at its end), against the axis's own maximum.
const readCharts = (pg) =>
  pg.evaluate(() => {
    const out = {};
    for (const svg of document.querySelectorAll('#postcode-air-section svg[data-air-chart]')) {
      const axis = svg.querySelector('line[data-axis]').getBoundingClientRect();
      out[svg.dataset.airChart] = {
        max: Number(svg.dataset.max),
        rows: [...svg.querySelectorAll('g[data-kind]')].map((g) => {
          const mark = g.querySelector('[data-mark]');
          const r = mark && mark.getBoundingClientRect();
          return { kind: g.dataset.kind, value: g.dataset.value, at: r ? (r.left + r.width / 2 - axis.left) / axis.width : null };
        }),
      };
    }
    const first = document.querySelector('#postcode-air-section .air-key li');
    return { charts: out, keyFirst: first ? { source: first.dataset.airSource, text: first.innerText } : null };
  });

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
      // Where it sits: in the Air and flood group, ahead of the fold, under the council's rating (Bill's pick, 2026-11-04).
      const group = s.closest('.find-group');
      return {
        hidden: s.hidden,
        text: s.innerText,
        names: Array.from(s.querySelectorAll('.station-name')).map((n) => n.textContent.trim()),
        links: Array.from(s.querySelectorAll('a')).map((a) => a.textContent.trim()),
        inGroup: Boolean(group) && /AIR AND FLOOD/i.test(group.querySelector('h3')?.textContent || '') && !s.closest('#panel-all'),
      };
    });
    const wantNames = [want.sensor && want.sensor.name, want.monitor && want.monitor.name].filter(Boolean);
    const wantCredits = [want.sensor && AIR_SENSORS.attribution, want.monitor && AIR_MONITORS.attribution].filter(Boolean);
    check(
      `  ${c.city}: air measured nearby lists ${wantNames.length ? wantNames.join(' and ') : 'nothing (none within 5 km)'}, each saying what it is`,
      wantNames.length
        ? Boolean(air) && !air.hidden && JSON.stringify(air.names) === JSON.stringify(wantNames) &&
            Boolean(want.sensor) === /Breathe London sensor, low-cost, provisional\./.test(air.text) &&
            Boolean(want.monitor) === /Official DEFRA monitor, ratified\./.test(air.text)
        : !air || air.hidden,
      air ? `${JSON.stringify(air.names)} | ${air.text.slice(0, 160)}` : 'no air section',
    );
    if (wantNames.length) {
      // Each caveat said once (2026-11-11): the rows name a sensor provisional and a monitor ratified, so the paragraph
      // under them does not say it again; the credit line carries the publishers' own words with no "Sources:" before them.
      const times = (re) => (air.text.match(re) || []).length;
      check(`  ${c.city}: the air fold says each caveat once, and its credit line is the publishers' words alone`,
        times(/provisional/g) <= 1 && times(/ratified/g) <= 1 && !/Sources: /.test(air.text),
        `provisional x${times(/provisional/g)}, ratified x${times(/ratified/g)}`);
    }
    if (wantNames.length) {
      // SIDE BY SIDE (2026-11-03, refined B): one chart per pollutant something measures; DEFRA's model for the
      // postcode's own 1 km square first (the API's figure, asked for above), then the sensor and the monitor, each
      // printing ITS OWN figure and drawn to scale on the axis the chart draws.
      const seen = await readCharts(page);
      const fmt = (v) => (v === null || v === undefined ? '' : Number(v).toFixed(1));
      const wantRows = (p) =>
        [
          want.square && { kind: 'model', value: fmt(want.square[p]) },
          want.sensor && { kind: 'sensor', value: fmt(want.sensor[p] && want.sensor[p].mean) },
          want.monitor && { kind: 'monitor', value: fmt(want.monitor[p] && want.monitor[p].mean) },
        ].filter(Boolean);
      for (const p of ['no2', 'pm25']) {
        const rows = wantRows(p);
        const expectChart = rows.some((r) => r.value !== '');
        const got = seen.charts[p];
        check(
          `  ${c.city}: ${p.toUpperCase()} ${expectChart ? 'shows each source\'s own figure, DEFRA\'s 1 km model first' : 'has no chart (nothing measures it here)'}`,
          expectChart
            ? Boolean(got) && JSON.stringify(got.rows.map((r) => ({ kind: r.kind, value: r.value }))) === JSON.stringify(rows)
            : !got,
          JSON.stringify({ want: rows, got: got && got.rows.map((r) => `${r.kind}=${r.value}`) }),
        );
        if (got) {
          const off = got.rows.filter((r) => r.value !== '' && Math.abs(r.at - Math.min(Number(r.value), got.max) / got.max) > 0.012);
          check(`  ${c.city}: ${p.toUpperCase()} marks sit to scale on the drawn axis`, off.length === 0, JSON.stringify(off));
        }
      }
      check(
        `  ${c.city}: the key opens with DEFRA's model for the postcode's own 1 km square`,
        !want.square || (seen.keyFirst && seen.keyFirst.source === 'model' && /1 km square/.test(seen.keyFirst.text)),
        JSON.stringify(seen.keyFirst),
      );
    }
    if (wantNames.length) {
      check(
        `  ${c.city}: it sits in Air and flood, ahead of the fold`,
        Boolean(air) && air.inGroup,
        JSON.stringify(air && { inGroup: air.inGroup }),
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

// THE 1 KM FIGURE CANNOT LOAD (2026-11-03, refined B): the council's DEFRA average stands in, named as the council's,
// and the key says the postcode's own figure did not load. Reached ON PURPOSE by refusing /v1/environment for this
// page, never by hoping the API is slow; the expected figure is read from the data file, not from the page.
console.log('Air nearby when the 1 km figure cannot load');
{
  const fb = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await keepPanelOpen(fb);
  await fb.route('**/v1/environment**', (r) => r.abort());
  await fb.goto(url, { waitUntil: 'domcontentloaded' });
  await fb.waitForTimeout(3000);
  await fb.evaluate((city) => window.switchCity(city), 'london');
  await fb.waitForTimeout(1200);
  await fb.fill('#search-input', 'SW11 1AA');
  await fb.press('#search-input', 'Enter');
  await fb
    .waitForFunction(() => {
      const s = document.getElementById('postcode-air-section');
      return s && !s.hidden;
    }, null, { timeout: 30000 })
    .catch(() => {});
  const seen = await readCharts(fb);
  const council = JSON.parse(await readFile(join(ROOT, 'data', 'borough-extra.json'), 'utf8')).london.Wandsworth;
  const model = seen.charts.no2 && seen.charts.no2.rows.find((r) => r.kind === 'model');
  check(
    '  SW11 1AA: the key names the council average and says the 1 km figure did not load',
    Boolean(seen.keyFirst) && seen.keyFirst.source === 'model' && /Wandsworth average/.test(seen.keyFirst.text) && /did not load/.test(seen.keyFirst.text),
    JSON.stringify(seen.keyFirst),
  );
  check(
    "  SW11 1AA: its NO2 row is Wandsworth's DEFRA figure, read from the data file",
    Boolean(model) && model.value === Number(council.no2AnnualMeanUgm3).toFixed(1),
    JSON.stringify({ model, want: council.no2AnnualMeanUgm3 }),
  );
  await fb.close();
}
console.log('');

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
  await keepPanelOpen(deep);
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
  // THE SEARCH GUIDE ENDS WHEN AN ANSWER ARRIVES BY ANY ROUTE (the first-run banner's rule of 2026-10-08, which the guide
  // replaced on 2026-11-11): a deep link's answer must not sit under a box still pointing at the search. Read from what is
  // painted: the box's ring. tests/search-guide.mjs holds the rest (remembered or not, chips, timing).
  const deepHint = await deep.evaluate(() => ({ guide: !!document.querySelector('.search-box.guide'), banner: !!document.getElementById('first-hint') }));
  check('TW9 3PZ from a deep link: the search guide has ended, and no first-run banner exists', !deepHint.guide && !deepHint.banner, JSON.stringify(deepHint));
  await deep.close();
  console.log('');
}

// A BOROUGH CLICK IS AN ANSWER TOO (the first-run banner's rule, now the search guide's). A fresh page, so no saved
// "seen" flag: the guide must be on first.
console.log('Search guide after a borough click');
{
  const fresh = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await fresh.goto(url, { waitUntil: 'domcontentloaded' });
  await fresh.waitForSelector('path.borough', { timeout: 20000 });
  const painted = () => fresh.evaluate(() => (document.querySelector('.search-box.guide') ? 'on' : 'off'));
  const before = await painted();
  await fresh.locator('path.borough').first().dispatchEvent('click');
  await fresh.waitForTimeout(500);
  const after = await painted();
  check('a borough click ends the search guide (it was on before)', before === 'on' && after === 'off', `before: ${before}, after: ${after}`);
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
        const tile = document.querySelector('[data-find="path"] .t-level')?.textContent.trim() || '';
        return { airport: read('Nearest airport'), path: read('Path distance'), tile };
      },
      { timeout: 25000 },
    )
    .then((h) => h.jsonValue())
    .catch(() => ({ airport: 'never resolved', path: 'never resolved', tile: '' }));
  const gotLine = parseFloat(rows.path);
  check(`TW3 1ES: nearest airport is the front page's runway-strip figure, Heathrow (${wantAirport} km)`, rows.airport === `Heathrow (${wantAirport} km)`, `row: "${rows.airport}"`);
  check(`TW3 1ES: path distance is to the drawn line, about ${wantLine.toFixed(1)} km`, Math.abs(gotLine - wantLine) <= 0.1, `row: "${rows.path}"`);
  // The noise summary that repeated these went with the fold's repeats (2026-11-08); the path tile says the distance now.
  check('TW3 1ES: the nearest flight path tile says the same distance', rows.tile === `${gotLine.toFixed(1)} km away`, `tile: "${rows.tile}"`);
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

// /epc ONLY FOR A FULL POSTCODE (2026-11-03). A district search carried `postcode: 'TW3'` (the outcode fallback) to
// /epc; the register answered 400 and the Lambda reported its own 502: 134 of the API's 146 5xx in a day. The panel
// said "temporarily unavailable", which was not true either. Counted at the network, with /epc stubbed.
{
  await page.evaluate((city) => window.switchCity(city), 'london');
  await page.waitForTimeout(1200);
  const epcAsked = [];
  await page.route('**/epc?**', (route) => {
    epcAsked.push(new URL(route.request().url()).searchParams.get('postcode'));
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'access-control-allow-origin': '*' },
      body: JSON.stringify({ postcode: 'stub', available: true, count: 0, certificates: [], summary: null }),
    });
  });
  for (const [q, full] of [['TW3', false], ['TW3 3QL', true]]) {
    epcAsked.length = 0;
    await page.evaluate(() => {
      const el = document.getElementById('postcode-epc-data');
      if (el) el.innerHTML = '';
    });
    await page.fill('#search-input', '');
    await page.fill('#search-input', q);
    await page.press('#search-input', 'Enter');
    const text = await page
      .waitForFunction(
        () => {
          const el = document.getElementById('postcode-epc-data');
          const t = el ? el.innerText : '';
          return t && !/Loading/i.test(t) ? t : false;
        },
        { timeout: 15000 },
      )
      .then((h) => h.jsonValue())
      .catch(() => '');
    if (full) {
      check(`  EPC: a full postcode (${q}) still asks /epc`, epcAsked.length > 0, `asked ${JSON.stringify(epcAsked)}`);
    } else {
      check(`  EPC: a district search (${q}) never asks /epc`, epcAsked.length === 0, `asked ${JSON.stringify(epcAsked)}`);
      check('  EPC: a district search asks for a full postcode', /Enter a full postcode for EPC data/.test(text),
        `reads "${text.replace(/\s+/g, ' ').slice(0, 100)}"`);
    }
  }
  // The guard itself, for the paths a district flag does not catch (a US ZIP typed on a UK map, which
  // tests/bayarea-map.mjs does on every run): no request, and the panel says why.
  epcAsked.length = 0;
  const guard = await page.evaluate(async () => {
    const zip = await fetchEpcData('94301');
    const district = await fetchEpcData('TW9');
    renderEpcData('postcode-epc-data', zip);
    return { zip, district, text: document.getElementById('postcode-epc-data')?.innerText || '' };
  });
  check('  EPC: fetchEpcData sends nothing for a ZIP or a district', epcAsked.length === 0
    && guard.zip.fullPostcodeOnly === true && guard.district.fullPostcodeOnly === true, JSON.stringify({ epcAsked, ...guard }));
  check('  EPC: the panel says why, never "temporarily unavailable"', /Enter a full postcode for EPC data/.test(guard.text)
    && !/temporarily/i.test(guard.text), `reads "${guard.text.slice(0, 100)}"`);
  await page.unroute('**/epc?**');
}
console.log('');

// THE PANEL LEADS WITH ITS FINDINGS (Bill's pick, 2026-11-04: Stitch's draft), as an answer card and tiles closed until
// tapped since 2026-11-08 (Bill: "keep to road noise is high", then the explanation in plain words). This page does NOT
// keep the fold open: it reads each tile's face as a visitor first sees it, then opens the tiles to read what they explain.
// Every lookup is stubbed, so each road case is reached on purpose.
console.log('Findings first');
{
  const fp = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const fpErrors = [];
  fp.on('pageerror', (e) => fpErrors.push(e.message));
  const json = (route, body) =>
    route.fulfill({ status: 200, contentType: 'application/json', headers: { 'access-control-allow-origin': '*' }, body: JSON.stringify(body) });
  const environmentWith = (road, postcode = 'SW5 9HP') => ({
    location: { postcode },
    environment: { ...road, roadNoiseWhoGuidelineDb: 53, no2AnnualMeanUgm3: 24, pm25AnnualMeanUgm3: 9.6, no2WhoGuidelineUgm3: 10, pm25WhoGuidelineUgm3: 5, airQualitySource: 'DEFRA background pollution maps' },
    provenance: {
      'environment.roadNoiseLdenDb': { method: 'modelled', period: '2021' },
      'environment.no2AnnualMeanUgm3': { method: 'modelled', resolution: '1 km grid', period: '2024' },
    },
  });
  let environment = null;
  await fp.route('**/v1/environment**', (r) => (environment ? json(r, environment) : r.abort()));
  await fp.route('**/transport?**', (r) => json(r, { stations: [{ name: "Earl's Court Underground Station", distance: 376, lines: ['district'] }], lineStatus: [] }));
  await fp.route('**/nhs?**', (r) => json(r, { gp: [{ name: 'Brompton Medical Centre', distance: 49 }], pharmacies: [], hospitals: [] }));
  await fp.route('**/sold-prices?**', (r) =>
    json(r, { transactions: [
      { price: 20000, type: 'other', date: '2025-06-01', address: '1', street: 'Shop Row' },
      { price: 1810000, type: 'terraced', category: 'A', date: '2025-01-15', address: '241', street: 'Old Brompton Road' },
    ] }));
  await fp.route('**/epc?**', (r) => json(r, { available: true, count: 32, certificates: [], summary: { averageBand: 'D', averageRating: 67, bandDistribution: { D: 16 } } }));
  await fp.goto(url, { waitUntil: 'domcontentloaded' });
  await fp.waitForTimeout(2500);
  await fp.evaluate((city) => window.switchCity(city), 'london');
  await fp.waitForTimeout(1200);

  const readPanel = () =>
    fp.evaluate(() => {
      const norm = (t) => (t || '').replace(/\s+/g, ' ').trim();
      const text = (k) => norm(document.querySelector(`[data-find="${k}"]`)?.innerText);
      // Each tile's explanation, read opened as a reader who tapped it would, then closed again.
      const tiles = [...document.querySelectorAll('#sidebar-content details.tile')];
      const wasOpen = tiles.map((t) => t.open);
      tiles.forEach((t) => { t.open = true; });
      const full = Object.fromEntries(['road', 'aircraft', 'planes', 'path', 'air', 'flood', 'crime', 'transport', 'healthcare', 'schools', 'price', 'sold', 'epc']
        .map((k) => [k, norm(document.querySelector(`[data-find="${k}"]`)?.innerText)]));
      tiles.forEach((t, i) => { t.open = wasOpen[i]; });
      const fold = document.getElementById('panel-all');
      const groups = [...document.querySelectorAll('.find-group')];
      const notify = document.querySelector('.notify-block');
      return {
        road: text('road'), aircraft: text('aircraft'), planes: text('planes'), path: text('path'), air: text('air'), flood: text('flood'),
        crime: text('crime'), transport: text('transport'), healthcare: text('healthcare'), schools: text('schools'),
        price: text('price'), sold: text('sold'), epc: text('epc'),
        full,
        planesChart: [...document.querySelectorAll('[data-find="planes"] svg[data-planes-chart] g[data-kind]')].map((g) => [g.dataset.kind, g.querySelectorAll('text')[1]?.textContent]),
        anyOpen: wasOpen.some(Boolean),
        head: norm(document.getElementById('ac-head')?.textContent),
        pills: [...document.querySelectorAll('#ac-pills .ac-pill')].map((x) => x.textContent),
        roadBar: Boolean(document.querySelector('[data-find="road"] .t-track')),
        foldOpen: Boolean(fold && fold.open),
        foldHides: ![...document.querySelectorAll('.noise-detail-label')].some((l) => l.getClientRects().length > 0),
        shown: groups.filter((g) => getComputedStyle(g).display !== 'none').map((g) => g.querySelector('h3').textContent.trim()),
        order: Boolean(fold && notify) && Boolean(groups.at(-1).compareDocumentPosition(fold) & Node.DOCUMENT_POSITION_FOLLOWING) && Boolean(fold.compareDocumentPosition(notify) & Node.DOCUMENT_POSITION_FOLLOWING),
        airInGroup: Boolean(document.getElementById('postcode-air-section')?.closest('.find-group')),
        note: [...document.querySelectorAll('.find-group .sec-wide:not([hidden])')].map((n) => n.textContent.trim()),
        shownText: groups.map((g) => g.innerText).join(' '),
        favImpact: document.querySelector('.fav-btn')?.dataset.favImpact,
        all: document.getElementById('sidebar-content').innerText,
      };
    });
  const search = async (pc, env, settled) => {
    environment = env;
    await fp.evaluate(() => { const c = document.getElementById('sidebar-content'); if (c) c.innerHTML = ''; });
    await fp.fill('#search-input', '');
    await fp.fill('#search-input', pc);
    await fp.press('#search-input', 'Enter');
    await fp.waitForFunction(settled, null, { timeout: 20000 }).catch(() => {});
    return readPanel();
  };
  const loaded = () => /\S/.test(document.querySelector('[data-find="sold"]')?.innerText || '') && /\S/.test(document.querySelector('[data-find="epc"]')?.innerText || '') && /m$/.test((document.querySelector('[data-find="healthcare"]')?.innerText || '').trim()) && /\S/.test(document.querySelector('[data-find="road"]')?.innerText || '') && /\S/.test(document.querySelector('[data-find="planes"]')?.innerText || '');

  const over = await search('SW5 9HP', environmentWith({ roadNoiseLdenDb: 71.8 }), loaded);
  check('every tile starts closed', !over.anyOpen);
  check('the rating leads, explained by the postcode\'s own figure beside the WHO level', /^Road noise High Kensington and Chelsea-wide$/.test(over.road)
    && /This postcode 71\.8 dB The WHO recommends at most 53 dB/.test(over.full.road)
    && /The rating is for Kensington and Chelsea as a whole; the bars are for this postcode\./.test(over.full.road)
    && /Source: DEFRA noise map \(modelled\), 2021/.test(over.full.road), `${over.road} | ${over.full.road}`);
  check('all four groups show, the fold starts closed and hides its sections', over.shown.length === 4 && !over.foldOpen && over.foldHides, JSON.stringify([over.shown, over.foldOpen, over.foldHides]));
  check('the findings come first, then the fold, then the notify form', over.order);
  check('the air charts sit in their group, ahead of the fold', over.airInGroup);
  check('whose rating it is: said once for Air and flood and Living here, and on the road and price tiles, whose sections mix in this postcode\'s own', JSON.stringify(over.note) === JSON.stringify(['Kensington and Chelsea-wide', 'Kensington and Chelsea-wide'])
    && /Kensington and Chelsea-wide$/.test(over.road) && /Kensington and Chelsea-wide$/.test(over.price), JSON.stringify([over.note, over.road, over.price]));
  check('aircraft says its figure, as an estimate', /^Aircraft noise (Low|Moderate|High) \d+\.\d out of 10$/.test(over.aircraft) && /Our estimate from the published flight routes/.test(over.full.aircraft), `${over.aircraft} | ${over.full.aircraft}`);
  check('planes come from the postcode\'s own file', /^Heathrow planes overhead \S+ a day flying (west|east)$/.test(over.planes) && JSON.stringify(over.planesChart[0]) === JSON.stringify(['westerly', '56% of days']), `${over.planes} | ${JSON.stringify(over.planesChart)}`);
  check('the headline is the front page\'s sentence for this place (js/answer-lead.mjs)', /^Fewer than \d+ Heathrow planes a day pass over SW5 9HP$|^On most days, about \d+ Heathrow planes a day pass over SW5 9HP$/.test(over.head), over.head);
  check('the planes notes keep their credits', /adsb\.lol/.test(await fp.evaluate(() => document.querySelector('[data-find="planes"] details')?.textContent || '')));
  check('crime is set against a typical London borough, in words', /^Crime \w+/.test(over.crime) && /A typical London borough/.test(over.full.crime) && /Kensington and Chelsea has [\d.]+ recorded crimes a year for every 1,000 people\./.test(over.full.crime), over.full.crime);
  check('the crime note says no figure twice', !/recorded offences per 1,000 residents/.test(over.full.crime), over.full.crime);
  check('station and doctor are the lists\' own first rows', /Earl's Court is 376 m away\./.test(over.full.transport) && /Brompton Medical Centre is 49 m away\./.test(over.full.healthcare), `${over.full.transport} | ${over.full.healthcare}`);
  check('the last sale passes the shop', /£1,810,000 January 2025$/.test(over.sold), over.sold);
  check('energy reads plainly', /^Energy rating Band D 67 out of 100$/.test(over.epc) && /The average of 32 energy certificates/.test(over.full.epc), `${over.epc} | ${over.full.epc}`);
  check('nothing reads undefined, null or NaN', !/\bundefined\b|\bNaN\b|\bnull\b/.test(over.all));
  const notifyLabel = await fp.evaluate(() => document.querySelector('label[for="notify-email"]').getBoundingClientRect().width);
  check('the email label is for screen readers only (a class with no rule showed it, live, until 2026-11-04)', notifyLabel <= 1, String(notifyLabel));

  check('a saved favourite uses the finding\'s own word', new RegExp(`^Aircraft noise ${over.favImpact} `, 'i').test(over.aircraft), JSON.stringify([over.aircraft, over.favImpact]));

  const under = await search('SW5 9JZ', environmentWith({ roadNoiseLdenDb: 49.9 }, 'SW5 9JZ'), loaded);
  check('a figure under the guideline keeps the council\'s rating, as Bill chose, and its own true number', /^Road noise High /.test(under.road) && /This postcode 49\.9 dB/.test(under.full.road), `${under.road} | ${under.full.road}`);

  const quiet = await search('SW5 9HP', environmentWith({ roadNoiseBelowDb: 45 }), loaded);
  check('a surveyed-quiet postcode gets no rating, no reading, no bar and no council\'s name', /^Road noise Under the WHO level$/.test(quiet.road) && /DEFRA’s map shows no road noise here at 45 dB or above/.test(quiet.full.road) && !quiet.roadBar, `${quiet.road} | ${quiet.full.road}`);

  const neighbour = await search('SW5 9HP', environmentWith({ roadNoiseLdenDb: 49.9 }, 'SW5 9JZ'), loaded);
  check('a reading the API gives for a neighbouring postcode never passes as this one', /^Road noise High Kensington and Chelsea-wide$/.test(neighbour.road) && !/49\.9/.test(neighbour.full.road) && !/49\.9/.test(neighbour.head), `${neighbour.full.road} | ${neighbour.head}`);

  const failed = await search('SW5 9HP', null, loaded);
  check('with no figure the rating names its council, and says so', /^Road noise High Kensington and Chelsea-wide$/.test(failed.road)
    && /\d+ in every 100 Kensington and Chelsea postcodes louder than the World Health Organization \(WHO\) recommends/.test(failed.full.road)
    && /We have no reading for this street, so this is for Kensington and Chelsea as a whole\./.test(failed.full.road) && !failed.roadBar, failed.full.road);

  const area = await search('SW5', environmentWith({ roadNoiseLdenDb: 71.8 }), () => /\S/.test(document.querySelector('[data-find="road"]')?.innerText || ''));
  check('an area search asks for no postcode figure', /^Road noise \w+/.test(area.road) && /so this is for .+ as a whole/.test(area.full.road), area.full.road);
  // Outside London the list is NaPTAN's, in rows of its own: the finding must find those too.
  await fp.evaluate((city) => window.switchCity(city), 'manchester');
  await fp.waitForTimeout(1200);
  const north = await search('M1 1AE', environmentWith({ roadNoiseLdenDb: 60 }, 'M1 1AE'), () => /\d/.test(document.querySelector('[data-find="transport"]')?.innerText || ''));
  check('outside London the station comes from the NaPTAN list', /is \d+(\.\d+)? ?k?m away\./.test(north.full.transport), north.full.transport);
  check('no page errors in the findings', fpErrors.length === 0, fpErrors.slice(0, 2).join(' | '));
  await fp.close();

  // Should the module not load, nothing may be stranded behind a fold no one was told to open.
  // Service workers off: the worker fetches the module itself, out of sight of page.route, so the block would not bite.
  const noModule = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, serviceWorkers: 'block' })).newPage();
  await noModule.route('**/js/panel-findings.mjs', (r) => r.abort());
  await noModule.goto(url, { waitUntil: 'domcontentloaded' });
  await noModule.waitForTimeout(2500);
  await noModule.evaluate((city) => window.switchCity(city), 'london');
  await noModule.waitForTimeout(1200);
  await noModule.fill('#search-input', 'SW5 9HP');
  await noModule.press('#search-input', 'Enter');
  const opened = await noModule.waitForFunction(() => document.getElementById('panel-all')?.open === true, null, { timeout: 15000 }).then(() => true).catch(() => false);
  check('if the findings cannot load, the fold opens by itself', opened);
  await noModule.close();

  // New York answers from its own figures, never against London's.
  const ny = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await ny.goto(url, { waitUntil: 'domcontentloaded' });
  await ny.waitForTimeout(2500);
  await ny.evaluate((city) => window.switchCity(city), 'nyc');
  await ny.waitForTimeout(1200);
  await ny.fill('#search-input', '10001');
  await ny.press('#search-input', 'Enter');
  await ny.waitForFunction(() => /\S/.test(document.querySelector('[data-find="crime"]')?.innerText || ''), null, { timeout: 20000 }).catch(() => {});
  const nyCrime = await ny.evaluate(() => document.querySelector('[data-find="crime"]')?.innerText || '');
  const nyAll = await ny.evaluate(() => document.getElementById('sidebar-content').innerText);
  const nyShown = await ny.evaluate(() => {
    document.querySelectorAll('#sidebar-content details.tile').forEach((t) => { t.open = true; });
    return [...document.querySelectorAll('.find-group')].map((g) => g.innerText).join(' ');
  });
  check('New York\'s findings say borough and ZIP code, never council or postcode', /borough|ZIP code/i.test(nyShown) && !/\bcouncil\b|\bpostcode/i.test(nyShown) && !/\bcouncil\b|\bpostcode/i.test(nyAll), nyShown.slice(0, 200));
  check('New York\'s crime is never set against London\'s', nyCrime !== '' && !/London/.test(nyCrime), nyCrime);
  check('New York\'s panel reads nothing undefined', !/\bundefined\b|\bNaN\b/.test(nyAll));
  await ny.close();

  // ON A PHONE, ONE DETAIL CARD A ROW (Bill, 2026-11-09: "do what's best for the phone view"). Two half cards left an
  // opened card's neighbour alone beside a gap; in one column opening only pushes the rest down. Measured, not read from
  // the CSS: every closed card fills the row, and an open card's chevron sits on its face, not halfway down its list.
  const ph = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const phErrors = [];
  ph.on('pageerror', (e) => phErrors.push(e.message));
  await ph.route('**/v1/environment**', (r) => r.abort());
  await ph.route('**/transport?**', (r) => json(r, { stations: [{ name: "Earl's Court Underground Station", distance: 376, lines: ['district'] }], lineStatus: [] }));
  await ph.route('**/nhs?**', (r) =>
    json(r, { gp: [{ name: 'Brompton Medical Centre', distance: 49 }], pharmacies: ['Boots', 'Superdrug', 'Rowlands', 'Day Lewis', 'Bliss'].map((name, i) => ({ name, distance: 120 + 90 * i })), hospitals: [] }));
  await ph.route('**/epc?**', (r) => json(r, { available: true, count: 32, certificates: [], summary: { averageBand: 'D', averageRating: 67, bandDistribution: { D: 16 } } }));
  await ph.goto(url, { waitUntil: 'domcontentloaded' });
  await ph.waitForTimeout(2500);
  await ph.evaluate((city) => window.switchCity(city), 'london');
  await ph.waitForTimeout(1200);
  await ph.fill('#search-input', 'SW5 9HP');
  await ph.press('#search-input', 'Enter');
  await ph.waitForFunction(() => {
    const v = (id) => document.querySelector(`#${id} .dc-v`)?.textContent.trim();
    return v('dcard-station') && v('dcard-station') !== '…' && v('dcard-pharmacy');
  }, null, { timeout: 20000 }).catch(() => {});
  const phone = await ph.evaluate(() => {
    document.getElementById('panel-all').open = true;
    const box = document.querySelector('#panel-all .dcards');
    const cards = [...box.querySelectorAll(':scope > details.dcard')].filter((c) => !c.hidden);
    const row = box.getBoundingClientRect();
    const narrow = cards.filter((c) => Math.abs(c.getBoundingClientRect().width - row.width) > 1).map((c) => c.id);
    const card = document.getElementById('dcard-pharmacy');
    card.open = true;
    const face = card.querySelector('summary');
    const mark = getComputedStyle(face, '::after');
    const markAt = parseFloat(mark.top) + parseFloat(mark.marginTop);
    return { shown: cards.length, narrow, markAt, faceHeight: face.offsetHeight, cardHeight: card.offsetHeight };
  });
  check('on a phone every detail card fills its row', phone.shown >= 4 && phone.narrow.length === 0,
    `${phone.shown} cards shown; narrower than the row: ${phone.narrow.join(', ') || 'none'}`);
  check('on a phone an open card\'s chevron sits on its face', phone.cardHeight > phone.faceHeight + 40 && phone.markAt > 0 && phone.markAt < phone.faceHeight,
    `chevron at ${phone.markAt} px; face ${phone.faceHeight} px; card ${phone.cardHeight} px`);
  check('no page errors at phone width', phErrors.length === 0, phErrors.slice(0, 2).join(' | '));
  await ph.close();

  // ENTER BEATS THE SUGGESTIONS (2026-11-09, a live bug). Typing waits 250 ms, then asks postcodes.io; Enter closed the
  // list, but the pause or the request still on its way then opened it again, over the answer. Reached on purpose both
  // ways: Enter inside the pause, and Enter while the request is held. And typing still shows suggestions, so the fix
  // cannot pass by turning them off.
  const sg = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const sgErrors = [];
  sg.on('pageerror', (e) => sgErrors.push(e.message));
  let holdNext = false;
  let held = null;
  let heldArrived = () => {};
  const acAsked = [];
  await sg.route('**/postcodes/*/autocomplete', (r) => {
    acAsked.push(decodeURIComponent(new URL(r.request().url()).pathname.split('/')[2]));
    if (holdNext) {
      held = r;
      heldArrived();
    } else json(r, { status: 200, result: ['SW5 9AA', 'SW5 9HP'] });
  });
  await sg.route('**/v1/environment**', (r) => r.abort());
  await sg.route('**/transport?**', (r) => json(r, { stations: [], lineStatus: [] }));
  await sg.route('**/nhs?**', (r) => json(r, { gp: [], pharmacies: [], hospitals: [] }));
  await sg.route('**/epc?**', (r) => json(r, { available: false }));
  await sg.goto(url, { waitUntil: 'domcontentloaded' });
  await sg.waitForTimeout(2500);
  await sg.evaluate((city) => window.switchCity(city), 'london');
  await sg.waitForTimeout(1200);
  const listOpen = () => sg.evaluate(() => document.getElementById('autocomplete-dropdown').classList.contains('visible'));

  await sg.fill('#search-input', 'SW5 9');
  const offered = await sg.waitForFunction(() => document.querySelectorAll('#autocomplete-dropdown.visible .autocomplete-item').length > 0, null, { timeout: 8000 })
    .then(() => true, () => false);
  check('typing still offers postcode suggestions', offered);

  // ONLY THE START OF A POSTCODE GOES TO postcodes.io WHILE TYPING (audit M-6, 2026-11-09): this box sent any 2-8 letters and
  // digits, so a place name typed here left the page before anyone pressed Enter.
  const before = acAsked.length;
  for (const words of ['Hounslow', 'Flat 3', 'kew']) {
    await sg.fill('#search-input', '');
    await sg.fill('#search-input', words);
    await sg.waitForTimeout(700); // past the 250 ms pause and a lookup's time to leave
  }
  const sentWords = acAsked.slice(before);
  check('a place name or "Flat 3" typed into the box is never sent while typing', sentWords.length === 0 && acAsked.includes('SW59'),
    `sent: ${JSON.stringify(sentWords)}; asked before: ${JSON.stringify(acAsked.slice(0, before))}`);
  await sg.fill('#search-input', '');
  await sg.waitForTimeout(300);

  await sg.fill('#search-input', 'SW5 9HP');
  await sg.press('#search-input', 'Enter');
  await sg.waitForTimeout(1200);
  const afterPause = await listOpen();
  check('Enter inside the pause: the list stays closed', !afterPause, afterPause ? 'the list opened over the answer' : '');

  await sg.fill('#search-input', '');
  await sg.waitForTimeout(300);
  holdNext = true;
  const arrived = new Promise((r) => { heldArrived = r; });
  await sg.fill('#search-input', 'SW5 9HP');
  const wasHeld = await Promise.race([arrived.then(() => true), new Promise((r) => setTimeout(() => r(false), 5000))]);
  await sg.press('#search-input', 'Enter');
  if (held) await json(held, { status: 200, result: ['SW5 9HP'] });
  await sg.waitForTimeout(800);
  const afterHeld = await listOpen();
  check('Enter while suggestions are on their way: the list stays closed', wasHeld && !afterHeld,
    !wasHeld ? 'the suggestion request never went out, so this case was not reached' : afterHeld ? 'the late suggestions opened over the answer' : '');
  check('no page errors around the suggestions', sgErrors.length === 0, sgErrors.slice(0, 2).join(' | '));
  await sg.close();

  // THE PILLS SAY WHAT THEY MEAN, AND A LATE ANSWER KEEPS THE VISITOR'S PLACE (audit I-3 and I-4, 2026-11-09).
  // I-3 (WCAG 1.4.1): a pill to watch and a good one differed only by a dot's colour; now a group label in words, a mark's
  // shape and the button's own name say it (Bill's pick A, 2026-11-10). I-4 (WCAG 2.4.3): in London, Transport and
  // Healthcare are drawn from the council's rating, then again when TfL and the NHS answer, and every redraw replaced
  // the slot and every pill: an opened tile shut and a keyboard user was sent to <body>. Both answers are HELD here, so the
  // redraw happens on purpose while the focus is where a visitor put it.
  const lt = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const ltErrors = [];
  lt.on('pageerror', (e) => ltErrors.push(e.message));
  const gate = () => {
    let open = () => {};
    const shut = new Promise((r) => { open = r; });
    return { shut, open: () => open() };
  };
  const nhsGate = gate();
  const tflGate = gate();
  await lt.route('**/v1/environment**', (r) => json(r, environmentWith({ roadNoiseLdenDb: 71.8 })));
  await lt.route('**/transport?**', async (r) => {
    await tflGate.shut;
    await json(r, { stations: [{ name: "Earl's Court Underground Station", distance: 376, lines: ['district'] }], lineStatus: [] }).catch(() => {});
  });
  await lt.route('**/nhs?**', async (r) => {
    await nhsGate.shut;
    await json(r, { gp: [{ name: 'Brompton Medical Centre', distance: 49 }], pharmacies: [], hospitals: [] }).catch(() => {});
  });
  await lt.route('**/sold-prices?**', (r) => json(r, { transactions: [] }));
  await lt.route('**/epc?**', (r) => json(r, { available: false }));
  await lt.goto(url, { waitUntil: 'domcontentloaded' });
  await lt.waitForTimeout(2500);
  await lt.evaluate((city) => window.switchCity(city), 'london');
  await lt.waitForTimeout(1200);
  await lt.fill('#search-input', 'SW5 9HP');
  await lt.press('#search-input', 'Enter');
  const drawnEarly = await lt.waitForFunction(() => document.querySelector('#ac-pills:not([hidden]) button')
    && document.querySelector('[data-find="healthcare"] details.tile') && document.querySelector('[data-find="transport"] details.tile'), null, { timeout: 8000 })
    .then(() => true, () => false);

  const pills = await lt.evaluate(() => {
    const box = document.getElementById('ac-pills');
    let group = null;
    const out = [];
    for (const el of box.children) {
      if (el.classList.contains('ac-pill-lab')) group = { words: el.textContent, hidden: el.getAttribute('aria-hidden') };
      else if (el.matches('button.ac-pill')) {
        const mark = el.querySelector('svg.ac-mark');
        out.push({
          stand: el.classList.contains('watch') ? 'watch' : el.classList.contains('good') ? 'good' : null,
          name: el.textContent.replace(/\s+/g, ' ').trim(),
          // What a sighted reader sees: innerText would keep the clipped .sr-only words, so they are taken out by hand.
          seen: (() => {
            const c = el.cloneNode(true);
            c.querySelectorAll('.sr-only').forEach((s) => s.remove());
            return c.textContent.replace(/\s+/g, ' ').trim();
          })(),
          group,
          mark: mark ? { d: [...mark.querySelectorAll('path')].map((p) => p.getAttribute('d')).join(' '), w: mark.getBoundingClientRect().width, hidden: mark.getAttribute('aria-hidden') } : null,
        });
      }
    }
    return out;
  });
  const WORDS = { watch: 'Worth a look', good: 'Good here' };
  const SHAPE = { watch: /^M7 3\.6v4\.3$/, good: /^M4\.3 7\.2/ };
  check('the card has pills to read (case reached)', drawnEarly && pills.length > 0, drawnEarly ? '' : 'the card, its pills or the two tiles never drew');
  check('every pill sits under a label that says what it means, in words', pills.every((p) => p.stand && p.group && p.group.words === WORDS[p.stand] && p.group.hidden === 'true'), JSON.stringify(pills));
  check('every pill\'s name says it too, after what it shows ("Crime, good here")', pills.every((p) => p.name === `${p.seen}, ${WORDS[p.stand].toLowerCase()}`), JSON.stringify(pills.map((p) => [p.seen, p.name])));
  check('every pill carries its mark, a shape that differs by meaning', pills.every((p) => p.mark && p.mark.w >= 12 && p.mark.hidden === 'true' && SHAPE[p.stand].test(p.mark.d)), JSON.stringify(pills.map((p) => p.mark)));

  // A tile opened, the focus inside it, then the NHS answers and the tile is drawn again from the real list.
  // textContent, not innerText: a CLOSED tile's innerText is its face alone, and a redraw may change only what it opens to.
  const tileText = (k) => lt.evaluate((key) => document.querySelector(`[data-find="${key}"]`)?.textContent || '', k);
  const healthBefore = await tileText('healthcare');
  await lt.evaluate(() => {
    const t = document.querySelector('[data-find="healthcare"] details.tile');
    t.open = true;
    t.querySelector('summary').focus();
  });
  nhsGate.open();
  const healthRedrawn = await lt.waitForFunction((b) => (document.querySelector('[data-find="healthcare"]')?.textContent || '') !== b, healthBefore, { timeout: 8000 })
    .then(() => true, () => false);
  const tileKept = await lt.evaluate(() => {
    const t = document.querySelector('[data-find="healthcare"] details.tile');
    return { open: Boolean(t?.open), focus: document.activeElement === t?.querySelector('summary'), on: document.activeElement?.tagName };
  });
  check('a tile redrawn by a late answer stays open, with the focus still in it', healthRedrawn && tileKept.open && tileKept.focus,
    !healthRedrawn ? 'the NHS answer never redrew the tile, so this case was not reached' : JSON.stringify(tileKept));

  // The focus on a pill, then TfL answers: the transport tile is drawn again, and the card tidied with it.
  const pillKey = await lt.evaluate(() => {
    const b = document.querySelector('#ac-pills button');
    b.focus();
    return b.dataset.pillKey;
  });
  const transportBefore = await tileText('transport');
  tflGate.open();
  const transportRedrawn = await lt.waitForFunction((b) => (document.querySelector('[data-find="transport"]')?.textContent || '') !== b, transportBefore, { timeout: 8000 })
    .then(() => true, () => false);
  const pillKept = await lt.evaluate((key) => {
    const a = document.activeElement;
    const same = [...document.querySelectorAll('#ac-pills button')].find((b) => b.dataset.pillKey === key);
    return { inPills: Boolean(a?.closest('#ac-pills')), same: same ? a === same : null, on: a?.tagName };
  }, pillKey);
  check('a late answer leaves the keyboard on the pill it was on', transportRedrawn && pillKept.inPills && pillKept.same !== false,
    !transportRedrawn ? 'the TfL answer never redrew the tile, so this case was not reached' : JSON.stringify(pillKept));
  check('no page errors around late answers', ltErrors.length === 0, ltErrors.slice(0, 2).join(' | '));
  await lt.close();

  // A PROFILE CHANGE SAYS ITS SCORE AND KEEPS THE DETAIL; THE SCHOOLS STRIP FITS 320 PX (audit M-12, M-1, M-13, 2026-11-09).
  // M-12 (WCAG 4.1.3): the redraw announced "Results loaded for SW5 9HP", never the new score. M-1: the redraw is a new
  // request object for the same search, and a late answer to the first one wiped the answers the redraw had (reached here
  // by holding the FIRST TfL answer until after the profile change). M-13: five unbroken rating words needed ~266 px in a
  // ~246 px tile at 320.
  const nw = await browser.newPage({ viewport: { width: 320, height: 800 } });
  const nwErrors = [];
  nw.on('pageerror', (e) => nwErrors.push(e.message));
  const firstTfl = gate();
  let tflCalls = 0;
  await nw.route('**/v1/environment**', (r) => json(r, environmentWith({ roadNoiseLdenDb: 71.8 })));
  await nw.route('**/transport?**', async (r) => {
    tflCalls += 1;
    if (tflCalls === 1) await firstTfl.shut;
    await json(r, { stations: [{ name: "Earl's Court Underground Station", distance: 376, lines: ['district'] }], lineStatus: [] }).catch(() => {});
  });
  await nw.route('**/nhs?**', (r) => json(r, { gp: [{ name: 'Brompton Medical Centre', distance: 49 }], pharmacies: [{ name: 'Boots', distance: 120 }], hospitals: [] }));
  await nw.route('**/sold-prices?**', (r) => json(r, { transactions: [] }));
  await nw.route('**/epc?**', (r) => json(r, { available: false }));
  await nw.goto(url, { waitUntil: 'domcontentloaded' });
  await nw.waitForTimeout(2500);
  await nw.evaluate((city) => window.switchCity(city), 'london');
  await nw.waitForTimeout(1200);
  await nw.fill('#search-input', 'SW5 9HP');
  await nw.press('#search-input', 'Enter');
  const picture = () => nw.evaluate(() => document.querySelector('#detail-near svg')?.getAttribute('aria-label') || '');
  const nhsDrawn = await nw.waitForFunction(() => /pharmac/i.test(document.querySelector('#detail-near svg')?.getAttribute('aria-label') || '')
    && document.querySelector('[data-persona-chip][aria-pressed="false"]'), null, { timeout: 15000 }).then(() => true, () => false);
  const said = await nw.evaluate(() => {
    document.querySelector('[data-persona-chip][aria-pressed="false"]').click();
    return new Promise((done) => setTimeout(() => done(document.getElementById('result-status')?.textContent || ''), 400));
  });
  check('a profile change says the new score, not "Results loaded"', /out of 10 for .+ buyer profile\.$/.test(said), JSON.stringify(said));
  firstTfl.open();
  await nw.waitForTimeout(1500);
  const after = await picture();
  check('a late answer to the search before a profile change keeps what the redraw had', nhsDrawn && tflCalls >= 1 && /pharmac/i.test(after),
    !nhsDrawn ? 'the NHS lane never drew, so this case was not reached' : `${tflCalls} TfL calls; picture now: ${after}`);

  const strip = await nw.evaluate(() => {
    const tile = document.querySelector('[data-find="schools"] details.tile');
    if (!tile) return null;
    tile.open = true;
    const s = tile.querySelector('.t-strip');
    if (!s) return { none: true };
    const body = tile.querySelector('.t-body').getBoundingClientRect();
    const r = s.getBoundingClientRect();
    const spans = [...s.querySelectorAll('span')];
    return {
      words: spans.map((x) => x.textContent),
      overStrip: s.scrollWidth - s.clientWidth,
      pastTile: Math.round(r.right - body.right),
      overWord: spans.filter((x) => x.scrollWidth > x.clientWidth + 1).map((x) => x.textContent),
    };
  });
  check('at 320 px the Schools strip fits its tile, every word inside its box', strip && !strip.none && strip.words.length === 5
    && strip.overStrip <= 0 && strip.pastTile <= 0 && strip.overWord.length === 0, JSON.stringify(strip));
  check('no page errors at 320 px', nwErrors.length === 0, nwErrors.slice(0, 2).join(' | '));
  await nw.close();
  console.log('');
}

check('no page errors', errors.length === 0, errors.slice(0, 2).join(' | '));

await browser.close();
if (!TARGET) server.close();

if (failures.length) {
  console.error(`\nFAIL: ${failures.length} check(s) failed`);
  for (const f of failures) console.error(`  - ${f}`);
  process.exit(1);
}
console.log('\nOK: every UK city gets UK content, NYC keeps its own\n');
