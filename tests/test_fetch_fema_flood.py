"""Tests for scripts/fetch_fema_flood.py, the Bay Area flood-zone fetcher that runs on a US runner.

FEMA cannot be reached from this machine, so the fetcher's guards are tested here against a stubbed
service: the box follows the place file, the layer is found by NAME on either documented path, an
empty answer FAILS rather than reading as "no flood", a short chunk fails as a truncated set, and
both ways FEMA refuses a heavy query (an error body, seen in run 39066895696, and a dropped
connection, seen in run 39069350042) split the tile or chunk instead of ending the run.
Offline only.
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('fetch_fema_flood', REPO_ROOT / 'scripts' / 'fetch_fema_flood.py')
ff = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ff)


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(ff, 'PAUSE_S', 0)


def test_the_box_is_derived_from_cities_and_towns_only():
    doc = {'places': [
        {'kind': 'city', 'rings': [[[-122.5, 37.7], [-122.4, 37.8]]]},
        {'kind': 'town', 'rings': [[[-122.0, 37.3], [-121.9, 37.4]]]},
        {'kind': 'cdp', 'rings': [[[-125.0, 30.0], [-124.0, 31.0]]]},  # not scored: must not widen the box
    ]}
    m = ff.MARGIN_DEG
    assert ff.city_box(doc) == [-122.5 - m, 37.3 - m, -121.9 + m, 37.8 + m]


def test_the_real_place_file_gives_a_bay_area_box():
    xmin, ymin, xmax, ymax = ff.city_box(json.loads(ff.PLACES.read_text(encoding='utf-8')))
    assert -123.2 < xmin < xmax < -121.3 and 36.8 < ymin < ymax < 38.1


def test_the_layer_is_found_by_name_and_the_second_path_is_tried():
    def get(url, params, tries=ff.TRIES):
        if url == ff.SERVICES[0]:
            raise ff.NetworkError('connection reset')
        return {'layers': [{'id': 3, 'name': 'LOMRs'}, {'id': 28, 'name': 'Flood Hazard Zones'}]}
    assert ff.find_layer(get) == (ff.SERVICES[1], 28, 'Flood Hazard Zones')


def test_no_flood_layer_anywhere_fails():
    with pytest.raises(SystemExit, match='no FEMA NFHL service'):
        ff.find_layer(lambda url, params, tries=ff.TRIES: {'layers': [{'id': 1, 'name': 'Something Else'}]})


def test_an_empty_answer_is_a_failed_fetch_not_no_flood():
    with pytest.raises(SystemExit, match='not "no flood"'):
        ff.object_ids('L', [0, 0, 1, 1], lambda url, params, tries=ff.TRIES: {'objectIds': None})


def test_tiles_cover_the_box_without_gaps():
    box = [-122.6, 37.2, -121.9, 37.75]
    ts = ff.tiles(box, 0.25)
    assert min(t[0] for t in ts) == box[0] and max(t[2] for t in ts) == box[2]
    assert min(t[1] for t in ts) == box[1] and max(t[3] for t in ts) == box[3]
    assert all(t[2] - t[0] <= 0.25 + 1e-9 and t[3] - t[1] <= 0.25 + 1e-9 for t in ts)
    area = sum((t[2] - t[0]) * (t[3] - t[1]) for t in ts)
    assert area == pytest.approx((box[2] - box[0]) * (box[3] - box[1]))


@pytest.mark.parametrize('refusal', [ff.ServiceError('Failed to execute query'), ff.NetworkError('reset by peer')])
def test_a_refused_tile_is_split_and_its_ids_are_unioned(refusal):
    # Any tile wider than 0.06 degrees is refused, in either of FEMA's two ways, so every first
    # tile must split before it is answered.
    def get(url, params, tries=ff.TRIES):
        x0, y0, x1, y1 = map(float, params['geometry'].split(','))
        if x1 - x0 > 0.06:
            raise refusal
        return {'objectIds': [round(x0 * 1000), 7]}  # 7 is in every tile: the union must dedupe
    ids = ff.object_ids('L', [0.0, 0.0, 0.3, 0.2], get)
    assert 7 in ids and len(ids) == len(set(ids)) and len(ids) > 2


def test_a_tile_refused_at_the_smallest_size_fails_naming_it():
    def get(url, params, tries=ff.TRIES):
        raise ff.NetworkError('reset by peer')
    with pytest.raises(SystemExit, match='refused even at'):
        ff.object_ids('L', [0.0, 0.0, 0.25, 0.25], get)


def feature(_):
    return {'attributes': {'FLD_ZONE': 'AE'}, 'geometry': {'rings': []}}


def test_features_are_fetched_in_chunks_and_a_short_chunk_fails():
    ids = list(range(ff.CHUNK + 5))
    calls = []

    def get(url, params, tries=ff.TRIES):
        chunk = params['objectIds'].split(',')
        calls.append(len(chunk))
        return {'features': [feature(i) for i in chunk]}
    assert len(ff.features('L', ids, ff.Ledger(), get)) == len(ids)
    assert calls == [ff.CHUNK, 5]

    def short(url, params, tries=ff.TRIES):
        return {'features': [feature(0)]}
    with pytest.raises(SystemExit, match='truncated'):
        ff.features('L', ids, ff.Ledger(), short)


def test_a_refused_chunk_is_halved_until_answered():
    sizes = []

    def get(url, params, tries=ff.TRIES):
        chunk = params['objectIds'].split(',')
        if len(chunk) > 10:
            raise ff.NetworkError('reset by peer')
        sizes.append(len(chunk))
        return {'features': [feature(i) for i in chunk]}
    ids = list(range(ff.CHUNK))
    assert len(ff.features('L', ids, ff.Ledger(), get)) == len(ids)
    assert max(sizes) <= 10 and sum(sizes) == len(ids)


def test_a_feature_refused_at_every_tolerance_is_left_out_and_recorded_with_what_fema_will_say():
    # Run 39134615637: feature 352386 refused even at 20 m. FEMA still answers for its attributes and extent.
    def get(url, params, tries=ff.TRIES):
        if params.get('returnGeometry') == 'false':
            return {'features': [{'attributes': {'FLD_ZONE': 'AE', 'SFHA_TF': 'T'}}]}
        if params.get('returnExtentOnly') == 'true':
            return {'extent': {'xmin': -122.4, 'ymin': 37.4, 'xmax': -122.1, 'ymax': 37.6}}
        chunk = params['objectIds'].split(',')
        if '41' in chunk:
            raise ff.ServiceError('Failed to execute query')
        return {'features': [feature(i) for i in chunk]}
    ledger = ff.Ledger(near=[[-122.5, 37.3, -122.0, 37.8]])
    got = ff.features('L', [40, 41, 42], ledger, get)
    assert len(got) == 2
    assert set(ledger.refused) == {41} and not ledger.outside
    assert ledger.refused[41]['attributes'] == {'FLD_ZONE': 'AE', 'SFHA_TF': 'T'}
    assert ledger.refused[41]['extent']['xmin'] == -122.4


def test_more_refusals_than_the_cap_fail_the_run_as_systemic():
    def get(url, params, tries=ff.TRIES):
        raise ff.ServiceError('Failed to execute query')
    with pytest.raises(SystemExit, match='systemic'):
        ff.features('L', list(range(ff.MAX_REFUSED + 1)), ff.Ledger(), get)


def test_a_heavy_feature_is_fetched_simplified_and_the_tolerance_that_worked_is_recorded():
    # Run 39072503762: feature 352386 was refused even alone. Here full detail and the 1 m
    # tolerance are refused and 5 m works, so the record must say 5 m, not the first one tried.
    def get(url, params, tries=ff.TRIES):
        chunk = params['objectIds'].split(',')
        if '41' in chunk and params.get('maxAllowableOffset', 0) < ff.GENERALISE_DEG[1]:
            raise ff.ServiceError('Failed to execute query')
        return {'features': [feature(i) for i in chunk]}
    ledger = ff.Ledger()
    got = ff.features('L', [40, 41, 42], ledger, get)
    assert len(got) == 3
    assert ledger.generalised == {41: ff.GENERALISE_DEG[1]}


def test_refusals_whose_extent_touches_no_city_are_recorded_apart_and_do_not_reach_the_cap():
    # Run 39137323723: 352386-352389 lie in Santa Cruz County, outside every city; FEMA gives only the extent
    def get(url, params, tries=ff.TRIES):
        if params.get('returnExtentOnly') == 'true':
            return {'extent': {'xmin': -122.05, 'ymin': 36.97, 'xmax': -122.02, 'ymax': 37.01}}
        raise ff.ServiceError('Failed to execute query')
    ledger = ff.Ledger(near=[[-122.2, 37.4, -121.8, 37.5]])
    assert ff.features('L', list(range(ff.MAX_REFUSED + 3)), ledger, get) == []
    assert len(ledger.outside) == ff.MAX_REFUSED + 3 and not ledger.refused


def test_only_tiles_that_touch_a_city_are_searched():
    asked = []

    def get(url, params, tries=ff.TRIES):
        asked.append([float(v) for v in params['geometry'].split(',')])
        return {'objectIds': [1]}
    city = [-122.25, 37.35, -122.15, 37.45]
    ff.object_ids('L', [-122.5, 36.9, -121.9, 37.5], get, near=[city])
    assert asked and all(ff.touches(t, city) for t in asked)
    assert len(asked) < len(ff.tiles([-122.5, 36.9, -121.9, 37.5], ff.TILE_DEG))


def test_a_feature_refused_with_every_field_is_fetched_with_only_the_two_the_reader_needs():
    # Run 39142466860: FEMA served an extent but refused the five fields; the geometry was fine
    def get(url, params, tries=ff.TRIES):
        chunk = params['objectIds'].split(',')
        if '41' in chunk and params.get('outFields') != ff.MIN_FIELDS:
            raise ff.ServiceError('Failed to execute query')
        return {'features': [feature(i) for i in chunk]}
    ledger = ff.Ledger()
    assert len(ff.features('L', [40, 41, 42], ledger, get)) == 3
    assert ledger.minimal == {41} and not ledger.generalised and not ledger.refused


def test_a_feature_refused_even_with_two_fields_has_each_field_probed_and_named():
    def get(url, params, tries=ff.TRIES):
        if params.get('returnExtentOnly') == 'true':
            return {'extent': {'xmin': -122.4, 'ymin': 37.6, 'xmax': -122.39, 'ymax': 37.61}}
        if params.get('returnGeometry') == 'false' and params.get('outFields') == 'SFHA_TF':
            return {'features': [{'attributes': {'SFHA_TF': 'T'}}]}
        raise ff.ServiceError('Failed to execute query')
    ledger = ff.Ledger()
    assert ff.features('L', [41], ledger, get) == []
    fields = ledger.refused[41]['fields']
    assert fields['SFHA_TF'] == 'ok' and fields['FLD_ZONE'] == 'refused' and set(fields) == set(ff.FIELDS.split(','))

