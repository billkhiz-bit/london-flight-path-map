// /api/'s "Try a request" (2026-11-05): a reader sends a postcode and sees the real request and its real answer.
//
// WHY THIS EXISTS. The band is the front page's (js/dev-demo.mjs), but the front page only ever shows one example, so its
// tests reach one shape. Here a reader can reach all of them, and the answers are REAL ones from the live route
// (tests/fixtures/api-demo-env.json): figures for the postcode asked, for a neighbour, some figures only, a postcode with
// no point, a postcode nobody knows, no figures, a failure, and a late reply overtaken by a newer one. Each is read in the
// browser, under the page's own Content Security Policy, at 1366 and 390 and with reduced motion. It also holds what must
// never happen: a request to /v1/score (it would spend the public demo key), a lookup on postcodes.io before a reader
// sends anything, a postcode in a counted name, a sample showing a point other than the one answered, a missing figure
// shown as a zero, a quiet road called missing.
//
//   node tests/api-demo.mjs

import { chromium } from '@playwright/test';
import { strict as assert } from 'node:assert';
import { readFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { dirname, extname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { atPoint, devAnswer } from '../js/dev-demo.mjs';
import { EXAMPLE, answeredFor, askPoint, cleanPostcode, lookup, sayAnswer, sayProblem } from '../js/api-demo.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const REAL = JSON.parse(readFileSync(join(ROOT, 'tests/fixtures/api-demo-env.json'), 'utf8'));
const PORT = Number(process.env.API_DEMO_PORT) || 8947;
const API = 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod';

let failures = 0, checks = 0;
const ok = (cond, label, detail = '') => {
  checks += 1;
  if (!cond) failures += 1;
  console.log(`  ${cond ? 'ok  ' : 'FAIL'} ${label}${cond || !detail ? '' : `: ${detail}`}`);
};
const same = (got, want, label) => ok(JSON.stringify(got) === JSON.stringify(want), label, `got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);

// ---- pure: what the module decides, without a browser ----

console.log('The postcode as typed');
for (const [typed, want] of [['sw5 9hp', 'SW5 9HP'], ['  SW59HP ', 'SW5 9HP'], ['sw5-9hp', 'SW5 9HP'], ['M1 1AE', 'M1 1AE'], ['w1a0ax', 'W1A 0AX'], ['SW1A 1AA', 'SW1A 1AA']]) {
  same(cleanPostcode(typed), want, `"${typed}" reads as ${want}`);
}
for (const typed of ['', '   ', '10001', 'SW5', 'Kew', 'SW5 9HPX', null, undefined]) same(cleanPostcode(typed), null, `"${typed}" is not a postcode`);

console.log('The two lookups, as one outcome');
const reply = (status, body) => ({ status, ok: status >= 200 && status < 300, json: async () => body });
const asked = (place, env) => {
  const urls = [];
  const signals = [];
  const get = async (url, options) => {
    urls.push(url);
    signals.push(options?.signal);
    const r = url.includes('postcodes.io') ? place : env;
    if (r instanceof Error) throw r;
    return r;
  };
  return { urls, signals, get };
};
const kew = REAL.TW93PZ;
const geoReply = reply(200, { result: kew.geo });
{
  const { urls, signals, get } = asked(geoReply, reply(200, kew.env));
  const stop = new AbortController();
  const out = await lookup('TW9 3PZ', API, { get, signal: stop.signal });
  same(out.kind, 'answer', 'a postcode with figures is an answer');
  same(urls, ['https://api.postcodes.io/postcodes/TW93PZ', `${API}/v1/environment?lat=${kew.geo.latitude}&lon=${kew.geo.longitude}`], 'it asks postcodes.io, then the open route at that point');
  ok(signals.length === 2 && signals.every((s) => s === stop.signal), 'and a newer request can cancel both');
}
{
  const { urls, get } = asked(reply(500, {}), reply(200, kew.env));
  const out = await askPoint(EXAMPLE, API, { get });
  ok(out.kind === 'answer' && urls.length === 1 && !urls[0].includes('postcodes.io'), 'the example asks only the API, at its held point');
  same([EXAMPLE.postcode, EXAMPLE.latitude, EXAMPLE.longitude], [kew.geo.postcode, kew.geo.latitude, kew.geo.longitude], 'and that point is really the example\'s, as postcodes.io has it');
}
for (const [label, place, env, kind, calls] of [
  ['postcodes.io says 404', reply(404, {}), null, 'unknown', 1],
  ['postcodes.io says 200 with no result', reply(200, { result: null }), null, 'unknown', 1],
  ['a point with no latitude (the Isle of Man)', reply(200, { result: { postcode: 'IM1 1AD', latitude: null, longitude: null } }), null, 'no-point', 1],
  ['postcodes.io says 500', reply(500, {}), null, 'failed', 1],
  ['postcodes.io cannot be reached', new TypeError('Failed to fetch'), null, 'failed', 1],
  ['the route finds no postcode (404)', geoReply, reply(404, { error: 'No UK postcode found near those coordinates.' }), 'no-postcode', 2],
  ['the route says 500', geoReply, reply(500, {}), 'failed', 2],
  ['the route says 429 (a throttle, readable since its gateway reply carries CORS)', geoReply, reply(429, { message: 'Too Many Requests' }), 'busy', 2],
  ['the route says 503 (its own postcode lookup failed)', geoReply, reply(503, { error: 'The postcode lookup this route depends on is unavailable just now. Try again shortly.' }), 'failed', 2],
  ['the route says 502', geoReply, reply(502, { message: 'Internal server error' }), 'failed', 2],
  ['a reply the browser cannot read', geoReply, new TypeError('Failed to fetch'), 'failed', 2],
  ['the route answers with no figures', geoReply, reply(200, { location: { postcode: 'TW9 3PZ' }, environment: {} }), 'no-figures', 2],
  ['the route answers with no environment', geoReply, reply(200, {}), 'no-figures', 2],
  ['the route answers something unreadable', geoReply, { status: 200, ok: true, json: async () => { throw new SyntaxError('not json'); } }, 'failed', 2],
]) {
  const { urls, get } = asked(place, env);
  const out = await lookup('TW9 3PZ', API, { get });
  ok(out.kind === kind && urls.length === calls, `${label}: ${kind}, ${calls} request${calls > 1 ? 's' : ''}`, `${out.kind}, ${urls.length}`);
}

console.log('What a reader is told');
same(sayAnswer('TW9 3PZ', kew.env), 'Answered for TW9 3PZ.', 'all three figures: just whose answer it is');
same(sayAnswer('SW5 9HP', REAL.SW59HP.env), 'Answered for SW5 9HP. We hold no figure here for aircraft noise.', 'a figure the answer lacks is said to be missing');
same(sayAnswer('EX1 1HS', REAL.EX11HS.env), 'Answered for EX1 1HS. Outside the city regions we cover, we hold no figure for aircraft noise and road noise, though DEFRA may map this place.', 'outside our city regions it says what we hold, never what DEFRA has');
ok(sayAnswer('ZE1 0AA', REAL.ZE10AA.env).startsWith('Answered for ZE1 9ZZ, the nearest postcode the API found to ZE1 0AA.'), 'a neighbour is named, with the postcode asked', sayAnswer('ZE1 0AA', REAL.ZE10AA.env));
ok(!/road noise/.test(sayAnswer('NG11 8AH', REAL.NG118AH.env)), 'a quiet road is a reading, so it is never called missing', sayAnswer('NG11 8AH', REAL.NG118AH.env));
same(answeredFor('TW9 3PZ', { environment: {} }), 'TW9 3PZ', 'an answer naming no postcode stands for the one asked');
for (const kind of ['unknown', 'no-point', 'no-postcode', 'no-figures']) ok(sayProblem(kind, 'SW5 9XX', null).includes('SW5 9XX'), `${kind} names the postcode`);
ok(/busy/.test(sayProblem('busy', 'SW5 9HP', null)), 'a 429 says the API is busy');
ok(!/busy/.test(sayProblem('failed', 'SW5 9HP', null)), 'any other failure never guesses it was a throttle');
ok(sayProblem('unknown', 'SW5 9XX', 'TW9 3PZ').endsWith('Still showing TW9 3PZ.'), 'with an answer still on the page, it says whose');
ok(!/Still showing|undefined|null/.test(sayProblem('failed', 'SW5 9HP', null)), 'with nothing on the page, it claims nothing');

console.log('The sample at a new point');
same(atPoint("lat=51.5&lon=0.1", { lat: '51.5', lon: '0.1' }, 50.1, 0.2), 'lat=50.1&lon=0.2', "a new latitude holding the old longitude's digits survives");
same(atPoint("{'lat': 51.5, 'lon': 0.1} lat=51.5", { lat: '51.5', lon: '0.1' }, 53.48, -2.23), "{'lat': 53.48, 'lon': -2.23} lat=53.48", 'every place the point is named moves');
same(devAnswer(REAL.EX11HS.env).missing, ['aircraft noise', 'road noise'], 'the band knows which figures an answer lacks');
same(devAnswer(kew.env).missing, [], 'and that a whole answer lacks none');
same(devAnswer(REAL.NG118AH.env).figures.find((f) => f.words === 'road noise')?.figure, `under ${REAL.NG118AH.env.environment.roadNoiseBelowDb} dB`, 'a quiet road reads as its bound');

// ---- the page, as a visitor gets it ----

const TYPES = { '.html': 'text/html', '.mjs': 'application/javascript', '.js': 'application/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon' };
const server = createServer(async (req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]);
  if (p.endsWith('/')) p += 'index.html';
  try {
    const buf = await readFile(join(ROOT, p));
    res.writeHead(200, { 'Content-Type': TYPES[extname(p)] || 'application/octet-stream' });
    res.end(buf);
  } catch { res.writeHead(404); res.end('not found'); }
});
await new Promise((r) => server.listen(PORT, '127.0.0.1', r));

// Postcodes that exist only here, each a shape the live route can give but no real postcode can be relied on to.
const point = (latitude, longitude) => ({ latitude, longitude });
const MADE_UP = {
  AB12CD: { geo: point(57.1, -2.1), env: { body: { location: { postcode: 'AB1 2CD' }, environment: {}, notices: [] } } },
  BB11BB: { geo: point(53.7, -2.4), env: { status: 404, body: { error: 'No UK postcode found near those coordinates.' } } },
  CC11CC: { geo: point(54.8, -1.5), env: { status: 500, body: { message: 'Internal server error' } } },
  DD11DD: { geo: point(56.4, -2.9), env: { abort: true } },
  FF11FF: { geo: point(52.2, 0.1), env: { status: 429, body: { message: 'Too Many Requests' } } },
  GG11GG: { geo: point(52.6, 1.3), env: { status: 503, body: { error: 'The postcode lookup this route depends on is unavailable just now. Try again shortly.' } } },
  SL11AA: { geo: point(51.5, -0.6), env: { body: REAL.TW93PZ.env }, wait: 900 },
  SL22AA: { geo: point(51.6, -0.7), env: { body: REAL.M11AE.env }, wait: 600 },
  // A whole degree: `-2` read back from a sample would also match the API's host, `eu-west-2`.
  WD11AA: { geo: point(53, -2), env: { body: REAL.M11AE.env } },
};

// What postcodes.io gives for the start of a postcode: a list, or null when it knows none (read 2026-11-06).
const COMPLETIONS = { SW59: ['SW5 9HP', 'SW5 9HQ'], M1: ['M1 2AA'], M11: ['M1 1AE'], E1: ['E1 6AN'], N1: ['N1 9AG'], W1: ['W1A 1AA'], SE1: ['SE1 7PB'] };

async function open(browser, { width, height, motion = 'no-preference', arrival = true, js = true, hold = 0, base = true }) {
  const context = await browser.newContext({ viewport: { width, height }, reducedMotion: motion, javaScriptEnabled: js });
  const page = await context.newPage();
  const seen = { env: [], geo: [], completions: [], score: 0, errors: [], csp: [], cancelled: [] };
  page.on('requestfailed', (r) => { if (/ERR_ABORTED/.test(r.failure()?.errorText || '')) seen.cancelled.push(r.url()); });
  page.on('pageerror', (e) => seen.errors.push(String(e)));
  // A refusal says it refused.
  page.on('console', (m) => { if (/Refused to|violates the following Content Security Policy/i.test(m.text())) seen.csp.push(m.text()); });
  await page.route('**/js/count.mjs', (r) => r.fulfill({ status: 200, contentType: 'application/javascript', body: '' }));
  if (js) await page.addInitScript(() => {
    window.__counted = [];
    window.goatcounter = { count: (v) => window.__counted.push(v.path) };
    window.__shift = 0;
    new PerformanceObserver((l) => { for (const x of l.getEntries()) if (!x.hadRecentInput) window.__shift += x.value; }).observe({ type: 'layout-shift', buffered: true });
  });
  if (!base) await page.route('**/js/api-base.js', (r) => r.fulfill({ status: 200, contentType: 'application/javascript', body: '' }));
  await page.route((u) => u.hostname === 'api.postcodes.io', async (route) => {
    const parts = new URL(route.request().url()).pathname.split('/');
    if (parts.at(-1) === 'autocomplete') {
      const text = parts.at(-2);
      seen.completions.push(text);
      if (text === 'FA1') return route.abort();
      if (text === 'M1' || text === 'W1') await new Promise((r) => setTimeout(r, 900)); // slower than what follows
      return route.fulfill({ json: { status: 200, result: COMPLETIONS[text] ?? null } }).catch(() => {});
    }
    const pc = route.request().url().split('/').pop();
    seen.geo.push(pc);
    if (pc === 'EE11EE') return route.abort();
    if (pc === 'IM11AD') return route.fulfill({ json: { status: 200, result: { postcode: 'IM1 1AD', latitude: null, longitude: null } } });
    const geo = REAL[pc]?.geo || (MADE_UP[pc] && { postcode: pc, ...MADE_UP[pc].geo });
    if (!geo) return route.fulfill({ status: 404, json: { status: 404, error: 'Postcode not found' } });
    return route.fulfill({ json: { status: 200, result: geo } });
  });
  await page.route((u) => u.hostname.endsWith('execute-api.eu-west-2.amazonaws.com'), async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.includes('/v1/score')) { seen.score += 1; return route.abort(); }
    seen.env.push(url.search);
    const lat = Number(url.searchParams.get('lat'));
    if (!arrival && lat === EXAMPLE.latitude) return route.abort();
    if (hold && lat === EXAMPLE.latitude) await new Promise((r) => setTimeout(r, hold));
    const made = Object.values(MADE_UP).find((m) => m.geo.latitude === lat);
    if (made?.wait) await new Promise((r) => setTimeout(r, made.wait));
    if (made?.env.abort) return route.abort();
    // A late reply to a cancelled request has nowhere to go: that is the point of cancelling it.
    if (made) return route.fulfill({ status: made.env.status || 200, json: made.env.body }).catch(() => {});
    const real = Object.values(REAL).find((r) => r.geo?.latitude === lat);
    return real ? route.fulfill({ json: real.env }) : route.fulfill({ status: 500, json: {} });
  });
  await page.goto(`http://127.0.0.1:${PORT}/api/`, { waitUntil: 'load' });
  return { page, seen, context };
}

const state = (page) => page.evaluate(() => ({
  status: document.getElementById('try-status').textContent,
  tiles: [...document.querySelectorAll('#dev-tiles .ans-tile b')].map((b) => b.textContent),
  json: document.getElementById('dev-res').textContent,
  curl: document.getElementById('dev-env').textContent,
  python: document.getElementById('dev-env-py').textContent,
  js: document.getElementById('dev-env-js').textContent,
  hidden: document.getElementById('dev-run').hidden,
  invalid: document.getElementById('try-pc').getAttribute('aria-invalid'),
  copied: document.getElementById('copy-status').textContent,
  busy: document.getElementById('try-form').getAttribute('aria-busy'),
  running: document.getElementById('dev-run').classList.contains('is-waiting'),
}));
const settled = (page) => page.waitForFunction(() => !document.getElementById('try-form').hasAttribute('aria-busy'), null, { timeout: 8000 });
const send = async (page, text) => {
  await page.fill('#try-pc', text);
  await page.click('.try-row button');
  await settled(page);
  return state(page);
};
// Every sample must name the one point, and it must be the point the last request asked about.
const atSamePoint = (s, seen) => {
  const q = /lat=(-?[\d.]+)&lon=(-?[\d.]+)/.exec(seen.env.at(-1));
  return Boolean(q) && s.curl.includes(`lat=${q[1]}&lon=${q[2]}`) && s.js.includes(`lat=${q[1]}&lon=${q[2]}`)
    && s.python.includes(`'lat': ${q[1]}, 'lon': ${q[2]}`);
};

const browser = await chromium.launch();

for (const [width, height] of [[1366, 900], [390, 844], [320, 640]]) {
  console.log(`Suggestions at ${width}px`);
  const { page, seen, context } = await open(browser, { width, height });
  await settled(page);
  const list = () => page.evaluate(() => {
    const box = document.getElementById('try-pc'), l = document.getElementById('try-list');
    const r = l.getBoundingClientRect(), send = document.querySelector('.try-row button').getBoundingClientRect();
    return {
      hidden: l.hidden, expanded: box.getAttribute('aria-expanded'),
      options: [...l.querySelectorAll('[role="option"]')].map((o) => o.dataset.value),
      bare: !l.hidden && !l.querySelector('[role="option"]'),
      overButton: !l.hidden && r.left < send.right && send.left < r.right && r.top < send.bottom && send.top < r.bottom,
      sideways: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      live: document.querySelector('#try-list + .pc-live')?.textContent,
    };
  });
  const past = () => page.waitForTimeout(450);
  await page.click('#try-pc');
  ok((await list()).hidden, 'a first click opens nothing: the chips are the examples');
  for (const text of ['kew', 'SW5 9HP', 'hello there']) {
    await page.fill('#try-pc', text);
    await past();
    ok((await list()).hidden, `"${text}" opens no list and leaves Send clear`);
  }
  same(seen.completions, [], 'and none of them is sent');
  await page.fill('#try-pc', 'sw5 9');
  await page.waitForSelector('#try-list [role="option"]', { timeout: 3000 }).catch(() => {});
  const open1 = await list();
  same(open1.options, ['SW5 9HP', 'SW5 9HQ'], 'the start of a postcode is offered the rest');
  ok(open1.expanded === 'true' && open1.live === '2 suggestions.' && open1.sideways <= 0, 'and it is said, with nothing scrolling sideways', JSON.stringify(open1));
  ok(!open1.overButton, 'and the list opens clear of Send', JSON.stringify(open1));
  // The text's own line boxes: a computed line-height here is "normal", and a guess at it let two lines pass.
  const line = await page.evaluate(() => {
    const words = document.createRange();
    words.selectNodeContents(document.querySelector('#try-list [role="option"] span'));
    const boxes = [...words.getClientRects()];
    return { name: Math.max(...boxes.map((b) => b.bottom)) - Math.min(...boxes.map((b) => b.top)), one: boxes[0].height };
  });
  ok(line.name < line.one * 1.5, 'and each postcode sits on one line', JSON.stringify(line));
  same(seen.completions, ['SW59'], 'asked once, with no space');
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await settled(page);
  ok((await state(page)).status.startsWith('Answered for SW5 9HP.') && atSamePoint(await state(page), seen), 'choosing one sends it, and the samples follow', (await state(page)).status);
  ok(await page.evaluate(() => window.__counted.includes('event/api-demo-pick')), 'counted as a pick, by name only');
  ok(!(await page.evaluate(() => JSON.stringify(window.__counted))).includes('SW5'), 'with no postcode in the count');

  await page.fill('#try-pc', 'm1');
  await page.waitForTimeout(350); // on its way, and slow
  await page.fill('#try-pc', 'm1 1');
  await page.waitForSelector('#try-list [role="option"]', { timeout: 3000 }).catch(() => {});
  await page.waitForTimeout(1100); // past the slow reply
  same((await list()).options, ['M1 1AE'], 'a slower reply for older text never replaces the list');

  await page.fill('#try-pc', 'zz9');
  await past();
  ok((await list()).hidden, 'a start postcodes.io does not know opens nothing');
  await page.fill('#try-pc', 'fa1');
  await past();
  ok((await list()).hidden && seen.errors.length === 0, 'a lookup that fails opens nothing and breaks nothing', seen.errors.join(' '));
  const made = seen.geo.length;
  await page.fill('#try-pc', 'SW5 9HP');
  await page.click('.try-row button');
  await settled(page);
  ok((await state(page)).status.startsWith('Answered for SW5 9HP.') && seen.geo.length === made, 'and the box still sends: a repeat of the postcode on show asks nothing', (await state(page)).status);

  // What ends the box's turn ends the lookup, or a list opens on a reader who has moved on.
  const leave = () => page.evaluate(() => document.getElementById('try-pc').blur());
  await page.fill('#try-pc', 'e1');
  await page.keyboard.press('Escape');
  await past();
  ok((await list()).hidden && !seen.completions.includes('E1'), 'Escape inside the pause sends nothing and opens nothing', seen.completions.join());
  await page.fill('#try-pc', 'n1');
  await leave();
  await past();
  ok((await list()).hidden && !seen.completions.includes('N1'), 'leaving the box inside the pause sends nothing', seen.completions.join());
  await page.fill('#try-pc', 'w1');
  await page.waitForTimeout(350); // asked, and slow
  await leave();
  await page.waitForTimeout(1100); // past the slow reply
  ok((await list()).hidden && seen.completions.includes('W1'), 'a reply landing after the reader left opens nothing', seen.completions.join());
  await page.fill('#try-pc', 'se1');
  await page.keyboard.press('Enter');
  await past();
  ok((await list()).hidden && !seen.completions.includes('SE1') && (await state(page)).invalid === 'true', 'Enter inside the pause is the form\'s, and no lookup follows it', seen.completions.join());
  await context.close();
}

for (const [width, height, motion] of [[1366, 900, 'no-preference'], [390, 844, 'no-preference'], [390, 844, 'reduce'], [320, 640, 'no-preference']]) {
  const tag = `${width}px${motion === 'reduce' ? ', reduced motion' : ''}`;
  console.log(`The page at ${tag}`);
  const { page, seen, context } = await open(browser, { width, height, motion });
  await settled(page);
  let s = await state(page);

  ok(await page.locator('#try-form').isVisible() && await page.locator('.code-tabs').isVisible(), 'the form and the language tabs show once the module runs');
  same(s.status, 'Answered for TW9 3PZ.', 'it opens on the example');
  same(seen.geo, [], 'and nothing has gone to postcodes.io: no reader has sent anything');
  const kewFigures = REAL.TW93PZ.env.environment;
  same(s.tiles, [`${kewFigures.aircraftNoiseLdenDb} dB`, `${kewFigures.roadNoiseLdenDb} dB`, `${kewFigures.no2AnnualMeanUgm3} µg/m³`], 'the example\'s figures are the answer\'s own');
  ok(atSamePoint(s, seen), 'all three samples name the point that was asked', s.curl);
  ok(s.json.includes('"postcode": "TW9 3PZ"'), 'the answer shown is the one that came back');
  ok(await page.locator('section.sample pre').evaluate((n) => n.textContent.includes("-H 'X-Api-Key: YOUR_KEY'")), 'the keyed sample keeps its key line, or it would fail for anyone who pasted it');

  if (motion === 'reduce') {
    // On a phone the band starts below the fold, and it only plays once in view: a check made there could not fail.
    await page.locator('section.dev .code').scrollIntoViewIfNeeded();
    await page.waitForTimeout(700);
    s = await state(page);
    ok(!s.running && (await page.textContent('#dev-replay')) === 'Play', 'reduced motion: nothing moves on arriving, and Play is offered');
  } else if (width === 1366) {
    const ran = await page.waitForSelector('.dev-n.is-lit', { state: 'attached', timeout: 4000 }).then(() => true).catch(() => false);
    ok(ran, 'it plays once on arriving');
    await page.waitForFunction(() => !document.getElementById('dev-run').classList.contains('is-waiting'), null, { timeout: 8000 });
  }

  s = await send(page, 'sw5 9hp');
  same(s.tiles, [`${REAL.SW59HP.env.environment.roadNoiseLdenDb} dB`, `${REAL.SW59HP.env.environment.no2AnnualMeanUgm3} µg/m³`], 'a postcode sent: its own figures, and no tile for what it lacks');
  ok(s.status === 'Answered for SW5 9HP. We hold no figure here for aircraft noise.', 'and it says what is missing', s.status);
  ok(atSamePoint(s, seen), 'the samples moved to the point answered', s.curl);
  ok(s.running, 'a press plays, whatever the motion setting');
  await page.waitForFunction(() => !document.getElementById('dev-run').classList.contains('is-waiting'), null, { timeout: 8000 });

  const box = await page.evaluate(() => {
    const over = document.documentElement.scrollWidth - document.documentElement.clientWidth;
    const tile = document.querySelector('#dev-tiles .ans-tile b');
    const line = parseFloat(getComputedStyle(tile).lineHeight);
    return { over, lines: [...document.querySelectorAll('#dev-tiles .ans-tile b')].map((b) => Math.round(b.getBoundingClientRect().height / line)) };
  });
  ok(box.over <= 0, 'nothing scrolls the page sideways', `${box.over}px`);
  if (width >= 390) ok(box.lines.every((n) => n === 1), 'each figure stays on one line in its card', JSON.stringify(box.lines));

  await page.click('[data-try="M1 1AE"]');
  await settled(page);
  s = await state(page);
  ok(s.status.startsWith('Answered for M1 1AE.') && (await page.inputValue('#try-pc')) === 'M1 1AE', 'a chip fills the box and sends');
  ok(atSamePoint(s, seen), 'and its answer moves the samples too');

  s = await send(page, 'EX1 1HS');
  same(s.tiles, [`${REAL.EX11HS.env.environment.no2AnnualMeanUgm3} µg/m³`], 'NO₂ alone: one card, never a zero for noise');
  ok(/no figure for aircraft noise and road noise, though DEFRA may map this place\.$/.test(s.status), 'and the two it lacks are named, as what we hold', s.status);

  s = await send(page, 'ZE1 0AA');
  ok(s.status.startsWith('Answered for ZE1 9ZZ, the nearest postcode the API found to ZE1 0AA.'), 'a neighbour\'s answer says so', s.status);
  ok(s.json.includes('"postcode": "ZE1 9ZZ"'), 'and the answer on show names it');

  s = await send(page, 'NG11 8AH');
  same(s.tiles, [`under ${REAL.NG118AH.env.environment.roadNoiseBelowDb} dB`, `${REAL.NG118AH.env.environment.no2AnnualMeanUgm3} µg/m³`], 'a quiet road reads as its bound, on a card');
  ok(s.status === 'Answered for NG11 8AH. We hold no figure here for aircraft noise.', 'and only what is truly missing is said to be', s.status);
  ok(s.json.includes('"roadNoiseBelowDb": '), 'and the answer on show carries the field a caller would read');

  await context.close();
}

console.log('Nothing to show');
{
  const { page, seen, context } = await open(browser, { width: 1366, height: 900 });
  await settled(page);
  const before = await state(page);
  const unchanged = (s) => JSON.stringify([s.tiles, s.curl, s.json]) === JSON.stringify([before.tiles, before.curl, before.json]);

  for (const typed of ['not a postcode', '10001', '']) {
    const made = seen.geo.length;
    await page.fill('#try-pc', typed);
    await page.click('.try-row button');
    const s = await state(page);
    ok(s.status === 'That is not a UK postcode. Try one like SW5 9HP. Still showing TW9 3PZ.' && s.invalid === 'true' && seen.geo.length === made && unchanged(s), `"${typed}": said, marked invalid, nothing sent, and it says whose answer stays`, JSON.stringify(s));
  }
  await page.fill('#try-pc', 'S');
  ok((await state(page)).invalid === null, 'typing again clears the mark');

  for (const [typed, words] of [
    ['SW5 9XX', 'We could not find SW5 9XX. Check it and send it again. Still showing TW9 3PZ.'],
    ['AB1 2CD', 'We hold no noise or NO₂ figure for AB1 2CD. Still showing TW9 3PZ.'],
    ['BB1 1BB', 'The API found no postcode near the map reference for BB1 1BB. Try another. Still showing TW9 3PZ.'],
    ['IM1 1AD', 'IM1 1AD has no map reference, so there is no point to ask about. The Isle of Man and the Channel Islands have none. Still showing TW9 3PZ.'],
    ['CC1 1CC', `${sayProblem('failed', 'CC1 1CC', 'TW9 3PZ')}`],
    ['DD1 1DD', `${sayProblem('failed', 'DD1 1DD', 'TW9 3PZ')}`],
    ['EE1 1EE', `${sayProblem('failed', 'EE1 1EE', 'TW9 3PZ')}`],
    ['FF1 1FF', 'The API is busy just now: this route answers a few requests a second for everyone. Wait a moment and send it again. Still showing TW9 3PZ.'],
    ['GG1 1GG', 'The request did not finish. Wait a moment and send it again. Still showing TW9 3PZ.'],
  ]) {
    const s = await send(page, typed);
    ok(s.status === words && unchanged(s) && s.busy === null, `${typed}: said in words, the answer on show untouched`, s.status);
  }
  ok(!seen.env.some((q) => q.includes('null')), 'a postcode with no point never reaches the API');
  await page.fill('#try-pc', 'SW5 9HP');
  await page.press('#try-pc', 'Enter');
  await settled(page);
  ok((await state(page)).status.startsWith('Answered for SW5 9HP.'), 'Enter sends, and the page recovers after a failure');
  await context.close();
}

console.log('Two requests in flight');
{
  const { page, seen, context } = await open(browser, { width: 1366, height: 900 });
  await settled(page);
  await page.fill('#try-pc', 'SL1 1AA');
  await page.click('.try-row button');
  ok((await state(page)).status === 'Asking about SL1 1AA.' && (await state(page)).busy === 'true', 'a request in flight is said, and the form is marked busy');
  await page.fill('#try-pc', 'SL2 2AA');
  await page.click('.try-row button');
  await page.waitForTimeout(200);
  ok((await state(page)).status === 'Asking about SL2 2AA.' && (await state(page)).busy === 'true', 'the request it cancels says nothing over the newer one', (await state(page)).status);
  await page.click('[data-try="M1 1AE"]');
  await settled(page);
  await page.waitForTimeout(1100); // past the slow reply
  const s = await state(page);
  ok(s.status.startsWith('Answered for M1 1AE.') && s.json.includes('M1 1AE'), 'the newest request wins: a late reply never replaces it', s.status);
  ok(seen.cancelled.some((u) => u.includes('/v1/environment')), 'and the older request is cancelled, not just ignored', JSON.stringify(seen.cancelled));
  await context.close();
}
{
  const { page, seen, context } = await open(browser, { width: 1366, height: 900 });
  await settled(page);
  await page.fill('#try-pc', 'SL1 1AA');
  await page.click('.try-row button');
  await page.click('.try-row button');
  await page.press('#try-pc', 'Enter');
  await settled(page);
  same(seen.geo.filter((pc) => pc === 'SL11AA').length, 1, 'three presses of a postcode on its way send it once');
  const asks = seen.env.length;
  await page.click('.try-row button');
  await page.waitForTimeout(150);
  ok(seen.env.length === asks && (await state(page)).running, 'a postcode already on show replays, and asks nothing');

  // The slow one, so it is truly on its way when the bad press lands.
  await send(page, 'SW5 9HP');
  await page.fill('#try-pc', 'SL1 1AA');
  await page.click('.try-row button');
  await page.fill('#try-pc', 'nonsense');
  await page.click('.try-row button');
  ok((await state(page)).busy === 'true', 'a bad postcode leaves a good one on its way', (await state(page)).status);
  await settled(page);
  ok((await state(page)).status.includes('SL1 1AA'), 'and that one still lands', (await state(page)).status);
  ok((await state(page)).invalid === null, 'taking the mark off the box with the words that explained it');
  await context.close();
}
{
  const { page, seen, context } = await open(browser, { width: 1366, height: 900 });
  await settled(page);
  await page.click('#dev-replay');
  await page.waitForSelector('.dev-caret', { state: 'attached', timeout: 3000 });
  const s = await send(page, 'SW5 9HP');
  ok(atSamePoint(s, seen), 'an answer landing mid-run is not overwritten by the sample being typed', s.curl);
  await context.close();
}
{
  const { page, context } = await open(browser, { width: 1366, height: 900 });
  await settled(page);
  let s = await send(page, 'WD1 1AA');
  ok(s.curl.includes('lat=53&lon=-2') && s.curl.includes('eu-west-2.amazonaws.com'), 'a whole degree is written as it is', s.curl);
  s = await send(page, 'M1 1AE');
  ok(s.curl === `curl '${API}/v1/environment?lat=${REAL.M11AE.geo.latitude}&lon=${REAL.M11AE.geo.longitude}'`, 'and the next answer leaves the API\'s host alone', s.curl);
  await context.close();
}

console.log('Copy, the tabs and the counts');
{
  const { page, seen, context } = await open(browser, { width: 1366, height: 900 });
  await settled(page);
  await page.evaluate(() => {
    window.__copied = [];
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async (t) => { window.__copied.push(t); } } });
  });
  await send(page, 'SW5 9HP');
  await send(page, 'M1 1AE');
  await page.click('section.dev button.copy[data-copy]');
  await page.click('#code-tab-py');
  await page.click('section.dev button.copy[data-copy]');
  await page.click('#dev-replay');
  await page.click('#dev-replay');
  const copied = await page.evaluate(() => window.__copied);
  const s = await state(page);
  ok(/^Copied/.test(s.copied), 'Copy says so');
  await send(page, 'EX1 1HS');
  same((await state(page)).copied, '', 'and stops saying so once the request on show has changed');
  ok(copied.length === 2 && copied[0] === s.curl && copied[1] === s.python && copied[0].includes(String(REAL.M11AE.geo.latitude)), 'Copy takes the sample on show, at the point answered', JSON.stringify(copied));
  const counted = await page.evaluate(() => window.__counted);
  same([...counted].sort(), ['event/api-demo-copy', 'event/api-demo-lang', 'event/api-demo-play', 'event/api-demo-send'], 'each way is counted once per page view, by name');
  ok(seen.score === 0, 'nothing here ever asks /v1/score');
  ok(seen.errors.length === 0 && seen.csp.length === 0, 'no page errors, and the page\'s own policy allows both lookups', JSON.stringify([seen.errors, seen.csp]));
  await context.close();
}

