"""A postcode is sampled at ONS's grid reference, never a re-projection (2026-10-11).

`scripts/postcode_grid.py` is the one holder. Measured that day at 21 postcodes:
pyproj's WGS84 -> British National Grid step, with no OSTN15 grid, lands 1.2 to
2.3 m off the grid reference ONS publishes, which is the neighbouring 10 m cell
of a DEFRA raster for about one postcode in five (DE74 2SA: 49.5 dB served
against DEFRA's 51.0 at ONS's reference). These tests hold the helper's three
cases, and the scan at the foot holds every script to it: a new reader that
projects a postcode's lat/long itself fails here, by name.
"""
import importlib.util
import re
import sys
import unittest
from pathlib import Path

from pyproj import Transformer

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / 'scripts'


def _load():
    spec = importlib.util.spec_from_file_location('postcode_grid', SCRIPTS / 'postcode_grid.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules['postcode_grid'] = mod
    spec.loader.exec_module(mod)
    return mod


TO_BNG = Transformer.from_crs('EPSG:4326', 'EPSG:27700', always_xy=True)


class GridRef(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = _load()

    def test_a_british_postcode_is_ons_grid_reference_exactly(self):
        # DE74 2SA as NSPL holds it. The projection of its lat/long is the 2 m
        # error the helper exists to remove, so the two must differ here.
        row = {'pcds': 'DE74 2SA', 'east1m': '445483', 'north1m': '0325654', 'lat': '52.826521', 'long': '-1.326420'}
        self.assertEqual(self.g.grid_ref(row, TO_BNG), (445483.0, 325654.0))
        x, y = TO_BNG.transform(-1.326420, 52.826521)
        self.assertGreater(abs(x - 445483) + abs(y - 325654), 0.5)

    def test_northern_ireland_never_uses_its_irish_grid_reference(self):
        # BT1 1AA: NSPL's (334316, 374675) is IRISH Grid. Read as British it is
        # near Wigan, and a road raster there would publish a Merseyside reading
        # for Belfast. The helper projects the lat/long instead.
        row = {'pcds': 'BT1 1AA', 'east1m': '334316', 'north1m': '0374675', 'lat': '54.602438', 'long': '-5.922291'}
        x, y = self.g.grid_ref(row, TO_BNG)
        self.assertGreater(abs(x - 334316), 100_000)
        self.assertLess(abs(x - 146_200), 1_000)
        self.assertLess(abs(y - 529_600), 1_000)

    def test_a_row_with_no_grid_reference_falls_back_to_its_lat_long(self):
        row = {'pcds': 'SW1A 1AA', 'east1m': '', 'north1m': '', 'lat': '51.501009', 'long': '-0.141588'}
        x, y = self.g.grid_ref(row, TO_BNG)
        self.assertLess(abs(x - 529_090), 100)
        self.assertLess(abs(y - 179_645), 100)

    def test_an_unlocatable_row_is_none_not_a_point(self):
        # NSPL parks the Channel Islands, the Isle of Man and unlocatable
        # postcodes at (99.999999, 0) with no grid reference.
        row = {'pcds': 'GY1 1AA', 'east1m': '', 'north1m': '', 'lat': '99.999999', 'long': '0.000000'}
        self.assertIsNone(self.g.grid_ref(row, TO_BNG))
        self.assertIsNone(self.g.grid_ref({'pcds': 'X', 'lat': '', 'long': ''}, TO_BNG))

    def test_a_header_without_the_grid_columns_stops_the_run(self):
        with self.assertRaises(SystemExit):
            self.g.require_grid_columns(['pcds', 'lat', 'long'], 'nspl.csv')
        self.g.require_grid_columns(['pcds', 'east1m', 'north1m', 'lat', 'long'], 'nspl.csv')


# Scripts that project WGS84 to the British grid for something that is NOT a
# postcode, each with the reason. Any other script that does so must import
# postcode_grid, or explain itself here.
NOT_A_POSTCODE = {
    'audit_flight_paths.py': 'samples DEFRA along flight-path WAYPOINTS, which have no grid reference',
    'fetch_defra_road_noise.py': "builds each city's fetch bbox from its BOUNDARY vertices",
    'measure_aircraft_footprint.py': 'projects borough BOUNDARY geometry',
    'build_aircraft_rasters.py': 'requests WMS renders by bbox; samples no postcode',
    'lidar_building_heights.py': ("projects the council's BOUNDARY and OpenStreetMap building centres (a check); "
                                  "its postcodes come from NSPL's grid reference (adsb_postcode_averages)"),
}
PROJECTS = re.compile(r"from_crs\(\s*'EPSG:4326'\s*,\s*('EPSG:27700'|raster|crs)")


class EveryPostcodeReaderUsesTheHolder(unittest.TestCase):
    def test_no_script_projects_a_postcode_lat_long_itself(self):
        offenders = []
        for path in sorted(SCRIPTS.glob('*.py')):
            if path.name == 'postcode_grid.py' or path.name in NOT_A_POSTCODE:
                continue
            text = path.read_text(encoding='utf-8', errors='replace')
            if PROJECTS.search(text) and 'postcode_grid' not in text:
                offenders.append(path.name)
        self.assertEqual(offenders, [], (
            'these scripts project WGS84 to the British grid without scripts/postcode_grid.py; '
            "sample a postcode at ONS's grid reference (grid_ref), or add the script to "
            'NOT_A_POSTCODE with the reason'))

    def test_the_exemptions_are_still_real(self):
        # An exemption for a script that no longer projects anything is dead
        # config that would wave a future reader through.
        for name in NOT_A_POSTCODE:
            text = (SCRIPTS / name).read_text(encoding='utf-8', errors='replace')
            self.assertTrue(PROJECTS.search(text) or "CRS=EPSG:4326" in text, f'{name} no longer projects; drop its exemption')


if __name__ == '__main__':
    unittest.main()
