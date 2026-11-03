### Proposed: a Cost of Living layer, London first (raised by the founder, 2026-11-03; nothing built)

The question it answers: **"Is it pleasant, and what will it actually cost me?"** An estimated monthly cost to live
in a London borough for a stated household, beside the scores, deepening affordability rather than becoming a second
product. v1: London's 33 boroughs, two households (a single renter; a couple renting, no children), postcode-level
adjustments where an open source allows. Out of v1: childcare, other cities, New York and the Bay Area.

**What the sources actually offer (read on their own pages 2026-11-03; workbooks downloaded and opened):**

- **Rent: ONS Price Index of Private Rents (PIPR)**, monthly, OGL v3.0, one 17.9 MB xlsx per edition (edition of
  21 October 2026 holds September 2026; next 18 November 2026). **It publishes £ levels, not only an index**:
  `Rental price` for all properties, one, two, three and four-plus bedrooms, and by property type, keyed on ONS area
  codes. **Every English and Welsh local authority** (Scotland and Northern Ireland by Broad Rental Market Area), so it
  is NOT a London-only source: 96 of Sky Score's 97 sterling council areas have a September 2026 row. **The gap is the
  City of London (E09000001): no row in any month.** Caveats in ONS's own words and methodology: "official statistics
  in development"; a STOCK measure ("both new and existing tenancies"), so it sits below what a household moving in
  pays; levels are "a weighted geometric average of the predicted prices" (model-predicted, not observed averages);
  a 3-month moving average is applied to local-authority indices. London, September 2026: £2,338 all properties,
  £1,764 one bed (PIPR, Table 1).
- **Rent ranges: ONS ad hoc "Private rental market in London, April 2025 to March 2026"** (ref 3389, 27 April 2026,
  OGL v3.0), from VOA rent officers' data: count, mean, lower quartile, median, upper quartile by **borough (all 33,
  City of London included) and by POSTCODE DISTRICT (329)**, per bedroom category (room, studio, one to four-plus).
  Free postcode-district rent exists, so "postcode-level rent is paid data" is only half true. But ONS says these
  "should not be compared across time periods or between areas", they are an ad hoc release (no schedule promise),
  the borough sheet is keyed on NAMES only, and 98 of 329 districts have no one-bed median.
- **Council tax: MHCLG "Council Tax levels set by local authorities in England 2026 to 2027"** (25 March 2026, OGL
  v3.0, ODS). **Table 9 gives the area charge for every band A to H, per billing authority, keyed on ONS codes**,
  including parish and adult social care precepts; band ratios 6/9 to 18/9 in its note. Lowest London Band D:
  Wandsworth £1,028.21 (Table 9). **Band per home: VOA "Council Tax: stock of properties, 2026"** (now published by HM
  Revenue & Customs, 24 September 2026, OGL v3.0): CTSOP3.0 counts properties by band, property type AND bedrooms per
  local authority, so the band of one-bedroom flats is known per borough (Hounslow: 23,670 one-bed flats, middle band
  C); CTSOP3.1 goes to LSOA. Single occupants get 25% off (gov.uk, "Council Tax: who has to pay").
- **Transport: TfL Open Data**, OGL v2.0 "with specific amendments for Transport for London" (transport data service
  terms): registration, "Powered by TfL Open Data", 500 calls a minute per feed, revisable without notice, no implied
  endorsement. **Fares are not an open data feed** (the open data page lists none). The Unified API's Single Fare
  Finder (`/Stoppoint/{from}/FareTo/{to}`) prices a pair of stations, and zones come from StopPoint data, per TfL's
  tech forum, not its documentation (UNVERIFIED there); caps and Travelcards are not served by the API (forum,
  UNVERIFIED). `data/stations.json` holds name, coordinates and type only: no NaPTAN code, no zone.
- **Fuel: Fuel Finder EXISTS and is LIVE** (DESNZ; the guidance names VE3 Global Limited as operator under the Motor
  Fuel Price (Open Data) Regulations 2025; guidance published 2 February 2026; CMA enforcement from 1 May 2026).
  Prices within 30 minutes of a change; a CSV twice a day by email subscription, or a REST API (OAuth 2.0 client
  credentials, a GOV.UK One Login). **The DATA licence is not stated**: the pages carry only GOV.UK's site footer
  (OGL v3.0 for "content"), and the developer portal refused a connection from here (SSL handshake failure):
  UNVERIFIED until its terms are read.
- **Groceries, store locations: Geolytix Supermarket Retail Points**, quarterly (a 2026 Q1 update dated 30 April
  2026), "unrestricted use, no licensing requirements and without cost", acknowledgement requested, not required;
  Aldi and Lidl under "Discounters". The terms in the download's user guide are unread.
