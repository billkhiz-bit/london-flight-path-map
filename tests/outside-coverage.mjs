// A postcode no city covers must be told so - not analysed against the city on screen.
//
// WHY THIS EXISTS. On 2026-09-26 a user wrote in: "The closest airport is
// Norwich airport, not Heathrow." Reproduced on the live site: searching
// NR2 1NE (central Norwich) from the default London view printed "Nearest
// airport: Stansted (109.4 km)" and "This area has low aircraft noise",
// five kilometres from Norwich Airport. triggerSearch() switched to the
// postcode's own city only when a covered city held it; for anywhere else it
// fell through to the city on screen and measured Norwich against London.
//
// Measuring the fix turned up the same defect INSIDE coverage: postcodes.io
// writes "St. Helens" and the registry "St Helens", so every St Helens
// postcode was analysed against whichever city was showing.
//
// WHAT IT ASSERTS
//   1. Offline, every postcodes.io district spelling in
//      tests/fixtures/postcodes-io-districts.json (one per covered borough,
//      86) derives to its own city. A registry rename or a new punctuation
//      quirk fails here, not in a user's inbox.
//   2. Through the real search box, at desktop and phone widths:
//      - an Exeter postcode renders NOT COVERED YET, lists the covered cities,
//        links no scorecard and carries no "Nearest airport" claim at all;
//      - a Norwich postcode (API-only since 2026-09-27) renders NOT ON THE MAP
//        YET and links /area/norwich/norwich/, again with no airport claim;
//      - a "St. Helens" postcode lands on Merseyside with a real analysis.
//   3. Offline, the AREA_SCORECARDS table: every URL in it is a page that
//      exists in area/, an outcode-style NAME lookup ("Nottingham", which the
//      registry holds as "City of Nottingham") finds its card, and a name no
//      card holds finds none.
//   postcodes.io is STUBBED with its real response shape, and every other
//   off-site request is aborted, so no third party can make this flaky.
//
//   node tests/outside-coverage.mjs

import { chromium } from '@playwright/test';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const PORT = 8937;
const TYPES = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.mjs': 'application/javascript',
  '.json': 'application/json',
  '.css': 'text/css',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.webmanifest': 'application/manifest+json',
  '.png': 'image/png',
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

const fixture = JSON.parse(await readFile(join(ROOT, 'tests', 'fixtures', 'postcodes-io-districts.json'), 'utf8'));
const sthelens = fixture.districts.find((d) => d.admin_district === 'St. Helens');

// Real postcodes.io shapes (trimmed to the fields the page reads).
const STUBS = {
  NR21NE: {
    postcode: 'NR2 1NE', latitude: 52.628, longitude: 1.2921, admin_district: 'Norwich', admin_ward: 'Mancroft', country: 'England',
    codes: { admin_district: 'E07000148' },
  },
  EX11HS: {
    postcode: 'EX1 1HS', latitude: 50.722209, longitude: -3.530574, admin_district: 'Exeter', admin_ward: "St David's", country: 'England',
    codes: { admin_district: 'E07000041' },
  },
  [sthelens.postcode.replace(/\s/g, '')]: {
    postcode: sthelens.postcode, latitude: 53.4186, longitude: -2.8196, admin_district: 'St. Helens', admin_ward: 'Rainhill', country: 'England',
  },
};

const failures = [];
let checks = 0;
const browser = await chromium.launch();

// 1. Offline derivation over every covered borough's postcodes.io spelling.
{
  const page = await browser.newPage();
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof deriveCityFromBorough === 'function', { timeout: 20000 });
  const out = await page.evaluate(
    (ds) => ds.map((d) => ({ ...d, derived: deriveCityFromBorough(d.admin_district) })),
    fixture.districts
  );
  const bad = out.filter((o) => o.derived !== o.city);
  checks += out.length;
  for (const b of bad) failures.push(`"${b.admin_district}" (${b.postcode}) derives ${b.derived}, expected ${b.city}`);
  console.log(`  ${bad.length ? 'FAIL' : 'ok  '} ${out.length} postcodes.io district spellings derive their own city`);
  await page.close();
}

