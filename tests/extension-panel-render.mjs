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

// 5. Air measured nearby (2026-11-18, Bill's pick A): a block UNDER the modelled rows. The block is the API's own
// answer for the SW5 listing the e2e uses (build_air_nearby at 51.49423, -0.18825 on the 13 Nov files); the API side
// is held by backend/tests/test_air_nearby.py, which runs the site's own nearestSensor/nearestMonitor against it.
const SW5_NEARBY = {
  scopeKm: 5,
  sensor: {
    network: 'Breathe London', siteCode: 'BL0118', name: 'Kensington High Street', distanceKm: 0.88,
    setting: 'roadside', kerbDistanceM: 0.9, no2MeanUgm3: 18.3, pm25MeanUgm3: 7.1,
    period: { from: '2025-11-01', to: '2026-10-31' },
    note: 'Display only, never scored.',
    source: 'Contains Breathe London data licensed under the Open Government License v3.0',
    sourceLink: 'https://www.breathelondon.org/',
  },
  monitor: {
    network: 'DEFRA AURN', siteCode: 'KC1', name: 'London N. Kensington', distanceKm: 3.45,
    setting: 'urban background', no2MeanUgm3: 15.4, pm25MeanUgm3: 7.2,
    period: { from: '2024-01-01', to: '2024-12-31' },
    note: 'Display only, never scored.',
    source: '© Crown 2026 copyright Defra via uk-air.defra.gov.uk, licenced under the Open Government Licence (OGL).',
    sourceLink: 'https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/',
  },
};
const MODELLED = { no2AnnualMeanUgm3: 24.0, no2WhoGuidelineUgm3: 10, pm25AnnualMeanUgm3: 9.6, pm25WhoGuidelineUgm3: 5 };

async function nearbyView(env) {
  return page.evaluate((e) => {
    const box = window.__render(e, []);
    const block = box.querySelector('.c33-nearby');
    const notes = [...box.querySelectorAll('.c33-note-body')];
    return {
      heading: block?.querySelector('h4')?.textContent || null,
      blockIsLast: block ? block.previousElementSibling?.matches('ul.c33-list') && !block.querySelector('.c33-bar') : null,
      modelled: [...box.querySelectorAll(':scope > ul.c33-list > .c33-item .c33-name')].map((n) => n.textContent.trim()),
      items: block
        ? [...block.querySelectorAll('.c33-item')].map((i) => ({
            name: i.querySelector('.c33-name')?.textContent,
            dist: i.querySelector('.c33-dist')?.textContent,
            sub: i.querySelector('.c33-rownote')?.textContent,
            vals: i.querySelector('.c33-vals')?.textContent,
          }))
        : [],
      fold: box.querySelector('.c33-note-sum')?.textContent || '',
      links: notes.flatMap((p) => [...p.querySelectorAll('a')].map((a) => ({ text: a.textContent, href: a.getAttribute('href'), rel: a.rel, target: a.target }))),
      foldText: notes.map((p) => p.textContent).join(' | '),
      text: box.textContent,
      html: box.innerHTML,
    };
  }, env);
}

{
  const v = await nearbyView({ ...MODELLED, airMeasuredNearby: SW5_NEARBY });
  check('nearby: one "Measured nearby" heading', v.heading === 'Measured nearby', v.heading);
  check('nearby: the modelled rows are unchanged', JSON.stringify(v.modelled) === JSON.stringify(['Nitrogen dioxide', 'Fine particles (PM2.5)']), JSON.stringify(v.modelled));
  check('nearby: sits under the modelled rows, with no bar', v.blockIsLast === true);
  check('nearby: sensor first, then monitor', v.items.map((i) => i.name).join(' / ') === 'Kensington High Street / London N. Kensington', JSON.stringify(v.items.map((i) => i.name)));
  check('nearby: distances as the site words them', v.items.map((i) => i.dist).join(' / ') === '880 m / 3.5 km', JSON.stringify(v.items.map((i) => i.dist)));
  check('nearby: the sensor names its network and setting', v.items[0]?.sub === 'Breathe London sensor · roadside, 0.9 m from the kerb', v.items[0]?.sub);
  check('nearby: the monitor names its network and setting', v.items[1]?.sub === 'DEFRA monitor · urban background', v.items[1]?.sub);
  check('nearby: the sensor readings and period', v.items[0]?.vals === 'NO2 18.3 · PM2.5 7.1 ug/m3 · 12 months to Oct 2026', v.items[0]?.vals);
  check('nearby: the monitor readings and year', v.items[1]?.vals === 'NO2 15.4 · PM2.5 7.2 ug/m3 · 2024', v.items[1]?.vals);
  check('nearby: the fold counts the two lines it gained', /\(2\)$/.test(v.fold.trim()), v.fold);
  check('nearby: each credit word for word, linked to its address', v.links.length === 2
    && v.links[0].text === SW5_NEARBY.sensor.source && v.links[0].href === SW5_NEARBY.sensor.sourceLink
    && v.links[1].text === SW5_NEARBY.monitor.source && v.links[1].href === SW5_NEARBY.monitor.sourceLink, JSON.stringify(v.links));
  check('nearby: links open apart and send nothing back', v.links.every((l) => l.target === '_blank' && /noopener/.test(l.rel) && /noreferrer/.test(l.rel)));
  check('nearby: never ranked, and says so', /not ranked/.test(v.foldText), v.foldText.slice(0, 120));
}

