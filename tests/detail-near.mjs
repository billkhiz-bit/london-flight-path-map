// "All the detail", option 1 (Bill's pick, 2026-11-08): the picture of what is within 1 km and the card faces, as plain
// answers in and plain text out. No browser: every branch is reached on purpose, from the routes' real shapes.
import { strict as assert } from 'node:assert';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import {
  KINDS, LANE_M, NAPTAN_CAP, ROUTE_CAP, countWords, distanceParts, epcFace, faceHtml, healthFace, lanesSvg, lineStatusFace,
  nearestFace, placesByKind, placesListHtml, stationName,
} from '../js/detail-near.mjs';

let passed = 0;
const check = (name, fn) => {
  try { fn(); passed += 1; } catch (e) { e.message = `${name}: ${e.message}`; throw e; }
};
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), 'utf8');

// SW11 1AA as /nhs and /transport answered on 2026-11-09.
const NHS = {
  available: true,
  gp: [['Battersea Rise Surgery', 407], ['Bupa Clapham', 445], ['The Glass House', 497], ['The Junction Health Centre', 515],
    ['Stormont Health Clinic', 599]].map(([name, distance]) => ({ name, distance })),
  pharmacies: [['Boots', 144], ['Robards Pharmacy', 409], ['Goys the Chemist', 524], ['Day Lewis Pharmacy', 564],
    ['Barkers (Chemist)', 620]].map(([name, distance]) => ({ name, distance })),
  hospitals: [{ name: 'Bridge Lane Health Centre', distance: 991 }],
};
const TFL = {
  available: true,
  stations: [{ name: 'Clapham Junction Rail Station', distance: 416, lines: ['mildmay', 'southern'] }],
  lineStatus: [{ name: 'Mildmay', status: 'Good Service' }, { name: 'Southern', status: 'Special Service' },
    { name: 'South Western Railway', status: 'Part Closure' }],
  lineStatusAvailable: true,
};

// The caps are the routes' own, read from them, never retyped (a parity claim is a claim about a holder).
check('ROUTE_CAP equals both Lambdas', () => {
  assert.match(read('backend/lambdas/nhs/app.py'), new RegExp(`^MAX_RESULTS_PER_TYPE = ${ROUTE_CAP}$`, 'm'));
  assert.match(read('backend/lambdas/transport/app.py'), new RegExp(`return results\\[:${ROUTE_CAP}\\]`));
});
check('NAPTAN_CAP equals the map', () => {
  assert.match(read('index.html'), new RegExp(`nearestStations\\(lat, lon, ${NAPTAN_CAP}\\)`));
});

check('places within 1 km, nearest first, station names as the panel shows them', () => {
  const p = placesByKind({ transport: TFL, nhs: NHS });
  assert.deepEqual(p.stations, [{ name: 'Clapham Junction', m: 416 }]);
  assert.equal(p.pharmacies[0].name, 'Boots');
  assert.equal(p.hospitals.length, 1);
  assert.ok(Object.values(p).filter(Array.isArray).every((list) => list.every((x) => x.m <= LANE_M)));
});
check('a place past 1 km is left off the line but still counts towards the cap test', () => {
  const p = placesByKind({ nhs: { ...NHS, gp: [...NHS.gp.slice(0, 4), { name: 'Far', distance: 1400 }] } });
  assert.equal(p.gp.length, 4);
  assert.equal(p.mayBeMore.gp, false, 'the route sent one beyond the reach, so all within it were sent');
});
check('a full cap all within reach may hide more', () => {
  const p = placesByKind({ transport: TFL, nhs: NHS });
  assert.deepEqual(p.mayBeMore, { stations: false, gp: true, pharmacies: true, hospitals: false });
});

