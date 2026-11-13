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
// The ring at rest is the focus orange, --focus #d35a12 (audit M-9, Bill's pick A, 2026-11-12): the brand orange read
// 2.60:1 against the panel, under the 3:1 a control's edge needs (WCAG 1.4.11). Measured against what is behind it.
const RING = 'rgb(211, 90, 18)';
const lumOf = (rgb) => { const [r, g, b] = rgb.match(/\d+/g).slice(0, 3).map((v) => { const c = v / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
const contrastOf = (a, b) => { const [x, y] = [lumOf(a), lumOf(b)].sort((m, n) => n - m); return (x + 0.05) / (y + 0.05); };const UK_POSTCODE = /^[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}$/;

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
    // The first painted background behind the box: the panel the ring is seen against.
    let el = document.getElementById('search-input').parentElement;
    let panel = 'rgba(0, 0, 0, 0)';
    while (el && /rgba\(0, 0, 0, 0\)|transparent/.test(panel)) { panel = getComputedStyle(el).backgroundColor; el = el.parentElement; }
    return { border: i.borderTopColor, shadow: i.boxShadow, light: getComputedStyle(document.querySelector('.search-comet')).opacity, panel };
  });
  ok(rest.border === RING && contrastOf(rest.border, rest.panel) >= 3 && /3px/.test(rest.shadow) && rest.light === '0',
    'at rest the light is gone and the box keeps a still ring in the focus orange, 3:1 or more against the panel (WCAG 1.4.11, audit M-9)',
    JSON.stringify({ ...rest, ratio: contrastOf(rest.border, rest.panel).toFixed(2) }));
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
  ok(r.guide && r.running === 0 && r.border === RING && r.light === '0', 'with reduced motion: the still ring at once, no light, nothing moving', JSON.stringify(r));
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

// ---- 7. The 12 Nov audit's map-state faults, each reached on purpose (I-13 to I-17) ----
console.log('The audit\'s map-state faults');
{
  // I-15: a covered council typed from another city's view opens it there; a prefix ("north") never jumps.
  const { ctx, page } = await visit('');
  await page.evaluate(() => triggerSearch('Birmingham'));
  const title = await answered(page);
  const city = await page.evaluate(() => currentCity);
  ok(/BIRMINGHAM/.test(title) && city === 'westmidlands', '"Birmingham" typed on London\'s map opens it in the West Midlands', `${title} in ${city}`);
  await page.evaluate(() => switchCity('london'));
  await page.evaluate(() => triggerSearch('north'));
  const north = await answered(page);
  ok(/NOT FOUND/.test(north) && (await page.evaluate(() => currentCity)) === 'london', '"north" is no council\'s whole name: not found, and the map stays put', north);
  // I-14: the area names that pointed at retired postcodes answer.
  for (const q of ['Mayfair', 'Hendon']) {
    await page.evaluate((s) => triggerSearch(s), q);
    const t = await answered(page);
    ok(!FAILS.test(t) && t !== 'no answer in 15 s', `"${q}" leads to an answer (its postcode was retired)`, t);
  }
  await ctx.close();
}
{
  // I-16: after a city switch the empty panel has no subject, so a profile change brings no postcode back.
  const { ctx, page } = await visit('');
  await page.evaluate(() => triggerSearch('Hounslow'));
  await answered(page);
  await page.evaluate(() => switchCity('manchester'));
  await page.waitForSelector('#tab-analysis .no-result-yet', { timeout: 15000 }).catch(() => {});
  await page.evaluate(() => setPersona('family'));
  await page.waitForTimeout(500);
  const after = await page.evaluate(() => ({ title: document.getElementById('sidebar-title')?.textContent.trim(), empty: !!document.querySelector('#tab-analysis .no-result-yet') }));
  ok(after.empty && after.title === 'PROPERTY INTELLIGENCE', 'a profile change after a city switch keeps the empty panel: the old result never comes back', JSON.stringify(after));
  await ctx.close();
}
{
  // I-13: outside London, a click after a profile change shows the NEW profile's score (the table is read at click time).
  const { ctx, page } = await visit('?city=manchester');
  await page.waitForFunction(() => currentCity === 'manchester' && document.querySelectorAll('path.borough').length === 10, null, { timeout: 15000 }).catch(() => {});
  await page.evaluate(() => setPersona('investor'));
  const want = await page.evaluate(() => getActiveBoroughData().Trafford?.score);
  await page.evaluate(() => {
    const el = [...document.querySelectorAll('path.borough')].find((p) => p.__data__?.properties?.name === 'Trafford');
    el?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });
  await page.waitForFunction(() => /TRAFFORD/.test(document.getElementById('sidebar-title')?.textContent || ''), null, { timeout: 10000 }).catch(() => {});
  const panel = await page.evaluate(() => document.getElementById('sidebar-content')?.innerText || '');
  ok(typeof want === 'number' && panel.includes(`${want.toFixed(1)}/10`) && /Investor/.test(panel),
    'Trafford clicked after choosing Investor shows the Investor score, as the ranking has it', `want ${want} | ${panel.slice(0, 160).replace(/\s+/g, ' ')}`);
  await ctx.close();
}
for (const [what, q, want] of [['a postcode', 'TW9 3PZ', /TW9 3PZ/], ['a borough', 'Hounslow', /HOUNSLOW/]]) {
  // I-18: on a phone, a profile chosen in Rankings with a result open keeps the phone on Rankings (it was thrown back to
  // Search, the table drawn over the map), and the result is redrawn for the new profile, still the same result.
  const { ctx, page } = await visit('', { width: 390, height: 844 });
  await page.evaluate((s) => triggerSearch(s), q);
  await answered(page);
  await page.locator('.mobile-nav-btn[data-mview="ranking"]').click();
  await page.waitForFunction(() => document.querySelector('.app')?.dataset.mview === 'ranking', null, { timeout: 5000 }).catch(() => {});
  await page.locator('#persona-bar .persona-btn[data-persona="family"]').click();
  await page.waitForTimeout(600);
  const st = await page.evaluate(() => ({
    mview: document.querySelector('.app')?.dataset.mview,
    nav: document.querySelector('.mobile-nav-btn[aria-current="page"]')?.dataset.mview,
    persona: currentPersona,
    title: document.getElementById('sidebar-title')?.textContent.trim(),
  }));
  ok(st.mview === 'ranking' && st.nav === 'ranking' && st.persona === 'family' && want.test(st.title),
    `on a phone, a profile chosen in Rankings with ${what} open stays on Rankings and keeps the result`, JSON.stringify(st));
  await ctx.close();
}
{
  // M-14: on a phone with a result card open, Escape on the Layers popover closes the popover only; a second closes the card.
  const { ctx, page } = await visit('', { width: 390, height: 844 });
  await page.evaluate(() => triggerSearch('TW9 3PZ'));
  await answered(page);
  // A keyboard user's path (Escape is a key): the open card covers the Layers button on a phone, so a pointer cannot reach it.
  await page.locator('#layers-trigger').focus();
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.getElementById('layers-trigger')?.getAttribute('aria-expanded') === 'true', null, { timeout: 5000 }).catch(() => {});
  const cardOpen = () => page.evaluate(() => !document.querySelector('#tab-analysis .no-result-yet') && getComputedStyle(document.getElementById('result-close')).display !== 'none');
  const before = { popover: await page.evaluate(() => document.getElementById('layers-trigger').getAttribute('aria-expanded')), card: await cardOpen() };
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  const first = { popover: await page.evaluate(() => document.getElementById('layers-trigger').getAttribute('aria-expanded')), card: await cardOpen() };
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  const second = { card: await cardOpen() };
  ok(before.popover === 'true' && before.card && first.popover === 'false' && first.card && !second.card,
    'on a phone, Escape on the Layers popover closes it and leaves the result card open; a second Escape closes the card', JSON.stringify({ before, first, second }));
  await ctx.close();
}
{
  // I-17: the first San Francisco ZIP of a session keeps its ZIP once the neighbourhood list arrives.
  const { ctx, page } = await visit('?city=bayarea');
  await page.waitForFunction(() => currentCity === 'bayarea' && document.querySelectorAll('path.borough').length > 20, null, { timeout: 20000 }).catch(() => {});
  await page.evaluate(() => triggerSearch('94103'));
  await page.waitForFunction(() => /ZIP 94103/.test(document.getElementById('sidebar-title')?.textContent || ''), null, { timeout: 15000 }).catch(() => {});
  await page.waitForFunction(() => typeof bayTiers !== 'undefined' && !!bayTiers.loaded, null, { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(800);
  const zipNow = await page.evaluate(() => ({ title: document.getElementById('sidebar-title')?.textContent.trim(), card: /ZIP 94103/.test(document.getElementById('sidebar-content')?.innerText || ''), loaded: typeof bayTiers !== 'undefined' && !!bayTiers.loaded }));
  ok(zipNow.loaded && /ZIP 94103/.test(zipNow.title) && zipNow.card, 'the first San Francisco ZIP keeps its ZIP card after the neighbourhood list arrives', JSON.stringify(zipNow));
  await ctx.close();
}

await browser.close();
server.close();
ok(errors.length === 0, 'no page errors', errors.join(' | '));
console.log(failed ? `FAIL: ${passed} of ${passed + failed} checks` : `PASS: ${passed} of ${passed} checks`);
process.exit(failed ? 1 : 0);
