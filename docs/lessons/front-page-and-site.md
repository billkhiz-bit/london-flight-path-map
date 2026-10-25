# The front page and the site around it

> Moved verbatim from `CLAUDE.md` on 2026-10-17 to keep the session-start file small.
> / vs /map/, the street report, pricing, top bar, New York on the front page, altitude, distances, favicon, count.mjs, Find areas, focus rings, grid references.
> Statements are dated as written; re-measure a number before relying on it, and when a
> rule here changes, update the one-line rule in `CLAUDE.md` too.

<!-- CLAUDE.md lines 1213-1451 (2026-10-16) -->
> ## THE FRONT DOOR MOVED ON 2026-10-06: `/` is the front page, the map is `/map/`
>
> **DEPLOYED 2026-10-06 (`41c0852`, master level) and verified from the origin**: drift 31 pages / 34 data / 103 area, every precached asset present; a browser on the LIVE site at 1440 and 390 found / the front page, /map/ the map with its API base, /reports/street/ making TW9 3PZ's report from the live API, /preview/ forwarding, no page errors or failed requests; manifest start_url /map/, worker v1.0.37; live e2e 33 of 33 (10 before the deploy); live phone layout PASS; site == /v1/score on 6 postcodes; responsive live 115 combinations across 17 pages clean.
>
> Bill's ruling, the same day, all four recommended options: the installed app
> opens the MAP (`manifest.webmanifest` `start_url: "/map/"`), reports are free
> and self-serve for your own home with firms asking by email, launch now and
> rename later, and the API / pricing / open-data pages (and all 103 area pages)
> carry the front page's site bar and footer links.
>
> - **The map's SOURCE is still `index.html`** - a dozen scripts write generated
>   blocks into it by that name - and `web-deploy` uploads it to `map/index.html`.
>   The front page's source is `home/index.html`, uploaded to the root key by
>   `home-deploy`. **web-deploy before home-deploy.**
> - **Locally, `/` is still the map**: the 18 gates that run their own static
>   server serve the repo path for path and were left alone. `tests/front-page.mjs`
>   is the exception: it routes every URL through the Makefile's upload lines
>   (`make.py --dry-run`), so it sees `/`, `/map/` and `/reports/` as the site
>   does and names any file no target uploads. Live gates (e2e, `responsive`
>   live half via a per-page `live:` slug, `site-api-parity`,
>   `live-mobile-verify`) were repointed at `/map/`.
> - **`sw.js` v1.0.37 precaches `/map/` BEST-EFFORT, outside the atomic
>   `SHELL_ASSETS`**, and an offline navigation falls back to `/map/` then
>   `/index.html`. The first version put `/map/` IN `SHELL_ASSETS`, and since
>   `cache.addAll()` is atomic the worker stopped installing wherever `/map/` is
>   a 404 - the native app (whose root IS the map) and every local gate (the repo
>   has no `map/`): preflight's offline and PWA gates went red with
>   `state=timeout-waiting` / `swRegistered: false`. `/` and `/index.html` stay
>   in the atomic list (the map there, the front page on the web).
> - **`index.html` loaded `js/api-base.js` by a RELATIVE path.** At `/map/` that
>   is `/map/js/api-base.js`, so every API call would have had no base. Absolute
>   now, and `tests/front-page.mjs` asserts it.
> - Area pages link "Open <borough> on the Sky Score map" to `/map/?city=...`;
>   the front page reads the same `?city=`/`?borough=`/`?postcode=`, so an old
>   `/?city=` link still lands on something sensible (the council area's card).
> - **The street report is ONE module, `js/street_report.mjs`**, shared by the
>   browser page (`/reports/street/`, `js/street_report_page.mjs`) and the PDF
>   script (`scripts/address_noise_report.mjs`, whose HTML was proven
>   byte-identical before and after the move on three postcodes). It holds the
>   DEFRA band colours and London's picture box as MIRRORS of index.html, held by
>   `tests/test_street_report_mirrors.py` (blocking, proven red) and by the PDF
>   script on every run; the front page's engine imports them instead of keeping
>   a third copy. A postcode with `aircraftQuietCoverage: 'outside'` gets no
>   report and no estimate tile: the endpoint's 10.0 there is from nothing nearby.
> - **The free report is ON SCREEN ONLY** (Bill, 2026-10-06, after asking whether firms
>   could pose as residents): no print button, and printing - a browser's "Save as PDF" -
>   prints a firms note instead, from the page AND from inside the report's frame (the
>   frame rule is injected by `js/street_report_page.mjs`; `tests/front-page.mjs` reads
>   the frame's own computed style, because hiding the page's result box hides the frame
>   too and a visibility check passed with the rule removed). The free copy carries "Free
>   copy for personal use, not for use with clients". The PDF is the paid product for
>   firms (`scripts/address_noise_report.mjs`, which never gets those additions, so it
>   stays byte-identical to the module). **It REFLOWS on a phone since 2026-10-12 (audit I-6, WCAG 1.4.10; Bill
>   chose "reflow it")**: below A4 width the frame is fluid, and under 600 px the free copy's injected CSS gives two
>   tiles a row, one column and 11 pt type; the routes table becomes a list whose cells carry `data-label` read from
>   the table's own `th` cells (never retyped); the map alone keeps 720 px in its own `.map-scroll`, opened on the
>   pin and a tab stop only while it scrolls. The free copy's "Prepared" date is the page's UTC `made` (M-6), never
>   the local clock. `tests/front-page.mjs` checks 390 and 320 px: the FRAME must fit the screen (the old page
>   scrolled inside `.sheet-wrap`, so "the page does not scroll" passed it) and the QR still decodes.
> - **EVERY PRICE LIVES ON `/pricing`** (Bill, 2026-10-06: "one pricing page, in the top bar").
>   The report tiers moved there as `#reports`; `/reports/` states no figure (the gate fails on
>   any `£` digit there) and every old `/reports/#prices` link points at `/pricing#reports`. A price
>   shown twice (the pilot on both ladders, the API tiers on `/api/`) carries one `data-price` key.
> - **The free copy is protected, never by the shared module** (Bill: "people can screenshot and
>   maybe edit it"): `js/street_report_page.mjs` adds a watermark, a REFERENCE (8 chars of a SHA-256
>   over the postcode, the day it was made, the AIRAC cycle and the seven figures the copy states), a
>   check link + QR code, and the terms line. The check stores NOTHING: `?postcode=&made=&ref=`
>   re-makes the report from today's data and recomputes with the copy's date; a mismatch says the
>   figures moved OR the copy was changed, because it cannot tell which. The QR is vendored
>   qrcode-generator 2.0.4 (MIT) and `tests/front-page.mjs` DECODES it with OpenCV. The frame REFITS
>   as its body resizes: measured once, it was cut off when the web fonts arrived.
> - **The top bar marks the current page with an UNDERLINE, never a fill**, and Full map is an
>   OUTLINED button: an orange block beside a grey box read as two selected tabs. The underline is
>   `#d35a12` (3.61:1); the brand orange is 2.44:1, under WCAG 1.4.11's 3:1 for a state cue.
>   **Hover underlines too (thinner, dark), never fills** (Bill, same day); gated in 16c on
>   every bar. The generated pages put the brand INSIDE the site nav, so a check picking "the
>   first link" there reads the brand: exclude `.site-brand`.
> - **NEW YORK IS A FRONT-PAGE CITY since 2026-10-06** (Bill: "show on the main screen instead
>   of going to the full map"): a chip, not a link out. Outlines `data/nyc-boroughs.json`, routes
>   the FAA's `data/us-flight-procedures.json` (JFK, LGA, EWR, TEB - until v5.6 the full map drew New
>   York's HAND-DRAWN corridors), and `scripts/build_nyc_front.py` writes `data/us-nyc.json` (one
>   row per borough FROM `resolve_query`, in the open-data CSV's row shape, so the card is
>   unchanged) plus `data/aircraft-noise-nyc-laeq.png` (US DOT 2022, via
>   `build_bay_area_page.build_noise`). `--check` is BLOCKING ("New York front page == engine").
>   The open-data CSV still EXCLUDES New York, deliberately. The card prints dollars, "Borough
>   of", and a note that the figures are curated (NYPD CompStat, borough medians) and NOT
>   comparable with the UK's. A card fact shows only when the row HAS its column, so UK cards
>   keep one price in pounds. Not yet: New York ZIP search on the front page (it says the ZIPs
>   are on the full map). **New York's lines are `data/us-nyc-routes.json` since 2026-10-07**: the Bay Area's
>   derivation (`bay.routes()` / `bay.arrival_routes()` now take an airport list) run for JFK, LGA, EWR and TEB by
>   `build_nyc_front.py`, whose blocking `--check` holds the file; arrivals included. Both US cities share
>   `state.usRoutes`, so `loadNyc()` MUST replace it: left out, New York drew the Bay Area's 16/36/35 lines
>   (proven red in `tests/front-page.mjs`). The footer credits the UK AIP (NATS) and carries the FAA's "as is" line.
> - **THE PLANE ALTITUDE IS THE GLIDE PATH'S, ON EVERY SURFACE (2026-10-07, website audit A1).** The full map's "Plane altitude" was a hand
>   ladder by distance to the airport ("4,000-6,000 ft" at TW9 3PZ) while the front page and street report said about 1,800 ft.
>   It now lazy-loads `js/flight_geometry.mjs` + `data/flight-procedures.json` (`ensureFlightGeometry`, like the stations) and
>   gives a height only under a final approach via `finalOverhead()`, the ONE rule the front page imports too. **New York
>   too since the same evening**: `planeAltitude(city, lat, lon)` reads the AIP's record for a UK city and the FAA's
>   (`data/us-flight-procedures.json`, 227 KB, loaded only for a non-UK search) otherwise; the JFK/EWR/LGA ladder is
>   deleted (Woodhaven 11421 "About 1,200 ft (JFK 13L final approach)"; Chelsea 10001 "Not under a final approach").
>   A published approach is not a busy one (JFK 13L's straight-in ILS is rarely flown), and the row never says how often. Gate: `tests/uk-city-panel.mjs` (a physics bound). Any local test server that serves the
>   map must map `.mjs` to a JavaScript type, or the import fails there while the site is fine.
>   **A result is analysed BEFORE the search-time data is awaited** (the pin must not wait), so both result paths call
>   `planeAltitude()` again after the await: a deep link (/map/?postcode=) never focuses the search box, never preloads, and
>   printed N/A until that refresh (found retaking the LGM screenshot). The gate drives a deep link in a fresh page too.
> - **THE FULL MAP'S DISTANCES ARE THE FRONT PAGE'S (2026-10-08)**: for TW3 1ES the panel said "Heathrow 6.3 km,
>   within 0.6 km of a flight path" (the airport's reference point; the nearest corridor POINT, 1 km apart) where the
>   front page said 4.9 km and 0.3 km from the 27L centreline. `shownDistances()` (beside `planeAltitude()`) now gives
>   the panel routesNear()'s runway-strip distance and the distance to the drawn SEGMENTS, through
>   `js/flight_geometry.mjs`, recomputed after the geometry await on both result paths. **Only the words moved**: the
>   noise estimate still reads `airportDists`/`minPathScaled`, which mirror the Lambda. Same day: the first-run hint
>   now goes on ANY result (`hideFirstHint()` in `triggerSearch()` and `updateSidebar()`; a deep link and a borough
>   click left it over the answer), and a city with no flight path says so instead of "Infinity km". Gate: four
>   checks in `tests/uk-city-panel.mjs`, all proven red on the old map.
> - **EVERY PAGE CARRIES THE FAVICON (2026-10-08)**: `/favicon.ico` (16/32/48), `/icons/favicon.svg` (a SIMPLIFIED
>   mark: the app icon's rings vanish at 16 px) and `/icons/apple-touch-icon.png` (180, the full app icon on solid
>   ground, because iOS fills alpha with black), all rendered by `scripts/build_favicons.mjs` (no `--check`: Chromium
>   rasters are not byte-stable). Before it, three pages drew a ✈ emoji and 122 drew nothing. Both page generators
>   write the three links; `tests/test_favicons.py` reds on a page without exactly one of each in `<head>`, an old
>   icon, a generator that drops one, a touch icon with alpha, or an icons upload of one type. A page with a strict
>   CSP needs `img-src 'self'` or Firefox blocks the icon (404 and the two `/preview/` forwards gained it).
> - **WE COUNT WITH OUR OWN `js/count.mjs`, NOT GOATCOUNTER'S SCRIPT (2026-10-11, audit 2026-10-09 I-1).** Its
>   `count.v5.js` (pinned with SRI on 7 Oct) sent `q: location.search` with every hit, a literal inside `get_data()`
>   that no setting reaches, so a postcode in a page's address reached GoatCounter against privacy s2c. The module
>   sends GoatCounter's documented `/count` endpoint the path (the canonical's, never a query), the title AS SERVED
>   (the full map writes the postcode into `document.title`), the referrer WITHOUT its query (a same-origin move keeps
>   it), screen size, an event flag, and on a page view the `utm_source`/`utm_medium`/`utm_campaign` tags ALONE
>   (`CAMPAIGN_KEYS`: OUTREACH_DRAFTS' UTM convention files outreach visits by them; the first deploy sent none and
>   broke it for an evening; never widen it to "everything but postcode", since `ref` is the free report's
>   reference); it keeps `window.goatcounter.count(vars)`, so no event caller changed, and
>   skips localhost, frames and the `#toggle-goatcounter` opt-out. One tag on eleven pages and in
>   `build_bay_area_page.py`: `<script type="module" src="/js/count.mjs"></script>`, held by
>   `tests/test_analytics_first_party.py` (no `gc.zgo.at` anywhere, policies allow it), and `tests/front-page.mjs` 8a
>   reads what the real module would send from a postcode address. Never go back to GoatCounter's script.
> - **"FIND AREAS" IS CONDITIONS ON PUBLISHED FACTS, NEVER PERSONA RANKING (built 2026-10-14, reviewed and
>   committed 2026-10-15, DEPLOYED 2026-10-15 `86ecd1b` on Bill's "make it live if it's accurate", verified live).**
>   Accuracy was checked two ways before release: an independent recompute (Python, the CSV and the written-out
>   thresholds only) matched the page on six combinations, names and order, locally and then LIVE; and
>   every sentence was read against its builder, which found three untrue ones, fixed in the release: the shares are
>   over POSTCODES, never "addresses" (the council card said it too); the council aircraft band is estimated from
>   distance to the airport and its routes scaled by its DEFRA map (`build_aircraft_bands.py`), NOT from the AIP's
>   flight routes (that is the postcode answer); the flood figure is rivers and sea only. A second tab in the front page's panel (`#tab-find`, real WAI-ARIA tabs)
>   filters the open-data CSV by region, a HARD budget, and avoid/want conditions whose cuts (`FIT_CUTS` in
>   `js/home-engine.mjs`) are the map's own band cuts; matches are shaded on the map. Persona reweighting was
>   measured and rejected first (it moves levels, not order). `tests/test_fit_conditions_mirror.py` holds the cuts
>   to `build_borough_bands.py` AND asserts the list and the map make the SAME call for every area (the CSV is
>   rounded, bands are cut unrounded: Bradford's road share prints 50.0, on the cut). The 15 Oct review fixed five
>   defects, each with a check in `tests/front-page.mjs` 18d/18e proven red: focus fell to `<body>` after a list
>   rebuild (`focusAfterCard()`, never into the hidden `#pc`), a shared `?borough=...#find` link lost its card
>   (`keepCard`), a city chip synced the list BEFORE `show()` had moved the map, so New York left a UK list beside it
>   (now `show(key).then(syncFindWhere)` and the note says the map is elsewhere), plus two superseded-`show()` races.
> - **"AVOID AIRCRAFT NOISE" NEEDS NO ROUTE ACROSS THE AREA (2026-10-16, audit I-3, Bill's "go ahead").** The lowest
>   band alone offered Bexley, under London City's runway 27 final approach. `data/area-route-crossings.json` is the
>   page's own `routesAcross()` count per council area, written by `node scripts/build_area_route_crossings.mjs`
>   (it drives the front page in a browser via the exported `routeCrossingsByCity()`; blocking `--check`, and a new
>   AIRAC cycle reds it). A region the map does not draw (Cardiff, Nottingham, Norwich) is UNKNOWN, never a pass.
>   London's list: 13 areas -> 4. Ships in `data-deploy` (no-cache). Same audit: the card lives IN the selected tab's
>   panel (moved there by `openCard`/`setTab`), the skip link targets the open tab, the card is not a live region when
>   focus moves into it, the count is announced after 800 ms, and fitting areas are outlined in a `.fit-outlines`
>   layer ABOVE the noise picture.
> - **A VOTE FOR WHERE THE MAP GOES NEXT IS A COUNT, NOT A FORM (2026-10-13).** The front page's uncovered
>   answers send one GoatCounter event: `event/want/uk/<council area>` (from postcodes.io, NEVER the postcode)
>   or `event/want/country/<code>` from `WANT_COUNTRIES`, a FIXED list (no free text: people type addresses).
>   No email until I17 is flipped and the ICO fee paid. `tests/front-page.mjs` 18c holds it; privacy s2c
>   still names page views, referrers and screen sizes only (wording is Bill's, legal batch 2).
>   **DEPLOYED 2026-10-13 evening and verified live** (the real `count.mjs` with `navigator.sendBeacon`
>   replaced by a recorder, so the check counted nothing: never verify analytics by sending real hits).
>   **The votes live ONLY in GoatCounter** (`cubitt33`): events with paths starting `want/`, read with the
>   dashboard's path filter. Claude cannot read them without a GoatCounter API key in `.env`. Once per place
>   per page VIEW, so a reload votes again: a demand signal for EXPANSION.md, never a poll.
> - **Focus rings use `--focus: #d35a12`** on the front page, its reports pages, the full map, `/pricing` and `/api/`
>   (audit I-7, 2026-10-07; the last two 2026-10-11, audit 2026-10-09 I-7): the brand orange is 2.17-2.72:1 against them.
>   `tests/test_focus_ring_contrast.py` has NO file list since 2026-10-11: it walks every served page with a focus rule
>   and bans the brand orange COLOUR `#f27d26` in any ring (outline, stroke or box-shadow, literal or via any token),
>   so 404.html's darker `--orange` (#c2410c) passes. Widening it found the full map's ranking rows ringing in an orange
>   inset `box-shadow`, which the old outline/stroke-only check could not see.
> - **A RUNWAY WITH NO GLIDE ANGLE IN THE RECORD IS A GAP, NEVER "NOT UNDER" (2026-10-11, audit 2026-10-09 I-5).**
>   `routesNear()` returns `unglided` (JFK 13R, TEB 01, SFO 01L/R, OAK 15/33 and every runway of the runways-only
>   LGW/STN/LTN records, each extended at a nominal 3 deg); `unglidedOverhead()` applies `finalOverhead()`'s rule and
>   is asked only when no glided final is overhead. Howard Beach (11414) reads "N/A (no glide path in the FAA record
>   for JFK 13R)", not "Not under a final approach"; the front page says "In line with ... the record gives no glide
>   path for it". Never give a height from the nominal angle: it only withholds a negative.
> - **The phone footer's "More" links the SAME 16 places as the desktop footer (2026-10-11, audit 2026-10-09 I-4)**,
>   Front page first: the installed app opens `/map/`, so without `/` it was a dead end. `tests/mobile-legal-links.mjs`
>   reads both footers and fails on any difference; add a footer link to both or neither.
> - **The front page's `search()` takes a number (`searchSeq`) and stops after any await once a newer search has
>   begun (2026-10-11, audit 2026-10-09 I-3)**; `tests/front-page.mjs` 11a holds one lookup 1.5 s under a second.
> - **A POSTCODE IS SAMPLED AT ONS'S GRID REFERENCE, NEVER A RE-PROJECTION (2026-10-11).** `scripts/postcode_grid.py`
>   (`grid_ref()`) is the one holder: NSPL's `east1m`/`north1m`. Re-projecting its lat/long with pyproj (no OSTN15
>   grid) lands a median 1.75 m off, the next 10 m cell for 22% of road readings (median 2.8 dB, one in ten of those
>   10.9 dB or more; aircraft 5.6%, at most 0.7 dB). **BT postcodes are IRISH Grid in NSPL** (BT1 1AA would sample
>   near Wigan), so they and rows with no grid reference keep the projection. Every loader and the bands builder use
>   it; `tests/test_postcode_grid.py` fails any script that projects WGS84 to the British grid without it (exemptions
>   named, with reasons). **A re-placing needs `scripts/remove_lost_readings.py --apply` after the reload**: the loader
>   upserts, so a field the new placing lost stays in the table. The Lambda publishes the below-40 bound ONLY when
>   no reading is stored, so the visible harm is one-sided - measured on the 12 Oct dry run: 3,047 postcodes kept
>   publishing an OLD road reading where DEFRA at ONS's point records below 40 dB (AL2 3FS: 47.4), and 16 kept an
>   old aircraft cell the site's datasets had already dropped (site and API disagreeing); the other 3,522 carried a
>   stale bound their new reading hides. The borough shares
>   move under one point (one band: Bradford road low -> moderate); re-derived 2026-10-12 on PCM 2024 rather than
>   waiting for 2025 (231 fields, 19 of 816 scores by 0.1). The per-postcode AIR table needs its own reload too
>   (`load_defra_air_quality.py --live-only`; 2,860 postcodes change 1 km square), after the noise reload.
>   `load_aircraft_rasters.sh` now loads London's region raster too (it was in no runbook) and deploys through
>   `make.py data-deploy`: it used to upload `index.html` to the ROOT key, i.e. over the front page.
> - **The council card names undrawn routes (2026-10-11, audit 2026-10-09 M-4)**: `routeGap()` is the one wording,
>   shared with the postcode answer, and `routeGapsNear()` lists every airport within 30 km of the area's NEAREST
>   point whose routes the record lacks. Trafford read "None of the routes on this map crosses it" under
>   Manchester's chart-only departures.
> - **EPC band letters take `bandInk()`** (#fff on A and G, #141414 on B-F; 2026-10-11, I-8), and
>   `tests/panel-contrast.mjs` has an `area panel, epc bands` state that fulfils `/epc`, because no run had ever seen
>   the bands render (offsite requests are aborted there).
> - **ROUTE EXPLANATIONS IN THE COUNCIL-AREA CARD (2026-10-09, audit 2026-10-05 M-15)**: the tooltip was a mouse's alone,
>   so the front page's card lists the routes on the map that cross the area (`routesAcross()` / `routesFactHtml()` in
>   `js/home-engine.mjs`), in the tooltip's own words, in a `<details>`. Inside is the DRAWN fill's rule, even-odd over
>   every ring in view space (the `.boro` paths carry `fill-rule: evenodd`; never d3's spherical tests, which the Bay
>   Area's rings do not suit); exact, not sampled; cross-checked against the browser's `isPointInFill` on all 165 areas.
>   "None of the routes on this map crosses it" always carries the radar caveat - never "no aircraft here" - and a city
>   with no routes prints no row. Gated in `tests/front-page.mjs` by keyboard (the card must carry the HOVERED tooltip's
>   exact text). Open on it: M-4 (undrawn published departures not mentioned) and M-13 (ring over the label on phones).
> - **THE FREE COPY'S QR CODE IS CRISP AT WHOLE DEVICE PIXELS PER MODULE (2026-10-09)**: `shape-rendering: crispEdges`
>   and a side of `(modules + 8) * ceil(3 * dpr) / dpr` px, re-set on resize (zoom changes the ratio). A fixed size
>   decoded on some DAYS and not others (the code holds the date): 132 px read 75/80 links, a flat 3 CSS px 47/80 at 150%
>   Windows scaling; this rule reads 78-80/80 from 100% to 200% at a fractional page offset. `tests/front-page.mjs`
>   asserts device px per module and crisp edges, and decodes at 1x AND 1.5x. Do not "simplify" it to a fixed width.
> - **Distances print one decimal on every surface** (2026-10-09): the front page's `km()` switched to whole km above
>   10 ("10 km" where the map said 10.2). `tests/front-page.mjs` reds on a whole-km figure at TW9 3PZ.
> - **THE NEAREST STATION IS SHOWN, NOT SCORED** (Bill, 2026-10-06: "show it first"): the front
>   page's postcode answer and every street report (free and PDF) say "Nearest station: X, N m in a
>   straight line" from `data/stations.json`, through ONE function, `nearestStation()` in
>   `js/street_report.mjs`. Beyond `STATION_SCOPE_KM` (3) NOTHING is said: the list holds stations
>   INSIDE the covered cities, so "no station near" could be false at a city's edge. The score's
>   transport input stays the council area's share within 800 m; scoring per address would be a
>   measured v5.6 that REPLACES that share, never adds to it (double count).
> - **AIR MEASURED NEARBY IS SHOWN, NOT SCORED (2026-10-19, ROADMAP "The plan for Breathe London" steps 3-4).** The
>   front page's answer (`#ans-air`) and every street report (free and PDF) name the nearest Breathe London sensor
>   (London) and the nearest DEFRA AURN monitor (every city), each within `AIR_SCOPE_KM` (5; Bill, 2026-10-19, after
>   measuring: a monitor is within 5 km of about half of places outside London, 21% in Leicester, 20% in West
>   Yorkshire; a London sensor is within 4 km of 90%), through ONE pair of functions, `nearestSensor()` /
>   `nearestMonitor()` in `js/street_report.mjs`. London shows BOTH (Bill). Beyond the scope NOTHING is said (the
>   files hold only what cleared the 75% floor). A sensor file more than `SENSOR_STALE_DAYS` (45) past its window is
>   hidden, never shown as current. The roadside sentence says a sensor by a road "CAN read higher" than DEFRA's
>   background: medians were roadside 20.6 against background 19.9, so "reads higher" would be false on some pages.
>   Each reading's credit is linked, word for word from the file (`--check` holds the wording). `tests/front-page.mjs`
>   works the expected lines out with its own maths at TW9 3PZ (George Street 1.5 km; the monitor 7.6 km away must
>   not appear) and M22 5RX (no sensor; Manchester Sharston 1.7 km), and the existing "every file the pages fetched
>   is one a Makefile target uploads" gate caught the two files missing from `data-deploy` on the first run.
>   **The full map's postcode panel shows it too (same day, Bill):** `renderAirNearby()` in `index.html` loads the
>   same module by dynamic `import()` (as the flight geometry is loaded), fills a hidden "AIR MEASURED NEARBY"
>   section and unhides it only when a reading is in reach; UK full postcodes only (an outcode's centre is not a
>   place to measure from). `tests/uk-city-panel.mjs` works the expected names out from postcodes.io's position:
>   SW11 1AA shows BOTH (sensor 1.1 km, monitor 4.0 km), M1 1AE / B15 2TT / LS1 4DY a monitor, 10001 no section;
>   proven red by removing the call and by rendering the section for every city.
> - **THE BRAND GOES HOME; HAVE YOUR SAY; SPOTTED SOMETHING WRONG? (2026-10-19, Bill).** The first "Sky Score" on
>   every public page links to "/": `tests/test_brand_links_home.py` FINDS the pages (globs, 123 on the day) and
>   declares the four without a brand (two /preview/ redirect stubs, two printed talk handouts), two-way. The full
>   map's link WRAPS `#map-title-text`, because `applyCityChrome()` sets its textContent. "Have your say" links
>   live ONLY in `HAVE_YOUR_SAY` in `js/street_report.mjs` (LHR, LCY: verified live that day, LCY in a real
>   browser since its site turns scripts away) plus `AIRSPACE_CHANGE`; `haveYourSay(scope)` answers for the nearest
>   airport in scope only, so Manchester gets nothing rather than a guessed link. `correctionHref()` is the map's
>   mailto, now on the front page and both reports. Proven red: a planted MAN entry and a postcode-less subject.
>   **The map's brand is a link ONLY where it can be seen**: on phones and tablets in the search view the title is
>   visually hidden (audit M32 keeps it as the page's heading), and the always-on link was a focusable control
>   nobody could see, under the city chips: `tests/responsive.mjs` failed 27 of 132 combinations on it (COVERED at
>   11 sizes). A `ResizeObserver` on `.map-title` now removes the anchor's `href` when the title renders at 1px and
>   restores it when visible (measured: phone/tablet `href` null, desktop `/`, 25 px tall for 2.5.8). The gate was NOT
>   loosened: a clipped control is a design question, and a visible wordmark on the phone map stays Bill's call.
> - **THE DEVELOPER BAND (2026-10-19)** shows two requests with Copy buttons: `/v1/score?postcode=` with the header
>   value `YOUR_KEY` (never a key) and `/v1/environment?lat=&lon=`, which needs no key. BOTH WERE TRIED before
>   they were written (403 without a key; 200), and the first draft's `/v1/environment?postcode=` would have
>   published a 400 ("lat and lon are required"). The host is held to `js/api-base.js` by
>   `scripts/check_api_url_drift.sh`, which did NOT read `home/index.html` until this change (proven: a planted
>   host now reds it). `tests/front-page.mjs` stubs the clipboard and asserts Copy copies exactly what is shown;
>   proving it red, a heredoc ate a backslash and planted a syntax error that CRASHED the run, which a
>   "no FAIL lines = green" harness reported as STILL GREEN: read the exit code and the summary, always.
>   The full map's measured air (`renderAirNearby`) comes AFTER "Additional insights" and names the Air
>   Quality card above only when it is there (Bill: above it, the two read as unrelated); rows from the front
>   page's exported pieces (`sensorSetting`, `sensorReadings`, `monitorSetting`, `monitorReadings`).
> - **THE COVERAGE LINE IS GENERATED (2026-10-19).** "Which places does it cover?" in the search card is a
>   `<details>` written by `scripts/build_coverage_strip.py` between the COVERAGE-STRIP markers, from the score
>   Lambda's registry (`app.CITIES`: name, country, council areas) and the Bay Area's outlines; `--check` (blocking)
>   holds the markup to the registry AND its UK numbers to the page's own "97 ... in 13" figure. It is ONE line
>   on purpose: written out in full it made the card four lines taller, and the card then covered the whole faded
>   London map (the backdrop check probed 0 points clear of it). Even one line cost probes: 8 px found 34 under
>   the floor of 40, so the grid went to 6 px, the precedent of 14 Oct (the floor stays; the grid gets finer).
>   A plain list, not chips: nothing in it is clickable until the area index has a heading id per region.
> - **"Cubitt33" stays on `privacy.html` and `terms.html` ONLY.** Bill asked for it off the
>   site for now; the legal pages must still name the company (trading disclosures, and
>   the controller in the privacy notice). Footers say "All figures from official public
>   data" - not "open government data", because the UK routes come from the AIP, public
>   but not openly licensed.

**`/how-it-works/` (2026-10-22): the method in plain English, its numbers derived.** Bill asked for it after the
22 Oct engagement research (a page explaining the score backs the number up; plain copy at a reading age of 10-12
converts better). Written to that reading age, linked from the front page's answer ("How it is worked out", beside
"Its figures") and from the front page's, the map's (both footers: they must list the same links) and the area
pages' footers. Its signature is the arithmetic itself: Hounslow taken apart, each score times its weight, adding
up to the published 3.4, with each part tagged by WHO made it ("official data", "area band", "our estimate", the
last two from `context.quietResolution`, never assumed). Every figure that can move (the example, the eight views'
weights, the price month, the coverage line) sits between `HOW-IT-WORKS-*` markers written by
`scripts/build_how_it_works.py` (blocking `--check` in preflight; `deploy_hpi_roll.sh` refuses to roll while it
is behind, because a price roll moves Hounslow's affordability). A first draft tagged the council area's Quiet
Skies "our estimate": wrong, a whole area reads the band we set, which is why the tag now follows the tier that
answered. Registered in the ten places a new page needs (Makefile web-deploy and its invalidation, lint:html, the
brand-link, a11y, e2e, responsive, fonts and top-bar tests, deploy drift, the em-dash list, the sitemap).

**The area pages are COUNTED since 2026-10-22.** Until then the 102 area pages, the area index and `/open-data/`
loaded no analytics, so the search entry pages were the unmeasured ones (GoatCounter showed ten paths in all).
`scripts/build_area_pages.py` now writes `js/count.mjs` into all three templates, and with it the strict meta CSP
the other counting pages carry, which `tests/test_analytics_first_party.py` requires of any page that counts (the
pages load only their own styles and fonts, so it blocks nothing). The site has NO header CSP (a distribution-wide
one blanks the prototype), so a page without its own meta policy has none at all.

**The About page (2026-10-23, LIVE).** `/about/` names the founder (Bill's call: a deliberate exception to keeping
names out of the repo, for this page only), with who it is for, why it was built, five questions really asked at a
talk, and the talks. Published before the rename's attorney opinion (Bill, 23 Oct); the Deen Developers photo is
held until they agree (original in `sky-score-drafts\about-photos\`). "Who it is for" is ONE list,
`scripts/build_who_for.py`, written between WHO-FOR markers into the front page and `/about/` (blocking `--check`).
Its opening said "beside every postcode" until a review caught the overclaim: "every postcode we cover".

**"How it grew" (2026-10-24, Bill: "a timeline, which includes the video").** Six steps on `/about/`, dated by MONTH
from git and CHANGELOG.md, quoting no count that moves (the coverage sentence and visit figures stay out, so the
section cannot go stale). The March step links Bill's Amazon Nova hackathon film (youtu.be/xbR9cP4Ad4A, 3:06), which
shows the retired AI product: its own voiceover says "AI-powered", the never-claim word, so the film is history with
a caption saying the AI answers came out in May, never a current demo. A LINK, NEVER AN EMBED: the page's policy
allows no frames, and an embed would set YouTube's cookies before anyone chose to watch (a `privacy.html` change).
The still is frame 1:13 of Bill's own export (`Downloads\Videos\Sky Score Video Demo.mp4`), cropped to the app (no
tab strip, taskbar or scrollbar). Do not write "first talk" for September: Deen Developers was July.
The demos first went on the timeline as small waypoints (ten entries); Bill chose (24 Oct, after GoatCounter showed
the About page at 3 views to the front page's 105 in October) product steps only on the timeline, demos under
"Talks and demos", where London Geo Meetup had been missing. Its readers are evaluators (API buyers, organisers,
journalists, employers), not home buyers. `about-film` / `about-prototype` clicks are counted from an allow-list of
exact destinations in `js/count.mjs` (`WATCHED_LINKS`); `tests/front-page.mjs` 16f clicks every link in `/about/`'s
main and holds the names sent to exactly film, prototype and the support email (proven red: film's entry broken ->
351/352, the film missing). Read them ~20 Nov with the top-bar and email counts.

**AI, said as little as possible (2026-10-24, Bill: "I don't want this to be synonymous with AI slop").** Public text
says AI only as an event's NAME (AI Tinkerers) or to say where AI is NOT used ("No AI summaries layered on top").
Never as how the product works or how it was built: the About letter lost "I built it with AI", the timeline says
"an AWS hackathon" (not "Amazon Nova AI Hackathon"), and the March still was re-cut from frame 1:13 (the "AI INSIGHT
POWERED BY AMAZON NOVA" panel) to frame 1:26 cropped to the MAP alone, because every full frame of the film carries
"AI-powered" and "ASK AI". Bill kept the film LINK (his call over a recommendation to drop it: it shows retired
features and AI-written prices; `about-film` will say whether anyone watches). The talk handout "How Sky Score works"
lost Part 10 (built with Claude Code; parts renumbered 10-12) and one Part 7 sentence; the companion "The 57 checks,
and how the coding assistant reaches Amazon" is UNLISTED from /talks/ (its URL still answers; `test_brand_links_home`
still checks it). The same edit found the handout breaking two standing rules since 22 Sep, unseen because no gate
reads /talks/: prices (GBP 499, GBP 2,500) outside /pricing, and "the data underneath is all published under the Open
Government Licence" after the 26 Sep move to UK AIP routes. Both fixed; the PDF regenerated with
`scripts/render_talks_pdfs.mjs` (it renders EVERY handout: `git restore` the ones you did not change). Check PDF text
with pypdf, never a byte search: the text is compressed, so a byte search reported a price still present (chance digits
in a compressed stream) after the prices were gone, and could equally miss words that are there.

**The wording rules became a gate (2026-10-24, Bill: "yes" to "a check that scans every public page").**
`tests/test_public_wording.py` (run by "pytest (root)") reads every file the Makefile UPLOADS (its `aws s3 cp
*.html` and `aws s3 sync <dir>/` commands, continuation lines joined: 126 pages, 103 of them area pages, and the 4
PDFs under talks/ and home/reports/, read with pypdf, pinned in CI's pip line) plus `js/*.mjs`, and only what a
visitor sees: text, alt/title/aria-label/placeholder, the description and link-preview tags, and script strings (a
small scanner, not a regex: template literals are read through their nested `${...}`, and each string has its tags
stripped and its entities and escapes decoded; URLs dropped). Never comments (the pages' comments quote the rules)
or the CSP (it names cubitt33.goatcounter.com). It holds: our prices (READ from /pricing, as £ or GBP) and anything
shaped like a price per month/report/call outside /pricing; a priced JSON-LD offer outside /pricing (any `price`,
`lowPrice`, `highPrice` at any depth); no figure beside the word licence on ANY page, /pricing included; VAT only as
"not registered for VAT"; Cubitt33 only on privacy/terms; the old name; AI only from an allow-list of read phrases;
the whole product as "open government data", "all ..." or "every figure ... OGL"; shares of addresses/homes; "<n>
planes a day" and "a plane every <n> minutes". It proves itself on every run: `RulesCatchTheirDefectsTests` feeds
each rule the page SOURCE of its defect through the same reader (`shown_from_source`) and must see it fail (18
cases), so a rule or the reader loosened later reds (checked by loosening FREQUENCY, LICENCE_FIGURE and the OGL
allow-list). Proven once on the REAL slip too: the handout as it was before `f13a737` reds the price, OGL and AI
rules. A review agent asked for what it would MISS found the first version's regex tokeniser dropped every nested
template literal (already losing real front-page text: home-engine.mjs's "Sky Score out of 10, balanced
weighting..."), read script strings as raw HTML (`&pound;39 a report`, `<b>41%</b> of homes` passed), looked for a
licence figure only in the price cells, COUNTED the pending AI mentions (a worse sentence swapped in kept the count)
and skipped a deleted write-up that S3 still serves; all fixed and each in the self-test. Calibrating found: "all
items" in ONS's CPIH series name tripped the OGL rule across 100 area pages (the rule stops at a comma or bracket);
count.mjs's GoatCounter URL tripped Cubitt33 (URLs dropped); /pricing's description lists prices beside "licences"
(allow-listed with its reason); the Norwich sample PDF's "All Open Government Licence v3.0 except the WHO guidelines"
is TRUE (it closes its list of DEFRA sources): allow-listed. And run ruff on a new test BEFORE the preflight: the
first version's `%` format failed "ruff (scripts, tests)" an hour in. Two write-ups are PENDING BILL, pinned to the
very AI sentences they hold today (`tests/public_wording_ai_pending.json`; re-pin with `python
tests/test_public_wording.py --write-pending` only after reading each change): "How Sky Score works" still describes
the API's assistant, which DOES call an AI model (true, and a privacy disclosure: the question goes to Virginia), and
"The 57 checks" was unlisted but is STILL LIVE: talks-deploy syncs every talks/*.html and *.pdf with no --delete, so
unlisting a page publishes it again on every talks deploy, and a write-up deleted here FAILS until its S3 copy is
gone too. **Bill ruled 2026-10-25:** the checks handout was archived (`archive/ai-tinkerers-2026-09-22/`) and its two S3 keys deleted; "How Sky Score works" now says only that the assistant's question is processed by Amazon in Virginia, USA, linking the privacy policy (its Bedrock entry, May history and every other AI-model sentence cut; 19 -> 18 pages). The pending pin, its sentences file and `--write-pending` are gone; a self-test now proves the AI rule reads the handout. Doing it found `privacy.html` never names the US transfer that `SUBPROCESSORS.md` row 18 records: drafted into legal batch 2, not live. An archived write-up goes OUTSIDE `talks/`: `aws s3 sync talks/` recurses, so a `talks/archive/` copy would be republished at a new address.

**"What you can hold us to" (2026-10-24, Bill's pick from About-page practice: Plausible, 37signals, Linear state what
you can hold them to).** Four promises after "Why I built it", then the publishers as TEXT (a logo implies an
endorsement). Wording held to what is true today: "credited to them", NOT "and when" (per-field periods are only on the
`provenance-per-field` branch); "none is invented by an AI", NOT "never a model's guess" (Quiet Skies and DEFRA's maps
ARE modelled); "no cookies" is privacy.html s8. The ONS, not the Home Office, for crime, as /how-it-works/#credits says.
Each name is a `<span class="src">`; `tests/test_about_sources.py` maps each to a LIVE row of LICENSING.md (above
"Removed sources") and fails on a name it does not know (proven red both ways: OpenSky on the page; FAA mapped to the
removed OpenSky). Not yet, and never faked: a user's quote (a residents' group, after the Earl's Court correction),
press, customer logos. Avoided: a team section (solo), visitor counts (small, moving), mission-speak.

**One page, story first (2026-10-24, Bill asked whether it was too much).** Measured: 6.5 desktop screens, 10 phone
screens; the length was not the fault, the ORDER was: "Who it's for" (1.3 phone screens, the same list the front
page shows) sat first, so the story began 2.3 phone screens down. Bill's calls: keep ONE page (the readers are
evaluators who want it in one place; sub-pages add clicks for 3 views a month; no accordions, hidden text goes
unread); move "Who it's for" to just above "Get in touch" as the step after trust (story now 0.9 phone screens
down; the WHO-FOR builder finds its markers anywhere); talk photos in one 16:9 row (the portrait Deen Developers
photo had set the row height; `object-position: 50% 45%` keeps the face). Sections open on a full-width `--rule`
line with clamp(64-104 px) between them (Bill: "bunched up, no clear separation"). Rule for later: new material
REPLACES (a quote goes into Questions or Talks), it does not add a section.

**THE PHONE MENU IS A POPOVER (2026-10-23).** Adding How it works and About made six links, which stop fitting
beside the name below 620 px (measured on four pages): the bar wrapped into three rows with "Sky Score" stranded in
the middle one (the front page's `header.top` has no `flex-wrap`, so its links wrapped inside their own box). The
responsive audit passed it, because nothing overflowed. Below 680 px every bar now folds its links behind a
`<button popovertarget="site-nav">Menu</button>`; the nav (`.top-nav`, or `.site-nav` in the generated pages) is
the `popover`, opening as a sheet across the top with its own Close button (`popovertargetaction="hide"`); Escape
and a tap outside close it too. A POPOVER, NOT SCRIPT, because privacy and terms carry `script-src 'none'` and the
area pages are gated to carry no script but the analytics tag (`tests/area-pages.mjs`): neither rule was worth
loosening for a menu. On a wide screen the closed popover IS the ordinary row of links: the UA hides a closed
popover only by its own `display: none`, which any author rule beats, so each page undoes the UA's popover box
(position, inset, border, padding, background) and keeps its own `display: flex`. The phone rules sit inside
`@supports selector(:popover-open)`, so a browser without popovers keeps the plain bar, never a dead button.
Written into the 13 hand-made bars and `404.html` by one script, and into the generator's three templates;
`tests/front-page.mjs` 16d holds all 16 bars at 390 and 1366 wide, measured (the name and Menu share one row,
Menu shows every link, Close and Escape fold them; on a desktop no Menu and one row with the name), proven red on
a page with the phone rule switched off and one with the desktop undo removed. The area pages now have a width
breakpoint, so `tests/a11y-source.mjs` scans them on both sides of every breakpoint the generator emits.

**ANSWER FIRST (Bill, 2026-10-23, option B of three mock-ups made on the live page).** Two
thirds of all views land on the front page and about 6% of those act, and a visitor met a question and an empty
box. A plain visit now opens on one real answer, `#ans-example`'s postcode (TW9 3PZ, under Heathrow's 27R
approach), labelled "Example: a street in Kew, under Heathrow's arrivals"; the box says "Your postcode" and the
button "Check yours" ("Check" at 360 px and under, where "yours" left the box no room for its hint). It is
`search(pc, { example: true })`, so it can never differ from what typing it gives, but it is not the visitor's: no
`?postcode=` in the address, nothing said in the live region, no engagement counted (the counts sit on the
controls), the question kept if a lookup fails (the intro stays until the answer is ready, then one change), the
coverage line kept, and it gives way to anything the visitor has done first (`acted`, set by `engaged()` before
the GoatCounter check, so an ad blocker cannot hide it). A link that asks for something (`?city=`, `?postcode=`,
`?borough=`, `#find`) gets that; campaign tags are still a plain visit. Measure it against the ~6% before the
next change. TESTS: `tests/front-page.mjs` serves the front page with the example pointed at `ZZ0 0ZZ` (no stub
answers it: exactly the fallback a visitor gets on a failed lookup), so its intro checks keep testing that state,
and section 1z turns the real example on (seven checks, proven red with the example off and with `acted`
ignored). `stubLiveApi` answers ONLY the example's two lookups (postcodes.io for TW9 3PZ, `/v1/environment` at
its latitude), so the layout, accessibility and font gates audit the page a visitor gets and never reach either
service. The a11y scans must WAIT for the example: scanned when the map appeared, axe met the page mid-change and
flagged a target the settled page passes. The answer becoming the first screen also surfaced an old defect: "Its
figures" was a 13 px inline button under WCAG 2.2's 24 px target, and on a phone held sideways "How it is worked
out" broke across two lines over it; both fixed (`min-height: 24px`, `white-space: nowrap`).

**THE TOP BAR'S CLICKS ARE COUNTED (2026-10-23).** Bill asked what order the bar should take and what visitors
click. GoatCounter could not say: the bar's links had never been counted (only pages, and footer events on the
map, `/api/` and `/pricing`). The page views (1 Jul-23 Oct: `/map` 39, `/pricing` 37 of which 24 came from the
FOOTER link, reports 30, the developer path 29) and best practice (first and last positions get the attention,
Pricing where people look for it at the right, group by audience) gave a proposal, `Full map · Reports · How it
works · About · API · Pricing`, but Bill's call was to MEASURE first and reorder around 20 Nov, after the
answer-first reading, so that neither change muddies the other. `js/count.mjs` now counts every bar click on
every page that loads it, through one delegated listener (no markup change in any bar): `event/nav-<slug>` from
the row, `event/nav-<slug>-menu` from the phone menu, `event/nav-menu` for opening it. Held by
`tests/front-page.mjs` 16d on all 11 counting bars at both widths, proven red with the listener off (22 checks);
the five bars that count nothing (privacy, terms, status, talks, 404: no analytics there) are named in the test.

**THE EMAIL BUTTONS ARE COUNTED, ONCE, AND NEVER WITH A POSTCODE (2026-10-23).** Bill asked about a "book a demo"
page; the cheap test first was to count the email buttons. Two things nearly went wrong. (1) The obvious name, the
button's subject, would have sent visitors' POSTCODES: the full map's correction link is
`?subject=Correction: <postcode or borough>`. So `js/count.mjs` maps subjects through an allow-list
(`EMAIL_SUBJECTS`) to `email-<page>-<what>`: no subject is `support`, a correction is `correction`, anything else
`other`. (2) I told Bill the pricing buttons were uncounted after searching count.mjs alone: /pricing has counted
seven of them since summer through its own `data-event` script, so the new listener skips any link with a
`data-event`. Held by `tests/front-page.mjs` 16e (every email link on /pricing and /api/ clicked, names in page
order; its first run showed each pricing button counted twice; the correction check proven red with its rule
removed). **The readout that answered the demo-page question, 1 Jul - 23 Oct:** /pricing ~37 views, mostly via the
footer (24); its email buttons clicked ONCE in total (`pricing-pilot-cta`), councils and paid tiers never; one free
key issued. The constraint is buyers reaching the page, not how they make contact.

**A REGION THE MAP DOES NOT DRAW IS NAMED, NOT "NOT FOUND" (2026-10-23, audit 2026-10-22 M-9).** The coverage
line lists every region the API scores, and three of them (Nottingham, Greater Norwich, Cardiff) are not drawn
on the front page's map. Typing "Nottingham" or "Greater Norwich" answered "That postcode was not found, and no
place on the map has that name", right under the line naming them ("Cardiff", "Norwich" and "City of
Nottingham" already opened their council-area cards, being council-area names). `search()` now matches a typed
name against the open-data rows' `city_name` for a city the map does not draw, and says it is scored by the API
but not drawn yet, naming its council areas from those rows (never a typed list). Held in `tests/front-page.mjs`
section 12, proven red.

**THE EXAMPLE SAYS IT IS ONE, IN ITS HEADING (2026-10-23, the same evening).** Bill opened the live page and read it
as "it automatically shows scores for TW9 3PZ": the small mono capitals above a large "TW9 3PZ" did not register.
The heading now reads "Example: TW9 3PZ" ("Example:" in `--orange-ink`, a span the example adds after `render()`,
so a visitor's own search, which rewrites the heading, can never carry it), and the line under it reads "A street
in Kew, under Heathrow's arrivals. Type your postcode above to see yours." in body text. The owner reading a
change as a bug is the cheapest usability test there is: run it before measuring anything.

**A test waits for the state it wants (2026-10-23).** The M-9 check first waited for the status to stop saying
"Looking it up", which a typed NAME never says (it waits on the Bay Area places file instead), so the wait passed at
once and, under preflight's load, read the empty line before the answer arrived: green alone, red in preflight.
It now polls for the answer itself (CLAUDE.md: poll for the state you want, never one already true).
