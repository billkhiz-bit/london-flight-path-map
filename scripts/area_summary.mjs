/**
 * One-page air-quality and noise summary for a local area, as a PDF.
 *
 *   node scripts/area_summary.mjs --area "Earls Court" \
 *     --point "Earls Court station=SW5 9NJ" --point "Nevern Square=SW5 9TL" \
 *     --out "C:/Users/bilal/OneDrive/Desktop/earls-court-summary.pdf"
 *
 * WHY THIS EXISTS (2026-09-29). The community plan in OUTREACH_TARGETS.md
 * offers residents' groups a free one-pager for their area. The first one
 * (Earls Court) was assembled by hand; this makes the offer repeatable.
 *
 * WHERE EVERY NUMBER COMES FROM, so nothing on the page is typed by hand:
 *   - per-point NO2, PM2.5 and road noise: the LIVE /v1/environment endpoint
 *     (unauthenticated, measurements only), one call per point, spaced to stay
 *     well under that route's 5 RPS throttle;
 *   - the borough comparison: data/borough-extra.json, the same holder the
 *     site's panels read, ranked within the borough's own city;
 *   - for a council area the map does not carry (an API-only city such as
 *     Greater Norwich): open-data/sky-score-boroughs.csv, ranked against
 *     EVERY UK council area in it. A city of three authorities gives no
 *     meaningful rank within itself, and that file is the one holder with
 *     them all;
 *   - the data year: parsed from the API's own source line, so the page
 *     re-dates itself when the air-quality vintage rolls.
 * Postcodes resolve through postcodes.io, as the site's search does.
 *
 * --aircraft adds what the published runway data says about each point: how
 * far the nearest runway is, whether the point sits under an approach line,
 * and DEFRA's measured aircraft level where one exists. Geometry and
 * measurements only: it never prints the estimated Quiet Skies figure, because
 * a sheet handed to a residents' group should not lead with an estimate.
 *
 * Only publishes what is measured: a point with no reading says so, a city
 * with one borough gets no rank, and the limits note is always printed.
 * No em dashes in the output, matching the site's rule.
 */
import { chromium } from '@playwright/test';
import { readFile, rename, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

import { AIRPORT_NAME, compass, plane, routesNear } from '../js/flight_geometry.mjs';

const API = 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/environment';
const WHO = { no2: 10, pm25: 5, road: 53, aircraft: 45 };
// --aircraft: airports nearer than scopeKm are considered; a point within
// underKm of an approach line, and alongside it, counts as under it.
const AIRCRAFT = { scopeKm: 40, underKm: 2 };
const CITY_LABEL = {
  london: "London's 33 boroughs",
  manchester: 'Greater Manchester',
  westmidlands: 'the West Midlands',
  westyorkshire: 'West Yorkshire',
  southyorkshire: 'South Yorkshire',
  merseyside: 'Merseyside',
  tyneandwear: 'Tyne and Wear',
  bristol: 'the Bristol area',
  leicester: 'Leicestershire',
  teesside: 'Teesside',
};

function args(argv) {
  const out = { points: [] };
  for (let i = 2; i < argv.length; i++) {
    const [k, v] = [argv[i], argv[i + 1]];
    if (k === '--area') (out.area = v), i++;
    else if (k === '--aircraft') out.aircraft = true;
    else if (k === '--out') (out.out = v), i++;
    else if (k === '--point') {
      const eq = v.lastIndexOf('=');
      if (eq < 1) throw new Error(`--point must be "Label=POSTCODE", got "${v}"`);
      out.points.push({ label: v.slice(0, eq).trim(), postcode: v.slice(eq + 1).trim().toUpperCase() });
      i++;
    } else throw new Error(`unknown argument ${k}`);
  }
  if (!out.area || !out.points.length) {
    throw new Error('usage: --area "Name" --point "Label=POSTCODE" [--point ...] [--aircraft] [--out file.pdf]');
  }
  out.out = resolve(out.out || `area-summary-${out.area.toLowerCase().replace(/[^a-z0-9]+/g, '-')}.pdf`);
  return out;
}

const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const norm = (s) =>
  String(s)
    .toLowerCase()
    .replace(/\./g, '')
    .replace(/^city of |, city of$/g, '')
    .trim();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const ord = (n) => {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};
const fmt = (x) => (typeof x === 'number' ? x.toFixed(1) : '');

async function lookupPostcodes(postcodes) {
  const r = await fetch('https://api.postcodes.io/postcodes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ postcodes }),
  });
  if (!r.ok) throw new Error(`postcodes.io answered ${r.status}`);
  const body = await r.json();
  return body.result.map((x) => x.result);
}

