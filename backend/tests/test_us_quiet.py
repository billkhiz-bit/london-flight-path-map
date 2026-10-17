"""US aircraft geometry: usage-weighted runway lobes (2026-10-16).

scripts/measure_us_quiet_yardstick.py --check holds the fitted values to the
airports' noise monitors: SFO's and San Jose's for the Bay Area, the Port
Authority's for New York. These tests hold the SHAPE of the change: that the Bay
Area is reachable by no endpoint yet, that New York scores from its fit, that no
UK city carries the new geometry fields (so no UK score can move), and what
runway_lobe_km means.
"""

import math
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambdas', 'score'))
import app  # noqa: E402

US_ONLY_KEYS = {'runway_lobes', 'airport_sizes', 'corridor_weight', 'major_airports'}
FITTED_US_CITIES = ('bayarea', 'nyc')


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

    def test_no_uk_city_carries_the_us_fields(self):
        # calc_postcode_quiet reads each US field only when present, so this is
        # what guarantees every UK quiet value is unchanged. New York joined the
        # fitted cities on 2026-10-16 (Bill's ruling), on purpose.
        for city, geo in app.CITY_GEOMETRY.items():
            if city in FITTED_US_CITIES:
                continue
            self.assertFalse(US_ONLY_KEYS & set(geo), f'{city} carries {US_ONLY_KEYS & set(geo)}')

    def test_the_fitted_cities_carry_all_of_them(self):
        for city in FITTED_US_CITIES:
            with self.subTest(city=city):
                geo = app.CITY_GEOMETRY[city]
                self.assertEqual(US_ONLY_KEYS - set(geo), set())
                self.assertEqual(set(geo['major_airports']), {ap['code'] for ap in geo['airports']})
                self.assertIsNone(geo['major_airport'])
                self.assertIsNone(geo.get('secondary_airport'))
                self.assertTrue(geo['paths'], 'no routes: the fit kept no lobe')
                kinds = {p['kind'] for p in geo['paths']}
                self.assertLessEqual(kinds, {'final', 'departure'}, 'arrival routes are not scored')

    def test_new_york_scores_from_its_fit(self):
        # Served: a New York point near JFK must read the fitted geometry, so
        # changing JFK's fitted size moves calc_postcode_quiet. The point is FOUND,
        # not borrowed: Howard Beach was the subject until v5.7, when the refit put it
        # at 0.0 (the floor) whichever size JFK had, and the test could show nothing.
        # So step east of JFK (between its lobes, clear of LaGuardia) to the first
        # point that is at neither limit.
        self.assertIn('nyc', app.CITIES)
        jfk = next(a for a in app.CITY_GEOMETRY['nyc']['airports'] if a['code'] == 'JFK')
        sizes = app.CITY_GEOMETRY['nyc']['airport_sizes']
        for km in range(2, 31):
            lat, lon = offset(jfk['lat'], jfk['lon'], 90, km)
            fitted = app.calc_postcode_quiet(lat, lon, 'nyc', raster_lden=None)
            if 0.0 < fitted < 10.0:
                break
        else:
            self.fail('no point east of JFK reads between the limits')
        saved = sizes['JFK']
        try:
            sizes['JFK'] = saved / 2
            smaller = app.calc_postcode_quiet(lat, lon, 'nyc', raster_lden=None)
        finally:
            sizes['JFK'] = saved
        self.assertGreater(smaller, fitted, 'halving JFK did not make Howard Beach quieter')

    def test_us_sizes_stay_out_of_the_site_mirrored_table(self):
        # AIRPORT_NOISE_SCALE mirrors index.html; the US sizes live in the city.
        for city in FITTED_US_CITIES:
            for code in app.CITY_GEOMETRY[city]['airport_sizes']:
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

    def test_a_lobe_ends_at_its_length(self):
        # v5.7 (2026-10-17): a lobe is a SEGMENT, not an endless half-line. The Jan-Jul
        # runway count added JFK's 31L departures, whose straight line points at Lower
        # Manhattan 19 km out; endless, it read 10002-10038 3-4 points louder where US
        # DOT's 2022 map paints nothing, though the FAA's coded climb-out turns away.
        L, K = app.RUNWAY_LOBE_KM, app.AIRPORT_SHAPE_K
        inside = offset(self.AP['lat'], self.AP['lon'], 300, L - 1.0)
        d_in = app.haversine_km(*inside, self.AP['lat'], self.AP['lon'])
        self.assertAlmostEqual(app.runway_lobe_km(*inside, self.AP, [{'bearing': 300.0}]), d_in, delta=0.01)
        beyond = offset(self.AP['lat'], self.AP['lon'], 300, L + 4.0)
        d_out = app.haversine_km(*beyond, self.AP['lat'], self.AP['lon'])
        self.assertAlmostEqual(app.runway_lobe_km(*beyond, self.AP, [{'bearing': 300.0}]),
                               L + K * (d_out - L), delta=0.05)

    def test_the_lobe_end_is_continuous(self):
        # No ring on the map where the lobe stops: just inside and just past its end agree.
        L = app.RUNWAY_LOBE_KM
        a = offset(self.AP['lat'], self.AP['lon'], 300, L - 0.001)
        b = offset(self.AP['lat'], self.AP['lon'], 300, L + 0.001)
        lobes = [{'bearing': 300.0}]
        self.assertLess(abs(app.runway_lobe_km(*a, self.AP, lobes) - app.runway_lobe_km(*b, self.AP, lobes)), 0.01)

    def test_the_site_mirrors_the_lobe_length(self):
        # index.html's runwayLobeKm mirrors runway_lobe_km term for term; the length is
        # the term most easily changed on one side only.
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'index.html')
        src = open(os.path.abspath(path), encoding='utf-8').read()
        m = re.search(r'const RUNWAY_LOBE_KM = ([\d.]+);', src)
        self.assertIsNotNone(m, 'RUNWAY_LOBE_KM missing from index.html')
        self.assertEqual(float(m.group(1)), app.RUNWAY_LOBE_KM)
        body = src[src.index('function runwayLobeKm('):]
        body = body[:body.index('\n      }\n')]
        self.assertIn('RUNWAY_LOBE_KM', body, 'runwayLobeKm does not read RUNWAY_LOBE_KM')

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


