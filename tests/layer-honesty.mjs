/**
 * A fill layer must paint exactly the boroughs it has a reading for.
 *
 * Why this exists
 * ---------------
 * On 2026-08-11 the three borough choropleth layers - road noise, flood risk,
 * air quality - each ended their lookup with a fallback:
 *
 *     const level = roadNoiseData[n] || 'moderate';
 *     const risk  = extra?.flood     || 'low';
 *     const aq    = extra?.airQuality|| 'moderate';
 *
 * `data/borough-extra.json` gave London and NYC those fields and gave the other
 * seven UK cities nothing, so every borough of all seven was painted a single
 * confident colour - the same purple that means "moderate road noise" where a
 * reading exists. The legend title above it already said "(NO DATA)". The label
 * said no data and the map drew a value.
 *
 * Nothing caught it because nothing compared the RENDER to the DATA. The pytest
 * suites never open index.html, and the Playwright specs assert the site against
 * itself, so a fabricated fill is self-consistent and passes.
 *
 * What it asserts
 * ---------------
 * For every city and each of the three layers: the number of paths painted
 * equals the number of that city's boroughs whose borough-extra record carries
 * the corresponding field. Both directions matter -
 *
 *   painted > expected  a default is being invented for boroughs with no data
 *   painted < expected  a borough HAS data the map is failing to find, which is
 *                       what a borough-name mismatch between the holder and the
 *                       GeoJSON looks like, and it fails silently
 *
 * Proven red in both directions: restoring `|| 'moderate'` over-paints, and
 * renaming a borough key in borough-extra.json under-paints.
 *
 * And the legend's BAND ROWS, added 2026-08-23
 * --------------------------------------------
 * The same question one level down. The three layer TITLES have been measured
 * since 2026-08-11 - "(NO DATA)" is appended from what the render produced -
 * but each title sat above three static swatches that were never checked
 * against anything. Measured across all eleven cities at the time of writing:
 * 41 of 99 rendered band rows described a band no borough on that map carried.
 * Leicester and Teesside showed six confident colour swatches - three road,
 * three flood - underneath two titles already reading "(NO DATA)".
 *
 * Two assertions, both from the DOM on both sides:
 *
 *   completeness  every key in FILL_LAYER_COLOURS has a [data-band] row, and
 *                 vice versa. City-independent, so it runs once. This is the
 *                 root-cause guard: aq held four colours against three rows,
 *                 so 'excellent' (#16a34a, four shades off GOOD's #22c55e) was
 *                 a colour the map could paint with nothing to name it.
 *
 *   visibility    per city, the set of VISIBLE rows equals the set of bands
 *                 actually painted. Painted bands are inverted out of the
 *                 rendered `fill` attributes and visibility is read from
 *                 computed style - never from the counter or the inline style
 *                 the fix itself writes.
 *
 * Both fail in both directions, and all four directions are proven red:
 * deleting the hiding loop (the pre-fix state) reds visibility one way,
 * inverting its condition reds it the other, deleting the EXCELLENT row reds
 * completeness one way, and an unknown row reds it the other.
 *
 *   node tests/layer-honesty.mjs
 */
import { chromium } from '@playwright/test';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';

const ROOT = process.cwd();
// 8123 / 8921 / 8922 / 8923 / 8924 are taken by the other harnesses, and
// preflight runs these in one block.
const PORT = 8925;
const TYPES = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.json': 'application/json',
  '.css': 'text/css',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.woff2': 'font/woff2',
  '.webmanifest': 'application/manifest+json',
};

const server = createServer(async (req, res) => {
  const raw = decodeURIComponent(req.url.split('?')[0]);
  const p = join(ROOT, normalize(raw === '/' ? '/index.html' : raw));
  if (!p.startsWith(ROOT)) return res.writeHead(403).end();
  try {
    const body = await readFile(p);
    res.writeHead(200, { 'content-type': TYPES[extname(p)] || 'application/octet-stream' });
    res.end(body);
  } catch {
    res.writeHead(404).end();
  }
});
await new Promise((r) => server.listen(PORT, r));

const LAYERS = [
  {
    key: 'defra-road',
    field: 'roadNoise',
    sel: '.layer-defra-road',
    label: 'road noise',
    group: 'legend-road-group',
    colourKey: 'road',
  },
  {
    key: 'flood',
    field: 'flood',
    sel: '.layer-flood',
    label: 'flood',
    group: 'legend-flood-group',
    colourKey: 'flood',
  },
  {
    key: 'air-quality',
    field: 'airQuality',
    sel: '.layer-air-quality',
    label: 'air quality',
    group: 'legend-aq-group',
    colourKey: 'aq',
  },
];

