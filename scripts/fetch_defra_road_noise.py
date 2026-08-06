#!/usr/bin/env python3
"""Fetch the DEFRA Round 4 road-noise Lden raster for Greater London via WCS.

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

  pip install rasterio requests
  python scripts/fetch_defra_road_noise.py
"""

import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

BASE = 'https://environment.data.gov.uk/spatialdata/road-noise-all-metrics-england-round-4/wcs'
COVERAGE = '562c9d56-7c2d-4d42-83bb-578d6e97a517__Road_Noise_Lden_England_Round_4_All'

# Greater London in British National Grid (EPSG:27700), the raster's own CRS —
# so no reprojection is involved and the numbers stay faithful samples.
BBOX = (500000, 155000, 562000, 202000)
TILE = 20000

OUT_DIR = Path(__file__).resolve().parents[1] / 'data'
TILE_DIR = OUT_DIR / 'road_noise_tiles'
MOSAIC = OUT_DIR / 'defra_road_lden_london.tif'

# The service is free and shared. Being slow about it is the price of using it.
PAUSE_S = 1.0
RETRIES = 3


def tile_urls():
    """Yield (path, url) for each tile covering BBOX."""
    min_e, min_n, max_e, max_n = BBOX
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
            with urlopen(url, timeout=300) as resp:
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


def main():
    TILE_DIR.mkdir(parents=True, exist_ok=True)
    tiles = list(tile_urls())
    print(f'{len(tiles)} tiles covering {BBOX} at {TILE} m')

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

    print('\nmosaicking...')
    srcs = [rasterio.open(p) for p, _ in tiles]
    mosaic, transform = merge(srcs)
    meta = srcs[0].meta.copy()
    meta.update(
        height=mosaic.shape[1],
        width=mosaic.shape[2],
        transform=transform,
        compress='deflate',
    )
    with rasterio.open(MOSAIC, 'w', **meta) as dst:
        dst.write(mosaic)
    for s in srcs:
        s.close()

    size_mb = MOSAIC.stat().st_size / 1e6
    print(f'wrote {MOSAIC} ({mosaic.shape[2]}x{mosaic.shape[1]}, {size_mb:.1f} MB)')
    print('\nNext: python scripts/load_defra_raster.py --geotiff data/defra_road_lden_london.tif ...')
    return 0


if __name__ == '__main__':
    sys.exit(main())
