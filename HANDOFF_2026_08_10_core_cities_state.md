# Handoff, 2026-08-10 — Core Cities: what is built, what is blocked, and how far this scales

Supersedes the data-sourcing half of `HANDOFF_2026_08_09_core_cities_next.md`.
Read that one for the traps; read this one for the current state.

## What shipped today

| Change | Commit |
|---|---|
| Locator a11y regression fixed; new WCAG source gate | `9d47ebd` |
| Registry-driven lazy scoring; Manchester autocomplete bug | `37e06ea` |
| `build_hpi_prices.py` — prices re-derivable, ONS-code keyed | `d86e956` |
| London's `trend` corrected to HPI; new blocking gate | `c5b237c` |
| USA locator + all eight regions' boundaries | `fbf6705` |

Deployed and verified from the endpoint: the corrected trends (site and API
agree on all 6 parity postcodes), `sw.js` v1.0.19, `deployed == source` clean.

## Per-region readiness, MEASURED not estimated

Run `python scripts/build_hpi_prices.py --emit --city <id>` to get the price
half of any borough table.

| Region | Authorities | Prices | Crime | Boundaries |
|---|---|---|---|---|
| West Midlands | 7 | 7/7 | 7/7 | ✅ |
| West Yorkshire | 5 | 5/5 | 5/5 | ✅ |
| South Yorkshire | 4 | 4/4 | 4/4 | ✅ |
| Merseyside | 5 | 5/5 | 5/5 | ✅ |
| Tyne and Wear | 5 | 5/5 | 5/5 | ✅ |
| Bristol | 4 | 4/4 | 4/4 | ✅ |
| Nottingham | 4 | 4/4 | **1/4** | ✅ |
| Cardiff | 4 | 4/4 | 4/4 | ✅ |

**Seven of eight are data-complete on prices and crime.** Boundaries exist for
all eight, are checked in, and are un-ignored in `.gitignore`.

## West Midlands is LIVE on /v1/score (backend-only)

Deployed and verified from the endpoint: `/v1/regions` returns four cities and
Birmingham scores 3.7. It is **backend-only and declared as such** in
`BACKEND_ONLY_CITIES`, because it has no `data/borough-extra.json` entry.

`scripts/build_aircraft_bands.py` now exists and covers all eight regions -
`--city <id>` prints a paste-ready `impact` block. The remaining seven need only
that command plus the mechanical checklist below.

**The band rule was wrong first time and the fix matters.** Taking
`min(distance-to-airport, distance-to-corridor)` rated Walsall `severe` at
21.9 km from Birmingham on the strength of sitting 3.2 km off the extended
centreline. Aircraft that far out are ~6,000 ft up. Being under the approach now
makes a place one band worse, not equivalent to the runway. If you regenerate
bands for another city, sanity-check the far-field boroughs against that.

### Why it is not on the consumer site

There is **no Progress 8 pipeline in this repo for any city**, so West Midlands
has crime as its only liveability input. That is below the two-input floor, so
`live` is dropped and its weight redistributed, and `liveResolution` reports
"1/4 inputs measured, too few to publish". Putting it on the site in that state
is exactly what made all ten Manchester boroughs disagree with the API.

Consequence worth knowing before outreach: for the default `balanced` persona
the city effectively scores on **quiet and afford alone** (v3.3 leaves growth
unweighted), so its scores are more extreme than London's - Solihull lands at
0.0 by being both the priciest borough in its cohort and under the approach.
That is arithmetically correct and reads harshly. Progress 8 is what fixes it.

## 🚨 THE DEFRA "BLOCKER" IS NOT A BLOCKER. THE DATA EXISTS FOR EVERY CITY.

**Measured 2026-08-10 against the DEFRA WCS the repo already knows about**
(`environment.data.gov.uk/spatialdata/airport-noise-all-metrics-england-round-4/wcs`,
the endpoint named in `scripts/download_defra_wcs.py`). GetCapabilities
advertises **80 coverages, 16 airports with a Round 4 `Lden` surface**:

    ALL, Birmingham, Bournemouth, Bristol, EastMidlands, Gatwick, Heathrow,
    LeedsBradford, Liverpool, LondonCity, Luton, Manchester, Newcastle,
    Southampton, Southend, Stansted

Every airport this product needs is there, **including Manchester**:

