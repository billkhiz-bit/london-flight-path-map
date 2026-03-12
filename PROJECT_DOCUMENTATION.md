# Sky Score - Complete Project Documentation

## Project Overview

**Sky Score** is an AI-powered property intelligence tool that helps property buyers in London and New York assess aircraft noise, crime, schools, transport, and more before purchasing. It combines Amazon Nova AI (Lite and Pro) with live government data sources and interactive D3.js mapping across 290+ individually scored neighbourhoods.

**Live URL:** https://d1oe4ftwutjpf.cloudfront.net
**GitHub:** https://github.com/billkhiz-bit/london-flight-path-map
**Category:** Amazon Nova AI Hackathon - Freestyle

---

## Architecture

### AWS Services Used (10 services)

| Service | Purpose | Region |
|---------|---------|--------|
| **Amazon Bedrock** | AI engine - Nova 2 Lite (chat) + Nova Pro (reasoning, multimodal) | us-east-1 |
| **AWS Lambda** | 10 serverless functions (Python 3.11) | eu-west-2 |
| **Amazon API Gateway** | REST API with CORS | eu-west-2 |
| **Amazon S3** | Static website hosting | eu-west-2 |
| **Amazon CloudFront** | Global CDN with HTTPS | Global |
| **Amazon DynamoDB** | User favourites storage | eu-west-2 |
| **AWS SAM/CloudFormation** | Infrastructure as code | eu-west-2 |
| **AWS IAM** | Least-privilege access control | Global |
| **Amazon CloudWatch** | Logging and monitoring | eu-west-2 |
| **AWS STS** | Cross-region model access | us-east-1 |

### Data Sources (10+ live APIs)

**London:**
1. **DEFRA Strategic Noise Maps** - Official UK government aircraft and road noise contours (WMS)
2. **Met Police Crime Statistics** - Curated borough-level crime rates
3. **TfL Unified API** - Live nearest stations, line status, distances
4. **EPC Open Data Communities** - Energy Performance Certificates by postcode
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

## Amazon Nova Integration (6 Modes + Multi-Agent)

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

## Lambda Functions (10 total)

### 1. ChatFunction (`/chat` POST)
- **File:** `backend/lambdas/chat/app.py`
- **Purpose:** AI chatbot with multi-turn conversation and auto-insights
- **Models:** Nova 2 Lite (simple) + Nova Pro (complex)
- **Modes:** `chat` (conversation) and `insight` (auto-generation)

### 2. MultiAgentFunction (`/multi-agent` POST)
- **File:** `backend/lambdas/multi_agent/app.py`
- **Purpose:** Multi-agent orchestration for complex queries
- **Models:** Nova 2 Lite (orchestrator + 3 agents) + Nova Pro (synthesiser)
- **Timeout:** 90s (runs 4 Bedrock calls in parallel + synthesis)

### 3. AnalyzeImageFunction (`/analyze-image` POST)
- **File:** `backend/lambdas/analyze_image/app.py`
- **Purpose:** Multimodal property photo analysis
- **Model:** Nova Pro (image understanding)

### 4. AnalyzeDocumentFunction (`/analyze-document` POST)
- **File:** `backend/lambdas/analyze_document/app.py`
- **Purpose:** EPC certificate and survey report analysis
- **Model:** Nova Pro (document understanding)

### 5. ReportFunction (`/report` POST)
- **File:** `backend/lambdas/report/app.py`
- **Purpose:** Comprehensive AI-generated property intelligence reports
- **Model:** Nova Pro
- **Timeout:** 90s

### 6. FavouritesFunction (`/favourites` GET/POST/DELETE)
- **File:** `backend/lambdas/favourites/app.py`
- **Purpose:** Save/load/delete favourite locations
- **Storage:** DynamoDB table `london-flight-map-favourites`

### 7. SoldPricesFunction (`/sold-prices` GET)
- **File:** `backend/lambdas/sold_prices/app.py`
- **Purpose:** Land Registry Price Paid Data proxy (CORS)

### 8. EpcFunction (`/epc` GET)
- **File:** `backend/lambdas/epc/app.py`
- **Purpose:** EPC energy ratings from Open Data Communities

### 9. TransportFunction (`/transport` GET)
- **File:** `backend/lambdas/transport/app.py`
- **Purpose:** TfL nearest stations and live line status

### 10. NhsFunction (`/nhs` GET)
- **File:** `backend/lambdas/nhs/app.py`
- **Purpose:** NHS GP surgery data

---

## Frontend Architecture

### Single-Page Application
- **File:** `index.html` (~3,870 lines)
- **Framework:** None (vanilla JavaScript)
- **Mapping:** D3.js v7 with SVG-based interactive rendering
- **Build step:** None required
- **Styling:** Custom CSS with CSS variables for theming

### Key Frontend Features

#### Multi-City Support (London + New York)
- City selector toggles between London and New York
- Each city has its own airports, flight paths, borough/neighbourhood data, and GeoJSON
- London: 33 boroughs, 5 airports, 5 heliports, ~143 neighbourhoods
- New York: 5 boroughs, 4 airports, ~151 neighbourhoods

