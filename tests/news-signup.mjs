// NEWS BY EMAIL, as a visitor meets it (Bill, 2026-11-22; mock-up claude.ai/artifact/XFr75aGp5ziqBEeFFNCCmu v6, colour A;
// news-v2 the same evening, claude.ai/artifact/8v4FMpDJ9Eq8N24zEGhVHz). The front page's strip under the hero: one form,
// the button is the consent, NEWS ONLY (no postcode box: Bill, "confusing", the page opens on an example). After a
// sign-up, "Check your inbox" takes the form's place. Held here, measured on the drawn page (never the flags):
//   - desktop 1366 x 900: the box and button sit in the FIRST screen; the form starts on the map column's own edge and
//     the words on the search column's; the strip is the map's blue-grey; the search keeps the ONLY orange button; the
//     link is dark (the orange-brown fails on blue-grey);
//   - nothing is sent on arrival; the address goes only in a POST body, alone: no postcode, before or after a search;
//   - after a 201: the panel names the address mostly hidden, focus moves to it, the form is gone (no second press);
//     "Send it again" sends the same address at most to the Lambda's three a day and then says so in words; "Use a
//     different address" brings the form back, empty and focused;
//   - every answer is said in words: no address, 429, the Lambda's own refusal, a network failure;
//   - counted as front-news-requested / front-news-link-sent / front-news-resend, never an address;
//   - phone 390 and 360: after the map, the box and button on one row, nothing off the page, the panel too; the search
//     button says "Check my area" with room for the box's hint, and "Check" under 375 px.
// /v1/signup is answered IN THE PAGE: nothing here reaches the live API. TW9 3PZ is the example AND the postcode
// tests/stub-live-api.mjs answers offline.
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

