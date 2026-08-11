# Changelog

Sky Score release history. API contract is stable (`/v1/*`); breaking changes deploy under `/v2/*`. Methodology versions are tracked separately in [`METHODOLOGY.md`](./METHODOLOGY.md#20-changelog).

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### 2026-08-11 (night, latest) - Flood risk gets a source, and London moves

- **Flood risk is now derived from the Environment Agency** for all 73 UK
  boroughs, closing the last of the three fill layers. It was curated for London
  and New York and absent everywhere else.
- **Banded on the share of a borough's addresses at Medium or High risk** - the
  1%-annual-chance line, which is also what defines Flood Zone 3 in planning.
  Sefton 31.4%, Doncaster 24.4% and Kingston upon Thames 20.0% are the highest;
  60 of 77 boroughs band `low`.
- **This moved 18 of London's 33 boroughs, almost all for one reason.** RoFRS
  measures risk AFTER existing defences, so Tower Hamlets, Southwark,
  Westminster, Hammersmith and Fulham, Lambeth and Kensington and Chelsea fall
  to `low` behind the Thames Barrier and the tidal walls, while Kingston upon
  Thames rises to `high` because it sits upstream of the Barrier. The curated
  values had described the floodplain; this describes the likelihood of being
  flooded. **The detail panel now says so in as many words**, because "low" for
  a riverside borough is surprising without it.
- **How it is fetched is unusual, and every dead end is recorded.** The dataset
  publishes no WCS and no WFS, and its postcode-level product is retired, so
  `scripts/fetch_ea_flood_risk.py` renders the WMS and decodes the classes.
  `format_options=antialias:none` is load-bearing - without it a tile carries
  16,289 blended colours instead of 5 - and the colour-to-band mapping was
  verified against the service's own `risk_band` attribute by point-in-polygon
  containment, not by reading the legend. An unrecognised colour fails the fetch
  rather than silently reclassifying, and `--verify` re-runs the check.
- New York keeps its curated FEMA-derived bands and Cardiff is skipped: both
  coverages are England's.

### 2026-08-11 (evening) - The map layers were inventing data; now they measure it

- **Fixed: three map layers were painting a value nobody had measured.** Road
  noise, flood risk and air quality each ended their lookup with a fallback, and
  `borough-extra.json` carried those fields for London and New York only. So
  every borough of the other seven UK cities was painted one confident colour -
  "moderate" road noise, "low" flood risk, "moderate" air quality - in the same
  purple, blue and amber those words mean where a reading exists. The legend
  title above already said "(NO DATA)". The label said no data, the map drew a
  value, and the map is louder.
- **Road noise and air quality are now DERIVED for every city**, from DEFRA
  Strategic Noise Mapping Round 4 and the DEFRA background pollution maps, by
  `scripts/build_borough_bands.py`. 711 fields written across 73 boroughs.
  Sampling is at NSPL postcode centroids rather than over borough area, because
  an area figure is dominated by parks and farmland and reports the quiet of
  places nobody lives.
- **The data was one bounding box away the whole time.**
  `scripts/fetch_defra_road_noise.py` already pointed at a coverage id ending
  `England_Round_4_All`; the only London-specific thing in it was a hardcoded
  bbox. It now derives the bbox from each city's boundary file. Measured before
  generalising: 79-98% of cells over each city centre carry a reading.
- **London's values were replaced too.** Its road-noise bands were a hand-written
  literal with no script behind them - the same editorial shape as the Ofsted
  bands Progress 8 replaced - and several were assigned by airport proximity
  rather than roads. Hillingdon moves from "high" to "low" on the road layer for
  that reason. No score changes: flood and air quality are `plannedComponents`,
  and road noise reaches the score through the per-postcode path, not these bands.
- **Bands are anchored on WHO guidelines, never on percentiles.** Road noise is
  the share of a borough's addresses at or above WHO 53 dB Lden (high >= 2/3,
  moderate >= 1/2); air quality is the worse of NO2 and PM2.5 against the WHO
  2021 annual means. A first attempt banded on the borough median and put 30 of
  London's 33 boroughs in one band with "low" never occurring - true, and a
  useless map. Recorded in the script so it is not retried.
- **A borough with no reading is no longer painted at all**, the legend's
  "(NO DATA)" suffix is measured from the render rather than declared per city,
  and the detail panel no longer prints the literal word "UNDEFINED" for
  boroughs missing a field. Flood remains curated for London and New York and
  genuinely absent elsewhere - there is no Environment Agency integration yet.
- **Stopped fetching London's aircraft raster for cities it does not cover.**
  Every non-New-York city loaded `aircraft-noise-london-lden.png` and positioned
  it at London's bbox, which lands roughly 2,000px off the side of a Merseyside
  canvas: a 1.4 MB download on every city switch to render nothing.
- **New gate: `tests/layer-honesty.mjs`**, in preflight. A layer must paint
  exactly the boroughs that hold a reading. Fails in both directions - over-
  painting is an invented default, under-painting is a borough whose data the
  map cannot find. Proven red by reintroducing the fallback.

### 2026-08-11 - Six of the nine cities were unusable, and the phone could not reach them

- **Fixed: six of nine cities threw on selection.** West Midlands, West
  Yorkshire, South Yorkshire, Merseyside, Tyne and Wear and Bristol raised
  `Cannot read properties of undefined (reading 'center')` the moment they were
  chosen, so the map title changed and the geography did not. The projection's
  `center` and `scale` lived in a **second city registry** holding three cities
  while `CITY_DATA` held nine. Live since the six regions shipped on 2026-08-10.
- **Fixed: a second throw hidden behind the first.** The new cities' flight
  corridors were ported from the score Lambda, which names that key `coords`,
  while the frontend renderer reads `.coordinates` - so no corridors drew. It
  was only reachable once the first fault was cleared. South Yorkshire was the
  one new city unaffected, because it has no airports.
- **Resolved by removal, not by syncing two holders.** `center` and `scale` are
  now `CITY_DATA` fields and the second registry is deleted, which puts them
  under the key-parity assertion that already guards every other city field.
  `scripts/fit_city_projection.py` derives a new city's pair from its boundary
  file instead of having someone choose numbers by eye.
- **Fixed: the city switcher was unreachable on phones.** Nine cities made the
  chip row 453px wide against a 375px viewport, and it was absolutely positioned
  with no bound, so the map container simply clipped it: **three of eight UK
  cities could not be tapped at 320px**, two at 375 and 390. It is now a
  horizontal scroll strip with a measured edge fade, scroll-snap, and the active
  chip scrolled into view.
- **Country tabs met the WCAG 2.5.8 target minimum.** 14x24 and 22x24 became
  26x24 and 34x24 on touch, with the row's offset and gap absorbing the padding
  so nothing moves.
- **Three gates that could not see any of this were strengthened.** The
  responsive audit had always built a list of clipped elements and only printed
  it when the page itself scrolled sideways, so it read "ok" at all ten
  viewports throughout; it now fails on a control past the edge with no
  scrollable ancestor, and runs against source as well as against the live site.
  `tests/city-switch.mjs` is new and clicks every chip - nothing in the suite
  ever had. The local smoke stage now enumerates the registry rather than naming
  three cities while the app carried nine.

### 2026-08-10 (evening) - Six regions reach the website, and postcode scoring leaves London

- **The consumer site goes from 3 cities to 9.** West Midlands, West Yorkshire,
  South Yorkshire, Merseyside, Tyne and Wear and Bristol. Verified as an OUTPUT
  comparison before opening the one-way door: all 30 boroughs score identically
  on the site and in the Lambda. Input parity would not have been enough - the
  Manchester incident had matching inputs on both sides and still diverged.
- **Boundaries load through one registry-driven path.** The loader was
  `if london / else if manchester / else NYC`, whose own comment described the
  bug it had caused; six more branches would have entrenched it.
- **Postcode-level scoring now works for every city.** The gate was
  `if city != 'london': return 400`, and it needed **no reload** to remove: NSPL
  already stores the LAD code for all 2.7M rows, only the borough NAME was
  London-only. Verified against the live table before changing anything.
- **Corridors resampled to a common 1 km interval**, which had to precede
  un-gating: corridor distance is measured to the nearest waypoint, so a coarse
  polyline reads as further away and therefore quieter. Measuring first
  corrected a claim this repo made in three places - **London was 3.34 km
  median, not "~1 km"** - so the disparity was ~20%, not 4x. London's own change
  was measured: median 0 m, p90 390 m closer, max 2.7 km.
- **Two defects the un-gate exposed, both previously unreachable.** South
  Yorkshire has no airports, so `min()` raised on an empty sequence and every
  one of its postcodes would have 500'd. And the new resolver strings were
  static, claiming the NSPL table even when it had not answered - caught
  immediately by the test that flips `_LOCAL_POSTCODE_SERVED`.
- **Progress 8 landed for 31 boroughs across seven regions**, DfE KS4 2022/23
  Revised, 0 differing including the 42 values already present. That is what
  lifted these cities over the two-input liveability floor and made the site
  rollout possible.
- Cardiff and Nottingham stay API-only and cannot follow on current data.


### 2026-08-10 (latest) - Eight more UK city-regions on the API, and the DEFRA blocker turns out not to exist

- **`/v1/score` goes from 3 cities to 11.** West Midlands, West Yorkshire,
  South Yorkshire, Merseyside, Tyne and Wear, Bristol, Cardiff and Nottingham.
  **API only**, declared in `BACKEND_ONLY_CITIES` rather than discovered.
- **Every field is script-derived and verified against the publishing body**,
  and each check can go red: prices and trends against HM Land Registry HPI
  2026-05 (now a blocking preflight stage covering all cities, derived from the
  Lambda rather than a hardcoded pair), crime against ONS Table C4 (0 differ in
  every region), Progress 8 against DfE KS4 2022/23 **Revised** (0 differ,
  including the 42 values that were already here).
- **New loaders**: `build_hpi_prices.py`, `build_city_boroughs.py`,
  `build_aircraft_bands.py`, `build_progress8.py`, `build_locator.py`. Between
  them the data half of adding a city is now a command rather than research.
- **DEFRA Round 4 covers every one of these cities, and always did.**
  GetCapabilities on the WCS this repo already named advertises 16 airports with
  an Lden surface. `CITY_PROVENANCE` had been telling API consumers the raster
  "has not been run for" the city - false for nine cities, live in production,
  and corrected. We have not sampled it; the gap is in our pipeline, not in the
  regulator's coverage.
