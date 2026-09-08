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
# THE DEPLOYED DATA FILES AND THE AREA PAGES (2026-09-02).
#
# WHY THIS EXISTS. On 2026-09-02 this script reported "5 of 16 surfaces differ"
# while the wave actually waiting to deploy had changed `data/borough-extra.json`
# and all 99 area pages - and it could not see either, because neither is a
# PAGE. It named a number and that number was over the wrong denominator, which
# is worse than saying nothing: a reader checking "is the deploy outstanding?"
# gets a confident partial answer.
#
# `borough-extra.json` is the one that matters most. CLAUDE.md's deploy section
# already says a stale copy "means wrong scores" - it carries every borough's
# crime, schools, transport, healthcare and the three continuous environment
# fields that SCORE since v3.9/v4.0 - and it is served `no-cache` for exactly
# that reason. The precache pass below sees three of these files, and only ever
# asks whether they RESPOND, never whether they match.
#
# The area pages are the second gap. `tests/area-page-freshness.mjs` compares
# them against the live API, but it reads the SOURCE files off disk, so a
# rebuild that is never deployed passes it: source agrees with the API, and the
# 99 pages a crawler actually sees still carry the old numbers.
#
# BOTH LISTS ARE DERIVED, never re-listed here - the same rule the precache
# pass below states for sw.js, and the one mobile/scripts/copy-web.mjs was
# fixed under on 2026-08-30 (F41) after a hand-written copy froze on 3 August.
# The data list comes out of the Makefile target that deploys it, so a file
# added to `data-deploy` is checked with no edit here; the area list comes from
# walking `area/`, as tests/a11y-source.mjs already does.
DATA_SURFACES=$(sed -n '/^data-deploy:/,/^[a-zA-Z0-9_-]*:/p' Makefile \
  | grep -oE 'data/[A-Za-z0-9._-]+' | sort -u)

DATA_CHECKED=0
DATA_DRIFTED=0
for local_path in $DATA_SURFACES; do
  [ -z "$local_path" ] && continue
  if [ ! -f "$local_path" ]; then
    printf '  MISSING LOCALLY  %s\n' "$local_path"
    DATA_DRIFTED=$((DATA_DRIFTED + 1))
    continue
  fi
  live_hash=$(curl -fsS "$BASE/$local_path" 2>/dev/null | tr -d '\r' | shasum | cut -d' ' -f1)
  if [ -z "$live_hash" ]; then
    printf '  UNREACHABLE      %s\n' "$local_path"
    DATA_DRIFTED=$((DATA_DRIFTED + 1))
    continue
  fi
  local_hash=$(tr -d '\r' < "$local_path" | shasum | cut -d' ' -f1)
  DATA_CHECKED=$((DATA_CHECKED + 1))
  if [ "$live_hash" != "$local_hash" ]; then
    printf '  DRIFT            %s\n' "$local_path"
    DATA_DRIFTED=$((DATA_DRIFTED + 1))
  fi
done

# The Makefile target declares 17. A MINIMUM, so adding a city's boundary file
# raises it with no edit here while a broken parse - which would silently check
# nothing - reds.
if [ "$DATA_CHECKED" -lt 17 ]; then
  printf 'FAIL: compared only %d deployed data files, expected at least 17. The\n' "$DATA_CHECKED"
  printf '  data-deploy parse is broken or the files have moved - either way this\n'
  printf '  pass reported agreement it never measured.\n'
  exit 1
fi
printf '  data: %d of %d deployed data files match the live origin\n' \
  "$((DATA_CHECKED - DATA_DRIFTED))" "$DATA_CHECKED"

# The area pages. 100 requests, run 8 at a time - sequentially this pass alone
# took longer than every other stage in this script combined, and a check people
# switch off is worth nothing. Each worker prints one line per DRIFT, so the
# count comes from the output rather than from a variable a subshell cannot
# export back.
AREA_PAGES=$(find area -name index.html -type f 2>/dev/null | sort)
AREA_TOTAL=$(printf '%s\n' "$AREA_PAGES" | grep -c . )
AREA_TMP=$(mktemp)
printf '%s\n' "$AREA_PAGES" | grep . | xargs -P 8 -I{} sh -c '
  live=$(curl -fsS "'"$BASE"'/{}" 2>/dev/null | tr -d "\r" | shasum | cut -d" " -f1)
  if [ -z "$live" ]; then printf "  UNREACHABLE      %s\n" "{}"; exit 0; fi
  local_h=$(tr -d "\r" < "{}" | shasum | cut -d" " -f1)
  [ "$live" != "$local_h" ] && printf "  DRIFT            %s\n" "{}"
  exit 0
