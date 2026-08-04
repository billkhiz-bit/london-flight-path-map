# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Compact Instructions

When context fills up, always preserve:
- AWS deployment details (API URL, CloudFront ID, S3 bucket, region)
- The current task the user is working on
- Any file changes made during this session that haven't been committed
- Branding: always "Sky Score", never "London Flight Path Map" in user-facing text

## Canonical repo location

**Use `C:\Users\bilal\projects\london-flight-path-map`** for any work on this repo. The `OneDrive\Desktop\london-flight-path-map` clone was the legacy location; OneDrive's filesystem-level sync can corrupt `.git/` if it interrupts a write mid-transaction (the user's global CLAUDE.md flags this risk explicitly). The OneDrive clone was retired on 2026-05-07 once the in-flight DEFRA loader finished — only `data/` (782 MB of NSPL CSV + DEFRA GeoTIFF, gitignored) was migrated by `mv`; everything else came from `git clone` of the GitHub remote.

If a future session lands you back in `OneDrive\Desktop\london-flight-path-map`, exit and `cd` to the projects/ path before doing anything destructive. If the OneDrive clone has come back from the dead (e.g. someone restored from a backup), prefer running on the projects/ clone and `git pull` to catch up rather than working in OneDrive.

**2026-07-19 update:** the `Claude Projects\Sky Score.bat` launcher was found still pointing at the OneDrive clone and has been repointed to the projects/ path. Both stale Desktop copies (`london-flight-path-map` and `London Flight Path Map`) were verified fully contained in this clone's history and are scheduled for deletion. Their unique March-era artefacts (original `london_flight_paths.py`/`.html` prototype, March `samconfig.toml`, old `.claude/commands`) are preserved in `archive/prototype-2026-03/` here. The 4 fastlane ASC vars (`ASC_ISSUER_ID`/`ASC_KEY_ID`/`ASC_KEY_FILE_PATH`/`FASTLANE_SKIP_DOCS`) existed only in the OneDrive clone's `.env` — merge into this clone's `.env` before relying on fastlane locally.

## Rolling planning docs

Two project-level planning docs live alongside this file. Read them when picking up work between sessions:
- **`ROADMAP.md`**, the broader rolling plan: vision, three parallel tracks (consumer site, B2B API, competitions/outreach), near-term task list with deadlines, open decisions. The source of truth for "what next".
- **`BUILDATHON_PLAN.md`**, focused single-purpose doc for the Shared Futures Buildathon (deadline 2026-05-15, event 2026-06-07). Will be archived after the event.

When a task ships or a decision lands, update the relevant doc rather than relying on chat memory.

After any substantial change (feature shipped/removed, audit item closed, vendor relationship changed), follow the **echo-work discipline** in the global `~/.claude/CLAUDE.md` — propagate to README, ROADMAP, LICENSING, AUDIT_REPORT, OUTREACH_LOG, memory, .env.example, tests, AWS surfaces. Doing it now is 2-3× cheaper than re-deriving the context tomorrow. For Sky Score specifically, the "echo loop" almost always touches: README.md (Lambda counts), ROADMAP.md (open decisions resolved), LICENSING.md (data sources), and `~/.claude/projects/.../memory/MEMORY.md` (cross-session facts).

**Cross-project echo**: substantial Sky Score waves (release submitted, big pivot landed, competition outcome confirmed, new submission added/dropped) also belong in the 90-day builder roadmap at `C:\Users\bilal\OneDrive\Desktop\90_DAY_ROADMAP.md` under the "Daily Progress Log" section. Keep that file strategic — competitions, pivots, deadlines, headline wins — not wave-level commit detail. The 90-day file is opened via the `90-Day Roadmap.bat` shortcut in `OneDrive\Desktop\Claude Projects\` to seed cross-session context across all Bill's projects, so Sky Score wave logs going there means future Claude sessions on Noor / LedgerAgent / Siraj see Sky Score's state too.

## Before conversation ends

When the user says goodbye, thanks you, or indicates they're done, run `git status` to check for uncommitted changes. If there are any, remind the user:

```
You have unsaved changes. Would you like me to commit them before you go?
```

If they say yes, create a commit with a clear message describing what changed. Keep git local only, never push.

## On conversation start

When the user starts a new conversation (first message, greeting, or asks what they can do), display this welcome message:

```
Sky Score

