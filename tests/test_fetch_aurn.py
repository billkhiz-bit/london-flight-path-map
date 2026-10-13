"""DEFRA's AURN monitors keep their rules (2026-10-13).

`data/aurn-sites.json` is the "nearest official monitor" file the Breathe London
release will show beside DEFRA's modelled background figure. These tests break the
REAL checked-in file one way at a time and assert `--check` names each break, so the
gate is seen to fail on the defect itself rather than on a fixture written to suit it.
The `build()` cases copy rows measured in DEFRA's 2024 files: Canterbury closed on
4 Nov 2024 and is ratified to that day; Nottingham Centre closed in January with 8%
of the year's hours; Warrington has no row in DEFRA's site metadata.
"""
import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / 'scripts'


def _load():
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location('fetch_aurn', SCRIPTS / 'fetch_aurn.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules['fetch_aurn'] = mod
    spec.loader.exec_module(mod)
    return mod


aurn = _load()
REAL = json.loads((REPO / 'data' / 'aurn-sites.json').read_text(encoding='utf-8'))


def problems_after(mutate):
    data = copy.deepcopy(REAL)
    mutate(data)
    return aurn.check(data)


class TheCheckedInFile(unittest.TestCase):
    def test_the_real_file_keeps_every_rule(self):
        self.assertEqual(aurn.check(REAL), [])

    def test_the_year_is_the_pcm_year(self):
        self.assertEqual(REAL['year'], aurn.PCM_YEAR)

    def test_every_covered_uk_city_holds_a_usable_site(self):
        for city, geoms in aurn.uk_city_shapes().items():
            with self.subTest(city=city):
                self.assertTrue(aurn.sites_inside(REAL['sites'], geoms) or city in aurn.NO_SITE_INSIDE)


class EachBreakIsNamed(unittest.TestCase):
    def assertNamed(self, mutate, needle):
        found = problems_after(mutate)
        self.assertTrue(any(needle in p for p in found), f'{needle!r} not in {found}')

    def test_a_year_behind_the_pcm_roll(self):
        self.assertNamed(lambda d: d.update(year=d['year'] - 1), 'is not the PCM year')

    def test_an_attribution_not_word_for_word(self):
        # The NORMAL spelling fails: UK-AIR's statement says "licenced", and it is quoted as published.
        self.assertNamed(lambda d: d.update(attribution=d['attribution'].replace('licenced', 'licensed')),
                         "UK-AIR's required statement")

    def test_swapped_coordinates(self):
        def swap(d):
            s = d['sites'][0]
            s['lat'], s['lon'] = s['lon'], s['lat']
        self.assertNamed(swap, 'is not a UK coordinate')

    def test_a_mean_resting_on_too_few_hours(self):
        def thin(d):
            next(s for s in d['sites'] if s['no2'])['no2']['capture'] = 0.64
        self.assertNamed(thin, 'capture 0.64 is outside')

    def test_an_implausible_mean(self):
        def huge(d):
            next(s for s in d['sites'] if s['pm25'])['pm25']['mean'] = 3.4e38
        self.assertNamed(huge, 'is not a plausible annual mean')

    def test_a_site_with_neither_pollutant(self):
        self.assertNamed(lambda d: d['sites'][0].update(no2=None, pm25=None), 'carries neither pollutant')

    def test_a_duplicate_site(self):
        self.assertNamed(lambda d: d['sites'].append(copy.deepcopy(d['sites'][0])), 'duplicate site codes')

    def test_a_city_losing_every_site_inside_it(self):
        geoms = aurn.uk_city_shapes()['leicester']
        inside = set(aurn.sites_inside(REAL['sites'], geoms))
        self.assertTrue(inside, 'Leicester held no site to remove')
        self.assertNamed(lambda d: d.update(sites=[s for s in d['sites'] if s['code'] not in inside]),
                         'leicester: no usable AURN site inside its boundary')

    def test_a_stale_declaration_fails_too(self):
        aurn.NO_SITE_INSIDE['london'] = 'test'
        try:
            self.assertTrue(any('declared in NO_SITE_INSIDE but' in p for p in aurn.check(REAL)))
        finally:
            del aurn.NO_SITE_INSIDE['london']


def meta(site, param, lat, lon, start, end, ratified, kind='Urban Background', la='Somewhere'):
    return {'site_id': site, 'site_name': site, 'location_type': kind, 'latitude': lat, 'longitude': lon,
            'parameter': param, 'start_date': start, 'end_date': end, 'ratified_to': ratified,
            'local_authority': la}


class TheRulesOfBuild(unittest.TestCase):
    """What enters the file, on rows copied from DEFRA's 2024 files."""

    def setUp(self):
        self.summary = [
            {'code': 'CANT', 'site': 'Canterbury', 'NO2.mean': 8.2, 'NO2.capture': 0.812,
             'PM2.5.mean': 7.8, 'PM2.5.capture': 0.835},
            {'code': 'NOTT', 'site': 'Nottingham Centre', 'NO2.mean': 23.3, 'NO2.capture': 0.08,
             'PM2.5.mean': 10.1, 'PM2.5.capture': 0.08},
            {'code': 'WAR', 'site': 'Warrington', 'NO2.mean': 13.8, 'NO2.capture': 0.95,
             'PM2.5.mean': 8.2, 'PM2.5.capture': 0.95},
            {'code': 'LATE', 'site': 'An open site ratified to September', 'NO2.mean': 20.0, 'NO2.capture': 0.99,
             'PM2.5.mean': float('nan'), 'PM2.5.capture': float('nan')},
        ]
        self.meta = [
            meta('CANT', 'NO2', 51.27399, 1.098061, '2001-02-01', '2024-11-04', '2024-11-04'),
            meta('CANT', 'PM2.5', 51.27399, 1.098061, '2022-05-27', '2024-11-04', '2024-11-04'),
            meta('NOTT', 'NO2', 52.95473, -1.146447, '1996-09-02', '2024-01-30', '2024-01-30'),
            meta('NOTT', 'PM2.5', 52.95473, -1.146447, '2008-12-19', '2024-01-30', '2024-01-30'),
            meta('LATE', 'NO2', 51.5, -0.1, '2010-01-01', 'ongoing', '2024-09-30'),
        ]
        self.data = aurn.build(2024, self.summary, self.meta, fetched='2026-10-13')
        self.codes = {s['code'] for s in self.data['sites']}

    def test_a_site_that_closed_is_ratified_to_its_closing_day(self):
        cant = next(s for s in self.data['sites'] if s['code'] == 'CANT')
        self.assertEqual(cant['no2'], {'mean': 8.2, 'capture': 0.812})
        self.assertEqual(cant['closed'], '2024-11-04')

    def test_an_open_site_ratified_short_of_the_year_end_is_left_out(self):
        self.assertNotIn('LATE', self.codes)
        self.assertIn('ratified only to 2024-09-30', {e['reason'] for e in self.data['excluded']})

    def test_a_mean_under_the_capture_floor_is_left_out(self):
        self.assertNotIn('NOTT', self.codes)
        self.assertIn('capture 8% of hours', {e['reason'] for e in self.data['excluded'] if e['code'] == 'NOTT'})

    def test_a_site_missing_from_the_metadata_is_reported_not_guessed(self):
        self.assertNotIn('WAR', self.codes)
        self.assertIn({'code': 'WAR', 'site': 'Warrington', 'reason': 'no row in AURN_metadata'}, self.data['excluded'])

    def test_the_attribution_carries_the_year_it_was_fetched(self):
        self.assertTrue(aurn.ATTRIBUTION.match(self.data['attribution']))
        self.assertIn('Crown 2026', self.data['attribution'])


if __name__ == '__main__':
    unittest.main()
