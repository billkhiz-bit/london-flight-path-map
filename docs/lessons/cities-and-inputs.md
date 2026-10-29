# Cities, coverage and the scored inputs

> Moved verbatim from `CLAUDE.md` on 2026-10-17 to keep the session-start file small.
> Which cities are where, the input table with each builder and its --check, the one-way door, uncovered postcodes, postcode-level scoring for every city.
> Statements are dated as written; re-measure a number before relying on it, and when a
> rule here changes, update the one-line rule in `CLAUDE.md` too.

<!-- CLAUDE.md lines 73-127 (2026-10-16) -->
## Project

**THE PUBLIC COVERAGE SENTENCE (2026-10-12), the only one to quote: "97 council areas in 13 UK city regions, plus
New York's 5 boroughs and 50 Bay Area cities (facts only)".** Three versions had been live at once (97 in 13; 102
in 14; 11 and 91), each true of one surface. The counts below describe surfaces; `build_area_pages.py` counts the
sentence per country for `/area/`, and OUTREACH_TARGETS "Facts safe to quote" holds it.

**FOURTEEN cities on `/v1/score`; ELEVEN SCORED on the consumer site, as of 2026-09-27** (Greater Norwich joined the API that day, deployed and verified from the origin; see the Norwich block below). **Plus a twelfth, the San Francisco Bay Area, on the site and NOT scored (2026-10-05, release 1, DEPLOYED and verified from the origin that day)**: 50 cities with the `/bay-area/` page's facts and no number (Bill's ruling: the UK estimate is fitted against DEFRA and the Bay Area has no yardstick), a noise-map-order ranking, ZIP and name search. Its records carry `facts: true` and `updateSidebar()` / `renderBoroughRanking()` route them to their own renderers, so nothing passes through `calcScores()`; it is in no Lambda, and the parity gates read `borough-extra.json`, which it is not in. Both holders come from `scripts/build_bayarea_map_data.py` (blocking `--check`), which calls the page builder's own `facts()` / `routes()` / cell functions. Gate: `tests/bayarea-map.mjs`, blocking. **Two tiers beneath a city since the same day** (layer 1): San Francisco's 41 DataSF neighbourhoods and the 165 ZIP areas, the same facts measured over the smaller area by `scripts/build_bayarea_areas.py` (blocking, re-measures offline; its sources sit in ignored `data/datasf/` and `data/census/`). Outlines are drawn as STATE (`tierOutlineFeature`) because a phone's card opening runs `redrawForViewport()`, which rebuilds every layer and wiped a path drawn once. **Arrival routes since 2026-10-06**: each coded STAR joined to the approach transition starting where it ends, drawn from the first fix where the FAA ALLOWS 10,000 ft or lower (Bill's rule; 24 of 50 cities), stopping at radar vectors; a city's altitude is the FAA's published one at a fix INSIDE it, worded as published ("4,000 ft or above"), never interpolated. **The front page draws them since 2026-10-07**, from `data/us-bayarea-routes.json`, the third holder of `build_bayarea_map_data.py` (`route_records()` is the ONE derivation for it and the live map's block); until then the front page re-derived Bay Area lines from the raw FAA record, with whole departures and no arrivals. The legend's FAA cycle is generated (`BAYAREA_ROUTES_CYCLE`).

- **On both site and API (11):** London (33), NYC (5), Greater Manchester (10),
  West Midlands (7), West Yorkshire (5), South Yorkshire (4), Merseyside (5),
  Tyne and Wear (5), Bristol (4), **Leicester (8)**, **Teesside (5)**. That is
  **91 boroughs**, and `tests/borough-score-parity.mjs` compares the score the
  site RENDERS against the Lambda's for every one of them.
- **API only, declared in `BACKEND_ONLY_CITIES` (2):** Cardiff (4), Nottingham (4).
  **Cardiff cannot leave**: Progress 8 is an ENGLAND measure, so Wales has none.
  **Nottingham now could and does not** - the "1 of 4 inputs" recorded here for
  months stopped being true when healthcare landed in v3.7. Broxtowe, Gedling and
  Rushcliffe gained transport (v3.6) then healthcare (v3.7), so they clear the
  two-input floor and publish a liveability score. It stays on JUDGEMENT: `live`
  of 2.6 on two inputs is thinner than the site should claim.
- **Greater Norwich (3), API-only PREVIEW since 2026-09-27**: Norwich, Broadland,
  South Norfolk - the Greater Norwich Local Plan area, NOT all of Norfolk (the
  Leicester-style widening only mattered while affordability was min-max within
  a city; v5.0 made it national). Every authority has its own ONS crime row
  (3 of 3 agree) and none has Progress 8 (Norfolk is the education authority),
  so each is 3 of 4 liveability inputs. **Norwich International is NOT in DEFRA
  Round 4** (16 airports, measured via GetCapabilities), so quiet is geometry
  floored like Teesside. Runway 09 has no ILS and no RNP approach: its glide is
  the NDB chart's RECOMMENDED PROFILE gradient (5.3% = 3.03 deg), the builder's
  third published source. No SIDs published. **Adding it moved the national
  price band** (p95 720,241 -> 716,131): 33 of 792 borough/persona scores move by
  0.1, 4 under `balanced`. **The not-covered panel links a scorecard** for every
  API-only borough (`AREA_SCORECARDS`, generated by `build_area_pages.py --write`
  between markers, keyed on the ONS code postcodes.io returns), so NR2 1NE now
  reads NOT ON THE MAP with a link (no "yet" since 2026-10-07, website audit M13: Cardiff
  cannot join the map on current data, so "yet" was a promise). **The standard uncovered spot-check is
  now `EX1 1HS` (Exeter)**, which must still say NOT COVERED YET with no link.

**Leicester and Teesside went through the one-way door on 2026-08-11.** Leicester
is the city plus all seven Leicestershire districts (a four-authority cohort
spans only 230k-281k, and min-max over a narrow cohort manufactures spread it
has not measured). Progress 8 covers **1 of Leicester's 8** - education is an
upper-tier county function, the same gap as Nottingham - but transport and
healthcare carry them to 3 of 4. Teesside's five unitaries are their own
education authority, so all five are 4 of 4; it spans **two police forces**
(Cleveland and Durham) so crime needs an include-list.

Every field of the eight is **script-derived and independently verified**, and
each has a `--check` that can go red:

| Input | Script | Status |
|---|---|---|
| avgPrice / trend | `build_hpi_prices.py --check --all` | HPI **2026-08** (rolled 2026-10-22; July was rolled 2026-09-16, the day HMLR published, June 2026-08-25, and this row said 2026-05 until 2026-09-11), **blocking preflight stage**, all agree. **A monthly roll inside a quarter keeps `SNAPSHOT_VINTAGE` and moves `SNAPSHOT_VINTAGE_LABEL` + `CPIH_12M_PCT[current]` + `SNAPSHOT_CPIH_PCT` (index.html)**; `--check` reds on any of the three left behind. **Deploy with `sh scripts/deploy_hpi_roll.sh`** - backend first, then the freshness gate, then web/area/meta, then origin verification; written 2026-09-16 when the classifier refused the SAM deploy from Claude's session, so it is Bill's one command |
| roadNoise / airQuality / flood bands | `build_borough_bands.py --check` | DEFRA Round 4 road Lden + DEFRA background maps + EA RoFRS. **Air quality is every city bar NYC; road noise now is too, and flood is everything bar NYC and Cardiff** (measured from `borough-extra.json` 2026-08-30: air 86, road 86, **flood 86** of 91 - Teesside's five joined when the georeferencing fix stopped one blank sea tile from abandoning the whole city). The old note here said Leicester 0/8 and Teesside 0/5 carried NEITHER, and recorded it as a property of the data - **it was an unrun script**. Both fetchers are per-city against ENGLAND-WIDE coverages and neither city was in `NO_ROAD_COVERAGE`/`NO_FLOOD_COVERAGE`; the rasters had simply never been fetched for the two cities that joined on 2026-08-11. **A measurement recorded without its cause reads as a constraint.** Teesside's blank sea tile is still refused by the C11 guard - correctly - but its area is now carried as Unavailable instead of failing the city, so the other seven tiles publish. `paintBoroughLayer()` skips what is missing, so the MAP is honest; this row was the thing over-claiming. **Since v3.9 the BANDS are still display-only but the CONTINUOUS fields beside them SCORE** - see the `environment` row below. |
<!-- CLAUDE.md lines 269-293 (2026-10-16) -->
| **environment** (v4.0, 2026-08-29) | `build_borough_bands.py --check` / `--write --write-lambda` | **Air quality 0.45 + road noise 0.35 + flood 0.20, from `airQualityWhoRatio`, `roadNoiseAboveWhoPct` and `floodMediumOrHighPct` - the CONTINUOUS fields, never the three-band map summaries** (68.1% share the modal air band, 54.9% the modal road band). **Road noise reads the SHARE over WHO 53 dB, never `roadNoiseLdenMedian`** - the median carries 41 distinct values to the share's 69 over an IQR of 1.7 dB, and ramping it 53->63 dB clamps 19 of 73 boroughs to a perfect 10. All three anchored on PUBLISHED thresholds: WHO 2021 -> the UK legal NO2 limit; 0% -> 100% over WHO's 53 dB Lden road guideline; 0% -> the EA's 10% Medium-or-High cut. **SCORING inputs, so they live in BOTH holders** - `test_borough_data_parity.py` covers all three, plus a `NAME_ALIASES` drift guard. **Use `--write --write-lambda`, not `--sync-lambda`**: sync copies from `borough-extra.json`, which SKIPS backend-only Cardiff and Nottingham, so Nottingham would silently miss road. 90/99 carry road; **90 `measured`, 0 `partial`, 9 `unavailable` (NYC 5, Cardiff 4)** - measured 2026-09-11 through `env_resolution()`; the `partial` tier has been unreachable since the flood georeferencing fix, as the note 260 lines below already said. |
| **BOTH OF THE ABOVE ARE OVER LIVE POSTCODES ONLY SINCE 2026-09-01 (audit F38)** | `build_borough_bands.py` | NSPL keeps TERMINATED postcodes with real coordinates and they were being counted - **915,867 of them, 38.7% of the scan**. The bands were weighted toward demolished estates and redeveloped industrial land. The `(99.999, 0.0)` guard catches only the UNLOCATABLE ones, which is why this looked handled; four sibling scripts already read `doterm`. The reader now HARD-FAILS if the column is absent, or if a scan that kept rows found no terminated ones. Same pass, **audit I3**: DEFRA road `0.0` means "surveyed, below the lowest mapped band" and was being dropped from the SHARE's own denominator, so `roadNoiseAboveWhoPct` was computed among the noisier postcodes only; `sample_raster` returns `(mapped, surveyed, inside)` now and the median alone stays over mapped readings. Its flood sibling twenty lines below had explained the identical trap all along. **Together: 811 fields updated across both holders.** |
| transport | `build_borough_bands.py --write --write-lambda` | **NaPTAN, share of postcodes within 800 m of a rail/metro/tram node. A SCORING input (0.25 of liveability), so it lives in BOTH holders — `tests/test_borough_data_parity.py` fails the build on drift. Methodology v3.6, 2026-08-11.** |
| crimeRate | `refresh_crime_from_ons.py --check --all` | ONS Table C4, 0 differ; **blocking preflight stage since 2026-08-24, with a PER-CITY floor** (it used to pass having compared zero). **`--write-lambda --all` writes the Lambda's copy since 2026-10-23** (the first quarterly roll: it had been "mirror it by hand", ninety rates; its first run skipped Barking and Dagenham, keyed 'Barking' on the site, until a per-borough floor refused to write and the alias was limited to the site's copy). **`--write --all` writes every holder city since 2026-09-13** - it was London-only, and for the eight cities it never reached the panel printed TWO false sentences from the absent fields: "Offence breakdown not published for this area" (audit I5; Table C4 carries it for every CSP row) on 53 boroughs, and on the 43 with no `crimeVintage` a DISCLAIMER of ONS - "Sky Score estimate - ONS publishes no recorded-crime rate for this area" - on figures that are ONS's and that this very gate verifies against ONS. Measured live on Birmingham. `crimeTop` is now 85 of 91 (NYC and the City of London are the honest absences), `vsLondonMedian` divides by LONDON's per-offence medians for every city so the label stays true, and no rate and no London record moved. The Oct roll is `--check --all`, then `--write --all`, then mirror any moved rate into the Lambda registry (`test_borough_data_parity.py` reds until you do). |
| p8 | `build_progress8.py --check` | **DfE KS4 2023/24 Revised (rolled 2026-08-27)**, 79 compared, 0 differ; advisory preflight stage since 2026-08-24 (its gitignored KS4 bundle cannot be auto-fetched - EES 403s non-browser UAs - so blocking would gate every fresh clone). **2023/24 IS AVAILABLE AND NOT ROLLED (verified against DfE 2026-08-27).** The script used to claim 2022/23 was terminal until 2026/27; the mechanism was right and the boundary one year early - the cohorts with no KS2 baseline are **2024/25 and 2025/26**, and DfE's own 2024/25 release says exactly that, while 2023/24 (published 2025-02-27) carries P8 as a headline measure. **Costed, not guessed: 72 of 79 boroughs would move, none by more than ±0.20**, mean +0.008, 33 up / 39 down, none dropping out - currency, not a re-basing. One blocker, now handled: DfE renamed the `gender` column to `sex`. Area pages BAKE scores, so a roll must rerun `build_area_pages.py --write`. |
| impact | `build_aircraft_bands.py --check` | geometry ESTIMATE, ladder scaled by DEFRA footprint. **The near-field floor is a CONTOUR TEST since 2026-09-01, not a disc** - see the block below. Its measurement lives in **`data/aircraft-footprint.json`** and NOT in `<something>-boroughs.json`: **that suffix is a CONVENTION five scripts glob to enumerate the cities** (`check_flood_georef`, `fetch_ea_flood_risk`, `fetch_defra_road_noise`, `fit_city_projection`, `build_city_stations`), and the original name invented a phantom city called "aircraft-footprint" that the blocking flood gate caught the same day. Do not name a non-city data file `*-boroughs.json` |
| boundaries | `build_city_boroughs.py --all` | ONS codes, counts asserted |

**Leaving `BACKEND_ONLY_CITIES` is a ONE-WAY DOOR.** The moment a city drops
out, the site must reproduce the API on every borough, and
`test_backend_only_cities_are_declared_not_discovered` fails in both directions
to force it. Six cities went through that door on 2026-08-10; before opening it,
all 30 of their boroughs were compared site-vs-Lambda as an OUTPUT check.
Input parity is not enough - the Manchester incident had matching inputs on both
sides and still diverged by up to 1.5 points, because the site never loaded them.

**Boundaries load through one registry-driven path**, `loadCityBoundaries()`
reading a `boundaries` field. It used to be `if london / else if manchester /
else NYC`, whose own comment described the bug it had already caused.

**Cardiff and Nottingham can never fully leave** on current data: Progress 8 is
an ENGLAND measure so Cardiff has none, and Nottingham gets 1 of 4 because
Broxtowe, Gedling and Rushcliffe are districts inside `South Nottinghamshire`
rather than local authorities. Both also have that gap in ONS crime.

<!-- CLAUDE.md lines 304-354 (2026-10-16) -->
**A POSTCODE NO CITY COVERS IS TOLD SO (2026-09-26, deployed).** The site used to
analyse it against whichever city was on screen: a user near Norwich emailed that
it named a London airport, and live, NR2 1NE read "Nearest airport: Stansted
(109.4 km)" and "low aircraft noise", ~5 km from Norwich Airport. It now renders
NOT COVERED YET (`renderOutsideCoverage()`), and a null from
`deriveCityFromBorough()` is a third state, never "keep the current city".
**Spot-check with `EX1 1HS`** (Exeter) - the standard uncovered postcode since 2026-09-27; `NR2 1NE` now links Norwich's scorecard. The same audit
found "St. Helens" (postcodes.io) vs "St Helens" (registry): both matchers drop
full stops now. Gate: `tests/outside-coverage.mjs`, blocking, postcodes.io
stubbed, plus all 86 covered boroughs' real postcodes.io spellings in
`tests/fixtures/postcodes-io-districts.json`. The API already 404s these.

**Postcode-level scoring works for every city — REALLY, since 2026-08-12.** The
gate was `if city != 'london': return 400` and was lifted on 2026-08-10, and the
recorded reason for it — that NSPL writes the borough attribute for London LADs
alone — was half the story. NSPL writes the LAD **code** for all 2.7M rows, so
`LAD_TO_BOROUGH` resolves the rest and **no reload was needed**. Verified against
the live table: M1 1AE carries `lad=E08000003` with `b` absent.

**But it did not actually work until 2026-08-12, and this file said it did for
two days.** `city` defaults to `'london'` and **nothing derived it from the
resolved LAD**, so `/v1/score?postcode=M1+1AE` answered *"Borough not currently
supported in london."* — naming a city the caller never mentioned. B15, LS1, S1,
BS1 and NG1 all did the same. The un-gating was genuine (`?city=manchester` with
that postcode scores 7.7); it simply could not be reached without supplying the
answer in the question, which no documented caller does.

- **Every piece was correct and the feature still did not exist.** The un-gating
  commit, `LAD_TO_BOROUGH`, and the postcode table were all right — the row for
  M1 1AE was verified by hand and written up above. Nothing joined them. **When
  a capability lands, exercise it the way a caller would**, not the way the code
  is organised.
- **The fix is three parts and one was not enough.** Derive the city from
  `_ladCode`; fall back to a borough-NAME index because the postcodes.io tier
  carries no LAD code (a code-only fix repairs the loaded tier and leaves the
  fallback answering london); and absorb the qualifier inversion — ONS writes
  `City of Bristol`, postcodes.io returns `Bristol, City of` — in **both** the
  derivation and `normalise_borough`, or Bristol and Nottingham resolve the right
  city and then 404 one step later on the borough.
- **A passing test asserted the defect.**
  `test_resolve_query_404_unchanged_for_non_london` was correct when written, was
  never revisited when the gate lifted, and so spent two days reporting the bug as
  expected behaviour — reading as evidence the endpoint worked.
  `PostcodeCityDerivationTests` replaces it, asserts the **derived city** rather
  than that a score came back (a London default returns a well-formed error), and
  is proven red.
- **Nothing else could have caught it**: `check_score_sanity.py` probes 16 LONDON
  postcodes, `borough-score-parity` compares boroughs by NAME, and every other
  unit test passed a `city` alongside the postcode. Widening the sanity probes
  beyond London is the open follow-up.

<!-- CLAUDE.md lines 637-639 (2026-10-16) -->

Sky Score, a property noise + livability data tool for UK and NYC. Originally built for the Amazon Nova AI Hackathon; pivoted in May 2026 from "AI-powered" to "data-first" positioning. Consumer site is the marketing engine; the B2B `/v1/score` API is the product. Single-page frontend (`index.html`) plus B2B funnel pages (`/api/`, `/pricing`, `/privacy`) backed by the 8 active AWS Lambda functions orchestrated via SAM (the 4 dormant Bedrock Lambdas live in git history only; `live_flights` was removed in May 2026 pending OpenSky licensing).

