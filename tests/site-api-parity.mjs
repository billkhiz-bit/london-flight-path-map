// Compare the score the LIVE SITE renders against the score /v1/score returns,
// for the same postcode. Exits non-zero on any measured disagreement.
//
// WHY THIS EXISTS (2026-08-04). Three site/API divergences have now shipped,
// and each survived because every guard compared INPUTS rather than the OUTPUT:
//
//   * SiteApiGeometryParityTests compares flight-path waypoints.
//   * tests/test_persona_parity.py compares persona weights.
//   * The ad-hoc probes during the raster incident compared COMPONENTS.
//
// The third divergence was invisible to all of them. On SW11 1AA the site
// rendered 6.5 against the API's 6.4 while every component matched exactly
// (5 / 6.7 / 4.3 / 8) - calcScores rounds components to 1dp for display and the
// postcode panel recombined those ROUNDED values, double-rounding, where the
// API sums at full precision and rounds once. 4 of 30 random London postcodes
// (13%) disagreed, in both directions.
//
// A parity check that validates the inputs does not validate the output. This
// is the only check that reads the number a user actually sees and the number a
// customer actually receives, and compares those two.
//
// Run:
//   node tests/site-api-parity.mjs
//   SMOKE_BASE=... SKY_SCORE_API_KEY=... node tests/site-api-parity.mjs
//
// NOTE it compares deployed-against-deployed. If you have changed index.html
// locally and not deployed it, this still passes - it is not a source check.
// scripts/check_deploy_drift.sh is the one that notices that.

import { chromium } from '@playwright/test';

const SITE = process.env.SMOKE_BASE || 'https://d1oe4ftwutjpf.cloudfront.net';
const API =
  process.env.SKY_SCORE_API ||
  'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod';
// Same public demo key scripts/check_score_sanity.py defaults to.
const KEY = process.env.SKY_SCORE_API_KEY || 'avPkPw4yug7JbZ9XSEyuZsH8F79n7h12qeUoTXDe';

// Chosen for coverage of the failure modes, not at random:
//   SW11 1AA  the postcode the double-rounding defect was found on
//   W3 7BN    diverged in the opposite direction (site read high)
//   SW12 0DL  diverged with the site reading LOW, so a one-sided fix fails here
//   TW6 1AP   inside Heathrow; the airport invariant's postcode
//   SE18 6NQ  London City catchment, where the raster and Haversine disagree most
//   N1 7SX    ordinary inner London; the worked example in README
const POSTCODES = process.env.POSTCODES
  ? process.env.POSTCODES.split(',').map((s) => s.trim())
  : ['SW11 1AA', 'W3 7BN', 'SW12 0DL', 'TW6 1AP', 'SE18 6NQ', 'N1 7SX'];

// If fewer than this fraction of probes return, the run is a FAILURE, not a
// pass with a small sample. Same discipline as check_score_sanity.py: a check
// that quietly measures nothing is the failure mode this repo keeps hitting.
const MIN_COVERAGE = 0.8;

const LABEL_TO_COMPONENT = {
  'quiet skies': 'quiet',
  affordability: 'afford',
  growth: 'growth',
  liveability: 'live',
};

const one = (n) => Math.round(n * 10) / 10;

async function fetchApi(postcode) {
  const url = `${API}/v1/score?postcode=${encodeURIComponent(postcode)}`;
  const resp = await fetch(url, { headers: { 'X-Api-Key': KEY, Accept: 'application/json' } });
  if (!resp.ok) throw new Error(`API ${resp.status}`);
  return resp.json();
}

async function readSite(page, postcode) {
  const input = page.locator('#search-input');
  await input.fill('');
  await input.fill(postcode);
  await input.press('Enter');

  // Wait for the title to settle away from the transient SEARCHING... state.
  let title = '';
  for (let i = 0; i < 40; i++) {
    await page.waitForTimeout(250);
    title = (await page.locator('#sidebar-title').textContent()) || '';
    if (title.trim() && !/SEARCHING/i.test(title)) break;
  }
  if (/NOT FOUND|CONNECTION/i.test(title)) throw new Error(`site: ${title.trim()}`);

  const verdict =
    (await page.locator('.summary-verdict').first().textContent().catch(() => '')) || '';
  const m = verdict.match(/(\d+(?:\.\d+)?)\s*\/\s*10/);
  if (!m) throw new Error('site: no total in verdict');

  const rows = await page.evaluate(() => {
    const out = {};
    document.querySelectorAll('.score-row').forEach((r) => {
      const label = r.querySelector('.score-row-label')?.textContent?.trim();
      const value = r.querySelector('.score-row-value')?.textContent?.trim();
      if (label && value) out[label.toLowerCase()] = value;
    });
    return out;
  });

  const components = {};
  for (const [label, key] of Object.entries(LABEL_TO_COMPONENT)) {
    const raw = rows[label];
    if (raw == null) continue;
    const v = parseFloat(String(raw).split('/')[0]);
    if (Number.isFinite(v)) components[key] = v;
  }

  return { total: parseFloat(m[1]), components };
}

const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(`${SITE}/index.html`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('#app', { state: 'visible', timeout: 30000 });

console.log('SITE / API PARITY');
console.log('=================');
console.log(`  site: ${SITE}`);
console.log(`  api : ${API}\n`);

let measured = 0;
const divergences = [];
const skipped = [];

for (const pc of POSTCODES) {
  let site, api;
  try {
    [site, api] = await Promise.all([readSite(page, pc), fetchApi(pc)]);
  } catch (e) {
    skipped.push(`${pc}: ${e.message}`);
    console.log(`  ${pc.padEnd(10)} SKIP  ${e.message}`);
    continue;
  }
  measured++;

  const problems = [];
  if (one(site.total) !== one(api.score)) {
    problems.push(`total site ${one(site.total)} vs api ${one(api.score)}`);
  }
  for (const [key, siteVal] of Object.entries(site.components)) {
    const apiVal = api.components?.[key];
    if (apiVal == null) continue;
    if (one(siteVal) !== one(apiVal)) {
      problems.push(`${key} site ${one(siteVal)} vs api ${one(apiVal)}`);
    }
  }

  if (problems.length) {
    divergences.push({ pc, problems });
    console.log(`  ${pc.padEnd(10)} DIVERGE  ${problems.join('; ')}`);
  } else {
    console.log(
      `  ${pc.padEnd(10)} OK       ${one(api.score)}/10  ` +
        `(q ${one(api.components.quiet)} af ${one(api.components.afford)} ` +
        `gr ${one(api.components.growth)} live ${one(api.components.live)})`
    );
  }
}

await browser.close();

const coverage = measured / POSTCODES.length;
console.log('');

if (coverage < MIN_COVERAGE) {
  console.log(
    `FAIL: only ${measured}/${POSTCODES.length} probes returned ` +
      `(need ${Math.ceil(MIN_COVERAGE * POSTCODES.length)}).`
  );
  console.log('A run that measures almost nothing is a failure, not a pass.');
  skipped.forEach((s) => console.log(`  skipped: ${s}`));
  process.exit(1);
}

if (divergences.length) {
  console.log(`FAIL: ${divergences.length} of ${measured} postcodes disagree.`);
  console.log('The site and /v1/score must answer the same number for the same');
  console.log('postcode. Check rounding order before assuming a data problem:');
  console.log('components can match exactly while the total does not.');
  process.exit(1);
}

console.log(`PASS: ${measured} postcodes, site and API agree on every component and total.`);
process.exit(0);
