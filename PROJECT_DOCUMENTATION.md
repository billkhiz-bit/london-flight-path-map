# Sky Score - Complete Project Documentation

_Last full refresh: 2026-07-24 (audit item I14)._

## Project Overview

**Sky Score** is a noise + livability data product for UK and NYC property. Two surfaces:

- **Consumer site**, public, free, no sign-up. Helps renters and buyers see the structural data (aircraft noise, road noise, schools, crime, transport, healthcare) that listings sites are commercially incentivised not to surface. London + NYC, postcode/ZIP-level for both.
- **B2B API** (`/v1/score`, `/v1/score/batch`, `/v1/regions`), productised endpoint for property data aggregators, conveyancers, and Sharia-compliant home-finance providers. Methodology fully published, OpenAPI 3.0 spec, free tier 1000 req/month, self-service signup at `/v1/signup`.

Coverage today: 33 London boroughs (postcode resolution via DEFRA Lden raster + Haversine fallback) + 5 NYC boroughs (~182 residential ZIPs, ~110 with per-ZIP centroids).

**Live URL:** https://skyscore.co.uk
**API:** https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/
**Methodology:** [METHODOLOGY.md](./METHODOLOGY.md) (v3.1)
**GitHub:** https://github.com/billkhiz-bit/london-flight-path-map
**Origin + pivot:** Built for the Amazon Nova AI Hackathon (March 2026, won $200 AWS credits, blog category). Productised post-hackathon as a B2B API; consumer-side AI features (chat, multi-agent, document analysis, AI report) removed from the UI in May 2026 to align the consumer narrative with the methodology-defensibility positioning of the B2B API. The Bedrock Lambda code and template entries now live in git history only (verified 2026-07-23: `template.yaml` holds just the 7 active functions); re-introduction means restoring both from history.

---

## Architecture

### AWS Services Used

| Service | Purpose | Region |
|---------|---------|--------|
| **AWS Lambda** | 7 functions (Python 3.11); the 5 former Bedrock AI Lambdas live in git history only | eu-west-2 |
| **Amazon API Gateway** | REST API with CORS, per-route throttling, Usage Plans | eu-west-2 |
| **Amazon S3** | Static website hosting | eu-west-2 |
| **Amazon CloudFront** | Global CDN with HTTPS, custom domain `skyscore.co.uk` | Global |
| **Amazon DynamoDB** | Favourites + DEFRA noise raster + signup audit log | eu-west-2 |
| **AWS SAM/CloudFormation** | Infrastructure as code | eu-west-2 |
| **AWS IAM** | Least-privilege access control (tag-condition scope-down on signup `apigateway:DELETE`) | Global |
| **Amazon CloudWatch** | Logging and monitoring (`[SIGNUP_ORPHAN_KEY]` structured-log alarm filter) | eu-west-2 |
| **Amazon Bedrock** | (Historical) Nova 2 Lite + Nova Pro for the 5 removed AI Lambdas; nothing in the deployed stack invokes Bedrock | us-east-1 |
| **AWS STS** | (Historical) Cross-region model access; only relevant if the Bedrock Lambdas are restored from git history | us-east-1 |

### Data Sources (10+ live APIs)

**London:**
1. **DEFRA Strategic Noise Maps** - Official UK government aircraft and road noise contours (WMS)
2. **Met Police Crime Statistics** - Curated borough-level crime rates
3. **TfL Unified API** - Live nearest stations, line status, distances
4. **MHCLG EPC service** - Energy Performance Certificates by postcode (`get-energy-performance-data.communities.gov.uk`; replaced Open Data Communities, retired 2026-05-30)
5. **HM Land Registry** - Price Paid Data for sold property prices
6. **NHS/Healthcare Data** - GP surgery and hospital information
7. **Postcodes.io** - Geolocation, autocomplete, outcode lookup
8. **Environment Agency** - Flood risk zones (WMS)

**New York City:**
9. **BTS/DOT** - Aviation noise contours (ArcGIS REST)
10. **FEMA NFHL** - Flood zones (ArcGIS REST)
11. **EPA** - Air quality nonattainment areas (ArcGIS REST)
12. **NYPD CompStat** - Crime data

