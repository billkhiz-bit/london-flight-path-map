/**
 * The three-page aircraft-noise report for one postcode: everything except
 * where the inputs come from and how the page is printed.
 *
 * WHY THIS EXISTS (2026-10-06). Bill ruled that reports are free for a person's
 * own home, so a visitor must be able to make one on the site rather than ask
 * for it by email. The report had lived in scripts/address_noise_report.mjs,
 * which reads its inputs off the disk and prints with Playwright. Its page,
 * map and chart are pure functions of the inputs, so they live here and both
 * sides import them - the script that makes the sample PDFs, and the browser
 * page at /reports/street/. One holder, as js/flight_geometry.mjs is for the
 * runway geometry: two copies of a report drift, and a report that says one
 * thing on paper and another on screen is worse than no report.
 *
 * Moving it was checked, not assumed: the script's HTML for three postcodes
 * (measured London, unmeasured Manchester, Teesside with no DEFRA map) was
 * byte-identical before and after.
 *
 * Runs in the browser and in Node alike: no imports from either.
 */

import { AIRPORT_NAME, ORIGIN, add, compass, mul, reciprocal } from './flight_geometry.mjs';
// The report's headline, planes chart and road bars are the site's own (Bill's pick C, 2026-11-11). planes.mjs imports
// esc from here: a cycle ES modules allow, as nothing in either runs the other at load (tests/street-report.mjs).
import { answerLead } from './answer-lead.mjs';
import { pictureHtml, planesFindings, roadFinding } from './panel-findings.mjs';
import { planesChart } from './planes.mjs';

// A route further away than this is not listed. A judgement, stated on the page.
export const ROUTE_RADIUS_KM = 5;
// An airport nearer than this is named on the page, with what the report holds for it.
export const SCOPE_KM = 40;
export const MIN_DISTRICT = 30; // fewer live measured postcodes than this: no comparison chart

// ---- The nearest station (Bill, 2026-10-06: "show it first"), shown and NOT scored ----
// From data/stations.json, the list the full map's panel reads (NaPTAN rail and metro,
// each covered city's own). The score's transport input stays the council area's share of
// addresses within 800 m. One holder for the front page, the free report and the PDF.
// The list holds stations INSIDE the cities covered, so near a city's edge a closer one
// can lie outside it: beyond STATION_SCOPE_KM nothing is said, never "no station near".
export const STATION_SCOPE_KM = 3;
const haversineKm = (lat1, lon1, lat2, lon2) => {
  const r = Math.PI / 180, dLat = (lat2 - lat1) * r, dLon = (lon2 - lon1) * r;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371.0088 * Math.asin(Math.sqrt(h));
};
/** The nearest station in the list (keyed by city, as data/stations.json is), or null beyond the scope. */
export function nearestStation(stationsByCity, lat, lon) {
  let best = null;
  for (const s of Object.values(stationsByCity || {}).flat()) {
    const km = haversineKm(lat, lon, s.coords[1], s.coords[0]);
    if (!best || km < best.km) best = { name: s.name, km };
  }
  return best && best.km <= STATION_SCOPE_KM ? best : null;
}
/** "650 m" under a kilometre (to the nearest 10 m), "1.4 km" above.
 *  The unit is chosen AFTER rounding to 10 m: choosing it first printed 0.995 km as "1000 m"
 *  (audit 2026-10-09 M-7). Kilometres still format from the raw distance, because rounding
 *  twice (to 10 m, then to 0.1 km) tips ties: 1.0451 km would read "1.1 km". */
export const stationDistance = (km) => {
  const m = Math.round(km * 100) * 10;
  return m < 1000 ? `${m} m` : `${km.toFixed(1)} km`;
};

// ---- Air measured nearby (ROADMAP "The plan for Breathe London", step 3), shown and NOT scored ----
// Two files, each written and checked offline: data/breathe-london-sensors.json (London's low-cost
// sensors, a 12-month mean; scripts/fetch_breathe_london.py) and data/aurn-sites.json (DEFRA's
// reference monitors, the PCM year's annual mean; scripts/fetch_aurn.py). One holder for the front
// page, the free report and the PDF, as for the station. Beyond AIR_SCOPE_KM nothing is said (Bill,
// 2026-10-19: 5 km for both, and London shows both), never "no monitor near": the files hold only
// what cleared the capture floor, so a nearer one may exist and have been left out. Never ranked:
// a kerbside sensor and a background monitor measure different things.
export const AIR_SCOPE_KM = 5;
// A sensor file whose window ended longer ago than this is not shown at all, rather than shown as
// current (Bill, 2026-10-13); check_data_freshness.py reads NEWER at the same age.
export const SENSOR_STALE_DAYS = 45;
const CAPTURE_FLOOR_PCT = 75;
const nearestWithin = (rows, lat, lon) => {
  let best = null;
  for (const r of rows || []) {
    const km = haversineKm(lat, lon, r.lat, r.lon);
    if (!best || km < best.km) best = { row: r, km };
  }
  return best && best.km <= AIR_SCOPE_KM ? best : null;
};
/** The nearest Breathe London sensor, or null: beyond the scope, or the file past its window. */
export function nearestSensor(file, lat, lon, today = new Date()) {
  const to = file?.window?.to;
  if (!to || Math.floor((today.getTime() - Date.parse(`${to}T00:00:00Z`)) / 86400000) > SENSOR_STALE_DAYS) return null;
  const best = nearestWithin(file.sites, lat, lon);
  return best && { ...best.row, km: best.km, to, credit: { text: file.attribution, href: file.attributionLink } };
}
/** The nearest DEFRA AURN monitor, or null beyond the scope. */
export function nearestMonitor(file, lat, lon) {
  const best = nearestWithin(file?.sites, lat, lon);
  return best && { ...best.row, km: best.km, year: file.year, credit: { text: file.attribution, href: file.licence } };
}
const ugm3 = (v) => `${v.toFixed(1)} µg/m³`;
const pollutants = (r) =>
  [r.no2 && `nitrogen dioxide ${ugm3(r.no2.mean)}`, r.pm25 && `fine particles ${ugm3(r.pm25.mean)}`].filter(Boolean).join(' and ');
const SENSOR_KIND = { 'Urban Background': 'background', Roadside: 'roadside', Kerbside: 'kerbside' };
// Plain text: the front page sets it as textContent, the report escapes it. The PIECES are exported so
// the full map can lay the same words out as rows (Bill, 2026-10-19: the panel's one paragraph was
// unclear) without wording anything differently.
/** "roadside, 0.7 m from the kerb" */
export function sensorSetting(s) {
  const kind = SENSOR_KIND[s.classification] || String(s.classification).toLowerCase();
  return typeof s.kerbDistanceM === 'number' ? `${kind}, ${Number(s.kerbDistanceM.toFixed(1))} m from the kerb` : kind;
}
/** "12 months to September 2026": the sensor file's window, the one place its period is worded. */
export function sensorPeriod(s) {
  const month = new Date(`${s.to}T12:00:00Z`).toLocaleDateString('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' });
  return `12 months to ${month}`;
}
/** "nitrogen dioxide 18.7 µg/m³ and fine particles 7.5 µg/m³ over the 12 months to September 2026" */
export function sensorReadings(s) {
  return `${pollutants(s)} over the ${sensorPeriod(s)}`;
}
/** "suburban industrial" */
export const monitorSetting = (m) => String(m.type).toLowerCase();
/** "2024": the monitor file's year. */
export const monitorPeriod = (m) => String(m.year);
/** "nitrogen dioxide 14.2 µg/m³ in 2024" */
export const monitorReadings = (m) => `${pollutants(m)} in ${monitorPeriod(m)}`;
/** "Nearest Breathe London sensor: George Street, 1.5 km away (roadside, 0.7 m from the kerb): nitrogen dioxide 18.7 µg/m³ and fine particles 7.5 µg/m³ over the 12 months to September 2026." */
/** The short forms for the answer's Nearby list: the place, how far, and the readings; the full line sits in its fold. */
export const sensorFact = (s) => `${s.name}, ${stationDistance(s.km)}: ${sensorReadings(s)}`;
export const monitorFact = (m) => `${m.name}, ${stationDistance(m.km)}: ${monitorReadings(m)}`;
export function sensorLine(s) {
  return `Nearest Breathe London sensor: ${s.name}, ${stationDistance(s.km)} away (${sensorSetting(s)}): ${sensorReadings(s)}.`;
}
/** "Nearest official monitor: Manchester Sharston, 1.7 km away (suburban industrial): nitrogen dioxide 14.2 µg/m³ in 2024." */
export function monitorLine(m) {
  return `Nearest official monitor: ${m.name}, ${stationDistance(m.km)} away (${monitorSetting(m)}): ${monitorReadings(m)}.`;
}
// ---- Where to have your say (Bill, 2026-10-19), for the airports whose own pages were VERIFIED ----
// Each link was checked live on 2026-10-19 (status and content; London City's in a real browser, since its
// site turns scripts away). An airport joins only when its pages have been checked: a wrong link is a false
// claim (the full map's WebTrak lesson, 2026-08-24). Never imply a complaint moves a route: routes change
// through the CAA's airspace change process, which Heathrow itself says.
// A link with `until` (YYYY-MM-DD, its last open day) shows to the end of that day (UTC, UK time in winter) and
// drops out by itself after it, so a closed consultation is never offered. Heathrow's expansion consultation runs
// "From 27 October to 22 December 2026" (checked live 2026-11-01: 200 + page text in Chrome; its response form
// turns scripts away, so the link is the consultation page, which carries every way to respond). Neutral: a
// signpost to have a say, never a view on expansion.
export const HAVE_YOUR_SAY = {
  LHR: [
    { text: "Heathrow's expansion consultation, open until 22 December", href: 'https://www.heathrow.com/expansion/consultation', until: '2026-12-22' },
    { text: 'contact Heathrow about noise', href: 'https://www.heathrow.com/company/local-community/noise/what-you-can-do/contact-us-about-noise' },
    { text: 'find a flight on WebTrak', href: 'https://webtrak.emsbk.com/lhr6' },
  ],
  LCY: [
    { text: 'London City enquiries and complaints', href: 'https://www.londoncityairport.com/corporate/environment/enquiries-and-complaints' },
    { text: 'its flight track and noise monitoring', href: 'https://www.londoncityairport.com/corporate/environment/noise-management-and-monitoring/flight-track-and-monitoring-system' },
  ],
};
export const AIRSPACE_CHANGE = { text: "the CAA's airspace change portal", href: 'https://airspacechange.caa.co.uk/having-your-say/' };
/**
 * The links for the airport whose published route passes NEAREST (`routesNear(...)`: its final approaches and
 * departures, among the airports in scope), else the nearest airport in scope; null when that airport's pages
 * are not verified, never another airport's. Picking the nearest AIRPORT sent Battersea, 1.1 km from Heathrow's
 * 27L approach and nearer London City's runway, to London City's pages (audit 2026-10-22, I-6).
 * `today` decides which dated links (`until`) are still open.
 */
