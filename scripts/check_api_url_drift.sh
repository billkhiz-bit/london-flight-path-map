#!/usr/bin/env sh
# API base-URL drift check (audit I-N5).
#
# Every HTML/JS surface must reference the SAME API Gateway host. When a stack
# is redeployed and API Gateway issues a new id, any file still carrying the
# old host breaks silently — the page renders, the data just never arrives.
# That is exactly the failure shape that hid the dead signup funnel, so it is
# a blocking check rather than a lint.
#
# Extracted from the preflight skill on 2026-07-27 so it is a real file with a
# real exit code, runnable and testable on its own, rather than a fenced block
# in a markdown document that only ever ran inside a model's head.

set -u
cd "$(dirname "$0")/.." || exit 2

PATTERN='https\?://[a-z0-9]\+\.execute-api\.eu-west-2\.amazonaws\.com'
# changes.html added 2026-08-03. It calls /v1/changes, so it can drift like any
# other caller, and it was the ONE public page excluded from this check - a
# blind spot on the page most likely to be edited during a vintage roll.
FILES='index.html changes.html score-demo/index.html score-demo/api-docs.html score-demo/status.html api/index.html js/api-base.js'

# shellcheck disable=SC2086
HOSTS=$(grep -ho "$PATTERN" $FILES tests/*.mjs 2>/dev/null | sort -u)
COUNT=$(printf '%s\n' "$HOSTS" | sed '/^$/d' | wc -l | tr -d ' ')

if [ "$COUNT" -eq 0 ]; then
  echo "FAIL: no API Gateway host found in any surface. Did the files move?"
  exit 1
fi

if [ "$COUNT" -ne 1 ]; then
  echo "FAIL: API base URL drift. Found $COUNT distinct hosts:"
  printf '%s\n' "$HOSTS" | sed 's/^/  /'
  echo
  echo "Occurrences:"
  # shellcheck disable=SC2086
  grep -n "$PATTERN" $FILES tests/*.mjs 2>/dev/null | head -20 | sed 's/^/  /'
  exit 1
fi

echo "PASS: every surface uses $HOSTS"
exit 0
