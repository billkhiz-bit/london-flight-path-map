"""The ground under the overflight counter's cones, from OS Terrain 50 (2026-10-26).

`scripts/build_ground_grid.py` turns OS Terrain 50's 10 km tiles (50 m cells, NORTH row first) into one grid
of 100 m cells on the counter's own rows and columns (SOUTH row first, row j is northing j * 100). A tile
placed upside down or a column out would put every hill in the wrong place and pass unnoticed, so these
tests build a tiny zip of tile zips as OS publishes them and read it back. Offline only.
"""
import importlib.util
import io
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load(name):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, REPO / 'scripts' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


gg = _load('build_ground_grid')
ao = _load('adsb_overflights')

# 4 x 4 cells of 50 m, NORTH row first: the north-west 100 m block is 10, the south-east 40.
TILE = [[10, 10, 20, 20], [10, 10, 20, 20], [30, 30, 40, 40], [30, 31, 40, 40]]


def _asc(rows, xll=10_000, yll=20_000, size=50):
    head = f'ncols {len(rows[0])}\nnrows {len(rows)}\nxllcorner {xll}\nyllcorner {yll}\ncellsize {size}\n'
    return head + '\n'.join(' '.join(str(v) for v in r) for r in rows) + '\n'


def _zip(tmp_path, asc_text, name='data/sk/sk12_OST50GRID_20260602.zip'):
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, 'w') as z:
        z.writestr('SK12.asc', asc_text)
    path = tmp_path / 'terr50_gagg_gb.zip'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr(name, inner.getvalue())
    return path


def test_the_grid_is_the_counters():
    assert gg.CELL_M == ao.CELL_M
    assert ao.GROUND_GRID == gg.GRID


def test_a_tile_lands_south_row_first_at_its_corner(tmp_path):
    grid, meta = gg.build(_zip(tmp_path, _asc(TILE)), min_tiles=1)
    j, i = 20_000 // 100, 10_000 // 100
    # Row j (the tile's southern 100 m) holds the SOUTH blocks: 30 (a 31 rounds the mean 30.25 down) and 40.
    assert grid[j:j + 2, i:i + 2].tolist() == [[30, 40], [10, 20]]
    assert grid[j - 1, i] == 0 and grid[j, i + 2] == 0  # beyond the tile: unpublished, the sea
    assert meta['release'] == '20260602' and meta['tiles'] == 1


def test_a_tile_off_the_10_km_grid_or_not_50_m_is_refused(tmp_path):
    with pytest.raises(SystemExit, match='Terrain 50'):
        gg.build(_zip(tmp_path, _asc(TILE, size=25)))
    with pytest.raises(SystemExit, match='Terrain 50'):
        gg.build(_zip(tmp_path, _asc(TILE, xll=10_050)))


def test_a_zip_with_no_tiles_is_refused(tmp_path):
    path = tmp_path / 'empty.zip'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('readme.txt', 'nothing here')
    with pytest.raises(SystemExit, match='no Terrain 50 tiles'):
        gg.build(path)


def test_a_zip_short_of_the_gb_set_is_refused(tmp_path):
    # 2026-10-27 review: a tile missing from the zip reads as sea level (0 m), so inland cones there would be too
    # wide and count high while the day files said "OS Terrain 50 under the aircraft". The whole set, or nothing.
    with pytest.raises(SystemExit, match='fewer than the 2858'):
        gg.build(_zip(tmp_path, _asc(TILE)))
