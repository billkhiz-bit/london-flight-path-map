/**
 * Saved-location rows: every action reachable by keyboard, none nested.
 *
 * WHY THIS EXISTS (2026-09-13, audit I3). The favourites row was a
 * role="button" container with a real <button class="fav-remove"> inside it -
 * nested interactive - and makeKeyActivatable's keydown handler called
 * preventDefault() on Enter and Space. Both keys bubble from the inner button,
 * so Enter on the remove x suppressed the button's own activation and ran the
 * ROW's handler instead: it switched city and re-ran the search. There was no
 * keyboard route to delete a saved location, and nothing could see it, because
 * no gate had ever rendered a populated favourites list - axe had never been
 * shown one.
 *
 * Three assertions, each of which the pre-fix tree fails:
 *   1. axe `nested-interactive` over the rendered list is empty.
 *   2. Enter on a row's remove button DELETES that row and does NOT run a
 *      search. Asserted on the DOM and on a stubbed triggerSearch, because
 *      "the row is gone" and "the search did not run" are two facts.
 *   3. Enter on a row's open button DOES run the search for that postcode.
 *      The positive half, so a fix that made every key inert would not pass.
 *
 * Three more since 2026-09-14 (audit M30), each red on the 13 Sep tree:
 *   4. After Enter on remove, focus is INSIDE the list - on the row that took
 *      the removed one's place, or on the list itself once none remain -
 *      never on <body>. A re-render destroys the focused control, and a
 *      destroyed focused element drops focus silently.
 *   5. The removal is ANNOUNCED: #favourites-status names the postcode.
 *   6. The open button's accessible name carries the row's data (borough,
 *      score), not an aria-label that replaced it.
 *
 * Serves the WORKING TREE. RED-PROOF: `SKY_INDEX=<path>` serves that file as
 * /index.html instead, so the gate can be run against a checked-out pre-fix
 * copy - it was: axe named both rows as nested, and Enter on the remove
 * control ran the search for SW11 1AA and deleted nothing.
 *
 * Run: node tests/favourites-keyboard.mjs
 */

import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join } from 'node:path';
import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

/* global switchTab -- a page function, called inside page.evaluate */

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
const PORT = 8942;
const INDEX = process.env.SKY_INDEX || join(ROOT, 'index.html');
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

const browser = await chromium.launch();
// axe-core/playwright rejects the implicit context browser.newPage() creates.
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

// The favourites API is answered locally: the list LOADS from it when the tab
// opens, and the remove handler DELETEs against it before touching the DOM.
// So the rows arrive the way production delivers them, the gate spends
// nothing, needs no device token, and a network failure cannot masquerade as
// "Enter did nothing". (Setting `userFavourites` by hand and then opening the
// tab loses the race to that load, which re-renders from the response.)
// Two rows, so removing one leaves the other to prove the open path on.
const SAVED = [
  { postcode: 'SW11 1AA', city: 'london', borough: 'Wandsworth', noiseLevel: 'Low', buyerScore: 5.0 },
  { postcode: 'M1 1AE', city: 'manchester', borough: 'Manchester', noiseLevel: 'Low', buyerScore: 7.7 },
];
let deletes = 0;
await page.route((u) => /\/favourites$/.test(u.pathname), async (route) => {
  if (route.request().method() === 'DELETE') {
    deletes += 1;
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
  }
  return route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ favourites: SAVED }),
  });
});

