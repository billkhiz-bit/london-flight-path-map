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
- **`archive/BUILDATHON_PLAN_2026.md`**, the Shared Futures Buildathon plan (event was 2026-06-07). Archived 2026-08-24, 78 days after the event, exactly as its own header promised.

When a task ships or a decision lands, update the relevant doc rather than relying on chat memory.

After any substantial change (feature shipped/removed, audit item closed, vendor relationship changed), follow the **echo-work discipline** in the global `~/.claude/CLAUDE.md` — propagate to README, ROADMAP, LICENSING, AUDIT_REPORT, OUTREACH_LOG, memory, .env.example, tests, AWS surfaces. Doing it now is 2-3× cheaper than re-deriving the context tomorrow. For Sky Score specifically, the "echo loop" almost always touches: README.md (Lambda counts), ROADMAP.md (open decisions resolved), LICENSING.md (data sources), and `~/.claude/projects/.../memory/MEMORY.md` (cross-session facts).

**Cross-project echo**: substantial Sky Score waves (release submitted, big pivot landed, competition outcome confirmed, new submission added/dropped) also belong in the 90-day builder roadmap at `C:\Users\bilal\OneDrive\Desktop\90_DAY_ROADMAP.md` under the "Daily Progress Log" section. Keep that file strategic — competitions, pivots, deadlines, headline wins — not wave-level commit detail. The 90-day file is opened via the `90-Day Roadmap.bat` shortcut in `OneDrive\Desktop\Claude Projects\` to seed cross-session context across all Bill's projects, so Sky Score wave logs going there means future Claude sessions on Noor / LedgerAgent / Siraj see Sky Score's state too.

## Before conversation ends

When the user says goodbye, thanks you, or indicates they're done, run `git status` to check for uncommitted changes. If there are any, remind the user:

```
You have unsaved changes. Would you like me to commit them before you go?
```

If they say yes, create a commit with a clear message describing what changed.

**PUSH. The old "keep git local only, never push" line here is SUPERSEDED
(2026-08-27, Bill's ruling.)** It contradicted the global rule that push/pull is
the only safe sync mechanism, and the contradiction was not harmless: it stalled
**21 commits** on a single machine and cost two round-trips in one session to
resolve, because an explicit "never" cannot be overridden by inference. Follow
the global multi-device workflow - `git fetch` early, surface drift,
`git pull --rebase` before pushing if the branch diverged.

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
| roadNoise / airQuality / flood bands | `build_borough_bands.py --check` | DEFRA Round 4 road Lden + DEFRA background maps + EA RoFRS. **Air quality is every city bar NYC; road noise now is too, and flood is everything bar NYC and Cardiff** (measured from `borough-extra.json` 2026-08-30: air 86, road 86, **flood 86** of 91 - Teesside's five joined when the georeferencing fix stopped one blank sea tile from abandoning the whole city). The old note here said Leicester 0/8 and Teesside 0/5 carried NEITHER, and recorded it as a property of the data - **it was an unrun script**. Both fetchers are per-city against ENGLAND-WIDE coverages and neither city was in `NO_ROAD_COVERAGE`/`NO_FLOOD_COVERAGE`; the rasters had simply never been fetched for the two cities that joined on 2026-08-11. **A measurement recorded without its cause reads as a constraint.** Teesside's blank sea tile is still refused by the C11 guard - correctly - but its area is now carried as Unavailable instead of failing the city, so the other seven tiles publish. `paintBoroughLayer()` skips what is missing, so the MAP is honest; this row was the thing over-claiming. **Since v3.9 the BANDS are still display-only but the CONTINUOUS fields beside them SCORE** - see the `environment` row below. |
> ## FLOOD WAS MIS-GEOREFERENCED IN 10 OF 11 CITIES - FIXED 2026-08-30 (audit F24/F39)
>
> `fetch_ea_flood_risk.py` clipped edge tiles to the city bbox but **requested
> every tile at 2000x2000 px** whatever ground it covered, then mosaicked at a
> uniform 10 m/px. A 5 km-wide edge tile rendered at 2.5 m/px and was pasted as
> if 10 m/px - **stretched up to 5x**, dragging flood polygons kilometres out of
> position. **London was the worst city, not a footnote: 6 of 12 tiles clipped,
> 5.00x.** Only Nottingham (40x40 km) is an exact multiple of the 20 km tile.
>
> **The fix is `tile_px()`**: request each tile at its real extent, so every tile
> is genuinely 10 m/px and the mosaic's existing assumption becomes true. The
> bbox is snapped to 1 km, so the division is always exact. Verified by
> simulation before any fetch: all 11 cities tile their mosaic with **zero holes
> and zero overlaps**.
>
> **The cache key had to change too, or the fix does nothing.** Tiles were named
> `flood_{e}_{n}.npy` - origin only, no extent - and `fetch_tile` skips on
> existence, so the stale 2000x2000 renders would have been served forever. The
> name now carries the extent.
>
> **Two more defects surfaced while fixing it, both the same class:**
> - **Bristol's edge tile was cached ALL-ZERO** from before the blank-render
>   guard existed - 2000x2000 of code 0, "surveyed, no flood risk", over 220 km².
>   Exactly what that guard's own comment predicted would outlive the outage.
> - **The mosaic initialised to `np.zeros`**, and code 0 is a REAL READING
>   meaning no risk. It is `255` (Unavailable) now. Unreachable while a failed
>   tile aborted the city; load-bearing the moment partial mosaics became legal.
>
> **A city is no longer abandoned for one bad tile.** Bristol and Teesside are
> each held by one near-all-sea tile the service renders blank at every
> resolution tried (10, 5.5 and 5 m/px - measured, not assumed). Bristol's lies
> outside all four boroughs; Teesside's clips one corner of Redcar. The gap is
> carried as Unavailable and reported by `floodCoverage`.
>
> **Effect, measured against the pre-fix file:** 37 of 81 boroughs moved, **13
> changed band**, none lost. Sefton **31.39 -> 0.27** `high -> low` (the audit
> predicted 0.28 by hand), South Tyneside **10.94 -> 0.11**, Doncaster
> **24.38 -> 6.39**. **Teesside GAINED flood for the first time**, so coverage
> is **86 of 91, up from 81**.
>
> ### The gate: `scripts/check_flood_georef.py`, blocking, `net_check`
>
> `build_borough_bands.py --check` could never see this - it re-derives from the
> same mosaic, so the two things it compares are the file and itself. The new
> gate asks the **EA's own GetFeatureInfo** what `risk_band` it publishes at a
> BNG coordinate. It asserts MEDIUM-OR-HIGH (the scored quantity), **in both
> directions**, because "where we say flood, the service agrees" passes a mosaic
> that has lost its polygons entirely.
>
> **Its first version PASSED the known-bad mosaic 9 of 9**, and that is the part
> worth remembering. Uniform sampling proves nothing here: measured against the
> pre-fix London file, the **six interior tile blocks were byte-identical** and
> only the top row and right column had moved, so half the samples could not
> fire. `spread_samples()` draws one sample per grid cell, **periphery first**,
> because a tiling error accumulates at the edges by construction. Re-proven
> red at **33%** on the same file. **Sampling was the whole gate; the network
> call was the easy half.**

| **environment** (v4.0, 2026-08-29) | `build_borough_bands.py --check` / `--write --write-lambda` | **Air quality 0.45 + road noise 0.35 + flood 0.20, from `airQualityWhoRatio`, `roadNoiseAboveWhoPct` and `floodMediumOrHighPct` - the CONTINUOUS fields, never the three-band map summaries** (68.1% share the modal air band, 54.9% the modal road band). **Road noise reads the SHARE over WHO 53 dB, never `roadNoiseLdenMedian`** - the median carries 41 distinct values to the share's 69 over an IQR of 1.7 dB, and ramping it 53->63 dB clamps 19 of 73 boroughs to a perfect 10. All three anchored on PUBLISHED thresholds: WHO 2021 -> the UK legal NO2 limit; 0% -> 100% over WHO's 53 dB Lden road guideline; 0% -> the EA's 10% Medium-or-High cut. **SCORING inputs, so they live in BOTH holders** - `test_borough_data_parity.py` covers all three, plus a `NAME_ALIASES` drift guard. **Use `--write --write-lambda`, not `--sync-lambda`**: sync copies from `borough-extra.json`, which SKIPS backend-only Cardiff and Nottingham, so Nottingham would silently miss road. 90/99 carry road; **85 `measured`, 5 `partial` (Teesside), 9 `unavailable` (NYC 5, Cardiff 4)**. |
| transport | `build_borough_bands.py --write --write-lambda` | **NaPTAN, share of postcodes within 800 m of a rail/metro/tram node. A SCORING input (0.25 of liveability), so it lives in BOTH holders — `tests/test_borough_data_parity.py` fails the build on drift. Methodology v3.6, 2026-08-11.** |
| crimeRate | `refresh_crime_from_ons.py --check --all` | ONS Table C4, 0 differ; **blocking preflight stage since 2026-08-24, with a PER-CITY floor** (it used to pass having compared zero) |
| p8 | `build_progress8.py --check` | **DfE KS4 2023/24 Revised (rolled 2026-08-27)**, 79 compared, 0 differ; advisory preflight stage since 2026-08-24 (its gitignored KS4 bundle cannot be auto-fetched - EES 403s non-browser UAs - so blocking would gate every fresh clone). **2023/24 IS AVAILABLE AND NOT ROLLED (verified against DfE 2026-08-27).** The script used to claim 2022/23 was terminal until 2026/27; the mechanism was right and the boundary one year early - the cohorts with no KS2 baseline are **2024/25 and 2025/26**, and DfE's own 2024/25 release says exactly that, while 2023/24 (published 2025-02-27) carries P8 as a headline measure. **Costed, not guessed: 72 of 79 boroughs would move, none by more than ±0.20**, mean +0.008, 33 up / 39 down, none dropping out - currency, not a re-basing. One blocker, now handled: DfE renamed the `gender` column to `sex`. Area pages BAKE scores, so a roll must rerun `build_area_pages.py --write`. |
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

**Postcode-level scoring works for every city — REALLY, since 2026-08-12.** The
gate was `if city != 'london': return 400` and was lifted on 2026-08-10, and the
recorded reason for it — that NSPL writes the borough attribute for London LADs
alone — was half the story. NSPL writes the LAD **code** for all 2.7M rows, so
`LAD_TO_BOROUGH` resolves the rest and **no reload was needed**. Verified against
the live table: M1 1AE carries `lad=E08000003` with `b` absent.

**But it did not actually work until 2026-08-12, and this file said it did for
two days.** `city` defaults to `'london'` and **nothing derived it from the
resolved LAD**, so `/v1/score?postcode=M1+1AE` answered *"Borough not currently
supported in london."* — naming a city the caller never mentioned. B15, LS1, S1,
BS1 and NG1 all did the same. The un-gating was genuine (`?city=manchester` with
that postcode scores 7.7); it simply could not be reached without supplying the
answer in the question, which no documented caller does.

- **Every piece was correct and the feature still did not exist.** The un-gating
  commit, `LAD_TO_BOROUGH`, and the postcode table were all right — the row for
  M1 1AE was verified by hand and written up above. Nothing joined them. **When
  a capability lands, exercise it the way a caller would**, not the way the code
  is organised.
- **The fix is three parts and one was not enough.** Derive the city from
  `_ladCode`; fall back to a borough-NAME index because the postcodes.io tier
  carries no LAD code (a code-only fix repairs the loaded tier and leaves the
  fallback answering london); and absorb the qualifier inversion — ONS writes
  `City of Bristol`, postcodes.io returns `Bristol, City of` — in **both** the
  derivation and `normalise_borough`, or Bristol and Nottingham resolve the right
  city and then 404 one step later on the borough.
- **A passing test asserted the defect.**
  `test_resolve_query_404_unchanged_for_non_london` was correct when written, was
  never revisited when the gate lifted, and so spent two days reporting the bug as
  expected behaviour — reading as evidence the endpoint worked.
  `PostcodeCityDerivationTests` replaces it, asserts the **derived city** rather
  than that a score came back (a London default returns a well-formed error), and
  is proven red.
- **Nothing else could have caught it**: `check_score_sanity.py` probes 16 LONDON
  postcodes, `borough-score-parity` compares boroughs by NAME, and every other
  unit test passed a `city` alongside the postcode. Widening the sanity probes
  beyond London is the open follow-up.

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

**THE DISPLAY-ONLY CATEGORY IS EMPTY as of 2026-08-29 (v4.0).** The paragraph below is still true of the three *map layers* - the BANDS are drawn, not scored - but the CONTINUOUS field beside each one now scores: `airQualityWhoRatio` and `floodMediumOrHighPct` since v3.9, and `roadNoiseAboveWhoPct` since v4.0. Road noise was the last input that was measured, drawn and reported by `/v1/environment` while **nothing scored it**. Every input this product derives is now either scored, or is a MEASUREMENT published under a label naming what it measures. `plannedComponents` is down to `epcDistribution` and `crimeBreakdown`; `roadNoise` never entered it and now never will. **The `env` FLOOR is 2 inputs, raised from 1 at v4.0** - adding road lowers every borough that HAS it and leaves the rest standing still, so at a floor of 1 the missing-data boroughs rose from median rank 41 to 9 of 86 and Teesside took the top four places on one input of three. **`environmentSingleInput` could NOT be the mitigation: it is published and read by NOTHING** (third instance of the `lineStatusAvailable` shape), and is now literal to its name rather than firing for 2-of-3.

**The three borough fill layers were FABRICATING data for seven cities until 2026-08-11.** Road noise, flood risk and air quality each ended their lookup with a fallback — `|| 'moderate'`, `|| 'low'`, `|| 'moderate'` — and `borough-extra.json` gave those fields to London and NYC only. So every borough of the other seven was painted **one confident colour** meaning a reading nobody had taken, while the legend title above it already said "(NO DATA)". The label said no data; the map drew a value; the map is louder. The detail panel separately printed the literal string **"UNDEFINED"**, uppercased by its own CSS.

- **`paintBoroughLayer()` is now the single painter and it SKIPS a borough with no reading.** Do not reintroduce a default. An unknown band is skipped too, because painting it as "moderate" is how a data problem becomes a false claim.
- **All three layers are derived for every city** by `python scripts/build_borough_bands.py --write`, anchored on published thresholds (road: share of addresses over WHO 53 dB Lden; air: worse of NO₂/PM2.5 against WHO 2021; flood: share at EA Medium-or-High, the 1%-annual-chance Flood Zone 3 line). See `METHODOLOGY.md` §7.1. The nine `*_BOROUGH_ROAD_NOISE` constants and the `roadNoise()` registry accessor are **deleted** — `borough-extra.json` is the single holder for all three layers.
- **Flood risk comes out of a WMS by decoding rendered colours, and that is deliberate.** The EA's RoFRS dataset publishes **no WCS and no WFS** (both 404), and its postcode-level product is **retired** — `scripts/fetch_ea_flood_risk.py` records every dead route so they are not retried. Two things keep it honest: `format_options=antialias:none` is **load-bearing** (without it one tile carries 16,289 blended colours instead of 5), and the colour→band map was **verified against the service's own `risk_band` by point-in-polygon containment** — an earlier check that trusted `features[0]` made High and Medium look interchangeable, because a 200 m query box spans several 50 m polygons. Re-run `--verify` after any upstream restyle; an unrecognised colour **fails the fetch** rather than silently reclassifying. Rendering is scale-dependent: nothing draws above ~10 m/px.
- **`scripts/fetch_defra_road_noise.py` was London-only by a single hardcoded bbox** while pointing at a coverage id ending `England_Round_4_All`. It now derives the bbox from each city's boundary file. **Wales is excluded by name** (`NO_ROAD_COVERAGE`) — the coverage is England's, and a Cardiff fetch would otherwise "succeed" and read as no-noise-anywhere.
- **Legend "(NO DATA)" is now MEASURED**, appended by `markLayerCoverage()` from what the render produced. It used to be a hardcoded registry string per city, which has to be remembered when data arrives and is wrong in the other direction the moment it does. **That prediction came true within a day, in a slot the fix did not cover**: `legendFlood` and `legendAq` label the *first swatch* of each legend, not the title, and all seven UK cities still said `'NO DATA'` there — so the High and Poor swatches were labelled "NO DATA" while the map painted real EA and DEFRA readings beneath them. Corrected 2026-08-11 to `'HIGH'` / `'POOR'`. **Any registry string that describes data availability is a liability**; prefer measuring it.
- **Cardiff and NYC are excluded from road noise and flood by name** (`NO_ROAD_COVERAGE` / `NO_FLOOD_COVERAGE`) — both coverages are England's, and NYC keeps curated FEMA-derived flood bands. A Welsh fetch would otherwise "succeed" and read as no-risk-anywhere.
- **The BAND ROWS are measured too, since 2026-08-23** - the titles had been since 2026-08-11, and the three swatches under each title had never been checked against anything. Measured across all eleven cities: **41 of 99 rendered band rows described a band no borough on that map carried.** Leicester and Teesside showed six confident colour swatches - three road, three flood - beneath two titles already reading "(NO DATA)", which is the same defect the aircraft dB scale was fixed for on 2026-08-11, in its three sibling layers. `markLayerCoverage()` now hides a row whose band painted nothing. Do not reintroduce a static row.
- **`FILL_LAYER_COLOURS` is the single holder of what each layer can paint**, hoisted out of `repaintFillLayers()` so it and the legend's `data-band` rows are two lists a gate can compare. While they were a function-local and static markup, **`aqColors` held four bands against the legend's three**: `excellent` (`#16a34a`) was a colour the map could paint with no row to name it, four shades off GOOD's `#22c55e`. It cannot fire for our 91 urban boroughs (62 moderate, 18 good, 11 poor, 0 excellent) but 59.2% of DEFRA's national cells clear both WHO guidelines, so it fires the moment coverage leaves the city cores. **Both `HANDOVER.md` and `ROADMAP.md` recorded this backwards** - as a legend advertising an unreachable band - for eleven days. A row that hides itself when empty is why the swatch could simply be added.
- **NOTHING IN THE SUITE OPENED THE SIDEBAR until 2026-08-29**, which is how
  `envCaveat()` shipped rendering **"- undefined only here"** on every UK
  borough panel, deployed, and stayed live for hours with every gate green.
  `tests/borough-score-parity.mjs` compares the SCORE out of the registry
  without rendering the panel, so **every string beside every number was
  unasserted**. **`tests/panel-caveat.mjs`** renders it - Camden 3/3 must carry
  no caveat, Brooklyn must survive having none of the three, and a CONSTRUCTED
  2-of-3 borough must NAME the two inputs it has - and is blocking in preflight. Proven red
  against the pre-fix tree. The defect itself: the caveat reads the three
  CONTINUOUS fields, which only `borough-extra.json` carries, and the sidebar
  handed it the SCORED record from `matchBorough()`, which never has them, so
  the measured-input list was always empty and `names[0]` was `undefined`. It
  resolves the record itself now, exactly as `getEnvScore()` does. **A record
  argument can always be the wrong record; a name can only resolve through the
  holder that has the fields.**
