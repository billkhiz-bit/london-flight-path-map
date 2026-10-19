// The front page (home/index.html + js/home-engine.mjs, at / since 2026-10-06;
// tests/preview-home.mjs while it was trialled at /preview/) is a tool,
// not a picture: a borough tap opens the council area's figures, the search
// takes a postcode or a place name, the routes explain themselves, the URL
// carries the state. None of that is seen by any other gate - a11y, responsive
// and fonts scan the LANDING state - so this one drives each interaction and
// reads the DOM it produced, offline:
//
//   - the open data CSV is the holder of every borough's score, so a card's
//     score is compared against the CSV row (parity with the data, not with
//     the flag the click sets);
//   - postcodes.io and /v1/environment are STUBBED with three real response
//     shapes captured on 2026-10-03 - measured (TW9), estimated (NW1 7PJ,
//     `aircraftQuietEstimated`, the branch the mockup never rendered) and
//     outside every city (EX1 1HS) - and every other offsite request is
//     aborted, so the gate cannot go red on someone else's latency.
//
// It is served HERE the way the SITE serves it: every URL is resolved through
// the Makefile's own upload lines (`make.py --dry-run`), so / is the front page,
// /map/ the full map, /reports/ the reports pages - and a file no target uploads
// is noticed rather than quietly served off the working tree.
//
// Run: node tests/front-page.mjs   (in preflight, blocking)
import { chromium } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { createServer } from 'node:http';
import { readFile, unlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { extname, join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { stubLiveApi } from './stub-live-api.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const PORT = 8941;
const TYPES = {
  '.html': 'text/html', '.js': 'application/javascript', '.mjs': 'application/javascript', '.json': 'application/json',
  '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.csv': 'text/csv', '.pdf': 'application/pdf',
};
// THE LIVE ROUTING, read from the Makefile (2026-10-06). The repo and the site
// disagree at the root since the front page took / and the map moved to /map/,
// so serving the working tree path for path would test a layout nobody visits.
// Each upload line becomes a rule from an S3 key to the file it came from.
const makefile = await readFile(join(ROOT, 'Makefile'), 'utf8');
const deployTargets = [...makefile.matchAll(/^([a-z0-9-]+-deploy):/gm)].map((m) => m[1]);
const dryRun = execFileSync('python', ['scripts/make.py', '--dry-run', ...deployTargets], { cwd: ROOT, encoding: 'utf8' });
const rules = [];
for (const line of dryRun.split(/\r?\n/)) {
  const m = /aws s3 (cp|sync)\s+(\S+)\s+s3:\/\/[^/\s]+\/(\S*)/.exec(line);
  if (!m) continue;
  const [, verb, src, dest] = m;
  // aws's --include patterns match the path under the source folder, and * crosses a slash.
  const includes = [...line.matchAll(/--include\s+"([^"]+)"/g)].map((x) => new RegExp(`^${x[1].replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*')}$`));
  if (verb === 'sync' || /--recursive/.test(line)) rules.push({ prefix: dest, src, includes });
  else rules.push({ key: dest.endsWith('/') ? dest + src.split('/').pop() : dest, src });
}
// CloudFront's rewrite: a folder or an extensionless path is served from its index.html.
const keyOf = (p) => (p.endsWith('/') ? `${p}index.html` : extname(p) ? p : `${p}/index.html`).replace(/^\//, '');
const sourceOf = (key) => {
  for (const r of rules) {
    if (r.key !== undefined && r.key === key) return r.src;
    if (r.prefix !== undefined && key.startsWith(r.prefix)) {
      const rest = key.slice(r.prefix.length);
      if (!r.includes.length || r.includes.some((g) => g.test(rest))) return join(r.src, rest);
    }
  }
  return null;
};
// Paths the pages asked for that NO upload line serves. Served off the working tree
// anyway, so the page still renders and the check at the end names each one.
const unrouted = new Set();
const server = createServer(async (req, res) => {
  const p = decodeURIComponent(req.url.split('?')[0]);
  let src = sourceOf(keyOf(p));
  if (!src) {
    unrouted.add(p);
    src = keyOf(p);
  }
  try {
    const buf = await readFile(join(ROOT, src));
    res.writeHead(200, { 'Content-Type': TYPES[extname(src)] || 'application/octet-stream' });
    res.end(buf);
  } catch {
    res.writeHead(404);
    res.end('not found');
  }
});
await new Promise((r) => server.listen(PORT, '127.0.0.1', r));
const BASE = `http://127.0.0.1:${PORT}/`;

// The CSV the page reads, parsed here independently (no quoted fields in it today; assert that).
const csvText = await readFile(join(ROOT, 'open-data', 'sky-score-boroughs.csv'), 'utf8');
if (csvText.includes('"')) throw new Error('the CSV has quoted fields; this parser (and the assumption) needs revisiting');
const [head, ...body] = csvText.trim().split(/\r?\n/).map((l) => l.split(','));
const CSV = body.map((r) => Object.fromEntries(head.map((h, i) => [h, r[i] ?? ''])));
const csvRow = (name) => CSV.find((r) => r.borough === name);
// How many routes on the map cross each area (scripts/build_area_route_crossings.mjs): "avoid aircraft
// noise" needs the lowest band AND none crossing (audit 2026-10-16 I-3).
const CROSS = JSON.parse(await readFile(join(ROOT, 'data', 'area-route-crossings.json'), 'utf8')).cities;
const normName = (s) => s.toLowerCase().replace(/&/g, 'and').replace(/[.,'']/g, '').replace(/\s+/g, ' ').trim();
const crossesOf = (r) => {
  const m = CROSS[r.city];
  if (!m) return null;
  const k = Object.keys(m).find((n) => normName(n) === normName(r.borough));
  return k === undefined ? null : m[k];
};
const quietAndClear = (r) => r.quiet !== '' && Number(r.quiet) >= 10 && crossesOf(r) === 0;

// Real postcodes.io shapes, trimmed to what the page reads.
const GEO = {
  TW93PZ: { postcode: 'TW9 3PZ', latitude: 51.4713, longitude: -0.2894, admin_district: 'Richmond upon Thames' },
  NW17PJ: { postcode: 'NW1 7PJ', latitude: 51.539, longitude: -0.1426, admin_district: 'Camden' },
  EX11HS: { postcode: 'EX1 1HS', latitude: 50.722209, longitude: -3.530574, admin_district: 'Exeter' },
  M225RX: { postcode: 'M22 5RX', latitude: 53.3677, longitude: -2.2644, admin_district: 'Manchester' },
  // CONSTRUCTED, not a real postcode: a point 5 km out on Gatwick 26L's extended centreline,
  // given a London district so the page answers it. Every runway of Gatwick's record lacks a
  // glide angle, and no real covered postcode sits under one, so this is the only way to
  // reach the answer's "no glide path on record" sentence on purpose (section 11b).
  ZZ99GAP: { postcode: 'ZZ9 9GAP', latitude: 51.16029, longitude: -0.102, admin_district: 'Croydon' },
};
// Real /v1/environment shapes, captured 2026-10-03, keyed on the latitude the page sends.
const ENV = {
  '51.4713': { environment: { roadNoiseLdenDb: 53.1, roadNoiseWhoGuidelineDb: 53, no2AnnualMeanUgm3: 16.3, no2WhoGuidelineUgm3: 10, pm25AnnualMeanUgm3: 8.4, pm25WhoGuidelineUgm3: 5, aircraftNoiseLdenDb: 56.0, aircraftQuiet: 3.9, aircraftQuietCoverage: 'measured', aircraftNoiseWhoGuidelineDb: 45 }, notices: [] },
  '51.539': { environment: { roadNoiseLdenDb: 74.7, roadNoiseWhoGuidelineDb: 53, no2AnnualMeanUgm3: 23.0, no2WhoGuidelineUgm3: 10, pm25AnnualMeanUgm3: 9.5, pm25WhoGuidelineUgm3: 5, aircraftQuietEstimated: 9.0, aircraftQuietBasis: 'flight-path geometry, not measured', aircraftQuietCoverage: 'city' }, notices: [] },
  '50.722209': { environment: { no2AnnualMeanUgm3: 8.0, no2WhoGuidelineUgm3: 10, pm25AnnualMeanUgm3: 5.6, pm25WhoGuidelineUgm3: 5, aircraftQuietEstimated: 10.0, aircraftQuietCoverage: 'outside' }, notices: [] },
  '51.16029': { environment: { no2AnnualMeanUgm3: 9.0, no2WhoGuidelineUgm3: 10, pm25AnnualMeanUgm3: 6.0, pm25WhoGuidelineUgm3: 5, aircraftQuietEstimated: 6.0, aircraftQuietBasis: 'flight-path geometry, not measured', aircraftQuietCoverage: 'city' }, notices: [] },
  '53.3677': { environment: { roadNoiseLdenDb: 60.2, roadNoiseWhoGuidelineDb: 53, no2AnnualMeanUgm3: 14.1, no2WhoGuidelineUgm3: 10, pm25AnnualMeanUgm3: 7.2, pm25WhoGuidelineUgm3: 5, aircraftNoiseLdenDb: 64.0, aircraftQuiet: 2.0, aircraftQuietCoverage: 'measured', aircraftNoiseWhoGuidelineDb: 45 }, notices: [] },
};

const failures = [];
let checks = 0;
const ok = (cond, label, detail = '') => {
  checks++;
  console.log(`  ${cond ? 'ok  ' : 'FAIL'} ${label}${cond || !detail ? '' : `: ${detail}`}`);
  if (!cond) failures.push(label + (detail ? `: ${detail}` : ''));
};

// The OS street-map trial: every request the page makes of api.os.uk, answered with a 1x1 PNG.
const osTiles = [];
const PNG_1PX = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', 'base64');

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1366, height: 820 } });
// Named so a second context (the free report at 150% display scaling, section 18) answers the same way.
const OFFSITE = /^https?:\/\/(?!127\.0\.0\.1)/;
const stubOffsite = (route) => {
  const url = new URL(route.request().url());
  if (url.hostname === 'api.os.uk') {
    osTiles.push(url.href);
    return route.fulfill({ status: 200, contentType: 'image/png', body: PNG_1PX });
  }
  if (url.hostname === 'api.postcodes.io') {
    // Spaced or compact, as postcodes.io itself accepts both: the front page sends
    // TW93PZ and the street report sends TW9%203PZ.
    const key = decodeURIComponent(url.pathname.split('/').pop()).replace(/\s+/g, '').toUpperCase();
    const result = GEO[key] || null;
    return route.fulfill({ status: result ? 200 : 404, contentType: 'application/json', body: JSON.stringify({ status: result ? 200 : 404, result }) });
  }
  if (url.pathname.endsWith('/v1/environment')) {
    const body = ENV[url.searchParams.get('lat')];
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body || { error: 'unstubbed' }) });
  }
  return route.abort();
};
await context.route(OFFSITE, stubOffsite);
const page = await context.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
// Every file this run reads off the working tree, for the upload check at the end.
const fetched = new Set();
page.on('response', (res) => {
  const u = new URL(res.url());
  if (u.hostname === '127.0.0.1' && res.status() === 200) fetched.add(u.pathname);
});
const boroCount = () => page.locator('#map .boro').count();
const cardOpen = () => page.locator('#borough.is-open');
const answerOpen = () => page.locator('#answer.is-open');
const waitMap = async () => { await page.waitForSelector('#map .boro', { timeout: 20000 }); await page.waitForTimeout(150); };

// 1. Landing: London, 33 council areas, each a keyboard-reachable button with a CSV row.
await page.goto(BASE, { waitUntil: 'domcontentloaded' });
await waitMap();
ok((await boroCount()) === 33, 'London lands with 33 council areas');
const labels = await page.locator('#map .boro').evaluateAll((els) => els.map((e) => [e.getAttribute('role'), e.getAttribute('tabindex'), e.getAttribute('aria-label')]));
ok(labels.every(([r, t]) => r === 'button' && t === '0'), 'every council area is role=button and in the tab order');
ok((await page.locator('#map').getAttribute('role')) !== 'img', 'the svg is not role=img (its children are buttons)');
// The SET of cities, not a count: New York became a chip on 2026-10-06 (it was a link out to
// the full map), and a count would only have said "one more".
const chipCities = (await page.locator('#chips button').evaluateAll((bs) => bs.map((b) => b.dataset.city))).sort().join(' ');
ok(
  chipCities === 'bayarea bristol leicester london manchester merseyside nyc southyorkshire teesside tyneandwear westmidlands westyorkshire' &&
    (await page.locator('#chips a').count()) === 0,
  'a chip for every city on the front page, New York included, and no link out',
  chipCities
);
await page.keyboard.press('Tab');
const onSkip = await page.evaluate(() => document.activeElement?.matches('a.skip[href="#pc"]'));
ok(onSkip, 'the first Tab reaches "Skip to the search" (audit I-5: the box was stop 56)');
// Enter only on the skip link: on anything else the first stop is a header link, and Enter would leave the page.
if (onSkip) await page.keyboard.press('Enter');
ok(onSkip && (await page.evaluate(() => document.activeElement?.id === 'pc')), 'and Enter on it lands in the search box');
// And without the skip link, Tab reaches the search before any council area
// (I-5): the panel came after the map in the page, so the map's thirty-odd
// controls came first, and on a phone focus order ran against visual order.
{
  await page.locator('a.brand').focus();
  let pcAt = -1, boroAt = -1;
  for (let i = 1; i <= 80 && (pcAt < 0 || boroAt < 0); i++) {
    await page.keyboard.press('Tab');
    const here = await page.evaluate(() => (document.activeElement?.id === 'pc' ? 'pc' : document.activeElement?.classList.contains('boro') ? 'boro' : ''));
    if (here === 'pc' && pcAt < 0) pcAt = i;
    if (here === 'boro' && boroAt < 0) boroAt = i;
  }
  ok(pcAt > 0 && (boroAt < 0 || pcAt < boroAt), 'Tab reaches the search box before any council area', `search at ${pcAt}, first area at ${boroAt}`);
}
// The postcode -> city lookup is the PREVIEW's own copy, so the 86 real postcodes.io spellings the live map is
// held to (tests/fixtures/postcodes-io-districts.json) are run through it too. It missed Barking and Dagenham.
const spellings = JSON.parse(await readFile(join(ROOT, 'tests', 'fixtures', 'postcodes-io-districts.json'), 'utf8')).districts;
const derived = await page.evaluate(async (ds) => {
  const engine = await import('/js/home-engine.mjs');
  if (typeof engine.cityOf !== 'function') return null;
  return ds.map((d) => ({ ...d, got: engine.cityOf(d.admin_district) }));
}, spellings);
const wrong = derived ? derived.filter((d) => d.got !== d.city) : [{ admin_district: 'the engine exports no cityOf', got: '' }];
ok(spellings.length >= 80 && wrong.length === 0, `all ${spellings.length} postcodes.io district spellings resolve to their own city (audit I-1)`, wrong.map((d) => `${d.admin_district} -> ${d.got}`).join('; '));

// 1b. ASK FIRST, THEN THE TOOL (Bill, 2026-10-05). On a wide screen the page opens as
// v3 - the question centred over a faded map, the map's controls out of the way -
// and the first use makes it v2: the panel at the side, the map refitted beside it.
const introState = () =>
  page.evaluate(() => {
    const hero = document.querySelector('.hero').getBoundingClientRect();
    const panel = document.querySelector('.panel').getBoundingClientRect();
    return {
      intro: document.querySelector('.hero').classList.contains('is-intro'),
      centred: Math.abs(panel.left + panel.width / 2 - (hero.left + hero.width / 2)) < 4,
      atLeft: panel.left - hero.left < 40,
      legend: getComputedStyle(document.querySelector('.legend')).visibility,
      mapOpacity: Number(getComputedStyle(document.querySelector('#map')).opacity),
    };
  });
const before = await introState();
ok(before.intro && before.centred && before.legend === 'hidden' && before.mapOpacity < 0.5, 'on a wide screen the page opens as the question, centred over a faded map', JSON.stringify(before));
// WHERE THE SEARCH COVERS, before anyone types (2026-10-19): every UK region the API serves, its council
// areas adding up to the page's own figure, then New York and the Bay Area. Cardiff is the region the
// map's city buttons never named. scripts/build_coverage_strip.py --check holds the markup to the
// registry; this holds what a visitor sees.
// FOR DEVELOPERS (2026-10-19): two requests a developer can paste. Both on the API host js/api-base.js
// holds (window.API_BASE), the key ONLY ever the placeholder, the no-key one by lat and lon (the form
// /v1/environment answers; by postcode it is a 400), and Copy copies exactly what is shown. The clipboard
// is stubbed: a headless browser has none to read back.
{
  const dev = await page.evaluate(async () => {
    const copied = [];
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async (t) => { copied.push(t); } } });
    document.querySelector('button.copy[data-copy="dev-score"]')?.click();
    await new Promise((r) => setTimeout(r, 100));
    return {
      api: window.API_BASE || '',
      score: document.getElementById('dev-score')?.textContent || '',
      env: document.getElementById('dev-env')?.textContent || '',
      copied,
      status: document.getElementById('copy-status')?.textContent || '',
    };
  });
  ok(
    Boolean(dev.api) && dev.score === `curl '${dev.api}/v1/score?postcode=TW9+3PZ' \\\n  -H 'X-Api-Key: YOUR_KEY'` &&
      dev.env === `curl '${dev.api}/v1/environment?lat=51.4790&lon=-0.2860'` &&
      dev.copied.length === 1 && dev.copied[0] === dev.score && /^Copied/.test(dev.status),
    'the developer band shows two requests on the live API host, the key only a placeholder, and Copy copies exactly what is shown',
    JSON.stringify({ api: dev.api, score: dev.score.slice(0, 90), env: dev.env.slice(-50), copied: dev.copied.length, status: dev.status })
  );
}
// It is ONE LINE that opens the list: written out, the list made the card cover the whole faded map
// (the backdrop check below probed 0 points), so the summary is asserted visible and the list read open.
{
  const covers = await page.evaluate(() => {
    const el = document.querySelector('details.covers');
    if (!el) return null;
    const summary = el.querySelector('summary');
    const line = summary && summary.getBoundingClientRect().height > 0 && !el.open;
    el.open = true;
    const read = {
      visible: line,
      text: el.innerText,
      regions: [...el.querySelectorAll('li')].map((li) => [li.firstChild.textContent.trim(), Number(li.querySelector('b').textContent)]),
      figure: document.querySelector('.fig')?.textContent || '',
    };
    el.open = false; // closed again, so the checks that follow see the card as a visitor first does
    return read;
  });
  const fig = covers && /^(\d+)\s*council areas in (\d+) UK city regions/.exec(covers.figure);
  const total = covers ? covers.regions.reduce((s, [, n]) => s + n, 0) : 0;
  ok(
    Boolean(covers && fig) && covers.visible && covers.regions.length === Number(fig[2]) && total === Number(fig[1]) &&
      covers.regions.some(([name]) => name === 'Cardiff') && /plus New York's \d+ boroughs and \d+ Bay Area cities \(facts only\)/.test(covers.text),
    "before any search one line offers where it covers, and opens to every UK region adding up to the page's own figure, then New York and the Bay Area",
    JSON.stringify(covers && { regions: covers.regions.length, total, figure: covers.figure.slice(0, 50) })
  );
}
// The faded map is a BACKDROP while the question covers it (Bill, 2026-10-07): no hover, no
// tooltip, no click, no Tab stop behind the card (WCAG 2.2 2.4.11). Asked of the BROWSER, not of
// the attribute the fix sets: an 8 px grid over every council area's box, clear of the card and
// inside the window, must hit no area, and none may take focus. A grid, not one point per area:
// at 1366x820 the card covers all but ONE area's centre, and a probe of one proves little.
// Until 7 Oct this step tabbed to Havering behind the card.
const backdrop = await page.evaluate(() => {
  // The keyboard steps above leave the page scrolled; an off-screen point hit-tests nothing.
  // 'instant': the page scrolls smoothly by default, and a smooth scroll would still be moving.
  window.scrollTo({ top: 0, behavior: 'instant' });
  const panel = document.querySelector('.panel').getBoundingClientRect();
  const map = document.querySelector('#map').getBoundingClientRect();
  const boxes = [...document.querySelectorAll('#map .boro')].map((el) => el.getBoundingClientRect());
  let probed = 0;
  let hits = 0;
  // 8 px since 2026-10-14: the panel's tab row made the card taller, and a 12 px grid then found 33
  // points clear of it, under the floor below. The floor stays; the grid got finer. 6 px since
  // 2026-10-19, for the same reason: the coverage line made the card one line taller and 8 px found 34.
  for (let x = Math.max(map.left, 0) + 2; x < Math.min(map.right, innerWidth); x += 6) {
    for (let y = Math.max(map.top, 0) + 2; y < Math.min(map.bottom, innerHeight); y += 6) {
      if (x > panel.left - 8 && x < panel.right + 8 && y > panel.top - 8 && y < panel.bottom + 8) continue;
      if (!boxes.some((r) => x >= r.left && x <= r.right && y >= r.top && y <= r.bottom)) continue;
      probed++;
      if (document.elementFromPoint(x, y)?.closest?.('.boro')) hits++;
    }
  }
  const focusable = [...document.querySelectorAll('#map .boro')].filter((el) => {
    el.focus();
    return document.activeElement === el;
  }).length;
  document.activeElement?.blur?.();
  const r = (v) => Math.round(v);
  const areas = boxes.reduce((u, b) => [Math.min(u[0], b.left), Math.min(u[1], b.top), Math.max(u[2], b.right), Math.max(u[3], b.bottom)], [Infinity, Infinity, -Infinity, -Infinity]);
  return { probed, hits, focusable, card: [panel.left, panel.top, panel.right, panel.bottom].map(r), areas: areas.map(r), window: [innerWidth, innerHeight] };
});
ok(backdrop.probed >= 40 && backdrop.hits === 0 && backdrop.focusable === 0, 'while the question covers it, the faded map takes no pointer and no focus', JSON.stringify(backdrop));
// The first use, here by keyboard and by the honest route: "Or explore the map", then Enter on
// the council area it focuses.
await page.locator('#explore-map').focus();
await page.keyboard.press('Enter');
await page.waitForFunction(() => document.activeElement?.classList.contains('boro'), null, { timeout: 5000 });
await page.keyboard.press('Enter');
await page.waitForSelector('#borough.is-open', { timeout: 5000 });
const after = await introState();
ok(!after.intro && after.atLeft && after.legend === 'visible' && after.mapOpacity === 1, 'the first use turns it into the tool: panel at the side, map and controls back', JSON.stringify(after));

