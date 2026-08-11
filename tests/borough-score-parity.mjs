// Site vs Lambda, on the OUTPUT, for every borough of every shared city.
//
// WHY THIS EXISTS
// ---------------
// test_borough_data_parity.py compares the INPUTS the two holders carry, and it
// is not enough. All ten Greater Manchester boroughs once disagreed with
// /v1/score by up to 1.5 points while both holders HELD identical inputs,
// because the site never loaded them into the object it scores from. An input
// check cannot see that; only reading the number the page renders can.
//
// tests/site-api-parity.mjs is the other output check, but it hits the LIVE API
// on six LONDON postcodes. This one runs against the SOURCE tree and covers
// every borough of every city, so it gates a deploy where that one catches a
// bad one.
//
// Promoting a city out of BACKEND_ONLY_CITIES is a ONE-WAY DOOR and this is the
// gate it has to pass first.
import { chromium } from 'playwright';
import { execFileSync } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const PORT = 8931;
const TOL = 0.05; // both sides round to 1dp, so anything real is >= 0.1

const TYPES = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.mjs': 'application/javascript',
  '.json': 'application/json',
  '.css': 'text/css',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.webmanifest': 'application/manifest+json',
};

// The Lambda is the reference. Dumped by running its own calc_score, not by
// re-reading its data - a comparison against the inputs is the thing this test
// exists to improve on.
const PY = `
import json, sys
sys.path.insert(0, 'backend/lambdas/score')
import app
out = {}
for city, cfg in app.CITIES.items():
    out[city] = {}
    for b in cfg['boroughs']:
        out[city][b] = app.calc_score(b, city, app.PERSONAS['balanced'])['score']
# The site keys some boroughs by a shorter name than the Lambda's canonical -
# London's holder says 'Barking', the Lambda says 'Barking and Dagenham'. That
# is a NAMING difference, not a scoring one, so the alias table the Lambda
# already maintains is exported rather than a match being invented here.
print(json.dumps({'scores': out, 'aliases': app.BOROUGH_ALIASES}))
`;
const dumped = JSON.parse(execFileSync('python', ['-c', PY], { encoding: 'utf-8', cwd: ROOT }));
const lambdaScores = dumped.scores;
// canonical -> every site-side spelling that resolves to it
const altNames = {};
for (const [alias, canonical] of Object.entries(dumped.aliases)) {
  (altNames[canonical] ||= []).push(alias);
}

const server = http.createServer((req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]);
  if (p === '/') p = '/index.html';
  const file = path.join(ROOT, p);
  if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    res.writeHead(404).end('not found');
    return;
  }
  res.writeHead(200, { 'content-type': TYPES[path.extname(file)] || 'application/octet-stream' });
  fs.createReadStream(file).pipe(res);
});
await new Promise((r) => server.listen(PORT, r));

const browser = await chromium.launch();
const page = await browser.newPage();
const pageErrors = [];
page.on('pageerror', (e) => pageErrors.push(String(e)));
await page.goto(`http://localhost:${PORT}/index.html`, { waitUntil: 'networkidle' });

// Cities the SITE has, intersected with the Lambda's. Derived from the page's
// own registry so a city added to CITY_DATA is covered with no edit here.
// Bare identifiers, not window.*: index.html's registries are top-level
// `const` in a classic script, which binds in the global LEXICAL environment
// and is reachable by name but absent from `window`. Reading window.CITY_DATA
// yields undefined and this compared 0 boroughs while exiting 0-adjacent.
const siteCities = await page.evaluate(() => Object.keys(CITY_DATA));
const shared = siteCities.filter((c) => lambdaScores[c]);

const failures = [];
let compared = 0;
for (const city of shared) {
  await page.evaluate((c) => {
    // Country tab first, exactly as the chip row does - switchCity alone
    // leaves the two-tier selector inconsistent.
    if (typeof switchCountry === 'function') switchCountry(CITY_DATA[c].country);
    switchCity(c);
  }, city);
  // borough-extra hydrates asynchronously; scoring before it lands compares
  // the site's DEFAULT scores and passes for the wrong reason.
  await page.waitForFunction(() => _boroughExtraHydrated === true, null, { timeout: 15000 });
  const siteScores = await page.evaluate((c) => {
    const scored = CITY_DATA[c].boroughData();
    const out = {};
    for (const [name, d] of Object.entries(scored)) out[name] = d.score ?? null;
    return out;
  }, city);

  for (const [borough, want] of Object.entries(lambdaScores[city])) {
    let got = siteScores[borough];
    if (got === undefined) {
      for (const alt of altNames[borough] || []) {
        if (siteScores[alt] !== undefined) {
          got = siteScores[alt];
          break;
        }
      }
    }
    compared += 1;
    if (got === undefined || got === null) {
      failures.push(`${city}/${borough}: site renders no score (Lambda ${want})`);
    } else if (Math.abs(got - want) > TOL) {
      failures.push(`${city}/${borough}: site ${got} vs Lambda ${want} (${(got - want).toFixed(1)})`);
    }
  }
}

await browser.close();
server.close();

if (pageErrors.length) {
  console.log('PAGE ERRORS (a throw here means a city is broken, not merely adrift):');
  pageErrors.slice(0, 8).forEach((e) => console.log('  ' + e));
}

console.log(`compared ${compared} boroughs across ${shared.length} cities: ${shared.join(', ')}`);

// A run that measures almost nothing is a failure, not a pass - the same guard
// site-api-parity.mjs carries, for the same reason.
if (compared < 60) {
  console.log(`FAIL: only ${compared} boroughs compared; expected the full set.`);
  process.exit(1);
}
if (pageErrors.length || failures.length) {
  console.log(`\nFAIL: ${failures.length} borough(s) disagree`);
  failures.slice(0, 40).forEach((f) => console.log('  ' + f));
  process.exit(1);
}
console.log('PASS: the site and the Lambda agree on every borough.');