- **The partial case in `panel-caveat.mjs` is CONSTRUCTED, and had to become so
  on 2026-08-30.** It used to borrow Middlesbrough, which held air quality and
  road noise and no flood. The flood georeferencing fix gave Teesside flood, so
  Middlesbrough became 3/3 and **the gate went red on a borough whose data had
  improved**. Measured that day: of 99 borough records, 90 hold all three env
  inputs, 4 hold one (Cardiff) and 5 hold none (NYC) - **no borough is 2-of-3 any
  more**. Flipping the expectation to `false` was the tempting one-line fix and
  would have left the caveat branch - the exact code that shipped "undefined only
  here" - permanently unexercised while the file still looked like it covered it.
  The test now drops one field from a real record, renders, asserts the caveat
  NAMES what survived, and restores in a `finally`. **Borrowing a real subject for
  an edge case means the coverage expires the day the data gets better.**
- Guarded by **`tests/layer-honesty.mjs`** (in preflight), which fails in both directions: over-painting is an invented default, under-painting is a borough whose data the map cannot find. **Since 2026-08-23 it also asserts the legend**: every `FILL_LAYER_COLOURS` key has a `[data-band]` row and vice versa (city-independent, runs once), and per city the set of VISIBLE rows equals the set of bands actually painted - inverted out of the rendered `fill` attributes and read from computed style, never from the counter or the inline style the fix writes. Proven red four ways.
- **`tests/a11y-source.mjs` reveals the band rows before scanning**, added the same day. Otherwise the EXCELLENT swatch - hidden in all eleven cities - would never be evaluated by axe and would first reach a user on the day coverage widens, never having had its contrast measured. That is exactly how three legend headings shipped at 1.00:1.

