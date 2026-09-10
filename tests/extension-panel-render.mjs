// Renders the extension's Environment section from documented /v1/environment
// shapes and asserts what the reader sees. No Rightmove, no API, no service
// worker.
//
// WHY THIS EXISTS (2026-09-10). /v1/environment gained a second road-noise
// state: `roadNoiseBelowDb`, a BOUND for ground DEFRA surveyed and found under
// the lowest level its map records (40 dB) - 2.0% of covered postcodes, every
// one of them quiet, previously reported as "not measured". panel.js renders
// it as "< 40 dB Lden" with the dot at the bound. Nothing could gate that:
// tests/extension-e2e.mjs drives real saved listings against the LIVE endpoint
// on purpose, its two fixtures sit on postcodes with a reading, a listing at a
// surveyed-quiet postcode cannot be manufactured (self-authored fixtures are
// circular here), and the fetch runs in the background service worker with a
// six-hour cache, which page.route() does not reach.
//
// So this loads panel.js into a blank page with its boot call stripped and a
// stub `chrome`, and calls renderEnvironment() with each documented shape. It
// tests the PANEL, not the API - the API side is held by RoadSurveyedQuietTests
// in backend/tests/test_score.py. The two together cover the path.
//
// Proven red against the pre-change panel.js (3a07bdf): "bound renders as < 40"
// fails because that panel had no row for a value that is not roadNoiseLdenDb.
//
//   node tests/extension-panel-render.mjs
//   PANEL_JS=path/to/other/panel.js node tests/extension-panel-render.mjs

import { chromium } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { readFileSync } from 'node:fs';

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = process.env.PANEL_JS || join(HERE, '..', 'extension', 'content', 'panel.js');

// The content script boots itself on load (a setInterval poll and a final
// `run();`). Strip the boot call only; everything above it is the library
// under test. If the tail ever changes shape this throws, which is right - a
// silently un-stripped boot would try to extract a listing from about:blank.
const raw = readFileSync(SOURCE, 'utf8');
const bootIdx = raw.lastIndexOf('\nrun();');
if (bootIdx === -1) throw new Error(`${SOURCE}: expected a trailing run(); boot call`);
const src = raw.slice(0, bootIdx);

const results = [];
const check = (name, ok, detail = '') => results.push([name, ok, detail]);

const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto('about:blank');
await page.addScriptTag({
  content: `
    window.chrome = { runtime: { sendMessage: () => Promise.resolve({ ok: false }), getURL: (p) => p } };
    ${src}
    window.__render = (env, notices) =>
      renderEnvironment({ ok: true, data: { environment: env, notices: notices || [] } });
  `,
});

const ROAD_SOURCE = 'DEFRA Strategic Noise Mapping Round 4, road Lden. Published 2022, maps 2021.';

// Reads the rendered section back as the facts a reader would take from it.
async function render(env, notices) {
  return page.evaluate(
    ([e, n]) => {
      // The section is a live element the panel built; read it in place.
      const box = window.__render(e, n);
      const rows = [...box.querySelectorAll('.c33-item')].map((item) => ({
        name: (item.querySelector('.c33-name')?.textContent || '').trim(),
        readout: (item.querySelector('.c33-dist')?.textContent || '').trim(),
        readoutClass: item.querySelector('.c33-dist')?.className || '',
        bar: item.querySelector('.c33-bar')?.getAttribute('aria-label') || '',
        note: (item.querySelector('.c33-rownote')?.textContent || '').trim(),
      }));
      return rows;
    },
    [env, notices]
  );
}

// 1. The bound: what 2.0% of covered postcodes now return.
{
  const rows = await render({
    roadNoiseBelowDb: 40.0,
    roadNoiseWhoGuidelineDb: 53,
    roadNoiseSource: ROAD_SOURCE,
  });
  const road = rows.filter((r) => /^Road noise/.test(r.name));
  check('bound: exactly one Road noise row', road.length === 1, JSON.stringify(rows.map((r) => r.name)));
  const r = road[0] || {};
  check('bound renders as < 40 dB Lden', r.readout === '< 40 dB Lden', r.readout);
  check('bound is coloured as within the guideline', /c33-under/.test(r.readoutClass), r.readoutClass);
  check(
    'bound: the bar says "< 40" to a screen reader too',
    /^< 40 dB Lden, within the WHO guideline of 53 dB Lden$/.test(r.bar),
    r.bar
  );
  check('bound: the note says quiet, not missing', /quiet reading, not a missing one/i.test(r.note), (r.note || '').slice(0, 80));
  check('bound: the 2021 vintage tag rides the row', /2021/.test(r.name), r.name);
}

// 2. A reading: the shape every postcode with a value has always had.
{
  const rows = await render({
    roadNoiseLdenDb: 56.3,
    roadNoiseWhoGuidelineDb: 53,
    roadNoiseSource: ROAD_SOURCE,
  });
  const road = rows.filter((r) => /^Road noise/.test(r.name));
  check('reading: exactly one Road noise row', road.length === 1, JSON.stringify(rows.map((r) => r.name)));
  check('reading renders without a prefix', road[0]?.readout === '56.3 dB Lden', road[0]?.readout);
  check('reading over the guideline is coloured over', /c33-over/.test(road[0]?.readoutClass || ''), road[0]?.readoutClass);
  check('reading: no surveyed-quiet note', !/quiet reading/i.test(road[0]?.note || ''), road[0]?.note);
}

// 3. Both present: a reading is what DEFRA mapped; the bound is history.
{
  const rows = await render({
    roadNoiseLdenDb: 56.3,
    roadNoiseBelowDb: 40.0,
    roadNoiseWhoGuidelineDb: 53,
    roadNoiseSource: ROAD_SOURCE,
  });
  const road = rows.filter((r) => /^Road noise/.test(r.name));
  check('both: one row, the reading, never two', road.length === 1 && road[0].readout === '56.3 dB Lden', JSON.stringify(road.map((r) => r.readout)));
}

// 4. Neither: absence stays absence. A row here would be a reading nobody took.
{
  const rows = await render({ no2AnnualMeanUgm3: 12.0, no2WhoGuidelineUgm3: 10 });
  check('neither: no Road noise row at all', !rows.some((r) => /^Road noise/.test(r.name)), JSON.stringify(rows.map((r) => r.name)));
}

await browser.close();

let failed = 0;
for (const [name, ok, detail] of results) {
  if (!ok) failed += 1;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `   [${detail}]` : ''}`);
}
console.log(failed === 0 ? `\n${results.length} checks passed.` : `\n${failed} of ${results.length} FAILED.`);
process.exit(failed === 0 ? 0 : 1);
