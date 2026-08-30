#!/usr/bin/env sh
# Sky Score preflight — the pre-commit quality gate.
#
# WHY THIS FILE EXISTS (2026-07-27). The gate lied, in both directions, twice
# in one session:
#
#   * `make preflight` reported SUCCESS while running nothing at all, because
#     `make` is not on PATH in Git Bash on this machine and every check was
#     piped to `tail` — a shell pipeline exits with the status of its LAST
#     stage, so `anything | tail` is always 0. Nothing here pipes a check
#     whose exit code matters.
#
#   * The Playwright suite reported 14 failures that were all false, because
#     it runs against the LIVE CloudFront site with an uncapped worker pool.
#
# A gate that cries wolf gets ignored, and a gate that reports green while
# doing nothing is worse than having none — it is the same class of failure
# as the signup funnel sitting dead for 2.5 months behind a passing test suite.
#
# Usage:
#   sh scripts/preflight.sh              # everything
#   sh scripts/preflight.sh --skip-e2e   # skip the 3 stages needing network
#
# --skip-e2e skips ONLY the stages that need the network: the Playwright
# suite, the extension e2e, and the area-page freshness check. It does NOT
# skip the source-pointed browser gates - those serve the working tree and
# are what stop a defect reaching the deploy. It used to skip all fourteen
# and report PASS, which made it a way to get a green run by not looking.
#   sh scripts/preflight.sh --fix        # auto-fix what is auto-fixable
#
# Exit status is 0 only if every BLOCKING check passed. Advisory checks are
# reported but never change the exit code — see the note on Prettier below.

set -u

SKIP_E2E=0
FIX=0
for arg in "$@"; do
  case "$arg" in
    --skip-e2e) SKIP_E2E=1 ;;
    --fix)      FIX=1 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.." || exit 2

# Load .env so checks that need a credential can find one (added 2026-08-07).
# `score sanity` is the first: it used to hard-code the demo API key, which put
# a blocking gate on the same public 2,000/month quota as score-demo/index.html,
# and when that ran out every commit in the repo was blocked by an exhausted
# counter rather than a defect. It now needs SKY_SCORE_API_KEY from here.
#
# `set -a` exports what the file defines; the guard keeps a fresh clone without
# a .env working for every check that does not need one, rather than failing at
# startup with a message about a file the developer has not been told to create.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

FAILED=""
PASSED=""
ADVISORY=""
SKIPPED_NET=""

# Run a blocking check. Output is shown only on failure, so a green run stays
# readable — but it is NEVER piped, so $? is the real status of the command.
check() {
  name="$1"; shift
  printf '  %-34s' "$name"
  out=$("$@" 2>&1)
  if [ $? -eq 0 ]; then
    printf 'PASS\n'
    PASSED="$PASSED $name"
  else
    printf 'FAIL\n'
    FAILED="$FAILED|$name"
    printf '%s\n' "$out" | tail -25 | sed 's/^/      /'
  fi
}

# Run a BLOCKING check that genuinely needs the network, honouring --skip-e2e.
#
# The flag used to be a block wrapper, and it swallowed FOURTEEN stages while
# printing SKIPPED for two. Eleven of them never touched the network at all -
# they serve the working tree over a local server precisely so they gate the
# DEPLOY - so `--skip-e2e` was silently disabling the entire source-pointed
# half of the suite and then printing RESULT: PASS. That is the shape this
# repo keeps paying for: green because of what it was not looking at.
#
# A per-stage helper is used instead of a block so a skipped stage still prints
# its own line, in its own position. A stage that vanishes from the report is
# indistinguishable from a stage that passed.
net_check() {
  if [ "$SKIP_E2E" -eq 1 ]; then
    printf '  %-34s%s\n' "$1" "SKIPPED (--skip-e2e, needs network)"
    SKIPPED_NET="$SKIPPED_NET|$1"
  else
    check "$@"
  fi
}


# Run an advisory check. Reported, never blocking.
advise() {
  name="$1"; shift
  printf '  %-34s' "$name"
  if "$@" >/dev/null 2>&1; then
    printf 'ok\n'
  else
    printf 'deviates (advisory, not blocking)\n'
    ADVISORY="$ADVISORY|$name"
  fi
}

echo
echo "PREFLIGHT, Sky Score"
echo "===================="
echo

echo "Blocking:"

