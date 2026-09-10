"""Tests for the cell classification in scripts/load_defra_raster.py.

The loader never runs in Lambda or CI, and until 2026-09-10 nothing tested it
at all: its skip decisions were only ever exercised by a multi-hour run against
the live table. `classify_cell` and `assert_lowest_mapped` are pure, and they
hold the one decision this file exists to guard - that in ROAD mode a raw 0 is
a surveyed-quiet reading written as a bound, while in aircraft mode it stays
the anomaly it always was.

Offline only: no AWS, no rasterio, no boto3. Those are lazy-imported inside
run_load, so importing the module at collection time is safe.
"""

import importlib.util
import os
import sys

import numpy as np
import pytest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), os.pardir))
LOADER = os.path.join(REPO_ROOT, 'scripts', 'load_defra_raster.py')


def _load():
    alias = 'load_defra_raster_under_test'
    if alias in sys.modules:
        return sys.modules[alias]
    spec = importlib.util.spec_from_file_location(alias, LOADER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope='module')
def loader():
    return _load()


ROAD = 'roadLdenDb'
AIR = 'ldenDb'
NODATA = -96.0  # what fetch_defra_road_noise.py writes into every city mosaic


class TestClassifyCell:
    def test_road_zero_is_a_bound_not_a_skip(self, loader):
        state, value = loader.classify_cell(0.0, NODATA, ROAD)
        assert state == 'below'
        assert value == loader.ROAD_LOWEST_MAPPED_DB == 40.0

    def test_aircraft_zero_stays_anomalous(self, loader):
        # The aircraft rasters put below-contour ground in nodata, not 0, so a
        # literal 0 there is still an encoding fault - keyed on the attribute.
        assert loader.classify_cell(0.0, None, AIR) == ('anomalous', None)

    def test_nodata_is_nodata_in_both_modes(self, loader):
        assert loader.classify_cell(NODATA, NODATA, ROAD) == ('nodata', None)
        assert loader.classify_cell(NODATA, NODATA, AIR) == ('nodata', None)
        # The float-max sentinel some GeoTIFFs use, with no declared nodata.
        assert loader.classify_cell(3.4e38, None, ROAD) == ('nodata', None)

    def test_nodata_wins_over_zero_when_nodata_is_zero(self, loader):
        # If a raster declared 0 as its nodata, a 0 must NOT become a
        # surveyed-quiet reading. Sentinel check precedes the zero check.
        assert loader.classify_cell(0.0, 0.0, ROAD) == ('nodata', None)

    def test_a_reading_is_passed_through_unchanged(self, loader):
        assert loader.classify_cell(56.3, NODATA, ROAD) == ('reading', 56.3)
        assert loader.classify_cell(40.0, NODATA, ROAD) == ('reading', 40.0)

    def test_out_of_range_positives_are_anomalous(self, loader):
        assert loader.classify_cell(12.0, NODATA, ROAD) == ('anomalous', None)
        assert loader.classify_cell(150.0, NODATA, ROAD) == ('anomalous', None)


class TestAssertLowestMapped:
    def test_accepts_a_raster_that_bottoms_out_at_40(self, loader):
        band = np.array([[NODATA, 0.0, 40.0], [55.5, 0.0, 72.0]], dtype='float32')
        assert loader.assert_lowest_mapped(band, NODATA) == 40.0

    def test_refuses_a_raster_with_a_different_lower_band(self, loader):
        # The bound written for every zero would be false. Proven red: this is
        # the guard, so the wrong number must not load quietly.
        band = np.array([[NODATA, 0.0, 45.0], [55.5, 0.0, 72.0]], dtype='float32')
        with pytest.raises(SystemExit, match='45.00 dB, not 40.00'):
            loader.assert_lowest_mapped(band, NODATA)

    def test_refuses_a_raster_with_no_readings(self, loader):
        band = np.array([[NODATA, 0.0], [0.0, NODATA]], dtype='float32')
        with pytest.raises(SystemExit, match='no positive cells'):
            loader.assert_lowest_mapped(band, NODATA)

    def test_sentinels_do_not_count_as_the_minimum(self, loader):
        # -96 is below 40; it must be excluded before the min is taken, or every
        # raster would "bottom out" at its own nodata value.
        band = np.array([[NODATA, 40.0]], dtype='float32')
        assert loader.assert_lowest_mapped(band, NODATA) == 40.0
