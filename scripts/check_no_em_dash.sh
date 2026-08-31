#!/usr/bin/env sh
# No em dashes in any deployed page.
#
# Added 2026-08-03 at the author's request. 184 were removed in one pass across
# the eight deployed HTML files; without a gate they return one edit at a time,
# because an em dash is the default thing both a word processor and a language
# model reach for. Enforcing it is a one-line grep, so there is no reason to
# rely on remembering.
#
# Scope is deployed pages only. Markdown docs are deliberately NOT covered:
# METHODOLOGY, CHANGELOG and the audit reports use them heavily, they are not
# "the website", and rewriting them was not what was asked for. Widen this list
# if that changes.
#
# En dashes are not checked. They were not part of the request, and a few are
# legitimately numeric ranges.

set -u
cd "$(dirname "$0")/.." || exit 2

# U+2014, built with printf so this file itself stays ASCII and cannot trip.
EM=$(printf '\342\200\224')

PAGES="index.html api/index.html pricing.html privacy.html changes.html
       terms.html
       score-demo/index.html score-demo/status.html score-demo/api-docs.html"

# THE 100 area/ PAGES ARE DEPLOYED TOO (2026-08-31, audit I13). They were
# outside this list entirely - 100 of the site's ~109 public URLs, and the only
# ones a search visitor lands on cold. Measured clean today, which is exactly
# when to gate them: they are generated, so one edit to the template's copy
# would put an em dash on all 99 at once. DERIVED by glob, never listed, so a
# twelfth city is covered the day it is generated.
AREA_PAGES=$(find area -name 'index.html' 2>/dev/null | sort)

found=0
scanned=0
missing=''
for f in $PAGES; do
  # A MISSING PAGE IS A FAILURE, NOT A SKIP. This was `[ -f "$f" ] || continue`,
  # so renaming terms.html to terms-and-conditions.html (and adding three em
  # dashes to it) left this printing nothing and exiting 0. A page in this list
  # that is not on disk means the list is wrong or the page moved; either way
  # the claim "no em dashes on the deployed pages" is no longer being made
  # about that page.
  if [ ! -f "$f" ]; then
    missing="$missing $f"
    continue
  fi
  scanned=$((scanned + 1))
  n=$(grep -c "$EM" "$f" 2>/dev/null || true)
  # grep -c prints 0 and exits 1 on no match; normalise.
  [ -z "$n" ] && n=0
  if [ "$n" -gt 0 ]; then
    found=$((found + n))
    echo "  $f: $n em dash(es)"
    grep -n "$EM" "$f" | head -3 | sed 's/^/      /'
  fi
done

for f in $AREA_PAGES; do
  scanned=$((scanned + 1))
  n=$(grep -c "$EM" "$f" 2>/dev/null || true)
  [ -z "$n" ] && n=0
  if [ "$n" -gt 0 ]; then
    found=$((found + n))
    echo "  $f: $n em dash(es)"
  fi
done

if [ -n "$missing" ]; then
  echo "FAIL: listed page(s) not on disk:"
  for f in $missing; do echo "  $f"; done
  echo "  A page this check cannot open is a page it is not checking."
  exit 1
fi

# A FLOOR. Zero files scanned used to be a silent PASS - running this in a tree
# holding the script and no pages printed nothing and exited 0.
if [ "$scanned" -lt 100 ]; then
  echo "FAIL: scanned only $scanned file(s); expected at least 100"
  echo "  (9 public pages plus the generated area/ set). A sweep that opened"
  echo "  almost nothing must not report a clean result."
  exit 1
fi

if [ "$found" -gt 0 ]; then
  echo "  $found em dash(es) in deployed pages. Use a comma, a hyphen, or a full stop."
  exit 1
fi
echo "PASS: no em dashes across $scanned deployed pages."
exit 0
