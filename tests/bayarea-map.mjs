// The San Francisco Bay Area on the live map: drawn, clicked, ranked and searched, with NO score.
//
// WHY THIS EXISTS. Release 1 (2026-10-05, Bill's ruling) puts the Bay Area on
// the map with the /bay-area/ page's FACTS and no number, because every UK
// quiet estimate is fitted against DEFRA and the Bay Area has no yardstick. It
// is the first city whose records are not scores, so every place that prints
// a score is a place it could print "undefined/10", and every search route that
// assumes New York's ZIP table could swallow a Bay Area ZIP.
//
// WHAT IT ASSERTS, at desktop and phone widths, every off-site request aborted
// and postcodes.io answering 404 (so a name search has nowhere else to go):
//   1. The Bay Area chip draws its 50 cities, three airports and the routes.
//   2. A city opens a facts card ON SCREEN with the page's own text and no
//      score anywhere in it.
//   3. The ranking is the noise-map order, with no score column.
//   4. A Bay Area ZIP typed from London lands on that city's card, with the ZIP.
//   5. A Bay Area city NAME typed from London does too.
//   6. A ZIP in no drawn city says so, on screen.
//   7. A ZIP in neither table names both places Sky Score covers.
//   8. A ?city=bayarea link ends with no inset, not England's arriving late.
//   9. No page errors.
//
//   node tests/bayarea-map.mjs

import { chromium } from '@playwright/test';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const PORT = 8955;
const TYPES = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.mjs': 'application/javascript',
  '.json': 'application/json',
  '.css': 'text/css',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.png': 'image/png',
  '.webmanifest': 'application/manifest+json',
};
const server = createServer(async (req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]);
  if (p === '/') p = '/index.html';
  if (!extname(p)) p = p.replace(/\/$/, '') + '/index.html';
  try {
    const buf = await readFile(join(ROOT, p));
    res.writeHead(200, { 'Content-Type': TYPES[extname(p)] || 'application/octet-stream' });
    res.end(buf);
  } catch {
    res.writeHead(404);
    res.end('not found');
  }
});
await new Promise((r) => server.listen(PORT, '127.0.0.1', r));
const BASE = `http://127.0.0.1:${PORT}/`;

const failures = [];
let checks = 0;
const ok = (cond, label, detail = '') => {
  checks++;
  console.log(`  ${cond ? 'ok  ' : 'FAIL'} ${label}${cond || !detail ? '' : `: ${detail}`}`);
  if (!cond) failures.push(label + (detail ? `: ${detail}` : ''));
};

// The panel as a sighted visitor sees it: text only from a panel with a box on
// screen, and the first paragraph hit-tested (an element that is not rendered
// still returns its text through innerText; tests/outside-coverage.mjs records
// what assuming otherwise cost).
const panel = (page) =>
  page.evaluate(() => {
    const content = document.getElementById('sidebar-content');
    const box = content.getBoundingClientRect();
    const first = content.querySelector('p');
    const r = first?.getClientRects()[0];
    const top = r ? document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2) : null;
    return {
      title: document.getElementById('sidebar-title').textContent.trim(),
      text: box.width && box.height ? content.innerText.replace(/\s+/g, ' ') : '',
      onScreen: !!top && (top === first || first.contains(top)),
    };
  });

