# Sky Score — CLI orchestration for web + PWA + native iOS/Android.
#
# Wraps the deploy / build / submit commands behind short targets so the
# whole release pipeline is `make` away. Most targets shell out to the
# canonical commands documented in OPERATIONS.md, mobile/CODEMAGIC_SETUP.md,
# mobile/ANDROID_BUILD.md, and mobile/RELEASE_CHECKLIST.md — this file is
# the keyboard-shortcut layer, not a new pipeline.
#
# Usage:
#   make help              List all targets
#   make web-deploy        Upload index.html + invalidate CloudFront
#   make pwa-deploy        Upload manifest, sw.js, icons
#   make android-build     Build signed AAB locally via gradle
#   make android-upload    Upload AAB to Play Console internal track
#   make ios-trigger       git push (Codemagic auto-builds on push)
#   make ios-submit        fastlane deliver — submit latest TestFlight build for App Store review
#   make score-book        Score a book of addresses offline to CSV (no API quota)
#   make preflight         Run quality checks
#
# Requires (install once per machine):
#   - GNU Make. Windows: not installed by default. Get via either:
#       choco install make           (Chocolatey)
#       scoop install make           (Scoop)
#       winget install GnuWin32.Make (winget)
#     CORRECTED 2026-08-04: this used to say "or use the equivalent npm-script
#     aliases in package.json instead (e.g. `npm run deploy:web`)". THERE ARE
#     NO deploy:* npm scripts. package.json has lint/test/preflight aliases and
#     no deploy aliases at all, so on a machine without GNU Make — which is the
#     default state of this one, `make` is not on PATH in Git Bash — the
#     documented fallback did not exist and the deploy commands had to be run
#     by hand. That is a contributing cause of audit finding 38: eleven live
#     files reached production by hand-upload with no deploy command anywhere.
#     Until deploy:* aliases exist (ideally delegating to one shared script, as
#     preflight already does, so they cannot drift), run the aws commands in
#     the targets below directly, or use OPERATIONS.md section 2.
#   - AWS CLI v2 with `flightmap` profile configured
#   - Node + npm (for the asset pipeline)
#   - Android Studio (for the GUI-based AAB build) OR a JDK + the Android
#     SDK on PATH (for `make android-build` via gradle CLI)
#   - Ruby + fastlane (`gem install fastlane`) for store-submission targets

AWS_PROFILE_NAME ?= flightmap
AWS_REGION       ?= eu-west-2
S3_BUCKET        ?= london-flight-map-frontend
CF_DISTRIBUTION  ?= EGSSPJKLFL33M

# Used by Codemagic build trigger; expected in env or .env file.
# Get a token at codemagic.io → Teams → Personal account settings → User API tokens.
CMG_API_TOKEN ?=
CMG_APP_ID    ?=

.PHONY: help
help:
	@echo "Sky Score Makefile — common targets:"
	@echo ""
	@echo "  Web / PWA"
	@echo "    web-deploy          Upload js/api-base.js + index/privacy/pricing/changes + invalidate"
	@echo "    data-deploy         Upload data/ boundaries + noise raster (run BEFORE pwa-deploy)"
	@echo "    pwa-deploy          Upload manifest, sw.js, icons (PWA assets)"
	@echo "    deeplinks-deploy    Upload .well-known/apple-app-site-association + assetlinks.json"
	@echo "    demo-deploy         Upload score-demo/ (Swagger UI, openapi.yaml, status)"
	@echo "    prototype-deploy    Upload prototype/index.html (Sky Score Radar)"
	@echo "    meta-deploy         Upload robots.txt, sitemap.xml, .well-known/security.txt"
	@echo "    web-deploy-all      web + data + pwa + demo + prototype + meta"
	@echo ""
	@echo "  iOS (Codemagic-driven)"
	@echo "    ios-trigger         git push origin master (Codemagic auto-builds)"
	@echo "    ios-build-status    Show recent Codemagic builds (needs CMG_API_TOKEN)"
	@echo "    ios-submit          fastlane deliver — submit latest TestFlight build for review"
	@echo ""
	@echo "  Android (local-build)"
	@echo "    android-sync        npm run sync inside mobile/ (refresh www + cap sync)"
	@echo "    android-assets      npm run build:assets (regenerate icons + splash)"
	@echo "    android-build       gradle bundleRelease (produces signed AAB)"
	@echo "    android-fingerprint Print SHA-256 of release keystore (for assetlinks.json)"
	@echo "    android-upload      fastlane supply — upload AAB to Play Console internal track"
	@echo "    android-promote     fastlane supply — promote internal track to production"
	@echo ""
	@echo "  Quality"
	@echo "    preflight           Run all quality checks (ESLint, html-validate, prettier, ruff, pytest, drift)"
	@echo "    test-pwa            Smoke test the PWA via Playwright (needs local server running)"
	@echo ""
	@echo "  Variables (override on the command line):"
	@echo "    AWS_PROFILE_NAME=$(AWS_PROFILE_NAME)  AWS_REGION=$(AWS_REGION)"
	@echo "    S3_BUCKET=$(S3_BUCKET)  CF_DISTRIBUTION=$(CF_DISTRIBUTION)"

