/* The engine behind the homepage mockups (design/homepage-v*.html): the live
   map, the city chips and the working postcode search. Each mockup is a
   different layout round the same ids (#map, #chips, #check, #pc, #status,
   #answer and its parts, #ramp). MOCKUP CODE, not shipped. */
// ---- what the page knows: the same data files the live site ships ----
const DEFRA = ['#B8D6D1', '#CEE4CC', '#E2F2BF', '#F3C683', '#E87E4D', '#CD463E', '#A11A4D', '#75085C', '#430A4A'];
document.getElementById('ramp').innerHTML = DEFRA.map((c) => `<b style="background:${c}"></b>`).join('');
const CITIES = [
  ['london', 'London'], ['manchester', 'Greater Manchester'], ['westmidlands', 'West Midlands'],
  ['westyorkshire', 'West Yorkshire'], ['southyorkshire', 'South Yorkshire'], ['merseyside', 'Merseyside'],
  ['tyneandwear', 'Tyne and Wear'], ['bristol', 'Bristol'], ['leicester', 'Leicester'], ['teesside', 'Teesside'],
  ['bayarea', 'San Francisco Bay Area'],
];
// The Bay Area is not a city on the live map yet: its outlines are the Census
// places the /bay-area/ page is built from, its routes the FAA record, its
// noise picture the one that page serves. Drawn here to show what "on the
// map" would look like.
const US = { bayarea: { places: '/data/us-bayarea-places.json', proc: '/data/us-flight-procedures.json', noiseDir: '/bay-area/' } };
// London's picture is the one file not described by aircraft-noise-rasters.json.
const LONDON_PNG = { png: '/data/aircraft-noise-london-lden.png', bbox: { minLon: -0.85, maxLon: 0.4, minLat: 51.1, maxLat: 51.78 } };
const ENV = 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/environment';
const FT_KM = 0.0003048;

const svg = d3.select('#map');
const tip = document.getElementById('tip');
const state = { city: null, boroughs: null, extra: null, proc: null, rasters: null, projection: null, usProc: null, usNoise: null };

const dest = (lat, lon, brg, km) => {
  const R = 6371.0088, d = km / R, b = (brg * Math.PI) / 180, la = (lat * Math.PI) / 180, lo = (lon * Math.PI) / 180;
  const la2 = Math.asin(Math.sin(la) * Math.cos(d) + Math.cos(la) * Math.sin(d) * Math.cos(b));
  const lo2 = lo + Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(la), Math.cos(d) - Math.sin(la) * Math.sin(la2));
  return [(lo2 * 180) / Math.PI, (la2 * 180) / Math.PI];
};
const size = () => { const r = svg.node().getBoundingClientRect(); return [Math.max(320, r.width), Math.max(300, r.height)]; };

async function load() {
  const [extra, proc, rasters] = await Promise.all([
    d3.json('/data/borough-extra.json'), d3.json('/data/flight-procedures.json'), d3.json('/data/aircraft-noise-rasters.json'),
  ]);
  Object.assign(state, { extra, proc, rasters });
  renderChips();
  await show('london');
}

function renderChips() {
  const box = document.getElementById('chips');
  box.innerHTML = '';
  for (const [key, name] of CITIES) {
    const b = document.createElement('button');
    b.type = 'button'; b.textContent = name; b.dataset.city = key; b.setAttribute('aria-pressed', 'false');
    b.addEventListener('click', () => show(key));
    box.append(b);
  }
  for (const [href, name] of [['/?city=nyc', 'New York']]) {
    const a = document.createElement('a'); a.href = href; a.textContent = name; box.append(a);
  }
}