- **Aircraft bands are an ESTIMATE and say so.** Derived from each airport's
  runway geometry (OurAirports, verified against Manchester's existing data),
  calibrated on the only part of London that is genuinely distance-driven, and
  deliberately PESSIMISTIC because erring quiet is the one direction a noise
  product cannot be wrong in.
- **New York gets its own map.** The locator inset was hidden for NYC by a
  `country !== 'United Kingdom'` test; it is now a registry field, and
  `data/usa-locator.json` is generated rather than hand-authored.
- **Scoring is registry-driven and lazy.** `recalcAllScores()` and
  `hydrateBoroughExtra()` no longer name any city, so adding one needs no change
  in either. Also fixed: `showAutocomplete()` offered LONDON boroughs in
  Greater Manchester.
- **Two new blocking preflight stages**: WCAG over the source tree
  (`tests/a11y-source.mjs`) and `prices == HM Land Registry`. Both were
  red-proofed before being wired in.


### 2026-08-10 (latest) - London's growth input now comes from the source it always claimed

- **London's 33 `trend` values corrected to HM Land Registry HPI, 2026-05.**
  They matched **no HPI month at all** - the closest was 4 of 33, which is
  noise - while the same test identifies the *price* source unambiguously at
  33 of 33. Greater Manchester's ten already matched 2026-05 exactly. Two
  cities carried one provenance sentence from two different sources, and
  `CITY_PROVENANCE` has been telling `/v1/score` consumers that London's growth
  is *"HM Land Registry House Price Index (HPI), annualised price trend"*
  throughout. It is now true.
- **What moves**: 18 of 33 boroughs shift by 0.5 or more growth points, mean
  absolute change 0.84, mostly downward - the held trends were optimistic
  against HPI. Largest are Hackney 7.8 to 5.2, Southwark 8.8 to 6.5, Greenwich
  7.3 to 5.2. **Composite scores move for the `investor` persona only**, since
  METHODOLOGY section 5.1 weights `growth` for that persona alone.
- **Note for `?compare=previous`**: the previous-vintage table is unchanged, so
  a comparison spanning this release mixes a source correction in with real
  market movement. It is a one-off at this boundary.
- **New: `scripts/build_hpi_prices.py`**, so both fields are re-derivable rather
  than hand-entered. Keyed on **ONS area codes, not names** - name matching has
  failed here five times and each failure read as missing data rather than a
  spelling difference (`Brentwood` matching the borough key `Brent`;
  `ST. HELENS`; `THE VALE OF GLAMORGAN`; `CITY OF NOTTINGHAM`; `Westminster`,
  which HPI calls `City of Westminster`). The same authority is `ST. HELENS` in
  Price Paid and `St Helens` in HPI.
- **New blocking gate `prices == HM Land Registry`**, covering both holders.
  `avgPrice` and `trend` exist in `index.html` and in the score Lambda and
  **nothing enforced that they agree** - `test_borough_data_parity.py` compares
  the liveability inputs only. `--write` refuses to touch either file unless
  every borough resolves, because a half-applied correction is exactly the
  site/API divergence this repo has shipped three times.
- Covers all eleven cities and 81 authorities, so the eight Core Cities regions
  still to come inherit one source at one vintage.

### 2026-08-09 (night) - Country tier and locator inset, recovered from the spike branch

- **The city switcher is two tiers**: country tabs (underlined text, not chips,
  so the rows read as a hierarchy) above city chips showing only that country's
  cities. **The last city visited per country is remembered**, so UK to USA to
  UK returns you to Manchester rather than resetting to London.
- **Country is where the DATA breaks, not just the UI**: DEFRA versus no
  published US survey, Open Government Licence versus not, DfE Progress 8
  versus no equivalent, Land Registry versus curated New York prices. A flat
  row also put New York between two UK cities and would have tacked it onto a
  run of nine as Core Cities land.
- **Locator inset**: an England & Wales silhouette showing where the current
  city sits and which others exist. Three marker states separating by value
  rather than size - **solid dark is live, light disc with a dark rim is
  planned, orange ring is where you are** - captioned `ENGLAND & WALES / 2 OF
  10 CORE CITIES`. Clipped to England and Wales because Scotland and Northern
  Ireland sit in different data regimes, and at inset scale an empty Scotland
  and a broken one render identically.
- **Both tiers are generated from `CITY_DATA`**, so a Core City is a registry
  entry rather than markup, and the locator's ten markers already name the
  full roadmap.
- **This was recovered, not invented.** It was built on
  `worktree-core-cities-spike-2026-07-31` (commits `e892789`, `d83fbde`,
  `1dc2d2e`, `e227cc6`, `7d29ae9`, `12437a1`) and never reached master. An
  earlier search for it this session looked only at `index.html` on the current
  branch and wrongly concluded no prior version existed; the flat
  grouped-by-country row built on that conclusion is replaced by this.
- `data/uk-locator.json` is checked in and **has no generator** - it is an
  artefact, which is precisely why it must live in git rather than on one
  machine. It is deliberately **NOT in `sw.js` SHELL_ASSETS**: `cache.addAll()`
  is atomic and this is a decoration with a graceful fallback, so precaching it
  would let a missing decoration stop the service worker installing for every
  city. It does have a `make data-deploy` line, because a 404 removes the inset
  with only a `console.warn`.
- **Fixed the same bug in both ported harnesses**: their static server wrote the
  200 header before `readFile` could throw, so a missing file killed the run
  with `ERR_HTTP_HEADERS_SENT` rather than reporting. Found by red-proofing
  `locator-verify` - it exited 1, but for entirely the wrong reason, which is a
  green check's evil twin. Both now report `markers=0 land=0` cleanly.
- Both harnesses added to preflight (**18 blocking stages**).
- **The gate caught this before it shipped.** `local smoke (3 cities)` went red:
  it clicked `.city-btn[data-city="nyc"]` directly, and that chip does not exist
  while the UK tab is active, so it waited 30s for an element that was gone. The
  spike branch had flagged exactly this ("all three harnesses had to learn the
  new tier"), and master's smoke test post-dates that branch so it never got the
  memo. It now selects country then chip via a `selectCity()` helper - which the
  Manchester leg needs too, since that one crosses back from USA to UK.

### 2026-08-09 (night, later) - GM neighbourhoods, sourced rather than authored

- **85 Greater Manchester neighbourhoods in the ranking**, across all ten
  boroughs, built by `scripts/build_manchester_neighbourhoods.py` from
  **43,512 real HM Land Registry transactions** (2025). Previously
  `MANCHESTER_AREA_MAP` and `MANCHESTER_NEIGHBOURHOOD_DETAIL` were both `{}`,
  so "Show neighbourhoods" on Manchester rendered an empty table.
- **Nothing in it is authored.** London's and NYC's tables carry a curated
  median price and a hand-assigned `crime` modifier on a -2..+1 scale. Writing
  85 more of those would repeat the Ofsted-bands defect: numbers that no
  published threshold reproduces. Here `price` is the **median of real sales**
  per postcode district, coordinates are the **mean of live ONS NSPL
  postcodes**, and `borough` comes off the transactions themselves.
- **`crime` is 0 everywhere and says so.** There is no sub-borough crime source
  for Greater Manchester - ONS Table C4 is Community Safety Partnership level,
  which here is the borough. A per-neighbourhood modifier would have been
  invented. The panel states this rather than printing a silent zero.
- **A "neighbourhood" here is a POSTCODE DISTRICT** and is labelled as one, so
  it cannot borrow the precision of London's named areas. Districts under **30
  sales are dropped, not estimated** - M90 (Manchester Airport, 3 sales), M17
  (Trafford Park), M2 (city-centre commercial) among them - and every drop is
  printed by the build.
- **Labels are curated where the name is a checkable fact and only there.**
  Royal Mail's `locality` field is blank for 44 districts, which would have
  rendered "Manchester" 17 times; 26 got a postal-district name (M20 =
  Didsbury & Withington). A label is not a measurement, it enters no score, and
  the outward code stays visible beside it. The 15 with no widely recognised
  name keep their post town.
- **`neighbourhoodNote` added to all three cities**, forced by the registry
  key-parity test - which is the point. Adding a sourced table for one city
  while leaving the others undescribed would let the coarser ones borrow its
  credibility, so London and NYC now say their figures are indicative and
  their crime value is a relative modifier.
- **Fixed a latent fail-open in search**: the area branch tested
  `currentCity === 'nyc'` to decide whether an `areaMap` entry was an object,
  so a third city with object entries would have handed a whole object to
  `lookupPostcode` and queried postcodes.io for `[object Object]`. It now
  branches on the value's type.
- Land Registry's API cannot serve this: `propertyAddress.postcode=M20` returns
  **HTTP 200 with an empty list**, indistinguishable from "no sales", which is
  the same graceful-failure shape that let `/sold-prices` return nothing for
  its entire existence. The bulk CSV is used instead.

### 2026-08-09 (night) - Greater Manchester on the consumer site

**DEPLOYED 2026-08-09 night**, backend first then frontend, and verified at
each step. **Supersedes the API-only note in the entry below**: the site now
offers three cities.

- Verification: `/v1/regions` returns three cities; Trafford scores **4.1** on
  `/v1/score`; all 12 `SHELL_ASSETS` return 200 so the service worker installs;
  16 of 16 surfaces hash-match the source. **All ten GM boroughs verified
  identical between the deployed site and the deployed API** (3.6 Manchester to
  8.5 Wigan) - done by hand, because `tests/site-api-parity.mjs` probes by
  postcode and GM is borough-only, so the one gate that compares OUTPUT cannot
  see this city.
- City of London moved **6.7 to 6.6** as predicted from the working tree before
  the deploy, Camden unchanged. §7's notice threshold is a score moving more
  than **0.5**, so at 0.1 this is not a §7 event and no customer notice is due.

- **Greater Manchester is on the map**, and site and API agree on **all 48
  boroughs** across the three cities - verified by loading the working-tree
  page and diffing every borough against the working-tree Lambda, not by
  looking at the map.
- **Looking at the map was the point.** The first cut rendered ten correct
  outlines, the right airport and both approach corridors, and disagreed with
  `/v1/score` on **every single borough by up to 1.5 points** - Trafford read
  2.8 against 4.1. Nothing errored and nothing looked wrong. Two causes:
  `data/borough-extra.json` had no `manchester` entry, so the site could not
  see Progress 8 or crime, `live` fell below its floor of two and the
  composite rescaled onto the other three components; and
  `hydrateBoroughExtra()` assigned `london` and `nyc` and nothing else, so
  even once the data existed the site scored from an empty object.
  `recalcAllScores()` had the same two-city shape.
- **The parity guard could not have caught either**, which is why it was fixed
  first: both holders *had* the data, and the site never loaded it into the
  object it scores from. `BACKEND_ONLY_CITIES` is declared rather than
  inferred, so "someone shipped a city and forgot its data" stays
  distinguishable from "backend-only on purpose", and it fails in **both**
  directions - a declared city that *gains* site data also fails, so it starts
  being compared instead of staying permanently exempt. It is now
  `frozenset()`.
- **Map chrome comes from the registry.** `applyCityChrome()` replaces two
  `if (city === 'nyc') ... else ...` blocks holding ~20 DOM assignments, and
  runs at init where nothing ran before - first paint used whatever the markup
  said, so London's subtitle gained its "LONDON" prefix only after you visited
  another city and came back. That surfaced a defect **live on production and
  unrelated to Manchester**: the aircraft explainer had no id and nothing
  swapped it, so New York rendered a paragraph about DEFRA, LHR, LCY and LGW
  underneath a "BTS AIRCRAFT NOISE (dB DNL)" heading.
- **Manchester's legend does not say DEFRA.** It says ESTIMATED AIRCRAFT
  NOISE, and the explainer states the bands come from runway geometry and are
  not sampled from the DEFRA maps covering London. A regulator's name there
  would contradict, on the one surface a consumer actually reads, the
  provenance `/v1/score` publishes for the same city. Road noise, flood and
  air quality read **"NO DATA"** rather than borrowing London's labels for
  layers with nothing behind them; area search, stations and neighbourhood
  detail are declared empty, so those layers render blank instead of throwing.
- **The city would have shipped broken despite every local gate passing.**
  `data/*` is gitignored with files un-ignored one at a time, so the
  boundaries file sat on disk, the map rendered, and it was never in git - a
  fresh clone or a deploy would have served "Greater Manchester borough
  outlines could not be loaded". Added to `.gitignore`, to `SHELL_ASSETS` and
  to `make data-deploy`; `cache.addAll()` is atomic, so a file listed in the
  worker but missing at the origin stops the service worker installing **at
  all**, taking offline support for all three cities with it.
- `sw.js` **v1.0.17**, required twice over by that file's own rule
  (`index.html` and `data/borough-extra.json` both changed). Logged that
  v1.0.16 has no entry - bumped without one, which is what the log exists to
  prevent.

### 2026-08-09 (evening) - Greater Manchester, and the checks that let it in

**DEPLOYED** the same night, with the frontend entry above - not when this
entry was written. Note the gap: this said "needs a SAM deploy" and was
correct, while `ROADMAP.md` and the memory index simultaneously said Greater
Manchester was "LIVE ON THE API". Production answered
`{"error": "Unsupported city: manchester"}` for hours afterwards.

- **Greater Manchester is a third city on `/v1/score` and `/v1/regions`**, ten
  metropolitan boroughs. **API-only**: the consumer site still offers two
  cities, because `cityOf()` throws on a city missing any registry field and
  the frontend needs boundaries, area maps, stations and neighbourhood detail
  that GM does not have. A half-added city on the map is worse than none.
- **Unblocked by the redistribution, not by new data.** These figures have sat
  on a spike branch since 2 August. Manchester has schools and crime but no
  transport or healthcare, and while absent inputs defaulted to 5.0 a partial
  city scored WORSE than an empty one. The ten boroughs now span 4.3-7.2;
  against the placeholder formula they would span 4.5-6.4. Removing the
  placeholders widens the spread by 53%, and Trafford gains most (+0.8)
  because the strongest borough was dragged down hardest by two invented
  inputs.
- **Every figure re-verified rather than taken on the porting commit's word**,
  which mattered: that commit's own header comment said "schools NOT SOURCED"
  above ten Progress 8 values. Crime: **all ten exact** against ONS Table C4.
  Progress 8: verified sideways, since all 32 London p8 values are identical
  between that commit and master, so the same DfE extraction produced both.
- **`scripts/refresh_crime_from_ons.py` now takes `--city manchester`**, so
  that verification is repeatable rather than a one-off claim. Greater
  Manchester publishes **eleven** Community Safety Partnership rows in Table
  C4: the ten boroughs plus `Manchester Airport`, which is its own
  partnership and is excluded explicitly.
- **The checker loads the Lambda from source text, not importlib.** Proving it
  can go red means editing `app.py` and restoring it, and importlib validates
  `__pycache__` on recorded source size and mtime - a same-length edit
  restored within the same second matches both, so it ran bytecode compiled
  from code that no longer existed and reported drift against a value the file
  did not contain. Any inject-and-restore proof against an imported module has
  this hazard.
- **`liveResolution` no longer says "defaulted to 5.0"**, which had been true
  that morning and false that afternoon. It is a served string, so a stale one
  is a public claim about how a number was reached. The partial/unavailable
  boundary also moved: one measured input now reads `unavailable`, because the
  component is omitted below the floor of two.
- **Manchester's affordability provenance states it is NOT comparable across
  cities.** A first draft claimed the opposite from "same vintage as London",
  conflating source with scaling: min-max is cohort-relative, so Trafford at
  £393k scores 0.0 exactly as London's priciest borough does at several times
  that.
- **Three tests broke and none wanted a blanket update.** One hardcoded
  `len(vals) == 32` directly beneath a comment explaining it iterates `CITIES`
  so it survives new cities; one hardcoded which borough may move under
  redistribution, where the invariant is that no *complete* borough may; one
  compared two single-input cases the new floor collapses to the same answer.

### 2026-08-09 (later) - liveability stops filling gaps with a penalty

**DEPLOYED**: nothing. Both the Lambda and `index.html` are changed in source
and need a backend deploy plus a `web-deploy`. **`index.html` also still carries
the healthcare-heading fix from earlier today**, so the two ship together.

- **An absent liveability input is now redistributed, not defaulted to 5.0.**
  Its weight is spread across the sub-scores that exist, in proportion, so the
  remaining weights sum to 1.0 and their relative emphasis is unchanged.
  Below two of the four inputs `live` is not published at all and the component
  weight is redistributed across quiet/afford/growth by the same rule.
- **Why it mattered: 5.0 was not neutral.** London's computed liveability spans
  5.5-8.4, so the placeholder sat below every real borough. A place with no data
  scored worse than the worst place with data, and filling in one of four fields
  could push a place lower. That is what forced Greater Manchester to be "all
  four fields or none" - **that constraint is now lifted**, and GM can be
  sourced one field at a time.
- **This is a correction, not a reweighting.** 37 of 38 boroughs are
  bit-identical and a test locks it. The one that moves is **City of London,
  5.5 -> 5.2**, because 35% of its published liveability was a number about
  nothing: it has no Progress 8, having effectively no state secondary
  provision. That absence is correct and the borough stays scoreable - which is
  why the rule is redistribution and never refusal. It moved DOWN: the
  placeholder had been flattering it against a high crime rate.
- **Ported to `index.html` in the same commit.** The site scores client-side
  from its own copy, and three site/API divergences have come from one side
  changing alone. `site == /v1/score` could not have caught this one - it
  compares deployed against deployed, so a source change on both sides at once
  is invisible to it. Verified instead by loading the working-tree page and
  diffing all 38 boroughs against the working-tree Lambda: zero divergences.
- **Three call sites in `index.html` wrote `?? 5`**, reinstating the placeholder
  downstream of its removal - including `pcScore`, which the favourites Lambda
  persists to DynamoDB. All now route through one `combineWeighted()`. The two
  display rows render "no data" rather than painting a bar at an unmeasured
  value.
- **`CITY_DATA` gained `country`**, mirroring the Lambda, because the schools
  rule is jurisdictional: an English borough's input is Progress 8 while New
  York's curated tier is its input. Testing `city === 'nyc'` would have been the
  trap the 8 Aug registry removed, and getting it wrong drops New York's schools
  input silently rather than failing.
- **Three of five recorded Core Cities blockers were already closed** and were
  re-audited this session because the note was stale: `hasHistory`
  (`app.py:241`), `/v1/regions` iterating `CITIES` (`:3855`) and
  `validate_borough_vocabulary(CITIES)` at import (`:1264`). Only the Greater
  Manchester DEFRA raster remains.
- **Corrected "5.5-8.8"** in two docstrings. The real pre-change range was
  5.5-8.4; the wrong figure had been carried for months and quoted in
  `AUDIT_REPORT_2026-08-03.md`.
- **Branches:** master fast-forwarded; `london-corrections-2026-08-02`,
  `site-trust-fixes-2026-07-23`, `wave-13.8.1-fastlane-verified` and the merged
  `core-cities-2026-08-08` deleted after verifying each held nothing master
  lacked. `worktree-core-cities-spike-2026-07-31` kept - it is the only home of
  `data/manchester-boroughs.json`, `data/uk-locator.json` and four test files.

### 2026-08-09 - the loaders were dying, not slow, and air quality is finally served

**DEPLOYED**: nothing. The loaders write straight to DynamoDB and the score
Lambda reads it live, so postcodes gain their values as the run reaches them.
The `index.html` fix below is in source and **needs a `web-deploy`**.

- **`/v1/environment` returned its first NO2 and PM2.5 figures.** A Bromley
  coordinate now reads `no2AnnualMeanUgm3` 18.3 against a WHO guideline of 10,
  and `pm25AnnualMeanUgm3` 8.5 against 5. The endpoint has advertised those
  fields since 6 Aug and had never once populated them.
- **The air-quality loader had been DYING mid-run, twice, and the cause was
  configuration rather than data.** Windows entered sleep at 21:28:12 on 8 Aug;
  the checkpoint last moved at 21:27. Sleep does not kill the process - the
  system resumed six seconds later - it kills the in-flight HTTPS connections,
  and `list(ex.map(_put, batch))` re-raises the first worker exception with no
  `try` anywhere beneath it. One broken socket ended a 26-hour run at 28%.
  Neither death left a log; the cause came out of the Windows event log.
- **The fix already existed one file over.** `load_nspl.py` builds its client
  with adaptive retry and is the only loader here that has ever run to
  completion (5.8h, 2.7M rows); both DEFRA loaders used a bare client. Policy is
  now shared in `scripts/ddb_write.py` rather than pasted, because the part worth
  getting right is `FATAL_CODES` and two copies drift into one loader waiting out
  an error the other raises on.
- **The wait is bounded at 30 minutes on purpose.** Unbounded waiting swaps this
  failure for the worse one `load_nspl.py` already hit: an IAM denial spinning
  silently forever, making no progress and saying nothing. Verified by pointing
  the loader at a table it cannot write - it raised `AccessDeniedException` in
  3.1s, not 1800. Stalled postcodes are recorded **by name** to a failures file,
  never as a count, because a tally cannot be re-run.
- **Both loaders stopped over-reporting `written`.** Each added `len(batch)`
  whether or not the batch landed, so 25 items with 3 stalls claimed 25 - the
  same absent-read-as-present error one layer up from the data.
- **13 tests, both failure directions proven red.** Emptying `FATAL_CODES` fails
  6; making transient faults re-raise fails 3. **The first version of the test
  could not fail**: it parametrised over the constant it guards, so emptying that
  constant printed `7 passed, 1 skipped` and exit 0 - the test was deleted rather
  than failed. The codes are now written out in the test, because an expectation
  that reads from the code it checks cannot disagree with it.
- **Coverage lands alphabetically and central London is last.** The first `SW`
  row sits at ~85% of a full NSPL pass and the first `W` at ~93%, so outer London
  lights up early while the West End stays blank. This is the same shape as the
  road figure published as 99.2% while `W`, `WC` and `WD` held nothing. Air
  quality figures must not be read as complete from an outer-London spot check.
- **Fixed: the healthcare panel heading rendered as literal
  "DOCTORS &amp; CLINICS".** Reported from the live site. `renderGroup` escapes
  its own title and was handed a pre-escaped entity, so it encoded a second time,
  in both the heading and the "Search NHS ... services" fallback. The entity was
  correct when the string went straight into `innerHTML`; `escapeHtml()` was
  added later - rightly, since `/nhs` proxies OpenStreetMap names - and the old
  entity silently became a defect. The extension was unaffected: `panel.js`
  builds nodes with `textContent`, which needs no entity.
- **The raster loader stopped recommending `describe-table`'s `ItemCount`** for
  verifying a load. That figure refreshes roughly every six hours, so it reads 0
  through most of a run and a load that wrote nothing looks exactly like one that
  worked. It now prints a `get-item` on a known postcode.

### 2026-08-08 - both DEFRA loaders found dead, and the charts learned to say less

**DEPLOYED**: nothing. Extension is local-only and the loaders write straight to
DynamoDB, which the score Lambda reads live.

- **Both DEFRA loaders had been dead for a day and `load_status.sh` reported
  both as RUNNING.** Road stopped 6 Aug at 92%, air quality 7 Aug at 4%; the
  script branched on whether the checkpoint FILE EXISTED, and the loaders delete
  it only on a clean full finish, so every interrupted run leaves one behind
  forever. It also printed `rate 25.27it/s, elapsed 3:19:34` scraped from a log
  nothing had written to in 38 hours - a tqdm frame carries no timestamp, so a
  rate from a dead run is indistinguishable from a live one. Liveness now comes
  from the checkpoint's mtime, with thresholds derived from the measured write
  cadence (~15 rows/s over 1,000-row checkpoints means a HEALTHY loader is
  silent for ~65s, so anything under two minutes would have flagged the running
  loader as dead). The raw age prints on every line whatever the verdict says.
- **CORRECTION: "road 99.2%" below was the SOURCE GRID too, not what was
  served.** The 2026-08-07 correction caught the air figure and did not ask
  where the number beside it came from. The road pass had died at `UB6 9TJ`, so
  everything from there on - **`W`, `WC` and `WD`, the entire West End** - had
  never been served a road reading. `W1D 3QU` held no `roadLdenDb` at all until
  the pass was resumed and finished today; it now reads 56. Two coverage
  percentages written in one sentence, both describing the source rather than
  the table, and only one of them was checked.
- **Road load COMPLETE.** Air quality resumed and running; it writes in
  postcode-alphabetical order and had only reached `BA14` (Bath), so **no London
  postcode had an air-quality figure** a day after the coverage claim was
  corrected. Measured at 27 rows/s, ~26h to finish. Watch what a loader has
  REACHED, not the percentage: 4% of an alphabetical pass over the whole UK is
  0% of the city that matters.
- **EPC bands now render as a chart**, seven discrete columns with the MEES
  threshold (band E, the lowest a property may legally be let at) marked.
  Deliberately **not** a `scaleBar`: `cert.rating` looks like a plottable SAP
  score but is synthesised from `BAND_MIDPOINT` in the Lambda, because MHCLG's
  search API dropped the numeric rating - every band C in the country returns
  exactly 75. Plotting it on a continuous axis would assert a precision that no
  longer exists anywhere in the pipeline.
- **Sold prices render as a range with the asking price marked.** The asking
  price is now READ from the listing page and **still never transmitted** - the
  comparison happens in the tab, against a payload already fetched on a rounded
  coordinate. `extract.js`'s "never the price" header was corrected rather than
  quietly weakened, because that sentence is what the store listing and
  `privacy.html` both rest on. Returned **only on a positive `RES_BUY`/`BUY`
  signal**: on a letting Rightmove's `price` is a monthly figure, so £2,400 pcm
  would plot at the far left of a range of completed sales and read as the
  bargain of the century. No verdict anywhere - no colour, no "% above average"
  - because Land Registry lags completion and is unadjusted for size, condition
  or lease.
- **Panel collapses to its header**, and the EPC certificates and sold
  transactions fold into `<details>` under their charts. **Gotcha: `display:
  flex` on a `<summary>` removes the `::marker` box in Chrome**, so the
  `list-style: revert` that had been sitting on `.c33-note-sum` could never have
  worked - "About these readings" had been rendering with no disclosure
  affordance at all. Both kinds now draw their own triangle.
- **Typical rent, on letting listings.** ONS Price Index of Private Rents,
  average monthly rent for the borough the listing sits in, split by bedroom
  count — `Brent, 2 bed · £1,932 pcm · Borough average, June 2026 · ONS`.
  Built by `scripts/build_london_rents.py` from the 18 MB ONS workbook down to a
  275 KB bundle. **Deliberately NOT a chart**: Sold nearby earns a range because
  every dot is a real transaction on that postcode, and there is no rental
  equivalent below local-authority level, so the same visual grammar would claim
  a comparable the data cannot support. An e2e assertion exists purely to fail
  if a chart appears there. Borough resolves by point-in-polygon from the
  coordinate against outlines generated into the *same file* as the rents so
  they cannot drift; bedroom count comes through the page model's index
  indirection (`{"bedrooms":228}` → `flat[228] === 2`). **Bundled and served by
  the service worker**, not `web_accessible_resources` — which would expose it
  to every host page — so a whole data source landed with **no Lambda change and
  no deploy**. Renders nothing outside the 33 boroughs and for the City of
  London, which ONS does not publish, rather than borrowing a neighbour's figure.
  Corroborated independently: our June figure for Kensington and Chelsea is
  £3,596 against ONS's published May headline of £3,591.
- **The extension shows a different panel for lettings.** The `channel`
  (`RES_BUY` / `RES_LET`) already had to be read to stop a monthly rent being
  plotted against completed sales; it now decides what renders. On a letting
  **Sold nearby is removed** — Price Paid records sales, so on a rental it is a
  column of six-figure sums beside a property nobody is selling, and an empty
  section would still assert the question was worth asking. **EPC leads
  instead**, with a MEES line: for a buyer the band is context, for a tenant it
  is two live facts the listing page omits — band F or G generally cannot be let
  on a new tenancy, and the band is a heating bill paid on fabric only the
  landlord can change. Every sentence is about the **postcode's** certificates,
  because the extension never reads the listing address and so cannot tie one to
  this property; an e2e assertion exists purely to fail if that wording appears.
  A **null** channel keeps the sale layout, the conservative direction.
  **Rental comparables are deliberately absent**: there is no open,
  postcode-level UK rental dataset, and drawing a borough median in the
  sold-price chart's grammar would be the failure `decidePresentation()` already
  warns about.
- **Constant fields are elided from the sold list.** Land Registry keys on PAON,
  so a block of flats returns every sale at the same address and often the same
  type; six rows of `4 COLLINGHAM ROAD · flat-maisonette` read as one property
  sold six times. Anything identical across the list is stated once above it.

### 2026-08-07 - log retention actually bound, the company named as controller, and a gate that could be starved

**DEPLOYED**: `privacy.html`, `terms.html`, `index.html`,
`score-demo/index.html`. **AWS changed**: `FlightMapDeployPolicy` widened, 7 log
groups deleted, 30-day retention set on 7, new `SkyScoreCiTier` plan and key.

- **Log retention is 30 days, verified from the API rather than the console.**
  The 26 July attempt was reported done and found unchanged, so verification is
  a fresh `describe-log-groups` read. One deleted group held **raw email
  addresses from 26 Jun to 23 Jul**; deletion removes them, where retention
  would have preserved them for the window.
  - **The count was 14 groups, not the 13 recorded for weeks.** Restoring `chat`
    on 6 Aug added an eighth function and orphaned its predecessor, leaving
    **two `ChatFunction` groups** differing only in CloudFormation suffix. The
    runbook said to delete "ChatFunction" by name, which would have taken out
    the live one.
  - **The retention gate had been exempting that live chat Lambda.** Its orphan
    list was hand-maintained and named `ChatFunction`, so the fragment matched
    both groups and the only Lambda receiving free-text user input was
    downgraded to a warning and never compared against `privacy.html`. The
    active set now derives from `template.yaml`.
  - **`privacy.html` stated the retention claim twice.** Correcting §2d left the
    sub-processor table reading "indefinitely", and the check parsed §2d alone,
    so it passed a self-contradictory document. A contradiction guard was added
    and proven red against that exact bug.
  - **Residual, stated not hidden:** Lambda recreates a deleted group with no
    retention, so signup returns at *Never Expire* on the next signup. Durable
    fix written up in `DRAFT_security_retention_passage.md` §5, not applied:
    CloudFormation *creates* log groups, so declaring one of the seven that
    exist fails the whole stack update.
- **CUBITT33 LTD (13651304) is now the named operator and data controller** on
  `privacy.html`, `terms.html`, `SUBPROCESSORS.md` and `LIA.md`, from the
  Companies House record. Called a three-line change in three places; it was
  four. **The footer copyright still names a person deliberately** -
  controllership follows who decides purposes and means, copyright follows
  authorship, which does not move until the IP deed signs. **The ICO
  registration is now due in the company's name.**
- **A blocking gate was sharing a quota with a public page.**
  `check_score_sanity.py` hard-coded the demo key embedded in
  `score-demo/index.html`; that key's 2,000/month allowance ran out and
  **preflight went red with nothing wrong in the tree**, with 25 days until it
  reset. Per-day usage showed our own testing spent it, not demo visitors. CI
  now has its own plan and key via `.env`; a missing key fails loudly rather
  than falling back.
- **Every pointer target now meets the WCAG 2.5.8 24px minimum.** Mobile was
  already clean; this was all desktop. Layer toggles and city buttons were 22px;
  footer links 12-14px, which needed the hover underline moved off
  `border-bottom` (it draws at the padding edge, 6px adrift of its text) and
  compensation in **two** `.site-footer` rules, the base one and a 901-1366px
  override. Text lands within 1px of its original position.
- **`score-demo` never styled its email field.** The CSS covered
  `input[type="text"]` and `select`, so the signup email input rendered as a
  browser default beside a styled name field, on the page that sells the API.
- **The extension's close button was 20x20**, the panel's only dismiss control.
- **`/aws-debug` works for the first time**, and deploys can finally self-verify
  their own CloudFront invalidation.
- **Gotcha recorded:** `backend/iam-policy.json` is sanitised - 8 ARNs carry an
  account-ID placeholder - and pasting it verbatim makes IAM reject the document
  with **"The policy failed legacy parsing"**, which says nothing about account
  IDs. The failed save is harmless; AWS validates before storing.

**Extension (same day, later):**

- **The panel was mostly prose, and now is not.** A real SW5 listing showed
  three measurements carrying a two-sentence coverage notice, a two-sentence
  DEFRA vintage paragraph and a guideline sub-line each; outside London, one
  measurement under two notices. Visible text on the same listing: **1,660 ->
  1,317 characters**, with the environment section itself losing about
  two-thirds while keeping every fact.
  - Explanatory prose collapses into one **"About these readings"** disclosure.
    What stays visible is the fact - "(estimated)" in the label, the value, the
    guideline - and what collapses is the justification.
  - The DEFRA vintage became a **`2021` tag on the two rows it applies to**,
    replacing a paragraph that visually qualified the air-quality rows too.
  - Unavailable sources went from a heading plus a sentence each to **one quiet
    line**. Four dead sources had cost eight lines.
- **Each reading now carries a scale bar against its WHO guideline.** The domain
  is 0 to twice the guideline, with the guideline at the midpoint. The obvious
  alternative - the observed range across London - is a number that would be
  **invented at the point of drawing it**, which METHODOLOGY 4.6 forbids and
  which this project has twice had to undo. So the bar answers "how does this
  compare to the guideline", not "how does this compare to London". Over/under
  is legible from which side of the tick the dot sits, so it does not rest on
  colour; the 0-10 aircraft estimate gets a neutral fill and no tick, because
  colouring it green would assert it is good against a threshold that does not
  exist.
- **A full interactive map was considered and rejected.** MV3 forbids remote
  code, so D3 plus the borough GeoJSON plus the aircraft dataset - about 800 KB
  - would ship inside the extension and load on every listing, to duplicate the
  map Rightmove already shows on the same page. The bar does the job the map was
  wanted for, in about 2 KB, and removes text rather than adding it.
- Two defects the screenshots caught that reading the code did not: the quiet
  readout rendered **"5 /10 quiet"**, and Rightmove repeats the town so the
  address read **"Collingham Road, London, London, SW5"**.
- The vintage tag needed a real space text node rather than CSS margin -
  `textContent` was "Aircraft noise2021", which is what a screen reader
  announces.

### 2026-08-06 (evening, cont.) - the raster quarantine is lifted, and /sold-prices had never worked

**DEPLOYED**: `ScoreFunction`, `NhsFunction`, `SoldPricesFunction`, new
`ChatFunction`, `index.html`, `data/aircraft-quiet-london.json`.

- **`RASTER_TIER_QUARANTINED` is now False.** Condition 3 - the site computing
  quiet from geometry with no access to the raster - is closed by
  `data/aircraft-quiet-london.json`, 35,352 measured postcodes at 461 KB,
  fetched alongside `borough-extra.json`. It ships the **computed quiet score,
  not decibels**, so neither side reimplements the 45-to-63 dB ramp;
  `methodologyVersion` is embedded and the page REFUSES a mismatched file.
  - **Not the option originally recommended.** "Serve the site's quiet from
    `/v1/score`" is API-key gated, so the site would embed a key and meter every
    visitor. The sparse coverage that caused the problem is what made the
    client-side option cheap.
  - A first build disagreed with the API by 0.1 on measured postcodes: the
    loader stores `f'{lden:.1f}'` so DynamoDB holds 58.2 while the raster
    samples 58.24. Found only by querying the live API after deploying.
- **`POST /v1/chat` restored as RETRIEVAL-ONLY.** Context comes from invoking
  `ScoreFunction` directly; `verify_answer()` discards any reply containing a
  number absent from the retrieved payload. **The control earned itself on the
  third live question** - asked for a 2030 price forecast, the model produced a
  number despite the prompt forbidding it.
- **`GET /v1/environment?lat=&lon=`** - unauthenticated, reverse-geocodes
  server-side so the extension can reach postcode-keyed data from a listing's
  coordinates. Returns measurements only: no weights, no persona, no composite.
- **Road noise + air quality now reported per postcode.** Road via a WCS fetch
  (`scripts/fetch_defra_road_noise.py`) that removes the browser-only download
  step from METHODOLOGY §7; air quality from DEFRA PCM background maps. Both
  **reported, not scored** - weighting them would change every score ever
  returned. Coverage: aircraft 9.0%, road 99.2%, air 100%. **Every one of these
  three figures describes the SOURCE GRID, not the table** - see the two
  corrections below, 7 Aug for air and 8 Aug for road.
  - **CORRECTION (2026-08-07): the air figure described the SOURCE GRID, not
    what was served.** `scripts/load_defra_air_quality.py` was written and the
    two DEFRA CSVs downloaded, but **the loader was never run**, so
    `no2Ugm3`/`pm25Ugm3` were absent from every row of
    `london-flight-map-noise-raster` and **`/v1/environment` had never returned
    an air-quality figure to anyone**. The Lambda code was correct throughout,
    which is why nothing failed: the endpoint omits a key when a measurement is
    missing - a deliberate design so an absent reading cannot be misread as a
    good one - and that makes "never loaded" indistinguishable from "not
    measured here", at HTTP 200. Same shape as the `/sold-prices` defect two
    entries down. Found on 2026-08-07 only because the extension gained a bar
    chart for those two rows and the rows never appeared. Load started
    2026-08-07 22:09.
- **`/sold-prices` HAD NEVER RETURNED A TRANSACTION.** `.replace(' ', '+')` then
  `quote()` sent Land Registry the literal string `WA2+8SN`. Every postcode
  returned `[]` with HTTP 200 - indistinguishable from a postcode with no sales.
  The consumer site's sold-prices panel has been silently empty for its whole
  existence. Two parsing bugs surfaced once data flowed: RFC-style dates sliced
  to `Thu, 17 Oc`, and `propertyType.prefLabel` rendering as `[object Object]`.
- **`/nhs` fixed twice.** First the Overpass budget and radius; then the real
  cause - Lambda egress uses AWS-managed **shared IPs**, so we compete for
  Overpass's per-IP budget with all of AWS. Greater London now ships inside the
  function: 3,224 POIs, 447 KB. Mirrors were rejected;
  `overpass.osm.ch` returns **200 with zero elements** for London queries.
- **DEFRA vintage stated beside the readings**, not only in a footer. The label
  said "Round 4 (2022)", which reads as 2022 data; it maps **2021**, a
  COVID-affected year, so readings err quiet. No correction factor is applied.
- **Responsive audit added** (`tests/responsive.mjs`, 10 viewports). No
  horizontal overflow anywhere. Found `#first-hint button` at 17x44 on mobile
  and 17x18 on desktop - raised to 44px height in a media query, never widened.
- **`extension/`**: Transport dropped (Rightmove already prints stations), EPC
  and sold prices added, WHO guidelines on every environmental row, official
  EPC band colours. **Blocking preflight stages: 12 -> 16.**

### 2026-08-06 (evening) - coverage notices, a retrieval-only chatbot, and /nhs fixed

**DEPLOYED**: `NhsFunction`, `ScoreFunction`, and a new `ChatFunction`.

- **`/nhs` was falling back to nhs.uk links on every request**, on both the
  site's healthcare panel and the extension. Not rate limiting - the same query
  from a second IP also returned 504. `[out:json][timeout:10]` is the budget we
  hand *Overpass*, and a 3 km radius returned 187 elements to display 3 per
  category. Now 1.5 km / `[timeout:25]` / 30s client. **Verified live**: The
  Medical Chambers Kensington at 159 m.
- **`context.coverage` added to `/v1/score`.** `quietResolution` always said HOW
  an answer was reached, but in machine terms - only an integrator would know
  `'postcode'` means "DEFRA never measured here". 89.5% of London falls outside
  the aircraft contours. Coverage now carries a plain-English notice per
  component; it appears on **every** response, since a field that shows up only
  on failure teaches readers to ignore its absence. Keyed so airQuality and
  roadNoise slot in unchanged.
- **`POST /v1/chat` restored as RETRIEVAL-ONLY**, not the free-form assistant
  deleted in `6bad8ce`. Context comes from invoking `ScoreFunction` directly, so
  an answer cannot drift from the API. `verify_answer()` checks every number in
  the reply against the retrieved payload and **discards** the answer if one
  came from nowhere. API-key gated.
  - **The control earned itself on the third live question.** Asked for a 2030
    price forecast, the model produced a number despite the prompt forbidding
    it; `verify_answer` caught it and the reply was replaced. **The prompt
    failed and the control held** - which is the entire argument for building it
    this way.
  - Composition worth noting: asked about noise, the chatbot volunteered the
    coverage notice added hours earlier, unprompted.
  - Cost ~£0.25 per 1,000 messages (Nova Lite, 400-token cap).

### 2026-08-06 (later the same day) - the browser extension works on real Rightmove, and the tests that said it did were circular

**`extension/` now works on live Rightmove listings.** It had 33 passing checks
while never once working on a real page, because every fixture was one Claude
wrote, encoding the assumption that a portal serialises coordinates as
`"latitude":51.47`.

- **Rightmove ships `window.__PAGE_MODEL = {"data":"[...]"}`** - a JSON *string*
  containing JSON (so keys arrive escaped as `\"latitude\"`) holding a
  **flattened** array where `{"latitude":160}` is an **index**, not a value.
  `flat[160] === 51.49423`. Two leading underscores. No pattern reachable by
  reasoning would have matched. `fromRightmovePageModel()` unpacks it and runs
  first in the cascade.
- **Timing was the other half, and would have defeated the unpacker too.**
  `run_at` was `document_idle`, which fires after `load`; the page model is
  transient and React hydration removes it. Observed directly - present on a
  fresh load, gone from the same tab minutes later. Now `document_end`.
  **When extraction finds nothing, suspect *when* you looked before *how* you
  parsed.**
- **`tests/fixtures/rightmove-real-sw5.html`** carries that script verbatim from
  a saved listing. It is the first fixture in the extension capable of
  contradicting its author; both suites now run against it.
- **The panel no longer blocks on the slowest upstream.** It did `Promise.all`
  over `/transport` and `/nhs`; Overpass can take 30s or hang, so the panel sat
  on "Loading..." with TfL's answer already in memory. One endpoint per message
  now. Measured: transport paints in **~880 ms**, cached view **~40 ms**.
- **Degraded paths tested in a browser**: a non-London property suppresses the
  transport section with a caveat rather than rendering "0 stations" (an absence
  of DATA is not an absence of TRANSPORT); an unlocatable page renders nothing
  at all, not an inert badge.
- Preflight gained **`extension extraction`** and **`extension e2e`**, taking
  blocking stages from 12 to **14**. `tests/fixtures/` is globally ignored by
  ESLint - captured third-party markup is evidence, not source.
- Known limit recorded: the "GP surgeries" bucket is OSM `amenity=doctors`,
  which tags private clinics identically to NHS practices. Relabel or filter
  before demoing.

### 2026-08-06 - privacy.html is true again, and the check guarding it now reads the page

**`privacy.html` §2d now carries Version B**: logs are "currently retained
indefinitely", with the 30-day policy described as intended rather than done.
The subprocessor table row was corrected to match, because leaving the two
disagreeing would have swapped one false statement for an internal
contradiction.

**This unblocks the deploy the 2026-08-05 entry held back.** That entry withheld
`privacy.html` because its source claimed 30-day retention while AWS reported
never-expire, so shipping it would have replaced one untruth with another. The
source is now accurate, and **the live page still reads "7 days", which is
false** - so `privacy.html` should be deployed. It is the only surface still
publishing the original claim.

- **`scripts/check_log_retention.sh` rewritten to do what its name says.** It
  has been called "log retention == privacy.html" since it was written and
  never opened `privacy.html`; it hardcoded `WANT_DAYS=30`. That made the
  console work the only route to green, so making the page *truthful* left the
  gate **red on a truthful tree**. `DRAFT_security_retention_passage.md` §2b had
  flagged exactly this. It now parses the claim out of §2d and asserts AWS
  matches whatever the page says - strictly stronger, because it still reds on
  "page says 30, AWS says None" **and** on the reverse, which the old version
  could not detect. Both directions proven red, plus the unparseable-claim case.
- **The 6 orphaned log groups now WARN rather than fail.** Under an
  "indefinite" claim they do not contradict the page, and deleting them needs
  `logs:DeleteLogGroup`, which `flightmap-dev` lacks - blocking there gated
  every commit in the repo on a console action nobody can take from the CLI.
  **The console work in §1 is still outstanding**, and the warning names the
  Signup group specifically: raw emails from 26 Jun - 23 Jul 2026, in a location
  §2b does not disclose.
- **Windows gotcha, found by a false red:** the AWS CLI emits CRLF here, so the
  retention field arrives as `None\r` and never string-equals `None`. Every
  group compared unequal against a value it visibly matched. The `tr -d '\r'`
  is load-bearing; the same bug on the name-matching side would have failed
  green rather than red.
- **`extension/` added** - an unlisted Rightmove demo using `/transport` and
  `/nhs`, the two endpoints that already take lat/lon and need no API key. Not
  for publication. `/v1/score`, `/epc` and `/sold-prices` are all
  postcode-keyed, so they need a lat/lon to postcode reverse lookup that does
  not exist yet; aircraft noise stays out while the DEFRA quarantine stands.
  The directory was outside the lint script's file list on arrival and is now
  inside it.
- **`ESLint` preflight stage relabelled** from "(index.html)" to "(8 targets)",
  stale since the 2026-08-03 config change. The command was always right; the
  label understated it, which is the same failure as a label that overstates.
- **iOS rebuild confirmed necessary and unblocked.** The shipped binary is
  commit `4af9bc5` (29 May); the native bundle fix is `3b31ca9` (3 Aug), and
  `git merge-base` confirms it is not an ancestor - so every App Store install
  still scores liveability without `borough-extra.json`. `3b31ca9` is already on
  `origin/master`, so the rebuild never depended on this commit gate. Building
  after this push carries both that fix and `d7c5af3`, the postcode
  double-rounding correction, in one review cycle.

### 2026-08-05 - a terms page finally exists, and the privacy policy was found to be publicly false

**DEPLOYED AND VERIFIED LIVE** the same day: `fonts/`, `terms.html` (now serving
at `/terms`, previously 403), `index.html`, `pricing`, `changes`, `api/`, both
`score-demo` pages, `prototype/` and `sw.js`. Verified from CloudFront:
`/terms` returns 200, `/fonts/inter.woff2` returns 200 as `font/woff2`, and the
live homepage carries **zero** references to `fonts.googleapis.com`.

**`privacy.html` was deliberately HELD BACK.** Its source now claims 30-day log
retention while AWS still reports never-expire, so deploying it would swap one
false statement for another. The live page therefore still reads "7 days", which
is equally untrue - the honest fix is the 15 minutes of console work in
`DRAFT_security_retention_passage.md` §1, after which it deploys truthfully. One
consequence to note: with the fonts change live, the live subprocessor table now
lists Google Fonts as a subprocessor that is no longer used. That is
over-disclosure, which is the harmless direction, and it clears when
`privacy.html` ships.

- **`privacy.html` §2d states three things that are not true**, found by
  checking AWS rather than reading the document. It says server logs are
  "retained for 7 days then automatically deleted"; **all 13 log groups are
  verified `retentionInDays: None`**, meaning never expire. It describes **API
  Gateway logs that do not exist** - there is no API Gateway log group in the
  account and no `AccessLogSetting` in `template.yaml`, so what actually exists
  is 13 Lambda *execution* log groups. And the subprocessor table calls them
  "anonymous request logs" when the Signup group held **raw email addresses**
  from 26 Jun to 23 Jul and **still holds 8,730 bytes today**. This is a UK GDPR
  Art 13(2)(a) transparency problem on top of an Art 5(1)(e) storage-limitation
  one, and it means `privacy.html` and `SECURITY.md` now **contradict each other
  in public** - SECURITY.md honestly describes the gap as open. **Not corrected
  **Corrected to 30 days, and the claim is now enforced rather than asserted**:
  `scripts/check_log_retention.sh` reads the live log groups and fails while
  they disagree with the document, wired into `/preflight` as a **blocking**
  check. It is **red right now, deliberately** - the retention policy is console
  work that `flightmap-dev` cannot perform (`logs:PutRetentionPolicy` is not
  granted, though `DescribeLogGroups` is, which is what makes this checkable).
  The repo is public, so a privacy claim ships on `git push` rather than on
  deploy, which is why the gate guards the commit. Two honest routes to green
  and no bypass flag: apply the policy, or revert §2d to the interim wording in
  `DRAFT_security_retention_passage.md` §2b. **The old "7 days" claim was never
  true at any point in the project's life**, and it survived because nothing
  compared the document to the infrastructure.
- **`terms.html` added** - the first liability page Sky Score has ever had. A
  repo-wide search for `no warranty`, `as is`, `not liable`, `not advice` and
  `terms of use` returned **zero hits** outside documents discussing the gap.
  What had been assumed to be the disclaimer was `METHODOLOGY.md` §18, a
  *regulatory-scope* note that says nothing about accuracy and lives in a GitHub
  file rather than on any page a user reads. Covers informational-not-advice, no
  accuracy warranty, acceptable use, ODbL/TfL attribution pass-through, and
  liability capped at fees paid, with the mandatory UCTA 1977 s.2(1) carve-out
  and CRA 2015 statutory-rights preservation. **Drafted for a solicitor to
  review rather than to replace one**: UCTA s.2(2) and CRA s.62 make an
  over-broad exclusion *void rather than weak*, so a bad one is worse than none.
  Linked from both `index.html` footers and `privacy.html`, and added to the
  em-dash gate, html-validate, the a11y scan and the deploy-drift list.
- **`LIA.md` added.** Narrower than expected: `privacy.html` relies primarily on
  Art 6(1)(b) for key issuance, so the assessment covers only the 6(1)(f)
  processing (one-key-per-email, rate limiting, abuse investigation). Its §6
  records that **the balancing test is conditional until log retention is
  actually bounded**, rather than asserting a conclusion the infrastructure does
  not support.
- **Google Fonts removed from all nine deployed pages.** Every page load was
  transferring the visitor's IP address to Google in the US;
  `SUBPROCESSORS.md` row 12 had already recorded this as an open compliance item
  citing *LG München I, 3 O 17493/20* and naming self-hosting as the remedy.
  Fonts are now vendored by `scripts/vendor_fonts.py` into `fonts/`, and both
  Google hosts are out of every CSP and out of `sw.js` `SWR_ORIGINS`.
  **Google's CSS hides that these are variable fonts** - it emits one
  `@font-face` per weight, all pointing at the same file, so a naive fetch wrote
  **four byte-identical copies of Geist**. Deduplicated by checksum: 371,488
  bytes across 11 files became **141,188 across 4**. The declared weight *range*
  is load-bearing and fails silently, since a variable font declared `400 600`
  renders a 300-weight request clamped at 400 with no warning; `index.html` uses
  JetBrains Mono 300-700, wider than the range first vendored.
- **`tests/fonts-selfhosted.mjs` added and proven able to fail** (exits 1 on a
  removed woff2). It serves the repo over a local static server, so it validates
  **source before a deploy**. Uses `document.fonts.load()` rather than
  `check()`: fonts are fetched lazily, so `check()` only sees what painted above
  the fold and reported Geist Mono missing on `score-demo/index.html`, where it
  is declared on four selectors inside a results panel that is empty until a
  query runs.
- **`LICENSING.md` corrected**: its TL;DR grouped OpenStreetMap with OGL and TfL
  as "similar". **ODbL 1.0 is share-alike**, which for a paid B2B product is a
  materially different obligation. `privacy.html` had described it correctly
  since 2026-08-03, so the two documents disagreed and the **more permissive
  reading was the one in the licensing file**. Now records the three reasons
  current use is very likely outside the Derivative Database trigger, the
  load-bearing one being that healthcare scoring comes from
  `data/borough-extra.json`, not from OSM.

### 2026-08-04 - the DEFRA raster maps a COVID year, and the band mapping was built for the wrong dataset

**Deployed:** the consumer site, `/pricing`, `/api/`, `/score-demo/*` and the
prototype. **Not deployed:** the signup Lambda's new `upgrade` block, and
`privacy.html`.

- **The dB-to-quiet curve was re-derived, and the premise three documents
  rested on was false.** `AUDIT_REPORT.md` said "every DEFRA value is above
  55 dB"; `BAND_MAPPING_ANALYSIS.md` said "there is no 45-55 dB contour to
  score against" and recommended **no code change** on that basis. Reading
  `data/defra_lden_2022.tif` directly refutes both: **2,359,172 valid cells
  spanning 40.0 to 88.9 dB**, and 40.0 to 73.0 dB at London postcode centroids
  with a **median of 51.0**. The band table had been derived for DEFRA's
  *published reporting bands*, which do begin at 55, and then applied to the
  *raster*, which begins at 40 - so its top bucket spanned 40.0-55.0 dB and put
  **80.4% of every measurement we hold (15,173 of 18,862 postcodes) on a flat
  10.0**. `lden_db_to_quiet` is now a continuous ramp between two cited
  thresholds, 10.0 at WHO's 45 dB to 0.0 at ~63 dB Lden: **101 distinct values
  instead of 5**, Heathrow **7.5 to 2.7**. 16 tests.
- **DEFRA Round 4 maps 2021, a COVID year, and every surface fed by it errs
  quiet.** Round 4 documentation calls the result "a highly anomalous
  situation". London City flew **12,921 movements in 2021 against 80,751 in
  2019** - 16%, or **-8.0 dB** on a logarithmic energy sum. The prototype's
  noise panel now names the year; so does the consumer map legend, which had
  said "Round 4, 2022 data" when 2022 is the *publication* year. **Re-anchoring
  needs Round 5 (~2027); no correction factor has been invented.**
- **A site-defect finding was raised and then retracted the same day.** The
  raster/Haversine gap concentrated at London City (+4.03 against Heathrow's
  +1.97) looked like the airport term being distance-only. The COVID
  differential explains essentially all of it, so the "2,007 postcodes shown at
  2.5/10" figure is withdrawn as evidence. **The mechanism is still real** - the
  airport term uses `min(distance)` across all five airports while the heliport
  term beside it is movement-weighted - **but its magnitude is now unmeasured.**
- **The raster tier stays quarantined**, on a third condition nobody had listed:
  the consumer site scores quiet from Haversine and cannot read the raster, so
  lifting the flag re-opens the site/API divergence across 18,862 postcodes -
  and the parity test would not catch it, because the geometry it compares still
  matches.
- **Professional's score ceiling is published**, completing the 2026-07-29
  decision: 100,000 requests/month under a **fair-use ceiling of 1,000,000
  scores/month**. Free's ceiling is an arithmetic identity; Professional's is a
  contractual cap deliberately below the product (100,000 x 100 = 10,000,000),
  and `scoreCeilingBasis` now marks which is which.
- **The Article 28 sub-processor register was materially incomplete and its
  residency claim was false.** It stated the request body "never leaves UK AWS
  infrastructure during processing"; the `nhs` Lambda sends lat/lon to
  **`overpass-api.de` in Germany**. Ten rows added across server-side upstreams
  (TfL, MHCLG, HM Land Registry, Overpass) and browser-contacted third parties
  (Google Fonts, GitHub, US DOT, EPA, FEMA). **Google Fonts is recorded as an
  open compliance item, not as compliant.**
- **`quiet` measures aircraft noise only.** README and METHODOLOGY both said
  "Aviation + road noise impact"; there is no road-noise term in the engine. The
  live consumer surfaces were already correct.
- **Gate and deploy coverage:** `backend/tests/` was outside every ruff target;
  `web-deploy-all` covered 4 of 15 public surfaces while being named "all", so
  eleven live files had no deploy command (audit finding 38). Both closed.
- Also: audit findings 30, 49, 53 and 62 closed; the `/api/` sample response and
  README's, both wrong in every field, replaced with live captures; README's
  persona count corrected from five to eight.

**Second half of the day — everything below is now DEPLOYED.**

- **The site and the API disagreed on 13% of London postcodes, and every
  existing parity guard was blind to it.** Found by driving the live site with
  `tests/rehearse.mjs` and diffing against `/v1/score`: SW11 1AA rendered
  **6.5** against the API's **6.4** while *every component matched exactly*
  (5 / 6.7 / 4.3 / 8). `calcScores` rounds components to 1 dp for display and
  the postcode panel recombined **those rounded values** — double-rounding,
  where the API sums at full precision and rounds once. Measured over 30 random
  live postcodes: **4 of 30, in both directions** (W3 7BN site-high, SW12 0DL
  site-low). `calcScores` now also emits `scoresRaw`; anything recombining into
  a total reads that. The **borough** score was always correct — only the
  postcode panel re-derived from rounded values.
- **New gate: `site == /v1/score`.** The three existing parity guards all
  compare *inputs* — geometry, weights, components — which is exactly why the
  above survived. This one compares the **output**: the number a user sees
  against the number a customer receives. Proven able to fail against the real
  pre-fix build, reproducing all three divergences and correctly passing the
  postcode that never diverged. Advisory for now.
- **New gate: `deployed == source`.** Compares all 14 public surfaces against
  what CloudFront actually serves. `privacy.html` had been corrected in git —
  removing a **false** claim that request data "never leaves UK AWS
  infrastructure" — and then sat unpublished, so the live policy kept saying
  something untrue. Advisory, because drift between commit and deploy is the
  expected state.
- **`?methodology=` version pinning is withdrawn, not fixed.** It was promised
  in three places including a **contractual 14-day grace period**, and the
  parameter is read nowhere in the Lambda — a caller passing it was silently
  ignored while believing they had pinned. Real pinning needs retained data
  vintages *and* retained formula paths; it will be built when a contract
  requires it. `?compare=previous` and `/v1/changes` cover the "what moved and
  why" case meanwhile. §16's "currently 3.1" was also stale by four versions.
- **Cloud review acted on.** It caught an assertion I orphaned earlier the same
  day — inserting tests mid-method split `test_gate_can_actually_fail`, leaving
  it asserting only `Limit > 0` while its comment still promised the gate could
  go red. Also flagged the OpenAPI spec, which I had edited that morning and
  still left out of sync with the Lambda's new `upgrade` block *and* carrying
  two "aviation + road noise" strings the correction wave had fixed elsewhere.
  A `348` vs `334` disagreement it reported as a mistranscription turned out to
  be **two correct measurements of different questions**: 334 postcodes sit at
  or above the 63 dB floor, 348 *read* 0.0 once `round(x, 1)` is applied.
- **Backend deployed.** `SignupFunction` now returns the `upgrade` block;
  `ScoreFunction` shipped the re-derived quiet curve and the widened vocabulary
  guard, verified **unchanged in production** as intended — the curve is live
  but dormant behind the quarantine.
- **CLAUDE.md's documented backend deploy could never have worked**: it sourced
  `../.env`, which does not exist, and the `&&` chain aborted the whole deploy
  rather than failing on a missing token.

### 2026-08-03 - prototype stops publishing invented noise readings

- **The 3D prototype presented fabricated decibel figures at named real
  locations as if measured**, under a pulsing green "live" dot. Both the levels
  and the distances were wrong: Hounslow was labelled 2.1 km from Heathrow at
  72.4 dB when it is 6.5 km at 57.6 dB - overstated by **14.8 dB** - and
  Westminster was given 48.2 dB where DEFRA publishes no contour at all.
- **Values now come from the DEFRA Round 4 (2022) Lden raster**, sampled at each
  location, with real great-circle distances. Westminster reads "below 55,
  unmapped", because that is what the source says. The heading states these are
  annual averages and not live readings.
- **The traffic and weather rows are labelled ILLUSTRATIVE** and the fake live
  dot is gone. Those numbers are animated to look like a feed - Flights Today
  jitters on a sine wave, Peak Movements calls `Math.random()`, METAR Age ticks
  up as a counter. Simulated data is fine in a demo; simulated data dressed as
  live is not.
- The flight panel's status dot is deliberately unchanged: it goes amber with
  "TRACKED FLIGHTS (SIM)" when no feed is connected, which is the honest pattern
  the noise block lacked.
- **No critical or high findings remain on any web surface.**


### 2026-08-03 - dead code, gate coverage, and honest contact details

- **Removed a dead `DEFRA_WMS` block and two CSP grants it was the only reason
  for.** The block was declared and never read; `environment.data.gov.uk` and
  `ukair.maps.rcdo.co.uk` appeared only there and in the policy, so the page was
  granting network access to two hosts it never called. CSP: 12 hosts to 10. The
  other three carry live layer URLs and stay.
- **`changes.html` was excluded from html-validate AND the API-URL drift check** -
  the one public page missing from both, and the one most likely to be edited
  during a vintage roll. Both gates now cover 8 of 8.
- **21 school notes named retired Ofsted grades** beneath a Progress 8 badge. The
  grades are now marked historic; the named schools stay. Not rewritten borough
  by borough, because inventing replacement prose is what produced the Ofsted
  bands in the first place.
- **Three documents cited `index.html:1118-1247` as the quiet algorithm.** Those
  lines are CSS. All three now name `calcScores()` instead.
- **Two disclosure addresses disagreed.** `SECURITY.md` gave a personal Gmail
  while `security.txt` gave `support@skyscore.co.uk`; the same file also gave the
  personal address for SAR requests while `privacy.html` and `SUBPROCESSORS.md`
  publish `support@`. All aligned.
- **The DEFRA raster quarantine stands, now for a measured reason.** The hybrid
  chain discriminates fine (12 distinct values) but scores airport-adjacent
  postcodes *quieter* - perfect 10.0s go 5.7% to 13.8% - because every DEFRA
  value is above 55 dB and the band mapping awards 55-60 dB a 7.5/10 against a
  WHO aircraft guideline of 45 dB. Unblocking it means re-deriving the 55+ bands.


### 2026-08-03 - a stale-cache bug users could hit, and keyboard access

- **Users could be served crime data days out of date.** `index.html` fetched
  `data/borough-extra.json` with `cache: 'force-cache'`, which serves any cached
  copy **without revalidating**, and the S3 object carried **no `Cache-Control`
  at all**. Between them a browser could pin the file indefinitely. Reported by a
  user seeing a London median of 91.0 against the live 87.4, and "offence
  breakdown not published" on a borough that has one. Now `no-cache`
  (revalidate), with an explicit header set in the Makefile.
- **No service-worker bump could have fixed that.** `sw.js` VERSION bumps evict
  the *service worker's* caches; this was the *browser's HTTP cache*, which
  `force-cache` had opted out of freshness checks entirely. Worth knowing before
  reaching for a VERSION bump as the remedy for stale content.
- **The ranking table and saved postcodes are now keyboard-operable.** 128 rows
  bound `click` alone, so keyboard, switch and voice users could not activate any
  of them (WCAG 2.1.1). Table rows deliberately do **not** carry
  `role="button"` - that would strip the cells from the accessibility tree and
  cost screen-reader users the borough, score and rank. Guarded by a behavioural
  e2e test, because axe cannot see a `<tr>` with a click listener and no role.
- **Two faults in the crime checker, both found by chasing the cache bug.** The
  ONS workbook carries footnote suffixes (`"City of London[note 8]"`), so exact
  name matching silently excluded the one borough `--check` exists to flag while
  reporting "in step with ONS". And the London median folded in the Metropolitan
  Police **force-level aggregate**, so every `vsLondonMedian` ratio was computed
  against a cohort containing its own summary - **12 of 96 published ratios were
  wrong**. Westminster's headline driver moves 25.2x to 25.5x.
- **`--check` now fails on drift only.** The City of London case is permanent, so
  failing on it would leave the gate red for ever, which is how a gate stops
  being read.
- **A live EPC credential was redacted** from `archive/prototype-2026-03/`, which
  is tracked and public. **It remains in git history**; removing it needs a
  rewrite and is the author's call.


### 2026-08-03 - API flight paths trimmed; quiet rises across a third of London

- **The API was scoring noisier than the consumer site for the same postcode, and
  had been for three months.** The 2026-05-07 corridor trim, audited against the
  DEFRA Lden raster, reached `index.html` and `scripts/audit_flight_paths.py` but
  never the score Lambda. `/v1/score` kept **85 waypoints across 12 corridors**
  against the site's **50 across 10**, including two whole corridors the audit
  had removed.
- **Measured, not estimated:** across 7,239 live London postcodes, site and API
  disagreed on `quiet` for **2,503 (34.6%)**, with the API noisier in **100%** of
  the disagreements. Correcting it raises `quiet` by **1.0 to 4.0** for that
  34.6% and lowers it nowhere, because surplus geometry can only add noise.
- **No methodology version bump.** No weight, threshold or formula changed; only
  the geometry the existing formula reads.
- **Guarded so it cannot recur.** Two tests now compare the Lambda against
  `index.html` directly, verified to fail by restoring a trimmed corridor. Until
  now nothing could have caught it: the pytest suites only read the Lambda,
  Playwright only reads the site, and each half was internally consistent.
- **Heliports are now the only remaining site/API difference**, documented in
  METHODOLOGY §4.5.
- **Native bundle fixed at source.** `mobile/scripts/copy-web.mjs` filtered
  `data/` by `.png`, silently excluding `borough-extra.json` and both boundary
  files, so the shipped app scored liveability at a flat default for every
  borough. Now an explicit allow-list that **fails the build** when a required
  file is absent. The shipped binary still needs a rebuild and resubmission.
- **Website:** the search pin now visibly moves between nearby areas instead of
  the map re-centring on every search; a failed borough-data load is disclosed
  rather than silently scoring defaults; the neighbourhood ranking applies the
  heliport term the postcode panel already did; and 184 em dashes were removed
  from the deployed pages, with a preflight gate to keep them out.

### 2026-08-03 — DEFRA raster quarantined; quiet scores corrected downward

- **The loaded noise raster was wrong, and had been serving production since
  ~26 July.** `london-flight-map-noise-raster` stores **58.2 dB Lden for TW6 1AP,
  a postcode inside Heathrow Airport**, where DEFRA Round 4 contours exceed
  75 dB near the runways. It also stores an identical, exactly round **35** for
  postcodes as far apart as E1 8BL and N4 1AA — a background fill, not a
  measurement. DEFRA maps only down to the 55 dB reporting threshold, so
  *absence of data* had been written as though it meant *quiet*.
- **Quiet had collapsed to two values across all of London.** Through the
  documented band mapping (`<55 → 10.0`, `<60 → 7.5`) those two inputs are the
  only outputs the table can yield. The component carried almost no signal and
  erred **optimistic** — the one direction a noise product cannot be wrong in.
  Responses could contradict themselves, reporting `noiseImpactBand: "severe"`
  beside `quiet: 10.0`.
- **It also explained a site/API divergence.** The consumer site has always
  computed Haversine client-side, so it published different numbers from the API
  for the same postcode: SW1A 1AA scored **7.1 via the API and 5.2 on the site**,
  with `afford`, `growth` and `live` matching to the decimal. The site was right.
- **Quiet now resolves on the Haversine tier**, already documented in
  METHODOLOGY §4.5. Scores fall where the raster inflated them: Heathrow
  **7.5 → 0.0**, Hounslow **7.5 → 1.0**, Finsbury Park 10.0 → 6.0. This is the
  correction, not a regression. `quietResolution` no longer returns `'raster'`.
- **No methodology version bump.** No weight, threshold or formula changed and
  both tiers were already documented; only which tier answers has changed.
- **Guarded by a test that was verified to fail**, asserting a postcode inside
  Heathrow scores ≤ 3.0 against the table's real stored value. The assertion is
  absolute rather than comparative on purpose: "Heathrow beats Finsbury Park"
  passes on the broken data (7.5 vs 10.0), which is why this survived a week.
- **Corrected 2026-08-03 (same day, second pass): there is no loader bug.** This
  entry originally called the table invalid and named a CRS mismatch as the likely
  cause. The raster is genuine, the projection is correct, and the stored values
  reproduce exactly when sampled. The defect is **coverage** — 89.5% of London
  falls outside DEFRA's aircraft contours, and filling those with 35 dB rendered
  *not measured* as *perfectly quiet*, putting 98% of the city on one value. The
  loader now skips uncovered postcodes; the quarantine remains because the stored
  rows still hold the old fill and because §4.1's bands score a genuine 58.2 dB
  reading at Heathrow as quiet 7.5.
- **Notice:** the API has no paying customers as at this date, so this ships with
  this changelog entry as the record.

### 2026-08-02 — Schools re-sourced to Progress 8; three crime rates corrected

- **Methodology v3.5: the schools input is now DfE Key Stage 4 Progress 8.**
  The previous input was a four-value vocabulary (`outstanding`/`excellent`/`good`/`mixed`
  → 10/9/6/3) documented as "anchored to the Ofsted distribution". It was not:
  checked against the Ofsted management-information release (30 June 2026, 21,957
  schools), **no threshold on "% Good or Outstanding" reproduces the stored bands** —
  `excellent` spanned 90.9–100% and `good` spanned 83.3–100%, so **Westminster at 100%
  was banded `good` while Richmond at 100% was banded `excellent`**. The bands were
  editorial. The measure behind them had also been withdrawn: Ofsted abolished
  single-word overall-effectiveness grades in **September 2024**, only ~44% of schools
  still carry one, and that remainder is shrinking *and* non-random. Schools now scores
  continuously as `clamp(5.0 + 5.0 × p8, 0, 10)`, whose anchors are external constants
  (0.0 = national average, ±1.0 = a full grade per subject against pupils with the same
  KS2 baseline) rather than cohort extremes. Being intake-adjusted also stops school
  quality re-importing the affluence already priced into `afford`.
- **London goes from 2 distinct schools sub-scores to 25.** Wandsworth's headline moves
  6.7 → 6.4 (P8 +0.33 against a London median of +0.30); Camden 7.8 → 7.1.
- **Three London crime rates were compressed to fit the formula, not drawn from source.**
  **Westminster held 175 against an actual 355.5**, Kensington and Chelsea 95 against
  145.8, Camden 130 against 173.3 — all three understated, so all three scores fall.
  Corrected against ONS *Crime in England and Wales: Police Force Area data tables*,
  year ending March 2026, Table C4. **[Corrected 2026-08-03: this entry claimed the
  other 29 boroughs already agreed within 10 per 1,000. Generalised from three spot
  checks, and false — 29 of 33 disagreed with the cited release, seven by more than
  10 per 1,000. All were corrected on 2026-08-03; see that entry.]** The 50/15 band is unchanged: on true figures it clamps once in 43.
- **Vintage warning.** Progress 8 **cannot be calculated for 2024/25 or 2025/26** — those
  cohorts sat KS2 in the cancelled 2020 and 2021 windows — and DfE announced in April
  2024 that there is no replacement. **2022/23 is the terminal vintage until 2026/27.**
- **Defaulted components can no longer read as measurements.** Responses now carry
  `context.liveResolution` (`measured` / `partial` / `unavailable`), plus
  `comparisonUnavailable` where no prior vintage exists. City of London is the only
  London borough with no Progress 8 figure and falls back to the legacy band.
- **Notice:** the API has no paying customers as at this date, so this ships with this
  changelog entry as the record.

### 2026-07-31 — Growth rescaled to a dual anchor

- **Methodology v3.4: a flat market now scores 5.0, and both tails are legible.**
  The v3.2 formula scaled every borough against the fastest riser and clamped at
  0, so all fourteen falling London boroughs collapsed onto a single value —
  Ealing at −0.3% scored exactly what the City of London scored at −28.2%, and
  the API published a caveat conceding that growth "cannot tell a slight dip
  apart from a steep fall". Growth now anchors 0% trend at **5.0**, scales risers
  across 5–10 against the fastest riser and fallers across 5–0 against the
  steepest faller, each tail to its own extreme so that London's −28.2%…+5.0%
  spread does not compress every rising borough into the top sixth of the scale.
  The cohort goes from **17 to 28 distinct growth values**, and only the steepest
  faller now sits on the floor.
- **Fixed a live sub-zero score in the neighbourhood view.** `index.html` carried
  a third, separate growth formula that was neither clamped nor guarded against a
  falsy zero: a City of London postcode computed **−56.4** on a 0–10 scale, and a
  legitimate trend of `0` was silently replaced with an invented +3%. On the
  `investor` persona — the only one weighting growth, at 0.40 — that dragged the
  headline total more than 22 points negative. All three implementations (API,
  borough view, neighbourhood view) now share one formula, verified identical
  across all 38 boroughs.
- **No persona except `investor` sees a headline change.** v3.3 had already set
  growth to 0.00 everywhere else, so the component is published but unweighted;
  `investor` totals move materially. NYC moves more than London because its whole
  cohort is rising and now scores against the absolute 5.0 anchor rather than its
  own fastest riser (Manhattan 3.6 → 6.8).
- **Explanations rewritten to match.** `why.workings` and the prose steps now
  describe the anchor and name the steepest-fall benchmark instead of asserting a
  floor. The retired caveat is gone, and a regression test asserts that mild and
  severe falls stay distinguishable so the v3.2 collapse cannot return.

### 2026-07-30 — Growth reweighted, explanations rewritten, third-party assets vendored

- **Methodology v3.3: growth is weighted for the `investor` persona only.** In
  the Q1→Q2 refresh growth accounted for **87% of all score movement** across the
  33 boroughs; excluding it, the largest change anywhere in London was 0.62
  points, while nothing physical about any borough had changed. Quiet,
  affordability and liveability describe durable attributes of a place; price
  growth is a mean-reverting market series that METHODOLOGY §4.3 already stated
  does not predict future returns. Each persona's former growth weight was
  redistributed across its remaining three factors in proportion, so relative
  emphasis is unchanged and all eight still sum to 1.0. Wandsworth moves 5.3 →
  6.7 under balanced weights, purely because a floored growth component had been
  dragging it down for a reason that says nothing about Wandsworth.
- **Movement is reported even where it is not counted.** A zero-weight factor is
  no longer listed as a driver contributing +0.00, but `why.unweighted[]` reports
  it and `/changes` renders a "Moved, but not counted here" block — otherwise
  "the market clearly moved, why didn't my score?" goes unanswered.
- **`/v1/changes` and `?compare=previous` now explain *why* a score moved.**
  `attribution[]` decomposes the change exactly (score is a weighted sum, so
  `Δscore = Σ wᵢ·Δcomponentᵢ`), `why.drivers[]` carries plain-English steps and
  the actual workings with the benchmark named, and `marketContext` gives the
  city-wide picture. `weights` is published so a caller can reproduce every
  contribution; `attributionSum`/`roundingResidual` state the rounding gap rather
  than hiding it. No model generates any of it.
- **`/changes` is dated throughout.** Column headers read "Score Q1 2026" and
  "Score Q2 2026" instead of "then"/"now", set from the API vintages so they
  cannot drift, plus a dated heading and tab title.
- **A 19.2 MB third-party download no longer gates first paint.** `init()` awaited
  borough boundaries fetched from `raw.githubusercontent.com` — all 380 GB local
  authority districts, ~347 of them discarded in the browser — before revealing
  the app, and the listed fallback URL had been returning 404. Now a 123 KB
  same-origin trim (`scripts/build_london_boroughs.py`), precached by the service
  worker. d3 is self-hosted too (byte-identical to the CDN copy, verified against
  the SRI hash already pinned in the markup) and `d3js.org` is out of the CSP.
- **Brentwood, Essex was being drawn as a London borough** — the old filter used a
  bare substring test, and the borough key `Brent` is a prefix of `Brentwood`. It
  was also feeding the map projection an outlier ~30 km north-east.
- **Searches now have deadlines and stop lying about failures.** The
  AbortController only ever fired when a newer search superseded an older one, so
  a single search on a stalled network waited on the browser default; and every
  failure rendered "NOT FOUND — area or borough not found", telling users a valid
  postcode did not exist. Now 5s/8s timeouts and a "CONNECTION ISSUE" state with
  a working retry.
- **`tests/test_persona_parity.py` added.** `index.html` scores client-side from
  its own copy of PERSONAS and nothing linked it to the Lambda's, so the site
  could silently disagree with its own API about a score.
- **NYC borough boundaries vendored too — the same fix, one city late.** London
  was moved same-origin above, but switching the map to New York still issued a
  **2.67 MB** cross-origin fetch to `raw.githubusercontent.com` at the moment of
  the click, precached by nothing, failing into a bare `console.warn` that left
  the outlines silently absent. Now a 238 KB same-origin build
  (`scripts/build_nyc_boroughs.mjs`), precached by the service worker, with the
  remote kept only as a mid-deploy fallback and a spoken message when both fail.
  Unlike London there were no surplus features to drop — the source is already
  the five boroughs — so the 83% cut comes from Douglas-Peucker simplification at
  ~6 m, which stays under half a pixel at the map's maximum zoom (worst
  bounding-box shift measured at 4.0 m against ~11 m per pixel).
- **`tests/smoke-local.mjs` asserted "no `raw.githubusercontent.com`" while only
  ever loading London.** The NYC fetch above survived a wave because nothing
  exercised the city switch. The smoke test now clicks through to New York and
  re-checks the same properties there, and `tests/failure-path.mjs` covers an
  offline city switch. Noted in that file: Chromium's offline emulation does not
  apply to loopback, so the offline assertion is only meaningful against a remote
  base — the precache assertion is what goes red locally.

### 2026-07-27 — Bulk export was missing its OGL attribution

- **The bulk scoring CSV shipped with no attribution at all.** It is a derived
  work — every row carries an ONS NSPL centroid and a DEFRA-derived quiet score
  — so OGL v3.0 attribution survives into it, and handing a customer a bare
  file would put **them** in breach as well as us.

  `scripts/load_nspl.py`'s own docstring had warned about exactly this: *"The
  attribution obligation SURVIVES INTO ANY DERIVED EXPORT. The Enterprise
  'score your whole city' CSV is such an export."* The warning predated the
  exporter and was not consulted when it was built.

- **Now attributed in two places, deliberately.** A `sources` column on every
  row — the copy that cannot be separated when a customer emails the CSV on its
  own — plus a companion `<output>.sources.txt` carrying the full notices, the
  OGL link, and the ONS/OS/Royal Mail copyright.

- **Both generated from the API's own `build_sources()`**, so the export and
  the live `sources` array cannot drift; and the companion file is written
  **after** the run, because `build_sources()` only credits ONS once the local
  NSPL tier has genuinely served a lookup. A file claiming ONS provenance for a
  run that had fallen back to postcodes.io would be a false claim in a
  customer-facing document.

- **5 tests** (`TestAttribution`) pin it, including that *unscored* rows carry
  attribution too — a customer filtering to failures must not end up with an
  unattributed file. Root suite 167 → **172**. `LICENSING.md` gains a "Derived
  exports" section and a row in the attribution-surfacing table.

### 2026-07-27 — Accessibility: scan the whole funnel, not just the homepage

**Deployed and verified live** (user-authorised): the deployed HTML carries each
fix, **8/8 axe scans pass against production**, and the full preflight is green
including e2e.

- **`cloudfront:GetInvalidation` + `ListInvalidations` added to
  `backend/iam-policy.json`** (still to be applied). Found during this deploy:
  `flightmap-dev` can *create* an invalidation but not read its status, so
  `aws cloudfront wait invalidation-completed` fails and a deploy cannot
  self-verify. Every other CloudFront resource already had a `Get` beside its
  `Create`; invalidations were the lone exception.

- **A regression only a screenshot caught.** The first Swagger fix used a bare
  `#swagger-ui small`, which also matched the `<small>` used for tag-section
  descriptions — painting a dark bar over the "Score" header and hiding its
  text. **axe reported zero violations**, because a dark bar on a dark bar has
  excellent contrast. Contrast tooling scores the legibility of what is there,
  not whether the layout survived.

- **The axe scan covered `/` and nothing else.** That page had already had
  three a11y waves run over it, so the suite reported a clean sweep while the
  B2B funnel — the pages shown to investors and pilot prospects — had **never
  been scanned**. Now covers all **8** public pages. `/pricing`, `/privacy`,
  `/api/`, `/changes` and `/` were already clean; the three `score-demo`
  pages were not.

- **Threshold raised from `critical`-only to `critical` + `serious`.** Every
  defect below is `serious` — under the old threshold, scanning those pages
  would *still* have passed them.

- **`status.html` had no global `a` rule at all**, so both footer links fell
  through to the browser default `#0000ee` on a `#06070d` background —
  **2.14:1** against a 4.5:1 requirement. Effectively invisible, live since
  the page shipped.

- **Links distinguished by colour alone** on all three pages (1.49:1 where
  3:1 is required), underlined only on `:hover` — no use to touch or keyboard
  users. Underline is now permanent.

- **Swagger UI's server `<select>` had no accessible name** — axe rates this
  **critical**; a screen reader announced it only as "combo box". Also fixed:
  method badges (white on pastel, ~2:1), the version badge, and description
  links (`#4990e2` on white, 3.1:1). All fixed from the page's own `<style>`
  and an `onComplete` hook rather than by editing the vendored bundle, so a
  Swagger upgrade cannot silently revert them. Badge **fills** were darkened
  rather than text recoloured, preserving the blue-GET / green-POST coding.

- **`nested-interactive` left failing and excluded by name, on that page
  only.** Swagger renders each operation summary as a `<button>` containing a
  `<button>` — an upstream defect; patching the bundle would be overwritten on
  upgrade. Scoping the exclusion to one rule on one page keeps every other
  rule enforced there. Re-check on the next Swagger upgrade.

- Verified 0 critical/serious on all three pages against a local server,
  since the suite's `baseURL` is live CloudFront.

### 2026-07-27 — `/preflight` stops lying

The gate lied in **both directions in a single session**, which is how a
2.5-month outage hides behind a green suite. Rewritten as a real, runnable
script with real exit codes: `scripts/preflight.sh`, wired to `make preflight`,
`npm run preflight` and the `/preflight` skill so all three run the same checks.

- **False green.** `make preflight` reported success while running *nothing*:
  `make` is not on PATH in Git Bash here, and every check in the old skill was
  piped to `tail` — a pipeline exits with the status of its **last** stage, so
  no failure could ever surface. Nothing in the new script pipes a check whose
  exit code matters, and it is verified to exit 1 on an injected defect.

- **False red.** Playwright reported 14 failures that were all spurious; it
  runs against the *live* CloudFront site and the uncapped worker pool produced
  timeouts indistinguishable from assertion failures. Pinned to `--workers=2`
  (measured: 14 failed / 2 passed at default, 16 passed at 2).

- **A silent gap: the root test suite was never in the gate.** Only
  `backend/tests` ran, so all **167** root tests — the NSPL loader, the bulk
  scorer, the handler contracts — were unguarded before every commit to date.
  Now blocking. ruff coverage likewise widened from `backend/lambdas` to
  `scripts/` and `tests/`, which fixed 6 pre-existing findings.

- **A no-op reading as a green tick.** The `pip-audit` step looped over
  `backend/lambdas/*/requirements.txt`, which matches nothing (no Lambda has
  one), and swallowed the result with `|| true`. Removed.

- **Prettier is now advisory, and says so.** Every HTML/JS file in the repo
  deviates; bringing `index.html` into line is a **19,205-line diff on an
  8,462-line deployed file**. That is a decision to review, not a pre-commit
  chore — and a permanently red gate is an ignored gate.

- **The API-URL drift check is a real file**, `scripts/check_api_url_drift.sh`,
  rather than a fenced block in a markdown document that only ever ran inside a
  model's head.

- **`SECURITY.md` corrected.** It claimed "`npm audit` clean (0 vulnerabilities,
  verified 2026-05-07)"; the dev tree now carries 4 high-severity advisories.
  The accurate statement is stronger: `dependencies` is **empty** and the site
  has no build step, so nothing from `node_modules` ships, and
  `npm audit --omit=dev` reports **0**. The 4 highs are lint tooling on
  developer machines only.

