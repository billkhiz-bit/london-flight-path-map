/** Checks the locator inset: visible for UK cities, hidden for US, correct highlight. */
import { chromium } from '@playwright/test';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';

const ROOT = process.cwd();
const PORT = 8921;
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.webmanifest': 'application/manifest+json' };

const server = createServer(async (req, res) => {
  const p = join(ROOT, normalize(decodeURIComponent(req.url.split('?')[0]) === '/' ? '/index.html' : decodeURIComponent(req.url.split('?')[0])));
  if (!p.startsWith(ROOT)) return res.writeHead(403).end();
  try {
    // Read BEFORE writing the header. The other order sends 200 and then lets
    // readFile throw, so the catch hits ERR_HTTP_HEADERS_SENT and the harness
    // dies with a stack trace instead of reporting a missing file. Found by
    // red-proofing this test: deleting data/uk-locator.json made it exit 1 for
    // entirely the wrong reason, which is a green check's evil twin - a red
    // one that does not mean what it says.
    const body = await readFile(p);
    res.writeHead(200, { 'content-type': TYPES[extname(p)] || 'application/octet-stream' });
    res.end(body);
  } catch { res.writeHead(404).end(); }
});
await new Promise((r) => server.listen(PORT, r));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto(`http://localhost:${PORT}/index.html`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1500);

const read = () => page.evaluate(() => {
  const box = document.getElementById('locator');
  const rings = [...document.querySelectorAll('#locator-cities circle[stroke="var(--orange)"]')];
  return {
    hidden: box.hasAttribute('hidden'),
    markers: document.querySelectorAll('#locator-cities .cty').length,
    clickable: document.querySelectorAll('#locator-cities .cty[role="button"]').length,
    highlighted: rings.length,
    caption: [document.getElementById('locator-region').textContent, document.getElementById('locator-count').textContent].filter(Boolean).join(' - '),
    landLength: (document.getElementById('locator-land').getAttribute('d') || '').length,
  };
});

let fail = 0;
const expect = { london: false, nyc: true, manchester: false };
for (const city of ['london', 'nyc', 'manchester']) {
  if (city !== 'london') {
    // window.cityOf, not window.CITY_DATA: `const` at script top level is not
    // a window property, but function declarations are. Renamed from the
    // spike branch's cityCfg when the registry landed on master.
    const want = await page.evaluate((c) => window.cityOf(c).country, city);
    const have = await page.evaluate(
      () => document.querySelector('.country-btn.active')?.dataset.country
    );
    if (want !== have) {
      await page.click(`.country-btn[data-country="${want}"]`);
      await page.waitForTimeout(1400);
    }
    await page.click(`.city-btn[data-city="${city}"]`);
    await page.waitForTimeout(1400);
  }
  const r = await read();
  const wantHidden = expect[city];
  const ok = r.hidden === wantHidden && (wantHidden || (r.markers === 10 && r.highlighted === 1 && r.clickable === 2));
  if (!ok) fail++;
  console.log(`${city.padEnd(11)} ${ok ? 'OK  ' : 'FAIL'} hidden=${r.hidden} markers=${r.markers} clickable=${r.clickable} highlighted=${r.highlighted} land=${r.landLength} "${r.caption}"`);
}

// The inset must be able to drive a switch, not just report one.
await page.click('.city-btn[data-city="manchester"]');
await page.waitForTimeout(1200);
await page.evaluate(() => {
  const first = [...document.querySelectorAll('#locator-cities .cty[role="button"])'.replace(')', ''))]
    .find((n) => n.getAttribute('aria-label')?.includes('London'));
  first?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
});
await page.waitForTimeout(1600);
const after = await page.evaluate(() => ({
  boroughs: document.querySelectorAll('path.borough').length,
  active: document.querySelector('.city-btn[aria-pressed="true"]')?.dataset.city,
}));
const navOk = after.active === 'london' && after.boroughs === 33;
if (!navOk) fail++;
console.log(`\nclick London in inset -> ${navOk ? 'OK' : 'FAIL'} (active=${after.active}, boroughs=${after.boroughs})`);

await browser.close();
server.close();
console.log(`\nRESULT: ${fail === 0 ? 'PASS' : 'FAIL'}`);
process.exit(fail === 0 ? 0 : 1);
