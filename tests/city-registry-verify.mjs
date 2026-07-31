/**
 * Verifies the CITY_DATA registry renders every registered city, and that
 * converting the `city === 'nyc' ? … : …` ternaries did not regress London.
 *
 * Serves the working tree over HTTP rather than file:// because boundary data
 * is fetched from absolute `/data/...` paths, which file:// resolves against
 * the filesystem root.
 *
 *   node tests/city-registry-verify.mjs
 */
import { chromium } from '@playwright/test';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';

const ROOT = process.cwd();
const PORT = 8917;
const TYPES = {
  '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json',
  '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png',
  '.webmanifest': 'application/manifest+json',
};

const server = createServer(async (req, res) => {
  const url = decodeURIComponent(req.url.split('?')[0]);
  // Contain path traversal: resolve inside ROOT or refuse.
  const path = join(ROOT, normalize(url === '/' ? '/index.html' : url));
  if (!path.startsWith(ROOT)) {
    res.writeHead(403).end();
    return;
  }
  try {
    const body = await readFile(path);
    res.writeHead(200, { 'content-type': TYPES[extname(path)] || 'application/octet-stream' });
    res.end(body);
  } catch {
    res.writeHead(404).end();
  }
});
await new Promise((r) => server.listen(PORT, r));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
// Two errors are artefacts of serving the tree over plain http://localhost and
// appear on the live site too, so they are not signal here. Matched narrowly
// rather than filtered wholesale - a blanket ignore is how a real error hides.
const BENIGN = [
  // frame-ancestors is only honoured in a real CSP header, never in <meta>.
  /Content Security Policy directive 'frame-ancestors' is ignored/,
  // The analytics beacon is https:// in the CSP; this harness serves http://.
  /gc\.zgo\.at.*violates the following Content Security Policy/,
];
const errors = [];
const record = (t) => {
  if (!BENIGN.some((re) => re.test(t))) errors.push(t);
};
page.on('pageerror', (e) => record(String(e)));
page.on('console', (m) => {
  if (m.type() === 'error') record(m.text());
});

await page.goto(`http://localhost:${PORT}/index.html`, { waitUntil: 'networkidle' });

async function probe(city, { click = true } = {}) {
  // London is the initial state, so the first probe reads it without clicking;
  // every later probe - London included - must actually drive the button, or
  // the "switch back" check silently re-reads the previous city.
  if (click) {
    // Chips only exist for the active country, so select that tier first.
    const want = await page.evaluate((c) => window.cityCfg(c).country, city);
    const have = await page.evaluate(
      () => document.querySelector('.country-btn.active')?.dataset.country
    );
    if (want !== have) {
      await page.click(`.country-btn[data-country="${want}"]`);
      await page.waitForTimeout(1400);
    }
    await page.click(`.city-btn[data-city="${city}"]`);
    // Boundary fetch + d3 render.
    await page.waitForTimeout(1400);
  }
  return page.evaluate(() => ({
    subtitle: document.getElementById('map-subtitle')?.textContent?.trim(),
    boroughs: document.querySelectorAll('path.borough').length,
    paths: document.querySelectorAll('.layer-paths path, path.flight-path').length,
    pressed: [...document.querySelectorAll('.city-btn')]
      .filter((b) => b.getAttribute('aria-pressed') === 'true')
      .map((b) => b.dataset.city),
    // Sample the active city's own score set through the registry.
    sample: (() => {
      const d = window.getActiveBoroughData ? window.getActiveBoroughData() : {};
      const names = Object.keys(d);
      if (!names.length) return null;
      const n = names[0];
      return { name: n, score: d[n]?.score, live: d[n]?.scores?.live };
    })(),
    liveValues: (() => {
      const d = window.getActiveBoroughData ? window.getActiveBoroughData() : {};
      return new Set(Object.values(d).map((b) => b?.scores?.live)).size;
    })(),
  }));
}

const expect = { london: 33, nyc: 5, manchester: 10 };
let fail = 0;
for (const city of ['london', 'nyc', 'manchester']) {
  const r = await probe(city, { click: city !== 'london' });
  const ok = r.boroughs === expect[city] && r.pressed.join() === city;
  if (!ok) fail++;
  console.log(`\n--- ${city} ---  ${ok ? 'OK' : 'FAIL'}`);
  console.log(`  subtitle    ${r.subtitle}`);
  console.log(`  boroughs    ${r.boroughs} (expected ${expect[city]})`);
  console.log(`  active btn  ${r.pressed.join(', ') || '(none)'}`);
  console.log(`  sample      ${r.sample ? `${r.sample.name} score=${r.sample.score} live=${r.sample.live}` : '(none)'}`);
  console.log(`  distinct liveability values: ${r.liveValues}`);
}

// Back to London to prove the switch is reversible and nothing leaks.
const back = await probe('london');
if (back.boroughs !== 33) {
  fail++;
  console.log(`\nreturn to London FAILED: ${back.boroughs} boroughs`);
} else {
  console.log(`\nreturn to London OK: ${back.boroughs} boroughs`);
}

if (errors.length) {
  console.log(`\nconsole/page errors (${errors.length}):`);
  errors.slice(0, 6).forEach((e) => console.log('  ' + e.slice(0, 150)));
}

await browser.close();
server.close();
console.log(`\nRESULT: ${fail === 0 && errors.length === 0 ? 'PASS' : 'FAIL'}`);
process.exit(fail === 0 && errors.length === 0 ? 0 : 1);
