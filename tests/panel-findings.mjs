// The panel's findings, as plain facts in and plain words out (Bill, 2026-11-04). No browser: every branch is reached on
// purpose here, because a finding only some cities reach would otherwise be proven by chance.
import { strict as assert } from 'node:assert';
import { readFileSync } from 'node:fs';
import { planesModel } from '../js/planes.mjs';
import {
  aircraftFinding, crimeFinding, epcFinding, nearestFinding, planesFindings, planesNotes, priceFinding,
  pathFinding, planesNotesHtml, ratingFinding, roadFinding, soldFinding, tileHtml,
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
  rules: { overhead: 'Overhead means 48.5 degrees or more.', direction: 'A day counts one way at 80%.', postcodes: 'PO boxes are left out.' },
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
check('the notes are the overhead rule and three points, word for word; the caveats stay on the row (2026-11-11)', () => {
  const n = planesNotes({ ...MODEL, edge: 'A range means this.' });
  assert.equal(n.over, MODEL.rules.overhead);
  assert.deepEqual(n.points.map((p) => p.text), [MODEL.rules.direction, MODEL.counted, MODEL.rules.postcodes]);
  assert.doesNotMatch(JSON.stringify(n), /A range means this|adsb/, 'no caveat, and no credit said twice: the tile names the tracks');
  assert.deepEqual(planesNotes({ ...MODEL, rules: { overhead: null, direction: 'R.', postcodes: null } }).points.map((p) => p.text), ['R.', MODEL.counted],
    'a rule the file lacks is left out, never "undefined"');
  assert.equal(planesNotes(null), null);
});
check('a caveat that changes what a figure means stays with the figure', () => {
  const two = { ...MODEL, airports: [MODEL.airports[0], { ...MODEL.airports[0], name: 'Gatwick' }], other: 'Other flying passes over here too.', approx: 'Approximate.', edge: 'A range.' };
  const found = planesFindings(two);
  assert.equal(found[0].caveats, undefined);
  assert.deepEqual(found[1].caveats, ['A range.', 'Approximate.', 'Other flying passes over here too.']);
  assert.match(tileHtml(found[1]), /Other flying passes over here too/);
  const none = planesFindings({ ...MODEL, airports: [], none: 'Under 1 a day.', other: 'Other flying.' });
  assert.deepEqual(none[0].caveats, ['Other flying.']);
});

check('the notes fold, escaped: the rule beside its drawing, the points, the way to the method and to every source', () => {
  const html = planesNotesHtml({ ...MODEL, how: '/how-it-works/#planes-overhead', rules: { ...MODEL.rules, postcodes: 'A <b> c' } });
  assert.match(html, /^<details/);
  assert.match(html, /About these figures/);
  assert.match(html, /<div class="planes-over"><svg [^>]*class="planes-cone"[^>]*aria-hidden="true"/);
  assert.match(html, /href="\/how-it-works\/#planes-overhead">How it is counted<\/a>/);
  assert.match(html, /href="\/how-it-works\/#credits">All sources<\/a>/);
  assert.doesNotMatch(html, /<b> c/);
  assert.match(html, /A &lt;b&gt; c/);
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

// What the reader sees: drawn by tileHtml(), the one renderer the page uses (audit M-5, 2026-11-09). These checks read a
// second renderer, findingHtml(), until it was found that no page called it: they proved nothing about the panel.
const colour = () => '#888';
check('an absent finding leaves no trace', () => assert.equal(tileHtml(null), ''));
check('text is escaped', () => {
  const html = tileHtml(roadFinding({ council: '<b>X</b>', band: 'high' }));
  assert.doesNotMatch(html, /<b>X/);
  assert.match(html, /&lt;b&gt;X/);
  assert.match(tileHtml(nearestFinding('t', 'Transport', 'good', { name: 'A "B" <c>', dist: '1m' })), /A &quot;B&quot; &lt;c&gt;/);
  const own = tileHtml(roadFinding({ db: 60, who: 53, council: '<x>', band: 'high' }));
  assert.doesNotMatch(own, /<x>/);
  assert.match(own, /&lt;x&gt;/);
});
check('no finding ever prints undefined, null or NaN', () => {
  const all = [roadFinding({ ...WHO, db: 71.8 }), roadFinding({ belowDb: 45 }), roadFinding(WHO), aircraftFinding({ score: 3.5, word: 'Low' }),
    ...planesFindings(MODEL), ratingFinding('f', 'Flood risk', 'low'), crimeFinding({ band: 'medium', rate: 142.4, median: 87.6 }),
    crimeFinding({ band: 'high' }), nearestFinding('t', 'Transport', 'good', { name: 'A' }), priceFinding({ price: '£1', trend: 'x' }),
    soldFinding([{ price: 5, type: 'terraced', category: 'A' }], gbp), epcFinding({ available: true, count: 2, summary: { averageBand: 'B', averageRating: '' } })];
  for (const f of all) assert.doesNotMatch(tileHtml(f, { scoreColour: colour }), /undefined|null|NaN/);
});
check('every picture says in words what it shows', () => {
  const html = [roadFinding({ ...WHO, db: 71.8 }), aircraftFinding({ score: 3.5, word: 'Low' }), crimeFinding({ band: 'medium', rate: 142.4, median: 87.6 }),
    ...planesFindings(MODEL)].map((f) => tileHtml(f, { scoreColour: colour })).join('');
  const pictures = [...html.matchAll(/<[a-z]+ [^>]*role="img"[^>]*>/g)].map((m) => m[0]);
  assert.ok(pictures.length >= 2, `${pictures.length} pictures drawn`);
  for (const p of pictures) assert.match(p, /aria-label="[^"]+"/, p);
});
check('a unit is never set in capitals by the markup', () => assert.match(tileHtml(roadFinding({ ...WHO, db: 71.8 })), /71\.8 dB/));

// ---- THE ANSWER CARD'S TILES (Bill, 2026-11-08): plain words, a picture where one is honest, closed until tapped ----
const T = await import('../js/panel-findings.mjs');
const INDEX = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
// The map's own rules, READ from index.html (never run): which words each badge class takes, and each school band's class.
const bodyOf = (name) => {
  const m = new RegExp(`function ${name}\\([^)]*\\) \\{([\\s\\S]*?)\\n      \\}`).exec(INDEX);
  assert.ok(m, `${name}() found in index.html`);
  return m[1];
};
check("a rating's tone is the map's own: toneOf() matches ratingBadgeClass() and the school bands, word for word", () => {
  const asTone = { 'rating-low': 'good', 'rating-medium': 'mid', 'rating-high': 'bad' };
  const badge = {};
  for (const [, cond, cls] of bodyOf('ratingBadgeClass').matchAll(/if \(([^)]*)\) return '([a-z-]+)';/g)) {
    for (const [, w] of cond.matchAll(/r === '([^']+)'/g)) badge[w] = cls;
  }
  const fallback = /\n\s*return '([a-z-]+)';\s*$/.exec(bodyOf('ratingBadgeClass'))[1];
  assert.ok(Object.keys(badge).length >= 5, 'the badge rules were read');
  for (const [scale, list] of Object.entries(T.SCALES)) {
    if (scale === 'schools' || scale === 'epc') continue;
    for (const w of list) assert.equal(T.toneOf(w), asTone[badge[w] || fallback], `${scale}: ${w}`);
  }
  const bands = [...bodyOf('schoolBandFromP8').matchAll(/label: '([^']+)', cls: '([a-z-]+)'/g)];
  assert.equal(bands.length, 5, 'all five school bands were read');
  for (const [, label, cls] of bands) assert.equal(T.toneOf(label), asTone[cls], `school band: ${label}`);
  assert.equal(T.toneOf('not recorded'), null, 'an unknown word is no reading, never "bad"');
  assert.equal(T.toneOf(undefined), null);
});
check('road noise, rated for the council with no postcode figure: a strip, 100 squares, and the council named', () => {
  const t = roadFinding({ council: 'Wandsworth', band: 'moderate', abovePct: 58, source: 'DEFRA noise map (modelled)' }).tile;
  assert.deepEqual([t.name, t.level, t.sub, t.shared, t.tone, t.stand], ['Road noise', 'Moderate', 'Wandsworth-wide', true, 'mid', null]);
  assert.deepEqual(t.visual.map((v) => v.kind), ['strip', 'share']);
  assert.equal(t.visual[1].pct, 58);
  assert.deepEqual(t.say, ['We have no reading for this street, so this is for Wandsworth as a whole.']);
  assert.equal(t.source, 'DEFRA noise map (modelled)');
  const html = T.tileHtml({ key: 'road', tile: t });
  assert.equal((html.match(/<i class="on"><\/i>/g) || []).length, 58, '58 of the 100 squares filled');
  assert.equal((html.match(/<i( class="on")?><\/i>/g) || []).length, 100);
  assert.doesNotMatch(html, /<details[^>]*\bopen\b/, 'closed until tapped');
});
check('road noise with its own figure: the figure beside the WHO level, from zero; a high band is a watch item', () => {
  const t = roadFinding({ ...WHO, db: 71.8, source: 'DEFRA noise map (modelled)' }).tile;
  assert.deepEqual([t.level, t.stand, t.source], ['High', 'watch', 'DEFRA noise map (modelled), 2021']);
  const bars = t.visual.find((v) => v && v.kind === 'bars');
  assert.deepEqual(bars.rows.map((r) => r.text), ['71.8 dB', '53 dB']);
  assert.match(t.say[0], /^The rating is for Kensington and Chelsea as a whole; the bars are for this postcode\.$/);
  const plain = roadFinding({ db: 60, who: 53 }).tile;
  assert.deepEqual([plain.level, plain.tone, plain.stand, plain.source], ['Over the WHO level', null, null, null], 'no band: no stand-out, no source invented');
});
check("New York's tiles name the borough and never borrow DEFRA", () => {
  const f = roadFinding({ council: 'Queens', band: 'moderate', abovePct: 40, area: 'borough', spot: 'ZIP code' });
  assert.equal(f.tile.source, null, 'no source given: none printed, never a UK one');
  assert.match(f.tile.say[0], /this ZIP code, so this is for Queens/);
  assert.doesNotMatch(T.tileHtml(f), /council|postcode|DEFRA/i);
});
check('aircraft noise: a yearly average says so, and a high one is not softened', () => {
  const low = aircraftFinding({ score: 3.6, word: 'Low', modelled: true, source: 'DEFRA noise map (modelled)' }).tile;
  assert.deepEqual([low.level, low.sub, low.stand], ['Low', '3.6 out of 10', 'good']);
  assert.match(low.say[1], /some days are much louder/);
  const high = aircraftFinding({ score: 8, word: 'High', modelled: true }).tile;
  assert.equal(high.say[1], null);
  assert.equal(high.source, null, 'modelled with no source given prints none');
  assert.equal(aircraftFinding({ score: 2, word: 'Low' }).tile.source, 'Sky Score estimate from published flight routes');
});
const LAYER = [{ step: 1, from: 10 }, { step: 2, from: 50 }, { step: 3, from: 100 }, { step: 4, from: 200 }];
const planesFile = (figs) => planesModel(
  { district: 'SW11', postcodes: { 'SW11 1AA': { LHR: figs } }, none: [], approx: [], other: [] },
  { classes: ['westerly', 'easterly', 'mixed'], bar_full: 400, definition: 'D.', direction_rule: 'R.', credits: ['Flight tracks: adsb.lol (ODbL 1.0)'],
    airports: { LHR: { share_pct: { westerly: 56, easterly: 29, mixed: 15 }, months: ['202601', '202608'] } } },
  'SW11 1AA',
);
check("planes: the commonest one-way day on the face, a watch item from the layer's third step, every bar in the layer's colour", () => {
  const [f] = planesFindings(planesFile([318, 2, 188]), { steps: LAYER.map((s, i) => ({ ...s, colour: ['#dc8a4a', '#c2622a', '#9a4316', '#662809'][i] })) });
  assert.deepEqual([f.tile.level, f.tile.sub, f.tile.stand, f.tile.pill], ['318 a day', 'flying west', 'watch', 'Heathrow planes']);
  assert.equal(f.tile.visual[0].kind, 'chart', "the front page's chart, not bars (2026-11-11)");
  assert.deepEqual([...f.tile.visual[0].svg.matchAll(/data-mark="planes" [^>]*fill="(#[0-9a-f]{6})"/g)].map((m) => m[1]), ['#662809', '#9a4316', '#9a9893'],
    '318 and 188 in the colours of their steps (data/planes-layer/index.json); 2 is under the first, neutral');
  assert.match(T.tileHtml(f), /<div class="t-chart"><svg [^>]*data-planes-chart="LHR"/);
  assert.match(f.tile.source, /^Flight tracks: adsb\.lol \(ODbL 1\.0\), January to August 2026$/);
});
check('the planes tile names its main source; every other one stays in the fold (Bill, 2026-11-09)', () => {
  const credits = ['Flight tracks: adsb.lol (ODbL 1.0)', 'Weather at each airport: Iowa Environmental Mesonet',
    'Ground heights: Contains OS data © Crown copyright and database right', 'Postcode positions: ONS National Statistics Postcode Lookup (OGL)'];
  const model = { ...planesFile([318, 2, 188]), credits };
  const [f] = planesFindings(model);
  assert.equal(f.tile.source, 'Flight tracks: adsb.lol (ODbL 1.0), January to August 2026. Other sources below');
  assert.match(planesNotesHtml(model), /href="\/how-it-works\/#credits">All sources</, 'every other source is one link away (tests/test_credits_list.py holds the list)');
  const none = planesFindings({ ...model, airports: [], none: 'Fewer than 1 a day.' })[0];
  assert.ok(credits.every((c) => none.tile.source.includes(c)), 'no airport, no fold: every credit stays in sight');
  assert.equal(planesFindings(planesFile([90, 2, 40]), { steps: LAYER })[0].tile.stand, null, 'under the third step: not a watch item');
  assert.equal(planesFindings(planesFile([318, 2, 188]))[0].tile.stand, null, 'no layer steps: never a watch item');
});
check('pills: watch first, then good; aircraft noise is never "good" beside planes that are a watch item', () => {
  const pills = T.pillsFor([
    { key: 'aircraft', stand: 'good', pill: 'Aircraft noise' }, { key: 'planes', stand: 'watch', pill: 'Heathrow planes' },
    { key: 'price', stand: 'watch', pill: 'High prices' }, { key: 'transport', stand: 'good', pill: 'Transport' }, { key: 'path', stand: null, pill: null },
  ]).map((e) => e.pill);
  assert.deepEqual(pills, ['Heathrow planes', 'High prices', 'Transport']);
  assert.deepEqual(T.pillsFor([{ key: 'aircraft', stand: 'good', pill: 'Aircraft noise' }]).map((e) => e.pill), ['Aircraft noise']);
});
check('the nearest flight path: a ruler, the way planes fly from its runway, and "not under it" only when the map says so', () => {
  const t = pathFinding(1.27, { airport: 'Heathrow', name: 'LHR 27L final approach', under: false, record: 'UK AIP (NATS)' }).tile;
  assert.deepEqual([t.level, t.sub, t.say[0], t.say[1]], ['1.3 km away', 'not directly under it', 'Planes landing at Heathrow on days it flies west use this route.', 'You are not directly under it.']);
  const unsure = pathFinding(0.4, { airport: 'Heathrow', name: 'LHR 27L final approach' }).tile;
  assert.deepEqual([unsure.sub, unsure.say[1]], [null, null], 'no word from the map: nothing said about being under it');
  assert.match(pathFinding(2, { airport: 'Manchester', name: 'MAN 23R departure' }).tile.say[0], /^Planes taking off from Manchester on days it flies south-west/);
  assert.equal(pathFinding(2, {}).tile.say[0], 'This is the nearest published flight route.');
  assert.deepEqual([T.runwayHeading('LCY 09 final approach'), T.runwayHeading('no runway'), T.runwayHeading('XX 40')], ['east', null, null]);
  assert.match(T.tileHtml(pathFinding(1.27, { name: 'LHR 27L final approach' })), /<svg class="t-ruler"[^>]*aria-label="Landing route, 1\.3 km away"/);
});
check('crime in plain words, against a typical London borough only where the figures compare', () => {
  const t = crimeFinding({ band: 'medium', rate: 76.6, median: 87.6, council: 'Wandsworth' }).tile;
  assert.deepEqual(t.say, ['Wandsworth has 76.6 recorded crimes a year for every 1,000 people.', 'That is close to a typical London borough.']);
  assert.match(crimeFinding({ band: 'high', rate: 142.4, median: 87.6, council: 'K' }).tile.say[1], /^That is 1\.6 times a typical London borough\.$/);
  assert.equal(crimeFinding({ band: 'low', rate: 50, median: 87.6, council: 'K' }).tile.say[1], 'That is lower than a typical London borough.');
  const ny = crimeFinding({ band: 'medium', rate: 78, comparable: false, area: 'borough', council: 'Queens' }).tile;
  assert.equal(ny.say.length, 1, 'New York: no London yardstick');
  assert.doesNotMatch(JSON.stringify(crimeFinding({ band: 'high', rate: 190, median: 87.6, estimated: true })), /recorded/i);
});
check('price: a watch item under 3 of 10 affordability, and the change said in words', () => {
  const t = priceFinding({ price: '£694,210', trend: '-5.3%', council: 'Wandsworth', afford: 0.3, source: 'UK House Price Index' }).tile;
  assert.deepEqual([t.level, t.sub, t.stand, t.pill], ['£694,210', 'Wandsworth-wide', 'watch', 'High prices']);
  assert.deepEqual(t.say, ['The average price of a home in Wandsworth, 5.3% less than a year ago.', 'That gives it an affordability score of 0.3 out of 10.']);
  assert.equal(priceFinding({ price: '£1', afford: 3 }).tile.stand, null);
  assert.equal(priceFinding({ price: '£1' }).tile.visual[0], null, 'no affordability: no bar, never a zero');
});
check('a rating outside its own scale draws no strip: never a wrong picture', () => {
  const legacy = ratingFinding('schools', 'Schools', 'good', { council: 'Queens', area: 'borough' }).tile;
  assert.deepEqual(legacy.visual, [null]);
  assert.doesNotMatch(T.tileHtml({ key: 'schools', tile: legacy }), /t-strip/);
  const p8 = ratingFinding('schools', 'Schools', 'above average', { council: 'Wandsworth' }).tile;
  assert.equal(p8.visual[0].current, 'above average');
  assert.match(T.tileHtml({ key: 'schools', tile: p8 }), /<span class="on t-bg-good">Above<\/span>/);
});
check('nearest places: the list\'s own first row, said once', () => {
  const t = nearestFinding('transport', 'Transport', 'good', { name: 'Clapham Junction', dist: '416m' }, { council: 'Wandsworth' }).tile;
  assert.deepEqual(t.say, ['Clapham Junction is 416 m away.']);
  assert.equal(nearestFinding('transport', 'Transport', null, { name: 'A', dist: '1.2 km' }).tile.level, '1.2 km');
});
check('the energy rating draws its band among A to G; the last sale names its month', () => {
  const e = epcFinding({ available: true, count: 3, summary: { averageBand: 'D', averageRating: 67 } }).tile;
  assert.deepEqual([e.level, e.sub, e.visual[0].current], ['Band D', '67 out of 100', 'D']);
  const s = soldFinding([{ price: 1810000, type: 'flat-maisonette', category: 'A', date: '2025-01-10' }], (v) => `£${v}`).tile;
  assert.deepEqual([s.level, s.sub], ['£1810000', 'January 2025']);
});
check('every tile escapes what it is given', () => {
  const html = T.tileHtml(nearestFinding('t', 'Transport', 'good', { name: 'A "B" <c>', dist: '1m' }, { council: '<x>' }));
  assert.match(html, /A &quot;B&quot; &lt;c&gt;/);
  assert.match(html, /&lt;x&gt;-wide/);
  assert.equal(T.tileHtml(null), '');
});

// The map's verdict line (audit I-2, 2026-11-12): growth is said only from the GROWTH score. getVerdict() is lifted from
// index.html and run on its own, so the words tested are the words served; its claims read affordability until that day.
{
  const src = INDEX.match(/\r?\n( *)function getVerdict\(data\) \{[\s\S]*?\r?\n\1\}\r?\n/); // CRLF in a Windows checkout
  assert.ok(src, 'getVerdict() found in index.html');
  const getVerdict = new Function(`${src[0]}; return getVerdict;`)();
  const say = (scores, score) => getVerdict({ name: 'Here', score, scores });
  check('"strong growth" only with a strong growth score, never from affordability', () => {
    assert.doesNotMatch(say({ quiet: 8, afford: 9, growth: 3.2 }, 8), /growth/);
    assert.match(say({ quiet: 8, afford: 9, growth: 7.4 }, 8), /and strong growth/);
    assert.doesNotMatch(say({ quiet: 8, afford: 9 }, 8), /growth/, 'no growth score (the Bay Area): nothing said of growth');
  });
  check('"scores highly on affordability and growth" only with a high growth score', () => {
    assert.doesNotMatch(say({ quiet: 3, afford: 9, growth: 4 }, 8), /and growth/);
    assert.match(say({ quiet: 3, afford: 9, growth: 8 }, 8), /affordability and growth/);
  });
  check('"a balance of ... growth" only with a middling growth score or better', () => {
    assert.match(say({ quiet: 6, afford: 6, growth: 2 }, 6.5), /balance of quiet skies and affordability\./);
    assert.match(say({ quiet: 6, afford: 6, growth: 5.5 }, 6.5), /quiet skies, affordability, and growth\./);
    assert.match(say({ quiet: 6, afford: 6 }, 6.5), /balance of quiet skies and affordability\./);
  });
}

// The full map's district search (audit I-1, 2026-11-12): the council at the district's centre, never postcodes.io's
// alphabetical first. lookupPostcode() is lifted from index.html and run with a stand-in fetch holding the live answers of
// 12 Nov (TW15: Hounslow, Spelthorne; its centre's nearest postcode, TW15 2NT, is Spelthorne's).
{
  const src = INDEX.match(/\r?\n( *)async function lookupPostcode\(postcode, search\) \{[\s\S]*?\r?\n\1\}\r?\n/);
  assert.ok(src, 'lookupPostcode() found in index.html');
  const make = (answers) => {
    const asked = [];
    const fetch = async (url) => {
      asked.push(url);
      const hit = answers.find(([pattern]) => pattern.test(url));
      if (!hit) throw new TypeError('network');
      return { json: async () => hit[1] };
    };
    const fn = new Function('fetch', 'POSTCODE_SHAPE', 'searchSignal', 'SEARCH_TIMEOUT_MS', 'isAbortError', 'isTimeoutError',
      `${src[0]}; return lookupPostcode;`)(fetch, /^[A-Z]{1,2}\d[A-Z\d]?(\d[A-Z]{2})?$/, () => undefined, 1, (e) => e && e.name === 'AbortError', (e) => e && e.name === 'TimeoutError');
    return { fn, asked };
  };
  const NOT_FULL = [/\/postcodes\/TW15$/, { status: 404 }];
  const TW15 = [/\/outcodes\/TW15$/, { status: 200, result: { outcode: 'TW15', latitude: 51.43, longitude: -0.46, admin_district: ['Hounslow', 'Spelthorne'], admin_ward: ['Ashford East', 'Feltham North'] } }];
  const NEAR = [/\/postcodes\?lon=/, { status: 200, result: [{ postcode: 'TW15 2NT', admin_district: 'Spelthorne', admin_ward: 'Ashford Town' }] }];
  // A district spanning councils takes the council at its centre (top-level await: check() runs synchronously).
  const { fn, asked } = make([NOT_FULL, TW15, NEAR]);
  const got = await fn('TW15');
  assert.equal(got.result.admin_district, 'Spelthorne', 'TW15 is Spelthorne\'s, never the alphabetical Hounslow');
  assert.equal(got.result.admin_ward, 'Ashford Town');
  assert.ok(asked.some((u) => /\/postcodes\?lon=-0\.46&lat=51\.43/.test(u)), 'asked for the postcode nearest the centre');
  // A nearest postcode in a council the district does not list (over a boundary) is not taken.
  const off = await make([NOT_FULL, TW15, [/\/postcodes\?lon=/, { status: 200, result: [{ admin_district: 'Runnymede' }] }]]).fn('TW15');
  assert.equal(off.result.admin_district, 'Hounslow', 'only a council the district lists counts');
  // The second lookup failing keeps the search working, on the old answer.
  const failed = await make([NOT_FULL, TW15]).fn('TW15');
  assert.ok(failed.result && failed.failure === null, 'a failed centre lookup never fails the search');
  // One council: no second request.
  const one = make([[/\/postcodes\/SW5$/, { status: 404 }], [/\/outcodes\/SW5$/, { status: 200, result: { outcode: 'SW5', latitude: 51.49, longitude: -0.19, admin_district: ['Kensington and Chelsea'], admin_ward: ['Earl\'s Court'] } }]]);
  assert.equal((await one.fn('SW5')).result.admin_district, 'Kensington and Chelsea');
  assert.ok(!one.asked.some((u) => /\?lon=/.test(u)), 'a district in one council asks nothing more');
  passed += 4; // centre taken, a listed council only, failure kept working, one council asks nothing more
}

// The Healthcare card names the record's own source (audit I-12, 2026-11-12): it printed the registry's "NOT SOURCED" in
// nine UK cities while every record named the NHS Organisation Data Service. Both halves held: the data, and the card.
check('every rated UK healthcare record names its source, and the card reads it', () => {
  const extra = JSON.parse(readFileSync(new URL('../data/borough-extra.json', import.meta.url), 'utf8'));
  const missing = Object.entries(extra).filter(([city]) => city !== 'nyc').flatMap(([city, block]) =>
    Object.entries(block || {}).filter(([, r]) => r && typeof r === 'object' && r.healthcare && !r.healthcareVintage).map(([name]) => `${city}/${name}`));
  assert.deepEqual(missing, [], 'a UK record rated for healthcare without its source');
  // The card as drawn: buildOptionalSections() lifted from index.html and run on real records (a text match on the source
  // passed with the line broken, 2026-11-12).
  const src = INDEX.match(/\r?\n( *)function buildOptionalSections\(extra, sectionId\) \{[\s\S]*?\r?\n\1\}\r?\n/);
  assert.ok(src, 'buildOptionalSections() found in index.html');
  const REGISTRY = { westmidlands: 'NHS TRUST DATA (NOT SOURCED)', nyc: 'NYC HEALTH+HOSPITALS DATA (CURATED)' };
  const build = (city) => new Function('metricColor', 'ratingBadgeClass', 'cityOf', 'currentCity', `${src[0]}; return buildOptionalSections;`)(
    () => '#000', () => '', (c) => ({ healthSource: REGISTRY[c] }), city);
  const healthLine = (html) => (html.match(/id="[^"]*-nhs">[\s\S]*?<div class="defra-badge"[^>]*>([^<]*)<\/div>/) || [])[1] || '';
  const brum = Object.values(extra.westmidlands).find((r) => r && r.healthcare);
  const line = healthLine(build('westmidlands')(brum, 'test'));
  assert.ok(/NHS Organisation Data Service/.test(line) && !/NOT SOURCED/.test(line), `a West Midlands card names the NHS register: ${line}`);
  const nyc = Object.values(extra.nyc).find((r) => r && r.healthcare);
  assert.equal(healthLine(build('nyc')(nyc, 'test')), 'SOURCE: NYC HEALTH+HOSPITALS DATA (CURATED)', 'New York, with no source of its own, keeps its line');
});

console.log(`PASS ${passed} of ${passed}`);
