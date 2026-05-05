# Sky Score Methodology

> Version 1.0 — last updated 2026-05-05.
> Public methodology for the Sky Score property scoring system. Maintained alongside the live API at `https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/`.

## What Sky Score is

Sky Score is a per-postcode (and per-borough) property quality score from 0 to 10, designed to surface noise, livability, and affordability factors that mainstream UK listings sites have a financial incentive to obscure. It exists in two surfaces:

- A consumer site at `https://d1oe4ftwutjpf.cloudfront.net` that informs renters and buyers.
- A B2B API (in development) intended for property data aggregators, conveyancers, and Islamic-finance providers whose customers benefit from accurate due-diligence data.

The score is a transparent weighted combination of four components — Quiet, Affordability, Growth, and Liveability — described below. It is not a market valuation, an EPC rating, or a regulatory rating; it is a holistic quality signal designed to complement those.

## Components

| Component | What it measures | Inputs | Range |
|---|---|---|---|
| **Quiet** | Aviation + road noise impact at postcode level | DEFRA noise mapping; OpenSky Network aircraft tracking; flight path geometry | 0–10 (10 = quietest) |
| **Affordability** | Average sold price relative to neighbouring areas | HM Land Registry Price Paid Data | 0–10 (10 = cheapest in cohort) |
| **Growth** | Recent price-trend signal | HM Land Registry Price Paid Data (5-year window) | 0–10 (10 = strongest growth) |
| **Liveability** | Schools, crime, transport, healthcare access | ONS, Department for Education, Home Office crime stats, TfL Open Data, NHS Service Search | 0–10 (10 = most liveable) |

The default Sky Score is `0.30 × Quiet + 0.20 × Affordability + 0.15 × Growth + 0.35 × Liveability`. The B2B API will accept a `?weights=` override so different customer segments (buyers, lenders, councils) can apply their own preference profile without changing the underlying components.

## Data sources

Every input listed in this section. Each row gives the source, its licence, the refresh cadence, and the algorithmic role.

| Source | Purpose | Licence | Refresh |
|---|---|---|---|
| **DEFRA Strategic Noise Mapping** (Round 4, 2022) | Baseline aviation + road noise contours for England | Open Government Licence v3.0 | 5-yearly (next: 2027) |
| **OpenSky Network** | Live + historical aircraft positions over UK airspace | OpenSky terms — research/non-commercial on the free tier (see "Limitations") | Real-time |
| **HM Land Registry Price Paid Data** | Historic sold prices at postcode resolution | Open Government Licence v3.0 | Monthly |
| **MHCLG Energy Performance Certificates** (new "Get energy performance of buildings data" service) | Per-property EPC bands and ratings | Open Government Licence v3.0 | Quarterly |
| **TfL Open Data** | Transport accessibility (Tube, Rail, DLR stations and live status) | TfL Open Data terms — commercial use permitted with attribution | Real-time (line status), static (station locations) |
| **NHS Service Search API** | GP, pharmacy, and hospital availability | Provided by NHS Digital under public-sector terms | Real-time |
| **ONS** | Boundary geometry, demographic context | Open Government Licence v3.0 + OS Open licence (boundaries) | Annual |
| **Home Office crime statistics** | Borough-level crime rate input | Open Government Licence v3.0 | Monthly |
| **Department for Education school ratings** | Ofsted-derived school quality signal | Open Government Licence v3.0 | Continuous |

### Attribution

Live API responses include a `sources` array in the response body for each data-source endpoint. Consumers redistributing Sky Score outputs are expected to preserve attribution for the underlying open-data sources. Required attribution lines are provided in `sources` and are also reproduced in this document.

> Contains public sector information licensed under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
>
> Powered by TfL Open Data.

## Computation

1. **Quiet** is computed from DEFRA's strategic noise raster sampled at the postcode centroid and adjusted for live aviation overflight density (where coverage is available). A 0–10 score is mapped from a six-band qualitative impact ladder (`low`, `low-moderate`, `moderate`, `moderate-high`, `high`, `severe`).
2. **Affordability** is computed by min-max scaling the average sold price within the cohort (borough or city), inverted so cheaper areas score higher.
3. **Growth** is computed from the 5-year linear price trend, min-max scaled within the cohort, capped at +/- 50% to dampen outliers.
4. **Liveability** is a weighted combination: `0.35 × schools + 0.30 × inverse-crime + 0.25 × transport + 0.10 × healthcare`. Each sub-component maps a categorical or numeric input to a 0–10 score via a documented lookup table.
5. The four components are then combined using the persona weights (default above; configurable in the consumer site and the planned API).

The complete scoring code lives at `index.html:1066-1175` (consumer site) and is being extracted to a shared Lambda at `backend/lambdas/score/` for the B2B API.

## Accuracy and validation

- Postcode-to-borough mapping is verified against the ONS NSPL (National Statistics Postcode Lookup).
- DEFRA noise scores are spot-checked against the legacy `noiseimpact` field and the audit catch on contradictory verdicts (March 2026 release).
- Sold price data is verified against the public Land Registry portal at known transactions.
- EPC band aggregates are sample-validated against the legacy `epc.opendatacommunities.org` portal until the new service has been fully migrated (target: 2026-05-30).
- The score is **not** validated against measured noise at known properties. This validation step is planned before any B2B integration commits to a contractual accuracy claim.

## Limitations

- **OpenSky aircraft tracking** is on the research/non-commercial free tier. Coverage is limited at night and rate-limited to ~10 requests per minute anonymous. The B2B API will use a commercial aviation source (FlightAware Firehose, Flightradar24 Business, or ADS-B Exchange paid tier) before any paying customer integration.
- **Borough-level data** is the highest resolution for several inputs (crime, schools); per-postcode variation within a borough is not always reflected.
- **Price-trend signal** is a simple linear trend; it does not capture cyclical effects or local development announcements.
- **EPC service migration** is in progress; pre-2026-05-30 outputs use the legacy `epc.opendatacommunities.org` API, post-2026-05-30 will use the new `get-energy-performance-data.communities.gov.uk` service.
- **Sky Score is not a regulated valuation** and is not intended as a substitute for an RICS valuation, mortgage survey, or chartered surveyor's report.

## Personal data and GDPR

- The consumer site does not store personally identifiable data on the user beyond a session cookie. Saved favourites are scoped to a free-text userId and a postcode; no email, name, or device identifier is collected.
- Per-property EPC data may include household-identifiable address fields. The consumer site shows aggregated postcode-level summaries by default; per-address detail is rendered only when the user has explicitly searched a single address. The B2B API will provide per-UPRN responses only to authenticated customers with a documented lawful basis.
- All data is processed in AWS eu-west-2 (London) for UK data residency.

## Versioning

The methodology and the API contract are versioned independently:

- **Methodology versions** track changes to scoring logic, weights, or data sources. Breaking changes increment the major version (`Methodology v1.0 → v2.0`).
- **API versions** are pinned in the URL path (`/v1/score`, `/v2/score`) and changes are tracked in `CHANGELOG.md`.
- Score values from prior methodology versions remain reproducible from archived inputs; the API response will include the methodology version used (e.g. `"methodologyVersion": "1.0"`).

## Provenance and integrity

- Source code is open at `https://github.com/billkhiz-bit/london-flight-path-map`.
- Live API URL: `https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/`.
- Issues and methodology questions: open a GitHub issue, or contact via the consumer site.

## Changelog

- **2026-05-05 (v1.0)**: First published methodology document. Aligns with current production scoring; documents EPC migration in progress.
