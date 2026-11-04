// The panel's findings, as plain facts in and plain words out (Bill, 2026-11-04). No browser: every branch is reached on
// purpose here, because a finding only some cities reach would otherwise be proven by chance.
import { strict as assert } from 'node:assert';
import {
  aircraftFinding, crimeFinding, epcFinding, findingHtml, nearestFinding, planesFindings, planesNotes, priceFinding,
  pathFinding, planesNotesHtml, ratingFinding, roadFinding, soldFinding,
} from '../js/panel-findings.mjs';

let passed = 0;
const check = (name, fn) => { fn(); passed += 1; };

// Road noise: the council's rating leads, explained by the postcode's own figure (Bill, 2026-11-04).
const WHO = { who: 53, period: '2021', council: 'Kensington and Chelsea', band: 'high', abovePct: 75 };
check('the rating, explained by the figure', () => {
  const f = roadFinding({ ...WHO, db: 71.8 });
  assert.equal(f.head, 'Road noise is high');
  assert.equal(f.detail, '71.8 dB. The WHO guideline is 53 dB. This is a modelled figure for 2021.');
  assert.deepEqual(f.gauge, { value: 71.8, tick: 53, caption: 'WHO guideline 53 dB', text: '71.8 dB' });
  assert.equal(f.note, 'The road noise rating is for all of Kensington and Chelsea. The figures are for this postcode.');
});
check('a note appears only where a rating sits above a figure', () => {
  assert.equal(roadFinding({ db: 60, who: 53 }).note, null);
  assert.equal(roadFinding({ db: 60, who: 53, council: 'X' }).note, null);
  assert.equal(roadFinding(WHO).note, undefined);
  assert.equal(roadFinding({ ...WHO, belowDb: 45 }).note, undefined);
});
check('New York says borough and ZIP code', () => {
  const f = roadFinding({ council: 'Queens', band: 'moderate', abovePct: 40, area: 'borough', spot: 'ZIP code' });
  assert.equal(f.detail, 'A rating for the whole borough: 40% of its ZIP codes are over the WHO guideline. There is no figure for this ZIP code.');
  assert.doesNotMatch(JSON.stringify(f), /council|postcode/i);
  const c = crimeFinding({ band: 'medium', rate: 78, comparable: false, area: 'borough' });
  assert.match(c.detail, /across the whole borough\.$/);
  assert.equal(priceFinding({ price: '$1', area: 'borough' }).label, 'Average price in the borough');
});
check("a figure under the guideline keeps the council's rating, as Bill chose, and its own true number", () => {
  const f = roadFinding({ ...WHO, db: 49.9 });
  assert.equal(f.head, 'Road noise is high');
  assert.equal(f.detail, '49.9 dB. The WHO guideline is 53 dB. This is a modelled figure for 2021.');
});
check('a council with no rating gets the plain fact, on either side', () => {
  assert.equal(roadFinding({ db: 60, who: 53 }).head, 'Road noise is over the WHO guideline');
  assert.equal(roadFinding({ db: 40, who: 53 }).head, 'Road noise is under the WHO guideline');
  assert.equal(roadFinding({ db: 53, who: 53 }).head, 'Road noise is at the WHO guideline');
});
check('a reading with no period does not invent one', () => assert.match(roadFinding({ db: 60, who: 53 }).detail, /This is a modelled figure\.$/));
check('a surveyed-quiet bound is not a reading: no bar, no figure as a reading', () => {
  const f = roadFinding({ belowDb: 45, who: 53 });
  assert.equal(f.head, 'Road noise is under the WHO guideline');
  assert.equal(f.gauge, undefined);
  assert.match(f.detail, /mapped none at or above 45 dB/);
});
check("a surveyed-quiet postcode is never given the council's rating", () => {
  assert.equal(roadFinding({ ...WHO, belowDb: 45 }).head, 'Road noise is under the WHO guideline');
});
check('a bound above the guideline claims nothing about the guideline', () => {
  const f = roadFinding({ belowDb: 55, who: 53 });
  assert.doesNotMatch(f.head, /WHO/);
});
check("the council's rating names the council and says there is no figure", () => {
  const f = roadFinding(WHO);
  assert.equal(f.head, 'Road noise in Kensington and Chelsea is high');
  assert.match(f.detail, /whole council: 75% of its postcodes are over the WHO guideline\. There is no figure for this postcode\.$/);
  assert.equal(f.gauge, undefined);
});
check('the council fallback survives a missing share', () => assert.doesNotMatch(roadFinding({ council: 'X', band: 'low' }).detail, /%/));
check('nothing known says nothing', () => {
  assert.equal(roadFinding({}), null);
  assert.equal(roadFinding(), null);
  assert.equal(roadFinding({ db: null, who: 53 }), null);
  assert.equal(roadFinding({ db: '71.8', who: 53 }), null);
  assert.equal(roadFinding({ db: NaN, who: 53 }), null);
  assert.equal(roadFinding({ council: 'X' }), null);
});

