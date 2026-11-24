/**
 * Delete all saved places (Bill's pick A, 2026-11-23; mock-up claude.ai/artifact/86m9oyizi3kZiuDpUSdZx4).
 *
 * Every state reached on purpose, each against a stubbed favourites API (nothing is spent, nothing live is touched):
 *   0. A browser that never saved holds no token: the map makes none and asks for no list (privacy s2e: "It is created
 *      only when you save something. Browsing and scoring never generate one." Until 2026-11-23 every page load made
 *      one and sent it).
 *   1. The link shows under a loaded list. Pressed, it asks IN PLACE, focus on the question; "Keep them" sends nothing
 *      and puts focus back on the link.
 *   2. "Delete all" sends ONE request naming every listed place; the list says "Deleted", the removal is announced,
 *      focus is on the list, and the browser's token is gone.
 *   3. A failed request deletes nothing on screen, keeps the token, says so, and offers the link again.
 *   4. A partial answer (the Lambda names a place back in notDeleted) keeps that place and the token, and says how many.
 *   5. One place takes the singular. 6. At a phone's 390 the controls fit the panel and are at least 24 px tall.
 *   Code review, 2026-11-24:
 *   7. While it deletes, the buttons are busy through aria-disabled (never `disabled`, which drops focus) and a second
 *      press asks nothing; a save made meanwhile WAITS, then goes under a new token, and the list keeps it (it was
 *      dropped, its token forgotten, the place left stored with nothing pointing at it).
 *   8. After a failed Delete all, a removal that works takes the "Nothing was deleted" note away.
 *   9. A save button on screen follows the list: SAVE after Delete all, never a stale SAVED that saves again.
 *
 * Serves the WORKING TREE. RED-PROOF: `SKY_INDEX=<path>` serves that file as /index.html instead.
 * Run: node tests/favourites-delete-all.mjs
 */

import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join } from 'node:path';
import { chromium } from 'playwright';

/* global switchTab, saveFavourite -- page functions, called inside page.evaluate */

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
const PORT = 8943;
const INDEX = process.env.SKY_INDEX || join(ROOT, 'index.html');
const TOKEN = '550e8400-e29b-41d4-a716-446655440000';
const TYPES = {
  '.html': 'text/html', '.js': 'application/javascript', '.mjs': 'application/javascript',
  '.json': 'application/json', '.css': 'text/css', '.png': 'image/png',
  '.svg': 'image/svg+xml', '.webmanifest': 'application/manifest+json', '.woff2': 'font/woff2',
};
const server = createServer(async (req, res) => {
  const url = decodeURIComponent(req.url.split('?')[0]);
  try {
    const file = url === '/' || url === '/index.html' ? INDEX : join(ROOT, url);
    const buf = await readFile(file);
    res.writeHead(200, { 'content-type': TYPES[extname(url)] || 'application/octet-stream' });
    res.end(buf);
  } catch { res.writeHead(404); res.end('nf'); }
});
await new Promise((r) => server.listen(PORT, r));

const THREE = [
  { postcode: 'TW9 3PZ', city: 'london', borough: 'Richmond upon Thames', noiseLevel: 'moderate', buyerScore: '6.4' },
  { postcode: 'SW1P 3JA', city: 'london', borough: 'Westminster', noiseLevel: 'low', buyerScore: '5.9' },
  { postcode: 'M22 5RX', city: 'manchester', borough: 'Manchester', noiseLevel: 'high', buyerScore: '5.1' },
];

