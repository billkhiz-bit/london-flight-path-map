// Site vs Lambda, on New York's aircraft quiet, point by point (2026-10-16).
//
// WHY THIS EXISTS
// ---------------
// New York's quiet estimate is FITTED to the Port Authority's noise monitors
// (scripts/measure_us_quiet_yardstick.py): runway lobes, per-airport sizes, its
// own corridor weight and four major airports. The fit is written twice, into
// the score Lambda's CITY_GEOMETRY and into index.html's US_QUIET_NYC, and the
// site re-implements the arithmetic in its two quiet ramps (analysePostcode and
// calcNeighbourhoodScores). The fit script's --check holds the two DATA blocks;
// only running both ramps can hold the ARITHMETIC. borough-score-parity cannot:
// a New York borough scores from its impact band, never from this geometry.
//
// So this runs the Lambda's own calc_postcode_quiet and the page's own ramps
// at the same points - a grid over the five boroughs and every curated New
// York neighbourhood - and fails on any difference. Offline: the page is
// served from the working tree and no third party is asked anything.
import { chromium } from 'playwright';
import { execFileSync } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const PORT = 8937;
const TYPES = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.mjs': 'application/javascript',
  '.json': 'application/json',
  '.css': 'text/css',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.webmanifest': 'application/manifest+json',
};

// A grid at 0.02 deg (about 2 km) over the boroughs and the three airports
// outside them: Newark and Teterboro are in New Jersey, and their lobes reach
// Staten Island and the Bronx.
const GRID = [];
for (let lat = 40.48; lat <= 40.93; lat += 0.02) {
  for (let lon = -74.28; lon <= -73.68; lon += 0.02) GRID.push([+lat.toFixed(4), +lon.toFixed(4)]);
}

const server = http.createServer((req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]);
  if (p === '/') p = '/index.html';
  const file = path.join(ROOT, p);
  if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    res.writeHead(404).end('not found');
    return;
  }
  res.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' });
  fs.createReadStream(file).pipe(res);
});
await new Promise((r) => server.listen(PORT, r));

const browser = await chromium.launch();
const page = await browser.newPage();
const pageErrors = [];
page.on('pageerror', (e) => pageErrors.push(String(e)));
// Nothing offsite: the ramps need no network, and a stalled third party must
// not be able to make this gate flaky.
await page.route(
  (url) => !url.href.startsWith(`http://localhost:${PORT}/`),
  (route) => route.abort()
);
await page.goto(`http://localhost:${PORT}/index.html`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => typeof switchCity === 'function' && typeof CITY_DATA === 'object');

const site = await page.evaluate((grid) => {
  if (typeof switchCountry === 'function') switchCountry(CITY_DATA.nyc.country);
  switchCity('nyc');
  const postcode = grid.map(([lat, lon]) => {
    const a = analysePostcode({ latitude: lat, longitude: lon, admin_district: 'Queens' });
    return Math.max(0, Math.min(10, 10 - a.noiseScore));
  });
  // The neighbourhood ramp, at each neighbourhood's own point, resolved the way
  // calcNeighbourhoodScores resolves it.
  const areaMap = cityOf('nyc').areaMap();
  const detail = cityOf('nyc').neighbourhoodDetail();
  const where = {};
  for (const [name, info] of Object.entries(areaMap)) {
    const nd = detail[name];
    if (!nd) continue;
    const lat = typeof info === 'object' ? info.lat : nd.lat;
    const lon = typeof info === 'object' ? info.lon : nd.lon;
    if (lat && lon) where[name] = [lat, lon];
  }
  const hoods = calcNeighbourhoodScores('nyc')
    .filter((r) => where[r.name])
    .map((r) => ({ name: r.name, lat: where[r.name][0], lon: where[r.name][1], quiet: r.scores.quiet }));
  return { postcode, hoods };
}, GRID);

// The Lambda is the reference: its own calc_postcode_quiet, never a re-reading
// of its data. raster_lden=None asks for the geometry tier alone, which is the
// only tier New York has (DEFRA does not map it).
const PY = `
import json, math, sys
sys.path.insert(0, 'backend/lambdas/score')
import app
pts = json.load(sys.stdin)
q = lambda lat, lon: app.calc_postcode_quiet(lat, lon, 'nyc', raster_lden=None)
print(json.dumps({
    'grid': [q(lat, lon) for lat, lon in pts['grid']],
    # The ranking prints quiet at 1dp; the engine's round_1dp rule, which equals
    # JS Math.round on a non-negative value.
    'hoods': [math.floor(q(h['lat'], h['lon']) * 10 + 0.5) / 10 for h in pts['hoods']],
}))
`;
const lambda = JSON.parse(
  execFileSync('python', ['-c', PY], {
    encoding: 'utf-8',
    cwd: ROOT,
    input: JSON.stringify({ grid: GRID, hoods: site.hoods }),
  })
);

await browser.close();
server.close();

const failures = [];
GRID.forEach(([lat, lon], i) => {
  if (Math.abs(site.postcode[i] - lambda.grid[i]) > 1e-9) {
    failures.push(`point ${lat}, ${lon}: site ${site.postcode[i]} vs Lambda ${lambda.grid[i]}`);
  }
});
site.hoods.forEach((h, i) => {
  if (Math.abs(h.quiet - lambda.hoods[i]) > 1e-9) {
    failures.push(`neighbourhood ${h.name}: site ${h.quiet} vs Lambda ${lambda.hoods[i]}`);
  }
});

// Floors, so a page that silently scored nothing cannot pass: the whole grid,
// a real spread of values (the airports must actually be read), and the
// curated neighbourhoods.
const distinct = new Set(lambda.grid.map((v) => v.toFixed(3))).size;
if (site.postcode.length !== GRID.length) failures.push(`site scored ${site.postcode.length} of ${GRID.length} points`);
if (distinct < 10) failures.push(`only ${distinct} distinct quiet values over the grid: the geometry is not being read`);
if (site.hoods.length < 50) failures.push(`only ${site.hoods.length} New York neighbourhoods compared (floor 50)`);
if (pageErrors.length) failures.push(...pageErrors.map((e) => `page error: ${e}`));

if (failures.length) {
  console.error(`FAIL: New York quiet, site vs Lambda - ${failures.length} problem(s)`);
  for (const f of failures.slice(0, 20)) console.error('  ' + f);
  process.exit(1);
}
console.log(
  `PASS: New York quiet agrees at ${GRID.length} grid points (${distinct} distinct values) ` +
    `and ${site.hoods.length} neighbourhoods`
);
