# Audit Report, Sky Score
**Date:** 2026-05-07
**Files scanned:** 13 Python Lambdas (2 new since prior baseline: `live_flights`, `signup`), `template.yaml`, `iam-policy.json`, `index.html` (4,334 lines), `score-demo/*`, `prototype/index.html`, `scripts/*.py` (incl. new `download_defra_wcs.py`), `tests/`, `backend/tests/`
**Audit performed by:** 3 parallel agents (code, security, frontend/a11y) + manual triage of prior baseline against commits since 2026-05-06
**Previous audit:** 2026-05-06 (39 findings, see triage column below)

---

## Triage of 2026-05-06 baseline

| # | Original issue | Status | Fix commit / note |
|---|---|---|---|
| C1 | NYC `renderNycBoroughs()` resize crash | ✅ Fixed | `3ffd640` |
| C2 | Demo API key publicly exposed | 🟡 Key rotated, structural exposure remains | `8edd4b0` rotated; key still hardcoded in `score-demo/index.html:412`, `score-demo/status.html:153`. See **N-Sec-3** below for the structural fix |
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
