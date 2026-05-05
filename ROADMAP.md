# Sky Score Roadmap

> **Living document.** Updated as Sky Score evolves. For the focused buildathon plan see `BUILDATHON_PLAN.md`. For Claude session instructions see `CLAUDE.md`. This roadmap is the *what next* across all tracks.

**Last reviewed:** 2026-05-05

---

## Vision

Sky Score is the noise + livability layer for UK property data — designed to be honest about hidden harms (aviation noise, road noise, air quality, crime) that listings sites have a financial incentive to hide. Two surfaces: a consumer site that informs renters/buyers, and a B2B API that puts the same data inside the workflows of conveyancers, property data aggregators, and Islamic-finance providers. Aligned with Maqasid al-Shariah (protecting buyers from harm) and explicitly riba-free in customer targeting.

## Current state

- **Consumer site live**: `https://d1oe4ftwutjpf.cloudfront.net` — covers London + NYC, postcode/borough scoring, AI chat, multi-agent reports, image/document analysis, favourites
- **Backend**: 10 Lambdas behind API Gateway at `https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/`
- **Prototype (Sky Score Radar)** live at `/prototype/` — 3D visualisation with live OpenSky aircraft data
- **Recent wins**: Amazon Nova hackathon ($200 AWS credits, blog category), Emergent Ventures application submitted (awaiting response), Red Bull Basement application submitted (awaiting shortlist), Luma event applied
- **Known issues**: see `AUDIT_REPORT.md` (last audit 10–12 March, **suggest re-running `/audit`**)

## Constraints

These shape every product decision:

- **Riba-free**: don't target conventional banks, mortgage lenders, or general insurers. Target aggregators (data companies, no riba issue), Islamic finance providers (Al Rayan / StrideUp / Gatehouse), conveyancers, surveyors, B2R operators, public bodies. (Memory: `feedback_no_riba_customers.md`.)
- **Estate agents are misaligned, not target**: their incentive is to push sales through, not inform buyers. (Memory: `project_api_target_customers.md`.)
- **Dual-model channel wall**: consumer site = borough-level free; API = per-property paid. Avoid undercutting paying integrators. (See "Track 1" below.)
- **British English everywhere**: code comments, UI text, docs, commits. (See user CLAUDE.md.)

---

## Three parallel tracks

### Track 1 — Consumer site (`d1oe4ftwutjpf.cloudfront.net`)

The consumer site is the marketing engine, not the revenue centre. Keep it sharp; don't compete with the paid API.

**Active work**:
- Down-grade per-property data display to borough-level only (granularity wall — protects API customers)
- Sharpen the "ethical alternative to listings sites" framing in copy
- Mobile UX pass on borough/postcode flows

**Deferred**:
- Authentication for favourites endpoint (post-hackathon item from `AUDIT_REPORT.md`)
- ARIA accessibility pass (post-hackathon item)

### Track 2 — B2B API (`/v1/score`, `/v1/score/batch`)

The product. Wraps the scoring engine into a stable, documented, monetisable endpoint for aggregators and Islamic-finance providers.

**Shipped (2026-05-05)**:
- ✅ `GET /v1/score` — single-postcode (London) or borough (London + NYC) lookup with persona presets and custom weights override
- ✅ `POST /v1/score/batch` — bulk endpoint, up to 100 queries per call, partial-failure-tolerant (failed items return error per-row)
- ✅ API key auth via API Gateway Usage Plan (1000 req/month free tier, 5/sec burst, 2/sec sustained)
- ✅ Methodology v2.0 — every threshold and weight anchored to DEFRA Lden bands, WHO noise guidelines, Ofsted distribution, ONS crime medians, TfL PTAL; references section
- ✅ OpenAPI 3.0 spec at `/score-demo/openapi.yaml` + interactive Swagger UI at `/score-demo/api-docs.html`
- ✅ NYC light support — borough-name lookup for Manhattan, Brooklyn, Queens, Bronx, Staten Island; ZIP resolution still on roadmap
- ✅ CORS opened to `*` so third-party browser integrations work; abuse vector unchanged (server-side abuse was always possible regardless)
- ✅ OGL attribution in every response

**Outstanding**:
- 🟡 Per-postcode noise sampling (replacing borough-level Lden bands with DEFRA WMS raster sampling at postcode centroid + Haversine flight-path distance) — ~1-day task
- 🟡 NYC ZIP-to-borough resolution — adds ~250 ZIP lookups; dependent on a non-postcodes.io resolver
- 🟡 UK Core Cities (Manchester, Birmingham, Bristol, etc.) — geographic expansion, gated on liveability data acquisition
- 🟡 Pricing tiers beyond free — define when first paying integrator commits
- 🟡 Status page at `status.skyscore.com`

### Track 3 — Competitions & outreach

**Buildathon (active focus)**: Shared Futures Buildathon London 2026, application deadline 2026-05-15, event 2026-06-07. Awaiting eligibility reply from Foundation. See `BUILDATHON_PLAN.md`.

**Pending applications**:
- Emergent Ventures / Mercatus (£45k, submitted 2026-04-20, expect response within ~1 week of submission — chase if no reply by 2026-05-12)
- Red Bull Basement (submitted 2026-04-12, awaiting shortlist)

