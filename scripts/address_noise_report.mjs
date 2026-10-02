/**
 * Aircraft-noise report for ONE postcode, as a one-page PDF.
 *
 *   node scripts/address_noise_report.mjs --postcode "TW9 3PZ" --place "Kew" \
 *     --sample --out "C:/Users/bilal/OneDrive/Desktop/aircraft-noise-report.pdf"
 *
 * WHY THIS EXISTS (2026-10-02). Geovation's advice was to narrow to the
 * flight-path niche and to test paid reports. `area_summary.mjs` is the free
 * community sheet (air and road noise across an area); this is the business
 * one: what the official map and the published routes say about one postcode.
 * See ROADMAP "Monetisation, ranked". It is a SAMPLE generator until the gates
 * recorded there are met (licence for the route data, insurance, the rename).
 *
 * WHERE EVERY NUMBER COMES FROM, so nothing on the page is typed by hand:
 *   - aircraft and road noise, NO2, PM2.5: the LIVE /v1/environment endpoint;
 *   - flight routes: data/flight-procedures.json, the UK AIP record that
 *     build_flight_paths.py generates the map's lines from. A final approach
 *     is the same line the builder draws: threshold, true bearing and glide
 *     angle, out to FINAL_TOP_FT;
 *   - the noise picture on the map: the DEFRA PNG the site paints, placed by
 *     the bbox the site holds for it, with the band colours read out of
 *     index.html (NOISE_SCALE_DEFRA_LDEN) so the legend cannot drift from it;
 *   - the district comparison: the per-postcode Quiet Skies datasets the site
 *     ships, limited to LIVE postcodes (postcodes.io), because those files
 *     keep terminated ones;
 *   - the 2021-vs-2024 caveat: data/covid-understatement.json.
 *
 * WHAT IT DELIBERATELY DOES NOT SAY. How OFTEN aircraft pass: that is N65,
 * which this product does not hold. Any adjective for the level ("severe",
 * "acceptable"): the page compares with the WHO guideline and stops there.
 * A height for departures: the AIP record carries none.
 * No em dashes in the output, matching the site's rule.
 */
import { chromium } from '@playwright/test';
import { existsSync } from 'node:fs';
import { readFile, rename, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

import { AIRPORT_NAME, ORIGIN, add, compass, mul, plane, reciprocal, routesNear } from './flight_geometry.mjs';

const API = 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/environment';
// A route further away than this is not listed. A judgement, stated on the page.
const ROUTE_RADIUS_KM = 5;
// An airport nearer than this is named on the page, with what the report holds for it.
const SCOPE_KM = 40;
const MIN_DISTRICT = 30; // fewer live measured postcodes than this: no comparison chart
const MAP = { w: 1000, h: 345, padKm: 5, minHeightKm: 11 };

function args(argv) {
  const out = { sample: false };
  for (let i = 2; i < argv.length; i++) {
    const [k, v] = [argv[i], argv[i + 1]];
    if (k === '--postcode') ((out.postcode = v), i++);
    else if (k === '--place') ((out.place = v), i++);
    else if (k === '--out') ((out.out = v), i++);
    else if (k === '--sample') out.sample = true;
    else throw new Error(`unknown argument ${k}`);
  }
  if (!out.postcode) throw new Error('usage: --postcode "TW9 3PZ" [--place "Kew"] [--sample] [--out file.pdf]');
  out.postcode = out.postcode.trim().toUpperCase();
  // The same filter the score Lambda applies before a postcode reaches a URL path.
  if (!/^[A-Z0-9 ]{5,8}$/.test(out.postcode)) throw new Error(`"${out.postcode}" is not a postcode`);
  out.out = resolve(out.out || `aircraft-noise-${out.postcode.replace(/\s+/g, '').toLowerCase()}.pdf`);
  return out;
}

const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const km = (x) => x.toFixed(1);
const r1 = (x) => Math.round(x * 10) / 10;

const where = (d, q) => (d < 0.05 ? 'directly overhead' : `${km(d)} km to the ${compass(q)}`);

// ---- sources ---------------------------------------------------------------
async function lookup(postcode) {
  const r = await fetch(`https://api.postcodes.io/postcodes/${encodeURIComponent(postcode)}`);
  if (r.status === 404) throw new Error(`postcodes.io does not know ${postcode}`);
  if (!r.ok) throw new Error(`postcodes.io answered ${r.status}`);
  return (await r.json()).result;
}
async function environment(lat, lon) {
  const r = await fetch(`${API}?lat=${lat}&lon=${lon}`);
  if (!r.ok) throw new Error(`/v1/environment answered ${r.status}`);
  return r.json();
}
/** Which of these postcodes are live. The quiet datasets keep terminated ones. */
async function livePostcodes(codes) {
  const live = new Set();
  for (let i = 0; i < codes.length; i += 100) {
    const r = await fetch('https://api.postcodes.io/postcodes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ postcodes: codes.slice(i, i + 100) }),
    });
    if (!r.ok) throw new Error(`postcodes.io bulk lookup answered ${r.status}`);
    for (const row of (await r.json()).result) if (row.result) live.add(row.query);
    await sleep(150);
  }
  return live;
}
const readJson = async (p) => JSON.parse(await readFile(resolve(p), 'utf8'));

