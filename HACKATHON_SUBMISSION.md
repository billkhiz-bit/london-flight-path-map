# Amazon Nova AI Hackathon - Submission

## Project Title
**London Flight Path Map - AI-Powered Property Intelligence for Aircraft Noise**

## Tagline
Helping London property buyers avoid hidden aircraft noise using Amazon Nova, live government data, and interactive mapping.

---

## Description

### The Problem

Every year, thousands of London home buyers unknowingly purchase properties under flight paths. Aircraft noise is the single most common complaint from new homeowners in London - yet no existing property platform shows flight path data, noise contours, or helps buyers assess the true noise impact at a specific address. Rightmove, Zoopla, and OnTheMarket show zero noise data. Buyers only discover the problem after they've moved in.

### The Solution

London Flight Path Map is a free, AI-powered property intelligence tool that combines Amazon Nova 2 Lite with five live government data sources to give buyers a complete picture of any London location before they commit.

Users can search by **postcode** (SW11 1AA), **area** (Chelsea, Twickenham - 130+ neighbourhoods), **partial postcode** (TW3, SW1), or **borough** (Hounslow) - or simply click the map - to instantly see:

- **Aircraft noise analysis** - flight paths from 5 airports (Heathrow, Gatwick, City, Stansted, Luton), helicopter routes, estimated plane altitudes, and distance to the nearest flight path
- **Official DEFRA noise contours** - government noise maps overlaid directly on the interactive map via WMS (road noise and aircraft noise in decibels)
- **AI Property Advisor** - powered by Amazon Nova 2 Lite via Bedrock, trained on borough-level data covering noise, prices, crime, schools, transport, and flood risk. Users can ask natural language questions like *"Where's the quietest area with good schools under 500K?"* and get specific, data-backed recommendations
- **Postcode-specific Buyer Value Score** - a composite 1-10 score that uses the actual noise level at your searched location (not the borough average), combined with borough affordability and growth data. Weighted: Quiet Skies (40%), Affordability (35%), Growth (25%)
- **Crime statistics** - curated borough-level crime rates per 1,000 residents based on Met Police data, with London-average comparison
- **Nearest train stations** - live TfL API data showing closest tube/rail stations with distances, lines served, and real-time service status
- **Energy Performance Certificates** - EPC band distribution from the official UK government register, showing average energy ratings for properties in any postcode
- **Sold prices** - recent Land Registry Price Paid Data showing what properties actually sold for nearby
- **Healthcare facilities** - curated GP surgery and hospital information per borough
- **Schools** - Ofsted-based ratings with specific school highlights per borough

### How Amazon Nova Powers This

Amazon Nova 2 Lite serves as the core AI engine through an **AI Property Advisor chatbot** accessible from any page. Unlike generic chatbots, Nova is provided with structured data for all 29 London boroughs (noise levels, average prices, growth rates, crime rates per 1,000 residents, school ratings, flood risk, air quality, and transport connections). This enables Nova to:

- **Compare boroughs** by multiple criteria simultaneously
- **Recommend areas** based on complex user requirements (budget + noise tolerance + school quality + commute needs)
- **Explain trade-offs** honestly (e.g. "Lewisham is quieter but has a longer commute than Lambeth")
- **Quote specific data** rather than giving generic advice

The chatbot is invoked via AWS Lambda through API Gateway, calling Bedrock's InvokeModel API with the cross-region inference profile `us.amazon.nova-2-lite-v1:0`. Nova's fast inference and strong instruction-following make it ideal for this real-time advisory use case where responses need to be both accurate and concise.

### Architecture

The entire backend is built on AWS using the Serverless Application Model (SAM):

- **Amazon Bedrock (Nova 2 Lite)** - AI chatbot for property advice
- **Amazon CloudFront** - global CDN serving the frontend with HTTPS
- **Amazon S3** - static website hosting for the single-page application
- **5 AWS Lambda functions** (Python 3.11) - chat, transport, EPC, sold prices, NHS
- **Amazon API Gateway** - REST API with CORS, public access
- **AWS CloudFormation** - infrastructure as code via SAM template
- **AWS IAM** - scoped least-privilege policies for deployment and runtime

The frontend is a self-contained single-page application using D3.js v7 for SVG-based interactive mapping with real-time DEFRA WMS tile overlays. No frameworks, no build step - just a single HTML file that connects to live government APIs through the Lambda proxy layer.

### Community Impact

This tool addresses a genuine gap in the UK property market. Aircraft noise affects property values by 10-20% in severely impacted areas, yet this information is almost impossible for buyers to find in one place. By making this data free and accessible, it helps:

- **First-time buyers** avoid costly mistakes
- **Families** find quiet areas with good schools within budget
- **Investors** identify undervalued boroughs with growth potential
- **Renters** check noise before signing a lease

It combines data that would otherwise require visiting 8+ separate government websites (DEFRA, Land Registry, Met Police, TfL, EPC Register, NHS, Ofsted).

### What Makes This Different

1. **Real data, not estimates** - DEFRA noise contours, Met Police crime stats, Land Registry sold prices, TfL live status, EPC certificates - all from official government sources
2. **AI that knows London** - Nova isn't just answering generically; it has structured borough data and gives specific, comparable recommendations
3. **Postcode-specific scoring** - the Buyer Value Score adapts to your exact location's noise level, not just the borough average
4. **Search by anything** - postcodes, partial postcodes, 130+ area names, or borough names
5. **No sign-up, no paywall** - completely free to use
6. **Production-ready** - deployed and live on AWS CloudFront

---

## Built With
- Amazon Bedrock (Nova 2 Lite)
- Amazon CloudFront
- Amazon S3
- AWS Lambda
- Amazon API Gateway
- AWS SAM / CloudFormation
- AWS IAM
- Python 3.11
- D3.js v7
- JavaScript (vanilla)
- HTML/CSS

## Data Sources
- DEFRA Strategic Noise Maps (WMS)
- Met Police crime statistics (curated)
- TfL Unified API (live)
- EPC Open Data Communities API (live)
- HM Land Registry Price Paid Data (live via Lambda)
- NHS/healthcare data (curated)
- Postcodes.io (geolocation + autocomplete)

## Links
- **Live Demo**: https://d1oe4ftwutjpf.cloudfront.net (AWS S3 + CloudFront)
- **Code Repository**: https://github.com/billkhiz-bit/london-flight-path-map
- **Video Demo**: [YouTube link - to be added]
- **GitHub Pages Mirror**: https://billkhiz-bit.github.io/london-flight-path-map

## Category
Freestyle

## Hashtags
#AmazonNova #AWS #PropertyTech #London #AI