Available commands:
  /project:deploy-frontend Upload to S3 + invalidate CloudFront
  /project:deploy-backend SAM build + deploy Lambdas
  /project:deploy-all Deploy everything
  /preflight Pre-commit quality checks (lint, security, a11y)
  /careful Enable production safety mode (blocks destructive AWS commands)
  /aws-debug Debug Lambda/API Gateway issues (LIMITED — no log read on this account, see Quality & Plugins)
  /project:test-apis Test all API endpoints
  /project:review Summarise recent changes

Or just describe what you need, I have full context of this project.
```

## Project

Sky Score, a property noise + livability data tool for UK and NYC. Originally built for the Amazon Nova AI Hackathon; pivoted in May 2026 from "AI-powered" to "data-first" positioning. Consumer site is the marketing engine; the B2B `/v1/score` API is the product. Single-page frontend (`index.html`) plus B2B funnel pages (`/api/`, `/pricing`, `/privacy`) backed by the 7 active AWS Lambda functions orchestrated via SAM (the 5 dormant Bedrock Lambdas live in git history only; `live_flights` was removed in May 2026 pending OpenSky licensing).

## Branding

Always use "Sky Score" in all public-facing files and UI text.

## Do NOT add Co-Authored-By lines to git commits

## Quality & Plugins

- Run `/preflight` before every commit — or directly: **`sh scripts/preflight.sh`** (also `npm run preflight`, `make preflight`; all three invoke the same script so they cannot drift apart). Blocking: ESLint (now `.js`/`.mjs` too, not just `index.html`), html-validate, ruff over `backend/lambdas` + `scripts/` + `tests/`, **both** pytest suites, API-URL drift, **score sanity against the live API** (`scripts/check_score_sanity.py` - the only stage that can catch a DATA defect; the pytest suites never reach DynamoDB and Playwright asserts the site against itself), **no em dashes on the 8 deployed pages**, and Playwright at `--workers=2`. Advisory: Prettier, npm audit.
  - **Read the exit code, never pipe it.** `preflight | tail` is always 0 — a pipeline exits with its LAST stage's status. That is exactly how `make preflight` reported success on 2026-07-27 while running nothing at all (`make` is not on PATH in Git Bash here).
  - `--skip-e2e` skips Playwright, which hits the live site. `--fix` auto-fixes what is auto-fixable.
  - Rewritten 2026-07-27 after the gate produced a false green, a false red, and silently omitted the 167-test root suite. Change what blocks in `scripts/preflight.sh`, **not** in the skill file.
- Run `/careful` before touching live AWS resources, blocks destructive commands
- ~~Use `/aws-debug` when Lambda errors or API Gateway 5xx issues occur~~ **`/aws-debug` does NOT work on this account** (verified 2026-07-26): `flightmap-dev` is denied `logs:FilterLogEvents`, `logs:GetLogEvents`, `logs:DescribeLogStreams`, `cloudtrail:LookupEvents`, `iam:GetRolePolicy`, `lambda:ListFunctions` and `cloudformation:DescribeStackResource`. Only `logs:DescribeLogGroups` (names) works, and the `default` profile's token is invalid. Until a console-side grant lands, debug Lambda faults from the **console** or by **side-effect elimination** — see `OPERATIONS.md` §6. Prefix any `/aws/lambda/...` CLI argument with `export MSYS_NO_PATHCONV=1` or Git Bash mangles it.
- Use **context7** to look up D3.js, AWS SDK, or SAM docs before using unfamiliar APIs
- Use **security-guidance** when editing Lambda functions or API Gateway config
- Use **code-review** on all changed files before committing
- Use **frontend-design** when modifying the UI in index.html

## Build & Deploy

```bash
# Shared API base URL constant (loaded by index.html, score-demo/index.html,
# score-demo/status.html). Deploy alongside any frontend change that depends
# on it; the file rarely changes (only on APIGW id rotation), so most deploys
# can skip this line. Wave 12.9 / I-N5 offensive half.
AWS_PROFILE=flightmap aws s3 cp js/api-base.js s3://london-flight-map-frontend/js/api-base.js --content-type "application/javascript" --region eu-west-2

