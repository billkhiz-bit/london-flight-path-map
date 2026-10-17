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


def test_features_are_fetched_in_chunks_and_a_short_chunk_fails():
    ids = list(range(ff.CHUNK + 5))
    calls = []

    def get(url, params, tries=4):
        chunk = params['objectIds'].split(',')
        calls.append(len(chunk))
        return {'features': [{'properties': {'FLD_ZONE': 'AE'}} for _ in chunk]}
    assert len(ff.features('L', ids, get)) == len(ids)
    assert calls == [ff.CHUNK, 5]

    def short(url, params, tries=4):
        return {'features': [{'properties': {}}]}
    with pytest.raises(SystemExit, match='truncated'):
        ff.features('L', ids, short)