' > "$AREA_TMP" 2>/dev/null
# `grep -c` PRINTS its count and EXITS 1 when that count is zero, so an
# `|| echo 0` fallback emitted a SECOND zero and the variable became two
# lines - which every later arithmetic test rejected as a non-integer.
# Swallow the status and keep grep's own count.
AREA_DRIFTED=$(grep -c . "$AREA_TMP" 2>/dev/null || true)
[ -z "$AREA_DRIFTED" ] && AREA_DRIFTED=0
head -8 "$AREA_TMP"
if [ "$AREA_DRIFTED" -gt 8 ]; then
  printf '  ... and %d more area pages\n' "$((AREA_DRIFTED - 8))"
fi
rm -f "$AREA_TMP"

# build_area_pages.py writes 99 borough pages plus area/index.html. A MINIMUM
# for the same reason as every other floor here: `find` matching nothing must
# not read as a clean sweep.
if [ "$AREA_TOTAL" -lt 100 ]; then
  printf 'FAIL: found only %d area pages, expected at least 100. Run\n' "$AREA_TOTAL"
  printf '  `python scripts/build_area_pages.py --write`, or this pass is\n'
  printf '  reporting agreement over a directory it could not read.\n'
  exit 1
fi
printf '  area: %d of %d area pages match the live origin\n' \
  "$((AREA_TOTAL - AREA_DRIFTED))" "$AREA_TOTAL"

DATA_FAILED=0
if [ "$DATA_DRIFTED" -gt 0 ] || [ "$AREA_DRIFTED" -gt 0 ]; then
  printf '  %d data file(s) and %d area page(s) differ from the live origin.\n' \
    "$DATA_DRIFTED" "$AREA_DRIFTED"
  printf '  Run `make data-deploy` and/or re-upload area/ , then invalidate.\n'
  DATA_FAILED=1
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

# CACHE-CONTROL ON THE SHELL, checked at the ORIGIN (2026-09-08, audit s4).
#
# A hash comparison cannot see this: index.html can match byte-for-byte and
# still be served with no freshness directive, which is the state the audit
# found and this pass now prevents returning. Browsers fall back to heuristic
# caching without one, so the shell can pin for an arbitrary period - and
# neither a CloudFront invalidation nor an sw.js bump reaches the browser's
# HTTP cache. This is the borough-extra.json defect, on the shell.
#
# Asserts PRESENCE of a revalidating directive, deliberately not an exact
# string: `no-cache`, `max-age=0` and `must-revalidate` all satisfy the
# requirement, and pinning the literal would red on a defensible change.
HEADER_FAILED=0

# ONE request, several passes. The four checks below all interrogate the same
# response, so fetching per header would be four round-trips saying the same
# thing - and could disagree with itself if a deploy landed between them.
SHELL_HEADERS=$(curl -fsSI "$BASE/index.html" 2>/dev/null | tr -d '\r')
hdr() { printf '%s\n' "$SHELL_HEADERS" | grep -i "^$1:" | head -1 | cut -d' ' -f2-; }

SHELL_CC=$(hdr 'cache-control')
if [ -z "$SHELL_CC" ]; then
  printf '  shell cache-control: ABSENT - index.html is browser-pinnable\n'
  printf 'FAIL: index.html is served with no Cache-Control header.\n'
  printf '  Browsers apply heuristic freshness, so the app shell can pin for an\n'
  printf '  arbitrary period. Neither a CloudFront invalidation nor an sw.js\n'
  printf '  bump can evict it. Redeploy via `make web-deploy`.\n'
  HEADER_FAILED=1
elif printf '%s' "$SHELL_CC" | grep -qiE 'no-cache|no-store|max-age=0|must-revalidate'; then
  printf '  shell cache-control: %s (revalidates)\n' "$SHELL_CC"
else
  printf '  shell cache-control: %s\n' "$SHELL_CC"
  printf 'FAIL: index.html is served cacheable without revalidation (%s).\n' "$SHELL_CC"
  printf '  The app shell must revalidate; see the note in the Makefile.\n'
  HEADER_FAILED=1
