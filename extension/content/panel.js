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
 * A collapsed explanation. Added 2026-08-07 because the panel was mostly prose:
 * on a real SW5 listing it showed three measurements carrying a two-sentence
 * coverage notice, a two-sentence DEFRA vintage paragraph and a guideline
 * sub-line each, and outside London it showed ONE measurement under two
 * notices. Caveats that long stop being read, which defeats the point of
 * writing them.
 *
 * What stays visible is the FACT; what collapses is the JUSTIFICATION. "Aircraft
 * noise (estimated)" is in the row label, and DEFRA-sourced rows are tagged
 * with their vintage inline, so a reader who never opens this still cannot
 * mistake an estimate for a measurement or 2021 data for current. What moves in
 * here is why DEFRA covers so little and what the anomalous year means — real
 * and worth keeping, but not worth burying the numbers under.
 */
function disclosure(summaryText, paragraphs) {
  const box = el('details', 'c33-note');
  box.appendChild(el('summary', 'c33-note-sum', summaryText));
  for (const p of paragraphs) box.appendChild(el('p', 'c33-note-body', p));
  return box;
}

const SVG_NS = 'http://www.w3.org/2000/svg';

function svgEl(tag, attrs) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  return node;
}

/**
 * Where a reading sits relative to its guideline, as one small bar.
 *
 * WHY THE SCALE RUNS 0 TO TWICE THE GUIDELINE. A bar needs a domain, and the
 * obvious choice - the observed range across London - is a number we would be
 * inventing at the point of drawing. METHODOLOGY §4.6 forbids exactly that
 * shape of thing for noise, and this project has twice had to undo a figure
 * that was estimated rather than sourced. The guideline is the ONLY reference
 * the endpoint hands us, so it is the only one used: it sits at the midpoint,
 * the scale ends at twice it, and every number drawn is one we were given.
 *
 * The consequence is that the bar answers "how does this compare to the WHO
 * guideline", not "how does this compare to London". That is a narrower claim
 * and it is the one the data supports.
 *
 * Over/under is carried by POSITION relative to the tick, not by colour alone,
 * so it survives WCAG 1.4.1. Colour reinforces it. The aria-label carries the
 * whole sentence, because a bar announces nothing on its own.
 */
function scaleBar({ value, guideline, unit, max }) {
  const ceiling = guideline ? guideline * 2 : max;
  const clamped = Math.min(Math.max(value / ceiling, 0), 1);
  const over = typeof guideline === 'number' && value > guideline;
  const pct = clamped * 100;

  const height = guideline ? 24 : 12;
  // Neutral when there is no guideline. Falling through to "under" would paint
  // the 0-10 quiet estimate green, i.e. assert it is good, against a threshold
  // that does not exist. Colour here reports a comparison; with nothing to
  // compare to it must report nothing.
  const verdict =
    typeof guideline === 'number' ? (over ? 'c33-bar-over' : 'c33-bar-under') : 'c33-bar-neutral';

  const svg = svgEl('svg', {
    class: `c33-bar ${verdict}`,
    width: '100%',
    height,
    role: 'img',
    'aria-label': guideline
      ? `${value} ${unit}, ${over ? 'above' : 'within'} the WHO guideline of ${guideline} ${unit}`
      : `${value} out of ${max}`,
  });

  svg.appendChild(svgEl('rect', { class: 'c33-bar-track', x: 0, y: 4, width: '100%', height: 4, rx: 2 }));
  svg.appendChild(svgEl('rect', { class: 'c33-bar-fill', x: 0, y: 4, width: `${pct}%`, height: 4, rx: 2 }));

  if (guideline) {
    // The tick is always at the midpoint, by construction of the domain.
    svg.appendChild(svgEl('line', { class: 'c33-bar-tick', x1: '50%', x2: '50%', y1: 1, y2: 11 }));
    const lab = svgEl('text', { class: 'c33-bar-lab', x: '50%', y: 21, 'text-anchor': 'middle' });
    lab.textContent = `WHO ${guideline}`;
    svg.appendChild(lab);
  }

  svg.appendChild(svgEl('circle', { class: 'c33-bar-dot', cx: `${pct}%`, cy: 6, r: 3.5 }));
  return svg;
}

/**
 * The compact "we have nothing" state. Was a heading plus a sentence per
 * section, so four dead sections cost eight lines and pushed the data that DID
 * arrive off-screen. One line each now, and the reason is kept in the title
 * attribute rather than thrown away.
 */
function unavailable(label, reason) {
  const row = el('p', 'c33-none', `${label} — not available`);
  if (reason) row.title = String(reason);
  return row;
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
  if (!result.ok) {
    return unavailable('Healthcare', result.error);
  }

  const section = el('section', 'c33-section');
  section.appendChild(el('h3', 'c33-h3', 'Healthcare'));

  const data = result.data;

  if (data.available === false) {
    section.appendChild(el('p', 'c33-none', data.note || 'Live data unavailable'));
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
    section.appendChild(el('p', 'c33-none', 'None found nearby'));
  }

  return section;
}

