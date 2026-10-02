# Expansion: which cities and countries are reachable, and what each costs

**Written 2026-08-11.** Every figure here was measured on the day, not recalled.
Where something has not been verified it says so, because the expensive mistake
in this project has repeatedly been treating "the dataset exists" as "we have
the data" — DEFRA publishes an aircraft surface for all 16 English airports and
it still only reaches 0.5% of West Yorkshire's addresses.

## The one fact that shapes everything

**Eleven of our thirteen cities cost almost nothing to add because every source
is national.** The nation, not the city, is the unit of work.

| Source | What it feeds | Coverage | Verified |
|---|---|---|---|
| ONS NSPL | postcode → borough, coordinates | **UK** | in use |
| HM Land Registry HPI | avgPrice, trend | **UK** | in use |
| HM Land Registry Price Paid | neighbourhoods, sold prices | **England + Wales** | 2026-08-11 |
| ONS Table C4 | crimeRate | **England + Wales** | in use |
| DEFRA background pollution maps | airQuality, NO₂, PM2.5 | **UK** | 2026-08-11 |
| DfE Progress 8 | schools | **England only** | in use |
| DEFRA noise mapping Round 4 (road) | roadNoise | **England only** | 2026-08-11 |
| DEFRA noise mapping Round 4 (aircraft) | aircraft Lden | **England, 16 airports** | 2026-08-11 |
| EA Risk of Flooding from Rivers and Sea | flood | **England only** | 2026-08-11 |
| NaPTAN | transport | **Great Britain** | in use since v3.6 |
| NHS Organisation Data Service | healthcare | **UK** | in use since v3.7 |

So an **English** city-region needs no new data integration at all. A Welsh one
loses schools, road noise and flood. Scotland and Northern Ireland change the
publisher for almost everything.

## Where we are

94 local authorities across 13 cities, 11 of them on the consumer site as well as the API. Measured against HM Land Registry's 2025
transactions, that is **34.6% of all residential sales in England and Wales**,
from 318 districts of which we cover 81.

## Next UK city-regions, ranked by market size

Ranked on 2025 transaction volume, grouped into the travel-to-work city-regions
the product already uses. **All are in England, so all are "free" in the sense
above** — the work is registry wiring, boundaries and a neighbourhood build, not
new sources.

| # | City-region | Likely LADs | 2025 sales | Notes |
|---|---|---|---|---|
| - | **Greater Norwich** | Norwich, Broadland, South Norfolk | ~6.5k | **API-ONLY PREVIEW, DEPLOYED 2026-09-27.** Not ranked on volume - built on demand, after a Norwich user's report. 3 of 4 liveability inputs everywhere (no district P8); airport not in DEFRA Round 4 (geometry, floored). Promoting it to the site needs CITY_DATA, chip, stations, neighbourhoods and a projection fit |
| 1 | **Nottingham** | already in `LAD_TO_BOROUGH` | ~20k | **API-only, and now promotable.** Healthcare (v3.7) took Broxtowe, Gedling and Rushcliffe to two measured inputs, so they clear the floor - it stays back on judgement (`live` 2.6 on two inputs), not impossibility |
| ~~2~~ | ~~**Leicester**~~ | **DONE 2026-08-11, ON THE SITE.** City plus all 7 Leicestershire districts | ~15k | Widened from 4 to 8: a 4-authority cohort spans only 230k-281k |
| 3 | **Bournemouth + Poole** | BCP, Dorset | ~14k | **NOT VIABLE as a 2-authority cohort.** 315,473 vs 326,381 is 3.5%, which min-max over two items renders as a 10-point affordability spread. Needs a wider grouping (a Solent region of 5) or leave out |
| ~~4~~ | ~~**Teesside**~~ | **DONE 2026-08-11, ON THE SITE.** All 5 Tees Valley unitaries | ~13k | Spans Cleveland and Durham forces, so needs a crime include-list |
| 5 | **Stoke + Staffordshire** | Stoke-on-Trent, Newcastle-under-Lyme, Staffs Moorlands | ~9k | |
| 6 | **Hull + East Riding** | Hull, East Riding | ~11k | Large but two-unit |
| 7 | **Derby** | Derby, Amber Valley, Erewash, South Derbyshire | ~11k | Shares East Midlands Airport |
| 8 | **Southampton + Portsmouth** | Southampton, Portsmouth, Eastleigh, Fareham, Havant | ~12k | Southampton Airport has a DEFRA surface |
| 9 | **Brighton + Hove** | Brighton and Hove, Adur, Lewes | ~7k | Gatwick surface partly covers it |
| 10 | **Plymouth** | Plymouth, South Hams, West Devon | ~7k | No airport; the South Yorkshire path already handles that |
| 11 | **Milton Keynes** | Milton Keynes, Central Bedfordshire | ~10k | Luton surface partly covers it |
| 12 | **Coventry + Warwickshire** | Warwick, Rugby, Nuneaton | ~8k | Coventry itself is already in West Midlands |

