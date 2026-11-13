/**
 * The street report as the site draws it (Bill's pick C with the small print bigger, 2026-11-11; mock-up
 * claude.ai/artifact/1HZDc4VDRGxVUL791DMewp v5), held without a browser: js/street_report.mjs reportParts() is pure, so
 * every branch C added is reached on purpose here, from real routes (data/flight-procedures.json, tracked) and planes,
 * air and district inputs written below in the shapes their builders give. The free copy is read in a browser by
 * tests/front-page.mjs (block 18); the PDF's three pages and its 8 pt floor are measured by printing it
 * (scripts/address_noise_report.mjs refuses a third page; docs/lessons/front-page-and-site.md says how to measure type).
 *
 *   node tests/street-report.mjs
 */
import { execFileSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const ROOT = process.cwd();
const url = (p) => pathToFileURL(join(ROOT, p)).href;
const m = await import(url('js/street_report.mjs'));
const { planesModel } = await import(url('js/planes.mjs'));
const { answerLead } = await import(url('js/answer-lead.mjs'));
const { plane, routesNear } = await import(url('js/flight_geometry.mjs'));

let failed = 0;
let passed = 0;
const ok = (cond, name, detail = '') => {
  if (cond) passed++;
  else failed++;
  console.log(`${cond ? '  ok  ' : '  FAIL'} ${name}${cond || !detail ? '' : `: ${detail}`}`);
};

// ---- 1. The import cycle (street_report -> answer-lead/panel-findings -> planes -> street_report) loads whichever
// module comes first: each order in a fresh process, every export used here defined.
for (const first of ['street_report', 'planes', 'panel-findings', 'answer-lead']) {
  const code = `const a = await import(${JSON.stringify(url(`js/${first}.mjs`))});
const sr = await import(${JSON.stringify(url('js/street_report.mjs'))}); const pl = await import(${JSON.stringify(url('js/planes.mjs'))});
const pf = await import(${JSON.stringify(url('js/panel-findings.mjs'))}); const al = await import(${JSON.stringify(url('js/answer-lead.mjs'))});
process.stdout.write([sr.reportParts, sr.esc, sr.airRows, pl.planesChart, pf.pictureHtml, pf.roadFinding, al.answerLead].every((f) => typeof f === 'function') ? 'yes' : 'no');`;
  let out = '';
  try {
    out = execFileSync(process.execPath, ['--input-type=module', '-e', code], { encoding: 'utf8' });
  } catch (e) {
    out = String(e.stderr || e.message).slice(0, 160);
  }
  ok(out === 'yes', `the modules load with ${first}.mjs first, the cycle through planes.mjs included`, out);
}

// ---- inputs, in the shapes their builders give
const KEW = { lat: 51.476982, lon: -0.285639 };
const proc = JSON.parse(await readFile(join(ROOT, 'data', 'flight-procedures.json'), 'utf8'));
const covid = JSON.parse(await readFile(join(ROOT, 'data', 'covid-understatement.json'), 'utf8'));
const routes = routesNear(proc, plane(KEW.lat, KEW.lon), m.SCOPE_KM);
const OVERHEAD = 'Overhead means more than halfway up the sky (48.5 degrees or more) and below 7,000 ft, the CAA’s definition of an overflight (CAP 1498).';
const info = {
  classes: ['westerly', 'easterly', 'mixed'],
  bar_full: 629,
  definition: OVERHEAD,
  direction_rule: 'A day counts as one way when 80% of its flights used that way.',
  postcodes_rule: 'PO boxes and other postcodes for organisations that receive a lot of post are left out: they sit at a delivery office or a business, not at homes.',
  credits: ['Flight tracks: adsb.lol (ODbL 1.0)'],
  airports: {
    LHR: { share_pct: { westerly: 56, easterly: 29, mixed: 15 }, months: ['202601', '202608'] },
    LCY: { share_pct: { westerly: 47, easterly: 35, mixed: 18 }, months: ['202601', '202608'] },
  },
};
// London City listed FIRST and quieter: the report must lead with the busier airport, the one the headline names.
const twoFile = { postcodes: { 'TW9 3PZ': { LCY: ['<1', 2, 1], LHR: [310, 4, 168] } }, none: [], approx: [], other: [] };
const oneFile = { postcodes: { 'TW9 3PZ': { LHR: [310, 4, 168] } }, none: [], approx: [], other: [] };
const steps = [{ from: 0, colour: '#fde6d2' }, { from: 100, colour: '#f4a46b' }, { from: 300, colour: '#c2410c' }];
const measuredEnv = {
  aircraftNoiseLdenDb: 57.2, aircraftNoiseWhoGuidelineDb: 45, aircraftQuiet: 3.2, aircraftQuietCoverage: 'modelled',
  roadNoiseLdenDb: 50.5, roadNoiseWhoGuidelineDb: 53,
  no2AnnualMeanUgm3: 17.0, pm25AnnualMeanUgm3: 8.5, no2WhoGuidelineUgm3: 10, pm25WhoGuidelineUgm3: 5,
  airQualitySource: 'DEFRA background',
};
const provenance = {
  'environment.no2AnnualMeanUgm3': { method: 'modelled', resolution: '1 km grid', period: '2024' },
  'environment.pm25AnnualMeanUgm3': { method: 'modelled', resolution: '1 km grid', period: '2024' },
  'environment.roadNoiseLdenDb': { method: 'modelled', period: '2021' },
};
const sensor = {
  name: 'George Street', km: 2.2, classification: 'Roadside', kerbDistanceM: 0.7, to: '2026-09-30',
  no2: { mean: 18.7 }, pm25: { mean: 7.5 },
  credit: { text: 'Contains Breathe London data licensed under the Open Government License v3.0', href: 'https://www.breathelondon.org/' },
};
const district = { n: 597, outcode: 'TW9', quieterPct: 61, louderPct: 29, bins: [0, 0, 40, 210, 60, 20, 10, 0, 0, 0], mineBin: 3 };
const base = (over = {}) => ({
  postcode: 'TW9 3PZ', council: 'Richmond upon Thames', hasRaster: true, resolvedAs: null, notices: [],
  env: measuredEnv, provenance, routes, district, covid, airac: '2026-10-29', map: '<svg></svg>',
  station: { name: 'Kew Gardens', km: 0.02 }, sensor, monitor: null,
  planes: { model: planesModel(oneFile, info, 'TW9 3PZ'), steps },
  ...over,
});
const doc = (f) => m.reportParts({ postcode: 'TW9 3PZ', place: 'Kew', sample: true }, f);
const count = (s, needle) => s.split(needle).length - 1;

// ---- 2. Kew: measured, under the 27R approach, one airport, a district chart
{
  const f = base();
  const { body, css } = doc(f);
  const lead = answerLead(f.env, 'TW9 3PZ', f.planes.model, steps);
  ok(Boolean(lead) && body.includes(`<p class="lead">${m.esc(lead)}</p>`), "the headline is answerLead()'s sentence for this place, the full map's and the front page's", lead);
  ok(!body.includes('<h2>What this shows</h2>'), 'a measured postcode under an approach has no "What this shows": each of its lines repeated a tile, a row or a chart');
  ok(/<div class="district">[\s\S]*<p class="cap fact">Of the 597 postcodes in TW9 on DEFRA's map, <strong>61% are quieter<\/strong> than this one and 29% are louder\.<\/p><\/div>/.test(body),
    "the district's shares are its chart's caption, word for word as the line said them");
  ok(count(body, 'data-planes-chart=') === 1 && body.includes('<h2>Planes overhead a day, from Heathrow</h2>'), 'one counted airport: one planes chart, named in its heading');
  ok(count(body, OVERHEAD.slice(0, 40)) === 1, 'the overhead rule is said once, under the chart');
  ok(['A day counts as one way', 'PO boxes and other postcodes', "checked against the CAA's monthly totals"].every((t) => body.includes(m.esc(t))),
    "the planes' other rules are reading points, word for word from airports.json");
  ok(body.includes('Planes overhead: Flight tracks: adsb.lol (ODbL 1.0).'), "the flight tracks' credit is in the sources");
  ok(count(body, 'class="t-bar"') === 2 && body.includes('This postcode') && body.includes('The WHO recommends at most') && body.includes("DEFRA's modelled figure for 2021."),
    "road noise is the full map's two bars, the postcode's modelled figure against the WHO's, its year said");
  ok(['no2', 'pm25'].every((p) => body.includes(`data-air-chart="${p}"`)), 'the air is the full map\'s two charts');
  ok(body.includes('Breathe London sensor, low-cost, provisional.') && !body.includes('Breathe London sensors are low-cost'),
    "the sensor's key says low-cost and provisional, so the note does not say it again");
  ok(body.includes('<p class="note"><strong>Nearest station:</strong> Kew Gardens, 20 m in a straight line.</p>'), 'the nearest station is its own line');
  ok(/<p class="say">[\s\S]*class="chip" href="https:\/\/webtrak\.emsbk\.com\/lhr6"[\s\S]*Spotted something wrong\?/.test(body), 'have your say is a row of buttons, then the correction address');
  ok(count(body, '<section class="page">') === 3 && /\.page \{ break-after: page; \}/.test(css) && /\.blk[^{]*\{[^}]*break-inside:\s*avoid/.test(css),
    'three fixed pages (Bill\'s pick, 2026-11-11 v2), each section whole within its page');
  ok(/body \{[^}]*font-size: 10\.5pt;/.test(css) && /table \{[^}]*font-size: 10\.5pt;/.test(css) && /\.note \{ font-size: 10\.5pt;/.test(css)
      && /\.cap \{ font-size: 9\.5pt;/.test(css) && /\.key \.l \{ font-size: 9\.5pt;/.test(css) && /footer \{[^}]*font-size: 8\.5pt;/.test(css),
    'the bigger text Bill asked for: body and table 10.5 pt, notes 10.5, labels and captions 9.5, sources 8.5');
  ok(!/font-size: [0-7](\.\d+)?pt/.test(css), 'no type under 8 pt anywhere in the stylesheet', (css.match(/font-size: [0-7](\.\d+)?pt/) || [''])[0]);
  ok(body.includes('A desktop report from published data: no site visit or survey.') && body.includes('It is not a conveyancing search under the Search Code. Our terms: skyscore.co.uk/terms.'),
    'it says it is a desktop report, and not a conveyancing search');
}

// ---- 3. Two airports: one heading, the busiest first, the rule once
{
  const f = base({ planes: { model: planesModel(twoFile, info, 'TW9 3PZ'), steps } });
  const { body } = doc(f);
  const order = [...body.matchAll(/data-planes-chart="([A-Z]+)"/g)].map((x) => x[1]);
  ok(order.join() === 'LHR,LCY', 'the busier airport comes first, the one the headline names, whatever order the file lists them in', order.join());
  ok(count(body, '<h2>Planes overhead a day</h2>') === 1 && body.includes('<p class="from">From Heathrow</p>') && body.includes('<p class="from">From London City</p>'),
    'two airports share one heading, each chart labelled');
  ok(count(body, OVERHEAD.slice(0, 40)) === 1, 'the overhead rule is said once for both');
}

// ---- 4. Not counted, no DEFRA figure, a surveyed-quiet road, no air instrument
{
  const env = { aircraftQuietEstimated: 7.1, aircraftQuietCoverage: 'city', roadNoiseBelowDb: 45, roadNoiseWhoGuidelineDb: 53 };
  const f = base({ env, provenance: {}, district: null, sensor: null, station: null, planes: { model: null, steps }, notices: ['No aircraft noise contour covers this postcode.'] });
  const { body } = doc(f);
  ok(!body.includes('What this shows') && /<div class="keys">[\s\S]*?<\/div>\s*<p class="cap moved why">No aircraft noise contour covers this postcode\.<\/p>/.test(body),
    'without a DEFRA figure, the line under the key figures says why, in the endpoint\'s words, and no "What this shows" heading (mock-up v3)');
  ok(!body.includes('data-planes-chart') && !body.includes('Planes overhead'), 'a postcode not counted says nothing of planes');
  ok(body.includes('Road noise at this postcode') && !body.includes('class="t-bar"') && body.includes('45 dB or above'),
    "a surveyed-quiet bound is said in the map's words and draws no bar: it is no reading");
  ok(!body.includes('data-air-chart') && !body.includes('Nearest station'), 'nothing to chart and no station: neither is drawn');
  ok(!body.includes('Of the ') || !body.includes('class="cap fact"'), 'no district, no district line');
}

// ---- 5. Neither road figure: no road block (absence is never drawn as a reading)
{
  const env = { ...measuredEnv };
  delete env.roadNoiseLdenDb;
  const { body } = doc(base({ env }));
  ok(!body.includes('Road noise at this postcode'), 'no road figure and no bound: no road block');
}

// ---- 6. The 12 Nov audit's three report findings, each reached on purpose
{
  // A-11: the API answered for a neighbour. Its road reading is not this postcode's (neighbours differ by 20 dB).
  const { body } = doc(base({ resolvedAs: 'TW9 3PQ' }));
  const at = body.indexOf('<div class="road blk">');
  const roadHtml = at < 0 ? '' : body.slice(at, body.indexOf('</div>', at) + 6); // the district chart says "This postcode" too
  ok(!body.includes('class="t-bar"') && !roadHtml.includes('This postcode') && roadHtml.includes('is for TW9 3PQ, the nearest postcode, not TW9 3PZ'),
    "a neighbour's road reading is never drawn as this postcode's: the block says whose it is and draws nothing", roadHtml.slice(0, 160));
}
{
  // A-9: under 1 a day from every counted airport is a figure: it carries the rules and the credit.
  const noneFile = { postcodes: {}, none: ['TW9 3PZ'], approx: [], other: [] };
  const { body } = doc(base({ planes: { model: planesModel(noneFile, info, 'TW9 3PZ'), steps } }));
  ok(body.includes('Under 1 a day from each of the') && count(body, OVERHEAD.slice(0, 40)) === 1, '"under 1 a day" carries the overhead rule once');
  ok(['A day counts as one way', 'PO boxes and other postcodes', "checked against the CAA's monthly totals"].every((t) => body.includes(m.esc(t))),
    '"under 1 a day" carries the other rules, word for word');
  ok(body.includes('Planes overhead: Flight tracks: adsb.lol (ODbL 1.0).'), '"under 1 a day" carries the flight tracks\' credit');
}
{
  // A-1: no airport with verified pages (none in scope here): no "Have your say" label over nothing.
  const { body } = doc(base({ routes: { scope: [], finals: [], departures: [], airports: [] } }));
  ok(!body.includes('Have your say') && body.includes('Spotted something wrong?'), 'no verified pages: no "Have your say" label, the correction address stays');
}

// ---- 7. Page 1's cards: the one verdict rule (glanceCards), each case reached on purpose
const cardsOf = (body) => [...body.matchAll(/<div class="card (\w+)" data-card="(\w+)">[\s\S]*?<div class="fig">([^<]*)<\/div>/g)].map((x) => ({ stand: x[1], key: x[2], fig: x[3] }));
{
  // Kew: DEFRA's figure over the WHO's, the busiest airport over the layer's watch step, road under the WHO's, air.
  const c = cardsOf(doc(base()).body);
  ok(c.map((x) => x.key).join() === 'aircraft,planes,road,air', 'Kew has four cards, in the order of the pages', c.map((x) => x.key).join());
  const by = Object.fromEntries(c.map((x) => [x.key, x]));
  ok(by.aircraft.stand === 'watch' && by.aircraft.fig === "57 dB on DEFRA&#39;s map, over the WHO guideline of 45", 'aircraft noise: DEFRA\'s own figure over the WHO guideline is "Worth a look", in whole dB as the key figure gives it', JSON.stringify(by.aircraft));
  ok(by.planes.stand === 'watch' && by.planes.fig === 'Heathrow: 310 a day when flying west', 'planes: the map\'s own watch step (310 is past the layer\'s third step, 300)', JSON.stringify(by.planes));
  ok(by.road.stand === 'good' && by.road.fig === '50.5 dB, under the WHO guideline of 53', 'road: the postcode\'s own figure under the WHO guideline is "Good here"', JSON.stringify(by.road));
  ok(by.air.stand === 'none', 'air never gets a verdict: "For context"', JSON.stringify(by.air));
  const body = doc(base()).body;
  ok(body.includes('<i aria-hidden="true">!</i>Worth a look') && body.includes('<i aria-hidden="true">✓</i>Good here') && body.includes('<i aria-hidden="true">–</i>For context'),
    'each verdict is a mark and a word, never colour alone');
}
{
  // The map's rule: aircraft noise is never "Good here" beside planes that are a watch item.
  const env = { ...measuredEnv, aircraftNoiseLdenDb: 40.0 };
  const c = cardsOf(doc(base({ env })).body);
  ok(c.find((x) => x.key === 'aircraft').stand === 'none', 'aircraft under the WHO guideline beside a planes watch item gets no verdict', JSON.stringify(c));
  const quietPlanes = { postcodes: { 'TW9 3PZ': { LHR: [20, 4, 12] } }, none: [], approx: [], other: [] };
  const c2 = cardsOf(doc(base({ env, planes: { model: planesModel(quietPlanes, info, 'TW9 3PZ'), steps } })).body);
  ok(c2.find((x) => x.key === 'aircraft').stand === 'good' && c2.find((x) => x.key === 'planes').stand === 'none',
    'with few planes, aircraft under the WHO guideline is "Good here" and the planes get no verdict', JSON.stringify(c2));
}
{
  // An estimate never gets a verdict; a neighbour's road reading is never this postcode's; not counted, no planes card.
  const env = { aircraftQuietEstimated: 8.5, aircraftQuietCoverage: 'city', roadNoiseLdenDb: 67.5, roadNoiseWhoGuidelineDb: 53 };
  const c = cardsOf(doc(base({ env, provenance: {}, planes: { model: null, steps }, resolvedAs: 'TW9 3PQ', sensor: null })).body);
  const by = Object.fromEntries(c.map((x) => [x.key, x]));
  ok(by.aircraft && by.aircraft.stand === 'none' && /^No DEFRA figure: outside its contours, so an estimate$/.test(by.aircraft.fig), 'an estimate is "For context", and says why', JSON.stringify(by.aircraft));
  ok(by.road && by.road.stand === 'none' && by.road.fig === 'Not given: the figure we hold is for TW9 3PQ', 'a neighbour\'s road reading gives no verdict on this postcode', JSON.stringify(by.road));
  ok(!by.planes && !by.air, 'a postcode not counted has no planes card, and no air figure means no air card', c.map((x) => x.key).join());
  const level = cardsOf(doc(base({ env: { ...measuredEnv, roadNoiseLdenDb: 53 } })).body).find((x) => x.key === 'road');
  ok(level.stand === 'none' && level.fig === '53.0 dB, level with the WHO guideline of 53', 'exactly at the guideline is neither', JSON.stringify(level));
}

// ---- 8. The details box, the page footer and the reference
{
  const { body, css } = m.reportParts({ postcode: 'TW9 3PZ', place: 'Kew', made: '2026-11-12', ref: 'HCH7-V2UJ', check: 'https://skyscore.co.uk/reports/street/?postcode=TW9%203PZ&made=2026-11-12&ref=HCH7V2UJ' }, base());
  ok(/<div class="details"><b>Report details<\/b> TW9 3PZ, Kew, Richmond upon Thames · prepared 12 November 2026 · reference HCH7-V2UJ<br><b>How current<\/b> [^<]*flight routes AIRAC 2026-10-29 · planes counted January to August 2026 · air: DEFRA's model for 2024<br><b>Check this report<\/b> <a href="https:\/\/skyscore\.co\.uk\/reports\/street\/\?postcode=TW9%203PZ/.test(body),
    'the details box names the place, the day, the reference, how current each source is, and the check link', (body.match(/<div class="details">[\s\S]*?<\/div>/) || [''])[0].slice(0, 400));
  ok(css.includes('@bottom-left { content: "Reference HCH7-V2UJ  ·  TW9 3PZ  ·  Prepared 12 November 2026  ·  AIRAC 2026-10-29";') && css.includes('content: "Page " counter(page) " of " counter(pages);'),
    'every printed page carries the reference, the postcode, the day and the AIRAC, and "Page x of 3"');
  const odd = m.reportParts({ postcode: 'TW9 3PZ', made: '2026-11-12', ref: 'A"B\\C' }, base()).css;
  ok(odd.includes('content: "Reference A\\"B\\\\C'), 'a quote or backslash in the footer is escaped for CSS', (odd.match(/@bottom-left \{ content: [^;]*/) || [''])[0]);
}
{
  // The reference moved from js/street_report_page.mjs on 2026-11-12, unchanged: HCH7-V2UJ is what the live free copy
  // (the code before the move) printed for TW9 3PZ that day, from these same figures. A new recipe would break every copy
  // already handed out, so it must never change silently.
  const env = { aircraftNoiseLdenDb: 57.2, aircraftQuiet: 3.2, roadNoiseLdenDb: 50.5, no2AnnualMeanUgm3: 17.0, pm25AnnualMeanUgm3: 8.5 };
  const got = await m.reportReference('TW9 3PZ', '2026-11-12', '2026-10-29', env);
  ok(got === 'HCH7-V2UJ', 'the reference recipe is the one live copies were made with', got);

  // THE PLANES FIGURES JOIN THE REFERENCE from REF_PLANES_FROM (audit M-4, Bill's pick A, 2026-11-13): a planes roll left
  // the check saying "matches" over out-of-date planes figures. A copy's own day picks the recipe, so a copy made before
  // the day still checks as it was made, whatever planes figures are passed.
  const planes = (west, months = 'January to August 2026') => ({
    none: null,
    airports: [{ code: 'LHR', period: months, rows: [{ value: west }, { value: 4 }] }],
  });
  ok(await m.reportReference('TW9 3PZ', '2026-11-12', '2026-10-29', env, planes(310)) === 'HCH7-V2UJ',
    'a copy made before the planes day keeps its reference whatever planes figures are passed');
  const day = m.REF_PLANES_FROM;
  const [a, b, c, d, e] = await Promise.all([
    m.reportReference('TW9 3PZ', day, '2026-10-29', env, planes(310)),
    m.reportReference('TW9 3PZ', day, '2026-10-29', env, planes(310)),
    m.reportReference('TW9 3PZ', day, '2026-10-29', env, planes(311)),
    m.reportReference('TW9 3PZ', day, '2026-10-29', env, planes(310, 'January to September 2026')),
    m.reportReference('TW9 3PZ', day, '2026-10-29', env, null),
  ]);
  ok(a === b, 'from the planes day the same planes figures give the same reference', `${a} / ${b}`);
  ok(a !== c, 'from the planes day a planes count that moved changes the reference', `${a} / ${c}`);
  ok(a !== d, 'from the planes day a new counting period changes the reference', `${a} / ${d}`);
  ok(a !== e, 'from the planes day a copy without a planes block has its own reference', `${a} / ${e}`);
  ok(JSON.stringify(m.planesStated({ none: 'Under 1 a day ...', airports: [] })) === '["none"]' && m.planesStated(null) === null,
    '"Under 1 a day" and no planes block are stated as themselves');
}

console.log(`street report: ${passed} checks passed${failed ? `, ${failed} FAILED` : ''}`);
process.exit(failed ? 1 : 0);
