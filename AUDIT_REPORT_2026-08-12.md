# Audit Report, Sky Score — 2026-08-12

**Scope:** 56 Python files, 9 deployed HTML pages, `index.html` (11,466 lines),
8 Lambdas, 25 `.mjs` suites, 16 blocking preflight gates.
**Since the last full audit** (2026-08-03): **163 commits** — methodology v3.6
(transport), v3.7 (healthcare), v3.8 (per-airport aircraft scale), six then two
more city-regions onto the site, borough fill layers derived for all nine,
neighbourhood area names, a district containment floor, and the DEFRA raster
tier extended to seven more airports.

**Method:** four parallel dimension agents — security, backend code, frontend +
accessibility, and gate/claim honesty — each required to trace a finding to a
concrete failure before reporting it. **Every finding acted on below was
re-verified by hand** before it was fixed, per the standing rule that a
confident agent report is not evidence. That mattered: one agent's headline
number did not reproduce (see A-0812-U1), and one of my own corrections was
wrong on first attempt (99 vs 94 boroughs) and caught by re-deriving it from
`LAD_TO_BOROUGH`.

---

## Summary

| | Count |
|---|---|
| Critical, verified and **FIXED** | 4 |
| Critical, verified, **open** | 3 |
| Important, **FIXED** | 6 |
| Important, **open** | 14 |
| Minor / recorded | 9 |
| Verified clean | see §6 |

**The through-line: nothing found was individually broken.** The substring
borough lookup was correct for spelling drift. The `-0.4` transport ladder is
correct when a station list exists. `layer-honesty.mjs` is correct when
`borough-extra.json` parses. Each failed only in a *relationship* — with a
neighbouring key, a missing generator, or its own expectation source. That is
why 495 passing tests coexisted with four confident wrong numbers.

---

## 1. Critical — verified and fixed today

### A-0812-1 — North West Leicestershire was served Leicester's data
`index.html:8041` · **FIXED**

`getExtraData()` returned on the first *substring* match, and `Leicester` is key
#1 in the leicester block, so `'north west leicestershire'.includes('leicester')`
won. The district rendered:

| Shown | Actual |
|---|---|
| crime **110.0**/1,000 | 59.2 |
| schools badge P8 **0.14** | no P8 published |
| transport **moderate** | poor |
| healthcare **good** | moderate |

Fixed with an exact-match pass ahead of the substring pass. The substring pass is
**kept** — it is load-bearing for ONS/Land-Registry spelling drift
(`City of Westminster` ↔ `Westminster`), it just must not outrank an exact name.
Verified: 0 of 91 boroughs mis-resolve after the fix (was 1), and the drift
fallback still resolves.

### A-0812-2 — every neighbourhood outside London carried a phantom −0.4
`index.html:7146` · **FIXED**

`build_city_frontend_block.py` emits `const <CITY>_STATIONS = [];` for every
generated city, so `stations` was empty for **all nine**, `minStDist` stayed
`Infinity`, and `Infinity > 5` applied `transportAdj = -0.4` to every
neighbourhood in the ranking list. The penalty's real meaning was "nobody has
built this file yet" — absence rendered as a measurement, in the penalising
direction. `borough-score-parity.mjs` compares *borough* scores and is
structurally blind to a neighbourhood-level adjustment.

Fixed: an empty list now yields **no adjustment**. Verified London is identical
at every distance. Transport remains a measured liveability input via NaPTAN
(v3.6), so these cities are not missing the signal — only this second, finer one.

### A-0812-3 — NYC sold-price links pointed at English villages
`index.html:8578` · **FIXED** · *reported by Bill as "a dead link"*

`renderSoldPrices()` had no city branch, though `buildPropertyLinks()` fifty
lines below has had one all along. On NYC the fallback emitted a Rightmove **UK**
link built from a US ZIP. Rightmove resolves five digits as a UK place id and
serves a real page for somewhere else:

- `10001` (Manhattan) → *House Prices in **Fishpond***, Dorset
- `11201` (Brooklyn) → *House Prices in **Great Fransham***, Norfolk
- `10451` (Bronx) → *House Prices in **Gaineys Well***

