# Audit Report — Sky Score

**Date:** 2026-11-09
**Commit audited:** `e0e7b358` (the 75 commits since the 31 October audit, `6bee6bb7..e0e7b358`), plus the uncommitted
working tree of that night (the full map's suggestions race fix, the DEFRA legend check's retry, docs), plus a
whole-repo pass over all 927 tracked files for secrets and personal data, plus a data-accuracy spot-check of the live
API against the publishers' own files (Bill's ask: "double check data and data accuracy as well").
**Files scanned:** the 141 changed source files (Python, JavaScript modules, HTML, YAML, shell, Makefile, GitHub
workflows; data, area pages, docs and fixtures excluded) by reading, grep and pure `node -e` / `python -c` calls; all
927 tracked files for secrets and personal data.
**Method:** three read-only reviewers in parallel (code correctness; security and privacy; front end and WCAG 2.2 AA),
while a full preflight ran in the same tree, so no browser, local server or preflight was started by the audit. Every
finding below was re-checked in session against the code, and the Important ones against the live service. Contrast
ratios are computed from the CSS colours with the WCAG formula. Nothing was fixed or deployed by the audit itself.

## Critical Issues

None.

## Important Issues

| # | Issue | File:Line | Category |
|---|-------|-----------|----------|
| I-1 | **"All the detail" reads a measured "none within 1.5 km" from `/nhs` as "not asked".** `placesByKind()` drops any kind whose rows carry `link`, but the route's `none_nearby()` row is `{link: true, noneNearby: true, fallback: false}` with `available: true`, a READING. So TW9 3PZ (the front page's own example; checked live 9 Nov) loses its Hospitals line, and where doctors and pharmacies are both "none" (e.g. Biggin Hill, TN16) the card falls back to "Healthcare data is unavailable just now", which is false. The test missed it because its fixture sends `hospitals: []`, a shape the route never sends. Fix: drop only `fallback === true` rows; a `noneNearby` row is an empty list. | `js/detail-near.mjs:61`; `index.html` ~14227; `backend/lambdas/nhs/app.py:300-318` | Correctness |
| I-2 | **Air figures are rounded twice, so 4.9% of DEFRA's cells show NO2 or PM2.5 0.1 ug/m3 off.** The loader stores `no2Ugm3`/`pm25Ugm3` at 2 dp (`f'{val:.2f}'`); `/v1/environment` publishes `round(no2, 1)`. DEFRA's 3.654 shows 3.6 (AB42 4UL), 6.445 shows 6.5 (BN9 9NU); over the whole PCM 2024 grid 12,600 NO2 and 12,465 PM2.5 cells (4.9%) differ from rounding DEFRA's value once. It reached an outreach sheet (W14 9PJ PM2.5 printed 9.2; DEFRA 9.1499). No gate could see it: they compare our holders with each other. Fix (Bill's OK, 9 Nov): store 4 dp and reload the air attributes (the loader uses `update_item` on the air fields only). | `scripts/load_defra_air_quality.py` (`_put`); `backend/lambdas/score/app.py:9305,9310` | Data accuracy |
| I-3 | **The answer card's pills say "concern" or "good" by colour alone** (WCAG 1.4.1). Each pill's text is only the topic ("Crime", "Road noise"); `.ac-pill.watch::before` is orange, the default dot green (`#26f27d` vs `#f27d26`, 1.82:1 apart in lightness), and forced-colours mode removes both. A screen-reader user hears "Crime, button" for Westminster (high) and for Richmond (low). Fix: put the meaning in words, e.g. a visually hidden "Worth a look:" / "Good:" prefix, or two labelled groups. | `index.html:2441-2450, 14305` | Accessibility |
| I-4 | **Late answers rebuild the pills and redraw tiles under the user** (WCAG 2.4.3). Every `placeFinding()` rewrites its slot with `innerHTML` and `tidyCard()` rebuilds every pill with `replaceChildren`, even when the pills have not changed; in London, Transport and Healthcare are drawn from the council's rating and drawn again when TfL and the NHS answer. A keyboard user on a pill, or with the Transport tile open, in the first seconds after a search loses focus to `<body>` and the tile shuts. Fix: rebuild the pills only when their list changes and restore focus by key; keep `open` and focus when a slot is redrawn. | `index.html:14247, 14303`; `14526-14527`, `14901`, `14907` | Accessibility |

## Minor Issues

