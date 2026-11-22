// NEWS BY EMAIL, as a visitor meets it (Bill, 2026-11-22; mock-up claude.ai/artifact/XFr75aGp5ziqBEeFFNCCmu v6, colour A).
// The front page's strip under the hero: one form, the button is the consent, and after a real search one UNTICKED box
// for that postcode. Held here, measured on the drawn page (never the flags that should draw it):
//   - desktop 1366 x 900: the box and button sit in the FIRST screen; the form starts on the map column's own edge and
//     the words on the search column's (Bill: "a bit over the place" until they did); the strip is the map's blue-grey;
//     the search keeps the ONLY orange button; the link is dark (the orange-brown fails on blue-grey);
//   - nothing is sent on arrival; the address goes only in a POST body; no postcode is sent unless its box is ticked;
//   - the box: never for the example, shown after a search of a full postcode, unticked, gone after a place search, and
//     a tick never carries to the next search;
//   - every answer is said in words: no address, 201, 429, the Lambda's own refusal, a network failure;
//   - counted as front-news-requested / front-news-link-sent, never an address;
//   - phone 390: after the map, the box and button on one row, nothing off the page; the search button says "Check my
//     area" with room for the box's hint, and "Check" under 375 px.
// /v1/signup is answered IN THE PAGE: nothing here reaches the live API. TW9 3PZ is the example AND the postcode
// tests/stub-live-api.mjs answers offline, so one place shows both rules: the example has no box, a search of it does.
// Run: node tests/news-signup.mjs
import { chromium } from '@playwright/test';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { stubLiveApi } from './stub-live-api.mjs';

const ROOT = process.cwd();
const PORT = 8975; // the other harnesses hold 8099, 8921-8926, 8931-8962, 8971
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2', '.csv': 'text/csv', '.webmanifest': 'application/manifest+json' };
const PC = 'TW9 3PZ';
const ORANGE = 'rgb(242, 125, 38)';
const WATER = 'rgb(219, 228, 232)';
const DARK = 'rgb(20, 20, 20)';

const server = createServer(async (req, res) => {
  let raw = decodeURIComponent(req.url.split('?')[0]);
  if (raw.endsWith('/')) raw += 'index.html';
  const p = join(ROOT, normalize(raw));
  if (!p.startsWith(ROOT)) return res.writeHead(403).end();
  try {
    const body = await readFile(p);
    res.writeHead(200, { 'content-type': TYPES[extname(p)] || 'application/octet-stream' });
    res.end(body);
  } catch {
    res.writeHead(404).end();
  }
});
await new Promise((r) => server.listen(PORT, '127.0.0.1', r));
const HOME = `http://127.0.0.1:${PORT}/home/`;

let failures = 0;
let passed = 0;
const ok = (cond, name, detail = '') => {
  if (cond) { passed += 1; console.log(`  ok   ${name}`); } else { failures += 1; console.log(`  FAIL ${name}${detail ? `: ${detail}` : ''}`); }
};

// The module's postcode shape is the Lambda's, character for character.
{
  const mod = await readFile(join(ROOT, 'js', 'news-signup.mjs'), 'utf8');
  const app = await readFile(join(ROOT, 'backend', 'lambdas', 'signup', 'app.py'), 'utf8');
  const js = /export const FULL_POSTCODE = \/(.+)\/;/.exec(mod)?.[1];
  const py = /^UK_POSTCODE = re\.compile\(r'(.+)'\)/m.exec(app)?.[1];
  ok(js && js === py, 'the strip checks a postcode exactly as the Lambda does', `${js} vs ${py}`);
}

