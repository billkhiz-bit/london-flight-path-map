/**
 * Aircraft-noise report for ONE postcode, as a three-page PDF, the answer first (Bill's pick 2026-11-11 v2, built
 * 2026-11-12): page 1 the cards, key figures, map and details; page 2 the aircraft and road detail; page 3 the air and the
 * notes, in bigger type. One page until 2026-11-11, two (Bill's pick C) for a day. A fourth page is refused.
 *
 *   node scripts/address_noise_report.mjs --postcode "TW9 3PZ" --place "Kew" \
 *     --sample --out ~/OneDrive/Desktop/aircraft-noise-report.pdf
 *
 * WHY THIS EXISTS (2026-10-02). Geovation's advice was to narrow to the
 * flight-path niche and to test paid reports. `area_summary.mjs` is the free
 * community sheet (air and road noise across an area); this is the business
 * one: what the official map and the published routes say about one postcode.
 * See ROADMAP "Monetisation, ranked". It is a SAMPLE generator until the gates
 * recorded there are met (licence for the route data, insurance, the rename).
 *
 * WHERE EVERY NUMBER COMES FROM, so nothing on the page is typed by hand:
 *   - aircraft and road noise, NO2, PM2.5: the LIVE /v1/environment endpoint;
 *   - flight routes: data/flight-procedures.json, the UK AIP record that
 *     build_flight_paths.py generates the map's lines from. A final approach
 *     is the same line the builder draws: threshold, true bearing and glide
 *     angle, out to FINAL_TOP_FT;
 *   - the noise picture on the map: the DEFRA PNG the site paints, placed by
 *     the bbox the site holds for it, with DEFRA's band colours; both are
 *     held in js/street_report.mjs and COMPARED with index.html's holders
 *     (NOISE_SCALE_DEFRA_LDEN, LONDON_AIRCRAFT_BBOX) on every run;
 *   - the district comparison: the per-postcode Quiet Skies datasets the site
 *     ships, limited to LIVE postcodes (postcodes.io), because those files
 *     keep terminated ones;
 *   - the 2021-vs-a-normal-year caveat (the CAA's latest Heathrow contours): data/covid-understatement.json.
 *
 * WHAT IT DELIBERATELY DOES NOT SAY. How OFTEN aircraft pass, except through
 * js/planes.mjs from data/planes/ (since 2026-11-11, the planes chart every surface
 * draws), never a figure of its own; not N65, which this product does not hold.
 * Any adjective for the level ("severe",
 * "acceptable"): the page compares with the WHO guideline and stops there.
 * A height for departures: the AIP record carries none.
 * No em dashes in the output, matching the site's rule.
 *
 * THE PAGE ITSELF IS IN js/street_report.mjs since 2026-10-06, shared with the
 * browser page /reports/street/ that lets a visitor make their own (free for
 * your own home, Bill's ruling). This script is the Node half: it reads the
 * inputs off the disk and prints the page to PDF with Playwright.
 */
