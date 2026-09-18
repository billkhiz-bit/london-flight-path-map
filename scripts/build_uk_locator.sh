#!/bin/sh
# Regenerate data/uk-locator.json, the England & Wales silhouette in the
# locator inset, from the ONS LAD boundaries and each city's own boundary file.
#
#     sh scripts/build_uk_locator.sh
#
# The checked-in file predated scripts/build_locator.py and could not be
# reproduced from anything (a jagged raster trace on a 130x168 frame, source
# unknown); this replaces it with one the generator can rebuild, first run
# 2026-09-18. Two things are DERIVED rather than typed: the country filter is
# the ONS code prefix (E and W), and every marker is the bbox centre of the
# city's data/<city>-boroughs.json - the same files the map draws - so adding
# a city here is one line and cannot put its marker somewhere the map is not.
# Marker NAMES must match CITY_DATA labels and LOCATOR_TO_CITY in index.html:
# tests/locator-verify.mjs derives its clickable count from that match.
#
# data/uk-lad.json (19 MB, gitignored) is the ONS LAD13 boundary GeoJSON; the
# per-city files are checked in.
set -eu
cd "$(dirname "$0")/.."

python scripts/build_locator.py --src data/uk-lad.json --out data/uk-locator.json \
  --region "England & Wales" --unit "core cities" --projection equirect \
  --name-key LAD13NM --code-key LAD13CD --keep-prefix E W --width 130 \
  --city-bbox "London:data/london-boroughs.json" \
  --city-bbox "Greater Manchester:data/manchester-boroughs.json" \
  --city-bbox "West Midlands:data/westmidlands-boroughs.json" \
  --city-bbox "West Yorkshire:data/westyorkshire-boroughs.json" \
  --city-bbox "Merseyside:data/merseyside-boroughs.json" \
  --city-bbox "South Yorkshire:data/southyorkshire-boroughs.json" \
  --city-bbox "Tyne and Wear:data/tyneandwear-boroughs.json" \
  --city-bbox "Bristol:data/bristol-boroughs.json" \
  --city-bbox "Nottingham:data/nottingham-boroughs.json" \
  --city-bbox "Cardiff:data/cardiff-boroughs.json" \
  --city-bbox "Leicester:data/leicester-boroughs.json" \
  --city-bbox "Teesside:data/teesside-boroughs.json"
