// Does the map fit the box it is drawn in?
//
// WHY THIS EXISTS. On 2026-08-24 every city was measured to be drawing part of
// its geography OUTSIDE the map's own SVG box on every phone - London worst at
// 40.9% off-screen at 320x568, with Heathrow 140px past the left edge, and even
// the best case (Leicester) losing 8.1%. Boroughs on a region's flanks could
// not be seen or tapped. In landscape it was the other axis: 28.4% clipped off
// the top and bottom at 844x390.
//
// EVERY GATE IN THE SUITE PASSED THROUGHOUT. tests/responsive.mjs asks four
// questions - does the DOCUMENT overflow, and is a CONTROL past the edge,
// covered, or clipped above. An SVG path drawn outside its own SVG box is none
// of those: the document does not scroll, and a borough is not a control.
// tests/city-switch.mjs counts outlines, and the count is right whether or not
// you can see them. So the defect was invisible to the whole suite while being
// the first thing a phone user would notice.
//
// WHAT IT ASSERTS. For every city at every viewport, the union bounding box of
// the drawn paths must lie inside the SVG box. It reads the geometry back out
// of getBBox() rather than recomputing the projection, so it cannot agree with
// the fix's own arithmetic - the expectation does not come from the code under
// test.
//
// It also asserts a LOWER bound. Clipping is trivially avoidable by drawing the
// map tiny, so a fit that leaves the geography under a floor of the box is a
// failure too. Both directions were proven red before this was trusted:
// restoring the old constant fails the upper bound at every phone, and halving
// the fitted scale fails the lower one.
//
//   node tests/map-fit.mjs [baseUrl]

import { chromium } from '@playwright/test';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const PORT = 8931;
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

// Portrait phones, a landscape phone, the breakpoint boundary, and desktop.
// LANDSCAPE IS NOT OPTIONAL HERE: it was the only viewport where the old code
// took the desktop branch, so it failed in the vertical axis while every
// portrait phone failed in the horizontal one. A suite of portraits alone would
// have called that fixed.
const VIEWPORTS = [
  [320, 568, 'iPhone SE, smallest in use'],
  [375, 667, 'iPhone 8 / SE2'],
  [390, 844, 'iPhone 14'],
  [414, 896, 'iPhone 11 Pro Max'],
  [430, 932, 'iPhone 15 Pro Max'],
  [844, 390, 'iPhone 14 LANDSCAPE'],
  [768, 1024, 'iPad portrait'],
  [1366, 768, 'commonest laptop'],
  [1440, 900, 'desktop'],
];

// The geography must fill at least this share of the axis that binds. Without
// it, "nothing is clipped" is satisfiable by drawing nothing.
const MIN_FILL = 0.4;

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
const BASE = process.argv[2] || `http://127.0.0.1:${PORT}/`;

function measure() {
  const svg = document.getElementById('map-svg');
  if (!svg) return { error: 'no #map-svg' };
  const box = svg.getBoundingClientRect();
  const drawn = [...svg.querySelectorAll('path')].filter((p) => {
    try {
      return p.getBBox().width > 0;
    } catch {
      return false;
    }
  });
  if (!drawn.length) return { error: 'no geography drawn' };
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (const p of drawn) {
    const b = p.getBBox();
    x0 = Math.min(x0, b.x);
    y0 = Math.min(y0, b.y);
    x1 = Math.max(x1, b.x + b.width);
    y1 = Math.max(y1, b.y + b.height);
  }
  return {
    boxW: box.width,
    boxH: box.height,
    geoW: x1 - x0,
    geoH: y1 - y0,
    over: {
      left: Math.max(0, -x0),
      right: Math.max(0, x1 - box.width),
      top: Math.max(0, -y0),
      bottom: Math.max(0, y1 - box.height),
    },
  };
}

const browser = await chromium.launch();
const failures = [];
let checks = 0;
// Set on the first viewport pass, from CITY_DATA, so the floor below is the
// registry's own count rather than a literal that goes stale on city twelve.
let CITY_COUNT = 0;

