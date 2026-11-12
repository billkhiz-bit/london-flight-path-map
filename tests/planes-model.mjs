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
import { districtOf, overheadConeSvg, period, perDay, planesBandLead, planesChart, planesLead, planesLinks, planesModel, planesWalk, shortFigure, stepColour } from '../js/planes.mjs';

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

check('the hero\'s tile: the commonest one-way day, its figure from the model, and nothing if that day has no planes', () => {
  assert.deepEqual(planesWalk(planesModel(TW9, INFO, 'TW9 3PZ', NAMES), STEPS).lead, { figure: '310', words: 'planes a day, flying west' });
  const east = { ...INFO, airports: { ...INFO.airports, LHR: { ...INFO.airports.LHR, share_pct: { westerly: 29, easterly: 56, mixed: 15 } } } };
  assert.deepEqual(planesWalk(planesModel(TW9, east, 'TW9 3PZ', NAMES), STEPS).lead, { figure: '4', words: 'planes a day, flying east' });
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

// OPTION C, THE ANSWER AS THE HEADLINE (review prototype, 2026-11-07): the front page's h1 leads with the planes only in
// planesWalk()'s own "most days" terms, only where the full map's planes layer would colour the figure, names the airport
// it counts, and never carries a figure whose caveat it cannot.
check('headline: Kew leads with its most days, the airport named, in the walkthrough\'s own words', () => {
  const kew = planesModel(TW9, INFO, 'TW9 3PZ', NAMES);
  assert.equal(planesLead(kew, STEPS), 'On most days, about 310 Heathrow planes a day pass over TW9 3PZ');
  assert.ok(planesWalk(kew, STEPS).sentence.map((p) => p.text).join('').startsWith('On most days, about 310 planes a day pass over TW9 3PZ'),
    'the headline and the walkthrough say the same day and figure');
  const e16 = planesModel({ ...E16, approx: [], other: [] }, INFO, 'E16 2QD', NAMES);
  assert.equal(planesLead(e16, STEPS), 'On most days, about 104 Heathrow planes a day pass over E16 2QD', 'two airports: the busiest, named, never a sum');
});

check('headline: no "most days" at half or under, no range, nothing the layer leaves blank, and no steps, no planes', () => {
  const even = { ...INFO, airports: { ...INFO.airports, LHR: { ...INFO.airports.LHR, share_pct: { westerly: 50, easterly: 35, mixed: 15 } } } };
  assert.equal(planesLead(planesModel(TW9, even, 'TW9 3PZ', NAMES), STEPS), null);
  assert.equal(planesLead(planesModel(TW3, INFO, 'TW3 3QL', NAMES), STEPS), null, 'a range is never a headline');
  const few = (v) => planesModel({ district: 'TW9', postcodes: { 'TW9 3PZ': { LHR: [v, 40, 2] } }, none: [], approx: [], other: [] }, INFO, 'TW9 3PZ', NAMES);
  assert.equal(planesLead(few(9), STEPS), null, 'under the layer\'s first step (10), as SW5 9HP\'s 4 a day: blank on the map, so not the headline');
  assert.equal(planesLead(few(10), STEPS), 'On most days, about 10 Heathrow planes a day pass over TW9 3PZ', 'the first step itself leads');
  assert.equal(planesLead(few('<1'), STEPS), null);
  assert.equal(planesLead(planesModel(TW9, INFO, 'TW9 3PZ', NAMES)), null, 'without the layer\'s steps the planes never lead');
  assert.equal(planesLead(planesModel(TW9, INFO, 'TW9 9ZZ', NAMES), STEPS), null, 'none reaching 1 a day is said below, never led with');
  assert.equal(planesLead(null, STEPS), null);
});

check('headline: a caveat that changes the figure keeps the planes out of it', () => {
  assert.equal(planesLead(planesModel({ ...TW9, approx: ['TW9 3PZ'] }, INFO, 'TW9 3PZ', NAMES), STEPS), null, 'an estimated position');
  assert.equal(planesLead(planesModel({ ...TW9, other: ['TW9 3PZ'] }, INFO, 'TW9 3PZ', NAMES), STEPS), null, 'other flying the count cannot see');
});

// THE QUIET SIDE (Bill, 2026-11-07: "answer the planes question before road noise"): the band the layer leaves blank, said
// as that band, read from the steps, only where it holds on every kind of day for every airport listed.
const at = (figs, extra = {}) => planesModel({ district: 'SW5', postcodes: { 'SW5 9HP': figs }, none: [], approx: [], other: [], ...extra }, INFO, 'SW5 9HP', NAMES);
check('band: SW5 9HP\'s few planes, as the layer\'s blank band, the airport named, the step read from the layer', () => {
  assert.equal(planesBandLead(at({ LHR: [4, '<1', 3] }), STEPS), 'Fewer than 10 Heathrow planes a day pass over SW5 9HP');
  assert.equal(planesBandLead(at({ LHR: [9, 9, 9] }), STEPS), 'Fewer than 10 Heathrow planes a day pass over SW5 9HP', 'up to the step itself');
  assert.equal(planesBandLead(at({ LHR: [4, '<1', 3] }), [{ from: 25, colour: '#dc8a4a' }]), 'Fewer than 25 Heathrow planes a day pass over SW5 9HP', 'the band is the layer\'s, never typed');
  assert.equal(planesBandLead(at({ LHR: [4, '<1', 3] }), []), null, 'no steps, no band');
});

check('band: never claimed unless true on every kind of day held: a figure at the step, a range reaching it, or a day not measured', () => {
  assert.equal(planesBandLead(at({ LHR: [10, 1, 1] }), STEPS), null);
  assert.equal(planesBandLead(at({ LHR: [[2, 12], 1, 1] }), STEPS), null, 'a range is judged on its top');
  assert.equal(planesBandLead(at({ LHR: [[2, 9], 1, '<1'] }), STEPS), 'Fewer than 10 Heathrow planes a day pass over SW5 9HP', 'a range under the step is inside the band');
  assert.equal(planesBandLead(at({ LHR: [4, null, 3] }), STEPS), null, 'a kind of day not measured is not "fewer than"');
});

check('band: per airport, never a sum; none reaching 1 says it of each airport; a caveat or no data claims nothing', () => {
  assert.equal(planesBandLead(at({ LHR: [4, 2, 3], LCY: [6, 1, 2] }), STEPS), 'Fewer than 10 planes a day from each of Heathrow and London City pass over SW5 9HP');
  assert.equal(planesBandLead(at({ LHR: [4, 2, 3], LCY: [16, 1, 2] }), STEPS), null, 'one airport over the step');
  assert.equal(planesBandLead(planesModel(TW9, INFO, 'TW9 9ZZ', NAMES), STEPS), 'Fewer than 10 planes a day from each airport we count pass over TW9 9ZZ');
  assert.equal(planesBandLead(at({ LHR: [4, 2, 3] }, { approx: ['SW5 9HP'] }), STEPS), null, 'an estimated position');
  assert.equal(planesBandLead(at({ LHR: [4, 2, 3] }, { other: ['SW5 9HP'] }), STEPS), null, 'other flying the count cannot see');
  assert.equal(planesBandLead(at({ BHX: [4, 2, 3] }), STEPS), null, 'an airport airports.json does not publish is never spoken for');
  assert.equal(planesBandLead(null, STEPS), null);
});

check('the large-user rule is said beside the definition, and an older file without it says nothing extra', () => {
  const rule = 'PO boxes and other postcodes for organisations that receive a lot of post are left out.';
  const told = planesModel(TW9, { ...INFO, postcodes_rule: rule }, 'TW9 3PZ', NAMES).definition;
  assert.ok(told.endsWith(rule) && told.includes(INFO.direction_rule), told);
  const older = planesModel(TW9, INFO, 'TW9 3PZ', NAMES).definition;
  assert.equal(older, `${INFO.definition} ${INFO.direction_rule}`);
  assert.doesNotMatch(older, /undefined/);
});

// ---- the planes chart (2026-11-11): the air chart's twin, from the model, banded and coloured by the layer's steps ----
const rowsOf = (svg) => [...svg.matchAll(/<g data-kind="([^"]+)" data-value="([^"]*)">/g)].map((m) => [m[1], m[2]]);
const fillsOf = (svg) => [...svg.matchAll(/data-mark="planes" cx="([\d.]+)"[^>]*fill="(#[0-9a-f]{6})"/g)].map((m) => [Number(m[1]), m[2]]);
check('chart: Kew, each kind of day at its figure on one scale, coloured and banded as the layer', () => {
  const svg = planesChart(planesModel(TW9, INFO, 'TW9 3PZ', NAMES).airports[0], STEPS);
  assert.deepEqual(rowsOf(svg), [['westerly', '310'], ['mixed', '168'], ['easterly', '4']]);
  assert.match(svg, /data-max="400"/, '310 with a little room rounds to 400');
  assert.deepEqual([...svg.matchAll(/data-band="(\d+)"/g)].map((m) => Number(m[1])), [10, 50, 100, 200]);
  const x = (v) => +(176 + (v / 400) * 158).toFixed(2);
  assert.deepEqual(fillsOf(svg), [[x(310), '#662809'], [x(168), '#9a4316'], [x(4), '#9a9893']], 'dots at their figures, in their steps; under the first step neutral');
  assert.match(svg, /56% of days/);
});
check('chart: a range is a bar from fewest to most with its label above; none is a figure, at zero', () => {
  const svg = planesChart(planesModel(TW3, INFO, 'TW3 3QL', NAMES).airports[0], STEPS);
  assert.deepEqual(rowsOf(svg), [['westerly', '7 to 339'], ['mixed', '3'], ['easterly', 'none']]);
  const x = (v) => +(176 + (v / 400) * 158).toFixed(2);
  assert.match(svg, new RegExp(`data-range="1" x1="${x(7)}" x2="${x(339)}"`));
});
check('chart: a kind of day with no figure says "not measured", never 0', () => {
  const lcy = planesModel(E16, INFO, 'E16 2QD', NAMES).airports.find((a) => a.code === 'LCY');
  const svg = planesChart(lcy, STEPS);
  assert.deepEqual(rowsOf(svg).find(([k]) => k === 'easterly'), ['easterly', '']);
  assert.match(svg, />not measured</);
  assert.equal(fillsOf(svg).length, 2, 'no dot for the day not measured');
});
check('chart: without the layer steps, no bands and no guessed colour', () => {
  const svg = planesChart(planesModel(TW9, INFO, 'TW9 3PZ', NAMES).airports[0], []);
  assert.doesNotMatch(svg, /data-band/);
  assert.ok(fillsOf(svg).every(([, c]) => c === '#9a9893'));
});
check('chart: every name is escaped, and a colour that is not a colour is never drawn', () => {
  const svg = planesChart({ name: 'A<b>', code: 'Q"x', rows: [{ kind: 'westerly', label: 'L<i>', share: 's&t', value: 120 }] },
    [{ from: 10, colour: 'red" onload="x' }, { from: 100, colour: '#9a4316' }]);
  assert.doesNotMatch(svg, /<b>|<i>|onload/);
  assert.match(svg, /L&lt;i&gt;/);
  assert.deepEqual(fillsOf(svg).map(([, c]) => c), ['#9a4316']);
});
check('rules: the three sentences apart, word for word, null where the file has none', () => {
  const rule = 'PO boxes and other postcodes for organisations that receive a lot of post are left out.';
  assert.deepEqual(planesModel(TW9, { ...INFO, postcodes_rule: rule }, 'TW9 3PZ', NAMES).rules, { overhead: INFO.definition, direction: INFO.direction_rule, postcodes: rule });
  assert.equal(planesModel(TW9, INFO, 'TW9 3PZ', NAMES).rules.postcodes, null);
});
check("cone: the drawing's angle is the rule's own, and no angle means no drawing", () => {
  const svg = overheadConeSvg(INFO.definition);
  const [, ax, ay] = /L([\d.]+) ([\d.]+)/.exec(svg);
  assert.ok(Math.abs(Math.atan2(62 - Number(ay), 60 - Number(ax)) * 180 / Math.PI - 48.5) < 0.2, svg);
  assert.match(svg, /aria-hidden="true"/);
  assert.equal(overheadConeSvg('Overhead means close by.'), '');
});

console.log(`planes model: ${passed} checks passed`);
