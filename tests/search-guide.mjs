// The full map's search guide (Bill's pick C2, 2026-11-11; mock-ups claude.ai/artifact/Jkh6b9wkuwpXHaK17BycFu v5).
//
// WHAT IT HOLDS, measured on the page, never read off a class alone:
//   1. A first visit shows the guide: one light round the search box, 4.6 s in all and so under WCAG 2.2.2's 5 s
//      (no pause control needed), then a still orange ring; the old dark banner is gone for good.
//   2. Reduced motion: the ring, no light, nothing animating.
//   3. On a phone the city's first three Try chips sit in the search card in place of the hint, each a 24 px+ target;
//      on a desktop they stay in the empty panel, every one of the registry's.
//   4. The guide ends at the visitor's first search, chip or borough, and is remembered; it ends but is NOT remembered
//      when an answer arrives by a link nobody tapped (/?postcode=), so that visitor still gets it next time.
//   5. Every city's Try chips lead to an answer in that city: each named one is searched here, never "not found".
//
// Locally / is the full map (index.html). Port 8981: the other harnesses hold 8099, 8921-8962.
//   node tests/search-guide.mjs
import { chromium } from '@playwright/test';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { stubLiveApi } from './stub-live-api.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const PORT = 8981;
const TYPES = { '.html': 'text/html', '.js': 'application/javascript', '.mjs': 'application/javascript', '.json': 'application/json',
  '.css': 'text/css', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.png': 'image/png', '.webmanifest': 'application/manifest+json' };
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

let failed = 0;
let passed = 0;
const ok = (cond, name, detail = '') => {
  if (cond) passed += 1;
  else failed += 1;
  console.log(`  ${cond ? 'ok  ' : 'FAIL'} ${name}${cond || !detail ? '' : `: ${detail}`}`);
};
const FAILS = /NOT FOUND|NOT COVERED|NOT ON THE MAP|CONNECTION ISSUE/;
const ORANGE = 'rgb(242, 125, 38)';
const UK_POSTCODE = /^[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}$/;

const browser = await chromium.launch();
const errors = [];
// A fresh context per visit: a first visit has no saved "seen".
async function visit(path, { width = 1366, height = 900, reducedMotion = 'no-preference', context = null } = {}) {
  const ctx = context || (await browser.newContext({ viewport: { width, height }, reducedMotion }));
  const page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push(`${path}: ${e.message}`));
  await stubLiveApi(page);
  await page.goto(BASE + path, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#search-input', { timeout: 20000 });
  return { ctx, page };
}
const guideOn = (page) => page.evaluate(() => !!document.querySelector('.search-box.guide'));
const seen = (page) => page.evaluate(() => { try { return localStorage.getItem('flightmap_hint_seen'); } catch { return 'unreadable'; } });
const answered = (page) => page.waitForFunction(() => {
  const t = document.getElementById('sidebar-title')?.textContent.trim() || '';
  return t && t !== 'SEARCHING...' && !document.querySelector('#tab-analysis .no-result-yet');
}, null, { timeout: 15000 }).then(() => page.locator('#sidebar-title').textContent()).catch(() => 'no answer in 15 s');

// ---- 1. Desktop, first visit ----
console.log('Desktop, first visit');
{
  const { ctx, page } = await visit('');
  const start = await page.evaluate(() => {
    const anims = document.getAnimations().filter((a) => a.effect?.target?.closest?.('.search-comet') || a.effect?.target?.id === 'search-input');
    const box = document.querySelector('.search-box');
    return {
      guide: box.classList.contains('guide'),
      banner: !!document.getElementById('first-hint'),
      rects: document.querySelectorAll('.search-wrapper .search-comet rect[pathLength="100"]').length,
      hidden: document.querySelector('.search-comet')?.getAttribute('aria-hidden'),
      ends: anims.map((a) => a.effect.getComputedTiming().endTime),
      names: anims.map((a) => a.animationName).sort(),
    };
  });
  ok(start.guide && !start.banner && start.rects === 3 && start.hidden === 'true', 'the guide is on, drawn round the search box, hidden from screen readers; the old banner is gone', JSON.stringify(start));
  ok(start.ends.length === 5 && start.ends.every((t) => t === 4600) && Math.max(...start.ends) <= 5000,
    'the light runs once, 4.6 s in all: under the 5 s after which moving content needs a pause control (WCAG 2.2.2)', JSON.stringify(start));
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => {}))));
  const rest = await page.evaluate(() => {
    const i = getComputedStyle(document.getElementById('search-input'));
    return { border: i.borderTopColor, shadow: i.boxShadow, light: getComputedStyle(document.querySelector('.search-comet')).opacity };
  });
  ok(rest.border === 'rgb(242, 125, 38)' && /3px/.test(rest.shadow) && rest.light === '0', 'at rest the light is gone and the box keeps a still orange ring', JSON.stringify(rest));
  const chips = await page.evaluate(() => ({
    row: getComputedStyle(document.getElementById('search-try')).display,
    panel: [...document.querySelectorAll('#sidebar-content .quicksearch .quicksearch-chip')].map((b) => b.textContent),
    want: cityOf('london').tryExamples,
  }));
  ok(chips.row === 'none' && JSON.stringify(chips.panel) === JSON.stringify(chips.want) && chips.want.length >= 3,
    "on a desktop the Try chips stay in the empty panel, every one of the city's", JSON.stringify(chips));
  await page.locator('#sidebar-content .quicksearch-chip', { hasText: 'Hounslow' }).click();
  const title = await answered(page);
  ok(/HOUNSLOW/i.test(title) && !(await guideOn(page)) && (await seen(page)) === '1', 'a Try chip searches, ends the guide and remembers it', `${title} guide=${await guideOn(page)} seen=${await seen(page)}`);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#search-input');
  ok(!(await guideOn(page)), 'and a later visit has no guide');
  await ctx.close();
}

