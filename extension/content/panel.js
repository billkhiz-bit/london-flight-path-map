/* global extractListing */
// cubitt33 extension — injected panel.
//
// Renders as a FLOATING CARD appended to document.body, deliberately not
// injected into Rightmove's own layout. Two reasons, and both matter:
//
//   1. Resilience. Injecting into their grid means depending on a container
//      class name, and Rightmove's class names are build-hashed — they change
//      without notice. A fixed-position card depends on nothing.
//   2. Posture. We are a guest on someone else's page. Overlaying our own
//      panel, without reflowing or hiding any of their content, is a far more
//      defensible position than restructuring it.
//
// It also does NOT fetch on page load. The user clicks the badge to ask for
// data, which means zero upstream traffic for anyone who ignores it — the
// politest possible relationship with both Rightmove and OSM's Overpass.

const PANEL_ID = 'cubitt33-panel';
const BADGE_ID = 'cubitt33-badge';

// --- Small DOM helpers ---------------------------------------------------
// Everything data-bearing is built with createElement + textContent, never
// innerHTML. This is not stylistic: /nhs proxies OpenStreetMap, which is
// CROWD-EDITED — a facility's `name` tag is arbitrary user-supplied text that
// has travelled through Overpass and our Lambda without ever being treated as
// markup. Interpolating it into innerHTML would be a stored-XSS sink with a
// public edit form at the far end of it.
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function metres(d) {
  if (d === null || d === undefined) return '';
  return d >= 1000 ? `${(d / 1000).toFixed(1)} km` : `${Math.round(d)} m`;
}

/**
 * Decide what the panel is allowed to show for a given extraction.
 *
 * This is the honesty gate. The Core Cities audit recorded the underlying
 * lesson the hard way: partial data presented as complete is worse than no
 * data, because a neutral-looking number reads as a measurement.
 *
 * Demo build collapses to three cases. When /v1/score, EPC and sold prices
 * arrive (all of which need lat/lon -> postcode reverse geocoding first) this
 * grows a 'partial' tier for borough-only resolution, and THAT is the tier
 * worth arguing about — a borough-average affordability score rendered against
 * a specific flat is precisely the failure above.
 *
 * TODO(bill): revisit when the reverse-geocode path lands. The open question is
 * whether a borough-level score should render greyed-out with a caveat, or not
 * render at all. I have defaulted to the conservative reading below.
 */
function decidePresentation(listing) {
  if (!listing) {
    // No coordinates means no data we can stand behind. Show nothing at all —
    // not an empty panel, not a "couldn't find anything" card. An empty panel
    // invites the reader to conclude the area has no GPs and no stations.
    return { show: 'nothing', sections: [], caveat: null };
  }

  if (!listing.inLondon) {
    // Outside London the environmental rasters thin out - DEFRA's aircraft
    // contours are English agglomerations and the road raster we hold is a
    // London bbox. Everything here still resolves via postcode, so the sections
    // stay; the caveat exists so a sparse answer is not read as a clean one.
    return {
      show: 'partial',
      sections: ['environment', 'epc', 'soldPrices', 'nhs'],
      caveat:
        'Aircraft and road noise coverage is strongest in London; figures outside it may be absent.',
    };
  }

  return { show: 'full', sections: ['environment', 'epc', 'soldPrices', 'nhs'], caveat: null };
}

// --- Section renderers ---------------------------------------------------