// 1c. Bill, 2026-10-06: the bar leads with the map as its one button and drops the Bay Area;
// the intro stops promising "tap a council area on the map" while that map sits faded and
// hidden behind it, and offers "Or explore the map" instead.
{
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await waitMap();
  const nav = await page.locator('header.top nav a').evaluateAll((as) => as.map((a) => [a.textContent.trim(), a.className]));
  ok(nav.length > 0 && !nav.some(([t]) => /Bay Area/.test(t)) && nav[0][0] === 'Full map' && nav[0][1].includes('nav-cta'), 'the bar leads with the full map as its button and no longer lists the Bay Area', JSON.stringify(nav));
  ok(!/tap a council area/i.test(await page.locator('.panel .lead').textContent()), 'the intro no longer promises a map it is hiding');
  await page.click('#explore-map');
  await page.waitForTimeout(300);
  const st = await introState();
  const focused = await page.evaluate(() => document.activeElement?.classList.contains('boro'));
  ok(!st.intro && st.legend === 'visible' && focused && (await page.locator('#explore-map').isHidden()), '"Or explore the map" ends the intro, focuses a council area, then steps aside', JSON.stringify({ ...st, focused }));
}

// 2. Click Camden: the card opens with the CSV's score and components, and the URL says so.
await page.locator('#map .boro[aria-label^="Camden"]').click();
await page.waitForSelector('#borough.is-open', { timeout: 5000 });
const camden = csvRow('Camden');
const cardScore = await page.locator('#borough .score strong').textContent();
ok(cardScore === camden.score, 'Camden card prints the open data CSV score', `card ${cardScore}, CSV ${camden.score}`);
const bars = await page.locator('#borough .rows .row .val').allTextContents();
ok(bars.length === 5 && bars[0].startsWith(`${camden.quiet} /`) && bars[4].startsWith(`${camden.env} /`), 'five component bars match the CSV', bars.join(' | '));
const facts = await page.locator('#borough .facts dd').allTextContents();
ok(facts.some((f) => f.includes(Number(camden.avg_price_gbp).toLocaleString('en-GB'))) && facts.some((f) => f.startsWith(`${camden.crime_per_1000} offences`)), 'facts carry the price and crime figures', facts.join(' | '));
ok(facts.some((f) => f.includes(`${camden.flood_medium_or_high_pct}% of postcodes at medium or high`)), 'the card carries flood risk (the card promised it)');
const links = await page.locator('#borough .more a').evaluateAll((as) => as.map((a) => a.getAttribute('href')));
ok(links.includes('/area/london/camden/') && links.includes('/map/?city=london&borough=Camden'), 'links to the scorecard page and the full map at /map/', links.join(' '));
ok(await page.evaluate(() => location.search) === '?city=london&borough=Camden', 'URL carries ?city=&borough=');
ok((await page.locator('#map .boro.is-selected').getAttribute('aria-label')) === 'Camden: open its figures', 'the clicked area is highlighted');

// 3. Close returns focus to the search box; Escape closes too.
await page.locator('#borough-close').click();
ok((await cardOpen().count()) === 0, 'close button closes the card');
ok(await page.evaluate(() => document.activeElement?.id === 'pc'), 'close returns focus to the search box');
await page.locator('#map .boro[aria-label^="Hounslow"]').click();
await page.waitForSelector('#borough.is-open');
await page.keyboard.press('Escape');
ok((await cardOpen().count()) === 0, 'Escape closes the card');

// 4. Keyboard: focus a council area, Enter opens its card and moves focus into it.
await page.locator('#map .boro[aria-label^="Ealing"]').focus();
await page.keyboard.press('Enter');
await page.waitForSelector('#borough.is-open');
ok((await page.locator('#borough h2').textContent()) === 'Ealing', 'Enter on a focused council area opens it');
ok(await page.evaluate(() => document.activeElement?.tagName === 'H2'), 'focus moves to the card heading');
await page.keyboard.press('Escape');
const backTo = await page.evaluate(() => document.activeElement?.getAttribute('aria-label') || document.activeElement?.tagName || '');
ok((await cardOpen().count()) === 0 && backTo.startsWith('Ealing'), 'Escape from inside the card returns focus to the council area that opened it (audit M-17)', backTo);

// 5. Every council area in every UK city has a CSV row, so no card can say "not scored" by accident.
const missing = [];
let drawn = 0;
for (const key of ['london', 'manchester', 'westmidlands', 'westyorkshire', 'southyorkshire', 'merseyside', 'tyneandwear', 'bristol', 'leicester', 'teesside']) {
  await page.locator(`#chips button[data-city="${key}"]`).click();
  await page.waitForFunction((k) => document.querySelector(`#chips button[data-city="${k}"]`)?.getAttribute('aria-pressed') === 'true' && document.querySelectorAll('#map .boro').length > 0, key);
  await page.waitForTimeout(200);
  const names = await page.locator('#map .boro').evaluateAll((els) => els.map((e) => e.getAttribute('aria-label').replace(/: open its figures$/, '')));
  drawn += names.length;
  for (const n of names) if (!csvRow(n)) missing.push(`${key}/${n}`);
}
ok(drawn === 86 && missing.length === 0, `all ${drawn} drawn council areas have a CSV row (expected 86)`, missing.join(', '));
ok(await page.evaluate(() => location.search) === '?city=teesside', 'a city chip sets ?city=');

// 6. Approach-line tooltip names the airport and the glide; the toggle hides the lines; the noise toggle hides the picture.
await page.locator('#chips button[data-city="london"]').click();
await page.waitForFunction(() => document.querySelectorAll('#map .boro').length === 33);
await page.waitForTimeout(200);
// Routes have no hit area (a wide one stole Hounslow's tap): move the mouse onto the midpoint of a final
// that is clear of the floating panel (Heathrow's 09L final runs west INTO the panel, where the svg sees nothing).
const mid = await page.locator('#map .lines .final').evaluateAll((ls) => {
  const r = ls[0].ownerSVGElement.getBoundingClientRect();
  const inset = JSON.parse(document.body.dataset.mapInset).left;
  const mids = ls.map((l) => [(+l.getAttribute('x1') + +l.getAttribute('x2')) / 2, (+l.getAttribute('y1') + +l.getAttribute('y2')) / 2]).filter(([x]) => x > inset + 40);
  const [x, y] = mids.sort((p, q) => q[0] - p[0])[0];
  return { x: r.left + x, y: r.top + y };
});
await page.mouse.move(mid.x, mid.y);
await page.waitForTimeout(100);
const tipText = await page.locator('#tip').textContent();
ok(/Heathrow|London City/.test(tipText) && /glide path/.test(tipText), 'hovering a route names the airport, runway and glide', tipText);
// The lines are clipped to the city's outline while their geometry runs on to the last waypoint, so a
// pointer on a clipped stretch must not raise a tooltip for a line that is not drawn there.
const clipped = await page.locator('#map .lines .departure').evaluateAll((paths) => {
  const svgEl = paths[0].ownerSVGElement;
  const r = svgEl.getBoundingClientRect();
  for (const p of paths) {
    const pts = p.getAttribute('d').slice(1).split('L').map((s) => s.split(' ').map(Number));
    for (let i = 0; i + 1 < pts.length; i++) {
      for (const f of [0.25, 0.5, 0.75]) {
        const x = r.left + pts[i][0] + f * (pts[i + 1][0] - pts[i][0]);
        const y = r.top + pts[i][1] + f * (pts[i + 1][1] - pts[i][1]);
        if (x < r.left + 2 || x > r.right - 2 || y < r.top + 2 || y > r.bottom - 2) continue;
        if (document.elementFromPoint(x, y) === svgEl) return { x, y };
      }
    }
  }
  return null;
});
ok(clipped !== null, 'a departure has a stretch outside the outline to test against');
if (clipped) {
  await page.mouse.move(clipped.x, clipped.y);
  await page.waitForTimeout(100);
  ok(await page.locator('#tip').evaluate((t) => getComputedStyle(t).display === 'none'), 'no route tooltip where the route is clipped away', await page.locator('#tip').textContent());
}
ok((await page.locator('#map .lines .departure').count()) > 0, 'London draws its published departure routes too');
ok((await page.locator('#map .lines').evaluate((g) => getComputedStyle(g).pointerEvents)) === 'none', 'routes take no pointer events, so every tap reaches a borough');
await page.locator('#toggle-lines').click();
ok(await page.locator('#map .lines').evaluate((g) => getComputedStyle(g).display === 'none'), 'the approach toggle hides the lines');
await page.locator('#toggle-lines').click();
ok(await page.locator('#map .lines').evaluate((g) => getComputedStyle(g).display !== 'none'), 'and shows them again');
ok((await page.locator('#noise-image').count()) === 1, 'London draws its DEFRA noise picture');
await page.locator('#toggle-noise').click();
ok(await page.locator('#noise-image').evaluate((g) => getComputedStyle(g).display === 'none'), 'the noise toggle hides the picture');
await page.locator('#toggle-noise').click();