if [ "$FIX" -eq 1 ]; then
  npm run lint:fix >/dev/null 2>&1
  python -m ruff check backend/lambdas/ backend/tests/ scripts/ tests/ --fix >/dev/null 2>&1
fi

# Label was "ESLint (index.html)" until 2026-08-06, three days after the config
# and npm script grew to cover *.js, js/, scripts/, tests/, mobile/scripts/ and
# now extension/. The command was right; the label understated it, which is the
# same failure mode as a gate that overstates — either way the name stops
# describing what actually ran.
check "ESLint (8 targets)"             npm run lint
check "html-validate (9 pages)"        npm run lint:html
check "ruff (backend/lambdas)"         python -m ruff check backend/lambdas/
# backend/tests/ was outside every ruff target until 2026-08-04, so the suite
# that guards the score engine was the one directory nothing linted — it had
# accumulated 4 import-order errors and an S105. Same shape as the root-suite
# omission below and the single-page a11y scan: the gate looked green because
# of what it was not looking at.
check "ruff (scripts, tests)"          python -m ruff check backend/tests/ scripts/ tests/
check "pytest (backend)"               sh -c 'cd backend && python -m pytest -q'
# Root suite covers the NSPL loader, the bulk scorer and the handler contracts.
# It was absent from the gate until 2026-07-27, so 167 tests — including every
# test written that day — were never run before a commit.
check "pytest (root)"                  python -m pytest tests/ -q
check "API base-URL drift (I-N5)"      sh scripts/check_api_url_drift.sh
# Added 2026-08-03. The only check here that can catch a DATA defect: the two
# pytest suites never reach DynamoDB and Playwright asserts the site against
# itself, which is how the raster served Heathrow a quiet score of 7.5/10 for a
# week with this gate green throughout. Hits the live API, like the e2e stage.
check "score sanity (live API)"        python scripts/check_score_sanity.py
# Costs ZERO demo quota in the normal case: the two denial assertions are
# throttled at the edge and API Gateway does not meter a throttled request.
# The one metered call degrades to a warning if the funnel quota is spent,
# so this gate cannot repeat what `score sanity` did when it held this key.
check "demo key reaches only /v1/score" node tests/demo-key-scope.mjs
# Borough avgPrice and trend against HM Land Registry HPI, keyed on ONS codes.
# Placed with the offline gates rather than in the --skip-e2e block: it needs no
# browser and no live site, only data/hpi-average-prices.csv, which it fetches
# once and caches.
#
# The only gate that can catch a PARTIAL VINTAGE ROLL, and it was written
# because there was one. Until 2026-08-10 London's avgPrice matched HPI 2026-05
# for all 33 boroughs while its `trend` matched NO HPI month - the growth input
# was reading from a source nobody could name, under a CITY_PROVENANCE sentence
# telling B2B customers it was HPI. Nothing noticed, because both fields sit in
# TWO holders and test_borough_data_parity.py compares only the liveability
# inputs.
#
# Proven able to fail: it went red on exactly that defect, 0/33 trends agreeing,
# which is why it was not wired in here until the data agreed.
check "prices == HM Land Registry"     python scripts/build_hpi_prices.py --check --all
# Aircraft `impact` was the last score input with NO script behind it, and it
# was wrong: a Heathrow-calibrated distance ladder applied unweighted to
# airports up to 485x smaller, which banded Stockton-on-Tees `severe` off an
# airport carrying 173,006 passengers a year. Greater Manchester's ten bands
# were hand-assigned and no script could even reproduce them.
#
# Proven able to fail in BOTH holders: it reported 89 disagreements before the
# correction and 0 after, and it reads the site and the Lambda separately so a
# one-sided edit reds it. Four different spellings of the same record exist
# across the two files; --check parses all four, and a parser that knew only
# one silently read every borough as absent.
check "aircraft bands == geometry"     python scripts/build_aircraft_bands.py --check
# Borough crimeRate against ONS Table C4, all eleven CITY_PFA cities in one
# run. The --check has existed since 2026-08-03 and no preflight stage ever
# ran it - crime was one of three scoring inputs whose check sat outside the
# gate - and until 2026-08-24 it could exit 0 having compared ZERO boroughs,
# so wiring it in without the per-city floor would have gated nothing.
#
# Same data-dependency shape as the HPI stage above: needs only
# data/ons_pfa_tables.xlsx, which load_table() fetches once from ONS and
# caches. Measured 2026-08-24: 1.7s for all eleven cities with the workbook
# cached. Proven able to fail per city: a renamed London borough key floors
# london while the other ten still compare, and the run exits 1.
check "crime == ONS Table C4"          python scripts/refresh_crime_from_ons.py --check --all
# THE ONLY FLOOD GATE THAT CROSSES A SOURCE BOUNDARY.
#
# `build_borough_bands.py --check` re-derives each borough's flood percentage
# by sampling the same GeoTIFF the published figures came from, so the two
# things it compares are the file and itself. It reported agreement for the
# entire period the mosaics were mis-georeferenced - flood was SCORED from
# 26 Aug and banded on the map from 11 Aug, wrong in 10 of 11 cities, with
# every gate green. A re-derivation is not a verification.
#
# This asks the Environment Agency's own GetFeatureInfo what it publishes at a
# British National Grid coordinate and compares it to what our raster says
# there. Samples are drawn from the ERODED INTERIOR of each class, because
# uniform sampling would be another check that cannot fail: 93% of a mosaic is
# `none`, and a random point agrees on both sides whatever the georeferencing.
#
# net_check: it needs the network. Proven red against the pre-2026-08-30
# mosaics and green against the re-fetched ones - run it with --mosaic-dir
# pointed at a backup to reproduce that.
# --per-class 4, not the script default of 6. Measured 2026-08-30: at 6 this
# stage took ~25 minutes inside preflight, which is long enough that someone
# reaches for --skip-e2e, and a gate that gets skipped protects nothing. 4 is
# still one above the MIN_COMPARED floor of 3, and the top-up pass adds more
# points when the service throttles, so the cut costs evidence only when the
# service is healthy - exactly when the extra points were least needed.
net_check "flood == EA service (georef)" python scripts/check_flood_georef.py --all --per-class 4
# The OUTPUT check the Manchester incident needed and nothing had. Input parity
# (tests/test_borough_data_parity.py) passed throughout that defect, because
# both holders HELD the data and the site never loaded it into the object it
# scores from - all ten boroughs were adrift by up to 1.5 points with nothing
# raised. This drives the real page and reads the number it renders.
#
# Runs against SOURCE, so it gates a deploy; tests/site-api-parity.mjs is the
# live counterpart and catches a bad one. It is also the gate a city must pass
# before leaving BACKEND_ONLY_CITIES, which is a one-way door.
# Proven able to fail: a single site-side band edit reds it at -3.8.
check "site == Lambda (91 boroughs)"   node tests/borough-score-parity.mjs
# The 285 curated postcode-district labels are the one output of the
# neighbourhood builder that nothing downstream can contradict: a wrong price
# reds "prices == HM Land Registry", a wrong borough shows up as a borough with
# no neighbourhoods, but "L8: Chelsea" would simply render. This asserts every
# label against that district's own published MSOA names, so a name that
# belongs somewhere else cannot ship.
#
# Reads data/district-msoa-names.json, which is checked in for this reason -
# the check needs neither the 806 MB NSPL nor a network.
#
# Proven able to fail in both directions: a transplanted name ("BS8: Didsbury")
# reds it, and so does a dict keyed to a city nobody looks up, which is how 163
# of the names were dead on arrival while the check still read all-green.
check "area names == MSOA names"       python scripts/build_city_neighbourhoods.py --check-names
# Author preference, enforced 2026-08-03: no em dashes on any deployed page.
# 184 were removed in one pass; a gate is the only thing that keeps them out.
check "no em dashes (9 pages)"         sh scripts/check_no_em_dash.sh