// ABSENCE: never asked is no line; asked and found nothing within 1 km is an empty line, which is a reading.
check('never asked: no line, no card', () => {
  const p = placesByKind({ transport: TFL });
  assert.equal(p.gp, null);
  assert.equal(nearestFace('gp', p), null);
  assert.ok(!lanesSvg('SW11 1AA', p).includes('Doctors'));
});
check('nothing asked at all: no picture', () => assert.equal(lanesSvg('SW11 1AA', placesByKind({})), null));
check('a route that failed is not asked', () => {
  const p = placesByKind({ transport: { available: false }, nhs: { available: false } });
  assert.deepEqual([p.stations, p.gp], [null, null]);
});
// /nhs's two link rows, made by the route itself (backend/lambdas/nhs/app.py), never typed here: a self-written fixture
// hid that a measured "none within 1.5 km" carries `link` too (audit I-1, 2026-11-09). TW9 3PZ's hospitals answered so live.
const ROUTE_ROWS = JSON.parse(execFileSync('python', ['-c',
  "import json, app; print(json.dumps({'none': app.none_nearby('GP'), 'fallback': app.fallback_links('GP')}))"],
{ cwd: fileURLToPath(new URL('../backend/lambdas/nhs/', import.meta.url)), encoding: 'utf8' }));
check('the route\'s two link rows are told apart by what the route says, not by `link`', () => {
  assert.equal(ROUTE_ROWS.none[0].noneNearby, true);
  assert.equal(ROUTE_ROWS.none[0].fallback, false);
  assert.equal(ROUTE_ROWS.fallback[0].fallback, true);
});
check('fallback search links are not places: Overpass failed, the kind was not measured', () => {
  const p = placesByKind({ nhs: { ...NHS, gp: ROUTE_ROWS.fallback } });
  assert.equal(p.gp, null);
  assert.ok(Array.isArray(p.pharmacies));
});
check('a measured "none within 1.5 km" is a reading: an empty line, and the card says none', () => {
  const p = placesByKind({ nhs: { ...NHS, hospitals: ROUTE_ROWS.none } });
  assert.deepEqual(p.hospitals, []);
  assert.equal(nearestFace('hospitals', p), null);
  assert.match(lanesSvg('TW9 3PZ', p), /No hospital/);
  const none = placesByKind({ nhs: { available: true, gp: ROUTE_ROWS.none, pharmacies: ROUTE_ROWS.none, hospitals: ROUTE_ROWS.none } });
  assert.deepEqual(healthFace(none), { k: 'Doctors and clinics', v: 'None', unit: '', l: 'within 1 km · No pharmacy · No hospital' });
});
check('asked and none within 1 km: the line stays, empty; the card still names the nearest, in km', () => {
  const p = placesByKind({ nhs: { ...NHS, hospitals: [{ name: 'St Far', distance: 1300 }] } });
  assert.deepEqual(p.hospitals, []);
  assert.deepEqual(nearestFace('hospitals', p), { k: 'Nearest hospital', v: '1.3', unit: 'km', l: 'St Far' });
  assert.match(lanesSvg('SW11 1AA', p), /No hospital/);
});
check('asked and the source sent none: no card', () => {
  const p = placesByKind({ nhs: { ...NHS, hospitals: [] } });
  assert.deepEqual(p.hospitals, []);
  assert.equal(nearestFace('hospitals', p), null);
});
check('the healthcare card counts doctors and clinics, the other kinds under it', () => {
  const p = placesByKind({ nhs: NHS });
  assert.deepEqual(healthFace(p), { k: 'Doctors and clinics', v: '5 or more', unit: '', l: 'within 1 km · 5 or more pharmacies · 1 hospital' });
  const few = placesByKind({ nhs: { ...NHS, gp: NHS.gp.slice(0, 2) } });
  assert.equal(healthFace(few).v, '2');
  assert.equal(healthFace(placesByKind({ nhs: { ...NHS, gp: [] } })).v, 'None');
  assert.equal(healthFace(placesByKind({ transport: TFL })), null, 'never asked outside London');
});
check('the energy card says which absence it is', () => {
  assert.equal(epcFace(null), null);
  assert.equal(epcFace({ available: false }).v, 'Not loaded');
  assert.equal(epcFace({ available: false, fullPostcodeOnly: true }).v, 'Full postcode');
  assert.equal(epcFace({ available: true, count: 0 }).v, 'None yet');
  assert.deepEqual(epcFace({ available: true, count: 3, summary: { averageBand: 'D', averageRating: 62 } }),
    { k: 'Energy rating', v: 'Band D', unit: '', l: '62 out of 100, from 3 certificates' });
  assert.equal(epcFace({ available: true, count: 1, summary: { averageBand: 'C', averageRating: '' } }).l, 'from 1 certificate');
});
check('faces and lists are escaped, units kept with their figures', () => {
  const html = faceHtml({ k: 'Nearest <x>', v: '416', unit: 'm', l: 'A & B', tone: 'watch' });
  assert.equal(html, '<span class="t-name">Nearest &lt;x&gt;</span><span class="dc-v dc-watch">416 <small>m</small></span><span class="t-sub">A &amp; B</span>');
  assert.equal(placesListHtml([{ name: '<b>', m: 1250 }]), '<ul class="dc-list"><li><span>&lt;b&gt;</span><b>1.3 km</b></li></ul>');
  assert.deepEqual(distanceParts(999), { v: '999', unit: 'm' });
  assert.deepEqual(distanceParts(1000), { v: '1.0', unit: 'km' });
});
check('TfL empty: the NaPTAN rows stand in, in metres', () => {
  const p = placesByKind({ transport: { available: true, stations: [] }, naptan: [{ name: 'Leeds', km: 0.62 }] });
  assert.deepEqual(p.stations, [{ name: 'Leeds', m: 620 }]);
});
check('NaPTAN full cap within reach may hide more', () => {
  const four = [0.2, 0.4, 0.6, 0.8].map((km, i) => ({ name: `S${i}`, km }));
  assert.equal(placesByKind({ naptan: four }).mayBeMore.stations, true);
  assert.equal(placesByKind({ naptan: four.slice(0, 3) }).mayBeMore.stations, false);
});