// 6a. THE TOOLTIP'S WORDS REACH A KEYBOARD AND A FINGER (2026-10-09, audit 2026-10-05 M-15). Route
// explanations were hover-only: a tap opens the council area's card and a key cannot reach a line.
// The card now lists the routes across the area. Opened here by KEYBOARD alone, on the area under
// the very point hovered above, and it must carry that tooltip's text exactly.
// ONE reader of the card's routes row, run in the desktop page here and the phone page below.
const readRouteRow = () => {
  const dt = [...document.querySelectorAll('#borough.is-open .facts dt')].find((d) => d.textContent === 'Flight routes');
  const dd = dt?.nextElementSibling;
  if (!dd) return null;
  const items = [...dd.querySelectorAll('li')];
  return { text: dd.textContent, items: items.map((li) => li.textContent), titled: items.every((li) => li.querySelector('b') && li.textContent.length > 40), open: dd.querySelector('details')?.open ?? null };
};
const routeCard = () => page.evaluate(readRouteRow);
const hoveredArea = await page.evaluate(({ x, y }) => document.elementFromPoint(x, y)?.closest('.boro')?.getAttribute('aria-label') || '', mid);
let keyed = null;
// A route midpoint that is not over a council area FAILS with that said, rather than a 30 s wait on no element.
if (hoveredArea) {
  await page.locator(`#map .boro[aria-label="${hoveredArea}"]`).focus();
  await page.keyboard.press('Enter');
  await page.waitForSelector('#borough.is-open');
  // Counted first, so a card without the list FAILS below rather than timing out here.
  if (await page.locator('#borough .routes-across summary').count()) {
    await page.locator('#borough .routes-across summary').focus();
    await page.keyboard.press('Enter');
  }
  keyed = await routeCard();
}
ok(Boolean(hoveredArea) && keyed?.open === true && keyed.items.includes(tipText), `by keyboard alone, ${hoveredArea.replace(/: open its figures$/, '') || '(no council area under the hovered route)'}'s card lists the hovered route in the tooltip's words`, JSON.stringify(keyed)?.slice(0, 300));
// Sutton: no drawn route crosses it, and the card must not read as "no aircraft here".
await page.locator('#map .boro[aria-label^="Sutton"]').focus();
await page.keyboard.press('Enter');
await page.waitForFunction(() => document.querySelector('#borough.is-open h2')?.textContent === 'Sutton');
const sutton = await routeCard();
ok(/^None of the routes on this map crosses it\./.test(sutton?.text || '') && /radar/.test(sutton.text), 'an area no drawn route crosses says so, and that radar-directed paths are not drawn', sutton?.text);
// ...and names the routes the record holds no line for (audit 2026-10-09 M-4): Gatwick's runway is
// 18 km from Sutton's southern edge, and its routes are not drawn.
ok(/Routes: Gatwick's are not drawn here\./.test(sutton?.text || ''), "Sutton's card says Gatwick's routes are not drawn, not that no route is near", sutton?.text);
// Trafford read "None of the routes on this map crosses it" under Manchester's departures, which are
// published only as charts (M-4). Its card must say so, as a postcode's answer there does (M-7).
await page.locator('#borough-close').click();
await page.locator('#chips button[data-city="manchester"]').click();
await page.waitForFunction(() => document.querySelector('#chips button[data-city="manchester"]')?.getAttribute('aria-pressed') === 'true' && document.querySelectorAll('#map .boro').length === 10);
await page.locator('#map .boro[aria-label^="Trafford"]').focus();
await page.keyboard.press('Enter');
await page.waitForFunction(() => document.querySelector('#borough.is-open h2')?.textContent === 'Trafford');
const trafford = await routeCard();
ok(/Departure routes: Manchester's are published only as charts and are not drawn here\./.test(trafford?.text || ''), "Trafford's card says Manchester's departures are not drawn (audit 2026-10-09 M-4)", trafford?.text);
await page.locator('#borough-close').click();
// A city with no routes at all (South Yorkshire has no airport) prints no routes row.
await page.locator('#chips button[data-city="southyorkshire"]').click();
await page.waitForFunction(() => document.querySelector('#chips button[data-city="southyorkshire"]')?.getAttribute('aria-pressed') === 'true' && document.querySelectorAll('#map .boro').length === 4);
await page.locator('#map .boro[aria-label^="Barnsley"]').focus();
await page.keyboard.press('Enter');
await page.waitForFunction(() => document.querySelector('#borough.is-open h2')?.textContent === 'Barnsley');
ok((await routeCard()) === null, 'a city with no routes on its map prints no routes row');
await page.locator('#borough-close').click();
await page.locator('#chips button[data-city="london"]').click();
await page.waitForFunction(() => document.querySelectorAll('#map .boro').length === 33);
await page.waitForTimeout(200);

// 7. Zoom in scales the view; reset enables and returns to identity; marks keep their size.
ok(await page.locator('#zoom-reset').isDisabled(), 'reset is disabled at zoom 1');
await page.locator('#zoom-in').click();
await page.waitForTimeout(400);
const k1 = await page.locator('#map .view').evaluate((g) => /scale\(([\d.]+)\)/.exec(g.getAttribute('transform') || '')?.[1]);
ok(Number(k1) > 1.5, 'zoom in scales the view group', `k=${k1}`);
const apSize = await page.locator('#map .ap').first().evaluate((t) => parseFloat(t.getAttribute('font-size')));
ok(Math.abs(apSize * Number(k1) - 12) < 0.05, 'airport labels are counter-scaled to 12px on screen', `${apSize}px at k=${k1}`);
await page.locator('#zoom-reset').click();
await page.waitForTimeout(400);
const k0 = await page.locator('#map .view').evaluate((g) => /scale\(([\d.]+)\)/.exec(g.getAttribute('transform') || '')?.[1] ?? '1');
ok(Number(k0) === 1 && (await page.locator('#zoom-reset').isDisabled()), 'reset returns to zoom 1 and disables itself', `k=${k0}`);

// 7a. A slow outline file must not draw under another city's routes: choose Manchester, then London before it lands.
await page.route('**/data/manchester-boroughs.json', async (route) => { await new Promise((r) => setTimeout(r, 900)); await route.continue(); });
await page.locator('#chips button[data-city="manchester"]').click();
await page.locator('#chips button[data-city="london"]').click();
await page.waitForTimeout(1800);
const lateCount = await boroCount();
ok(lateCount === 33 && (await page.locator('#chips button[data-city="london"]').getAttribute('aria-pressed')) === 'true', 'a late outline file does not overwrite the city chosen after it', `${lateCount} council areas drawn`);
await page.unroute('**/data/manchester-boroughs.json');

// 8. A measured postcode: four rows, the runway line, the council-area line, the pin, the hand-off link.
await page.fill('#pc', 'TW9 3PZ');
await page.press('#pc', 'Enter');
await page.waitForSelector('#answer.is-open', { timeout: 10000 });
const vals = await page.locator('#ans-rows .val').allTextContents();
ok(vals.length === 4 && vals[0].startsWith('56 dB') && vals[0].includes('measured') && vals[1].startsWith('53.1 dB'), 'measured postcode renders four rows with the DEFRA readings', vals.join(' | '));
const routes = await page.locator('#ans-routes').textContent();
ok((await page.locator('#status').textContent()) === 'Showing the figures for TW9 3PZ.', 'a found postcode is announced in the live region, not left silent (audit M-14)', await page.locator('#status').textContent());
// ONE decimal, as the full map and the street report print it. TW9 3PZ is ~10.2 km out, the
// distance at which this page used to switch to whole km and print "10 km" (2026-10-09).
ok(/Nearest airport on the map: Heathrow, \d+\.\d km to the (west|north-west|south-west)/.test(routes), 'the answer names the nearest airport on the map with distance (one decimal, like the map) and direction', routes);
ok(/Under the Heathrow 27[LR] final approach, .* aircraft at about [\d,]+ ft/.test(routes), 'Kew is reported under a Heathrow 27 final approach at a height', routes);
// The nearest station (Bill, 2026-10-06: "show it first"): worked out HERE with this test's own
// distance maths over data/stations.json, so the shared nearestStation() cannot pass by agreeing
// with itself. TW9 3PZ is at the stub's 51.4713, -0.2894.
{
  const stations = Object.values(JSON.parse(await readFile(join(ROOT, 'data', 'stations.json'), 'utf8'))).flat();
  const r = Math.PI / 180;
  const km = (s) => {
    const [lon, lat] = s.coords;
    const dLat = (lat - 51.4713) * r, dLon = (lon + 0.2894) * r;
    return 2 * 6371.0088 * Math.asin(Math.sqrt(Math.sin(dLat / 2) ** 2 + Math.cos(51.4713 * r) * Math.cos(lat * r) * Math.sin(dLon / 2) ** 2));
  };
  const near = stations.reduce((a, s) => (km(s) < km(a) ? s : a));
  const metres = Math.round(km(near) * 100) * 10;
  await page.waitForFunction(() => !document.getElementById('ans-station').hidden, null, { timeout: 10000 }).catch(() => {});
  const line = await page.locator('#ans-station').evaluate((p) => ({ hidden: p.hidden, text: p.textContent }));
  ok(
    !line.hidden && line.text === `Nearest station: ${near.name}, ${metres} m in a straight line.`,
    'the answer names the nearest station, as worked out independently from the station list',
    `${line.text} | expected ${near.name}, ${metres} m`
  );
  // Beyond 3 km nothing is said, never "no station near": the list holds stations inside the cities only.
  const scope = await page.evaluate(async () => {
    const m = await import('/js/street_report.mjs');
    const one = { x: [{ name: 'A', coords: [0, 0] }] };
    return { near: m.nearestStation(one, 0.01, 0)?.name ?? null, far: m.nearestStation(one, 0.05, 0) };
  });
  ok(scope.near === 'A' && scope.far === null, 'a station 1.1 km away is named; one 5.6 km away is not mentioned at all', JSON.stringify(scope));
  // The unit follows the ROUNDED distance (audit 2026-10-09 M-7): 0.995 km printed "1000 m".
  const dist = await page.evaluate(async () => {
    const { stationDistance } = await import('/js/street_report.mjs');
    return Object.fromEntries([0.65, 0.9949, 0.995, 0.9999, 1.0451, 1.4].map((k) => [k, stationDistance(k)]));
  });
  const wantDist = { 0.65: '650 m', 0.9949: '990 m', 0.995: '1.0 km', 0.9999: '1.0 km', 1.0451: '1.0 km', 1.4: '1.4 km' };
  ok(
    Object.entries(wantDist).every(([k, v]) => dist[k] === v),
    'a station distance never reads "1000 m": the unit follows the rounded figure, km from the raw one',
    JSON.stringify(dist)
  );
}
// Air measured nearby (ROADMAP "The plan for Breathe London", step 3; Bill, 2026-10-19: within 5 km,
// London shows the sensor AND the official monitor). Worked out HERE over the two data files with this
// test's own distance maths, as the station is, so the shared functions cannot pass by agreeing with
// themselves. From Kew the nearest sensor is in reach and the nearest official monitor is not.
const kmBetween = (lat1, lon1, lat2, lon2) => {
  const r = Math.PI / 180, dLat = (lat2 - lat1) * r, dLon = (lon2 - lon1) * r;
  return 2 * 6371.0088 * Math.asin(Math.sqrt(Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(dLon / 2) ** 2));
};
const sensorFile = JSON.parse(await readFile(join(ROOT, 'data', 'breathe-london-sensors.json'), 'utf8'));
const monitorFile = JSON.parse(await readFile(join(ROOT, 'data', 'aurn-sites.json'), 'utf8'));
const nearestTo = (sites, lat, lon) => sites.reduce((a, s) => (kmBetween(lat, lon, s.lat, s.lon) < kmBetween(lat, lon, a.lat, a.lon) ? s : a));
const airBlock = async () => {
  await page.waitForFunction(() => !document.getElementById('ans-air').hidden, null, { timeout: 10000 }).catch(() => {});
  return page.locator('#ans-air').evaluate((d) => ({ hidden: d.hidden, text: d.textContent, links: [...d.querySelectorAll('a')].map((a) => [a.textContent, a.getAttribute('href')]) }));
};
{
  const sensor = nearestTo(sensorFile.sites, 51.4713, -0.2894);
  const monitor = nearestTo(monitorFile.sites, 51.4713, -0.2894);
  const sensorKm = kmBetween(51.4713, -0.2894, sensor.lat, sensor.lon);
  const air = await airBlock();
  ok(
    !air.hidden && sensorKm <= 5 && air.text.startsWith(`Nearest Breathe London sensor: ${sensor.name}, ${sensorKm.toFixed(1)} km away (${sensor.classification.toLowerCase()}`),
    'Kew names its nearest Breathe London sensor, as worked out independently from the sensor file',
    `${air.text.slice(0, 160)} | expected ${sensor.name}, ${sensorKm.toFixed(1)} km`
  );
  ok(
    kmBetween(51.4713, -0.2894, monitor.lat, monitor.lon) > 5 && !air.text.includes('Nearest official monitor'),
    'the nearest official monitor is over 5 km from Kew, so it is not mentioned at all (never "none nearby")',
    `${monitor.name} ${kmBetween(51.4713, -0.2894, monitor.lat, monitor.lon).toFixed(1)} km`
  );
  ok(/can read higher than DEFRA's background figure/.test(air.text) && /at least 75% of the hours/.test(air.text), 'a roadside sensor carries why it can read above the background, and the capture floor is stated', air.text.slice(-320));
  ok(
    air.links.length === 1 && air.links[0][0] === sensorFile.attribution && air.links[0][1] === sensorFile.attributionLink,
    "the reading carries Breathe London's credit word for word, linked to breathelondon.org",
    JSON.stringify(air.links)
  );
  // Scope and staleness on the shared functions, on made-up rows: 0.01 degrees is 1.1 km, 0.05 is 5.6 km.
  const edge = await page.evaluate(async () => {
    const m = await import('/js/street_report.mjs');
    const file = { window: { to: '2026-09-30' }, attribution: 'a', attributionLink: 'b', sites: [{ name: 'A', lat: 0.01, lon: 0, no2: { mean: 20 }, pm25: null, classification: 'Kerbside' }] };
    const far = { ...file, sites: [{ ...file.sites[0], lat: 0.05 }] };
    const on = (day) => new Date(`${day}T12:00:00Z`);
    return {
      near: m.nearestSensor(file, 0, 0, on('2026-10-19'))?.name ?? null,
      far: m.nearestSensor(far, 0, 0, on('2026-10-19')),
      day45: m.nearestSensor(file, 0, 0, on('2026-11-14'))?.name ?? null,
      day46: m.nearestSensor(file, 0, 0, on('2026-11-15')),
    };
  });
  ok(
    edge.near === 'A' && edge.far === null && edge.day45 === 'A' && edge.day46 === null,
    'a sensor 1.1 km away is named and one 5.6 km away is not; a file 45 days past its window still shows, at 46 it is hidden, never shown as current',
    JSON.stringify(edge)
  );
}
ok(await page.locator('.covers').isHidden(), 'the coverage strip steps aside once an answer shows, as "Try" does');
// HAVE YOUR SAY and SPOTTED SOMETHING WRONG? (Bill, 2026-10-19). Kew's nearest airport is Heathrow, whose
// pages were verified: its two links and the CAA's portal, exactly as js/street_report.mjs holds them, so a
// link edited in one place and not the other reds here. The correction goes to support@ with the postcode.
{
  const { HAVE_YOUR_SAY, AIRSPACE_CHANGE } = await import(pathToFileURL(join(ROOT, 'js', 'street_report.mjs')).href);
  const want = [...HAVE_YOUR_SAY.LHR, AIRSPACE_CHANGE].map((l) => [l.text, l.href]);
  const lines = await page.evaluate(() => {
    const read = (id) => {
      const el = document.getElementById(id);
      return el && { hidden: el.hidden, text: el.textContent, links: [...el.querySelectorAll('a')].map((a) => [a.textContent, a.getAttribute('href')]) };
    };
    return { say: read('ans-say'), wrong: read('ans-wrong') };
  });
  ok(
    lines.say && !lines.say.hidden && JSON.stringify(lines.say.links) === JSON.stringify(want) && /^Have your say: /.test(lines.say.text),
    "Kew's answer says where to have your say: Heathrow's verified pages and the CAA's airspace change portal",
    JSON.stringify(lines.say)
  );
  ok(
    lines.wrong && !lines.wrong.hidden && lines.wrong.links.length === 1 && lines.wrong.links[0][1] === `mailto:support@skyscore.co.uk?subject=${encodeURIComponent('Correction: TW9 3PZ')}`,
    'the answer offers a way to report a figure that looks wrong, addressed with the postcode',
    JSON.stringify(lines.wrong)
  );
}
const area = await page.locator('#ans-area').textContent();
const richmond = csvRow('Richmond upon Thames');
ok(area.includes('Richmond upon Thames') && area.includes(`Sky Score ${richmond.score}`) && area.includes(`${richmond.flood_medium_or_high_pct}% of postcodes at medium or high flood risk`), 'the council-area line carries the CSV score and flood share', area);
ok((await page.locator('#map .pin').count()) === 1, 'a pin is drawn at the postcode');
ok((await page.locator('#ans-link').getAttribute('href')) === '/map/?city=london&postcode=TW9%203PZ', 'the hand-off link carries city and postcode to the full map at /map/');
ok(await page.evaluate(() => location.search) === '?city=london&postcode=TW9+3PZ', 'URL carries ?city=&postcode=');

// 8a. THE COUNTER SENDS NO POSTCODE (audit 2026-10-09 I-1). GoatCounter's own script sent `q: location.search`
// with every hit, so this very address (?city=london&postcode=TW9+3PZ) reached GoatCounter. js/count.mjs is
// the page's counter now: what it WOULD send, for a page view and for an event, is read here from the real
// module on a page whose address holds a postcode, a title changed after load, and a referrer with a query.
{
  const sent = await page.evaluate(async () => {
    const m = await import('/js/count.mjs');
    const before = document.title;
    document.title = 'TW9 3PZ - Sky Score';
    const ctx = m.pageContext();
    const view = m.countUrl({}, { ...ctx, referrer: m.withoutQuery('https://skyscore.co.uk/map/?postcode=TW9+3PZ#x') });
    const event = m.countUrl({ path: 'event/front-search', title: 'front-search', event: true }, ctx);
    document.title = before;
    return { view, event, wired: typeof window.goatcounter?.count === 'function' };
  });
  const leaks = (u) => /TW9|postcode|city%3D|[?&]q=/i.test(u);
  const params = (u) => Object.fromEntries(new URL(u).searchParams);
  const v = params(sent.view);
  ok(
    sent.wired && !leaks(sent.view) && !leaks(sent.event) && v.p === '/' && v.r === 'https://skyscore.co.uk/map/' && !/TW9/.test(v.t),
    'the counter sends the path, the served title and a bare referrer: no postcode, no query (audit I-1)',
    JSON.stringify({ view: sent.view, event: sent.event })
  );
  ok(params(sent.event).e === 'true' && params(sent.event).p === 'event/front-search', 'an event is sent as an event, by name', sent.event);
  // OUTREACH LINKS STILL FILE UNDER THEIR CAMPAIGN (OUTREACH_DRAFTS.md "UTM convention"). The first version
  // of the counter sent no `q`, so utm_source=outreach-<org> never reached GoatCounter's Referrers tab. Only
  // the three tags pass: `ref` is the free report's reference and GoatCounter would read it as a source.
  const tagged = await page.evaluate(async () => {
    const m = await import('/js/count.mjs');
    const campaign = m.campaignQuery('?city=london&postcode=TW9+3PZ&ref=ab12cd34&made=2026-10-11&utm_source=outreach-landmark&utm_medium=email&utm_campaign=2026-10');
    return { campaign, view: m.countUrl({}, { ...m.pageContext(), campaign }), none: m.campaignQuery('?city=london&postcode=TW9+3PZ') };
  });
  ok(
    tagged.campaign === '?utm_source=outreach-landmark&utm_medium=email&utm_campaign=2026-10' &&
      new URL(tagged.view).searchParams.get('q') === tagged.campaign && !/TW9|postcode|ab12cd34|made/.test(tagged.view) && tagged.none === '',
    'a page view carries the outreach campaign tags and nothing else from the address',
    JSON.stringify(tagged)
  );
}
await page.locator('#ans-open-area').click();
await page.waitForSelector('#borough.is-open');
ok((await page.locator('#borough h2').textContent()) === 'Richmond upon Thames' && (await answerOpen().count()) === 0, '"Its figures" opens the council-area card and closes the answer');
ok((await page.locator('#map .pin').count()) === 0, 'the pin goes when the answer it marks is closed');

// 9. An ESTIMATED postcode: the row the mockup never rendered (it read aircraftQuiet; the API sends aircraftQuietEstimated).
// It sits among measurements, where a longer bar is worse, so it is printed as aircraft NOISE (10 minus the
// quiet score, as the extension does) and the bar must agree with the number beside it.
await page.fill('#pc', 'NW1 7PJ');
await page.press('#pc', 'Enter');
await page.waitForSelector('#answer.is-open', { timeout: 10000 });
const est = await page.locator('#ans-rows .row').first().textContent();
ok(/Aircraft noise/.test(est) && /1\.0 \/ 10/.test(est) && /estimate/.test(est), 'an estimated postcode renders the aircraft-noise estimate, labelled as one', est);
const estBar = await page.locator('#ans-rows .row').first().locator('.bar i').evaluate((i) => parseFloat(i.style.width));
ok(Math.abs(estBar - 10) < 0.01, 'the estimate\'s bar runs the same way as its number', `1.0 / 10 drawn at ${estBar}%`);
ok((await cardOpen().count()) === 0, 'a new search closes the card');
ok((await page.locator('#map .pin').count()) === 1, 'the estimated postcode is pinned');

// 10. A postcode outside every city: no pin (the previous search's included), no false quiet verdict, the
// status says so, and the city on screen does not change. Searched straight after a pinned postcode with no
// city switch between: a redraw would clear the old pin and hide whether the search did.
await page.fill('#pc', 'EX1 1HS');
await page.press('#pc', 'Enter');
await page.waitForFunction(() => document.querySelector('#ans-title')?.textContent === 'EX1 1HS', null, { timeout: 10000 });
const outside = await page.locator('#ans-rows .row').first().textContent();
ok(/not covered/.test(outside) && !/10\.0/.test(outside), 'outside coverage: aircraft row says not covered, never a 10/10', outside);
ok((await page.locator('#map .pin').count()) === 0, 'outside coverage: no pin on whichever city is on screen, nor the last search\'s');
ok(/outside the cities on the map/.test(await page.locator('#status').textContent()), 'outside coverage: the status says so');
ok((await page.locator('#ans-area').textContent()) === '' && (await page.locator('#ans-routes').textContent()) === '', 'outside coverage: no council-area or runway line is invented');
ok((await boroCount()) === 33, 'the map stayed on the city that was on screen');
ok(!(await page.locator('#ans-link').isVisible()), 'outside coverage: no "see the full picture on the map" link to a map it is not on (audit M-18)');
{
  // The vote names the council area postcodes.io returned, never the postcode (2026-10-13).
  const want = (await page.locator('#ans-want').isVisible()) ? await page.locator('#ans-want').textContent() : '';
  ok(/Want Exeter on the map\? Count my vote/.test(want) && !/EX1/i.test(want), 'outside coverage: a vote for the council area is offered, by name, without the postcode', want);
}
await page.locator('#chips button[data-city="manchester"]').click();
await page.waitForFunction(() => document.querySelectorAll('#map .boro').length === 10);

// 11. A postcode in another city switches the map there.
await page.fill('#pc', 'M22 5RX');
await page.press('#pc', 'Enter');
await page.waitForSelector('#answer.is-open', { timeout: 10000 });
await page.locator('#chips button[data-city="london"]').click();
await page.waitForFunction(() => document.querySelectorAll('#map .boro').length === 33);
await page.fill('#pc', 'M22 5RX');
await page.press('#pc', 'Enter');
await page.waitForFunction(() => document.querySelectorAll('#map .boro').length === 10 && document.querySelector('#answer.is-open'), null, { timeout: 10000 });
ok(/published only as charts and are not drawn here/.test(await page.locator('#ans-routes').textContent()), 'Manchester\'s undrawn departures are said, not left silent (audit M-7)', await page.locator('#ans-routes').textContent());
ok(/Nearest airport on the map: Manchester/.test(await page.locator('#ans-routes').textContent()), 'a Manchester postcode switches the map and names Manchester airport');
// Outside London no Breathe London line (the network is London's), and the official monitor within 5 km
// is named with DEFRA's credit; worked out independently, as for Kew.
{
  const monitor = nearestTo(monitorFile.sites, 53.3677, -2.2644);
  const km = kmBetween(53.3677, -2.2644, monitor.lat, monitor.lon);
  const air = await airBlock();
  ok(
    !air.hidden && !/Breathe London/.test(air.text) && km <= 5 &&
      air.text.startsWith(`Nearest official monitor: ${monitor.name}, ${km.toFixed(1)} km away (${monitor.type.toLowerCase()}): `) &&
      air.text.includes(` in ${monitorFile.year}.`),
    'a Manchester postcode names its nearest official monitor, and no Breathe London sensor',
    `${air.text.slice(0, 200)} | expected ${monitor.name}, ${km.toFixed(1)} km`
  );
  ok(air.links.length === 1 && air.links[0][0] === monitorFile.attribution && air.links[0][1] === monitorFile.licence, "the monitor's reading carries UK-AIR's credit word for word, linked to the OGL", JSON.stringify(air.links));
  // Manchester's airport pages have not been verified: no "have your say" line at all, never a guessed link;
  // the correction route is for every covered postcode.
  const say = await page.evaluate(() => ({ say: document.getElementById('ans-say')?.hidden, wrong: document.getElementById('ans-wrong')?.hidden }));
  ok(say.say === true && say.wrong === false, 'a Manchester postcode gets no unverified "have your say" link, but can still report a figure', JSON.stringify(say));
}

// 11a. A SLOWER EARLIER SEARCH MUST NOT OVERWRITE A LATER ONE (audit 2026-10-09 I-3). TW9 3PZ's lookup is
// held up; NW1 7PJ is searched while it waits, and answers first. Both are London, so the late TW9 lands on
// the city already on screen and goes straight to draw() and render(), which is what overwrote the answer.
{
  const slow = /api\.postcodes\.io\/postcodes\/TW93PZ/;
  await page.route(slow, async (route) => { await new Promise((r) => setTimeout(r, 1500)); return stubOffsite(route); });
  await page.fill('#pc', 'TW9 3PZ');
  await page.press('#pc', 'Enter');
  await page.waitForTimeout(300);
  await page.fill('#pc', 'NW1 7PJ');
  await page.press('#pc', 'Enter');
  await page.waitForFunction(() => document.querySelector('#ans-title')?.textContent === 'NW1 7PJ', null, { timeout: 10000 });
  await page.waitForTimeout(2000); // past the held-up TW9 3PZ answer
  const race = await page.evaluate(() => ({
    title: document.querySelector('#ans-title')?.textContent,
    where: document.querySelector('#ans-where')?.textContent,
    q: location.search,
    status: document.querySelector('#status')?.textContent,
    pins: document.querySelectorAll('#map .pin').length,
  }));
  ok(
    race.title === 'NW1 7PJ' && race.where === 'Camden' && race.q === '?city=london&postcode=NW1+7PJ' && race.status === 'Showing the figures for NW1 7PJ.' && race.pins === 1,
    'a slower earlier search does not overwrite the answer to a later one (audit I-3)',
    JSON.stringify(race)
  );
  await page.unroute(slow);
}

// 11b. A RUNWAY WITH NO GLIDE PATH ON RECORD IS A GAP, NOT "NO APPROACH" (audit 2026-10-09 I-5). The full map
// told Howard Beach, beside JFK 13R, "Not under a final approach"; the answer here would have named the
// nearest PUBLISHED approach instead. The constructed ZZ9 9GAP sits on Gatwick 26L's extended centreline.
await page.fill('#pc', 'ZZ9 9GAP');
await page.press('#pc', 'Enter');
await page.waitForFunction(() => document.querySelector('#ans-title')?.textContent === 'ZZ9 9GAP', null, { timeout: 10000 });
{
  const gapText = await page.locator('#ans-routes').textContent();
  ok(
    /In line with Gatwick runway 26L, on its extended centreline: the record gives no glide path for it, so no height is given here\./.test(gapText) && !/Nearest published approach/.test(gapText),
    'a home in line with a runway the record holds no glide path for is told so, not pointed at another approach (audit I-5)',
    gapText
  );
}

// 12. Place names: a borough opens its card (switching city), a Bay Area city opens the Bay Area, a city name switches.
await page.fill('#pc', 'Trafford');
await page.press('#pc', 'Enter');
await page.waitForSelector('#borough.is-open', { timeout: 10000 });
ok((await page.locator('#borough h2').textContent()) === 'Trafford' && (await boroCount()) === 10, 'a borough name opens its card');
await page.fill('#pc', 'camden');
await page.press('#pc', 'Enter');
await page.waitForFunction(() => document.querySelector('#borough h2')?.textContent === 'Camden' && document.querySelectorAll('#map .boro').length === 33, null, { timeout: 10000 });
ok(true, 'a borough name in another city switches the map and opens its card');
await page.fill('#pc', 'Palo Alto');
await page.press('#pc', 'Enter');
await page.waitForFunction(() => document.querySelector('#borough h2')?.textContent === 'Palo Alto', null, { timeout: 15000 });
const fact = (label) => page.locator('#borough .facts div', { has: page.locator('dt', { hasText: label }) }).locator('dd').textContent();
const paloField = await fact('Nearest airfield');
ok(/^Palo Alto \(KPAO\), [\d.]+ km to the/.test(paloField), 'Palo Alto card names its own airfield as the nearest (audit I-2: it named SJC)', paloField);
ok(/^SJC 12R, [\d.]+ km to the/.test(await fact('Nearest of SFO, OAK and SJC')), 'and SJC 12R as the nearest of the three airports whose routes are drawn', await fact('Nearest of SFO, OAK and SJC'));
// The Bay Area's lines are the GENERATED routes file's (2026-10-07), the same records the live map
// draws: so the map draws one path per record of each kind, arrivals included, and nothing from the
// raw FAA record (which drew finals as <line> elements and whole departures, and no arrivals).
{
  const file = JSON.parse(await readFile(join(ROOT, 'data', 'us-bayarea-routes.json'), 'utf8'));
  const want = { final: 0, departure: 0, arrival: 0 };
  for (const r of file.routes) want[r.kind]++;
  const got = await page.evaluate(() => ({
    final: document.querySelectorAll('#map .lines path.final').length,
    departure: document.querySelectorAll('#map .lines path.departure').length,
    arrival: document.querySelectorAll('#map .lines path.arrival').length,
    rawFinals: document.querySelectorAll('#map .lines line.final').length,
  }));
  ok(
    want.arrival > 0 && got.final === want.final && got.departure === want.departure && got.arrival === want.arrival && got.rawFinals === 0,
    'the Bay Area draws every route in data/us-bayarea-routes.json, arrivals included, and none from the raw FAA record',
    JSON.stringify({ want, got })
  );
}
const BTS = ['#FFC107', '#FF8000', '#FF0000', '#FF3399', '#A300CC', '#5200CC', '#0000FF'];
const rampHex = () => page.locator('#ramp b').evaluateAll((bs) => bs.map((b) => '#' + getComputedStyle(b).backgroundColor.match(/\d+/g).slice(0, 3).map((v) => (+v).toString(16).padStart(2, '0')).join('').toUpperCase()));
ok(JSON.stringify(await rampHex()) === JSON.stringify(BTS), "the Bay Area legend ramp is BTS's seven colours, the picture it sits over (audit M-11)", (await rampHex()).join(' '));
await page.fill('#pc', 'Livermore');
await page.press('#pc', 'Enter');
await page.waitForFunction(() => document.querySelector('#borough h2')?.textContent === 'Livermore', null, { timeout: 10000 });
const liv = await fact('Nearest airfield');
ok(/^Livermore Municipal \(KLVK\), [\d.]+ km/.test(liv) && /none within 30 km/.test(await fact('Nearest of SFO, OAK and SJC')), 'Livermore names its own airport, and says the three drawn airports are all further than 30 km', liv);
ok((await page.locator('#chips button[data-city="bayarea"]').getAttribute('aria-pressed')) === 'true', 'the Bay Area chip is pressed');
// A Bay Area ZIP opens its city with the ZIP's own pin, and says how much of the ZIP is in that city.
const zipFact = (label) => page.locator('#borough .facts div', { has: page.locator('dt', { hasText: label }) }).locator('dd').textContent();
const searchZip = async (code, heading) => {
  await page.fill('#pc', code);
  await page.press('#pc', 'Enter');
  await page.waitForFunction((h) => document.querySelector('#borough.is-open h2')?.textContent === h, heading, { timeout: 10000 });
};
await searchZip('94301', 'Palo Alto');
ok(/^In Palo Alto\./.test(await zipFact('ZIP 94301')) && /Nearest airport on the map: (SJC|SFO|OAK)/.test(await zipFact('At its centre')) && /^Palo Alto \(KPAO\)/.test(await zipFact('Nearest airfield')), 'ZIP 94301 opens Palo Alto, says it is in it, and names the nearest runway from its centre', `${await zipFact('ZIP 94301')} | ${await zipFact('At its centre')}`);
// The Census centre point and the drawn outline are two sources: the pin must land on the city it names.
const underPin = await page.locator('#map .pin').evaluate((c) => {
  const r = c.getBoundingClientRect();
  return document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)?.getAttribute('aria-label') || '';
});
ok((await page.locator('#map .pin').count()) === 1 && underPin.startsWith('Palo Alto'), 'the ZIP\'s pin is drawn, inside the city the ZIP is said to be in', underPin);
ok(await page.evaluate(() => location.search) === '?city=bayarea&postcode=94301', 'URL carries ?city=bayarea&postcode=<ZIP>');
await searchZip('95014', 'Cupertino');
ok(/^44% of the ZIP area's land is in Cupertino/.test(await zipFact('ZIP 95014')), 'a ZIP that is mostly hills says how much of it is in the city, not that it is the city', await zipFact('ZIP 95014'));
await searchZip('94305', 'ZIP 94305');
ok(/^Mostly in Stanford: 51%/.test(await zipFact('ZIP 94305')), 'a ZIP in a community the map does not draw gets its own card and names the community', await zipFact('ZIP 94305'));
await searchZip('94074', 'ZIP 94074');
ok(/^In no city\./.test(await zipFact('ZIP 94074')) && /San Mateo County/.test(await page.locator('#borough .where').textContent()), 'a ZIP in no city says so and names its county');
// A ZIP outside the four counties: a sentence, and nothing else moves (no pin, no card, the city stays).
await page.fill('#pc', '90210');
await page.press('#pc', 'Enter');
await page.waitForFunction(() => /not a ZIP in the four Bay Area counties/.test(document.querySelector('#status')?.textContent || ''), null, { timeout: 10000 });
ok((await page.locator('#map .pin').count()) === 0 && (await cardOpen().count()) === 0 && (await page.locator('#chips button[data-city="bayarea"]').getAttribute('aria-pressed')) === 'true', 'a ZIP outside the four counties gets a sentence: no pin, no card, the map stays put');
await page.fill('#pc', 'Cardiff');
await page.press('#pc', 'Enter');
await page.waitForFunction(() => document.querySelector('#borough h2')?.textContent === 'Cardiff', null, { timeout: 10000 });
ok(/Not on the map: figures only/.test(await page.locator('#borough .where').textContent()), 'an API-only council area shows its figures and says it is not on the map');
// The air-quality ratio is the WORSE of NO2 and fine particles, so the card must not print it as NO2's.
// Cardiff holds the ratio and neither concentration; City of Bristol holds both.
const airFact = () => page.locator('#borough .facts div', { has: page.locator('dt', { hasText: 'Air quality' }) }).locator('dd').textContent();
const cardiff = csvRow('Cardiff');
const cardiffAir = await airFact();
ok(cardiffAir.includes(`${cardiff.air_quality_who_ratio}×`) && !/\(\s*(µg|\))/.test(cardiffAir) && !/NO₂ at/.test(cardiffAir), 'a ratio with no concentrations prints no empty brackets', cardiffAir);
await page.fill('#pc', 'City of Bristol');
await page.press('#pc', 'Enter');
await page.waitForFunction(() => document.querySelector('#borough h2')?.textContent === 'City of Bristol', null, { timeout: 10000 });
const bristol = csvRow('City of Bristol');
const bristolAir = await airFact();
ok(bristolAir.includes(`${bristol.air_quality_who_ratio}×`) && bristolAir.includes(bristol.no2_ugm3) && bristolAir.includes(bristol.pm25_ugm3) && !/NO₂ at/.test(bristolAir), 'the air-quality fact names both pollutants and claims the ratio for neither', bristolAir);
await page.fill('#pc', 'West Midlands');
await page.press('#pc', 'Enter');
await page.waitForFunction(() => document.querySelectorAll('#map .boro').length === 7, null, { timeout: 10000 });
ok(true, 'a city name switches the map');

// 12b. NEW YORK ON THE FRONT PAGE (Bill, 2026-10-06: "show on the main screen instead of going to the
// full map"). A chip, not a link out; its five boroughs, the FAA's routes for its four airports and the
// US DOT's picture; and a card that is the score engine's row (scripts/build_nyc_front.py --check holds
// the file to the engine), in dollars, saying its figures are curated and not comparable with the UK's.
{
  const nycDoc = JSON.parse(await readFile(join(ROOT, 'data', 'us-nyc.json'), 'utf8'));
  const nycChip = page.locator('#chips button[data-city="nyc"]');
  ok((await nycChip.count()) === 1 && (await page.locator('#chips a[href*="city=nyc"]').count()) === 0, 'New York is a city chip, not a link out to the full map');
  await nycChip.click();
  await page.waitForFunction(
    () => document.querySelector('#chips button[data-city="nyc"]')?.getAttribute('aria-pressed') === 'true' && document.querySelectorAll('#map .boro').length === 5,
    null,
    { timeout: 15000 }
  );
  const nycMap = await page.evaluate(() => ({
    finals: document.querySelectorAll('#map .lines .final').length,
    // The label's own text node: its <title> child carries the airport's name as well.
    airports: [...document.querySelectorAll('#map text.ap')].map((t) => t.childNodes[0].nodeValue.trim()).sort(),
    picture: document.getElementById('noise-image')?.getAttribute('href'),
  }));
  ok(
    nycMap.finals > 0 && JSON.stringify(nycMap.airports) === JSON.stringify(['EWR', 'JFK', 'LGA', 'TEB']) && nycMap.picture === `/data/${nycDoc.noise.file}`,
    "New York draws its five boroughs, the FAA's final approaches for JFK, LaGuardia, Newark and Teterboro, and the US DOT's noise picture",
    JSON.stringify(nycMap)
  );
  // New York's lines are its GENERATED routes file's too (2026-10-07), the Bay Area's derivation run
  // for its four airports. Reached here straight after the Bay Area, so a New York that kept the Bay
  // Area's file (state.usRoutes is shared) draws the wrong counts and fails.
  {
    const file = JSON.parse(await readFile(join(ROOT, 'data', 'us-nyc-routes.json'), 'utf8'));
    const want = { final: 0, departure: 0, arrival: 0 };
    for (const r of file.routes) want[r.kind]++;
    const got = await page.evaluate(() => ({
      final: document.querySelectorAll('#map .lines path.final').length,
      departure: document.querySelectorAll('#map .lines path.departure').length,
      arrival: document.querySelectorAll('#map .lines path.arrival').length,
      rawFinals: document.querySelectorAll('#map .lines line.final').length,
    }));
    ok(
      want.arrival > 0 && got.final === want.final && got.departure === want.departure && got.arrival === want.arrival && got.rawFinals === 0,
      'New York draws every route in data/us-nyc-routes.json, arrivals included, and none from the raw FAA record',
      JSON.stringify({ want, got })
    );
  }
  ok(JSON.stringify(await rampHex()) === JSON.stringify(BTS), "New York's legend ramp is the US DOT's seven colours, the picture it sits over", (await rampHex()).join(' '));
  await page.fill('#pc', 'Brooklyn');
  await page.press('#pc', 'Enter');
  await page.waitForFunction(() => document.querySelector('#borough h2')?.textContent === 'Brooklyn', null, { timeout: 10000 });
  const bk = nycDoc.rows.find((r) => r.borough === 'Brooklyn');
  const card = await page.locator('#borough').evaluate((c) => ({
    where: c.querySelector('.where')?.textContent || '',
    score: c.querySelector('.score strong')?.textContent,
    text: c.textContent,
    scorecard: c.querySelector('a[href^="/area/"]')?.getAttribute('href'),
    prices: [...c.querySelectorAll('.facts dt')].filter((d) => d.textContent === 'Average price').length,
  }));
  ok(
    card.score === Number(bk.score).toFixed(1) &&
      /^Borough of New York City/.test(card.where) &&
      card.text.includes(`$${Number(bk.avg_price_usd).toLocaleString('en-US')}`) &&
      !/£/.test(card.text) &&
      card.prices === 1 &&
      /not comparable/.test(card.text) &&
      card.scorecard === '/area/nyc/brooklyn/',
    "Brooklyn's card is the engine's row: its score, its price in dollars (one price line, no pounds), the curated-and-not-comparable note, and its scorecard",
    JSON.stringify({ ...card, text: card.text.slice(0, 160) })
  );
  ok((await page.evaluate(() => location.search)) === '?city=nyc&borough=Brooklyn', 'the URL names New York and Brooklyn', await page.evaluate(() => location.search));
  // A UK card is unchanged by the dollar line: one price, in pounds.
  await page.fill('#pc', 'Camden');
  await page.press('#pc', 'Enter');
  await page.waitForFunction(() => document.querySelector('#borough h2')?.textContent === 'Camden', null, { timeout: 10000 });
  const camden = await page.locator('#borough .facts').evaluate((f) => ({
    prices: [...f.querySelectorAll('dt')].filter((d) => d.textContent === 'Average price').length,
    pounds: /£/.test(f.textContent),
    dollars: /\$/.test(f.textContent),
  }));
  ok(camden.prices === 1 && camden.pounds && !camden.dollars, 'a UK card still shows one price, in pounds', JSON.stringify(camden));
  // And a link straight to New York opens it.
  await page.goto(`${BASE}?city=nyc&borough=Staten%20Island`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelector('#borough h2')?.textContent === 'Staten Island', null, { timeout: 20000 });
  ok((await nycChip.getAttribute('aria-pressed')) === 'true', '?city=nyc&borough= boots New York with the card open');
}

// 13. Deep links boot into the state the URL names.
await page.goto(`${BASE}?city=manchester&borough=Trafford`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('#borough.is-open', { timeout: 20000 });
ok((await page.locator('#borough h2').textContent()) === 'Trafford' && (await boroCount()) === 10, '?city=&borough= boots with the card open');
await page.goto(`${BASE}?city=manchester&borough=Camden`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('#borough.is-open', { timeout: 20000 });
const mismatchWhere = await page.locator('#borough .where').textContent();
ok((await boroCount()) === 33 && !/Not on the map/.test(mismatchWhere), 'a council area in the URL opens on its own city, whatever ?city= says', `${await boroCount()} areas drawn; "${mismatchWhere}"`);
await page.goto(`${BASE}?postcode=TW9+3PZ`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('#answer.is-open', { timeout: 20000 });
ok((await page.locator('#ans-title').textContent()) === 'TW9 3PZ' && (await page.inputValue('#pc')) === 'TW9 3PZ', '?postcode= runs the search on load');
// A link that names a city came for that city's map: it opens on the tool, chips showing,
// not the question over a faded map. A city it cannot open is not a city, so it does not.
await page.goto(`${BASE}?city=teesside`, { waitUntil: 'domcontentloaded' });
await waitMap();
ok(!(await page.evaluate(() => document.querySelector('.hero').classList.contains('is-intro'))) && (await page.evaluate(() => getComputedStyle(document.querySelector('.chips')).visibility)) === 'visible', '?city=teesside opens on the tool, not the opening question');
await page.goto(`${BASE}?city=constructor`, { waitUntil: 'domcontentloaded' });
await waitMap();
ok((await boroCount()) === 33 && !/could not load/.test(await page.locator('#status').textContent()), '?city=constructor opens London, not a map that cannot load (audit M-6)');
await page.goto(`${BASE}?city=bayarea&postcode=94612`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => document.querySelector('#borough.is-open h2')?.textContent === 'Oakland', null, { timeout: 20000 });
ok((await page.locator('#map .pin').count()) === 1 && (await page.locator('#chips button[data-city="bayarea"]').getAttribute('aria-pressed')) === 'true', 'a ZIP in the URL boots the Bay Area with its city open and its pin drawn');

// 14. A phone: the card scrolls into view on a tap and the controls sit inside the viewport.
await page.setViewportSize({ width: 390, height: 844 });
// "not held here" is a note, not a value: on a phone it ran 17px past its row
// (audit M-19). Exeter's stub has no road reading, so its answer carries it.
{
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await waitMap();
  await page.fill('#pc', 'EX1 1HS');
  await page.press('#pc', 'Enter');
  await page.waitForSelector('#answer.is-open', { timeout: 15000 });
  const spill = await page.evaluate(() => {
    const row = [...document.querySelectorAll('#ans-rows .row')].find((r) => /not held here/.test(r.textContent));
    if (!row) return null;
    const range = document.createRange();
    range.selectNodeContents(row.querySelector('.val'));
    return Math.round(range.getBoundingClientRect().right - row.getBoundingClientRect().right);
  });
  ok(spill !== null && spill <= 0, 'on a phone, "not held here" stays inside its row (audit M-19)', spill === null ? 'no such row' : `${spill}px past the row`);
}
await page.goto(BASE, { waitUntil: 'domcontentloaded' });
await waitMap();
// Stacked, the map sits BELOW the question, uncovered, so it is live from the start (2026-10-07).
ok((await page.evaluate(() => document.querySelector('.mapwrap').inert)) === false, 'on a phone the map is live from the start: it sits below the question, not under it');
await page.locator('#map .boro[aria-label^="Camden"]').click({ force: true });
await page.waitForSelector('#borough.is-open');
await page.waitForTimeout(700);
const cardTop = await page.locator('#borough').evaluate((e) => e.getBoundingClientRect().top);
ok(cardTop >= -1 && cardTop < 844, 'on a phone the card is brought into view', `top ${Math.round(cardTop)}px`);
// A real TAP, in a touch context: the tap focuses the area, its focus handler
// shows the tooltip, and nothing on a phone moves a pointer off it, so it stayed
// on the map until the next tap (audit M-15). An emulated mouse click cannot
// show this: the card's scroll fires a mouse-leave, and that check passed on the
// defect.
{
  const touch = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  await touch.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  const tp = await touch.newPage();
  await tp.goto(BASE, { waitUntil: 'domcontentloaded' });
  await tp.waitForSelector('#map .boro', { timeout: 20000 });
  await tp.locator('#map .boro[aria-label^="Camden"]').tap({ force: true });
  await tp.waitForSelector('#borough.is-open');
  await tp.waitForTimeout(700);
  ok(await tp.locator('#tip').isHidden(), 'on a phone, a tapped council area takes its tooltip off the map (audit M-15)');
  // ...and the route explanations the tooltip held come with the card (the other half of M-15).
  const tapped = await tp.evaluate(readRouteRow);
  ok(Boolean(tapped) && tapped.items.length > 0 && tapped.titled, 'on a phone, the tapped area\'s card lists the routes across it, each named and explained', JSON.stringify(tapped)?.slice(0, 300));

  // A zoomed map moves without a drag (audit M-16, WCAG 2.5.7): a finger scrolls the
  // page, so after three zoom-ins 13 of London's 33 areas were off the box with no
  // way to reach them. Tabbing to one brings it in; tapping one centres it.
  for (let i = 0; i < 3; i++) { await tp.locator('#zoom-in').tap(); await tp.waitForTimeout(350); }
  const where = (name) => tp.evaluate((n) => {
    const box = document.getElementById('map').getBoundingClientRect();
    const r = document.querySelector(`#map .boro[aria-label^="${n}"]`).getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    return { inside: x >= box.left && x <= box.right && y >= box.top && y <= box.bottom, off: Math.hypot(x - (box.left + box.width / 2), y - (box.top + box.height / 2)) };
  }, name);
  const offBox = await tp.evaluate(() => {
    const box = document.getElementById('map').getBoundingClientRect();
    return [...document.querySelectorAll('#map .boro')].filter((p) => { const r = p.getBoundingClientRect(); const x = r.left + r.width / 2, y = r.top + r.height / 2; return x < box.left || x > box.right || y < box.top || y > box.bottom; }).map((p) => p.getAttribute('aria-label').split(':')[0]);
  });
  ok(offBox.length > 0, `zoomed in three times at 390 wide, areas are off the map box (${offBox.length})`, '');
  if (offBox.length) {
    await tp.locator(`#map .boro[aria-label^="${offBox[0]}"]`).focus();
    await tp.waitForTimeout(600);
    const tabbed = await where(offBox[0]);
    ok(tabbed.inside, `Tab to ${offBox[0]}, off the zoomed map, brings it into the box (audit M-16)`, JSON.stringify(tabbed));
  }
  const edge = await tp.evaluate(() => {
    const box = document.getElementById('map').getBoundingClientRect();
    const cx = box.left + box.width / 2, cy = box.top + box.height / 2;
    const seen = [...document.querySelectorAll('#map .boro')].map((p) => { const r = p.getBoundingClientRect(); return { n: p.getAttribute('aria-label').split(':')[0], x: r.left + r.width / 2, y: r.top + r.height / 2 }; })
      .filter((b) => b.x > box.left + 20 && b.x < box.right - 20 && b.y > box.top + 20 && b.y < box.bottom - 20)
      .map((b) => ({ ...b, d: Math.hypot(b.x - cx, b.y - cy) })).sort((a, b) => b.d - a.d);
    return seen[0] ? { n: seen[0].n, d: seen[0].d } : null;
  });
  if (edge) {
    await tp.locator(`#map .boro[aria-label^="${edge.n}"]`).tap({ force: true });
    await tp.waitForTimeout(800);
    const tapped = await where(edge.n);
    ok(tapped.off < Math.max(30, edge.d / 3), `tapping ${edge.n} at the edge of the zoomed map centres it (audit M-16)`, `${Math.round(edge.d)}px from the middle -> ${Math.round(tapped.off)}px`);
  } else ok(false, 'tapping an area at the edge of the zoomed map centres it (audit M-16)', 'no area inside the box to tap');
  await touch.close();
}
const inside = await page.locator('#toggle-noise, #zoom-in, #zoom-out, #zoom-reset').evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return r.left >= 0 && r.right <= 390; }));
ok(inside.every(Boolean), 'layer and zoom controls are inside a phone viewport');

// London's noise picture is the one box no data file describes; the holder is
// LONDON_AIRCRAFT_BBOX in index.html (audit M-13). Since 2026-10-06 the engine
// takes it, and DEFRA's colours, from js/street_report.mjs instead of typing a
// third copy; tests/test_street_report_mirrors.py holds the module to index.html.
{
  const engine = await readFile(join(ROOT, 'js', 'home-engine.mjs'), 'utf8');
  const fromModule = /import \{[^}]*\bLONDON_RASTER\b[^}]*\} from '\/js\/street_report\.mjs'/.test(engine) && /const LONDON_PNG = \{.*\bbbox: LONDON_RASTER\.bbox \};/.test(engine);
  const box = await page.evaluate(async () => (await import('/js/street_report.mjs')).LONDON_RASTER.bbox);
  const live = await readFile(join(ROOT, 'index.html'), 'utf8');
  const holder = live.match(/const LONDON_AIRCRAFT_BBOX = \{([^}]*)\}/)?.[1] || '';
  const want = ['minLon', 'maxLon', 'minLat', 'maxLat'].map((k) => Number(holder.match(new RegExp(`${k}:\\s*(-?[\\d.]+)`))?.[1]));
  const mine = ['minLon', 'maxLon', 'minLat', 'maxLat'].map((k) => box?.[k]);
  ok(fromModule && want.every(Number.isFinite) && mine.every((v, i) => v === want[i]), 'the front page places London\'s noise picture where the map does, from the one shared copy', `${mine} vs ${want}`);
}