# privacy.html §2d promises 30-day log retention. This asserts AWS actually
# does that. BLOCKING, and currently RED on purpose.
#
# The repo is PUBLIC, so a claim in privacy.html is published on push, not on
# deploy — which is why this guards the commit and not just the CloudFront
# upload. The previous claim ("7 days") was never true at any point in the
# project's life and survived for months precisely because nothing compared the
# document to the infrastructure.
#
# There are two honest ways to make this green, and no bypass flag:
#   1. apply the retention policy (console: DRAFT_security_retention_passage.md §1)
#   2. revert §2d to the interim wording in that file's §2b, Version B
check "log retention == privacy.html"  sh scripts/check_log_retention.sh

# Fonts were self-hosted on 2026-08-05 to close a UK GDPR Chapter V item (every
# page load transferred the visitor's IP to Google in the US). That touched the
# CSP on nine pages, and every way it can break is SILENT: a bad path, a
# too-strict font-src, or a variable font declared with too narrow a weight
# range all still render a plausible-looking page in a fallback font.
#
# Serves the repo locally, so this validates SOURCE and runs before a deploy.
# Proven able to fail: with fonts/inter.woff2 removed it exits 1 on a 404.
check "self-hosted fonts (9 pages)"    node tests/fonts-selfhosted.mjs