**Not city-regions, but the largest uncovered units by volume**, and worth
knowing they exist: North Yorkshire (11,599 sales), County Durham (10,342),
Somerset (9,979), Cornwall (9,830), Buckinghamshire (8,817), Wiltshire (8,501),
Cheshire East (8,282). These are large rural unitaries rather than cities. They
would work technically — every source covers them — but "borough" means
something different there, and the product's framing is urban.

## Countries

### Wales — partial, and the gaps are structural

Already present as Cardiff (API-only, 4 LADs). **Blocked from the site by
missing schools data**, and two more gaps found on 2026-08-11:

| Component | Status |
|---|---|
| Prices, trend, neighbourhoods | **Works** — Land Registry covers Wales |
| Crime | **Works** — ONS Table C4 covers Wales |
| Air quality | **Works** — DEFRA grid is UK-wide |
| Schools | **No Progress 8.** Wales uses its own measures; needs a separate source and a separate methodology statement |
| Road noise | **Natural Resources Wales**, not DEFRA. Excluded by name in `NO_ROAD_COVERAGE` |
| Flood | **NRW**, not the EA. Excluded by name in `NO_FLOOD_COVERAGE` |

Adding Wales properly means integrating NRW twice and answering the schools
question. Cardiff, Swansea and Newport together are a modest market; the work is
not proportional to the return yet.

### Scotland — a different publisher for almost everything

Nothing is wired. Every component changes hands:

| Component | Likely source | Verified |
|---|---|---|
| Prices | **Registers of Scotland** — Land Registry does NOT cover Scotland | no |
| Crime | Police Scotland / Scottish Government recorded crime | no |
| Schools | Scottish Government; no Progress 8 equivalent | no |
| Noise | Scottish noise mapping (Transport Scotland) | no |
| Flood | **SEPA** flood maps | no |
| Air quality | DEFRA grid **does** cover Scotland | yes |
| Postcodes | NSPL covers Scotland | yes |

Edinburgh and Glasgow are genuinely attractive markets, but this is the largest
single integration on the list — five new publishers. Treat it as a project, not
a city addition.

### Northern Ireland — smallest market, most bespoke

Land & Property Services rather than Land Registry; NISRA for statistics; a
different postcode and LGD geography. Lowest priority on both effort and return.

### Ireland, and beyond the UK

New York works because its inputs are **curated**, not derived — it is the
exception this repo keeps having to special-case (`NO_ROAD_COVERAGE`,
`NO_FLOOD_COVERAGE`, FEMA flood bands, DOT road noise). Adding a second
non-UK city repeats that cost unless the country has a comparable open-data
stack.

Ranked by how close each is to having one:

1. **Ireland** — Property Price Register (prices), EPA (air, noise, flood).
   Nearest thing to a drop-in outside the UK.
2. **Netherlands** — exceptional open data (Kadaster, RIVM, PDOK). Small market,
   high data quality.
3. **Australia** — state-by-state rather than national; each state is its own
   integration.
4. **United States beyond NYC** — HUD/Census/EPA/FEMA are national, but property
   prices are county-level and fragmented. The existing NYC entry is curated and
   does not generalise. **Re-opened 2026-10-02 on Bill's instruction: San
   Francisco is next, built DERIVED not curated, for a US audience. See "San
   Francisco" below - the survey changed this ranking's premise.**

### San Francisco (decided 2026-10-02; survey done, nothing built)

Bill's ruling: build it properly, not as a second curated city. Goal: a US
audience and more visits. Every source below was CALLED on 2026-10-02, not
recalled; the result is what answered.