Not a dead link — a confident wrong one, with no error anywhere. NYC now gets
Redfin + NYC ACRIS; the UK keeps Rightmove + Land Registry.

### A-0812-4 — the public API demo had been dead for five days
`score-demo/status.html:322` · **FIXED (cause) + quota restored**

The "Try the API" form returned `{"message":"Limit Exceeded"}` from **2026-08-07
to 2026-08-12**. Cause: this status page polled **4 key-gated endpoints every 5
minutes on the shared public demo key** — 48 requests/hour per open tab,
1,152/day, draining the 2,000/month `SkyScoreDemoTier` plan in **1.7 days**.

Measured consumption: 698 (3 Aug), 414 (4 Aug), 687 (6 Aug), 97 (7 Aug) → 0
remaining, then five days of zeros because every request 429'd.

The page's own comment already reasoned about "exhaustion time" and re-tuned the
interval when the quota moved — treating the symptom. Any interval leaves an
abandoned tab spending a customer-facing consumable.

Fixed structurally: **authenticated only on the first sweep of a page load**;
every automatic sweep afterwards is keyless. API Gateway does not meter a request
that fails authorisation, so an idle tab now costs nothing, and a `403` is still
a real liveness signal — it proves the route and its authorizer are alive
(verified: keyless `/v1/score` → `403`). Cost model: 1,152/day per abandoned tab
→ 4 per genuine visitor. Quota reset; demo verified returning `200`.

**This is the second instance of the same class** — see
`feedback-gate-blocked-by-shared-quota`. First time a gate was blocked by our own
CI spending a shared key; this time a status page spent the funnel's key.

---

## 2. Critical — verified, still open

### A-0812-U1 — `/v1/environment` computes aircraft noise with London geometry for every UK coordinate
`backend/lambdas/score/app.py:6136` · **OPEN**

The call is literally `calc_postcode_quiet(lat, lon, 'london', postcode_clean)`
regardless of where the coordinate is. The endpoint is **unauthenticated** and is
what the public browser extension renders as `10 − quiet`.

**Verification status: code confirmed, live impact NOT reproduced.** The
reporting agent measured `aircraftQuietEstimated: 10.0` for M22 5PR beside
Manchester Airport against `2.0` under `'manchester'`. My own live call for that
coordinate returned `"No UK postcode found near those coordinates"`, and a
Heathrow-area control returned `aircraftQuietEstimated: null`. So the hardcode is
real and the consequence is plausible, but the specific figures are unconfirmed.
**Reproduce properly before fixing** — pass a coordinate that reverse-geocodes,
and compare `'london'` against the resolved city.

### A-0812-U2 — three WCAG contrast failures, one invisible on every phone
`index.html:2277`, `:108`, `:1613` · **OPEN**

1. **Mobile legend headings at 1.19:1.** `@media (max-width:900px)` paints the
   legend pill near-black; the author wrote an override at `:2289` to whiten the
   headings, but each heading carries an **inline** `style="…color: var(--dark)"`
   (`:3104`, `:3124`, `:3144`), and inline style beats any selector. Composited:
   `#141414` on `#252424` = **1.19:1**. On any phone the swatches are visible and
   the heading saying which dataset they belong to is not. `applyCityChrome()`
   rewrites these with `textContent`, so it never clears the inline colour.
2. **`--orange` as text: 2.60:1 on sidebar, 2.11:1 over the map.** ~14
   always-rendered occurrences including the entire Noise column of the 128-row
   ranking table. **The darkened variant already exists** — `scoreTextColor()`
   (`:9519`) returns AA-clearing values and was applied to the score number and
   to `--yellow`, never to `--orange`.
3. **Every metric-card value fails on the card's own background.** `--orange`
   2.11:1, `--yellow` 3.84:1, `--green` 4.23:1 on `.metric-card`'s `--bg`. The
   2026-08-03 `--yellow` correction computed 4.73:1 against `#fafaf9` and its
   comment claims "all seven uses are on light backgrounds" — it did not account
   for the darker card. The ROAD NOISE / FLOOD / AIR QUALITY readouts are the
   least legible text in the panel.