/** A page with the API stub, every /v1/signup answered here (`answer` decides how), and GoatCounter recorded. */
async function open(browser, { width, height, answer = () => ({ status: 201, body: { status: 'pending' } }) }) {
  const context = await browser.newContext({ viewport: { width, height }, serviceWorkers: 'block' });
  const page = await context.newPage();
  await page.addInitScript(() => {
    window.__gc = [];
    window.goatcounter = { count: (v) => window.__gc.push(v.path) };
  });
  await page.route('**/js/count.mjs', (r) => r.fulfill({ status: 200, contentType: 'application/javascript', body: '' }));
  await stubLiveApi(page);
  const signups = [];
  await page.route((url) => url.pathname.endsWith('/v1/signup'), (route) => {
    const req = route.request();
    signups.push({ url: req.url(), method: req.method(), body: req.postData() });
    const a = answer(req);
    if (a === 'abort') return route.abort('failed');
    return route.fulfill({ status: a.status, contentType: 'application/json', headers: { 'Access-Control-Allow-Origin': '*' }, body: JSON.stringify(a.body) });
  });
  return { context, page, signups };
}

// render() rewrites "Spotted something wrong?" (#ans-wrong) on every answer, the example's included: wait for the
// example's "Tell us", blank it, search, and wait for it to come back, which proves the SEARCH's render ran.
const exampleDrawn = (page) => page.waitForFunction(() => /Tell us/.test(document.getElementById('ans-wrong')?.textContent || ''), null, { timeout: 30000 });
async function searchFor(page, text) {
  await page.evaluate(() => document.getElementById('ans-wrong').replaceChildren());
  await page.evaluate((q) => {
    const form = document.getElementById('check');
    const input = form.querySelector('input');
    input.value = q;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    form.requestSubmit();
  }, text);
}
async function searchPostcode(page) {
  await searchFor(page, PC);
  await page.waitForFunction(() => /Tell us/.test(document.getElementById('ans-wrong')?.textContent || '')
    && document.getElementById('ans-example')?.hidden === true, null, { timeout: 30000 });
}
const boxState = (page) => page.evaluate(() => ({
  hidden: document.getElementById('news-pc-row').hidden,
  shown: document.getElementById('news-pc-row').getBoundingClientRect().height > 0,
  name: document.getElementById('news-pc-name').textContent,
  ticked: document.getElementById('news-pc').checked,
}));
async function send(page, email) {
  const before = await page.evaluate(() => document.getElementById('news-result').textContent);
  await page.fill('#news-email', email);
  await page.click('#news-form button[type=submit]');
  await page.waitForFunction((b) => {
    const t = document.getElementById('news-result').textContent;
    return t && t !== 'Sending...' && t !== b;
  }, before, { timeout: 10000 }).catch(() => {});
  return page.evaluate(() => document.getElementById('news-result').textContent);
}
const bodyOf = (s) => JSON.parse(s.body || '{}');

