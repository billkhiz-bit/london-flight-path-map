# Handover — resuming on another machine

**Written 2026-08-12; §1 rewritten 2026-09-01.** Read this first if you are
picking the repo up on a laptop, or starting a fresh session on this desktop.

**As of 2026-09-01 there is a large UNCOMMITTED, UNDEPLOYED wave in the
working tree.** §1 is the whole of it.

---

## 1. PICK UP HERE - 2026-09-01, a big uncommitted wave. READ THIS WHOLE SECTION FIRST.

**NOTHING IS COMMITTED AND NOTHING IS DEPLOYED.** The working tree holds
13 modified files and 3 new ones. Every published number below changed in the
SOURCE only; the live site and the live API still serve the old figures. Do not
start new work until the four steps in §1.1 are done, because two of them are
blocking gates that are currently RED by construction.

### 1.1 Steps 1-3 are DONE. **ONLY THE DEPLOY IS LEFT.**

1. ~~Rebuild the 99 static area pages.~~ **DONE** - `python
   scripts/build_area_pages.py --write` wrote 99 pages + index + sitemap
   against the corrected data.
2. ~~Run the full gate.~~ **DONE** - `sh scripts/preflight.sh`, exit code read
   directly and never piped. **RESULT: green except two - `area pages match the live API`, which is red until step 4 by construction, and `UK cities get UK panel content`, a transient live-TfL timeout that passes standalone (verified immediately after)**.
3. ~~Commit.~~ **DONE**, staged file by file, no `git add -A`.
4. **DEPLOY BOTH HALVES, BACKEND FIRST. THIS IS THE ONLY STEP LEFT, AND IT HAS
   NOT BEEN DONE** (the 1 Sep session was explicitly asked not to deploy). SAM
   for the Lambda, then `make web-deploy-all` + a CloudFront invalidation
   (`export MSYS_NO_PATHCONV=1` FIRST - see the warning block in CLAUDE.md).
   Backend-then-web is the order the aircraft-raster runbook already uses: it
   flips `/v1/score` while the site still shows the old numbers, which is the
   safe direction. Deploying the site first shows users figures the API cannot
   reproduce.

**Two stages are red until step 4 runs, and that is CORRECT.** `area pages
match the live API` and `site == /v1/score` compare the tree against the
DEPLOYED tier, which still serves the old numbers. They are the normal state
mid-wave, not a defect - and they are the stages that will confirm the deploy
worked.

### 1.2 What changed - four published-number corrections, all with evidence

Every one of these reproduces a figure the 31 August audit computed BY HAND,
which is the strongest evidence available that the fix is the right one.

| | Fix | Reproduced |
|---|---|---|
| **C1** | The aircraft near-field floor was a **DISC** compared against runway-shaped contours. It now tests the borough against the >=55 dB cells in that airport's own DEFRA GeoTIFF | Rushcliffe **10.43 km2, max 65.6 dB**; North Tyneside **0.32 / 57.1**; Solihull **9.21** - all three to 2 dp. Rushcliffe scores **balanced 5.0 -> 3.4, quietlife 6.4 -> 4.0**, exactly the audit's prediction |
| **C2** | Neighbourhood medians included HM Land Registry **Category B**. Filtered to category A, the basis HMLR and the UK HPI use - and the basis `avgPrice` beside it was already on | **TS26 Hartlepool 125k -> 175k (+40.0%)**, WV2 150k -> 190k, LS2 184k -> 150k. All three match the audit exactly |
| **F38** | Borough bands were weighted by **TERMINATED** postcodes | **915,867 excluded, 578,940 live remain - 38.7%**, against the audit's hand count of 39.2% |
| **I3** | DEFRA road `0.0` means "surveyed, below the lowest band" and was dropped from the SHARE's own denominator, so the share was computed among the noisier postcodes only | `roadNoiseCoverage` reaches **100.0** in boroughs that read 92-99% before |

**Combined effect: 811 fields updated across BOTH holders**
(`data/borough-extra.json` and the Lambda), plus 3 aircraft bands.

**Three bands moved and one of them moved the OPTIMISTIC way**, which is the one
to check if you are suspicious: Knowsley `moderate -> low`. It is not the disc's
error in reverse - Knowsley's boundary is **0.76 km clear** of the nearest
>=55 dB cell, measured. Rushcliffe and North Tyneside both moved `low ->
moderate`.

**Teesside and Cardiff keep the disc**, and that is deliberate and recorded in
the data file: MME and CWL are **not mapped by DEFRA Round 4 at all**, so there
is no contour to test against. "No contour published" and "not measured here"
are different things and the file says which.

### 1.3 What changed - correctness, with no published-number effect

- **I2** 34 provenance strings said `May 2026 vintage` while the Lambda has
  served **June** figures since the 25 August roll. Corrected, and
  `build_hpi_prices.py --check` now asserts the PROSE names the vintage it
  verified the NUMBERS against. Proven red on one stale string; restore
  sha256-verified.
- **I18** `score_bulk.py` - the Enterprise deliverable - crashed on
  `app._LOCAL_POSTCODE_SERVED` on **every run since 22 August**. Fixed, and the
  silent half with it: attribution is thread-local, the workers hold it and the
  main thread writes the `.sources.txt`, so the OGL file credited postcodes.io
  for lookups ONS served. Workers now report it and main aggregates.
  **The suite passed throughout** because its `_FakeApp` stub still carried the
  attribute the Lambda had deleted - a stale stub is a stale claim about an
  interface, and reads exactly like a correct one.
- **I28** City of London's crime rate is Sky Score's own estimate and
  `liveResolution` still said `measured`. `crimeEstimated` was published, read by
  the `sources` line, and read by NOTHING else. **The wording needed two passes**:
  demoting the input made the existing "partial" string claim the weight was
  redistributed, which is false - the estimate still scores. It now names the
  estimate instead. `partial - 2/4 inputs measured; the crime rate is a Sky Score
  estimate carrying its full weight`.