**Neighbourhood ranking data.** London and NYC hold *curated* medians and a hand-assigned `crime` modifier inline. **All nine UK city-regions' 485 entries are generated** (2026-08-11; was Greater Manchester's 85 alone) — `python scripts/build_city_neighbourhoods.py --write-index` rewrites `index.html` between each city's `<CITY>-NEIGHBOURHOODS:START/END` markers from HM Land Registry's **bulk** Price Paid CSV (the linked-data API returns **HTTP 200 with an empty list** for a district query, so it cannot be used) plus NSPL for coordinates. A "neighbourhood" is a **postcode district**, districts under 30 sales are dropped rather than estimated, and `crime` is 0 everywhere because sub-borough crime is not published at that geography. **Boroughs come from the Lambda's `LAD_TO_BOROUGH`, matched to Land Registry's own district spelling by normalisation** (`Westminster` → `CITY OF WESTMINSTER`); a borough matching nothing is reported loudly, because a silent miss reads as "this borough has no neighbourhoods". One PPD pass and one NSPL pass cover every city. Do not hand-edit inside the markers; re-run the script. The 155 MB PPD cache and the JSON by-product both land in gitignored `data/`.

**The transport MAP LAYER is DELETED; stations live in the PANEL (2026-08-12).**
Bill: "still messy for the other core cities - I can't click on them because it
will click on the borough instead." Both true, and together fatal: the markers
cluttered the thing you *can* click, could not be clicked themselves (the borough
path takes the event), and duplicated a signal already in the score. Toggle,
flag, renderer, `.layer-transport` selector entry and the `labelTransport`
registry field on all eleven cities are **removed**.

The DATA moved to where it is readable: the detail panel's nearest-stations
section, which is fed by `/transport` = **TfL**, and which had been telling ten
of eleven cities **"No stations found within 1.5km."** That is not what TfL
meant - it meant "TfL does not cover Manchester" - and the panel rendered a
confident absence in its place. **Third instance of that shape in one day**,
after the `-0.4` penalty and the `|| 'moderate'` fill layers. NaPTAN now backs
it: four nearest rail/metro/tram, straight-line distance, source named.

**The panel reads `lineStatusAvailable` since 2026-08-27, and until then nothing
did.** `/transport` has separated "TfL answered and nothing near you is
disrupted" from "we could not ask" since 2026-08-24, and the frontend gated the
whole section on `lineStatus.length > 0` - so a 403 on the Status route rendered
as NO SECTION AT ALL, which is indistinguishable from a clean network. **Fourth
instance of absence-as-measurement in this one panel's history.** The producing
comment is where it went wrong: "consumers can upgrade to read the flag; none is
required to" made the second half optional, so it never happened. **A field only
its producer reads is not a fix.** The notice DENIES the false reading rather
than merely withholding the claim, names the upstream, and scopes itself to the
status leg (the stations came from a different TfL route that answered). Use
`!== false`, never a truthiness test - a response cached before 2026-08-24 has
the field `undefined`, which meant "checked", and truthiness would turn every
stale cached response into a false outage claim.

**Three stale references survived the removal and Bill found the first**: the
metric card still said `TOGGLE "TRANSPORT" ON MAP TO SEE STATIONS`, the layer
selector map still listed `.layer-transport`, and the map's `aria-label` still
advertised the overlay (while naming three cities out of eleven). **When you
delete a feature, grep for its NAME, not just its function.**

The e2e asserted `toHaveCount(7)` on the toggles and went red - the gate working,
but the fix it invited was to edit the number. It now asserts the **set**, so a
removed layer fails with its own name in the diff. **Any count in an assertion is
scheduled staleness.**

**Stations are DISPLAY-ONLY, and the transport nudge is gone (2026-08-12).**
`scripts/build_city_stations.py` fills `<CITY>_STATIONS` from NaPTAN - 1,771
stations across ten cities - **read by `nearestStations()` for the detail
panel**. (This paragraph said they "draw the map's transport layer" until
2026-08-23, contradicting the paragraph directly above it, which correctly
records that the transport MAP LAYER was deleted on 2026-08-12. There is no
transport layer: six toggles are declared - paths, defra-aircraft, defra-road,
flood, air-quality, labels - and a dead CSS rule for a seventh survived until
2026-08-23, the **fourth** stale reference from that one removal.) The `+/-0.4` liveability nudge those arrays
fed is **removed, not filled**: transport is already scored from the same NaPTAN
register at borough level since v3.6 (0.25 of liveability), so filling them would
count one measurement twice, and London's 18 hand-picked interchanges mean
something different from "every station". Two traps, both the bbox/first-match
family: **a bounding box is not containment** (Leicester's and Nottingham's
overlap - first-match-wins gave Leicester 104 stations and Nottingham 16; point-
in-polygon gives 19 and 69), and **stripping a descriptor anywhere in a name
edits the name** ("Station Approach" -> "Approach"; four Altrinchams). NYC is
untouched - NaPTAN is UK-only and correctly yields zero. **NYC's transport
layer has ALWAYS drawn nothing**: `NYC_STATIONS` was already `[]` before this
work, under a comment describing "major subway/rail hubs". Filling it needs an
MTA source, not NaPTAN.

**The neighbourhood ranking says "best value" where price leads it (2026-08-12).**
Rank-to-price correlation, measured over the rendered rows: **-0.23 London,
-0.06 NYC, 0.67-0.89 every generated city**. So nine of eleven lists are largely
cheapest-first - each puts Bradford City Centre, Middlesbrough Town Centre,
Chopwell or Bootle at #1. Structural, not a fault: a generated "neighbourhood" is
a postcode district with `crime: 0` (not published at that geography) and a
liveability inherited from its borough, so districts differ mainly by price and
aircraft quiet while affordability is ~31% of the score. **Nothing is
miscomputed; the LABEL over-claims** - the same distinction as WA8 publishing a
Knowsley median as "Widnes". **The threshold is MEASURED at render time, never a
per-city string**, so a city that gains a differentiating input drops the
disclosure by itself - the `markLayerCoverage()` principle, applied before the
stale-string version could be written. 0.6 is the line and nothing sits between
-0.23 and 0.67.

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

## Public surfaces added 2026-08-21 — badge and area pages

**`GET /badge?postcode=` returns an SVG, unauthenticated.** It renders inside an
`<img>` on third-party listing pages, which cannot carry a key. **An image and
not a JS snippet, deliberately**: portals run strict CSP and a third-party script
is the first thing blocked, so the badge would fail silently on exactly the sites
worth appearing on. It reuses `resolve_query`, so it cannot show a score
`/v1/score` would not. An unresolvable postcode returns a BADGE saying "not
covered", never a 404 - a 404 renders as a broken image on a customer's page. The
SVG is XML-escaped because **an SVG is a script-capable document served from our
origin onto someone else's page**. Cached 24h; uncovered postcodes 5 min, so a
newly-covered area does not keep saying otherwise.

**99 static borough pages under `area/`, generated by
`scripts/build_area_pages.py --write`.** The sitemap went from 8 URLs to 108. The
pages carry **no `<script>` tag at all** - the map is client-side, so a crawler
previously got a shell.

