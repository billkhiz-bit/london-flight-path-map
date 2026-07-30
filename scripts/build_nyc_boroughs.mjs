/**
 * Trim and simplify the NYC borough boundaries into a same-origin asset.
 *
 * Why this exists
 * ---------------
 * `index.html` loaded NYC boundaries straight from
 * `raw.githubusercontent.com/codeforgermany/click_that_hood` — a **2.67 MB**
 * cross-origin fetch issued the moment a user switches the map to New York.
 * The 2026-07-30 asset-vendoring work fixed the equivalent London path
 * (19.2 MB -> a 123 KB same-origin trim, see build_london_boroughs.py) but
 * left NYC on the third party. Three consequences:
 *
 *   * switching city depended on a host we do not control, live, at the
 *     moment of the click;
 *   * the file was not in the service worker's precache, so an offline or
 *     congested session drew no NYC boroughs at all; and
 *   * the failure path was a bare `console.warn` — the outlines simply did
 *     not appear, with nothing said to the user.
 *
 * Unlike London there are no surplus features to discard: the source is
 * already exactly the five boroughs, and `properties.name` already matches
 * the keys in NYC_BOROUGH_DATA_RAW. The weight is vertex density — 68,677
 * points for five outlines drawn at city scale. So the lever here is
 * geometry simplification rather than feature filtering.
 *
 * Why this is .mjs and its London counterpart is .py
 * --------------------------------------------------
 * Not a considered split — the laptop this was written on has no Python
 * beyond the Microsoft Store stub, and a build script that cannot be run is
 * worse than an inconsistent one. Porting this to Python (or that one to
 * Node) is a reasonable tidy-up; the two are independent and neither is
 * called from the deploy.
 *
 * Tolerance
 * ---------
 * Douglas-Peucker at 0.00005 degrees, ~6 m at this latitude. The NYC
 * projection is `d3.geoMercator().scale(55000)`, so one degree of longitude
 * is ~960 px and one pixel is ~88 m at rest. `zoom.scaleExtent([0.5, 8])`
 * means the tightest the user can pull in is ~11 m/px, so a 6 m tolerance
 * stays under half a pixel even fully zoomed. ~11 m tolerance would have
 * saved a further 80 KB and been sub-pixel at rest, but lands at ~1 px when
 * zoomed — not worth the bytes.
 *
 * Usage
 * -----
 *     node scripts/build_nyc_boroughs.mjs             # fetch + build
 *     node scripts/build_nyc_boroughs.mjs --src FILE  # build from a local copy
 *
 * Verify the output by feature count and by eye at max zoom, not by file
 * size: 5 features is correct, and anything fewer means the source's `name`
 * field has drifted from BOROUGHS below.
 */

import { writeFileSync, mkdirSync, readFileSync, statSync } from 'node:fs';
import { dirname } from 'node:path';

const SRC_URL =
  'https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/new-york-city-boroughs.geojson';
const OUT_PATH = 'data/nyc-boroughs.json';

// The source of truth for "which boroughs" is index.html's
// NYC_BOROUGH_DATA_RAW. renderNycBoroughs() looks the clicked feature up by
// `d.properties.name`, so these strings must survive the build byte-for-byte
// or a click resolves to no data and silently does nothing.
const BOROUGHS = ['Queens', 'Brooklyn', 'Manhattan', 'Bronx', 'Staten Island'];

// ~6 m at 40.75N. See the Tolerance note above before changing this.
const TOLERANCE = 0.00005;

// ~1 m. Borough outlines are drawn at city scale, so the 6 decimal places in
// the source are below the simplifier's own tolerance anyway.
const COORD_PRECISION = 5;

// Longitude degrees are shorter than latitude degrees away from the equator.
// Without this the simplifier is ~24% more aggressive east-west than
// north-south at NYC's latitude.
const LAT_SCALE = Math.cos((40.75 * Math.PI) / 180);

/** Perpendicular distance from `p` to segment `a`-`b`, in latitude-degrees. */
function perpendicularDistance(p, a, b) {
  const px = (p[0] - a[0]) * LAT_SCALE;
  const py = p[1] - a[1];
  const bx = (b[0] - a[0]) * LAT_SCALE;
  const by = b[1] - a[1];
  const lenSq = bx * bx + by * by;
  if (lenSq === 0) return Math.hypot(px, py);
  // Clamped, so a point beyond either end measures to the endpoint rather
  // than to the infinite line — otherwise near-duplicate endpoints report
  // absurdly small distances and whole spurs collapse.
  const t = Math.max(0, Math.min(1, (px * bx + py * by) / lenSq));
  return Math.hypot(px - t * bx, py - t * by);
}

/** Douglas-Peucker. Iterative rather than recursive: Staten Island's outer
 *  ring is ~20k points and the recursive form overflows the stack on it. */
