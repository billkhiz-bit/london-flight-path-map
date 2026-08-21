/**
 * The public demo key must reach /v1/score and NOTHING ELSE.
 *
 * WHY THIS EXISTS. An API Gateway key authorises at the STAGE, not per route.
 * Every method carrying `ApiKeyRequired: true` is reachable by a key on ANY
 * usage plan attached to that stage. The demo key is printed in the page source
 * of score-demo/index.html, so until 2026-08-21 it also opened:
 *
 *   POST /v1/chat         a Bedrock model billed to this account
 *   POST /v1/score/batch  100 scores per metered request
 *
 * The fix is a per-method `Throttle` map on ScoreDemoUsagePlan with RateLimit 0,
 * which is the only declarative way to keep a key off a route.
 *
 * WHY IT IS A LIVE TEST AND NOT A TEMPLATE ASSERTION. Reading `RateLimit: 0`
 * back out of template.yaml would be an expectation read from the code under
 * test - this repo's most-repeated defect, six instances and counting. The
 * question is not whether the YAML says 0, it is whether API Gateway TREATS 0
 * as deny rather than as "unlimited". Only the running API can answer that, and
 * if the answer ever changes this file goes red while the template still looks
 * correct.
 *
 * Run: node tests/demo-key-scope.mjs
 */

const API = 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod';

// The key from score-demo/index.html. Public by design - it is served in page
// source to every visitor. Hardcoded here ON PURPOSE: this test asserts what
// THAT key can reach, so reading it from the environment would let a different
// key silently satisfy the test.
const DEMO_KEY = 'avPkPw4yug7JbZ9XSEyuZsH8F79n7h12qeUoTXDe';

const BLOCKED_STATUS = new Set([403, 429]);

async function call(path, { method = 'GET', body = null } = {}) {
  const headers = { 'X-Api-Key': DEMO_KEY };
  if (body) headers['Content-Type'] = 'application/json';
  const res = await fetch(`${API}${path}`, { method, headers, body });
  let text = '';
  try {
    text = await res.text();
  } catch {
    /* body is not required to reach a verdict */
  }
  return { status: res.status, bytes: text.length, text };
}

const failures = [];
function check(name, pass, detail) {
  console.log(`  ${pass ? 'PASS' : 'FAIL'}  ${name}  ${detail}`);
  if (!pass) failures.push(`${name}: ${detail}`);
}

console.log('\nDemo key scope\n==============\n');

// 1. The route the key EXISTS for must still work. Asserted first and asserted
//    on DATA: a scoping change that breaks the demo is a worse outcome than the
//    hole it closes, and a 200 with an error body would satisfy a status check.
{
  const r = await call('/v1/score?postcode=SW11+1AA');
  let scored = false;
  try {
    scored = typeof JSON.parse(r.text).score === 'number';
  } catch {
    /* leaves scored false, which fails below */
  }
  // A CONSUMABLE MUST NEVER BLOCK A COMMIT. This is the only assertion here
  // that spends demo quota - the two denials below are throttled at the edge
  // and API Gateway does not meter a throttled request - and the quota it
  // spends belongs to the MARKETING FUNNEL, not to CI.
  //
  // preflight.sh already carries the scar: `score sanity` hardcoded this key,
  // and when the 2,000/month ran out every commit in the repo was blocked by an
  // exhausted counter rather than by a defect. So an exhausted quota degrades
  // to a warning here. The security assertions below do NOT degrade - they cost
  // nothing, so nothing can wear them down.
  if (r.status === 429) {
    console.log(
      '  WARN  GET /v1/score not verified - demo quota exhausted (429).' +
        ' Not failing: this is a consumable, and the boundary checks below' +
        ' are unaffected because a throttled request is never metered.',
    );
  } else {
    check(
      'GET /v1/score still returns a score',
      r.status === 200 && scored,
      `status=${r.status} scored=${scored}`,
    );
  }
}

// 2. Batch must be refused. 100 scores per metered request is 20x the Free tier
//    for a key that costs nobody an email address.
{
  const r = await call('/v1/score/batch', {
    method: 'POST',
    body: JSON.stringify({ queries: [{ postcode: 'SW11 1AA' }] }),
  });
  check(
    'POST /v1/score/batch is refused',
    BLOCKED_STATUS.has(r.status),
    `status=${r.status}${r.status === 200 ? ' <- RATE 0 IS NOT DENYING' : ''}`,
  );
}

// 3. Chat must be refused. This one spends Bedrock credit on every success, so
//    the probe deliberately sends a question that would be cheap and obviously
//    non-product if it ever DID get through.
{
  const r = await call('/v1/chat', {
    method: 'POST',
    body: JSON.stringify({ question: 'ping', postcode: 'SW11 1AA' }),
  });
  check(
    'POST /v1/chat is refused',
    BLOCKED_STATUS.has(r.status),
    `status=${r.status}${r.status === 200 ? ' <- A PUBLIC KEY IS REACHING BEDROCK' : ''}`,
  );
}

console.log('');
if (failures.length) {
  console.error(`FAIL: ${failures.length} boundary check(s) failed`);
  for (const f of failures) console.error(`  - ${f}`);
  process.exit(1);
}
console.log('OK: the demo key reaches /v1/score and nothing else\n');
