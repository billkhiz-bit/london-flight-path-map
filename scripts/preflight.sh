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

check "ESLint (index.html)"            npm run lint
check "html-validate (7 pages)"        npm run lint:html
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
check "no em dashes (8 pages)"         sh scripts/check_no_em_dash.sh

if [ "$SKIP_E2E" -eq 1 ]; then
  printf '  %-34s%s\n' "Playwright e2e" "SKIPPED (--skip-e2e)"
else
  # --workers=2 is load-bearing, not tuning. The suite's baseURL is the live
  # CloudFront site; at the default worker count the parallel burst produces
  # timeouts indistinguishable from real assertion failures (measured
  # 2026-07-27: 14 failed / 2 passed at default, 16 passed at --workers=2).
  check "Playwright e2e (--workers=2)"  npx playwright test --workers=2 --reporter=line
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
