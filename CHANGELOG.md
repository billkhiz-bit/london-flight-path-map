# Changelog

Sky Score release history. API contract is stable (`/v1/*`); breaking changes deploy under `/v2/*`. Methodology versions are tracked separately in [`METHODOLOGY.md`](./METHODOLOGY.md#20-changelog).

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **Consumer site B2B integration links** (commit `00cf1d7`):
  - Updated `<title>`, meta description, OG tags, Twitter card to reflect dual-product positioning ("UK property quality data, consumer + B2B API"). Removes the original Amazon Nova hackathon framing.
  - Small "DEVELOPERS · API DEMO →" link in the map title block, linking to `/score-demo/`.
  - New site footer at the map bottom-left with: methodology link (GitHub `METHODOLOGY.md`), API reference (Swagger UI), status page, GitHub repo, OGL v3.0 attribution. Hidden on mobile (<768px) to avoid crowding the legend.
  - Consumer features unchanged, no removal, no down-grade.

### Decisions
- **Monetisation strategy resolved** (see [`ROADMAP.md`](./ROADMAP.md#monetisation-strategy-decided-2026-05-05)): Sky Score will charge for *integration value* (SLA, structured JSON, batch, audit trail, methodology pinning, support, contracts) rather than data exclusivity. The consumer site keeps all features; the API earns its price on reliability + ergonomics. Pattern matches Hometrack/Zoopla, Companies House, Land Registry, Ordnance Survey. Revisit triggers documented for if/when a real paying customer asks for restrictions.

### Planned
- DEFRA Lden raster data load (one-shot ~1-hour batch, scaffolded in v3.1)
- Independent measured-noise validation (gating contractual accuracy claims)
- Per-postcode flood risk component (`flood`)
- Per-postcode air quality component (`airQuality`)
- LSOA-level crime breakdown (`crimeBreakdown`)
- Per-customer API keys + Usage Plans (replaces shared free-tier key)
- Optional `/api` landing page (B2B discovery surface, defer until outreach signals warrant)
- Public methodology change-history page
- ISO 27001 / SOC 2 attestation tracks
- MSA + DPA template (use CommonPaper.com or PandaDoc UK template; do not draft from scratch)
- First commercial contract with a paying integrator
- Pricing tier structure firmed up post first prospect conversation

## [3.1], 2026-05-05

### Added
- **NYC ZIP centroids**, ~110 NYC ZIPs now have static centroid lat/lon, enabling the v3.0 per-postcode Haversine layer for NYC postcodes (previously borough-aggregate only). Within-borough variation now works for NYC (e.g. 11201 DUMBO returns quiet=8.0; 11375 Forest Hills returns quiet=2.0 under JFK / LGA traffic).
- **DEFRA raster scaffold**, DynamoDB table `london-flight-map-noise-raster` deployed with IAM read access from the score Lambda. Resolution chain extended: `raster → postcode (Haversine) → borough`. New `context.quietResolution` enum value `'raster'`. Lambda is forward-compatible: empty table falls back transparently to v3.0 Haversine; populating the table silently upgrades to gold-standard precision.
- **`scripts/load_defra_raster.py`**, runbook + code template for the one-shot batch that downloads the DEFRA GeoTIFF, samples at every UK postcode centroid, and writes to DynamoDB.
- **`?include=` query parameter** on `/v1/score`, selective response shape for integrators who only want specific fields.
- **`plannedComponents` field** on `/v1/score` responses, visible roadmap of components on the development plan (`flood`, `airQuality`, `epcDistribution`, `crimeBreakdown`).
- **Public status page** at `/score-demo/status.html`, live endpoint health checks, methodology version, region, SLA reference.
- **Public `CHANGELOG.md`** at repo root (this file).

## [3.0], 2026-05-05

### Added
- **Per-postcode Haversine quiet scoring**, when the API receives a UK postcode (resolved to lat/lon via postcodes.io), the Quiet score is computed at postcode resolution using Haversine distance to airports and flight-path geometry. Same algorithm as the consumer-site neighbourhood scoring (`index.html:1118-1247`); ported to the Lambda.
- 5 London airports tracked (LHR, LGW, LCY, STN, LTN), 4 NYC airports (JFK, LGA, EWR, TEB).
- 12 London flight-path corridors (Lambourne / Biggin / Ockham / Bovingdon stacks; LHR departures; LCY / LGW / LTN approaches), 8 NYC corridors.
- New `context.quietResolution` field (`'postcode' | 'borough'`) reports which tier produced the response.

### Changed
- Hackney N1 7SX `quiet` updates from 10.0 (borough-aggregate "low") to 4.0 (under Lambourne Stack, the LHR east-London arrival corridor).
- Wandsworth SW11 1AA `quiet` updates from 5.0 (borough-aggregate "moderate") to 7.0 (south of major LHR corridors).
- Hounslow TW3 4DX `quiet` updates from 0.0 to 2.0 (still severe, postcode under approach corridor).

### Removed
- Borough Lden band as the default quiet source (still available as fallback when postcode lat/lon unavailable). The borough Lden remains visible in `context.noiseImpactBand` for transparency.

## [2.1], 2026-05-05

### Added
- New benchmark anchors in methodology: HM Land Registry House Price Index (Affordability + Growth), EU Environmental Noise Directive 2002/49/EC (the regulatory framework DEFRA implements for Quiet), Care Quality Commission (roadmap anchor for Healthcare in v3.0+), English Indices of Deprivation (alignment reference for Liveability).

### Changed
- Audit-protection edits across §4.4 (Schools, Crime, Healthcare), §5.2 (Personas), §11 (Editorial), §14 (Comparison): softened Ofsted distribution percentages, clarified crime-rate denominator, removed specific Climate X funding figure, softened Rightmove citation, replaced generic reference URLs with stable government collection pages.

## [2.0], 2026-05-05

### Added
- **OGL attribution** in every data-source response (epc, sold_prices, transport, nhs).
- **`/v1/score/batch`** endpoint, bulk scoring up to 100 queries per call; per-row failure tolerance.
- **`/v1/regions`** endpoint, discovery for supported cities, boroughs, postcode formats.
- **OpenAPI 3.0 spec** at `/score-demo/openapi.yaml`.
- **Interactive Swagger UI** at `/score-demo/api-docs.html`.
- **`sourceBreakdown` field** in score responses, per-component data lineage.
- **Methodology v2.0**, every numeric threshold and weight anchored to a published source or explicitly-acknowledged editorial decision.
- **NYC borough lookup** (`?city=nyc&borough=Manhattan`).
- **NYC ZIP detection** (~182 ZIPs static-mapped; auto-detect in `?postcode=`).
- **postcodes.io in-memory LRU cache** for repeat lookups within a Lambda container.
- **Per-resource CORS** open to `*` for the score endpoints.

## [1.0], 2026-05-05

### Added
- Initial **`/v1/score`** B2B API endpoint.
- **API key auth** via API Gateway Usage Plan (1,000 req/month free tier, 5/sec burst, 2/sec sustained).
- **B2B browser demo** at `/score-demo/index.html`.
- **Public methodology document** (`METHODOLOGY.md` v1.0).

## [0.9], 2026-04-XX

### Added (consumer site, pre-API)
- Sky Score consumer site (London + NYC) at `https://d1oe4ftwutjpf.cloudfront.net/`.
- Sky Score Radar 3D prototype at `/prototype/`.
- Amazon Nova hackathon submission.