async function environment(lat, lon) {
  const r = await fetch(`${API}?lat=${lat}&lon=${lon}`);
  if (!r.ok) throw new Error(`/v1/environment answered ${r.status}`);
  return r.json();
}

function boroughContext(extra, district) {
  for (const [city, boroughs] of Object.entries(extra)) {
    if (!CITY_LABEL[city] || typeof boroughs !== 'object') continue;
    const names = Object.keys(boroughs).filter((b) => typeof boroughs[b] === 'object');
    const hit = names.find((b) => norm(b) === norm(district)) || names.find((b) => norm(district).startsWith(norm(b)));
    if (!hit) continue;
    const rank = (field) => {
      const vals = names.filter((b) => typeof boroughs[b][field] === 'number');
      vals.sort((a, b) => boroughs[b][field] - boroughs[a][field]);
      return { rank: vals.indexOf(hit) + 1, of: vals.length, above: vals.slice(0, vals.indexOf(hit)) };
    };
    return { city, name: district, rec: boroughs[hit], no2: rank('no2AnnualMeanUgm3'), pm25: rank('pm25AnnualMeanUgm3') };
  }
  return null;
}

/** The open-data CSV as objects. It carries no quoted fields; a row of the wrong width fails loudly. */
function parseCsv(text) {
  const [head, ...lines] = text.trim().split(String.fromCharCode(10)).map((l) => l.replace(String.fromCharCode(13), ''));
  const cols = head.split(',');
  return lines.map((line, i) => {
    const cells = line.split(',');
    if (cells.length !== cols.length) {
      throw new Error(`open-data CSV row ${i + 2} has ${cells.length} fields, the header has ${cols.length}`);
    }
    return Object.fromEntries(cols.map((c, j) => [c, cells[j]]));
  });
}

/** Where a council area sits among every UK council area in the open-data CSV, highest first. */
function nationalContext(csvText, district) {
  const all = parseCsv(csvText);
  const hit = all.find((r) => norm(r.borough) === norm(district));
  if (!hit) return null;
  const rank = (field) => {
    const have = all.filter((r) => r[field] !== '' && Number.isFinite(Number(r[field])));
    have.sort((a, b) => Number(b[field]) - Number(a[field]));
    const i = have.indexOf(hit);
    return i < 0 ? null : { value: Number(hit[field]), rank: i + 1, of: have.length };
  };
  return {
    name: hit.borough,
    air: rank('air_quality_who_ratio'),
    road: rank('road_noise_above_who_pct'),
    flood: rank('flood_medium_or_high_pct'),
  };
}

/** What the published runway data says about one point. Geometry, not a noise level. */
function aircraftFacts(proc, lat, lon) {
  const r = routesNear(proc, plane(lat, lon), AIRCRAFT.scopeKm);
  const under = r.finals.filter((f) => f.beside && f.dist <= AIRCRAFT.underKm).sort((a, b) => a.dist - b.dist)[0];
  return { near: r.scope[0] || null, under: under || null };
}