# The extension's coordinate extraction is the only code in the repo that reads
# a third party's markup, and it fails SILENTLY — a Rightmove redesign turns
# every listing into "no panel" with no error raised anywhere. Wired in on the
# day it was written rather than left as a file nothing runs. It needs no jsdom;
# extract.js touches four DOM surfaces and the suite shims exactly those.
#
# This proves the code is not broken. It CANNOT prove Rightmove still looks like
# the fixtures — only a browser can, via scripts/build_extraction_probe.sh.
check "extension extraction"           node tests/extension-extraction.mjs

# The three stages below that need the network are marked with net_check.
# Everything else here runs against the working tree and must NOT be
# skippable: these are the gates that stop a defect reaching the deploy.
# --workers=2 is load-bearing, not tuning. The suite's baseURL is the live
# CloudFront site; at the default worker count the parallel burst produces
# timeouts indistinguishable from real assertion failures (measured
# 2026-07-27: 14 failed / 2 passed at default, 16 passed at --workers=2).
net_check "Playwright e2e (--workers=2)" npx playwright test --workers=2 --reporter=line

# Loads the extension into a real Chromium and drives it against a fixture
# served AT the rightmove.co.uk URL, so the content script's match pattern
# fires without a single request reaching Rightmove. Grouped under --skip-e2e
# because it launches a browser and calls the live /transport and /nhs.
#
# It cannot run under Playwright's normal headless mode: that uses
# chromium_headless_shell, which does not load extensions at all, so every
# assertion would fail for reasons unrelated to the code. The suite passes
# --headless=new itself.
net_check "extension e2e"             node tests/extension-e2e.mjs

# Loads the live site at ten viewports, 320px to 1920px, and fails on
# horizontal overflow OR on a control stranded past the viewport edge with no
# scrollable ancestor. The first is the failure that matters on a phone and
# the one least likely to be noticed otherwise: the page still works, it just
# drifts sideways, and nobody testing at 1440px will ever see it.
#
# The second was added 2026-08-11 because the first could not see it. The
# audit had always BUILT a list of clipped elements and only PRINTED it when
# the page itself scrolled sideways — so the city chips, clipped by the map
# container's overflow:hidden, left this stage reading "ok" at all ten
# viewports while three of eight UK cities could not be tapped at 320px.
# Proven red against the pre-fix live site (5 of 10 viewports) and green
# against the fixed source.
#
# Tap-target findings are printed but do not fail the run. They need judgement
# rather than a threshold — the site footer is 8px uppercase chrome, hidden
# entirely below 900px, and forcing it to 24px would triple its height to fix
# a desktop-only mouse target. A gate that demanded that would be overruled
# every time it fired, which is how a gate stops being read.
#
# SPLIT ACROSS SOURCE AND LIVE on 2026-08-11, the same split a11y already
# makes (tests/a11y-source.mjs blocking, the CloudFront spec catching a bad
# deploy). The BLOCKING run is against the working tree and lives in the
# local-server block below; the live run is ADVISORY, at the bottom.
#
# The reason is not convenience. Pointed at live, this stage goes red on a
# tree that has ALREADY FIXED the defect and stays red until a deploy, so
# "do not commit past a red gate" would forbid committing the fix for the
# very thing it is complaining about. Blocking on source gates the deploy;
# the advisory live run keeps reporting production's real state, which is
# exactly what `deployed == source` is already advisory for.

