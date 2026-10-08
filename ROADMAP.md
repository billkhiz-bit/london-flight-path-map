# Sky Score Roadmap

> **Living document.** Updated as Sky Score evolves. For Claude session instructions see `CLAUDE.md`. This roadmap is the *what next* across all tracks. (The buildathon plan lives at `archive/BUILDATHON_PLAN_2026.md` since 2026-08-24.)

**Last reviewed:** 2026-10-08 (evening) - **Four more items, in Bill's order**: a sample borough evidence pack for the Mayor's Air Quality Fund (Hounslow, on Bill's Desktop) with drafts per buyer type held; the phone footer is "Privacy · Terms · More" (M-20); stylelint removed (npm audit 7 high -> 0); the API status page routes support to email. Earlier, the afternoon: **The favicon (`0e1cbb4`) and three full-map fixes (`71f28e5`) DEPLOYED and verified from the origin**: every page has an icon; the map's distances are the front page's (TW3 1ES: Heathrow 4.9 km and 0.3 km, was 6.3 and 0.6); the first-run hint clears on any answer; no more "Infinity km". Outreach Phase 1 research and LGM #6 prep are on Bill's Desktop. Earlier the same day: **Batch 3 DEPLOYED and verified from the origin (`fc078db`, master level)**: drift 32 pages / 38 data / 103 area, area pages 102 of 102 against the live API, the live map's Woodhaven 11421 "About 1,200 ft (JFK 13L final approach)", the front page's AIP/FAA credit and the site bar on /privacy all checked live. Next: the favicon (START HERE block below). Previously 2026-10-07 (late): batch 3 was built and Bill stopped mid-preflight. Batch 3, everything on Claude's side: New York parity (the front page draws New York's routes from the Bay Area's derivation, arrivals included; the full map's New York altitude is the FAA's glide path, its ladder deleted); the front page credits the UK AIP (NATS) and carries the FAA's disclaimer (it had neither); website audit M1, M3, M8 and M13 closed (the site bar on six more pages; region names from the API, ending "Nottinghamshire" for four of its eight authorities; plain words for RoFRS, NaPTAN, ODS and "ladder"; "10 is best"; no "not on the map yet"); 3b's engagement event; EXPANSION.md's measured air-quality table (AURN, the GLA's Breathe London API, AQS and NYCCAS usable; PurpleAir not); the Innovate UK AI calls assessed and not pursued (Track 3). Earlier the same evening: **Four more items DEPLOYED and verified live (`4c2c5d2`)**: the full map's plane altitude is the published glide path (A1: TW9 3PZ "About 1,800 ft", was "4,000-6,000 ft"); GoatCounter pinned to `count.v5.js` with its integrity hash on every page; focus rings at 3:1+ (I-7, `--focus: #d35a12`); the responsive audit covers the front page at every width. Earlier the same day: the Bay Area arrivals on the front page (`eace052`), the UK AIP credit in the API's sources plus the M-2 privacy fix (`fddc433`), the Capacitor 7.6.9 fix (`96ff918`, iOS rebuild is Bill's). Before that, the same day: **Website audit batch 1 DEPLOYED and verified from the origin** (`e2396cc`, master level): preflight PASS, drift 31 pages / 36 data / 103 area, area pages 102 of 102 against the live API, new wording spot-checked live. The last session had ended mid-preflight with all of it uncommitted. Reviewing it found **I16**: the 11 API-only area pages omit air quality, road noise and flood rows the Lambda holds (Bill chose the measured figure; fixed the same day, see row 3w). Batch 2 still waits on the legal draft. Previously 2026-10-06 (late) - **A full day: pricing by buyer (councils, platforms, firms on one page), New York and the nearest station on the front page, the free report protected (watermark, checkable reference, QR), header links underline, and a website content audit whose first batch is in preflight.** Before that the same day: **The front door moved and arrivals went live.** `/` is the "ask first" page, the full map is `/map/`, a visitor makes their own aircraft-noise report at `/reports/street/` (on screen free; the PDF is the paid product for firms), report prices are three tier cards, and the Bay Area page and map draw the FAA's coded arrival routes (Palo Alto: SIDBY, 4,000 ft or above). Both deploys verified from the origin. In flight: see "WHERE WE ARE (2026-10-06, evening)" at the top of the task list. Previously 2026-10-02 - **Geovation follow-up call held**: narrow to the flight-path niche, keep freemium, keep going with community groups; the first view confuses (see "Geovation feedback (2026-10-02)", checked against the live site). Previously 2026-10-01 (later) - **Methodology v5.5 DEPLOYED and verified from the origin (master `3d4ae39`): the airport term is runway-shaped** (`AIRPORT_SHAPE_K = 4`, `CORRIDOR_WEIGHT` 0.3 -> 0.5, axes generated from the AIP into both holders). Held-out DEFRA error on the strip 1.431 -> 1.141, beside it 1.226 -> 0.770, every city better and every city reading louder than DEFRA, never quieter; London's published figure 1.32 -> 1.03. **The choice reversed twice in a day**, and the second reversal is the lesson: pooled, k = 6 / w = 0.5 looked best and neutral, but per city it read quieter than DEFRA in five of eight (London is 72% of the strip). `fit_airport_shape.py` now fits under a PER-CITY rule and its `--check` replaced `fit_corridor_weight.py --check`. Borough scores and area pages unchanged bar the version string. Earlier the same day: the measurement became a script (it reproduced the 30 Sep figures, taken with the weight held at 0.45), and sitemap `lastmod` became each file's last change. Previous: 2026-09-30 - **The last ZAP finding is closed and DEPLOYED**: API Gateway's own error responses carry HSTS + nosniff (`GatewayResponses` DEFAULT_4XX/5XX), with the body template PINNED to API Gateway's default, because SAM writes `responseTemplates: {}` when none is given and the 429 types inherit from DEFAULT_4XX. Shipped through a reviewed changeset (API body, deployment and stage only) and verified from the origin: eight unrouted paths carry both headers with unchanged bodies, `demo-key-scope.mjs` 6 of 6. **Geovation data clinic:** altitude measured and rejected (under 1%), but the same run found the airport term is a circle; a runway-shaped term at k = 4 takes DEFRA error 1.44 -> 1.12 on the strip and 1.23 -> 0.72 off it - **v5.5 awaits Bill's go-ahead** (row "Time of day and flight altitude"). Earl's Court Society replied: call Thu 1 Oct 18:00. **Also live (`c95124c`):** the 11 preview area pages (Cardiff, Nottingham, Norwich) linked "Open on the map" to a city the site does not hold, which opened LONDON's map - the Norwich user's defect, from the page built for him; they now say "Not on the map yet", each page's identity is `<main data-city data-borough>`, and `tests/area-pages.mjs` reds on any map link to a city `CITY_DATA` lacks. A member of the public's name and email, and an organiser's, came out of `OUTREACH_LOG.md` and HANDOVER (the repo is public; history still holds them - rewriting it is Bill's call). **Outreach drafts** (Norwich user, CAA to the verified `noise@caa.co.uk`, Geovation) are in `OneDrive/Desktop/outreach-drafts-2026-09-30.txt`. Small, open: `build_area_pages.py --write` re-stamps EVERY sitemap `lastmod` with today's date, including unchanged pages, so this deploy left `sitemap.xml` alone - date only the pages whose content moved. Previous: 2026-09-29 - **Security, air data and community, all DEPLOYED and verified from the origin** except one item. A passive **OWASP ZAP baseline** (site 0 fail, API 0 fail; reports on Bill's Desktop) found three real issues, all fixed and live in `7df6d4e`: Swagger UI 5.17.14 -> 5.33.0 (bundled DOMPurify 3.1.4 had CVEs), HSTS + nosniff on every Lambda response (`backend/tests/test_security_headers.py`), and `method="post"` on the notify form. **~~NOT YET COMMITTED OR DEPLOYED~~ (DEPLOYED 2026-09-30): the same two headers on API Gateway's OWN error responses** (`GatewayResponses` DEFAULT_4XX/5XX in `template.yaml`, with its test, proven red/green) - the ZAP re-scan still flagged 5 because unrouted paths are answered by API Gateway, not a Lambda. Its preflight was killed for LOW MEMORY (Docker Desktop was running); next: close Docker, preflight, commit, reviewed changeset, then `tests/demo-key-scope.mjs` to confirm the 429 bodies are unchanged. Also live (`216fb22`): London borough panels show DEFRA NO2/PM2.5 (they were hidden behind a curated note), the open-data CSV gains `no2_ugm3`/`pm25_ugm3` (blank for the 11 API-preview areas), and "+ VAT" is gone from `api/index.html` and the pilot drafts (**Cubitt33 is not VAT-registered**). TTL on the I17 pending table is live (`28a809b`) and PR #15 is green; the flip waits only on Bill's SPF/DMARC + SES sandbox exit. **Air quality is on DEFRA PCM 2022 while 2024 is published** - roll once to 2025 when DEFRA releases it (~mid-Oct), with the late-Oct crime roll. Community: first community email sent (Earl's Court Society), plan in OUTREACH_TARGETS "Community plan", and `scripts/area_summary.mjs` builds the free area one-pager from the live API. Previous: 2026-09-27 - **Greater Norwich DEPLOYED as an API-only preview** (master `4592c1d`, verified from the origin; 33 of 792 scores moved by 0.1 through the national price band) and the not-covered panel now links scorecards for every API-only borough. **What to do next is the table at the top of the near-term task list.** Previous: 2026-09-26 - **methodology v5.3, BUILT BUT UNCOMMITTED - one preflight gate red (`map fits its box`, London, 1.9% spill from the longer AIP departure lines); see HANDOVER "WHERE TO START (2026-09-26)"**: London's flight-path corridors are derived from the UK AIP (a Reddit reply was right that the hand-drawn Ockham and Bovingdon lines ran straight into east-west runways), and the corridor penalty is FITTED against DEFRA at 0.3 of its old strength - held-out error 2.36 -> 1.43 across eight cities, London 1.879 -> 1.320 as published on `/api/`. Phase 2 (the other twelve UK airports through the same AIP derivation) is the task table below. Previous: 2026-09-25 - a fresh `/audit` (`AUDIT_REPORT_2026-09-25.md`: 0 Critical, 6 Important, 14 Minor), and everything fixable in it DEPLOYED and verified from the origin the same day: `/v1/changes` no longer calls a July figure a change from itself (I-1), the public `/talks/` write-up states both IAM gaps honestly and ships tagged (I-2, I-3), the badge carries a CSP, the phone result card's close button is sticky (M-9, gated by `tests/result-close-reachable.mjs`), and - found while preparing a Reddit image, not by any gate - **the aircraft-noise legend was a palette neither overlay uses and read London 10-15 dB louder than DEFRA** (I-6, fixed, gated by `scripts/check_noise_legend.py`). **First public marketing**: an [OC] chart posted to r/dataisbeautiful (live) and r/london (auto-removed under its self-promotion rule 6) - see OUTREACH_LOG. Still open and Bill's: **I-5** (verified signup loses keys to email link scanners - a precondition before the I17 flip), the **M-9 footer decision** (legal links unreachable while a phone result is open), NYC's legend heading `dB DNL` (unverified - BTS 403s fetches), the ICO fee (GBP 52, Cubitt33 Ltd), and GitHub's 15 Dependabot alerts (10 high; the audit counted 1 at the root). Previous: 2026-09-15 - the open-decisions brief below was READ

> ## START HERE (2026-10-08, evening)
>
> **Evening, in Bill's order** (one preflight over all four; see the commit for deploy status):
> - **(a) MAQF evidence pack, outreach Phase 2, nothing sent.** `area_summary.mjs` made a one-pager for Hounslow's
>   five AQAP focus roads (one postcode ON each road, geocoded via OpenStreetMap + postcodes.io): every point above WHO
>   for NO2 and PM2.5, road noise 68-78 dB Lden, Vicarage Farm Rd 0.1 km from the 27R approach at about 600 ft. Drafts
>   for five buyer types held on the Desktop (`outreach-drafts-phase2-2026-10-08.txt`). The script now names the
>   LOWEST aircraft first and credits the AIP as not OGL. OUTREACH_TARGETS gained the facts (with sources) and lost
>   two over-claims: "everything is OGL" and "each figure checked before release" (air and noise checks are advisory).
>   **MAQF Round 5 closes 5pm Fri 13 Nov 2026**; sending still waits on the gates below.
> - **(b) M-20 closed**: the phone footer is one line, "Privacy · Terms · More" (55 px, was 107 over the map's
>   airport labels); the rest open from an inline `<details>`. Gate: `tests/mobile-legal-links.mjs`, red on the old one.
> - **(c) stylelint removed**: it could not parse `index.html` (since March) and carried all 7 high npm advisories
>   (`braces` <=3.0.3, no patched release). `npm audit` now 0.
> - **(d) The API status page** sends support to support@skyscore.co.uk, not GitHub issues (audit M14, part).
> - **New for Bill:** `robots.txt` blocks `/api/` for GPTBot, ClaudeBot and others while its own comment welcomes
>   AI citation of the API docs - change the rule or the comment (M14). And the `api.skyscore.co.uk` CNAME.
>
> ### Afternoon: everything live, nothing in flight
>
> Deployed today and verified FROM THE ORIGIN (drift 32 pages / 38 data / 103 area, every time):
> - **Batch 3** (`fc078db`): New York parity, the AIP/FAA credit, website audit M1/M3/M8/M13, the engagement event.
> - **The favicon** (`0e1cbb4`): `/favicon.ico`, `/icons/favicon.svg` (simplified mark), `/icons/apple-touch-icon.png`;
>   three links on all 125 pages and both generators; `tests/test_favicons.py`; icons uploaded BY TYPE.
> - **Full-map fixes** (`71f28e5`): the panel's distances come from `js/flight_geometry.mjs` like the front page's
>   (TW3 1ES Heathrow 4.9 km / 0.3 km, was 6.3 / 0.6; TW9 3PZ 10.2 km, was 11.7); the first-run hint clears on any
>   answer (deep link, borough click); a city with no flight path no longer prints "Infinity km". `uk-city-panel.mjs`
>   48 of 48 against the live map, the four new checks proven red on the old one.
>
> **Found today, NOT fixed (Bill's call):** (a) the full map's postcode badge ("MODERATE AIRCRAFT NOISE" at TW9
> 3PZ) comes from its own distance ladder while Quiet Skies 3.2/10 beside it is DEFRA's measurement - a wording /
> classification question, related to but not the same as I-8; (b) the front page rounds distances over 10 km to
> whole km ("10 km") where the map and report print 10.2 km - same measure, different rounding.
>
> **Outreach Phase 1 (research only, 8 Oct)**: on Bill's Desktop, `public-sector-research-2026-10-08.txt` (names
> people, so never in this repo). Organisation-level findings, spot-checked against primary pages: the **Mayor's Air
> Quality Fund Round 5 is OPEN to boroughs, GBP 6m, closing 5pm Fri 13 Nov 2026**; the **DEFRA Air Quality Grant has
> had no round since 2023-24** (whose ~GBP 6m was withheld in 2024), so in London the live money is MAQF; aircraft
> noise cannot be a statutory nuisance (EPA 1990 s.79(6)), and boroughs do not write noise action plans. Outreach
> still waits on the Phase 3 gates (name, ICO fee, legal pages, DKIM, NATS on paid use).
>
> **LGM #6 (Wed 14 Oct 18:00)**: `OneDrive/Desktop/lgm-2026-10-14-demo/` has `run-sheet-2026-10-08.txt` (every
> figure re-read live), `deck-review-2026-10-08.txt` (two suggested rewordings: slide 4 says every check can block a
> release, but five data checks are advisory; slide 9's note says the EA has "no download", unverified) and four
> backups retaken 8 Oct. The deck itself is unchanged.
>
> **Waiting on Bill:** rehearse LGM; the two deck rewordings; (a) and (b) above; example-button labels; privacy
> s2c wording; the name (TMview, domains, attorney, file), the ICO fee, the iOS rebuild for Capacitor 7.6.9, legal
> draft approval, the console checklist, Claude Startups; whether to delete the two merged agent worktrees.
AGAINST THE CODE and corrected in four places (badge cache is scriptable but
the managed policy would 403 API Gateway; repo settings are all CLI; the July
roll hides one decision; **M23 was missing from the list entirely**). Done
the same day: M14's chat 502 and M23's station qualifiers (both red-proven,
committed, **deployed and verified from the origin the same evening**),
Dependabot on, CI actions pinned to SHAs.
Bill is leaning to I17 option A; the policy answer is in item 1. Previous:
2026-09-14 evening - **36 of the 13 Sep audit's 37 Minors
closed or converted to decisions, in five preflighted commits, all deployed and
verified from the origin** (drift 133/133). What is left is DECISIONS, and each
is written up in practical terms under "What each open decision entails" at the
foot of Open decisions: I17 signup verification, the badge edge cache, GoatCounter
on the demo page, three repo settings, CPI real-terms growth, the July HPI roll
(waiting on HMLR, ~16 Sep), and M14's chat-400 remainder. Bill: "will get back
to this." Previous review, 2026-09-13 evening - every Critical and Important from the
11 Sep audit closed and deployed; the demo quota raised to 5,000 and the demo
scoring again; the real-terms growth adjustment COSTED (26 of 99 "rising"
boroughs fall in real terms - see Open decisions); a fresh `/audit` run the
same evening (2 Critical, both fixed and deployed within hours; 24 Important,
37 Minor, in `AUDIT_REPORT_2026-09-13.md`). **Then, the same night, 23 of the
24 Importants were closed and deployed in four tiers - see "Audit backlog,
13 Sep" under Near-term tasks, every tier struck through. What is left for the
NEXT SESSION: (1) the I17 signup decision (Open decisions table - three
options, Bill's call); (2) the July HPI roll once
`Average-prices-2026-07.csv` answers 200 (~16 Sep; the roll is safe as
documented now that I6/I7 are closed - `--check --all`, `--write --all`,
rebuild area pages, backend first); (3) the CPI growth decision, costed;
(4) the 37 Minors, less the few closed with the tiers; (5) the console items.**
Previous review, 2026-09-10 afternoon (**THE PER-POSTCODE ROAD TIER COVERS
ALL ELEVEN CITIES, loaded and verified** - it had been London-only since August, unrecorded
anywhere: M2 4NG served `None` on `/v1/environment` while SW11 served 69.1 dB.
Measured first: 100% of live postcodes surveyed in every English city, and **2.0%
of them are DEFRA zeros** - surveyed, under 40.00 dB - which the loader dropped
with the sentinels, so 11,281 quiet postcodes read "not measured" (audit I3, one
tier down). Now a BOUND, `roadNoiseBelowDb`, *quiet not missing*. Runbook
`scripts/load_road_rasters.sh`, `--live-only`; see `HANDOVER.md` s0a for the
resume check. And the loaders were ~50x slower than they should have been -
25 threads on boto3's default 10-connection pool - fixed in `ddb_write`. With
that fixed, the roll's POSTCODE-level residue closed the same afternoon: the
aircraft and air-quality tables re-sampled at August positions, both client
quiet datasets regenerated and deployed - London 35,352 -> 35,441 measured
postcodes - and the neighbourhood centroids rebuilt. **Every reader of
`nspl.csv` is on August 2026**; `HANDOVER.md` s0 step 7 lists the eight.)
Earlier the same day: **THE AUGUST 2026 NSPL ROLL IS COMPLETE**,
table and derived shares both. The postcode table had held the February 2026
edition since July - the one genuinely stale dataset in the product. Measured
before loading: **+5,494 postcodes, 0 removed**, live 1,807,729 -> **1,810,364**,
72,554 positions refined (median 20.5 m), **81 LAD reassignments touching a
borough we score**. Routine currency, not a re-basing - and the re-derivation
proved it: **240 numeric field moves across both holders, none of the four
scored shares by more than 0.5, six `Environment` components move 0.1, ONE
headline score moves (Merton 6.0 -> 5.9) and ONE band flips** (Dudley road
noise `moderate -> low`, on an unrounded share that crossed 50% under a printed
`50.0` that did not move - a hairline, and METHODOLOGY s7.1 now records that
bands are cut on the unrounded share by design, same as s6's rounding rule).

- **The recorded ~6-hour blocker was dead.** `BatchWriteItem` is granted, so
  the load runs at ~776 rows/s rather than the 129 rows/s per-item fallback -
  about an hour.
- **The NSPL geography columns gained a new year suffix** (`lad25cd` ->
  `lad26cd`) and the file went 36 columns to 35. Four scripts read them; only
  `build_city_neighbourhoods.py` survived it. **`build_borough_bands.py` - the
  script that writes BOTH score holders - would have failed silently**, because
  `.get(name, '')` returns `''` rather than raising. All four resolve by prefix
  now and the bands builder has a zero floor.
- **All three follow-ups landed**: `NSPL_VINTAGE` -> `'2026-08'` after the run,
  `__META__` re-stamped, and the derived shares re-run on 2026-09-10 - **the
  load does not update them**, and until that re-run both score holders
  described February's geography against an August table. The order of
  operations for the next roll is written down in `HANDOVER.md` s0.

Earlier the same day: **METHODOLOGY v5.0: AFFORDABILITY IS NATIONAL
AND LOG-SCALED. Plus WCAG 2.2 AA enforced, applied weights published, and two
stale records corrected.**

- **v5.0 affordability, decision 1 of the four, CLOSED IN SOURCE AND NOT YET
  DEPLOYED.** All 1,619 inverted cross-city pairs are gone; **737 of 792
  composite scores move**, London -1.55 mean, Teesside +1.28. The linear
  p10/p90 this file recommended was **measured and rejected** - it flattened
  four of thirteen cities. `context.priceRankInCity` carries the within-city
  signal. Two defects surfaced doing it: the site pooled 86 boroughs against
  the Lambda's 94, and `check_worked_example.py` had **never compared
  affordability at all**.
- **Applied weights, decision 2, CLOSED.** See below.

**WCAG 2.2 AA IS NOW CLAIMED AND ENFORCED, AND
THE 2026-09-08 WAVE IS DEPLOYED THOUGH THIS FILE SAID IT WAS NOT.**

- **The WCAG 2.2 decision below is CLOSED.** `wcag22aa` is in `WCAG_TAGS`, so
  2.2 blocks preflight. The entire backlog - 16 `target-size` nodes on the
  vendored Swagger UI page - is fixed, **proven red** before and green after
  across 134 page-states. It turned out to be a **nested-interactive** defect,
  not a small-control one: the deep-link anchor sits *inside* the expand
  button, so raising only the anchors would have pushed the button further out
  of conformance. Changed no published number. The advisory tally that sized
  it is deleted with its machinery.
- **Two stale records corrected by measurement, not by reading.** This header
  said the 09-08 wave was *"Source only - not yet deployed"* and `HANDOVER.md`'s
  top banner said the deploy was **BLOCKED**; the origin serves source
  byte-for-byte (133 of 133 surfaces) and `check_aws_permissions.py` reports
  **18 granted, 0 denied**. Third and fourth phantoms in eight days.)

**Previously reviewed:** 2026-09-08 (**TWO AUDIT-MINOR a11y DEFECTS CLOSED, AND A
PHANTOM TO-DO RETIRED.** ~~Source only - not yet deployed.~~ **DEPLOYED - the
origin was asked on 2026-09-09 and disagreed with this line.** Live
`index.html` is byte-identical to source (sha256 `69245f00f48d085b...`), it
serves `Cache-Control: no-cache`, and `#country-selector` reads
`role="group"` on the live site; `check_deploy_drift.sh` reports **133 of 133
surfaces plus five origin headers**. **The stale record survived exactly one
day**, in the file whose own commit (`2848cab`) wrote *"when a wave closes an
item, delete it from the open list in the commit that closes it"* - the
deploy-status half of the same sentence was left behind. `#country-selector`
stopped claiming to be a `role="tablist"` (there was no panel any tab could
name: `switchCountry()` swaps the whole application), and the locator's ten
markers left the tab order, where they had been stops **14-23 of 51** at
**5.2 CSS px**, 6.4 px apart - WCAG 2.2 2.5.8 fails by size AND by the spacing
exception, and no enlargement can fix it inside a 112 px silhouette. **Both
fixes REMOVE a claim the code could not keep**, which is the inverse of what
each finding implied; see `memory/project-a11y-selector-and-locator-2026-09-08.md`.
Two new gates, both proven red. **`METHODOLOGY` s6 was listed as open in TWO
documents while its blocking gate was green** - `HANDOVER.md` contradicted
itself forty lines apart. Corrected in both, each saying it was wrong.
**One new decision below: WCAG 2.2 or 2.1?**)

**Previously reviewed:** 2026-09-07 (**A FULL AUDIT RAN AND ITS FINDINGS ARE CLOSED
AND DEPLOYED.** Three commits - `b69406a`, `9f8b57b`, `05bca67`. **8 criticals
and 11 importants**, plus the whole second tier: everything the audit found
that did not need a decision. Preflight went 39 -> **43 blocking stages**, all
green; deploy drift **133 of 133**. The consumer site had been serving a
mobile homepage with **ONE visible link** for ten days - /privacy and /terms
unreachable from every phone - and the SCORED transport share was counting
retired stations (City of Nottingham 8.3 -> 8.0). Full list in
`AUDIT_REPORT.md`; the lessons in `memory/project-audit-2026-09-07.md`.

**TWO THINGS NEED A DECISION AND NOTHING ELSE DOES:** the IAM
privilege-escalation path (`OPERATIONS.md` s3.8 - it needs a console session
AND a real deploy to verify, and an untested IAM edit is what caused the 3 Sep
outage), and the four numeric decisions below, which are unchanged.

~~the `healthcareWithin1kmPct` field name~~ **RENAMED 2026-09-11 to
`healthcareWithin500mPct`.** It was never a contract change - measured, the key
lived in `data/borough-extra.json` alone and no endpoint, spec or page emitted
or read it. "A deployed asset" was mistaken for "a published contract" for four
days.

Previous review 2026-09-04: (**NOTHING IS BLOCKED. The wave is committed,
pushed and DEPLOYED.** `FlightMapDeployPolicy` had been REPLACED by the
Observability statements rather than extended; it was restored from
`backend/iam-policy.json` and `check_aws_permissions.py` reports **18
granted, 0 denied**. `web-deploy-all` then ran clean - **133 of 133 surfaces
match the live origin**, 8 invalidations Completed. What remains is
DECISIONS, not blockers: affordability cohort scaling, the un-renormalised
weights, the expired 0.60 threshold, and flood-gate caching. Read
`HANDOVER.md` §0,
which carries the paste-ready policy and the verification order.)

**Previously reviewed:** 2026-09-01, later the same day (the four published-number
corrections - all now deployed and verified, see `HANDOVER.md` §0z.)

**All four of the items this file listed as "STILL OPEN AND NEEDING A DEPLOY
WINDOW" are now fixed in source, except the last:**

- **The aircraft near-field DISC (C1) is gone.** It tests the borough against
  the >=55 dB cells in that airport's own DEFRA GeoTIFF now. Rushcliffe scores
  **balanced 3.4 / quietlife 4.0** - the exact pair the audit predicted by hand.
- **Category B (C2) is filtered out of the neighbourhood medians.** TS26
  Hartlepool **125k -> 175k**, matching the audit's hand figure; 485 published
  rows became 481, the four drops being districts that fell below the 30-sale
  floor once repossessions and buy-to-lets stopped propping them up.
- **F38's retired postcodes are gone**: 915,867 excluded, 578,940 live remain.
- **N1 7SX is still undiagnosed** and still must not be fixed from the obvious
  explanation, which the report already disproves.

**811 borough fields moved across both holders**, so the 99 area pages must be
rebuilt before any gate run - they bake their scores.

Also closed the same day: I2, I3, I18, I28, I29, I31, I33, I34, D5, D7 and the
`document.title` half of D8 - plus **44 contrast failures beyond the two the
audit found**, surfaced by a new gate that measures contrast itself because axe
returns `incomplete` for 66 nodes in this panel and a gate reading `violations`
counts those as passes.

**Two of the audit's own findings turned out INVERTED** and are corrected in
`AUDIT_REPORT.md` §4a: the borough panel HAS been scanned since 24 August (the
scan opens the wrong panel), and the panel DOES name the borough on desktop
(what never changed was `document.title`).

**Previously reviewed:** 2026-09-01 (**D3 LANDED; the parked "one CSS declaration"
was the wrong element.** See the LANDED note below and `AUDIT_REPORT.md` §D3.
Source-only, live untouched.)

**Previously reviewed:** 2026-08-31, later the same day (**FIVE FIX PASSES AFTER THE
AUDIT, ALL SOURCE-ONLY - LIVE IS UNTOUCHED.** 14 gates that could not fail are
closed, plus five absence-as-measurement defects, two false provenance claims
and three live UX defects. Every fix proven red against a constructed defect
first; where a proof touched a tracked file the restore was sha256-verified.

*The three worst gates.* `check_flood_georef` passed on a mosaic with **every
flood polygon erased** (proven by zeroing London's 1,215,784 medium-or-high
pixels) and silently skipped **10 of 11 cities**. `build_borough_bands --check`
read missing data as agreement, on the ONLY source-crossing gate for road noise,
air quality, transport and healthcare. `map-fit` **never measured New York at any
viewport** - it enumerated the active country's chips only, and NYC is the one
city with a different projection origin AND boundary source.

*Three live UX defects.* The result-close `x` was **20% hit-testable at every
width <=900px** with its centre resolving to the search card; Escape did nothing
either. **13 controls stayed in the tab order behind the full-screen mobile
panel.** And **6 of 10 city chips could not be reached with a mouse** at 901px,
with Greater Manchester still off-strip at 1366x768 - no scrollbar exists, a
vertical wheel does nothing, there is no drag handler.

*Two false provenance claims fixed.* `sourceBreakdown.live` credited DfE for 7 of
Leicester's 8 boroughs while the same response said 3/4; and the postcode LRU
returned above the attribution call, so only the FIRST request for a postcode
credited ONS and every later one credited postcodes.io, uncalled.

*Three fixes were made twice and the first attempt was wrong each time,* which is
the part worth carrying: keying the ONS cache on EDITION forces a re-download and
the ONS URL 404s today; `renderBoroughs` comparing raw instead of canonical names
was a real bug but NOT the cause of the mobile deep-link behaviour; and inerting
`#map-container` removed the document's only `<main>`, caught by the a11y gate
within one run.

**LANDED 2026-09-01: `wip/d3-landscape` is merged and `responsive.mjs` is 71 of
71.** The parked note said one CSS declaration was left - make the sticky legend
toggle opaque and raise it above its own scrolling rows. **That declaration was
already committed on the branch and the gate still reported 1 of 71**, so the
recorded diagnosis was wrong rather than unfinished. The coverer was
`div.search-box`, the full-width sticky search card at y 54-138: the flat 160px
floor asked for 42px more than a 390px-tall viewport has, and a bottom-anchored
panel takes that difference from whatever is above it. **The audit output could
not have said so** - it prints tag and id only, and `search-box` has no id, so
it read `covered by div`.

Fixed by capping at the band that is actually clear
(`calc(100dvh - 126px - 146px)` = 118px at 844x390), which also **deleted** the
`min-height: 380px` boundary and the harness carve-out mirroring it - that
carve-out had been accepting a **26px legend of 427px content** at 568x320.
Proven red three ways. A brace-move that had silently carried `.map-controls`
into the wrong media block was found and reverted in the same pass.

**[SUPERSEDED 2026-09-01 - three of these four are fixed in source; see the top
of this file.] STILL OPEN AND NEEDING A DEPLOY WINDOW:** the aircraft near-field **disc**
(Rushcliffe publishes `Quiet skies 10.0/10` over 10.43 km2 at >=55 dB, should be
3.4), the neighbourhood medians including HM Land Registry **Category B** (412 of
485 prices wrong, Hartlepool by 40%), **F38**'s 904,453 retired postcodes, and
the N1 7SX site/API divergence. All four change published numbers, and
`area pages match the live API` is blocking, so none can be committed green
without deploying.)

**Previously reviewed:** 2026-08-31 (**THE GATE CLUSTER IS CLOSED, AND A FULL AUDIT
FOUND TWO WRONG NUMBERS WE PUBLISH TODAY.** Two pieces of work.

*First, the "gates that cannot fail" cluster from the 29 Aug audit* - F14, F15,
F31, F34, F35, F43 closed and F33 partial, every one proven able to go red
before it was accepted. **F34 was worse than recorded**: `FAIL_MODERATE` was not
merely filtered out by impact, axe never RAN those four rules, because all four
are tagged `best-practice` only while the builder asked for WCAG tags alone -
dead code from the day it was written, proven at the taxonomy level so it could
never have fired on ANY page. It was hiding missing `<main>` landmarks on
**privacy.html and terms.html, the two legal pages, and all 100 pages under
`area/`** - which were in no accessibility or responsive gate at all. The a11y
scan now covers 109 pages, the list DERIVED from the filesystem, with the
single-viewport exemption **asserted** (it reads the generator and fails if a
width breakpoint appears) rather than left in a comment. `native-sim-render` and
`live-mobile-verify` were in **no runner at all** - the 3rd and 4th orphaned
gates found here after `failure-path` on 27 Aug - and two of the three contexts
inside the first asserted **nothing**, so the App Store layout could break in any
way and it still exited 0. **On 1 Sep a 5th, 6th and 7th were wired the day they
were written** (`panel-contrast`, `measure_aircraft_footprint --verify`,
`build_city_neighbourhoods --check`), and running them before wiring is what
found the rest of that day's work: the contrast gate reds intermittently on a
FIXED 1200 ms settle while the area panel it opens resolves a district through
`api.postcodes.io` (measured warm at 113-147 ms), so a stage documented as
needing no network needed one for half of what it measured. It polls for the
state now and is TWO stages, `check` plus `net_check`, rather than carrying an
in-gate skip - "nothing wrong here" must never be how a gate says "I could not
look". `check_deploy_drift` covered **3 of the 20** assets
whose atomic `cache.addAll()` decides whether the PWA installs; it now derives
the set from `sw.js` and proves reachability (live: **20 of 20 present**).
**Two lessons cost more than the fixes.** F43's first red-proof PASSED and the
HARNESS was at fault - MSYS rewrote the `/fonts/...` argument, this repo's own
documented Git Bash gotcha in a new place; *a harness that disagrees with the
real thing is evidence about the harness first*. And a collapsed `\b` in a Bash
heredoc became a literal `\x08`, so a guard written that minute to close F34
could never match - **a check that cannot fail, created while removing checks
that cannot fail**.

*Second, a full seven-finder audit* - report in `AUDIT_REPORT.md`, previous
archived as `AUDIT_REPORT_2026-08-29.md`. 6 critical / ~34 important. **Two
findings change numbers we publish right now.** The aircraft near-field floor is
a **DISC** compared against a runway-shaped contour, so Rushcliffe publishes
`Quiet skies 10.0/10` over **10.43 km² at ≥55 dB, max 65.6 dB** - its balanced
score should be 3.4, not 5.0 - while Solihull at a comparable 9.21 km² is
published `moderate-high`, so it is internally inconsistent rather than a
threshold. And the neighbourhood medians include HM Land Registry **Category B**
transactions (repossessions, non-private transfers, "Other" property types),
which HMLR's own statistics and the UK HPI exclude - **412 of 485 published
prices are wrong**, TS26 Hartlepool by 40%, swinging its score 7.84 -> 5.88,
while the borough `avgPrice` beside it is Category-A via the HPI gate. **The
same product publishes two price bases.** Also live: the 99 area pages credit
ONS, DEFRA, EA and NaPTAN on New York's pages while the same page's derived
sources paragraph says OGL does not apply; a `/transport` 5xx renders as a clean
network; and a slow `/nhs` or `/transport` leaves "Loading from TfL API..." up
permanently, measured at 2 of 16 live samples past the 8s deadline. **Nine
findings were re-verified by hand** and the documentation half was FIXED in the
same pass - METHODOLOGY §5 published a five-component score under a FOUR-term
formula (the reproduction procedure a B2B audit runs), §7.1's road band rule
reproduced 11 of 86 published bands and now reproduces 86 of 86, LICENSING
carried the v3.9 env weights and had no row for DEFRA road Lden at all, and CI's
`test-backend` had been RED on every push since F30 "fixed" it - 254 tests pass
locally, 8 fail under CI's dependency set. **Nothing from the audit's critical
list is fixed yet; F38 from 29 Aug remains the largest open item.**)

**Previously reviewed:** 2026-08-30 (**THE FLOOD DATA IS FIXED, AND THE GATE THAT
SHOULD HAVE CAUGHT IT NOW EXISTS.** Audit F24/F39, the worst finding of the 29
Aug audit, is closed. `fetch_ea_flood_risk.py` clipped edge tiles to the city
bbox but requested every one at 2000x2000 px whatever ground it covered, then
mosaicked at a uniform 10 m/px - stretching clipped tiles up to **5x**. **London
was the worst city, not a footnote** (6 of 12 tiles clipped, 5.00x); only
Nottingham's bbox is an exact multiple of the 20 km tile. `tile_px()` requests
each tile at its real extent, verified by simulation before any fetch: all 11
cities tile with **zero holes and zero overlaps**. **The cache key had to change
too** - tiles were named by origin alone and `fetch_tile` skips on existence, so
the stale renders would have been served forever. **Two more defects surfaced in
the same file, both absence-as-measurement**: Bristol's edge tile was cached
ALL-ZERO from before the blank-render guard existed (2000x2000 of "surveyed, no
risk" over 220 km², exactly what that guard's comment predicted would outlive
the outage), and the mosaic initialised to `np.zeros` where **0 is a real
reading** - it is 255/Unavailable now, which became load-bearing the moment a
partial mosaic was legal. **A city is no longer abandoned for one bad tile**:
Bristol and Teesside are each held by a near-all-sea tile the service renders
blank at 10, 5.5 and 5 m/px (measured, not assumed); Bristol's lies outside all
four boroughs, Teesside's clips one corner of Redcar. Effect: **37 of 81
boroughs moved, 13 changed band, none lost** - Sefton 31.39 -> **0.27**
`high -> low` (the audit predicted 0.28 by hand, from a separate fetch), South
Tyneside 10.94 -> **0.11**, Doncaster 24.38 -> **6.39** - and **Teesside gained
flood for the first time**, taking coverage from 81 to **86 of 91**. **The new
gate is the point.** `build_borough_bands.py --check` re-derives from the same
mosaic, so the two things it compares are the file and itself; it reported
agreement throughout. `scripts/check_flood_georef.py` asks the **EA's own
GetFeatureInfo** what it publishes at a BNG coordinate, asserts MEDIUM-OR-HIGH -
the scored quantity - in **both directions**, and is blocking as a `net_check`.
**Its first version passed the known-bad mosaic 9 of 9**, which is the lesson
worth keeping: measured against the pre-fix London file the **six interior tile
blocks were byte-identical** and only the top row and right column had moved, so
uniform sampling could not fire. `spread_samples()` draws one sample per grid
cell, **periphery first**, because a tiling error accumulates at the edges by
construction. Re-proven red at 33-50%. It also gained a **MIN_COMPARED floor** -
throttling silently shrank one class to 3 of 6 reached, and a class that reached
the service twice has not been tested. **Sampling was the whole gate; the network
call was the easy half.**)

**Previously reviewed:** 2026-08-29, later the same day (**FULL AUDIT: 45 FINDINGS,
AND THE FLOOD DATA IS WRONG.** Ten-agent survey plus adversarial verification -
report in `AUDIT_REPORT.md`, previous archived as `AUDIT_REPORT_2026-08-21.md`.
9 critical / 21 important / 15 minor. **The worst is a mis-georeferenced EA
flood mosaic affecting 10 of 11 cities**: `fetch_ea_flood_risk.py` clips edge
tiles to the bbox but always requests 2000x2000 px, then mosaics at a uniform
10 m/px, stretching real flood polygons ~2x. Only Nottingham's bbox is an exact
tile multiple - I checked every city by hand. Sefton publishes 31.39% against a
corrected 0.28%. **Flood has SCORED since v3.9 and banded the map since 11 Aug**,
so live scores, the map and the 99 baked area pages are all affected, and
`build_borough_bands.py --check` cannot see it because it samples the same
mosaic - the two things it compares are the file and itself. Also critical: **CI
has run neither test suite since 24 July** (both test jobs `needs:` lint jobs
that fail on formatting, so they SKIP rather than fail); `envCaveat()` prints
**"undefined only here"** on every UK borough panel, a regression from the v4.0
wave hours earlier; London's aircraft raster is declared painted from an href
attribute and the gate reads the same attribute; borough bands are weighted by
**retired postcodes**, 39.2% of the NSPL sample. **Two process lessons.** The
audit skill's spend-limit gotcha FIRED: verification died at 13 of 48 agents on
the session limit, and survived only because the finders were checkpointed to
disk first - always run finders and verifiers as SEPARATE workflows, because
verification runs last and is what dies. And **verifiers downgraded 8 of the
first 13 findings** while refuting none: a finder's `critical` is a hypothesis,
so re-measure before writing any fix. NOTHING FROM THIS AUDIT IS FIXED YET.)

**Previously reviewed:** 2026-08-29 (**THE LAST DISPLAY-ONLY INPUT, AND A CONSTRAINT
THAT WAS NEVER ONE.** Methodology **v4.0**: road noise becomes the third scored
`environment` input, at air quality 0.45 / road noise 0.35 / flood 0.20. Persona
weights are untouched - this re-composes the component, not the top-level split.
Road noise had been derived for every covered city since 2026-08-11, drawn as a
map layer and reported by `/v1/environment`, and **nothing scored it**; it was
the last input in that state, in a component whose other two were wired in three
days earlier. **The measured-but-display-only category is now empty.** *The
obvious continuous field was the wrong one*: `roadNoiseLdenMedian` looks the
plottable one but carries **41 distinct values across 73 boroughs over an IQR of
1.7 dB** against the share's 69 over 13.4 points - a borough median of a 10 m
raster averages the quiet streets into the arterials - and ramping it 53->63 dB
clamps **19 of 73 to a perfect 10**. They correlate at 0.931: same signal, worse
resolution. This is the v3.9 band lesson one level down, and **"continuous" was
never the criterion - discrimination was.** *The Leicester/Teesside gap was an
unrun script*: `CLAUDE.md`, `METHODOLOGY.md` and audit **I6** all recorded "0/8
and 0/5 carry neither" as a property of the DATA, when both fetchers are
per-city against **England-wide** coverages, both cities are in England, and
**neither was ever in `NO_ROAD_COVERAGE` or `NO_FLOOD_COVERAGE`**. The rasters
had simply never been fetched for the two cities added on 2026-08-11. Three of
four landed; Teesside's flood is held by ONE near-all-sea tile that renders
blank, which the audit-C11 guard rightly refuses to cache - **the guard is right
and was left alone**. *A measurement recorded without its cause reads as a
constraint*, which is a new variant of the recorded-findings failure and its
seventh instance. *The floor rose from 1 input to 2*, on a measurement: adding
road lowers every borough that HAS it and leaves the rest standing still, so at
a floor of 1 the 13 missing-data boroughs would have gone from median rank 41 to
**9 of 86**, Teesside taking the top four on one input of three.
**`env_single_input()` could not be the mitigation - it is published as
`environmentSingleInput` and read by NOTHING**, the only other reference being a
test asserting it is `false`; third instance of the `lineStatusAvailable` shape
in three days. It is now literal to its name, having previously fired for 2-of-3.
Effect: median environment **8.00 -> 6.65**, mean -1.16, worst -2.10
(Darlington), best **+0.50** (Sefton), 81 fell / 4 rose / 1 unchanged; the
ranking artefact is **gone** - top ten all fully measured, Teesside now 12, 21,
35, 47, 55. Coverage 85 `measured` / 5 `partial` / 9 `unavailable`. The three
ramps and the floor gained their **first direct unit tests** - v3.9 shipped six
env functions with none between them. **COMMITTED (`34e1a93`), PUSHED AND DEPLOYED
THE SAME DAY.** Backend first via SAM, because the 99 area pages bake their
scores and `area-page-freshness` cannot go green until the Lambda serves v4.0 -
the same ordering the 28 Aug P8 roll had to respect, and the one gate that
inverts "preflight, then commit". Verified from the ORIGIN rather than a deploy
exit code: `/v1/regions` reports `methodologyVersion: 4.0`, drift **0 of 16**,
`index.html` sha256 matches source, **99 of 99 area pages match the live API**,
and the three coverage tiers were spot-checked on the deployed API - Cardiff
`unavailable`, Middlesbrough `partial`, Camden `measured`. **Full preflight with
NOTHING skipped: all 32 stages.** Weights confirmed by Bill at 0.45/0.35/0.20.)


**Previously reviewed:** 2026-08-27 (**A FIELD ONLY ITS PRODUCER READ, AND A GATE
NOTHING RAN.** `/transport` has published `lineStatusAvailable` since the 24 Aug
wave so a caller can tell a TfL outage from a quiet network - and **no surface
read it**, so a 403 on the Status route rendered as NO SECTION AT ALL: stations
listed, silence where the disruption list goes, which is precisely what a clean
network looks like. The producing comment is where it went wrong - *"consumers
can upgrade to read the flag; none is required to"* made the second half
optional, so it never happened and the field became documentation of a bug.
**A field only its producer reads is not a fix**; close such an audit item on
the CONSUMER, never the producer. The panel now names TfL and **denies the
good-service reading explicitly** rather than merely withholding it, because
silence was already being read as "no disruptions". Closes the consumer half of
audit **C3**. **`tests/failure-path.mjs` - the file dedicated to "the fallback
shipped untested" - was itself in NO runner**: absent from `preflight.sh`,
`package.json` and the Makefile. Now blocking, pointed at SOURCE for the same
reason `responsive` and `a11y` are. Three things were living in that gap: it had
been **dying on Node 24 at check 10 of 19** (a route aborted after `unroute`;
sibling of the undici crash the day before, and proof that audit was scoped to
one MECHANISM rather than the class); its NYC check had spent **sixteen days
clicking a selector deleted by the two-tier switcher**, with a bare `catch`
reporting London's 33 boroughs as though the switch had run - **a missing
control rendered as a measurement of broken behaviour**, when offline NYC was
fine all along; and the new stub was **answered by the live API** because its
glob matched nothing and its fixture was realistic enough to hide that. **DEPLOYED
and verified from the origin** - `deployed == source` 16 of 16, and the guard
that was red against live is now 19/19 there. **Then two more, same day.** The
**fifth inline copy of the noise-row range check** is folded into
`_plausible_value` (I had reported this closed earlier in the day, having
misread the consolidation; `_plausible_from_row` genuinely was one holder for
the four ROW-based fields, while `_lookup_lden_raster` kept its own copy -
**a holder that names its callers can still be missing one; count the copies,
not the callers**). Red-proven: neutering it fails 14 tests across BOTH tiers.
And **Progress 8's "terminal vintage" claim was wrong by exactly one year** -
P8 needs a KS2 baseline, the cancelled sittings were 2020 and 2021, so the
cohorts without one are KS4 2024/25 and 2025/26, **not 2023/24**, which has
been published since 2025-02-27 and carries P8 as a headline measure (verified
against DfE's release pages, not inferred). **The roll is costed and
deliberately NOT taken**: 72 of 79 boroughs would move, none by more than
±0.20, mean +0.008, 33 up against 39 down, none dropping out - currency rather
than a re-basing. It changes published scores and needs the 99 area pages
regenerated, so it is Bill's call; the unknowns are gone. DfE renamed the
`gender` column to `sex` and the loader now accepts both. **The stale claim had
also outlived its own correction in two places** - the schools memory's
frontmatter description and the MEMORY.md index line both still asserted
terminality three days after the body was fixed.)

**Previously reviewed:** 2026-08-26 (**METHODOLOGY v3.9 SHIPPED: air quality and flood
now SCORE.** Two datasets that had been derived, verified and drawn since
2026-08-11 had never entered a score - they sat in `plannedComponents`, so the
API was advertising as forthcoming two things it already held. They are now the
`environment` component, air quality 0.65 / flood 0.35, at 0.14 of most personas
and **0.18 for `family` and `laterlife`** - the only persona weights in the
product anchored on an external HEALTH source (WHO/COMEAP sensitivity groups:
children, older adults) rather than buyer-priority research. **Scores the
CONTINUOUS fields, never the three-band map summaries**: 68.1% of boroughs share
the modal air band, so the bands would have put two-thirds of the country on one
number. Both ramps anchor on published thresholds (WHO 2021 guideline -> the UK
legal limit for NO2; 0% -> the EA 10% Medium-or-High cut), never the cohort.
**94 of 99 boroughs carry it, 77 fully measured; New York is the only city with
neither.** Cardiff and Nottingham were derived straight into the Lambda with no
`borough-extra` entry - correct, not a shortcut, since they are backend-only and
giving them one would trip `test_backend_only_cities_are_declared_not_discovered`
and force them onto the site. **The 14-day integrator notice did NOT block the
deploy**: the signups table holds two rows and both are Bill's own, so there was
no third-party integrator to notify - re-check that before the next material
change rather than inheriting it. **Nottingham may now be able to leave
`BACKEND_ONLY_CITIES`** - it sits there on judgement, not impossibility, and a
fully-measured environment component is a real second leg. One-way door.
**Also shipped:** the tabbed mobile layout behind `?tabbed=1`, live and default
OFF - map 34.6% -> 78.7% at 375px, controls 18 -> 14; the native-only gate was a
hedge against a design that "never shipped to either store", and iOS 1.0.21
carrying it went live on 1 June, so that condition expired three months ago.
**Two gates found broken along the way:** `responsive, source` was reporting FAIL
having evaluated ZERO pages (undrained `fetch` body killing Node 24's undici),
and `write_lambda` silently skipped Barking and Dagenham on a borough-name alias
- caught only because 159 was a checkable number and it reported 157.)

Previous review 2026-08-24 latest (**THE MAP DID NOT FIT ANY PHONE, AND THE ANSWER SCREEN RANSOMED ITS OWN ANSWER.** A 33-agent review with adversarial verification (112 findings, 23 of 24 verifications CONFIRMED, 1 refuted) followed by a fix wave, all deployed same day. The projection was fitted to the desktop box and pushed through `w < 600 ? scale * 0.625` written out three times: **41% of London drew off-screen at 320x568 in every city, landscape clipped 28% in the other axis, 53 of 90 city/viewport combinations failing with every gate green** - a borough is not a control, so `responsive.mjs`'s four questions all passed. Now a ratio against the fitted box, city-independent, desktop provably unchanged, guarded by blocking `tests/map-fit.mjs` (9 viewports incl. landscape, red-proven both ways - it caught my own first two fix attempts). **The consumer email-capture form had NEVER sent a request** (`trackEvent` scoped inside an IIFE, ESLint's no-undef said so throughout), **blocked site data blanked the whole app** (unguarded `localStorage.getItem` in `init()`, 0 -> 142 map paths), the mobile legend's disclosure was 1.20:1 dark-on-dark, landscape had 0/6 layer toggles reachable, the badge embed was CSP-blocked since it shipped, and the SW pinned `borough-extra.json` forever past its load-bearing no-cache header (Cache Storage does not read Cache-Control; the 2026-08-03 incident fix closed only the HTTP-cache half). **Wave 2, the answer screen**: the verdict sat at y=1001 of an 844px viewport under 602px of preamble - the score section now leads; focusing search opens the sheet so autocomplete went 2/10 -> 10/10 visible; the pill handle drags (ghost-click suppressed, proven by event trace); install prompt yields the peek slot; type floor raised at <=900; popover dismissal no longer selects a borough; safe-area insets reach the WEB sheet. **Wave 3**: 573 KB aircraft-quiet now fetched on search intent not boot (which also closed a boot race where an early search silently scored from geometry), flight-dot animation pauses when hidden/off/reduced-motion (was ~31% of a throttled core, forever), the London PNG head-preload dropped. **Cross-city postcode search switches city** (M1 1AE while London displayed analysed against Heathrow - frontend twin of the backend's 2026-08-12 derive_city fix), `matchBorough` is exact-first (North West Leicestershire resolved to Leicester), the 99 area pages' `?city=` CTA finally has a reader (sequenced after init, or London's render lands on top - measured before sequencing), and `check_score_sanity` gained the NYC probe - the one city whose pipeline shares nothing with the others. **The metric-card "collapsed" finding was OVERSTATED and is recorded as such**: the tap toggle works; inline onclick is invisible to ESLint, not to the browser.) Previous review 2026-08-23 latest (**PHONES HAD BEEN LANDING ON 12% MAP, AND THE NOTE EXPLAINING WHY HAD THE HISTORY BACKWARDS.** The bottom sheet auto-opened over the map below 640px. That was the tail of a half-finished fix: **Apple rejected build 19 under Guideline 4.0 on 2026-05-18 BECAUSE auto-opening hid the map** on an iPad Air, and the same-day fix moved the threshold from `<=900` to `<=640` - giving iPad portrait its map back and leaving phones with exactly the behaviour the reviewer objected to. The line was drawn where the REJECTION stopped, not where the reasoning did, because Apple only tested an iPad. `CLAUDE.md` then recorded the survivor as "deliberate ... carries an Apple Guideline 4.0 rejection scar", which reads as though Apple had REQUIRED it. Measured: 12% of the viewport was map at 320, 375, 390 and 414, against iPad portrait's 71%, with the city chips and the legend both below the fold at boot. Now **61-75%**, and nothing is lost - the peek height is 220px precisely so the search box is reachable without tapping the handle, and `revealSheetIfMobile()` still opens the sheet when a result lands. **Three collisions were invisible while a panel covered everything**: the first-run hint over the title/country tabs/zoom at every phone size; the site footer over the LABELS toggle and the legend at desktop widths (all three are bottom-anchored in `#map-container` at `z-index: 10`, and the footer is 34-72px tall depending on how its links wrap, so it had ALWAYS run through them); and a legend cap that fitted the viewport but not the navigation. **`--footer-inset` is measured at runtime**, because a constant is right at one width and wrong at every other. **The audit that should have caught all of it only ever asked questions about POSITION** - is the page too wide, is a control past the horizontal edge. It now also asks whether a control has something painted on top of it (`elementFromPoint`), whether anything is clipped above the fold, and it audits the consumer app a SECOND time with the legend open - necessary because the first two judge the landing state, and on a phone the legend ships collapsed, so **removing the legend cap left the audit reporting all 45 combinations clean**. Each of the three found a live defect on its first run. `city-switch.mjs` runs at two viewports now, phone first; it had been 1440-only since the day it was written to catch six cities that threw on selection. **Earlier the same day**: 41 of 99 legend band rows described a band not on their map, the `excellent` air band was recorded BACKWARDS in two docs (the painter had four colours against the legend's three, so the fix was a swatch to ADD), the extension's `LONDON_BOUNDS` was deleted after live-probing showed it wrong in both directions, d3 moved out of `<head>` for **FCP 3592 -> 1124 ms**, and a CRITICAL WCAG `select-name` on `api-docs.html` that presented as flake turned out to be a scan racing its own spec fetch - that page was effectively unaudited. **A first reading was WRONG and is kept in the record**: a hit test called every map control unclickable on every phone, having never dismissed the onboarding hint or collapsed the sheet. The screenshot disagreed with the measurement, and the disagreement was the signal. **OPEN:** the render-race guard is fixed for `api-docs.html` and not generalised to the other eight pages, any of which could pass by scanning before its content exists (`AUDIT_REPORT.md` §7 item 6).) Previous review 2026-08-21 latest (**FOUR THINGS THE PRODUCT SAID CONFIDENTLY THAT WERE NOT TRUE, AND ONE OF THEM HAD NEVER BEEN TRUE.** `/v1/environment` scored every UK coordinate with LONDON's geometry from the day it shipped - M22 5RX, 1.2 km from Manchester Airport's runway, published 10.0, the top of the scale, against Manchester's own 2.0. Structural rather than incidental: every term in `calc_postcode_quiet` is distance-gated, so a geometry lacking your airport CANNOT over-report, and over 6,000 sampled NSPL postcodes **291 of 291 changed readings moved louder, none quieter**. `derive_city()` is now the ONE holder, shared with `resolve_query`, because two correct copies is what caused the next one. **`/transport` had NEVER returned a line status** - one function sent a User-Agent and its mirror eleven lines below did not, TfL 403s urllib's default, the 403 became `[]`, and an empty disruption list is indistinguishable from "every line running normally"; a suspended Central line read as "no disruptions" for the endpoint's whole life. **The test could not see it and the FIRST fix did not make it able to** - `"lineStatus" in body` is satisfied by `[]`, so the mock learned to 403 and the suite stayed green. Ten cities promised live crime data from `data.police.uk` that no code fetches and the CSP would block. Road Lden had a floor and no ceiling while its mirror had both, and the two GeoTIFF nodata sentinels have OPPOSITE SIGNS, so `+3.4e38` was publishable as decibels. **Four separate places said `/v1/regions` is key-gated; it answers 200 with no key** - and the `handle_changes` docstring had it RIGHT in an earlier version and was "corrected" into the falsehood. **A recorded finding was itself wrong**: the `excellent` air band was down as one no UK borough can occupy, but 59.2% of 254,904 DEFRA cells clear both WHO guidelines and the PM2.5 median is 4.43 against a guideline of 5.0 - the band is reachable, our COVERAGE is 86 urban boroughs, and dropping it would have meant re-adding it. **OPEN and deliberately not patched:** the public demo key reaches `POST /v1/chat` and `/v1/score/batch` because **API Gateway usage plans authorise per STAGE, not per route**, so any future key-gated route is granted to it automatically - an auth-architecture choice. ~~**OPEN:** nine UK cities are shown "NYC subway data coming soon", and the 1,771 NaPTAN stations built to fix that are unreachable behind a `currentCity === 'london'` branch.~~ **CLOSED, and it was already closed when this was written** - re-measured 2026-08-23 against the code: the panel branch is THREE ways not two (`index.html:10254`), `renderNaptanStations()` was extracted the same day so both the TfL-returned-nothing path and the no-TfL-here path call it, and "NYC subway data coming soon" now reaches only NYC, which genuinely has no station data. **Fourth time a recorded blocker in this file has outlived its own fix**; re-measure before working from one.) Previous review 2026-08-12 latest (**COLD OUTREACH IS BLOCKED BY DKIM ALIGNMENT, NOT BY A MISSING MAILBOX.** (An earlier version of this entry said there was "no way to send as @skyscore.co.uk at all". **That was WRONG** - Bill corrected it: `support@skyscore.co.uk` has been sending for months via Gmail's "Send mail as", with Cloudflare Email Routing on the inbound side. The narrower and more easily-missed problem is that **Gmail DKIM-signs those messages as `gmail.com` while the From: header says `skyscore.co.uk`, so DKIM does not ALIGN** - the signature is valid and vouches for the wrong domain. Nothing enforces that today because no DMARC record exists, which is precisely why it looks fine.) Measured from public DNS: SPF exists (`v=spf1 include:_spf.mx.cloudflare.net ~all`), **DKIM has no selector published** (nine common ones checked) and **`_dmarc.skyscore.co.uk` does not exist**. The MX records are `route1/2/3.mx.cloudflare.net` - **Cloudflare Email Routing, which is RECEIVE-ONLY**. It forwards `support@` to an inbox; it provides no SMTP and signs nothing outbound. So "add a DKIM record" still cannot be done in isolation - **Gmail will not issue a DKIM key for a domain it does not host**, so this is an ALIGNMENT UPGRADE of a working setup rather than a build from scratch. Since Feb 2024 Gmail and Yahoo require SPF + DKIM + DMARC with DKIM ALIGNED to the From: domain, so the five drafts unsent since 21 May would not have landed even if sent. **Runbook written: `EMAIL_AUTH_SETUP.md`.** Step 1 (DMARC at `p=none`) is safe to apply today with no provider and starts the reporting feed. Step 2 is the real decision - **Google Workspace at ~GBP5/month is the recommendation**, because the free "Gmail send-as" route signs as `gmail.com` and therefore FAILS DMARC alignment for skyscore.co.uk while appearing to work. **Warm follow-ups need none of this** - they are already authenticated as gmail.com, which is what they claim to be. Cannot be applied from here: Cloudflare dashboard access, same constraint as the AWS console work.) Previous review 2026-08-12 (**THE MAP'S TRANSPORT LAYER WAS EMPTY FOR NINE OF ELEVEN CITIES, AND THE NEIGHBOURHOOD RANKING WAS A PRICE SORT WEARING A SCORE'S CLOTHING.** 1,771 NaPTAN stations now fill that layer, DISPLAY-ONLY - the `+/-0.4` liveability nudge those arrays fed is REMOVED rather than filled, because transport is already scored from the same register at borough level since v3.6 and filling them would count one measurement twice. Two traps on the way, both the bbox/first-match family already seen this morning: **a bounding box is not containment** (Leicester and Nottingham overlap; first-match-wins gave Leicester 104 stations and Nottingham 16, point-in-polygon gives 19 and 69) and **stripping a descriptor anywhere in a name edits the name** ("Station Approach" -> "Approach"; four Altrinchams). **The ranking now says "best value" where price leads it**: rank-to-price correlation is -0.23 in London, -0.06 in NYC, and 0.67-0.89 in every generated city, so nine of eleven lists are largely cheapest-first - each puts Bradford City Centre, Middlesbrough Town Centre, Chopwell or Bootle at #1. Structural, not a fault (postcode districts carry `crime: 0` and inherit borough liveability), and **nothing is miscomputed - the LABEL over-claimed**, the same distinction as WA8 publishing a Knowsley median as "Widnes". **The threshold is MEASURED at render time, never a per-city string**, so the disclosure removes itself when it stops being true. ~~**OPEN: the `excellent` air-quality band can never fire** - all 86 boroughs exceed the WHO PM2.5 guideline of 5 ug/m3 (range 6.3-11.3), so the legend advertises a category no UK borough can occupy.~~ **CLOSED 2026-08-23, and this sentence was wrong in two ways.** The 59.2%-of-national-cells measurement on 2026-08-21 already corrected "can never fire" to "cannot fire for the urban boroughs we cover". The second error survived that: **the legend did not advertise the band at all.** It carried three swatches against the painter's four colours, so `excellent` was a colour the map could paint with nothing to name it - the inverse of what was recorded. Fixed by adding the swatch AND making every band row measured, so 41 of 99 rows that described nothing on their map now hide themselves.) Previous review 2026-08-12 (**POSTCODE SCORING WAS LONDON-ONLY IN PRODUCTION, AND THREE DOCS SAID OTHERWISE.** `/v1/score?postcode=M1+1AE` answered "Borough not currently supported in london" - a city the caller never named - and B15, LS1, S1, BS1 and NG1 did the same, while CLAUDE.md, ROADMAP and METHODOLOGY all recorded the capability as un-gated since 2026-08-10. **The un-gating was real and unreachable**: `?city=manchester` scored 7.7 on the same postcode throughout, but `city` defaults to `london` and nothing derived it from the resolved LAD. **Every piece was correct** - the un-gating commit, `LAD_TO_BOROUGH`, and the postcode table, whose M1 1AE row CLAUDE.md records verifying by hand. Nothing joined them. Fixed in three parts (derive from `_ladCode`; fall back to a borough-NAME index because the postcodes.io tier has no LAD code; absorb the `City of Bristol` / `Bristol, City of` inversion in both the derivation and `normalise_borough`). **12 of 12 cities verified LIVE.** **A passing test asserted the defect** - `test_resolve_query_404_unchanged_for_non_london` was right when written, never revisited when the gate lifted, and read as evidence the endpoint worked; `PostcodeCityDerivationTests` replaces it and asserts the DERIVED CITY. **Nothing else could have caught it**: score sanity probes 16 LONDON postcodes - widening that is the open follow-up. **Also: the a11y gate scanned one desktop viewport and the landing state only**; it now scans a phone and the post-selection state, and immediately caught two real bugs, both fixed - contrast systemically, via text tokens that clear 4.5:1 on the metric card as well as the sidebar. **And a blocking gate died on a line-ending change**: `build_aircraft_bands.py --check` matches a literal "
}
", so a `git restore` flipping LF to CRLF took it from green to a traceback for all eleven cities with no data change. `_slurp` now normalises.) Previous review 2026-08-12 (**THE DEFRA RASTER TIER NOW REACHES EIGHT MORE CITIES - `impact` was the last score input still an estimate outside London.** Seven of DEFRA's twelve per-airport Lden coverages are loaded, covering 7,339 postcodes across Birmingham, Bristol, East Midlands, Leeds Bradford, Liverpool, Manchester and Newcastle. **The scope was MEASURED, and five coverages turned out not to be worth loading**: Heathrow's and London City's would have REPLACED London's better region-export coverage (35,352 postcodes down to 17,330), and Gatwick's, Luton's and Stansted's 3,704 readings all land outside `LAD_TO_BOROUGH` where `/v1/score` cannot resolve a city. **Coverage is thin by nature - 0.6% to 3.9% of each city** - these are contour strips, not city rectangles, so ~97% still answers from geometry. **What it corrects: mean 2.224 score points, signed -2.104**, the geometry estimate reading these postcodes LOUDER than DEFRA measured. **London already received a correction of the same size (2.070)**, so the product had been ranking London postcodes measured one way against eight cities' measured another - consistency, not accuracy, is the argument. **Caveat carried everywhere those numbers appear: Round 4 maps 2021, which DEFRA calls atypical**, so some share of the -2.1 is real COVID-year reduction. **A plausibility guard that described itself as "a range, not a value" was a floor**: the two nodata sentinels have OPPOSITE signs (+3.4e38 London, -3.4e38 per-airport), so `+3.4e38` passed and scored 0.0, maximally loud, off a cell with no measurement. Ceiling added and proven red both ways. `scripts/load_aircraft_rasters.sh` waits for the air-quality loader, loads the seven, and GATES THE DEPLOY on all seven succeeding - load-then-deploy, because loading flips `/v1/score` while the site keeps its status quo.) Previous review 2026-08-12 (**18 DISTRICTS WERE PUBLISHED FOR PLACES MOSTLY OUTSIDE THE CITY PUBLISHING THEM, AND ARE NOW DROPPED.** Bill asked about "Widnes (WA8), Knowsley" in the Merseyside ranking. **4% of WA8's 1,591 live postcodes are in Knowsley; 1,500 are in Halton, which we do not cover at all.** So it published a Knowsley median of GBP345k resting on 32 sales - Merseyside's FOURTH PRICIEST entry - under the label "Widnes", the post town of the 94% we do not price, at a centroid averaged over the whole district and therefore plotted in Halton. Every step was arithmetically correct; the JOIN was wrong - transactions bucket by Land Registry `district` (a local authority) while entries publish as postcode districts (Royal Mail), and those do not nest. **34 of 501 were under 75% contained, 8 under 20%.** A 50% floor drops 18, 503 -> 485, every drop printed with its share. **`lat/lon` and `postcodes` now cover the covered part only** - 43 retained markers moved, Darlington by 4.4 km. **A district belongs to exactly one city**: WN4 and WN5 straddle Wigan/St Helens and were each published TWICE at identical coordinates, WN5 as `Pemberton & Orrell` GBP165k in Greater Manchester and `Billinge` GBP235k in Merseyside. The LABEL is the part no arithmetic repairs - the covered slice of WA8 has no name of its own - which is why the floor drops rather than relabels.) Previous review 2026-08-12 (**LEICESTER AND TEESSIDE ARE ON THE CONSUMER SITE - THE SITE AND THE API NOW CARRY THE SAME ELEVEN CITIES, 91 BOROUGHS.** Neither was ever held back by data: Teesside's five unitaries are their own education authority so all five measure 4 of 4 liveability inputs, and Leicester's districts hold 3 of 4. **The one-way-door gate finally exists** - `tests/borough-score-parity.mjs` drives the real page and compares the score it RENDERS against the Lambda for all 91 boroughs, which is the check the Manchester incident needed and nothing had; proven red at -3.8 and blocking in preflight. **Nottingham's "1 of 4 inputs, cannot leave" is CORRECTED**: healthcare in v3.7 took its outer districts to two inputs, so it clears the floor and stays back on judgement rather than impossibility. Cardiff genuinely cannot (Progress 8 is an England measure). **Three pre-existing defects surfaced while wiring it up**: the flood and air-quality legends labelled their FIRST SWATCH "NO DATA" on all seven UK cities - the High and Poor bands - while the map painted real EA and DEFRA readings underneath; five legend explainers still told users the ladder "reaches further than the airport really does", false since v3.8 hours earlier; and the city strip's bound lived only in the <=900px block, so eleven chips ran off the edge at 901px where the phone fix did not reach. **Two hardcoded enumerations became derived** - the neighbourhood builder reported "448 across 7 cities" while silently skipping both new cities, and locator-verify's counts were hardcoded at 10/8. **CLOSED 2026-08-12: curated area names, and the names are SOURCED.**) Previous review 2026-08-12 (**THE 273 DUPLICATE AREA LABELS ARE DOWN TO 5, AND EVERY CURATED NAME IS CORROBORATED AGAINST A PUBLISHED SOURCE.** 273 of 503 districts rendered under a repeated post town - Birmingham x35, Liverpool x29, Leeds x16, Sheffield x15, Bristol x16 - because only Greater Manchester had overrides. Nothing shipped was false, the outward code being visible beside every label, but thirty-five "Birmingham" rows in a ranked list tell a user nothing. `NAME_OVERRIDES_BY_CITY` now covers all nine cities (285 names) and **`--check-names` asserts each one against that district's own House of Commons Library MSOA name**, blocking in preflight, evidence checked in at `data/district-msoa-names.json` so the gate needs neither NSPL nor a network. **Deriving the names outright was tried FIRST and rejected on measurement, not taste**: a district spans 4-13 MSOAs so the modal name carries 15-33% and names a sub-area - BS8 came out `Clifton East`, SK5 came out `Brinnington` when the district is Reddish, and a shared-token variant gave `Five` for B16, `Quays` for M50 and `Mossley` for BOTH L17 and L18, recreating the duplicate it was meant to fix. Manchester's 26 hand-written names were the answer key. **The check immediately caught four labels that had shipped for months** - `Chorlton-on-Medlock`, `Chorlton-cum-Hardy`, `Ancoats & Northern Quarter`, `The Heatons` - none of which any published source places in those districts. **Two failure modes recorded because both nearly shipped green**: a dict keyed `west_midlands` when the builder's key is `westmidlands` corroborates perfectly and reaches nothing (163 of 285 names were dead while the check read all-green, now guarded); and a `--city` run wrote its own 59 districts over the 501-district evidence file, reddening 239 good names in preflight - the evidence is now written only by a full build. The 5 remaining duplicates are Bath x2 and Darlington x3, left as post towns because no single area name is widely recognised for any of them.) Previous review 2026-08-11 later (**METHODOLOGY v3.8 - THE AIRCRAFT LADDER IS SCALED BY EACH AIRPORT'S MEASURED NOISE FOOTPRINT, AND THE FIX HAD TO BE MADE TWICE.** The distance ladder was calibrated on Heathrow and applied UNWEIGHTED to every airport, so it asserted every airport was Heathrow-sized: **Stockton-on-Tees was published `severe`, Hounslow's band, off an airport carrying 173,006 passengers a year against Heathrow's 83.9 million** - quiet 0.0, overall 2.6. The scale is now the published contour itself: area above 55 dB Lden in each airport's DEFRA Round 4 surface, as an equivalent radius over Heathrow's 4.91 km. **Passenger counts were tried first and are the WRONG proxy** - they collapse six airports onto one value and measure demand not emission (East Midlands is second-largest of the twelve on 3.2M passengers because it flies freight at night; Gatwick is 0.475 on 40.9M). **31 borough bands move, all upward, +0.30 to +1.60; no London or NYC borough moves, Heathrow being 1.000 by construction.** Scaling every rung alone OVERSHOT - it moved 29 boroughs and moved all 29 DOWN, putting Vale of Glamorgan on `low` with Cardiff Airport inside it - so a borough holding any part of a published 55 dB contour is floored at `moderate`, measured to the POLYGON not the centroid. **The important half: `calc_postcode_quiet` runs its OWN copy of the ramp and takes precedence over the borough band**, so fixing only the band left the two tiers contradicting each other by up to 4.0 points. Both are now scaled. **Validated rather than argued: against the 35,352 London postcodes DEFRA measured, mean absolute error falls 3.230 -> 1.879, with 14,730 postcodes closer and 20 further**, signed error staying negative so it never crosses to optimistic. London postcodes therefore move (65%, mean +1.75) around LGW/STN/LTN and especially LCY, 2.7 km2 against Heathrow's 75.6; discrimination checked first, London keeps all 11 distinct values over 0.0-10.0 and no city collapsed. **Also fixed a live site/API divergence found in passing**: both client-side ramps hardcoded JFK/LHR, so the +2 major-airport bonus could never fire in ANY of the seven single-airport cities and the site scored them 2 noise points quieter than /v1/score. **`impact` was the last score input with no script behind it** - `build_aircraft_bands.py --check` is now blocking in preflight, proven red at 89 disagreements; two new tests compare the site's scale and major-airport registries against the Lambda's. Deployed and verified live at v3.8, both surfaces.) Previous review 2026-08-11 late night (**METHODOLOGY v3.7 - THE LIVEABILITY COMPONENT IS NOW FULLY MEASURED.** Healthcare derived from the NHS ODS register (10,173 GP practices and branch surgeries) as the share of postcodes within 500 m of one. **78 of 86 boroughs now score on all four liveability inputs, up from 38**; the rest are Cardiff (no Progress 8 in Wales) and Nottingham's outer districts. 54 boroughs moved, mean 0.22, max 0.60. Radius chosen by measurement: at 1 km, 68 of 81 came out `excellent` and none `moderate`. **Two accuracy traps hit and recorded**: the ODS GP role is RO76 not RO177 (which also covers hospices, care homes, courts and prisons), and a practice's PRIMARY role is RO177 so `PrimaryRoleId=RO76` returns zero - a well-formed query that answers 200 and is silently empty. Deployed and verified: Coventry now reports `measured` rather than `partial`. **Breadth, not depth, is now the sensible next move** - the ranked English city-regions in `EXPANSION.md` inherit all four inputs with no new integration.) Previous review 2026-08-11 night (**METHODOLOGY v3.6 - TRANSPORT IS NOW MEASURED FOR ALL 81 BOROUGHS, AND SCORES MOVED.** Derived from NaPTAN (DfT national access node register) as the share of a borough's postcodes within 800 m of a rail/metro/tram node. **Rail/metro/tram only, never bus** - 416,539 of NaPTAN's 435,298 nodes are bus stops - and **never called PTAL**, which is all-modes and London-only. **52 of 86 boroughs moved liveability by >0.05, mean 0.64, max 1.50** (Enfield +1.50); London mostly rose, the other cities mostly fell. Bill authorised the movement explicitly. **Cardiff became scoreable for the first time** (1 input became 2, clearing the floor) and could now leave BACKEND_ONLY_CITIES - a ONE-WAY DOOR needing per-borough output parity first. Nottingham did NOT move: three of its four boroughs still hold one input, because education is an upper-tier county function. Deployed backend + frontend, verified live at v3.6. **Also tonight: 448 neighbourhoods across 7 cities, area search fixed for every generated city (Manchester's 85 had been unreachable since launch), and South Yorkshire's search crash on a city with no airport.** **HEALTHCARE IS NOW THE ONLY REMAINING LIVEABILITY GAP** (0.10 weight) - NHS ODS 403s, OSM Overpass is the ODbL fallback. See `EXPANSION.md`.) Previous review 2026-08-11 evening (**THE MAP LAYERS WERE INVENTING DATA FOR SEVEN CITIES; ROAD NOISE AND AIR QUALITY ARE NOW DERIVED FOR ALL OF THEM.** Bill asked whether the layer data was actually per-city. It was not: road noise, flood and air quality each ended their lookup with `|| 'moderate'` / `|| 'low'`, and `borough-extra.json` held those fields for London and NYC only, so all seven other cities were painted ONE confident colour per layer for a reading nobody had taken - under a legend title that already said "(NO DATA)". **The data was one bounding box away**: `fetch_defra_road_noise.py` already pointed at an England-wide coverage and only ever fetched London's bbox. Now derived for every city by `scripts/build_borough_bands.py` (711 fields), sampled at NSPL postcode centroids, banded on WHO guidelines - road on the SHARE of addresses over WHO 53 dB Lden, air quality on the worse of NO2/PM2.5 against WHO 2021. **London's own values were replaced too** - a hand-written literal with no script, several assigned by airport proximity rather than roads. No score changes (flood/airQuality are `plannedComponents`). A borough with no reading is now unpainted rather than defaulted; `tests/layer-honesty.mjs` gates it and is proven red. **Air-quality per-postcode load resumed and running** (48.8% → 51%+, ~15h remaining at ~20 rows/s; the unapplied `dynamodb:BatchWriteItem` grant would cut it ~25×). **FLOOD RISK NOW SOURCED TOO (same night)** - EA Risk of Flooding from Rivers and Sea for all 73 UK boroughs, banded on the share of addresses at Medium/High (the 1%-annual-chance Flood Zone 3 line). The dataset has no WCS/WFS and its postcode product is retired, so it is fetched by rendering the WMS and decoding colours - antialiasing off, and the colour map VERIFIED against the service's own `risk_band` by point-in-polygon. **It moved 18 of London's 33 boroughs**, because RoFRS is risk AFTER defences: central Thames-side boroughs fall to `low` behind the Barrier while Kingston rises to `high` upstream of it. The detail panel says which question it answers. Previous review 2026-08-11: (**SIX OF THE NINE CITIES WERE UNUSABLE ON THE LIVE SITE, AND THE PHONE COULD NOT REACH ANY OF THEM.** Reported by Bill as "I don't see Merseyside or Yorkshire", which turned out to be two separate defects plus a layout one. (1) `center`/`scale` sat in a **second city registry** holding three cities while `CITY_DATA` held nine, so West Midlands, West Yorkshire, South Yorkshire, Merseyside, Tyne and Wear and Bristol threw on selection - **title changed, map did not**, live since 2026-08-10. (2) A second throw hid behind it: the new corridors were ported from the Lambda under its `coords` key while the renderer reads `.coordinates`. South Yorkshire was the only new city unaffected, *because it has no airports*. (3) The chip row was 453px wide against a 375px viewport with no bound, so the map container clipped it - **3 of 8 UK cities untappable at 320px**. **None of this was a data problem**: all 30 boroughs had been output-compared site-vs-Lambda before shipping. What was never checked was whether a user could reach the city. **Four guards added, each proven red in both directions**: `center`/`scale` moved into CITY_DATA so key parity covers them; `tests/city-switch.mjs` clicks every chip (nothing ever had); the responsive audit now fails on a stranded control, which it had been *computing and not printing* since it was written; the smoke stage enumerates the registry instead of naming three cities. Chips are now a scroll strip with a measured edge fade. **NOT YET DEPLOYED - production still carries all three defects.** Previous review 2026-08-10 evening: (**NINE CITIES ON THE SITE, ELEVEN ON THE API, POSTCODE-LEVEL EVERYWHERE.** Six Core Cities regions reached the consumer site after Progress 8 lifted them over the two-input liveability floor; all 30 boroughs were output-compared site-vs-Lambda before the one-way door was opened. Postcode scoring is un-gated beyond London and needed NO NSPL reload - the LAD code was in the table all along. Corridors resampled to a common 1 km interval first, which corrected a claim made in three places: London was 3.34 km, not ~1 km. **Next: sample the DEFRA Round 4 rasters per airport** (proven downloadable; Birmingham already on disk) to move ten cities from modelled to measured. **Cardiff and Nottingham stay API-only** - no Progress 8 in Wales, and Nottingham's outer boroughs are districts rather than local authorities. **Still the actual bottleneck, unchanged: 5 outreach drafts, 0 sent since 21 May; 6 warm Build Night connections unfollowed; no DKIM or DMARC on skyscore.co.uk, so cold email lands in spam while warm Gmail follow-ups need neither.**)
`-based replacements silently no-op on the CRLF file and report success. Use the Edit tool on tests. **STILL OPEN, AWS-console (only TWO need Bill's hands):** assign a 2nd MFA device; apply `FlightMapDeployPolicy` (paste-ready file generated, adds `dynamodb:BatchWriteItem`, the logs retention/read actions and `cloudfront:GetInvalidation`). Everything else is CLI-runnable once that lands: export ~47 KB of dormant log content, delete the **6** orphaned groups, set retention on the **7** active ones (**note: 6/7, not the 7/6 recorded earlier**; a restore would not reuse an old group anyway since CFN assigns a fresh suffix). **STILL OPEN, non-AWS:** EPC token rotation (**higher priority** — printed into a chat log; lives in **two** places, `.env` AND `backend/samconfig.toml`), Cloudflare `CNAME api → d1pr4crjutz9z8.cloudfront.net` (**AWS side verified complete**, domain exists; still `NXDOMAIN`), the four Professional-tier copy surfaces, Migadu/DKIM, Android Play Console. **OPEN QUESTION:** real-terms/CPI adjustment — at 2% CPI **22 of 33** boroughs are falling vs 14 nominal, and Barking flips from rising to falling, which contradicts live copy saying 'still rising'. Blocked on a CPI figure: **the ONS timeseries API was decommissioned 25/11/2024** — do not invent a rate.) — Previous review 2026-07-29 (**Free-tier cut DEPLOYED and verified · demo key rescued from the same plan · Professional decided · a closed audit item was silently gating the CNAME swap.** (1) **The quota cut is live.** `SkyScoreFreeTier` (plan `sjtyz8`) reads **100 req/month** with `RateLimit` 1 from `get-usage-plans` — the 27 Jul decision had been committed but never deployed, so every doc describing it in the past tense was describing something that had not happened. Verified **from the API, not from the deploy's own report**. (2) **Deploy order was chosen, not incidental: frontend first.** The drift window has to exist either way; pages advertising 100 against a plan still granting 1,000 under-promise, whereas the reverse re-creates exactly the trust problem the cut was meant to close. (3) **`ScoreDemoUsagePlan` created (`x88go8`, 2,000/month) and the shared public demo key relinked onto it** — CloudFormation created the plan but **could not move the key**, which was created out-of-band in May 2026 and is unmanaged by CFN, so between deploy and relink the public `/score-demo` form was drawing on the tightened 100. **APIGW quotas are per-key, not pooled per plan** — the exposure was one key shared by the whole internet, not key-to-key contention. Unlink-then-link is mandatory (APIGW refuses a key on two plans sharing an API stage) and belongs in **one chained shell command** so the no-plan window cannot be paused in. Verified structurally *and* functionally: a live `GET /v1/score` with the embedded key returned 200. Runbook now DONE in `OPERATIONS.md` §2 with real plan ids. (4) **`A-0724-M4` was fixed, deployed, and still logged as open — and the 25 Jul correction recorded it as gating the `api.skyscore.co.uk` CNAME swap** on the reasoning that landing it afterwards is too late for anyone already installed. So a closed item was holding back a DNS change. Verified before rewriting: `sw.js` excludes `js/api-base.js` from the shell precache, serves `/js/` network-first with `cache:'no-cache'` plus a `fresh.ok` guard, `VERSION` is `v1.0.2`, and the live file is **byte-identical to source**. **That gate is lifted.** Generalisable: a stale "open" is not a cosmetic error, it is a false constraint. (5) **Professional's ×100 DECIDED (Bill, in-session): keep 100,000 requests, publish a 1,000,000 scores/month ceiling beside them.** The free-tier move repeated, because the unit was the problem both times. Rejected: cutting requests to 10,000 (caps scores correctly but charges £499 for 10,000 single-address lookups, and a portal doing per-search lookups is the likelier first customer), and building per-score metering now (premature). Price unchanged. **The ceiling is UNENFORCED and recorded as such** — APIGW meters requests, so nothing stops a Professional key taking all ten million; it stops the price list lying, it does not stop the extraction, and **Professional's first paying customer is precisely the trigger this project deferred option A against.** **NOT SHIPPED:** `pricing.html`, `api/index.html`, `score-demo/openapi.yaml` and the signup response still carry no Professional score ceiling, and all four need a deploy. (6) **`cloudfront:GetInvalidation` is denied** — the invalidation fires but its status cannot be read, so deploys are verified by fetching the CDN instead. Same shape as `dynamodb:BatchWriteItem`: **both grants are in `backend/iam-policy.json` and neither is applied to the live policy**, because that needs the locked-out console. **Treat `iam-policy.json` as an aspiration, not a description of live permissions.** (7) **`EPC_BEARER_TOKEN` needs rotating — Claude printed `backend/samconfig.toml` into a chat log.** Not publicly leaked (gitignored at `.gitignore:1`, absent from all git history under `git log -S`), but the project's own rule covers a chat log. **The token lives in TWO places** — `.env` *and* `backend/samconfig.toml` — so rotation must update both, then redeploy. (8) **AWS Support replied and recommended the recovery route already proven dead** (alternative factors, where the control is not a link); reply sent asking what phone number is on file and whether a network restriction applies, call offer accepted. Untried and cheap: a mobile hotspot, and proving AWS mail reaches the inbox at all. Memory: `project-aws-console-lockout`. (9) Preflight run green three times (8 blocking checks incl. both pytest suites and Playwright at `--workers=2`); pushed as `c0026b9` + `a06f4a8`, local level with origin. **STILL OPEN, all user-side:** EPC token rotation (**now higher priority**), the four Professional copy surfaces + deploy, `api.skyscore.co.uk` CNAME (**newly un-gated**), log retention + orphan-group cleanup and the two IAM grants (all still blocked on the console lockout), Migadu/DKIM, Android Play Console.) — Previous review 2026-07-27 (**NSPL loader made fast for the August roll · batch-metering decision written up · AWS console lockout now blocks everything user-side.** (1) **`scripts/load_nspl.py` switched from per-item `PutItem` to `BatchWriteItem`** — 25 items per signed request, ~96% fewer round trips, targeting the August vintage roll that would otherwise pay the measured 5.80 hours again. The per-item design only ever existed because the IAM action was ungranted. **The next load is unmeasured and no figure is quoted** — this docstring was already 10× optimistic once. The loader **degrades automatically** on `AccessDeniedException` and completes at the old ~129 rows/s, so it is safe either side of the grant; **a roll that still takes ~6 hours is the signal the grant never landed.** (2) **The `UnprocessedItems` retry loop is the load-bearing part, not defensive padding.** `BatchWriteItem` signals partial failure as an **HTTP 200 with a non-empty `UnprocessedItems` map**, never an exception, so boto3 adaptive retry cannot see it; dropping it would lose rows while `written` still credited them and the checkpoint advanced past them — unrecoverable, because a resume starts *after* the rows that never landed. Same class as the checkpoint-ahead-of-writes bug fixed 25 Jul. Exhausting retries is deliberately fatal. 5 tests added (`TestBatchWritePath`), all covering ways the swap loses rows *while reporting success*; root 140 → **145**, backend **125**. (3) **`backend/iam-policy.json` gains `dynamodb:BatchWriteItem` + a `CloudWatchLogsOperateOwnGroups` statement** (logs read + `PutRetentionPolicy` + `DeleteLogGroup`, scoped `/aws/lambda/london-flight-map-*`). **The file is not the live policy.** A probe confirmed `logs:PutRetentionPolicy` is still cleanly denied — and the denial message revealed IAM evaluates that action against an ARN ending `:log-stream:`, which confirms the trailing wildcard is load-bearing; an exactly-scoped group ARN would have been **silently insufficient**, the same failure shape as the signup outage. (4) **`BATCH_METERING_DECISION.md` written** (figures read from `template.yaml` + `score/app.py`, not memory): quota 1,000/month × `MAX_BATCH_SIZE` 100 = **100,000 free scores/month**. **Newly noted: the quota is monthly but the throttle is per second, so one free key drains the entire allowance in ~8.5 minutes** — a burst, not a drip, and the $20 billing alarm is not positioned to catch it. Five options; recommendation is that the launch blocker is **not** building metering but **deciding what the free tier may be worth** (`Quota.Limit: 100` → 10,000 scores/mo, one line, shippable before any pilot signs), with in-Lambda score metering deferred until a paying customer justifies operating it. **Decision still open — Bill deferred it 27 Jul.** (5) **NEW BLOCKER: Bill is locked out of the AWS console.** Correct root password, bounced back to sign-in, and a **passkey prompt he never knowingly registered**; dismissing it, alternative browsers and the cross-device QR flow all failed (the QR is only a Bluetooth handshake, so "nothing happens" means the phone holds no AWS passkey). **Account-recovery ticket filed with AWS Support 27 Jul, awaiting response.** **On first successful sign-in, check the MFA device list and its creation date** — if it does not reconcile, treat as compromise on an account holding customer emails (rotate root, remove device, read CloudTrail, rotate `flightmap-dev` keys), then register a TOTP authenticator so console access never again depends on a passkey nobody remembers creating. Memory: `project-aws-console-lockout`. (6) **Two quality-gate defects found, neither fixed.** `npm run format:check` **fails on `index.html`** (pre-existing, byte-identical at origin — reformatting an 8,200-line hand-maintained deployed file is a decision, not a chore). The **Playwright e2e suite reports false failures at default concurrency** — 14 failed / 2 passed, versus **16 passed at `--workers=2`** — because it runs against the *live CloudFront site* and the parallel burst produces timeouts indistinguishable from real assertion failures; `workers: 2` was deliberately **not** pinned, since one run cannot tell whether the constraint is CloudFront or the machine. Also: `make` is absent from Git Bash here, and `cmd | tail` reports *tail's* exit code — an initial "preflight exit 0" was meaningless. Memory: `feedback-playwright-parallel-false-failures`. (7) **THE OFFLINE CITY-SCALE BULK SCORER IS BUILT** (`scripts/score_bulk.py`, `make score-book IN=… OUT=…`) — the Enterprise "score your whole book / whole city" deliverable and the pilot demo artefact, unblocked by the NSPL load finishing on 26 Jul and repeatedly listed as NOT built in every review since 25 Jul. **Zero methodology drift by construction:** it does not reimplement scoring, it imports the score Lambda and calls **`resolve_query()`** — the exact function the live API calls one layer below HTTP — so every threshold, weight, persona, alias, NYC ZIP mapping and terminated rule is shared with production structurally, not by discipline. Reimplementing would have reopened the class audit I4 closed. **Why offline:** `/v1/score/batch` caps at 100 queries in a 28s timeout, so a 100k-address book is 1,000 calls = the entire monthly free-tier quota; offline it is ~£0.02 of DynamoDB reads and no quota. **Decision (Bill, 27 Jul): every input row appears in the output**, with a machine-readable `status` and a plain-English `note` for anything unscored — a silently short CSV looks complete and is not, which is the `UnprocessedItems` failure shape again but worse, because the reader is a customer who cannot tell a deliberate exclusion from a bug. **Honesty constraint preserved:** a 404 for a retired postcode is byte-identical to one that never existed (deliberate public API surface, audit L5), so the `not_found` note SUGGESTS a retired postcode and points at `--include-terminated`; it never asserts a cause we cannot observe. Customer columns are carried through so the output reconciles row-for-row rather than needing a lossy join on postcode (a block of flats shares one), with collisions renamed `src_*` so a customer column can never overwrite a computed one. **Import order is load-bearing and handled** — `score/app.py` reads `POSTCODE_TABLE`/`NOISE_RASTER_TABLE` at *module* level, so getting this wrong routes an entire run through postcodes.io, the very free service the NSPL table exists to stop depending on, while still appearing to work. 22 offline tests (root 145 → **167**), covering the customer contract rather than the scoring. **Known follow-up:** lookups are per-item `GetItem`, so this inherits the same client-CPU bound the loader measured; a `BatchGetItem` prefetch is the same ~25× win but would mean interpreting NSPL rows outside `_lookup_postcode_local`, so it is deliberately deferred until a real book is measured. (8) **`/preflight` was lying in both directions, and is now a real script** (`scripts/preflight.sh`, wired to `make preflight`, `npm run preflight` and the skill so all three cannot drift apart). **False green:** `make preflight` reported success while running *nothing* — `make` is absent from Git Bash here and every check in the skill was piped to `tail`, and a pipeline exits with the status of its LAST stage. **False red:** Playwright, as above. **A silent gap, the worst of the three: the root suite was never in the gate at all** — only `backend/tests` ran, so all 167 root tests have been unguarded before every commit to date. **A no-op reading as a tick:** the `pip-audit` step looped over `backend/lambdas/*/requirements.txt`, which matches nothing, and swallowed the result with `|| true`. Verified the new script exits 1 on an injected defect rather than assuming it. ruff widened from `backend/lambdas` to `scripts/` + `tests/` (6 pre-existing findings fixed). Prettier is now **advisory and labelled as such** — every file in the repo deviates and reformatting `index.html` is a 19,205-line diff on an 8,462-line deployed file, so blocking on it would leave the gate permanently red, which is how a gate becomes decoration. **`SECURITY.md` corrected:** it claimed `npm audit` clean; the dev tree carries 4 high advisories. The accurate statement is stronger — `dependencies` is empty and there is no build step, so nothing from `node_modules` ships and `npm audit --omit=dev` is **0**. (9) **A11Y: THE SCAN ONLY EVER COVERED THE HOMEPAGE.** `/` had had three a11y waves run over it and reported a clean sweep, while `/pricing`, `/privacy`, `/api/`, `/changes` and the three `score-demo` pages had **never been scanned**; the spec also failed on `critical` only, and every defect found was `serious`, so two independently-defensible narrowings multiplied into a check that could not fail. Extended to all 8 pages at critical+serious. The four investor-facing pages were already clean. **The `score-demo` pages were not:** `status.html` had **no global `a` rule at all**, so both footer links used the browser default `#0000ee` on `#06070d` — **2.14:1**, effectively invisible and live since the page shipped; links across all three pages were distinguished from surrounding copy by colour alone (1.49:1 vs 3:1) with the underline only on `:hover`, which touch and keyboard users never get; and Swagger UI's server `<select>` **had no accessible name**, which axe rates CRITICAL — a screen reader announced it as "combo box". Swagger's method badges (~2:1), version badge and description links were fixed too, all from the page's own `<style>` + an `onComplete` hook rather than by editing the vendored bundle, so an upgrade cannot silently revert them; badge FILLS were darkened rather than text recoloured, preserving the blue-GET/green-POST coding. `nested-interactive` is left failing and excluded **by name, on that one page** (Swagger renders a button inside a button — upstream defect), which keeps every other rule enforced there. Verified 0 critical/serious locally on all three. **SOURCE ONLY — the live site still carries these until a `web-deploy`, and the e2e gate correctly reports them as failing until then.** (10) **Task #4 closed** — ONS attribution verified present in `/v1/score` `sources`, and verified in BOTH directions (absent before a lookup, present after), so the OGL v3.0 credit is served *and* still gated on the local tier having genuinely answered. It never needed an API key: importing the Lambda and calling `resolve_query()` exercises the identical path. **STILL OPEN, all user-side and now all gated on the AWS Support ticket:** log retention + orphan-group cleanup (**verified still ALL `None` on 27 Jul**), the IAM grants above, `git push` (**14 commits**, held because `SECURITY.md` describes the retention gap as open and the repo is public), Cloudflare CNAME, Migadu/DKIM, Gmail `/mcp` re-auth, Android Play Console. **NOT blocked:** `flightmap-dev` still deploys normally, so the free-tier quota change is shippable the moment the number is chosen.) — Previous review 2026-07-26 (**Backend DEPLOYED · signup funnel actually fixed, it took a second IAM fault · NSPL table live and empty.** (1) **`POST /v1/signup` returns 201, verified live — the 2.5-month outage is over.** The 25 Jul diagnosis was half-right: there were **two stacked IAM faults** and `878b09d` fixed only the downstream one, so the funnel still 503'd after the first deploy. The real first blocker: **API Gateway keeps tags at a separate resource path** (`/tags/{arn}`; TagResource is `PUT /tags/{arn}`), so `create_api_key(tags={...})` needs a grant on `arn:aws:apigateway:*::/tags/*` that the I-G hardening (`dab713d`) never added — `CreateApiKey` was denied before a key ever existed, meaning the `/apikeys` half had *never once* succeeded in production, exactly as the 25 Jul note predicted it might. Fixed by a second deploy with the condition retained (dropping it would let the Lambda tag anything in the account). **Generalisable lesson: granting a tag *condition* is not the same as granting the *tagging*.** (2) **Deployed:** NSPL `PostcodeTable` created (ACTIVE, empty — loader runs whenever, score Lambda is forward-compatible so no second deploy); throttles applied (`/epc` GET 3/6 new, batch 5/10 → 10/20, `GET /v1/score` 40/80 **now declared in source instead of console drift — that revert risk is permanently closed**); CORS + the 24/25 Jul fix waves live; no resource replacements. EPC token in `.env` verified still valid against MHCLG before deploying, so `/epc` did not regress. (3) **NEW OPERATIONAL BLOCKER — `/aws-debug` cannot function on this account.** `flightmap-dev` has *no* observability permissions: `logs:FilterLogEvents`/`GetLogEvents`/`DescribeLogStreams`, `cloudtrail:LookupEvents`, `iam:ListRoles`/`GetRolePolicy`, `lambda:ListFunctions`, `cloudformation:DescribeStackResource` all denied (the 25 Jul note claiming `iam:GetRolePolicy` works is wrong); `default` profile token is invalid. Root-causing therefore needed **side-effect elimination** — a failed signup leaves no API key and no orphan, which places the denial before key creation. Granting CloudWatch Logs read is a console action Bill must do; it would have turned this into one command. Memory: `reference-flightmap-dev-no-observability`. (4) **EPC auth-failure handling FIXED + deployed same day.** `lambdas/epc/app.py` branched on `401` for the graceful "token expired" degradation, but MHCLG returns **`403`** (confirmed with a control request) — that branch was unreachable, so an expired EPC token would have 502'd and broken the property page rather than quietly hiding the panel. Now handles both, and logs the rejection at ERROR with rotation instructions, because a graceful body is indistinguishable from "no data" and silent auth degradation is precisely how the signup funnel stayed dead for 2.5 months. 3 tests added (both codes degrade, 500 still 502s, 404 still means no-certificates); verified live (`N1 7SX` → 76 certificates). (5) Preflight green before deploy (122 backend + 140 root tests, ruff/HTML/ESLint clean, API-URL drift PASS); the one Prettier failure on `index.html` is byte-identical at `origin/master`, i.e. pre-existing baseline noise. (6) **Doc sweep found three materially wrong statements, all corrected.** (a) **`SECURITY.md` claimed "default 90-day" CloudWatch retention — it is actually UNLIMITED.** All 13 log groups read `retentionInDays: none` (*Never Expire*); Lambda-created groups have no default policy. This is a customer-facing trust document, and the signup Lambda logged **raw email addresses until 2026-07-23**, so that is personal data retained indefinitely while documented as expiring — a GDPR storage-limitation gap, not just stale prose. (b) `SECURITY.md` claimed per-Lambda `requirements.txt` files; there are none — every handler is stdlib + runtime boto3, so the backend has **no PyPI supply-chain surface** (which also makes the preflight skill's `pip-audit` step a no-op that reads as a green tick). (c) `OPERATIONS.md` §6's entire debugging recipe was unrunnable (told you to tail CloudWatch and run `/aws-debug`, all denied), its throttle figures were two deploys stale, and its CORS note contradicted the 24 Jul `CORS_ORIGIN: '*'` fix; §4 listed 3 DynamoDB tables (there are 4) and cross-referenced the wrong section for token rotation. **Also found: 6 orphaned log groups** for Lambdas deleted from the template (Chat, MultiAgent, AnalyzeImage, AnalyzeDocument, Report, LiveFlights) — deleting a function does not delete its logs.
(7) **NSPL LOAD COMPLETE — the local postcode tier is live.** Finished 20:28 BST: **2,699,393 written, 24,203 skipped, 904,453 terminated, 332,308 London, 0 spaced-form mismatches, 5.80 hours at ~129 rows/s.** Verified by ten `get-item` probes (never `ItemCount`, which read 0 throughout and refreshes ~6-hourly), including the loader's own boundary cases: `SW11 1AA`→Wandsworth, `E1 6AN`→City of London, `BR1 1HB`→Bromley `dt=198412 q=8`; controls confirm non-London rows carry no `b`. A `__META__` row records vintage/counts/OGL source. **postcodes.io is now the fallback, not the primary — the fair-use exposure that made a 100k-address customer backfill indefensible is closed.** The loader was also **~10× slower than its own docs claimed** and the fix is one IAM line: measured ~129 rows/s against a documented ~1,300/s / ~35 min. The old figure extrapolated linearly from the DEFRA loader and assumed per-item `PutItem` matches `BatchWriteItem`; neither held. The run is **client-CPU-bound** on 2.7M separate TLS + SigV4 handshakes, so raising `--workers` will not help. The loader uses per-item `PutItem` *only* because `dynamodb:BatchWriteItem` is not granted — **grant it in `backend/iam-policy.json` and switch `_flush_batch` before the August vintage roll** (~25× fewer round trips). Corrected in the loader docstring, `PROJECT_DOCUMENTATION.md`, the handoff runbook and memory.
(8) **The log-group remediation was reported done but verified NOT done, and it blocks the push.** All 13 groups unchanged — the Signup group's `creationTime` is still `2026-05-06 13:23`, which proves the delete never happened independently of any caching question (`describe-log-groups` is strongly consistent). **It is console-only: there are NO working admin credentials on this machine** — the `default` profile's key returns `InvalidClientTokenId` (deleted/deactivated, not a permissions error) and `flightmap` is deploy-scoped and cannot even read its own IAM user. No SSO, no role assumption, no `AWS_*` env vars. Memory: `reference-no-local-admin-aws-credentials`. **Consequence for the push: the repo is PUBLIC, and `SECURITY.md` currently describes the retention gap as OPEN**, so pushing publishes a written admission of a live GDPR exposure on a repo shown to investors. Bill chose "close it first, then the docs describe history" — precondition unmet, so the 11 commits were **deliberately left unpushed**. Full runbook in `HANDOFF_2026_07_26_deploy_day.md` §6.
**STILL OPEN, all user-side:** CloudWatch Logs **read** grant (new — blocks `/aws-debug` entirely), **log retention + orphan-group cleanup** (upgraded: unlimited retention on personal data, console-only, **attempted 26 Jul and did not take effect**), Cloudflare `CNAME api → d1pr4crjutz9z8.cloudfront.net` (**now safe — the `sw.js` unstranding fix is live**), `dynamodb:BatchWriteItem` grant before the next NSPL roll, `git push`, Migadu/DKIM, Gmail `/mcp` re-auth, Android Play Console. ~~`dynamodb:DeleteTable` grant or `DeletionPolicy: Retain`~~ **DONE** — Retain on all four tables. **NSPL load finished 2026-07-26 20:28 — table fully populated, nothing further needed until the August vintage roll.**) — Previous review 2026-07-25 (**Signup funnel found dead since 7 May · 18 of 19 audit leads confirmed · NSPL postcode independence shipped to source.** (1) **CRITICAL, live since `dab713d` 2026-05-07: `POST /v1/signup` returned 503 to every visitor.** One IAM statement gated `apigateway:POST` on both `/apikeys` and `/usageplans/*/keys` behind `aws:RequestTag/CreatedBy`, but `CreateUsagePlanKey` accepts no tags, so the condition could never match. An audit I-G hardening silently broke the feature it protected. Verified against the DEPLOYED role policy. Zero customer cost (no orphan keys, signups table holds 1 pre-regression row = nobody tried), but the whole Free → £499 ladder was a dead end during the Haatch commercial-proof window. Fixed in `878b09d`; **needs one live `POST /v1/signup` returning 201 after deploy** — the `/apikeys` half of that condition has also never succeeded in production. Root cause of the duration: no 201 happy-path test existed. Now it does. (2) **The 25 spend-limit-stranded audit leads re-verified: 18 of 19 confirmed**, verifiers instructed to default to refuted. Finders got mechanism right / consequence wrong almost every time; one was under-rated ("orphan key leak" → dead funnel). Fixed same day: signup IAM split, `GET /epc` throttle 3/6 (it was an unauthenticated proxy onto a bearer-token MHCLG upstream with no per-method limit), favourites input validation, `createdAt` dropped from the 409, EPC panel no longer hangs on "Loading" forever. (3) **Near-miss:** `MethodSettings` declared `GET /v1/score` twice — the 24 Jul soak fix at 40/80 and a stale audit I-D pair at 5/10 BELOW it. CFN renders last-wins, so the soak fix was never active and the live 40 rps was console drift; the next deploy would have cut the primary paid route 8×. Duplicates removed. Same add-above-instead-of-edit anti-pattern also found in the site CSS (`.search-hint` 11px a11y bump has never rendered). Memory: `feedback-cfn-methodsettings-last-wins`. (4) **NSPL local postcode resolution shipped to source** (`ebd6abf`, undeployed): 2,699,393 ONS rows into DynamoDB, postcodes.io demoted to fallback, removing the fair-use problem that made a 100k-address customer backfill indefensible. Forward-compatible (empty table = identical behaviour, upgrades silently). Three adversarial passes, each catching the previous one's collateral. The offline city-scale bulk scorer — the Enterprise "score your whole city" deliverable and the second consumer of this table — is **NOT built yet**. (5) **Commercial exposure, decision still open:** APIGW meters requests not results and `MAX_BATCH_SIZE=100`, so the advertised 1,000-req/month free tier is really **100,000 scores/month = Professional's entire £499 allowance**. £0 leaked. Must be decided before Professional launches (same mechanism makes that tier 10M scores/month). The "1,000 requests" figure appears on 5 surfaces: `pricing.html:244`, `api/index.html:291`, `README.md:74`, `score-demo/index.html:372`, `METHODOLOGY.md:733`. (6) Preflight green (0 ESLint errors, HTML/Prettier/ruff clean, 257 tests, API-URL drift PASS). **STILL OPEN, all user-side:** EPC token rotation (gates every backend change), `dynamodb:DeleteTable` grant on `london-flight-map-*` or `DeletionPolicy: Retain` — **without it a failed update wedges the live stack in `UPDATE_ROLLBACK_FAILED` and `flightmap-dev` cannot self-recover** — then deploy + verify signup, plus the unchanged Cloudflare CNAME, log-retention click, Gmail `/mcp` re-auth and Migadu/DKIM. **FRONTEND BATCH IN FLIGHT** (deploys via CloudFront independently of the above): search-flow request sequencing (live-reproduced showing SW11 EPC + sold-price data under a TW3 heading — wrong data, terminal state), `sw.js` cache-first stranding installed PWAs on a stale `js/api-base.js` (**must land BEFORE the `api.skyscore.co.uk` CNAME swap; afterwards is too late for anyone installed**), `switchCity` re-entrancy, resize debounce + D3 transition interrupt, verdict contrast 1.16:1 vs a 4.5:1 requirement, `.search-hint` duplicate, score-demo sequencing.) — Previous review 2026-07-24 (**Claude-side backlog cleared: test rewrite + I4/I6/I14 closed + full audit (1 live critical found) + pilot outreach pack.** (1) The 21 stale legacy tests rewritten to the current handler contracts (MHCLG EPC JSON API, X-Device-Token auth, OSM Overpass) — 83 root + 62 backend tests green at the time, both suites now gate CI. **Current split as of the NSPL local-postcode-resolution build: 108 root + 91 backend = 199.** (2) The standing audit trio closed: I4 resolved by removal (score/app.py is the single borough-metadata holder), I6 moot (all 7 Lambdas APIGW-synchronous), I14 done (PROJECT_DOCUMENTATION.md fully refreshed — it had the removed AI endpoints listed as live and the /v1/* product endpoints missing entirely). (3) **Full 6-dimension audit with adversarial verification — found and manually verified a live critical, A-0724-C1: `CORS_ORIGIN` pinned to the legacy CloudFront URL has been silently breaking all five consumer data panels (epc / favourites / nhs / sold-prices / transport) on skyscore.co.uk since the domain went canonical in May** — every panel degrades to its fallback state, which is why it went unnoticed; score ('*') and signup (own allow-list) were unaffected, so the B2B demo kept working. Source-fixed in `template.yaml` (Globals → '*'); **the fix deploys with the already-pending EPC-token `sam deploy`**. Beyond the critical: 34 confirmed findings (11 important — sw.js offline-shell cache poisoning, status.html burning the demo key's monthly quota at ~300 req/hr, £NaNK NYC demo render, batch-vs-timeout, transport silent failure, mobile-web footer unreachable ≤900px, 5 a11y) and 25 unverified leads — the verification agents died when the account's **monthly Claude spend limit** hit mid-run; re-verify when it resets. Full detail: `AUDIT_REPORT.md` §2026-07-24. (4) **Pilot outreach pack complete against the Haatch commercial-proof gate:** LOI template created at `Desktop/SKY_SCORE_LOI_TEMPLATE.md` (non-binding + confidentiality carve-out that lets the pilot's existence be cited to investors; kept out of the public repo with the one-pager), pilot-first email variants (Tier 1 + Tier 2 + LinkedIn DM) added to `OUTREACH_DRAFTS.md`, one-pager internal notes refreshed (support@ resolved). Send gates: Migadu/DKIM before any domain cold email; incorporate before the first kickoff invoice. (5) **Same-day fix wave: 18 of the audit's findings closed** — frontend fixes (sw.js, status.html quota, score-demo NYC, mobile footer, a11y/CSP batch) deployed to CloudFront; backend fixes (transport honesty, epc timeouts, batch headroom, weight bounds) source-only and riding the pending `sam deploy`. 152 tests green. (6) **Pushed to origin 2026-07-24 (user-authorised):** the 12-commit backlog (trust-fix session record → audit day → fix wave) is on GitHub; local and origin are level. Claude also re-verified the remaining pending items are genuinely not CLI-reachable: no Cloudflare credentials exist on this machine (CNAME + DKIM records are dashboard-only), `logs:PutRetentionPolicy` is cleanly denied for flightmap-dev (re-tested via PowerShell to rule out the Git-Bash path-mangling false negative; the user also has no `iam:` read so cannot self-amend), and the Gmail connector authenticates via `/mcp` → "claude.ai Gmail" in the CLI. (7) **Evening (user-directed): backend DEPLOYED twice, methodology v3.2 live, 100k soak run.** First deploy shipped the CORS critical (consumer data panels verified working from skyscore.co.uk again), 28s batch timeout, stage throttle, fix wave. The 118,501-request soak still measured 5 successful req/s — exposing the TRUE ceiling: **console-set per-method throttles (5 rps) on both revenue routes, present in no template** (CFN merges but never removes undeclared stage settings). Second deploy: routes declared in template (40/80, 10/20; batch needed a manual update-stage patch) + **methodology v3.2** — quarterly HPI check found 28/33 boroughs ≥3% adrift, all refreshed to May-2026 UKHPI in both engines, and the growth formula clamped to 0-10 (negative trends had produced sub-zero scores; 18 borough scores move >0.5, changelog is the notice record — zero customers). Post-fix verified live: 39.4 successful req/s (8×), 15/15 concurrent cold batches (was 6/15), free-tier throttle exact, v3.2 serving. Full story: AUDIT_REPORT addenda + `Desktop/SKY_SCORE_STRESS_TEST_2026-07-24_FULL.xlsx`. (8) **Night: TRENDS FEATURE SHIPPED end-to-end** (user-directed) — `?compare=previous` on `/v1/score` (previous vintage embedded, rescored under current formula; NYC honestly zero), public keyless `GET /v1/changes` (33 boroughs sorted by movement: 6 risers / 25 fallers / 18 moved >0.5, largest fall Barking & Dagenham 9.0→7.4), and the shareable **`/changes` "What changed this quarter" page** linked from both site footers. OpenAPI + Makefile + CLAUDE.md runbooks updated; 159 tests green; deployed + verified live. Turns the quarterly refresh into the product's heartbeat; Tier 3 (portfolio alerts/webhooks — "tell me when my book moves") deliberately deferred to post-pilot. Load harness now persists per-request CSV (`tests/loadtest.mjs`), demonstrated with a 1,736-row clean capture on the Desktop. First Aini-update item is ready-made. **STILL OPEN (all user-side):** EPC token rotation (deploys reused the old token — update `.env`, one redeploy; next session per Bill), Cloudflare `CNAME api → d1pr4crjutz9z8.cloudfront.net` (DNS only / grey cloud), signup log-retention console click, Gmail `/mcp` re-auth, Migadu/DKIM before cold outreach. **NEXT-SESSION BUILD QUEUE (agreed 24 Jul, late):** (a) EPC rotation first; (b) 1,000-postcode × 8-persona results matrix via batch (~80 calls — all-distinct rows, fair use of postcodes.io); (c) **UPGRADED (24 Jul, night): the NSPL postcode table — one build serving both offline and live.** Load NSPL (postcode → borough + lat/lon; ONS, OGL; already on disk in `data/`) into a DynamoDB table alongside the raster table (~2.5M tiny rows, pennies/month), then: the score Lambda resolves postcodes **locally in ms** (postcodes.io demoted to fallback — removes the free-community-service dependency that makes a customer's 100k-distinct-postcode backfill unfair use today), AND the offline city-scale scorer reads the same table to produce the Enterprise "score your whole book / whole city" CSV (the pilot demo artefact + the managed-first-load sales motion: run the customer's book FOR them in the pilot). Context: a 100k-request dump over the 22-location test pool would be 176 distinct answers repeated ~570× — volume is proven (118k soak); *distinct coverage* is what scales the artefact. **Pricing decision before Professional launches:** batch metering currently counts CALLS (100k scores = 1,000 requests against quota — customer-generous); decide deliberately whether Professional meters per-call or per-score.) — Previous review 2026-07-23 (**Haatch warm pass → freeze lifted → trust-fix bundle SHIPPED + deployed.** Aini Hashim (Haatch) replied 23 Jul: solo build "compelling", regulatory timing right, but progress needs **commercial proof — a signed pilot or LOI plus outcome evidence**; thread parked warm on the investor-update list. All eight brief changes shipped to production same day: **`/pricing`** (90-day £2,500 + VAT pilot — day-0 metric, day-45 review, day-90 written evidence report, fee credited in full against first-year licence; Free tier live; **Professional £499/mo "Launching"** — user decision 23 Jul, replacing the £49 proposal to keep the pilot/licence ladder coherent; Enterprise POA; founder block; GoatCounter events on every CTA); founder/contact identity in the site footer + `/api/` + privacy §1; App Store footer link (v1.0.21); signup privacy notice + **privacy.html §2a corrected** (it flatly denied the signup form existed — now documents purpose/lawful basis/storage incl. APIGW key metadata/retention/deletion) + Play-rating claim removed; DEFRA **Round-4-is-latest** note (site legend + METHODOLOGY §7); air-quality AND flood detail badges → "borough-level rating (curated)"; **support@skyscore.co.uk** replaces gmail on every public surface (incl. security.txt, robots.txt, /api/ JSON-LD, SUPPORT/SUBPROCESSORS); api-docs **Swagger self-hosted** (removes the unpkg SRI single-point-of-failure that could blank the page; hashes verified); **GoatCounter CSP fix** — the count beacon (connect-src) and img fallback (img-src) were blocked on every page, so funnel events likely never recorded; now allowed on all five pages. Backend deployed: signup Lambda no longer logs raw emails; 30-day log retention pending a console click (flightmap-dev lacks `logs:PutRetentionPolicy`; CFN can't adopt the auto-created group — IaC import is a follow-up). **CI un-broken** — red on every push since 18 May (stale chat e2e specs, 8-vs-7 toggle count, root pytest dying at collection on the removed chat Lambda, ruff-format drift); now green: e2e specs fixed, CI gates on `backend/tests`, lambdas ruff-formatted; the legacy root suite's 21 stale tests (epc/favourites/nhs) need a triage session. **api.skyscore.co.uk AWS side live** (edge custom domain + base-path mapping → prod, us-east-1 wildcard cert; created 2026-07-23) — pending Bill's Cloudflare record `CNAME api → d1pr4crjutz9z8.cloudfront.net` (DNS only/grey cloud), then swap the raw execute-api URLs out of METHODOLOGY.md (+ /api/ curl sample + openapi.yaml servers as follow-up). **Livability convention resolved: keep** US "livability" in brand phrases/metadata, British "Liveability" as the score component — deck already mirrors site. Consumers stay free (23 Jul decision). **STILL OPEN:** EPC token rotation (`.env` untouched since 7 May despite in-session "rotated" answer — live EPC works, so the old token remains valid and exposed; oldest security item), signup log-group retention click, Cloudflare CNAME, Gmail MCP re-auth for an end-to-end support@ delivery test, `git push` (local master is ahead), Migadu/DKIM before cold outreach from the domain. `samconfig.toml` regenerated locally via `--save-params` (it never migrated from the OneDrive clone).) — Previous review 2026-07-19 (**Pre-investor-call freeze + trust-fix bundle staged.** Deck sent to Haatch (Aini Hashim) Fri 17 Jul; catch-up call Mon 20 Jul. **No site deploys until after the call** — the deck-site sync certified 17 Jul is an asset; weekend deploys risk screenshot mismatch, partial CDN cache invalidation, and scramble optics. A 5-agent ground-truth audit (19 Jul) found: the site is anonymous (no founder/entity/contact anywhere — top B2B trust gap); the API-key signup form has no privacy notice; the API reference page renders nearly empty to visitors; METHODOLOGY.md exposes the raw execute-api URL; the DEFRA "Round 4, 2022" citation has no on-site "latest official round" note; the iOS listing (apps.apple.com/gb/app/sky-score/id6768118116, v1.0.21) is live but never linked from the site; **Android is confirmed NOT on the Play Store** (AAB stale vs master; the Play Console flow in `HANDOFF_2026_05_16_play_submission.md` was never completed); the air-quality layer is real but borough-static (`data/borough-extra.json` fills; WMS/ArcGIS configs are dead code; the detail-panel "DEFRA DATA" badge overstates). **Post-call trust-fix bundle (target Tue 21 Jul, shaped by investor feedback):** founder/about + contact line; App Store footer link; signup privacy notice; DEFRA Round-4-is-latest sentence (+ METHODOLOGY echo); API reference rendering fix; api.skyscore.co.uk subdomain; livability/liveability decision; pricing page LAST and only after Haatch input. **EPC bearer-token rotation still pending (flagged since May) — do this week.** Housekeeping: March-era prototype artefacts archived at `archive/prototype-2026-03/` (original `london_flight_paths.py`/`.html`, March samconfig, old `.claude/commands`); the `Sky Score.bat` launcher now points at this canonical clone (was still launching the deprecated OneDrive copy); 4 fastlane ASC vars pending merge into `.env` from the old OneDrive clone before it is deleted.) — Previous review 2026-05-29 (**Web/native split — the mobile redesign is now native-app only.** Per user decision, the live website reverts to its classic pre-redesign bottom-sheet mobile layout while the iOS/Android apps keep the v2 bottom-nav redesign. Implemented as a single `is-native` class on `<html>` (added only by `setupNativeFeatures()` inside Capacitor) that gates the redesign's base CSS (`.is-native .mobile-nav`, `.is-native .app > #map-container`/`.sidebar`, `.is-native .sheet-handle`, `.is-native .sidebar > .tab-bar`) plus the `setMobileView()` JS guard; `revealSheetIfMobile()` branches native→`setMobileView('search')`, web→classic `setSheetState('open')`. One file, no fork — the classic layout was still fully present because v1/v2 were additive (they removed only the viewport-meta line + one `setSheetState` call). Verified locally via `tests/native-sim-render.mjs` (native sim → redesign; web mobile → classic, no nav, sheet handle present, zero overflow; desktop 1440px → two-column grid). `tests/live-mobile-verify.mjs` re-pointed to assert the classic layout on live (post-deploy gate). **Then shipped the same day:** deployed the reverted `index.html` to CloudFront + verified the live web serves the classic layout (360/390/414, post-deploy gate green); committed (`3945226`) + store-copy fix (`4af9bc5`), pushed to origin, both clones synced. **iOS `1.0.21` (build 21)** — the native redesign, iPhone-only, built via Codemagic from `4af9bc5` — was **submitted for App Store review on 2026-05-29 (Waiting for Review)**; screenshots regenerated at 1242×2688, store copy reworded to the 3-tab design. Android native build still pending. See `MOBILE_REDESIGN_PLAN.md` v3.) — Previous review 2026-05-28 (**Mobile redesign v2 — map background + 3 tabs.** Iterated on the 2026-05-22 Option A build after the search tab landed too blank on first load. Collapsed Search and Map into a single tab so new users see the map immediately, with a floating search card pinned top-left, a compact LONDON/NEW YORK chip top-right, the App Store 4.2 locate button surviving as a FAB, and a `×` close button on the result card that restores the empty-state via safe DOM cloning (`cloneNode` + `replaceChildren`, no `innerHTML`). Two specificity gotchas captured in `MOBILE_REDESIGN_PLAN.md` v2 section: `switchTab()`'s inline `style.display='block'` beats external CSS (needed `!important`), and base `display:none` requires every state-rule to re-assert display explicitly. Verified via `tests/native-sim-render.mjs` (3 nav tabs, map foregrounded on Search, hidden on Rankings/Saved, no overflow at iPhone-13). Desktop 1440px unchanged. **Code complete in canonical clone, NOT yet pushed/deployed** — `git push` + CloudFront `index.html` invalidation + Android rebuild + Codemagic iOS build remain.) — Previous review 2026-05-22 (**Mobile redesign shipped to web — Option A bottom-nav, search-first.** Reworked the mobile UI from a desktop-map-in-a-bottom-sheet into four full-screen views (Search / Map / Rankings / Saved) driven by a fixed bottom nav, with `viewport-fit=cover` + safe-area insets, and a fix for the PWA install prompt leaking into the native app — its root cause was the `[hidden]` attribute being silently overridden by explicit `display`. **Deployed live to CloudFront + verified across 360/390/414 phone widths (zero horizontal overflow); desktop layout untouched.** Committed in the canonical clone as `78aea08` (redesign) + `a0e518b` (store release notes + Windows `build:android` `gradlew.bat` fix) — **awaiting `git push` + iOS resubmission + Android rebuild** (these are user-only: push rule, Apple 2FA, keystore password in Bitwarden). Plan + reusable verification harness: `MOBILE_REDESIGN_PLAN.md`, `tests/native-sim-render.mjs`. Memory: `project_mobile_redesign_option_a.md`, `feedback_hidden_attr_display_footgun.md`, `feedback_build_android_windows_gradlew.md`. — Previous review 2026-05-21: **iOS v1.0 LIVE on the App Store as of 2026-05-20** — build 20 with the Wave 13.20 iPad Guideline 4.0 fix was approved, closing the 2026-05-12 → 2026-05-20 rejection arc. Public: apps.apple.com/gb/app/sky-score/id6768118116. Android AAB still stale relative to master — rebuild before Play upload. skyscore.co.uk email forwarding still to set up — `support@` declared in App Review notes + privacy policy. Previous review 2026-05-18 EOD (Wave 13.20 — build 19 rejected on iPad layout, fix shipped + build 20 resubmitted same day).

iOS side: Build 19 is the first successful build under the persisted-cert pipeline (orange radar icon, signed by persistent Distribution cert public-key SHA256 `c680ad18...805934`). Attached to v1.0.1 in ASC, submitted for review. The arc from 13.16 → 13.18.1 took three failed builds: 13.17 base64-in-env-var (corrupted in clip.exe→textarea transit), 13.18 raw PEM (dashboard Edit on a Secure var didn't persist the value due to a Codemagic UI quirk), 13.18.1 added length-diagnostic + delete-and-recreate. Eight distinct failure modes resolved.

Android side: keystore generated at `~/.keystores/sky-score-release.jks` (upload-key SHA-256 `A5:53:4A:8F...:22:50:AB`), `mobile/android/app/build.gradle` wired for env-var-driven signing (force-tracked because `/android/` is gitignored), gradle bundleRelease produced a signed 3.6 MB AAB at `mobile/android/app/build/outputs/bundle/release/app-release.aab`. Three Play Store screenshots auto-generated at 1080×1920 via Playwright + Chromium (`tests/android-screenshots.mjs` hides PWA install prompts to match the native app's runtime view), feature graphic 1024×500 auto-rendered (`tests/android-feature-graphic.mjs`). Fastlane metadata at `mobile/fastlane/metadata/android/en-GB/` pre-populated. AAB is ready for manual Play Console upload (Internal track → Production); Play review typically <24h. Forensic trail in `memory/feedback_codemagic_personal_account_signing.md` (iOS), `memory/project_android_keystore.md` (Android keystore facts), `HANDOFF_2026_05_14_icon_ship.md` (icon arc).)

---

- **`EXPANSION.md`** (new 2026-08-11): which cities and countries are reachable and what each costs, ranked on measured 2025 transaction volume. The key finding is that the NATION is the unit of work, not the city: every source behind an English city-region is already national, so England is nearly free, while Wales loses schools/road/flood to different publishers and Scotland changes publisher for five of six components.

## Vision

Sky Score is the noise + livability layer for UK property data, designed to be honest about hidden harms (aviation noise, road noise, air quality, crime) that listings sites have a financial incentive to hide. Two surfaces: a consumer site that informs renters/buyers, and a B2B API that puts the same data inside the workflows of conveyancers, property data aggregators, and Islamic-finance providers. Aligned with Maqasid al-Shariah (protecting buyers from harm) and explicitly riba-free in customer targeting.

## Current state

- **Consumer site live**: `https://skyscore.co.uk`, covers London + NYC, postcode/borough scoring, favourites, NHS/transport/EPC/sold-prices data lookups
- **Backend**: **8 active Lambdas** behind API Gateway at `https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/`. The 5 dormant Bedrock functions built for the original hackathon are **not in `template.yaml`** — code and template entries live in git history only, so reviving one means restoring both, redeploying, then unhiding the UI block. (Corrected 2026-07-29 from "8 active + 5 dormant" to 7; corrected again 2026-08-22 to **8**, by counting `AWS::Serverless::Function` blocks rather than trusting the prose - `ChatFunction` was restored to the template on 2026-08-06 as a retrieval-only function and this line never caught up. The eight: Score, Chat, Signup, Favourites, Epc, SoldPrices, Transport, Nhs.)
- **Prototype (Sky Score Radar)** live at `/prototype/`, 3D visualisation with simulated flight tracks (live OpenSky data removed 2026-05-07 pending licensing — see open decisions table)
- **Recent wins**: Amazon Nova hackathon ($200 AWS credits, blog category), Emergent Ventures application submitted (awaiting response), Red Bull Basement application submitted (awaiting shortlist), Luma event applied
- **Known issues**: see **`AUDIT_REPORT_2026-09-11.md`** - the current list. **Last full audit 2026-09-11** (4 fixed: the panel's `undefined` on 53 of 91 boroughs, two gates that could not fail, and `env` missing from the bulk CSV; **5 criticals open, four of them one mechanism - a mirror left behind by a version bump**). `AUDIT_REPORT.md` still holds the 2026-09-07 list and was deliberately not rotated. Older: **2026-08-21** (not 07-24, as this line said until 2026-08-22 - there have been three since). All 11 criticals closed 21 Aug; **10 of 14 Important and 10 Minor closed and deployed 22 Aug**. ~~Open: I1~~ **I1 CLOSED 2026-09-11 as won't-fix** - both routes stay unauthenticated because their consumers are public pages and a blocking preflight gate, the same argument that keeps `/v1/environment` open; re-measured live that day, both answer 200 with no key. Still open: **only** the `ReservedConcurrentExecutions` half of I3 - **re-probed 2026-09-11 and still genuinely blocked**: `lambda:GetAccountSettings` returns `AccessDeniedException` for `flightmap-dev` even after the 4 Sep policy restore, so the reserve cannot be sized from here. (Probed rather than assumed, because that claim pre-dates the restore and two sibling claims checked the same day turned out to be stale.) ~~and I6~~ - **I6 was closed 2026-09-07** by the blocking `worked example reproduces` gate, and re-verified against the live API on 2026-09-11; it had been listed as open here, in `CLAUDE.md` and in `AUDIT_REPORT.md` while the table five sections down already recorded it closed.

## Constraints

These shape every product decision:

- **Riba-free**: don't target conventional banks, mortgage lenders, or general insurers. Target aggregators (data companies, no riba issue), Islamic finance providers (Al Rayan / StrideUp / Gatehouse), conveyancers, surveyors, B2R operators, public bodies. (Memory: `feedback_no_riba_customers.md`.)
- **No conventional insurance bought** (Bill, 2026-10-06), for the same reason: no professional indemnity policy. Prefer data-supplier contracts with a liability cap, a company reserve, and takaful only if Bill's scholar approves a product (OUTREACH_TARGETS.md "Without conventional insurance").
- **Estate agents are misaligned, not target**: their incentive is to push sales through, not inform buyers. (Memory: `project_api_target_customers.md`.)
- **Dual-model channel wall**: consumer site = borough-level free; API = per-property paid. Avoid undercutting paying integrators. (See "Track 1" below.)
- **British English everywhere**: code comments, UI text, docs, commits. (See user CLAUDE.md.)

---

## Three parallel tracks

### Track 1, Consumer site (`skyscore.co.uk`)

The consumer site is the marketing engine, not the revenue centre. Keep it sharp; don't compete with the paid API.

**Active work**:
- Down-grade per-property data display to borough-level only (granularity wall, protects API customers)
- Sharpen the "ethical alternative to listings sites" framing in copy
- ✅ Mobile UX pass (2026-05-22, iterated 2026-05-28 to v2 map-overlay + 3 tabs + result-close button) — see `MOBILE_REDESIGN_PLAN.md`. **2026-05-29 web/native split: the redesign is now native-app only (gated behind `is-native`); the website reverts to the classic bottom-sheet layout.** Deployed live + verified; iOS `1.0.21` (build 21) submitted for App Store review 2026-05-29 (Waiting for Review); Android native build pending.

**Deferred**:
- Authentication for favourites endpoint (post-hackathon item from `AUDIT_REPORT.md`)
- ARIA accessibility pass (post-hackathon item)

### Track 2, B2B API (`/v1/score`, `/v1/score/batch`)

The product. Wraps the scoring engine into a stable, documented, monetisable endpoint for aggregators and Islamic-finance providers.

**Shipped (2026-05-05)**:
- ✅ `GET /v1/score`, single-postcode (London) or borough (London + NYC) lookup with persona presets and custom weights override
- ✅ `POST /v1/score/batch`, bulk endpoint, up to 100 queries per call, partial-failure-tolerant (failed items return error per-row)
- ✅ API key auth via API Gateway Usage Plan (1000 req/month free tier, 5/sec burst, 2/sec sustained)
- ✅ Methodology v2.0, every threshold and weight anchored to DEFRA Lden bands, WHO noise guidelines, Ofsted distribution, ONS crime medians, TfL PTAL; references section
- ✅ OpenAPI 3.0 spec at `/score-demo/openapi.yaml` + interactive Swagger UI at `/score-demo/api-docs.html`
- ✅ NYC support, borough-name lookup + 5-digit US ZIP auto-detection. ~182 residential ZIPs covered across all 5 boroughs; ~110 of those have per-ZIP centroids that drive the v3.0 Haversine quiet-score path (verified live 2026-05-06: 10001 Manhattan → score 5.0 / postcode-resolution, 11201 Brooklyn → 6.9 / postcode-resolution, 11375 Forest Hills → 6.0 / postcode-resolution). Non-NYC US ZIPs (e.g. 90210) return a structured 404 with the supported borough list.
- ✅ Per-postcode quiet score, v3.0 Haversine to airports + flight-path geometry, applied to both UK postcodes (postcodes.io centroid) and NYC ZIPs (static centroid lookup). v3.1 raster scaffold present in code (DynamoDB lookup) for once the offline DEFRA loader runs.
- ✅ CORS opened to `*` so third-party browser integrations work; abuse vector unchanged (server-side abuse was always possible regardless)
- ✅ OGL attribution in every response

**Outstanding**:
- ✅ **DEFRA Lden raster offline data-load COMPLETE** (`scripts/load_defra_raster.py`). Final run finished 2026-05-07: **423,481 postcodes written** (England-bbox subset of the ~2.5M NSPL list; 2.3M skipped as Scotland / NI / sea / out-of-bbox). v2 below-threshold sentinel verified live for TW1 1RR (Twickenham), SW19 1AA (Wimbledon), NW3 1AA (Hampstead) — all return `quietResolution: raster` with sentinel-quiet 10/10 despite their borough aggregate being "high"/"low-moderate"/"low". TW6 2GA (Heathrow village) returns the real Lden raster value with quiet 5/10. The "borough aggregate vs per-postcode reality" gap that motivated v3.1 is now closed for in-bbox postcodes; outside-bbox postcodes correctly fall through to v3.0 Haversine.
- 🟡 DEFRA full-UK extension (Birmingham, Manchester, Bristol, Leeds, Edinburgh, Glasgow), per-city WCS fetches against the same dataset; ~30-60 min of fetch+load per city. Trigger when first paying integrator asks for a non-London region.
- 🟡 UK Core Cities (Manchester, Birmingham, Bristol, etc.), geographic expansion, gated on liveability data acquisition
- 🟡 Pricing tiers beyond free — **public page shipped 2026-07-23** (`/pricing`: Free live, Professional £499/mo "Launching", Enterprise POA, 90-day £2,500 pilot). Contracts/billing still to define when the first paying integrator commits; £12k/yr licence floor stays verbal.
- 🟡 Status page at `status.skyscore.com`

### Track 3, Competitions & outreach

**Buildathon**: over (event was 2026-06-07). Plan archived at `archive/BUILDATHON_PLAN_2026.md` on 2026-08-24; this line had still called it the active focus 78 days later.

**Pending applications**:
- **Makerversity "Makers with a Mission"** (submitted 2026-10-01): six months' free membership - desk, workshops, community, business support, public showcase; 20 places a year. Pitch and answers in CLAUDE.md "Submissions".
- ~~**Deep Tech London Expo, 8 Oct 2026, Shoreditch**~~ **DECLINED 2026-09-29** (hardware-only floor). (drafted 2026-09-28; Bill to submit at `deeptech.london/expo`). Free table if no round raised - Cubitt33 has raised nothing, no grants; the table includes 3 tickets and needs a founder there all day. Fit is the weak point (the floor is hardware and hard science), so the pitch leads with the open government science data and the lockdown noise-map finding, in plain English. Answers at `OneDrive/Desktop/deep-tech-london-expo-2026-10-08-form.txt`; black-and-white logos (wordmark as outlines, Geist Bold) at `OneDrive/Desktop/sky-score-logo-bw.svg` and `-mark-bw.svg`, generated from `mobile/assets/logo.svg`. **Open: the ringed mark reads as a CROSSHAIR in flat black** - a tick-free variant is offered, not made. Their page still says "hear back before September", so free places may be gone.
- Emergent Ventures / Mercatus (£45k, submitted 2026-04-20, expect response within ~1 week of submission, chase if no reply by 2026-05-12)
- Red Bull Basement (submitted 2026-04-12, awaiting shortlist)

**Assessed and not pursued** (so they are not re-assessed from scratch):
- **Innovate UK's autumn 2026 AI calls, assessed 2026-10-07.** (1) *Frontier AI: SME Champions,
  Phase 1* (closes 11 Nov): its fourth theme, "AI Safety and Assurance: runtime control, dynamic
  evaluation, formal verification, adversarial testing", describes the `/v1/chat` grounding
  check, but eligible costs are GBP 150k-250k in a 1-3 month project with no subcontractors, at
  up to 70% funding: GBP 45k-75k of match cash and GBP 50k+ a month of one founder's costs, for an
  AI-assurance R&D project that is not Sky Score's product. Revisit with a co-founder or investor.
  (2) *Efficient, Structured and Controllable AI Systems* (18 Nov): for new underlying AI
  technology; Sky Score uses public data, not novel AI. (3) *BridgeAI Deployment Catalyst*
  (8 Dec, official page not found; provisional): needs an existing AI solution scaled with a
  financial or professional-services partner. Recasting Sky Score as an AI product to fit it
  would undo the data-first positioning; the one honest angle is a conveyancing firm under its
  Assurance and Compliance strand. A conventional bank or insurer partner conflicts with
  Constraints (riba-free); grants are fine, Innovate UK LOANS are not. Better fits: the next
  Geovation Accelerator intake, and non-AI geospatial or environmental calls.

**Outreach pipeline**, running from week of 2026-05-12 onward:

| Tier | Companies | Approach | Cadence |
|---|---|---|---|
| 1, Aggregators | Landmark, TM Group, OneSearch Direct | LinkedIn → cold email; reference Riskview/Plansearch gap | 2/week |
| 2, Islamic finance | Al Rayan, StrideUp, Gatehouse, Nester, Yielders | LinkedIn (founder-direct for StrideUp); aligned-values angle | 2/week |
| 3, Direct enterprise | Wahed, Manzilanas, B2R operators | Warm intros only | as found |

Track replies in `OUTREACH_LOG.md` (create when first reply lands). Each entry: contact, date, channel, response, next action.

---

## Near-term task list (next 4 weeks)

### WHERE WE ARE (2026-10-06, evening)

| | Item | State |
|---|---|---|
| 1 | Front-page polish batch: "Bay Area" out of the top bar, "Or explore the map", "Full map" as the bar's button, pricing tier cards, the free report ON SCREEN ONLY, Cubitt33 off the marketing pages, the phone route-tooltip fix | **DEPLOYED 6 Oct, verified live** |
| 2 | Bay Area arrivals on the FRONT page | **DEPLOYED 7 Oct (`eace052`), verified live: 16/36/35 drawn from the file, drift 37 data files**: `data/us-bayarea-routes.json` (16 finals, 36 departures, 35 arrivals, FAA cycle 2610) from `route_records()`, the one derivation for it and the live map block; the front page draws every record and nothing from the raw FAA record (gated in `tests/front-page.mjs`, proven red: the old drawing gave 0 arrivals and 29 whole departures). Was: Next. One generated routes file (`data/us-bayarea-routes.json` from `build_bayarea_map_data.py`) that the front page reads instead of re-deriving lines, so all three surfaces draw the same geometry |
| 3 | `/api/` and `/pricing` bodies in the new design | **Done 6 Oct (moved ahead of 2).** Both light, grouped by buyer. **Council ladder (Bill): area study from GBP 750 and the 90-day pilot at GBP 2,500 PUBLISHED, the annual licence ON REQUEST** (priced to the authority after a pilot; licence figures stay off every public page and out of this public file). A council card on `/reports/` too. Every price shown twice carries one `data-price` key and `tests/front-page.mjs` 16b reds if a key reads two ways across `/pricing`, `/reports/` and `/api/` (proven red). `/api/`'s JSON-LD no longer claims "GDPR-compliant UK data residency" (`/v1/chat` calls us-east-1); it says where it is hosted |
| 3+ | **Same evening, Bill's three rulings, built and gated:** (1) **top bar**: the page you are on is an UNDERLINE (#d35a12, 3.61:1; brand orange is 2.44:1, under the 3:1 a state cue needs), Full map an OUTLINED button, Pricing in the bar on every page incl. the 103 generated ones; (2) **ONE pricing page**: every price on `/pricing` (report tiers moved there as `#reports`), `/reports/` states none; (3) **the free report is protected**: a watermark ("Personal use only · postcode · date"), a reference that hashes the figures + postcode + day, a check link and QR code (`?postcode=&made=&ref=` re-makes the report and says whether the reference matches, or that the figures moved or the copy was changed), and the terms line (section 4 already limits free use to personal, non-commercial). QR from vendored qrcode-generator 2.0.4 (MIT, audited), DECODED by OpenCV in `tests/front-page.mjs`. Found doing it: the report frame was measured once, before the web fonts arrived, so its foot was clipped (9 px; the check block landed there) - it now refits as the body resizes. All proven red | **DEPLOYED 6 Oct, verified live** |
| 3t | **Nearest station shown, not scored** (Bill, 6 Oct: "would it not be wise to include close to stations as part of the score?" -> "show it first"). Front-page answer + street reports, one function `nearestStation()`, silent beyond 3 km (the list is city-bounded). Transport already scores 25% of liveability as the area's share within 800 m; a per-address score would be a measured v5.6 REPLACING that share. Gated (independent distance maths in the test), proven red | **DEPLOYED 6 Oct, verified live** |
| 3n | **New York on the front page** (Bill, 6 Oct: "show on the main screen instead of going to the full map"). DONE in source: a chip, the five boroughs, the FAA's routes for JFK/LGA/EWR/TEB, the US DOT noise picture, cards from the score engine via `scripts/build_nyc_front.py` (blocking `--check`, proven red), dollars and a "curated, not comparable with the UK" note. Gate `tests/front-page.mjs` 12b (7 checks, proven red). Next: New York ZIP search on the front page, then New York arrivals there (the Bay Area's are drawn since 7 Oct) | **DEPLOYED 6 Oct, verified live** |
| 3= | **Firm terms + no highlighted cards** (Bill, 2026-10-06, after asking whether firms need a minimum). **No minimum order; paid before the report is sent** (invoice on order until a card payment link exists - a Stripe Payment Link needs no code, but it is Bill's account); **first report free ONCE PER FIRM**, recognised by the work-email domain (firm reports are made by hand, so this needs no system); **ten for GBP 250 (GBP 25 each) used within 12 months**; a bigger pack only when a firm asks. Reasoning: with no paying firm yet a minimum blocks the first sale, and the admin a minimum would save is better saved by paying up front. **No card on `/pricing` or `/api/` is highlighted** and every card button has one style: each section is for a different buyer, and a homeowner jumping to the report tiers saw the FIRMS card outlined. Gated (16b, computed style), proven red | **DEPLOYED 6 Oct, verified live** |
| 3s | **Search platforms (InfoTrack, TM Group, Search Acumen; Groundsure and Landmark as report makers)** (Bill, 6 Oct: "can we get in touch?"). Two routes: (A) our report in a platform's catalogue, wholesale per report, invoiced monthly to ONE platform account; (B) our data INSIDE an existing environmental report under an API licence - where the volume is. Before any approach: **PI insurance** (already a gate), **written NATS confirmation that AIP-derived routes may be resold** (the AIP terms 5.4 acknowledge commercial data services; nats.aero's terms leave doubt), CAA counts never in a resold product, **England-wide coverage** (we cover 34.6% of sales: measured from HMLR 2025, 932,678 sales / 779,131 standard, so ~270k-320k a year in covered areas; every 1% take-up ~2,700-3,200 reports), then the rename + ICO fee + DKIM (OUTREACH_TARGETS row 6, "after rename"). **Warm route: OS lists InfoTrack and TM Group as OS business partners, and Geovation (OS + HMLR) offered partner introductions.** Drafts on request: the NATS email, a one-page partner brief. **Full plan, the ten things needed with their costs (about GBP 1,700 to 4,100 in year one, then GBP 800 to 2,000 a year) and the verdict: OUTREACH_TARGETS.md "Search platforms"** | Sequenced; nothing sent |
| 3p | **Card payments for firms: Stripe Payment Links, set up AT THE FIRST PAID FIRM ORDER** (Bill asked if worth it, 6 Oct). Yes, then: no monthly fee; UK card 1.5% + 20p (GBP 35 -> 73p), business/premium card 2.8% + 20p (GBP 1.18), so budget ~3%; two links (1 report, 10 reports), no code. Not before, because it adds a Stripe account in the company's name, a NEW SUBPROCESSOR (`SUBPROCESSORS.md` + `privacy.html`) and a refund line in the terms, for no sale yet; the free first report gives time to set it up. Until then invoice + bank transfer. Councils and the pilot stay on invoice / PO regardless | Waiting on the first firm |
| 3- | **"Who is behind it" removed from `/pricing` and `/api/`** (Bill, 2026-10-06, chose removal over a one-line credit). The legal pages keep their copyright line and the map keeps its schema.org `creator`; both pages keep the support address | **DEPLOYED 6 Oct, verified live** |
| 3d | **Dependabot, 5 open (seen on the 6 Oct push):** **2 CRITICAL in the native app** - `@capacitor/ios` and `@capacitor/android`, "remote content can be loaded at the app origin", fixed in **7.6.9**: update `mobile/`, rebuild iOS on Codemagic and resubmit (the live App Store build carries it). 1 high (`source-map-js`) + 2 medium (`brace-expansion`) are dev tooling in the root lockfile, never shipped to a browser: a lockfile bump | Not started |
| 3w | **Website content audit, 6 Oct** (`AUDIT_REPORT_2026-10-06-website.md`: 1 Critical, 15 Important, 15 Minor; links, prices and counts all clean). **C1: "open government data" claimed for everything while the UK flight routes are the AIP's (NATS, not openly licensed), credited on no page.** Bill's calls: no "Launching" tag; a firm's SITE study (GBP 150) named apart from a council's AREA study (GBP 750); company names off `/api/`; a branded 404. **Batch 1 (content, 20+ findings) DEPLOYED 7 Oct (`e2396cc`), verified from the origin**: "official public data", NATS credited on open data / the map footer / UK area pages, the map's footer links back, `/api/` keeps no prices (gated), area pages describe themselves from their rows, New York's method sentence, methodology + Terms links, liveability (18 on the map), em dashes, og tags, sitemap, "Height". **Batch 2 waits on Bill's approval of the legal draft** (`OneDrive/Desktop/legal-updates-draft-2026-10-06.txt`): terms + privacy (a repealed 1991 Act cited; "one exception" contradicted; no paid-report, free-copy or open-data terms), and **the FAA credit + "as is, without warranty" on the front page (a licence obligation missed since the Bay Area joined it)**. **The 404 page + `.html` forwarding came out of batch 2 and are LIVE 7 Oct** (`86e9816`; `cloudfront_not_found.py --verify` 16 of 16, `/badge` unaffected; Bill ran the two AWS steps because the classifier refuses CloudFront publishes from Claude's session). **The API's own `sources` credit the UK AIP since 7 Oct, DEPLOYED** (`fddc433`, reviewed changeset; derived from each city's AIP airports, so twelve cities credit it and South Yorkshire and New York do not; the 5 Oct audit's M-2 `/sold-prices` privacy fix rode the same changeset). **The Capacitor 7.6.9 fix is on master** (`96ff918`; Dependabot 0 open), but it reaches users only through a new iOS build: Bill to run the Codemagic build and resubmit. **A1 (7 Oct):** the full map's "Planes pass at roughly 4,000-6,000 ft" is a hand ladder by distance to the airport (`index.html` ~10060); the front page and street report use the AIP glide path (TW9 3PZ: ~1,800 ft). **Fixed and DEPLOYED 7 Oct** (`4c2c5d2`): one rule, `finalOverhead()` in `js/flight_geometry.mjs`, for the front page and the full map; live TW9 3PZ reads "About 1,800 ft (Heathrow 27R final approach)" on both. The responsive audit now runs the front page at all twelve widths (127 combinations, clean). **I16 (found 7 Oct reviewing batch 1):** the 11 API-only area pages show no air quality / road noise / flood although the Lambda holds them and they feed the Environment score; `gather()` reads those rows from `borough-extra.json`, which skips API-only cities. Bands are cut on UNROUNDED shares, so do not re-band the Lambda's rounded figures. **Fixed 7 Oct: those pages print the measured figure** ("48.9% of addresses", "1.49 × the WHO 2021 guideline"; `MEASURED_FIELD` + `measured_value()` in `build_area_pages.py`), a city that joins the map switches to bands by itself, and `tests/test_area_page_env_rows.py` asks from the Lambda's side that every held figure reaches its page | Batch 1, I16 and the 404 page live; batch 2 (legal + FAA) on Bill |
| 3a | **GoatCounter loads with no integrity hash on every page** (security hook, 6 Oct) | **DEPLOYED 7 Oct (`4c2c5d2`)**: all eleven pages and the Bay Area generator load `count.v5.js` with `crossorigin` and its sha384 (computed from the served file; matches GoatCounter's published hash; gc.zgo.at sends CORS and a year's cache). Live: loads and runs with no integrity error. `tests/test_goatcounter_pinned.py` holds every page to the one tag; upgrading = recompute the hash, change it everywhere at once |
| 3b | **Front-page engagement** (Bill, 6 Oct: "more distinctive/interactive ... decrease bounce rates"), then the **twice-yearly Flight Path and Noise Report** | **Engagement event BUILT 2026-10-07** (`front-engaged` once per view at a person's first action, plus each way in; read engaged / views of `/` in GoatCounter after a few weeks before judging any redesign). Next: label the example buttons by what each shows (Bill's copy call: the codes alone say nothing). Was: Engagement event first (GoatCounter has no bounce rate; under 200 visits Mar-Sep, so measure before judging), example-answer buttons, planes moving along the real routes (labelled as an illustration, not live traffic), compare + share. The report: league tables by city from data already held and gated; publish on the site now, press push after the rename |
| 4 | ~~Audit 2026-10-05 I-7 (focus-ring contrast)~~ **DEPLOYED 7 Oct** (`4c2c5d2`); I-3 (privacy section on email, Bill approves the wording) still waits with the legal draft; then the weekly `/audit` (due ~12 Oct) | I-7 done; I-3 on Bill |
| 5 | Bay Area release 2 research (prices, crime, population) | **Done 6 Oct, and NO KEY IS NEEDED** (EXPANSION.md, the US sources table): ACS bulk file, California DOJ crime, Census population. Open: the price-TREND decision (FHFA misses 23 of 50 cities) and the 5 sheriff-contract cities with no crime row |
| - | **Waiting on others:** CAA Aviation Intelligence (flight counts, reply due by ~3 Nov; do not write to the supplier or passenger-survey addresses the auto-reply lists, they are other teams), LGM #6 talk 14 Oct 18:00, online (**announced 7 Oct as the first speaker**; see OUTREACH_LOG; talk prep due before then), Breathe London (which network; written approval for the Communities API). Bill's Census and api.data.gov keys are NO LONGER NEEDED (6 Oct research) | - |
| - | **Bill's, any time:** **approve the legal draft** (Desktop file above); the noise@caa.co.uk ERCD contour request (update "Cubitt33 Ltd" and "open government data" first); the I-8 decision; **the name** (TMview hand-checks: `OneDrive/Desktop/name-shortlist-trademark-checks-2026-10-06.txt`; Overhush the only one confirmed clear; Earborne clear on the UK register itself but beside AIRBORN/AIRBORNE marks); **the ICO fee (GBP 52)**; **a new confirmation statement for the SIC codes** (free: the 8 Sep one went in with no updates); **tell the accountant the company is about to trade** (it has filed dormant accounts since 2022); **sign the IP assignment deed**; Dependabot (2 critical in `mobile/` Capacitor, fix 7.6.9) | - |


### RECOMMENDED NEXT, in order (written 2026-09-27, after the Norwich deploy; updated 2026-09-30)

Most of what matters now is not code. Owner in brackets.

| # | Task | Why now | Owner / size |
|---|---|---|---|
| 1 | ~~**Send the Norwich reporter the scorecard links**~~ **SENT; he replied warmly on 2026-10-03** (OUTREACH_LOG; two ideas from his reply are parked below under "Parked idea"). Original: (draft in `OneDrive/Desktop/outreach-drafts-2026-09-30.txt`, replacing the lost 27 Sep scratchpad one. Until 30 Sep those scorecards ended "Open Norwich on the Sky Score map", which opened LONDON's map - the defect he reported; fixed and live in `c95124c`, so the links are safe to send) | Closing the loop fast on public feedback is the cheapest trust there is; the links are live | Bill, 5 min |
| 2 | **Send the CAA data request** (drafted 26 Sep, refreshed 30 Sep in the same Desktop file; **to `noise@caa.co.uk`**, verified from the CAA's own ERCD report. No Heathrow address could be verified, so the email asks the CAA who holds the airports' reuse rights instead of guessing one) | The ERCD Heathrow contours are the newer yardstick the Chiswick/Feltham complaint needs, and they gate phase 2 and the `CORRIDOR_WEIGHT` refit | Bill, 10 min |
| 3 | **Pay the ICO fee** (GBP 52, Cubitt33 Ltd) | Legal obligation, open since August | Bill, 5 min |
| 4 | ~~**Triage the 16 Dependabot alerts**~~ **Done 2026-09-28.** All 16 were in `mobile/` build tooling; **none reached the site, the Lambdas or the extension**. Ruby (5): fastlane 2.233.1 -> 2.240.1 plus excon 1.6.0 / json 2.21.2 - the old fastlane capped faraday at 1.x and rubyzip below 3, so no patch fitted under it; `bundle exec fastlane lanes` loads every lane. npm (11): all via `@capacitor/assets` 3.0.5, the LATEST release, which pins sharp 0.32.6 exactly - fixed with `overrides` (sharp ^0.35.4, tar ^7.5.22, uuid ^11.1.1), `npm audit` 0. **Verified by running the generator**, not reading: 148 Android files, 0 "Unable to load" lines (its known silent-failure signature), and old-vs-new output within 1.6/255 mean per channel, visually identical. **Unverified until the next Codemagic iOS build**: sharp 0.35 on Codemagic's macOS. Found doing it: the COMMITTED Android icons differ from what either tool generates (up to 27/255), so they were not produced by the pipeline as it stands | Claude, done |
| 5 | ~~**Follow up Geovation for the video call its clinic lead offered**~~ **CALL HELD 2026-10-02, went well; Bill invited to Geovation's Slack. The product feedback is checked against the live site in "Geovation feedback (2026-10-02)" below; still to ask: the next intake.** (added 2026-09-30, ahead of the rename because it is warm and will not keep; draft in the same Desktop file) | The Geovation Accelerator is run with OS and HM Land Registry, and a 2026 priority theme is "Risk & Resilience", property-level environmental risk, which is close to what Sky Score is: up to GBP 20k equity-free plus partner and market-lead introductions, i.e. warm routes to the buyers cold email cannot reach before the rename. From search summaries - confirm on geovation.uk; both 2026 intakes appear closed, so ask when the next opens | Bill, 10 min, then a 30-min call |
| 6 | **Pick the new name, then unblock outreach** | Five pilot drafts, zero sent; the rename is now the bottleneck, not the product. Warm channels (London AI Hub, AI Tinkerers organisers) need not wait | Bill, decision |

Parked on purpose: phase 2 departures (until the CAA data - the v5.4 fit showed DEFRA cannot reward them); Norwich on the map (watch scorecard traffic first); I17 (**28 Sep: IAM paste DONE - probe 23 granted, 0 denied; SES identity VERIFIED, DKIM SUCCESS; I17 code landed on master with the flag off.** **29 Sep: TTL deployed on master (live table reads ENABLED); PR #15 rebased, reworded to "press Confirm", and GREEN.** Left: SPF merge + DMARC in Cloudflare and the SES sandbox-exit request, both Bill's; then merge PR #15, which IS the flip - OPERATIONS s3.9); the Android rebuild (after the rename, so it goes through review once). Optional: `CITIES=norwich sh scripts/load_road_rasters.sh` for the per-postcode road tier on `/v1/environment`.

**Added 2026-10-03, all Bill's and all short:** (a) a free OS Data Hub key on the OpenData plan, then open `/#oskey=<key>` once on each device (the FRAGMENT since 2026-10-05, audit M-1: a `?oskey=` is now ignored; `/preview/` until the front page moved on 2026-10-06) to judge the street-map trial; (b) before the first PAID report, indemnity insurance and NATS AIS's written confirmation on reusing AIP-derived routes (`LICENSING.md`); (c) a free Census API key, after the Bay Area map release (released: request it now); ~~(d) try `/preview/` on a phone and rule on when it replaces `/`~~ **ruled 2026-10-06: it IS `/` now** (Homepage redesign, below).

### Audit 2026-10-05: what it left open

Full detail and statuses in `AUDIT_REPORT_2026-10-05.md`; this is the work list.
Strike a row here in the commit that closes it.

| # | Item | Owner / size |
|---|---|---|
| ~~C-1~~ | ~~On a phone the main map showed nothing for a search that did not succeed.~~ **FIXED AND DEPLOYED 2026-10-05** (`d6de92b`, `.no-result-yet`; gate red-then-green; live page verified at phone and landscape widths; master level). Left: the App Store copy keeps the defect until its next binary | Done, bar the binary |
| ~~I-1~~ | ~~`/preview/` tells Barking and Dagenham postcodes they are outside the map: derive the city from the open-data row, and run the 86-spelling fixture against the preview~~ **Fixed 2026-10-05** | Done |
| ~~I-2~~ | ~~`/preview/` "Nearest runway" reads three airports only: say "nearest of SFO, OAK and SJC" or read the page's own airfield list; the test asserts the old wording~~ **Fixed 2026-10-05** | Done |
| I-3 | Privacy notice has no section on email, and the register says Cloudflare sees no payload while it routes the mail | Claude drafts, **Bill approves the wording** (legal page) |
| ~~I-4~~ | ~~`/preview/` layout collides from 761px to about 1180px wide~~ **Fixed 2026-10-05**: stacked below 1280px and on short screens, one query for CSS and engine | Done; worth a look on a tablet |
| ~~I-5~~ | ~~`/preview/` search box is tab stop 56, no skip link~~ **Fixed 2026-10-05**: skip link, and the panel first in the page | Done |
| ~~I-6~~ | ~~`/preview/` placeholder is the only visible label~~ **Fixed 2026-10-05**: a visible label and an example placeholder that fits at 320 | Done |
| ~~I-7~~ | ~~Focus rings at 2.1-2.7:1 on the new pages and on the main map (1.4.11 asks 3:1)~~ **DEPLOYED 7 Oct** (`4c2c5d2`): `--focus: #d35a12`, 3.2:1 or better everywhere, gated | Done |
| I-8 | **Decision:** the borough Quiet skies band says 0.0 for Hillingdon while most of its postcodes estimate 8-10. Keep "worst exposure in the borough" and say so where it is printed, or re-derive the band from the postcode tier (a methodology version) | **Bill** |
| Minors | 20. **Closed 2026-10-05:** M-2 (in source; **the score and sold-prices Lambdas need Bill's backend deploy**), M-4, M-5, M-6, M-8, M-9, M-10, M-11, M-12, M-14, and the Bay Area order and open-data scroller of M-19. **Part-done:** M-15, M-17, M-18. M-3 is recorded as a precondition of the signup flip. **Also closed 2026-10-05:** M-1 (the key moved to the fragment), M-7, M-13 bar the `sw.js` comment (it waits for the next real `sw.js` change), M-16, and M-19 bar the laptop card fold. **Bill's calls:** M-20 (where the phone footer goes) and the card fold | Bill: two layout choices |

### Geovation feedback (2026-10-02): positioning and the first view

From the follow-up call (OUTREACH_LOG). Each UX point was **checked on the live site the same
day** (Playwright, 1440x900 and 390x844), not taken on trust in either direction. Nothing here
is built yet.

| Point | What the live site does today | Options / owner |
|---|---|---|
| **Narrow to the flight-path niche**: several noise checkers exist | Breadth is crowded: **Crystal Roof** (part of Geovation, per the call) already publishes road, rail AND aircraft noise by postcode beside crime, schools, air quality and flood (its noise page, read 2026-10-02). What nobody else has is the depth: routes derived from the UK AIP for each runway, a runway-shaped estimate fitted against DEFRA (v5.3-v5.5), and per-postcode quiet scores | **Feeds the rename (#6 above)**: the new name and the landing line should say aircraft or flight paths, not a generic "score". Bill, decision |
| **Freemium sets us apart** from Crystal Roof | The site and the 10,000-request free tier are both free; paid is the B2B pilot and Professional tier | Keep. Say it on the landing page and in the Geovation application |
| **The flight noise shown at load may confuse** | At load the boroughs are UNFILLED and the only colour is two layers that start on (`layers = { paths: true, 'defra-aircraft': true }` in `index.html`): animated corridor lines plus DEFRA's 40-80+ dB contours, explained by a legend in "dB Lden". No plain sentence says what the colours mean. On desktop the strapline is small grey text, partly covered by the first-run hint | A one-line plain caption on the map ("Orange lines: where Heathrow's planes fly. Coloured areas: how loud it is on average, measured by DEFRA"); or start on the borough scores and let the noise layers be one tap away. Gates that move: `layer-honesty`, `responsive`, `map-fit`, a11y. Claude, after Bill picks |
| **Make search more obvious** | Desktop: the search box is in the right-hand panel under "PROPERTY INTELLIGENCE"; the map, where the eye lands, carries only a dismissible hint. **Phone: the tabbed search view hides `.sidebar-header`, `.empty-state` and `.first-hint`, so a first-time visitor sees no product name and no "what is this"**, and the first thing under the search card is the nine footer links (put there on purpose by audit C2 so the legal links are reachable; move them, do not hide them) | A headline question at the search ("Check aircraft noise at your postcode") on both layouts; a phone heading. Claude |
| **Noise charts when you click an area** | A borough click gives a score card and five component bars; noise is ONE bar ("Quiet skies 7.5/10"). Nothing shows decibels, how the borough compares with its neighbours, or how noise varies across it | A small chart of the borough's postcodes per DEFRA band (data already held: the per-postcode aircraft-quiet datasets and road share). **Do not say "how often planes pass"**: that is N65, which we do not hold. Claude, after Bill picks |
| **OS open maps API** | No basemap, by recorded decision (CLAUDE.md "There is NO basemap") | OS Data Hub's OpenData plan (Maps, Names, Features APIs) is free and unlimited; Premium carries GBP 1,000/month of free transactions. **He meant the map background (confirmed 2026-10-02). COSTED: GBP 0 in tiles.** Every zoom the map reaches sits in OS's free OpenData band (web-map zoom 7-16; OS: "Open layers are available to all users of the API regardless of which Data Hub plan is used, at no cost"): measured from the CITY_DATA scales and `scaleExtent([0.5, 8])`, desktop runs zoom 8.6-13.6 (14.6 on retina), London's default view is 10.2, and only a 320px phone fully zoomed out on the widest city dips to 6.9, where OS serves nothing (clamp). Premium (MasterMap) starts at zoom 17, which the 8x cap never reaches. Two routes: **(A) OS Maps API live** - an OS Data Hub key visible in the page (keep it on the OpenData plan so a copied key cannot spend), CSP `img-src` widened, a runtime dependency, no offline basemap; **(B) self-host OS Open Zoomstack (OGL) clipped to our cities** on our own S3/CloudFront - no key, no CSP change, low zooms precachable, egress inside CloudFront's always-free 1 TB/month. Either way attribution: "Contains OS data (c) Crown copyright and database right". The real cost is engineering time and the two non-money objections that still stand (offline launch, street detail implying precision the borough scores lack). **Cheapest next step:** point `design/map-basemap.html`'s raster toggle at OS OpenData tiles (needs a free Data Hub key) and judge it on screen. **Superseded 2026-10-03: the trial is BUILT on `/preview/`** (route A, behind a key pasted per device, never in the source - see "Homepage redesign"); it needs only Bill's free Data Hub key to be judged on screen. **OS Names API for place-name search** is still worth a separate look |
| **Profit from generated reports** (like the Earl's Court one-pager) | `scripts/area_summary.mjs` makes one from live data in about a minute. Two decisions already bound who pays: **consumers stay free** (23 Jul) and **community one-pagers are free** (29 Sep community plan) | Sell the SAME generator to businesses on the buyer's side: buying and relocation agents, surveyors, developers' and planning consultants (site screening, never a formal assessment). **Not estate or letting agents, and not conventional lenders or insurers** ("Constraints"). The niche version is an **aircraft-noise report per address** (routes overhead, DEFRA level, the 2021 caveat). Gates: the rename first; never presented as a conveyancing environmental search; check PI insurance; OGL attribution and no implied Breathe London endorsement. **Test by hand before building**: a payment link plus the script, offered to two or three warm contacts. Bill, decision |
| **Browser extension is a decent idea** | Unlisted MV3 demo, ship gates in `extension/README.md` | Publish after the rename, so it goes through store review once |
| **Defect found while checking** | **The first-run hint does not dismiss on a borough click**, though its comment says it does (`index.html`, "Hidden once ... (search, borough click, layer toggle)": only search focus, the layer toggles and a 30 s timer are wired). Seen live: the hint stayed on screen through three borough clicks | Small fix in the borough click handler. Claude |

#### Monetisation, ranked (brainstorm 2026-10-02; nothing decided)

Two facts bound it. **Traffic is small** (under 200 visits March to mid-September), so
anything paid per visitor (consumer subscriptions, adverts, affiliate links) earns close to
nothing today; revenue has to come from a few businesses paying real amounts. And **Crystal
Roof already sells the consumer subscription** (its pricing page, read 2026-10-02: GBP
7.99/week, 12.99/month, 29.99 per 3 months, with postcode-level data limited on its free
plan; it also sells an API and widgets to property websites, prices not public). Free
postcode-level data is therefore the differentiator Geovation named, and a consumer paywall
would give it away.

| # | Route | Why this rank | Gate |
|---|---|---|---|
| 1 | **Aircraft-noise address reports for businesses, sold by hand** (buying and relocation agents, surveyors, developers' consultants; **NOT estate agents** - corrected the same day against "Constraints" above, which this table was first written without reading: estate agents are misaligned, and conventional lenders and insurers are out under the riba-free rule) | Cheapest test of whether anyone pays; uses the niche. **SAMPLE BUILT 2026-10-02: `scripts/address_noise_report.mjs`** (one page per postcode: DEFRA level against the WHO guideline, a map of the contours and published routes, each route's closest point and the approach height there, the postcode's place among its district's live postcodes, the 2021 caveat). Sample for TW9 3PZ (Kew) on the Desktop. Run on four postcodes (measured, outside the contours, a neighbour-resolved postcode, Teesside); lint clean; **no automated test yet** | Not a conveyancing search; PI insurance checked; price is a guess until someone pays. **NEW GATE: the UK AIP's reuse terms have never been read. `LICENSING.md` has no entry for it at all**, though the map has drawn AIP-derived routes since v5.3 - read NATS/CAA's terms and add the entry before any report is SOLD. **DONE 2026-10-03: read, and LICENSING.md has the row; no licence is granted in terms, so ask NATS AIS in writing before the first paid report. Price set the same day: GBP 35 a report for firms, free for individuals and residents' groups** |
| 2 | **Commissioned area studies** (councils, developers, groups holding grant money) | The free community one-pager is the sample; a few per year matter at this size | Stay a data supplier, never a campaigner |
| 3 | ~~**Badge / widget subscription for agents and property sites**~~ **WITHDRAWN the same day**: it sells to estate agents and listing sites, which "Constraints" rules out (their incentive is to push the sale through), and only flattering listings would embed it | `/badge` exists and is edge-cached; keep it free for buyers' advisers and community pages | - |
| 4 | **API and data licensing** (the existing ladder), pitched as an aircraft-noise layer, not a general score | Largest contracts, slowest cycle | Rename, then outreach |
| 5 | **Non-dilutive funding** (Geovation, grants) | Likeliest near-term cash; not revenue | Ask the next intake |
| - | Consumer paywall, adverts, affiliate links | Tiny at this traffic; costs the differentiator or the neutrality the community work rests on | Not now |

#### Breathe London is London-only: the rules if it is built (recommended 2026-10-02)

**Licence first (2026-10-06): there are TWO Breathe London APIs.** breathelondon.org (the
GLA's network) is OGL v3.0, commercial use allowed with its attribution. breathelondon-
communities.org (Imperial Projects' Communities network) is non-commercial only without
IPROJ's prior written approval - and the Breathe London team's reply of 6 Oct pointed to
THAT one. Build on the GLA API; take anything only the Communities network holds only once
approval is in writing (OUTREACH_TARGETS L5 quotes both; re-read on 2026-10-07 and unchanged,
with every other measured source's licence in EXPANSION.md "Measured air quality"). **How, when built:** a scheduled
script fetches the sensor list and recent averages into a static file under data/ (the
key stays on Bill's machine, never in a page, and no visitor ever calls their API, which
both licences let them throttle for "excessive use").

It causes no problem for the other cities provided three rules hold. **(1) Display only,
never scored**: scores are compared across cities (v5.0 anchors are national), so a
London-only input would score London differently, and the key is revocable. **(2) Outside
London the section does not render**; it must never say "no sensors nearby", which is the
`/transport` lesson (TfL's silence about Manchester was printed as "No stations found").
Inside London, far from a sensor, it gives the distance. **(3) Any `/v1/environment` field
is documented as London-only and absent elsewhere, never null-as-zero.** The national
counterpart exists: DEFRA's AURN, 205 active sites (uk-air.defra.gov.uk), with a public
JSON API that answered 200 with no key on 2026-10-02 (`/sos-ukair/api/v1/stations`). It is
far sparser than Breathe London, but it would give every city a "nearest official monitor"
row, so London gains a layer rather than being the only city with measurements. Licence and
update rhythm for that API: not yet read.

### The Bay Area flight-path page (built 2026-10-02)

Bill's rulings: the Bay Area goes live as a flight-path PAGE first (`/bay-area/`),
covering the 50 cities of the four counties round SFO, OAK and SJC; the scored
city on the map follows. Detail and what was learnt: EXPANSION.md.

- [x] Derive the routes from the FAA's CIFP (`build_us_flight_paths.py`).
- [x] Build and gate the page (`build_bay_area_page.py --check`, blocking).
- [x] **DEPLOYED 2026-10-02 (22:05 UTC) and verified from the origin**: every
      uploaded file hash-equal to source, three invalidations Completed,
      `/bay-area/` 200 with `no-cache`, the no-slash address keeps its noise
      shading, drift 22 pages / 25 data files / 103 area pages, and the live
      WCAG scan passes (`/bay-area/` is in `tests/e2e/accessibility.spec.js`).
      Linked from both footers of the main site ("Bay Area") and from `/area/`.
- [ ] Post it where Bay Area residents are (Bill's to do). Never say "how often
      planes fly over": the page says where the routes are, not their traffic.
- [ ] Each new FAA cycle (28 days; **next is 2611, effective 2026-10-29**):
      `build_us_flight_paths.py --fetch`, then `--write` on
      `build_bay_area_page.py`, `build_bayarea_map_data.py` and
      `build_bayarea_areas.py` (all three read the record, and all three
      `--check`s are blocking), re-render `share.png` (`node
      scripts/render_bay_area_share.mjs`) if a line moved, then deploy
      `bay-area-deploy`, `web-deploy` (the BAYAREA-MAP block) and
      `data-deploy`. The legend's cycle number is GENERATED since 2026-10-06
      (`BAYAREA_ROUTES_CYCLE`); it was typed by hand and nothing checked it.
- [ ] **The scored city: stages 2-5 in EXPANSION.md. Bill, 2 Oct evening: "have
      San Francisco as part of the map" - so this is NEXT, not later.** First
      step is generalising the by-name New York branches (EXPANSION.md lists
      them); the homepage mockups already draw the Bay Area as a city on the
      map from the page's own files, which is what it will look like.
- [ ] **RULED 2026-10-03 (Bill): two releases.** (1) ON THE MAP, honestly
      scoped: the 50 cities, the FAA routes, the noise picture, city and ZIP
      search, and a Quiet Skies ESTIMATE per city and ZIP, labelled as one -
      and NO overall Sky Score, because a composite from one estimated input
      would break the two-input floor every other city is held to. (2)
      SCORED: prices and the liveability inputs, then the overall score, San
      Francisco's 41 neighbourhoods as the neighbourhood tier, area pages and
      the launch post. Release 1 starts with the by-name New York branches
      (counted 3 Oct: 18 comparisons in `index.html`, 7 and three tables in
      the score Lambda, 10 scripts).
- [x] **Release 1, step 1 (2026-10-03, branch `bay-area-on-map`)**: five of the
      page's eleven by-name New York tests now ask the registry; the rest are
      declared in `tests/test_us_city_branches.py`.
- [x] **Release 1, ZIP codes (2026-10-04)**: `data/us-bayarea-zips.json`, 165
      ZIP areas from three Census files, and ZIP search on `/preview/`
      (EXPANSION.md has what the data taught). Next: the Bay Area's entry in
      the live map's registry, then the Lambda entry and its deploy.
- [x] **Both steps MERGED AND DEPLOYED 2026-10-04 on Bill's instruction**:
      master fast-forwarded to `35f1a2b` (CI green), `web-deploy` and
      `preview-deploy`, both invalidations Completed, five files hash-equal
      to source. Driven in a browser against the live origin: the map still
      draws London, New York's noise tiles and Manchester's DEFRA picture
      with no page error, and on `/preview/` 94301 opens Palo Alto with its
      pin, 95014 says 44% of it is in Cupertino and 90210 is told it is not
      covered, at desktop and phone widths.
- [x] **Release 1 on the LIVE map, BUILT AND DEPLOYED 2026-10-05** (`24cf782`, inset fix `6b39f59`;
      verified from the origin at desktop and phone: BTS tiles paint, ZIP 94066 opens
      San Bruno's facts, no inset, no page errors). Bill ruled the same day:
      facts and no number, ranking by noise-map share). Done: items 1-4 and 6 below,
      bar the locator marker (done later the same day: `usa-locator.json` is rebuilt
      by `scripts/build_us_locator.py` from the Census state outlines and marks both
      cities, gated at desktop by `tests/bayarea-map.mjs`); item 5 turned out moot, because the parity gates read
      `borough-extra.json`, which a facts-only city is not in. Gates:
      `build_bayarea_map_data.py --check` and `tests/bayarea-map.mjs`, both
      blocking. Left for release 2: the Lambda entry, a score, prices.
- [x] **Release 1 on the LIVE map: the checklist** (read off the code 2026-10-05,
      when Bill asked for it before the AI Tinkerers newsletter and it was
      judged a day or two, not hours; `/preview/?city=bayarea` was made safe to
      share instead). In order:
      1. A generator (`scripts/build_bayarea_map_data.py --write|--check`, made
         blocking) writing `data/us-bayarea-cities.json` (GeoJSON of the 50
         cities, rings REWOUND for d3's spherical paths, which the preview
         dodges by drawing planar; never `*-boroughs.json`) and an index.html
         block between markers: airports, routes in New York's shape
         (`coordinates` as [lon, lat]), and a quiet estimate per city.
      2. The `bayarea` CITY_DATA entry with every key New York has (smoke-local
         asserts parity); `center`/`scale` from `fit_city_projection.py`,
         which globs `*-boroughs.json` and needs a path argument; `noiseScale:
         NOISE_SCALE_BTS` (the tile layer is already generic); the FAA warranty
         disclaimer in the legend explainer.
      3. The "no overall score" state in `calcScores`, the sidebar, both
         ranking tables, favourites and share text (seven places).
      4. Registry fields replacing the six by-name New York branches
         (`tests/test_us_city_branches.py`), starting with the ZIP table and
         the property links (a Bay Area city falls to Rightmove today).
      5. A SITE-ONLY city is a new kind: the parity gates assume every site
         city is in the API. Declare it beside `BACKEND_ONLY_CITIES` rather
         than weakening them.
      6. Locator marker, `make data-deploy` line, drift check, then every
         gate that clicks a chip (`city-switch`, `map-fit`, `layer-honesty`).
- [x] **Layer 1 of the deeper Bay Area, BUILT 2026-10-05** (Bill: "a more in depth
      preview of ZIP, area and borough like we do for New York, London"). The same
      facts as a city, one tier down: San Francisco's 41 neighbourhoods (DataSF
      Analysis Neighborhoods, PDDL) and the 165 ZIP areas measured over each ZIP's
      whole area (Census 2020 ZCTA boundaries), by `scripts/build_bayarea_areas.py`
      with the page's own functions (blocking `--check`, offline). On the map: a
      ZIP opens its area's facts and dashed outline above its city's; San
      Francisco's card lists its neighbourhoods; neighbourhood names search; the
      ranking toggles to them. Gated in `tests/bayarea-map.mjs`. **Layer 2 (prices,
      crime, a score) waits for the Census and api.data.gov keys, both Bill's.**
- [x] **Arrival routes, BUILT 2026-10-06** (Bill chose them first, before area
      pages and the launch post: Palo Alto's well-known complaint is ARRIVALS, and
      the page drew none, so the first local reply to a post would have been
      "where are the arrivals?"). `build_us_flight_paths.py` now records each
      STAR (common route, then runway transition, with the FAA's published
      altitude at every fix as a floor/ceiling pair) and each approach's coded
      transitions; departures came out byte-identical. The page joins a STAR to
      the approach transition that starts where it ends, follows it only to a
      drawn final, stops at radar vectors, and **draws it from the first fix where
      the FAA allows 10,000 ft or lower** (Bill's rule, measured against two
      others: 24 of 50 cities overhead, against 21 for "required below 10,000"
      and 32 for the whole route). A city's figure is the published altitude at
      a fix INSIDE it, never interpolated between fixes. **Palo Alto now reads
      "SFO SERFR4. Published altitude at SIDBY, inside the city: 4,000 ft or
      above".** On the page (new column, dashed line, key, notes), the live map
      (`arrival` lines, a card row), and both area tiers. **DEPLOYED 2026-10-06
      (`f14a352`, CI green, master level) and verified from the origin**: every
      uploaded file hash-equal to source, a browser on the live map drew 51
      arrival-type lines (16 finals + 35 arrivals) and Palo Alto's card showed
      the SIDBY row at desktop and phone, drift 22 pages / 29 data / 103 area.
- [ ] **`/preview/` does not draw the arrivals.** Its engine draws finals and
      departures from the RAW record with its own rules (departures whole, cut
      by the city outline), so arrivals there would mean re-implementing the
      join and the 10,000 ft start in JavaScript - mirrored code. Do it by having
      the preview read the generated lines (the BAYAREA-MAP block's shape, or a
      routes member in `us-bayarea-cities.json`), not by copying the rules.
- [ ] **Prices by the public-domain route need a free Census API key**
      (American Community Survey median home values, with FHFA for the
      trend), which avoids Zillow's unread terms. Bill's to request at
      `api.census.gov/data/key_signup.html`; he will do it after the map
      release. It goes in `.env`, never in source. Not needed for release 1.
- [ ] **Reports in the Bay Area follow England's rule** (Bill, 3 Oct): free
      for a person's own home and for residents' groups, firms pay. What can
      be made there today is a ROUTES summary (which routes pass, how close,
      how high), not a noise level: BTS says its map "should not be used to
      evaluate noise levels in individual locations", and the 2022 band
      values are unverified.

### Homepage redesign (opened 2026-10-02, after Geovation)

Geovation: the first view confuses (flight lines before the visitor knows what
the site is); Bill: "a grid system like Hometrack". The path so far, all in
`design/` and none deployed:

- v1 `homepage-grid.html`, six bordered cards; Google Stitch's rendering of it
  (prompt in `homepage-stitch-prompt.md`) "looks like a report itself" (Bill).
- v2-v5: four directions as WORKING pages on one engine (`hp-engine.js`): the
  live map with city chips (the Bay Area included), and a postcode search that
  resolves through postcodes.io and shows the live `/v1/environment` figures.
- **Narrowed to v2 (map with a floating panel) and v3 (ask first), with two
  variations each: v2a, v2b, v3a, v3b.** `homepage-variants.html` is the chooser.
  v1, v4 and v5 deleted at Bill's request (in history at `3452301`).
- **Measured, not judged, 2 Oct evening:** at desktop and phone, is the search
  on the first screen, and after a search is the answer on screen without
  scrolling. v2 is the only one with question, answer and the pin on one
  screen; v3 the simplest first screen; v3b scrolls the search box away on a
  phone; v2b opens the answer a screen below the box on a phone. **Bill chose
  v2** ("go with recommended").
- **`/preview/` is v2 as a working site, branch `homepage-v2`**: the live map
  with the Bay Area as a city chip, the working search, a new `/preview/reports/`
  page with two real sample PDFs, phone layout measured at five widths, all the
  source gates (`make preview-deploy`, noindex). The live front page is
  untouched until Bill has tried it on a phone.
- **3 Oct: the mockup became a TOOL** (Bill: "make the mockup into a fully
  interactive website before deploying"). A borough tap opens the council
  area's card in the panel - Sky Score, five components, price, crime, road,
  air, flood, rail - read from the open data CSV (`/open-data/`), so it costs
  no key and no quota, with links to the scorecard page and the live map;
  boroughs are keyboard buttons (the svg stopped being `role="img"`). Routes
  explain themselves on hover or tap (airport, runway, glide, direction), and
  London draws its departures too; two layer toggles and a zoom. The search
  takes a postcode OR a place name (a borough anywhere, a Bay Area city, a
  city region); a ZIP says what to type instead. The answer gained the
  nearest runway and "under which approach, at what height", from
  `js/flight_geometry.mjs` - MOVED from `scripts/` so the browser and the two
  report generators share one holder - plus the council area's score and
  flood share. The URL carries `?city=` / `?postcode=` / `?borough=` in and
  out, the same names the live map reads. **Two mockup defects found doing
  it**: the estimate row never rendered (it read `aircraftQuiet`; the API
  sends `aircraftQuietEstimated`), and an uncovered postcode was pinned on
  whichever city was on screen - both now gated, and `outside` coverage says
  so rather than printing the 10/10 the endpoint returns for it. Gate:
  `tests/preview-home.mjs` (69 checks, offline, blocking), whose first run
  found a third: the 14px hover band of Heathrow's 27L approach stole
  Hounslow's tap, so routes now take no pointer events at all and the svg
  measures the pointer's distance to them instead. **And a fourth, in
  `sw.js`, before the deploy**: same-origin paths are cache-first by default
  there, so the engine (no-cache) and the open-data CSV would have pinned in
  Cache Storage on any phone that had visited the live site - the
  `borough-extra.json` incident on the page meant to replace the front door.
  v1.0.36 routes `/preview/`, `/open-data/` and `/score-demo/openapi.yaml`
  network-first; `tests/test_sw_no_cache_prefixes.py` derives the rule from
  the Makefile's `no-cache` uploads and found `openapi.yaml` the same way.
  **Deploy is therefore `pwa-deploy` + `preview-deploy`**, not the preview
  alone. **And a fifth, at the commit**: `.gitignore` carried an unanchored
  `reports/`, so `preview/reports/` (the page and both sample PDFs) was
  invisible to git while five gates read it - green here, red on any fresh
  clone, the `data/*` trap on a page. It is `/reports/` now. **The review
  before the commit found six more in the engine, each given a check that
  was red first** (57 checks became 66): the air-quality fact printed the
  worse-of-two WHO ratio as NO2's (PM2.5's on more than 60 of 97 rows; empty
  brackets on the 11 API-only rows, which hold no concentrations); an
  uncovered postcode left the LAST search's pin on the map, which the gate's
  own city switch had been clearing; the estimated row read `Quiet skies
  9.0 / 10` beside a 10% bar and is `Aircraft noise 1.0 / 10` now, the
  extension's reading of the same field (METHODOLOGY s11.0); a late outline
  file could draw one city's council areas under another's routes; route
  tooltips fired where the line is clipped away; and `?city=` beat
  `?borough=` when the two disagreed.
- **DEPLOYED 2026-10-03 on Bill's instruction and verified from the origin**:
  `https://skyscore.co.uk/preview/`. `pwa-deploy` then `preview-deploy`, both
  invalidations Completed, 11 files hash-equal to source, the live worker
  reads v1.0.36, and a browser driven against the LIVE page at desktop and
  phone widths drew all ten UK cities and the Bay Area, opened Camden's card,
  answered TW9 3PZ from the real API and served both PDFs with no failed
  request. **The deploy itself found one more**: four data files the engine
  reads (`flight-procedures.json`, `aircraft-noise-rasters.json`,
  `us-bayarea-places.json`, `us-flight-procedures.json`) had never been at
  the origin - the live map carries their contents inline - so the page would
  have opened on "The map could not load". Caught by curling the origin
  before uploading; no source gate could see it, since they all serve the
  working tree. `preview-deploy` uploads them now, and the gate's last check
  (69 checks) fails any file the page fetches that no Makefile target
  uploads. Both pages joined the CloudFront accessibility scan. Next: Bill
  tries it on a phone, then the open decisions below.
- **Bill's rulings, 2026-10-03, and what was built on them the same day:**
  - **Reports are free for individuals** (a buyer or renter, their own home,
    one at a time) **and for residents' groups; firms pay GBP 35 a report**,
    first one free, ten for GBP 250, an area or site study from GBP 150.
    Quoted flat: Cubitt33 is not VAT-registered. `/preview/reports/#prices`
    is the ONE holder of the report price; the front page links to it and the
    gate fails if it repeats the figure. `/pricing` lost its last
    "+ VAT where applicable". Still Bill's before the first SALE: indemnity
    insurance, and NATS's written confirmation (below).
  - **The AIP reuse terms are now READ** (the gate "Monetisation, ranked"
    row 1 recorded as never done) and `LICENSING.md` has the row: the AIP's
    own terms (GEN 0.1 section 5) grant no licence in so many words but
    acknowledge third parties putting the information in their own products
    "with or without charge" and place liability on the user; NATS's
    corporate website terms forbid commercial reuse of that website's
    content. No term read forbids the free uses. Ask NATS AIS in writing
    before the first paid report.
  - **Every offering has a page**: all 30 links on the two preview pages
    resolved; pricing and the council-area index were not linked from the
    preview at all and now are (cards and both footers). API, open data and
    pricing still land on current-design pages whose header leads back to
    the current map; new-design versions are not built.
  - **OS street-map trial, on the preview only**: the OS Maps API's
    `Light_3857` tiles under the map, behind a Streets button that exists
    only on a device given a Data Hub key (`/preview/?oskey=<key>` stores it
    in that browser and removes it from the address bar; `?oskey=off`
    forgets it). No key is in the source and no ordinary visitor's browser
    contacts `api.os.uk`. The gate stubs the tiles and checks the grid
    against the pin of a known postcode (proven red with the grid shifted
    one tile). **Waiting on Bill: a free OS Data Hub key on the OpenData
    plan.** If it earns its place, ship self-hosted OS Open Zoomstack, not
    the keyed API (LICENSING row).
  - The free-tier figure on the preview's third card is now under
    `FreeTierQuotaDriftTests`; it was an unguarded mirror.

- **MERGED TO MASTER 2026-10-03 on Bill's instruction**: a fast-forward to
  `0c2445e` (master had not moved since the branch was cut), CI green on all
  four jobs. Master now equals what is live, sw.js v1.0.36 included, so a
  deploy from master cannot roll the worker back. Work continues on
  `homepage-v2`; fast-forward master after each deploy so the two stay level.
  (Since then master has moved on with `bay-area-on-map`: `35f1a2b` on
  2026-10-04. `homepage-v2` is fully contained in it.)
- **THE FRONT PAGE SINCE 2026-10-06** (Bill: "making our mockup (with report
  generation and api etc.) into our live website"; branch `front-door`). His
  rulings, all four recommended options: **the installed app opens the full map**
  (`start_url: "/map/"`; the App Store app IS the map), **reports are free and
  self-serve for your own home, firms ask by email** (no payment system until
  NATS confirms reuse and insurance is in place), **launch now and rename later**,
  and **the API, pricing and open-data pages get the shared site bar and footer
  now**, their bodies restyled later (the 103 area pages got the bar too). What
  moved, and why each piece is where it is, is CLAUDE.md "THE FRONT DOOR MOVED".
  New: `/reports/street/`, a visitor's own one-page aircraft-noise report made in
  the browser from `js/street_report.mjs`, the same module the sample PDFs are
  printed from. **DEPLOYED 2026-10-06 (`41c0852`, master level) and verified from the origin**: drift 31 pages / 34 data / 103 area, every precached asset present; a browser on the LIVE site at 1440 and 390 found / the front page, /map/ the map with its API base, /reports/street/ making TW9 3PZ's report from the live API, /preview/ forwarding, no page errors or failed requests; manifest start_url /map/, worker v1.0.37; live e2e 33 of 33 (10 before the deploy); live phone layout PASS; site == /v1/score on 6 postcodes; responsive live 115 combinations across 17 pages clean.
  - **Same evening, Bill's polish (built, preflight then deploy):** "Bay Area" out of the
    top bar (still reached by its city chip, the `/map/` footer and now the front page's
    footer); the intro no longer says "tap a council area on the map" while that map sits
    faded behind it, and offers **"Or explore the map"**, which ends the intro and puts
    focus on a council area; "Full map" is the bar's one orange button, the other links
    full-strength with an orange hover, on every page with the bar. **Report prices are
    three tier cards** (own home Free, residents' groups Free, firms GBP 35 with the bundle
    and study prices), still held on `/reports/` alone. **The free browser-made report says
    on its face "Free copy for personal use, not for use with clients"**: Bill asked whether
    firms could pose as residents; they can, and visible terms on the page a client sees
    are the cheap deterrent. Terms-of-use wording for the same is Bill's to approve.
    Fixed on the way: a phone tap on a council area beside a route opened the card and
    then left the ROUTE's tooltip on the map (the click handler for routes ran after the
    area's own) - M-15 by another door, caught by `tests/front-page.mjs`.
  - **Then, the same evening (Bill): the free report is ON SCREEN ONLY; the PDF is the paid
    product for firms.** He still felt firms could take advantage of a free PDF. No print
    button; printing the page (a browser's "Save as PDF") prints a firms note instead, and
    so does printing the report's own frame; the firm tier now leads with "A PDF to hand to
    your client". A screenshot still works - the aim is that a firm cannot hand a client a
    clean document, not to stop a person keeping their own figures. Next step if that is
    not enough: email to unlock, one per address a month, once SES leaves the sandbox.
    **"Cubitt33" is off the marketing pages** ("Sky Score is run by Cubitt33 Ltd." in three
    footers, and the VAT note); it STAYS on privacy.html and terms.html, which must name
    the company (UK trading-disclosure rules and the controller's identity in the privacy
    notice). The footers now say "All figures from official public data" - "open
    government data" over-claimed, as the UK routes come from the AIP, public but not
    openly licensed. And the Bay Area is no longer called out on its own in the reports
    copy or the front page's footer (its city chip and the /map/ footer remain).
  - **Pricing evidence gathered 2026-10-06 (for the "price is a guess" row above):**
    Groundsure Homebuyers, the nearest conveyancing comparator, is advertised from GBP 92.60
    + VAT for seven risk areas with GBP 10M PI cover; ours is narrower, uninsured and not a
    search, so GBP 35 sits sensibly below it. **A direct competitor, My Flight Path**, sells
    per-property "Flight Blight Reports" (aircraft types, daily and hourly impact, decibels,
    helicopters and GA) and gives surveyors its ratings free through Survey Booker; its
    report price is not public. It holds the "how often" data we do not (N65). Keep GBP 35,
    test by hand with two or three buying agents, and sell firms what the free copy cannot
    give (their branding, batches, an invoice, a human check, later the insurance).
  - **Still to do, deliberately later:** restyle the bodies of `/api/` and
    `/pricing` (dark, Geist) to the new design; the free AREA summary is still
    by email (`scripts/area_summary.mjs` reads the live API with a key, so it
    cannot run in a visitor's browser as it stands); draw the Bay Area's arrival
    lines on the front page (it reads the raw FAA record, ROADMAP Bay Area).

### Parked idea: a community noise-sensor network (raised 2026-10-03)

Bill: "an initiative like Breathe London but for flight and road noise".
Kept for reference; nothing is built or promised.

- **Why it fits**: sensors answer the two things published data cannot - how
  OFTEN aircraft pass (N65, which we do not hold) and what levels are THIS
  year (DEFRA's map models 2021). It is also what residents' groups ask for,
  and it is hardware, which the Makerversity residency (applied 1 Oct) and
  the declined Deep Tech Expo both turn on.
- **What exists already** (searched 2026-10-03, not contacted): Breathe
  London is run by Imperial's Environmental Research Group on sensors from a
  commercial supplier, with about GBP 1.5m from the Mayor and Bloomberg
  Philanthropies for 195 sensors, and a sponsorship scheme that gives
  community groups nodes at no cost. For aircraft noise, a German volunteer
  body (Deutscher Fluglaermdienst) reports 790 stations round 56 airports in
  nine European countries and Canada, data open; whether any are in the UK
  was not established. The Open University ran a six-site citizen study at
  London City Airport with a phone app said to be accurate to about 2 dB.
  Heathrow publishes its own monitors.
- **The honest limits**: a network of that size needs institutional money
  and calibration; cheap microphones give indicative levels that must never
  be set beside DEFRA's as equals; telling aircraft from traffic needs
  flight-track data (the OpenSky licence question again); a device must send
  sound LEVELS only, never audio; and siting needs each host's consent.
- **The shape that could work**: a pilot, not a network - three to five
  sensors with one residents' group under one flight path for three months,
  with a partner doing the calibration, published openly, funded by a grant.
- **First steps, all free**: ask the German body whether it has UK stations
  and takes new ones; ask the Breathe London contact (introduced via the
  Earl's Court call) whether Imperial would partner or its nodes can carry
  noise; ask one residents' group whether it would host. A one-page pilot
  proposal is the artefact to write when Bill picks this up.
- **A possible host, not to be chased** (2026-10-03): the user near Norwich
  whose email led to the uncovered-postcode fix wrote that he would host a
  roof microphone with API access if he had the time, which he does not at
  present. Recorded so the offer is not forgotten; ask again only if a pilot
  is actually being set up.

### Parked, ready to build: how often planes fly (raised by Bill, 2026-10-06)

Bill: "can we not measure or get a source about how often planes come in and out of
certain airports". Chose AIRPORT-WIDE counts first, then parked them pending the CAA's
answer. **The source is CAA UK airport data, Table 03 Aircraft Movements** (annual
2025: a 6 KB CSV linked from the "Annual airport data 2025" page): every take-off and
landing per airport, split by type. **57 reporting airports, and all 15 UK airports the
product draws are in it.** Per day in 2025 (all types): Heathrow 1,315, Gatwick 720,
Manchester 556, Stansted 533, Luton 369, Birmingham 271, Bristol 213, East Midlands 164,
Liverpool 147, London City 139, Newcastle 133, Leeds Bradford 105, Norwich 72, Teesside
57 (only 11 commercial: the rest is training and flying-club traffic, which is noise
too, so show ALL movements and say "take-offs and landings"), Cardiff 46.

**THE LICENCE GATE, read from the CAA's page:** "No statistical data provided by CAA
maybe sold on to a third party. CAA insists that they are referenced in any publication
that makes reference to CAA Statistics." So: free surfaces only (front page answer, the
free on-screen report, credited), NOT the paid firm PDF or the B2B API, until the CAA
says otherwise. **Email drafted for Bill** (to `Aviation.Intelligence@caa.co.uk`,
`OneDrive/Desktop/caa-airport-data-email-2026-10-06.txt`): free use, paid use, and
whether a runway-direction or day/night split exists or can be commissioned. US airports
can use FAA counts (public domain) without that gate.

**How, when built:** `scripts/build_airport_movements.py --fetch | --write | --check`
(blocking) -> `data/airport-movements.json`, keyed by the AIP/FAA airport codes, with
the year and the CAA credit inside the file. The engine and the browser report read it;
the shared report module takes it as an OPTIONAL input the PDF script never passes, so
the paid PDF cannot carry it by accident. **Per-home frequency (N65)** is the step after:
the CAA's ERCD contours (the unsent `noise@caa.co.uk` request, 30 Sep) or a licensed
flight-track source (OpenSky needs a written agreement for commercial use).

### Parked idea: mobile and broadband coverage (raised by Bill, 2026-10-06)

Asked mid-way through the front-door work: "can we also factor in network
coverage or is that too much?" Answer given: possible, parked. **Ofcom publishes
mobile and broadband coverage by postcode** (Connected Nations: downloads, and an
API behind a free key) - from memory, NOT yet called, and its reuse terms are
unread, which is the first gate. **It sits outside the niche** Geovation advised
(flight paths, not breadth; Crystal Roof already sells the breadth). If it is
built, the Breathe London rules apply: **display only, never scored** (scores
are compared across cities), a fact on the panel and in reports, absent - never
"no coverage" - where it was not measured.

### Parked idea: light aircraft, leaded fuel and schools (raised by a user, 2026-10-03)

The same correspondent suggested a light-aircraft-only layer: piston aircraft
burn leaded aviation fuel, and he thinks it should not be flown over schools.
He also expects it would draw press and Hacker News interest. Kept for
reference; nothing is built or promised.

- **What is established** (searched 2026-10-03): a study commissioned by
  Santa Clara County of more than 14,000 blood samples from children living
  near Reid-Hillview airport found lead levels rising with proximity to the
  airport, higher downwind, and rising with piston-aircraft traffic; the
  county stopped the sale of leaded fuel at its airports in January 2022. The
  US EPA published a final finding in October 2023 that lead emissions from
  aircraft engines endanger public health, and the FAA and industry have
  pledged a lead-free fleet by the end of 2030. **Reid-Hillview is in San
  Jose, inside the four counties of our Bay Area coverage.** The UK position
  was not checked.
- **What we do not hold**: light aircraft mostly fly visually, off the
  published instrument routes the map draws, so there is no official line to
  plot. Showing where they actually fly needs track data (the OpenSky licence
  question again, and many light aircraft do not broadcast).
- **The version that could be stood behind**: no flight lines and no exposure
  estimate. A map of the airfields where piston aircraft are based (the FAA's
  airport records in the US; the AIP and the CAA's aerodrome list here)
  beside the schools within a stated distance (official school registers in
  both countries), citing the regulators' own findings. A statement of
  proximity, labelled as that.
- **The caution**: ROADMAP's rule for commissioned work applies - stay a data
  supplier, never a campaigner. The wording would need the same care as the
  noise pages: what is near what, from whose data, and nothing about any
  child's health.
- **Where it would fit**: as part of the Bay Area release, where the best
  evidence and a local audience both are, before any UK version.

**Ruled 2026-10-05 (Bill): "combinations of v2 and v3" - ASK FIRST, THEN THE TOOL.**
On a wide screen `/preview/` opens as v3 (the question and a large search centred
over the map, faded, its controls out of the way) and the first search, council-area
tap, city chip or `?city=` link turns it into v2 (panel at the side, map refitted
beside it). One class, `.is-intro`, inside the complement of the engine's `STACKED`
query, so tablets and phones (already stacked: question above, map below) are
unchanged. Built at `/preview/` first, by Bill's choice; making it the front page is
the separate step below. Gated in `tests/preview-home.mjs`.

Open, Bill's (the choice among the six is made: v2, 2 Oct; the v2+v3 combination, 5 Oct): whether it replaces `/` and where the full map
then lives (the same `index.html` runs in the native app, about twenty gates
and 103 area-page links assume the map at `/`); build under "Sky Score" or
after the rename. Audiences on every version follow the Constraints above.

### Open after the New York noise-layer repoint (2026-10-02)

- **`US_MAP_SERVICES.flood` and `.airQuality` are read by nothing**, yet
  `hazards.fema.gov` and `gispub.epa.gov` sit in the CSP and are listed in
  privacy.html, LICENSING.md and SUBPROCESSORS.md as hosts a visitor's browser
  contacts. Either wire the layers or remove the entries, the two CSP hosts and
  the three document rows together. Small; touches the privacy page, so Bill's
  call.
- **The BTS decibel breaks are unverified for the 2022 edition.** The tile
  service publishes no legend and bts.gov answers 403 to a script. Read
  BTS's page in a browser and confirm 45 / 50 / 55 / 60 / 70 / 80 / 90.
- ~~**Deploy.**~~ **DEPLOYED 2026-10-02 (17:24 UTC) on Bill's instruction and verified from the origin**: invalidation Completed, live `index.html` and `privacy.html` hash-equal to source, drift PASS (19 pages, 25 data files, 103 area pages), and the live New York map loads 2 tiles from `tiles.arcgis.com` under the corrected heading.

### Critical path

| Task | Deadline | Why | Status |
|---|---|---|---|
| **EPC API migration** to `get-energy-performance-data.communities.gov.uk` | **2026-05-30** (hard) | Old service shuts down; current `lambdas/epc/app.py` will 404 | **Done 2026-05-05**, deployed and verified live against `prod/epc?postcode=N1+7SX` (returned 72 real certificates, summary, pagination, OGL attribution). Bearer auth via `EpcBearerToken` SAM parameter sourced from `.env`. **Still pending**: token rotation on the dashboard + redeploy (the version in chat history is considered exposed). |
| Buildathon application (if eligible) | 2026-05-15 | Competition deadline | Awaiting Foundation reply |
| `/v1/score` Lambda extraction | 2026-05-22 | Unblocks both API track + buildathon pre-work | **Done 2026-05-05.** Plus on the same day: bulk endpoint (`POST /v1/score/batch`, up to 100 queries), NYC borough support, methodology v2.0 (iron-clad anchoring of every threshold), OpenAPI spec, Swagger UI, CORS opened to `*`. All verified live. Free-tier API key + Usage Plan (1000/month, 5 burst). |
| OGL attribution on data Lambdas | done | Required for any B2B sale | Done 2026-05-05, `epc`, `sold_prices`, `transport`, `nhs` now return `sources` array |
| Methodology document | done | Required for B2B audit / Buildathon judging | Done 2026-05-05, `METHODOLOGY.md` v1.0 |

### Flight-path corridors from the UK AIP - phase 2 (v5.3 follow-up, opened 2026-09-26)

v5.3 derived **London's** corridors from the AIP (`scripts/build_flight_paths.py`,
`data/flight-procedures.json`) and fitted `CORRIDOR_WEIGHT` against DEFRA
(`scripts/fit_corridor_weight.py`). The other cities still carry
runway-centreline corridors, now at the fitted weight. Each airport below is:
add it to `AIRPORTS` + `HOLDERS` in the builder, add markers around that city's
two constants, `--fetch`, eyeball it over its DEFRA GeoTIFF, `--write`, then
re-run the fit (the weight is fitted over ALL cities, so it can move).

**SURVEYED 2026-09-26 against AIRAC 2026-09-03 with the builder's own parsers.
The row this replaced said all nine publish "RNAV SID coding tables, as London
City"; that was an assumption, and it was false for seven of the nine.**

**RE-SURVEYED 2026-10-02 against AIRAC 2026-10-01 (every AD 2.24 chart titled
DEPARTURE, listed with the builder's own `fetch` + `chart_links`): the
classification below is unchanged.** Departure charts published: LHR 6, LCY 4
(+4 coding tables), BHX 6 (+3), NCL 3 (+1), MAN 6, LBA 2, LPL 5, BRS 3, EMA 3,
CWL 3, MME 0, NWI 0; no coding table at any of the six conventional airports.
London's three outer airports DO publish coding tables (LGW 5, STN 4, LTN 2),
so the existing `rnav-coding` method would draw part of their departures if the
outer-London corridor decision is ever taken. **New, and it changes the order
for the six:** the Heathrow method needs written routes in AD 2.21, and
counting that section's wording gives LBA 648 words with 12 track/turn/DME
terms and "Noise Preferential Routeings" named, BRS 801 / 11 / named, CWL 266 /
6 / named - but **MAN 1,751 / 2** (it refers to routeings "specified for each
runway" without giving them there), **LPL 785 / 3 / not named, EMA 1,752 / 7 /
not named**. So Leeds Bradford, Bristol and Cardiff look drawable from wording;
Manchester, the busiest, probably needs its charts read by hand. A term count,
not a reading of each sentence: read the section before promising a day each.

| Airport | City | Finals (AD 2.12 + 2.19) | Departures source | Verdict |
|---|---|---|---|---|
| **BHX** | West Midlands | parses | **RNAV SID coding tables, 8 routes, parse today** | do first |
| **NCL** | Tyne and Wear | parses | **RNAV SID coding tables, 3 routes (GIRLI), parse today** | do first |
| MAN | Greater Manchester | **23L has no ILS glide angle in AD 2.19** | conventional SIDs ("RNAV substitution only"), no coding tables | finals now; take 23L's angle from its RNP approach coding table (VPA), never a default |
| CWL | Cardiff | **12 has no ILS glide angle** | conventional SIDs | finals now; same VPA route for 12 |
| LBA, LPL, BRS, EMA | W Yorks, Merseyside, Bristol, Leicester + Nottingham | parse | conventional SIDs, no coding tables | finals now |
| MME | Teesside | parses | **no SIDs published at all** | finals only - that is the true answer, not a gap |
| NWI | Greater Norwich (API-only, 2026-09-27) | 27 from its ILS; **09 has neither ILS nor RNP**, so its NDB chart's RECOMMENDED PROFILE gradient (5.3% = 3.03 deg) - a third published source added to `read_glide` | **no SIDs published at all** | finals only, as Teesside |

- **Conventional SID chart PDFs do not extract**: pdfplumber returns mirrored,
  fragmented vector text (tried on MAN). The only route to those six airports'
  departures is the Heathrow one - geometrise the AD 2.21 noise-route WORDING,
  quoting each sentence - roughly a day per airport. Do it only if the v5.4 fit
  shows departure geometry moves the error; busiest first (MAN, then BRS/EMA).
  **The v5.4 fit answered that (re-read 2026-09-27): it does not.** Adding BHX
  and NCL departures left held-out error at 1.431 and the weight at 0.30,
  because DEFRA only maps the strip around each runway. So phase 2 cannot be
  justified on SCORING accuracy against the current yardstick; its case is the
  MAP (readers see approach lines and no departures - "no data for Manchester
  other than the approach lines") and the postcodes beyond DEFRA's strip, where
  there is nothing to fit against. If done: MAN only first, one day, one
  changeset, and measure the 17,926-postcode movement as v5.4 did. Better
  sequencing: after the CAA Heathrow contours arrive (a newer yardstick may
  reward departures where DEFRA 2021 cannot).
- **EMA feeds TWO cities** (Leicester and Nottingham); `AIRPORTS[...]['city']` is
  a single key and must become a list.
- **v5.4 IS DEPLOYED (2026-09-26, master `8cb8e31`) and verified from the
  origin: live `/v1/score` serves 5.4.** All nine
  airports' finals (MAN 23L / CWL 12 from their RNP charts' 3.0 deg VPA), BHX
  and NCL departures from coding tables, EMA feeding both Leicester and
  Nottingham. Measured: held-out error vs DEFRA 1.431 -> 1.431, fitted weight
  still 0.30; 5.2% of 17,926 sampled geometry-tier postcodes move, mean -0.02,
  0.3% by >= 1 point (nearly all under the new BHX/NCL departures); borough
  bands and area pages unchanged. Also fixes a PRE-EXISTING legend defect: in
  ten cities every line was drawn default blue under an orange AND a blue
  swatch; now one orange row per airport, empty rows hidden. Ship order when
  approved: SAM via a reviewed changeset, then `make.py data-deploy web-deploy
  demo-deploy` (openapi example changed), then verify from the origin.
- **Before v5.4, every one of these cities carried two runway-centreline "Approach"
  lines and no departures**, and Manchester draws one pair for two runways, so
  AIP finals alone are a real correction. Plan: **v5.4** = AIP finals for all
  nine + coding-table departures for BHX and NCL + refit `CORRIDOR_WEIGHT` +
  area-page rebuild; conventional-SID airports after, one at a time.

| Airport | City | Departures source | Note |
|---|---|---|---|
| LGW, LTN, STN | London | coding tables | London carries NO corridor for them today (removed 2026-05-07); adding one moves outer-London scores, so decide per airport after the fit |
| JFK, LGA, EWR | New York | FAA charts, not the UK AIP | out of scope; no DEFRA-equivalent measurement to fit against |

### From the first public feedback (r/dataisbeautiful, 2026-09-25/26)

Triaged against the code on 2026-09-26. **Shipped the same day**: AIP-derived
London paths (nebber: "look up the SIDs... nobody turns that early"); the
selected borough drawn as an OUTLINE, not a black fill (18 upvotes: "having a
selected area all black really gets in the way"); heliports drawn by their scored
traffic tier with place-name labels and a two-row legend (King's vs Battersea;
"What's King? What's BHL?"); London's legend naming the lines ("HEATHROW FLIGHT
PATHS" for "LHR PATHS"). Still open:

| Item | Why | Size |
|---|---|---|
| **Number-above metric (N65 / N70)** alongside Lden | Two readers: Battersea "one plane every 5 mins" and a noise-complaints officer - annoyance lives in how OFTEN, which an energy average hides. The CAA publishes N65 contours for Heathrow; nothing publishes it nationally | methodology decision; measure coverage first |
| **Time of day and flight altitude** (Geovation data clinic, 2026-09-30) | Geovation suggested time-of-day data and flight altitudes would make the aircraft figures more accurate. **Time:** Lden already penalises evening (+5 dB) and night (+10 dB) but publishes one number; a separate night figure (Lnight) would show it - check whether DEFRA's Round 4 WCS carries Lnight per airport before promising it. **Altitude:** DEFRA's contours already model it; only the geometry ESTIMATE ignores it (distance only). A cheap test with no new data: derive height along each final from its published glide path (already in `data/flight-procedures.json`) and score the change against the 35,352-postcode DEFRA validation set (MAE 1.879 today). Real tracked altitudes need ADS-B data, which is the OpenSky licensing problem again (open decisions). **MEASURED 2026-09-30, test half of the 26,233-postcode split used by `fit_corridor_weight.py`: altitude is NOT worth shipping.** Slant distance (published glide on finals; 0 / 3.3 / 5 / 7 / 10% assumed climb on departures, weight re-fitted each time) moves test MAE **1.431 -> 1.418-1.419**, under 1%, and makes Bristol, Leicester, Merseyside and West Yorkshire WORSE at every departure gradient. Why: finals are cut at 3,000 ft (0.91 km), so height rarely crosses a 1/2/4/6 km ladder step, and the corridor term is at most 1.2 points. **What the same run found instead: the AIRPORT term is a circle and noise is a strip** (the audit-C1 disc defect, in the geometry tier). Measured 3-15 km from the airport: MAE 1.30 within 15 deg of the runway axis, **3.70 at 30-60 deg, where the estimate reads 3.7 points too LOUD**. Making the airport distance runway-shaped, `sqrt(along^2 + (k*side)^2)`, fitted on train: **test MAE 1.431 -> 0.967, every city better** (Manchester 2.06 -> 1.00, Leicester 2.56 -> 1.22), bias +0.07, minimum bracketed at k = 8, w = 0.6 (k 6-8 all ~0.96-0.98). **Do NOT ship that k yet**: DEFRA only maps the strip, so a fit against it rewards shapes that hug the axis - the same warning `fit_corridor_weight.py` carries. Next: find truth OFF the strip (does a DEFRA nodata cell inside the raster extent mean "below 40 dB"? If so it is a quiet reading and can test the side of the runway), then refit, then a methodology version. The three measurement scripts were scratch work and are NOT in the repo; rewrite as `scripts/fit_airport_shape.py` (same crc32 split, same reproduce-the-engine guard) when this is picked up. **OFF-STRIP VALIDATION DONE 2026-09-30.** DEFRA's aircraft rasters hold NO below-floor zeros (unlike road); a blank cell inside a raster's box is ground below its lowest band. Floors MEASURED: 40 dB for London's region export, Bristol, East Midlands, Liverpool (blank = quiet exactly 10); **49 dB** for Birmingham, Manchester, Leeds Bradford, Newcastle (blank = quiet >= 7.8, a bound). Outside the box nothing is claimed, because EMA's and BHX's contours run off the file edge. That adds **164,690 exact and 14,902 bound readings** to the 26,232 on-strip ones. Results, all postcodes in each box (bias < 0 = estimate louder than DEFRA): today on-strip **1.44 (-0.30)**, below-40 **1.23 (-1.23)**, below-49 hinge **2.12**; **k = 4, w = 0.45: 1.12 (-0.24), 0.72 (-0.72), 0.18**, every city better. The narrow-strip risk did NOT show up off the strip: the estimate is still LOUDER than DEFRA there at every k tried, up to 8. It shows up ON the axis instead: on-strip bias 0-30 deg off the axis is about 0 at k = 4, **+0.26/+0.37 (too quiet) at k = 6**, and the share of readings the estimate puts >1 point QUIETER than DEFRA is 23.4% today, **18.5% at k = 4**, 23.2% at k = 6. **Recommended: k = 4** - the largest strip that is not optimistic anywhere measured, which also hedges the 2021 COVID understatement. ~~Gatwick, Stansted and Luton have no runway record in `flight-procedures.json` and stayed circles in this test; add them before shipping.~~ **Added 2026-10-01** as `not-drawn` records (runway axis only, no corridor, so no score moves; the twelve existing airports re-fetched byte-identical). Step 3 (v5.5, both holders) awaits go-ahead. **SCRIPTED 2026-10-01: `scripts/fit_airport_shape.py`** (about 20 s; advisory, needs NSPL + the eight GeoTIFFs). Both guards hold: at k = 1 it reproduces `calc_postcode_quiet` exactly and refits the shipped w = 0.30 at test MAE 1.431. **It reproduces the 30 Sep figures, and in doing so shows they were taken at a HELD weight**: `--w 0.45` gives 1.118 (-0.24), 0.715, hinge 0.173, 18.2% over all postcodes - the recorded 1.12, 0.72, 0.18, 18.5%. **Refitting w per k, as CORRIDOR_WEIGHT itself was set, changes the picture**: k = 4 refits to **w = 0.35**, test 1.092 (+0.05), axis bias **+0.17** (slightly optimistic), 24.5% read over a point quieter (worse than today's 23.3%); **k = 6 refits to w = 0.50**, test **0.983 (-0.01)**, axis **+0.02**, 20.2%, below-floor 0.711, hinge 0.011. So "6 turns optimistic along the axis" is true only with w held at 0.45. **The decision is now a PAIR (k, w)** and its rule goes in `recommend()` in the script (the TODO) before v5.5. **DECIDED AND BUILT 2026-10-01 as v5.5: k = 4, w = 0.50.** k = 6 / w = 0.50 was recommended first and approved, then withdrawn before anything shipped: per city it reads quieter than DEFRA in five of eight cities (West Midlands +0.66, West Yorkshire +0.35, Nottingham +0.29, Manchester +0.24, Leicester +0.21), invisible in the pooled -0.01 because London is 72% of the strip. A first per-city attempt ("no city more optimistic than the circle") rejected every shape, because the circle read most cities 0.9-2.0 points too LOUD and any accuracy gain moves toward zero; the rule that shipped is "no city may CROSS to quieter than DEFRA" (bias above max(circle, 0) + 0.05), each shape's weight fitted on train under it, then the lowest strip + beside-the-strip error. Held-out: strip 1.431 -> 1.141, beside 1.226 -> 0.770, every city better, every city's bias negative (Manchester +0.20 -> -0.16), >1 point quieter 23.3% -> 15.8%. 31% of sampled DEFRA-unmeasured postcodes move, mean +0.31 quiet | altitude: closed, no. Runway shape: **v5.5 DEPLOYED 2026-10-01 (k = 4, w = 0.50)**, verified from the origin |
| **A newer aircraft yardstick than DEFRA 2021** | "Massive difference between Chiswick and Feltham": DEFRA 2021 (a COVID year) puts W4 2PJ and TW13 4AA 0.5 apart (7.3 vs 7.8), and the raster outranks the geometry, which separates them (4.8 vs 2.8). Candidates: the CAA's annual Heathrow contours (ERCD). The fitted weight must be refitted against whatever replaces it | research first |
| **DEFRA aircraft layer on the map outside London** - **DEPLOYED 2026-09-26 (master `8cb8e31`), verified from the origin** | "No data for Manchester other than the approach lines" - seven per-airport rasters were LOADED for scoring but never PAINTED. `scripts/build_aircraft_rasters.py` renders DEFRA's own layer over each covered city's box (boundary + airport) into `data/aircraft-noise-<city>-lden.png` (11-18 KB each), generates the site's `AIRCRAFT_RASTERS` table from the checked-in JSON, refuses a blank render, and drops a neighbouring airport's contour where the box edge cuts it (Liverpool's tip on Manchester's map). Blocking stage `aircraft rasters == DEFRA renders`, proven red on a blank PNG and on a moved box; `check_noise_legend.py` now also asserts every city PNG paints only legend colours. The seven cities' legend copy said 'runway geometry, NOT DEFRA' - rewritten to say what is drawn, keeping each airport's measured footprint ratio. Teesside is not in Round 4. Ship: `make.py data-deploy web-deploy` (data first - the page references the PNGs). Expect a small `index.html` merge conflict with v5.4 (adjacent registry lines) | done, awaiting deploy |
| **"Outdoor exposure" in the copy** - **done on `ship-v54-and-defra-layer` (2026-09-26)** | A Hounslow resident: with double glazing you hear them only outside. Lden is a facade/outdoor quantity; the labels did not say so. Now on the quiet-score line, every legend explainer, the API page and METHODOLOGY | done |
| **COVID understatement measured** - **done, same branch** | Heathrow 55 dB Lden: DEFRA 2021 **75.6 km²** vs CAA 2024 **148.4 km²** (ERCD 2501 Table 12) - about half. Published as a caveat, never a correction; `scripts/measure_covid_understatement.py --check` is blocking and reds if a page stops quoting the JSON. `CORRIDOR_WEIGHT` marked provisional: it is fitted against the same 2021 map | done |

#### Option C: CAA 2024 contours as the London aircraft layer - the drawbacks, measured 2026-09-26

The CAA's ERCD Report 2501 carries Heathrow's 2024 Lden, Lnight, N65, N70 and N60
contours, from a normal year (traffic 0.5% below 2019). It is the best available
fix for the COVID understatement and the only source for N65. What using it
would actually involve, from inspecting the report rather than assuming:

1. **There is no data, only pictures.** The 41 Appendix B figures are embedded
   raster images (e.g. 1338x1892 px), not vectors: pdfplumber finds zero curves.
   Each shows contour LINES, 2024 in black overlaid on 2006 in red, broken by
   circled dB labels, on a grey Ordnance Survey basemap, with **no coordinate
   grid**, only a scale bar. Digitising means colour-separating thin lines from
   a busy basemap, closing broken polygons, assigning levels by nesting, and
   georeferencing by hand from road junctions. Positional error is unmeasured
   and likely tens of metres or more, which matters when the product's claim
   is postcode precision.
2. **Two licences, neither OGL.** The contours are CAA/airport material (the
   reports say contours from 2016 are commissioned and published by the
   airports), and the figure prints "Crown copyright ... Ordnance Survey
   Licence number 100016105": data digitised from an OS-based figure raises
   OS derived-data rights too. Every input today is OGL, which is both the
   product's public-sector pitch and what `terms.html` and the `sources`
   array promise integrators. A non-OGL input breaks that unless licensed.
3. **It REMOVES data below 55 dB.** The Lden contours start at 55 dB. Measured
   on DEFRA's Heathrow raster: **62% of its mapped area (124.2 of 199.8 km²)
   lies below 55 dB**, which is where most of London's exposure is and where
   the ramp still grades quiet. Swapping sources would drop those readings
   back to the geometry estimate; blending the two (2024 above 55, 2021
   below) puts a model seam exactly at 55 dB.
4. **Heathrow only, in practice.** ERCD covers Heathrow, Gatwick and Stansted;
   Gatwick's and Stansted's contours barely reach any borough we score. So
   London would move to 2024 while every other city stays on 2021, and
   **cross-city comparisons would reflect vintage, not noise** - the exact
   incomparability methodology v5.0 was built to remove.
5. **It would silently re-scale every other city.** The aircraft ladder divides
   each airport's DEFRA footprint by Heathrow's (`LHR` = 1.000). Doubling
   Heathrow's footprint from 2024 data while the others stay 2021 would halve
   every other airport's ratio and make every other city quieter overnight.
   Footprint scaling would have to stay on DEFRA even if the layer moved.
6. **Everything downstream re-fits.** The corridor weight, the published
   estimator error, borough bands, area pages and the quiet validation set
   are all defined against DEFRA; each would need re-deriving, and a
   methodology version.
7. **Annual, manual, and superseded.** A new PDF each August, re-digitised by
   hand, with no API. DEFRA Round 5 (due 2027, OGL, every airport, a
   representative year) replaces it for free - so C is likely one to two
   years of value for the largest piece of work on this list.

**Verdict: do not digitise.** Ask for the GIS files and a licence (drafted:
`OneDrive/Desktop/caa-ercd-data-request-2026-09-26.txt`, logged in
OUTREACH_LOG). If they arrive as vectors with reuse rights, points 1 and 2
disappear and **C-lite** becomes worth doing: draw the 2024 55 dB outline over
London's map as a labelled "normal-year extent" line, scoring nothing, plus N65
as a displayed overlay. That answers the Chiswick/Feltham and Battersea
comments visually without touching points 3-6. Scoring on it waits for Round 5.

### Audit backlog, 13 Sep 2026 - the 24 Importants, in the order to take them

Full detail per item in `AUDIT_REPORT_2026-09-13.md`. Grouped by what each
tier protects; each tier is a preflight + commit, and tiers 2-4 need a deploy.
Strike a row here when it closes, and close it BY NAME in the report.

| Tier | Items | Why this order |
|---|---|---|
| ~~**1. Roll safety**~~ **CLOSED 2026-09-13, same night** | ~~I6, I7, I8, I10, I15~~ - each proven red before the fix and green after; no deploy needed (scripts, Makefile, preflight runner). | The July roll can now be done as documented: `--check --all` (which also asserts the constant), `--write --all` (both holders, every city), rebuild area pages, deploy backend first. |
| ~~**2. Live false statements**~~ **CLOSED 2026-09-13, same night, deployed** | ~~I3, I4, I9, I24, I5, I20, I23~~ - every notice, caption and weight now DERIVED from the holder that knows (contour status from the geometry registry; the postcode line injected per UK city; applied weights rescaled as scored). Guarded through `resolve_query` / `handle_environment`; area pages rebuilt. | The same class as both of this audit's Criticals; the product's standing rule is that absence and estimates must never render as measurements. |
| ~~**3. User-facing frontend**~~ **CLOSED 2026-09-13, same night, deployed** | ~~I1, I2, I19, I21, I22~~ (+ M35) - the responsive gate gained a layers-open state (78 combinations), red on the deployed page and clean on the source. | Measured, reproducible, on the primary flow. |
| ~~**4. Backend robustness + security**~~ **CLOSED 2026-09-13 bar I17, deployed** | ~~I11, I12, I13, I14, I18~~ - 18 red on the committed Lambdas, green on the fix; the two dead workflows deleted. **I17 is a decision row in Open decisions** (verification email, or two lesser options). | Each is a runtime or documentation defect; I17 is the one that needs a decision before code. |

Then the 37 Minors, which the report lists with file:line. **14 of 37 closed
as of 2026-09-14** (M14 partial and M35 on the 13th; M4, M5, M8, M9, M10, M11,
M12, M18, M21, M25, M26 and M29 on the 14th, **deployed and verified from the origin the same afternoon** (SAM: five Lambdas UPDATE_COMPLETE; CORS from `capacitor://localhost` echoed live; Cardiff and Truro road notices live; drift 133 of 133) - the two gate-shaped ones first,
then the "absence rendered as a measurement" one, then the comment-drift
cluster in one pass; each struck BY NAME in the report). **Still open, 23:**
M1-M3, M6, M7, M13, M15-M17, M19, M20, M22-M24, M27, M28, M30-M34, M36, M37,
plus M14's chat-400 remainder. ~~The a11y five (M30-M34) are one pass with the
two contrast gates run after~~ **M30-M34 closed later the same day (19 of 37)**:
each proven red on the committed page, two gates widened (`favourites-keyboard`
+5 checks, `responsive` +1 state +1 detector, `page-has-heading-one` now
blocking). **Then M19, M20, M22, M24, M27, M28 (25 of 37)**: both loaders
hard-fail on schema drift and on an empty full run, checkpoint at the top of the
loop, and refuse `--limit 0` (measured doing a full 2.7M-row dry pass); the
aircraft runbook verifies from the origin; `airQualityCoverage` joins its two
siblings. **Then the backend error-path cluster M2, M3, M13, M15, M16 (30 of
37)**, held by `backend/tests/test_error_paths.py`, 9 of 9 red on the committed
Lambdas. **Then M17, M36, M37 and the fixable halves of M1, M6, M7 (36 of
37 closed or converted)**: M1, M6 and M7's repo-settings half are DECISIONS,
each with a row in Open decisions below. **Still open: M14's chat-400
remainder** (chat reports a ScoreFunction crash as a 400 "could not be
resolved") - and the three decision rows.

### Legal & entity — blocks the first pilot invoice (raised 2026-08-04)

> ## ⛔ THERE IS NOTHING TO INCORPORATE
>
> **Cubitt33 Ltd (13651304) has existed since 2021.** It is already the named
> operator and data controller on the **live** `privacy.html`, and in
> `terms.html`, `LIA.md` and `SUBPROCESSORS.md`.
>
> This has now surfaced as a to-do **three times** — it blocked the ICO fee for
> two days in August, and was raised again as planned work on 2026-08-08. The
> struck-through row below is invisible when scanning a long table for what to
> do next, so the ghost keeps returning. **The stale record is what does the
> damage, not the missing work.**
>
> **The real company tasks are exactly two:**
> 1. **Sign the IP assignment deed** (`Desktop/CUBITT33_IP_ASSIGNMENT_DRAFT.md`)
>    — must be a **deed**, no consideration, witnessed by a **non-cohabitee**,
>    ODbL/OGL carve-out at clause 5. Dad to confirm connected-party tax
>    treatment first. Without it the company would be selling IP it does not
>    own, which is a standard diligence failure the moment a pilot lands.
> 2. **Pay the ICO fee, £52.** The controller decision that blocked it is
>    settled and already public. Nothing is left to decide.


### Legal items - RECOMMENDED SEQUENCING, 2026-09-04

**Two of the three are gated on a pilot that has not started.** Outreach has
never been sent - 0 of 5 drafts since 21 May. That reframes the priority: these
read like blockers, but the bottleneck is upstream of all three.

1. **ICO fee, GBP 52 - PAY NOW**, in Cubitt33 Ltd's name. Genuinely unblocked
   since 2026-08-07, and re-raised as open work three times since. It is the
   only one of the three carrying **live** exposure, because signup processes
   email addresses today. **This may be larger than recorded**: the Signup
   CloudWatch log group holds 2,671 bytes and `privacy.html` section 2b
   discloses DynamoDB and API-key metadata, not CloudWatch. If those bytes
   contain addresses it is an Article 13 gap on top, and worth establishing
   BEFORE filing, since it changes what is disclosed. (The group was created
   2026-08-21, so the "26 Jun - 23 Jul" range in the gate's warning text is
   stale prose, not a live finding.)
2. **IP assignment deed - worth doing, not urgent today.** Still waiting on
   Dad's confirmation of connected-party tax treatment. It becomes a diligence
   failure when a pilot lands, not before.
3. **Solicitor review of `terms.html` - DEFER** until a pilot is actually in
   prospect. Paying for review before a single outreach email has gone out is
   spending ahead of the risk.

**If the pilot track matters this quarter, OUTREACH is the item, not the
paperwork.**

**Not legal advice; these are verified gaps.** Full reasoning in
`memory/project-legal-liability-gaps.md`.

| Task | Why | Status |
|---|---|---|
| **Log retention, then correct `privacy.html` §2d** | **NOW THE FIRST ITEM (raised 2026-08-05). The only gap that is live and false rather than merely missing.** `privacy.html` publicly states server logs are "retained for 7 days then automatically deleted"; all 13 log groups are verified `retentionInDays: None`. It also describes **API Gateway logs that do not exist** (no such log group, no `AccessLogSetting` in the template) and calls "anonymous" a Signup group that held raw emails 26 Jun - 23 Jul and **still holds 8,730 bytes**. Art 13(2)(a) transparency on top of Art 5(1)(e) storage limitation, and it now **contradicts `SECURITY.md` in public** | **CLOSED 2026-08-07. Performed and verified against the AWS API, not the console.** The deploy policy was widened (`FlightMapDeployPolicy`), **7 log groups deleted** (5 orphans, the stale `ChatFunction-wzeXuMdafiCz` generation, and the `SignupFunction` group holding the raw emails, which is deleted rather than aged out because retention would have *preserved* them), and **30-day retention set on the 7 live groups**. `privacy.html` §2d now reads 30 days and `scripts/check_log_retention.sh` passes. Two things this uncovered: the count was **14 groups, not 13** (restoring `chat` added an eighth function and orphaned its predecessor), and **`privacy.html` states the retention claim TWICE** - the sub-processor table at line 263 still said "indefinitely" and the gate could not see it, since it parsed §2d alone. A self-contradiction guard was added and proven red against that exact bug. **Residual:** Lambda recreates a deleted group with no retention, so the signup group returns at *Never Expire* on the next signup; the gate catches it, but the durable fix is declaring retention in `template.yaml`. |
| **Terms / liability page** | **The actual gap, and the assumed protection does not exist.** A repo-wide search for `no warranty`, `as is`, `limitation of liability`, `not liable`, `not advice`, `terms of use` returns **zero hits**, and there is no terms page. What was believed to be the disclaimer is `METHODOLOGY.md` §18 — a *regulatory-scope* note ("not regulated under the Estate Agents Act 1979") that says nothing about accuracy and lives in a GitHub file, not on any page a user reads. **"Informative not instructive" is a sound argument for the free site and inverts for the paid pilot**, which supplies every element it depends on being absent: an identified client, a jointly-defined success metric, founder integration support, and a day-90 written evidence report. Caveat: UCTA 1977 s.2(2) limits negligence exclusions to what is *reasonable* and CRA 2015 s.62 applies a fairness test, so an over-broad exclusion is **void rather than weak** — draft for a solicitor to review, not to replace one | **DRAFTED 2026-08-05** as `terms.html`, source-only. Covers informational-not-advice, no accuracy warranty, acceptable use, ODbL/TfL attribution pass-through, liability capped at fees paid, with the UCTA s.2(1) carve-out and CRA 2015 statutory-rights preservation. Linked from both `index.html` footers and `privacy.html`; added to the em-dash, html-validate, a11y and deploy-drift gates. **DEPLOYED. `/terms` returns 200 and `deployed == source` passes on all 16 surfaces (re-measured 2026-08-26). This row said "then deploy" for three weeks after the page went live. **Still needs: solicitor review** — that half is genuinely outstanding** |
| **ICO data protection fee** | Sole traders electronically processing personal data must pay unless *wholly* exempt; the exemptions apply only where processing is for those purposes **only**, and signup email also serves abuse prevention and rate limiting. **Tier 1 £52/yr**; non-payment risks up to £4,000, typically ~£400 at that tier. Nothing in the repo mentions registration | **SELF-ASSESSMENT COMPLETED 2026-08-05. Outcome: fee payable, TIER 1, £52/yr** (£47 by direct debit). Answers on file: public authority no · currently trading **yes** (the test is commercial *purpose*, not income) · not-for-profit no · using personal information yes · electronically yes · controller yes · legal/financial no · health/education no · **property services no** (the listed activities all turn on holding tenant/resident data; scoring places is not providing property services) · software development yes · sole trader · not a charity · no existing registration. **NOT YET PAID. The stated blocker no longer exists (revised 2026-08-07)** — it was "sequenced after incorporation", and there is nothing to incorporate; Cubitt33 Ltd has existed since 2021. ~~**What it is actually waiting on is the controller decision**~~ — **SETTLED 2026-08-07 and this row did not say so until 2026-08-26: the controller is CUBITT33 LTD (13651304).** Verified live the same day: `skyscore.co.uk/privacy` already names the company as controller. So the fee is due **in the company's name, now**, and it does **not** wait on the IP assignment deed — controllership turns on who determines the purposes and means of processing, which a sole director decides today; companies routinely control processing using software they license rather than own. **This stale row sat on a £52 payment for nineteen days while the answer was already recorded in `memory/project-legal-liability-gaps.md`.** Third time this same ghost has been re-raised as open work. That single answer also decides the three entity lines in `privacy.html` §1, `terms.html` §1 and `SUBPROCESSORS.md` §1 (replacement text already commented out beneath each), and whether the IP assignment deed needs to be signed first — the company cannot honestly be named as controller of a service whose IP it does not yet own and does not operate. Registering the wrong entity is worse than registering late, because the ICO register is **public** and an entry naming Bill personally publishes a home address. Tier 1 £52 either way. **Every day unregistered is live exposure**, so this decision is now the whole cost of the item |
| ~~**Incorporate**~~ | Already the documented entity gate on the kickoff invoice (`OUTREACH_DRAFTS.md`). **Caps liability going forward only** — no retroactive cover for anything already published, and no shield from data-protection enforcement where you are the controller. `privacy.html` names Bill personally as operator and controller | **SUPERSEDED same day — see "Entity SETTLED 2026-08-05" below.** There is nothing to incorporate: **Cubitt33 Ltd (13651304) already exists**, carries no liabilities, and Sky Score becomes a trading name of it. This row sat unamended for two days saying incorporation was "the FIRST legal action" while the section below said it was unnecessary, which left the ICO row blocked on a task that had already evaporated. The real gate it was standing in for is the **controller decision** — see the ICO row |
| **Legitimate Interests Assessment** | `privacy.html` relies on Article 6(1)(f) and `METHODOLOGY.md` cites the ICO's LIA guidance, but **no LIA document existed** | **DRAFTED 2026-08-05** as `LIA.md`. **Narrower than recorded here**: `privacy.html` relies primarily on **6(1)(b)** for key issuance, so the assessment covers only the 6(1)(f) processing (one-key-per-email, rate limiting, abuse investigation). Its §6 records that the balancing test is **conditional until log retention is actually bounded**, rather than asserting a conclusion the infrastructure does not support |
| **Trade mark search on "Sky Score"** | Sky Ltd defends "Sky" marks aggressively (*Sky v SkyKick* reached the UK Supreme Court). The name is now on the App Store, a domain, and about to go in front of financial institutions — a free UK IPO search before the next pitch round is cheap insurance | **DONE.** Bill searched SKY SCORE on 2026-08-05 (result: one letter from `SKY STORE`, Sky Ltd, classes 9 and 42 — rebrand decided). The CUBITT33 side was searched 2026-08-27: **both class-9 "blockers" are audio equipment and neither is in class 42**, so the recorded "borderline" basis dissolved. **Next step is unchanged: attorney opinion, never file first.** Not a clearance search — a word-level sweep and a class-42 check remain. |
| ~~Patent~~ | **Settled 2026-08-04: no.** `METHODOLOGY.md` has been public for months and the UK/EU apply **absolute novelty** with no grace period, so the window closed on publication. Likely excluded anyway under Patents Act 1977 s.1(2) (mathematical methods, programs for computers "as such"), and secrecy fights the "audit-defensible methodology" positioning that *is* the B2B pitch | **CLOSED, no action** |

**Data exposure itself is genuinely low and well designed** — the only personal
data held is signup email addresses plus an optional display name; browsing and
scoring require no account and device tokens are opaque. The gaps above are
paperwork, not architecture.

### Entity SETTLED 2026-08-05 — Cubitt33 Ltd, no incorporation needed

**`CUBITT33 LTD`, company 13651304** (inc. 29 Sept 2021), confirmed by Bill to
carry **no liabilities, debt or stock**. Also owned: `CUBITT INTERNATIONAL LTD`
(11724515, inc. 2018). Both currently declare **SIC 47990 "other retail sale not
in stores"**.

Using the existing company beats a NewCo because **the carve-out cost is
proportional to what has accumulated, and that is currently nothing** — one
pilot contract later is a one-page novation; fifteen contracts plus revenue is a
project. Sky Score becomes a **trading name** of Cubitt33 Ltd.

**SWITCHED IN SOURCE 2026-08-07, not yet deployed.** `privacy.html` §1,
`terms.html` §1, `SUBPROCESSORS.md` §1 and `LIA.md` now name **CUBITT33 LTD,
company 13651304, registered office 50 Pembroke Road, London W8 6NX**, confirmed
against the Companies House public record. It was called a three-line change; it
was four, because `LIA.md` names the controller in its header. The **footer
copyright on both HTML pages still reads "Bilal Khizar" deliberately** —
controllership follows who decides the purposes and means of the processing and
has moved to the company, while copyright follows authorship and does not move
until the IP assignment deed below is signed. Two tests, two answers, both true
at once.

**The ICO registration must now be in the company's name**, and should follow
promptly rather than sitting behind the deed: the pages say the company is the
controller, so the company is the entity that owes a registration.

| Task | Status |
|---|---|
| **SIC → `62012` + `63110`** | **NOT DONE (checked against Companies House 2026-10-06): the 8 Sept 2026 statement was filed on 28 Sept "with no updates", so the register still says 47990 retail. Fix: file ANOTHER confirmation statement now with the new codes - Companies House charges the annual fee once per 12-month period, already paid.** Original plan: on the confirmation statement due **8 Sept 2026** (by 22 Sept). Free, normal filing, one conversation with Bill's father who is the accountant. **A SIC code is a statistical classification, not a permission — a pilot signed before then is fine**, and a statement can be filed early if wanted |
| **Dormant to trading** | **NEW 2026-10-06.** Cubitt33 Ltd has filed DORMANT accounts every year (2022-2025, last to 30 Sept 2025, filed 27 Dec 2025). The first revenue ends that: tell HMRC it is trading for Corporation Tax (within 3 months of starting), and the accounts for the period trading starts are not dormant ones. If the company has paid anything this year (AWS, domains), the year to 30 Sept 2026 may already not be dormant. Costs paid personally: keep receipts (director's loan). For Bill's father (the accountant) before the first invoice | Before the first GBP |
| **IP assignment** | **DRAFTED** at `Desktop/CUBITT33_IP_ASSIGNMENT_DRAFT.md`. Sky Score's IP is owned by **Bill personally**; Cubitt33 owns none of it, so the company would be selling what it does not own — a standard diligence failure. Must be a **deed** (no consideration), signed and **witnessed by a non-cohabitee**, with the ODbL/OGL third-party carve-out at clause 5. **Dad to confirm connected-party tax treatment before signature** |
| **Article 28 DPA** | **NEW GATE, not previously listed.** The pilot's headline deliverable is "score your whole book" (`scripts/score_bulk.py`). The moment a customer sends a CSV of addresses we process **their** personal data on **their** instructions, making us a **processor** — Art 28 requires a written contract *before* processing starts. `SUBPROCESSORS.md` is most of the disclosure it needs |
| **PI insurance** | **DECIDED 2026-10-06: NOT BOUGHT** - Bill: no conventional insurance, for the same reason as no conventional lenders. Options (data-supplier contracts with a liability cap, takaful enquiry, a company reserve, low-risk design): OUTREACH_TARGETS.md "Without conventional insurance". Original note: **NEW GATE.** A £2,500 engagement producing a day-90 written evidence report is advisory-shaped. A liability cap says "no more than X"; PI is what makes X payable, and procurement may ask for evidence of cover |
| **Apple Developer account** | Personal, not corporate — the iOS app belongs to Bill. Moving it needs Cubitt33 enrolled as an *organisation* (D-U-N-S number) then Apple's app transfer. **Longest lead time on the legal list** |

### Rebrand DECIDED 2026-08-05 — Sky Score must go; CUBITT33 named as the likely choice 2026-08-08

**2026-08-08: Bill named CUBITT33 as the likely name.** Recorded as a direction,
not an execution: nothing is renamed and nothing should be filed yet.

**The premise needs one qualification.** "Free to be trademarked" is stronger
than the search found. `cubitt33` **as one string** returned nothing on
similarity search — that part is real and is why it beat ~80 alternatives. But
its **components are occupied in class 9**: `Cubitt` (UK00004145719, Jan 2025)
and bare `33` (UK00003649225, 2021). The 5 August verdict was **"borderline, not
clean"**, and the distinction changes what to do next, because filing is
irreversible in a way searching is not.

**Order of operations, and it matters:**

1. **Read `UK00004145719`** — who owns `Cubitt` in class 9, and for what goods.
   Free, private, notifies nobody, and still not done. If the goods are distant
   (spectacles was the guess) that is a strong argument and it changes what the
   attorney is being asked. Automated fetch returns **403**; open it by hand.
2. **Buy `cubitt33.co.uk/.com/.io`** (~£30, private). All three showed no A
   record on 8 Aug — but DNS proves nobody is *using* them, not that nobody has
   *registered* them, so confirm at a registrar.
3. **Then** the attorney opinion (£150–300), with the class 9 goods in hand so
   the spend buys judgement rather than a lookup.
4. **Do NOT file first.** The UK IPO notifies earlier rights holders when an
   application publishes, so filing `CUBITT33` in class 9 puts a notice in front
   of whoever owns `CUBITT` and opens a two-month opposition window. The cheap
   test is also the one move that summons the most likely opponent.

**Do not execute the rename before 13 August.** Stay Sky Score through the 10
and 13 Aug events — those are conversations, not contracts, and Deen Developers
have publicly named it. The deadline is **before outreach begins**. Execution is
a one-word swap across ~560 occurrences with AWS untouched, so it is cheap
whenever it happens and there is no gain in going early.

**No legal work waits on this.** ICO, IP assignment, SIC codes, pilot contract
and insurance all proceed as Sky Score / Cubitt33 Ltd.


**On Bill's own IPO search:** `SKY SCORE` is **one letter from `SKY STORE`**,
which **Sky Ltd** holds registered in **classes 9, 16, 28, 35, 36, 38, 41, 42
and 45**. Classes 9 and 42 are ours. Same shape as **SkyDrive → OneDrive** and
**Skyscape → UKCloud**, both forced rebrands. Secondary reason independent of
law: the name describes aircraft noise while the product scores five components.

**Work this decision GATES — check this list before starting anything that puts
the name somewhere new (added 2026-08-07).** The rebrand was decided on 5 August
but the open-task lists elsewhere in this file were never re-triaged against it,
so items kept surfacing as "ready" that should not be done at all. Two were
caught on 7 August only because they were questioned:

| Held item | Why the rebrand gates it |
|---|---|
| **Play Store / Android release** | Play is the one platform the mark is not yet published on. Submitting extends a contested mark to a new surface for a binary carrying nothing the web app does not already serve. |
| **`api.skyscore.co.uk` DNS CNAME** | The point of a branded API hostname is that integrators hardcode it, so it only pays once customers depend on it, which is exactly when the name must already be final. Publishing it now means migrating customers twice, and a customer's hardcoded base URL is far harder to change than an app update. Nothing public references it today (checked 7 Aug: no HTML, no OpenAPI spec, no JS), the raw execute-api URL keeps working, and the unused APIGW custom domain costs nothing to leave sitting. |

**Rule of thumb:** if a task's value comes from *other people depending on the
name*, it is gated. If the value is internal or the name is incidental, it is not
(the retention work, the IAM grants and the MFA device were all correctly done
while the name is unsettled).

**Full detail, method, kill list and taste profile: `memory/project-rebrand-sky-score.md`.**
Headlines:

- **Leading candidate `CUBITT33`** — company already owned, all domains free,
  clean as a whole string, but `CUBITT` and `33` are separately registered in
  class 9, so it is **borderline rather than clean**.
- **DO NOT FILE any mark before an attorney opinion.** The IPO notifies earlier
  rights holders when an application publishes, so filing is what alerts them.
  This is the one candidate worth £150-300 of attorney time.
- **Buy `cubitt33.co.uk/.com/.io` regardless** — private, ~£30, nobody notified.
- **Timing: stay Sky Score for the 10 + 13 Aug events; rename before outreach
  begins.** Cold approaches to Tier 1 aggregators are a resource spent once, and
  renaming after signed pilots means novating contracts.
- **No legal work waits on the name.** Execution is a one-word swap across ~560
  occurrences; AWS is untouched (all `london-flight-map-*`); the App Store
  rename rides a future native build for free.
- Tooling built this session: **`scripts/check_name.py`** screens domains and
  Companies House by SIC code. The IPO register is the authoritative step and
  has **no public API**. Search the **root**, filter to **classes 9 and 42**.

### Outreach — NOTHING HAS EVER BEEN SENT (measured 2026-08-08)

**`OUTREACH_LOG.md` holds five Tier 1 targets, all dated 21 May, all still 🟡
"Draft ready" or "To draft". Eleven weeks. Zero sent. The signups table holds
one row**, which is a test.

One identified route has already expired in the interval: the log names a
divisional director at Landmark as a panellist at the **Bold Legal Group Conference, 17
June**, calling it the best route. That passed seven weeks ago. **Identified-but-
unsent decays** — the same shape as the DEFRA loaders, work correctly specified
and never actually run.

**The blocker was real but narrower than applied.** "Rename before outreach" is
right for **cold** channels — a first impression is spent once, and burning
Landmark under a name being retired is a genuine cost. It does **not** apply to
warm ones:

| Channel | Now, or wait? |
|---|---|
| Cold email / cold LinkedIn | **Wait for the rename.** Spent once. |
| Warm intro, events, in-person | **Go now.** A relationship survives a rename; "we're rebranding next month" reads as momentum. |

So the events, and the six LinkedIn connections from Build Night 1, were never
blocked by anything. That is also the highest-converting channel — this file's
own line is *"One warm intro beats 20 cold emails."*

**Before any email goes out at all:** confirm **DKIM** is configured. Five good
drafts landing in spam folders spends them for nothing.

| Task | Deadline | Why |
|---|---|---|
| 2 warm-intro asks (LinkedIn 1st/2nd connections at Al Rayan, StrideUp, Landmark, Climate X) | 2026-05-08 | One warm intro beats 20 cold emails |
| 2 cold emails using Tier 1 + Tier 2 templates | Weekly from 2026-05-12 | Build response sample size |
| Chase Emergent Ventures if no reply by 2026-05-12 | 2026-05-12 | Stated response window passing |

### Polish (non-blocking)

| Task | Deadline | Why |
|---|---|---|
| Re-run `/audit` | next due ~2026-06-07 | Catches drift; last refresh 2026-05-07 |
| Methodology doc for the API | 2026-05-29 | Required for serious B2B conversations |
| **`support@` email — VERIFY, do not build (corrected 2026-09-08)** | — | **Cloudflare Email Routing is already live**: `skyscore.co.uk` MX points at `route1/2/3.mx.cloudflare.net`, measured 2026-09-08. So this is a 30-second dashboard check that the `support@` alias exists, **not the ~25-minute setup this row claimed for four months**. Worth checking rather than assuming: the address is published in `.well-known/security.txt`, `api/index.html` and `index.html`, and it is in the Apple review notes, so a bounce during review is expensive. What MX cannot show is whether that specific alias is routed. Steps in `memory/project_email_setup_todo.md` |
| **Billing alarm — NOT CREATED (found 2026-09-08)** | — | `OPERATIONS.md` §7 stated "Billing alarm is set at $20 USD as a tripwire"; measured, there are **zero CloudWatch alarms in `us-east-1`**, the only region `AWS/Billing` publishes to. Three alarms exist in `eu-west-2` and are operational, which is why it looked covered. Console task, steps in `AWS_BILLING_ALARM_SETUP.md`. Check the Billing console for an AWS **Budget** first — `budgets:ViewBudget` is denied to `flightmap-dev`, so a Budget could exist unseen |
| **Second MFA device** | — | Recorded in `memory/project-aws-console-lockout.md` as **the top outstanding action** and not previously in this table. One factor with no fallback on the account that holds S3, DynamoDB, Lambda and CloudFront. ~5 minutes in IAM |
| **v1.1 native release** (iOS + Android) | **post-Apple-approval** | iPad widths addressed in Wave 13.20 (2026-05-18). Still open for v1.1: (1) iPhone-width layer-toggle UX (legend cramps map on mobile, ~32% of 414px viewport) (2) app icon redesign deferred until conversion data is available (current orange-radar shipping in v1.0.1+). See `memory/project_mobile_ux_redesign_v1_1.md`. |
| **Codemagic cert persistence** | **before build 13** | Apple's 2-cert-per-Personal-Account limit hit during v1.0 ship (build 11 failed, build 12 succeeded after revocation). Generate cert private key once, store base64-encoded as Codemagic env var. Otherwise next signed build hits the wall. Pattern documented in `memory/feedback_codemagic_personal_account_signing.md` ("Future iteration to plan for"). |
| **Play Store / Android side** | **HELD until the rename lands (decided 2026-08-07)** | Build AAB locally via Android Studio per `mobile/ANDROID_BUILD.md`. Same `index.html`; reuse v1.0 metadata + screenshots. **Technically unblocked** — keystore, Android Studio JBR and `mobile/node_modules` all verified present on this machine, and `mobile/www/` is stale by exactly the 6 Aug wave. **Deliberately not built.** Play Store is the one surface "Sky Score" is *not* yet published on, and the mark is being retired because it sits one letter from Sky Ltd's registered `SKY STORE` in classes 9 and 42. Submitting would extend the contested mark to a new platform while the exposure is open, for a binary that adds nothing the web app is not already serving. Revisit the day a name is chosen; the build itself is under an hour. |
| Consumer-site granularity-wall pass | 2026-06-15 | Protects API channel before serious sales |

### Deferred from 2026-05-07 session — full list in [`AUDIT_REPORT.md`](./AUDIT_REPORT.md#deferred--kept-in-mind-for-future-sessions)

Brief summary; pick one or two next session:

- **Security residual** (~10-30 min each), RE-MEASURED 2026-08-24 - the old list here was stale in both directions: **HSTS is DONE** (the live response carries it; this list still offered it), and `img-src` was tightened long ago. RE-MEASURED AGAIN 2026-09-18, and the three "still open" items were three different things: CSP `report-uri` is **won't-fix** (header-only directive, a distribution-wide CSP header blanks the prototype, no collector exists - OPERATIONS s3.3); **Permissions-Policy + X-Frame-Options DENY is LIVE since 2026-09-28** (`scripts/cloudfront_security_headers.py --apply`, `--verify` all three URLs ok, `/badge` repointed off no policy; the drift check now guards the header - OPERATIONS s3.2); signup CAPTCHA is **superseded by I17 option A** (a verification email is the stronger control and is built). ~~per-route throttle on `/v1/score`~~ **- that one was already done when this line was written**: `GET /v1/score` has carried 40/80 since the 2026-07-24 soak, and `POST /v1/score/batch` 10/20. As of **2026-09-07 every unauthenticated route carries its own throttle** (the last five sized from measured traffic - see `HANDOVER.md` §0.4), guarded by `backend/tests/test_route_throttles.py`, whose allow-list is now empty. A third stale entry in a list this same sentence twice corrects for being stale in both directions.
- **Visual polish** (~5-15 min each): layer-toggle indicator colours per layer, aircraft-noise legend gating, DEFRA caption stacking, airport text plates.
- ~~**A11y carry-forward**: layer toggle hover/active, heading hierarchy, skip-to-content, touch targets, `:focus-visible`, SR search-results count, `prefers-reduced-motion`.~~ **ALL CLOSED — verified against the code 2026-07-27, not against this list.** Every item was already implemented (some since Wave 10); the list was stale and had been making finished work look outstanding for weeks. `index.html` scans **0 violations at any severity** under axe WCAG 2.1 AA.

  **The real gap was coverage, not any of the items above:** the axe scan only ever ran against `/`, and only failed on `critical`. The B2B funnel had never been scanned. Now all 8 public pages are scanned at critical+serious — which found 4 genuine `serious` defects on the `score-demo` pages, including footer links at 2.14:1 and a Swagger `<select>` with no accessible name (critical). Fixed in source 2026-07-27; **awaiting a `web-deploy` to reach live.**
- **Code quality** (~10-60 min each): ~~API base URL extraction (4 files duplicated)~~ — done in Wave 12.9 (`js/api-base.js` shared by 3 browser pages; tests/api.test.mjs duplicates intentionally with /preflight 4d drift check guarding alignment). `BOROUGH_ALIASES` expansion, Swagger UI SRI hash, signup race-recovery test.
- **Enterprise readiness** (legal effort): DPA template (CommonPaper, 2-3 hr legal review), MSA + SLA + termination + data return (1-day legal), privacy notice + sub-processor list + retention policy (half-day each), DynamoDB PITR + RTO/RPO doc (1-click + ~1 hour), `pip-audit` integration, `support@skyscore.co.uk` mailbox + 1-business-day SLA, status page subdomain.
- **Performance** (~1 hour): extract inline data (`BOROUGH_DATA`, `AREA_MAP`) from index.html (6.9k lines) to JSON files fetched after first paint, improves LCP.

---

## Distribution findings, 2026-08-21 (from a cowork session)

Six findings, **all six verified against the repo** before being recorded here.
They are DISTRIBUTION problems, not correctness ones - the data is now in better
shape than the funnel that is meant to carry it.

| # | Finding | Verified | Owner |
|---|---|---|---|
| D1 | Free tier is 100 requests/month | TRUE - `SkyScoreFreeTier`, `Limit: 100`, `Period: MONTH` | Bill (pricing) |
| D2 | No embeddable badge | TRUE - the only `badge` strings in `index.html` are the `line-badge` / `rating-badge` CSS classes | Build |
| D3 | Nothing between GBP0 and GBP499 | TRUE - `pricing.html` contains exactly two figures, GBP499 and GBP2,500 | Bill (pricing) |
| D4 | Eight URLs in the sitemap | TRUE - and **all eight are product or marketing pages**. Zero content pages, and the map is client-side, so there is no indexable surface at all | Build |
| D5 | The postcode search captures nothing | TRUE at the point named. Signup EXISTS but lives on `score-demo/index.html`, the B2B page - so the capture is on the low-intent surface and absent from the high-intent one | Build |
| D6 | Round 4 maps 2021, a COVID year | TRUE and disclosed everywhere. **Checked 2026-08-21: the five-year END cycle is documented, but DEFRA has published NO Round 5 date.** The site's legend said "DEFRA expects Round 5 around 2027", which asserts an expectation DEFRA has not stated; corrected to "falls due in 2027; DEFRA has not published a date". Nothing further to do until they announce | Watch |

**The connection the findings did not make, and it changes D1.** The free tier is
100/month *because* `MAX_BATCH_SIZE` is 100, so one request can be 100 scores -
`BATCH_METERING_DECISION.md` cut it 1,000 -> 100 for exactly that reason. That
was the only lever available at the time. It is not any more: the 2026-08-21 fix
for C6/C7 proved that a **per-method `RateLimit: 0`** keeps a key off a route,
verified live. Applying the same block to `ScoreFreeUsagePlan` decouples the two,
so **the request quota could go back up without the x100 multiplier following
it**. Free keys can still call batch today - only the demo plan is scoped.

That is a genuine unlock rather than a price cut: the wedge was closed by a
metering workaround, and the workaround now has a better alternative.

**D2 is the strategically largest.** Walk Score's mechanism was the badge, not
the API - the badge is what put the score on every listing page and made the API
worth buying. It is also the one item here that compounds with D4: an embed is a
backlink, and 8 URLs with no content pages is not a weak organic surface, it is
none.

**Sequence I would suggest**, cheapest-first and each independently useful:
D5 (capture at the moment of intent) -> D1 (unlock the quota via the C6/C7
mechanism) -> D2 (badge) -> D4 (per-borough static pages, which the badge then
links back to). D3 and D6 need no build - one is a pricing call, the other a
date to watch.

**D5, D1, D2 and D4 all SHIPPED and deployed 2026-08-21.** D3 and D6 remain
open by their nature - one is a pricing call, the other a date to watch.

| | Shipped | Verified live |
|---|---|---|
| D5 | Notify form under every postcode result, posting `source:'consumer'` to `/v1/signup`; no API key is minted for a consumer | Form renders on CloudFront, both new and repeat submissions correct |
| D1 | Free tier 100 -> **10,000 requests/month**, `/v1/score/batch` denied per-method so requests == scores | Plan reads `quota=10000`, batch 429s, CI key on another plan still batches |
| D2 | `GET /badge?postcode=` returns an SVG; embed snippet with copy button in the panel | Badge returns **7.1** for SW11 1AA, matching `/v1/score` exactly, no key |
| D4 | 99 generated borough pages + `/area/` index; sitemap **8 -> 108 URLs** | Pages serve 200 with 15 facts each and **no `<script>` tag** |

Three new blocking gates: `demo-key-scope`, `uk-city-panel`, `area-pages`.

**What each one cost that was not in the finding.** D5 needed a privacy
disclosure, because `privacy.html` had said the only address we hold is for API
keys. D1 needed all four mirrors the template names, and the drift gate caught
two of them itself. D2 needed XML escaping, because an SVG is a script-capable
document served from our origin onto someone else's page. D4 needed a
duplicate-content floor, because 99 thin pages is a doorway network and worse
for the domain than none.

---

## Closed 2026-09-07 - the audit wave

Recorded here so the "what next" list does not carry finished work. Detail in
`AUDIT_REPORT.md`, which marks every finding by whether it was re-verified by
hand or carries only the finder's evidence.

| | Was | Now |
|---|---|---|
| Mobile web homepage | **1 visible link**; /privacy and /terms unreachable on every phone since 28 Aug | 9 hit-testable links, gated by `tests/mobile-legal-links.mjs` |
| Scored transport share | counted **806 retired** NaPTAN nodes | active only; City of Nottingham `good`->`moderate`, 8.3 -> 8.0 |
| `/v1/chat` residency | Bedrock in `us-east-1` while four documents denied it | disclosed; gated by `test_data_residency.py` |
| London `/v1/score` | credited **no price source at all** | credits HM Land Registry; gated |
| Nottingham crime | never compared against ONS | compared, and it agrees |
| `area pages match the live API` | passed on **zero pages** | floor derived from `/v1/regions` |
| `score sanity` | never checked `env` | components derived from live responses |
| Borough parity floor | `< 60` against a real **91** | derived from the Lambda |
| `/badge` path injection | **500** with a JSON body | 404 |
| Area-page attribution | Environment Agency credited on **0** of 90 pages | 90 of 90 |
| METHODOLOGY s6 | transposed `quiet` and the total; broken 3 times | rebuilt at v4.0 and **gated** |
| Orphaned gates | `pwa-check` and `changes-why` in no runner | both wired in |

**Two things that only showed up by doing the work**, both worth remembering:

- **Restoring a hidden surface restores its defects with it.** Un-hiding the
  mobile footer produced three further defects in sequence - 1.97:1
  separators, a pointer-events band swallowing taps meant for the map, and
  links parked under the sticky search card - each only findable once the
  previous was fixed.
- **METHODOLOGY s6 kept drifting for a structural reason**, not carelessness:
  at SW11 1AA the live `quiet` comes from the DEFRA raster, not the geometry
  the example hand-derived, so every growth in raster coverage diverged it
  again. Check `quietResolution` before hand-deriving quiet for any postcode.

---

## Open decisions

### WHEN EACH OPEN ITEM IS SAFE TO DO - written 2026-09-10, after the roll closed

Everything below is what was left when the August NSPL roll, the road tier and
the loader fix were all deployed and verified. Each row says what has to be
TRUE before starting, how to do it so a mistake is caught, and what a mistake
costs. "Safe" means: reversible in one deploy, verifiable from the origin, and
not on the same day as another deploy of the same surface. **Nothing here is
safe mid-load or mid-deploy** - `sh scripts/load_status.sh` and `git status`
first, every time.

| Item | Safe when | Do it like this | Verify | If it goes wrong |
|---|---|---|---|---|
| ~~**UK HPI July 2026 roll** (prices + trend, both holders)~~ **DONE 2026-09-16, the morning HMLR published** | Rolled as this row said, with one decision it did not name (item 6 below): the quarter KEY stayed `2026-Q3`, the LABEL and the deflator moved (CPIH 3.1). 177 of 188 fields moved; `balanced` moved 9 of 99 scores by 0.1, `investor` 78 of 99. Two things shipped alongside - the twelve literal price-source lines became one derived line, and `/v1/changes`' market summary stopped inferring score direction from trend direction (it was wrong for the first time this month). See CHANGELOG 2026-09-16. *Original row:* The moment `Average-prices-2026-07.csv` answers 200 - expected **~16 Sep** (June answered on 19 Aug). | Exactly this morning's sequence, `HANDOVER.md` s0 steps 3-6: `--check --all` to size it, `--write` (both holders, `BACKEND_ONLY_PRICES` block included), `build_area_pages.py --write`, preflight (`area pages match the live API` reds until the backend deploys - correct), SAM first, then `borough-extra.json`, `area/`, `sitemap.xml`. A price roll also moves `afford` for EVERY borough (v5.0 pools nationally), so expect the whole table to move, not seven pages. | Drift 133/133, freshness 99/99, `site == /v1/score`, and re-read METHODOLOGY s6's Wandsworth example - `check_worked_example.py` goes red if the baked inputs moved. | Frontend-first puts the site ahead of the API on every borough. Redeploy the backend; nothing is destroyed. |
| **`/audit`** | **Last run 2026-10-05** (`AUDIT_REPORT_2026-10-05.md`); next due **~12 Oct**. Not before a roll lands the same day - an audit against a tree mid-change reports the change as findings. | `/audit`, then triage into `AUDIT_REPORT.md` as on 7 Sep. | Every finding has a measured number or a repro before it is called a finding. | Nothing deploys from an audit. |
| **ONS crime, year ending June 2026** | When ONS publishes Table C4 for YE June (the YE March release landed in July; expect **~late October**). `refresh_crime_from_ons.py --check --all` fetches and caches the workbook, so it reds by itself if the URL or sheet changes. | `--check --all` first (per-city floor), then `--write`, then area pages, then backend-first deploy. | Same as HPI. Nottingham is compared since 7 Sep; `NO_ONS_COMPARISON` must stay empty. | A workbook restyle can make the parser read zeros - the per-city floor catches an empty compare; a WRONG column does not, so eyeball three boroughs against the sheet. |
| **Air quality vintage roll** (DEFRA PCM background maps) - **ROLLED 2022 -> 2024 on 2026-10-01** on Bill's call (fresher figures now beat waiting two weeks); the 2025 roll ~mid-Oct is the same steps again | **When DEFRA publishes 2025** - the advisory preflight stage `data == publishers' latest` (`scripts/check_data_freshness.py`, added 2026-10-01, every dataset in one table) flags the day it lands. **The 2026-09-29 plan was to skip 2024 and roll once; Bill chose on 2026-10-01 to roll 2024 immediately, accepting a second `environment` shift when 2025 lands. **Fallback unchanged: if 2025 is not out by 31 Oct, keep 2024 and re-check monthly.** Ideally the same deploy as the ONS crime roll below. | Change `PCM_YEAR` in `load_defra_air_quality.py` (the one holder; `tests/test_script_mirrors.py` then reds until the builder's `AQ_VINTAGE`, the Lambda source line and METHODOLOGY's source row match); download `mapno2{year}.csv` + `mappm25{year}g.csv` from `uk-air.defra.gov.uk/datastore/pcm/`; run the loader detached (~1 h); `build_borough_bands.py --check` then `--write --write-lambda`; `build_area_pages.py --write`; methodology changelog with the measured `env` movement. | Freshness stage reads `ok`; mirrors test green; area freshness against the live API; a spot postcode serves the new year in `/v1/environment`'s source line. | Every NO2/PM2.5 figure, the `env` component and the one-pagers move together; a partial roll publishes one year under another's label, which the mirrors test exists to stop. Re-run with the previous `PCM_YEAR` to undo. |
| **NSPL November 2026 edition** | When Geoportal lists it (quarterly: Feb/May/Aug/Nov, expect **mid-late Nov**). Diff FIRST: if `REMOVED` is non-zero the upsert is no longer safe, because nothing deletes a dropped postcode from the table. | `HANDOVER.md` s0 steps 1-7, and step 7 is the one the August roll almost missed: **eight scripts read `nspl.csv`**, and the per-postcode DEFRA tiers and the client quiet datasets all re-run. With the pool fixed the whole roll is ~2 h detached. The column suffix will be `lad27cd` in February - every reader resolves by prefix now, and the bands builder hard-fails if none matches. | `__META__` re-stamped; `borough bands == sources` green; B13 0FF-style spot check that a NEW postcode carries NO2 and road; datasets deployed before anyone looks at the site. | A roll that stops after the table leaves the shares and the postcode tiers on the old edition with only an advisory saying so - this is exactly what happened on 9-10 Sep. Finish the list. |
| ~~**Gate `/v1/regions` and `/v1/changes`** (audit I1)~~ **CLOSED 2026-09-11 as WON'T-FIX** | Decided, not deferred. Both routes stay **deliberately unauthenticated**, for the same reason `/v1/environment` is: their consumers are public artefacts that cannot hold a key. Re-measured 2026-09-11 - both answer **HTTP 200 with no key** live, and the callers are `changes.html` (public), `score-demo/status.html` (public) and `tests/area-page-freshness.mjs` (a BLOCKING preflight gate). | Nothing to do. **Two details in the old row were wrong and are corrected here**: (1) `scripts/score_bulk.py` does NOT fetch `/v1/regions` - it names the route in an attribution string only, so it needed no key; (2) gating `/v1/changes` does not degrade `changes.html`, it **empties** it - that page builds its entire body from the one fetch, as `tests/a11y-source.mjs` records, so the a11y gate would then scan a blank page and the failure would surface as an accessibility regression. | The finding's SUBSTANCE - "documented as key-gated, answers 200" - was closed on 2026-08-21 by correcting `template.yaml` and the `handle_regions` docstring, and in `CLAUDE.md` later. What remained was only the question of whether they SHOULD be gated. | Reopen only if a route starts returning something a competitor could harvest at scale. Neither does today: `/v1/regions` is a list of city names and `/v1/changes` is one cohort's quarter-over-quarter movement, both already published on public pages. The throttles (5/10 each) are the rate control, not the key. |
| **`/v1/signup` writes any address, unverified** (audit I17 of 13 Sep; F16 of 29 Aug, dropped and re-found) | Bill's call, because every fix changes what the endpoint MEANS. Today: `{email, source:'consumer'}` from anyone writes that address to the score-updates list as a consented subscriber (privacy.html s2 says consent is given "by submitting the form" - not true of an address submitted by a stranger), and that row then makes the real owner's API signup answer 409 "contact support" - a lock-out; the three known-address replies also differ, so the route enumerates which addresses hold keys. Stage throttle 1 rps = 86,400 addresses a day. | **Option A (right, needs SES):** a verification email before ANY write - the key and the subscription both arrive by email, so the response can be identical for every address and nothing is written for one the requester does not control. **Option B (partial, no email):** make every reply the same 201 and let an API signup UPGRADE a consumer-only row to a key - closes the lock-out and the consumer-side enumeration, leaves "already holds a key" as an oracle and still lets a stranger subscribe an address. **Option C:** take the consumer form off `/v1/signup` entirely until A exists. Recommendation: A, and B in the meantime only if the lock-out is hurting a real customer. | `backend/tests/test_handlers.py` signup cases; a live `POST /v1/signup` for a plus-addressed copy of your own address in each state. | A: nothing - verification is additive. B: a customer who signed up on the consumer form and then wants a key gets one without support; the oracle remains and is documented in SECURITY.md. |
| ~~**`OPTIONS /v1/environment` returns 403**~~ **DONE AND DEPLOYED 2026-09-13** | Bill said so on 13 Sep. The `Auth` block is removed from `EnvironmentOptions` in `template.yaml`, matching `/v1/signup` and `/v1/chat`; `test_route_throttles.py` green (OPTIONS methods are exempt from the throttle assertion by design, as its siblings already were). Bundled with the 11 Sep wave's SAM deploy rather than deployed alone, as this row said to. | Nothing left to do but deploy. | `curl -X OPTIONS -H 'Origin: https://example.com' -H 'Access-Control-Request-Method: GET' .../v1/environment` -> **200** with the CORS headers (measured after the deploy; the score handler answers 200 like `/v1/signup`, only `/v1/chat` is 204 - this row said 204 until it was run). Was 403. | None that matters - reverting is the same one-line change. |
| ~~**Rename `healthcareWithin1kmPct`**~~ **DONE 2026-09-11** | Shipped. The field is `healthcareWithin500mPct` in the builder, the holder and the four `design/` prototypes; the log label says `<500m`. | Verified by a FULL re-derivation, not by grep: `--check` compared **86 boroughs, 0 moved, 0 holder-only, exit 0**. | **The procedure written in this row was unsafe and has been fixed.** It said "run `--write` so the holder follows" and that `--check` catches a stale key left beside the new one. It does not - `--check` only iterates `DERIVED_KEYS`, so a key LEAVING that tuple stops being written and stops being compared on the same edit. `--write` would have published both keys on all 86 boroughs with nothing able to see it. | `FOREIGN_KEYS` + an orphaned-key check now fail the gate on any holder key no script owns, proven red at 86 boroughs. Any FUTURE rename of a derived field is covered; rename the key in the holder directly, then `--check`. |
| **CPI / real-terms growth adjustment** - **COSTED 2026-09-13, decision still Bill's** | The costing the old row asked for exists: `python scripts/cost_real_growth.py` (reads CPIH series L55O from ONS for the engine's `SNAPSHOT_VINTAGE_LABEL` month, changes nothing, prints per-borough before/after; `--csv` for the table). **Measured on June 2026 (CPIH 2.8%): 26 of 99 boroughs read "rising" today and are FALLING in real terms** - 10 of them in London (Hounslow, Lewisham, Hackney, Southwark, Haringey, Waltham Forest, Merton, Enfield, Sutton, Bexley). Growth component mean -1.32, worst -7.00; **81 of 99 investor composites move by >=0.1**; `balanced` does not move (growth weight 0). **A formula consequence to decide, not just a number**: the dual anchor scales each tail to the COHORT extreme, so when a whole cohort crosses zero (South Yorkshire: Rotherham +2.4% -> -0.4%) its fastest riser drops from 10.0 to ~3.0 and no borough in that city can score above 5 - the scale's meaning changes per city. Recommendation if adopted: score `growth` on the real trend, keep `trend` nominal (it is HPI's own figure and published to everyone), ADD `trendReal` and `cpihRate` to `context` so nothing is relabelled, and treat it as v5.1 with s12's 14 days' notice. It touches `growth`, which only the `investor` persona weights, so `balanced` scores do not move - but the trend field is published to everyone. Source has a cadence (ONS CPIH, monthly, next 16 Sep) and needs a place in the vintage-roll sequence beside the HPI step. | Prototype the formula in a script that prints per-borough before/after; write METHODOLOGY s4 first; then engine + site together (`borough-score-parity.mjs` is the OUTPUT gate); version bump + 14 days' notice. | `check_worked_example.py` (the s6 example carries `trend`), parity on 91 boroughs, `/v1/changes` explains the movement. | A formula in one holder and not the other - the Manchester-incident shape. The parity gate exists for this. |
| **IAM privilege-escalation path** (OPERATIONS s3.8, audit C3) | **Only with Bill at the console, at the START of a working session, with no load or deploy running and time to test a real deploy straight after.** **Step 1 (the managed-policy allow-list) was tried from the CLI on 2026-09-13 and is NOT reachable**: `cloudformation:GetTemplate --template-stage Processed`, `iam:ListAttachedRolePolicies` and `iam:ListRolePolicies` are all denied to `flightmap-dev`; `iam:GetRole` works and confirms **no permissions boundary** on any of the 8 roles. Strong prior for the console read, not a substitute: every function uses SAM policy TEMPLATES (inline), so the only managed ARN is almost certainly `arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole` - confirm it in one glance rather than trusting this sentence. The 3 Sep console edit REPLACED the policy instead of extending it and no deploy of any kind could run for a day; nothing detected it until `check_aws_permissions.py` was written. | `python scripts/check_aws_permissions.py` BEFORE (expect 18 granted, 0 denied); make the edit with the whole of `backend/iam-policy.json` open beside it; run the probe again; run a real `sam deploy` of an unchanged stack; run `scripts/check_deploy_drift.sh`. | 18/18 both times; the deploy completes; drift 133/133. | Paste the whole of `backend/iam-policy.json` back - that is what fixed 4 Sep. A permission is a timestamp, not a property: re-probe, never read it off a document. |
| ~~**`/badge` has no edge cache** (audit M1)~~ **DONE 2026-09-17, option A - applied, verified (two postcodes Miss -> Hit), URLs repointed, `sw.js` pass-through, gated by `tests/test_badge_edge_cache.py`** | Any time; console or template. Today every distinct viewer's first render of a badge on a listing page is a Lambda invocation, bounded only by the 5 RPS route throttle - `X-Cache: Miss` on every call, measured 2026-09-14. A busy portal page can 429, which renders as a broken image on a customer's page. | **Option A (recommended, no running cost):** add a cache behaviour for `/badge*` on the site's own CloudFront distribution (`EGSSPJKLFL33M`) with the API as origin, honouring the response's `max-age=86400`; the badge embed then points at `skyscore.co.uk/badge`. **Option B:** enable API Gateway caching on the stage - a 0.5 GB cluster is ~USD 14/month, and it caches every route unless disabled per method. **Option C:** accept the throttle as the bound until a portal actually embeds one. | `curl -D -` three identical badge GETs: `X-Cache: Hit` on the second. | A: nothing - a miss falls through to the API as today. B: cost. C: a broken image on the first customer page that gets busy. |
| **GoatCounter on the key-minting page** (audit M6) | Any time. `/score-demo/` loads GoatCounter's rolling `count.js` (no SRI possible) on the page that mints and displays a FREE-tier key. The script runs inside the page's CSP and could read the DOM. | **A:** remove analytics from `/score-demo/` and lose the demo's funnel events - the only measure of B2B interest today. **B:** keep it and record the trade (done in SECURITY.md, 2026-09-14) - the exposed key is free-tier, `/v1/score` only, 10,000/month, and GoatCounter is a small EU operator chosen for exactly this posture. **C:** mint the key on a page without analytics and link to it from the demo. | The demo page's `<script>` tags; the `analytics` line in SECURITY.md. | A: blind to demo usage. B: a compromised GoatCounter could harvest free-tier keys. |
| ~~**Repo settings** (audit M7)~~ **ALL DONE - re-measured 2026-09-28 via `gh api`**: Dependabot alerts AND security updates enabled, secret scanning + push protection enabled, `master` protected requiring `lint-frontend`/`lint-backend`/`test-backend`, and all nine `uses:` in `ci.yml` pinned to commit SHAs with a version comment. This row said all three were open after they had closed. *Original row:* Dependabot security updates OFF, `master` unprotected, actions pinned by tag not SHA | Console (GitHub settings), any time. `ci.yml` has `permissions: contents: read` since 2026-09-14; the rest is dashboard work or a pinning pass. | Settings -> Code security -> enable Dependabot security updates; Branches -> protect `master` (require CI green; allow the owner to push - solo repo); pin the four `actions/*` uses to commit SHAs with a `# vX.Y.Z` comment. | `gh api repos/:owner/:repo/branches/master/protection` answers 200; Dependabot PRs appear. | A vulnerable dev dependency stays unnoticed; a force-push to master goes through. |
| **Second MFA device** | Any time Bill has a second authenticator in hand. The account has ONE factor and no fallback (`memory/project-aws-console-lockout.md`). | IAM console -> security credentials -> assign a second virtual MFA. **Do not sign-out-test the single factor first.** | Both devices listed; sign in with the second one while the first is still registered. | Lockout. The recovery is the account-level support route, days not minutes. |
| **Billing alarm** | Console only, and ONE STEP EARLIER than this row said (measured 2026-09-13): `AWS/Billing` reports **zero metrics** in us-east-1, so *Receive Billing Alerts* has never been ticked in the Billing preferences - without it the `EstimatedCharges` metric does not exist and any alarm sits in INSUFFICIENT_DATA forever. And **SNS is denied to `flightmap-dev` outright** (`ListTopics` AuthorizationError), so the alarm's action cannot be created from here either. Do step 1 of `AWS_BILLING_ALARM_SETUP.md` at the console first. ~~The alarm itself (`cloudwatch:PutMetricAlarm` IS granted) can then be created from the CLI~~ - **wrong, corrected 2026-09-28 from the live policy**: `PutMetricAlarm` is scoped to `arn:aws:cloudwatch:eu-west-2:...:alarm:london-flight-map-*`, and a billing alarm must live in us-east-1, so the alarm is console work too. **28 Sep: started; the browser extension cannot read Billing pages, so the tick is Bill's**, then SNS topic + subscription + alarm in the CloudWatch/SNS consoles. `OPERATIONS.md` s7 stated one existed; measured 8 Sep, there are zero alarms. | `AWS_BILLING_ALARM_SETUP.md`. | The alarm shows in us-east-1 with an SNS subscription CONFIRMED (an unconfirmed subscription is an alarm that emails nobody). | Nothing - an alarm cannot break a deploy. |
| **`index.html` data extraction** - **RE-MEASURED 2026-09-28 and recommended CLOSED**: the page is 863 KB raw but **182 KB brotli**; cut 2 (the nine generated neighbourhood blocks, 112 KB raw) saves **14 KB** on the wire and cut 3 (`*_BOROUGH_DATA_RAW`, 8 KB raw) about **2 KB**, for a new loading state on the ranking and a second holder of scoring inputs. Held open only if Bill still wants cut 2; cut 3 is not worth its risk. *Original row:* (inline `BOROUGH_DATA` / `AREA_MAP` -> fetched JSON, for first paint). **CUT 1 of 3 DONE 2026-09-18**: the eleven `<CITY>_STATIONS` arrays (92 KB, one writer, one test, no boot change) became `data/stations.json`, fetched on search intent like aircraft-quiet, with a not-loaded state; extraction byte-verified against a NaPTAN rebuild; page 933 -> 841 KB. **Measured before cutting**: 917 KB raw is 233 KB brotli, FCP already 1.1 s since the d3 move, so the remaining win is cache granularity, not first paint. **Cuts 2 (neighbourhood detail + area maps, ~110 KB, boot renders the ranking) and 3 (`*_BOROUGH_DATA_RAW` + flight paths, ~45 KB, scoring inputs at parse time, HPI/crime writers + both parity gates) still want the day below.** | A day with no other deploy, and a session that can run the FULL frontend gate set plus a live check afterwards. Not for an away window. | Extract to `data/*.json`; add each to `SHELL_ASSETS` in `sw.js` AND to `make data-deploy` (point 1 of "adding a city" in CLAUDE.md: a precached file missing at the origin stops the service worker installing for EVERY city, because `cache.addAll()` is atomic); deploy data BEFORE `sw.js`; bump the SW version. | `failure-path.mjs` (offline launch), `smoke-local.mjs`, `city-switch.mjs` at both viewports, `borough-score-parity.mjs`, then the live responsive/`live web == tabbed layout` advisories. | A returning visitor's service worker fails to install and they keep the old shell forever; the fix is the data deploy, not another SW bump. |
| **Visual polish list** (layer-toggle colours, legend gating, DEFRA caption stacking, airport plates) | Any time, with Bill looking at the result - these are judgements, not defects. | One item per commit; `frontend-design` on the change; `a11y-source.mjs` and `panel-contrast.mjs` after, because the last three polish passes each found a contrast regression. | The two contrast gates green at desktop, phone and landscape. | Nothing structural. |
| **Rebrand** (Sky Score -> CUBITT33, decided 5 Aug) | Before any COLD outreach, not before warm - `memory/project-outreach-never-sent.md`. A rename touches every deployed page, the App Store listing, `manifest.webmanifest`, the badge SVG and the `sources` strings integrators carry. | Grep the NAME across the tree first and count the surfaces; do the web in one deploy and the native binaries in their own release (2-4 week cadence). | `check_deploy_drift.sh` 133/133; `no em dashes`; the App Store lookup by bundle id. | Half-renamed surfaces - a public page saying one name and the API another. The grep count is the checklist. |
| **Outreach** (5 drafts, 0 sent since 21 May) | Warm channels any time; cold channels after the rename. **DKIM verified before any send** - a first email that lands in spam is the most expensive one. | `memory/project-pilot-outreach-pack.md`; send gates in `OUTREACH_LOG.md`. | A test send to a personal address arrives with DKIM pass. | A bounced or spam-foldered first touch. |
| **Sell through AWS Marketplace** (raised by Bill 2026-09-16) | **After the rebrand, never before** - a Marketplace listing is the most public, permanent, indexed cold channel there is, and renaming a live listing later means a new listing. **It is a CLOSING mechanism for deals sourced elsewhere, with zero expected discovery value**: tens of thousands of listings in broad categories, buyers search for what they already know, and small-ISV Marketplace revenue is private offers to customers the seller found. The £2,500 pilot transacting on a buyer's existing AWS bill (committed-spend burn-down, no vendor onboarding) is the case for it. Marketing stays where the project already puts it: the consumer site, the 99 area pages, the badge, warm outreach. | The fit is unusually good: API Gateway has a NATIVE Marketplace integration - attach a product code to a usage plan and it meters to Marketplace - so the work is a registration endpoint (`ResolveCustomer` on the `x-amzn-marketplace-token`, mint the key against the right plan, as `/v1/signup` already does) plus an SNS listener for subscribe/unsubscribe: 1-2 days. Listing needs: seller registration as CUBITT33 LTD (W-8BEN-E, bank), pricing/privacy/terms pages (exist), an EULA (AWS Standard Contract is the low-effort route), a support contact, then a review measured in weeks. **The fee is VERIFIED (AWS docs, read 2026-09-16): 3% on public SaaS subscriptions and on private offers under USD 1M TCV, 1.5% on private-offer renewals**, effective since 5 Jan 2024 - `docs.aws.amazon.com/marketplace/latest/userguide/listing-fees.html`. Still to verify: UK seller eligibility terms and the W-8BEN-E path for a UK Ltd. | A Marketplace test subscription mints a key that scores; a private offer can be issued. | Listed under a name the rebrand then retires; a fee assumption that turns out wrong in the pricing page. |

### What each open decision entails - written 2026-09-14, corrected 2026-09-15

Bill asked for this expansion on 14 Sep and said he would come back to it. Each
item below is a row in the table above; this is the practical half - what is
wrong today, what each option means in work and cost, and the recommendation.
Nothing here needs re-deriving: the measurements are in the audit report and
the commits of 14 Sep.

**1. I17 - `/v1/signup` writes any address unverified.** Anyone can POST
`{"email": "you@example.com", "source": "consumer"}` and that address joins the
score-updates list as a consented subscriber. Three consequences: privacy.html
says consent is given "by submitting the form", untrue of an address a stranger
submitted; the row makes the real owner's later API signup answer 409 "contact
support" (a lock-out); and the three replies for a known address differ, so the
route tells a caller which addresses hold API keys. 1 RPS = 86,400 addresses a
day.
- **A, verification email first (right):** nothing is written until the address
  confirms. Needs SES - verify `skyscore.co.uk`, DKIM at Cloudflare, sandbox
  exit, a pending-token table, a confirm endpoint, one identical 201 for every
  address; key and subscription both arrive by email. Half a day plus SES
  approval (1-2 days).
- **B, same 201 for everyone + an API signup upgrades a consumer row:** closes
  the lock-out and the consumer-side oracle in one Lambda change; a stranger
  can still subscribe your address and "holds a key" stays detectable. ~1 hour.
- **C, take the consumer form off `/v1/signup`:** notify-me disappears until A.
- **Recommendation: A.** B only if the lock-out hurts a real customer (the
  signups table holds a handful of rows - it does not today).
- **A IS BUILT (2026-09-15), BEHIND `SignupVerify=off`.** `start_verification`
  / `handle_confirm` / `complete_signup` in `signup/app.py`, the pending
  table, the `GET /v1/signup/confirm` route with its throttle, SES send,
  the demo page's `pending` branch, 13 tests. Deploying it changes NOTHING
  until the flag is flipped, and the flip is **OPERATIONS.md s3.9**: SES
  identity + DKIM at Cloudflare, sandbox exit, two IAM verbs for the TTL
  (`UpdateTimeToLive`/`DescribeTimeToLive` - granted by the 28 Sep paste;
  the TTL itself landed on master 2026-09-29),
  the privacy.html s2a wording in the same deploy, then
  `--parameter-overrides SignupVerify=on`.
- **Bill is leaning to A (2026-09-15). What A changes in the POLICIES, read
  from the pages:** `privacy.html` s2a says consent is given "by submitting
  the form" (`:241`) and "we collect the address and the postcode you
  searched, and nothing else" - both sentences change (consent by clicking
  the emailed link; an unconfirmed address held N hours then deleted), under
  the SAME lawful basis, Art 6(1)(a). The API-key paragraph needs nothing:
  Art 6(1)(b) contract already covers issuing the key, by email or otherwise.
  `SUBPROCESSORS.md` row 1 (AWS) must name SES, in `eu-west-2` so
  `test_data_residency.py` holds. **Cookies: no change** - s8's "does not use
  cookies" stays true, the confirm link carries its token in the URL and the
  confirm page sets nothing; under PECR a confirmation email is not
  marketing. Not policy, but on the list: SPF/DKIM/DMARC at Cloudflare, SES
  sandbox exit, `ses:SendEmail` in `iam-policy.json` AND the Lambda role, a
  throttle on the new confirm route (`test_route_throttles.py` reds without
  one), and the demo page's "your key is..." panel becoming "check your
  email" (`FreeTierQuotaDriftTests` reads that page).

**2. ~~`/badge` has no edge cache (audit M1).~~ CLOSED 2026-09-17, option A,
in the order below: `--apply` (ETag unchanged from 15 Sep, Deployed in ~5
min), `--verify` PASS (SW11 1AA and M1 1AE each `Miss` then `Hit`, SVGs
differ), THEN `index.html` repointed - both URLs through one holder,
`BADGE_BASE = 'https://skyscore.co.uk/badge'`, ABSOLUTE because the snippet
lives on other people's pages and the preview renders in the native app at
`capacitor://localhost`; the host added to the CSP `img-src`. Two things the
plan below did not know: (1) **`sw.js` would have pinned the preview** -
same-origin paths default to cache-first there, and Cache Storage ignores
Cache-Control (the `borough-extra.json` incident, on an image), so `/badge`
now passes through; (2) API Gateway has no HEAD on the route, so `curl -I`
answers 403 where a GET hits - browsers GET images, so nothing is wrong, but
verify with GET. `tests/test_badge_edge_cache.py` holds the holder, both
uses, the CSP host and the SW rule's POSITION together (a pass-through after
the cache-first branch is dead code), proven red three ways. The original
text follows.**

Every badge request is a Lambda
invocation; the 24h `max-age` is honoured by each viewer's browser only.
Measured 2026-09-14: `X-Cache: Miss` on every call. A busy listing page with
many first-time viewers can pass the 5 RPS route throttle and render a broken
image.
- **A, cache behaviour on the site's CloudFront (`EGSSPJKLFL33M`):** add the API
  (`2gjfdzg20c.execute-api.eu-west-2.amazonaws.com`) as a second origin with
  origin path `/prod`, a `/badge` behaviour keyed on the `postcode` query
  string that honours the origin's Cache-Control. Then point BOTH badge URLs
  in index.html (`embedSnippet()` and the `badge-preview` img) at `/badge`,
  same-origin. Cost nil. **Corrected 2026-09-15, having read the live config
  (one origin, zero behaviours, default policy CachingOptimized which strips
  query strings):** it is SCRIPTABLE - `GetDistributionConfig` and
  `UpdateDistribution` are granted - but NOT with a managed cache policy. Both
  `UseOriginCacheControlHeaders*` policies put the viewer `Host` header in the
  cache key and forward it, and API Gateway answers 403 to a Host it does not
  own; `CreateCachePolicy` is not granted. So the behaviour uses its own
  forwarding settings (query string `postcode`, no headers, no cookies, TTL
  0/86400/31536000 so the origin's 24 h and 5 min rule). **And it must carry
  NO function**: the default behaviour's `sky-score-rewrite-index` turns an
  extensionless `/badge` into `/badge/index.html`. **The script is
  `scripts/cloudfront_badge_behaviour.py`** - `--plan` (read-only, run 15 Sep:
  1 origin, 0 behaviours, ETag E1F83G8C2ARO7P), `--apply` (UpdateDistribution
  with the ETag, waits for Deployed; the classifier refused to run it in
  Claude's session, correctly - it is a production change, so it is Bill's
  one command), `--verify` (proven red on the current state: 403 twice, no
  hit). **ORDER: `--apply`, then `--verify` must PASS - TWO different
  postcodes both `X-Cache: Hit` on their second call and different SVGs from
  each other - THEN repoint index.html.** Repointing
  first breaks every badge. The verification has to be two postcodes: one
  postcode hitting twice also passes a cache that keys on nothing and serves
  the first badge to everyone for 24 hours.
- **B, API Gateway caching:** one stage setting, ~USD 14/month for the smallest
  cluster, and it caches EVERY route unless disabled per method (`/v1/score`
  would need opting out).
- **C, accept** until a portal embeds one.
- **Recommendation: A.**

**3. GoatCounter on the key-minting page (audit M6).** `/score-demo/` loads
`count.js`, a rolling third-party script with no SRI, on the page that mints
and shows a free-tier key; a compromised GoatCounter could read it. Recorded in
SECURITY.md on 14 Sep (option B), so nothing is undisclosed.
- **A, remove the tag:** one line; the demo funnel events - the only measure of
  B2B interest - go with it.
- **B, keep, recorded:** done. Exposure is a free-tier key: `/v1/score` only,
  10,000 requests a month.
- **C, mint on a separate analytics-free page** linked from the demo. ~1 hour.
- **Recommendation: B stands** unless a paid tier ever mints on that page.

**4. Repo settings (audit M7). ALL THREE DONE - the third on 2026-09-16 evening,
when Bill asked for it directly and the classifier allowed it**: `master` is
protected (verified by GET: required checks `lint-frontend`, `lint-backend`,
`test-backend`; `enforce_admins` false; no force-push or deletion; linear
history) and all nine Dependabot PRs (#5-#13) are squash-merged - two needed a
`@dependabot rebase` after their siblings landed on the same `ci.yml` lines -
with master CI green on the merged head and the root `npm audit` down from 5 to
1 moderate. *The 15 Sep record follows.* TWO OF THREE DONE 2026-09-15, all from the
CLI** - the 14 Sep line said dashboard; `gh api` does all three. **Done:**
Dependabot alerts + security updates enabled (`PUT /vulnerability-alerts`,
`PUT /automated-security-fixes`, verified `enabled: true`); the NINE `uses:`
lines (four actions) in `ci.yml` pinned to commit SHAs with `# vX.Y.Z`
comments, resolved through the tags API; and `.github/dependabot.yml` for the
`github-actions` ecosystem only, monthly, so the pins are updated by a PR
rather than rotting - a pin nothing updates is a frozen list. **Left for
Bill, one command** (the classifier refused it as a shared-resource change):
```
gh api -X PUT repos/billkhiz-bit/london-flight-path-map/branches/master/protection --input .github/branch-protection.master.json
```
The payload is CHECKED IN at `.github/branch-protection.master.json` since
2026-09-16 - the 15 Sep copy lived in a session scratchpad and was gone by the
next morning. Required checks `lint-frontend`, `lint-backend`, `test-backend`
(the names GitHub reports on `71264c4`'s check runs) - NOT `test-e2e`, which
reads the LIVE site and would block a Dependabot PR on deploy drift -
`enforce_admins: false`, no force-push, no deletion, linear history. Verify
with `gh api repos/billkhiz-bit/london-flight-path-map/branches/master/protection`
(404 "Branch not protected" on 16 Sep). **Why
`enforce_admins` must be false:** required checks block DIRECT pushes whose
commit has no passing run yet, which is every push from this machine; the
owner bypass is what "allow the owner to push" means concretely. The checks
then bind PRs - Dependabot's - which is where they matter.

**5. CPI real-terms growth.** `growth` is nominal HPI trend; at CPIH 2.8%, 26
of 99 boroughs the product calls "rising" fall in real terms
(`python scripts/cost_real_growth.py` prints the per-borough before/after).
Entails a methodology bump to v5.1, 14 days' notice to integrators
(METHODOLOGY s7), CPIH as a new data source in LICENSING.md, a changelog entry,
the worked example and all 99 area pages rebuilt, one backend-first deploy.
Half a day. The question is whether `investor` - the one persona weighting
growth - should see real or nominal movement. **Read against the code, 15
Sep:** `growth_score()` is `score/app.py:6412` and has a JS mirror in
index.html (Python rounds halves to even, JS up - `borough-score-parity.mjs`
is the gate), `/v1/changes` is unaffected (it recomputes `previousScore`
under the current formula by design), and the decision INSIDE the decision
is the contract: integrators read `trend` today, so it should stay nominal
with a `trendReal` beside it rather than flip. **DONE AS v5.1 ON 2026-09-15**,
the same day, because the notice turned out not to bind: the signups
register was READ (four rows: two consumer subscriptions, two keys both
Bill's) and no third party holds a key, so the changelog entry is the record
exactly as for v4.0 and v5.0. `trend` nominal, `priceTrendRealPct` +
`inflationPct` + `growthBasis` beside it, one CPIH per vintage, New York
nominal and saying so, growth provenance DERIVED (13 literals gone, 12 of
them a literal 'June 2026'). Engine-measured: 25 of 77 'rising' flip, 78 of
99 investor scores move (mean -0.53), balanced cannot. Three gates widened
(worked example derives growth for the first time; HPI gate checks CPIH
against ONS; parity compares investor). See CHANGELOG 2026-09-15. **DEPLOYED
the same evening, verified from the origin (drift 133/133, score sanity 28,
area 99/99, site == API, Cardiff investor 4.1 live).**

**6. July HPI roll. DONE 2026-09-16, decision (a) taken.** The key stayed
`2026-Q3`, `SNAPSHOT_VINTAGE_LABEL` moved to 'July 2026', `CPIH_12M_PCT['2026-Q3']`
moved 2.8 -> 3.1 with it, and the Lambda's vintage comment now records the rule
so the next in-quarter roll does not re-derive it. The three-step SNAPSHOT roll
happens at the first Q4 release (October HPI, ~mid-December). What the roll
surfaced is item 9 below. *Original entry follows.* Blocked on HMLR publishing `Average-prices-2026-07.csv`
(~16 Sep; 404 on 14 Sep). `build_hpi_prices.py --check` now prints **NEWER HPI
VINTAGE PUBLISHED** the moment it exists (audit M26). Then, per HANDOVER s0
steps 3-6: `--check --all`, `--write --all`, bump `DEFAULT_VINTAGE` and
`SNAPSHOT_VINTAGE_LABEL`, rebuild area pages, backend-first deploy. About an
hour. **Still 404 on 15 Sep** (HMLR publishes on Wednesdays). **"No
decisions" was wrong - there is one, and it is small:** `/v1/changes` is a
QUARTERLY comparison. The 25 Aug roll copied June's predecessor into
`LONDON_PREVIOUS_PT` and moved `PREVIOUS_VINTAGE`/`SNAPSHOT_VINTAGE` Q2 -> Q3
(`memory/project-trends-feature.md`, the three-step roll). A July roll either
(a) keeps `2026-Q3` and refreshes the numbers under it, so `/changes` still
compares against Q2 and `SNAPSHOT_VINTAGE_LABEL` alone moves to 'July 2026',
or (b) treats every monthly roll as a snapshot roll, which makes "this
quarter" a misnomer. **Recommendation: (a)** - `SNAPSHOT_VINTAGE` and
`SNAPSHOT_VINTAGE_LABEL` being two constants already implies it. METHODOLOGY
s6's worked example (SW11 1AA, afford 0.4) may move; `check_worked_example.py`
will say so.

**7. M14 remainder. DONE AND DEPLOYED 2026-09-15.** `/v1/chat`
reported a crashed ScoreFunction as 400 "That location could not be
resolved". The crash arrives as the runtime's error envelope
(`{"errorMessage": ...}`, `FunctionError` set) with no `statusCode` at all,
and `retrieve_context` read "not 200" as "the score API rejected the
postcode". It returns a third value now, the HTTP status the caller should
answer with: 400 with the score API's own wording for its 4xx; **502 "the
scoring service failed" for a crash, a 5xx, an unreadable response or an
unreachable function** (three of those four were ALSO 400 before - M14 named
one); 500 when the function name is unset. `ChatUpstreamFailureTests` drives
`handler`, not the helper, because the helper could be right while the
handler still mapped every error to 400 - 3 of 5 red on HEAD. `/v1/chat` is in
no spec and has no site caller, so nothing else changes.

**8. M23 - station qualifiers. NOT ON THE 14 SEP LIST, and DONE AND DEPLOYED
2026-09-15.** The 13 Sep table had ONE Minor not struck through
and the write-up above said "36 of 37, only M14's half remains" - the
"list that omits a member reads as complete" trap, in the list of remaining
work. Measured: **19 published station entries were a listed place under a
parenthetical** (15 London - "Abbey Wood" / "Abbey Wood (London)" 28 m
apart, Hammersmith once per Underground line - 2 West Midlands, 1 West
Yorkshire, 1 Tyne and Wear), and `build_city_stations.py:22` + `CLAUDE.md`
both still said London's array was "18 hand-picked interchanges" against
693 NaPTAN rows - stale from the day it was written, since the same commit
generated London's array. **The qualifier is split off LAST and RETURNED,
not dropped**: NaPTAN writes it mid-name ("Edgware Road (Circle Line)
Underground Station"), so it is only trailing once the descriptor has gone,
and stripping it first would mangle "Battersea Power Station Underground
Station" into "Battersea Power". `collect` merges on the base and restores
the qualifier only when every node carries the same one - "Kensington
(Olympia)", "Hayes (Kent)", "Bitton (Avon Valley Railway)" keep their
names; dropping it unconditionally would publish "Hayes" beside "Hayes &
Harlington", a new ambiguity for the old duplicate. **1,415 -> 1,390**, every
departed name's base still listed, two names improved
("Shackerstone Rail Station (Battlefield Line)" -> "Shackerstone (Battlefield
Line)"). `test_no_place_is_listed_twice_under_a_qualifier` reads the SHIPPED
arrays like its I19 sibling, red on the old ones with all 19 named. Observed
and left: "Queen's Park" and "Queens Park (London)" differ by an
apostrophe and stay two entries.

**9. `investor` is volatile month to month in the small cohorts - OBSERVED
2026-09-16, MEASURED AND DECIDED THE SAME DAY: option (a), methodology v5.2.**
`scripts/cost_growth_anchor.py` replayed 24 months under four designs: the
city cohort's mean month-on-month growth change was 1.44 with 8.2% of
transitions moving 5+ points and a within-city spread of 8.79/10 (one borough
per city on each rail by construction); the national pool 0.76 / 0.2% / 3.64;
a 3-month smoothed input 0.95 / 4.1% (the rails stay, and it publishes a trend
no integrator can verify against HMLR). Bill chose (a). Cross-city inversions
651 -> 0; `balanced` untouched; `investor` moves on 56 of 99, max 1.8.
CHANGELOG 2026-09-16 (v5.2). *Original observation follows.* The July roll moved 78 of 99 `investor` scores
(mean -0.24) while `balanced` moved 9 by 0.1. Growth scales each tail against
the CITY cohort's real-terms extremes, and a 4-5 borough cohort re-orders on
ordinary HPI month-to-month noise: Hartlepool's nominal trend went +0.8% ->
+5.5% and its growth 0.0 -> 10.0 (investor 5.1 -> 8.5); Newport +5.0% -> +2.0%
took growth 8.5 -> 0.0 (investor 7.5 -> 4.2); Bradford 7.4 -> 0.0; Gedling
10.0 -> 2.7. London's 33-borough cohort barely moved. Nothing is miscomputed -
these ARE the published trends - but a component that can swing 10 points on
one monthly release, in one persona, is a property a B2B buyer would want
named. Options, none costed: (a) anchor growth NATIONALLY as v5.0 did for
affordability (pool the 94 real trends; the same argument - a narrow cohort
manufactures spread); (b) smooth the input (HPI's own 3-month or annual
average, which HMLR publishes); (c) accept and document in METHODOLOGY s4.3.
Measure first: the per-borough month-on-month growth deltas over June -> July
are in `git diff 6439c65 -- backend/lambdas/score/app.py`. Recommendation
pending the measurement; (a) is the one this repo has already accepted the
reasoning for.

**Where this stands after 19 Sep:** **the held frontend is DEPLOYED and
verified from the origin.** All three surfaces went out together -
`index.html`, `data/stations.json`, `data/uk-locator.json` - on a preflight of
**45 blocking stages PASS, `RESULT: PASS`** with no stage skipped. Verified,
never from an exit code: all three hash-MATCH the origin, `stations.json`
answers **200 where it answered 403** (it had never existed at the origin),
both carry `no-cache`, both CloudFront invalidations reached **Completed**, and
`check_deploy_drift.sh` reads **134 of 134** - 16 pages, **18** data files
(`stations.json` is the 18th, exactly as the 18 Sep row predicted) and 100 area
pages, `cache-control: 11 of 11`, all 20 precached assets present. A live search
drove every city against the deployed site: Manchester renders 4 stations
(Market Street, Piccadilly Gardens), London renders Clapham Junction.

**THE DOCUMENTED ORDER WAS BACKWARDS AND IS CORRECTED: `data-deploy` FIRST,
THEN `web-deploy`.** Both rows below, and the 18 Sep memory, said
`python scripts/make.py web-deploy data-deploy`. That uploads and invalidates
`index.html` - which carries **5** references to `stations.json` and **0**
inline `_STATIONS` arrays - *before* `stations.json` reaches the origin, so for
the window between the two invalidations every search on the live site reads
"station list could not be loaded". Reversed there is **no functional window at
all**, because the page that was live carried the inverse (10 inline arrays, 0
references) and simply ignores the new file until the new page lands.
`make.py` honours argument order - confirmed with `--dry-run` before the run,
not assumed. The locator is a genuine wash either way: live `viewBox` was
`0 0 130 168` against the new file's `0 0 130 148`, so either order mis-scales
a decoration briefly, and it has a graceful fallback. **This is the
`fonts-deploy` rule one surface along** - "runs FIRST in `web-deploy-all`, and
that ordering is load-bearing" - and the reasoning was already written in the
Makefile's own `stations.json` comment while the command sat in the opposite
order in three holders. ~~`web-deploy-all` still lists `web-deploy` before
`data-deploy`~~ **Reordered 2026-09-25** (`fonts data web pwa ...`) and gated by
`test_web_deploy_all_ships_data_before_the_page`, proven red on the old line.

**Where this stands after 18 Sep:** the technical backlog was worked
through (CHANGELOG 2026-09-18): `aircraftQuietCoverage` on `/v1/environment`
(**backend DEPLOYED 14:41 UTC on Bill's instruction, ScoreFunction alone,
verified live in all three states**; the frontend half of the commit -
`index.html` viewBox + the regenerated locator - is NOT deployed and the
drift gate reads 2 until `python scripts/make.py data-deploy web-deploy`),
`scripts/make.py` as the Makefile runner (`deploy_hpi_roll.sh` no
longer retypes recipes), `scripts/rotate_epc_token.sh`, the UK locator
regenerated from source, and `scripts/cloudfront_security_headers.py` ready
behind one IAM paste. Both demos (22 and 23 Sep) were dry-run beat by beat
against live; two text slips fixed (weekday, "58" -> 57 checks). **The
afternoon, on Bill's "go" while away** (three more commits, each on a 45/45
preflight): a TfL total outage now lists the four nearest NaPTAN stations
UNDER the notice instead of nothing (`failure-path.mjs` asserts it on the
DOM); **cut 1 of the extraction is done** - the eleven station arrays are
`data/stations.json`, fetched on search intent, page 933 -> 841 KB, the
extraction byte-verified against a NaPTAN rebuild; and `mobile/`'s
Dependabot alerts went 11 -> 7 with the rest recorded in SECURITY.md as
upstream-pinned inside `@capacitor/assets`. PRs #4 and #14 closed as
superseded. **THE FRONTEND IS NOT DEPLOYED - three surfaces wait together:
`index.html`, `data/stations.json`, `data/uk-locator.json`**, held because a
frontend deploy is not for an away window. When Bill is back:
`python scripts/make.py data-deploy web-deploy`, then
`sh scripts/check_deploy_drift.sh` (expect 134 of 134 now that `stations.json`
is an 18th data surface), then a live search in Manchester and in London -
stations must render in both, and the drift gate must not read "MISSING
stations.json" for the page to be honest. **Still Bill's, unchanged**: I17
steps 1-3, the EPC token regenerate (then `sh scripts/rotate_epc_token.sh`),
the `iam-policy.json` paste (now carries BOTH the I17 verbs and the
CloudFront response-headers verbs - one paste closes both), second MFA,
billing alarm, the s3.8 IAM review. The probe reads 5 DENIED until the paste
lands. Not done, deliberately: extraction cuts 2 and 3 (their own day, see
the safe-windows row), visual polish (needs Bill looking), NYC stations
(needs an MTA licence read), the rebrand and everything behind it.

**Where this stands after 17 Sep:** item 2 (badge edge cache) is DONE and
verified live; the M1 row above is struck. Item 1 (I17) has its pages
PREPARED on branch `i17-flip-verification-on` - privacy.html s2a, the
SUBPROCESSORS row, and the template default `SignupVerify: 'on'`, so merging
the branch IS the flip - held RED by `VerifyPagesAndTemplateTests` until step
3's TTL is in the template, so it cannot merge early by accident; steps 1-3
(SES identity, sandbox exit, two IAM verbs) are Bill's, then the merge and
the deploy per OPERATIONS s3.9. Two things found on the way: privacy.html s10
promises "an in-app notice" for material changes and nothing implements one
(a wording decision, in the PR body); and `check_log_retention.sh` went red on
a tree byte-identical to HEAD because `git checkout privacy.html` rewrites
the file CRLF under `core.autocrlf=true` and the gate did not strip `
`
from the page - it does now. Still Bill's: I17 steps 1-3, the EPC token
rotation, AWS Marketplace after the rebrand.

**Where this stands after 16 Sep:** the July roll (`d82e96d`) and v5.2
(`71264c4`) are **DEPLOYED and verified from the origin** - drift 133 of 133,
area freshness 99 of 99, score sanity 28 postcodes at v5.2, site == API on 6.
`scripts/deploy_hpi_roll.sh` is the runbook; a methodology change also needs
`demo-deploy` for `openapi.yaml`, which it does not cover. Item 4 and the nine
Dependabot merges are DONE (evening, on Bill's direct instruction). Still
Bill's: item 2 (badge CloudFront apply), item 1 (I17 flip, needs SES), and the
EPC token rotation. New row: sell through AWS Marketplace,
after the rebrand, as a closing mechanism not a channel.

**Where this stands after 15 Sep:** 7 and 8 are **DEPLOYED 2026-09-15 and verified from the origin**: SAM modified `ChatFunction` alone; `index.html` uploaded `no-cache` and invalidated (completed); live hash == source; 1,390 stations served with 0 duplicates; `check_deploy_drift.sh` 133 of 133; live `/v1/chat` answers 400 with the score API's wording for a bad postcode and 200 for SW11 1AA.
4 needs Bill's one protection
command; 2A needs Bill to apply the prepared distribution config, THEN the
index.html repoint; 6 waits on HMLR; 1 is A when there is an afternoon for
SES - **the code for A is built, tested AND DEPLOYED with the flag off;
OPERATIONS s3.9 is the flip**; **5 is DONE as v5.1 and DEPLOYED**; 3
stands; 7's nine Dependabot PRs are reviewed and green, one merge command
for Bill (the classifier refuses merges).

**Two things from 10 Sep to know when reading the table.** The air-quality
re-run was `--live-only`, so terminated postcodes still hold February's
NO2/PM2.5 in the table - unreachable by any endpoint, harmless, and not drift.
And `data/nspl-feb2026.csv` (805 MB) plus `nspl-aug2026.zip` (185 MB) are
still on disk, gitignored; February earned its keep for the roll diff and can
go whenever the space is wanted - the November roll will diff against August.


### ~~Raised 2026-09-08 - does Sky Score claim WCAG 2.2 AA, or 2.1 AA?~~ DECIDED AND SHIPPED 2026-09-09: **2.2 AA, and it BLOCKS**

> **CLOSED. `wcag22aa` is in `WCAG_TAGS`, so WCAG 2.2 AA now fails preflight
> like 2.0 and 2.1.** The whole backlog - 16 nodes of `target-size` on
> `/score-demo/api-docs.html` - is fixed, and the gate was **proven red**
> against the un-fixed page (`RESULT: FAIL`, exit 1, `[SERIOUS] target-size`
> at all three viewports) and green after.
>
> **The recommendation below was followed, and the diagnosis under it was
> wrong in a way worth keeping.** It read as "raise the hit areas" - a
> small-control problem. It is a **nested-interactive** one: Swagger puts
> `a.nostyle` (deep-link) *inside* `button.opblock-summary-control` (expand),
> so the two targets share pixels. 15 of the 16 nodes were the 5 anchors at 3
> viewports failing on HEIGHT (19px desktop, 14px mobile; the WIDTH was always
> fine at 59-132px), and the 16th was the button at a perfectly adequate
> **306x29**, failing because the anchor **obscured** it to 306x15. Every pixel
> the anchor gains, the button loses - so `min-height: 24px` on the anchor
> alone would have moved the failure, not cleared it. The fix grows the ROW to
> 56px *and* the anchor to 24px together, leaving a 42px unobstructed band.
> Measured at both viewports, and screenshotted: the rows read better than
> before, which is the point of the SC.
>
> **The two-step promotion is the transferable part.** Running the rules first
> (8 Sep) without gating them turned an open-ended scope question into a
> measurement, and *the measurement changed the question* - not "audit the
> product for 2.2" but "override ~20 lines of vendored Swagger CSS". The
> advisory `WCAG 2.2 backlog` stage, `.wcag22-backlog.txt` and the tally
> machinery in `a11y-source.mjs` are **deleted**: a mechanism whose only job
> was to size a backlog that is now empty is dead weight a reader still has to
> understand.
>
> Changed **no published number**, as predicted. The original text follows.

**No WCAG 2.2 rule has ever run against this codebase.** `AXE_TAGS` in
`tests/a11y-source.mjs` is `['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa',
'best-practice']`, and axe tags `target-size` - the rule for the locator
defect closed on 8 Sep - as **`wcag22aa`**. The gate did not weigh those ten
5.2 px targets and pass them; **it never evaluated them.** Same mechanism as
`FAIL_MODERATE` sitting unreachable for want of `best-practice`, which that
same file documents: *a rule that does not run cannot fail.*

**Deliberately not changed as a side effect of the fix** - the comment beside
`AXE_TAGS` warns in terms against that, and promoting an unknown number of 2.2
rules to blocking across 109 pages is a scope change that should be chosen.
The public pages make no conformance claim today, so either level is
defensible.

**DONE, and the backlog is SIZED - 2026-09-08.** `wcag22aa` is in `AXE_TAGS`
so the rules run, and deliberately NOT in `WCAG_TAGS`, so nothing 2.2-only
blocks. Measured across all 134 scanned page-states:

> **1 rule, 16 nodes, 1 state.** `target-size` (serious), every node on
> **`/score-demo/api-docs.html`**. Nothing else in WCAG 2.2 fires anywhere -
> not on the homepage, not on the borough panel, not on any of the 99 area
> pages.

**That one page is the vendored Swagger UI**, so the 16 controls are a third
party's markup rendered through `score-demo/vendor/swagger-ui.css`, not our
own components. The decision is therefore smaller and different from what it
looked like: it is not "audit the product for 2.2", it is **"do we override
vendored Swagger UI CSS, or scope the claim to exclude the API reference"**.

**Recommendation:** raise the hit areas with a local override in that page's
existing `<style>` block - it already restyles roughly twenty Swagger UI
selectors, so this needs no new mechanism - then add `wcag22aa` to
`WCAG_TAGS` so 2.2 starts blocking, and delete the advisory tally. If the
override proves brittle against the vendored stylesheet, the honest fallback
is to claim 2.2 AA for the product and say plainly that the embedded API
reference is third-party. Changes **no published number** either way.

The backlog is reported by preflight's `WCAG 2.2 backlog` advisory stage,
which reads `.wcag22-backlog.txt` written by the scan - because `check()`
prints a stage's output only on failure and `advise()` discards it, so a tally
printed to stdout alone would have been read by nobody.

### Raised 2026-09-03 - four that change PUBLISHED NUMBERS
### Recommendations added 2026-09-04; still undecided

1. ~~**Affordability scaling.**~~ **DONE 2026-09-09 as METHODOLOGY v5.0, in
   source.** Affordability is now a **LOG scale against the 5th-95th percentile
   of borough medians across the whole currency pool**, not min-max within each
   city. Barking and Dagenham **10.0 -> 4.4** at GBP 371,030; Stockton-on-Tees
   **0.0 -> 9.5** at GBP 170,923. All **1,619 inverted cross-city pairs** (of
   4,371) are gone.

   - **LOG, and NOT the linear p10/p90 this file recommended** - that was
     measured and rejected. UK borough medians are strongly right-skewed, and a
     linear scale over them flattened **four of thirteen cities** to under a
     point of internal spread (Teesside to exactly 0.0, all five on 10.0) and
     pinned 22 of 99 boroughs at a rail. Log p5/p95 flattens one city, keeps
     the best mean internal spread of the four candidates (3.1), and still
     clamps at percentiles so one outlier cannot set the scale. Table in
     METHODOLOGY s4.2.
   - **The within-city rank IS published**, as the recommendation asked:
     `context.priceRankInCity` = `{rank, of}`, cheapest first. One nested
     object rather than two flat keys, so the pair cannot drift apart.
   - **Scale of the change: 737 of 792 composite scores move (93%).** London
     falls a mean **1.55** (afford 7.6 -> 1.8), Teesside rises **1.28**, Tyne
     and Wear 1.10; overall mean -0.28. This is the change working - London
     stops reading as affordable and the North stops reading as expensive.
   - **A city cohort compressing is CORRECT, not a defect.** Teesside really is
     171k-200k. The codebase already accepted that argument for Leicester:
     "min-max over a narrow cohort manufactures spread it has not measured".
   - **Pools are per CURRENCY**, so the USD pool is New York's five boroughs -
     the only city outside the UK. UK scores are comparable with each other and
     **not** with New York's, and METHODOLOGY says so rather than implying a US
     national comparison the data cannot support.
   - **Price-to-earnings stays ruled out.** METHODOLOGY s10 commits that
     resident income and wealth are never inputs, because the customer set
     includes Sharia-compliant home-finance providers.
   - **Two defects surfaced while doing it**, both now closed. The site pooled
     **86** sterling boroughs against the Lambda's **94** - it has no CITY_DATA
     entry for the backend-only Cardiff and Nottingham - so p5/p95 differed and
     four boroughs disagreed by 0.1. Only `borough-score-parity.mjs` could see
     that: the formulas were bit-identical, the two holders simply disagreed
     about *who is in the country*. And `check_worked_example.py` had **never
     compared affordability at all** - see the note below.
   - **DEPLOYED AND VERIFIED LIVE 2026-09-09.** Backend first, then 104 web
     uploads and 4 invalidations. Drift **133 of 133**, area pages **99 of 99**
     against the live API, `site == /v1/score` agreeing on every component of
     6 postcodes, `score sanity` 28 postcodes. Barking serves **4.4**, Wandsworth
     **0.4 / score 4.6**, and SW11 1AA serves **5.0** - METHODOLOGY s6 exactly.

   > **A BLOCKING GATE HAD NEVER CHECKED AFFORDABILITY.**
   > `check_worked_example.py` read
   > `app.calc_afford(...) if hasattr(app, 'calc_afford') else None`, and there
   > is no `calc_afford` in the engine - affordability was inline in
   > `calc_score`. The guard was permanently False, the value permanently None,
   > and the loop skips a None. The stage still printed *"every input, bound,
   > component, weight and the final arithmetic agree"*, and it passed on a
   > METHODOLOGY s6 that still showed the min-max formula after the engine had
   > stopped using it. **Second instance of a `hasattr()` guard on a name that
   > does not exist** - the first dropped seven fields from all 99 area pages.
   > It compares 17 things now, up from 16, and was proven red.
2. ~~**Published weights do not reproduce the published score**~~ **DONE
   2026-09-09, in source.** The response now publishes the APPLIED
   (renormalised) table, so `sum(components * weights)` reaches `score` on every
   borough: Brooklyn **4.4826 -> 4.5** (was 3.9 against 4.5), Cardiff **6.2953
   -> 6.3** (was 5.4). Not a separate `weightsApplied` field - that is the
   `lineStatusAvailable` shape, and an optional correct field leaves the naive
   computation wrong for everyone who does not know to switch. The whole
   response-side fix was **deleting one line**: `'weights': weights` sat *after*
   the `**score_data` spread and overrode the applied set `calc_score` had
   computed all along.

   - **Changes no score**, and no weight on the 720 complete combinations - the
     applied values are rounded to 6dp so a complete set republishes the
     declared `0.32` rather than `0.32000000000000006`. Only the 72
     absent-component combinations move, and they move to the truth.
   - **The spec now has two schemas**, because they are two objects:
     `Weights` is what a caller may SEND, `AppliedWeights` what the response
     carries back. Callers using the documented divide-by-the-present-weights
     workaround need change nothing - that denominator is now 1.0.
   - **Both gates were proven red**, and one of them could not have caught this
     before: `check_openapi_matches_engine.py` divided by the present weights,
     and **that division cannot tell the two tables apart** - it recovers the
     same score either way, so it sat green throughout. It asserts the
     published total is 1.0 now, and that the key sets match.
   - **The engine-level tests could not catch it either**, and the first five I
     wrote went green against the live defect: they read `calc_score`, which
     was always right. The guarding test goes through `resolve_query`.
   - **Found while measuring, and NOT fixed - a decision, not a bug.**
     Reproduction is exact only **to the last published digit**: components are
     published at 1dp while the engine weights them unrounded, so the sum can
     sit up to 0.1 from `score` (worst observed **0.069**). Making it exact
     means computing `score` from the ROUNDED components, which **moves 43 of
     792 published scores by 0.1** (19 in London) and rounds twice where the
     engine now rounds once. **This is a fifth numeric decision - see below.**
3. **The 0.60 price-led threshold.** Chosen because "nothing sat between -0.23
   and 0.67". London moved **-0.23 -> +0.55** when `environment` shipped and now
   sits 0.05 below the line, inside that gap. Nothing is over-claimed - the
   threshold is measured at render time - but the constant is now arbitrary.
4. ~~**Flood-gate caching.**~~ **DONE 2026-09-09.** Measured back to back:
   a cold run is **17m28s**, a warm one **1m24s** - a 92% cut on a BLOCKING
   stage whose cost was being paid four times in a single session. Keyed on
   each mosaic's sha256 plus `--per-class` and `--seed`, since a cached run
   at 4 samples says nothing about one at 12.

   **Every guard against "a cache is how a gate quietly stops checking" was
   PROVEN, not asserted:** a corrupt cache, a wrong-shaped one and an
   8-day-old one each return zero entries so everything re-verifies; one
   stale entry among eleven expires alone; a tampered key re-verified that
   city and left the other ten cached; and the rotation covers all eleven
   cities across eleven consecutive days. Only PASSES are cached. Skipped
   cities print **in their own position**, per the `--skip-e2e` lesson. The
   run **fails outright if no city reached the EA service**, which the
   rotating city makes unreachable by construction - asserted precisely
   because the construction is what a future edit would remove. `--no-cache`
   forces a full run.

**RECOMMENDATIONS, 2026-09-04.** Each is a recommendation, not a decision -
all four still change published numbers and all four are Bill's call.

1. **Affordability - national anchor with percentile clamping, AND publish the
   within-city rank separately.** The diagnosis is that **affordability is the
   only component not anchored on a published external threshold**: quiet uses
   measured DEFRA footprints, liveability uses DfE's 0.0 anchor and crime per
   1,000, environment uses WHO 2021 and the EA's 10% Medium-or-High cut.
   Affordability alone is "relative to cohort", and that exception IS the
   Barking/Stockton result. Clamp at the national p10/p90 of the 99 borough
   medians rather than raw min-max, so a single outlier cannot set the scale.
   Keep the within-city signal as an EXPLICIT RANK ("3rd cheapest of 33 in
   London") rather than a disguised score - pure national anchoring flattens
   most of London to 0.0, and choosing WITHIN a city is the dominant consumer
   use case. Surface both with honest labels; an optional field beside a wrong
   one is the `lineStatusAvailable` failure, which this repo has now hit four
   times.

   > **DO NOT reach for a price-to-earnings ratio**, the standard UK
   > affordability measure and the obvious fix. `METHODOLOGY.md` section 10
   > commits publicly that **"income or wealth distributions of residents"**
   > are NEVER inputs, and that section exists because the customer set
   > includes **Sharia-compliant home-finance providers** - regulated lenders,
   > where indirect discrimination is a live compliance question. ONS's ratio
   > uses WORKPLACE-based earnings, which is arguably a different thing from
   > resident income, so this is genuinely arguable - but it is a fine line to
   > walk in a published fairness commitment, and crossing it means rewriting
   > section 10 deliberately rather than as a side effect.

   Changes every published affordability number, so it is a v5.0 bump. Use the
   existing `?compare=previous` and `/v1/changes` machinery to explain the
   movement, and **do this LAST of the four** - the other three are cheap.

2. **DONE 2026-09-09 — but one premise of this recommendation was wrong, and
   measuring is what showed it.** *"holds by construction"* is not achievable by
   renormalising alone, and the reason was **already live and unnoticed**:
   `calc_score` weights the FULL-PRECISION components and rounds once at the
   end, while publishing each component at 1dp. So **37 of the 720 COMPLETE
   sets already failed to reproduce**, with no absent component anywhere near
   them. Publishing applied weights fixes the absent-component half completely
   (worst error **1.518 -> 0.069**) and cannot close a residual that comes from
   component rounding — which is why the residual is identical whether the
   weights are published at 3dp or 6dp. **The gate therefore asserts a DERIVED
   bound of 0.10** (0.05 component rounding + 0.05 rounding the total) rather
   than the observed 0.069, which would have been a magic number with an expiry
   date — the trap decision 3 below is about. Original recommendation follows.

   **Weights - make `weights` the APPLIED (renormalised) weights**, so
   `sum(components * weights) == score` holds by construction, with a gate
   asserting that invariant for every persona x city INCLUDING the
   absent-component cases. **Not a separate `weightsApplied` field.** That is
   precisely the shape this repo has been burned by: the producing comment for
   `lineStatusAvailable` said "consumers can upgrade to read the flag; none is
   required to", which made the second half optional and it never happened. An
   optional correct field leaves the naive computation wrong for everyone who
   does not know to switch. Keep the persona's NOMINAL weights in the spec,
   where they are a definition rather than a reproduction aid.

3. ~~**The 0.60 threshold**~~ **DONE 2026-09-09.** The rank-to-price
   correlation and its 0.60 constant are DELETED - the dead
   `priceDominance`/`rankPrice` machinery with them, since nothing else read
   it. `priceLed` is now structural: a city is price-led iff its
   neighbourhood detail carries **no non-zero sub-borough crime modifier**,
   because without one a generated district differs from its neighbours only
   by price and aircraft quiet - it inherits its borough's liveability and
   crime is not published at postcode-district geography.

   - **It reproduces the correlation exactly** on the day it replaced it:
     London 71 non-zero modifiers and New York 88 (not price-led), all nine
     generated cities 0 (price-led) - the same split the correlation gave at
     +0.55, -0.06 and 0.65-0.89. So no city's disclosure changed.
   - **The code now matches the sentence it prints.** That notice already
     said districts "share their borough's liveability and carry no
     sub-borough crime figure", which is the structural condition - the flag
     was measuring a correlation instead.
   - **Gated** by a second pass in `tests/ranking-separability.mjs`, computed
     from the DATA HOLDER rather than the flag the fix sets, and **proven
     red** by forcing the flag on (London reds).

   Original recommendation follows. **The 0.60 threshold - delete the
   constant, use a STRUCTURAL test.** The
   real question is not the correlation but whether anything besides price
   distinguishes the rows, and for the nine generated cities that is knowable
   without measuring: `crime` is 0 (not published at district geography) and
   liveability is inherited from the borough, so price and aircraft quiet are
   all that vary. London and NYC carry curated medians and a hand-assigned
   crime modifier, so they hold a real differentiator. A structural test is
   deterministic, cannot expire the way 0.60 did, and settles London cleanly
   wherever its correlation drifts next. Same move that dissolved
   `min-height: 380px` in the D3 landscape fix: **a magic number whose job is
   to approximate a fact you can read straight off the data holder dissolves
   when you read it.**

4. **Flood gate - content-key the cache, plus a rotating full check.** Key on
   each mosaic's sha256 so an unchanged city is skipped, **always verify one
   rotating city regardless**, and hard-expire the whole cache at 7 days. Most
   runs drop to near-zero, all 11 cities still get a real EA round-trip within
   ~11 runs, and the gate cannot silently stop checking - which is the actual
   risk named. Print skipped cities **in their own position**, per the
   `--skip-e2e` lesson: a stage that vanishes from a report is
   indistinguishable from one that passed.

### Raised 2026-09-09 - v5.0 COLLAPSED WITHIN-CITY DISCRIMINATION, and South Yorkshire can no longer be ranked

**Measured AFTER the deploy, which is the wrong order and is the first thing to
note.** Before shipping v5.0 I measured affordability spread per city. I did not
measure COMPOSITE spread, and the composite is what colours the map, orders the
ranking and bakes into the 99 area pages.

| City | composite spread before | after | change |
|---|---|---|---|
| South Yorkshire | 2.3 | **0.1** | -2.2 |
| Teesside | 4.0 | 1.7 | -2.3 |
| Cardiff | 4.7 | 2.5 | -2.2 |
| Tyne and Wear | 4.8 | 2.7 | -2.1 |
| London | 4.6 | 3.9 | -0.7 |

**Twelve of thirteen cities lost internal discrimination.** South Yorkshire's
four boroughs now span **0.1 points** with three sharing a published score, so
its ranking is an artefact of rounding. Mean gap 0.033 against a published
precision of 0.1; every other city clears it (London 0.122 is the next lowest).

**REWEIGHTING WAS TESTED AND MAKES IT WORSE - do not reach for it.** The obvious
read is that `quiet` 0.32 + `afford` 0.27 = 0.59 crowds out `live` at 0.27. But a
weight can only amplify variation that exists, and measured per-component
within-city spread says `quiet` varies MOST (5.0-10.0 in most cities) while
`live` and `env` vary LEAST (0.8-2.7 and 0.0-1.4). Three candidate sets, all
shifting weight to liveability, **reduced** spread in twelve of thirteen cities
(London 3.9 -> 3.0, Manchester 2.7 -> 1.5) and left South Yorkshire at 0.1-0.2.
Its ceiling under ANY weighting is 3.0, and only by putting all weight on growth,
which `balanced` deliberately zeroes. South Yorkshire's `quiet` spread is
**0.0** - Doncaster Sheffield closed to commercial flights in 2022, so all four
boroughs are equally quiet. None of the candidates put a London borough back in
the national top 12 either.

**The honest reading favours v5.0.** The old 2.3-point spread was almost entirely
affordability, MANUFACTURED by min-max forcing 0-10 across a narrow price band.
Strip that out and the remaining inputs barely differ across those four
boroughs. So this is a finding about **how little we measure that separates
similar places**, not about the anchor - and it is the Leicester argument again,
one level up.

**Recommendation: disclose it, measured at render time.** A note on the borough
ranking when the mean gap between adjacent boroughs falls below the published
precision - derived from 0.1, never a chosen constant, because the `priceLed`
0.60 sitting a few lines away in `index.html` is a standing warning about
exactly that and has already expired once. Today it fires for South Yorkshire
alone and no city's numbers change.

> **SHIPPED 2026-09-09, gated, after one false start worth recording.** The
> disclosure lives in `renderBoroughRanking()` and
> `tests/ranking-separability.mjs` asserts the RELATIONSHIP in both directions
> - a city discloses iff its rendered scores are too close to rank, recomputed
> from the DOM rather than read off the flag the fix sets. **Proven red both
> ways**: unwiring the note reds on South Yorkshire, forcing it on reds on the
> six separable cities.
>
> **The first attempt was abandoned on a WRONG DIAGNOSIS, and both bugs were
> in the harness rather than the page.** It reported "the ranking did not
> draw" for every city, which read as a rendering fault; the table was drawing
> perfectly.
>
> 1. **The score cell renders `<span aria-hidden>GLYPH</span> 7.9`**, so a
>    bare `parseFloat(td.textContent)` hits the glyph and returns NaN for
>    every row. Take the TRAILING number.
> 2. **The poll waited on a condition the previous city already satisfied**
>    ("more than one score cell exists"), so every reading came back one city
>    stale. Comparing counts as well is not enough either - Merseyside and
>    Tyne and Wear both have five boroughs and alias. Wait until the rendered
>    `data-rank-name`s ARE the target city's borough set.
>
> Two states must still be reached before anything is measurable:
> `#tab-ranking` ships `display:none`, and `rankingView` defaults to
> `neighbourhood`, whose scores the national anchor never touched.

### Raised 2026-09-09 - a FIFTH numeric decision, surfaced by fixing the second

**Should `score` be computed from the ROUNDED components, so the published
arithmetic reproduces the published number EXACTLY rather than to within 0.1?**

Found by measuring, and it had been true and unnoticed since long before the
weights work: `calc_score` weights the full-precision components and rounds once
at the end, but publishes each component at 1dp. So a customer adding up what we
give them can land up to 0.1 away from the score beside it, **and this is not
caused by the absent-component defect just fixed** — 37 of the 720 COMPLETE
persona-borough sets already did not reproduce.

| | |
|---|---|
| Today, after the applied-weights fix | **43 of 792** combinations do not reproduce at 1dp; worst residual **0.069** |
| If `score` were computed from rounded components | **0 fail** - reproduction becomes exact |
| Cost | **43 of 792 published scores move by 0.1** (london 19, nyc 4, leicester 4, teesside 3, then 2s and 1s) |

**The trade is real in both directions, which is why it is a decision.** Exact
reproducibility is worth something to a B2B integrator whose auditor is checking
our arithmetic, and `terms.html` obliges them to carry our numbers through.
Against that, scoring from rounded components **rounds twice where the engine
now rounds once**, which is straightforwardly less accurate: the 1dp component
is up to 0.05 from the value actually measured, and that error would become part
of the score rather than being averaged out of it.

> **DECIDED 2026-09-09: WON'T CHANGE, and the bound is now GATED.** `score`
> keeps being computed from the full-precision components and rounded once.
> What that decision left behind was a **published number with no check** -
> METHODOLOGY s6 and the `AppliedWeights` schema both state a measured worst
> case, and a vintage roll, a new city or a scoring change could grow the
> residual past what they claim with nothing noticing.
>
> `test_the_published_residual_figure_does_not_understate_reality` reads both
> documents and fails if either claim is **below** the measured worst. Asserted
> as "must not understate", never as equality: a residual that shrinks leaves
> the documents conservative, which is honest, while pinning the figure would
> be a magic number with an expiry date - the trap decision 3 was about.
> **Proven red** by lowering the claim to 0.010.
>
> Measuring for the gate also corrected the figure: the worst residual against
> the weights **as published** (rounded to 6dp) is **0.0674**, not the 0.069
> computed from unrounded ones. Both documents now say "under 0.07", which is
> true, stable, and not spuriously precise.

**Recommendation: do NOT change it. Publish the bound instead** - which is now
done, in METHODOLOGY §6 and the `AppliedWeights` schema, stated as "exact to the
last published digit, worst observed 0.069". The precedent is already in this
codebase and is the honest one: `attribution` has always published
`roundingResidual` beside itself rather than forcing the parts to add up. **A
number that is 0.069 out and says so is better than one that is exact and less
accurate.** If it is ever revisited, the cheaper alternative is to publish
components at 2dp, which shrinks the residual tenfold and moves no score at all.

**Nothing is over-claimed today** - the bound is documented and gated - so this
is a "could be better", not a defect.


| Decision | Default | Resolve when |
|---|---|---|
| **Batch metering / what the free tier may be worth** | **Resolved 2026-07-29**: option B at `Quota.Limit: 100` (**10,000 free scores/month**, was 100,000), `RateLimit` 2 → 1. API Gateway meters *requests* while the product sells *scores*, and `MAX_BATCH_SIZE` 100 made the advertised 1,000 really 100,000 — drainable by one key in ~8.5 minutes, i.e. the entire volume proposition of the £499 tier, free. The multiplier is now **stated** on `/pricing`, `/api/` and in the OpenAPI spec, and returned as `batchMultiplier` + `monthlyScoreCeiling` in the signup response, rather than left for customers to derive. In-Lambda per-score metering (option A) stays deferred until a paying customer justifies operating it. **Deployed and verified live 2026-07-29** — plan `sjtyz8` reads 100/month from the API; the shared `/score-demo` key was relinked to its own `SkyScoreDemoTier` (`x88go8`, 2,000/month) in the same session. Full analysis and the rejected options in [`BATCH_METERING_DECISION.md`](./BATCH_METERING_DECISION.md). | n/a |
| Professional tier's own batch multiplier | **DECIDED 2026-07-29 and SHIPPED — verified 2026-08-27 on all four surfaces** (`pricing.html`, `api/index.html`, `score-demo/openapi.yaml`, signup `upgrade` block with `scoreCeilingBasis: 'fair-use'`). This row read "NOT YET IMPLEMENTED" for four weeks after the work was done — the seventh stale record found in one day. Original decision follows. Professional keeps **100,000 requests/month** but gains a published **1,000,000 scores/month** ceiling stated beside it — the same move made on the free tier, for the same reason: requests are the wrong unit and the honest fix is to name the number the customer actually buys rather than let them derive it. Rejected: cutting the request quota to 10,000 (caps scores correctly but punishes the single-address integrator, the likelier first customer), and building per-score metering now (right eventually, premature before a paying customer exists). **What was wrong before:** ×100 made the real entitlement 10,000,000 scores for £499 — roughly every home in London three times a month, drainable in under 3 hours at the batch route's 10 rps — which undercut both the £12k Enterprise floor and the £2,500 pilot. **Caveat to carry:** APIGW meters requests only, so until per-score metering (option A) ships, the 1,000,000 figure is a *published commitment*, contractually useful but technically unenforced. Do not record this as closed on that basis. | Implementation: before Professional launches |
| Channel wall design (granularity / volume / format) | Granularity | Before first paying API customer |
| API pricing model | Per-query, tiered | When first prospect asks |
| Score response shape (opinionated / components / both) | **Resolved 2026-05-05**: both. `/v1/score` returns `score` + `components` + `context`. Optional `?weights=` lets customers override defaults. | n/a |
| Buildathon fork repo name | `sky-score-halal` | When Foundation confirms eligibility |
| Whether to delete the 5 dormant Bedrock Lambdas (chat, multi_agent, analyze_image, analyze_document, report) entirely vs. keep template entries | **Resolved 2026-05-07**: keep dormant in template; Lambda has zero idle cost on on-demand pricing, and re-introducing any feature later as a user-triggered constrained variant is just unhiding the UI block. Re-evaluate if Bedrock pricing model changes. | n/a |
| CORS for `/v1/score` from third-party browser origins | **Resolved 2026-05-05**: global CORS opened to `*`. The score endpoints are API-key gated; the Bedrock endpoints are throttled at API Gateway (10 req/s) and CORS does not protect against server-side abuse anyway. | n/a |
| OpenSky commercial-licensing, replace, negotiate, or decouple | **Resolved 2026-05-07**: removed live_flights Lambda + UI from consumer site and prototype after research showed OpenSky's terms require a written agreement for any operational use, including consumer surfaces. Email sent to contact@opensky-network.org enquiring about licensing options. Lambda code lives in git (commit `a214ba0`); restore once a licence lands or after evaluating alternatives (AviationStack, FlightAware AeroAPI, self-hosted ADS-B). | n/a |
| EPC: API-on-demand vs bulk download | API now; bulk download once approaching rate-limit pressure (~50% of 6000-per-5-min quota) | When B2B traffic ramps |
| NYC ZIP-to-borough resolution | **Resolved 2026-05-05/06**: ~182 residential ZIPs supported via static lookup; ~110 with per-ZIP centroids for Haversine quiet-score. `?postcode=10001` and `?postcode=11201` work alongside UK postcodes. Non-NYC US ZIPs return a structured 404. | n/a |
| Native iOS / Android distribution | **In-flight 2026-05-10 (Wave 13.8.14)**: full release pipeline including Codemagic iOS signing wired and operational. Capacitor wrapper + Codemagic CI for iOS; Android local-build via Android Studio per `mobile/ANDROID_BUILD.md`. fastlane metadata push works against `uk.co.skyscore.app` ASC record (description, keywords, copyright, URLs, app review notes all auto-pushed). Apple Team ID `L3UXT79KFZ` resolved; Universal Links AASA file live at `skyscore.co.uk/.well-known/apple-app-site-association`. Codemagic Personal Account signing solved after 12 iterations: env-var-based pattern (NOT named-integration lookup) with `groups: [asc]` import, `ios_signing` block removed to disable opaque pre-flight key selection, fresh per-build private key for the Distribution cert. Pattern documented in `mobile/CODEMAGIC_SETUP.md` and `memory/feedback_codemagic_personal_account_signing.md`. Remaining: confirm first build hits TestFlight, upload screenshots, run `fastlane ios submit_for_review`. Caveat: current setup creates a new Distribution cert per build (Apple's 2-cert team limit) — needs `CERT_PRIVATE_KEY` env-var persistence before build 3. | Once iOS submission lands in App Store review queue (target: this week) |

---

## Git sync — contradiction resolved 2026-08-27

The project `CLAUDE.md` said *"Keep git local only, never push"* while the global
rules say push/pull is the **only** safe sync mechanism and that drift should be
surfaced. That contradiction stalled 21 commits on one machine and cost two
round-trips in one session to resolve. **Bill's ruling: push.** The global rule
governs; the project line is superseded and has been corrected where it lives.

## Cross-references

- `archive/BUILDATHON_PLAN_2026.md`, the buildathon plan (archived 2026-08-24)
- `AUDIT_REPORT.md`, code quality snapshot (re-run pending)
- `CLAUDE.md`, Claude session conventions
- `README.md`, public-facing project documentation
- Memory: `project_api_target_customers.md`, `project_buildathon_focus.md`, `project_competitive_landscape.md`, `feedback_no_riba_customers.md`, `project_siraj_noor.md` (sister project)

## Design notes for deferred work

Detailed scoping for the two main outstanding items in Track 2. Captured 2026-05-05 so future-self picks up with context.

### ~~NYC ZIP-to-borough resolution~~, **shipped 2026-05-05/06**

Captured original 2-3-hour scope; actual build came in close to estimate plus a v3.1 follow-up that added per-ZIP centroids for the Haversine path. Final shape: 182 residential ZIPs across the five boroughs, ~110 with explicit centroids; ZIPs without centroid fall back to borough-aggregate Lden bands; non-NYC US ZIPs return a structured 404 with the supported borough list. Live-verified against test postcodes 10001, 11201, 11375. See commits `af201fb` (initial detection + tests), `156b622` (v3.1 centroids), and `app.py` lines 105-260 for the data structures.

### Per-postcode noise sampling — code shipped 2026-05-06, full run pending

> **v3.0 update (2026-05-05)**: Option 2 (Haversine port from consumer site) shipped. Per-postcode quiet via airport + flight-path geometry live in `/v1/score` for UK postcodes. Methodology v3.0 documents the formula in §4.5. NYC ZIP centroids also v3.1.
>
> **v3.1 update (2026-05-06)**: DEFRA raster sampling code shipped. Loader, mosaic, score-Lambda integration all live; ~38k Greater London postcodes already populated from a previous v1 partial run, plus ~16k new v2 sentinel rows added before the run was paused. The score Lambda's resolution chain is: raster → postcode-Haversine → borough fallback. Postcodes inside the bbox but outside the 40 dB contour use a v2 below-threshold sentinel (35.0 dB Lden → quiet=10) so suburban postcodes correctly score quiet from aircraft. Verified live: TW6 2GA (Heathrow village) returns `raster` with Lden 61.7 dB. **Pending**: complete the v2 loader pass (~25 min wall-clock), then re-verify Twickenham/Wimbledon/Hampstead now hit the sentinel path. After that: per-city WCS fetches for the rest of the UK Core Cities (Birmingham, Manchester, etc.) — gated on first paying integrator asking for non-London coverage.

#### Current limitation (concrete)

The Lambda's quiet component is a single categorical lookup per *borough*, so every postcode in a borough gets the same quiet score. Within-borough variation can be 10-15 dB Lden, a 2-3 component-point error in a 0-10 score.

| Borough | Borough Lden band | Reality at specific postcodes |
|---|---|---|
| **Hounslow** | severe (≥75 dB) | TW6 (Heathrow approach): genuinely severe. **TW1 (Twickenham, ~62 dB)**: should score ~5/10. **TW8 (Brentford, ~58 dB)**: should score ~6.5/10. |
| **Richmond upon Thames** | high (70-75 dB) | West (Hampton, Teddington): 70+ dB. **East (Richmond town centre, Sheen, ~62 dB)**: should score ~5. |
| **Wandsworth** | moderate (60-65 dB) | Battersea Heliport area: ~68 dB. **Tooting Bec (~55 dB)**: should score ~7.5. |
| **Greenwich** | moderate | London City approach corridor: ~70 dB. **Blackheath (~55 dB)**: should score ~7.5. |

This is the methodology weakness B2B audit teams will challenge first.

#### Replacement approach

Use the postcode's lat/long (postcodes.io already returns it) to sample two data sources:
1. **DEFRA Strategic Noise Mapping raster**, sample Lden value at postcode centroid (10m grid resolution)
2. **Haversine distance to flight paths and airports**, already implemented in the consumer site (`calcScores()` in `index.html`)

Combine into continuous dB-based score:
```
quiet = 10 × clip( (75 - effective_lden) / 25, 0, 1 )
```
Where `effective_lden = max(raster_lden, flight_path_proximity_lden)`.

#### Side-by-side

| Aspect | Borough-level (now) | Per-postcode (deferred) |
|---|---|---|
| Within-borough variation | None | Real |
| Accuracy | ~80% at borough; ±3 points within borough | ~95% (limited by raster resolution) |
| Defensibility | "DEFRA borough-aggregate", coarse | "DEFRA raster sampled at postcode centroid + Haversine flight-path proximity", gold standard |
| Audit risk | Real, surveyors will challenge | Should pass clean |
| Latency per request | <5ms | <20ms (pre-computed in DynamoDB) |
| Build effort | Done | ~1 day + overnight batch |

#### Build plan

1. **Acquire DEFRA Lden raster** for England round 4 (2022), 1h, free from data.gov.uk, ~500 MB GeoTIFF
2. **Pre-compute postcode-centroid samples**, script over ~1.7M UK postcodes, store in DynamoDB. Overnight batch, ~£5 compute.
3. **Lambda code change**, replace `IMPACT_TO_QUIET[impact]` with DynamoDB read by postcode, fall back to borough-aggregate if missing. ~2h.
4. **Port flight-path distance scoring** from consumer site Haversine logic, ~2h.
5. **Methodology update**, §4.1 revision, version bump to 3.0. ~1h.
6. **Validation**, spot-check 20 postcodes against DEFRA noise contour map. ~1h.

**Effort: ~1 working day + overnight pre-compute.**

#### When to ship

The trigger is **first paying B2B customer asks "do you have postcode-level noise resolution?"**, aggregator-tier customers will ask in their first audit. Until then, borough-level + the documented limitation in methodology §9 is honest and acceptable.

### Recommended order for deferred work

| When | What | Why |
|---|---|---|
| Next short session (2-3h) | NYC ZIP resolution | Highest leverage per minute spent. Removes a known limitation cheaply. Marketing-ready. |
| Next focused day | Per-postcode noise sampling | Larger accuracy win. Best done with fresh head over a longer block. Closes the audit-defensibility gap. |
| When OpenSky reply lands (or after 4 weeks no reply) | OpenSky licence decision (use, replace with paid alternative, or skip the feature) | Unblocks live-aircraft re-introduction |
| Before public launch | Polish: domain (`skyscore.uk`), homepage CTA for "API access", contact form | Commercial-readiness |

## Monetisation strategy (decided 2026-05-05)

**Decision: Convenience-tier monetisation. NOT granularity wall.**

Sky Score charges for *integration value* (SLA, structured JSON, batch, audit trail, methodology version pinning, support, contracts), **not** for data exclusivity. Consumer site keeps all features; the API earns its price through reliability and ergonomics.

### The four models considered

| Model | What you charge for | What stays free on consumer site | Real-world example |
|---|---|---|---|
| **Convenience tier** ⭐ chosen | Integration ergonomics: SLA, structured JSON, batch, OpenAPI, audit log | Everything | Hometrack/Zoopla, Companies House, Land Registry, Ordnance Survey |
| Granularity wall | Per-postcode resolution; per-component access | Borough-level summaries only | Bloomberg Terminal vs free public data |
| Volume wall | Rate-limited access above a threshold | First N lookups free per session | Newspapers, metered SaaS |
| Format wall | Structured / embeddable / batch data | UI-rendered display only | Spotify embed vs API |

### Why convenience tier (and not granularity wall)

1. **Target customers don't compete with the consumer site.** Landmark, TM Group, OneSearch (aggregators) want SLA + batch + structured JSON; Al Rayan, StrideUp, Gatehouse (Islamic finance) want underwriting depth; conveyancers want product-bundle integration; B2R operators want site selection. None of these customers' value depends on Sky Score not having a public site.
2. **Consumer site is the marketing engine.** Every prospect who searches "Sky Score" lands here first. Stripping features means losing inbound pipeline.
3. **Removing features creates support cost without revenue.** "Why does the consumer site no longer show X?" emails don't convert.
4. **Real customer feedback should drive feature decisions.** Don't optimise for theoretical objections, wait for actual ones.

### What customers actually pay for (the convenience-tier value list)

| Value | Sky Score has it? |
|---|---|
| **SLA** with refund/credit commitments | Not yet, commit one in first contract |
| **Per-customer API key + Usage Plan** (billing isolation) | API Gateway supports; hand-issue per customer in Phase 1 |
| **Bulk endpoint** (`POST /v1/score/batch`) | Shipped |
| **Structured response** (OpenAPI 3.0 spec) | Shipped |
| **Audit log access** (per-key CloudWatch filter) | Available; could expose to customers |
| **Methodology document for due diligence** | Shipped (v3.5 as at 2026-08-04; the "v3.1" here was stale by four versions) |
| **Methodology version pinning** (`?methodology=` for grace periods) | **NOT BUILT — and "Documented in §16" was the problem, not the status.** The parameter is read nowhere in the score Lambda, so a caller passing it is silently ignored and receives current-version numbers believing they pinned. §16 promised it, the Round 5 plan relied on it, and the change policy hung a contractual 14-day grace period off it. All three retracted 2026-08-04. Build when a contract requires it: it needs retained data vintages **and** retained formula code paths (reproducing v3.0 needs the pre-v3.2 clamp, pre-v3.3 weights and pre-v3.4 growth formula). `?compare=previous` + `/v1/changes` cover the "what moved and why" case meanwhile |
| **Custom weights + persona profiles** | Shipped (`?weights=`, `?persona=`) |
| **Selective response shaping** | Shipped (`?include=`) |
| **Data refresh on a schedule** | Documented commitment in §7 |
| **Dedicated support channel** | Email per contract; future Slack Connect |
| **Status page + uptime visibility** | Shipped (`/score-demo/status.html`) |
| **MSA + DPA template** | Use CommonPaper.com or PandaDoc UK template, recommendation, not for me to draft |
| **Future: ISO 27001 / SOC 2** | Multi-year track |

### Pricing structure (illustrative; firm up after first conversation)

| Tier | Quota | Indicative price/month | Customer profile |
|---|---|---|---|
| **Developer** | 5,000 req/month | £49 | Individual integrator, evaluating |
| **Professional** | 100,000 req/month | £499 | Small platform integrating Sky Score |
| **Enterprise** | Custom | £2k-£20k+ | Aggregators, large integrators (Landmark-shape) |

### Revisit triggers

Switch toward granularity / volume / format wall **only when**:
- A real paying customer says "your consumer site undermines my product"
- Multiple customers (3+) ask for the same restriction
- Pricing pressure from prospect feedback becomes evident

Until those triggers fire: keep all consumer features. Charge for integration value.

### What we explicitly will NOT do pre-emptively

- ❌ Remove per-postcode / per-neighbourhood scoring from consumer site
- ❌ Add a consumer signup wall pre-emptively
- ❌ Hide methodology behind a paywall (transparency wins B2B trust)
- ❌ Split consumer site into "free borough / paid postcode" tiers

**Updated 2026-05-07**: AI features (chat, multi-agent, image/document analysis, AI report) were removed from the consumer UI. Reasoning: methodology defensibility is the B2B story, and AI summaries on top of deterministic scoring add variance that B2B audit teams will challenge first ("not fully accurate" is structural, not tunable). The 5 Bedrock Lambdas remain dormant in `template.yaml` for potential re-introduction as user-triggered constrained features (e.g. "explain in plain English" button) once consumer feedback warrants it. Bedrock-cost saving was a secondary win (~$80-115/mo at modest traffic).

These are theoretical optimisations against problems that don't exist yet.

### Optional intermediate step

If outreach picks up and prospects look confused about how to find the API: add a focused `/api` landing page on the consumer site (B2B discovery surface). Routes prospects toward the API funnel without removing consumer features. ~30 min to build; defer until outreach signal warrants it.

### When *each* customer might ask for restrictions (and how to handle case-by-case)

| Their objection | Real fix (without breaking other customers) |
|---|---|
| "Our customers can Google your free site" | Custom contract clause: integration doesn't show "Powered by Sky Score" branding; consumers Googling don't connect the dots |
| "Free per-postcode data undermines our pricing" | Move per-postcode access behind a consumer signup wall (capture email; rate-limit). Site still works; data still public; their pricing unaffected. |
| "We need data exclusivity" | Custom enterprise tier with API-only fields not on the consumer site (e.g., commercial-tier aviation source, future paid-data sources) |

Each is a *case-by-case fix triggered by real feedback*, not pre-emptive site stripping.

## Update protocol

When a task ships or a decision lands: update this file rather than the chat. Treat unresolved items in "Near-term tasks" and "Open decisions" as the source of truth between sessions.
