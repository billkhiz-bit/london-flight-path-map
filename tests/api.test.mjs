// I-N5: the browser pages pull API_BASE from /js/api-base.js (window global).
// This test runs in Node where window does not exist, so the value is
// duplicated here. The /preflight drift check (step 4d) grep-asserts that
// every API URL reference in the repo resolves to one host, so any drift
// between this constant and js/api-base.js fails preflight.
const API_BASE = 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod';

const endpoints = [
  {
    name: 'sold-prices',
    method: 'GET',
    path: '/sold-prices?postcode=SW11+1AA',
  },
  {
    name: 'transport',
    method: 'GET',
    path: '/transport?postcode=SW11+1AA',
  },
  {
    name: 'epc',
    method: 'GET',
    path: '/epc?postcode=SW11+1AA',
  },
  {
    name: 'nhs',
    method: 'GET',
    path: '/nhs?postcode=SW11+1AA',
  },
  {
    name: 'favourites (GET)',
    method: 'GET',
    path: '/favourites',
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
    const pass = res.status >= 200 && res.status < 500;
    return { name: ep.name, status: res.status, elapsed, pass };
  } catch (err) {
    const elapsed = Math.round(performance.now() - start);
    return { name: ep.name, status: 'ERR', elapsed, pass: false, error: err.message };
  }
}

async function main() {
  console.log(`\nAPI Integration Tests — ${API_BASE}\n`);
  console.log('-'.repeat(60));

  const results = await Promise.all(endpoints.map(testEndpoint));

  let allPass = true;
  for (const r of results) {
    const icon = r.pass ? 'PASS' : 'FAIL';
    const line = `[${icon}] ${r.name.padEnd(20)} status=${String(r.status).padEnd(4)} ${r.elapsed}ms`;
    console.log(line);
    if (r.error) console.log(`       Error: ${r.error}`);
    if (!r.pass) allPass = false;
  }

  console.log('-'.repeat(60));
  console.log(allPass ? '\nAll endpoints passed.\n' : '\nSome endpoints failed.\n');
  process.exit(allPass ? 0 : 1);
}

main();
