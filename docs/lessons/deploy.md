# Build and deploy

> Moved verbatim from `CLAUDE.md` on 2026-10-17 to keep the session-start file small.
> MSYS_NO_PATHCONV, make targets, make.py, manual commands, SAM, env setup, token rotation.
> Statements are dated as written; re-measure a number before relying on it, and when a
> rule here changes, update the one-line rule in `CLAUDE.md` too.

<!-- CLAUDE.md lines 1211-1212 (2026-10-16) -->
## Build & Deploy

<!-- CLAUDE.md lines 1452-1603 (2026-10-16) -->
> ## ⚠️ `export MSYS_NO_PATHCONV=1` BEFORE ANY `cloudfront create-invalidation`
>
> Git Bash rewrites any argument that looks like a Unix absolute path into a
> Windows one, so `'/index.html'` reaches the API as
> `C:/Program Files/Git/index.html` and CloudFront rejects the whole batch with
> `InvalidArgument: Your request contains one or more invalid invalidation
> paths`. CLAUDE.md has documented this for `/aws/lambda/*` arguments for
> months; it bites invalidation paths identically.
>
> **It bit on 2026-08-26 AFTER all four upload stages had already succeeded** -
> objects live at the origin, cache not cleared, exit code non-zero only at the
> very end. That is the worst half to lose, because the deploy looks done. The
> same script got it right on its next two runs with the guard in place.

**Prefer the make targets; the commands below are the manual fallback.** As of
2026-08-04 every publicly-served file has one, and `make web-deploy-all` covers
all of them - **count the targets below, do not trust a number in this sentence**; it said "15 surfaces" while omitting `area-deploy` and its 100 pages entirely:

| Target | Covers |
|---|---|
| `fonts-deploy` | **new (2026-08-05)** — self-hosted `fonts/`. **Runs FIRST in `web-deploy-all`, and that ordering is load-bearing**: three font files are in `sw.js` `SHELL_ASSETS` and `cache.addAll()` is atomic, so shipping `sw.js` before the fonts exist at the origin makes the service worker fail to install at all |
| `web-deploy` | **the full map: `index.html` -> `map/index.html` (since 2026-10-06; it no longer writes the root key)**, privacy, pricing, changes, **terms**, `api/`, `js/` (api-base.js + every `js/*.mjs`) |
| `data-deploy` | `data/*` (gets `borough-extra.json`'s load-bearing `no-cache` right) |
| `pwa-deploy` | manifest, `sw.js`, icons. **Uploaded BY TYPE since 2026-10-08** (`*.svg` and `*.png` in separate commands): the one `--content-type "image/svg+xml"` for the whole folder would have served the new PNG touch icon as SVG |
| `demo-deploy` | **new** — all 7 `score-demo/` files incl. the vendored Swagger UI |
| `prototype-deploy` | **new** — `prototype/index.html` |
| `meta-deploy` | **new** — `robots.txt`, `sitemap.xml`, `.well-known/security.txt`, `preview.png`, **`favicon.ico` since 2026-10-08** (browsers request it from the root whatever a page declares; it 404'd on every page view until then), and **`404.html` since 2026-10-07**: CloudFront serves it with status 404 for any origin 403/404 (`scripts/cloudfront_not_found.py --plan/--apply/--verify`; the error responses are DISTRIBUTION-WIDE, so they cover `/badge` too, which was thought safe because "`/badge` answers every GET 200" - **it does not: an uncovered postcode's badge is a 404 SVG, and this mapping replaced it with HTML; audit 2026-10-09 I-2. Since 2026-10-11 the script maps origin 403 ONLY (S3 never 404s: no ListBucket), applied and verified 18 of 18 the same day**). The old `/privacy.html`, `/terms.html`, `/pricing.html`, `/changes.html` 301 from `sky-score-rewrite-index`, whose source is `FUNCTION_CODE` in `scripts/install_cloudfront_index_rewrite.py` (run in Node by `tests/test_cloudfront_function.py`). **Both AWS steps are Bill's**: the classifier refuses CloudFront publishes from Claude's session ("Protected-Scope IaC Apply"), so hand them over as `!` commands, one per message |
| `area-deploy` | **the 99 static borough pages + `area/index.html`** (`s3 sync --delete`). **Was MISSING FROM THIS TABLE until 2026-09-02**, which is the same "a list that omits a member reads as complete" trap this file records about `template.yaml`'s free-tier mirrors. It also had **no CloudFront invalidation** until that date - the only target without one - so all 100 pages uploaded, every command reported success, and CloudFront served the OLD pages for up to the hour its `max-age=3600` allows. That is what made it silent: check immediately and the deploy looks broken, check later and it looks fine, which reads as a flaky check rather than a missing step |
| `talks-deploy` | **new (2026-09-21)** - `aws s3 sync` of `talks/`: the plain-English write-ups (`how-sky-score-works.pdf`, `how-the-checks-work.pdf`, each rendered TAGGED from the `.html` beside it by `node scripts/render_talks_pdfs.mjs`; commit both, and both are uploaded - the `.html` is the primary format since 2026-09-25) and `talks/index.html`, which is what the end-card QR code points at (`skyscore.co.uk/talks/`). No `--delete`. **Standalone**: not a product surface, so not in `web-deploy-all` and not compared by `check_deploy_drift.sh`. Exists because a live file with no deploy command is audit finding 38's shape. **No em dashes** - the gate does not scan `talks/`, so the rule is kept by hand here |
| `deeplinks-deploy` | `.well-known/apple-app-site-association` + `assetlinks.json`. **NOT in `web-deploy-all`**, deliberately: the target refuses to run while the files hold `TEAMID`/`REPLACE:WITH` placeholders (see `mobile/DEEP_LINKING.md`). Omitted from this table until 2026-09-14 (audit M29) |
| `open-data-deploy` | `open-data/index.html` + the borough CSV (2026-09-28). In `web-deploy-all`. **Absent from this table until 2026-10-02**, the list-that-omits-a-member trap again |
| `bay-area-deploy` | **new (2026-10-02)** - `bay-area/index.html`, its BTS noise picture and `share.png`. In `web-deploy-all`. The page is GENERATED: `python scripts/build_bay_area_page.py --write` (`--check` is blocking), from `data/us-flight-procedures.json`, `data/us-bayarea-places.json` and the picture. **A new FAA cycle reds `--check` until `--write` is re-run.** The picture's name carries its edition because `sw.js` serves same-origin images cache-first |
| `home-deploy` | **THE FRONT PAGE (2026-10-06), replacing `preview-deploy`.** `home/index.html` -> the ROOT key (`/`), `home/reports/` -> `/reports/` (the reports page, the two sample PDFs, and `/reports/street/`, the free self-serve street report), `home/moved/preview/` -> two meta-refresh pages so `/preview/` and `/preview/reports/` forward, and `js/*.mjs`. **Run AFTER `web-deploy`** (web-deploy-all does): the front page links to `/map/` everywhere. The engine's five data files (+ `covid-understatement.json` for the report) moved into `data-deploy`, as preview-deploy's own comment said they would. History: built as `/preview/` from 2026-10-02 (branch `homepage-v2`, Bill's v2, then 'ask first, then the tool' on 5 Oct), deployed `noindex` 2026-10-03, made the front door 2026-10-06. Gate: `tests/front-page.mjs` (was `tests/preview-home.mjs`), blocking, offline |
| `web-deploy-all` | all of the above bar `deeplinks-deploy` and `talks-deploy`; `fonts-deploy` first, then `data-deploy`, `web-deploy`, `home-deploy`, `pwa-deploy` |

The last three were added closing audit finding 38: **eleven live files had no
deploy command anywhere** and had reached production by hand-upload, which is
how `api/index.html` sold the product on retired claims for months.
`web-deploy-all` previously covered **4 of 15** surfaces while being named
"all". Run `sh scripts/check_deploy_drift.sh` to see what is currently stale.

**`make` is not on PATH in Git Bash here, and since 2026-09-18 that no longer
matters: `python scripts/make.py <target>` (or `npm run make -- <target>`)
runs any Makefile target without GNU Make.** It reads the Makefile itself, so
there is one holder and nothing to keep in step; it refuses constructs it does
not implement (`$(shell)`, `ifeq`, `include`) rather than guessing;
`--dry-run` prints the expanded commands; and `tests/test_make_runner.py`
parses the whole Makefile on every preflight. `deploy_hpi_roll.sh` calls it
for its web steps instead of carrying retyped recipes. Until that date the
manual commands below were what actually ran on this machine, which is how
`OPERATIONS.md` s2 came to upload `privacy.html` to a dead key. They stay as
the reference for what each target does.

```bash
# Shared API base URL constant (loaded by index.html, score-demo/index.html,
# score-demo/status.html). Deploy alongside any frontend change that depends
# on it; the file rarely changes (only on APIGW id rotation), so most deploys
# can skip this line. Wave 12.9 / I-N5 offensive half.
AWS_PROFILE=flightmap aws s3 cp js/api-base.js s3://london-flight-map-frontend/js/api-base.js --content-type "application/javascript" --region eu-west-2

# Self-hosted fonts (added 2026-08-05). Deploy these BEFORE sw.js — three of
# them are in SHELL_ASSETS and cache.addAll() is atomic, so a missing font at
# the origin stops the service worker installing entirely. Regenerate with
# `python scripts/vendor_fonts.py`; they change only when that script is re-run.
AWS_PROFILE=flightmap aws s3 cp fonts/ s3://london-flight-map-frontend/fonts/ --recursive --exclude "*" --include "*.woff2" --content-type "font/woff2" --cache-control "public,max-age=31536000" --region eu-west-2
AWS_PROFILE=flightmap aws s3 cp fonts/fonts.css s3://london-flight-map-frontend/fonts/fonts.css --content-type "text/css" --cache-control "public,max-age=86400" --region eu-west-2

# Frontend, upload to S3 then invalidate CloudFront
# --cache-control is LOAD-BEARING here too (added 2026-09-08). index.html
# shipped with NO Cache-Control header at all, so browsers applied HEURISTIC
# freshness and could pin the whole app shell indefinitely - a CloudFront
# invalidation does not reach the browser's HTTP cache, and neither does an
# sw.js bump, which evicts Cache Storage instead. Identical to the
# borough-extra.json trap recorded above, on the shell rather than the data.
AWS_PROFILE=flightmap aws s3 cp index.html s3://london-flight-map-frontend/index.html --content-type "text/html" --cache-control "no-cache" --region eu-west-2
AWS_PROFILE=flightmap aws cloudfront create-invalidation --distribution-id EGSSPJKLFL33M --paths "/*"

# Pricing + privacy + changes pages — MUST target <name>/index.html keys (the
# sky-score-rewrite-index CloudFront function rewrites extensionless
# paths to <path>/index.html; a flat "pricing" key is never served).
AWS_PROFILE=flightmap aws s3 cp pricing.html s3://london-flight-map-frontend/pricing/index.html --content-type "text/html" --region eu-west-2
AWS_PROFILE=flightmap aws s3 cp privacy.html s3://london-flight-map-frontend/privacy/index.html --content-type "text/html" --region eu-west-2
AWS_PROFILE=flightmap aws s3 cp terms.html s3://london-flight-map-frontend/terms/index.html --content-type "text/html" --region eu-west-2
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
- Update `.env`, then **`sh scripts/rotate_epc_token.sh`** (added 2026-09-18) - it refuses a token equal to the one the last deploy used (read from gitignored `backend/samconfig.toml`, which `sam deploy` writes), refuses a dirty `backend/`, deploys, and verifies `/epc` from the origin on `available: true` AND `count > 0`, because a rejected token answers **200 with `available: false`** by design and a status check passes it. Do the three steps back to back: regenerating retires the old token at once, so `/epc` is degraded until the deploy lands.