fi

# SECURITY HEADERS AT THE ORIGIN (2026-09-08).
#
# These come from a CloudFront RESPONSE HEADERS POLICY, not from anything in
# this repo, so no amount of source review can tell you what is actually being
# served - and a policy is edited in a console, by hand, months apart. The
# distribution ran on the AWS MANAGED SecurityHeadersPolicy
# (67f7725c-6f97-4210-82d7-5512b31e9d03), which cannot be edited and carries no
# Permissions-Policy: those headers were not removed, that policy never had
# them.
#
# PRESENCE, not exact values, for the four below. They are a floor that must not
# silently drop when someone swaps the policy - the failure mode this pass
# exists for, and one the drift hashes above are blind to because the BODY is
# unchanged.
for h in strict-transport-security x-content-type-options referrer-policy x-frame-options; do
  v=$(hdr "$h")
  if [ -z "$v" ]; then
    printf '  shell %s: ABSENT\n' "$h"
    printf 'FAIL: %s is not served on index.html.\n' "$h"
    printf '  Check the response headers policy on distribution EGSSPJKLFL33M.\n'
    HEADER_FAILED=1
  else
    printf '  shell %s: %s\n' "$h" "$v"
  fi
done

# X-Frame-Options carries the CSPs' STATED intent, because theirs cannot.
# Every page declares `frame-ancestors 'none'` in a <meta> CSP, where that
# directive is IGNORED - so this header is the only thing actually refusing to
# be framed. DENY matches what the pages claim; SAMEORIGIN is the weaker state
# that was inherited from the managed policy and is accepted so this does not
# red before the console work lands. Anything else is a misconfiguration.
XFO=$(hdr 'x-frame-options' | tr 'A-Z' 'a-z')
case "$XFO" in
  deny|sameorigin|'') ;;
  *)
    printf 'FAIL: x-frame-options is "%s", expected DENY or SAMEORIGIN.\n' "$XFO"
    HEADER_FAILED=1
    ;;
esac

# DECLARED PENDING, and the declaration is checked in BOTH directions.
#
# Same shape as ON_THE_STAGE_CEILING in backend/tests/test_route_throttles.py:
# a known-absent header is listed here with the work identified, so this pass
# does not go permanently red on outstanding console work and become a signal
# nobody reads. The other direction is the point - once the header IS served,
# this reds until it is removed from the list, so the list cannot rot into a
# permanent exemption. A header in neither the loop above nor this list is
# simply unguarded, which is why new ones belong in one or the other.
#
# permissions-policy: needs a CUSTOM response headers policy, because the
# managed one cannot carry it and cannot be edited. flightmap-dev is denied
# cloudfront:CreateResponseHeadersPolicy, so this is console work. The value to
# set is in ROADMAP under the CloudFront item.
PENDING_HEADERS="permissions-policy"
for h in $PENDING_HEADERS; do
  if [ -n "$(hdr "$h")" ]; then
    printf '  shell %s: %s\n' "$h" "$(hdr "$h")"
    printf 'FAIL: %s is now served but is still declared PENDING.\n' "$h"
    printf '  Remove it from PENDING_HEADERS so the header becomes guarded\n'
    printf '  rather than exempt - that is what this list is for.\n'
    HEADER_FAILED=1
  else
    printf '  shell %s: pending (declared; needs the custom policy)\n' "$h"
  fi
done

# ONE verdict, covering ALL passes, so a run always reports everything it
# measured rather than stopping at whichever finding came first.
if [ "$DRIFT_FAILED" -ne 0 ] || [ "$DATA_FAILED" -ne 0 ] || [ "$PRECACHE_FAILED" -ne 0 ] || [ "$HEADER_FAILED" -ne 0 ]; then
  exit 1
fi

# EVERY COUNT, NOT ONE OF THEM. This line said "all %d public surfaces" over
# $CHECKED alone, which was 16 while the script now compares 117 - and an
# under-reported denominator is the very defect this pass was added to close
# on 2026-09-02. A summary that names one of its three passes reads as
# complete, exactly like the free-tier mirror list in template.yaml that
# omitted a mirror.
printf 'PASS: %d pages, %d data files and %d area pages match the live origin;\n' \
  "$CHECKED" "$DATA_CHECKED" "$AREA_TOTAL"
printf '  all %d precached assets present.\n' "$PRECACHE_CHECKED"
exit 0
