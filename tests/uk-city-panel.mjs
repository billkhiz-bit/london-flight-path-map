/**
 * Run an area search in a NON-LONDON UK city and assert it gets UK content.
 *
 * Why this exists
 * ---------------
 * `updateSidebarPostcode()` branched `currentCity === 'london' ? … : …` and the
 * ELSE-BRANCH WAS NEW YORK'S. So an area search in Manchester, Birmingham,
 * Leeds, Sheffield, Liverpool, Newcastle, Bristol, Leicester or Teesside
 * answered:
 *
 *     NEAREST SUBWAY STATIONS
 *     NYC subway data coming soon. Check MTA.info for schedules.
 *
 * A heading naming one city over a page showing another. Those nine also lost
 * EPC and sold prices, under a comment reading "London only - these APIs are
 * UK-specific", which is the reverse of true: EPC and HM Land Registry are
 * UK-wide. And because the sold-prices CONTAINER is emitted by
 * buildPropertyLinks() for every UK city while the FETCH was London-gated, all
 * nine sat on "Loading from Land Registry..." that could never resolve.
 *
 * The 1,771 NaPTAN stations built on 2026-08-12 to fix exactly this were
 * unreachable: nearestStations() had one call site, inside renderTransportData(),
 * which was only ever called from the London branch. The data shipped, the
 * renderer shipped, nothing joined them.
 *
 * Why NOTHING caught it
 * ---------------------
 * The audit of 2026-08-21 put it plainly: no gate had ever exercised the
 * non-London area-search path. `borough-score-parity` compares boroughs by
 * SCORE, `city-switch` clicks the chip and checks the MAP. Both pass with this
 * panel showing another continent's transit system, because neither one ever
 * types a postcode.
 *
 * What it asserts, and why each one
 * ---------------------------------
 *   - no New York text in a UK city      the defect itself, stated directly
 *   - stations render with real NAMES    "the section exists" is satisfied by a
 *                                        spinner; only a name proves NaPTAN was
 *                                        reached. Assert on DATA, not shape -
 *                                        the /transport lesson from the same day
 *   - nothing is still "Loading..."      an unresolved spinner is the same lie
 *                                        as a confident empty list, just slower
 *   - London is UNCHANGED                the fix must not cost London its live
 *                                        TfL panel
 *   - NYC still gets its own copy        the NYC message was never wrong FOR
 *                                        NYC; NaPTAN is UK-only and NYC_STATIONS
 *                                        is legitimately empty
 *
 * Driven off CITY_DATA's `country`, not a hardcoded city list - a list is one
 * more place to forget, and forgetting is what shipped this.
 *
 *   node tests/uk-city-panel.mjs
 *   node tests/uk-city-panel.mjs https://skyscore.co.uk/   (verify a deploy)
 */
import { chromium } from '@playwright/test';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';

const ROOT = process.cwd();
// 8123, 8921, 8922, 8923 and 8924 are taken by the other harnesses and preflight
// runs these in one block; a shared port dies with EADDRINUSE, which reads as a
// panel failure and is not one.
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

const TARGET = process.argv[2] || null;

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
if (!TARGET) await new Promise((r) => server.listen(PORT, r));
const url = TARGET || `http://localhost:${PORT}/index.html`;

// One real postcode per city under test. Real because the panel resolves them
// through postcodes.io, and an invented postcode fails for a reason that has
// nothing to do with what is being tested.
// TAKEN FROM scripts/check_score_sanity.py, which probes one postcode per city
// against the live API on every preflight - so these are known to resolve and
// known to belong to the city claimed. Inventing plausible ones instead cost a
// run here: `B1 1AA` and `LS1 1AA` look like Birmingham and Leeds city centre
// and postcodes.io 404s both, which failed this file for a reason that had
// nothing to do with the panel it tests.
const CASES = [
  { city: 'manchester', postcode: 'M1 1AE', uk: true },
  { city: 'westmidlands', postcode: 'B15 2TT', uk: true },
  { city: 'westyorkshire', postcode: 'LS1 4DY', uk: true },
  { city: 'london', postcode: 'SW11 1AA', uk: true, london: true },
  { city: 'nyc', postcode: '10001', uk: false },
];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));

await page.goto(url, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(3000);

const failures = [];
function check(name, pass, detail) {
  console.log(`  ${pass ? 'PASS' : 'FAIL'}  ${name}${detail ? '  ' + detail : ''}`);
  if (!pass) failures.push(`${name}: ${detail}`);
}

console.log('\nNon-London area-search panel\n============================\n');

for (const c of CASES) {
  await page.evaluate((city) => window.switchCity(city), c.city);
  await page.waitForTimeout(1200);
  await page.fill('#search-input', c.postcode);
  await page.press('#search-input', 'Enter');
  // The panel fans out to postcodes.io, EPC and Land Registry; 6s is what the
  // slowest of those needs from a cold container.
  await page.waitForTimeout(6000);

  const panel = await page.evaluate(() => {
    const sb = document.querySelector('#sidebar') || document.body;
    const t = document.getElementById('postcode-transport-data');
    return {
      text: sb.innerText,
      transport: t ? t.innerText.trim() : null,
      stationNames: t
        ? Array.from(t.querySelectorAll('.station-name')).map((n) => n.textContent.trim())
        : [],
      epc: !!document.getElementById('postcode-epc-data'),
      nhs: !!document.getElementById('postcode-nhs-data'),
    };
  });

  console.log(`${c.city} (${c.postcode})`);

  if (c.uk) {
    check(
      `  ${c.city}: no New York content`,
      !/subway|MTA\.info/i.test(panel.text),
      /subway|MTA\.info/i.test(panel.text) ? 'panel mentions the NYC subway' : '',
    );
    // DATA, not shape. A rendered section with a spinner in it satisfies
    // "the element exists"; only a station NAME proves the register was read.
    check(
      `  ${c.city}: stations have real names`,
      panel.stationNames.length > 0,
      panel.stationNames.length
        ? `${panel.stationNames.length}: ${panel.stationNames.slice(0, 2).join(', ')}`
        : `transport panel reads "${(panel.transport || '').slice(0, 60)}"`,
    );
    check(
      `  ${c.city}: nothing stuck loading`,
      !/Loading from|Finding nearest/i.test(panel.text),
      /Loading from|Finding nearest/i.test(panel.text) ? 'a spinner never resolved' : '',
    );
    check(`  ${c.city}: EPC section present`, panel.epc, '');
    // London keeps its NHS panel; the others do not have one yet, and an
    // ABSENT section is the honest state while /nhs has an open concurrency
    // fault. Asserted in both directions so "we quietly enabled it" and "we
    // quietly lost it" both fail.
    check(
      `  ${c.city}: NHS present iff London`,
      panel.nhs === Boolean(c.london),
      `nhs=${panel.nhs} london=${Boolean(c.london)}`,
    );
  } else {
    check(
      `  ${c.city}: keeps its own transit copy`,
      /subway/i.test(panel.text),
      'NYC must still say subway - NaPTAN is UK-only',
    );
  }
  console.log('');
}

check('no page errors', errors.length === 0, errors.slice(0, 2).join(' | '));

await browser.close();
if (!TARGET) server.close();

if (failures.length) {
  console.error(`\nFAIL: ${failures.length} check(s) failed`);
  for (const f of failures) console.error(`  - ${f}`);
  process.exit(1);
}
console.log('\nOK: every UK city gets UK content, NYC keeps its own\n');