const browser = await chromium.launch();
try {
  // ---- DESKTOP, on arrival ----
  {
    const { context, page, signups } = await open(browser, { width: 1366, height: 900 });
    await page.goto(HOME);
    await exampleDrawn(page);
    await page.waitForFunction(() => document.querySelectorAll('#map .boro').length > 0, null, { timeout: 30000 });
    const m = await page.evaluate(({ ORANGE }) => {
      const r = (el) => { const b = el.getBoundingClientRect(); return { left: Math.round(b.left), right: Math.round(b.right), top: Math.round(b.top + scrollY), bottom: Math.round(b.bottom + scrollY) }; };
      const news = document.getElementById('news');
      const inFirstScreen = (el) => { const b = el.getBoundingClientRect(); return b.top + scrollY < innerHeight && b.width > 0 && b.height > 0; };
      const orange = [...document.querySelectorAll('button, a, input[type=submit]')]
        .filter((el) => inFirstScreen(el) && getComputedStyle(el).backgroundColor === ORANGE)
        .map((el) => el.textContent.trim());
      return {
        news: r(news), words: r(news.querySelector('.news-words h2')), form: r(news.querySelector('.news-row')),
        row: r(news.querySelector('.news-row')), button: r(news.querySelector('.news-row button')),
        panel: r(document.querySelector('.panel')), map: r(document.querySelector('.mapwrap')), mapcol: r(document.querySelector('.mapcol')),
        bg: getComputedStyle(news).backgroundColor, link: getComputedStyle(news.querySelector('.news-small a')).color,
        buttonBg: getComputedStyle(news.querySelector('.news-row button')).backgroundColor,
        inMapcol: !!news.closest('.mapcol'), afterMap: !!(document.querySelector('.mapcol').compareDocumentPosition(news) & Node.DOCUMENT_POSITION_FOLLOWING),
        orange, search: document.querySelector('form.check button').textContent.trim(),
        overflow: document.documentElement.scrollWidth - innerWidth,
      };
    }, { ORANGE });
    ok(m.button.bottom <= 900, 'desktop: the box and button end inside the first screen (1366 x 900)', JSON.stringify(m.button));
    ok(Math.abs(m.form.left - m.map.left) <= 1, 'desktop: the form starts on the map column\'s own edge', `${m.form.left} vs ${m.map.left}`);
    ok(Math.abs(m.words.left - (m.panel.left + 20)) <= 1 && Math.abs(m.news.left - m.panel.left) <= 1 && Math.abs(m.news.right - m.map.right) <= 1,
      'desktop: the strip spans both columns, its words on the search column', JSON.stringify({ news: m.news, words: m.words, panel: m.panel, map: m.map }));
    ok(m.news.top >= m.panel.bottom && m.news.top >= m.mapcol.bottom, 'desktop: it sits under both columns', JSON.stringify({ news: m.news.top, panel: m.panel.bottom, mapcol: m.mapcol.bottom }));
    ok(!m.inMapcol && m.afterMap, 'desktop: outside the sticky map column, after it in the page (keyboard order = screen order)');
    ok(m.bg === WATER, 'desktop: the strip is the map\'s blue-grey', m.bg);
    ok(m.link === DARK && m.buttonBg === DARK, 'desktop: its link and button are the dark (the orange-brown fails on blue-grey)', `${m.link} / ${m.buttonBg}`);
    ok(JSON.stringify(m.orange) === JSON.stringify(['Check my area']), 'desktop: the search keeps the only orange button in the first screen', JSON.stringify(m.orange));
    ok(m.search === 'Check my area', 'desktop: the search button says "Check my area"', m.search);
    ok(m.overflow <= 0, 'desktop: nothing runs off the page', String(m.overflow));
    const onExample = await boxState(page);
    ok(onExample.hidden && !onExample.shown && onExample.name === '', 'the example answer offers no postcode box (nobody asked for it)', JSON.stringify(onExample));
    ok(signups.length === 0, 'nothing is sent on arrival', String(signups.length));
    await context.close();
  }

  // ---- SENDING, after a real search ----
  {
    let mode = 'ok';
    const answers = {
      ok: () => ({ status: 201, body: { status: 'pending' } }),
      busy: () => ({ status: 429, body: { message: 'Too Many Requests' } }),
      refused: () => ({ status: 403, body: { error: 'News by email is not open yet.' } }),
      down: () => 'abort',
    };
    const { context, page, signups } = await open(browser, { width: 1366, height: 900, answer: () => answers[mode]() });
    await page.goto(HOME);
    await exampleDrawn(page);
    await page.waitForFunction(() => document.querySelectorAll('#map .boro').length > 0, null, { timeout: 30000 });

    await page.click('#news-form button[type=submit]');
    const empty = await page.evaluate(() => document.getElementById('news-result').textContent);
    ok(/Enter your email address/.test(empty) && signups.length === 0, 'no address: said in words, nothing sent', `${empty} / ${signups.length}`);

    const newsOnly = await send(page, 'someone@example.com');
    const first = signups[0] || {};
    ok(/Check your inbox/.test(newsOnly), 'a 201 says to check the inbox', newsOnly);
    // A second press would send a second confirmation email (code review 2026-11-22): the button stays off, and the
    // handler refuses a submit that gets past it, until the address or the box changes.
    const afterSent = await page.evaluate(() => document.querySelector('#news-form button[type=submit]').disabled);
    await page.evaluate(() => document.getElementById('news-form').requestSubmit());
    await page.waitForTimeout(300);
    ok(afterSent && signups.length === 1, 'after a sign-up goes through, a second press sends nothing', JSON.stringify({ afterSent, sent: signups.length }));
    ok(first.method === 'POST' && !/someone|example\.com/.test(first.url) && !new URL(first.url || 'http://x').search,
      'the address goes only in a POST body, never the URL', JSON.stringify(first));
    ok(JSON.stringify(bodyOf(first)) === JSON.stringify({ email: 'someone@example.com', source: 'updates', postcode: '' }),
      'news only: source "updates", no postcode', first.body);

    await searchPostcode(page);
    // The answer is long now, and the map column is sticky: scrolled down to the strip, the map must stop above it, never
    // slide over it (2026-11-22: inside the hero it did, because a sticky box travels its whole parent; found on a
    // screenshot after a search, which no arrival-only check could see). Measured at the strip's top and its bottom.
    const overlap = [];
    for (const block of ['start', 'center', 'end']) {
      overlap.push(await page.evaluate((b) => {
        document.getElementById('news').scrollIntoView({ block: b });
        const map = document.querySelector('.mapcol').getBoundingClientRect();
        const strip = document.getElementById('news').getBoundingClientRect();
        return { block: b, mapBottom: Math.round(map.bottom), stripTop: Math.round(strip.top), long: document.querySelector('.panel').getBoundingClientRect().height > innerHeight };
      }, block));
    }
    ok(overlap.every((o) => o.long && o.mapBottom <= o.stripTop + 1), 'after a long answer, the sticky map never slides over the strip', JSON.stringify(overlap));
    await page.evaluate(() => scrollTo(0, 0));
    const moved = await page.evaluate(() => ({ line: document.getElementById('news-result').textContent, off: document.querySelector('#news-form button[type=submit]').disabled }));
    ok(moved.line === '' && !moved.off, 'a new search clears the last answer and offers the button again', JSON.stringify(moved));
    const box = await boxState(page);
    ok(!box.hidden && box.shown && box.name === PC && !box.ticked, 'a search of a full postcode offers its box, unticked', JSON.stringify(box));
    await send(page, 'someone@example.com');
    ok(bodyOf(signups[1] || {}).postcode === '', 'the box unticked sends no postcode', signups[1]?.body);
    await page.check('#news-pc');
    await send(page, 'other@example.com');
    ok(bodyOf(signups[2] || {}).postcode === PC, 'the box ticked sends that postcode', signups[2]?.body);

    // A place search closes the postcode answer, and the box goes with it; the next postcode starts unticked.
    await searchFor(page, 'Hounslow');
    await page.waitForFunction(() => document.getElementById('news-pc-row').hidden === true, null, { timeout: 15000 }).catch(() => {});
    const afterPlace = await boxState(page);
    ok(afterPlace.hidden && !afterPlace.shown, 'a council search hides the postcode box', JSON.stringify(afterPlace));
    await searchPostcode(page);
    const again = await boxState(page);
    ok(!again.hidden && !again.ticked, 'a tick never carries to the next search', JSON.stringify(again));

    mode = 'busy';
    ok(/Busy just now/.test(await send(page, 'a@example.com')), 'a 429 says busy');
    mode = 'refused';
    ok(/not open yet/.test(await send(page, 'b@example.com')), 'a refusal says the Lambda\'s own words');
    mode = 'down';
    ok(/Check your connection/.test(await send(page, 'c@example.com')), 'a network failure says so');

    const gc = await page.evaluate(() => window.__gc.slice());
    const news = gc.filter((p) => p.includes('news'));
    ok(news.includes('event/front-news-requested') && news.includes('event/front-news-link-sent') && news.every((p) => /^event\/front-news-(requested|link-sent)$/.test(p)),
      'counted as front-news-requested / front-news-link-sent, never an address', JSON.stringify(news));
    ok(!gc.some((p) => /@|example\.com|TW9/.test(p)), 'no address or postcode in any count', JSON.stringify(gc));
    await context.close();
  }

  // ---- A SIGN-UP BEFORE THE EXAMPLE LANDS leaves the example to land (code review 2026-11-22: the count once marked the
  // visitor as having acted, and the example stands down for that, leaving the answer empty all visit) ----
  {
    const { context, page, signups } = await open(browser, { width: 1366, height: 900 });
    let release;
    const held = new Promise((r) => { release = r; });
    await page.route((url) => url.pathname.endsWith('/v1/environment'), async (route) => { await held; return route.fallback(); });
    await page.goto(HOME);
    await page.waitForFunction(() => document.querySelector('#news-form button[type=submit]')?.disabled === false, null, { timeout: 30000 });
    const early = await page.evaluate(() => /Tell us/.test(document.getElementById('ans-wrong')?.textContent || ''));
    await page.fill('#news-email', 'early@example.com');
    await page.click('#news-form button[type=submit]');
    await page.waitForFunction(() => /Check your inbox/.test(document.getElementById('news-result').textContent), null, { timeout: 10000 }).catch(() => {});
    release();
    let drawn = true;
    await exampleDrawn(page).catch(() => { drawn = false; });
    ok(!early && drawn && signups.length === 1, 'a sign-up made before the example lands leaves the example to land', JSON.stringify({ early, drawn, sent: signups.length }));
    await context.close();
  }

  // ---- PHONE 390 and 360 ----
  for (const [width, height] of [[390, 844], [360, 780]]) {
    const { context, page } = await open(browser, { width, height });
    await page.goto(HOME);
    await exampleDrawn(page);
    const p = await page.evaluate(() => {
      const r = (el) => { const b = el.getBoundingClientRect(); return { left: Math.round(b.left), right: Math.round(b.right), top: Math.round(b.top + scrollY), bottom: Math.round(b.bottom + scrollY), width: Math.round(b.width), height: Math.round(b.height) }; };
      const btn = document.querySelector('form.check button');
      return {
        news: r(document.getElementById('news')), map: r(document.querySelector('.mapwrap')),
        input: r(document.querySelector('.news-row input')), button: r(document.querySelector('.news-row button')),
        search: btn.innerText.trim(), pcBox: r(document.getElementById('pc')),
        overflow: document.documentElement.scrollWidth - innerWidth,
      };
    });
    ok(p.news.top >= p.map.bottom, `${width}: the strip comes after the map`, JSON.stringify({ news: p.news.top, map: p.map.bottom }));
    ok(Math.abs(p.input.top - p.button.top) <= 1 && p.button.height >= 44 && p.input.height >= 44,
      `${width}: the box and button on one row, both at least 44 px tall`, JSON.stringify({ input: p.input, button: p.button }));
    ok(p.overflow <= 0 && p.news.right <= width, `${width}: nothing runs off the page`, JSON.stringify({ overflow: p.overflow, news: p.news }));
    if (width >= 375) ok(p.search === 'Check my area' && p.pcBox.width >= 157, `${width}: "Check my area", and the box keeps room for "Your postcode"`, JSON.stringify({ search: p.search, box: p.pcBox.width }));
    else ok(p.search === 'Check' && p.pcBox.width >= 157, `${width}: "Check" alone, so the box keeps room for its hint`, JSON.stringify({ search: p.search, box: p.pcBox.width }));
    await context.close();
  }
} finally {
  await browser.close();
  server.close();
}
console.log(`\n${passed} passed, ${failures} failed`);
process.exit(failures ? 1 : 0);
