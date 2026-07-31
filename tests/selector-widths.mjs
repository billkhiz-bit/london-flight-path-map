/**
 * The country tier and the city chips are independently absolute-positioned, so
 * every responsive override that moves one must move the other. It did not, and
 * between 901px and 1366px the chips rendered on top of the tabs — visible in no
 * screenshot taken at 1440px.
 *
 * Asserts they never overlap at any width, and that the tier is the topmost
 * element at its own coordinates.
 *
 *   node tests/selector-widths.mjs   (expects a server on :8920)
 */
import { chromium } from '@playwright/test';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';

const ROOT = process.cwd();
const PORT = 8922;
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.webmanifest': 'application/manifest+json' };
const server = createServer(async (req, res) => {
  const p = join(ROOT, normalize(decodeURIComponent(req.url.split('?')[0]) === '/' ? '/index.html' : decodeURIComponent(req.url.split('?')[0])));
  if (!p.startsWith(ROOT)) return res.writeHead(403).end();
  try {
    res.writeHead(200, { 'content-type': TYPES[extname(p)] || 'application/octet-stream' });
    res.end(await readFile(p));
  } catch { res.writeHead(404).end(); }
});
await new Promise((r) => server.listen(PORT, r));

const browser = await chromium.launch();
let fail = 0;
// Widths chosen to straddle every breakpoint boundary in the file.
for (const w of [1680, 1440, 1367, 1366, 1200, 1024, 901, 900, 768]) {
  const page = await browser.newPage({ viewport: { width: w, height: 800 } });
  await page.goto(`http://localhost:${PORT}/index.html`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(700);
  const r = await page.evaluate(() => {
    const c = document.getElementById('country-selector');
    const s = document.getElementById('city-selector');
    const cb = c.getBoundingClientRect();
    const sb = s.getBoundingClientRect();
    const hit = document.elementFromPoint(cb.x + 6, cb.y + cb.height / 2);
    return {
      cy: Math.round(cb.y), sy: Math.round(sb.y),
      overlap: !(cb.bottom <= sb.top || sb.bottom <= cb.top),
      covered: !(hit && (hit.closest('#country-selector') !== null)),
    };
  });
  const ok = !r.overlap && !r.covered;
  if (!ok) fail++;
  console.log(`${String(w).padStart(5)}px  country=${String(r.cy).padStart(3)} chips=${String(r.sy).padStart(3)}  ${ok ? 'OK' : 'FAIL' + (r.overlap ? ' overlap' : '') + (r.covered ? ' covered' : '')}`);
  await page.close();
}
await browser.close();
server.close();
console.log(`\nRESULT: ${fail === 0 ? 'PASS' : 'FAIL'}`);
process.exit(fail === 0 ? 0 : 1);