- **Groceries, a basket cost: there is no official one.** ONS Family Spending FYE 2025 (11 June 2026, about 5,000
  households): food and non-alcoholic drinks £73.70 a week, all UK households (workbook 4, Table A17). **Its
  workbook 4 does not split spending by household composition** (one adult vs two adults); the nearest is A57,
  households without children, £61.60 a week (UK, FYE 2023 to FYE 2025 pooled), and ONS removed tables A9 to A11
  for volatility this year. The **Minimum Income Standard** (Loughborough University's CRSP, JRF; London edition
  by Trust for London) is built per household type (London 2026, after housing costs, April 2025 prices: single
  £395 a week inner, £408 outer; couple £662 inner, £687 outer), but **no licence is stated** and its reports say
  reproduction for non-commercial purposes: permission first.
- **Energy: Ofgem price cap**, quarterly. 1 October to 31 December 2026, Direct Debit, average across England,
  Scotland and Wales: electricity 26.32p/kWh and 54.83p a day, gas 7.97p/kWh and 29.68p a day (Ofgem's regional
  page; London's own row not read). **Typical domestic consumption values changed on 1 July 2026** (Ofgem decision,
  27 May 2026, OGL): electricity single-rate low/medium/high 1,600 / 2,500 / 3,800 kWh, gas 6,000 / 9,500 / 14,000
  kWh. Checked: medium consumption at those average rates gives £1,723.61 a year, Ofgem's own "£1,723" headline.
  **London is one Ofgem region, so energy adds nothing to the difference between boroughs.**

**What the brief gets wrong, measured (2026-11-03):**

1. Rent is not London-limited by its source: PIPR covers every English and Welsh council area. London-only is a
   choice for the other components (TfL), not for rent. And PIPR misses one London borough (the City).
2. "Postcode-level rent is paid data" is only half true: ONS publishes London rents by postcode district free, with
   quartiles, but with a warning against comparing areas. It is a phase 4 candidate, not v1.
3. A discount-store DISTANCE cannot become a £ figure without store-level prices, which no open source has. v1
   shows the distance as a fact beside the cost, never inside it.