# ---------------------------------------------------------------------------
# Web / PWA deploy
# ---------------------------------------------------------------------------

.PHONY: web-deploy
web-deploy:
	# js/api-base.js is the shared API base URL (window.API_BASE) that
	# index.html and both score-demo pages load. It had no make target until
	# 2026-07-25 — editable but never actually deployed, which matters most
	# for the pending api.skyscore.co.uk switchover. Uploaded first so a
	# fresh index.html never reads a stale base. no-cache keeps browsers
	# revalidating; sw.js serves it network-first for the same reason.
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp js/api-base.js \
		s3://$(S3_BUCKET)/js/api-base.js \
		--content-type "application/javascript" \
		--cache-control "no-cache" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp index.html \
		s3://$(S3_BUCKET)/index.html \
		--content-type "text/html" --region $(AWS_REGION)
	# NB: the CloudFront function sky-score-rewrite-index rewrites
	# extensionless paths to <path>/index.html, so these MUST land at
	# <name>/index.html keys. A flat "privacy" key is never served (the
	# pre-2026-07-23 version of this target uploaded there — dead object,
	# live /privacy was actually serving a manually-uploaded copy).
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp privacy.html \
		s3://$(S3_BUCKET)/privacy/index.html \
		--content-type "text/html" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp pricing.html \
		s3://$(S3_BUCKET)/pricing/index.html \
		--content-type "text/html" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp changes.html \
		s3://$(S3_BUCKET)/changes/index.html \
		--content-type "text/html" --region $(AWS_REGION)
	# terms.html added 2026-08-05. Same extensionless-key rule as privacy and
	# pricing: it MUST land at terms/index.html or /terms is never served. This
	# is the liability page, so an unpublished copy means the one document that
	# allocates risk exists only in git.
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp terms.html \
		s3://$(S3_BUCKET)/terms/index.html \
		--content-type "text/html" --region $(AWS_REGION)
	# api/index.html had NO target until 2026-08-03 - editable, deployed, and
	# uploaded by hand. It is the B2B landing page, so a stale copy sells the
	# product on claims the code no longer honours - exactly what it was doing
	# (Ofsted as a live source, the DEFRA raster tier as primary).
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp api/index.html \
		s3://$(S3_BUCKET)/api/index.html \
		--content-type "text/html" --region $(AWS_REGION)
	# js/vendor/ likewise had no target, and this one can break the site rather
	# than merely date it: d3.v7.min.js is in sw.js SHELL_ASSETS and cache.addAll()
	# is ATOMIC, so if it is missing from the origin the service worker fails to
	# install AT ALL, taking offline support for both cities with it. It returns
	# 200 today only because a hand-upload happened to land on 2026-07-30; a
	# fresh bucket would not. Cacheable unlike js/api-base.js above, because the
	# filename is version-pinned and index.html carries an SRI hash for these bytes.
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp js/vendor/ \
		s3://$(S3_BUCKET)/js/vendor/ \
		--recursive --content-type "application/javascript" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws cloudfront create-invalidation \
		--distribution-id $(CF_DISTRIBUTION) --paths '/index.html' '/privacy*' '/pricing*' '/changes*' '/terms*' '/js/*' '/api/*'