// The search has a visible label, and its placeholder fits the box at 320 wide
// (audit I-6: the placeholder WAS the label, cut to "Postcode, ZIP o").
{
  await page.setViewportSize({ width: 320, height: 640 });
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await waitMap();
  const f = await page.evaluate(() => {
    const input = document.getElementById('pc');
    const label = document.querySelector('label[for="pc"]');
    const lr = label?.getBoundingClientRect();
    const cs = getComputedStyle(input);
    const ctx = document.createElement('canvas').getContext('2d');
    ctx.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
    const room = input.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    return { label: label?.textContent.trim() || '', seen: !!lr && lr.width > 40 && lr.height >= 10, need: Math.ceil(ctx.measureText(input.placeholder).width), room: Math.floor(room) };
  });
  ok(f.seen && /postcode/i.test(f.label), 'the search box has a visible label (audit I-6)', JSON.stringify(f));
  ok(f.need <= f.room, 'its placeholder fits the box at 320 wide', `${f.need}px of text in ${f.room}px`);
}

// 14a. Tablets and landscape phones stack the panel above the map (audit I-4): the
// floating panel lay over the toggles and chips from 761px to about 1180px wide.
// One query decides it in the CSS and the engine, held to one string here.
{
  const engine = await readFile(join(ROOT, 'js', 'home-engine.mjs'), 'utf8');
  const html = await readFile(join(ROOT, 'home', 'index.html'), 'utf8');
  const q = engine.match(/const STACKED = '([^']+)'/)?.[1];
  ok(Boolean(q) && html.includes(`@media ${q} {`), 'the CSS and the engine stack the panel on one query', q || 'no STACKED');
}
for (const vp of [{ width: 1024, height: 768 }, { width: 768, height: 1024 }, { width: 844, height: 390 }]) {
  await page.setViewportSize(vp);
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await waitMap();
  const lay = await page.evaluate(() => {
    // Scrolled into view first: the question is whether anything COVERS the control, and
    // elementFromPoint answers nothing for a point below the fold (a 24px label once
    // moved the toggles 0-28px past it at 844x390, and the check went red on nothing).
    const hit = (id) => { const el = document.getElementById(id); el.scrollIntoView({ block: 'center' }); const r = el.getBoundingClientRect(); const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !!t && (t === el || el.contains(t)); };
    const panel = document.querySelector('.panel').getBoundingClientRect();
    const map = document.querySelector('.mapwrap').getBoundingClientRect();
    return { toggles: hit('toggle-lines') && hit('toggle-noise'), overlap: Math.max(0, Math.min(panel.bottom, map.bottom) - Math.max(panel.top, map.top)) > 1 && Math.max(0, Math.min(panel.right, map.right) - Math.max(panel.left, map.left)) > 1 };
  });
  ok(lay.toggles && !lay.overlap, `${vp.width}x${vp.height}: the panel stacks clear of the map and the layer toggles answer`, JSON.stringify(lay));
}

