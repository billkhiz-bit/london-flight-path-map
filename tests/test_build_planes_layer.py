"""The full map's planes overhead layer (Bill's pick B2, 2026-11-02): every postcode its own step, nothing grouped.

`scripts/build_planes_layer.py` draws one picture per city and kind of day from the published per-postcode files.
These tests hold, on synthetic figures: the four steps and their edges (10, 50, 100, 200; '<1' and 9 clear); a range
(a postcode on a cone's edge) giving its least and most step, several airports the higher of each end separately, an
airport with no figure for the kind of day ignored; a picture drawn so a postcode's pixels carry its step, an edge
postcode striped between its two steps, a pixel beyond REACH_M left clear and an `approx` position never drawn; the
corners in index.json landing on the picture's own grid in Web Mercator (the map's projection); and --check catching
a stale, missing or extra picture and a manifest that does not describe the files. Offline only.
"""
import importlib.util
import io
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from pyproj import Transformer

REPO = Path(__file__).resolve().parents[1]


def _load():
    name = 'build_planes_layer'
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, REPO / 'scripts' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


L = _load()
CLASSES = ['westerly', 'easterly', 'mixed']
TO_BNG = Transformer.from_crs('EPSG:4326', 'EPSG:27700', always_xy=True)


def test_steps_and_their_edges():
    assert [L.step(v) for v in ('<1', 0, 9, 10, 49, 50, 99, 100, 199, 200, 629)] == [0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4]


def test_ranges_and_several_airports():
    # One airport, a range: least and most steps.
    assert L.least_most({'LHR': [[3, 316], 4, 7]}, 0) == (0, 4)
    # Two airports: the higher step for each END separately (least from one, most from the other).
    assert L.least_most({'LHR': [[60, 120], None, None], 'LCY': [[15, 250], None, None]}, 0) == (2, 4)
    # No figure for this kind of day: ignored; no airports at all: clear.
    assert L.least_most({'LHR': [150, None, '<1']}, 1) == (0, 0)
    assert L.least_most({'LHR': [150, None, '<1']}, 2) == (0, 0)
    assert L.least_most({}, 0) == (0, 0)


def _city(points):
    """Draw a synthetic city: points = [(postcode, easting, northing, figures)] near Kew."""
    pcs = np.array([p for p, *_ in points])
    east = np.array([e for _, e, _, _ in points], float)
    north = np.array([n for _, _, n, _ in points], float)
    figures = {p: f for p, _, _, f in points if f is not None}
    return L.draw_city('testcity', pcs, east, north, figures, CLASSES, TO_BNG)


def _rgba(im):
    return np.array(im.convert('RGBA'))


def _at(entry, im, east, north):
    """The pixel of a picture under a British grid point, through index.json's corners (as the map places it)."""
    to_ll = Transformer.from_crs('EPSG:27700', 'EPSG:4326', always_xy=True)
    lon, lat = to_ll.transform(east, north)
    w, s, e, n = entry['bounds']
    W, H = entry['size']
    x = (L.merc_x(lon) - L.merc_x(w)) / (L.merc_x(e) - L.merc_x(w)) * W
    y = (L.merc_y(n) - L.merc_y(lat)) / (L.merc_y(n) - L.merc_y(s)) * H
    return _rgba(im)[int(y), int(x)]


def _hex(rgba):
    return '#' + ''.join(f'{int(c):02x}' for c in rgba[:3])


def test_a_postcode_paints_its_own_step_and_nothing_is_grouped():
    pts = [('TW9 1AA', 518000, 176000, {'LHR': [250, 3, 120]}),
           ('TW9 1AB', 518600, 176000, {'LHR': [60, '<1', 20]}),
           ('TW9 1AD', 519200, 176000, None)]          # not measured: clear, but still claims its own ground
    imgs, entry = _city(pts)
    west = imgs['testcity-westerly.png']
    assert _hex(_at(entry, west, 518000, 176000)) == L.COLOURS[4]
    assert _hex(_at(entry, west, 518600, 176000)) == L.COLOURS[2]
    assert _at(entry, west, 519200, 176000)[3] == 0        # not measured: clear, never borrowed from a neighbour
    mixed = imgs['testcity-mixed.png']
    assert _hex(_at(entry, mixed, 518000, 176000)) == L.COLOURS[3]
    assert _hex(_at(entry, mixed, 518600, 176000)) == L.COLOURS[1]
    assert _at(entry, imgs['testcity-easterly.png'], 518000, 176000)[3] == 0   # 3 a day: under 10, clear


