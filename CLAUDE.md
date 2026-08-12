# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Compact Instructions

When context fills up, always preserve:
- AWS deployment details (API URL, CloudFront ID, S3 bucket, region)
- The current task the user is working on
- Any file changes made during this session that haven't been committed
- Branding: always "Sky Score", never "London Flight Path Map" in user-facing text

## Canonical repo location

**Use `C:\Users\bilal\projects\london-flight-path-map`** for any work on this repo. The `OneDrive\Desktop\london-flight-path-map` clone was the legacy location; OneDrive's filesystem-level sync can corrupt `.git/` if it interrupts a write mid-transaction (the user's global CLAUDE.md flags this risk explicitly). The OneDrive clone was retired on 2026-05-07 once the in-flight DEFRA loader finished — only `data/` (782 MB of NSPL CSV + DEFRA GeoTIFF, gitignored) was migrated by `mv`; everything else came from `git clone` of the GitHub remote.

If a future session lands you back in `OneDrive\Desktop\london-flight-path-map`, exit and `cd` to the projects/ path before doing anything destructive. If the OneDrive clone has come back from the dead (e.g. someone restored from a backup), prefer running on the projects/ clone and `git pull` to catch up rather than working in OneDrive.

**2026-07-19 update:** the `Claude Projects\Sky Score.bat` launcher was found still pointing at the OneDrive clone and has been repointed to the projects/ path. Both stale Desktop copies (`london-flight-path-map` and `London Flight Path Map`) were verified fully contained in this clone's history and are scheduled for deletion. Their unique March-era artefacts (original `london_flight_paths.py`/`.html` prototype, March `samconfig.toml`, old `.claude/commands`) are preserved in `archive/prototype-2026-03/` here. The 4 fastlane ASC vars (`ASC_ISSUER_ID`/`ASC_KEY_ID`/`ASC_KEY_FILE_PATH`/`FASTLANE_SKIP_DOCS`) existed only in the OneDrive clone's `.env` — merge into this clone's `.env` before relying on fastlane locally.

## Rolling planning docs

Two project-level planning docs live alongside this file. Read them when picking up work between sessions:
- **`ROADMAP.md`**, the broader rolling plan: vision, three parallel tracks (consumer site, B2B API, competitions/outreach), near-term task list with deadlines, open decisions. The source of truth for "what next".
- **`EXPANSION.md`**, which cities and countries are reachable and what each costs. Read before proposing a new city: the NATION is the unit of work, not the city. Every source behind an English city-region is already national (NSPL, HPI, Price Paid, ONS crime, DEFRA air/road/aircraft, EA flood), so England is nearly free; Wales loses schools, road noise and flood to different publishers, and Scotland changes publisher for five of six components. Ranked on measured 2025 transaction volume - we currently cover 34.6% of English and Welsh sales.
- **`BUILDATHON_PLAN.md`**, focused single-purpose doc for the Shared Futures Buildathon (deadline 2026-05-15, event 2026-06-07). Will be archived after the event.

When a task ships or a decision lands, update the relevant doc rather than relying on chat memory.

After any substantial change (feature shipped/removed, audit item closed, vendor relationship changed), follow the **echo-work discipline** in the global `~/.claude/CLAUDE.md` — propagate to README, ROADMAP, LICENSING, AUDIT_REPORT, OUTREACH_LOG, memory, .env.example, tests, AWS surfaces. Doing it now is 2-3× cheaper than re-deriving the context tomorrow. For Sky Score specifically, the "echo loop" almost always touches: README.md (Lambda counts), ROADMAP.md (open decisions resolved), LICENSING.md (data sources), and `~/.claude/projects/.../memory/MEMORY.md` (cross-session facts).

**Cross-project echo**: substantial Sky Score waves (release submitted, big pivot landed, competition outcome confirmed, new submission added/dropped) also belong in the 90-day builder roadmap at `C:\Users\bilal\OneDrive\Desktop\90_DAY_ROADMAP.md` under the "Daily Progress Log" section. Keep that file strategic — competitions, pivots, deadlines, headline wins — not wave-level commit detail. The 90-day file is opened via the `90-Day Roadmap.bat` shortcut in `OneDrive\Desktop\Claude Projects\` to seed cross-session context across all Bill's projects, so Sky Score wave logs going there means future Claude sessions on Noor / LedgerAgent / Siraj see Sky Score's state too.

## Before conversation ends

When the user says goodbye, thanks you, or indicates they're done, run `git status` to check for uncommitted changes. If there are any, remind the user:

```
You have unsaved changes. Would you like me to commit them before you go?
```

If they say yes, create a commit with a clear message describing what changed. Keep git local only, never push.

## On conversation start

When the user starts a new conversation (first message, greeting, or asks what they can do), display this welcome message:

```
Sky Score

Available commands:
  /project:deploy-frontend Upload to S3 + invalidate CloudFront
  /project:deploy-backend SAM build + deploy Lambdas
  /project:deploy-all Deploy everything
  /preflight Pre-commit quality checks (lint, security, a11y)
  /careful Enable production safety mode (blocks destructive AWS commands)
  /aws-debug Debug Lambda/API Gateway issues (LIMITED — no log read on this account, see Quality & Plugins)
  /project:test-apis Test all API endpoints
  /project:review Summarise recent changes

