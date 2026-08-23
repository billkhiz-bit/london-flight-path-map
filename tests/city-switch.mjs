/**
 * Click EVERY city chip and assert the city actually renders.
 *
 * Why this exists
 * ---------------
 * Nothing in the suite had ever clicked a city chip, and on 2026-08-11 two
 * separate defects were sitting behind that gap on the live site — both shipped
 * on 2026-08-10 with the six Core Cities regions, both invisible to every gate:
 *
 *   1. `center` and `scale` lived in a SECOND registry (`CITIES`) that held
 *      three cities while `CITY_DATA` held nine. Selecting any of the six threw
 *      "Cannot read properties of undefined (reading 'center')" inside
 *      switchCity(), so the title changed and the map did not.
 *   2. The five new cities' corridors were ported from the score Lambda, which
 *      names that key `coords`; the frontend renderer reads `.coordinates`.
 *      Fixing (1) revealed (2) — the second throw was hidden behind the first.
 *
 * Neither was a data problem. Every borough's SCORES had been compared
 * site-vs-Lambda before those cities shipped, and all thirty agreed. What was
 * never checked was whether a user could get to the city at all.
 *
 * What it asserts, and why each one
 * ---------------------------------
 *   - zero page errors while switching     — (1) and (2) were both uncaught
 *                                             throws; nothing else notices one
 *   - borough outlines are drawn           — the throw left the map EMPTY while
 *                                             every label around it read right,
 *                                             so "the page still looks fine" is
 *                                             not evidence
 *   - the count matches the registry        — a city rendering ANOTHER city's
 *                                             outlines is the failure the
 *                                             registry refactor was for, and a
 *                                             bare "> 0" cannot see it
 *
 * It is DATA-DRIVEN off CITY_DATA on purpose. tests/smoke-local.mjs carries a
 * hardcoded three cities and a comment admitting the number is load-bearing;
 * that number was three while the app had nine. City ten needs no edit here.
 *
 *   node tests/city-switch.mjs
 *   node tests/city-switch.mjs https://skyscore.co.uk/   (verify a deploy)
 *
 * With no argument it serves the working tree, which is what preflight runs and
 * what gates a deploy. Given a URL it checks that URL instead, so the same
 * assertions confirm production afterwards — the defects this file exists for
 * were LIVE for a day, and "the upload succeeded" is not evidence that the
 * cities work.
 */
import { chromium } from '@playwright/test';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';

const ROOT = process.cwd();
// 8123 (smoke-local), 8921 (locator), 8922 (selector-widths) and 8923
// (a11y-source) are taken, and preflight runs these in one block — sharing a
// port makes this harness die with EADDRINUSE, which reads as a city failure
// and is not one.
const PORT = 8924;
const TYPES = {
  '.html': 'text/html',
  '.js': 'text/javascript',
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
    // Read BEFORE writing the header: writing first and then failing the read
    // kills the harness with ERR_HTTP_HEADERS_SENT instead of serving a 404.
    // Same copied server, same note, as locator-verify.mjs.
    const body = await readFile(p);
    res.writeHead(200, { 'content-type': TYPES[extname(p)] || 'application/octet-stream' });
    res.end(body);
  } catch {
    res.writeHead(404).end();
  }
});
// Only bind the local server when it is the thing being tested. Starting it
// against a remote target would be a port collision waiting to happen for no
// benefit.
if (!TARGET) await new Promise((r) => server.listen(PORT, r));
const url = TARGET || `http://localhost:${PORT}/index.html`;

// TWO VIEWPORTS, added 2026-08-23. This file ran at 1440x900 only, so from
// the day it was written - to catch six cities that threw on selection - it had
// never switched a city on a phone. The mobile layout is not a narrower copy of
// the desktop one: it has a scroll strip, a bottom sheet, a popover for the
// layer toggles and a collapsed legend, all driven by JavaScript that does not
// run above 900px. A throw in any of that is invisible here at 1440.
//
// Phone first is deliberate. If both are going to fail, the phone failure is
// the one worth reading first, because it is the one nothing else covers.
const VIEWPORTS = [
  { width: 390, height: 844, label: 'phone 390x844' },
  { width: 1440, height: 900, label: 'desktop 1440x900' },
];

const browser = await chromium.launch();
const errors = [];

const openAt = async (vp) => {
  const context = await browser.newContext({
    viewport: { width: vp.width, height: vp.height },
    isMobile: vp.width < 900,
    hasTouch: vp.width < 900,
  });
  const pg = await context.newPage();
  pg.on('pageerror', (e) => errors.push(e.message));
  pg.on('console', (m) => {
    if (m.type() === 'error') errors.push('console: ' + m.text().slice(0, 140));
  });
  await pg.goto(url, { waitUntil: 'domcontentloaded' });
  await pg.waitForTimeout(3000);
  return { context, pg };
};