/**
 * Read what a layer painted and what its legend claims, both from the DOM.
 *
 * `painted` is inverted out of the rendered `fill` attributes rather than read
 * from the counter markLayerCoverage() maintains, and `visible` is the computed
 * display of each row rather than the inline style the fix writes. Taking
 * either from the code under test is this repo's most repeated defect - a gate
 * that reads the flag the fix sets agrees with the fix's own bugs.
 *
 * Computed `display` on a row is unaffected by its group being hidden: an
 * ancestor's `display: none` does not change a descendant's computed value. So
 * this reads correctly whether or not the layer's legend group is open.
 */
const readLegendState = (layerDefs) =>
  layerDefs.map((l) => {
    const colours = FILL_LAYER_COLOURS[l.colourKey];
    const invert = {};
    for (const [band, hex] of Object.entries(colours)) invert[hex.toLowerCase()] = band;

    const gEl = document.querySelector(l.sel);
    const painted = new Set();
    if (gEl) {
      for (const path of gEl.querySelectorAll('path')) {
        const fill = (path.getAttribute('fill') || '').toLowerCase();
        painted.add(invert[fill] || `UNMAPPED:${fill}`);
      }
    }

    const group = document.getElementById(l.group);
    const rows = group ? Array.from(group.querySelectorAll('[data-band]')) : [];
    return {
      key: l.key,
      label: l.label,
      colourBands: Object.keys(colours),
      declared: rows.map((r) => r.dataset.band),
      visible: rows
        .filter((r) => getComputedStyle(r).display !== 'none')
        .map((r) => r.dataset.band),
      painted: Array.from(painted),
    };
  });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto(`http://localhost:${PORT}/index.html`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(3000);

const cities = await page.evaluate(() =>
  Object.entries(CITY_DATA).map(([id, d]) => ({ id, label: d.label, country: d.country }))
);

// EVERY COLOUR THE PAINTER CAN PRODUCE MUST HAVE A ROW TO EXPLAIN IT.
//
// City-independent, so it runs once. This is the root-cause guard for the
// defect found on 2026-08-23: FILL_LAYER_COLOURS.aq held four bands while the
// air-quality legend held three, so 'excellent' - #16a34a, four shades off
// GOOD's #22c55e - was a colour the map could paint with nothing to name it.
//
// Recorded in HANDOVER.md and ROADMAP.md the other way round, as a legend
// advertising a band no borough can occupy. It never advertised it. The two
// lists were function-locals and static markup with no gate between them,
// which is why a note could sit on the wrong side of the fact for two days.
{
  const state = await page.evaluate(readLegendState, LAYERS);
  let missing = 0;
  for (const l of state) {
    const gap = l.colourBands.filter((b) => !l.declared.includes(b));
    const extra = l.declared.filter((b) => !l.colourBands.includes(b));
    if (gap.length) {
      missing += 1;
      console.log(
        `  ! ${l.label}: the painter can paint [${gap.join(', ')}] with no legend row ` +
          `to name it (legend declares [${l.declared.join(', ')}])`
      );
    }
    if (extra.length) {
      missing += 1;
      console.log(
        `  ! ${l.label}: the legend declares [${extra.join(', ')}], which the painter ` +
          'has no colour for, so no map can ever show it'
      );
    }
  }
  if (missing) {
    console.log(
      '\nFAIL: legend rows and painter colours are not the same list of bands.'
    );
    await browser.close();
    server.close();
    process.exit(1);
  }
  console.log(
    `Legend rows and painter colours agree on all bands ` +
      `(${state.map((l) => `${l.label} ${l.declared.length}`).join(', ')}).`
  );
}

console.log('\nLayer honesty: painted boroughs vs boroughs holding a reading\n');
console.log(`${'city'.padEnd(20)} ${'road noise'.padEnd(16)} ${'flood'.padEnd(16)} air quality`);
console.log('-'.repeat(74));

let fail = 0;
let totalExpected = 0;
let totalBandRows = 0;

// THE LANDING CITY, MEASURED WITHOUT SWITCHING TO IT.
//
// Separate from the loop below, and first, because switching to a city
// re-renders the map: every city reached through the switcher is painted from a
// fully hydrated `borough-extra.json`, so the loop cannot see anything that goes
// wrong on the FIRST render. The city a visitor actually lands on is the only
// one painted before the switcher has been touched.
//
// HONEST LIMIT OF THIS CASE. It is here because that asymmetry is real, not
// because it is proven to catch a specific bug. `borough-extra.json` is
// lazy-loaded and could in principle arrive after the first render, leaving the
// landing city's fills empty - but on a local server hydration reliably wins
// (measured at 500ms through 6s, always 33/33), so removing the
// repaintFillLayers() call from hydrateBoroughExtra() does NOT turn this red.
// Treat it as a guard against a race that is latent here and plausible on a
// slow connection, not as a proven red-prover like the over-painting case.
{
  const landing = await page.evaluate((layerDefs) => {
    for (const l of layerDefs) layers[l.key] = true;
    const feats = cityOf(currentCity).features();
    const out = { city: currentCity };
    for (const l of layerDefs) {
      const expected = feats.filter((f) => {
        const e = getExtraData(getName(f));
        return e && e[l.field];
      }).length;
      const gEl = document.querySelector(l.sel);
      out[l.key] = { painted: gEl ? gEl.querySelectorAll('path').length : 0, expected };
    }
    return out;
  }, LAYERS);

  const cells = [];
  for (const l of LAYERS) {
    const m = landing[l.key];
    const ok = m.painted === m.expected;
    if (!ok) fail += 1;
    cells.push(`${ok ? ' ' : '!'}${m.painted}/${m.expected}`.padEnd(16));
  }
  console.log(`${`${landing.city} (landing)`.padEnd(20)} ${cells.join(' ')}`);
}

for (const city of cities) {
  await page.evaluate((c) => switchCountry(c), city.country);
  await page.waitForTimeout(250);
  await page.evaluate((id) => switchCity(id), city.id);
  await page.waitForTimeout(250);
  await page.evaluate((keys) => {
    for (const k of keys) layers[k] = true;
  }, LAYERS.map((l) => l.key));

  // THE SETTLE WAIT BELONGS HERE, AFTER THE TOGGLES, NOT AFTER switchCity.
  // Setting the layer flags triggers another render, and updateDefraTiles()
  // opens by resetting aircraftScalePainted to false and CLEARING the tile
  // group before re-adding it - so a wait placed before this line is undone by
  // it. Measured with the wait in the wrong place: 3 failures in 6 runs, all
  // reporting "scale hidden but a dB surface IS painted", which is the freshly
  // re-added tiles being measured before their own settle. Waiting first and
  // then re-rendering is waiting for the wrong render.
  // WAIT FOR THE AIRCRAFT LAYER TO SETTLE BEFORE MEASURING IT.
  //
  // Every tile in #us-aircraft-tiles is a remote fetch that removes itself on
  // error, so the group is populated synchronously and can empty a moment
  // later. NYC's come from geo.dot.gov, measured at 11.6 s for a metadata call
  // on 2026-08-29. There are three states, and only two of them are meaningful:
  //
  //   settled, painted   images present, scale shown        -> compare
  //   settled, empty     all tiles errored, scale hidden    -> compare
  //   IN FLIGHT          images present, scale not yet on   -> meaningless
  //
  // The third looks exactly like the defect this file exists to catch, so it
  // must be waited out rather than measured. A fixed sleep cannot do it (this
  // file used waitForTimeout(1800) and went red in one full preflight run while
  // passing on identical source either side), and NEITHER CAN A STABLE TILE
  // COUNT - pending tiles hold a perfectly stable count for as long as they are
  // pending. That was the first attempt at this fix and it still failed 2 runs
  // in 4. networkidle is the only instrument here that sees a request which has
  // not come back yet.
  //
  // Deliberately NOT read: `aircraftScalePainted`. Taking the settle signal
  // from the flag under test is the trap this file avoids everywhere else, and
  // is why the check below reads the DOM.
  //
  // A timeout is REPORTED, never swallowed - the reading that follows would be
  // early, and a quiet catch would turn this gate's own uncertainty into a
  // confident measurement, which is the defect class the file exists to catch.
  try {
    await page.waitForLoadState('networkidle', { timeout: 45000 });
  } catch {
    console.log(
      `  ~ ${city.id}: network still busy after 45s - the aircraft reading below may be early`
    );
  }
  await page.waitForTimeout(400);

  const measured = await page.evaluate((layerDefs) => {
    // Expected count comes from the SAME record the renderer reads, resolved
    // through the SAME getExtraData() lookup - so a borough-name mismatch shows
    // up as a shortfall rather than being silently excused on both sides.
    const feats = cityOf(currentCity).features();
    const out = {};
    for (const l of layerDefs) {
      const expected = feats.filter((f) => {
        const e = getExtraData(getName(f));
        return e && e[l.field];
      }).length;
      const gEl = document.querySelector(l.sel);
      out[l.key] = { painted: gEl ? gEl.querySelectorAll('path').length : 0, expected };
    }
    return out;
  }, LAYERS);

  // THE AIRCRAFT LAYER, which is a raster and not borough paths, so it cannot
  // be counted the way the three above are - but it went wrong the same way.
  // Its five-band decibel scale is static markup, while updateDefraTiles()
  // paints a dB surface for London and NYC only. For the other nine cities the
  // legend described a surface that is not on the map at any zoom, worst in
  // South Yorkshire whose own title reads "AIRCRAFT NOISE (NO AIRPORT)".
  //
  // Measured from the DOM on BOTH sides - is an image actually there, and is
  // the scale actually visible - rather than from the `aircraftScalePainted`
  // flag the fix introduced. Reading that flag would be taking the expectation
  // from the code under test, which is this repo's most repeated defect.
  //
  // POLLED TO SETTLEMENT, not read at one instant. networkidle is not the end
  // of this layer: renderTileGrid's onSettle fires only once every appended
  // tile has loaded or failed, or after its own 20 SECOND hung-tile deadline,
  // and networkidle can fire in a gap BEFORE the tile requests are issued.
  // Measured 2026-09-01: one run reached networkidle at 4,891 ms with all tiles
  // loaded and agreeing for 35 s straight, while a preflight run caught NYC
  // mid-settle and reported "scale hidden but a dB surface IS painted" - the
  // very message this file's comment records from an earlier failed fix.
  //
  // THIS IS NOT "ASSERT UNTIL TRUE". The property is "once settled, the legend
  // matches the map". A disagreement during settle is not a defect; a
  // persistent one is, and BOTH defects this check exists for are persistent -
  // NYC's flag set before a tile had loaded, and a stale callback relabelling
  // another city's legend. Neither self-heals, so neither can be waited out.
  // The deadline is past the app's own 20 s so a hung tile resolves inside it.
  const readAir = () =>
    page.evaluate(() => {
      const img = document.getElementById('defra-aircraft-img');
      const tiles = document.getElementById('us-aircraft-tiles');
      const hasRaster = Boolean(
        // `data-loaded`, NOT href (audit F26). The London branch ASSIGNS the
        // href, so reading it here took the expectation from the code under
        // test - this check could never have caught a London PNG that 404'd,
        // which is precisely the failure it exists for. The attribute is set
        // in the image's own onload, exactly as NYC's tiles do below.
        (img && img.hasAttribute('data-loaded')) ||
          // image[data-loaded], not image. A tile element whose href has not
          // come back yet paints NOTHING, so counting elements reports a
          // surface that is not on the map - which is the very thing this check
          // exists to catch, made by the checker. The attribute is set in the
          // tile's own onload, so it is per-tile ground truth about the DOM and
          // not the `aircraftScalePainted` flag this file refuses to read.
          (tiles && tiles.querySelectorAll('image[data-loaded]').length > 0)
      );
      const scale = document.getElementById('legend-noise-scale');
      const scaleShown = Boolean(scale) && getComputedStyle(scale).display !== 'none';
      const title = (document.getElementById('legend-noise-title') || {}).textContent || '';
      return { hasRaster, scaleShown, saysNoData: /\(NO DATA\)/.test(title) };
    });

  const AIR_SETTLE_MS = 25000;
  const airDeadline = Date.now() + AIR_SETTLE_MS;
  let air = await readAir();
  let airWaited = 0;
  while (air.scaleShown !== air.hasRaster && Date.now() < airDeadline) {
    await page.waitForTimeout(500);
    airWaited += 500;
    air = await readAir();
  }
  // Reported, never swallowed: a reading that needed seconds to settle is worth
  // knowing about even when it ends up agreeing, because it is the shape that
  // precedes a flake.
  if (airWaited >= 2000) {
    console.log(`  ~ ${city.id}: aircraft layer took ${airWaited}ms to settle`);
  }
  if (air.scaleShown !== air.hasRaster) {
    fail += 1;
    console.log(
      `  ! ${city.id}: decibel scale ${air.scaleShown ? 'SHOWN' : 'hidden'} but a dB ` +
        `surface is ${air.hasRaster ? 'painted' : 'NOT painted'}`
    );
  }
  // And the title must agree with the scale. Relabelling without hiding leaves
  // "(NO DATA)" above five confident bands, which is the map still being louder
  // than the label.
  if (air.saysNoData === air.hasRaster) {
    fail += 1;
    console.log(
      `  ! ${city.id}: title says ${air.saysNoData ? '(NO DATA)' : 'data'} while a dB ` +
        `surface is ${air.hasRaster ? 'painted' : 'not painted'}`
    );
  }

  // THE LEGEND'S BAND ROWS, against the bands actually on the map.
  //
  // The layer titles have been measured since 2026-08-11 - "(NO DATA)" is
  // appended from what the render produced - but their band ROWS were static
  // markup until 2026-08-23. A city with no High-risk flood borough still
  // carried a HIGH swatch, and every city carried all three road bands
  // whatever was underneath.
  //
  // Fails in both directions, which are two different lies:
  //   visible but not painted  the legend claims a colour the map cannot show
  //   painted but not visible  the map shows a colour the legend cannot explain
  const legend = await page.evaluate(readLegendState, LAYERS);
  for (const l of legend) {
    const unmapped = l.painted.filter((b) => b.startsWith('UNMAPPED:'));
    if (unmapped.length) {
      fail += 1;
      console.log(
        `  ! ${city.id} ${l.label}: painted ${unmapped.length} path(s) in a colour ` +
          `absent from FILL_LAYER_COLOURS (${unmapped.join(', ')})`
      );
    }
    const claimed = l.visible.filter((b) => !l.painted.includes(b));
    const unexplained = l.painted.filter((b) => !b.startsWith('UNMAPPED:') && !l.visible.includes(b));
    if (claimed.length) {
      fail += 1;
      console.log(
        `  ! ${city.id} ${l.label}: legend shows [${claimed.join(', ')}], which no ` +
          'borough on this map carries'
      );
    }
    if (unexplained.length) {
      fail += 1;
      console.log(
        `  ! ${city.id} ${l.label}: map paints [${unexplained.join(', ')}] with the ` +
          'legend row hidden'
      );
    }
    totalBandRows += l.visible.length;
  }

  const cells = [];
  for (const l of LAYERS) {
    const m = measured[l.key];
    const ok = m.painted === m.expected;
    if (!ok) fail += 1;
    totalExpected += m.expected;
    cells.push(`${ok ? ' ' : '!'}${m.painted}/${m.expected}`.padEnd(16));
  }
  const bandCells = legend
    .map((l) => `${l.visible.length}/${l.declared.length}`)
    .join(' ');
  console.log(`${city.label.padEnd(20)} ${cells.join(' ')}  bands ${bandCells}`);
}

// A FLOOR ON THE EXPECTATION ITSELF.
//
// `expected` is computed through getExtraData() - deliberately the same lookup
// the renderer uses, so a borough-name mismatch shows as a shortfall rather
// than being excused on both sides. The cost of that choice is that when
// data/borough-extra.json does not PARSE, both sides collapse to 0 together:
// every city prints 0/0, `fail` stays 0, and this gate reports "Every layer
// paints exactly the boroughs that hold a reading" while the map is blank.
// Proven by serving that one file as 200 + a non-JSON body, which is the shape
// a CloudFront custom error page takes.
//
// This is the only gate covering roadNoise/flood/airQuality - they are not
// scoring inputs, so borough-score-parity.mjs cannot see them either. A total
// of zero is therefore never a pass.
if (totalExpected === 0) {
  console.log(
    '\nFAIL: every city expected 0 boroughs with a reading. borough-extra.json ' +
      'is missing or unparseable, so the comparison ran against nothing.'
  );
  process.exit(1);
}

// THE SAME FLOOR FOR THE BAND CHECK, and it is a separate one on purpose.
//
// The band comparison is between two sets, and empty == empty passes - the
// shape that let build_aircraft_bands.py print "0/0 agree" and exit 0 while
// being a blocking gate.
//
// HONEST LIMIT, in the spirit of the note on the landing-city case above: this
// floor is NOT independently provable red today, because every route to it is
// already covered. Removing [data-band] from the markup reds the completeness
// check first; hiding every row while boroughs paint reds the set comparison;
// and nothing painting anywhere reds the totalExpected floor below it. It is a
// backstop against a future refactor that removes one of those, not a
// proven red-prover. The other three assertions here ARE proven, in both
// directions each - see the header.
if (totalBandRows === 0) {
  console.log(
    '\nFAIL: no legend band row was visible in any city. Either [data-band] no ' +
      'longer matches the legend markup, or markLayerCoverage hid every row - ' +
      'the comparison ran against nothing either way.'
  );
  process.exit(1);
}

await browser.close();
server.close();

console.log(
  fail === 0
    ? `\nEvery layer paints exactly the boroughs that hold a reading, and every ` +
        `legend band row matches a band on the map (${totalBandRows} rows shown ` +
        `across ${cities.length} cities).`
    : `\n${fail} layer/city problem(s): a painted count that disagrees with the data, ` +
        'or a legend band row that disagrees with the map.'
);
process.exit(fail === 0 ? 0 : 1);
