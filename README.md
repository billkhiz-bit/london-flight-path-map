# Flight Path Intelligence

**AI-Powered Property Analysis for Aircraft Noise — London & New York**

> Multi-city property intelligence combining Amazon Nova Pro multimodal AI, Nova Lite chat, neighbourhood-level scoring across 290+ areas, live government data, and interactive D3.js mapping.

**[Live Demo](https://d1oe4ftwutjpf.cloudfront.net)** | Built for the Amazon Nova AI Hackathon

---

## The Problem

Every year, thousands of home buyers unknowingly purchase properties under flight paths. Aircraft noise is the single most common complaint from new homeowners — yet no property platform shows flight path data or noise contours. Rightmove, Zoopla, Zillow, and StreetEasy show zero noise data.

## The Solution

A free tool that combines **Amazon Nova AI** with **10+ live data sources** to give buyers a complete noise and property picture for any location in London or New York City.

- **London**: 33 boroughs, 5 airports, 5 heliports, ~143 neighbourhoods
- **New York**: 5 boroughs, 4 airports, ~151 neighbourhoods
- **290+ neighbourhoods** with individually computed scores

---

## Features

### Search & Analysis
- Search by postcode/ZIP, neighbourhood name, or borough
- Instant noise assessment: distance to airports, flight paths, estimated plane altitude
- Official government noise contour overlays (DEFRA WMS / BTS ArcGIS)

### Amazon Nova AI — 6 Modes
1. **Multi-turn chat** (Nova Lite) — conversational property advisor with context
2. **Auto-insights** (Nova Lite) — instant AI summary for every search
3. **Complex reasoning** (Nova Pro) — multi-criteria comparisons, "best area for..." queries
4. **Photo analysis** (Nova Pro multimodal) — upload listing photos for condition/glazing analysis
5. **Document analysis** (Nova Pro multimodal) — upload EPC certificates or survey reports
6. **Report generation** (Nova Pro) — 7-section property intelligence reports

### Neighbourhood Scoring Engine
Each of 290+ neighbourhoods gets a unique score computed from:
- **Quiet Skies** — actual distance to airports and flight paths (Haversine)
- **Affordability** — neighbourhood-specific median prices
- **Growth** — annual price trends
- **Liveability** — schools + crime safety + transport + healthcare

5 buyer personas (Balanced, Family, Investor, First-Time, Quiet Life) dynamically reweight all scores.

### Data Layers
| Layer | London | NYC |
|-------|--------|-----|
| Aircraft Noise | DEFRA WMS | BTS/DOT ArcGIS |
| Road Noise | DEFRA WMS | DOT ArcGIS |
| Flood Risk | Environment Agency | FEMA NFHL |
| Air Quality | DEFRA AQMA | EPA Nonattainment |
| Transport | 18 hubs | 16 hubs |

---

## Architecture

10 AWS services, fully serverless:

```
CloudFront → S3 (frontend)
                ↓
API Gateway → Lambda (x9) → Bedrock (Nova Lite + Pro)
                           → DynamoDB (favourites)
```

| Service | Role |
|---------|------|
| Amazon Bedrock | Nova 2 Lite + Nova Pro |
| AWS Lambda (x9) | Chat, image/doc analysis, reports, favourites, data proxies |
| Amazon API Gateway | REST API with CORS |
| Amazon DynamoDB | Favourites storage |
| Amazon S3 | Static hosting |
| Amazon CloudFront | CDN + HTTPS |
| AWS CloudFormation/SAM | Infrastructure as code |
| AWS IAM | Least-privilege policies |
| Amazon CloudWatch | Logging |
| AWS STS | Cross-region access |

---

## Tech Stack

- **Frontend**: Single HTML file (~3,900 lines), D3.js v7, vanilla JS — no frameworks, no build step
- **Backend**: Python 3.11 Lambdas, SAM template
- **AI**: Amazon Bedrock — Nova 2 Lite (`us.amazon.nova-2-lite-v1:0`) + Nova Pro (`us.amazon.nova-pro-v1:0`)
- **Data**: DEFRA, BTS, FEMA, EPA, TfL, Land Registry, Postcodes.io, Met Police, NYPD CompStat

## Deployment

```bash
# Frontend
AWS_PROFILE=flightmap aws s3 cp index.html s3://london-flight-map-frontend/index.html --content-type "text/html" --region eu-west-2
AWS_PROFILE=flightmap aws cloudfront create-invalidation --distribution-id EGSSPJKLFL33M --paths "/*"

# Backend
cd backend && AWS_PROFILE=flightmap sam build && AWS_PROFILE=flightmap sam deploy
```

## License

MIT

---

Built for the **Amazon Nova AI Hackathon** (March 2026)
