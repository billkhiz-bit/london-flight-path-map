# Sky Score

**A noise + livability data API for UK and NYC property.**

Sky Score scores any UK postcode or NYC ZIP from 0-10 across four components, quiet, affordability, growth, liveability (growth is weighted for the `investor` persona only since methodology v3.3 — it describes the market rather than the property), surfacing the hidden quality factors (aircraft noise, road noise, schools, crime, transport, healthcare) that listings sites are commercially incentivised not to show. For renters and buyers on the consumer side; for property-data aggregators, conveyancers, and Sharia-compliant home-finance providers on the B2B side.

> Methodology v3.3 · API v1.0 · Live in production · **11 cities on `/v1/score`, 3 on the consumer site** · 33 London + 5 NYC + 10 Greater Manchester boroughs on both, plus 8 UK city-regions API-only · Per-postcode Haversine quiet resolution (v3.0) with DEFRA raster scaffold (v3.1)
>
> **Greater Manchester is live on both the site and the API, and is thinner than
> the other two on purpose.** Added 2026-08-09. Its aircraft-noise bands are
> estimated from runway geometry rather than sampled from DEFRA — the map legend
> says so rather than borrowing London's DEFRA labelling — and liveability rests
> on two measured inputs (DfE Progress 8, ONS recorded crime) where London has
> four, with `context.liveResolution` reporting that per response and the absent
> inputs having their weight redistributed rather than filled with a placeholder.
> Road noise, flood risk, air quality, area search and station data do not exist
> for this city and are shown as "NO DATA" rather than left to look sourced.
> Query it with `?borough=Trafford&city=manchester`; **postcode resolution is
> London-only**.

## Try it in 30 seconds

Browser demo (no setup):
> <https://skyscore.co.uk/score-demo/index.html>

Interactive API reference (Swagger UI):
> <https://skyscore.co.uk/score-demo/api-docs.html>

Or one curl:

```bash
curl 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/score?postcode=TW3+4DX&persona=family' \
  -H 'X-Api-Key: YOUR_KEY' -H 'Accept: application/json'
```

…returns Hounslow's score with `"quiet": 0.0` (under Heathrow's approach corridor), demonstrating the API correctly flags severe noise that listings sites obscure.

## Live URLs

| What | URL |
|---|---|
| Consumer site | <https://skyscore.co.uk/> |
| Pricing (B2B API tiers + 90-day pilot) | <https://skyscore.co.uk/pricing> |
| Privacy policy | <https://skyscore.co.uk/privacy> |
| Sky Score Radar (3D prototype) | <https://skyscore.co.uk/prototype/> |
| API landing page | <https://skyscore.co.uk/api/> |
| API browser demo | <https://skyscore.co.uk/score-demo/index.html> |
| API reference (Swagger UI) | <https://skyscore.co.uk/score-demo/api-docs.html> |
| OpenAPI 3.0 spec | <https://skyscore.co.uk/score-demo/openapi.yaml> |
| `/v1/score` endpoint | <https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/score> |
| Methodology | [METHODOLOGY.md](./METHODOLOGY.md), the document that closes B2B audits |

## Install

Sky Score runs as a website, an installable PWA, and a native iOS / Android app — same code, three install paths.

