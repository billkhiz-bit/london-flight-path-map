# Audit Report, Sky Score
**Date:** 2026-05-06
**Files scanned:** 11 Python Lambdas, 5 HTML/JS files, 6 markdown docs, OpenAPI spec, SAM template, IAM policy, Playwright + unit tests
**Audit performed by:** 3 parallel agents (backend, frontend, cross-cutting)
**Previous audit:** 2026-03-10..12 (56 days ago, superseded by this one)

---

## Critical (must fix before publicity push or B2B sales)

| # | Issue | File:Line | Category |
|---|---|---|---|
| C1 | **Runtime bug, NYC view crashes on browser resize.** `renderNycBoroughs()` is called with no argument from the resize handler but its signature requires `features`. Calls `.data(undefined)` on D3 selection, throws `Cannot read properties of undefined`. | `index.html:4007` (call site) vs `index.html:3561` (signature) | code |
| C2 | **API key publicly exposed in served frontend.** Free-tier key `T2NpQ…bk5i` is hardcoded in two static files served via CloudFront and committed to git. Anyone viewing source has the key; the 1000 req/month cap is the only abuse defence. Confirmed in commits `2280148` and `07ad823`. | `score-demo/index.html:363`, `score-demo/status.html:153` | security |
| C3 | **Favourites endpoint allows total cross-tenant access (IDOR).** `userId` is taken from query/body without auth, any caller can read/write/delete any user's saved properties. OWASP A01. Already in ROADMAP as known post-hackathon item; severity remains critical for any publicity push that drives traffic. | `backend/lambdas/favourites/app.py:22, 41-42, 62-63` | security |
| C4 | **CORS open to `*` on Bedrock-spending endpoints.** `chat`, `multi_agent`, `analyze_image`, `analyze_document`, `report`, `favourites` should be locked to CloudFront origin, currently any origin can call and burn Bedrock spend. The per-Lambda `CORS_ORIGIN` env var is set but unused (template overrides). | `backend/template.yaml:26` (template default) vs all `backend/lambdas/*/app.py:6-9` (env var dead) | security |
| C5 | **Prompt injection unmitigated.** User-controlled `viewing_context` and `locationData` are interpolated directly into Bedrock system prompts with no delimiter / instruction to ignore embedded directives. | `backend/lambdas/chat/app.py:148`, `multi_agent/app.py:187`, `report/app.py:79` | security |
| C6 | **No JSON body size limits on Bedrock endpoints.** `chat`, `multi_agent`, `report` accept arbitrarily large payloads → an attacker can send megabytes of `history`/`context` and burn Bedrock spend per request. No API Gateway request validator on these routes. | `backend/lambdas/chat/app.py:108`, `multi_agent/app.py:178`, `report/app.py:54`; `backend/template.yaml` (no `RequestValidator`) | security |
| C7 | **Bare `except Exception:` swallows everything with no logging on 10 of 11 Lambdas.** Returns generic 500 without any CloudWatch trail. Production debugging is essentially impossible after the fact. | `backend/lambdas/{chat,multi_agent,analyze_image,analyze_document,report,favourites,score,epc,sold_prices,nhs}/app.py` (multiple lines per file) | code |
| C8 | **Documentation drift, claimed methodology version doesn't match code.** Live API returns `methodologyVersion: "3.1"` but `README.md:7,97` says "v3.0", `score-demo/openapi.yaml:237` example shows "2.0". Methodology defensibility is the explicit selling point, drift here is the highest-trust-risk doc bug. | `README.md:7,97`, `score-demo/openapi.yaml:237`, vs `backend/lambdas/score/app.py:28` | docs |
| C9 | **D3 SVG map has no accessible name.** `<svg id="map-svg">` is the primary content and is invisible to screen readers. No `role`, `aria-label`, or `<title>`. The interactive map is unusable for assistive-tech users. | `index.html:490` | a11y |

---

## Important (fix in next 1-2 weeks)

| # | Issue | File:Line | Category |
|---|---|---|---|
| I1 | `MAX_BATCH_SIZE = 100` allows ~100 sequential postcodes.io HTTP calls per `/v1/score/batch` request inside a 10s Lambda timeout, guaranteed timeouts above ~30 unique postcodes. | `backend/lambdas/score/app.py:30, 268, 822` | code |
| I2 | npm audit: 4 vulns (2 high, `flatted` prototype pollution GHSA-rf6f-7fwh-wjgh, `picomatch` ReDoS GHSA-c2c7-rcm5-vvqj; 2 moderate, `brace-expansion` GHSA-f886-m6hf-6m8v, `postcss` XSS GHSA-qx2v-qp2m-jg93). All transitive devDeps; `fixAvailable: true` for each. | `package.json` / `package-lock.json` | security |
| I3 | OpenAPI spec is missing recent fields. Doesn't document `?include=` query param, `context.quietResolution`, `plannedComponents` block, `?methodology=` grace-period parameter. | `score-demo/openapi.yaml` | docs |
| I4 | Borough metadata duplicated across 3 Lambdas. Drift inevitable; extract to a shared layer or module. | `backend/lambdas/chat/app.py:11-52`, `multi_agent/app.py:11-52`, `score/app.py:51-97` | code |
| I5 | No tests for 9 of 11 Lambdas. Only `score` has unit tests. | `backend/tests/` | tests |
| I6 | No DLQ / `MaximumRetryAttempts` on any Lambda, failed async invocations vanish silently. | `backend/template.yaml` | infra |
| I7 | `lru_cache` caches errors as `None` forever within a container; postcodes.io outage poisons cache for ~15 min. | `backend/lambdas/score/app.py:283, 503` | code |
| I8 | XSS-prone inline `onclick="..."` handlers built via string interpolation with only `'` escaping (not `"`, backslashes, `</script>`). | `index.html:3378, 3383, 3677, 2902` | security |
| I9 | Listener leak: `startLiveFlights()` adds `visibilitychange` listener every toggle. Toggle 5 times, 5 listeners. | `index.html:2751` | code |
| I10 | Touch targets below WCAG 2.5.8 minimum, `.fav-remove` is ~14×14, `.layer-toggle` ~22 px tall. | `index.html:67, 73, 415-416` | a11y |
| I11 | Layer toggles are `<div role="button">` not `<button>`. Switch to native button. | `index.html:452-459` | a11y |
| I12 | Hardcoded API/CloudFront URLs duplicated 3× across files. Drift risk. | `index.html:584`, `score-demo/index.html:364`, `score-demo/status.html:158-188` | code |
| I13 | Bedrock model IDs hardcoded across 5 Lambdas, should be env vars. | `backend/lambdas/{chat,multi_agent,analyze_image,analyze_document,report}/app.py` | infra |
| I14 | `PROJECT_DOCUMENTATION.md` severely stale, claims "10 Lambdas", "290+ neighbourhoods", framing project as a hackathon entry. | `PROJECT_DOCUMENTATION.md:5, 50, 85, 309, 322` | docs |
| I15 | Missing canonical / theme-color / robots meta tags. `score-demo/*` and `prototype/index.html` have no OG tags. | `index.html`, `score-demo/*.html`, `prototype/index.html` | seo |
| I16 | Postcode lookup failure silent, `null` returned with no user-facing toast. | `index.html:1639, 3331, 3346, 3358` | ux |

