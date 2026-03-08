# London Flight Path Map - AWS Migration Build Plan

## Current State (v8 - Static Client-Side App)

### What's Built
- Single `index.html` (~1940 lines) - D3.js interactive map
- 29 London boroughs with noise, crime, school, flood, AQ, transport data
- 12 flight paths with animated dots (arrivals/departures)
- DEFRA WMS noise contours (official government data)
- Live aircraft tracking via OpenSky Network API (toggleable)
- Clickable flight details with Flightradar24/FlightAware links
- Postcode search with autocomplete (postcodes.io)
- Crime data via data.police.uk API (live, per-postcode)
- Flood risk + air quality WMS overlays (Environment Agency, DEFRA)
- Property listing links (Rightmove, Zoopla, OnTheMarket)
- Land Registry sold prices (with CORS fallback)
- Buyer Value Score: Quiet Skies (40%) + Affordability (35%) + Growth (25%)
- Hosted on GitHub Pages: billkhiz-bit.github.io/london-flight-path-map
- MIT Licensed

### What's Missing
- No backend (CORS blocks some APIs)
- No AI chatbot (can't expose API key client-side)
- No user accounts or saved searches
- No PDF report generation
- No TfL transport data (live)
- No EPC energy ratings
- Static property prices (not live)

---

## Target State (v9 - AWS Full Stack)

### Architecture

```
User (Browser)
  |
CloudFront (CDN)
  |
S3 (index.html + static assets)
  |
API Gateway (REST API)
  |-- POST /chat          -> Lambda -> Bedrock (Claude) -> AI area advisor
  |-- GET  /sold-prices    -> Lambda -> Land Registry API -> DynamoDB cache
  |-- GET  /epc            -> Lambda -> EPC API -> DynamoDB cache
  |-- GET  /transport      -> Lambda -> TfL API -> response
  |-- GET  /crime-summary  -> Lambda -> data.police.uk -> DynamoDB cache
  |-- POST /save-search    -> Lambda -> DynamoDB (user data)
  |-- GET  /my-searches    -> Lambda -> DynamoDB (user data)
  |-- POST /generate-report -> Lambda -> PDF gen -> S3 signed URL
  |-- POST /compare        -> Lambda -> Bedrock -> AI comparison
  |
Cognito (user authentication)
EventBridge (nightly cache refresh) -> Lambda -> DynamoDB
SES (weekly digest emails to users with saved searches)
```

### AWS Services (8 total - matches LedgerAgent depth)

| # | Service | Purpose | Free Tier |
|---|---------|---------|-----------|
| 1 | **S3** | Host frontend + store generated PDF reports | 5GB storage |
| 2 | **CloudFront** | CDN for fast global delivery | 1TB/mo transfer |
| 3 | **Lambda** | All backend logic (7+ functions) | 1M requests/mo |
| 4 | **API Gateway** | REST API endpoints | 1M calls/mo |
| 5 | **Bedrock (Claude)** | AI chatbot + comparison reports | Pay per token |
| 6 | **DynamoDB** | Cached API data + user saved searches | 25GB free |
| 7 | **Cognito** | User authentication | 50K MAU free |
| 8 | **EventBridge** | Schedule nightly data refresh | Free |
| +  | **SES** | Weekly email digests (future) | 62K emails/mo free |

---

## Build Phases

### Phase 1: Backend Foundation (Lambda + API Gateway + S3/CloudFront)
- [ ] Set up AWS SAM/CDK project structure
- [ ] Create S3 bucket for frontend hosting
- [ ] Configure CloudFront distribution
- [ ] Deploy index.html to S3
- [ ] Create API Gateway REST API
- [ ] Create Lambda function: `/sold-prices` (proxy Land Registry API, bypass CORS)
- [ ] Create Lambda function: `/epc` (proxy EPC API)
- [ ] Create Lambda function: `/transport` (proxy TfL API)
- [ ] Update frontend to call API Gateway instead of direct APIs
- [ ] Test end-to-end

### Phase 2: AI Chatbot (Bedrock)
- [ ] Create Lambda function: `/chat`
- [ ] Configure Bedrock access for Claude model
- [ ] Build system prompt with all borough data as context
- [ ] Support natural language queries:
  - "Where's quiet with good schools under 500K?"
  - "Is Hounslow safe for families?"
  - "Compare Richmond vs Kingston"
- [ ] Add floating chat UI to frontend
- [ ] Add `/compare` endpoint for side-by-side AI analysis

### Phase 3: User Accounts (Cognito + DynamoDB)
- [ ] Set up Cognito User Pool
- [ ] Add login/signup UI to frontend
- [ ] Create DynamoDB table: `SavedSearches` (userId, postcode, timestamp, notes)
- [ ] Create Lambda: `/save-search` (POST)
- [ ] Create Lambda: `/my-searches` (GET)
- [ ] Add "Save this area" button to postcode analysis
- [ ] Add "My Saved Areas" panel in sidebar

### Phase 4: Data Caching (DynamoDB + EventBridge)
- [ ] Create DynamoDB table: `CachedData` (dataType, key, value, ttl)
- [ ] Cache Land Registry sold prices (TTL: 7 days)
- [ ] Cache EPC data per postcode (TTL: 30 days)
- [ ] Cache crime data per borough (TTL: 1 day)
- [ ] Create EventBridge rule: nightly at 2am
- [ ] Create Lambda: `refreshCache` (pre-fetch popular postcodes)

### Phase 5: PDF Reports + Email (S3 + SES)
- [ ] Create Lambda: `/generate-report`
- [ ] Generate branded PDF with: map screenshot, scores, crime, schools, transport, AI summary
- [ ] Upload PDF to S3, return signed URL (expires 24h)
- [ ] Add "Download Report" button to frontend
- [ ] Set up SES for verified sending domain
- [ ] Create weekly digest Lambda (EventBridge scheduled)
- [ ] Email users: changes in crime/prices for their saved postcodes

### Phase 6: New Data Layers
- [ ] TfL Integration:
  - Nearest tube/rail station to postcode
  - Live line status (disruptions)
  - Journey time to central London
- [ ] EPC Integration:
  - Average energy rating per postcode
  - Band distribution (A-G)
  - Estimated energy costs
- [ ] Postcode Comparison:
  - Side-by-side UI (split sidebar)
  - AI-powered comparison narrative via Bedrock

---

## Lambda Functions Summary

| Function | Trigger | Input | Output |
|----------|---------|-------|--------|
| `getSoldPrices` | API GW GET | postcode | Land Registry transactions |
| `getEpcData` | API GW GET | postcode | EPC ratings for area |
| `getTransport` | API GW GET | lat, lon | Nearest stations + live status |
| `getCrimeSummary` | API GW GET | lat, lon | Crime breakdown (cached) |
| `chat` | API GW POST | message, context | Claude AI response |
| `compareAreas` | API GW POST | postcode1, postcode2 | AI comparison report |
| `saveSearch` | API GW POST | userId, postcode, notes | confirmation |
| `getMySearches` | API GW GET | userId | saved postcodes list |
| `generateReport` | API GW POST | postcode | S3 signed URL to PDF |
| `refreshCache` | EventBridge | (scheduled) | updated DynamoDB entries |
| `sendDigest` | EventBridge | (weekly) | SES emails sent |

---

## DynamoDB Tables

### SavedSearches
```
PK: userId (String)
SK: postcode#timestamp (String)
Attributes: postcode, lat, lon, notes, createdAt
GSI: postcode-index (for aggregating popular searches)
```

### CachedData
```
PK: dataType (String) - "sold-prices", "epc", "crime", "transport"
SK: key (String) - postcode or lat#lon
Attributes: data (Map), cachedAt (Number), ttl (Number)
TTL: enabled on ttl attribute
```

---

## Bedrock Chat System Prompt (Draft)

```
You are an AI property advisor for London. You have access to the following data
for 29 London boroughs: noise impact levels, average property prices, price growth
trends, crime rates, school ratings, flood risk, air quality, and transport links.

When answering questions:
- Be specific with data (quote prices, scores, ratings)
- Be honest about limitations (borough-level data, not street-level)
- Reference the Buyer Value Score methodology when relevant
- Suggest 2-3 areas that match the user's criteria
- Mention trade-offs (e.g., "quieter but longer commute")
- Never guarantee property advice - remind users to do their own research

Borough data:
[INJECT FULL BOROUGH_DATA AND BOROUGH_EXTRA OBJECTS HERE]
```

---

## Cost Estimate (Demo/Hackathon with ~100 users)

| Service | Monthly Cost |
|---------|-------------|
| S3 | $0.00 (free tier) |
| CloudFront | $0.00 (free tier) |
| Lambda | $0.00 (free tier) |
| API Gateway | $0.00 (free tier) |
| DynamoDB | $0.00 (free tier) |
| Cognito | $0.00 (free tier) |
| EventBridge | $0.00 (free tier) |
| Bedrock (Claude) | ~$1-3 (token usage) |
| **Total** | **~$1-3/month** |

---

## Hackathon Pitch (30 seconds)

"Every year 100,000 Londoners buy a home without knowing a flight path is directly overhead. We built an AI-powered property intelligence platform on AWS that combines official government noise data, live aircraft tracking, crime statistics, and a Claude-powered advisor - so buyers can make informed decisions before the biggest purchase of their lives."

---

## GitHub Repository

- **Repo**: github.com/billkhiz-bit/london-flight-path-map
- **Live (current)**: billkhiz-bit.github.io/london-flight-path-map
- **Live (AWS)**: TBD (CloudFront URL or custom domain)

---

## Version History

| Version | Description |
|---------|-------------|
| v1-v8 | Static client-side app (see PROJECT.md for full history) |
| v9 | AWS migration: S3/CloudFront hosting, Lambda backend, API Gateway |
| v10 | AI chatbot via Bedrock (Claude) |
| v11 | User accounts (Cognito) + saved searches (DynamoDB) |
| v12 | Data caching (DynamoDB + EventBridge) |
| v13 | PDF reports (Lambda + S3) + email digests (SES) |
| v14 | New data layers: TfL, EPC, postcode comparison |
