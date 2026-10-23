# Audit Report — Sky Score

**Date:** 2026-10-22
**Commit audited:** `8d89c0d` (the 47 commits since the 16 October audit, `a5c8f89..8d89c0d`), plus a whole-repo
pass for secrets and personal data.
**Files scanned:** the changed source files (Python, JavaScript modules, HTML, YAML, shell) in full, every tracked
file for secrets and personal data, and the changed pages driven in a browser at 1440x900, 390x844, 320x568 and
844x390 (plus 915x412 for the map).
**Method:** three read-only reviews in parallel (code correctness, security, front end and accessibility), each
reading the audited commit rather than the working tree (another session was editing it) and told to verify every
finding before reporting it. Findings marked **re-checked** were then reproduced in session against the code or
data; the rest stand on the reviewer's own measurement, which each report records, and are labelled so.

**Fixed the same day** means changed in the working tree after the audit and before the next commit; nothing here
was deployed by the audit. Three of the Important items changed numbers the Bay Area's API release was about to
publish, so they were put to Bill and decided the same afternoon.

## Critical Issues

None.

## Important Issues

| # | Issue | File:Line | Category | Status |
|---|-------|-----------|----------|--------|
| I-1 | **The leading rename candidate was back in the public repo**, against CLAUDE.md's branding rule (candidate names stay out until their domains are bought). Added 7 Oct, scrubbed by 12 Oct, re-added 16 Oct in a START HERE block, on both remote branches. | `ROADMAP.md:281` | Security / personal and business data | **Fixed the same day** (re-checked: `git grep` now finds no candidate name in the tree). It remains in git history since 7 Oct, so **buying the three domains is the lasting fix** (Bill's job, NOW.md s1). |
| I-2 | **Bay Area transport was not on the UK's bands, although every note said it was.** The builder typed 50/25/10% while the UK's cut-points are 75/50/25% (`build_borough_bands.py`), so 25 of 49 cities read one band better than the same share earns in the UK (San Francisco 61.9%: excellent, not good). The choice put to Bill on 22 Oct described 50/25/10 as "the same four bands the UK uses", which was false. | `scripts/build_bayarea_transport.py:40` | Code / methodology | **Fixed the same day on Bill's decision** (UK cut-points), re-checked. `BANDS` is now PARSED from the UK holder, and a test compares it with the UK's own `transport_band()` over every tenth of a point (proven red). 1 excellent (Colma), 1 good (San Francisco), 4 moderate, 43 poor; Emeryville stays withheld (with Capitol Corridor put back it would read good, not excellent). |
| I-3 | **The US crime anchor was not like for like.** California's 22.27 per 1,000 counted every agency, including crimes recorded by railroad police, universities, the Highway Patrol and transit, which no city's own rate can contain, so every city read better than its anchor by construction (San Jose 3.5 instead of 3.3 on the US scale). | `scripts/build_bayarea_crime.py:116` | Code / methodology | **Fixed the same day on Bill's decision** (like for like), re-checked: 34,447 crimes of 209 agencies left out, anchor **21.39**. Every agency is put in one of four classes (a Census city or town, a sheriff, a declared community police force, or a no-residents agency by pattern), held both ways: an unclassified agency or a stale declared name stops the build. Proven red twice. |
| I-4 | **Bay Area growth sat on its rails by construction.** FHFA's trend is county-wide, so the 50 cities hold four values, and in their own pool the dual anchor put San Francisco (+0.5% nominal, a real-terms fall) on 10.0 and all 14 Alameda cities on 0.0: the shape v5.2 went national to remove. | `backend/lambdas/score/app.py` (`pool_of`), `scripts/build_bayarea_records.py:84` | Code / methodology | **Fixed the same day on Bill's decision** (held out), re-checked: `growthNotScored` on the registry entry; the component is dropped and its weight redistributed, `context.growthBasis` reads `not scored`, and `coverage.notices` says why on every response. |
| I-5 | **Sold-price rows hide the new labels and the address.** The "leasehold flat / not a standard sale" label now comes before the address in a one-line, ellipsised cell, so 3 of 4 rows are cut at 1440 and all 4 at 390 and 320, with no way to read the rest; the price and text also touch with no gap. | `index.html:2089` (`.sold-address`), `:11286` | Front end | **Fixed the same day:** the cell wraps (`overflow-wrap: anywhere`, no ellipsis) and `.sold-row` has an 8px gap. Re-checked the cause in the CSS; the widths were the reviewer's measurement. |
| I-6 | **"Have your say" sends people to the nearest airport, not the one whose route passes them.** For SW11 1AA the answer names Heathrow 27L's approach 1.1 km away, yet offers only London City's pages (LCY is 15.4 km, LHR 18.5 km; both verified and in scope). | `js/street_report.mjs:139-141` (`haveYourSay` reads `scope[0]`) | Front end / wording | **Fixed the same day:** `haveYourSay()` takes the whole route result and names the airport whose final approach or departure passes nearest (else the nearest airport in scope), and none when that airport's pages are unverified, never a neighbour's. Held in `tests/front-page.mjs` on a Battersea case the old rule fails. |

