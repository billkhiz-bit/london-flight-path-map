"""Fit CORRIDOR_WEIGHT against DEFRA's measured postcodes, and report honestly.

The geometry tier stands in for DEFRA's raster wherever DEFRA published
nothing, so the postcodes DEFRA DID measure are the only place its error can be
observed. This scores each of them through calc_postcode_quiet's own geometry
and picks the corridor weight that minimises mean absolute error on a TRAIN
half, then reports the error on the held-out TEST half, per city. Tuning and
testing on the same postcodes would publish an error smaller than a user gets.

The halves are split by a hash of the postcode, so the split is stable across
runs and machines and needs no seed.

WHAT IT CANNOT SEE: DEFRA only maps the loud strip around each airport, so this
yardstick cannot judge a corridor where it leaves that strip. It is used to set
the SIZE of the corridor penalty, never to choose the geometry, which comes
from the AIP (scripts/build_flight_paths.py).

data/nspl.csv is gitignored (964 MB), so this is advisory: without it, or
without the checked-in aircraft-quiet datasets, it reports INCONCLUSIVE and
exits 0.

    python scripts/fit_corridor_weight.py           # fit and report
    python scripts/fit_corridor_weight.py --check   # exit 1 if the shipped weight is not the fit
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import statistics as st
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NSPL = ROOT / 'data' / 'nspl.csv'
MEASURED = [ROOT / 'data' / 'aircraft-quiet-london.json', ROOT / 'data' / 'aircraft-quiet-regions.json']
GRID = [round(i * 0.05, 2) for i in range(21)]
# The shipped constant is compared to the fit at the grid's own resolution.
TOLERANCE = 0.05
MIN_PER_CITY = 150  # below this a city's test half is too thin to report


def load_app():
    spec = importlib.util.spec_from_file_location('score_app', ROOT / 'backend' / 'lambdas' / 'score' / 'app.py')
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    return app


def path_points(app, lat, lon, geo):
    """The corridor ladder's points, exactly as calc_postcode_quiet ranks them."""
    best = float('inf')
    for path in geo['paths']:
        scale = app.airport_noise_scale(path.get('airport'))
        for plat, plon in path['coords']:
            d = app.haversine_km(lat, lon, plat, plon) / scale
            best = min(best, d)
    return 4 if best < 1 else 3 if best < 2 else 2 if best < 4 else 1 if best < 6 else 0


def collect(app):
    measured = {}
    for f in MEASURED:
        if f.exists():
            measured.update(json.loads(f.read_text(encoding='utf-8'))['quiet'])
    if not measured or not NSPL.exists():
        return None
    rows = []
    shipped = app.CORRIDOR_WEIGHT
    with open(NSPL, newline='', encoding='utf-8') as fh:
        r = csv.DictReader(fh)
        lad_col = next(c for c in r.fieldnames if c.startswith('lad') and c.endswith('cd'))
        for row in r:
            pc = row['pcds'].replace(' ', '')
            if row['doterm'] or pc not in measured:
                continue
            hit = app.LAD_TO_BOROUGH.get(row[lad_col])
            if not hit or hit[0] not in app.CITY_GEOMETRY:
                continue
            city = hit[0]
            geo = app.CITY_GEOMETRY[city]
            if not geo.get('airports'):
                continue
            lat, lon = float(row['lat']), float(row['long'])
            app.CORRIDOR_WEIGHT = 0.0
            q0 = app.calc_postcode_quiet(lat, lon, city, raster_lden=None)
            app.CORRIDOR_WEIGHT = shipped
            if q0 is None:
                continue
            pts = path_points(app, lat, lon, geo)
            # Reproduction guard: the decomposition must give back the engine's
            # own answer at the shipped weight, or everything below is fiction.
            q_ship = app.calc_postcode_quiet(lat, lon, city, raster_lden=None)
            if abs(max(0.0, q0 - shipped * pts) - q_ship) > 1e-9:
                raise SystemExit(f'{pc}: decomposition {q0} - {shipped}*{pts} does not reproduce {q_ship}')
            half = 'train' if zlib.crc32(pc.encode()) % 2 == 0 else 'test'
            rows.append((city, half, q0, pts, measured[pc]))
    return rows


def errors(rows, w):
    return [max(0.0, q0 - w * pts) - m for _, _, q0, pts, m in rows]


def mae(rows, w):
    e = errors(rows, w)
    return st.mean(abs(x) for x in e) if e else float('nan')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    app = load_app()
    rows = collect(app)
    if not rows:
        print('INCONCLUSIVE: data/nspl.csv or the aircraft-quiet datasets are absent (both gitignored)')
        return 0
    train = [r for r in rows if r[1] == 'train']
    test = [r for r in rows if r[1] == 'test']
    fits = {w: mae(train, w) for w in GRID}
    best = min(GRID, key=lambda w: (round(fits[w], 6), -w))
    print(f'{len(rows):,} measured postcodes, {len(train):,} train / {len(test):,} test')
    print('train MAE by weight: ' + '  '.join(f'{w:.2f}:{fits[w]:.3f}' for w in GRID))
    print(f'\nFITTED CORRIDOR_WEIGHT = {best:.2f} (shipped {app.CORRIDOR_WEIGHT:.2f})\n')
    print(f'{"city":15} {"test n":>7} {"MAE w=1.00":>11} {"MAE fitted":>11} {"bias fitted":>12}')
    cities = sorted({r[0] for r in rows})
    for city in cities + ['ALL']:
        sub = test if city == 'ALL' else [r for r in test if r[0] == city]
        if city != 'ALL' and len(sub) < MIN_PER_CITY:
            print(f'{city:15} {len(sub):>7}   (under {MIN_PER_CITY}; too thin to report)')
            continue
        bias = st.mean(errors(sub, best))
        print(f'{city:15} {len(sub):>7} {mae(sub, 1.0):>11.3f} {mae(sub, best):>11.3f} {bias:>+12.2f}')
    if args.check and abs(best - app.CORRIDOR_WEIGHT) > TOLERANCE:
        print(f'\nFAIL: shipped CORRIDOR_WEIGHT {app.CORRIDOR_WEIGHT} is not the fit {best}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
