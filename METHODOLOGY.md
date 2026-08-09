# Sky Score Methodology

> Version 3.5, last updated 2026-08-03.
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
- 10 Greater Manchester metropolitan boroughs, **borough-name lookup only** — postcode resolution is London-only, because `resolve_query()` gates it there *and* the NSPL loader writes the borough attribute for London local authorities alone. Two separate blockers, not one.

**Sub-borough granularity differs by city, and the consumer-site ranking says
so per city.** London and New York rank *named areas* whose median prices are
indicative and whose crime figure is a relative modifier rather than a measured
rate. Greater Manchester ranks **85 postcode districts** whose price is the
**median of real HM Land Registry transactions** in that district (built by
`scripts/build_manchester_neighbourhoods.py`, minimum 30 sales or the district
is omitted rather than estimated) and which carry **no crime modifier at all**,
because sub-borough crime is not published for Greater Manchester. None of this
enters `/v1/score`, which is borough-level for all three cities.

**Coverage is not uniform, and every response says which inputs it rests on**
via `context.liveResolution`. Greater Manchester's
aircraft bands are **estimated from runway geometry, not sampled from the DEFRA
strategic noise maps** that cover London, and its liveability rests on 2 of the
4 inputs (see the table in §4.4.1) with the absent inputs' weight redistributed
rather than filled with a placeholder. Road noise, flood risk and air quality
have no Greater Manchester source and are not published for it.

**Planned:** the remaining UK Core Cities (Birmingham, Bristol, Leeds, Edinburgh, Glasgow, Liverpool, Newcastle, Sheffield, Cardiff, Belfast, Nottingham), then England + Wales.

**Postcode → borough resolution** uses `postcodes.io` for UK postcodes; NYC ZIPs use a static lookup table baked into the Lambda (sourced from NYC OpenData ZCTA boundaries + USPS). ZIPs without an explicit centroid fall back to the borough-aggregate Lden band for the quiet score; non-NYC US ZIPs (e.g. 90210) return a structured 404 with the supported borough list.

A request for a postcode outside the supported geography returns a 404 with a `supportedBoroughs` list so the caller can fall back gracefully.

## 3. Components

| Component | What it measures | Range |
|---|---|---|
| **Quiet** | **Aircraft noise only** — see the note below | 0-10 (10 = quietest) |
| **Affordability** | Average sold price relative to cohort | 0-10 (10 = cheapest in cohort) |
| **Growth** | Recent price-trend signal | 0-10 (10 = fastest riser, 5 = flat market, 0 = steepest faller) |
| **Liveability** | Schools, crime, transport, healthcare | 0-10 (10 = most liveable) |

Each component is bounded in 0-10 with floating-point precision internally and one-decimal display precision in the API response.

> **Correction, 2026-08-04: `quiet` measures aircraft noise only.** The row above read
> *"Aviation + road noise impact"*, and `README.md` said the same. **There is no road-noise term
> in the scoring engine** — `backend/lambdas/score/app.py` contains no road-noise code at all, and
> §4.1/§4.5 describe only aircraft sources (DEFRA aircraft Lden, distance to airports,
> flight-path geometry, heliports).
>
> The confusion has a real origin: DEFRA publishes aircraft **and** road contours, the loader
> script documents both datasets, and the consumer site renders a **road-noise map overlay** as a
> separate visual layer. None of that reaches the score. A buyer comparing this document against
> a competitor's road-noise product would have been misled about what the number contains, which
> matters more than a typical doc error because it is a claim about the headline component.
>
> Road noise remains a genuine candidate for a future version — the loader already documents the
> logarithmic dB sum for combining the two rasters — but it is **not implemented**, and this
> document will say so until it is.

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
| **10.0** | low | < 55 | **Below DEFRA's 55 dB mapping threshold — unmeasured, not verified quiet.** See the correction below |
| **7.5** | low-moderate | 55-60 | Below DEFRA "significantly affected" threshold; slight annoyance |
| **5.0** | moderate | 60-65 | Sleep disturbance becomes detectable in WHO meta-analyses |
| **3.0** | moderate-high | 65-70 | Significant annoyance; measurable cardiovascular risk increase |
| **1.5** | high | 70-75 | High annoyance; established cardiovascular and sleep effects |
| **0.0** | severe | ≥ 75 | DEFRA "important areas" action threshold; hearing impact possible |

The score values are spaced to reflect the inverse-square-ish relationship between noise dB and health effect, the gap from "moderate-high" (3.0) to "high" (1.5) is half the gap from "low" (10.0) to "low-moderate" (7.5), reflecting that small dB increases at high baselines have outsized health consequences.

> **Correction, 2026-08-03.** The `< 55` row previously read *"Below WHO health-impact threshold;
> not measurably affected"*. That contradicted this very section: WHO's strong recommendation for
> aircraft is **below 45 dB Lden** (verified against the publisher, not taken from this document),
> so a band spanning 45-55 dB is **above** the threshold it claimed to be below.
>
> **The bands themselves are not wrong and no score has changed.** DEFRA publishes strategic noise
> mapping only from 55 dB upward - its own bands, quoted above, begin at 55 - so **the 45-55 dB
> range is not measured by this source at all**. A borough in `low` may sit at 54 dB or at 30 dB;
> neither DEFRA nor Sky Score can tell you which, and inventing a boundary at 45 would assert a
> precision the data does not carry.
>
> So `low` means **"below the level at which DEFRA is required to map"**, which is a statement
> about the survey and not about the air. It is kept at 10.0 because the component measures
> aircraft noise *as mapped by DEFRA*, and by that measure these boroughs are at the floor;
> lowering it would replace an unevidenced reassurance with an unevidenced penalty. **13 of the 33
> London boroughs sit in this band.**
>
> Full working: [`BAND_MAPPING_ANALYSIS.md`](./BAND_MAPPING_ANALYSIS.md). Revisit if DEFRA Round 5
> (~2027) maps below 55 dB. **Unverified:** the 53 dB figure cited above is WHO's *road traffic*
> guideline; whether it is also the aircraft annoyance-onset threshold was not established and
> should be checked before it is relied on.

