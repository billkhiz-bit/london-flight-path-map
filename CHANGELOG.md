# Changelog

Sky Score release history. API contract is stable (`/v1/*`); breaking changes deploy under `/v2/*`. Methodology versions are tracked separately in [`METHODOLOGY.md`](./METHODOLOGY.md#20-changelog).

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Planned
- DEFRA Lden raster data load completion (in flight 2026-05-07; loader at NSPL row ~2.1M of ~2.5M)
- Independent measured-noise validation (gating contractual accuracy claims)
- Per-postcode flood risk component (`flood`)
- Per-postcode air quality component (`airQuality`)
- LSOA-level crime breakdown (`crimeBreakdown`)
- Per-customer API keys + Usage Plans (replaces shared free-tier key)
- Optional `/api` landing page (B2B discovery surface, defer until outreach signals warrant)
- Public methodology change-history page
- ISO 27001 / SOC 2 attestation tracks
- MSA + DPA template (use CommonPaper.com or PandaDoc UK template; do not draft from scratch)
- First commercial contract with a paying integrator
- Pricing tier structure firmed up post first prospect conversation
- Live aircraft feature re-introduction once OpenSky licensing reply lands (Ticket #835285) or an alternative provider (AviationStack / FlightAware) is selected

## [Consumer rebrand + security hardening] 2026-05-07

Single big day: removed all AI features from the consumer site, removed the OpenSky-backed live-aircraft feature pending licensing, hardened the signup endpoint, fixed several DOM-XSS surfaces, trimmed flight-path polylines to noise-relevant portions, refreshed every relevant doc. Net: 32 commits, 3 backend deploys, 5 frontend deploys.

### Added
- **XSS hardening sweep** across the consumer site (commit `2405122`). New `safeUrl()` allow-list for href values from community data; `formatChatReply` (since removed) escapes before markdown to break the OSM → chat injection chain; every API-derived `innerHTML` interpolation in NHS / TfL / sold-prices / autocomplete / borough-postcode renderers wrapped in `escapeHtml`. Closes audit N-Sec-1, N-Sec-2, N-Sec-3.
- **Self-service signup hardening** (commit `a214ba0`). Tag-based IAM scope-down on `apigateway:DELETE` so the signup Lambda can only delete keys it created (closes N-Code-1); per-route APIGW throttle of 1 RPS / 5 burst on `/v1/signup` (closes N-Code-2); CORS lockdown from `*` to a `skyscore.co.uk` allow-list (closes N-Sec-4 partial); orphan-key revoke failures now logged at ERROR level with a `[SIGNUP_ORPHAN_KEY]` prefix for CloudWatch alarming (closes N-Code-7).
- **Tab a11y** (commit `847935c`). Tabs converted from `<div role="tab">` to native `<button>` with Left/Right/Home/End arrow-key navigation and roving tabindex per WAI-ARIA tabs pattern.
- **Prototype mobile touch-target sizing** (commit `2e77bda`). Mobile touch-bar buttons now `min-height: 44px` per WCAG 2.5.8 (was ~22-30 px on smallest breakpoint).
- **SEO + meta tags** on `score-demo/{index,api-docs,status}.html` and `prototype/index.html` (commit `bc4d426`). Canonical, theme-color, OG / Twitter cards, robots. Status page is `noindex`.
- **`live_flights` tuple-return refactor + 9 unit tests** (commit `5418d73`, *later removed*). Replaced function-attribute state pattern with explicit `(payload, error)` tuple; race-safe under concurrent Lambda invocations.
- **Per-secret `AllowedPattern '^.+$'`** in `template.yaml` (commit `aaf192f`). Deploys with empty / missing tokens now fail CloudFormation parameter validation instead of silently propagating empty strings to the Lambda env.
- **DEFRA WCS downloader** (`scripts/download_defra_wcs.py`, commit `7c3ce04`) bypasses the data.gov.uk UI 250 km² area threshold and pulls the full London bbox raster directly from the WCS endpoint.
- **DEFRA loader v2** with below-threshold sentinel (commit `2fc2c0b`). Postcodes inside the bbox but outside the published 40 dB Lden contour now write a 35 dB sentinel rather than falling through to Haversine — fixes suburban Twickenham / Wimbledon / Hampstead being mis-scored as loud. Plus checkpoint-on-every-1000-rows fix for resumability.
- **Flight-paths audit script** (`scripts/audit_flight_paths.py`, commit `d9f33b9`). Samples each `FLIGHT_PATHS` polyline at 50 evenly-spaced points and looks up Lden in the DEFRA GeoTIFF; flags paths that don't track real noise. Output: `FLIGHT_PATHS_AUDIT.md`.
- **Per-route Bedrock throttle** plan documented (made moot by AI removal — see below).

### Changed
- **AI-powered → data-first repositioning** (commit `455af60`). README, ROADMAP, CLAUDE.md updated. The 5 Bedrock Lambdas (`chat`, `multi_agent`, `analyze_image`, `analyze_document`, `report`) reframed as "dormant in the template, kept for potential re-introduction as user-triggered constrained features".
- **`FLIGHT_PATHS` polylines trimmed** to noise-relevant final-approach / initial-departure portions only (commit `abbae36`). Previously extended 30-45 km out to holding fixes at FL120+ where DEFRA shows zero ground noise — visualisation now matches what's actually audible. Per-path mean Lden up across the board (Lambourne 38→43, Biggin 39→45, Dep SE 43→52). Score Lambda's Haversine fallback now also more accurate for outer-London postcodes.
- **DOM XSS chat-reply chain blocked** at the renderer layer — `formatChatReply` now escapes before applying markdown so a successful prompt-injection bypass can't render `<img onerror>` and steal the device token. (Function later removed entirely with the chat panel.)
- **Tab interaction** moves Tab in/out of the tablist in one keystroke instead of cycling through every tab (roving tabindex pattern).
- **Demo regression fixes** (commit `a2b5695`). `score-demo/index.html` persona dropdown caught up with the `192ce18` persona expansion (renter / commuter / downsizer); four `", "` placeholder strings on `score-demo/status.html` and `prototype/index.html` (left over from the dash-strip script) replaced with `Loading…` / `Checking…`.
- **Signup `print()` → `logger`** (commit `a214ba0`) — restores structured-log search across CloudWatch.
- **`live_flights` upstream errors surfaced to UI** (commit `12617e2`, *later moot*). Frontend showed "LIVE AIRCRAFT, DATA UNAVAILABLE" when the proxy returned `available: false`, instead of silently rendering nothing.

### Removed
- **All AI features from the consumer UI** (commit `69905ee`). Chat panel, AI insight auto-summary on postcode views, multi-agent routing, property-photo image analysis, EPC / survey document upload + AI analysis, "Generate AI Report" button. The 5 Bedrock Lambdas remain dormant in `template.yaml` (zero idle cost on on-demand pricing); restoring is "uncomment one frontend block + redeploy". Net `-25 KB` on served HTML, `-535 lines`. Reasoning: methodology defensibility is the B2B story, and AI summaries on top of deterministic scoring add variance B2B audit teams will challenge first; "not fully accurate" is structural not tunable.
- **`live_flights` Lambda + UI end-to-end** (commit `6f6ce7d`). OpenSky's terms require a written agreement for any operational use including consumer surfaces. Lambda code in git history (commit `a214ba0`); UI gated behind `liveLicensed=false` flag in the prototype. Restoration recipe in `LICENSING.md` "Removed sources" + `OPENSKY_LICENSING_EMAIL.md`. Email enquiry sent same day — OpenSky Ticket #835285, awaiting reply.
- **Borough metadata duplication** between chat / multi_agent / score Lambdas → reduced to score-only (the other two are dormant).
- **Pre-existing preflight noise** (commit `70405f8`): 1 ESLint error + 1 HTML-validate error → 0 errors. Aligned Prettier and html-validate void-element style; converted `<div class="site-footer">` to semantic `<footer>` so its `aria-label` is valid; ruff `--fix` cleaned 16 import-order + `datetime.UTC` modernisation issues across all backend Lambdas.

### Security
- **Closed**: N-Sec-1 (OSM DOM XSS), N-Sec-2 (chat-reply DOM XSS), N-Sec-3 (defence-in-depth XSS sweep), N-Sec-4 partial (signup CORS lockdown — full closure pending CAPTCHA), N-Code-1 (signup IAM `apigateway:DELETE` wildcard), N-Code-2 (no per-route throttle on `/v1/signup`), N-Code-5 (signup `print()` vs logger), N-Code-7 (orphan-key revoke alerting), N-Front-1 (persona drift on B2B demo), N-Front-2 (corrupted status placeholders), N-Front-5 (tab a11y), N-Front-6 (first-hint announcement), N-Front-9 (prototype touch targets), N-Front-10 (prototype ticker XSS).
- **Made moot by AI removal**: N-Sec-4 partial (per-route Bedrock throttle), N-Front-3, N-Front-4, N-Front-7, N-Front-8 (all chat/report-modal a11y items).
- **OpenSky licensing**: live aircraft removed from production pending OpenSky's reply (Ticket #835285). Email and FAQ research confirmed: no public commercial-use form exists; the documented commercial path is exactly the email we sent. Sky Score never created an OpenSky account — consciously kept hands clean before the licensing question is settled.

### Decisions
- **AI feature removal** → data-first positioning. Recovery path: re-introduce later as user-triggered constrained "explain in plain English" button (≤5% of the cost, lower hallucination risk) only when consumer feedback warrants it.
- **OpenSky → remove and ask** (option 3 of three considered: contact for licence, replace with paid alternative, or remove). Chase scheduled for 2026-06-04 (4 weeks).
- **Repo migration**: canonical clone now at `C:\Users\bilal\projects\london-flight-path-map`; legacy OneDrive clone retired pending DEFRA-loader completion. OneDrive `.git` corruption risk per global CLAUDE.md.
- **Echo-work discipline** added to global `~/.claude/CLAUDE.md`: after substantive change, propagate to README / ROADMAP / LICENSING / METHODOLOGY / AUDIT_REPORT / OUTREACH_LOG / memory / `.env.example` / tests / AWS surfaces in the same session while context is hot.

## [3.1], 2026-05-05

### Added
- **NYC ZIP centroids**, ~110 NYC ZIPs now have static centroid lat/lon, enabling the v3.0 per-postcode Haversine layer for NYC postcodes (previously borough-aggregate only). Within-borough variation now works for NYC (e.g. 11201 DUMBO returns quiet=8.0; 11375 Forest Hills returns quiet=2.0 under JFK / LGA traffic).
- **DEFRA raster scaffold**, DynamoDB table `london-flight-map-noise-raster` deployed with IAM read access from the score Lambda. Resolution chain extended: `raster → postcode (Haversine) → borough`. New `context.quietResolution` enum value `'raster'`. Lambda is forward-compatible: empty table falls back transparently to v3.0 Haversine; populating the table silently upgrades to gold-standard precision.
- **`scripts/load_defra_raster.py`**, runbook + code template for the one-shot batch that downloads the DEFRA GeoTIFF, samples at every UK postcode centroid, and writes to DynamoDB.
- **`?include=` query parameter** on `/v1/score`, selective response shape for integrators who only want specific fields.
- **`plannedComponents` field** on `/v1/score` responses, visible roadmap of components on the development plan (`flood`, `airQuality`, `epcDistribution`, `crimeBreakdown`).
- **Public status page** at `/score-demo/status.html`, live endpoint health checks, methodology version, region, SLA reference.
- **Public `CHANGELOG.md`** at repo root (this file).

## [3.0], 2026-05-05

### Added
- **Per-postcode Haversine quiet scoring**, when the API receives a UK postcode (resolved to lat/lon via postcodes.io), the Quiet score is computed at postcode resolution using Haversine distance to airports and flight-path geometry. Same algorithm as the consumer-site neighbourhood scoring (`index.html:1118-1247`); ported to the Lambda.
- 5 London airports tracked (LHR, LGW, LCY, STN, LTN), 4 NYC airports (JFK, LGA, EWR, TEB).
- 12 London flight-path corridors (Lambourne / Biggin / Ockham / Bovingdon stacks; LHR departures; LCY / LGW / LTN approaches), 8 NYC corridors.
- New `context.quietResolution` field (`'postcode' | 'borough'`) reports which tier produced the response.

### Changed
- Hackney N1 7SX `quiet` updates from 10.0 (borough-aggregate "low") to 4.0 (under Lambourne Stack, the LHR east-London arrival corridor).
- Wandsworth SW11 1AA `quiet` updates from 5.0 (borough-aggregate "moderate") to 7.0 (south of major LHR corridors).
- Hounslow TW3 4DX `quiet` updates from 0.0 to 2.0 (still severe, postcode under approach corridor).

### Removed
- Borough Lden band as the default quiet source (still available as fallback when postcode lat/lon unavailable). The borough Lden remains visible in `context.noiseImpactBand` for transparency.

## [2.1], 2026-05-05

### Added
- New benchmark anchors in methodology: HM Land Registry House Price Index (Affordability + Growth), EU Environmental Noise Directive 2002/49/EC (the regulatory framework DEFRA implements for Quiet), Care Quality Commission (roadmap anchor for Healthcare in v3.0+), English Indices of Deprivation (alignment reference for Liveability).

### Changed
- Audit-protection edits across §4.4 (Schools, Crime, Healthcare), §5.2 (Personas), §11 (Editorial), §14 (Comparison): softened Ofsted distribution percentages, clarified crime-rate denominator, removed specific Climate X funding figure, softened Rightmove citation, replaced generic reference URLs with stable government collection pages.

## [2.0], 2026-05-05

### Added
- **OGL attribution** in every data-source response (epc, sold_prices, transport, nhs).
- **`/v1/score/batch`** endpoint, bulk scoring up to 100 queries per call; per-row failure tolerance.
- **`/v1/regions`** endpoint, discovery for supported cities, boroughs, postcode formats.
- **OpenAPI 3.0 spec** at `/score-demo/openapi.yaml`.
- **Interactive Swagger UI** at `/score-demo/api-docs.html`.
- **`sourceBreakdown` field** in score responses, per-component data lineage.
- **Methodology v2.0**, every numeric threshold and weight anchored to a published source or explicitly-acknowledged editorial decision.
- **NYC borough lookup** (`?city=nyc&borough=Manhattan`).
- **NYC ZIP detection** (~182 ZIPs static-mapped; auto-detect in `?postcode=`).
- **postcodes.io in-memory LRU cache** for repeat lookups within a Lambda container.
- **Per-resource CORS** open to `*` for the score endpoints.

## [1.0], 2026-05-05

### Added
- Initial **`/v1/score`** B2B API endpoint.
- **API key auth** via API Gateway Usage Plan (1,000 req/month free tier, 5/sec burst, 2/sec sustained).
- **B2B browser demo** at `/score-demo/index.html`.
- **Public methodology document** (`METHODOLOGY.md` v1.0).

## [0.9], 2026-04-XX

### Added (consumer site, pre-API)
- Sky Score consumer site (London + NYC) at `https://skyscore.co.uk/`.
- Sky Score Radar 3D prototype at `/prototype/`.
- Amazon Nova hackathon submission.
