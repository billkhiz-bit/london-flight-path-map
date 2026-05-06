# Sky Score

**A noise + livability data API for UK and NYC property.**

Sky Score scores any UK postcode or NYC ZIP from 0–10 across four components — quiet, affordability, growth, liveability — surfacing the hidden quality factors (aircraft noise, road noise, schools, crime, transport, healthcare) that listings sites are commercially incentivised not to show. For renters and buyers on the consumer side; for property-data aggregators, conveyancers, and Sharia-compliant home-finance providers on the B2B side.

> Methodology v3.1 · API v1.0 · Live in production · 33 London boroughs + 5 NYC boroughs (~182 ZIPs) · Per-postcode Haversine quiet resolution (v3.0) with DEFRA raster scaffold (v3.1)

## Try it in 30 seconds

Browser demo (no setup):
> <https://d1oe4ftwutjpf.cloudfront.net/score-demo/index.html>

Interactive API reference (Swagger UI):
> <https://d1oe4ftwutjpf.cloudfront.net/score-demo/api-docs.html>

Or one curl:

```bash
curl 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/score?postcode=TW3+4DX&persona=family' \
  -H 'X-Api-Key: YOUR_KEY' -H 'Accept: application/json'
```

…returns Hounslow's score with `"quiet": 0.0` (under Heathrow's approach corridor), demonstrating the API correctly flags severe noise that listings sites obscure.

## Live URLs

| What | URL |
|---|---|
| Consumer site | <https://d1oe4ftwutjpf.cloudfront.net/> |
| Sky Score Radar (3D prototype) | <https://d1oe4ftwutjpf.cloudfront.net/prototype/> |
| API browser demo | <https://d1oe4ftwutjpf.cloudfront.net/score-demo/index.html> |
| API reference (Swagger UI) | <https://d1oe4ftwutjpf.cloudfront.net/score-demo/api-docs.html> |
| OpenAPI 3.0 spec | <https://d1oe4ftwutjpf.cloudfront.net/score-demo/openapi.yaml> |
| `/v1/score` endpoint | <https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/score> |
| Methodology | [METHODOLOGY.md](./METHODOLOGY.md) — the document that closes B2B audits |

## Why Sky Score exists

UK property listings sites make money when transactions close. A listing that flags risks — aircraft noise, road noise, poor schools — is a bug in their funnel, not a feature. The data that materially affects whether a property is right for a buyer is systematically absent from the buyer-facing UI.

Sky Score is the ethical alternative data layer:

- **For buyers and renters**: a free site that shows the hidden quality factors *before* a viewing decision.
- **For B2B integrators** — property-data aggregators (Landmark, TM Group), conveyancers, surveyors, build-to-rent operators, and Sharia-compliant home-finance providers (Al Rayan, StrideUp, Gatehouse) — a documented, audit-defensible API.

## API surface

Three endpoints, all API-key gated, all returning JSON.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/score` | Score a single postcode or borough |
| `POST` | `/v1/score/batch` | Bulk lookup, up to 100 queries per call |
| `GET` | `/v1/regions` | Discovery — list supported cities, boroughs, postcode formats |

Free tier: 1,000 requests/month, 5/sec burst, 2/sec sustained. Paid tiers introduced when the first paying integrator commits.

## Quick-start

```bash
# Single lookup, balanced persona
curl 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/score?postcode=N1+7SX' \
  -H 'X-Api-Key: YOUR_KEY'

# Family persona
curl '.../v1/score?postcode=SW11+1AA&persona=family' -H 'X-Api-Key: YOUR_KEY'

# Custom weights override (must sum to 1.0)
curl '.../v1/score?postcode=TW3+4DX&weights=quiet:0.6,afford:0.2,growth:0.1,live:0.1' \
  -H 'X-Api-Key: YOUR_KEY'

# NYC ZIP
curl '.../v1/score?postcode=10001' -H 'X-Api-Key: YOUR_KEY'

# Bulk
curl -X POST '.../v1/score/batch' -H 'X-Api-Key: YOUR_KEY' \
  -H 'Content-Type: application/json' \
  -d '{"queries":[{"postcode":"SW11 1AA"},{"postcode":"10001","persona":"investor"}]}'
