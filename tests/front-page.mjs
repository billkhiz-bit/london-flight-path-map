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
import { fileURLToPath } from 'node:url';

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

// Real postcodes.io shapes, trimmed to what the page reads.
const GEO = {
  TW93PZ: { postcode: 'TW9 3PZ', latitude: 51.4713, longitude: -0.2894, admin_district: 'Richmond upon Thames' },
  NW17PJ: { postcode: 'NW1 7PJ', latitude: 51.539, longitude: -0.1426, admin_district: 'Camden' },
  EX11HS: { postcode: 'EX1 1HS', latitude: 50.722209, longitude: -3.530574, admin_district: 'Exeter' },
  M225RX: { postcode: 'M22 5RX', latitude: 53.3677, longitude: -2.2644, admin_district: 'Manchester' },
};
// Real /v1/environment shapes, captured 2026-10-03, keyed on the latitude the page sends.
const ENV = {
  '51.4713': { environment: { roadNoiseLdenDb: 53.1, roadNoiseWhoGuidelineDb: 53, no2AnnualMeanUgm3: 16.3, no2WhoGuidelineUgm3: 10, pm25AnnualMeanUgm3: 8.4, pm25WhoGuidelineUgm3: 5, aircraftNoiseLdenDb: 56.0, aircraftQuiet: 3.9, aircraftQuietCoverage: 'measured', aircraftNoiseWhoGuidelineDb: 45 }, notices: [] },
  '51.539': { environment: { roadNoiseLdenDb: 74.7, roadNoiseWhoGuidelineDb: 53, no2AnnualMeanUgm3: 23.0, no2WhoGuidelineUgm3: 10, pm25AnnualMeanUgm3: 9.5, pm25WhoGuidelineUgm3: 5, aircraftQuietEstimated: 9.0, aircraftQuietBasis: 'flight-path geometry, not measured', aircraftQuietCoverage: 'city' }, notices: [] },
  '50.722209': { environment: { no2AnnualMeanUgm3: 8.0, no2WhoGuidelineUgm3: 10, pm25AnnualMeanUgm3: 5.6, pm25WhoGuidelineUgm3: 5, aircraftQuietEstimated: 10.0, aircraftQuietCoverage: 'outside' }, notices: [] },
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
await context.route(/^https?:\/\/(?!127\.0\.0\.1)/, (route) => {
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
});
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
// The first use, here by keyboard: on the opening screen the question covers most of
// London (that is the design: the map is the backdrop until someone asks), and every
// council area stays reachable by Tab and Enter.
await page.locator('#map .boro[aria-label^="Havering"]').focus();
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
ok(facts.some((f) => f.includes(`${camden.flood_medium_or_high_pct}% of addresses at medium or high`)), 'the card carries flood risk (the card promised it)');
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
ok(/Nearest airport on the map: Heathrow, [\d.]+ km to the (west|north-west|south-west)/.test(routes), 'the answer names the nearest airport on the map with distance and direction', routes);
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
}
const area = await page.locator('#ans-area').textContent();
const richmond = csvRow('Richmond upon Thames');
ok(area.includes('Richmond upon Thames') && area.includes(`Sky Score ${richmond.score}`) && area.includes(`${richmond.flood_medium_or_high_pct}% of addresses at medium or high flood risk`), 'the council-area line carries the CSV score and flood share', area);
ok((await page.locator('#map .pin').count()) === 1, 'a pin is drawn at the postcode');
ok((await page.locator('#ans-link').getAttribute('href')) === '/map/?city=london&postcode=TW9%203PZ', 'the hand-off link carries city and postcode to the full map at /map/');
ok(await page.evaluate(() => location.search) === '?city=london&postcode=TW9+3PZ', 'URL carries ?city=&postcode=');
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
ok(/Not on the map yet/.test(await page.locator('#borough .where').textContent()), 'an API-only council area shows its figures and says it is not on the map');
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
ok((await boroCount()) === 33 && !/Not on the map yet/.test(mismatchWhere), 'a council area in the URL opens on its own city, whatever ?city= says', `${await boroCount()} areas drawn; "${mismatchWhere}"`);
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
await page.goto(`http://127.0.0.1:${PORT}/api/`, { waitUntil: 'domcontentloaded' });
const apiPrices = await pricesOn();
const apiCards = await cardLook();
await page.goto(`http://127.0.0.1:${PORT}/pricing`, { waitUntil: 'domcontentloaded' });
const pricingPrices = await pricesOn();
const pricingCards = await cardLook();
ok(
  [apiCards, pricingCards].every((c) => c.cards >= 4 && c.ringed.length === 0 && c.buttons.length === 1),
  'no pricing card is highlighted, on /pricing or /api/, and every card button looks the same',
  JSON.stringify({ apiCards, pricingCards })
);
const priceText = {};
const clashes = [];
for (const [key, text] of [...pricingPrices, ...apiPrices]) {
  if (key in priceText && priceText[key] !== text) clashes.push(`${key}: "${priceText[key]}" vs "${text}"`);
  priceText[key] ??= text;
}
const pricingKeys = pricingPrices.map(([k]) => k);
const apiKeys = apiPrices.map(([k]) => k);
const apiLadder = ['api-free', 'pilot', 'api-professional', 'api-enterprise'];
ok(
  clashes.length === 0 &&
    pricingKeys.filter((k) => k === 'pilot').length === 2 &&
    ['council-area-study', 'council-licence', ...apiLadder].every((k) => pricingKeys.includes(k)) &&
    apiLadder.every((k) => apiKeys.includes(k)),
  'every price on /pricing and /api/ that shares a key reads the same (the pilot on both ladders, the API tiers on both pages)',
  clashes.join('; ') || JSON.stringify({ pricingPrices, apiPrices })
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
for (const [path, here] of [
  ['/', null],
  ['/reports/', '/reports/'],
  ['/pricing', '/pricing'],
  ['/api/', '/api/'],
  ['/open-data/', '/open-data/'],
  ['/area/london/camden/', null],
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
  // PROTECTION FOR THE FREE COPY (Bill, 2026-10-06: "people can screenshot and maybe edit it"): a
  // watermark, a reference tied to the figures and the day, a check link with a QR code, the terms line.
  const today = new Date().toISOString().slice(0, 10);
  const free = await page.evaluate(() => {
    const d = document.getElementById('sheet').contentDocument;
    const m = d.querySelector('.free-copy-mark');
    const box = d.querySelector('.free-copy-check');
    return {
      marks: m ? m.children.length : 0,
      line: m?.children[0]?.textContent || '',
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
    free.marks >= 20 && free.line.startsWith('Personal use only · TW9 3PZ · ') && free.hidden === 'true' && free.events === 'none',
    'the free copy is watermarked with its postcode and date, out of the way of screen readers and the pointer',
    JSON.stringify(free)
  );
  const wantLink = `https://skyscore.co.uk/reports/street/?postcode=TW9%203PZ&made=${today}&ref=${free.ref.replace('-', '')}`;
  ok(free.ref !== '' && free.link === wantLink && free.terms, 'the free copy carries a reference, a check link for that reference and day, and the terms line', `${free.ref} ${free.link}`);
  // The QR code is DECODED, by OpenCV: a code that scans to the wrong address would be worse than none.
  // Enlarged first (nearest-neighbour, on a white border): at 132 px a module is about 3 px.
  let decoded = '';
  const png = join(tmpdir(), `skyscore-qr-${process.pid}.png`);
  try {
    await sheetDoc().locator('.free-copy-check svg').screenshot({ path: png });
    decoded = execFileSync(
      'python',
      [
        '-c',
        'import cv2,sys\nimg=cv2.imread(sys.argv[1])\nimg=cv2.resize(img,None,fx=4,fy=4,interpolation=cv2.INTER_NEAREST)\nimg=cv2.copyMakeBorder(img,40,40,40,40,cv2.BORDER_CONSTANT,value=(255,255,255))\nprint(cv2.QRCodeDetector().detectAndDecode(img)[0])',
        png,
      ],
      { encoding: 'utf8' }
    ).trim();
  } catch (e) {
    decoded = `(could not decode: ${String(e.message).split('\n')[0]})`;
  }
  await unlink(png).catch(() => {});
  ok(decoded === wantLink, 'its QR code scans to exactly that check link', decoded);
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
    !okCheck.hidden && /\bok\b/.test(okCheck.cls) && /matches/.test(okCheck.text) &&
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