---

## Amazon Nova Integration — DORMANT (May 2026)

**Status: dormant since 2026-05-07; removed from the working tree since.** All consumer-side AI features were removed from the UI as part of the data-first repositioning, and the Lambda code + `template.yaml` entries were subsequently removed too — both live in git history only (verified 2026-07-23). Re-enabling means restoring code and template entries from history, redeploying, and unhiding the frontend block. The descriptions below document what these Lambdas *do* when invoked — useful reference for any future re-introduction (e.g. user-triggered "explain in plain English" button, constrained EPC summariser).

### Nova 2 Lite (`us.amazon.nova-2-lite-v1:0`)
- **Multi-turn AI chatbot** with conversation history (last 8 messages)
- **Context-aware**: knows what location the user is currently viewing
- **Auto-insights**: generates a 2-3 sentence buyer insight for every postcode search
- **Borough data**: structured data for London boroughs and NYC neighbourhoods (noise, prices, crime, schools, transport, flood, air quality)
- Used for simple queries to keep costs low and responses fast

### Nova Pro (`us.amazon.nova-pro-v1:0`)
- **Complex reasoning**: automatically routes multi-criteria queries (comparisons, recommendations, investment analysis) to Pro
- **Property photo analysis** (multimodal): upload a listing photo, Nova Pro analyzes property type, condition, glazing, and buyer concerns
- **EPC certificate analysis** (multimodal): upload an EPC PDF/image, Nova Pro extracts ratings, insulation details, and improvement recommendations
- **Survey report analysis** (multimodal): upload a survey, Nova Pro summarizes structural issues, damp, and negotiation points
- **AI report generation**: generates comprehensive 7-section Property Intelligence Reports with executive summary, noise assessment, market analysis, amenities, risks, investment outlook, and verdict

### Intelligent Model Routing
The chat Lambda detects query complexity using keyword analysis:
- Simple queries ("What's the noise like in Hounslow?") -> Nova 2 Lite (fast, cheap)
- Complex queries ("Compare the top 5 boroughs for a family with 600K budget commuting to Canary Wharf") -> Nova Pro (deeper reasoning)
- Keywords trigger Pro: compare, recommend, rank, investment, budget, commute, vs, negotiate, top 5, first time buyer, etc.

### Multi-Agent Orchestration
For complex queries (comparisons, multi-criteria recommendations), the system activates a multi-agent pipeline:

1. **Orchestrator** (Nova 2 Lite) - analyses the query, decomposes it into sub-tasks, determines which specialist agents to invoke
2. **Noise Analyst Agent** (Nova 2 Lite) - assesses aircraft noise, airport proximity, flight path impact, and sound insulation needs
3. **Property Researcher Agent** (Nova 2 Lite) - analyses prices, affordability, growth trends, and investment potential
4. **Neighbourhood Scorer Agent** (Nova 2 Lite) - evaluates schools, crime, transport, healthcare, and overall livability
5. **Synthesiser** (Nova Pro) - combines all agent outputs into a single coherent recommendation with trade-offs

Agents run in parallel using `concurrent.futures.ThreadPoolExecutor`, then Nova Pro synthesises the results. The frontend shows which agents contributed to each response.

---

## Lambda Functions (7 active)

### Active

#### 1. ScoreFunction (`/v1/score`, `/v1/score/batch`, `/v1/regions` GET/POST)
- **File:** `backend/lambdas/score/app.py`
- **Purpose:** B2B scoring engine — main product. Returns `score`, `components`, `context`, `sources`. v3.1 raster-first resolution chain falling back to Haversine then borough.
- **Auth:** API key gated via APIGW Usage Plan (`SkyScoreFreeTier`: 1000 req/month, 5/sec burst)

