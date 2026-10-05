// The new front page (preview/index.html + preview/hp-engine.js) is a tool,
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
// Run: node tests/preview-home.mjs   (in preflight, blocking)
import { chromium } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const PORT = 8941;
const TYPES = {
  '.html': 'text/html', '.js': 'application/javascript', '.mjs': 'application/javascript', '.json': 'application/json',
  '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.csv': 'text/csv', '.pdf': 'application/pdf',
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
const BASE = `http://127.0.0.1:${PORT}/preview/`;

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
    const key = url.pathname.split('/').pop().toUpperCase();
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
ok((await page.locator('#chips button').count()) === 11 && (await page.locator('#chips a').count()) === 1, 'eleven city chips plus the New York link');
await page.keyboard.press('Tab');
const onSkip = await page.evaluate(() => document.activeElement?.matches('a.skip[href="#pc"]'));
ok(onSkip, 'the first Tab reaches "Skip to the search" (audit I-5: the box was stop 56)');
// Enter only on the skip link: on anything else the first stop is a header link, and Enter would leave the page.
if (onSkip) await page.keyboard.press('Enter');
ok(onSkip && (await page.evaluate(() => document.activeElement?.id === 'pc')), 'and Enter on it lands in the search box');
// The postcode -> city lookup is the PREVIEW's own copy, so the 86 real postcodes.io spellings the live map is
// held to (tests/fixtures/postcodes-io-districts.json) are run through it too. It missed Barking and Dagenham.
const spellings = JSON.parse(await readFile(join(ROOT, 'tests', 'fixtures', 'postcodes-io-districts.json'), 'utf8')).districts;
const derived = await page.evaluate(async (ds) => {
  const engine = await import('/preview/hp-engine.js');
  if (typeof engine.cityOf !== 'function') return null;
  return ds.map((d) => ({ ...d, got: engine.cityOf(d.admin_district) }));
}, spellings);
const wrong = derived ? derived.filter((d) => d.got !== d.city) : [{ admin_district: 'the engine exports no cityOf', got: '' }];
ok(spellings.length >= 80 && wrong.length === 0, `all ${spellings.length} postcodes.io district spellings resolve to their own city (audit I-1)`, wrong.map((d) => `${d.admin_district} -> ${d.got}`).join('; '));

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
ok(links.includes('/area/london/camden/') && links.includes('/?city=london&borough=Camden'), 'links to the scorecard page and the live map', links.join(' '));
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
ok(/Nearest airport on the map: Heathrow, [\d.]+ km to the (west|north-west|south-west)/.test(routes), 'the answer names the nearest airport on the map with distance and direction', routes);
ok(/Under the Heathrow 27[LR] final approach, .* aircraft at about [\d,]+ ft/.test(routes), 'Kew is reported under a Heathrow 27 final approach at a height', routes);
const area = await page.locator('#ans-area').textContent();
const richmond = csvRow('Richmond upon Thames');
ok(area.includes('Richmond upon Thames') && area.includes(`Sky Score ${richmond.score}`) && area.includes(`${richmond.flood_medium_or_high_pct}% of addresses at medium or high flood risk`), 'the council-area line carries the CSV score and flood share', area);
ok((await page.locator('#map .pin').count()) === 1, 'a pin is drawn at the postcode');
ok((await page.locator('#ans-link').getAttribute('href')) === '/?city=london&postcode=TW9%203PZ', 'the hand-off link carries city and postcode to the live map');
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
await page.goto(`${BASE}?city=constructor`, { waitUntil: 'domcontentloaded' });
await waitMap();
ok((await boroCount()) === 33 && !/could not load/.test(await page.locator('#status').textContent()), '?city=constructor opens London, not a map that cannot load (audit M-6)');
await page.goto(`${BASE}?city=bayarea&postcode=94612`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => document.querySelector('#borough.is-open h2')?.textContent === 'Oakland', null, { timeout: 20000 });
ok((await page.locator('#map .pin').count()) === 1 && (await page.locator('#chips button[data-city="bayarea"]').getAttribute('aria-pressed')) === 'true', 'a ZIP in the URL boots the Bay Area with its city open and its pin drawn');

// 14. A phone: the card scrolls into view on a tap and the controls sit inside the viewport.
await page.setViewportSize({ width: 390, height: 844 });
await page.goto(BASE, { waitUntil: 'domcontentloaded' });
await waitMap();
await page.locator('#map .boro[aria-label^="Camden"]').click({ force: true });
await page.waitForSelector('#borough.is-open');
await page.waitForTimeout(700);
const cardTop = await page.locator('#borough').evaluate((e) => e.getBoundingClientRect().top);
ok(cardTop >= -1 && cardTop < 844, 'on a phone the card is brought into view', `top ${Math.round(cardTop)}px`);
const inside = await page.locator('#toggle-noise, #zoom-in, #zoom-out, #zoom-reset').evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return r.left >= 0 && r.right <= 390; }));
ok(inside.every(Boolean), 'layer and zoom controls are inside a phone viewport');

