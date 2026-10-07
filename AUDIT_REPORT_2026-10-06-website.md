# Website content audit, 2026-10-06

A read-only walk through the live site as four visitors (a homeowner, a firm, a council
officer, a developer), after a day that moved the front door, pricing, New York and the
report protection. Text and link checks only (no browser); the front page, the street
report and `/changes` were judged on their static HTML and their modules. Top findings were
re-checked against the live site before being recorded. Organisations only: this repo is
public.

**Clean:** all 138 internal URLs answer 200 (102 area pages, both sample PDFs, the CSV),
every external link and anchor resolves; prices agree everywhere they appear; no "+ VAT";
"Cubitt33" only on `/privacy` and `/terms`; no old project name; no em dashes in static
text; methodology v5.5 everywhere; 97 UK areas + 5 New York = 102, matching the CSV; titles,
descriptions and canonicals unique and correct.

Status: **open** unless marked. "Bill" = needs a decision or approval of wording. Everything
marked "fixed 6 Oct" was committed and deployed on 7 Oct (`e2396cc`) and verified from the
origin.

## Critical

| # | Finding | Fix | Status |
|---|---|---|---|
| C1 | "Open government data / OGL" claimed for everything (`/open-data/` "Built entirely from open government data"; the front page's og:description; the map footer's "OGL v3.0" for every city, New York and the Bay Area included; area-page source lists), and **the UK AIP (NATS) is credited on no web page**, though the flight routes and the quiet score derive from it and LICENSING.md says to credit it wherever routes are shown | "Official public data"; a "Flight routes: UK AIP (NATS)" credit on `/open-data/`, `/map/`, the front page and the area pages; the AIP and US sources added to `/terms` s6 and `/privacy` s5 (Bill: legal wording) | pages fixed 6 Oct ("official public data"; NATS credited on /open-data/, the map footer, UK area pages); **API `sources` fixed and DEPLOYED 7 Oct** (`fddc433`, reviewed changeset; verified live: TW9 3PZ's `sources` ends with the credit, area pages 102/102 against the live API, Sheffield's page carries none): `/v1/score` appends "Flight routes: UK Aeronautical Information Publication (NATS) ..." for every city whose quiet geometry reads an AIP airport (derived from `CITY_GEOMETRY` x `RUNWAY_AXIS_DEG`: the twelve UK cities with an airport; not South Yorkshire, not New York), and `sourceBreakdown.quiet` names the airports; the area pages now print the API's line instead of a hand-added one (which had also credited South Yorkshire's four pages). The legal pages are still pending (batch 2, Bill's approval) |

## Important

| # | Finding | Fix | Status |
|---|---|---|---|
| I1 | `/map/` is a dead end: no link to `/`, `/reports/`, `/pricing`, `/api/` or `/open-data/`; every "Full map" link and the installed app land there | Site links in the map's footer | fixed 6 Oct (map footer: Front page, Reports, Open data, For developers -> /api/) |
| I2 | `/api/` repeats the API prices and has already drifted (Enterprise "a support contract" there, "bulk scoring" on `/pricing`; the free tier's rates missing) | Replace the `/api/` table with a short summary and a link to `/pricing#platforms` | fixed 6 Oct (no prices on /api/; gated in front-page 16b) |
| I3 | "Professional - Launching" on `/pricing` and `/api/`: a developer cannot tell whether it can be bought | Bill: remove the badge, or "by arrangement" | fixed 6 Oct (Bill: tag removed) |
| I4 | Firms: "An area or site study from GBP 150"; councils: "Area study from GBP 750" - what looks like one product at two prices | Bill: explain the difference, or drop the GBP 150 line | fixed 6 Oct (Bill: a firm's "site study" vs a council's "area study") |
| I5 | `/bay-area/` is stale: "covers city regions across England, and New York, on the map" (the Bay Area is on the map now); "the map" links `/`; no site bar | Update the generator's wording and link (`/map/?city=bayarea`) | fixed 6 Oct |
| I6 | New York area pages: "Scored against borough prices across the whole country", while the same page says the pool is New York's five boroughs | Per-currency wording in the generator | fixed 6 Oct |
| I7 | 22 of 102 area pages promise "schools" in their subtitle and meta and show no schools figure (New York, the Cardiff region, Norwich, 7 Leicestershire districts, Broxtowe, Gedling, Rushcliffe); the Cardiff pages promise road noise; Cardiff credits DfE; one meta reads "Cardiff, Cardiff" | Generate the subtitle and meta from the rows a page has | fixed 6 Oct (topics() derives the subtitle and description) |
| I8 | "Full method: API reference" on all 102 area pages goes to the Swagger console, not the methodology; none links `/terms` | Point at METHODOLOGY.md; add Terms to the footer | fixed 6 Oct (methodology link; Terms in the footer) |
| I9 | Legal pages: `/terms` s9 and the `/privacy` summary each call the API-key email "the one exception" while `/privacy` s2a lists a score-update email list (the form is live); `/terms` (last updated 2026-08-05) says nothing of paid firm reports, the free-copy restriction or the CC BY-NC data licence; `/privacy` omits report requests emailed with clients' addresses; `/terms` cites the Property Misdescriptions Act 1991, **repealed in 2013** | Bill: approve a drafted update | Bill |
| I10 | Developers are never shown the Terms: neither `/api/` nor `/score-demo/` (where keys are issued) links `/terms`; `/score-demo/` meta says "any UK postcode" | Terms link beside "Issue key" and in both footers; "the city regions we cover" | fixed 6 Oct (terms beside "Issue key", in both footers) |
| I11 | `/open-data/` grants CC BY-NC, then says "redistributing it in bulk ... needs written permission", which the licence already allows non-commercially; the front page offers "one open file" without saying it is non-commercial | "for commercial purposes"; "free for non-commercial use" | fixed 6 Oct |
| I12 | `/reports/` samples a Norwich area summary while saying "Reports cover the city regions on the map"; Norwich is not on the map | Describe the real coverage (the map's cities and the API previews) | fixed 6 Oct |
| I13 | `/api/` "Built for" names nine real companies (aggregators and Islamic lenders): can read as a customer list or an endorsement | Bill: keep the categories, drop the names | fixed 6 Oct (Bill: categories, no names) |
| I14 | "livability" (US spelling) in `/map/`'s title, meta and tagline, and on `/score-demo/` | "liveability" | fixed 6 Oct (18 places on the map) |
| I15 | Mistyped URLs and `/privacy.html`, `/terms.html`, `/pricing.html` answer a raw `403 AccessDenied` XML page | A branded 404 page through CloudFront custom error responses, and redirects from the `.html` names (an AWS change: Bill to approve) | fixed and live 7 Oct (`86e9816`): `404.html` served with status 404 for origin 403/404 (`scripts/cloudfront_not_found.py`), the four old names 301 from the viewer-request function; `--verify` 16 of 16 from the origin. Bill ran the two AWS steps: the classifier refuses CloudFront publishes from Claude's session |
| I16 | (found 7 Oct, reviewing the I7 fix) The 11 API-only area pages (Cardiff, Nottingham, Norwich) show no air quality, road noise or flood row, though the Lambda holds them for every one (Cardiff: air quality only) and they feed each page's Environment score. `gather()` reads those rows from `data/borough-extra.json` alone, which skips `BACKEND_ONLY_CITIES` by design. I7's subtitle is now honest about the gap; the gap itself predates it | Fall back to the scoring record's `airQualityWhoRatio` / `roadNoiseAboveWhoPct` / `floodMediumOrHighPct` when the painted holder has no entry, then rebuild | fixed 7 Oct (Bill chose the measured figure over a band: "48.9% of addresses", "1.49 × the WHO 2021 guideline"; the subtitles follow by themselves; gated by `tests/test_area_page_env_rows.py`) |

## Minor

| # | Finding | Status |
|---|---|---|
| M1 | (partly fixed 6 Oct: Terms added to the area, open-data, Bay Area, /changes, /api/ and demo footers) Terms missing from the footers of `/open-data/`, the area pages, `/bay-area/` and `/changes`; no site bar on `/privacy`, `/terms`, `/changes`, `/talks/`, `/score-demo/api-docs.html`, `/score-demo/status.html` | open |
| M2 | "Back to the map" on `/area/` and `/talks/`, and "the map" on `/bay-area/`, point to `/` (the front page) | fixed 6 Oct |
| M3 | "council areas", "boroughs" and "areas" used for the same 97; 13 or 14 city regions; Leicester vs Leicestershire; the front page meta says "English" and the body "England and Wales"; New York missing from the front page's coverage figure | open |
| M4 | (fixed 6 Oct: "UK city regions", "any UK postcode", residents' groups get area summaries) Small over-promises: the front page's "any postcode in the cities we cover" (Bay Area places are not scored); the street report's "any postcode we cover" (US ZIPs are refused); "free for residents' groups" on the street report | open |
| M5 | Stale incident note on `/api/` ("updated 12 August 2026", "three separate reasons" then four headings, "is published in 2022") | fixed 6 Oct |
| M6 | "Checked before it leaves" names price and crime checks for reports that contain neither | fixed 6 Oct |
| M7 | Em dashes rendered by `/map/`'s JavaScript (eight cities' legend strings, the "led by price" note), `robots.txt`, the prototype's meta | fixed 6 Oct (map strings, robots.txt, prototype meta) |
| M8 | Unexplained jargon (RoFRS, NaPTAN, NHS ODS, "ladder", persona); no "10 = best" key | open |
| M9 | No og tags on `/reports/`, `/reports/street/`, `/open-data/`; no og:image on several pages; the sitemap omits `/terms` and `/changes` and includes `/prototype/`; `/bay-area/`'s title is 99 characters | fixed 6 Oct (og on /reports/, /reports/street/, /open-data/; sitemap gains /terms and /changes, drops /prototype/) |
| M10 | `/privacy`: claims US-hosted fonts (self-hosted since August); "New York view only" for the US tiles (the Bay Area uses them); mentions an unpublished Android app; the copyright line names an individual where the operator is the company (deliberate until the IP deed is signed) | Bill |
| M11 | The prototype, linked from `/score-demo/`, promises "live aircraft tracking" (removed in May) | fixed 6 Oct ("simulated flight tracks") |
| M12 | Every Method link goes to the GitHub repository under its old name | after the rename |
| M13 | Cardiff "not on the map yet" may never be kept (Wales has no Progress 8) | open |
| M14 | Developer trust: the raw AWS API address everywhere; `api.skyscore.co.uk` does not resolve (a Cloudflare CNAME, Bill); the status page routes support to GitHub issues; `robots.txt` contradicts its own comment | partly Bill |
| M15 | Firms are not told how to pay (councils are told "we invoice on order") | fixed 6 Oct ("paid by bank transfer before the report is sent") |

## Found after the audit

| # | Finding | Status |
|---|---|---|
| A1 | (7 Oct, preparing the LGM demo) The full map contradicts the front page and the street report for the same postcode. TW9 3PZ: front page and report say "Under the Heathrow 27R final approach, 0.1 km from the centreline, aircraft at about 1,800 ft" and 10.2 km to the nearest runway; the full map's "What you need to know about noise here" says "Planes pass at roughly 4,000-6,000 ft" and "Heathrow is 11.7km away". The map's prose looks like generic band text, and its distance is to the airport, not the runway. Fix: derive the map's sentence from the same AIP geometry `js/street_report.mjs` uses (one holder), or drop the height claim there | **fixed and DEPLOYED 7 Oct** (`4c2c5d2`): the full map loads `js/flight_geometry.mjs` and `data/flight-procedures.json` on search intent and gives a height only for a home under a final approach (`finalOverhead()`, now the ONE rule the front page imports too); live TW9 3PZ reads "About 1,800 ft (Heathrow 27R final approach)". Gated by `tests/uk-city-panel.mjs` (a physics bound, proven red on the ladder). **Follow-up the same evening:** a deep link (/map/?postcode=TW9 3PZ) still read N/A, because the result is analysed before the geometry is awaited and only a focused search box preloads it; both result paths now recompute the altitude after the await, and the gate drives a deep link in a fresh page (proven red on the first version). The distance basis (airport vs nearest runway) is a different measure, not a wrong one, and is left |

Also from the same day: the street report's route table header "Height there" becomes "Height" (Bill).

Found while fixing: `prototype/index.html` has seven `<button>`s without a `type` (html-validate `no-implicit-button-type`); pre-existing, and the prototype is outside the validator's page list. "Height there" became "Height" (Bill) on 6 Oct.
