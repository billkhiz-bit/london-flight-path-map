#!/usr/bin/env sh
# Progress for the long-running DEFRA loaders, at a glance.
#
# WHY THIS EXISTS. Both loaders run for hours and emit tqdm output, which uses
# carriage returns to redraw one line. Redirected to a file that becomes a
# single enormous line of overwritten frames, so `tail` shows nothing useful and
# `cat` floods the terminal. The information was there and unreadable.
#
# It reads the CHECKPOINT file rather than parsing the log where it can: the
# checkpoint is what the loader would actually resume from, so it cannot
# disagree with reality the way a scraped progress frame might.
#
#   sh scripts/load_status.sh
#
# Exits 0 whether or not a load is running. This reports; it never gates.

set -u

ROOT="$(dirname "$0")/.."
NSPL_ROWS=2723596

# A checkpoint file outlives the process that wrote it. The loaders delete it
# only on a clean full finish, so every interrupted run leaves one behind and
# "file exists" means "a run STARTED", never "a run is RUNNING". On 2026-08-08
# this script reported both loaders RUNNING - one of them 38 hours dead - and
# printed a throughput figure scraped from a log nothing had written to since.
#
# The checkpoint's MODIFICATION TIME is the liveness signal, not its existence:
# a live loader rewrites it every 1000 NSPL rows.
age_secs() {
  # Seconds since $1 was last modified. Git Bash ships GNU stat; the BSD form
  # is the fallback. An unreadable mtime returns a large number, so the
  # unknown case reads as stale rather than as healthy - this script's whole
  # bug was an unknown rendering as healthy.
  mtime=$(stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null)
  [ -z "$mtime" ] && { echo 999999; return; }
  echo $(( $(date +%s) - mtime ))
}

# Thresholds are derived from the checkpoint WRITE CADENCE, not from a guess at
# how long feels reasonable. Both loaders rewrite every 1000 NSPL rows, so the
# quiet gap between writes is 1000/rate seconds. Measured 2026-08-08 on the road
# pass resuming into the dense UB-onward range: 8,000 rows in 522s = ~15 rows/s,
# so a HEALTHY loader is silent for ~65s at a stretch. Anything under ~2 minutes
# would therefore flag a running loader as dead - which is the failure that gets
# a check switched off and ignored.
#
# 300s is ~4.6x that observed worst cadence: enough headroom for a slower patch
# or the startup skip (the road pass reads past ~2.5M already-done CSV rows to
# reach its resume point, writing nothing meanwhile), while still turning an
# overnight death into something you see immediately.
STALLED_SECS=300
STOPPED_SECS=1800

# Two verdicts, because they call for different actions. STALLED might be a slow
# patch and might be a death - run this again in a minute. STOPPED past half an
# hour is never a slow patch; it needs restarting.
liveness() {
  age=$(age_secs "$1")
  if [ "$age" -lt "$STALLED_SECS" ]; then
    echo 'RUNNING'
  elif [ "$age" -lt "$STOPPED_SECS" ]; then
    echo 'STALLED?'
  else
    echo 'STOPPED'
  fi
}

bar() {
  # $1 = percent (integer 0-100)
  filled=$(( $1 * 30 / 100 ))
  i=0
  printf '  ['
  while [ $i -lt 30 ]; do
    if [ $i -lt $filled ]; then printf '#'; else printf '.'; fi
    i=$((i + 1))
  done
  printf '] %s%%\n' "$1"
}

report() {
  name="$1"; checkpoint="$2"; log="$3"; expected_writes="$4"

  if [ ! -f "$checkpoint" ]; then
    # No checkpoint means either never started, or finished — the loader
    # deletes it on a clean full run. Distinguish, because "done" and "never
    # ran" look identical otherwise and only one of them needs action.
    if [ -f "$log" ] && grep -q "Done\." "$log" 2>/dev/null; then
      printf '%s: COMPLETE\n' "$name"
      tr '\r' '\n' < "$log" | grep -E "^Done\." | tail -1 | sed 's/^/  /'
    else
      printf '%s: not started\n' "$name"
    fi
    echo
    return
  fi

  rows=$(cat "$checkpoint" 2>/dev/null | tr -d ' \n')
  [ -z "$rows" ] && rows=0
  pct=$(( rows * 100 / NSPL_ROWS ))

  verdict=$(liveness "$checkpoint")
  printf '%s: %s\n' "$name" "${verdict:-UNKNOWN}"
  bar "$pct"
  printf '  %s of %s NSPL rows scanned\n' "$rows" "$NSPL_ROWS"
  # Always show the age, whatever the verdict. The reader can then disagree
  # with the threshold, which they could not do when the only output was a
  # bare "RUNNING".
  printf '  checkpoint last moved %ss ago\n' "$(age_secs "$checkpoint")"
  [ -n "$expected_writes" ] && printf '  %s postcodes expected to be written in total\n' "$expected_writes"

  # Only scrape the log while the loader is actually live. A tqdm frame carries
  # no timestamp, so a rate read from a dead run is indistinguishable from a
  # live one: on 2026-08-08 this line printed "rate 25.27it/s, elapsed 3:19:34"
  # for a process that had been dead 38 hours. A number that cannot say how old
  # it is must not outlive the thing it measured.
  if [ -f "$log" ] && [ "$verdict" = 'RUNNING' ]; then
    # tqdm redraws with \r, so split on it and take the last frame. This is
    # display only — the checkpoint above is the number that matters.
    rate=$(tr '\r' '\n' < "$log" | grep -oE '[0-9.]+it/s' | tail -1)
    elapsed=$(tr '\r' '\n' < "$log" | grep -oE '\[[0-9:]+' | tail -1 | tr -d '[')
    [ -n "$rate" ] && printf '  rate %s, elapsed %s\n' "$rate" "$elapsed"
  fi
  echo
}

echo
report 'Road noise (aircraft table, roadLdenDb)' \
       "$ROOT/.defra_load_checkpoint_defra_road_lden_london" \
       '/tmp/roadload.log' '390,743'

report 'Air quality (NO2 + PM2.5)' \
       "$ROOT/.defra_aq_checkpoint" \
       '/tmp/aqload.log' ''

echo 'A postcode gains its value the moment it is written - the Lambda reads the'
echo 'table live, so nothing needs deploying or restarting as these progress.'
echo
