/**
 * Render the link-preview picture for the Bay Area page: bay-area/share.png.
 *
 *   node scripts/render_bay_area_share.mjs
 *
 * A link posted without a picture is a line of grey text, and this page exists
 * to be posted. The card is the page's OWN map (the same SVG, cut to the three
 * airports) beside its title, so it cannot show a route the page does not.
 *
 * Re-run after `build_bay_area_page.py --write` changes the map (a new FAA
 * cycle that moves a route, a new noise edition). Nothing checks the picture
 * against the page: a browser's rendering is not reproducible byte for byte,
 * so a gate on it would red on a font update. It is a picture of the map, and
 * the page beside it is what is gated.
 *
 * 1200x630 is the size link previews are cut to.
 */
import { chromium } from '@playwright/test';
import { createServer } from 'node:http';
import { createReadStream, existsSync, statSync } from 'node:fs';
import { extname, join, resolve } from 'node:path';

const ROOT = resolve('.');
const OUT = join(ROOT, 'bay-area', 'share.png');
const TYPES = { '.html': 'text/html', '.css': 'text/css', '.png': 'image/png', '.woff2': 'font/woff2' };

if (!existsSync(join(ROOT, 'bay-area', 'index.html'))) {
  console.error('bay-area/index.html not found - run from the repo root, after build_bay_area_page.py --write.');
  process.exit(1);
}

const server = createServer((req, res) => {
  const path = decodeURIComponent(req.url.split('?')[0]);
  const file = join(ROOT, path.endsWith('/') ? `${path}index.html` : path);
  if (!file.startsWith(ROOT) || !existsSync(file) || statSync(file).isDirectory()) {
    res.writeHead(404);
    res.end();
    return;
  }
  res.writeHead(200, { 'Content-Type': TYPES[extname(file)] || 'application/octet-stream' });
  createReadStream(file).pipe(res);
});
await new Promise((ok) => server.listen(0, '127.0.0.1', ok));
const base = `http://127.0.0.1:${server.address().port}`;

const browser = await chromium.launch();
try {
  const page = await (await browser.newContext({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 })).newPage();
  // The page's own analytics script must not count a render as a visit.
  await page.route('**/gc.zgo.at/**', (r) => r.abort());
  await page.goto(`${base}/bay-area/index.html`, { waitUntil: 'networkidle' });
  const drawn = await page.evaluate(() => {
    const svg = document.querySelector('svg.map');
    const [, , w] = svg.getAttribute('viewBox').split(' ').map(Number);
    // The three airports and the cities between them: map units 95 to 690 down
    // the page, and everything east of the open ocean.
    const top = 95;
    const scale = 630 / (690 - top);
    const card = document.createElement('div');
    card.id = 'card';
    card.innerHTML = `
      <div class="words">
        <p class="brand">SKY SCORE</p>
        <p class="title">Which Bay Area cities are under a flight path?</p>
        <p class="sub">The FAA's published routes for SFO, Oakland and San Jose, over 50 cities, with the federal aircraft noise map.</p>
        <p class="where">skyscore.co.uk/bay-area</p>
      </div>
      <div class="mapbox"></div>`;
    const box = card.querySelector('.mapbox');
    svg.removeAttribute('class');
    svg.classList.add('map');
    svg.style.cssText = `position:absolute;width:${w * scale}px;height:auto;top:${-top * scale}px;right:0;border:0`;
    box.append(svg);
    document.body.replaceChildren(card);
    const style = document.createElement('style');
    style.textContent = `
      body { margin:0; background:#e4e3e0; }
      #card { width:1200px; height:630px; display:flex; font-family:'Inter',system-ui,sans-serif; color:#141414; }
      .words { width:330px; padding:44px 28px 36px 40px; display:flex; flex-direction:column; }
      .brand { font:500 13px 'JetBrains Mono',ui-monospace,monospace; letter-spacing:3px; margin:0 0 36px; }
      .title { font-size:38px; font-weight:700; line-height:1.08; letter-spacing:-0.02em; margin:0 0 18px; }
      .sub { font-size:17px; line-height:1.4; color:#55554f; margin:0; }
      .where { font:500 14px 'JetBrains Mono',ui-monospace,monospace; margin:auto 0 0; }
      .mapbox { position:relative; flex:1; overflow:hidden; border-left:1px solid #141414; }`;
    document.head.append(style);
    return { width: w * scale };
  });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
  await page.screenshot({ path: OUT, clip: { x: 0, y: 0, width: 1200, height: 630 } });
  console.log(`wrote bay-area/share.png (map drawn ${Math.round(drawn.width)} px wide)`);
} finally {
  await browser.close();
  server.close();
}
