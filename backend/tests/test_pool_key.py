"""The anchor pool key (decision 2 of the Bay Area's release 2, Bill 2026-10-16).

Affordability (v5.0) and growth (v5.2) are anchored on a POOL of cities. Until 2026-10-18 the pool was
the currency, so the Bay Area joining the dollar pool would have moved New York's published scores
(the p95 anchor lands on the "$2M+" top code: Queens 6.5 -> 9.9). Decision 2 gives each US metro its
own pool through a registry key, `CITIES[city]['pool']`, defaulting to the currency.

These tests hold the promise both ways: a city in its OWN pool leaves New York byte-identical in
every persona, and the same city WITHOUT a pool of its own does move New York, so the first test
can fail. Introducing the key itself moved none of the 816 scores (checked with a full before/after
snapshot on 2026-10-18; it also caught a shadowed `pool` variable that emptied the growth pool).
"""

import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambdas', 'score'))

import app  # noqa: E402


def _nyc_scores():
    return json.dumps({f'{b}|{p}': app.calc_score(b, 'nyc', w)
                       for b in sorted(app.CITIES['nyc']['boroughs']) for p, w in sorted(app.PERSONAS.items())},
                      sort_keys=True, default=str)


class PoolKeyTest(unittest.TestCase):
    def setUp(self):
        app._NATIONAL_AFFORD_BOUNDS.clear()
        app._NATIONAL_GROWTH_BOUNDS.clear()
        self.baseline = _nyc_scores()

    def tearDown(self):
        app.CITIES.pop('zz_test_metro', None)
        app._NATIONAL_AFFORD_BOUNDS.clear()
        app._NATIONAL_GROWTH_BOUNDS.clear()

    def _add_metro(self, pool):
        # a dollar city far dearer and faster-rising than any New York borough, so that pooling it
        # with New York must move both anchors
        metro = copy.deepcopy(app.CITIES['nyc'])
        metro['name'] = 'Test metro'
        for bd in metro['boroughs'].values():
            bd['avgPrice'] = bd['avgPrice'] * 4
            bd['trend'] = 40.0
        if pool is not None:
            metro['pool'] = pool
        app.CITIES['zz_test_metro'] = metro
        app._NATIONAL_AFFORD_BOUNDS.clear()
        app._NATIONAL_GROWTH_BOUNDS.clear()

    def test_every_city_pools_by_its_currency_but_the_bay_area(self):
        # The Bay Area is the one city naming its own pool (decision 2, served 2026-10-22); every other city
        # pools by currency, so New York's dollar pool is New York alone. A SET, so a second city naming a
        # pool fails here: update this test and decision 2's notes on purpose.
        named = {city: cfg['pool'] for city, cfg in app.CITIES.items() if 'pool' in cfg}
        self.assertEqual(named, {'bayarea': 'bayarea'})
        for city, cfg in app.CITIES.items():
            if city not in named:
                self.assertEqual(app.pool_of(city), cfg['currency'], city)
        self.assertEqual({app.pool_of(c) for c in app.CITIES}, {'GBP', 'USD', 'bayarea'})
        self.assertEqual(app._pool_size('USD'), len(app.CITIES['nyc']['boroughs']))
        self.assertEqual(app._pool_size('bayarea'), len(app.CITIES['bayarea']['boroughs']))

    def test_a_metro_in_its_own_pool_leaves_new_york_byte_identical(self):
        self._add_metro('USD-test-metro')
        self.assertEqual(_nyc_scores(), self.baseline)
        self.assertEqual(app._pool_size('USD'), len(app.CITIES['nyc']['boroughs']))

    def test_a_pool_of_none_reads_as_the_currency_as_the_site_reads_null(self):
        self._add_metro(None)
        app.CITIES['zz_test_metro']['pool'] = None
        self.assertEqual(app.pool_of('zz_test_metro'), 'USD')

    def test_the_same_metro_in_the_dollar_pool_does_move_new_york(self):
        self._add_metro(None)
        self.assertNotEqual(_nyc_scores(), self.baseline)


if __name__ == '__main__':
    unittest.main()