let fail = 0;
const check = (name, ok, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${name}${detail ? '  ' + detail : ''}`);
  if (!ok) fail += 1;
};

const browser = await chromium.launch();

/** A fresh map with `saved` behind the stub; `answer(body)` gives the DELETE's reply. */
async function open({ saved = THREE, token = TOKEN, answer = () => ({ status: 200, body: { notDeleted: [] } }), hold = null, width = 1366, height = 768 } = {}) {
  const context = await browser.newContext({ viewport: { width, height }, isMobile: width < 500, hasTouch: width < 500 });
  if (token) await context.addInitScript((t) => { if (!sessionStorage.getItem('seeded')) { localStorage.setItem('flightmap_device_token', t); sessionStorage.setItem('seeded', '1'); } }, token);
  const page = await context.newPage();
  const seen = { gets: 0, deletes: [], posts: [], tokens: [] };
  await page.route((u) => /\/favourites$/.test(u.pathname), async (route) => {
    const req = route.request();
    seen.tokens.push(req.headers()['x-device-token'] || null);
    if (req.method() === 'DELETE') {
      const body = JSON.parse(req.postData() || '{}');
      seen.deletes.push(body);
      if (hold && body.postcodes) await hold; // a Delete all answers only when the test lets it
      const out = answer(body);
      return route.fulfill({ status: out.status, contentType: 'application/json', body: JSON.stringify(out.body) });
    }
    if (req.method() === 'POST') {
      seen.posts.push({ token: req.headers()['x-device-token'] || null, body: JSON.parse(req.postData() || '{}') });
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ saved: true }) });
    }
    seen.gets += 1;
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ favourites: saved }) });
  });
  await page.goto(`http://localhost:${PORT}/index.html`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof switchTab === 'function', null, { timeout: 20000 });
  await page.evaluate(() => switchTab('favourites'));
  return { context, page, seen };
}
const state = (page) => page.evaluate(() => ({
  rows: document.querySelectorAll('#favourites-list .fav-item').length,
  list: document.getElementById('favourites-list')?.textContent.trim().replace(/\s+/g, ' '),
  // Element by element, so a paragraph and the button after it read as two things.
  box: [...(document.getElementById('favourites-delete-all')?.querySelectorAll('p, button') || [])].map((e) => e.textContent.trim()).join(' | '),
  focus: document.activeElement?.id || document.activeElement?.dataset?.favAll || document.activeElement?.tagName,
  status: document.getElementById('favourites-status')?.textContent || '',
  token: localStorage.getItem('flightmap_device_token'),
}));
const waitRows = (page, n) => page.waitForFunction((k) => document.querySelectorAll('#favourites-list .fav-item').length === k, n, { timeout: 15000 }).catch(() => {});

console.log('0. No token: nothing made, nothing asked');
{
  const { context, page, seen } = await open({ token: null });
  await page.waitForTimeout(3000);
  const s = await state(page);
  check('a browser that never saved sends no favourites request', seen.gets === 0 && seen.tokens.length === 0, JSON.stringify(seen));
  check('and is given no token by browsing', s.token === null, `token=${s.token}`);
  check('its Saved tab says nothing is saved and offers no Delete all', /No saved locations yet/.test(s.list) && s.box === '', JSON.stringify(s));
  await context.close();
}

console.log('1-2. Ask, keep, ask, delete');
{
  const { context, page, seen } = await open();
  await waitRows(page, 3);
  let s = await state(page);
  check('the link shows under a loaded list of 3', s.rows === 3 && s.box === 'Delete all saved places', JSON.stringify(s));
  await page.focus('[data-fav-all="ask"]');
  await page.keyboard.press('Enter');
  s = await state(page);
  check('pressed, it asks in place, focus on the question', s.focus === 'fav-confirm-q'
    && s.box.startsWith("Delete all 3 saved places? They go from our server too, and this can't be undone."), JSON.stringify(s));
  await page.focus('[data-fav-all="no"]');
  await page.keyboard.press('Enter');
  s = await state(page);
  check('"Keep them" sends nothing and puts focus back on the link', seen.deletes.length === 0 && s.focus === 'ask' && s.rows === 3, JSON.stringify(s));
  await page.click('[data-fav-all="ask"]');
  await page.click('[data-fav-all="yes"]');
  await page.waitForFunction(() => /Deleted\./.test(document.getElementById('favourites-list')?.textContent || ''), null, { timeout: 10000 }).catch(() => {});
  s = await state(page);
  check('ONE request names every listed place', seen.deletes.length === 1
    && JSON.stringify(seen.deletes[0]) === JSON.stringify({ postcodes: ['TW9 3PZ', 'SW1P 3JA', 'M22 5RX'] }), JSON.stringify(seen.deletes));
  check('the list says it is deleted, with no Delete all left', s.rows === 0 && s.list === 'Deleted. Nothing is saved for this browser on our server any more.' && s.box === '', JSON.stringify(s));
  check('the removal is announced and focus is on the list', s.status === 'Deleted all 3 saved places.' && s.focus === 'favourites-list', JSON.stringify(s));
  check("the browser's token is forgotten", s.token === null, `token=${s.token}`);
  const before = seen.gets; // the first visit asked twice: at load, and again when the tab opened
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);
  const after = await state(page);
  check('the next visit asks for no list and makes no new token', seen.gets === before && after.token === null, `gets ${before} -> ${seen.gets} token=${after.token}`);
  await context.close();
}

