#!/usr/bin/env python3
"""Remove the per-postcode readings the 2026-10-11 re-placing took away. One-off.

Since 2026-10-11 a postcode is sampled at ONS's grid reference, not at a
re-projection of its lat/long (scripts/postcode_grid.py), and the road and
aircraft tiers are reloaded that way (scripts/load_road_rasters.sh,
scripts/load_aircraft_rasters.sh). The loader UPSERTS, so a reading the new
placing no longer has is never removed:

  - aircraft: a postcode whose new cell is no-data (outside DEFRA's contour)
    is skipped, and keeps the old `ldenDb`. The client datasets drop it, so the
    site would estimate it from geometry while /v1/score served the old cell;
  - road: a postcode moving between a mapped reading (`roadLdenDb`) and
    DEFRA's surveyed-below-40-dB bound (`roadLdenBelowDb`) gets the new field
    and keeps the old one, and /v1/environment publishes both.

This finds exactly those postcodes by sampling every raster the two runbooks
load at BOTH placings, and removes the field the new placing does not hold,
only where no other raster (the city mosaics overlap) still gives it. Each
removal is conditional on the field existing, so it never creates an item.

Run AFTER both runbooks have finished:
    python scripts/remove_lost_readings.py                         # dry run: counts and samples
    AWS_PROFILE=flightmap python scripts/remove_lost_readings.py --apply
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ddb_write  # noqa: E402
import load_defra_raster as loader  # noqa: E402
import postcode_grid  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
ROAD_CITIES = ('norwich', 'nottingham', 'teesside', 'leicester', 'tyneandwear', 'bristol',
               'southyorkshire', 'merseyside', 'westmidlands', 'westyorkshire', 'manchester', 'london')
AIRCRAFT = ('birmingham', 'bristol', 'eastmidlands', 'leedsbradford', 'liverpool', 'manchester', 'newcastle')


def rasters():
    """(path, attribute, live_only) for every raster the two runbooks load, in their order."""
    out = [(DATA / f'defra_road_lden_{c}.tif', loader.ROAD_ATTRIBUTE, True) for c in ROAD_CITIES]
    out += [(DATA / f'defra_aircraft_lden_{a}.tif', 'ldenDb', False) for a in AIRCRAFT]
    out.append((loader.DEFRA_GEOTIFF_PATH if loader.DEFRA_GEOTIFF_PATH.is_absolute()
                else ROOT / loader.DEFRA_GEOTIFF_PATH, 'ldenDb', False))
    return out


def read_points():
    """Postcode, live flag, old (projected) and new (ONS grid reference) placings."""
    from pyproj import Transformer

    to_bng = Transformer.from_crs('EPSG:4326', 'EPSG:27700', always_xy=True)
    pcs, live, old, new = [], [], [], []
    with (ROOT / loader.NSPL_CSV_PATH).open(newline='', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)
        loader.require_columns(reader.fieldnames)
        for row in reader:
            try:
                lat, lon = float(row['lat']), float(row['long'])
            except ValueError:
                continue
            xy = postcode_grid.grid_ref(row, to_bng)
            if xy is None or lat > 90:
                continue
            pcs.append(row['pcds'].replace(' ', '').upper())
            live.append(not (row.get('doterm') or '').strip())
            old.append(to_bng.transform(lon, lat))
            new.append(xy)
    return pcs, np.array(live), np.array(old), np.array(new)


def states(path, attribute, pts):
    """The field each point would be written under from this raster: attribute, the bound, or None."""
    import rasterio

    with rasterio.open(path) as ds:
        band = ds.read(1)
        nodata = ds.nodata
        cols, rows = ~ds.transform * (pts[:, 0], pts[:, 1])
    cols, rows = np.floor(cols).astype(int), np.floor(rows).astype(int)
    h, w = band.shape
    inside = (rows >= 0) & (rows < h) & (cols >= 0) & (cols < w)
    out = np.full(len(pts), None, dtype=object)
    for i in np.flatnonzero(inside):
        state, _ = loader.classify_cell(float(band[rows[i], cols[i]]), nodata, attribute)
        if state == 'reading':
            out[i] = attribute
        elif state == 'below':
            out[i] = loader.ROAD_BELOW_ATTRIBUTE
    return out


def lost(pcs, live, old, new):
    """{field: [postcode, ...]}: held under the old placing, by no raster under the new one."""
    had, has = defaultdict(set), defaultdict(set)
    for path, attribute, live_only in rasters():
        if not path.exists():
            raise SystemExit(f'missing {path}: the runbooks load it, so the comparison needs it')
        keep = live if live_only else np.ones(len(pcs), bool)
        idx = np.flatnonzero(keep)
        for field_set, pts in ((had, old), (has, new)):
            for i, f in zip(idx, states(path, attribute, pts[idx]), strict=True):
                if f:
                    field_set[f].add(pcs[i])
        print(f'  {path.name}: compared')
    return {f: sorted(had[f] - has[f]) for f in had}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--apply', action='store_true', help='remove them (default: dry run)')
    args = ap.parse_args()
    print('reading NSPL...')
    pcs, live, old, new = read_points()
    print(f'  {len(pcs):,} postcodes')
    gone = lost(pcs, live, old, new)
    for f, items in gone.items():
        print(f'{f}: {len(items):,} postcode(s) lose it, e.g. {items[:5]}')
    if not args.apply:
        print('dry run: nothing removed. Re-run with --apply after both runbooks have finished.')
        return 0
    ddb = ddb_write.make_client(loader.AWS_REGION)
    removed = absent = 0
    for f, items in gone.items():
        for pc in items:
            try:
                ddb.update_item(
                    TableName=loader.TABLE_NAME,
                    Key={'postcode': {'S': pc}},
                    UpdateExpression='REMOVE #a',
                    ConditionExpression='attribute_exists(#a)',
                    ExpressionAttributeNames={'#a': f},
                )
                removed += 1
            except ddb.exceptions.ConditionalCheckFailedException:
                absent += 1
    print(f'removed {removed:,}; {absent:,} already held no such field')
    return 0


if __name__ == '__main__':
    sys.exit(main())