// 15. The other pages at their live addresses: the reports page and its PDFs, the full map at /map/,
// and the trial's old address, which forwards.
await page.goto(`${BASE}reports/`, { waitUntil: 'domcontentloaded' });
const pdfs = await page.locator('a[href$=".pdf"]').evaluateAll((as) => as.map((a) => new URL(a.href).pathname));
for (const p of pdfs) if ((await page.request.get(`http://127.0.0.1:${PORT}${p}`)).status() === 200) fetched.add(p);
ok(pdfs.length >= 2 && pdfs.every((p) => fetched.has(p) && p.startsWith('/reports/')), 'the reports page links sample PDFs that exist, under /reports/', pdfs.join(' '));
{
  const map = await page.request.get(`${BASE}map/`);
  const mapHtml = await map.text();
  ok(map.status() === 200 && mapHtml.includes('id="app"') && mapHtml.includes('<link rel="canonical" href="https://skyscore.co.uk/map/" />'), '/map/ serves the full map, which names /map/ as its address');
  ok(mapHtml.includes('<script src="/js/api-base.js"></script>'), 'the map loads the API base by an absolute path (relative, it broke at /map/)');
  const old = await (await page.request.get(`${BASE}preview/`)).text();
  const oldReports = await (await page.request.get(`${BASE}preview/reports/`)).text();
  ok(/http-equiv="refresh" content="0; url=\/"/.test(old) && /http-equiv="refresh" content="0; url=\/reports\/"/.test(oldReports), 'the trial\'s old addresses forward to / and /reports/');
  const front = await (await page.request.get(BASE)).text();
  ok(!/noindex/.test(front) && front.includes('<link rel="canonical" href="https://skyscore.co.uk/" />') && !/class="mock"/.test(front), 'the front page is indexable, names / as its address and carries no preview badge');
}

// 16. EVERY PRICE LIVES ON /pricing (Bill, 2026-10-06: "one pricing page, in the top bar"). The reports
// page states no figure and links there; the front page links there and repeats nothing.
const reportsText = await page.locator('main').textContent();
ok(
  !/£\s?\d/.test(reportsText) &&
    (await page.locator('main a[href="/pricing#reports"]').count()) > 0 &&
    /not a conveyancing search/.test(reportsText) &&
    !/\+ ?VAT/.test(reportsText),
  'the reports page states no price, links to the pricing page, and says a report is not a conveyancing search',
  reportsText.match(/£\s?\d\S*/)?.[0] || ''
);
const footReports = await page.locator('footer a').evaluateAll((as) => as.map((a) => a.getAttribute('href')));
await page.goto(BASE, { waitUntil: 'domcontentloaded' });
await waitMap();
const frontText = await page.locator('body').textContent();
// The front page draws the UK AIP's routes and the FAA's (2026-10-07): it credits NATS, as LICENSING.md
// asks wherever UK routes are shown, and carries the FAA's "as is" disclaimer, as its CIFP terms ask.
{
  const credit = (await page.locator('footer .route-credit').textContent().catch(() => '')) || '';
  ok(/Aeronautical Information Publication \(NATS\)/.test(credit) && /"as is", without warranty/.test(credit) && /Not for navigation/.test(credit),
    `the front page credits the UK AIP (NATS) and carries the FAA's "as is" disclaimer for the routes it draws`, credit);
}
// THE COVERAGE FIGURE IS THE DATA'S (website audit M3, 2026-10-07: New York was missing from it).
// Each number is recounted from the file it describes: the open-data CSV's UK rows, New York's
// front-page rows, the Bay Area's places. A count written once is scheduled staleness.
{
  const csvLines = (await readFile(join(ROOT, 'open-data', 'sky-score-boroughs.csv'), 'utf8')).trim().split(/\r?\n/).slice(1);
  const csvRows = csvLines.length;
  // The regions too (2026-10-13): the card said "across England and Wales", which reads as the
  // whole of both countries; the one coverage sentence (12 Oct) names the city regions instead.
  const csvRegions = new Set(csvLines.map((l) => l.split(',')[0])).size;
  const nycRows = JSON.parse(await readFile(join(ROOT, 'data', 'us-nyc.json'), 'utf8')).rows.length;
  // The 50 INCORPORATED places (43 cities, 7 towns): the file also holds 28 census-designated
  // places, unincorporated, which are outlines on the map and never 'cities'.
  const bayPlaces = JSON.parse(await readFile(join(ROOT, 'data', 'us-bayarea-places.json'), 'utf8')).places.filter((x) => x.kind === 'city' || x.kind === 'town').length;
  const want = `${csvRows}council areas in ${csvRegions} UK city regions, New York's ${nycRows} boroughs and ${bayPlaces} Bay Area cities`;
  const fig = (await page.locator('.cards .fig').first().textContent()).trim();
  ok(fig === want, 'the coverage figure is recounted from the data: UK council areas and city regions, New York boroughs, Bay Area cities', `page "${fig}" vs data "${want}"`);
}
const frontLinks = await page.locator('main a, footer a').evaluateAll((as) => as.map((a) => a.getAttribute('href')));
ok(!/£35/.test(frontText) && frontLinks.includes('/pricing#reports'), 'the front page links to the report prices and does not repeat them');
ok(frontLinks.includes('/reports/street/'), 'the front page links to the free street report');
ok(['/pricing', '/area/', '/map/'].every((h) => frontLinks.includes(h) && footReports.includes(h)), 'pricing, the council areas and the full map are linked from both pages', `${frontLinks.join(' ')} | ${footReports.join(' ')}`);
// Their LIVE addresses: this server routes as the site does, so /pricing is pricing.html.
for (const p of ['/pricing', '/area/', '/map/']) ok((await page.request.get(`http://127.0.0.1:${PORT}${p}`)).status() === 200, `${p} is a page that exists`);

// 16b. /pricing: a ladder per buyer, and a price shown in two places reads one way. /api/ carries its own
// copy of the API ladder; each mirrored price carries one data-price key wherever it appears, read
// without its <small> qualifier, which may differ by page.
const pricesOn = () =>
  page.locator('[data-price]').evaluateAll((els) =>
    els.map((e) => {
      const c = e.cloneNode(true);
      c.querySelector('small')?.remove();
      return [e.dataset.price, c.textContent.replace(/\s+/g, ' ').trim()];
    })
  );
// No card is "the one to pick" (Bill, 2026-10-06): a homeowner who jumps to the report tiers
// saw the firms card outlined. Read from computed style: no card carries a ring or shadow, and
// every card button has one look.
const cardLook = () =>
  page.locator('.tier').evaluateAll((cards) => ({
    cards: cards.length,
    ringed: cards.filter((c) => getComputedStyle(c).boxShadow !== 'none').map((c) => c.querySelector('h3')?.textContent.trim()),
    buttons: [...new Set(cards.flatMap((c) => [...c.querySelectorAll('a.go')].map((a) => `${getComputedStyle(a).backgroundColor}|${a.className}`)))],
  }));
// /api/ states NO prices since the website audit of 2026-10-06 (I2): its own copy of the API
// ladder had already drifted from /pricing ("a support contract" there, "bulk scoring" here).
// It links to the platform ladder instead, so a price creeping back onto /api/ fails here.
await page.goto(`http://127.0.0.1:${PORT}/api/`, { waitUntil: 'domcontentloaded' });
const apiPage = await page.evaluate(() => ({
  pounds: document.querySelector('main')?.textContent.match(/£\s?\d[\d,]*/g) || [],
  cards: document.querySelectorAll('.tier').length,
  link: Boolean(document.querySelector('main a[href="/pricing#platforms"]')),
}));
ok(
  apiPage.pounds.length === 0 && apiPage.cards === 0 && apiPage.link,
  '/api/ states no price and links to the platform prices on /pricing, the one holder',
  JSON.stringify(apiPage)
);
await page.goto(`http://127.0.0.1:${PORT}/pricing`, { waitUntil: 'domcontentloaded' });
const pricingPrices = await pricesOn();
const pricingCards = await cardLook();
ok(
  pricingCards.cards >= 4 && pricingCards.ringed.length === 0 && pricingCards.buttons.length === 1,
  'no pricing card is highlighted on /pricing, and every card button looks the same',
  JSON.stringify(pricingCards)
);
const priceText = {};
const clashes = [];
for (const [key, text] of pricingPrices) {
  if (key in priceText && priceText[key] !== text) clashes.push(`${key}: "${priceText[key]}" vs "${text}"`);
  priceText[key] ??= text;
}
const pricingKeys = pricingPrices.map(([k]) => k);
ok(
  clashes.length === 0 &&
    pricingKeys.filter((k) => k === 'pilot').length === 2 &&
    ['council-area-study', 'council-licence', 'api-free', 'api-professional', 'api-enterprise'].every((k) => pricingKeys.includes(k)),
  'a price shown twice on /pricing reads the same both times (the pilot on the council and platform ladders)',
  clashes.join('; ') || JSON.stringify(pricingPrices)
);
// The report tiers, read card by card so a price moved under the wrong heading fails. The SET of
// headings, never a count: a count in an assertion is scheduled staleness.
const tiers = await page.locator('#reports .tier').evaluateAll((cards) =>
  cards.map((c) => [c.querySelector('h3')?.textContent.trim(), c.querySelector('.price')?.textContent.replace(/\s+/g, ' ').trim()])
);
const tierOf = Object.fromEntries(tiers);
ok(
  tiers.map(([h]) => h).sort().join('|') === ['Firms', "Residents' groups", 'Your own home'].join('|') &&
    tierOf['Your own home'] === 'Free' &&
    tierOf["Residents' groups"] === 'Free' &&
    tierOf.Firms === '£35 a report',
  "the pricing page prices a report: free for your own home and for residents' groups, £35 for firms",
  JSON.stringify(tiers)
);
const homeTier = await page.locator('#reports .tier').first().locator('a').getAttribute('href');
ok(homeTier === '/reports/street/', 'the free tier for your own home leads straight to making the report', homeTier);
const councilCards = await page.locator('#councils .tier h3').allTextContents();
const pricingText = await page.locator('main').textContent();
ok(
  ['Area study', '90-day pilot', 'Annual licence'].every((h) => councilCards.includes(h)) &&
    /not a conveyancing search/.test(pricingText) &&
    !/\+ ?VAT/.test(pricingText),
  'the pricing page gives councils a study, a pilot and a licence, and adds no VAT anywhere',
  councilCards.join(' | ')
);

