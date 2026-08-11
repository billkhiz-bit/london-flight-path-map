/**
 * A fill layer must paint exactly the boroughs it has a reading for.
 *
 * Why this exists
 * ---------------
 * On 2026-08-11 the three borough choropleth layers - road noise, flood risk,
 * air quality - each ended their lookup with a fallback:
 *
 *     const level = roadNoiseData[n] || 'moderate';
 *     const risk  = extra?.flood     || 'low';
 *     const aq    = extra?.airQuality|| 'moderate';
 *
 * `data/borough-extra.json` gave London and NYC those fields and gave the other
 * seven UK cities nothing, so every borough of all seven was painted a single
 * confident colour - the same purple that means "moderate road noise" where a
 * reading exists. The legend title above it already said "(NO DATA)". The label
 * said no data and the map drew a value.
 *
 * Nothing caught it because nothing compared the RENDER to the DATA. The pytest
 * suites never open index.html, and the Playwright specs assert the site against
 * itself, so a fabricated fill is self-consistent and passes.
 *
 * What it asserts
 * ---------------
 * For every city and each of the three layers: the number of paths painted
 * equals the number of that city's boroughs whose borough-extra record carries
 * the corresponding field. Both directions matter -
 *
 *   painted > expected  a default is being invented for boroughs with no data
 *   painted < expected  a borough HAS data the map is failing to find, which is
 *                       what a borough-name mismatch between the holder and the
 *                       GeoJSON looks like, and it fails silently
 *
 * Proven red in both directions: restoring `|| 'moderate'` over-paints, and
 * renaming a borough key in borough-extra.json under-paints.
 *
 *   node tests/layer-honesty.mjs
 */
import { chromium } from '@playwright/test';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';

const ROOT = process.cwd();
// 8123 / 8921 / 8922 / 8923 / 8924 are taken by the other harnesses, and
// preflight runs these in one block.
const PORT = 8925;
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
await new Promise((r) => server.listen(PORT, r));

const LAYERS = [
  { key: 'defra-road', field: 'roadNoise', sel: '.layer-defra-road', label: 'road noise' },
  { key: 'flood', field: 'flood', sel: '.layer-flood', label: 'flood' },
  { key: 'air-quality', field: 'airQuality', sel: '.layer-air-quality', label: 'air quality' },
];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto(`http://localhost:${PORT}/index.html`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(3000);

const cities = await page.evaluate(() =>
  Object.entries(CITY_DATA).map(([id, d]) => ({ id, label: d.label, country: d.country }))
);

console.log('\nLayer honesty: painted boroughs vs boroughs holding a reading\n');
console.log(`${'city'.padEnd(20)} ${'road noise'.padEnd(16)} ${'flood'.padEnd(16)} air quality`);
console.log('-'.repeat(74));

let fail = 0;

// THE LANDING CITY, MEASURED WITHOUT SWITCHING TO IT.
//
// Separate from the loop below, and first, because switching to a city
// re-renders the map: every city reached through the switcher is painted from a
// fully hydrated `borough-extra.json`, so the loop cannot see anything that goes
// wrong on the FIRST render. The city a visitor actually lands on is the only
// one painted before the switcher has been touched.
//
// HONEST LIMIT OF THIS CASE. It is here because that asymmetry is real, not
// because it is proven to catch a specific bug. `borough-extra.json` is
// lazy-loaded and could in principle arrive after the first render, leaving the
// landing city's fills empty - but on a local server hydration reliably wins
// (measured at 500ms through 6s, always 33/33), so removing the
// repaintFillLayers() call from hydrateBoroughExtra() does NOT turn this red.
// Treat it as a guard against a race that is latent here and plausible on a
// slow connection, not as a proven red-prover like the over-painting case.
{
  const landing = await page.evaluate((layerDefs) => {
    for (const l of layerDefs) layers[l.key] = true;
    const feats = cityOf(currentCity).features();
    const out = { city: currentCity };
    for (const l of layerDefs) {
      const expected = feats.filter((f) => {
        const e = getExtraData(getName(f));
        return e && e[l.field];
      }).length;
      const gEl = document.querySelector(l.sel);
      out[l.key] = { painted: gEl ? gEl.querySelectorAll('path').length : 0, expected };
    }
    return out;
  }, LAYERS);

  const cells = [];
  for (const l of LAYERS) {
    const m = landing[l.key];
    const ok = m.painted === m.expected;
    if (!ok) fail += 1;
    cells.push(`${ok ? ' ' : '!'}${m.painted}/${m.expected}`.padEnd(16));
  }
  console.log(`${`${landing.city} (landing)`.padEnd(20)} ${cells.join(' ')}`);
}

for (const city of cities) {
  await page.evaluate((c) => switchCountry(c), city.country);
  await page.waitForTimeout(250);
  await page.evaluate((id) => switchCity(id), city.id);
  await page.waitForTimeout(1800);
  await page.evaluate((keys) => {
    for (const k of keys) layers[k] = true;
  }, LAYERS.map((l) => l.key));
  await page.waitForTimeout(400);

  const measured = await page.evaluate((layerDefs) => {
    // Expected count comes from the SAME record the renderer reads, resolved
    // through the SAME getExtraData() lookup - so a borough-name mismatch shows
    // up as a shortfall rather than being silently excused on both sides.
    const feats = cityOf(currentCity).features();
    const out = {};
    for (const l of layerDefs) {
      const expected = feats.filter((f) => {
        const e = getExtraData(getName(f));
        return e && e[l.field];
      }).length;
      const gEl = document.querySelector(l.sel);
      out[l.key] = { painted: gEl ? gEl.querySelectorAll('path').length : 0, expected };
    }
    return out;
  }, LAYERS);

  const cells = [];
  for (const l of LAYERS) {
    const m = measured[l.key];
    const ok = m.painted === m.expected;
    if (!ok) fail += 1;
    cells.push(`${ok ? ' ' : '!'}${m.painted}/${m.expected}`.padEnd(16));
  }
  console.log(`${city.label.padEnd(20)} ${cells.join(' ')}`);
}

await browser.close();
server.close();

console.log(
  fail === 0
    ? '\nEvery layer paints exactly the boroughs that hold a reading.'
    : `\n${fail} layer/city combination(s) paint a different number of boroughs than hold data.`
);
process.exit(fail === 0 ? 0 : 1);
