/**
 * The one-page aircraft-noise report for one postcode: everything except
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
/** "650 m" under a kilometre (to the nearest 10 m), "1.4 km" above. */
export const stationDistance = (km) => (km < 1 ? `${Math.round(km * 100) * 10} m` : `${km.toFixed(1)} km`);
const MAP = { w: 1000, h: 345, padKm: 5, minHeightKm: 11 };

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
  const w = text.length * 8.6 + 12;
  return `<rect x="${r1(x - w / 2)}" y="${r1(y - 15)}" width="${r1(w)}" height="20" rx="3" class="plate"/><text x="${r1(x)}" y="${r1(y)}" class="lab${cls}" text-anchor="middle">${esc(text)}</text>`;
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
  layers += `<g transform="translate(18,${H - 16})"><rect x="-6" y="-24" width="${r1(bar + 12)}" height="32" class="plate"/><line x1="0" y1="0" x2="${r1(bar)}" y2="0" class="scalebar"/><text x="${r1(bar / 2)}" y="-7" class="small" text-anchor="middle">5 km</text></g>`;
  layers += `<rect x="12" y="12" width="92" height="24" class="plate"/><text x="20" y="29" class="small">North is up</text>`;

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
    .map((t) => `<text x="${r1(t * bw)}" y="${base + 14}" class="small" text-anchor="middle">${t}</text>`)
    .join('');
  return `<svg viewBox="-8 0 ${W + 16} ${H}" role="img" aria-label="Quiet Skies scores of the ${c.n} postcodes in ${esc(c.outcode)} on DEFRA's map">
${bars}<line x1="0" y1="${base}" x2="${W}" y2="${base}" class="axis"/>${ticks}
<text x="0" y="${H - 6}" class="small">loudest</text><text x="${W}" y="${H - 6}" class="small" text-anchor="end">quietest</text></svg>`;
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

  const bullets = [];
  if (measured) {
    const diff = Math.round(db - who);
    bullets.push(
      `Aircraft noise here averages <strong>${Math.round(db)} dB</strong> outdoors across the year, ${diff > 0 ? `${diff} dB above` : diff < 0 ? `${-diff} dB below` : 'level with'} the ${who} dB the WHO recommends.`
    );
  } else {
    // The endpoint's own sentence says WHY there is no measurement here (outside
    // DEFRA's contours, or no contours published at all); do not paraphrase it.
    // Chosen by content, not position: the same array carries road notices.
    const aircraftNotice = (f.notices || []).find((n) => /aircraft/i.test(n));
    bullets.push(esc(aircraftNotice || 'There is no measured aircraft noise level for this postcode.'));
  }
  if (top) {
    bullets.push(
      `Aircraft landing on ${esc(name(top.code))}'s runway ${esc(top.rwy)} pass <strong>${where(top.dist, top.q)}</strong> at about ${ft(top)}, on days when the airport is landing towards the ${top.towards}.`
    );
  }
  if (deps[0]) {
    bullets.push(
      `The nearest published departure route (${esc(deps[0].name)}, runway ${esc(deps[0].rwy)}) passes ${where(deps[0].dist, deps[0].q)}.`
    );
  }
  if (!top && near) {
    bullets.push(
      `${esc(name(near.code))} Airport's runway is <strong>${km(near.dist)} km to the ${compass(near.q)}</strong>. ${
        finals.length
          ? 'This postcode is level with the runway, to its side, not under an approach line: the nearest point of each approach is the runway end.'
          : `No published approach line passes within ${ROUTE_RADIUS_KM} km of this postcode.`
      }`
    );
  } else if (!top && !deps[0]) {
    bullets.push(`No published approach or departure route passes within ${ROUTE_RADIUS_KM} km.`);
  }
  if (district) {
    bullets.push(
      `Of the ${district.n.toLocaleString('en-GB')} postcodes in ${esc(district.outcode)} on DEFRA's map, <strong>${district.quieterPct}% are quieter</strong> than this one and ${district.louderPct}% are louder.`
    );
  }

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

  const also = [];
  if (typeof env.roadNoiseLdenDb === 'number')
    also.push(
      `road noise ${env.roadNoiseLdenDb.toFixed(1)} dB Lden (WHO guideline ${Number(env.roadNoiseWhoGuidelineDb)})`
    );
  else if (typeof env.roadNoiseBelowDb === 'number') also.push(`road noise below ${env.roadNoiseBelowDb} dB Lden`);
  if (typeof env.no2AnnualMeanUgm3 === 'number')
    also.push(
      `nitrogen dioxide ${env.no2AnnualMeanUgm3.toFixed(1)} &micro;g/m&sup3; (guideline ${Number(env.no2WhoGuidelineUgm3)})`
    );
  if (typeof env.pm25AnnualMeanUgm3 === 'number')
    also.push(
      `fine particles ${env.pm25AnnualMeanUgm3.toFixed(1)} &micro;g/m&sup3; (guideline ${Number(env.pm25WhoGuidelineUgm3)})`
    );
  if (f.station) also.push(`nearest station ${esc(f.station.name)}, ${stationDistance(f.station.km)} in a straight line`);

  const c55 =
    covid && routes.airports[0] && routes.airports[0].code === covid.airport
      ? covid.rows.find((r) => r.lden_db === 55)
      : null;
  const vintage = c55
    ? `DEFRA's map models 2021, when COVID restrictions cut air traffic. At Heathrow the CAA's model of 2024 puts the 55 dB area at ${c55.caa_2024_km2} km&sup2; against ${c55.defra_2021_km2} km&sup2; on DEFRA's map, so levels today are likely to be higher than DEFRA's map shows. That is an indication, not a correction.`
    : aircraftMap
      ? "DEFRA's map models 2021, when COVID restrictions cut air traffic, so levels today are likely to be higher than DEFRA's map shows."
      : 'DEFRA publishes no aircraft noise map for this airport. Its road-noise map models 2021 traffic, which lockdown reduced.';
  const title = `Aircraft noise at ${esc(f.postcode)}${spec.place ? `, ${esc(spec.place)}` : ''}`;
  const when = new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });

  const css = `  @page { size: A4; margin: 13mm 15mm 11mm; }
  :root { --ink:#1c1c1a; --muted:#5f5e59; --rule:#dedcd6; --band:#f4f2ee; --accent:#b4441a; --fin:#d9480f; --dep:#1d4ed8; }
  body { font-family: 'Geist', system-ui, sans-serif; color: var(--ink); background:#fff; font-size: 9.5pt; line-height: 1.4; margin: 0; }
  h1 { font-size: 18pt; line-height: 1.15; margin: 0 0 3px; }
  .tag { font-size: 8pt; font-weight: 600; letter-spacing: .6px; text-transform: uppercase; color: var(--accent); border: 1px solid var(--accent); border-radius: 3px; padding: 1px 6px; vertical-align: middle; margin-left: 8px; }
  .sub { color: var(--muted); margin: 0 0 9px; }
  h2 { font-size: 10.5pt; margin: 11px 0 5px; }
  .keys { display: grid; grid-template-columns: repeat(${tiles.length}, 1fr); gap: 7px; margin: 0 0 9px; }
  .key { background: var(--band); border-radius: 6px; padding: 8px 10px; }
  .key .n { font-size: 17pt; font-weight: 700; line-height: 1; }
  .key .l { font-size: 8pt; color: var(--muted); margin-top: 4px; }
  svg { display: block; width: 100%; height: auto; }
  .ground { fill: #ebe9e4; } .boro { fill: none; stroke: #a9a79f; stroke-width: 0.8; }
  .fin { fill: none; stroke: var(--fin); stroke-width: 3; } .dep { fill: none; stroke: var(--dep); stroke-width: 2; stroke-dasharray: 9 6; }
  .rwy { fill: none; stroke: var(--ink); stroke-width: 5; } .pin { fill: #fff; stroke: var(--ink); stroke-width: 3; }
  .lab { font-size: 15px; fill: var(--ink); } .strong { font-weight: 700; } .plate { fill: #fff; fill-opacity: 0.85; }
  .small { font-size: 12px; fill: var(--muted); } .scalebar { stroke: var(--ink); stroke-width: 2; } .axis { stroke: var(--rule); stroke-width: 1; }
  .bin { fill: #cfccc4; } .mine { fill: var(--accent); }
  .legend { font-size: 8pt; color: var(--muted); margin: 4px 0 0; display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
  .key-line { display: inline-block; width: 22px; height: 0; border-top: 3px solid var(--fin); margin: 0 2px 0 0; }
  .key-line.dep { border-top: 2px dashed var(--dep); margin-left: 10px; } .gap { width: 12px; }
  .sw { display: inline-flex; align-items: center; gap: 2px; } .sw i { width: 11px; height: 9px; display: inline-block; }
  table { width: 100%; border-collapse: collapse; font-size: 8.8pt; }
  th, td { text-align: left; padding: 4px 6px; border-bottom: 1px solid var(--rule); vertical-align: top; }
  th { font-weight: 600; color: var(--muted); font-size: 8.2pt; }
  .cols { display: grid; grid-template-columns: ${district ? '1.25fr 1fr' : '1fr'}; gap: 16px; align-items: start; }
  ul { margin: 0; padding-left: 17px; } li { margin: 3px 0; }
  .cap { font-size: 8pt; color: var(--muted); margin: 0 0 2px; }
  .note { font-size: 8pt; color: var(--muted); margin: 8px 0 0; }
  footer { margin-top: 9px; padding-top: 6px; border-top: 1px solid var(--rule); font-size: 7.4pt; color: var(--muted); }
`;

  const body = `<h1>${title}${spec.sample ? '<span class="tag">Sample report</span>' : ''}</h1>
<p class="sub">What ${aircraftMap ? 'the official noise map and the published flight routes' : 'the published flight routes and official data'} say about this postcode${f.council ? `, in ${esc(f.council)}` : ''}.${f.resolvedAs ? ` Noise and air figures are for ${esc(f.resolvedAs)}, the nearest postcode the data resolves to.` : ''}</p>
<div class="keys">${tiles.map(([n, l]) => `<div class="key"><div class="n">${n}</div><div class="l">${l}</div></div>`).join('')}</div>
${f.map}
<h2>Published routes within ${ROUTE_RADIUS_KM} km</h2>
${
  rows.length
    ? `<table><thead><tr><th>Route</th><th>Used when aircraft are</th><th>Closest point to this postcode</th><th>Height</th></tr></thead><tbody>