- **They BAKE their scores**, so a data vintage silently puts them out of step
  with `/v1/score`. `tests/area-page-freshness.mjs` is blocking and compares all
  99 against the live API in **ONE batch request** (1 CI quota unit, not 99 -
  a blocking gate that spends a consumable is how `score sanity` once blocked
  every commit in this repo). **Rerun the builder after any vintage roll.**
- `tests/area-pages.mjs` asserts CONTENT, not existence: a fact floor, unique
  titles and descriptions, and that **no two pages share a fact block**. 99 thin
  or near-identical pages is a doorway network and worse for the domain than
  having none.
- Both data holders are read and **neither is guarded**. The first version read
  `app.BOROUGH_EXTRA` behind a `hasattr()` - an attribute that does not exist -
  so all 99 pages silently lost crime, schools, transport, healthcare, road
  noise, air quality and flood, and still passed `--check`.

**The free tier is 10,000 requests = 10,000 scores.** `/v1/score/batch` is denied
per-method on `ScoreFreeUsagePlan` and on `ScoreDemoUsagePlan`, via
`ApiStages[].Throttle` with `RateLimit: 0` - the only declarative way to keep a
key off a route, since **API Gateway keys authorise per STAGE, not per route**.
`tests/demo-key-scope.mjs` asks the RUNNING API whether 0 denies, because the
template cannot answer that. **Verify after every deploy.**

## Absence must never render as a measurement — the 2026-08-22 sweep

**Shipped and verified live the same day.** Four Lambdas via SAM, six public
surfaces via S3 + a completed CloudFront invalidation. The live responsive audit
went from 10 failing page/viewport combinations to 0, and `/nhs` at an uncovered
bbox point now answers with NHS search links instead of three empty lists.

Ten audit-Important findings closed in one pass, and **most were one defect
wearing different clothes**. Read this before adding any fallback value.

- **`/nhs` asserted absence over 35.4% of its own bounding box.**
  `in_bundle_area()` tests a RECTANGLE (51.25..51.72 by -0.55..0.35) that reaches
  into Surrey, Kent, Essex and Herts. Measured on a 24x24 grid: 204 of 576 points
  had no bundled service within 1500 m and were published as `available: true`
  with three empty lists - "we checked, there is no GP near you". The Overpass
  branch beside it, facing the same gap, returns fallback links and
  `available: false`. One branch admitted ignorance, the other asserted absence,
  for identical missing data. It now falls through. **"A bounding box is not
  containment", fourth instance.**
- **EPC published an unparsed band as the WORST possible property.**
  `BAND_MIDPOINT[band]` inside `if band in bands` was guarded; `.get(band, 0)`
  **ten lines below** was not. 0 is not "unknown" on a 1-100 scale, it is below
  every real certificate - and `rating_to_band(0)` is `'G'`, so a postcode whose
  bands we could not read reported itself as worse than any genuine G. Mirrored
  code, eleven lines apart, **third instance**.
- **A gate that compares nothing was three gates, one of them extra-blocking.**
  `build_aircraft_bands.py`, `build_hpi_prices.py` (also blocking - an empty
  registry printed `0/0 agree`, and `--all` over an empty city list is
  `sum(())` = 0 = PASS) and `build_progress8.py`. All three now print what they
  compared and fail on zero. **The floor is PER-UNIT**: renaming one city's
  marker leaves 104 of 114 bands comparing, which a global `compared > 0` waves
  through.
- **Attribution was per-CONTAINER, not per-request.** `_LOCAL_POSTCODE_SERVED`
  was set True on the first NSPL hit and never reset, so one local hit credited
  ONS in the `sources` array of every later response from that container. The
  comment reasoned about the write race under the batch pool and called it
  "idempotent" - true, and beside the point: the defect is one thread READING
  another's True. Now `threading.local()`, reset in `resolve_query`.
- **The extension deleted its own caveat whenever a basis string existed.** The
  suppression flag tested "the row has some text", but the row carries the
  short per-row basis when `aircraftQuietBasis` is present and only falls back
  to the coverage notice when it is absent - so in the common case the notice
  was filtered out of the disclosure having never been inlined anywhere. Keyed
  on the notice itself now.
- **The pre-release API gate passed on any 4xx.** `res.status < 500`. Measured
  live: `/transport` and `/nhs` were BOTH returning 400 and reported PASS - they
  take `lat`/`lon` and the file had always sent `postcode`. Two of five
  endpoints had never once been exercised. It asserts payload contents now, and
  probes were re-chosen for postcodes that HAVE data: SW11 1AA has no recorded
  sales, so even the endpoint that answered 200 was proved by an empty array.

**Every Lambda timeout was above what API Gateway will wait for**, including the
Globals default (30 against a 29s integration cap). The cost was the smaller
half: at `Timeout: 45`, `/nhs` could not reach its own fallback branch inside
the caller's window, so a slow Overpass produced a raw 504 instead of the
degraded answer the code exists to give. **Raising a timeout past the cap
silently disables the fallback beneath it.** Guarded by
`ApiGatewayTimeoutCapTests`.

**`score-demo/index.html` advertised the free tier at 100 requests/month against
a plan enforcing 10,000**, and sold a batch multiplier the gateway answers with
429. `FreeTierQuotaDriftTests` opens by saying the numbers live in five places
and only one is enforced - and then asserted exactly one of the other four,
the signup Lambda. `template.yaml`'s own list of mirrors omitted this file.
**A list of mirrors that omits a mirror is worse than no list, because it reads
as complete.** The pages are now asserted against the plan.

## Scale direction — do NOT "fix" the apparent site/extension disagreement

**Scores rise, measurements rise, and the label names which.** See `METHODOLOGY.md` §11.0.

- **Scores** (0–10 components) run **higher = better** and are labelled with the *good* thing: `Quiet Skies`, `Affordability`, `Liveability`. Site score panel and `/v1/score`.
- **Measurements** run **higher = worse** and are labelled with the *bad* thing: `Road noise 49.5 dB Lden`, `Aircraft noise 2/10 noise`. `/v1/environment` and the extension's Environment section.

So the same postcode reads **`Quiet Skies 8/10` on the site** and **`Aircraft noise 2/10` in the extension**. That is one value under two labels, *not* a divergence: `/v1/environment` returns `aircraftQuietEstimated: 8` and the extension shows `10 − 8`, asserted against the live endpoint in `tests/extension-e2e.mjs` (on an **asymmetric** value — SW5 scores 5, which inverts to itself and cannot detect a missing transform).

The rule is not "noise always goes up" — it is that direction must agree with whatever the number sits *beside*. Until 2026-08-08 the extension rendered a quiet score under a "noise" label, so the longest bar in the section marked the quietest row. Harmonising the two surfaces reintroduces that defect in one direction or the other.

## Branding

Always use "Sky Score" in all public-facing files and UI text.

## Do NOT add Co-Authored-By lines to git commits

## There is NO basemap, and that is a decision (evaluated 2026-08-30)

The map is `d3.geoMercator` + `geoPath` over our own GeoJSON. **No tiles, no map
API, no key, no per-load cost.** The handful of "basemap" mentions in
`index.html` are comments about the grey background, not a tile layer.

`design/map-basemap.html` toggles the same borough data between that vector
ground and an OpenStreetMap raster basemap, so the trade can be seen rather than
argued. Adding a street basemap would mean: a third-party runtime dependency at
the centre of the product, widening the CSP `img-src`, **losing offline** (tiles
cannot be `cache.addAll`'d, and `tests/failure-path.mjs` asserts an offline
launch), permanent provider attribution, and per-load billing if it is Google.
The product argument is separate and stronger: **street detail implies a
precision we do not have**, since every figure published is borough-level.

**Two gotchas found building it, both the "graceful failure" shape:**

- **CARTO serves HTTP 200 with a valid 76 KB PNG when unauthenticated** - a
  placeholder stamped "API KEY REQUIRED" on every tile. A health check on status
  and content-type PASSES on a useless tile. **Assert pixels, not status**, if a
  tile provider is ever wired in.
- **A MapLibre `symbol` layer with no `glyphs` URL means the style never
  finishes loading.** Tiles paint perfectly, `isStyleLoaded()` stays false
  forever, and the data layers are never added - a flawless street map carrying
  none of our data, which reads as a design choice rather than a fault. Poll
  readiness; do not hang data layers off a single `load` event.

## Audit follow-ups closed 2026-08-30

- **F30 - CI had run neither test suite since 24 July.** `test-backend` and
  `test-e2e` were `needs:` the lint jobs, and the lint jobs failed on FORMATTING
  alone (`ruff format --check` exit 1, `npm run format:check` exit 1) while the
  real checks passed (`ruff check` 0, `npm run lint` 0). A skipped job reports
  neither pass nor fail, so CI looked healthy running nothing. **Formatting is
  now advisory in CI, as it has always been in preflight**, and the test jobs no
  longer `needs:` lint at all - style must never be able to withhold the
  correctness signal.
- **F41 - a Capacitor build shipped 2 of 13 cities' geometry.**
  `mobile/scripts/copy-web.mjs` held a hand-written four-file `REQUIRED_DATA`
  frozen on 3 August. Worse than missing outlines: `sw.js` precaches ELEVEN
  borough files through `cache.addAll()`, which is **atomic**, so the service
  worker would have failed to install at all in the native app. The requirement
  is now **derived** from the `/data/` references in `sw.js` and `index.html`
  (their union, 17 files) with a floor of 10, because a regex that matches
  nothing must not produce an empty requirement. Verified by running it: 4 -> 17,
  and every sw.js-precached file present.