async function loadBayArea() {
  const [places, proc] = await Promise.all([d3.json(US.bayarea.places), d3.json(US.bayarea.proc)]);
  state.usProc = proc;
  // The picture's frame is in web-mercator pixels at the zoom it was fetched at.
  const [x0, y0, x1, y1] = places.frame.px;
  const n = 256 * 2 ** places.frame.zoom;
  const lonlat = (px, py) => [(px / n) * 360 - 180, (Math.atan(Math.sinh(Math.PI * (1 - (2 * py) / n))) * 180) / Math.PI];
  const [minLon, maxLat] = lonlat(x0, y0);
  const [maxLon, minLat] = lonlat(x1, y1);
  state.usNoise = { png: US.bayarea.noiseDir + places.noise.file, bbox: { minLon, maxLon, minLat, maxLat } };
  // Shapefile rings wind the opposite way to what d3's spherical geometry
  // expects for holes, so these are drawn on the plane (see planarPath).
  const features = places.places
    .filter((p) => p.kind !== 'cdp')
    .map((p) => ({ type: 'Feature', properties: { name: p.name, planar: true }, geometry: { type: 'MultiPolygon', coordinates: p.rings.map((r) => [r]) } }));
  return { type: 'FeatureCollection', features };
}

function fitTarget(fc) {
  // A plain bounding box, wound clockwise, which d3 fits without reading each ring.
  // Each place's LARGEST ring only: San Francisco's outline includes the Farallon Islands, 45 km out to sea.
  const area = (ring) => Math.abs(d3.sum(ring, (p, i) => { const q = ring[(i + 1) % ring.length]; return p[0] * q[1] - q[0] * p[1]; }));
  const pts = fc.features.flatMap((f) => d3.greatest(f.geometry.coordinates, (poly) => area(poly[0]))[0]);
  const lons = pts.map((p) => p[0]), lats = pts.map((p) => p[1]);
  const a = Math.min(...lons), b = Math.max(...lons), c = Math.min(...lats), d = Math.max(...lats);
  return { type: 'Polygon', coordinates: [[[a, c], [a, d], [b, d], [b, c], [a, c]]] };
}