**Outreach pipeline** — running from week of 2026-05-12 onward:

| Tier | Companies | Approach | Cadence |
|---|---|---|---|
| 1 — Aggregators | Landmark, TM Group, OneSearch Direct | LinkedIn → cold email; reference Riskview/Plansearch gap | 2/week |
| 2 — Islamic finance | Al Rayan, StrideUp, Gatehouse, Nester, Yielders | LinkedIn (founder-direct for StrideUp); aligned-values angle | 2/week |
| 3 — Direct enterprise | Wahed, Manzilanas, B2R operators | Warm intros only | as found |

Track replies in `OUTREACH_LOG.md` (create when first reply lands). Each entry: contact, date, channel, response, next action.

---

## Near-term task list (next 4 weeks)

### Critical path

| Task | Deadline | Why | Status |
|---|---|---|---|
| **EPC API migration** to `get-energy-performance-data.communities.gov.uk` | **2026-05-30** (hard) | Old service shuts down; current `lambdas/epc/app.py` will 404 | **Done 2026-05-05** — deployed and verified live against `prod/epc?postcode=N1+7SX` (returned 72 real certificates, summary, pagination, OGL attribution). Bearer auth via `EpcBearerToken` SAM parameter sourced from `.env`. **Still pending**: token rotation on the dashboard + redeploy (the version in chat history is considered exposed). |
| Buildathon application (if eligible) | 2026-05-15 | Competition deadline | Awaiting Foundation reply |
| `/v1/score` Lambda extraction | 2026-05-22 | Unblocks both API track + buildathon pre-work | **Done 2026-05-05.** Plus on the same day: bulk endpoint (`POST /v1/score/batch`, up to 100 queries), NYC borough support, methodology v2.0 (iron-clad anchoring of every threshold), OpenAPI spec, Swagger UI, CORS opened to `*`. All verified live. Free-tier API key + Usage Plan (1000/month, 5 burst). |
| OGL attribution on data Lambdas | done | Required for any B2B sale | Done 2026-05-05 — `epc`, `sold_prices`, `transport`, `nhs` now return `sources` array |
| Methodology document | done | Required for B2B audit / Buildathon judging | Done 2026-05-05 — `METHODOLOGY.md` v1.0 |

### Outreach

| Task | Deadline | Why |
|---|---|---|
| 2 warm-intro asks (LinkedIn 1st/2nd connections at Al Rayan, StrideUp, Landmark, Climate X) | 2026-05-08 | One warm intro beats 20 cold emails |
| 2 cold emails using Tier 1 + Tier 2 templates | Weekly from 2026-05-12 | Build response sample size |
| Chase Emergent Ventures if no reply by 2026-05-12 | 2026-05-12 | Stated response window passing |

### Polish (non-blocking)

| Task | Deadline | Why |
|---|---|---|
| Re-run `/audit` (last one is >40 days old) | this week | Catches drift |
| Methodology doc for the API | 2026-05-29 | Required for serious B2B conversations |
| Consumer-site granularity-wall pass | 2026-06-15 | Protects API channel before serious sales |

---

## Open decisions

| Decision | Default | Resolve when |
|---|---|---|
| Channel wall design (granularity / volume / format) | Granularity | Before first paying API customer |
| API pricing model | Per-query, tiered | When first prospect asks |
| Score response shape (opinionated / components / both) | **Resolved 2026-05-05**: both. `/v1/score` returns `score` + `components` + `context`. Optional `?weights=` lets customers override defaults. | n/a |
| Buildathon fork repo name | `sky-score-halal` | When Foundation confirms eligibility |
| Whether to drop `multi_agent` Lambda from API surface in favour of leaner score-only | TBD | After first 3 customer conversations |
| CORS for `/v1/score` from third-party browser origins | **Resolved 2026-05-05**: global CORS opened to `*`. The score endpoints are API-key gated; the Bedrock endpoints are throttled at API Gateway (10 req/s) and CORS does not protect against server-side abuse anyway. | n/a |
| OpenSky commercial-licensing — replace, negotiate, or decouple | Decouple (consumer only) until first paying integration; negotiate or swap before then | Before any B2B aviation-data integration |
| EPC: API-on-demand vs bulk download | API now; bulk download once approaching rate-limit pressure (~50% of 6000-per-5-min quota) | When B2B traffic ramps |
| NYC ZIP-to-borough resolution | **Deferred** — borough-name lookup works for now (`?city=nyc&borough=Manhattan`) | When first NYC integrator asks |

---

## Cross-references

- `BUILDATHON_PLAN.md` — focused plan for Shared Futures Buildathon
- `AUDIT_REPORT.md` — code quality snapshot (re-run pending)
- `CLAUDE.md` — Claude session conventions
- `README.md` — public-facing project documentation
- Memory: `project_api_target_customers.md`, `project_buildathon_focus.md`, `project_competitive_landscape.md`, `feedback_no_riba_customers.md`, `project_siraj_noor.md` (sister project)

## Update protocol

When a task ships or a decision lands: update this file rather than the chat. Treat unresolved items in "Near-term tasks" and "Open decisions" as the source of truth between sessions.
