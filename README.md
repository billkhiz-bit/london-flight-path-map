# Sky Score

**A noise + livability data API and consumer site for UK property.**

Sky Score scores any UK postcode from 0–10 across four components — quiet, affordability, growth, and liveability — surfacing the hidden harms (aircraft noise, road noise, neighbourhood quality) that listings sites have a financial incentive to obscure. Designed for renters and buyers on the consumer side, and for property data aggregators, conveyancers, and Sharia-compliant home-finance providers on the B2B side.

## Live

| What | URL |
|---|---|
| Consumer site | <https://d1oe4ftwutjpf.cloudfront.net/> |
| Sky Score Radar (3D prototype) | <https://d1oe4ftwutjpf.cloudfront.net/prototype/> |
| API tester (browser demo) | <https://d1oe4ftwutjpf.cloudfront.net/score-demo/index.html> |
| `/v1/score` API | <https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/score> |
| Methodology | [METHODOLOGY.md](./METHODOLOGY.md) |

## Why Sky Score exists

UK property listings sites are run by businesses whose revenue depends on transactions closing. A listing that flags risks — aircraft noise, road noise, poor schools — is a bug in their funnel. As a result, data that materially affects whether a property is right for a given buyer is systematically absent from the buyer-facing UI.

Sky Score is the ethical alternative data layer:

- **For buyers and renters**, a free site that shows the hidden quality factors before a viewing decision.
- **For B2B integrators** — property-data aggregators, conveyancers, surveyors, build-to-rent operators, and Sharia-compliant home-finance providers — a documented API that returns transparent component scores for any UK postcode.

## API quick-start

The `/v1/score` endpoint is API-key gated with a 1000 req/month free tier. To get a key, contact via the live site.

```bash
curl 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/score?postcode=N1+7SX' \
  -H 'X-Api-Key: YOUR_KEY' \
  -H 'Accept: application/json'
```

Response shape:

```json
{
  "score": 7.7,
  "components": { "quiet": 10.0, "afford": 7.5, "growth": 5.2, "live": 7.1 },
  "context": {
    "avgPriceGbp": 590000,
    "priceTrendPct": 3.0,
    "noiseImpactBand": "low"
  },
  "location": { "borough": "Hackney", "postcode": "N1 7SX", "city": "london" },
  "persona": "balanced",
  "weights": { "quiet": 0.30, "afford": 0.25, "growth": 0.20, "live": 0.25 },
  "methodologyVersion": "1.1",
  "sources": [ "EPC data: MHCLG, OGL v3.0", "..." ]
}
```

Five named persona presets are available (`balanced`, `family`, `investor`, `firsttime`, `quietlife`) and `?weights=quiet:0.5,afford:0.2,growth:0.1,live:0.2` lets integrators apply their own preference profile.

For the full contract, see [METHODOLOGY.md §14](./METHODOLOGY.md). For a try-it-now browser demo, open the [score demo](https://d1oe4ftwutjpf.cloudfront.net/score-demo/index.html).

## What the score measures

| Component | Description | Source |
|---|---|---|
| **Quiet** | Aviation + road noise impact band | DEFRA strategic noise mapping (England round 4, 2022) |
| **Affordability** | Average sold price relative to cohort | HM Land Registry Price Paid Data |
| **Growth** | 5-year linear price trend | HM Land Registry Price Paid Data |
| **Liveability** | Schools, crime, transport, healthcare | ONS, DfE, Home Office, TfL, NHS Service Search |

The score and methodology are fully transparent — see the [worked example](./METHODOLOGY.md#5-worked-example) for a step-by-step calculation reproducible against the live API.

## Coverage

- **Live**: 33 London boroughs (32 boroughs plus the City of London)
- **Planned**: New York City (data already in code, API integration pending), UK Core Cities, England + Wales

## Architecture

Single-region AWS, fully serverless, deployed via SAM:

```
CloudFront ── S3 (frontend, prototype, score-demo)
                │
API Gateway ── Lambda × 11 ── Bedrock (Nova 2 Lite, Nova Pro)
                            ── DynamoDB (favourites)
                            ── External APIs (postcodes.io, MHCLG EPC, Land Registry,
                                              TfL Open Data, NHS, OpenSky)
```

| Lambda | Path | Purpose |
|---|---|---|
| `score` | `/v1/score` | B2B-facing structural score, API-key gated |
| `chat` | `/chat` | Conversational property advisor (Nova 2 Lite + Nova Pro auto-routed) |
| `multi_agent` | `/multi-agent` | Orchestrator + 3 specialist agents + synthesiser (Nova Pro) |
| `analyze_image` | `/analyze-image` | Listing photo analysis (Nova Pro multimodal) |
| `analyze_document` | `/analyze-document` | EPC / survey document analysis (Nova Pro multimodal) |
| `report` | `/report` | 7-section property report generation (Nova Pro) |
| `favourites` | `/favourites` | Saved-property storage (DynamoDB) |
| `epc` | `/epc` | EPC certificate proxy (MHCLG `Get energy performance of buildings data` service) |
| `sold_prices` | `/sold-prices` | Land Registry Price Paid Data proxy |
| `transport` | `/transport` | TfL Open Data station + line-status proxy |
| `nhs` | `/nhs` | NHS Service Search proxy |

## Tech stack

- **Frontend**: single-file HTML + D3.js v7, no build step
- **Backend**: Python 3.11 Lambdas, AWS SAM template
- **AI**: Amazon Bedrock (Nova 2 Lite for routing/chat, Nova Pro for reasoning + multimodal)
- **Data residency**: AWS eu-west-2 (London) for UK GDPR alignment

## Repo layout

```
.
├── index.html                 # Consumer site (single page)
├── prototype/                 # Sky Score Radar (3D Three.js prototype)
├── score-demo/                # B2B API browser demo (this is the page prospects open)
├── backend/
│   ├── template.yaml          # SAM stack: 11 Lambdas, API Gateway, DynamoDB, Usage Plan
│   └── lambdas/               # One folder per Lambda, app.py + minimal deps
├── METHODOLOGY.md             # Public methodology — the document that closes B2B audits
├── ROADMAP.md                 # Rolling project plan
├── BUILDATHON_PLAN.md         # Shared Futures Buildathon (June 2026) plan
└── tests/                     # Playwright E2E
```

## Local development

Backend deploys require an AWS profile with rights to the SAM stack. The EPC service requires a bearer token from the MHCLG portal.

```bash
# Copy the env template, fill in the EPC bearer token
cp .env.example .env

# Deploy backend (sources EPC token from .env)
set -a && source .env && set +a
cd backend && rm -rf .aws-sam && \
  AWS_PROFILE=flightmap sam build && \
  AWS_PROFILE=flightmap sam deploy \
    --parameter-overrides "EpcBearerToken=$EPC_BEARER_TOKEN"
```

Frontend deploy commands are in [`CLAUDE.md`](./CLAUDE.md).

## Licence

Proprietary. See [LICENSE](./LICENSE). Source-available for inspection and methodology audit; commercial use requires a licence agreement.

For licensing, integration, or partnership enquiries, contact via the [live site](https://d1oe4ftwutjpf.cloudfront.net/).

## Acknowledgements

The data the API returns is built on UK and US open data — Department for Levelling Up, Housing and Communities (now MHCLG), DEFRA, HM Land Registry, ONS, Home Office, Department for Education, TfL, NHS Digital. Contains public sector information licensed under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

The original consumer site was built for the [Amazon Nova AI Hackathon](https://devpost.com/), March 2026, where it received a build credit award. The B2B API and productisation work began May 2026.