### 2026-07-27 (later) — Offline city-scale bulk scorer

- **`scripts/score_bulk.py` is new** — the Enterprise "score your whole book /
  whole city" deliverable and the pilot demo artefact, unblocked by the NSPL
  table finishing its load on 2026-07-26. Takes a CSV or postcode list, emits a
  scored CSV. `make score-book IN=book.csv OUT=scored.csv`.

- **Zero methodology drift by construction.** It does not reimplement scoring:
  it imports the score Lambda and calls **`resolve_query()`**, the exact
  function the live API calls one layer below HTTP. Every threshold, weight,
  persona, borough alias, NYC ZIP mapping and terminated-postcode rule is
  therefore shared with production structurally rather than by discipline —
  reimplementing would have reopened the class of problem audit I4 closed.

- **Why offline rather than an endpoint:** `/v1/score/batch` caps at 100
  queries inside a 28s Lambda timeout, so a 100,000-address book is 1,000 calls
  — the entire monthly free-tier quota. Offline the same work costs ~£0.02 of
  DynamoDB reads and no quota at all.

- **Every input row appears in the output** (decision, Bill, 2026-07-27), with
  a machine-readable `status` and a plain-English `note` for anything unscored.
  A silently short CSV looks complete and is not — the same failure shape as
  the `UnprocessedItems` trap, but worse here because the reader is a customer
  who cannot distinguish a deliberate exclusion from a bug.