console.log('3. A failed request');
{
  const { context, page } = await open({ answer: () => ({ status: 503, body: { error: 'Storage backend temporarily unavailable.' } }) });
  await waitRows(page, 3);
  await page.click('[data-fav-all="ask"]');
  await page.click('[data-fav-all="yes"]');
  await page.waitForSelector('#fav-delete-note', { timeout: 10000 }).catch(() => {});
  const s = await state(page);
  check('nothing leaves the list and the token stays', s.rows === 3 && s.token === TOKEN, JSON.stringify(s));
  check('it says nothing was deleted, announced, focus on the note, the link offered again',
    s.box === "Nothing was deleted: we couldn't reach our server. Try again in a moment. | Delete all saved places"
    && s.status.startsWith('Nothing was deleted') && s.focus === 'fav-delete-note', JSON.stringify(s));
  await context.close();
}

console.log('4. A partial answer');
{
  const { context, page } = await open({ answer: () => ({ status: 200, body: { deleted: 2, notDeleted: ['M22 5RX'] } }) });
  await waitRows(page, 3);
  await page.click('[data-fav-all="ask"]');
  await page.click('[data-fav-all="yes"]');
  await page.waitForSelector('#fav-delete-note', { timeout: 10000 }).catch(() => {});
  const s = await state(page);
  check('the place left is still listed and the token stays', s.rows === 1 && /M22 5RX/.test(s.list) && s.token === TOKEN, JSON.stringify(s));
  check('it says how many went', s.box.startsWith('2 of 3 were deleted; 1 is still saved. Try again in a moment.'), JSON.stringify(s));
  await context.close();
}

console.log('5. One place');
{
  const { context, page } = await open({ saved: THREE.slice(0, 1) });
  await waitRows(page, 1);
  await page.click('[data-fav-all="ask"]');
  const s = await state(page);
  check('one place takes the singular', s.box === "Delete your saved place? It goes from our server too, and this can't be undone. | Delete all | Keep it", JSON.stringify(s));
  await context.close();
}

console.log('6. A phone');
{
  const { context, page } = await open({ width: 390, height: 844 });
  await page.evaluate(() => document.querySelector('.mobile-nav-btn[data-mview="saved"]')?.click());
  await waitRows(page, 3);
  await page.click('[data-fav-all="ask"]');
  const m = await page.evaluate(() => {
    const panel = document.getElementById('tab-favourites').getBoundingClientRect();
    return [...document.querySelectorAll('#favourites-delete-all button')].map((b) => {
      const r = b.getBoundingClientRect();
      return { h: Math.round(r.height), inside: r.left >= panel.left - 0.5 && r.right <= panel.right + 0.5, visible: r.width > 0 };
    }).concat([{ scroll: document.documentElement.scrollWidth <= window.innerWidth }]);
  });
  const buttons = m.slice(0, -1);
  check('both buttons show inside the panel, each at least 24 px tall', buttons.length === 2 && buttons.every((b) => b.visible && b.inside && b.h >= 24), JSON.stringify(m));
  check('and nothing scrolls sideways', m.at(-1).scroll, JSON.stringify(m.at(-1)));
  await context.close();
}

