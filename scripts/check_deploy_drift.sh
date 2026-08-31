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
terms.html|terms
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
fonts/fonts.css|fonts/fonts.css
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

# PAGE DRIFT IS RECORDED HERE, NOT ACTED ON YET (restructured 2026-08-31, F43).
#
# This used to `exit 1` on the spot. That made every check below it unreachable
# in the ONLY state where this script normally runs: a source tree that is
# ahead of the last deploy. Page drift is the expected condition between a fix
# and its deploy, so exiting here meant the PWA precache pass - the one that
# decides whether the app installs at all - was skipped precisely when someone
# was about to deploy, and would first be seen on the run AFTER the problem was
# introduced.
#
# A gate that stops at the first finding reports the least important one.
DRIFT_FAILED=0
if [ "$DRIFTED" -gt 0 ]; then
  printf '  %d of %d surfaces differ from the live origin. Run the matching\n' \
    "$DRIFTED" "$CHECKED"
  printf '  make target (web-deploy / demo-deploy / prototype-deploy / meta-deploy).\n'
  DRIFT_FAILED=1
fi

# A FLOOR ON THE COMPARISON ITSELF, added 2026-08-23.
#
# CHECKED was counted and never asserted, and success printed NOTHING - so a
# run that compared all sixteen surfaces and a run whose loop never executed
# were byte-identical output and both exit 0. Empty SURFACES, or move the repo
# so every local_path misses its `[ -f ]` guard, and this reports the tree as
# perfectly in sync while having opened nothing.
#
# Fourth instance of that shape in this repo, after build_aircraft_bands.py
# (blocking), build_hpi_prices.py (blocking) and refresh_crime_from_ons.py, all
# closed on 2026-08-22. Found here by watching it verify a real deploy: the
# check went from one line of output to none, which is the same thing it would
# have printed had it died before the loop.
#
# 16 is the count the SURFACES list declares. Asserted as a MINIMUM, so adding
# a seventeenth surface raises it with no edit here while a shrinking list
# reds - a fixed count would be the scheduled staleness this repo keeps paying
# for.
if [ "$CHECKED" -lt 16 ]; then
  printf 'FAIL: compared only %d surfaces, expected at least 16. The list is\n' "$CHECKED"
  printf '  short or the files are not where this script looks - either way it\n'
  printf '  reported agreement it never measured.\n'
  exit 1
fi

# ---------------------------------------------------------------------------
# THE PWA PRECACHE SET (2026-08-31, audit F43).
#
# The 16 surfaces above are the PAGES. They are not the set that decides
# whether the app installs. `sw.js` precaches SHELL_ASSETS through
# `cache.addAll()`, which is ATOMIC: one 404 anywhere in that list and the
# service worker fails to install AT ALL, taking offline support for every city
# with it. Only 3 of the 20 entries were covered above, and this script still
# printed "all public surfaces match the live origin" - a confident all-clear
# over the exact assets whose absence breaks the PWA.
#
# The realistic way it fires is a PARTIAL deploy, which this repo has already
# had. `make web-deploy-all` runs fonts-deploy FIRST precisely because of this
# ordering, and on 2026-08-26 an invalidation failed AFTER four upload stages
# had already succeeded. Interrupt the recursive .woff2 copy and
# jetbrains-mono.woff2 is missing at the origin while every later target
# reports success.
#
# DERIVED FROM sw.js, never re-listed here. A second hand-written copy is the
# mirrored-code trap this repo has paid for three times, and
# mobile/scripts/copy-web.mjs was fixed the same way on 2026-08-30 (F41) after
# its hand-written REQUIRED_DATA froze on 3 August and shipped 2 of 13 cities.
#
# PRESENCE, not equality. Several entries are binary (woff2, svg) and the hash
# path above strips CR, which would corrupt the comparison; and `/` is
# index.html under another name, so it would always "drift". Reachability is
# also the precise question cache.addAll() asks, so this checks the thing that
# actually matters rather than the thing that is easy.
PRECACHE=$(sed -n '/SHELL_ASSETS *= *\[/,/^\];/p' sw.js | grep -oE "'/[^']*'" | tr -d "'")

PRECACHE_CHECKED=0
PRECACHE_MISSING=0
for asset in $PRECACHE; do
  [ -z "$asset" ] && continue
  code=$(curl -o /dev/null -s -w '%{http_code}' "$BASE$asset" 2>/dev/null)
  PRECACHE_CHECKED=$((PRECACHE_CHECKED + 1))
  if [ "$code" != "200" ]; then
    printf '  PRECACHE MISSING %s  (HTTP %s)\n' "$asset" "$code"
    PRECACHE_MISSING=$((PRECACHE_MISSING + 1))
  fi
done

# A FLOOR ON THIS PASS TOO, same reasoning as the one above: a regex that
# matches nothing must not read as a clean sweep. sw.js declares 20; asserted
# as a MINIMUM so a new city raises it with no edit here, while a shrinking
# list or a broken parse reds.
if [ "$PRECACHE_CHECKED" -lt 15 ]; then
  printf 'FAIL: found only %d precache assets in sw.js, expected at least 15.\n' "$PRECACHE_CHECKED"
  printf '  The SHELL_ASSETS parse is broken, so this pass checked almost\n'
  printf '  nothing while looking like it passed.\n'
  exit 1
fi

# ALWAYS REPORT WHAT THIS PASS MEASURED. The comment 60 lines above this one
# records that the surface loop used to print NOTHING on success, so a full
# run and a run whose loop never executed were byte-identical. Printing the
# count unconditionally is what stops that shape coming back here.
printf '  precache: %d of %d SHELL_ASSETS present at the origin\n' "$((PRECACHE_CHECKED - PRECACHE_MISSING))" "$PRECACHE_CHECKED"

PRECACHE_FAILED=0
if [ "$PRECACHE_MISSING" -gt 0 ]; then
  printf 'FAIL: %d of %d precached assets are absent from the origin.\n' \
    "$PRECACHE_MISSING" "$PRECACHE_CHECKED"
  printf '  cache.addAll() is atomic, so the service worker will not install at\n'
  printf '  all and the PWA is broken for every user - including the offline\n'
  printf '  launch tests/failure-path.mjs asserts. Run `make web-deploy-all`.\n'
  PRECACHE_FAILED=1
fi

# ONE verdict, covering both passes, so a run always reports everything it
# measured rather than stopping at whichever finding came first.
if [ "$DRIFT_FAILED" -ne 0 ] || [ "$PRECACHE_FAILED" -ne 0 ]; then
  exit 1
fi

printf 'PASS: all %d public surfaces match the live origin; all %d precached assets present.\n' \
  "$CHECKED" "$PRECACHE_CHECKED"
exit 0
