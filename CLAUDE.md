# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## How this file works (since 2026-10-17)

This is the CORE: what every session needs, one line per rule. The stories behind the rules (the
incident, the measurement, the gate that was proven red) live **verbatim** in `docs/lessons/`, moved
there on 2026-10-17 because this file had grown to 272 KB (~68k tokens loaded before any work).
**Before working in an area, read its lesson file**; to find one, grep `docs/lessons/` for the script,
file, function or field name. Code comments that cite "CLAUDE.md" for a story now mean `docs/lessons/`.
When something new is learned: add the one-line rule here and the story to the lesson file.

| Lesson file | Read before touching |
|---|---|
| `session-and-repo.md` | clone location, planning docs, the PUSH ruling |
| `cities-and-inputs.md` | city coverage, the scored-input table (builder + `--check` per input), postcode scoring, uncovered postcodes |
| `aircraft-estimate.md` | Quiet Skies: AIP flight paths, fitted weights, near-field contour floor, per-airport ladder, validation set |
| `flood.md` | EA flood mosaics, georeferencing, `check_flood_georef.py` and its cache |
| `adding-a-city.md` | any new city (gitignore, borough-extra, generated constants, registry, switcher) |
| `map-layers-and-legends.md` | fill layers, legends, `FILL_LAYER_COLOURS`, noise-legend palettes, panel caveat |
| `neighbourhoods-and-stations.md` | PPD medians, generated neighbourhoods, NaPTAN stations, area labels, "best value" |
| `in-progress-measurements.md` | AURN monitors, Breathe London sensors, how often planes pass (adsb.lol vs CAA) |
| `public-surfaces.md` | `/badge`, area pages, free tier, route throttles, signup verification (I17), per-field provenance |
| `us-cities.md` | `/bay-area/`, Bay Area releases 1-2, the US noise yardstick, New York v5.6-v5.7 |
| `product-rules.md` | scale direction, branding, why there is no basemap |
| `quality-gates.md` | preflight stages, responsive / a11y gates, `/aws-debug` history |
| `front-page-and-site.md` | `/` vs `/map/`, street report, pricing, top bar, count.mjs, Find areas, grid refs |
| `deploy.md` | make targets, manual commands, SAM, env, token rotation |
| `architecture.md` | extension, raster tier, mobile layout, map fit, Lambdas, prototype, PWA/native |
| `aws-and-loaders.md` | resource IDs, DynamoDB tables, NSPL rolls, loader speed, detached runs |
| `methodology-history.md` | v5.0-v5.2: national affordability, growth pool, real terms, applied weights, rounding |
| `audit-history.md` | audit waves, known issues, the website audit, the current audit's must-not-undo list |
| `submissions-and-store.md` | competitions, events, Claude Startups, App Store / Play |
| `building-heights.md` | EA lidar, building heights, the Hounslow pilot (context facts, never scored) |

## Compact Instructions

When context fills up, always preserve:
- AWS deployment details (API URL, CloudFront ID, S3 bucket, region)
- The current task the user is working on
- Any file changes made during this session that haven't been committed
- Branding: always "Sky Score", never "London Flight Path Map" in user-facing text

## Session rhythm

**On conversation start** (first message, greeting, or "what can I do"), display:

```
Sky Score

Available commands:
  /project:deploy-frontend Upload to S3 + invalidate CloudFront
  /project:deploy-backend SAM build + deploy Lambdas
  /project:deploy-all Deploy everything
  /preflight Pre-commit quality checks (lint, security, a11y)
  /careful Enable production safety mode (blocks destructive AWS commands)
  /aws-debug Debug Lambda/API Gateway issues (log read restored 2026-09-04)
  /project:test-apis Test all API endpoints
  /project:review Summarise recent changes

Or just describe what you need, I have full context of this project.
```

- **Where we left off**: ROADMAP.md's newest "START HERE" block and the newest `project-start-here-*` memory.
- **Canonical clone is `%USERPROFILE%\projects\london-flight-path-map`.** Never work in the retired
  OneDrive clone; if a session lands there, move here first.