### A-0812-U3 — road noise has no plausibility ceiling, and a dead 60-line duplicate holds a third copy
`backend/lambdas/score/app.py:3901` · **OPEN**

`lden_from_row` gained `_RASTER_MAX_PLAUSIBLE_DB` today; its explicit mirror
`road_lden_from_row` did not, and both read the same row. A `+3.4e38` sentinel —
the sign the code's own comment says the London region export uses — passes
`>= 40.0` and would publish `roadNoiseLdenDb: 3.4e+38`. Separately
`_lookup_road_lden` (60 lines, its own 2048-entry LRU) has **zero call sites**
and holds a third copy of the floor. Three ranges exist for one raster: loader
`[30,100]`, Lambda `[40,120]`, dataset builder `[40,100]`.

---

## 3. Important — fixed today

| ID | Finding | File |
|---|---|---|
| A-0812-5 | **`layer-honesty.mjs` passed with zero layer data.** Expected count came from `getExtraData()` — the same lookup the renderer uses — so an unparseable `borough-extra.json` collapsed both sides to 0 and printed "Every layer paints exactly the boroughs that hold a reading". It is the **only** gate covering roadNoise/flood/airQuality. Floor added; **red proven** by serving the file as `200` + non-JSON. | `tests/layer-honesty.mjs` |
| A-0812-6 | **`city-switch.mjs` passed on a city with no map.** `expected` is derived by fetching the city's own boundary sources *in the page*, and `loadCityBoundaries()` swallows a bad source and returns `[]` — both sides go to 0. This is exactly the gitignore trap CLAUDE.md names as the #1 hazard when adding a city. Floor added. | `tests/city-switch.mjs` |
| A-0812-7 | **`api/index.html` told integrators the raster tier was bypassed and `quietResolution` "never" returns `raster`** — live since 2026-08-06. Sample response advertised `methodologyVersion 3.5` against a live `3.8`. *The fix had inverted into the defect*: this note was **added** to close finding A-0803-10. | `api/index.html:233` |
| A-0812-8 | **`METHODOLOGY.md` asserted "`METHODOLOGY_VERSION` is still `3.5`, and that is correct"** against a live `3.8`; §11 published default weights `30/25/20/25` against the real `38/31/0/31`. This is the canonical B2B/diligence document. | `METHODOLOGY.md:3, 708, 1508` |
| A-0812-9 | **Coverage undersold by 10 city-regions** on both selling pages, and the **£2,500 pilot was scoped in writing to "London and New York"**. | `api/index.html:224`, `pricing.html:231, 264` |
| A-0812-10 | **`LICENSING.md` claimed OSM is "a transient passthrough… nothing is stored".** `backend/lambdas/nhs/london_healthcare.json` is a **3,224-element, 458 KB OSM extract bundled in the deployed Lambda**, read on the hot path. The document's own re-open trigger ("if OSM output is ever cached, stored") had fired and was never actioned. Corrected by strike-through, with the live share-alike question stated rather than resolved — that needs a solicitor. **Five scoring inputs were also absent from every licence table**: NaPTAN (0.25 of liveability), NHS ODS (0.10), EA RoFRS, DEFRA background maps, OurAirports. And `borough-extra.json` is no longer described as "own editorial work" — nearly every field in it is third-party derived since 2026-08-11. | `LICENSING.md:28, 82` |

---

## 4. Important — open

**Security**

- **A-0812-11 — the public demo key is authorised on `/v1/score/batch`.** One
  metered request returns 100 scores, so the 2,000/month demo plan is worth
  200,000 scores — 20× the free tier's stated 10,000 ceiling. The template
  comment ("the demo form only ever makes single calls") is an assumption about
  the client, not a control on the key. Fix: per-method throttle map, or a
  route-scoped plan. `backend/template.yaml:491`
- **A-0812-12 — no reserved concurrency anywhere + an unauthenticated 45s proxy.**
  `/nhs`, `/transport`, `/sold-prices` carry no key and no per-method throttle,
  inheriting 50 RPS. A non-London coordinate takes the live Overpass path
  (seconds per call), so a single unauthenticated client can drive concurrency to
  the account limit and throttle the paid `/v1/score`. `backend/template.yaml:208`
