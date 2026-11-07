// About and How it works on Stitch's layout (2026-11-05, Bill's brief of 4 Nov), measured on the page.
//
// WHY THIS EXISTS. Both pages are static, and every other gate reads their WORDS or scans them for contrast. None can see
// what this rebuild is: that the grey boxes of the drafts are real pictures, the bands are the site's colours, a 16:9 crop
// is 16:9, "How it grew" reads in date order, arrow by arrow, without one step sitting on another, and a bar is the length its
// figure says. tests/approach-strip.mjs holds the strip and the page's order around it; this holds the rest.
//
//   node tests/page-bands.mjs

import { chromium } from '@playwright/test';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { dirname, extname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const PORT = Number(process.env.PAGE_BANDS_PORT) || 8948;
const TYPES = { '.html': 'text/html', '.mjs': 'application/javascript', '.js': 'application/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.avif': 'image/avif', '.webp': 'image/webp', '.jpg': 'image/jpeg', '.png': 'image/png', '.svg': 'image/svg+xml', '.json': 'application/json' };
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

let failures = 0, checks = 0;
const ok = (cond, label, detail = '') => {
  checks += 1;
  if (!cond) failures += 1;
  console.log(`  ${cond ? 'ok  ' : 'FAIL'} ${label}${cond || !detail ? '' : `: ${detail}`}`);
};

const TINT = 'rgb(251, 238, 227)', WATER = 'rgb(219, 228, 232)', DARK = 'rgb(20, 20, 20)', PAPER = 'rgb(251, 250, 248)', ORANGE = 'rgb(242, 125, 38)', WHITE = 'rgb(255, 255, 255)';
// The colours every surface gives a score (build_area_pages.score_colour, held to the map by tests/test_area_findings.py).
const scoreColour = (v) => (v >= 7 ? 'rgb(38, 242, 125)' : v >= 4 ? 'rgb(242, 184, 38)' : 'rgb(242, 125, 38)');

const browser = await chromium.launch();
const open = async (path, width, height = 900) => {
  const page = await browser.newPage({ viewport: { width, height } });
  page.errors = [];
  page.on('pageerror', (e) => page.errors.push(String(e)));
  await page.route('**/js/count.mjs', (r) => r.fulfill({ status: 200, contentType: 'application/javascript', body: '' }));
  await page.goto(`http://127.0.0.1:${PORT}${path}`, { waitUntil: 'load' });
  return page;
};
const sideways = (page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
const background = (page, sel) => page.evaluate((s) => getComputedStyle(document.querySelector(s)).backgroundColor, sel);

// ---- About ----

console.log('About: pictures and bands');
{
  const page = await open('/about/', 1366);
  const hero = await page.evaluate(() => {
    const img = document.querySelector('figure.hero img');
    const r = img.getBoundingClientRect();
    const main = document.querySelector('main');
    const pad = parseFloat(getComputedStyle(main).paddingLeft);
    return { ratio: r.width / r.height, fills: Math.abs(r.width - (main.clientWidth - pad * 2)) < 1, fit: getComputedStyle(img).objectFit, loaded: img.naturalWidth > 0, before: Boolean(document.querySelector('figure.hero').compareDocumentPosition(document.getElementById('why')) & Node.DOCUMENT_POSITION_FOLLOWING), alt: img.alt };
  });
  ok(Math.abs(hero.ratio - 16 / 9) < 0.01 && hero.fit === 'cover', 'the speaker photo is cropped 16:9, not squashed', JSON.stringify(hero));
  ok(hero.fills && hero.before, 'it runs the full width of the page, above "Why I built it"');
  ok(hero.loaded && hero.alt.length > 20, 'it is the real picture, and it says what it shows');

  // Every picture on the page is real, the lazy ones too: the drafts' grey boxes must not survive in any form.
  await page.evaluate(async () => {
    for (const img of document.images) { img.scrollIntoView(); await new Promise((r) => setTimeout(r, 60)); }
  });
  await page.waitForFunction(() => [...document.images].every((i) => i.complete), null, { timeout: 8000 });
  const broken = await page.evaluate(() => [...document.images].filter((i) => !i.naturalWidth).map((i) => i.currentSrc || i.src));
  ok(broken.length === 0, 'every picture on the page loads', broken.join(' '));
  ok(await page.evaluate(() => !document.querySelector('iframe') && document.querySelector('figure.film a').href.startsWith('https://youtu.be/')), 'the film is a still linking to YouTube, never an embed');

  ok(await background(page, '#promises') === TINT, 'the promises sit on the warm band');
  ok(await background(page, '#asked') === WATER, 'the questions sit on the cool band');
  ok(await background(page, '.contact') === DARK, 'the contact band is dark');
  const cards = await page.evaluate(() => ({
    promises: [...document.querySelectorAll('ul.promises li')].map((n) => [getComputedStyle(n).backgroundColor, Math.round(n.getBoundingClientRect().left)]),
    questions: document.querySelectorAll('dl.asked > div').length,
  }));
  ok(cards.promises.length === 4 && cards.promises.every(([c]) => c === PAPER) && new Set(cards.promises.map(([, x]) => x)).size === 2, 'four promises, as paper cards in two columns', JSON.stringify(cards.promises));
  ok(cards.questions === 5, 'all five questions are kept');

  // The page's link hover is --orange-ink: on the dark band and the orange button that fails, so these underline instead.
  const hover = async (sel) => { await page.hover(sel); return page.evaluate((s) => { const n = document.querySelector(s); return [getComputedStyle(n).color, getComputedStyle(n).backgroundColor]; }, sel); };
  const primary = await hover('ul.links a.primary');
  ok(primary[0] === DARK && primary[1] === ORANGE, 'the orange button keeps dark text on hover', JSON.stringify(primary));
  const plain = await hover('ul.links li:nth-child(2) a');
  ok(plain[0] === WHITE, 'and the other links stay white on the dark band', JSON.stringify(plain));
  ok(page.errors.length === 0, 'no page errors', page.errors.join(' '));
  await page.close();
}

console.log('About: the links');
{
  // Bill, 2026-11-06: the section links stay quiet until the pointer is on one, and links in the text are the darker orange.
  const page = await open('/about/', 1366);
  const INK = 'rgb(168, 84, 22)', CLEAR = 'rgba(0, 0, 0, 0)', PILL = 'nav.jump a[href="#grew"]', WORDS = 'ol.grew a[href="/api/"]';
  const pills = () => page.evaluate(() => [...document.querySelectorAll('nav.jump a')].map((a) => ({ href: a.getAttribute('href'), back: getComputedStyle(a).backgroundColor, text: getComputedStyle(a).color })));
  const rest = await pills();
  ok(rest.length === 6 && rest.every((p) => p.back === CLEAR && p.text === DARK), 'at rest no section link is filled', JSON.stringify(rest));
  await page.hover(PILL);
  const under = await pills();
  ok(under.filter((p) => p.back === ORANGE).map((p) => p.href).join() === '#grew' && under.find((p) => p.href === '#grew').text === DARK, 'the one under the pointer fills orange, dark text on it, and no other', JSON.stringify(under));
  await page.mouse.move(2, 2);
  // Polled: the browser applies a hover change on a later frame, so a read straight after the move sees the old one.
  const gone = await page.waitForFunction((clear) => [...document.querySelectorAll('nav.jump a')].every((a) => getComputedStyle(a).backgroundColor === clear), CLEAR, { timeout: 2000 }).then(() => true, () => false);
  ok(gone, 'and it goes when the pointer leaves', JSON.stringify(await pills()));

  // Every link, on what is really behind it: a light band or a dark one, a card or the page.
  const links = await page.evaluate(() => {
    const rgb = (s) => { const v = s.match(/[\d.]+/g).map(Number); return { r: v[0], g: v[1], b: v[2], a: v[3] ?? 1 }; };
    const lin = (c) => { const x = c / 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; };
    const lum = (c) => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
    const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
    const behind = (start) => { for (let n = start; n; n = n.parentElement) { const c = rgb(getComputedStyle(n).backgroundColor); if (c.a === 1) return c; } return { r: 255, g: 255, b: 255 }; };
    return [...document.querySelectorAll('main a')].map((a) => ({ words: a.textContent.trim().slice(0, 40), ratio: +ratio(rgb(getComputedStyle(a).color), behind(a)).toFixed(2), text: getComputedStyle(a).color }));
  });
  ok(links.length >= 30 && links.every((l) => l.ratio >= 4.5), 'every link on the page reads 4.5:1 or better', JSON.stringify(links.filter((l) => l.ratio < 4.5)));
  const colours = await page.evaluate(() => ({
    words: [...document.querySelectorAll('ol.grew p a')].map((a) => getComputedStyle(a).color),
    band: [...document.querySelectorAll('ul.links a:not(.primary)')].map((a) => getComputedStyle(a).color),
  }));
  ok(colours.words.length >= 8 && colours.words.every((c) => c === INK), 'links in the text are the darker orange', JSON.stringify(colours.words));
  ok(colours.band.length >= 3 && colours.band.every((c) => c === WHITE), 'and the dark band keeps its white ones', JSON.stringify(colours.band));
  await page.hover(WORDS);
  ok(await page.evaluate((s) => getComputedStyle(document.querySelector(s)).color, WORDS) === DARK, 'a link in the text goes dark under the pointer, or hovering it would change nothing');
  await page.close();

  // A phone's hover stays on what was tapped.
  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  const tapped = await phone.newPage();
  await tapped.route('**/js/count.mjs', (r) => r.fulfill({ status: 200, contentType: 'application/javascript', body: '' }));
  await tapped.goto(`http://127.0.0.1:${PORT}/about/`, { waitUntil: 'load' });
  await tapped.tap(PILL);
  await tapped.waitForTimeout(300);
  const after = await tapped.evaluate((s) => ({ back: getComputedStyle(document.querySelector(s)).backgroundColor, hovered: document.querySelector(s).matches(':hover'), noPointer: matchMedia('(hover: none)').matches }), PILL);
  ok(after.noPointer && after.hovered && after.back === CLEAR, 'on a phone a tap leaves no pill stuck orange', JSON.stringify(after));
  await phone.close();
}

console.log('About: How it grew');
// An arrow is a pseudo-element, which has no box to ask for, so its place is worked out from its computed values.
const grid = (page) => page.evaluate(() => {
  const list = document.querySelector('ol.grew');
  const arrow = (li, which) => {
    const s = getComputedStyle(li, which);
    if (s.display === 'none') return null;
    const r = li.getBoundingClientRect();
    const left = r.left + parseFloat(s.left) + parseFloat(s.marginLeft), top = r.top + parseFloat(s.top) + parseFloat(s.marginTop);
    return { left, top, right: left + parseFloat(s.width), bottom: top + parseFloat(s.height), picture: s.backgroundImage, place: s.backgroundPosition };
  };
  const steps = [...list.children].map((li) => {
    const r = li.getBoundingClientRect();
    // The arrows stand outside their card on purpose, so what must stay in is the words and the film.
    const spill = Math.max(...[...li.querySelectorAll('time, h3, p, figure')].map((n) => n.getBoundingClientRect().right)) - r.right;
    return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, spill, before: arrow(li, '::before'), after: arrow(li, '::after') };
  });
  const px = (sel) => parseFloat(getComputedStyle(list.querySelector(sel)).fontSize);
  return { steps, display: getComputedStyle(list).display, width: list.getBoundingClientRect().width, p: px('li:nth-child(2) p'), h3: px('li:nth-child(2) h3'), time: px('li:nth-child(2) time') };
});
const RIGHT = 'M0 0l10 6L0 12z', DOWN = 'M0 0h12L6 10z';
const near = (a, b, by = 1.5) => Math.abs(a - b) <= by;
const mid = (x) => (x.left + x.right) / 2;
const STORY = ['The first map', 'Sky Score Radar', 'Data first', 'An iPhone app', 'Beyond London', "Deen Developers' Build Night", 'AI Tinkerers London', 'Flight paths from the official routes', 'The Bay Area, and the air nearby', 'London Geo Meetup'];
for (const width of [1920, 1366, 1100, 1000]) {
  const page = await open('/about/', width);
  const g = await grid(page);
  const s = g.steps;
  ok(s.length === 10 && g.display === 'grid', `${width}: ten steps, on a grid`);
  ok(near(s[0].width, g.width), `${width}: the first map runs the full width`, `${Math.round(s[0].width)} of ${Math.round(g.width)}`);
  const rest = s.slice(1);
  ok(rest.every((x, i) => near(x.top, rest[i - (i % 3)].top) && near(x.bottom, rest[i - (i % 3)].bottom)), `${width}: the other nine sit in rows of three, each row level`, JSON.stringify(rest.map((x) => [Math.round(x.top), Math.round(x.bottom)])));
  ok(rest.every((x, i) => near(x.left, rest[i % 3].left)) && rest[0].left < rest[1].left && rest[1].left < rest[2].left, `${width}: in three columns, so date order reads left to right`, rest.map((x) => Math.round(x.left)).join(' '));
  ok(rest.every((x, i) => i < 3 || x.top > rest[i - 3].bottom), `${width}: and row by row down the page`);
  const hit = s.flatMap((a, i) => s.slice(i + 1).filter((b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom).map(() => i));
  ok(hit.length === 0, `${width}: no step sits on another`, hit.join());
  ok(rest.every((x) => x.width >= 250 && x.spill <= 0), `${width}: each card has room for a readable line, and nothing spills out`, s.map((x) => Math.round(x.width)).join(' '));
  ok(g.p >= 16 && g.h3 >= 20 && g.time >= 15, `${width}: the steps read near the page's own size`, JSON.stringify([g.p, g.h3, g.time]));

  // Every step points at the next, and only there.
  const along = [[1, 2], [2, 3], [4, 5], [5, 6], [7, 8], [8, 9]];
  for (const [a, b] of along) {
    const w = s[a].after;
    ok(w && near(w.left, s[a].right) && near(w.right, s[b].left) && w.top > s[a].top && w.bottom < s[a].bottom && w.picture.includes(RIGHT), `${width}: step ${a + 1} points right, at step ${b + 1}`, JSON.stringify(w));
  }
  const down = s[1].before;
  ok(down && near(down.top, s[0].bottom) && near(down.bottom, s[1].top) && near(mid(down), mid(s[1])) && down.picture.includes(DOWN), `${width}: the first map points down, at step 2`, JSON.stringify(down));
  for (const [a, b] of [[3, 4], [6, 7]]) {
    const leave = s[a].after, come = s[b].before;
    ok(leave && near(mid(leave), mid(s[a])) && near(leave.top, s[a].bottom, 6) && near(leave.bottom, come?.top), `${width}: step ${a + 1} leaves from under itself`, JSON.stringify(leave));
    ok(come && near(come.right, mid(s[a]), 7) && near(come.left + 6, mid(s[b])) && near(come.bottom, s[b].top) && come.picture.includes(DOWN), `${width}: and comes back to point down at step ${b + 1}`, JSON.stringify(come));
    // The box spans the whole way back, so it cannot say which end the head is at, or that a line is drawn at all.
    ok(come?.place?.startsWith('0% ') && come.picture.includes('repeating-linear-gradient(to right') && come.picture.split('repeating-linear-gradient(').length === 3, `${width}: its head at that end, on a line all the way back`, JSON.stringify(come));
  }
  ok([0, 2, 3, 5, 6, 8, 9].every((i) => !s[i].before) && [0, 9].every((i) => !s[i].after), `${width}: no arrow anywhere else, and none after the last step`, JSON.stringify(s.map((x) => [!!x.before, !!x.after])));
  ok(await sideways(page) <= 0, `${width}: nothing scrolls the page sideways`);

  const cards = await page.evaluate(() => {
    const film = document.querySelector('ol.grew > li:first-child figure.film');
    const label = film?.querySelector('.film-label');
    return {
      titles: [...document.querySelectorAll('ol.grew h3')].map((h) => h.textContent),
      talks: [...document.querySelectorAll('ol.grew > li.talk')].map((n) => getComputedStyle(n).backgroundColor),
      rest: [...document.querySelectorAll('ol.grew > li:not(.talk)')].map((n) => getComputedStyle(n).backgroundColor),
      labelLines: label ? Math.round(label.getBoundingClientRect().height / parseFloat(getComputedStyle(label).lineHeight)) : null,
      still: film?.querySelector('img')?.getBoundingClientRect().width,
    };
  });
  ok(cards.titles.join() === STORY.join(), `${width}: your talks sit among the steps, in date order`, cards.titles.join(' | '));
  ok(cards.talks.length === 3 && cards.talks.every((c) => c === TINT) && cards.rest.every((c) => c === PAPER), `${width}: talks on the warm colour, the rest on paper`, JSON.stringify(cards));
  ok(cards.labelLines !== null && cards.labelLines <= 2 && cards.still >= 300, `${width}: the film stays in the first card, at a size worth pressing`, JSON.stringify(cards));
  await page.close();
}
for (const width of [999, 760, 390, 320]) {
  const page = await open('/about/', width, 800);
  const g = await grid(page);
  ok(g.display !== 'grid' && g.steps.every((x, i) => !i || x.top >= g.steps[i - 1].bottom - 1), `${width}: the steps run down the page, as they always have`);
  const dashed = g.steps.slice(0, -1).every((x, i) => x.before?.picture?.includes('repeating-linear-gradient') && near(x.before.right - x.before.left, 2) && x.before.bottom > g.steps[i + 1].top);
  ok(dashed && !g.steps.at(-1).before && g.steps.every((x) => x.after), `${width}: a dashed line from each step to the next, and a point on each`, JSON.stringify(g.steps.map((x) => x.before)));
  ok(g.steps.every((x) => !x.after?.picture?.includes('svg') && !x.before?.picture?.includes('svg')), `${width}: and no arrows`);
  ok(await sideways(page) <= 0, `${width}: nothing scrolls the page sideways`);
  await page.close();
}
{
  // Each step goes on to one place, on the step's own words, and that place is there.
  const page = await open('/about/', 1366);
  const steps = await page.evaluate(() => [...document.querySelectorAll('ol.grew > li')].map((li) => [...li.querySelectorAll('a')].map((a) => ({ href: a.getAttribute('href'), words: a.textContent.trim() }))));
  ok(steps.every((links) => links.length === 1 && links[0].words), 'every step links on to one place', JSON.stringify(steps));
  const own = steps.flat().filter((l) => !/^https?:/.test(l.href));
  const reached = await Promise.all(own.map(async ({ href }) => {
    const [path, id] = href.split('#');
    const reply = await fetch(`http://127.0.0.1:${PORT}${path || '/about/'}`); // from here, because the page's own CSP refuses it
    const html = await reply.text();
    return { href, there: reply.ok && (!id || html.includes(`id="${id}"`)) };
  }));
  ok(own.length >= 7 && reached.every((r) => r.there), "each link reaches a page of ours, and each # a section there", JSON.stringify(reached.filter((r) => !r.there)));
  await page.close();
}

console.log('About: the section links stay in view');
for (const [width, height] of [[1366, 900], [1000, 800], [390, 844], [320, 640]]) {
  const page = await open('/about/', width, height);
  const hrefs = await page.evaluate(() => [...document.querySelectorAll('nav.jump a')].map((a) => a.getAttribute('href')));
  ok(hrefs.join() === '#why,#grew,#asked,#talks,#for,#contact', `${width}: a link to each section`, hrefs.join());
  const bar = () => page.evaluate(() => { const n = document.querySelector('nav.jump'); const r = n.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, height: r.height, background: getComputedStyle(n).backgroundColor, page: getComputedStyle(document.body).backgroundColor }; });
  const first = await bar();
  ok(first.height <= 64, `${width}: the links keep to one line, so the bar stays small`, JSON.stringify(first));
  ok(first.background === first.page, `${width}: the page does not show through the bar`, JSON.stringify(first));
  for (const href of hrefs) {
    await page.locator(`nav.jump a[href="${href}"]`).click();
    const at = await page.evaluate((h) => {
      const n = document.querySelector('nav.jump').getBoundingClientRect(), head = document.querySelector(`${h} h2`).getBoundingClientRect();
      return { bar: n.top, barBottom: n.bottom, head: head.top, foot: head.bottom, screen: window.innerHeight };
    }, href);
    ok(near(at.bar, 0), `${width}: at ${href} the links are still there`, JSON.stringify(at));
    ok(at.head >= at.barBottom && at.foot <= at.screen, `${width}: and its heading lands in view, clear of the bar`, JSON.stringify(at));
  }
  // The danger is a link already under the bar when Tab reaches it: on screen as far as the browser knows, so nothing would move it.
  const focus = await page.evaluate(() => {
    const link = document.querySelector('ol.grew a[href="/api/"]');
    window.scrollBy(0, link.getBoundingClientRect().top - 20);
    const before = link.getBoundingClientRect().top;
    link.focus();
    const n = document.querySelector('nav.jump').getBoundingClientRect(), r = link.getBoundingClientRect();
    return { bar: n.bottom, before, link: r.top };
  });
  ok(near(focus.before, 20) && focus.link >= focus.bar, `${width}: a link reached by Tab is not hidden under the bar`, JSON.stringify(focus));
  ok(await sideways(page) <= 0, `${width}: nothing scrolls the page sideways`);
  await page.close();
}
{
  const page = await open('/about/', 844, 390);
  await page.evaluate(() => window.scrollTo(0, 1200));
  const top = await page.evaluate(() => document.querySelector('nav.jump').getBoundingClientRect().top);
  ok(top < 0, 'a short window keeps its height: the links stay at the top of the page', String(top));
  await page.close();
}
// A mouse cannot swipe the bar sideways, so on a desktop window every link must be in view (Bill's pick D, 2026-11-07:
// at 820 px two of six ran past the edge, reachable only by Tab or Shift+wheel). Full names wherever they fit.
for (const [width, words] of [[1366, 'long'], [1000, 'long'], [900, 'short'], [820, 'short'], [720, 'short']]) {
  const page = await open('/about/', width, 800);
  const fit = await page.evaluate(() => {
    const n = document.querySelector('nav.jump'), edge = n.getBoundingClientRect().right;
    const names = [...n.querySelectorAll('a')].map((a) => a.innerText.trim());
    return { spill: n.scrollWidth - n.clientWidth, lastRight: [...n.querySelectorAll('a')].at(-1).getBoundingClientRect().right, edge, names };
  });
  ok(fit.spill <= 0 && fit.lastRight <= fit.edge, `${width}: every section link is in view, none past the bar's edge`, JSON.stringify(fit));
  const long = fit.names.includes('Why I built it') && fit.names.includes('Get in touch');
  ok(words === 'long' ? long : (fit.names.join() === "Why,How it grew,Questions,Talks,Who it's for,Contact"), `${width}: ${words === 'long' ? 'the full names' : 'the short names'}`, fit.names.join());
  await page.close();
}

// ---- How it works ----

console.log('How it works: the worked example');
{
  const page = await open('/how-it-works/', 1366);
  const rows = await page.evaluate(() => [...document.querySelectorAll('table.sum tbody tr, table.sum tfoot tr')].map((tr) => {
    const track = tr.querySelector('.bar');
    const fill = track?.querySelector('i');
    const cells = [...tr.querySelectorAll('td')].map((td) => td.textContent.trim());
    return { name: tr.querySelector('th').textContent.trim(), value: Number(tr.closest('tfoot') ? cells.at(-1) : cells[0]), share: fill ? fill.getBoundingClientRect().width / track.getBoundingClientRect().width : null, colour: fill && getComputedStyle(fill).backgroundColor, hidden: track?.getAttribute('aria-hidden') };
  }));
  ok(rows.length === 6, 'five scores and the overall score', JSON.stringify(rows.map((r) => r.name)));
  ok(rows.every((r) => r.share !== null && Math.abs(r.share - r.value / 10) < 0.01), 'each bar is the length its figure says, from a true zero to 10', JSON.stringify(rows.map((r) => [r.value, r.share])));
  ok(rows.every((r) => r.colour === scoreColour(r.value)), 'in the colours every surface gives a score', JSON.stringify(rows.map((r) => [r.value, r.colour])));
  ok(rows.every((r) => r.hidden === 'true'), 'and the figure beside it is what a screen reader reads');
  ok(await page.evaluate(() => !document.querySelector('table.sum').closest('details') && document.querySelector('table.sum').checkVisibility()), 'the example is open, not in a fold');
  ok(await page.evaluate(() => Boolean(document.querySelector('.example p.cost'))), 'what a zero costs is still said under it');

  console.log('How it works: the bands and the folds');
  ok(await background(page, '#short') === TINT, 'the short version sits on the warm band');
  ok(await background(page, '#limits') === WATER, "what it can't tell you sits on the cool band");
  ok(await page.evaluate(() => document.querySelectorAll('#limits ul.plain li').length) === 6, 'all six limits are kept');
  const scores = await page.evaluate(() => [...document.querySelectorAll('dl.scores > div')].map((n) => [getComputedStyle(n).backgroundColor, Math.round(n.getBoundingClientRect().top)]));
  ok(scores.length === 5 && scores.every(([c]) => c === PAPER) && new Set(scores.map(([, y]) => y)).size === 2, 'five scores as paper cards, on two rows', JSON.stringify(scores));
  const ids = await page.evaluate(() => [...document.querySelectorAll('section[id]')].map((s) => s.id));
  ok(['short', 'see-it', 'example', 'scores', 'data', 'planes-overhead', 'overall', 'limits', 'credits', 'fresh', 'coverage'].join() === ids.join(), 'every section keeps its id, in this order', ids.join());

  const folds = await page.evaluate(() => [...document.querySelectorAll('details.more')].map((d) => {
    const s = d.querySelector('summary');
    return { open: d.open, row: Math.abs(s.getBoundingClientRect().width - d.parentElement.clientWidth) < 8, name: s.textContent.trim() };
  }));
  ok(folds.length === 5 && folds.every((f) => !f.open && f.row), 'five folds, each a closed full-width row', JSON.stringify(folds));
  await page.click('details.more summary');
  ok(await page.evaluate(() => document.querySelector('details.more').open && document.querySelector('details.more > :not(summary)').checkVisibility()), 'and a fold opens');
  ok(await sideways(page) <= 0, 'nothing scrolls the page sideways');
  ok(page.errors.length === 0, 'no page errors', page.errors.join(' '));
  await page.close();
}
for (const width of [390, 320]) {
  const page = await open('/how-it-works/', width, 800);
  const columns = await page.evaluate(() => new Set([...document.querySelectorAll('dl.scores > div')].map((n) => Math.round(n.getBoundingClientRect().left))).size);
  ok(columns === 1, `${width}: the five scores stack`);
  ok(await sideways(page) <= 0, `${width}: nothing scrolls the page sideways`);
  await page.close();
}

await browser.close();
server.close();
console.log(`\npage bands: ${checks - failures} of ${checks} checks passed`);
if (failures) process.exit(1);