- **F1 - the scored `environment` component was credited to nobody.** No
  `sourceBreakdown` key and no `sources` line, while `terms.html` obliges
  integrators to carry the sources array through to their own users and
  METHODOLOGY §18 tells their auditor it is complete. The component is 0.14 of
  six personas and 0.18 of `family`/`laterlife`, entirely from three OGL v3.0
  datasets. Both the lineage line and the three source lines are now **derived
  from the borough records per city**, injected into all 13 provenance entries
  rather than written into each, so a city that gains or loses a dataset
  re-describes itself. `build_sources` drops a `None` line, which is how New
  York credits **zero** UK bodies while still SAYING the component is not scored
  there. Cardiff states it is below the two-input floor. **The guard was the
  real problem**: `test_every_city_has_its_own_provenance` asserted the literal
  `{'quiet','afford','growth','live'}` and so passed unchanged through v3.9 and
  v4.0. It now derives the expected set from the components London actually
  emits, and is proven red.

## Quality & Plugins

- Run `/preflight` before every commit — or directly: **`sh scripts/preflight.sh`** (also `npm run preflight`, `make preflight`; all three invoke the same script so they cannot drift apart). Blocking: ESLint (now `.js`/`.mjs` too, not just `index.html`), html-validate, ruff over `backend/lambdas` + **`backend/tests/`** + `scripts/` + `tests/`, **both** pytest suites, **extension extraction + extension e2e + responsive (EVERY public page since 2026-08-22, not just the homepage - widening it found `privacy.html`, `changes.html` and `score-demo/status.html` all scrolling sideways on a phone, the worst of them moving the WINDOW 402px at five viewports off a `position: sticky` header escaping its scroll container; the homepage keeps all ten viewports, static pages get the narrow end; 10 viewports, now run against SOURCE as the blocking half and against CloudFront as an advisory one — the same split `a11y-source.mjs` makes, because pointed only at live it goes red on a tree that has already fixed the defect and stays red until deploy) + `every city switches`**, plus **`panel says what it measured`** (`tests/panel-caveat.mjs`, added 2026-08-29 - the first gate that ever RENDERED the borough detail panel; nothing had, which is how "undefined only here" reached production) (added 2026-08-06; the responsive audit fails on horizontal overflow **and, since 2026-08-11, on a control past the viewport edge with no scrollable ancestor** — it had always BUILT that list and only PRINTED it when the page itself scrolled sideways, so the city chips clipped by the map container's `overflow: hidden` left it reading "ok" at all ten viewports while three of eight UK cities could not be tapped at 320px; tap-target findings stay advisory because they need judgement; `every city switches` is `tests/city-switch.mjs`, added the same day because nothing had ever clicked a city chip; the e2e loads the extension into a real Chromium and needs `--headless=new`, since Playwright's normal headless uses `chromium_headless_shell` which does not load extensions at all), API-URL drift, **score sanity against the live API** (`scripts/check_score_sanity.py` - **27 probes since 2026-08-12, one per city; it was 16 and ALL LONDON**, which is why postcode scoring could be broken for eleven cities for two days with every gate green. The new probes assert the RESOLVED CITY, not that a score came back, because a London default returns a well-formed error. They caught a live false provenance claim on their first run - Manchester still said "PARTIAL, 2 of 4 inputs measured" two days after v3.6 and v3.7 gave it all four. The only stage that can catch a DATA defect; the pytest suites never reach DynamoDB and Playwright asserts the site against itself), **no em dashes on the 9 deployed pages** (`terms.html` joined 2026-08-05), **self-hosted fonts on all 9** (`tests/fonts-selfhosted.mjs`, serves the repo locally so it validates source before a deploy), **log retention == `privacy.html`** (`scripts/check_log_retention.sh` — see below; it now parses the claim out of `privacy.html` and passes honestly), **WCAG over the SOURCE tree** (`tests/a11y-source.mjs`. **Since 2026-08-31 it scans 109 pages, not 9** - the 9 public pages at two viewports plus **all 100 under `area/`**, which were in no accessibility or responsive gate at all. The area list is DERIVED by walking `area/`, never written down, and runs at ONE viewport because the generator emits no width breakpoint - a fact the gate ASSERTS by reading `build_area_pages.py` and failing if one appears, rather than leaving it in a comment. Same day, `AXE_TAGS` gained `best-practice`: **`FAIL_MODERATE` had been unreachable since the day it was written**, because all four of its rules are `best-practice`-tagged and the builder asked for WCAG tags only, so axe never RAN them. It was hiding missing `<main>` landmarks on `privacy.html`, `terms.html` and every area page. `failing()` keeps the old bar for everything else, so adding the tag did not quietly promote ~30 more rules to blocking. **It still scans the app's LANDING state only** - the borough panel has never been scanned by anything, and the 31 Aug audit found four defects living there. Original note follows: added 2026-08-10; since 2026-08-22 it also scans the **expanded legend**, because on a phone the legend ships `aria-expanded="false"` and axe does not evaluate hidden elements - so adding a mobile viewport had NOT made the mobile legend reachable, and three headings sat at **1.00:1**, literally the same colour as their background, until measured. It found a second untouched defect on its first run. *Adding a viewport is not the same as reaching the state.* Original note follows: added 2026-08-10 — the Playwright a11y spec scans CloudFront, so an accessibility regression could not be caught until it was already serving users, which is exactly how the locator inset shipped `role="img"` around ten focusable markers; this one serves the repo on 8923 with the CloudFront extensionless rewrite reproduced, and gates the deploy where the e2e one catches a bad deploy), **flood == EA service (georef)** (`scripts/check_flood_georef.py --all --per-class 4`, blocking `net_check` since 2026-08-30 - the ONLY flood gate that crosses a source boundary. `build_borough_bands.py --check` re-derives from the same mosaic, so the two things it compares are the file and itself, and it reported agreement for the whole period the mosaics were mis-georeferenced. This asks the EA's own GetFeatureInfo what it publishes at a BNG coordinate. **Sampling is the gate**: the first version passed the known-bad London file 9 of 9, because the six interior tile blocks were byte-identical and only clipped edge tiles had moved - `spread_samples()` draws one point per grid cell, PERIPHERY FIRST. Proven red at 20-60% across seven cities and green at 100% on all eleven. Carries a `MIN_COMPARED` floor (a class that reached the service twice has not been tested, and reports INCONCLUSIVE, never ok) and a top-up retry, because the EA host throttles and a gate that reds on rate-limiting gets switched off), **crime == ONS Table C4** (`scripts/refresh_crime_from_ons.py --check --all`, blocking since 2026-08-24 - the last of the audit's named gates to gain a per-city floor; its workbook auto-fetches and caches like the HPI stage's, ~1.7s), **map fits its box** (`tests/map-fit.mjs`, blocking since 2026-08-24 - 90 city/viewport combinations including landscape; see the 2026-08-24 memory entry for why nothing else could see a map drawn outside its own SVG), **prices == HM Land Registry** (`scripts/build_hpi_prices.py --check --all`, added 2026-08-10 — the only gate that can catch a PARTIAL VINTAGE ROLL, and written because there was one: London's `avgPrice` matched HPI 2026-05 for all 33 boroughs while its `trend` matched **no** HPI month, under a `CITY_PROVENANCE` sentence telling customers it was HPI. Keyed on **ONS codes, not names** — name matching has failed here five times. `--write` corrects BOTH holders or neither), **degraded + offline fallbacks** (`tests/failure-path.mjs`, blocking since 2026-08-27 - a stalled network, an offline launch and a partial TfL outage. It had been in NO gate at all since it was written: the one file dedicated to "the fallback shipped untested" was itself untested. Pointed at SOURCE for the same reason `responsive` and `a11y` are. Two things were living in that gap - it had been DYING on Node 24 at check 10 of 19 (a route aborted after `unroute`, unhandled rejection, fatal) so it read as a failing gate rather than a crashed one, and its NYC check had been clicking a selector that stopped existing when the switcher went two-tier on 2026-08-11, reporting London's 33 boroughs through a bare `catch` as though the switch had run), **web/native layout split** (`tests/native-sim-render.mjs`, blocking since 2026-08-31 - it and `tests/live-mobile-verify.mjs` were in **NO RUNNER AT ALL**, the 3rd and 4th orphaned gates here after `failure-path`. Two of its three contexts asserted **nothing** - the native and desktop halves measured, printed and compared nothing, so the App Store layout could break in any way and it exited 0. Now proven red both ways against real index.html defects. `live-mobile-verify` is **advisory**, because it reads CloudFront and a source tree ahead of the last deploy is the normal state), and Playwright at `--workers=2`
  - **`log retention == privacy.html` is BLOCKING and now PASSES, honestly (2026-08-06).** It asserts that AWS matches **whatever `privacy.html` §2d claims** — it parses the figure out of the page rather than hardcoding one. Until 2026-08-06 it hardcoded `WANT_DAYS=30` and never opened `privacy.html` despite its name, so the only route to green was the console work, and switching §2d to the honest interim wording left the gate **red on a truthful tree**. `DRAFT_security_retention_passage.md` §2b had flagged exactly this. The rewrite is strictly stronger: it still reds on "page says 30, AWS says None" and additionally reds on the reverse, which the old one could not see. **Both failure directions are proven red, plus an unparseable-claim case.** §2d carries **Version A** ("retained for 30 days") and `check_log_retention.sh` exits 0 against it - 7 live log groups match the page (re-verified 2026-08-21). This sentence said Version B for some time after the page had moved on, which is why the GATE is the authority here and not this file. **The console work in §1 is DONE, and was already done before anyone checked (measured 2026-08-21).** The account holds **exactly 8 log groups, one per live Lambda, every one at 30-day retention, and ZERO orphans** - so the 6 orphaned groups recorded here, and the Signup one said to hold raw emails from 26 Jun-23 Jul 2026, no longer exist. They had aged out under the retention that was applied to them. `flightmap-dev` DOES hold `logs:PutRetentionPolicy` (it lacks only the delete verbs), which is what made the fix possible without a console session. **Re-measure a recorded blocker before working around it.** The historical note: those groups used to **WARN, not fail**, because under an "indefinite" claim they do not contradict the page and deleting them needs `logs:DeleteLogGroup`, which `flightmap-dev` lacks — blocking there would gate every commit in the repo on a console action. When the console work lands, flip §2d back to Version A and the same check validates it. Gotcha: the AWS CLI here emits **CRLF**, so `retention=None\r` never string-equals `None`; the script strips `\r` and that line is load-bearing. Advisory: Prettier, npm audit, **`deployed == source`**, **`site == /v1/score`**.
  - **`tests/responsive.mjs` gained THREE detectors on 2026-08-23, and every one found a live defect on its first run.** It had only ever asked two questions - is the page wider than the viewport, and is a control past the horizontal edge with nothing to scroll it back. Both are about POSITION. Now also: **COVERED** (a control inside the viewport with something painted on top - `elementFromPoint` at its centre, which is the question a finger asks), **CLIPPED ABOVE** (the vertical twin of stranded; a 711px legend rendering from y=-374 was neither overflow nor past the horizontal edge), and a **legend-open page state**, because every entry was audited in its landing state and on a phone the legend ships collapsed - so the clipped detector could not see the defect it was written for. Two exemptions are tested rather than named: a control parked outside its own scroller is a scroll case (the city chips), and an element that returns into view when focused is the skip-link pattern (**focus it with `transition: none`** - `.skip-link` transitions `top` over 0.15s, so a rect read immediately after `focus()` reports the position it is moving away from, which is how that exemption failed on its first run).
  - **`tests/city-switch.mjs` runs at TWO viewports since 2026-08-23**, phone first. It had run at 1440x900 only since the day it was written to catch six cities that threw on selection - so it had never switched a city on a phone, where the scroll strip, the sheet, the toggle popover and the collapsed legend are all driven by JavaScript that does not run above 900px. 11 cities x 2 viewports = 22 switches.
  - **`backend/tests/` joined the ruff targets on 2026-08-04.** It had been outside every one of them — the suite guarding the score engine was the one directory nothing linted, and it held 4 import-order errors and an S105.
  - **The two new advisory stages both compare DEPLOYED state**, which is why they are advisory rather than blocking. `scripts/check_deploy_drift.sh` compares all 14 public surfaces against what CloudFront serves (drift between commit and deploy is expected, so blocking it would go red on nearly every run). `tests/site-api-parity.mjs` compares the score the **live site renders** against what `/v1/score` returns — the only check that reads the *output* rather than the inputs, added after the site and API disagreed on 13% of London postcodes while every component matched. Promote either to `check` once it has a track record; both already exit non-zero only on a measured problem.
  - **Read the exit code, never pipe it.** `preflight | tail` is always 0 — a pipeline exits with its LAST stage's status. That is exactly how `make preflight` reported success on 2026-07-27 while running nothing at all (`make` is not on PATH in Git Bash here).
  - `--skip-e2e` skips **only the three stages that need the network** - the Playwright suite, the extension e2e, and `area pages match the live API`. **Until 2026-08-28 it was a block wrapper that swallowed FOURTEEN stages while printing SKIPPED for two**, then printed a bare `RESULT: PASS`. Eleven of the twelve it hid never touched the network at all: `local smoke`, `degraded + offline fallbacks`, `locator inset`, `selector tiers`, `every city switches`, `map fits its box`, `UK city panel`, `area pages carry real data`, `layers paint only real data`, `responsive, source` and `WCAG source scan` all serve the WORKING TREE, which is precisely why they exist - they gate the deploy. So the flag documented as "skip Playwright (hits the live site)" was really a way to get a green run by not looking, and it hid exactly the gate set that caught every defect in the tabbed-default flip. Now `net_check()` marks the three per stage, a skipped stage still prints its own line **in its own position** (a stage that vanishes from a report is indistinguishable from one that passed), and a run with anything skipped reports `RESULT: PASS (INCOMPLETE - network stages skipped)` and names them. Report went from 20 stages to 32. `--fix` auto-fixes what is auto-fixable.
  - Rewritten 2026-07-27 after the gate produced a false green, a false red, and silently omitted the 167-test root suite. Change what blocks in `scripts/preflight.sh`, **not** in the skill file.
