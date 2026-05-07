"""
DEFRA noise raster downloader via WCS (Web Coverage Service).

Bypasses the interactive download UI's threshold by fetching the raster
tile-by-tile via the OGC WCS endpoint, then stitches the tiles with
rasterio. Used to grab the Aircraft (or Road) Noise GeoTIFF for the
Greater London area when DEFRA's UI refuses bulk downloads.

USAGE:

  # 1. Get the WCS endpoint URL from data.gov.uk:
  #    On https://www.data.gov.uk/dataset/airport-noise-all-metrics-england-round-4
  #    find the "_WCS" download link, right-click, "Copy link address".
  #    It looks something like:
  #      https://environment.data.gov.uk/spatialdata/airport-noise-all-metrics-england-round-4/wcs
  #
  # 2. Discover available coverages (layer names) so we know what to fetch:
  #    python scripts/download_defra_wcs.py --wcs-url <URL> --list-coverages
  #
  # 3. Download Greater London tiles + stitch into one GeoTIFF:
  #    python scripts/download_defra_wcs.py --wcs-url <URL> \
  #        --coverage Airport_Noise_ALL_Lden \
  #        --bbox london --output data/defra_lden_2022.tif
  #
  # 4. (Optional) test fetch a single small tile first to sanity-check
  #    that WCS responds + the coverage ID is correct:
  #        --bbox test
  #
  # The London bbox is in British National Grid (EPSG:27700) and covers
  # M25 commuter belt + Heathrow approach corridors. Tile size is 5 km
  # (small enough to avoid threshold; ~110 tiles for Greater London,
  # ~5 min total fetch time).

PRE-REQUISITES (~2 min):

    pip install rasterio requests

OUTPUT:

  A single mosaic GeoTIFF saved to the path given by --output. The
  loader (scripts/load_defra_raster.py) reads this and samples at every
  postcode centroid.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# British National Grid (EPSG:27700) bboxes. DEFRA publishes in BNG.
# Coordinates are (minx, miny, maxx, maxy) in metres.
BBOXES_BNG = {
    # Greater London + airport approach corridors. Covers Heathrow,
    # London City, all 33 boroughs, M25 commuter belt. Excludes Gatwick
    # (south, separate Sussex coverage), Stansted (north-east, Essex),
    # Luton (north, Bedfordshire). Add those as separate downloads if
    # you need them.
    'london': (493000, 156000, 568000, 207000),
    # Tiny test bbox - 2km square in central London.
    # If WCS works for this, the whole script will work.
    'test':   (530000, 179000, 532000, 181000),
}
TILE_SIZE_M = 5000  # 5 km tiles - small enough to avoid throttling
TIMEOUT_S = 30


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--wcs-url', required=True,
                        help='WCS endpoint URL from the data.gov.uk dataset page')
    parser.add_argument('--list-coverages', action='store_true',
                        help='List available coverage IDs via GetCapabilities')
    parser.add_argument('--coverage',
                        help='Coverage ID to fetch, e.g. Airport_Noise_ALL_Lden')
    parser.add_argument('--bbox', choices=list(BBOXES_BNG.keys()), default='london',
                        help='Pre-defined bbox (default: london)')
    parser.add_argument('--output', default='data/defra_lden_2022.tif',
                        help='Output GeoTIFF path (default: data/defra_lden_2022.tif)')
    args = parser.parse_args()

    try:
        import requests
    except ImportError:
        print('Missing requests. Install: pip install requests')
        sys.exit(1)

    if args.list_coverages:
        list_coverages(args.wcs_url, requests)
        return

    if not args.coverage:
        print('--coverage required (run with --list-coverages first to discover IDs)')
        sys.exit(1)

    try:
        import rasterio
        from rasterio.merge import merge
    except ImportError:
        print('Missing rasterio. Install: pip install rasterio')
        sys.exit(1)

    bbox = BBOXES_BNG[args.bbox]
    print(f'Bbox ({args.bbox}, BNG metres): {bbox}')
    print(f'Coverage: {args.coverage}')
    print(f'Output: {args.output}')

    fetch_and_mosaic(
        wcs_url=args.wcs_url,
        coverage_id=args.coverage,
        bbox=bbox,
        output_path=args.output,
        requests=requests,
        rasterio=rasterio,
        merge=merge,
    )


def list_coverages(wcs_url, requests):
    """Hit GetCapabilities so the user can see which coverage IDs exist."""
    print('Querying WCS GetCapabilities ...')
    r = requests.get(wcs_url, params={
        'service': 'WCS',
        'version': '2.0.1',
        'request': 'GetCapabilities',
    }, timeout=TIMEOUT_S)
    r.raise_for_status()
    text = r.text
    # Pull out coverage IDs from the XML response. Could parse properly,
    # but a regex over <wcs:CoverageId> elements gets us 95% there with
    # zero deps.
    import re
    ids = re.findall(r'<wcs:CoverageId[^>]*>([^<]+)</wcs:CoverageId>', text)
    if not ids:
        # Some servers use just <CoverageId>
        ids = re.findall(r'<CoverageId[^>]*>([^<]+)</CoverageId>', text)
    if ids:
        print(f'\n{len(ids)} coverage(s) found:')
        for cid in ids:
            print(f'  {cid}')
        print('\nPick the one ending in _Lden for day-evening-night.')
    else:
        print('Could not parse coverage IDs. Raw response (first 500 chars):')
        print(text[:500])


def fetch_and_mosaic(wcs_url, coverage_id, bbox, output_path, requests, rasterio, merge):
    """Iterate over a tile grid covering the bbox, fetch each as GeoTIFF
    via WCS GetCoverage, write to a temp directory, then stitch them all
    into a single mosaic with rasterio.merge."""
    minx, miny, maxx, maxy = bbox
    tile_size = TILE_SIZE_M

    # Generate the list of tile bboxes
    tiles = []
    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            tx_max = min(x + tile_size, maxx)
            ty_max = min(y + tile_size, maxy)
            tiles.append((x, y, tx_max, ty_max))
            y += tile_size
        x += tile_size

    print(f'\n{len(tiles)} tiles to fetch. Estimated runtime: '
          f'~{len(tiles) * 3 // 60} min at 3 s/tile.\n')

    # Output dir setup
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    tile_dir = output.parent / '_tmp_tiles'
    tile_dir.mkdir(exist_ok=True)

    # Fetch each tile
    fetched = []
    for i, tile_bbox in enumerate(tiles, 1):
        tx_min, ty_min, tx_max, ty_max = tile_bbox
        tile_path = tile_dir / f'tile_{tx_min}_{ty_min}.tif'

        if tile_path.exists() and tile_path.stat().st_size > 1024:
            print(f'  [{i}/{len(tiles)}] cached: {tile_path.name}')
            fetched.append(tile_path)
            continue

        print(f'  [{i}/{len(tiles)}] fetching {tx_min},{ty_min}-{tx_max},{ty_max} ...',
              end=' ', flush=True)
        ok = fetch_tile(wcs_url, coverage_id, tile_bbox, tile_path, requests)
        if ok:
            fetched.append(tile_path)
            print(f'OK ({tile_path.stat().st_size // 1024} KB)')
        else:
            print('FAILED (skipping)')

        # Be polite to DEFRA's WCS endpoint
        time.sleep(0.5)

    if not fetched:
        print('\nNo tiles fetched. Check WCS URL and coverage ID.')
        sys.exit(1)

    print(f'\nStitching {len(fetched)} tiles into {output} ...')
    sources = [rasterio.open(p) for p in fetched]
    mosaic, transform = merge(sources)
    profile = sources[0].profile
    profile.update({
        'height': mosaic.shape[1],
        'width': mosaic.shape[2],
        'transform': transform,
        'compress': 'lzw',
    })
    with rasterio.open(output, 'w', **profile) as dst:
        dst.write(mosaic)
    for s in sources:
        s.close()

    print(f'Done. {output} is {output.stat().st_size // 1024 // 1024} MB.')
    print('Next step:')
    print('  AWS_PROFILE=flightmap python scripts/load_defra_raster.py --self-test')
    print('  AWS_PROFILE=flightmap python scripts/load_defra_raster.py --limit 100 --dry-run')
    print('  AWS_PROFILE=flightmap python scripts/load_defra_raster.py')


def fetch_tile(wcs_url, coverage_id, bbox, output_path, requests):
    """Fetch one WCS tile as GeoTIFF. Returns True on success."""
    minx, miny, maxx, maxy = bbox
    params = {
        'service': 'WCS',
        'version': '2.0.1',
        'request': 'GetCoverage',
        'coverageId': coverage_id,
        'subset': [
            f'E({minx},{maxx})',  # Easting (BNG)
            f'N({miny},{maxy})',  # Northing (BNG)
        ],
        'format': 'image/tiff',
    }
    try:
        r = requests.get(wcs_url, params=params, timeout=TIMEOUT_S)
    except requests.RequestException as exc:
        # Catch only network-layer failures (Timeout, ConnectionError,
        # SSLError, etc.); audit N-Code-4 flagged the prior bare except
        # which would also swallow KeyboardInterrupt + bugs in the call
        # chain. requests.RequestException is the documented base class.
        print(f'(network error: {type(exc).__name__}: {exc})', end=' ')
        return False

    if r.status_code != 200:
        print(f'(HTTP {r.status_code})', end=' ')
        return False

    # Sanity-check that we got a TIFF (not an XML error response)
    if not r.content.startswith(b'II*\x00') and not r.content.startswith(b'MM\x00*'):
        print('(not a TIFF, got XML/text)', end=' ')
        return False

    output_path.write_bytes(r.content)
    return True


if __name__ == '__main__':
    main()
