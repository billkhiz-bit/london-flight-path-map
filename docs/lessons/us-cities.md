# The Bay Area and New York

> Moved verbatim from `CLAUDE.md` on 2026-10-17 to keep the session-start file small.
> The /bay-area/ page, release 1 and 2, the US noise yardstick, the v5.6 New York fit.
> Statements are dated as written; re-measure a number before relying on it, and when a
> rule here changes, update the one-line rule in `CLAUDE.md` too.

<!-- CLAUDE.md lines 991-1056 (2026-10-16) -->
## The Bay Area flight-path page, `/bay-area/` (2026-10-02)

**A standalone static page, NOT a city on the map** (Bill's ruling: page first,
scored city later; plan in EXPANSION.md). **Ruled 2026-10-03: the scored city follows in TWO RELEASES** - on the main map first (the 50 cities, routes, noise picture, city and ZIP search, a Quiet Skies ESTIMATE, and NO overall score, since one estimated input is not a composite), scored second (prices by the Census route, liveability inputs, the neighbourhood tier, area pages). EXPANSION.md has what each needs; the by-name New York branches come first. The 50 cities of the four counties
round SFO, OAK and SJC, the FAA's coded routes, and BTS's 2022 noise map.
`scripts/build_bay_area_page.py --fetch | --write | --check`; do not hand-edit
`bay-area/index.html`. **DEPLOYED 2026-10-02**, linked from both footers of
`index.html` ("Bay Area") and from `/area/`. It publishes **no score and no decibel figure** (the
2022 tile service has no legend, so the band values are unverified), carries
the FAA's warranty disclaimer its licence requires, and says "where the routes
are, not how many aircraft use them".

- **Ordered by share of the city on the noise map, not by route geometry**: SFO's
  runway 10 approaches are published and rarely flown.
- **BTS's map is land only.** An approach over the bay is unpainted, so the
  cross-check asks for every threshold and each airport's best approach.
- **The Census outlines are 1:500,000**: SJC's 12R threshold is 126 m inside
  Santa Clara. Nothing on the page depends on a boundary to that precision.
- **`data/us-bayarea-places.json` is deliberately not `*-boroughs.json`**: that
  suffix is globbed to enumerate cities, and two fetchers would go and ask
  DEFRA and the Environment Agency for California.
- `tests/test_bay_area_page.py` breaks the REAL inputs one way at a time (a
  mis-paired shapefile record, a picture one tile out, a missing city).
