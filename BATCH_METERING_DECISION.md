# Batch metering — the decision that blocked the Professional launch

**Written 2026-07-27. Decided and implemented 2026-07-29: option B, at `Limit: 100`
(a 10,000 score/month ceiling), with `RateLimit` dropped 2 → 1 as suggested in §4.2.**

**What shipped:** `backend/template.yaml` (`ScoreFreeUsagePlan`), plus the five mirrors of
those numbers that cannot read the plan at runtime — `backend/lambdas/signup/app.py` (whose
201 response was still advertising 1000), `pricing.html`, `api/index.html` and
`score-demo/openapi.yaml`. The signup response and the OpenAPI schema now also return
`batchMultiplier` and `monthlyScoreCeiling`, so the ceiling is a field a customer reads rather
than an arithmetic exercise they perform and then feel entitled to.

**A consequence the original analysis missed:** the shared public demo key on
`/score-demo` was linked to the *same* `ScoreFreeUsagePlan`, so cutting the free tier would have
capped the public "Try the API" form at 100 requests shared across every visitor. The usage plan
had two unrelated consumers and §3 reasoned about only one of them. Fixed by giving the demo key
its own `ScoreDemoUsagePlan` at 2,000 req/month — §3's objection to per-endpoint plans (two keys
per customer) does not apply to a single key on our own page. The relink was a manual post-deploy
step, because the key was created out-of-band in 2026-05 and CloudFormation does not manage it:
runbook in `OPERATIONS.md` §2.

**Shipped 2026-07-29.** `sam deploy` cut `SkyScoreFreeTier` (`sjtyz8`) to 100 req/month and
created `SkyScoreDemoTier` (`x88go8`) at 2,000; the demo key was relinked in the same session and
verified from the API, structurally and with a live 200 from `/v1/score`. The nine copy surfaces
went out to CloudFront ahead of the backend, so the only drift window was the harmless direction —
pages advertising less than the plan granted.

**Not done, deliberately:** option A. The recommendation stands — build per-score metering when
a paying customer's usage makes it worth operating, not before.

**Professional: DECIDED 2026-07-29, implementation still to do.** Keep 100,000 requests/month,
publish a **1,000,000 scores/month** ceiling beside it — the free-tier move repeated, because the
unit is the problem in both cases. Cutting Professional's requests to 10,000 was rejected: it caps
scores correctly but charges £499 for 10,000 single-address lookups, and a portal doing per-search
lookups is the likelier first customer than a batch-only one. Building option A now was also
rejected as premature, though note the trigger below is closer than it was.

**The unenforced half, stated plainly:** API Gateway meters requests, so nothing technically stops
a Professional key from taking all 10,000,000. The published ceiling is a contractual commitment,
not a control. It stops the price list lying; it does not stop the extraction. That gap closes
only when option A ships, and **Professional's first paying customer is precisely the trigger
condition this document deferred option A against** — so expect to build it then, not later.

> **IMPLEMENTED 2026-08-04.** All four surfaces below now carry the figure, plus six tests.
> **Not deployed** — `pricing.html`, `api/index.html` and `score-demo/openapi.yaml` need a
> `web-deploy`, and the signup change needs a SAM deploy.
>
> **One thing this document did not say explicitly, and it caused a wrong first attempt.**
> The free ceiling is an *arithmetic identity* (100 × 100 = 10,000). Professional's is a
> *contractual cap deliberately below* the product (100,000 × 100 = **10,000,000**, capped at
> 1,000,000). The first implementation copied the free tier's phrasing — *"a batch request carries
> up to 100 addresses, so the ceiling is 1,000,000"* — which states a derivation that is false by a
> factor of ten, on a public price list, in the customer's favour. A reader doing the multiplication
> would have caught it.
>
> Caught by `test_upgrade_ceiling_is_a_cap_BELOW_the_product_not_equal_to_it`, which was itself
> written backwards first and failed. The response now carries **`scoreCeilingBasis`** on both
> blocks (`quota` vs `fair-use`) so the two kinds of number cannot be read as the same, and the
> public copy says *"fair-use ceiling"* rather than deriving it.

**Surfaces still to change** (none done as of 2026-07-29): `pricing.html`, `api/index.html`,
`score-demo/openapi.yaml`, and the `signup` Lambda's response, which already returns
`batchMultiplier` + `monthlyScoreCeiling` for the free tier and needs the Professional equivalent.
All four need a deploy.

**Why it mattered:** the ×100 made Professional's real entitlement 10,000,000 scores for £499 —
around every home in London three times a month, and drainable in under 3 hours of sustained calls
at the batch route's 10 rps / 20 burst. That undercut both the £12,000/yr Enterprise floor (£1,000
a month for less volume than the £499 tier already gave away) and the £2,500 pilot, which
"includes everything in Professional" and therefore implied 30,000,000 scores across its 90 days.

**The £499 price itself is unchanged** — repricing Professional was outside this decision, and the
ceiling change removes most of the reason to revisit it. Enterprise and pilot pricing likewise
stand; what changes is that Professional no longer silently out-delivers them on volume.

---

*Original 2026-07-27 text follows, unedited.*

Every figure below was read from source on 2026-07-27, not from memory:
`backend/template.yaml` (`ScoreFreeUsagePlan`) and `backend/lambdas/score/app.py`
(`MAX_BATCH_SIZE`).

---

## 1. The mismatch, stated precisely

API Gateway usage plans meter **requests**. They have no concept of how much work a request
represents. The product meters **scores**. Those two units are the same on `/v1/score` and differ
by up to 100× on `/v1/score/batch`.

