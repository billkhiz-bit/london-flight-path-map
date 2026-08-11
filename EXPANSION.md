# Expansion: which cities and countries are reachable, and what each costs

**Written 2026-08-11.** Every figure here was measured on the day, not recalled.
Where something has not been verified it says so, because the expensive mistake
in this project has repeatedly been treating "the dataset exists" as "we have
the data" — DEFRA publishes an aircraft surface for all 16 English airports and
it still only reaches 0.5% of West Yorkshire's addresses.

## The one fact that shapes everything

**Nine of our eleven cities cost almost nothing to add because every source is
national.** The nation, not the city, is the unit of work.

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

81 local authorities across 11 cities. Measured against HM Land Registry's 2025
transactions, that is **34.6% of all residential sales in England and Wales**,
from 318 districts of which we cover 81.

## Next UK city-regions, ranked by market size

Ranked on 2025 transaction volume, grouped into the travel-to-work city-regions
the product already uses. **All are in England, so all are "free" in the sense
above** — the work is registry wiring, boundaries and a neighbourhood build, not
new sources.

| # | City-region | Likely LADs | 2025 sales | Notes |
|---|---|---|---|---|
| 1 | **Nottingham** | already in `LAD_TO_BOROUGH` | ~20k | **Already API-only.** Needs the outer districts resolved to reach the site |
| 2 | **Leicester** | Leicester, Blaby, Charnwood, Oadby & Wigston | ~15k | East Midlands Airport has a DEFRA surface |
| 3 | **Bournemouth + Poole** | BCP, Dorset | ~14k | Bournemouth Airport has a DEFRA surface |
| 4 | **Teesside** | Stockton, Middlesbrough, Redcar, Darlington, Hartlepool | ~13k | Contiguous with Tyne and Wear's data path |
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
   does not generalise.

**The liveability component is now fully measured**, so depth is no longer the
blocker it was: transport landed as v3.6 and healthcare as v3.7 on 2026-08-11.
Breadth is now the reasonable next move - the ranked English city-regions above
inherit all four inputs with no new integration.

## What to do next, in order

1. ~~Transport, from NaPTAN.~~ **DONE 2026-08-11 as methodology v3.6.** All 81
   boroughs; 52 of 86 moved by more than 0.05; Cardiff became scoreable for the
   first time. The UK city-regions went from 2 of 4 liveability inputs to 3.
2. ~~Healthcare.~~ **DONE 2026-08-11 as methodology v3.7.** `epraccur.zip` 403s,
   but the **ODS syndication API** works and needs no key. **All four liveability
   inputs are now measured for 78 of 86 boroughs**, up from 38. OSM Overpass was
   not needed, so no ODbL share-alike obligation was taken on.
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
