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


def _cache_stand_in(tmp_path, monkeypatch):
    """A repo-shaped stand-in: two counties' files, the frame, the county list and the anchor."""
    import types
    (tmp_path / 'scripts').mkdir()
    counties = [('Alameda', '06001'), ('Alpine', '06003')]
    state_dir = tmp_path / 'counties'
    state_dir.mkdir()
    for _, fips in counties:
        (state_dir / f'{fips}.esrijson.gz').write_bytes(b'gz ' + fips.encode())
        (state_dir / f'{fips}.json').write_text('{}', encoding='utf-8')
    # the loads as the real scripts make them: one direct, one only through another script
    scripts = {
        'build_bayarea_flood.py': "inside = _load('build_bay_area_page').inside\nb = _load('bayarea_blocks')\n",
        'bayarea_blocks.py': '# reads the Census frame\n',
        'build_bay_area_page.py': "q = _load('fetch_helper')\n",
        'fetch_helper.py': '# loaded only by build_bay_area_page\n',
        'unrelated.py': '# loaded by nothing the re-measure runs\n',
    }
    for name, body in scripts.items():
        (tmp_path / 'scripts' / name).write_text(body, encoding='utf-8')
    paths = {'pl': tmp_path / 'pl.zip', 'ca': tmp_path / 'ca.json', 'out': tmp_path / 'state.json'}
    for p in paths.values():
        p.write_text(p.name, encoding='utf-8')
    monkeypatch.setattr(bf, 'REPO', tmp_path)
    monkeypatch.setattr(bf, 'STATE_DIR', state_dir)
    monkeypatch.setattr(bf, 'STATE_OUT', paths['out'])
    monkeypatch.setattr(bf, 'STATE_CACHE', tmp_path / '.state-check-cache.json')
    blocks = types.SimpleNamespace(PL_RAW=paths['pl'])
    fetcher = types.SimpleNamespace(CA_COUNTIES=paths['ca'])
    return counties, blocks, fetcher, state_dir, paths


def test_the_anchor_cache_vouches_only_for_the_same_bytes(tmp_path, monkeypatch):
    counties, blocks, fetcher, state_dir, paths = _cache_stand_in(tmp_path, monkeypatch)
    key = bf.state_check_key(blocks, counties, fetcher)
    assert bf.state_check_cached(key) is None  # no cache yet
    bf.save_state_check(key)
    assert bf.state_check_cached(key) is not None
    # any input or the code changing gives a new key, which the cache does not hold
    scripts = tmp_path / 'scripts'
    for path in (state_dir / '06003.esrijson.gz', state_dir / '06001.json', paths['pl'], paths['ca'], paths['out'],
                 scripts / 'build_bayarea_flood.py', scripts / 'bayarea_blocks.py', scripts / 'build_bay_area_page.py',
                 scripts / 'fetch_helper.py'):
        before = path.read_bytes()
        path.write_bytes(before + b' changed')
        moved = bf.state_check_key(blocks, counties, fetcher)
        assert moved != key, path.name
        assert bf.state_check_cached(moved) is None, path.name
        path.write_bytes(before)
    assert bf.state_check_key(blocks, counties, fetcher) == key
    # a script nothing loads is not the re-measure's code, so it does not spend the cache
    (scripts / 'unrelated.py').write_text('# edited\n', encoding='utf-8')
    assert bf.state_check_key(blocks, counties, fetcher) == key


def test_the_key_follows_the_real_scripts_loads():
    names = {p.name for p in bf.script_closure()}
    # inside() classifies every block; fetch_fema_flood is loaded only through the county fetcher
    assert {'build_bayarea_flood.py', 'build_bay_area_page.py', 'bayarea_blocks.py', 'fetch_fema_nfhl_counties.py',
            'fetch_fema_flood.py'} <= names


@pytest.mark.parametrize('cache', [
    'not json',
    '{"at": 1}',                      # no key
    '{"key": "k", "at": "yesterday"}',  # an unreadable time
    '[]',                             # the wrong shape
])
def test_an_unreadable_anchor_cache_re_measures(tmp_path, monkeypatch, cache):
    monkeypatch.setattr(bf, 'STATE_CACHE', tmp_path / 'cache.json')
    bf.STATE_CACHE.write_text(cache, encoding='utf-8')
    assert bf.state_check_cached('k') is None


def test_an_anchor_cache_older_than_a_week_re_measures(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(bf, 'STATE_CACHE', tmp_path / 'cache.json')
    now = bf.time.time()
    bf.STATE_CACHE.write_text(json.dumps({'key': 'k', 'at': now - 6.9 * 86400}), encoding='utf-8')
    assert bf.state_check_cached('k') is not None
    bf.STATE_CACHE.write_text(json.dumps({'key': 'k', 'at': now - 7.1 * 86400}), encoding='utf-8')
    assert bf.state_check_cached('k') is None
    bf.STATE_CACHE.write_text(json.dumps({'key': 'k', 'at': now + 86400}), encoding='utf-8')  # from the future
    assert bf.state_check_cached('k') is None