# LOCAL smoke, and the distinction from every other e2e stage here is the
# point: those hit the DEPLOYED site, so a broken index.html in the working
# tree passes all of them. tests/smoke-local.mjs has existed since the
# 2026-07-30 vendoring work and was in no gate at all — the one test that
# could catch a regression before it shipped was the one nothing ran.
#
# It loads the working tree over a throwaway static server, paints London, NYC
# and Greater Manchester in detail, and asserts the CITY_DATA registry rejects
# an unknown city instead of silently serving London's data under its name.
#
# The count that used to be in this label was load-bearing and went stale
# anyway: it read "both cities" through the session in which Greater
# Manchester became the third, then "3 cities" while the app carried NINE, so
# six cities sat outside the only pre-deploy registry gate. The registry
# assertions inside now ENUMERATE CITY_DATA rather than naming three cities,
# and "every city switches" below covers rendering, so there is no longer a
# number here to fall behind.
smoke_port=8123
python -m http.server "$smoke_port" --bind 127.0.0.1 >/dev/null 2>&1 &
smoke_pid=$!
# Wait for the socket rather than sleeping a guessed interval.
smoke_tries=0
until curl -sf "http://127.0.0.1:$smoke_port/index.html" -o /dev/null; do
  smoke_tries=$((smoke_tries + 1))
  [ "$smoke_tries" -gt 30 ] && break
  sleep 1
done
check "local smoke + registry"        node tests/smoke-local.mjs
# DEGRADED PATHS: a stalled network, an offline launch, and a partial TfL
# outage. Wired in 2026-08-27, having been in NO gate at all since it was
# written - not preflight, not package.json, not the Makefile. The one file
# dedicated to "the fallback shipped untested" was itself untested, and it
# had been dying on Node 24 partway through (a route aborted after unroute
# -> unhandled rejection -> fatal), exiting 1 having run 10 of 19 checks.
# That reads as a FAILING gate rather than a crashed one, which is the same
# shape as the undici crash that had `responsive, source` reporting FAIL on
# zero pages.
#
# Pointed at SOURCE, not live, for the reason spelled out above this block:
# against CloudFront it reds on a tree that has already fixed the defect and
# stays red until a deploy, so "do not commit past a red gate" would forbid
# committing the very fix it is asking for. Blocking on source gates the
# deploy. The trade is that Chromium ignores offline emulation on loopback,
# so the two offline-paint checks pass spuriously here; "nyc geojson is
# precached" is the one that genuinely reds locally, and it is the assertion
# that actually guards cache.addAll() being atomic.
check "degraded + offline fallbacks"  env "SMOKE_BASE=http://127.0.0.1:$smoke_port" node tests/failure-path.mjs
# Both ported from the core-cities spike branch with the country tier, and
# both serve the repo themselves rather than reusing the server above.
# locator-verify is proven able to fail: remove data/uk-locator.json and
# London and Manchester report markers=0 land=0.
check "locator inset"                 node tests/locator-verify.mjs
check "selector tiers do not overlap" node tests/selector-widths.mjs
# Clicks EVERY chip in CITY_DATA and asserts the city renders the number of
# outlines its own boundary file declares, with no page error. Added
# 2026-08-11: nothing in the suite had ever clicked a city chip, and two
# defects were living in that gap on the LIVE site — a second registry that
# held three cities while CITY_DATA held nine, and corridors ported from the
# Lambda under its `coords` key when the renderer reads `.coordinates`.
# Six of nine cities threw on selection and every gate was green.
#
# Deliberately data-driven, unlike the stage above: no count to keep in step,
# so city ten is covered the day it is added. Both defects re-proven red.
check "every city switches"           node tests/city-switch.mjs
# DOES THE MAP FIT THE BOX IT IS DRAWN IN? Added 2026-08-24.
#
# "every city switches" counts outlines, and the count is right whether or
# not you can see them. responsive.mjs asks whether the DOCUMENT overflows
# and whether a CONTROL is stranded, covered or clipped - and an SVG path
# drawn outside its own SVG box is none of those. So every gate here was
# green while 41% of London rendered off-screen at 320x568, Heathrow 140px
# past the left edge, in all eleven cities. 53 of 90 city/viewport
# combinations were failing.
#
# Asserts both directions: nothing may spill outside the box, and the
# geography must fill a floor of it - "nothing is clipped" is otherwise
# satisfiable by drawing the map tiny. Includes a LANDSCAPE viewport,
# which is where the old code took its desktop branch and failed in the
# vertical axis while every portrait phone failed in the horizontal one.
check "map fits its box"              node tests/map-fit.mjs
# Types a real postcode in a NON-LONDON city, which nothing had ever done.
# "every city switches" clicks the chip and checks the MAP;
# borough-score-parity compares SCORES. Both passed while nine UK cities
# answered an area search with "NYC subway data coming soon".
check "UK cities get UK panel content" node tests/uk-city-panel.mjs
# 99 static area pages are the site's only indexable surface; thin or
# duplicated ones are worse than none (doorway pages), so this asserts
# CONTENT and that the sitemap agrees in both directions.
check "area pages carry real data"    node tests/area-pages.mjs
# The area pages BAKE their scores at build time - that is what makes them
# indexable without JS, and what lets them go stale when a data vintage
# lands. No other gate can see it: `area pages carry real data` checks
# richness, and `deployed == source` compares repo to CDN, which after a
# roll are BOTH stale and therefore agree. One batch request covers all 99,
# so this costs 1 CI quota unit per run rather than 99.
net_check "area pages match the live API" node tests/area-page-freshness.mjs
# A borough choropleth must paint exactly the boroughs that hold a reading.
# Added 2026-08-11: all three fill layers ended their lookup with `|| 'moderate'`
# or `|| 'low'`, so every borough of the seven non-London UK cities was painted
# one confident colour for data nobody had. Nothing caught it because nothing
# compared the RENDER to the DATA - pytest never opens index.html and the
# Playwright specs assert the site against itself, so a fabricated fill is
# self-consistent. Fails in BOTH directions: over-painting is an invented
# default, under-painting is a borough whose data the map cannot find.
check "layers paint only real data"   node tests/layer-honesty.mjs
check "panel says what it measured"  node tests/panel-caveat.mjs
# The blocking half of the responsive audit, against the working tree over the
# server started above. See the long note on the advisory live run further up.
# Covers EVERY public page since 2026-08-22, not just the homepage - widening
# it found privacy.html, changes.html and the status page all scrolling
# sideways on a phone. The label carries no count on purpose; the harness
# prints how many page/viewport pairs it actually ran.
check "responsive, source"            node tests/responsive.mjs "http://127.0.0.1:$smoke_port/index.html"
# WCAG over the SOURCE tree, on its own server on 8923 with the CloudFront
# extensionless rewrite reproduced, so /pricing resolves the way the origin
# resolves it.
#
# The Playwright a11y spec above scans CloudFront, so until 2026-08-10 an
# accessibility regression could not be caught until it was already serving to
# users - which is exactly how the locator inset shipped `role="img"` around
# ten focusable markers and failed this gate the next morning, from
# production. The two are complementary: this one gates the deploy, that one
# catches a bad or partial deploy.
#
# Proven able to fail: flipping #locator-svg back to role="img" reds it with
# "[SERIOUS] nested-interactive" on `/` alone and exits 1.
check "WCAG source scan (9 pages)"    node tests/a11y-source.mjs
kill "$smoke_pid" 2>/dev/null || true