| Platform | How |
|---|---|
| Browser | Visit <https://skyscore.co.uk/> — no install needed |
| Desktop / Android Chrome | Click the install icon in the address bar, or "Install Sky Score" button inside the app |
| iOS Safari (16+) | Tap **Share → Add to Home Screen** |
| iOS App Store | **v1.0.21 live** (<https://apps.apple.com/gb/app/sky-score/id6768118116>) — the native mobile redesign, approved after the 2026-05-29 submission. |
| Google Play Store | Not yet listed — AAB is stale relative to master; rebuild then resume the Play Console flow in `HANDOFF_2026_05_16_play_submission.md` |

The native iOS and Android apps add a "Score where I am" button that uses your phone's GPS for instant scoring of your current location. See [`mobile/`](./mobile/) for the Capacitor + Codemagic build setup.

## Why Sky Score exists

UK property listings sites make money when transactions close. A listing that flags risks, aircraft noise, road noise, poor schools, is a bug in their funnel, not a feature. The data that materially affects whether a property is right for a buyer is systematically absent from the buyer-facing UI.

Sky Score is the ethical alternative data layer:

- **For buyers and renters**: a free site that shows the hidden quality factors *before* a viewing decision.
- **For B2B integrators**, property-data aggregators (Landmark, TM Group), conveyancers, surveyors, build-to-rent operators, and Sharia-compliant home-finance providers (Al Rayan, StrideUp, Gatehouse), a documented, audit-defensible API.

## API surface

Six endpoints returning JSON. Four are API-key gated. Two are deliberately public: `/v1/changes`, so anyone can audit what moved between vintages without holding a key, and `/v1/environment`, because it serves a browser extension that cannot keep a key secret — which is why it returns measurements only and never a score.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/score` | Score a single postcode or borough |
| `POST` | `/v1/score/batch` | Bulk lookup, up to 100 queries per call |
| `GET` | `/v1/regions` | Discovery, list supported cities, boroughs, postcode formats |
| `POST` | `/v1/chat` | Retrieval-only assistant; answers are discarded if they contain a number the retrieved data does not |
| `GET` | `/v1/changes` | **Public.** What moved between data vintages, and why |
| `GET` | `/v1/environment` | **Public.** Aircraft/road Lden, NO2 and PM2.5 for a coordinate, each against its WHO guideline. No weights, no persona, no composite score |

Free tier: 100 requests/month, 5/sec burst, 1/sec sustained — and because a batch request carries up to 100 addresses for one request, that is a ceiling of 10,000 scores/month. Paid tiers introduced when the first paying integrator commits.

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
  "score": 6.4,
  "components": { "quiet": 5.0, "afford": 7.2, "growth": 7.8, "live": 7.2 },
  "context": {
    "avgPriceGbp": 608000,
    "priceTrendPct": 2.8,
    "noiseImpactBand": "low",
    "quietResolution": "postcode",
    "liveResolution": "measured"
  },
  "location": { "city": "london", "borough": "Hackney", "postcode": "N1 7SX" },
  "persona": "balanced",
  "weights": { "quiet": 0.38, "afford": 0.31, "growth": 0.00, "live": 0.31 },
  "methodologyVersion": "3.5",
  "apiVersion": "1.0",
  "sources": [ "EPC data: MHCLG, Open Government Licence v3.0", "..." ],
  "sourceBreakdown": {
    "quiet": "DEFRA Strategic Noise Mapping (Round 4, 2022). Resolution chain: v3.1 raster sample -> v3.0 Haversine to airports + flight-path geometry -> v2.x borough-aggregate Lden band. The chosen resolution is reported in context.quietResolution.",
    "afford": "HM Land Registry House Price Index (HPI), borough cohort min-max scaling",
    "growth": "HM Land Registry House Price Index (HPI), annualised price trend, cohort-relative",
    "live": "Composite weighted (schools 35% + crime 30% + transport 25% + healthcare 10%). Schools: DfE Key Stage 4 Progress 8, 2022/23. Crime: ONS Crime in England and Wales, PFA data tables, Table C4. Transport and healthcare: curated tiers."
  }
}
```

> **Captured from the live API on 2026-08-04, not hand-written.** The block above previously
> carried `score: 7.7` with `methodologyVersion: "3.3"` and every component value stale, and its
> `sourceBreakdown` credited **Home Office** for crime (re-sourced to ONS Table C4 in v3.5),
> **NHS** for healthcare (curated tiers), and **Price Paid Data** for affordability and growth
> where the engine uses **HPI** — while the table further down this same file already said HPI.
> Re-capture it when the methodology version moves rather than editing values by hand.

**Eight** named persona presets: `balanced`, `family`, `investor`, `firsttime`, `quietlife`,
`renter`, `commuter`, `laterlife`. The `?weights=` parameter lets integrators apply their own
preference profile instead. (This said "five" until 2026-08-04, omitting the last three — the
same undercount that made the OpenAPI spec reject valid requests until it was corrected.)

## What the score measures

Each component is anchored to a published source, see [METHODOLOGY.md](./METHODOLOGY.md) for the full provenance.

| Component | Description | Anchored to |
|---|---|---|
| **Quiet** | **Aircraft noise only.** Road noise is a map overlay on the consumer site and is **not** a score input | DEFRA Strategic Noise Mapping (Round 4, 2022) aircraft Lden; WHO Environmental Noise Guidelines (2018) health thresholds. **Live tier is Haversine to airports + flight-path geometry** — the direct raster tier is quarantined, see [METHODOLOGY §4.5](./METHODOLOGY.md) |
| **Affordability** | Sold price relative to cohort | HM Land Registry House Price Index (HPI) |
| **Growth** | Annualised price trend | HM Land Registry House Price Index (HPI) |
| **Liveability** | Schools (35%) + crime (30%) + transport (25%) + healthcare (10%) | DfE Key Stage 4 Progress 8 (2022/23); ONS *Crime in England and Wales* PFA tables, Table C4; TfL PTAL approximation; curated healthcare tiers |

The score is reproducible by hand from [METHODOLOGY §4](./METHODOLOGY.md) and the persona weights in §5.1, against the current data snapshot.

> **Corrected 2026-08-04.** This paragraph said the [worked example](./METHODOLOGY.md#6-worked-example) "reproduces the live API exactly" and that a mismatch should be reported as a bug. **§6 of that document says the opposite** — it is explicitly retained as a **historical trace of v3.0** and "no longer matches the live API, and has not since v3.2", because of the v3.2 clamp, the v3.3 weighting change and the v3.4 dual-anchor growth formula. Anyone following the old instruction would have filed a bug against a discrepancy the methodology already documents. The example is still worth reading for the *method*; it is not a current-values check.

## Coverage

- **London**: 33 boroughs by postcode (local ONS NSPL table, postcodes.io fallback)
- **NYC**: 5 boroughs by ZIP (~182 residential ZIPs supported), or by borough name
- **Greater Manchester**: 10 boroughs **by borough name only** — postcode
  resolution is London-only, because `resolve_query()` gates it there *and*
  `scripts/load_nspl.py` writes the borough attribute for London LADs alone.
  Two blockers, not one. On the site and the API.
- **Eight further UK city-regions, on `/v1/score` only** (2026-08-10): West
  Midlands, West Yorkshire, South Yorkshire, Merseyside, Tyne and Wear, Bristol,
  Cardiff, Nottingham. Prices, trends, crime, Progress 8 and boundaries are all
  script-derived and verified against the publishing body; aircraft bands are an
  **estimate from runway geometry, not DEFRA**. They are declared in
  `BACKEND_ONLY_CITIES`, not discovered, and reach the consumer site when the
  boundary loader stops being a per-city if/else chain.
- **Planned**: the rest of England and Wales. Both the price and crime loaders
  are already parameterised by city, so roughly 318 local authorities are
  reachable without new research. The site's locator inset names the ten UK core
  cities and marks which are live.

**What "supported" means per city**, because it is not uniform:

| | London | NYC | Greater Manchester | The other 8 |
|---|---|---|---|---|
| On the consumer site | yes | yes | yes, visibly thinner | **no - API only** |
| Lookup | postcode or borough | ZIP or borough | **borough only** | **borough only** |
| Aircraft noise | DEFRA raster where covered, else geometry | curated bands from approach geometry | **runway geometry only, not DEFRA** | **runway geometry only, not DEFRA** |
| Liveability inputs | 4 of 4 (32 of 33 boroughs) | 4 of 4 | **2 of 4** (schools, crime) | **2 of 4**, except Cardiff **1 of 4** (no Progress 8 in Wales) |
| Quarterly comparison | yes | yes | **declines** — no prior vintage exists | **declines** — no prior vintage |

Absent liveability inputs are **not** estimated: their weight is redistributed
across the measured ones, and `context.liveResolution` states how many were
measured. Affordability and growth are scaled **within** each city's cohort, so
those two components are not comparable between cities — compare
`context.avgPriceGbp` directly instead.

### Environmental measurements (`/v1/environment`), as at 2026-08-08

These are **reported, not scored** — weighting them would change every score the
API has ever returned. Coverage differs enormously per measurement, and the
figures below describe **what the table actually holds**, not what the source
grids contain:

| Measurement | Coverage | Note |
|---|---|---|
| Aircraft Lden | ~9% of London postcodes | DEFRA's contours are localised lobes around airports. Outside them there is no reading, and the endpoint **omits the key** rather than returning a default |
| Road Lden | Complete across the London raster | Finished 2026-08-08. Was missing everything from `UB6` onward — `W`, `WC`, `WD` — for two days before that |
| NO₂ / PM2.5 | **Loading; London not yet reached** | The pass runs in postcode-alphabetical order over the whole UK, so early-alphabet regions have figures well before London does |

A missing key means "not measured here", never "measured and fine" — the
distinction is deliberate, and it is also what let an unrun loader look
identical to genuine absence for a day. See `CHANGELOG.md` for both corrections.

## Architecture

Single-region AWS, fully serverless, deployed via SAM:

```
CloudFront ── S3 (frontend, prototype, score-demo, OpenAPI spec)
                │
API Gateway ── Lambda × 8 active ── DynamoDB (favourites, signups, DEFRA
                                 │              noise raster, ONS NSPL postcodes)
                                 ── External APIs (postcodes.io fallback, MHCLG EPC,
                                                   Land Registry, TfL, NHS)
```

| Lambda | Path | Purpose |
|---|---|---|
| `score` | `/v1/score`, `/v1/score/batch`, `/v1/regions`, `/v1/changes`, `/v1/environment` | B2B scoring, API-key gated except `/v1/changes` and `/v1/environment` |
| `chat` | `/v1/chat` | Retrieval-only assistant; context comes from invoking `score` directly, never from the model |
| `signup` | `/v1/signup` | Self-service API-key issuance |
| `favourites` | `/favourites` | Consumer saved-property storage (`X-Device-Token` auth) |
| `epc` | `/epc` | EPC certificate proxy (MHCLG `Get energy performance of buildings data`) |
| `sold_prices` | `/sold-prices` | Land Registry Price Paid Data proxy |
| `transport` | `/transport` | TfL Open Data station + line-status |
| `nhs` | `/nhs` | NHS Service Search |

**Removed surfaces (kept in git history):** Five Bedrock Lambdas (`chat`, `multi_agent`, `analyze_image`, `analyze_document`, `report`) and the OpenSky-backed `live_flights` Lambda were deployed earlier but removed end-to-end in May 2026 — Bedrock to align the consumer surface with the methodology-defensibility positioning of the B2B API, OpenSky pending a written commercial-use agreement. Restoration: `git revert` of commits `69905ee` + `71a731c` + `6bad8ce` for AI features; restore `live_flights/` + flip prototype's `liveLicensed` flag for live aircraft. See `LICENSING.md` for the OpenSky context.

## Tech stack

- **Frontend**: single-file HTML + D3.js v7, no build step
- **B2B Backend**: Python 3.11 Lambdas with embedded scoring data, `lru_cache`-backed postcode lookups
- **Data residency**: AWS `eu-west-2` (London) for UK GDPR alignment
- **API documentation**: OpenAPI 3.0 spec served from CloudFront, rendered via Swagger UI

## Repo layout

```
.
├── index.html # Consumer site (single page)
├── prototype/ # Sky Score Radar, 3D Three.js prototype
├── score-demo/ # B2B API browser demo + Swagger UI + OpenAPI spec
├── backend/
│ ├── template.yaml # SAM stack: 8 Lambdas, API Gateway (per-route throttle), 4× DynamoDB (PITR-ready), Usage Plan
│ ├── lambdas/ # One folder per Lambda
│ └── tests/ # Unit tests: score engine + handler suite
├── METHODOLOGY.md # Public methodology, every threshold anchored to a published source
├── ROADMAP.md # Rolling project plan with design notes for deferred work
├── BUILDATHON_PLAN.md # Shared Futures Buildathon (June 2026) plan
├── OUTREACH_LOG.md # B2B outreach pipeline tracker
└── tests/ # Playwright E2E + per-Lambda pytest suites (rewritten 2026-07-24)
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

For licensing, integration, or partnership enquiries, contact via the [live site](https://skyscore.co.uk/).

## Acknowledgements

The data the API returns is built on UK and US open data, MHCLG, DEFRA, HM Land Registry, ONS, Home Office, Department for Education, TfL, NHS Digital. Contains public sector information licensed under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

The original consumer site was built for the Amazon Nova AI Hackathon, March 2026, where it received a build credit award. The B2B API and productisation work began May 2026; the consumer-side AI features built for the hackathon were retired from the UI in May 2026 to align the consumer surface with the methodology-defensibility positioning of the B2B API. Their Lambda code and template entries live in git history for potential future re-introduction.
