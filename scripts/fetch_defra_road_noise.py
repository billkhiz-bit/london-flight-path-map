#!/usr/bin/env python3
"""Fetch the DEFRA Round 4 road-noise Lden raster for a city via WCS.

WHY THIS EXISTS. METHODOLOGY.md §7 says the DEFRA rasters come from an
interactive "Download data by area of interest and format" tool on data.gov.uk —
select England, GeoTIFF, Lden, submit, wait for the export. That is a browser
workflow, so the road-noise dataset sat unobtainable from a terminal and the
component stayed unbuilt.

The dataset page also publishes a **WCS endpoint**, which is a standard OGC
coverage service and takes bounding-box requests over plain HTTP. Same data,
same licence, no form. That makes the road-noise component reproducible from a
script rather than dependent on someone clicking through a portal, which also
means the Round 5 refresh in §7 step 1 stops being a manual step.

WHY TILED. A single request for the whole Greater London bbox returns 504 —
measured. 20 km tiles return 200 in a few seconds each (2000x2000 at the native
10 m resolution, ~16 MB). Anything larger was not tested; anything smaller just
multiplies round-trips.

Output feeds scripts/load_defra_raster.py, which already samples a GeoTIFF at
postcode centroids for the aircraft raster.

PER-CITY SINCE 2026-08-11, AND THE COVERAGE WAS ALWAYS NATIONAL. The coverage id
below ends `Road_Noise_Lden_England_Round_4_All` and always did; the only
London-specific thing in this file was a hardcoded bbox. Meanwhile the site
painted every borough of the other seven cities a single default colour, because
`BOROUGH_ROAD_NOISE` was `{}` for all of them and the renderer falls back to
'moderate'. The data was one bounding box away the whole time.

Measured on 2026-08-11 before generalising, rather than assumed: a 10 km probe
tile over each city centre returns a valid TIFF with 79-98% of cells carrying a
reading, 40-89 dB Lden, medians 50-55. London is 99.5% and is the control. So
this is not the aircraft situation, where the raster is real but 94% of its grid
is empty.

The bbox is DERIVED from the city's own boundary file rather than listed here,
so a new city needs no new constant and cannot be fetched over the wrong extent.

  pip install rasterio requests pyproj
  python scripts/fetch_defra_road_noise.py --city london
  python scripts/fetch_defra_road_noise.py --all
"""

import argparse
import json
import math
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = 'https://environment.data.gov.uk/spatialdata/road-noise-all-metrics-england-round-4/wcs'
COVERAGE = '562c9d56-7c2d-4d42-83bb-578d6e97a517__Road_Noise_Lden_England_Round_4_All'

# The host answers 403 without a browser User-Agent and looks bot-blocked. Same
# note as scripts/download_defra_wcs.py; both learned it the same way.
UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/126.0 Safari/537.36'
)

TILE = 20000
# Kilometres of slack around a city's boundary box. Road noise that matters to a
# borough's edge is generated on roads just outside it, and a postcode centroid
# can sit nearer the boundary than the raster's own 10 m grid resolves.
PAD_M = 2000

# ENGLAND ONLY. The coverage is England's; Cardiff is in Wales and Natural
# Resources Wales publishes its own Round 4 maps under a different service. A
# silent empty raster would be worse than this list, because a Cardiff fetch
# would "succeed" and then read as no-noise-anywhere.
WELSH = {'cardiff'}

OUT_DIR = Path(__file__).resolve().parents[1] / 'data'
TILE_DIR = OUT_DIR / 'road_noise_tiles'


def mosaic_path(city):
    return OUT_DIR / f'defra_road_lden_{city}.tif'


def city_bbox(city):
    """Bounding box in EPSG:27700 for a city, derived from its boundary file.

    The raster is published in British National Grid, so projecting INTO its CRS
    means the request is made in the raster's own coordinates and no resampling
    happens on our side. Sampling later happens in the same frame.
    """
    path = OUT_DIR / f'{city}-boroughs.json'
    if not path.exists():
        raise SystemExit(f'no boundary file for {city}: {path}')
    with path.open(encoding='utf-8') as fh:
        gj = json.load(fh)
    feats = gj['features'] if gj.get('type') == 'FeatureCollection' else gj

    lons, lats = [], []

    def walk(c):
        if isinstance(c[0], (int, float)):
            lons.append(c[0])
            lats.append(c[1])
            return
        for part in c:
            walk(part)

    for f in feats:
        walk(f['geometry']['coordinates'])

    try:
        from pyproj import Transformer
    except ImportError as exc:
        raise SystemExit('pip install pyproj') from exc
    # always_xy so the argument order is (lon, lat) rather than pyproj's
    # CRS-declared (lat, lon) for EPSG:4326 - getting this backwards produces a
    # bbox in the North Sea that still fetches cleanly.
    tr = Transformer.from_crs('EPSG:4326', 'EPSG:27700', always_xy=True)
    es, ns = [], []
    for lon, lat in ((min(lons), min(lats)), (max(lons), max(lats)),
                     (min(lons), max(lats)), (max(lons), min(lats))):
        e, n = tr.transform(lon, lat)
        es.append(e)
        ns.append(n)
    return (
        int(math.floor((min(es) - PAD_M) / 1000) * 1000),
        int(math.floor((min(ns) - PAD_M) / 1000) * 1000),
        int(math.ceil((max(es) + PAD_M) / 1000) * 1000),
        int(math.ceil((max(ns) + PAD_M) / 1000) * 1000),
    )

