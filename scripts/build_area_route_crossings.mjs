// How many routes on the front page's map cross each council area (audit 2026-10-16 I-3).
//
// WHY
// ---
// "Avoid aircraft noise" in Find areas used the council's aircraft band alone, so it offered Bexley,
// under London City's runway 27 final approach, and five London boroughs with London City departures
// across them, at quiet skies 10.0. The card for each of those areas already says which routes cross
// it, computed in the browser by routesAcross() in js/home-engine.mjs. The list needs that count for
// EVERY region at once, and a second copy of the geometry (in Python, say) is how site and API have
// drifted in this repo before. So this runs the page's own function: it serves the working tree, opens
// the front page, and asks routeCrossingsByCity() to draw each UK region the map holds and count.
//
//   node scripts/build_area_route_crossings.mjs           write data/area-route-crossings.json
//   node scripts/build_area_route_crossings.mjs --check   fail if the file is not what the page computes
//
// Offline: every request outside the local server is aborted, and the page needs none. The file records
// the UK AIP cycle its routes come from, so a new cycle reds --check until the file is rewritten.
import { chromium } from 'playwright';
import { createServer } from 'node:http';
import { readFile, writeFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
const OUT = join(ROOT, 'data', 'area-route-crossings.json');
const CHECK = process.argv.includes('--check');
const TYPES = {
  '.html': 'text/html', '.js': 'application/javascript', '.mjs': 'application/javascript', '.json': 'application/json',
  '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2', '.csv': 'text/csv',
};

const server = createServer(async (req, res) => {
  const path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  const file = normalize(join(ROOT, path === '/' ? '/home/index.html' : path));
  if (!file.startsWith(normalize(ROOT))) return res.writeHead(403).end();
  try {
    const body = await readFile(file);
    res.writeHead(200, { 'Content-Type': TYPES[extname(file)] || 'application/octet-stream' });
    res.end(body);
  } catch {
    res.writeHead(404).end();
  }
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const base = `http://127.0.0.1:${server.address().port}`;

const browser = await chromium.launch();
let cities;
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.route((u) => !u.href.startsWith(base), (r) => r.abort());
  await page.goto(`${base}/`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelectorAll('#map .boro').length > 0, null, { timeout: 30000 });
  cities = await page.evaluate(async () => (await import('/js/home-engine.mjs')).routeCrossingsByCity());
  if (errors.length) throw new Error(`page errors: ${errors.join(' | ')}`);
} finally {
  await browser.close();
  server.close();
}

const proc = JSON.parse(await readFile(join(ROOT, 'data', 'flight-procedures.json'), 'utf-8'));
const doc = {
  what: 'For each council area of each UK region the front page draws, how many routes on its map cross the area: '
    + 'routesAcross() in js/home-engine.mjs, the count each area\'s card shows. Read by "avoid aircraft noise" in Find areas.',
  generator: 'node scripts/build_area_route_crossings.mjs',
  routes_from: `UK Aeronautical Information Publication (NATS), AIRAC ${proc.airac}, via data/flight-procedures.json`,
  airac: proc.airac,
  cities,
};
const areas = Object.values(cities).reduce((n, c) => n + Object.keys(c).length, 0);
const crossed = Object.values(cities).reduce((n, c) => n + Object.values(c).filter((v) => v > 0).length, 0);
// A floor, so a page that drew nothing cannot write an empty file: ten regions, about 86 areas.
if (Object.keys(cities).length < 10 || areas < 80) {
  console.error(`FAIL: only ${Object.keys(cities).length} regions and ${areas} areas came back`);
  process.exit(1);
}
const text = `${JSON.stringify(doc, null, 1)}\n`;
if (CHECK) {
  let have = '';
  try { have = await readFile(OUT, 'utf-8'); } catch { /* missing reads as stale */ }
  if (have.replace(/\r\n/g, '\n') !== text) {
    console.error('FAIL: data/area-route-crossings.json is not what the page computes (rerun without --check)');
    process.exit(1);
  }
  console.log(`PASS: ${areas} areas in ${Object.keys(cities).length} regions, ${crossed} crossed by a route on the map`);
} else {
  await writeFile(OUT, text, 'utf-8');
  console.log(`wrote data/area-route-crossings.json: ${areas} areas in ${Object.keys(cities).length} regions, ${crossed} crossed`);
}
