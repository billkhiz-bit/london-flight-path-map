/* global d3 */
/* The engine behind the front page (home/index.html, served at /) and its mockups
   (design/homepage-v*.html): the live map, the city chips, the working
   postcode-or-place search, the council-area card, the layer toggles and the
   zoom. Each layout is markup round the same ids (#map, #chips, #check, #pc,
   #status, #answer and its parts, #borough and its parts, #ramp, the toggles
   and zoom buttons); any of them may be absent from a mockup, so every lookup
   tolerates a missing element. One copy, here.

   What it reads, all served by this site: the borough outlines, borough-extra,
   flight-procedures and the noise pictures the live map uses, plus the open
   data CSV (/open-data/) for every council area's Sky Score - so a borough
   tap shows a real score without an API key and without spending anyone's
   quota. A postcode goes to postcodes.io and then the key-free
   /v1/environment. The runway geometry is js/flight_geometry.mjs, the one
   holder the two report generators use. */
import { AIRPORT_NAME, compass, plane, routesNear, towards } from '/js/flight_geometry.mjs';
import { DEFRA_LDEN_SCALE, LONDON_RASTER } from '/js/street_report.mjs';

// The full map's address since the front page took / (2026-10-06). Every link
// from here to the map goes through it.
const MAP_PATH = '/map/';

// ---- what the page knows: the same data files the live site ships ----
// DEFRA's colours and London's picture box come from js/street_report.mjs, whose
// copies are held to index.html's on every report run and in preflight; this
// engine kept a third copy of each until 2026-10-06.
const DEFRA = DEFRA_LDEN_SCALE.map((b) => b.colour);
// BTS's seven colours, as NOISE_SCALE_BTS in index.html: the Bay Area's picture.
const BTS = ['#FFC107', '#FF8000', '#FF0000', '#FF3399', '#A300CC', '#5200CC', '#0000FF'];
const CITIES = [
  ['london', 'London'], ['manchester', 'Greater Manchester'], ['westmidlands', 'West Midlands'],
  ['westyorkshire', 'West Yorkshire'], ['southyorkshire', 'South Yorkshire'], ['merseyside', 'Merseyside'],
  ['tyneandwear', 'Tyne and Wear'], ['bristol', 'Bristol'], ['leicester', 'Leicester'], ['teesside', 'Teesside'],
  ['bayarea', 'San Francisco Bay Area'], ['nyc', 'New York'],
];
const CITY_NAME = Object.fromEntries(CITIES);
// Own keys only: `CITY_NAME.constructor` is truthy, so ?city=constructor
// once opened a map that could not load (audit 2026-10-05 M-6).
const isMapCity = (k) => Object.hasOwn(CITY_NAME, k);

// ---- ask first, then the tool (Bill, 2026-10-05) ----
// The page opens as v3 (the question over a faded map) and becomes v2 (the tool)
// the first time someone uses it. One way in, one way out: leaveIntro().
const hero = document.querySelector('.hero');
// STACKED is declared further down; this runs only after the module has loaded.
const inIntro = () => Boolean(hero?.classList.contains('is-intro')) && !window.matchMedia(STACKED).matches;
function leaveIntro() {
  if (!hero?.classList.contains('is-intro')) return;
  const wasIntro = inIntro();
  hero.classList.remove('is-intro');
  // The map refits beside the panel; on a stacked layout nothing moved.
  if (wasIntro && state.boroughs) draw(state.pin);
}
// The Bay Area here is drawn from the files the /bay-area/ page is built from:
// its outlines the Census places, its routes the FAA record, its noise picture
// the one that page serves.
const US = {
  bayarea: { places: '/data/us-bayarea-places.json', proc: '/data/us-flight-procedures.json', noiseDir: '/bay-area/' },
  // New York (Bill, 2026-10-06: "show on the main screen instead of going to the full map"):
  // the map's own outlines, the FAA's routes for JFK, LaGuardia, Newark and Teterboro, and
  // scripts/build_nyc_front.py's file - the US noise picture's frame and one row per borough
  // from the score engine, in the open-data CSV's row shape.
  nyc: { data: '/data/us-nyc.json', outlines: '/data/nyc-boroughs.json', proc: '/data/us-flight-procedures.json' },
};
const isUs = (key) => Object.hasOwn(US, key);
// London's picture is the one file not described by aircraft-noise-rasters.json.
const LONDON_PNG = { png: `/${LONDON_RASTER.png}`, bbox: LONDON_RASTER.bbox };
// js/api-base.js is the one holder of the API host; the literal is for a mockup opened without it.
const ENV = `${window.API_BASE || 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod'}/v1/environment`;
const CSV = '/open-data/sky-score-boroughs.csv';
const FT_KM = 0.0003048;
// When the panel stacks above the map rather than floating over it: the SAME
// query as the @media rule in home/index.html (audit 2026-10-05 I-4). The
// engine used to decide on the map's own width (> 760px) while the CSS tested
// the viewport, so 761-826px got the floating CSS with a full-width map beneath.
const STACKED = '(max-width: 1279px), (max-height: 500px)';
// How far out an airport counts as "near" a searched postcode, and how close to
// an approach line a street must be to be called "under" it. The street report
// (scripts/address_noise_report.mjs) uses its own, wider ones (40 km and 5 km):
// it is read for one address, this is glanced at for a postcode.
const AIRPORT_SCOPE_KM = 30;
const UNDER_LINE_KM = 1.0;
const ZOOM_MAX = 6;
const ZOOM_STEP = 1.6;

// ---- trial (2026-10-03): an Ordnance Survey street background ----
// The OS Maps API's OpenData layers cost nothing at any zoom this map reaches
// (ROADMAP "OS open maps API"), but need a Data Hub key. No key is in the
// source: opening /#oskey=<key> once stores it on that device and
// takes it out of the address bar; #oskey=off forgets it. The FRAGMENT, not the
// query (audit 2026-10-05 M-1): a query string reaches the server and the service
// worker's page cache, which kept the key after #oskey=off; a fragment reaches
// neither. A ?oskey= in the query is dropped unread. Without a key the
// Streets button stays hidden and nothing is asked of api.os.uk.
const OS_LAYER = 'Light_3857'; // the muted style, so the noise picture reads over it; Road_3857 and Outdoor_3857 also exist
const OS_ZOOM = [7, 16]; // the OpenData band; Premium starts at 17
const OS_MAX_TILES = 80;
const OS_KEY_STORE = 'osMapsKey';
const osKey = {
  get() { try { return localStorage.getItem(OS_KEY_STORE) || ''; } catch { return ''; } },
  set(v) { try { if (v) localStorage.setItem(OS_KEY_STORE, v); else localStorage.removeItem(OS_KEY_STORE); } catch { /* storage blocked: the trial stays off */ } },
};

const byId = (id) => document.getElementById(id);
const svg = d3.select('#map');
const tip = byId('tip');
const state = {
  city: null, boroughs: null, extra: null, proc: null, rasters: null, projection: null,
  usProc: null, usNoise: null, usPlaces: null,
  nycDoc: null, nycNoise: null, // scripts/build_nyc_front.py's file, and its picture placed on the map
  usZips: null, // the Census ZIP areas of the four Bay Area counties, fetched on the first ZIP typed
  rows: [], // the open-data CSV, one object per council area
  layers: { noise: true, lines: true, streets: false },
  zoom: null, k: 1,
  routes: [], // every drawn route as view-space segments with its tooltip, for the pointer-distance check
  selected: null, // the name of the council area or Bay Area place whose card is open
};

