"""Tests for scripts/build_bayarea_flood.py, the Bay Area's flood input (release 2).

FEMA's file arrives from a US runner, so the reader is tested on stand-in polygons: a point in the 1%
zone counts, a point in a polygon's HOLE does not, zone D and "no polygon at all" are UNKNOWN rather
than safe, overlapping studies take the riskier reading, and the check reds a city whose residents are
mostly unknown and a share that is not its counts. Offline only.
"""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('build_bayarea_flood', REPO_ROOT / 'scripts' / 'build_bayarea_flood.py')
bf = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bf)


def square(x0, y0, size):
    return [[x0, y0], [x0, y0 + size], [x0 + size, y0 + size], [x0 + size, y0], [x0, y0]]


def feature(zone, sfha, *rings):
    return {'attributes': {'FLD_ZONE': zone, 'SFHA_TF': 'T' if sfha else 'F'}, 'geometry': {'rings': list(rings)}}


FEATURES = [
    # an AE zone with a hole in it (an island of higher ground)
    feature('AE', True, square(-122.30, 37.80, 0.04), square(-122.29, 37.81, 0.01)),
    # ...which FEMA maps as its own X polygon, as it maps all studied land
    feature('X', False, square(-122.29, 37.81, 0.01)),
    # minimal-risk X beside it, and an undetermined D further east
    feature('X', False, square(-122.26, 37.80, 0.04)),
    feature('D', False, square(-122.20, 37.80, 0.04)),
    # a newer study's X overlapping the AE: the 1% reading must win
    feature('X', False, square(-122.30, 37.80, 0.01)),
]


def test_each_kind_of_point_is_classified_and_absence_is_unknown_not_safe():
    polys, cells = bf.zone_index(FEATURES)
    assert bf.classify(-122.28, 37.835, polys, cells) == 'sfha'      # in the AE, outside its hole
    assert bf.classify(-122.285, 37.815, polys, cells) == 'outside'  # in the hole: the island's X, not the AE
    assert bf.classify(-122.24, 37.82, polys, cells) == 'outside'    # in the X
    assert bf.classify(-122.18, 37.82, polys, cells) == 'unknown'    # zone D
    assert bf.classify(-122.10, 37.82, polys, cells) == 'unknown'    # in no polygon at all
    assert bf.classify(-122.295, 37.805, polys, cells) == 'sfha'     # AE under an overlapping X


def test_the_check_reds_a_mostly_unknown_city_and_a_share_that_is_not_its_counts():
    want = [{'geoid': '0600001', 'name': 'A'}, {'geoid': '0600002', 'name': 'B'}]
    ok = {'cities': [
        {'geoid': '0600001', 'name': 'A', 'residents': 1000, 'residents_sfha': 50, 'residents_unknown': 0,
         'sfha_pct': 5.0},
        {'geoid': '0600002', 'name': 'B', 'residents': 1000, 'residents_sfha': 0, 'residents_unknown': 20,
         'sfha_pct': 0.0},
    ]}
    assert bf.problems(ok, want) == []
    ok['cities'][1]['residents_unknown'] = 400
    ok['cities'][1]['sfha_pct'] = 0.0
    assert any('no determined zone' in p for p in bf.problems(ok, want))
    ok['cities'][1]['residents_unknown'] = 20
    ok['cities'][0]['sfha_pct'] = 0.5
    assert any('not its counts' in p for p in bf.problems(ok, want))
