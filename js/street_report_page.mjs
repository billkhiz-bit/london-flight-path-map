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
// MIT, Kazuhiko Arase; vendored unmodified, version in the name (LICENSING.md, code shipped to browsers).
import qrcode from '/js/vendor/qrcode-generator-2.0.4.mjs';

const byId = (id) => document.getElementById(id);
const form = byId('make');
const input = byId('pc');
const go = byId('go');
const status = byId('status');
const checkResult = byId('check-result');
const result = byId('result');
const sheet = byId('sheet');

// ---- A free copy can be screenshotted and edited (Bill, 2026-10-06), so it says what it is ----
// Every free copy carries a watermark, a reference and a link (with a QR code) that reopens the
// genuine figures. The reference is a hash of the figures the copy states, the postcode and the day
// it was made, so anyone handed a screenshot can check it in seconds. Nothing is stored: the check
// re-makes the report from today's official data and recomputes the hash with the original date.
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
const MADE = /^\d{4}-\d{2}-\d{2}$/;
const REF = /^[A-HJ-NP-Z2-9]{4}-?[A-HJ-NP-Z2-9]{4}$/;

/** The reference for a copy: 8 characters of a SHA-256 over what the copy states. */
export async function reportReference(postcode, made, airac, env) {
  const text = JSON.stringify([postcode, made, airac ?? null, ...STATED.map((k) => (typeof env[k] === 'number' ? env[k] : null))]);
  const d = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)));
  let out = '';
  for (let i = 0; i < 8; i++) out += REF_ALPHABET[d[i] & 31];
  return `${out.slice(0, 4)}-${out.slice(4)}`;
}
const checkLink = (postcode, made, ref) =>
  `${SITE}/reports/street/?postcode=${encodeURIComponent(postcode)}&made=${made}&ref=${ref.replace('-', '')}`;
