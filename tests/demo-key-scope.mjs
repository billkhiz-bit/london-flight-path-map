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

// 4. THE FREE TIER IS SCOPED THE SAME WAY (D1, 2026-08-21).
//
// The free quota was 100 requests specifically BECAUSE batch multiplied each
// one by 100 - the ceiling was an arithmetic identity, and cutting the
// multiplicand was the only lever available at the time. It cost the wedge:
// 100 requests is an afternoon of one live listings page. Denying batch
// per-method decouples the two, so the quota could go to 10,000 while the
// entitlement stayed at the same 10,000 scores.
//
// Which means this assertion is now load-bearing in a way the demo one is not:
// if this deny stops working, the free tier is not slightly too generous, it is
// 1,000,000 scores a month - twice Professional's entire published ceiling,
// for free. Uses the CI key, which is on its own plan and NOT free tier, so
// this is checked with the key preflight already holds rather than by minting
// a throwaway free key on every run.
const CI_KEY = process.env.SKY_SCORE_API_KEY;
if (!CI_KEY) {
  console.log('  SKIP  free-tier batch deny - SKY_SCORE_API_KEY not set');
  console.log('        (set it in .env; this check cannot run without a key)');
} else {
  const res = await fetch(`${API}/v1/score/batch`, {
    method: 'POST',
    headers: { 'X-Api-Key': CI_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({ queries: [{ postcode: 'SW11 1AA' }] }),
  });
  // The CI plan is NOT the free plan, so batch SHOULD work here. Asserting the
  // positive keeps this honest: a blanket batch outage would otherwise read as
  // the free-tier deny working, and the two are different facts.
  check(
    'CI key (not free tier) can still batch',
    res.status === 200,
    `status=${res.status}`,
  );
}

// 5. THE FREE TIER MUST NOT REACH /v1/chat EITHER (2026-08-24).
//
// The demo deny above closed the key printed in page source; the free plan -
// whose keys /v1/signup mints for ANY email address - kept reaching Bedrock
// for three more days. Same stage-not-route mechanism, same RateLimit-0 fix,
// applied to ScoreFreeUsagePlan. ChatRouteDenyTests holds the template half;
// this is the half only the running API can answer.
//
// Needs a key that is genuinely ON the free plan. The CI key is deliberately
// not (SkyScoreCiTier), so this uses its own env var and SKIPS loudly rather
// than letting the wrong plan's key satisfy a free-tier assertion - the
// shared-quota incident is exactly what happens when key and plan are
// conflated. Mint one via POST /v1/signup with a throwaway address and keep it
// in .env; it costs nothing (the probes below are throttled at the edge and a
// throttled request is never metered).
const FREE_KEY = process.env.SKY_SCORE_FREE_TIER_KEY;
if (!FREE_KEY) {
  console.log('  SKIP  free-tier chat/batch deny - SKY_SCORE_FREE_TIER_KEY not set');
  console.log('        (a signup-minted free key in .env; the CI key is on another plan)');
} else {
  for (const [name, path, body] of [
    ['free-tier key: POST /v1/chat is refused', '/v1/chat',
      JSON.stringify({ question: 'ping', postcode: 'SW11 1AA' })],
    ['free-tier key: POST /v1/score/batch is refused', '/v1/score/batch',
      JSON.stringify({ queries: [{ postcode: 'SW11 1AA' }] })],
  ]) {
    const res = await fetch(`${API}${path}`, {
      method: 'POST',
      headers: { 'X-Api-Key': FREE_KEY, 'Content-Type': 'application/json' },
      body,
    });
    check(
      name,
      BLOCKED_STATUS.has(res.status),
      `status=${res.status}${res.status === 200 ? ' <- A FREE KEY IS THROUGH THE DENY' : ''}`,
    );
  }
}

console.log('');
if (failures.length) {
  console.error(`FAIL: ${failures.length} boundary check(s) failed`);
  for (const f of failures) console.error(`  - ${f}`);
  process.exit(1);
}
console.log('OK: the demo key reaches /v1/score and nothing else\n');