#### 2. SignupFunction (`/v1/signup` POST)
- **File:** `backend/lambdas/signup/app.py`
- **Purpose:** Self-service API key issuance (one key per email, idempotent on retry, race-recovered on collision)
- **Hardening (2026-05-07):** Tag-based IAM scope-down on `apigateway:DELETE`; per-route APIGW throttle 1 RPS / 5 burst; CORS allow-list (no wildcard); `[SIGNUP_ORPHAN_KEY]` structured-log alarm filter

#### 3. FavouritesFunction (`/favourites` GET/POST/DELETE)
- **File:** `backend/lambdas/favourites/app.py`
- **Purpose:** Save/load/delete favourite locations
- **Auth:** `X-Device-Token` UUID header (audit C3 mitigation)
- **Storage:** DynamoDB table `london-flight-map-favourites`

#### 4. EpcFunction (`/epc` GET)
- **File:** `backend/lambdas/epc/app.py`
- **Purpose:** MHCLG EPC certificate proxy via the new `get-energy-performance-data.communities.gov.uk` service (post-2026-05-30 migration)
- **Auth:** Bearer token from `EPC_BEARER_TOKEN` SAM parameter

#### 5. SoldPricesFunction (`/sold-prices` GET)
- **File:** `backend/lambdas/sold_prices/app.py`
- **Purpose:** Land Registry Price Paid Data proxy (CORS)

#### 6. TransportFunction (`/transport` GET)
- **File:** `backend/lambdas/transport/app.py`
- **Purpose:** TfL nearest stations and live line status

#### 7. NhsFunction (`/nhs` GET)
- **File:** `backend/lambdas/nhs/app.py`
- **Purpose:** Nearby NHS services via OSM Overpass (replaced the deprecated NHS Service Search public key)

### Dormant (git history only) — 2026-05-07

The five Lambdas below were removed from `template.yaml` and the working tree; code and template entries live in git history only (verified 2026-07-23). Their per-Lambda detail is preserved here for reference if any feature is re-introduced; numbering continues from the active list for historical continuity.

#### 8. ChatFunction (`/chat` POST) — DORMANT
- **File:** `backend/lambdas/chat/app.py`
- **Purpose:** AI chatbot with multi-turn conversation and auto-insights
- **Models:** Nova 2 Lite (simple) + Nova Pro (complex, auto-routed)
- **Modes:** `chat` (conversation) and `insight` (auto-generation)

#### 9. MultiAgentFunction (`/multi-agent` POST) — DORMANT
- **File:** `backend/lambdas/multi_agent/app.py`
- **Purpose:** Multi-agent orchestration for complex queries
- **Models:** Nova 2 Lite (orchestrator + 3 agents) + Nova Pro (synthesiser)
- **Timeout:** 90s (runs 4 Bedrock calls in parallel + synthesis)

#### 10. AnalyzeImageFunction (`/analyze-image` POST) — DORMANT
- **File:** `backend/lambdas/analyze_image/app.py`
- **Purpose:** Multimodal property photo analysis
- **Model:** Nova Pro (image understanding)

#### 11. AnalyzeDocumentFunction (`/analyze-document` POST) — DORMANT
- **File:** `backend/lambdas/analyze_document/app.py`
- **Purpose:** EPC certificate and survey report analysis
- **Model:** Nova Pro (document understanding)

#### 12. ReportFunction (`/report` POST) — DORMANT
- **File:** `backend/lambdas/report/app.py`
- **Purpose:** Comprehensive AI-generated property intelligence reports
- **Model:** Nova Pro
- **Timeout:** 90s

### Removed — 2026-05-07

`live_flights` (OpenSky `/api/states/all` proxy for live aircraft positions) was removed end-to-end pending OpenSky's licensing reply (Ticket #835285). Code lives in git history (last working commit `a214ba0`). See `LICENSING.md` "Removed sources" + `OPENSKY_LICENSING_EMAIL.md`.

---

## Frontend Architecture

