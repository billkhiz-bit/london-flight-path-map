# Audit Report, Sky Score
**Date:** 2026-07-24 (full audit)
**Files scanned:** 7 active Python Lambdas, `template.yaml`, `iam-policy.json`, `index.html` (8.2k lines), `js/api-base.js`, `sw.js`, `score-demo/*`, `api/index.html`, `pricing.html`, `privacy.html`, `tests/`, `backend/tests/`, `.github/workflows/`, live-site parity vs skyscore.co.uk
**Audit performed by:** 6 parallel dimension agents (security backend/frontend, code backend/frontend, a11y/design, deps + live parity) with per-finding adversarial verification. Verification was cut short by the account's monthly spend limit — see the 2026-07-24 section for what that means.
**Previous audits:** 2026-05-21 (website, post-launch), 2026-05-07, 2026-05-06 (39-finding baseline; triage table below)

---

## 2026-07-24 full audit

**Method + caveat:** 6 dimension finders ran to completion; each finding then went to an adversarial verifier. 40 of 66 agents completed before the account hit its **monthly spend limit**, which killed the remaining verifiers (all of security-backend's, most of code-frontend's, two of a11y's). Findings whose verifier ran and confirmed are in the *Confirmed* tables (34 confirmed, 0 refuted — unusually, every verified finding survived). Findings whose verifier never ran were recovered from the finder journals and listed under *Unverified* — treat them as credible leads, not established facts. The one critical was **verified manually in this session against the live API** before being written down.

**Session close-outs (same day, before the audit ran):** I4 closed (resolved by removal), I6 closed (moot — no async Lambdas), I14 closed (PROJECT_DOCUMENTATION.md fully refreshed), and the 21 stale legacy tests rewritten to current handler contracts (83 root + 62 backend tests green, both suites now gate CI).

### Same-day fix wave (2026-07-24, evening) — 18 findings closed

**Fixed in source AND covered by tests where applicable (152 tests green post-wave):**

- **Frontend (deployed to CloudFront):** I1 (sw.js `fresh.ok` guard), I2 (status.html: 5-min visibility-aware cadence, redundant re-fetch dropped — keyed calls fall from ~300/hr to ≤48/hr visible-only), I3 (score-demo renders `avgPriceUsd`/`avgPriceGbp` by presence; negative trends no longer render "+-"), I6 (in-sheet `.sheet-footer` shown ≤900px on web, overlay footer hidden there; native app excluded via `.is-native`; verified across 390/1440/native-sim), I7 (`#result-status` live region announces results + both not-found paths), I8 (persona buttons: `type` + `aria-pressed`, synced on change), I9 (privacy.html text orange → `#a04d00`, ~4.7:1), I10 (rankings toggle `--light` → `--dark`), M1 (dead EPC/landregistry hosts out of index.html CSP + sw.js; retired-service signup link replaced with an honest unavailable note), M2 (privacy.html strict CSP — the page is script-free), M3 (status.html CSP + skyscore.co.uk), M4 (sw VERSION → v1.0.1), M5 (methodologyUrl escaped).
- **Backend (source-only — deploys with the pending EPC-token/CORS `sam deploy`):** I4 (ScoreFunction timeout 10s → 28s), I5 (transport returns `available:false` on TfL failure; frontend renders "temporarily unavailable" instead of "No stations found"), M8 (transport 400s on non-numeric lat/lon), M9 (epc catches `TimeoutError`/`JSONDecodeError` → 504/502), M11 (weights must each be within [0,1]).

**Still open from this audit:** I11 (tooltip methodology link keyboard access), M6 (Math.random token fallback), M7 (GoatCounter SRI/self-host), M10 (LRU thread-safety), M12 (favourites schema validation), M13 (helper duplication), M14 (test docstring), M15-M18, and the entire Unverified list.

### Load-test addendum (2026-07-24, ~19:00 UTC — production, temp key, cleaned up after)

Method: temporary usage plan (100 rps / 200 burst / 200k quota) + key, ~63k requests against `/v1/score` + 40 × 100-query `/v1/score/batch` calls, then plan + key deleted (verified: only SkyScoreFreeTier remains).

- **A-0724-I4 CONFIRMED LIVE**: at 5 concurrent 100-query batches, warm instances answer in ~1.3-1.6s but every **cold** instance hits the deployed 10s Lambda timeout → APIGW 502, whole batch lost (9 of 15 calls in the concurrent phase, all at ~10.2s). Worse, timed-out instances recycle and re-cold-start, so they *keep* failing round after round. The 28s timeout fix already in source resolves this — **deploy it**.
- **NEW — A-0724-I12 (important): stage-wide throttle caps the whole API at ~5-6 successful req/s.** `MethodSettings` 10 rps / 20 burst is shared across ALL clients, overriding any usage-plan allowance (measured: a key on a 100-rps plan still got ~5.5 req/s of 200s; everything else 429'd). Fine for today's traffic; incompatible with the Professional promise the moment one integration bursts or two customers overlap. **Source-fixed same day: raised to 50/100** (per-plan throttles keep per-customer fairness; signup keeps its 1-rps override) — rides the pending `sam deploy`.
- **Healthy numbers**: single-score latency under sustained paced load p50 56ms / p99 83ms / max 189ms, 263/263 success; warm batch (100 queries) ~1.1-2.3s with zero row errors; one cold start observed at 3.3s.
- **M10 (LRU thread-safety) did not reproduce** under 5-way concurrent batch load — stays open as a lead, not upgraded.

### Critical — verified manually against production

| # | Issue | File:Line | Status |
|---|-------|-----------|--------|
| A-0724-C1 | **`CORS_ORIGIN` pinned to the legacy CloudFront URL breaks all five consumer data panels on the canonical domain.** `Globals.Function.Environment` sets `CORS_ORIGIN: 'https://d1oe4ftwutjpf.cloudfront.net'`; epc, favourites, nhs, sold_prices and transport echo it as `Access-Control-Allow-Origin`. The site has been canonical on `https://skyscore.co.uk` since May 2026 and `js/api-base.js` (verified live) calls the raw execute-api URL cross-origin — so browsers on skyscore.co.uk block every response (preflights pass because APIGW's MOCK OPTIONS returns `*`; the Lambda GET/POST responses then fail the origin check). Verified live 2026-07-24: `curl -H "Origin: https://skyscore.co.uk" .../prod/transport` → `Access-Control-Allow-Origin: https://d1oe4ftwutjpf.cloudfront.net`. Every affected panel degrades to its fallback/empty state ("No stations found…", EPC unavailable, favourites silently fail), which is why ~2 months passed unnoticed — testing happened on the CloudFront URL. The native app's WebView origin is likewise not the CloudFront domain. score (`'*'` override) and signup (own allow-list incl. skyscore.co.uk) were unaffected — which is precisely why the B2B demo kept working while the consumer site quietly lost its data panels. | `backend/template.yaml:12` | **Source-FIXED 2026-07-24** (Globals `CORS_ORIGIN: '*'`, matching the Api-level CORS declaration and the score override; signup keeps its stricter in-code allow-list). **DEPLOY PENDING — ride the same `sam deploy` as the EPC token rotation.** |

### Important — confirmed by adversarial verification

| # | Issue | File:Line | Category |
|---|-------|-----------|----------|
| A-0724-I1 | `sw.js` `networkFirst` caches responses without a `fresh.ok` check (unlike its own `cacheFirst`/`staleWhileRevalidate`) — a single CloudFront/S3 error page overwrites the last-good offline shell for that URL; every offline launch then serves the error page until a later good online load. Realistic here: this repo's own history includes PWA assets 403'ing for weeks. | `sw.js:115` | Cache poisoning |
| A-0724-I2 | `status.html` auto-refreshes every 60s, firing ~5 API-key'd calls/min on the shared demo key (4 endpoint checks + a redundant score re-fetch). The key's usage plan is 1,000 req/**month** — one tab left open ~3.3h exhausts it, 429-ing the public demo AND the status page for everyone until month reset; the status page then falsely shows 4/6 endpoints "down". Distinct from accepted C2 — rotation doesn't fix self-inflicted quota burn. | `score-demo/status.html:286` | Availability |
| A-0724-I3 | score-demo renders `£NaNK` for NYC results — currency/field contract drift between the score response shape and the demo's render(). | `score-demo/index.html:562` | Contract drift |
| A-0724-I4 | `/v1/score/batch` worst-case runtime exceeds the ScoreFunction's 10s timeout — the whole batch dies with no partial results, defeating the endpoint's documented partial-failure tolerance. | `backend/lambdas/score/app.py:68` | Reliability |
| A-0724-I5 | Transport Lambda swallows TfL upstream failures and returns an empty station list; the frontend then asserts "No stations found within 1.5km" — an outage renders as confident wrong data. | `backend/lambdas/transport/app.py:68` | Silent failure |
| A-0724-I6 | The site footer (Pricing, Privacy, For Developers, App Store link) is unreachable at every viewport ≤900px — the mobile web layout never exposes it, cutting mobile users off from the B2B funnel + legal pages the trust-fix bundle shipped. | `index.html:405` | A11y / funnel |
| A-0724-I7 | Search results and errors are never announced to screen readers (no live region on the result panel) — WCAG 4.1.3. | `index.html:6748` | A11y |
| A-0724-I8 | Persona picker buttons expose no pressed/selected state (no `aria-pressed`, no `type`) — SR users can't tell which persona is active. | `index.html:7528` | A11y |
| A-0724-I9 | privacy.html headings/links render orange at 2.11:1 contrast (WCAG AA needs 4.5:1). | `privacy.html:102` | A11y |
| A-0724-I10 | Rankings "Show boroughs/neighbourhoods" toggle is nearly invisible: `#c8c7c4` on white = 1.62:1. | `index.html:7608` | A11y |
| A-0724-I11 | The methodology link inside the score tooltip is keyboard-unreachable (tooltip hides when focus leaves the trigger). | `index.html:4768` | A11y |

### Minor — confirmed by adversarial verification

| # | Issue | File:Line |
|---|-------|-----------|
| A-0724-M1 | Stale `epc.opendatacommunities.org` **and** `landregistry.data.gov.uk` in CSP connect-src (all calls proxy via Lambda now) + same dead hosts in `sw.js:40-41` `NEVER_CACHE_ORIGINS` + a live user-facing signup link still points at the retired EPC service (`index.html:5875`). Found independently by 4 of 6 dimensions; M-0521-2 was never actually fixed. | `index.html:15`, `sw.js:40` |
| A-0724-M2 | privacy.html is the only page with no CSP meta (no frame-ancestors/script-src). | `privacy.html:6` |
| A-0724-M3 | status.html CSP connect-src omits `https://skyscore.co.uk` — two checks falsely report "down" when browsed on the canonical domain. | `score-demo/status.html:12` |
| A-0724-M4 | `js/api-base.js` is pinned in the SW shell cache with a never-bumped VERSION — an API base rotation never reaches installed PWAs. | `sw.js:31` |
| A-0724-M5 | score-demo renders API-response fields unescaped (methodologyUrl into href, persona/limits into HTML). | `score-demo/index.html:577` |
| A-0724-M6 | Device-token fallback path uses `Math.random` to mint a security capability token. | `index.html:7122` |
| A-0724-M7 | GoatCounter `count.js` from gc.zgo.at on 5 pages, no SRI, not self-hosted (same class as the fixed Swagger SPOF). | all pages |
| A-0724-M8 | Transport 500s (not 400) on non-numeric lat/lon — unguarded `float()`. | `transport/app.py:31` |
| A-0724-M9 | EPC handler misses `TimeoutError`/`JSONDecodeError` — upstream flakiness becomes a 500 instead of the graceful fallback. | `epc/app.py:101` |
| A-0724-M10 | Score LRU caches aren't thread-safe under the batch ThreadPoolExecutor — rare KeyError can 500 an entire batch. | `score/app.py:44` |
| A-0724-M11 | `parse_weights` accepts negative / >1 component weights as long as the sum is ~1. | `score/app.py:1444` |
| A-0724-M12 | Favourites POST forwards unvalidated body values into DynamoDB — type errors surface as 503. | `favourites/app.py:113` |
| A-0724-M13 | Triplicate `haversine` and 7× duplicated `response()`/CORS helper across Lambdas. | `score/app.py:1045` |
| A-0724-M14 | `backend/tests/test_handlers.py` docstring still describes 9 Lambdas + Bedrock 413 checks; `MagicMock` imported unused. | `backend/tests/test_handlers.py:1` |
| A-0724-M15 | score-demo API response region has no ARIA live region (the signup result does — inconsistent). | `score-demo/index.html:432` |
| A-0724-M16 | Favourites items + ranking table rows are click-only (not keyboard-operable). | `index.html:7240` |
| A-0724-M17 | Inputs at 14px trigger iOS Safari auto-zoom on focus. | `index.html:1070` |
| A-0724-M18 | npm audit: 3 high advisories, all dev-only transitive deps, fix available. | `package.json` |

### Status changes verified this audit

- **F-UX-11 (`prefers-reduced-motion`) — FIXED** on all four animating pages. ✅
- **N-Front-3/4 (modal focus trap + Escape) — OBSOLETE**: the modals no longer exist; close both. ✅
- **M-0521-2 (stale EPC CSP host) — NOT fixed** and wider than recorded → folded into A-0724-M1. 🔴
- **I-0521-5 (resize debounce) — NOT fixed** per the code-frontend finder (verifier didn't run) → listed under Unverified. 🔴

### Unverified findings (verifiers killed by the spend limit — credible leads, re-verify before acting)

**Important:** `/epc` route is an unauthenticated open proxy for the bearer-token MHCLG upstream (quota theft) (`epc/app.py:39`) · favourites POST stores schema-free, size-unbounded items under an unauthenticated device token (`favourites/app.py:113`) · infinite D3 transitions keep running on detached nodes after resize/city-switch (`index.html:7462`) · I-0521-5 resize debounce never landed — full D3 teardown per resize tick (`index.html:8089`) · search flow has no request sequencing — stale responses render another postcode's data (`index.html:7083`) · `switchCity` re-entrancy duplicates map layers / draws NYC boroughs on the London projection (`index.html:7354`) · SW cache-first + never-bumped VERSION strands installed PWAs on stale `js/api-base.js` (`sw.js:128`) · score verdict colours fail contrast badly on light theme (1.16–2.11:1) (`index.html:6734`).

**Minor:** postcode interpolated into postcodes.io URL path with `/` unescaped (`score/app.py:1374`) · non-string batch query values crash `resolve_query` → whole batch 500s (`score/app.py:1491`) · signup 409 leaks email-enumeration signal incl. `createdAt` (`signup/app.py:291`) · enabled orphan API key leaks if `create_usage_plan_key` fails post-creation (`signup/app.py:195`) · deploy-user IAM: region-wide APIGW write + leftover Bedrock grant (`iam-policy.json:79`) · batch counts 100 queries as 1 request against the 1000/month quota (`template.yaml:264`) · dead WMS/ArcGIS URL builders since the raster refactor (`index.html:5153`) · vestigial dead code: `_boroughExtraHydrated`, `getDeviceId` alias, unused zoom var (`index.html:7128`) · `escapeHtml` duplicated twice despite the global helper's comment (`index.html:7213`) · quicksearch chips double-bound after result-close → double search (`index.html:8166`) · score-demo example buttons clickable mid-request → out-of-order renders (`score-demo/index.html:490`) · borough-extra hydration can replace an open postcode result (`index.html:4871`) · duplicate `.search-hint` rule reverts the 11px a11y bump to 9px (`index.html:1118`).

### Priority fix order (updated after the same-day fix wave)

1. **Deploy the A-0724-C1 CORS fix + backend fixes I4/I5/M8/M9/M11** (all source-fixed; ride the EPC-token `sam deploy` — *user action*) ← the only blocking step
2. ~~I1+M4 (sw.js), I2 (status.html), I6 (footer), I3 (NYC render), I7-I10 a11y~~ — **DONE + deployed 2026-07-24**
3. Remaining a11y: I11 (tooltip keyboard access), M15-M17
4. Re-verify the Unverified list once the spend limit resets; then triage M6/M7/M10/M12/M13

---

## 2026-05-21 website audit (post App Store launch)

**Scope:** the live website + frontend — deploy parity (live vs source), security headers, `index.html`, `score-demo/*`, all 7 active Lambdas, `template.yaml`, `npm audit`. Two parallel agents (frontend/a11y + security) read live source, plus a deployment-parity sweep against `https://skyscore.co.uk`.

**Headline:** healthy. No Critical or new High-severity issues. The May-7 remediation waves genuinely landed (verified in source, not trusted from the triage column). The one real bug fixed this session was infrastructure, not code: the PWA was non-installable because its assets were never deployed.

### Critical
| # | Issue | File:Line | Category | Status |
|---|-------|-----------|----------|--------|
| C-0521-1 | PWA assets (`manifest.webmanifest`, `sw.js`, `icons/*`) returned 403 on the live origin — never in the deploy runbook, so the PWA was non-installable since Wave 13.1 and the install button silently no-op'd. | S3 origin / `CLAUDE.md` deploy block | Infra | **FIXED 2026-05-21** — uploaded all four + Wave 13.20 `index.html`, invalidated CloudFront, patched the runbook. Parity sweep now shows every local asset 200. |

### Important
| # | Issue | File:Line | Category |
|---|-------|-----------|----------|
| I-0521-1 | `saveFavourite` / `removeFavourite` never check `resp.ok` — optimistically mutate `userFavourites` and re-render even on 4xx/5xx, so the UI shows a favourite as "SAVED" the backend rejected (silent failure, real user impact). | `index.html:6741-6767` | Code / silent-failure | **FIXED 2026-05-21** — both now return a success boolean and only mutate state on `resp.ok`; `toggleFavourite` awaits the result and rolls the button back (flashes "FAILED") if the write didn't land. |
| I-0521-2 | `score-demo` `render()` assumes a perfect response shape (`d.components[key]`, `d.location.borough`, `d.score.toFixed`…); a partial 200 throws a `TypeError` surfaced as a misleading "Network error". | `score-demo/index.html:525-567` | Error handling |
| I-0521-3 | `score-demo` signup success assumes `data.limits.monthlyQuota` present; missing object throws *after* the one-time API key was shown, losing it. | `score-demo/index.html:637` | Error handling |
| I-0521-4 | `navigator.clipboard.writeText(...)` has no `.catch()` — silent unhandled rejection + dead "Copy" button in insecure contexts / on permission denial. | `score-demo/index.html:640` | Error handling |
| I-0521-5 | Map resize handler does a full D3 teardown+rebuild on every `resize` tick (no debounce) → layout thrashing on mobile URL-bar show/hide + orientation change. | `index.html:7657-7673` | Performance |
| I-0521-6 | Demo API key hardcoded in served HTML (known C2, risk-accepted; bounded to 1000 req/mo demo quota). Still a live scrape exposure. | `score-demo/index.html:443`, `score-demo/status.html:178` | Secret exposure (accepted) |

### Minor
| # | Issue | File:Line | Category |
|---|-------|-----------|----------|
| M-0521-1 | First-party curated note fields interpolated into `innerHTML` without `escapeHtml` — not exploitable (OGL data, not user input) but the one path bypassing the otherwise-universal escaping discipline. | `index.html:5318,5323,5328,5335,6448`; `score-demo/status.html:276-277` | Defence-in-depth |
| M-0521-2 | Stale `connect-src` entry `https://epc.opendatacommunities.org` in CSP — EPC moved server-side to MHCLG; browser never calls it directly. Over-permissive, not a hole. | `index.html:15` | CSP tidy |
| M-0521-3 | `lookupPostcode` calls `resp.json()` without `resp.ok` check (works because postcodes.io returns JSON on 404; inside try/catch so degrades safely). | `index.html:5051-5052` | Consistency |
| M-0521-4 | Response **headers** lack `Permissions-Policy`; HSTS lacks `includeSubDomains`/`preload`; CSP is delivered via `<meta>` not header. All hardening, not holes. | CloudFront response headers | Hardening |
| M-0521-5 | Residual inline `onclick` handlers (static values only, no XSS vector) inconsistent with the delegated-listener pattern adopted in audit I8. | `index.html:2176,2180,5295-5309,6382,7182` | Consistency |

### Verified-good (don't re-investigate)
- **Deploy parity:** every local asset `index.html` references now returns 200 live; all entry points (`/`, `/privacy`, `/score-demo/*`, `/prototype/`, `/.well-known/apple-app-site-association`, `robots.txt`, `sitemap.xml`) 200.
- **`npm audit`: 0 vulnerabilities.**
- **XSS:** all API/community strings route through `escapeHtml`/`escapeHtmlAttr`/`safeUrl` (scheme-restricted); the Bedrock chat XSS vector is gone (feature removed).
- **API security:** all 3 B2B routes API-key gated + per-route throttling; CORS locked to the CloudFront origin for favourites/epc/sold_prices/nhs (score `*` by design, key-gated); inputs `quote()`-encoded; no stack-trace leakage; no hardcoded secrets (EPC env-only).
- **Security headers present:** HSTS (1yr), X-Frame-Options SAMEORIGIN, X-Content-Type-Options nosniff, Referrer-Policy.
- **A11y/responsive:** combobox ARIA, roving-tabindex tablist, `aria-pressed` toggles, icon-button labels, skip-link, `prefers-reduced-motion`, `100dvh` iOS fix, iPad-portrait peek (the Guideline 4.0 fix) all confirmed solid.

### Process lesson
The prior report (line ~26 below) claimed *"PWA install path verified end-to-end… manifest reachable… SW registers"* via `tests/pwa-check.mjs`. That test ran against a **local** build, never the deployed origin — which is precisely why the 403s went unseen. **Smoke tests for deployed behaviour must hit the live URL, not localhost.** Recommend pointing `pwa-check.mjs` (or a CI step) at `https://skyscore.co.uk` so a missing-asset regression fails loudly.

### Summary
- Critical: 1 (fixed this session)
- Important: 6 (1 real silent-failure bug + 3 demo-page error-handling + 1 perf + 1 accepted)
- Minor: 5 (defence-in-depth / hardening / consistency)

---

## Wave 13 close — 2026-05-09 (mobile UX overhaul + PWA + native iOS/Android pipeline)

Mobile-first responsive refactor and PWA + native infrastructure shipped together. Eight new audit findings (F-A11Y-1..8) introduced and resolved within the same wave; five new mobile-related preflight gates pass clean.

**Closed in this wave (a11y / mobile):**

- **F-A11Y-1** (footer + small text below comfortable reading at phone viewing distance) — bumped 8px → 11px for `.site-footer` ≤768px (`letter-spacing` 1px → 0.6px); subtitle/dev-link 8px → 10px ≤480px. Desktop unchanged.
- **F-A11Y-2** (score colour as sole signal — WCAG 1.4.1) — added `scoreLabel(v)` returning `{glyph, word}` (▲/●/▼ + "Strong"/"Mixed"/"Weak"). Both `summary-verdict` renders + 2 ranking-table cell renders now show glyph + word + `aria-label` for screen readers ("Strong score: 7 out of 10 for Family buyer profile").
- **F-A11Y-3** (legend `display:none` ≤480px removed legend from a11y tree + blanked colour key on phones) — replaced with a tap-to-open chip pattern: `<button class="legend-toggle" aria-expanded>` flips state, CSS general-sibling rule `.legend-toggle[aria-expanded='false'] ~ *` hides every following row when collapsed. Legend stays in DOM/a11y tree throughout.
- **F-A11Y-4** (sidebar 45vh on phones squeezes search + tabs into ~270px) — bottom-sheet sidebar replaces the 55/45 vertical split. Two states: peek (220px showing handle + header + search-box + tabs) and open (88dvh). Auto-opens on result via `revealSheetIfMobile()`. Drag pill + `aria-controls`/`aria-expanded` for keyboard a11y.
- **F-A11Y-5** (layer-toggles vertical column on phones consumed ~50% of map width with no swipe affordance on resized desktop browsers) — collapsed behind a single `≡ Layers` disclosure trigger; popover anchored just above sheet peek; CSS sibling rule reveals when expanded; outside-click + Esc closes it.
- **F-A11Y-6** (heliport airport-code labels — ELS, DEN, KING, HEMS — clipped at narrow projection edges) — added `.heliport-label` class and `display:none` ≤600px. Dots remain visible.
- **F-A11Y-7** (subtitle "INDEPENDENT NOISE + LIVABILITY DATA" eats ~25px vertical at the title block on phones, decorative once H1 visible) — `display:none` at ≤480px. Removed from a11y tree intentionally; the H1 carries the title meaning.
- **F-A11Y-8** (sheet empty state shows blank panel under tabs — no discoverable starting point) — quick-search chips ("Try: SW11 1AA · Wandsworth · Camden · Hounslow") in `.empty-state`, role=group + aria-label, delegated `click` listener calls `triggerSearch`. Each chip ≥36px tap target (44px ≤900px).

**Closed in this wave (PWA / native infra)**:

- PWA install path verified end-to-end via `tests/pwa-check.mjs` (Playwright smoke). Manifest reachable at `/manifest.webmanifest`; service worker registers; install affordance markup present. Tested manually in Chrome desktop install flow.
- Capacitor 7.6.4 wraps the same `index.html` for iOS + Android. Native-only features (locate-me, share) feature-detected via `window.Capacitor.isNativePlatform()` — invisible on web/PWA.
- Codemagic CI verified at config level (`codemagic.yaml` parses, two workflows declared, build steps include `cap add ios`/`build:assets`/`xcode-project build-ipa`/`gradlew bundleRelease`). Cloud build itself awaiting user-side dashboard config.
- Asset pipeline verified end-to-end on Windows: 5 SVG sources → 136 Android variants + 7 PWA icons via `npx capacitor-assets generate`. iOS icons regenerated by Codemagic in cloud.

**Standing items (carried)**:
- I4 (borough metadata duplication across chat/multi_agent/score Lambdas) — not addressed
- I6 (no DLQ / retry config on async Lambdas) — not addressed
- I14 (stale `PROJECT_DOCUMENTATION.md` sections) — partial fix in Wave 13.5 (added Mobile / Native Apps section)

---

## Wave 12.6 + 12.7 close — 2026-05-07 late night (analytics gap fix + B2B funnel events + UTM convention)

**Wave 12.6 (analytics gap):** `score-demo/index.html` — the most B2B-relevant page on the site — had GoatCounter in its CSP allowlist but the actual tracker script was never added. Without it, we couldn't tell whether visitors who landed on `/` or `/api/` actually clicked through to try the API. One-line fix; tracker now consistent across `/`, `/api/`, `/score-demo/`, `/prototype/`. Deliberately untracked: `/score-demo/api-docs.html` (Swagger reference) + `/score-demo/status.html` (uptime page — won't-fix-by-design from Wave 12).

**Wave 12.7 (event tracking + UTM):** wired 8 GoatCounter custom events for the B2B conversion funnel:
- `event/api-demo-run` + `event/api-demo-error` (score-demo API call)
- `event/signup-attempted` + `event/signup-issued` (signup funnel; the gap = drop-off rate)
- `event/api-methodology-click` (real diligence signal)
- `event/api-licensing-click` (procurement signal)
- `event/api-demo-click` + `event/api-spec-click` (intent to integrate)

All events are guarded by a try/catch + presence-check so analytics never breaks the UI. Helper function pattern: `trackEvent(name)` calls `window.goatcounter.count({path: 'event/' + name, event: true})`.

UTM convention documented in `OUTREACH_DRAFTS.md` with a per-target slug table (landmark / tmgroup / onesearch / strideup / alrayan / etc.). Format: `?utm_source=outreach-{slug}&utm_medium={channel}&utm_campaign={YYYY-MM}`. GoatCounter logs the full referrer URL including query string, so the tags flow through automatically — no setup beyond using the right URL when sending. Visible in the dashboard's Referrers tab.

---

## Wave 12.5 close — 2026-05-07 late night (borough label contrast fix)

User flagged: clicking a borough made its name unreadable because the label fill (#141414) and the selected-borough fill (#141414) were identical. Previous code tried to swap the label colour at render-time based on `selectedBorough`, but the click handler never re-calls `renderLabels`, so labels stayed dark even after the fill went dark.

**Fix:** switched to single dark label colour with a white stroke halo via `paint-order: stroke` (same trick as airport code labels from Wave 7). Labels now read on ANY background colour without needing per-click updates. Opacity bumped 0.6 → 0.9 (halo handles contrast); font-weight 500 → 600.

Pattern reuse: this is now the third time `paint-order: stroke` has saved a contrast issue (airport codes Wave 7, heliport codes Wave 7, borough labels Wave 12.5). Worth remembering as the default contrast trick for SVG text over variable backgrounds.

---

## Wave 12.4 close — 2026-05-07 late night (in-map layer captions removed, legend group titles beefed up)

User flagged: when toggling road / flood / air-quality layers, the in-map SVG captions ("DEFRA ROAD NOISE BY BOROUGH" etc.) appeared beneath the LONDON/NYC city-selector buttons in the top-left corner. Two-part fix:

1. **Removed in-map SVG captions entirely** — they were redundant with the bottom-left HTML legend (which already gates a colour-keyed entry per toggled layer via `legend-{road,flood,aq}-group`). They also overlapped the SKY SCORE title.
2. **Beefed up legend group titles** for road / flood / AQ — font 8px `var(--mid)` → 10px `var(--dark)` bold, with source prefix: `DEFRA ROAD NOISE` / `EA FLOOD RISK` / `BOROUGH AIR QUALITY` (NYC: `DOT ROAD NOISE` / `FEMA FLOOD RISK` / `EPA BOROUGH AIR QUALITY`). Aircraft title now reads `DEFRA/BTS AIRCRAFT NOISE` for consistency.

Result: cleaner top-left corner, layer attribution lives in the canonical legend at bottom-left where users naturally look.

---

## Wave 12.1 + 12.2 + 12.3 close — 2026-05-07 late night (self-host DEFRA PNG + widen bbox + in-place explainer + legend max-width)

**Wave 12.3 (visual fix-DEFRA-7):** User flagged "the colour code box extends further and messes up the layout, not responsive anymore" — Wave 12.2's in-place explainer text expanded `.map-legend` (which had no max-width) across the bottom of the desktop map. One-line CSS fix: `max-width: 260px` so the prose wraps inside the legend container instead of stretching it. Mobile already had `display: none` on the legend so was unaffected.



After Wave 12 made the contours visible, user reported (a) renders with a lag, (b) noise cuts off at edges, and (c) asked whether the visual is real data. All three addressed:

**Wave 12.1 — Self-host DEFRA aircraft PNG (visual fix-DEFRA-5):** Measured DEFRA's GeoServer at **8.9 seconds** to render the WMS PNG on demand. Cached the PNG to `data/aircraft-noise-london-lden.png`, served from CloudFront edge (~86 ms cached). ~100× faster. Also added `<link rel="preload" as="image">` so the browser starts the fetch during HTML parse instead of waiting for JS. New `scripts/refresh_aircraft_noise.sh` documents the regeneration procedure for when DEFRA publishes Round 5 (expected 2027).

**Wave 12.2 — Widen bbox + in-place explainer (visual fix-DEFRA-6):** Bbox widened from (-0.55, 0.35, 51.25, 51.72) to (-0.85, 0.40, 51.10, 51.78):
- Old box clipped the western half of LHR's butterfly contour
- Old box missed LGW (Gatwick) entirely (its contour reaches Croydon/Sutton/Bromley)
- LCY eastern approach also now cleanly inside
- Stansted + Luton remain excluded (their Lden ≥55 dB contours don't reach inhabited Greater London)

PNG regenerated at 4096×2228 px (~21 m/px ground resolution). Added explainer in the legend itself: "DEFRA Strategic Noise Map (Round 4, 2022 data), the long-term average aircraft noise around LHR, LCY and LGW — modelled from a year of actual flight tracks, not a live feed. Used by councils for planning decisions."

**Costs:** PNG self-hosting adds ~37 KB to S3 storage (rounding-error money) and routes the bandwidth through our CloudFront. Trade-off: PNG is now stale until manually refreshed via `scripts/refresh_aircraft_noise.sh`. DEFRA noise mapping rounds run on a 5-year cadence (Round 4 2022, Round 5 expected 2027), so refresh frequency is "roughly never". Acceptable.

---

## Wave 12 close — 2026-05-07 late evening (DEFRA visibility recovery + Wave 12 polish + SEO)

**DEFRA visibility recovery (visual fix-DEFRA-2 / -3 / -4):** User reported "I don't see aircraft noise anymore" after the fix-DEFRA-1 single-fetch refactor. Root cause: at 2048 px source covering ~50 km, contour edges blurred when downscaled to viewport, AND opacity 0.6 compounded the PNG's own ~80% alpha to make bands invisible. Three combined fixes:
- Bumped raster source from 2048 px → 4096 px (~12.5 m/px ground resolution; PNG ~37 KB)
- Opacity 0.6 → 1.0 (let the PNG's own alpha do the work, no double-dimming)
- CSS `filter: saturate(1.6) brightness(0.92)` + `mix-blend-mode: multiply` to make contours pop against the basemap

**Audit residual closures (deferred → done):**
- M-E (status-page CSP omits Goatcounter) — investigated, intentional. Documented in inline comment that status page deliberately doesn't track ("we don't want analytics on the 'is the API up' surface"). Audit item closed as won't-fix-by-design.
- F-UX-8 (search dropdown not announced to SR users) — added `aria-live` status region (#autocomplete-status, role=status, .sr-only) updated in showAutocomplete + closeAcDropdown. Announces suggestion count with arrow-key hint.
- F-UX-9 (score-explain tooltip Esc dismiss + small-viewport overflow) — added `.score-tip-dismissed` class triggered by document-level keydown(Esc); `focusout` clears it for re-tab. Mobile (<= 600 px) gets `max-width: calc(100vw - 48px)` on the tip.
- I-N5 (API base URL drift across 4 files) — closed in two halves. **Wave 12.7/12.8 (defensive):** consolidated `BASE` + `SIGNUP_URL` → single `API_BASE` constant in score-demo/{index,status}.html, then added `/preflight` step 4d that grep-counts hosts across all HTML/JS files and fails if more than one distinct host found. **Wave 12.9 (offensive):** extracted the URL to `js/api-base.js` (single browser-side source of truth, loaded via `<script src=>` by index.html, score-demo/index.html, score-demo/status.html). `tests/api.test.mjs` keeps a duplicate constant because Node has no `window`; the drift check guarantees alignment.

**SEO basics (no audit ID — proactive):**
- `/robots.txt` — Allow: / for general crawlers; explicit Disallow: /data/ for bandwidth. AI training crawlers (GPTBot, anthropic-ai, ClaudeBot, CCBot) restricted from /data/ + /api/ pending licensing conversation.
- `/sitemap.xml` — 6 URLs (consumer site + /api + score-demo/{index,api-docs,status} + prototype) with priorities 1.0 → 0.5.
- `/api/` JSON-LD: Schema.org SoftwareApplication markup for Google Rich Results + LLM-driven discovery surfaces. Includes pricing tier + featureList + publisher Organization.

**Deferred (genuinely admin-only after Wave 12):**
- `cloudfront:CreateResponseHeadersPolicy` for Permissions-Policy + 2-year HSTS preload-eligible
- DDB PITR (root account IAM update)
- Cloudflare email-routing for `support@skyscore.co.uk`
- Status page on `status.skyscore.co.uk` (DNS + Better Stack)
- CSP report-uri token (sign up at report-uri.com)
- F-A11y-4 (heading hierarchy) — already addressed in Wave 10
- F-Perf-10 (inline data extraction) — already addressed in Wave 11
- Legal items: DPA, MSA, privacy notice, pen test, SOC 2, insurance — defer until first paying customer triggers contractual need

---

## Wave 11 close — 2026-05-07 late evening (CloudFront security headers live + F-Perf-10 inline data extraction)

**CloudFront response-headers policy applied to distribution `EGSSPJKLFL33M`** via the AWS-managed `SecurityHeadersPolicy` (id `67f7725c-6f97-4210-82d7-5512b31e9d03`). Verified live with `curl -sI https://skyscore.co.uk`:

```
Strict-Transport-Security: max-age=31536000
X-Frame-Options: SAMEORIGIN
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
X-XSS-Protection: 1; mode=block
```

This closes M-B (HSTS) outright at the 1-year value. The 2-year preload-eligible value would require a custom response-headers policy (root account perms — `cloudfront:CreateResponseHeadersPolicy` not in `flightmap-dev`'s allowlist). M-C (Permissions-Policy) is still deferred — also requires custom policy creation.

**F-Perf-10 (LCP):** `BOROUGH_EXTRA` (~503 lines) + `NYC_BOROUGH_EXTRA` (~85 lines) extracted from `index.html` to `/data/borough-extra.json`. Net effect:

- `index.html` shrunk from 7,178 lines / 309 KB to 6,593 lines / 275 KB (-585 lines, -34 KB / -11%)
- JSON is fetched in parallel with the geojson load and lazy-hydrates `BOROUGH_EXTRA` + `NYC_BOROUGH_EXTRA` (initially `{}`)
- After hydration, `recalcAllScores()` runs and any visible sidebar / ranking refreshes from default-5 scores to real data
- Trade-off: if a user clicks a borough in the first ~50-200ms before the fetch lands, they momentarily see default scores. In practice this is invisible because the geojson load is the slower of the two.

Cache headers: `Cache-Control: public, max-age=86400` on the JSON so subsequent visits hit the CDN directly. The data only changes when borough metadata is updated, which is roughly never.

---

## Wave 10 close — 2026-05-07 late evening (DEFRA + a11y + reduced motion + CloudFront docs)

**DEFRA noise visual fix (visual fix-DEFRA-1):**
- Pre-fetch the London aircraft raster ONCE at a fixed Greater-London bbox at 2048 px width.
- Position in g-coordinates via `projection()`; D3's zoom transform handles all subsequent scaling — no per-pan refetch.
- Eliminates the "swimming contour bands" the user flagged ("DEFRA all over the place").
- NYC slippy-tile path (XYZ) preserved unchanged — it genuinely needs per-pan refresh.
- Cache invalidated on city switch + window resize.

**A11y:**
- F-A11y-4 (real bug found): tab panels' `aria-labelledby` self-referenced (`tab-analysis` panel pointed to id `tab-analysis`). Fix: gave each tab button an explicit `id="tab-btn-X"` and updated all 3 panels' `aria-labelledby` to point at the buttons.
- F-UX-11: `prefers-reduced-motion: reduce` global guard added to all 5 HTML pages (index, prototype, score-demo/index, score-demo/status, api/index). Animations + transitions clamped to 0.001ms.

**Ops docs (CloudFront response-headers + CSP report-uri runbook):**
- `OPERATIONS.md` §3.2: HSTS + Permissions-Policy + Referrer-Policy via CloudFront response-headers policy (one-time admin setup, ~30 min).
- `OPERATIONS.md` §3.3: CSP report-uri via report-uri.com free tier OR custom Lambda (admin choice; ~5 min vs ~30 min).
- M-B (HSTS), M-C (Permissions-Policy), I-A (CSP report-uri) → moved from "deferred" to "documented as one-time admin tasks" — no further code-side work needed; just admin clicks.

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
| ~~I-N5~~ | ~~API base URL duplicated in 4 files~~ — **DONE in Wave 12.9.** Extracted to `js/api-base.js` (browser-side single source); `tests/api.test.mjs` keeps a duplicate (Node runtime), guarded by `/preflight` 4d drift check. | — | done |
| I-N6 | Signup race-recovery test (the `_safe_revoke_orphan_key` path with mocked `get_api_key` / `delete_api_key`) | Medium | ~20 min |
| ~~I4~~ | ~~Borough metadata Lambda layer~~ — **CLOSED 2026-07-24**: resolved by removal. The duplication was across chat/multi_agent/score; the first two left the working tree with the May pivot, leaving `score/app.py` as the single holder. A shared layer for one consumer is overhead. Re-open if a second Lambda ever needs borough metadata. | — | done |
| ~~I6~~ | ~~DLQ on async Lambdas~~ — **CLOSED 2026-07-24 as moot**: all 7 functions carry only `Type: Api` (synchronous proxy) events; zero async invocation paths exist, so DLQ/retry config has nothing to attach to. Re-open on the first async event source. | — | done |
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
| I4 | Borough metadata duplicated | ✅ Closed 2026-07-24 | Resolved by removal — chat/multi_agent left the tree in May; `score/app.py` is the single remaining holder |
| I5 | No tests for 9 of 11 Lambdas | 🟡 Partial | `eb2aa56` added handler tests; new `live_flights` + `signup` have none — see **N-Code-3** |
| I6 | No DLQ on async Lambdas | ✅ Closed 2026-07-24 (moot) | No async invocation paths exist — all 7 functions are APIGW-synchronous. Re-open on first async event source |
| I7 | `lru_cache` caches errors as None | ✅ Fixed | `e8992bb` |
| I8 | Inline onclick XSS | 🟡 Mostly fixed | Favourites delegated; static handlers (`closeReport`, `printReport`, `switchTab`, `switchCity`, `toggleMetricDetail`) still inline. **N-Sec-1**, **N-Sec-2** are the live exploitation paths |
| I9 | visibilitychange listener leak | ✅ Fixed | `e8992bb` |
| I10 | Touch targets <24×24 | ✅ Fixed | `5e7524d` |
| I11 | Layer toggles `<div role="button">` | ✅ Fixed | Native `<button>` + `aria-pressed` |
| I12 | Hardcoded URLs duplicated | 🔴 Still open | |
| I13 | Bedrock model IDs hardcoded | 🟡 Partial | Env vars added (`os.environ.get('NOVA_*_MODEL_ID', ...)`) but template never overrides — defaults still hardcoded in code |
| I14 | Stale `PROJECT_DOCUMENTATION.md` | ✅ Closed 2026-07-24 | Full refresh: 7-Lambda truth, real endpoint table (/v1/* was missing entirely), 3-table DynamoDB schema, 8.2k-line count, removed-AI sections marked historical, cost table de-Bedrocked |
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
- ~~**I4** shared borough Lambda layer~~ (closed 2026-07-24 — resolved by removal)
- ~~**I6** DLQ on async Lambdas~~ (closed 2026-07-24 — moot, no async Lambdas)

Standing items below remain on the backlog. Re-run `/audit` quarterly or before major releases.