| Need | Source | What answered | Reach |
|---|---|---|---|
| Runways, glide angles, departure and arrival routes | **FAA CIFP** (`aeronav.faa.gov/Upload_313-d/cifp/CIFP_261001.zip`, 9.1 MB, ARINC 424, 28-day cycle; the FAA page needs a browser User-Agent, as the UK AIP host does) | KSFO 8 runway records, 3 ILS, **11 SIDs**; KOAK 8 / 3 / **11**; KSJC 4 / 2 / **7**. Every SID is CODED, where six UK airports publish charts only | **Every US airport** |
| Aircraft noise picture | **BTS National Transportation Noise Map 2022**, tiles at `tiles.arcgis.com/tiles/xOi1kZaI0eWDREZv/arcgis/rest/services/NTAD_Noise_2022_CONUS_aviation/MapServer` (`TilesOnly`, EPSG:3857, levels 0-23) | A tile over SFO returns the SAME seven colours as `NOISE_SCALE_BTS` | Lower 48 states |
| Crime | **DataSF** police incidents (`data.sf.gov/resource/wg3w-h783`), carries `analysis_neighborhood` | Current to 2026-09-30 | San Francisco only |
| Area boundaries | **DataSF Analysis Neighborhoods** (`data.sf.gov/resource/j2bu-swwd`) | 41 neighbourhoods, GeoJSON | San Francisco only |
| Prices | **Zillow ZHVI by neighbourhood** (103 MB CSV) | 107 San Francisco neighbourhoods, all with a value for 2026-08-31, from USD 477k (Tenderloin) to USD 4.96M (Presidio Heights) | US. **Zillow's 107 are NOT DataSF's 41**, and **its reuse terms have not been read** - a gate before any price is published, and before any is sold |
| Price trend | **FHFA HPI by ZIP** (`fhfa.gov/hpi/download/annual/hpi_at_zip5.xlsx`) | Downloads | US, public domain |
| Area boundaries, national | Census cartographic files (`www2.census.gov/geo/tiger/GENZ2023/`) | Downloads | US, public domain |

**BTS's own limit on its noise map, which shapes how a US city may use it:**
the 2022 edition is a 24-hour average (LAeq), published "to facilitate the
tracking of trends" and "should not be used to evaluate noise levels in
individual locations". So it is the PICTURE on a US map, as it is for New York,
and never a per-address measurement the way DEFRA's raster is in England. A US
quiet score comes from the flight-path geometry, labelled as an estimate.

**Three things the survey found that are not about San Francisco:**

1. **NEW YORK'S AIRCRAFT-NOISE LAYER IS DEAD ON THE LIVE SITE** (FIXED in
   the source the same day, stage 0 below; live once deployed).
   `geo.dot.gov` (both noise entries in `US_MAP_SERVICES`) refuses connections
   from two networks; the live page times out twice and the legend reads "BTS
   AIRCRAFT NOISE (dB DNL) (NO DATA)". The honesty mechanism worked; the layer
   did not. The 2022 edition above replaces it. **It is a URL change, not a
   code change** (corrected the same day: `renderTileGrid` already requests
   `/tile/{z}/{y}/{x}`; the registry's `type: 'arcgis-export'` label is what
   misled). It needs `tiles.arcgis.com` in the CSP `img-src`, the live half of
   `check_noise_legend.py` repointed, and LICENSING, SUBPROCESSORS and
   privacy.html updated. The `road`, `flood` and `airQuality` entries in
   `US_MAP_SERVICES` are referenced by NOTHING, so three documents describe
   browser requests the page never makes.
2. **`data.sfgov.org` now redirects to `data.sf.gov`** through an HTML page a
   script does not follow. Use the new host.