.PHONY: fonts-deploy
fonts-deploy:
	# Self-hosted fonts, added 2026-08-05 (see scripts/vendor_fonts.py). These
	# replaced fonts.googleapis.com / fonts.gstatic.com, which transferred every
	# visitor's IP address to Google in the US on each page load.
	#
	# ORDER IS LOAD-BEARING: fonts-deploy runs FIRST in web-deploy-all, ahead of
	# pwa-deploy. /fonts/fonts.css and the two Inter/JetBrains files are in
	# sw.js SHELL_ASSETS, and cache.addAll() is ATOMIC — ship sw.js before the
	# fonts exist at the origin and the service worker fails to install AT ALL,
	# taking offline support with it. Same trap as js/vendor/d3.v7.min.js.
	#
	# The .woff2 files are variable fonts, one per family, and change only when
	# vendor_fonts.py is re-run, so they cache hard. fonts.css references them by
	# fixed name, so it gets a shorter TTL and the deploy invalidates both.
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp fonts/ \
		s3://$(S3_BUCKET)/fonts/ \
		--recursive --exclude "*" --include "*.woff2" \
		--content-type "font/woff2" \
		--cache-control "public,max-age=31536000" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp fonts/fonts.css \
		s3://$(S3_BUCKET)/fonts/fonts.css \
		--content-type "text/css" \
		--cache-control "public,max-age=86400" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws cloudfront create-invalidation \
		--distribution-id $(CF_DISTRIBUTION) --paths '/fonts/*'

.PHONY: data-deploy
data-deploy:
	# Added 2026-07-30. Until now nothing under data/ had a target at all —
	# the boundary files and the DEFRA noise PNG were uploaded by hand, which
	# is fine right up until someone deploys sw.js without them. SHELL_ASSETS
	# lists both boundary files and cache.addAll() is ATOMIC: one 404 and the
	# service worker does not install, taking offline support for both cities
	# with it. So this runs BEFORE pwa-deploy in web-deploy-all, never after.
	@echo "Uploading data assets (boundaries + DEFRA noise raster)..."
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp data/london-boroughs.json \
		s3://$(S3_BUCKET)/data/london-boroughs.json \
		--content-type "application/json" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp data/nyc-boroughs.json \
		s3://$(S3_BUCKET)/data/nyc-boroughs.json \
		--content-type "application/json" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp data/borough-extra.json \
		s3://$(S3_BUCKET)/data/borough-extra.json \
		--content-type "application/json" \
		--cache-control "no-cache" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp data/aircraft-noise-london-lden.png \
		s3://$(S3_BUCKET)/data/aircraft-noise-london-lden.png \
		--content-type "image/png" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws cloudfront create-invalidation \
		--distribution-id $(CF_DISTRIBUTION) --paths '/data/*'

.PHONY: pwa-deploy
pwa-deploy:
	@echo "Uploading PWA manifest, service worker, icons..."
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp manifest.webmanifest \
		s3://$(S3_BUCKET)/manifest.webmanifest \
		--content-type "application/manifest+json" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp sw.js \
		s3://$(S3_BUCKET)/sw.js \
		--content-type "application/javascript" \
		--cache-control "no-cache, no-store, must-revalidate" \
		--region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp icons/ \
		s3://$(S3_BUCKET)/icons/ \
		--recursive --content-type "image/svg+xml" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws cloudfront create-invalidation \
		--distribution-id $(CF_DISTRIBUTION) \
		--paths '/manifest.webmanifest' '/sw.js' '/icons/*'

.PHONY: deeplinks-deploy
deeplinks-deploy:
	@echo "Checking for placeholder values in .well-known/..."
	@if grep -q "TEAMID\|REPLACE:WITH" .well-known/apple-app-site-association .well-known/assetlinks.json; then \
		echo "FAIL: placeholder values still present. Replace TEAMID and SHA-256 fingerprint first."; \
		echo "See mobile/DEEP_LINKING.md for what to fill in."; \
		exit 1; \
	fi
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp .well-known/apple-app-site-association \
		s3://$(S3_BUCKET)/.well-known/apple-app-site-association \
		--content-type "application/json" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp .well-known/assetlinks.json \
		s3://$(S3_BUCKET)/.well-known/assetlinks.json \
		--content-type "application/json" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws cloudfront create-invalidation \
		--distribution-id $(CF_DISTRIBUTION) --paths '/.well-known/*'