- Run `/careful` before touching live AWS resources, blocks destructive commands
- ~~Use `/aws-debug` when Lambda errors or API Gateway 5xx issues occur~~ **`/aws-debug` does NOT work on this account** (verified 2026-07-26): `flightmap-dev` is denied `logs:FilterLogEvents`, `logs:GetLogEvents`, `logs:DescribeLogStreams`, `cloudtrail:LookupEvents`, `iam:GetRolePolicy`, `lambda:ListFunctions` and `cloudformation:DescribeStackResource`. Only `logs:DescribeLogGroups` (names) works, and the `default` profile's token is invalid. Until a console-side grant lands, debug Lambda faults from the **console** or by **side-effect elimination** — see `OPERATIONS.md` §6. Prefix any `/aws/lambda/...` CLI argument with `export MSYS_NO_PATHCONV=1` or Git Bash mangles it.
- Use **context7** to look up D3.js, AWS SDK, or SAM docs before using unfamiliar APIs
- Use **security-guidance** when editing Lambda functions or API Gateway config
- Use **code-review** on all changed files before committing
- Use **frontend-design** when modifying the UI in index.html

## Build & Deploy

> ## ⚠️ `export MSYS_NO_PATHCONV=1` BEFORE ANY `cloudfront create-invalidation`
>
> Git Bash rewrites any argument that looks like a Unix absolute path into a
> Windows one, so `'/index.html'` reaches the API as
> `C:/Program Files/Git/index.html` and CloudFront rejects the whole batch with
> `InvalidArgument: Your request contains one or more invalid invalidation
> paths`. CLAUDE.md has documented this for `/aws/lambda/*` arguments for
> months; it bites invalidation paths identically.
>
> **It bit on 2026-08-26 AFTER all four upload stages had already succeeded** -
> objects live at the origin, cache not cleared, exit code non-zero only at the
> very end. That is the worst half to lose, because the deploy looks done. The
> same script got it right on its next two runs with the guard in place.

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

