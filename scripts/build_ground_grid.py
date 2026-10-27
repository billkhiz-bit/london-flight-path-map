"""The ground's height above sea level on the overflight counter's 100 m grid, from OS Terrain 50.

WHY THIS EXISTS (2026-10-26)
----------------------------
CAP 1498's overflight is an aircraft above an elevation angle seen from the ground, so the cone's radius is
the aircraft's height ABOVE THE OBSERVER over tan(angle). scripts/adsb_overflights.py drew it from the
height above SEA LEVEL, so on high ground every cone was too wide and every count erred HIGH. Measured at the
postcodes with a plane a day or more on westerly days (Bill asked "is this accurate"): the ground under them
has a median of 26 m in London but 87-131 m in Manchester, West Yorkshire and the West Midlands, so the cones
there were drawn a median 77-116 m too wide, always in the same direction.

The counter now takes the ground UNDER THE AIRCRAFT from this grid. Judging each cell against its own ground
is exact but multiplies the work by the ~1,000 cells a cone covers; the ground under the aircraft leaves an
error of 0.885 x the change in ground across the cone's radius, in either direction, so it cancels over many
passes: measured at those postcodes, a median 3-14 m of ground change at 500 m and 8-33 m at 2 km, against
the 26-131 m bias it replaces.

THE GRID: data/terrain50/gb-ground-100m.npy (int16 metres, gitignored, ~180 MB) and a .json beside it naming
the release. Row j, column i is the 100 m cell whose south-west corner is (i * 100, j * 100) on the British
National Grid, as in adsb_overflights.py; each value is the mean of the four 50 m Terrain 50 cells inside it,
rounded to the metre. A 10 km tile OS does not publish is all sea and reads 0, which is sea level.

SOURCE: OS Terrain 50, ASCII grid, GB (OGL v3: "Contains OS data (c) Crown copyright and database right"),
from the OS Downloads API, which needs no key:
    https://api.os.uk/downloads/v1/products/Terrain50/downloads?area=GB&format=ASCII+Grid+and+GML+%28Grid%29&redirect
saved as data/terrain50/download/terr50_gagg_gb.zip (a download: read it under python -I).

    python -I scripts/build_ground_grid.py            # write the grid from the zip
    python -I scripts/build_ground_grid.py --at 519150,176750   # the ground in one cell of the written grid
"""

import argparse
import io
import json
import re
import sys
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
ZIP = ROOT / 'data' / 'terrain50' / 'download' / 'terr50_gagg_gb.zip'
GRID = ROOT / 'data' / 'terrain50' / 'gb-ground-100m.npy'
CELL_M = 100  # adsb_overflights.CELL_M: held equal by a test
TILE_M = 10_000
EXTENT_E, EXTENT_N = 700_000, 1_300_000  # Great Britain on the National Grid; Terrain 50 stays inside it
# The tiles in the GB set (release 20260602, counted 2026-10-27). A tile missing from the zip would read as sea
# level, the bias this grid exists to remove, so a short zip is refused rather than built.
GB_TILES = 2858


def read_tile(text):
    """(header, 50 m heights north row first) from one Terrain 50 .asc file."""
    lines = text.split('\n', 5)
    head = {ln.split()[0].lower(): float(ln.split()[1]) for ln in lines[:5]}
    if head['cellsize'] != 50 or head['xllcorner'] % TILE_M or head['yllcorner'] % TILE_M:
        raise SystemExit(f'not a Terrain 50 tile on the 10 km grid: {head}')
    grid = np.array(lines[5].split(), dtype=np.float32).reshape(int(head['nrows']), int(head['ncols']))
    return head, grid


def to_100m(grid):
    """The mean of each 2 x 2 block of 50 m cells, SOUTH row first (the counter's row order)."""
    n, m = grid.shape
    return grid.reshape(n // 2, 2, m // 2, 2).mean(axis=(1, 3))[::-1]


def build(zip_path=ZIP, min_tiles=GB_TILES):
    """(int16 grid [rows, cols], provenance) from the GB zip of 10 km tile zips, refused if it holds fewer than
    `min_tiles` (the whole GB set unless a test says otherwise)."""
    rows, cols = EXTENT_N // CELL_M, EXTENT_E // CELL_M
    out = np.zeros((rows, cols), np.int16)
    releases, tiles = set(), 0
    with zipfile.ZipFile(zip_path) as outer:
        for name in outer.namelist():
            if not name.lower().endswith('.zip'):
                continue
            stamp = re.search(r'_(\d{8})\.zip$', name, re.I)
            if stamp:
                releases.add(stamp.group(1))
            with zipfile.ZipFile(io.BytesIO(outer.read(name))) as inner:
                asc = [n for n in inner.namelist() if n.lower().endswith('.asc')]
                if len(asc) != 1:
                    raise SystemExit(f'{name}: expected one .asc, found {asc}')
                head, grid = read_tile(inner.read(asc[0]).decode('ascii'))
            j0, i0 = int(head['yllcorner']) // CELL_M, int(head['xllcorner']) // CELL_M
            block = np.rint(to_100m(grid)).astype(np.int16)
            out[j0:j0 + block.shape[0], i0:i0 + block.shape[1]] = block
            tiles += 1
    if not tiles:
        raise SystemExit(f'{zip_path}: no Terrain 50 tiles in it')
    if tiles < min_tiles:
        raise SystemExit(f'{zip_path}: {tiles} Terrain 50 tiles, fewer than the {min_tiles} of the GB set: the missing '
                         'land would read as sea level. Download the whole set again.')
    meta = {
        'source': 'OS Terrain 50 (ASCII grid, GB)', 'licence': 'OGL v3: Contains OS data (c) Crown copyright and '
        'database right', 'release': max(releases) if releases else 'unknown', 'tiles': tiles, 'cell_m': CELL_M,
        'value': 'metres above sea level, mean of the four 50 m cells, rounded; unpublished tiles (sea) 0',
        'generator': 'scripts/build_ground_grid.py',
    }
    return out, meta


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--at', help='print the ground in the cell holding this BNG point (easting,northing)')
    a = ap.parse_args()
    if a.at:
        e, n = (float(v) for v in a.at.split(','))
        grid = np.load(GRID, mmap_mode='r')
        print(f'{int(grid[int(n // CELL_M), int(e // CELL_M)])} m')
        return 0
    if not ZIP.exists():
        print(f'{ZIP} is missing: download it (see this script\'s docstring)', file=sys.stderr)
        return 1
    grid, meta = build()
    GRID.parent.mkdir(parents=True, exist_ok=True)
    partial = GRID.with_suffix('.npy.partial')
    with open(partial, 'wb') as fh:
        np.save(fh, grid)
    partial.replace(GRID)
    GRID.with_suffix('.json').write_text(json.dumps(meta, indent=1), encoding='utf-8')
    print(f'{GRID.name}: {meta["tiles"]} tiles, release {meta["release"]}, highest {int(grid.max())} m')
    return 0


if __name__ == '__main__':
    sys.exit(main())
