"""The Bay Area's aircraft geometry: usage-weighted runway lobes (2026-10-16).

scripts/measure_us_quiet_yardstick.py --check holds the fitted values to SFO's
and San Jose's noise monitors. These tests hold the SHAPE of the change: that it
is reachable by no endpoint yet, that no UK or New York city carries the new
geometry fields (so no published score can move), and what runway_lobe_km means.
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambdas', 'score'))
import app  # noqa: E402

US_ONLY_KEYS = {'runway_lobes', 'airport_sizes', 'corridor_weight', 'major_airports'}


def offset(lat, lon, bearing_deg, km):
    """A point km away on a bearing (flat-earth, accurate enough at these distances)."""
    b = math.radians(bearing_deg)
    dlat = km * math.cos(b) / 111.195
    dlon = km * math.sin(b) / (111.195 * math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon


class BayAreaGeometryTests(unittest.TestCase):
    def test_the_bay_area_is_not_served_yet(self):
        # Release 2 wires 'bayarea' into CITIES. Until then the geometry must be
        # inert: no endpoint can reach calc_postcode_quiet with it. When release 2
        # lands, this assertion is changed on purpose, not discovered.
        self.assertIn('bayarea', app.CITY_GEOMETRY)
        self.assertNotIn('bayarea', app.CITIES)

    def test_no_uk_or_new_york_city_carries_the_us_fields(self):
        # calc_postcode_quiet reads each US field only when present, so this is
        # what guarantees every UK and New York quiet value is unchanged.
        for city, geo in app.CITY_GEOMETRY.items():
            if city == 'bayarea':
                continue
            self.assertFalse(US_ONLY_KEYS & set(geo), f'{city} carries {US_ONLY_KEYS & set(geo)}')

    def test_the_bay_area_carries_all_of_them(self):
        geo = app.CITY_GEOMETRY['bayarea']
        self.assertEqual(US_ONLY_KEYS - set(geo), set())
        self.assertEqual(set(geo['major_airports']), {ap['code'] for ap in geo['airports']})
        self.assertIsNone(geo['major_airport'])
        self.assertTrue(geo['paths'], 'no routes: the fit kept no lobe')
        kinds = {p['kind'] for p in geo['paths']}
        self.assertLessEqual(kinds, {'final', 'departure'}, 'arrival routes are not scored')

    def test_us_sizes_stay_out_of_the_site_mirrored_table(self):
        # AIRPORT_NOISE_SCALE mirrors index.html; the US sizes live in the city.
        for code in app.CITY_GEOMETRY['bayarea']['airport_sizes']:
            self.assertNotIn(code, app.AIRPORT_NOISE_SCALE)


class RunwayLobeTests(unittest.TestCase):
    AP = {'code': 'TST', 'lat': 37.5, 'lon': -122.2}

    def test_no_lobes_is_a_circle(self):
        lat, lon = offset(self.AP['lat'], self.AP['lon'], 77, 4.0)
        self.assertAlmostEqual(app.runway_lobe_km(lat, lon, self.AP, []),
                               app.haversine_km(lat, lon, self.AP['lat'], self.AP['lon']), places=9)

    def test_on_the_lobe_is_the_plain_distance(self):
        lat, lon = offset(self.AP['lat'], self.AP['lon'], 300, 5.0)
        d = app.haversine_km(lat, lon, self.AP['lat'], self.AP['lon'])
        self.assertAlmostEqual(app.runway_lobe_km(lat, lon, self.AP, [{'bearing': 300.0}]), d, delta=0.01)

    def test_behind_the_lobe_is_off_the_strip(self):
        # A runway end that is only ever flown one way: the far side is quiet.
        lat, lon = offset(self.AP['lat'], self.AP['lon'], 120, 5.0)
        d = app.haversine_km(lat, lon, self.AP['lat'], self.AP['lon'])
        self.assertAlmostEqual(app.runway_lobe_km(lat, lon, self.AP, [{'bearing': 300.0}]),
                               app.AIRPORT_SHAPE_K * d, places=9)

    def test_the_nearest_flown_lobe_wins(self):
        lat, lon = offset(self.AP['lat'], self.AP['lon'], 120, 5.0)
        d = app.haversine_km(lat, lon, self.AP['lat'], self.AP['lon'])
        both = app.runway_lobe_km(lat, lon, self.AP, [{'bearing': 300.0}, {'bearing': 120.0}])
        self.assertAlmostEqual(both, d, delta=0.01)

    def test_two_lobes_reproduce_the_engine_axis(self):
        # Both directions of one runway flown = the v5.5 runway-shaped axis.
        ap = dict(self.AP, code='LHR')
        lobes = [{'bearing': app.RUNWAY_AXIS_DEG['LHR']}, {'bearing': (app.RUNWAY_AXIS_DEG['LHR'] + 180) % 360}]
        for brg in (10, 60, 95, 150, 200, 260, 330):
            lat, lon = offset(ap['lat'], ap['lon'], brg, 6.0)
            self.assertAlmostEqual(app.runway_lobe_km(lat, lon, ap, lobes),
                                   app.airport_distance_km(lat, lon, ap), places=6, msg=brg)


if __name__ == '__main__':
    unittest.main()
