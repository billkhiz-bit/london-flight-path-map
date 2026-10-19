"""Breathe London's sensors keep their rules (2026-10-19).

`data/breathe-london-sensors.json` is the "nearest sensor" file the front page and street
report will show beside DEFRA's modelled background figure. These tests break the REAL
checked-in file one way at a time and assert `--check` names each break, so the gate is
seen to fail on the defect itself rather than on a fixture written to suit it. The
`build()` cases copy the shapes measured on the API on 2026-10-19: a missing hour is a
row with a null `ScaledValue`, `endTime` is inclusive, a sensor installed inside the
window has no rows before it, and `RatificationStatus` is "P" or "R".
"""
import contextlib
import copy
import datetime
import importlib.util
import io
import json
import os
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / 'scripts'


def _load():
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location('fetch_breathe_london', SCRIPTS / 'fetch_breathe_london.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules['fetch_breathe_london'] = mod
    spec.loader.exec_module(mod)
    return mod


bl = _load()
REAL = json.loads((REPO / 'data' / 'breathe-london-sensors.json').read_text(encoding='utf-8'))
UTC = datetime.UTC


def problems_after(mutate, key=None):
    data = copy.deepcopy(REAL)
    mutate(data)
    return bl.check(data, key)


class TheCheckedInFile(unittest.TestCase):
    def test_the_real_file_keeps_every_rule(self):
        self.assertEqual(bl.check(REAL), [])

    def test_every_borough_holds_a_usable_sensor_or_says_why(self):
        held = {s['borough'] for s in REAL['sites']}
        for code, name, _geom in bl.london_boroughs():
            with self.subTest(borough=name):
                self.assertTrue(code in held or code in bl.NO_SENSOR_INSIDE)

    def test_no_field_beyond_the_schema(self):
        # A key smuggled into a new field would survive every value check; the schema cannot.
        self.assertEqual(set(REAL), {'source', 'attribution', 'attributionLink', 'licence', 'window',
                                     'captureFloor', 'fetched', 'note', 'sites', 'excluded'})
        for s in REAL['sites']:
            self.assertEqual(set(s), {'code', 'name', 'borough', 'boroughName', 'classification', 'locationType',
                                      'kerbDistanceM', 'heightM', 'lat', 'lon', 'measuringSince', 'no2', 'pm25'})


class EachBreakIsNamed(unittest.TestCase):
    def assertNamed(self, mutate, needle, key=None):
        found = problems_after(mutate, key)
        self.assertTrue(any(needle in p for p in found), f'{needle!r} not in {found}')

    def test_an_attribution_not_word_for_word(self):
        # The BRITISH spelling fails: Breathe London's statement says "License", quoted as published.
        self.assertNamed(lambda d: d.update(attribution=d['attribution'].replace('License', 'Licence')),
                         "Breathe London's required statement")

    def test_the_api_key_in_the_file(self):
        self.assertNamed(lambda d: d['sites'][0].update(name='abc123SECRET'), 'contains the API key',
                         key='abc123SECRET')

    def test_swapped_coordinates(self):
        def swap(d):
            s = d['sites'][0]
            s['lat'], s['lon'] = s['lon'], s['lat']
        self.assertNamed(swap, 'is not inside')

    def test_a_sensor_filed_under_the_wrong_borough(self):
        def move(d):
            s = d['sites'][0]
            other = next(code for code, _n, _g in bl.london_boroughs() if code != s['borough'])
            s['borough'] = other
        self.assertNamed(move, 'is not inside')

    def test_a_borough_name_typed_rather_than_derived(self):
        self.assertNamed(lambda d: d['sites'][0].update(boroughName='Somewhere'), 'boroughName')

    def test_a_window_that_is_not_the_12_months_before_the_fetch(self):
        self.assertNamed(lambda d: d['window'].update({'from': '2025-09-01'}), 'is not the 12 months before')

    def test_a_mean_resting_on_too_few_hours(self):
        def thin(d):
            next(s for s in d['sites'] if s['no2'])['no2']['capture'] = 0.74
        self.assertNamed(thin, 'capture 0.74 is outside')

    def test_an_implausible_mean(self):
        def huge(d):
            next(s for s in d['sites'] if s['pm25'])['pm25']['mean'] = 3.4e38
        self.assertNamed(huge, 'is not a plausible 12-month mean')

    def test_an_unknown_classification(self):
        self.assertNamed(lambda d: d['sites'][0].update(classification='Industrial'), 'unknown classification')

    def test_a_sensor_with_neither_pollutant(self):
        self.assertNamed(lambda d: d['sites'][0].update(no2=None, pm25=None), 'carries neither pollutant')

    def test_a_duplicate_sensor(self):
        self.assertNamed(lambda d: d['sites'].append(copy.deepcopy(d['sites'][0])), 'duplicate site codes')

    def test_a_borough_losing_every_sensor_inside_it(self):
        code = REAL['sites'][0]['borough']
        self.assertNamed(lambda d: d.update(sites=[s for s in d['sites'] if s['borough'] != code]),
                         f'{code} ')

    def test_a_mean_resting_on_hours_from_before_this_place(self):
        # A sensor moved under its code: its mean counted hours from the old place.
        def moved(d):
            s = next(s for s in d['sites'] if s['no2'] and s['no2']['capture'] > 0.9)
            s['measuringSince'] = '2026-04-01'
        self.assertNamed(moved, 'possible since it began measuring here')

    def test_a_measuring_since_that_is_not_a_date(self):
        self.assertNamed(lambda d: d['sites'][0].update(measuringSince=None), 'measuringSince None is not a date')

    def test_a_stale_declaration_fails_too(self):
        code = REAL['sites'][0]['borough']
        bl.NO_SENSOR_INSIDE[code] = 'test'
        try:
            self.assertTrue(any('declared in NO_SENSOR_INSIDE but' in p for p in bl.check(REAL)))
        finally:
            del bl.NO_SENSOR_INSIDE[code]


def hours(start, n, value=20.0, status='P', code='BL0001', species='NO2', every=None):
    """`n` hourly rows from `start`, in the API's shape. `every` maps an hour index to a value."""
    rows = []
    for i in range(n):
        t = start + datetime.timedelta(hours=i)
        v = every(i) if every else value
        rows.append({'Species': species, 'Source': 'Measurement', 'Units': 'ug.m-3', 'SiteCode': code,
                     'DateTime': t.strftime(bl.STAMP), 'Duration': 'PT1H', 'ScaledValue': v,
                     'RatificationStatus': status if v is not None else None, 'SensorContract': 'Vodafone'})
    return rows


class TheWindow(unittest.TestCase):
    def test_the_12_whole_months_before_the_fetch_month(self):
        start, end = bl.window(datetime.date(2026, 10, 19))
        self.assertEqual((start, end), (datetime.datetime(2025, 10, 1, tzinfo=UTC),
                                        datetime.datetime(2026, 10, 1, tzinfo=UTC)))
        self.assertEqual(bl.window_label(start, end), {'from': '2025-10-01', 'to': '2026-09-30'})

    def test_a_january_fetch_takes_the_previous_calendar_year(self):
        self.assertEqual(bl.window_label(*bl.window(datetime.date(2027, 1, 3))),
                         {'from': '2026-01-01', 'to': '2026-12-31'})

    def test_a_window_holding_29_february_has_8784_hours(self):
        start, end = bl.window(datetime.date(2024, 3, 9))
        self.assertEqual(round((end - start) / bl.HOUR), 8784)


class TheRulesOfSummarise(unittest.TestCase):
    """One sensor's mean, on rows shaped as the API answered on 2026-10-19."""

    def setUp(self):
        self.start, self.end = bl.window(datetime.date(2026, 10, 19))
        self.n = round((self.end - self.start) / bl.HOUR)

    def summarise(self, rows):
        return bl.summarise(rows, 'BL0001', 'NO2', self.start, self.end)

    def test_capture_is_over_the_windows_hours_not_the_rows_returned(self):
        # Installed a quarter of the way in: the API has no rows before that, so a share of the
        # rows RETURNED would read 100%. Over the window's hours it is 75%, exactly the floor.
        late = self.start + datetime.timedelta(hours=self.n // 4)
        result, reason = self.summarise(hours(late, self.n - self.n // 4))
        self.assertIsNone(reason)
        self.assertEqual(result['capture'], 0.75)
        result, reason = self.summarise(hours(late + bl.HOUR, self.n - self.n // 4 - 1))
        self.assertEqual(reason, 'capture 75% of hours')  # one hour short: 74.99..., under the floor

    def test_a_null_hour_is_missing_not_zero(self):
        rows = hours(self.start, self.n, every=lambda i: None if i % 2 else 30.0)
        result, reason = self.summarise(rows)
        self.assertIsNone(result)
        self.assertEqual(reason, 'capture 50% of hours')
        rows = hours(self.start, self.n, every=lambda i: None if i % 10 == 0 else 30.0)
        self.assertEqual(self.summarise(rows)[0]['mean'], 30.0)  # not 27.0, as zeros would make it

    def test_the_inclusive_end_hour_is_not_counted(self):
        # The API's endTime is inclusive, so an extra hour at the window's end can arrive.
        rows = hours(self.start, self.n) + hours(self.end, 1, value=1000.0)
        result, reason = self.summarise(rows)
        self.assertEqual((result['mean'], result['capture']), (20.0, 1.0))

    def test_an_hour_returned_twice_is_refused(self):
        rows = hours(self.start, self.n)
        rows.append(dict(rows[5]))
        self.assertIn('returned twice', self.summarise(rows)[1])

    def test_a_row_for_another_sensor_is_refused(self):
        rows = hours(self.start, self.n)
        rows[0]['SiteCode'] = 'BL0002'
        self.assertIn('BL0002', self.summarise(rows)[1])

    def test_units_other_than_ug_m3_are_refused_not_converted(self):
        rows = hours(self.start, self.n)
        for r in rows:
            r['Units'] = 'ppb'
        self.assertIn('not hourly ug.m-3', self.summarise(rows)[1])

    def test_the_ratified_share(self):
        rows = hours(self.start, self.n // 4, status='R') + hours(
            self.start + datetime.timedelta(hours=self.n // 4), self.n - self.n // 4)
        self.assertEqual(self.summarise(rows)[0]['ratified'], 0.25)


class TheRulesOfBuild(unittest.TestCase):
    """Which sensors enter the file."""

    def setUp(self):
        self.boroughs = bl.london_boroughs()
        start, end = bl.window(datetime.date(2026, 10, 19))
        n = round((end - start) / bl.HOUR)
        westminster = dict(Latitude='51.4975', Longitude='-0.1357', Borough='Westminster')  # Victoria Street
        self.sensors = [
            dict(SiteCode='BL0001', SiteName='Live, full year', EndDate=None, SiteClassification='Roadside',
                 **westminster),
            dict(SiteCode='BL0002', SiteName='Moved away', EndDate='2026-03-01T00:00:00Z',
                 SiteClassification='Roadside', **westminster),
            dict(SiteCode='BL0003', SiteName='Outside London', EndDate=None, SiteClassification='Roadside',
                 Latitude='51.7520', Longitude='-1.2577', Borough='Oxford'),
            dict(SiteCode='BL0004', SiteName='NO2 only', EndDate=None, SiteClassification='Kerbside',
                 **westminster),
        ]
        self.series = {
            ('BL0001', 'NO2'): hours(start, n, code='BL0001'),
            ('BL0001', 'PM25'): hours(start, n, value=8.0, code='BL0001', species='PM25'),
            ('BL0004', 'NO2'): hours(start, n, value=40.0, code='BL0004'),
            ('BL0004', 'PM25'): hours(start, n // 2, value=9.0, code='BL0004', species='PM25'),
        }
        self.data = bl.build(self.sensors, self.series, '2026-10-19', self.boroughs)
        self.by_code = {s['code']: s for s in self.data['sites']}

    def test_a_sensor_with_an_end_date_is_not_listed(self):
        self.assertNotIn('BL0002', self.by_code)
        self.assertNotIn('BL0002', {e['code'] for e in self.data['excluded']})

    def test_a_sensor_outside_every_borough_is_reported_not_placed(self):
        self.assertNotIn('BL0003', self.by_code)
        self.assertIn('is inside no London borough',
                      next(e['reason'] for e in self.data['excluded'] if e['code'] == 'BL0003'))

    def test_the_borough_comes_from_the_boundary_with_its_ons_code(self):
        self.assertEqual((self.by_code['BL0001']['borough'], self.by_code['BL0001']['boroughName']),
                         ('E09000033', 'Westminster'))

    def test_one_usable_pollutant_keeps_the_sensor_and_names_the_other(self):
        s = self.by_code['BL0004']
        self.assertEqual((s['no2']['mean'], s['pm25']), (40.0, None))
        self.assertIn({'code': 'BL0004', 'site': 'NO2 only', 'pollutant': 'pm25', 'reason': 'capture 50% of hours'},
                      self.data['excluded'])

    def test_an_unfetched_series_is_named_not_skipped(self):
        del self.series[('BL0001', 'PM25')]
        data = bl.build(self.sensors, self.series, '2026-10-19', self.boroughs)
        self.assertIn({'code': 'BL0001', 'site': 'Live, full year', 'pollutant': 'pm25', 'reason': 'not fetched'},
                      data['excluded'])


class OnePlacePerMean(unittest.TestCase):
    """`/SensorData` by site code returns every installation's hours (BL0005: 5,996 valid hours before
    its live installation began, 2026-10-19). A move under the same code must not blend two places."""

    def setUp(self):
        self.boroughs = bl.london_boroughs()
        start, end = bl.window(datetime.date(2026, 10, 19))
        n = round((end - start) / bl.HOUR)
        self.live = dict(SiteCode='BL0009', SiteName='Here since April', EndDate=None, StartDate='2026-04-01T00:00:00Z',
                         Latitude='51.4975', Longitude='-0.1357', SiteClassification='Roadside', DistanceToKerb=2.0,
                         SensorHeightAboveGround=2.8)
        self.series = {('BL0009', 'NO2'): hours(start, n, code='BL0009'),
                       ('BL0009', 'PM25'): hours(start, n, value=8.0, code='BL0009', species='PM25')}

    def build(self, *earlier):
        return bl.build([*earlier, self.live], self.series, '2026-10-19', self.boroughs)

    def reason(self, data):
        return next(e['reason'] for e in data['excluded'] if e['code'] == 'BL0009' and e.get('pollutant') == 'no2')

    def test_hours_from_another_place_are_dropped(self):
        elsewhere = dict(self.live, StartDate='2024-01-01T00:00:00Z', EndDate='2026-04-01T00:00:00Z', Latitude='51.5100')
        data = self.build(elsewhere)
        # October to March belong to the old place: 4,392 of the window's 8,760 hours are this one's.
        self.assertEqual(self.reason(data), 'capture 50% of hours (measuring here since 2026-04-01)')
        self.assertEqual(data['sites'], [])

    def test_a_device_swapped_on_the_same_post_keeps_its_hours(self):
        swapped = dict(self.live, StartDate='2024-01-01T00:00:00Z', EndDate='2026-04-01T00:00:00Z',
                       SensorHeightAboveGround=2.4)  # BL0056's swap moved it 0.4 m up the post
        s = self.build(swapped)['sites'][0]
        self.assertEqual((s['no2']['capture'], s['measuringSince']), (1.0, '2024-01-01'))

    def test_an_installation_elsewhere_ends_the_run(self):
        older_here = dict(self.live, StartDate='2023-01-01T00:00:00Z', EndDate='2024-01-01T00:00:00Z')
        between = dict(self.live, StartDate='2024-01-01T00:00:00Z', EndDate='2026-04-01T00:00:00Z', Latitude='51.5100')
        self.assertIn('measuring here since 2026-04-01', self.reason(self.build(older_here, between)))


class TheKeyStaysHome(unittest.TestCase):
    def test_a_redirect_is_refused_not_followed(self):
        # urllib would copy the X-API-KEY header onto the redirected request, to any host.
        req = urllib.request.Request('https://example.invalid/x', headers={'X-API-KEY': 'k'})
        with self.assertRaises(urllib.error.HTTPError):
            bl._NoRedirect().redirect_request(req, None, 302, 'Found', {}, 'http://elsewhere.invalid/')

    def test_a_check_that_finds_the_key_does_not_print_it(self):
        # The key, as if it had leaked into a field the report prints (the classification counts):
        # --check must name the problem without echoing it.
        leaked = 'Roadside'
        self.assertIn(leaked, {s['classification'] for s in REAL['sites']})
        out = io.StringIO()
        with mock.patch.dict(os.environ, {bl.KEY_NAME: leaked}), contextlib.redirect_stdout(out):
            code = bl.main(['--check'])
        self.assertEqual(code, 1)
        self.assertIn('the file contains the API key', out.getvalue())
        self.assertNotIn(leaked, out.getvalue())


if __name__ == '__main__':
    unittest.main()
