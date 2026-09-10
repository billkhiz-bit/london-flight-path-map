#!/usr/bin/env python3
"""What a per-postcode road-noise load would find, city by city - BEFORE loading.

Road sibling of probe_aircraft_raster_coverage.py, written 2026-09-10 when the
per-postcode road tier (`roadLdenDb` in london-flight-map-noise-raster) turned
out to be LONDON-ONLY: SW11 serves 69.1 dB on /v1/environment while M2 4NG
serves None with "not measured, or still being loaded". All eleven city road
mosaics have been on disk since August; nothing had measured what loading them
would publish.

THE THREE STATES A MOSAIC CELL CAN BE IN, and why the third one is the point:

  nodata    not surveyed - DEFRA mapped nothing here
  0         SURVEYED, below the lowest mapped band (~40 dB). Quiet, and known
            to be quiet.
  > 0       a reading

load_defra_raster.py skips nodata (correctly) AND skips anything under
LDEN_MIN = 30, which drops every 0 with it. A surveyed-quiet postcode therefore
gets no row, and /v1/environment tells its reader the road noise "has not been
measured" - the audit I3 trap (build_borough_bands.py fixed it for the SHARE on
2026-09-01) one tier down. Whether that matters depends on how many zeros there
are, which is what this prints. If a third of a city is zeros, loading only the
positives publishes a decibel figure for the noisy postcodes and silence for the
quiet ones, which is a directional bias wearing a coverage number.

Reuses the bands builder's own decoding (collect_postcodes, sample_raster) so
the probe cannot disagree with the derivation about what a cell means.

  python scripts/probe_road_raster_coverage.py            # all cities
  python scripts/probe_road_raster_coverage.py --city bristol
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_borough_bands as bb  # noqa: E402

WHO_ROAD_DB = 53.0
LOADER_MIN_DB = 30.0  # load_defra_raster.LDEN_MIN
LAMBDA_MIN_DB = 40.0  # score/app.py _ROAD_MIN_PLAUSIBLE_DB


def probe_city(city, boroughs):
    tif = bb.DATA / f'defra_road_lden_{city}.tif'
    points = [p for pts in boroughs.values() for p in pts]
    if not tif.exists() or city in bb.NO_ROAD_COVERAGE:
        return {'city': city, 'live': len(points), 'mosaic': None}
    vals, surveyed, inside = bb.sample_raster(tif, points)
    vals = np.asarray(vals, dtype='float64')
    return {
        'city': city,
        'live': len(points),
        'mosaic': tif.name,
        'inside': inside,
        'surveyed': surveyed,
        'zero': surveyed - len(vals),
        'mapped': len(vals),
        'below_loader_min': int((vals < LOADER_MIN_DB).sum()),
        'loader_to_lambda_gap': int(((vals >= LOADER_MIN_DB) & (vals < LAMBDA_MIN_DB)).sum()),
        'servable': int((vals >= LAMBDA_MIN_DB).sum()),
        'median': float(np.median(vals)) if len(vals) else None,
        'share_over_who': (
            100.0 * float((vals >= WHO_ROAD_DB).sum()) / surveyed if surveyed else None
        ),
    }


def pct(n, d):
    return f'{100.0 * n / d:5.1f}%' if d else '    -'


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--city', help='probe one city key (default: every city with a mosaic)')
    args = ap.parse_args()

    lad_map = bb.load_lad_map()
    by_city, _gp = bb.collect_postcodes(lad_map)
    cities = [args.city] if args.city else sorted(by_city)
    if args.city and args.city not in by_city:
        raise SystemExit(f'unknown city {args.city!r}; have {sorted(by_city)}')

    print()
    print(
        f'{"city":<15} {"live":>8} {"inside":>7} {"surveyed":>8} {"zero":>7} '
        f'{"mapped":>7} {"<40dB":>6} {"servable":>9} {"median":>7} {">=WHO":>6}'
    )
    tot = dict(live=0, inside=0, surveyed=0, zero=0, mapped=0, servable=0)
    for city in cities:
        r = probe_city(city, by_city[city])
        if r['mosaic'] is None:
            print(f'{city:<15} {r["live"]:>8}   no road mosaic (or excluded by name)')
            continue
        for k in tot:
            tot[k] += r[k]
        print(
            f'{city:<15} {r["live"]:>8} {pct(r["inside"], r["live"]):>7} '
            f'{pct(r["surveyed"], r["live"]):>8} {pct(r["zero"], r["surveyed"]):>7} '
            f'{r["mapped"]:>7} {r["loader_to_lambda_gap"]:>6} '
            f'{pct(r["servable"], r["surveyed"]):>9} {r["median"]:>7.1f} '
            f'{r["share_over_who"]:>5.1f}%'
        )
    print(
        f'{"TOTAL":<15} {tot["live"]:>8} {pct(tot["inside"], tot["live"]):>7} '
        f'{pct(tot["surveyed"], tot["live"]):>8} {pct(tot["zero"], tot["surveyed"]):>7} '
        f'{tot["mapped"]:>7} {"":>6} {pct(tot["servable"], tot["surveyed"]):>9}'
    )
    print()
    print('zero      = surveyed and below the lowest mapped band: QUIET, and known to be.')
    print('<40dB     = mapped readings the loader would write and the Lambda would then')
    print('            refuse (LDEN_MIN 30 vs _ROAD_MIN_PLAUSIBLE_DB 40).')
    print('servable  = readings /v1/environment would actually publish after a load.')
    print('The gap between servable and surveyed is what today reads as "not measured".')
    return 0


if __name__ == '__main__':
    sys.exit(main())
