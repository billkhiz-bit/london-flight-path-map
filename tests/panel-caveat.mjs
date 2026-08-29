// Does the borough panel's Environment caveat describe the borough in front of
// it? Camden is 3/3 (no caveat), Middlesbrough is 2/3 (must NAME the two inputs
// it has), Brooklyn has none of the three (no caveat, no crash).
//
// WHY THIS FILE EXISTS. On 2026-08-29 every UK borough panel rendered
// "... - undefined only here" beside a correctly-computed Environment score,
// because envCaveat() was handed the SCORED record from matchBorough() while it
// reads the three CONTINUOUS fields, which only borough-extra.json carries. It
// shipped and deployed with all 32 gates green, and the audit found it hours
// later.
//
// NOTHING IN THE SUITE OPENS THE SIDEBAR. borough-score-parity.mjs compares the
// score out of the registry without rendering the panel, so the whole detail
// panel - every string beside every number - was unasserted. This gate renders
// it. Proven red against the pre-fix tree: Camden and Middlesbrough both came
// back with undefined=true.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join } from 'node:path';
import { chromium } from 'playwright';

// Serve the repo root regardless of where this is invoked from.
const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
const PORT = 8941;
const TYPES = {
  '.html': 'text/html', '.js': 'application/javascript', '.mjs': 'application/javascript',
  '.json': 'application/json', '.css': 'text/css', '.png': 'image/png',
  '.svg': 'image/svg+xml', '.webmanifest': 'application/manifest+json', '.woff2': 'font/woff2',
};
const server = createServer(async (req, res) => {
  const url = decodeURIComponent(req.url.split('?')[0]);
  try {
    const buf = await readFile(join(ROOT, url === '/' ? '/index.html' : url));
    res.writeHead(200, { 'content-type': TYPES[extname(url)] || 'application/octet-stream' });
    res.end(buf);
  } catch { res.writeHead(404); res.end('nf'); }
});
await new Promise((r) => server.listen(PORT, r));

const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(`http://localhost:${PORT}/index.html`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(3000);

let fail = 0;
async function check(city, country, borough, expectCaveat) {
  await page.evaluate((c) => switchCountry(c), country);
  await page.waitForTimeout(300);
  await page.evaluate((c) => switchCity(c), city);
  await page.waitForTimeout(1500);
  const out = await page.evaluate((b) => {
    const d = matchBorough(b);
    if (!d) return { err: 'borough not found' };
    updateSidebar(d);
    const rows = [...document.querySelectorAll('.score-explain')];
    const row = rows.find((r) => /Air quality, road noise and flood risk/.test(r.textContent));
    return { text: row ? row.textContent.trim() : '(no environment row)' };
  }, borough);
  if (out.err) { console.log(`  ! ${borough}: ${out.err}`); fail++; return; }
  const hasUndef = /undefined/i.test(out.text);
  const hasCaveat = /only here/.test(out.text);
  const ok = !hasUndef && hasCaveat === expectCaveat;
  if (!ok) fail++;
  console.log(`  ${ok ? 'ok ' : 'FAIL'} ${borough.padEnd(16)} caveat=${hasCaveat} (want ${expectCaveat}) undefined=${hasUndef}`);
  console.log(`       "${out.text.slice(0, 165)}"`);
}

console.log('Environment caveat, rendered:');
await check('london', 'United Kingdom', 'Camden', false);
await check('teesside', 'United Kingdom', 'Middlesbrough', true);
await check('nyc', 'United States', 'Brooklyn', false);

console.log(fail ? `\n${fail} FAILED` : '\nall good');
await browser.close();
server.close();
process.exit(fail ? 1 : 0);
