"""Tests for scripts/fetch_fema_flood.py, the Bay Area flood-zone fetcher that runs on a US runner.

FEMA cannot be reached from this machine, so the fetcher's guards are tested here against a stubbed
service: the box follows the place file, the layer is found by NAME on either documented path, an
empty answer FAILS rather than reading as "no flood", and a short chunk fails as a truncated set.
Offline only.
"""

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location('fetch_fema_flood', REPO_ROOT / 'scripts' / 'fetch_fema_flood.py')
ff = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ff)


def test_the_box_is_derived_from_cities_and_towns_only():
    doc = {'places': [
        {'kind': 'city', 'rings': [[[-122.5, 37.7], [-122.4, 37.8]]]},
        {'kind': 'town', 'rings': [[[-122.0, 37.3], [-121.9, 37.4]]]},
        {'kind': 'cdp', 'rings': [[[-125.0, 30.0], [-124.0, 31.0]]]},  # not scored: must not widen the box
    ]}
    m = ff.MARGIN_DEG
    assert ff.city_box(doc) == [-122.5 - m, 37.3 - m, -121.9 + m, 37.8 + m]


def test_the_real_place_file_gives_a_bay_area_box():
    import json
    xmin, ymin, xmax, ymax = ff.city_box(json.loads(ff.PLACES.read_text(encoding='utf-8')))
    assert -123.2 < xmin < xmax < -121.3 and 36.8 < ymin < ymax < 38.1


def test_the_layer_is_found_by_name_and_the_second_path_is_tried():
    def get(url, params, tries=4):
        if url == ff.SERVICES[0]:
            raise SystemExit('connection reset')
        return {'layers': [{'id': 3, 'name': 'LOMRs'}, {'id': 28, 'name': 'Flood Hazard Zones'}]}
    assert ff.find_layer(get) == (ff.SERVICES[1], 28, 'Flood Hazard Zones')


def test_no_flood_layer_anywhere_fails():
    with pytest.raises(SystemExit, match='no FEMA NFHL service'):
        ff.find_layer(lambda url, params, tries=4: {'layers': [{'id': 1, 'name': 'Something Else'}]})


def test_an_empty_answer_is_a_failed_fetch_not_no_flood():
    with pytest.raises(SystemExit, match='not "no flood"'):
        ff.object_ids('L', [0, 0, 1, 1], lambda url, params, tries=4: {'objectIds': None})


def test_tiles_cover_the_box_without_gaps():
    box = [-122.6, 37.2, -121.9, 37.75]
    ts = ff.tiles(box, 0.25)
    assert min(t[0] for t in ts) == box[0] and max(t[2] for t in ts) == box[2]
    assert min(t[1] for t in ts) == box[1] and max(t[3] for t in ts) == box[3]
    assert all(t[2] - t[0] <= 0.25 + 1e-9 and t[3] - t[1] <= 0.25 + 1e-9 for t in ts)
    area = sum((t[2] - t[0]) * (t[3] - t[1]) for t in ts)
    assert area == pytest.approx((box[2] - box[0]) * (box[3] - box[1]))


def test_a_refused_tile_is_split_and_its_ids_are_unioned():
    # The 17 Oct run: FEMA refused the whole box ("Failed to execute query"). Here any tile wider
    # than 0.1 degrees is refused, so every 0.25 tile must split until it is answered.
    def get(url, params, tries=4):
        x0, y0, x1, y1 = map(float, params['geometry'].split(','))
        if x1 - x0 > 0.1:
            raise ff.ServiceError('Failed to execute query')
        return {'objectIds': [int(x0 * 1000), 7]}  # 7 appears in every tile: the union must dedupe
    ids = ff.object_ids('L', [0.0, 0.0, 0.5, 0.25], get)
    assert 7 in ids and len(ids) == len(set(ids))
    assert len(ids) > 2


def test_a_tile_refused_at_the_smallest_size_fails_naming_it():
    def get(url, params, tries=4):
        raise ff.ServiceError('Failed to execute query')
    with pytest.raises(SystemExit, match='refused even at'):
        ff.object_ids('L', [0.0, 0.0, 0.25, 0.25], get)


def test_features_are_fetched_in_chunks_and_a_short_chunk_fails():
    ids = list(range(ff.CHUNK + 5))
    calls = []

    def get(url, params, tries=4):
        chunk = params['objectIds'].split(',')
        calls.append(len(chunk))
        return {'features': [{'attributes': {'FLD_ZONE': 'AE'}, 'geometry': {'rings': []}} for _ in chunk]}
    assert len(ff.features('L', ids, get)) == len(ids)
    assert calls == [ff.CHUNK, 5]

    def short(url, params, tries=4):
        return {'features': [{'attributes': {}}]}
    with pytest.raises(SystemExit, match='truncated'):
        ff.features('L', ids, short)