const browser = await chromium.launch();
for (const vp of [
  { width: 1440, height: 900, label: 'desktop' },
  { width: 390, height: 844, label: 'phone' },
]) {
  const ctx = await browser.newContext({ viewport: vp, isMobile: vp.width < 900, hasTouch: vp.width < 900 });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (route) =>
    /api\.postcodes\.io/.test(route.request().url())
      ? route.fulfill({ status: 404, contentType: 'application/json', body: '{"status":404,"error":"not found"}' })
      : route.abort()
  );
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof switchCity === 'function', { timeout: 20000 });
  const L = vp.label.padEnd(8);

  // 1. Drawn.
  await page.evaluate(() => switchCity('bayarea'));
  await page.waitForFunction(() => document.querySelectorAll('path.borough').length >= 50, null, { timeout: 20000 }).catch(() => {});
  const drawn = await page.evaluate(() => ({
    outlines: document.querySelectorAll('path.borough').length,
    airports: document.querySelectorAll('.layer-airports circle').length,
    routes: document.querySelectorAll('.layer-paths path').length,
  }));
  ok(drawn.outlines === 50 && drawn.airports === 3 && drawn.routes >= 40, `${L} the Bay Area draws 50 cities, 3 airports and its routes`, JSON.stringify(drawn));

  // 2. A city's facts, on screen, with no score.
  await page.evaluate(() => selectBoroughByName('San Bruno'));
  await page.waitForTimeout(300);
  const sb = await panel(page);
  ok(
    sb.title === 'SAN BRUNO' && sb.onScreen && /Not scored/.test(sb.text) && /94% of the city/.test(sb.text) && /SFO 10L/.test(sb.text),
    `${L} San Bruno opens its facts card on screen, in the page's own words`,
    `${sb.title} / on screen ${sb.onScreen} / ${sb.text.slice(0, 140)}`
  );
  ok(!/\/10|undefined|NaN|null/.test(sb.text), `${L} the facts card prints no score and no placeholder`, sb.text.slice(0, 200));

  // 3. The ranking: noise-map order, no score column.
  const rank = await page.evaluate(() => {
    renderBoroughRanking();
    const head = [...document.querySelectorAll('#borough-ranking thead th')].map((t) => t.textContent.trim());
    const first = [...document.querySelectorAll('#borough-ranking tbody tr')].map((tr) => tr.dataset.rankName);
    return { head, first: first.slice(0, 3), n: first.length, text: document.getElementById('borough-ranking').innerText };
  });
  ok(
    rank.n === 50 && rank.head.includes('On the noise map') && !rank.head.some((h) => /score/i.test(h)) && /Not scored/.test(rank.text),
    `${L} the ranking lists 50 cities by noise-map share, with no score column`,
    JSON.stringify({ head: rank.head, n: rank.n })
  );
  ok(rank.first[0] === 'Colma', `${L} the ranking starts where the Bay Area page does (Colma, 100%)`, rank.first.join(', '));

  // 4. A Bay Area ZIP from London.
  await page.evaluate(() => switchCity('london'));
  await page.waitForFunction(() => document.querySelectorAll('path.borough').length === 33, null, { timeout: 20000 });
  await page.evaluate(() => triggerSearch('94301'));
  await page.waitForFunction(() => /PALO ALTO/i.test(document.getElementById('sidebar-title').textContent), null, { timeout: 20000 }).catch(() => {});
  const zip = await panel(page);
  ok(/PALO ALTO/i.test(zip.title) && zip.onScreen && /ZIP 94301 In Palo Alto\./.test(zip.text), `${L} ZIP 94301 typed on London's map opens Palo Alto with its ZIP line`, `${zip.title} / ${zip.text.slice(0, 160)}`);

  // 5. A Bay Area city name from London (postcodes.io answers 404, so only the Bay Area can find it).
  await page.evaluate(() => switchCity('london'));
  await page.waitForFunction(() => document.querySelectorAll('path.borough').length === 33, null, { timeout: 20000 });
  await page.evaluate(() => triggerSearch('Livermore'));
  await page.waitForFunction(() => /LIVERMORE/i.test(document.getElementById('sidebar-title').textContent), null, { timeout: 20000 }).catch(() => {});
  const named = await panel(page);
  ok(/LIVERMORE/i.test(named.title) && named.onScreen && /36% of the city, from Livermore Municipal/.test(named.text), `${L} "Livermore" typed on London's map opens Livermore's facts`, `${named.title} / ${named.text.slice(0, 160)}`);

  // 6. A ZIP in no drawn city.
  await page.evaluate(() => triggerSearch('94305'));
  await page.waitForFunction(() => /ZIP 94305/i.test(document.getElementById('sidebar-title').textContent), null, { timeout: 20000 }).catch(() => {});
  const cdp = await panel(page);
  ok(/ZIP 94305/i.test(cdp.title) && cdp.onScreen && /Santa Clara County/.test(cdp.text) && /Stanford/.test(cdp.text), `${L} a ZIP in no drawn city says so, on screen, and names where it is`, `${cdp.title} / ${cdp.text.slice(0, 160)}`);

  // 7. A ZIP in neither table.
  await page.evaluate(() => triggerSearch('90210'));
  await page.waitForFunction(() => document.getElementById('sidebar-title').textContent.trim() === 'NOT FOUND', null, { timeout: 20000 }).catch(() => {});
  const none = await panel(page);
  ok(none.title === 'NOT FOUND' && none.onScreen && /New York City/.test(none.text) && /Bay Area/.test(none.text), `${L} a ZIP in neither table names both places covered`, none.text.slice(0, 160));

  // 8. A ?city=bayarea link must not end with England's inset on screen. London's
  // silhouette is fetched at boot and held back here, so it lands AFTER the
  // switch, which is how the live page came to show it (2026-10-05).
  await page.route('**/data/uk-locator.json', async (route) => {
    await new Promise((r) => setTimeout(r, 1500));
    await route.continue();
  });
  await page.goto(`${BASE}?city=bayarea`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelectorAll('path.borough').length >= 50, null, { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(2500);
  const inset = await page.evaluate(() => {
    const box = document.getElementById('locator');
    return { hidden: !box || box.hidden || getComputedStyle(box).display === 'none', region: document.querySelector('.locator-region')?.textContent || '' };
  });
  ok(inset.hidden, `${L} a ?city=bayarea link shows no inset, not England's arriving late`, inset.region);

  ok(errors.length === 0, `${L} no page errors`, errors.join(' | '));
  await ctx.close();
}
await browser.close();
server.close();

const EXPECTED = 2 * 11;
if (checks < EXPECTED) {
  console.error(`\nFAIL: ran ${checks} checks, expected ${EXPECTED}.`);
  process.exit(1);
}
if (failures.length) {
  console.error(`\nFAIL: ${failures.length} problem(s):`);
  for (const f of failures) console.error('  - ' + f);
  process.exit(1);
}
console.log(`\nThe Bay Area is drawn, searched and ranked with no score: ${checks} checks.`);
