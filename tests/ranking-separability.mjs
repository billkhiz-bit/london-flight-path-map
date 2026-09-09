/**
 * The borough ranking must not present an ordering the scores cannot support.
 *
 * Methodology v5.0 moved affordability to a national anchor, which removed
 * spread that within-city min-max had MANUFACTURED. Measured across all
 * thirteen cities the day it shipped: composite spread fell in twelve, and
 * South Yorkshire went from 2.3 points to 0.1 with three of its four boroughs
 * sharing a published score. A numbered list of four boroughs differing by 0.1
 * claims an ordering the data does not have - the same over-claim as the "best
 * value" label on a price-led ranking, whose disclosure sits beside this one.
 *
 * WHAT THIS ASSERTS, AND WHY IT IS NOT A SNAPSHOT. It does not pin which cities
 * disclose - a golden list goes stale the day coverage changes. It asserts the
 * RELATIONSHIP: a city discloses if and only if its RENDERED scores are too
 * close to rank, recomputed here from the DOM rather than read off the page's
 * own flag. A gate that reads the boolean the fix sets agrees with the fix's
 * own bugs.
 *
 * Usage:
 *     node tests/ranking-separability.mjs
 */
import { chromium } from '@playwright/test';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';

const ROOT = process.cwd();
const PORT = 8926;
const TYPES = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.json': 'application/json',
  '.css': 'text/css',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.webmanifest': 'application/manifest+json',
};
// The precision these scores are published at. The disclosure's threshold is
// DERIVED from this rather than chosen, and that is the point: if adjacent
// boroughs differ by less than one rounding step, their order is an artefact of
// rounding. The `priceLed` 0.60 sitting a few lines from it in index.html is a
// standing warning about picking a number instead, and it has expired once.
const SCORE_PRECISION = 0.1;

const server = createServer(async (req, res) => {
  const raw = decodeURIComponent(req.url.split('?')[0]);
  const p = join(ROOT, normalize(raw === '/' ? '/index.html' : raw));
  if (!p.startsWith(ROOT)) return res.writeHead(403).end();
  try {
    // Read BEFORE writing the header - see the note in locator-verify.mjs.
    const body = await readFile(p);
    res.writeHead(200, { 'content-type': TYPES[extname(p)] || 'application/octet-stream' });
    res.end(body);
  } catch {
    res.writeHead(404).end();
  }
});
await new Promise((r) => server.listen(PORT, r));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const pageErrors = [];
page.on('pageerror', (e) => pageErrors.push(String(e.message).slice(0, 120)));
await page.goto(`http://localhost:${PORT}/index.html`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1500);

// Bare `CITY_DATA`, not `window.CITY_DATA`: it is a top-level `const` in a
// classic script, so it lives in the global LEXICAL scope and never becomes a
// property of `window`. Reading it off `window` returns undefined and makes
// this report "no cities" on a healthy page. Same access city-switch.mjs uses.
const cities = await page.evaluate(() => Object.keys(CITY_DATA));

// TWO STATES MUST BE REACHED BEFORE ANYTHING IS MEASURABLE, and missing either
// gives a gate that passes while looking at nothing:
//
//   1. `#borough-ranking` sits inside `#tab-ranking`, which ships
//      `display: none` - the same shape as a11y-source.mjs having to reveal the
//      legend and panel-caveat.mjs having to open the sidebar.
//   2. `rankingView` defaults to 'neighbourhood', whose scores come from
//      WITHIN-CITY neighbourhood prices and are therefore untouched by the
//      national anchor. Stopping at the tab measures the one view this
//      disclosure does not apply to.
await page.click('#tab-btn-ranking');
await page.waitForTimeout(400);
await page.evaluate(() => {
  if (rankingView !== 'borough') toggleRankingView();
});
await page.waitForTimeout(600);
const view = await page.evaluate(() => rankingView);
if (view !== 'borough') {
  console.error(`FAIL: could not reach the borough view (rankingView=${view}).`);
  await browser.close();
  server.close();
  process.exit(1);
}

// Scoped to the cities the DEFAULT country renders, and the exclusion is stated
// rather than hidden: the switcher is two tiers, so New York's chip does not
// exist while the UK tab is active. Every collapse lives in the UK cities -
// New York's five boroughs span 4.0 points and are the one cohort the national
// anchor did not compress.
const chips = await page.evaluate(() =>
  [...document.querySelectorAll('.city-btn[data-city]')].map((b) => b.dataset.city)
);