4. Fuel is a small, car-only cost (and a car's other costs, insurance and parking permits, dwarf it). Off by default.
5. Two of six components (energy, groceries) are London-wide constants, so a borough's cost differs from its
   neighbour's almost entirely through rent, council tax and transport. Say so on the page.

**The build, in order:**

**Phase 1: data ingestion, one builder per source, each with `--fetch` and an offline blocking `--check` (~7-9
sessions).** Raw downloads gitignored, derived JSON tracked (a `!data/...` line each), keyed on ONS codes, a row
each in `check_data_freshness.py` and `LICENSING.md`, each `--check` proven red on a defect first.

| Source | Builder (proposed) | Cadence | Licence | Format, access | Blocks v1? | Sessions |
|---|---|---|---|---|---|---|
| ONS PIPR | `build_rents_pipr.py` (all 97 sterling council areas, not only London: phase 3b needs them) | monthly (next edition 18 Nov 2026) | OGL v3.0 | xlsx download, no key | No. City of London withheld, said so | 1 |
| ONS London rents ad hoc | `build_rents_london_range.py` (name to code pinned once, like `CITY_LADS`) | quarterly, rolling 12 months (unscheduled) | OGL v3.0 | xlsx download | No; range only | 0.5-1 |
| MHCLG Table 9 + VOA CTSOP3.0/3.1 | `build_council_tax.py` | annual (late March, in force 1 April); stock annual (September) | OGL v3.0 | ODS (pandas' ODS reader failed on Table 10 on 2026-11-03; reading `content.xml` works), zip | No | 1-1.5 |
| TfL stations, zones, fares | `build_tfl_fares.py` + `build_city_stations.py` gaining NaPTAN codes and zones | fares annual (usually March); stations as NaPTAN | OGL v2.0 + TfL amendments | Unified API (key), fares from TfL's published fares document | No, but fares are hand-sourced: `--check` must hold the file to TfL's document | 2 |
| Ofgem cap + TDCV | `build_energy_cap.py` | quarterly (announced about five weeks before) | TDCV decision OGL; cap pages "(c) Ofgem 2026", licence to confirm | xlsx/PDF download | No | 1 |
| Family Spending, MIS, Geolytix | `build_groceries.py` | annual (June) / annual / quarterly | OGL v3.0 / permission needed / open, terms to read | xlsx / request / zip | MIS licence; household split | 1-1.5 |
| Fuel Finder | `fetch_fuel_finder.py` (optional, car variant) | CSV twice a day; we would take a 28-day average | UNVERIFIED | CSV by email, or API (One Login, OAuth) | Licence unread | 1 |

Acceptance: every `--check` blocking in preflight with a per-borough floor (33 London boroughs present, or named as
absent with a reason: the City's PIPR rent); a newer edition answering 200 is reported, as `build_hpi_prices.py`
does; no key in any tracked file; LICENSING.md rows written from the terms READ, quoting the attribution.

**Phase 2: the household cost model (~2-3 sessions).** `scripts/build_cost_of_living.py` reads only phase 1's files
and writes `data/cost-of-living-london.json` (per borough, per household: each component's central figure, low and
high, source id, period and resolution). Formulas and assumptions in the methodology draft: rent (PIPR one-bed,
range from the borough's quartile shape), council tax (the middle band of one-bed flats, 25% off for one adult),
transport (the home zone of the nearest station, a stated commute pattern, the cheaper of capped pay as you go and a
Travelcard, per adult), energy (London's cap rates times Ofgem's low consumption, range to medium), groceries (a
London-wide constant with a range), fuel (only with a car). Total = sum of centrals; range = sum of lows to sum of
highs, displayed to the nearest £10.

Acceptance: a worked example in METHODOLOGY reproduced by a blocking gate (as `check_worked_example.py` does for
§6); every figure traceable to a source id; a missing input is skipped and said so, never filled (no `.get(x, 0)`,
no 5.0 fallback); the total withheld where rent is missing; tests assert SETS of boroughs, not counts; an
independent yardstick: the non-housing subtotal must sit below the Minimum Income Standard for London's
after-housing-costs budget for the same household (MIS covers more items), and a borough failing it is a defect.

**Phase 3: surfaces (~6-8 sessions).**

- **API (~2):** `GET /v1/cost-of-living?postcode=&household=single|couple` (key-gated, its own throttle), and
  `?include=costOfLiving` on `/v1/score` for London; per-field provenance through `with_provenance` (new
  `PROVENANCE_SOURCES` ids and `PROVENANCE_PERIODS` rows; a new method word for published charges such as tariffs,
  fares and council tax, declared in `backend/tests/test_provenance.py`); `resolution` says borough or postcode on
  every field; OpenAPI and the MCP tools updated.
- **Area pages and the borough comparison (~1-2):** a "What it costs" block on the 33 London area pages (centrals,
  ranges, sources, the period of each), a cost column in London's `/area/` table; built by `build_area_pages.py`
  from the JSON, so a monthly rent roll reruns it (and re-dates the 33 pages in the sitemap).
- **Map layer (~2):** a London borough fill "Estimated monthly cost (single renter)" on `/map/`, darker = dearer
  (a measurement, labelled with the cost), legend in £ steps from the JSON, never a typed figure; the postcode panel
  adds the postcode-level parts (zone, nearest discount store).
- **The wording gate (~0.5-1, BEFORE any page shows a figure):** `tests/test_public_wording.py` would refuse the
  layer as written (see open questions): "£1,850 a month" matches `PRICE_SHAPE`, a cost that happens to equal one
  of our prices (25, 35, 150, 250, 499, 750, 2,500, read from /pricing on 2026-11-03) fails
  `test_our_prices_appear_only_on_pricing` by coincidence, and "% of households" fails `ADDRESS_SHARE`. Add a
  `COST_ALLOWED` list (the builder's exact sentence frame, by path prefix, with its reason) and make the builder's
  `--check` hold every cost figure byte-equal to a fresh build, as the planes pages are held.

Acceptance: drift check PASS after deploy; the City of London says why its total is missing; `EX1 1HS` and every
non-London postcode get no cost block and no "0"; checked at 390 and 1366 px; WCAG 2.2 AA gates pass.

**Phase 3b: rent into affordability for the renter view (methodology v5.8, ~3-4 sessions, after phase 3).** See
`integration.md`: PIPR rent (all properties, national pool) as a new `affordRent` component that the `renter`
persona weights instead of `afford`; both holders, parity tests, the site's engine, METHODOLOGY §4.2 and §5.2.
Measured on September 2026 rents: renter affordability would move by more than 1 point in 32 of 96 boroughs.

**Phase 4, later (not estimated until phase 3 has run):** postcode-district rent (the ONS London ad hoc first, free;
paid sources only after reading their reuse terms); EPC-based energy per dwelling (main fuel, floor area); water
(supplier areas); more households (a room in a shared house; families need childcare, out of scope); the other
twelve city regions (rent and council tax travel; transport does not: no open fare data outside TfL); a US rent
source per metro.

**Decisions for the founder (recommended):**

- **Context, not a score, for the total** (the integration draft): yes recommended.
- **Rent central from PIPR, the range from the ONS London quartiles**: yes recommended; never mix the two as one
  number without saying so.
- **Fuel off by default**: yes recommended.
- **Groceries a London-wide constant, the discount-store distance a separate fact**: yes recommended.
- **Ask Loughborough's CRSP for MIS permission** (for the grocery range and the validation yardstick): recommended.

**Gates:** the Constraints still bind: never pitched to conventional mortgage lenders or insurers, nor to estate or
letting agents (a monthly cost figure is exactly what a lender's affordability check wants); buyers named in the
brief that fit: relocation firms, employer HR, build-to-rent operators, proptech platforms on the buyer's side,
councils, charities, journalists. No figure is a quote: "estimate", with a range, on every surface. The standing
outreach gates apply before any of it is sold; the Geovation application (spring 2027) can describe it as built.

**Founder's steps first:** read and paste Fuel Finder's developer terms (the portal refused this session); register
a GOV.UK One Login for it only if fuel stays in; confirm the TfL app key covers StopPoint; email CRSP about MIS;
open the Geolytix download's user guide and record its terms.

**Effort, all phases 1 to 3b: ~18-24 sessions** (estimate; phase 1 is the most uncertain because two sources need a
licence answer before code).
