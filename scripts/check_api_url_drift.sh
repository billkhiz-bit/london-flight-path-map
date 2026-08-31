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
# extension/background.js added 2026-08-23. It is the extension's ONLY
# API_BASE - every panel fetch goes through it - and it was outside this
# check while tests/*.mjs, which asserts against the same host, was inside.
# So an id rotation would have reddened the e2e without ever naming the file
# holding the stale host.
FILES='index.html changes.html score-demo/index.html score-demo/api-docs.html score-demo/status.html api/index.html js/api-base.js extension/background.js'

# shellcheck disable=SC2086
HOSTS=$(grep -ho "$PATTERN" $FILES tests/*.mjs 2>/dev/null | sort -u)
COUNT=$(printf '%s\n' "$HOSTS" | sed '/^$/d' | wc -l | tr -d ' ')

if [ "$COUNT" -eq 0 ]; then
  echo "FAIL: no API Gateway host found in any surface. Did the files move?"
  exit 1
fi

# PER-FILE FLOOR (2026-08-31, audit I12).
#
# COUNT is the number of distinct MATCHING hosts, so a file that matches
# NOTHING contributes nothing and cannot fail this. Proven: rewrite the API
# base in index.html, changes.html, all three score-demo pages, api/index.html
# and extension/background.js to https://DELETED.example, leave js/api-base.js
# alone, and this printed "PASS: every surface uses <host>" and exited 0. It
# detected drift BETWEEN two execute-api ids and never drift AWAY from
# execute-api at all - which is the likelier accident, because that is what a
# find-and-replace or a half-finished custom-domain migration produces.
#
# Every one of the eight surfaces carries the host today (measured: 2,2,1,1,1,
# 1,1,1), so requiring one from each is a floor, not a new constraint. The
# tests/*.mjs glob is deliberately NOT included here - those files are a moving
# set and their job is to assert against the host, not to hold it.
MISSING=''
for f in $FILES; do
  if [ ! -f "$f" ]; then
    MISSING="$MISSING $f(absent)"
  elif [ "$(grep -c "$PATTERN" "$f" 2>/dev/null)" -eq 0 ]; then
    MISSING="$MISSING $f"
  fi
done
if [ -n "$MISSING" ]; then
  echo "FAIL: these surfaces carry no API Gateway host at all:"
  for f in $MISSING; do echo "  $f"; done
  echo
  echo "  A surface that matches nothing cannot disagree with the others, so"
  echo "  it drops out of the comparison silently. Either it lost the host in"
  echo "  an edit, or it moved and \$FILES needs updating."
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
