#!/bin/sh
# Load the seven per-airport DEFRA aircraft Lden coverages and London's region
# export (the eighth, since 2026-10-11), then ship the matching client datasets.
# Each postcode is sampled at ONS's grid reference (scripts/postcode_grid.py).
# After a RE-PLACING, run scripts/remove_lost_readings.py too: the loader
# upserts, so a reading the new placing no longer has is never removed.
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

# LONDON'S REGION EXPORT, THE EIGHTH (2026-10-11). It is the loader's default
# raster and was in no runbook, so re-placing "every aircraft raster" here left
# London on the old placing. Loaded last; its own checkpoint, so it resumes too.
say "loading london (region export, data/defra_lden_2022.tif)"
if AWS_PROFILE=flightmap python -u scripts/load_defra_raster.py --geotiff data/defra_lden_2022.tif >> "$LOG" 2>&1; then
  say "  london done"
else
  say "  london FAILED (exit $?)"
  say "NOT DEPLOYING. Re-run this script; it resumes."
  exit 1
fi

say "all eight rasters loaded"

if [ -n "${NO_DEPLOY:-}" ]; then
  say "NO_DEPLOY set - stopping before the deploy"
  exit 0
fi

# THROUGH THE MAKEFILE, NOT RETYPED (2026-10-11). This block uploaded
# index.html to the ROOT key, which has been the front page since 2026-10-06:
# run as written, it would have replaced the live front page with the map.
# The client datasets are data files and need no page: data-deploy uploads
# both no-cache and invalidates, from the one holder of how that is done.
say "deploying the client datasets (make.py data-deploy)"
MSYS_NO_PATHCONV=1 python scripts/make.py data-deploy >> "$LOG" 2>&1 \
  || { say "data deploy FAILED"; exit 1; }

# VERIFY FROM THE ORIGIN, not from the exit codes above (audit M19). An
# upload that succeeded and a cache that still serves the old bytes look the
# same from here; the hash the edge returns is the only thing a user gets.
CF="https://skyscore.co.uk"
for f in data/aircraft-quiet-london.json data/aircraft-quiet-regions.json; do
  local_hash=$(sha256sum "$f" | cut -c1-16)
  live_hash=$(curl -sf -H "Cache-Control: no-cache" "$CF/$f" | sha256sum | cut -c1-16)
  if [ "$local_hash" != "$live_hash" ]; then
    say "VERIFY FAILED: $f live $live_hash != local $local_hash"
    exit 1
  fi
  say "  verified $f ($live_hash)"
done

say "=== done: loaded, deployed and verified from the origin ==="