function renderNhs(result) {
  const section = el('section', 'c33-section');
  section.appendChild(el('h3', 'c33-h3', 'Healthcare'));

  if (!result.ok) {
    section.appendChild(el('p', 'c33-muted', `Healthcare data unavailable (${result.error}).`));
    return section;
  }

  const data = result.data;

  if (data.available === false) {
    section.appendChild(el('p', 'c33-muted', data.note || 'Live data unavailable.'));
  }

  const groups = [
    ['gp', 'Doctors & clinics'],
    ['pharmacies', 'Pharmacies'],
    ['hospitals', 'Hospitals'],
  ];

  let rendered = 0;
  for (const [key, label] of groups) {
    const items = data[key] || [];
    if (!items.length) continue;

    const group = el('div', 'c33-group');
    group.appendChild(el('h4', 'c33-h4', label));

    const list = el('ul', 'c33-list');
    for (const item of items.slice(0, 3)) {
      const li = el('li', 'c33-item');
      const row = el('div', 'c33-row');
      row.appendChild(el('span', 'c33-name', item.name));
      // A fallback row has distance null — it is a link to nhs.uk, not a
      // located facility, so showing "0 m" would be a lie.
      row.appendChild(el('span', 'c33-dist', item.fallback ? '' : metres(item.distance)));
      li.appendChild(row);
      list.appendChild(li);
    }
    group.appendChild(list);
    section.appendChild(group);
    rendered += 1;
  }

  if (rendered === 0) {
    section.appendChild(el('p', 'c33-muted', 'No healthcare facilities found nearby.'));
  }

  return section;
}

function renderEnvironment(result) {
  const section = el('section', 'c33-section');
  section.appendChild(el('h3', 'c33-h3', 'Environment'));

  if (!result.ok) {
    section.appendChild(el('p', 'c33-muted', `Environment data unavailable (${result.error}).`));
    return section;
  }

  const data = result.data;
  const env = data.environment || {};

  // Every row is present only when a real measurement exists — the endpoint
  // omits the key rather than sending null or a default. So an empty list here
  // means "nothing was measured for this postcode", which the notices explain,
  // and never "measured as fine".
  // Every environmental row now carries its WHO reference. A bare "69.6 dB
  // Lden" is uninterpretable — the guideline is what turns a number into
  // something a reader can act on, and it is cited rather than invented:
  // WHO Environmental Noise Guidelines for the European Region (2018) for the
  // two noise rows, WHO global air quality guidelines (2021) for the two
  // pollutant rows.
  //
  // The estimated aircraft row is the exception and deliberately carries none.
  // It is on a 0-10 quiet scale, not decibels, because it comes from
  // flight-path geometry rather than a reading — putting a dB guideline beside
  // it would imply a measurement that does not exist.
  const rows = [
    ['Aircraft noise', env.aircraftNoiseLdenDb, 'dB Lden', env.aircraftNoiseWhoGuidelineDb],
    ['Aircraft noise (estimated)', env.aircraftQuietEstimated, '/10 quiet', null],
    ['Road noise', env.roadNoiseLdenDb, 'dB Lden', env.roadNoiseWhoGuidelineDb],
    ['Nitrogen dioxide', env.no2AnnualMeanUgm3, 'ug/m3', env.no2WhoGuidelineUgm3],
    ['Fine particles (PM2.5)', env.pm25AnnualMeanUgm3, 'ug/m3', env.pm25WhoGuidelineUgm3],
  ].filter((r) => typeof r[1] === 'number');

  if (rows.length) {
    const list = el('ul', 'c33-list');
    for (const [label, value, unit, guideline] of rows) {
      const item = el('li', 'c33-item');
      const row = el('div', 'c33-row');
      row.appendChild(el('span', 'c33-name', label));

      const readout = el('span', 'c33-dist', `${value} ${unit}`);
      // Colour states a fact, not a verdict: whether the measurement is above
      // the cited guideline. No "good"/"bad" wording, because the guideline is
      // WHO's judgement and the comparison is arithmetic — anything richer
      // would be us editorialising over someone else's threshold.
      if (typeof guideline === 'number') {
        readout.className += value > guideline ? ' c33-over' : ' c33-under';
      }
      row.appendChild(readout);
      item.appendChild(row);

      if (typeof guideline === 'number') {
        const over = value > guideline;
        item.appendChild(
          el(
            'div',
            'c33-sub',
            over
              ? `above the WHO guideline of ${guideline} ${unit}`
              : `within the WHO guideline of ${guideline} ${unit}`
          )
        );
      }
      list.appendChild(item);
    }
    section.appendChild(list);
  }

  // Notices explain what was NOT measured. Rendered even when rows exist,
  // because a partial answer is the case most likely to be misread as complete.
  for (const notice of data.notices || []) {
    section.appendChild(el('div', 'c33-caveat', notice));
  }

  if (!rows.length && !(data.notices || []).length) {
    section.appendChild(el('p', 'c33-muted', 'No environmental measurements for this location.'));
  }

  return section;
}