### Single-Page Application
- **File:** `index.html` (~8,200 lines as of 2026-07-24)
- **Framework:** None (vanilla JavaScript)
- **Mapping:** D3.js v7 with SVG-based interactive rendering
- **Build step:** None required for the web target; the native target uses `mobile/scripts/copy-web.mjs` to assemble a `www/` bundle but doesn't bundle or transpile
- **Styling:** Custom CSS with CSS variables for theming
- **Three install paths from one codebase**: web, PWA, native iOS/Android (see "Mobile / Native Apps" section below)

### Key Frontend Features

#### Multi-City Support (London + New York)
- City selector toggles between London and New York
- Each city has its own airports, flight paths, borough/neighbourhood data, and GeoJSON
- London: 33 boroughs, 5 airports, 5 heliports, ~143 neighbourhoods
- New York: 5 boroughs, 4 airports, ~151 neighbourhoods

#### Search System
- **Full postcode** (SW11 1AA) - exact location analysis
- **Partial postcode/outcode** (TW3, SW1) - area-level analysis via outcodes API
- **Area/neighbourhood** (Chelsea, Twickenham, Astoria) - hundreds of areas mapped to postcodes for the consumer-site search
- **Borough name** (Hounslow, Queens) - borough-level view
- **Autocomplete** with debounced API calls and keyboard navigation

#### Postcode-Specific Buyer Value Score (1-10)
Each searchable area gets a score computed from four factors:
1. **Quiet Skies** - actual geographic distance (Haversine formula) to airports and flight path corridors
2. **Affordability** - neighbourhood-specific median prices (not borough averages)
3. **Growth** - annual price trend percentage
4. **Liveability** - composite of schools (35%), crime safety (30%), transport access (25%), and healthcare (10%)

**Eight Buyer Personas** (Balanced, Family, Investor, First-Time, Quiet Life, Renter, Commuter, Later Life) dynamically reweight all four factors and instantly re-rank every postcode / borough / neighbourhood.

#### Interactive Map Data Layers (Toggle On/Off)
| Layer | London Source | NYC Source |
|-------|-------------|-----------|
| Flight Paths | Manual path data | Manual path data |
| Aircraft Noise | DEFRA WMS (dB Lden) | BTS/DOT ArcGIS (dB DNL) |
| Road Noise | DEFRA WMS (zoom-triggered, borough level+) | DOT ArcGIS |
| Transport Stations | 18 major hubs | 16 major hubs |
| Flood Risk | Borough-level EA data + WMS at street zoom | Borough-level FEMA data + ArcGIS REST |
| Air Quality | Borough-level coloring + DEFRA AQMA WMS | Borough-level coloring + EPA Nonattainment ArcGIS REST |

Four overlay rendering engines handle different government data standards:
1. **WMS** - for DEFRA noise and air quality data (EPSG:4326 bbox, zoom-aware refresh)
2. **ArcGIS REST export** - for EPA air quality (single image per viewport)
3. **Tile grid rendering** - for BTS aviation/road noise (computing slippy map tile coordinates)
4. **Borough SVG overlay** - flood risk and air quality rendered as colour-coded borough polygons, visible at all zoom levels

#### AI Features (Frontend) — removed from the UI May 2026
The blocks below were removed in the data-first repositioning; descriptions preserved as re-introduction reference:
- **Chat FAB button** - "ASK AI" pill button with pulsing glow
- **Multi-turn chat panel** - conversation history, context awareness
- **Photo upload** - camera button in chat for property photo analysis
- **Auto AI insight** - generated for every postcode search
- **Document upload** - EPC and survey analysis in sidebar
- **Report generation** - full report with print/PDF support
- **Pro indicator** - shows when Nova Pro handles a complex query
- **Multi-agent badges** - shows which specialist agents contributed to a response

#### Favourites System
- Save/unsave postcode locations with one click
- Stored in DynamoDB via device ID
- "SAVED" tab in sidebar shows all bookmarked locations
- Click a favourite to jump back to that analysis

---

## DynamoDB Schema

### Table: `london-flight-map-favourites`

| Attribute | Type | Key |
|-----------|------|-----|
| userId | String | Partition Key |
| postcode | String | Sort Key |
| borough | String | - |
| noiseLevel | String | - |
| buyerScore | String | - |
| notes | String | - |
| timestamp | String (ISO) | - |
| city | String | - |

