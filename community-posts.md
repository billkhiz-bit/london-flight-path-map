# Community Posts

---

## Amazon Nova Group

**Title:** Sky Score - Multi-Agent Property Intelligence Built on Amazon Nova (Hackathon Entry)

**Body:**

Sky Score uses Amazon Nova to solve a problem no property platform addresses: hidden aircraft noise.

Buyers on Rightmove, Zoopla, Zillow, and StreetEasy see zero noise data. Sky Score combines Nova AI with 10+ live government data sources to give buyers a complete noise and property picture across London and New York - for free.

How Nova powers it:
- Multi-agent orchestration - an Orchestrator (Nova Lite) decomposes complex queries and dispatches to 3 specialist agents (Noise Analyst, Property Researcher, Neighbourhood Scorer) running in parallel, then Nova Pro synthesises the results
- Multimodal photo analysis - upload property listing photos for glazing type, condition, and noise insulation assessment via Nova Pro
- Multimodal document analysis - upload EPC certificates or building surveys for AI extraction via Nova Pro
- One-click 7-section Property Intelligence Reports - powered by Nova Pro
- Auto-insights on every search - Nova Lite generates an AI summary for every location, no button press needed
- Smart model routing - Nova Lite handles ~70% of queries cheaply, Nova Pro fires only for complex reasoning and multimodal tasks

290+ individually scored neighbourhoods across 33 London boroughs and 5 NYC boroughs. Five buyer personas instantly re-rank every neighbourhood based on what matters most to each buyer.

Live demo: https://skyscore.co.uk

#AmazonNova

---

## AWS Community Group

**Title:** Sky Score - Full-Stack Serverless Property Intelligence on AWS (Hackathon Entry)

**Body:**

Sky Score is a free AI-powered tool that helps home buyers avoid hidden aircraft noise - a problem no major property platform addresses. It covers London and New York with 290+ individually scored neighbourhoods.

Built entirely on AWS:
- Amazon Bedrock - Nova 2 Lite + Nova Pro for chat, multi-agent orchestration, multimodal analysis, and report generation
- AWS Lambda (x10) - multi-agent orchestrator, chat, image analysis, document analysis, report generation, favourites, and 4 external data proxies (TfL, EPC, Land Registry, NHS)
- Amazon API Gateway - REST API with CORS
- Amazon DynamoDB - favourites storage (PAY_PER_REQUEST)
- Amazon S3 + CloudFront - static hosting with global CDN
- AWS SAM/CloudFormation - entire infrastructure as code
- AWS STS - cross-region Bedrock access

The frontend is a single HTML file (~3,870 lines) using D3.js for interactive mapping - no React, no Leaflet, no build step. It overlays official government noise contours, flight paths, flood risk, and air quality data from DEFRA, BTS, FEMA, and EPA using three different rendering engines (WMS, ArcGIS REST, tile grid).

10+ live government data sources. Five buyer personas. Six Amazon Nova AI modes. Zero sign-up required.

Live demo: https://skyscore.co.uk

#AmazonNova #AWS #Serverless
