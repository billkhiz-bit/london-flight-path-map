"""scripts/fetch_healthcare.py: which areas it bundles, and what it refuses to write.

WHY THIS EXISTS (2026-10-27). /nhs bundled Greater London only, so every other
point we score asked Overpass live and, in October, fell back to links 147 times
at Manchester's centre alone. The fetcher now bundles every UK area, its box
DERIVED from the boundary files, and refuses an area whose answer is too small to
be a city: Overpass mirrors have answered "200, zero elements", which would ship
as "no healthcare nearby" (the behaviour of the Lambda is held in
backend/tests/test_handlers.py).
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load():
    if 'fetch_healthcare' in sys.modules:
        return sys.modules['fetch_healthcare']
    spec = importlib.util.spec_from_file_location('fetch_healthcare', REPO / 'scripts' / 'fetch_healthcare.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules['fetch_healthcare'] = mod
    spec.loader.exec_module(mod)
    return mod


fh = _load()


def _boundary(path, ring):
    path.write_text(json.dumps({'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': {}, 'geometry': {'type': 'Polygon', 'coordinates': [ring]}}]}),
        encoding='utf-8')


def test_areas_are_the_uk_boundary_files_widened_by_the_margin(tmp_path):
    _boundary(tmp_path / 'leeds-boroughs.json', [[-1.6, 53.7], [-1.4, 53.7], [-1.4, 53.9], [-1.6, 53.9], [-1.6, 53.7]])
    _boundary(tmp_path / 'nyc-boroughs.json', [[-74.2, 40.5], [-73.7, 40.5], [-73.7, 40.9], [-74.2, 40.9], [-74.2, 40.5]])
    got = fh.areas(tmp_path)
    assert list(got) == ['leeds']  # New York is outside Great Britain: /nhs is UK healthcare
    s, w, n, e = got['leeds']
    assert s == pytest.approx(53.7 - fh.MARGIN_KM / 111, abs=1e-3) and n == pytest.approx(53.9 + fh.MARGIN_KM / 111, abs=1e-3)
    assert w < -1.6 and e > -1.4


def test_the_real_areas_include_every_uk_city_and_reproduce_londons_old_box():
    got = fh.areas()
    assert {'london', 'manchester', 'cardiff', 'norwich', 'nottingham'} <= set(got) and 'nyc' not in got
    # The box this script typed by hand until 2026-10-27; the derived one must agree to within 0.03 degrees.
    assert got['london'] == pytest.approx((51.25, -0.55, 51.72, 0.35), abs=0.03)


def _element(i, amenity='pharmacy', name='Boots'):
    return {'type': 'node', 'lat': 53.0 + i / 1000, 'lon': -2.0, 'tags': {'amenity': amenity, 'name': f'{name} {i}'}}


def test_an_empty_success_is_refused_and_nothing_is_written(tmp_path):
    boxes = {'big': (53, -3, 54, -2), 'empty': (52, -3, 53, -2)}
    answers = {'big': {'elements': [_element(i) for i in range(fh.MIN_NAMED)]}, 'empty': {'elements': []}}
    with pytest.raises(SystemExit, match='empty: 0 named services'):
        fh.build(answers, boxes)


def test_rows_keep_named_services_only_in_a_stable_order():
    els = [_element(2), _element(1), {'type': 'node', 'lat': 53, 'lon': -2, 'tags': {'amenity': 'pharmacy'}},
           _element(3, amenity='dentist'),
           {'type': 'way', 'center': {'lat': 53.5, 'lon': -2.1}, 'tags': {'amenity': 'hospital', 'name': 'Royal'}}]
    rows = fh.rows_of(els)
    assert [(r['a'], r['n']) for r in rows] == [('hospital', 'Royal'), ('pharmacy', 'Boots 1'), ('pharmacy', 'Boots 2')]
    assert fh.rows_of(list(reversed(els))) == rows
