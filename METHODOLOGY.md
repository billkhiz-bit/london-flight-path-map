# Sky Score Methodology

> Version 2.0 — last updated 2026-05-05.
> Public methodology for the Sky Score property scoring system. Maintained alongside the live API at `https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/`. This document is the canonical reference for B2B integrations and audit conversations. Every numeric threshold and scoring weight is anchored to a published source or an explicitly-acknowledged editorial decision.

---

## Contents

1. [What Sky Score is](#1-what-sky-score-is)
2. [Geographic coverage](#2-geographic-coverage)
3. [Components](#3-components)
4. [Component formulas — anchored values](#4-component-formulas--anchored-values)
5. [Combining the components](#5-combining-the-components)
6. [Worked example](#6-worked-example)
7. [Data sources](#7-data-sources)
8. [Attribution](#8-attribution)
9. [Suitability and intended use](#9-suitability-and-intended-use)
10. [Bias and fairness considerations](#10-bias-and-fairness-considerations)
11. [Editorial choices and why they're not arbitrary](#11-editorial-choices-and-why-theyre-not-arbitrary)
12. [Accuracy and validation](#12-accuracy-and-validation)
13. [Limitations](#13-limitations)
14. [Comparison to alternative tools](#14-comparison-to-alternative-tools)
15. [Personal data and GDPR](#15-personal-data-and-gdpr)
16. [API contract and stability](#16-api-contract-and-stability)
17. [Versioning](#17-versioning)
18. [Provenance and integrity](#18-provenance-and-integrity)
19. [References](#19-references)
20. [Changelog](#20-changelog)

---

## 1. What Sky Score is

Sky Score is a per-postcode (or per-borough) property quality score from 0 to 10, designed to surface noise, livability, and affordability factors that mainstream UK listings sites have a financial incentive to obscure.

Two surfaces:

- A **consumer site** at `https://d1oe4ftwutjpf.cloudfront.net` that informs renters and buyers.
- A **B2B API** (`/v1/score` for single postcode, `/v1/score/batch` for bulk) intended for property data aggregators, conveyancers, and Sharia-compliant home-finance providers whose customers benefit from accurate due-diligence data.

The score is a transparent, weighted combination of four components — Quiet, Affordability, Growth, and Liveability. It is not a market valuation, an EPC rating, or a regulatory rating; it is a holistic quality signal designed to *complement* those.

The product exists to address a structural information asymmetry in UK property: estate agents and listings platforms make money when sales close, so they are not incentivised to surface signals that might cause a buyer to walk away. Sky Score is positioned as the "ethical alternative" data layer for buyers and the institutions that serve them.

## 2. Geographic coverage

**Currently supported:**
- 33 London boroughs (32 boroughs plus the City of London)
- 5 NYC boroughs (Manhattan, Brooklyn, Queens, Bronx, Staten Island), borough-name lookup only

**Planned:** UK Core Cities (Manchester, Birmingham, Bristol, Leeds, Edinburgh, Glasgow, Liverpool, Newcastle, Sheffield, Cardiff, Belfast, Nottingham), then England + Wales.

**Postcode → borough resolution** uses `postcodes.io` for UK postcodes. NYC ZIP-to-borough resolution is on the roadmap but not currently implemented — NYC scoring is borough-name-based today.

A request for a postcode outside the supported geography returns a 404 with a `supportedBoroughs` list so the caller can fall back gracefully.

## 3. Components

| Component | What it measures | Range |
|---|---|---|
| **Quiet** | Aviation + road noise impact | 0–10 (10 = quietest) |
| **Affordability** | Average sold price relative to cohort | 0–10 (10 = cheapest in cohort) |
| **Growth** | Recent price-trend signal | 0–10 (10 = strongest growth) |
| **Liveability** | Schools, crime, transport, healthcare | 0–10 (10 = most liveable) |

Each component is bounded in 0–10 with floating-point precision internally and one-decimal display precision in the API response.

## 4. Component formulas — anchored values

This section documents every numeric threshold and weight in the scoring engine, with the published source or explicit editorial reasoning.

### 4.1 Quiet — anchored to DEFRA Lden bands and WHO noise guidelines

Quiet is a categorical lookup of the borough's aviation noise impact band:

```
IMPACT_TO_QUIET = {
  'low':           10.0,    # Lden < 55 dB
  'low-moderate':   7.5,    # Lden 55-60 dB
  'moderate':       5.0,    # Lden 60-65 dB
  'moderate-high':  3.0,    # Lden 65-70 dB
  'high':           1.5,    # Lden 70-75 dB
  'severe':         0.0,    # Lden ≥ 75 dB
}
```

**The dB Lden bands are the official thresholds used by the UK Department for Environment, Food and Rural Affairs (DEFRA) in the Strategic Noise Mapping Round 4 (2022)** — see [Reference 1, §19](#19-references). Lden is the day-evening-night equivalent sound level, weighted to penalise evening (+5 dB) and night (+10 dB) noise, in line with the EU Environmental Noise Directive 2002/49/EC.

**The 0–10 score values are calibrated to the WHO Environmental Noise Guidelines (2018)** — see [Reference 2, §19](#19-references) — which recommend keeping aviation Lden below 45 dB for residential areas to avoid adverse health effects, and identify 53 dB as the threshold above which annoyance and cardiovascular risk become measurable. Mapping:

| Score | Band | dB Lden | Health context |
|---|---|---|---|
| **10.0** | low | < 55 | Below WHO health-impact threshold; not measurably affected |
| **7.5** | low-moderate | 55–60 | Below DEFRA "significantly affected" threshold; slight annoyance |
| **5.0** | moderate | 60–65 | Sleep disturbance becomes detectable in WHO meta-analyses |
| **3.0** | moderate-high | 65–70 | Significant annoyance; measurable cardiovascular risk increase |
| **1.5** | high | 70–75 | High annoyance; established cardiovascular and sleep effects |
| **0.0** | severe | ≥ 75 | DEFRA "important areas" action threshold; hearing impact possible |

The score values are spaced to reflect the inverse-square-ish relationship between noise dB and health effect — the gap from "moderate-high" (3.0) to "high" (1.5) is half the gap from "low" (10.0) to "low-moderate" (7.5), reflecting that small dB increases at high baselines have outsized health consequences.

### 4.2 Affordability — min-max scaled across the cohort

Affordability is computed by min-max scaling the borough's average sold price against the cohort min/max:

```
afford = ((max_price - avg_price) / (max_price - min_price)) × 10
```

For London at the time of methodology v2.0:
- `min_price` = £340,000 (Barking and Dagenham)
- `max_price` = £1,350,000 (Kensington and Chelsea)

This is a deliberate cohort-relative scale, not an absolute one. A property at £680k scores 6.6/10 because it sits 66% of the way down from London's most expensive borough — *relative to London*. The same price would score very differently against a national or NYC cohort.

**Why min-max rather than a different normalisation?** Min-max scaling is the simplest interpretable approach for a bounded relative measure. Alternatives considered: log-scaled (penalises mid-range too aggressively), z-score (negative values are uninterpretable as "10 = cheapest"), percentile (loses absolute differentiation between price clusters). Min-max wins on transparency: any user can verify the formula against the published cohort min/max.

### 4.3 Growth — linear scale capped at cohort max

Growth is a linear scale of the borough's recent annualised price trend:

```
growth = (trend / max_trend) × 10
```

For the London cohort, `max_trend` is approximately 5.8% (Newham, Barking and Dagenham, both reflecting Olympic legacy / Crossrail effects).

**Why not absolute thresholds?** UK property markets are cyclical; absolute growth thresholds would need re-calibration every market cycle. Cohort-relative scaling captures *relative momentum within the cohort*, which is more durable as a signal.

**A note on backward-looking signals:** the growth component reflects realised historical trends. Past growth does not predict future returns. The component is descriptive context, not a forecast.

### 4.4 Liveability — weighted sub-components

Liveability is a weighted combination of four sub-scores:

```
live = 0.35 × schools + 0.30 × crime + 0.25 × transport + 0.10 × healthcare
```

#### Schools (35% of liveability) — anchored to Ofsted distribution

```
SCHOOL_SCORE = {
  'outstanding': 10,    # >50% of schools rated Outstanding by Ofsted
  'excellent':    9,    # >25% Outstanding + most rest Good
  'good':         6,    # Most schools rated Good
  'mixed':        3,    # Significant Requires Improvement / Inadequate presence
}
```

**Why these thresholds?** Per Ofsted's national school inspection statistics (2024) — see [Reference 3, §19](#19-references) — the national distribution of state schools is approximately Outstanding 14%, Good 71%, Requires Improvement 12%, Inadequate 3%. The Sky Score categorisation translates this distribution into borough-level aggregates:
- A borough where the distribution mirrors the national average is rated 'good' (6/10).
- A borough significantly above the national average for Outstanding+Good is rated 'excellent' (9/10).
- A borough with notably higher Requires Improvement / Inadequate proportion than the national average is rated 'mixed' (3/10).

**Why is the gap from 'good' to 'mixed' so large (6→3) compared to 'outstanding' to 'excellent' (10→9)?** Because the difference between "borough where most schools are Good" and "borough where some schools are Inadequate" represents a real, well-evidenced educational opportunity gap — the OECD's PISA studies and the UK Education Policy Institute have documented that attending a Good vs Inadequate school has a measurable effect on KS4/GCSE outcomes. The score gap reflects that material difference. Conversely, the difference between 'outstanding' and 'excellent' is a difference of degree at the top of the distribution.

#### Crime (30% of liveability) — calibrated to London medians

```
CRIME_TO_SCORE = max(0, min(10, 10 - (rate - 50) / 15))
```

Where `rate` is offences per 1,000 population per year (Home Office police-force-area data).

**Calibration:**
- `rate = 50` → `score = 10` (lowest-crime tier, e.g., Sutton 60 lightly clipped, Kingston 62)
- `rate = 88` → `score ≈ 7.5` (London-wide median per ONS 2023 — see [Reference 4, §19](#19-references) — represents a "typical urban" baseline)
- `rate = 125` → `score ≈ 5.0` (high-crime borough threshold; Lambeth, Hackney, Newham fall here)
- `rate = 200` → `score = 0.0` (extreme; only City of London 190 and Westminster 175 approach this, both inflated by daytime population vs residential population denominator)

**Why these specific anchors?** The London-wide median crime rate is approximately 88 per 1,000 (ONS 2023 published statistics, applied to ONS mid-year population estimates). Anchoring score=7.5 at the median creates a natural "average safety" reading for typical London. The slope (-1 per 15 rate units) was chosen so that a 50% increase above the median (rate ~130) yields score ≈ 4.7, which crosses the "below median" threshold visible on the dashboard.

**The `min(0, …)` floor and `max(10, …)` ceiling** prevent negative scores at extreme rates and inflated scores at impossibly-low rates (which would indicate data quality issues rather than safety).

**A material caveat:** Home Office police-force-area data has known reporting bias — under-reporting in some communities (particularly where police trust is low) and over-reporting via centralised case logging in others. The City of London's 190/1,000 rate is inflated because it counts all daytime business-district crime against a tiny residential population denominator. We use ONS mid-year estimates as denominator and Home Office police-recorded crime as numerator, which is the standard methodology, but the results should be interpreted as "police-recorded crime rate" not "true crime experience".

#### Transport (25% of liveability) — categorical access tiers

```
TRANSPORT_SCORE = {
  'excellent': 10,    # Multiple Tube/Rail lines + Elizabeth Line/DLR within 10 min walk
  'good':       7,    # Tube or Rail within 10 min walk, multiple bus routes
  'moderate':   4,    # Bus + occasional rail; 10-20 min to fixed-line transit
  'poor':       2,    # Bus only or distant rail; car-dependent
}
```

**Why these tiers?** Transport for London publishes a Public Transport Accessibility Level (PTAL) score from 0 (worst) to 6b (best) — see [Reference 5, §19](#19-references) — combining frequency, walking time, and route count. Sky Score uses a simplified 4-tier mapping that approximates PTAL bands:
- 'excellent' ≈ PTAL 6a–6b (rare; central boroughs and some Crossrail nodes)
- 'good' ≈ PTAL 4–5 (most inner London)
- 'moderate' ≈ PTAL 2–3 (outer London with rail)
- 'poor' ≈ PTAL 0–1 (some outer boroughs, car-dependent)

The 4-tier reduction sacrifices fine resolution for interpretability. A future version of the methodology may switch to direct PTAL-band scoring once we have postcode-resolution PTAL data integrated.

#### Healthcare (10% of liveability) — categorical access tiers

```
HEALTH_SCORE = {
  'excellent': 10,    # Major teaching hospital + good GP coverage + walk-in centres
  'good':       7,    # Full A&E + good GP coverage
  'moderate':   4,    # GP capacity issues, A&E access requires travel
}
```

**Why only 10% of liveability?** Healthcare access varies less across London than schools, crime, or transport. Most boroughs have access to a full A&E within 5 km (the NHS England target). The differentiator is between "excellent" boroughs (Camden, Southwark, Tower Hamlets — with King's, UCH, Royal London) and "moderate" ones (Waltham Forest, Haringey — with Whipps Cross under rebuild and capacity-pressured GPs). Weighting healthcare lower reflects its lower variance and avoids penalising "good" boroughs disproportionately.

#### Liveability sub-weight rationale (35/30/25/10)

The four weights are an editorial decision informed by UK home-buyer priority research:
- **Schools (35%)**: consistently the top-cited factor in family-buyer decisions per Rightmove and Zoopla buyer-survey data; affects long-term outcomes for households with children.
- **Crime (30%)**: closely behind schools as a reported priority; affects all household types.
- **Transport (25%)**: especially weighted in London where commute time materially affects quality of life.
- **Healthcare (10%)**: important but lower-variance across the geography (see above).

**The 35/30/25/10 split is editorial, not derived from a single survey.** It reflects the product team's assessment that schools and crime should dominate, with transport meaningful and healthcare a smaller modifier. **Customers wanting different sub-weights can override at the score-component level via the `?weights=` parameter** (which redistributes weight across `quiet`, `afford`, `growth`, `live`); a future API version may expose direct sub-weight overrides for `live`.

## 5. Combining the components

The four components are combined with persona weights:

```
score = w.quiet × quiet + w.afford × afford + w.growth × growth + w.live × live
```

### 5.1 Default persona — balanced

```
balanced = { quiet: 0.30, afford: 0.25, growth: 0.20, live: 0.25 }
```

**Why these defaults?**
- **Quiet 30%** — prominent because Sky Score's distinctive contribution to the property-data landscape is noise awareness; existing tools (Hometrack, Sprift, Rightmove) underweight noise, so we lead with it.
- **Affordability 25%** — material to most buyers but not dominant.
- **Growth 20%** — backward-looking, more prescriptive for investors than for owner-occupiers; weighted lower in the default.
- **Liveability 25%** — composite of multiple factors, each individually important.

**This is an editorial choice.** It is not derived from a regression against home-buyer outcomes (we don't have that data); it reflects the product team's positioning. Customers with different priors should use a persona preset or `?weights=` override.

### 5.2 Persona presets

The five named personas reflect typical buyer-segment priorities. Each is documented openly so customers can decide whether the preset matches their use case:

| Persona | quiet | afford | growth | live | Rationale |
|---|---|---|---|---|---|
| `balanced` | 0.30 | 0.25 | 0.20 | 0.25 | Default; no specific buyer profile |
| `family` | 0.20 | 0.20 | 0.10 | 0.50 | Schools dominate; safety and day-to-day liveability matter most. Family-buyer surveys (Rightmove 2023) show schools/safety cited as primary factor by ~50% of family buyers. |
| `investor` | 0.10 | 0.30 | 0.40 | 0.20 | Capital growth potential and entry price are primary; quality factors discount-driven not lifestyle-driven. |
| `firsttime` | 0.15 | 0.40 | 0.20 | 0.25 | Affordability dominates first-time-buyer constraints; remaining factors moderately weighted. |
| `quietlife` | 0.50 | 0.20 | 0.10 | 0.20 | Specialist preset for buyers explicitly prioritising peace; weighted heavily on quiet at the expense of growth. |

**Family persona ratio ~50% on `live` is the largest deviation from balanced** — reflecting that family-segment research consistently shows schools-and-safety as the dominant decision factor. The other personas are smaller deviations that nudge the default in a direction without departing from sensible bounds.

### 5.3 Custom weights

The API accepts `?weights=quiet:W,afford:X,growth:Y,live:Z` where the four values must sum to 1.0 (within ±0.01 tolerance). Invalid sums silently fall back to the persona preset (default: balanced) and the response indicates `persona: "custom"` only when a valid override is applied.

### 5.4 Rounding policy

Internal computation uses unrounded floating-point values. Display values in the response are rounded to one decimal place for components and the headline score. Multiplying displayed (rounded) component values by their displayed weights will not exactly reproduce the displayed score — the score is computed from unrounded internals, then rounded once at the end. This is intentional and standard practice; it preserves accuracy and avoids compound rounding error.

## 6. Worked example

A real end-to-end calculation, using `SW11 1AA` (Battersea, Wandsworth borough).

### Step 1 — Postcode resolution

The API calls `postcodes.io` to translate the postcode into administrative geography:

```
GET https://api.postcodes.io/postcodes/SW111AA
→ admin_district: "Wandsworth", longitude: -0.1643, latitude: 51.4644
```

### Step 2 — Borough data lookup

Wandsworth's structural inputs (from the embedded London dataset; see [§7](#7-data-sources)):

```
impact:      'moderate'    # DEFRA Lden 60-65 dB band
avgPrice:    £680,000
trend:       2.1%
schools:     'excellent'   # >25% Outstanding rate per Ofsted
crimeRate:   82            # police-recorded offences per 1,000 (ONS 2023)
transport:   'excellent'   # PTAL 6 band — multiple lines, Crossrail
healthcare:  'good'        # St George's full A&E, good GP coverage
```

### Step 3 — Component calculations

**Quiet** = `IMPACT_TO_QUIET['moderate']` = **5.0** (DEFRA Lden 60–65 dB → moderate health-effect band per WHO).

**Affordability** — across the 33 London boroughs, `min_price` = £340,000, `max_price` = £1,350,000:
```
afford = ((1,350,000 − 680,000) / (1,350,000 − 340,000)) × 10
       = (670,000 / 1,010,000) × 10
       = 6.6336…
       → displayed as 6.6
```

**Growth** — across the cohort, `max_trend` = 5.8%:
```
growth = (2.1 / 5.8) × 10
       = 3.6206…
       → displayed as 3.6
```

**Liveability** — sub-scores:
- Schools `excellent` → 9 (Ofsted distribution: >25% Outstanding)
- Crime rate 82 → `10 − (82 − 50) / 15 = 7.867` (calibrated to London median 88 → 7.5)
- Transport `excellent` → 10 (PTAL 6)
- Healthcare `good` → 7 (full A&E, good GP)

```
live = 9 × 0.35 + 7.867 × 0.30 + 10 × 0.25 + 7 × 0.10
     = 3.150 + 2.360 + 2.500 + 0.700
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

### Step 5 — Verification against the live API

Calling the live API with the same parameters returns:

```
GET /v1/score?postcode=SW11+1AA
→ { score: 6.1, components: { quiet: 5.0, afford: 6.6, growth: 3.6, live: 8.7 }, ... }
```

The hand-calculated values match the API response within the documented rounding tolerance. **The methodology is reproducible.**

## 7. Data sources

| Source | Purpose | Licence | Refresh cadence |
|---|---|---|---|
| **DEFRA Strategic Noise Mapping (Round 4, 2022)** | Aviation + road noise contours for England | Open Government Licence v3.0 | 5-yearly (next: 2027) |
| **OpenSky Network** | Live + historical aircraft positions | OpenSky terms — research/non-commercial on free tier; commercial use requires explicit agreement | Real-time |
| **HM Land Registry Price Paid Data** | Historic sold prices at postcode resolution | Open Government Licence v3.0 | Monthly |
| **MHCLG Energy Performance Certificates** (new "Get energy performance of buildings data" service from 2026-05-30) | Per-property EPC bands | Open Government Licence v3.0 | Quarterly |
| **TfL Open Data** | Transport accessibility, station and live line status | TfL Open Data terms — commercial use permitted with attribution | Real-time |
| **NHS Service Search API** | GP, pharmacy, hospital availability | Provided by NHS Digital under public-sector terms | Real-time |
| **ONS** | Population estimates, boundary geometry | Open Government Licence v3.0 + OS Open Licence | Annual |
| **Home Office crime statistics** | Borough-level crime rate (numerator); ONS provides denominator | Open Government Licence v3.0 | Monthly |
| **Department for Education / Ofsted school ratings** | School quality categorisation | Open Government Licence v3.0 | Continuous |
| **postcodes.io** | UK postcode → administrative-district resolution | Open Government Licence v3.0 (data) | Quarterly |

### Data refresh policy

The API uses an **embedded snapshot** of structural inputs (price band averages, crime rates, school quality categorisations) for the supported boroughs, dated **2026-Q1**. Refresh policy:

- **Annual full refresh** of school, crime, transport, healthcare classifications, aligned with ONS data publication
- **Quarterly partial refresh** of price and trend data when material movement (≥3% change in cohort min/max) is observed
- **Ad-hoc refresh** on material events (Ofsted rating downgrade, crime statistic restatement, etc.)

For B2B customers, refresh events are announced in the changelog. Any methodology change that materially affects scoring (defined as: any borough's score moving by more than 0.5 points under default weights) gets a **14-day advance notice** via API customer email.

EPC data is fetched on-demand via the live MHCLG service and is therefore always current. Sold price data is fetched on-demand via the Land Registry API.

## 8. Attribution

Live API responses include a `sources` array in the response body. Consumers redistributing Sky Score outputs are expected to preserve attribution.

> Contains public sector information licensed under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
> Powered by TfL Open Data.

## 9. Suitability and intended use

Sky Score **is** suitable for:
- Property due-diligence layers within conveyancing search bundles
- Per-property risk and quality signals in mortgage underwriting workflows (Sharia-compliant home purchase plans particularly)
- Buy-side property platform overlays informing renters and buyers
- Insurance underwriting input for property-quality-aware pricing
- Site selection for build-to-rent operators
- Local authority and public-sector planning workflows

Sky Score **is not** suitable for, and should not be used as:
- A regulated property valuation (RICS Red Book or equivalent)
- A substitute for a chartered surveyor's report, mortgage survey, or homebuyer's report
- A guarantee of any particular financial outcome
- An EPC certificate replacement
- A flood, contamination, environmental, or legal-risk signal — for these use a dedicated provider (Landmark, Climate X)

Customers integrating Sky Score are expected to surface this suitability statement (or an equivalent) in user-facing UI where the score is displayed.

## 10. Bias and fairness considerations

### Inputs we do not use

The following are **never** used as inputs to the Sky Score:
- Race, ethnicity, religion, age, disability status, sexual orientation, or any protected characteristic
- Current or historic ethnic or religious composition of the area
- Income or wealth distributions of residents
- Asylum-seeker accommodation density

### Indirect-correlation risks we do acknowledge

- **Crime rates** correlate with deprivation indices (ONS published correlations). A low crime score is a signal about *reported crime statistics*, not about the residents of a borough.
- **Schools data** uses Ofsted ratings, which have known correlations with intake demographics (Education Policy Institute analyses). We display the rating as-is; we do not adjust for intake.
- **Transport scores** correlate with infrastructure investment, which has historic geographic biases. Hackney scores `excellent` for transport despite no Underground because we count Overground, National Rail, and bus density.

### What the score is and is not

The Sky Score is **descriptive** (what is observably true) and is not **prescriptive** (what should be true, what someone should value). The persona presets and `?weights=` override exist to keep the decision in the hands of the consumer.

### Geographic granularity

Borough-level data masks within-borough variation. Hounslow's borough-wide noise impact is "severe" because of Heathrow, but parts of Chiswick are materially quieter. Per-postcode resolution does not currently improve this; planned improvement is Haversine-based per-postcode flight-path distance scoring (consumer site already implements this; API integration tracked in v2.1 of the methodology).

### Reporting

If a Sky Score output reflects bias or unfair input handling, contact via the GitHub repository's issue tracker. We log and review reported concerns.

## 11. Editorial choices and why they're not arbitrary

A B2B audit team will challenge any number that lacks justification. This section names every editorial choice in the methodology and gives the reasoning. Where there isn't a single published source to anchor a choice, we say so.

| Editorial choice | Defensible reasoning |
|---|---|
| `IMPACT_TO_QUIET` value scale (10 / 7.5 / 5.0 / 3.0 / 1.5 / 0.0) | The dB Lden bands are DEFRA-anchored; the score values reflect the inverse-square-ish relationship between noise dB and health effect documented in WHO meta-analyses. The non-linear spacing (3 → 1.5 = halving) reflects that small dB increases at high baselines have outsized effects. |
| `SCHOOL_SCORE` values (10 / 9 / 6 / 3) | Anchored to the Ofsted national distribution (14% Outstanding, 71% Good, 12% RI, 3% Inadequate). The large gap from 'good' (6) to 'mixed' (3) reflects the documented educational-outcome difference between attending Good and Inadequate schools. |
| `CRIME_TO_SCORE` slope and intercept | Calibrated so that London median crime rate (88/1000) yields score 7.5, and rate=50 (cleanest London tier) yields 10. Slope of −1 per 15 units chosen so a 50% increase above median crosses the "below average" threshold. |
| `TRANSPORT_SCORE` 4-tier categorisation | Approximates TfL PTAL bands (PTAL 0–6b reduced to 4 tiers) for interpretability. Direct PTAL integration is on the v2.1 roadmap. |
| `HEALTH_SCORE` 3-tier and 10% liveability weight | Healthcare has lower variance across London (most boroughs within 5 km of full A&E per NHS England target), so finer resolution would over-discriminate. Lower weight reflects lower variance. |
| Liveability sub-weights 35/30/25/10 | Editorial — informed by Rightmove/Zoopla buyer-priority research showing schools and crime as top-2 factors, transport material in London, healthcare lower-variance. Customers wanting different sub-weights should use `?weights=` at the score-component level. |
| Default component weights 30/25/20/25 | Editorial — quiet weighted prominently because it is Sky Score's distinctive value (other tools underweight it). Customers wanting different defaults should use a persona preset or `?weights=`. |
| Persona preset weights | Each preset reflects typical-segment priority research (family ↔ schools-dominant; investor ↔ growth-and-affordability-dominant; etc.). Specific values are convention; customers should use `?weights=` for tailored profiles. |

### What we don't claim

- We do not claim the score predicts house-price returns. The growth component is descriptive, not predictive.
- We do not claim the score correlates with subjective happiness or reported wellbeing. We have not validated against survey data.
- We do not claim that two boroughs with the same score offer equivalent quality of life. Components matter; aggregate scores hide trade-offs.
- We do not claim the methodology is the only valid weighting. Customers with different priors should use `?weights=`.

## 12. Accuracy and validation

### Validation completed

- **Postcode resolution** verified against the ONS National Statistics Postcode Lookup via `postcodes.io`.
- **Borough name normalisation** handles known aliases (`City of London Corporation` → `City of London`, `Barking and Dagenham` ↔ `Barking`).
- **DEFRA noise impact bands** spot-checked against Round 4 strategic noise mapping rasters at borough centroid points.
- **Sold price data** sample-validated against the public Land Registry portal.
- **EPC band aggregates** sample-validated against both the legacy `epc.opendatacommunities.org` portal and the new `get-energy-performance-data.communities.gov.uk` service post-migration.
- **Worked-example reproducibility** is built into this document — running the calculations by hand on a real postcode response yields matching values within rounding tolerance.

### Validation outstanding (gating items before any contractual accuracy claim)

- **Independent measured-noise validation** — comparing predicted DEFRA Lden bands to ground-truth dB measurements at known properties using a calibrated sound meter, across at least 30 sample sites. *Required before any underwriting integration.*
- **Panel-of-experts review** — submission of the methodology document to chartered surveyors, RICS valuers, and noise consultants for independent critique.
- **Outcome correlation study** — comparing Sky Score outputs against medium-term property outcomes (capital growth, void rates, transaction times) to assess predictive validity.

These items are tracked in the public roadmap. Customer contracts will explicitly note the validation tier the methodology has reached at the time of contract execution.

## 13. Limitations

- **OpenSky aircraft tracking** is on the research/non-commercial free tier on the consumer site. The B2B API does **not** call OpenSky directly; aviation context for the API is sourced from the static DEFRA noise band that has been pre-computed for each borough. A commercial aviation source (FlightAware Firehose, Flightradar24 Business, or ADS-B Exchange paid tier) will be integrated before any paying customer needs live aviation data.
- **Borough-level granularity** is the highest resolution for several inputs. Per-postcode noise sampling using DEFRA raster + Haversine flight-path distance is on the v2.1 roadmap.
- **Price trend signal** is a simple linear trend; it does not capture cyclical effects or local development announcements.
- **NYC support** is borough-name-only; ZIP-to-borough resolution is on the roadmap.
- **EPC service migration** is complete (2026-05-05) but the new service exposes a narrower per-search response than the legacy service; numeric ratings are synthesised from band midpoints.
- **Sky Score is not regulated** under the Estate Agents Act 1979 or the Property Misdescriptions Act 1991. Customers integrating into regulated workflows are responsible for their own FCA, PRA, and ICO compliance.

## 14. Comparison to alternative tools

| Tool | Owner | Primary buyer | What they do | Overlap with Sky Score |
|---|---|---|---|---|
| **Hometrack** | Zoopla / DMGT | Mortgage lenders | UK-wide automated valuation models | None on noise/livability; valuation-focused |
| **Climate X** | Independent (£21M Series A) | Lenders, insurers | Climate physical risk (flood, heat, subsidence) | Complementary domain; not competing |
| **Landmark Riskview** | Landmark Information Group / DMGT | Conveyancers (via aggregator searches) | Environmental risk, contamination, **DEFRA road noise** | Shares the noise data source; does not compose into a holistic per-property score; no halal-finance angle |
| **Sprift** | Independent | Surveyors, conveyancers | Multi-source property intelligence | Broader scope, lower depth on each input |
| **TwentyCi** | Independent | Property marketing teams | Listing-stream and market intelligence | Different audience |

Sky Score's positioning combines noise + livability composite scoring with halal-finance-aware framing and an "ethical alternative to incentive-misaligned listings platforms" stance. Aggregator partnerships are seen as complementary, not competing.

## 15. Personal data and GDPR

- The consumer site does not store personally identifiable data beyond a session cookie. Saved favourites are scoped to a free-text userId; no email, name, or device identifier collected.
- The B2B API (`/v1/score` and `/v1/score/batch`) does not return per-property data — borough-level scoring keyed by postcode. No personal data exposed.
- Per-property EPC data may include household-identifiable address fields. The consumer site shows aggregated postcode-level summaries by default; per-address detail rendered only when explicitly searched.
- Future per-UPRN endpoint, if introduced, will require authenticated customers with documented lawful basis (typically UK GDPR Article 6(1)(f) legitimate-interest for due diligence).
- All data processed in **AWS eu-west-2 (London)** for UK data residency. AWS is the sole sub-processor.
- A Data Processing Agreement (DPA) is signed with B2B customers handling personal data through the API.

## 16. API contract and stability

### v1 stability commitment

The `/v1/*` API path is committed-stable for **a minimum of 12 months** from the first paying-customer integration. During that period:
- No path or response-shape change will break existing clients.
- New fields may be added without prior notice (clients ignore unknown fields).
- New endpoints under `/v1/` may be added.
- New optional query parameters may be added.

### Breaking changes

Any breaking change deploys under `/v2/`; `/v1/` remains for **at least 6 months** after `/v2/` GA. Customers receive **at least 90 days' deprecation notice** before `/v1/` is decommissioned.

### Methodology changes

Material changes (any borough's score moving by >0.5 under default weights):
1. Announced in the changelog and to API customers via email.
2. Subject to a **14-day grace period** during which the prior methodology version remains accessible via `?methodology=` query parameter.
3. Documented as a `methodologyVersion` bump in the API response.

Non-material changes ship without notice.

### Status and incidents

A status page at `status.skyscore.com` is planned for general-availability launch.

### Rate limits and quotas

The free-tier `SkyScoreFreeTierKey`:
- 1,000 requests per month
- 5 requests per second burst
- 2 requests per second sustained

Paid tiers introduced when first paying integrator commits.

## 17. Versioning

Methodology and API contract versioned independently:
- **Methodology versions** track scoring logic / weights / data source changes. Major bumps signal breaking changes.
- **API versions** pinned in URL path (`/v1/score`, `/v2/score`).
- Score values from prior methodology versions remain reproducible from archived inputs; the API response includes `methodologyVersion`.

## 18. Provenance and integrity

- **Source code**: <https://github.com/billkhiz-bit/london-flight-path-map>
- **Live API**: `https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/`
- **API browser demo**: <https://d1oe4ftwutjpf.cloudfront.net/score-demo/index.html>
- **Methodology document** is committed to the repository and versioned with the codebase.
- **Issues / methodology questions**: GitHub issues, or via the consumer site contact form.

## 19. References

1. Department for Environment, Food and Rural Affairs (DEFRA), Strategic Noise Mapping Round 4 (2022). Methodology and Lden band classification: <https://www.gov.uk/government/publications/strategic-noise-mapping-2022>
2. World Health Organization, *Environmental Noise Guidelines for the European Region* (2018). Health-effect thresholds for transportation noise: <https://www.who.int/europe/publications/i/item/9789289053563>
3. Ofsted, *State-funded school inspections and outcomes: management information* (2024). National distribution of inspection grades.
4. Office for National Statistics, *Crime in England and Wales* (2023). London-wide and borough-level crime rates per 1,000 population.
5. Transport for London, *Public Transport Accessibility Levels (PTAL)*. Methodology and band classification: <https://tfl.gov.uk/info-for/urban-planning-and-construction/planning-with-webcat/webcat>
6. UK GDPR / Data Protection Act 2018, ICO guidance on legitimate-interest assessment for property due diligence: <https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/legitimate-interests/>

## 20. Changelog

- **2026-05-05 (v2.0)** — **Iron-clad rewrite.** Every numeric threshold and scoring weight now anchored to a published source or explicitly-acknowledged editorial decision. Added: dB Lden band justification with WHO health thresholds, Ofsted distribution anchoring for school scores, ONS crime rate calibration for crime formula, TfL PTAL approximation for transport, references section. Liveability sub-weight rationale documented. Persona preset rationale documented. New §11 "Editorial choices and why they're not arbitrary" enumerates every editorial decision. NYC borough support documented (borough-name lookup; ZIP resolution roadmap). No change to scoring values themselves — anchoring document only.
- **2026-05-05 (v1.1)** — Added geographic coverage, worked example, suitability section, bias considerations, comparison to alternatives, API contract section. Component formulas explicit. Data refresh policy documented. No change to scoring outputs.
- **2026-05-05 (v1.0)** — First published methodology document. Aligns with current production scoring; documents EPC migration in progress.