// The page counts sends up to the Lambda's own cap, read from its source (a capped send answers the same 201).
{
  const mod = await readFile(join(ROOT, 'js', 'news-signup.mjs'), 'utf8');
  const app = await readFile(join(ROOT, 'backend', 'lambdas', 'signup', 'app.py'), 'utf8');
  const js = /export const SENDS_PER_DAY = (\d+);/.exec(mod)?.[1];
  const py = /^SEND_CAP_PER_DAY = (\d+)/m.exec(app)?.[1];
  ok(js && js === py, 'the page stops resending where the Lambda stops sending', `${js} vs ${py}`);
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

const exampleDrawn = (page) => page.waitForFunction(() => /Tell us/.test(document.getElementById('ans-wrong')?.textContent || ''), null, { timeout: 30000 });
async function searchPostcode(page) {
  await page.evaluate(() => document.getElementById('ans-wrong').replaceChildren());
  await page.evaluate((q) => {
    const form = document.getElementById('check');
    const input = form.querySelector('input');
    input.value = q;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    form.requestSubmit();
  }, PC);
  await page.waitForFunction(() => /Tell us/.test(document.getElementById('ans-wrong')?.textContent || '')
    && document.getElementById('ans-example')?.hidden === true, null, { timeout: 30000 });
}
const panel = (page) => page.evaluate(() => {
  const sent = document.getElementById('news-sent');
  const form = document.getElementById('news-form');
  return {
    shown: !sent.hidden && sent.getBoundingClientRect().height > 0,
    formShown: !form.hidden && form.getBoundingClientRect().height > 0,
    to: document.getElementById('news-sent-to').textContent,
    // The panel's FIRST paragraph, the one in body text, names Junk (Bill, 2026-11-23): in the small print it was missed.
    junkFirst: /Junk or Spam/.test(sent.querySelector('p')?.textContent || ''),
    again: !document.getElementById('news-again').hidden,
    said: document.getElementById('news-again-said').textContent,
    focus: document.activeElement?.id || '',
    result: document.getElementById('news-result').textContent,
  };
});
/** Press Sign me up with an address; wait for the panel or for words in the result line. */
async function send(page, email) {
  await page.fill('#news-email', email);
  await page.click('#news-form button[type=submit]');
  await page.waitForFunction(() => {
    const t = document.getElementById('news-result').textContent;
    return !document.getElementById('news-sent').hidden || (t && t !== 'Sending...');
  }, null, { timeout: 10000 }).catch(() => {});
  return panel(page);
}
async function resend(page) {
  const before = await page.evaluate(() => document.getElementById('news-again-said').textContent);
  await page.click('#news-again');
  await page.waitForFunction((b) => {
    const t = document.getElementById('news-again-said').textContent;
    return t && t !== 'Sending...' && t !== b;
  }, before, { timeout: 10000 }).catch(() => {});
  return panel(page);
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
        button: r(news.querySelector('.news-row button')),
        panel: r(document.querySelector('.panel')), map: r(document.querySelector('.mapwrap')), mapcol: r(document.querySelector('.mapcol')),
        bg: getComputedStyle(news).backgroundColor, link: getComputedStyle(news.querySelector('.news-small a')).color,
        buttonBg: getComputedStyle(news.querySelector('.news-row button')).backgroundColor,
        inMapcol: !!news.closest('.mapcol'), afterMap: !!(document.querySelector('.mapcol').compareDocumentPosition(news) & Node.DOCUMENT_POSITION_FOLLOWING),
        orange, search: document.querySelector('form.check button').textContent.trim(),
        boxes: news.querySelectorAll('input[type=checkbox]').length,
        sentHidden: document.getElementById('news-sent').hidden,
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
    ok(m.boxes === 0 && m.sentHidden, 'news only: no tick box, and "Check your inbox" waits hidden', JSON.stringify({ boxes: m.boxes, sentHidden: m.sentHidden }));
    ok(m.overflow <= 0, 'desktop: nothing runs off the page', String(m.overflow));
    ok(signups.length === 0, 'nothing is sent on arrival', String(signups.length));
    await context.close();
  }

  // ---- SENDING ----
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

    // After a real search, still news only: the request carries the address and the list, nothing about the place.
    await searchPostcode(page);
    const sentPanel = await send(page, 'someone@example.com');
    const first = signups[0] || {};
    ok(first.method === 'POST' && !/someone|example\.com/.test(first.url) && !new URL(first.url || 'http://x').search,
      'the address goes only in a POST body, never the URL', JSON.stringify(first));
    ok(JSON.stringify(bodyOf(first)) === JSON.stringify({ email: 'someone@example.com', source: 'updates' }),
      'news only, even after a search: the address and the list, no postcode', first.body);
    ok(sentPanel.shown && !sentPanel.formShown && sentPanel.to === 's•••••@example.com',
      'a 201 shows "Check your inbox" in the form\'s place, the address mostly hidden', JSON.stringify(sentPanel));
    ok(sentPanel.focus === 'news-sent-h', 'focus moves to the panel, where the change is', sentPanel.focus);
    ok(sentPanel.junkFirst, '"Check your inbox" says to look in Junk or Spam in its main sentence, not only the small print', JSON.stringify(sentPanel));
    ok(sentPanel.again && signups.length === 1, 'the form is gone, so a second press cannot send; "Send it again" is the one way', JSON.stringify({ again: sentPanel.again, sent: signups.length }));

    // The page sends at most the Lambda's three a day to one address, then says so (a capped send answers the same 201).
    const second = await resend(page);
    ok(second.said === 'Sent again.' && second.again && signups.length === 2 && bodyOf(signups[1]).email === 'someone@example.com',
      '"Send it again" sends the same address again', JSON.stringify({ second, sent: signups.length }));
    const third = await resend(page);
    ok(/three today/.test(third.said) && !third.again && signups.length === 3, 'after the third, it says so and offers no more', JSON.stringify({ third, sent: signups.length }));
    await page.evaluate(() => document.getElementById('news-again').click());
    await page.waitForTimeout(300);
    ok(signups.length === 3, 'a hidden button sends nothing', String(signups.length));

    // The answer is long now, and the map column is sticky: scrolled down to the strip, the map must stop above it.
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

    await page.click('#news-other');
    const back = await panel(page);
    const field = await page.evaluate(() => ({ value: document.getElementById('news-email').value, focus: document.activeElement?.id }));
    ok(!back.shown && back.formShown && field.value === '' && field.focus === 'news-email', '"Use a different address" brings the form back, empty and focused', JSON.stringify({ back, field }));

    mode = 'busy';
    ok(/Busy just now/.test((await send(page, 'a@example.com')).result), 'a 429 says busy');
    mode = 'refused';
    ok(/not open yet/.test((await send(page, 'b@example.com')).result), 'a refusal says the Lambda\'s own words');
    mode = 'down';
    const down = await send(page, 'c@example.com');
    ok(/Check your connection/.test(down.result) && down.formShown && !down.shown, 'a network failure says so, and keeps the form', JSON.stringify(down));

    const gc = await page.evaluate(() => window.__gc.slice());
    const news = gc.filter((p) => p.includes('news'));
    ok(['event/front-news-requested', 'event/front-news-link-sent', 'event/front-news-resend'].every((p) => news.includes(p))
      && news.every((p) => /^event\/front-news-(requested|link-sent|resend)$/.test(p)),
    'counted as front-news-requested / -link-sent / -resend, never an address', JSON.stringify(news));
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
    await page.waitForFunction(() => !document.getElementById('news-sent').hidden, null, { timeout: 10000 }).catch(() => {});
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
    const measure = () => page.evaluate(() => {
      const r = (el) => { const b = el.getBoundingClientRect(); return { left: Math.round(b.left), right: Math.round(b.right), top: Math.round(b.top + scrollY), bottom: Math.round(b.bottom + scrollY), width: Math.round(b.width), height: Math.round(b.height) }; };
      const btn = document.querySelector('form.check button');
      return {
        news: r(document.getElementById('news')), map: r(document.querySelector('.mapwrap')),
        input: r(document.querySelector('.news-row input')), button: r(document.querySelector('.news-row button')),
        sent: r(document.getElementById('news-sent')), again: r(document.getElementById('news-again')),
        search: btn.innerText.trim(), pcBox: r(document.getElementById('pc')),
        overflow: document.documentElement.scrollWidth - innerWidth,
      };
    });
    const p = await measure();
    ok(p.news.top >= p.map.bottom, `${width}: the strip comes after the map`, JSON.stringify({ news: p.news.top, map: p.map.bottom }));
    ok(Math.abs(p.input.top - p.button.top) <= 1 && p.button.height >= 44 && p.input.height >= 44,
      `${width}: the box and button on one row, both at least 44 px tall`, JSON.stringify({ input: p.input, button: p.button }));
    ok(p.overflow <= 0 && p.news.right <= width, `${width}: nothing runs off the page`, JSON.stringify({ overflow: p.overflow, news: p.news }));
    if (width >= 375) ok(p.search === 'Check my area' && p.pcBox.width >= 157, `${width}: "Check my area", and the box keeps room for "Your postcode"`, JSON.stringify({ search: p.search, box: p.pcBox.width }));
    else ok(p.search === 'Check' && p.pcBox.width >= 157, `${width}: "Check" alone, so the box keeps room for its hint`, JSON.stringify({ search: p.search, box: p.pcBox.width }));
    await send(page, 'phone@example.com');
    const s = await measure();
    ok(s.sent.height > 0 && s.overflow <= 0 && s.sent.right <= width - 12 && s.again.height >= 40,
      `${width}: "Check your inbox" fits, nothing off the page, its button at least 40 px tall`, JSON.stringify({ sent: s.sent, again: s.again, overflow: s.overflow }));
    await context.close();
  }
} finally {
  await browser.close();
  server.close();
}
console.log(`\n${passed} passed, ${failures} failed`);
process.exit(failures ? 1 : 0);