- **Browser extension** (`extension/`, added 2026-08-06): unlisted MV3 demo showing `/v1/environment`, `/epc`, `/sold-prices` and `/nhs` data on Rightmove listings. **`LONDON_BOUNDS` is DELETED (2026-08-23) and the panel's coverage caveat is read from the response.** It was a rectangle deciding whether to show a caveat, and it was wrong twice over. It existed to caveat the TRANSPORT section - "TfL only knows about London" - which was removed from the extension on 2026-08-06, so it outlived its reason by seventeen days and was quietly repurposed to noise coverage without the geography being re-asked. And **a bounding box is not containment, fifth instance**: verified live, Watford `WD17 2RA` and Dartford `DA1 1DR` sit INSIDE the box while `/v1/environment` answers "outside every city Sky Score covers", so the caveat was hidden exactly where it was true; `M3 4EN` sits outside the box and is a covered city with its own geometry since 2026-08-21, so it was shown exactly where it was false. Watford also returns a **measured** `roadNoiseLdenDb` of 55.2 while the suppressed caveat claimed road figures "may be absent". `coverageCaveat()` now reads `aircraftQuietBasis`, which is the only place the answer exists. **The e2e was asserting the defect** - it checked that Manchester received a "coverage is strongest in London" caveat - which is the fourth instance in this repo of a passing test reading as evidence. The prose match `coverageCaveat()` depends on is **guarded, not noted**: the e2e asks the live endpoint for a known-uncovered coordinate and asserts the phrase is still there, so wording drift reds rather than silently returning null forever. Adding `aircraftQuietCoverage` to the response is the better shape and would delete the constant. (Transport was dropped 2026-08-06 — Rightmove already prints nearest stations with distances, so the section duplicated the page it sat on. This line said `/transport` for a day after it was removed.) **Not for publication** — see `extension/README.md` for the ship gates. **Panel UI reworked 2026-08-07, extended 2026-08-08**: each measurement carries a scale bar positioned against its WHO guideline (domain is 0 to twice the guideline, because the observed-London-range alternative would be a number invented at the point of drawing it), explanatory prose collapses into one disclosure, and the DEFRA vintage is a `2021` tag on the two rows it applies to rather than a paragraph under rows it does not. **EPC and Sold nearby now lead with a chart and fold their rows into `<details>`**; the panel collapses to its header on a header click. The EPC chart is **seven discrete band columns, deliberately not a `scaleBar`** — `cert.rating` looks plottable but is synthesised from `BAND_MIDPOINT` in the Lambda (MHCLG dropped the numeric rating), so every C returns exactly 75. The sold chart marks the **asking price**, which `extract.js` now READS but still never transmits, and only on a positive `RES_BUY`/`BUY` signal — on a letting Rightmove's `price` is a monthly figure and would plot as an extraordinary bargain. **Gotcha: `display: flex` on a `<summary>` removes the `::marker` box in Chrome**, so `list-style: revert` cannot restore the disclosure triangle; the panel draws its own. **Sales and lettings get the same section ORDER and different CONTENT** (2026-08-08): on a letting Sold nearby is replaced by **Typical rent** (ONS borough average, `extension/data/london-rents.json`, rebuild with `scripts/build_london_rents.py`) and EPC gains a MEES line. Promoting EPC to the top on lettings was tried and **reverted** — moving sections between listing types reads as inconsistency, not judgement. The rent figure is **deliberately not a chart**: it is a borough-wide average and the sold-price grammar would claim a comparable. The dataset is **bundled and served by the service worker**, never `web_accessible_resources` (which exposes it to every host page), so it needed **no Lambda change and no deploy**. Extraction is a five-strategy cascade and is deliberately site-agnostic; the only Rightmove-specific part is `fromRightmovePageModel()`, which unpacks `window.__PAGE_MODEL` (a JSON *string* holding a *flattened* array where `{"latitude":160}` is an **index**, not a value). `run_at` is `document_end`, **not** `document_idle` — the page model is transient and React hydration removes it, so idle arrives after the data is gone. `tests/fixtures/rightmove-real-sw5.html` is a real saved listing and is the only fixture that can contradict its author; 33 green checks once coexisted with an extension that had never worked on a real page.
- **The DEFRA raster tier reaches EIGHT MORE CITIES as of 2026-08-12, and the scope was MEASURED not assumed.** Twelve per-airport coverages are on disk; **seven** are loaded. `heathrow`/`londoncity` are excluded because London's region export covers London *better* (35,352 postcodes vs their 17,330) — loading them would replace good coverage with less. `gatwick`/`luton`/`stansted` are excluded because all 3,704 of their readings land outside `LAD_TO_BOROUGH` (Surrey, Beds, Essex), which `/v1/score` cannot resolve to a city. The seven carry **7,339 postcodes = 0.6–3.9% of each city**: these are contour strips, not city rectangles. Run `scripts/probe_aircraft_raster_coverage.py` before believing any coverage claim here, and `scripts/load_aircraft_rasters.sh` to load + deploy (it waits for the air-quality loader, then gates the deploy on the load succeeding).
  - **It corrects a mean 2.224 score points** against the geometry tier, signed **-2.104** — geometry reads these postcodes LOUDER than DEFRA measured. **London already got a correction of the same size (2.070) from its own raster**, so before this the product ranked London postcodes measured one way against eight cities' measured another. That inconsistency, not accuracy, is the argument.
  - **CAVEAT THAT MUST TRAVEL WITH THOSE NUMBERS: Round 4 maps 2021, a COVID year DEFRA itself calls atypical.** Some share of the -2.1 is real traffic reduction, not estimator error. See [[project-lcy-airport-weighting]]; never apply an estimated correction for it.
  - **The two nodata sentinels have OPPOSITE SIGNS.** London's region export declares `+3.4e38`; every per-airport coverage declares `-3.4e38`. The loader's `raw > 1e30 or raw == nodata` survives only via the equality branch. The Lambda's read guard called itself "a range, not a value" while implementing a FLOOR only, so `+3.4e38` passed and scored `0.0` — maximally loud. A ceiling (`_RASTER_MAX_PLAUSIBLE_DB = 120.0`) was added 2026-08-12 and proven to fire both ways.
  - **The client dataset is split by SOURCE, not by city**: `aircraft-quiet-london.json` (region export) and `aircraft-quiet-regions.json` (per-airport, 98 KB). Both merge into one flat `AIRCRAFT_QUIET` map because postcodes are globally unique. **Ship order is LOAD THEN DEPLOY** — loading flips `/v1/score` while the site keeps its status-quo geometry; deploying first would flip the surface users actually look at onto readings the API cannot reproduce.
- **DEFRA raster quarantine LIFTED 2026-08-06.** `RASTER_TIER_QUARANTINED = False`. The blocker was that `index.html` computed quiet from geometry while `/v1/score` would answer from the raster, diverging on the ~9% of London DEFRA measures. Closed by `data/aircraft-quiet-london.json` (35,352 postcodes, 461 KB), which ships the **computed quiet score, not decibels**, so neither side reimplements the ramp. **Regenerate with `python scripts/build_aircraft_quiet_dataset.py` whenever `lden_db_to_quiet` changes** - the file embeds `methodologyVersion` and the page refuses a mismatch. Deploying the file without the Lambda, or vice versa, recreates the divergence.
- **Mobile city switcher is a horizontal SCROLL STRIP** (≤900px), added 2026-08-11. With nine cities the chip row was 453px wide against a 375px viewport and `position: absolute` with only `left` set, so it sized to content and the map container clipped it: **3 of 8 UK cities untappable at 320px**, 2 at 375/390. `right: 60px` bounds the row and clears the map-controls column; `flex: 0 0 auto` makes chips scroll rather than squash; the active chip is scrolled into view on render. **The edge fade is load-bearing** — `data-scroll` is measured and set to `right`/`left`/`both`, because this app already retired one scroll strip (the layer toggles, see the comment by `.layers-trigger`) for the exact reason that a strip with no affordance reads as absent. **The sheet boots at PEEK on every mobile width (2026-08-23), and the note that used to sit here had the history backwards.** It read: *"the sheet still opens over the map on phones ≤640px and that is deliberate; it carries an Apple Guideline 4.0 rejection scar"* - which reads as though Apple required the auto-open. **Apple rejected build 19 FOR the sheet hiding the map** (Guideline 4.0, Design, 2026-05-18, iPad Air 11" M3). The same-day fix moved the auto-open threshold from ≤900px to ≤640px, giving iPad portrait its map back and leaving phones with exactly the behaviour the reviewer had objected to. **The line was drawn where the rejection stopped, not where the reasoning did** - Apple only tested an iPad. Measured before the change: **12% of the viewport was map at 320, 375, 390 and 414**, against iPad portrait's 71%, and the city chips and the legend were both entirely below the fold at boot. Peek gives 61-75%. Nothing is lost: the peek height is 220px, sized in the CSS so **the search box is reachable without tapping the handle**, and `revealSheetIfMobile()` still auto-opens the moment a result lands - the discoverability argument that chose auto-open is about a RESULT being missed, and at boot there is no result. **Native is unaffected either way**: `.is-native .app > .sidebar` sets `transform: none !important`, so `.sheet-open` has no visual effect there.

**The map FITS its box since 2026-08-24 (`fd2558b`), and the fit is a RATIO, not a constant.** The projection scale in `CITY_DATA` is fitted by `fit_city_projection.py` to the DESKTOP map box; the mobile path pushed it through `w < 600 ? scale * 0.625 : scale`, written out in THREE places. Measured before the fix: **every city drew part of its geography outside the SVG box on every phone** - London 40.9% off-screen at 320x568 with Heathrow 140px past the left edge - and LANDSCAPE failed in the other axis (28.4% clipped top/bottom at 844x390, because `w < 600` is false there). **No gate could see it**: a borough is not a control, so `responsive.mjs`'s four questions all pass while the map is unreadable; `city-switch` counts outlines, right whether or not visible. 53 of 90 city/viewport combinations were failing, all gates green. Now: `fittedScale()` (one holder) scales by `min(w/1040, h/746, 1)` - the reference is the box holding the largest geography ANY city draws (Tyne and Wear is the tallest, NOT London), so desktop is unchanged at factor 1.0 and each city keeps its own framing. `mapCentreY()` centres the map in the band the nav and sheet leave uncovered, and clips to it (`--map-band-top/bottom`) because a city's AIRPORTS are outside its boundary - LTN/STN otherwise paint into the chip strip. **`tests/map-fit.mjs` is blocking in preflight** (9 viewports including landscape, both directions proven red; a 12th city taller than Tyne and Wear goes red there first). Same commit: the sheet peek's six derived literals became ONE `--sheet-peek` holder capped `min(220px, 42dvh)` - a landscape phone matched the iPad `min-width: 640px` override and gave 67% of a 390px-tall screen to the sheet; the layers popover applies at `max-height: 500px` too, because **three separate mobile rules keyed on WIDTH while the failing dimension was HEIGHT**. Also fixed there: legend `<summary>`/`<em>` dark-on-dark on the phone panel (inherit-by-default + the inline style moved to CSS - the I7 mechanism again), `trackEvent` scoped inside an IIFE so the notify form had NEVER sent a request (ESLint's no-undef had said so all along), an unguarded `localStorage.getItem` in `init()` blanking the app when site data is blocked (all storage via `readFlag`/`writeFlag` now), the postcode panel printing unrounded `scoresRaw`, the badge preview missing from `img-src`, and **`sw.js` serving `/data/` cache-first** - Cache Storage ignores the load-bearing `no-cache` header, so `borough-extra.json` was pinned forever; `/data/` is network-first since v1.0.34.

