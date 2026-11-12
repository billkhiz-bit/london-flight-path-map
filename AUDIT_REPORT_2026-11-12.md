# Audit Report — Sky Score

**Date:** 2026-11-12
**Commit audited:** `741aa88c` (the 14 commits since the 9 November audit, `e0e7b358..741aa88c`), plus the uncommitted
working tree: the two-page street report build of 11 Nov (`js/street_report.mjs`, `js/street_report_page.mjs`,
`js/panel-findings.mjs`, `scripts/address_noise_report.mjs`, `tests/street-report.mjs`, `scripts/preflight.sh` and the
wording on `/`, `/pricing`, `/reports/`).
**Files scanned:** about 407 tracked source files (Python, JavaScript modules, HTML, CSS, shell, YAML; the built `area/`
and `planes-overhead/` pages sampled through their builders), split over five territories: A the changes since 9 Nov,
B the backend and security, C the full map (`index.html` and its modules), D every other page, E the data pipeline,
builders, deploy and the gates.
**Method:** five read-only reviewers in parallel, with no browser, local server, preflight or port opened, so nothing
here is a layout measurement. Each finding says how it was checked: RAN (executed against data, a stub or the live
service), READ (followed end to end in the code), or PLAUSIBLE. Every Important finding marked **verified** was re-read
in session against the code before it went in this report. The 9 Nov audit's closed items were not re-reported; none
was found to have regressed. Its M-7 (static fallback, Bill's call) and M-9 (`npm install` of html-validate, Bill's
command) stay open.

## Critical Issues

None.

## Important Issues

