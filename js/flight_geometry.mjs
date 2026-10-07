/**
 * Where a point sits relative to the airports in data/flight-procedures.json.
 *
 * ONE HOLDER for two report generators (2026-10-02): address_noise_report.mjs
 * (one postcode, aircraft-led) and area_summary.mjs (several points, with an
 * optional aircraft column). Both need "how far is the runway" and "is this
 * under an approach line", and two copies of that arithmetic would drift the
 * way every mirrored pair in this repo has.
 *
 * It lives under js/ rather than scripts/ since 2026-10-03 because the new
 * front page (js/home-engine.mjs) is the THIRD consumer and runs in the
 * browser: it answers "nearest runway" and "under which approach, at what
 * height" for a searched postcode with this same arithmetic. No Node imports,
 * on purpose - the file is served as-is (web-deploy and preview-deploy both
 * upload it).
 *
 * Everything here is GEOMETRY FROM PUBLISHED POSITIONS: runway thresholds,
 * true bearings, glide angles and departure waypoints, as the UK AIP gives
 * them. Nothing in this file estimates loudness.
 */

// Mirrors build_flight_paths.py: a final is drawn from the threshold out to
// where the published glide path passes this height.
export const FINAL_TOP_FT = 3000;
export const FT_KM = 0.0003048;
export const ORIGIN = [0, 0];

export const rad = (d) => (d * Math.PI) / 180;

/** What each airport is called on a page. Labels, not data. */
export const AIRPORT_NAME = {
  LHR: 'Heathrow',
  LCY: 'London City',
  MAN: 'Manchester',
  BHX: 'Birmingham',
  LBA: 'Leeds Bradford',
  LPL: 'Liverpool',
  NCL: 'Newcastle',
  BRS: 'Bristol',
  EMA: 'East Midlands',
  CWL: 'Cardiff',
  MME: 'Teesside',
  NWI: 'Norwich',
  LGW: 'Gatwick',
  STN: 'Stansted',
  LTN: 'Luton',
  // New York's, drawn on the front page from the FAA record (2026-10-06), whose airport
  // records carry no name: without these the tooltips read the bare codes.
  JFK: 'JFK',
  LGA: 'LaGuardia',
  EWR: 'Newark',
  TEB: 'Teterboro',
};

/** A flat plane in km, centred on a point. Good to well under 1% across a city region. */
export function plane(lat0, lon0) {
  const kx = 111.32 * Math.cos(rad(lat0));
  const ky = 111.19;
  return { xy: (lat, lon) => [(lon - lon0) * kx, (lat - lat0) * ky] };
}
export const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
export const add = (a, b) => [a[0] + b[0], a[1] + b[1]];
export const mul = (a, s) => [a[0] * s, a[1] * s];
export const dot = (a, b) => a[0] * b[0] + a[1] * b[1];
export const len = (a) => Math.hypot(a[0], a[1]);
export const unit = (bearingDeg) => [Math.sin(rad(bearingDeg)), Math.cos(rad(bearingDeg))];

/** Nearest point on segment a-b to p, and its distance. */
export function closest(p, a, b) {
  const ab = sub(b, a);
  const t = Math.max(0, Math.min(1, dot(sub(p, a), ab) / (dot(ab, ab) || 1)));
  const q = add(a, mul(ab, t));
  return { d: len(sub(p, q)), q };
}
/** Eight-point compass name of a vector from the centre of the plane. */
export function compass(v) {
  const names = ['north', 'north-east', 'east', 'south-east', 'south', 'south-west', 'west', 'north-west'];
  const deg = (Math.atan2(v[0], v[1]) * 180) / Math.PI;
  return names[((Math.round(deg / 45) % 8) + 8) % 8];
}
export const towards = (bearingDeg) => compass(unit(bearingDeg));

/** 09L <-> 27R: the other end of the same strip. */
export function reciprocal(rwy) {
  const n = ((parseInt(rwy, 10) + 17) % 36) + 1;
  const side = { L: 'R', R: 'L', C: 'C' }[rwy.replace(/\d/g, '')] || '';
  return String(n).padStart(2, '0') + side;
}

