#!/usr/bin/env python3
"""Score the geometry quiet tier against DEFRA's own measurements.

WHY THIS EXISTS. `Quiet Skies` is the headline component of every score this
product publishes, and for the great majority of postcodes it is an ESTIMATE:
Haversine distance to airports plus flight-path geometry, standing in for a
DEFRA Lden reading that does not exist at that address. DEFRA's aircraft
contours are narrow strips around runways, so they reach only about a tenth of
live London postcodes and 0.6-3.9% of each region.

That estimate's accuracy was measured ONCE, during the v3.8 footprint-scaling
work, and the result - "mean absolute error 3.230 -> 1.879" - was written into
CLAUDE.md and nowhere else. A number recorded in prose and derivable by nothing
is exactly the shape this repo keeps paying for: it cannot be re-checked, it
cannot go stale detectably, and it cannot be shown to a customer's auditor as
anything more than a claim. Every OTHER published figure here has a `--check`
that can go red. This one did not.

WHAT IT MEASURES. `data/aircraft-quiet-london.json` holds the quiet score
DEFRA's raster actually produces for 35,352 London postcodes. The geometry tier
only ever stands in for that raster, so the two are directly comparable: run
`calc_postcode_quiet` with the raster deliberately withheld, and the difference
IS the estimator's error, over the largest set where truth is known.

WHAT IT DELIBERATELY DOES NOT CLAIM. This measures the estimator against DEFRA
where DEFRA published a contour - i.e. NEAR AIRPORTS, which is where the
geometry has the most to get wrong and where the raster exists at all. It says
nothing about accuracy far from any airport, because no measurement exists
there to compare against. Reporting it as a global accuracy figure would be
over-claiming; the summary says which population it describes.

ADVISORY, and reports INCONCLUSIVE rather than PASS when it cannot measure.
`data/nspl.csv` is gitignored (805 MB), so a fresh clone has no coordinates and
this can run nowhere but a machine that has loaded it. A gate that silently
passes when its input is absent is the defect this repo has closed four times.

  python scripts/check_quiet_estimate_error.py            # full run
  python scripts/check_quiet_estimate_error.py --sample 2000
  python scripts/check_quiet_estimate_error.py --max-mae 2.5   # gate on it
"""

import argparse
import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NSPL = ROOT / 'data' / 'nspl.csv'
MEASURED = ROOT / 'data' / 'aircraft-quiet-london.json'

sys.path.insert(0, str(ROOT / 'backend' / 'lambdas' / 'score'))


def load_measured():
    """The DEFRA-derived quiet score per postcode, keyed with no spaces."""
    if not MEASURED.exists():
        return None
    doc = json.loads(MEASURED.read_text(encoding='utf-8'))
    return doc.get('quiet') or None