echo
echo "Advisory:"

# Prettier is NOT a blocking gate here, and saying so out loud is the point.
# Measured 2026-07-27: every HTML/JS file in the repo deviates, and bringing
# index.html into line is a 19,205-line diff on an 8,462-line deployed file
# (it would grow to 10,743 lines). That is a deliberate decision to review,
# not a chore to slip into a pre-commit hook. Reporting it as blocking would
# make the gate permanently red, which is how a gate gets ignored.
advise "Prettier (all files deviate)"   npm run format:check

# npm audit covers the frontend/tooling tree. The BACKEND has no PyPI
# supply-chain surface at all: no Lambda has a requirements.txt, every handler
# is stdlib plus the runtime's boto3. The old gate ran pip-audit over
# `backend/lambdas/*/requirements.txt`, which matches nothing, and swallowed
# the result with `|| true` — a no-op that rendered as a green tick.
advise "npm audit"                      npm audit

# Progress 8 against DfE KS4 2023/24 Revised. Advisory, NOT blocking, on the
# data dependency alone: the check itself is offline and fast (0.2s measured
# 2026-08-24, with a compared-nothing floor since 2026-08-22), but its input
# KS4 bundle is gitignored and CANNOT be auto-fetched the way the HPI csv can -
# the Explore Education Statistics host answers 403 to a non-browser
# User-Agent - so a blocking stage would fail every fresh clone on a file no
# command restores.
#
# THE LABEL SAID 2022/23 UNTIL 2026-08-28, one day after the roll, which is the
# staleness this repo keeps paying for: a gate whose NAME asserts a vintage has
# to be remembered, and the reason given for not worrying about drift ("2022/23
# is the TERMINAL vintage until ~2027") was itself the claim the roll disproved.
# 2023/24 genuinely is terminal until 2026/27 - the suspended cohorts are
# 2024/25 and 2025/26 - but that is a fact to re-check, not to lean on. The
# pytest parity suite blocks on the two holders disagreeing, and
# ProvenanceVintageTests now blocks on any city naming a vintage we do not serve.
advise "p8 == DfE KS4 2023/24"          python scripts/build_progress8.py --check

