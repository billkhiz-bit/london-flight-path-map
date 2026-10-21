"""Tests for scripts/build_bayarea_flood.py, the Bay Area's flood input (release 2).

FEMA's file arrives from a US runner, so the reader is tested on stand-in polygons: a point in the 1%
zone counts, a point in a polygon's HOLE does not, zone D and "no polygon at all" are UNKNOWN rather
than safe, overlapping studies take the riskier reading, and the check reds a city whose residents are
mostly unknown and a share that is not its counts. Offline only.
"""

import importlib.util
from pathlib import Path

import pytest

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


def test_the_anchor_is_measured_county_by_county_and_refuses_a_county_left_out():
    # Bill, 2026-10-21: the US flood scale's anchor is California's own share, measured over every county.
    by_county = {'06001': [feature('AE', True, square(-122.30, 37.80, 0.04)),
                           feature('X', False, square(-122.20, 37.80, 0.04))],
                 '06003': [feature('D', False, square(-120.00, 38.60, 0.04))]}
    read = by_county.__getitem__
    points = {'06001': [(-122.28, 37.82, 30, '0600100'), (-122.18, 37.82, 970, '0600100')],  # a town: 3% in the 1%
              '06003': [(-119.98, 38.62, 900, '06003 rest')]}                              # all undetermined
    counties = [('Alameda', '06001'), ('Alpine', '06003')]
    total, per, units = bf.state_tally(counties, points, read)
    assert total == {'sfha': 30, 'outside': 970, 'unknown': 900}
    assert units == {'0600100': {'sfha': 30, 'outside': 970, 'unknown': 0},
                     '06003 rest': {'sfha': 0, 'outside': 0, 'unknown': 900}}
    doc = bf.state_doc(total, per, units, {'06001': 'a', '06003': 'b'})
    assert (doc['sfha_pct'], doc['residents_counted'], doc['units_counted']) == (3.0, 1000, 1)
    assert doc['residents'] == 1900  # the undetermined are counted, never hidden
    assert bf.state_problems(doc, counties) == []
    with pytest.raises(SystemExit, match='06003'):
        bf.state_tally(counties[:1], points, read)  # a county with residents left out of the list


def test_a_mostly_undetermined_place_adds_nothing_to_the_anchor():
    # Code review, 2026-10-21: pooled, a withheld city's determined residents (the creek-biased few FEMA studied)
    # inflated the anchor: the Bay Area read 4.39% where the 41 cities with a share read 2.85%.
    units = {'town': {'sfha': 20, 'outside': 980, 'unknown': 0},       # 2%, fully determined
             'valley': {'sfha': 200, 'outside': 50, 'unknown': 750}}   # 75% zone D; 80% of the rest in the 1%
    doc = bf.state_doc({'sfha': 220, 'outside': 1030, 'unknown': 750}, [], units, {})
    assert doc['sfha_pct'] == 2.0 and doc['units_counted'] == 1
    assert doc['sfha_pct_all_determined'] == 17.6  # what pooling would have said: kept for comparison only


def test_the_anchor_check_reds_a_share_not_its_units_and_an_anchor_on_under_half_the_state():
    counties = [('Alameda', '06001')]
    per = [{'county': 'Alameda', 'fips': '06001', 'residents': 2000, 'residents_sfha': 230, 'residents_unknown': 750}]
    units = {'town': {'sfha': 30, 'outside': 970, 'unknown': 0}, 'valley': {'sfha': 200, 'outside': 50, 'unknown': 750}}
    doc = bf.state_doc({'sfha': 230, 'outside': 1020, 'unknown': 750}, per, units, {})
    assert bf.state_problems(doc, counties) == []
    doc['sfha_pct'] = doc['sfha_pct_all_determined']  # the pooled figure passed off as the anchor
    assert any('not its counted units' in p for p in bf.state_problems(doc, counties))
    doc = bf.state_doc({'sfha': 230, 'outside': 1020, 'unknown': 750}, per,
                       {'town': {'sfha': 3, 'outside': 97, 'unknown': 0},
                        'valley': {'sfha': 227, 'outside': 923, 'unknown': 750}}, {})
    assert any('under half of California' in p for p in bf.state_problems(doc, counties))
    assert any('counties, not the' in p for p in bf.state_problems(doc, counties + [('Alpine', '06003')]))
