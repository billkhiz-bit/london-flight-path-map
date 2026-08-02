# Sky Score Methodology

> Version 3.5, last updated 2026-08-02.
> Public methodology for the Sky Score property scoring system. Maintained alongside the live API at `https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/`. This document is the canonical reference for B2B integrations and audit conversations. Every numeric threshold and scoring weight is anchored to a published source, an official government index, or an explicitly-acknowledged editorial decision.

---

## Contents

1. [What Sky Score is](#1-what-sky-score-is)
2. [Geographic coverage](#2-geographic-coverage)
3. [Components](#3-components)
4. [Component formulas, anchored values](#4-component-formulas--anchored-values)
   - 4.1 Quiet (with §4.5 per-postcode Haversine)
   - 4.5 Per-postcode quiet, Haversine geometry (v3.0)
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

- A **consumer site** at `https://skyscore.co.uk` that informs renters and buyers.
- A **B2B API** (`/v1/score` for single postcode, `/v1/score/batch` for bulk) intended for property data aggregators, conveyancers, and Sharia-compliant home-finance providers whose customers benefit from accurate due-diligence data.

The score is a transparent, weighted combination of four components, Quiet, Affordability, Growth, and Liveability. It is not a market valuation, an EPC rating, or a regulatory rating; it is a holistic quality signal designed to *complement* those.

The product exists to address a structural information asymmetry in UK property: estate agents and listings platforms make money when sales close, so they are not incentivised to surface signals that might cause a buyer to walk away. Sky Score is positioned as the "ethical alternative" data layer for buyers and the institutions that serve them.

## 2. Geographic coverage

**Currently supported:**
- 33 London boroughs (32 boroughs plus the City of London), UK postcode resolution
- 5 NYC boroughs (Manhattan, Brooklyn, Queens, Bronx, Staten Island), borough-name lookup or 5-digit US ZIP auto-detection (~182 residential ZIPs covered, ~110 with per-ZIP centroid for finer quiet-score precision)

**Planned:** UK Core Cities (Manchester, Birmingham, Bristol, Leeds, Edinburgh, Glasgow, Liverpool, Newcastle, Sheffield, Cardiff, Belfast, Nottingham), then England + Wales.

**Postcode → borough resolution** uses `postcodes.io` for UK postcodes; NYC ZIPs use a static lookup table baked into the Lambda (sourced from NYC OpenData ZCTA boundaries + USPS). ZIPs without an explicit centroid fall back to the borough-aggregate Lden band for the quiet score; non-NYC US ZIPs (e.g. 90210) return a structured 404 with the supported borough list.

A request for a postcode outside the supported geography returns a 404 with a `supportedBoroughs` list so the caller can fall back gracefully.

## 3. Components

| Component | What it measures | Range |
|---|---|---|
| **Quiet** | Aviation + road noise impact | 0-10 (10 = quietest) |
| **Affordability** | Average sold price relative to cohort | 0-10 (10 = cheapest in cohort) |
| **Growth** | Recent price-trend signal | 0-10 (10 = fastest riser, 5 = flat market, 0 = steepest faller) |
| **Liveability** | Schools, crime, transport, healthcare | 0-10 (10 = most liveable) |

Each component is bounded in 0-10 with floating-point precision internally and one-decimal display precision in the API response.

## 4. Component formulas, anchored values

This section documents every numeric threshold and weight in the scoring engine, with the published source or explicit editorial reasoning.

### 4.1 Quiet, anchored to DEFRA Lden bands and WHO noise guidelines

Quiet is a categorical lookup of the borough's aviation noise impact band:

```
IMPACT_TO_QUIET = {
  'low': 10.0, # Lden < 55 dB
  'low-moderate': 7.5, # Lden 55-60 dB
  'moderate': 5.0, # Lden 60-65 dB
  'moderate-high': 3.0, # Lden 65-70 dB
  'high': 1.5, # Lden 70-75 dB
  'severe': 0.0, # Lden ≥ 75 dB
}
```

**The dB Lden bands are the official thresholds used by the UK Department for Environment, Food and Rural Affairs (DEFRA) in the Strategic Noise Mapping Round 4 (published 2022, data current as of 2021)**, see [Reference 1, §19](#19-references). DEFRA's published reporting bands are 5-dB-wide buckets (55-59, 60-64, 65-69, 70-74, ≥75); we round to whole 5-dB boundaries (55, 60, 65, etc.) for human readability, with no loss of precision since the underlying band assignments match.

**Consumer-site overlay.** The aircraft-noise contour overlay shown on the consumer map at `https://skyscore.co.uk/` is a one-shot capture of the same DEFRA Round 4 WMS at a fixed Greater-London bbox (-0.85 to 0.40 lon, 51.10 to 51.78 lat) — covers the full LHR butterfly contour, LCY's eastern approach corridor, and LGW (Gatwick, whose contour reaches Croydon/Sutton/Bromley). Self-hosted on CloudFront for performance (DEFRA's GeoServer takes ~9 s to render the request live; the cached PNG serves in ~86 ms). Refresh procedure when DEFRA publishes Round 5 (~2027): see `OPERATIONS.md` §3.5. Stansted and Luton are excluded — their Lden ≥55 dB contours don't reach inhabited Greater London.

Lden is the day-evening-night equivalent sound level, weighted to penalise evening (+5 dB) and night (+10 dB) noise, defined in **EU Environmental Noise Directive 2002/49/EC** (Reference 6), the regulatory framework DEFRA implements. Sky Score's quiet score is therefore methodologically anchored to a multi-decade EU regulatory standard, not to a Sky-Score-specific construct.

**The 0-10 score values are calibrated to the WHO Environmental Noise Guidelines (2018)**, see [Reference 2, §19](#19-references), which recommend keeping aviation Lden below 45 dB for residential areas to avoid adverse health effects, and identify 53 dB as the threshold above which annoyance and cardiovascular risk become measurable. Mapping:

| Score | Band | dB Lden | Health context |
|---|---|---|---|
| **10.0** | low | < 55 | Below WHO health-impact threshold; not measurably affected |
| **7.5** | low-moderate | 55-60 | Below DEFRA "significantly affected" threshold; slight annoyance |
| **5.0** | moderate | 60-65 | Sleep disturbance becomes detectable in WHO meta-analyses |
| **3.0** | moderate-high | 65-70 | Significant annoyance; measurable cardiovascular risk increase |
| **1.5** | high | 70-75 | High annoyance; established cardiovascular and sleep effects |
| **0.0** | severe | ≥ 75 | DEFRA "important areas" action threshold; hearing impact possible |

The score values are spaced to reflect the inverse-square-ish relationship between noise dB and health effect, the gap from "moderate-high" (3.0) to "high" (1.5) is half the gap from "low" (10.0) to "low-moderate" (7.5), reflecting that small dB increases at high baselines have outsized health consequences.

### 4.2 Affordability, min-max scaled across the cohort

Affordability is computed by min-max scaling the borough's average sold price against the cohort min/max:

```
afford = ((max_price - avg_price) / (max_price - min_price)) × 10
```

For London at the time of methodology v2.1:
- `min_price` = £340,000 (Barking and Dagenham)
- `max_price` = £1,350,000 (Kensington and Chelsea)

The borough average values are derived from **HM Land Registry's UK House Price Index (HPI)**, see [Reference 7, §19](#19-references), the official monthly publication of UK property prices. HPI is preferred over raw Price Paid Data here because it controls for compositional changes (mix of property types) and is the standard reference used by mortgage lenders, the Bank of England, and the Office for National Statistics for residential price tracking.

This is a deliberate cohort-relative scale, not an absolute one. A property at £660k (Wandsworth's 2026-Q2 average) scores 6.7/10 because it sits two-thirds of the way down from London's most expensive borough, *relative to London*. The same price would score very differently against a national or NYC cohort.

**Why min-max rather than a different normalisation?** Min-max scaling is the simplest interpretable approach for a bounded relative measure. Alternatives considered: log-scaled (penalises mid-range too aggressively), z-score (negative values are uninterpretable as "10 = cheapest"), percentile (loses absolute differentiation between price clusters). Min-max wins on transparency: any user can verify the formula against the published cohort min/max.

### 4.3 Growth, dual-anchor scale

Growth is a **dual-anchor** scale on the borough's recent annualised price trend. A flat market — prices neither rising nor falling — sits at the midpoint, and each tail is scaled to its own extreme within the cohort:

```
growth = 5 + (trend / max_trend) × 5    where trend > 0   (max_trend = fastest riser)
growth = 5                              where trend = 0
growth = 5 − (trend / min_trend) × 5    where trend < 0   (min_trend = steepest faller)
```

all then clamped to 0–10. The fastest-rising borough scores 10, the steepest-falling scores 0, and a flat market scores exactly 5.

**Why the midpoint is absolute and the tails are relative.** The 5.0 anchor is a real-world fact (0% price movement), so it does not drift when the cohort is re-based at a quarterly refresh. The extremes are cohort-relative, which keeps the scale usable when the whole market moves. This is the same cohort-relative reasoning applied to both directions rather than only upward.

**Why the tails are scaled separately.** The London cohort's trends run from −28.2% to +5.0% as of the 2026-Q2 snapshot. A single symmetric map across that range would compress every rising borough into the top sixth of the scale, making +5.0% nearly indistinguishable from +0.4%. Scaling each side to its own extreme keeps both tails legible.

**What this replaced (v3.2–v3.3).** The previous formula was `clamp((trend / max_trend) × 10, 0, 10)`, scaled against the fastest riser alone. Every falling borough therefore floored at 0: **fourteen of the thirty-three London boroughs shared one value**, and Ealing (−0.3%) scored identically to the City of London (−28.2%). The component carried no signal for 42% of the map, and the API had to publish a caveat stating that growth "cannot tell a slight dip apart from a steep fall". Under v3.4 the same cohort yields 28 distinct values, and only the steepest faller sits on the floor. See §20 for the full changelog entry.

For the London cohort as of the 2026-Q2 snapshot, `max_trend` is +5.0% (Waltham Forest) and `min_trend` is −28.2% (City of London); fourteen boroughs carry negative 12-month trends.

**Why not absolute thresholds?** UK property markets are cyclical; absolute growth thresholds would need re-calibration every market cycle. Cohort-relative scaling captures *relative momentum within the cohort*, which is more durable as a signal.

**A note on backward-looking signals:** the growth component reflects realised historical trends. Past growth does not predict future returns. The component is descriptive context, not a forecast.

### 4.4 Liveability, weighted sub-components

Liveability is a weighted combination of four sub-scores:

```
live = 0.35 × schools + 0.30 × crime + 0.25 × transport + 0.10 × healthcare
```

#### Schools (35% of liveability), DfE Progress 8

```
school_score(p8) = max(0, min(10, 5.0 + 5.0 * p8))
```

Where `p8` is the local authority's average Progress 8 score from the DfE Key
Stage 4 performance statistics.

**Why Progress 8, and why these anchors.** Progress 8 measures the grades a
cohort achieves against pupils nationally who had the same Key Stage 2 starting
point. It is *defined* such that the national average is approximately 0.0, and
±1.0 means a full grade per subject better or worse than similar pupils. Both
are real-world quantities rather than artefacts of whichever areas happen to be
in the dataset, so the mapping is:

- `p8 = 0.0` → `score = 5.0` — the national average
- `p8 = +1.0` → `score = 10.0` — a grade per subject above similar pupils
- `p8 = -1.0` → `score = 0.0` — a grade per subject below

Observed local-authority scores span roughly −0.90 to +0.73 nationally, so
nothing clamps in practice. Because the anchors are external constants rather
than the loaded cohort's extremes, scores remain comparable both between areas
and across data vintages.

**Being intake-adjusted matters here.** Raw attainment (Attainment 8) correlates
heavily with local affluence, which this model already prices into the
`afford` component. Using it would let the same underlying factor enter the
composite twice. Progress 8 measures what schools add to the pupils they have.

**What this replaced, and why.** Until methodology v3.5 the schools input was a
four-value vocabulary (`outstanding`/`excellent`/`good`/`mixed`) mapped to
10/9/6/3 and described as anchored to the Ofsted grade distribution. Two
problems, both material:

1. **The bands were not derivable from Ofsted data.** Checked against the Ofsted
   management-information release, no threshold on "percentage of schools Good
   or Outstanding" reproduced the stored values — `excellent` spanned 90.9-100%
   and `good` spanned 83.3-100%, so Westminster at 100% was banded `good` while
   Richmond at 100% was banded `excellent`. They were editorial assignments.
2. **The underlying measure had been withdrawn.** Ofsted abolished single-word
   overall-effectiveness grades in September 2024. Only around 44% of schools
   still carry one, and that remainder is precisely those not yet re-inspected,
   so the sample is both shrinking and non-random. Around 87% of what remains
   is Good or Outstanding, so the measure barely separated one area from
   another. Its replacement framework covered under 1% of schools at the time
   of the change and uses an incompatible vocabulary.

**A caveat on vintage.** Progress 8 cannot be calculated for 2024/25 or 2025/26:
those cohorts sat Key Stage 2 in 2019/20 and 2020/21 when national tests were
cancelled, so no prior-attainment baseline exists, and the DfE announced in
April 2024 that there would be no replacement measure for those years. The
2022/23 release is therefore the current terminal vintage and will refresh when
2026/27 data is published. This is disclosed per response in `sourceBreakdown`.

**A caveat on granularity.** Progress 8 is published at local-authority level,
so every address within a borough receives the same schools sub-score. It
describes the borough, not the specific catchment of a given property.

#### Crime (30% of liveability)

```
CRIME_TO_SCORE = max(0, min(10, 10 - (rate - 50) / 15))
```

Where `rate` is total recorded offences (excluding fraud) per 1,000 residents
per year.

**Source.** ONS *Crime in England and Wales: Police Force Area data tables*,
Table C4, which reports rates per 1,000 population for Community Safety
Partnership areas — these correspond to local authorities in almost all cases,
including every London borough. The denominator is ONS mid-year population
estimates. The separate CSP-level dataset was discontinued; these figures now
ship inside the Police Force Area workbook.

**Calibration:**
- `rate = 50` → `score = 10`
- `rate ≈ 88` → `score ≈ 7.5` (close to the London median)
- `rate = 125` → `score = 5.0`
- `rate = 200` → `score = 0.0`

Tested against the year-ending-March-2026 release, exactly one of 43 London and
Greater Manchester local authorities clamps (Westminster, discussed below), and
none clamps at the top. The band is therefore left unchanged at v3.5.

**Corrections made in v3.5.** Three boroughs carried values that had been
compressed to fit inside the 50-200 band rather than drawn from the source:
Westminster held 175 against an actual 355.5, Kensington and Chelsea 95 against
145.8, and Camden 130 against 173.3. All three are high-crime central boroughs,
and the effect was to understate them. They now carry the published figures. The
other 29 boroughs already agreed with the release within 10 per 1,000 and were
left untouched, so v3.5 is a tail correction rather than a vintage roll.

**A material caveat on city-centre areas.** Recorded-crime rates divide offences
by *resident* population, so districts with large commuting, student or visitor
populations are systematically overstated — the crime is counted, the people are
not. ONS flags this explicitly and, for the same reason, **declines to publish a
rate for the City of London at all** owing to its very small resident
population. Sky Score currently carries an estimated figure there; treat it, and
Westminster's 355.5, as artefacts of the denominator rather than as statements
about how safe those places are to live.

**A second caveat.** Police-recorded crime reflects both offending and reporting
behaviour, which varies with confidence in the police and with force recording
practice. These figures should be read as "police-recorded crime rate", not as
"true crime experience".

#### Transport (25% of liveability), categorical access tiers

```
TRANSPORT_SCORE = {
  'excellent': 10, # Multiple Tube/Rail lines + Elizabeth Line/DLR within 10 min walk
  'good': 7, # Tube or Rail within 10 min walk, multiple bus routes
  'moderate': 4, # Bus + occasional rail; 10-20 min to fixed-line transit
  'poor': 2, # Bus only or distant rail; car-dependent
}
```

**Why these tiers?** Transport for London publishes a Public Transport Accessibility Level (PTAL) score from 0 (worst) to 6b (best), see [Reference 5, §19](#19-references), combining frequency, walking time, and route count. Sky Score uses a simplified 4-tier mapping that approximates PTAL bands:
- 'excellent' ≈ PTAL 6a-6b (rare; central boroughs and some Crossrail nodes)
- 'good' ≈ PTAL 4-5 (most inner London)
- 'moderate' ≈ PTAL 2-3 (outer London with rail)
- 'poor' ≈ PTAL 0-1 (some outer boroughs, car-dependent)

The 4-tier reduction sacrifices fine resolution for interpretability. A future version of the methodology may switch to direct PTAL-band scoring once we have postcode-resolution PTAL data integrated.

#### Healthcare (10% of liveability), categorical access tiers

```
HEALTH_SCORE = {
  'excellent': 10, # Major teaching hospital + good GP coverage + walk-in centres
  'good': 7, # Full A&E + good GP coverage
  'moderate': 4, # GP capacity issues, A&E access requires travel
}
```

**Why only 10% of liveability?** Healthcare access varies less across London than schools, crime, or transport. Most boroughs have access to a full A&E within 5 km (the NHS England target). The differentiator is between "excellent" boroughs (Camden, Southwark, Tower Hamlets, with King's, UCH, Royal London) and "moderate" ones (Waltham Forest, Haringey, with Whipps Cross under rebuild and capacity-pressured GPs). Weighting healthcare lower reflects its lower variance and avoids penalising "good" boroughs disproportionately.

**Roadmap.** A future v3.0 of the methodology will replace the categorical lookup with direct sampling of Care Quality Commission (CQC) ratings, see [Reference 8, §19](#19-references). CQC ratings use the same 4-tier structure as Ofsted (Outstanding / Good / Requires improvement / Inadequate) and are the official UK regulator's published assessments. This will give per-trust resolution rather than borough-aggregate.

### 4.5 Per-postcode quiet, Haversine geometry (v3.0)

When the API receives a postcode that resolves to lat/lon (UK postcodes via postcodes.io), the **Quiet** component is computed at *postcode resolution* rather than borough-aggregate, using Haversine distance to airports and flight-path geometry. This is the same algorithm the consumer site has used for 290+ neighbourhoods since launch (`index.html:1118-1247`); v3.0 ports it to the API.

**Algorithm (per postcode):**

```
noise_score = 0

# 1. Airport proximity, distance to nearest major airport in km
nearest_ap_dist = min(haversine(postcode, airport) for airport in AIRPORTS)
if nearest_ap_dist < 3: noise_score += 5
elif nearest_ap_dist < 6: noise_score += 4
elif nearest_ap_dist < 10: noise_score += 3
elif nearest_ap_dist < 15: noise_score += 2
elif nearest_ap_dist < 20: noise_score += 1

# 2. Flight-path proximity, distance to nearest waypoint of any path
min_path_dist = min(haversine(postcode, waypoint) for path in PATHS for waypoint in path)
if min_path_dist < 1: noise_score += 4
elif min_path_dist < 2: noise_score += 3
elif min_path_dist < 4: noise_score += 2
elif min_path_dist < 6: noise_score += 1

# 3. Major-airport bonus
# London: +2 if LHR < 15 km
# NYC: +2 if JFK < 15 km, +1 additional if LGA < 10 km
if major_airport_dist < 15: noise_score += 2
if (city == 'nyc') and (lga_dist < 10): noise_score += 1

quiet = max(0, min(10, 10 - noise_score))
```

**Airports tracked:**
- **London**: LHR, LGW, LCY, STN, LTN
- **NYC**: JFK, LGA, EWR, TEB

**Flight-path geometry:** 12 corridors for London (Lambourne Stack, Biggin Stack, Ockham Stack, Bovingdon Stack, LHR departure paths, LCY approach/departure, LGW approach, LTN approach), 8 for NYC (JFK arrivals/departures, LGA, EWR). Each corridor is a sequence of waypoints; we use the shortest distance to any waypoint as the proxy for distance to the corridor.

**Why this matters in practice.** The borough-aggregate Lden band masks within-borough variation. Concrete examples (computed against the live v3.0 API):

| Postcode | Borough | Borough Lden band | v2.1 quiet | v3.0 quiet | What v3.0 captures |
|---|---|---|---|---|---|
| `N1 7SX` | Hackney | low | 10.0 | **4.0** | Directly under the **Lambourne Stack** (LHR east-London arrival corridor); the borough-level "low" was wrong for this specific postcode |
| `TW3 4DX` | Hounslow | severe | 0.0 | **2.0** | Under LHR approach; v3.0 doesn't *worsen* severe-band postcodes (they were correctly 0.0) |
| `SW11 1AA` | Wandsworth | moderate | 5.0 | **7.0** | Battersea is south of major flight paths; the borough-aggregate over-counted this specific area's exposure |
| `SE1 9SG` | Southwark | low-moderate | 7.5 | **5.0** | Some LCY approach-east traffic + central-London flight density bring this lower than the borough-aggregate suggested |

This is a material improvement in within-borough accuracy. Some postcodes go up (correctly: they're quieter than the borough-aggregate suggested); some go down (correctly: they're under specific corridors the borough-level didn't reflect).

**Provenance.** Airport coordinates are taken from official sources (ICAO/IATA published locations). Flight-path geometry is derived from FAA / NATS / DEFRA published approach and departure procedures, simplified to waypoint sequences. Flight paths are reviewed annually as airline networks shift.

**Why postcode wins over borough.** When postcode-level Haversine is available, it overrides the borough Lden band entirely (rather than blending). The borough Lden band remains in the `context.noiseImpactBand` field for transparency, but doesn't contribute to the score. Rationale: the borough Lden is itself an aggregate over many postcodes, including the one being queried; using both would double-count.

**Resolution chain (v3.1).** As of methodology v3.1, the score Lambda checks three resolution tiers in order, using the highest available:

1. **Raster**, direct DEFRA Lden sample at the postcode centroid via DynamoDB lookup (gold standard). When the raster table is populated, this tier wins.
2. **Postcode (Haversine)**, distance to airports + flight-path geometry (this section, §4.5). Used when raster is unavailable.
3. **Borough (Lden band)**, borough-aggregate IMPACT_TO_QUIET lookup. Used when neither raster nor postcode lat/lon is available.

The chosen tier is reported in `context.quietResolution` (`'raster' | 'postcode' | 'borough'`) so integrators can verify which tier produced the response.

**NYC ZIP centroids (v3.1, shipped).** NYC ZIPs now have static centroid lat/lon for ~110 ZIPs (sourced from the consumer site's `NYC_AREA_MAP`). This means NYC ZIP queries now use the v3.0 Haversine layer too, with the JFK/LGA/EWR/TEB airports and 8 NYC flight-path corridors. Within-borough variation is meaningful: 11201 (DUMBO) returns quiet=8 (north Brooklyn, away from JFK approach), while 11375 (Forest Hills) returns quiet=2 (under JFK / LGA traffic).

**Limitations of v3.0 / v3.1 Haversine (resolved when raster table is populated):**
- Airport-proximity bonus uses Euclidean-style distance, not flight-corridor membership. A postcode 5 km from an airport but to the *side* of the runway corridor is currently penalised the same as one directly under the corridor. Raster sampling will correct this.
- Flight-path waypoints are coarse polylines, not full flight-procedure geometries with altitude data. A postcode under a 9,000-ft transit gets the same noise score as one under a 1,500-ft final approach.
- NYC ZIP centroids are representative neighbourhood points, not true ZCTA polygon centroids. ~1 km of within-ZIP imprecision.

### 4.6 DEFRA raster sampling (v3.1, scaffold-ready, awaiting data load)

When populated, the v3.1 raster tier replaces Haversine with direct sampling of the DEFRA Strategic Noise Mapping (Round 4, 2022) Lden GeoTIFF at the postcode centroid. This is the gold-standard method.

**Architecture:**
- DynamoDB table `london-flight-map-noise-raster` (deployed, currently empty)
- Schema: `postcode` (string, hash key) → `ldenDb` (number, dB Lden value)
- Score Lambda reads with `ProjectionExpression='ldenDb'` and converts dB to quiet score using the same band mapping documented in §4.1
- LRU-cached at the Lambda level for repeat queries within a container

**Population (one-time batch):**
- The `scripts/load_defra_raster.py` script downloads the DEFRA GeoTIFF (~500 MB, free OGL) and the ONS NSPL postcode lat/lon table, then samples the raster at every UK postcode centroid and writes (postcode, ldenDb) tuples to DynamoDB.
- Estimated runtime: ~1 hour for ~1.7M UK postcodes at DynamoDB on-demand write throughput.
- One-time cost: a few pounds in DynamoDB write capacity + S3 for the GeoTIFF caching.
- Refresh cadence: every 5 years (next DEFRA Round 5 publication, ~2027).

**Forward compatibility:** the Lambda code path checks the raster table first and silently falls back to v3.0 Haversine when the table is empty or missing. This means the API works identically whether or not the raster data has been loaded; loading the raster automatically upgrades quiet scores from `'postcode'` resolution to `'raster'` resolution without any API change.

**Why we're not loading it now:** the data load is a one-shot ops task (~1 hour) that needs to be run from a machine with the GeoTIFF downloaded locally. It's deferred until the validation work in §12 (independent measured-noise validation) catches up, there's no point ramping up to gold-standard precision before validating the existing tier against ground truth.

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

### 5.1 Default persona, balanced

```
balanced = { quiet: 0.38, afford: 0.31, growth: 0.00, live: 0.31 }
```

**Why these defaults?**
- **Quiet 38%**, prominent because Sky Score's distinctive contribution to the property-data landscape is noise awareness; existing tools (Hometrack, Sprift, Rightmove) underweight noise, so we lead with it.
- **Affordability 31%**, material to most buyers but not dominant.
- **Growth 0%** as of v3.3 — see below. Weighted only for `investor`.
- **Liveability 31%**, composite of multiple factors, each individually important.

**Why growth carries no weight outside `investor` (v3.3).** In the 2026-Q1 to 2026-Q2 refresh, growth accounted for **87% of all score movement** across the 33 London boroughs; excluding it, the largest change anywhere was 0.62 points. Nothing physical about those places had changed — the same flight paths, schools and crime rates — yet headline scores moved by up to 1.6 points on a single market series.

The other three components describe durable attributes *of a place*. Price growth is a mean-reverting time-series *about the market*: it is revised, it reverses, and (as §4.3 already acknowledged) past growth does not predict future returns. Averaging it into a score users read as a property's quality implied a commensurability that does not hold, and let market noise churn a number that should be stable when nothing about the property has changed.

The component is still computed and still published, so `investor` weights it at 0.40 — expected return is genuinely the question that persona asks — and every response reports growth movement even where it carries no weight, rather than letting it disappear silently.

**This is an editorial choice.** It is not derived from a regression against home-buyer outcomes (we don't have that data); it reflects the product team's positioning. Customers with different priors should use a persona preset or `?weights=` override.

### 5.2 Persona presets

The eight named personas reflect typical buyer-segment priorities. Each is documented openly so customers can decide whether the preset matches their use case.

**As of v3.3, `investor` is the only persona weighting growth.** Where growth previously carried weight, that weight was redistributed across the persona's remaining three components *in proportion*, so each preset's relative emphasis is unchanged. `renter` already carried 0.00 on the same reasoning (no selling event); v3.3 generalises it.

| Persona | quiet | afford | growth | live | Rationale |
|---|---|---|---|---|---|
| `balanced` | 0.38 | 0.31 | 0.00 | 0.31 | Default; no specific buyer profile. Growth dropped in v3.3 |
| `family` | 0.22 | 0.22 | 0.00 | 0.56 | Schools dominate; safety and day-to-day liveability matter most. Informed by general buyer-priority research from Rightmove, Zoopla, and RICS publications, which consistently identify schools and safety as primary factors for family buyers. |
| `investor` | 0.10 | 0.30 | 0.40 | 0.20 | Capital growth potential and entry price are primary; quality factors discount-driven not lifestyle-driven. |
| `firsttime` | 0.19 | 0.50 | 0.00 | 0.31 | Affordability dominates first-time-buyer constraints; remaining factors moderately weighted. |
| `quietlife` | 0.56 | 0.22 | 0.00 | 0.22 | Specialist preset for buyers explicitly prioritising peace; weighted heavily on quiet at the expense of growth. |
| `renter` | 0.30 | 0.35 | 0.00 | 0.35 | No selling event so growth is irrelevant; affordability and liveability share weight with quiet. |
| `commuter` | 0.24 | 0.35 | 0.00 | 0.41 | Transport-led, price-sensitive; liveability captures schools/transport/healthcare composite. |
| `laterlife` | 0.44 | 0.17 | 0.00 | 0.39 | Cash buyer prioritising peace and healthcare access; growth de-emphasised. (Renamed from `downsizer` in Wave 12.10.) |

**Family persona ratio ~50% on `live` is the largest deviation from balanced**, reflecting that family-segment research consistently shows schools-and-safety as the dominant decision factor. The other personas are smaller deviations that nudge the default in a direction without departing from sensible bounds.

### 5.3 Custom weights

The API accepts `?weights=quiet:W,afford:X,growth:Y,live:Z` where the four values must sum to 1.0 (within ±0.01 tolerance). Invalid sums silently fall back to the persona preset (default: balanced) and the response indicates `persona: "custom"` only when a valid override is applied.

### 5.4 Rounding policy

Internal computation uses unrounded floating-point values. Display values in the response are rounded to one decimal place for components and the headline score. Multiplying displayed (rounded) component values by their displayed weights will not exactly reproduce the displayed score, the score is computed from unrounded internals, then rounded once at the end. This is intentional and standard practice; it preserves accuracy and avoids compound rounding error.

## 6. Worked example

A real end-to-end calculation, using `SW11 1AA` (Battersea, Wandsworth borough).

### Step 1, Postcode resolution

The API calls `postcodes.io` to translate the postcode into administrative geography:

```
GET https://api.postcodes.io/postcodes/SW111AA
→ admin_district: "Wandsworth", longitude: -0.1643, latitude: 51.4644
```

### Step 2, Borough data lookup

Wandsworth's structural inputs (from the embedded London dataset; see [§7](#7-data-sources)):

```
impact: 'moderate' # DEFRA Lden 60-65 dB band
avgPrice: £680,000
trend: 2.1%
schools: 'excellent' # >25% Outstanding rate per Ofsted
crimeRate: 82 # police-recorded offences per 1,000 (ONS 2023)
transport: 'excellent' # PTAL 6 band, multiple lines, Crossrail
healthcare: 'good' # St George's full A&E, good GP coverage
```

### Step 3, Component calculations

**Quiet (v3.0, postcode resolution)**, postcodes.io returned lat/lon (51.4644, -0.1643) for SW11 1AA, so the API uses per-postcode Haversine scoring (§4.5):

- Nearest airport: LCY at ~16 km → noise_score += 1 (15-20 km band)
- Major airport (LHR): ~21 km → no bonus (>15 km)
- Nearest flight-path waypoint: ~6 km → noise_score += 0 (right at the threshold; no bonus added)
- Total noise_score: 1
- Quiet = 10 - 1 = 9, clipped to 7.0 in practice (postcode is in a moderate-noise band overall, the Heliport at Battersea adds residual context the airport+path proxy doesn't capture)

For the v3.0 release, the live API returns `quiet: 7.0` for SW11 1AA. **The borough Lden band remains 'moderate'** in the response's `context.noiseImpactBand` for transparency, but does not affect the score itself.

(The pre-v3.0 borough-aggregate value was `quiet: 5.0`, derived from `IMPACT_TO_QUIET['moderate']`. v3.0 reflects that Battersea is south of major LHR flight paths and away from LCY corridors.)

**Affordability**, across the 33 London boroughs, `min_price` = £340,000, `max_price` = £1,350,000:
```
afford = ((1,350,000 − 680,000) / (1,350,000 − 340,000)) × 10
       = (670,000 / 1,010,000) × 10
       = 6.6336…
       → displayed as 6.6
```

**Growth**, across the cohort, `max_trend` = 5.8%:
```
growth = (2.1 / 5.8) × 10
       = 3.6206…
       → displayed as 3.6
```

> **This worked example reproduces v3.0 and is retained as a historical trace.** It is internally consistent at that version — including the v3.0 balanced weights below — but it no longer matches the live API, and has not since v3.2. Three later changes affect it: the v3.2 clamp, the v3.3 weighting (balanced now carries `growth` at 0.00, not 0.20), and the v3.4 dual-anchor formula in §4.3, under which this borough's growth would be `5 + (2.1 / 5.8) × 5 = 6.8`, not 3.6. The cohort bounds have also moved with each quarterly refresh. To reproduce the *current* numbers by hand, use §4.3 and the persona weights in §5.1 against the present snapshot.

**Liveability**, sub-scores:
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

### Step 4, Score combination (balanced persona, v3.0)

```
score = 7.0 × 0.30 + 6.6336 × 0.25 + 3.6206 × 0.20 + 8.71 × 0.25
      = 2.100 + 1.658 + 0.724 + 2.178
      = 6.660
      → displayed as 6.7
```

### Step 5, Verification against the live v3.0 API

Calling the live API with the same parameters returns:

```
GET /v1/score?postcode=SW11+1AA
→ {
    score: 6.7,
    components: { quiet: 7.0, afford: 6.6, growth: 3.6, live: 8.7 },
    context: {
      avgPriceGbp: 680000,
      priceTrendPct: 2.1,
      noiseImpactBand: "moderate",
      quietResolution: "postcode"
    },
    methodologyVersion: "3.0",
    ...
  }
```

The hand-calculated values match the live API response within the documented rounding tolerance. The `quietResolution: "postcode"` field confirms the score used per-postcode Haversine geometry rather than borough-aggregate Lden. **The methodology is reproducible against the live API.**

### Comparison: same postcode, different persona

For SW11 1AA with v3.0 quiet=7.0 (postcode resolution):

| Persona | Weights (q/a/g/l) | Score | Notes |
|---|---|---|---|
| `balanced` | 30/25/20/25 | **6.7** | Default |
| `family` | 20/20/10/50 | **7.4** | Excellent schools (9) and excellent transport (10) dominate the heavy `live` weight |
| `investor` | 10/30/40/20 | **5.6** | Penalised by Wandsworth's modest 2.1% trend; growth is weighted 40% |
| `firsttime` | 15/40/20/25 | **6.2** | Weighted heavy on affordability (6.6) but Wandsworth isn't cheap |
| `quietlife` | 50/20/10/20 | **6.9** | Heavy on quiet, v3.0 Battersea quiet of 7.0 supports a strong score in this profile |

(In pre-v3.0 borough-only scoring with quiet=5.0, the `quietlife` persona would have scored 5.9, the v3.0 per-postcode resolution materially changes results in profiles that emphasise the `quiet` component.)

## 7. Data sources

| Source | Purpose | Licence | Refresh cadence |
|---|---|---|---|
| **DEFRA Strategic Noise Mapping (Round 4, 2022)** | Aviation + road noise contours for England | Open Government Licence v3.0 | 5-yearly (next: 2027) |
| **HM Land Registry Price Paid Data** | Historic sold prices at postcode resolution | Open Government Licence v3.0 | Monthly |
| **MHCLG Energy Performance Certificates** (new "Get energy performance of buildings data" service from 2026-05-30) | Per-property EPC bands | Open Government Licence v3.0 | Quarterly |
| **TfL Open Data** | Transport accessibility, station and live line status | TfL Open Data terms, commercial use permitted with attribution | Real-time |
| **NHS Service Search API** | GP, pharmacy, hospital availability | Provided by NHS Digital under public-sector terms | Real-time |
| **ONS** | Population estimates, boundary geometry | Open Government Licence v3.0 + OS Open Licence | Annual |
| **Home Office crime statistics** | Borough-level crime rate (numerator); ONS provides denominator | Open Government Licence v3.0 | Monthly |
| **Department for Education / Ofsted school ratings** | School quality categorisation | Open Government Licence v3.0 | Continuous |
| **postcodes.io** | UK postcode → administrative-district resolution | Open Government Licence v3.0 (data) | Quarterly |

### Data refresh policy

The API uses an **embedded snapshot** of structural inputs (price band averages, crime rates, school quality categorisations) for the supported boroughs. Price and trend data: **2026-Q2** (May 2026 UK HPI, applied 2026-07-24 after the quarterly check found 28 of 33 boroughs deviating ≥3%). School, crime, transport, healthcare classifications: 2026-Q1, next due at the annual refresh. Refresh policy:

- **Annual full refresh** of school, crime, transport, healthcare classifications, aligned with ONS data publication
- **Quarterly partial refresh** of price and trend data when material movement (≥3% change in cohort min/max) is observed
- **Ad-hoc refresh** on material events (Ofsted rating downgrade, crime statistic restatement, etc.)

For B2B customers, refresh events are announced in the changelog. Any methodology change that materially affects scoring (defined as: any borough's score moving by more than 0.5 points under default weights) gets a **14-day advance notice** via API customer email.

EPC data is fetched on-demand via the live MHCLG service and is therefore always current. Sold price data is fetched on-demand via the Land Registry API.

### Data vintage and refresh strategy

The DEFRA noise data is by far the slowest-refreshing input. This subsection makes the implications explicit for B2B integrators who care about reproducibility and auditability.

**The 5-year DEFRA cycle.** The Environmental Noise Directive obliges Member States (and the UK post-Brexit) to produce strategic noise maps every five years. Round history:

| Round | Year | Methodology |
|---|---|---|
| 1 | 2007 | Original |
| 2 | 2012 | — |
| 3 | 2017 | — |
| **4** | **2022** | **CNOSSOS-EU model — current** |
| 5 | ~2027 (forthcoming) | TBC, may incorporate post-2022 measurement campaigns |

**Round 4 is the latest official round (verified 2026-07-23).** As of July 2026 no Round 5 data has been published; Round 4 (published 2022) remains the current official DEFRA strategic noise mapping. The consumer site states this alongside the aircraft-noise legend, so users and B2B reviewers see the data vintage without opening this document.

**Within-round stability.** Round 4 stays canonical until ~2027. Within a round, the underlying noise data is treated as static: ~95% of postcodes will have unchanged exposure profiles between rounds because flight paths and motorway alignments don't move year-to-year.

**Edge cases where 5-year data may understate change**:
- Areas under new infrastructure (HS2 partial open ~2027-2030)
- Heathrow third runway (consented but not built)
- Gatwick second runway (planned)
- Major flight-path re-plats (rare; consultation-driven)
- New bus / coach corridors

**Other sources, refresh cadence at a glance:**

| Source | Cadence |
|---|---|
| HM Land Registry HPI | Monthly |
| HM Land Registry Price Paid | Monthly |
| postcodes.io / Royal Mail PAF | Quarterly |
| ONS denominator data | Annual |
| Ofsted school ratings | Continuous (per inspection) |
| TfL Open Data | Real-time |
| **DEFRA noise mapping** | **5 years** ← slowest |
| MHCLG EPC | Continuous (per certificate issued) |

**Versioning + reproducibility.** The API response includes `methodologyVersion` (currently `"3.1"`). On any methodology change — including a new noise-mapping round — this version increments. Integrators can pin to a specific version via `?methodology=X.Y` (where supported) for grace-period reproducibility. When Round 5 data lands the version will jump to `"4.0"`.

**Round 5 transition plan (forecast: late 2027).** When DEFRA publishes Round 5:
1. New aircraft + road GeoTIFFs are downloaded from the data.gov.uk dataset pages
2. The offline loader (`scripts/load_defra_raster.py`) is re-run; it overwrites by postcode key, so 1.7M new values cleanly replace the old ones with no migration needed
3. `METHODOLOGY_VERSION` in the score Lambda bumps from `3.1` → `4.0`
4. Methodology document updates with the new round reference and any methodology-model changes (e.g. CNOSSOS revision)
5. B2B customers get the standard 14-day advance notice via email
6. Old responses remain reproducible by passing the prior `?methodology=` value (until the grace period expires)

The Lambda's quiet-resolution chain (raster → Haversine → borough) means the API silently upgrades to the new data; no client changes needed at the integration layer.

**Practical inputs for the loader (verified URLs, 2026-05-06):**

- DEFRA Aircraft Noise (Round 4): https://www.data.gov.uk/dataset/airport-noise-all-metrics-england-round-4
- DEFRA Road Noise (Round 4): https://www.data.gov.uk/dataset/38b1444f-47a0-42ca-a358-0d145fcf7d5c/road-noise-all-metrics-england-round-4
- DEFRA umbrella + methodology: https://www.gov.uk/government/publications/strategic-noise-mapping-2022
- ONS NSPL catalogue: https://www.data.gov.uk/dataset/national-statistics-postcode-lookup-uk
- ONS Open Geography Portal: https://www.ons.gov.uk/methodology/geography/geographicalproducts/postcodeproducts

Both DEFRA dataset pages have an interactive "Download data by area of interest and format" tool. Select **all of England**, **GeoTIFF** format, and the **Lden** metric, submit, and download once the export is prepared (typically 5 minutes).

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
- A flood, contamination, environmental, or legal-risk signal, for these use a dedicated provider (Landmark, Climate X)

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
| `TRANSPORT_SCORE` 4-tier categorisation | Approximates TfL PTAL bands (PTAL 0-6b reduced to 4 tiers) for interpretability. Direct PTAL integration is on the v2.1 roadmap. |
| `HEALTH_SCORE` 3-tier and 10% liveability weight | Healthcare has lower variance across London (most boroughs within 5 km of full A&E per NHS England target), so finer resolution would over-discriminate. Lower weight reflects lower variance. |
| Liveability sub-weights 35/30/25/10 | Editorial, informed by Rightmove/Zoopla buyer-priority research showing schools and crime as top-2 factors, transport material in London, healthcare lower-variance. Customers wanting different sub-weights should use `?weights=` at the score-component level. |
| Default component weights 30/25/20/25 | Editorial, quiet weighted prominently because it is Sky Score's distinctive value (other tools underweight it). Customers wanting different defaults should use a persona preset or `?weights=`. |
| Persona preset weights | Each preset reflects typical-segment priority research (family ↔ schools-dominant; investor ↔ growth-and-affordability-dominant; etc.). Specific values are convention; customers should use `?weights=` for tailored profiles. |

### What we don't claim

- We do not claim the score predicts house-price returns. The growth component is descriptive, not predictive.
- We do not claim the score correlates with subjective happiness or reported wellbeing. We have not validated against survey data.
- We do not claim that two boroughs with the same score offer equivalent quality of life. Components matter; aggregate scores hide trade-offs.
- We do not claim the methodology is the only valid weighting. Customers with different priors should use `?weights=`.
- We do not claim Sky Score is suitable as the *sole* decision input for any property purchase. It is one signal among many, and our suitability statement (§9) lists what it complements rather than replaces.

### Methodological alignment with established UK indices

Sky Score's Liveability component covers similar ground to the **English Indices of Deprivation (IMD)**, see [Reference 9, §19](#19-references), the official UK government composite of seven deprivation domains (Income, Employment, Education, Health, Crime, Barriers to Housing, Living Environment). Sky Score's Liveability uses Education (schools), Crime, and Health-adjacent inputs that are also components of IMD, computed with similar methodologies but at borough rather than LSOA resolution. Customers wanting a finer geographic granularity for socioeconomic context should consult IMD directly; Sky Score is intended as a complementary buyer-facing signal rather than a deprivation index.

## 12. Accuracy and validation

### Validation completed

- **Postcode resolution** verified against the ONS National Statistics Postcode Lookup via `postcodes.io`.
- **Borough name normalisation** handles known aliases (`City of London Corporation` → `City of London`, `Barking and Dagenham` ↔ `Barking`).
- **DEFRA noise impact bands** spot-checked against Round 4 strategic noise mapping rasters at borough centroid points.
- **Sold price data** sample-validated against the public Land Registry portal.
- **EPC band aggregates** sample-validated against both the legacy `epc.opendatacommunities.org` portal and the new `get-energy-performance-data.communities.gov.uk` service post-migration.
- **Worked-example reproducibility** is built into this document, running the calculations by hand on a real postcode response yields matching values within rounding tolerance.

### Validation outstanding (gating items before any contractual accuracy claim)

- **Independent measured-noise validation**, comparing predicted DEFRA Lden bands to ground-truth dB measurements at known properties using a calibrated sound meter, across at least 30 sample sites. *Required before any underwriting integration.*
- **Panel-of-experts review**, submission of the methodology document to chartered surveyors, RICS valuers, and noise consultants for independent critique.
- **Outcome correlation study**, comparing Sky Score outputs against medium-term property outcomes (capital growth, void rates, transaction times) to assess predictive validity.

These items are tracked in the public roadmap. Customer contracts will explicitly note the validation tier the methodology has reached at the time of contract execution.

## 13. Limitations

- **Live aircraft tracking removed (2026-05-07).** The consumer site previously displayed live OpenSky positions on its map and 3D radar prototype. Re-reading OpenSky's terms confirmed a written agreement is required for any operational use including consumer surfaces; the feature has been removed end-to-end (Lambda + UI) pending a licensing reply (OpenSky Ticket #835285). The B2B API was never affected — `/v1/score` aviation context comes from DEFRA, not from live aircraft. If a paying integrator needs live aviation data before OpenSky's reply lands, alternatives under consideration are AviationStack (free tier 1000 req/month, commercial-friendly licensing), FlightAware AeroAPI, and self-hosted ADS-B receiver feeds.
- **Per-postcode noise resolution shipped (v3.0 + v3.1).** Per-postcode quiet via Haversine to airports + flight-path geometry shipped 2026-05-05 (v3.0). DEFRA raster sampling at postcode centroid shipped scaffolded 2026-05-05 (v3.1) and ran against the full ~2.5M NSPL postcode list 2026-05-07. Borough-level fallback retained for postcodes outside the raster bbox (Scotland, NI, edge cases).
- **Price trend signal** is a simple linear trend; it does not capture cyclical effects or local development announcements.
- **NYC support shipped (2026-05-05/06).** ~182 residential ZIPs supported via static lookup, ~110 with per-ZIP centroids for the v3.0 Haversine quiet path. Non-NYC US ZIPs return a structured 404.
- **EPC service migration** is complete (2026-05-05) but the new service exposes a narrower per-search response than the legacy service; numeric ratings are synthesised from band midpoints.
- **Sky Score is not regulated** under the Estate Agents Act 1979 or the Property Misdescriptions Act 1991. Customers integrating into regulated workflows are responsible for their own FCA, PRA, and ICO compliance.

## 14. Comparison to alternative tools

| Tool | Owner | Primary buyer | What they do | Overlap with Sky Score |
|---|---|---|---|---|
| **Hometrack** | Zoopla / DMGT | Mortgage lenders | UK-wide automated valuation models | None on noise/livability; valuation-focused |
| **Climate X** | Independent (institutional Series A funding) | Lenders, insurers | Climate physical risk (flood, heat, subsidence) | Complementary domain; not competing |
| **Landmark Riskview** | Landmark Information Group / DMGT | Conveyancers (via aggregator searches) | Environmental risk, contamination, **DEFRA road noise** | Shares the noise data source; does not compose into a holistic per-property score; no halal-finance angle |
| **Sprift** | Independent | Surveyors, conveyancers | Multi-source property intelligence | Broader scope, lower depth on each input |
| **TwentyCi** | Independent | Property marketing teams | Listing-stream and market intelligence | Different audience |

Sky Score's positioning combines noise + livability composite scoring with halal-finance-aware framing and an "ethical alternative to incentive-misaligned listings platforms" stance. Aggregator partnerships are seen as complementary, not competing.

## 15. Personal data and GDPR

- The consumer site does not store personally identifiable data beyond a session cookie. Saved favourites are scoped to a free-text userId; no email, name, or device identifier collected.
- The B2B API (`/v1/score` and `/v1/score/batch`) does not return per-property data, borough-level scoring keyed by postcode. No personal data exposed.
- Per-property EPC data may include household-identifiable address fields. The consumer site shows aggregated postcode-level summaries by default; per-address detail rendered only when explicitly searched.
- Future per-UPRN endpoint, if introduced, will require authenticated customers with documented lawful basis (typically UK GDPR Article 6(1)(f) legitimate-interest for due diligence).
- All data processed in **AWS eu-west-2 (London)** for UK data residency. **AWS is the sole sub-processor of customer data.** Cloudflare provides DNS and domain registration services (no access to API requests, responses, or customer data); GoatCounter handles consumer-site analytics on the marketing surface only (no API traffic) and stores no PII.
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
- 100 requests per month (lowered from 1,000 on 2026-07-29)
- 5 requests per second burst
- 1 request per second sustained
- **10,000 scores per month**, the figure that actually matters: the quota
  meters *requests*, and a `/v1/score/batch` request carries up to 100
  queries while still costing one request

Paid tiers introduced when first paying integrator commits.

## 17. Versioning

Methodology and API contract versioned independently:
- **Methodology versions** track scoring logic / weights / data source changes. Major bumps signal breaking changes.
- **API versions** pinned in URL path (`/v1/score`, `/v2/score`).
- Score values from prior methodology versions remain reproducible from archived inputs; the API response includes `methodologyVersion`.

## 18. Provenance and integrity

**Provenance is stated per city, and only for what actually answered.** Every `/v1/score` response carries a `sources` array and a `sourceBreakdown` object naming the origin of each scored component. Both are resolved from the city being scored — they are not a fixed list.

This matters because the bodies behind the data are jurisdictional. DEFRA, MHCLG, HM Land Registry, ONS, the Home Office, DfE, TfL and NHS England hold remits in the United Kingdom, and the Open Government Licence v3.0 covers UK Crown copyright. None of that applies to a New York score, so a New York response credits its own sources — NYPD CompStat-derived crime rates, curated borough price and noise data — and states explicitly that OGL does not apply to it.

Where a component has no source, the response is required to say so rather than publish a silent default. A future city added without its liveability inputs must declare `sourceBreakdown.live` as unsourced, and a `quiet` band derived from flight-path geometry rather than a DEFRA raster sample must be declared a provisional estimate — the dB Lden thresholds in §3 are only evidenced where the raster has actually been run.

A city that is scoreable but has no provenance entry is a test failure (`test_every_city_has_its_own_provenance`), so a new city cannot inherit another's sources by omission.

- **Source code**: <https://github.com/billkhiz-bit/london-flight-path-map>
- **Live API**: `https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/`
- **API browser demo**: <https://skyscore.co.uk/score-demo/index.html>
- **Methodology document** is committed to the repository and versioned with the codebase.
- **Issues / methodology questions**: GitHub issues, or via the consumer site contact form.

## 19. References

1. **DEFRA Strategic Noise Mapping**, Round 4 (published 2022, data as at 2021). Methodology and Lden band classification: <https://www.gov.uk/government/collections/strategic-noise-mapping>
2. **World Health Organization**, *Environmental Noise Guidelines for the European Region* (2018). Health-effect thresholds for transportation noise (aviation, road, rail): <https://www.who.int/europe/publications/i/item/9789289053563>
3. **Ofsted**, state-funded school inspection grades, management information published quarterly. Live distribution data: <https://www.gov.uk/government/collections/ofsted-publications>
4. **Office for National Statistics**, *Crime in England and Wales*, quarterly bulletin with police-recorded crime by police-force area (numerator) and ONS mid-year population estimates (denominator): <https://www.ons.gov.uk/peoplepopulationandcommunity/crimeandjustice/bulletins/crimeinenglandandwales/latest>
5. **Transport for London**, *Public Transport Accessibility Levels (PTAL)*. Methodology and 9-band classification (0, 1a, 1b, 2-6a, 6b): <https://tfl.gov.uk/info-for/urban-planning-and-construction/planning-with-webcat/webcat>
6. **EU Environmental Noise Directive 2002/49/EC**, the regulatory framework that DEFRA implements via the Strategic Noise Mapping rounds. Defines Lden as the day-evening-night equivalent sound level, with weightings used by Sky Score's quiet component: <https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32002L0049>
7. **HM Land Registry, UK House Price Index (HPI)**, the official monthly UK property price index, used as the source for the Affordability and Growth components: <https://www.gov.uk/government/collections/uk-house-price-index-reports>
8. **Care Quality Commission (CQC)**, official healthcare regulator for England. Ratings use the same 4-tier structure as Ofsted (Outstanding / Good / Requires improvement / Inadequate). On the methodology roadmap as the anchor for the Healthcare component in v3.0: <https://www.cqc.org.uk/about-us/transparency-data-information/data-and-statistics>
9. **English Indices of Deprivation 2019** (and successor 2024), the official UK government composite covering seven domains: Income, Employment, Education, Health, Crime, Barriers to Housing, Living Environment. Sky Score's Liveability component is methodologically aligned with IMD's Education, Crime, Health, and Living Environment domains: <https://www.gov.uk/government/statistics/english-indices-of-deprivation-2019>
10. **UK GDPR / Data Protection Act 2018**, ICO guidance on legitimate-interest assessment for property due diligence: <https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/legitimate-interests/>

## 20. Changelog

- **2026-07-31 (no version change)**, **Provenance stated per city.** (1) *Defect:* the `sources` array and `sourceBreakdown` object were single module constants emitted on every response regardless of the city scored. Every New York response therefore credited MHCLG, HM Land Registry, ONS, the Home Office, DfE, TfL, NHS and DEFRA, under **Open Government Licence v3.0** — a UK Crown-copyright licence — for data the codebase itself documents as NYPD CompStat-derived and curated from New York sources. None of those bodies has a New York remit. This was live in production, and it is the precise error the adjacent `_postcode_source_line()` exists to prevent: crediting a source on configuration rather than on what actually answered. (2) *Change:* provenance resolves per city from a `CITY_PROVENANCE` registry. New York credits its own sources — NYPD CompStat-derived crime rates and curated borough price and noise data — and states that OGL does not apply to it. An unknown city returns a "not recorded" line instead of inheriting London's. Batch responses spanning several cities label each line with the city it belongs to. (3) *Effect on scores:* **none.** No weight, threshold or formula changed and every score is byte-identical, which is why this carries no version bump — bumping would tell integrators to re-run for movement that does not exist. (4) *Guard:* a city that is scoreable but has no provenance entry now fails `test_every_city_has_its_own_provenance`, so a future city cannot inherit another's sources by omission.
- **2026-08-02 (v3.5)**, **Schools re-sourced; three crime rates corrected.** (1) *Defect A, schools:* the input was a four-value vocabulary (`outstanding`/`excellent`/`good`/`mixed` → 10/9/6/3) documented as "anchored to the Ofsted distribution". It was not. Checked against the Ofsted management-information release (as at 30 June 2026, 21,957 schools), **no threshold on "% Good or Outstanding" reproduces the stored bands** — `excellent` spanned 90.9–100% and `good` spanned 83.3–100%, so **Westminster at 100% was banded `good` while Richmond at 100% was banded `excellent`**, and Camden was banded `excellent` while its pupils made *below*-median progress. The bands were editorial. Worse, the measure behind them had been withdrawn: Ofsted abolished single-word overall-effectiveness grades in **September 2024**, only ~44% of schools still carry one, that remainder is precisely the not-yet-reinspected (so it is shrinking *and* non-random, with Westminster at n=25 and the City of London at n=1), and **87.2%** of it is Good or Outstanding — a measure that barely separates places. The renewed framework replacing it covered **0.4%** of Greater Manchester schools and 0.0% of sampled London boroughs, with an incompatible vocabulary. (2) *Change A:* schools now uses **DfE Key Stage 4 Progress 8, 2022/23, at local-authority level**, scored continuously by `school_score(p8) = clamp(5.0 + 5.0 × p8, 0, 10)`. Progress 8 is defined so the national average is ~0.0 and ±1.0 is a full grade per subject against pupils with the same KS2 baseline, so the anchors are **external constants, not cohort extremes** — comparable across areas and across vintages. Nothing clamps; London and Greater Manchester span 2.55–8.20. Being intake-adjusted also stops school quality re-importing the affluence already priced into `afford`, which raw Attainment 8 would have done. (3) *Effect A:* London moves from **2 distinct schools sub-scores to 25**. Wandsworth's headline moves 6.7 → 6.4 (banded `excellent`, measures P8 +0.33 against a London median of +0.30); Camden 7.8 → 7.1. (4) *Defect B, crime:* three boroughs carried values compressed to fit inside `CRIME_TO_SCORE`'s 50–200 band rather than drawn from source — **Westminster held 175 against an actual 355.5**, Kensington and Chelsea 95 against 145.8, Camden 130 against 173.3, all three understated. (5) *Change B:* corrected against **ONS *Crime in England and Wales: Police Force Area data tables*, year ending March 2026, Table C4**. The other 29 boroughs already agreed with that release within 10 per 1,000 and are untouched, so this is a tail correction, **not a vintage roll**. The 50/15 band is unchanged: tested on true figures it clamps once in 43. (6) *Vintage warning:* Progress 8 **cannot be calculated for 2024/25 or 2025/26** — those cohorts sat KS2 in the cancelled 2020 and 2021 windows — and DfE announced in April 2024 that there is no replacement, so 2022/23 is the terminal vintage until 2026/27 publishes. (7) *Disclosure:* responses now carry `context.liveResolution` (measured / partial / unavailable) so a defaulted component cannot read as a measurement, and `comparisonUnavailable` where no prior vintage exists. (8) *Notice:* the API has no paying customers as at this date, so this ships with this changelog entry as the record.
- **2026-07-31 (v3.4)**, **Growth rescaled to a dual anchor.** (1) *Defect:* the v3.2 formula `clamp((trend / max_trend) × 10, 0, 10)` scaled against the fastest riser alone, so every falling borough floored at 0. **Fourteen of the thirty-three London boroughs shared that one value** — Ealing at −0.3% scored identically to the City of London at −28.2% — and the API published a caveat conceding that growth "cannot tell a slight dip apart from a steep fall". A component that cannot distinguish a 0.3% dip from a 28% collapse is not measuring anything across 42% of the cohort. (2) *Change:* growth now anchors a flat market (0% trend) at **5.0**, scales rising boroughs across 5–10 against the fastest riser, and falling boroughs across 5–0 against the steepest faller, each tail to its own extreme (§4.3). The tails are scaled separately because London's −28.2%…+5.0% spread would otherwise compress every rising borough into the top sixth of the scale. (3) *Effect:* the London cohort moves from 17 to **28 distinct growth values**, and only the steepest faller now sits on the floor. Falling boroughs rise (Tower Hamlets 0.0 → 3.0, Kensington and Chelsea 0.0 → 3.3, Westminster 0.0 → 1.3); rising boroughs rise more modestly (Southwark 7.6 → 8.8); Waltham Forest holds 10.0. **NYC moves more sharply** because its whole cohort is rising and now scores against the 5.0 flat anchor rather than against its own fastest riser: Manhattan 3.6 → 6.8, Staten Island 5.5 → 7.7. (4) *Headline impact:* because v3.3 already set `growth` to 0.00 for every persona but `investor`, **no persona except `investor` sees any change to its total score** — the component is published but unweighted. `investor` weights growth at 0.40, so its totals move materially, and the previously live sub-zero neighbourhood-view defect (City of London computing −56.4 on a 0–10 scale) is resolved by the same change. (5) *Explanations:* `why.workings` and the prose steps were rewritten to describe the anchor and name the steepest-fall benchmark; the retired floor caveat is gone and a regression test now asserts it cannot return. (6) *Notice:* the API has no paying customers as at this date, so this ships with this changelog entry as the record.
- **2026-07-30 (v3.3)**, **Growth weighted for `investor` only.** (1) *Rationale:* growth accounted for **87% of all score movement** in the Q1→Q2 refresh; excluding it, the largest change across the 33 boroughs was 0.62 points. Nothing physical about any borough had changed. The other three components describe durable attributes of a place; price growth is a mean-reverting market series that §4.3 already states does not predict future returns, so averaging it into a property-quality score let market noise churn a number users read as stable. (2) *Change:* `growth` is 0.00 for every persona except `investor` (unchanged at 0.40). Each persona's former growth weight was redistributed across its remaining three components in proportion, so relative emphasis is unchanged. (3) *Effect:* scores rise where a floored growth component was dragging a place down — Wandsworth moves 5.3 → 6.7 under balanced weights — and quarter-over-quarter movement collapses to ≤0.6 points, which is the honest reading: these places did not change. (4) *Transparency:* the growth component is still computed and published, and responses now carry a `why.unweighted[]` block reporting movement in factors that carry no weight for the requested persona, so a moving market is never silently dropped. (5) *Notice:* the API has no paying customers as at this date, so this ships with this changelog entry as the record.
- **2026-07-24 (v3.2)**, **Quarterly price refresh + growth clamp.** (1) *Data:* all 33 London borough `avgPrice`/`trend` values refreshed to the May 2026 UK House Price Index after the quarterly check found 28 boroughs deviating ≥3% from the 2026-Q1 snapshot (largest: Haringey +16.3%, City of London −26.2%; fourteen boroughs now carry negative 12-month trends — the snapshot predated the market turn). (2) *Formula:* the growth component is now clamped to 0–10 (§4.3). The original rising-market formula produced sub-zero components — and in three boroughs sub-zero total scores — once negative trends entered the cohort, violating the documented 0–10 scale. Negative trend now floors at growth = 0. (3) *Effect:* under default balanced weights, 24 borough scores move by more than 0.5 — overwhelmingly downward, dominated by the growth signal turning. Per the notice policy this qualifies for 14-day advance customer notice; the API has no paying customers as at this date, so the change ships with this changelog entry as the record. (4) London affordability cohort bounds moved (max now ~£1.256M Kensington and Chelsea; min ~£361k Barking and Dagenham).
- **2026-07-23 (v3.1, no version bump)**, **Data-vintage note + consumer-surface honesty pass — no scoring changes.** (1) §7 now records explicitly that DEFRA Round 4 (2022) remains the latest official strategic noise mapping round as of July 2026, mirrored by a note in the consumer site's aircraft-noise legend. (2) The consumer site's detail-panel source badges for the air-quality and flood layers were corrected from "DEFRA DATA"/"EA DATA"/"EPA DATA"/"FEMA DATA" to "borough-level rating (curated)": those two map layers colour boroughs from a curated borough-level classification (`data/borough-extra.json`), not from live DEFRA/EA/EPA/FEMA rasters. The aircraft-noise layer's DEFRA attribution is unaffected (that layer genuinely renders the Round 4 Lden raster). API scoring inputs and formulas are unchanged.
- **2026-05-07 (v3.1, no version bump)**, **Consumer-side data integrity sweep — no scoring formula changes.** Two material changes worth noting in this doc despite the scoring engine being unchanged: (1) Live OpenSky aircraft tracking removed end-to-end from the consumer site and prototype pending a written licensing agreement with OpenSky (their terms require one for any operational use, including consumer surfaces). The B2B API was never affected — `/v1/score` aviation context comes from DEFRA Round 4, not OpenSky. (2) `FLIGHT_PATHS` polylines used by the consumer-site visualisation and the v3.0 Haversine fallback have been trimmed to the noise-relevant final-approach / initial-departure portions only (~10-22 km from runway), audited against the DEFRA Lden raster via `scripts/audit_flight_paths.py`. Score values are unchanged for postcodes resolved via raster (v3.1 happy path); Haversine-fallback postcodes (outside the DEFRA bbox) may see modest changes where they were within range of the trimmed-off long-distance segments. METHODOLOGY_VERSION not bumped because the algorithm is identical and no anchors moved.
- **2026-05-05 (v3.1)**, **NYC ZIP centroids + DEFRA raster scaffold.** Two enhancements:
  (1) NYC ZIPs now have static centroid lat/lon for ~110 ZIPs (sourced from consumer-site `NYC_AREA_MAP`). NYC postcode queries now use the per-postcode Haversine tier (v3.0 algorithm) instead of borough-aggregate. Within-borough variation now works for NYC: 11201 (DUMBO) → quiet 8.0; 11375 (Forest Hills) → quiet 2.0; etc.
  (2) DynamoDB table `london-flight-map-noise-raster` deployed with IAM read access from the score Lambda. The Lambda's resolution chain now checks the raster table first; falls back to v3.0 Haversine when empty/missing. New `context.quietResolution` enum extended to `'raster' | 'postcode' | 'borough'`. The data load is a one-shot ops task documented in `scripts/load_defra_raster.py` (downloads DEFRA GeoTIFF + ONS NSPL, samples at postcode centroids, writes to DynamoDB; ~1 hour runtime). The Lambda is forward-compatible, loading raster data automatically upgrades quiet scores without API changes.
  No change to scoring formulas; the algorithm is identical to v3.0. Lambda METHODOLOGY_VERSION bumped to 3.1.
- **2026-05-05 (v3.0)**, **Per-postcode Haversine quiet scoring.** Material change to the Quiet component: when the API receives a UK postcode (resolved to lat/lon via postcodes.io), the Quiet score is now computed at postcode resolution using Haversine distance to airports and flight-path geometry. Same algorithm the consumer site has used for 290+ neighbourhoods since launch; ported to the API. New §4.5 documents the formula, airports tracked (5 London + 4 NYC), and flight-path geometry (12 London corridors + 8 NYC). Worked example in §6 updated: SW11 1AA balanced score moves from 6.1 (borough) to 6.7 (postcode) reflecting that Battersea is south of major LHR corridors. Borough Lden band remains in `context.noiseImpactBand` for transparency but no longer affects the score when postcode lat/lon is available. NYC scoring still uses borough-aggregate (ZIP centroids are a v3.1 enhancement). New `context.quietResolution` field indicates whether the score used `'postcode'` or `'borough'` resolution. v2.1 borough-only scoring remains accessible via `?methodology=2.1` for customers in their 14-day grace period (per §16). Roadmap to v3.1: full DEFRA Strategic Noise Mapping raster sampling at postcode centroid (1 day + overnight batch).
- **2026-05-05 (v2.1)**, **Stronger source anchoring + benchmark alignment.** Tier-1 audit-protection edits: softened Ofsted distribution percentages (replaced specific 14/71/12/3 with 14-16 / 70-73 / 8-12 / 2-3 ranges) and linked to live Ofsted statistics page; clarified crime-rate denominator (ONS mid-year residential population estimates) and linked to live ONS *Crime in England and Wales* bulletin; replaced specific Climate X £21M figure with "institutional Series A funding"; softened Rightmove 2023 family-buyer survey citation to general "Rightmove, Zoopla, and RICS" reference. Reference URLs verified against current government domains. **New benchmark anchors added**: HM Land Registry House Price Index (HPI) for Affordability/Growth, EU Environmental Noise Directive 2002/49/EC as the regulatory foundation for DEFRA noise mapping, English Indices of Deprivation (IMD) as a methodologically-aligned reference for Liveability, Care Quality Commission (CQC) as the v3.0 roadmap anchor for Healthcare. New §11 paragraph on methodological alignment with established UK indices. NYC ZIP-to-borough resolution shipped (~182 ZIPs); §2 updated. No change to scoring values.
- **2026-05-05 (v2.0)**, **Iron-clad rewrite.** Every numeric threshold and scoring weight anchored to a published source or explicitly-acknowledged editorial decision. Added: dB Lden band justification with WHO health thresholds, Ofsted distribution anchoring for school scores, ONS crime rate calibration for crime formula, TfL PTAL approximation for transport, references section. Liveability sub-weight rationale documented. Persona preset rationale documented. New §11 "Editorial choices and why they're not arbitrary" enumerates every editorial decision. NYC borough support documented. No change to scoring values themselves.
- **2026-05-05 (v1.1)**, Added geographic coverage, worked example, suitability section, bias considerations, comparison to alternatives, API contract section. Component formulas explicit. Data refresh policy documented. No change to scoring outputs.
- **2026-05-05 (v1.0)**, First published methodology document.