// 16c. THE TOP BAR (Bill, 2026-10-06: an orange block and a grey box "confusing"). On every page that
// carries it: Pricing is in it; Full map is an OUTLINED button, never a filled block; the page you are
// on is an underline, never a filled box, and only that page is marked. Read from computed style, so a
// rule that stops applying fails here even with the markup unchanged.
// /score-demo/status.html probes the live API on load. This run already aborts every request
// off 127.0.0.1, but the demo-key guard (tests/test_demo_key_spenders.py) asks every gate that
// loads it to answer those calls through the shared stub, and to prove the stub fired.
const statusStub = await stubLiveApi(page);
for (const [path, here] of [
  ['/', null],
  ['/reports/', '/reports/'],
  ['/pricing', '/pricing'],
  ['/api/', '/api/'],
  ['/open-data/', '/open-data/'],
  ['/area/london/camden/', null],
  // The six that had none until 2026-10-07 (website audit M1). Three are dark pages, so the bar
  // takes the page's colours; the rules checked are the same.
  ['/privacy', null],
  ['/terms', null],
  ['/changes', null],
  ['/talks/', null],
  ['/score-demo/api-docs.html', null],
  ['/score-demo/status.html', null],
]) {
  await page.goto(`http://127.0.0.1:${PORT}${path}`, { waitUntil: 'domcontentloaded' });
  await page.mouse.move(0, 0); // no link hovered
  const bar = await page.evaluate(() => {
    const nav = document.querySelector('nav[aria-label="Site"]');
    if (!nav) return null;
    const cs = (el) => getComputedStyle(el);
    const cta = nav.querySelector('a.nav-cta');
    const current = [...nav.querySelectorAll('a[aria-current]')];
    return {
      hrefs: [...nav.querySelectorAll('a')].map((a) => a.getAttribute('href')),
      ctaFill: cta && cs(cta).backgroundColor,
      ctaRing: cta && cs(cta).boxShadow,
      current: current.map((a) => a.getAttribute('href')),
      filled: current.filter((a) => cs(a).backgroundColor !== 'rgba(0, 0, 0, 0)').length,
      underlined: current.every((a) => cs(a).textDecorationLine.includes('underline')),
    };
  });
  ok(
    bar &&
      bar.hrefs.includes('/pricing') &&
      bar.ctaFill === 'rgba(0, 0, 0, 0)' &&
      /inset/.test(bar.ctaRing) &&
      JSON.stringify(bar.current) === JSON.stringify(here ? [here] : []) &&
      bar.filled === 0 &&
      bar.underlined,
    `${path}: the bar lists Pricing, Full map is outlined, and ${here ? 'this page is underlined, not filled' : 'no page is marked'}`,
    JSON.stringify(bar)
  );
  // Hover (Bill, 2026-10-06: "underline the header links instead of highlighting them a colour"):
  // an underline and no fill, on an ordinary link and on Full map alike.
  const hoverLook = async (sel) => {
    const link = page.locator(sel).first();
    await link.hover();
    return link.evaluate((a) => ({ fill: getComputedStyle(a).backgroundColor, line: getComputedStyle(a).textDecorationLine }));
  };
  const hovered = {
    // Not the brand: the generated pages put "Sky Score" INSIDE the site nav (the hand-written
    // ones beside it), and the brand is not a menu item (first run read it as a missed underline).
    plain: await hoverLook('nav[aria-label="Site"] a:not(.nav-cta):not([aria-current]):not(.site-brand)'),
    cta: await hoverLook('nav[aria-label="Site"] a.nav-cta'),
  };
  await page.mouse.move(0, 0);
  ok(
    Object.values(hovered).every((h) => h.fill === 'rgba(0, 0, 0, 0)' && h.line.includes('underline')),
    `${path}: hovering a header link underlines it, with no colour fill`,
    JSON.stringify(hovered)
  );
}
ok(statusStub.count > 0, 'the status page\'s API probes were answered by the stub, never the live API', `${statusStub.count} stubbed: ${statusStub.paths.slice(0, 3).join(', ')}`);
// Back to the front page: section 17's first check ("the Streets button is hidden") would pass
// vacuously on a page that has no such button.
await page.goto(BASE, { waitUntil: 'domcontentloaded' });
await waitMap();

