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
 *   - the data year: parsed from the API's own source line, so the page
 *     re-dates itself when the air-quality vintage rolls.
 * Postcodes resolve through postcodes.io, as the site's search does.
 *
 * Only publishes what is measured: a point with no reading says so, a city
 * with one borough gets no rank, and the limits note is always printed.
 * No em dashes in the output, matching the site's rule.
 */
import { chromium } from '@playwright/test';
import { readFile, rename, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const API = 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/environment';
const WHO = { no2: 10, pm25: 5, road: 53 };
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
    else if (k === '--out') (out.out = v), i++;
    else if (k === '--point') {
      const eq = v.lastIndexOf('=');
      if (eq < 1) throw new Error(`--point must be "Label=POSTCODE", got "${v}"`);
      out.points.push({ label: v.slice(0, eq).trim(), postcode: v.slice(eq + 1).trim().toUpperCase() });
      i++;
    } else throw new Error(`unknown argument ${k}`);
  }
  if (!out.area || !out.points.length) {
    throw new Error('usage: --area "Name" --point "Label=POSTCODE" [--point ...] [--out file.pdf]');
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

function page(spec, rows, ctx, vintage) {
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

  const over = (v, g) => (typeof v === 'number' && v > g ? ' over' : '');
  const road = (r) => (typeof r.road === 'number' ? fmt(r.road) : typeof r.roadBelow === 'number' ? `&lt; ${r.roadBelow}` : 'n/a');
  const table = rows
    .map(
      (r) =>
        `<tr><td>${esc(r.label)}</td><td>${esc(r.postcode)}</td><td class="num${over(r.no2, WHO.no2)}">${typeof r.no2 === 'number' ? fmt(r.no2) : 'n/a'}</td>` +
        `<td class="num${over(r.pm25, WHO.pm25)}">${typeof r.pm25 === 'number' ? fmt(r.pm25) : 'n/a'}</td><td class="num${over(r.road, WHO.road)}">${road(r)}</td></tr>`,
    )
    .join('\n');

  const bullets = [];
  const both = rows.filter((r) => r.no2 > WHO.no2 && r.pm25 > WHO.pm25).length;
  if (rows.length && both === rows.length) {
    bullets.push('<strong>Every point sampled is above the WHO guidelines for both NO&#8322; and PM2.5.</strong>');
  } else if (withNo2.length) {
    bullets.push(`${both} of ${rows.length} points sampled are above the WHO guidelines for both NO&#8322; and PM2.5.`);
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

  return `<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8"><title>${esc(spec.area)}: air and noise</title>
<style>
  @font-face { font-family: 'Geist'; src: url('${pathToFileURL(resolve('fonts/geist.woff2')).href}') format('woff2'); font-weight: 100 900; }
  @page { size: A4; margin: 16mm 16mm 14mm; }
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
  th, td { text-align: left; padding: 5px 6px; border-bottom: 1px solid var(--rule); }
  th { font-weight: 600; color: var(--muted); font-size: 8.5pt; }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .over { color: var(--accent); font-weight: 600; }
  ul { margin: 4px 0 0; padding-left: 18px; } li { margin: 2px 0; }
  .note { font-size: 8.5pt; color: var(--muted); }
  footer { margin-top: 14px; padding-top: 8px; border-top: 1px solid var(--rule); font-size: 8pt; color: var(--muted); }
</style></head><body>
<h1>${esc(spec.area)}: air quality and noise from official data</h1>
<p class="sub">Official figures from DEFRA's published pollution and noise maps, compared with World Health Organization guidelines.</p>
<div class="keys">${tiles.map(([n, l]) => `<div class="key"><div class="n">${n}</div><div class="l">${l}</div></div>`).join('')}</div>
<h2>Air quality and road noise across ${esc(spec.area)}</h2>
<table><thead><tr><th>Location</th><th>Postcode</th><th class="num">NO&#8322; (&micro;g/m&sup3;)</th><th class="num">PM2.5 (&micro;g/m&sup3;)</th><th class="num">Road noise (dB Lden)</th></tr></thead>
<tbody>${table}
<tr><th colspan="2">WHO guideline</th><th class="num">${WHO.no2}</th><th class="num">${WHO.pm25}</th><th class="num">${WHO.road}</th></tr></tbody></table>
<p class="note">Figures in orange exceed the WHO guideline. The UK legal limit for NO&#8322; is 40 &micro;g/m&sup3;, so levels below it are within the law even where they are above what the WHO recommends for health.</p>
${bullets.length ? `<h2>What this shows</h2><ul>${bullets.map((b) => `<li>${b}</li>`).join('')}</ul>` : ''}
<p class="note" style="margin-top:12px"><strong>Note:</strong> DEFRA's air figures are modelled background levels on a 1&nbsp;km grid (${esc(vintage.air)} annual means), so they understate pollution at the kerb of main roads, where roadside monitors and sensors take direct measurements. The noise maps model 2021 traffic, reduced by lockdown.</p>
<footer>Sources: DEFRA background pollution maps (PCM), ${esc(vintage.air)} annual mean, 1 km grid; DEFRA Strategic Noise Mapping Round 4 (road, Lden, 2021 traffic); WHO Global Air Quality Guidelines (2021) and Environmental Noise Guidelines for the European Region (2018). All Open Government Licence v3.0 except the WHO guidelines.${ctx ? ` Borough comparison across ${esc(CITY_LABEL[ctx.city])}.` : ''} Compiled with Sky Score (skyscore.co.uk), which joins these public datasets; free to reuse and cite. Prepared ${new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })}.</footer>
</body></html>`;
}

const spec = args(process.argv);
const looked = await lookupPostcodes(spec.points.map((p) => p.postcode));
const rows = [];
let vintage = { air: 'recent' };
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
  });
  await sleep(400); // stay well under the route's 5 RPS
}
if (!rows.length) throw new Error('no point resolved - nothing to publish');

const extra = JSON.parse(await readFile(resolve('data/borough-extra.json'), 'utf8'));
const ctx = boroughContext(extra, rows[0].district);
if (!ctx) console.error(`no borough comparison: ${rows[0].district} is not on the map`);

const html = page(spec, rows, ctx, vintage);
if (/\u2014/.test(html)) throw new Error('em dash in output');
const htmlPath = spec.out.replace(/\.pdf$/i, '.html');
await writeFile(htmlPath, html, 'utf8');

const browser = await chromium.launch();
try {
  const pg = await browser.newPage();
  await pg.goto(pathToFileURL(htmlPath).href, { waitUntil: 'load' });
  const tmp = spec.out.replace(/\.pdf$/i, '.NEW.pdf');
  await pg.pdf({ path: tmp, format: 'A4', printBackground: true, preferCSSPageSize: true, tagged: true });
  try {
    await rename(tmp, spec.out);
  } catch (e) {
    console.error(`Could not replace ${spec.out} - close it in any PDF viewer and re-run. (${e.code})`);
    process.exitCode = 1;
  }
} finally {
  await browser.close();
}
console.log(`${rows.length} points, borough ${ctx ? `${ctx.name} (${ctx.city})` : 'none'}, air vintage ${vintage.air}\n  ${spec.out}`);
