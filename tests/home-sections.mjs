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
import { devAnswer } from '../js/dev-demo.mjs';
import { readFileSync } from 'node:fs';
import { airPanel, answerLead, exampleFigures, noiseRows } from '../js/home-sections.mjs';
import { planesModel } from '../js/planes.mjs';

// /v1/environment for TW9 3PZ, as captured 2026-11-03 (trimmed to what the page reads).
const ENV = {
  roadNoiseLdenDb: 53.1, roadNoiseWhoGuidelineDb: 53, no2AnnualMeanUgm3: 16.3, no2WhoGuidelineUgm3: 10,
  pm25AnnualMeanUgm3: 8.4, pm25WhoGuidelineUgm3: 5, aircraftNoiseLdenDb: 56, aircraftQuietCoverage: 'modelled',
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

check('example tiles: the aircraft and air figures, from the answer', () => {
  const tiles = exampleFigures({ aircraftNoiseLdenDb: 57.2, aircraftNoiseWhoGuidelineDb: 45, no2AnnualMeanUgm3: 17 });
  assert.deepEqual(tiles, [{ figure: '57.2 dB', words: 'aircraft noise' }, { figure: '17 µg/m³', words: 'NO₂ in the air' }]);
});

check('example tiles: an estimate says it is one', () => {
  const [tile] = exampleFigures({ aircraftQuietCoverage: 'estimated', aircraftQuietEstimated: 7 });
  assert.equal(tile.figure, '3.0 / 10');
  assert.match(tile.words, /estimate from the routes, not measured/);
});

check('example tiles: a figure the answer lacks is no tile, never a zero', () => {
  assert.deepEqual(exampleFigures({ aircraftQuietCoverage: 'outside' }), []);
  assert.deepEqual(exampleFigures(null), []);
  assert.deepEqual(exampleFigures({ no2AnnualMeanUgm3: 0 }), [{ figure: '0 µg/m³', words: 'NO₂ in the air' }], 'a real zero stays');
});

const DEV = {
  location: { postcode: 'TW9 3PZ' },
  environment: { aircraftNoiseLdenDb: 57.2, roadNoiseLdenDb: 50.5, no2AnnualMeanUgm3: 17 },
  provenance: { 'environment.no2AnnualMeanUgm3': { sources: ['defra-pcm'], method: 'modelled', period: '2024' } },
  sourceIndex: { 'defra-pcm': { publisher: 'DEFRA' } },
};

check('developers band: the lines are valid JSON holding the response\'s own values', () => {
  const { lines } = devAnswer(DEV);
  assert.deepEqual(JSON.parse(lines.join('\n')), { location: DEV.location, environment: DEV.environment });
});

check('developers band: each figure says who made it and how, from the response\'s provenance', () => {
  const { figures } = devAnswer(DEV);
  assert.deepEqual(figures.map((f) => f.figure), ['57.2 dB', '50.5 dB', '17 µg/m³']);
  assert.equal(figures[2].credit, 'DEFRA, modelled, 2024');
  assert.equal(figures[0].credit, '', 'no provenance, no credit: never a guessed one');
});

check('developers band: a value the answer lacks is no line and no tile, never a zero', () => {
  const dev = devAnswer({ environment: { no2AnnualMeanUgm3: 17 } });
  assert.deepEqual(dev.figures.map((f) => f.key), ['no2AnnualMeanUgm3']);
  assert.deepEqual(JSON.parse(dev.lines.join('\n')), { environment: { no2AnnualMeanUgm3: 17 } });
  assert.equal(devAnswer({ environment: {} }), null);
  assert.equal(devAnswer(null), null);
});

// OPTION C, THE ANSWER AS THE HEADLINE (review prototype, 2026-11-07): what the hero's h1 says once an answer is on show,
// held on real answers (tests/fixtures/api-demo-env.json, saved from the live route 2026-11-05). The planes lead when they
// may (js/planes.mjs planesLead, held in tests/planes-model.mjs); then DEFRA's aircraft noise; then the planes as the layer's
// blank band (planesBandLead); then road noise, only with no planes data at all; air and the routes' estimate never;
// nothing true to lead with keeps the question (null).
const REAL = JSON.parse(readFileSync(new URL('./fixtures/api-demo-env.json', import.meta.url), 'utf8'));
const real = (key) => [REAL[key].env.environment, REAL[key].geo.postcode];
const LEAD_INFO = {
  classes: ['westerly', 'easterly', 'mixed'], bar_full: 629,
  airports: { LHR: { share_pct: { westerly: 56, easterly: 29, mixed: 15 }, months: ['202601', '202608'] } },
  definition: 'Overhead means more than halfway up the sky.', direction_rule: '', credits: [],
};
// The full map's planes layer steps (data/planes-layer/index.json, scripts/build_planes_layer.py), as built 2026-11-02.
const LAYER = [{ step: 1, from: 10, colour: '#dc8a4a' }, { step: 2, from: 50, colour: '#c2622a' }, { step: 3, from: 100, colour: '#9a4316' }, { step: 4, from: 200, colour: '#662809' }];
const planesAt = (pc, figs) => planesModel({ postcodes: { [pc]: { LHR: figs } }, none: [], approx: [], other: [] }, LEAD_INFO, pc, { LHR: 'Heathrow' });
const kewPlanes = planesAt('TW9 3PZ', [310, 4, 168]);

check('headline: the example leads with its planes; without them, with DEFRA\'s aircraft noise against the WHO guideline', () => {
  const [e, pc] = real('TW93PZ');
  assert.equal(answerLead(e, pc, kewPlanes, LAYER), 'On most days, about 310 Heathrow planes a day pass over TW9 3PZ');
  assert.equal(answerLead(e, pc, null, LAYER), 'Aircraft noise at TW9 3PZ is over the WHO guideline');
  assert.equal(answerLead(e, pc, kewPlanes, []), 'Aircraft noise at TW9 3PZ is over the WHO guideline', 'no layer steps: the planes never lead');
});

check('headline: the planes question before road noise: SW5 9HP\'s few planes lead as the layer\'s blank band', () => {
  // SW5 9HP's real district file: 4, under 1 and 3 a day (2026-11-07); road 71.8 dB against 53. Bill, 2026-11-07.
  const [e, pc] = real('SW59HP');
  assert.equal(answerLead(e, pc, planesAt(pc, [4, '<1', 3]), LAYER), 'Fewer than 10 Heathrow planes a day pass over SW5 9HP');
  assert.equal(answerLead(e, pc, planesAt(pc, [4, '<1', 3]), []), null, 'no layer steps: no band to say, and the roads still wait for the planes');
});

check('headline: DEFRA\'s aircraft noise comes before the quiet band, so a postcode off a flight path is never headlined as quiet', () => {
  const [e, pc] = real('TW93PZ');
  assert.equal(answerLead(e, pc, planesAt(pc, [4, 2, 3]), LAYER), 'Aircraft noise at TW9 3PZ is over the WHO guideline');
});

check('headline: road noise leads only where we hold no planes data at all', () => {
  const [e, pc] = real('SW59HP');
  assert.equal(answerLead(e, pc, planesAt(pc, [[5, 40], 3, 2]), LAYER), null, 'planes held but none can lead (a range reaching the step): the question, never the roads');
  assert.equal(answerLead(e, pc, planesAt(pc, [4, null, 3]), LAYER), null, 'a kind of day not measured is not "fewer than"');
});

check('headline: no planes data, no aircraft figure, so road noise leads; a surveyed-quiet road is under the guideline, never missing', () => {
  assert.equal(answerLead(...real('SW59HP')), 'Road noise at SW5 9HP is over the WHO guideline', 'the routes\' estimate never leads');
  assert.equal(answerLead(...real('NG118AH')), 'Road noise at NG11 8AH is under the WHO guideline');
  assert.equal(answerLead({ roadNoiseLdenDb: 53, roadNoiseWhoGuidelineDb: 53 }, 'SW1A 1AA'), 'Road noise at SW1A 1AA is level with the WHO guideline');
});

check('headline: outside our city regions, with only air figures, it keeps the question; so does no answer', () => {
  assert.equal(answerLead(...real('EX11HS')), null, 'air never leads, and the outside estimate is no finding');
  assert.equal(answerLead({ roadNoiseBelowDb: 60, roadNoiseWhoGuidelineDb: 53 }, 'SW1A 1AA'), null, 'a bound above the guideline says nothing either way');
  assert.equal(answerLead(null, 'TW9 3PZ'), null);
  assert.equal(answerLead({}, 'TW9 3PZ'), null);
  for (const key of ['TW93PZ', 'SW59HP', 'M11AE', 'NG118AH']) {
    const [e, pc] = real(key);
    assert.doesNotMatch(answerLead(e, pc).replace(pc, ''), /measured|\d/, 'words, never a figure of its own (the postcode aside)');
  }
});

console.log(`home sections: ${passed} checks passed`);
