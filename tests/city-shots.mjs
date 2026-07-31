/** Screenshots each registered city's map view. node tests/city-shots.mjs [outDir] */
import { chromium } from '@playwright/test';
import { createServer } from 'node:http';
import { readFile, mkdir } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';

const ROOT = process.cwd();
const OUT = process.argv[2] || join(ROOT, 'city-shots');
const PORT = 8918;
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.webmanifest': 'application/manifest+json' };

const server = createServer(async (req, res) => {
  const url = decodeURIComponent(req.url.split('?')[0]);
  const path = join(ROOT, normalize(url === '/' ? '/index.html' : url));
  if (!path.startsWith(ROOT)) return res.writeHead(403).end();
  try {
    const b = await readFile(path);
    res.writeHead(200, { 'content-type': TYPES[extname(path)] || 'application/octet-stream' });
    res.end(b);
  } catch { res.writeHead(404).end(); }
});
await new Promise((r) => server.listen(PORT, r));
await mkdir(OUT, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
await page.goto(`http://localhost:${PORT}/index.html`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);

for (const city of ['london', 'nyc', 'manchester']) {
  if (city !== 'london') {
    // Chips exist only for the active country, so select that tier first.
    const want = await page.evaluate((c) => window.cityCfg(c).country, city);
    const have = await page.evaluate(
      () => document.querySelector('.country-btn.active')?.dataset.country
    );
    if (want !== have) {
      await page.click(`.country-btn[data-country="${want}"]`);
      await page.waitForTimeout(1500);
    }
    await page.click(`.city-btn[data-city="${city}"]`);
    await page.waitForTimeout(1800);
  }
  const n = await page.locator('path.borough').count();
  const file = join(OUT, `${city}.png`);
  await page.screenshot({ path: file });
  console.log(`${city.padEnd(11)} ${n} boroughs  ->  ${file}`);
}

await browser.close();
server.close();