3. **The Census API now requires a key** (free; Bill's to request). FEMA's flood
   service reset the connection from here; untested from the US.

**Why this changes the ranking above:** the US was last because prices are
fragmented. That is still true. But the product's niche is now flight paths
(Geovation, 2026-10-02), and for flight paths the US is the BEST-served country
surveyed: one federal file codes every route at every airport.

**Stages, in order.** (0) Repoint the dead New York noise layer to the 2022
tiles. (1) A US flight-path builder from the CIFP, the sibling of
`build_flight_paths.py`, for SFO, OAK and SJC - and New York's three airports,
whose corridors are still hand-drawn. (2) San Francisco on the map: boundaries,
routes, noise tiles, quiet scores. (3) Crime, transit and the other liveability
inputs. (4) Prices, once Zillow's terms are read. (5) Area pages and a launch
post.

**DECIDED 2026-10-02 (Bill): an "area" is a BAY AREA CITY**, accepting the
bigger build - San Francisco as one area beside South San Francisco, Millbrae,
Oakland, Alameda, San Jose and the rest, because that is where the aircraft
noise falls. Consequences: DataSF's crime and neighbourhood files stop at the
city line, so crime needs a source that covers every city (the FBI's agency
figures are the candidate, NOT yet called); boundaries come from the Census
place file; and San Francisco's 41 neighbourhoods become the NEIGHBOURHOOD
ranking beneath the city, as London's are beneath its boroughs. Which cities,
and the key (`bayarea`, not `sanfrancisco`), are stage 2's first decisions.

**What a second US city must touch** (code survey 2026-10-02; line numbers
omitted because they move - search for the names). New York is wired in BY
NAME in about 25 places, and a second US city would fall into the UK branch at
each of them, silently. Generalise these FIRST, each to a test on country or
on the registry, before any Bay Area data exists:

- **Lambda:** `english=(city != 'nyc')` and `_live_inputs_present` (the site
  already tests `country !== 'United States'`, so the two would disagree and
  the parity gate would go red); the ZIP routing in `resolve_query` and its
  static `NYC_ZIP_TO_BOROUGH` / `NYC_ZIP_CENTROIDS` tables, 404 note and
  `supportedNycBoroughs` key (`score_bulk.py` reads it); `_US_AIRPORT_CODES`
  (any US airport outside it reads about five times too quiet);
  `_quiet_across_all_geometry`; `_postcode_coverage_notice`, which would tell
  a Californian that "DEFRA publishes no noise contours for that airport";
  and the two provenance lines that say New York is the only USD city.
- **Site:** the three `currentCity === 'nyc'` tests gating the noise tiles;
  `handleUsZipSearch` and its not-found copy; the `deriveCityFromBorough`
  skip; the autocomplete suppression; `airportNoiseScale`; `crimeNote`;
  `buildPropertyLinks` (a US city gets Rightmove); the transit panel's subway
  copy; `PATH_COLORS`; and `MAJOR_AIRPORT` / `SECONDARY_AIRPORT`.
- **Scripts:** `NO_ONS_COMPARISON` and `DERIVATION_EXEMPT` (both REQUIRED, the
  gates red on an unaccounted city); `fetch_defra_road_noise.py --all`, which
  excludes New York by name and would fetch DEFRA tiles for California;
  `fetch_ea_flood_risk`; and `build_area_pages.py`, whose open-data writer
  skips only `nyc` and **would publish a US city into the UK CSV under the
  Open Government Licence**, and whose price formatter prints sterling only.
- **A pooling decision hides in here.** Price and growth pools are keyed on
  CURRENCY, so a second USD city joins New York's pool automatically and moves
  New York's affordability and growth scores. That is correct, and it makes
  every sentence saying "the USD pool is New York's five boroughs" false.
- **Launch on the site, not API-only:** `build_hpi_prices.py` writes every
  backend-only city's prices into the page's sterling pool with no currency
  filter, so an API-only US city would leak dollars into UK affordability.
- **Tests extend, they do not block:** the NYC-specific tests pass untouched
  with a second US city present, so each gap above ships green unless a test
  is added for it.

**The liveability component is now fully measured**, so depth is no longer the
blocker it was: transport landed as v3.6 and healthcare as v3.7 on 2026-08-11.
Breadth is now the reasonable next move - the ranked English city-regions above
inherit all four inputs with no new integration.

## What to do next, in order

1. ~~Transport, from NaPTAN.~~ **DONE 2026-08-11 as methodology v3.6.** All 81
   boroughs; 52 of 86 moved by more than 0.05; Cardiff became scoreable for the
   first time. The UK city-regions went from 2 of 4 liveability inputs to 3.
2. ~~Healthcare.~~ **DONE 2026-08-11 as methodology v3.7.** `epraccur.zip` 403s,
   but the **ODS syndication API** works and needs no key. All four liveability
   inputs were measured for **78 of 86 boroughs** at v3.7, up from 38. OSM
   Overpass was not needed, so no ODbL share-alike obligation was taken on.
   **Current figure: 84 of 99** (re-counted 2026-08-23 through the Lambda's own
   `live_resolution()`); the 86 became 99 when Leicester and Teesside shipped
   later the same day. This is a planning doc, so the live number is the one to
   plan against - the v3.7 figure is kept beside it as the record of what that
   change achieved, not as the current state.
3. **Cardiff to the site — newly possible as of v3.6.** Its four boroughs held
   `crimeRate` alone, one input, below the two-input floor. Transport made it
   two, so all four now publish a liveability score. Leaving `BACKEND_ONLY` is a
   ONE-WAY DOOR: every borough must be output-compared site-vs-Lambda first, and
   the road-noise and flood layers will read "NO DATA" there because both
   coverages are England's. **Nottingham did NOT move** — Broxtowe, Gedling and
   Rushcliffe gained transport but hold nothing else, so three of its four are
   still on one input. Education is an upper-tier county function, so Progress 8
   is published for Nottinghamshire rather than for them.
4. **Then** the ranked English city-regions above, cheapest first.
5. **Not yet:** Scotland, Wales-in-full, or any second country.

Related: `METHODOLOGY.md` §7.1 for how the derived bands are built,
`ROADMAP.md` for the live task list.