// 15. Every file this run fetched is one a Makefile target uploads. This gate serves the working tree, where
// a file no target deploys looks exactly like one that is live: on 2026-10-03 four data files the engine reads
// had no upload line (the live map carries their contents inline), and the deployed page would have opened on
// "The map could not load". The rules are read from `make.py --dry-run`, so the Makefile stays the one holder.
await page.goto(`${BASE}reports/`, { waitUntil: 'domcontentloaded' });
const pdfs = await page.locator('a[href$=".pdf"]').evaluateAll((as) => as.map((a) => new URL(a.href).pathname));
for (const p of pdfs) if ((await page.request.get(`http://127.0.0.1:${PORT}${p}`)).status() === 200) fetched.add(p);
ok(pdfs.length >= 2 && pdfs.every((p) => fetched.has(p)), 'the reports page links sample PDFs that exist', pdfs.join(' '));
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
  if (verb === 'sync' || /--recursive/.test(line)) rules.push({ prefix: dest, includes });
  else rules.push({ key: dest.endsWith('/') ? dest + src.split('/').pop() : dest });
}
// CloudFront's rewrite: a folder or an extensionless path is served from its index.html.
const keyOf = (p) => (p.endsWith('/') ? `${p}index.html` : extname(p) ? p : `${p}/index.html`).replace(/^\//, '');
const isUploaded = (p) => {
  const key = keyOf(p);
  return rules.some((r) => (r.key ? r.key === key : key.startsWith(r.prefix) && (!r.includes.length || r.includes.some((g) => g.test(key.slice(r.prefix.length))))));
};
const orphans = [...fetched].filter((p) => !isUploaded(p)).sort();
ok(fetched.has('/preview/hp-engine.js') && fetched.has('/data/london-boroughs.json') && rules.length >= 20, 'the upload check saw the page\'s files and the Makefile\'s upload lines', `${fetched.size} files fetched, ${rules.length} upload rules`);
ok(orphans.length === 0, `every one of the ${fetched.size} files the page fetched is one a Makefile target uploads`, orphans.join(', '));

// 16. What a report costs lives on the reports page alone, and both pages reach pricing and the council areas.
const reportsText = await page.locator('main').textContent();
ok(/Your own home: free/.test(reportsText) && /Firms: £35 a report/.test(reportsText) && /not a conveyancing search/.test(reportsText) && !/\+ ?VAT/.test(reportsText), 'the reports page prices a report: free for your own home, £35 for firms, no VAT added, not a conveyancing search');
const footReports = await page.locator('footer a').evaluateAll((as) => as.map((a) => a.getAttribute('href')));
await page.goto(BASE, { waitUntil: 'domcontentloaded' });
await waitMap();
const frontText = await page.locator('body').textContent();
const frontLinks = await page.locator('main a, footer a').evaluateAll((as) => as.map((a) => a.getAttribute('href')));
ok(!/£35/.test(frontText) && frontLinks.includes('/preview/reports/#prices'), 'the front page links to the price and does not repeat it');
ok(['/pricing', '/area/'].every((h) => frontLinks.includes(h) && footReports.includes(h)), 'pricing and the council areas are linked from both preview pages', `${frontLinks.join(' ')} | ${footReports.join(' ')}`);
for (const p of ['/pricing', '/area/']) ok((await page.request.get(`http://127.0.0.1:${PORT}${p === '/pricing' ? '/pricing.html' : p}`)).status() === 200, `${p} is a page that exists`);

// 17. The OS street-map trial. No key is in the source: nothing is asked of api.os.uk until a device is given
// one, the key leaves the address bar, and each tile sits where web-mercator says it should - checked against
// the pin of a known postcode, because a tile grid that is off by one still looks like a map.
ok(osTiles.length === 0, 'nothing was requested from api.os.uk in the whole run without a key', osTiles.slice(0, 2).join(' '));
ok(await page.locator('#toggle-streets').isHidden(), 'the Streets button is hidden without a key');
await page.setViewportSize({ width: 1366, height: 820 });
await page.goto(`${BASE}?oskey=TESTKEY1234`, { waitUntil: 'domcontentloaded' });
await waitMap();
ok(!(await page.evaluate(() => location.search)).includes('oskey'), 'the key leaves the address bar');
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
await page.goto(`${BASE}?oskey=off`, { waitUntil: 'domcontentloaded' });
await waitMap();
ok((await page.locator('#toggle-streets').isHidden()) && (await page.locator('#map .streets image').count()) === 0, '?oskey=off forgets the key');

ok(errors.length === 0, 'no page errors', errors.join(' | '));
await browser.close();
server.close();

console.log(`\n${failures.length ? 'FAIL' : 'PASS'}: ${checks - failures.length} of ${checks} checks`);
for (const f of failures) console.log(`  - ${f}`);
process.exit(failures.length ? 1 : 0);