- **Billing:** PAY_PER_REQUEST (no provisioned capacity)
- **Region:** eu-west-2

### Table: `london-flight-map-signups`

Self-service signup audit log. Partition key `email` (one signup per email; duplicates return 409). Stores `keyId` for revocation and `createdAt` for analytics — the handler logs keyIds, never raw emails. PITR enabled (35 days): this table holds the only mapping between an issued API key and the requesting email.

### Table: `london-flight-map-noise-raster`

DEFRA Lden raster samples, partition key `postcode`. Populated offline by `scripts/load_defra_raster.py` (samples the DEFRA GeoTIFF at every UK postcode centroid); the score Lambda reads it when populated and falls back to Haversine when empty. PITR enabled — a loader re-run costs ~6h of compute, roll-back is cheaper.

### Table: `london-flight-map-postcodes`

ONS NSPL postcode index, partition key `postcode` (spaces stripped, uppercased — the same key format as the noise-raster table, so one normalisation serves both). Populated offline by `scripts/load_nspl.py` from `data/nspl.csv` (2,699,393 positioned rows; ~40 min, ~£1.50 of write units, ~£0.18/month storage with PITR). Attributes: `lat`/`lon` centroid, `lad` (ONS district code, every row), `b` (canonical borough name, only on the 33 London districts), `rgn` (England-only), `dt` (presence = terminated), `q` (positional quality, omitted when building-level). Absence is meaningful, so the common case is the cheapest item.

The score Lambda reads it first and falls back to postcodes.io on a miss, an unloaded table or an error — so behaviour is identical to before until data lands, then upgrades silently with no second deploy.

All four tables: PAY_PER_REQUEST billing, eu-west-2.

---

## IAM Security

### Deployment User: `flightmap-dev`
- Managed policy: `FlightMapDeployPolicy` (v6)
- Scoped to `london-flight-map-*` resources only
- Permissions: CloudFormation, S3, Lambda, API Gateway, IAM roles, Bedrock, CloudFront, DynamoDB, CloudWatch

### Lambda Execution Roles
- Each Lambda has its own least-privilege role (created by SAM)
- Bedrock Lambda roles: `bedrock:InvokeModel` on `amazon.nova-*` models only
- Favourites Lambda: DynamoDB CRUD on `london-flight-map-favourites` table only

---

## Mobile / Native Apps (Wave 13)

Sky Score has three install paths sharing the same `index.html`:

1. **Web** at <https://skyscore.co.uk/> (no install)
2. **PWA** via web manifest + service worker (Add to Home Screen on any modern browser)
3. **Native iOS / Android** via Capacitor wrapper at `mobile/`. iOS built by Codemagic in cloud Mac (no local Mac available); Android built locally via Android Studio + gradle on Windows. Distributed via App Store + Play Store. Mirrors the Noor app's proven workflow.

### Native-only features

Feature-detected via `window.Capacitor.isNativePlatform()`:
- **"Score where I am"** button — uses native GPS via `@capacitor/geolocation`, reverse-geocodes via api.postcodes.io, triggers existing search flow. This is the App Store Section 4.2 "Minimum Functionality" defence.
- **Native share sheet** via `@capacitor/share` (exposed as `window.shareScore` for the result panel)
- **Native splash + status bar** styled to match the app's light theme

### Layout