export function haveYourSay(routes, today = new Date()) {
  const day = today.toISOString().slice(0, 10);
  const scope = (routes && routes.scope) || [];
  const inScope = new Set(scope.map((a) => a.code));
  const nearestRoute = [...((routes && routes.finals) || []), ...((routes && routes.departures) || [])]
    .filter((r) => inScope.has(r.code))
    .sort((a, b) => a.dist - b.dist)[0];
  const code = nearestRoute ? nearestRoute.code : scope[0] && scope[0].code;
  if (!code || !Object.hasOwn(HAVE_YOUR_SAY, code)) return null;
  const links = HAVE_YOUR_SAY[code].filter((l) => !l.until || day <= l.until);
  return links.length ? { code, links, change: AIRSPACE_CHANGE } : null;
}
/** The correction address, as the full map's "Spotted something wrong?" has used since before 2026-10-13. */
export const correctionHref = (place) => `mailto:support@skyscore.co.uk?subject=${encodeURIComponent(`Correction: ${place}`)}`;

// ---- The reference, shared by the free copy and the printed report (moved here from js/street_report_page.mjs
// 2026-11-12, unchanged, so every copy already made still checks). A hash of the figures a copy states, the postcode
// and the day it was made: anyone handed a copy re-makes it from today's data with the original day and compares.
const SITE = 'https://skyscore.co.uk';
const STATED = [
  'aircraftQuiet',
  'aircraftQuietEstimated',
  'aircraftNoiseLdenDb',
  'roadNoiseLdenDb',
  'roadNoiseBelowDb',
  'no2AnnualMeanUgm3',
  'pm25AnnualMeanUgm3',
];
const REF_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // no 0/O or 1/I to misread

// The planes figures join the reference for copies made from this day (audit M-4, Bill's pick A, 2026-11-13): before it a
// planes roll left the check saying "matches" over out-of-date planes figures. The recipe is chosen by the copy's OWN day,
// so the copy and its check always agree, and every copy made before this day still checks the way it was made.
export const REF_PLANES_FROM = '2026-11-14';

/** The planes figures a copy states, for its reference: each airport's period and figures in the model's order, and
 * whether it says "Under 1 a day". Null when the copy has no planes block. */
export function planesStated(model) {
  if (!model) return null;
  return [model.none ? 'none' : null, ...(model.airports || []).map((a) => [a.code, a.period, ...a.rows.map((r) => r.value ?? null)])];
}

/** The reference for a copy: 8 characters of a SHA-256 over what the copy states. `planes` is the copy's planesModel(). */
export async function reportReference(postcode, made, airac, env, planes = null) {
  const stated = [postcode, made, airac ?? null, ...STATED.map((k) => (typeof env[k] === 'number' ? env[k] : null))];
  if (made >= REF_PLANES_FROM) stated.push(planesStated(planes));
  const text = JSON.stringify(stated);
  const d = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)));
  let out = '';
  for (let i = 0; i < 8; i++) out += REF_ALPHABET[d[i] & 31];
  return `${out.slice(0, 4)}-${out.slice(4)}`;
}
/** The link that re-makes a copy and checks its reference. */
export const checkLink = (postcode, made, ref) =>
  `${SITE}/reports/street/?postcode=${encodeURIComponent(postcode)}&made=${made}&ref=${ref.replace('-', '')}`;

// ---- Page 1's cards (Bill's three-page pick, 2026-11-11 v2; v3 and the build 2026-11-12) ----
/** The verdict words: the site's pill words, a mark and a word, never colour alone (audit I-3, 2026-11-10). */
export const GLANCE_WORDS = { watch: ['!', 'Worth a look'], good: ['✓', 'Good here'], none: ['–', 'For context'] };

/**
 * One card per topic: a verdict word, the figure, a next step where the site has one, and the page its detail is on.
 * ONE RULE decides the word, and this is its only holder: a postcode's OWN figure against its WHO guideline ("Worth a
 * look" over it, "Good here" under it) for road noise, and for aircraft noise where DEFRA's map gives a figure; the planes
 * from the full map's own watch step (planesFindings' `stand`, from the planes layer's steps); air and any estimate get
 * none ("For context"): the WHO 2021 air guidelines sit under the modelled figure almost everywhere (js/answer-lead.mjs),
 * and an estimate is not a finding against a yardstick. As the map's pills (pillsFor), aircraft noise is never "Good
 * here" beside planes that are a watch item. The map rates aircraft noise by its band and road noise by the council, so a
 * card can differ from a map pill: the card is about this postcode's own figure. A topic with nothing true to say has no
 * card. A neighbour's road reading is never this postcode's (audit I-4). Pure; held by tests/street-report.mjs.
 */
/** Where a figure stands against its WHO guideline, in the words every card uses: ONE holder (glanceCards here, and the
 * front page's example tiles since Bill's pick A of 2026-11-13). */
export const whoSide = (v, who) => (v > who ? 'over' : v < who ? 'under' : 'level with');

export function glanceCards({ env = {}, model = null, steps = [], resolvedAs = null, aircraftMap = false, sensor = null, say = null } = {}) {
  const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
  const verdict = (v, who) => (v > who ? 'watch' : v < who ? 'good' : null);
  const side = whoSide;
  const cards = [];

  const webtrak = say && (say.links || []).some((l) => /webtrak/i.test(l.href))
    ? `WebTrak shows each ${AIRPORT_NAME[say.code] || say.code} flight as it passes; the link is on page 2.`
    : null;
  const db = num(env.aircraftNoiseLdenDb);
  const awho = num(env.aircraftNoiseWhoGuidelineDb);
  if (db !== null) {
    cards.push({
      key: 'aircraft', topic: 'Aircraft noise', stand: awho !== null ? verdict(db, awho) : null,
      // Whole decibels, as the key figure under the cards gives it, so page 1 never states one figure two ways; the
      // verdict is decided on the figure itself.
      figure: `${Math.round(db)} dB on DEFRA's map${awho !== null ? `, ${side(db, awho)} the WHO guideline of ${awho}` : ''}`,
      step: webtrak, page: 2,
    });
  } else if (env.aircraftQuietCoverage !== 'outside' && num(env.aircraftQuietEstimated) !== null) {
    cards.push({
      key: 'aircraft', topic: 'Aircraft noise', stand: null,
      figure: aircraftMap ? 'No DEFRA figure: outside its contours, so an estimate' : 'No DEFRA map for this airport, so an estimate',
      step: webtrak, page: 1,
    });
  }

  if (model) {
    const found = planesFindings(model, { steps });
    if (!model.airports.length) {
      if (found.length) cards.push({ key: 'planes', topic: 'Planes overhead', stand: null, figure: 'Under 1 a day from each airport we count', step: null, page: 2 });
    } else {
      // The busiest airport, as the report's charts and headline lead with it.
      const peak = (a) => Math.max(0, ...a.rows.map((r) => (Array.isArray(r.value) ? r.value[1] : typeof r.value === 'number' ? r.value : 0)));
      const i = model.airports.map((a, k) => [k, peak(a)]).sort((x, y) => y[1] - x[1])[0][0];
      const a = model.airports[i];
      const t = found[i] && found[i].tile;
      if (t) {
        const level = /^(Not measured|None)$/.test(t.level) ? t.level.toLowerCase() : t.level;
        cards.push({
          key: 'planes', topic: 'Planes overhead', stand: t.stand === 'watch' ? 'watch' : null,
          figure: `${a.name}: ${level}${t.sub ? ` when ${t.sub}` : ''}`, step: (t.say && t.say[0]) || null, page: 2,
        });
      }
    }
  }
  const watchPlanes = cards.some((c) => c.key === 'planes' && c.stand === 'watch');
  const air0 = cards.find((c) => c.key === 'aircraft');
  if (air0 && watchPlanes && air0.stand === 'good') air0.stand = null;

  const rdb = num(env.roadNoiseLdenDb);
  const below = num(env.roadNoiseBelowDb);
  const rwho = num(env.roadNoiseWhoGuidelineDb);
  if (resolvedAs && (rdb !== null || below !== null)) {
    cards.push({ key: 'road', topic: 'Road noise', stand: null, figure: `Not given: the figure we hold is for ${resolvedAs}`, step: null, page: 2 });
  } else if (rdb !== null && rwho !== null) {
    const tip = roadFinding({ db: rdb, who: rwho });
    cards.push({
      key: 'road', topic: 'Road noise', stand: verdict(rdb, rwho),
      figure: `${rdb.toFixed(1)} dB, ${side(rdb, rwho)} the WHO guideline of ${rwho}`, step: (tip && tip.tile.tip) || null, page: 2,
    });
  } else if (below !== null) {
    const under = rwho !== null && below <= rwho;
    cards.push({
      key: 'road', topic: 'Road noise', stand: under ? 'good' : null,
      figure: under ? `Under the WHO guideline of ${rwho}: DEFRA mapped none at ${below} dB or above` : `DEFRA mapped none at ${below} dB or above`,
      step: null, page: 2,
    });
  }

  const no2 = num(env.no2AnnualMeanUgm3);
  const pm = num(env.pm25AnnualMeanUgm3);
  if (no2 !== null || pm !== null) {
    const figs = [no2 !== null && `NO₂ ${no2.toFixed(1)}`, pm !== null && `PM2.5 ${pm.toFixed(1)}`].filter(Boolean).join(' and ');
    const whos = [no2 !== null && num(env.no2WhoGuidelineUgm3), pm !== null && num(env.pm25WhoGuidelineUgm3)].filter((v) => typeof v === 'number');
    const breathe = sensor && sensor.credit && /Breathe London/.test(sensor.credit.text || '');
    cards.push({
      key: 'air', topic: 'Air', stand: null,
      figure: `${figs} µg/m³ on DEFRA's model${whos.length === (no2 !== null) + (pm !== null) ? `; the WHO guideline${whos.length > 1 ? 's are' : ' is'} ${whos.join(' and ')}` : ''}`,
      step: breathe ? "Breathe London's own map shows the nearest sensor's readings hour by hour." : null, page: 3,
    });
  }
  return cards;
}

