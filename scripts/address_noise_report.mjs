/**
 * Aircraft-noise report for ONE postcode, as a one-page PDF.
 *
 *   node scripts/address_noise_report.mjs --postcode "TW9 3PZ" --place "Kew" \
 *     --sample --out "C:/Users/bilal/OneDrive/Desktop/aircraft-noise-report.pdf"
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
 *   - the 2021-vs-2024 caveat: data/covid-understatement.json.
 *
 * WHAT IT DELIBERATELY DOES NOT SAY. How OFTEN aircraft pass: that is N65,
 * which this product does not hold. Any adjective for the level ("severe",
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
import { existsSync } from 'node:fs';
import { readFile, rename, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

import { plane, routesNear } from '../js/flight_geometry.mjs';
import {
  DEFRA_LDEN_SCALE,
  LONDON_RASTER,
  ROUTE_RADIUS_KM,
  SCOPE_KM,
  districtComparison,
  mapSvg,
  rasterFor,
  reportDocument,
} from '../js/street_report.mjs';

const API = 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/environment';

function args(argv) {
  const out = { sample: false };
  for (let i = 2; i < argv.length; i++) {
    const [k, v] = [argv[i], argv[i + 1]];
    if (k === '--postcode') ((out.postcode = v), i++);
    else if (k === '--place') ((out.place = v), i++);
    else if (k === '--out') ((out.out = v), i++);
    else if (k === '--sample') out.sample = true;
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

const html = reportDocument(
  spec,
  {
    postcode: loc.postcode,
    council: loc.admin_district,
    hasRaster: Boolean(raster),
    resolvedAs,
    notices: envBody.notices,
    env,
    routes,
    district,
    covid: await readJson('data/covid-understatement.json'),
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
  // It is sold as ONE page. Count the page objects rather than trusting the layout.
  const pages = (pdf.toString('latin1').match(/\/Type\s*\/Page[^s]/g) || []).length;
  if (pages !== 1) {
    console.error(`the report ran to ${pages} pages, not 1 - shorten it before sending`);
    process.exitCode = 1;
  }
  try {
    await rename(tmp, spec.out);
  } catch (e) {
    console.error(`Could not replace ${spec.out} - close it in any PDF viewer and re-run. (${e.code})`);
    process.exitCode = 1;
  }
} finally {
  await browser.close();
}
const listed =
  routes.finals.filter((x) => x.dist <= ROUTE_RADIUS_KM).length +
  routes.departures.filter((x) => x.dist <= ROUTE_RADIUS_KM).length;
console.log(
  `${loc.postcode} (${loc.admin_district}): aircraft ${typeof env.aircraftNoiseLdenDb === 'number' ? `${env.aircraftNoiseLdenDb} dB measured` : 'not measured'}, ` +
    `${listed} routes within ${ROUTE_RADIUS_KM} km, district comparison ${district ? `${district.n} live postcodes` : 'none'}\n  ${spec.out}`
);