/** DEFRA's band colours, from the one holder the site's legend reads. */
function defraScale(indexHtml) {
  const block = /const NOISE_SCALE_DEFRA_LDEN = \[([\s\S]*?)\]/.exec(indexHtml);
  const bands = [...(block ? block[1] : '').matchAll(/from:\s*(\d+),\s*colour:\s*'(#[0-9A-Fa-f]{6})'/g)].map((m) => ({
    from: Number(m[1]),
    colour: m[2],
  }));
  if (bands.length < 5) throw new Error('NOISE_SCALE_DEFRA_LDEN not found in index.html - the legend holder has moved');
  return bands;
}
/** The DEFRA PNG whose box contains this point, and the city key it belongs to. */
function rasterFor(indexHtml, regions, lat, lon) {
  const inside = (b) => lat >= b.minLat && lat <= b.maxLat && lon >= b.minLon && lon <= b.maxLon;
  const m = /const LONDON_AIRCRAFT_BBOX = \{([\s\S]*?)\}/.exec(indexHtml);
  if (!m) throw new Error('LONDON_AIRCRAFT_BBOX not found in index.html - the holder has moved');
  const london = Object.fromEntries([...m[1].matchAll(/(\w+):\s*(-?[\d.]+)/g)].map((x) => [x[1], Number(x[2])]));
  if (inside(london)) return { city: 'london', png: 'data/aircraft-noise-london-lden.png', bbox: london };
  for (const [city, c] of Object.entries(regions.cities || {})) {
    if (inside(c.bbox)) return { city, png: c.png.replace(/^\//, ''), bbox: c.bbox };
  }
  return null;
}

// ---- the report's facts ----------------------------------------------------
async function districtComparison(outcode, mine) {
  if (typeof mine !== 'number') return null;
  const quiet = {
    ...(await readJson('data/aircraft-quiet-london.json')).quiet,
    ...(await readJson('data/aircraft-quiet-regions.json')).quiet,
  };
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
function mapSvg({ pl, routes, raster, boroughs, scale, label }) {
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
    layers += `<image href="${pathToFileURL(resolve(raster.png)).href}" x="${ix0}" y="${iy0}" width="${r1(ix1 - ix0)}" height="${r1(iy1 - iy0)}" preserveAspectRatio="none"/>`;
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

function page(spec, f) {
  const { env, routes, district, covid, airac } = f;
  // Every figure from the endpoint reaches the page as a NUMBER, guidelines included.
  const who = Number(env.aircraftNoiseWhoGuidelineDb ?? 45);
  const db = env.aircraftNoiseLdenDb;
  const measured = typeof db === 'number';
  const quiet = measured ? env.aircraftQuiet : env.aircraftQuietEstimated;
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

  return `<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8"><title>${title}</title>
<style>
  @font-face { font-family: 'Geist'; src: url('${pathToFileURL(resolve('fonts/geist.woff2')).href}') format('woff2'); font-weight: 100 900; }
  @page { size: A4; margin: 13mm 15mm 11mm; }
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
</style></head><body>
<h1>${title}${spec.sample ? '<span class="tag">Sample report</span>' : ''}</h1>
<p class="sub">What ${aircraftMap ? 'the official noise map and the published flight routes' : 'the published flight routes and official data'} say about this postcode${f.council ? `, in ${esc(f.council)}` : ''}.${f.resolvedAs ? ` Noise and air figures are for ${esc(f.resolvedAs)}, the nearest postcode the data resolves to.` : ''}</p>
<div class="keys">${tiles.map(([n, l]) => `<div class="key"><div class="n">${n}</div><div class="l">${l}</div></div>`).join('')}</div>
${f.map}
<h2>Published routes within ${ROUTE_RADIUS_KM} km</h2>
${
  rows.length
    ? `<table><thead><tr><th>Route</th><th>Used when aircraft are</th><th>Closest point to this postcode</th><th>Height there</th></tr></thead><tbody>
${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('\n')}</tbody></table>`
    : `<p>No published approach or departure route passes within ${ROUTE_RADIUS_KM} km of this postcode.</p>`
}
<p class="note" style="margin-top:4px">${scopeLine}</p>
<div class="cols"><div><h2>What this shows</h2><ul>${bullets.map((b) => `<li>${b}</li>`).join('')}</ul></div>
${district ? `<div><h2>How it compares within ${esc(district.outcode)}</h2><p class="cap">Quiet Skies scores of the ${district.n.toLocaleString('en-GB')} postcodes on DEFRA's map. This postcode's band is in orange.</p>${districtSvg(district)}</div>` : ''}</div>
${also.length ? `<p class="note"><strong>Also at this postcode:</strong> ${also.join('; ')}.</p>` : ''}
<p class="note"><strong>Reading this report.</strong> Lden is a yearly average of the outdoor level, with evening and night flights weighted more heavily; it does not describe single loud events or the number of flights. ${vintage} The route lines are the published centre lines: aircraft fly either side of them, and the path to joining a final approach is directed by air traffic control and is not drawn. This is information, not a survey or an environmental search; visit at different times of day before deciding.</p>
<footer>Sources: DEFRA Strategic Noise Mapping Round 4 (${aircraftMap ? 'aircraft and road' : 'road'}, Lden, 2021 traffic) and DEFRA background pollution maps, Open Government Licence v3.0; flight routes from the UK Aeronautical Information Publication (NATS), AIRAC ${esc(airac)}; ${c55 ? 'CAA ERCD Report 2501; ' : ''}WHO Environmental Noise Guidelines for the European Region (2018) and Global Air Quality Guidelines (2021); postcode positions from postcodes.io (ONS). Compiled with Sky Score (skyscore.co.uk). Prepared ${when}.</footer>
</body></html>`;
}

// ---- run -------------------------------------------------------------------
const spec = args(process.argv);
const loc = await lookup(spec.postcode);
const envBody = await environment(loc.latitude, loc.longitude);
const env = envBody.environment || {};
// The endpoint reverse-geocodes a coordinate, so it can answer for a
// neighbour. That goes ON THE PAGE, never only in the terminal.
const resolvedAs = envBody.location && envBody.location.postcode !== loc.postcode ? envBody.location.postcode : null;
if (resolvedAs)
  console.error(`note: /v1/environment answered for ${resolvedAs}, the postcode nearest ${loc.postcode}'s centre`);

const indexHtml = await readFile(resolve('index.html'), 'utf8');
const proc = await readJson('data/flight-procedures.json');
const pl = plane(loc.latitude, loc.longitude);
const routes = routesNear(proc, pl, SCOPE_KM);
const raster = rasterFor(indexHtml, await readJson('data/aircraft-noise-rasters.json'), loc.latitude, loc.longitude);
// Area outlines for the raster's city and every city the nearest airport
// serves (East Midlands serves two). Keyed on the airport as well as the
// raster because Norwich and Teesside have no DEFRA aircraft map at all, and
// a map with no outlines gives the reader nothing to place the pin against.
const home = routes.airports[0];
const outlineCities = new Set([
  ...(raster ? [raster.city] : []),
  ...(home && home.dist <= SCOPE_KM ? proc.airports[home.code].cities : []),
]);
const boroughs = { features: [] };
for (const city of outlineCities) {
  const file = resolve(`data/${city}-boroughs.json`);
  if (existsSync(file)) boroughs.features.push(...(await readJson(file)).features);
}
const district = await districtComparison(loc.outcode, env.aircraftQuiet);

const html = page(spec, {
  postcode: loc.postcode,
  council: loc.admin_district,
  hasRaster: Boolean(raster),
  resolvedAs,
  notices: envBody.notices,
  env,
  routes,
  district,
  covid: await readJson('data/covid-understatement.json'),
  airac: proc.airac,
  map: mapSvg({ pl, routes, raster, boroughs, scale: defraScale(indexHtml), label: loc.postcode }),
});
if (html.includes(String.fromCharCode(0x2014))) throw new Error('em dash in output');
const htmlPath = spec.out.replace(/\.pdf$/i, '.html');
await writeFile(htmlPath, html, 'utf8');

const browser = await chromium.launch();
try {
  const pg = await browser.newPage();
  await pg.goto(pathToFileURL(htmlPath).href, { waitUntil: 'load' });
  const tmp = spec.out.replace(/\.pdf$/i, '.NEW.pdf');
  const pdf = await pg.pdf({ path: tmp, format: 'A4', printBackground: true, preferCSSPageSize: true, tagged: true });
  // It is sold as ONE page. Count the page objects rather than trusting the layout.
  const pages = (pdf.toString('latin1').match(/\/Type\s*\/Page[^s]/g) || []).length;
  if (pages !== 1) {
    console.error(`the report ran to ${pages} pages, not 1 - shorten it before sending`);
    process.exitCode = 1;
  }
  try {
    await rename(tmp, spec.out);
  } catch (e) {
    console.error(`Could not replace ${spec.out} - close it in any PDF viewer and re-run. (${e.code})`);
    process.exitCode = 1;
  }
} finally {
  await browser.close();
}
const listed =
  routes.finals.filter((x) => x.dist <= ROUTE_RADIUS_KM).length +
  routes.departures.filter((x) => x.dist <= ROUTE_RADIUS_KM).length;
console.log(
  `${loc.postcode} (${loc.admin_district}): aircraft ${typeof env.aircraftNoiseLdenDb === 'number' ? `${env.aircraftNoiseLdenDb} dB measured` : 'not measured'}, ` +
    `${listed} routes within ${ROUTE_RADIUS_KM} km, district comparison ${district ? `${district.n} live postcodes` : 'none'}\n  ${spec.out}`
);