def test_an_edge_postcode_is_striped_between_its_two_steps():
    # Least under 10 (clear), most 200+: about half the pixels near it are 200+, the rest clear, nothing else.
    imgs, entry = _city([('TW4 5AA', 510000, 176000, {'LHR': [[3, 316], 4, 7]})])
    near = [_at(entry, imgs['testcity-westerly.png'], 510000 + dx, 176000 + dy)
            for dx in range(-100, 101, 10) for dy in range(-100, 101, 10)]
    painted = [c for c in near if c[3]]
    assert {_hex(c) for c in painted} == {L.COLOURS[4]}
    assert 0.35 < len(painted) / len(near) < 0.65
    # Both ends painted (50-99 and 100-199): stripes of the two colours, no clear pixel.
    imgs, entry = _city([('TW4 5AB', 510000, 176000, {'LHR': [[60, 150], 4, 7]})])
    near = [_at(entry, imgs['testcity-westerly.png'], 510000 + dx, 176000 + dy)
            for dx in range(-100, 101, 10) for dy in range(-100, 101, 10)]
    assert {(_hex(c) if c[3] else 'clear') for c in near} == {L.COLOURS[2], L.COLOURS[3]}


def test_beyond_reach_is_clear_and_the_corners_are_the_grid():
    # Two postcodes 1 km apart: the ground between them, beyond REACH_M of both, is inside the picture and clear.
    imgs, entry = _city([('TW9 1AA', 518000, 176000, {'LHR': [250, 3, 120]}),
                         ('TW9 1ZZ', 519000, 176000, {'LHR': [250, 3, 120]})])
    west = imgs['testcity-westerly.png']
    assert _hex(_at(entry, west, 518000 + L.REACH_M * 0.6, 176000)) == L.COLOURS[4]
    assert _at(entry, west, 518500, 176000)[3] == 0
    # The corners give square pixels of PX_M on the ground at the city's middle, in Web Mercator.
    w, s, e, n = entry['bounds']
    W, H = entry['size']
    lat0 = Transformer.from_crs('EPSG:27700', 'EPSG:4326', always_xy=True).transform(518000, 176000)[1]
    px_x = (L.merc_x(e) - L.merc_x(w)) / W
    px_y = (L.merc_y(n) - L.merc_y(s)) / H
    # index.json rounds the corners to 1e-7 degree (about 1 cm), so square to 1 in 10,000, not exactly.
    assert px_x == pytest.approx(px_y, rel=1e-4)
    assert px_x * math.cos(math.radians(lat0)) == pytest.approx(L.PX_M, rel=1e-4)


def test_check_catches_stale_missing_extra_and_manifest(tmp_path):
    imgs, entry = _city([('TW9 1AA', 518000, 176000, {'LHR': [250, 3, 120]})])
    files = {**imgs, 'index.json': b'{}\n'}
    out, man = tmp_path / 'layer', tmp_path / 'manifest.json'
    L.write(files, out, man)
    assert L.check(files, out, man) == []
    # A picture that SHOWS something else is stale, even one pixel; the same picture re-packed is not.
    im = Image.open(io.BytesIO((out / 'testcity-westerly.png').read_bytes())).convert('RGBA')
    im.putpixel((0, 0), (255, 0, 0, 255))
    im.save(out / 'testcity-westerly.png')
    probs = L.check(files, out, man)
    assert 'stale: testcity-westerly.png' in probs
    assert any('does not describe' in p for p in probs)
    L.write(files, out, man)
    (out / 'testcity-westerly.png').write_bytes(L.png(Image.open(out / 'testcity-westerly.png')))  # re-packed
    man.write_text(json.dumps(L.manifest_of(out), indent=1) + '\n', encoding='utf-8')
    assert L.check(files, out, man) == []
    (out / 'testcity-mixed.png').unlink()
    (out / 'old-westerly.png').write_bytes(b'x')
    probs = L.check(files, out, man)
    assert 'missing: testcity-mixed.png' in probs and 'no longer built: old-westerly.png' in probs


