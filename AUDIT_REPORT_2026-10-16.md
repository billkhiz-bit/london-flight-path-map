# Audit Report — Sky Score

**Date:** 2026-10-16
**Commit audited:** `a5c8f89` (the 31 commits since the 9 October audit, `1894dcd..a5c8f89`), plus a
whole-repo pass for secrets and personal data.
**Files scanned:** 73 changed source files (Python, JavaScript modules, HTML, YAML, shell) in full, every tracked
file for secrets, and the served pages driven in a browser at 1440x900, 390x844, 320x568 and 844x390.
**Method:** three read-only reviews run in parallel (code, security, front end and accessibility), each told to
verify every finding before reporting it. Every finding below was then re-checked in session against the code
before it was written here; anything that could not be reproduced is listed separately as unverified.

**Fixed the same day** means changed in the working tree after the audit, before the v5.6 release was deployed
(the New York items were loose ends of that release). Nothing here was deployed by the audit.

## Critical Issues

None.

## Important Issues

| # | Issue | File:Line | Category | Status |
|---|-------|-----------|----------|--------|
| I-1 | **The full map's New York legend described the pre-v5.6 method**: "Curated borough-aggregate aircraft-noise bands derived from JFK and LaGuardia approach geometry", while the bands are now derived from the FAA routes of four airports fitted to the Port Authority's monitors. It contradicted the API's own `sourceBreakdown.quiet`. | `index.html` (`legendNoiseExplainer`, New York) | Code / provenance | **Fixed the same day**: rewritten to the fitted method and the louder-rounded band. |
| I-2 | **New York's borough bands could publish quieter than their own estimate.** The band was the nearest of six values to the population-weighted estimate, so Brooklyn (estimate 4.11) published 5.0 and Staten Island (9.12) 10.0, against v5.6's rule that the estimate errs loud. | `scripts/build_nyc_impact.py` (`derive`) | Code / methodology | **Fixed the same day on Bill's decision**: the band is now the quietest one not above the estimate. Brooklyn moderate-high (3.0), Staten Island low-moderate (7.5); Queens, the Bronx and Manhattan unchanged. |
| I-3 | **"Avoid aircraft noise" in Find areas lists council areas the same page shows routes crossing.** London under £1m with aircraft noise ticked lists 13 areas at quiet skies 10.0, among them Bexley (London City's runway 27 final approach), Havering, Barking and Dagenham, Redbridge, Waltham Forest and Enfield (several London City departures each). The rule (the lowest council band, estimated) is explained only inside the collapsed "What the choices mean". | `js/home-engine.mjs` (`FIT_CONDITIONS.planes`) | Front end / wording | **Fixed the same evening (Bill: "go ahead with recommendations")**: "avoid aircraft noise" now needs the lowest band AND no route on the map crossing the area. The counts are the page's own `routesAcross()`, run for every drawn UK region by `scripts/build_area_route_crossings.mjs` into `data/area-route-crossings.json` (blocking `--check`); a region the map does not draw counts as unknown, never a pass. London's "aircraft noise" list went from 13 areas to 4 (Hackney, Haringey, Islington, Sutton). Proven red in `tests/front-page.mjs` with the rule removed. |
| I-4 | **On a landscape phone the full map hides the north of every city under the search card.** At 844x390 `elementFromPoint` at an area's centre lands on `div.search-box` for 12 of London's 33 boroughs, 4 of Greater Manchester's 10, 3 of Tyne and Wear's 5, the Bronx, and 32 of the Bay Area's 50. `tests/map-fit.mjs` passes because it measures the SVG box, not the band the chrome leaves uncovered. Pre-dates this window. | `index.html` (`mapCentreY`, `--map-band-top`), `tests/map-fit.mjs` | Front end / responsive | **Fixed for the phone layout**: the map now fits and centres in the band below the search card (and below the phone footer where the band is still deep enough), clipped to it. `tests/map-fit.mjs` now asks what lies at every area's centre at each phone size and measures fill against the visible band; proven red on the old layout (London 12, Bay Area 32, the Bronx, Leeds, Bradford, Doncaster, Sefton...). At 568x320 the footer's links still overlie 5 London centres, because the band below them is too shallow to use. |

| I-5 | **Found while fixing I-4: wide but short screens get the desktop layout, and its chrome piles onto the map.** At 915x412 (and an iPhone Pro Max on its side, 932x430) the layout switches to two columns above 900 px wide, so the city chips, legend, layer buttons and footer all sit over a 412 px-tall map: 23 of London's 33 area centres are covered, and the layer buttons overlap the chips. | `index.html` (the 900 px breakpoint, `applyTabbedLayout`) | Front end / responsive | Open. Recommended: use the phone layout below about 500 px of height as well as below 900 px of width (the front page already does: `STACKED` includes `max-height: 500px`), then add 915x412 to `tests/map-fit.mjs`. |

## Minor Issues

| # | Issue | File:Line | Category | Status |
|---|-------|-----------|----------|--------|
| M-1 | The UK outside-coverage reading looped over the Bay Area's geometry too (it excluded only `'nyc'` by name). No value was wrong (the Bay Area returns 10.0), but the docstring's reason for excluding New York applied. | `backend/lambdas/score/app.py` (`_quiet_across_all_geometry`) | Code | **Fixed**: UK cities chosen by country. |
| M-2 | Stale comments and docs still said New York was hand-drawn or unchanged: `app.py` (two places), `scripts/preflight.sh`, `scripts/build_us_flight_paths.py`, `CLAUDE.md`, and `measure_nyc_quiet_yardstick.py`, which would have printed the fitted engine under a "hand-drawn, Heathrow-sized" label. | as listed | Code / docs | **Fixed**. |
| M-3 | New York's borough notes named places the estimate contradicts: Queens called Forest Hills and Rego Park "relatively quieter" (2.0 and 3.0); the Bronx note named Hunts Point (2.4 km from the route, "Not under a final approach"), the Brooklyn note Flatbush (2.2 km); `score-demo` labelled Forest Hills "under JFK" (its nearest route is a LaGuardia departure). | `index.html` (`NYC_BOROUGH_DATA_RAW`), `score-demo/index.html` | Content | **Fixed**: each note now names only places within about a kilometre of a scored route (measured). |
| M-4 | `build_bayarea_prices.py`'s docstring said "ten" cities are top-coded; the file holds 16. | `scripts/build_bayarea_prices.py` | Docs | **Fixed**. |
| M-5 | New York's monitor positions are snapped onto OpenStreetMap street geometry (ODbL) and feed the scored fit, but LICENSING said they were "measured off its maps" and the data file did not carry the ODbL credit. | `scripts/snap_panynj_monitors.py`, `data/us-noise-monitors.json`, `LICENSING.md` | Licensing | **Fixed in the record** (credit in both, treated as an insubstantial extract). Whether each New York response should also credit OSM is Bill's call. |
| M-6 | One corrupt member in an adsb.lol archive aborted the whole day's extract (`BadGzipFile` is an `OSError`, a truncated member `EOFError`; only `ValueError` was caught), and decompression had no size cap (a gzip bomb would exhaust memory). | `scripts/adsb_extract.py` (`_work`) | Code / security | **Fixed**: both count as one bad trace; decompression capped at 64 MB per trace (proven on a 70 MB bomb). |
| M-7 | `adsb_fetch.py` downloaded from any URL the untrusted release JSON gave it, including `file://` and plain `http://`. | `scripts/adsb_fetch.py` | Security | **Fixed**: https from GitHub only. |
| M-8 | The local Python is 3.11.8, older than the tarfile header-parsing denial-of-service fixes (e.g. CVE-2024-6232, fixed in 3.11.10), and `adsb_extract.py` parses an untrusted tar stream. | the build machine | Security | **Done for the scripts at risk**: they now run under an unregistered, embeddable Python 3.13.15 (hash checked against python.org's API), documented in both scripts and CLAUDE.md; nothing else on the machine changes. The 3.11.8 to 3.11.9 patch waits until another project's Python jobs finish (3.11.9 is the last 3.11 with a Windows installer and still lacks the tarfile fix). |
| M-9 | The `/prototype/` page loads three.js from jsDelivr with no integrity check, while `SECURITY.md` said no third-party script runs on any page. A compromised CDN could read the favourites device token from the same origin. | `prototype/index.html:886-893`, `SECURITY.md` | Security | **Fixed**: every one of the 11 modules the page fetches carries a SHA-384 in the import map (a tampered hash was proven to block the module); `tests/test_prototype_integrity.py` holds the map to the page's imports. |
| M-10 | Rightmove's own Google Maps browser key sat in two saved-listing fixtures (a third party's public key, but it sets off secret scanners). | `tests/fixtures/rightmove-real-*.html` | Security hygiene | **Fixed**: replaced with a dummy of the same shape. |
| M-11 | The founder's personal email address is in six documents (and in commit metadata), and the AWS account ID in about ten, though `iam-policy.json` deliberately uses a placeholder. No phone number found anywhere. | `OUTREACH_DRAFTS.md`, `EMAIL_SETUP.md`, `OPERATIONS.md` and others | Privacy | **Account number removed** from all 17 places in tracked files (a placeholder, and the command that prints it). The Gmail address stays (Bill's call: it is in every commit's author field anyway). Neither is a credential; both remain in history. |
| M-12 | Find areas offers Cardiff, Nottingham and Greater Norwich, which the map cannot draw: the map stays on London unshaded with no note, and a reload of `/?city=norwich&borough=Norwich#find` reopens Norwich's card with Where reading "London". | `js/home-engine.mjs` | Front end | **Fixed**: the note says the map does not draw that region and the map link goes; a reload of `?city=norwich#find` starts the list on Norwich. Gated in `tests/front-page.mjs`. |
| M-13 | "Skip to the search" fails on the Find tab: its target `#pc` is in the hidden panel, so focus lands on `<body>` and the address changes from `#find` to `#pc`. | `home/index.html`, `js/home-engine.mjs` | Accessibility | **Fixed**: on the Find tab the link lands on its first control and keeps `#find`. Gated, proven red. |
| M-14 | With an area's card open, the selected tab's panel is `display:none` and the card sits outside any tab panel, which breaks the tabs pattern. | `home/index.html` | Accessibility | **Fixed**: the card moves into the selected tab's panel, which stays shown while its own content steps aside. Gated, proven red. |
| M-15 | Live-region chatter (the 9 Oct M-11, now wider): opening an area inserts ~820 characters into `aria-live` `#borough` and focuses its heading; `#fit-count` announces on every arrow-key step through the budget list. Not tested with a screen reader. | `home/index.html` | Accessibility | **Fixed**: a card that focus moves into is not also a live region, and the count is announced once the choices settle (800 ms). Gated, proven red. Still not tested with a screen reader. |
| M-16 | The full map's legend lines are dashed for every city while every route is drawn solid (since March); on the front page a dashed line means a departure. | `index.html` (`.legend-line`) | Front end | **Fixed**: solid. |
| M-17 | The "fits your choices" shading (`#ffd2a8`) is close to DEFRA's 55-60 dB colour and sits under the noise picture, so a fitting area near Heathrow is hard to tell apart. | `home/index.html` | Front end | **Fixed**: the matches are outlined (white halo, dark line) in a layer above the noise picture. Gated, proven red. |
| M-18 | `pricing.html` said batch requests "carry up to 100 addresses"; they carry postcodes. | `pricing.html:246` | Content | **Fixed**. |
| M-19 | The `_US_AIRPORT_CODES` exemption in `airport_noise_scale` (and the site's matching branch) is no longer reached by scoring, since all four New York airports have fitted sizes. | `backend/lambdas/score/app.py`, `index.html` | Code | Kept deliberately: it stops a future US airport without a fitted size from silently taking the UK default. |

## Unverified (not counted)

- `js/count.mjs` reads `document.title` when the module runs; on `/map/?postcode=` the map later writes the postcode
  into the title. Both the code and security reviews found the module always runs first and could not make it
  fail. Hardening option: send a fixed title per path.
- `gbpShort` would print "£1.0m" or "£1000k" exactly at its boundaries; no borough sits there today.

## Carried from 9 October (`AUDIT_REPORT_2026-10-09.md`)

| Item | Status 16 Oct |
|---|---|
| I-2 (badge "not covered" replaced by the 404 page) | Closed in source and deployed 11 Oct (`MAPPED = (403,)`). |
| M-2 (free copy's check verdict wording) | Open. |
| M-5 ("Nearest airport on the map: Gatwick", runways-only record) | Open. |
| M-8 (front page BTS palette not compared with `NOISE_SCALE_BTS`) | Open. |
| M-10 (watermark contrast; frame footer landmark) | Open (axe: 10 nodes at 1440, 16 at 320). |
| M-11 (card announced twice) | Open, widened: see M-15 above. |
| M-12 (no heading on the postcode answer) | Open. |
| M-13 (routes focus ring over its label) | Open (5 px overlap at 390, 320, 844). |
| M-14, M-17 (design: answer below the clip; page furniture) | As recorded, Bill's calls. |
| M-15 (two `main` landmarks on the API reference) | Open. |
| M-16 (`/reports/` sub-headings as `<div><b>`) | Open. |
| The old EPC key in git history (`7eb1984`) | Still not confirmed revoked. |

## Checked and clean

- The New York fit, end to end: the site's `runwayLobeKm`/`quietGeometry()` against the Lambda's
  `runway_lobe_km`/`calc_postcode_quiet` term by term; all 23 lobe bearings point the right way; the engine equals
  the fit's replica at 42 + 28 monitors; site and Lambda agree at 713 points and 127 neighbourhoods; nothing reads
  the deleted hand-drawn lists.
- `js/count.mjs` sends the canonical path, the allow-listed `utm_*` tags and nothing else; no `gc.zgo.at` on any
  served page. Every value that reaches `innerHTML` in Find areas, the cards and the street report is escaped.
- No new secret in this window's history; npm audit 0 vulnerabilities at the root and in `mobile/`; live headers
  (HSTS, nosniff, X-Frame-Options, Referrer-Policy) present; the uncovered badge is still a 404 SVG.
- Find areas: keyboard operation, focus rings (3 px `#d35a12`), focus return, contrast (5.04:1 or better), target
  sizes, and reflow at 320 px all pass. The street report reflows at 390 and 320 with no sideways scroll.

## Summary

- Critical: 0
- Important: 5 (I-1 to I-4 fixed the same day, I-3 and I-4 after Bill's "go ahead"; I-5, found while fixing I-4, open with a recommendation)
- Minor: 19 (18 fixed or settled the same day, M-19 kept deliberately; the Python patch in place waits on another project's jobs)