// "Or explore the map" (Bill, 2026-10-06). The intro used to say "or tap a council area
// on the map" while, on a wide screen, the map sat faded behind the question with its
// controls hidden. This is the way to the map without a search: wide, it ends the intro
// and brings the map and its controls forward; stacked, the map is already below the
// question and is scrolled into view. Focus lands on the first council area either way,
// so a keyboard user arrives where they asked to go.
byId('explore-map')?.addEventListener('click', () => {
  leaveIntro();
  const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  document.querySelector('.mapwrap')?.scrollIntoView({ behavior: still ? 'auto' : 'smooth', block: 'start' });
  document.querySelector('#map .boro')?.focus({ preventScroll: true });
});

const ramp = byId('ramp');
// The ramp is the palette of the picture on the map: DEFRA's in England, BTS's
// in the Bay Area. It was DEFRA's everywhere, so not one colour painted over
// the Bay Area appeared in its legend (audit 2026-10-05 M-11).
const paintRamp = (key) => {
  if (ramp) ramp.innerHTML = (isUs(key) ? BTS : DEFRA).map((c) => `<b style="background:${c}"></b>`).join('');
};
paintRamp('london');

const dest = (lat, lon, brg, km) => {
  const R = 6371.0088, d = km / R, b = (brg * Math.PI) / 180, la = (lat * Math.PI) / 180, lo = (lon * Math.PI) / 180;
  const la2 = Math.asin(Math.sin(la) * Math.cos(d) + Math.cos(la) * Math.sin(d) * Math.cos(b));
  const lo2 = lo + Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(la), Math.cos(d) - Math.sin(la) * Math.sin(la2));
  return [(lo2 * 180) / Math.PI, (la2 * 180) / Math.PI];
};
const size = () => { const r = svg.node().getBoundingClientRect(); return [Math.max(320, r.width), Math.max(300, r.height)]; };
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
// Same normalisation as the live map's borough matcher: postcodes.io writes
// "Bristol, City of" and "St. Helens" where the registry has "City of Bristol"
// and "St Helens".
const norm = (s) => String(s).toLowerCase().replace(/[.,]/g, '').replace(/\s+/g, ' ').trim().replace(/^(.*) city of$/, 'city of $1');
// build_area_pages.py's slug(): lowercase, runs of anything else become one hyphen.
const slug = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const fmt1 = (v) => (v === '' || v == null ? null : Number(v).toFixed(1));
const km = (d) => (d < 10 ? d.toFixed(1) : Math.round(d)) + ' km';
const ugm3 = (v) => (v === '' || v == null ? '' : ` (${v} µg/m³)`);

// ---- the open data CSV: every council area's score, no key needed ----
function parseCsv(text) {
  const rows = [];
  let field = '', row = [], quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; } else if (c === '"') quoted = false; else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') { row.push(field); field = ''; }
    else if (c === '\n' || c === '\r') { if (c === '\r' && text[i + 1] === '\n') i++; row.push(field); rows.push(row); field = ''; row = []; }
    else field += c;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  const [head, ...body] = rows.filter((r) => r.length > 1);
  return body.map((r) => Object.fromEntries(head.map((h, i) => [h, r[i] ?? ''])));
}
const rowFor = (name) => state.rows.find((r) => norm(r.borough) === norm(name)) || null;

async function load() {
  const [extra, proc, rasters, csv, nycDoc] = await Promise.all([
    d3.json('/data/borough-extra.json'), d3.json('/data/flight-procedures.json'), d3.json('/data/aircraft-noise-rasters.json'),
    d3.text(CSV).catch(() => ''),
    // Optional like the CSV: without it New York's chip still draws, and its cards say "not scored".
    d3.json(US.nyc.data).catch(() => null),
  ]);
  Object.assign(state, { extra, proc, rasters, nycDoc, rows: [...(csv ? parseCsv(csv) : []), ...(nycDoc?.rows || [])] });
  readOsKey();
  renderChips();
  bindControls();
  await bootFromQuery();
}

function renderChips() {
  const box = byId('chips');
  if (!box) return;
  box.innerHTML = '';
  for (const [key, name] of CITIES) {
    const b = document.createElement('button');
    b.type = 'button'; b.textContent = name; b.dataset.city = key; b.setAttribute('aria-pressed', 'false');
    b.addEventListener('click', () => { leaveIntro(); show(key); setQuery({ city: key }); });
    box.append(b);
  }
}

// ?oskey= is read once and removed, so a key is never left in a link that gets
// shared or bookmarked. Anything that is not a plain token is ignored.
function readOsKey() {
  const given = new URLSearchParams(location.hash.slice(1)).get('oskey');
  const q = new URLSearchParams(location.search);
  const inQuery = q.has('oskey');
  if (given != null) {
    if (given === 'off') osKey.set('');
    else if (/^[A-Za-z0-9]{8,64}$/.test(given)) osKey.set(given);
  }
  if (given != null || inQuery) {
    q.delete('oskey');
    const s = q.toString();
    history.replaceState(null, '', s ? `?${s}` : location.pathname);
  }
  state.layers.streets = Boolean(osKey.get());
}

// ---- the URL: the same names the live map reads, so links carry across ----
async function bootFromQuery() {
  const q = new URLSearchParams(location.search);
  const city = (q.get('city') || '').toLowerCase().trim();
  const postcode = (q.get('postcode') || '').trim();
  const borough = (q.get('borough') || '').trim();
  const row = borough ? rowFor(borough) : null;
  // A council area names its own city: ?city=manchester&borough=Camden opens London.
  const start = row && isMapCity(row.city) ? row.city : isMapCity(city) ? city : 'london';
  // A link that names a city came for that city's map: it opens on the tool, not the
  // question over a faded map with the city chips hidden. (A postcode or council area
  // leaves the question by itself, through search() and selectBorough().)
  if (isMapCity(city)) leaveIntro();
  await show(start);
  if (postcode) {
    const input = byId('pc');
    if (input) { input.value = postcode; await search(postcode); }
  } else if (borough) {
    selectBorough(borough);
  }
}
function setQuery(parts) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(parts)) if (v) q.set(k, v);
  const s = q.toString();
  history.replaceState(null, '', s ? `?${s}` : location.pathname);
}

// ---- the map ----
// A US picture's frame is in web-mercator pixels at the zoom it was fetched at.
function frameBox(frame) {
  const [x0, y0, x1, y1] = frame.px;
  const n = 256 * 2 ** frame.zoom;
  const lonlat = (px, py) => [(px / n) * 360 - 180, (Math.atan(Math.sinh(Math.PI * (1 - (2 * py) / n))) * 180) / Math.PI];
  const [minLon, maxLat] = lonlat(x0, y0);
  const [maxLon, minLat] = lonlat(x1, y1);
  return { minLon, maxLon, minLat, maxLat };
}

async function loadNyc() {
  const [doc, proc, outlines] = await Promise.all([
    state.nycDoc || d3.json(US.nyc.data).catch(() => null), d3.json(US.nyc.proc), d3.json(US.nyc.outlines),
  ]);
  state.nycDoc = doc;
  state.usProc = proc;
  state.nycNoise = doc ? { png: `/data/${doc.noise.file}`, bbox: frameBox(doc.frame) } : null;
  return outlines;
}

async function loadBayArea() {
  const [places, proc] = await Promise.all([d3.json(US.bayarea.places), d3.json(US.bayarea.proc)]);
  state.usProc = proc;
  state.usPlaces = places;
  state.usNoise = { png: US.bayarea.noiseDir + places.noise.file, bbox: frameBox(places.frame) };
  // Shapefile rings wind the opposite way to what d3's spherical geometry
  // expects for holes, so these are drawn on the plane (see planarPath).
  const features = places.places
    .filter((p) => p.kind !== 'cdp')
    .map((p) => ({ type: 'Feature', properties: { name: p.name, county: p.county, planar: true }, geometry: { type: 'MultiPolygon', coordinates: p.rings.map((r) => [r]) } }));
  return { type: 'FeatureCollection', features };
}

