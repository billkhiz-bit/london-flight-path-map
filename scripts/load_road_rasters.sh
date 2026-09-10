#!/bin/sh
# Load the per-postcode ROAD Lden tier for every English city we score.
#
# WHY. Until 2026-09-10 the road pass had been run against the London mosaic
# alone: SW11 answered 69.1 dB on /v1/environment while M2 4NG answered None
# with "not measured, or still being loaded", though all eleven city mosaics
# had been on disk since August. Measured before loading
# (scripts/probe_road_raster_coverage.py): 100% of live postcodes in every
# English city are inside their mosaic and surveyed; 549,336 readings and
# 11,281 surveyed-quiet postcodes across the ten cities plus London.
#
# ROAD MODE WRITES TWO ATTRIBUTES. A reading goes to roadLdenDb. A DEFRA zero -
# surveyed, under the lowest mapped band, 40.00 dB in every mosaic - goes to
# roadLdenBelowDb as a BOUND, and the Lambda publishes it as roadNoiseBelowDb
# with a notice that says quiet rather than missing. The loader asserts the
# raster's lowest positive value is 40.00 before writing a single bound.
#
# --live-only, deliberately. /v1/score never reads roadLdenDb and
# /v1/environment reaches a postcode only through a reverse geocode, which
# returns live postcodes, so a road row for a terminated postcode serves
# nobody - and terminated rows are 61% of the scan. The AIRCRAFT runbook must
# not copy this flag: /v1/score does read ldenDb off a terminated postcode.
#
# LONDON LAST. It already holds its readings from the August pass; re-running
# it rewrites those with identical values and adds the 1,347 markers it never
# had. Cheapest city to lose if this is interrupted, so it goes at the end.
#
# NO DEPLOY STEP. Nothing on the frontend reads this tier; the Lambda reads the
# table live, so each postcode gains its value the moment it is written. The
# Lambda that publishes the BOUND is a separate SAM deploy, safe in either
# order: an old Lambda ignores the attribute, a new one finds no marker and
# says "not measured" until the row lands.
#
# Resumable: each raster keeps its own checkpoint, so re-running after any
# death picks up where it stopped. Safe to run twice.
#
#   sh scripts/load_road_rasters.sh                    # all eleven
#   CITIES="bristol" sh scripts/load_road_rasters.sh   # one
#   tail -f roadload.log                               # watch
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT" || exit 1
LOG="$ROOT/roadload.log"

CITIES="${CITIES:-nottingham teesside leicester tyneandwear bristol southyorkshire merseyside westmidlands westyorkshire manchester london}"

say() { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" | tee -a "$LOG"; }

say "=== road raster load starting: $CITIES ==="
FAILED=""
for city in $CITIES; do
  tif="data/defra_road_lden_${city}.tif"
  if [ ! -f "$tif" ]; then
    say "MISSING $tif - skipping"
    FAILED="$FAILED $city"
    continue
  fi
  say "loading $city"
  if AWS_PROFILE=flightmap python -u scripts/load_defra_raster.py \
      --geotiff "$tif" --attribute roadLdenDb --live-only >> "$LOG" 2>&1; then
    say "  $city done"
  else
    say "  $city FAILED (exit $?)"
    FAILED="$FAILED $city"
  fi
done

if [ -n "$FAILED" ]; then
  say "FAILED:$FAILED - re-run this script; it resumes."
  exit 1
fi
say "all cities loaded"
say "verify: curl -s 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod/v1/environment?lat=53.4808&lon=-2.2426' | python -m json.tool"
