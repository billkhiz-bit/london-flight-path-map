#!/bin/sh
# Load the seven per-airport DEFRA aircraft Lden coverages, then ship the
# matching client dataset.
#
# WHY A CHAINED SCRIPT RATHER THAN SEVEN COMMANDS. The table and the client
# file hold THE SAME measurements, and the site reads one while /v1/score reads
# the other. Whichever lands first, the surfaces disagree until the second one
# does - by about 2.2 score points on 7,339 postcodes, measured. That window is
# unavoidable; leaving it open for hours because the deploy was a separate
# manual step is not. So the deploy is chained to the load and gated on it.
#
# ORDER IS LOAD THEN DEPLOY, deliberately. Loading first flips /v1/score; the
# site keeps answering from geometry until the deploy, which is the status quo
# it has served since launch. Deploying first would flip the SITE onto readings
# the API cannot yet reproduce, which is the same divergence pointing at the
# surface users actually look at.
#
# WAITS FOR THE AIR-QUALITY LOADER. Both write to london-flight-map-noise-raster
# through per-item UpdateItems, so running them together just halves both. The
# air-quality loader deletes its checkpoint when it finishes; that is the signal.
#
# Resumable: each raster keeps its own checkpoint, so re-running after any death
# picks up where it stopped. Safe to run twice.
#
#   sh scripts/load_aircraft_rasters.sh              # wait, load, deploy
#   SKIP_WAIT=1 sh scripts/load_aircraft_rasters.sh  # do not wait for air quality
#   NO_DEPLOY=1 sh scripts/load_aircraft_rasters.sh  # load only

set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT" || exit 1

AQ_CHECKPOINT="$ROOT/.defra_aq_checkpoint"
LOG="$ROOT/aircraftload.log"

# Seven, not twelve. Heathrow and London City are excluded because the London
# region export already covers London better (35,352 postcodes against their
# 17,330), and Gatwick, Luton and Stansted are excluded because all 3,704 of
# their readings land outside LAD_TO_BOROUGH - Surrey, Beds and Essex - where
# /v1/score cannot resolve a city at all. Measured by
# scripts/probe_aircraft_raster_coverage.py, not assumed.
RASTERS="birmingham bristol eastmidlands leedsbradford liverpool manchester newcastle"

say() { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" | tee -a "$LOG"; }

say "=== aircraft raster load starting ==="

if [ -z "${SKIP_WAIT:-}" ]; then
  while [ -f "$AQ_CHECKPOINT" ]; do
    say "air-quality loader still running ($(cat "$AQ_CHECKPOINT" 2>/dev/null) rows); waiting 5 min"
    sleep 300
  done
  say "air-quality loader finished; starting aircraft rasters"
fi

FAILED=""
for name in $RASTERS; do
  tif="data/defra_aircraft_lden_${name}.tif"
  if [ ! -f "$tif" ]; then
    say "MISSING $tif - skipping"
    FAILED="$FAILED $name"
    continue
  fi
  say "loading $name"
  if AWS_PROFILE=flightmap python -u scripts/load_defra_raster.py --geotiff "$tif" >> "$LOG" 2>&1; then
    say "  $name done"
  else
    say "  $name FAILED (exit $?)"
    FAILED="$FAILED $name"
  fi
done

if [ -n "$FAILED" ]; then
  say "FAILED:$FAILED"
  say "NOT DEPLOYING. The client dataset must not be served while the table is"
  say "incomplete: the site would score postcodes DEFRA-measured that /v1/score"
  say "still answers from geometry. Re-run this script; it resumes."
  exit 1
fi

say "all seven rasters loaded"

if [ -n "${NO_DEPLOY:-}" ]; then
  say "NO_DEPLOY set - stopping before the deploy"
  exit 0
fi

say "deploying client dataset + index.html + sw.js"
AWS_PROFILE=flightmap aws s3 cp data/aircraft-quiet-regions.json \
  s3://london-flight-map-frontend/data/aircraft-quiet-regions.json \
  --content-type "application/json" --cache-control "no-cache" \
  --region eu-west-2 >> "$LOG" 2>&1 || { say "data deploy FAILED"; exit 1; }
AWS_PROFILE=flightmap aws s3 cp index.html \
  s3://london-flight-map-frontend/index.html \
  --content-type "text/html" --region eu-west-2 >> "$LOG" 2>&1 \
  || { say "index deploy FAILED"; exit 1; }
AWS_PROFILE=flightmap aws s3 cp sw.js \
  s3://london-flight-map-frontend/sw.js \
  --content-type "application/javascript" --region eu-west-2 >> "$LOG" 2>&1 \
  || { say "sw deploy FAILED"; exit 1; }
AWS_PROFILE=flightmap aws cloudfront create-invalidation \
  --distribution-id EGSSPJKLFL33M --paths "/*" >> "$LOG" 2>&1 \
  || { say "invalidation FAILED"; exit 1; }

say "=== done: loaded and deployed ==="