| # | Issue | File:Line | Category |
|---|-------|-----------|----------|
| M-1 | `fillDetail()` resets its shared answers by request-object identity; a profile change re-render makes a new `{token}` object, so an original answer landing after the re-render's can wipe the Stations lane from the picture. Low likelihood. Compare `req.token`. | `index.html` ~14187, ~16113 | Correctness |
| M-2 | Front page: if `load()` rejects (e.g. `borough-extra.json` fails), `booted` never becomes true, so a later Check is held forever as "Looking it up...". Before `5ea355a2` it said "Could not reach the data". | `js/home-engine.mjs:1249-1258, 2242` | Correctness |
| M-3 | `/api/`: an invalid press returns before aborting the request on its way, so the earlier answer lands over "That is not a UK postcode" and clears `aria-invalid`. | `js/api-demo.mjs:147-151` | Correctness |
| M-4 | Front page "Nearby": a nearest airport whose routes are not drawn (Gatwick, Stansted, Luton) is labelled "Flight paths", because `routeFacts()` only knows "Nearest airport on the map:" and `routesText()` writes "Nearest airport:" for `not-drawn`. E.g. CR5 (Gatwick 18.7 km): two "Flight paths" rows, no Airport row. | `js/home-engine.mjs:1222, 1666` | Correctness |
| M-5 | Dead code: `findingHtml()`/`gaugeHtml()` and the findings' non-tile fields are used only by `tests/panel-findings.mjs`, whose planes caveat check reads the dead copy, never `tile.notes`, the words users see. | `js/panel-findings.mjs:378-398`; `tests/panel-findings.mjs:121-127` | Correctness |
| M-6 | The full map sends any 2-8 letter text to postcodes.io while typing (`POSTCODE_SHAPE = /^[A-Z0-9]{1,8}$/`: "Hounslow", "Flat 3"); the front page and `/api/` send only the start of a postcode (`askable`). Disclosed by privacy s2b, so not a notice breach, but more than needed; CLAUDE.md says the front page works "as the full map's does", which is not so. | `index.html:11067, 12572-12576`; `CLAUDE.md:343` | Privacy |
| M-7 | Every front-page and `/api/` view fetches the held example from `/v1/environment`, whose one shared bucket is 5 a second (burst 10): a cheap flood of 400s empties it and the example silently disappears for everyone. The comment says arriving "asks our own API and postcodes.io nothing"; it asks our API. Option: ship the example's answer as a static file. | `js/home-engine.mjs:1640-1643`; `js/api-demo.mjs:207`; `backend/template.yaml:164-166` | Security |
| M-8 | `/api/` keeps `script-src 'unsafe-inline'` for one 20-line inline click tracker, on a page that now renders typed input and API answers (no sink found: all writes are `textContent`). Move the tracker into a module. | `api/index.html:9, 477-496` | Security |
| M-9 | `npm audit` (root): 3 moderate, down from 7 on 31 Oct, all through html-validate 10 (glob GHSA-3g3m-2fjr-6pw4, minimatch GHSA-g3hv-75wg-m249); html-validate 11.21.0 clears them (a major: re-run `lint:html`). Dev tooling only. Supersedes 31 Oct M-5. | `package.json` | Dependencies |
| M-10 | The postcode box's hint ("Keep typing the full postcode...", "No place by that name yet...") is a `<p>` inside the `role="listbox"` and is never spoken; `aria-expanded` is true with no options (WCAG 4.1.3, 4.1.2). | `js/place-box.mjs:76-80, 103, 116, 119, 134` | Accessibility |
| M-11 | The walkthrough's typing caret blinks forever (`walk-caret 1.1s steps(1) infinite`); only the OS reduced-motion setting stops it (WCAG 2.2.2). Cap it at a few blinks. | `home/index.html:516-518` | Accessibility |
| M-12 | Changing the buyer profile on the card announces "Results loaded for SW5 9HP.", never the new score (WCAG 4.1.3). | `index.html` ~14281-14291, ~14573 | Accessibility |
| M-13 | At 320 px the five-step Schools strip needs ~266 px in a ~246 px tile and overruns by ~20 px (`white-space: nowrap` in `1fr` columns); gates test 390 and 1366 only. | `index.html:2765-2779`; `js/panel-findings.mjs:418, 421` | Responsive |
| M-14 | The yardstick bar (WHO guideline, typical borough) is `#c8c7c4` on `#e4e3e0`, 1.32:1 (area pages 1.40:1 light, 2.22:1 dark); the figures are printed, so not a strict 1.4.11 failure, but the comparison is the picture's point. | `index.html:2864` | Accessibility |
| M-15 | `/api/` speaks its arrival example ("Asking about TW9 3PZ.", "Answered for TW9 3PZ.") into `role="status"` unprompted; the front page keeps its example silent. | `js/api-demo.mjs:171, 187, 207` | Accessibility |
| M-16 | The outreach sheet script ranks boroughs by `indexOf` after a sort, so ties fall by list order: the West Kensington sheet calls Hammersmith and Fulham "11th-highest" NO2 where it is level 10th with Newham (20.4). | `scripts/area_summary.mjs:127-130` | Data accuracy |

