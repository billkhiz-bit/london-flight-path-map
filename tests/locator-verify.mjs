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
// Per city, because the inset is no longer UK-only. New York used to expect
// hidden=true - `country !== 'United Kingdom'` hid it rather than drawing the
// USA - and now draws the contiguous US with one marker. markers/clickable
// differ per silhouette, so they are declared here rather than assumed:
// The counts are DERIVED, not declared, and that is a correction. They were
// hardcoded at markers:10 / clickable:8, under a comment explaining that
// clickable "was 2 until 2026-08-10 and is now 8" - a number that had already
// been rewritten once and went stale again the moment Leicester and Teesside
// were added, failing a tree where the inset was perfectly correct. A count
// baked into an assertion is scheduled staleness.
//
// What actually needs guarding is the RELATIONSHIP: every marker in the
// silhouette file is drawn, and exactly those whose name is in LOCATOR_TO_CITY
// are clickable. Cardiff and Nottingham are deliberately NOT - they are
// API-only, so they draw as planned discs. That still fails on the real defect
// (a live city whose marker never became clickable) without failing on growth.
//
// The expectation is anchored on CITY_DATA LABELS, deliberately NOT on
// LOCATOR_TO_CITY. Deriving it from LOCATOR_TO_CITY would make the test read
// its expectation out of the very table it is checking, so deleting a city from
// that table would lower both sides together and pass - the failure mode this
// repo has hit five times. A marker is expected to be clickable when a city ON
// THE SITE carries that display name, which is an independent fact.
const derived = await page.evaluate(async () => {
  const labels = new Set(Object.values(CITY_DATA).map((c) => c.label));
  const out = {};
  for (const [id, cfg] of Object.entries(CITY_DATA)) {
    if (!cfg.locator) continue;
    const res = await fetch(cfg.locator);
    const data = await res.json();
    out[id] = {
      markers: data.cities.length,
      clickable: data.cities.filter((c) => labels.has(c.name)).length,
    };
  }
  return out;
});
const expect = {
  london: { hidden: false, ...derived.london, highlighted: 1 },
  nyc: { hidden: false, ...derived.nyc, highlighted: 1 },
  manchester: { hidden: false, ...derived.manchester, highlighted: 1 },
};
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
  const want = expect[city];
  const ok =
    r.hidden === want.hidden &&
    (want.hidden ||
      (r.markers === want.markers &&
        r.highlighted === want.highlighted &&
        r.clickable === want.clickable &&
        r.landLength > 1000));
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