# Frontend, upload to S3 then invalidate CloudFront
AWS_PROFILE=flightmap aws s3 cp index.html s3://london-flight-map-frontend/index.html --content-type "text/html" --region eu-west-2
AWS_PROFILE=flightmap aws cloudfront create-invalidation --distribution-id EGSSPJKLFL33M --paths "/*"

# Pricing + privacy + changes pages — MUST target <name>/index.html keys (the
# sky-score-rewrite-index CloudFront function rewrites extensionless
# paths to <path>/index.html; a flat "pricing" key is never served).
AWS_PROFILE=flightmap aws s3 cp pricing.html s3://london-flight-map-frontend/pricing/index.html --content-type "text/html" --region eu-west-2
AWS_PROFILE=flightmap aws s3 cp privacy.html s3://london-flight-map-frontend/privacy/index.html --content-type "text/html" --region eu-west-2
AWS_PROFILE=flightmap aws s3 cp changes.html s3://london-flight-map-frontend/changes/index.html --content-type "text/html" --region eu-west-2

# Data assets. NOT covered by the index.html line above and absent from this
# file entirely until 2026-08-03, which is how the Cache-Control gap below went
# unnoticed. borough-extra.json carries every borough's crime, schools,
# transport and healthcare inputs, so a stale copy means wrong scores.
#
# --cache-control "no-cache" is LOAD-BEARING, not tidiness. The object shipped
# with no Cache-Control at all, and index.html fetched it with
# cache: 'force-cache' - serve any cached copy WITHOUT revalidating - so a
# browser could pin it indefinitely. A user was served crime figures from before
# the 2026-08-02 correction, days after it shipped.
#
# Bumping sw.js does NOT fix this. That evicts the service worker's caches; the
# stale copy lived in the browser's HTTP cache, which force-cache had opted out
# of freshness checks entirely. Prefer `make web-deploy-all`, which gets this
# right; these lines are the manual fallback.
AWS_PROFILE=flightmap aws s3 cp data/borough-extra.json s3://london-flight-map-frontend/data/borough-extra.json --content-type "application/json" --cache-control "no-cache" --region eu-west-2
AWS_PROFILE=flightmap aws s3 cp data/london-boroughs.json s3://london-flight-map-frontend/data/london-boroughs.json --content-type "application/json" --region eu-west-2
AWS_PROFILE=flightmap aws s3 cp data/nyc-boroughs.json s3://london-flight-map-frontend/data/nyc-boroughs.json --content-type "application/json" --region eu-west-2


# PWA assets — REQUIRED for the install prompt + offline SW to work. These are
# NOT covered by the index.html line above; they were missing from the live
# origin until 2026-05-21 (every asset 403'd → no manifest → install button
# silently dead). Re-deploy whenever manifest.webmanifest, sw.js, or the icons
# change (rare). Content-types matter: a wrong manifest type fails Chrome's
# installability check.
AWS_PROFILE=flightmap aws s3 cp manifest.webmanifest s3://london-flight-map-frontend/manifest.webmanifest --content-type "application/manifest+json" --region eu-west-2
AWS_PROFILE=flightmap aws s3 cp sw.js s3://london-flight-map-frontend/sw.js --content-type "application/javascript" --region eu-west-2
AWS_PROFILE=flightmap aws s3 cp icons/icon.svg s3://london-flight-map-frontend/icons/icon.svg --content-type "image/svg+xml" --region eu-west-2
AWS_PROFILE=flightmap aws s3 cp icons/icon-maskable.svg s3://london-flight-map-frontend/icons/icon-maskable.svg --content-type "image/svg+xml" --region eu-west-2

