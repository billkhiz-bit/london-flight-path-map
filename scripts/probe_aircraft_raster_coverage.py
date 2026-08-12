#!/usr/bin/env python3
"""How many live postcodes would each DEFRA per-airport Lden raster actually
give a reading for, and which of our cities do they land in?

WHY MEASURE BEFORE LOADING. `load_defra_raster.py` is a multi-hour DynamoDB
pass per raster, and the value of running it is entirely a question of
COVERAGE, which nobody has measured for the per-airport coverages. The London
experience is the warning: the raster tier was quarantined for weeks because
89.5% of London sat OUTSIDE the published contours, so a tier that looked like
an upgrade returned nothing for nine postcodes in ten.

These rasters are contour strips, not city rectangles - Heathrow's is 41 km by
10.4 km - so the honest question is not "does it cover the city" but "how many
postcodes does it reach, and whose".

Reads nothing from DynamoDB and writes nothing to it. Safe to run while a
loader is mid-pass.

  pip install rasterio pyproj
  python scripts/probe_aircraft_raster_coverage.py
  python scripts/probe_aircraft_raster_coverage.py --json out.json
"""

import argparse
import csv
import glob
import json
import os
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NSPL_PATH = os.path.join(REPO, 'data', 'nspl.csv')
RASTER_GLOB = os.path.join(REPO, 'data', 'defra_aircraft_lden_*.tif')

# ABSENCE TEST, mirroring load_defra_raster.py exactly so this probe predicts
# what a load would actually write rather than a stricter thing of its own.
#
# The loader treats a cell as absent only when it is the nodata sentinel - it
# applies no dB floor. Note the sentinel's SIGN differs between exports: the
# London-region `defra_lden_2022.tif` carries +3.4e38 while every per-airport
# coverage carries -3.4e38, so a `> 1e30` test alone (which is what the loader
# leads with) would read every per-airport nodata cell as a real -3.4e38 dB
# reading. The `== raster.nodata` branch is what saves it, and this probe uses
# the magnitude so it cannot depend on which branch fires.
SENTINEL_MAGNITUDE = 1e30

# Not a threshold, only a sanity range for reporting: a dB outside it would mean
# the sentinel test missed something.
PLAUSIBLE_DB = (0.0, 200.0)


def load_rasters():
    import rasterio

    out = []
    for path in sorted(glob.glob(RASTER_GLOB)):
        name = os.path.basename(path).replace('defra_aircraft_lden_', '').replace('.tif', '')
        with rasterio.open(path) as r:
            band = r.read(1)
            out.append({
                'name': name,
                'array': band,
                'left': r.bounds.left,
                'top': r.bounds.top,
                'right': r.bounds.right,
                'bottom': r.bounds.bottom,
                'res_x': r.transform.a,
                'res_y': -r.transform.e,
                'height': r.height,
                'width': r.width,
                'nodata': r.nodata,
            })
        print(f'  {name:14} {out[-1]["width"]:5}x{out[-1]["height"]:<5} '
              f'{out[-1]["res_x"]:.0f} m/px', file=sys.stderr)
    if not out:
        sys.exit(f'no rasters matched {RASTER_GLOB}')
    return out


def sample(r, x, y):
    """Value at BNG (x, y), or None outside the raster / on nodata."""
    if not (r['left'] <= x < r['right'] and r['bottom'] < y <= r['top']):
        return None
    col = int((x - r['left']) / r['res_x'])
    row = int((r['top'] - y) / r['res_y'])
    if not (0 <= row < r['height'] and 0 <= col < r['width']):
        return None
    v = float(r['array'][row, col])
    if abs(v) > SENTINEL_MAGNITUDE:
        return None
    if r['nodata'] is not None and v == r['nodata']:
        return None
    if not (PLAUSIBLE_DB[0] <= v <= PLAUSIBLE_DB[1]):
        # Would mean the sentinel test missed a form of absence. Loud, not
        # silent: a bad reading written as dB is worse than no reading.
        raise SystemExit(f'implausible {v} dB in {r["name"]} - sentinel test is wrong')
    return v


