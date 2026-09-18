#!/bin/sh
# Deploy an HPI vintage roll in the ORDER the roll requires, and verify it from
# the origin. Written for the July 2026 roll (2026-09-16), when the auto-mode
# classifier refused to run the SAM deploy from Claude's session - correctly,
# it is a production change - and the alternative was five commands retyped
# from three documents. Run from the repo root in Git Bash:
#
#     sh scripts/deploy_hpi_roll.sh
#
# WHY BACKEND FIRST. index.html computes every score locally (v5.0 pools the
# national price band, v5.1 deflates growth), so a frontend-first deploy puts
# the site ahead of the API on every borough until the Lambda catches up.
# Backend first means the API moves, the site follows a minute later, and
# `tests/site-api-parity.mjs` agrees at the end. Redeploying the backend is also
# the whole of the recovery if anything below goes wrong; nothing is destroyed.
#
# WHAT IT DOES NOT COVER. `demo-deploy` (score-demo/, incl. openapi.yaml) and
# `data-deploy` (borough-extra.json) - a PRICE roll touches neither. A
# METHODOLOGY change alongside a roll usually changes openapi.yaml, and that
# is how v5.2 left "1 of 16 surfaces differ" on 2026-09-16 until demo-deploy
# was run by hand. Read the drift line at the end and run what it names.
#
# THE WEB TARGETS RUN THROUGH `scripts/make.py` (since 2026-09-18). `make` is
# on no PATH in Git Bash here, and until that date steps 3 and 4 carried the
# Makefile's recipes (web-deploy, area-deploy, meta-deploy) retyped - a copy
# that drifts on the next Makefile edit. The runner reads the Makefile itself,
# so this file names TARGETS and the Makefile stays the one holder of what
# each one uploads. `data-deploy` is NOT needed for a price roll, because
# avgPrice/trend live in index.html and the Lambda, not in borough-extra.json.
#
# MSYS_NO_PATHCONV=1 is load-bearing on every invalidation: Git Bash rewrites
# '/index.html' into a Windows path and CloudFront rejects the whole batch.
set -eu
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."

step() { printf '\n### %s\n' "$*"; }

step "0. preconditions"
[ -f .env ] || { echo "no .env at the repo root (EPC_BEARER_TOKEN is needed)"; exit 1; }
set -a; . ./.env; set +a
[ -n "${EPC_BEARER_TOKEN:-}" ] || { echo "EPC_BEARER_TOKEN is empty in .env"; exit 1; }
git status --short | grep -q . && echo "(uncommitted changes present - expected if you are deploying before committing)"
python scripts/build_hpi_prices.py --check --all >/dev/null || { echo "prices == HPI is RED on the tree; fix before deploying"; exit 1; }
echo "prices == HPI: green on the tree"

step "1. backend (SAM) - the API moves first"
( cd backend && rm -rf .aws-sam \
  && AWS_PROFILE=flightmap sam build \
  && AWS_PROFILE=flightmap sam deploy --no-confirm-changeset --no-fail-on-empty-changeset \
       --parameter-overrides EpcBearerToken="$EPC_BEARER_TOKEN" )

step "2. the gate that was red before the deploy must be green now"
node tests/area-page-freshness.mjs

step "3. web (index.html + the funnel pages) - the site follows"
python scripts/make.py web-deploy

step "4. area pages (they BAKE scores) + sitemap"
python scripts/make.py area-deploy meta-deploy

step "5. verify FROM THE ORIGIN, never from the exit codes above"
echo "-- invalidations still in progress (should drain within a few minutes):"
AWS_PROFILE=flightmap aws cloudfront list-invalidations --distribution-id EGSSPJKLFL33M \
  --query "InvalidationList.Items[?Status=='InProgress'].Id" --output text
echo "-- deployed == source (expect 133 of 133 once the invalidations complete):"
sh scripts/check_deploy_drift.sh || echo "   (drift can lag the invalidations by a few minutes - re-run this line alone)"
echo "-- score sanity against the live API:"
python scripts/check_score_sanity.py
echo "-- site == /v1/score:"
node tests/site-api-parity.mjs
echo "-- the worked example's postcode, live:"
curl -s "https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/score?postcode=SW11+1AA" \
  -H "x-api-key: ${SKY_SCORE_FREE_TIER_KEY:-}" | python -c "import sys,json; b=json.load(sys.stdin); print({k:b.get(k) for k in ('score','components','methodologyVersion')}); print({k:b['context'].get(k) for k in ('avgPriceGbp','priceTrendPct','priceTrendRealPct','inflationPct')})"
echo
echo "Expect: score 5.0, afford 0.3, growth 3.2, avgPriceGbp 686076, priceTrendPct -5.5, priceTrendRealPct -8.3, inflationPct 3.1 (METHODOLOGY s6)."
