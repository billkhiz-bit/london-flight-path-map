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

  printf '%s: RUNNING\n' "$name"
  bar "$pct"
  printf '  %s of %s NSPL rows scanned\n' "$rows" "$NSPL_ROWS"
  [ -n "$expected_writes" ] && printf '  %s postcodes expected to be written in total\n' "$expected_writes"

  if [ -f "$log" ]; then
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