${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('\n')}</tbody></table>`
    : `<p>No published approach or departure route passes within ${ROUTE_RADIUS_KM} km of this postcode.</p>`
}
<p class="note" style="margin-top:4px">${scopeLine}</p>
<div class="cols"><div><h2>What this shows</h2><ul>${bullets.map((b) => `<li>${b}</li>`).join('')}</ul></div>
${district ? `<div><h2>How it compares within ${esc(district.outcode)}</h2><p class="cap">Quiet Skies scores of the ${district.n.toLocaleString('en-GB')} postcodes on DEFRA's map. This postcode's band is in orange.</p>${districtSvg(district)}</div>` : ''}</div>
${also.length ? `<p class="note"><strong>Also at this postcode:</strong> ${also.join('; ')}.</p>` : ''}
<p class="note"><strong>Reading this report.</strong> Lden is a yearly average of the outdoor level, with evening and night flights weighted more heavily; it does not describe single loud events or the number of flights. ${vintage} The route lines are the published centre lines: aircraft fly either side of them, and the path to joining a final approach is directed by air traffic control and is not drawn. This is information, not a survey or an environmental search; visit at different times of day before deciding.</p>
<footer>Sources: DEFRA Strategic Noise Mapping Round 4 (${aircraftMap ? 'aircraft and road' : 'road'}, Lden, 2021 traffic) and DEFRA background pollution maps, Open Government Licence v3.0; flight routes from the UK Aeronautical Information Publication (NATS), AIRAC ${esc(airac)}; ${c55 ? 'CAA ERCD Report 2501; ' : ''}WHO Environmental Noise Guidelines for the European Region (2018) and Global Air Quality Guidelines (2021); postcode positions from postcodes.io (ONS). Compiled with Sky Score (skyscore.co.uk). Prepared ${when}.</footer>
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