- **A-0812-13 — `/v1/changes` is unauthenticated and returns 116 KB.** ~460×
  amplification on a 250-byte GET; at the stage ceiling that is ~15 TB/month of
  billed egress from one client. `backend/template.yaml:407`
- **A-0812-14 — `/favourites` accepts unauthenticated writes with no aggregate
  cap.** `X-Device-Token` is self-issued, so it is a capability, not
  authentication. Per-field caps exist; per-token and per-client do not.
- **A-0812-15 — `/v1/regions` is not key-gated, and the code says it is.**
  Verified `200` with no key. `app.py:5956` states it "carries
  `ApiKeyRequired: true`"; CLAUDE.md repeats it. Low data sensitivity — the
  problem is a documented control that does not exist.
- **A-0812-16 — the extension transmits more than its stated privacy claim.**
  `extract.js:18` promises "the only value that leaves the browser is a rounded
  coordinate pair"; `background.js:120` sends full-precision lat/lon (the
  `toFixed(3)` applies only to the local cache key) plus the exact postcode.
  One-line fix, or a corrected claim.

**Correctness and gates**

- **A-0812-17 — `AIRCRAFT_QUIET_METHODOLOGY = '3.6'`** under a comment reading
  "Must match `METHODOLOGY_VERSION`", which is `'3.8'`. Three unlinked hand-kept
  copies; no gate touches any. **Benign today** (the ramp has not changed) — and
  the dangerous move is the *tidy* one: bumping it to `'3.8'` without
  regenerating silently switches the DEFRA tier off for 42,691 postcodes on the
  site while `/v1/score` keeps answering from the raster.
- **A-0812-18 — the blocking `aircraft bands == geometry` gate never checks
  London or NYC.** `AIRPORTS` excludes both, so 38 of 99 boroughs are unchecked —
  including London's `impact`, the hand-assigned Heathrow calibration the whole
  v3.8 ladder is anchored on. Makes CLAUDE.md's "every field of the eight is
  script-derived and independently verified" false.
- **A-0812-19 — `check_score_sanity.py` probes London only.** All 16 probes are
  London postcodes; `/v1/score` serves 13 cities with postcode-level scoring
  un-gated everywhere. The "only stage that can catch a DATA defect" covers 1 of
  13. Its `noiseImpactBand` stage can also assert over **zero** comparisons and
  print PASS.
- **A-0812-20 — `build_hpi_prices.py --check` narrows itself twice.**
  `_in_registry()` silently drops any city with no `CITY_LADS` entry, and its
  `except Exception` fallback returns `("london","manchester")` — so if reading
  the Lambda ever raises, the only gate that can catch a partial vintage roll
  checks 2 of 13 cities and prints PASS.
- **A-0812-21 — `load_defra_air_quality.py` checkpoints without flushing.**
  `CHECKPOINT.write_text(str(idx))` fires on `idx % 1000 == 0` with no
  `not batch` guard while `BATCH_SIZE` is 25, so up to 24 buffered postcodes are
  recorded done before reaching DynamoDB and are skipped forever on resume.
  `load_nspl.py` documents at length why that guard is load-bearing. This loader
  is known to die mid-run.
- **A-0812-22 — `terms.html` makes attribution binding on a field two endpoints
  do not return.** "**Every** API response includes a `sources` array" —
  `/v1/regions` and `/v1/environment` do not. `/v1/environment` is the
  unauthenticated endpoint the public extension consumes.
- **A-0812-23 — `chat`'s grounding whitelist spans `'0'`–`'10'`**, i.e. every
  component and composite value, so a hallucinated "Liveability 8 out of 10" over
  a retrieved 2.6 ships with `grounded: true`.
- **A-0812-24 — `check_deploy_drift.sh` omits all of `data/`** while its header
  claims "every publicly-served file". The one deploy target whose staleness
  changes published numbers is the one the drift check cannot see.

---

## 5. Minor

- `npm run lint:css` has **never worked** — stylelint is pointed at `index.html`
  with no `customSyntax`, so it parses HTML as CSS and dies on the leading `<`.
  Nothing depended on it (stylelint is not in preflight), which is why it went
  unnoticed. Confirmed pre-existing against the committed lockfile.
