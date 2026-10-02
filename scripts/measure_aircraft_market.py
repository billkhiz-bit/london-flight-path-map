"""How many homes sell each year at postcodes on DEFRA's aircraft-noise map?

    python scripts/measure_aircraft_market.py            # 2025
    python scripts/measure_aircraft_market.py --year 2025

WHY THIS EXISTS (2026-10-02). A pitch application asked for market size "with
your working". The honest unit for an aircraft-noise report is a home SALE at a
postcode where aircraft noise is a question at all, and both halves of that are
already held: HM Land Registry's bulk Price Paid file and the per-postcode
DEFRA readings the site ships. This joins them, so the figure in
OUTREACH_TARGETS.md "Facts safe to quote" is measured, not recalled.

WHAT IT COUNTS, and what it does not:
  - Category A sales only, as every other price figure in this product does
    (see build_city_neighbourhoods.py: Category B is repossessions, transfers
    and non-residential, and HMLR's own statistics exclude it).
  - A postcode counts as "on DEFRA's aircraft map" if it is in either quiet
    dataset: London's region export, or one of the seven per-airport coverages.
    That is the cities this product covers, NOT England: Gatwick's, Stansted's
    and Luton's surroundings are outside it, so this is a floor.
  - "About 55 dB or louder" is quiet <= 4.4, from the ramp both files embed
    (45 dB -> 10, 63 dB -> 0). The datasets ship the score at 1dp, not
    decibels, so the cut is within 0.1 dB of 55, not exactly on it.
  - DEFRA Round 4 maps 2021, a COVID year, so today's footprint is larger.
  - Lettings are not in Price Paid data at all.

The Price Paid file is gitignored (155 MB), so an absent file reports
INCONCLUSIVE and exits 0 rather than printing a zero that reads as a count.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUIET_FILES = ('data/aircraft-quiet-london.json', 'data/aircraft-quiet-regions.json')
C_POSTCODE, C_CATEGORY = 3, 14  # the bulk CSV has no header row
QUIET_AT_55_DB = 4.4


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--year', type=int, default=2025)
    args = ap.parse_args()

    ppd = ROOT / 'data' / f'pp-{args.year}.csv'
    if not ppd.exists():
        print(f'INCONCLUSIVE: {ppd.name} is not on disk (gitignored). Nothing was counted.')
        return 0

    quiet = {}
    ramps = set()
    for name in QUIET_FILES:
        body = json.loads((ROOT / name).read_text(encoding='utf-8'))
        ramps.add((body['ramp']['ceilingDb'], body['ramp']['floorDb']))
        quiet.update(body['quiet'])
    if ramps != {(45.0, 63.0)}:
        sys.exit(f'the quiet ramp is {sorted(ramps)}, not 45 -> 63 dB: QUIET_AT_55_DB no longer means 55 dB')

    rows = standard = mapped = loud = 0
    with ppd.open(encoding='utf-8', newline='') as f:
        for row in csv.reader(f):
            rows += 1
            if row[C_CATEGORY] != 'A':
                continue
            standard += 1
            score = quiet.get(row[C_POSTCODE].replace(' ', ''))
            if score is None:
                continue
            mapped += 1
            if score <= QUIET_AT_55_DB:
                loud += 1
    if not standard:
        sys.exit(f'{ppd.name} held {rows} rows and no Category A sale: the column layout has changed')
    if not mapped:
        sys.exit('no sale matched a mapped postcode: the postcode join has broken, this is not a zero')

    print(f'{ppd.name}: {rows:,} rows, {standard:,} Category A sales (England and Wales)')
    print(f'postcodes with a DEFRA aircraft reading: {len(quiet):,}')
    print(f"sales on DEFRA's aircraft map: {mapped:,} ({100 * mapped / standard:.2f}% of Category A sales)")
    print(f'  of which at about 55 dB Lden or louder: {loud:,}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
