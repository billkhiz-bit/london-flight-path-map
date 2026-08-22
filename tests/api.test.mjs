// Pre-release API integration gate.
//
// REWRITTEN 2026-08-22, audit finding I4. What it used to do:
//
//     const pass = res.status >= 200 && res.status < 500;
//
// Every 4xx was a pass. Measured live on the day it was fixed, `/transport` and
// `/nhs` were BOTH returning 400 and both reported PASS - they take `lat`/`lon`
// and this file had always sent `postcode`, so two of the five endpoints in the
// pre-release gate had never once been exercised. `/favourites` returned 401
// for the same reason a locked door does, which is correct, but nothing here
// distinguished that from a broken route.
//
// The rule this repo keeps relearning: ASSERT ON DATA, NOT SHAPE. A 200 with an
// empty array satisfies a status check while proving nothing. `/sold-prices`
// was queried at SW11 1AA, which genuinely has no recorded sales, so even the
// endpoint that DID answer 200 was being proved by an empty list - the same
// trap that once let /sold-prices pass 24/24 having never returned a
// transaction.
//
// So each endpoint now declares the status it must return AND a predicate over
// the body that fails when the payload is empty. Probes are chosen because they
// have data: N1 7SX has 10 sales and 79 certificates, Oxford Circus has 5
// stations and 6 line statuses. Re-measure before changing one.

// I-N5: the browser pages pull API_BASE from /js/api-base.js (window global).
// This test runs in Node where window does not exist, so the value is
// duplicated here. The /preflight drift check (step 4d) grep-asserts that
// every API URL reference in the repo resolves to one host, so any drift
// between this constant and js/api-base.js fails preflight.
const API_BASE = 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod';

// Oxford Circus. Central enough that zero stations or zero line statuses is a
// fault rather than a quiet corner of the network.
const LAT = 51.5152;
const LON = -0.1418;

const size = (v) => (Array.isArray(v) ? v.length : 0);

const endpoints = [
  {
    name: 'sold-prices',
    method: 'GET',
    // NOT SW11 1AA. That postcode has no recorded sales, so it returns 200 with
    // an empty array and cannot fail. N1 7SX had 10 transactions when measured.
    path: '/sold-prices?postcode=N1+7SX',
    expect: 200,
    wants: 'at least one transaction',
    check: (b) => size(b.transactions) > 0,
  },
  {
    name: 'transport',
    method: 'GET',
    // lat/lon, NOT postcode. Sending postcode returned 400 and passed, for
    // however long this file has existed.
    path: `/transport?lat=${LAT}&lon=${LON}`,
    expect: 200,
    wants: 'at least one station AND one line status',
    // lineStatus is asserted separately from stations on purpose: TfL 403s a
    // missing User-Agent and the handler turns that into [], which is how a
    // suspended Central line rendered as "no disruptions" for the whole life of
    // the endpoint. An empty lineStatus must never be a pass again.
    check: (b) => size(b.stations) > 0 && size(b.lineStatus) > 0,
  },
  {
    name: 'epc',
    method: 'GET',
    path: '/epc?postcode=N1+7SX',
    expect: 200,
    wants: 'at least one certificate',
    check: (b) => size(b.certificates) > 0,
  },
  {
    name: 'nhs',
    method: 'GET',
    path: `/nhs?lat=${LAT}&lon=${LON}`,
    expect: 200,
    wants: 'at least one GP, pharmacy or hospital',
    check: (b) => size(b.gp) + size(b.pharmacies) + size(b.hospitals) > 0,
  },
  {
    name: 'favourites (no token)',
    method: 'GET',
    path: '/favourites',
    // 401 is the CORRECT answer here and the assertion is deliberate: this row
    // proves the device-token gate is still shut. A 200 would be a security
    // defect, and under the old `< 500` rule it would have passed identically.
    expect: 401,
    wants: 'an error explaining the missing device token',
    check: (b) => typeof b.error === 'string' && b.error.length > 0,
  },
  // /chat and /report POST cases removed 2026-05-07 — the API Gateway
  // routes were closed in commit 71a731c after the smoke-test caught
  // them as cost-abuse vectors. Re-add ONLY if the corresponding Events
  // blocks are restored in template.yaml.
];

async function testEndpoint(ep) {
  const url = `${API_BASE}${ep.path}`;
  const start = performance.now();
  try {
    const res = await fetch(url, {
      method: ep.method,
      headers: ep.headers || {},
      body: ep.body || undefined,
    });
    const elapsed = Math.round(performance.now() - start);
    const text = await res.text();

    if (res.status !== ep.expect) {
      return { ...ep, status: res.status, elapsed, pass: false,
               why: `expected HTTP ${ep.expect}` };
    }

    let body;
    try {
      body = JSON.parse(text);
    } catch {
      return { ...ep, status: res.status, elapsed, pass: false,
               why: `body is not JSON: ${text.slice(0, 80)}` };
    }

    if (!ep.check(body)) {
      // The payload is what failed, so print it. A gate that says only "failed"
      // on a data assertion sends you back to the terminal to re-run it by hand.
      return { ...ep, status: res.status, elapsed, pass: false,
               why: `wanted ${ep.wants}; got ${JSON.stringify(body).slice(0, 160)}` };
    }
    return { ...ep, status: res.status, elapsed, pass: true };
  } catch (err) {
    const elapsed = Math.round(performance.now() - start);
    return { ...ep, status: 'ERR', elapsed, pass: false, why: err.message };
  }
}

async function main() {
  console.log(`\nAPI Integration Tests — ${API_BASE}`);
  console.log('Asserting on payload contents, not status class.\n');
  console.log('-'.repeat(70));

  const results = await Promise.all(endpoints.map(testEndpoint));

  let allPass = true;
  for (const r of results) {
    const icon = r.pass ? 'PASS' : 'FAIL';
    console.log(`[${icon}] ${r.name.padEnd(22)} status=${String(r.status).padEnd(4)} ${String(r.elapsed).padStart(5)}ms  ${r.pass ? r.wants : ''}`);
    if (!r.pass) console.log(`       ${r.why}`);
    if (!r.pass) allPass = false;
  }

  console.log('-'.repeat(70));
  console.log(allPass ? '\nAll endpoints returned real data.\n' : '\nSome endpoints failed.\n');
  process.exit(allPass ? 0 : 1);
}

main();
