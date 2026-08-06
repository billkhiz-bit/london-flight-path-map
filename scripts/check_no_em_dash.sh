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

found=0
for f in $PAGES; do
  [ -f "$f" ] || continue
  n=$(grep -c "$EM" "$f" 2>/dev/null || true)
  # grep -c prints 0 and exits 1 on no match; normalise.
  [ -z "$n" ] && n=0
  if [ "$n" -gt 0 ]; then
    found=$((found + n))
    echo "  $f: $n em dash(es)"
    grep -n "$EM" "$f" | head -3 | sed 's/^/      /'
  fi
done

if [ "$found" -gt 0 ]; then
  echo "  $found em dash(es) in deployed pages. Use a comma, a hyphen, or a full stop."
  exit 1
fi
exit 0