> **Correction to the correction, 2026-08-04. The table above now describes the borough tier
> only.** The 2026-08-03 note generalised one true statement into a false one. "The 45-55 dB range
> is not measured by this source at all" holds for **DEFRA's published borough band assignments**,
> which genuinely do not resolve below 55 — that part stands, and the borough mapping is unchanged.
>
> It does **not** hold for the **raster**. `data/defra_lden_2022.tif` was read directly on
> 2026-08-04: **2,359,172 valid cells spanning 40.0 to 88.9 dB**, and at London's live postcode
> centroids **40.0 to 73.0 dB, median 51.0**. There is no missing 45-55 dB range there —
> **13,166 London postcodes are measured inside it**. Applying this table to those samples put
> **80.4% of every measurement on a flat 10.0**, flattening a ~15 dB spread that is roughly a
> tripling of perceived loudness.
>
> The raster tier therefore no longer uses this table. It uses the continuous v3.6 curve in
> **§4.6**. Two rows here remain unreachable from raster data regardless: nothing in London reaches
> 75 dB, and only four postcodes reach 70.

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

**When a sub-score has no data (added 2026-08-09).** An absent input is not
filled with a placeholder. Its weight is redistributed across the sub-scores
that do exist, **in proportion**, so the remaining weights still sum to 1.0 and
their relative emphasis is unchanged. Dropping schools leaves crime at three
times healthcare exactly as declared above.

Below **two** of the four inputs, liveability is not published at all: `live` is
omitted from the response and the *component* weight is redistributed across
Quiet, Affordability and Growth by the same rule. One surviving sub-score scaled
to 1.0 would make `live` mean that one thing under a label promising four.

This replaced a fixed 5.0 fallback, which was not neutral. London's computed
liveability spans 5.5–8.4, so 5.0 sat below every real borough: a place with no
data scored worse than the worst place with data, and filling in one of four
fields could push a place *lower*. Redistribution removes both effects.

The mechanism follows the v3.3 growth decision in §5.1, which redistributed a
dropped component's weight across the others *in proportion* so that relative
emphasis was preserved and the weights still summed to 1.0. The circumstances
differ — §5.1 drops a component deliberately, this drops one for want of data —
but both refuse the same substitution: a component that is **not counted** must
never be rendered as a component **counted as poor**.

*Worked example.* City of London has no Progress 8 figure, because it has
effectively no state secondary provision. Its schools weight of 0.35 is spread
across the other three in proportion — crime 0.30/0.65, transport 0.25/0.65,
healthcare 0.10/0.65 — and its liveability is computed from what is actually
known about it. Its published `context.liveResolution` reports `partial`.

*Second worked example, and the reason this rule exists.* Greater Manchester
has schools and crime but no transport or healthcare — 2 of 4. Under the old
fallback its ten boroughs spanned 4.5–6.4, compressed toward 5.0 by two
invented inputs; under redistribution they span 4.3–7.2. Both figures describe
the same places. The difference is that one of them is partly a statement about
data we do not hold.

### 4.4.1 Which liveability inputs each city has

Not uniform, and the response says so per request via
`context.liveResolution`. Cross-city comparison of `live` should account for
this: a two-input composite is a narrower claim than a four-input one, even
though both are on 0–10.

| City | schools | crime | transport | healthcare | Resolution |
|---|---|---|---|---|---|
| London | Progress 8 | ONS Table C4 | curated | curated | `measured` (32 of 33; City of London is `partial`) |
| New York | curated tier | NYPD CompStat | curated | curated | `measured` |
| Greater Manchester | Progress 8 | ONS Table C4 | — | — | `partial — 2/4` |

Below **two** inputs the component is omitted entirely rather than published,
and `liveResolution` reads `unavailable`. This is why one measured input is
reported as `unavailable` rather than `partial`: `partial` would describe a
number the caller never receives.

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
and the effect was to understate them. They now carry the published figures.

**Corrected 2026-08-03.** This section previously continued: *"The other 29
boroughs already agreed with the release within 10 per 1,000 and were left
untouched, so v3.5 is a tail correction rather than a vintage roll."* That was
false. It rested on three spot checks — Richmond, Sutton and Enfield, all
genuinely correct — generalised to the cohort without enumeration. Compared
against every London row of the published workbook, **29 of the 33 boroughs
disagreed with the source they cited**, seven of them by more than 10 per 1,000:
Barking and Dagenham held 105 against 84.2, Hillingdon 72 against 91.6, Croydon
98 against 80.4, Tower Hamlets 120 against 106.6, Hammersmith and Fulham 96
against 107.0, Merton 70 against 59.3 and Harrow 70 against 59.5. Seventeen
boroughs carried a crime sub-score wrong by more than 0.3. Only the three
corrected on 2026-08-02 matched exactly.

All 33 now carry the published figures. `scripts/refresh_crime_from_ons.py
--check` reads every London row rather than sampling, so this cannot recur
silently: it exits non-zero on any drift. The v3.5 change was therefore a tail
correction *of three boroughs*, and a full re-verification of the other 29
followed a day later.

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

When the API receives a postcode that resolves to lat/lon (UK postcodes via postcodes.io), the **Quiet** component is computed at *postcode resolution* rather than borough-aggregate, using Haversine distance to airports and flight-path geometry. This is the same algorithm the consumer site has used for 290+ neighbourhoods since launch (`calcScores()` in `index.html`; cited by function name because a line range in an 8,500-line file drifts - the range previously given here pointed at CSS); v3.0 ports it to the API.

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

1. **Raster**, direct DEFRA Lden sample at the postcode centroid via DynamoDB lookup. Intended as the gold standard. **Quarantined since 2026-08-03 — see the warning below. This tier does not currently run.**
2. **Postcode (Haversine)**, distance to airports + flight-path geometry (this section, §4.5). **Currently the top live tier for any postcode with a centroid.**
3. **Borough (Lden band)**, borough-aggregate IMPACT_TO_QUIET lookup. Used when postcode lat/lon is not available.

The chosen tier is reported in `context.quietResolution` (`'raster' | 'postcode' | 'borough'`) so integrators can verify which tier produced the response. While the quarantine holds, `'raster'` is never returned.