// 17. The OS street-map trial. No key is in the source: nothing is asked of api.os.uk until a device is given
// one, the key leaves the address bar, and each tile sits where web-mercator says it should - checked against
// the pin of a known postcode, because a tile grid that is off by one still looks like a map.
ok(osTiles.length === 0, 'nothing was requested from api.os.uk in the whole run without a key', osTiles.slice(0, 2).join(' '));
ok(await page.locator('#toggle-streets').isHidden(), 'the Streets button is hidden without a key');
await page.setViewportSize({ width: 1366, height: 820 });
// A key in the QUERY is dropped unread: a query reaches the server and the service
// worker's page cache, a fragment reaches neither (audit M-1).
await page.goto(`${BASE}?oskey=PLANTED12345`, { waitUntil: 'domcontentloaded' });
await waitMap();
ok((await page.evaluate(() => localStorage.getItem('osMapsKey'))) === null && !(await page.evaluate(() => location.href)).includes('oskey'), 'a ?oskey= in the query is dropped, not stored (audit M-1)');
// Arrive fresh, as someone opening the link does: from /preview/ itself a
// fragment-only change is a same-page jump, and the page never re-reads it.
await page.goto('about:blank');
await page.goto(`${BASE}#oskey=TESTKEY1234`, { waitUntil: 'domcontentloaded' });
await waitMap();
ok(!(await page.evaluate(() => location.href)).includes('oskey'), 'the key leaves the address bar');
await page.fill('#pc', 'TW9 3PZ');
await page.press('#pc', 'Enter');
await page.waitForSelector('#map .pin', { timeout: 10000 });
const tiles = await page.locator('#map .streets image').evaluateAll((els) => els.map((e) => ({ href: e.getAttribute('href'), x: +e.getAttribute('x'), y: +e.getAttribute('y'), w: +e.getAttribute('width') })));
const parsed = tiles.map((t) => ({ ...t, m: /^https:\/\/api\.os\.uk\/maps\/raster\/v1\/zxy\/Light_3857\/(\d+)\/(\d+)\/(\d+)\.png\?key=TESTKEY1234$/.exec(t.href) }));
ok(tiles.length >= 6 && parsed.every((t) => t.m), 'with a key the map draws OS tiles from the documented address', `${tiles.length} tiles; ${tiles[0]?.href}`);
ok(parsed.every((t) => t.m && +t.m[1] >= 7 && +t.m[1] <= 16), 'every tile is in the free OpenData zoom band (7 to 16)', parsed[0]?.m?.[1]);
ok(await page.locator('#map').evaluate((s) => s.classList.contains('has-streets')) && /Crown copyright/.test(await page.locator('#os-credit').textContent()) && (await page.locator('#os-credit').isVisible()), 'the OS credit shows while the streets do');
if (parsed.length && parsed.every((t) => t.m)) {
  const z = +parsed[0].m[1], n = 2 ** z, { latitude: lat, longitude: lon } = GEO.TW93PZ;
  const fx = ((lon + 180) / 360) * n;
  const rad = (lat * Math.PI) / 180;
  const fy = ((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2) * n;
  const home = parsed.find((t) => +t.m[2] === Math.floor(fx) && +t.m[3] === Math.floor(fy));
  const pin = await page.locator('#map .pin').evaluate((c) => [+c.getAttribute('cx'), +c.getAttribute('cy')]);
  const ts = home ? home.w - 0.5 : 0;
  const want = home ? [home.x + (fx - Math.floor(fx)) * ts, home.y + (fy - Math.floor(fy)) * ts] : [NaN, NaN];
  ok(Boolean(home) && Math.abs(pin[0] - want[0]) < 1 && Math.abs(pin[1] - want[1]) < 1, 'the pin sits where its own tile says the postcode is (the grid is georeferenced)', `pin ${pin.map((v) => v.toFixed(1))}, tile says ${want.map((v) => v.toFixed(1))}`);
}
await page.locator('#toggle-streets').click();
ok((await page.locator('#map .streets image').count()) === 0 && (await page.locator('#os-credit').isHidden()) && (await page.locator('#toggle-streets').getAttribute('aria-pressed')) === 'false', 'the Streets button takes the tiles and the credit away');
await page.locator('#toggle-streets').click();
await page.waitForTimeout(500); // let London's tiles finish asking before counting what the Bay Area asks for
const beforeBay = osTiles.length;
await page.locator('#chips button[data-city="bayarea"]').click();
await page.waitForFunction(() => document.querySelector('#chips button[data-city="bayarea"]')?.getAttribute('aria-pressed') === 'true' && document.querySelectorAll('#map .boro').length > 20, null, { timeout: 15000 });
await page.waitForTimeout(300);
ok((await page.locator('#toggle-streets').isDisabled()) && (await page.locator('#map .streets image').count()) === 0 && osTiles.length === beforeBay, 'the Bay Area asks Ordnance Survey for nothing: it maps Great Britain only', `${osTiles.length - beforeBay} requests`);
await page.goto('about:blank');
await page.goto(`${BASE}#oskey=off`, { waitUntil: 'domcontentloaded' });
await waitMap();
ok((await page.locator('#toggle-streets').isHidden()) && (await page.locator('#map .streets image').count()) === 0, '#oskey=off forgets the key');

// 18. THE FREE STREET REPORT (2026-10-06), made in the browser from js/street_report.mjs, the module the
// sample PDFs are printed from. Same stubs as the front page: measured (TW9), estimated (NW1) and outside (EX1).
const sheetDoc = () => page.frameLocator('#sheet');
const makeReport = async (pc) => {
  await page.goto(`${BASE}reports/street/`, { waitUntil: 'domcontentloaded' });
  await page.fill('#pc', pc);
  await page.press('#pc', 'Enter');
  await page.waitForFunction(() => /ready below|outside the city|not a postcode|does not look|answered|reached/.test(document.getElementById('status').textContent), null, { timeout: 20000 });
  return page.locator('#status').textContent();
};
{
  const said = await makeReport('TW9 3PZ');
  // Read the report only once the page says it is ready: otherwise a failure is a
  // 30-second wait for a heading, with no word of what the page said instead.
  const ready = /ready below/.test(said);
  const h1 = ready ? await sheetDoc().locator('h1').textContent({ timeout: 5000 }) : `(no report: ${said})`;
  const tiles = ready ? await sheetDoc().locator('.key .n').allTextContents() : [];
  ok(/ready below/.test(said) && h1 === 'Aircraft noise at TW9 3PZ' && tiles[0] === '56 dB' && tiles[1] === '3.9/10', 'a measured postcode makes a report with DEFRA\'s level and the Quiet Skies score from the endpoint', `${said} | ${h1} | ${tiles.join(' ')}`);
  // ON SCREEN ONLY (Bill, 2026-10-06): the PDF is the paid report for firms. No print
  // button, and printing - the browser's route to "Save as PDF" - prints the firms note
  // instead, from the page AND from inside the report's frame.
  ok((await page.locator('#print').count()) === 0 && (await page.locator('#result.is-open').isVisible()), 'the free report is on screen, with no print or Save as PDF button');
  await page.emulateMedia({ media: 'print' });
  const printed = {
    report: await page.locator('#result').isVisible(),
    note: await page.locator('.print-note').isVisible(),
    // Read INSIDE the frame: hiding the page's #result hides the frame too, so a
    // visibility check would pass with the frame's own rule gone (tried 2026-10-06).
    // The frame's rule is what covers printing the frame alone ("Print Frame").
    frameHeading: await page.evaluate(() => {
      const d = document.getElementById('sheet').contentDocument;
      const h1 = d?.querySelector('h1');
      return !h1 || d.defaultView.getComputedStyle(h1).display !== 'none';
    }),
  };
  await page.emulateMedia({ media: 'screen' });
  ok(!printed.report && printed.note && !printed.frameHeading, 'printing the page or the report frame gives the firms note, not the report', JSON.stringify(printed));
  const foot = ready ? await sheetDoc().locator('footer').textContent() : '';
  ok(/Free copy for personal use, not for use with clients/.test(foot), 'the free copy says on its face that it is for personal use, not for clients', foot.slice(-140));
  const alsoLine = ready ? await sheetDoc().locator('p.note', { hasText: 'Also at this postcode' }).textContent() : '';
  ok(/nearest station [^,]+, \d+ m in a straight line/.test(alsoLine), 'the report names the nearest station, from the same function as the front page', alsoLine.slice(-120));
  const airNote = ready ? await sheetDoc().locator('p.note', { hasText: 'Air measured nearby' }).textContent() : '';
  const kewSensor = nearestTo(sensorFile.sites, 51.4713, -0.2894);
  ok(airNote.startsWith(`Air measured nearby. Nearest Breathe London sensor: ${kewSensor.name}, `), 'the report names the nearest Breathe London sensor, from the same function as the front page', airNote.slice(0, 140));
  ok(foot.includes(sensorFile.attribution), "the report's sources carry Breathe London's credit word for word", foot.slice(-300));
  const reportSay = ready
    ? await sheetDoc().locator('p.note', { hasText: 'Have your say.' }).evaluate((p) => [...p.querySelectorAll('a')].map((a) => a.getAttribute('href')))
    : [];
  const reportWrong = ready ? await sheetDoc().locator('p.note', { hasText: 'Spotted something wrong?' }).evaluate((p) => p.querySelector('a')?.getAttribute('href')) : '';
  ok(
    reportSay.includes('https://webtrak.emsbk.com/lhr6') && reportSay.includes('https://airspacechange.caa.co.uk/having-your-say/') &&
      reportWrong === `mailto:support@skyscore.co.uk?subject=${encodeURIComponent('Correction: TW9 3PZ')}`,
    'the report says where to have your say and how to report a figure that looks wrong, from the same functions as the front page',
    JSON.stringify({ reportSay, reportWrong })
  );
  // PROTECTION FOR THE FREE COPY (Bill, 2026-10-06: "people can screenshot and maybe edit it"): a
  // watermark, a reference tied to the figures and the day, a check link with a QR code, the terms line.
  const today = new Date().toISOString().slice(0, 10);
  const free = await page.evaluate(() => {
    const d = document.getElementById('sheet').contentDocument;
    const m = d.querySelector('.free-copy-mark');
    const box = d.querySelector('.free-copy-check');
    return {
      // A tiled image since 2026-10-16 (M-10): the line is read from its data, and the image must be there.
      marks: m && /^url\("data:image\/svg\+xml/.test(d.defaultView.getComputedStyle(m).backgroundImage) ? 1 : 0,
      line: m?.dataset.line || '',
      hidden: m?.getAttribute('aria-hidden'),
      events: m ? d.defaultView.getComputedStyle(m).pointerEvents : '',
      ref: (box?.textContent.match(/Reference ([A-Z2-9]{4}-[A-Z2-9]{4})/) || [])[1] || '',
      link: box?.querySelector('a')?.getAttribute('href') || '',
      terms: /section 4, skyscore\.co\.uk\/terms/.test(box?.textContent || ''),
    };
  });
  // Nothing of the report is cut off: the frame is as tall as its content once the fonts are in.
  // It was measured once, before the fonts arrived, and the check block landed in the clipped strip.
  await page.evaluate(() => document.getElementById('sheet').contentDocument.fonts.ready);
  await page.waitForTimeout(150);
  const clip = await page.evaluate(() => {
    const f = document.getElementById('sheet');
    const box = f.contentDocument.querySelector('.free-copy-check').getBoundingClientRect();
    return { frame: f.clientHeight, checkBottom: Math.ceil(box.bottom) };
  });
  ok(clip.checkBottom <= clip.frame, 'the whole report shows in its frame, the check block included, once the fonts have arrived', JSON.stringify(clip));
  ok(
    free.marks === 1 && free.line.startsWith('Personal use only · TW9 3PZ · ') && free.hidden === 'true' && free.events === 'none',
    'the free copy is watermarked with its postcode and date, out of the way of screen readers and the pointer',
    JSON.stringify(free)
  );
  const wantLink = `https://skyscore.co.uk/reports/street/?postcode=TW9%203PZ&made=${today}&ref=${free.ref.replace('-', '')}`;
  ok(free.ref !== '' && free.link === wantLink && free.terms, 'the free copy carries a reference, a check link for that reference and day, and the terms line', `${free.ref} ${free.link}`);
  // WHOLE DEVICE PIXELS PER MODULE, CRISP EDGES (2026-10-09). At a fixed 132 px a module was 2.69 px and
  // anti-aliased, and the decode below failed on some days' patterns and not others: it went red on an
  // unchanged tree. Asserted here, not left to the decode, because whether a blurred code decodes depends
  // on the date. Measured over 80 links (see js/street_report_page.mjs), and checked again at 150% below.
  const qrShape = (frame) =>
    frame.locator('.free-copy-check svg').evaluate((s) => {
      const dpr = s.ownerDocument.defaultView.devicePixelRatio;
      const perModule = (s.getBoundingClientRect().width * dpr) / Number(s.dataset.modules);
      return { dpr, perModule: Math.round(perModule * 1000) / 1000, crisp: s.ownerDocument.defaultView.getComputedStyle(s).shapeRendering };
    });
  const wholeModules = (q) => q.perModule >= 3 && Math.abs(q.perModule - Math.round(q.perModule)) < 0.02 && q.crisp === 'crispedges';
  const qr1 = await qrShape(sheetDoc());
  ok(wholeModules(qr1), 'its QR code is drawn at whole device pixels per module, with crisp edges', JSON.stringify(qr1));
  // The QR code is DECODED, by OpenCV: a code that scans to the wrong address would be worse than none.
  // Enlarged first (nearest-neighbour, on a white border), from a screenshot at the context's own scale.
  const decodeQr = async (frame) => {
    const png = join(tmpdir(), `skyscore-qr-${process.pid}.png`);
    let out;
    try {
      await frame.locator('.free-copy-check svg').screenshot({ path: png });
      out = execFileSync(
        'python',
        [
          '-c',
          'import cv2,sys\nimg=cv2.imread(sys.argv[1])\nimg=cv2.resize(img,None,fx=4,fy=4,interpolation=cv2.INTER_NEAREST)\nimg=cv2.copyMakeBorder(img,40,40,40,40,cv2.BORDER_CONSTANT,value=(255,255,255))\nprint(cv2.QRCodeDetector().detectAndDecode(img)[0])',
          png,
        ],
        { encoding: 'utf8' }
      ).trim();
    } catch (e) {
      out = `(could not decode: ${String(e.message).split('\n')[0]})`;
    }
    await unlink(png).catch(() => {});
    return out;
  };
  const decoded = await decodeQr(sheetDoc());
  ok(decoded === wantLink, 'its QR code scans to exactly that check link', decoded);
  // AT 150% DISPLAY SCALING, the commonest Windows setting and the worst case for a fixed CSS size: 3 CSS px
  // a module is 4.5 device px, and that decoded 47 of 80 links. A context of its own, same stubs.
  {
    const scaled = await browser.newContext({ viewport: { width: 1366, height: 820 }, deviceScaleFactor: 1.5 });
    await scaled.route(OFFSITE, stubOffsite);
    const sp = await scaled.newPage();
    await sp.goto(`${BASE}reports/street/`, { waitUntil: 'domcontentloaded' });
    await sp.fill('#pc', 'TW9 3PZ');
    await sp.press('#pc', 'Enter');
    await sp.waitForFunction(() => /ready below/.test(document.getElementById('status').textContent), null, { timeout: 20000 }).catch(() => {});
    const frame = sp.frameLocator('#sheet');
    const ready = (await frame.locator('.free-copy-check svg').count()) > 0;
    const qr15 = ready ? await qrShape(frame) : { missing: true };
    const link15 = ready ? await frame.locator('.free-copy-check a').getAttribute('href') : '';
    const dec15 = ready ? await decodeQr(frame) : '(no report)';
    ok(ready && qr15.dpr === 1.5 && wholeModules(qr15) && dec15 === link15, 'at 150% display scaling its QR code is still whole device pixels per module, and scans', `${JSON.stringify(qr15)} | ${dec15}`);
    await scaled.close();
  }
  // ONE DAY ON THE WHOLE COPY (audit 2026-10-09 M-6). At 23:30 UTC on 9 October, London's clock reads
  // 00:30 on the 10th: "Prepared" read the local clock and said 10 October while the watermark, the
  // reference and the check link said the 9th, and a copy that disagrees with itself reads as tampered.
  {
    const late = await browser.newContext({ viewport: { width: 1366, height: 820 }, timezoneId: 'Europe/London' });
    await late.route(OFFSITE, stubOffsite);
    const lp = await late.newPage();
    await lp.clock.setFixedTime(new Date('2026-10-09T23:30:00Z'));
    await lp.goto(`${BASE}reports/street/`, { waitUntil: 'domcontentloaded' });
    await lp.fill('#pc', 'TW9 3PZ');
    await lp.press('#pc', 'Enter');
    await lp.waitForFunction(() => /ready below/.test(document.getElementById('status').textContent), null, { timeout: 20000 }).catch(() => {});
    const dates = await lp.evaluate(() => {
      const d = document.getElementById('sheet').contentDocument;
      return {
        local: new Date().toLocaleDateString('en-GB'),
        prepared: (d?.querySelector('footer')?.textContent.match(/Prepared ([^.]+)\./) || [])[1] || '',
        mark: d?.querySelector('.free-copy-mark')?.dataset.line.split(' · ')[2] || '',
        made: (d?.querySelector('.free-copy-check')?.textContent.match(/made ([^.]+)\./) || [])[1] || '',
        link: d?.querySelector('.free-copy-check a')?.getAttribute('href') || '',
      };
    });
    ok(
      dates.local === '10/10/2026' &&
        dates.prepared === '9 October 2026' &&
        dates.mark === '9 October 2026' &&
        dates.made === '9 October 2026' &&
        dates.link.includes('&made=2026-10-09&'),
      'a copy made at 00:30 London time on the 10th (23:30 UTC on the 9th) carries one day throughout: Prepared, watermark, reference and check link',
      JSON.stringify(dates)
    );
    await late.close();
  }
  // REFLOW ON A PHONE (audit 2026-10-09 I-6, WCAG 1.4.10). The free copy was a fixed 794 px A4 page in a
  // sideways scroller: at 390 px wide, 358 px of 826 showed and every line ran off the edge. Under 600 px it
  // now reads top to bottom; the map alone scrolls sideways, opened on the pin, and is a tab stop only then.
  // On a wide screen it is the A4 page it was, the routes a table, the map no tab stop.
  const wide = await page.evaluate(() => {
    const f = document.getElementById('sheet');
    const d = f.contentDocument;
    const td = d.querySelector('tbody td');
    return { frame: f.clientWidth, cell: td ? d.defaultView.getComputedStyle(td).display : null, mapStop: d.querySelector('.map-scroll')?.hasAttribute('tabindex') ?? null };
  });
  ok(wide.frame === 794 && wide.cell === 'table-cell' && wide.mapStop === false, 'on a wide screen the free report is still the A4 page: 794 px, the routes a table, the map no tab stop', JSON.stringify(wide));
  for (const vp of [{ width: 390, height: 844 }, { width: 320, height: 568 }]) {
    const phone = await browser.newContext({ viewport: vp, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
    await phone.route(OFFSITE, stubOffsite);
    const pp = await phone.newPage();
    await pp.goto(`${BASE}reports/street/`, { waitUntil: 'domcontentloaded' });
    await pp.fill('#pc', 'TW9 3PZ');
    await pp.press('#pc', 'Enter');
    await pp.waitForFunction(() => /ready below/.test(document.getElementById('status').textContent), null, { timeout: 20000 }).catch(() => {});
    await pp.evaluate(() => document.getElementById('sheet')?.contentDocument?.fonts.ready);
    await pp.waitForTimeout(200);
    const r = await pp.evaluate(() => {
      const f = document.getElementById('sheet');
      const d = f?.contentDocument;
      if (!d?.querySelector('h1')) return { made: false };
      const map = d.querySelector('.map-scroll');
      const words = [...d.querySelectorAll('h1, h2, p, li, td, .key')].filter((e) => !e.closest('.map-scroll'));
      const pin = map?.querySelector('.pin')?.getBoundingClientRect();
      const box = map?.getBoundingClientRect();
      const height = d.querySelector('tbody td:nth-child(4)');
      return {
        made: true,
        // The defect itself: the old page scrolled INSIDE .sheet-wrap, so neither the page nor the
        // frame scrolled while the A4 frame ran 400 px past the screen's edge.
        frameFits: f.getBoundingClientRect().right <= document.documentElement.clientWidth,
        wrapScrolls: document.querySelector('.sheet-wrap').scrollWidth > document.querySelector('.sheet-wrap').clientWidth,
        pageScrolls: document.documentElement.scrollWidth > document.documentElement.clientWidth,
        frameScrolls: d.documentElement.scrollWidth > d.documentElement.clientWidth,
        textRunsTo: Math.ceil(Math.max(...words.map((e) => e.getBoundingClientRect().right))),
        frameWidth: d.documentElement.clientWidth,
        mapScrolls: map ? map.scrollWidth > map.clientWidth : null,
        mapStop: map?.getAttribute('tabindex') === '0',
        pinInView: Boolean(pin && box && pin.left >= box.left && pin.right <= box.right),
        heightLabel: height ? d.defaultView.getComputedStyle(height, '::before').content : '',
        tilesPerRow: d.defaultView.getComputedStyle(d.querySelector('.keys')).gridTemplateColumns.split(' ').length,
      };
    });
    ok(
      r.made && r.frameFits && !r.wrapScrolls && !r.pageScrolls && !r.frameScrolls && r.textRunsTo <= r.frameWidth && r.tilesPerRow === 2 && /^"Height: "$/.test(r.heightLabel),
      `at ${vp.width} px the free report reflows: no sideways scroll, every line inside the frame, two tiles a row, route lines labelled from their column headings`,
      JSON.stringify(r)
    );
    ok(r.mapScrolls && r.mapStop && r.pinInView, `at ${vp.width} px the map keeps a legible width in its own scroller, opened on the postcode's pin, and is a tab stop`, JSON.stringify(r));
    const fl = pp.frameLocator('#sheet');
    const decodedPhone = r.made ? await decodeQr(fl) : '(no report)';
    const linkPhone = r.made ? await fl.locator('.free-copy-check a').getAttribute('href') : '';
    ok(decodedPhone === linkPhone && linkPhone !== '', `at ${vp.width} px its QR code still scans to its check link`, decodedPhone);
    await phone.close();
  }
  // The check: the genuine reference matches, one changed character does not, a malformed one is ignored.
  const checkWith = async (ref) => {
    await page.goto(`${BASE}reports/street/?postcode=TW9%203PZ&made=${today}&ref=${ref}`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => /ready below|outside the city|answered|reached/.test(document.getElementById('status').textContent), null, { timeout: 20000 });
    return page.locator('#check-result').evaluate((el) => ({ hidden: el.hidden, cls: el.className, text: el.textContent }));
  };
  const genuine = free.ref.replace('-', '');
  const okCheck = await checkWith(genuine);
  const badCheck = await checkWith(genuine.slice(0, 7) + (genuine[7] === 'A' ? 'B' : 'A'));
  const junk = await checkWith('NOT-A-REF');
  ok(
    !okCheck.hidden && /\bok\b/.test(okCheck.cls) && /matches/.test(okCheck.text) && /compare every figure on your copy/.test(okCheck.text) &&
      !badCheck.hidden && /\bbad\b/.test(badCheck.cls) && /does not match/.test(badCheck.text) &&
      junk.hidden,
    'a check link confirms the genuine reference, flags one changed character, and ignores a malformed one',
    JSON.stringify({ okCheck, badCheck, junk: junk.hidden })
  );
  const img = await sheetDoc().locator('svg image').getAttribute('href');
  ok(img === '/data/aircraft-noise-london-lden.png' && (await page.request.get(`${BASE}data/aircraft-noise-london-lden.png`)).status() === 200, 'its map draws DEFRA\'s London picture from an address the site serves', img);
  const est = await makeReport('NW1 7PJ');
  const estTiles = await sheetDoc().locator('.key').allTextContents();
  ok(/ready below/.test(est) && estTiles.some((t) => t.startsWith('9.0/10') && /ESTIMATE/.test(t)), 'an unmeasured postcode shows the estimate and calls it one', estTiles.join(' | '));
  const outside = await makeReport('EX1 1HS');
  ok(/outside the city regions/.test(outside) && !(await page.locator('#result').evaluate((r) => r.classList.contains('is-open'))), 'a postcode outside every city is told so and gets no report (the endpoint\'s 10.0 is from nothing nearby)', outside);
  const bad = await makeReport('NOT A PC!');
  ok(/does not look like a UK postcode/.test(bad), 'a string that is not a postcode is refused before anything is asked of the network', bad);
}

// 18b. ENGAGEMENT IS COUNTED, ONCE, AND ONLY FOR A PERSON'S ACTIONS (ROADMAP 3b, 2026-10-07).
// GoatCounter has no bounce rate, so the page sends `front-engaged` at the first thing a visitor
// does, and each way in once. A stand-in records the calls (the real script is a third party, and
// this run aborts every third-party request). A deep link searches at boot and must send nothing.
{
  const gcPage = await context.newPage();
  await gcPage.addInitScript(() => {
    window.__gc = [];
    window.goatcounter = { count: (v) => window.__gc.push(v.path) };
  });
  // Our own counter (js/count.mjs, since 2026-10-11) is served from this origin, so it would load
  // and replace the stand-in; GoatCounter's script was third-party and aborted. Section 8a holds
  // what the real module sends.
  await gcPage.route('**/js/count.mjs', (r) => r.fulfill({ status: 200, contentType: 'application/javascript', body: '' }));
  const sent = () => gcPage.evaluate(() => window.__gc.slice());
  await gcPage.goto(`${BASE}?postcode=TW9%203PZ`, { waitUntil: 'domcontentloaded' });
  await gcPage.waitForFunction(() => document.getElementById('answer')?.classList.contains('is-open'), null, { timeout: 15000 }).catch(() => {});
  const afterDeepLink = await sent();
  ok(afterDeepLink.length === 0, 'a deep link that searches at boot is not counted as engagement', JSON.stringify(afterDeepLink));

  await gcPage.goto(BASE, { waitUntil: 'domcontentloaded' });
  await gcPage.locator('.try button[data-pc="TW9 3PZ"]').click();
  await gcPage.fill('#pc', 'NW1 7PJ');
  await gcPage.press('#pc', 'Enter');
  await gcPage.fill('#pc', 'M22 5RX');
  await gcPage.press('#pc', 'Enter');
  await gcPage.locator('#chips button[data-city="manchester"]').click();
  await gcPage.waitForTimeout(300);
  const ways = await sent();
  ok(
    JSON.stringify(ways) === JSON.stringify(['event/front-engaged', 'event/front-example', 'event/front-search', 'event/front-city']),
    'engagement: one front-engaged at the first action, then each way in once (an example is not also a typed search; a second search is not counted again)',
    JSON.stringify(ways)
  );
  await gcPage.close();
}

// 18c. A VOTE FOR WHERE THE MAP GOES NEXT IS A COUNT, NOT A FORM (Bill, 2026-10-13). A visitor the map does
// not cover can vote for their council area (from an uncovered postcode) or a country (from a search that finds
// nothing, or a US ZIP outside the Bay Area). Each vote is one GoatCounter event: the council area or a code from
// a fixed list, never the postcode and never free text, once per place per page view. The stand-in records the
// whole event, so a postcode anywhere in it (path or title) fails here.
{
  const voteAs = await context.newPage();
  await voteAs.addInitScript(() => {
    window.__gc = [];
    window.goatcounter = { count: (v) => window.__gc.push(`${v.path}|${v.title}`) };
  });
  await voteAs.route('**/js/count.mjs', (r) => r.fulfill({ status: 200, contentType: 'application/javascript', body: '' }));
  const votes = async () => (await voteAs.evaluate(() => window.__gc.slice())).filter((e) => e.startsWith('event/want/'));
  const searchFor = async (q) => { await voteAs.fill('#pc', q); await voteAs.press('#pc', 'Enter'); };
  await voteAs.goto(BASE, { waitUntil: 'domcontentloaded' });
  await voteAs.waitForFunction(() => document.querySelectorAll('#map .boro').length > 0, null, { timeout: 15000 });

  await searchFor('EX1 1HS');
  await voteAs.waitForSelector('#ans-want:not([hidden]) button', { timeout: 10000 });
  const areaButton = voteAs.locator('#ans-want button');
  await areaButton.click();
  // A second click, as a person can make on a button marked aria-disabled (Playwright will not, so dispatch it).
  await areaButton.evaluate((b) => b.click());
  const afterArea = await votes();
  ok(JSON.stringify(afterArea) === JSON.stringify(['event/want/uk/exeter|Want covered: Exeter']),
    'vote: an uncovered postcode counts its council area once, and no postcode is sent', JSON.stringify(afterArea));
  ok((await areaButton.textContent()) === 'Thank you' && await areaButton.evaluate((b) => b === document.activeElement),
    'vote: the button says thank you (never "counted") and keeps keyboard focus', await areaButton.textContent());

  await searchFor('TW9 3PZ');
  await voteAs.waitForFunction(() => document.querySelector('#ans-title')?.textContent === 'TW9 3PZ', null, { timeout: 10000 });
  ok(await voteAs.locator('#ans-want').isHidden(), 'vote: a covered postcode carries no vote offer, and the last one is gone');

  await searchFor('Paris');
  await voteAs.waitForSelector('#want-country:not([hidden]) select', { timeout: 10000 });
  const go = voteAs.locator('#want-country button');
  await go.click(); // nothing chosen: nothing sent
  await voteAs.selectOption('#want-country select', 'fr');
  await go.click();
  await voteAs.selectOption('#want-country select', 'de');
  ok((await go.textContent()) === 'Count my vote', 'vote: choosing another country brings the button back');
  await go.click();
  const countries = (await votes()).slice(1);
  ok(JSON.stringify(countries) === JSON.stringify(['event/want/country/fr|Want covered: France', 'event/want/country/de|Want covered: Germany']),
    'vote: a search that finds nothing offers a fixed country list; nothing is sent until one is chosen', JSON.stringify(countries));
  ok((await voteAs.locator('#want-country input, #want-country textarea').count()) === 0, 'vote: there is no free-text box to type an address into');

  await searchFor('60601');
  await voteAs.waitForSelector('#want-country:not([hidden]) select', { timeout: 10000 });
  ok((await voteAs.locator('#want-country select').inputValue()) === 'us', 'vote: a US ZIP outside the Bay Area offers the list with the United States chosen');
  await voteAs.close();
}

// 18d. FIND AREAS (Bill, 2026-10-14, after Path came up at LGM #6): the panel's second tab, which lists the
// council areas whose published figures meet the reader's choices and shades them on the map beside it as
// each choice is made. The expected list is computed HERE from the CSV with the cuts written out, so a cut
// that drifts in the engine reds here as well as in tests/test_fit_conditions_mirror.py. Also held: real
// tabs (arrow keys, one tab stop, panels that exist); a blank figure is never a pass; nothing chosen
// shades nothing; a row under the pointer or keyboard outlines its area; the card replaces the list and
// closing it returns focus to the row; the map and the list stay on the same region both ways; the
// postcode tab takes the shading away; and the only count is that the tab was opened.
{
  const fp = await context.newPage();
  await fp.addInitScript(() => {
    window.__gc = [];
    window.goatcounter = { count: (v) => window.__gc.push(`${v.path}|${v.title}`) };
  });
  await fp.route('**/js/count.mjs', (r) => r.fulfill({ status: 200, contentType: 'application/javascript', body: '' }));
  fp.on('pageerror', (e) => errors.push(String(e)));
  await fp.goto(BASE, { waitUntil: 'domcontentloaded' });
  await fp.waitForSelector('.tabs:not([hidden]) #tab-find', { timeout: 15000 });
  await fp.waitForSelector('#map .boro', { timeout: 15000 });
  const listed = () => fp.locator('#fit-list button[data-borough]').evaluateAll((bs) => bs.map((b) => b.dataset.borough));
  const shadedNames = () => fp.locator('#map .boro.is-fit').evaluateAll((els) => els.map((e) => e.getAttribute('aria-label').replace(/, fits your choices: open its figures$/, '')));
  const UK = CSV.filter((r) => r.ons_code);
  const num = (v) => (v === '' ? null : Number(v));
  const order = (a, b) => (Number(b.score || -1) - Number(a.score || -1)) || (Number(a.avg_price_gbp) - Number(b.avg_price_gbp));
  const selectedTab = () => fp.locator('[role="tab"][aria-selected="true"]').getAttribute('id');

  // Real tabs: two, each naming a real panel, one tab stop, the arrow keys move and select.
  const tabs = await fp.locator('[role="tablist"] [role="tab"]').evaluateAll((ts) => ts.map((t) => [t.id, t.getAttribute('aria-controls'), t.tabIndex, Boolean(document.getElementById(t.getAttribute('aria-controls'))?.matches('[role="tabpanel"]'))]));
  ok(JSON.stringify(tabs) === JSON.stringify([['tab-check', 'panel-check', 0, true], ['tab-find', 'panel-find', -1, true]]),
    'find: two real tabs, each controlling a real panel, with one tab stop', JSON.stringify(tabs));
  await fp.locator('#tab-check').focus();
  await fp.keyboard.press('ArrowRight');
  ok((await selectedTab()) === 'tab-find' && await fp.evaluate(() => document.activeElement?.id === 'tab-find'), 'find: the right arrow moves to "Find areas" and selects it');
  ok(await fp.locator('#panel-find').isVisible() && await fp.locator('#panel-check').isHidden(), 'find: its panel shows and the postcode panel hides');
  ok(!(await fp.locator('.hero').getAttribute('class')).includes('is-intro'), 'find: the question over the faded map makes way, because the map is the answer');
  ok((await fp.locator('#fit-where').inputValue()) === 'london', 'find: the list starts on the region the map shows');
  ok((await listed()).length === 0 && /^Choose a price/.test(await fp.locator('#fit-count').textContent())
    && (await fp.locator('#map .boro.is-fit').count()) === 0 && await fp.locator('#toggle-fit').isHidden(),
  'find: with nothing chosen, nothing is listed or shaded, and it says what to do');

  // London, under £750,000, away from aircraft noise, close to a station: the list and the map are the CSV's answer.
  // (£750,000 since 2026-10-16: "away from aircraft noise" now also needs no route across the area, which left
  // Sutton alone under £600,000, and the hover checks below need three.)
  await fp.selectOption('#fit-budget', '750000');
  await fp.getByLabel('aircraft noise').check();
  await fp.getByLabel('a station').check();
  const want = UK.filter((r) => r.city === 'london' && num(r.avg_price_gbp) <= 750000 && quietAndClear(r) && num(r.rail_within_800m_pct) >= 50)
    .sort(order).map((r) => r.borough);
  const got = await listed();
  ok(want.length > 0 && JSON.stringify(got) === JSON.stringify(want), 'find: the list is exactly the CSV areas that meet all three, highest score first', `${got.join(', ')} vs ${want.join(', ')}`);
  ok((await fp.locator('#fit-count').textContent()).startsWith(`${want.length} of the 33 council areas in London`), 'find: the count says how many of how many', await fp.locator('#fit-count').textContent());
  const firstRow = fp.locator('#fit-list .find-row').first();
  const top = csvRow(want[0]);
  ok((await firstRow.locator('.find-score').textContent()) === `${top.score} Sky Score` && (await firstRow.locator('.find-price').textContent()) === `average £${Math.round(Number(top.avg_price_gbp) / 1000)}k`,
    'find: a row carries its average price and Sky Score from the CSV', `${await firstRow.locator('.find-price').textContent()} / ${await firstRow.locator('.find-score').textContent()}`);
  const shaded = (await shadedNames()).sort();
  ok(JSON.stringify(shaded) === JSON.stringify([...want].sort()), 'find: the map shades exactly the areas listed, as the choices are made, and says so in their labels', shaded.join(', '));
  const toggleFit = fp.locator('#toggle-fit');
  ok(await toggleFit.isVisible() && (await toggleFit.getAttribute('aria-pressed')) === 'true', 'find: the legend shows a "Fits your choices" switch, on');
  await toggleFit.click();
  ok((await fp.locator('#map .boro.is-fit').count()) === 0 && (await toggleFit.getAttribute('aria-pressed')) === 'false', 'find: and the switch turns the shading off');
  await toggleFit.click();

  // A row under the pointer, or reached by keyboard, outlines its area on the map.
  await fp.locator('#fit-list .find-row').nth(1).hover();
  const hot = await fp.locator('#map .boro.is-hot').evaluateAll((els) => els.map((e) => e.getAttribute('aria-label').split(',')[0].split(':')[0]));
  ok(hot.length === 1 && hot[0] === want[1], 'find: hovering a row outlines its area on the map', hot.join(', '));
  await fp.locator('#fit-list button[data-borough]').nth(2).focus();
  const hotKey = await fp.locator('#map .boro.is-hot').evaluateAll((els) => els.map((e) => e.getAttribute('aria-label').split(',')[0].split(':')[0]));
  ok(hotKey.length === 1 && hotKey[0] === want[2], 'find: and so does focusing one by keyboard', hotKey.join(', '));

  // The shading follows the list when a choice changes.
  // Dropping "aircraft noise" widens the list (dropping the station would not: every quiet, clear area has one).
  await fp.getByLabel('aircraft noise').uncheck();
  const wider = UK.filter((r) => r.city === 'london' && num(r.avg_price_gbp) <= 750000 && num(r.rail_within_800m_pct) >= 50).length;
  ok((await fp.locator('#map .boro.is-fit').count()) === wider, 'find: the shading follows the list when a choice changes', `${await fp.locator('#map .boro.is-fit').count()} vs ${wider}`);
  // Audit 2026-10-16 M-17: the matches are outlined in a layer ABOVE the noise picture, which is multiplied over
  // the fill and muddied it; one outline per shaded area, and the layer after the picture in drawing order.
  const outlines = await fp.evaluate(() => {
    const img = document.getElementById('noise-image'), layer = document.querySelector('#map .fit-outlines');
    return {
      edges: document.querySelectorAll('#map .fit-outlines path.edge').length,
      above: Boolean(img && layer && (img.compareDocumentPosition(layer) & Node.DOCUMENT_POSITION_FOLLOWING)),
    };
  });
  ok(outlines.edges === wider && outlines.above, 'find: each area that fits is outlined above the noise picture', JSON.stringify(outlines));
  await fp.getByLabel('aircraft noise').check();

  // An area opens its card in place of the list; closing it brings the list back with focus on that row.
  await fp.locator('#fit-list button[data-borough]').first().click();
  await fp.waitForSelector('#borough.is-open', { timeout: 10000 });
  // The card sits IN the selected tab's panel (audit 2026-10-16 M-14): the panel stays shown, the list steps aside.
  ok((await fp.locator('#borough h2').textContent()) === want[0] && await fp.evaluate(() => document.activeElement?.matches('#borough h2'))
    && await fp.locator('#panel-find').isVisible() && await fp.locator('#fit-list').isHidden() && await fp.locator('#fit-form').isHidden()
    && await fp.evaluate(() => Boolean(document.querySelector('#panel-find > #borough'))),
    'find: a row opens its card in place of the list, inside the Find panel, with focus on its name', want[0]);
  ok((await fp.locator('#borough').getAttribute('aria-live')) === 'off', 'find: a card focus moves into is not also announced as a live region (M-15)');
  await fp.locator('#borough-close').click();
  ok(await fp.locator('#panel-find').isVisible() && await fp.evaluate((n) => document.activeElement?.dataset?.borough === n, want[0]),
    'find: closing the card brings the list back, with focus on the row it came from');

  // THE BUDGET IS A HARD LIMIT (Bill, 2026-10-14): nothing over it is offered, not even as a near miss.
  // London, under £400,000, away from aircraft noise and close to a station fits nowhere; Bromley, Camden,
  // Enfield and Hackney meet both choices but average more, and were offered as "the nearest" until then.
  await fp.selectOption('#fit-budget', '400000');
  const nearest = await listed();
  const overBudget = nearest.filter((b) => num(csvRow(b).avg_price_gbp) > 400000);
  const nearMisses = await fp.locator('#fit-list .find-miss em').allTextContents();
  ok(/^None of the 33 council areas in London meets all of these\. The nearest under £400,000 miss one:$/.test(await fp.locator('#fit-count').textContent())
    && nearest.length > 0 && overBudget.length === 0 && nearMisses.every((m) => !/budget/.test(m)),
  'find: the budget is a hard limit: nothing over it is offered, not even as a near miss', `${nearest.join(', ')} | over budget: ${overBudget.join(', ')}`);
  await fp.selectOption('#fit-budget', '200000');
  ok((await fp.locator('#fit-count').textContent()) === 'No council area in London averages under £200,000. Try a higher price or another region.' && (await listed()).length === 0,
    'find: a budget no area meets says so plainly, and lists nothing', await fp.locator('#fit-count').textContent());
  await fp.selectOption('#fit-budget', '750000');

  // A blank figure is unknown, not a pass: anywhere, away from busy roads. Cardiff publishes no road share,
  // and a blank read as a number is 0, which is UNDER the cut, so this is the condition that would wave it
  // through. (Schools could not catch that: a blank Progress 8 read as 0 fails "above average" by luck.)
  await fp.selectOption('#fit-where', { index: 0 });
  await fp.selectOption('#fit-budget', { index: 0 });
  await fp.getByLabel('aircraft noise').uncheck();
  await fp.getByLabel('a station').uncheck();
  await fp.getByLabel('busy roads').check();
  const noRoad = UK.filter((r) => r.road_noise_above_who_pct === '').map((r) => r.borough);
  const quietRoads = UK.filter((r) => r.road_noise_above_who_pct !== '' && num(r.road_noise_above_who_pct) < 50);
  await fp.locator('#fit-more').click();
  const roads = await listed();
  ok(noRoad.length > 0 && !roads.some((b) => noRoad.includes(b)), 'find: an area that publishes no road-noise figure is never listed as avoiding busy roads', roads.filter((b) => noRoad.includes(b)).join(', '));
  ok((await fp.locator('#fit-note').textContent()).includes(`${noRoad.length} more might fit`),
    'find: and the areas that do not publish it are counted as "might fit", not dropped silently', await fp.locator('#fit-note').textContent());
  ok(roads.length === quietRoads.length, `find: "Show all" lists every one of the ${quietRoads.length}`, String(roads.length));
  ok(await fp.evaluate(() => document.activeElement?.matches('#fit-list button[data-borough]')), 'find: and focus lands on the first area it revealed, not the top of the panel');
  const inView = quietRoads.filter((r) => r.city === 'london').length;
  ok((await fp.locator('#map .boro.is-fit').count()) === inView, 'find: with "anywhere", the map shades the part of the list in view', `${await fp.locator('#map .boro.is-fit').count()} vs ${inView}`);

  // Nothing fits: Greater Manchester, close to a station and away from aircraft noise. Choosing the region moves
  // the map there; the areas one condition away are named with what they miss; nothing is shaded.
  await fp.getByLabel('busy roads').uncheck();
  await fp.selectOption('#fit-where', 'manchester');
  await fp.getByLabel('aircraft noise').check();
  await fp.getByLabel('a station').check();
  await fp.waitForFunction(() => document.querySelector('#chips button[aria-pressed="true"]')?.dataset.city === 'manchester', null, { timeout: 15000 });
  const noneText = await fp.locator('#fit-count').textContent();
  const misses = await fp.locator('#fit-list .find-miss em').allTextContents();
  ok(/^None of the 10 council areas in Greater Manchester meets all of these/.test(noneText) && misses.length > 0 && misses.every((m) => /^(more aircraft noise|fewer stations|flight routes cross it): /.test(m)),
    'find: choosing a region moves the map there; when nothing fits, the nearest are named with what they miss and by how much', `${noneText} / ${misses.join(' | ')}`);
  ok((await fp.locator('#map .boro.is-fit').count()) === 0 && await fp.locator('#toggle-fit').isHidden(), 'find: and nothing is shaded, so the switch goes');
  ok((await fp.evaluate(() => location.hash)) === '#find' && (await fp.evaluate(() => location.search)) === '?city=manchester',
    'find: the address keeps #find as the region changes, so a reload or a shared link comes back to the tab', await fp.evaluate(() => location.href));

  // The other way: a city chosen on the map becomes the list's region.
  await fp.locator('#chips button[data-city="westmidlands"]').click();
  await fp.waitForFunction(() => document.getElementById('fit-where')?.value === 'westmidlands', null, { timeout: 10000 }).catch(() => {});
  ok((await fp.locator('#fit-where').inputValue()) === 'westmidlands', 'find: a city chosen on the map becomes the list\'s region too');

  // Audit 2026-10-16 M-13: on the Find tab "Skip to the search" lands on the Find controls (the postcode box
  // is in the hidden panel, so it went to <body>), and the address keeps #find.
  await fp.evaluate(() => document.querySelector('a.skip').focus());
  await fp.keyboard.press('Enter');
  ok(await fp.evaluate(() => document.activeElement?.id === 'fit-where' && location.hash === '#find'),
    'find: on the Find tab the skip link lands on its first control and keeps #find', await fp.evaluate(() => `${document.activeElement?.id}|${location.hash}`));

  // Audit 2026-10-16 M-12: a region the API scores and this map does not draw says so, and stops offering the map.
  if (await fp.locator('#fit-where option[value="cardiff"]').count()) {
    await fp.selectOption('#fit-where', 'cardiff');
    ok(/does not draw Cardiff's council areas/.test(await fp.locator('#fit-note').textContent()) && await fp.locator('#fit-mapjump').isHidden()
      && (await fp.locator('#chips button[aria-pressed="true"]').getAttribute('data-city')) === 'westmidlands',
    'find: a region the map does not draw says so, leaves the map where it was, and stops offering it', await fp.locator('#fit-note').textContent());
    await fp.selectOption('#fit-where', 'westmidlands');
  } else {
    ok(false, 'find: the list should offer Cardiff (an API-only region) for the undrawn-region check');
  }

  // Review 2026-10-15: a city the list does not hold (the open-data CSV is UK council areas) must
  // not leave a West Midlands list silently beside a New York map.
  await fp.locator('#chips button[data-city="nyc"]').click();
  await fp.waitForFunction(() => /does not cover/.test(document.getElementById('fit-note')?.textContent || ''), null, { timeout: 15000 }).catch(() => {});
  ok(/showing New York, which this list does not cover/.test(await fp.locator('#fit-note').textContent()) && await fp.locator('#fit-mapjump').isHidden(),
    'find: on New York the list says the map is elsewhere, and stops offering to show its areas there', await fp.locator('#fit-note').textContent());

  // An area in another city, from "anywhere": the map switches to it.
  await fp.selectOption('#fit-where', { index: 0 });
  await fp.getByLabel('aircraft noise').uncheck();
  await fp.getByLabel('a station').uncheck();
  await fp.selectOption('#fit-budget', '200000');
  // The first area in a city the map DRAWS and is not showing: Cardiff, say, has no outlines to switch to.
  const drawn = new Set(['london', 'manchester', 'westmidlands', 'westyorkshire', 'southyorkshire', 'merseyside', 'tyneandwear', 'bristol', 'leicester', 'teesside']);
  const cheap = UK.filter((r) => num(r.avg_price_gbp) <= 200000).sort(order).find((r) => drawn.has(r.city) && r.city !== 'westmidlands');
  if (await fp.locator('#fit-more').count()) await fp.locator('#fit-more').click();
  await fp.locator(`#fit-list button[data-borough="${cheap.borough}"]`).click();
  await fp.waitForFunction((n) => document.querySelector('#borough.is-open h2')?.textContent === n, cheap.borough, { timeout: 15000 });
  ok((await fp.locator('#chips button[aria-pressed="true"]').getAttribute('data-city')) === cheap.city, 'find: an area in another city switches the map to that city', `${cheap.borough} (${cheap.city})`);

  // Review 2026-10-15: a list rebuilt while the card is open detaches the row that opened it, and
  // closing then focused the search box, hidden in the other tab: focus fell to <body>.
  await fp.evaluate(() => {
    const s = document.getElementById('fit-budget');
    s.value = '250000';
    s.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await fp.locator('#borough-close').click();
  const afterClose = await fp.evaluate(() => {
    const a = document.activeElement;
    return { el: a?.id || a?.tagName, inFind: Boolean(a?.closest('#panel-find')) || a?.id === 'tab-find' };
  });
  ok(afterClose.inFind, 'find: closing a card after the list was rebuilt keeps focus in the Find panel, never on the page body', JSON.stringify(afterClose));

  // Back to the postcode tab: the shading and its switch go, and the postcode panel is back.
  await fp.locator('#tab-check').click();
  ok((await fp.locator('#map .boro.is-fit').count()) === 0 && await fp.locator('#toggle-fit').isHidden() && await fp.locator('#panel-check').isVisible()
    && (await fp.evaluate(() => location.hash)) === '',
  'find: the postcode tab takes the shading, its switch and #find away');

  const events = await fp.evaluate(() => window.__gc.slice());
  ok(JSON.stringify(events) === JSON.stringify(['event/front-engaged|front-engaged', 'event/front-fit|front-fit', 'event/front-city|front-city']),
    'find: one count that the tab was opened, and nothing about what was chosen', JSON.stringify(events));
  await fp.close();
}

// 18e. FIND AREAS IS PART OF THE PAGE, NOT A HIDDEN TAB (Bill, 2026-10-14: "where are the options exactly",
// then "it can fit better on the website"). /#find opens the tab, and is not engagement (nobody has done
// anything); the "Find an area that fits" card opens it; and the card's figure is the number of choices
// the tab offers, counted from the page, never a number someone has to remember to change.
{
  const dp = await context.newPage();
  await dp.addInitScript(() => {
    window.__gc = [];
    window.goatcounter = { count: (v) => window.__gc.push(v.path) };
  });
  await dp.route('**/js/count.mjs', (r) => r.fulfill({ status: 200, contentType: 'application/javascript', body: '' }));
  dp.on('pageerror', (e) => errors.push(String(e)));
  await dp.goto(`${BASE}#find`, { waitUntil: 'domcontentloaded' });
  await dp.waitForFunction(() => document.getElementById('tab-find')?.getAttribute('aria-selected') === 'true', null, { timeout: 15000 }).catch(() => {});
  ok((await dp.locator('#tab-find').getAttribute('aria-selected')) === 'true' && await dp.locator('#panel-find').isVisible(), 'find: /#find opens the Find areas tab');
  ok((await dp.evaluate(() => window.__gc.slice())).length === 0, 'find: and a link opening it is not counted as engagement', JSON.stringify(await dp.evaluate(() => window.__gc.slice())));
  await dp.locator('#tab-check').click();
  const card = dp.locator('.card', { has: dp.locator('a[href="#find"]') });
  await card.locator('a[href="#find"]').click();
  ok((await dp.locator('#tab-find').getAttribute('aria-selected')) === 'true' && await dp.evaluate(() => document.activeElement?.id === 'tab-find'),
    'find: the "Find an area that fits" card opens the tab, with focus on it');
  const choices = await dp.locator('#fit-avoid input, #fit-want input').count();
  const fig = (await card.locator('.fig').evaluate((el) => el.firstChild.textContent)).trim();
  ok(choices > 0 && fig === String(choices), 'find: the card\'s figure is the number of choices the tab offers', `${fig} vs ${choices}`);

  // Review 2026-10-15: an area opened from the list writes ?borough= with #find, and booting from
  // that link closed the card the link was for.
  await dp.goto(`${BASE}?city=london&borough=Camden#find`, { waitUntil: 'domcontentloaded' });
  await dp.waitForFunction(() => document.getElementById('tab-find')?.getAttribute('aria-selected') === 'true', null, { timeout: 15000 }).catch(() => {});
  await dp.waitForFunction(() => document.querySelector('#borough.is-open h2')?.textContent === 'Camden', null, { timeout: 15000 }).catch(() => {});
  ok((await dp.locator('#tab-find').getAttribute('aria-selected')) === 'true' && (await dp.locator('#borough.is-open h2').textContent().catch(() => '')) === 'Camden',
    'find: a shared link to an area on the Find tab opens with that area\'s card', await dp.evaluate(() => location.href));
  await dp.close();
}

// 19. Every file this run fetched is one a Makefile target uploads. Served through those same rules above, an
// unrouted path is one the deployed site would not have: on 2026-10-03 four data files the engine reads had no
// upload line (the map carries their contents inline), and the page would have opened on "The map could not load".
ok(fetched.has('/js/home-engine.mjs') && fetched.has('/js/street_report.mjs') && fetched.has('/data/london-boroughs.json') && rules.length >= 20, 'the upload check saw the pages\' files and the Makefile\'s upload lines', `${fetched.size} files fetched, ${rules.length} upload rules`);
ok(unrouted.size === 0, `every one of the ${fetched.size} files the pages fetched is one a Makefile target uploads`, [...unrouted].sort().join(', '));

ok(errors.length === 0, 'no page errors', errors.join(' | '));
await browser.close();
server.close();

console.log(`\n${failures.length ? 'FAIL' : 'PASS'}: ${checks - failures.length} of ${checks} checks`);
for (const f of failures) console.log(`  - ${f}`);
process.exit(failures.length ? 1 : 0);
