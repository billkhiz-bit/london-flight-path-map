// Stub the live API for gates that audit LAYOUT and ACCESSIBILITY.
//
// WHY THIS EXISTS. `score-demo/status.html` probes the real API on load
// (`runAllChecks()` at :439, and again on a setInterval at :443), and two of
// its probes are `GET /v1/score` carrying the PUBLIC DEMO KEY that is printed
// in that page's source. `tests/a11y-source.mjs` and `tests/responsive.mjs`
// both load that page - a11y at three viewports, responsive at several - so
// every preflight run spent real demo-key quota.
//
// Measured 2026-09-11 from API Gateway's own usage data: the demo key's
// 2,000/month quota was EXHAUSTED on 9 September, and `GET /v1/score` with
// that key has returned `429 Limit Exceeded` ever since - so the public B2B
// API tester was broken for real prospects for two days. The daily pattern is
// conclusive about the cause: 511 requests on 1 Sep and 627 on 7 Sep, both
// heavy development days, and exactly ZERO across 5-6 Sep, a weekend. Visitor
// traffic does not take weekends off and does not spike on the days the gates
// ran most.
//
// Second instance of the shape in `memory/feedback-gate-blocked-by-shared-
// quota.md` - CI spent this same key once before and was given its own. The
// lesson did not reach the two gates that spend it by SIDE EFFECT, because
// neither names the API: they just load a page that calls it.
//
// FULFIL, DO NOT ABORT. Aborting would make the status page render its error
// state, so the gates would start auditing a different surface than the one
// they were written against - a scope change arriving as a side effect of a
// quota fix. A canned 200 keeps the audited DOM the same shape it is today.
//
// A URL PREDICATE, NOT A GLOB. `page.route('**/v1/score**')` that matches
// nothing fails open and silently: the requests go to the network and look
// fine. This repo has paid for that once already (a realistic fixture that was
// never consulted, 2026-08-27). A predicate cannot quietly match nothing, and
// the hit counter below is what proves it did not.

const API_HOSTS = ['execute-api.eu-west-2.amazonaws.com'];

// ONLY /v1/score. Narrowed 2026-09-11, having first intercepted the whole API
// host and broken a gate with it.
//
// `/v1/score` is the ONLY route that spends the demo quota - it is the one
// carrying the demo key. `/v1/regions` and `/v1/changes` are unauthenticated,
// cost nothing, and must reach the network: `changes.html` builds its ENTIRE
// body from `/v1/changes` (tests/a11y-source.mjs says so in its own comment),
// so answering it with a score-shaped payload rendered a different page and
// `responsive` immediately went red on a 2px overflow at 320x568.
//
// That is the danger a stub carries in a LAYOUT gate, and it cuts both ways:
// answer too little and the page renders an error state, answer the wrong
// shape and it renders a wrong state. Either way the gate stops auditing the
// surface it was written for, and it looks like a real regression. Intercept
// the narrowest thing that solves the problem.
const SPENDS_QUOTA = (pathname) => pathname.includes('/v1/score');

// Shaped like a real /v1/score response, because status.html parses the body
// of `captureBody` endpoints to render its two version rows. A bare `{}` would
// leave those rows empty and change the audited DOM, which is the thing this
// helper exists to avoid.
const CANNED_SCORE = {
  score: 5.0,
  components: { quiet: 6.4, afford: 0.4, growth: 4.0, live: 7.8, env: 5.6 },
  apiVersion: '1.0',
  methodologyVersion: '5.0',
  location: { borough: 'Wandsworth', city: 'london', postcode: 'SW11 1AA' },
  persona: 'balanced',
  sources: ['Stubbed by tests/stub-live-api.mjs - not a live reading'],
};

/**
 * Intercept every request to the live API host and answer it locally.
 *
 * Returns a live `hits` object. Assert on it: a stub cannot tell you it was
 * never used, so the caller has to ask. Both current callers load
 * score-demo/status.html, which probes on load, so `hits.count` being 0 at the
 * end of a run means the interception stopped working - not that the page got
 * quieter.
 */
export async function stubLiveApi(page) {
  const hits = { count: 0, paths: [] };

  await page.route(
    (url) => API_HOSTS.some((h) => url.hostname.endsWith(h)) && SPENDS_QUOTA(url.pathname),
    async (route) => {
      const path = new URL(route.request().url()).pathname;
      hits.count += 1;
      hits.paths.push(path);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: { 'Access-Control-Allow-Origin': '*' },
        body: JSON.stringify(CANNED_SCORE),
      });
    }
  );

  return hits;
}

/**
 * Fail the run if the stub never fired. Call once at the end.
 *
 * Deliberately a hard failure and not a warning: if this stops matching, the
 * gates go back to spending a public quota that a real customer is trying to
 * use, and nothing else in the suite would notice.
 */
export function assertStubFired(hits, label) {
  if (hits.count > 0) {
    console.log(`  live-API stub: ${hits.count} request(s) intercepted, 0 spent`);
    return true;
  }
  console.error(
    `FAIL: ${label} intercepted ZERO live-API requests. score-demo/status.html ` +
      `probes the API on load, so this run should have caught some. The route ` +
      `predicate in tests/stub-live-api.mjs has probably stopped matching - ` +
      `which means the gates are spending the public demo key again.`
  );
  return false;
}