// 3. The scorecard table itself.
{
  const page = await browser.newPage();
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof scorecardFor === 'function', { timeout: 20000 });
  const cards = await page.evaluate(() => AREA_SCORECARDS);
  checks++;
  if (cards.length < 3) failures.push(`AREA_SCORECARDS holds ${cards.length} entries; an empty table would link nothing`);
  for (const c of cards) {
    checks++;
    const res = await fetch(BASE + c.url.replace(/^\//, ''));
    await res.arrayBuffer();
    if (res.status !== 200) failures.push(`scorecard ${c.url} (${c.borough}) is linked but answers ${res.status}`);
  }
  const lookups = await page.evaluate(() => ({
    nottingham: scorecardFor({ admin_district: 'Nottingham' })?.url ?? null,
    broadland: scorecardFor({ admin_district: 'Broadland' })?.url ?? null,
    exeter: scorecardFor({ admin_district: 'Exeter' }),
  }));
  checks++;
  const lOk =
    lookups.nottingham === '/area/nottingham/city-of-nottingham/' &&
    lookups.broadland === '/area/norwich/broadland/' &&
    lookups.exeter === null;
  if (!lOk) failures.push(`scorecard name lookup: ${JSON.stringify(lookups)}`);
  console.log(`  ${lOk ? 'ok  ' : 'FAIL'} ${cards.length} scorecards link real pages; name fallback finds only its own`);
  await page.close();
}

// 2. Through the search box.
async function search(vp, query) {
  const ctx = await browser.newContext({ viewport: vp, isMobile: vp.width < 900, hasTouch: vp.width < 900 });
  const page = await ctx.newPage();
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (route) => {
    const m = route.request().url().match(/api\.postcodes\.io\/postcodes\/([A-Z0-9]+)$/i);
    if (m && STUBS[m[1].toUpperCase()]) {
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ status: 200, result: STUBS[m[1].toUpperCase()] }) });
    }
    return route.abort();
  });
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof triggerSearch === 'function', { timeout: 20000 });
  // Poll for the RESULT state, never a sleep: SEARCHING... is the only title
  // this could otherwise be read in.
  await page.evaluate((q) => triggerSearch(q), query);
  await page
    .waitForFunction(() => !/SEARCHING/.test(document.getElementById('sidebar-title').textContent), { timeout: 20000 })
    .catch(() => {});
  const state = await page.evaluate(() => {
    const content = document.getElementById('sidebar-content');
    const titleEl = document.getElementById('sidebar-title');
    // SHOWN means a sighted visitor can see it and a finger can reach it: the
    // element has a box inside the viewport and is what is under its own
    // centre. Until 2026-10-05 this gate read `innerText` alone, and for an
    // element that is not rendered `innerText` returns the text anyway - so
    // "phone Exeter says not covered" passed for nine days on a panel that
    // was `display: none` at every width up to 900px.
    // The FIRST line box, not the bounding box: a link that wraps onto a
    // second line has a bounding box whose centre is on neither line.
    const shown = (el) => {
      if (!el) return false;
      const r = el.getClientRects()[0];
      if (!r || !r.width || !r.height) return false;
      const x = r.left + r.width / 2;
      const y = r.top + r.height / 2;
      if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) return false;
      const top = document.elementFromPoint(x, y);
      return !!top && (top === el || el.contains(top));
    };
    const link = content.querySelector('.empty-state a');
    const box = content.getBoundingClientRect();
    return {
      title: titleEl.textContent.trim(),
      // Text only from a panel that is rendered; text nobody can see is not said.
      text: box.width && box.height ? content.innerText.replace(/\s+/g, ' ') : '',
      domText: content.textContent.replace(/\s+/g, ' ').trim(),
      // An outcome message is short and opens the panel, so its first
      // paragraph must be on screen. (A full analysis is long and its first
      // paragraph may sit below a landscape card's fold: not asked of it.)
      messageShown: shown(content.querySelector('.empty-state p')),
      titleShown: shown(titleEl),
      city: document.querySelector('.city-selector .city-btn.active')?.textContent?.trim() ?? '',
      link: link?.getAttribute('href') ?? null,
      linkShown: shown(link),
      retryShown: shown(document.getElementById('search-retry-btn')),
    };
  });
  await ctx.close();
  return state;
}

// What a failed read looks like in the report: the DOM held the words and the
// screen did not.
const seen = (r) => (r.text && r.messageShown ? `text "${r.text.slice(0, 120)}"` : `NOTHING SHOWN (the DOM holds "${r.domText.slice(0, 80)}")`);

