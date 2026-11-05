// About and How it works on Stitch's layout (2026-11-05, Bill's brief of 4 Nov), measured on the page.
//
// WHY THIS EXISTS. Both pages are static, and every other gate reads their WORDS or scans them for contrast. None can see
// what this rebuild is: that the grey boxes of the drafts are real pictures, the bands are the site's colours, a 16:9 crop
// is 16:9, "How it grew" runs along its rail in order without one step sitting on another, and a bar is the length its
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

console.log('About: How it grew');
const along = (page) => page.evaluate(() => {
  const list = document.querySelector('ol.grew');
  const steps = [...list.children].map((li) => {
    const r = li.getBoundingClientRect();
    const dot = getComputedStyle(li, '::after');
    const dotTop = dot.top === 'auto' ? r.top - parseFloat(dot.bottom) - parseFloat(dot.height) : r.top + parseFloat(dot.top);
    return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, spill: li.scrollWidth - li.clientWidth, dotY: dotTop + parseFloat(dot.height) / 2, dotX: r.left + parseFloat(dot.left) };
  });
  const rail = getComputedStyle(list, '::before');
  return { steps, display: getComputedStyle(list).display, railHeight: rail.height, top: list.getBoundingClientRect().top, rows: getComputedStyle(list).gridTemplateRows };
});
const STORY = ['The first map', 'Sky Score Radar', 'Data first', 'An iPhone app', 'Beyond London', "Deen Developers' Build Night", 'AI Tinkerers London', 'Flight paths from the official routes', 'The Bay Area, and the air nearby', 'London Geo Meetup'];
for (const width of [1366, 1320, 1920]) {
  const page = await open('/about/', width);
  const g = await along(page);
  const s = g.steps;
  ok(s.length === 10 && g.display === 'grid', `${width}: ten steps, across the page`);
  ok(s.every((x, i) => !i || x.left > s[i - 1].left + 40), `${width}: in order along the rail, left to right`, s.map((x) => Math.round(x.left)).join(' '));
  const railY = g.top + parseFloat(g.rows.split(' ')[0]) + 44;
  ok(s.every((x, i) => (i % 2 ? x.top > railY : x.bottom < railY)), `${width}: alternating above and below the rail`, JSON.stringify({ railY, s: s.map((x) => [x.top, x.bottom]) }));
  ok(s.every((x) => Math.abs(x.dotY - railY) <= 2), `${width}: every waypoint sits on the rail`, s.map((x) => Math.round(x.dotY)).join(' '));
  const hit = s.flatMap((a, i) => s.slice(i + 1).filter((b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom).map(() => i));
  ok(hit.length === 0, `${width}: no step sits on another`, hit.join());
  ok(s.every((x) => x.width >= 185 && x.spill <= 0), `${width}: each step has room for a readable line, and nothing spills out`, s.map((x) => Math.round(x.width)).join(' '));
  ok(s[0].width > s[1].width * 1.4, `${width}: the first card is wider, for the film`, `${Math.round(s[0].width)} against ${Math.round(s[1].width)}`);
  const row = (i) => s.filter((_, n) => n % 2 === i);
  ok([0, 1].every((i) => new Set(row(i).map((x) => Math.round(x.top))).size === 1), `${width}: the cards in a row line up`);
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
  ok(cards.labelLines !== null && cards.labelLines <= 4 && cards.still >= 100, `${width}: the film stays in the first card, with room for its label`, JSON.stringify(cards));
  await page.close();
}
for (const width of [1319, 1080, 760, 390, 320]) {
  const page = await open('/about/', width, 800);
  const g = await along(page);
  ok(g.display !== 'grid' && g.steps.every((x, i) => !i || x.top >= g.steps[i - 1].bottom - 1), `${width}: the steps run down the page, as they always have`);
  ok(await sideways(page) <= 0, `${width}: nothing scrolls the page sideways`);
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