// ---- 2. Reduced motion ----
console.log('Reduced motion');
{
  const { ctx, page } = await visit('', { reducedMotion: 'reduce' });
  const r = await page.evaluate(() => ({
    guide: !!document.querySelector('.search-box.guide'),
    running: document.getAnimations().filter((a) => a.effect?.target?.closest?.('.search-comet') || a.effect?.target?.id === 'search-input').length,
    border: getComputedStyle(document.getElementById('search-input')).borderTopColor,
    light: getComputedStyle(document.querySelector('.search-comet')).opacity,
  }));
  ok(r.guide && r.running === 0 && r.border === ORANGE && r.light === '0', 'with reduced motion: the still ring at once, no light, nothing moving', JSON.stringify(r));
  await ctx.close();
}

// ---- 3. Phone, first visit ----
console.log('Phone, first visit');
{
  const { ctx, page } = await visit('', { width: 390, height: 844 });
  const m = await page.evaluate(() => {
    const row = document.getElementById('search-try');
    const input = document.getElementById('search-input').getBoundingClientRect();
    const comet = document.querySelector('.search-comet').getBoundingClientRect();
    const card = document.querySelector('.search-box').getBoundingClientRect();
    return {
      shown: getComputedStyle(row).display,
      chips: [...row.querySelectorAll('.quicksearch-chip')].map((b) => [b.textContent, Math.round(b.getBoundingClientRect().width), Math.round(b.getBoundingClientRect().height)]),
      want: cityOf('london').tryExamples.slice(0, 3),
      hint: getComputedStyle(document.getElementById('search-hint')).display,
      aligned: ['left', 'top', 'width', 'height'].every((k) => Math.abs(input[k] - comet[k]) <= 1),
      fits: card.left >= 0 && card.right <= innerWidth,
      sideways: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    };
  });
  ok(m.shown === 'flex' && JSON.stringify(m.chips.map((c) => c[0])) === JSON.stringify(m.want) && m.chips.every(([, w, h]) => w >= 24 && h >= 24) && m.hint === 'none',
    "the card shows the city's first three Try chips in place of the hint, each a 24 px+ target", JSON.stringify(m));
  ok(m.aligned && m.fits && !m.sideways, 'the light sits exactly on the search box, and the card fits a 390 screen', JSON.stringify(m));
  await page.locator('#search-try .quicksearch-chip', { hasText: 'Camden' }).click();
  const title = await answered(page);
  const after = await page.evaluate(() => getComputedStyle(document.getElementById('search-try')).display);
  ok(/CAMDEN/i.test(title) && !(await guideOn(page)) && after === 'none' && (await seen(page)) === '1', 'a chip tap on a phone searches, and the chips go with the guide', `${title} row=${after}`);
  await ctx.close();
}