.PHONY: demo-deploy
# Added 2026-08-04, closing audit finding 38. Every file below was already
# serving 200 from CloudFront and NONE of them had a deploy command anywhere:
# they got there by hand-upload, so the only record that they exist was the
# live bucket. That is how api/index.html drifted until 2026-08-03, and on
# 2026-08-04 a `make web-deploy-all` would have silently skipped two files
# that had just been edited while still reporting success.
#
# openapi.yaml is the one that matters most: Swagger UI at /score-demo/
# api-docs.html reads it, so a stale copy documents an API that no longer
# exists. Content type must stay application/yaml (matched to what the live
# object already serves) or the browser downloads it instead of rendering.
demo-deploy:
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp score-demo/index.html \
		s3://$(S3_BUCKET)/score-demo/index.html \
		--content-type "text/html" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp score-demo/api-docs.html \
		s3://$(S3_BUCKET)/score-demo/api-docs.html \
		--content-type "text/html" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp score-demo/status.html \
		s3://$(S3_BUCKET)/score-demo/status.html \
		--content-type "text/html" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp score-demo/openapi.yaml \
		s3://$(S3_BUCKET)/score-demo/openapi.yaml \
		--content-type "application/yaml" --region $(AWS_REGION)
	# Vendored Swagger UI. Separate content types, so no --recursive here:
	# one wrong type on the CSS and the reference page renders unstyled.
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp score-demo/vendor/swagger-ui.css \
		s3://$(S3_BUCKET)/score-demo/vendor/swagger-ui.css \
		--content-type "text/css" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp score-demo/vendor/swagger-ui-bundle.js \
		s3://$(S3_BUCKET)/score-demo/vendor/swagger-ui-bundle.js \
		--content-type "application/javascript" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp score-demo/vendor/swagger-ui-standalone-preset.js \
		s3://$(S3_BUCKET)/score-demo/vendor/swagger-ui-standalone-preset.js \
		--content-type "application/javascript" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws cloudfront create-invalidation \
		--distribution-id $(CF_DISTRIBUTION) --paths '/score-demo/*'

.PHONY: prototype-deploy
# Sky Score Radar. Standalone page, no shared assets, so it deploys alone.
# Also hand-uploaded until now (most recently 2026-08-04, adding the DEFRA
# vintage disclosure to its noise panel).
prototype-deploy:
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp prototype/index.html \
		s3://$(S3_BUCKET)/prototype/index.html \
		--content-type "text/html" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws cloudfront create-invalidation \
		--distribution-id $(CF_DISTRIBUTION) --paths '/prototype/*'

.PHONY: meta-deploy
# robots.txt, sitemap.xml and .well-known/security.txt. Low churn, but they
# are the three files most likely to be edited and then forgotten, because
# nothing visibly breaks when they go stale. security.txt in particular
# carries a disclosure address that SECURITY.md is checked against.
meta-deploy:
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp robots.txt \
		s3://$(S3_BUCKET)/robots.txt \
		--content-type "text/plain" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp sitemap.xml \
		s3://$(S3_BUCKET)/sitemap.xml \
		--content-type "application/xml" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws s3 cp .well-known/security.txt \
		s3://$(S3_BUCKET)/.well-known/security.txt \
		--content-type "text/plain" --region $(AWS_REGION)
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws cloudfront create-invalidation \
		--distribution-id $(CF_DISTRIBUTION) \
		--paths '/robots.txt' '/sitemap.xml' '/.well-known/*'

.PHONY: web-deploy-all
# Order matters: data-deploy before pwa-deploy, because sw.js precaches the
# boundary files and cache.addAll() fails atomically on a missing one.
#
# demo-deploy, prototype-deploy and meta-deploy joined on 2026-08-04. Before
# that this target covered 4 of the 15 publicly-served surfaces while being
# named "all", which is the shape of every gate failure in this repo: green
# because of what it was not looking at.
web-deploy-all: fonts-deploy web-deploy data-deploy pwa-deploy demo-deploy prototype-deploy meta-deploy
	@echo "Web + data + PWA + demo + prototype + meta deployed. Skip deeplinks-deploy until placeholders are filled."

# ---------------------------------------------------------------------------
# iOS (Codemagic does the heavy lifting; we just trigger and submit)
# ---------------------------------------------------------------------------