- **The `not_found` note suggests a retired postcode; it never asserts one.**
  A 404 for a terminated postcode is byte-identical to one that never existed
  (deliberate public API surface, audit L5), so the cause is not observable
  from the response. The note points at `--include-terminated` instead.

- **Customer columns are carried through**, so the output reconciles row-for-row
  against their input rather than needing a join on postcode — which is lossy
  exactly where property books are densest, since a block of flats shares one
  postcode. A column colliding with ours is renamed `src_*` so it can never
  overwrite a computed value.

- **Import order is load-bearing and handled.** `score/app.py` reads
  `POSTCODE_TABLE` / `NOISE_RASTER_TABLE` at *module* level, so the script sets
  them before importing. Getting this wrong routes an entire run through
  postcodes.io — the free community service the NSPL table exists to stop
  depending on — while still appearing to work.

- **22 tests** (`tests/test_score_bulk.py`), all offline, covering the customer
  contract rather than the scoring: every row survives, one exploding row does
  not kill a 100k run, passthrough cannot overwrite computed columns, Excel BOM
  headers still parse. Root suite 145 → **167**.

- **Measured the same day, on a 5,484-postcode book spanning all 33 boroughs**
  (28-core machine, **100% score rate**): 86.7 rows/s at 4 workers, 371.1 at 16,
  **500.2 at 32**, and **360.6 at 64** — throughput *peaks at 32 and falls at 64*,
  the same client-CPU bound (TLS + SigV4) the NSPL loader hit. Default raised
  16 → 32. `--workers` is not a speed knob above that.