console.log('When the example cannot load');
{
  const { page, seen, context } = await open(browser, { width: 1366, height: 900, arrival: false });
  await settled(page);
  let s = await state(page);
  ok(s.hidden && s.status === sayProblem('failed', 'TW9 3PZ', null), 'the band stays the request alone, and it says so', s.status);
  ok(s.curl.includes('lat=51.4790&lon=-0.2860'), 'the sample stands as written');
  s = await send(page, 'SW5 9HP');
  ok(!s.hidden && s.status.startsWith('Answered for SW5 9HP.') && atSamePoint(s, seen), 'a reader can still send their own');
  await context.close();
}

console.log('A press of what is on show');
{
  const { page, seen, context } = await open(browser, { width: 1366, height: 900 });
  await settled(page);
  await page.fill('#try-pc', 'SL2 2AA');
  await page.click('.try-row button');
  await page.waitForTimeout(150); // past its postcode lookup, so the slow reply is truly on its way
  await page.click('[data-try="TW9 3PZ"]');
  ok((await state(page)).busy === null, 'it ends the wait for what was on its way', String((await state(page)).busy));
  await page.waitForTimeout(800); // past the slow reply
  const s = await state(page);
  ok(s.status.startsWith('Answered for TW9 3PZ.') && !s.json.includes('M1 1AE'), 'and a late reply never replaces it', `${s.status} ${s.json.slice(0, 80)}`);
  ok(seen.cancelled.some((u) => u.includes('/v1/environment')), 'the older request is cancelled, not just ignored', JSON.stringify(seen.cancelled));
  const problem = await send(page, 'SW5 9XX');
  ok(problem.status.startsWith('We could not find SW5 9XX'), 'a postcode nobody knows is said', problem.status);
  await page.click('[data-try="TW9 3PZ"]');
  ok((await state(page)).status.startsWith('Answered for TW9 3PZ.'), 'and a replay takes those words back', (await state(page)).status);
  await context.close();
}
{
  // A reader who asks for less motion is sent no run on arriving, so only the press can play this.
  const { page, context } = await open(browser, { width: 390, height: 844, motion: 'reduce', hold: 700 });
  await page.click('[data-try="TW9 3PZ"]');
  ok((await state(page)).busy === 'true', 'the example is still on its way when the reader presses it');
  await settled(page);
  ok((await state(page)).running, 'and it plays when it lands, whatever the motion setting');
  await context.close();
}