# Score demo (B2B API tester), same pattern as prototype
AWS_PROFILE=flightmap aws s3 cp score-demo/index.html s3://london-flight-map-frontend/score-demo/index.html --content-type "text/html" --region eu-west-2
AWS_PROFILE=flightmap aws cloudfront create-invalidation --distribution-id EGSSPJKLFL33M --paths "/score-demo/*"

# Backend, SAM build + deploy (always clean .aws-sam first)
# EPC bearer token is required after the 2026-05-30 service migration.
# Source from .env (gitignored); never paste the token into source files or chat.
# NOTE (corrected 2026-08-04): this line said `source ../.env`, which does not
# exist — `.env` is at the repo root, and `../.env` would be
# `C:\Users\bilal\projects\.env`. Because the whole block is `&&`-chained, the
# failed source ABORTED THE ENTIRE DEPLOY rather than falling through, so the
# documented command could never have worked from the repo root. Verified by
# running it during the 2026-08-04 signup deploy.
#
# Second gotcha, same deploy: the Bash tool's working directory PERSISTS between
# calls while environment variables do NOT, so splitting build and deploy across
# two invocations lands the second one in backend/ with no EPC_BEARER_TOKEN.
# Use absolute paths, or keep source + build + deploy in one invocation.
set -a && source .env && set +a && \
  cd backend && rm -rf .aws-sam && \
  AWS_PROFILE=flightmap sam build && \
  AWS_PROFILE=flightmap sam deploy --parameter-overrides \
    EpcBearerToken="$EPC_BEARER_TOKEN"
```

**Local env setup**: copy `.env.example` to `.env` and fill in:
- `EPC_BEARER_TOKEN` — from the My account page on `get-energy-performance-data.communities.gov.uk`
- `ASC_KEY_ID` / `ASC_ISSUER_ID` / `ASC_KEY_FILE_PATH` — for fastlane (see `mobile/CODEMAGIC_SETUP.md`)
- `FASTLANE_SKIP_DOCS=1` — non-optional, stops fastlane overwriting `mobile/fastlane/README.md`

The `.env` file is gitignored. The EPC SAM parameter uses `NoEcho: true` so the value doesn't appear in CloudFormation events. AllowedPattern `^.+$` on the parameter blocks deploys with empty / missing tokens.

**Token rotation**:
- EPC: regenerate from the My account page on `get-energy-performance-data.communities.gov.uk` whenever the token has touched a chat log, terminal scrollback, or any unencrypted persistence
- Update `.env` and redeploy after rotation

## Architecture

- **Frontend**: Single `index.html` (~8,200 lines as of 2026-07-24), vanilla JS, D3.js maps, all UI logic inline. **The mobile bottom-nav redesign is NATIVE-APP ONLY as of 2026-05-29** (web/native split): the redesign (`#mobile-nav` + `.app[data-mview]` 3-tab views via `setMobileView()`, map-as-background) is gated behind an `is-native` class that `setupNativeFeatures()` adds to `<html>` only inside the Capacitor app. **The website — desktop, mobile browser, and PWA — serves the classic bottom-sheet layout** (`.sheet-handle` + `setSheetState()`); the iOS/Android apps get the redesign. The redesign's base CSS rules are `.is-native`-prefixed and `setMobileView()` (sole writer of `data-mview`) bails unless `is-native`. Desktop (≥901px) keeps the two-column grid regardless. See `MOBILE_REDESIGN_PLAN.md` (v3 section).
- **Backend**: `backend/template.yaml`, SAM/CloudFormation defining the 7 active Lambdas + API Gateway + DynamoDB. (Corrected 2026-07-23: earlier docs said "12 Lambdas (7 active + 5 dormant)" but the template contains only the 7 — the dormant Bedrock five live in git history, not the template.)
- **B2B funnel pages** (deployed alongside `index.html`): `/api/` landing (`api/index.html`), `/pricing` (`pricing.html`, added 2026-07-23: 90-day £2,500 pilot + Free/£499 Professional/Enterprise tiers + founder block), `/privacy` (`privacy.html`). **S3 key gotcha:** the `sky-score-rewrite-index` CloudFront function rewrites extensionless paths to `<path>/index.html`, so privacy/pricing MUST be uploaded to `privacy/index.html` and `pricing/index.html` keys (`make web-deploy` does this correctly since 2026-07-23; a flat `privacy` key is a dead object).
- **Active Lambdas** (in `backend/lambdas/<name>/app.py`):
  - `score`, B2B scoring engine, API-key gated (`/v1/score`, `/v1/score/batch`, `/v1/regions`)
  - `signup`, self-service API-key issuance
  - `favourites`, DynamoDB CRUD with `X-Device-Token` auth
  - `epc`, MHCLG EPC certificate proxy (bearer-token auth via `EPC_BEARER_TOKEN`)
  - `sold_prices`, HM Land Registry Price Paid Data proxy
  - `transport`, TfL Open Data station + line-status
  - `nhs`, NHS Service Search via OSM Overpass