## Data accuracy spot-check (9 Nov, read-only)

Compared the live API with the publishers' own files, not with another copy of ours (scripts kept outside the repo).

| What | Result |
|---|---|
| PCM 2024 NO2 and PM2.5 grids in `data/` vs uk-air's downloads today | Byte-identical |
| Air, 60 random live UK postcodes (seeded), live API vs DEFRA's cell at ONS's grid reference | 57 compared, 3 answered for a co-located postcode (a lat/lon endpoint cannot tell them apart); 2 values off by 0.1 = I-2; Northern Ireland right once placed as the loader places it (Irish Grid to BNG) |
| Road noise, 8 random surveyed postcodes in each of the 12 city mosaics | 96 of 96 equal DEFRA's pixel (1 dp) on the live API |
| Earl's Court and West Kensington sheets (sent 1-2 Oct, corrected 18 Oct) | All 9 postcodes' road noise and NO2 equal the API; two PM2.5 print 9.2 (DEFRA 9.1499: I-2); the H&F rank (M-16) |
| Science Museum draft's planes figure (SW11 1AA) | 318 a day flying west, 2 flying east (Jan-Aug 2026), read through `js/planes.mjs` |

The preflight already holds ~50 data checks (builders against their sources, the site against the Lambda, area pages
against the live API, the worked example, freshness against the publishers); none compares a served postcode value
with the publisher's raw value, which is the class I-2 belongs to.

## Carried (open, not new)

- 31 Oct M-3 and M-4 (privacy promises on bookings and key-holder addresses): Bill's, with legal batch 2.
- The old EPC key in history (`7eb1984`) is still not recorded as revoked; the founder's Gmail address in 10 places in
  6 files; I17 unchanged (all from earlier audits).

## Closed since 31 October (`AUDIT_REPORT_2026-10-31.md`)

M-1, M-2 and M-6 fixed 31 Oct; M-5 superseded by M-9 above (fewer advisories).

## Checked and clean (summary)

Backend: no new route, every throttle present, `/epc`'s full-postcode guard, the new 503 echoes only the caller's
lat/lon, every 5xx text fixed (no postcode in `[5XX]` logs). Live headers: HSTS, nosniff, Referrer-Policy,
Permissions-Policy and `X-Frame-Options: DENY` on all nine page types checked, the 404 and the www 301 included; the
www redirect cannot be steered off-host or header-injected. GitHub Actions: pins match upstream tags, `contents: read`,
no `pull_request_target`, inputs only through `env`. XSS: every new module escapes all five characters or uses
`textContent`. Analytics events are fixed words. Secrets: none in 927 tracked files. Contrast of every new full-map
component's text (5.65-12.79:1) and the focus ring (>= 3.11:1) on every new background. Tab sets, the city menu,
profile chips, detail cards (focus survives `fillDetail`), text alternatives of every picture, reduced motion, tap
targets (>= 28 px). The uncommitted suggestions fix and DEFRA retry: no new hole.

## Summary

- Critical: 0
- Important: 4. I-1 FIXED (committed 10 Nov with the upkeep; `tests/detail-near.mjs` red on the old code). I-2: the
  loader now stores DEFRA's 6 decimals (`tests/test_air_loader_precision.py`); the live table changes only when the air
  attributes are reloaded (production writes: Bill's word). RELOADED 10 Nov (Bill's OK): all 2,704,817 NSPL rows,
  no failures; 285 random postcodes on the live API then equal DEFRA's own file to the decimal (570 values, the 8 NI
  ones placed as the loader places them), where ~28 would have been off before. I-2 CLOSED. I-3 and I-4 FIXED (10 Nov, Bill's go; I-3 as his pick A of
  claude.ai/artifact/9fizwcmmDp59FWUDtzuCQh: labelled groups, marks, names in words; both held in `tests/uk-city-panel.mjs`).
- M-16 FIXED (10 Nov): ranks say "joint 10th" (`scripts/rank_place.mjs`, `tests/test_rank_place_ties.py`).
- M-2 and M-4 FIXED (10 Nov; `tests/front-page.mjs`). M-3 is NOT A DEFECT: the 5 Nov build chose to let a good postcode on
  its way land after a bad press, and tests it (`tests/api-demo.mjs`: "a bad postcode leaves a good one on its way").
- M-1, M-5, M-6, M-8, M-10, M-11, M-12, M-13, M-15 FIXED (10 Nov, batch A; each new check red on the old code, M-5's by
  breaking the live renderer twice). M-15 keeps the example's words and stops only their being spoken. Left: M-7, M-9, M-14.
- Minor: 16