- **PUSH** (Bill's ruling, 2026-08-27, superseding an old "keep git local" line): `git fetch` early, surface
  drift, `git pull --rebase` before pushing if diverged.
- **Before the conversation ends** (goodbye / thanks / done): run `git status`; if anything is uncommitted,
  say "You have unsaved changes. Would you like me to commit them before you go?"
- **Planning docs**: `ROADMAP.md` (what next, open decisions), `EXPANSION.md` (the NATION is the unit of
  work), `OUTREACH_TARGETS.md` (**start every outreach email from it**; repo is public, so organisations
  only, never people), `CHANGELOG.md`, `HANDOVER.md`. Update the doc when a task ships or a decision lands.
- **Echo-work**: after a substantial change, propagate to README, ROADMAP, LICENSING, METHODOLOGY,
  AUDIT_REPORT, memory, `.env.example`, tests, the lesson file, and the deployed surfaces. **Bill's
  cross-project state is `%USERPROFILE%\OneDrive\Desktop\NOW.md`** (imported by the global CLAUDE.md): when
  a Sky Score item listed there closes or changes, update its line, then add one dated line to the "Daily
  Progress Log" of `90_DAY_ROADMAP.md` (strategic only; search it, never read all 278 KB).
- **Weekly audit**: the current one is `AUDIT_REPORT_2026-10-31.md`; suggest `/audit` when it is >7 days old.

## The product, in facts safe to repeat

- **Sky Score**: property noise and liveability data. The consumer site is the marketing engine; the B2B
  `/v1/score` API is the product. Pivoted May 2026 from "AI-powered" to data-first.
- **THE public coverage sentence, the only one to quote**: "97 council areas in 13 UK city regions, plus New
  York's 5 boroughs and 50 Bay Area cities (facts only)".
- **Surfaces**: `/v1/score` serves 15 cities LIVE, the 15th the Bay Area's 50 cities (live 2026-10-29), by name
  (`city=bayarea`) or by ZIP (scored as the city where half or more of its residents live); the site keeps their facts
  (`SITE_FACTS_ONLY_CITIES`, held both ways by both parity gates). The site SCORES 11 (London 33, NYC 5, Greater Manchester 10,
  West Midlands 7, West Yorkshire 5, South Yorkshire 4, Merseyside 5, Tyne and Wear 5, Bristol 4, Leicester 8,
  Teesside 5 = 91 boroughs) and shows the **Bay Area's 50 cities as facts with no score**. API-only, declared
  in `BACKEND_ONLY_CITIES`: Cardiff (cannot leave: no Progress 8 in Wales) and Nottingham (judgement). Greater
  Norwich (3) is an API-only preview. Uncovered spot-check postcode: **`EX1 1HS`** (must say NOT COVERED YET,
  no link).
- **Methodology v5.7** (`METHODOLOGY_VERSION` in `backend/lambdas/score/app.py`). Components: `quiet`
  (aircraft estimate), `afford` (national log p5-p95 per currency pool), `growth` (real-terms HPI trend vs the
  currency pool), `live` (crime, Progress 8, transport, healthcare), `env` (air 0.45 + road 0.35 + flood 0.20
  from CONTINUOUS fields; floor 2 inputs).
- **Scale direction**: scores rise = better and are labelled with the good thing (`Quiet Skies 8/10`);
  measurements rise = worse and are labelled with the bad thing (`Aircraft noise 2/10`). The site/extension
  "disagreement" is one value under two labels: do NOT harmonise it.
- **Branding**: "Sky Score" in all public text (rebrand decided; candidate names stay OUT of this public repo
  until domains are bought). "Sky Score Radar" for `prototype/`. "Cubitt33" appears on `privacy.html` and
  `terms.html` ONLY. **Cubitt33 is not VAT-registered: never write "+ VAT".**
- **Wording rules**: never call the whole product "open government data"/OGL (UK routes come from the UK AIP,
  credit "UK AIP (NATS)"); FAA routes carry the FAA's "as is, without warranty" line wherever shown; shares
  are over **postcodes, not addresses**; a DEFRA map figure is **modelled, never "measured"** (only a monitor's reading is
  measured; the front page said "DEFRA, measured" until 2026-11-03, and `tests/test_public_wording.py` now refuses it); never say **how often planes pass** except for airports that pass
  `coverage_verdict()`, and only through `js/planes.mjs` from `data/planes/` (`build_planes_overhead.py`, 2026-10-26)
  or the district pages `build_planes_pages.py` BUILDS from the same files (`/planes-overhead/`, 2026-10-28: a cell
  counts postcodes in bands, never a middle figure; since 2026-11-03 it SHOWS the busiest band and draws every band as
  one bar in the layer's colours (`BAND_COLOURS`, held equal to `build_planes_layer.COLOURS`), every count in the bar's
  label; its `--check` holds every page), or the full map's layer pictures
  `build_planes_layer.py` draws from the same files (2026-11-02: each postcode its own step, from the busiest airport
  over it, never airports added, never grouped; its
  `--check` holds every picture, its legend names steps, never a place's figure), a range on a cone's edge,
  never a figure typed into a page; prices appear on `/pricing` ONLY, and never a licence figure anywhere public (a
  `/talks/` handout broke the OGL and prices rules unseen for a month, fixed 2026-10-24). Say **AI** only as an event's
  name or where AI is NOT used; never how the product works or was built (Bill, 2026-10-24: not "AI slop").
  **`tests/test_public_wording.py` holds these on every page and PDF the Makefile uploads** (+ js/ modules), on
  what a visitor sees; a new exception goes in its allow-lists WITH its reason, never a looser pattern.

## Rules that bite

### Data and scoring
- **Derive, never copy.** Anything between generated markers (`FLIGHT-PATHS-LONDON`, `RUNWAY-AXES`,
  `<CITY>-NEIGHBOURHOODS`, `BACKEND-ONLY-PRICES`, `US-QUIET-NYC`, `US-QUIET-BAYAREA`, `AREA_SCORECARDS`, `COVERAGE-STRIP`, `HOW-IT-WORKS-*` ...)
  is rewritten by its builder; never hand-edit it. Each builder's `--check` is the gate.
- **Scoring inputs live in BOTH holders** (Lambda registry + `data/borough-extra.json` / `index.html`),
  held by `tests/test_borough_data_parity.py`. Use `build_borough_bands.py --write --write-lambda`, never
  `--sync-lambda` (it skips the API-only cities).
- **Absence must never render as a measurement**: no `|| 'moderate'`-style defaults, no `.get(x, 0)` on a
  1-100 scale, an empty index is not a zero reading, a `.get` with a default is a silent skip. Missing is
  skipped and said so.
- **A bounding box is not containment** (five incidents). Use point-in-polygon / the real boundary.
- **Key on ONS codes, never names**; postcodes.io and ONS spell places differently ("Bristol, City of",
  "St. Helens").
- **When correcting a scoring input, ask which tier answers first**: the postcode tier
  (`calc_postcode_quiet`, DEFRA rasters) takes precedence over the borough band.
- **NSPL geography columns carry a year suffix that moves** (`lad25cd` -> `lad26cd`): resolve by prefix.
- **Sample a postcode at NSPL's `east1m`/`north1m`** (`scripts/postcode_grid.py grid_ref()`), never a
  re-projection; BT postcodes are Irish Grid. Loaders UPSERT, so a re-placing needs
  `remove_lost_readings.py --apply`.
- **A data roll is done only when every reader of the file has run** (HANDOVER s0 step 7). Area pages BAKE
  scores (the `/area/` index's tables too) AND the planes overhead links (`data/planes-districts-by-council.json`,
  written by `build_planes_pages.py`): rerun `build_area_pages.py --write` after any vintage or planes roll (its
  `--check` compares every page since 2026-11-01); on Windows `git add area/` and run it again, or the sitemap dates
  every page today. The sitemap dates a `--no-ff` merge's pages by the merge day (`--first-parent -m`); a fast-forward keeps commit dates.
- **Quarterly crime roll** (first done 2026-10-23): set `EDITION` + `XLSX_FILE` in `refresh_crime_from_ons.py`
  (copied from the ONS page, never its `current` folder), then `--write-lambda --all`, `--write --all`,
  `--check --all`, `build_area_pages.py --write`, and re-derive METHODOLOGY s6 (`check_worked_example.py`);
  `CRIME_EDITION_LABEL` must equal `edition_label()` (tests/test_provenance_periods.py).
- **Monthly HPI roll**: `sh scripts/deploy_hpi_roll.sh`; it must move `SNAPSHOT_VINTAGE_LABEL`,
  `CPIH_12M_PCT[current]` and `SNAPSHOT_CPIH_PCT` together (`build_hpi_prices.py --check --all` reds otherwise).
- **DEFRA Round 4 maps 2021, a COVID year.** Never apply an estimated correction for it.
- **National anchors are per POOL** (`pool_of(city)` / site `poolOf`: a city's `pool`, else its currency;
  one per US metro: decision 2 of 2026-10-16, built 2026-10-18): never pool USD with GBP, nor the Bay Area
  with New York. The site needs `BACKEND_ONLY_PRICES` /
  `BACKEND_ONLY_TRENDS` to pool what the API pools; only `tests/borough-score-parity.mjs` (output parity)
  can see a miss.
- **`weights` in a response is the APPLIED table**; reproduction residual is published as "under 0.08".
- **Leaving `BACKEND_ONLY_CITIES` is a one-way door**: the site must then reproduce the API on every borough.
- **The Breathe London key lives ONLY in `.env`** (`BREATHE_LONDON_API_KEY`, typed in by Bill, never pasted into
  a chat, never `cat .env`): sent as the `X-API-KEY` header; check it by printing set/MISSING and its length.
  A missing hour is a row with a null value, so capture is valid hours over the WINDOW's hours, never the rows;
  `/SensorData` returns every INSTALLATION's hours, so only the current place's count (`measuring_since`).
- **Never name a non-city data file `*-boroughs.json`**: five scripts glob that suffix to enumerate cities.
- **US quiet geometry uses per-city fields** (`runway_lobes`, `airport_sizes`, `corridor_weight`,
  `major_airports`); never put US sizes in `AIRPORT_NOISE_SCALE` (it mirrors index.html). A runway lobe
  runs `RUNWAY_LOBE_KM` (15 km), mirrored in index.html. A fit only tests points near its monitors: check
  anything far from every monitor against an independent source (v5.7: the US DOT map caught Manhattan).
- **`check_flood_georef.py` re-samples a small-sample miss on 64 cells a class at 92% before failing** (2026-11-05): at preflight's
  4 a class one boundary cell is 75%, under the 80% bar, all day, and 16 at 90% was too small to say so too (`docs/lessons/flood.md`). Judge a
  change here per city on the real sampler, never on a formula: the binomial called 48 at 90% an improvement, and three cities' bad edges got easier. Repeat draws in `spread_samples` are on purpose.
- **A download's 200 is not the product**: test its magic bytes (FEMA's portal answered a missing county
  product with its page template, 2026-10-20; `docs/lessons/us-cities.md`).
- **A tile service's 404 is "not cached", never "quiet"**: measure which levels a cache holds before reading
  a tile as a reading (BTS's road cache stops at 12 though it lists 24). US shares (crime, road, flood) are
  not on the UK scales: each takes a US scale, LINEAR on its California anchor (`us_anchored_to_score`: 10 at
  zero, 5.0 at the anchor, 0 at double; Bill, 2026-10-18; `docs/lessons/us-cities.md`).
- **A Bay Area ZIP is scored as the city holding HALF OR MORE of its 2020 residents**, shares said (Bill, 2026-10-23);
  `build_bayarea_zips.py` writes the site's file AND the Lambda's `BAYAREA_ZIPS`, `--check` holds them equal.
- **Pooled figures hide per-city optimism**: any fit must hold per city (no city may read quieter than its
  yardstick).
- **A parity claim is a claim about a holder: read it, never retype it.** The Bay Area's transport bands were
  typed (50/25/10) and called "the UK's" (75/50/25) to Bill; they are now parsed from `build_borough_bands.py`.
  Likewise an anchor counts only what its unit can (the crime anchor: agencies policing residents, 21.39).
- **Every value's provenance is built from the response that answered** (`with_provenance`, from the full body,
  then cut to what `?include=` sends; 2026-10-23). A new context field or credit line needs its rule and its
  registry source (`backend/tests/test_provenance.py` names it); a loader roll moves `PROVENANCE_PERIODS` with it
  (`tests/test_provenance_periods.py`); a credit-line pattern names its city's OWN airports (the Bay Area once
  matched New York's); only an instrument's reading is `measured`: DEFRA's and the EA's maps are `modelled`.
  `aircraftQuietCoverage` follows it (`modelled`/`city`/`outside` since 2026-11-04; every reader tests only `=== 'outside'`).

### Frontend
- **One registry, `CITY_DATA`.** No `if (city === 'x')`; add a registry field to ALL cities
  (`tests/smoke-local.mjs` asserts key parity). New `=== 'nyc'` tests must be declared in
  `tests/test_us_city_branches.py`.
- **The map's source is `index.html`, served at `/map/`; the front page is `home/index.html` at `/`.**
  Locally, `/` is still the map. `js/api-base.js` is loaded by an ABSOLUTE path.
- **Phone vs desktop is `PHONE_LAYOUT = '(max-width: 900px), (max-height: 500px)'`**, stated by every @media
  rule (`tests/test_phone_layout_query.py`). Never test `innerWidth` against 900.
- **`.no-result-yet`, not `.empty-state`**, marks "nothing searched yet".
- **Air measured nearby is ONE pair of functions** (`nearestSensor` / `nearestMonitor` in `js/street_report.mjs`)
  for the front page, the full map's panel (dynamic import) and both reports: 5 km, never "none nearby", a stale sensor file hidden, credits linked.
  **The full map's panel is "Air quality nearby", side by side** (Bill, 2026-11-03, refined B): DEFRA's MODEL for the
  postcode's own 1 km square (from `/v1/environment`, read with its provenance; the council average stands in, named so,
  if it cannot load) beside the sensor and monitor on ONE scale per pollutant to 4x the WHO 2021 guideline, by
  `airChart()` (pure; `tests/air-chart.mjs`); the model is a hollow ring, never "measured"; `AIR_WHO_2021` equals the API's.