// Aircraft: the word follows the number shown.
check('the word is the one the panel gives, and the figure stays on its scale', () => {
  assert.equal(aircraftFinding({ score: 7, word: 'High' }).head, 'Aircraft noise is high');
  assert.match(aircraftFinding({ score: 12, word: 'High' }).detail, /^10\.0 out of 10/);
  assert.equal(aircraftFinding({ score: 12, word: 'High' }).gauge.value, 100);
});
check('an estimate says so, and DEFRA is modelled, never measured', () => {
  assert.equal(aircraftFinding({ score: 3.5, word: 'Low' }).detail, '3.5 out of 10, an estimate from the routes.');
  assert.equal(aircraftFinding({ score: 3.5, word: 'Low', modelled: true }).detail, "3.5 out of 10, from DEFRA's noise map, modelled.");
  assert.doesNotMatch(JSON.stringify(aircraftFinding({ score: 3.5, word: 'Low', modelled: true })), /measured/i);
});
check('no aircraft score says nothing, and zero is a reading', () => {
  assert.equal(aircraftFinding({}), null);
  assert.equal(aircraftFinding({ score: 3 }), null);
  assert.equal(aircraftFinding({ score: 0, word: 'Low' }).head, 'Aircraft noise is low');
});

// Planes: only ever what the model holds.
const MODEL = {
  heading: 'Planes overhead', none: null, edge: null, approx: null, other: null, definition: 'Overhead means this.',
  counted: 'Counted from tracking.', credits: ['Tracks: adsb.lol'],
  airports: [{ name: 'Heathrow', period: 'January to August 2026', wind: 'The wind decides.', rows: [
    { label: 'Flying west', text: '4 a day', share: '56% of days' }, { label: 'Both ways', text: '3 a day', share: '15% of days' },
    { label: 'Flying east', text: 'under 1 a day', share: '29% of days' }] }],
};
check('planes rows come straight from the model', () => {
  const [f] = planesFindings(MODEL);
  assert.equal(f.head, 'Heathrow planes overhead');
  assert.deepEqual(f.rows[2], ['Flying east: under 1 a day', '29% of days']);
});
check('a postcode outside the files says nothing', () => assert.deepEqual(planesFindings(null), []));
check('a counted postcode with no planes says what the model says', () => {
  const f = planesFindings({ ...MODEL, airports: [], none: 'Under 1 a day from each of the ten airports we count.' });
  assert.equal(f.length, 1);
  assert.match(f[0].detail, /Under 1 a day/);
});
check('the notes keep the credits, and leave the caveats on the row', () => {
  const n = planesNotes({ ...MODEL, edge: 'A range means this.' });
  assert.equal(n.length, 3);
  assert.match(n.at(-1), /adsb\.lol/);
  assert.doesNotMatch(n.join(' '), /A range means this/);
  assert.deepEqual(planesNotes(null), []);
});
check('a caveat that changes what a figure means stays with the figure', () => {
  const two = { ...MODEL, airports: [MODEL.airports[0], { ...MODEL.airports[0], name: 'Gatwick' }], other: 'Other flying passes over here too.', approx: 'Approximate.', edge: 'A range.' };
  const found = planesFindings(two);
  assert.equal(found[0].caveats, undefined);
  assert.deepEqual(found[1].caveats, ['A range.', 'Approximate.', 'Other flying passes over here too.']);
  assert.match(findingHtml(found[1]), /Other flying passes over here too/);
  const none = planesFindings({ ...MODEL, airports: [], none: 'Under 1 a day.', other: 'Other flying.' });
  assert.deepEqual(none[0].caveats, ['Other flying.']);
});

