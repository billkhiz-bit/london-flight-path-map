# Sky Score data-source licensing audit

Every external data source used by Sky Score, with the licence terms,
our use case (consumer site / B2B API / both), required attribution,
and any obligations or restrictions. This is the canonical reference
for "are we allowed to use this commercially" questions.

**TL;DR:** every UK government source is **OGL v3.0** (commercial use OK
with attribution), TfL is similar,
**OpenStreetMap is ODbL and is NOT "similar"** — see the note below,
MHCLG EPC needs attribution + bearer token, Bedrock is a paid AWS
service (and the consumer-side AI features that used it were removed
end-to-end; their Lambda code + template entries live in git history
only, verified 2026-07-23).

> **ODbL is share-alike, not just attribution — corrected 2026-08-05.**
> This TL;DR previously grouped OpenStreetMap with OGL and TfL as
> "similar". It is not. OGL and the TfL licence permit commercial reuse
> on attribution alone; **ODbL 1.0 additionally requires that a
> *Derivative Database* be offered under ODbL**, which for a paid B2B
> product is a materially different obligation. `privacy.html` §5 has
> described it correctly as "share-alike rather than permissive" since
> 2026-08-03, so the two documents disagreed, and the more permissive
> reading was the one sitting in the licensing file.
>
> **Why our current use is very likely outside the share-alike trigger,
> stated so it can be re-checked rather than assumed:**
> 1. ~~OSM is reached through Overpass **per request, as a transient
>    passthrough** for the `/nhs` nearby-facilities panel. Nothing is
>    stored, so there is no database of ours for the term to attach to.~~
>    **NO LONGER TRUE, corrected 2026-08-12.** `backend/lambdas/nhs/london_healthcare.json`
>    is a **stored 3,224-element OSM extract (458 KB) bundled inside the
>    deployed Lambda** and read on the hot path (`nhs/app.py:112`), built by
>    `scripts/fetch_london_healthcare.py`. The re-open trigger below ("if OSM
>    output is ever cached, stored") fired when that snapshot landed and was
>    not actioned. **This is a stored extract of an ODbL database**, so the
>    share-alike question is live and needs an actual answer rather than the
>    assumption above. Point 2 still holds and is what limits the exposure.
> 2. **The healthcare component of the liveability score does not come
>    from OSM**, and that is the load-bearing separation. It comes from
>    `data/borough-extra.json`, derived from the **NHS Organisation Data
>    Service** register since methodology v3.7 (`scripts/fetch_nhs_gp_practices.py`)
>    — OGL, not ODbL. (This file used to describe that field as our own
>    editorial work; see the corrected row in the table below.)
> 3. Attribution is emitted in the `/nhs` response, which ODbL requires
>    regardless.
>
> **Re-open this if any of those three stop being true** — in particular
> if OSM output is ever cached, stored, or fed into a scored component.
> At that point the question becomes whether `/v1/score` output is a
> Produced Work or a Derivative Database, and that is a question for a
> solicitor, not for this file.
**OpenSky was removed entirely on 2026-05-07** — see "Removed sources"
below. We're clean for both consumer + B2B.

---

## Sources used by the B2B API (`/v1/score`)

These appear in the `sources` array of every `/v1/score` response.

| Source | Licence | Use | Attribution | Status |
|---|---|---|---|---|
| **DEFRA Strategic Noise Mapping — road Lden** (Round 4, 2022, England) | [OGL v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) | Borough `roadNoise` band and `roadNoiseLdenMedian` (display-only), and — **SCORED since methodology v4.0 (2026-08-29)** — `roadNoiseAboveWhoPct`, the share of a borough's postcodes at or above WHO 2018's 53 dB road guideline, which is **0.35** of the `environment` component. Also returned per postcode by `/v1/environment` as `roadNoiseLdenDb` - or, where DEFRA surveyed the ground and found it under the lowest level its map records (40 dB, 2.0% of covered postcodes), as the BOUND `roadNoiseBelowDb`, never as a decibel figure. **Every English city since 2026-09-10**; it was London-only before that. **England only** — the coverage is England's, so Cardiff is excluded by name (`NO_ROAD_COVERAGE`) and New York carries none. **This row did not exist until 2026-08-31**: the surface was licensed and attributed under the aircraft row below, which describes a different coverage and does not mention scoring, so the one environmental dataset carrying the largest scored share after air quality had no licensing entry of its own. | "Contains public sector information licensed under the Open Government Licence v3.0" | ✅ Commercial use OK |
| **DEFRA Strategic Noise Mapping** (Round 4, 2022) | [OGL v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) | (a) Quiet score (Lden bands per borough; raster sample at postcode centroid in v3.1). (b) Consumer-site overlay PNG cached on our origin (refreshed via `scripts/refresh_aircraft_noise.sh` when DEFRA publishes a new round, ~5-year cadence). | "Contains public sector information licensed under the Open Government Licence v3.0" | ✅ Commercial use OK |
| **HM Land Registry House Price Index (HPI)** | OGL v3.0 | Affordability + Growth scores (price log-scaled against the national p5-p95 band since methodology v5.0; real-terms trend dual-anchored against the whole sterling pool since v5.2 - neither is city-cohort-relative any more). Credited in every UK `/v1/score` response - London's line was missing from 2026-08-25 to 2026-09-07, see the note below this table. | **Not "same OGL boilerplate"** (corrected 2026-09-07). HMLR requires its own notice: *"Contains HM Land Registry data (c) Crown copyright and database right YYYY. This data is licensed under the Open Government Licence v3.0."* The project already holds that wording, in the docstring of `scripts/build_city_neighbourhoods.py` - the very script that derives the 481 published medians - and it does not reach any output. | ✅ Commercial use OK |
| **HM Land Registry Price Paid Data** | OGL v3.0 | Recent sold-price comparables (`/sold_prices`) | Same OGL boilerplate | ✅ Commercial use OK |
| **MHCLG Energy Performance of Buildings Register** (`/epc`) | OGL v3.0 + bearer-token T&Cs | EPC band lookup per address | "EPC data: MHCLG, Open Government Licence v3.0" + comply with new bearer-token terms | ✅ Commercial use OK with token rotation hygiene |
| **ONS CPIH, 12-month rate, all items** (series L55O, dataset MM23) - *since methodology v5.1, 2026-09-15* | OGL v3.0 | Deflates the HPI 12-month trend to real terms for the Growth score, one value per vintage month (`CPIH_12M_PCT` in the score Lambda; July 2026 3.1%, May 2026 3.0% - the current entry rolls with the HPI month). Sterling cities only - New York's growth stays nominal because no US series is held. Credited in every UK `/v1/score` response as "Inflation: ONS CPIH 12-month rate ... Open Government Licence v3.0", and published as `context.inflationPct` so the deflation is reproducible. | OGL boilerplate | ✅ Commercial use OK |
| **ONS National Statistics Postcode Lookup (NSPL)** — *live resolver since 2026-07-25* | OGL v3.0 | **Primary** postcode → borough + lat/lon resolution, served from our own DynamoDB table (`london-flight-map-postcodes`, loaded by `scripts/load_nspl.py`). Also still the input to the DEFRA raster sampler — see the offline table below. | "Postcode resolution: ONS National Statistics Postcode Lookup (Open Government Licence v3.0), with postcodes.io (Open Government Licence v3.0) as fallback" — emitted only once the local tier has actually served a lookup, so the credit is never claimed while the table is empty | ✅ Commercial use OK |
| **postcodes.io** (api.postcodes.io) | OGL v3.0 (data) + MIT (the service) | Postcode → admin_district resolution. **Demoted to fallback 2026-07-25**: used when the local NSPL table misses, is unloaded, or errors. The move was made partly for licence hygiene — routing a customer's 100k-address backfill through a free community service is not fair use, whatever the data licence permits. | "Postcode resolution: postcodes.io (Open Government Licence v3.0)" — still the sole credit whenever the local tier has not served | ✅ Commercial use OK |
| **ONS** (population, deprivation, recorded crime) | OGL v3.0 | Liveability composite + crime score normalisation. **Primary crime rate since 2026-08-02**: *Crime in England and Wales*, Police Force Area data tables, year ending March 2026, **Table C4**, offences per 1,000 residents on mid-2024 population. | OGL boilerplate | ✅ Commercial use OK |
| **Department for Education** (Key Stage 4 Progress 8) | OGL v3.0 | Liveability "schools" sub-score. **Re-sourced 2026-08-02** (methodology v3.5): was Ofsted overall-effectiveness grades, which Ofsted abolished in September 2024 and which never reproduced from the published distribution anyway. Now Progress 8, **2023/24, local-authority level (rolled 2026-08-27 from 2022/23)** — and 2023/24 IS the last edition until 2026/27 publishes, because the 2024/25 and 2025/26 cohorts lost their KS2 baseline to the cancelled 2020/2021 test windows. The earlier claim that *2022/23* was terminal was wrong by one year: the cancelled sittings were 2020 and 2021, so 2023/24's cohort (KS2 in 2018/19) has a baseline, and DfE published it on 2025-02-27. | OGL boilerplate | ✅ Commercial use OK |
| **Home Office** (recorded crime statistics) | OGL v3.0 | **Superseded 2026-08-02** — the crime sub-score now reads ONS *Crime in England and Wales* Table C4 (row above). Listed here because scores published before that date used it. | OGL boilerplate | ✅ Commercial use OK |
| **NaPTAN** (DfT National Public Transport Access Nodes) | OGL v3.0 | Two uses, deliberately separate. (a) Liveability **`transport`** sub-score for every borough since methodology v3.6 — share of a borough's postcodes within 800 m of a rail/metro/tram node, a **scored input at 0.25 of liveability**. (b) Since 2026-08-12, the **1,415 stations listed in the detail panel's nearest-stations section** (`scripts/build_city_stations.py`) — **display only**, and deliberately not scored, because scoring them too would count (a) twice. This said "drawn on the map's transport layer" until 2026-09-01; that layer was **deleted on 2026-08-12**, the same day the data landed. The count fell from 1,651 on 2026-09-01 (audit I19: one tram stop was being published as up to five "stations", and 806 retired NaPTAN nodes shipped as current). | OGL boilerplate | ✅ Commercial use OK |
| **NHS Organisation Data Service** (ODS) | OGL v3.0 | Liveability **`healthcare`** sub-score since methodology v3.7 — share of postcodes within 500 m of a GP practice (role RO76). **Scored input at 0.10 of liveability.** Deliberately NOT OpenStreetMap: that choice is what keeps the score clear of ODbL share-alike. | OGL boilerplate | ✅ Commercial use OK |
| **Environment Agency** — Risk of Flooding from Rivers and Sea (RoFRS/NAFRA2) | OGL v3.0 | Borough `flood` band, via the published WMS (no WCS/WFS exists). **SCORED since methodology v3.9 (2026-08-26)**: `floodMediumOrHighPct` is **0.20** of the `environment` component (0.35 until methodology v4.0, 2026-08-29, when road noise became the third scored input; corrected here 2026-08-31). The three-band summary beside it remains display-only. England only — Natural Resources Wales publishes Wales's own, so Cardiff carries air quality without flood. | OGL boilerplate | ✅ Commercial use OK |
| **DEFRA background air-quality maps** (modelled annual mean NO₂ / PM2.5, PCM 1 km grid) | OGL v3.0 | Borough `airQuality` band, the per-postcode NO₂/PM2.5 figures returned by `/v1/environment`, and — **SCORED since methodology v3.9 (2026-08-26)** — `airQualityWhoRatio`, which is **0.45** of the `environment` component (0.65 until methodology v4.0, 2026-08-29; corrected here 2026-08-31). Whole-UK coverage including Wales, so all 13 cities carry it; New York does not, DEFRA being a UK source. | OGL boilerplate | ✅ Commercial use OK |
| **DEFRA Automatic Urban and Rural Network (AURN)**, reference monitors, annual means from the openair summary files on uk-air.defra.gov.uk. **Added 2026-10-13** | OGL v3.0 ("exploit the information commercially and non-commercially", UK-AIR data page, read 2026-10-13) | `data/aurn-sites.json` (`scripts/fetch_aurn.py`): each site's NO2 and PM2.5 annual mean for the PCM year, ratified, on at least 75% of the year's hours, for a "nearest official monitor" line beside the PCM figure. **Display only, never scored.** Read by the front page, the full map's postcode panel and both street reports since 2026-10-19 (built, with the Breathe London line): the nearest monitor within 5 km, in every city. UK-AIR warns that ranking sites is "not scientifically sound", so sites are never ordered by these numbers | The statement UK-AIR requires, word for word, with a link to the OGL: "© Crown 2026 copyright Defra via uk-air.defra.gov.uk, licenced under the Open Government Licence (OGL)." (held in the file; `--check` fails on any other wording) | ✅ Commercial use OK |
| **Breathe London** (Greater London Authority), low-cost air sensors, hourly NO2 and PM2.5 from the GLA's Breathe London API (`breathe-london-7x54d7qf.ew.gateway.dev`, key in an `X-API-KEY` header). **Added 2026-10-19** | OGL v3.0 (breathelondon.org/developers, read 2026-10-11). The key is issued to us by the GLA and is held only in the gitignored `.env`; no page or visitor calls the API. The separate **Communities API** (Imperial Projects) is NOT used: non-commercial without written approval, and "no automated extraction". **The GLA API also lists the Imperial-run 2021-2024 network** (checked 2026-10-21 after Imperial asked about commercial use of "BLC data"): `/ListSensors` carries `SensorContract` "Imperial" (140 installations, started 2021-01 to 2024-05, all ended by 2024) or "Vodafone" (187, from 2025-03; all 153 live ones), and `/SensorData` returns a site code's Imperial-era hours too. Every sensor we show (116) is Vodafone-contract and the 12-month window (Oct 2025 - Sep 2026) holds no Imperial-era hour; never widen the window or backfill before 2025-03 without asking Imperial Projects first | `data/breathe-london-sensors.json` (`scripts/fetch_breathe_london.py`): each live sensor's 12-month NO2 and PM2.5 mean (the 12 whole months before the fetch), on at least 75% of the window's hours, with its borough, classification and kerb distance, for a "nearest sensor" line beside DEFRA's background figure in London. **Display only, never scored.** Read by the front page, the full map's postcode panel and both street reports (built 2026-10-19: the nearest sensor within 5 km of a London postcode). Values are provisional and recalibrated by the network, and kerbside and background sensors measure different things, so sensors are never ranked | "Contains Breathe London data licensed under the Open Government License v3.0", linked to breathelondon.org, word for word wherever a reading is shown (held in the file; `--check` fails on any other wording). Never imply Breathe London or the GLA endorses Sky Score | ✅ Commercial use OK |
| **FAA Coded Instrument Flight Procedures (CIFP)** (`aeronav.faa.gov`, ARINC 424, a new cycle every 28 days). **Added 2026-10-02** | Not copyrighted: "The CIFP is not copyrighted under Title 17 U.S.C." (FAA CIFP Disclaimer, shipped in the zip, read 2026-10-02). **One obligation**: the FAA "requires that product developers and manufactures include warranty disclaimers" - the product is provided "as is", neither the FAA nor its personnel is liable, and under 10 U.S.C. 456 no civil action may be brought against the United States on the basis of its content | `data/us-flight-procedures.json`: runway thresholds, glide angles and coded departure routes for seven US airports (`scripts/build_us_flight_paths.py`). **Published on `/bay-area/` since 2026-10-02** (the routes of SFO, OAK and SJC); **New York's score and full map read its routes since v5.6 (2026-10-16)**, and every New York response's `sources` carries the "as is" line | Credit the FAA, and carry its warranty disclaimer on any page or product that shows a route derived from it. `/bay-area/` carries it under "Sources", and `tests/test_bay_area_page.py` fails the build if the wording goes. **The front page carries it too since 2026-10-07** (its footer's `.route-credit`: "the FAA's Coded Instrument Flight Procedures, supplied "as is", without warranty. Not for navigation."), checked in `tests/front-page.mjs`. This row said GAP until 2026-10-12, five days after the fix shipped | ✅ Disclaimer carried wherever its routes are shown |
| **UK Aeronautical Information Publication (UK AIP)**, NATS Aeronautical Information Service (`www.aurora.nats.co.uk`, a new AIRAC cycle every 28 days). **Entry added 2026-10-03: the routes have been derived from it since v5.3 (2026-09-26) and this table had no row for it** | **No licence is granted in so many words.** The AIP's own "UK Aeronautical Information Product Terms and Conditions" (GEN 0.1 section 5, AIRAC 2026-10-01, read 2026-10-03): NATS "accepts no liability for your use" (5.3); it acknowledges "commercial organisations and other third-parties that provide data services and/or process data using information sourced from official UK Aeronautical Information Products, and who then make this information available to users within their own products and services (with or without charge)" (5.4); and "every data user is liable for any damages caused by any modification made by it to the data" (5.5). **Separately**, the terms of NATS's corporate website (nats.aero, read the same day) forbid reusing "content of this Website for commercial purposes without first obtaining a licence"; nothing read says whether those reach the AIP on the aurora host | `data/flight-procedures.json`: runway thresholds, glide angles, noise preferential routes and SID coding tables for the UK airports (`scripts/build_flight_paths.py`), which generate the flight paths in the Lambda and `index.html`, feed the `quiet` estimate, and are drawn on `/preview/` and in the street report. Facts are extracted; no chart or page of the AIP is reproduced | Credit "UK AIP, NATS" wherever the routes are shown, say the lines are derived by Sky Score and are not for navigation, and report any error found to UK AIS as 5.5 asks. **The API carries it since 2026-10-07 (committed, not yet deployed)**: `/v1/score` `sources` ends with "Flight routes: UK Aeronautical Information Publication (NATS), derived by Sky Score for the aircraft noise estimate; public but not openly licensed, and not for navigation" for every city whose quiet geometry reads an AIP airport (derived per city in `_aip_airports()`, so South Yorkshire and New York carry none), and `sourceBreakdown.quiet` names the airports. The area pages print that line rather than adding their own | **Free uses: no term read forbids them. Before the first PAID report or licence that rests on the routes, ask NATS AIS to confirm in writing** (the wider "who holds the reuse rights" question is already in the drafted CAA request). Not legal advice |
| **Ordnance Survey, OS Maps API** (`api.os.uk`, OpenData layers, style `Light_3857`). **TRIAL on `/preview/` only, added 2026-10-03** | OS OpenData. ROADMAP records OS's statement that the open layers cost nothing on any Data Hub plan; **the OS Data Hub API terms themselves have not been read** | A street background under the preview's map, drawn ONLY on a device that has been given a Data Hub key (`/preview/?oskey=`, held in that browser's storage, never in the source). No ordinary visitor's browser contacts `api.os.uk` | "Contains OS data (c) Crown copyright and database right 2026", shown on the map whenever the layer is on | **Trial only.** Before it is on for visitors: read the API terms, list `api.os.uk` in privacy.html and SUBPROCESSORS.md as a host the browser contacts, or self-host OS Open Zoomstack instead so no third party is contacted at all |
| **US Census Bureau cartographic boundary files, 2023** (`www2.census.gov/geo/tiger/GENZ2023/`, places and counties at 1:500,000). **Added 2026-10-02** | US federal public domain | The city, town and county outlines on `/bay-area/` (`data/us-bayarea-places.json`, simplified). Generalised by up to a few hundred feet, which the page says | None required; credited on the page | OK |
| **US Census Bureau ZCTA gazetteer (2024) and the 2020 ZCTA-to-county and ZCTA-to-place relationship files** (`www2.census.gov/geo/docs/maps-data/data/`, plain downloads, no API key). **Added 2026-10-04** | US federal public domain | `data/us-bayarea-zips.json`: the 165 ZIP areas of the four Bay Area counties, each with its centre point, its county and the city holding the most of its land with that share (`scripts/build_bayarea_zips.py`). Read by the ZIP search on `/preview/`; the score Lambda will read it when the Bay Area has an entry there. These are ZIP Code Tabulation Areas, the Census's map of ZIP delivery areas, not the Postal Service's ZIPs | "US Census, 2020" beside the share on the card | OK |
| **US DOT NTAD** - BTS National Transportation Noise Map, **2022 edition** (released May 2026), served from `tiles.arcgis.com`, the host BTS itself names for its web services. **Repointed 2026-10-02**: the old host `geo.dot.gov` stopped answering | US federal public domain ("a work of the United States government ... available for unrestricted public use"; BTS asks to be acknowledged) | The AVIATION noise map layer on the **New York** view (`index.html`); the road layer was never requested. Metric: 24-hour LAeq, which BTS says is for tracking trends and "should not be used to evaluate noise levels in individual locations". Requested by the visitor's browser, so the layer host receives their IP and map bbox. Display only; nothing here is scored. **Added 2026-09-07** - in live use and absent from this file. **Since 2026-10-02 also a stitched copy on our own origin**, `bay-area/aircraft-noise-laeq-2022.png` (56 tiles over the Bay Area, fetched once by `scripts/build_bay_area_page.py --fetch`), so that page asks the visitor's browser for nothing from the tile host. The page reports each city's SHARE of area on the map and no decibel figure, and repeats BTS's caveat. | None required; credited on the page | OK |
| **FEMA National Flood Hazard Layer** (`hazards.fema.gov`) | US federal public domain | New York flood layer, browser-requested. Display only. The Environment Agency row above is England only, which is why New York has a separate source and no `environment` score. **Added 2026-09-07.** | None required; credited on the page | OK |
| **US EPA** (`gispub.epa.gov`) | US federal public domain | Air-quality non-attainment areas on the New York view, browser-requested. Display only. **Added 2026-09-07.** | None required; credited on the page | OK |
| **New York borough inputs** (curated) | Compiled by Sky Score from public NYC sources | **SCORED.** NYPD CompStat-derived offence rates per 1,000, curated borough median sale prices (USD), and JFK/LaGuardia approach-geometry aircraft bands - `CITIES['nyc']` in the score Lambda. **Added 2026-09-07**, and this was the largest gap in this file: five boroughs of a commercial API scored from inputs with no licensing position recorded anywhere. They are DERIVED figures, not a redistributed dataset, and `/v1/score` states so - every NYC response carries *"OGL v3.0 covers UK Crown copyright and does NOT apply to any data in this response."* | Sky Score is the source; no third-party notice required | Own work |
| **OurAirports** | Public domain (CC0 dedication) | Runway coordinates and geometry behind every non-London `impact` band (`scripts/build_aircraft_bands.py`). | None required; credited anyway | ✅ Commercial use OK |
| **TfL Open Data** (`/transport`) | [TfL Open Data licence](https://tfl.gov.uk/info-for/open-data-users/our-open-data) | **Line status only, London only, display only.** Corrected 2026-09-07: this row claimed the liveability **`transport` sub-score** and the nearby stations. Both moved to **NaPTAN** - the sub-score at methodology v3.6 (2026-08-11) and the station list on 2026-08-12 - and the NaPTAN row two above has said so since. `backend/lambdas/score/app.py` contains no TfL call at all; the only caller is `backend/lambdas/transport/app.py`, which the detail panel uses for disruption. So this row credited TfL for a scored input it does not supply, in the file whose purpose is to say who supplies what. | "Powered by TfL Open Data. Contains OS data © Crown copyright and database rights..." | ✅ Commercial use OK |

**Conclusion for the B2B API**: every data source is commercial-use-OK
under OGL v3.0 or equivalent open licence, **with one exception**: the UK
AIP (NATS) flight routes, which no licence covers in so many words (see
its row above, including the written confirmation to seek before the
first paid product that rests on them). Attribution is enforced via
the `sources` array in every API response, the AIP's included since
2026-10-07. We are **clean to charge for
the API** (per-query, subscription, or usage-tier).

---

## Sources used by the consumer site (`https://skyscore.co.uk`) only

These are visible to consumer-site visitors but NOT exposed via the B2B API.

| Source | Licence | Use | Attribution | Status |
|---|---|---|---|---|
| **OpenStreetMap** (via Overpass API) | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/) | Nearby NHS services in `/nhs` (replaced the deprecated NHS Service Search public key) | "OpenStreetMap contributors (ODbL)" — must include in response + visible attribution on the page | ✅ Commercial use OK; **attribution is mandatory** |
| **Office for National Statistics** (NSPL via Geoportal — offline uses) | OGL v3.0 | Postcode lat/lon for the v3.1 raster sampler, **and** the source loaded by `scripts/load_nspl.py` into the live resolver table (see the primary table above). The same on-disk `data/nspl.csv` now feeds both. | OGL boilerplate | ✅ Commercial use OK |
| **DEFRA GeoTIFF (Round 4, 2022)** | OGL v3.0 | Sampled offline by `scripts/load_defra_raster.py`. v2 (with below-threshold sentinel) shipped 2026-05-06; loader running 2026-05-07 against the full ~2.5M NSPL postcode list. Same source as the live noise mapping. | Same OGL boilerplate | ✅ Commercial use OK |
| **House of Commons Library MSOA Names v2.1** (2021 MSOAs) | [OGL v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) | **Verification only, never displayed and never scored.** `scripts/build_city_neighbourhoods.py --check-names` corroborates each of the 281 curated postcode-district labels against that district's own published MSOA names, so a label cannot claim a place no source puts there. The derived join lives in `data/district-msoa-names.json`; the 663 KB source CSV stays local. | OGL boilerplate; not surfaced to users because nothing derived from it reaches a page | ✅ Commercial use OK |
| **`data/borough-extra.json`** — **mostly third-party derived since 2026-08-11, not editorial** | Third-party, all OGL v3.0 (see the five rows added above); the residual `crime`/`schools` PROSE tiers on 38 boroughs remain own editorial work | Borough-level air-quality, flood-risk, schools, crime, transport and healthcare ratings + prose notes shown in the detail panel; also drive the air-quality and flood map fills (the map layers colour boroughs from this file, not from live DEFRA/EA/EPA/FEMA services) | UI badges label these "borough-level rating (curated)" since 2026-07-23 | ✅ No third-party licence involved; must never be presented as official agency data |

---

## Removed sources

| Source | Used for | When removed | Why |
|---|---|---|---|
| **OpenSky Network** (`/api/states/all`) | Live aircraft positions on the consumer-site map and the 3D radar prototype's "live mode" | 2026-05-07 (commit `6f6ce7d`) | Re-reading [their terms](https://opensky-network.org/about/terms-of-use) confirmed a written agreement is required for any operational use, including consumer surfaces. Lambda + UI both removed end-to-end pending a licensing reply. Email enquiry sent — see `OPENSKY_LICENSING_EMAIL.md`. Restoring is `git revert 6f6ce7d` + add OpenSky params back to `.env` + redeploy. |

---

## Backend infrastructure (paid services)

Not "data sources" but listed for completeness.

| Service | Type | Notes |
|---|---|---|
| **AWS Bedrock — Amazon Nova 2 Lite + Nova Pro** | Paid AWS service | Per-token billing; commercial use is the intended use |
| **AWS Lambda / API Gateway / S3 / CloudFront / DynamoDB / ACM** | Paid AWS services | Standard commercial AWS terms |
| **Cloudflare DNS / Cloudflare Registrar** | Free / at-cost | Standard Cloudflare ToS |

---

## Code shipped to visitors' browsers

Third-party code the site serves from its own origin (vendored in `js/vendor/`, bytes kept exact by `js/vendor/* -text` in `.gitattributes`). Fonts are self-hosted too; see `scripts/vendor_fonts.py`.

| Code | Licence | Where it runs | Obligation |
|---|---|---|---|
| **d3** v7 (`js/vendor/d3.v7.min.js`) | ISC | The full map (`/map/`), the front page | Keep the copyright notice in the file (it is in its header) |
| **qrcode-generator** 2.0.4 by Kazuhiko Arase (`js/vendor/qrcode-generator-2.0.4.mjs`). **Added 2026-10-06** | MIT | The free street report (`/reports/street/`): the QR code that opens a copy's check link | Keep the copyright and licence notice in the file (it is in its header). Audited before vendoring: no network calls, no dynamic code. "QR Code" is a registered trademark of DENSO WAVE, as its header says |

---

## Attribution surfacing — where the OGL boilerplate appears

| Surface | How attribution is shown |
|---|---|
| `/v1/score` response | `sources` array (always returned) + `sourceBreakdown` per-component |
| `/v1/score/batch` response | Same `sources` array on the wrapper |
| `/epc`, `/sold_prices`, `/transport`, `/nhs` responses | Each has its own `sources` array |
| Consumer site | Footer link: "Methodology v5.0" → links to the methodology document which lists every source with full attribution + licence |
| Methodology document (`METHODOLOGY.md`) | Section 11 enumerates every source + licence reference |
| `/v1/regions` discovery endpoint | Includes `methodologyVersion` + `methodologyUrl` so integrators can audit licensing |
| **Bulk scoring export** (`scripts/score_bulk.py`) | **Two places, deliberately.** A `sources` column on **every** row naming the sources and OGL v3.0, plus a companion `<output>.sources.txt` carrying the full attribution, the OGL link, and the ONS/OS/Royal Mail copyright notices |

Attribution requirements are **structurally satisfied on the scoring path**,
and there are three exceptions. Corrected 2026-09-07: this read "there is no
code path in the API that returns data without the source array", which was
an absolute claim that three live endpoints falsify.

- **`/badge`** returns an SVG whose entire text content is the score, the
  band and the postcode. No attribution at all, and it is the surface
  designed to render on third-party listing pages, so it is the one where
  the obligation travels furthest from us.
- **`/v1/environment`** returns DEFRA road Lden and DEFRA PCM NO2/PM2.5
  with no `sources` key. The browser extension renders only what that
  response carries, so its Environment section shows no OGL line while its
  EPC, sold-price and NHS siblings do.
- **`/v1/regions`** returns ONS-derived borough lists with the same gap.

`/v1/score`, `/v1/score/batch` and `/v1/changes` all carry it. Recorded
rather than quietly softened, because a licensing file that overstates
compliance is worse than one that admits a gap: the gap is fixable and the
false assurance is what stops anyone fixing it.

### Derived exports — the obligation travels

The bulk scoring CSV is a **derived work**: every row carries an ONS NSPL
centroid and a DEFRA-derived quiet score. OGL v3.0 attribution therefore
survives into it, and shipping the file bare would put the *customer* in
breach as well as us.

It is attributed in two places on purpose. The companion file holds the full
notices, but a customer will inevitably email the CSV on its own — so the
per-row `sources` column is the copy that cannot be separated from the data.

Both are generated from the API's own `build_sources()`, so the export and the
live responses cannot drift apart; and the companion file is written **after**
the run, because `build_sources()` only credits ONS once the local NSPL tier
has genuinely served a lookup. A file that claimed ONS provenance for a run
that had actually fallen back to postcodes.io would be a false claim in a
customer-facing document.

Pinned by `tests/test_score_bulk.py::TestAttribution` rather than left to a
code comment.

**Gap found and closed 2026-07-27.** The export shipped initially with **no
attribution at all** — despite `scripts/load_nspl.py`'s own docstring warning
that "the attribution obligation SURVIVES INTO ANY DERIVED EXPORT. The
Enterprise 'score your whole city' CSV is such an export." The warning was
written before the exporter existed and was not consulted when it was built.

---

## Obligations we're meeting

- ✅ OGL v3.0: attribution included on every response that uses OGL data
- ✅ TfL Open Data: full attribution string in `/transport` responses + methodology
- ✅ OpenStreetMap ODbL: attribution in `/nhs` responses + methodology
- ✅ MHCLG EPC: bearer token rotated per their guidance; attribution in responses
- ✅ Postcodes.io: attribution + we don't redistribute the raw dataset

## Obligations to keep in mind

- 📌 **OpenSky** — only consumer-site, low-risk, but worth a courtesy email to confirm "free public site with attribution + OAuth2 free tier" is OK with them
- 📌 **MHCLG EPC bearer token** — rotate periodically (the production token shouldn't appear in chat logs, terminal scrollback, or any unencrypted persistence per CLAUDE.md note)
- 📌 **NSPL — now a live serving source, not just an offline input (changed 2026-07-25).** The `london-flight-map-postcodes` table is OGL-derived, and `/v1/score` responses carry NSPL-derived `location.postcode`, `latitude`, `longitude` and `borough` directly. OGL v3.0 permits this commercially; the obligation is attribution, which the response `sources` array now carries. Two consequences worth holding:
  - **The planned Enterprise "score your whole city" CSV is a bulk export of NSPL-derived data.** That is allowed under OGL, but the attribution must travel *with the file* — a licence notice in the CSV header or an accompanying README, not merely in the API response the customer never sees. Decide the exact form before the first pilot deliverable ships.
  - We still must not redistribute the raw NSPL dataset itself, as distinct from scores derived from it.

---

## What's NOT in our stack (yet) and would need licensing review

If we add any of these later, **check terms first**:

- Flightradar24 / FlightAware (paid)
- Zoopla / Rightmove listings APIs (commercial-only, expensive)
- Gov.uk Crime API beyond ONS aggregates (mostly OK but check rate limits)
- ADS-B Exchange (would replace OpenSky; their commercial terms differ)
- Any PAID dataset (we currently use only free / open data)

**Under evaluation since 2026-10-15 for "how often planes pass" (ROADMAP "IN PROGRESS: how
often planes fly"). Measured privately; nothing derived from these is published:**

- **adsb.lol flight history** (`github.com/adsblol/globe_history_2026`), **ODbL 1.0**; its
  feeders' contributions are CC0. Read by `scripts/adsb_extract.py` and
  `scripts/adsb_movements.py`. **Share-alike, as for OpenStreetMap above**: the moment a
  count derived from it is published, that count is a Derivative Database and must be
  offered under ODbL, credited "aircraft positions via adsb.lol (ODbL)". Commercial use is
  allowed. **Bill accepted the share-alike on 2026-10-15**: the counts will be published
  under ODbL once they pass the per-airport floor (ROADMAP).
- **Bay Area runway use, `data/us-runway-use.json` (2026-10-16), DERIVED FROM adsb.lol, so ODbL.**
  Landings and take-offs per runway end at SFO, OAK and SJC over July-August 2026 (55 of 62
  days kept), and the lobe shares built from them in the score Lambda's US-QUIET-BAYAREA block.
  They WEIGHT the Bay Area's aircraft estimate, which the API scores from release 2 (built 2026-10-22;
  serving once Bill's changeset deploys), and every Bay Area response's `sources` carries the credit and
  the period. **PUBLISHED 2026-10-16 (`17d7ef1`, pushed to the public repo on Bill's "push")**,
  after it was held back for his decision: his 15 Oct acceptance covered counts that pass the
  per-airport floor, which a US airport cannot (no official monthly figure to test against), and
  these weight runways rather than claim how often planes pass. Offered under ODbL and credited
  "aircraft positions via adsb.lol (ODbL)" in the file; the credit must also appear wherever a Bay
  Area score built on it is shown, which the API's `sources` does (release 2).
- **US airport noise monitors, `data/us-noise-monitors.json` (2026-10-16)**, the yardstick for the
  US aircraft estimate: **SFO** via DataSF's "Aircraft Noise Climates" (dataset qxw2-ncq3),
  **PDDL 1.0** (public domain), read from the dataset's own metadata (both its conventional and ANEEM
  columns are kept; ANEEM is the yardstick, `scripts/build_sfo_noise_monitors.py`); **SJC** from its Quarterly
  Noise Report to Caltrans (a public Title 21 filing; no licence stated, used as published
  facts with the source named). Annual figures only; no raw files are redistributed.
- **New York airport noise monitors (2026-10-16)**, `data/us-noise-monitors.json` 'NYC': the Port Authority of NY &
  NJ's Monthly Noise Monitor Report (a public report; no licence stated). Monthly figures transcribed and monitor
  positions measured off its maps, used as published facts with the source named; no report images or tables
  are redistributed. **The positions were then snapped onto the named street with OpenStreetMap street geometry**
  (`scripts/snap_panynj_monitors.py`, one Overpass query; OSM is ODbL 1.0, "(c) OpenStreetMap contributors"). Found
  by the 2026-10-16 audit: they feed the fitted (scored) estimate, which is this file's re-open trigger. 29 points
  are treated as an insubstantial extract, credited here and in the data file's notes, and never published per
  response; whether a response-level credit is also wanted is Bill's call. **New York's runway use is in `data/us-runway-use.json` since 2026-10-16** (JFK, LGA, EWR,
  TEB; every third day of January-July 2026 since v5.7, July-August before) and New York's score reads it, so it takes the Bay Area's ODbL treatment: offered
  under ODbL, credited "aircraft positions via adsb.lol (ODbL)" in the file and in every New York response's
  `sources` (with the period, from the engine's own block).
- **US Census Bureau ACS 5-year, table B25077 (2020-2024), `data/us-bayarea-prices.json` (2026-10-16)**: median
  home value for the Bay Area's 50 cities, release 2's price input. Public domain (a US government work), from
  the keyless summary file (the API now wants a key). "$2,000,000+" is coded 2000001: a floor, flagged
  `top_coded` (16 of 50), never shown as a price.
- **FHFA House Price Index, counties (annual, all-transactions, "developmental"), `data/us-bayarea-trend.json`
  (2026-10-16)**: the 2025 annual change for the four Bay Area counties, release 2's growth input. Public domain
  under FHFA's website policy s10 ("information and materials produced by Federal agencies, including FHFA, are
  in the public domain"; the FHFA seal excluded); s11 forbids implying FHFA's endorsement. County-wide and a
  calendar year behind the UK's monthly HPI: never shown as a city's own or current trend.
- **BTS National Transit Map Stops, `data/us-bayarea-transit.json` (2026-10-16)**: 334 rail, metro and light-rail
  stations in the four counties (GTFS route types 0-2), release 2's transport input. **CC-BY 3.0 United States**:
  credit "US Department of Transportation, Bureau of Transportation Statistics" wherever it is shown; the Bay
  Area agencies list their own feeds as public domain. Cable cars are left out (a decision, recorded in the
  file); Capitol Corridor (Amtrak) is absent from the layer (a known gap, recorded, not filled).
- **California DOJ OpenJustice "Crimes and Clearances" (1985-2025) and the US Census Bureau Vintage 2025 city
  population estimates (`sub-est2025_6.csv`), `data/us-bayarea-crime.json` (2026-10-18)**: violent + property
  crimes per 1,000 residents for 45 of the 50 cities, release 2's crime input. Both public domain
  (oag.ca.gov/conditions: "Considered in the public domain"; the estimates a US government work). The five
  San Mateo sheriff-contract cities have no rate of their own (`null`, with the reason); never apportion the
  sheriff's county total among them. Not comparable with the UK's ONS Table C4 rate.
- **US Census Bureau 2020 redistricting file (PL 94-171) geographic header, and the 2020 Block Assignment File
  (2026-10-18)**: block population and internal points, the resident frame for the Bay Area's road and flood
  shares (`scripts/bayarea_blocks.py`). Public domain. Gitignored inputs; only derived city shares are published.
- **BTS National Transportation Noise Map 2022, road (`NTAD_Noise_2022_CONUS_road` tiles),
  `data/us-bayarea-road.json` (2026-10-18)**: the share of each city's residents in the 45 dB LAeq band or
  louder, release 2's road-noise input. A US government work; credit "USDOT Bureau of Transportation
  Statistics". BTS: simplified modelling that "should not be used to evaluate noise levels in individual
  locations", so only a city share is published, never a reading at a point.
- **US Census Bureau ACS 5-year, table B01003 (2020-2024), and the 2024 ZCTA gazetteer, `data/us-nyc-zcta.json`
  (2026-10-16)**: population and internal point of the 211 ZIP Code Tabulation Areas inside New York's five
  boroughs, which weight New York's borough aircraft bands (`scripts/build_nyc_impact.py`). Public domain (US
  government works), keyless summary file; credited in New York's `sources`.
- **CAA airport statistics, Table 03.1 Aircraft Movements** (2025, `data/caa/`, gitignored):
  used to CHECK the tracked counts. The CAA's terms: "No statistical data provided by CAA
  maybe sold on to a third party. CAA insists that they are referenced in any publication
  that makes reference to CAA Statistics." So free, credited display only, until the CAA
  answers (OUTREACH_LOG 2026-10-06).
- **EASA ANP database** (aircraft noise-power-distance data, needed for N65): access by
  request under Regulation (EU) 598/2014 Art 7. Terms unread; request drafted
  (OUTREACH_LOG 2026-10-15).
- **Rail noise, parked as breadth**: DEFRA Round 4 rail Lden (England; the road map's
  family, so check its licence statement when built), the Welsh Government's 2022 rail
  mapping on DataMapWales (licence unread), BTS's 2022/23 rail layer for the US (terms
  unread; BTS says it is not for individual locations).

---

## Action items from this audit

| Priority | Action |
|---|---|
| 🟢 None blocking | All current B2B API sources are commercial-use-OK with attribution we're already shipping |
| 🟡 Hygiene | Email OpenSky to confirm consumer-site usage is OK with attribution + free OAuth2 tier |
| 🟡 Hygiene | Rotate MHCLG EPC bearer token (already noted in CLAUDE.md) |
| 🟢 None | DEFRA + ONS + Land Registry + TfL all OGL v3.0; nothing to do |

This document gets refreshed whenever we add or change a data source.
Last reviewed: 2026-10-15 (candidate sources for flight frequency and rail noise listed under "What's NOT in our stack (yet)": adsb.lol is ODbL share-alike, CAA statistics may not be sold on, EASA's ANP data is by request; nothing new is published). — Previous review 2026-09-07 (**five datasets in live use added** - US DOT NTAD, FEMA NFHL, US EPA and the curated New York scored inputs; the **TfL row corrected**, which had credited TfL for the liveability `transport` sub-score that NaPTAN has supplied since v3.6; HMLR's required notice recorded as its own rather than "same OGL boilerplate"; and the absolute attribution claim corrected against three endpoints that falsify it. Found by the 2026-09-07 audit.) — Previous review 2026-07-25 (**ONS NSPL promoted from an offline input to a primary live serving source**, postcodes.io demoted to fallback; response attribution is now conditional on the local tier having actually served, so ONS is never credited while the table is empty. Flagged: the Enterprise city-scale CSV will be a bulk export of NSPL-derived data — allowed under OGL, but the attribution must travel with the file, and that form needs deciding before the first pilot deliverable). — Previous review 2026-05-07 (OpenSky removal end-to-end; AI-powered consumer features removed earlier the same day; loader still running against the full NSPL postcode list).