// The city list is identical at every viewport - it is read out of CITY_DATA
// and each city's own boundary file - so derive it once on the first page.
let { context, pg: page } = await openAt(VIEWPORTS[0]);

// The expected borough count comes from the city's own boundary file, fetched
// in the page. Hardcoding the counts here would make this test a second holder
// of exactly the thing the registry refactor removed a second holder of.
//
// `boundaries` is an ORDERED FALLBACK LIST, not a union — loadCityBoundaries()
// returns the first URL that yields features and stops. NYC declares two (a
// local file and a remote GeoJSON), so summing them expected 10 outlines for a
// 5-borough city and failed a city that was rendering perfectly. Mirror the
// loader's own semantics.
const cities = await page.evaluate(async () => {
  const out = [];
  for (const [id, data] of Object.entries(CITY_DATA)) {
    let expected = 0;
    for (const url of data.boundaries) {
      try {
        const res = await fetch(url);
        if (!res.ok) continue;
        const gj = await res.json();
        const feats = gj.features || gj;
        if (feats && feats.length) {
          expected = feats.length;
          break;
        }
      } catch {
        // Same as the loader: try the next source rather than failing the city.
      }
    }
    out.push({ id, label: data.label, country: data.country, expected });
  }
  return out;
});

console.log(`\nCity switch: ${cities.length} cities from CITY_DATA at ${url}`);

let fail = 0;
for (const vp of VIEWPORTS) {
  if (vp !== VIEWPORTS[0]) {
    await context.close();
    ({ context, pg: page } = await openAt(vp));
  }
  console.log(`\n--- ${vp.label} ---`);
  for (const city of cities) {
  errors.length = 0;

  // Switch countries through the tab, the way a user does — the chips for a
  // country do not exist in the DOM until its tab is active.
  await page.evaluate((c) => switchCountry(c), city.country);
  await page.waitForTimeout(400);

  const chip = page.locator(`.city-btn[data-city="${city.id}"]`);
  const chipCount = await chip.count();
  if (chipCount !== 1) {
    console.log(`FAIL  ${city.label.padEnd(20)} no chip in the ${city.country} tab`);
    fail += 1;
    continue;
  }

  // force: true because a chip can legitimately sit outside the visible part of
  // the mobile scroll strip. Reachability is tests/responsive.mjs's job; this
  // test is about what happens AFTER the click.
  await chip.click({ force: true });
  await page.waitForTimeout(1800);

  const state = await page.evaluate(() => ({
    current: typeof currentCity === 'string' ? currentCity : null,
    boroughs: document.querySelectorAll('#map-svg path.borough').length,
    subtitle: document.getElementById('map-subtitle')?.textContent?.trim() || '',
  }));

  const problems = [];
  if (state.current !== city.id) problems.push(`currentCity is ${state.current}`);
  // A FLOOR, because `expected` is derived by fetching the city's own boundary
  // sources IN THE PAGE, and loadCityBoundaries() swallows an unparseable
  // source with console.warn and returns []. So when a boundary file is served
  // as 200 + non-JSON - the shape a CloudFront error page takes, and the exact
  // gitignore trap CLAUDE.md names as the #1 hazard when adding a city - both
  // sides collapse to 0 together and 0 === 0 passes. Proven: a city whose map
  // drew nothing reported `ok`. An expectation read from the thing under test
  // cannot disagree with it; a floor can.
  if (!city.expected) {
    problems.push('boundary file resolved to 0 outlines - source missing or unparseable');
  }
  if (state.boroughs !== city.expected) {
    problems.push(`${state.boroughs} outlines drawn, boundary file has ${city.expected}`);
  }
  if (errors.length) problems.push(`page error: ${errors[0].slice(0, 100)}`);

  if (problems.length) {
    fail += 1;
    console.log(`FAIL  ${city.label.padEnd(20)} ${problems.join(' | ')}`);
  } else {
    console.log(
      `ok    ${city.label.padEnd(20)} ${String(state.boroughs).padStart(2)} outlines · ${state.subtitle.slice(0, 34)}`
    );
  }
  }
}

await context.close();
await browser.close();
if (!TARGET) server.close();

console.log(
  fail === 0
    ? `\nAll ${cities.length} cities switch and render at ${VIEWPORTS.length} viewports ` +
      `(${cities.length * VIEWPORTS.length} switches).`
    : `\n${fail} of ${cities.length * VIEWPORTS.length} city/viewport combinations fail to ` +
      `switch or render.`
);
process.exit(fail === 0 ? 0 : 1);