function renderEpc(result) {
  const section = el('section', 'c33-section');
  section.appendChild(el('h3', 'c33-h3', 'EPC register'));

  if (!result.ok) {
    section.appendChild(el('p', 'c33-muted', `EPC data unavailable (${result.error}).`));
    return section;
  }

  const data = result.data;
  const certs = data.certificates || [];
  const summary = data.summary || {};

  if (!certs.length) {
    section.appendChild(el('p', 'c33-muted', 'No lodged certificates for this postcode.'));
    return section;
  }

  // The point is NOT "here is the EPC" — Rightmove already shows one, from
  // whatever the agent uploaded. The point is what the MHCLG register holds for
  // this postcode, and how this property's claim sits against its neighbours.
  // A listing claiming C on a postcode where seven of nine homes are D or E is
  // a question worth asking, and no listing page asks it for you.
  const dist = summary.bandDistribution || {};
  const bands = Object.entries(dist).filter(([, n]) => n > 0);
  if (bands.length) {
    section.appendChild(
      el('div', 'c33-sub', 'Postcode: ' + bands.map(([b, n]) => `${b}×${n}`).join('  '))
    );
  }
  if (summary.mostCommonBand && summary.mostCommonBand !== 'N/A') {
    section.appendChild(el('div', 'c33-sub', `Most common band here: ${summary.mostCommonBand}`));
  }

  const list = el('ul', 'c33-list');
  for (const cert of certs.slice(0, 4)) {
    const item = el('li', 'c33-item');
    const row = el('div', 'c33-row');
    row.appendChild(el('span', 'c33-name', cert.address || 'Address not given'));
    // EPC bands carry a colour scale everyone already recognises from the
    // certificate itself, so reusing it costs nothing and reads instantly.
    // Class per band rather than a computed colour: A-G is a fixed, official
    // seven-step scale, not something to interpolate.
    const band = (cert.band || '').toUpperCase();
    const badge = el('span', 'c33-dist c33-band', band || '?');
    if (/^[A-G]$/.test(band)) badge.className += ` c33-band-${band.toLowerCase()}`;
    row.appendChild(badge);
    item.appendChild(row);
    if (cert.date) item.appendChild(el('div', 'c33-sub', `lodged ${cert.date.slice(0, 10)}`));
    list.appendChild(item);
  }
  section.appendChild(list);
  return section;
}

function renderSoldPrices(result) {
  const section = el('section', 'c33-section');
  section.appendChild(el('h3', 'c33-h3', 'Sold nearby'));

  if (!result.ok) {
    section.appendChild(el('p', 'c33-muted', `Sold-price data unavailable (${result.error}).`));
    return section;
  }

  const tx = (result.data || {}).transactions || [];
  if (!tx.length) {
    section.appendChild(el('p', 'c33-muted', 'No Land Registry sales recorded for this postcode.'));
    return section;
  }

  // Rightmove HAS sold-price data, but as a separate search tool — not on the
  // listing you are looking at, beside the asking price. Putting the street's
  // actual transactions next to what is being asked for is the whole value.
  const list = el('ul', 'c33-list');
  for (const t of tx.slice(0, 4)) {
    const item = el('li', 'c33-item');
    const row = el('div', 'c33-row');
    const where = [t.address, t.street].filter(Boolean).join(' ') || 'Address not given';
    row.appendChild(el('span', 'c33-name', where));
    row.appendChild(
      el('span', 'c33-dist', t.price ? '£' + Number(t.price).toLocaleString('en-GB') : '')
    );
    item.appendChild(row);
    const meta = [t.date ? t.date.slice(0, 10) : '', t.type, t.newBuild ? 'new build' : '']
      .filter(Boolean)
      .join(' · ');
    if (meta) item.appendChild(el('div', 'c33-sub', meta));
    list.appendChild(item);
  }
  section.appendChild(list);
  return section;
}