console.log('The run on arriving');
{
  const { page, context } = await open(browser, { width: 390, height: 844 });
  await settled(page);
  const seenOf = () => page.evaluate(() => {
    const r = document.querySelector('section.dev .code').getBoundingClientRect();
    return Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0)) / r.height;
  });
  ok((await seenOf()) < 0.35, 'on a phone the band is below the form, so the run on arriving is still waiting', String(await seenOf()));
  await page.click('[data-try="SW5 9HP"]');
  await settled(page);
  await page.waitForFunction(() => !document.getElementById('dev-run').classList.contains('is-waiting'), null, { timeout: 15000 });
  await page.locator('section.dev .code').evaluate((n) => n.scrollIntoView({ block: 'start' }));
  ok((await seenOf()) >= 0.35, 'the reader then scrolls down to the answer', String(await seenOf()));
  await page.waitForTimeout(300);
  ok(!(await state(page)).running, 'and it never restarts what they pressed');
  await context.close();
}

console.log('The band keeps its place');
for (const [width, height] of [[1920, 1080], [1366, 900], [1024, 768], [768, 1024], [390, 844]]) {
  const { page, context } = await open(browser, { width, height, hold: 800 });
  await settled(page);
  await page.waitForTimeout(300);
  const shift = await page.evaluate(() => +window.__shift.toFixed(4));
  ok(shift < 0.02, `${width}px: the page does not move while the example arrives`, String(shift));
  await context.close();
}
{
  const { page, context } = await open(browser, { width: 1366, height: 900, arrival: false });
  await settled(page);
  same(await page.locator('#dev-run').evaluate((n) => getComputedStyle(n).display), 'none', 'an example that fails keeps no empty room');
  await context.close();
}

