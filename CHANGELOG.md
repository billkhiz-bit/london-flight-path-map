# Changelog

Sky Score release history. API contract is stable (`/v1/*`); breaking changes deploy under `/v2/*`. Methodology versions are tracked separately in [`METHODOLOGY.md`](./METHODOLOGY.md#20-changelog).

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### 2026-07-26 (later) — Frontend batch deployed; DynamoDB tables made unloseable

- **Frontend batch is live.** `index.html`, `sw.js`, `js/api-base.js` and
  `score-demo/index.html` had all drifted from S3 — the 2026-07-25 commit was
  committed but never deployed, so the search-flow race (one postcode's EPC and
  sold-price data rendered under a *different* postcode's heading, a terminal
  state that never self-corrects) was live on skyscore.co.uk the whole time.
  Deployed with a 9-path CloudFront invalidation. Post-deploy gates: live web
  serves the CLASSIC layout at 360/390/414 with zero horizontal overflow
  (web/native split intact), live `index.html`/`sw.js` hash byte-identical to
  local, all 8 surfaces 200 with correct content-types, live API suite 5/5.
- **Ordering note for the `api.skyscore.co.uk` switchover.** The `sw.js`
  cache-first fix is now live, but service workers only update on navigation,
  so installed PWAs adopt it on their next visit. `js/api-base.js` still points
  at the raw execute-api URL, which keeps working regardless. Correct sequence:
  **sw.js live (done) → set the Cloudflare CNAME → only then repoint
  `api-base.js`.** Repointing early is what strands installed PWAs.
- **`DeletionPolicy: Retain` + `UpdateReplacePolicy: Retain` on all four
  DynamoDB tables.** This closes two interacting risks at once. `flightmap-dev`
  has no `dynamodb:DeleteTable` grant, so any rollback needing to delete a
  table would be *denied*, wedging the stack in `UPDATE_ROLLBACK_FAILED` with
  no self-recovery path; and the data itself was unprotected. `Retain` means
  CFN never attempts the delete, so the missing grant can never bite and the
  rows survive either way. Applied deliberately **before** the NSPL loader's
  first run — 2.7M rows is hours of loading to rebuild. All four tables updated
  in place, no replacement, no data disturbed (signups 1, favourites 14,
  noise-raster 423,481 all intact).
- **NSPL loader started.** Self-test green (BOM, 36-column header, 33-borough
  map, spaced-postcode invariant, sentinel rule), dry-run item shape verified,
  5,000-row real-write smoke test wrote 4,999 (1 unpositioned, correctly
  skipped). Full run in progress. Note `ItemCount` on a DynamoDB table refreshes
  only every ~6 hours — verify loads with `get-item`, not `describe-table`.

### 2026-07-26 — Backend deployed; signup funnel actually fixed (second IAM fault)

- **`POST /v1/signup` returns 201 again**, verified live. The funnel had been
  503'ing for every visitor since 2026-05-07. The 2026-07-25 statement split was
  correct but incomplete — there were **two stacked IAM faults**, and it fixed
  only the second one. The first: API Gateway treats tags as a **separate
  resource path** (`/tags/{arn}`; TagResource is `PUT /tags/{arn}`), so
  `create_api_key(tags={...})` requires a grant on
  `arn:aws:apigateway:*::/tags/*` that the audit I-G hardening never added.
  Denial therefore happened at `CreateApiKey`, before any key existed.
- **`backend/template.yaml`**: `SignupFunctionRole` gains `apigateway:PUT` +
  `apigateway:POST` on `arn:aws:apigateway:${AWS::Region}::/tags/*`, **keeping**
  the `aws:RequestTag/CreatedBy` condition — dropping it would let the Lambda
  tag any API Gateway resource in the account, a wider hole than I-G closed.
- **Deployed**: NSPL `PostcodeTable` created (ACTIVE, empty — the loader can run
  at any time, the score Lambda is forward-compatible); stage throttles applied
  (`/epc` GET 3/6 new, `/v1/score/batch` 5/10 → 10/20, `/v1/score` GET 40/80 now
  declared in source rather than surviving as console drift); CORS and the
  2026-07-24/25 fix waves are live. No resource replacements.
- **Known issue found, not fixed**: `lambdas/epc/app.py:62` branches on HTTP
  `401` to return the graceful "token invalid or expired" body, but MHCLG
  returns **`403`** for a rejected bearer token (confirmed against the live
  service). That branch is unreachable; an expired token will fall through to
  the generic `502` and break the property page instead of quietly hiding the
  EPC panel.

### 2026-07-25 — Test coverage for the local ONS NSPL postcode-resolution tier

- **`backend/tests/test_score.py` gained `PostcodeTableTests`** (19 tests) over
  the new local tier: the forward-compatibility guarantee (with
  `POSTCODE_TABLE` unset, no boto3 client is even constructed), the
  postcodes.io-shaped return contract, the DDB key format matching what
  `scripts/load_nspl.py` writes, deferral on every failure path (miss, unusable
  centroid, `ClientError`, terminated-without-opt-in), the non-London
  `admin_district = None` case and its byte-identical 404, the
  `?includeTerminated=true` response keys, the unchanged six-key `location`
  shape on live postcodes, and the two cache-leak guards (neither negative nor
  terminated results may be cached).
- **`tests/test_load_nspl.py` is new** (21 tests) over the loader's pure
  `_row_to_item` and its borough map — including the assertion that
  `LONDON_LAD_TO_BOROUGH`'s 33 names are byte-identical to the score Lambda's
  `LONDON_BOROUGHS` keys and each survives `normalise_borough` unchanged. A
  single typo there would 404 an entire borough with no postcodes.io rescue,
  because a local hit never falls back.
- **Loader fix found by those tests**: `_row_to_item` coerced coordinates under
  `except (KeyError, ValueError)`, but `csv.DictReader` yields `None` for a
  short row's trailing fields and `float(None)` raises `TypeError` — which
  would have escaped the row loop (deliberately bare-`except`-free per audit
  I-F) and killed a 40-minute run. Now `(KeyError, TypeError, ValueError)`,
  matching the Lambda's mirror-image guard.
- All fixtures are real rows from the on-disk ONS NSPL 2026-02 edition. No
  network, no AWS, no moto, no new dependencies. **199 tests green**
  (108 root + 91 backend), up from 159.

### 2026-07-24 (night) — Trends feature SHIPPED: ?compare=previous + /v1/changes + /changes page

- **`?compare=previous` on `/v1/score`**: any location rescored against the
  previous quarterly vintage under the current formula — `previousScore`,
  `scoreChange`, price movement. Works per-postcode (raster path included);
  NYC honestly reports zero change. In the `include` filter set.
- **`GET /v1/changes`** (public, keyless): all 33 boroughs'
  quarter-over-quarter movement, sorted by magnitude, with summary. This
  vintage: 6 risers, 25 fallers, 18 moved >0.5; largest fall Barking and
  Dagenham (9.0 → 7.4).
- **`/changes` page** ("What changed this quarter") renders it live, honesty
  note included; linked from both site footers. OpenAPI documents both.
  Deployed end-to-end and verified live.
- **Load harness** (`tests/loadtest.mjs`) gained per-request CSV persistence
  (`CSVFILE`) — demonstrated with a 1,736-request clean capture, every
  request a row (timestamp, status, latency). Gotcha for future runs: a
  freshly-created API key can 403 for ~20s while APIGW propagates — probe
  until 200 before starting a capture.

### 2026-07-24 (later) — Backend deployed · Methodology v3.2 (quarterly refresh + growth clamp) · 100k soak

- **Backend deployed** (user-directed): the CORS critical fix, 28s batch
  timeout, 50-rps stage throttle, and backend fix wave are LIVE. Verified:
  `Access-Control-Allow-Origin: *` from the skyscore.co.uk origin — the
  consumer data panels work again after ~2 months silently broken.
- **Methodology v3.2**: quarterly refresh check (per the published policy)
  found 28/33 boroughs ≥3% adrift from the 2026-Q1 snapshot; all 33
  borough prices/trends refreshed to May 2026 UK HPI in both engines. The
  refresh exposed an unclamped growth formula (negative trends → sub-zero
  scores); v3.2 clamps growth to 0–10. 18 borough scores move >0.5
  (balanced weights); no paying customers, changelog is the notice record.
  Public surfaces (footer, api sample, OpenAPI examples) bumped to 3.2.
- **100k-request production soak** run against the newly-raised limits with
  a temporary key (results in the stress-test workbook + AUDIT_REPORT).

### 2026-07-24 — Legacy test rewrite + full audit (1 live critical) + pilot outreach pack

- **Root `tests/` rewritten** to current handler contracts after 21 tests went
  stale against the May migrations: epc (MHCLG JSON API + `EPC_BEARER_TOKEN`),
  favourites (`X-Device-Token` auth — the old suite asserted the removed
  IDOR-era `userId` contract), nhs (OSM Overpass). 83 root + 62 backend tests
  green at the time; **CI now gates both suites** (`ci.yml`). (Current split:
  108 root + 91 backend = 199 — see the NSPL entry above.)
- **Audit items I4, I6, I14 closed** — I4 resolved by removal, I6 moot (no
  async Lambdas), I14 via a full `PROJECT_DOCUMENTATION.md` refresh (7-Lambda
  truth, real `/v1/*` endpoint table, 3-table DynamoDB schema, historical
  markers on the removed AI features).
- **Full audit** (6 dimensions, adversarially verified) → `AUDIT_REPORT.md`
  §2026-07-24. Headline: **A-0724-C1 (critical, verified live)** —
  `CORS_ORIGIN` pinned to the legacy CloudFront URL silently broke all five
  consumer data panels on skyscore.co.uk. **Source-fixed in `template.yaml`;
  deploys with the pending EPC-token `sam deploy`.** Plus 34 confirmed
  findings and 25 unverified leads (verification cut short by the account's
  monthly spend limit).
- **Outreach**: pilot-first email variants added to `OUTREACH_DRAFTS.md`;
  LOI template + one-pager maintained off-repo (Desktop) — the Haatch
  commercial-proof pack is complete.
- **Production load test (~63k requests, temp key, cleaned up):** single-score
  p50 56ms / p99 83ms at sustained load; **confirmed I4 live** (cold instances
  lose whole 100-query batches to the 10s timeout under concurrency — the 28s
  source fix is validated and waiting on deploy); **new finding A-0724-I12** —
  the stage-wide 10 rps throttle capped every key at ~5-6 req/s regardless of
  usage plan; raised to 50/100 in source (rides the same deploy). LRU race
  (M10) did not reproduce.
- **Pricing page:** pilot card now says the premium over 3× Professional buys
  the evidence (metric design, day-45/90 reviews, founder support), not the
  API calls. Deployed.
- **Same-day fix wave — 18 audit findings closed** (evening): sw.js cache
  poisoning + VERSION bump, status.html quota discipline (5-min
  visibility-aware checks), score-demo NYC currency render, in-sheet mobile
  footer (funnel/legal links finally reachable ≤900px on web), result
  announcements + persona `aria-pressed` + two contrast fixes, privacy.html
  strict CSP, dead CSP hosts removed. Backend (source-only, rides the pending
  `sam deploy`): transport honesty on TfL outages + 400 on bad input, epc
  timeout/JSON handling, batch timeout headroom, weight bounds. 152 tests
  green; e2e 16/16; layout harness clean on web/native/desktop.

### 2026-05-29 — Web/native split + iOS 1.0.21 submitted for review

- **Web/native split** (`3945226`): the mobile bottom-nav redesign is now
  native-app only, gated behind an `is-native` class on `<html>` (added by
  `setupNativeFeatures()` only inside Capacitor). The website (desktop + mobile
  browser + PWA) reverted to the classic bottom-sheet layout; the iOS/Android
  apps keep the redesign. Deployed to CloudFront + verified. See
  `MOBILE_REDESIGN_PLAN.md` v3.
- **Store copy** (`4af9bc5`): iOS "What's New" + Android changelog reworded from
  the v1 four-tab nav (Search/Map/Rankings/Saved) to the v2 three-tab,
  map-as-background design (Search/Rankings/Saved).
- **iOS `1.0.21` (build 21)** submitted for App Store review (2026-05-29) —
  native redesign, iPhone-only, built via Codemagic from `4af9bc5`. Screenshots
  at 1242×2688. Waiting for Review.

### Wave 13.1 → 13.5 — 2026-05-09 (mobile UX + PWA + native iOS/Android pipeline)

Five-part wave that takes Sky Score from "web-only" to "PWA + native iOS + native Android pipeline". 46 files / ~8,700 lines added across five focused commits.

- **13.1 — Mobile UX overhaul + PWA install** (`d7ac20d`): bottom-sheet sidebar replaces the 55/45 vertical split on phones (auto-opens on result; peek state shows search), Legend chip + Layers hamburger above the sheet (matched dark-pill styling), score chips gain non-colour signals (▲/●/▼ glyph + "Strong/Mixed/Weak" word + aria-label, WCAG 1.4.1), footer 8px → 11px on phones, subtitle hidden ≤480px, heliport labels (ELS/DEN/etc.) hidden ≤600px, empty-state quick-search chips. PWA wired up: `manifest.webmanifest` (light theme, scope `/`), two SVG icons (regular + maskable), Apple touch icon + iOS meta tags, `sw.js` (network-first shell, cache-first static, network-only API, stale-while-revalidate fonts), custom Install chip + iOS Add-to-Home-Screen hint, CSP `worker-src` and `manifest-src` directives, `tests/pwa-check.mjs` Playwright smoke test.
- **13.2 — Capacitor wrapper + Codemagic config** (`d2e2cad`): `mobile/` directory with isolated `package.json`, `capacitor.config.ts` (app id `uk.co.skyscore.app`), `scripts/copy-web.mjs` assembles `mobile/www/` from parent web app, 5 plugins bundled (app, geolocation, share, splash-screen, status-bar). Geolocation as the App Store Section 4.2 "Minimum Functionality" defence — "Score where I am" button. `codemagic.yaml` with two workflows (mac_mini_m2 for iOS, linux_x2 for Android) auto-publishing to TestFlight + Play Console internal track.
- **13.3 — Native-launch prep** (`a081090`): `mobile/STORE_LISTINGS.md` (paste-ready App Store + Play Store copy including descriptions, keywords, age rating, Data Safety form answers), `mobile/APPLE_REVIEW_NOTES.md` (Section 4.2 review-notes copy + escalation script if Apple rejects), `mobile/PRIVACY_POLICY.md` (GDPR-compliant draft for hosting at `/privacy`). Asset pipeline scaffolded: SVG sources in `mobile/assets/` + `@capacitor/assets` integration. README + CLAUDE.md updated to document the mobile workflow; SUBPROCESSORS.md adds api.postcodes.io, Codemagic, Apple App Store, Google Play as sub-processors #4-7.
- **13.4 — Asset pipeline verified + release checklist + privacy.html + launch blog draft** (`3a45e1c`): renamed `icon-source.svg` → `logo.svg` to match `@capacitor/assets` v3 conventions; cleaned XML comments (no `--` inside `<!-- -->` blocks). Verified 136 Android variants + 7 PWA icons generated from 5 SVG sources. Removed obsolete Playwright SVG→PNG step (capacitor-assets accepts SVG directly). `mobile/RELEASE_CHECKLIST.md` (9-step pre-release runbook), `mobile/LAUNCH_BLOG_POST.md` (announcement post draft + social excerpts + press hooks), `privacy.html` (live page for `/privacy` URL referenced in store listings). `codemagic.yaml` adds `build:assets` step. ROADMAP.md flips "native iOS/Android distribution" from open to in-flight.
- **13.5 — Deep-link stubs + outreach artefacts** (`d0bfcef`): `.well-known/apple-app-site-association` (iOS Universal Links manifest, TEAMID placeholder), `.well-known/assetlinks.json` (Android App Links, SHA-256 placeholder). `mobile/DEEP_LINKING.md` setup guide (where to find Team ID, how to extract keystore fingerprint, validation tools). OUTREACH_LOG.md gains the privacy URL + TBD entries for the iOS/Android apps.
- **13.7 — Android off Codemagic** (post-merge correction): user clarified that Noor's Android binary was built locally via Android Studio, not via Codemagic — only iOS went through Codemagic. Mirroring that pattern: dropped `android-workflow` from `codemagic.yaml` (iOS-only now), added `mobile/ANDROID_BUILD.md` documenting the Android Studio + gradle local build process, updated `CODEMAGIC_SETUP.md` and `RELEASE_CHECKLIST.md` to reflect the dual-path build (iOS cloud, Android local). Saves cloud-Linux build minutes; faster Android feedback loop on Windows. The Capacitor-generated `mobile/android/` project itself is unchanged — only the CI strategy differs.
- **13.8 — CLI release pipeline (Makefile + fastlane)**: three-layer CLI ergonomics on top of the deploy/build commands. Layer 1: `Makefile` at repo root with one-word targets for every common op (`make help` lists them all). Layer 2: `package.json` npm-script aliases for the most common ops (work without GNU Make installed). Layer 3: `mobile/fastlane/` with Fastfile (5 Android lanes + 3 iOS lanes), Appfile, Gemfile (pins fastlane ~> 2.222), and ready-to-paste store listing metadata for both stores in `metadata/{android,ios}/en-GB/`. Bug fix in `mobile/.gitignore`: anchored `ios/` and `android/` patterns with leading `/` so `mobile/fastlane/metadata/{android,ios}/` weren't accidentally ignored.
- **13.8.1 — fastlane verified working** (post-merge): user successfully installed Ruby 3.3 + bundler + fastlane via `bundle install` on Windows. `bundle exec fastlane lanes` outputs all 8 lanes cleanly. UTF-8 locale env vars (`LANG`, `LC_ALL`) set permanently to suppress fastlane's locale warning; rocket emoji renders correctly which confirms UTF-8 round-trip is working. `mobile/Gemfile.lock` committed (Bundler convention for application-level repos — locks gem versions across machines + Codemagic cloud builds for reproducible installs).
- **13.8.2 — fastlane env vars documented in `.env.example`** (`c3c506e`): names match what `Fastfile` reads: `PLAY_CONSOLE_JSON_KEY`, `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_KEY_FILE_PATH`, optional `ANDROID_AAB_PATH`. Comments point at the exact console pages where each secret is generated, and recommend storing `.p8` / JSON files outside the repo (`~/.secrets/`) so a stray `git add -f` can't leak them.
- **13.8.3 — fix iOS metadata_path + protect README** (`0a26ca3`): two bugs caught on the first iOS lane run. (1) iOS `deliver` expects metadata at `fastlane/metadata/<locale>/` not `fastlane/metadata/ios/<locale>/` — fixed by passing `metadata_path: './fastlane/metadata/ios'` explicitly on every iOS lane (and matching `screenshots_path`). Android `supply` and iOS `deliver` disagree on the platform-subdirectory convention. (2) fastlane silently overwrites `mobile/fastlane/README.md` with its auto-generated lane listing after every run — fixed by setting `FASTLANE_SKIP_DOCS=1` in `.env` and documenting in `.env.example`.
- **13.8.4 — first successful metadata push** (`e3c7780`): confirmed end-to-end metadata push works after the 13.8.3 fixes plus three further small adjustments. (1) Added `precheck_include_in_app_purchases: false` because precheck's IAP scan requires interactive Apple ID login (not API key) — irrelevant for Sky Score (no IAP). (2) Added `mobile/fastlane/metadata/ios/copyright.txt` ("© 2026 Bilal Khizar") — app-level metadata, not locale-scoped. (3) Deployed `privacy.html` to S3 as `privacy/index.html` (extensionless URL pattern, due to the `sky-score-rewrite-index` CloudFront Function that appends `/index.html` to clean URLs) — was missing since Wave 13.4 despite the file existing in the repo. Both fastlane precheck warnings now pass.
- **13.8.5 — App Review Notes auto-pushed via fastlane**: moved the Section 4.2 review-notes copy from `mobile/APPLE_REVIEW_NOTES.md` (manual paste) into `mobile/fastlane/metadata/ios/review_information/notes.txt` (auto-pushed by every `metadata_only` or `submit_for_review` run). `APPLE_REVIEW_NOTES.md` retained as runbook documentation (rejection counter-arguments, "what NOT to include") but flagged as no longer the canonical source. `mobile/RELEASE_CHECKLIST.md` step 8 updated to reflect the auto-push.
- **13.8.6 — Apple Team ID resolved + AASA deployed for Universal Links** (`096c262`): retrieved Apple Team ID (`L3UXT79KFZ`) via Spaceship API (`BundleId#seed_id`) — automatable, not the manual developer.apple.com → Membership Details lookup the docs suggest. Updated `.well-known/apple-app-site-association` to use the real Team ID, deployed to S3 with `Content-Type: application/json`, invalidated CloudFront. Live at `https://skyscore.co.uk/.well-known/apple-app-site-association`. iOS Universal Links infrastructure now active — once Sky Score is installed via TestFlight, tapping any `skyscore.co.uk/*` link on iPhone routes to the app. Android assetlinks.json half still pending the release keystore SHA-256 (waits for first Android Studio build).
- **13.8.7 → 13.8.12 — Codemagic iOS signing arc** (6 commits, 1 working binary): wrestling Codemagic's Personal Account signing model into submission for Sky Score. The story:
  - **13.8.7** (`0a26ca3`): added explicit `keychain initialize` + `app-store-connect fetch-signing-files --create` steps so `xcode-project use-profiles` can find profiles on disk. Build failed.
  - **13.8.8** (`1b2ba87`): removed `integrations.app_store_connect: codemagic_asc` since Personal Accounts don't have named integrations. Yaml validation immediately failed because `publishing.auth: integration` requires the block.
  - **13.8.9** (`5d66ba0`): restored `integrations:` but pointed at the actual key label `"Sky Score Fastlane"` instead of the placeholder `codemagic_asc`. Build still failed identically.
  - **13.8.10** (`d618eff`): switched `publishing` block from `auth: integration` to explicit env vars (`api_key: $APP_STORE_CONNECT_PRIVATE_KEY` etc.) — bypasses the integration name lookup entirely. Build still failed (env vars existed in dashboard but yaml didn't import the group).
  - **13.8.11** (`00a74ab`): single-line fix — added `environment.groups: [asc]` so the workflow imports the dashboard env vars. Build still failed identically because Codemagic's pre-flight signing check runs BEFORE scripts and uses the Apple Developer Portal pool's auto-selected key (Noor's, alphabetically first), not the env vars.
  - **13.8.12** (`69e14e8`): removed the `environment.ios_signing` block entirely to disable pre-flight signing. Signing now happens exclusively in scripts (`keychain initialize` → `app-store-connect fetch-signing-files` with env-var credentials → `keychain add-certificates`). **Build progressed past the signing wall for the first time** — through 8 stages, ~30 seconds in. Confirmed env vars correctly populated by the build log printing `APP_STORE_CONNECT_*` values from the imported `asc` group.
- **13.8.13 — Node version syntax fix** (`755b73e`): build past pre-flight failed at `> n 20.x` with "Unable to install Node version 20.x". Codemagic's `n` version manager rejects `.x` wildcards — must be bare major (`20`) or fully-specified version (`20.10.0`). One-line yaml fix.
- **13.8.14 — Pass `--certificate-key-path` to fetch-signing-files** (`9f597b0`): next-stage failure was "Cannot save Signing Certificates without certificate private key" — Codemagic CLI needs a private key path to either match an existing Distribution cert OR create a new one. Generate fresh RSA-2048 key on the build VM, pass via `--certificate-key-path` to both `fetch-signing-files --create` and `keychain add-certificates`. Caveat: creates a new cert per build, eating Apple's 2-cert team limit. Future: persist key as Codemagic env var for cert reuse.

**Why split from earlier waves**: native binaries have a different release cadence (TestFlight + Play review cycles, ~2–3 days vs minutes for CloudFront). Keeping them in a sibling `mobile/` directory means web deploys stay unaffected and we can iterate on either independently. The web app, the PWA, and both native apps run from the **same `index.html`** — feature-detected via `window.Capacitor.isNativePlatform()` for native-only UI.

**Still required (user-side, not committable)**: ASC API key + Bundle ID registration (done 2026-05-10), App Store Connect "Sky Score" app record creation (done 2026-05-10), real Apple Team ID + keystore fingerprint to replace the `.well-known/` placeholders, first iOS Codemagic build trigger, first iOS screenshots manually uploaded to ASC, first iOS submit_for_review, first Android Studio local build + Play Console listing.

### Wave 12.10 — 2026-05-08 (persona rename: `downsizer` → `laterlife`)

**Breaking API change.** The `persona` enum value `downsizer` is removed; the equivalent persona is now `laterlife` with identical weights (quiet 0.40 / afford 0.15 / growth 0.10 / live 0.35). User-facing label changes from "Downsizer" to "Later life".

**Why:** the term "downsizer" reads as faintly diminishing of older buyers when the persona is really about prioritising quiet and healthcare access, not about reducing one's life. "Later life" is the framing used in BBC/healthcare/policy contexts and matches the persona's actual function.

**Customer impact:** zero paying B2B customers at time of change, so the breaking shape is acceptable without a `/v2` path bump. Anyone passing `?persona=downsizer` will now receive a normal "invalid persona" 400 response. The free-tier demo key holders (one active, ~75 calls historical) will not have hit this code path.

**Files touched:** `backend/lambdas/score/app.py` (key + comment), `backend/tests/test_score.py` (fixture + new regression test asserting `downsizer` is gone), `index.html` (persona definition + label), `score-demo/index.html` (dropdown + label map), `score-demo/openapi.yaml` (enum), `METHODOLOGY.md` (persona table — also expanded from 5 to the actual 8 entries; the table had drifted away from `app.py` in an earlier wave), `PROJECT_DOCUMENTATION.md` (persona list).

### Wave 12.8 + 12.9 — 2026-05-08 (I-N5 closure: API URL drift defence + extraction)

Two-half close on the long-running I-N5 audit item (API base URL duplicated across files).

- **12.8 (defensive half):** added step 4d to `/preflight` — greps every HTML/JS/test file for `execute-api` hosts and fails the build if more than one distinct host appears. Catches drift at commit time before it ships, regardless of why the URLs diverged (manual edit, partial deploy, stale clone).
- **12.9 (offensive half):** extracted the URL to `js/api-base.js` — a 1-line classic script that sets `window.API_BASE`. The 3 browser pages (`index.html`, `score-demo/index.html`, `score-demo/status.html`) now load it via `<script src>` and pull the value from `window.API_BASE`. The 4 hardcoded constants collapsed to 2 (one in the shared script, one in `tests/api.test.mjs` which can't read `window`); the test duplicate stays guarded by the 12.8 drift check. Deploy commands in `CLAUDE.md` updated; `js/api-base.js` joins the S3 frontend bundle.

Net: rotating the API host now requires editing 2 files instead of 4, and the drift check is a hard guarantee they stay aligned. The prior "keep in sync with X, Y, Z" comments are now redundant and were trimmed.

### Wave 12.6 + 12.7 closure — 2026-05-07 late night (analytics gap + funnel events + UTM convention)

- **12.6:** added missing GoatCounter tracker to `score-demo/index.html` (the API browser demo). CSP allowlist had it, but the script tag was never added — the most B2B-relevant page wasn't being counted.
- **12.7:** wired 8 funnel events (`api-demo-run/error`, `signup-attempted/issued`, `api-{methodology,licensing,demo,spec}-click`) for B2B conversion measurement. UTM convention documented in `OUTREACH_DRAFTS.md` — per-target slug table for cold-email attribution.

### Wave 12.5 closure — 2026-05-07 late night (borough label contrast)

User flagged that clicking a borough made its name unreadable (label and fill both #141414). Switched borough labels to dark fill + white stroke halo via `paint-order: stroke` so they read on any background — same trick used for airport/heliport codes earlier.

### Wave 12.4 closure — 2026-05-07 late night (in-map layer captions removed, legend group titles beefed up)

User flagged the in-map SVG captions (DEFRA ROAD NOISE BY BOROUGH etc.) overlapped the LONDON/NYC city-selector buttons in the top-left. Removed them entirely (the bottom-left HTML legend already handles attribution per toggled layer) and bumped the legend group titles from 8px mid-grey to 10px bold dark with source prefixes (DEFRA ROAD NOISE / EA FLOOD RISK / BOROUGH AIR QUALITY for London; DOT / FEMA / EPA equivalents for NYC).

### Wave 12.1 + 12.2 + 12.3 closure — 2026-05-07 late night (self-host DEFRA PNG + widen bbox + explainer + legend layout fix)

**Wave 12.3:** added a one-line `max-width: 260px` to `.map-legend` because the in-place explainer text from 12.2 had stretched the legend container across the bottom of the desktop map. Mobile already hides the legend < 768 px.



User reported the contours render with a lag, cut off at edges, and asked whether the visual is real data. All three addressed:

**Wave 12.1 — Self-host the DEFRA WMS PNG.** Measured DEFRA's GeoServer at 8.9 s to render the request. Cached the PNG to `/data/aircraft-noise-london-lden.png`, served from CloudFront edge (86 ms cached, ~100× faster). Added `<link rel="preload" as="image">` so the fetch starts during HTML parse. New `scripts/refresh_aircraft_noise.sh` for the next DEFRA publication round (~2027).

**Wave 12.2 — Widen bbox + in-place explainer.** Bbox now -0.85..0.40 lon, 51.10..51.78 lat — covers the full LHR butterfly contour, LCY approach, and LGW (was missing). Stansted + Luton still excluded (don't reach inhabited Greater London). New PNG at 4096×2228 (~21 m/px). Legend now reads "DEFRA Strategic Noise Map (Round 4, 2022 data), the long-term average aircraft noise around LHR, LCY and LGW — modelled from a year of actual flight tracks, not a live feed."

### Wave 12 closure — 2026-05-07 late evening (DEFRA visibility recovery + a11y + I-N5 + SEO)

**DEFRA visibility recovery:** user reported "I don't see aircraft noise anymore" after the Wave 10 single-fetch refactor. Three combined fixes:
- Raster source 2048 → 4096 px (~12.5 m/px ground resolution)
- Opacity 0.6 → 1.0 (PNG alpha already handles translucency)
- CSS `filter: saturate(1.6) brightness(0.92)` + `mix-blend-mode: multiply`

**Audit residual closures:**
- F-UX-8: `aria-live` status region announces autocomplete suggestion count to SR users
- F-UX-9: Esc dismisses the score-explain tooltip; mobile gets max-width to prevent overflow
- I-N5: API_BASE consolidated within each file; `/preflight` grep-checks for drift
- M-E: status-page CSP intentionally omits Goatcounter (no analytics on uptime page) — documented as won't-fix-by-design

**SEO basics:**
- `/robots.txt`: general crawlers allowed; AI training crawlers (GPTBot, anthropic-ai, ClaudeBot, CCBot) restricted from /data/ + /api/
- `/sitemap.xml`: 6 URLs covering consumer site, /api, score-demo, prototype
- `/api/` JSON-LD: Schema.org SoftwareApplication for Google Rich Results + LLM-driven discovery

### Wave 11 closure — 2026-05-07 late evening (CloudFront security headers + F-Perf-10)

**HSTS + 4 other security headers now live** on `https://skyscore.co.uk` via AWS-managed CloudFront `SecurityHeadersPolicy`. Verified by curl:
```
Strict-Transport-Security: max-age=31536000
X-Frame-Options: SAMEORIGIN
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
X-XSS-Protection: 1; mode=block
```
M-B closed at 1-year HSTS. Permissions-Policy + 2-year preload-eligible HSTS still need a custom CloudFront policy (root-account perms).

**F-Perf-10:** `BOROUGH_EXTRA` (503 lines, London) + `NYC_BOROUGH_EXTRA` (85 lines) extracted from `index.html` to `/data/borough-extra.json`. Lazy-fetched in parallel with geojson load; sidebar rescore on hydration.

- index.html: 7,178 → 6,593 lines, 309 KB → 275 KB (-11%)
- JSON: 28.7 KB, served with 24-hour browser cache
- Initial paint no longer waits for borough-metadata parse; LCP improvement scales with parser-blocked time on slower devices.

### Wave 10 closure — 2026-05-07 late evening (DEFRA fix + a11y + reduced motion + ops docs)

User flagged the DEFRA noise overlay looked "all over the place" — root cause was per-pan WMS re-fetch causing the contour bands to "swim" as each new viewport rendered slightly differently. Fixed by pre-fetching once at a fixed Greater-London bbox (2048 px) and positioning the raster in g-coordinates so D3's zoom transform scales it natively.

Also closed:
- **F-A11y-4 (real bug):** tab panels had `aria-labelledby` self-referencing their own ids — gave each tab button `id="tab-btn-X"` and pointed panels at the buttons.
- **F-UX-11:** `prefers-reduced-motion: reduce` global guard added to all 5 HTML pages.
- **OPERATIONS.md §3.2 + §3.3:** documented HSTS/Permissions-Policy CloudFront setup + CSP report-uri runbook (M-B, M-C, I-A — moved from deferred to one-time admin tasks).

### Wave 7+8+9 closure — 2026-05-07 late evening

Three more focused waves shipped after the main session-close:

**Wave 7 (visual polish, commit `0d634b1`):**
- Per-layer indicator dot colours on `.layer-toggle.active` (matches the layer's actual map colour — paths/aircraft/road/transport/flood/AQ/labels)
- DEFRA caption stagger so road/flood/AQ labels don't overlap when multiple borough overlays toggled together
- Airport-code text gets a white halo via `paint-order: stroke`

**Wave 8 (code quality, commit `f91935d`):**
- `BOROUGH_ALIASES` expanded from 4 to ~25 entries — covers Royal Borough / London Borough / ampersand / common spelling variants postcodes.io and partner address data return
- New end-to-end signup race-recovery test — proves the orphan key is revoked and the secret value is not echoed back to the loser of the race

**Wave 9 (enterprise no-legal items, this commit):**
- `OPERATIONS.md` runbook (production topology, deploys, one-time admin actions, DR, monitoring, debugging, cost profile)
- `SUBPROCESSORS.md` register (3 sub-processors: AWS, Cloudflare, GoatCounter — explicit "tools we don't use" list for procurement)
- `SUPPORT.md` (contact channels, response targets, planned `support@` + `status.skyscore.co.uk`)
- DynamoDB PITR enabled in `template.yaml` for all 3 tables (signups, noise-raster, favourites). **Deploy gated** on one-time IAM policy update at root account — see OPERATIONS.md §3.1.
- `pip-audit` integrated into `/preflight` skill — PyPI Advisory Database vuln scan per Lambda's `requirements.txt`; CVSS ≥ 7.0 blocks commit

### Planned (deferred from 2026-05-07 session)

- See [`AUDIT_REPORT.md`](./AUDIT_REPORT.md#deferred--kept-in-mind-for-future-sessions) for the full deferred list with audit IDs, priorities, and time estimates. Top items:
  - Layer-toggle hover vs active visual differentiation (a11y critical)
  - Heading hierarchy fix in injected sidebar HTML (a11y critical)
  - Touch targets <44px on consumer site (`.layer-toggle` 32px; `.persona-btn` ~25px; `.fav-btn` ~22px)
  - Skip-to-content link
  - CSP `report-uri` endpoint + `img-src` tightening
  - Per-route throttle on `/v1/score` to prevent one tenant starving others
  - hCaptcha on `/v1/signup`
  - HSTS + `Permissions-Policy` via CloudFront response-headers policy
  - DPA + MSA templates (CommonPaper) — needs legal review
  - Privacy notice + sub-processor list + retention policy (`/privacy`, `SUBPROCESSORS.md`, `OPERATIONS.md`)
  - DynamoDB PITR + documented RTO/RPO
  - Status page on `status.skyscore.co.uk` subdomain
  - `pip-audit` integration into `/preflight`
  - Extract inline `BOROUGH_DATA` / `AREA_MAP` from index.html (6.9k lines) to JSON for LCP improvement
  - DEFRA Lden raster data load completion (in flight 2026-05-07; loader at NSPL row ~2.3M of ~2.5M)

### Original [Unreleased] planned items

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

## [Consumer rebrand + security + audit-driven hardening] 2026-05-07

The longest-running session in the project's history. Two parts:
1. **Morning/afternoon (32 commits, 3 backend deploys, 5 frontend deploys):** removed all AI features from the consumer site, removed OpenSky-backed live-aircraft pending licensing, hardened the signup endpoint, fixed DOM-XSS surfaces, trimmed flight-path polylines to noise-relevant portions, refreshed every relevant doc.
2. **Evening (13 further commits, 4 more backend deploys, 6 more frontend deploys):** ran two rounds of 3-5 parallel audit agents (code, security, frontend visual + a11y, enterprise readiness), closed the highest-leverage agent findings, deployed CSP enforcing on all 5 HTML pages, added `/.well-known/security.txt`, `SECURITY.md` security one-pager, `/api` landing page, `OUTREACH_DRAFTS.md`, `AVIATIONSTACK_SPIKE.md`, `AWS_BILLING_ALARM_SETUP.md`. Then deleted the 5 dormant Bedrock Lambda directories entirely + their IAM grants.

Total: ~45 commits, 7 backend deploys, 11 frontend deploys.

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
- **Demo API key exposure (audit C2)** accepted with rotation discipline rather than building a server-side proxy. Blast radius bounded by 1000 req/month quota; rotation = 5 minutes. Re-evaluate if a paying customer ever depends on the demo working specifically.
- **Dormant Bedrock Lambda directories deleted entirely (2026-05-07 evening)**: revised the prior "keep dormant" decision after the smoke-test caught the routes were still publicly invokable. "Uncomment Events block to re-enable" wasn't materially easier than "git revert + sam deploy", and 5 Lambdas with intact `bedrock:InvokeModel` grants were attack surface for any future SAM template typo. Restoration recipe: git revert this commit + the 2026-05-05 AI-removal commit (commit `69905ee`).

### Evening additions (post-CHANGELOG-write commits)

- **Two rounds of 3-5 parallel audit agents** (code, security, frontend visual + a11y, enterprise readiness). Findings merged in commits `dab713d` (post-audit security fixes), `6bad8ce` (Wave 1: code quality), `a830acb` (Wave 2: visual polish), `b6c7806` (Wave 3: SECURITY.md), `54191df` (Wave 4: a11y criticals).
- **CSP enforcing** on all 5 HTML pages (commit `967f9d1`); was Report-Only earlier in the day. Then `unsafe-eval` dropped (commit `dab713d`) — codebase has no `eval`/`new Function`, so it was free attack-surface widening.
- **`SECURITY.md` security one-pager** (commit `b6c7806`) closes enterprise gap #4 — pre-empts the SOC 2 question by listing controls actually in place + an honest "what we don't have" table.
- **`/api` landing page** at `https://skyscore.co.uk/api/` (commit `88b56a4`) closes enterprise gap #19 (B2B prospects had no buy-path discovery surface). Hero CTA → demo / reference / methodology, "Built for" target-audience cards, indicative pricing tiers, 5-step "Get started" path.
- **`OUTREACH_DRAFTS.md`** (commit `2024147`) — warm-intro DM template + Tier 1 / 2 cold-email templates with per-target tweaks for Landmark / TM Group / OneSearch Direct / Al Rayan / StrideUp / Gatehouse / Nester / Yielders. Subject-line A/B options.
- **`AVIATIONSTACK_SPIKE.md`** (commit `2024147`) — fallback live-aircraft provider reference; ~3-hour swap if OpenSky says no.
- **`AWS_BILLING_ALARM_SETUP.md`** (commit `445c59d`) — one-time admin runbook for $20 USD billing alarm; would have caught today's "AI Lambda routes left open" defect within hours.
- **6 new signup tests** (commit `2024147`): CORS allow-list (echoed origin / hostile origin / no-origin / lowercase header) + `_safe_revoke_orphan_key` prefix guard (refuses non-prefix names; deletes legitimate prefix). Backend tests 61 → 67 then back to 60 after dormant-Lambda test classes deleted.
- **Visual polish on map**: road overlay `mix-blend-mode: multiply` so it tints aircraft raster instead of covering it; legend "LCY/OTHER" → "LCY PATHS"; flight-path strokes 1/1.5px @ 0.5 → 1.5/2.25px @ 0.7; heliport colour orange → violet (was identical to LHR orange); animated dot halo for visibility over noise rasters.
- **Search input** now implements the WAI-ARIA combobox pattern (`role="combobox"`, `aria-expanded`, `aria-controls`, `aria-autocomplete`, `aria-activedescendant`); each `.autocomplete-item` is a `role="option"` with stable id + `aria-selected`; new `closeAcDropdown()` helper centralises 5 dismiss paths so screen readers stay in sync.
- **ADDITIONAL INSIGHTS metric cards** converted from `<div onclick>` to native `<button>` with `aria-expanded` / `aria-controls`; toggle handler synchronises the ARIA state.
- **Dropped 5 dormant Bedrock Lambda directories + their IAM grants** (commit `6bad8ce`). Net ~800 LOC removed from backend; 5 fewer execution roles with `bedrock:InvokeModel` permissions.
- **`live_flights` Lambda removed** earlier in the day (commit `6f6ce7d`); the `liveLicensed=false` gate in `prototype/index.html` strengthened to `throw` on flag flip with a message pointing to `OPENSKY_LICENSING_EMAIL.md` (commit `6bad8ce`).
- **Enterprise audit doc gap fix**: METHODOLOGY §15 said "AWS is the sole sub-processor" but LICENSING.md listed Cloudflare. Reconciled (commit `6bad8ce`).
- **OpenSky licensing enquiry sent** to `contact@opensky-network.org` — Ticket #835285 acknowledged via auto-reply; chase 2026-06-04.

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
