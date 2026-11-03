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
import { districtOf, period, perDay, planesLinks, planesModel, planesWalk, shortFigure, stepColour } from '../js/planes.mjs';

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

// Where to go next (2026-11-02, Bill: "make the links clear and easy to navigate"). The index is the one holder of
// which district pages exist: a link only to a district it lists, and the consultation link only for a postcode with
// a figure from the pack's airport, only while it is open, and never without the index.
const INDEX = {
  councils: { E09000027: ['TW9'], E09000018: ['TW3'] },
  consultation: { airport: 'LHR', until: '2026-12-22', hub: '/planes-overhead/heathrow-consultation/', councils: {} },
};
const SE1 = { district: 'SE1', postcodes: { 'SE1 9AA': { LCY: [40, 2, 20] } }, none: [], approx: [], other: [] };
const INFO_SE1 = { ...INFO, districts: [...INFO.districts, 'SE1'] };
const day = (iso) => new Date(`${iso}T12:00:00Z`);

check('the district page and the consultation pack, linked only where they exist and while it is open', () => {
  const kew = planesModel(TW9, INFO, 'TW9 3PZ', NAMES);
  assert.deepEqual(planesLinks(INDEX, 'TW9 3PZ', kew, day('2026-11-02')), [
    { text: 'Every postcode in TW9, sector by sector', href: '/planes-overhead/tw9/' },
    { text: "For Heathrow's consultation, open until 22 December: the planes over each council", href: '/planes-overhead/heathrow-consultation/' },
  ]);
  assert.equal(planesLinks(INDEX, 'TW9 3PZ', kew, day('2026-12-22')).length, 2, 'its last day still offers it');
  assert.deepEqual(planesLinks(INDEX, 'TW9 3PZ', kew, day('2026-12-23')).map((l) => l.href), ['/planes-overhead/tw9/']);
  // E16 has Heathrow figures but no page in the index: the pack, never a guessed district page.
  const e16 = planesModel(E16, INFO, 'E16 2QD', NAMES);
  assert.deepEqual(planesLinks(INDEX, 'E16 2QD', e16, day('2026-11-02')).map((l) => l.href), ['/planes-overhead/heathrow-consultation/']);
  // London City only: no consultation link (the pack is Heathrow's).
  const se1 = planesModel(SE1, INFO_SE1, 'SE1 9AA', NAMES);
  assert.deepEqual(planesLinks(INDEX, 'SE1 9AA', se1, day('2026-11-02')), []);
  // No index (a failed fetch): no links at all; an index with no consultation: the page only.
  assert.deepEqual(planesLinks(null, 'TW9 3PZ', kew, day('2026-11-02')), []);
  assert.deepEqual(planesLinks({ councils: INDEX.councils }, 'TW9 3PZ', kew, day('2026-11-02')).map((l) => l.href), ['/planes-overhead/tw9/']);
  assert.deepEqual(planesLinks(INDEX, 'TW9 3PZ', null, day('2026-11-02')), []);
});

// THE FRONT PAGE'S WALKTHROUGH, STEP 04 (front-page-v3, 2026-11-03): the answer in a sentence, then the three kinds of day
// as bars coloured as the full map's planes layer colours each figure. Every word and figure from the model.
const STEPS = [{ step: 1, from: 10, colour: '#dc8a4a' }, { step: 2, from: 50, colour: '#c2622a' },
  { step: 3, from: 100, colour: '#9a4316' }, { step: 4, from: 200, colour: '#662809' }];

check('walkthrough: Kew in one sentence, then west, both ways, east in the layer\'s colours', () => {
  const w = planesWalk(planesModel(TW9, INFO, 'TW9 3PZ', NAMES), STEPS);
  assert.equal(w.sentence.map((p) => p.text).join(''),
    'On most days, about 310 planes a day pass over TW9 3PZ: the days Heathrow flies west. On a day it flies east, about 4.');
  assert.deepEqual(w.sentence.filter((p) => p.strong).map((p) => p.text), ['about 310 planes a day', 'about 4']);
  assert.deepEqual(w.rows.map((r) => [r.label, r.share, r.figure, r.colour]), [
    ['Flying west', '56% of days', '310', '#662809'],
    ['Both ways', '15% of days', '168', '#9a4316'],
    ['Flying east', '29% of days', '4', null],
  ]);
  assert.deepEqual(w.rows[0].bar, [0, 310 / 400], "the bar is the model's own, on the file's scale");
  assert.equal(w.foot, 'Planes a day over TW9 3PZ from Heathrow, January to August 2026. Never an average of the three: no day is average.');
});

check('walkthrough: no "most days" unless one way is over half of all days, and never a range in the sentence', () => {
  const even = { ...INFO, airports: { ...INFO.airports, LHR: { ...INFO.airports.LHR, share_pct: { westerly: 50, easterly: 35, mixed: 15 } } } };
  const w = planesWalk(planesModel(TW9, even, 'TW9 3PZ', NAMES), STEPS);
  assert.equal(w.sentence.length, 1);
  assert.match(w.sentence[0].text, /^Planes land and take off into the wind/);
  const edge = planesWalk(planesModel(TW3, INFO, 'TW3 3QL', NAMES), STEPS);
  assert.doesNotMatch(edge.sentence.map((p) => p.text).join(''), /On most days/);
  assert.deepEqual(edge.rows.map((r) => [r.figure, r.colour]), [['7 to 339', '#662809'], ['3', null], ['none', null]]);
});

check('walkthrough: several airports tell the busiest; nothing to tell is null; no steps, no colour', () => {
  const e16 = planesWalk(planesModel(E16, INFO, 'E16 2QD', NAMES), STEPS);
  assert.equal(e16.airport, 'Heathrow');
  assert.equal(planesWalk(planesModel(TW9, INFO, 'TW9 9ZZ', NAMES), STEPS), null);
  assert.equal(planesWalk(null, STEPS), null);
  assert.equal(stepColour(310), null);
  assert.equal(stepColour(310, [{ from: 10, colour: 'red' }]), null, 'a colour that is not #rrggbb is never written into a style');
  assert.deepEqual([shortFigure(null), shortFigure('<1'), shortFigure([0, 40]), shortFigure(['<1', 40])],
    ['not measured', 'under 1', 'up to 40', 'under 1 to 40']);
  assert.equal(stepColour(['<1', 49], STEPS), '#dc8a4a', "a range is coloured by its busier end, as the layer's stripes are");
});

console.log(`planes model: ${passed} checks passed`);