async function show(key, pin) {
  state.city = key;
  state.boroughs = key === 'bayarea' ? await loadBayArea() : await d3.json(`/data/${key}-boroughs.json`);
  document.querySelectorAll('#chips button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.city === key)));
  draw(pin);
}

function draw(pin) {
  const [W, H] = size();
  svg.attr('viewBox', `0 0 ${W} ${H}`).selectAll('*').remove();
  // Each layout says how much of the map a floating panel covers, in pixels at desktop width.
  const inset = document.body.dataset.mapInset ? JSON.parse(document.body.dataset.mapInset) : { left: 0, top: 0, right: 0, bottom: 0 };
  const wide = W > 760;
  const planar = state.boroughs.features.some((f) => f.properties.planar);
  const projection = d3.geoMercator().fitExtent(
    [[(wide ? inset.left : 0) + 24, (wide ? inset.top : 0) + 24], [W - (wide ? inset.right : 0) - 24, H - (wide ? inset.bottom : 0) - 64]],
    planar ? fitTarget(state.boroughs) : state.boroughs,
  );
  state.projection = projection;
  const geoPath = d3.geoPath(projection);
  const planarPath = (f) =>
    f.geometry.coordinates
      .map((poly) => poly.map((ring) => 'M' + ring.map((pt) => projection(pt).map((v) => v.toFixed(1)).join(' ')).join('L') + 'Z').join(''))
      .join('');
  const path = (f) => (f.properties.planar ? planarPath(f) : geoPath(f));
  const extra = state.extra[state.city] || {};

  // The noise picture is cut to the city's outline: DEFRA's London export reaches Gatwick,
  // and a lobe floating beside the map reads as a mistake.
  svg.append('clipPath').attr('id', 'city-clip').selectAll('path').data(state.boroughs.features).join('path').attr('d', path);
  svg.append('g').selectAll('path').data(state.boroughs.features).join('path').attr('class', 'boro').attr('d', path).attr('fill-rule', 'evenodd')
    .on('mousemove', (ev, d) => {
      const name = d.properties.name || d.properties.NAME || '';
      const x = extra[name] || {};
      const bits = [];
      if (x.roadNoiseAboveWhoPct != null) bits.push(`${Math.round(x.roadNoiseAboveWhoPct)}% of addresses over WHO's road-noise guideline`);
      if (x.airQualityWhoRatio != null) bits.push(`NO2 at ${x.airQualityWhoRatio.toFixed(1)} times the WHO guideline`);
      tip.innerHTML = `<b>${name}</b>${bits.join('<br>')}`;
      tip.style.display = 'block';
      const r = svg.node().getBoundingClientRect();
      tip.style.left = `${Math.min(ev.clientX - r.left + 14, r.width - 270)}px`;
      tip.style.top = `${ev.clientY - r.top + 14}px`;
    })
    .on('mouseleave', () => { tip.style.display = 'none'; })
    .on('click', (ev, d) => {
      svg.selectAll('.boro').classed('is-selected', false);
      d3.select(ev.currentTarget).classed('is-selected', true);
    });

  const raster = state.city === 'london' ? LONDON_PNG : state.city === 'bayarea' ? state.usNoise : state.rasters.cities[state.city];
  if (raster) {
    const [x0, y0] = projection([raster.bbox.minLon, raster.bbox.maxLat]);
    const [x1, y1] = projection([raster.bbox.maxLon, raster.bbox.minLat]);
    svg.append('image').attr('href', raster.png).attr('x', x0).attr('y', y0).attr('width', x1 - x0).attr('height', y1 - y0)
      .attr('preserveAspectRatio', 'none').style('mix-blend-mode', document.body.dataset.noiseBlend || 'multiply').attr('clip-path', 'url(#city-clip)').style('pointer-events', 'none');
  }
  const g = svg.append('g').style('pointer-events', 'none');
  const proc = state.city === 'bayarea' ? state.usProc : state.proc;
  for (const [code, ap] of Object.entries(proc.airports)) {
    if (!(ap.cities || []).includes(state.city)) continue;
    for (const r of Object.values(ap.runways)) {
      if (r.glide_deg == null || !r.thr) continue;
      const far = dest(r.thr[0], r.thr[1], r.true_brg + 180, (3000 * FT_KM) / Math.tan((r.glide_deg * Math.PI) / 180));
      const a = projection([r.thr[1], r.thr[0]]), b = projection(far);
      g.append('line').attr('class', 'final').attr('x1', a[0]).attr('y1', a[1]).attr('x2', b[0]).attr('y2', b[1]);
    }
    const thr = Object.values(ap.runways).map((r) => r.thr).filter(Boolean);
    if (thr.length) {
      const p = projection([d3.mean(thr, (t) => t[1]), d3.mean(thr, (t) => t[0])]);
      g.append('rect').attr('x', p[0] - 4).attr('y', p[1] - 4).attr('width', 8).attr('height', 8).attr('fill', '#f27d26').attr('stroke', '#141414');
      g.append('text').attr('class', 'ap').attr('x', p[0] + 8).attr('y', p[1] - 6).text(code);
    }
  }
  if (pin) {
    const [px, py] = projection([pin.lon, pin.lat]);
    g.append('circle').attr('class', 'pin-ring').attr('cx', px).attr('cy', py).attr('r', 9);
    g.append('circle').attr('class', 'pin').attr('cx', px).attr('cy', py).attr('r', 4);
  }
}

// ---- the search: postcodes.io, then the live environment endpoint ----
const form = document.getElementById('check');
const status = document.getElementById('status');
const answer = document.getElementById('answer');
document.querySelectorAll('.try button').forEach((b) => b.addEventListener('click', () => { document.getElementById('pc').value = b.dataset.pc; form.requestSubmit(); }));
form.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const pc = document.getElementById('pc').value.trim().toUpperCase().replace(/[^A-Z0-9 ]/g, '');
  if (!pc) return;
  if (/^\d{5}$/.test(pc)) {
    // A US ZIP: the live endpoint takes UK postcodes only, so the mockup shows the map instead.
    status.textContent = 'ZIP search is not built yet. Here is the Bay Area map.';
    answer.classList.remove('is-open');
    await show('bayarea');
    return;
  }
  status.textContent = 'Looking it up...';
  answer.classList.remove('is-open');
  try {
    const geo = await (await fetch(`https://api.postcodes.io/postcodes/${encodeURIComponent(pc.replace(/\s+/g, ''))}`)).json();
    if (!geo.result) { status.textContent = 'That postcode was not found.'; return; }
    const { latitude: lat, longitude: lon, admin_district: district } = geo.result;
    const city = cityOf(district);
    if (city && city !== state.city) await show(city, { lat, lon }); else draw({ lat, lon });
    const env = await (await fetch(`${ENV}?lat=${lat}&lon=${lon}`)).json();
    if (!env.environment) { status.textContent = env.error || 'No figures for that spot.'; return; }
    status.textContent = '';
    render(geo.result.postcode, district, city, env.environment);
  } catch (e) {
    status.textContent = 'Could not reach the data just now. Try again in a moment.';
  }
});

