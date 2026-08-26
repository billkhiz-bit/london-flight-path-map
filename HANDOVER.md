# Handover — resuming on another machine

**Written 2026-08-12.** Read this first if you are picking the repo up on a
laptop, or starting a fresh session on this desktop.

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