**Three more collisions were invisible until the map became the landing surface**, all measured with `elementFromPoint` rather than eyeballed:
- **`.first-hint` covered the title, the country tabs and the top zoom button** at every phone size. It sat at `top: 24px` while the whole band y 8-148 is chrome (map-controls y 8-148, title y 36-59, tabs y 70-94, chips y 96-140). Now `top: 156px` on mobile.
- **`.site-footer`, `.map-legend` and `.layer-toggles` are all bottom-anchored in `#map-container` at `z-index: 10`**, and the footer stands 34-72px tall depending on how its links wrap - so it ran through both. At 901x800 it drew "AREAS PRIVACY" across the LABELS toggle, which was genuinely unclickable. **`--footer-inset` is MEASURED by `updateFooterInset()`**, because a constant is right at one width and wrong at every other. The 901-1366 band needs it too: a plain `bottom: 28px` there silently reinstated the collision, and that block's own comment claimed the footer inset existed "to clear the layer-toggle band", which measurement disproved.
- **The legend's `max-height` must clear the NAVIGATION, not just the viewport.** A cap of `100dvh - 248px` fitted the screen and still grew up through the country tabs and the first two city chips. It is `calc(100dvh - 232px - 156px)` - its own bottom offset, plus the bottom of the nav band.
- **Frontend**: Single `index.html` (~8,200 lines as of 2026-07-24), vanilla JS, D3.js maps, all UI logic inline. **`d3.v7.min.js` sits at the FOOT of `<body>`, immediately above the inline script, with a `rel=preload` in `<head>` (moved 2026-08-23).** In `<head>` it blocked the parser, so 280 KB had to land before a pixel of shell painted: measured on emulated 3G, **First Contentful Paint 3592 ms -> 1124 ms**, with time-to-map 8614 -> 8698 ms, inside run-to-run noise. **`defer` is the obvious fix and is WRONG here** - deferred scripts run after the parser, therefore after the inline script, so every top-level `d3` reference in ~8,400 lines would break. Moving the tag changes execution order not at all. The preload's `as`/`integrity` must match the tag or the browser silently fetches it TWICE with everything still working, so `tests/smoke-local.mjs` counts the requests and asserts exactly one (proven red with `as="fetch"`). **The mobile bottom-nav redesign is gated on `.is-tabbed`, NOT `.is-native`, since 2026-08-26.** The redesign (`#mobile-nav` + `.app[data-mview]` 3-tab views via `setMobileView()`, map-as-background) is set UNCONDITIONALLY on native - so the App Store build is byte-identical - and on the WEB only behind **`?tabbed=1` at <=900px**, deployed and live. **The website still serves the classic bottom-sheet layout by default** (`.sheet-handle` + `setSheetState()`), and `tests/native-sim-render.mjs` + `tests/live-mobile-verify.mjs` both assert that; **making tabs the web default means INVERTING those two gates deliberately**, not deleting them. Why it stopped being native-only: `MOBILE_REDESIGN_PLAN.md` v3 gated it because the redesign "never shipped to either store" - and iOS 1.0.21 carrying it went live on 1 June, so the condition expired. Measured live at 375x667: map **34.6% -> 78.7%**, visible controls **18 -> 14**. **`applyTabbedLayout()` must run on RESIZE, not only at parse time** - it originally ran once, so opening at desktop width and narrowing (DevTools device mode, a phone rotating) left the class unset and the flag looked broken. A width-gated class evaluated once is load-time-gated. Desktop (≥901px) keeps the two-column grid regardless. See `MOBILE_REDESIGN_PLAN.md` (v3 section).
- **Backend**: `backend/template.yaml`, SAM/CloudFormation defining the 8 active Lambdas + API Gateway + DynamoDB. (Was 7 until 2026-08-06, when `chat` was restored to the template as a retrieval-only function; count the `AWS::Serverless::Function` blocks rather than trusting any prose, here or elsewhere.)
- **B2B funnel pages** (deployed alongside `index.html`): `/api/` landing (`api/index.html`), `/pricing` (`pricing.html`, added 2026-07-23: 90-day £2,500 pilot + Free/£499 Professional/Enterprise tiers + founder block), `/privacy` (`privacy.html`). **S3 key gotcha:** the `sky-score-rewrite-index` CloudFront function rewrites extensionless paths to `<path>/index.html`, so privacy/pricing MUST be uploaded to `privacy/index.html` and `pricing/index.html` keys (`make web-deploy` does this correctly since 2026-07-23; a flat `privacy` key is a dead object).
- **Active Lambdas** (in `backend/lambdas/<name>/app.py`):
  - **`/v1/environment` DERIVES ITS CITY (2026-08-21).** It called
    `calc_postcode_quiet(lat, lon, 'london', ...)` — the city as a string
    literal — for every UK coordinate from the day it shipped. Measured:
    **M22 5RX, 1.2 km from Manchester Airport, published 10.0** (top of scale,
    "no aircraft noise") against Manchester's own **2.0**. Over 6,000 sampled
    NSPL postcodes the fix moved 4.9%, and **291 of 291 moved LOUDER, none
    quieter** — because every term in `calc_postcode_quiet` is distance-gated, a
    geometry lacking your airport is structurally incapable of over-reporting.
    **`derive_city()` is now the ONE holder** of LAD→city, shared with
    `resolve_query`; do not inline a second copy. Outside the 13 cities (**68%
    of live UK postcodes**) it takes the loudest of all UK geometries, which is
    safe only because `/v1/score` 404s those postcodes and a maximum cannot
    under-report. **`reverse_geocode` returns a dict now, not a string.**
    Related gotcha: postcodes.io reverse lookup defaults to a **100 m radius**,
    so a coordinate over a runway or field returns `result: null` — that is what
    defeated the first attempt to reproduce this.
  - **Road Lden is a RANGE, both ends (2026-08-21).** `road_lden_from_row` was a
    floor alone while its mirror `lden_from_row`, eleven lines above and reading
    the same row, gained a ceiling on 2026-08-12. **The two GeoTIFF nodata
    sentinels have opposite signs**, so a floor catches `-3.4e38` and publishes
    `+3.4e38` as `roadNoiseLdenDb` — proven at HEAD, not theorised. Dead
    `_lookup_road_lden` (62 lines, third copy of the floor, zero call sites
    since `4e90cc0`) and its orphaned LRU are deleted.
  - `score`, B2B scoring engine. API-key gated on `/v1/score` and `/v1/score/batch`. **`/v1/regions` and `/v1/changes` are NOT gated** - both answer 200 with no key, re-verified live 2026-08-27. This line claimed otherwise for months, and `template.yaml` and the `handle_regions` docstring were corrected on 2026-08-21 while THIS one was not, so the falsehood survived in the file sessions actually read. Whether they SHOULD be gated is open (audit I1); the deployment is the authority, not this sentence. **`/v1/environment?lat=&lon=` is UNAUTHENTICATED** (added 2026-08-06): it reverse-geocodes a coordinate and returns MEASUREMENTS only (aircraft/road Lden, NO2, PM2.5, each with its WHO guideline) - no weights, no persona, no composite score, because the browser extension is a public artefact and cannot hold a key. Throttled 5 RPS.
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

  **`scripts/load_aircraft_rasters.sh` is the chained aircraft-raster runbook (2026-08-12).** It waits for the air-quality loader's checkpoint to disappear, loads the seven per-airport coverages in sequence, and **gates the frontend deploy on all seven succeeding**. Resumable — each raster keeps its own checkpoint, so re-running after any death continues. `SKIP_WAIT=1` to skip the wait, `NO_DEPLOY=1` to load only. Check progress with `tail aircraftload.log`.

  **`Start-Process -ArgumentList '-lc','<command string>'` SILENTLY RUNS ONLY THE FIRST WORD.** PowerShell joins ArgumentList elements without quoting, so `sh -lc 'cd X && run.sh'` becomes `sh -lc cd X && run.sh` — sh takes `cd` as the whole command, exits 0 in milliseconds, and leaves two empty redirect files and no log. It looks exactly like a script that crashed before its first line. Pass the SCRIPT PATH as the argument and let `-WorkingDirectory` do the `cd`.

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

See `AUDIT_REPORT.md` (**last full audit 2026-08-31**; previous archived as `AUDIT_REPORT_2026-08-29.md`) for the live list. **Two numbers we publish today are wrong and neither is drift**: the aircraft near-field floor is a DISC compared against runway-shaped contours (Rushcliffe publishes `Quiet skies 10.0/10` over 10.43 km2 at >=55 dB), and the neighbourhood medians include HM Land Registry **Category B** transactions, which HMLR's own statistics exclude - 412 of 485 published prices wrong, so the product carries two price bases. A full re-derivation reproduced `borough-extra.json` with 0 disagreements, which is why every gate is green: both are SHAPE errors, not drift. The long-standing trio closed 2026-07-24: I4 (borough metadata duplication — resolved by removal, `score/app.py` is the single holder), I6 (DLQ on async Lambdas — moot, all 7 functions are APIGW-synchronous), I14 (`PROJECT_DOCUMENTATION.md` — fully refreshed).

Most of the May-6 critical findings have shipped fixes — see `AUDIT_REPORT.md` for the triage column.