- **Dormant Lambdas** (NOT in `template.yaml` — verified 2026-07-23, the template holds only the 7 active functions):
  - `chat`, `multi_agent`, `analyze_image`, `analyze_document`, `report` — all Bedrock Nova Pro/Lite. Code + template entries live in git history only; re-introduction means restoring both from history and redeploying, then unhiding the UI block.
- **Removed**: `live_flights` (OpenSky proxy) — terminated in May 2026 pending OpenSky's required written licensing agreement for operational use. Lambda code lives in git (last working commit: `a214ba0`); restore + add OpenSky params back to template + flip the prototype's `liveLicensed` flag to revive.

## Prototype (Sky Score Radar)

- **Location**: `prototype/index.html`, standalone HTML, no dependencies on main app
- **Live URL**: `https://d1oe4ftwutjpf.cloudfront.net/prototype/index.html`
- **Stack**: Three.js (CDN), CSS2DRenderer for labels, UnrealBloomPass for bloom
- **Features**: 3D wireframe terrain, day/night cycle (real GMT/BST), noise contour rings, borough boundaries, corridor heatmap/timelapse, simulated flight tracks (live OpenSky data removed pending licensing — see Active Lambdas note above)
- **Controls**: `R` Reset, `1-3` Camera presets, `P` Screenshot, `N` Time-lapse, `C` Contours, `B` Boroughs, `V` Corridor view (Daily/Weekly/Monthly), `T` Timelapse replay, `H` Heatmap toggle
- **Mobile**: Fully responsive, touch button bar replaces keyboard shortcuts, collapsible panels via ☰ menu, breakpoints at 768px and 480px. OrbitControls supports pinch/drag natively.
- **Analytics**: GoatCounter (same `cubitt33` tracker as main site), prototype visits appear as `/prototype/index.html`
- **Naming**: Use "Sky Score Radar" for the prototype, "Sky Score" for the main app
- **Deploy**: `AWS_PROFILE=flightmap aws s3 cp prototype/index.html s3://london-flight-map-frontend/prototype/index.html --content-type "text/html" --region eu-west-2`

## PWA + Native (Capacitor + Codemagic)

Sky Score has three install paths from the same `index.html`:

1. **Web** — anyone visits skyscore.co.uk, no install
2. **PWA** — Install prompt in Chrome/Edge/Android; iOS Safari uses Share → Add to Home Screen. Manifest at `/manifest.webmanifest`, service worker at `/sw.js`.
3. **Native iOS / Android** — Capacitor wrap at `mobile/`, distributed via App Store + Play Store. **Split build pipeline** mirroring the Noor pattern:
   - **iOS**: built by Codemagic in cloud Mac (no local Mac available)
   - **Android**: built locally via Android Studio + gradle on Windows (Codemagic Android workflow not used; cloud Linux time was overhead since gradle runs fine on Windows)

The same `index.html` runs in all three contexts. Native-only features (geolocation "Score where I am" button, share sheet) feature-detect via `window.Capacitor.isNativePlatform()` — invisible on web/PWA.

```
mobile/
  capacitor.config.ts       # appId uk.co.skyscore.app, light theme
  package.json              # isolated; @capacitor/* + plugins
  scripts/copy-web.mjs      # assembles mobile/www/ from parent
  assets/                   # icon source SVGs (logo, foreground, background, splash)
  CODEMAGIC_SETUP.md        # iOS-only: ASC API key + dashboard config
  ANDROID_BUILD.md          # local Android Studio + gradle workflow
  STORE_LISTINGS.md         # paste-ready App Store + Play Store copy
  APPLE_REVIEW_NOTES.md     # Section 4.2 review notes for App Store
  PRIVACY_POLICY.md         # GDPR-compliant draft for /privacy
  RELEASE_CHECKLIST.md      # 9-step pre-release runbook (dual-path)
  DEEP_LINKING.md           # iOS Universal Links + Android App Links setup

codemagic.yaml              # repo root; ios-workflow only
```

**Update cadence:** web changes (CSS, JS, copy) deploy to CloudFront immediately. Native binaries need a build + store review (~2-3 days Apple, ~1 day Google). Plan binary releases every 2–4 weeks at most — more often than that isn't worth the review-cycle cost.

**Local dev:**
```bash
cd mobile
npm install                  # one-off
npm run sync                 # rebuilds mobile/www/, syncs Capacitor
npx cap open android         # Android Studio (for the actual Android build)
```

iOS native project is regenerated by Codemagic's `ios-workflow` on each cloud build — `npx cap add ios` runs in the cloud Mac, not locally. Android native project lives at `mobile/android/` and is built locally per `mobile/ANDROID_BUILD.md`.

**Apple Section 4.2:** the "Score where I am" button using native GPS is the App Store "Minimum Functionality" defence. Verbatim review-notes copy lives in `mobile/APPLE_REVIEW_NOTES.md`.

## AWS Resources

- **API Gateway**: `https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/`
- **CloudFront**: `https://d1oe4ftwutjpf.cloudfront.net` (distribution EGSSPJKLFL33M)
- **S3 bucket**: `london-flight-map-frontend` (eu-west-2)
- **DynamoDB tables** (4, all PAY_PER_REQUEST, eu-west-2): `london-flight-map-favourites`, `london-flight-map-signups`, `london-flight-map-noise-raster` (DEFRA Lden samples, loader `scripts/load_defra_raster.py`), `london-flight-map-postcodes` (ONS NSPL index, loader `scripts/load_nspl.py` — **fully loaded 2026-07-26: 2,699,393 rows, February-2026 vintage; roll to the August 2026 edition when it ships**). Both loaders run locally, not in Lambda, and both tables are forward-compatible: the score Lambda works correctly when they are absent or empty and upgrades silently once data lands, so **loading never needs a second deploy**.

  **NSPL loader speed (2026-07-27):** `_flush_batch` uses `BatchWriteItem`, but that needs `dynamodb:BatchWriteItem` on `flightmap-dev`, which is **in `backend/iam-policy.json` and not yet applied to the live policy**. Until it is, the loader detects the denial on its first chunk and completes on the old per-item path at ~129 rows/s — so **a vintage roll that takes ~6 hours is the signal the grant never landed**. Verify a load with `get-item`, never `describe-table`'s `ItemCount` (it refreshes ~6-hourly and reads 0 throughout).
