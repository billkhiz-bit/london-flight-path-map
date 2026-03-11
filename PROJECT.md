# London Flight Path Analysis - Property Buyer Intelligence Tool

## Overview

A self-contained, browser-based geospatial intelligence tool that helps London property buyers make informed decisions by combining aircraft noise analysis with crime, schools, flood risk, air quality, transport, and property data - all in one interactive map interface.

**No build tools, no backend, no API keys required.** Single HTML file, opens in any browser.

---

## Problem Statement

London property buyers have no single tool that combines flight noise analysis with other liveability factors. Existing platforms (Rightmove, Zoopla) offer basic flood indicators but nothing on aircraft noise - despite it being one of the most common complaints from London homeowners, especially near Heathrow (the UK's busiest airport with 79.2M passengers/year).

This tool fills that gap by layering official government noise data, live flight tracking, crime statistics, school ratings, flood risk, air quality, and property market data into one interactive analysis.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Mapping | D3.js v7 (SVG-based, interactive zoom/pan) |
| Styling | Custom CSS (monochrome editorial design system) |
| Typography | JetBrains Mono + Inter (Google Fonts) |
| GeoJSON | GitHub-hosted UK boundary data (fallback chain) |
| Noise Data | DEFRA WMS (Web Map Service) - official UK government |
| Live Flights | OpenSky Network API (real-time aircraft positions) |
| Crime Data | data.police.uk API (live, per-postcode) |
| Postcodes | postcodes.io API (geocoding + autocomplete) |
| Flood Risk | Environment Agency WMS overlay |
| Air Quality | DEFRA AQMA WMS overlay |
| Sold Prices | HM Land Registry Price Paid Data API |
| Hosting | Static file - no server needed |

All APIs used are **free, public, and require no authentication**.

---

## Features

### Core Features (Always Visible)

1. **Interactive D3.js Map of London**
   - 29 borough boundaries from GeoJSON
   - Click any borough for full analysis
   - Zoom/pan with mouse or controls
   - Monochrome editorial design (#E4E3E0 bg, #141414 dark)

2. **Flight Path Visualization**
   - 12 real Heathrow, City, Gatwick, and Luton flight paths
   - Animated dots showing direction of travel (arrivals/departures)
   - Color-coded by airport (orange=LHR, blue=LCY, purple=LGW)

3. **DEFRA Noise Contours (WMS Overlay)**
   - Official government aircraft noise data (Lden metric)
   - Road noise layer available
   - Real WMS tiles from `environment.data.gov.uk`
   - Color bands: 55-59dB, 60-64dB, 65-69dB, 70-74dB, 75+dB

4. **Postcode-Level Analysis**
   - Autocomplete dropdown (postcodes.io)
   - Haversine distance calculation to all 5 airports
   - Nearest flight path identification
   - Altitude estimation based on distance from airport
   - Heliport proximity (5 heliports tracked)
   - Noise score computation (airport + path + heliport factors)

5. **Buyer Value Score (Transparent Methodology)**
   - Computed, not hardcoded: `calcScores()` function
   - Three factors:
     - Quiet Skies (40%) - freedom from aircraft noise
     - Affordability (35%) - price vs London min/max
     - Price Growth (25%) - annual appreciation rate
   - Formula: `total = quiet*0.4 + afford*0.35 + growth*0.25`
   - Plain English verdicts (e.g., "Excellent pick", "Affordable but noisy", "Noise is a concern")
   - Full score breakdown with visual bars

6. **Crime Data**
   - **Postcode level**: Live API call to data.police.uk (crimes within 1 mile, broken down by category)
   - **Borough level**: Estimated rates per 1,000 residents (clearly labelled as estimates from Met Police published statistics)

7. **School Ratings**
   - Borough-level Ofsted-based ratings (Excellent/Good)
   - Specific school names and notes for each borough

8. **Property Listings & Sold Prices**
   - Pre-filled search links to Rightmove (sale + rent), Zoopla, OnTheMarket
   - HM Land Registry sold prices (API with CORS fallback to direct links)

9. **Borough Rankings Table**
   - All 29 boroughs ranked by Buyer Value Score
   - Columns: Rank, Borough, Noise Level, Avg Price, Score
   - Click any row for full breakdown

10. **Disclaimer**
    - Persistent banner: "Not a replacement for professional property advice"

### Toggleable Layers (Map Overlays)

| Layer | Default | Source |
|-------|---------|--------|
| Flight Paths (animated) | ON | Curated route data |
| DEFRA Aircraft Noise | ON | environment.data.gov.uk WMS |
| DEFRA Road Noise | OFF | environment.data.gov.uk WMS |
| Live Aircraft | OFF | OpenSky Network API |
| Transport Stations | OFF | Curated (18 major stations) |
| Flood Risk Zones | OFF | Borough-level coloring (EA data) + WMS detail at street zoom |
| Air Quality Areas | OFF | DEFRA AQMA WMS (zoom-aware refresh) |
| Borough Labels | OFF | Computed from GeoJSON centroids |

### Live Aircraft Tracking (Toggle)

- Real aircraft positions from OpenSky Network API
- Refreshes every 15 seconds
- Glowing dots with heading indicators
- **Click any aircraft** for detailed popup:
  - Callsign, altitude, ground speed, heading
  - Vertical rate (climbing/descending/en route)
  - Nearest airport with distance
  - ICAO24 transponder code
  - Direct links to Flightradar24, FlightAware, OpenSky profile

### Additional Insights (Expandable Cards)

- **Flood Risk**: Borough-level rating + colour-coded borough overlay (dark blue=high, medium blue=medium, light blue=low)
- **Air Quality**: Borough-level rating + DEFRA AQMA WMS overlay (zoom-aware)
- **Transport Links**: Rating with specific line/station details

---

## Data Sources & APIs

| Source | URL | Auth | CORS | Usage |
|--------|-----|------|------|-------|
| postcodes.io | `api.postcodes.io/postcodes/` | None | Yes | Postcode geocoding + autocomplete |
| data.police.uk | `data.police.uk/api/crimes-street/` | None | Yes | Live crime data per location |
| DEFRA Noise WMS | `environment.data.gov.uk/spatialdata/airport-noise-*/wms` | None | Yes | Official noise contour tiles |
| DEFRA Road WMS | `environment.data.gov.uk/spatialdata/road-noise-*/wms` | None | Yes | Road noise tiles |
| EA Flood WMS | `environment.data.gov.uk/spatialdata/flood-map-*/wms` | None | Yes | Flood zone tiles |
| DEFRA AQMA WMS | `environment.data.gov.uk/spatialdata/air-quality-*/wms` | None | Yes | Air quality area tiles |
| OpenSky Network | `opensky-network.org/api/states/all` | None | Yes | Real-time aircraft positions |
| Land Registry | `landregistry.data.gov.uk/data/ppi/` | None | Partial | Sold price data |
| GitHub GeoJSON | `raw.githubusercontent.com/*/UK-GeoJSON/` | None | Yes | Borough boundaries |

All data is used under Open Government Licence or open-access terms.

---

## File Structure

```
London Flight Path Map/
  index.html              <- Main application (self-contained, ~1940 lines)
  london_flight_paths.py  <- Original Python/Folium prototype (v1/v2)
  london_flight_paths.html <- Generated output from Python version
  PROJECT.md              <- This file
```

---

## Architecture

### Design System
- Background: `#E4E3E0`
- Dark: `#141414`
- White: `#FAFAF9`
- Accent: `#F27D26` (orange), `#267DF2` (blue), `#26F27D` (green), `#F2B826` (yellow)
- Fonts: JetBrains Mono (data), Inter (prose)
- Monochrome editorial aesthetic with color used sparingly for data

### Key JavaScript Functions

| Function | Purpose |
|----------|---------|
| `calcScores()` | Computes Buyer Value Score from raw borough data |
| `analysePostcode()` | Full postcode analysis (distances, noise, altitude) |
| `fetchCrimeData()` | Live crime data from data.police.uk |
| `fetchLiveFlights()` | Real aircraft positions from OpenSky |
| `fetchSoldPrices()` | Land Registry transaction data |
| `fetchAutocomplete()` | Postcode suggestions from postcodes.io |
| `updateDefraTiles()` | Renders WMS overlay tiles for current map view |
| `renderLiveFlights()` | Plots live aircraft as interactive dots |
| `showFlightPopup()` | Detailed flight info popup on click |
| `buildOptionalSections()` | Metric cards for flood/AQ/transport |
| `buildPropertyLinks()` | Property portal links + sold prices |
| `getVerdict()` | Plain English summary from score components |
| `postcodeNoiseSummary()` | Detailed noise description for postcodes |

### Scoring Methodology

```
QUIET SKIES (40%):  severe=0, high=1.5, moderate-high=3, moderate=5, low-moderate=7.5, low=10
AFFORDABILITY (35%): ((maxPrice - price) / (maxPrice - minPrice)) * 10
PRICE GROWTH (25%):  (trend / maxTrend) * 10
FINAL SCORE:         quiet*0.4 + afford*0.35 + growth*0.25  (scaled 0-10)
```

---

## Borough Coverage (29 Boroughs)

Each borough has: noise impact rating, average price, growth trend, detailed description, property advice, crime level, crime rate, school rating, school details, flood risk, air quality, transport rating.

Top 5 by Buyer Value Score (typical):
1. Enfield - quiet skies, affordable, strong growth
2. Waltham Forest - no aircraft noise, good value
3. Lewisham - inner London value with quiet skies
4. Croydon - most affordable, major regeneration
5. Redbridge - excellent schools, Elizabeth Line

---

## How to Run

1. Open `index.html` in any modern browser
2. That's it. No install, no build, no server needed.

For development:
- Edit `index.html` directly
- Refresh browser to see changes
- All APIs are called client-side (no backend)

---

## Hackathon Suitability

### Why This Works for Hackathons

1. **Real problem, real users**: London has 9M residents, ~500K property transactions/year. Aircraft noise is a genuine blind spot in property decisions.

2. **Multiple live APIs**: Demonstrates API integration (6+ free APIs, all live, no mocking).

3. **Government data integration**: DEFRA WMS, Environment Agency, Land Registry, Police API - shows ability to work with official data sources.

4. **No backend required**: Entirely client-side. Deploy anywhere (GitHub Pages, S3, Netlify) in seconds.

5. **Transparent methodology**: The scoring formula is visible, explainable, and auditable - important for trust.

6. **Differentiated**: No existing tool combines flight noise + crime + schools + flood + AQ + transport + property data in one interface.

### Hackathon Positioning Ideas

| Hackathon Theme | Angle |
|----------------|-------|
| **PropTech / Real Estate** | "Noise-aware property search" - the missing layer in property portals |
| **Smart Cities / GovTech** | Using open government APIs (DEFRA, EA, Police, Land Registry) for citizen decision-making |
| **AI / ML** | Add ML-based price prediction or noise impact scoring (extend the calcScores model) |
| **Sustainability / Climate** | Air quality + flood risk as climate-aware property guidance |
| **Data Visualization** | D3.js multi-layer geospatial dashboard with live data |
| **Amazon Nova Hackathon** | Integrate Amazon Nova for natural language postcode queries ("Find me a quiet 2-bed under 500K near good schools"), use Bedrock for generating personalized property reports, or use Nova to analyze and summarize noise patterns |

### Potential Amazon Nova / AWS Extensions

- **Amazon Nova (Bedrock)**: Natural language interface - "Find quiet areas under 500K with good schools" parsed into filters
- **Amazon Location Service**: Replace postcodes.io with AWS geocoding
- **Lambda + API Gateway**: Backend proxy to solve CORS issues with Land Registry
- **DynamoDB**: Cache API responses, store user saved searches
- **S3 + CloudFront**: Host the static site globally
- **Personalize**: ML-based borough recommendations based on user preferences
- **Comprehend**: Sentiment analysis on area reviews/comments

---

## Limitations & Honest Assessment

### What's Real Data
- DEFRA noise contours (official government WMS)
- Live aircraft positions (OpenSky Network)
- Postcode crime data (data.police.uk)
- Postcode geocoding (postcodes.io)
- Flood risk zones (Environment Agency WMS)
- Air quality areas (DEFRA AQMA WMS)

### What's Curated/Estimated
- Borough average property prices (representative but not live)
- Borough crime rates per 1,000 (estimated from Met Police published stats, clearly labelled)
- School ratings (based on Ofsted data, summarised manually)
- Flight path coordinates (based on published approach/departure routes, not radar data)
- Borough descriptions and property advice (written guidance, not algorithmic)

### Known Issues
- Land Registry API may be blocked by CORS in some browsers (falls back to external links)
- OpenSky Network has rate limits for anonymous users (~10 requests/min)
- GeoJSON source URLs may change (fallback chain handles this)
- Borough boundaries may not perfectly align depending on GeoJSON source
- Property prices are static snapshots, not live market data

---

## Evolution History

| Version | What Changed |
|---------|-------------|
| v1 | Python/Folium basic map with airports and flight paths |
| v2 | Added live flights (OpenSky), property prices, transport, value scoring |
| v3 | Complete visual redesign to D3.js monochrome editorial aesthetic |
| v4 | DEFRA WMS integration, postcodes.io postcode analysis |
| v5 | Plain English descriptions, transparent scoring, heliport data |
| v6 | Crime data (data.police.uk), school ratings, flood/AQ/transport as optional layers |
| v7 | Postcode autocomplete, metric cards, property listing links, Land Registry sold prices |
| v8 | Live aircraft as toggle (not default), animated dots restored, clickable flight details with Flightradar24/FlightAware links |

---

## Licence

Data sourced under Open Government Licence v3.0 (DEFRA, Environment Agency, Land Registry, Police API). OpenSky Network data used under their open access terms. Map boundary data from open GitHub repositories.

The application code is original work.