# The five borough band fields (road noise, air quality, flood, transport,
# healthcare) against their sources. Advisory for the same reason as p8, at
# larger scale: the check re-derives every band from the 806 MB NSPL plus the
# DEFRA/EA rasters, NaPTAN and the NHS GP register - all gitignored, restored
# only by their own fetch scripts and loaders - and a fresh clone has none of
# them. 59s measured 2026-08-24 with the data present, during which it still
# reds on any drifted band before a commit.
advise "borough bands == sources"       python scripts/build_borough_bands.py --check

# Compares all 14 publicly-served files against what CloudFront actually
# serves. Advisory because drift is the EXPECTED state between committing and
# deploying — blocking it would go red on nearly every run and be ignored
# inside a week, the same trap the Prettier line above describes.
#
# It exists because on 2026-08-04 `privacy.html` was corrected in git, removing
# a false claim that request data "never leaves UK AWS infrastructure", and
# then sat unpublished — the live policy kept saying something untrue and
# nothing would have noticed. Audit finding 38 is the same defect at scale:
# eleven live files had no deploy command at all, so `api/index.html` sold the
# product on retired claims for months. Deploy targets now exist for all of
# them; a target only helps if somebody runs it, and this is what notices when
# nobody did.
#
# Skipped with --skip-e2e: it hits the network, same as the Playwright stage.
if [ "$SKIP_E2E" -eq 0 ]; then
  # No count in the label. It read "14 pages" while the script checked 16, which
  # is the same scheduled-staleness bug the local-smoke stage carried as
  # "3 cities" against a nine-city app. The script prints its own denominator
  # when it fails; a number here can only ever go stale.
  advise "deployed == source"            sh scripts/check_deploy_drift.sh

  # Compares the score the LIVE SITE renders against what /v1/score returns for
  # the same postcode — the only check that reads the OUTPUT rather than the
  # inputs. Three site/API divergences have shipped, and each survived because
  # the existing guards compare geometry, weights or components: on SW11 1AA
  # every component matched exactly while the totals differed, because the site
  # recombined already-rounded values.
  #
  # Advisory, matching the drift check above, for two reasons: it drives a real
  # browser against the live site (this repo has documented Playwright false
  # failures under load) and it compares deployed-against-deployed, so it is
  # reporting on production rather than on the commit in hand. Promote it to
  # `check` once it has a track record of not flaking — it is written to exit 1
  # only on a MEASURED disagreement, and to fail loudly rather than pass quietly
  # if too few probes return.
  advise "site == /v1/score (6 postcodes)" node tests/site-api-parity.mjs

  # The live half of the responsive audit. Reports what visitors actually get;
  # the blocking half runs the same file against the working tree.
  # Advisory for the same reason as the drift check above: it is describing
  # production, not the commit in hand, so it stays red between fixing a layout
  # defect and deploying the fix.
  advise "responsive, live"              node tests/responsive.mjs
fi

echo
echo "===================="
if [ -n "$FAILED" ]; then
  echo "RESULT: FAIL"
  echo "$FAILED" | tr '|' '\n' | sed '/^$/d' | sed 's/^/  failed: /'
  echo
  echo "Fix these before committing. Do not commit past a red gate."
  exit 1
fi

# A PASS that skipped stages must SAY so. Under --skip-e2e this printed a
# bare "RESULT: PASS" while three network gates had not run, and one of
# them (area pages match the live API) is the only gate in the suite that
# can see a site/API divergence.
if [ -n "$SKIPPED_NET" ]; then
  echo "RESULT: PASS (INCOMPLETE - network stages skipped)"
  echo "$SKIPPED_NET" | tr '|' '
' | sed '/^$/d' | sed 's/^/  not run: /'
  echo "  Re-run without --skip-e2e before committing."
else
  echo "RESULT: PASS"
fi
if [ -n "$ADVISORY" ]; then
  echo "$ADVISORY" | tr '|' '\n' | sed '/^$/d' | sed 's/^/  advisory: /'
fi
exit 0