- **The full map's postcode panel is findings first** (Bill's pick, 2026-11-04: Stitch's draft): four `.find-group`s, then every earlier section unchanged in
  `#panel-all` ("All the detail"), closed; ids stay, so the loaders fill them there. `js/panel-findings.mjs` words each finding, pure text, null when there is
  nothing true to say (`tests/panel-findings.mjs`); `fillFindings()` places them. Road noise leads with the council's rating over the postcode's own figure
  (Bill's call: a rating can sit above a figure under the guideline, so the group's note says whose it is); with no figure the rating names its council;
  a surveyed-quiet bound (`roadNoiseBelowDb`) is no reading and takes no rating. Station and doctor read the panel's own first row, so they cannot disagree
  with it. "Last home sold" skips `other` and category B: SW5 9HP's January 2025 sale is not a home. A test of a folded section calls `keepPanelOpen()`
  (`tests/panel-fold.mjs`); what shows before anything is opened is `tests/uk-city-panel.mjs` "Findings first". If the module fails, the fold opens.
- **/pricing has a colour for each audience** (Bill's pick B, 2026-11-04): `#reports` tint, `#councils` water, `#platforms` dark. His "no highlighted card, one
  button style" (2026-10-06) now holds WITHIN a section, measured by `tests/front-page.mjs` 16b. Words and `data-event`s are untouched by a restyle: diff them.
- **Area pages say findings, not a table** (Bill's yes, 2026-11-04: Stitch's layout): `gather()`'s facts are unchanged; `findings_html()` places each fact, a label with no place stops the build. A bare figure gets
  plain words: crime against the London median (`crime_against_london`), Progress 8 as a band (`school_band`), bars in `score_colour`, all three held equal to `index.html` by `tests/test_area_findings.py`. A
  figure where a band would be stays a figure. `visuals()` (his pick B) draws only what truly compares: a share of postcodes, a figure beside a named yardstick from a true zero, a strip for a rating
  among its own words. Aircraft noise and the price trend stay words: nothing honest to draw them against. A figure not held draws nothing. Planes pages lead with `day_figure()`'s "Up to N", always with its "Up to": a bare 318 reads as every postcode's. The score span and ` data-fact` are read by tests.
- **One palette for the pages, held by `tests/test_site_palette.py`** (Bill, 2026-11-04: "ensure the colour scheme is consistent"): a
  rebuilt page joins `HELD` and cannot drift; every other page is declared with its reason, and the waiting list can only shrink (empty since 2026-11-05, when `/bay-area/` joined). Read a
  colour from the repo, never from a mock-up (the amber `#f0b429` I called the scores' was in no file). Colours that carry meaning keep
  their own holders: `scoreColor`, `BAND_COLOURS`, the air marks. The full map keeps its own surfaces.
- **Stitch gives layouts, never colours or code** (Bill's pick, 2026-11-04): its pages load Google Fonts, some Tailwind from a CDN (the CSP
  refuses it), its design system recalculates exact values, and it reported a recolour it never made. Apply exact colours yourself and
  measure the pixels. A chart needs a real comparison; otherwise the finding in plain words, then its number (`docs/lessons/front-page-and-site.md`).
- **The brand links home on every page** (`tests/test_brand_links_home.py` finds them). **"Have your say" links come
  only from `HAVE_YOUR_SAY`** (verified live; add an airport only after checking its pages; a time-limited link, such as
  a consultation, carries `until: 'YYYY-MM-DD'` and drops out by itself after it).
- **The Heathrow consultation pack** (`/planes-overhead/heathrow-consultation/`, 2026-11-01) is BUILT by
  `build_planes_pages.py` for every council with a district page counting Heathrow, its link and closing day READ from
  `HAVE_YOUR_SAY` (`until`): neutral wording, today's flights only (never a third runway's routes), the area page's own
  noise/air/flood. After `until` its `--check` reds until `--write` re-says "closed"; then `planes-pages-deploy`.
  Its ways in (2026-11-02, Bill: "clear and easy to navigate"): a line on each Heathrow district page, on the 32 councils'
  area pages and in the front page's planes answer, all from the `consultation` entry the builder writes into
  `data/planes-districts-by-council.json`, all gone after `until` (each `--check` reds until `--write`; then deploy).
- **The full map's Planes overhead layer is pictures, never figures** (2026-11-02, Bill's pick B2 of the mock-ups: "B's
  look without the blur"): `build_planes_layer.py` draws each postcode's own step from `data/planes/` into Web Mercator
  pictures (the map's projection, so two corners place them); a district/sector/hexagon colour was rejected because it
  washes out the few-hundred-metre strip under a low approach (TW4: 4% at 100+). A postcode shows its BUSIEST airport,
  never a sum (each airport's kinds of day are its own): every surface naming the layer says so. Smoothed until one
  picture pixel covers a screen pixel, sharp from there (`setPlanesRendering`). It and DEFRA aircraft noise are never
  on together; the legend's step colours equal `index.json`'s (`tests/planes-layer.mjs`, `test_build_planes_layer.py`).
  **A tap names the district under it** (2026-11-03, Bill's pick "small card"): read from `<city>-district-ids.json`
  (the outlines' own grid, run-length rows; a list of numbers, never a colour-coded picture), placed where the picture
  is; `districtFromGrid` mirrors `build_planes_layer.district_at` line for line; a card only if
  `planes-districts-by-council.json` lists the district (never a guessed link), beside the tap, never a figure.
  **A builder's new KIND of output needs its own deploy line**: `planes-layer-deploy` syncs named file types, so the
  first grids never shipped and the card stayed silent (2026-11-03); nothing fails, only the drift check can see it.
- **`/epc` takes full UK postcodes only** (2026-11-03): a ZIP or a bare district is the caller's 400 and never reaches
  MHCLG (it answered 400, which the Lambda reported as its own 502: 134 of the API's 146 5xx in a day); the map's
  `fetchEpcData` asks only with a full postcode. An upstream 400 for a valid postcode stays a 502: their change, loud.
- **The front page's lower sections type no figure** (front-page-v3, Bill's mock v8, live 2026-11-04): the walkthrough's steps 02-04 are written by `js/home-sections.mjs` from the hero's own example lookup
  (`home-engine.mjs` `exampleAnswer()`, one shared pair), the planes step through `planesWalk()` in `js/planes.mjs`
  (bar colours from the layer's `index.json` steps); step 05's picture is MADE from the sample PDF by
  `build_report_still.py` (its `--check` reds once the PDF changes: re-run `--write` after any sample regeneration);
  the dark band is written between PLANES-BAND markers by `build_planes_pages.py` (`--write --home` needs no tracks;
  `--check` reds the day after `until` until `--write`, then `home-deploy`). A worktree without the tracks checks the
  planes pages with `--check --inputs-from <main clone>` (read only).
- **The front page's planes answer links a district page only if that index lists it** (`js/planes.mjs` `planesLinks`):
  the index ships with the pages in `planes-pages-deploy` and the drift check compares it; never a guessed page.
- **Breadcrumb JSON-LD comes only from `build_area_pages.breadcrumb_ld()`** (area pages, /open-data/, every planes
  page; 2026-11-02): every item but the last is a link the visible breadcrumb shows, the last is the page's canonical
  (`tests/test_breadcrumb_ld.py`, every built page). `/llms.txt` (`meta-deploy`) is read by the wording gate and held
  to the sitemaps and the coverage sentence (`tests/test_llms_txt.py`); never a price or "AI" in either.
- **Focus rings use `--focus: #d35a12`**, never the brand orange `#f27d26` (fails 3:1).
- **Analytics only through `js/count.mjs`**; never GoatCounter's own script (it sends the query string).
  Campaign tags are an allow-list (`CAMPAIGN_KEYS`). The top bar's clicks are counted there too (`nav-<slug>`, `-menu` from the
  phone menu): reorder the bar from them, not from a guess (Bill, 2026-10-23: read them ~20 Nov). Email buttons
  too (`email-<page>-<what>`): the what comes from an ALLOW-LIST of our subjects, never the link (the map's
  correction subject holds a postcode), and a link with its own `data-event` is skipped (counted once). The About
  page's film and prototype too (`about-film`, `about-prototype`), from `WATCHED_LINKS`, exact destinations only.
- **The Book a demo link has ONE holder, `js/count.mjs` `DEMO_BOOKING_URL`** (2026-10-29): only `/pricing`, `/api/`
  (bar + page), `/score-demo/` and TWO front-page spots, the "Can I use it for my business?" answer (`faq`, since
  front-page-v3; the business card's button until then) and the closing band (never its bar; Bill, 2026-11-02) carry it
  (`tests/test_demo_booking_link.py`), counted by destination as `book-demo-<page>-<bar|bar-menu|page|spot>` (a spot
  from `data-book-place`); `make booking-link-check` refuses web/demo/home deploys while it is a placeholder.
- **The company LinkedIn link has ONE holder, `js/count.mjs` `LINKEDIN_URL`** (Bill, 2026-11-03): the front page's footer
  and Organization `sameAs`, both map footers and /about/'s "Get in touch" only, never the generated area/planes pages
  (a footer change re-dates them all in the sitemap); counted `<page>-linkedin`; `tests/test_linkedin_company_link.py`
  holds every copy, so at the rename change the holder and it names what is left.
- **`sw.js`**: `SHELL_ASSETS` is atomic (`cache.addAll`), so a precached file missing at the origin stops the
  worker installing everywhere; `/data/` is network-first; `/badge` passes through; every `no-cache` upload in
  the Makefile must be network-first (`tests/test_sw_no_cache_prefixes.py`).
- **The phone footer links the same places as the desktop footer**: add a link to both or neither.
- **No street basemap on the live map** (decided; the OS trial lives on the front page only).
- **The approach strip on `/how-it-works/` comes from the Blender repo** (`strip_page.py`): picture paths ABSOLUTE,
  a new render is a new folder (`strip_v8`), and `js/approach.mjs`'s two "EMBED FIXES" must reach `strip_page.py`.
- **`d3.v7.min.js` sits at the foot of `<body>` with a matching preload**; `defer` is wrong here.
- **The top bar folds behind a Menu POPOVER below 680 px** (no script: privacy/terms allow none, area pages carry
  none); every bar is held at 390 and 1366 wide by `tests/front-page.mjs` 16d. A new bar needs the same markup.
- **The front page's hero is two columns** (front-page-v3 step 2, live 2026-11-04; it ended the ~20 Nov read early, Bill's
  call, counts frozen on the Desktop): question, search and answer left, the live map right, nothing over it (no
  `.is-intro`, `data-map-inset` or `inert` any more). The example opens compact: `#ans-tiles` from `exampleFigures()` and
  `planesWalk().lead`, never typed; `#ans-more` opens the rest in place. The cities sit in `#city-menu` (`#chips` is still
  their holder; tests go through `pickCity`), and `#map-full` follows the city. The "New" pill goes with the consultation
  (PLANES-PILL markers, `build_planes_pages.py`). The map's box rule is `.mapwrap > svg`, never `.hero svg`: that one
  stretched a tick icon over half the page. No plane glides on the hero map (Bill: "isn't clear"; the mock's was dropped).
- **The answer after a search is summary first** (Bill's pick B, 2026-11-04: it ran to 495 words): the rows, the planes as tiles
  (`planesNodes`), one "Nearby" list (`factRow`), then folds holding what `planesNotes()`, `#ans-air`, `#ans-say` and `#ans-wrong`
  say, nothing deleted; a caveat that changes what a figure means stays on the row. A fold with nothing to say hides itself
  (`.ans-fold:has(> [hidden])`). The overhead drawing reads its two figures from the file's `definition`.
- **Never `text-transform: uppercase` on a unit** (2026-11-04): it turns the micro sign into a capital mu, so µg/m³ read MG/M³.
- **The front page counts its controls by name** (Bill, 2026-11-04, for the read that starts from the new page): `front-place-pick`,
  `front-fold-<which>`, `front-walk-<step>`, `front-dev-play`, `front-dev-lang`, `front-full-map`, through `engaged()`, once per
  page view. Never a postcode or anything typed; `tests/front-page.mjs` holds the shape of every counted path.
- **The postcode box's suggestions are `js/place-box.mjs`** (Bill's pick B, 2026-11-04; a WAI-ARIA combobox, replacing a
  `<datalist>`): read in the browser from what the page holds, nothing typed fetched, stored or counted (`tests/place-box.mjs`).
- **The front page arrives in place** (2026-11-04: phone layout shift 0.133 to 0.008): `.panel.is-loading` shows `.ans-skeleton`, the
  example's frame, until `endLoading()`; hidden tabs keep their room. Anything that fills in later keeps its place from the first
  frame. Held in `tests/front-page.mjs`, on a phone with the example held back.
- **The developers band's animation shows only what was answered** (Bill's pick C, 2026-11-04): `devAnswer()` builds the
  JSON and tiles from the example's own response, and `writeAnswer()` rewrites the three samples to that answer's point, so the
  request on show is the one answered and no lookup is added. Once on arriving, about 4 s (under WCAG 2.2.2's five), never a
  loop; again on a language change or Replay; at rest and with reduced motion everything shows, and Play is offered: a press
  is a request, whatever the setting (Bill's PC has Windows animations off, which is why he saw none). A number, its card and the
  card's figure arrive in one frame, one figure at a time, and the request box never moves (held frame by frame in
  `tests/front-page.mjs`, all three languages and at 390). The caret stays out of the text's flow, or a long URL re-wraps;
  typing keeps the whole text in the node, so Copy is never partial.
- **The developers band is one module on two pages** (`js/dev-demo.mjs`, moved from `js/home-sections.mjs` 2026-11-05): the front page and `/api/` carry the same ids, and
  `tests/test_dev_band_parity.py` holds their CSS and starting samples equal (a new band rule goes in its `RULES`). `writeAnswer()` runs for every answer, always from the samples as written (a read-back whole degree, `-2`, also matches the API's host), `armDev()` binds once.
- **/api/'s "Try a request" asks only the open route** (`js/api-demo.mjs`, Bill's brief of 2026-11-04): postcodes.io, then `/v1/environment`, never `/v1/score` (it would spend the public demo key). Arriving asks only the API, at a held point (`EXAMPLE`): the privacy policy covers a search, not an unprompted lookup. A repeat press costs nothing, and any newer press aborts what is on its way, even one that only replays (the route is 5 a second site-wide). The route's 404 is not always "no postcode": the Lambda answers it too when its own postcodes.io call fails, so the words cover both. The band keeps its room from the first frame under `@media (scripting: enabled)`, `.no-answer` giving it back (shift held under 0.02 at five widths). Every
  outcome is said in words: a neighbour's answer, a figure missing, a quiet road's bound (`under 40 dB`, a reading and never "missing"), no point (the Isle of Man and the Channel Islands: 200 with a null latitude), unknown, no figures, failed. `tests/api-demo.mjs` reaches each from
  real answers in `tests/fixtures/api-demo-env.json`; a late reply never replaces a newer one; a press plays whatever the motion setting (a review queried it, Bill confirmed it 2026-11-05: do not raise it again); counted `api-demo-<way>`, never a postcode.
- **A browser cannot read API Gateway's own errors**: `GatewayResponses` set no CORS header, so a throttled 429 is a rejected `fetch`, never a status (checked live 2026-11-05 on the 403 for a missing key). Word a failure to cover it.
- **About and How it works are on Stitch's layout** (2026-11-05, every word, link and section id kept; `tests/page-bands.mjs` measures them): About's speaker photo is the 16:9 hero, held from the top third so both the
  speaker and the screen stay; How it works opens on the short version, then the strip (a reversal of Bill's 26 Oct call, one move to undo); its worked example is open, a bar per score from `build_how_it_works.py bar()`.
  **"How it grew" is ten cards along a rail from 1320 px** (`ol.grew.across`; Bill's picks, 2026-11-05: across, cards, his talks among the steps as `li.talk` on the warm colour, reversing his 24 Oct "product steps only", the film kept in the timeline). They alternate above and
  below it on twelve columns: the first card takes three, for the film, every other two, each starting further along. Under 1320 px a card drops below a readable line, so it runs down the page. A new step means the column list and `STORY` in `tests/page-bands.mjs`.
- **`tests/test_home_links.py` holds every link the front page makes and every link back to it** (Bill, 2026-11-04):
  each reaches a tracked file or a page the planes index lists, each fragment an id there (a fragment that misses opens
  the page at the top, with no error). Links to other sites are checked from the live page after a deploy, never there.
- **The front page opens on an example answer** (`#ans-example`, `search(pc, { example: true })`): never in the
  address, never engagement, silent on failure. `stubLiveApi` answers its two lookups; scans wait for it.
- **"Describe what you want" (Find areas) is read IN THE BROWSER** (`js/find-words.mjs`, 2026-11-02, Bill: "without
  imposing on privacy concerns"): fixed rules, no server, no model, nothing typed sent, stored or counted (front-page.mjs
  checks no request or address carries the words). It only sets Find areas' own controls and says what it read and
  what it did not; never a figure of its own. The postcode box's place list comes from the page's rows (`js/place-box.mjs`).

### Gates and verification
- **Run preflight before every commit**: `sh scripts/preflight.sh` (== `npm run preflight`). Read the EXIT
  CODE; never pipe it (`| tail` is always 0). `INCONCLUSIVE` and `PASS (INCOMPLETE ...)` are not PASS.
  Change what blocks in `scripts/preflight.sh`, not in the skill.
- **Count `check` / `advise` / `net_check` call sites in `scripts/preflight.sh`**; never trust a count in prose.
- **A keyed request spends its key's quota on ANY route, open ones too.** `tests/stub-live-api.mjs` answers
  `/v1/score` and sends every other API request on WITHOUT the demo key (2026-10-31: ~13 keyed `/v1/regions` calls per
  preflight had been most of the public demo key's October use; `docs/lessons/quality-gates.md`).
- **Prove every new gate red on the defect itself** before trusting it green. Assert SETS, not counts.
- **Measure the DOM, not the flag that should change it**; poll for the state you want, never one already true;
  reach edge states on purpose (a state reached by chance is not gated).
- **Verify deploys from the ORIGIN, never from exit codes**: `sh scripts/check_deploy_drift.sh`,
  `tests/area-page-freshness.mjs`, `scripts/check_score_sanity.py`, `tests/site-api-parity.mjs`.
- **When a capability lands, exercise it the way a caller would** (postcode scoring "worked" for two days
  without being reachable).
- **When you delete a feature, grep for its NAME**, not just its function.

### Windows, shell and tools
- **`export MSYS_NO_PATHCONV=1`** before any AWS command with a `/`-leading argument (CloudFront invalidation
  paths, `/aws/lambda/*`), or Git Bash rewrites it to a Windows path. It ALSO stops `/tmp/...` reaching Windows
  programs translated (`curl.exe -o /tmp/x` writes `C:\tmp\x`): a script that hands temp paths to curl or python
  must `unset MSYS_NO_PATHCONV`, as `check_deploy_drift.sh` now does (2026-10-31: a false "0 of 25" after a deploy).
- **No user folder in a tracked file**: write `%USERPROFILE%` (prose, cmd), `~` (Git Bash, unquoted) or
  `$env:USERPROFILE` (PowerShell); `tests/test_no_user_paths.py` catches any name (audit M-5, 2026-10-23).
- **`make` is not on PATH**: `python scripts/make.py <target>` runs any Makefile target (`--dry-run` to see it).
- The AWS CLI emits CRLF; strip `\r` before comparing its output.
- The Bash tool's cwd persists between calls, env vars do not: keep `source .env` + build + deploy in ONE call.
- `Start-Process`: pass a script PATH (an `-lc '<cmd>'` string runs only its first word), and prepend
  `C:\Program Files\Git\usr\bin` to `$env:PATH` for `sh` runbooks. Run long loads detached with `python -u`.
- adsb scripts that open the ARCHIVES (`adsb_fetch.py`, `adsb_extract.py`) run under
  `~/tools/python-3.13.15/python.exe -I` (untrusted input); `adsb_fetch.py --workers 3` while the PC is
  in use. Stopping it is always safe (an extract is written whole or not at all). Readers of our OWN extracts
  (`adsb_movements.py`, `adsb_overflights.py`) run under the system Python: they need tzdata, numpy and pyproj.
- **The plane counter's field level follows the day's METAR QNH** (`adsb_movements.FieldLevel`, 2026-10-24): cache
  every month you count with `python scripts/fetch_metar.py <first> <last>` FIRST; an uncached month silently falls
  back to the aircraft alone and reads stormy mornings low. `data/us-runway-use.json` and the NYC yardsticks are
  built from this counter: rebuilding them now re-derives published US inputs, so do it as a reviewed change.
- **The overflight cone stands on the ground under the aircraft** (OS Terrain 50, 2026-10-26): run
  `python -I scripts/build_ground_grid.py` before counting (a missing grid refuses, never sea level); the 7,000 ft
  ceiling stays above SEA level. Day files name their ground, and averaging refuses a mix: recount into a NEW folder.
- Look up D3, AWS SDK and SAM APIs with **context7** before using unfamiliar ones; use **security-guidance**
  on Lambda / API Gateway edits and **frontend-design** on UI changes in `index.html`.

## Build and deploy (detail: `docs/lessons/deploy.md`)

- **Prefer make targets**: `fonts-deploy`, `data-deploy`, `web-deploy` (index.html -> `map/index.html`,
  privacy, pricing, changes, terms, `api/`, `how-it-works/` (+ its `img/`), `about/`, `js/`), `home-deploy` (front page, `/reports/`), `pwa-deploy`,
  `demo-deploy`, `prototype-deploy`, `meta-deploy`, `area-deploy`, `open-data-deploy`, `bay-area-deploy`,
  plus standalone `talks-deploy` and `deeplinks-deploy` (refuses placeholders), and `planes-pages-deploy` (after
  `planes-deploy`, before `meta-deploy`; refuses unless `build_planes_pages.py --check --strict` passes), and
  `planes-layer-deploy` (the full map's planes pictures: after `planes-deploy`, BEFORE the `web-deploy` that ships a
  map reading them; refuses unless `build_planes_layer.py --check --strict` passes).
- **`web-deploy-all` order is load-bearing**: fonts, then data, then web, then home, then pwa. Data before the
  page; web before home; fonts before `sw.js`.
- Pages go to `<name>/index.html` keys (the CloudFront function rewrites extensionless paths).
  `borough-extra.json` and `index.html` must ship `--cache-control "no-cache"`.
- **SAM deploys go through a reviewed changeset** (a blind `sam deploy` is refused): in ONE invocation,
  `set -a && source .env && set +a && cd backend && rm -rf .aws-sam && AWS_PROFILE=flightmap sam build &&
  AWS_PROFILE=flightmap sam deploy --no-execute-changeset --parameter-overrides EpcBearerToken="$EPC_BEARER_TOKEN"`,
  then `describe-change-set` and read it, then `execute-change-set`, wait, verify from the origin.
- **CloudFront configuration publishes are Bill's** (the classifier refuses them): hand over `!` commands.
- Backend before frontend whenever the site computes the new methodology locally.
- `.env` (from `.env.example`): `EPC_BEARER_TOKEN`, fastlane `ASC_*` vars, `FASTLANE_SKIP_DOCS=1`. Rotate the EPC
  token with `sh scripts/rotate_epc_token.sh`.

## AWS resources (detail: `docs/lessons/aws-and-loaders.md`)

- **API Gateway**: `https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/` (use this for checks:
  `api.skyscore.co.uk` does NOT resolve, its Cloudflare CNAME was never added)
- **CloudFront**: `https://d1oe4ftwutjpf.cloudfront.net`, distribution `EGSSPJKLFL33M`; site `skyscore.co.uk`
- **S3 bucket**: `london-flight-map-frontend` (eu-west-2)
- **DynamoDB** (PAY_PER_REQUEST, eu-west-2): `london-flight-map-favourites`, `-signups`, `-signup-pending`,
  `-noise-raster`, `-postcodes` (NSPL Aug 2026 edition). Verify a load with `get-item`, never `ItemCount`.
- **IAM**: `flightmap-dev`, `FlightMapDeployPolicy`; probe with `scripts/check_aws_permissions.py` (a
  permission is a timestamp, not a property). **SAM stack**: `london-flight-map`. **Region**: eu-west-2.

## Architecture (detail: `docs/lessons/architecture.md`)

- **Frontend**: single `index.html` (the full map, vanilla JS + D3, ~14k lines: measure, don't quote), the
  front page `home/index.html` + `js/home-engine.mjs`, B2B pages `api/`, `pricing.html`, `privacy.html`,
  `terms.html`, `changes.html`, `score-demo/` (Swagger, `openapi.yaml`), 102 generated `area/` pages,
  `bay-area/`, `open-data/`.
- **Backend**: `backend/template.yaml` (SAM), 8 Lambdas in `backend/lambdas/<name>/app.py`: `score`
  (`/v1/score` + batch, key-gated; `/v1/regions`, `/v1/changes`, `/v1/environment`, `/badge` open),
  `chat` (retrieval-only; `verify_answer()` discards unsupported numbers: never "simplify" it), `signup`,
  `favourites`, `epc`, `sold_prices`, `transport`, `nhs`. Handlers are `lambda_handler(event, context)` with
  CORS + HSTS + nosniff headers (`backend/tests/test_security_headers.py`). Dormant Bedrock Lambdas and
  `live_flights` live in git history only.
- **Every unauthenticated route carries its own throttle** (`backend/tests/test_route_throttles.py`).
- **Extension** (`extension/`): unlisted MV3 demo on Rightmove, reads `/v1/environment`.
- **Native**: Capacitor wrap in `mobile/`; iOS built by Codemagic (`codemagic.yaml`), Android locally. iOS
  v1.0.21 live (App Store ID `6768118116`); Android pending; Capacitor 7.6.9 iOS rebuild is Bill's.
- **Prototype** "Sky Score Radar": `prototype/index.html`, standalone Three.js.

## Git

- **Do NOT add Co-Authored-By lines to commits** (this user rule overrides any harness attribution default).
- Stage specific files, never `git add -A` / `.`; British English everywhere; messages say why.
- `data/*` is gitignored and un-ignored file by file: a new data file needs its `!data/...` line.