// --- Attribution ---------------------------------------------------------
// Both upstreams carry licence obligations that follow the data into any
// surface that displays it — TfL Open Data requires credit, and OpenStreetMap
// is ODbL, which requires attribution on any Produced Work. The Lambdas already
// return the correct strings in `sources`; our only job is not to drop them.
function renderSources(payloads) {
  const seen = new Set();
  for (const p of payloads) {
    if (!p?.ok) continue;
    for (const s of p.data.sources || []) seen.add(s);
  }
  if (!seen.size) return null;

  const foot = el('footer', 'c33-foot');
  for (const s of seen) foot.appendChild(el('div', null, s));
  return foot;
}

// --- Panel lifecycle -----------------------------------------------------

function removePanel() {
  document.getElementById(PANEL_ID)?.remove();
}

function buildPanel(listing, plan) {
  removePanel();

  const panel = el('div', null);
  panel.id = PANEL_ID;
  panel.setAttribute('role', 'complementary');
  panel.setAttribute('aria-label', 'cubitt33 property data');

  const header = el('header', 'c33-header');
  header.appendChild(el('span', 'c33-title', 'cubitt33'));

  const close = el('button', 'c33-close', '×');
  close.type = 'button';
  close.setAttribute('aria-label', 'Close cubitt33 panel');
  close.addEventListener('click', () => {
    removePanel();
    showBadge(listing);
  });
  header.appendChild(close);
  panel.appendChild(header);

  // Echo back what we located, so a mislocation is obvious at a glance rather
  // than silently poisoning every number below it.
  if (listing.address) {
    panel.appendChild(el('p', 'c33-addr', listing.address));
  }

  if (plan.caveat) {
    panel.appendChild(el('p', 'c33-caveat', plan.caveat));
  }

  const body = el('div', 'c33-body');
  body.appendChild(el('p', 'c33-muted', 'Loading…'));
  panel.appendChild(body);

  document.body.appendChild(panel);
  return body;
}

// Ordered by how much each adds that the listing page does not.
//
// Environment first: noise and air quality are the only figures here a portal
// will never print. EPC and sold prices next - both exist on Rightmove, but the
// register is the authority rather than the agent's upload, and sold prices sit
// in a separate search tool rather than beside the asking price. Healthcare
// last, as the weakest.
//
// `postcode: true` marks a section that cannot start until /v1/environment has
// reverse-geocoded a postcode from the listing's coordinates.
const SECTIONS = {
  environment: { label: 'Environment', render: renderEnvironment },
  epc: { label: 'EPC register', render: renderEpc, postcode: true },
  soldPrices: { label: 'Sold nearby', render: renderSoldPrices, postcode: true },
  nhs: { label: 'Healthcare', render: renderNhs },
};

async function requestSection(name, listing, postcode) {
  try {
    return await chrome.runtime.sendMessage({
      type: 'FETCH_ENDPOINT',
      endpoint: name,
      lat: listing.lat,
      lon: listing.lon,
      postcode,
    });
  } catch {
    // Fires when the service worker was torn down mid-flight, or the extension
    // was reloaded while this tab stayed open. Both are recoverable by the
    // user, so report rather than fail silently.
    return { ok: false, error: 'extension reloaded, refresh the page' };
  }
}