/**
 * Every airport, final approach and departure route relative to the centre of
 * `pl`. `scope` is every airport whose runway lies within `scopeKm`, nearest
 * first, with what the record holds for it (`method`), so a caller can say
 * which routes the data lacks instead of implying they are not there.
 */
export function routesNear(proc, pl, scopeKm) {
  const finals = [];
  const departures = [];
  const airports = [];
  const scope = [];
  for (const [code, ap] of Object.entries(proc.airports)) {
    const thresholds = Object.values(ap.runways).map((r) => pl.xy(...r.thr));
    // Distance to the runway ITSELF (threshold to reciprocal threshold), not
    // to its nearest end: a home beside the strip is nearer than either end.
    let strip = { d: Infinity, q: ORIGIN };
    for (const [rwy, r] of Object.entries(ap.runways)) {
      const other = ap.runways[reciprocal(rwy)];
      const c = closest(ORIGIN, pl.xy(...r.thr), pl.xy(...(other || r).thr));
      if (c.d < strip.d) strip = c;
    }
    const dist = strip.d;
    // What the record holds for this airport goes on the page: a route the
    // data lacks must never read as a route that is not there.
    if (dist <= scopeKm) scope.push({ code, dist, q: strip.q, method: ap.departures_method });
    if (!ap.cities.length) continue; // runways-only record: nothing is drawn for it
    airports.push({ code, dist, thresholds, runways: ap.runways });
    for (const [rwy, r] of Object.entries(ap.runways)) {
      if (typeof r.glide_deg !== 'number') continue;
      const thr = pl.xy(...r.thr);
      const back = unit(r.true_brg + 180);
      const length = (FINAL_TOP_FT * FT_KM) / Math.tan(rad(r.glide_deg));
      const outer = add(thr, mul(back, length));
      const along = dot(sub(ORIGIN, thr), back); // km out from the threshold, along the approach
      const c = closest(ORIGIN, thr, outer);
      finals.push({
        code,
        rwy,
        line: [thr, outer],
        dist: c.d,
        q: c.q,
        beside: along > 0 && along < length,
        along,
        glide: r.glide_deg,
        heightFt: (along * Math.tan(rad(r.glide_deg))) / FT_KM,
        towards: towards(r.true_brg),
      });
    }
    for (const dep of ap.departures) {
      const pts = dep.waypoints.map(([la, lo]) => pl.xy(la, lo));
      let best = { d: Infinity, q: ORIGIN };
      for (let i = 0; i + 1 < pts.length; i++) {
        const c = closest(ORIGIN, pts[i], pts[i + 1]);
        if (c.d < best.d) best = c;
      }
      departures.push({
        code,
        name: dep.name,
        rwy: dep.runway,
        line: pts,
        dist: best.d,
        q: best.q,
        towards: towards(parseInt(dep.runway, 10) * 10),
      });
    }
  }
  airports.sort((a, b) => a.dist - b.dist);
  scope.sort((a, b) => a.dist - b.dist);
  return { finals, departures, airports, scope };
}

// A point is UNDER a final approach when it lies beside the drawn segment (between the
// threshold and the 3,000 ft point) and within this distance of its centreline.
export const UNDER_LINE_KM = 1.0;

/**
 * The final approach a point sits under, the nearest if several, or null.
 *
 * ONE RULE for every page that says "aircraft at about N ft here" (website audit A1,
 * 2026-10-07): the front page's answer and the full map's "Plane altitude". The full map
 * printed a hand ladder by distance to the airport instead, "4,000-6,000 ft" at TW9 3PZ,
 * where the published glide path gives about 1,800 ft on Heathrow's 27R approach. The
 * height is the final's own `heightFt` from routesNear(), the glide path's.
 */
export function finalOverhead(finals) {
  return finals.filter((x) => x.beside && x.dist <= UNDER_LINE_KM).sort((a, b) => a.dist - b.dist)[0] || null;
}

/** A glide-path height as every page prints it: to the nearest 100 ft. */
export const roundFt = (ft) => Math.round(ft / 100) * 100;