/**
 * What kind of measurement each line is, and why a sensor by a road reads above DEFRA's background figure, one note
 * each, with a mark for a list: the front page's air fold sets them as points (2026-11-11), the report and the full map
 * as one paragraph (airNotes). One holder, so the two can never say different things.
 */
export function airNoteList(sensor, monitor) {
  const notes = [];
  if (sensor) notes.push({ key: 'provisional', mark: '~', text: 'Breathe London sensors are low-cost: their figures are provisional and are recalibrated over time.' });
  if (sensor && sensor.classification !== 'Urban Background')
    notes.push({ key: 'roadside', mark: '↑', text: "A sensor by a road can read higher than DEFRA's background figure: it measures the traffic beside it, where DEFRA's is the average across a 1 km square." });
  if (monitor) notes.push({ key: 'ratified', mark: '✓', text: "Official monitors are DEFRA's reference instruments, and their figures are ratified." });
  notes.push({ key: 'capture', mark: '✓', text: `Each figure rests on at least ${CAPTURE_FLOOR_PCT}% of the hours in its period.` });
  return notes;
}
export const airNotes = (sensor, monitor) => airNoteList(sensor, monitor).map((n) => n.text).join(' ');

// ---- Air side by side (Bill, 2026-11-03: "refined B" of claude.ai/artifact/6ysdR2AJvPbWhi8PR3UVGc) ----
// The full map sets DEFRA's model for the postcode's own 1 km square beside the nearest sensor and monitor, ONE scale
// per pollutant with the WHO 2021 guideline drawn through, so a reader sees at a glance whether the air is over the
// guideline and how the measurements sit against the model. A pure function returning SVG text (every name escaped
// here), so tests/air-chart.mjs holds its geometry without a browser.
/** WHO 2021 annual guidelines, µg/m³. The API sends its own (`no2WhoGuidelineUgm3`, `pm25WhoGuidelineUgm3` in
 *  backend/lambdas/score/app.py) and the chart prefers those; tests/air-chart.mjs holds the two equal. */
export const AIR_WHO_2021 = { no2: 10, pm25: 5 };
/** The scale runs to this many times the guideline: 40 for NO2, also the UK legal limit for its annual mean. */
export const AIR_SCALE_TIMES = 4;
/** Each pollutant's heading. */
export const AIR_POLLUTANT_NAMES = { no2: 'Nitrogen dioxide (NO₂)', pm25: 'Fine particles (PM2.5)' };
const AIR_MARK = {
  // DEFRA's MODEL is a hollow ring (modelled, never measured); a sensor a filled circle, a monitor a filled square:
  // shape carries the source as well as colour. Colours checked for colour-blind separation and 3:1 on the panel.
  // No fill and no halo: the panel is white on a desktop and cream on a phone, so a "panel-coloured" centre would
  // show as a blob on one of them; the row's line stops short of the mark instead.
  model: (cx, cy) => `<circle cx="${cx}" cy="${cy}" r="5.5" fill="none" stroke-width="2.5" style="stroke:var(--air-model, #a85416)"/>`,
  sensor: (cx, cy) => `<circle cx="${cx}" cy="${cy}" r="6" style="fill:var(--air-sensor, #14866a)"/>`,
  monitor: (cx, cy) => `<rect x="${cx - 5.5}" y="${cy - 5.5}" width="11" height="11" style="fill:var(--air-monitor, #267df2)"/>`,
};
/** The key's mark for a source, 14 px. */
export function airKeyMark(kind) {
  return `<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" focusable="false">${AIR_MARK[kind](7, 7)}</svg>`;
}
/**
 * One pollutant's rows on one scale, as SVG text: `rows` are [{ kind: 'model'|'sensor'|'monitor', label, sub, v }],
 * `v` null where that source does not measure the pollutant ("not measured here", no mark). The scale is 0 to
 * AIR_SCALE_TIMES x `who`; a reading beyond it sits at the end, its own figure beside it with "▸". A value label that
 * would leave the picture moves to the mark's left. Every mark carries data-kind and data-value for the tests.
 */
export function airChart(pollutant, rows, who = AIR_WHO_2021[pollutant]) {
  const max = who * AIR_SCALE_TIMES;
  const W = 352, L = 176, R = 14, rowH = 30, top = 16;
  const x0 = L, x1 = W - R;
  const x = (u) => +(x0 + (Math.min(Math.max(u, 0), max) / max) * (x1 - x0)).toFixed(2);
  const g = x(who);
  const axisY = top + rows.length * rowH + 4;
  const H = axisY + 18;
  const fmt = (v) => Number(v).toFixed(1);
  const name = AIR_POLLUTANT_NAMES[pollutant];
  const body = rows.map((r, i) => {
    const cy = top + i * rowH + rowH / 2;
    const label = r.label.length > 26 ? `${r.label.slice(0, 25)}…` : r.label;
    const head = `<text x="0" y="${cy - 2}" font-size="11.5" font-weight="600" style="fill:var(--air-ink, #141414)">${esc(label)}</text>`
      + `<text x="0" y="${cy + 11}" font-size="10" style="fill:var(--air-ink-3, #636363)">${esc(r.sub)}</text>`;
    if (r.v == null || !Number.isFinite(r.v)) {
      return `<g data-kind="${r.kind}" data-value="">${head}<text x="${x1}" y="${cy + 4}" font-size="11" text-anchor="end" style="fill:var(--air-ink-3, #636363)">not measured here</text></g>`;
    }
    const cx = x(r.v);
    const beyond = r.v > max;
    const text = `${fmt(r.v)}${beyond ? ' ▸' : ''}`;
    const left = cx > W - 46;
    const tip = `${r.label} (${r.sub}): ${fmt(r.v)} µg/m³${beyond ? `, beyond this scale of ${max}` : ''}, ${(r.v / who).toFixed(1)}× the WHO guideline of ${who}`;
    return `<g data-kind="${r.kind}" data-value="${fmt(r.v)}"><title>${esc(tip)}</title>${head}`
      + (cx - 9 > x0 ? `<line x1="${x0}" x2="${(cx - 9).toFixed(2)}" y1="${cy}" y2="${cy}" stroke-width="2" style="stroke:var(--air-rule, #c8c7c4)"/>` : '')
      + `<g data-mark="${r.kind}" data-cx="${cx}">${AIR_MARK[r.kind](cx, cy)}</g>`
      + `<text x="${left ? cx - 10 : cx + 10}" y="${cy + 4}" font-size="11" font-weight="600" text-anchor="${left ? 'end' : 'start'}" style="fill:var(--air-ink, #141414);font-family:var(--font-mono, monospace)">${esc(text)}</text></g>`;
  }).join('');
  const ticks = [0, who, max / 2, max];
  const aria = `${name}, µg/m³: ${rows.map((r) => `${r.label} ${r.v == null ? 'not measured here' : fmt(r.v)}`).join('; ')}. WHO guideline ${who}.`;
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(aria)}" data-air-chart="${pollutant}" data-x0="${x0}" data-x1="${x1}" data-max="${max}">`
    + `<rect x="${g}" y="${top - 4}" width="${(x1 - g).toFixed(2)}" height="${rows.length * rowH + 8}" style="fill:var(--air-band, rgba(20,20,20,0.05))"/>`
    + `<text x="${((g + x1) / 2).toFixed(2)}" y="${top - 6}" font-size="9" text-anchor="middle" style="fill:var(--air-ink-3, #636363)">over the WHO guideline</text>`
    + `<line data-who="${g}" x1="${g}" x2="${g}" y1="${top - 4}" y2="${axisY}" stroke-width="1.5" stroke-dasharray="3 2" style="stroke:var(--air-ink, #141414)"/>`
    + body
    + `<line data-axis="1" x1="${x0}" x2="${x1}" y1="${axisY}" y2="${axisY}" stroke-width="1" style="stroke:var(--air-ink-3, #636363)"/>`
    + ticks.map((t) => `<text x="${x(t)}" y="${axisY + 13}" font-size="9.5" text-anchor="${t === max ? 'end' : 'middle'}" style="fill:var(--air-ink-3, #636363);font-family:var(--font-mono, monospace)">${t === who ? `WHO ${t}` : t}</text>`).join('')
    + '</svg>';
}
// ---- The air for one postcode, as the full map's panel and the street report both set it (2026-11-11) ----
// Moved here from index.html's panel when the report took the same charts (Bill's pick C), so the two read the API's
// answer, word the key and build the rows one way: a third copy was the alternative.
/**
 * DEFRA's model for the postcode's own grid square, from a /v1/environment body, read with the provenance the API sends
 * (method, resolution, period), so a surface says what the API says and never calls the model measured. Null for a
 * non-modelled answer or no figure.
 */