for (const [w, h, label] of VIEWPORTS) {
  const ctx = await browser.newContext({
    viewport: { width: w, height: h },
    hasTouch: w < 900,
    isMobile: w < 900,
  });
  const page = await ctx.newPage();
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page
    .waitForFunction(() => document.querySelectorAll('#map-svg path').length > 3, { timeout: 20000 })
    .catch(() => {});
  await page.waitForTimeout(1200);

  // DRIVEN FROM CITY_DATA AND ACROSS BOTH COUNTRY TABS (2026-08-31, audit I11).
  //
  // This enumerated `.city-selector .city-btn`, and the app renders chips for
  // the ACTIVE COUNTRY only - so this gate measured 10 cities, never 11, and
  // **New York was never measured at any viewport**. Verified before the fix:
  // the distinct labels it printed were Bristol, Greater Manchester, Leicester,
  // London, Merseyside, South Yorkshire, Teesside, Tyne and Wear, West Midlands
  // and West Yorkshire, with zero mentions of New York.
  //
  // NYC is the one city with a different projection origin AND a different
  // boundary source, so it is the single city most likely to draw outside its
  // own box - and it was the one city exempt from the check written for that.
  //
  // `switchCountry` then `switchCity` rather than clicking a chip: this gate is
  // about GEOMETRY, and tests/city-switch.mjs already covers the chip as a
  // control. Both are page-scope function declarations, so they are reachable
  // from evaluate (a `let` like `currentCity` is not - it never becomes a
  // window property, which is why the switch is confirmed from the DOM below).
  const cities = await page.evaluate(() =>
    Object.entries(CITY_DATA).map(([id, d]) => ({ id, label: d.label, country: d.country }))
  );
  CITY_COUNT = cities.length;

  console.log(`\n# ${w}x${h}  ${label}`);
  for (const city of cities) {
    await page.evaluate((c) => switchCountry(c), city.country);
    await page.waitForTimeout(300);
    await page.evaluate((id) => switchCity(id), city.id);
    await page.waitForTimeout(1300);

    // CONFIRM THE SWITCH LANDED. The old loop did
    // `.click({force:true}).catch(() => {})` and then measured whatever was on
    // screen - so a chip that had stopped switching was measured as the
    // PREVIOUS city and printed ok under the new city's name. Read it back from
    // the rendered chip, not from a variable the fix would also set.
    const active = await page.evaluate(
      () => document.querySelector('.city-selector .city-btn.active')?.textContent?.trim() ?? ''
    );
    checks++;
    if (active !== city.label) {
      failures.push(`${w}x${h} ${city.label}: switch did not land (active chip reads "${active}")`);
      console.log(`  FAIL  ${city.label.padEnd(20)} switch did not land (active "${active}")`);
      continue;
    }

    const m = await page.evaluate(measure);
    if (m.error) {
      failures.push(`${w}x${h} ${city.label}: ${m.error}`);
      console.log(`  FAIL  ${city.label.padEnd(20)} ${m.error}`);
      continue;
    }
    const spill = Math.round(m.over.left + m.over.right + m.over.top + m.over.bottom);
    const fill = Math.max(m.geoW / m.boxW, m.geoH / m.boxH);
    const line = `${city.label.padEnd(20)} ${Math.round(m.geoW)}x${Math.round(m.geoH)} in ${Math.round(m.boxW)}x${Math.round(m.boxH)}  fill ${(fill * 100).toFixed(0)}%`;
    if (spill > 1) {
      const pct = (((m.over.left + m.over.right) / m.geoW) * 100).toFixed(1);
      failures.push(
        `${w}x${h} ${city.label}: ${spill}px outside the map box (${pct}% of width off-screen)`
      );
      console.log(`  FAIL  ${line}  SPILL ${spill}px`);
    } else if (fill < MIN_FILL) {
      failures.push(
        `${w}x${h} ${city.label}: fills only ${(fill * 100).toFixed(0)}% of the box, floor is ${MIN_FILL * 100}%`
      );
      console.log(`  FAIL  ${line}  TOO SMALL`);
    } else {
      console.log(`  ok    ${line}`);
    }
  }
  await ctx.close();
}
await browser.close();
server.close();

// A gate that compares nothing must fail, not pass. This repo has recorded four
// checks that reported agreement having measured none.
// The floor was `VIEWPORTS.length * 2` = 18 against a real 90 - global, so
// eight of nine viewports could contribute nothing and it still passed. It is
// now every city at every viewport, derived from the registry.
if (CITY_COUNT < 10) {
  console.error(`
FAIL: only ${CITY_COUNT} cities enumerated from CITY_DATA; expected at least 10.`);
  process.exit(1);
}
const EXPECTED_CHECKS = CITY_COUNT * VIEWPORTS.length;
if (checks < EXPECTED_CHECKS) {
  console.error(
    `\nFAIL: only ${checks} city/viewport combinations were measured; expected ${EXPECTED_CHECKS} (${CITY_COUNT} cities x ${VIEWPORTS.length} viewports).`
  );
  process.exit(1);
}

if (failures.length) {
  console.error(`\nFAIL: ${failures.length} of ${checks} combinations draw outside the map box or too small:`);
  for (const f of failures) console.error('  - ' + f);
  process.exit(1);
}
console.log(
  `\nEvery city fits the box it is drawn in: ${checks} city/viewport combinations, ${VIEWPORTS.length} viewports including landscape.`
);