---

## Minor (polish)

| # | Issue | File:Line | Category |
|---|---|---|---|
| M1 | Inconsistent response shape, only 5 of 11 Lambdas include a `sources` array. | `backend/lambdas/{chat,multi_agent,analyze_image,analyze_document,report,favourites}/app.py` | docs |
| M2 | Inconsistent CORS headers across Lambdas. | `backend/lambdas/*/app.py` | code |
| M3 | `datetime.utcnow()` deprecated in Python 3.12+. | `backend/lambdas/favourites/app.py:54` | code |
| M4 | `iam-policy.json` contains `REPLACE_WITH_YOUR_AWS_ACCOUNT_ID` placeholders. | `backend/iam-policy.json:21,76,108,118,149,160` | infra |
| M5 | 7-9px font sizes trigger WCAG 1.4.4 zoom/reflow concerns. | `index.html:145, 210, 244, 270, 336, 491` | a11y |
| M6 | Tab elements use `<div role="tab">` not native `<button>`. | `index.html:547-549` | a11y |
| M7 | `score-demo/index.html` lacks `:focus-visible` outline. | `score-demo/index.html:96-99` | a11y |
| M8 | Prototype 7-9px cyan-on-black fails AA contrast. | `prototype/index.html:633, 638, 660, 664-665` | a11y |
| M9 | Meta description in `index.html:9` is 268 chars (Google truncates ~155-160). | `index.html:9` | seo |
| M10 | `lang` attribute mismatch, `index.html` uses `"en"`, `score-demo/*` use `"en-GB"`. | various | seo |
| M11 | Score-demo HTML files have no favicon. | `score-demo/*.html` | polish |
| M12 | `is_complex_query` keyword router has overlapping/loose triggers. | `backend/lambdas/chat/app.py:90-103` | code |
| M13 | CHANGELOG entries all dated 2026-05-05 (5 versions same day). Benign. | `CHANGELOG.md` | docs |
| M14 | README architecture diagram says "Lambda × 11" but PROJECT_DOCUMENTATION.md says 10. | `README.md:137`, `PROJECT_DOCUMENTATION.md:85` | docs |

---

## False positives (flagged but not actually issues)

- **NHS Lambda hardcoded `subscription-key: 'public'`**, `'public'` is the literal documented value NHS publishes for the free public tier of `api.nhs.uk/service-search`. Not a leaked secret.

---

## Summary

| Severity | Count |
|---|---|
| Critical | 9 |
| Important | 16 |
| Minor | 14 |
| **Total** | **39** |

By category:
- Security: 8 (incl. IDOR, prompt injection, hardcoded key, CORS)
- Code quality: 11
- Accessibility: 8
- Documentation: 7
- Infra (AWS/SAM): 3
- SEO / metadata: 3
- UX: 1
- Tests: 1

---

## Action plan (this session)

Each item is a separate commit:

1. **C1** Fix `renderNycBoroughs()` resize bug (1 line)
2. **C8** Sync README + OpenAPI version refs to v3.1
3. **C4 / C6** Tighten CORS on Bedrock endpoints + add request body validators
4. **I2** `npm audit fix`
5. **I11 / I10** Quick a11y wins, `<button>` semantics, key touch targets
6. **C9** Add `role="application"` + `aria-label` + `<title>` to map SVG
7. **I14** Refresh `PROJECT_DOCUMENTATION.md`
8. **I3** Update OpenAPI to document `?include=`, `quietResolution`, `plannedComponents`

Deferred (each ≥ half a day; tracked here as the standing list):

- **C3** Favourites auth, needs a real auth scheme
- **C5** Prompt injection mitigations, needs prompt re-engineering
- **C7** Bare except sweep + structured logging, touches every Lambda
- **I1** Batch parallelism, needs `concurrent.futures` or async rewrite
- **I4** Shared borough module via Lambda layer, infra work
- **I5** Test coverage for 9 Lambdas, needs unittest scaffolding
- **I13** Bedrock model IDs to env vars, coordinate with rollover policy

The deferred items above remain in this report as the standing list. Re-run `/audit` quarterly or before major releases.