const longDate = (iso) =>
  new Date(`${iso}T12:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });

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

async function make(raw, check = null) {
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
    // The day this copy is made, and the reference that ties its figures to that day.
    const made = new Date().toISOString().slice(0, 10);
    const ref = await reportReference(loc.postcode, made, proc.airac, env);
    const link = checkLink(loc.postcode, made, ref);

    sheet.srcdoc = html;
    await new Promise((resolve) => sheet.addEventListener('load', resolve, { once: true }));
    const doc = sheet.contentDocument;
    if (doc) {
      // Everything below is added to the FREE copy only, never to the shared module, so the
      // PDF script's output (the paid product for firms) stays byte-identical and clean.
      const pad = doc.createElement('style');
      pad.textContent =
        // The report's margins are the A4 page's (@page), which a screen does not draw.
        '@media screen { body { padding: 13mm 15mm; position: relative; } }' +
        // On screen only: printing the frame itself (the browser's route to "Save as PDF")
        // gets the firms note, not the report.
        '@media print { body > * { display: none !important; } body::before { content: "A printed or PDF copy of a report is part of the service for firms: skyscore.co.uk/pricing"; font: 14pt system-ui, sans-serif; } }' +
        // The watermark: faint enough to read through, there on every screenshot.
        '.free-copy-mark { position: absolute; inset: 0; overflow: hidden; pointer-events: none; z-index: 5; display: flex; flex-wrap: wrap; align-content: flex-start; gap: 110px 70px; padding: 60px 20px; }' +
        '.free-copy-mark span { transform: rotate(-28deg); font: 600 15px system-ui, sans-serif; color: rgba(20, 20, 20, 0.09); white-space: nowrap; }' +
        // The check block sits ABOVE the watermark on white, so faint text never crosses the QR code.
        '.free-copy-check { position: relative; z-index: 6; background: #fff; display: flex; gap: 14px; align-items: center; margin-top: 10px; padding-top: 10px; border-top: 1px solid #dedcd6; }' +
        '.free-copy-check svg { flex: 0 0 auto; width: 132px; height: 132px; }' +
        '.free-copy-check p { margin: 0; }';
      doc.head.append(pad);

      const mark = doc.createElement('div');
      mark.className = 'free-copy-mark';
      mark.setAttribute('aria-hidden', 'true');
      const line = `Personal use only · ${loc.postcode} · ${longDate(made)}`;
      for (let i = 0; i < 60; i++) {
        const span = doc.createElement('span');
        span.textContent = line;
        mark.append(span);
      }
      doc.body.append(mark);

      // The reference, the check link and its QR code, and the terms line. Bill, 2026-10-06:
      // "can't firms just pretend to be a resident?", then "people can screenshot and maybe
      // edit it". The terms (section 4) already limit free use to personal, non-commercial use.
      const qr = qrcode(0, 'M');
      qr.addData(link);
      qr.make();
      const block = doc.createElement('div');
      block.className = 'free-copy-check';
      block.innerHTML =
        qr.createSvgTag({ cellSize: 4, margin: 16, scalable: true, alt: 'QR code to check this report' }) +
        `<p><strong>Reference ${esc(ref)}</strong>, made ${esc(longDate(made))}. To check a copy against the official figures, scan the code or open <a href="${esc(link)}">${esc(link.replace('https://', ''))}</a>.` +
        ' <strong>Free copy for personal use, not for use with clients</strong>, under our terms (section 4, skyscore.co.uk/terms). Reports for firms: skyscore.co.uk/pricing.</p>';
      (doc.querySelector('footer') || doc.body).append(block);
      // As tall as the report, so the page scrolls rather than the frame, and KEPT so: the web
      // fonts arrive after the first measure and make the text taller, which clipped the foot
      // of the report (found 2026-10-06, when the check block landed in the clipped strip).
      // Measured from the BODY, whose height does not depend on the frame's: measuring the
      // document element would grow with each fit and never settle.
      const fit = () => {
        const cs = doc.defaultView.getComputedStyle(doc.body);
        const tall = doc.body.getBoundingClientRect().height + parseFloat(cs.marginTop) + parseFloat(cs.marginBottom);
        sheet.style.height = `${Math.max(1123, Math.ceil(tall) + 8)}px`;
      };
      fit();
      new doc.defaultView.ResizeObserver(fit).observe(doc.body);
      doc.fonts?.ready.then(fit);
    }
    result.classList.add('is-open');
    // The check's verdict before "ready": whoever waits for ready sees the verdict with it.
    if (check) await showCheck(check, loc.postcode, proc.airac, env);
    say(`Your report for ${esc(loc.postcode)} is ready below.`);
    window.goatcounter?.count?.({ path: 'event/street-report-made', title: 'street-report-made', event: true });
  } catch (e) {
    say(esc(e.message || 'Something went wrong making the report. Try again.'));
  } finally {
    go.disabled = false;
  }
}

/**
 * Someone opened a check link from a copy they were shown: re-make the report from today's
 * official data and recompute the reference with the copy's own date. A match means the copy
 * states today's figures; a mismatch means the figures have moved since, or the copy was changed,
 * and the page says both, because it cannot tell which.
 */
async function showCheck(check, postcode, airac, env) {
  const expected = (await reportReference(postcode, check.made, airac, env)).replace('-', '');
  const shown = `${check.ref.slice(0, 4)}-${check.ref.slice(4)}`;
  const when = esc(longDate(check.made));
  const ok = expected === check.ref;
  checkResult.className = `check-result ${ok ? 'ok' : 'bad'}`;
  checkResult.innerHTML = ok
    ? `Reference ${esc(shown)} matches. A copy made for ${esc(postcode)} on ${when} with this reference states the same official figures as the report below.`
    : `Reference ${esc(shown)} does not match today's figures for ${esc(postcode)}. Either the official figures have been updated since ${when}, or the copy you were shown was changed. The report below is made from today's official data.`;
  checkResult.hidden = false;
}

form.addEventListener('submit', (e) => {
  e.preventDefault();
  checkResult.hidden = true;
  make(input.value);
});
// ?postcode= from a link (the front page's answer, a shared URL) makes the report at once, and
// &made=&ref= (the check link printed on every free copy) checks a copy against it. A malformed
// date or reference is ignored rather than trusted.
const params = new URLSearchParams(location.search);
const given = params.get('postcode');
if (given) {
  const made = params.get('made') || '';
  const ref = (params.get('ref') || '').toUpperCase().replace('-', '');
  const check = MADE.test(made) && REF.test(ref) ? { made, ref } : null;
  input.value = given;
  make(given, check);
}
