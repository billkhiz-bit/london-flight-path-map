"""The building-heights pilot's arithmetic (scripts/lidar_building_heights.py, 2026-10-23).

Offline: no tile, outline or postcode is read. What is held here is what a quiet change would get wrong without
any number looking odd: which 5 km tile a point is in (the EA names tiles by their south-west corner), which pixels
an outline covers, the storey rule the pilot validated (the MEDIAN roof, not the ridge, which read a storey high),
and how "near this postcode" is counted two ways, ties going to the lower band so a street is never overstated.
"""

import os
import subprocess
import sys

REPO = os.path.normpath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, os.path.join(REPO, 'scripts'))

import lidar_building_heights as lbh  # noqa: E402


def test_a_point_is_in_the_tile_named_by_its_south_west_corner():
    # The tile the EA calls TQ17sw starts at OS grid 510000, 170000 (its world file: 510000.5, 174999.5)
    assert lbh.tile_id(510000.5, 174999.5) == 'TQ1070'
    assert lbh.tile_id(507008, 170318) == 'TQ0570'
    assert lbh.tile_id(514999.9, 179999.9) == 'TQ1075'


def test_an_outline_covers_the_pixels_whose_centres_it_holds():
    square = [(10, 10), (14, 10), (14, 14), (10, 14), (10, 10)]
    assert int(lbh.polygon_mask(square, 10, 14, 4, 4).sum()) == 16
    # an L (concave): 4 x 2 along the bottom and 2 x 2 above its left end; edges on whole metres, so no pixel
    # centre lies on an edge (a centre exactly on one is an arbitrary call, not a test)
    ell = [(10, 10), (14, 10), (14, 12), (12, 12), (12, 14), (10, 14), (10, 10)]
    mask = lbh.polygon_mask(ell, 10, 14, 4, 4)
    assert int(mask.sum()) == 12
    assert not mask[0, 3] and mask[0, 0] and mask[3, 3]  # row 0 is the top: its right half is outside the L
    # a window beside the outline sees none of it
    assert int(lbh.polygon_mask(square, 20, 14, 4, 4).sum()) == 0


def test_storeys_come_from_the_median_roof_at_3_m_a_storey():
    assert [lbh.storeys(h) for h in (0.8, 5.0, 7.0, 8.4, 9.1, 30.0)] == [1, 2, 2, 3, 3, 10]


def test_near_a_postcode_counts_buildings_and_floor_space_apart():
    # three two-storey houses and one four-storey block: houses by count, the block by floor space
    near = [(80, 2), (80, 2), (80, 2), (400, 4)]
    assert lbh.near_summary(near) == ('1 to 2 storeys', '3 to 5 storeys', 4)


def test_a_tie_goes_to_the_lower_band_so_a_street_is_never_overstated():
    assert lbh.near_summary([(100, 2), (50, 4)])[0] == '1 to 2 storeys'
    assert lbh.near_summary([]) is None


def test_the_pilot_writes_only_to_a_gitignored_folder():
    assert lbh.LIDAR == lbh.ROOT / 'data' / 'lidar'
    res = subprocess.run(['git', 'check-ignore', '-q', 'data/lidar/hounslow-buildings.csv'], cwd=REPO, check=False)  # noqa: S603, S607  (git, fixed arguments)
    assert res.returncode == 0, 'data/lidar/ must stay gitignored: it holds 1.6 GB of tiles for one borough'