def load_coords(wanted):
    """lat/lon for the wanted postcodes, from NSPL.

    Reads the whole file once rather than seeking: it is one pass over 2.7M
    rows and the alternative is 35,352 network lookups.

    TERMINATED postcodes are kept here ON PURPOSE, unlike the borough-band
    build (audit F38). This is not a population statistic - it is a paired
    comparison, and the pairing is the raster reading we already hold for that
    exact postcode. Dropping a terminated one would discard a real measurement
    and could not bias the error, since both sides describe the same point.
    """
    if not NSPL.exists():
        return None
    out = {}
    with NSPL.open(newline='', encoding='utf-8', errors='replace') as fh:
        reader = csv.DictReader(fh)
        cols = reader.fieldnames or []
        pc_col = next((c for c in ('pcds', 'pcd', 'pcd2') if c in cols), None)
        lat_col = next((c for c in ('lat', 'latitude') if c in cols), None)
        lon_col = next((c for c in ('long', 'lon', 'longitude') if c in cols), None)
        if not (pc_col and lat_col and lon_col):
            raise SystemExit(
                f'FAIL: NSPL is missing an expected column. Saw {cols[:12]}...\n'
                '  Expected a postcode column (pcds/pcd/pcd2) and lat/long.'
            )
        for row in reader:
            key = (row.get(pc_col) or '').replace(' ', '').upper()
            if key not in wanted:
                continue
            try:
                lat, lon = float(row[lat_col]), float(row[lon_col])
            except (TypeError, ValueError):
                continue
            # NSPL writes (99.999, 0.0) for a postcode it cannot place.
            if lat > 99 or (lat == 0.0 and lon == 0.0):
                continue
            out[key] = (lat, lon)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sample', type=int, default=0,
                    help='compare a random N rather than all (0 = all)')
    ap.add_argument('--seed', type=int, default=20260902)
    ap.add_argument('--max-mae', type=float, default=None,
                    help='exit 1 if mean absolute error exceeds this')
    args = ap.parse_args()

    measured = load_measured()
    if measured is None:
        print('INCONCLUSIVE: data/aircraft-quiet-london.json is absent, so there')
        print('  is nothing to compare the estimator against. Not a pass.')
        return 0

    import app  # noqa: E402  (path is set above)

    keys = sorted(measured)
    if args.sample and args.sample < len(keys):
        # noqa justification: this picks a REPRODUCIBLE subset for a
        # statistical measurement (the seed is a CLI argument precisely so two
        # runs compare the same postcodes). Nothing here is a secret, a token,
        # or a sampling decision an adversary benefits from predicting.
        random.Random(args.seed).shuffle(keys)  # noqa: S311
        keys = sorted(keys[:args.sample])

    coords = load_coords(set(keys))
    if coords is None:
        print('INCONCLUSIVE: data/nspl.csv is absent (gitignored, 805 MB), so no')
        print('  postcode coordinates are available. Nothing was compared, which')
        print('  is NOT the same as agreement. Load NSPL to run this.')
        return 0

    errs, signed, missing_geom = [], [], 0
    for pc in keys:
        if pc not in coords:
            continue
        lat, lon = coords[pc]
        # raster_lden=None forces the GEOMETRY tier and, importantly, stops
        # calc_postcode_quiet re-querying DynamoDB for a reading we are
        # deliberately withholding.
        est = app.calc_postcode_quiet(lat, lon, 'london', pc, raster_lden=None)
        if est is None:
            missing_geom += 1
            continue
        truth = float(measured[pc])
        errs.append(abs(est - truth))
        signed.append(est - truth)

    compared = len(errs)
    # A FLOOR, for the reason every other check here has one: "0 differ" over
    # zero comparisons is the shape that has passed on nothing four times.
    if compared < 100:
        print(f'FAIL: compared only {compared} postcodes, expected at least 100.')
        print('  Either NSPL does not cover them or the join is broken - either')
        print('  way this measured nothing while looking like it ran.')
        return 1

    errs.sort()
    mae = sum(errs) / compared
    bias = sum(signed) / compared
    p50 = errs[compared // 2]
    p90 = errs[int(compared * 0.90)]
    worst = errs[-1]
    within1 = sum(1 for e in errs if e <= 1.0) / compared * 100
    within2 = sum(1 for e in errs if e <= 2.0) / compared * 100

    print('Geometry quiet tier vs DEFRA raster measurement')
    print('===============================================')
    print(f'  compared            {compared:,} London postcodes'
          f'{"" if not args.sample else f" (sampled from {len(measured):,})"}')
    if missing_geom:
        print(f'  no geometry answer  {missing_geom}')
    print(f'  mean absolute error {mae:.3f} points (0-10 scale)')
    print(f'  median / p90 / max  {p50:.3f} / {p90:.3f} / {worst:.3f}')
    print(f'  signed bias         {bias:+.3f}  '
          f'({"estimate reads LOUDER than DEFRA" if bias < 0 else "estimate reads QUIETER than DEFRA"})')
    print(f'  within 1.0 point    {within1:.1f}%')
    print(f'  within 2.0 points   {within2:.1f}%')
    print()
    print('  Population: postcodes where DEFRA PUBLISHED a contour, i.e. near')
    print('  airports. That is where the geometry has most to get wrong, and')
    print('  the only place a comparison is possible at all. It is NOT a global')
    print('  accuracy figure and must not be quoted as one.')

    if args.max_mae is not None and mae > args.max_mae:
        print(f'\nFAIL: mean absolute error {mae:.3f} exceeds --max-mae {args.max_mae}.')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
