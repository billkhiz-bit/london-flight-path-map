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
# BACKEND_ONLY_CITIES has ONE holder, tests/test_borough_data_parity.py,
# whose own test asserts it is declared rather than discovered. READ from
# that file rather than copied here: a second copy is correct the day it
# is written and wrong at the next one-way door. Parsed rather than
# imported because that module uses a package-relative conftest import
# and will not load standalone.
import ast
_src = open('tests/test_borough_data_parity.py', encoding='utf-8').read()
backend_only = None
for _n in ast.walk(ast.parse(_src)):
    if isinstance(_n, ast.Assign) and any(
            getattr(t, 'id', None) == 'BACKEND_ONLY_CITIES' for t in _n.targets):
        _v = _n.value
        _v = _v.args[0] if isinstance(_v, ast.Call) and _v.args else _v
        backend_only = set(ast.literal_eval(_v))
if backend_only is None:
    raise SystemExit('BACKEND_ONLY_CITIES not found in its holder - the floor below cannot tell a deliberate absence from a regression')
out = {}
for city, cfg in app.CITIES.items():
    out[city] = {}
    for b in cfg['boroughs']:
        out[city][b] = app.calc_score(b, city, app.PERSONAS['balanced'])['score']
# The site keys some boroughs by a shorter name than the Lambda's canonical -
# London's holder says 'Barking', the Lambda says 'Barking and Dagenham'. That
# is a NAMING difference, not a scoring one, so the alias table the Lambda
# already maintains is exported rather than a match being invented here.
# BACKEND_ONLY_CITIES is exported so the floor below can tell a city that
# is DELIBERATELY absent from the site from one that has silently fallen
# out of CITY_DATA - which used to shrink this comparison without
# failing it.
print(json.dumps({'scores': out, 'aliases': app.BOROUGH_ALIASES,
                  'backendOnly': sorted(backend_only)}))
`;
const dumped = JSON.parse(execFileSync('python', ['-c', PY], { encoding: 'utf-8', cwd: ROOT }));
const lambdaScores = dumped.scores;
const BACKEND_ONLY = dumped.backendOnly;
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

// THE FLOOR, AND IT IS DERIVED (2026-09-07 audit, I13).
//
// This was `compared < 60` against a real total of 91, and there was no floor
// at all on `shared.length`. So Greater Manchester (10), West Midlands (7),
// Leicester (8) and Teesside (5) could ALL drop out of CITY_DATA together and
// this still printed "PASS: the site and the Lambda agree on every borough" -
// the one-way-door guarantee, asserted over two thirds of the boroughs.
//
// The expectation is now the boroughs the Lambda actually serves for the
// cities the site actually offers, so it tracks a city being added or removed
// with no edit here, and a CITY DROPPING OUT of the site is caught by the
// second check rather than silently shrinking the first.
const expectedCities = Object.keys(lambdaScores).filter((c) => !BACKEND_ONLY.includes(c));
const missingCities = expectedCities.filter((c) => !shared.includes(c));
if (missingCities.length) {
  console.log(`FAIL: the site no longer offers ${missingCities.join(', ')}, which the`);
  console.log('      Lambda scores and which are not declared backend-only. A city');
  console.log('      that vanishes from CITY_DATA takes its boroughs out of this');
  console.log('      comparison without failing it.');
  process.exit(1);
}
const expected = shared.reduce((n, c) => n + Object.keys(lambdaScores[c]).length, 0);
if (compared !== expected) {
  console.log(`FAIL: compared ${compared} boroughs, but the Lambda serves ${expected}`);
  console.log(`      across those ${shared.length} cities. Every borough the API scores`);
  console.log('      must be rendered and compared - a borough the site cannot draw is');
  console.log('      exactly the divergence this gate exists to catch.');
  process.exit(1);
}
if (pageErrors.length || failures.length) {
  console.log(`\nFAIL: ${failures.length} borough(s) disagree`);
  failures.slice(0, 40).forEach((f) => console.log('  ' + f));
  process.exit(1);
}
console.log('PASS: the site and the Lambda agree on every borough.');