| | Value | Source |
|---|---|---|
| Free-tier quota | 1,000 requests / month | `template.yaml:357` |
| Free-tier throttle | 2 req/s, burst 5 | `template.yaml:359-361` |
| Max queries per batch call | 100 | `score/app.py:80` |
| **Effective free tier** | **100,000 scores / month** | 1,000 × 100 |

So the free tier is advertised as 1,000 and is really 100,000 for anyone who reads the batch docs.

**The part that is easy to miss: the quota is monthly, but the throttle is per second.** At 2 req/s
with 100 queries each, a single free key drains the entire monthly allowance in **about eight and a
half minutes** (1,000 ÷ 2 = 500 seconds). This is not a slow drip that shows up as gradual growth in
the bill — it is a burst that is over before any alarm with a monthly window notices. The $20 billing
alarm in `AWS_BILLING_ALARM_SETUP.md` is not positioned to catch it either.

## 2. Why it blocks Professional, specifically

The £499/month Professional tier's headline justification is volume. A prospect who needs 100,000
address scores a month is precisely the customer that tier exists for — and today they can have it
for nothing, in under ten minutes, with a self-service key and no conversation.

That is not merely lost revenue. It undercuts the pricing conversation itself: the £2,500 90-day
pilot is quoted to organisations whose portfolios are in exactly this range, and a prospect who
checks the free tier before the call arrives knowing the paid tier's core benefit is already free.

## 3. Options

### A. Meter scores in the Lambda

Count queries per key in `handle_batch` / `handle_score`, persist to DynamoDB, enforce a monthly
score budget in-handler.

- **For:** the only option that meters the unit actually being sold, and the only one that survives
  a future where batch size changes. Makes usage-based pricing possible later.
- **Against:** real engineering. Atomic counters under a 100-way worker pool, month-boundary
  rollover, a reset path, and a fail-open-or-fail-closed decision that is itself a judgement call
  (fail closed and a DynamoDB blip becomes a customer outage; fail open and the limit is advisory).
  Adds a write to the hot path of the latency-sensitive endpoint. This is a week of careful work,
  not an afternoon.

### B. Cut the free quota so the worst case is tolerable

Set `Quota.Limit` to whatever you are willing to give away, divided by 100.

| Quota | Worst-case free scores/month |
|---|---|
| 1,000 (today) | 100,000 |
| 250 | 25,000 |
| **100** | **10,000** |
| 50 | 5,000 |

- **For:** one line in `template.yaml`, one deploy, zero new code, no new failure modes. Closes the
  exposure **today**, before any pilot is signed.
- **Against:** it is a blunt instrument. A developer evaluating single-address scoring gets 100 calls
  a month, which is stingy for genuine evaluation, while a batch user still gets 10,000. The unit
  mismatch is not fixed, only made smaller.

### C. Separate usage plans per endpoint

**Check this before costing it.** An API Gateway usage plan's `Quota` applies to the plan as a
whole, not per method — per-method configuration covers throttling only. Giving `/v1/score/batch` its
own quota therefore means a second usage plan and a **second API key per customer**, with the signup
Lambda issuing and the customer juggling both. The DX cost is real and the support burden is worse.
Not recommended, listed so it is visibly considered and rejected.

### D. Reduce `MAX_BATCH_SIZE`

Drops the multiplier directly — 100 → 10 makes the free tier 10,000 scores.

- **Against:** batch size is a paying-customer feature. The customers who most want 100-query calls
  are the ones being charged for them, so this taxes the wrong people to fix a free-tier problem.

### E. Accept it and reprice around it

Describe the free tier honestly as "1,000 API calls/month, up to 100 addresses per call", and move
Professional's value to SLA, support, rate limits, and the trends/changes endpoints rather than raw
volume.

- **For:** intellectually honest, no engineering at all, and arguably where the product is heading —
  volume is a weak moat and a support commitment is a strong one.
- **Against:** requires the £499 tier to actually carry non-volume value that a free user can feel
  the absence of. Some of that exists; not obviously £499/month of it yet.

## 4. Recommendation

**Do B now, plan for A, revisit E when the first pilot converts.**

The reasoning: the decision that unblocks the Professional launch is *not* "build metering". It is
**"decide what the free tier is allowed to be worth"** — and that is a pricing question you can
answer today, in one deploy, without writing a metering subsystem you would then have to operate
while also running a pilot.

Concretely:

1. Set `Quota.Limit: 100` — a 10,000-score/month free ceiling. Generous for evaluation, clearly below
   any real portfolio, one line in `template.yaml`.
2. Consider dropping `RateLimit` to 1 alongside it. It does not change the monthly total, but it
   doubles the time to drain the quota and makes the burst pattern less abrupt.
3. State the batch multiplier explicitly on `/pricing` and in the API docs. Right now the effective
   limit is something a reader has to derive, and a limit customers derive for themselves is one they
   will feel entitled to.
4. Only build A once a paying customer's usage makes per-score accounting worth operating.

## 5. What this does not decide

- Whether Professional is £499. That ladder is settled (see `memory/project-pricing-ladder.md`); this
  is only about what sits beneath it.
- Whether the £12k enterprise floor stays verbal.
- Anything about the pilot's own volume terms, which are contractual rather than enforced in code —
  though whatever ceiling you pick here should be visibly below what the pilot buys, or the pilot
  looks poor value next to the free tier.

## 6. If you take the recommendation

The change itself, for reference — not applied:

```yaml
# backend/template.yaml, ScoreFreeUsagePlan
      Quota:
        Limit: 100        # was 1000; 100 x MAX_BATCH_SIZE(100) = 10,000 scores/month
        Period: MONTH
```

Then update: `pricing.html`, `api/index.html`, `score-demo/api-docs.html`, and the free-tier line in
`SECURITY.md` (which currently says "1000 req/month free tier"). Existing keys inherit the new quota
automatically — the plan is shared, so no per-key migration is needed.