- **That settles the `BatchGetItem` follow-up: not worth building.** It had been
  earmarked as the same ~25× win it was for the loader. Reads turn out to be far
  cheaper than the loader's writes — a 100,000-address book extrapolates to ~3–4
  minutes — so there is no user-visible problem left to solve, and it would cost
  a second interpretation of NSPL rows outside `_lookup_postcode_local`. Measuring
  beat reasoning by analogy. (The 100k figure is an extrapolation; the largest
  real run to date is 5,484 rows.)

### 2026-07-27 — NSPL loader moved to BatchWriteItem; batch-metering decision documented

- **`scripts/load_nspl.py` now writes with `BatchWriteItem`** (25 items per
  signed request) instead of one `PutItem` per row. The measured 5.80-hour full
  load was client-CPU-bound on 2.7M separate TLS handshakes and SigV4
  signatures, not throttled by DynamoDB; this removes ~96% of those round trips.
  The per-item design only ever existed because the IAM action was not granted.

  **The next full load is unmeasured.** Expect well under an hour, but no figure
  is quoted here until a real run produces one — this docstring was already
  wrong by 10× once, in the optimistic direction, for exactly this reason.

- **The `UnprocessedItems` retry loop is load-bearing, not defensive.**
  `BatchWriteItem` reports partial failure as an HTTP **200 with a non-empty
  `UnprocessedItems` map**, never as an exception, so boto3's adaptive retry
  cannot observe it. Dropping that map would lose rows while `run_load` still
  credited them to `written` and checkpointed past them — unrecoverable, since a
  resume starts *after* rows that never landed. Same class of silent shortfall
  as the checkpoint-ahead-of-writes bug fixed on 2026-07-25. Exhausting the
  retries is therefore deliberately fatal rather than quiet.

- **Degrades automatically when the grant is missing.** On `AccessDeniedException`
  the loader latches back to the per-item path and completes at the old speed, so
  it is safe to run either side of the IAM change. **A roll that still takes ~6
  hours is the signal the grant never landed.** A `ValidationException` (most
  plausibly a duplicate postcode inside one 25-item window, which fails the whole
  request where `PutItem` would simply overwrite) falls back for that chunk only,
  without latching.

