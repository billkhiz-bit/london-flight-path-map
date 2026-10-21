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


def test_land_outside_the_study_and_open_water_are_unknown_not_safe():
    # FEMA's first real file (run 39443609009) held both, flagged SFHA_TF 'F': neither is a determination.
    feats = [feature('AREA NOT INCLUDED', False, square(-122.30, 37.80, 0.02)),
             feature('OPEN WATER', False, square(-122.25, 37.80, 0.02)),
             feature('AE', True, square(-122.30, 37.80, 0.005))]  # a study over part of the excluded land
    polys, cells = bf.zone_index(feats)
    assert bf.classify(-122.29, 37.81, polys, cells) == 'unknown'
    assert bf.classify(-122.24, 37.81, polys, cells) == 'unknown'
    assert bf.classify(-122.298, 37.802, polys, cells) == 'sfha'  # a determined 1% reading still wins


def test_a_mostly_undetermined_city_has_no_share_only_the_reason():
    # San Jose, 2026-10-21: 766,952 of 1,013,240 in zone D; 53,189 in the 1% zone, 21.6% of the rest
    assert bf.share(1013240, 53189, 766952) == (
        None, 'FEMA has not determined the flood risk for 76% of residents (zone D or unmapped)')
    assert bf.share(43908, 1702, 855) == (3.95, None)  # San Bruno: 1.9% undetermined, the share stands
    assert bf.share(1000, 0, 1000)[0] is None


def test_the_check_reds_a_share_printed_where_fema_has_not_determined_and_one_not_its_counts():
    want = [{'geoid': '0600001', 'name': 'A'}, {'geoid': '0600002', 'name': 'B'}]
    ok = {'cities': [
        {'geoid': '0600001', 'name': 'A', 'residents': 1000, 'residents_sfha': 50, 'residents_unknown': 0,
         'sfha_pct': 5.0, 'withheld': None},
        {'geoid': '0600002', 'name': 'B', 'residents': 1000, 'residents_sfha': 0, 'residents_unknown': 400,
         'sfha_pct': None, 'withheld': 'FEMA has not determined the flood risk for 40% of residents (zone D or unmapped)'},
    ]}
    assert bf.problems(ok, want) == []
    ok['cities'][1]['sfha_pct'] = 0.0  # a share (and a reassuring one) where FEMA gave none
    assert any('must be withheld' in p for p in bf.problems(ok, want))
    ok['cities'][1]['sfha_pct'] = None
    ok['cities'][0]['sfha_pct'] = 0.5
    assert any('not its counts' in p for p in bf.problems(ok, want))
    ok['cities'][0]['sfha_pct'] = 5.0
    ok['cities'][0]['withheld'] = 'made up'  # a reason where the share stands
    assert any('not its counts' in p for p in bf.problems(ok, want))
