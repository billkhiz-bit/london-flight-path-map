# Sub-Processors — Sky Score

This page lists every third party that processes customer data on Sky Score's
behalf. Provided to satisfy enterprise procurement / DPA requirements
("section 28(2) GDPR sub-processor disclosure").

**Last updated:** 2026-08-07
**Maintained by:** support@skyscore.co.uk (sole controller)

Sky Score is a trading name of **CUBITT33 LTD**, registered in England and Wales,
company number **13651304**, registered office 50 Pembroke Road, London W8 6NX.

<!-- ENTITY LINE, switched to the company 2026-08-07. The matching lines are
     privacy.html §1, terms.html §1 and LIA.md. The old comment called this a
     three-line change; it was four, and the footer copyright on both HTML
     pages names a person too. That one stays as it is: copyright follows
     authorship and does not move until the IP assignment deed is signed. -->


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
| 3 | **GoatCounter** (offshootbv) [^gc] | Web analytics on the consumer/marketing pages and the B2B funnel pages (`/api/`, `/pricing`, `/score-demo/index.html`, `/score-demo/api-docs.html`). Self-hosted alternative chosen specifically to avoid sending data to Google. Deliberately **not** loaded on `/score-demo/status.html` (no analytics on the "is the API up" surface) and never on API responses themselves. | Page-view counts + named funnel events (`event/…`), referrer, anonymised IP truncation. No cookies, no PII. | EU (Netherlands). | Operator processes pseudonymous analytics under legitimate-interests basis; no contract necessary as no personal data is processed. |
| 4 | **api.postcodes.io** (Ideal Postcodes) | **Corrected 2026-08-03** — this row previously said the lookup was "used only by the native iOS/Android app's 'Score where I am' feature; web app does not call this endpoint". That was wrong on both the caller and the data category. Called from **three surfaces**: the web app's postcode search and its debounced autocomplete (`index.html`, host allow-listed in the page CSP `connect-src`), the native "Score where I am" reverse lookup, and **server-side** by the score Lambda as the Tier-2 resolver whenever the local NSPL table defers. | **User-typed postcode** (customer data per §2 of this register) and lat/lon. Transient — never stored on Sky Score's side. | UK. | Service operates under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/); no contract required for this transient lookup. |
| 5 | **Codemagic** (Nevercode Ltd.) | CI/CD service that builds Sky Score's **iOS** binary in cloud Mac instances and pushes to TestFlight. Android is built locally via Android Studio so does not flow through Codemagic. **Does not process user data** — only project source code and iOS signing artefacts. | Source code, iOS signing certs + provisioning profiles, App Store Connect API key. | EU (Estonia). | Standard sub-processor agreement; no user data flows through Codemagic. |
| 6 | **Apple Inc.** (App Store) | Distribution of the iOS app binary; receives crash reports if the user opts in via iOS Settings. | Standard App Store telemetry; bundle distribution. | Global (Apple Inc., US-headquartered with regional data centres). | [Apple Developer Programme Licence Agreement](https://developer.apple.com/legal/) and [Apple Privacy Policy](https://www.apple.com/legal/privacy/). |
| 7 | **Google LLC** (Google Play) | **Planned, not yet active** — will distribute the Android app binary (.aab) once the Play Store listing completes (no Android app is currently distributed; listed ahead of use so this register does not lag the launch). | Standard Play Store telemetry; bundle distribution (once live). | Global (Google LLC, US-headquartered with regional data centres). | [Google Play Developer Distribution Agreement](https://play.google.com/about/developer-distribution-agreement.html); standard sub-processor terms via Google Play Data Processing and Security Terms. |

[^gc]: **Region unverified, flagged 2026-08-04.** This row says *EU (Netherlands)*, which
matches the operator being a Dutch BV, while `privacy.html` said *EU (Berlin)* — two
published documents giving different data locations for the same processor. Neither was
verifiable from the repo, so `privacy.html` now states only *EU*, which is certainly true.
Confirm the hosting region with GoatCounter and then make both specific again. Recorded
rather than harmonised silently, because picking one at random is how a register acquires a
figure nobody can source.

### Added 2026-08-04 — upstream data APIs called during request processing

**Rows 8-11 were absent from this register entirely**, which made §5's residency
statement false. Found by grepping the Lambda sources for outbound hosts rather than
re-reading this document. Row 4 had been corrected on 2026-08-03 for exactly this
class of error, but only that row was fixed; nobody asked what else the code calls,
which is a two-line search. Each row below is derived from the call site named in it.

| # | Sub-processor | Purpose | Data categories | Region | Legal basis |
|---|---|---|---|---|---|
| 8 | **Transport for London** (`api.tfl.gov.uk`) | Nearest-station and line-status lookup for the `live` component. Called by `backend/lambdas/transport/app.py:83`, which passes the **coordinates directly in the query string** (`/StopPoint?lat=…&lon=…&radius=1500`). | Customer-supplied **lat/lon**. Transient; never stored by Sky Score. | UK. | TfL Open Data, operating under the [TfL Open Data licence](https://tfl.gov.uk/info-for/open-data-users/) / OGL v3.0. Public-sector open data; no contract required for a transient lookup. |
| 9 | **MHCLG** (`api.get-energy-performance-data.communities.gov.uk`) | EPC certificate search for the property panel. Called by `backend/lambdas/epc/app.py:53`. | Customer-supplied **postcode**. Transient. | UK. | Bearer-token access to a public register; Open Government Licence v3.0. |
| 10 | **HM Land Registry** (`landregistry.data.gov.uk`) | Price Paid Data lookup for sold-price history. Called by `backend/lambdas/sold_prices/app.py:30` as `?propertyAddress.postcode=…`. | Customer-supplied **postcode**. Transient. | UK. | Open Government Licence v3.0. |
| 11 | **OpenStreetMap Overpass API** (`overpass-api.de`, operated by FOSSGIS e.V.) | Healthcare-facility proximity for the `live` component. Called by `backend/lambdas/nhs/app.py:99` with the coordinates embedded in the Overpass QL query. | Customer-supplied **lat/lon**. Transient. | **Germany — the only non-UK route in the server-side request path.** See §5. | Data under ODbL; service provided by FOSSGIS e.V. on a best-effort community basis with **no contract and no SLA**. Sky Score sets `OVERPASS_URL` from the environment, so this can be repointed to a UK-hosted Overpass instance without a code change. |

**Not a sub-processor, recorded to prevent it being added in error:** `www.nhs.uk`
appears in `backend/lambdas/nhs/app.py` (lines 47-49, 170) **only as link targets
returned in the response body**. No request is ever made to it. The single outbound
call in that Lambda is to Overpass.

### Added 2026-08-04 — third parties the visitor's browser contacts directly

These are not called by Sky Score's servers; the **visitor's browser** requests them
while rendering the consumer site, so each receives the visitor's **IP address** and
`Referer`. Enumerated from the `connect-src` / `style-src` / `font-src` / `script-src`
directives in `index.html`'s CSP and then **verified against actual call sites** — the
CSP is known to retain hosts for removed features (audit finding 55), so an allow-list
entry alone is not evidence of use. All six below are genuinely fetched.

| # | Third party | Purpose | Data categories | Region | Legal basis |
|---|---|---|---|---|---|
| 12 | ~~**Google LLC** (`fonts.googleapis.com`, `fonts.gstatic.com`)~~ **REMOVED 2026-08-05** | ~~Web fonts (Inter, JetBrains Mono)~~ Fonts are now **self-hosted** at `/fonts/`, vendored by `scripts/vendor_fonts.py`. | **None. No request is made to Google.** | n/a | ✅ **Gap closed.** This row previously recorded an open compliance item: German case law (LG München I, 3 O 17493/20) held that embedding Google Fonts transmits the visitor's IP to a US provider without consent, contrary to GDPR, and named self-hosting as the remedy. That remedy is now applied, matching `js/vendor/d3.v7.min.js`. Both hosts are out of every page CSP and out of `sw.js` `SWR_ORIGINS`. Row kept rather than deleted so the register shows the gap was closed, not that it never existed. |
| 13 | **GitHub, Inc.** (Microsoft) (`raw.githubusercontent.com`) | **Fallback only** — boundary GeoJSON for UK LADs and NYC boroughs (`index.html:5687`, `:8136`) when the vendored same-origin copies are unavailable. Primary path is same-origin since 2026-07-30. | Visitor **IP address**, `Referer`. | **US.** | Legitimate interests; static public file, no customer data in the request. Retiring the fallback would remove this row. |
| 14 | **US Department of Transportation** (`geo.dot.gov`) | NTAD aviation + road noise map layers for the **NYC** view (`index.html:5485`, `:5490`). | Visitor **IP address** and the **map viewport bbox**, which indicates the area being viewed. | **US.** | Public-sector open data; US federal public-domain layers. |
| 15 | **US Environmental Protection Agency** (`gispub.epa.gov`) | Air-quality non-attainment-area layer for the NYC view (`index.html:5501`). | Visitor **IP address** and map viewport bbox. | **US.** | Public-sector open data. |
| 16 | **FEMA** (`hazards.fema.gov`) | National Flood Hazard Layer for the NYC view (`index.html:5495`). | Visitor **IP address** and map viewport bbox. | **US.** | Public-sector open data. |
| 17 | **GoatCounter script host** (`gc.zgo.at`) | Serves `count.js` for the analytics in row 3 (`index.html:9074`). Named separately because row 3 covers the *count* endpoint (`cubitt33.goatcounter.com`) and a reviewer checking the CSP will find this host too. | Visitor **IP address** while fetching the script. | EU (operated by offshootbv, Netherlands). | As row 3. |

Rows 14-16 serve the **NYC** map layers only; a UK-only visitor who never switches
city does not trigger them. They are listed unconditionally because the code path is
reachable by any visitor.

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

> **Corrected 2026-08-04.** This section previously stated that "the request body
> never leaves UK AWS infrastructure during processing". **That was false.** The `nhs`
> Lambda sends customer-supplied coordinates to `overpass-api.de` in **Germany** on
> every healthcare lookup (row 11). The claim was written when the register listed no
> upstream data APIs at all, and it survived because the register and the code were
> never checked against each other. It is corrected below rather than removed, and the
> exception is stated first so a reader cannot miss it.

- All customer **state** (DynamoDB) is in `eu-west-2` (London).
- All customer **compute** (Lambda) is in `eu-west-2` (London).
- API requests terminate at API Gateway in `eu-west-2`.
- **Processing is not wholly UK-resident.** One outbound route leaves the UK:
  the healthcare component sends **lat/lon to `overpass-api.de` (Germany)**, row 11.
  Germany is an EU member state, so this is an intra-EEA transfer rather than a
  third-country transfer, and no Article 46 safeguard is required — but it is a
  transfer, and a buyer requiring UK-only processing must know about it. The
  endpoint is environment-configurable (`OVERPASS_URL`), so it can be repointed to
  a UK-hosted Overpass instance **without a code change** if a contract requires it.
- The other four upstream routes (rows 8-10, and row 4) are **UK-resident**: TfL,
  MHCLG, HM Land Registry and postcodes.io.
- **Static** marketing assets (the `index.html` file, CSS, JS bundles)
  are cached at CloudFront edge POPs globally. These contain no customer
  data.
- **The visitor's browser contacts US-hosted third parties** while rendering the
  consumer site (rows 13-16): the FEMA / EPA / US-DOT map layers on the NYC view,
  and GitHub for a boundary-file fallback. These receive the visitor's IP address,
  not API customer data, and are separate from the server-side processing path
  above. **Google Fonts was the every-page-load case and is gone as of
  2026-08-05** — fonts are self-hosted, so the remaining US contacts are
  view-specific rather than universal. See row 12.

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
| 2026-08-04 | **Ten rows added (8-17) and the §5 residency claim corrected as false.** The register listed no upstream data APIs at all, so four services receiving customer-supplied postcodes or coordinates during request processing were unrecorded (TfL, MHCLG, HM Land Registry, and **Overpass in Germany**), as were six third parties the visitor's browser contacts directly (Google Fonts, GitHub, US DOT, EPA, FEMA, and GoatCounter's script host). §5's "the request body never leaves UK AWS infrastructure during processing" was false because of the Overpass route. Rows derived by grepping the Lambda sources and the page CSP for outbound hosts, then verifying each against its call site — the CSP retains hosts for removed features, so allow-listing alone was not treated as evidence of use. `www.nhs.uk` was explicitly excluded: it appears only as link targets in a response body and is never requested. **Open compliance item recorded, not resolved:** Google Fonts is loaded from Google's US CDN on every page load; the remedy is self-hosting, as `js/vendor/d3.v7.min.js` already is. |
| 2026-07-23 | Contact switched to `support@skyscore.co.uk`; Google Play row (#7) marked planned-not-active (no Android app is on the Play Store yet). |
| 2026-05-07 | Initial register published as part of Wave 9 enterprise readiness. |
| 2026-05-09 | Added api.postcodes.io (#4), Codemagic (#5), Apple App Store (#6), Google Play (#7) for the native iOS/Android build path (Wave 13.2). |