#### Search System
- **Full postcode** (SW11 1AA) - exact location analysis
- **Partial postcode/outcode** (TW3, SW1) - area-level analysis via outcodes API
- **Area/neighbourhood** (Chelsea, Twickenham, Astoria) - 290+ areas mapped to postcodes
- **Borough name** (Hounslow, Queens) - borough-level view
- **Autocomplete** with debounced API calls and keyboard navigation

#### Postcode-Specific Buyer Value Score (1-10)
Each of 290+ neighbourhoods gets a unique score computed from four factors:
1. **Quiet Skies** - actual geographic distance (Haversine formula) to airports and flight path corridors
2. **Affordability** - neighbourhood-specific median prices (not borough averages)
3. **Growth** - annual price trend percentage
4. **Liveability** - composite of schools (35%), crime safety (30%), transport access (25%), and healthcare (10%)

**Five Buyer Personas** (Balanced, Family, Investor, First-Time, Quiet Life) dynamically reweight all four factors and instantly re-rank all 290+ neighbourhoods.

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

#### AI Features (Frontend)
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

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/chat` | POST | AI chatbot (Lite + Pro routing) |
| `/multi-agent` | POST | Multi-agent orchestration (complex queries) |
| `/analyze-image` | POST | Property photo analysis (Pro multimodal) |
| `/analyze-document` | POST | EPC/survey analysis (Pro multimodal) |
| `/report` | POST | AI report generation (Pro) |
| `/favourites` | GET/POST/DELETE | Save/load/delete favourites (DynamoDB) |
| `/sold-prices` | GET | Land Registry sold prices |
| `/epc` | GET | EPC energy ratings |
| `/transport` | GET | TfL nearest stations |
| `/nhs` | GET | NHS GP surgeries |

---

## File Structure

```
Sky Score/
|-- index.html                     # Frontend SPA (~3,870 lines)
|-- HACKATHON_SUBMISSION.md        # Devpost submission text
|-- PROJECT_DOCUMENTATION.md       # This file
|-- AUDIT_REPORT.md                # Code audit findings
|-- CLAUDE.md                      # Claude Code project config
|-- LICENSE                        # MIT License
|-- backend/
    |-- template.yaml              # SAM/CloudFormation template
    |-- iam-policy.json            # IAM deployment policy (v6)
    |-- lambdas/
        |-- chat/app.py            # AI chatbot (Nova 2 Lite + Pro)
        |-- multi_agent/app.py     # Multi-agent orchestration
        |-- analyze_image/app.py   # Photo analysis (Nova Pro)
        |-- analyze_document/app.py # Document analysis (Nova Pro)
        |-- report/app.py          # AI report generation (Nova Pro)
        |-- favourites/app.py      # DynamoDB favourites CRUD
        |-- sold_prices/app.py     # Land Registry proxy
        |-- epc/app.py             # EPC data proxy
        |-- transport/app.py       # TfL API proxy
        |-- nhs/app.py             # NHS data
```

---

## Cost Analysis

| Service | Monthly Cost (low traffic) |
|---------|--------------------------|
| S3 + CloudFront | ~$0.05 (free tier covers most) |
| Lambda (10 functions) | ~$0.01 (free tier: 1M requests) |
| API Gateway | ~$0.01 (free tier: 1M calls) |
| DynamoDB | ~$0.01 (PAY_PER_REQUEST, minimal reads/writes) |
| Bedrock Nova 2 Lite | ~$0.10 (per 1000 chat messages) |
| Bedrock Nova Pro | ~$0.50 (per 100 complex queries/reports) |
| **Total** | **< $1/month at low traffic** |

---

## Hackathon Strengths

1. **Deep Nova integration** - 6 distinct AI modes (chat, insight, photo analysis, document analysis, report generation, complex reasoning) + multi-agent orchestration across 2 models (Lite + Pro)
2. **Multimodal AI** - Photo and document analysis using Nova Pro vision capabilities
3. **Multi-agent orchestration** - Orchestrator + 3 specialist agents + synthesiser with parallel execution
4. **Intelligent model routing** - Automatically selects Lite vs Pro based on query complexity
5. **10 AWS services** - Production-grade serverless architecture
6. **Real-world problem** - Aircraft noise is the #1 complaint from new London homeowners
7. **Live and deployed** - Not a localhost demo, fully deployed on CloudFront
8. **10+ live data sources** - Government APIs, not mock data
9. **Multi-city** - London + New York proves global scalability
10. **290+ individually scored neighbourhoods** - Not borough averages
11. **Full stack** - DynamoDB for data persistence, not just a static frontend
12. **Free and accessible** - No sign-up, no paywall

---

## Known Limitations

- NYC search currently works by clicking boroughs (no ZIP code geocoding API integrated yet)
- EPC API requires registration for an API key
- OpenSky Network has rate limits (~10 requests/min for anonymous users)
- DEFRA WMS tiles can be slow to load on first request
- Property listing links open external sites (no public APIs available)
- Nova Pro multimodal document analysis may have variable accuracy on handwritten or low-quality scans
- DynamoDB favourites use device ID (not user authentication) so favourites are device-specific
- Favourites endpoint has no authentication (any client can access any userId)
