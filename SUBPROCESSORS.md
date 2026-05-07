# Sub-Processors — Sky Score

This page lists every third party that processes customer data on Sky Score's
behalf. Provided to satisfy enterprise procurement / DPA requirements
("section 28(2) GDPR sub-processor disclosure").

**Last updated:** 2026-05-07
**Maintained by:** billkhiz@gmail.com (sole controller)

---

## 1. What "customer data" means here

For Sky Score B2B API customers, "customer data" is the address / postcode /
lat-lon you submit to `/v1/score` plus the API key in your request header.
We do not store request payloads beyond the duration of the synchronous
Lambda invocation (no request logging on the API path).

For consumer-site visitors, "personal data" is limited to the email a user
provides on the API signup form (kept in DynamoDB to enforce one-key-per-email
and to support revocation).

---

## 2. Sub-processor register

| # | Sub-processor | Purpose | Data categories | Region | Legal basis |
|---|---|---|---|---|---|
| 1 | **Amazon Web Services Inc.** (AWS) | Sole compute, storage, CDN and DNS-record-set host. Runs Lambda, API Gateway, DynamoDB, S3, CloudFront. | All API requests in transit; signup email at rest; user favourites at rest. | eu-west-2 (London) for compute/state; CloudFront edge POPs globally for static assets only. | UK GDPR Art. 28(3) DPA via the [AWS Service Terms](https://aws.amazon.com/service-terms/) and [AWS DPA](https://aws.amazon.com/compliance/gdpr-center/). |
| 2 | **Cloudflare, Inc.** | Domain registration and authoritative DNS for `skyscore.co.uk`. Does **not** proxy API traffic; CNAME points directly to CloudFront. | DNS query metadata only (no payload, no headers). | US-headquartered; DNS resolved from anycast network. | UK SCCs / Data Processing Addendum on Cloudflare's Business plan. |
| 3 | **GoatCounter** (offshootbv) | Consumer-site analytics on the marketing pages only. Self-hosted alternative chosen specifically to avoid sending data to Google. **Not** loaded on `/score-demo/` or any API surface. | Page-view counts, referrer, anonymised IP truncation. No cookies, no PII. | EU (Netherlands). | Operator processes pseudonymous analytics under legitimate-interests basis; no contract necessary as no personal data is processed. |

That's the entire list. Sky Score uses no third-party email provider, no
billing processor (free tier / direct billing only), no customer support
SaaS, no chat widget, no error-monitoring service.

---

## 3. Sub-processors we have considered but do *not* use

Documented to make procurement reviews faster:

| Tool | Why we don't use it |
|---|---|
| Google Analytics / GA4 | Avoided to keep zero data out to Google. |
| Sentry / Datadog / New Relic | Error monitoring not yet wired up; would be a future sub-processor addition with prior notice. |
| Stripe / any payment processor | Free tier only; no commercial sub-processor today. |
| HubSpot / Salesforce / Mailchimp | No marketing automation; outreach is hand-curated. |
| OpenAI / Anthropic / any LLM provider | All AI features were removed from the consumer site on 2026-05-07; no LLM provider receives any customer data. |
| OpenSky Network | Live-flight tracking removed end-to-end on 2026-05-07 pending OpenSky's required written licensing agreement. Re-introduction would trigger a sub-processor notification. |

---

## 4. Notification of changes

Adding a new sub-processor: 30 days' notice via `OUTREACH_LOG.md` and
direct email to enterprise customers if any are signed by then. Critical
hot-fix additions (e.g. switching CDN due to provider outage) may be made
without notice with retroactive disclosure within 7 days.

Removing a sub-processor: noted here on the same business day.

---

## 5. Data residency commitments

- All customer **state** (DynamoDB) is in `eu-west-2` (London).
- All customer **compute** (Lambda) is in `eu-west-2` (London).
- API requests terminate at API Gateway in `eu-west-2`; the request body
  never leaves UK AWS infrastructure during processing.
- **Static** marketing assets (the `index.html` file, CSS, JS bundles)
  are cached at CloudFront edge POPs globally. These contain no customer
  data.

If you require US-only or APAC-only deployment for compliance reasons,
contact billkhiz@gmail.com — the SAM template is region-agnostic and a
single-tenant deployment in another region is feasible.

---

## 6. Related documents

- `SECURITY.md` — overall security posture
- `LICENSING.md` — data sources (separate concern: open-data inputs vs
  customer data sub-processors)
- `OPERATIONS.md` — runbook for the production stack
- `METHODOLOGY.md` §15 — short-form residency note

---

## Change history

| Date | Change |
|---|---|
| 2026-05-07 | Initial register published as part of Wave 9 enterprise readiness. |