- **Release 2's noise gate is BUILT (2026-10-16, engine only, inert):** `CITY_GEOMETRY['bayarea']` from the
  generated `US-QUIET-BAYAREA` block, fitted to SFO's 29 and SJC's 13 monitors with runway use from adsb.lol
  tracks (`data/us-runway-use.json`, ODbL, published with `17d7ef1` on Bill's word; LICENSING); blocking
  `measure_us_quiet_yardstick.py --check`. Per-city fields only (`runway_lobes`, `airport_sizes`,
  `corridor_weight`, `major_airports`): never put US sizes in `AIRPORT_NOISE_SCALE`, which mirrors index.html.
  Normal-year monitors prefer a route weight of 1.0 against the UK's provisional 0.5: a UK lead, not a change.
  **The yardstick is ANEEM where published (SFO; Bill 2026-10-16)**, built by `scripts/build_sfo_noise_monitors.py`,
  and the fit needs every airport 0.2 louder in sample (`MARGIN`) so it holds out: weight 1.25, SFO 0.96 held out.
- **New York's published Quiet Skies reads QUIETER than measured near JFK (15 of 17 monitors, +2.38; 2026-10-16,
  `scripts/measure_nyc_quiet_yardstick.py`, Port Authority monitors in `data/us-noise-monitors.json`).**
  **FIXED AS v5.6 (Bill's "yes", 2026-10-16; DEPLOYED 2026-10-16 night via a reviewed SAM changeset - only
  ScoreFunction's code changed - then data/web/home/area/demo/meta/prototype/open-data, verified from the origin:
  drift 35 pages / 39 data / 103 area, 102 of 102 area pages == live API, score sanity 29, site == /v1/score):** `measure_us_quiet_yardstick.py` runs per
  REGION (`--region all|bayarea|nyc`) and writes New York's `US-QUIET-NYC` block into BOTH holders (the Lambda's
  `AIRPORTS_NYC_FITTED`/`FLIGHT_PATHS_NYC_FITTED`/`NYC_QUIET`, and index.html's `US_QUIET_NYC`, which sits in the
  New York data section because `NYC_AIRPORTS`/`NYC_FLIGHT_PATHS` are now VIEWS of it: the map draws what the
  score reads). Both site ramps read `quietGeometry(city)`, which mirrors calc_postcode_quiet's optional fields
  (lobes via `runwayLobeKm`, sizes, `corridorWeight`, `majors`); `tests/us-quiet-site-parity.mjs` (BLOCKING) runs
  both ramps against the Lambda at 713 points and 127 neighbourhoods, proven red three ways. The hand-drawn
  `AIRPORTS_NYC`/`FLIGHT_PATHS_NYC` are DELETED from the Lambda. The five borough bands are DERIVED by
  `scripts/build_nyc_impact.py` (BLOCKING `--check`, offline from the checked-in `data/us-nyc-zcta.json`):
  population-weighted mean over 2020 ZCTAs (ACS B01003, keyless summary file), rounded to the LOUDER band (the
  quietest band not above the estimate; Bill, after the 16 Oct audit: nearest put Brooklyn 0.89 quieter).
  `sources` credits the FAA ("as is") and adsb.lol (ODbL, period read from the block's `runway_use_period`) for
  any city carrying `runway_lobes`. **Known limitation, stated in every NY response:** runway use is July-August
  while the monitors are January-July, so JFK's north-west (Howard Beach, 150th/165th Ave) reads 2-3 points
  quieter than its monitors; the fix is a runway count over the monitors' months.
- **Release 1 of the scored city is under way** (branch `bay-area-on-map`,
  fast-forwarded into master as it goes). Done by 2026-10-04: five of the
  page's eleven by-name New York tests ask the registry
  (`paintsNoiseFromTiles()`, and `isUkCity()`, which already existed), and
  **`tests/test_us_city_branches.py` DECLARES the twelve that remain**: a new
  `=== 'nyc'` fails the build, so ask the registry or declare it there with
  its reason. **`data/us-bayarea-zips.json`** (165 ZIP areas from three Census
  files; `scripts/build_bayarea_zips.py --check` is blocking) names the city
  holding the most of each ZIP's land WITH its share. Do not drop the share,
  and do not bring back "name a city only at half or more": that left
  Cupertino's and Livermore's ZIPs in no city, because both reach into empty
  hills. ZIP search is live on `/preview/` only; the live map and the Lambda
  still use New York's hand-built tables. Next is the Bay Area's entry in
  the live map's registry, where a city with no overall score is a new state
  for the score panel and the ranking.


<!-- added 2026-10-17 -->
**v5.7 (2026-10-17): New York's runway use over the monitors' months, and a lobe has a length (Bill's ruling).**
The 16 Oct detached download of every third day of January-July died at 7 May when the laptop shut down, yet its
driver printed `DONE` (it ignored exit codes); restarted with a driver that prints DONE only when all 71 days exist.
Counted over January-July, JFK's north-west monitors went from +3.0 / +2.0 / +3.0 (held out, + = quieter than
measured) to 0.0 / 0.0 / +1.0. **But the same count added a JFK 31L departure lobe (bearing 300.9) pointing straight
at Lower Manhattan, 19 km out**, and `runway_lobe_km` treated a lobe as an endless half-line: 10002-10038 read 3-4
points louder and Manhattan's band went moderate -> moderate-high, with every fit statistic IMPROVING, because no
monitor is in Manhattan. US DOT's 2022 map (our own `data/aircraft-noise-nyc-laeq.png`, sampled at ZIP centroids)
paints nothing there, below 45 dB, while the Howard Beach monitors sit in its 55-60 bands; the FAA's coded climb-out
turns away. Fix: `RUNWAY_LOBE_KM = 15` in both holders; past the end the distance along the lobe counts
`AIRPORT_SHAPE_K` times over, so the field is continuous (no ring on the map). Lengths 8/10/12/15/20 km and none
were refitted for both regions: 15 km alone held both regions' monitors with the Bay Area's fit unchanged (12 km
worsened SFO 0.96 -> 1.28). JFK's size 1.8 -> 2.05, LOO MAE 1.28 -> 1.04. Queens 1.44 rounds louder: high -> severe,
borough score 5.0 -> 4.4. The embeddable Python 3.13 has no tz database, so `adsb_movements.py` (which reads only
our own extracts) runs under the system Python; the extract step stays on 3.13. Lesson: **a fit only tests points
near its monitors; check every point far from all of them against an independent source before shipping.**


<!-- added 2026-10-18 -->
**Release 2's readers, 2026-10-18: crime, road noise and flood, over one resident frame.** The UK's flood and
road inputs are shares of a borough's live POSTCODES, so the US ones are shares of RESIDENTS: 2020 Census blocks
(`scripts/bayarea_blocks.py`), each block's internal point weighted by its population, in the city the Census
places it in. The source is the geographic header of California's PL 94-171 file (population, internal point
and place code in one row; 80 MB, where the state TIGER block file with population is 382 MB and the
per-county TIGER2020PL files carry NO population column). It has no header line, so fields are read by
position, and `--check` holds the positions against the separate Block Assignment File: shifting PLACE by one
field reds 45,686 blocks (proven). The 2020 base differs from the counted blocks by tens of people (count
question resolution; Colma 1,507 counted, base 1,469), so the tolerance is 1% or 50, whichever is larger.
- **Crime** (`build_bayarea_crime.py`): violent + property over every California agency gives 22.27 per 1,000,
  decision 4's 22.3 (arson in: 22.45), so the definition is derived from the anchor and the anchor is
  recomputed, never typed. 45 of 50 cities matched by name; the five sheriff-contract cities are a SET held
  both ways (a city gaining a DOJ row stops the build). The places file holds 78 places (28 CDPs): Broadmoor, a
  CDP with its own police district, matched too, so the reader selects the 50 by kind first. The Census
  estimates file is Latin-1. The "few residents" note: under 20,000 residents AND over 3x the state rate
  (Colma and Emeryville only), Claude's recommendation, accepted by Bill 2026-10-18 ("do what is recommended").