const failures = [];
const rows = [];
for (const city of chips) {
  await page.locator(`.city-btn[data-city="${city}"]`).click({ force: true });
  await page.evaluate(() => {
    if (rankingView !== 'borough') toggleRankingView();
  });

  // POLL FOR THE TARGET STATE, NOT ONE THAT IS ALREADY TRUE. This is the whole
  // reason an earlier version of this file was abandoned as unworkable. It
  // waited for "more than one score cell exists", which the PREVIOUS city's
  // table already satisfied, so every reading came back one city stale - and
  // two cities with the same borough count (Merseyside and Tyne and Wear both
  // have five) alias even if you also compare counts. Waiting on the rendered
  // NAMES belonging to the target city cannot alias.
  let stalled = '';
  try {
    await page.waitForFunction(
      (want) => {
        if (currentCity !== want || rankingView !== 'borough') return false;
        const held = Object.keys(scoredBoroughs(want));
        const drawn = [...document.querySelectorAll('#borough-ranking tbody tr[data-rank-name]')]
          .map((tr) => tr.dataset.rankName);
        return drawn.length === held.length && drawn.every((n) => held.includes(n));
      },
      city,
      { timeout: 15000 }
    );
  } catch {
    stalled = ' (never reached its own borough set)';
  }

  const seen = await page.evaluate(() => {
    // The cell renders `<span aria-hidden>GLYPH</span> 7.9`, so a bare
    // parseFloat hits the glyph and returns NaN for every row - which reads as
    // "the ranking did not draw" and sent an earlier version of this file
    // chasing a rendering bug that did not exist. Take the trailing number.
    const cells = [...document.querySelectorAll('#borough-ranking td.col-score')];
    const scores = cells
      .map((td) => {
        const m = (td.textContent || '').match(/(\d+(?:\.\d+)?)\s*$/);
        return m ? parseFloat(m[1]) : NaN;
      })
      .filter((n) => Number.isFinite(n));
    const note = document.getElementById('borough-ranking')?.textContent || '';
    return { scores, disclosed: note.includes('too close to rank'), view: rankingView };
  });

  if (seen.view !== 'borough' || seen.scores.length < 2) {
    failures.push(
      `${city}: ${seen.scores.length} score(s) in the ${seen.view} view${stalled}` +
        (pageErrors.length ? ` - page error: ${pageErrors[pageErrors.length - 1]}` : '')
    );
    continue;
  }

  const spread = Math.max(...seen.scores) - Math.min(...seen.scores);
  const meanGap = spread / (seen.scores.length - 1);
  const shouldDisclose = meanGap < SCORE_PRECISION;
  rows.push(
    `  ${city.padEnd(16)} n=${String(seen.scores.length).padStart(2)}  spread ${spread.toFixed(1)}` +
      `  mean gap ${meanGap.toFixed(3)}  ${seen.disclosed ? 'DISCLOSED' : '-'}`
  );

  if (shouldDisclose && !seen.disclosed) {
    failures.push(
      `${city}: boroughs are ${spread.toFixed(1)} apart (mean gap ${meanGap.toFixed(3)} < ` +
        `${SCORE_PRECISION}) and the ranking claims an order anyway`
    );
  }
  if (!shouldDisclose && seen.disclosed) {
    failures.push(
      `${city}: mean gap ${meanGap.toFixed(3)} is above ${SCORE_PRECISION}, so this ranking IS ` +
        'separable, but the page says it is not - a caveat where none is due is its own false claim'
    );
  }
}

console.log('Borough ranking separability');
console.log('============================');
console.log(rows.join('\n'));

// Per-unit floors. A run that drew no table, or that lost most of the chips,
// passes every comparison above by making none of them.
if (rows.length < 10) {
  failures.push(`only ${rows.length} cities produced a ranking; expected every UK city to draw one`);
}
if (chips.length < cities.length - 1) {
  failures.push(`only ${chips.length} chips rendered against ${cities.length} cities in the registry`);
}

await browser.close();
server.close();

if (failures.length) {
  console.error(`\nFAIL: ${failures.length} problem(s)`);
  for (const f of failures) console.error(`  - ${f}`);
  process.exit(1);
}
console.log(
  `\nPASS: ${rows.length} cities; every ranking discloses exactly when its scores cannot be separated.`
);
