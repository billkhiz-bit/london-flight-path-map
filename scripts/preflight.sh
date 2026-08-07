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
#   sh scripts/preflight.sh --skip-e2e   # skip Playwright (hits the live site)
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

if [ "$SKIP_E2E" -eq 1 ]; then
  printf '  %-34s%s\n' "Playwright e2e" "SKIPPED (--skip-e2e)"
  printf '  %-34s%s\n' "extension e2e" "SKIPPED (--skip-e2e)"
else
  # --workers=2 is load-bearing, not tuning. The suite's baseURL is the live
  # CloudFront site; at the default worker count the parallel burst produces
  # timeouts indistinguishable from real assertion failures (measured
  # 2026-07-27: 14 failed / 2 passed at default, 16 passed at --workers=2).
  check "Playwright e2e (--workers=2)"  npx playwright test --workers=2 --reporter=line

  # Loads the extension into a real Chromium and drives it against a fixture
  # served AT the rightmove.co.uk URL, so the content script's match pattern
  # fires without a single request reaching Rightmove. Grouped under --skip-e2e
  # because it launches a browser and calls the live /transport and /nhs.
  #
  # It cannot run under Playwright's normal headless mode: that uses
  # chromium_headless_shell, which does not load extensions at all, so every
  # assertion would fail for reasons unrelated to the code. The suite passes
  # --headless=new itself.
  check "extension e2e"                 node tests/extension-e2e.mjs

  # Loads the live site at ten viewports, 320px to 1920px, and fails ONLY on
  # horizontal overflow. That is the failure that matters on a phone and the one
  # least likely to be noticed otherwise: the page still works, it just drifts
  # sideways, and nobody testing at 1440px will ever see it.
  #
  # Tap-target findings are printed but do not fail the run. They need judgement
  # rather than a threshold — the site footer is 8px uppercase chrome, hidden
  # entirely below 900px, and forcing it to 24px would triple its height to fix
  # a desktop-only mouse target. A gate that demanded that would be overruled
  # every time it fired, which is how a gate stops being read.
  check "responsive (10 viewports)"     node tests/responsive.mjs
fi

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
  advise "deployed == source (14 pages)" sh scripts/check_deploy_drift.sh

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

echo "RESULT: PASS"
if [ -n "$ADVISORY" ]; then
  echo "$ADVISORY" | tr '|' '\n' | sed '/^$/d' | sed 's/^/  advisory: /'
fi
exit 0