// ---- 3b. Short phones: the guide, but no chip row (it covered the layer buttons at 320x568 and squeezed the map at
//      844x390 in the preflight of 2026-11-11); the hint stays in its place ----
console.log('Short phones');
for (const [width, height] of [[320, 568], [375, 667], [844, 390]]) {
  const { ctx, page } = await visit('', { width, height });
  const s = await page.evaluate(() => ({
    guide: !!document.querySelector('.search-box.guide'),
    row: getComputedStyle(document.getElementById('search-try')).display,
    hint: getComputedStyle(document.getElementById('search-hint')).display,
  }));
  ok(s.guide && s.row === 'none' && s.hint !== 'none', `${width}x${height}: the guide runs, the chip row stays out (no room), the hint stays`, JSON.stringify(s));
  await ctx.close();
}

// ---- 4. An answer by a link nobody tapped ----
console.log('Deep link');
{
  const { ctx, page } = await visit('?postcode=TW9%203PZ');
  await page.waitForFunction(() => !document.querySelector('.search-box.guide'), null, { timeout: 15000 }).catch(() => {});
  const ended = !(await guideOn(page));
  const remembered = await seen(page);
  ok(ended && remembered !== '1', 'an answer by a link ends the guide but does not remember it', `ended=${ended} seen=${remembered}`);
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#search-input');
  ok(await guideOn(page), 'so the next plain visit still gets the guide');
  await ctx.close();
}

// ---- 5. A borough tap ----
console.log('Borough tap');
{
  const { ctx, page } = await visit('');
  await page.waitForSelector('path.borough', { timeout: 20000 });
  const before = await guideOn(page);
  // A real click (a synthetic one is no user activation, so it could never be remembered), on a point that is inside a
  // borough's outline AND on top there: a centre can fall outside a concave borough, or under a label.
  const spot = await page.evaluate(() => {
    for (const path of document.querySelectorAll('path.borough')) {
      const b = path.getBBox();
      const m = path.getScreenCTM();
      for (let i = 1; i < 10; i++) {
        for (let j = 1; j < 10; j++) {
          const pt = new DOMPoint(b.x + (b.width * i) / 10, b.y + (b.height * j) / 10);
          if (!path.isPointInFill(pt)) continue;
          const s = pt.matrixTransform(m);
          if (document.elementFromPoint(s.x, s.y) === path) return { x: s.x, y: s.y };
        }
      }
    }
    return null;
  });
  ok(!!spot, 'a borough can be tapped where nothing covers it', JSON.stringify(spot));
  if (spot) await page.mouse.click(spot.x, spot.y);
  await answered(page);
  ok(before && !(await guideOn(page)) && (await seen(page)) === '1', 'a borough tap ends the guide and remembers it', `before=${before} after=${await guideOn(page)} seen=${await seen(page)}`);
  await ctx.close();
}

