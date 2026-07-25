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
#   make preflight         Run quality checks
#
# Requires (install once per machine):
#   - GNU Make. Windows: not installed by default. Get via either:
#       choco install make           (Chocolatey)
#       scoop install make           (Scoop)
#       winget install GnuWin32.Make (winget)
#     Or use the equivalent npm-script aliases in package.json instead
#     (e.g. `npm run deploy:web` ≡ `make web-deploy`).
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
	@echo "    pwa-deploy          Upload manifest, sw.js, icons (PWA assets)"
	@echo "    deeplinks-deploy    Upload .well-known/apple-app-site-association + assetlinks.json"
	@echo "    web-deploy-all      Run web-deploy + pwa-deploy + deeplinks-deploy"
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
	AWS_PROFILE=$(AWS_PROFILE_NAME) aws cloudfront create-invalidation \
		--distribution-id $(CF_DISTRIBUTION) --paths '/index.html' '/privacy*' '/pricing*' '/changes*' '/js/*'

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

.PHONY: web-deploy-all
web-deploy-all: web-deploy pwa-deploy
	@echo "Web + PWA deployed. Skip deeplinks-deploy until placeholders are filled."

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
# Quality
# ---------------------------------------------------------------------------

.PHONY: preflight
preflight:
	npm run lint
	npm run lint:html
	npm run format:check
	cd backend && python -m ruff check lambdas/ && python -m pytest -q
	@HOSTS=$$(grep -hoE 'https?://[a-z0-9]+\.execute-api\.eu-west-2\.amazonaws\.com' \
		index.html score-demo/*.html api/*.html tests/*.mjs 2>/dev/null | sort -u | wc -l); \
	if [ "$$HOSTS" -eq 1 ]; then echo "PASS: API URL drift check"; \
	else echo "FAIL: $$HOSTS distinct API hosts"; exit 1; fi

.PHONY: test-pwa
test-pwa:
	@echo "Starting local server on :8765 (background) then running smoke test..."
	@(npx --yes http-server -c-1 -p 8765 . > /tmp/sky-pwa-server.log 2>&1 &)
	@sleep 2
	node tests/pwa-check.mjs
	@-pkill -f "http-server.*8765" 2>/dev/null || true