- **I29** A caller could not opt into `env` weights - a five-key set failed a
  set-equality check, fell back to `balanced`, and said nothing. `env` is now an
  optional fifth key, and a rejected override returns **400 with a reason**
  instead of scoring under a model the caller did not ask for. There is a
  round-trip test against `PERSONAS['balanced']` rather than a five-key literal,
  so a sixth component cannot repeat this.
- **I31** EPC `extract_rows` returned `[]` for both "no certificates here" and
  "we cannot read this envelope", so one upstream rename would have answered
  **"no certificates on record" for every postcode in the country**, with a 200.
  Three-way now, and `pagination.totalRecords` - already forwarded to callers -
  is finally READ, so a payload claiming 42 certificates and returning none is
  refused. 3 tests.
- **I33** The favourites list rendered **"No saved locations yet"** on an API
  failure, and filed every non-NYC favourite under a heading reading **"London"**.
  Both fixed; grouping is per-city from the registry.
- **I34** The tooltip said "four components" over five; "Four factors" is now
  counted from what the panel will actually render (3, 4 or 5 depending on the
  borough's input floors); the ranking header is built from the persona's own
  weights, so it can no longer sum to 82-86%.

### 1.4 Accessibility: D5 and D7 were the visible tip of 46

`tests/panel-contrast.mjs` is **new and blocking-worthy** (not yet wired into
`preflight.sh` - see §1.6). It opens the borough panel and the area panel at two
viewports and measures the effective contrast of every visible text node itself.

**It found 46 nodes below AA, not the 2 the audit named**, and all 46 are now
fixed. The repeat offenders were the `↗` link arrow at **2.11:1** (seven per
panel), the live line-status rows, and the rating badges at 4.44:1.

**Why the existing gate could not see any of it, measured:**

- **axe reported `colour-contrast` as INCOMPLETE for 66 nodes and as violations
  for 0.** `incomplete` is axe declining to answer because it could not resolve
  an effective background, and a gate reading `violations` counts every one of
  those as a pass.
- **`a11y-source.mjs`'s "borough selected" state opens the AREA panel.** It
  clicks `.borough-list-item, .rank-table tbody tr`; the first survives in CSS
  only (its own comment says so) and the second opens `Cheam (SM3 8BD)`. The
  borough panel - where D5, D7 and D8 all live - had never been opened.
  **So §3b of the audit is INVERTED**: it says the panel "has never been scanned
  by anything", when the truth is that it HAS been scanned since 24 August and
  the thing scanned was a different panel. Ninth instance of a recorded finding
  being the inverse of the code.
- **The new gate reproduced that same defect inside itself on the first run.**
  Its borough route fell back to a ranking row when `BOROUGH_DATA` turned out not
  to be a global, so both states measured the same panel while the report named
  two. **Identical node counts across two states was the tell** (204/204). It now
  drives `selectBoroughByName`, fails rather than falls back, and asserts the
  panel title matches the state it claims.

The fix used tokens that **already existed**: `--orange-text` / `--green-text` /
`--yellow-text` were added on 2026-08-12 with a comment saying "now they are
tokens so the next use inherits the fix instead of repeating the defect". The
call sites never adopted them.

**D8 is half done.** `document.title` never changed - measured on both viewports
with a borough selected - and now names the subject through one holder,
`setPanelSubject()`. **The mobile half is NOT done**: at 390px the panel's `<h2>`
is `display: none` because `.sidebar-header` is hidden in `data-mview='search'`,
and I could not reach the tabbed *analysis* view from the console
(`setMobileView` is not a global). **Do not fix this from the description - reach
the state first**, the way a user does.

### 1.5 Still open

**I19, I25, I17, I26/F8 and F26 were all on this list and are now CLOSED** -
see §1.6a and the 2026-09-01 entries in `CHANGELOG.md`. What is left is the
design cluster and one undiagnosed divergence.

**Two things a future session should pick up from the I17 work rather than
re-derive.** The throttle guard (`backend/tests/test_route_throttles.py`) found
**five more unauthenticated routes on the 50 RPS stage ceiling** - `/nhs`,
`/sold-prices`, `/transport`, `/v1/regions`, `/v1/changes` - and they are LISTED
rather than throttled, because three of them are called by the consumer site on
every postcode lookup and a limit set too low 429s real visitors. **Pick those
numbers from measured traffic, not by eye.** And `FavouritesTable` still has no
TTL: adding one deletes user data on a schedule, so it is Bill's decision, not
a fix to slip into a throttling change.

- **D9** four visual systems across nine page types (narrowed slightly by the
  token work above, not closed). **D11** dark mode exists on the area pages only
  and declares no `color-scheme`. (**D10 is CLOSED** - and was a regression: the
  base rule had met WCAG 2.5.8 since 2026-08-23 and the tabbed mobile view
  overrode it back to 14px, which became the WEB default on 2026-08-28.)
- **The N1 7SX site/API divergence** (§5b). Still undiagnosed, and the obvious
  explanation is still wrong - identify the differing RAW value before writing
  any fix.

### 1.6 The three gates are WIRED IN - done 2026-09-01

All three are in `scripts/preflight.sh`, and **each was run before being wired**,
which is what turned up the rest of the day's work.

| Stage | Kind | Result on this tree |
|---|---|---|
| `panel contrast, borough (AA)` | **blocking** `check` | 134 nodes at desktop, 87 at phone, 0 below AA |
| `panel contrast, area (AA)` | **blocking** `net_check` | 174-204 nodes at desktop, 127-143 at phone, 0 below AA |
| `neighbourhood medians == PPD` | advisory | **481 medians across 9 cities, 0 differ** - the C2 fix verified end to end |
| `aircraft footprint == DEFRA` | advisory | 48 boroughs across 8 cities reproduce from the GeoTIFFs |

**The contrast gate is TWO stages, and finding out why is the useful part.** It
reds intermittently, and "flaky" was not the diagnosis. It allowed a FIXED
1200 ms settle before asking whether the panel had rendered; measured warm, the
area panel renders **113-147 ms** after the click, but on a cold run the same
sequence overran the budget and it printed `could not open` against a tree whose
panel was fine. It polls for the state now, bounded at 15 s, and a state that
never opens still reds - proven by breaking the selector.

**Re-run with every offsite request aborted, the reason appeared**: the borough
panel measures 134 and 87 nodes, and **both area states fail with the exact
signature of the intermittent red**. The area panel is reached by a ranking-row
click that runs `triggerSearch()`, which resolves the district through
`api.postcodes.io`. So a stage documented as needing no network needed one for
half of what it measured. The honest fix was not an in-gate skip - that is
"nothing wrong here" meaning "I could not look" - but `--only=<state>` and two
preflight stages, reusing the `check` / `net_check` split that already prints a
skipped stage in its own position and marks the run INCOMPLETE.

**`--skip-e2e` now skips FIVE stages, not four**, and CLAUDE.md says so. Count
the `net_check` call sites; do not trust the sentence.

### 1.6a Also closed on 2026-09-01, after the wave above

- **I25 - METHODOLOGY.md was a SIXTH free-tier mirror and was in no list.** It
  advertised **100 requests/month against an enforced 10,000**, 1/s sustained
  against 2, and explained the batch multiplier **removed on 2026-08-21** - so
  its stated reason for the 10,000-score ceiling was the inverse of the
  mechanism producing it. It is now in `template.yaml`'s list and in
  `FreeTierQuotaDriftTests`, read **by section**, because the file also quotes a
  third party's quota (AviationStack, "1000 req/month") that must not be forced
  to match ours; `_page` fails if the heading moves rather than returning an
  empty string. **Two gate defects surfaced on the first run**: the quota
  pattern read "5 requests per second burst" as a monthly quota of 5 - a rate is
  not a quota, and no other mirror spells a rate out in words - and **the
  per-second rates were never asserted against the plan at all**, which is
  exactly what let the wrong sustained rate survive. Both directions proven red.
- **I19 - one tram stop published as five stations.** Measured first: **170 of
  943 published entries were a place already listed, 166 of them South
  Yorkshire**, whose Supertram names each DIRECTION as its own NaPTAN node
  ("Attercliffe", "... From City", "... To City", "... Platform to City",
  "... Platform to Meadowhall"). South Yorkshire **268 -> 102**, the product
  **1,651 -> 1,415**. Separately **806 retired nodes** were published as current
  because `Status` was never read. The strip is anchored to the end and was
  proven safe first - of 180 names changed, **175 merge into a place listed
  within 800 m** and the other 5 keep a real place name. Both guards are
  two-directional and red-proven: an absent `Status` column fails, and so does a
  scan that keeps stations while excluding none.
- **A third instance appeared the moment the new gate ran** - Manchester
  published `"Besses o'th'Barn"` AND `"Besses o'th'barn"`, one stop, one capital
  letter apart. The dedup key is `casefold()`ed now and the display spelling is
  chosen deterministically. **"Hardening a gate finds a new defect, every time"
  is now four for four.**
- **`tests/test_station_lists.py` is new** and in the root pytest suite: 7
  offline tests reading the SHIPPED arrays (the builder needs the 101 MB
  gitignored NaPTAN, and a test that only runs where the raw data is present is
  a test that does not run), plus the two `collect()` guards exercised against a
  synthetic NaPTAN.
- **One removal is worth knowing about before anyone re-derives.** Grange Hill
  is a live Central line station that London no longer lists: its ACTIVE nodes
  sit 50 m **outside** the boundary polygon while the RETIRED one fell inside,
  so it had only ever been published by accident. The limitation that exposes -
  point-in-polygon containment never lists a station just outside a city - is
  real and PRE-DATES this fix.

### 1.7 Two environment gotchas that cost time today

- **The Bash tool mangles heredocs.** `\n` inside a quoted heredoc arrives as a
  real newline, and non-ASCII characters (`±`, em dashes) break the heredoc
  outright. Every multi-line patch script today had to be written with the Write
  tool and then run. Do that from the start.
- **`backend/lambdas/epc/app.py` is CRLF; everything else is LF.** An exact-match
  patch written with `\n` silently matches zero times there. Normalise on read
  and restore on write.
- **`nohup ... &` returns the wrapper, not the Python process**, so the "task
  completed" notification fires immediately and means nothing. Poll the log file.

---

## 1b. SUPERSEDED (was "PICK UP HERE", 2026-08-29). Kept for the still-open items.

> The flood georeferencing fix in point 1 below **shipped on 2026-08-30**
> and the verification in point 2 was overtaken by the 31 August audit.
> Read §1 above for the current state; this section survives because its
> "other criticals" paragraph still lists open work.

**Read `AUDIT_REPORT.md` first.** 45 findings (9 critical / 21 important / 15
minor). All four of today's waves are committed, pushed, deployed and verified;
the audit is recorded but almost entirely UNFIXED.

**Do these two first, in this order:**

1. **The EA flood mosaic is mis-georeferenced in 10 of 11 cities** (F24/F39).
   `scripts/fetch_ea_flood_risk.py` clips edge tiles to the city bbox (line 219)
   but always requests **2000x2000 px** whatever their extent (line 156), then
   mosaics at a uniform **10 m/px** (line 237). Only Nottingham's bbox is an
   exact multiple of the 20 km tile - I checked all eleven. Sefton publishes
   31.39% against a corrected 0.28%. **Flood has SCORED since v3.9**, so live
   scores, the map and the 99 baked area pages are affected. Fix the request
   size (or give each tile its own transform), re-fetch every city, re-derive,
   rebuild area pages, redeploy. **`build_borough_bands.py --check` cannot see
   this** - it samples the same mosaic.
2. **Finish the verification.** 40 findings are still UNVERIFIED because the
   pass died at 15 of 48 on the session limit. Workflow resume is
   **same-session only**, so this means re-running the adversarial pass - but
   NOT the survey: `audit-findings-2026-08-29.json` holds all 45 findings with
   stable ids, evidence and scenarios. Verify before fixing: the verifiers that
   did run **downgraded 8 of 13** while refuting none.

**One caveat on tonight's work.** The `envCaveat` fix and its new gate
(`ce0bf49`) were committed after a green full preflight on the PREVIOUS tree; a
full run was started afterwards but the session ended before it finished. **Run
`sh scripts/preflight.sh` before anything else ships.**

Other criticals, none started: CI has run no test suite since 24 July (both test
jobs `needs:` lint jobs that fail on formatting, so they SKIP); London's
aircraft raster is declared painted from an href attribute and the gate reads
the same attribute; borough bands are weighted by retired postcodes (39.2% of
the NSPL sample); `mobile/scripts/copy-web.mjs`'s data allow-list is stale since
3 August.

---

## 1a. METHODOLOGY v4.0 SHIPPED AND DEPLOYED, 2026-08-29

| | |
|---|---|
| Commit | **`34e1a93`**, pushed; `master` level with `origin/master` |
| Backend | **DEPLOYED** via SAM. `/v1/regions` reports `methodologyVersion: 4.0` |
| Web | **DEPLOYED** - `index.html`, `borough-extra.json`, `sw.js` v1.0.35, 99 area pages, sitemap. Invalidation `I1WETPASHZENQKIIFHGO65NH4Y` **waited to completion** |
| Verified from the ORIGIN | drift **0 of 16**, `index.html` sha256 matches source, **99 of 99 area pages match the live API** |
| Weights | **0.45 / 0.35 / 0.20 confirmed by Bill** - decision closed |

Live spot-check of the three coverage tiers, against the deployed API:

| Borough | `env` | `environmentResolution` |
|---|---|---|
| Cardiff | absent | `unavailable - 1/3 inputs measured, too few to publish` |
| Middlesbrough | 6.3 | `partial - 2/3 inputs measured` |
| Camden | 4.4 | `measured` |

**What it is.** Road noise becomes the third scored `environment` input:
air quality 0.45 / road noise 0.35 / flood 0.20. It was the last input that was
derived, drawn on the map and reported by `/v1/environment` while nothing scored
it. Persona weights are untouched - this re-composes the component, not the
top-level split. Full detail in `CHANGELOG.md`, `METHODOLOGY.md` §4.7 and the
memory `project-road-noise-scored-v40-2026-08-29`.

**Three things that will save you re-deriving them.**

1. **Score `roadNoiseAboveWhoPct`, never `roadNoiseLdenMedian`.** The median dB
   looks like the plottable one and carries **41 distinct values over an IQR of
   1.7 dB** against the share's 69 over 13.4 points. They correlate at 0.931 -
   same signal, worse resolution.
2. **Use `build_borough_bands.py --write --write-lambda`, NOT `--sync-lambda`.**
   Sync copies from `borough-extra.json`, which **skips backend-only Cardiff and
   Nottingham**, so Nottingham would silently miss road noise. Each derive is a
   2.7M-row NSPL scan, several minutes.
3. **The env ramps had no direct unit tests before this wave.**
   `EnvironmentComponentTests` in `backend/tests/test_score.py` adds 18.

**The one thing that did not finish.** Teesside's flood raster is one tile short
of eight: the Boulby coastal corner of Redcar and Cleveland, largely North Sea,
renders blank on all 8 attempts, and `fetch_ea_flood_risk.py` refuses to cache a
blank render (the audit **C11** guard - *"a blank render is an outage, not a
risk-free area"*). **The guard is right and was deliberately left alone.**
Teesside publishes `partial` on two real inputs, which is the honest outcome.
The proper fix is teaching the tiler to skip a tile containing no postcodes -
a change to a data-integrity guard, so it wants review rather than a quick patch.

**Deploy order, and it matters.** The 99 area pages BAKE their scores, so
`tests/area-page-freshness.mjs` stays red until the Lambda serves v4.0 - the same
ordering the 28 Aug Progress 8 roll had to respect, and the one gate that inverts
"preflight, then commit".

1. `sam build && sam deploy` (backend first).
2. `make web-deploy-all` - `index.html`, the 99 area pages,
   `data/borough-extra.json`, and `sw.js` (bumped to **v1.0.35**; without it a
   returning visitor keeps a v3.9 shell and renders two inputs while the API
   answers three). **`export MSYS_NO_PATHCONV=1`** before any invalidation.
3. Re-run the three skipped gates: Playwright e2e, extension e2e, area-page
   freshness.

---

## 1. State at handover

Everything is committed, pushed and deployed. Nothing is running.

| | |
|---|---|
| Branch | `master`, level with `origin/master` |
| Deploy drift | **zero** - re-verified 2026-08-21 by sha256 against the origin |
| Score sanity | **PASS, 27 postcodes** |
| Preflight | **PASS** (re-run 2026-08-22, all blocking stages green) |
| Loaders | all finished — air quality complete, 7 DEFRA aircraft rasters loaded and deployed 19:01:57 |

---

## 2. What a second machine CAN and CANNOT do

Use `git push` / `git pull` as the **only** sync. Never OneDrive — an
interrupted write corrupts `.git/`. Clone to
`C:\Users\<you>\projects\london-flight-path-map`.

### Works immediately after `git clone`

- All code, docs, tests
- `npm install` then ESLint, html-validate, Playwright
- `python -m pytest backend/tests/ tests/` — 258 + 241 tests, no network
- Reading `AUDIT_REPORT_2026-08-12.md` and planning

### Needs setup before it works

| Blocker | What it gates | How to fix |
|---|---|---|
| **`.env`** (gitignored) | score sanity, `/preflight`, any live API call, SAM deploy | Copy `.env.example`, fill `EPC_BEARER_TOKEN` and `SKY_SCORE_API_KEY`. The CI key belongs to the `SkyScoreCiTier` plan — **do not** reuse the public demo key from `score-demo/index.html`; that coupled a blocking gate to a public quota once already. |
| **AWS profile `flightmap`** | every deploy, all loaders | `aws configure --profile flightmap`, region `eu-west-2`. Credentials are for the `flightmap-dev` IAM user. |
| **`data/nspl.csv`** (~806 MB, gitignored) | neighbourhood builder, station builder, all DEFRA loaders, air-quality/raster passes | Download link in `scripts/load_defra_raster.py` header. **This is the big one** — most data scripts are unusable without it. |
| **`data/naptan.csv`** (~101 MB) | `build_city_stations.py`, `build_borough_bands.py` transport | `curl -o data/naptan.csv "https://naptan.api.dft.gov.uk/v1/access-nodes?dataFormat=csv"` |
| **`data/defra_*.tif`** (~140 MB) | aircraft/road raster work | Per-airport URLs in `scripts/download_defra_wcs.py`. Needs a browser User-Agent or the host 403s. |
| **`data/pp-2025.csv`** (~155 MB) | neighbourhood prices | Auto-downloads on first `build_city_neighbourhoods.py` run. |

**Practical rule:** a laptop is fine for code, docs, tests and review. Anything
touching `data/` or AWS needs the setup above, and the NSPL download alone is
worth starting before you need it.

---

## 2a-quater. METHODOLOGY v3.9 SHIPPED TO SOURCE, NOT DEPLOYED, 2026-08-26

**The June roll (2a-ter below) is DONE - deployed, verified, committed. That
section is closed; do not re-run it.** What sits in the working tree now is
methodology **v3.9**: air quality and flood become a scored `environment`
component. It is complete, both holders agree, and it is **deliberately not
deployed**.

**IT CAN DEPLOY - the notice does not bind on an empty list.** The component
introduces ~0.62 points of total-score range, above the 0.5 threshold
METHODOLOGY sets, so the 14-day advance-notice policy applies. **Measured
2026-08-26: the signups table holds two rows and both are Bill's own** (the May
test key, and an August consumer signup), so there is no third-party integrator
to notify. That is the same basis the previous TEN methodology changes shipped
on - "no paying customers as at this date, so this ships with this changelog
entry as the record".

An earlier draft of this section said the deploy was blocked on the notice. It
is not, and the difference matters: the obligation is real and becomes binding
the moment a first customer holds a key. **Re-check the signups table before
the next material change rather than assuming this still holds.**

| Piece | State |
|---|---|
| `environment` component in the Lambda | `get_env_score`, `env_resolution`, `env_single_input`, anchored on WHO 2021 -> UK NO2 legal limit and the EA 10% `high` cut |
| Two continuous fields in BOTH holders | `LAMBDA_FIELDS` gained them; propagated by the new `build_borough_bands.py --sync-lambda`, which skips the heavy derivation |
| Persona weights | All 8, both holders, every row sums to 1.00, `env` uniform at 0.14 |
| Frontend | Computes AND displays it; all three `combineWeighted` sites carry it, including the `pcScore` that is persisted to DynamoDB |
| `plannedComponents` | `flood` and `airQuality` REMOVED - they shipped |
| METHODOLOGY | v3.9, new 4.7, 7.1 corrected, persona table regenerated from the Lambda, changelog entry |
| Gates | `borough-score-parity` PASS on all 91; parity test gained both fields plus a NAME_ALIASES drift guard, proven red |

**Two defects this uncovered, both worth knowing:**

1. **`write_lambda` could not carry a float.** It matched and wrote
   `'field': 'value'` only, so a ratio would have been written as a quoted
   string - importing fine and turning every later comparison into a string
   compare. Now type-aware.
2. **The borough-name alias was missing from the builder.** `borough-extra.json`
   keys `Barking`; the Lambda keys `Barking and Dagenham`. The propagation
   SILENTLY skipped it (157 fields written, not 159), which would have left
   Barking and Dagenham as the one London borough with no environment score
   while its 32 neighbours had one. Caught on the first dry run.

**THE AREA PAGES WILL GO STALE THE MOMENT THIS DEPLOYS, and preflight cannot
warn you yet.** `area pages match the live API` passes RIGHT NOW because both
sides are still v3.8: the pages were rebuilt on the June vintage during the
roll, and the live Lambda still scores without `environment`. Deploying v3.9
moves the API to five components while the 99 baked pages keep four, so that
blocking gate flips red immediately after the deploy rather than before it.

So the v3.9 deploy runbook is the roll's, plus a rebuild:

1. Send the 14-day notice. Wait it out. Nothing below happens first.
2. Deploy backend (SAM), so the Lambda serves v3.9.
3. **`python scripts/build_area_pages.py --write`** - rebuild all 99 on v3.9.
4. Deploy web + area + meta, then invalidate. Use
   `MSYS_NO_PATHCONV=1` on the CloudFront paths or the batch is rejected AFTER
   the uploads have already succeeded.
5. Re-run preflight; `area pages match the live API` should be green again.

**OPEN, and deliberately not done here:**

- **The 14-day notice.** Required before deploy.
- ~~`env` uniform at 0.14~~ **DONE.** `family` and `laterlife` carry 0.18,
  anchored on the WHO/COMEAP air-pollution sensitivity groups (children, older
  adults). The other six stay at baseline - no published group, no variation.
- ~~Cardiff and Nottingham get no environment score~~ **DONE.** Derived straight
  into the Lambda with no `borough-extra` entry, which is correct rather than a
  gap: they are backend-only, so there is no site half to diverge from, and
  giving them a `borough-extra` entry would trip
  `test_backend_only_cities_are_declared_not_discovered`. Coverage went 86 -> 94
  scored, 73 -> 77 measured, and **New York is now the only city with none**.
  Nottingham is `measured` on both inputs; Cardiff is `partial` because the EA
  coverage is England's.
- **Nottingham is now materially less thin, which is a BACKEND_ONLY_CITIES
  question.** It sits there on judgement rather than impossibility - `live` of
  2.6 on two inputs was too thin to publish. A fully-measured environment
  component is a real second leg. Worth re-asking whether it can go on the site;
  that is a one-way door, so read the checklist in CLAUDE.md before opening it.
- **Road noise still does not score.** Scheduled for v4.0 with rail, as the
  `quiet` noise composite.
- **Rank guard is returned, not enforced.** `context.environmentSingleInput` is
  published; no ranking surface consumes it yet.

## 2a-ter. PAUSED MID-ROLL, 2026-08-25 - read this FIRST

**The working tree carries a finished-but-undeployed vintage roll and fix set.
Live is UNTOUCHED and internally consistent on the May vintage.** Bill logged
off before the final preflight/deploy. Everything below is verified offline:
**pytest 583 + 136 subtests green, ruff clean, `build_hpi_prices.py --check
--all` = 0 disagreements on 2026-06.**

What is in the tree (uncommitted):

| Piece | State |
|---|---|
| **HPI roll May→June 2026** (published 19 Aug; 179 fields moved) | Both holders, all 12 cities. `--write` generalised from London-and-trend-only; site dialect is `avg_price` (bit again mid-roll) |
| **3-step previous-vintage roll** | `LONDON_PREVIOUS_PT` = May values; `SNAPSHOT_VINTAGE` 2026-Q3, `PREVIOUS_VINTAGE` 2026-Q2 |
| **Market summary direction-aware** | Its tail said "the market fell" unconditionally; June is the first RISING quarter (-3.35→-3.03) and exposed it |
| **Provenance prose corrections** | Six cities' "not yet sampled" (false since 2026-08-12), Nottingham's "liveability UNAVAILABLE/DROPPED" (false since v3.6/7), Cardiff's DEFRA-maps-CWL contradiction, London credits (NaPTAN+NHS ODS in, EPC/sold out - index-2 contract kept), P8 "cannot exist" claim (2023/24 Revised EXISTS, Feb 2025) |
| **NYC airport scale exemption** | JFK/LGA/EWR/TEB at 1.0 in the Lambda via `_US_AIRPORT_CODES` (module-load order forbids reading AIRPORTS_NYC; drift guard test added). Fixes Howard Beach quiet 10.0 beside impact "severe" |
| **Test re-aims** | ~12 vintage pins re-pinned with comments; Waltham Forest is now the real-data was-the-benchmark subject; the stubbed cohort now DOMINATES live trends (Havering 9.0 - its 4.0 was overtaken by real Barking +4.3) |
| **99 area pages rebuilt** on June | `--check` OK |
| **METHODOLOGY** | P8 terminality corrected (non sequitur), vintage line + 2026-08-25 changelog entry |

**RESUME RUNBOOK (~20-30 min):**
1. `set -a && source .env && set +a && sh scripts/preflight.sh` - expect
   **exactly one red: `area pages match the live API`**. That gate compares the
   rebuilt June pages against the LIVE API still serving May - red by design
   inside a roll window, green after step 2. Any OTHER red is real.
2. Deploy backend first (Lambda serves June): the documented SAM block in
   CLAUDE.md. Then `make web-deploy-all` equivalents: index.html + area/ +
   sitemap (area-deploy target exists) + invalidate; sw.js unchanged.
3. Re-run preflight → all green incl. area freshness. Commit (suggested split:
   roll+tests / provenance+NYC / area pages+docs), verify live:
   `check_score_sanity` (28 probes), drift 0/16, and three spot probes the
   audit named: NG1 5FS sourceBreakdown.live no longer says UNAVAILABLE;
   M22 1PR prose defers to quietResolution; ZIP 11414 quiet is no longer 10.0.
4. Update the review artifact's data-accuracy state if desired.

**Still open after that** (the data-accuracy audit's remaining items):
P8 roll to 2023/24 Revised (EES 403s non-browser UAs - fetch with a browser
User-Agent; scoring will move); NSPL reload when the August 2026 edition lands
(days away - skip May, one ~6h load; BatchWriteItem grant still unapplied);
London/NYC curated neighbourhood tables are UNDATED March-2026 values 10-16%
under current PPD in spots - date them or regenerate London via the proven PPD
pipeline; crime year-ending-June lands 22 Oct.

## 2a-bis. State as of 2026-08-24

| | |
|---|---|
| Review | 33-agent whole-app review, 112 findings, criticals independently verified (23 CONFIRMED / 1 REFUTED) |
| Deployed | `fd2558b` (map fits its box + 9 sibling fixes) live, sha256-verified, drift 0/16; a second wave (answer screen, payload diet, cross-city search, `?city=` reader) staged behind preflight |
| New blocking gate | `tests/map-fit.mjs` - 90 city/viewport combinations incl. landscape |
| Score sanity | 28 probes now - NYC added, the one city that had none |
| Docs | BUILDATHON archived to `archive/`, ROADMAP security-residual re-measured, OUTREACH_LOG iOS line corrected (it said "TBD - pending" two months after the app went live) |

**Needs Bill, unchanged:** DMARC p=none; second AWS MFA; ICO fee (Cubitt33 Ltd);
rebrand step 1 (read UK00004145719); console concurrency figure; the outreach
send itself. **Full register and evidence: the 2026-08-24 review artifact.**

## 2a. State as of 2026-08-21 evening

Everything below §3 predates a long session; this is where it actually stands.

| | |
|---|---|
| Audit criticals | **all 11 closed**, deployed, verified live |
| Audit **Important** | **10 of 14 closed 2026-08-22**, DEPLOYED and verified live |
| Audit **Minor** | 10 closed 2026-08-22 + **2 more on 2026-08-23** (`LONDON_BOUNDS`, the d3 tag), all deployed except the 2026-08-23 batch |
| Tests | **pytest 555, unchanged** - 2026-08-23 added assertions to the `.mjs` gates, not to pytest (extension e2e 60 -> 65 checks, plus new families in `layer-honesty`, `smoke-local` and `check_deploy_drift`). The line here read "555 +8", which implied 563 pytest tests and was measured wrong within a day of being written. Every added assertion proven red first |
| Distribution findings | **D5, D1, D2, D4 shipped**; D3 and D6 need no build |
| Blocking preflight stages | **29** (measured 2026-08-23 from a real run, not counted by hand - it read 30, and a count in a label is scheduled staleness. `sed -n '/^Blocking:/,/^Advisory:/p' <log> \| grep -cE '  (PASS\|FAIL)'`) |
| Log groups | 8, one per live Lambda, all 30-day retention, **zero orphans** |
| Deploy drift | zero, re-verified by sha256 2026-08-22 after the deploy |

**Needs Bill, and nothing else does:** publish DMARC at `p=none` in Cloudflare;
add a second AWS MFA device (there is one factor and no fallback); decide D3, the
gap between £0 and £499.

**Gates added today, all proven red before being trusted:**
`demo-key-scope.mjs` (asks the running API whether a per-method RateLimit of 0
actually denies - the template cannot answer that), `uk-city-panel.mjs` (types a
real postcode in a non-London city, which nothing had ever done),
`area-pages.mjs`, `area-page-freshness.mjs` (99 baked scores against the live
API in ONE batch request) and `test_empty_source_guards.py`.

---

## 3. What is left, highest value first

All traced with evidence in `AUDIT_REPORT_2026-08-12.md`.

1. ~~**`/v1/score/batch` demo-key bypass**~~ — **DONE**, and it was already done
   when this list was written. `ScoreDemoUsagePlan` and `ScoreFreeUsagePlan`
   both carry the per-method `RateLimit: 0` deny (commit `f883a0e`), and
   `tests/demo-key-scope.mjs` asks the RUNNING API whether 0 actually denies.
   This entry survived its own fix by two days. *Re-measure a recorded blocker
   before working from it* — the third time that lesson has been paid for in
   this file.
2. ~~**Road-noise plausibility ceiling**~~ — **DONE 2026-08-21.** The
   `+3.4e38` sentinel was proven to return `3.4e+38` as decibels at HEAD; the
   check is now a range. Dead `_lookup_road_lden` deleted.
2a. **`ReservedConcurrentExecutions` is the one part of I3 still open**, and it
   is blocked on a number this machine cannot read: `flightmap-dev` is denied
   `lambda:GetAccountSettings`, so the account's concurrency limit is unknown
   and any reserve would be a guess. AWS also refuses to leave under 100
   unreserved. Get the figure from the console, then reserve for
   `ScoreFunction` (protect the paid path) rather than capping the free ones.
   The timeout half of I3 is done: every function was over API Gateway's 29s
   integration cap, including the Globals default, and at 45s `/nhs` could not
   reach its own fallback branch inside the caller's window.

3. ~~**The `excellent` air-quality band**~~ — **DONE 2026-08-23, and the
   finding was recorded BACKWARDS twice.** It was written up here and in
   `ROADMAP.md` as a band *"the legend advertises that no UK borough can
   occupy"*. The legend never advertised it. `#legend-aq-group` carried three
   rows — POOR, MODERATE, GOOD — while `repaintFillLayers()` carried four
   colours, so `excellent` (`#16a34a`, four shades off GOOD's `#22c55e`) was the
   one band the map could paint with **no row to explain it**. The over-claim
   was the painter's, not the legend's, and the correction was a swatch to ADD
   rather than one to remove.

   The 2026-08-21 measurement underneath it stands and is what made the shape
   obvious: 59.2% of 254,904 DEFRA PCM cells clear both WHO guidelines, PM2.5
   median 4.43 against 5.0, so the band is reachable nationally and simply
   cannot fire for the 91 urban boroughs we cover (measured across
   `borough-extra.json`: 62 moderate, 18 good, 11 poor, 0 excellent).

   Fixed the way the note proposed anyway — `markLayerCoverage()` extended one
   level down, hiding any band row that painted nothing. **41 of 99 rendered
   band rows were describing a band not on that map**, worst in Leicester and
   Teesside, which showed six confident swatches (three road, three flood)
   beneath two titles already reading "(NO DATA)". The EXCELLENT row costs
   nothing while empty and appears by itself when coverage leaves the city
   cores, so nobody has to remember it. Guarded by `tests/layer-honesty.mjs`,
   which now also asserts painter-colours and legend-rows are the same list;
   proven red in four directions.

   **The lesson is about the note, not the band.** Two docs carried a
   confidently-worded diagnosis that was the inverse of the code, for eleven
   days, because the two lists it compared were a function-local and a block of
   static markup with no gate between them. There is a gate now.
4. ~~**`/v1/environment` hardcodes `'london'` geometry**~~ — **DONE 2026-08-21.**
   Reproduced live (M22 5RX returned 10.0 against Manchester's 2.0) and fixed by
   deriving the city from the resolved LAD. Measured over 6,000 NSPL postcodes:
   94% unchanged, and all 291 changed readings moved louder. **Needs a SAM
   deploy** — the fix is committed but not live.
5. ~~**Mobile legend headings at 1.19:1**~~ — **DONE 2026-08-22**, and the real
   figure was **1.00:1**: three headings were `#141414` on a `#141414` pill, the
   same colour as their background. Measured on the rendered DOM, not estimated.
   The a11y gate now opens the collapsed legend and reveals all four layer
   groups, which immediately found a second defect nothing had scanned -
   `.sheet-footer .for-devs` at 2.60:1.

---

## 4. Email / outreach

`EMAIL_AUTH_SETUP.md` has the full sequence. Summary:

- **Sending works today** via Gmail "Send mail as" — it is **not aligned**.
  Gmail signs as `gmail.com` while `From:` says `skyscore.co.uk`.
- **Do first, 2 minutes, zero risk:** publish DMARC at `p=none` in Cloudflare.
  It cannot affect delivery and starts the reports.
- **Then:** Google Workspace (~£5/mo) for real DKIM alignment, SPF update,
  verify with **Show original** that DKIM passes *for skyscore.co.uk*, not for
  `gmail.com`.
- **Warm outreach needs none of this** and is unblocked today.

---

## 4a. Deploy state

**DEPLOYED 2026-08-23, THREE TIMES.** The third carried the mobile sheet
change and the collision fixes (`index.html`); invalidation
`I4E0T15AM59EV7HSXCBHV7OK15` waited to completion, sha256 matches, drift 0 of 16,
and **`tests/responsive.mjs` against LIVE reports 55 of 55 clean** - it had gone
red against live with 10 failures the moment the new detectors landed, which was
the deployed page being measured honestly for the first time.

**Phones now land on the map**: 12% of the viewport was map at boot at 320, 375,
390 and 414; it is 61-75% now. The sheet boots at peek, as iPad portrait has
since the Apple fix in May.

**DEPLOYED 2026-08-23, EARLIER TWICE.** Second deploy carried the mobile legend
disclosure (`index.html`) and the Swagger `select-name` fix
(`score-demo/api-docs.html`); invalidation `I62G6RVYSZ7ZWSNL6EDFZIL8T6` waited to
completion, sha256 matches on both, `check_deploy_drift.sh` reports **all 16
surfaces in sync**, and the live smoke passes from CloudFront. **The branch was
also pushed** - it had been 14 commits ahead and local-only since 22 August, and
is now level with origin.

*(Note for a future session: the project `CLAUDE.md` still says "keep git local
only, never push", which now contradicts both the global multi-device rule and
what was actually done. Left as-is deliberately - Bill chose to push without
changing the instruction.)*

First deploy: `index.html` only - it was the sole surface out of step,
and neither the extension (unlisted) nor any Lambda changed. Uploaded to S3,
CloudFront invalidation `I1Q8QLUBYZ3SFP4BYRV4884NRM` **waited to completion**
rather than fired and forgotten.

Verified from the origin, not from the deploy's exit code:

| Check | Result |
|---|---|
| `index.html` source vs CloudFront | **sha256 MATCH** |
| `check_deploy_drift.sh` | **PASS, all 16 surfaces** |
| `smoke-local` against CloudFront | PASS - 33/5/10 boroughs paint, d3 loads, **1 request** (the preload does not double-fetch in production) |
| Legend markup live | 10 `data-band` rows, EXCELLENT swatch present |
| d3 tag position live | preload at line 93 in `<head>`, script at 3661 at the foot of `<body>` |
| `preflight` after the deploy | PASS, and `deployed == source` moved from *deviates* to **ok** |

**A gate hardened by watching it verify this deploy.** `check_deploy_drift.sh`
counted `CHECKED` and never asserted it, and printed **nothing** on success - so
a run comparing all sixteen surfaces and a run whose loop never executed
produced identical output and both exited 0. Empty `SURFACES` and it reported
the tree perfectly in sync having opened nothing. Fourth instance of that shape
here, after the three `--check` gates closed on 2026-08-22. It now asserts a
floor of 16 and says what it compared; proven red by emptying the list.

**Previously DEPLOYED 2026-08-22.** The audit-Important work of that day is live: SAM
updated `ScoreFunction`, `EpcFunction`, `NhsFunction` and `ChatFunction`, and
all six changed public surfaces were uploaded with a full CloudFront
invalidation (waited to completion, not fired and forgotten).

**Verified from the origin rather than from the deploy's exit code:**

| Check | Result |
|---|---|
| All six HTML surfaces vs source | **sha256 MATCH** on every one |
| `check_deploy_drift.sh` | **0 of 16 surfaces differ** (was 6) |
| `tests/responsive.mjs` against **live** | **0 failures across 45 page/viewport combinations** - it reported **10** before the deploy |
| `check_score_sanity.py` | **PASS, 27 postcodes** |
| `/v1/changes` | now returns `Cache-Control: public, max-age=3600` |
| `/nhs` at an uncovered bbox point (51.25, -0.472) | returns three **NHS search links** instead of three empty lists - the confident-absence fix, working live |
| `/nhs` central London (51.5152, -0.1418) | still `bundled-snapshot`, 5 GPs - real coverage untouched |
| `/epc` N1 7SX | 10 certificates, `averageBand: C`, a real band still carries its rating |

**Everything was deployed as of 2026-08-21 17:26.** `ScoreFunction` and
`TransportFunction` both updated via SAM; `index.html` and `api/index.html`
uploaded and CloudFront invalidated. Verified from the origin rather than from
the deploy's own exit code: both HTML files are byte-identical to source
(sha256), `/v1/environment` at M22 5RX returns 2.0, and `/transport` at Oxford
Circus returns 6 line statuses including two live disruptions.

Gotcha that still applies: keep `source .env` in the SAME Bash invocation as
`sam build`/`sam deploy` - the working directory persists between calls and
environment variables do not.

---

## 5. Habits this repo has paid for

Worth re-reading before changing anything:

- **A gate that reads its expectation from the code under test cannot fail.**
  Six instances. `layer-honesty` and `city-switch` were fixed on 2026-08-12.
- **A passing test asserting old behaviour is worse than no test** — it reads as
  evidence. That is how postcode scoring stayed broken for two days.
- **Absence must never render as a measurement.** The `-0.4` transport penalty,
  `|| 'moderate'` fill layers, and "No stations found within 1.5km" were all the
  same defect wearing different clothes.
- **Any count in an assertion or a label is scheduled staleness.**
- **Mirrored code drifts on the NEXT edit, not this one.** `lden_from_row` and
  `road_lden_from_row` sat eleven lines apart, documented as mirrors, and only
  one got the 2026-08-12 ceiling. Prefer one holder to two correct copies.
- **A join that matches nothing returns a confident, well-formatted number.**
  Measuring NSPL coverage on 2026-08-21 first produced a clean `100.0%` off a
  column name that did not exist. Assert on a non-zero match before reporting.
- **Verify agent and doc claims against primary sources.** Both produced
  confident, wrong figures this session.