import { chromium } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { readFile, rename, unlink, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

import { plane, routesNear } from '../js/flight_geometry.mjs';
import {
  DEFRA_LDEN_SCALE,
  LONDON_RASTER,
  ROUTE_RADIUS_KM,
  SCOPE_KM,
  checkLink,
  districtComparison,
  mapSvg,
  nearestMonitor,
  nearestSensor,
  nearestStation,
  rasterFor,
  reportDocument,
  reportReference,
} from '../js/street_report.mjs';
import { districtOf, planesModel } from '../js/planes.mjs';

const API = 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/environment';

function args(argv) {
  const out = { sample: false };
  for (let i = 2; i < argv.length; i++) {
    const [k, v] = [argv[i], argv[i + 1]];
    if (k === '--postcode') ((out.postcode = v), i++);
    else if (k === '--place') ((out.place = v), i++);
    else if (k === '--out') ((out.out = v), i++);
    else if (k === '--sample') out.sample = true;
    else if (k === '--keep-html') out.keepHtml = true;
    else throw new Error(`unknown argument ${k}`);
  }
  if (!out.postcode) throw new Error('usage: --postcode "TW9 3PZ" [--place "Kew"] [--sample] [--out file.pdf]');
  out.postcode = out.postcode.trim().toUpperCase();
  // The same filter the score Lambda applies before a postcode reaches a URL path.
  if (!/^[A-Z0-9 ]{5,8}$/.test(out.postcode)) throw new Error(`"${out.postcode}" is not a postcode`);
  out.out = resolve(out.out || `aircraft-noise-${out.postcode.replace(/\s+/g, '').toLowerCase()}.pdf`);
  return out;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---- sources ---------------------------------------------------------------
async function lookup(postcode) {
  const r = await fetch(`https://api.postcodes.io/postcodes/${encodeURIComponent(postcode)}`);
  if (r.status === 404) throw new Error(`postcodes.io does not know ${postcode}`);
  if (!r.ok) throw new Error(`postcodes.io answered ${r.status}`);
  return (await r.json()).result;
}
async function environment(lat, lon) {
  const r = await fetch(`${API}?lat=${lat}&lon=${lon}`);
  if (!r.ok) throw new Error(`/v1/environment answered ${r.status}`);
  return r.json();
}
/** Which of these postcodes are live. The quiet datasets keep terminated ones. */
async function livePostcodes(codes) {
  const live = new Set();
  for (let i = 0; i < codes.length; i += 100) {
    const r = await fetch('https://api.postcodes.io/postcodes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ postcodes: codes.slice(i, i + 100) }),
    });
    if (!r.ok) throw new Error(`postcodes.io bulk lookup answered ${r.status}`);
    for (const row of (await r.json()).result) if (row.result) live.add(row.query);
    await sleep(150);
  }
  return live;
}
const readJson = async (p) => JSON.parse(await readFile(resolve(p), 'utf8'));

/**
 * The module's two mirrors of index.html, compared before anything is printed:
 * DEFRA's band colours (the site's legend reads NOISE_SCALE_DEFRA_LDEN) and
 * London's picture box (LONDON_AIRCRAFT_BBOX). Until 2026-10-06 this script read
 * them out of index.html directly; the browser cannot, so the module holds them
 * and this refuses to print on any difference.
 */
function checkMirrors(indexHtml) {
  const block = /const NOISE_SCALE_DEFRA_LDEN = \[([\s\S]*?)\]/.exec(indexHtml);
  const bands = [...(block ? block[1] : '').matchAll(/from:\s*(\d+),\s*colour:\s*'(#[0-9A-Fa-f]{6})'/g)].map((m) => ({
    from: Number(m[1]),
    colour: m[2],
  }));
  if (bands.length < 5) throw new Error('NOISE_SCALE_DEFRA_LDEN not found in index.html - the legend holder has moved');
  if (JSON.stringify(bands) !== JSON.stringify(DEFRA_LDEN_SCALE))
    throw new Error('DEFRA_LDEN_SCALE in js/street_report.mjs differs from NOISE_SCALE_DEFRA_LDEN in index.html');
  const m = /const LONDON_AIRCRAFT_BBOX = \{([\s\S]*?)\}/.exec(indexHtml);
  if (!m) throw new Error('LONDON_AIRCRAFT_BBOX not found in index.html - the holder has moved');
  const london = Object.fromEntries([...m[1].matchAll(/(\w+):\s*(-?[\d.]+)/g)].map((x) => [x[1], Number(x[2])]));
  if (JSON.stringify(london) !== JSON.stringify(LONDON_RASTER.bbox))
    throw new Error('LONDON_RASTER in js/street_report.mjs differs from LONDON_AIRCRAFT_BBOX in index.html');
}

// ---- run -------------------------------------------------------------------
const spec = args(process.argv);
const loc = await lookup(spec.postcode);
const envBody = await environment(loc.latitude, loc.longitude);
const env = envBody.environment || {};
// The endpoint reverse-geocodes a coordinate, so it can answer for a
// neighbour. That goes ON THE PAGE, never only in the terminal.
const resolvedAs = envBody.location && envBody.location.postcode !== loc.postcode ? envBody.location.postcode : null;
if (resolvedAs)
  console.error(`note: /v1/environment answered for ${resolvedAs}, the postcode nearest ${loc.postcode}'s centre`);

checkMirrors(await readFile(resolve('index.html'), 'utf8'));
const proc = await readJson('data/flight-procedures.json');
const pl = plane(loc.latitude, loc.longitude);
const routes = routesNear(proc, pl, SCOPE_KM);
const raster = rasterFor(await readJson('data/aircraft-noise-rasters.json'), loc.latitude, loc.longitude);
// Area outlines for the raster's city and every city the nearest airport
// serves (East Midlands serves two). Keyed on the airport as well as the
// raster because Norwich and Teesside have no DEFRA aircraft map at all, and
// a map with no outlines gives the reader nothing to place the pin against.
const home = routes.airports[0];
const outlineCities = new Set([
  ...(raster ? [raster.city] : []),
  ...(home && home.dist <= SCOPE_KM ? proc.airports[home.code].cities : []),
]);
const boroughs = { features: [] };
for (const city of outlineCities) {
  const file = resolve(`data/${city}-boroughs.json`);
  if (existsSync(file)) boroughs.features.push(...(await readJson(file)).features);
}
const quiet = {
  ...(await readJson('data/aircraft-quiet-london.json')).quiet,
  ...(await readJson('data/aircraft-quiet-regions.json')).quiet,
};
const district = await districtComparison(quiet, loc.outcode, env.aircraftQuiet, livePostcodes);
// PLANES OVERHEAD (Bill's pick C, 2026-11-11), read through js/planes.mjs as every surface reads them. The airports'
// rules and the layer's steps must be here (planes-deploy builds them): without them the report would drop its chart
// in silence, so it refuses. A district with no file of its own is not counted, and the report says nothing of planes.
for (const need of ['data/planes/airports.json', 'data/planes-layer/index.json']) {
  if (!existsSync(resolve(need))) throw new Error(`${need} is missing: build the planes files before printing a report`);
}
const planesInfo = await readJson('data/planes/airports.json');
const planesFile = resolve(`data/planes/${districtOf(loc.postcode)}.json`);
const planesHere = existsSync(planesFile) ? planesModel(await readJson(planesFile), planesInfo, loc.postcode) : null;
const layerSteps = (await readJson('data/planes-layer/index.json')).steps || [];

// THE REFERENCE AND CHECK LINK the free copy carries (js/street_report.mjs, one holder), for the day in UTC as the free
// copy takes it, so a firm's copy can be checked at /reports/street/ exactly as a resident's can (2026-11-12).
const made = new Date().toISOString().slice(0, 10);
const ref = await reportReference(loc.postcode, made, proc.airac, env, planesHere);
const html = reportDocument(
  { ...spec, made, ref, check: checkLink(loc.postcode, made, ref) },
  {
    postcode: loc.postcode,
    council: loc.admin_district,
    hasRaster: Boolean(raster),
    resolvedAs,
    notices: envBody.notices,
    env,
    provenance: envBody.provenance,
    planes: { model: planesHere, steps: layerSteps },
    routes,
    district,
    covid: await readJson('data/covid-understatement.json'),
    // The nearest station, as the free report shows it (one holder: nearestStation).
    station: existsSync(resolve('data/stations.json')) ? nearestStation(await readJson('data/stations.json'), loc.latitude, loc.longitude) : null,
    // The air measured nearby, as the free report shows it (one holder each: nearestSensor, nearestMonitor).
    sensor: existsSync(resolve('data/breathe-london-sensors.json'))
      ? nearestSensor(await readJson('data/breathe-london-sensors.json'), loc.latitude, loc.longitude)
      : null,
    monitor: existsSync(resolve('data/aurn-sites.json')) ? nearestMonitor(await readJson('data/aurn-sites.json'), loc.latitude, loc.longitude) : null,
    airac: proc.airac,
    map: mapSvg({
      pl,
      routes,
      raster,
      boroughs,
      scale: DEFRA_LDEN_SCALE,
      label: loc.postcode,
      imageHref: (png) => pathToFileURL(resolve(png)).href,
    }),
  },
  pathToFileURL(resolve('fonts/geist.woff2')).href
);
if (html.includes(String.fromCharCode(0x2014))) throw new Error('em dash in output');
const htmlPath = spec.out.replace(/\.pdf$/i, '.html');
await writeFile(htmlPath, html, 'utf8');

const browser = await chromium.launch();
try {
  const pg = await browser.newPage();
  await pg.goto(pathToFileURL(htmlPath).href, { waitUntil: 'load' });
  const tmp = spec.out.replace(/\.pdf$/i, '.NEW.pdf');
  const pdf = await pg.pdf({ path: tmp, format: 'A4', printBackground: true, preferCSSPageSize: true, tagged: true });
  // It is sold as three fixed pages (Bill's pick, 2026-11-11 v2; built 2026-11-12): the answer, the noise detail, the air
  // and the notes. Count the page objects rather than trusting the layout. A fourth page is REFUSED: the new file is
  // removed and the last good one left where it was (audit M-8, 2026-11-12: it used to be written over it, then exit 1).
  const pages = (pdf.toString('latin1').match(/\/Type\s*\/Page[^s]/g) || []).length;
  // No text under 8 pt, chart labels included (Bill's rule for the three-page build), measured on the printed file by
  // the one holder, scripts/report_text_floor.py (audit M-6, 2026-11-13). Refused the same way as a fourth page; a
  // floor that could not be measured refuses too, because an unmeasured report is not a checked one.
  let floorFault = null;
  if (pages <= 3) {
    try {
      execFileSync('python', [resolve('scripts/report_text_floor.py'), tmp], { encoding: 'utf8', stdio: 'pipe' });
    } catch (e) {
      floorFault =
        e.status === 1
          ? `the report has text under 8 pt (${(e.stdout || '').trim()}) - fit it before sending`
          : `the 8 pt floor could not be measured (${(e.stderr || e.message || '').trim().split('\n').pop()})`;
    }
  }
  if (pages > 3) {
    console.error(`the report ran to ${pages} pages, not 3 - fit it before sending; ${spec.out} was left as it was`);
    process.exitCode = 1;
    await unlink(tmp).catch(() => {});
  } else if (floorFault) {
    console.error(`${floorFault}; ${spec.out} was left as it was`);
    process.exitCode = 1;
    await unlink(tmp).catch(() => {});
  } else {
    try {
      await rename(tmp, spec.out);
    } catch (e) {
      console.error(`Could not replace ${spec.out} - close it in any PDF viewer and re-run. (${e.code})`);
      process.exitCode = 1;
    }
  }
} finally {
  await browser.close();
  // The page the PDF was printed from is a working file. Left beside a PDF written into home/reports/, home-deploy's
  // `--include "*.html"` would publish it as /reports/<name>.html (2026-11-11, caught before a deploy): gone unless asked for.
  if (!spec.keepHtml) await unlink(htmlPath).catch(() => {});
}
const listed =
  routes.finals.filter((x) => x.dist <= ROUTE_RADIUS_KM).length +
  routes.departures.filter((x) => x.dist <= ROUTE_RADIUS_KM).length;
console.log(
  `${loc.postcode} (${loc.admin_district}): aircraft ${typeof env.aircraftNoiseLdenDb === 'number' ? `${env.aircraftNoiseLdenDb} dB on DEFRA's map (modelled)` : 'no DEFRA figure'}, ` +
    `${listed} routes within ${ROUTE_RADIUS_KM} km, district comparison ${district ? `${district.n} live postcodes` : 'none'}\n  ${spec.out}`
);
