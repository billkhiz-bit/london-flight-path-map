# Audit Report — Sky Score

**Date:** 2026-10-31
**Commit audited:** `6bee6bb` (the 48 commits since the 22 October audit, `8d89c0d..6bee6bb`), plus the uncommitted
front-page trim in the working tree at the time (the front page's booking links cut to one), plus a whole-repo pass
for secrets and personal data.
**Files scanned:** the 177 changed source files (Python, JavaScript modules, HTML, YAML, shell, Makefile; data, area
pages, docs and fixtures excluded) by reading and grep; all 824 tracked files for secrets and personal data; 15
published pages by a static accessibility scan; 4 published pages and the London area pages that no gate validates,
by html-validate.
**Method:** one read-only reviewer, working beside another session that was committing and deploying in the same
tree. So no browser, no local server and no preflight were run by this audit (a port collision turns the other
session's preflight red). The front end's browser checks therefore stand on the last preflight (preflight-8, 30 Oct
23:51, `RESULT: PASS`, on this same tree): axe, the WCAG source scan, the responsive gates and the approach strip at
both widths. Run here: 2,170 Python tests (backend/tests and tests/, all passed), `tests/planes-model.mjs` (9 of 9),
`npm audit` (root and mobile), and read-only AWS calls (usage plans, the live site's headers). Every finding below
was re-checked in session against the code, the data or the live service; nothing was fixed or deployed by the audit.

## Critical Issues

None.

## Important Issues

None.

## Minor Issues

| # | Issue | File:Line | Category | Status |
|---|-------|-----------|----------|--------|
| M-1 | **The FAA freshness row reads the OLDEST cycle the FAA page lists** (`stamps[0]`). Near a changeover the page lists the outgoing and the incoming cycle, so on the day the new one takes effect a site still serving the old one reads `current`: the row cannot go red on the one day it matters. Its hint also says the cycle "feeds no published route yet", but `/data/us-flight-procedures.json` is drawn by the map (`index.html:8491`) and the front page (`js/home-engine.mjs:191`, `:198`), so a missed cycle is visible. | `scripts/check_data_freshness.py:227`, `:229` | Code / gates | **Fixed 31 Oct.** The row takes the newest listed cycle whose date has arrived (falling back to the earliest when only future cycles are listed), says a published next cycle in its note, and its hint reads "drawn on the map and the front page". `tests/test_data_freshness.py::test_faa_reads_the_cycle_in_effect_today_not_the_oldest_listed` was proven red first: on a two-cycle page dated 26 Nov the old code read `('2026-10-29', 'current')`. |
| M-2 | **The public demo key used 3,467 of its 5,000 monthly calls in October** (API Gateway `get-usage`, plan `SkyScoreDemoTier`: ~112 a day, 268 on 23 Oct, 1,545 left on 31 Oct). The per-key log names the key, not the page, so the source cannot be split between the live demo's buttons, the status page's first (keyed) sweep and the preflight's three calls. `score-demo/status.html` is in the sitemap, so a crawler that renders it spends three keyed calls each time (a possible share, not measured). A month at 1.5 times October's rate (the marketing push) would answer 429 on `/score-demo/` and the status page before the month ends. | `backend/template.yaml:854`, `sitemap.xml:18` | Operations | **Cause found and fixed 31 Oct: it was our own preflight.** The score Lambda's `[API_REQUEST]` log split the key's 1,724 calls in the 14 days to 31 Oct into 1,600 `/v1/regions` and 124 `/v1/score`; the regions calls came in bursts of 8 and 5 at each preflight's browser stages (23:30/23:50 on 30 Oct, 15:20/15:40 on 31 Oct), never overnight. `tests/stub-live-api.mjs` let `/v1/regions` through as "unauthenticated", but `status.html` sends the key on it and API Gateway counts any keyed request. The stub now sends every non-score API request on WITHOUT the key. Real use is ~9 lookups a day, far inside 5,000 a month: no quota change needed. |
| M-3 | **Privacy s2a promises a booking is deleted 12 months after the call, with no step that does it.** No runbook, OPERATIONS entry or reminder in the repo schedules the deletion, and the promise names "Calendly and our calendar" while Calendly's notification emails put the same name, address and answer in the founder's mailbox too. | `privacy.html:305` | Privacy / process | Open, Bill's (with legal batch 2): a dated reminder per booking, and either delete the notifications too or name the mailbox in s2a. |
| M-4 | **Privacy s2a limits what a key holder's address is used for**: "to issue your key, enforce the one-key-per-email limit, contact you about your key if we ever need to (for example abuse or deprecation notices), and revoke the key". A check-in ("is the key working for you?") sits at the edge of "about your key"; anything about other products or a sale sits past it. | `privacy.html:292` | Privacy / wording | Open, Bill's: before any follow-up email to a key holder, keep it to the key, or add the purpose to s2a (with its date on /changes) first. |
| M-5 | **`npm audit` is no longer clean** (0 on 22 Oct; advisories published since): 7 moderate in the root's dev tooling (minimatch, GHSA-g3hv-75wg-m249, via eslint 9 and html-validate 10's glob 13; glob, GHSA-3g3m-2fjr-6pw4) and 5 moderate in `mobile/` (via `@capacitor/cli` -> rimraf -> glob). Nothing shipped uses any of them. | `package.json:36`, `:40` | Dependencies | Open. html-validate 11.17 clears the glob path (a major: re-run lint:html); eslint 9's minimatch 3.x waits on eslint; mobile waits on Capacitor's CLI. |
| M-6 | **html-validate covers 17 pages, not every page we publish**: `talks/index.html`, `talks/how-sky-score-works.html`, `open-data/index.html`, `bay-area/index.html` and the area pages are uploaded by their deploy targets but validated by no gate. All of them validate clean today (run in this audit, London's area pages included), so this is a gap, not a defect. | `package.json:10` | Gates | **Fixed 31 Oct.** `lint:html` names the four pages and the `area` folder (proven red on a page planted under `area/`, then removed); preflight's label reads "(21 pages + area/)". The 465 planes district pages (merged 31 Oct, generated and gitignored) get their own stage, "html-validate (planes pages)", INCONCLUSIVE on a clone that has not built them; all validate clean. |

## Closed since 22 October (`AUDIT_REPORT_2026-10-22.md`)

All 21 of its items are closed: the six Important and twelve of the Minor items on 22 Oct, the last three on 23 Oct.

| 22 Oct item | Closed by |
|---|---|
| I-1 rename candidate in the roadmap | `d24a012` (re-checked: `git grep` finds no candidate name; it remains in history, so buying the domains is still the lasting fix) |
| I-2 Bay Area transport bands, I-3 crime anchor, I-4 growth held out | `f6c4a35` |
| I-5 sold rows, I-6 "Have your say" by route, M-8 `bayarea_blocks --check` both ways, M-10 to M-15 (front end) | `c7f4b97` |
| M-1, M-2, M-3 (MCP server) | `2b7afef` |
| M-4 oversized archive members, M-6 fixture names | `efa77b0` |
| M-5 Windows user paths | `e69b90a` (`tests/test_no_user_paths.py` passes on today's tree) |
| M-7 Staten Island note | `a8a5d45` |
| M-9 regions the map does not draw | `e993d6a` |

## Carried (open, not new)

- The old EPC key in git history (`7eb1984`) is still not recorded as revoked anywhere in the tree.
- 16 Oct M-11: the founder's Gmail address in 10 places in 6 files (unchanged), the skyscore.co.uk address in 13 in 5;
  Bill's call.
- 16 Oct M-8: the project Python lacks the tarfile header fixes; the adsb archive scripts still run under 3.13.15.
- I17: `/v1/signup` stores addresses unverified while `SignupVerify` is off (`backend/template.yaml:1256`); it waits on
  DMARC (still absent) and SES production access.
- Privacy s2c (`privacy.html:335`) says GoatCounter stores "page views, referrers, screen sizes". This window added
  four more kinds of named click events (`nav-*`, `email-*`, `about-film`/`about-prototype`, `book-demo-*`) to those
  already counted. Already in legal batch 2 ("s2c wording for counted actions").
- 16 Oct M-15: not tested with a screen reader. 16 Oct I-4 residual (568x320 footer): not re-measured.
  `/score-demo/api-docs.html`'s two `main` landmarks (9 Oct M-15): the source has one (`score-demo/api-docs.html:202`),
  so the second is Swagger's at render; not re-measured (no browser this run). `/prototype/` at 1440 with no focusable
  control: not re-measured.

## Checked and clean

- **Secrets, whole repo (824 tracked files):** no AWS, GitHub, Slack, Anthropic, Google or payment-provider secrets
  and no private keys. The only live credential is the public demo key, by design, in its three declared holders
  (`score-demo/index.html`, `score-demo/status.html`, `tests/demo-key-scope.mjs`); the rest are labelled test fixtures.
- **Personal data:** no new email address in the tree; the About page names the founder and organisations only; its
  ten pictures carry no EXIF or GPS block; the uncommitted `OUTREACH_TARGETS.md` additions name organisations only.
- **Backend:** `backend/template.yaml` is unchanged since 22 Oct (no new route, every throttle kept). The score
  Lambda's new 404s (Bay Area ZIP with no majority city, ZIP asked of the wrong US city, not covered) echo only the
  caller's own postcode or ZIP, in JSON under nosniff. Provenance is built from the full body and then cut to the
  fields sent (`with_provenance`, `backend/lambdas/score/app.py:10771`), on `/v1/environment` as well. The log
  privacy scan passes; the signup Lambda logs key IDs and error codes, not addresses.
- **Analytics (`js/count.mjs`):** every counter added this window (top bar, email buttons, About links, Book a
  demo) sends a name from an allow-list or a fixed pattern, never the link, a subject, a query or a postcode; the
  bar's slug refuses another host (`OWN_HOSTS`). The live site sends `Referrer-Policy:
  strict-origin-when-cross-origin`, `X-Frame-Options: DENY`, HSTS and nosniff (checked on `/about/`), which is what
  privacy s2a's "told that you came from skyscore.co.uk, but not which page" relies on.
- **Book a demo:** seven copies of the link in five files, all equal to `DEMO_BOOKING_URL`; plain links, no Calendly
  script or frame and no CSP change; `booking-link-check` guards web, demo, home and web-deploy-all, and refuses an
  unreadable file.
- **Pages:** `/about/` and `/how-it-works/` carry CSPs with `script-src 'self'`. Static scan of 15 published pages:
  no image without `alt`, no `target="_blank"` without `noopener`, no iframe, no duplicate id, one `h1` each, no
  skipped heading level, every button typed. The phone menu is a native popover with typed buttons and the
  `#d35a12` focus ring.
- **Planes overhead (`js/planes.mjs`):** written with `textContent` only; a kind of day with no figure reads "not
  measured", never 0; a range needs a gap of 10 a day, so it never reads "up to under 1".
- **New download scripts:** `fetch_metar.py` (fixed https host, timeout), `lidar_building_heights.py` (zip magic
  bytes checked, members written by base name only, so no path escapes), `build_ground_grid.py` (`np.load` without
  pickle).
- **Makefile:** `planes-deploy` runs `build_planes_overhead.py --check` before its `sync --delete`, which is limited
  to its own prefix; the about and approach-strip pictures ship before the pages that name them.
- **CI:** the one change pins `pypdf==6.7.0` for the wording gate.

## Summary

- Critical: 0
- Important: 0
- Minor: 6 (M-1, M-2 and M-6 fixed 31 Oct; open: M-3 and M-4 Bill's, with legal batch 2; M-5 waits on upstream
  except html-validate)
- Closed from 22 October: all 21
