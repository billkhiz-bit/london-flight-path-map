# Sub-Processors — Sky Score

This page lists every third party that processes customer data on Sky Score's
behalf. Provided to satisfy enterprise procurement / DPA requirements
("section 28(2) GDPR sub-processor disclosure").

**Last updated:** 2026-05-09
**Maintained by:** support@skyscore.co.uk (sole controller)

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
| 3 | **GoatCounter** (offshootbv) | Web analytics on the consumer/marketing pages and the B2B funnel pages (`/api/`, `/pricing`, `/score-demo/index.html`, `/score-demo/api-docs.html`). Self-hosted alternative chosen specifically to avoid sending data to Google. Deliberately **not** loaded on `/score-demo/status.html` (no analytics on the "is the API up" surface) and never on API responses themselves. | Page-view counts + named funnel events (`event/…`), referrer, anonymised IP truncation. No cookies, no PII. | EU (Netherlands). | Operator processes pseudonymous analytics under legitimate-interests basis; no contract necessary as no personal data is processed. |
| 4 | **api.postcodes.io** (Ideal Postcodes) | **Corrected 2026-08-03** — this row previously said the lookup was "used only by the native iOS/Android app's 'Score where I am' feature; web app does not call this endpoint". That was wrong on both the caller and the data category. Called from **three surfaces**: the web app's postcode search and its debounced autocomplete (`index.html`, host allow-listed in the page CSP `connect-src`), the native "Score where I am" reverse lookup, and **server-side** by the score Lambda as the Tier-2 resolver whenever the local NSPL table defers. | **User-typed postcode** (customer data per §2 of this register) and lat/lon. Transient — never stored on Sky Score's side. | UK. | Service operates under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/); no contract required for this transient lookup. |
| 5 | **Codemagic** (Nevercode Ltd.) | CI/CD service that builds Sky Score's **iOS** binary in cloud Mac instances and pushes to TestFlight. Android is built locally via Android Studio so does not flow through Codemagic. **Does not process user data** — only project source code and iOS signing artefacts. | Source code, iOS signing certs + provisioning profiles, App Store Connect API key. | EU (Estonia). | Standard sub-processor agreement; no user data flows through Codemagic. |
| 6 | **Apple Inc.** (App Store) | Distribution of the iOS app binary; receives crash reports if the user opts in via iOS Settings. | Standard App Store telemetry; bundle distribution. | Global (Apple Inc., US-headquartered with regional data centres). | [Apple Developer Programme Licence Agreement](https://developer.apple.com/legal/) and [Apple Privacy Policy](https://www.apple.com/legal/privacy/). |
| 7 | **Google LLC** (Google Play) | **Planned, not yet active** — will distribute the Android app binary (.aab) once the Play Store listing completes (no Android app is currently distributed; listed ahead of use so this register does not lag the launch). | Standard Play Store telemetry; bundle distribution (once live). | Global (Google LLC, US-headquartered with regional data centres). | [Google Play Developer Distribution Agreement](https://play.google.com/about/developer-distribution-agreement.html); standard sub-processor terms via Google Play Data Processing and Security Terms. |

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
contact support@skyscore.co.uk — the SAM template is region-agnostic and a
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
| 2026-07-23 | Contact switched to `support@skyscore.co.uk`; Google Play row (#7) marked planned-not-active (no Android app is on the Play Store yet). |
| 2026-05-07 | Initial register published as part of Wave 9 enterprise readiness. |
| 2026-05-09 | Added api.postcodes.io (#4), Codemagic (#5), Apple App Store (#6), Google Play (#7) for the native iOS/Android build path (Wave 13.2). |