| # | Issue | File:Line | Category | Status |
|---|-------|-----------|----------|--------|
| I-1 | **A district search takes the council postcodes.io lists first, and it lists them alphabetically.** On 60 city-edge districts, 36 get a council that is not where the district's centre is. Covered places answer "not covered" (UB8 Uxbridge, RM14 Upminster, WA14 Altrincham, IG8, KT4, SK8; L24 and DE74, which hold Liverpool's and East Midlands' airports), and uncovered ones get a London council's figures (TW15 Ashford shows as Hounslow, DA1 Dartford as Bexley). RAN against postcodes.io; line **verified**. Fix: choose the council holding the district's centre (or most of its postcodes), never `[0]`. | `index.html:11259` | Correctness | **Fixed 12 Nov**: the postcode nearest the district's centre names the council, only one of those listed (`tests/panel-findings.mjs`, red with `[0]` put back) |
| I-2 | **The verdict line claims "strong growth" from the affordability score.** `a >= 7 ? ' and strong growth'` reads `scores.afford`; 34 councils get the phrase and 19 of them score under 5 on growth (Redcar and Cleveland 3.2, prices down 3%). The "Great value despite noise" branch says "and growth" the same way. RAN over all 152 built area pages; **verified**. Fix: test `scores.growth`, or drop the clause. | `index.html:13923-13924` | Correctness | **Fixed 12 Nov**: growth said only from the growth score ("Solid option" too); the Bay Area, with none, says nothing of growth (`tests/panel-findings.mjs`, red on the old function) |
| I-3 | **The planes pages name a district's councils from every postcode, PO boxes included**, though the figures leave them out (rule A, 10 Nov). Wandsworth's consultation pack and `/area/london/wandsworth/` list SW1P ("422 postcodes, up to 44 a day"): all 422 measured postcodes are Westminster's, Wandsworth's 280 are the Nine Elms mail-centre boxes. 43 district pages name a council only through left-out boxes, in their subheading, description and links (EC2R and 20 others name Islington; TW6 names Hounslow; SW3 names Lambeth). RAN read-only over the data; `district_context()` counts the averages file without `large_users()`, **verified**. Fix: count councils from the postcodes each district file holds; then `--write`, area pages, deploy. | `scripts/build_planes_pages.py:334-350` | Data accuracy | **Fixed 12 Nov**: `district_context(skip=large_users())`; SW1P no longer lists Wandsworth; 4 area pages lose a box-only link; 175 planes pages rebuilt (most only their nearby order) |
| I-4 | **The street report drew a neighbour's road reading as "This postcode".** `/v1/environment` answers for the nearest postcode; the report shows that and then labels the neighbour's road figure as this postcode's, though neighbours differ by 20 dB and the full map refuses the case (`roadReadingFrom`, `index.html:12095-12108`). RAN; **verified**. | `js/street_report.mjs:646-650` | Correctness | **Fixed 12 Nov** (uncommitted): no bars; the block says whose figure it is |
| I-5 | **The street report's "Under 1 a day" went out without the overhead rule, the PO-box rule, the CAA check or the adsb.lol ODbL credit** (158,748 postcodes). The rules and credit were tied to `pm.airports.length`. RAN; **verified**. | `js/street_report.mjs:628-637` | Wording rules / licence | **Fixed 12 Nov** (uncommitted) |
| I-6 | **The street report printed "Have your say" over nothing** wherever no airport's pages are verified (every postcode outside London today). RAN for M22 5RG; **verified**. | `js/street_report.mjs:679` | Correctness | **Fixed 12 Nov** (uncommitted) |
| I-7 | **`/reports/` contradicted the report it sells**: "every number comes from a public body's own published data" and "what it does not say: how often aircraft fly", beside a report that now draws planes a day counted from community flight tracking; the free page still said "One page … from public data". READ; **verified**. | `home/reports/index.html:114, 125, 147, 150, 157`; `home/reports/street/index.html:7, 129, 156, 162` | Wording | **Fixed 12 Nov** (uncommitted): wording for Bill to approve |
| I-8 | **`/nhs` reports an Overpass failure as "No GP within 1.5 km".** `query_overpass()` returns `.get('elements', [])`, so a 200 with no `elements` (or Overpass's runtime-error `remark`) becomes `available: true` with three "none nearby" rows: absence rendered as a reading. RAN with the reply stubbed; **verified**. Fix: check the reply's shape and send failures to the existing fallback. | `backend/lambdas/nhs/app.py:236-237` | Correctness | **Fixed 12 Nov in source** (`elements_of()`, tests in `backend/tests/test_error_paths.py`, red on the old code); live after the reviewed SAM deploy |
| I-9 | **`/nhs` sends any point on Earth to Overpass**, a free service other people run. One request for central Paris took 26.8 s and answered 200. At the route's throttle (2 a second) one anonymous loop holds about 52 Lambdas, costs about $19 a day, sends Overpass about 17 times its daily guideline, and with no concurrency reserved can starve `/v1/score`. RAN (one request); **verified** (only a whole-Earth range check at `:359`). Fix: refuse points outside the UK, cut the Overpass wait to about 8 s. | `backend/lambdas/nhs/app.py:359, 382-409`; `backend/template.yaml:313-316` | Security / cost | **Fixed 12 Nov in source**: points outside a UK box get a 400 before Overpass. The 8 s wait was NOT taken: the code's 6 Aug note measured Overpass 504s at a 10 s budget. Reserved concurrency waits on the account limit (Bill's console). Live after the SAM deploy |
| I-10 | **Nothing re-derives the figures in the public sample street report.** Its gates hold the picture's hash to the PDF and some wording, so every data roll leaves its TW9 3PZ figures stale while preflight stays green; it has happened twice (the CAA roll of 1 Nov; PM2.5 8.6 against 8.5 after the 10 Nov air reload) and the next AIRAC cycle and September's planes roll will do it again. READ. Fix: a `--check` that rebuilds the sample's figures from the data and compares. | `scripts/address_noise_report.mjs:16-29, 96`; `scripts/build_report_still.py` | Gate | Open |
| I-11 | **The drift check never hashes `sw.js`, `manifest.webmanifest`, or `home/reports/*.pdf` and `*.webp`**, so a deploy that skips `pwa-deploy` or leaves the regenerated PDF out passes unseen. Four of them hashed by hand match the origin today. READ. | `scripts/check_deploy_drift.sh:47-78` | Deploy gate | Open |
| I-12 | **The Healthcare card says "NOT SOURCED" in nine UK cities** (and "CURATED" in London and Manchester), while all 91 records name the NHS register as their source. READ; **verified** in the registry. | `index.html:11756`; `healthSource` at `8261-8713` | Provenance | **Fixed 12 Nov**: the card reads the record's own `healthcareVintage` (all 91 UK records carry it); New York keeps its line (`tests/panel-findings.mjs`, the card drawn, red with the line broken) |
| I-13 | Outside London, a map click after a profile change shows the old profile's score under the new profile's name. READ. | `index.html:16125` | Correctness | Open |
| I-14 | Nine London area names (Mayfair, Southall, Hendon and six more) point at terminated postcodes and answer "NOT FOUND" (Hendon's went in April 2026). RAN against postcodes.io. | `index.html:6173` | Correctness | Open |
| I-15 | Typing a covered council from another city's view ("Birmingham" from London) answers "NOT FOUND". READ. | `index.html:12978` | Correctness | Open |
| I-16 | After a city switch or closing a result, a profile change brings back the old postcode in the new city, with the new city's stations (about 260 km away for a London postcode). READ. | `index.html:16359` | Correctness | Open |
| I-17 | The first San Francisco ZIP looked up in a session loses its ZIP block about a second later. READ. | `index.html:17006` | Correctness | Open |
| I-18 | On a phone, choosing a profile in Rankings with a result open throws the view back to Search, so the table is drawn over the map. READ; needs one look at 390 wide before the fix. | `index.html:14824, 14301` | Responsive | Open |
| I-19 | In New York the Labels layer is on but its button says "not pressed" (WCAG 4.1.2). READ. | `index.html:15971` | Accessibility | Open |
| I-20 | `/score-demo/` has no live region, so the wait, the score and errors such as a 429 are never spoken (WCAG 4.1.3); its "Try an example" label is attached to no control. READ. | `score-demo/index.html:458, 443` | Accessibility | Open |
| I-21 | **"Heathrow's 2025 movements were 2% below 2019's" sets an annual average against a summer one.** The sentence is the CAA's own (ERCD 2601's summary), but its 1,347.1 is 2019's average SUMMER 24-hour figure (its para 2.15 says so: 1,260.4 + 86.7); 2019's annual figure is 1,312.9 a day (ERCD 2101, Table C6), so 2025 (1,315.0) matches 2019 like for like. The live `/map/` and `/api/`, METHODOLOGY s6 and the Leicester call brief repeat the 2%. Found by the Leicester fact-check (RAN against the CAA's documents); 1,347.1 as the summer figure **verified** in `data/n65/text/ercd-lhr-2025.txt:148, 445`. The like-for-like reading strengthens the point made: 2025's 55 dB contour (142.4 km²) is 19% smaller than 2019's (176.2) on the same traffic. | `index.html:5301, 8144`; `api/index.html:374`; `METHODOLOGY.md:1190, 1205`; `scripts/measure_covid_understatement.py:11` | Data accuracy | **Fixed 12 Nov in source** (Bill's yes): "a year with as many Heathrow flights as 2019" on the map and `/api/`, METHODOLOGY with ERCD 2101's 1,312.9; live with the next web deploy |
| I-22 | **Every `/v1/environment` test stub lacks `provenance`**, so the full map's DEFRA model row is never drawn in a browser test; run with empty provenance, a postcode with no sensor nearby says nothing about air and every test stays green. The live API sends provenance today. RAN. | `tests/stub-live-api.mjs` and the fixtures it answers from | Gate | Open |

## Minor Issues

| # | Issue | File:Line | Category | Status |
|---|-------|-----------|----------|--------|
| M-1 | The report was "two pages" in two places and "one page" in four others. | `home/index.html:1076`, `home/reports/street/index.html:7, 129`, `llms.txt:20` | Wording | **Fixed 12 Nov** (uncommitted) |
| M-2 | `/reports/` said "the planes overhead on an average day": no day is average. | `home/reports/index.html:125` | Wording | **Fixed 12 Nov** (uncommitted) |
| M-3 | A missing WHO road guideline became "0 dB" (`Number(null)`); latent, the API always sends 53. | `js/street_report.mjs:646` | Correctness | **Fixed 12 Nov** (uncommitted) |
| M-4 | A free copy's reference hash leaves out the planes figures, so after a planes roll the check says "matches" while the figures differ. | `js/street_report_page.mjs` | Correctness | Open |
| M-5 | The report's `aria-label` now sits on a footer inside a section, which is no longer a landmark. | `js/street_report.mjs` | Accessibility | Open |
| M-6 | "Nothing under 8 pt" has no check; four chart labels sit within 0.25 pt of the floor. | `scripts/address_noise_report.mjs` | Gate | Open |
| M-7 | 5,722 postcodes have three counted airports, and none has been printed to check the two-page fit. | `js/street_report.mjs` | Test coverage | **Fixed 12 Nov**: N3 1JN (Heathrow, Luton, Stansted) printed in the three-page build, 3 pages, nothing under 8 pt; now on the check list |
| M-8 | An over-long PDF is still written over the previous file: the script exits 1 rather than refusing before it writes. | `scripts/address_noise_report.mjs` | Correctness | **Fixed 12 Nov**: a fourth page removes the new file and leaves the last good one (seen working on TW6 2GA before its fit) |
| M-9 | The search guide's orange border is 2.6:1 against the panel, under WCAG 1.4.11's 3:1. | `index.html` (`.search-box.guide`) | Accessibility | Open |
| M-10 | A line meant to be guarded by the `try` for an older cached module sits outside it. | `index.html:12119` | Correctness | Open |
| M-11 | `/v1/signup` answers 500 for a body that is not a JSON object or has a non-string field (9 bodies tested); `DELETE /favourites` gives 503 for a postcode over 1,024 bytes. Either lets anyone write 5xx lines and trip the 5xx alarm. | `backend/lambdas/signup/app.py:406-418`; `backend/lambdas/favourites/app.py:271-281` | Robustness | Open |
| M-12 | OPERATIONS.md and ROADMAP still say the Lambda concurrency limit is 10; CloudWatch shows a peak of 13 with no throttles on 11 Nov, so the raise has landed (its value cannot be read with `flightmap-dev`). | `OPERATIONS.md`, `ROADMAP.md` | Docs | Open |
| M-13 | `mobile/` reports 3 moderate advisories with `--omit=dev`, only because `@capacitor/cli` (a build tool) sits in `dependencies`. | `mobile/package.json` | Dependencies | Open |
| M-14 | Escape on the Layers popover also closes a phone's open card. | `index.html` | Accessibility | Open |
| M-15 | A late borough-data load can swap a postcode answer for the council's panel (narrow timing; PLAUSIBLE). | `index.html` | Correctness | Open |
| M-16 | Three focus rings use the dark colour, not `--focus`. | `index.html` | Accessibility | Open |
| M-17 | Dead neighbourhood fields carry `|| 3`, and a 0 for "no data". | `index.html` | Dead code | Open |
| M-18 | Typing an Isle of Man or Channel Islands postcode on the front page shows the API's developer message "lat and lon are required and must be numbers."; `/api/` already says it in plain words. | `js/home-engine.mjs:1479-1496` | Wording | Open |
| M-19 | Footers say "All figures from official public data" on pages that show planes figures; a first visit to the front page shows a planes figure with no adsb.lol credit in view until the full example is opened. Fixed on the two report pages; the front page, `/pricing` and the rest remain. | `home/index.html:1249`, `pricing.html:335`, others | Wording / licence | Part fixed |
| M-20 | `/open-data/` still compares DEFRA's contour with the CAA's 2024 figure; everything else moved to 2025 on 1 Nov. | `scripts/build_area_pages.py:1509` | Data vintage | Open |
| M-21 | `/api/` and `/score-demo/` never mention the Bay Area, and `/api/` says "97 boroughs" where the coverage sentence says "97 council areas". | `api/index.html`, `score-demo/index.html` | Wording | Open |
| M-22 | The 11 Nov title and description limits are tested only on the built pages: `/bay-area/`'s title is 99 characters and its description 257; several hand-written pages run past 160. | `tests/test_page_meta.py`; `bay-area/index.html` | SEO gate | Open |
| M-23 | 16 Bay Area pages at the Census's $2M top code each say "35 of 50 … cheapest first", which reads as an order: it is a tie and should say "joint". | `scripts/build_area_pages.py` | Wording | Open |
| M-24 | The `/about/` timeline's last word on the Bay Area is still "shown as facts without a score". | `about/index.html` | Wording | Open |
| M-25 | The drift check's data floor is 41, but the target uploads 42 files. | `scripts/check_deploy_drift.sh:247` | Deploy gate | Open |
| M-26 | The front page's report picture keeps one fixed name and `sw.js` serves it cache-first, so returning visitors keep the old picture after a rebuild. | `home/index.html:1033`; `sw.js:424` | Caching | Open |
| M-27 | The wording gate reads no uploaded JSON, though panels draw sentences from it; two live files (`aircraft-quiet-london.json`, `aircraft-quiet-regions.json`) carry a note saying "DEFRA measured". | `tests/test_public_wording.py:44-72`; `scripts/build_aircraft_quiet_dataset.py:246, 321` | Wording gate | Open |
| M-28 | Four gates list files through git, so a new untracked file escapes them in the run before its commit (shown on today's untracked `tests/street-report.mjs`). | `tests/test_no_user_paths.py:24`, `test_home_links.py`, `test_meta_csp.py`, `test_site_palette.py` | Gate | Open |
| M-29 | `llms.txt` types "January to August 2026" for the planes counts; every other surface reads the period from `data/planes/airports.json`, and no test holds this copy. | `llms.txt:18` | Derive, never copy | Open |
| M-30 | CLAUDE.md says `CRIME_EDITION_LABEL` is held by `tests/test_provenance_periods.py`; the check is in `tests/test_crime_edition.py:36`. | `CLAUDE.md` | Docs | Open |

## Checked and found sound

Key gating on `/v1/score` and batch, input checks, logging and IAM in the backend; `verify_answer()` still discards
unsupported numbers; escaping and URL checks on the client pages; the extension, the service worker, `js/count.mjs`;
no secrets in tracked files; the live security headers; the 9 Nov audit's M-6 and M-8 still hold. The moved air
helpers, rule A (PO boxes) in the figures, `placeFinding()` keeping focus, `startsLikePostcode`, `page_title()`/`fit()`,
the sitemap's noindex refusal, `/api/` without inline script, two-airport ordering (44,422 postcodes, 0 mismatches).
Preflight: 81 `check`, 8 `net_check` and 27 `advise` call sites, every exit code read, every skip printed as incomplete.
Nine of ten "held by a test" claims in CLAUDE.md hold as written; the tenth holds through a different test (M-30), and
the HPI roll's deflator is caught by `tests/borough-score-parity.mjs`, not by `build_hpi_prices.py`.
`npm audit`: root 3 moderate (html-validate, M-9 of 9 Nov), 0 with `--omit=dev`; `mobile/` 5 moderate, 3 with
`--omit=dev` (M-13). No high or critical.

## Not covered

No browser, so no layout, contrast or axe measurement on any page, and the phone layouts were judged from the CSS only.
The larger builders and loaders (borough bands, HPI, crime outside London, the adsb counters, the NSPL and DEFRA
loaders, the Bay Area builders) were not swept line by line for bounding-box or default-value faults. The live routes
that write (signup, favourites, chat) were not exercised. Find areas, most of the approach strip's script, the API
reference and status pages, the prototype, the `/area/` index and the planes index pages were not read.
`index.html` 1-5013 (CSS), 6371-7918 (generated data) and 8330-8834 (the rest of the registry) were searched, not read.

## Summary

- Critical: 0
- Important: 22 (I-4 to I-7 fixed 12 Nov, uncommitted; I-8 and I-9 need a reviewed SAM changeset; I-21 came from the
  Leicester call's fact-check, run beside the audit)
- Minor: 30 (M-1 to M-3 fixed 12 Nov, uncommitted; M-19 part fixed)