export function airSquare(d) {
  const e = d && d.environment;
  const pv = (d && d.provenance) || {};
  const meta = pv['environment.no2AnnualMeanUgm3'] || pv['environment.pm25AnnualMeanUgm3'];
  if (!e || !meta || meta.method !== 'modelled') return null;
  const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
  const no2 = num(e.no2AnnualMeanUgm3);
  const pm25 = num(e.pm25AnnualMeanUgm3);
  if (no2 === null && pm25 === null) return null;
  // "1 km grid" -> "1 km square". One quantifier and a number check (a nested one is what the security
  // lint calls unsafe: catastrophic backtracking on a crafted string).
  const res = /^([0-9.]{1,8}) ?km grid$/.exec(String(meta.resolution || ''));
  const km = res && Number.isFinite(Number(res[1])) ? res[1] : null;
  return {
    no2,
    pm25,
    period: /^\d{4}$/.test(String(meta.period)) ? String(meta.period) : null,
    square: km ? `${km} km square` : 'grid square',
    background: /background/i.test(String(e.airQualitySource || '')),
    who: { no2: num(e.no2WhoGuidelineUgm3), pm25: num(e.pm25WhoGuidelineUgm3) },
  };
}
/** The model's row label, sub-label and key words, for a square from airSquare(); null for none. */
export function airModelOf(square) {
  if (!square) return null;
  return {
    label: "DEFRA's model",
    sub: `this ${square.square}${square.period ? ` · ${square.period}` : ''}`,
    no2: square.no2,
    pm25: square.pm25,
    detail: `DEFRA's ${square.background ? 'background ' : ''}model for this postcode's ${square.square}${square.period ? `, ${square.period}` : ''}.`,
  };
}
const capFirst = (t) => t.charAt(0).toUpperCase() + t.slice(1);
/** The key's words for a sensor: what it is, its setting, its period. */
export const sensorKeyNote = (s) => `Breathe London sensor, low-cost, provisional. ${capFirst(sensorSetting(s))}. Over the ${sensorPeriod(s)}.`;
/** The key's words for a monitor. */
export const monitorKeyNote = (m) => `Official DEFRA monitor, ratified. ${capFirst(monitorSetting(m))}. In ${monitorPeriod(m)}.`;
/** One pollutant's rows for airChart(): the model, the sensor and the monitor, each where present. */
export function airRows(p, { model, sensor, monitor }) {
  const reading = (r) => (r && r[p] && typeof r[p].mean === 'number' ? r[p].mean : null);
  return [
    model && { kind: 'model', label: model.label, sub: model.sub, v: model[p] },
    sensor && { kind: 'sensor', label: sensor.name, sub: `sensor · ${stationDistance(sensor.km)}`, v: reading(sensor) },
    monitor && { kind: 'monitor', label: monitor.name, sub: `monitor · ${stationDistance(monitor.km)}`, v: reading(monitor) },
  ].filter(Boolean);
}
// h 345 -> 290 on 2026-11-03: a little wider and shorter, so the report fits one A4 page again after it gained the
// air measured nearby and the have-your-say lines (the frame logic widens the view, so the approach stays in shot).
const MAP = { w: 1000, h: 290, padKm: 5, minHeightKm: 11 };

// DEFRA's Lden bands for its aircraft map. A MIRROR of NOISE_SCALE_DEFRA_LDEN in
// index.html, the holder the site's legend reads; the PDF script compares the two
// on every run and refuses to print on a difference, and
// tests/test_street_report_mirrors.py does the same in preflight.
export const DEFRA_LDEN_SCALE = [
  { from: 40, colour: '#B8D6D1' },
  { from: 45, colour: '#CEE4CC' },
  { from: 50, colour: '#E2F2BF' },
  { from: 55, colour: '#F3C683' },
  { from: 60, colour: '#E87E4D' },
  { from: 65, colour: '#CD463E' },
  { from: 70, colour: '#A11A4D' },
  { from: 75, colour: '#75085C' },
  { from: 80, colour: '#430A4A' },
];
// London's DEFRA picture, the one not described by data/aircraft-noise-rasters.json.
// A MIRROR of LONDON_AIRCRAFT_BBOX in index.html, held to it the same two ways.
export const LONDON_RASTER = {
  city: 'london',
  png: 'data/aircraft-noise-london-lden.png',
  bbox: { minLon: -0.85, maxLon: 0.4, minLat: 51.1, maxLat: 51.78 },
};

export const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const km = (x) => x.toFixed(1);
const r1 = (x) => Math.round(x * 10) / 10;

const where = (d, q) => (d < 0.05 ? 'directly overhead' : `${km(d)} km to the ${compass(q)}`);