```
mobile/
  capacitor.config.ts           # appId uk.co.skyscore.app, splash + status bar
  package.json                  # isolated; @capacitor/* + 5 plugins
  scripts/copy-web.mjs          # assembles mobile/www/ from parent web app
  assets/                       # 5 SVG sources (logo, foreground, background, splash, splash-dark)
  CODEMAGIC_SETUP.md            # one-off dashboard config walkthrough
  STORE_LISTINGS.md             # paste-ready App Store + Play Store copy
  APPLE_REVIEW_NOTES.md         # Section 4.2 review notes
  PRIVACY_POLICY.md             # GDPR-compliant, mirrors privacy.html
  RELEASE_CHECKLIST.md          # 9-step pre-release runbook
  DEEP_LINKING.md               # iOS Universal Links + Android App Links setup
  LAUNCH_BLOG_POST.md           # announcement post draft + social excerpts

codemagic.yaml                  # at repo root; ios-workflow only (Android is built locally)
.well-known/                    # apple-app-site-association + assetlinks.json (deep-link stubs)
manifest.webmanifest            # PWA manifest
sw.js                           # service worker (network-first shell, cache-first static)
icons/                          # PWA icons (full-bleed + maskable SVGs)
privacy.html                    # hosted at /privacy for store-listing forms
```

### Update cadence

- **Web** changes (CSS, JS, copy): deploy to S3 + CloudFront, instant
- **Native binaries**: trigger Codemagic build → store review (~2-3 days Apple, ~1 day Google). Plan binary releases every 2-4 weeks; more often than that isn't worth the review-cycle cost
- The `mobile/` Capacitor wrapper consumes the same `index.html` the web app serves — no separate codebase

## Deployment

### Prerequisites
- AWS CLI configured with `flightmap` profile
- AWS SAM CLI installed

### Deploy Backend
```bash
cd backend
rm -rf .aws-sam
AWS_PROFILE=flightmap sam build
AWS_PROFILE=flightmap sam deploy
```

### Deploy Frontend
```bash
AWS_PROFILE=flightmap aws s3 cp index.html s3://london-flight-map-frontend/index.html --content-type "text/html" --region eu-west-2
AWS_PROFILE=flightmap aws cloudfront create-invalidation --distribution-id EGSSPJKLFL33M --paths "/*"
```

---

## API Endpoints

**Base URL:** `https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod`

An `api.skyscore.co.uk` custom domain was configured on the AWS side 2026-07-23; it serves once the Cloudflare `CNAME api` record lands. The raw execute-api URL keeps working regardless.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/score` | GET | B2B single score lookup (API-key gated) |
| `/v1/score/batch` | POST | B2B bulk scoring, up to 100 queries per call (API-key gated) |
| `/v1/regions` | GET | Coverage metadata for the B2B API |
| `/v1/signup` | POST | Self-service API-key issuance (throttled 1 RPS) |
| `/favourites` | GET/POST/DELETE | Save/load/delete favourites (X-Device-Token auth) |
| `/sold-prices` | GET | Land Registry sold prices |
| `/epc` | GET | EPC energy ratings (MHCLG) |
| `/transport` | GET | TfL nearest stations + line status |
| `/nhs` | GET | Nearby NHS services (OSM Overpass) |

The former AI endpoints (`/chat`, `/multi-agent`, `/analyze-image`, `/analyze-document`, `/report`) were removed with the dormant Bedrock Lambdas and live in git history only.

---

## File Structure

```
Sky Score/
|-- index.html # Frontend SPA (~8,200 lines)
|-- pricing.html # /pricing — pilot + tier ladder (added 2026-07-23)
|-- privacy.html # /privacy — privacy policy
|-- api/index.html # /api/ — B2B landing page
|-- score-demo/ # B2B API tester + OpenAPI spec + Swagger UI
|-- prototype/index.html # Sky Score Radar (Three.js 3D visualisation)
|-- HACKATHON_SUBMISSION.md # Devpost submission text
|-- PROJECT_DOCUMENTATION.md # This file
|-- AUDIT_REPORT.md # Code audit findings
|-- CLAUDE.md # Claude Code project config
|-- LICENSE # MIT License
|-- backend/
    |-- template.yaml # SAM/CloudFormation template (7 functions, 3 tables)
    |-- iam-policy.json # IAM deployment policy (v6)
    |-- tests/ # Maintained suite (handlers + score engine)
    |-- lambdas/
        |-- score/app.py # B2B scoring engine (/v1/score, /v1/score/batch, /v1/regions)
        |-- signup/app.py # Self-service API-key issuance (/v1/signup)
        |-- favourites/app.py # DynamoDB favourites CRUD (X-Device-Token)
        |-- sold_prices/app.py # Land Registry proxy
        |-- epc/app.py # MHCLG EPC proxy
        |-- transport/app.py # TfL API proxy
        |-- nhs/app.py # NHS services via OSM Overpass
