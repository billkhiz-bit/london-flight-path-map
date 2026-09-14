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

# Wait on the checkpoint's AGE, not its existence (audit M19). A checkpoint
# outlives the process that wrote it - that is the misreading load_status.sh
# was rewritten to avoid - so a loader that died overnight would have parked
# this runbook for ever, "still running" on a file nobody was writing. The
# loader rewrites its checkpoint every 1000 rows (~65s at the slowest observed
# cadence); 1800s of silence is load_status.sh's own STOPPED verdict.
checkpoint_age() {
  mtime=$(stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null)
  [ -z "$mtime" ] && { echo 999999; return; }
  echo $(( $(date +%s) - mtime ))
}
if [ -z "${SKIP_WAIT:-}" ]; then
  while [ -f "$AQ_CHECKPOINT" ]; do
    age=$(checkpoint_age "$AQ_CHECKPOINT")
    if [ "$age" -ge 1800 ]; then
      say "air-quality checkpoint is ${age}s old - that loader is STOPPED, not running."
      say "Not waiting on a dead process. Restart it (sh scripts/load_status.sh), or"
      say "re-run this with SKIP_WAIT=1 to load the aircraft rasters regardless."
      exit 1
    fi
    say "air-quality loader still running ($(cat "$AQ_CHECKPOINT" 2>/dev/null) rows, checkpoint ${age}s old); waiting 5 min"
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
# Cache-Control on every object, matching the Makefile targets (audit M19).
# index.html and sw.js went up here with NO header, which reverted the 8 Sep
# `no-cache` on the shell: a browser applies heuristic freshness to a page
# with no Cache-Control and can pin the app shell for days, and neither a
# CloudFront invalidation nor an sw.js bump reaches the browser's HTTP cache.
AWS_PROFILE=flightmap aws s3 cp data/aircraft-quiet-regions.json \
  s3://london-flight-map-frontend/data/aircraft-quiet-regions.json \
  --content-type "application/json" --cache-control "no-cache" \
  --region eu-west-2 >> "$LOG" 2>&1 || { say "data deploy FAILED"; exit 1; }
AWS_PROFILE=flightmap aws s3 cp index.html \
  s3://london-flight-map-frontend/index.html \
  --content-type "text/html" --cache-control "no-cache" \
  --region eu-west-2 >> "$LOG" 2>&1 \
  || { say "index deploy FAILED"; exit 1; }
AWS_PROFILE=flightmap aws s3 cp sw.js \
  s3://london-flight-map-frontend/sw.js \
  --content-type "application/javascript" \
  --cache-control "no-cache, no-store, must-revalidate" \
  --region eu-west-2 >> "$LOG" 2>&1 \
  || { say "sw deploy FAILED"; exit 1; }
# MSYS_NO_PATHCONV: Git Bash rewrites "/*" into a Windows path and CloudFront
# rejects the whole batch (CLAUDE.md, "Build & Deploy").
INVALIDATION=$(MSYS_NO_PATHCONV=1 AWS_PROFILE=flightmap aws cloudfront create-invalidation \
  --distribution-id EGSSPJKLFL33M --paths "/*" \
  --query "Invalidation.Id" --output text 2>> "$LOG" | tr -d '\r') \
  || { say "invalidation FAILED"; exit 1; }
say "invalidation $INVALIDATION created; waiting for it to complete"
MSYS_NO_PATHCONV=1 AWS_PROFILE=flightmap aws cloudfront wait invalidation-completed \
  --distribution-id EGSSPJKLFL33M --id "$INVALIDATION" >> "$LOG" 2>&1 \
  || { say "invalidation did not complete"; exit 1; }

# VERIFY FROM THE ORIGIN, not from the exit codes above (audit M19). An
# upload that succeeded and a cache that still serves the old bytes look the
# same from here; the hash the edge returns is the only thing a user gets.
CF="https://d1oe4ftwutjpf.cloudfront.net"
for f in data/aircraft-quiet-regions.json index.html sw.js; do
  local_hash=$(sha256sum "$f" | cut -c1-16)
  live_hash=$(curl -sf -H "Cache-Control: no-cache" "$CF/$f" | sha256sum | cut -c1-16)
  if [ "$local_hash" != "$live_hash" ]; then
    say "VERIFY FAILED: $f live $live_hash != local $local_hash"
    exit 1
  fi
  say "  verified $f ($live_hash)"
done

say "=== done: loaded, deployed and verified from the origin ==="
