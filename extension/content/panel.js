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
    // Outside Greater London TfL simply has no coverage, so /transport would
    // return zero stations. That is an absence of DATA, not an absence of
    // TRANSPORT, and rendering it as a bare "0 stations" would state the
    // second while only knowing the first.
    return {
      show: 'partial',
      sections: ['nhs'],
      caveat: 'Transport data covers Greater London only — not shown for this property.',
    };
  }

  return { show: 'full', sections: ['transport', 'nhs'], caveat: null };
}

// --- Section renderers ---------------------------------------------------

function renderTransport(result) {
  const section = el('section', 'c33-section');
  section.appendChild(el('h3', 'c33-h3', 'Transport'));

  if (!result.ok) {
    section.appendChild(el('p', 'c33-muted', `Transport data unavailable (${result.error}).`));
    return section;
  }

  const data = result.data;

  // The Lambda distinguishes "TfL unreachable" from "no stations nearby" via
  // an explicit `available` flag. Honour that distinction here — collapsing
  // the two is the exact defect that flag exists to prevent.
  if (data.available === false) {
    section.appendChild(el('p', 'c33-muted', data.note || 'Transport data temporarily unavailable.'));
    return section;
  }

  const stations = data.stations || [];
  if (stations.length === 0) {
    section.appendChild(el('p', 'c33-muted', 'No stations found within 1.5 km.'));
    return section;
  }

  const list = el('ul', 'c33-list');
  for (const station of stations.slice(0, 5)) {
    const item = el('li', 'c33-item');
    const row = el('div', 'c33-row');
    row.appendChild(el('span', 'c33-name', station.name || 'Unnamed station'));
    row.appendChild(el('span', 'c33-dist', metres(station.distance)));
    item.appendChild(row);

    const lines = station.lines || [];
    if (lines.length) {
      item.appendChild(el('div', 'c33-sub', lines.join(' · ')));
    }
    list.appendChild(item);
  }
  section.appendChild(list);

  // Line status is only worth surfacing when something is actually wrong —
  // a wall of "Good Service" is noise that trains the eye to skip the block.
  const disrupted = (data.lineStatus || []).filter(
    (l) => l.status && !/good service/i.test(l.status)
  );
  if (disrupted.length) {
    const warn = el('div', 'c33-warn');
    warn.appendChild(el('strong', null, 'Now: '));
    warn.appendChild(
      document.createTextNode(disrupted.map((l) => `${l.name} — ${l.status}`).join('; '))
    );
    section.appendChild(warn);
  }

  return section;
}

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

const SECTIONS = {
  transport: { label: 'Transport', render: renderTransport },
  nhs: { label: 'Healthcare', render: renderNhs },
};

async function requestSection(name, listing) {
  try {
    return await chrome.runtime.sendMessage({
      type: 'FETCH_ENDPOINT',
      endpoint: name,
      lat: listing.lat,
      lon: listing.lon,
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
  await Promise.all(
    plan.sections.map(async (name) => {
      const result = await requestSection(name, listing);
      results[name] = result;
      const rendered = SECTIONS[name].render(result);
      slots[name].replaceWith(rendered);
      slots[name] = rendered;
    })
  );

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
