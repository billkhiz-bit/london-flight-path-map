# Audit Report, Sky Score
**Date:** 2026-05-07 (refreshed end-of-session)
**Files scanned:** 8 active Python Lambdas (5 dormant Bedrock Lambdas + live_flights deleted today), `template.yaml`, `iam-policy.json`, `index.html`, `score-demo/*`, `prototype/index.html`, `scripts/*.py`, `tests/`, `backend/tests/`
**Audit performed by:** Two rounds of 3-5 parallel agents (code, security, frontend visual + a11y, enterprise readiness) + manual triage. Final round merged into the "Session close" section below.
**Previous audit:** 2026-05-06 (39 findings, see triage column below)

---

## Wave 7+8+9 close — 2026-05-07 late evening

After the day's main session-close section below, three more focused waves shipped:

**Wave 7 (visual polish):**
- Visual fix-5 (per-layer indicator colours on `.layer-toggle.active`) → `0d634b1`
- Visual fix-8 (DEFRA caption stagger 20/34/48 so road/flood/AQ don't overlap) → `0d634b1`
- Visual fix-9 (airport code halo via `paint-order: stroke`) → `0d634b1`

**Wave 8 (code quality):**
- M-N2 (BOROUGH_ALIASES expanded: Royal Borough / London Borough / ampersand / common spellings) → `f91935d`
- I-N6 (signup race-recovery test — proves orphan key revoked, secret value not echoed) → `f91935d`

**Wave 9 (enterprise no-legal):**
- Enterprise gap #10 (DynamoDB PITR enabled in `template.yaml` for all 3 tables) → this commit; **deploy gated on one-time admin IAM update** (see OPERATIONS.md §3.1)
- Enterprise gap #14 (pip-audit integration into `/preflight` skill) → this commit
- `OPERATIONS.md` runbook (closes part of enterprise gap #3 + #10) → this commit
- `SUBPROCESSORS.md` register (closes enterprise gap #3 sub-processor disclosure) → this commit
- `SUPPORT.md` (documents `support@` mailbox + status-page subdomain plan, closes part of #16 / #8) → this commit

**Still open after Wave 9:**
- Enterprise IAM update for PITR — requires root AWS account, blocked until admin can update `FlightMapDeployPolicy` per OPERATIONS.md §3.1.
- Cloudflare email-routing for `support@skyscore.co.uk` — single console click, deferred to next admin window.
- `status.skyscore.co.uk` DNS + Better Stack / StatusGator subscription — deferred (~30 min one-time setup).
- Legal items (DPA, MSA, privacy notice, pen test, SOC 2, insurance) — defer until first paying customer triggers contractual need.

---

## Session close — 2026-05-07 evening

After the second round of agents (code-quality + security + frontend visual + a11y + enterprise readiness), this section consolidates **everything closed today** with commit SHAs, and lists **everything deferred** with audit IDs and priority. The triage column below this section is the longer-form version against the May-6 baseline.

### Closed today (with commit SHAs)

**Critical (security / cost):**
- N-Sec-1, N-Sec-2, N-Sec-3 (XSS chains via OSM, chat-reply, defence-in-depth) → `2405122`
- N-Code-1 (signup `apigateway:DELETE` wildcard) → `a214ba0`; tightened with `aws:RequestTag` on POST in `dab713d`
- N-Code-2 (no per-route throttle on /v1/signup) → `a214ba0`
- 5 dormant AI Lambda routes publicly invokable (smoke-test finding "P") → routes closed `71a731c`, Lambdas + IAM grants deleted entirely `6bad8ce`
- C-A (CSP `unsafe-eval` introduced earlier in session) → `dab713d`
- C-N1 (smoke test posting to closed routes) → `dab713d`
- I-G (signup `apigateway:POST` no `aws:RequestTag` condition) → `dab713d`

**Critical (UX / B2B-credibility):**
- N-Front-1 (B2B demo persona drift) → `a2b5695`
- N-Front-2 (corrupted status placeholders from dash strip) → `a2b5695`
- Visual fix-1 (road overlay paints over aircraft raster) → `a830acb` (mix-blend-mode + reduced opacity)
- Visual fix-2 (legend "LCY/OTHER" misleading after path trim) → `a830acb`
- F-A11y-1 (search input missing combobox semantics) → `54191df`
- F-A11y-3 (metric cards `<div onclick>`) → `54191df`

**Important (already deployed):**
- N-Sec-4 (CORS lockdown on signup) → `a214ba0`
- N-Code-3 partial (live_flights + signup tests) → `5418d73` + `2024147`
- N-Code-5 (signup `print()` → logger) → `a214ba0`
- N-Code-6 (live_flights state pattern) → `5418d73` (+ Lambda removed entirely in `6f6ce7d`)
- N-Code-7 (orphan-key alerting) → `56b0e03`
- N-Front-5 (tabs → buttons + arrow keys + roving tabindex) → `847935c`
- N-Front-6 (first-hint role=status auto-announce) → `f7de68e`
- N-Front-9 (prototype touch targets) → `2e77bda`
- N-Front-10 (prototype ticker XSS defence) → `2e77bda`
- N-Code-4 (DEFRA WCS bare except) → `f97cd8c`
- I2 (npm audit) → already clean
- I3 (OpenAPI completeness: /v1/signup + ?methodology=) → `29ab46f`
- I14 (PROJECT_DOCUMENTATION.md staleness) → `a24add0`
- I15 (canonical/OG/theme-color on score-demo + prototype) → `bc4d426`
- I-N1 (delete dormant Lambda dirs + their IAM grants) → `6bad8ce`
- I-N2 (prototype dead live-flights JS — strengthened gate to throw on flag flip) → `6bad8ce`
- I-N4 (score CORS env-var consistency) → `6bad8ce`
- I-F (DEFRA loader + audit script bare except) → `dab713d`
- M-N1 (boto3 client per call hoisted) → `6bad8ce`
- Visual fix-3 (flight-path strokes too faint) → `a830acb`
- Visual fix-4 (heliport orange = LHR orange) → `a830acb`
- Visual fix-7 (animated dot halo) → `a830acb`

**Critical (accepted with rationale):**
- C2 (demo API key in served HTML) → accepted with rotation discipline `d43dddf`
- C4 (CORS `*` on remaining endpoints) → accepted by design (B2B integrators need it; API-key gated)

**Defence-in-depth deployed (no specific audit ID, all preventive):**
- CSP enforcing on all 5 HTML pages → `967f9d1`
- `X-Content-Type-Options: nosniff` + `Referrer-Policy: strict-origin-when-cross-origin` on all 5 pages → `445c59d`
- `/.well-known/security.txt` (RFC 9116) → `445c59d`
- `AWS_BILLING_ALARM_SETUP.md` runbook → `445c59d`
- `AllowedPattern '^.+$'` on every NoEcho secret → `aaf192f`
- `OPENSKY_LICENSING_EMAIL.md` enquiry sent (Ticket #835285) → `a306a7b` + `9bf5482`
- `SECURITY.md` security one-pager (closes enterprise gap #4) → `b6c7806`
- `/api` landing page (closes enterprise gap #19) → `88b56a4`
- `OUTREACH_DRAFTS.md` (Tier 1/2 cold templates + warm-intro DM) → `2024147`
- `AVIATIONSTACK_SPIKE.md` (live-aircraft fallback if OpenSky says no) → `2024147`

### Deferred — kept in mind for future sessions

These didn't block today's session and are tracked here so they aren't lost. Each is a focused 15-60 min commit (or longer for the enterprise items requiring legal review).

#### Security (residual)

| ID | Item | Priority | Effort |
|---|---|---|---|
| I-A | CSP `report-uri` (no endpoint configured; violations log to DevTools only) | Medium | ~30 min (Lambda or `report-uri.com` SaaS) |
| I-B | CSP `img-src https:` too permissive on index.html — tighten to specific WMS hosts | Medium | ~10 min |
| I-D | No per-route throttle on `/v1/score` or `/v1/score/batch` (per-key usage plan caps cost; per-route would prevent one tenant starving others) | Medium | ~5 min in `template.yaml` |
| I-E | Favourites `X-Device-Token` is capability-only (not identity-based) — known limitation; tokens never expire / no rotation | Low until PII expands | Bigger redesign |
| I-H | No CAPTCHA on `/v1/signup` (1 RPS / 5 burst gates abuse but ~60 keys/min still possible) | Low-medium | ~30 min (hCaptcha free tier) |
| M-B | No `Strict-Transport-Security` header (needs CloudFront response-headers policy, can't be set via `<meta>`) | Low | ~15 min in CloudFront console |
| M-C | No `Permissions-Policy` header (same constraint as HSTS) | Low | ~10 min |
| M-D | CSP `connect-src` includes whole `raw.githubusercontent.com` host — pin specific commit + SRI for the geojson load | Low | ~5 min |
| M-E | Status-page CSP omits Goatcounter (intentional? or oversight?) | Trivial | ~3 min |

#### Frontend visual + design (carried)

| ID | Item | Priority | Effort |
|---|---|---|---|
| Visual fix-5 | Layer-toggle pills don't show layer's colour when active | Important | ~10 min CSS |
| Visual fix-6 | Aircraft-noise legend always visible regardless of toggle | Important | ~10 min in toggle handler |
| Visual fix-8 | DEFRA caption labels stack at same x/y on toggle | Polish | ~5 min |
| Visual fix-9 | Airport code text needs white text-stroke / plate over labels layer | Polish | ~5 min |

#### Frontend a11y + UX (carried)

| ID | Item | Priority | Effort |
|---|---|---|---|
| F-A11y-2 | Layer toggle hover and active states visually identical (colour-only differentiation) | Critical (WCAG 1.4.1) | ~15 min CSS |
| F-A11y-4 | Heading hierarchy skips levels in injected sidebar HTML (h2 → h3 with no h2 between) | Critical | ~30 min |
| F-UX-5 | No skip-to-content link | Important (WCAG 2.4.1) | ~10 min |
| F-UX-6 | Touch targets <44px on consumer site (`.layer-toggle` 32px; `.persona-btn` ~25; `.fav-btn` ~22; `.city-btn` ~22; `.tab` ~30) | Important (WCAG 2.5.5) | ~15 min CSS |
| F-UX-7 | Search `outline:none` without `:focus-visible` fallback | Important (keyboard a11y) | ~5 min |
| F-UX-8 | Search dropdown not announced to SR users — no `aria-live` count | Important | ~10 min |
| F-UX-9 | `score-explain-trigger` tooltip has no Esc dismiss + overflows on small viewports | Important (WCAG 1.4.13) | ~20 min |
| F-Perf-10 | `index.html` 6.9k lines / inline data — extract `BOROUGH_DATA`, `AREA_MAP`, `NYC_*` to JSON files fetched after first paint | Important (LCP) | ~1 hour |
| F-UX-11 | `prefers-reduced-motion` not honoured anywhere | Minor | ~10 min |
| F-UX-12 | City-selector buttons have no `aria-pressed` (same anti-pattern as N-Front-1) | Minor | ~5 min |
| F-UX-13 | "Change profile" inline button styled as link — confusing for SR users | Minor | ~5 min |
| F-UX-15 | Search hint not associated to input via `aria-describedby` (now FIXED in `54191df`) | — | done |

#### Code quality (carried)

| ID | Item | Priority | Effort |
|---|---|---|---|
| I-N5 | API base URL duplicated in 4 files (`index.html`, `score-demo/{index,api-docs,status}.html`, `tests/api.test.mjs`) | Medium | ~15 min (build step or constant) |
| I-N6 | Signup race-recovery test (the `_safe_revoke_orphan_key` path with mocked `get_api_key` / `delete_api_key`) | Medium | ~20 min |
| I4 | Borough metadata Lambda layer (carry-forward from May-6) | Medium-high | ~half day |
| I6 | DLQ on async Lambdas (no async Lambdas exist now — likely moot) | Low | re-check on next async addition |
| I12 | Hardcoded URL drift across 3-4 files | Medium | partly addressed via skyscore.co.uk migration |
| M-N2 | `BOROUGH_ALIASES` only 4 entries — postcodes.io returns dozens of edge-case admin_district strings | Medium | ~10 min |
| M-N5 | Swagger UI loaded from unpkg.com with no SRI hash | Low | ~5 min |

#### Enterprise readiness (carried — needs legal review)

| Gap # | Item | Effort |
|---|---|---|
| 1 | DPA template (CommonPaper) | 2-3 hr legal review |
| 2 | MSA + SLA + termination + data return clauses (CommonPaper SaaS MSA) | 1-day legal effort |
| 3 | Privacy notice + sub-processor list + retention policy (`/privacy`, `SUBPROCESSORS.md`, `OPERATIONS.md`) | half-day each |
| 5 | Independent penetration test | ~£3-5k for 3-day external test; defer until first £499+/mo customer |
| 6 | SOC 2 / ISO 27001 attestations | 6-12 months, ~£8-15k/yr Drata or Vanta; defer until contractually required |
| 8 | Status page on `status.skyscore.co.uk` subdomain | ~30 min DNS + S3 redirect |
| 10 | DynamoDB Point-in-Time Recovery + documented RTO/RPO in `OPERATIONS.md` | ~1 hour (PITR is a 1-click) |
| 12 | Termination + data return clause in MSA | bundle with #2 |
| 14 | `pip-audit` integration into `/preflight` + Swagger UI SRI pin | ~15 min |
| 15 | Professional indemnity / cyber liability insurance | Hiscox / Markel quote when first contract requires |
| 16 | Customer support response-time commitments (`support@skyscore.co.uk` mailbox + 1-business-day SLA) | ~30 min + DNS |
| 17 | Multi-region failover / customer-isolated environments | defer until Enterprise tier customer |

#### Decisions (still open)

| Decision | Default | Resolve when |
|---|---|---|
| OpenSky reply | Awaiting Ticket #835285; chase 2026-06-04 | Reply lands or 4 weeks pass |
| Whether to delete the 5 deleted Bedrock Lambda dirs from git history | No (git history is the recovery path) | n/a — keep |
| Buildathon eligibility | Awaiting Foundation reply (sent 2026-05-05); chase 2026-05-10 | Reply lands |
| Pricing tier specifics | Indicative on `/api` landing page | First prospect conversation |

---

---

## Triage of 2026-05-06 baseline

| # | Original issue | Status | Fix commit / note |
|---|---|---|---|
| C1 | NYC `renderNycBoroughs()` resize crash | ✅ Fixed | `3ffd640` |
| C2 | Demo API key publicly exposed | 🟢 **Accepted with rotation discipline (2026-05-07)** | `8edd4b0` rotated; key still hardcoded in `score-demo/index.html:412`. After review, accepted as bounded risk: blast radius is "attacker DOSes the demo for ≤30 days by burning the 1000 req/month quota". Rotation takes 5 minutes (regenerate key in APIGW console + redeploy `score-demo/index.html`). Building a server-side proxy adds latency + a moving piece for a marketing-surface threat. Re-evaluate if a paying customer ever depends on the demo working. |
| C3 | Favourites IDOR | 🟡 Mitigated by device-token, downgraded to Important | `eb2aa56` added `X-Device-Token` UUID requirement. Not fully closed: capability-based, not identity-based; anyone learning a token can use it. **N-Sec-2** chains XSS to token theft, re-opening the threat |
| C4 | Open CORS on Bedrock endpoints | 🟢 Accepted by design | `template.yaml:14-26` documents `*` as intentional for B2B; Lambda env var `CORS_ORIGIN` still locks response headers to CloudFront. Residual risk: **N-Sec-4** (no per-route throttle on Bedrock) |
| C5 | Prompt injection unmitigated | 🟡 Mitigated at prompt layer only | `e8992bb` added `<viewing_context>` delimiters + `_sanitise_context`. **Output layer not escaped** — see **N-Sec-2** for the chained XSS |
| C6 | No body size limits | 🟡 Per-Lambda cap added, no APIGW validator | `e8992bb` added `MAX_BODY_BYTES = 64KiB` in chat/multi_agent/report; analyze_image (1MB), analyze_document (2MB) cap separately |
| C7 | Bare `except Exception:` no logging | ✅ Fixed | `e8992bb` — every Lambda now `logger.exception` then 500 response |
| C8 | Methodology version drift | ✅ Fixed | `3ffd640` |
| C9 | D3 SVG no accessible name | ✅ Fixed | `3ffd640` — `index.html:591` has `role="application"` + comprehensive `aria-label` + `<title>` |
| I1 | Batch endpoint sequential HTTP | ✅ Fixed | `e8992bb` |
| I2 | npm audit (4 vulns) | ✅ Fixed | `3ffd640`; live `npm audit` returns 0 vulnerabilities (lockfile inspection by security agent disagreed but my fresh run is authoritative) |
| I3 | OpenAPI missing fields | 🔴 Still open | |
| I4 | Borough metadata duplicated | 🔴 Still open | |
| I5 | No tests for 9 of 11 Lambdas | 🟡 Partial | `eb2aa56` added handler tests; new `live_flights` + `signup` have none — see **N-Code-3** |
| I6 | No DLQ on async Lambdas | 🔴 Still open | |
| I7 | `lru_cache` caches errors as None | ✅ Fixed | `e8992bb` |
| I8 | Inline onclick XSS | 🟡 Mostly fixed | Favourites delegated; static handlers (`closeReport`, `printReport`, `switchTab`, `switchCity`, `toggleMetricDetail`) still inline. **N-Sec-1**, **N-Sec-2** are the live exploitation paths |
| I9 | visibilitychange listener leak | ✅ Fixed | `e8992bb` |
| I10 | Touch targets <24×24 | ✅ Fixed | `5e7524d` |
| I11 | Layer toggles `<div role="button">` | ✅ Fixed | Native `<button>` + `aria-pressed` |
| I12 | Hardcoded URLs duplicated | 🔴 Still open | |
| I13 | Bedrock model IDs hardcoded | 🟡 Partial | Env vars added (`os.environ.get('NOVA_*_MODEL_ID', ...)`) but template never overrides — defaults still hardcoded in code |
| I14 | Stale `PROJECT_DOCUMENTATION.md` | 🟡 Partial | `0c20451` synced NYC; other claims still drifted |
| I15 | Missing canonical/OG/theme-color | 🟡 Partial | Added to `index.html:9-37`. Still missing on `score-demo/*` and `prototype/index.html` |
| I16 | Silent postcode lookup failures | 🔴 Still open | |
| M1-M2, M4-M14 | Polish items | 🔴 Mostly still open | M3 (`datetime.utcnow`) ✅ fixed |

**Net delta:** 9 Critical → 1 still-open + 4 partial-mitigation + 2 design-accepted. 16 Important → 8 still open. 14 Minor → 13 still open.

---

## NEW Critical (must-fix before publicity push or B2B sales)

| # | Issue | File:Line | Category |
|---|---|---|---|
| **N-Sec-1** | **DOM XSS via OSM data, NHS service display.** `s.website`, `s.name`, `s.address`, `s.postcode` from community-edited OSM Overpass results interpolated raw into `innerHTML` and `href`. An attacker can poison an OSM node tag with `javascript:` or `<script>` payloads that execute on every visitor of the affected postcode. | `index.html:2229-2230, 2235` | security |
| **N-Sec-2** | **DOM XSS in chat-reply renderer, chains with C5.** `formatChatReply()` (line 2310) converts markdown to HTML but never escapes. A successful prompt-injection that emits `<img src=x onerror=…>` runs in the user's session, steals the device token, and turns C3's mitigation back into a favourites takeover. The C5 prompt-layer mitigation is incomplete on its own. | `index.html:3390, 4283, 4311` | security |
| **N-Code-1** | **Signup IAM grants `apigateway:DELETE` on `arn:.../apikeys/*` (wildcard).** A bug or compromise in the signup Lambda lets it delete any API key in the AWS account, not only keys it created. | `backend/template.yaml:425-427` | security/infra |
| **N-Code-2** | **Self-service `/v1/signup` has no per-route throttle and no CAPTCHA.** Inherits only the global 10 RPS API throttle shared across all routes. An attacker can pump ~600 keys/min into the AWS account's per-account APIGW key quota (default 10,000), exhausting it and locking out legitimate signups; plus the shared usage plan widens the Bedrock cost surface. | `backend/template.yaml:428-443`, `backend/lambdas/signup/app.py:13-20`, `backend/lambdas/signup/app.py:54-58` (CORS `*`) | security |
| **N-Front-1** | **Persona regression on B2B demo.** New personas (`renter`/`commuter`/`downsizer`) shipped on `index.html` + `openapi.yaml` in `192ce18` are missing from `score-demo/index.html`. The page B2B prospects land on disagrees with the docs they read first. | `score-demo/index.html:372-378, 415` | UX/credibility |
| **N-Front-2** | **Em-dash strip script (`192ce18`) corrupted UI placeholders in status page.** Render shows literal `, ` where a placeholder string used to live (Last checked, methodology version, API version). | `score-demo/status.html:127, 136-137` | UX |

---

## NEW Important (fix in next 1-2 weeks)

| # | Issue | File:Line | Category |
|---|---|---|---|
| **N-Sec-3** | TfL station names, sold-prices addresses, autocomplete `b`/`a`/`pc` values reach `innerHTML` unescaped. Lower exploitability (sources are trusted) but breaks defence-in-depth; autocomplete strings include user-typed text already spliced into `data-value="${b}"` attributes. | `index.html:2123-2128, 2137, 2334-2341, 2451-2462, 3284-3320` | security |
| **N-Sec-4** | **No per-route throttle on Bedrock endpoints.** Global API throttle (10 RPS / 20 burst) applies to all routes. A single attacker hitting 10 RPS for 1 minute = 600 Bedrock invocations on Nova Pro. Per-route limits should be 1 RPS / 3 burst for `/chat`, `/multi-agent`, `/report`. | `backend/template.yaml:38-42` | security/cost |
| **N-Sec-5** | Signup email/name interpolated into APIGW `key_name` and `description` with light sanitisation (`@`→`_at_`, `.`→`_`); newlines + control chars reach AWS API. Low impact (AWS validates) but no length cap could leak `ValidationException` internals. | `backend/lambdas/signup/app.py:139-143` | security |
| **N-Code-3** | **No tests for `live_flights` or `signup` Lambdas.** Reopens I5 with extra surface; signup race-recovery (delete on failed create) is exactly the path that needs a test. | `backend/tests/`, `tests/` | tests |
| **N-Code-4** | `download_defra_wcs.py` swallows all network errors with bare `except Exception` — same anti-pattern C7 fixed across the Lambdas, reintroduced in the new script. | `scripts/download_defra_wcs.py:242` | code |
| **N-Code-5** | `signup` uses `print()` for warning/info logs instead of the `logging` module. Inconsistent with the C7-shipped pattern; breaks structured-log search. | `backend/lambdas/signup/app.py:234, 238, 248, 278` | code |
| **N-Code-6** | `live_flights` mutates `_fetch_opensky.last_error` (function attribute) for cross-call state. Race-prone on warm containers; hides errors from the cache-hit path. | `backend/lambdas/live_flights/app.py:109-199` | code |
| **N-Code-7** | `signup` race recovery uses best-effort `delete_api_key`; orphaned APIGW keys leak silently if revoke fails. No DLQ or out-of-band reconciliation; AWS-account API-key quota erodes over time. | `backend/lambdas/signup/app.py:236-239` | infra |
| **N-Front-3** | Report modal + chat panel lack Escape-to-close, focus trap, and focus-on-open. `aria-modal="true"` is set but no Escape handler; tab focus leaks to the page underneath. | `index.html:609, 628-636` | a11y |
| **N-Front-4** | Modal close buttons are `<span>` not `<button>`. No `tabindex`, no keyboard activation. | `index.html:612, 630` | a11y |
| **N-Front-5** | Tabs still `<div role="tab">` not `<button>`; missing arrow-key navigation between tabs. (Repeats prior M6; layer toggles got fixed, tabs didn't.) | `index.html:650-652` | a11y |
| **N-Front-6** | First-hint `role="status"` announces on every page load, then auto-dismisses at 30s with no way to re-trigger. SR users hear it once, can never re-find it. | `index.html:534` | a11y |
| **N-Front-7** | `title=` is not an accessible name on mobile. `chat-fab` relies on `title` only; needs `aria-label`. | `index.html:608` | a11y |
| **N-Front-8** | Report `<body>` updates `innerHTML` after a 10-15s Nova call with no `aria-live`. SR users get no progress announcement; content silently appears. | `index.html:3611, 3622, 3624` | a11y |
| **N-Front-9** | Prototype mobile touch-bar buttons compute to ~22-30 px tall at 480 px viewport (`#mobile-touch-bar button { font-size:8px; padding:7px 8px }`). Below WCAG 2.5.8 24×24 minimum on smallest breakpoint. | `prototype/index.html:715-728` | a11y |
| **N-Front-10** | Prototype ticker / header `innerHTML` built by string concat. Currently safe (hard-coded METAR/ATIS) but pattern would break if any field came from OpenSky. `selectFlight` uses `esc()`; ticker doesn't. | `prototype/index.html:2454, 2614, 2618` | security/code |

---

## NEW Minor

| # | Issue | File:Line |
|---|---|---|
| **N-Code-8** | `_lookup_lden_raster` constructs a fresh `boto3.client('dynamodb')` per call (~50ms cold). Hoist to module scope. | `backend/lambdas/score/app.py:354` |
| **N-Code-9** | `MAX_PROMPT_INJECT_PATTERNS` defined but never referenced. Either remove or wire into `_sanitise_context`. | `backend/lambdas/chat/app.py:126` |
| **N-Code-10** | `BOROUGH_ALIASES` only has 4 entries; postcodes.io returns dozens of edge-case `admin_district` strings. Silently falls through to "borough not supported". | `backend/lambdas/score/app.py:454-459` |
| **N-Sec-6** | `score` Lambda hard-codes `Access-Control-Allow-Origin: '*'` ignoring `CORS_ORIGIN` env var; inconsistent with other Lambdas. Acceptable on B2B endpoint but creates drift. | `backend/lambdas/score/app.py:957-963` |
| **N-Sec-7** | Orchestrator JSON parsing in `multi_agent` only handles ` ``` ` fences. If the model emits commentary, the IndexError fallback runs all 3 agents — burns 3× Bedrock cost on every malformed reply. | `backend/lambdas/multi_agent/app.py:236-242` |
| **N-Front-11** | Footer separator `<span class="sep">·</span>` read by SR as "middle dot" between every link. Add `aria-hidden="true"`. | `index.html:108-120` |
| **N-Front-12** | Footer base font-size 8 px triggers WCAG 1.4.4 reflow concerns (re-flag of M5). | `index.html:111` |
| **N-Front-13** | Swagger UI loaded from `unpkg.com` with no SRI hash. A compromised CDN response would inject arbitrary JS into the docs page. | `score-demo/api-docs.html:1-68` |
| **N-Front-14** | Prototype `lang="en"` vs `en-GB` everywhere else (re-flag of M10; survived `192ce18`). | `prototype/index.html:2` |

---

## False positives (flagged but not actually issues)

- **`npm audit` 4 vulnerabilities still present** (security agent N7) — disconfirmed by live `npm audit` run, returns 0 vulnerabilities. The agent inspected the lockfile statically; the vulnerable version ranges no longer match what's installed.
- **NHS Lambda hardcoded `subscription-key: 'public'`** (carried forward from prior audit) — `'public'` is the literal documented value for the free public tier of `api.nhs.uk/service-search`, not a leaked secret.

---

## Summary

| Severity | New this cycle | Prior items still open | Total active |
|---|---|---|---|
| Critical | 6 | 0 (4 partial + 2 design-accepted) | 6 |
| Important | 15 | 8 | 23 |
| Minor | 9 | 13 | 22 |
| **Total** | **30** | **21** | **51** |

By category (new + carried):
- Security: 12 (XSS chains, signup IAM/throttle, per-route Bedrock limits, defence-in-depth)
- A11y: 11 (modal Escape/focus, tabs, screen-reader, touch targets on prototype)
- Code quality: 9 (logging, races, dead code, stale clients)
- Docs / drift: 6 (OpenAPI fields, persona drift, doc stale, status placeholders)
- Infra: 4 (DLQ, signup quota leak, model IDs, throttling)
- SEO / metadata: 3 (carry-forward)

---

## Recommended action plan (this week)

Each item is a separate commit; ordered by blast-radius / cost-to-fix.

1. **N-Sec-1, N-Sec-2, N-Sec-3** Wrap every `innerHTML` interpolation in `escapeHtml()` (helper exists at `index.html:1246`); for `href` use `escapeHtmlAttr` and validate scheme is `http(s):` only. Run `formatChatReply` through escape *before* markdown formatting. **One commit, ~1 hour.**
2. **N-Code-1, N-Code-2** Restrict signup IAM to keys created by this function via tag-based condition; add per-method APIGW throttle (1 RPS / 5 burst) on `/v1/signup` + lock CORS to `https://skyscore.co.uk`; add hCaptcha. **~1 hour.**
3. **N-Sec-4** Per-route `MethodSettings` for `/chat`, `/multi-agent`, `/report` with `ThrottlingRateLimit: 1`, `ThrottlingBurstLimit: 3`. **~10 min.**
4. **N-Front-1, N-Front-2** Add 3 `<option>` rows to demo persona dropdown + label entries; replace `, ` placeholders with `Loading…` in status.html. **~10 min.**
5. **N-Front-3, N-Front-4** Modal Escape handler + focus trap + close-as-button. **~30 min.**
6. **N-Front-9** Prototype mobile touch-bar `min-height: 44px`. **~5 min.**

**Deferred (each ≥ half day):**

- **N-Code-7** signup orphan-key reconciliation
- **N-Code-3** test coverage for live_flights + signup
- **N-Front-5** tab keyboard nav (arrow keys + roving tabindex)
- **I3** OpenAPI doc completeness
- **I4** shared borough Lambda layer
- **I6** DLQ on async Lambdas

Standing items below remain on the backlog. Re-run `/audit` quarterly or before major releases.