const ringArea = (ring) => Math.abs(d3.sum(ring, (p, i) => { const q = ring[(i + 1) % ring.length]; return p[0] * q[1] - q[0] * p[1]; }));
// Each place's LARGEST ring only: San Francisco's outline includes the Farallon Islands, 45 km out to sea.
const mainRing = (f) => d3.greatest(f.geometry.coordinates, (poly) => ringArea(poly[0]))[0];

function fitTarget(fc) {
  // A plain bounding box, wound clockwise, which d3 fits without reading each ring.
  const pts = fc.features.flatMap(mainRing);
  const lons = pts.map((p) => p[0]), lats = pts.map((p) => p[1]);
  const a = Math.min(...lons), b = Math.max(...lons), c = Math.min(...lats), d = Math.max(...lats);
  return { type: 'Polygon', coordinates: [[[a, c], [a, d], [b, d], [b, c], [a, c]]] };
}

let showSeq = 0;
async function show(key, pin) {
  const seq = ++showSeq;
  const boroughs = key === 'bayarea' ? await loadBayArea() : key === 'nyc' ? await loadNyc() : await d3.json(`/data/${key}-boroughs.json`);
  // The latest request owns the map: an outline file that lands late must not
  // draw one city's council areas under another's routes and noise picture.
  if (seq !== showSeq) return;
  state.city = key;
  state.boroughs = boroughs;
  paintRamp(key);
  document.querySelectorAll('#chips button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.city === key)));
  // The reset below ends a zoom, which re-tiles the street map: with no
  // projection it has nothing to tile, so the old city's tiles are not fetched.
  state.projection = null;
  if (state.zoom) svg.call(state.zoom.transform, d3.zoomIdentity);
  draw(pin);
}

// London's 2013 ONS file names its property LAD13NM; the live map's featureName() reads the same set.
const featureName = (f) => { const p = f.properties; return p.name || p.NAME || p.LAD13NM || p.LAD21NM || p.LAD24NM || ''; };

function draw(pin) {
  const [W, H] = size();
  hideTip();
  svg.attr('viewBox', `0 0 ${W} ${H}`).selectAll('*').remove();
  // Each layout says how much of the map a floating panel covers, in pixels at desktop width.
  const zero = { left: 0, top: 0, right: 0, bottom: 0 };
  // While the question sits centred over the map (.is-intro), the map fills the box.
  const inset = !inIntro() && document.body.dataset.mapInset ? JSON.parse(document.body.dataset.mapInset) : zero;
  const wide = !window.matchMedia(STACKED).matches;
  const planar = state.boroughs.features.some((f) => f.properties.planar);
  const projection = d3.geoMercator().fitExtent(
    [[(wide ? inset.left : 0) + 24, (wide ? inset.top : 0) + 24], [W - (wide ? inset.right : 0) - 24, H - (wide ? inset.bottom : 0) - 64]],
    planar ? fitTarget(state.boroughs) : state.boroughs,
  );
  state.projection = projection;
  state.pin = pin || null;
  const geoPath = d3.geoPath(projection);
  const planarPath = (f) =>
    f.geometry.coordinates
      .map((poly) => poly.map((ring) => 'M' + ring.map((pt) => projection(pt).map((v) => v.toFixed(1)).join(' ')).join('L') + 'Z').join(''))
      .join('');
  const path = (f) => (f.properties.planar ? planarPath(f) : geoPath(f));

  // Everything drawn sits in one group the zoom transforms.
  const view = svg.append('g').attr('class', 'view');
  // The noise picture is cut to the city's outline: DEFRA's London export reaches Gatwick,
  // and a lobe floating beside the map reads as a mistake.
  view.append('clipPath').attr('id', 'city-clip').selectAll('path').data(state.boroughs.features).join('path').attr('d', path);
  // The street-map trial sits under everything; drawStreets() fills it.
  view.append('g').attr('class', 'streets').style('pointer-events', 'none');
  view.append('g').selectAll('path').data(state.boroughs.features).join('path')
    .attr('class', 'boro').attr('d', path).attr('fill-rule', 'evenodd')
    .classed('is-selected', (d) => featureName(d) === state.selected)
    // A borough is a control: it opens the council area's card. role=img on the
    // svg would hide these from assistive tech, so the svg is a group instead.
    .attr('role', 'button').attr('tabindex', 0)
    .attr('aria-label', (d) => `${featureName(d)}: open its figures`)
    .on('mousemove', (ev, d) => showTip(ev, boroughTipHtml(d)))
    .on('mouseleave', hideTip)
    .on('focus', async (ev, d) => {
      const el = ev.currentTarget;
      const epoch = tipEpoch;
      // Tabbing to an area off a zoomed map brings it in first (M-16).
      await bringIntoView(el);
      // Not if focus moved on, or a hide came in while we waited (a tap's card opening: M-15).
      if (document.activeElement !== el || epoch !== tipEpoch) return;
      // The bbox is in view space; the tip is placed in screen space, so apply the zoom.
      const r = el.getBBox();
      const [x, y] = d3.zoomTransform(svg.node()).apply([r.x + r.width / 2, r.y + r.height / 2]);
      showTipAt(x, y, boroughTipHtml(d));
    })
    .on('blur', hideTip)
    .on('click', (ev, d) => selectBorough(featureName(d), { scroll: true }))
    .on('keydown', (ev, d) => {
      if (ev.key !== 'Enter' && ev.key !== ' ') return;
      ev.preventDefault();
      selectBorough(featureName(d), { scroll: true, focus: true });
    });

  const raster = state.city === 'london' ? LONDON_PNG : state.city === 'bayarea' ? state.usNoise : state.city === 'nyc' ? state.nycNoise : state.rasters.cities[state.city];
  if (raster) {
    const [x0, y0] = projection([raster.bbox.minLon, raster.bbox.maxLat]);
    const [x1, y1] = projection([raster.bbox.maxLon, raster.bbox.minLat]);
    view.append('image').attr('id', 'noise-image').attr('href', raster.png).attr('x', x0).attr('y', y0).attr('width', x1 - x0).attr('height', y1 - y0)
      .attr('preserveAspectRatio', 'none').style('mix-blend-mode', document.body.dataset.noiseBlend || 'multiply').attr('clip-path', 'url(#city-clip)').style('pointer-events', 'none')
      .style('display', state.layers.noise ? null : 'none');
  }
  markLayerCoverage('noise', Boolean(raster));

  // Routes are cut to the city's outline too: a departure runs 50 km to its
  // last waypoint, and a dozen of them crossing the whole hero read as noise.
  const lines = view.append('g').attr('class', 'lines').attr('clip-path', 'url(#city-clip)').style('display', state.layers.lines ? null : 'none');
  state.routes = [];
  const marks = view.append('g').attr('class', 'marks').style('pointer-events', 'none');
  const proc = isUs(state.city) ? state.usProc : state.proc;
  let drawn = 0;
  for (const [code, ap] of Object.entries(proc.airports)) {
    if (!(ap.cities || []).includes(state.city)) continue;
    const name = AIRPORT_NAME[code] || ap.name || code;
    for (const [rwy, r] of Object.entries(ap.runways)) {
      if (r.glide_deg == null || !r.thr) continue;
      const far = dest(r.thr[0], r.thr[1], r.true_brg + 180, (3000 * FT_KM) / Math.tan((r.glide_deg * Math.PI) / 180));
      const a = projection([r.thr[1], r.thr[0]]), b = projection(far);
      const html = `<b>${esc(name)} runway ${esc(rwy)}</b>Final approach on a ${r.glide_deg}&deg; glide path, aircraft descending towards the ${towards(r.true_brg)}, drawn from 3,000 ft down to the runway.`;
      lines.append('line').attr('class', 'final').attr('x1', a[0]).attr('y1', a[1]).attr('x2', b[0]).attr('y2', b[1]);
      state.routes.push({ pts: [a, b], html });
      drawn++;
    }
    for (const dep of ap.departures || []) {
      if (!dep.waypoints || dep.waypoints.length < 2) continue;
      const html = `<b>${esc(name)} departure ${esc(dep.name)}</b>Published departure route from runway ${esc(dep.runway)}, heading ${towards(parseInt(dep.runway, 10) * 10)} at first.`;
      const pts = dep.waypoints.map(([la, lo]) => projection([lo, la]));
      lines.append('path').attr('class', 'departure').attr('d', 'M' + pts.map((pt) => pt.map((v) => v.toFixed(1)).join(' ')).join('L'));
      state.routes.push({ pts, html });
      drawn++;
    }
    const thr = Object.values(ap.runways).map((r) => r.thr).filter(Boolean);
    if (thr.length) {
      const p = projection([d3.mean(thr, (t) => t[1]), d3.mean(thr, (t) => t[0])]);
      marks.append('rect').attr('class', 'ap-box').attr('x', p[0] - 4).attr('y', p[1] - 4).attr('width', 8).attr('height', 8).attr('fill', '#f27d26').attr('stroke', '#141414');
      marks.append('text').attr('class', 'ap').attr('x', p[0] + 8).attr('y', p[1] - 6).text(code).append('title').text(name);
    }
  }
  markLayerCoverage('lines', drawn > 0);
  if (pin) {
    const [px, py] = projection([pin.lon, pin.lat]);
    marks.append('circle').attr('class', 'pin-ring').attr('cx', px).attr('cy', py).attr('r', 9);
    marks.append('circle').attr('class', 'pin').attr('cx', px).attr('cy', py).attr('r', 4);
  }
  bindZoom(W, H);
  applyScale();
  drawStreets();
}

// Web-mercator tiles under a d3 mercator. With the projection's default centre
// the world is 2*pi*k view pixels square, centred on its translate, so tile
// (x, y) at zoom z sits at a fixed place in view space and the zoom transform
// carries it with everything else. Re-tiled when a zoom ends, at the level
// whose tiles are nearest 256 px on screen.
const OS_CREDIT = byId('os-credit')?.textContent || '';
function drawStreets() {
  const key = osKey.get();
  // OS maps Great Britain only: the US cities keep their plain ground.
  const can = Boolean(key) && !isUs(state.city);
  const on = can && state.layers.streets;
  const b = byId('toggle-streets');
  if (b) {
    b.hidden = !key;
    b.disabled = Boolean(key) && !can;
    b.title = b.disabled ? 'Ordnance Survey maps Great Britain only' : '';
    b.setAttribute('aria-pressed', String(on));
  }
  svg.classed('has-streets', on);
  const credit = byId('os-credit');
  if (credit) { credit.hidden = !on; credit.textContent = OS_CREDIT; }
  const g = svg.select('.streets');
  if (g.empty() || !state.projection) return;
  g.selectAll('*').remove();
  if (!on) return;
  const [W, H] = size();
  const world = 2 * Math.PI * state.projection.scale();
  const [tx, ty] = state.projection.translate();
  const t = d3.zoomTransform(svg.node());
  const z = Math.max(OS_ZOOM[0], Math.min(OS_ZOOM[1], Math.round(Math.log2((world * t.k) / 256))));
  const n = 2 ** z, ts = world / n;
  const x0 = tx - world / 2, y0 = ty - world / 2;
  const [vx0, vy0] = t.invert([0, 0]), [vx1, vy1] = t.invert([W, H]);
  const index = (v, origin) => Math.max(0, Math.min(n - 1, Math.floor((v - origin) / ts)));
  const tiles = [];
  for (let x = index(vx0, x0); x <= index(vx1, x0); x++) {
    for (let y = index(vy0, y0); y <= index(vy1, y0); y++) tiles.push([x, y]);
  }
  if (tiles.length > OS_MAX_TILES) return;
  g.selectAll('image').data(tiles).join('image')
    .attr('href', ([x, y]) => `https://api.os.uk/maps/raster/v1/zxy/${OS_LAYER}/${z}/${x}/${y}.png?key=${encodeURIComponent(key)}`)
    .attr('x', ([x]) => x0 + x * ts).attr('y', ([, y]) => y0 + y * ts)
    // Half a view pixel of overlap hides the hairline between tiles at fractional sizes.
    .attr('width', ts + 0.5).attr('height', ts + 0.5).attr('preserveAspectRatio', 'none')
    // A refused key must not look like a plain map: say so where the credit is.
    .on('error', () => { if (credit) credit.textContent = 'The OS map could not load. Check the key.'; });
}

// A 1.8px line cannot be hovered, and a wide invisible twin of it STEALS the
// tap from the borough beneath (the first run of tests/preview-home.mjs could
// not click Hounslow through Heathrow's 27L approach). So routes have no hit
// area at all: the svg measures the pointer's distance to every drawn route
// and shows the route's tooltip when it is within a few pixels. Boroughs keep
// every click. Bubbles after the borough's own handler, so a near route wins.
const ROUTE_HOVER_PX = 7;
function routeNear(ev) {
  if (!state.layers.lines || !state.routes.length) return null;
  // The lines are clipped to the city's outline but state.routes keeps every
  // segment, so only a pointer over a council area can be over a drawn line.
  if (!ev.target.classList?.contains('boro')) return null;
  const r = svg.node().getBoundingClientRect();
  const t = d3.zoomTransform(svg.node());
  const [vx, vy] = t.invert([ev.clientX - r.left, ev.clientY - r.top]);
  let best = { d: Infinity, route: null };
  for (const route of state.routes) {
    for (let i = 0; i + 1 < route.pts.length; i++) {
      const [ax, ay] = route.pts[i], [bx, by] = route.pts[i + 1];
      const abx = bx - ax, aby = by - ay;
      const s = Math.max(0, Math.min(1, ((vx - ax) * abx + (vy - ay) * aby) / (abx * abx + aby * aby || 1)));
      const d = Math.hypot(vx - (ax + s * abx), vy - (ay + s * aby)) * t.k;
      if (d < best.d) best = { d, route };
    }
  }
  return best.d <= ROUTE_HOVER_PX ? best.route : null;
}
svg.on('mousemove.routes', (ev) => { const route = routeNear(ev); if (route) showTip(ev, route.html); })
  // Not when the click opened a council area's card: the card is the answer to that tap,
  // and on a phone a route's tooltip left over the map after it is the M-15 defect by
  // another door (found 2026-10-06: tapping Camden beside a route opened the card, then
  // this handler, which runs after the area's own, put the route's tip back on the map).
  // A tap near a route over water or open ground still explains it; a mouse still hovers.
  .on('click.routes', (ev) => {
    if (ev.target.closest?.('.boro')) return;
    const route = routeNear(ev);
    if (route) showTip(ev, route.html);
  })
  .on('mouseleave.routes', hideTip);

function boroughTipHtml(d) {
  const name = featureName(d);
  if (d.properties.planar) return `<b>${esc(name)}</b>${esc(d.properties.county)} County. Click for the nearest runway.`;
  const row = rowFor(name);
  const x = (state.extra[state.city] || {})[name] || {};
  const bits = [];
  if (row && row.score !== '') bits.push(`Sky Score ${esc(row.score)} of 10`);
  if (x.roadNoiseAboveWhoPct != null) bits.push(`${Math.round(x.roadNoiseAboveWhoPct)}% of addresses over WHO's road-noise guideline`);
  bits.push('Click for the council area\'s figures');
  return `<b>${esc(name)}</b>${bits.join('<br>')}`;
}
function showTip(ev, html) {
  const r = svg.node().getBoundingClientRect();
  showTipAt(ev.clientX - r.left, ev.clientY - r.top, html);
}
function showTipAt(x, y, html) {
  if (!tip) return;
  const r = svg.node().getBoundingClientRect();
  tip.innerHTML = html;
  tip.style.display = 'block';
  tip.style.left = `${Math.max(0, Math.min(x + 14, r.width - 270))}px`;
  tip.style.top = `${Math.max(0, Math.min(y + 14, r.height - 80))}px`;
}
// Every hide also CANCELS a tooltip still waiting to appear. A council area's focus
// handler awaits bringIntoView() before it shows its tip, so a hide that lands during
// that wait (a tap's card opening, M-15) would otherwise be undone when it wakes.
let tipEpoch = 0;
function hideTip() {
  tipEpoch++;
  if (tip) tip.style.display = 'none';
}

// A toggle for a layer the city does not have is disabled and says so, the way
// the live map's legend measures "(NO DATA)" from what the render produced.
function markLayerCoverage(layer, has) {
  const b = byId(`toggle-${layer}`);
  if (!b) return;
  b.disabled = !has;
  b.title = has ? '' : 'Not published for this city';
}

// ---- zoom: buttons on every device, drag with a mouse, ctrl+wheel; a finger
// scrolls the page, as it must on a phone whose hero is half the screen ----
function bindZoom(W, H) {
  if (!state.zoom) {
    state.zoom = d3.zoom().scaleExtent([1, ZOOM_MAX])
      .filter((ev) => (ev.type === 'wheel' ? ev.ctrlKey || ev.metaKey : ev.type.startsWith('touch') ? false : !ev.button))
      .on('zoom', (ev) => {
        state.k = ev.transform.k;
        svg.select('.view').attr('transform', ev.transform);
        applyScale();
        hideTip();
      })
      .on('end', drawStreets);
    svg.call(state.zoom).on('dblclick.zoom', null);
  }
  state.zoom.translateExtent([[0, 0], [W, H]]).extent([[0, 0], [W, H]]);
  const t = d3.zoomTransform(svg.node());
  svg.select('.view').attr('transform', t);
  state.k = t.k;
}
// Marks and labels keep their on-screen size whatever the zoom; strokes do the
// same through vector-effect in the CSS.
function applyScale() {
  const k = state.k || 1;
  svg.selectAll('.ap').attr('font-size', `${12 / k}px`);
  svg.selectAll('.ap-box').attr('width', 8 / k).attr('height', 8 / k).attr('transform', `translate(${4 - 4 / k} ${4 - 4 / k})`);
  svg.selectAll('.pin').attr('r', 4 / k);
  svg.selectAll('.pin-ring').attr('r', 9 / k);
  const reset = byId('zoom-reset');
  if (reset) reset.disabled = k === 1;
}
// A zoomed map cannot be dragged by a finger (a finger scrolls the page, which
// a phone whose hero is half the screen needs) or by a key, so the map moves to
// the council area instead (audit 2026-10-05 M-16, WCAG 2.5.7: 13 of London's
// 33 were off the box after three zoom-ins at 390 wide). Tabbing to an area off
// the box brings it in; opening one centres it, so tapping an area at the edge
// is how a finger moves the map. Resolves when the map has stopped moving.
function bringIntoView(el, { centre = false } = {}) {
  if (!state.zoom || !el) return Promise.resolve();
  const t = d3.zoomTransform(svg.node());
  if (t.k <= 1) return Promise.resolve();
  const [W, H] = size();
  // On a wide screen the floating panel covers the left of the map: aim beside it.
  const wide = !window.matchMedia(STACKED).matches;
  const inset = wide && !inIntro() && document.body.dataset.mapInset ? JSON.parse(document.body.dataset.mapInset) : { left: 0, top: 0, right: 0, bottom: 0 };
  const box = { x0: inset.left, y0: inset.top, x1: W - inset.right, y1: H - inset.bottom };
  const r = el.getBBox();
  const cx = r.x + r.width / 2;
  const cy = r.y + r.height / 2;
  const [sx, sy] = t.apply([cx, cy]);
  if (!centre && sx >= box.x0 && sx <= box.x1 && sy >= box.y0 && sy <= box.y1) return Promise.resolve();
  return svg.transition().duration(250)
    .call(state.zoom.translateTo, cx, cy, [(box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2])
    .end().catch(() => {});
}
function zoomBy(f) {
  if (!state.zoom) return;
  svg.transition().duration(250).call(state.zoom.scaleBy, f);
}

function bindControls() {
  byId('zoom-in')?.addEventListener('click', () => zoomBy(ZOOM_STEP));
  byId('zoom-out')?.addEventListener('click', () => zoomBy(1 / ZOOM_STEP));
  byId('zoom-reset')?.addEventListener('click', () => svg.transition().duration(250).call(state.zoom.transform, d3.zoomIdentity));
  for (const layer of ['noise', 'lines']) {
    const b = byId(`toggle-${layer}`);
    if (!b) continue;
    b.setAttribute('aria-pressed', String(state.layers[layer]));
    b.addEventListener('click', () => {
      state.layers[layer] = !state.layers[layer];
      b.setAttribute('aria-pressed', String(state.layers[layer]));
      svg.select(layer === 'noise' ? '#noise-image' : '.lines').style('display', state.layers[layer] ? null : 'none');
    });
  }
  byId('toggle-streets')?.addEventListener('click', () => {
    state.layers.streets = !state.layers.streets;
    drawStreets();
  });
  byId('borough-close')?.addEventListener('click', () => closeBorough(true));
  // Escape closes the card and puts focus back where the card came from: the
  // council area that opened it, or the search box. It closed the card and
  // left focus on <body>, so a keyboard user restarted from the header
  // (audit 2026-10-05 M-17). Close (the button) keeps its tested rule: the
  // search box.
  document.addEventListener('keydown', (ev) => {
    if (ev.key !== 'Escape') return;
    hideTip();
    const card = byId('borough');
    const wasOpen = card?.classList.contains('is-open');
    const inCard = card?.contains(document.activeElement);
    closeBorough(false);
    if (wasOpen && (inCard || document.activeElement === document.body)) {
      (state.opener?.isConnected ? state.opener : byId('pc'))?.focus();
    }
  });
  window.addEventListener('resize', () => { if (state.boroughs) draw(state.pin); });
}

// ---- the council-area card: the open data CSV's row for the borough ----
const COMPONENTS = [['quiet', 'Quiet skies'], ['afford', 'Affordability'], ['growth', 'Growth'], ['live', 'Liveability'], ['env', 'Environment']];
// The facts under the score, in the order they are read. Each is a label, the
// CSV column, and how to print it; a blank cell prints as "not published"
// rather than as a number.
const CARD_FACTS = [
  ['Average price', 'avg_price_gbp', (v, r) => `£${Number(v).toLocaleString('en-GB')} (${r.price_vintage})`],
  // New York's rows (scripts/build_nyc_front.py) carry dollars, not pounds. A row LACKING a
  // column skips its line (every CSV row has all the UK columns; New York's have only what
  // the API publishes there); a BLANK one still says "not published".
  ['Average price', 'avg_price_usd', (v) => `$${Number(v).toLocaleString('en-US')} (curated borough median)`],
  ['Crime', 'crime_per_1000', (v) => `${v} offences per 1,000 people a year`],
  ['Road noise', 'road_noise_above_who_pct', (v) => `${v}% of addresses over the WHO guideline (53 dB)`],
  // The ratio is the WORSE of the two pollutants, so it is claimed for neither; some rows hold it without the concentrations.
  ['Air quality', 'air_quality_who_ratio', (v, r) => `${v}× the WHO guideline, on the worse of NO₂${ugm3(r.no2_ugm3)} and fine particles${ugm3(r.pm25_ugm3)}`],
  ['Flood risk', 'flood_medium_or_high_pct', (v) => `${v}% of addresses at medium or high risk`],
  ['Rail or tram', 'rail_within_800m_pct', (v) => `${v}% of addresses within 800 m of a station`],
];

function selectBorough(name, opts = {}) {
  const f = state.boroughs?.features.find((x) => norm(featureName(x)) === norm(name));
  const row = rowFor(name);
  if (!f && !row) return false;
  leaveIntro();
  state.selected = f ? featureName(f) : row.borough;
  svg.selectAll('.boro').classed('is-selected', (d) => featureName(d) === state.selected);
  // On a zoomed map, the area opened moves to the middle (M-16).
  bringIntoView(svg.selectAll('.boro').filter((d) => featureName(d) === state.selected).node(), { centre: true });
  byId('answer')?.classList.remove('is-open');
  // A ZIP search opens its city's card WITH the ZIP's pin; any other way in, the pin's answer has closed.
  if (!opts.zip) clearPin();
  // The tooltip goes with the tap that opened the card: it was left on the map,
  // 260x105 px, until the next tap (audit 2026-10-05 M-15).
  hideTip();
  const card = byId('borough');
  if (!card) return true;
  // Where Escape returns focus to (M-17): whatever had it, unless that was nothing.
  state.opener = document.activeElement !== document.body ? document.activeElement : null;
  openCard(f?.properties.planar ? placeCardHtml(f, opts.zip) : boroughCardHtml(row || { borough: name, city: state.city }, f));
  setQuery(opts.zip ? { city: state.city, postcode: opts.zip.code } : { city: row ? row.city : state.city, borough: state.selected });
  if (opts.scroll && window.matchMedia(STACKED).matches) card.scrollIntoView({ behavior: 'smooth', block: 'start' });
  if (opts.focus) card.querySelector('h2')?.focus();
  return true;
}
function openCard(html) {
  const card = byId('borough');
  if (!card) return;
  card.innerHTML = html;
  card.classList.add('is-open');
  panelState();
  card.querySelector('#borough-close')?.addEventListener('click', () => closeBorough(true));
}
// The pin marks the postcode whose answer is open. When that answer closes the
// pin goes with it, or the next answer (a postcode no city covers draws none of
// its own) is read against the last search's spot.
function clearPin() {
  state.pin = null;
  svg.selectAll('.pin, .pin-ring').remove();
}
function closeBorough(refocus) {
  const card = byId('borough');
  if (!card?.classList.contains('is-open')) return;
  card.classList.remove('is-open');
  panelState();
  state.selected = null;
  svg.selectAll('.boro').classed('is-selected', false);
  setQuery({ city: state.city });
  if (refocus) byId('pc')?.focus();
}
// Once there is a result the question makes way for it: the panel's heading
// shrinks and the lead and examples hide, so the answer stays on one screen
// (the measured reason v2 was chosen).
function panelState() {
  const panel = byId('answer')?.closest('.panel') || byId('borough')?.closest('.panel');
  if (!panel) return;
  panel.classList.toggle('has-result', Boolean(byId('answer')?.classList.contains('is-open') || byId('borough')?.classList.contains('is-open')));
}
const closeButton = '<button type="button" id="borough-close" class="close" aria-label="Close">&times;</button>';
function boroughCardHtml(row, f) {
  const cityName = row.city_name || CITY_NAME[row.city] || '';
  const onMap = Boolean(f);
  const bars = COMPONENTS.map(([k, label]) => {
    const v = fmt1(row[k]);
    return v == null
      ? `<div class="row"><span>${label}</span><span class="bar"></span><span class="val">not scored</span></div>`
      : `<div class="row"><span>${label}</span><span class="bar"><i style="width:${Number(v) * 10}%"></i></span><span class="val">${v} / 10</span></div>`;
  }).join('');
  const facts = CARD_FACTS.filter(([, col]) => col in row).map(([label, col, print]) => {
    const v = row[col];
    return `<div><dt>${label}</dt><dd>${v === '' || v == null ? 'not published for this area' : esc(print(v, row))}</dd></div>`;
  }).join('');
  const score = fmt1(row.score);
  const links = [
    row.ons_code ? `<a href="/area/${esc(row.city)}/${slug(row.borough)}/">Full scorecard</a>` : row.area_page ? `<a href="${esc(row.area_page)}">Full scorecard</a>` : '',
    onMap ? `<a href="${MAP_PATH}?city=${esc(row.city)}&amp;borough=${encodeURIComponent(row.borough)}">Open on the full map</a>` : '',
  ].filter(Boolean).join(' &middot; ');
  return `${closeButton}
    <h2 tabindex="-1">${esc(row.borough)}</h2>
    <p class="where">${row.city === 'nyc' ? 'Borough of' : 'Council area in'} ${esc(cityName)}${onMap ? '' : '. Not on the map yet: figures only'}.</p>
    ${score == null ? '<p class="score"><span>Not scored: too few inputs</span></p>' : `<p class="score"><strong>${score}</strong><span>Sky Score out of 10, balanced weighting, method ${esc(row.methodology_version)}</span></p>`}
    <div class="rows">${bars}</div>
    <dl class="facts">${facts}</dl>
    ${row.note ? `<p class="where">${esc(row.note)}</p>` : ''}
    <p class="more">${links}</p>`;
}
function placeCardHtml(f, zip) {
  const name = featureName(f);
  const ring = mainRing(f);
  const lat = d3.mean(ring, (p) => p[1]), lon = d3.mean(ring, (p) => p[0]);
  const near = nearestRunway(state.usProc, lat, lon);
  return `${closeButton}
    <h2 tabindex="-1">${esc(name)}</h2>
    <p class="where">${esc(f.properties.county)} County, California. Not scored: the Bay Area page shows where the routes are, not a score.</p>
    <dl class="facts">${zip ? zipFactsHtml(zip) : airfieldFactHtml(lat, lon, 'the city centre')}<div><dt>Nearest of SFO, OAK and SJC</dt><dd>${near ? esc(`${near.name} ${near.rwy}, ${km(near.dist)} to the ${near.dir} of the city centre`) : `none within ${AIRPORT_SCOPE_KM} km`}</dd></div></dl>
    <p class="more"><a href="/bay-area/">The Bay Area page</a></p>`;
}
// The routes on the map are SFO's, OAK's and SJC's, but the FAA holds 23 more
// airfields round the bay, and a card that named only the three told Livermore
// "none within 30 km" with its own airport 5.5 km away (audit 2026-10-05 I-2).
// The list is the one the Bay Area page reads: FAA airport records, any size.
// Airport reference points, so the distance is to the airfield, not a runway.
const FAA_WORDS = { Muni: 'Municipal', Exec: 'Executive', Intl: 'International', Fld: 'Field', Rgnl: 'Regional' };
// As airfield_name() in scripts/build_bay_area_page.py: the FAA record's name
// field is 30 characters, so a name that fills it ends in a fragment.
function airfieldName(raw) {
  const words = raw.toLowerCase().replace(/\b[a-z]/g, (c) => c.toUpperCase()).split(/\s+/);
  if (raw.length >= 30) words.pop();
  return words.map((w) => FAA_WORDS[w] || (w === 'Of' || w === 'The' ? w.toLowerCase() : w)).join(' ');
}
function nearestAirfield(lat, lon) {
  const fields = state.usPlaces?.airfields;
  if (!fields?.length) return null;
  const pl = plane(lat, lon);
  const best = d3.least(fields.map((a) => ({ a, v: pl.xy(...a.ref) })), (x) => Math.hypot(...x.v));
  const dist = Math.hypot(...best.v);
  return dist > AIRPORT_SCOPE_KM ? null : { name: airfieldName(best.a.name), ident: best.a.ident, dist, dir: compass(best.v) };
}
function airfieldFactHtml(lat, lon, from) {
  const a = nearestAirfield(lat, lon);
  const text = a ? `${a.name} (${a.ident}), ${km(a.dist)} to the ${a.dir} of ${from}` : `none within ${AIRPORT_SCOPE_KM} km`;
  return `<div><dt>Nearest airfield</dt><dd>${esc(text)} <small>any size, FAA records</small></dd></div>`;
}
// A ZIP is a Census ZIP area, and its share of land in the city is what keeps
// the city's name honest: 94301 is Palo Alto, 95014 is 44% Cupertino and
// mostly empty hills. The words follow the share (scripts/build_bayarea_zips.py).
function zipShareText(zip) {
  const pct = Math.round(zip.share * 100);
  if (zip.share >= 0.9) return `In ${zip.place}.`;
  if (zip.share >= 0.5) return `Mostly in ${zip.place}: ${pct}% of the ZIP area's land.`;
  return `${pct}% of the ZIP area's land is in ${zip.place}; the rest is in other cities or in none.`;
}
function zipFactsHtml(zip) {
  return `<div><dt>ZIP ${esc(zip.code)}</dt><dd>${esc(zip.place ? zipShareText(zip) : 'In no city.')} <small>US Census, 2020</small></dd></div>
    <div><dt>At its centre</dt><dd>${esc(routesText(state.usProc, zip.lat, zip.lon))}</dd></div>
    ${airfieldFactHtml(zip.lat, zip.lon, 'its centre')}`;
}
// A ZIP area that lies in no city we hold still has a centre and a nearest runway.
function zipCardHtml(zip) {
  return `${closeButton}
    <h2 tabindex="-1">ZIP ${esc(zip.code)}</h2>
    <p class="where">${esc(zip.county)} County, California. Not scored.</p>
    <dl class="facts">${zipFactsHtml(zip)}</dl>
    <p class="more"><a href="/bay-area/">The Bay Area page</a></p>`;
}

// ---- runway geometry for a point: the report generators' own arithmetic ----
function nearestRunway(proc, lat, lon) {
  const pl = plane(lat, lon);
  const near = routesNear(proc, pl, AIRPORT_SCOPE_KM);
  const ap = near.scope[0];
  if (!ap) return null;
  // The nearest END of the nearest strip names the runway; the strip distance is the figure.
  let best = null;
  for (const [rwy, r] of Object.entries(proc.airports[ap.code].runways)) {
    const d = Math.hypot(...pl.xy(...r.thr));
    if (!best || d < best.d) best = { rwy, d };
  }
  return { code: ap.code, name: AIRPORT_NAME[ap.code] || proc.airports[ap.code].name || ap.code, rwy: best.rwy, dist: ap.dist, dir: compass(ap.q) };
}
// Plain text: its one caller sets textContent, so escaping here would print the entities.
function routesText(proc, lat, lon) {
  const pl = plane(lat, lon);
  const near = routesNear(proc, pl, AIRPORT_SCOPE_KM);
  const ap = near.scope[0];
  // "On the map", not "nearest runway": the record holds the airports whose
  // routes are drawn, and a smaller airfield can be nearer (audit 2026-10-05 I-2).
  if (!ap) return `No airport on the map within ${AIRPORT_SCOPE_KM} km.`;
  const name = AIRPORT_NAME[ap.code] || ap.code;
  const under = near.finals.filter((x) => x.beside && x.dist <= UNDER_LINE_KM).sort((a, b) => a.dist - b.dist)[0];
  const nearestFinal = near.finals.sort((a, b) => a.dist - b.dist)[0];
  const parts = [`Nearest airport on the map: ${name}, ${km(ap.dist)} to the ${compass(ap.q)}.`];
  if (under) {
    parts.push(`Under the ${AIRPORT_NAME[under.code] || under.code} ${under.rwy} final approach, ${under.dist < 0.05 ? 'on the centreline' : `${km(under.dist)} from the centreline`}, aircraft at about ${(Math.round(under.heightFt / 100) * 100).toLocaleString('en-GB')} ft here.`);
  } else if (nearestFinal && nearestFinal.dist <= AIRPORT_SCOPE_KM) {
    parts.push(`Nearest published approach: ${AIRPORT_NAME[nearestFinal.code] || nearestFinal.code} ${nearestFinal.rwy}, ${km(nearestFinal.dist)} to the ${compass(nearestFinal.q)}.`);
  }
  // Say which routes the data lacks, as the street report does, so an
  // undrawn route never reads as one that is not there (audit 2026-10-05 M-7).
  const gap = {
    none: 'Departure routes: none published for this airport.',
    conventional: `Departure routes: ${name}'s are published only as charts and are not drawn here.`,
    'not-drawn': `Routes: ${name}'s are not drawn here.`,
  }[ap.method];
  if (gap) parts.push(gap);
  return parts.join(' ');
}

// ---- the search: a postcode (postcodes.io, then the live environment endpoint) or a place name ----
const form = byId('check');
const status = byId('status');
const answer = byId('answer');
const say = (s) => { if (status) status.textContent = s; };
document.querySelectorAll('.try button').forEach((b) => b.addEventListener('click', () => { const i = byId('pc'); if (i) i.value = b.dataset.pc; form?.requestSubmit(); }));
form?.addEventListener('submit', (ev) => { ev.preventDefault(); search(byId('pc')?.value || ''); });

async function search(raw) {
  const text = raw.trim();
  if (!text) return;
  leaveIntro();
  answer?.classList.remove('is-open');
  clearPin();
  // A place name first: a borough, a Bay Area city or a city region.
  const row = rowFor(text);
  if (row) {
    say('');
    if (CITY_NAME[row.city] && row.city !== state.city) await show(row.city);
    selectBorough(row.borough, { scroll: true });
    return;
  }
  // No Bay Area city has a digit in its name, so a postcode or ZIP never waits
  // on the 257 KB Bay Area file (audit 2026-10-05 M-12).
  const place = state.usPlaces?.places.find((p) => p.kind !== 'cdp' && norm(p.name) === norm(text))
    || (/\d/.test(text) ? null : await bayAreaPlace(text));
  if (place) {
    say('');
    if (state.city !== 'bayarea') await show('bayarea');
    selectBorough(place.name, { scroll: true });
    return;
  }
  const cityKey = CITIES.find(([k, n]) => norm(n) === norm(text) || k === norm(text).replace(/\s/g, ''))?.[0];
  if (cityKey) { say(''); closeBorough(false); await show(cityKey); setQuery({ city: cityKey }); return; }

  const pc = text.toUpperCase().replace(/[^A-Z0-9 ]/g, '');
  if (/^\d{5}$/.test(pc)) { await searchZip(pc); return; }
  say('Looking it up...');
  closeBorough(false);
  try {
    const geo = await (await fetch(`https://api.postcodes.io/postcodes/${encodeURIComponent(pc.replace(/\s+/g, ''))}`)).json();
    if (!geo.result) { say('That postcode was not found, and no place on the map has that name.'); return; }
    const { latitude: lat, longitude: lon, admin_district: district } = geo.result;
    const city = cityOf(district);
    // A postcode no city covers gets no pin: a pin on whichever city is on
    // screen is how the live site once told a Norwich reader about Stansted.
    if (city && city !== state.city) await show(city, { lat, lon }); else if (city) draw({ lat, lon });
    const env = await (await fetch(`${ENV}?lat=${lat}&lon=${lon}`)).json();
    if (!env.environment) { say(env.error || 'No figures for that spot.'); return; }
    // A success is announced too: the status line is the page's live region,
    // and it went from "Looking it up..." to empty, so a screen-reader user
    // heard nothing when the figures arrived (audit 2026-10-05 M-14).
    say(city ? `Showing the figures for ${geo.result.postcode}.` : `${geo.result.postcode} is outside the cities on the map. Here are the figures we hold for it.`);
    render(geo.result.postcode, district, city, env.environment, lat, lon);
    setQuery({ city: city || state.city, postcode: geo.result.postcode });
  } catch {
    say('Could not reach the data just now. Try again in a moment.');
  }
}
// ---- a US ZIP: the Census's ZIP areas for the four Bay Area counties ----
// The table is derived by scripts/build_bayarea_zips.py. A ZIP outside it gets
// a sentence and nothing else: no pin, and the map stays where it is, because
// a point drawn on whichever city is on screen is how the live site once told
// a Norwich reader about Stansted.
async function searchZip(code) {
  closeBorough(false);
  if (!state.usZips) {
    try {
      state.usZips = (await d3.json('/data/us-bayarea-zips.json')).zips;
    } catch {
      say('Could not load the ZIP list just now. Try again in a moment.');
      return;
    }
  }
  const found = state.usZips[code];
  if (!found) {
    say(`${code} is not a ZIP in the four Bay Area counties on the map (San Francisco, San Mateo, Santa Clara and Alameda). New York's ZIPs are on the full map.`);
    return;
  }
  const zip = { code, ...found };
  say('');
  const pin = { lat: zip.lat, lon: zip.lon };
  if (state.city !== 'bayarea') await show('bayarea', pin); else draw(pin);
  if (zip.place && selectBorough(zip.place, { scroll: true, zip })) return;
  // No city holds any of it (or the city is one the map does not draw): the ZIP's own card.
  state.selected = null;
  byId('answer')?.classList.remove('is-open');
  openCard(zipCardHtml(zip));
  setQuery({ city: 'bayarea', postcode: code });
}
let bayAreaNames = null;
async function bayAreaPlace(text) {
  if (state.usPlaces) return null;
  // Only fetch the Bay Area file for a name that found no UK match, and once.
  try {
    bayAreaNames ??= d3.json(US.bayarea.places);
    const places = await bayAreaNames;
    return places.places.find((p) => p.kind !== 'cdp' && norm(p.name) === norm(text)) || null;
  } catch {
    bayAreaNames = null; // a failed fetch is retried on the next search
    return null;
  }
}

// postcodes.io's district name -> the map city holding it, or null. Exported
// so tests/preview-home.mjs can hold it to every real postcodes.io spelling.
export function cityOf(district) {
  for (const [key, boroughs] of Object.entries(state.extra)) {
    if (Object.keys(boroughs).some((b) => norm(b) === norm(district))) return isMapCity(key) ? key : null;
  }
  // The open-data CSV names a council area as postcodes.io does where
  // borough-extra.json shortens it: "Barking and Dagenham" is held there as
  // "Barking", so every IG11 postcode was told it was off the map (audit
  // 2026-10-05 I-1).
  const row = rowFor(district);
  return row && isMapCity(row.city) ? row.city : null;
}

function render(postcode, district, city, e, lat, lon) {
  const title = byId('ans-title'), where = byId('ans-where');
  if (title) title.textContent = postcode;
  if (where) where.textContent = district + (city ? '' : ' (not yet on the map: figures only)');
  const bar = (v, who) => { const max = who * 2; return `<span class="bar"><i style="width:${Math.min(100, (v / max) * 100)}%"></i><b style="left:${(who / max) * 100}%" title="WHO guideline ${who}"></b></span>`; };
  const rows = [];
  // Aircraft: measured, or the site's own estimate from the published routes,
  // or outside every city - never the "outside" estimate, which is a maximum
  // taken from nothing nearby and would read as a quiet verdict.
  if (e.aircraftNoiseLdenDb != null) {
    rows.push(`<div class="row"><span>Aircraft noise</span>${bar(e.aircraftNoiseLdenDb, e.aircraftNoiseWhoGuidelineDb)}<span class="val">${e.aircraftNoiseLdenDb} dB<small>WHO ${e.aircraftNoiseWhoGuidelineDb} &middot; DEFRA, measured</small></span></div>`);
  } else if (e.aircraftQuietCoverage === 'outside') {
    rows.push('<div class="row"><span>Aircraft noise</span><span class="bar"></span><span class="val">not covered<small>outside the cities we map</small></span></div>');
  } else if (e.aircraftQuietEstimated != null) {
    // Among measurements a longer bar is worse, so the quiet score is turned
    // round (10 minus it) and named for the noise, as the extension prints it.
    const noise = 10 - e.aircraftQuietEstimated;
    rows.push(`<div class="row"><span>Aircraft noise</span><span class="bar"><i style="width:${noise * 10}%"></i></span><span class="val">${noise.toFixed(1)} / 10<small>estimate from the routes, not measured</small></span></div>`);
  } else {
    rows.push('<div class="row"><span>Aircraft noise</span><span class="bar"></span><span class="val">not measured</span></div>');
  }
  if (e.roadNoiseLdenDb != null) {
    rows.push(`<div class="row"><span>Road noise</span>${bar(e.roadNoiseLdenDb, e.roadNoiseWhoGuidelineDb)}<span class="val">${e.roadNoiseLdenDb} dB<small>WHO ${e.roadNoiseWhoGuidelineDb} &middot; DEFRA</small></span></div>`);
  } else if (e.roadNoiseBelowDb != null) {
    // DEFRA surveyed the ground and found it under its lowest mapped band: quiet, not missing.
    rows.push(`<div class="row"><span>Road noise</span><span class="bar"></span><span class="val">under ${e.roadNoiseBelowDb} dB<small>surveyed, below the lowest band</small></span></div>`);
  } else {
    rows.push('<div class="row"><span>Road noise</span><span class="bar"></span><span class="val"><small>not held here</small></span></div>');
  }
  for (const [label, v, who] of [['Nitrogen dioxide', e.no2AnnualMeanUgm3, e.no2WhoGuidelineUgm3], ['Fine particles', e.pm25AnnualMeanUgm3, e.pm25WhoGuidelineUgm3]]) {
    rows.push(v == null
      ? `<div class="row"><span>${label}</span><span class="bar"></span><span class="val">not measured</span></div>`
      : `<div class="row"><span>${label}</span>${bar(v, who)}<span class="val">${v} µg/m³<small>WHO ${who} &middot; DEFRA</small></span></div>`);
  }
  const rowsEl = byId('ans-rows');
  if (rowsEl) rowsEl.innerHTML = rows.join('');

  const routes = byId('ans-routes');
  if (routes) routes.textContent = city && state.proc ? routesText(state.proc, lat, lon) : '';
  const area = byId('ans-area');
  if (area) {
    const row = city ? rowFor(district) : null;
    area.innerHTML = row
      ? `Council area: <b>${esc(row.borough)}</b>${row.score !== '' ? `, Sky Score ${esc(row.score)}` : ''}${row.flood_medium_or_high_pct !== '' ? `, ${esc(row.flood_medium_or_high_pct)}% of addresses at medium or high flood risk` : ''}. <button type="button" class="linkish" id="ans-open-area">Its figures</button>`
      : '';
    area.querySelector('#ans-open-area')?.addEventListener('click', () => selectBorough(row.borough, { scroll: true, focus: true }));
  }
  const link = byId('ans-link');
  if (link) {
    link.href = city ? `${MAP_PATH}?city=${city}&postcode=${encodeURIComponent(postcode)}` : MAP_PATH;
    // "See the full picture on the map" for a postcode just called not on the
    // map contradicted itself (audit 2026-10-05 M-18): no map, no link.
    const more = link.closest('p');
    if (more) more.hidden = !city;
  }
  answer?.classList.add('is-open');
  panelState();
  // Two layout hooks: a panel that only exists once there is an answer (v2b),
  // and a map to bring into view when the answer lands on it (v3b).
  const opens = document.body.dataset.answerOpens;
  if (opens) document.querySelector(opens)?.classList.add('is-open');
  const scrollTo = document.body.dataset.scrollTo;
  if (scrollTo) document.querySelector(scrollTo)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

load().catch((e) => say(`The map could not load: ${e.message}`));