check('counts: zero is a reading, one is singular, a full cap is a floor', () => {
  assert.equal(countWords(0, false, 'pharmacy', 'pharmacies'), 'No pharmacy');
  assert.equal(countWords(1, false, 'station', 'stations'), '1 station');
  assert.equal(countWords(3, false, 'pharmacy', 'pharmacies'), '3 pharmacies');
  assert.equal(countWords(5, true, 'pharmacy', 'pharmacies'), '5 or more pharmacies');
});

check('the picture: one line per kind asked, every place a dot, its description from countWords', () => {
  const svg = lanesSvg('SW11 1AA', placesByKind({ transport: TFL, nhs: NHS }));
  assert.equal((svg.match(/<circle /g) || []).length, 12);
  assert.match(svg, /aria-label="Within 1 km of SW11 1AA: 1 station, 5 or more doctors and clinics, 5 or more pharmacies, 1 hospital"/);
  for (const k of KINDS) assert.ok(svg.includes(`>${k.short || k.plural}<`), k.key);
  assert.ok(!/#[0-9a-f]{3,6}/i.test(svg), 'colours come from the map\'s tokens, never typed');
});
check('names are escaped', () => {
  const svg = lanesSvg('SW11 1AA', placesByKind({ nhs: { gp: [{ name: '<b>A & B</b>', distance: 100 }] } }));
  assert.ok(svg.includes('&lt;b&gt;A &amp; B&lt;/b&gt;') && !svg.includes('<b>'));
});
check('dots sit on the scale: 0 m at the line start, 1 km at its end', () => {
  const svg = lanesSvg('X', placesByKind({ nhs: { gp: [{ name: 'Zero', distance: 0 }, { name: 'Edge', distance: 1000 }] } }));
  assert.match(svg, /cx="104.0"/);
  assert.match(svg, /cx="288.0"/);
});

check('nearest faces', () => {
  const p = placesByKind({ transport: TFL, nhs: NHS });
  assert.deepEqual(nearestFace('stations', p), { k: 'Nearest station', v: '416', unit: 'm', l: 'Clapham Junction' });
  assert.deepEqual(nearestFace('gp', p), { k: 'Nearest doctor', v: '407', unit: 'm', l: 'Battersea Rise Surgery' });
  assert.equal(nearestFace('nope', p), null);
});

check('line status: the first line not on good service leads', () => {
  assert.deepEqual(lineStatusFace(TFL), { k: 'Line status today', v: 'Special Service', tone: 'watch', l: 'Southern and 1 more' });
});
check('line status: all good says so', () => {
  const f = lineStatusFace({ ...TFL, lineStatus: [{ name: 'Mildmay', status: 'Good Service' }] });
  assert.deepEqual(f, { k: 'Line status today', v: 'Good service', tone: 'good', l: 'Mildmay' });
});
check('line status: not checked is never good service by silence', () => {
  const f = lineStatusFace({ ...TFL, lineStatus: [], lineStatusAvailable: false });
  assert.equal(f.v, 'Not checked');
});
check('line status: nothing listed, or TfL down, says nothing', () => {
  assert.equal(lineStatusFace({ ...TFL, lineStatus: [] }), null);
  assert.equal(lineStatusFace({ available: false }), null);
  assert.equal(lineStatusFace(null), null);
});
check('station names lose TfL\'s suffixes only', () => {
  assert.equal(stationName('Clapham Junction Rail Station'), 'Clapham Junction');
  assert.equal(stationName('Oval Underground Station'), 'Oval');
  assert.equal(stationName('Rail Station Road'), 'Rail Station Road');
});

check('the map detailDistance() is distanceParts() in km', () => {
  const src = read('index.html').match(/function detailDistance\(km\) \{[\s\S]*?\r?\n {6}\}/);
  assert.ok(src, 'detailDistance() not found in index.html');
  const detailDistance = new Function(`${src[0]}; return detailDistance;`)();
  for (const km of [0, 0.4164, 0.9994, 0.9996, 1, 1.25, 18.7]) assert.deepEqual(detailDistance(km), distanceParts(Math.round(km * 1000)), km);
});

const checkAsync = async (name, fn) => {
  try { await fn(); passed += 1; } catch (e) { e.message = `${name}: ${e.message}`; throw e; }
};

// The review's finding (2026-11-09): a late answer from an earlier search reset the shared state before the guard ran,
// so the current search lost an answer that had already landed (in London TfL's, leaving the station card hidden).
await checkAsync('a late answer from an earlier search leaves the current one\'s answers alone', async () => {
  const src = read('index.html').match(
    /const _detail = \{ req: null, answers: \{\} \};\r?\n {6}function fillDetail\(req, analysis, part, data\) \{[\s\S]*?\r?\n {6}\}/,
  );
  assert.ok(src, 'fillDetail() not found in index.html');
  const seen = [];
  const m = {
    NAPTAN_CAP,
    placesByKind: (answers) => { seen.push(answers); return { all: {}, mayBeMore: {} }; },
    nearestFace: () => null, healthFace: () => null, lineStatusFace: () => null, epcFace: () => null,
    lanesSvg: () => '', faceHtml: () => '', placesListHtml: () => '',
  };
  const searchSeq = 2;
  const fillDetail = new Function(
    'isCurrentSearch', 'loadDetail', 'isUkCity', 'currentCity', 'STATIONS_STATE', 'nearestStations', 'document', 'tidyDetailCards',
    `${src[0]}; return fillDetail;`,
  )(
    (s) => !!s && s.token === searchSeq, () => Promise.resolve(m), () => true, 'london', 'ready', () => [],
    { getElementById: () => null }, () => {},
  );
  const earlier = { token: 1 };
  const current = { token: 2 };
  const analysis = { postcode: 'SW11 1AA', lat: 51.4643, lon: -0.1704 };
  const tfl = { available: true, stations: [{ name: 'Clapham Junction Rail Station', distance: 160 }] };
  await fillDetail(current, analysis, 'transport', tfl);
  await fillDetail(earlier, analysis, 'nhs', NHS);
  await fillDetail(current, analysis, 'nhs', NHS);
  assert.equal(seen.at(-1).transport, tfl, 'the current search lost its TfL answer');
  assert.equal(seen.length, 2, 'the earlier search\'s answer reached the cards');
});

console.log(`detail-near: ${passed} checks passed`);