console.log('Without the module');
const display = (page, sel) => page.locator(sel).evaluate((n) => getComputedStyle(n).display);
{
  const { page, context } = await open(browser, { width: 1366, height: 900, js: false });
  ok(!(await page.locator('#try-form').isVisible()) && !(await page.locator('.code-tabs').isVisible()), 'no script: no dead form and no tabs');
  ok(await page.locator('#dev-env').isVisible() && !(await page.locator('#dev-run').isVisible()), 'the curl request shows alone');
  ok((await display(page, '#try-form')) === 'none' && (await display(page, '#dev-run')) === 'none', 'with no room kept for what will not come');
  ok(!/Type a postcode/.test(await page.locator('#try').innerText()), 'and nothing tells a reader to use a form that is not there');
  await context.close();
}
{
  const { page, context } = await open(browser, { width: 1366, height: 900, base: false });
  await page.waitForTimeout(200);
  ok(!(await page.locator('#try-form').isVisible()) && (await display(page, '#try-form')) === 'none' && (await display(page, '#dev-run')) === 'none', 'no API host: no form, and no room kept for one');
  ok(!/Type a postcode/.test(await page.locator('#try').innerText()), 'and no words about one');
  await context.close();
}

await browser.close();
server.close();
assert.ok(checks > 0);
console.log(`\napi demo: ${checks - failures} of ${checks} checks passed`);
if (failures) process.exit(1);
