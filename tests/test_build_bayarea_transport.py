"""Tests for scripts/build_bayarea_transport.py, the Bay Area's transport input (release 2; Bill, 2026-10-22).

The Census block frame is gitignored, so the reader is tested on small stand-ins: the share counts residents,
not blocks, within the walk; a band is taken from the published share at each edge; a source-gap city is
withheld, never read as no station; and the check holds the withheld set both ways, the gap against the
transit file's own words, and every share and band against its counts. Offline only.
"""

import copy
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('build_bayarea_transport',
                                              REPO_ROOT / 'scripts' / 'build_bayarea_transport.py')
bt = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bt)

STATION = {'lat': 37.80, 'lon': -122.27}
# 0.005 degrees of latitude is about 557 m (inside the walk); 0.01 about 1,113 m (outside)
NEAR, FAR = 37.805, 37.81
GAP_TEXT = 'Capitol Corridor (Amtrak) is absent from the layer: Emeryville reads no station'


def place(name, geoid):
    return {'name': name, 'geoid': geoid, 'county': 'Alameda', 'kind': 'city'}


def frame():
    return {
        # 300 of 400 residents near, though only one of its two blocks is: residents count, not blocks
        '0600001': [(-122.27, NEAR, 300), (-122.27, FAR, 100)],
        '0600002': [(-122.27, FAR, 50)],
        '0622594': [(-122.27, NEAR, 10)],  # Emeryville: near a station in the stand-in, withheld all the same
    }


def cities():
    return [place('Alpha', '0600001'), place('Beta', '0600002'), place('Emeryville', '0622594')]


def sound_doc():
    return bt.build(frame(), cities(), [STATION])


def test_the_share_counts_residents_within_the_walk():
    rows = {r['name']: r for r in sound_doc()['cities']}
    assert rows['Alpha']['residents_within_walk'] == 300
    assert rows['Alpha']['share_within_walk_pct'] == 75.0
    assert rows['Alpha']['band'] == 'excellent'
    assert rows['Beta']['share_within_walk_pct'] == 0.0
    assert rows['Beta']['band'] == 'poor'


def test_a_source_gap_city_is_withheld_not_read_as_no_station():
    em = {r['name']: r for r in sound_doc()['cities']}['Emeryville']
    assert em['share_within_walk_pct'] is None and em['band'] is None
    assert em['withheld'] == bt.SOURCE_GAP['Emeryville']


@pytest.mark.parametrize('share, band', [
    (50.0, 'excellent'), (49.9, 'good'), (25.0, 'good'), (24.9, 'moderate'),
    (10.0, 'moderate'), (9.9, 'poor'), (0.0, 'poor'),
])
def test_each_band_starts_at_its_edge(share, band):
    assert bt.band_of(share) == band


def test_rounding_down_never_lifts_a_city_into_a_better_band():
    # just under each edge: rounded to NEAREST these would read the better band
    for edge in (50.0, 25.0, 10.0):
        assert bt.band_of(bt.floor1(edge - 0.04)) != bt.band_of(edge)
    assert bt.floor1(62.0) == 62.0 and bt.floor1(0.0) == 0.0


def test_a_negative_share_raises_rather_than_banding():
    with pytest.raises(ValueError):
        bt.band_of(-0.1)


def test_the_sound_stand_in_passes():
    assert bt.problems(sound_doc(), cities(), GAP_TEXT) == []


def _mutated(fn):
    doc = copy.deepcopy(sound_doc())
    fn({r['name']: r for r in doc['cities']}, doc)
    return doc


@pytest.mark.parametrize('mutate, message', [
    # a band that is not its share's
    (lambda rows, doc: rows['Alpha'].update(band='good'), 'is not the band of'),
    # a share that is not its counts
    (lambda rows, doc: rows['Alpha'].update(share_within_walk_pct=70.0), 'is not its counts'),
    # the gap city given a reading, as though BTS's file were whole
    (lambda rows, doc: rows['Emeryville'].update(share_within_walk_pct=0.0, band='poor', withheld=None),
     'is not SOURCE_GAP'),
    # a withheld city that still carries a band, or a count
    (lambda rows, doc: rows['Emeryville'].update(band='poor'), 'withheld, yet carries'),
    (lambda rows, doc: rows['Emeryville'].update(residents_within_walk=0), 'withheld, yet carries'),
    # another city withheld without a declared gap
    (lambda rows, doc: rows['Beta'].update(share_within_walk_pct=None, band=None, residents_within_walk=None,
                                           withheld='no reason'), 'is not SOURCE_GAP'),
    # a city dropped
    (lambda rows, doc: doc['cities'].remove(rows['Beta']), 'exactly the 50 cities'),
    # more residents near than live there
    (lambda rows, doc: rows['Beta'].update(residents_within_walk=51), 'within a walk of'),
])
def test_the_check_reds_each_defect(mutate, message):
    found = bt.problems(_mutated(mutate), cities(), GAP_TEXT)
    assert any(message in f for f in found), found


def test_a_gap_the_transit_file_does_not_name_reds():
    found = bt.problems(sound_doc(), cities(), 'nothing is missing')
    assert any("known_gap does not name" in f for f in found), found


def test_the_real_gap_is_named_in_the_real_transit_file():
    import json
    transit = json.loads((REPO_ROOT / 'data' / 'us-bayarea-transit.json').read_text(encoding='utf-8'))
    assert all(name in transit['known_gap'] for name in bt.SOURCE_GAP)


def test_the_committed_file_passes_its_own_check():
    import json
    doc = json.loads(bt.OUT.read_text(encoding='utf-8'))
    places = json.loads((REPO_ROOT / 'data' / 'us-bayarea-places.json').read_text(encoding='utf-8'))['places']
    want = [p for p in places if p['kind'] in ('city', 'town')]
    transit = json.loads((REPO_ROOT / 'data' / 'us-bayarea-transit.json').read_text(encoding='utf-8'))
    assert bt.problems(doc, want, transit['known_gap']) == []