| City | Airport coverage | Status |
|---|---|---|
| Greater Manchester | `Airport_Noise_Manchester_Lden` | AVAILABLE |
| West Midlands | `Airport_Noise_Birmingham_Lden` | AVAILABLE |
| West Yorkshire | `Airport_Noise_LeedsBradford_Lden` | AVAILABLE |
| Merseyside | `Airport_Noise_Liverpool_Lden` | AVAILABLE |
| Tyne and Wear | `Airport_Noise_Newcastle_Lden` | AVAILABLE |
| Bristol | `Airport_Noise_Bristol_Lden` | AVAILABLE |
| Nottingham | `Airport_Noise_EastMidlands_Lden` | AVAILABLE |

There is also an **`Airport_Noise_ALL_Lden`** coverage - one England-wide
surface rather than seven downloads.

### Two provenance statements in production are therefore FALSE

`CITY_PROVENANCE` tells `/v1/score` consumers, for Greater Manchester and for
all eight regions added today, that the estimate is used because the Round 4
raster **"has not been run for"** that city. It has been run. The correct
sentence is that it **has not been SAMPLED by us** - a statement about our
pipeline, not about DEFRA's coverage.

Manchester has carried that wording since it shipped; I copied it onto eight
more cities today before checking it. It is the same defect class as London's
`trend` claiming HPI: a provenance sentence the data does not support. **Fix
this before any outreach**, because it understates the product to a customer
and misstates a public body's coverage.

### What this changes strategically

The estimate is a **stopgap, not a limitation**. `scripts/load_defra_raster.py`
already takes `--geotiff` with per-raster checkpointing, so this needs the
exports and a loader run - not new code and not new research. Ten cities can
move from *modelled* to *measured against the regulator's own surface*.

## ⚠️ DO NOT DEMO THE NEW CITIES UNTIL PROGRESS 8 LANDS

All nine UK/US regions are live on `/v1/score`. Measured on the deployed API:

| Flagship borough | City | Score | quiet | afford |
|---|---|---|---|---|
| Newcastle upon Tyne | Tyne and Wear | **0.0** | 0.0 | 0.0 |
| Leeds | West Yorkshire | **1.7** | 3.0 | 0.0 |
| Birmingham | West Midlands | **3.7** | 0.0 | 8.2 |
| Cardiff | Cardiff | **3.7** | 5.0 | 2.1 |

**The flagship city of each region scores near the floor, and it is arithmetic,
not data error.** With no Progress 8 there is one liveability input, so `live`
is dropped. v3.3 already gives `growth` zero weight for the `balanced` persona.
That leaves **quiet and afford alone** - and the biggest city in any region is
usually its priciest borough, which takes `afford` 0.0 by definition of cohort
min-max scaling. Newcastle is both the priciest in Tyne and Wear and close to
NCL, so it takes 0.0 twice and lands at 0.0 overall.

The responses are honest - `liveResolution` says "1/4 inputs measured" and the
provenance says the city is thinner than Greater Manchester - but "Newcastle
upon Tyne: 0.0 out of 10" is not a number to put in front of a prospect.

**This is the single strongest argument for doing Progress 8 next.** It is one
extraction, 2022/23 is terminal until 2026/27, and it restores the third
component for all nine cities at once. Until then the new regions are
API-reachable but not demo-ready, and they are correctly kept off the consumer
site by `BACKEND_ONLY_CITIES`.

## The two blockers, both real

### 1. Aircraft bands — the last one, and the one that matters most

`impact` is effectively **required**: `calc_score` does `bd['impact']`, so a
borough without one raises rather than degrading. And it feeds the product's
headline component, so getting it wrong is being wrong about the thing the
product is for.

Verified airport coordinates (OurAirports, public domain — do NOT type these
from memory, that is how a confidently-wrong figure gets in):

| Region | Airport | Lat | Lon |
|---|---|---|---|
| West Midlands | EGBB / BHX | 52.453899 | -1.74803 |
| West Yorkshire | EGNM / LBA | 53.865898 | -1.66057 |
| Merseyside | EGGP / LPL | 53.334863 | -2.849637 |
| Tyne and Wear | EGNT / NCL | 55.037958 | -1.689577 |
| Bristol | EGGD / BRS | 51.382326 | -2.716453 |
| Nottingham | EGNX / EMA | 52.8311 | -1.32806 |
| Cardiff | EGFF / CWL | 51.396702 | -3.34333 |
| **South Yorkshire** | **none** | — | — |

