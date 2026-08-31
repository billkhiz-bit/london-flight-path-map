/**
 * The generated area pages must carry REAL data and match the sitemap.
 *
 * Why this exists
 * ---------------
 * The sitemap listed eight URLs, all of them product or marketing pages, and
 * the map is client-side - so a crawler got a shell with no scores. The organic
 * surface was not weak, it was absent, and there was nothing for the embeddable
 * badge to link back to.
 *
 * These 99 pages are the fix, and the risk they introduce is worse than the
 * problem they solve if they are thin. A hundred near-identical pages carrying
 * a template and no facts is what search engines call a doorway network, and it
 * puts the whole domain's reputation behind filler. So this asserts CONTENT,
 * not existence.
 *
 * What it asserts, and why each one
 * ---------------------------------
 *   - every sitemap /area/ URL has a file      a sitemap entry with no page is
 *                                              a crawl error on every visit
 *   - every generated page is in the sitemap   the reverse; otherwise the work
 *                                              is done and undiscoverable
 *   - each page carries >= MIN facts           the doorway-page floor
 *   - no page repeats another's fact block     near-duplicate pages are the
 *                                              specific thing that gets a
 *                                              domain demoted, and a bug in the
 *                                              generator would produce exactly
 *                                              that: 99 copies of London
 *   - titles and descriptions are unique       duplicate <title> across 99 URLs
 *                                              is the same signal
 *   - no unresolved template placeholder       a stray {token} renders literally
 *
 *   node tests/area-pages.mjs
 */
import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = process.cwd();
const MIN_FACTS = 6;

const failures = [];
function check(name, pass, detail) {
  console.log(`  ${pass ? 'PASS' : 'FAIL'}  ${name}${detail ? '  ' + detail : ''}`);
  if (!pass) failures.push(`${name}: ${detail}`);
}

console.log('\nGenerated area pages\n====================\n');

// --- collect the generated pages -------------------------------------------
const pages = [];
const areaRoot = join(ROOT, 'area');
if (!existsSync(areaRoot)) {
  console.error('FAIL: area/ does not exist. Run scripts/build_area_pages.py --write');
  process.exit(1);
}
for (const city of readdirSync(areaRoot)) {
  const cityDir = join(areaRoot, city);
  if (!statSync(cityDir).isDirectory()) continue;
  for (const borough of readdirSync(cityDir)) {
    const f = join(cityDir, borough, 'index.html');
    if (existsSync(f)) pages.push({ url: `/area/${city}/${borough}/`, file: f });
  }
}
check('pages were generated', pages.length > 50, `${pages.length} pages`);

// --- sitemap agreement, both directions ------------------------------------
const sitemap = readFileSync(join(ROOT, 'sitemap.xml'), 'utf8');
const listed = new Set(
  [...sitemap.matchAll(/<loc>https:\/\/skyscore\.co\.uk(\/area\/[^<]*)<\/loc>/g)].map((m) => m[1]),
);
const generated = new Set(pages.map((p) => p.url));

const orphanedInSitemap = [...listed].filter((u) => u !== '/area/' && !generated.has(u));
check(
  'no sitemap URL without a page',
  orphanedInSitemap.length === 0,
  orphanedInSitemap.slice(0, 3).join(', '),
);
const missingFromSitemap = [...generated].filter((u) => !listed.has(u));
check(
  'no page missing from the sitemap',
  missingFromSitemap.length === 0,
  missingFromSitemap.slice(0, 3).join(', '),
);
check('the /area/ index is listed', listed.has('/area/'), '');

// --- content, not existence -------------------------------------------------
const titles = new Map();
const descriptions = new Map();
const factBlocks = new Map();
let thin = null;
let placeholder = null;