/** The DEFRA picture whose box contains this point, and the city it belongs to. `png` has no leading slash. */
export function rasterFor(regions, lat, lon) {
  const inside = (b) => lat >= b.minLat && lat <= b.maxLat && lon >= b.minLon && lon <= b.maxLon;
  if (inside(LONDON_RASTER.bbox)) return LONDON_RASTER;
  for (const [city, c] of Object.entries(regions.cities || {})) {
    if (inside(c.bbox)) return { city, png: c.png.replace(/^\//, ''), bbox: c.bbox };
  }
  return null;
}

/**
 * How the postcode compares with the others in its district on DEFRA's map.
 * `quiet` is the merged per-postcode Quiet Skies map the site ships (it keeps
 * TERMINATED postcodes, hence `livePostcodes`, an async function returning the
 * Set of those still live).
 */
export async function districtComparison(quiet, outcode, mine, livePostcodes) {
  if (typeof mine !== 'number') return null;
  const compact = outcode.replace(/\s+/g, '');
  const inDistrict = Object.keys(quiet).filter((k) => k.slice(0, -3) === compact);
  if (inDistrict.length < MIN_DISTRICT) return null;
  const live = await livePostcodes(inDistrict);
  const scores = inDistrict.filter((k) => live.has(k)).map((k) => quiet[k]);
  if (scores.length < MIN_DISTRICT) return null;
  const bins = Array(10).fill(0);
  for (const s of scores) bins[Math.min(9, Math.floor(s))]++;
  return {
    outcode,
    n: scores.length,
    bins,
    mineBin: Math.min(9, Math.floor(mine)),
    quieterPct: Math.round((100 * scores.filter((s) => s > mine).length) / scores.length),
    louderPct: Math.round((100 * scores.filter((s) => s < mine).length) / scores.length),
  };
}

// ---- drawing ---------------------------------------------------------------
/** A map label on a plate. */
function tag(x, y, text, cls) {
  // Sized for the 16-unit labels (8.3 pt printed; 15 until 2026-11-11, when no text in the report may print under 8 pt).
  const w = text.length * 9.4 + 12;
  return `<rect x="${r1(x - w / 2)}" y="${r1(y - 16)}" width="${r1(w)}" height="22" rx="3" class="plate"/><text x="${r1(x)}" y="${r1(y)}" class="lab${cls}" text-anchor="middle">${esc(text)}</text>`;
}

/** The report's map. `imageHref(png)` turns the picture's repository path into an address the page can load. */
export function mapSvg({ pl, routes, raster, boroughs, scale, label, imageHref }) {
  const { w: W, h: H } = MAP;
  const home = routes.airports[0];
  const frame = [ORIGIN, ...(home && home.dist < 45 ? home.thresholds : [])];
  let [x0, x1] = [Math.min(...frame.map((p) => p[0])) - MAP.padKm, Math.max(...frame.map((p) => p[0])) + MAP.padKm];
  let [y0, y1] = [Math.min(...frame.map((p) => p[1])) - MAP.padKm, Math.max(...frame.map((p) => p[1])) + MAP.padKm];
  let [w, h] = [x1 - x0, Math.max(y1 - y0, MAP.minHeightKm)];
  if (w / h < W / H) w = (h * W) / H;
  else h = (w * H) / W;
  const [cx, cy] = [(x0 + x1) / 2, (y0 + y1) / 2];
  const k = W / w;
  const S = (p) => [r1((p[0] - cx) * k + W / 2), r1(H / 2 - (p[1] - cy) * k)];
  const poly = (pts) => pts.map((p) => S(p).join(',')).join(' ');
  const seen = (p) => Math.abs(p[0] - cx) <= w / 2 && Math.abs(p[1] - cy) <= h / 2;

  let layers = '';
  if (raster) {
    const [ix0, iy0] = S(pl.xy(raster.bbox.maxLat, raster.bbox.minLon));
    const [ix1, iy1] = S(pl.xy(raster.bbox.minLat, raster.bbox.maxLon));
    layers += `<image href="${imageHref(raster.png)}" x="${ix0}" y="${iy0}" width="${r1(ix1 - ix0)}" height="${r1(iy1 - iy0)}" preserveAspectRatio="none"/>`;
  }
  for (const f of boroughs ? boroughs.features : []) {
    const polys = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates;
    for (const rings of polys) {
      const pts = rings[0].map(([lo, la]) => pl.xy(la, lo));
      if (pts.some(seen)) layers += `<polygon points="${poly(pts)}" class="boro"/>`;
    }
  }
  for (const d of routes.departures) layers += `<polyline points="${poly(d.line)}" class="dep"/>`;
  for (const f of routes.finals) layers += `<polyline points="${poly(f.line)}" class="fin"/>`;
  for (const ap of routes.airports) {
    for (const [rwy, r] of Object.entries(ap.runways)) {
      const other = ap.runways[reciprocal(rwy)];
      // Each strip once: from the lower designator's threshold to its reciprocal's.
      if (other && rwy < reciprocal(rwy))
        layers += `<polyline points="${poly([pl.xy(...r.thr), pl.xy(...other.thr)])}" class="rwy"/>`;
    }
    const mid = mul(ap.thresholds.reduce(add, ORIGIN), 1 / ap.thresholds.length);
    if (seen(mid)) {
      const lowest = Math.max(...ap.thresholds.map((t) => S(t)[1]));
      layers += tag(S(mid)[0], lowest + 24, AIRPORT_NAME[ap.code] || ap.code, '');
    }
  }
  const [px, py] = S(ORIGIN);
  layers += `<circle cx="${px}" cy="${py}" r="9" class="pin"/><circle cx="${px}" cy="${py}" r="2.5"/>`;
  layers += tag(px, py - 18, label, ' strong');
  const bar = 5 * k;
  layers += `<g transform="translate(18,${H - 16})"><rect x="-6" y="-26" width="${r1(bar + 12)}" height="34" class="plate"/><line x1="0" y1="0" x2="${r1(bar)}" y2="0" class="scalebar"/><text x="${r1(bar / 2)}" y="-7" class="small" text-anchor="middle">5 km</text></g>`;
  layers += `<rect x="12" y="12" width="112" height="26" class="plate"/><text x="20" y="30" class="small">North is up</text>`;

  const swatches = scale
    .map(
      (b, i) =>
        `<span class="sw"><i style="background:linear-gradient(${b.colour}80,${b.colour}80),#ebe9e4"></i>${b.from}${i === scale.length - 1 ? '+' : ''}</span>`
    )
    .join('');
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Map of ${esc(label)}, the nearest runways and the published flight routes">
<rect width="${W}" height="${H}" class="ground"/>${layers}</svg>
<div class="legend"><span class="key-line fin"></span>Final approach${routes.departures.some((d) => d.dist <= SCOPE_KM) ? ' <span class="key-line dep"></span>Departure route' : ''}
${raster ? `<span class="gap"></span>Aircraft noise, DEFRA (dB Lden): ${swatches}` : ''}</div>`;
}

function districtSvg(c) {
  const [W, H, base] = [420, 150, 112];
  const max = Math.max(...c.bins);
  const bw = W / 10;
  const bars = c.bins
    .map((n, i) => {
      const bh = max ? (n / max) * (base - 14) : 0;
      return `<rect x="${r1(i * bw + 3)}" y="${r1(base - bh)}" width="${r1(bw - 6)}" height="${r1(bh)}" class="${i === c.mineBin ? 'mine' : 'bin'}"/>`;
    })
    .join('');
  const ticks = [0, 2, 4, 6, 8, 10]
    .map((t) => `<text x="${r1(t * bw)}" y="${base + 17}" class="dsmall" text-anchor="middle">${t}</text>`)
    .join('');
  return `<svg viewBox="-8 0 ${W + 16} ${H}" role="img" aria-label="Quiet Skies scores of the ${c.n} postcodes in ${esc(c.outcode)} on DEFRA's map">
${bars}<line x1="0" y1="${base}" x2="${W}" y2="${base}" class="axis"/>${ticks}
<text x="0" y="${H - 4}" class="dsmall">loudest</text><text x="${W}" y="${H - 4}" class="dsmall" text-anchor="end">quietest</text></svg>`;
}

// ---- the page ----------------------------------------------------------------
/**
 * The report as three parts: its title, its stylesheet (every rule but the font
 * face, which the caller supplies) and its body. reportDocument() puts them
 * back together as the standalone page the PDF script prints.
 */
export function reportParts(spec, f) {
  const { env, routes, district, covid, airac } = f;
  // Every figure from the endpoint reaches the page as a NUMBER, guidelines included.
  const who = Number(env.aircraftNoiseWhoGuidelineDb ?? 45);
  const db = env.aircraftNoiseLdenDb;
  const measured = typeof db === 'number';
  // Outside every city the product covers, /v1/environment returns a quiet
  // estimate worked out from nothing nearby (10.0). The site renders that case
  // as not covered, never as the number, and so does the report (2026-10-06,
  // when the report became something any visitor can make, not only Bill).
  const outside = env.aircraftQuietCoverage === 'outside';
  const quiet = measured ? env.aircraftQuiet : outside ? null : env.aircraftQuietEstimated;
  // Is there a DEFRA aircraft map to speak of here at all? Norwich and Teesside have none.
  const aircraftMap = measured || f.hasRaster;
  const name = (code) => AIRPORT_NAME[code] || code;

  // Every approach line whose nearest point is within range. `beside` separates
  // a postcode UNDER or alongside the approach from one level with the runway,
  // where the line's nearest point is its end, on the ground.
  const finals = routes.finals.filter((x) => x.dist <= ROUTE_RADIUS_KM).sort((a, b) => a.dist - b.dist);
  const deps = routes.departures.filter((x) => x.dist <= ROUTE_RADIUS_KM).sort((a, b) => a.dist - b.dist);
  const top = finals.find((x) => x.beside);
  const ft = (x) => `${(Math.round(x.heightFt / 100) * 100).toLocaleString('en-GB')} ft`;

  const tiles = [];
  if (measured) {
    tiles.push([
      `${Math.round(db)} dB`,
      `average aircraft noise outdoors across a year (Lden), on DEFRA's official map. The WHO guideline is ${who} dB`,
    ]);
  }
  if (measured && typeof quiet === 'number') {
    tiles.push([`${quiet.toFixed(1)}/10`, "Sky Score's Quiet Skies score for this postcode. 10 is quietest"]);
  }
  const near = routes.scope[0]; // the nearest airport in the data, if any lies within SCOPE_KM
  if (near) {
    tiles.push([
      `${km(near.dist)} km`,
      `to the nearest runway, at ${esc(name(near.code))} Airport, which lies to the ${compass(near.q)}`,
    ]);
  }
  if (top) {
    tiles.push([
      top.dist < 0.05 ? 'Overhead' : `${km(top.dist)} km`,
      `from the approach line to ${esc(name(top.code))} runway ${esc(top.rwy)}, where landing aircraft are at about ${ft(top)}`,
    ]);
  }
  if (!measured && typeof quiet === 'number') {
    tiles.push([
      `${quiet.toFixed(1)}/10`,
      'Quiet Skies ESTIMATE (10 is quietest), worked out from flight-path geometry. It is not a measurement: see below',
    ]);
  }

  // The table holds six rows. They are the NEAREST six, approaches and
  // departures together, so a route a bullet names as nearest cannot be one
  // the table left out (four approach ends can sit within range of one home).
  const rows = [
    ...finals.map((x) => ({
      dist: x.dist,
      cells: [
        `Landings, ${esc(name(x.code))} runway ${esc(x.rwy)}`,
        `landing towards the ${x.towards}`,
        where(x.dist, x.q),
        x.beside ? `about ${ft(x)}` : 'at the runway',
      ],
    })),
    ...deps.map((x) => ({
      dist: x.dist,
      cells: [
        `Departures, ${esc(x.name)} route, ${esc(name(x.code))} runway ${esc(x.rwy)}`,
        `taking off towards the ${x.towards}`,
        where(x.dist, x.q),
        'not published',
      ],
    })),
  ]
    .sort((a, b) => a.dist - b.dist)
    .slice(0, 6)
    .map((r) => r.cells);

  // "WHAT THIS SHOWS" IS GONE (Bill's yes to mock-up v3, 2026-11-12, claude.ai/artifact/PETRJg3HpWznos2MV8TLuL): it held
  // only what no tile, row or chart says, under a heading that said nothing. Each of its two lines now sits beside what it
  // explains: why DEFRA gives no figure here under the key figures on page 1 (the estimate tile says "see below"), and a
  // postcode beside a runway rather than under its approach under the routes table on page 2.
  // The endpoint's own sentence says WHY there is no measurement here (outside DEFRA's contours, or no contours published
  // at all); do not paraphrase it. Chosen by content, not position: the same array carries road notices.
  const aircraftNotice = (f.notices || []).find((n) => /aircraft/i.test(n));
  const whyNone = measured ? '' : `<p class="cap moved why">${esc(aircraftNotice || "DEFRA's map gives no aircraft noise level for this postcode.")}</p>`;
  const runwaySide = !top && near
    ? `<p class="cap moved">${esc(name(near.code))} Airport's runway is <strong>${km(near.dist)} km to the ${compass(near.q)}</strong>. ${
        finals.length
          ? 'This postcode is level with the runway, to its side, not under an approach line: the nearest point of each approach is the runway end.'
          : `No published approach line passes within ${ROUTE_RADIUS_KM} km of this postcode.`
      }</p>`
    : '';
  // The district's shares, word for word as the bullet said them, now under its chart.
  const districtFact = district
    ? `Of the ${district.n.toLocaleString('en-GB')} postcodes in ${esc(district.outcode)} on DEFRA's map, <strong>${district.quieterPct}% are quieter</strong> than this one and ${district.louderPct}% are louder.`
    : '';

  const listed = (xs) => (xs.length > 1 ? `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}` : xs[0]);
  const covered = routes.scope.filter((a) => a.method !== 'not-drawn').map((a) => esc(name(a.code)));
  const gaps = routes.scope
    .map((a) =>
      a.method === 'conventional'
        ? `${esc(name(a.code))}'s departure routes are published only as charts and are not included.`
        : a.method === 'none'
          ? `${esc(name(a.code))} publishes no standard departure routes.`
          : a.method === 'not-drawn'
            ? `${esc(name(a.code))}'s routes are not included.`
            : ''
    )
    .filter(Boolean);
  const scopeLine = [
    covered.length
      ? `Airports covered: ${listed(covered)}.`
      : `No airport in this report's data lies within ${SCOPE_KM} km.`,
    ...gaps,
    'Smaller airfields, military flights and helicopters are not covered.',
  ].join(' ');

  // THE HEADLINE (Bill's pick C): the sentence the full map's answer card and the front page give this place, from
  // the one writer of it (answerLead), so the three can never disagree. A sentence about DEFRA's figures names the
  // postcode those figures are for; the planes' sentence names its own.
  const pm = (f.planes && f.planes.model) || null; // planesModel() for this postcode, or null: not counted, say nothing
  const steps = (f.planes && f.planes.steps) || [];
  const lead = answerLead(env, f.resolvedAs || f.postcode, pm, steps);

  // PLANES OVERHEAD (Bill's pick C): the front page's chart (planesChart), only where js/planes.mjs has counted this
  // postcode, with the overhead rule and the period under it; the other rules, word for word, are reading points.
  // Two airports (SW1P, E16): one heading, the busiest first (the one the headline names), each chart labelled, and the
  // overhead rule and the period said once under them, so the pair fits its page.
  const peak = (a) => Math.max(0, ...a.rows.map((r) => (Array.isArray(r.value) ? r.value[1] : typeof r.value === 'number' ? r.value : 0)));
  const flown = pm ? [...pm.airports].sort((a, b) => peak(b) - peak(a)) : [];
  const periods = [...new Set(flown.map((a) => a.period))];
  const planesBlock = pm
    ? (flown.length
        ? `<h2>Planes overhead a day${flown.length === 1 ? `, from ${esc(flown[0].name)}` : ''}</h2>` +
          flown.map((a) => `<div class="blk">${flown.length > 1 ? `<p class="from">From ${esc(a.name)}</p>` : ''}${planesChart(a, steps)}</div>`).join('') +
          `<p class="cap">${esc([pm.rules.overhead, `${periods.length === 1 ? periods[0] : flown.map((a) => `${a.name}: ${a.period}`).join('; ')}.`].filter(Boolean).join(' '))}</p>`
        : `<h2>${esc(pm.heading)}</h2><p class="cap">${esc([pm.none, pm.rules.overhead].filter(Boolean).join(' '))}</p>`) +
      [pm.edge, pm.approx, pm.other].filter(Boolean).map((s) => `<p class="cap">${esc(s)}</p>`).join('')
    : '';
  // "Under 1 a day" is a figure too (audit A-9, 2026-11-12): it carries the overhead rule above and the other rules and
  // the flight tracks' credit here, as a counted airport's chart does, or 158,748 postcodes' figure went out bare.
  const planesPoints = pm ? [pm.rules.direction, pm.counted, pm.rules.postcodes].filter(Boolean).map(esc) : [];
  const planesCredits = pm && pm.credits.length ? ` Planes overhead: ${pm.credits.map(esc).join('; ')}.` : '';

  // ROAD NOISE (Bill's pick C): the full map's own finding and bars (roadFinding, pictureHtml) for this postcode's
  // modelled figure against the WHO's, or DEFRA's surveyed-quiet bound, which is no reading and draws no bar. The
  // council's rating stays on the map: this report is about the postcode.
  const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : undefined);
  const roadPeriod = f.provenance && f.provenance['environment.roadNoiseLdenDb'] && /^\d{4}$/.test(String(f.provenance['environment.roadNoiseLdenDb'].period))
    ? String(f.provenance['environment.roadNoiseLdenDb'].period)
    : '';
  // /v1/environment answers for the NEAREST postcode. That is fine for a 1 km air square and wrong for road noise, where
  // neighbours differ by 20 dB, so a neighbour's reading is never drawn as this postcode's (the full map's
  // roadReadingFrom; audit A-11, 2026-11-12): the block then says whose the figure is and draws nothing.
  const neighbourRoad = Boolean(f.resolvedAs) && (num(env.roadNoiseLdenDb) !== undefined || num(env.roadNoiseBelowDb) !== undefined);
  const road = f.resolvedAs
    ? null
    : roadFinding({ db: num(env.roadNoiseLdenDb), belowDb: num(env.roadNoiseBelowDb), who: num(env.roadNoiseWhoGuidelineDb), period: roadPeriod });
  const roadPictures = road ? road.tile.visual.filter(Boolean).map((v) => pictureHtml(v)).join('') : '';
  const roadBlock = road
    ? `<div class="road blk"><h2>Road noise at this postcode</h2><div class="road-row">${roadPictures ? `<div class="road-pics">${roadPictures}</div>` : ''}<p class="cap">${esc(road.tile.say[0])}${typeof env.roadNoiseLdenDb === 'number' ? ` DEFRA's modelled figure${roadPeriod ? ` for ${roadPeriod}` : ''}.` : ''}</p></div></div>`
    : neighbourRoad
      ? `<div class="road blk"><h2>Road noise at this postcode</h2><p class="cap">DEFRA's road noise figure we hold here is for ${esc(f.resolvedAs)}, the nearest postcode, not ${esc(f.postcode)}. Road noise can differ by 20 dB between neighbouring postcodes, so it is not given for this one.</p></div>`
      : '';

  // AIR (Bill's pick C): the full map's charts, DEFRA's model for the postcode's own square beside the nearest sensor
  // and monitor on one scale per pollutant, with the map's key; then only the notes the key does not say already.
  const square = airSquare({ environment: env, provenance: f.provenance });
  const airModel = airModelOf(square);
  const airCharts = ['no2', 'pm25']
    .map((p) => {
      const rows = airRows(p, { model: airModel, sensor: f.sensor, monitor: f.monitor });
      if (!rows.some((r) => typeof r.v === 'number')) return '';
      return `<figure class="air-fig"><figcaption>${esc(AIR_POLLUTANT_NAMES[p].toUpperCase())}, &micro;g/m&sup3;</figcaption>${airChart(p, rows, (square && square.who[p]) || AIR_WHO_2021[p])}</figure>`;
    })
    .filter(Boolean);
  const airKey = [
    airModel && `<li>${airKeyMark('model')}<span><strong>${esc(airModel.label)}</strong> ${esc(airModel.detail)}</span></li>`,
    f.sensor && `<li>${airKeyMark('sensor')}<span><strong>${esc(f.sensor.name)}</strong> ${esc(stationDistance(f.sensor.km))}. ${esc(sensorKeyNote(f.sensor))}</span></li>`,
    f.monitor && `<li>${airKeyMark('monitor')}<span><strong>${esc(f.monitor.name)}</strong> ${esc(stationDistance(f.monitor.km))}. ${esc(monitorKeyNote(f.monitor))}</span></li>`,
  ].filter(Boolean);
  const airPoints = [
    [airModel, f.sensor, f.monitor].filter(Boolean).length > 1 ? 'They measure in different ways, places and periods, so expect them to differ.' : '',
    ...(f.sensor || f.monitor ? airNoteList(f.sensor, f.monitor).filter((n) => n.key === 'roadside' || n.key === 'capture').map((n) => n.text) : []),
  ].filter(Boolean);
  const airBlock = airCharts.length
    ? `<div class="blk"><h2>Air at this postcode, against the WHO guideline</h2><div class="air-two"><div class="air-charts">${airCharts.join('')}</div><ul class="air-key">${airKey.join('')}</ul></div></div>${airPoints.length ? `<ul class="pts">${airPoints.map((t) => `<li>${esc(t)}</li>`).join('')}</ul>` : ''}`
    : '';
  const stationLine = f.station ? `<p class="note"><strong>Nearest station:</strong> ${esc(f.station.name)}, ${stationDistance(f.station.km)} in a straight line.</p>` : '';
  // Where to have your say: the airport whose route passes nearest, only if its pages were verified (HAVE_YOUR_SAY),
  // as buttons (Bill's pick C), then the correction address.
  const say = haveYourSay(routes);
  // No verified pages for the airport (every postcode outside London today): no "Have your say" label over nothing (audit A-1).
  const sayBlock = `<p class="say">${say ? `<strong>Have your say</strong> ${[...say.links, say.change].map((l) => `<a class="chip" href="${esc(l.href)}">${esc(l.text)}</a>`).join(' ')} ` : ''}<span class="wrong"><strong>Spotted something wrong?</strong> <a href="${esc(correctionHref(f.postcode))}">Tell us</a></span></p>`;
  const airCredits = [f.sensor, f.monitor]
    .filter(Boolean)
    .map((r) => ` <a href="${esc(r.credit.href)}">${esc(r.credit.text)}</a>${r.credit.text.endsWith('.') ? '' : '.'}`)
    .join('');

  // data/covid-understatement.json (scripts/measure_covid_understatement.py). Its CAA keys carry no
  // year (`caa_km2`, `caa_year`, since 2026-11-01), so a new ERCD edition needs no change here. A file
  // without them (an older copy still cached, or one mid-deploy) drops the comparison rather than
  // printing "undefined km2": absence never renders as a measurement.
  const c55row =
    covid && routes.airports[0] && routes.airports[0].code === covid.airport
      ? covid.rows.find((r) => r.lden_db === 55)
      : null;
  const c55 =
    c55row && Number.isFinite(c55row.caa_km2) && Number.isFinite(c55row.defra_2021_km2) && Number.isInteger(covid.caa_year)
      ? c55row
      : null;
  const vintage = c55
    ? `DEFRA's map models 2021, when COVID restrictions cut air traffic. At Heathrow the CAA's model of ${covid.caa_year} puts the 55 dB area at ${c55.caa_km2} km&sup2; against ${c55.defra_2021_km2} km&sup2; on DEFRA's map, so levels today are likely to be higher than DEFRA's map shows. That is an indication, not a correction.`
    : aircraftMap
      ? "DEFRA's map models 2021, when COVID restrictions cut air traffic, so levels today are likely to be higher than DEFRA's map shows."
      : 'DEFRA publishes no aircraft noise map for this airport. Its road-noise map models 2021 traffic, which lockdown reduced.';
  const title = `Aircraft noise at ${esc(f.postcode)}${spec.place ? `, ${esc(spec.place)}` : ''}`;
  // The free copy passes `made` (its UTC day, the one its watermark and reference carry), so
  // "Prepared" cannot disagree with them: a local clock read 10 October at 23:30 UTC on 9
  // October, and a copy that disagrees with itself reads as tampered (audit 2026-10-09 M-6).
  // The PDF script passes none and keeps the local date, so its output does not change.
  const when = spec.made
    ? new Date(`${spec.made}T12:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' })
    : new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });

  // PAGE 1's CARDS, from the one rule glanceCards() holds, and the report's details box (Bill's three-page pick).
  const cards = glanceCards({ env, model: pm, steps, resolvedAs: f.resolvedAs, aircraftMap, sensor: f.sensor, say });
  const cardsHtml = cards.length
    ? `<div class="cards">${cards
        .map((c) => {
          const [mark, word] = GLANCE_WORDS[c.stand || 'none'];
          return `<div class="card ${c.stand || 'none'}" data-card="${c.key}"><div class="top"><b class="n">${esc(c.topic)}</b><span class="w"><i aria-hidden="true">${mark}</i>${word}</span></div>`
            + `<div class="fig">${esc(c.figure)}</div>${c.step ? `<div class="step"><strong>Next step:</strong> ${esc(c.step)}</div>` : ''}<div class="ref">The detail: page ${c.page}</div></div>`;
        })
        .join('')}</div>`
    : '';
  const planesPeriods = pm ? [...new Set(pm.airports.map((a) => a.period).filter(Boolean))] : [];
  const airMeta = f.provenance && f.provenance['environment.no2AnnualMeanUgm3'];
  const airPeriod = airMeta && /^\d{4}$/.test(String(airMeta.period)) ? String(airMeta.period) : '';
  const current = [
    aircraftMap ? "DEFRA's noise maps for 2021, the latest published" : "DEFRA's road noise map for 2021, the latest published",
    airac ? `flight routes AIRAC ${esc(airac)}` : null,
    planesPeriods.length ? `planes counted ${esc(planesPeriods.join('; '))}` : null,
    airPeriod ? `air: DEFRA's model for ${airPeriod}` : null,
  ].filter(Boolean).join(' · ');
  const details = `<div class="details"><b>Report details</b> ${esc(f.postcode)}${spec.place ? `, ${esc(spec.place)}` : ''}${f.council ? `, ${esc(f.council)}` : ''} · prepared ${esc(when)}${spec.ref ? ` · reference ${esc(spec.ref)}` : ''}<br><b>How current</b> ${current}${spec.check ? `<br><b>Check this report</b> <a href="${esc(spec.check)}">${esc(spec.check.replace('https://', ''))}</a>` : ''}</div>`;
  // The footer on every printed page: the reference where the copy has one, the postcode, the day, the routes' AIRAC, and
  // "Page x of 3" (@page margin boxes; a CSS string, so what is quoted in it is escaped for CSS). Print only.
  const cssStr = (s) => `"${String(s).replace(/[\\"]/g, (ch) => `\\${ch}`).replace(/[\r\n]+/g, ' ')}"`;
  const footLine = [spec.ref ? `Reference ${spec.ref}` : null, f.postcode, `Prepared ${when}`, airac ? `AIRAC ${airac}` : null].filter(Boolean).join('  ·  ');
  const pageFooter = `
  @page { @bottom-left { content: ${cssStr(footLine)}; font: 8pt 'Geist', system-ui, sans-serif; color: #5f5e59; }
          @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 8pt 'Geist', system-ui, sans-serif; color: #5f5e59; } }`;

  const css = `  @page { size: A4; margin: 10mm 14mm 8mm; }
  :root { --ink:#1c1c1a; --muted:#5f5e59; --rule:#dedcd6; --band:#f4f2ee; --accent:#b4441a; --fin:#d9480f; --dep:#1d4ed8; }
  body { font-family: 'Geist', system-ui, sans-serif; color: var(--ink); background:#fff; font-size: 10.5pt; line-height: 1.38; margin: 0; }
  h1 { font-size: 18pt; line-height: 1.15; margin: 0 0 3px; }
  .tag { font-size: 8pt; font-weight: 600; letter-spacing: .6px; text-transform: uppercase; color: var(--accent); border: 1px solid var(--accent); border-radius: 3px; padding: 1px 6px; vertical-align: middle; margin-left: 8px; }
  .sub { color: var(--muted); margin: 0 0 9px; }
  h2 { font-size: 12pt; margin: 10px 0 4px; }
  .lead { margin: 0 0 9px; padding: 6px 10px; background: var(--band); border-left: 3px solid var(--accent); font-size: 11.5pt; font-weight: 600; line-height: 1.3; }
  .keys { display: grid; grid-template-columns: repeat(${tiles.length}, 1fr); gap: 7px; margin: 0 0 9px; }
  .key { background: var(--band); border-radius: 6px; padding: 8px 10px; }
  .key .n { font-size: 17pt; font-weight: 700; line-height: 1; }
  .key .l { font-size: 9.5pt; color: var(--muted); margin-top: 4px; }
  svg { display: block; width: 100%; height: auto; }
  .ground { fill: #ebe9e4; } .boro { fill: none; stroke: #a9a79f; stroke-width: 0.8; }
  .fin { fill: none; stroke: var(--fin); stroke-width: 3; } .dep { fill: none; stroke: var(--dep); stroke-width: 2; stroke-dasharray: 9 6; }
  .rwy { fill: none; stroke: var(--ink); stroke-width: 5; } .pin { fill: #fff; stroke: var(--ink); stroke-width: 3; }
  .lab { font-size: 16px; fill: var(--ink); } .strong { font-weight: 700; } .plate { fill: #fff; fill-opacity: 0.85; }
  .small { font-size: 16px; fill: var(--muted); } .dsmall { font-size: 18px; fill: var(--muted); } .scalebar { stroke: var(--ink); stroke-width: 2; } .axis { stroke: var(--rule); stroke-width: 1; }
  .bin { fill: #cfccc4; } .mine { fill: var(--accent); }
  .legend { font-size: 8pt; color: var(--muted); margin: 4px 0 0; display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
  .key-line { display: inline-block; width: 22px; height: 0; border-top: 3px solid var(--fin); margin: 0 2px 0 0; }
  .key-line.dep { border-top: 2px dashed var(--dep); margin-left: 10px; } .gap { width: 12px; }
  .sw { display: inline-flex; align-items: center; gap: 2px; } .sw i { width: 11px; height: 9px; display: inline-block; }
  table { width: 100%; border-collapse: collapse; font-size: 10.5pt; }
  th, td { text-align: left; padding: 4px 6px; border-bottom: 1px solid var(--rule); vertical-align: top; }
  th { font-weight: 600; color: var(--muted); font-size: 9.5pt; }
  td:nth-child(4) { white-space: nowrap; } /* the height: "about 1,800 ft" wrapped to two lines at 10.5 pt (2026-11-12) */
  .cols { display: grid; grid-template-columns: ${planesBlock && district ? '300pt 1fr' : '1fr'}; gap: 16px; align-items: start; }
  .planes svg { max-width: 300pt; } .planes .from { font-size: 10.5pt; font-weight: 600; margin: 6px 0 0; } .district svg { max-width: 300pt; }
  ul { margin: 0; padding-left: 17px; } li { margin: 3px 0; }
  .cap { font-size: 9.5pt; color: var(--muted); margin: 3px 0 2px; }
  .cap.fact { color: var(--ink); }
  .cap.moved { margin: 4px 0 8px; } .cap.why { padding-left: 8px; border-left: 3px solid var(--accent); }
  .note { font-size: 10.5pt; color: var(--muted); margin: 6px 0 0; }
  .road-row { display: grid; grid-template-columns: 1.2fr 1fr; gap: 18px; align-items: center; }
  .t-bars { display: grid; gap: 6px; } .t-bar { display: grid; gap: 2px; }
  .t-cap { display: flex; justify-content: space-between; gap: 8px; font-size: 9.5pt; color: var(--muted); }
  .t-cap b { font-weight: 600; color: var(--ink); font-variant-numeric: tabular-nums; }
  .t-track { height: 6px; background: #e4e3e0; border-radius: 3px; }
  .t-track i { display: block; height: 100%; border-radius: 3px; } .t-track i.here { background: var(--ink); } .t-track i.yard { background: #807e79; }
  /* THREE FIXED PAGES, the answer first (Bill's pick, 2026-11-11 v2; built 2026-11-12): page 1 the answer (cards, key
     figures, map, details), page 2 the aircraft and road detail, page 3 the air and how to read it. Within a page each
     section stays whole and no heading is left at its foot; scripts/address_noise_report.mjs refuses a fourth page. */
  .page { break-after: page; } .page:last-child { break-after: auto; }
  .blk, .district, figure, li, tr, .card { break-inside: avoid; } h2 { break-after: avoid; }
  .page h2.pagehead { font-size: 13pt; margin: 0 0 6px; padding-bottom: 3px; border-bottom: 2px solid var(--accent); }
  .cards { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 0 0 10px; }
  .card { border: 1px solid var(--rule); border-radius: 7px; padding: 8px 10px; display: grid; gap: 3px; align-content: start; }
  .card .top { display: flex; justify-content: space-between; align-items: baseline; gap: 6px; }
  .card b.n { font-size: 11.5pt; }
  .card .w { display: inline-flex; gap: 4px; align-items: center; font-weight: 700; font-size: 9.5pt; white-space: nowrap; }
  .card .w i { font-style: normal; display: inline-grid; place-items: center; width: 14px; height: 14px; border-radius: 50%; color: #fff; font-size: 8.5pt; }
  .card.watch .w { color: #a04d00; } .card.watch .w i { background: #a04d00; }
  .card.good .w { color: #076b36; } .card.good .w i { background: #076b36; }
  .card.none .w { color: var(--muted); } .card.none .w i { background: #8a8880; }
  .card .fig { font-size: 10.5pt; font-weight: 600; }
  .card .step { font-size: 9.5pt; color: var(--muted); } .card .step strong { color: var(--accent); }
  .card .ref { font-size: 9pt; color: var(--muted); }
  .details { margin: 10px 0 0; padding: 7px 10px; background: var(--band); border-radius: 6px; font-size: 9.5pt; line-height: 1.5; overflow-wrap: anywhere; }
  .details b { margin-right: 4px; }${pageFooter}
  .air-two { display: grid; grid-template-columns: 320pt 1fr; gap: 16px; align-items: start; }
  .air-charts { display: grid; gap: 8px; }
  .air-fig { margin: 0; } .air-fig figcaption { font-size: 9.5pt; color: var(--muted); margin: 0 0 2px; }
  ul.air-key { list-style: none; padding: 0; margin: 14px 0 0; font-size: 9.5pt; color: var(--muted); }
  ul.air-key li { display: grid; grid-template-columns: 16px 1fr; gap: 5px; margin: 2px 0; }
  ul.air-key svg { width: 14px; height: 14px; margin-top: 1px; } ul.air-key strong { color: var(--ink); }
  ul.pts { font-size: 10.5pt; margin: 6px 0 0; padding-left: 16px; } ul.pts li { margin: 2px 0; }
  .say { font-size: 10.5pt; margin: 10px 0 0; display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
  .say a.chip { border: 1px solid var(--rule); border-radius: 6px; padding: 1px 7px; }
  .say .wrong { margin-left: 4px; }
  footer { margin-top: 10px; padding-top: 6px; border-top: 1px solid var(--rule); font-size: 8.5pt; color: var(--muted); }
`;

  const body = `<section class="page">
<h1>${title}${spec.sample ? '<span class="tag">Sample report</span>' : ''}</h1>
<p class="sub">What ${aircraftMap ? 'the official noise map and the published flight routes' : 'the published flight routes and official data'} say about this postcode${f.council ? `, in ${esc(f.council)}` : ''}.${f.resolvedAs ? ` Noise and air figures are for ${esc(f.resolvedAs)}, the nearest postcode the data resolves to.` : ''} A desktop report from published data: no site visit or survey.</p>
${lead ? `<p class="lead">${esc(lead)}</p>` : ''}
${cardsHtml}
<div class="keys">${tiles.map(([n, l]) => `<div class="key"><div class="n">${n}</div><div class="l">${l}</div></div>`).join('')}</div>
${whyNone}
${f.map}
${details}
</section>
<section class="page">
<h2 class="pagehead">${roadBlock ? 'Aircraft and road noise in detail' : 'Aircraft noise in detail'}</h2>
<h2>Published routes within ${ROUTE_RADIUS_KM} km</h2>
${
  rows.length
    ? `<table><thead><tr><th>Route</th><th>Used when aircraft are</th><th>Closest point to this postcode</th><th>Height</th></tr></thead><tbody>