## Minor Issues

| # | Issue | File:Line | Category | Status |
|---|-------|-----------|----------|--------|
| M-1 | The local MCP server sent its key to whatever `SKY_SCORE_API_BASE` named, a variable it shared with the sanity check, over http if that said so. | `mcp-server/sky_score_mcp.py:36` | Security | **Fixed the same day:** its own variable, and a keyed call refuses any base that is not the API's own host over https (tested, proven red). |
| M-2 | The MCP server matched borough names exactly, so "Bristol" and "Nottingham" (the API's "City of ...") found no city, were asked in London and read NOT COVERED YET. | `mcp-server/sky_score_mcp.py:131` | Code | **Fixed the same day:** the API's own loose key, held against the Lambda's function over every borough (tested, proven red). |
| M-3 | `compare_areas` dropped `coverage` and `weights` from each row, so a comparison lost the notices that say an input is withheld. | `mcp-server/sky_score_mcp.py:222` | Code | **Fixed the same day** (tested). |
| M-4 | `adsb_extract.py` reads a whole tar member before any size check; the 64 MB cap applies only to gzip output, so a plain member declaring gigabytes is read and then pickled to a worker. Reproduced by the reviewer on a synthetic 200 MB member. | `scripts/adsb_extract.py:241` | Security | **Fixed the same day:** a member over the cap is never read and counts as one bad trace (tested on a synthetic tar, proven red). |
| M-5 | About 30 tracked files carry the Windows user path (8 lines added in this window: `scripts/adsb_fetch.py:25`, `CLAUDE.md:65/76/205`, `docs/lessons/in-progress-measurements.md:52`). | various | Personal data | **Fixed 2026-10-23** (Bill: do it): 31 lines in 19 files now write `%USERPROFILE%`, `~` or `$env:USERPROFILE` as each place reads it; `tests/test_no_user_paths.py` (any user name, proven red on the 31) keeps it out. Git history still holds the path (rewriting it is Bill's call, parked). |
| M-6 | A saved Rightmove page names two branch staff. Public since 8 Aug; earlier audits missed it. | `tests/fixtures/rightmove-real-letting-nw2.html:6` | Personal data | **Fixed the same day:** the two names replaced in place (the extension's 14 extraction cases still pass). They remain in git history since 8 Aug. |
| M-7 | Staten Island's note says Newark departures pass "at high altitude"; the EWR 22L departure via PORTT4, scored since this window, has three vertices inside the borough 6-8 km from the runway. | `index.html:5804` | Front end / wording | **Fixed 2026-10-23:** the note now names the PORTT route and where it crosses (the north-west, a few km after take-off, still climbing); "high altitude" had no source (CIFP codes none after 518 ft). `tests/test_staten_island_note.py` holds each claim to the data (proven red on the old note). |
| M-8 | `bayarea_blocks.py --check` catches a misplaced block in one direction only (PL header 99999 against a BAF city compares `''` with `''`). Real data has none today. | `scripts/bayarea_blocks.py:81` | Code | **Fixed the same day:** compared both ways (real data still has 0 such blocks; the check passes on all 519,723). |
| M-9 | The coverage strip names Nottingham and Greater Norwich, which the search box says it does not know. | `home/index.html:414`, `js/home-engine.mjs:1268` | Front end | **Fixed 2026-10-23:** "Nottingham" and "Greater Norwich" are now named as scored by the API but not drawn on the map, with their council areas from the open-data rows (`tests/front-page.mjs`, proven red). |
| M-10 | The map's air line promises "the nearest sensor and monitor" where one is shown (every postcode outside London). | `index.html:13072` | Front end / wording | **Fixed the same day:** the line now says "the nearest air quality readings within 5 km", true whichever rendered. |
| M-11 | Air rows (new) and station rows (old) run the name and the distance together (no `.transport-row` rule). | `index.html:10840`, `:10792` | Front end | **Fixed the same day:** a `.transport-row` rule (flex, space-between, 8px gap) for the stations and the air rows. |
| M-12 | The map's air credit links are browser-default blue, unlike every other panel link. | `index.html:10844` | Front end | **Fixed the same day:** the air section's credit links take the panel colour and a new-tab arrow (scoped: another note link has its own arrow). |
| M-13 | The two new brand links fall back to the browser's focus ring, not `--focus`; on score-demo only "Sky Score" in the heading is a link, invisibly. | `index.html:247`, `score-demo/index.html:78/388` | Accessibility | **Fixed the same day:** the map's brand and every area and open-data link take the 3px `#d35a12` ring; on score-demo the brand is underlined at rest and the stray space is gone (score-demo ships with `demo-deploy`, so with the Bay Area release). |
| M-14 | The Copy fallback says "Ctrl+C" on every device, iPhone included. | `js/home-engine.mjs:289` | Front end | **Fixed the same day:** Ctrl+C, Cmd+C on a Mac, "copy it from the menu" on a phone or tablet. |
| M-15 | Pre-existing: `/api/` scrolls sideways at 320x568 once "How accurate is the noise estimate" is opened (inline `code`, 342 px; WCAG 1.4.10). | `api/index.html:210` | Accessibility | **Fixed the same day:** `code { overflow-wrap: anywhere; }`. |

## Found by the Bay Area work the same day (not an audit finding)

- **The API's 404 for an uncovered postcode named London** ("Borough not currently supported in london" for EX1
  1HS), found by the MCP server's first live test. Fixed in source: "Not covered yet: ... outside every city Sky
  Score scores", with `supportedCities`; documented in the OpenAPI 404.
- **A New York ZIP sent with another city was answered as New York in silence.** Now refused.
- **Thin-data cities lead the Bay Area.** 15 of 50 drop a component under the two-input floor (9 Santa Clara
  cities lose environment, FEMA not having mapped their flood risk; 5 sheriff-policed cities and Emeryville lose
  liveability), which put Gilroy, Emeryville and Morgan Hill top of the region. **Bill, 2026-10-22: the UK rule,
  disclosed** (`context.inputsWithheld` and `coverage.notices` carry each reason).

## Unverified (not counted)

None reported.

## Carried from 16 October (`AUDIT_REPORT_2026-10-16.md`)

- The old EPC key in git history (`7eb1984`) is still not recorded as revoked anywhere in the tree.
- M-11 (16 Oct): the founder's Gmail in 10 places in docs and the skyscore.co.uk address in 12; Bill's call.
- M-8 (16 Oct): the project Python lacks the tarfile header fixes; the adsb archive scripts run under 3.13.15.
- I17: `/v1/signup` stores addresses unverified while `SignupVerify` is off (waits on DMARC and SES production).
- M-15 (16 Oct): not tested with a screen reader. I-4 residual (568x320 footer over five London centres): not
  re-measured. `/score-demo/api-docs.html` still has two `main` landmarks (9 Oct M-15).
- New, pre-existing: `/prototype/` at 1440 has no focusable control.

## Checked and clean

- **Backend:** no new routes, `template.yaml` unchanged, every route keeps its throttle; `sold_prices` validation
  unchanged and its new fields escaped where rendered; CORS, HSTS and nosniff kept; `verify_answer()` untouched.
- **Scales and pools:** `us_anchored_to_score` (None in, None out; anchor guard; clamp); `pool_of`/`poolOf`
  mirror each other; New York's v5.7 lobes, bands and sizes agree across the Lambda, `index.html` and
  `data/us-nyc.json`.
- **Readers:** Bay Area flood (zones, shares, the state cache keyed on inputs and loaded scripts), road (legend
  held to BTS's colours, a 404 empty only when its parent proves it), transit (no platform lost its station),
  records (joined by GEOID, withheld reasons held both ways).
- **Breathe London and AURN:** window and capture arithmetic, key redaction and no-redirect, 5 km, the 45-day
  stale rule; every credit linked, no "none nearby" wording; a stale sensor file hides the sensor line only.
- **Plane counts:** cone bounds strict, chunking on pass boundaries, packing ranges, the batched average divides
  after summing; the extractor's decompression cap holds.
- **Downloads and workflows:** FEMA `safe_extract`, https-only adsb fetches, `allow_pickle=False`; the three new
  workflows are dispatch-only, `contents: read`, SHA-pinned, no secrets, no `pull_request_target`.
- **Whole repo:** no AWS, GitHub, Google, Anthropic, Slack or JWT secrets and no private keys; no new email
  address beyond `you+mcp@example.com`; Cubitt33 only on privacy and terms; `npm audit` 0 vulnerabilities.
- **Front end:** no sideways scroll on any changed page at the four sizes (one pre-existing exception, M-15);
  axe clean on every page and new section (one pre-existing prototype flag); the coverage strip, developer band
  and street report pass contrast, focus and order checks; the sold-price wording and the wording rules hold.

## Summary

- Critical: 0
- Important: 6 (all fixed the same day, 3 of them on Bill's decision)
- Minor: 15 (12 fixed the same day; the last 3, M-5 user paths, M-7 the Staten Island note and M-9 the coverage strip's unsearchable names, fixed 2026-10-23)
