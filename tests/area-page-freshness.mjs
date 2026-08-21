/**
 * The scores BAKED into the static area pages must still match the live API.
 *
 * Why this exists
 * ---------------
 * The 99 pages under area/ are generated: each one carries a score written at
 * build time. That is what makes them indexable - a crawler sees the number
 * without running JavaScript - and it is also what makes them able to go stale
 * in a way nothing else here can.
 *
 * Scores move on data vintages, roughly quarterly. When one lands, /v1/score
 * returns the new figure and 99 static pages go on serving the old one, with no
 * error anywhere. That is a site/API divergence, which is the defect class this
 * repo has paid for three separate times - the Manchester incident, the
 * quiet-score divergence, and the 13% of London postcodes where the site and
 * the API disagreed while every component matched.
 *
 * The existing gates cannot see it:
 *   - `area pages carry real data` checks richness and sitemap agreement, not
 *     whether the numbers are current
 *   - `deployed == source` compares the repo to CloudFront, and after a vintage
 *     roll BOTH are stale, so they agree perfectly
 *   - `site == Lambda` drives the map, which reads the API live
 *
 * So this compares the two things that can drift: the number in the file, and
 * the number the API returns today.
 *
 * ONE REQUEST, NOT NINETY-NINE
 * ----------------------------
 * Every borough goes in a single /v1/score/batch call. That matters because the
 * CI key has a 10,000/month quota and preflight runs many times a day; a
 * per-borough loop would spend ~99 units a run and turn a blocking gate into a
 * countdown, which is precisely how `score sanity` once blocked every commit in
 * the repo. Batch makes it 1 unit.
 *
 * Results are matched by `queryIndex`, not by array position - the handler
 * returns the field for exactly this reason, and trusting order would silently
 * compare one borough's page against another's score.
 *
 *   node tests/area-page-freshness.mjs
 */
import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const API = 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod';
const KEY = process.env.SKY_SCORE_API_KEY;
const CHUNK = 100; // MAX_BATCH_SIZE in backend/lambdas/score/app.py

// Scores are published to one decimal place, so anything at or above 0.05 is a
// visible difference on the page. Not a "close enough" allowance - it is the
// rounding boundary, and a real drift is never this small.
const EPSILON = 0.05;

if (!KEY) {
  console.error('FAIL: SKY_SCORE_API_KEY not set. Put it in .env (gitignored).');
  console.error('      This gate compares baked scores against the live API and');
  console.error('      cannot run without a key. Not skipped, because a silent');
  console.error('      skip is how a stale page would survive.');
  process.exit(1);
}

// --- what the pages currently claim -----------------------------------------
const ROOT = process.cwd();
const areaRoot = join(ROOT, 'area');
if (!existsSync(areaRoot)) {
  console.error('FAIL: area/ missing. Run scripts/build_area_pages.py --write');
  process.exit(1);
}

// city dir -> the `city` value /v1/score expects. The page path is a slug, and
// slugs are lossy: `city-of-bristol` is the BOROUGH slug, not the city key.
// The city key is carried in the page itself, in the map link, so it is read
// from there rather than reconstructed.
const pages = [];
for (const cityDir of readdirSync(areaRoot)) {
  const dir = join(areaRoot, cityDir);
  if (!statSync(dir).isDirectory()) continue;
  for (const boroughDir of readdirSync(dir)) {
    const file = join(dir, boroughDir, 'index.html');
    if (!existsSync(file)) continue;
    const html = readFileSync(file, 'utf8');
    const score = (html.match(/<span class="n">([\d.]+)<\/span>/) || [])[1];
    // Both taken from the map CTA, which carries the exact strings the API
    // wants. Parsing the <h1> instead would mean un-escaping and un-slugging.
    const link = html.match(/href="\/\?city=([^&"]+)&amp;borough=([^"]+)"/);
    if (!score || !link) {
      console.error(`FAIL: could not read score/city/borough from ${file}`);
      console.error('      The page template changed and this gate can no longer');
      console.error('      read it. Fix the parse, do not delete the check.');
      process.exit(1);
    }
    pages.push({
      file: `area/${cityDir}/${boroughDir}/`,
      baked: Number(score),
      city: decodeURIComponent(link[1]),
      borough: decodeURIComponent(link[2].replace(/\+/g, ' ')),
    });
  }
}

console.log(`\nArea page freshness\n===================\n`);
console.log(`  ${pages.length} pages to check, in ${Math.ceil(pages.length / CHUNK)} batch request(s)\n`);

// --- what the API says today ------------------------------------------------
const live = new Map();
for (let i = 0; i < pages.length; i += CHUNK) {
  const slice = pages.slice(i, i + CHUNK);
  const res = await fetch(`${API}/v1/score/batch`, {
    method: 'POST',
    headers: { 'X-Api-Key': KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      queries: slice.map((p) => ({ borough: p.borough, city: p.city })),
    }),
  });
  if (!res.ok) {
    console.error(`FAIL: batch returned HTTP ${res.status}`);
    if (res.status === 429) {
      console.error('      Throttled or out of quota. This gate uses ONE request');
      console.error('      per 100 boroughs precisely to avoid that, so a 429 here');
      console.error('      means the CI key itself is exhausted or lost batch access.');
    }
    process.exit(1);
  }
  const body = await res.json();
  for (const r of body.results || []) {
    // queryIndex, never array position: the handler returns it so a caller can
    // match reliably, and comparing by position would pair one borough's page
    // with another borough's score.
    const p = slice[r.queryIndex];
    if (p) live.set(p.file, r.status === 200 ? r.score : null);
  }
}

// --- compare ----------------------------------------------------------------
const stale = [];
const unresolved = [];
for (const p of pages) {
  if (!live.has(p.file)) {
    unresolved.push(`${p.file} (no result returned)`);
    continue;
  }
  const now = live.get(p.file);
  if (now === null) {
    unresolved.push(`${p.file} (${p.borough}/${p.city} no longer scores)`);
    continue;
  }
  if (Math.abs(now - p.baked) >= EPSILON) {
    stale.push({ ...p, now });
  }
}

for (const s of stale.slice(0, 12)) {
  console.log(`  STALE  ${s.file}  page says ${s.baked}, API says ${s.now}`);
}
for (const u of unresolved.slice(0, 6)) {
  console.log(`  ORPHAN ${u}`);
}

const ok = stale.length === 0 && unresolved.length === 0;
console.log('');
if (!ok) {
  console.error(
    `FAIL: ${stale.length} stale page(s), ${unresolved.length} unresolved.\n` +
      '      Regenerate and redeploy:\n' +
      '        python scripts/build_area_pages.py --write\n' +
      '        make area-deploy meta-deploy   (or the manual s3 sync)\n' +
      '      A stale page publishes a score the API contradicts, which is the\n' +
      '      site/API divergence this repo has paid for three times.',
  );
  process.exit(1);
}
console.log(`OK: all ${pages.length} area pages match the live API\n`);