function page(spec, rows, ctx, vintage, nat, air) {
  const withNo2 = rows.filter((r) => typeof r.no2 === 'number');
  const med = withNo2.map((r) => r.no2).sort((a, b) => a - b)[Math.floor((withNo2.length - 1) / 2)];
  const tiles = [];
  if (typeof med === 'number') {
    tiles.push([
      `${(med / WHO.no2).toFixed(1)}&times;`,
      `NO&#8322; background level against the WHO guideline (${fmt(med)} vs ${WHO.no2} &micro;g/m&sup3;)`,
    ]);
  }
  if (ctx && ctx.no2.of > 1) {
    tiles.push([
      ord(ctx.no2.rank),
      `highest nitrogen dioxide of ${esc(CITY_LABEL[ctx.city])}: ${esc(ctx.name)} (${fmt(ctx.rec.no2AnnualMeanUgm3)} &micro;g/m&sup3;)`,
    ]);
  }
  if (ctx && typeof ctx.rec.roadNoiseAboveWhoPct === 'number') {
    tiles.push([`${Math.round(ctx.rec.roadNoiseAboveWhoPct)}%`, `of ${esc(ctx.name)}'s postcodes are above the WHO road-noise guideline`]);
  }
  if (nat && nat.air) {
    tiles.push([
      ord(nat.air.rank),
      `highest air pollution of the ${nat.air.of} UK council areas compared: ${esc(nat.name)} (${nat.air.value.toFixed(2)} times the WHO guideline on its worst pollutant)`,
    ]);
  }
  if (nat && nat.road) {
    tiles.push([
      `${Math.round(nat.road.value)}%`,
      `of ${esc(nat.name)}'s postcodes are above the WHO road-noise guideline (${ord(nat.road.rank)} highest of ${nat.road.of})`,
    ]);
  }

  const over = (v, g) => (typeof v === 'number' && v > g ? ' over' : '');
  // Aircraft columns exist only with --aircraft, and the decibel column only
  // where DEFRA measured at least one of the points: a column of "not mapped"
  // from top to bottom is said once, in a sentence, instead.
  const anyDb = Boolean(air) && rows.some((r) => typeof r.aircraftDb === 'number');
  const airCells = (r) =>
    !air
      ? ''
      : `<td class="num">${r.air.near ? `${fmt(r.air.near.dist)} km ${compass(r.air.near.q)}` : `none within ${AIRCRAFT.scopeKm} km`}</td>` +
        (anyDb ? `<td class="num${over(r.aircraftDb, WHO.aircraft)}">${typeof r.aircraftDb === 'number' ? fmt(r.aircraftDb) : 'not mapped'}</td>` : '');
  const airHead = !air ? '' : `<th class="num">Nearest runway</th>${anyDb ? '<th class="num">Aircraft noise (dB Lden)</th>' : ''}`;
  const airGuide = !air ? '' : `<th></th>${anyDb ? `<th class="num">${WHO.aircraft}</th>` : ''}`;
  const road = (r) => (typeof r.road === 'number' ? fmt(r.road) : typeof r.roadBelow === 'number' ? `&lt; ${r.roadBelow}` : 'n/a');
  const table = rows
    .map(
      (r) =>
        `<tr><td>${esc(r.label)}</td><td>${esc(r.postcode)}</td><td class="num${over(r.no2, WHO.no2)}">${typeof r.no2 === 'number' ? fmt(r.no2) : 'n/a'}</td>` +
        `<td class="num${over(r.pm25, WHO.pm25)}">${typeof r.pm25 === 'number' ? fmt(r.pm25) : 'n/a'}</td><td class="num${over(r.road, WHO.road)}">${road(r)}</td>${airCells(r)}</tr>`,
    )
    .join('\n');

  const bullets = [];
  const both = rows.filter((r) => r.no2 > WHO.no2 && r.pm25 > WHO.pm25).length;
  if (rows.length && both === rows.length) {
    bullets.push('<strong>Every point sampled is above the WHO guidelines for both NO&#8322; and PM2.5.</strong>');
  } else if (withNo2.length) {
    // Say which pollutant, not only how many points fail both: outside the big
    // cities PM2.5 is over its guideline everywhere while NO2 sits close to its
    // own, and "3 of 8 for both" hides exactly that.
    // Each pollutant is counted over the points that HOLD a reading for it: a
    // point with no reading is not a point below the guideline.
    const of = (k, n) => (k === n ? (n === rows.length ? 'every point' : `all ${n} points with a reading`) : `${k} of ${n} points`);
    const withPm = rows.filter((r) => typeof r.pm25 === 'number');
    const pmOver = withPm.filter((r) => r.pm25 > WHO.pm25);
    const no2Over = withNo2.filter((r) => r.no2 > WHO.no2).length;
    const pms = pmOver.map((r) => r.pm25);
    const span = pms.length ? ` (${fmt(Math.min(...pms))} to ${fmt(Math.max(...pms))} against a guideline of ${WHO.pm25})` : '';
    bullets.push(
      `<strong>Fine particles (PM2.5) are above the WHO guideline at ${of(pmOver.length, withPm.length)} sampled</strong>${span}. Nitrogen dioxide is above its guideline at ${of(no2Over, withNo2.length)}.`,
    );
  }
  const roads = rows.filter((r) => typeof r.road === 'number').sort((a, b) => b.road - a.road);
  if (roads.length >= 2 && roads[0].road - roads[roads.length - 1].road >= 5) {
    const [hi, lo] = [roads[0], roads[roads.length - 1]];
    bullets.push(
      `<strong>Road noise varies street by street far more than air does.</strong> ${esc(hi.label)} reaches ${Math.round(hi.road)} dB Lden; ${esc(lo.label)} is ${Math.round(lo.road)}.`,
    );
  }
  if (ctx && ctx.no2.of > 1) {
    const above = ctx.no2.above.length ? ` (after ${ctx.no2.above.slice(0, 4).map(esc).join(', ')}${ctx.no2.above.length > 4 ? ' and others' : ''})` : '';
    const pm = ctx.pm25.of > 1 ? `, and the ${ord(ctx.pm25.rank)}-highest fine particles` : '';
    bullets.push(`${esc(ctx.name)} has the <strong>${ord(ctx.no2.rank)}-highest nitrogen dioxide</strong> of ${esc(CITY_LABEL[ctx.city])}${above}${pm}.`);
  }

  if (nat && nat.air) {
    const road = nat.road ? `, and ${ord(nat.road.rank)} of ${nat.road.of} for the share of postcodes above the road-noise guideline` : '';
    const flood = nat.flood ? ` ${nat.flood.value}% of its postcodes are at medium or high flood risk.` : '';
    bullets.push(
      `Across the council as a whole, ${esc(nat.name)} ranks <strong>${ord(nat.air.rank)} of ${nat.air.of}</strong> UK council areas for air pollution against WHO guidelines, highest first${road}.${flood}`,
    );
  }

  const located = air ? rows.filter((r) => r.air.near) : [];
  if (located.length) {
    const byDist = [...located].sort((a, b) => a.air.near.dist - b.air.near.dist);
    const [first, last] = [byDist[0], byDist[byDist.length - 1]];
    const airport = AIRPORT_NAME[first.air.near.code] || first.air.near.code;
    const span =
      byDist.length > 1 && last.air.near.dist - first.air.near.dist >= 0.1
        ? `${fmt(first.air.near.dist)} to ${fmt(last.air.near.dist)} km from the points sampled; the nearest is ${esc(first.label)}`
        : `${fmt(first.air.near.dist)} km from ${byDist.length > 1 ? 'the points sampled' : esc(first.label)}`;
    const under = rows.filter((r) => r.air.under);
    const ft = (u) => `${(Math.round(u.heightFt / 100) * 100).toLocaleString('en-GB')} ft`;
    const underText = under.length
      ? under
          .slice(0, 2)
          .map((r) => `${esc(r.label)} is ${fmt(r.air.under.dist)} km from the approach line to runway ${esc(r.air.under.rwy)}, where landing aircraft are at about ${ft(r.air.under)}`)
          .join('; ') + '.'
      : `None of them is within ${AIRCRAFT.underKm} km of a published approach line.`;
    const unmeasured = anyDb
      ? ''
      : air.unmapped.includes(first.air.near.code)
        ? ` The government's noise mapping does not cover ${esc(airport)} Airport, so there is no official aircraft noise figure for anywhere in this area.`
        : ` These points lie outside the aircraft noise contours the government publishes for ${esc(airport)} Airport, so no measured aircraft level exists for them.`;
    bullets.push(`<strong>${esc(airport)} Airport's runway is ${span}.</strong> ${underText}${unmeasured}`);
  }

  return `<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8"><title>${esc(spec.area)}: air and noise</title>
<style>
  @font-face { font-family: 'Geist'; src: url('${pathToFileURL(resolve('fonts/geist.woff2')).href}') format('woff2'); font-weight: 100 900; }
  @page { size: A4; margin: 14mm 15mm 12mm; }
  :root { --ink:#1c1c1a; --muted:#5f5e59; --rule:#dedcd6; --band:#f4f2ee; --accent:#b4441a; }
  body { font-family: 'Geist', system-ui, sans-serif; color: var(--ink); background:#fff; font-size: 10pt; line-height: 1.45; margin: 0; }
  h1 { font-size: 19pt; line-height: 1.15; margin: 0 0 4px; }
  .sub { color: var(--muted); margin: 0 0 14px; }
  h2 { font-size: 11pt; margin: 16px 0 6px; }
  .keys { display: grid; grid-template-columns: repeat(${Math.max(tiles.length, 1)}, 1fr); gap: 8px; margin: 10px 0 4px; }
  .key { background: var(--band); border-radius: 6px; padding: 10px 12px; }
  .key .n { font-size: 20pt; font-weight: 700; line-height: 1; }
  .key .l { font-size: 8.5pt; color: var(--muted); margin-top: 4px; }
  table { width: 100%; border-collapse: collapse; font-size: 9pt; }
  th, td { text-align: left; padding: 4px 6px; border-bottom: 1px solid var(--rule); }
  th { font-weight: 600; color: var(--muted); font-size: 8.5pt; }
  .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .over { color: var(--accent); font-weight: 600; }
  ul { margin: 4px 0 0; padding-left: 18px; } li { margin: 2px 0; }
  .note { font-size: 8.5pt; color: var(--muted); }
  footer { margin-top: 10px; padding-top: 6px; border-top: 1px solid var(--rule); font-size: 8pt; color: var(--muted); }
</style></head><body>
<h1>${esc(spec.area)}: air quality and noise from official data</h1>
<p class="sub">Official figures from DEFRA's published pollution and noise maps, compared with World Health Organization guidelines.</p>
<div class="keys">${tiles.map(([n, l]) => `<div class="key"><div class="n">${n}</div><div class="l">${l}</div></div>`).join('')}</div>
<h2>${air ? 'Air quality, road noise and the airport' : 'Air quality and road noise'} across ${esc(spec.area)}</h2>
<table><thead><tr><th>Location</th><th>Postcode</th><th class="num">NO&#8322; (&micro;g/m&sup3;)</th><th class="num">PM2.5 (&micro;g/m&sup3;)</th><th class="num">Road noise (dB Lden)</th>${airHead}</tr></thead>
<tbody>${table}
<tr><th colspan="2">WHO guideline</th><th class="num">${WHO.no2}</th><th class="num">${WHO.pm25}</th><th class="num">${WHO.road}</th>${airGuide}</tr></tbody></table>
<p class="note">Figures in orange exceed the WHO guideline. The UK legal limit for NO&#8322; is 40 &micro;g/m&sup3;, so levels below it are within the law even where they are above what the WHO recommends for health.</p>
${bullets.length ? `<h2>What this shows</h2><ul>${bullets.map((b) => `<li>${b}</li>`).join('')}</ul>` : ''}
<p class="note" style="margin-top:12px"><strong>Note:</strong> DEFRA's air figures are modelled background levels on a 1&nbsp;km grid (${esc(vintage.air)} annual means), so they understate pollution at the kerb of main roads, where roadside monitors and sensors take direct measurements. The noise maps model 2021 traffic, reduced by lockdown.${air ? ' Runway distances are measured to the runway itself, from its published position: they are distances, not noise levels. Helicopters, military flights and smaller airfields are not covered.' : ''}</p>
<footer>Sources: DEFRA background pollution maps (PCM), ${esc(vintage.air)} annual mean, 1 km grid; DEFRA Strategic Noise Mapping Round 4 (road, Lden, 2021 traffic); WHO Global Air Quality Guidelines (2021) and Environmental Noise Guidelines for the European Region (2018). All Open Government Licence v3.0 except the WHO guidelines.${air ? ` Runway and approach positions from the UK Aeronautical Information Publication (NATS), AIRAC ${esc(air.airac)}.` : ''}${ctx ? ` Borough comparison across ${esc(CITY_LABEL[ctx.city])}.` : ''}${nat && nat.air ? ` Council-area comparison across the ${nat.air.of} UK council areas in Sky Score's open data (skyscore.co.uk/open-data).` : ''} Compiled with Sky Score (skyscore.co.uk), which joins these public datasets; free to reuse and cite. Prepared ${new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })}.</footer>
</body></html>`;
}

const spec = args(process.argv);
const looked = await lookupPostcodes(spec.points.map((p) => p.postcode));
const rows = [];
let vintage = { air: 'recent' };
// --aircraft: the flight-procedure record, and which airports DEFRA does not map at all.
const proc = spec.aircraft ? JSON.parse(await readFile(resolve('data/flight-procedures.json'), 'utf8')) : null;
const footprint = spec.aircraft ? JSON.parse(await readFile(resolve('data/aircraft-footprint.json'), 'utf8')) : null;
const air = spec.aircraft
  ? { airac: proc.airac, unmapped: Object.values(footprint.unmapped || {}).map((u) => u.code).filter(Boolean) }
  : null;
for (const [i, p] of spec.points.entries()) {
  const loc = looked[i];
  if (!loc) {
    console.error(`skipping ${p.postcode}: postcodes.io does not know it`);
    continue;
  }
  const env = await environment(loc.latitude, loc.longitude);
  const e = env.environment || {};
  const m = /annual mean (\d{4})/.exec(e.airQualitySource || '');
  if (m) vintage = { air: m[1] };
  rows.push({
    label: p.label,
    postcode: loc.postcode,
    district: loc.admin_district,
    no2: e.no2AnnualMeanUgm3,
    pm25: e.pm25AnnualMeanUgm3,
    road: e.roadNoiseLdenDb,
    roadBelow: e.roadNoiseBelowDb,
    aircraftDb: e.aircraftNoiseLdenDb,
    air: proc ? aircraftFacts(proc, loc.latitude, loc.longitude) : null,
  });
  await sleep(400); // stay well under the route's 5 RPS
}
if (!rows.length) throw new Error('no point resolved - nothing to publish');

const extra = JSON.parse(await readFile(resolve('data/borough-extra.json'), 'utf8'));
const ctx = boroughContext(extra, rows[0].district);
// Not on the map (an API-only city): compare against every UK council area in the open-data file.
const nat = ctx ? null : nationalContext(await readFile(resolve('open-data/sky-score-boroughs.csv'), 'utf8'), rows[0].district);
if (!ctx && !nat) console.error(`no comparison: ${rows[0].district} is in neither borough-extra.json nor the open-data CSV`);

const html = page(spec, rows, ctx, vintage, nat, air);
if (/\u2014/.test(html)) throw new Error('em dash in output');
const htmlPath = spec.out.replace(/\.pdf$/i, '.html');
await writeFile(htmlPath, html, 'utf8');

const browser = await chromium.launch();
try {
  const pg = await browser.newPage();
  await pg.goto(pathToFileURL(htmlPath).href, { waitUntil: 'load' });
  const tmp = spec.out.replace(/\.pdf$/i, '.NEW.pdf');
  const pdf = await pg.pdf({ path: tmp, format: 'A4', printBackground: true, preferCSSPageSize: true, tagged: true });
  // It is handed over as ONE page. Count the page objects rather than trusting the layout.
  const pages = (pdf.toString('latin1').match(/\/Type\s*\/Page[^s]/g) || []).length;
  if (pages !== 1) {
    console.error(`the sheet ran to ${pages} pages, not 1 - use fewer points or shorter labels`);
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
console.log(`${rows.length} points, borough ${ctx ? `${ctx.name} (${ctx.city})` : nat ? `${nat.name} (national comparison)` : 'none'}, air vintage ${vintage.air}\n  ${spec.out}`);
