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
| `public-surfaces.md` | `/badge`, area pages, free tier, route throttles, signup verification (I17) |
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
- **Weekly audit**: the current one is `AUDIT_REPORT_2026-10-22.md`; suggest `/audit` when it is >7 days old.

## The product, in facts safe to repeat

- **Sky Score**: property noise and liveability data. The consumer site is the marketing engine; the B2B
  `/v1/score` API is the product. Pivoted May 2026 from "AI-powered" to data-first.
- **THE public coverage sentence, the only one to quote**: "97 council areas in 13 UK city regions, plus New
  York's 5 boroughs and 50 Bay Area cities (facts only)".
- **Surfaces**: `/v1/score` serves 14 cities LIVE, and 15 in source: the Bay Area's 50 cities, BY NAME only
  (`city=bayarea`), built 2026-10-22 and live once Bill's changeset deploys; the site keeps their facts
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
  are over **postcodes, not addresses**; never say **how often planes pass** except for airports that pass
  `coverage_verdict()`; prices appear on `/pricing` ONLY, and never a licence figure anywhere public (a
  `/talks/` handout broke the OGL and prices rules unseen for a month, fixed 2026-10-24: no gate reads /talks/). Say **AI** only as an event's
  name or where AI is NOT used; never how the product works or was built (Bill, 2026-10-24: not "AI slop").

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
  scores: rerun `build_area_pages.py --write` after any vintage roll.
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
- **A download's 200 is not the product**: test its magic bytes (FEMA's portal answered a missing county
  product with its page template, 2026-10-20; `docs/lessons/us-cities.md`).
- **A tile service's 404 is "not cached", never "quiet"**: measure which levels a cache holds before reading
  a tile as a reading (BTS's road cache stops at 12 though it lists 24). US shares (crime, road, flood) are
  not on the UK scales: each takes a US scale, LINEAR on its California anchor (`us_anchored_to_score`: 10 at
  zero, 5.0 at the anchor, 0 at double; Bill, 2026-10-18; `docs/lessons/us-cities.md`).
- **Pooled figures hide per-city optimism**: any fit must hold per city (no city may read quieter than its
  yardstick).
- **A parity claim is a claim about a holder: read it, never retype it.** The Bay Area's transport bands were
  typed (50/25/10) and called "the UK's" (75/50/25) to Bill; they are now parsed from `build_borough_bands.py`.
  Likewise an anchor counts only what its unit can (the crime anchor: agencies policing residents, 21.39).

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
- **The brand links home on every page** (`tests/test_brand_links_home.py` finds them). **"Have your say" links come
  only from `HAVE_YOUR_SAY`** (verified live; add an airport only after checking its pages).
- **Focus rings use `--focus: #d35a12`**, never the brand orange `#f27d26` (fails 3:1).
- **Analytics only through `js/count.mjs`**; never GoatCounter's own script (it sends the query string).
  Campaign tags are an allow-list (`CAMPAIGN_KEYS`). The top bar's clicks are counted there too (`nav-<slug>`, `-menu` from the
  phone menu): reorder the bar from them, not from a guess (Bill, 2026-10-23: read them ~20 Nov). Email buttons
  too (`email-<page>-<what>`): the what comes from an ALLOW-LIST of our subjects, never the link (the map's
  correction subject holds a postcode), and a link with its own `data-event` is skipped (counted once). The About
  page's film and prototype too (`about-film`, `about-prototype`), from `WATCHED_LINKS`, exact destinations only.
- **`sw.js`**: `SHELL_ASSETS` is atomic (`cache.addAll`), so a precached file missing at the origin stops the
  worker installing everywhere; `/data/` is network-first; `/badge` passes through; every `no-cache` upload in
  the Makefile must be network-first (`tests/test_sw_no_cache_prefixes.py`).
- **The phone footer links the same places as the desktop footer**: add a link to both or neither.
- **No street basemap on the live map** (decided; the OS trial lives on the front page only).
- **`d3.v7.min.js` sits at the foot of `<body>` with a matching preload**; `defer` is wrong here.
- **The top bar folds behind a Menu POPOVER below 680 px** (no script: privacy/terms allow none, area pages carry
  none); every bar is held at 390 and 1366 wide by `tests/front-page.mjs` 16d. A new bar needs the same markup.
- **The front page opens on an example answer** (`#ans-example`, `search(pc, { example: true })`): never in the
  address, never engagement, silent on failure. `stubLiveApi` answers its two lookups; scans wait for it.

### Gates and verification
- **Run preflight before every commit**: `sh scripts/preflight.sh` (== `npm run preflight`). Read the EXIT
  CODE; never pipe it (`| tail` is always 0). `INCONCLUSIVE` and `PASS (INCOMPLETE ...)` are not PASS.
  Change what blocks in `scripts/preflight.sh`, not in the skill.
- **Count `check` / `advise` / `net_check` call sites in `scripts/preflight.sh`**; never trust a count in prose.
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
  paths, `/aws/lambda/*`), or Git Bash rewrites it to a Windows path.
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
- Look up D3, AWS SDK and SAM APIs with **context7** before using unfamiliar ones; use **security-guidance**
  on Lambda / API Gateway edits and **frontend-design** on UI changes in `index.html`.

## Build and deploy (detail: `docs/lessons/deploy.md`)

- **Prefer make targets**: `fonts-deploy`, `data-deploy`, `web-deploy` (index.html -> `map/index.html`,
  privacy, pricing, changes, terms, `api/`, `js/`), `home-deploy` (front page, `/reports/`), `pwa-deploy`,
  `demo-deploy`, `prototype-deploy`, `meta-deploy`, `area-deploy`, `open-data-deploy`, `bay-area-deploy`,
  plus standalone `talks-deploy` and `deeplinks-deploy` (refuses placeholders).
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