check('the notes fold, escaped, with the way to the method', () => {
  const html = planesNotesHtml({ ...MODEL, how: '/how-it-works/#planes-overhead', definition: 'A <b> c' });
  assert.match(html, /^<details/);
  assert.match(html, /About these figures/);
  assert.match(html, /adsb\.lol/);
  assert.match(html, /href="\/how-it-works\/#planes-overhead"/);
  assert.doesNotMatch(html, /<b> c/);
  assert.equal(planesNotesHtml(null), '');
});
check('the flight path row, and none when no path is near', () => {
  assert.deepEqual(pathFinding(1.234).rows, [['Nearest flight path', '1.2 km']]);
  assert.equal(pathFinding(Infinity), null);
  assert.equal(pathFinding(undefined), null);
});

// Ratings.
check('ratings read plainly', () => {
  assert.equal(ratingFinding('flood', 'Flood risk', 'Low').head, 'Flood risk is low');
  assert.equal(ratingFinding('schools', 'Schools', 'above average').head, 'Schools are above average');
});
check('no rating says nothing', () => {
  assert.equal(ratingFinding('flood', 'Flood risk', undefined), null);
  assert.equal(ratingFinding('schools', 'Schools', 'not recorded'), null);
});

// Crime.
check('crime against the median, from a true zero', () => {
  const f = crimeFinding({ band: 'medium', rate: 142.4, median: 87.6 });
  assert.equal(f.head, 'Crime is medium');
  assert.match(f.detail, /1\.6 times the London median of 87\.6\.$/);
  assert.equal(f.amounts.length, 2);
  const [a, b] = f.amounts.map((x) => x[2]);
  assert.ok(Math.abs(a / b - 142.4 / 87.6) < 0.001, 'bars keep the true ratio');
});
check('crime at, and under, the median', () => {
  assert.match(crimeFinding({ band: 'low', rate: 87.6, median: 87.6 }).detail, /close to the London median/);
  assert.match(crimeFinding({ band: 'low', rate: 40, median: 87.6 }).detail, /2\.2 times lower than the London median/);
});
check('with no band the comparison is the finding, and the figure appears once', () => {
  const f = crimeFinding({ rate: 110, median: 87.6 });
  assert.equal(f.head, 'Recorded crime is 1.3 times the London median of 87.6');
  assert.equal(f.detail, '110 recorded offences per 1,000 residents a year across the whole council.');
});
check("an estimate says so, and never says recorded", () => {
  const f = crimeFinding({ band: 'high', rate: 190, median: 87.6, estimated: true });
  assert.match(f.detail, /Sky Score's estimate/);
  assert.doesNotMatch(JSON.stringify(f), /recorded/i);
  assert.match(crimeFinding({ rate: 190, median: 87.6, estimated: true }).head, /^Estimated crime is/);
});
check("New York's figures are never set against London's", () => {
  const f = crimeFinding({ band: 'medium', rate: 30, median: 87.6, comparable: false });
  assert.equal(f.amounts, undefined);
  assert.doesNotMatch(f.detail, /London/);
});
check('a band alone, and nothing at all', () => {
  assert.equal(crimeFinding({ band: 'high' }).detail, undefined);
  assert.equal(crimeFinding({}), null);
});

// What the panel already lists.
check('nearest under its rating, the rating alone, the list alone, or nothing', () => {
  const row = { name: "Earl's Court", dist: '376m' };
  assert.deepEqual(nearestFinding('transport', 'Transport', 'excellent', row).rows, [["Earl's Court", '376 m']]);
  assert.equal(nearestFinding('transport', 'Transport', 'excellent', null).rows, undefined);
  assert.deepEqual(nearestFinding('t', 'T', 'good', { name: 'A', dist: '1.2 km' }).rows, [['A', '1.2 km']]);
  assert.equal(nearestFinding('transport', 'Transport', undefined, row).head, 'Transport');
  assert.equal(nearestFinding('transport', 'Transport', undefined, null), null);
});

// Property.
check('the trend reads as words', () => {
  assert.equal(priceFinding({ price: '£1,204,072', trend: '-13.8%' }).detail, 'down 13.8% in a year.');
  assert.equal(priceFinding({ price: '£1', trend: '+2.1%' }).detail, 'up 2.1% in a year.');
  assert.equal(priceFinding({ price: '£1', trend: '0%' }).detail, 'unchanged in a year.');
});
check('a trend it cannot read is left out, and no price says nothing', () => {
  assert.equal(priceFinding({ price: '£1', trend: 'n/a' }).detail, null);
  assert.equal(priceFinding({}), null);
});
const gbp = (n) => `£${n.toLocaleString('en-GB')}`;
check('the last ordinary sale of a home, passing a shop and a non-standard sale', () => {
  const f = soldFinding([
    { price: 20000, type: 'other', category: 'B', date: '2025-06-01' }, { price: 90000, type: 'flat-maisonette', category: 'B', date: '2025-05-01' },
    { price: 70000, type: '', category: '', date: '2025-04-01' },
    { price: 1810000, type: 'terraced', category: 'A', date: '2025-01-15T00:00:00' }], gbp);
  assert.deepEqual(f.rows, [['£1,810,000', 'January 2025']]);
});
check('only a known home in a standard sale is called a home', () => {
  assert.equal(soldFinding([{ price: 5, type: '', category: 'A' }], gbp), null);
  assert.equal(soldFinding([{ price: 5, type: 'terraced', category: '' }], gbp), null);
  assert.equal(soldFinding([{ price: 5, type: 'terraced', category: 'A', date: '2020-02-01' }], gbp).rows[0][1], 'February 2020');
  assert.equal(soldFinding([{ price: 5, type: 'terraced', category: 'A' }], gbp).label, 'Last home sold at this postcode');
});
check('no sale, or an absence, says nothing', () => {
  assert.equal(soldFinding('none', gbp), null);
  assert.equal(soldFinding([], gbp), null);
  assert.equal(soldFinding([{ price: 5, type: 'other' }], gbp), null);
});
check('a sale with no usable date keeps its price, without inventing one', () => assert.equal(soldFinding([{ price: 5, type: 'flat-maisonette', category: 'A', date: 'x' }], gbp).rows[0][1], ''));
check('energy, with its count', () => {
  const f = epcFinding({ available: true, count: 32, summary: { averageBand: 'D', averageRating: 67 } });
  assert.equal(f.head, 'Energy rating D');
  assert.equal(f.detail, '67 out of 100, from 32 certificates.');
  assert.equal(epcFinding({ available: true, count: 1, summary: { averageBand: 'C' } }).detail, 'from 1 certificate.');
  assert.equal(epcFinding({ available: true, count: 1, summary: { averageBand: 'C' } }).gauge, null);
});
check('no energy data says nothing, unavailable or empty', () => {
  assert.equal(epcFinding(null), null);
  assert.equal(epcFinding({ available: false }), null);
  assert.equal(epcFinding({ available: true, count: 0, summary: {} }), null);
  assert.equal(epcFinding({ available: true, count: 3, summary: { averageBand: 'N/A', averageRating: null } }), null);
});

// What the reader sees.
check('an absent finding leaves no trace', () => assert.equal(findingHtml(null), ''));
check('text is escaped', () => {
  const html = findingHtml(roadFinding({ council: '<b>X</b>', band: 'high' }));
  assert.doesNotMatch(html, /<b>X/);
  assert.match(html, /&lt;b&gt;X/);
  assert.match(findingHtml(nearestFinding('t', 'Transport', 'good', { name: 'A "B" <c>', dist: '1m' })), /A &quot;B&quot; &lt;c&gt;/);
  assert.match(findingHtml(roadFinding({ db: 60, who: 53, council: '<x>', band: 'high' })), /all of &lt;x&gt;/);
});
check('no finding ever prints undefined, null or NaN', () => {
  const all = [roadFinding({ ...WHO, db: 71.8 }), roadFinding({ belowDb: 45 }), roadFinding(WHO), aircraftFinding({ score: 3.5, word: 'Low' }),
    ...planesFindings(MODEL), ratingFinding('f', 'Flood risk', 'low'), crimeFinding({ band: 'medium', rate: 142.4, median: 87.6 }),
    crimeFinding({ band: 'high' }), nearestFinding('t', 'Transport', 'good', { name: 'A' }), priceFinding({ price: '£1', trend: 'x' }),
    soldFinding([{ price: 5, type: 'terraced', category: 'A' }], gbp), epcFinding({ available: true, count: 2, summary: { averageBand: 'B', averageRating: '' } })];
  for (const f of all) assert.doesNotMatch(findingHtml(f), /undefined|null|NaN/);
});
check('a bar is decoration: the words carry it', () => assert.match(findingHtml(aircraftFinding({ score: 3.5, word: 'Low' })), /find-track" aria-hidden="true"/));
check('a unit is never set in capitals by the markup', () => assert.match(findingHtml(roadFinding({ ...WHO, db: 71.8 })), /71\.8 dB/));

console.log(`PASS ${passed} of ${passed}`);