class UsRouteProvenanceTests(unittest.TestCase):
    """A city scored from the fitted US geometry credits the FAA and adsb.lol; no other does.

    The FAA supplies its procedures "as is" and the runway counts are an ODbL produced
    work, and terms.html obliges integrators to carry `sources` through to their users.
    The expected period is read from data/us-runway-use.json, the file the fit reads,
    not from the engine's own block.
    """

    USE = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'us-runway-use.json')

    def test_only_fitted_us_cities_credit_the_faa_and_adsb_lol(self):
        import json  # noqa: PLC0415
        with open(self.USE, encoding='utf-8') as fh:
            use = json.load(fh)['airports']
        for city in app.CITY_PROVENANCE:
            for tier in (None, 'postcode', 'raster', 'borough'):
                src = app.build_sources(city, quiet_source=tier)
                faa = [s for s in src if 'FAA Coded Instrument Flight Procedures' in s]
                adsb = [s for s in src if 'adsb.lol' in s]
                with self.subTest(city=city, tier=tier):
                    if city in FITTED_US_CITIES:
                        self.assertEqual(len(faa), 1, src)
                        self.assertIn('"as is", without warranty', faa[0])
                        self.assertEqual(len(adsb), 1, src)
                        self.assertIn('ODbL', adsb[0])
                        codes = {ap['code'] for ap in app.CITY_GEOMETRY[city]['airports']}
                        periods = {use[c]['period'].split(', ', 1)[-1] for c in codes}
                        self.assertEqual(len(periods), 1, periods)
                        self.assertIn(periods.pop(), adsb[0])
                    else:
                        self.assertEqual(faa + adsb, [], f'{city} credits US data it does not use')
