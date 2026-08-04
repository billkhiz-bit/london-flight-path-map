#!/bin/sh
# Compare every publicly-served file against what CloudFront is actually
# serving. Exits non-zero if any surface differs.
#
# WHY THIS EXISTS (2026-08-04). Two separate incidents in one day:
#
#   * `privacy.html` was corrected in git - removing a FALSE claim that request
#     data "never leaves UK AWS infrastructure" - and then sat unpublished. The
#     live privacy policy kept telling visitors something untrue while the repo
#     said otherwise, and nothing anywhere would have noticed.
#   * `score-demo/openapi.yaml` was deployed in the morning, edited again in
#     the afternoon, and drifted a second time inside the same session.
#
# Audit finding 38 is the same defect at a larger scale: eleven live files had
# no deploy command at all, so `api/index.html` sold the product on claims the
# code no longer honoured for months. Deploy TARGETS now exist for all of them
# (`make demo-deploy` / `prototype-deploy` / `meta-deploy`), but a target only
# helps if somebody runs it. This is the check that notices when nobody did.
#
# ADVISORY, NEVER BLOCKING, and that is deliberate. Drift is the *expected*
# state between making a commit and deploying it - a blocking version would be
# red on almost every run and would be ignored within a week, which is exactly
# how the Prettier stage earned its advisory label. Honest amber beats
# decorative green and beats permanent red.
#
# Note the key mapping: the `sky-score-rewrite-index` CloudFront function
# rewrites extensionless paths to `<path>/index.html`, so `pricing.html` is
# served at `/pricing`, not `/pricing.html`. Comparing against the wrong URL
# would report permanent false drift.

set -u

BASE="${SMOKE_BASE:-https://d1oe4ftwutjpf.cloudfront.net}"

# "<local path>|<url path>"
SURFACES='
index.html|index.html
pricing.html|pricing
privacy.html|privacy
changes.html|changes
api/index.html|api/
score-demo/index.html|score-demo/index.html
score-demo/api-docs.html|score-demo/api-docs.html
score-demo/status.html|score-demo/status.html
score-demo/openapi.yaml|score-demo/openapi.yaml
prototype/index.html|prototype/index.html
robots.txt|robots.txt
sitemap.xml|sitemap.xml
.well-known/security.txt|.well-known/security.txt
js/api-base.js|js/api-base.js
'

DRIFTED=0
CHECKED=0

for entry in $SURFACES; do
  [ -z "$entry" ] && continue
  local_path=$(printf '%s' "$entry" | cut -d'|' -f1)
  url_path=$(printf '%s' "$entry" | cut -d'|' -f2)

  if [ ! -f "$local_path" ]; then
    printf '  MISSING LOCALLY  %s\n' "$local_path"
    DRIFTED=$((DRIFTED + 1))
    continue
  fi

  # Normalise line endings before hashing: this repo is mixed CRLF/LF (see the
  # 2026-07-30 gotcha) and S3 stores whatever was uploaded, so a raw byte
  # compare reports drift on files that are semantically identical.
  live_hash=$(curl -fsS "$BASE/$url_path" 2>/dev/null | tr -d '\r' | shasum | cut -d' ' -f1)
  if [ -z "$live_hash" ]; then
    printf '  UNREACHABLE      %s  (%s)\n' "$local_path" "$url_path"
    DRIFTED=$((DRIFTED + 1))
    continue
  fi
  local_hash=$(tr -d '\r' < "$local_path" | shasum | cut -d' ' -f1)

  CHECKED=$((CHECKED + 1))
  if [ "$live_hash" != "$local_hash" ]; then
    printf '  DRIFT            %s  ->  %s\n' "$local_path" "$url_path"
    DRIFTED=$((DRIFTED + 1))
  fi
done

if [ "$DRIFTED" -gt 0 ]; then
  printf '  %d of %d surfaces differ from the live origin. Run the matching\n' \
    "$DRIFTED" "$CHECKED"
  printf '  make target (web-deploy / demo-deploy / prototype-deploy / meta-deploy).\n'
  exit 1
fi

exit 0
