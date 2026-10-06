/**
 * /reports/street/: a visitor's own aircraft-noise report, made in the browser.
 *
 * The browser half of scripts/address_noise_report.mjs. The page, map and chart
 * are js/street_report.mjs, shared with that script; this file only fetches the
 * inputs from this site and the two public services, then draws the report into
 * an iframe that prints on its own. Every input is one the live site already
 * serves; nothing here needs a key or spends anyone's quota.
 */
import { plane, routesNear } from '/js/flight_geometry.mjs';
import {
  DEFRA_LDEN_SCALE,
  SCOPE_KM,
  districtComparison,
  mapSvg,
  rasterFor,
  reportDocument,
} from '/js/street_report.mjs';

const byId = (id) => document.getElementById(id);
const form = byId('make');
const input = byId('pc');
const go = byId('go');
const status = byId('status');
const result = byId('result');
const sheet = byId('sheet');

// js/api-base.js is the one holder of the API host.
const ENV = `${window.API_BASE || 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod'}/v1/environment`;
// A UK postcode's shape (outward code, optional space, inward code). Stricter than
// the score Lambda's [A-Z0-9]{1,8}, which only keeps a URL path safe: a visitor's
// typing that cannot be a postcode is answered here, without a network request.
const POSTCODE = /^[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}$/;

const say = (html) => {
  status.innerHTML = html;
};
const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

async function getJson(url, what) {
  let r;
  try {
    r = await fetch(url);
  } catch {
    throw new Error(`${what} could not be reached. Check your connection and try again.`);
  }
  if (!r.ok) throw new Error(`${what} answered ${r.status}. Try again in a minute.`);
  return r.json();
}
// A file this site may not hold for every city (outlines): absent is not an error.
async function maybeJson(url) {
  try {
    const r = await fetch(url);
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
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
    if (!r.ok) throw new Error(`postcodes.io answered ${r.status}`);
    for (const row of (await r.json()).result) if (row.result) live.add(row.query);
  }
  return live;
}

async function make(raw) {
  const postcode = raw.trim().toUpperCase().replace(/\s+/g, ' ');
  if (!POSTCODE.test(postcode)) {
    say('That does not look like a UK postcode. Try one such as TW9 3PZ.');
    return;
  }
  go.disabled = true;
  result.classList.remove('is-open');
  say(`Making the report for ${esc(postcode)}...`);
  try {
    const lookup = await fetch(`https://api.postcodes.io/postcodes/${encodeURIComponent(postcode)}`).catch(() => null);
    if (!lookup) throw new Error('postcodes.io could not be reached. Check your connection and try again.');
    if (lookup.status === 404) {
      say(`${esc(postcode)} is not a postcode the national register knows. Check it and try again.`);
      return;
    }
    if (!lookup.ok) throw new Error(`postcodes.io answered ${lookup.status}. Try again in a minute.`);
    const loc = (await lookup.json()).result;

    const envBody = await getJson(`${ENV}?lat=${loc.latitude}&lon=${loc.longitude}`, 'Our noise service');
    const env = envBody.environment || {};
    // Outside every city covered, the endpoint's quiet figure is worked out from
    // nothing nearby. Say so and stop, as the front page and the map do.
    if (env.aircraftQuietCoverage === 'outside') {
      say(
        `${esc(loc.postcode)}${loc.admin_district ? ` (${esc(loc.admin_district)})` : ''} is outside the city regions Sky Score covers, so there is no report for it yet. <a href="/area/">See the areas we cover</a>.`
      );
      return;
    }
    const resolvedAs = envBody.location && envBody.location.postcode !== loc.postcode ? envBody.location.postcode : null;

    const [proc, regions, covid] = await Promise.all([
      getJson('/data/flight-procedures.json', 'The route file'),
      getJson('/data/aircraft-noise-rasters.json', 'The noise map index'),
      getJson('/data/covid-understatement.json', 'The 2021 comparison'),
    ]);
    const pl = plane(loc.latitude, loc.longitude);
    const routes = routesNear(proc, pl, SCOPE_KM);
    const raster = rasterFor(regions, loc.latitude, loc.longitude);
    // The outlines of the raster's city and of every city the nearest airport
    // serves, as the PDF script draws them.
    const home = routes.airports[0];
    const outlineCities = new Set([
      ...(raster ? [raster.city] : []),
      ...(home && home.dist <= SCOPE_KM ? proc.airports[home.code].cities : []),
    ]);
    const boroughs = { features: [] };
    for (const outline of await Promise.all([...outlineCities].map((c) => maybeJson(`/data/${c}-boroughs.json`)))) {
      if (outline) boroughs.features.push(...outline.features);
    }
    // The district chart compares MEASURED postcodes, so it is fetched only for one.
    let district = null;
    if (typeof env.aircraftQuiet === 'number') {
      say(`Comparing ${esc(loc.postcode)} with the rest of ${esc(loc.outcode)}...`);
      const [london, rest] = await Promise.all([
        getJson('/data/aircraft-quiet-london.json', 'The London noise readings'),
        getJson('/data/aircraft-quiet-regions.json', 'The regional noise readings'),
      ]);
      try {
        district = await districtComparison({ ...london.quiet, ...rest.quiet }, loc.outcode, env.aircraftQuiet, livePostcodes);
      } catch {
        district = null; // the chart is a comparison, not a fact the report needs
      }
    }

    const html = reportDocument(
      { postcode: loc.postcode },
      {
        postcode: loc.postcode,
        council: loc.admin_district,
        hasRaster: Boolean(raster),
        resolvedAs,
        notices: envBody.notices,
        env,
        routes,
        district,
        covid,
        airac: proc.airac,
        map: mapSvg({
          pl,
          routes,
          raster,
          boroughs,
          scale: DEFRA_LDEN_SCALE,
          label: loc.postcode,
          imageHref: (png) => `/${png}`,
        }),
      },
      '/fonts/geist.woff2'
    );
    sheet.srcdoc = html;
    await new Promise((resolve) => sheet.addEventListener('load', resolve, { once: true }));
    const doc = sheet.contentDocument;
    if (doc) {
      // The report's margins are the A4 page's (@page), which a screen does not
      // draw. Added here, screen only, so the page the PDF script prints is
      // untouched (its HTML is held byte-identical to the module's).
      const pad = doc.createElement('style');
      pad.textContent = '@media screen { body { padding: 13mm 15mm; } }';
      doc.head.append(pad);
      // As tall as the report, so the page scrolls rather than the frame.
      sheet.style.height = `${Math.max(1123, doc.documentElement.scrollHeight + 8)}px`;
    }
    result.classList.add('is-open');
    say(`Your report for ${esc(loc.postcode)} is ready below.`);
    window.goatcounter?.count?.({ path: 'event/street-report-made', title: 'street-report-made', event: true });
  } catch (e) {
    say(esc(e.message || 'Something went wrong making the report. Try again.'));
  } finally {
    go.disabled = false;
  }
}

form.addEventListener('submit', (e) => {
  e.preventDefault();
  make(input.value);
});
byId('print').addEventListener('click', () => {
  sheet.contentWindow?.focus();
  sheet.contentWindow?.print();
});
// ?postcode= from a link (the front page's answer, a shared URL) makes the report at once.
const given = new URLSearchParams(location.search).get('postcode');
if (given) {
  input.value = given;
  make(given);
}
