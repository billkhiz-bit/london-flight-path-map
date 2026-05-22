# Sky Score Roadmap

> **Living document.** Updated as Sky Score evolves. For the focused buildathon plan see `BUILDATHON_PLAN.md`. For Claude session instructions see `CLAUDE.md`. This roadmap is the *what next* across all tracks.

**Last reviewed:** 2026-05-22 (**Mobile redesign shipped to web — Option A bottom-nav, search-first.** Reworked the mobile UI from a desktop-map-in-a-bottom-sheet into four full-screen views (Search / Map / Rankings / Saved) driven by a fixed bottom nav, with `viewport-fit=cover` + safe-area insets, and a fix for the PWA install prompt leaking into the native app — its root cause was the `[hidden]` attribute being silently overridden by explicit `display`. **Deployed live to CloudFront + verified across 360/390/414 phone widths (zero horizontal overflow); desktop layout untouched.** Committed in the canonical clone as `78aea08` (redesign) + `a0e518b` (store release notes + Windows `build:android` `gradlew.bat` fix) — **awaiting `git push` + iOS resubmission + Android rebuild** (these are user-only: push rule, Apple 2FA, keystore password in Bitwarden). Plan + reusable verification harness: `MOBILE_REDESIGN_PLAN.md`, `tests/native-sim-render.mjs`. Memory: `project_mobile_redesign_option_a.md`, `feedback_hidden_attr_display_footgun.md`, `feedback_build_android_windows_gradlew.md`. — Previous review 2026-05-21: **iOS v1.0 LIVE on the App Store as of 2026-05-20** — build 20 with the Wave 13.20 iPad Guideline 4.0 fix was approved, closing the 2026-05-12 → 2026-05-20 rejection arc. Public: apps.apple.com/gb/app/sky-score/id6768118116. Android AAB still stale relative to master — rebuild before Play upload. skyscore.co.uk email forwarding still to set up — `support@` declared in App Review notes + privacy policy. Previous review 2026-05-18 EOD (Wave 13.20 — build 19 rejected on iPad layout, fix shipped + build 20 resubmitted same day).

iOS side: Build 19 is the first successful build under the persisted-cert pipeline (orange radar icon, signed by persistent Distribution cert public-key SHA256 `c680ad18...805934`). Attached to v1.0.1 in ASC, submitted for review. The arc from 13.16 → 13.18.1 took three failed builds: 13.17 base64-in-env-var (corrupted in clip.exe→textarea transit), 13.18 raw PEM (dashboard Edit on a Secure var didn't persist the value due to a Codemagic UI quirk), 13.18.1 added length-diagnostic + delete-and-recreate. Eight distinct failure modes resolved.

Android side: keystore generated at `~/.keystores/sky-score-release.jks` (upload-key SHA-256 `A5:53:4A:8F...:22:50:AB`), `mobile/android/app/build.gradle` wired for env-var-driven signing (force-tracked because `/android/` is gitignored), gradle bundleRelease produced a signed 3.6 MB AAB at `mobile/android/app/build/outputs/bundle/release/app-release.aab`. Three Play Store screenshots auto-generated at 1080×1920 via Playwright + Chromium (`tests/android-screenshots.mjs` hides PWA install prompts to match the native app's runtime view), feature graphic 1024×500 auto-rendered (`tests/android-feature-graphic.mjs`). Fastlane metadata at `mobile/fastlane/metadata/android/en-GB/` pre-populated. AAB is ready for manual Play Console upload (Internal track → Production); Play review typically <24h. Forensic trail in `memory/feedback_codemagic_personal_account_signing.md` (iOS), `memory/project_android_keystore.md` (Android keystore facts), `HANDOFF_2026_05_14_icon_ship.md` (icon arc).)

---

## Vision

Sky Score is the noise + livability layer for UK property data, designed to be honest about hidden harms (aviation noise, road noise, air quality, crime) that listings sites have a financial incentive to hide. Two surfaces: a consumer site that informs renters/buyers, and a B2B API that puts the same data inside the workflows of conveyancers, property data aggregators, and Islamic-finance providers. Aligned with Maqasid al-Shariah (protecting buyers from harm) and explicitly riba-free in customer targeting.

## Current state

- **Consumer site live**: `https://skyscore.co.uk`, covers London + NYC, postcode/borough scoring, favourites, NHS/transport/EPC/sold-prices data lookups
- **Backend**: 8 active Lambdas + 5 dormant (the consumer-side Bedrock features built for the original hackathon) behind API Gateway at `https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/`
- **Prototype (Sky Score Radar)** live at `/prototype/`, 3D visualisation with simulated flight tracks (live OpenSky data removed 2026-05-07 pending licensing — see open decisions table)
- **Recent wins**: Amazon Nova hackathon ($200 AWS credits, blog category), Emergent Ventures application submitted (awaiting response), Red Bull Basement application submitted (awaiting shortlist), Luma event applied
- **Known issues**: see `AUDIT_REPORT.md` (last audit 2026-05-06; refreshed 2026-05-07)

## Constraints

These shape every product decision:

- **Riba-free**: don't target conventional banks, mortgage lenders, or general insurers. Target aggregators (data companies, no riba issue), Islamic finance providers (Al Rayan / StrideUp / Gatehouse), conveyancers, surveyors, B2R operators, public bodies. (Memory: `feedback_no_riba_customers.md`.)
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
- ✅ Mobile UX pass (2026-05-22) — Option A redesign: bottom-nav, search-first, full-screen views, safe-area insets. Live on web; pending native resubmission. See `MOBILE_REDESIGN_PLAN.md`.

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
- 🟡 Pricing tiers beyond free, define when first paying integrator commits
- 🟡 Status page at `status.skyscore.com`

### Track 3, Competitions & outreach

**Buildathon (active focus)**: Shared Futures Buildathon London 2026, application deadline 2026-05-15, event 2026-06-07. Awaiting eligibility reply from Foundation. See `BUILDATHON_PLAN.md`.

**Pending applications**:
- Emergent Ventures / Mercatus (£45k, submitted 2026-04-20, expect response within ~1 week of submission, chase if no reply by 2026-05-12)
- Red Bull Basement (submitted 2026-04-12, awaiting shortlist)

**Outreach pipeline**, running from week of 2026-05-12 onward:

| Tier | Companies | Approach | Cadence |
|---|---|---|---|
| 1, Aggregators | Landmark, TM Group, OneSearch Direct | LinkedIn → cold email; reference Riskview/Plansearch gap | 2/week |
| 2, Islamic finance | Al Rayan, StrideUp, Gatehouse, Nester, Yielders | LinkedIn (founder-direct for StrideUp); aligned-values angle | 2/week |
| 3, Direct enterprise | Wahed, Manzilanas, B2R operators | Warm intros only | as found |

Track replies in `OUTREACH_LOG.md` (create when first reply lands). Each entry: contact, date, channel, response, next action.

---

## Near-term task list (next 4 weeks)

### Critical path

| Task | Deadline | Why | Status |
|---|---|---|---|
| **EPC API migration** to `get-energy-performance-data.communities.gov.uk` | **2026-05-30** (hard) | Old service shuts down; current `lambdas/epc/app.py` will 404 | **Done 2026-05-05**, deployed and verified live against `prod/epc?postcode=N1+7SX` (returned 72 real certificates, summary, pagination, OGL attribution). Bearer auth via `EpcBearerToken` SAM parameter sourced from `.env`. **Still pending**: token rotation on the dashboard + redeploy (the version in chat history is considered exposed). |
| Buildathon application (if eligible) | 2026-05-15 | Competition deadline | Awaiting Foundation reply |
| `/v1/score` Lambda extraction | 2026-05-22 | Unblocks both API track + buildathon pre-work | **Done 2026-05-05.** Plus on the same day: bulk endpoint (`POST /v1/score/batch`, up to 100 queries), NYC borough support, methodology v2.0 (iron-clad anchoring of every threshold), OpenAPI spec, Swagger UI, CORS opened to `*`. All verified live. Free-tier API key + Usage Plan (1000/month, 5 burst). |
| OGL attribution on data Lambdas | done | Required for any B2B sale | Done 2026-05-05, `epc`, `sold_prices`, `transport`, `nhs` now return `sources` array |
| Methodology document | done | Required for B2B audit / Buildathon judging | Done 2026-05-05, `METHODOLOGY.md` v1.0 |

### Outreach

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
| **`support@`/`hello@`/`bilalkhizar@skyscore.co.uk` email setup** | **2026-05-12** | `support@skyscore.co.uk` already in App Review notes — Apple may email during v1.0 review (24-72h window starting 2026-05-11). Cloudflare Email Routing (free) → Gmail. ~25 min. Full steps in `memory/project_email_setup_todo.md` |
| **v1.1 native release** (iOS + Android) | **post-Apple-approval** | iPad widths addressed in Wave 13.20 (2026-05-18). Still open for v1.1: (1) iPhone-width layer-toggle UX (legend cramps map on mobile, ~32% of 414px viewport) (2) app icon redesign deferred until conversion data is available (current orange-radar shipping in v1.0.1+). See `memory/project_mobile_ux_redesign_v1_1.md`. |
| **Codemagic cert persistence** | **before build 13** | Apple's 2-cert-per-Personal-Account limit hit during v1.0 ship (build 11 failed, build 12 succeeded after revocation). Generate cert private key once, store base64-encoded as Codemagic env var. Otherwise next signed build hits the wall. Pattern documented in `memory/feedback_codemagic_personal_account_signing.md` ("Future iteration to plan for"). |
| **Play Store / Android side** | **after iOS approval** | Build AAB locally via Android Studio per `mobile/ANDROID_BUILD.md`. Same `index.html`; reuse v1.0 metadata + screenshots. Avoid splitting attention until iOS approval lands. |
| Consumer-site granularity-wall pass | 2026-06-15 | Protects API channel before serious sales |

### Deferred from 2026-05-07 session — full list in [`AUDIT_REPORT.md`](./AUDIT_REPORT.md#deferred--kept-in-mind-for-future-sessions)

Brief summary; pick one or two next session:

- **Security residual** (~10-30 min each): CSP `report-uri`, CSP `img-src` tightening, per-route throttle on `/v1/score`, signup CAPTCHA, HSTS / Permissions-Policy via CloudFront response-headers policy.
- **Visual polish** (~5-15 min each): layer-toggle indicator colours per layer, aircraft-noise legend gating, DEFRA caption stacking, airport text plates.
- **A11y carry-forward** (~10-30 min each): layer toggle hover/active visual differentiation (Critical), heading hierarchy fix (Critical), skip-to-content, touch targets <44px on consumer site, `:focus-visible` fallback, search-results count for SR users, `prefers-reduced-motion`.
- **Code quality** (~10-60 min each): ~~API base URL extraction (4 files duplicated)~~ — done in Wave 12.9 (`js/api-base.js` shared by 3 browser pages; tests/api.test.mjs duplicates intentionally with /preflight 4d drift check guarding alignment). `BOROUGH_ALIASES` expansion, Swagger UI SRI hash, signup race-recovery test.
- **Enterprise readiness** (legal effort): DPA template (CommonPaper, 2-3 hr legal review), MSA + SLA + termination + data return (1-day legal), privacy notice + sub-processor list + retention policy (half-day each), DynamoDB PITR + RTO/RPO doc (1-click + ~1 hour), `pip-audit` integration, `support@skyscore.co.uk` mailbox + 1-business-day SLA, status page subdomain.
- **Performance** (~1 hour): extract inline data (`BOROUGH_DATA`, `AREA_MAP`) from index.html (6.9k lines) to JSON files fetched after first paint, improves LCP.

---

## Open decisions

| Decision | Default | Resolve when |
|---|---|---|
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

## Cross-references

- `BUILDATHON_PLAN.md`, focused plan for Shared Futures Buildathon
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
2. **Haversine distance to flight paths and airports**, already implemented in the consumer site (`index.html` lines 1118-1247)

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
| **Methodology document for due diligence** | Shipped (v3.1) |
| **Methodology version pinning** (`?methodology=` for grace periods) | Documented in §16 |
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