- **5 new tests** in `tests/test_load_nspl.py::TestBatchWritePath`, all covering
  ways the swap could lose rows *while still reporting success*. Root suite
  140 → **145**; backend **125** (+8 subtests). The `_FakeDdb` double now models
  `batch_write_item`, partial success, and both fallback exceptions.

- **`backend/iam-policy.json`** gains `dynamodb:BatchWriteItem` and a new
  `CloudWatchLogsOperateOwnGroups` statement (`DescribeLogStreams`,
  `FilterLogEvents`, `GetLogEvents`, `PutRetentionPolicy`, `DeleteLogGroup`)
  scoped to `/aws/lambda/london-flight-map-*`. Between them these would make
  `/aws-debug` function and retire the console-only retention remediation.
  **The file is not the live policy — it still has to be applied.**

- **`BATCH_METERING_DECISION.md` added.** Documents the open decision blocking
  the Professional launch, read from source rather than memory: quota 1,000/month
  × `MAX_BATCH_SIZE` 100 = **100,000 free scores/month**. Newly noted: the quota
  is monthly but the throttle is per second, so a single free key drains the
  whole allowance in **~8.5 minutes** — a burst, not a drip, and the billing
  alarm is not positioned to catch it. Five options, with the recommendation that
  the blocker is not building metering but deciding what the free tier may be
  worth. **Decision still open; nothing implemented.**

### 2026-07-26 (later) — Frontend batch deployed; DynamoDB tables made unloseable

- **Frontend batch is live.** `index.html`, `sw.js`, `js/api-base.js` and
  `score-demo/index.html` had all drifted from S3 — the 2026-07-25 commit was
  committed but never deployed, so the search-flow race (one postcode's EPC and
  sold-price data rendered under a *different* postcode's heading, a terminal
  state that never self-corrects) was live on skyscore.co.uk the whole time.
  Deployed with a 9-path CloudFront invalidation. Post-deploy gates: live web
  serves the CLASSIC layout at 360/390/414 with zero horizontal overflow
  (web/native split intact), live `index.html`/`sw.js` hash byte-identical to
  local, all 8 surfaces 200 with correct content-types, live API suite 5/5.
- **Ordering note for the `api.skyscore.co.uk` switchover.** The `sw.js`
  cache-first fix is now live, but service workers only update on navigation,
  so installed PWAs adopt it on their next visit. `js/api-base.js` still points
  at the raw execute-api URL, which keeps working regardless. Correct sequence:
  **sw.js live (done) → set the Cloudflare CNAME → only then repoint
  `api-base.js`.** Repointing early is what strands installed PWAs.
- **`DeletionPolicy: Retain` + `UpdateReplacePolicy: Retain` on all four
  DynamoDB tables.** This closes two interacting risks at once. `flightmap-dev`
  has no `dynamodb:DeleteTable` grant, so any rollback needing to delete a
  table would be *denied*, wedging the stack in `UPDATE_ROLLBACK_FAILED` with
  no self-recovery path; and the data itself was unprotected. `Retain` means
  CFN never attempts the delete, so the missing grant can never bite and the
  rows survive either way. Applied deliberately **before** the NSPL loader's
  first run — 2.7M rows is hours of loading to rebuild. All four tables updated
  in place, no replacement, no data disturbed (signups 1, favourites 14,
  noise-raster 423,481 all intact).
- **EPC auth-failure handling fixed and deployed.** `lambdas/epc/app.py` now
  treats `403` — what MHCLG actually returns for a rejected bearer token,
  verified against the live service with a control request — the same as `401`,
  so a token expiry degrades to `available: false` and quietly hides the EPC
  panel instead of falling through to a generic `502` that breaks the whole
  property page. `401` is retained alongside it; the upstream contract is not
  ours to assume. The rejection is now also logged at ERROR with rotation
  instructions: the graceful body is indistinguishable from "no data" to a
  caller, and a silently-degrading auth failure is exactly how the signup
  funnel stayed dead for two and a half months. Response shape deliberately
  unchanged — the user-facing contract stays graceful, only the operator
  signal is new. Three tests added (`401`/`403` both degrade, `500` still
  surfaces as `502` so the branch can't swallow unrelated failures, `404`
  still means "no certificates"); 125 backend tests green. Verified live
  post-deploy: `N1 7SX` returns 76 certificates with a summary, `SW1A1AA`
  returns `available: true, count: 0`.
- **NSPL load COMPLETE** — the local postcode tier is live. Self-test green
  (BOM, 36-column header, 33-borough map, spaced-postcode invariant, sentinel
  rule), dry-run item shape verified, 5,000-row smoke test wrote 4,999
  (1 unpositioned, correctly skipped), then the full run:

  | | |
  |---|---|
  | Written | **2,699,393** postcodes |
  | Skipped | 24,203 (unpositioned / no geography / Channel Islands + IoM) |
  | Terminated (tagged `dt`) | 904,453 |
  | London (tagged `b`) | **332,308** |
  | Spaced-form mismatches | **0** |
  | Wall-clock | **5.80 hours** at ~129 rows/s |
  | Vintage | **2026-02** (see the roll note below) |

  `__META__` provenance item written: vintage, row counts, OGL v3.0 source and
  load policy, so the table self-documents which edition it holds.
- **Load verified by spot-check, not by `ItemCount`** (which refreshes only
  every ~6 hours and read 0 throughout). Ten `get-item` probes all correct,
  including the two boundary cases the loader itself nominates: `SW11 1AA` →
  Wandsworth, `E1 6AN` → **City of London** (the borough-boundary check),
  `BR1 1HB` → Bromley with `dt=198412, q=8` as predicted. Controls confirm
  non-London rows carry **no** `b` attribute (`M1 1AA` → Manchester LAD only,
  `EH1 1YZ` → Edinburgh), which is what keeps the existing "borough not
  supported" 404 byte-identical.
- **Vintage debt, tracked:** this is the **February 2026** NSPL edition, loaded
  on 26 July — verified from the data (`max(dointr) = 202601`), not from the
  hardcoded `NSPL_VINTAGE` constant. May 2026 already existed and August is due
  within weeks. Harmless by design: post-Feb postcodes simply miss and fall
  back to postcodes.io, so the tier is degraded-but-never-wrong. **Roll to the
  August edition when it ships**, and grant `dynamodb:BatchWriteItem` first —
  that is the ~25× speedup, not more workers.

### 2026-07-26 — Backend deployed; signup funnel actually fixed (second IAM fault)

- **`POST /v1/signup` returns 201 again**, verified live. The funnel had been
  503'ing for every visitor since 2026-05-07. The 2026-07-25 statement split was
  correct but incomplete — there were **two stacked IAM faults**, and it fixed
  only the second one. The first: API Gateway treats tags as a **separate
  resource path** (`/tags/{arn}`; TagResource is `PUT /tags/{arn}`), so
  `create_api_key(tags={...})` requires a grant on
  `arn:aws:apigateway:*::/tags/*` that the audit I-G hardening never added.
  Denial therefore happened at `CreateApiKey`, before any key existed.
- **`backend/template.yaml`**: `SignupFunctionRole` gains `apigateway:PUT` +
  `apigateway:POST` on `arn:aws:apigateway:${AWS::Region}::/tags/*`, **keeping**
  the `aws:RequestTag/CreatedBy` condition — dropping it would let the Lambda
  tag any API Gateway resource in the account, a wider hole than I-G closed.
- **Deployed**: NSPL `PostcodeTable` created (ACTIVE, empty — the loader can run
  at any time, the score Lambda is forward-compatible); stage throttles applied
  (`/epc` GET 3/6 new, `/v1/score/batch` 5/10 → 10/20, `/v1/score` GET 40/80 now
  declared in source rather than surviving as console drift); CORS and the
  2026-07-24/25 fix waves are live. No resource replacements.
- **Known issue found here, fixed later the same day** (see the entry above):
  `lambdas/epc/app.py` branched on HTTP `401` to return the graceful "token
  invalid or expired" body, but MHCLG returns **`403`** for a rejected bearer
  token. That branch was unreachable.

### 2026-07-25 — Test coverage for the local ONS NSPL postcode-resolution tier

- **`backend/tests/test_score.py` gained `PostcodeTableTests`** (19 tests) over
  the new local tier: the forward-compatibility guarantee (with
  `POSTCODE_TABLE` unset, no boto3 client is even constructed), the
  postcodes.io-shaped return contract, the DDB key format matching what
  `scripts/load_nspl.py` writes, deferral on every failure path (miss, unusable
  centroid, `ClientError`, terminated-without-opt-in), the non-London
  `admin_district = None` case and its byte-identical 404, the
  `?includeTerminated=true` response keys, the unchanged six-key `location`
  shape on live postcodes, and the two cache-leak guards (neither negative nor
  terminated results may be cached).
- **`tests/test_load_nspl.py` is new** (21 tests) over the loader's pure
  `_row_to_item` and its borough map — including the assertion that
  `LONDON_LAD_TO_BOROUGH`'s 33 names are byte-identical to the score Lambda's
  `LONDON_BOROUGHS` keys and each survives `normalise_borough` unchanged. A
  single typo there would 404 an entire borough with no postcodes.io rescue,
  because a local hit never falls back.
- **Loader fix found by those tests**: `_row_to_item` coerced coordinates under
  `except (KeyError, ValueError)`, but `csv.DictReader` yields `None` for a
  short row's trailing fields and `float(None)` raises `TypeError` — which
  would have escaped the row loop (deliberately bare-`except`-free per audit
  I-F) and killed a 40-minute run. Now `(KeyError, TypeError, ValueError)`,
  matching the Lambda's mirror-image guard.
- All fixtures are real rows from the on-disk ONS NSPL 2026-02 edition. No
  network, no AWS, no moto, no new dependencies. **199 tests green**
  (108 root + 91 backend), up from 159.

### 2026-07-24 (night) — Trends feature SHIPPED: ?compare=previous + /v1/changes + /changes page

- **`?compare=previous` on `/v1/score`**: any location rescored against the
  previous quarterly vintage under the current formula — `previousScore`,
  `scoreChange`, price movement. Works per-postcode (raster path included);
  NYC honestly reports zero change. In the `include` filter set.
- **`GET /v1/changes`** (public, keyless): all 33 boroughs'
  quarter-over-quarter movement, sorted by magnitude, with summary. This
  vintage: 6 risers, 25 fallers, 18 moved >0.5; largest fall Barking and
  Dagenham (9.0 → 7.4).
- **`/changes` page** ("What changed this quarter") renders it live, honesty
  note included; linked from both site footers. OpenAPI documents both.
  Deployed end-to-end and verified live.
- **Load harness** (`tests/loadtest.mjs`) gained per-request CSV persistence
  (`CSVFILE`) — demonstrated with a 1,736-request clean capture, every
  request a row (timestamp, status, latency). Gotcha for future runs: a
  freshly-created API key can 403 for ~20s while APIGW propagates — probe
  until 200 before starting a capture.

### 2026-07-24 (later) — Backend deployed · Methodology v3.2 (quarterly refresh + growth clamp) · 100k soak

- **Backend deployed** (user-directed): the CORS critical fix, 28s batch
  timeout, 50-rps stage throttle, and backend fix wave are LIVE. Verified:
  `Access-Control-Allow-Origin: *` from the skyscore.co.uk origin — the
  consumer data panels work again after ~2 months silently broken.
- **Methodology v3.2**: quarterly refresh check (per the published policy)
  found 28/33 boroughs ≥3% adrift from the 2026-Q1 snapshot; all 33
  borough prices/trends refreshed to May 2026 UK HPI in both engines. The
  refresh exposed an unclamped growth formula (negative trends → sub-zero
  scores); v3.2 clamps growth to 0–10. 18 borough scores move >0.5
  (balanced weights); no paying customers, changelog is the notice record.
  Public surfaces (footer, api sample, OpenAPI examples) bumped to 3.2.
- **100k-request production soak** run against the newly-raised limits with
  a temporary key (results in the stress-test workbook + AUDIT_REPORT).

### 2026-07-24 — Legacy test rewrite + full audit (1 live critical) + pilot outreach pack

- **Root `tests/` rewritten** to current handler contracts after 21 tests went
  stale against the May migrations: epc (MHCLG JSON API + `EPC_BEARER_TOKEN`),
  favourites (`X-Device-Token` auth — the old suite asserted the removed
  IDOR-era `userId` contract), nhs (OSM Overpass). 83 root + 62 backend tests
  green at the time; **CI now gates both suites** (`ci.yml`). (Current split:
  108 root + 91 backend = 199 — see the NSPL entry above.)
- **Audit items I4, I6, I14 closed** — I4 resolved by removal, I6 moot (no
  async Lambdas), I14 via a full `PROJECT_DOCUMENTATION.md` refresh (7-Lambda
  truth, real `/v1/*` endpoint table, 3-table DynamoDB schema, historical
  markers on the removed AI features).
- **Full audit** (6 dimensions, adversarially verified) → `AUDIT_REPORT.md`
  §2026-07-24. Headline: **A-0724-C1 (critical, verified live)** —
  `CORS_ORIGIN` pinned to the legacy CloudFront URL silently broke all five
  consumer data panels on skyscore.co.uk. **Source-fixed in `template.yaml`;
  deploys with the pending EPC-token `sam deploy`.** Plus 34 confirmed
  findings and 25 unverified leads (verification cut short by the account's
  monthly spend limit).
- **Outreach**: pilot-first email variants added to `OUTREACH_DRAFTS.md`;
  LOI template + one-pager maintained off-repo (Desktop) — the Haatch
  commercial-proof pack is complete.
- **Production load test (~63k requests, temp key, cleaned up):** single-score
  p50 56ms / p99 83ms at sustained load; **confirmed I4 live** (cold instances
  lose whole 100-query batches to the 10s timeout under concurrency — the 28s
  source fix is validated and waiting on deploy); **new finding A-0724-I12** —
  the stage-wide 10 rps throttle capped every key at ~5-6 req/s regardless of
  usage plan; raised to 50/100 in source (rides the same deploy). LRU race
  (M10) did not reproduce.
- **Pricing page:** pilot card now says the premium over 3× Professional buys
  the evidence (metric design, day-45/90 reviews, founder support), not the
  API calls. Deployed.
- **Same-day fix wave — 18 audit findings closed** (evening): sw.js cache
  poisoning + VERSION bump, status.html quota discipline (5-min
  visibility-aware checks), score-demo NYC currency render, in-sheet mobile
  footer (funnel/legal links finally reachable ≤900px on web), result
  announcements + persona `aria-pressed` + two contrast fixes, privacy.html
  strict CSP, dead CSP hosts removed. Backend (source-only, rides the pending
  `sam deploy`): transport honesty on TfL outages + 400 on bad input, epc
  timeout/JSON handling, batch timeout headroom, weight bounds. 152 tests
  green; e2e 16/16; layout harness clean on web/native/desktop.

### 2026-05-29 — Web/native split + iOS 1.0.21 submitted for review

- **Web/native split** (`3945226`): the mobile bottom-nav redesign is now
  native-app only, gated behind an `is-native` class on `<html>` (added by
  `setupNativeFeatures()` only inside Capacitor). The website (desktop + mobile
  browser + PWA) reverted to the classic bottom-sheet layout; the iOS/Android
  apps keep the redesign. Deployed to CloudFront + verified. See
  `MOBILE_REDESIGN_PLAN.md` v3.
- **Store copy** (`4af9bc5`): iOS "What's New" + Android changelog reworded from
  the v1 four-tab nav (Search/Map/Rankings/Saved) to the v2 three-tab,
  map-as-background design (Search/Rankings/Saved).
- **iOS `1.0.21` (build 21)** submitted for App Store review (2026-05-29) —
  native redesign, iPhone-only, built via Codemagic from `4af9bc5`. Screenshots
  at 1242×2688. Waiting for Review.

### Wave 13.1 → 13.5 — 2026-05-09 (mobile UX + PWA + native iOS/Android pipeline)

Five-part wave that takes Sky Score from "web-only" to "PWA + native iOS + native Android pipeline". 46 files / ~8,700 lines added across five focused commits.