- **Road** (`build_bayarea_road.py`): BTS's 2022 road service, unlike its aviation one, publishes a LEGEND
  (45-49.9 ... > 90 dB LAeq) in exactly NOISE_SCALE_BTS's colours, which is strong (not proof) evidence the
  aviation bands mean the same. **The cache stops at level 12**: 13 and 14 answer 404 even over US-101, so a
  404 is "not cached", never "quiet" (read as quiet, every city would have scored 0%). Level 12 is about 30 m
  at this latitude, BTS's own grid. WHO's 53 dB Lden is about 46.6 LAeq, inside the 45 band, so the share
  counts from 45 (the louder side). **Not on the UK scale**: Bay Area 0.9-24.8% (median 7.2%) against UK
  boroughs 27.9-95.6% (median 55.0%), because BTS models highway traffic; a score from it needs a US scale (Bill, 2026-10-18). The UK ramp is FIXED
  (0% over WHO = 10, 100% = 0; `road_to_score` refuses min-max), so the US one must be anchored on a published
  reference as crime is: proposed, California's statewide share of residents in the same BTS band, from the
  same block frame. Fixed at the scoring step, not before.
- **Flood** (`build_bayarea_flood.py`, waiting on FEMA's file): FEMA maps all studied land, zone X included,
  so a resident in zone D or in no polygon is UNKNOWN, counted and left out of the share, and over 5% of a city
  fails the check; overlapping studies take the riskier reading.
- **The road anchor, measured (2026-10-18):** California's statewide share in the 45 dB band or louder is 6.88%
  (39.5m residents over 4,499 zoom-12 tiles; `--fetch-state`). A 404 there is accepted as EMPTY only when the first
  parent tile that answers paints nothing over that quarter (`_area_painted`); none were needed. It sits on the Bay
  Area's median city (7.2%), so a scale anchored there splits the region rather than flattering it.
- **FEMA's refusals follow the FIELDS, not the geometry (2026-10-18, four runs).** Run 1 refused the whole box; run
  3 one polygon "even alone"; simplifying to 20 m did not help (run 2). Run 3's leave-out-and-record hit four in a
  row in Santa Cruz County (the one search box reached into it: now only tiles touching a city's own box are
  searched, and a refusal whose extent touches no city is recorded apart). Run 4 then hit one by SFO, and for it
  FEMA answered an EXTENT query (no fields) but refused an attributes-only query: the requested fields break it.
  The fetcher now retries a refused feature with `FLD_ZONE,SFHA_TF` only, and probes each field alone for any still
  refused, so the manifest names the field. Lesson: when a service refuses a record, vary WHAT is asked for before
  varying HOW MUCH.
- **The pool key (2026-10-18, decision 2, build-order step 2):** affordability and growth anchors are taken over
  `pool_of(city)` (Lambda) / `poolOf` (index.html): a city's `pool`, else its currency. Introduced as a pure
  refactor, proven by a byte-for-byte snapshot of all 816 scores (14 cities x 8 personas) before and after; the
  snapshot was itself proven red (London alone in a pool moved 728 of 816). It caught a shadowing bug first:
  the trend function's local result list was also named `pool`, so `pool = []` replaced the parameter and every
  city was skipped (any calc_score then raised ValueError, so the existing tests would have caught it too; an
  earlier note here said otherwise and was wrong, corrected after a code review). Lesson: renaming a parameter
  to a word the body already uses is a shadowing trap. The review also found: the Lambda must read `None` as
  the currency (`or`, as the site's `||`), because the site's key-parity gate will put `pool: null` on every
  city; and the site pools the API-only cities as sterling, now refused by build_hpi_prices.py for any other.
- **The US scales (Bill, 2026-10-18): LINEAR on the California anchor.** `us_anchored_to_score(value, anchor)`:
  10 at zero, 5.0 at the anchor, 0 at double; None in, None out; a missing or non-positive anchor raises. The log
  form (5 at the anchor, 10 at half) was rejected: it put 9 of 45 cities at 10 on crime and 7 on road, where the
  UK's linear ramps give 10 only to none at all. The tests read the anchors from the generated files and assert
  PROPERTIES (0 exactly at double or more, 10 only at zero, above 5 only below the anchor, monotonic), not named
  cities' scores, which change with every roll; they are red on the log form.
- **`uk_shape(city)` (2026-10-18)** replaced four `city != 'nyc'` tests ("is this the UK's liveability shape"):
  a `country` question, unknown cities read as UK exactly as before, 816 scores byte-identical. The by-name gate
  scans DOCSTRINGS as well as code (it skips only `#` lines), so describe an old by-name test without quoting it.
- **FEMA after the fields fix (2026-10-18):** run 5 was reset at the first request and run 6 found 7,094 ids in a
  minute, then hung on the feature fetch until the 30-minute workflow limit: throttling or an outage on FEMA's side
  for GitHub's runner, after five runs and thousands of requests that day. One retry per day at most. The bulk
  route's download address could not be read (FEMA's guide resets here and from WebFetch).
- **The bulk route, probed (2026-10-19, `fema-bulk-probe.yml`, run `39320864104`):** from GitHub,
  `msc.fema.gov/portal/home` and `/portal/advanceSearch` answer 200; both NFHL MapServer roots on `hazards.fema.gov`
  and the direct-download guide (`msc.fema.gov/msccontent/...pdf`) fail with curl exit 35 (TLS reset), and the guide
  resets in Bill's own browser too, so it is not only cloud addresses. The one open door is the portal: the probe's
  second step saves the portal page and the scripts it loads from msc.fema.gov, and searches them for the address
  its Download buttons use (FEMA's own code, not a guess; tested on a fixture with a stubbed network first).
- **The county downloads WORK (2026-10-20).** Run `39327658467` got the guide through once (FEMA blocks on and
  off): `msc.fema.gov/portal/downloadProduct?productID=` + `NFHL_<5-digit county FIPS>C` is a whole county's NFHL.
  `scripts/fetch_fema_nfhl_counties.py` (workflow `fema-nfhl-county-fetch.yml`) takes the counties from the place
  file's county names and the trend file's FIPS, never typed, and `--check` proves every resident block of the 50
  cities lies in them (4,950,918 residents in Alameda, San Francisco, San Mateo and Santa Clara; red with any one
  removed). GDAL (`gdal-bin` on the runner) reads S_FLD_HAZ_AR whether the zip holds a shapefile or a geodatabase,
  and the output is the query route's file, so `build_bayarea_flood.py` reads it unchanged (a test runs that
  reader on it). Run `39416950759`: Alameda came whole in 40 s (22.6 MB, 140 members, 2,451 polygons, a
  SHAPEFILE); San Francisco's `NFHL_06075C` answered 200 with the portal's page template (`var userName`), though
  the city-county's FIRM has been effective since 2021 (sf.gov). **A download's 200 is not the product: test its
  magic bytes.** The fetcher now asks a page again once, keeps it under `diagnostics/` as `.txt`, tries every
  county, and writes `failed.json` and NOTHING the reader takes unless all four came.
- **San Francisco has no county-wide product (2026-10-20, run `39430132007`).** The same afternoon FEMA let the
  runner through: Alameda, San Mateo and Santa Clara came whole (2,451 / 1,379 / 2,330 polygons, all SHAPEFILES),
  and `NFHL_06075C` answered "Sorry, the product you were looking for could not be found" twice, a minute apart:
  an answer, not a throttle (the kept reply said so; a page's TITLE did not). FEMA's guide (p.2) gives the other
  form, `NFHL_<community CID>`; rather than guess San Francisco's CID, the fetcher asks the portal the way its own
  page does (`getAjaxData()`: `advanceSearch?getCounty=06`, then `?getCommunity=<county value>&state=06`, each
  `[{value, label}]`), matches the county by FIPS else by name (never two). Run `39436786877`: the portal lists
  San Francisco as ONE jurisdiction, "SAN FRANCISCO COUNTY ALL JURISDICTIONS", value `06075C`, whose plain id is
  the one FEMA cannot find; so each such community is searched as the page searches (a POST of its form with
  `method=search`), and every `EFFECTIVE.NFHL_COUNTY_DATA[].product_NAME` it lists is downloaded at the address
  the page builds (`productTypeID=NFHL&productSubTypeID=NFHL_STATE_DATA&productID=<name>`, the STATE subtype for
  county data too, kept as found). **When a service answers "not found", read its words, and look for the address
  its own page uses before guessing one.**