> **⚠ Raster tier quarantined, 2026-08-03.** Tier 1 is bypassed in favour of tier 2.
> **The raster is not faulty and neither is the loader** — an earlier version of
> this note said otherwise, on the strength of an eight-postcode sample, and was
> wrong. `data/defra_lden_2022.tif` is the genuine DEFRA aircraft Lden map at 10 m
> resolution with values to 88.9 dB, its loudest cells falling exactly on
> Heathrow's two runway centrelines and London City Airport, and sampling it at
> correctly projected coordinates reproduces the stored values exactly.
>
> **The defect is coverage.** Aircraft contours are localised lobes: the raster
> holds data for 6.2% of its own grid, and **89.5% of London's postcodes fall
> outside them entirely** (measured over 22,622 live postcodes). The loader filled
> every one of those with 35 dB so they scored a perfect 10.0 — rendering *not
> measured* as *perfectly quiet*. The result was **98% of London on a single quiet
> value**, which cannot support this document's claim that Lden varies 10-15 dB
> within a borough. A single response could also report `noiseImpactBand:
> "severe"` alongside `quiet: 10.0`.
>
> **Effect on published scores:** quiet falls wherever the fill had inflated it —
> Heathrow moves 7.5 → 0.0, Hounslow 7.5 → 1.0. No weight, threshold or formula
> changed and both tiers were already documented here, so `METHODOLOGY_VERSION` is
> unchanged; only which documented tier answers has changed. It also closes a
> divergence in which the consumer site (always Haversine) published different
> numbers from the API for the same postcode.
>
> **What would let the tier return.** This said "two things" until 2026-08-04. It was
> wrong — there is a third, and it is the one now blocking.
>
> 1. **Done (code).** Uncovered postcodes must fall through to Haversine instead of
>    posing as raster hits. Guarded in the Lambda; the stored rows still hold the old
>    35.0 fill, but the read-side guard neutralises it, so a reload is tidiness rather
>    than a gate. The guard was widened on 2026-08-04 from an equality test on 35.0 to
>    a plausibility floor at 40.0 dB (the raster's true minimum), so a *different*
>    sentinel from some future loader cannot slip through the way 35.0 once did.
> 2. **Done 2026-08-04.** The band mapping is re-derived — see **§4.6**, which the
>    raster tier now uses instead of §4.1's borough table. TW6 1AP's genuine 58.2 dB
>    reading scored 7.5 under the old bands (an airport rated "fairly quiet") and
>    scores **2.7** under the v3.6 curve, inside the ≤ 3.0 that
>    `scripts/check_score_sanity.py` enforces.
> 3. **OPEN — the actual blocker.** The consumer site computes quiet from Haversine
>    geometry in `index.html` and has no access to the raster. Lifting the flag would
>    make the API answer from the raster for the 10.4% of London postcodes DEFRA
>    covers, while the site keeps answering from geometry — **re-opening, for 18,862
>    postcodes, the very site/API divergence this quarantine closed.**
>
>    The parity test will not catch it. `SiteApiGeometryParityTests` compares
>    `FLIGHT_PATHS` waypoints, which would still match; the API would simply stop
>    consulting them wherever a raster sample exists. Both halves stay self-consistent
>    — the same shape as the three-month divergence that test was written for.
>
>    Resolving it means choosing one of: serve the site's quiet from `/v1/score`, ship
>    the raster samples to the client, or accept and document the divergence. **That is
>    a product decision, not a data one**, and it is the last thing standing between
>    this tier and production.

**NYC ZIP centroids (v3.1, shipped).** NYC ZIPs now have static centroid lat/lon for ~110 ZIPs (sourced from the consumer site's `NYC_AREA_MAP`). This means NYC ZIP queries now use the v3.0 Haversine layer too, with the JFK/LGA/EWR/TEB airports and 8 NYC flight-path corridors. Within-borough variation is meaningful: 11201 (DUMBO) returns quiet=8 (north Brooklyn, away from JFK approach), while 11375 (Forest Hills) returns quiet=2 (under JFK / LGA traffic).

**Limitations of v3.0 / v3.1 Haversine (resolved when raster table is populated):**
- Airport-proximity bonus uses Euclidean-style distance, not flight-corridor membership. A postcode 5 km from an airport but to the *side* of the runway corridor is currently penalised the same as one directly under the corridor. Raster sampling will correct this.
- Flight-path waypoints are coarse polylines, not full flight-procedure geometries with altitude data. A postcode under a 9,000-ft transit gets the same noise score as one under a 1,500-ft final approach.
- NYC ZIP centroids are representative neighbourhood points, not true ZCTA polygon centroids. ~1 km of within-ZIP imprecision.
- **Helicopter noise is not modelled by the API.** See the divergence note below.

**Known divergence: the consumer site scores heliports, the API does not (recorded 2026-08-03).**
`skyscore.co.uk` adds a term this section does not describe: it measures distance to **five**
London rotary sites and adds a movement-weighted contribution to `noise_score`. `/v1/score`
has no heliport term at all. The term touches **14.1% of Greater London's land area**; outside
that, site and API now agree exactly.

> **A second divergence existed here and was closed on 2026-08-03.** This paragraph previously
> said the formulas were "otherwise identical, down to the same Haversine implementation and the
> same band edges". The implementation and band edges did match; **the geometry did not**. The
> 2026-05-07 trim recorded in §20 reached `index.html` and `scripts/audit_flight_paths.py` but
> never the score Lambda, which kept **85 waypoints across 12 corridors** against the site's
> **50 across 10** - including two whole corridors, `Approach N` and `Approach S`, that the audit
> removed. More waypoints means more chances to sit near one, so the API scored noisier wherever
> they differed: measured over 7,239 live London postcodes, `quiet` disagreed for **34.6%** of
> them and the API was the noisier side in **100%** of those. The Lambda now carries the audited
> geometry, and `test_flight_path_geometry_matches_the_site` asserts the two byte-for-byte so
> they cannot drift again. Heliports are now the *only* remaining difference, verified on five
> probes spanning both cases.

| Site | Rotary movements/yr | Source | Bands (<3 km, <5 km) | Share of London within 5 km |
|---|---|---|---|---|
| London Heliport (Battersea) | 12,000 | Planning cap, Wandsworth BC | +2, +1 | 4.79% |
| Elstree Aerodrome | 12,367 (2016) | Elstree Aerodrome Consultative Committee Guide, Hertsmere BC | +2, +1 | 0.97% |
| Denham Aerodrome | **not published** | — editorial, see §11 | +2, +1 | 1.50% |
| Royal London Hospital Helipad | ~1,600, daylight only | London's Air Ambulance annual mission report 2025 | +1, 0 | 4.71% |
| King's College Hospital Helipad | ~800, daylight only | Same report, smaller share — order-of-magnitude, see §11 | +1, 0 | 4.97% |

The weights follow from acoustics rather than preference: sound energy sums logarithmically, so
N movements contribute `10·log₁₀(N)` — the same basis as Lden under END 2002/49/EC, already
cited in §4.1. Battersea (40.79 dB-equivalent) and Elstree (40.92) are 0.13 dB apart and so
share a tier; the two air-ambulance pads sit ~8.75 dB lower, which on §4.1's ~5 dB bands is
nearly two steps. They are dropped **one** step, deliberately conservative — erring toward
keeping a noise penalty rather than removing one.

**Before 2026-08-03 all five scored an identical +2/+1**, which put two emergency helipads —
together 9.7% of London's land area, the largest footprint here — on the same footing as a
commercial heliport running roughly seven times their traffic. Contributions take the loudest
site rather than the nearest, consistent with the airport and flight-path terms, which also take
a single nearest source rather than accumulating.

This accounts for **every** observed site-versus-API difference on quiet, and for every case
where they agree. E1 8BL sits 1.10 km from the Royal London helipad, so the site scores quiet
**3** against the API's **5**; SW1A 1AA is 4.27 km from Battersea, giving **5** against **6**;
WC1E 6BT (5.13 km), TW3 1AA (12.61 km) and TW6 1AP have no heliport inside 5 km and match
exactly. It is not coordinate imprecision — both sides resolve identical latitude/longitude
and identical nearest-path distances.

The figures above **post-date** those examples: under the previous uniform weighting E1 8BL
scored quiet **3** against the API's **5**, and it now scores **4**. The site is still the
noisier of the two within 5 km of a rotary site, because the API models no rotary noise at all.

**What remains outstanding.** The tiers are now derived, but two inputs are not, and per §11 an
editorial choice must at least be *declared* as one:

- **Denham has no published movement figure.** Buckinghamshire Council, the Denham Aerodrome
  Consultative Committee and the aerodrome's own published material were all checked. Its weight
  is assigned by analogy to Elstree — a comparable general-aviation aerodrome with documented
  helicopter operations — and it affects 1.50% of London.
- **King's College's ~800 is order-of-magnitude,** inferred from London's Air Ambulance
  conveying to four major trauma centres with the Royal London taking ~40%. The tier would not
  change anywhere in the plausible range, since it sits far below the 12,000 reference either way.
- **The 3 km / 5 km radii and the two-tier structure itself are still editorial.** Only the
  *relative weighting between sites* is now derived.
- **The API does not implement this term at all**, so the surfaces remain divergent within
  14.1% of London until it is ported.

One thing settled deliberately: weighting rests on **noise exposure**, never on whether a
facility is socially desirable. Proximity to a trauma centre is a healthcare benefit and belongs
in the `live` component; importing it into `quiet` would double-count across components in
exactly the way §4.4's Progress 8 note guards against. The air-ambulance pads are weighted down
because they generate roughly a seventh of the movements, not because hospitals are good.

### 4.6 DEFRA raster sampling (v3.1, loaded 2026-07-26, quarantined 2026-08-03)

When correctly populated, the v3.1 raster tier replaces Haversine with direct sampling of the DEFRA Strategic Noise Mapping (Round 4, 2022) Lden GeoTIFF at the postcode centroid. That remains the intended gold-standard method — but it is an aspiration, not a description of what runs today. **The table was loaded, found to be wrong, and the tier is quarantined; see the warning in §4.5.** This section describes the design, not the live path.

**Architecture:**
- DynamoDB table `london-flight-map-noise-raster` (deployed and loaded; **tier bypassed since 2026-08-03 — the samples are correct but cover only ~10% of London, see the §4.5 warning. The contents are not invalid; an earlier revision of this line said they were**)
- Schema: `postcode` (string, hash key) → `ldenDb` (number, dB Lden value)
- Score Lambda reads with `ProjectionExpression='ldenDb'` and converts dB to quiet score using the **v3.6 continuous curve below** (until 2026-08-04 it reused §4.1's borough band table, which is what made this tier unusable)
- LRU-cached at the Lambda level for repeat queries within a container

**The dB → quiet curve (v3.6, re-derived 2026-08-04).** A continuous linear ramp between two
published thresholds, replacing the six-value band table §4.1 documents for boroughs.

> **`METHODOLOGY_VERSION` is still `3.5`, and that is correct.** "v3.6" names the curve, not the
> live methodology. The raster tier is quarantined, so **no request reaches this function** and no
> published score has changed; the version bumps to 3.6 on the deploy that unquarantines the tier,
> not before. Same reasoning as the 2026-08-03 quarantine entry, which also changed which
> documented tier answers without moving any weight, threshold or formula. Stated explicitly
> because a version that disagrees across surfaces is finding **#23** of the 2026-08-03 audit, and
> staging a curve under a version number is exactly how that starts.

| | dB Lden | Quiet | Source of the anchor |
|---|---|---|---|
| **Ceiling** | ≤ 45 | 10.0 | WHO Environmental Noise Guidelines (2018): aircraft Lden below 45 dB for residential areas, [Reference 2, §19](#19-references) |
| **Ramp** | 45 → 63 | 10.0 → 0.0 | Linear in dB, which is already perceptually reasonable — 10 dB ≈ a doubling of loudness |
| **Floor** | ≥ 63 | 0.0 | The UK's 57 dB LAeq,16h "onset of significant community annoyance" contour, re-expressed in Lden |

**Why 63 is not a free parameter.** Anchoring 10.0 at WHO's 45 dB, and requiring an airport to
score ≤ 3.0 (the invariant `scripts/check_score_sanity.py` enforces against the live API), forces
any linear ramp to reach 0.0 by ~64 dB. 63 is the point in that family with an independent
citation rather than one chosen to make a test pass.

**On the 57 dB figure.** It is `LAeq,16h`, **not** Lden. Lden carries +5 dB evening and +10 dB
night weighting, which puts 57 LAeq,16h at roughly 63 Lden for typical Heathrow operations. The
two must not be read as the same number.

**What changed, measured over all 18,862 covered London postcodes:**

| | old band table | v3.6 curve |
|---|---|---|
| Scored a flat 10.0 | 15,173 (**80.4%**) | 2,007 (**10.6%**) |
| Distinct values produced | 5 | 101 |
| Median | 10.0 | 6.7 |
| Heathrow `TW6 1AP` (58.20 dB) | 7.5 | **2.7** |
| Hounslow approach `TW3 4DX` (59.29 dB) | 7.5 | **2.1** |
| Bedfont `TW14 9QP` (72.97 dB, loudest) | 1.5 | **0.0** |

**Declared limitation — the mapped year is 2021, and it was not a normal year.** Round 4 is
published in 2022 but **maps the situation during 2021**, and Round 4 documentation describes the
result as *"a highly anomalous situation"* influenced by COVID travel restrictions — major
airports were even designated on the basis of movements *during 2021*. The understatement scales
with how hard each airport was hit, and sound energy sums logarithmically:

| airport | 2019 movements | 2021 movements | implied deficit |
|---|---|---|---|
| London City | 80,751 | **12,921** (16%) | **≈ −8.0 dB** |
| Heathrow | ~448,700 | substantially reduced | a few dB |

So **every dB figure derived from this raster errs quiet**, unevenly, and most at the smaller
airports. This affects the contour overlay on the consumer map and the prototype's published
readings as well as this tier — see `AUDIT_REPORT.md` A-0804-2. It is one more reason the raster
tier stays quarantined, and it cannot be corrected by re-banding: the fix is DEFRA Round 5
(~2027), which should map a representative year, or a non-DEFRA source. **Do not apply an
estimated correction factor** — inventing a multiplier is the failure mode this project has
already had to undo twice.

**Declared limitation — saturation at the loud end.** Everything at or above 63 dB reads 0.0, so
the loudest **348 covered postcodes (1.8% of covered, 0.19% of London)** cannot be told apart:
Bedfont at 72.97 dB and a postcode at 63.1 dB both score 0.0. This is the mirror of the defect it
replaces — at the other end, affecting 1.8% rather than 80.4%, and only among postcodes already
in the worst category. Erring loud is the safe direction for a noise product, so it is accepted
and disclosed rather than tuned away.

> **Why 348 and not 334.** A review on 2026-08-04 found this section and the `lden_db_to_quiet`
> docstring giving two different counts, and assumed one was a mistranscription. Neither was:
> **334** postcodes sit at or above the 63 dB floor, while **348** actually return 0.0, because
> the curve rounds to one decimal and anything from about **62.91 dB** upward rounds down to
> zero. Fourteen postcodes therefore read 0.0 without being at the floor. Since this limitation is
> about what a caller can distinguish, 348 is the correct figure and both surfaces now use it. The
> London proportion was also corrected from 0.18% to **0.19%** — 0.18% was the share for 334.

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

- Nearest airport: LCY at **15.87 km** → noise_score += 1 (15-20 km band)
- Major airport (LHR): **20.10 km** → no bonus (>15 km)
- Nearest flight-path waypoint: **2.38 km**, on the *Dep SE (Detling)* departure route → noise_score += 2 (2-4 km band)
- Nearest rotary site: **London Heliport (Battersea) at 1.13 km** → noise_score += 2 (§4.5 top tier, within 3 km)
- Total noise_score: **5**
- Quiet = 10 − 5 = **5.0**

The live API returns `quiet: 5.0` and a balanced total of `6.4` for SW11 1AA, which is what the arithmetic above produces — no adjustment, no clipping. **The borough Lden band remains 'moderate'** in the response's `context.noiseImpactBand` for transparency, but does not affect the score itself.

> **Second correction, 2026-08-03 (later the same day).** The heliport step above was added when
> the rotary term was ported from the consumer site to `/v1/score`. Until that port this example
> derived **7.0** and matched the API; the port changed SW11 1AA to **5.0** and left this section
> asserting the old figure for several hours. SW11 1AA sits 1.13 km from the London Heliport, so
> it is one of the postcodes the term moves most — the worked example was, by coincidence, the
> worst possible one to leave unchecked. Recorded rather than quietly amended because "the score
> is fully reproducible" is a claim this document has now broken twice in one day, both times by
> changing the engine without re-running the example.

> **Correction, 2026-08-03.** This example previously stated the nearest flight-path
> waypoint was "~6 km → noise_score += 0", giving a total of 1 and a quiet score of
> 9 — then reconciled that against the live 7.0 by asserting the result was
> "clipped to 7.0 in practice", with the Battersea heliport supplying "residual
> context the airport+path proxy doesn't capture". Both claims were wrong. The
> nearest waypoint is 2.38 km, not ~6 km, so the correct total was always 3 and the
> formula yields 7.0 directly. There is no clipping step in the code and the API
> does not model heliports at all; that sentence was a post-hoc rationalisation of
> an arithmetic slip, and it was this document's only mention of heliports. The
> formula was reproducible all along — this worked example was not. Recomputed here
> against the live geometry (`CITY_GEOMETRY['london']`) rather than by hand.

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
| **DEFRA Strategic Noise Mapping (Round 4, 2022)** | **Aircraft** Lden contours for England (the road dataset is published too and is used only for the consumer-site map overlay, never for the score — see §3) | Open Government Licence v3.0 | 5-yearly (next: 2027) |
| **HM Land Registry Price Paid Data** | Historic sold prices at postcode resolution | Open Government Licence v3.0 | Monthly |
| **MHCLG Energy Performance Certificates** (new "Get energy performance of buildings data" service from 2026-05-30) | Per-property EPC bands | Open Government Licence v3.0 | Quarterly |
| **TfL Open Data** | Transport accessibility, station and live line status | TfL Open Data terms, commercial use permitted with attribution | Real-time |
| **OpenStreetMap, via the Overpass API** (`overpass-api.de`, FOSSGIS e.V.) | GP, pharmacy and hospital proximity for the `live` component | Data under **ODbL 1.0** (share-alike, *not* OGL) — attribution required. Service provided best-effort with no SLA | Continuous (community-maintained) |
| **ONS** | Population estimates, boundary geometry | Open Government Licence v3.0 + OS Open Licence | Annual |
| **ONS, *Crime in England and Wales*, Police Force Area data tables, Table C4** | Borough-level offence rate per 1,000 residents, on mid-2024 population | Open Government Licence v3.0 | Quarterly release; year ending March 2026 in use |
| **Department for Education, Key Stage 4 Progress 8** | School quality, intake-adjusted, at local-authority level | Open Government Licence v3.0 | Annual — but **2022/23 is the terminal vintage** until 2026/27 publishes (§4.4) |
| **HM Land Registry House Price Index (HPI)** | Affordability cohort scaling and the growth trend. Distinct from Price Paid Data above, which serves the sold-price panel | Open Government Licence v3.0 | Monthly |
| **postcodes.io** | UK postcode → administrative-district resolution | Open Government Licence v3.0 (data) | Quarterly |

> **Corrected 2026-08-04.** This table credited **three suppliers the engine no longer uses, and
> one it never used**:
>
> - *"NHS Service Search API — provided by NHS Digital"*. **Nothing calls NHS Digital.**
>   `backend/lambdas/nhs/app.py` makes exactly one outbound request, to the **OpenStreetMap
>   Overpass API**. The `www.nhs.uk` URLs in that file are link targets placed in the response
>   body, never fetched. The licence was wrong as well as the supplier: OSM is **ODbL**, a
>   share-alike licence, not OGL — the same mislabelling audit finding 33 flagged on the privacy
>   page.
> - *"Home Office crime statistics"* — re-sourced to **ONS Table C4** in v3.5 (2026-08-02).
> - *"Department for Education / Ofsted school ratings"* — Ofsted single-word grades were
>   abolished in September 2024 and the bands were found to be editorial; replaced by **DfE
>   Progress 8** in v3.5.
>
> **HM Land Registry HPI** was missing entirely, despite driving both `afford` and `growth` —
> the table listed only Price Paid Data, which serves the sold-price panel. This is the table a
> diligence process starts from, so a supplier list that is three-quarters out of date on the
> `live` component is a procurement problem, not a tidiness one.

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

**Versioning + reproducibility.** The API response includes `methodologyVersion` (currently `"3.5"`). On any methodology change — including a new noise-mapping round — this version increments. When Round 5 data lands the version will jump to `"4.0"`.

> **Corrected 2026-08-04.** Two errors in the sentence above. (1) It said "currently `3.1`", **stale by four versions** — the live API returns `3.5`. (2) It promised *"integrators can pin to a specific version via `?methodology=X.Y` (where supported)"*. **That parameter is not implemented anywhere.** `backend/lambdas/score/app.py` never reads it, so the request is silently ignored and the caller receives current-version numbers while believing they pinned. The hedge "(where supported)" was doing a great deal of work; it is nowhere supported.
>
> The claim is **withdrawn rather than built.** Real pinning means retaining prior data vintages *and* prior formula code paths — this document's own §6 shows why, since reproducing v3.0 needs the pre-v3.2 clamp, the pre-v3.3 weights and the pre-v3.4 growth formula. That is a substantial piece of engineering and there is no paying customer to justify it yet. **It will be built when a contract requires it, not before, and this document will not claim it until it exists.**
>
> **What does exist today** is `?compare=previous`, which returns the current score alongside the prior vintage with an exact weighted-sum attribution of what moved — see §4.7 and `/v1/changes`. That answers "what changed and why", which is most of what pinning is usually wanted for, though it is not the same guarantee.

**Round 5 transition plan (forecast: late 2027).** When DEFRA publishes Round 5:
1. New aircraft + road GeoTIFFs are downloaded from the data.gov.uk dataset pages
2. The offline loader (`scripts/load_defra_raster.py`) is re-run; it overwrites by postcode key, so 1.7M new values cleanly replace the old ones with no migration needed
3. `METHODOLOGY_VERSION` in the score Lambda bumps to `4.0` (from `3.5` as at 2026-08-04)
4. Methodology document updates with the new round reference and any methodology-model changes (e.g. CNOSSOS revision)
5. B2B customers get the standard 14-day advance notice via email
6. ~~Old responses remain reproducible by passing the prior `?methodology=` value~~ — **not available; that parameter is unimplemented, see the correction in §16.** Use `?compare=previous` and `/v1/changes` to see what moved between vintages

The Lambda's quiet-resolution chain (raster → Haversine → borough) means the API silently upgrades to the new data; no client changes needed at the integration layer.

**Practical inputs for the loader (verified URLs, 2026-05-06):**

- DEFRA Aircraft Noise (Round 4): https://www.data.gov.uk/dataset/airport-noise-all-metrics-england-round-4
- DEFRA Road Noise (Round 4): https://www.data.gov.uk/dataset/38b1444f-47a0-42ca-a358-0d145fcf7d5c/road-noise-all-metrics-england-round-4
- DEFRA umbrella + methodology: https://www.gov.uk/government/publications/strategic-noise-mapping-2022
- ONS NSPL catalogue: https://www.data.gov.uk/dataset/national-statistics-postcode-lookup-uk
- ONS Open Geography Portal: https://www.ons.gov.uk/methodology/geography/geographicalproducts/postcodeproducts

Both DEFRA dataset pages have an interactive "Download data by area of interest and format" tool. Select **all of England**, **GeoTIFF** format, and the **Lden** metric, submit, and download once the export is prepared (typically 5 minutes).

> **Corrected 2026-08-06: the interactive tool is not the only route, and for road noise it is no longer the one we use.** The dataset pages also publish an **OGC WCS endpoint**, which takes bounding-box requests over plain HTTP and returns the same GeoTIFF under the same licence. `scripts/fetch_defra_road_noise.py` uses it to pull Greater London directly, so the road-noise raster is reproducible from a terminal rather than dependent on someone clicking through a portal. That also removes the manual step from the Round 5 plan above.
>
> One constraint found by measurement: a single request for the whole Greater London bbox returns **504**. 20 km tiles return 200 in a few seconds each (2000x2000 at native 10 m), so the script tiles and mosaics — 12 tiles, ~62 MB output.
>
> **Coverage differs enormously between the two rasters, and it changes what each can support.** The aircraft raster carries data for **6.2%** of its grid, because DEFRA's aircraft contours are localised lobes around airports — which is why the raster tier is quarantined (§4.5). The road raster carries **92.2%**, because roads are everywhere. Road noise therefore does not inherit the coverage defect that blocks aircraft, and can be scored honestly for nearly every London postcode. Measured 2026-08-06: range 40.0-92.7 dB, median 51.7, Hyde Park Corner 70.1.

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

### 11.0 Scale direction: scores rise, measurements rise, and the label says which

**Two opposite conventions run in this product, deliberately. Do not harmonise them.**

| Kind of number | Direction | Label pattern | Where |
|---|---|---|---|
| **Score** (0–10 component) | higher = **better** | names the *good* thing — `Quiet Skies`, `Affordability`, `Liveability` | `index.html` score panel, `/v1/score` components |
| **Measurement** (physical unit or a 0–10 stand-in for one) | higher = **worse** | names the *bad* thing — `Road noise 49.5 dB Lden`, `NO₂ 23.9 µg/m³`, `Aircraft noise 2/10 noise` | `/v1/environment`, the browser extension's Environment section |

The rule is **not** "noise always goes up". It is that a number's direction must agree with everything it is displayed *beside*, and the label must name which thing is being counted.

A score component sits alongside Affordability and Growth, where higher is better; making noise rise there would leave one bar filling up to mean the opposite of its neighbours. A measurement sits alongside dB and µg/m³, where higher is worse; a quiet score there does the same damage in reverse. **That reverse case was a live defect**: until 2026-08-08 the extension rendered `Aircraft noise 8/10` from a quiet score, so the row with the *longest* bar was the *quietest* one, and the only thing distinguishing them was the word "quiet" in the smallest text on the row.

**Consequence, and it is intended:** the same postcode reads `Quiet Skies 8/10` on the site and `Aircraft noise 2/10` in the extension. That is one value under two labels, not a disagreement — `/v1/environment` returns `aircraftQuietEstimated: 8` and the extension displays `10 − 8`, a transform asserted against the live endpoint in `tests/extension-e2e.mjs`. It is written down here because it *looks* like the site/API divergences this project has genuinely had three times, and a future session correcting the resemblance would reintroduce the defect above.

| Editorial choice | Defensible reasoning |
|---|---|
| `IMPACT_TO_QUIET` value scale (10 / 7.5 / 5.0 / 3.0 / 1.5 / 0.0) | The dB Lden bands are DEFRA-anchored; the score values reflect the inverse-square-ish relationship between noise dB and health effect documented in WHO meta-analyses. The non-linear spacing (3 → 1.5 = halving) reflects that small dB increases at high baselines have outsized effects. |
| `SCHOOL_SCORE` values (10 / 9 / 6 / 3) — **RETIRED 2026-08-02** | **This row previously claimed the bands were "anchored to the Ofsted national distribution". That claim was false**, which is why v3.5 removed them: no threshold on "% Good or Outstanding" reproduces the stored bands, and the measure behind them was withdrawn by Ofsted in September 2024. Retained here as a record of a defence that did not hold up, because the point of this section is that a stated justification can be checked. Schools now uses `school_score(p8) = clamp(5.0 + 5.0 × p8, 0, 10)`, whose anchors are external constants (0.0 = national average, ±1.0 = one grade per subject) rather than editorial. The legacy bands survive only as a fallback for areas with no Progress 8 figure — in London, the City of London alone. |
| Heliport bands (+2 / +1 within 3 km / 5 km) and the 3 km / 5 km radii | **Editorial, declared.** The *relative* weighting between sites is derived — sound energy sums logarithmically, so annual movements contribute `10·log₁₀(N)`, the same basis as Lden under END 2002/49/EC (§4.1). That is what separates the 12,000-movement sites from the ~1,600-movement air-ambulance pads. The absolute band values and the two distance radii are **not** anchored to any published source; they mirror the airport-proximity structure above for internal consistency. Consumer site only — `/v1/score` does not implement this term. See §4.5. |
| Denham Aerodrome's weight | **Editorial, declared, and the weakest link in this table.** No published movement figure exists: Buckinghamshire Council, the Denham Aerodrome Consultative Committee and the aerodrome's own material were all checked (2026-08-03). Its weight is assigned by analogy to Elstree, a comparable general-aviation aerodrome with documented helicopter operations. Affects 1.50% of Greater London. Revise on publication of a type breakdown. |
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
2. Subject to **14 days' advance notice** before the change takes effect. **Corrected 2026-08-04:** this previously promised a "14-day grace period during which the prior methodology version remains accessible via `?methodology=`". No such parameter exists, so no grace period was ever technically available — the notice period is real, the version-pinning mechanism behind it was not. Stated as notice-only until pinning is actually built.
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

- **2026-08-03 (no version change)**, **API flight-path geometry trimmed to match the audited site set.** (1) *Defect:* the 2026-05-07 trim, which scoped each London corridor to its noise-relevant final-approach / initial-departure portion and was audited against the DEFRA Lden raster by `scripts/audit_flight_paths.py`, was applied to `index.html` and to the audit script but **never to the score Lambda**. For three months `/v1/score` carried **85 waypoints across 12 corridors** against the site's **50 across 10**, including two entire corridors (`Approach N`, `Approach S`) the audit had removed. (2) *Consequence:* the quiet formula takes the distance to the nearest waypoint, so surplus geometry can only ever add noise. Measured across **7,239 live London postcodes**: site and API disagreed on `quiet` for **2,503 of them (34.6%)**, and the API was the noisier side in **100%** of the disagreements. (3) *Which side was authoritative was not a judgement call:* `scripts/audit_flight_paths.py` states in its own header that it mirrors `index.html` "as of 2026-05-07 (after the trim)", and its geometry is identical to the site's across all ten corridors. The Lambda was simply never updated. (4) *Effect on published scores:* `quiet` rises by **1.0 to 4.0** for that 34.6% and **falls nowhere**. No weight, threshold or formula changed - only the geometry the existing formula reads - so the version is unchanged. (5) *Guard:* `test_flight_path_geometry_matches_the_site` and `test_airports_match_the_site` compare the Lambda against `index.html` directly and were verified to fail by restoring one trimmed corridor. Nothing could previously have caught this: the pytest suites only ever read the Lambda and Playwright only ever reads the site, so each half stayed self-consistent while disagreeing with the other. (6) *Residual:* heliports are now the only site/API difference, documented in §4.5 and confirmed on five probes. (7) *Notice:* the API has no paying customers as at this date, so this ships with this changelog entry as the record.
- **2026-08-03 (no version change)**, **DEFRA raster tier quarantined; quiet falls back to Haversine.** (1) *Defect — RESTATED 2026-08-03, second pass:* this entry originally said "the loaded sample table was invalid". **That was wrong.** The raster is the genuine DEFRA aircraft Lden map (EPSG:27700, 10 m, values to 88.9 dB, loudest cells exactly on Heathrow's two runway centrelines and London City), the loader's projection is correct, and sampling at correctly projected coordinates reproduces the stored values exactly. The real defect is **coverage**: aircraft contours are localised lobes covering 6.2% of the grid, so 89.5% of London postcodes fall outside them, and the loader filled every one with 35 dB — rendering *not measured* as *perfectly quiet* and putting 98% of London on a single value. Measured over 22,622 live postcodes. The tier had been serving production since ~26 July. `london-flight-map-noise-raster` stores **58.2 dB Lden for TW6 1AP — a postcode inside Heathrow Airport** — against DEFRA Round 4 contours above 75 dB near the runways, and stores an identical, exactly round **35** for postcodes as distant as E1 8BL and N4 1AA, which is a background fill rather than a sample (DEFRA maps only to the 55 dB reporting threshold, so *no data* was written as though it meant *quiet*). (2) *Consequence:* through the §4.1 bands (<55 → 10.0, <60 → 7.5) those are the only two outputs the table can produce, so `quiet` carried **two distinct values across the whole of London** and erred **optimistic** — the one direction a noise product cannot be wrong in. Responses could self-contradict, reporting `noiseImpactBand: "severe"` beside `quiet: 10.0` (TW7 5QD). It also meant the consumer site, which has always computed Haversine client-side, published different numbers from the API for the same postcode: SW1A 1AA scored **7.1 via the API and 5.2 on the site**, with `afford`, `growth` and `live` agreeing to the decimal. (3) *Change:* `RASTER_TIER_QUARANTINED` bypasses tier 1, so every postcode with a centroid resolves on the Haversine tier already documented in §4.5. (4) *Effect:* scores fall wherever the raster inflated them — Heathrow **7.5 → 0.0**, Hounslow **7.5 → 1.0**, Finsbury Park 10.0 → 6.0. Both tiers were already documented and no weight, threshold or formula changed, so the version is unchanged; only which documented tier answers has changed. (5) *Guard:* `test_airport_postcode_is_never_scored_as_quiet` stubs the table with the real stored value and asserts Heathrow scores ≤ 3.0, verified to fail at 7.5 with the quarantine lifted. The assertion is **absolute, not comparative** — "Heathrow beats Finsbury Park" passes on the broken data (7.5 vs 10.0), which is why the collapse survived a week. A second test asserts quiet yields ≥3 distinct values from Heathrow to Bromley, the same guard the growth floor and the schools bands each needed. (6) *Root cause — RESOLVED 2026-08-03:* this entry originally read "`scripts/load_defra_raster.py` is unfixed. Suspects: a CRS mismatch (British National Grid vs WGS84)…". **There is no loader bug.** The nodata fill was deliberate and documented, added to stop postcodes near an airport but outside any contour falling through to Haversine and scoring as loud (Twickenham was the trigger). The loader now skips uncovered postcodes so they fall through as the §4.5 chain intends, and the Lambda treats a stored 35.0 as a miss — safe as a sentinel because the raster's minimum real value is 40.0 dB. **Two things still gate lifting the quarantine:** the stored rows still hold the old fill, and TW6 1AP has a *genuine* 58.2 dB reading that §4.1's bands score as quiet 7.5 — an airport rated "fairly quiet" — against a WHO 2018 aircraft guideline of 45 dB Lden. The open question is the band mapping, not the data. (7) *Notice:* the API has no paying customers as at this date, so this ships with this changelog entry as the record.
- **2026-07-31 (no version change)**, **Provenance stated per city.** (1) *Defect:* the `sources` array and `sourceBreakdown` object were single module constants emitted on every response regardless of the city scored. Every New York response therefore credited MHCLG, HM Land Registry, ONS, the Home Office, DfE, TfL, NHS and DEFRA, under **Open Government Licence v3.0** — a UK Crown-copyright licence — for data the codebase itself documents as NYPD CompStat-derived and curated from New York sources. None of those bodies has a New York remit. This was live in production, and it is the precise error the adjacent `_postcode_source_line()` exists to prevent: crediting a source on configuration rather than on what actually answered. (2) *Change:* provenance resolves per city from a `CITY_PROVENANCE` registry. New York credits its own sources — NYPD CompStat-derived crime rates and curated borough price and noise data — and states that OGL does not apply to it. An unknown city returns a "not recorded" line instead of inheriting London's. Batch responses spanning several cities label each line with the city it belongs to. (3) *Effect on scores:* **none.** No weight, threshold or formula changed and every score is byte-identical, which is why this carries no version bump — bumping would tell integrators to re-run for movement that does not exist. (4) *Guard:* a city that is scoreable but has no provenance entry now fails `test_every_city_has_its_own_provenance`, so a future city cannot inherit another's sources by omission.
- **2026-08-02 (v3.5)**, **Schools re-sourced; three crime rates corrected.** (1) *Defect A, schools:* the input was a four-value vocabulary (`outstanding`/`excellent`/`good`/`mixed` → 10/9/6/3) documented as "anchored to the Ofsted distribution". It was not. Checked against the Ofsted management-information release (as at 30 June 2026, 21,957 schools), **no threshold on "% Good or Outstanding" reproduces the stored bands** — `excellent` spanned 90.9–100% and `good` spanned 83.3–100%, so **Westminster at 100% was banded `good` while Richmond at 100% was banded `excellent`**, and Camden was banded `excellent` while its pupils made *below*-median progress. The bands were editorial. Worse, the measure behind them had been withdrawn: Ofsted abolished single-word overall-effectiveness grades in **September 2024**, only ~44% of schools still carry one, that remainder is precisely the not-yet-reinspected (so it is shrinking *and* non-random, with Westminster at n=25 and the City of London at n=1), and **87.2%** of it is Good or Outstanding — a measure that barely separates places. The renewed framework replacing it covered **0.4%** of Greater Manchester schools and 0.0% of sampled London boroughs, with an incompatible vocabulary. (2) *Change A:* schools now uses **DfE Key Stage 4 Progress 8, 2022/23, at local-authority level**, scored continuously by `school_score(p8) = clamp(5.0 + 5.0 × p8, 0, 10)`. Progress 8 is defined so the national average is ~0.0 and ±1.0 is a full grade per subject against pupils with the same KS2 baseline, so the anchors are **external constants, not cohort extremes** — comparable across areas and across vintages. Nothing clamps; London and Greater Manchester span 2.55–8.20. Being intake-adjusted also stops school quality re-importing the affluence already priced into `afford`, which raw Attainment 8 would have done. (3) *Effect A:* London moves from **2 distinct schools sub-scores to 25**. Wandsworth's headline moves 6.7 → 6.4 (banded `excellent`, measures P8 +0.33 against a London median of +0.30); Camden 7.8 → 7.1. (4) *Defect B, crime:* three boroughs carried values compressed to fit inside `CRIME_TO_SCORE`'s 50–200 band rather than drawn from source — **Westminster held 175 against an actual 355.5**, Kensington and Chelsea 95 against 145.8, Camden 130 against 173.3, all three understated. (5) *Change B:* corrected against **ONS *Crime in England and Wales: Police Force Area data tables*, year ending March 2026, Table C4**. **[Corrected 2026-08-03: this entry originally claimed "the other 29 boroughs already agreed with that release within 10 per 1,000 and are untouched". That was generalised from three spot checks and was false — 29 of 33 disagreed with the cited release, seven by more than 10 per 1,000. See the 2026-08-03 entry.]** This was a tail correction of three boroughs, **not a vintage roll**; the remaining 29 were re-verified and corrected the following day. The 50/15 band is unchanged: tested on true figures it clamps once in 43. (6) *Vintage warning:* Progress 8 **cannot be calculated for 2024/25 or 2025/26** — those cohorts sat KS2 in the cancelled 2020 and 2021 windows — and DfE announced in April 2024 that there is no replacement, so 2022/23 is the terminal vintage until 2026/27 publishes. (7) *Disclosure:* responses now carry `context.liveResolution` (measured / partial / unavailable) so a defaulted component cannot read as a measurement, and `comparisonUnavailable` where no prior vintage exists. (8) *Notice:* the API has no paying customers as at this date, so this ships with this changelog entry as the record.
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
