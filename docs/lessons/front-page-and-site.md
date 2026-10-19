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
> - **"Cubitt33" stays on `privacy.html` and `terms.html` ONLY.** Bill asked for it off the
>   site for now; the legal pages must still name the company (trading disclosures, and
>   the controller in the privacy notice). Footers say "All figures from official public
>   data" - not "open government data", because the UK routes come from the AIP, public
>   but not openly licensed.