# The service is free and shared. Being slow about it is the price of using it.
PAUSE_S = 1.0
RETRIES = 3


def tile_urls(city, bbox):
    """Yield (path, url) for each tile covering bbox."""
    min_e, min_n, max_e, max_n = bbox
    e = min_e
    while e < max_e:
        n = min_n
        while n < max_n:
            e2, n2 = min(e + TILE, max_e), min(n + TILE, max_n)
            url = (
                f'{BASE}?service=WCS&version=2.0.1&request=GetCoverage'
                f'&coverageId={COVERAGE}'
                f'&subset=E({e},{e2})&subset=N({n},{n2})'
                f'&format=image/tiff'
            )
            # Named by grid coordinate, not by city, so cities whose bounding
            # boxes overlap share the tile instead of fetching it twice.
            yield TILE_DIR / f'road_lden_{e}_{n}.tif', url
            n += TILE
        e += TILE


def fetch(path, url):
    """Download one tile, skipping if already present. Returns True on success."""
    if path.exists() and path.stat().st_size > 1000:
        print(f'  skip {path.name} (have it)')
        return True

    for attempt in range(1, RETRIES + 1):
        try:
            with urlopen(Request(url, headers={'User-Agent': UA}), timeout=300) as resp:
                data = resp.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            print(f'  {path.name}: attempt {attempt}/{RETRIES} failed ({exc})')
            time.sleep(PAUSE_S * attempt * 2)
            continue

        # A 504 comes back as an HTML error page with a 200-ish shape in some
        # gateways, so check the magic bytes rather than trusting the status.
        # TIFF is 'II*\0' little-endian or 'MM\0*' big-endian.
        if data[:4] not in (b'II*\x00', b'MM\x00*'):
            print(f'  {path.name}: attempt {attempt}/{RETRIES} returned non-TIFF ({len(data)} bytes)')
            time.sleep(PAUSE_S * attempt * 2)
            continue

        path.write_bytes(data)
        print(f'  got  {path.name} ({len(data) // 1024} KB)')
        return True

    print(f'  FAIL {path.name} after {RETRIES} attempts')
    return False


def fetch_city(city):
    """Fetch and mosaic one city. Returns 0 on success."""
    if city in WELSH:
        print(f'{city}: SKIPPED - Wales is not in the England coverage. '
              'Natural Resources Wales publishes its own Round 4 maps.')
        return 0

    bbox = city_bbox(city)
    out = mosaic_path(city)
    TILE_DIR.mkdir(parents=True, exist_ok=True)
    tiles = list(tile_urls(city, bbox))
    span_km = ((bbox[2] - bbox[0]) / 1000, (bbox[3] - bbox[1]) / 1000)
    print(f'\n{city}: {len(tiles)} tiles covering {bbox} '
          f'({span_km[0]:.0f}x{span_km[1]:.0f} km) at {TILE} m')

    failed = []
    for path, url in tiles:
        if not fetch(path, url):
            failed.append(path.name)
        time.sleep(PAUSE_S)

    if failed:
        print(f'\n{len(failed)} tiles failed: {failed}')
        print('Re-run to retry only those; completed tiles are skipped.')
        return 1

    try:
        import rasterio
        from rasterio.merge import merge
    except ImportError:
        print('\nTiles downloaded. Install rasterio to mosaic: pip install rasterio')
        return 0

    print('mosaicking...')
    srcs = [rasterio.open(p) for p, _ in tiles]
    mosaic, transform = merge(srcs)
    meta = srcs[0].meta.copy()
    meta.update(
        height=mosaic.shape[1],
        width=mosaic.shape[2],
        transform=transform,
        compress='deflate',
    )
    with rasterio.open(out, 'w', **meta) as dst:
        dst.write(mosaic)
    for s in srcs:
        s.close()

    # Report what is IN the mosaic, not just that one was written. A raster can
    # be valid and empty, which is exactly what the aircraft tier turned out to
    # be over most of its own grid, so "wrote 62 MB" is not evidence of data.
    try:
        import numpy as np
        with rasterio.open(out) as ds:
            arr = ds.read(1).astype('float64')
            nod = ds.nodata
        mask = np.isfinite(arr)
        if nod is not None:
            mask &= arr != nod
        mask &= arr > 0
        vals = arr[mask]
        pct = 100 * vals.size / arr.size if arr.size else 0
        detail = (f'{pct:.1f}% of cells carry a reading, '
                  f'{vals.min():.0f}-{vals.max():.0f} dB' if vals.size else 'NO DATA IN MOSAIC')
    except ImportError:
        detail = '(install numpy to report coverage)'

    size_mb = out.stat().st_size / 1e6
    print(f'wrote {out.name} ({mosaic.shape[2]}x{mosaic.shape[1]}, {size_mb:.1f} MB) - {detail}')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--city', help='city key, e.g. london or merseyside')
    ap.add_argument('--all', action='store_true', help='every city with a boundary file')
    args = ap.parse_args()

    if args.all:
        cities = sorted(p.name.replace('-boroughs.json', '') for p in OUT_DIR.glob('*-boroughs.json'))
        cities = [c for c in cities if c != 'nyc']
    elif args.city:
        cities = [args.city]
    else:
        ap.error('pass --city <key> or --all')

    rc = 0
    for city in cities:
        rc |= fetch_city(city)
    print('\nNext: scripts/load_defra_raster.py --attribute roadLdenDb over each mosaic.')
    return rc


if __name__ == '__main__':
    sys.exit(main())