function cityOf(district) {
  const norm = (s) => String(s).toLowerCase().replace(/[.,]/g, '').replace(/\s+/g, ' ').replace(/^(.*), city of$/, 'city of $1');
  for (const [key, boroughs] of Object.entries(state.extra)) {
    if (Object.keys(boroughs).some((b) => norm(b) === norm(district))) return CITIES.some(([k]) => k === key) ? key : null;
  }
  return null;
}

function render(postcode, district, city, e) {
  document.getElementById('ans-title').textContent = postcode;
  document.getElementById('ans-where').textContent = district + (city ? '' : ' (not yet on the map: figures only)');
  const rows = [
    ['Aircraft noise', e.aircraftNoiseLdenDb, e.aircraftNoiseWhoGuidelineDb, 'dB', e.aircraftQuietCoverage === 'measured' ? 'DEFRA, measured' : 'estimate'],
    ['Road noise', e.roadNoiseLdenDb, e.roadNoiseWhoGuidelineDb, 'dB', 'DEFRA'],
    ['Nitrogen dioxide', e.no2AnnualMeanUgm3, e.no2WhoGuidelineUgm3, 'ug/m3', 'DEFRA'],
    ['Fine particles', e.pm25AnnualMeanUgm3, e.pm25WhoGuidelineUgm3, 'ug/m3', 'DEFRA'],
  ];
  document.getElementById('ans-rows').innerHTML = rows.map(([label, v, who, unit, src]) => {
    if (v == null && label === 'Aircraft noise' && e.aircraftQuiet != null) {
      // DEFRA measured nothing here, so the site's own estimate from the published routes, on its 0-10 scale.
      const pct = (1 - e.aircraftQuiet / 10) * 100;
      return `<div class="row"><span>Quiet skies</span><span class="bar"><i style="width:${pct}%"></i></span><span class="val">${e.aircraftQuiet.toFixed(1)} / 10<small>estimate from the routes</small></span></div>`;
    }
    if (v == null) return `<div class="row"><span>${label}</span><span class="bar"></span><span class="val">not measured</span></div>`;
    const max = who * 2, pct = Math.min(100, (v / max) * 100), whoPct = (who / max) * 100;
    return `<div class="row"><span>${label}</span><span class="bar"><i style="width:${pct}%"></i><b style="left:${whoPct}%" title="WHO guideline ${who}"></b></span><span class="val">${v} ${unit}<small>WHO ${who} &middot; ${src}</small></span></div>`;
  }).join('');
  document.getElementById('ans-link').href = city ? `/?city=${city}` : '/';
  answer.classList.add('is-open');
  // Two layout hooks: a panel that only exists once there is an answer (v2b),
  // and a map to bring into view when the answer lands on it (v3b).
  const opens = document.body.dataset.answerOpens;
  if (opens) document.querySelector(opens)?.classList.add('is-open');
  const scrollTo = document.body.dataset.scrollTo;
  if (scrollTo) document.querySelector(scrollTo)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

window.addEventListener('resize', () => { if (state.boroughs) draw(); });
load().catch((e) => { status.textContent = `The map could not load: ${e.message}`; });
