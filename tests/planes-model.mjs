// What one postcode is told about planes overhead (js/planes.mjs planesModel), from district files shaped as
// scripts/build_planes_overhead.py writes them (tests/test_build_planes_overhead.py holds that side).
//
// WHY THIS EXISTS (2026-10-26). The front page's answer gains "Planes overhead", told by the way each airport
// flies (Bill, 25 Oct). The rules a reader relies on live in planesModel, so they are held here without a
// browser: rows in the mock-up's order (west, both ways, east) whatever the file's order; a range on a cone's
// edge, said so; a kind of day with no figure "not measured", never 0; a postcode measured with nothing reaching
// 1 a day told so, and one never measured told NOTHING (null: the block stays hidden); an airport the
// airports.json does not publish never shown; the position and uncounted-traffic warnings.
//
//   node tests/planes-model.mjs

import assert from 'node:assert/strict';
import { districtOf, period, perDay, planesModel } from '../js/planes.mjs';

const NAMES = { LHR: 'Heathrow', LCY: 'London City', MAN: 'Manchester' };
const INFO = {
  classes: ['westerly', 'easterly', 'mixed'],
  districts: ['TW3', 'TW9', 'E16'],
  bar_full: 400,
  definition: 'Overhead means more than halfway up the sky (48.5 degrees or more) and below 7,000 ft, the CAA\'s definition of an overflight (CAP 1498).',
  direction_rule: 'A day counts as one way when 80% of its flights used that way.',
  airports: {
    LHR: { share_pct: { westerly: 56, easterly: 29, mixed: 15 }, months: ['202601', '202608'] },
    LCY: { share_pct: { westerly: 47, easterly: 35, mixed: 18 }, months: ['202601', '202608'] },
  },
  credits: ['Flight tracks: adsb.lol (ODbL 1.0)'],
};
const TW9 = { district: 'TW9', postcodes: { 'TW9 3PZ': { LHR: [310, 4, 168] } }, none: ['TW9 9ZZ'], approx: [], other: [] };
const TW3 = { district: 'TW3', postcodes: { 'TW3 3QL': { LHR: [[7, 339], 0, 3] } }, none: [], approx: [], other: [] };
const E16 = {
  district: 'E16',
  postcodes: { 'E16 2QD': { LHR: [104, 1, 60], LCY: [36, null, 12], MAN: [5, 5, 5] } },
  none: [], approx: ['E16 2QD'], other: ['E16 2QD'],
};

let passed = 0;
const check = (name, fn) => { fn(); passed += 1; console.log(`  ok  ${name}`); };

check('Kew: west, both ways, east, each with its share of days', () => {
  const m = planesModel(TW9, INFO, 'TW9 3PZ', NAMES);
  const [lhr] = m.airports;
  assert.deepEqual(lhr.rows.map((r) => [r.label, r.share, r.text]), [
    ['Flying west', '56% of days', '310 a day'],
    ['Both ways', '15% of days', '168 a day'],
    ['Flying east', '29% of days', '4 a day'],
  ]);
  assert.equal(m.sub, 'From Heathrow, on an average day of each kind, January to August 2026');
  assert.match(lhr.wind, /here, about 310 on a day it flies west and about 4 on a day it flies east\.$/);
  assert.equal(m.edge, null);
  assert.equal(m.none, null);
  assert.deepEqual(lhr.rows[0].bar, [0, 310 / 400]);
});

check('a cone edge is a range, said so, and kept out of the sentence', () => {
  const m = planesModel(TW3, INFO, 'TW3 3QL', NAMES);
  const [west, both, east] = m.airports[0].rows;
  assert.equal(west.text, '7 to 339 a day');
  assert.deepEqual(west.bar, [7 / 400, 339 / 400]);
  assert.equal(both.text, '3 a day');
  assert.equal(east.text, 'none'); // a measured zero, written 0 in the file
  assert.match(m.edge, /edge of a flight path/);
  assert.doesNotMatch(m.airports[0].wind, /here,/);
});

check('measured with nothing reaching 1 a day: told so, no airport rows', () => {
  const m = planesModel(TW9, INFO, 'tw9  9zz', NAMES); // and the postcode is normalised
  assert.deepEqual(m.airports, []);
  assert.equal(m.none, 'Under 1 a day from each of the two airports we count, whichever way they fly.');
});

check('never measured: nothing at all', () => {
  assert.equal(planesModel(TW9, INFO, 'TW9 1AA', NAMES), null);
  assert.equal(planesModel(null, INFO, 'TW9 3PZ', NAMES), null); // a district file that did not load
  assert.equal(planesModel(TW9, null, 'TW9 3PZ', NAMES), null);
});

check('no figure for a kind of day reads "not measured", never 0', () => {
  const m = planesModel(E16, INFO, 'E16 2QD', NAMES);
  const lcy = m.airports.find((a) => a.code === 'LCY');
  assert.equal(lcy.rows.find((r) => r.kind === 'easterly').text, 'not measured');
  assert.equal(lcy.rows.find((r) => r.kind === 'easterly').bar, null);
  assert.doesNotMatch(lcy.wind, /here,/);
});

check('an airport airports.json does not publish is never shown', () => {
  const m = planesModel(E16, INFO, 'E16 2QD', NAMES);
  assert.deepEqual(m.airports.map((a) => a.code), ['LHR', 'LCY']);
  assert.equal(m.sub.startsWith('From Heathrow and London City,'), true);
});

check('listed only under airports airports.json no longer publishes: nothing at all, not an empty block', () => {
  // A district file a month older than airports.json (an edge cache, a part-deployed roll) can list an airport
  // that has since failed the year rule. Filtering it out left a heading over no rows, read as a measurement.
  const stale = { district: 'M1', postcodes: { 'M1 1AE': { MAN: [5, 5, 5] } }, none: [], approx: [], other: [] };
  assert.equal(planesModel(stale, INFO, 'M1 1AE', NAMES), null);
});

check('the position and the uncounted-traffic warnings', () => {
  const m = planesModel(E16, INFO, 'E16 2QD', NAMES);
  assert.match(m.approx, /approximate/);
  assert.match(m.other, /does not mean a quiet sky/);
  const k = planesModel(TW9, INFO, 'TW9 3PZ', NAMES);
  assert.equal(k.approx, null);
  assert.equal(k.other, null);
});

check('figures, districts and periods as written', () => {
  assert.deepEqual([perDay(0), perDay('<1'), perDay(12), perDay(['<1', 40]), perDay(null)],
    ['none', 'under 1 a day', '12 a day', 'under 1 to 40 a day', 'not measured']);
  // A range whose quietest end measured zero: "0 to 12" wrote a measured zero as a digit, where a lone one reads
  // "none"; "up to 12" says the same without the second wording.
  assert.equal(perDay([0, 12]), 'up to 12 a day');
  assert.equal(districtOf('ec1a 1bb'), 'EC1A');
  assert.equal(period(['202511', '202608']), 'November 2025 to August 2026');
});

console.log(`planes model: ${passed} checks passed`);