|-- tests/ # Per-Lambda handler suites (rewritten 2026-07-24)
|-- mobile/ # Capacitor native wrapper (see Mobile section)
```

---

## Cost Analysis

| Service | Monthly Cost (low traffic) |
|---------|--------------------------|
| S3 + CloudFront | ~$0.05 (free tier covers most) |
| Lambda (7 functions) | ~$0.01 (free tier: 1M requests) |
| API Gateway | ~$0.01 (free tier: 1M calls) |
| DynamoDB (3 tables) | ~$0.01 (PAY_PER_REQUEST, minimal reads/writes; + ~$0.20/GB-month PITR backup on tiny tables) |
| Bedrock | $0.00 (no active surface invokes Bedrock) |
| **Total** | **< $1/month at low traffic** |

---

## Product capabilities (current state)

1. **Productised B2B API**, `/v1/score`, `/v1/score/batch`, `/v1/regions` with API-key auth and a published OpenAPI 3.0 spec (self-hosted Swagger UI). Free tier (1000/month) capped via API Gateway UsagePlan; self-service signup at `/v1/signup`.
2. **Methodologically defensible**, every threshold and weight in the score is anchored to a published source (DEFRA Strategic Noise Mapping, WHO night-noise guidelines, Ofsted distribution, ONS crime medians, TfL PTAL, HM Land Registry HPI). See `METHODOLOGY.md`.
3. **Multi-city**, London (33 boroughs) + NYC (5 boroughs, ~182 ZIPs auto-detected). Postcode-level resolution for both.
4. **DEFRA raster resolution (v3.1)**, score Lambda samples DynamoDB Lden values per postcode, falling back to Haversine then borough averages. Loader in `scripts/load_defra_raster.py`.
5. **Live and deployed**, fully serverless on AWS: S3 + CloudFront frontend, 7 Lambda functions behind API Gateway, 4 DynamoDB tables.
6. **Halal-finance-aware**, affordability model makes no riba assumptions; cohort-relative price-to-income with no mortgage-rate dependency. Aimed at Sharia-compliant home-finance providers as one of the target B2B segments.
7. **Free, accessible consumer site**, no sign-up, no paywall — the marketing engine for the API.
8. **Three install paths**, web, PWA, and native iOS (App Store v1.0.21 live) / Android (pending) from a single `index.html`.

(The removed Nova AI capabilities — chat, multimodal analysis, multi-agent reports — are documented under "Amazon Nova Integration — DORMANT" above.)

## Origin

Built for the Amazon Nova AI Hackathon (March 2026). Won $200 AWS credits in the blog-post category. Productised post-hackathon as a B2B API + free public consumer site. See `ROADMAP.md` for the live tracks and `CHANGELOG.md` for incremental ships.

---

## Known Limitations

- Consumer site UI: NYC search accepts borough names (e.g. "Manhattan") and neighbourhood names (e.g. "Astoria", "Williamsburg") but not raw 5-digit ZIPs, typing `10001` falls through to postcodes.io and returns "NOT FOUND". The B2B `/v1/score` API *does* accept ZIPs; consumer-site parity is an open product item.
- EPC API requires registration + bearer token (post-2026-05-30 service migration; see `CLAUDE.md` for token rotation hygiene)
- DEFRA WMS tiles can be slow to load on first request
- Property listing links open external sites (no public APIs available)
- Favourites endpoint uses an opaque `X-Device-Token` UUID (capability-based, not identity-based; audit C3 mitigation). Anyone learning a token can use it; full identity auth is on the post-launch roadmap.
- NYC ZIP coverage is residential / general-use only (~182 ZIPs); non-NYC US ZIPs return a structured 404.
- Live aircraft tracking is currently disabled pending OpenSky licensing — see `LICENSING.md` "Removed sources".