function renderEnvironment(result) {
  if (!result.ok) {
    return unavailable('Environment', result.error);
  }

  const section = el('section', 'c33-section');
  section.appendChild(el('h3', 'c33-h3', 'Environment'));

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
  // Whether the DEFRA rows carry the COVID-year vintage. Kept as a per-row flag
  // so the tag sits ON the affected reading rather than as a paragraph under
  // rows it does not apply to.
  const mapsCovidYear = [env.aircraftNoiseSource, env.roadNoiseSource]
    .filter(Boolean)
    .some((s) => /maps 2021/.test(s));

  const rows = [
    ['Aircraft noise', env.aircraftNoiseLdenDb, 'dB Lden', env.aircraftNoiseWhoGuidelineDb, mapsCovidYear],
    ['Aircraft noise (estimated)', env.aircraftQuietEstimated, '/10 quiet', null, false],
    ['Road noise', env.roadNoiseLdenDb, 'dB Lden', env.roadNoiseWhoGuidelineDb, mapsCovidYear],
    ['Nitrogen dioxide', env.no2AnnualMeanUgm3, 'ug/m3', env.no2WhoGuidelineUgm3, false],
    ['Fine particles (PM2.5)', env.pm25AnnualMeanUgm3, 'ug/m3', env.pm25WhoGuidelineUgm3, false],
  ].filter((r) => typeof r[1] === 'number');

  if (rows.length) {
    const list = el('ul', 'c33-list');
    for (const [label, value, unit, guideline, vintage] of rows) {
      const item = el('li', 'c33-item');
      const row = el('div', 'c33-row');
      const name = el('span', 'c33-name', label);
      // The vintage rides on the reading it qualifies. This used to be a
      // two-sentence paragraph below the list, which meant it applied visually
      // to the air-quality rows it has nothing to do with.
      if (vintage) {
        // The space is a real text node, not CSS margin. Without it textContent
        // is "Aircraft noise2021", which is what a screen reader announces and
        // what any text assertion sees - the margin only moves pixels.
        name.appendChild(document.createTextNode(' '));
        const tag = el('span', 'c33-tag', '2021');
        tag.title = 'DEFRA data mapping 2021';
        name.appendChild(tag);
      }
      row.appendChild(name);

      // "/10 quiet" is a suffix, not a unit, so it takes no leading space -
      // this rendered as "5 /10 quiet".
      const readout = el(
        'span',
        'c33-dist',
        unit.startsWith('/') ? `${value}${unit}` : `${value} ${unit}`
      );
      // Colour states a fact, not a verdict: whether the measurement is above
      // the cited guideline. No "good"/"bad" wording, because the guideline is
      // WHO's judgement and the comparison is arithmetic — anything richer
      // would be us editorialising over someone else's threshold.
      if (typeof guideline === 'number') {
        readout.className += value > guideline ? ' c33-over' : ' c33-under';
      }
      row.appendChild(readout);
      item.appendChild(row);

      // The bar replaces the sub-line it used to carry ("within WHO 53 dB
      // Lden"), which was repeated verbatim on every row and read as
      // boilerplate. The same fact is now positional, and the aria-label still
      // says it in words for anyone the bar cannot reach.
      if (typeof guideline === 'number') {
        item.appendChild(scaleBar({ value, guideline, unit }));
      } else if (unit.startsWith('/')) {
        // The 0-10 quiet estimate: a scale by construction, so it gets a bar
        // with no guideline tick. There is nothing to compare it to, and
        // inventing a threshold for a geometry-derived figure would be exactly
        // the move the comment above refuses.
        item.appendChild(scaleBar({ value, guideline: null, unit, max: 10 }));
      }
      list.appendChild(item);
    }
    section.appendChild(list);
  }

  // The vintage caveat travels with the reading, not just in the footer.
  //
  // DEFRA Round 4 was published in 2022 and maps 2021 — a year its own
  // documentation calls "a highly anomalous situation" because of COVID travel
  // restrictions, with Heathrow movements substantially below 2019. Every dB
  // here therefore ERRS QUIET. Shown beside the numbers because a reader who
  // takes 50.4 dB at face value has been misled by an omission, and the footer
  // is not where anyone looks for that.
  //
  // No corrected figure is offered. METHODOLOGY §4.6 forbids applying an
  // estimated correction factor: inventing a multiplier is a failure mode this
  // project has already had to undo twice.
  // One disclosure for everything explanatory, rather than a stack of
  // paragraphs. The facts these justify are already on the rows: "(estimated)"
  // in a label, "2021" tagged on the readings it applies to. See disclosure().
  const explanations = [];
  if (mapsCovidYear) {
    explanations.push(
      'DEFRA noise data maps 2021, a COVID-affected year, so these readings ' +
        'understate current exposure. The direction is known; the amount is not, ' +
        'and no correction factor is applied.'
    );
  }
  explanations.push(...(data.notices || []));

  if (explanations.length) {
    // The summary names the count so it is obvious something was left out,
    // rather than a decorative "more info" nobody opens.
    const label =
      explanations.length === 1
        ? 'About this reading'
        : `About these readings (${explanations.length})`;
    section.appendChild(disclosure(label, explanations));
  }

  if (!rows.length && !explanations.length) {
    section.appendChild(el('p', 'c33-none', 'No environmental measurements here'));
  }

  return section;
}

function renderEpc(result) {
  if (!result.ok) {
    return unavailable('EPC register', result.error);
  }

  const section = el('section', 'c33-section');
  section.appendChild(el('h3', 'c33-h3', 'EPC register'));

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
  if (!result.ok) {
    return unavailable('Sold nearby', result.error);
  }

  const section = el('section', 'c33-section');
  section.appendChild(el('h3', 'c33-h3', 'Sold nearby'));

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
    // Rightmove's displayAddress repeats the town when the street already names
    // it, so a real SW5 listing renders "Collingham Road, London, London, SW5".
    // Dedupe case-insensitively and keep the FIRST occurrence, which preserves
    // the address's own ordering rather than imposing one.
    const seen = new Set();
    const address = String(listing.address)
      .split(',')
      .map((part) => part.trim())
      .filter((part) => {
        if (!part) return false;
        const key = part.toLowerCase();
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .join(', ');
    panel.appendChild(el('p', 'c33-addr', address));
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