- **Bedrock models** (only relevant if the dormant Bedrock Lambdas are ever restored from git history): `us.amazon.nova-2-lite-v1:0` (simple) + `us.amazon.nova-pro-v1:0` (complex/multimodal)
- **API custom domain**: `api.skyscore.co.uk` — APIGW edge custom domain (created 2026-07-23, cert = the us-east-1 wildcard, base-path mapping → `prod`). Serves once Cloudflare has `CNAME api → d1pr4crjutz9z8.cloudfront.net` (DNS only / grey cloud). The raw execute-api URL keeps working regardless.
- **IAM**: `flightmap-dev` user, `FlightMapDeployPolicy`
- **Region**: eu-west-2 (London)

## Key Conventions

- All Lambda handlers follow the same pattern: `def lambda_handler(event, context)` with CORS headers
- Frontend communicates with backend via fetch to API Gateway endpoints
- SAM stack name: `london-flight-map`

## Submissions

- **Amazon Nova AI Hackathon** (March 2026): Submitted, won $200 AWS credits (blog-post category). Video demo (3:10, with voiceover) complete.
- **Red Bull Basement** (submitted 2026-04-12): Awaiting shortlist decision; if invited, record 60-second pitch video. Positioning: "local friend" AI for renters with health risks.
- **Emergent Ventures / Mercatus** (submitted 2026-04-20): £45,000 ask over 9 months. Awaiting response (form promises within ~1 week). Draft at `Desktop/emergent-ventures-application.txt`.
- **Luma event** (applied 2026-04-23, `luma.com/vy4bnkom`): Submitted Sky Score as the idea (3-sentence pitch). Form fields: name, email, LinkedIn, GitHub (`billkhiz-bit`), phone, cofounder status. No project-URL field on the form. Event name/theme TBC.

Related separate project (not in this repo): **LedgerAgent** is a semi-finalist in the AWS 10,000 AIdeas Competition.

## Store Releases

- **iOS — v1.0.21 (mobile redesign) LIVE on the GB App Store.** <https://apps.apple.com/gb/app/sky-score/id6768118116> (App Store ID `6768118116`). Build 21 / version `1.0.21` — the native-only mobile redesign (web/native split; built via Codemagic from commit `4af9bc5`, iPhone-only to sidestep iPad review) — was submitted 2026-05-29 and subsequently approved; the public listing showed v1.0.21 (updated 1 Jun 2026, 1 rating at 5.0) per the 2026-07-19 store-listing audit. Screenshots at 1242×2688 (`store-screenshots/`); "What's New" in `mobile/fastlane/metadata/ios/en-GB/release_notes.txt`. Verify live anytime via `curl "https://itunes.apple.com/lookup?bundleId=uk.co.skyscore.app&country=gb"`. **The site footer links the listing since 2026-07-23** (trust-fix bundle, `appstore-footer-click` GoatCounter event).
- **Android — pending.** AAB stale relative to master; rebuild via `npm run build:android` (now fixed for Windows — uses `gradlew.bat`; needs `JAVA_HOME` = Android Studio JBR + `SKY_SCORE_KEYSTORE_PATH`/`SKY_SCORE_KEYSTORE_PASSWORD` env vars, password in Bitwarden) to carry the iPad fix + mobile redesign, then resume the Play Console flow in `HANDOFF_2026_05_16_play_submission.md`.

## Known Issues

See `AUDIT_REPORT.md` (last full audit 2026-07-24) for the live list. The long-standing trio closed 2026-07-24: I4 (borough metadata duplication — resolved by removal, `score/app.py` is the single holder), I6 (DLQ on async Lambdas — moot, all 7 functions are APIGW-synchronous), I14 (`PROJECT_DOCUMENTATION.md` — fully refreshed).

Most of the May-6 critical findings have shipped fixes — see `AUDIT_REPORT.md` for the triage column.