console.log('7. A save while Delete all is on its way');
{
  let release;
  const hold = new Promise((r) => { release = r; });
  const { context, page, seen } = await open({ hold });
  await waitRows(page, 3);
  await page.click('[data-fav-all="ask"]');
  await page.click('[data-fav-all="yes"]');
  await page.waitForFunction(() => document.querySelector('[data-fav-all="yes"]')?.getAttribute('aria-disabled') === 'true', null, { timeout: 5000 }).catch(() => {});
  const busy = await page.evaluate(() => {
    const b = [...document.querySelectorAll('#favourites-delete-all button')];
    return { aria: b.map((x) => x.getAttribute('aria-disabled')), disabled: b.some((x) => x.disabled), focus: document.activeElement?.id, text: b[0]?.textContent };
  });
  check('while it deletes, both buttons are busy through aria-disabled, never disabled, focus on the question',
    busy.aria.length === 2 && busy.aria.every((a) => a === 'true') && !busy.disabled && busy.focus === 'fav-confirm-q' && busy.text === 'Deleting…', JSON.stringify(busy));
  // A press while busy (a script click: Playwright will not click an aria-disabled button) asks nothing more.
  await page.evaluate(() => document.querySelector('[data-fav-all="yes"]')?.click());
  const saving = page.evaluate(() => saveFavourite('LS1 4DY', 'Leeds', 'low', 6));
  await page.waitForTimeout(800);
  check('the save waits: nothing is posted while the delete is on its way', seen.posts.length === 0, JSON.stringify(seen.posts));
  release();
  const ok = await saving;
  await page.waitForFunction(() => /LS1 4DY/.test(document.getElementById('favourites-list')?.textContent || ''), null, { timeout: 10000 }).catch(() => {});
  const s = await state(page);
  check('then it is posted under a NEW token, never the one the delete forgot', ok === true && seen.posts.length === 1
    && !!seen.posts[0].token && seen.posts[0].token !== TOKEN && seen.posts[0].token === s.token, JSON.stringify({ ok, posts: seen.posts, token: s.token }));
  check('and the list holds it', s.rows === 1 && /LS1 4DY/.test(s.list), JSON.stringify(s));
  check('a press while busy sent no second delete', seen.deletes.length === 1, JSON.stringify(seen.deletes));
  await context.close();
}

console.log('8. After a failed Delete all, a removal that works clears the note');
{
  const { context, page } = await open({ answer: (body) => (body.postcodes ? { status: 503, body: { error: 'Storage backend temporarily unavailable.' } } : { status: 200, body: {} }) });
  await waitRows(page, 3);
  await page.click('[data-fav-all="ask"]');
  await page.click('[data-fav-all="yes"]');
  await page.waitForSelector('#fav-delete-note', { timeout: 10000 }).catch(() => {});
  await page.click('[data-fav-remove="TW9 3PZ"]');
  await waitRows(page, 2);
  const s = await state(page);
  check('the "Nothing was deleted" note is gone and the link stays', s.rows === 2 && s.box === 'Delete all saved places', JSON.stringify(s));
  await context.close();
}

console.log('9. A save button on screen says what the list says');
{
  const { context, page } = await open();
  await waitRows(page, 3);
  // The postcode card's button in its builder's markup (index.html `.fav-btn`, data-fav-postcode), drawn SAVED: a card
  // needs a scored search, and the rule under test is the list's, so the button is placed and the list is changed.
  await page.evaluate(() => document.getElementById('sidebar-content')?.insertAdjacentHTML('beforeend',
    '<button class="fav-btn saved" id="fc-fav" data-fav-postcode="TW9 3PZ" data-fav-borough="Richmond upon Thames" data-fav-impact="LOW" data-fav-score="6.4">SAVED</button>'));
  await page.click('[data-fav-all="ask"]');
  await page.click('[data-fav-all="yes"]');
  await page.waitForFunction(() => /Deleted\./.test(document.getElementById('favourites-list')?.textContent || ''), null, { timeout: 10000 }).catch(() => {});
  const b = await page.evaluate(() => {
    const x = document.getElementById('fc-fav');
    return x ? { saved: x.classList.contains('saved'), text: x.textContent.trim() } : null;
  });
  check("after Delete all, the card's button says SAVE, not SAVED", !!b && !b.saved && b.text === 'SAVE', JSON.stringify(b));
  await context.close();
}

await browser.close();
server.close();
console.log('');
if (fail) {
  console.error(`FAIL: ${fail} delete-all check(s) failed`);
  process.exit(1);
}
console.log('OK: Delete all saved places, every state');
