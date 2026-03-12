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
  {
    name: 'chat (POST)',
    method: 'POST',
    path: '/chat',
    body: JSON.stringify({ message: 'Hello', history: [] }),
    headers: { 'Content-Type': 'application/json' },
  },
  {
    name: 'report (POST)',
    method: 'POST',
    path: '/report',
    body: JSON.stringify({ area: 'Chelsea', borough: 'Kensington and Chelsea' }),
    headers: { 'Content-Type': 'application/json' },
  },
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