for (const p of pages) {
  const html = readFileSync(p.file, 'utf8');
  const facts = [...html.matchAll(/<th scope="row">/g)].length;
  if (facts < MIN_FACTS && !thin) thin = `${p.url} has ${facts}`;

  // A literal {token} means a .format() key was never substituted, which reads
  // to a visitor as a broken page and to a crawler as boilerplate.
  if (/\{[a-z_]+\}/.test(html) && !placeholder) placeholder = p.url;

  const title = (html.match(/<title>([^<]*)<\/title>/) || [])[1] || '';
  titles.set(title, (titles.get(title) || 0) + 1);
  const desc = (html.match(/<meta name="description" content="([^"]*)"/) || [])[1] || '';
  descriptions.set(desc, (descriptions.get(desc) || 0) + 1);

  // The concatenated VALUES, not the labels - the labels are identical by
  // design. If two boroughs share a value block, the generator is writing one
  // borough's data under another's name, which is the WA8 join defect again.
  const values = [...html.matchAll(/<\/th><td>([^<]*)/g)].map((m) => m[1]).join('|');
  factBlocks.set(values, (factBlocks.get(values) || 0) + 1);
}

check('every page clears the fact floor', thin === null, thin || `min ${MIN_FACTS}`);
check('no unsubstituted template token', placeholder === null, placeholder || '');

const dupTitles = [...titles.entries()].filter(([, n]) => n > 1);
check('titles are unique', dupTitles.length === 0, dupTitles.slice(0, 2).map(([t]) => t).join(' | '));

const dupDesc = [...descriptions.entries()].filter(([, n]) => n > 1);
check('descriptions are unique', dupDesc.length === 0, `${dupDesc.length} repeated`);

const dupFacts = [...factBlocks.entries()].filter(([, n]) => n > 1);
check(
  'no two pages share a fact block',
  dupFacts.length === 0,
  dupFacts.length ? `${dupFacts.length} duplicated blocks - a borough is showing another's data` : '',
);

// --- the pages must be readable without JavaScript --------------------------
// The entire point: the map is client-side, so if these needed JS too they
// would add nothing a crawler can see.
// EVERY page, not pages[0] (2026-08-31, audit I10). These two ran on
// `pages[0]` alone - always area/bristol/bath-and-north-east-somerset - so 98
// of 99 pages were unchecked on the property the comment above calls "the
// entire point". Proven: given `<script src="https://evil.example/t.js">` and
// their score text stripped from 98 pages, all three checks passed and the file
// exited 0. The loop below already reads every file for the duplicate-block
// check, so this costs nothing.
const noScript = [];
const noScore = [];
const badCta = [];
for (const pg of pages) {
  const html = readFileSync(pg.file, 'utf8');
  if (/<script/i.test(html)) noScript.push(pg.url);
  if (!/Sky Score out of 10/.test(html)) noScore.push(pg.url);
  // THE CALL-TO-ACTION MUST CARRY THE BOROUGH (2026-08-31, audit D1). Every
  // page links to `/?city=<key>&borough=<Name>`, and index.html read `city`
  // and never `borough` - so the one link the whole SEO surface exists to
  // provide switched to the right city and then showed the empty state. The
  // reader is fixed; this asserts the WRITER still emits what it reads.
  // The `area/index.html` listing page has no per-borough CTA, so it is
  // excluded by only testing pages that carry the score line.
  // Excluded BY URL, not by content. Gating this on the score line being
  // present meant a page that failed the score check silently vanished from
  // this one too - one assertion becoming an escape hatch from another, which
  // is the shape this file exists to catch. Found while red-proofing it.
  if (pg.url !== '/area/' && !/href="\/\?city=[^"]*&amp;borough=[^"]+"/.test(html)) {
    badCta.push(pg.url);
  }
}
check(
  'every page carries no script tag',
  noScript.length === 0,
  noScript.length ? `${noScript.length} page(s) carry <script>: ${noScript.slice(0, 3).join(', ')}` : `${pages.length} checked`,
);
check(
  'every page has the score in served HTML',
  noScore.length === 0,
  noScore.length ? `${noScore.length} page(s) missing it: ${noScore.slice(0, 3).join(', ')}` : `${pages.length} checked`,
);
check(
  'every CTA deep-links to a borough',
  badCta.length === 0,
  badCta.length ? `${badCta.length} page(s) link without &borough=: ${badCta.slice(0, 3).join(', ')}` : `${pages.length - badCta.length} checked`,
);

console.log('');
if (failures.length) {
  console.error(`FAIL: ${failures.length} check(s) failed`);
  for (const f of failures) console.error(`  - ${f}`);
  process.exit(1);
}
console.log(`OK: ${pages.length} area pages, real data, sitemap agrees\n`);