def test_the_built_london_picture_tells_kew_what_the_front_page_does():
    """On the REAL built files: TW9 3PZ is told 310 a day flying west, 4 flying east, 168 both ways (the front page's
    example). Its pixel, found through index.json's corners as the map places it, must be 200+, clear, 100-199.
    Skipped where the gitignored inputs are absent (a clone without the tracks); preflight's --check reports that."""
    index_p = REPO / 'data' / 'planes-layer' / 'index.json'
    tw9 = REPO / 'data' / 'planes' / 'TW9.json'
    if not (index_p.exists() and tw9.exists() and L.AVERAGES.exists()):
        pytest.skip('built planes files absent (gitignored)')
    told = json.loads(tw9.read_text(encoding='utf-8'))['postcodes']['TW9 3PZ']['LHR']
    want = {'westerly': L.COLOURS[L.step(told[0])], 'easterly': None if L.step(told[1]) == 0 else L.COLOURS[L.step(told[1])],
            'mixed': L.COLOURS[L.step(told[2])]}
    z = np.load(L.AVERAGES, allow_pickle=False)
    i = int(np.flatnonzero(z['postcode'] == 'TW9 3PZ')[0])
    e, n = float(z['easting'][i]), float(z['northing'][i])
    entry = json.loads(index_p.read_text(encoding='utf-8'))['cities']['london']
    for cls, colour in want.items():
        im = Image.open(REPO / 'data' / 'planes-layer' / entry['files'][cls])
        px = _at(entry, im, e, n)
        if colour is None:
            assert px[3] == 0, (cls, px)
        else:
            assert px[3] == 255 and _hex(px) == colour, (cls, _hex(px), colour)


def test_approx_positions_are_never_drawn():
    # NSPL gridind 1 and 3 are ONS's own grid references; 5 and 6 are imputed or a sector mean (the `approx` flag).
    gridind = np.array([1, 3, 5, 6, 1], np.int8)
    east = np.array([1.0, 2.0, 3.0, 4.0, np.nan])
    north = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    assert L.placed(gridind, east, north).tolist() == [True, True, False, False, False]


# THE DISTRICT UNDER A TAP (2026-11-03): <city>-district-ids.json, read back exactly as the full map reads it.

def test_the_district_grid_reads_back_every_cell_as_drawn():
    dg = np.array([['TW4', 'TW4', 'TW5', 'TW5', 'TW5', 'TW3'],
                   ['TW4', 'TW4', 'TW5', 'TW5', 'TW3', 'TW3'],
                   ['TW4', 'TW4', 'TW4', 'TW4', 'TW3', 'TW3'],
                   ['TW4', 'TW4', 'TW4', 'TW4', 'TW3', 'TW3']])
    valid = np.ones(dg.shape, bool)
    valid[2:, :2] = False  # no postcode near: code 0, never a district
    ids = json.loads(L.district_ids(dg, valid, cell=2))
    assert ids['cell'] == 2 and ids['size'] == [3, 2] and ids['names'] == ['TW3', 'TW4', 'TW5']
    # Each cell is decided by its top-left picture pixel; every picture pixel reads its cell's district.
    want = {(0, 0): 'TW4', (1, 1): 'TW4', (2, 0): 'TW5', (3, 1): 'TW5', (4, 0): 'TW5', (5, 1): 'TW5',
            (0, 2): None, (1, 3): None, (2, 2): 'TW4', (3, 3): 'TW4', (4, 2): 'TW3', (5, 3): 'TW3'}
    assert {px: L.district_at(ids, *px) for px in want} == want
    for off in ((-1, 0), (0, -1), (6, 0), (0, 4), (99, 99)):  # off the picture: nothing, never the edge's district
        assert L.district_at(ids, *off) is None


def test_the_district_grid_runs_cover_each_row_exactly():
    rng = np.random.default_rng(3)
    dg = rng.choice(np.array(['E1', 'E2', 'E3']), size=(40, 60))
    valid = rng.random((40, 60)) > 0.2
    ids = json.loads(L.district_ids(dg, valid, cell=2))
    for row in ids['rows']:
        assert sum(row[1::2]) == ids['size'][0] and all(n > 0 for n in row[1::2])
        assert all(row[i] != row[i + 2] for i in range(0, len(row) - 2, 2))  # runs merged, never split
    for r in range(0, 40, 2):
        for c in range(0, 60, 2):
            assert L.district_at(ids, c, r) == (str(dg[r, c]) if valid[r, c] else None)