.PHONY: ios-trigger
ios-trigger:
	@echo "Pushing to GitHub. Codemagic will auto-trigger ios-workflow on push to master."
	git push origin master

.PHONY: ios-build-status
ios-build-status:
	@if [ -z "$(CMG_API_TOKEN)" ] || [ -z "$(CMG_APP_ID)" ]; then \
		echo "Set CMG_API_TOKEN + CMG_APP_ID env vars first."; \
		echo "Token: codemagic.io → Teams → User API tokens"; \
		echo "App ID: visible in the URL of your codemagic app page"; \
		exit 1; \
	fi
	curl -s -H "x-auth-token: $(CMG_API_TOKEN)" \
		"https://api.codemagic.io/builds?appId=$(CMG_APP_ID)&limit=5" | \
		jq -r '.builds[] | "\(.startedAt) \(.status) \(.workflowId) \(.buildHash)"'

.PHONY: ios-submit
ios-submit:
	@echo "Submitting latest TestFlight build for App Store review..."
	cd mobile && bundle exec fastlane ios submit_for_review

# ---------------------------------------------------------------------------
# Android (local Studio / gradle build, fastlane upload)
# ---------------------------------------------------------------------------

.PHONY: android-sync
android-sync:
	cd mobile && npm run sync

.PHONY: android-assets
android-assets:
	cd mobile && npm run build:assets

.PHONY: android-build
android-build: android-sync android-assets
	@echo "Building signed AAB via gradle..."
	cd mobile/android && ./gradlew bundleRelease
	@echo ""
	@echo "AAB output: mobile/android/app/build/outputs/bundle/release/app-release.aab"

.PHONY: android-fingerprint
android-fingerprint:
	@if [ -z "$(KEYSTORE_PATH)" ]; then \
		echo "Set KEYSTORE_PATH first, e.g.:"; \
		echo "  make android-fingerprint KEYSTORE_PATH=~/.keystores/sky-score-release.jks"; \
		exit 1; \
	fi
	keytool -list -v -keystore $(KEYSTORE_PATH) -alias sky-score | grep "SHA256:"

.PHONY: android-upload
android-upload:
	@echo "Uploading AAB to Play Console internal track..."
	cd mobile && bundle exec fastlane android deploy_internal

.PHONY: android-promote
android-promote:
	@echo "Promoting internal-track build to production..."
	cd mobile && bundle exec fastlane android promote_to_production

# ---------------------------------------------------------------------------
# Bulk scoring
# ---------------------------------------------------------------------------

# Score a whole book of addresses offline, reusing the live scoring engine.
# Consumes no API quota and needs no API key — it calls resolve_query()
# directly, one layer below HTTP. Reads DynamoDB, so it needs the flightmap
# profile, but it never writes anything.
#
#   make score-book IN=book.csv OUT=scored.csv
#   make score-book IN=book.csv OUT=scored.csv ARGS="--persona family"
#
# See scripts/score_bulk.py for input formats and the --include-terminated flag.
.PHONY: score-book
score-book:
	@test -n "$(IN)" || (echo "Usage: make score-book IN=book.csv OUT=scored.csv"; exit 1)
	@test -n "$(OUT)" || (echo "Usage: make score-book IN=book.csv OUT=scored.csv"; exit 1)
	AWS_PROFILE=flightmap python scripts/score_bulk.py --input "$(IN)" --output "$(OUT)" $(ARGS)

# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------

# Delegates to scripts/preflight.sh so `make preflight`, `npm run preflight`
# and the /preflight skill all run the SAME checks and report the SAME exit
# code. The previous inline version drifted from the skill, omitted the root
# test suite entirely, and blocked on Prettier — which every file in the repo
# fails. `make` is also not installed on every dev machine here, so the shell
# script is the canonical entry point and this is a convenience wrapper.
.PHONY: preflight
preflight:
	sh scripts/preflight.sh

.PHONY: test-pwa
test-pwa:
	@echo "Starting local server on :8765 (background) then running smoke test..."
	@(npx --yes http-server -c-1 -p 8765 . > /tmp/sky-pwa-server.log 2>&1 &)
	@sleep 2
	node tests/pwa-check.mjs
	@-pkill -f "http-server.*8765" 2>/dev/null || true