Or just describe what you need, I have full context of this project.
```

## Project

**THIRTEEN cities on `/v1/score`; ELEVEN on the consumer site, as of 2026-08-11.**

- **On both site and API (11):** London (33), NYC (5), Greater Manchester (10),
  West Midlands (7), West Yorkshire (5), South Yorkshire (4), Merseyside (5),
  Tyne and Wear (5), Bristol (4), **Leicester (8)**, **Teesside (5)**. That is
  **91 boroughs**, and `tests/borough-score-parity.mjs` compares the score the
  site RENDERS against the Lambda's for every one of them.
- **API only, declared in `BACKEND_ONLY_CITIES` (2):** Cardiff (4), Nottingham (4).
  **Cardiff cannot leave**: Progress 8 is an ENGLAND measure, so Wales has none.
  **Nottingham now could and does not** - the "1 of 4 inputs" recorded here for
  months stopped being true when healthcare landed in v3.7. Broxtowe, Gedling and
  Rushcliffe gained transport (v3.6) then healthcare (v3.7), so they clear the
  two-input floor and publish a liveability score. It stays on JUDGEMENT: `live`
  of 2.6 on two inputs is thinner than the site should claim.

**Leicester and Teesside went through the one-way door on 2026-08-11.** Leicester
is the city plus all seven Leicestershire districts (a four-authority cohort
spans only 230k-281k, and min-max over a narrow cohort manufactures spread it
has not measured). Progress 8 covers **1 of Leicester's 8** - education is an
upper-tier county function, the same gap as Nottingham - but transport and
healthcare carry them to 3 of 4. Teesside's five unitaries are their own
education authority, so all five are 4 of 4; it spans **two police forces**
(Cleveland and Durham) so crime needs an include-list.

Every field of the eight is **script-derived and independently verified**, and
each has a `--check` that can go red:

| Input | Script | Status |
|---|---|---|
| avgPrice / trend | `build_hpi_prices.py --check --all` | HPI 2026-05, **blocking preflight stage**, all agree |
| roadNoise / airQuality / flood bands | `build_borough_bands.py --check` | DEFRA Round 4 road Lden + DEFRA background maps + EA RoFRS, **all three derived for every city 2026-08-11** |
| transport | `build_borough_bands.py --write --write-lambda` | **NaPTAN, share of postcodes within 800 m of a rail/metro/tram node. A SCORING input (0.25 of liveability), so it lives in BOTH holders — `tests/test_borough_data_parity.py` fails the build on drift. Methodology v3.6, 2026-08-11.** |
| crimeRate | `refresh_crime_from_ons.py --check --city X` | ONS Table C4, 0 differ everywhere |
| p8 | `build_progress8.py --check` | DfE KS4 2022/23 **Revised**, 0 differ |
| impact | `build_aircraft_bands.py --check` | geometry ESTIMATE, ladder scaled by DEFRA footprint |
| boundaries | `build_city_boroughs.py --all` | ONS codes, counts asserted |

**Leaving `BACKEND_ONLY_CITIES` is a ONE-WAY DOOR.** The moment a city drops
out, the site must reproduce the API on every borough, and
`test_backend_only_cities_are_declared_not_discovered` fails in both directions
to force it. Six cities went through that door on 2026-08-10; before opening it,
all 30 of their boroughs were compared site-vs-Lambda as an OUTPUT check.
Input parity is not enough - the Manchester incident had matching inputs on both
sides and still diverged by up to 1.5 points, because the site never loaded them.

**Boundaries load through one registry-driven path**, `loadCityBoundaries()`
reading a `boundaries` field. It used to be `if london / else if manchester /
else NYC`, whose own comment described the bug it had already caused.

**Cardiff and Nottingham can never fully leave** on current data: Progress 8 is
an ENGLAND measure so Cardiff has none, and Nottingham gets 1 of 4 because
Broxtowe, Gedling and Rushcliffe are districts inside `South Nottinghamshire`
rather than local authorities. Both also have that gap in ONS crime.

**DEFRA IS NOT A BLOCKER AND NEVER WAS (measured 2026-08-10).** GetCapabilities
on the WCS named in `scripts/download_defra_wcs.py` advertises **16 airports
with a Round 4 Lden surface** - Manchester, Birmingham, Leeds Bradford,
Liverpool, Newcastle, Bristol and East Midlands among them. Provenance for nine
cities used to say the raster "has not been run for" the city; that was false
and is corrected. We have not SAMPLED it. Use the **per-airport** coverages
(Birmingham is 979x1467, an 11.5 MB GeoTIFF), never `Airport_Noise_ALL_Lden`,
which is 26,097 x 48,046 - 1.25 billion cells. The host needs a browser
User-Agent; without one it answers 403 and looks bot-blocked.

**Postcode-level scoring works for every city (un-gated 2026-08-10).** It was
`if city != 'london': return 400`, and the recorded reason - that NSPL writes
the borough attribute for London LADs alone - was half the story. NSPL writes
the LAD **code** for all 2.7M rows, so `LAD_TO_BOROUGH` in the Lambda resolves
the rest and **no reload was needed**. Verified against the live table: M1 1AE
carries `lad=E08000003` with `b` absent. The "two blockers, not one" recorded
here for months were really one, and it was a lookup rather than missing data.

**Corridors are on a common 1 km interval.** Corridor distance is measured to
the nearest waypoint, so a coarse polyline reads as further from the corridor
and therefore QUIETER - which is why resampling had to precede un-gating.
Measuring first also corrected a claim this file used to make: **London was
3.34 km median, not "~1 km"**, so the gap against the new cities' 4.00 km was
about 20% rather than 4x. Everything is now <=1.01 km. Regenerate at 1 km if
any corridor is ever re-derived.

**The aircraft ladder is scaled per airport, and the fix had to be made TWICE
(v3.8, 2026-08-11).** The distance ladder is calibrated on Heathrow and was
applied unweighted everywhere, so Stockton-on-Tees was published `severe` — the
same band as Hounslow — off an airport carrying 173,006 passengers a year. Each
airport's ladder is now divided by its **measured DEFRA 55 dB Lden footprint**
relative to Heathrow's; Heathrow is 1.000 so London bands cannot move. **Do not
reach for passenger numbers**: East Midlands has the second-largest footprint of
the twelve on 3.2M passengers because it flies freight at night, Gatwick 0.475 on
40.9M.

The important half is that **`calc_postcode_quiet` runs its OWN copy of the
ramp** and takes precedence over the borough band, so fixing only the band left
the two tiers contradicting each other by 4.0 points. **When correcting any
scoring input here, ask which tier answers first.** The borough path needs a
near-field floor (scaling alone moved 29 boroughs and moved all 29 *down*,
putting Vale of Glamorgan on `low` with Cardiff Airport inside it); the postcode
path does not, because a postcode carries a real distance.

**There is a validation set for quiet geometry — use it.**
`data/aircraft-quiet-london.json` holds DEFRA raster-measured quiet for 35,352
London postcodes, and the geometry tier only ever stands in for that raster, so
any change to it can be scored rather than argued: v3.8 cut mean absolute error
from 3.230 to 1.879, 14,730 postcodes closer and 20 further.

**A city with NO airports is a real case.** South Yorkshire has none (Doncaster
Sheffield closed to commercial flights in 2022), and un-gating turned that into
`min()` on an empty sequence - a 500 on every South Yorkshire postcode, which
the gate had been hiding. It now falls back to the borough band. Any new city
without an airport needs that path to stay intact.

**Adding a city — the things that bite. Points 1-3 were found doing the third city and all still apply; the scripts in the table above now handle the DATA half, so what is left is the wiring.**
1. **`data/*` is gitignored**, un-ignored file by file, so a new city's boundaries are invisible to git BY DEFAULT. It works on your machine, every gate passes, and the deploy serves "outlines could not be loaded". Add a `!data/<city>-boroughs.json` line, a `SHELL_ASSETS` entry, and a `make data-deploy` line — `cache.addAll()` is atomic, so a precached file missing at the origin stops the service worker installing for **every** city.
2. **`data/borough-extra.json` is the enumeration that still bites.** `hydrateBoroughExtra()` and `recalcAllScores()` are now registry-driven and name no city, but a city absent from borough-extra scores from an empty object while the API scores properly — all ten Manchester boroughs disagreed by up to 1.5 points that way, with nothing raised, because both holders *had* the data and the site never loaded it. **The gate for this now exists**: `tests/borough-score-parity.mjs` drives the real page and compares the RENDERED score against the Lambda's for all 91 boroughs. Seed a new city's entry from the Lambda (`crimeRate`/`p8` only), then `python scripts/build_borough_bands.py --write` derives the other five fields — it SKIPS any city with no borough-extra entry, so the seed comes first.

2a. **Generate the frontend constants, do not copy them.** `python scripts/build_city_frontend_block.py --city <key> --insert` writes `<CITY>_BOROUGH_DATA_RAW`, the airports, the corridors and the neighbourhood markers from the Lambda. It exists because the two holders use different dialects for the same geometry — `coords` vs `coordinates`, `(lat, lon)` vs `[lon, lat]`, `avgPrice` vs `avg_price` — and each has already caused a production defect. The `CITY_DATA` entry itself is still written by hand: legend copy is a provenance claim.
3. **Map chrome comes from the registry** via `applyCityChrome()`. Do not add an `if (city === 'x')` branch; add registry fields. The legend copy in particular is a provenance claim — NYC shipped a DEFRA/LHR explainer under a "BTS AIRCRAFT NOISE" heading for months because that block had no id. Adding a registry field means adding it to **all** cities: `tests/smoke-local.mjs` asserts key parity, so a field on one city and not the others fails the build.

4. **The city switcher is TWO TIERS** (country tabs above city chips) and both are **generated from `CITY_DATA`** by `renderCitySelector()` / `renderCountrySelector()` — there is no city markup to edit. A new country needs a `COUNTRY_SHORT` entry or its tab shows the full name. The **locator inset** (`data/uk-locator.json` and `data/usa-locator.json`, both checked in; `scripts/build_locator.py` generates them from a boundary GeoJSON - the UK file predates it and has not been regenerated) draws the ten UK core-city markers, and the USA file draws New York alone: add the city to `LOCATOR_TO_CITY` or it stays a "planned" light disc. The file is deliberately **not** in `SHELL_ASSETS` — decorations must not be able to stop an atomic `cache.addAll()` — but it does have a `data-deploy` line. Guarded by `tests/locator-verify.mjs` and `tests/selector-widths.mjs`, both in preflight.

5. **There is now ONE frontend city registry, and there used to be two.** `CITIES` held the projection `center`/`scale` for **three** cities while `CITY_DATA` held nine, so the six regions shipped on 2026-08-10 threw `Cannot read properties of undefined (reading 'center')` inside `switchCity()` — **title changed, map did not, six of nine cities dead on the live site**. `CITIES` is deleted; `center` and `scale` are CITY_DATA fields, which puts them under the key-parity assertion in point 3. Derive a new city's pair with `python scripts/fit_city_projection.py --city <key>` rather than picking numbers by eye — it fits the region into the same on-screen box London occupies at scale 48000.
6. **Corridors: the frontend key is `coordinates`, the Lambda's is `coords`.** Porting a corridor block across without renaming throws `Cannot read properties of undefined (reading 'map')` and draws no corridors. This bit five cities, and the throw was **invisible until the `center` bug above was fixed** — the first exception aborted the render before the second could fire. South Yorkshire was the only new city unaffected, *because it has no airports*.
7. **`tests/city-switch.mjs` clicks every chip and is in preflight.** Before 2026-08-11 nothing in the suite had ever clicked a city chip, which is how both defects above reached production with every gate green — the boroughs' *scores* were verified site-vs-Lambda, and reaching the city was not. It asserts the outline count against each city's own boundary file, so a city drawing another city's geography also fails. `boundaries` is an **ordered fallback list, not a union**: NYC declares two sources and only the first that resolves is used.

**The three borough fill layers were FABRICATING data for seven cities until 2026-08-11.** Road noise, flood risk and air quality each ended their lookup with a fallback — `|| 'moderate'`, `|| 'low'`, `|| 'moderate'` — and `borough-extra.json` gave those fields to London and NYC only. So every borough of the other seven was painted **one confident colour** meaning a reading nobody had taken, while the legend title above it already said "(NO DATA)". The label said no data; the map drew a value; the map is louder. The detail panel separately printed the literal string **"UNDEFINED"**, uppercased by its own CSS.

- **`paintBoroughLayer()` is now the single painter and it SKIPS a borough with no reading.** Do not reintroduce a default. An unknown band is skipped too, because painting it as "moderate" is how a data problem becomes a false claim.
- **All three layers are derived for every city** by `python scripts/build_borough_bands.py --write`, anchored on published thresholds (road: share of addresses over WHO 53 dB Lden; air: worse of NO₂/PM2.5 against WHO 2021; flood: share at EA Medium-or-High, the 1%-annual-chance Flood Zone 3 line). See `METHODOLOGY.md` §7.1. The nine `*_BOROUGH_ROAD_NOISE` constants and the `roadNoise()` registry accessor are **deleted** — `borough-extra.json` is the single holder for all three layers.
- **Flood risk comes out of a WMS by decoding rendered colours, and that is deliberate.** The EA's RoFRS dataset publishes **no WCS and no WFS** (both 404), and its postcode-level product is **retired** — `scripts/fetch_ea_flood_risk.py` records every dead route so they are not retried. Two things keep it honest: `format_options=antialias:none` is **load-bearing** (without it one tile carries 16,289 blended colours instead of 5), and the colour→band map was **verified against the service's own `risk_band` by point-in-polygon containment** — an earlier check that trusted `features[0]` made High and Medium look interchangeable, because a 200 m query box spans several 50 m polygons. Re-run `--verify` after any upstream restyle; an unrecognised colour **fails the fetch** rather than silently reclassifying. Rendering is scale-dependent: nothing draws above ~10 m/px.
- **`scripts/fetch_defra_road_noise.py` was London-only by a single hardcoded bbox** while pointing at a coverage id ending `England_Round_4_All`. It now derives the bbox from each city's boundary file. **Wales is excluded by name** (`NO_ROAD_COVERAGE`) — the coverage is England's, and a Cardiff fetch would otherwise "succeed" and read as no-noise-anywhere.
- **Legend "(NO DATA)" is now MEASURED**, appended by `markLayerCoverage()` from what the render produced. It used to be a hardcoded registry string per city, which has to be remembered when data arrives and is wrong in the other direction the moment it does. **That prediction came true within a day, in a slot the fix did not cover**: `legendFlood` and `legendAq` label the *first swatch* of each legend, not the title, and all seven UK cities still said `'NO DATA'` there — so the High and Poor swatches were labelled "NO DATA" while the map painted real EA and DEFRA readings beneath them. Corrected 2026-08-11 to `'HIGH'` / `'POOR'`. **Any registry string that describes data availability is a liability**; prefer measuring it.
- **Cardiff and NYC are excluded from road noise and flood by name** (`NO_ROAD_COVERAGE` / `NO_FLOOD_COVERAGE`) — both coverages are England's, and NYC keeps curated FEMA-derived flood bands. A Welsh fetch would otherwise "succeed" and read as no-risk-anywhere.
- Guarded by **`tests/layer-honesty.mjs`** (in preflight), which fails in both directions: over-painting is an invented default, under-painting is a borough whose data the map cannot find.

**Neighbourhood ranking data.** London and NYC hold *curated* medians and a hand-assigned `crime` modifier inline. **All nine UK city-regions' 485 entries are generated** (2026-08-11; was Greater Manchester's 85 alone) — `python scripts/build_city_neighbourhoods.py --write-index` rewrites `index.html` between each city's `<CITY>-NEIGHBOURHOODS:START/END` markers from HM Land Registry's **bulk** Price Paid CSV (the linked-data API returns **HTTP 200 with an empty list** for a district query, so it cannot be used) plus NSPL for coordinates. A "neighbourhood" is a **postcode district**, districts under 30 sales are dropped rather than estimated, and `crime` is 0 everywhere because sub-borough crime is not published at that geography. **Boroughs come from the Lambda's `LAD_TO_BOROUGH`, matched to Land Registry's own district spelling by normalisation** (`Westminster` → `CITY OF WESTMINSTER`); a borough matching nothing is reported loudly, because a silent miss reads as "this borough has no neighbourhoods". One PPD pass and one NSPL pass cover every city. Do not hand-edit inside the markers; re-run the script. The 155 MB PPD cache and the JSON by-product both land in gitignored `data/`.

**The 285 curated area labels are CORROBORATED, not recalled (2026-08-12).** Until then only Greater Manchester had any, so **273 of 503 districts rendered under a repeated post town** — Birmingham ×35, Liverpool ×29, Leeds ×16, Sheffield ×15. Nothing was false (the outward code is always beside the label) but a ranked list of thirty-five "Birmingham" rows says nothing. `NAME_OVERRIDES_BY_CITY` now covers all nine cities, and **`--check-names` asserts every label against that district's own House of Commons Library MSOA name**, evidence checked in at `data/district-msoa-names.json` so the gate needs neither NSPL nor a network. Blocking in preflight. **273 → 5**, the five being Bath ×2 and Darlington ×3, left as post towns on purpose.

**A district is published only if it is MAJORITY INSIDE the city publishing it (2026-08-12).** Transactions are bucketed by the Land Registry `district` field, a LOCAL AUTHORITY, but an entry is published as a POSTCODE DISTRICT, Royal Mail's — and those do not nest. **WA8 was 4% inside Knowsley and 94% inside Halton, which we do not cover**, so it published a Knowsley median of £345k off 32 sales — Merseyside's *fourth priciest* entry — under the label "Widnes", at a centroid averaged over all 1,591 postcodes and therefore sitting in Halton. Every step was arithmetically correct; the join was wrong. 34 of 501 were under 75% contained, 8 under 20%. **18 dropped**, 503 → 485.

- **`lat/lon` and `postcodes` now cover the COVERED part only**, so the marker sits in what the price describes. This moved 43 retained markers, Darlington (DL2, 64%) by **4.4 km**.
- **A district belongs to exactly ONE city.** WN4 and WN5 straddle Wigan/St Helens and were published TWICE at identical coordinates — WN5 as `Pemberton & Orrell` £165k in Greater Manchester *and* `Billinge` £235k in Merseyside. At the 50% floor the arbitration cannot fire (two cities cannot each hold a majority) but it is kept for `--min-containment` below 0.5.
- **The label is the part that cannot be repaired by maths.** The covered slice of WA8 has no name of its own; "Widnes" is the only name the district has. That is why the floor drops rather than relabels.

- **Deriving the name was tried and rejected ON MEASUREMENT.** A district spans 4–13 MSOAs, so the modal name carries 15–33% and names a sub-area: BS8 came out `Clifton East`, SK5 came out `Brinnington` when the district is Reddish, and a shared-token variant gave `Five` for B16, `Quays` for M50 and `Mossley` for **both** L17 and L18 — recreating the duplicate it was meant to fix. Manchester's 26 hand-written names were the answer key.
- **The check caught four names that had shipped for months** — `Chorlton-on-Medlock` (M13 is Ardwick and Victoria Park), `Chorlton-cum-Hardy`, `Ancoats & Northern Quarter`, `The Heatons` — plus `West Derby` and `Kelham Island`, none of which any published source places in those districts.
- **It cannot catch a name that is merely the NEIGHBOUR's**: MSOA lists reach over district boundaries, so `CH47: Hoylake & West Kirby` corroborated cleanly while CH48 *is* West Kirby. Read the sibling districts before writing a label.
- **A dict keyed to a city nobody looks up passes perfectly and reaches nothing.** Four of the eight were first written `west_midlands` / `south_yorkshire` when the builder's keys are `westmidlands` / `southyorkshire`: the check read all-285-green while **163 of them were dead**. There is now an UNKNOWN CITY KEYS guard, and the marker-derived `DEFAULT_CITIES` is the only source of truth for a city key.

Sky Score, a property noise + livability data tool for UK and NYC. Originally built for the Amazon Nova AI Hackathon; pivoted in May 2026 from "AI-powered" to "data-first" positioning. Consumer site is the marketing engine; the B2B `/v1/score` API is the product. Single-page frontend (`index.html`) plus B2B funnel pages (`/api/`, `/pricing`, `/privacy`) backed by the 8 active AWS Lambda functions orchestrated via SAM (the 4 dormant Bedrock Lambdas live in git history only; `live_flights` was removed in May 2026 pending OpenSky licensing).

## Scale direction — do NOT "fix" the apparent site/extension disagreement

**Scores rise, measurements rise, and the label names which.** See `METHODOLOGY.md` §11.0.

- **Scores** (0–10 components) run **higher = better** and are labelled with the *good* thing: `Quiet Skies`, `Affordability`, `Liveability`. Site score panel and `/v1/score`.
- **Measurements** run **higher = worse** and are labelled with the *bad* thing: `Road noise 49.5 dB Lden`, `Aircraft noise 2/10 noise`. `/v1/environment` and the extension's Environment section.

So the same postcode reads **`Quiet Skies 8/10` on the site** and **`Aircraft noise 2/10` in the extension**. That is one value under two labels, *not* a divergence: `/v1/environment` returns `aircraftQuietEstimated: 8` and the extension shows `10 − 8`, asserted against the live endpoint in `tests/extension-e2e.mjs` (on an **asymmetric** value — SW5 scores 5, which inverts to itself and cannot detect a missing transform).

The rule is not "noise always goes up" — it is that direction must agree with whatever the number sits *beside*. Until 2026-08-08 the extension rendered a quiet score under a "noise" label, so the longest bar in the section marked the quietest row. Harmonising the two surfaces reintroduces that defect in one direction or the other.

## Branding

Always use "Sky Score" in all public-facing files and UI text.

## Do NOT add Co-Authored-By lines to git commits

## Quality & Plugins

- Run `/preflight` before every commit — or directly: **`sh scripts/preflight.sh`** (also `npm run preflight`, `make preflight`; all three invoke the same script so they cannot drift apart). Blocking: ESLint (now `.js`/`.mjs` too, not just `index.html`), html-validate, ruff over `backend/lambdas` + **`backend/tests/`** + `scripts/` + `tests/`, **both** pytest suites, **extension extraction + extension e2e + responsive (10 viewports, now run against SOURCE as the blocking half and against CloudFront as an advisory one — the same split `a11y-source.mjs` makes, because pointed only at live it goes red on a tree that has already fixed the defect and stays red until deploy) + `every city switches`** (added 2026-08-06; the responsive audit fails on horizontal overflow **and, since 2026-08-11, on a control past the viewport edge with no scrollable ancestor** — it had always BUILT that list and only PRINTED it when the page itself scrolled sideways, so the city chips clipped by the map container's `overflow: hidden` left it reading "ok" at all ten viewports while three of eight UK cities could not be tapped at 320px; tap-target findings stay advisory because they need judgement; `every city switches` is `tests/city-switch.mjs`, added the same day because nothing had ever clicked a city chip; the e2e loads the extension into a real Chromium and needs `--headless=new`, since Playwright's normal headless uses `chromium_headless_shell` which does not load extensions at all), API-URL drift, **score sanity against the live API** (`scripts/check_score_sanity.py` - the only stage that can catch a DATA defect; the pytest suites never reach DynamoDB and Playwright asserts the site against itself), **no em dashes on the 9 deployed pages** (`terms.html` joined 2026-08-05), **self-hosted fonts on all 9** (`tests/fonts-selfhosted.mjs`, serves the repo locally so it validates source before a deploy), **log retention == `privacy.html`** (`scripts/check_log_retention.sh` — see below; it now parses the claim out of `privacy.html` and passes honestly), **WCAG over the SOURCE tree** (`tests/a11y-source.mjs`, added 2026-08-10 — the Playwright a11y spec scans CloudFront, so an accessibility regression could not be caught until it was already serving users, which is exactly how the locator inset shipped `role="img"` around ten focusable markers; this one serves the repo on 8923 with the CloudFront extensionless rewrite reproduced, and gates the deploy where the e2e one catches a bad deploy), **prices == HM Land Registry** (`scripts/build_hpi_prices.py --check --all`, added 2026-08-10 — the only gate that can catch a PARTIAL VINTAGE ROLL, and written because there was one: London's `avgPrice` matched HPI 2026-05 for all 33 boroughs while its `trend` matched **no** HPI month, under a `CITY_PROVENANCE` sentence telling customers it was HPI. Keyed on **ONS codes, not names** — name matching has failed here five times. `--write` corrects BOTH holders or neither), and Playwright at `--workers=2`
  - **`log retention == privacy.html` is BLOCKING and now PASSES, honestly (2026-08-06).** It asserts that AWS matches **whatever `privacy.html` §2d claims** — it parses the figure out of the page rather than hardcoding one. Until 2026-08-06 it hardcoded `WANT_DAYS=30` and never opened `privacy.html` despite its name, so the only route to green was the console work, and switching §2d to the honest interim wording left the gate **red on a truthful tree**. `DRAFT_security_retention_passage.md` §2b had flagged exactly this. The rewrite is strictly stronger: it still reds on "page says 30, AWS says None" and additionally reds on the reverse, which the old one could not see. **Both failure directions are proven red, plus an unparseable-claim case.** §2d now carries **Version B** ("currently retained indefinitely"), which is true, so page and infrastructure agree. **Still outstanding:** the console work in §1 — 6 orphaned log groups from removed Lambdas remain, and the Signup one holds raw emails from 26 Jun–23 Jul 2026 in a location §2b does not disclose. Those **WARN, they do not fail**, because under an "indefinite" claim they do not contradict the page and deleting them needs `logs:DeleteLogGroup`, which `flightmap-dev` lacks — blocking there would gate every commit in the repo on a console action. When the console work lands, flip §2d back to Version A and the same check validates it. Gotcha: the AWS CLI here emits **CRLF**, so `retention=None\r` never string-equals `None`; the script strips `\r` and that line is load-bearing. Advisory: Prettier, npm audit, **`deployed == source`**, **`site == /v1/score`**.
  - **`backend/tests/` joined the ruff targets on 2026-08-04.** It had been outside every one of them — the suite guarding the score engine was the one directory nothing linted, and it held 4 import-order errors and an S105.
  - **The two new advisory stages both compare DEPLOYED state**, which is why they are advisory rather than blocking. `scripts/check_deploy_drift.sh` compares all 14 public surfaces against what CloudFront serves (drift between commit and deploy is expected, so blocking it would go red on nearly every run). `tests/site-api-parity.mjs` compares the score the **live site renders** against what `/v1/score` returns — the only check that reads the *output* rather than the inputs, added after the site and API disagreed on 13% of London postcodes while every component matched. Promote either to `check` once it has a track record; both already exit non-zero only on a measured problem.
  - **Read the exit code, never pipe it.** `preflight | tail` is always 0 — a pipeline exits with its LAST stage's status. That is exactly how `make preflight` reported success on 2026-07-27 while running nothing at all (`make` is not on PATH in Git Bash here).
  - `--skip-e2e` skips Playwright, which hits the live site. `--fix` auto-fixes what is auto-fixable.
  - Rewritten 2026-07-27 after the gate produced a false green, a false red, and silently omitted the 167-test root suite. Change what blocks in `scripts/preflight.sh`, **not** in the skill file.
- Run `/careful` before touching live AWS resources, blocks destructive commands
- ~~Use `/aws-debug` when Lambda errors or API Gateway 5xx issues occur~~ **`/aws-debug` does NOT work on this account** (verified 2026-07-26): `flightmap-dev` is denied `logs:FilterLogEvents`, `logs:GetLogEvents`, `logs:DescribeLogStreams`, `cloudtrail:LookupEvents`, `iam:GetRolePolicy`, `lambda:ListFunctions` and `cloudformation:DescribeStackResource`. Only `logs:DescribeLogGroups` (names) works, and the `default` profile's token is invalid. Until a console-side grant lands, debug Lambda faults from the **console** or by **side-effect elimination** — see `OPERATIONS.md` §6. Prefix any `/aws/lambda/...` CLI argument with `export MSYS_NO_PATHCONV=1` or Git Bash mangles it.
- Use **context7** to look up D3.js, AWS SDK, or SAM docs before using unfamiliar APIs
- Use **security-guidance** when editing Lambda functions or API Gateway config
- Use **code-review** on all changed files before committing
- Use **frontend-design** when modifying the UI in index.html

## Build & Deploy

**Prefer the make targets; the commands below are the manual fallback.** As of
2026-08-04 every publicly-served file has one, and `make web-deploy-all` covers
all 15 surfaces:

| Target | Covers |
|---|---|
| `fonts-deploy` | **new (2026-08-05)** — self-hosted `fonts/`. **Runs FIRST in `web-deploy-all`, and that ordering is load-bearing**: three font files are in `sw.js` `SHELL_ASSETS` and `cache.addAll()` is atomic, so shipping `sw.js` before the fonts exist at the origin makes the service worker fail to install at all |
| `web-deploy` | `index.html`, privacy, pricing, changes, **terms**, `api/`, `js/` |
| `data-deploy` | `data/*` (gets `borough-extra.json`'s load-bearing `no-cache` right) |
| `pwa-deploy` | manifest, `sw.js`, icons |
| `demo-deploy` | **new** — all 7 `score-demo/` files incl. the vendored Swagger UI |
| `prototype-deploy` | **new** — `prototype/index.html` |
| `meta-deploy` | **new** — `robots.txt`, `sitemap.xml`, `.well-known/security.txt` |
| `web-deploy-all` | all of the above, `fonts-deploy` first |

The last three were added closing audit finding 38: **eleven live files had no
deploy command anywhere** and had reached production by hand-upload, which is
how `api/index.html` sold the product on retired claims for months.
`web-deploy-all` previously covered **4 of 15** surfaces while being named
"all". Run `sh scripts/check_deploy_drift.sh` to see what is currently stale.

**`make` is not on PATH in Git Bash here**, and there are **no `deploy:*` npm
aliases** despite the Makefile header once claiming otherwise — so on this
machine the manual commands below are what actually runs. Fixing that properly
means one shared script behind all three entry points, as `preflight` already
does.

```bash
# Shared API base URL constant (loaded by index.html, score-demo/index.html,
# score-demo/status.html). Deploy alongside any frontend change that depends
# on it; the file rarely changes (only on APIGW id rotation), so most deploys
# can skip this line. Wave 12.9 / I-N5 offensive half.
AWS_PROFILE=flightmap aws s3 cp js/api-base.js s3://london-flight-map-frontend/js/api-base.js --content-type "application/javascript" --region eu-west-2

# Self-hosted fonts (added 2026-08-05). Deploy these BEFORE sw.js — three of
# them are in SHELL_ASSETS and cache.addAll() is atomic, so a missing font at
# the origin stops the service worker installing entirely. Regenerate with
# `python scripts/vendor_fonts.py`; they change only when that script is re-run.
AWS_PROFILE=flightmap aws s3 cp fonts/ s3://london-flight-map-frontend/fonts/ --recursive --exclude "*" --include "*.woff2" --content-type "font/woff2" --cache-control "public,max-age=31536000" --region eu-west-2
AWS_PROFILE=flightmap aws s3 cp fonts/fonts.css s3://london-flight-map-frontend/fonts/fonts.css --content-type "text/css" --cache-control "public,max-age=86400" --region eu-west-2

# Frontend, upload to S3 then invalidate CloudFront
AWS_PROFILE=flightmap aws s3 cp index.html s3://london-flight-map-frontend/index.html --content-type "text/html" --region eu-west-2
AWS_PROFILE=flightmap aws cloudfront create-invalidation --distribution-id EGSSPJKLFL33M --paths "/*"

# Pricing + privacy + changes pages — MUST target <name>/index.html keys (the
# sky-score-rewrite-index CloudFront function rewrites extensionless
# paths to <path>/index.html; a flat "pricing" key is never served).
AWS_PROFILE=flightmap aws s3 cp pricing.html s3://london-flight-map-frontend/pricing/index.html --content-type "text/html" --region eu-west-2
AWS_PROFILE=flightmap aws s3 cp privacy.html s3://london-flight-map-frontend/privacy/index.html --content-type "text/html" --region eu-west-2
AWS_PROFILE=flightmap aws s3 cp terms.html s3://london-flight-map-frontend/terms/index.html --content-type "text/html" --region eu-west-2
AWS_PROFILE=flightmap aws s3 cp changes.html s3://london-flight-map-frontend/changes/index.html --content-type "text/html" --region eu-west-2

# Data assets. NOT covered by the index.html line above and absent from this
# file entirely until 2026-08-03, which is how the Cache-Control gap below went
# unnoticed. borough-extra.json carries every borough's crime, schools,
# transport and healthcare inputs, so a stale copy means wrong scores.
#
# --cache-control "no-cache" is LOAD-BEARING, not tidiness. The object shipped
# with no Cache-Control at all, and index.html fetched it with
# cache: 'force-cache' - serve any cached copy WITHOUT revalidating - so a
# browser could pin it indefinitely. A user was served crime figures from before
# the 2026-08-02 correction, days after it shipped.
#
# Bumping sw.js does NOT fix this. That evicts the service worker's caches; the
# stale copy lived in the browser's HTTP cache, which force-cache had opted out
# of freshness checks entirely. Prefer `make web-deploy-all`, which gets this
# right; these lines are the manual fallback.
AWS_PROFILE=flightmap aws s3 cp data/borough-extra.json s3://london-flight-map-frontend/data/borough-extra.json --content-type "application/json" --cache-control "no-cache" --region eu-west-2
AWS_PROFILE=flightmap aws s3 cp data/london-boroughs.json s3://london-flight-map-frontend/data/london-boroughs.json --content-type "application/json" --region eu-west-2
AWS_PROFILE=flightmap aws s3 cp data/nyc-boroughs.json s3://london-flight-map-frontend/data/nyc-boroughs.json --content-type "application/json" --region eu-west-2


# PWA assets — REQUIRED for the install prompt + offline SW to work. These are
# NOT covered by the index.html line above; they were missing from the live
# origin until 2026-05-21 (every asset 403'd → no manifest → install button
# silently dead). Re-deploy whenever manifest.webmanifest, sw.js, or the icons
# change (rare). Content-types matter: a wrong manifest type fails Chrome's
# installability check.
AWS_PROFILE=flightmap aws s3 cp manifest.webmanifest s3://london-flight-map-frontend/manifest.webmanifest --content-type "application/manifest+json" --region eu-west-2
AWS_PROFILE=flightmap aws s3 cp sw.js s3://london-flight-map-frontend/sw.js --content-type "application/javascript" --region eu-west-2
AWS_PROFILE=flightmap aws s3 cp icons/icon.svg s3://london-flight-map-frontend/icons/icon.svg --content-type "image/svg+xml" --region eu-west-2
AWS_PROFILE=flightmap aws s3 cp icons/icon-maskable.svg s3://london-flight-map-frontend/icons/icon-maskable.svg --content-type "image/svg+xml" --region eu-west-2

# Score demo (B2B API tester), same pattern as prototype
AWS_PROFILE=flightmap aws s3 cp score-demo/index.html s3://london-flight-map-frontend/score-demo/index.html --content-type "text/html" --region eu-west-2
AWS_PROFILE=flightmap aws cloudfront create-invalidation --distribution-id EGSSPJKLFL33M --paths "/score-demo/*"

# Backend, SAM build + deploy (always clean .aws-sam first)
# EPC bearer token is required after the 2026-05-30 service migration.
# Source from .env (gitignored); never paste the token into source files or chat.
# NOTE (corrected 2026-08-04): this line said `source ../.env`, which does not
# exist — `.env` is at the repo root, and `../.env` would be
# `C:\Users\bilal\projects\.env`. Because the whole block is `&&`-chained, the
# failed source ABORTED THE ENTIRE DEPLOY rather than falling through, so the
# documented command could never have worked from the repo root. Verified by
# running it during the 2026-08-04 signup deploy.
#
# Second gotcha, same deploy: the Bash tool's working directory PERSISTS between
# calls while environment variables do NOT, so splitting build and deploy across
# two invocations lands the second one in backend/ with no EPC_BEARER_TOKEN.
# Use absolute paths, or keep source + build + deploy in one invocation.
set -a && source .env && set +a && \
  cd backend && rm -rf .aws-sam && \
  AWS_PROFILE=flightmap sam build && \
  AWS_PROFILE=flightmap sam deploy --parameter-overrides \
    EpcBearerToken="$EPC_BEARER_TOKEN"
```

**Local env setup**: copy `.env.example` to `.env` and fill in:
- `EPC_BEARER_TOKEN` — from the My account page on `get-energy-performance-data.communities.gov.uk`
- `ASC_KEY_ID` / `ASC_ISSUER_ID` / `ASC_KEY_FILE_PATH` — for fastlane (see `mobile/CODEMAGIC_SETUP.md`)
- `FASTLANE_SKIP_DOCS=1` — non-optional, stops fastlane overwriting `mobile/fastlane/README.md`

The `.env` file is gitignored. The EPC SAM parameter uses `NoEcho: true` so the value doesn't appear in CloudFormation events. AllowedPattern `^.+$` on the parameter blocks deploys with empty / missing tokens.

**Token rotation**:
- EPC: regenerate from the My account page on `get-energy-performance-data.communities.gov.uk` whenever the token has touched a chat log, terminal scrollback, or any unencrypted persistence
- Update `.env` and redeploy after rotation

## Architecture

- **Browser extension** (`extension/`, added 2026-08-06): unlisted MV3 demo showing `/v1/environment`, `/epc`, `/sold-prices` and `/nhs` data on Rightmove listings. (Transport was dropped 2026-08-06 — Rightmove already prints nearest stations with distances, so the section duplicated the page it sat on. This line said `/transport` for a day after it was removed.) **Not for publication** — see `extension/README.md` for the ship gates. **Panel UI reworked 2026-08-07, extended 2026-08-08**: each measurement carries a scale bar positioned against its WHO guideline (domain is 0 to twice the guideline, because the observed-London-range alternative would be a number invented at the point of drawing it), explanatory prose collapses into one disclosure, and the DEFRA vintage is a `2021` tag on the two rows it applies to rather than a paragraph under rows it does not. **EPC and Sold nearby now lead with a chart and fold their rows into `<details>`**; the panel collapses to its header on a header click. The EPC chart is **seven discrete band columns, deliberately not a `scaleBar`** — `cert.rating` looks plottable but is synthesised from `BAND_MIDPOINT` in the Lambda (MHCLG dropped the numeric rating), so every C returns exactly 75. The sold chart marks the **asking price**, which `extract.js` now READS but still never transmits, and only on a positive `RES_BUY`/`BUY` signal — on a letting Rightmove's `price` is a monthly figure and would plot as an extraordinary bargain. **Gotcha: `display: flex` on a `<summary>` removes the `::marker` box in Chrome**, so `list-style: revert` cannot restore the disclosure triangle; the panel draws its own. **Sales and lettings get the same section ORDER and different CONTENT** (2026-08-08): on a letting Sold nearby is replaced by **Typical rent** (ONS borough average, `extension/data/london-rents.json`, rebuild with `scripts/build_london_rents.py`) and EPC gains a MEES line. Promoting EPC to the top on lettings was tried and **reverted** — moving sections between listing types reads as inconsistency, not judgement. The rent figure is **deliberately not a chart**: it is a borough-wide average and the sold-price grammar would claim a comparable. The dataset is **bundled and served by the service worker**, never `web_accessible_resources` (which exposes it to every host page), so it needed **no Lambda change and no deploy**. Extraction is a five-strategy cascade and is deliberately site-agnostic; the only Rightmove-specific part is `fromRightmovePageModel()`, which unpacks `window.__PAGE_MODEL` (a JSON *string* holding a *flattened* array where `{"latitude":160}` is an **index**, not a value). `run_at` is `document_end`, **not** `document_idle` — the page model is transient and React hydration removes it, so idle arrives after the data is gone. `tests/fixtures/rightmove-real-sw5.html` is a real saved listing and is the only fixture that can contradict its author; 33 green checks once coexisted with an extension that had never worked on a real page.
- **DEFRA raster quarantine LIFTED 2026-08-06.** `RASTER_TIER_QUARANTINED = False`. The blocker was that `index.html` computed quiet from geometry while `/v1/score` would answer from the raster, diverging on the ~9% of London DEFRA measures. Closed by `data/aircraft-quiet-london.json` (35,352 postcodes, 461 KB), which ships the **computed quiet score, not decibels**, so neither side reimplements the ramp. **Regenerate with `python scripts/build_aircraft_quiet_dataset.py` whenever `lden_db_to_quiet` changes** - the file embeds `methodologyVersion` and the page refuses a mismatch. Deploying the file without the Lambda, or vice versa, recreates the divergence.
- **Mobile city switcher is a horizontal SCROLL STRIP** (≤900px), added 2026-08-11. With nine cities the chip row was 453px wide against a 375px viewport and `position: absolute` with only `left` set, so it sized to content and the map container clipped it: **3 of 8 UK cities untappable at 320px**, 2 at 375/390. `right: 60px` bounds the row and clears the map-controls column; `flex: 0 0 auto` makes chips scroll rather than squash; the active chip is scrolled into view on render. **The edge fade is load-bearing** — `data-scroll` is measured and set to `right`/`left`/`both`, because this app already retired one scroll strip (the layer toggles, see the comment by `.layers-trigger`) for the exact reason that a strip with no affordance reads as absent. **The sheet still opens over the map on phones ≤640px and that is deliberate** (`index.html`, `setSheetState('open')` at boot); it carries an Apple Guideline 4.0 rejection scar from 2026-05-18.
- **Frontend**: Single `index.html` (~8,200 lines as of 2026-07-24), vanilla JS, D3.js maps, all UI logic inline. **The mobile bottom-nav redesign is NATIVE-APP ONLY as of 2026-05-29** (web/native split): the redesign (`#mobile-nav` + `.app[data-mview]` 3-tab views via `setMobileView()`, map-as-background) is gated behind an `is-native` class that `setupNativeFeatures()` adds to `<html>` only inside the Capacitor app. **The website — desktop, mobile browser, and PWA — serves the classic bottom-sheet layout** (`.sheet-handle` + `setSheetState()`); the iOS/Android apps get the redesign. The redesign's base CSS rules are `.is-native`-prefixed and `setMobileView()` (sole writer of `data-mview`) bails unless `is-native`. Desktop (≥901px) keeps the two-column grid regardless. See `MOBILE_REDESIGN_PLAN.md` (v3 section).
- **Backend**: `backend/template.yaml`, SAM/CloudFormation defining the 8 active Lambdas + API Gateway + DynamoDB. (Was 7 until 2026-08-06, when `chat` was restored to the template as a retrieval-only function; count the `AWS::Serverless::Function` blocks rather than trusting any prose, here or elsewhere.)
- **B2B funnel pages** (deployed alongside `index.html`): `/api/` landing (`api/index.html`), `/pricing` (`pricing.html`, added 2026-07-23: 90-day £2,500 pilot + Free/£499 Professional/Enterprise tiers + founder block), `/privacy` (`privacy.html`). **S3 key gotcha:** the `sky-score-rewrite-index` CloudFront function rewrites extensionless paths to `<path>/index.html`, so privacy/pricing MUST be uploaded to `privacy/index.html` and `pricing/index.html` keys (`make web-deploy` does this correctly since 2026-07-23; a flat `privacy` key is a dead object).
- **Active Lambdas** (in `backend/lambdas/<name>/app.py`):
  - `score`, B2B scoring engine. API-key gated on `/v1/score`, `/v1/score/batch`, `/v1/regions`, `/v1/changes`. **`/v1/environment?lat=&lon=` is UNAUTHENTICATED** (added 2026-08-06): it reverse-geocodes a coordinate and returns MEASUREMENTS only (aircraft/road Lden, NO2, PM2.5, each with its WHO guideline) - no weights, no persona, no composite score, because the browser extension is a public artefact and cannot hold a key. Throttled 5 RPS.
  - `chat`, **retrieval-only** assistant (`POST /v1/chat`, API-key gated), restored 2026-08-06 from `6bad8ce`. The model never supplies data: context comes from invoking `ScoreFunction` DIRECTLY, and `verify_answer()` DISCARDS any reply containing a number absent from the retrieved payload. That control fired in production on the third live question - a 2030 price forecast the prompt had forbidden. Do NOT "simplify" it to a free-form call.
  - `signup`, self-service API-key issuance
  - `favourites`, DynamoDB CRUD with `X-Device-Token` auth
  - `epc`, MHCLG EPC certificate proxy (bearer-token auth via `EPC_BEARER_TOKEN`)
  - `sold_prices`, HM Land Registry Price Paid Data proxy
  - `transport`, TfL Open Data station + line-status
  - `nhs`, NHS Service Search via OSM Overpass
- **Dormant Lambdas** (NOT in `template.yaml`):
  - `multi_agent`, `analyze_image`, `analyze_document`, `report` — all Bedrock Nova Pro/Lite. Code + template entries live in git history only; re-introduction means restoring both from history and redeploying, then unhiding the UI block. **`chat` left this list on 2026-08-06** and is active again — but as a *retrieval-only* function, not the free-form Bedrock one that was parked here. Its dead log group (`ChatFunction-wzeXuMdafiCz`) still exists alongside the live one (`ChatFunction-LuxoNSLxJMva`); see `DRAFT_security_retention_passage.md` §1.
- **Removed**: `live_flights` (OpenSky proxy) — terminated in May 2026 pending OpenSky's required written licensing agreement for operational use. Lambda code lives in git (last working commit: `a214ba0`); restore + add OpenSky params back to template + flip the prototype's `liveLicensed` flag to revive.

## Prototype (Sky Score Radar)

- **Location**: `prototype/index.html`, standalone HTML, no dependencies on main app
- **Live URL**: `https://d1oe4ftwutjpf.cloudfront.net/prototype/index.html`
- **Stack**: Three.js (CDN), CSS2DRenderer for labels, UnrealBloomPass for bloom
- **Features**: 3D wireframe terrain, day/night cycle (real GMT/BST), noise contour rings, borough boundaries, corridor heatmap/timelapse, simulated flight tracks (live OpenSky data removed pending licensing — see Active Lambdas note above)
- **Controls**: `R` Reset, `1-3` Camera presets, `P` Screenshot, `N` Time-lapse, `C` Contours, `B` Boroughs, `V` Corridor view (Daily/Weekly/Monthly), `T` Timelapse replay, `H` Heatmap toggle
- **Mobile**: Fully responsive, touch button bar replaces keyboard shortcuts, collapsible panels via ☰ menu, breakpoints at 768px and 480px. OrbitControls supports pinch/drag natively.
- **Analytics**: GoatCounter (same `cubitt33` tracker as main site), prototype visits appear as `/prototype/index.html`
- **Naming**: Use "Sky Score Radar" for the prototype, "Sky Score" for the main app
- **Deploy**: `AWS_PROFILE=flightmap aws s3 cp prototype/index.html s3://london-flight-map-frontend/prototype/index.html --content-type "text/html" --region eu-west-2`

## PWA + Native (Capacitor + Codemagic)

Sky Score has three install paths from the same `index.html`:

1. **Web** — anyone visits skyscore.co.uk, no install
2. **PWA** — Install prompt in Chrome/Edge/Android; iOS Safari uses Share → Add to Home Screen. Manifest at `/manifest.webmanifest`, service worker at `/sw.js`.
3. **Native iOS / Android** — Capacitor wrap at `mobile/`, distributed via App Store + Play Store. **Split build pipeline** mirroring the Noor pattern:
   - **iOS**: built by Codemagic in cloud Mac (no local Mac available)
   - **Android**: built locally via Android Studio + gradle on Windows (Codemagic Android workflow not used; cloud Linux time was overhead since gradle runs fine on Windows)

The same `index.html` runs in all three contexts. Native-only features (geolocation "Score where I am" button, share sheet) feature-detect via `window.Capacitor.isNativePlatform()` — invisible on web/PWA.

```
mobile/
  capacitor.config.ts       # appId uk.co.skyscore.app, light theme
  package.json              # isolated; @capacitor/* + plugins
  scripts/copy-web.mjs      # assembles mobile/www/ from parent
  assets/                   # icon source SVGs (logo, foreground, background, splash)
  CODEMAGIC_SETUP.md        # iOS-only: ASC API key + dashboard config
  ANDROID_BUILD.md          # local Android Studio + gradle workflow
  STORE_LISTINGS.md         # paste-ready App Store + Play Store copy
  APPLE_REVIEW_NOTES.md     # Section 4.2 review notes for App Store
  PRIVACY_POLICY.md         # GDPR-compliant draft for /privacy
  RELEASE_CHECKLIST.md      # 9-step pre-release runbook (dual-path)
  DEEP_LINKING.md           # iOS Universal Links + Android App Links setup

codemagic.yaml              # repo root; ios-workflow only
```

**Update cadence:** web changes (CSS, JS, copy) deploy to CloudFront immediately. Native binaries need a build + store review (~2-3 days Apple, ~1 day Google). Plan binary releases every 2–4 weeks at most — more often than that isn't worth the review-cycle cost.

**Local dev:**
```bash
cd mobile
npm install                  # one-off
npm run sync                 # rebuilds mobile/www/, syncs Capacitor
npx cap open android         # Android Studio (for the actual Android build)
```

iOS native project is regenerated by Codemagic's `ios-workflow` on each cloud build — `npx cap add ios` runs in the cloud Mac, not locally. Android native project lives at `mobile/android/` and is built locally per `mobile/ANDROID_BUILD.md`.

**Apple Section 4.2:** the "Score where I am" button using native GPS is the App Store "Minimum Functionality" defence. Verbatim review-notes copy lives in `mobile/APPLE_REVIEW_NOTES.md`.

## AWS Resources

- **API Gateway**: `https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/`
- **CloudFront**: `https://d1oe4ftwutjpf.cloudfront.net` (distribution EGSSPJKLFL33M)
- **S3 bucket**: `london-flight-map-frontend` (eu-west-2)
- **DynamoDB tables** (4, all PAY_PER_REQUEST, eu-west-2): `london-flight-map-favourites`, `london-flight-map-signups`, `london-flight-map-noise-raster` (DEFRA Lden samples, loader `scripts/load_defra_raster.py`), `london-flight-map-postcodes` (ONS NSPL index, loader `scripts/load_nspl.py` — **fully loaded 2026-07-26: 2,699,393 rows, February-2026 vintage; roll to the August 2026 edition when it ships**). Both loaders run locally, not in Lambda, and both tables are forward-compatible: the score Lambda works correctly when they are absent or empty and upgrades silently once data lands, so **loading never needs a second deploy**.

  **NSPL loader speed (2026-07-27):** `_flush_batch` uses `BatchWriteItem`, but that needs `dynamodb:BatchWriteItem` on `flightmap-dev`, which is **in `backend/iam-policy.json` and not yet applied to the live policy**. Until it is, the loader detects the denial on its first chunk and completes on the old per-item path at ~129 rows/s — so **a vintage roll that takes ~6 hours is the signal the grant never landed**. Verify a load with `get-item`, never `describe-table`'s `ItemCount` (it refreshes ~6-hourly and reads 0 throughout).

  **Loader write policy is SHARED, in `scripts/ddb_write.py` (2026-08-09).** Both DEFRA loaders import it; do not paste the retry logic into a third loader, and do not fork `FATAL_CODES` — two copies drift into one loader waiting out an error the other raises on, visible only during a multi-hour run nobody is watching. It exists because both DEFRA loaders kept dying mid-run with a bare boto3 client: sleep at 21:28:12 on 8 Aug, checkpoint stopped at 21:27. Sleep does not kill the process, it kills the in-flight connections, and an unguarded `ex.map` turns that into a fatal. The 30-minute wait is **bounded on purpose** — unbounded, an IAM denial spins forever, which is what `load_nspl.py` did when `BatchWriteItem` was refused. Covered by `tests/test_ddb_write.py` (13 tests, both failure directions proven red).

  **Run long loads detached and unbuffered**, or the next death is as undiagnosable as the last two — neither left a log, and the cause had to be read out of `Get-WinEvent -ProviderName Microsoft-Windows-Kernel-Power`. Use PowerShell `Start-Process` with `python -u` and redirected output so the run outlives the session. Check liveness with `sh scripts/load_status.sh` (reads checkpoint *mtime*, not file existence); a stopped loader resumes by re-running the same command.

  **Coverage lands alphabetically, and central London is LAST.** NSPL is scanned in postcode order, so the first `SW` row is at ~85% of a full pass and the first `W` at ~93%. A partial run therefore looks healthy from an outer-London spot check while the West End holds nothing — exactly how road coverage came to be published as "99.2%" while `W`, `WC` and `WD` had never been served a reading.
- **Bedrock models** (only relevant if the dormant Bedrock Lambdas are ever restored from git history): `us.amazon.nova-2-lite-v1:0` (simple) + `us.amazon.nova-pro-v1:0` (complex/multimodal)
- **API custom domain**: `api.skyscore.co.uk` — APIGW edge custom domain (created 2026-07-23, cert = the us-east-1 wildcard, base-path mapping → `prod`). Serves once Cloudflare has `CNAME api → d1pr4crjutz9z8.cloudfront.net` (DNS only / grey cloud). The raw execute-api URL keeps working regardless.
- **IAM**: `flightmap-dev` user, `FlightMapDeployPolicy`
- **Region**: eu-west-2 (London)

## Key Conventions

- All Lambda handlers follow the same pattern: `def lambda_handler(event, context)` with CORS headers
- Frontend communicates with backend via fetch to API Gateway endpoints
- SAM stack name: `london-flight-map`

## Submissions

- **Amazon Nova AI Hackathon** (March 2026): Submitted, won $200 AWS credits (blog-post category). Video demo (3:10, with voiceover) complete.
- **Red Bull Basement** (submitted 2026-04-12): Awaiting shortlist decision; if invited, record 60-second pitch video. Positioning: "local friend" AI for renters with health risks.
- **Emergent Ventures / Mercatus** (submitted 2026-04-20): £45,000 ask over 9 months. Awaiting response (form promises within ~1 week). Draft at `Desktop/emergent-ventures-application.txt`.
- **Luma event** (applied 2026-04-23, `luma.com/vy4bnkom`): Submitted Sky Score as the idea (3-sentence pitch). Form fields: name, email, LinkedIn, GitHub (`billkhiz-bit`), phone, cofounder status. No project-URL field on the form. Event name/theme TBC.

Related separate project (not in this repo): **LedgerAgent** is a semi-finalist in the AWS 10,000 AIdeas Competition.

## Store Releases

- **iOS — v1.0.21 (mobile redesign) LIVE on the GB App Store.** <https://apps.apple.com/gb/app/sky-score/id6768118116> (App Store ID `6768118116`). Build 21 / version `1.0.21` — the native-only mobile redesign (web/native split; built via Codemagic from commit `4af9bc5`, iPhone-only to sidestep iPad review) — was submitted 2026-05-29 and subsequently approved; the public listing showed v1.0.21 (updated 1 Jun 2026, 1 rating at 5.0) per the 2026-07-19 store-listing audit. Screenshots at 1242×2688 (`store-screenshots/`); "What's New" in `mobile/fastlane/metadata/ios/en-GB/release_notes.txt`. Verify live anytime via `curl "https://itunes.apple.com/lookup?bundleId=uk.co.skyscore.app&country=gb"`. **The site footer links the listing since 2026-07-23** (trust-fix bundle, `appstore-footer-click` GoatCounter event).
- **Android — pending.** AAB stale relative to master; rebuild via `npm run build:android` (now fixed for Windows — uses `gradlew.bat`; needs `JAVA_HOME` = Android Studio JBR + `SKY_SCORE_KEYSTORE_PATH`/`SKY_SCORE_KEYSTORE_PASSWORD` env vars, password in Bitwarden) to carry the iPad fix + mobile redesign, then resume the Play Console flow in `HANDOFF_2026_05_16_play_submission.md`.

## Known Issues

See `AUDIT_REPORT.md` (last full audit 2026-07-24) for the live list. The long-standing trio closed 2026-07-24: I4 (borough metadata duplication — resolved by removal, `score/app.py` is the single holder), I6 (DLQ on async Lambdas — moot, all 7 functions are APIGW-synchronous), I14 (`PROJECT_DOCUMENTATION.md` — fully refreshed).

Most of the May-6 critical findings have shipped fixes — see `AUDIT_REPORT.md` for the triage column.