await page.goto(`http://localhost:${PORT}/index.html`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(3000);

let fail = 0;
const check = (name, ok, detail = '') => {
  console.log(`  ${ok ? 'ok  ' : 'FAIL'} ${name}${detail ? '  ' + detail : ''}`);
  if (!ok) fail += 1;
};

await page.evaluate(() => {
  window.__searches = [];
  window.__switches = [];
  // Top-level function declarations in a classic script are writable globals,
  // and the handlers reference them by name, so these stubs are what runs.
  window.triggerSearch = (pc) => { window.__searches.push(pc); };
  window.switchCity = async (c) => { window.__switches.push(c); };
  switchTab('favourites');
});
// Poll for the STATE, not the clock: the rows appear when the stubbed load
// resolves, and a fixed wait is either flaky or slow.
await page.waitForFunction(
  () => document.querySelectorAll('#favourites-list .fav-item').length === 2, null, { timeout: 15000 },
).catch(() => {});
const rows = await page.locator('#favourites-list .fav-item').count();
check('two saved rows rendered from the (stubbed) favourites API', rows === 2, `rows=${rows}`);

// 1. Nothing interactive inside anything interactive.
const axe = await new AxeBuilder({ page })
  .include('#favourites-list')
  .withRules(['nested-interactive'])
  .analyze();
const nested = axe.violations.find((v) => v.id === 'nested-interactive');
check(
  'no nested interactive controls in the list',
  !nested,
  nested ? `${nested.nodes.length} node(s): ${nested.nodes.map((n) => n.target.join(' ')).join('; ')}` : '',
);

// 2. Enter on the remove control removes, and only removes.
const removeBtn = page.locator('#favourites-list [data-fav-remove="SW11 1AA"]');
await removeBtn.focus();
await page.keyboard.press('Enter');
await page.waitForTimeout(400);
const after = await page.evaluate(() => ({
  rows: document.querySelectorAll('#favourites-list .fav-item').length,
  stillThere: !!document.querySelector('#favourites-list [data-fav-remove="SW11 1AA"]'),
  searches: window.__searches.slice(),
  switches: window.__switches.slice(),
}));
check(
  'Enter on the remove control deletes that row',
  deletes === 1 && after.rows === 1 && !after.stillThere,
  `deletes=${deletes} rows=${after.rows} sw11-present=${after.stillThere}`,
);
check(
  'Enter on the remove control does NOT run a search',
  after.searches.length === 0 && after.switches.length === 0,
  `searches=${JSON.stringify(after.searches)} switches=${JSON.stringify(after.switches)}`,
);

// 4-5. Focus survives the re-render, and the removal is announced.
const focusAfter = await page.evaluate(() => {
  const a = document.activeElement;
  const list = document.getElementById('favourites-list');
  return {
    tag: a ? a.tagName.toLowerCase() : 'none',
    inList: !!(a && list && list.contains(a)),
    onRemove: !!(a && a.matches && a.matches('.fav-remove')),
    postcode: a && a.dataset ? a.dataset.favRemove || null : null,
    status: (document.getElementById('favourites-status') || {}).textContent || '',
  };
});
check(
  'after Enter on remove, focus is on the row that took its place',
  focusAfter.inList && focusAfter.onRemove && focusAfter.postcode === 'M1 1AE',
  `activeElement=${focusAfter.tag} inList=${focusAfter.inList} onRemove=${focusAfter.onRemove} postcode=${focusAfter.postcode}`,
);
check(
  'the removal is announced by name',
  /SW11 1AA/.test(focusAfter.status) && /1 remaining/.test(focusAfter.status),
  `status="${focusAfter.status}"`,
);

// 6. The open button's accessible name is the row's data, not a label over it.
const openName = await page.evaluate(() => {
  const b = document.querySelector('#favourites-list [data-fav-postcode="M1 1AE"]');
  if (!b) return null;
  return { label: b.getAttribute('aria-label'), text: (b.textContent || '').replace(/\s+/g, ' ').trim() };
});
check(
  'the open control is named by its content (borough and score audible)',
  !!openName && openName.label === null && /Manchester/.test(openName.text) && /7\.7/.test(openName.text),
  JSON.stringify(openName),
);

// 3. Enter on the open control runs the search - the positive half.
const openBtn = page.locator('#favourites-list [data-fav-postcode="M1 1AE"]');
const openCount = await openBtn.count();
if (openCount === 0) {
  check('an open control exists for the remaining row', false, 'no [data-fav-postcode="M1 1AE"] - the pre-fix row carries the attribute on a div, which is why this reads the fix\'s selector');
} else {
  await openBtn.focus();
  await page.keyboard.press('Enter');
  await page.waitForTimeout(400);
  const opened = await page.evaluate(() => ({ searches: window.__searches.slice(), switches: window.__switches.slice() }));
  check(
    'Enter on the open control searches that postcode',
    opened.searches.length === 1 && opened.searches[0] === 'M1 1AE' && opened.switches[0] === 'manchester',
    `searches=${JSON.stringify(opened.searches)} switches=${JSON.stringify(opened.switches)}`,
  );
}

// 4b. Remove the LAST row too: focus must land on the list, whose empty-state
// sentence is then what a screen reader gets, and the status must say so.
const lastRemove = page.locator('#favourites-list [data-fav-remove="M1 1AE"]');
if ((await lastRemove.count()) === 1) {
  await lastRemove.focus();
  await page.keyboard.press('Enter');
  await page.waitForTimeout(400);
  const empty = await page.evaluate(() => ({
    onList: document.activeElement === document.getElementById('favourites-list'),
    rows: document.querySelectorAll('#favourites-list .fav-item').length,
    status: (document.getElementById('favourites-status') || {}).textContent || '',
  }));
  check(
    'removing the last row puts focus on the list, not <body>',
    empty.onList && empty.rows === 0,
    `onList=${empty.onList} rows=${empty.rows} deletes=${deletes}`,
  );
  check('the last removal says none remain', /None remaining/.test(empty.status), `status="${empty.status}"`);
}

await browser.close();
server.close();
console.log('');
if (fail) {
  console.error(`FAIL: ${fail} favourites keyboard check(s) failed`);
  process.exit(1);
}
console.log('OK: saved-location rows are keyboard-operable and not nested');