def score_module():
    import importlib.util

    path = os.path.join(REPO, 'backend', 'lambdas', 'score', 'app.py')
    spec = importlib.util.spec_from_file_location('score_app_probe', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def lad_to_city(module):
    return {code: city for code, (city, _b) in module.LAD_TO_BOROUGH.items()}


def geometry_quiet(module, lat, lon, city):
    """What the CURRENT geometry tier scores, with the raster explicitly absent.

    Passing raster_lden=None rather than leaving the sentinel is the whole
    point: it means "already checked, it missed", so the function skips the
    DynamoDB lookup and takes the Haversine path. With the sentinel this would
    try to reach DynamoDB from a laptop and quietly answer from whatever it
    found - measuring the thing under test against itself.
    """
    try:
        return module.calc_postcode_quiet(lat, lon, city, postcode_clean=None, raster_lden=None)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--json', metavar='PATH')
    args = ap.parse_args()

    from pyproj import Transformer

    print('rasters:', file=sys.stderr)
    rasters = load_rasters()
    module = score_module()
    cities = lad_to_city(module)
    to_bng = Transformer.from_crs('EPSG:4326', 'EPSG:27700', always_xy=True)

    # error[city] = list of (geometry estimate - raster measurement) in score
    # points. This is the number that decides whether loading the rasters is
    # worth hours: if the estimate already agrees, the load buys nothing.
    errors = defaultdict(list)

    hits = defaultdict(int)                       # raster -> postcodes with a reading
    by_city = defaultdict(lambda: defaultdict(int))   # city -> raster -> n
    city_live = defaultdict(int)                  # city -> live postcodes seen
    overlap = defaultdict(int)                    # postcodes inside >1 raster
    values = defaultdict(list)
    n = live = 0

    with open(NSPL_PATH, encoding='utf-8-sig', newline='') as fh:
        rd = csv.DictReader(fh)
        cols = {c.lower(): c for c in rd.fieldnames}
        c_lat, c_lon = cols['lat'], cols['long']
        c_term = cols.get('doterm')
        c_lad = cols.get('lad25cd')
        for row in rd:
            n += 1
            if args.limit and n > args.limit:
                break
            if c_term and row[c_term].strip():
                continue
            try:
                lat, lon = float(row[c_lat]), float(row[c_lon])
            except (TypeError, ValueError):
                continue
            if lat > 90 or lat < 49:
                continue
            live += 1
            city = cities.get((row.get(c_lad) or '').strip())
            if city:
                city_live[city] += 1
            x, y = to_bng.transform(lon, lat)
            found = []
            for r in rasters:
                v = sample(r, x, y)
                if v is not None:
                    found.append((r['name'], v))
            if not found:
                continue
            if len(found) > 1:
                overlap['|'.join(sorted(nm for nm, _ in found))] += 1
            for nm, v in found:
                hits[nm] += 1
                if len(values[nm]) < 5000:
                    values[nm].append(v)
                if city:
                    by_city[city][nm] += 1
            if city:
                measured = module.lden_db_to_quiet(max(v for _nm, v in found))
                estimated = geometry_quiet(module, lat, lon, city)
                if estimated is not None:
                    errors[city].append(estimated - measured)
            if live % 250000 == 0:
                print(f'  {live:,} live scanned, {sum(hits.values()):,} readings',
                      file=sys.stderr, flush=True)

    print(f'\nscanned {n:,} rows, {live:,} live\n')
    print(f'{"raster":16} {"postcodes with a reading":>24} {"min":>6} {"median":>7} {"max":>6}')
    for r in rasters:
        nm = r['name']
        vs = sorted(values[nm])
        med = vs[len(vs) // 2] if vs else 0
        lo = vs[0] if vs else 0
        hi = vs[-1] if vs else 0
        print(f'{nm:16} {hits[nm]:24,} {lo:6.1f} {med:7.1f} {hi:6.1f}')
    print(f'\nTOTAL readings: {sum(hits.values()):,}')

    if overlap:
        print('\npostcodes inside MORE THAN ONE raster (these need a dB sum, not last-write-wins):')
        for k, v in sorted(overlap.items(), key=lambda kv: -kv[1]):
            print(f'  {k:40} {v:,}')
    else:
        print('\nNo postcode falls inside two rasters: the passes are disjoint.')

    print('\nby city (readings / live postcodes in that city):')
    for city in sorted(by_city):
        tot = sum(by_city[city].values())
        share = tot / city_live[city] if city_live[city] else 0
        which = ', '.join(f'{k} {v:,}' for k, v in sorted(by_city[city].items(), key=lambda kv: -kv[1]))
        print(f'  {city:16} {tot:7,} / {city_live[city]:7,}  {share:5.1%}   {which}')

    print('\ngeometry estimate vs raster measurement, in SCORE POINTS (0-10):')
    print(f'  {"city":16} {"n":>7} {"mean abs":>9} {"mean signed":>12} {"|err|>2":>8} {"|err|>4":>8}')
    all_err = []
    for city in sorted(errors):
        e = errors[city]
        if not e:
            continue
        all_err += e
        mae = sum(abs(x) for x in e) / len(e)
        mse = sum(e) / len(e)
        over2 = sum(1 for x in e if abs(x) > 2) / len(e)
        over4 = sum(1 for x in e if abs(x) > 4) / len(e)
        print(f'  {city:16} {len(e):7,} {mae:9.3f} {mse:12.3f} {over2:7.0%} {over4:7.0%}')
    if all_err:
        mae = sum(abs(x) for x in all_err) / len(all_err)
        mse = sum(all_err) / len(all_err)
        print(f'  {"ALL":16} {len(all_err):7,} {mae:9.3f} {mse:12.3f}')
        print('\n  A POSITIVE signed error means the geometry tier scores the postcode')
        print('  QUIETER than DEFRA measured it - the optimistic direction, and the')
        print('  one that matters for a noise product.')

    if args.json:
        with open(args.json, 'w', encoding='utf-8') as fh:
            json.dump({
                'live': live,
                'hits': dict(hits),
                'byCity': {c: dict(v) for c, v in by_city.items()},
                'cityLive': dict(city_live),
                'overlap': dict(overlap),
            }, fh, indent=1, sort_keys=True)
        print(f'\nwrote {args.json}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