```

Response shape (single):

```json
{
  "score": 7.7,
  "components": { "quiet": 10.0, "afford": 7.5, "growth": 5.2, "live": 7.1 },
  "context": {
    "avgPriceGbp": 590000,
    "priceTrendPct": 3.0,
    "noiseImpactBand": "low",
    "quietResolution": "postcode"
  },
  "location": { "city": "london", "borough": "Hackney", "postcode": "N1 7SX" },
  "persona": "balanced",
  "weights": { "quiet": 0.30, "afford": 0.25, "growth": 0.20, "live": 0.25 },
  "methodologyVersion": "3.1",
  "apiVersion": "1.0",
  "sources": [ "EPC data: MHCLG, OGL v3.0", "..." ],
  "sourceBreakdown": {
    "quiet": "DEFRA Strategic Noise Mapping (Round 4, 2022) — borough-aggregate Lden band",
    "afford": "HM Land Registry Price Paid Data — borough cohort min-max scaling",
    "growth": "HM Land Registry Price Paid Data — annualised price trend, cohort-relative",
    "live": "ONS + Home Office + DfE + TfL + NHS — composite weighted"
  }
}
```

Five named persona presets: `balanced`, `family`, `investor`, `firsttime`, `quietlife`. The `?weights=` parameter lets integrators apply their own preference profile.

## What the score measures

Each component is anchored to a published source — see [METHODOLOGY.md](./METHODOLOGY.md) for the full provenance.

| Component | Description | Anchored to |
|---|---|---|
| **Quiet** | Aviation + road noise impact | DEFRA Strategic Noise Mapping (Round 4, 2022) Lden bands; WHO Environmental Noise Guidelines (2018) health thresholds |
| **Affordability** | Sold price relative to cohort | HM Land Registry Price Paid Data |
| **Growth** | Annualised price trend | HM Land Registry Price Paid Data (5-year window) |
| **Liveability** | Schools (35%) + crime (30%) + transport (25%) + healthcare (10%) | Ofsted distribution; ONS/Home Office crime medians; TfL PTAL approximation; NHS England access targets |

The score is fully reproducible — see [the worked example](./METHODOLOGY.md#6-worked-example) for a hand calculation against `SW11 1AA` that matches the live API to within rounding tolerance.

## Coverage

- **London**: 33 boroughs by postcode (postcodes.io resolution)
- **NYC**: 5 boroughs by ZIP (~182 residential ZIPs supported), or by borough name
- **Planned**: UK Core Cities (Manchester, Birmingham, Bristol, Leeds, etc.), then England + Wales

## Architecture

Single-region AWS, fully serverless, deployed via SAM:

```
CloudFront ── S3 (frontend, prototype, score-demo, OpenAPI spec)
                │
API Gateway ── Lambda × 11 ── Bedrock (Nova 2 Lite, Nova Pro, for consumer-side AI)
                            ── DynamoDB (consumer favourites)
                            ── External APIs (postcodes.io, MHCLG EPC, Land Registry,
                                              TfL Open Data, NHS, OpenSky)
```

| Lambda | Path | Purpose |
|---|---|---|
| `score` | `/v1/score`, `/v1/score/batch`, `/v1/regions` | B2B scoring, API-key gated |
| `chat` | `/chat` | Conversational advisor (Nova 2 Lite + Nova Pro auto-routed) |
| `multi_agent` | `/multi-agent` | Orchestrator + specialist agents + synthesiser |
| `analyze_image` / `analyze_document` | `/analyze-image`, `/analyze-document` | Multimodal analysis (Nova Pro) |
| `report` | `/report` | 7-section property report generation |
| `favourites` | `/favourites` | Consumer saved-property storage |
| `epc` | `/epc` | EPC certificate proxy (MHCLG `Get energy performance of buildings data`) |
| `sold_prices` | `/sold-prices` | Land Registry Price Paid Data proxy |
| `transport` | `/transport` | TfL Open Data station + line-status |
| `nhs` | `/nhs` | NHS Service Search |

## Tech stack

- **Frontend**: single-file HTML + D3.js v7, no build step
- **B2B Backend**: Python 3.11 Lambdas with embedded scoring data, `lru_cache`-backed postcode lookups
- **Consumer AI**: Amazon Bedrock (Nova 2 Lite for routing/chat, Nova Pro for reasoning + multimodal)
- **Data residency**: AWS `eu-west-2` (London) for UK GDPR alignment
- **API documentation**: OpenAPI 3.0 spec served from CloudFront, rendered via Swagger UI

## Repo layout

```
.
├── index.html                 # Consumer site (single page)
├── prototype/                 # Sky Score Radar — 3D Three.js prototype
├── score-demo/                # B2B API browser demo + Swagger UI + OpenAPI spec
├── backend/
│   ├── template.yaml          # SAM stack: 11 Lambdas, API Gateway, DynamoDB, Usage Plan
│   ├── lambdas/               # One folder per Lambda
│   └── tests/                 # Unit tests for the score Lambda
├── METHODOLOGY.md             # Public methodology — every threshold anchored to a published source
├── ROADMAP.md                 # Rolling project plan with design notes for deferred work
├── BUILDATHON_PLAN.md         # Shared Futures Buildathon (June 2026) plan
├── OUTREACH_LOG.md            # B2B outreach pipeline tracker
└── tests/                     # Playwright E2E for the consumer site
```

## Local development

Backend deploys require an AWS profile and an EPC bearer token from the [MHCLG service portal](https://get-energy-performance-data.communities.gov.uk/).

```bash
cp .env.example .env
# fill in EPC_BEARER_TOKEN

set -a && source .env && set +a
cd backend && rm -rf .aws-sam && \
  AWS_PROFILE=flightmap sam build && \
  AWS_PROFILE=flightmap sam deploy \
    --parameter-overrides "EpcBearerToken=$EPC_BEARER_TOKEN"
```

Run unit tests:

```bash
python -m unittest backend.tests.test_score -v
```

Frontend deploy commands are in [`CLAUDE.md`](./CLAUDE.md).

## Licence

Proprietary. See [LICENSE](./LICENSE). Source-available for inspection and methodology audit; commercial use requires a licence agreement.

For licensing, integration, or partnership enquiries, contact via the [live site](https://d1oe4ftwutjpf.cloudfront.net/).

## Acknowledgements

The data the API returns is built on UK and US open data — MHCLG, DEFRA, HM Land Registry, ONS, Home Office, Department for Education, TfL, NHS Digital. Contains public sector information licensed under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

The original consumer site was built for the [Amazon Nova AI Hackathon](https://devpost.com/), March 2026, where it received a build credit award. The B2B API and productisation work began May 2026.
