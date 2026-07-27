# Batch metering — the open decision blocking the Professional launch

**Written 2026-07-27. Decision owner: Bill. Nothing here has been implemented.**

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