**South Yorkshire has no operating commercial airport.** OurAirports lists
Doncaster Sheffield as `type=closed`. That is evidenced, not assumed. Its
boroughs are genuinely not aircraft-affected, and the nearest large airports are
Leeds Bradford and Manchester at roughly 50-60 km. Whatever is published for it
must say that rather than implying a measurement.

**Do not reuse London's distance ladder unmodified.** `CITY_GEOMETRY` already
records that the airport term is distance-only and calibrated on Heathrow, and
that Manchester at roughly a third of Heathrow's movements is already overstated
by it (Core Cities finding 7). Applied to Bristol or Cardiff it would overstate
badly. The saving grace is the DIRECTION: overstating noise understates quiet,
and the DEFRA raster incident is on record precisely because it erred the other
way. Erring pessimistic is survivable; erring optimistic is not.

### 2. Progress 8 — no pipeline exists for any city

London's and Greater Manchester's `p8` values came from a DfE Key Stage 4
release, and **nothing in the repo re-derives them**. Without `p8` a new city has
one liveability input (crime), which is below the two-input floor, so `live` is
dropped entirely and its weight redistributed. That is handled and honest, but it
makes every new city thinner than Greater Manchester rather than equal to it.

2022/23 is the terminal vintage until 2026/27 publishes, so this is a one-off
extraction, not a recurring one.

### Nottingham specifically

ONS publishes `Nottingham` and `South Nottinghamshire` as Community Safety
Partnerships. Broxtowe, Gedling and Rushcliffe are **not published separately** —
they are inside that one combined row. Options: give the three the combined rate
with an explicit disclosure that it is a shared figure, or leave crime absent for
them. Do not silently spread one rate across three boroughs as if measured.

## Remaining mechanical work per city

Once a city has `impact`, everything else is the checklist from the previous
handoff, all of it mechanical:

1. `CITIES` + `CITY_PROVENANCE` in `backend/lambdas/score/app.py`
2. `CITY_DATA` in `index.html` — every key, since `tests/smoke-local.mjs`
   asserts key parity across cities
3. `data/borough-extra.json` entry
4. `sw.js` `SHELL_ASSETS` + a `make data-deploy` line for the boundary file
5. `LOCATOR_TO_CITY` in `index.html`
6. `CITY_PFA` + a CSP include-list in `scripts/refresh_crime_from_ons.py`

Steps that used to be error-prone are now closed: `hydrateBoroughExtra()` and
`recalcAllScores()` no longer enumerate cities by name, so there is nothing to
forget in either.

## How far this actually scales

The question was how many cities are reachable. Measured against what the
pipelines can already read:

- **England and Wales, ~318 local authorities.** HPI covers every one, and ONS
  Table C4 publishes CSP rows at local-authority level for all 43 forces. Both
  loaders are already parameterised, so this is not a per-city research task any
  more. Progress 8 is **England only** — Wales has no equivalent.
- **Scotland and Northern Ireland** need different sources: Police Scotland and
  PSNI publish separately from ONS, and neither is in Table C4.
- **The United States** needs a different pipeline for every input. The one
  genuinely strong asset is the **Bureau of Transportation Statistics National
  Transportation Noise Map**, which is a national road and aviation noise
  surface — the nearest thing to DEFRA outside Europe. Prices via FHFA HPI or
  Census ACS; crime via the FBI Crime Data Explorer, which is agency-level and
  patchy. No national schools equivalent.
- **Canada**: StatCan publishes crime by census metropolitan area, which is
  usable. Prices are the problem — the CREA MLS HPI is licensed restrictively.
  No national noise map.
- **The EU is the real lever, and it is not close.** The **Environmental Noise
  Directive 2002/49/EC** — already cited in `METHODOLOGY.md` as the regulatory
  foundation DEFRA's mapping implements — obliges *every member state* to
  produce strategic noise maps, on the same Lden basis, for every agglomeration
  over 100,000 people. That is the same data model this product is built on,
  several hundred cities wide, rather than a per-country reinvention.

The honest summary: **the UK is a data-pipeline problem that is now mostly
solved, Europe is the same product in another jurisdiction, and North America is
a different product wearing the same interface.**