async function loadInto(body, listing, plan) {
  // Each section gets its own placeholder and fills in when ITS upstream
  // answers. Previously the panel waited for both and repainted once, which
  // meant a slow or dead Overpass held the transport data hostage — measured at
  // up to 30 seconds of "Loading…" with TfL's answer already in memory.
  const slots = {};
  const parts = [];

  body.replaceChildren();
  for (const name of plan.sections) {
    const holder = el('section', 'c33-section');
    holder.appendChild(el('h3', 'c33-h3', SECTIONS[name].label));
    holder.appendChild(el('p', 'c33-muted', 'Loading…'));
    slots[name] = holder;
    body.appendChild(holder);
  }

  const results = {};

  const paint = (name, result) => {
    results[name] = result;
    const rendered = SECTIONS[name].render(result);
    slots[name].replaceWith(rendered);
    slots[name] = rendered;
  };

  // Coordinate-keyed sections start immediately. Postcode-keyed ones cannot:
  // a listing page yields a point, and /epc and /sold-prices want a postcode,
  // so they wait for /v1/environment to reverse-geocode one. Chained rather
  // than blocked — the coordinate sections still paint as they land, and a
  // failed environment call costs only the two that depend on it.
  const byKey = (wantsPostcode) =>
    plan.sections.filter((n) => Boolean(SECTIONS[n].postcode) === wantsPostcode);

  const coordWork = byKey(false).map(async (name) => {
    const result = await requestSection(name, listing);
    paint(name, result);
    return [name, result];
  });

  const postcodeWork = (async () => {
    const dependants = byKey(true);
    if (!dependants.length) return;

    const env = await requestSection('environment', listing);
    const postcode = env.ok ? (env.data || {}).location?.postcode : null;

    if (!postcode) {
      // No postcode means these genuinely cannot be answered, which is a
      // different thing from "we looked and found nothing". Say which.
      for (const name of dependants) {
        paint(name, { ok: false, error: 'no postcode resolved for this location' });
      }
      return;
    }

    await Promise.all(
      dependants.map(async (name) => {
        paint(name, await requestSection(name, listing, postcode));
      })
    );
  })();

  await Promise.all([...coordWork, postcodeWork]);

  // Attribution and the debug line go in once everything has settled: both are
  // summaries over the whole response set, so painting them early would mean
  // rewriting them.
  const sources = renderSources(Object.values(results));
  if (sources) parts.push(sources);

  const fromCache = Object.values(results).some((r) => r?.fromCache);

  // Debug line. Which extraction strategy won, the outcode we parsed, the
  // coordinates, and whether this came from cache. When Rightmove ships a
  // redesign this is the first thing to read: a silent fall-through to a weaker
  // strategy looks identical to success without it.
  //
  // The outcode is not used by either demo endpoint (both take lat/lon) but is
  // shown here because it IS the input the postcode-keyed endpoints will need
  // — /v1/score, /epc and /sold-prices. Surfacing it now means its accuracy is
  // being observed before anything depends on it.
  const debug = el(
    'div',
    'c33-debug',
    [
      listing.source,
      listing.outcode || 'no-outcode',
      `${listing.lat.toFixed(4)}, ${listing.lon.toFixed(4)}`,
      fromCache ? 'cached' : null,
    ]
      .filter(Boolean)
      .join(' · ')
  );
  parts.push(debug);

  // append, NOT replaceChildren. The sections are already in the DOM — they
  // painted as each upstream answered. Replacing here would wipe them and
  // undo the whole point of the incremental render.
  body.append(...parts);
}

// --- Badge (the click target) --------------------------------------------
// Nothing is fetched until this is pressed. See the file header.

function removeBadge() {
  document.getElementById(BADGE_ID)?.remove();
}

function showBadge(listing) {
  removeBadge();

  const badge = el('button', null, 'cubitt33');
  badge.id = BADGE_ID;
  badge.type = 'button';
  badge.setAttribute('aria-label', 'Show cubitt33 property data for this listing');

  badge.addEventListener('click', () => {
    const plan = decidePresentation(listing);
    if (plan.show === 'nothing') return;
    removeBadge();
    const body = buildPanel(listing, plan);
    loadInto(body, listing, plan);
  });

  document.body.appendChild(badge);
}

function run() {
  removePanel();
  removeBadge();

  const listing = extractListing();
  const plan = decidePresentation(listing);

  // show === 'nothing' means we could not locate the property. Render no UI at
  // all — an inert badge on a page we cannot serve is a promise we then break.
  if (plan.show === 'nothing') return;

  showBadge(listing);
}

// Rightmove routes between listings client-side, so a full page load is not
// guaranteed between one property and the next. Poll the URL rather than
// installing a MutationObserver over a page this size — the observer would fire
// on every lazy-loaded image for a signal we can read in one string compare.
let lastHref = location.href;
setInterval(() => {
  if (location.href !== lastHref) {
    lastHref = location.href;
    // Let the new page's scripts populate the DOM before extracting; the
    // coordinates are written by their router, not present at navigation time.
    setTimeout(run, 800);
  }
}, 1000);

run();