${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('\n')}</tbody></table>`
    : `<p>No published approach or departure route passes within ${ROUTE_RADIUS_KM} km of this postcode.</p>`
}
<p class="cap">${scopeLine}</p>
${runwaySide}
${planesBlock || district ? `<div class="cols">${planesBlock ? `<div class="planes">${planesBlock}</div>` : ''}${district ? `<div class="district"><h2>How it compares within ${esc(district.outcode)}</h2><p class="cap">Quiet Skies scores of the ${district.n.toLocaleString('en-GB')} postcodes on DEFRA's map. This postcode's band is in orange.</p>${districtSvg(district)}<p class="cap fact">${districtFact}</p></div>` : ''}</div>` : ''}
${roadBlock}
${sayBlock}
</section>
<section class="page">
<h2 class="pagehead">${airBlock ? 'Air, and how to read this report' : 'How to read this report'}</h2>
${airBlock}
${stationLine}
<h2>Reading this report</h2>
<ul class="pts"><li>Lden is a yearly average of the outdoor level, with evening and night flights weighted more heavily; it does not describe single loud events or the number of flights.</li><li>${vintage}</li><li>The route lines are the published centre lines: aircraft fly either side of them, and the path to joining a final approach is directed by air traffic control and is not drawn.</li>${planesPoints.map((t) => `<li>${t}</li>`).join('')}<li>This is information, not a survey or an environmental search; visit at different times of day before deciding.</li><li>It is not a conveyancing search under the Search Code. Our terms: skyscore.co.uk/terms.</li></ul>
<footer>Sources: DEFRA Strategic Noise Mapping Round 4 (${aircraftMap ? 'aircraft and road' : 'road'}, Lden, 2021 traffic) and DEFRA background pollution maps, Open Government Licence v3.0; flight routes from the UK Aeronautical Information Publication (NATS), AIRAC ${esc(airac)}; ${c55 ? `${esc(String(covid.caa || 'CAA ERCD').split(',')[0])}; ` : ''}WHO Environmental Noise Guidelines for the European Region (2018) and Global Air Quality Guidelines (2021); postcode positions from postcodes.io (ONS).${planesCredits}${airCredits} Compiled with Sky Score (skyscore.co.uk). Prepared ${when}.</footer>
</section>
`;
  return { title, css, body };
}

/** The standalone page the PDF script prints. `fontUrl` is where Geist is loaded from. */
export function reportDocument(spec, f, fontUrl) {
  const { title, css, body } = reportParts(spec, f);
  return `<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8"><title>${title}</title>
<style>
  @font-face { font-family: 'Geist'; src: url('${fontUrl}') format('woff2'); font-weight: 100 900; }
${css}</style></head><body>
${body}</body></html>`;
}