{
  const v = await nearbyView({ ...MODELLED, airMeasuredNearby: { scopeKm: 5, monitor: SW5_NEARBY.monitor } });
  check('nearby, monitor only: one line, the monitor', v.items.length === 1 && v.items[0].name === 'London N. Kensington', JSON.stringify(v.items));
  check('nearby, monitor only: one credit', v.links.length === 1 && v.links[0].href === SW5_NEARBY.monitor.sourceLink, JSON.stringify(v.links));
}

{
  const v = await nearbyView({ ...MODELLED });
  check('no block: no heading, no lines', v.heading === null && v.items.length === 0);
  check('no block: nothing says "none nearby"', !/none nearby|no sensor|no monitor/i.test(v.text), v.text.slice(0, 120));
  check('no block: the fold gains nothing', !/not ranked/.test(v.foldText));
}

{
  const noReading = { ...SW5_NEARBY.monitor };
  delete noReading.no2MeanUgm3;
  delete noReading.pm25MeanUgm3;
  const v = await nearbyView({ ...MODELLED, airMeasuredNearby: { scopeKm: 5, monitor: noReading } });
  check('an entry with no reading draws nothing', v.heading === null && v.items.length === 0, JSON.stringify(v.items));
}

{
  const hostile = {
    scopeKm: 5,
    sensor: { ...SW5_NEARBY.sensor, name: '<img src=x onerror="window.__pwned=1">', sourceLink: 'javascript:window.__pwned=1' },
  };
  const v = await nearbyView({ ...MODELLED, airMeasuredNearby: hostile });
  const pwned = await page.evaluate(() => window.__pwned === 1);
  check('hostile text is text, never markup', !/<img/i.test(v.html.replace(/&lt;img/g, '')) && v.items[0]?.name === hostile.sensor.name && !pwned);
  check('a link that is not https stays text', v.links.length === 0 && v.foldText.includes(hostile.sensor.source), JSON.stringify(v.links));
}

{
  // Audit 2026-11-19 M-5: an https credit link to any host but the publisher's own stays text, as the API refuses it.
  const elsewhere = {
    scopeKm: 5,
    sensor: { ...SW5_NEARBY.sensor, sourceLink: 'https://example.org/breathe' },
    monitor: { ...SW5_NEARBY.monitor, sourceLink: 'https://www.nationalarchives.gov.uk.example.org/' },
  };
  const v = await nearbyView({ ...MODELLED, airMeasuredNearby: elsewhere });
  check("a credit linking anywhere but its publisher's own site stays text", v.links.length === 0
    && v.foldText.includes(elsewhere.sensor.source) && v.foldText.includes(elsewhere.monitor.source), JSON.stringify(v.links));
}

{
  // 2026-11-27 (the LICENSING.md review): /v1/environment sends no `sources` list. Since per-field provenance went live
  // (2026-10-29) it names each source in `sourceIndex`, but the footer read only `sources`, so the Environment section
  // showed no OGL line while its EPC, sold-price and NHS siblings did.
  const foot = await page.evaluate(() => {
    const env = { ok: true, data: { environment: {}, sourceIndex: {
      'defra-pcm': { publisher: 'DEFRA', dataset: 'Background pollution maps (PCM), annual mean NO2 and PM2.5', licence: 'Open Government Licence v3.0', method: 'modelled' },
      'who-aq-2021': { publisher: 'World Health Organization', dataset: 'Global air quality guidelines (2021)', method: 'reference' },
    } } };
    const epc = { ok: true, data: { sources: ['EPC data: MHCLG, Open Government Licence v3.0'], sourceIndex: { x: { publisher: 'Not this', dataset: 'a response with its own sources list' } } } };
    const f = renderSources([env, epc]);
    return f ? [...f.children].map((d) => d.textContent) : null;
  });
  check('footer: /v1/environment is credited from its sourceIndex', !!foot && foot.includes('DEFRA: Background pollution maps (PCM), annual mean NO2 and PM2.5. Open Government Licence v3.0'), JSON.stringify(foot));
  check('footer: a source with no licence is named, never given one', !!foot && foot.includes('World Health Organization: Global air quality guidelines (2021)'), JSON.stringify(foot));
  check("footer: a response's own sources list is used, not its sourceIndex", !!foot && foot.includes('EPC data: MHCLG, Open Government Licence v3.0') && !foot.some((l) => l.startsWith('Not this')), JSON.stringify(foot));
}

await browser.close();

let failed = 0;
for (const [name, ok, detail] of results) {
  if (!ok) failed += 1;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `   [${detail}]` : ''}`);
}
console.log(failed === 0 ? `\n${results.length} checks passed.` : `\n${failed} of ${results.length} FAILED.`);
process.exit(failed === 0 ? 0 : 1);