- **5 high-severity npm advisories — FIXED**, and worth stating what they were:
  all five were devDependencies of the lint toolchain. The project has **zero
  production npm dependencies**, so none was ever reachable by a visitor. The
  "5 high" headline overstated the exposure considerably.
- `chat/app.py:200` has no top-level exception guard, unlike every other Lambda;
  `POST /v1/chat` with a non-object body returns a bare 502 with no CORS headers.
- `OPTIONS /v1/environment` requires an API key while the GET it preflights does
  not — backwards, and it will break the extension the moment a custom header is
  added.
- Boundary GeoJSON falls back to **unpinned third-party GitHub branches**; a push
  to either repo changes the geometry the map draws.
- `signup` 503 echoes the raw AWS error code.
- Two pytest files place `if __name__ == '__main__'` **mid-file**, so running
  them directly executes 141/162 and 45/60 tests and prints `OK`.
- CI never installs PyYAML, so the OpenAPI drift check `skipTest`s on every run.
- `boroughDataNotice()` is a `role="status"` injected with its text already
  present, so the one message telling a user four score inputs failed to load is
  visible but never announced.

---

## 6. Verified clean

Recorded so the coverage is legible rather than assumed.

**Security:** no secrets in any tracked file or in history (`git log --all -- .env`
empty); EPC token correctly flows through a `NoEcho` SAM parameter. Every
DynamoDB call uses parameterised keys and static projections — no dynamic filter
expressions anywhere. Overpass QL interpolates only `float()`-converted,
range-checked coordinates. `index.html` escapes consistently via `escapeHtml` and
gates every dynamic `href` through `safeUrl`, including crowd-edited OSM fields;
the extension panel uses `createElement` + `textContent` exclusively, zero
`innerHTML`. All 9 pages carry CSP with `frame-ancestors 'none'`. Extension
permissions are minimal, with the rents dataset deliberately served over the
message channel rather than `web_accessible_resources`. No SSRF reachable. No
stack traces, ARNs or table names in any response body.

**Backend:** `ddb_write.guarded_put` is correctly bounded with a fatal-code fast
path, proven red both ways. No bare excepts. Mutable defaults, float equality and
band-boundary off-by-ones clean throughout the scoring engine. `preflight.sh`
never pipes a blocking check — the 2026-07-27 false green cannot recur there.

**Frontend:** service worker `SHELL_ASSETS` holds nothing that could 404
independently of `make data-deploy`; the deliberate exclusions are correct.
Performance clean — no `mousemove` handlers, the only `scroll` listener is
passive and bound once, `resize` debounced, d3 transitions generation-tokened.
The combobox is a correct APG implementation.

---

## 7. Coverage holes — what no gate watches

- **`sw.js` `SHELL_ASSETS` vs `CITY_DATA` vs `data-deploy`.** Nothing asserts a
  city's boundary file is in all three. `cache.addAll()` is atomic, so a mismatch
  stops the service worker installing **for every city**.
- **`--check-names` checks the override dict, not the 485 shipped labels.** A
  hand-edit inside the markers ships unchecked, and `preflight.sh` overstates it
  as "asserts every label".
- **Neighbourhood prices.** 485 medians rendered from PPD, re-derived by nothing.
- **NYC `avgPrice` / `trend`** — excluded from the HPI gate by design, checked by
  nothing else.
- **`/v1/environment`** has no handler test and no schema gate.
- **`a11y-source.mjs` scans one 1440px viewport, initial state only** — so the
  mobile layout (including A-0812-U2's 1.19:1 legend), and the ~400 lines
  `updateSidebar()` injects, have never been scanned. It also filters to
  `critical|serious`, so `heading-order`, `landmark-one-main` and `region` **cannot
  fail it**, and it never reads `results.incomplete` — which is where axe puts
  colour-contrast it could not resolve, i.e. the whole map-overlay chrome.
- **`refresh_crime_from_ons.py --check`, `build_progress8.py --check`,
  `build_borough_bands.py --check`** all exist and are in **no** gate.
