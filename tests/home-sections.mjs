// What the front page's walkthrough says in its noise and air steps (js/home-sections.mjs noiseRows, airPanel), held
// without a browser. The planes step is js/planes.mjs planesWalk, held in tests/planes-model.mjs.
//
// WHY THIS EXISTS (front-page-v3, 2026-11-03). The walkthrough below the map SHOWS what a search gives, with the
// example's own answer, so no figure is ever typed into the page. The rules a reader relies on: a DEFRA map reading is
// drawn against its WHO guideline and called modelled, never measured; the routes' estimate is turned round to read as
// noise and said to be an estimate; DEFRA's air model joins the chart only when the API's provenance calls it modelled;
// nothing at all is shown where nothing was answered.
//
//   node tests/home-sections.mjs

import assert from 'node:assert/strict';
import { airPanel, noiseRows } from '../js/home-sections.mjs';

// /v1/environment for TW9 3PZ, as captured 2026-11-03 (trimmed to what the page reads).
const ENV = {
  roadNoiseLdenDb: 53.1, roadNoiseWhoGuidelineDb: 53, no2AnnualMeanUgm3: 16.3, no2WhoGuidelineUgm3: 10,
  pm25AnnualMeanUgm3: 8.4, pm25WhoGuidelineUgm3: 5, aircraftNoiseLdenDb: 56, aircraftQuietCoverage: 'measured',
  aircraftNoiseWhoGuidelineDb: 45,
};
const PROV = {
  'environment.aircraftNoiseLdenDb': { method: 'modelled', resolution: 'read at the postcode', period: '2021' },
  'environment.no2AnnualMeanUgm3': { method: 'modelled', resolution: '1 km grid', period: '2024' },
};
const SENSOR = { name: 'George Street', km: 2.2, no2: { mean: 18.7 }, credit: { text: 'Contains Breathe London data', href: 'https://example.org/bl' } };
const MONITOR = { name: 'Richmond Upon Thames', km: 4.1, pm25: { mean: 7 }, credit: { text: 'DEFRA AURN', href: 'https://example.org/aurn' } };

let passed = 0;
const check = (name, fn) => { fn(); passed += 1; console.log(`  ok  ${name}`); };

check('noise: aircraft and road against their WHO guidelines, DEFRA modelled with its year', () => {
  const n = noiseRows(ENV, PROV);
  assert.deepEqual(n.rows.map((r) => [r.label, r.figure, r.mark]), [['Aircraft', '56 dB', 50], ['Road', '53.1 dB', 50]]);
  assert.equal(n.rows[0].width.toFixed(1), (56 / 90 * 100).toFixed(1));
  assert.equal(n.note, "The line is the WHO guideline: 45 dB for aircraft and 53 dB for road, Lden. DEFRA's noise maps, modelled, 2021.");
  assert.doesNotMatch(n.note, /measured/);
});

check('noise: the routes\' estimate is a score turned round and said so; quiet road ground is a bound, not missing', () => {
  const n = noiseRows({ aircraftQuietEstimated: 9, aircraftQuietCoverage: 'city', roadNoiseBelowDb: 55 }, {});
  assert.deepEqual(n.rows.map((r) => [r.label, r.figure, r.sub, r.mark]), [
    ['Aircraft', '1.0 / 10', 'estimate from the routes, not measured', null],
    ['Road', 'under 55 dB', 'surveyed, below the lowest band', null],
  ]);
  assert.equal(n.note, '');
});

check('noise: outside every city, or nothing answered, shows nothing at all', () => {
  assert.equal(noiseRows({ aircraftQuietEstimated: 10, aircraftQuietCoverage: 'outside' }, {}), null);
  assert.equal(noiseRows(null), null);
});

check('air: DEFRA\'s model beside the sensor and the monitor, on one scale with the WHO line', () => {
  const a = airPanel(ENV, PROV, SENSOR, MONITOR);
  assert.match(a.svg, /data-air-chart="no2"/);
  const kinds = [...a.svg.matchAll(/data-kind="(\w+)" data-value="([\d.]*)"/g)].map((m) => [m[1], m[2]]);
  assert.deepEqual(kinds, [['model', '16.3'], ['sensor', '18.7'], ['monitor', '']], 'the monitor measures no NO2 here: no mark');
  assert.match(a.svg, /this 1 km square · 2024/);
  assert.deepEqual(a.credits.map((c) => c.text), ['Contains Breathe London data', 'DEFRA AURN']);
});

check('air: no provenance, no model row (never a figure the API did not call modelled)', () => {
  const a = airPanel(ENV, {}, SENSOR, null);
  assert.deepEqual([...a.svg.matchAll(/data-kind="(\w+)"/g)].map((m) => m[1]), ['sensor']);
  assert.equal(airPanel(ENV, {}, null, null), null);
  assert.equal(airPanel(null, PROV, null, MONITOR), null, 'a monitor with no NO2 and nothing else: nothing shown');
});

check('air: a hostile name is escaped inside the chart', () => {
  const a = airPanel(ENV, PROV, { ...SENSOR, name: '<img src=x onerror=alert(1)>' }, null);
  assert.doesNotMatch(a.svg, /<img/);
});

console.log(`home sections: ${passed} checks passed`);
