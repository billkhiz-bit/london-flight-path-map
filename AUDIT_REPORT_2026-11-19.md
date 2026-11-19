# Audit Report — Sky Score

**Date:** 2026-11-19
**Commit audited:** `f8715f75` (the 19 commits since the 12 November audit, `741aa88c..f8715f75`: the street report's
three pages, the planes January-September roll and pick C, the September HPI roll, measured air in `/v1/environment` and
the extension, the weather fetcher's end-date fix).
**Files scanned:** about 95 changed source files (Python, JavaScript modules, HTML, CSS, shell, YAML, the CI workflow; the
built `area/` and `planes-overhead/` pages sampled through their builders), plus a sweep of the whole backend for
security and of every test file changed in the range.
**Method:** four read-only reviewers in parallel (A correctness of the changes, B security, C frontend and accessibility,
D the data pipeline, builders, deploy and gates), with no browser, local server, preflight or port opened, so nothing here
is a layout measurement. Each finding says how it was checked: RAN (executed against data, a stub or the live service),
READ (followed end to end in the code), or PLAUSIBLE. **Every Important finding was re-read in session against the code
or the live data before it went in this report.** The 12 Nov audit's 22 Important and 30 Minor items were all fixed by
13 Nov; none was found to have regressed. The 9 Nov audit's M-7 (static fallback, Bill's call) and M-9 (`npm install` of
html-validate, Bill's command) stay open. A `/code-review` of the measured-air change earlier the same day found 9 issues
(5 fixed before its commit, `docs/lessons/in-progress-measurements.md`); they are not repeated here.

## Critical Issues

None.

## Important Issues

| # | Issue | File:Line | Category | Status |
|---|-------|-----------|----------|--------|
| I-1 | **The full map's borough panel gives buying advice, and two of its typed growth claims are now false.** "PROPERTY ADVICE" heads curated notes that say "Avoid anything south of the A4", "use noise as a bargaining chip", "Use the noise factor to negotiate", "Avoid Royal Docks", "Avoid Howard Beach"; Newham's note says "Fastest-growing property prices in London" beside its own -5.1% (September HPI), and Trafford's "fastest-rising borough in Greater Manchester" at +4.7% where Stockport is +5.2%. Breaks "information, not advice" and "derive, never copy"; no gate reads a typed superlative. READ (C); both trends **verified** in `index.html` | `index.html:14228`, `6664`, `6965`, `7660`, `7668`, `7684`, `7772`, `7788` | Wording / data accuracy | **Fixed 19 Nov in source** with the borough answer card (Bill's pick A): `getVerdict()` gone, "Prices" for "Property advice", the curated `property` notes deleted (38, Bill's word), 9 notes cut to facts; `tests/test_borough_card.py` (every borough) and `tests/uk-city-panel.mjs`. **LIVE 19 Nov** (`f0d7904c`) |
| I-2 | **Pick C ("the nearest airport is one we do not count") picks "nearest" three ways, and the district pages never say it.** The map uses its city's own airport list within 30 km, the front page every procedure airport within `AIRPORT_SCOPE_KM`, the report every one within 40 km (`SCOPE_KM`). WN1 1AE: front page and report say Liverpool (27.5 km) is not counted and lead with nothing; the map's card leads "about 39 Manchester planes a day". S70 1AH: the report names Leeds Bradford (36.1 km), the map and front page do not. District pages L35, WA9-WA12, WN1-WN6 show Manchester's figures and never name Liverpool John Lennon, 9.5-28.8 km away: the Speke defect pick C was built to end. RAN (A); the three rules **verified** | `index.html:14763`, `js/home-engine.mjs:1775`, `js/street_report_page.mjs:179`, `scripts/build_planes_pages.py` | Correctness | **Fixed 19 Nov in source** for the map, front page, report, PDF and sample check: one rule, `planesNearest()` (`tests/planes-model.mjs`); the map's Nearest airport card lists every UK airport with routes. District pages: **fixed 19 Nov** on Bill's yes: `build_planes_pages.nearest_airport()` (the rule's Python twin, held equal on ~3,600 points) names Liverpool on the 12 pages where it is nearest to some measured postcodes (L35, WA3, WA9-WA12, WN1-WN6) |
| I-3 | **The free street report reads a failed planes download as "not counted".** `maybeJson()` turns a network error or a 5xx into null for `airports.json`, the district file and the layer index, so a copy made during an outage drops its planes block without a word and carries that into its reference, and a check during an outage tells a genuine copy "does not match today's figures ... or the copy you were shown was changed". The PDF script refuses instead. READ (A); **verified** | `js/street_report_page.mjs:73-80`, `138-140`, `381` | Correctness | **Fixed 19 Nov in source**: the two shared files refuse; only a district file's 404 is "not counted" (`countedJson`); `tests/front-page.mjs` block 18 reaches both on purpose |
| I-4 | **A report card prints whole decibels beside a verdict decided on the unrounded figure.** 45.2 dB prints "45 dB on DEFRA's map, over the WHO guideline of 45" (Worth a look); 44.6 prints "45 dB ..., under the WHO guideline of 45" (Good here). At least 476 London postcodes on DEFRA's map sit at 45.1-45.45 dB. The front page's tile says "45.2 dB ... Over", consistent. RAN (A); **verified** | `js/street_report.mjs:249-256` (and the key figure, `:658`) | Correctness | **Fixed 19 Nov in source**: one decimal on the card and the key figure (the API sends one); `tests/street-report.mjs` at 45.2 and 44.6; sample regenerated (XRQT-RHB3), its still rebuilt |
| I-5 | **CI has been red on every commit since 2 Nov, and its root suite collects no tests.** `tests/test_build_planes_layer.py` imports `scripts/build_planes_layer.py`, which needs scipy, not in CI's pip line, so `pytest tests/` stops at collection (the 13 Nov `pypdfium2` pin "so the text floor runs in CI" has never run there); `test-e2e` fails installing Chromium: "Playwright does not support chromium on ubuntu26.04-x64" (`ubuntu-latest` moved; Playwright 1.58.2). Recorded nowhere, the 12 Nov audit included. RAN (D, `gh run view --log-failed`); **verified** on `f8715f75` | `.github/workflows/ci.yml:97`, `112`, `120` | Gates | **Fixed 19 Nov in source**: scipy 1.16.3 and tzdata 2025.2 pinned, every job on `ubuntu-24.04`; a venv with only CI's packages collected 3,149 root tests. **Verified 19 Nov**: CI green on `f0d7904c`, its first since 2 Nov |
| I-6 | **The weather fetcher's fix did not reach the 7 US stations, and the cache cannot heal them.** The 18 Nov refetch took the 15 UK stations' three short months (and EGLL's `-air`); JFK, LGA, EWR, TEB, SFO, OAK and SJC still end 30 Dec (2025-12), 29 Sep (2026-09) and 24 Oct 14:51 (2026-10, fetched while it ran). `todo` treats any file for a finished month as cached, so a plain run never refetches a partial one: `finished()`'s promise holds only until the month ends. Latent: `data/us-runway-use.json` and the NYC yardsticks were built 16-17 Oct, before this cache; the next rebuild would read the short months. RAN (D); **verified** (`JFK-2026-09.csv` ends 2026-09-29 23:51, EGLL's 30 Sep 23:50) | `scripts/fetch_metar.py:92-93`; `data/metar/{JFK,LGA,EWR,TEB,SFO,OAK,SJC}-{2025-12,2026-09,2026-10}.csv` | Data accuracy | **Fixed 19 Nov**: the 21 US files refetched (1,569 readings added, none lost or changed; old copies in `data/metar-set-aside-2026-11-19/`); a finished month is cached only if it reaches its last day (`due()`, red on the old rule) |

## Minor Issues

| # | Issue | File:Line | Category | Status |
|---|-------|-----------|----------|--------|
| M-1 | The report's planes card prints a statement under "Next step:" ("The wind decides which way Heathrow flies, and that decides your day."): `t.say[0]` is `windShort`. RAN (C, the sample PDF's text) | `js/street_report.mjs:281`, `js/planes.mjs:89` | Wording | **Fixed 19 Nov in source**: the planes card has no step (`tests/street-report.mjs`) |
| M-2 | The report's page heads and their sections are all `h2`, so the outline (and the tagged PDF's) loses the grouping by page (WCAG 1.3.1). READ (C) | `js/street_report.mjs:974-992` | Accessibility | **Fixed 19 Nov in source**: section headings `h3` under each page `h2`, styles unchanged (`tests/street-report.mjs` section 9) |
| M-3 | Two late redraws rebuild the whole postcode panel: when `borough-extra.json` lands (`redrawPanelSubject`, M-15) and the Bay Area neighbourhood redraw (I-17); open tiles close, focus drops to `body`, and the first re-announces "Results loaded" (WCAG 2.4.3; the repo's "a late answer never moves the visitor"). PLAUSIBLE (C, read, not run) | `index.html:9899`, `9919`, `17101`, `14975` | Accessibility | Open (the borough card now supersedes in-flight searches; the postcode redraws are as reported) |
| M-4 | At 320 px the front page's yardstick short forms may need three lines where two are reserved, so the tiles grow as the figures land. PLAUSIBLE (C, from font metrics) | `home/index.html:245-249` | Layout shift | Open |
| M-5 | The Lambda checks the air files' text for type only (no length cap; `classification`/`type` not allow-listed as the builder does) and passes any https credit link, which the extension makes clickable inside Rightmove's page. Needs a bad upstream row or a bad deploy, not a caller. READ (B) | `backend/lambdas/score/app.py` `check_air_file`, `_air_entry`; `extension/content/panel.js` `nearbyCredits` | Security (defence in depth) | **Fixed 19 Nov in source**: lengths capped, settings plain words, each credit to its publisher's host, in the Lambda and the extension (both tested). **LIVE 19 Nov**: reviewed changeset, ScoreFunction code only |
| M-6 | `/nhs`'s coarse UK box still admits Dublin, Cork and Boulogne-sur-Mer (Galway is out). Residual by design: the real control is the reserved concurrency waiting on the console. RAN (B, the box) | `backend/lambdas/nhs/app.py:47-48`, `388` | Security (availability) | Accepted: the console step |
| M-7 | Two callers build `planesModel` without `nearest`, so the sample check recomputes the headline differently from the report it checks (harmless for TW9 3PZ, under Heathrow). READ (A) | `scripts/check_sample_report.mjs:64`, `js/home-sections.mjs:265` | Correctness | **Fixed 19 Nov in source**: both pass `planesNearest()` |
| M-8 | A monitor that closed mid-year (only CANT, 4 Nov 2024) has its period worded "2024-01-01 to 2024-11-04" by the API and "in 2024" by the site. Reachable only near Canterbury. READ (A) | `app.py` `_air_entry` / `air_period_words`; `js/street_report.mjs` `monitorPeriod` | Wording | Open |
| M-9 | `tests/test_london_area_postcodes.py` skips the three double-quoted area names ("Shepherd's Bush", "St John's Wood", "Regent's Park"); the `>= 100` floor hides it. All three are live today. RAN (D) | `tests/test_london_area_postcodes.py:26` | Gates | **Fixed 19 Nov**: every line must parse; the three are named in the test |
| M-10 | `test_provenance`'s every-value loop never sees `airMeasuredNearby`: no provenance fixture carries it and `conftest.py` stubs it for that module; only `test_air_nearby.py`'s one synthetic body covers it. RAN (D) | `backend/tests/test_provenance.py:63` | Gates | **Fixed 19 Nov**: a live SW11 1AA answer with the block is the 12th fixture; the loop must see the block |
| M-11 | The plane counter draws a straight line across METAR gaps over 6 h (15 cached months; EGLC 21 h on 4 Oct 2025, EGNM 34.5 h in Dec 2025) with no flag. Effect on counts PLAUSIBLE, not measured (D) | `scripts/adsb_movements.py` `_interp`, `FieldLevel` | Data accuracy | Open |
| M-12 | `scripts/deploy_hpi_roll.sh` still runs a blind `sam deploy --no-confirm-changeset` (CLAUDE.md names it the monthly roll and refuses blind deploys), and has no `open-data-deploy` though each price roll rewrites `open-data/sky-score-boroughs.csv`. Predates the range. READ (D) | `scripts/deploy_hpi_roll.sh:52`, `59-62` | Deploy | **Fixed 19 Nov**: the script stops at the changeset; `--after-backend` ships web, area, meta and open data |
| M-13 | `origin/n65` lacks the fetcher fix (local `n65` has it, unpushed); `build_aircraft_quiet_dataset.py` has no `--check`, so its 13 Nov note edits (builder + both JSON files, by hand) are held only by the wording gate. READ (D) | `scripts/build_aircraft_quiet_dataset.py` | Gates | Open: n65 is pushed with its next commit (this session); `--check` for the builder not started |

## Checked and found sound

**Security (B):** no Critical or Important. `air_file`/`_air_body`: fixed URL keyed by kind, no caller input or data
outward, 2 MB cap in 64 KB `read1` chunks, about 2 s + one read at most, every failure a notice; the extension builds
no HTML from a response (no `innerHTML` in `extension/content/`), only `^https://` links, `noopener noreferrer`;
`npm audit` root 0 high/critical (3 moderate, the known M-9; 0 with `--omit=dev`), `mobile/` 0 high/critical (5
moderate in the build chain; 0 with `--omit=dev`, M-13 of 12 Nov holds); `template.yaml` unchanged, every route keeps its
throttle; live headers (XFO DENY, HSTS, nosniff, Referrer-Policy, Permissions-Policy) on `/`, `/reports/street/` and data;
no secret in any tracked file; CI actions pinned by SHA; no `eval`/`exec`/`shell=True`/disabled TLS in any Lambda.
**Correctness (A):** `weighted_total()`; `airMeasuredNearby` against the site's JS (staleness, scope, tie-break,
`shown_km`); the HPI roll's holders moved together (13 unchanged prices within the £500 tolerance); `request_end`;
`district_context(skip=)`; `price_ranks` "joint"; `card_items` tones; the NHS, signup and favourites fixes;
`redrawPanelSubject` scope; `councilElsewhere`; references unmoved by pick C.
**Frontend (C):** the yardstick's verdict in words at 4.67:1; the search guide's ring at 3.84:1 with a reduced-motion
path under 5 s; Escape's one effect; `aria-pressed` on Labels; the profile chips' focus; the street report's marks,
contrasts, chart labels and its iframe; the area pages' card; the extension's block (h3 then h4, 5.30:1, text nodes only).
**Pipeline (D):** preflight 82 `check` (+1, "street report: as the site draws it"), 27 `advise`, 9 `net_check` (+1,
"sample report == today's figures"); `check_sample_report.mjs` proven red on a scratch copy; the text floor; the freshness
retries; drift 55 surfaces, 42/42 data, 153 area pages, planes 25/25, pages 25/25, layer 31/31; the Jan-Sep planes roll's
`--check`s and removals (48 pages and 5 layer files 404 live); every CLAUDE.md line added since 741aa88c names a test that
exists and asserts it; 15 changed root test files 1983 passed.

## Not covered

No browser, so no layout, contrast or axe measurement, no real reflow at 320 px and no screen-reader output; focus
behaviour was traced from the code. The full map's dark theme, the generated area and planes pages beyond samples, and
the larger loaders were not swept. The live write routes (signup, favourites, chat) were not exercised.

## Summary

- Critical: 0
- Important: 6 (I-1 to I-6), each verified in session; ALL fixed on 19 Nov and LIVE the same day (`f0d7904c`; I-2's
  district pages after it, on Bill's yes); CI green again
- Minor: 13: 7 fixed on 19 Nov (M-1, M-2, M-5, M-7, M-9, M-10, M-12), M-6 accepted (the console step), 5 open: M-3,
  M-4 (needs a browser measurement), M-8, M-11, M-13's `--check`