function simplify(points, tolerance) {
  if (points.length < 3) return points.slice();
  const keep = new Uint8Array(points.length);
  keep[0] = 1;
  keep[points.length - 1] = 1;
  const stack = [[0, points.length - 1]];
  while (stack.length) {
    const [first, last] = stack.pop();
    let maxDist = 0;
    let index = 0;
    for (let i = first + 1; i < last; i++) {
      const d = perpendicularDistance(points[i], points[first], points[last]);
      if (d > maxDist) {
        maxDist = d;
        index = i;
      }
    }
    if (maxDist > tolerance) {
      keep[index] = 1;
      stack.push([first, index], [index, last]);
    }
  }
  return points.filter((_, i) => keep[i]);
}

/** Simplify one closed ring, keeping it closed and keeping it a polygon. */
function simplifyRing(ring, tolerance) {
  // A quad (4 points incl. the repeated close) is already minimal.
  if (ring.length < 5) return ring;
  const out = simplify(ring, tolerance);
  // Below 4 points it is no longer an area. Rather than emit a degenerate
  // ring, keep the original — these are tiny islands where the bytes are
  // irrelevant anyway.
  if (out.length < 4) return ring;
  // DP preserves both endpoints, but they are only equal to within float
  // noise after rounding; force exact closure.
  out[out.length - 1] = out[0];
  return out;
}

function round(node, precision) {
  if (Array.isArray(node)) return node.map((n) => round(n, precision));
  if (typeof node === 'number') {
    const f = 10 ** precision;
    return Math.round(node * f) / f;
  }
  return node;
}

function countVertices(node) {
  if (!Array.isArray(node)) return 0;
  if (typeof node[0] === 'number') return 1;
  return node.reduce((sum, child) => sum + countVertices(child), 0);
}

/** MultiPolygon -> polygons -> rings. Polygon is one level shallower. */
function simplifyGeometry(geometry, tolerance) {
  const walk = (node, depth) =>
    depth === 0 ? simplifyRing(node, tolerance) : node.map((child) => walk(child, depth - 1));
  const depth = geometry.type === 'MultiPolygon' ? 2 : 1;
  return { type: geometry.type, coordinates: walk(geometry.coordinates, depth) };
}

async function readSource(srcArg) {
  if (srcArg) return readFileSync(srcArg, 'utf8');
  process.stderr.write(`fetching ${SRC_URL} ...\n`);
  const res = await fetch(SRC_URL, { signal: AbortSignal.timeout(120_000) });
  if (!res.ok) throw new Error(`source returned HTTP ${res.status}`);
  return res.text();
}

async function main() {
  const args = process.argv.slice(2);
  const srcArg = args.includes('--src') ? args[args.indexOf('--src') + 1] : null;
  const outPath = args.includes('--out') ? args[args.indexOf('--out') + 1] : OUT_PATH;

  const source = JSON.parse(await readSource(srcArg));
  const features = source.features || [];
  process.stderr.write(`source features: ${features.length}\n`);

  const byName = new Map();
  for (const feature of features) {
    const name = feature.properties && feature.properties.name;
    if (name) byName.set(String(name), feature);
  }

  const missing = BOROUGHS.filter((b) => !byName.has(b));
  if (missing.length) {
    process.stderr.write(
      `ERROR: source is missing ${missing.length} borough(s): ${missing.join(', ')}\n` +
        `Found: ${[...byName.keys()].sort().join(', ')}\n` +
        "The source's name field has probably changed — check BOROUGHS.\n"
    );
    return 1;
  }

  let before = 0;
  let after = 0;
  // Emitted in BOROUGHS order so a diff against NYC_BOROUGH_DATA_RAW reads
  // cleanly. Draw order does not matter: the boroughs do not overlap.
  const kept = BOROUGHS.map((name) => {
    const feature = byName.get(name);
    before += countVertices(feature.geometry.coordinates);
    const geometry = simplifyGeometry(feature.geometry, TOLERANCE);
    geometry.coordinates = round(geometry.coordinates, COORD_PRECISION);
    after += countVertices(geometry.coordinates);
    // cartodb_id / created_at / updated_at are 2013 CartoDB export residue
    // that nothing reads. Only `name` is used, by renderNycBoroughs().
    return { type: 'Feature', properties: { name }, geometry };
  });

  mkdirSync(dirname(outPath), { recursive: true });
  // No whitespace: this is a served asset, not something a human reads.
  writeFileSync(outPath, JSON.stringify({ type: 'FeatureCollection', features: kept }), 'utf8');

  const sizeKb = statSync(outPath).size / 1024;
  process.stderr.write(
    `wrote ${outPath} — ${kept.length} boroughs, ${sizeKb.toFixed(0)} KB\n` +
      `vertices ${before} -> ${after} (${(100 - (100 * after) / before).toFixed(1)}% cut)\n`
  );
  for (const name of BOROUGHS) process.stderr.write(`  - ${name}\n`);
  return 0;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    process.stderr.write(`ERROR: ${err.message}\n`);
    process.exit(1);
  }
);