// ---- 5b. The panel before a search (Bill's pick A, 2026-11-11: claude.ai/artifact/8EFboJHqQ1FBvdd6K5pCCv) ----
console.log('The panel before a search');
{
  const { ctx, page } = await visit('');
  const empty = await page.evaluate(() => ({
    rows: [...document.querySelectorAll('#sidebar-content .tells-list li')].map((li) => [li.querySelector('b')?.textContent, li.querySelector('span')?.textContent]),
    disc: (() => { const d = document.querySelector('.disclaimer'); const cs = getComputedStyle(d); return { text: d.textContent.replace(/\s+/g, ' ').trim(), bg: cs.backgroundColor, fg: cs.color }; })(),
  }));
  // The rows are the answer card's own groups: read the card's headings from a real answer (TW9 3PZ, stubbed), in order.
  await page.fill('#search-input', 'TW9 3PZ');
  await page.press('#search-input', 'Enter');
  await page.waitForSelector('.find-group .sec-head h3', { timeout: 20000 }).catch(() => {});
  const card = await page.evaluate(() => [...document.querySelectorAll('.find-group .sec-head h3')].map((h) => h.textContent));
  ok(empty.rows.length === 4 && JSON.stringify(empty.rows.map((r) => r[0])) === JSON.stringify(card) && empty.rows.every(([, t]) => t && t.length > 10),
    "London's empty panel says what a search tells you, in the answer card's own four groups, one line each", JSON.stringify({ empty: empty.rows, card }));
  const lum = (rgb) => { const [r, g, b] = rgb.match(/\d+/g).slice(0, 3).map((v) => { const c = v / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m); return (x + 0.05) / (y + 0.05); };
  ok(empty.disc.text.startsWith('Disclaimer: This tool is for informational purposes only') && /commission a proper survey/.test(empty.disc.text)
    && empty.disc.bg === 'rgb(228, 227, 224)' && ratio(empty.disc.bg, empty.disc.fg) >= 4.5,
    'the disclaimer keeps every word, as a note on the map\'s grey, readable (4.5:1 or more)', JSON.stringify({ ...empty.disc, ratio: ratio(empty.disc.bg, empty.disc.fg).toFixed(2) }));
  await ctx.close();
}
{
  const { ctx, page } = await visit('?city=nyc');
  await page.waitForFunction(() => currentCity === 'nyc' && !!document.querySelector('#sidebar-content .no-result-yet p'), null, { timeout: 15000 }).catch(() => {});
  const nyc = await page.evaluate(() => ({ list: !!document.querySelector('#sidebar-content .tells-list'), p: document.querySelector('#sidebar-content .no-result-yet p')?.textContent, hint: CITY_DATA.nyc.emptyStateHint }));
  ok(!nyc.list && nyc.p === nyc.hint, "New York's answer is its own, so its panel keeps its own sentence (no UK groups)", JSON.stringify(nyc));
  // THE PAGE'S ONE HEADING SAYS WHAT THE PAGE IS (the SEO audit, 2026-11-11), after a city's chrome has run: applyCityChrome
  // set its textContent to the brand and erased the rest. On screen it is the brand alone; the rest is clipped to a pixel.
  const heading = await page.locator('#map-title-text').ariaSnapshot().catch((err) => String(err));
  const shown = await page.evaluate(() => {
    const h = document.getElementById('map-title-text');
    return { text: h.textContent, brand: [...h.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim(),
      hidden: [...h.children].length > 0 && [...h.children].every((c) => c.getBoundingClientRect().width <= 1) };
  });
  // What a search engine indexes is the text, exactly; the accessible name may carry a space before the colon, because
  // the clipped span is positioned and Chromium joins a positioned child's name with a space (heard the same).
  ok(shown.text === 'Sky Score: noise and liveability map' && /heading "Sky Score ?: noise and liveability map" \[level=1\]/.test(heading)
    && shown.brand === 'Sky Score' && shown.hidden,
    'the heading says "Sky Score: noise and liveability map" after the city chrome has run, and shows the brand alone', JSON.stringify({ heading, shown }));
  await ctx.close();
}
{
  // Closing a result on a phone restores THIS city's panel (it restored a copy taken at boot: London's, in every city).
  const { ctx, page } = await visit('?city=bristol', { width: 390, height: 844 });
  await page.waitForFunction(() => currentCity === 'bristol', null, { timeout: 15000 }).catch(() => {});
  await page.evaluate(() => triggerSearch('Bath'));
  await page.waitForSelector('#result-close', { state: 'visible', timeout: 15000 }).catch(() => {});
  await page.locator('#result-close').click().catch(() => {});
  await page.waitForSelector('#sidebar-content .no-result-yet', { timeout: 10000 }).catch(() => {});
  const back = await page.evaluate(() => [...document.querySelectorAll('#sidebar-content .quicksearch-chip')].map((b) => b.textContent));
  const want = await page.evaluate(() => CITY_DATA.bristol.tryExamples);
  ok(JSON.stringify(back) === JSON.stringify(want), "closing a result on a phone restores this city's own panel, not London's", JSON.stringify({ back, want }));
  await ctx.close();
}

// ---- 6. Every city's chips lead to an answer there ----
console.log("Every city's Try chips");
{
  const { ctx, page } = await visit('');
  const cities = await page.evaluate(() => Object.keys(CITY_DATA).filter((c) => Array.isArray(CITY_DATA[c].tryExamples)));
  const all = await page.evaluate(() => Object.keys(CITY_DATA));
  ok(cities.length === all.length && cities.length >= 12, 'every city in the registry has Try examples', `${cities.length} of ${all.length}`);
  await ctx.close();
  // Every place a city's words name: its chips, and the places its hint and its not-found message suggest (Bristol's hint
  // said "Bristol, Bath or Weston", and two of the three found nothing; 2026-11-11). Read from the registry's own words:
  // the parenthesised lists, and the list after "e.g.", split on commas and "or"; only names (a ZIP is said in words).
  const named = (text) => {
    const lists = [...String(text).matchAll(/\(([^)]+)\)/g)].map((m) => m[1]);
    const eg = /e\.g\.\s*([^.]+)\./.exec(String(text));
    if (eg) lists.push(eg[1]);
    return lists.flatMap((l) => l.split(/,\s*|\s+or\s+/)).map((t) => t.replace(/^or\s+/, '').trim()).filter((t) => /^[A-Z][A-Za-z' -]+$/.test(t));
  };
  for (const city of cities) {
    const v = await visit(`?city=${city}`);
    const ex = await v.page.evaluate((c) => CITY_DATA[c].tryExamples, city);
    // The switch rebuilds the panel after the city's outlines load (the Bay Area's take a moment): wait for it.
    await v.page.waitForFunction((want) => {
      const got = [...document.querySelectorAll('#sidebar-content .quicksearch .quicksearch-chip')].map((b) => b.textContent);
      return JSON.stringify(got) === JSON.stringify(want) && !!document.querySelector('#tab-analysis .no-result-yet');
    }, ex, { timeout: 15000 }).catch(() => {});
    const panel = await v.page.evaluate(() => [...document.querySelectorAll('#sidebar-content .quicksearch .quicksearch-chip')].map((b) => b.textContent));
    ok(JSON.stringify(panel) === JSON.stringify(ex), `${city}: the empty panel shows its own Try chips after the switch`, JSON.stringify({ panel, ex }));
    const words = await v.page.evaluate((c) => [CITY_DATA[c].emptyStateHint, CITY_DATA[c].searchNotFound], city);
    const suggested = [...new Set(words.flatMap(named))].filter((n) => !ex.includes(n));
    for (const q of [...ex, ...suggested]) {
      if (UK_POSTCODE.test(q)) {
        ok(true, `${city}: "${q}" is a full postcode (searched live by the postcode suites, not here)`);
        continue;
      }
      await v.page.evaluate((s) => triggerSearch(s), q);
      const title = await answered(v.page);
      ok(!FAILS.test(title) && title !== 'no answer in 15 s', `${city}: "${q}" leads to an answer`, title);
    }
    await v.ctx.close();
  }
}

await browser.close();
server.close();
ok(errors.length === 0, 'no page errors', errors.join(' | '));
console.log(failed ? `FAIL: ${passed} of ${passed + failed} checks` : `PASS: ${passed} of ${passed} checks`);
process.exit(failed ? 1 : 0);
