# Sky Score Methodology

> Version 1.1 — last updated 2026-05-05.
> Public methodology for the Sky Score property scoring system. Maintained alongside the live API at `https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/`. This document is the canonical reference for B2B integrations and audit conversations.

---

## Contents

1. [What Sky Score is](#1-what-sky-score-is)
2. [Geographic coverage](#2-geographic-coverage)
3. [Components](#3-components)
4. [Computation](#4-computation)
5. [Worked example](#5-worked-example)
6. [Data sources](#6-data-sources)
7. [Attribution](#7-attribution)
8. [Suitability and intended use](#8-suitability-and-intended-use)
9. [Bias and fairness considerations](#9-bias-and-fairness-considerations)
10. [Accuracy and validation](#10-accuracy-and-validation)
11. [Limitations](#11-limitations)
12. [Comparison to alternative tools](#12-comparison-to-alternative-tools)
13. [Personal data and GDPR](#13-personal-data-and-gdpr)
14. [API contract and stability](#14-api-contract-and-stability)
15. [Versioning](#15-versioning)
16. [Provenance and integrity](#16-provenance-and-integrity)
17. [Changelog](#17-changelog)

---

## 1. What Sky Score is

Sky Score is a per-postcode (or per-borough) property quality score from 0 to 10, designed to surface noise, livability, and affordability factors that mainstream UK listings sites have a financial incentive to obscure.

Two surfaces:

- A **consumer site** at `https://d1oe4ftwutjpf.cloudfront.net` that informs renters and buyers.
- A **B2B API** (`/v1/score`) intended for property data aggregators, conveyancers, and Islamic-finance providers whose customers benefit from accurate due-diligence data.

The score is a transparent, weighted combination of four components — Quiet, Affordability, Growth, and Liveability — described below. It is not a market valuation, an EPC rating, or a regulatory rating; it is a holistic quality signal designed to *complement* those.

The product exists to address a structural information asymmetry in UK property: estate agents and listings platforms make money when sales close, so they are not incentivised to surface signals that might cause a buyer to walk away. Sky Score is positioned as the "ethical alternative" data layer for buyers and the institutions that serve them.

## 2. Geographic coverage

**Currently supported:** the 33 London boroughs (32 boroughs plus the City of London), via the `/v1/score` endpoint. Postcodes are resolved through `postcodes.io` and matched to the borough returned by `admin_district`.

**Planned:** New York City (data already encoded in the consumer site; API support is a prioritisation decision, not a data-availability one).

**Out-of-scope today:** the rest of England, Wales, Scotland, and Northern Ireland. A request for a postcode outside the supported geography returns a 404 with a `supportedBoroughs` list so the caller can fall back gracefully.

Coverage will expand in the following priority order:
1. Greater London (already complete)
2. New York City (data ready, API integration pending)
3. UK Core Cities (Manchester, Birmingham, Bristol, Leeds, Edinburgh, Glasgow, Liverpool, Newcastle, Sheffield, Cardiff, Belfast, Nottingham)
4. England and Wales (England EPC and Land Registry coverage is national; geographic expansion is gated by liveability data acquisition)

Coverage of a new region requires four items: a borough/local-authority dataset, a noise impact dataset (DEFRA covers England, Welsh equivalents exist), a property price dataset (Land Registry covers England + Wales), and a liveability dataset. Geographic expansion is data-collection-led, not algorithmic.

## 3. Components

| Component | What it measures | Source inputs | Range |
|---|---|---|---|
| **Quiet** | Aviation + road noise impact at borough level | DEFRA noise mapping, OpenSky Network aircraft tracking, flight path geometry | 0–10 (10 = quietest) |
| **Affordability** | Average sold price relative to neighbouring boroughs | HM Land Registry Price Paid Data | 0–10 (10 = cheapest in cohort) |
| **Growth** | Recent price-trend signal | HM Land Registry Price Paid Data (5-year window) | 0–10 (10 = strongest growth) |
| **Liveability** | Schools, crime, transport, healthcare access | ONS, Department for Education, Home Office crime stats, TfL Open Data, NHS Service Search | 0–10 (10 = most liveable) |

The default Sky Score is computed using the **balanced** persona:

```
score = 0.30 × quiet + 0.25 × afford + 0.20 × growth + 0.25 × live
```

Five named persona presets are available (see [§4](#4-computation)) and the API accepts a `?weights=` override so different customer segments can apply their own preference profile without changes to the underlying components.

## 4. Computation

### 4.1 Component formulas

**Quiet** is a categorical lookup of the borough's aviation noise impact band:

```
IMPACT_TO_QUIET = {
  'low':           10.0,
  'low-moderate':   7.5,
  'moderate':       5.0,
  'moderate-high':  3.0,
  'high':           1.5,
  'severe':         0.0
}
```

The impact band reflects the borough's relationship to UK aviation flight paths and airport proximity (DEFRA Round 4 strategic noise mapping, supplemented by aviation track data). The categorical mapping intentionally preserves clean band semantics rather than smoothing into a continuous space, so the score reflects qualitatively different noise environments rather than spurious decimal precision.

**Affordability** is a min-max scale of the borough's average property price across the supported cohort, inverted so cheaper boroughs score higher:

```
afford = ((max_price - avg_price) / (max_price - min_price)) × 10
```

`max_price` and `min_price` are taken across all boroughs in the supported geography. For London, this is currently approximately £340k (Barking and Dagenham) to £1,350k (Kensington and Chelsea).

**Growth** is a linear scale of the borough's recent price trend, capped by the cohort's strongest performer:

```
growth = (trend / max_trend) × 10
```

Where `trend` is the borough's annualised price growth percentage and `max_trend` is the cohort maximum.

**Liveability** is a weighted combination of four sub-scores, each derived from a documented lookup table:

```
SCHOOL_SCORE     = { outstanding: 10, excellent: 9, good: 6, mixed: 3 }
CRIME_TO_SCORE   = max(0, min(10, 10 - (rate - 50) / 15))
TRANSPORT_SCORE  = { excellent: 10, good: 7, moderate: 4, poor: 2 }
HEALTH_SCORE     = { excellent: 10, good: 7, moderate: 4 }

live = 0.35 × schools + 0.30 × crime + 0.25 × transport + 0.10 × health
```

The `crime` rate is per-1000-population per-year and is converted via a clipped linear function: a borough with the London average crime rate (~50) scores 10/10; a borough at 200 scores 0/10.

### 4.2 Persona presets

| Persona | quiet | afford | growth | live | Suitable for |
|---|---|---|---|---|---|
| `balanced` (default) | 0.30 | 0.25 | 0.20 | 0.25 | General-purpose, no specific preference |
| `family` | 0.20 | 0.20 | 0.10 | 0.50 | Schools, safety, day-to-day liveability matter most |
| `investor` | 0.10 | 0.30 | 0.40 | 0.20 | Capital growth and entry price are primary |
| `firsttime` | 0.15 | 0.40 | 0.20 | 0.25 | Affordability dominates, with quality-of-life adjustment |
| `quietlife` | 0.50 | 0.20 | 0.10 | 0.20 | Peace and freedom from aircraft noise above all else |

### 4.3 Custom weights

The API accepts `?weights=quiet:W,afford:X,growth:Y,live:Z` where the four values must sum to 1.0 (within ±0.01 tolerance). Invalid sums silently fall back to the persona preset (default: balanced) and the response indicates `persona: "custom"` only when a valid override is applied.

### 4.4 Rounding policy

Internal computation uses unrounded floating-point values. Display values in the response are rounded to one decimal place for components and the headline score. Note that multiplying displayed (rounded) component values by their displayed weights will not exactly reproduce the displayed score — the score is computed from unrounded internals, then rounded once at the end. This is intentional and standard practice; it preserves accuracy and avoids compound rounding error.

## 5. Worked example

A real end-to-end calculation, using `SW11 1AA` (Battersea, Wandsworth borough).

### Step 1 — Postcode resolution

The API calls `postcodes.io` to translate the postcode into administrative geography:

```
GET https://api.postcodes.io/postcodes/SW111AA
→ admin_district: "Wandsworth", longitude: -0.1643, latitude: 51.4644
```

### Step 2 — Borough data lookup

Wandsworth's structural inputs (from the embedded London dataset):

```
impact:      'moderate'
avgPrice:    £680,000
trend:       2.1%
schools:     'excellent'
crimeRate:   82 per 1,000
transport:   'excellent'
healthcare:  'good'
```

### Step 3 — Component calculations

**Quiet** = `IMPACT_TO_QUIET['moderate']` = **5.0**

**Affordability** — across the 33 London boroughs, `min_price` = £340,000 (Barking and Dagenham), `max_price` = £1,350,000 (Kensington and Chelsea):
```
afford = ((1,350,000 − 680,000) / (1,350,000 − 340,000)) × 10
       = (670,000 / 1,010,000) × 10
       = 6.6336…
       → displayed as 6.6
```

**Growth** — across the cohort, `max_trend` = 5.8% (Newham and Barking and Dagenham):
```
growth = (2.1 / 5.8) × 10
       = 3.6206…
       → displayed as 3.6
```

**Liveability** — sub-scores:
- Schools: `SCHOOL_SCORE['excellent']` = 9
- Crime (rate 82): `10 − (82 − 50) / 15` = `10 − 2.133…` = 7.867
- Transport: `TRANSPORT_SCORE['excellent']` = 10
- Health: `HEALTH_SCORE['good']` = 7

```
live = 9 × 0.35 + 7.867 × 0.30 + 10 × 0.25 + 7 × 0.10
     = 3.15 + 2.360 + 2.5 + 0.7
     = 8.71
     → displayed as 8.7
```

### Step 4 — Score combination (balanced persona)

```
score = 5.0 × 0.30 + 6.6336 × 0.25 + 3.6206 × 0.20 + 8.71 × 0.25
      = 1.500 + 1.658 + 0.724 + 2.178
      = 6.060
      → displayed as 6.1
```

### Step 5 — Comparison: same postcode, family persona

Family weights: `quiet 0.20, afford 0.20, growth 0.10, live 0.50`.

```
score = 5.0 × 0.20 + 6.6336 × 0.20 + 3.6206 × 0.10 + 8.71 × 0.50
      = 1.000 + 1.327 + 0.362 + 4.355
      = 7.044
      → displayed as 7.0
```

The family persona scores Wandsworth a full point higher than balanced because excellent schools and "excellent" transport dominate the calculation.

### Step 6 — Comparison: same postcode, quietlife persona

Quietlife weights: `quiet 0.50, afford 0.20, growth 0.10, live 0.20`.

```
score = 5.0 × 0.50 + 6.6336 × 0.20 + 3.6206 × 0.10 + 8.71 × 0.20
      = 2.500 + 1.327 + 0.362 + 1.742
      = 5.931
      → displayed as 5.9
```

The quietlife persona scores Wandsworth lower than balanced — because Wandsworth's `quiet: 5.0` (moderate noise) dominates a profile that puts 50% weight on quietness.

This worked example is reproducible against the live API; running the request and computing by hand should yield matching values within rounding tolerance.

## 6. Data sources

Every input is listed below with its source, licence, refresh cadence, and algorithmic role.

| Source | Purpose | Licence | Refresh cadence |
|---|---|---|---|
| **DEFRA Strategic Noise Mapping (Round 4, 2022)** | Baseline aviation + road noise contours for England | Open Government Licence v3.0 | 5-yearly (next: 2027) |
| **OpenSky Network** | Live + historical aircraft positions over UK airspace | OpenSky terms — research/non-commercial on the free tier; commercial use requires explicit agreement | Real-time |
| **HM Land Registry Price Paid Data** | Historic sold prices at postcode resolution | Open Government Licence v3.0 | Monthly |
| **MHCLG Energy Performance Certificates** (new "Get energy performance of buildings data" service from 2026-05-30) | Per-property EPC bands and ratings | Open Government Licence v3.0 | Quarterly |
| **TfL Open Data** | Transport accessibility (Tube, Rail, DLR stations and live status) | TfL Open Data terms — commercial use permitted with attribution | Real-time (line status), static (station locations) |
| **NHS Service Search API** | GP, pharmacy, and hospital availability | Provided by NHS Digital under public-sector terms | Real-time |
| **ONS** | Boundary geometry, demographic context | Open Government Licence v3.0 + OS Open Licence (boundaries) | Annual |
| **Home Office crime statistics** | Borough-level crime rate input | Open Government Licence v3.0 | Monthly |
| **Department for Education school ratings** | Ofsted-derived school quality signal | Open Government Licence v3.0 | Continuous |
| **postcodes.io** | Postcode → administrative-district resolution | Open Government Licence v3.0 (data) | Quarterly |

### Data refresh policy

The API currently uses an **embedded snapshot** of structural inputs (price band averages, crime rates, school quality categorisations, etc.) for the supported boroughs. This snapshot is dated 2026-Q1 and will be refreshed on the following cadence:

- **Annual full refresh** of school, crime, transport, and healthcare classifications, aligned with ONS data publication
- **Quarterly partial refresh** of price and trend data when material movement (≥3% change in cohort min/max) is observed
- **Ad-hoc refresh** if a material event (e.g., a school's Ofsted rating downgrade, a major crime statistic restatement) warrants it

For B2B customers, refresh events are announced in the changelog and a 14-day notice period applies for any change that materially affects scoring (defined as: any borough's score moving by more than 0.5 points under default weights).

EPC data is fetched on-demand via the live MHCLG service and is therefore always current. Sold price data is fetched on-demand via the Land Registry API.

## 7. Attribution

Live API responses include a `sources` array in the response body for every data-source endpoint. Consumers redistributing Sky Score outputs are expected to preserve attribution for the underlying open-data sources. Required attribution lines are reproduced in this document and provided in the response.

> Contains public sector information licensed under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
>
> Powered by TfL Open Data.

## 8. Suitability and intended use

Sky Score **is** suitable for:

- Property due-diligence layers within conveyancing search bundles
- Per-property risk and quality signals in mortgage underwriting workflows (Sharia-compliant home purchase plans particularly)
- Buy-side property platform overlays informing renters and buyers
- Insurance underwriting input for property-quality-aware pricing (with appropriate licence terms — see [§13](#13-personal-data-and-gdpr))
- Site selection for build-to-rent operators
- Local authority and public-sector planning workflows

Sky Score **is not** suitable for, and should not be used as:

- A regulated property valuation (RICS Red Book or equivalent)
- A substitute for a chartered surveyor's report, mortgage survey, or homebuyer's report
- A guarantee of any particular financial outcome (sale price, rental yield, capital growth)
- A measure of investment return or a price prediction
- A flood, contamination, environmental, or legal-risk signal — for these specifically, use a dedicated provider (Landmark Riskview, Climate X, JS Group)
- An EPC certificate replacement — Sky Score's EPC band aggregate is a summary, not an individual certificate

Customers integrating Sky Score are expected to surface this suitability statement (or an equivalent) in user-facing UI where the score is displayed.

## 9. Bias and fairness considerations

A score that influences buying decisions has fairness obligations beyond technical correctness. We document our position openly.

### What the score is and is not

The Sky Score is **descriptive** (what is observably true of a place) and is not **prescriptive** (what should be true, what someone should value, what someone should do). The persona presets and the optional `?weights=` override exist precisely to keep the decision in the hands of the consumer, not the algorithm.

### Inputs we do not use

The following are **never** used as inputs to the Sky Score:

- Race, ethnicity, religion, age, disability status, sexual orientation, or any protected characteristic
- The current or historic ethnic or religious composition of the area
- Asylum-seeker accommodation density
- Income or wealth distributions of residents

### Indirect-correlation risks

Some of our inputs correlate with socioeconomic factors:

- **Crime rates** correlate with deprivation indices in published ONS data. A low crime score should not be interpreted as a signal about the residents of a borough; it is a signal about reported crime statistics. We use Home Office police-force-area data, which is itself subject to reporting bias (under-reporting in some communities, over-reporting in others).
- **Schools data** uses Ofsted ratings, which have known correlations with intake demographics. We do not adjust for this; we display the rating as-is.
- **Transport scores** correlate with infrastructure investment, which has historic geographic biases. Hackney scores `excellent` for transport despite having no Underground stations, because we count Overground, National Rail, and bus density as excellent infrastructure — but a different methodology might score it lower.

### Limitations of the personas

Our five named personas (`family`, `investor`, etc.) are illustrative profiles, not actual user segmentation. A real "family" includes many shapes — single parents, carers, multigenerational households — each of whom might weight components differently. Customers should treat persona presets as *starting points* and prefer the `?weights=` override for tailored use.

### Geographic granularity

Borough-level data masks within-borough variation. Hounslow's borough-wide noise impact is "severe" because of Heathrow, but parts of Chiswick at the eastern edge of the borough are materially quieter. Per-postcode resolution does not currently improve this; we plan finer-grained noise modelling (using the actual DEFRA noise raster sampled at postcode-centroid level) in v2 of the methodology.

### Backward-looking trends

The `growth` component reflects historical price trends. Past growth does not predict future returns. Customers using Sky Score for investment-related decisions should treat `growth` as descriptive context, not a forecast.

### Reporting

If you believe a Sky Score output reflects bias or unfair input handling, contact us via the GitHub repository's issue tracker. We log and review reported concerns.

## 10. Accuracy and validation

- **Postcode resolution** is verified against the ONS National Statistics Postcode Lookup (NSPL) via `postcodes.io`, which is the canonical UK postcode authority.
- **Borough name normalisation** handles known aliases (e.g., `City of London Corporation` → `City of London`, `Barking and Dagenham` ↔ `Barking`).
- **Noise impact bands** have been spot-checked against DEFRA's Round 4 strategic noise mapping rasters at borough centroid points; the bands have also been audited against the historical scoring code in the consumer site (March 2026 audit caught and fixed the contradictory-verdict bug between component and overall scoring).
- **Sold price data** is sample-validated against the public Land Registry portal at known transactions to ensure the cohort min/max bounds are correct.
- **EPC band aggregates** are sample-validated against the legacy `epc.opendatacommunities.org` portal until full migration to the new service is complete; post-migration validation is against the new service's per-certificate detail endpoint.
- **Worked-example reproducibility** is built into the methodology document — running the calculations by hand on a real postcode response from the live API yields matching values within rounding tolerance.

### Validation we have not yet done

The following validation steps are planned but not yet completed; they are gating items before any contractual accuracy claim:

- **Independent measured-noise validation.** Comparing predicted noise impact to ground-truth dB measurements at known properties using a calibrated sound meter. Required before any underwriting integration.
- **Panel-of-experts review.** Submitting the methodology document to chartered surveyors, RICS valuers, and noise consultants for independent critique.
- **Outcome correlation study.** Comparing Sky Score outputs against medium-term property outcomes (capital growth, void rates, transaction times) to assess whether the components are predictive of real-world quality signals.

These items are tracked in the public roadmap and customer contracts will explicitly note which validation tier the methodology has reached at the time of contract execution.

## 11. Limitations

- **OpenSky aircraft tracking** is on the research/non-commercial free tier on the consumer site. Coverage is limited at night and rate-limited (~10 req/min anonymous, more on standard tier). The B2B API does **not** call OpenSky directly; aviation context for the API is sourced from the static DEFRA noise band that has been pre-computed for each borough. A commercial aviation source (FlightAware Firehose, Flightradar24 Business, ADS-B Exchange paid tier) will be integrated before any paying customer needs live aviation data.
- **Borough-level granularity** is the highest resolution for several inputs (crime, schools); per-postcode variation within a borough is not always reflected. v2 will improve this for the noise component using the actual DEFRA raster.
- **Price trend signal** is a simple linear trend; it does not capture cyclical effects, local development announcements, or interest-rate-driven cycles.
- **Geography is currently London only.** See [§2](#2-geographic-coverage).
- **EPC service migration in progress.** Pre-2026-05-30 outputs use the legacy `epc.opendatacommunities.org` API; post-2026-05-30 use the new `get-energy-performance-data.communities.gov.uk` service. The new service exposes a narrower per-search response (band only, with numeric rating moved to a separate per-certificate endpoint); Sky Score synthesises a numeric rating from band midpoints to maintain consumer-site UI compatibility.
- **Sky Score is not regulated** under the Estate Agents Act 1979 or the Property Misdescriptions Act 1991 (nor would it need to be, since it is data infrastructure, not an estate agent). Customers integrating the score into regulated workflows (mortgage underwriting, insurance pricing) are responsible for their own compliance with FCA, PRA, and ICO obligations.

## 12. Comparison to alternative tools

We document our position relative to the existing UK property-data landscape. This is informational, not adversarial.

| Tool | Owner | Primary buyer | What they do | Overlap with Sky Score |
|---|---|---|---|---|
| **Hometrack** | Zoopla / DMGT | Mortgage lenders | Automated valuation models (AVM), UK-wide property data | None on noise / livability; entirely valuation-focused |
| **Climate X** | Independent (raised £21M Series A) | Lenders, insurers, asset managers | Physical climate risk (flood, heat, subsidence) | Complementary domain; not competing |
| **Landmark Riskview** | Landmark Information Group / DMGT | Conveyancers (via aggregated search bundles) | Environmental risk, contamination, flood, **DEFRA road noise** | Shares the noise data source (DEFRA) but does not compose into a holistic per-property score and has no halal-finance angle |
| **Sprift** | Independent | Surveyors, conveyancers | Multi-source property intelligence aggregator | Broader scope, lower depth on each input |
| **TwentyCi** | Independent | Marketing/CRM teams in property | Listing-stream and market-intelligence data | Different audience, marketing-focused |
| **Yopa, Strike, Purplebricks** | Various | Consumers (transactional) | Listing platforms / hybrid agencies | Not data-products; different category |

Sky Score's positioning is at the intersection of three dimensions that no incumbent currently combines: noise + livability composite scoring, halal-finance-aware framing, and an explicit "ethical alternative to incentive-misaligned listing platforms" stance. Aggregator partnerships (notably Landmark) are seen as *complementary* — Sky Score can be a layered input into Landmark's search bundles, not a replacement for them.

## 13. Personal data and GDPR

- The consumer site does not store personally identifiable data on the user beyond a session cookie. Saved favourites are scoped to a free-text userId and a postcode; no email, name, or device identifier is collected.
- Per-property EPC data may include household-identifiable address fields. The consumer site shows aggregated postcode-level summaries by default; per-address detail is rendered only when the user has explicitly searched a single address.
- The B2B API (`/v1/score`) does not return per-property data — it returns borough-level scoring keyed by postcode. No personal data is exposed via the score endpoint.
- A future per-UPRN endpoint, if introduced, will require authenticated customers with a documented lawful basis (legitimate interest for due diligence is the typical applicable basis under UK GDPR Article 6(1)(f)).
- All data is processed in **AWS eu-west-2 (London)** for UK data residency. AWS is the sole sub-processor.
- Sky Score will sign a Data Processing Agreement (DPA) with B2B customers handling personal data through the API.
- Customers are responsible for their own compliance obligations to the data subjects whose properties they look up. We provide attribution and methodology transparency to support those obligations; we do not act as the data controller for end-buyer or end-renter records.

## 14. API contract and stability

### v1 stability commitment

The `/v1/*` API path is committed-stable for **a minimum of 12 months** from the first paying-customer integration. During that period:

- No path or response-shape change will be made that breaks existing clients.
- New fields may be added to responses without prior notice (clients should ignore unknown fields).
- New endpoints under `/v1/` may be added.
- New optional query parameters may be added.

### Breaking changes

Any breaking change will be deployed under a new version path (`/v2/`) and `/v1/` will remain available for a **minimum of 6 months** after `/v2/` general availability. Customers will receive a **minimum 90-day deprecation notice** with migration guidance before `/v1/` is decommissioned.

### Methodology changes

Methodology updates that materially change scoring behaviour (defined as: any borough's score moving by more than 0.5 points under default weights) will be:

1. Announced in the changelog and to API customers via email.
2. Subject to a **14-day grace period** during which customers can opt to remain on the prior methodology version via a `?methodology=` query parameter.
3. Documented as a `methodologyVersion` bump in the API response.

Non-material methodology changes (improved data refreshes, fixed component formulas that don't change outputs) ship without notice.

### Status and incidents

A status page at `status.skyscore.com` is planned for general-availability launch. Until then, ad-hoc incident communication is via the email address on the customer contract.

### Rate limits and quotas

The free-tier `SkyScoreFreeTierKey` enforces:
- 1,000 requests per month
- 5 requests per second burst
- 2 requests per second sustained

Paid tiers will be introduced when the first paying integrator commits; tier definitions will be documented here and on a public pricing page.

## 15. Versioning

The methodology and the API contract are versioned independently:

- **Methodology versions** track changes to scoring logic, weights, or data sources. Breaking changes increment the major version (`Methodology v1.0 → v2.0`).
- **API versions** are pinned in the URL path (`/v1/score`, `/v2/score`) and changes are tracked in the project changelog.
- Score values from prior methodology versions remain reproducible from archived inputs; the API response includes the methodology version used (`"methodologyVersion": "1.1"`).

## 16. Provenance and integrity

- **Source code** is open at `https://github.com/billkhiz-bit/london-flight-path-map`.
- **Live API URL** is `https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/`.
- **Live demo** of the API rendered as a UI: `https://d1oe4ftwutjpf.cloudfront.net/score-demo/`.
- **This document** is committed to the repository and versioned with the codebase. The version listed at the top of this document corresponds to a tagged commit in source control.
- **Issues and methodology questions**: open a GitHub issue on the repository, or contact via the consumer site's contact form.

## 17. Changelog

- **2026-05-05 (v1.1)** — Substantial expansion. Added Geographic coverage, Worked example, Suitability and intended use, Bias and fairness considerations, Comparison to alternative tools, API contract and stability sections. Component formulas made explicit. Data refresh policy documented. No change to scoring outputs.
- **2026-05-05 (v1.0)** — First published methodology document. Aligns with current production scoring; documents EPC migration in progress.