- **13.1 — Mobile UX overhaul + PWA install** (`d7ac20d`): bottom-sheet sidebar replaces the 55/45 vertical split on phones (auto-opens on result; peek state shows search), Legend chip + Layers hamburger above the sheet (matched dark-pill styling), score chips gain non-colour signals (▲/●/▼ glyph + "Strong/Mixed/Weak" word + aria-label, WCAG 1.4.1), footer 8px → 11px on phones, subtitle hidden ≤480px, heliport labels (ELS/DEN/etc.) hidden ≤600px, empty-state quick-search chips. PWA wired up: `manifest.webmanifest` (light theme, scope `/`), two SVG icons (regular + maskable), Apple touch icon + iOS meta tags, `sw.js` (network-first shell, cache-first static, network-only API, stale-while-revalidate fonts), custom Install chip + iOS Add-to-Home-Screen hint, CSP `worker-src` and `manifest-src` directives, `tests/pwa-check.mjs` Playwright smoke test.
- **13.2 — Capacitor wrapper + Codemagic config** (`d2e2cad`): `mobile/` directory with isolated `package.json`, `capacitor.config.ts` (app id `uk.co.skyscore.app`), `scripts/copy-web.mjs` assembles `mobile/www/` from parent web app, 5 plugins bundled (app, geolocation, share, splash-screen, status-bar). Geolocation as the App Store Section 4.2 "Minimum Functionality" defence — "Score where I am" button. `codemagic.yaml` with two workflows (mac_mini_m2 for iOS, linux_x2 for Android) auto-publishing to TestFlight + Play Console internal track.
- **13.3 — Native-launch prep** (`a081090`): `mobile/STORE_LISTINGS.md` (paste-ready App Store + Play Store copy including descriptions, keywords, age rating, Data Safety form answers), `mobile/APPLE_REVIEW_NOTES.md` (Section 4.2 review-notes copy + escalation script if Apple rejects), `mobile/PRIVACY_POLICY.md` (GDPR-compliant draft for hosting at `/privacy`). Asset pipeline scaffolded: SVG sources in `mobile/assets/` + `@capacitor/assets` integration. README + CLAUDE.md updated to document the mobile workflow; SUBPROCESSORS.md adds api.postcodes.io, Codemagic, Apple App Store, Google Play as sub-processors #4-7.
- **13.4 — Asset pipeline verified + release checklist + privacy.html + launch blog draft** (`3a45e1c`): renamed `icon-source.svg` → `logo.svg` to match `@capacitor/assets` v3 conventions; cleaned XML comments (no `--` inside `<!-- -->` blocks). Verified 136 Android variants + 7 PWA icons generated from 5 SVG sources. Removed obsolete Playwright SVG→PNG step (capacitor-assets accepts SVG directly). `mobile/RELEASE_CHECKLIST.md` (9-step pre-release runbook), `mobile/LAUNCH_BLOG_POST.md` (announcement post draft + social excerpts + press hooks), `privacy.html` (live page for `/privacy` URL referenced in store listings). `codemagic.yaml` adds `build:assets` step. ROADMAP.md flips "native iOS/Android distribution" from open to in-flight.
- **13.5 — Deep-link stubs + outreach artefacts** (`d0bfcef`): `.well-known/apple-app-site-association` (iOS Universal Links manifest, TEAMID placeholder), `.well-known/assetlinks.json` (Android App Links, SHA-256 placeholder). `mobile/DEEP_LINKING.md` setup guide (where to find Team ID, how to extract keystore fingerprint, validation tools). OUTREACH_LOG.md gains the privacy URL + TBD entries for the iOS/Android apps.
- **13.7 — Android off Codemagic** (post-merge correction): user clarified that Noor's Android binary was built locally via Android Studio, not via Codemagic — only iOS went through Codemagic. Mirroring that pattern: dropped `android-workflow` from `codemagic.yaml` (iOS-only now), added `mobile/ANDROID_BUILD.md` documenting the Android Studio + gradle local build process, updated `CODEMAGIC_SETUP.md` and `RELEASE_CHECKLIST.md` to reflect the dual-path build (iOS cloud, Android local). Saves cloud-Linux build minutes; faster Android feedback loop on Windows. The Capacitor-generated `mobile/android/` project itself is unchanged — only the CI strategy differs.
- **13.8 — CLI release pipeline (Makefile + fastlane)**: three-layer CLI ergonomics on top of the deploy/build commands. Layer 1: `Makefile` at repo root with one-word targets for every common op (`make help` lists them all). Layer 2: `package.json` npm-script aliases for the most common ops (work without GNU Make installed). Layer 3: `mobile/fastlane/` with Fastfile (5 Android lanes + 3 iOS lanes), Appfile, Gemfile (pins fastlane ~> 2.222), and ready-to-paste store listing metadata for both stores in `metadata/{android,ios}/en-GB/`. Bug fix in `mobile/.gitignore`: anchored `ios/` and `android/` patterns with leading `/` so `mobile/fastlane/metadata/{android,ios}/` weren't accidentally ignored.
- **13.8.1 — fastlane verified working** (post-merge): user successfully installed Ruby 3.3 + bundler + fastlane via `bundle install` on Windows. `bundle exec fastlane lanes` outputs all 8 lanes cleanly. UTF-8 locale env vars (`LANG`, `LC_ALL`) set permanently to suppress fastlane's locale warning; rocket emoji renders correctly which confirms UTF-8 round-trip is working. `mobile/Gemfile.lock` committed (Bundler convention for application-level repos — locks gem versions across machines + Codemagic cloud builds for reproducible installs).
- **13.8.2 — fastlane env vars documented in `.env.example`** (`c3c506e`): names match what `Fastfile` reads: `PLAY_CONSOLE_JSON_KEY`, `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_KEY_FILE_PATH`, optional `ANDROID_AAB_PATH`. Comments point at the exact console pages where each secret is generated, and recommend storing `.p8` / JSON files outside the repo (`~/.secrets/`) so a stray `git add -f` can't leak them.
- **13.8.3 — fix iOS metadata_path + protect README** (`0a26ca3`): two bugs caught on the first iOS lane run. (1) iOS `deliver` expects metadata at `fastlane/metadata/<locale>/` not `fastlane/metadata/ios/<locale>/` — fixed by passing `metadata_path: './fastlane/metadata/ios'` explicitly on every iOS lane (and matching `screenshots_path`). Android `supply` and iOS `deliver` disagree on the platform-subdirectory convention. (2) fastlane silently overwrites `mobile/fastlane/README.md` with its auto-generated lane listing after every run — fixed by setting `FASTLANE_SKIP_DOCS=1` in `.env` and documenting in `.env.example`.
- **13.8.4 — first successful metadata push** (`e3c7780`): confirmed end-to-end metadata push works after the 13.8.3 fixes plus three further small adjustments. (1) Added `precheck_include_in_app_purchases: false` because precheck's IAP scan requires interactive Apple ID login (not API key) — irrelevant for Sky Score (no IAP). (2) Added `mobile/fastlane/metadata/ios/copyright.txt` ("© 2026 Bilal Khizar") — app-level metadata, not locale-scoped. (3) Deployed `privacy.html` to S3 as `privacy/index.html` (extensionless URL pattern, due to the `sky-score-rewrite-index` CloudFront Function that appends `/index.html` to clean URLs) — was missing since Wave 13.4 despite the file existing in the repo. Both fastlane precheck warnings now pass.
- **13.8.5 — App Review Notes auto-pushed via fastlane**: moved the Section 4.2 review-notes copy from `mobile/APPLE_REVIEW_NOTES.md` (manual paste) into `mobile/fastlane/metadata/ios/review_information/notes.txt` (auto-pushed by every `metadata_only` or `submit_for_review` run). `APPLE_REVIEW_NOTES.md` retained as runbook documentation (rejection counter-arguments, "what NOT to include") but flagged as no longer the canonical source. `mobile/RELEASE_CHECKLIST.md` step 8 updated to reflect the auto-push.
- **13.8.6 — Apple Team ID resolved + AASA deployed for Universal Links** (`096c262`): retrieved Apple Team ID (`L3UXT79KFZ`) via Spaceship API (`BundleId#seed_id`) — automatable, not the manual developer.apple.com → Membership Details lookup the docs suggest. Updated `.well-known/apple-app-site-association` to use the real Team ID, deployed to S3 with `Content-Type: application/json`, invalidated CloudFront. Live at `https://skyscore.co.uk/.well-known/apple-app-site-association`. iOS Universal Links infrastructure now active — once Sky Score is installed via TestFlight, tapping any `skyscore.co.uk/*` link on iPhone routes to the app. Android assetlinks.json half still pending the release keystore SHA-256 (waits for first Android Studio build).
- **13.8.7 → 13.8.12 — Codemagic iOS signing arc** (6 commits, 1 working binary): wrestling Codemagic's Personal Account signing model into submission for Sky Score. The story:
  - **13.8.7** (`0a26ca3`): added explicit `keychain initialize` + `app-store-connect fetch-signing-files --create` steps so `xcode-project use-profiles` can find profiles on disk. Build failed.
  - **13.8.8** (`1b2ba87`): removed `integrations.app_store_connect: codemagic_asc` since Personal Accounts don't have named integrations. Yaml validation immediately failed because `publishing.auth: integration` requires the block.
  - **13.8.9** (`5d66ba0`): restored `integrations:` but pointed at the actual key label `"Sky Score Fastlane"` instead of the placeholder `codemagic_asc`. Build still failed identically.
  - **13.8.10** (`d618eff`): switched `publishing` block from `auth: integration` to explicit env vars (`api_key: $APP_STORE_CONNECT_PRIVATE_KEY` etc.) — bypasses the integration name lookup entirely. Build still failed (env vars existed in dashboard but yaml didn't import the group).
  - **13.8.11** (`00a74ab`): single-line fix — added `environment.groups: [asc]` so the workflow imports the dashboard env vars. Build still failed identically because Codemagic's pre-flight signing check runs BEFORE scripts and uses the Apple Developer Portal pool's auto-selected key (Noor's, alphabetically first), not the env vars.
  - **13.8.12** (`69e14e8`): removed the `environment.ios_signing` block entirely to disable pre-flight signing. Signing now happens exclusively in scripts (`keychain initialize` → `app-store-connect fetch-signing-files` with env-var credentials → `keychain add-certificates`). **Build progressed past the signing wall for the first time** — through 8 stages, ~30 seconds in. Confirmed env vars correctly populated by the build log printing `APP_STORE_CONNECT_*` values from the imported `asc` group.
- **13.8.13 — Node version syntax fix** (`755b73e`): build past pre-flight failed at `> n 20.x` with "Unable to install Node version 20.x". Codemagic's `n` version manager rejects `.x` wildcards — must be bare major (`20`) or fully-specified version (`20.10.0`). One-line yaml fix.
- **13.8.14 — Pass `--certificate-key-path` to fetch-signing-files** (`9f597b0`): next-stage failure was "Cannot save Signing Certificates without certificate private key" — Codemagic CLI needs a private key path to either match an existing Distribution cert OR create a new one. Generate fresh RSA-2048 key on the build VM, pass via `--certificate-key-path` to both `fetch-signing-files --create` and `keychain add-certificates`. Caveat: creates a new cert per build, eating Apple's 2-cert team limit. Future: persist key as Codemagic env var for cert reuse.

**Why split from earlier waves**: native binaries have a different release cadence (TestFlight + Play review cycles, ~2–3 days vs minutes for CloudFront). Keeping them in a sibling `mobile/` directory means web deploys stay unaffected and we can iterate on either independently. The web app, the PWA, and both native apps run from the **same `index.html`** — feature-detected via `window.Capacitor.isNativePlatform()` for native-only UI.

**Still required (user-side, not committable)**: ASC API key + Bundle ID registration (done 2026-05-10), App Store Connect "Sky Score" app record creation (done 2026-05-10), real Apple Team ID + keystore fingerprint to replace the `.well-known/` placeholders, first iOS Codemagic build trigger, first iOS screenshots manually uploaded to ASC, first iOS submit_for_review, first Android Studio local build + Play Console listing.

### Wave 12.10 — 2026-05-08 (persona rename: `downsizer` → `laterlife`)

**Breaking API change.** The `persona` enum value `downsizer` is removed; the equivalent persona is now `laterlife` with identical weights (quiet 0.40 / afford 0.15 / growth 0.10 / live 0.35). User-facing label changes from "Downsizer" to "Later life".

**Why:** the term "downsizer" reads as faintly diminishing of older buyers when the persona is really about prioritising quiet and healthcare access, not about reducing one's life. "Later life" is the framing used in BBC/healthcare/policy contexts and matches the persona's actual function.

**Customer impact:** zero paying B2B customers at time of change, so the breaking shape is acceptable without a `/v2` path bump. Anyone passing `?persona=downsizer` will now receive a normal "invalid persona" 400 response. The free-tier demo key holders (one active, ~75 calls historical) will not have hit this code path.

**Files touched:** `backend/lambdas/score/app.py` (key + comment), `backend/tests/test_score.py` (fixture + new regression test asserting `downsizer` is gone), `index.html` (persona definition + label), `score-demo/index.html` (dropdown + label map), `score-demo/openapi.yaml` (enum), `METHODOLOGY.md` (persona table — also expanded from 5 to the actual 8 entries; the table had drifted away from `app.py` in an earlier wave), `PROJECT_DOCUMENTATION.md` (persona list).

### Wave 12.8 + 12.9 — 2026-05-08 (I-N5 closure: API URL drift defence + extraction)

Two-half close on the long-running I-N5 audit item (API base URL duplicated across files).

- **12.8 (defensive half):** added step 4d to `/preflight` — greps every HTML/JS/test file for `execute-api` hosts and fails the build if more than one distinct host appears. Catches drift at commit time before it ships, regardless of why the URLs diverged (manual edit, partial deploy, stale clone).
- **12.9 (offensive half):** extracted the URL to `js/api-base.js` — a 1-line classic script that sets `window.API_BASE`. The 3 browser pages (`index.html`, `score-demo/index.html`, `score-demo/status.html`) now load it via `<script src>` and pull the value from `window.API_BASE`. The 4 hardcoded constants collapsed to 2 (one in the shared script, one in `tests/api.test.mjs` which can't read `window`); the test duplicate stays guarded by the 12.8 drift check. Deploy commands in `CLAUDE.md` updated; `js/api-base.js` joins the S3 frontend bundle.

Net: rotating the API host now requires editing 2 files instead of 4, and the drift check is a hard guarantee they stay aligned. The prior "keep in sync with X, Y, Z" comments are now redundant and were trimmed.

### Wave 12.6 + 12.7 closure — 2026-05-07 late night (analytics gap + funnel events + UTM convention)

- **12.6:** added missing GoatCounter tracker to `score-demo/index.html` (the API browser demo). CSP allowlist had it, but the script tag was never added — the most B2B-relevant page wasn't being counted.
- **12.7:** wired 8 funnel events (`api-demo-run/error`, `signup-attempted/issued`, `api-{methodology,licensing,demo,spec}-click`) for B2B conversion measurement. UTM convention documented in `OUTREACH_DRAFTS.md` — per-target slug table for cold-email attribution.

### Wave 12.5 closure — 2026-05-07 late night (borough label contrast)

User flagged that clicking a borough made its name unreadable (label and fill both #141414). Switched borough labels to dark fill + white stroke halo via `paint-order: stroke` so they read on any background — same trick used for airport/heliport codes earlier.

### Wave 12.4 closure — 2026-05-07 late night (in-map layer captions removed, legend group titles beefed up)

User flagged the in-map SVG captions (DEFRA ROAD NOISE BY BOROUGH etc.) overlapped the LONDON/NYC city-selector buttons in the top-left. Removed them entirely (the bottom-left HTML legend already handles attribution per toggled layer) and bumped the legend group titles from 8px mid-grey to 10px bold dark with source prefixes (DEFRA ROAD NOISE / EA FLOOD RISK / BOROUGH AIR QUALITY for London; DOT / FEMA / EPA equivalents for NYC).

### Wave 12.1 + 12.2 + 12.3 closure — 2026-05-07 late night (self-host DEFRA PNG + widen bbox + explainer + legend layout fix)

**Wave 12.3:** added a one-line `max-width: 260px` to `.map-legend` because the in-place explainer text from 12.2 had stretched the legend container across the bottom of the desktop map. Mobile already hides the legend < 768 px.



User reported the contours render with a lag, cut off at edges, and asked whether the visual is real data. All three addressed:

**Wave 12.1 — Self-host the DEFRA WMS PNG.** Measured DEFRA's GeoServer at 8.9 s to render the request. Cached the PNG to `/data/aircraft-noise-london-lden.png`, served from CloudFront edge (86 ms cached, ~100× faster). Added `<link rel="preload" as="image">` so the fetch starts during HTML parse. New `scripts/refresh_aircraft_noise.sh` for the next DEFRA publication round (~2027).

**Wave 12.2 — Widen bbox + in-place explainer.** Bbox now -0.85..0.40 lon, 51.10..51.78 lat — covers the full LHR butterfly contour, LCY approach, and LGW (was missing). Stansted + Luton still excluded (don't reach inhabited Greater London). New PNG at 4096×2228 (~21 m/px). Legend now reads "DEFRA Strategic Noise Map (Round 4, 2022 data), the long-term average aircraft noise around LHR, LCY and LGW — modelled from a year of actual flight tracks, not a live feed."

### Wave 12 closure — 2026-05-07 late evening (DEFRA visibility recovery + a11y + I-N5 + SEO)

**DEFRA visibility recovery:** user reported "I don't see aircraft noise anymore" after the Wave 10 single-fetch refactor. Three combined fixes:
- Raster source 2048 → 4096 px (~12.5 m/px ground resolution)
- Opacity 0.6 → 1.0 (PNG alpha already handles translucency)
- CSS `filter: saturate(1.6) brightness(0.92)` + `mix-blend-mode: multiply`

**Audit residual closures:**
- F-UX-8: `aria-live` status region announces autocomplete suggestion count to SR users
- F-UX-9: Esc dismisses the score-explain tooltip; mobile gets max-width to prevent overflow
- I-N5: API_BASE consolidated within each file; `/preflight` grep-checks for drift
- M-E: status-page CSP intentionally omits Goatcounter (no analytics on uptime page) — documented as won't-fix-by-design

**SEO basics:**
- `/robots.txt`: general crawlers allowed; AI training crawlers (GPTBot, anthropic-ai, ClaudeBot, CCBot) restricted from /data/ + /api/
- `/sitemap.xml`: 6 URLs covering consumer site, /api, score-demo, prototype
- `/api/` JSON-LD: Schema.org SoftwareApplication for Google Rich Results + LLM-driven discovery

### Wave 11 closure — 2026-05-07 late evening (CloudFront security headers + F-Perf-10)

**HSTS + 4 other security headers now live** on `https://skyscore.co.uk` via AWS-managed CloudFront `SecurityHeadersPolicy`. Verified by curl:
```
Strict-Transport-Security: max-age=31536000
X-Frame-Options: SAMEORIGIN
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
X-XSS-Protection: 1; mode=block
```
M-B closed at 1-year HSTS. Permissions-Policy + 2-year preload-eligible HSTS still need a custom CloudFront policy (root-account perms).

**F-Perf-10:** `BOROUGH_EXTRA` (503 lines, London) + `NYC_BOROUGH_EXTRA` (85 lines) extracted from `index.html` to `/data/borough-extra.json`. Lazy-fetched in parallel with geojson load; sidebar rescore on hydration.

- index.html: 7,178 → 6,593 lines, 309 KB → 275 KB (-11%)
- JSON: 28.7 KB, served with 24-hour browser cache
- Initial paint no longer waits for borough-metadata parse; LCP improvement scales with parser-blocked time on slower devices.

### Wave 10 closure — 2026-05-07 late evening (DEFRA fix + a11y + reduced motion + ops docs)

User flagged the DEFRA noise overlay looked "all over the place" — root cause was per-pan WMS re-fetch causing the contour bands to "swim" as each new viewport rendered slightly differently. Fixed by pre-fetching once at a fixed Greater-London bbox (2048 px) and positioning the raster in g-coordinates so D3's zoom transform scales it natively.

Also closed:
- **F-A11y-4 (real bug):** tab panels had `aria-labelledby` self-referencing their own ids — gave each tab button `id="tab-btn-X"` and pointed panels at the buttons.
- **F-UX-11:** `prefers-reduced-motion: reduce` global guard added to all 5 HTML pages.
- **OPERATIONS.md §3.2 + §3.3:** documented HSTS/Permissions-Policy CloudFront setup + CSP report-uri runbook (M-B, M-C, I-A — moved from deferred to one-time admin tasks).

### Wave 7+8+9 closure — 2026-05-07 late evening

Three more focused waves shipped after the main session-close:

**Wave 7 (visual polish, commit `0d634b1`):**
- Per-layer indicator dot colours on `.layer-toggle.active` (matches the layer's actual map colour — paths/aircraft/road/transport/flood/AQ/labels)
- DEFRA caption stagger so road/flood/AQ labels don't overlap when multiple borough overlays toggled together
- Airport-code text gets a white halo via `paint-order: stroke`

**Wave 8 (code quality, commit `f91935d`):**
- `BOROUGH_ALIASES` expanded from 4 to ~25 entries — covers Royal Borough / London Borough / ampersand / common spelling variants postcodes.io and partner address data return
- New end-to-end signup race-recovery test — proves the orphan key is revoked and the secret value is not echoed back to the loser of the race

**Wave 9 (enterprise no-legal items, this commit):**
- `OPERATIONS.md` runbook (production topology, deploys, one-time admin actions, DR, monitoring, debugging, cost profile)
- `SUBPROCESSORS.md` register (3 sub-processors: AWS, Cloudflare, GoatCounter — explicit "tools we don't use" list for procurement)
- `SUPPORT.md` (contact channels, response targets, planned `support@` + `status.skyscore.co.uk`)
- DynamoDB PITR enabled in `template.yaml` for all 3 tables (signups, noise-raster, favourites). **Deploy gated** on one-time IAM policy update at root account — see OPERATIONS.md §3.1.
- `pip-audit` integrated into `/preflight` skill — PyPI Advisory Database vuln scan per Lambda's `requirements.txt`; CVSS ≥ 7.0 blocks commit

### Planned (deferred from 2026-05-07 session)

- See [`AUDIT_REPORT.md`](./AUDIT_REPORT.md#deferred--kept-in-mind-for-future-sessions) for the full deferred list with audit IDs, priorities, and time estimates. Top items:
  - Layer-toggle hover vs active visual differentiation (a11y critical)
  - Heading hierarchy fix in injected sidebar HTML (a11y critical)
  - Touch targets <44px on consumer site (`.layer-toggle` 32px; `.persona-btn` ~25px; `.fav-btn` ~22px)
  - Skip-to-content link
  - CSP `report-uri` endpoint + `img-src` tightening
  - Per-route throttle on `/v1/score` to prevent one tenant starving others
  - hCaptcha on `/v1/signup`
  - HSTS + `Permissions-Policy` via CloudFront response-headers policy
  - DPA + MSA templates (CommonPaper) — needs legal review
  - Privacy notice + sub-processor list + retention policy (`/privacy`, `SUBPROCESSORS.md`, `OPERATIONS.md`)
  - DynamoDB PITR + documented RTO/RPO
  - Status page on `status.skyscore.co.uk` subdomain
  - `pip-audit` integration into `/preflight`
  - Extract inline `BOROUGH_DATA` / `AREA_MAP` from index.html (6.9k lines) to JSON for LCP improvement
  - DEFRA Lden raster data load completion (in flight 2026-05-07; loader at NSPL row ~2.3M of ~2.5M)

### Original [Unreleased] planned items

### Planned
- DEFRA Lden raster data load completion (in flight 2026-05-07; loader at NSPL row ~2.1M of ~2.5M)
- Independent measured-noise validation (gating contractual accuracy claims)
- Per-postcode flood risk component (`flood`)
- Per-postcode air quality component (`airQuality`)
- LSOA-level crime breakdown (`crimeBreakdown`)
- Per-customer API keys + Usage Plans (replaces shared free-tier key)
- Optional `/api` landing page (B2B discovery surface, defer until outreach signals warrant)
- Public methodology change-history page
- ISO 27001 / SOC 2 attestation tracks
- MSA + DPA template (use CommonPaper.com or PandaDoc UK template; do not draft from scratch)
- First commercial contract with a paying integrator
- Pricing tier structure firmed up post first prospect conversation
- Live aircraft feature re-introduction once OpenSky licensing reply lands (Ticket #835285) or an alternative provider (AviationStack / FlightAware) is selected

## [Consumer rebrand + security + audit-driven hardening] 2026-05-07

The longest-running session in the project's history. Two parts:
1. **Morning/afternoon (32 commits, 3 backend deploys, 5 frontend deploys):** removed all AI features from the consumer site, removed OpenSky-backed live-aircraft pending licensing, hardened the signup endpoint, fixed DOM-XSS surfaces, trimmed flight-path polylines to noise-relevant portions, refreshed every relevant doc.
2. **Evening (13 further commits, 4 more backend deploys, 6 more frontend deploys):** ran two rounds of 3-5 parallel audit agents (code, security, frontend visual + a11y, enterprise readiness), closed the highest-leverage agent findings, deployed CSP enforcing on all 5 HTML pages, added `/.well-known/security.txt`, `SECURITY.md` security one-pager, `/api` landing page, `OUTREACH_DRAFTS.md`, `AVIATIONSTACK_SPIKE.md`, `AWS_BILLING_ALARM_SETUP.md`. Then deleted the 5 dormant Bedrock Lambda directories entirely + their IAM grants.

Total: ~45 commits, 7 backend deploys, 11 frontend deploys.

### Added
- **XSS hardening sweep** across the consumer site (commit `2405122`). New `safeUrl()` allow-list for href values from community data; `formatChatReply` (since removed) escapes before markdown to break the OSM → chat injection chain; every API-derived `innerHTML` interpolation in NHS / TfL / sold-prices / autocomplete / borough-postcode renderers wrapped in `escapeHtml`. Closes audit N-Sec-1, N-Sec-2, N-Sec-3.
- **Self-service signup hardening** (commit `a214ba0`). Tag-based IAM scope-down on `apigateway:DELETE` so the signup Lambda can only delete keys it created (closes N-Code-1); per-route APIGW throttle of 1 RPS / 5 burst on `/v1/signup` (closes N-Code-2); CORS lockdown from `*` to a `skyscore.co.uk` allow-list (closes N-Sec-4 partial); orphan-key revoke failures now logged at ERROR level with a `[SIGNUP_ORPHAN_KEY]` prefix for CloudWatch alarming (closes N-Code-7).
- **Tab a11y** (commit `847935c`). Tabs converted from `<div role="tab">` to native `<button>` with Left/Right/Home/End arrow-key navigation and roving tabindex per WAI-ARIA tabs pattern.
- **Prototype mobile touch-target sizing** (commit `2e77bda`). Mobile touch-bar buttons now `min-height: 44px` per WCAG 2.5.8 (was ~22-30 px on smallest breakpoint).
- **SEO + meta tags** on `score-demo/{index,api-docs,status}.html` and `prototype/index.html` (commit `bc4d426`). Canonical, theme-color, OG / Twitter cards, robots. Status page is `noindex`.
- **`live_flights` tuple-return refactor + 9 unit tests** (commit `5418d73`, *later removed*). Replaced function-attribute state pattern with explicit `(payload, error)` tuple; race-safe under concurrent Lambda invocations.
- **Per-secret `AllowedPattern '^.+$'`** in `template.yaml` (commit `aaf192f`). Deploys with empty / missing tokens now fail CloudFormation parameter validation instead of silently propagating empty strings to the Lambda env.
- **DEFRA WCS downloader** (`scripts/download_defra_wcs.py`, commit `7c3ce04`) bypasses the data.gov.uk UI 250 km² area threshold and pulls the full London bbox raster directly from the WCS endpoint.
- **DEFRA loader v2** with below-threshold sentinel (commit `2fc2c0b`). Postcodes inside the bbox but outside the published 40 dB Lden contour now write a 35 dB sentinel rather than falling through to Haversine — fixes suburban Twickenham / Wimbledon / Hampstead being mis-scored as loud. Plus checkpoint-on-every-1000-rows fix for resumability.
- **Flight-paths audit script** (`scripts/audit_flight_paths.py`, commit `d9f33b9`). Samples each `FLIGHT_PATHS` polyline at 50 evenly-spaced points and looks up Lden in the DEFRA GeoTIFF; flags paths that don't track real noise. Output: `FLIGHT_PATHS_AUDIT.md`.
- **Per-route Bedrock throttle** plan documented (made moot by AI removal — see below).

### Changed
- **AI-powered → data-first repositioning** (commit `455af60`). README, ROADMAP, CLAUDE.md updated. The 5 Bedrock Lambdas (`chat`, `multi_agent`, `analyze_image`, `analyze_document`, `report`) reframed as "dormant in the template, kept for potential re-introduction as user-triggered constrained features".
- **`FLIGHT_PATHS` polylines trimmed** to noise-relevant final-approach / initial-departure portions only (commit `abbae36`). Previously extended 30-45 km out to holding fixes at FL120+ where DEFRA shows zero ground noise — visualisation now matches what's actually audible. Per-path mean Lden up across the board (Lambourne 38→43, Biggin 39→45, Dep SE 43→52). Score Lambda's Haversine fallback now also more accurate for outer-London postcodes.
- **DOM XSS chat-reply chain blocked** at the renderer layer — `formatChatReply` now escapes before applying markdown so a successful prompt-injection bypass can't render `<img onerror>` and steal the device token. (Function later removed entirely with the chat panel.)
- **Tab interaction** moves Tab in/out of the tablist in one keystroke instead of cycling through every tab (roving tabindex pattern).
- **Demo regression fixes** (commit `a2b5695`). `score-demo/index.html` persona dropdown caught up with the `192ce18` persona expansion (renter / commuter / downsizer); four `", "` placeholder strings on `score-demo/status.html` and `prototype/index.html` (left over from the dash-strip script) replaced with `Loading…` / `Checking…`.
- **Signup `print()` → `logger`** (commit `a214ba0`) — restores structured-log search across CloudWatch.
- **`live_flights` upstream errors surfaced to UI** (commit `12617e2`, *later moot*). Frontend showed "LIVE AIRCRAFT, DATA UNAVAILABLE" when the proxy returned `available: false`, instead of silently rendering nothing.

### Removed
- **All AI features from the consumer UI** (commit `69905ee`). Chat panel, AI insight auto-summary on postcode views, multi-agent routing, property-photo image analysis, EPC / survey document upload + AI analysis, "Generate AI Report" button. The 5 Bedrock Lambdas remain dormant in `template.yaml` (zero idle cost on on-demand pricing); restoring is "uncomment one frontend block + redeploy". Net `-25 KB` on served HTML, `-535 lines`. Reasoning: methodology defensibility is the B2B story, and AI summaries on top of deterministic scoring add variance B2B audit teams will challenge first; "not fully accurate" is structural not tunable.
- **`live_flights` Lambda + UI end-to-end** (commit `6f6ce7d`). OpenSky's terms require a written agreement for any operational use including consumer surfaces. Lambda code in git history (commit `a214ba0`); UI gated behind `liveLicensed=false` flag in the prototype. Restoration recipe in `LICENSING.md` "Removed sources" + `OPENSKY_LICENSING_EMAIL.md`. Email enquiry sent same day — OpenSky Ticket #835285, awaiting reply.
- **Borough metadata duplication** between chat / multi_agent / score Lambdas → reduced to score-only (the other two are dormant).
- **Pre-existing preflight noise** (commit `70405f8`): 1 ESLint error + 1 HTML-validate error → 0 errors. Aligned Prettier and html-validate void-element style; converted `<div class="site-footer">` to semantic `<footer>` so its `aria-label` is valid; ruff `--fix` cleaned 16 import-order + `datetime.UTC` modernisation issues across all backend Lambdas.

### Security
- **Closed**: N-Sec-1 (OSM DOM XSS), N-Sec-2 (chat-reply DOM XSS), N-Sec-3 (defence-in-depth XSS sweep), N-Sec-4 partial (signup CORS lockdown — full closure pending CAPTCHA), N-Code-1 (signup IAM `apigateway:DELETE` wildcard), N-Code-2 (no per-route throttle on `/v1/signup`), N-Code-5 (signup `print()` vs logger), N-Code-7 (orphan-key revoke alerting), N-Front-1 (persona drift on B2B demo), N-Front-2 (corrupted status placeholders), N-Front-5 (tab a11y), N-Front-6 (first-hint announcement), N-Front-9 (prototype touch targets), N-Front-10 (prototype ticker XSS).
- **Made moot by AI removal**: N-Sec-4 partial (per-route Bedrock throttle), N-Front-3, N-Front-4, N-Front-7, N-Front-8 (all chat/report-modal a11y items).
- **OpenSky licensing**: live aircraft removed from production pending OpenSky's reply (Ticket #835285). Email and FAQ research confirmed: no public commercial-use form exists; the documented commercial path is exactly the email we sent. Sky Score never created an OpenSky account — consciously kept hands clean before the licensing question is settled.

### Decisions
- **AI feature removal** → data-first positioning. Recovery path: re-introduce later as user-triggered constrained "explain in plain English" button (≤5% of the cost, lower hallucination risk) only when consumer feedback warrants it.
- **OpenSky → remove and ask** (option 3 of three considered: contact for licence, replace with paid alternative, or remove). Chase scheduled for 2026-06-04 (4 weeks).
- **Repo migration**: canonical clone now at `C:\Users\bilal\projects\london-flight-path-map`; legacy OneDrive clone retired pending DEFRA-loader completion. OneDrive `.git` corruption risk per global CLAUDE.md.
- **Echo-work discipline** added to global `~/.claude/CLAUDE.md`: after substantive change, propagate to README / ROADMAP / LICENSING / METHODOLOGY / AUDIT_REPORT / OUTREACH_LOG / memory / `.env.example` / tests / AWS surfaces in the same session while context is hot.
- **Demo API key exposure (audit C2)** accepted with rotation discipline rather than building a server-side proxy. Blast radius bounded by 1000 req/month quota; rotation = 5 minutes. Re-evaluate if a paying customer ever depends on the demo working specifically.
- **Dormant Bedrock Lambda directories deleted entirely (2026-05-07 evening)**: revised the prior "keep dormant" decision after the smoke-test caught the routes were still publicly invokable. "Uncomment Events block to re-enable" wasn't materially easier than "git revert + sam deploy", and 5 Lambdas with intact `bedrock:InvokeModel` grants were attack surface for any future SAM template typo. Restoration recipe: git revert this commit + the 2026-05-05 AI-removal commit (commit `69905ee`).

### Evening additions (post-CHANGELOG-write commits)

- **Two rounds of 3-5 parallel audit agents** (code, security, frontend visual + a11y, enterprise readiness). Findings merged in commits `dab713d` (post-audit security fixes), `6bad8ce` (Wave 1: code quality), `a830acb` (Wave 2: visual polish), `b6c7806` (Wave 3: SECURITY.md), `54191df` (Wave 4: a11y criticals).
- **CSP enforcing** on all 5 HTML pages (commit `967f9d1`); was Report-Only earlier in the day. Then `unsafe-eval` dropped (commit `dab713d`) — codebase has no `eval`/`new Function`, so it was free attack-surface widening.
- **`SECURITY.md` security one-pager** (commit `b6c7806`) closes enterprise gap #4 — pre-empts the SOC 2 question by listing controls actually in place + an honest "what we don't have" table.
- **`/api` landing page** at `https://skyscore.co.uk/api/` (commit `88b56a4`) closes enterprise gap #19 (B2B prospects had no buy-path discovery surface). Hero CTA → demo / reference / methodology, "Built for" target-audience cards, indicative pricing tiers, 5-step "Get started" path.
- **`OUTREACH_DRAFTS.md`** (commit `2024147`) — warm-intro DM template + Tier 1 / 2 cold-email templates with per-target tweaks for Landmark / TM Group / OneSearch Direct / Al Rayan / StrideUp / Gatehouse / Nester / Yielders. Subject-line A/B options.
- **`AVIATIONSTACK_SPIKE.md`** (commit `2024147`) — fallback live-aircraft provider reference; ~3-hour swap if OpenSky says no.
- **`AWS_BILLING_ALARM_SETUP.md`** (commit `445c59d`) — one-time admin runbook for $20 USD billing alarm; would have caught today's "AI Lambda routes left open" defect within hours.
- **6 new signup tests** (commit `2024147`): CORS allow-list (echoed origin / hostile origin / no-origin / lowercase header) + `_safe_revoke_orphan_key` prefix guard (refuses non-prefix names; deletes legitimate prefix). Backend tests 61 → 67 then back to 60 after dormant-Lambda test classes deleted.
- **Visual polish on map**: road overlay `mix-blend-mode: multiply` so it tints aircraft raster instead of covering it; legend "LCY/OTHER" → "LCY PATHS"; flight-path strokes 1/1.5px @ 0.5 → 1.5/2.25px @ 0.7; heliport colour orange → violet (was identical to LHR orange); animated dot halo for visibility over noise rasters.
- **Search input** now implements the WAI-ARIA combobox pattern (`role="combobox"`, `aria-expanded`, `aria-controls`, `aria-autocomplete`, `aria-activedescendant`); each `.autocomplete-item` is a `role="option"` with stable id + `aria-selected`; new `closeAcDropdown()` helper centralises 5 dismiss paths so screen readers stay in sync.
- **ADDITIONAL INSIGHTS metric cards** converted from `<div onclick>` to native `<button>` with `aria-expanded` / `aria-controls`; toggle handler synchronises the ARIA state.
- **Dropped 5 dormant Bedrock Lambda directories + their IAM grants** (commit `6bad8ce`). Net ~800 LOC removed from backend; 5 fewer execution roles with `bedrock:InvokeModel` permissions.
- **`live_flights` Lambda removed** earlier in the day (commit `6f6ce7d`); the `liveLicensed=false` gate in `prototype/index.html` strengthened to `throw` on flag flip with a message pointing to `OPENSKY_LICENSING_EMAIL.md` (commit `6bad8ce`).
- **Enterprise audit doc gap fix**: METHODOLOGY §15 said "AWS is the sole sub-processor" but LICENSING.md listed Cloudflare. Reconciled (commit `6bad8ce`).
- **OpenSky licensing enquiry sent** to `contact@opensky-network.org` — Ticket #835285 acknowledged via auto-reply; chase 2026-06-04.

## [3.1], 2026-05-05

### Added
- **NYC ZIP centroids**, ~110 NYC ZIPs now have static centroid lat/lon, enabling the v3.0 per-postcode Haversine layer for NYC postcodes (previously borough-aggregate only). Within-borough variation now works for NYC (e.g. 11201 DUMBO returns quiet=8.0; 11375 Forest Hills returns quiet=2.0 under JFK / LGA traffic).
- **DEFRA raster scaffold**, DynamoDB table `london-flight-map-noise-raster` deployed with IAM read access from the score Lambda. Resolution chain extended: `raster → postcode (Haversine) → borough`. New `context.quietResolution` enum value `'raster'`. Lambda is forward-compatible: empty table falls back transparently to v3.0 Haversine; populating the table silently upgrades to gold-standard precision.
- **`scripts/load_defra_raster.py`**, runbook + code template for the one-shot batch that downloads the DEFRA GeoTIFF, samples at every UK postcode centroid, and writes to DynamoDB.
- **`?include=` query parameter** on `/v1/score`, selective response shape for integrators who only want specific fields.
- **`plannedComponents` field** on `/v1/score` responses, visible roadmap of components on the development plan (`flood`, `airQuality`, `epcDistribution`, `crimeBreakdown`).
- **Public status page** at `/score-demo/status.html`, live endpoint health checks, methodology version, region, SLA reference.
- **Public `CHANGELOG.md`** at repo root (this file).

## [3.0], 2026-05-05

### Added
- **Per-postcode Haversine quiet scoring**, when the API receives a UK postcode (resolved to lat/lon via postcodes.io), the Quiet score is computed at postcode resolution using Haversine distance to airports and flight-path geometry. Same algorithm as the consumer-site neighbourhood scoring (`calcScores()` in `index.html`); ported to the Lambda.
- 5 London airports tracked (LHR, LGW, LCY, STN, LTN), 4 NYC airports (JFK, LGA, EWR, TEB).
- 12 London flight-path corridors (Lambourne / Biggin / Ockham / Bovingdon stacks; LHR departures; LCY / LGW / LTN approaches), 8 NYC corridors.
- New `context.quietResolution` field (`'postcode' | 'borough'`) reports which tier produced the response.

### Changed
- Hackney N1 7SX `quiet` updates from 10.0 (borough-aggregate "low") to 4.0 (under Lambourne Stack, the LHR east-London arrival corridor).
- Wandsworth SW11 1AA `quiet` updates from 5.0 (borough-aggregate "moderate") to 7.0 (south of major LHR corridors).
- Hounslow TW3 4DX `quiet` updates from 0.0 to 2.0 (still severe, postcode under approach corridor).

### Removed
- Borough Lden band as the default quiet source (still available as fallback when postcode lat/lon unavailable). The borough Lden remains visible in `context.noiseImpactBand` for transparency.

## [2.1], 2026-05-05

### Added
- New benchmark anchors in methodology: HM Land Registry House Price Index (Affordability + Growth), EU Environmental Noise Directive 2002/49/EC (the regulatory framework DEFRA implements for Quiet), Care Quality Commission (roadmap anchor for Healthcare in v3.0+), English Indices of Deprivation (alignment reference for Liveability).

### Changed
- Audit-protection edits across §4.4 (Schools, Crime, Healthcare), §5.2 (Personas), §11 (Editorial), §14 (Comparison): softened Ofsted distribution percentages, clarified crime-rate denominator, removed specific Climate X funding figure, softened Rightmove citation, replaced generic reference URLs with stable government collection pages.

## [2.0], 2026-05-05

### Added
- **OGL attribution** in every data-source response (epc, sold_prices, transport, nhs).
- **`/v1/score/batch`** endpoint, bulk scoring up to 100 queries per call; per-row failure tolerance.
- **`/v1/regions`** endpoint, discovery for supported cities, boroughs, postcode formats.
- **OpenAPI 3.0 spec** at `/score-demo/openapi.yaml`.
- **Interactive Swagger UI** at `/score-demo/api-docs.html`.
- **`sourceBreakdown` field** in score responses, per-component data lineage.
- **Methodology v2.0**, every numeric threshold and weight anchored to a published source or explicitly-acknowledged editorial decision.
- **NYC borough lookup** (`?city=nyc&borough=Manhattan`).
- **NYC ZIP detection** (~182 ZIPs static-mapped; auto-detect in `?postcode=`).
- **postcodes.io in-memory LRU cache** for repeat lookups within a Lambda container.
- **Per-resource CORS** open to `*` for the score endpoints.

## [1.0], 2026-05-05

### Added
- Initial **`/v1/score`** B2B API endpoint.
- **API key auth** via API Gateway Usage Plan (1,000 req/month free tier, 5/sec burst, 2/sec sustained).
- **B2B browser demo** at `/score-demo/index.html`.
- **Public methodology document** (`METHODOLOGY.md` v1.0).

## [0.9], 2026-04-XX

### Added (consumer site, pre-API)
- Sky Score consumer site (London + NYC) at `https://skyscore.co.uk/`.
- Sky Score Radar 3D prototype at `/prototype/`.
- Amazon Nova hackathon submission.
