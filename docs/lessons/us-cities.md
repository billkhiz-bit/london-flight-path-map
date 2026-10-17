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