// Landscape is here because three mobile rules in this file's history were
// keyed on width while height was the failing dimension.
const VIEWPORTS = [
  { width: 1440, height: 900, label: 'desktop' },
  { width: 390, height: 844, label: 'phone' },
  { width: 844, height: 390, label: 'landscape' },
];
const PER_VIEWPORT = 5;

for (const vp of VIEWPORTS) {
  const x = await search(vp, 'EX1 1HS');
  checks++;
  const xOk =
    x.title === 'NOT COVERED YET' &&
    x.titleShown &&
    x.messageShown &&
    /Exeter/.test(x.text) &&
    !/nearest airport/i.test(x.text) &&
    /Greater Manchester/.test(x.text) &&
    x.link === null;
  if (!xOk) failures.push(`${vp.label} EX1 1HS: title "${x.title}" (shown ${x.titleShown}), link ${x.link}, ${seen(x)}`);
  console.log(`  ${xOk ? 'ok  ' : 'FAIL'} ${vp.label.padEnd(9)} Exeter is SHOWN as not covered, links nothing, claims no airport`);

  const n = await search(vp, 'NR2 1NE');
  checks++;
  const nOk =
    n.title === 'NOT ON THE MAP YET' &&
    n.titleShown &&
    n.messageShown &&
    /Norwich/.test(n.text) &&
    !/nearest airport/i.test(n.text) &&
    n.link === '/area/norwich/norwich/' &&
    n.linkShown;
  if (!nOk) failures.push(`${vp.label} NR2 1NE: title "${n.title}", link ${n.link} (shown ${n.linkShown}), ${seen(n)}`);
  console.log(`  ${nOk ? 'ok  ' : 'FAIL'} ${vp.label.padEnd(9)} Norwich's scorecard link is SHOWN, with no airport claim`);

  const s = await search(vp, sthelens.postcode);
  checks++;
  const sOk = s.title !== 'NOT COVERED YET' && s.city === 'Merseyside' && /nearest airport/i.test(s.text);
  if (!sOk) failures.push(`${vp.label} ${sthelens.postcode}: title "${s.title}", city "${s.city}"`);
  console.log(`  ${sOk ? 'ok  ' : 'FAIL'} ${vp.label.padEnd(9)} "St. Helens" lands on Merseyside with an analysis`);

  // The two outcomes that are not about coverage live behind the same panel
  // and were hidden by the same rule: a name nothing matches, and a lookup
  // that could not be reached (postcodes.io is aborted for any postcode this
  // file does not stub, which is exactly that).
  const nf = await search(vp, 'qwertyplace');
  checks++;
  const nfOk = nf.title === 'NOT FOUND' && nf.titleShown && nf.messageShown && /not found/i.test(nf.text);
  if (!nfOk) failures.push(`${vp.label} qwertyplace: title "${nf.title}" (shown ${nf.titleShown}), ${seen(nf)}`);
  console.log(`  ${nfOk ? 'ok  ' : 'FAIL'} ${vp.label.padEnd(9)} a name nothing matches is SHOWN as not found`);

  const cf = await search(vp, 'ZZ1 1ZZ');
  checks++;
  const cfOk = cf.title === 'CONNECTION ISSUE' && cf.titleShown && cf.messageShown && /connection problem/i.test(cf.text) && cf.retryShown;
  if (!cfOk) failures.push(`${vp.label} ZZ1 1ZZ (lookup unreachable): title "${cf.title}", retry shown ${cf.retryShown}, ${seen(cf)}`);
  console.log(`  ${cfOk ? 'ok  ' : 'FAIL'} ${vp.label.padEnd(9)} an unreachable lookup is SHOWN, with its retry button`);
}

await browser.close();
server.close();

// districts + table size + at least 3 page fetches + lookups + PER_VIEWPORT per viewport.
const expected = fixture.districts.length + 5 + PER_VIEWPORT * VIEWPORTS.length;
if (checks < expected) {
  console.error(`\nFAIL: ran ${checks} checks, expected at least ${expected}.`);
  process.exit(1);
}
if (failures.length) {
  console.error(`\nFAIL: ${failures.length} problem(s):`);
  for (const f of failures) console.error('  - ' + f);
  process.exit(1);
}
console.log(`\nOutside coverage is said, not analysed; ${fixture.districts.length} covered spellings derive correctly.`);
