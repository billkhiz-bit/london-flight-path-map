"""/v1/environment's `airMeasuredNearby` (2026-11-18, ROADMAP "The plan for Breathe London" step 5, Bill's pick A).

The nearest Breathe London sensor and DEFRA AURN monitor within 5 km of the point asked, read from the SITE'S OWN
files (route 1: one holder). What is held here:

- THE RULES ARE THE SITE'S: the scope, the staleness bar and the distance are read from js/street_report.mjs, and
  the site's own `nearestSensor()` / `nearestMonitor()`, run in node on the repo's files, must pick the same
  instrument at the same distance as the Lambda at every point (a London grid, a UK grid, and both sides of the
  5 km edge of real instruments). An independent implementation, not a fixture this file wrote.
- ABSENCE IS AN ABSENT KEY: nothing within 5 km, no block; no monitor, no `monitor`; no PM2.5, no key; never null.
  A copy past its window, or one that could not be read, is said in `notices`.
- A FILE IS READ WHOLE OR NOT AT ALL, kept an hour, retried after a minute, the last good copy kept meanwhile.
- PROVENANCE: the means are `measured` (the API's first) with the reading's own period, the distance `derived`,
  every other key named as describing the instrument; a new key in neither list fails here by name.
- NEVER SCORED: only `handle_environment` builds the block.
"""

import ast
import copy
import http.client
import io
import json
import math
import os
import random
import re
import subprocess
import sys
import threading
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambdas', 'score'))

import app  # noqa: E402

USES_REAL_AIR_NEARBY = True  # conftest.py stubs the block for every other suite

REPO = Path(__file__).resolve().parents[2]
SITE_JS = (REPO / 'js' / 'street_report.mjs').read_text(encoding='utf-8')
RAW = {
    'sensor': json.loads((REPO / 'data' / 'breathe-london-sensors.json').read_text(encoding='utf-8')),
    'monitor': json.loads((REPO / 'data' / 'aurn-sites.json').read_text(encoding='utf-8')),
}
# A day the sensor copy is current on, whatever month the repo's copy covers: its window's end plus a week.
TODAY = date.fromisoformat(RAW['sensor']['window']['to']) + timedelta(days=7)


def files(kind):
    return copy.deepcopy(RAW[kind])


def js_const(name):
    m = re.search(rf'export const {name} = ([0-9.]+);', SITE_JS)
    assert m, f'{name} not found in js/street_report.mjs'
    return float(m.group(1))


def walk(value, path=''):
    """Every (path, leaf) in a nested dict."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield from walk(v, f'{path}.{k}' if path else k)
    else:
        yield path, value


def site_answers(points, today):
    """The SITE's nearestSensor / nearestMonitor for each point, run in node on the repo's own files."""
    js = (
        "import { readFileSync } from 'node:fs';"
        "import { nearestSensor, nearestMonitor } from './js/street_report.mjs';"
        "const s = JSON.parse(readFileSync('data/breathe-london-sensors.json', 'utf8'));"
        "const m = JSON.parse(readFileSync('data/aurn-sites.json', 'utf8'));"
        "const { points, today } = JSON.parse(readFileSync(0, 'utf8'));"
        "const day = new Date(`${today}T12:00:00Z`);"
        "console.log(JSON.stringify(points.map(([lat, lon]) => {"
        "  const a = nearestSensor(s, lat, lon, day), b = nearestMonitor(m, lat, lon);"
        "  return [a && [a.code, a.km], b && [b.code, b.km]]; })));"
    )
    out = subprocess.run(  # noqa: S603 - node with our own fixed script
        ['node', '--input-type=module', '-e', js],  # noqa: S607 - node from PATH, as preflight runs it
        cwd=REPO, input=json.dumps({'points': points, 'today': today.isoformat()}),
        capture_output=True, text=True, encoding='utf-8', check=True,
    ).stdout
    return json.loads(out)


def edge_points(rows, n=12):
    """Points just inside and just outside 5 km due north and due east of real instruments (0.5 m either side)."""
    out = []
    for row in rows[:: max(1, len(rows) // n)][:n]:
        for d in (5 - 0.0005, 5 + 0.0005):
            dlat = math.degrees(d / 6371.0088)
            dlon = math.degrees(d / (6371.0088 * math.cos(math.radians(row['lat']))))
            out += [[row['lat'] + dlat, row['lon']], [row['lat'], row['lon'] + dlon]]
    return out


class TheRulesAreTheSites(unittest.TestCase):
    def test_the_scope_and_the_staleness_bar_are_read_from_the_site(self):
        self.assertEqual(app.AIR_SCOPE_KM, js_const('AIR_SCOPE_KM'))
        self.assertEqual(app.SENSOR_STALE_DAYS, js_const('SENSOR_STALE_DAYS'))

    def test_the_distance_is_the_sites_haversine(self):
        radius = re.search(r'const haversineKm = [^;]*?;[^;]*?;\s*return 2 \* ([0-9.]+) \*', SITE_JS, re.S)
        self.assertIsNotNone(radius, 'haversineKm not found in js/street_report.mjs')
        lat, lon = 51.5, -0.1
        # One degree of latitude on that radius, to the last digit.
        self.assertAlmostEqual(app.site_km(lat, lon, lat + 1, lon), float(radius.group(1)) * math.pi / 180, places=9)

    def test_the_api_reads_the_files_the_site_ships(self):
        makefile = (REPO / 'Makefile').read_text(encoding='utf-8')
        # The distribution's own address, which the rename does not change: the one the drift check reads the site at.
        drift = (REPO / 'scripts' / 'check_deploy_drift.sh').read_text(encoding='utf-8')
        base = re.search(r'BASE="\$\{SMOKE_BASE:-(https://[^}]+)\}"', drift).group(1)
        for url in app.AIR_FILES.values():
            self.assertTrue(url.startswith(f'{base}/data/'), url)
            path = url[len(base) + 1:]
            self.assertIn(f's3://$(S3_BUCKET)/{path}', makefile, f'{path} is not uploaded by the Makefile')
            self.assertTrue((REPO / path).is_file(), path)

    def test_the_site_and_the_api_pick_the_same_instrument_everywhere(self):
        london = [[51.28 + i * 0.021, -0.51 + j * 0.042] for i in range(21) for j in range(21)]
        uk = [[50.3 + i * 0.25, -4.6 + j * 0.3] for i in range(25) for j in range(20)]
        edges = edge_points(RAW['sensor']['sites']) + edge_points(RAW['monitor']['sites'])
        points = london + uk + edges
        site = site_answers(points, TODAY)
        loaded = {k: app.check_air_file(k, files(k)) for k in RAW}
        found = {'sensor': 0, 'monitor': 0}
        inside_edge = 0
        with patch.object(app, 'air_file', side_effect=lambda kind, now=None: loaded[kind]):
            for (lat, lon), (s, m) in zip(points, site, strict=True):
                for kind, want in (('sensor', s), ('monitor', m)):
                    got = app.nearest_within(loaded[kind]['sites'], lat, lon)
                    self.assertEqual(got is None, want is None, (kind, lat, lon))
                    if got:
                        found[kind] += 1
                        self.assertEqual(got[0]['code'], want[0], (kind, lat, lon))
                        self.assertAlmostEqual(got[1], want[1], places=9)
                        inside_edge += 4.99 < got[1] <= 5
                block, _ = app.build_air_nearby(lat, lon, today=TODAY)
                self.assertEqual((block or {}).get('sensor', {}).get('siteCode'), s and s[0])
                self.assertEqual((block or {}).get('monitor', {}).get('siteCode'), m and m[0])
        # The comparison reached both kinds, both answers and the edge itself.
        self.assertGreater(found['sensor'], 200)
        self.assertGreater(found['monitor'], 100)
        self.assertGreater(inside_edge, 10)
        self.assertGreater(sum(1 for s, m in site if s is None and m is None), 100)

    def test_the_site_and_the_api_agree_on_the_staleness_edge(self):
        to = date.fromisoformat(RAW['sensor']['window']['to'])
        point = [RAW['sensor']['sites'][0]['lat'], RAW['sensor']['sites'][0]['lon']]
        loaded = {k: app.check_air_file(k, files(k)) for k in RAW}
        for days, shown in ((app.SENSOR_STALE_DAYS, True), (app.SENSOR_STALE_DAYS + 1, False)):
            day = to + timedelta(days=days)
            (s, _m), = site_answers([point], day)
            self.assertEqual(s is not None, shown, days)
            with patch.object(app, 'air_file', side_effect=lambda kind, now=None: loaded[kind]):
                block, _ = app.build_air_nearby(*point, today=day)
            self.assertEqual('sensor' in (block or {}), shown, days)


class TheBlock(unittest.TestCase):
    def nearby(self, lat, lon, today=TODAY, sensor=None, monitor=None):
        given = {'sensor': files('sensor') if sensor is None else sensor,
                 'monitor': files('monitor') if monitor is None else monitor}
        with patch.object(app, 'air_file', side_effect=lambda kind, now=None: given[kind]):
            return app.build_air_nearby(lat, lon, today=today)

    def test_both_entries_carry_the_files_own_figures_and_credit(self):
        block, notices = self.nearby(51.464444, -0.164298)  # SW11 1AA's point
        self.assertEqual(notices, [])
        self.assertEqual(block['scopeKm'], 5)
        for kind, key in (('sensor', 'classification'), ('monitor', 'type')):
            entry, raw = block[kind], RAW[kind]
            row = next(r for r in raw['sites'] if r['code'] == entry['siteCode'])
            self.assertEqual(entry['network'], {'sensor': 'Breathe London', 'monitor': 'DEFRA AURN'}[kind])
            self.assertEqual(entry['name'], row['name'])
            self.assertEqual(entry['setting'], row[key].lower())
            self.assertEqual(entry['source'], raw['attribution'])  # word for word: Breathe London's "License"
            self.assertEqual(entry['note'], raw['note'])
            for p, field in (('no2', 'no2MeanUgm3'), ('pm25', 'pm25MeanUgm3')):
                if row[p] is None:
                    self.assertNotIn(field, entry)
                else:
                    self.assertEqual(entry[field], row[p]['mean'])
        self.assertEqual(block['sensor']['period'], RAW['sensor']['window'])
        self.assertEqual(block['sensor']['sourceLink'], RAW['sensor']['attributionLink'])
        self.assertEqual(block['monitor']['sourceLink'], RAW['monitor']['licence'])
        self.assertEqual(block['monitor']['period']['from'], f"{RAW['monitor']['year']}-01-01")

    def test_nothing_in_the_block_is_ever_null(self):
        # At every instrument in both files, so the rows with a gap (no kerb distance, no PM2.5) are each reached.
        points = [(r['lat'], r['lon']) for kind in RAW for r in RAW[kind]['sites']]
        gaps = 0
        for point in points:
            block, _ = self.nearby(*point)
            self.assertTrue(block)
            self.assertEqual([p for p, v in walk(block) if v is None], [], point)
            gaps += sum(1 for e in block.values() if isinstance(e, dict)
                        and ('kerbDistanceM' not in e and e['network'] == 'Breathe London' or 'pm25MeanUgm3' not in e))
        self.assertGreater(gaps, 5)

    def test_outside_london_there_is_a_monitor_and_no_sensor_key(self):
        block, notices = self.nearby(53.379941, -2.265017)  # M22 5RX
        self.assertNotIn('sensor', block)
        self.assertIn('monitor', block)
        self.assertEqual(notices, [])

    def test_with_nothing_within_5_km_there_is_no_block_and_nothing_said(self):
        block, notices = self.nearby(50.722209, -3.530574)  # EX1 1HS
        self.assertIsNone(block)
        self.assertEqual(notices, [])

    def test_a_monitor_without_pm25_has_no_pm25_key(self):
        monitor = files('monitor')
        row = next(r for r in monitor['sites'] if r['pm25'] is None and r['no2'] is not None)
        block, _ = self.nearby(row['lat'], row['lon'], monitor=monitor)
        self.assertNotIn('pm25MeanUgm3', block['monitor'])
        self.assertEqual(block['monitor']['no2MeanUgm3'], row['no2']['mean'])

    def test_a_stale_sensor_copy_is_withheld_and_said(self):
        to = date.fromisoformat(RAW['sensor']['window']['to'])
        block, notices = self.nearby(51.464444, -0.164298, today=to + timedelta(days=app.SENSOR_STALE_DAYS + 1))
        self.assertNotIn('sensor', block)
        self.assertIn('monitor', block)
        self.assertEqual(len(notices), 1)
        self.assertIn('withheld', notices[0])
        self.assertIn(app.air_period_words(RAW['sensor']['window']), notices[0])

    def test_a_stale_sensor_copy_says_nothing_where_no_sensor_is_near(self):
        to = date.fromisoformat(RAW['sensor']['window']['to'])
        _, notices = self.nearby(53.379941, -2.265017, today=to + timedelta(days=90))
        self.assertEqual(notices, [])

    def test_an_unread_file_is_said_where_it_matters_and_the_other_still_answers(self):
        given = {'sensor': None, 'monitor': files('monitor')}
        with patch.object(app, 'air_file', side_effect=lambda kind, now=None: given[kind]):
            block, notices = app.build_air_nearby(51.464444, -0.164298, 'london', today=TODAY)
            self.assertEqual(list(block), ['scopeKm', 'monitor'])
            self.assertEqual(len(notices), 1)
            self.assertTrue(notices[0].startswith('The nearest Breathe London sensor is missing'), notices[0])
            # Manchester is never told a London network is missing.
            block, notices = app.build_air_nearby(53.379941, -2.265017, 'manchester', today=TODAY)
            self.assertEqual(list(block), ['scopeKm', 'monitor'])
            self.assertEqual(notices, [])
        with patch.object(app, 'air_file', return_value=None):
            block, notices = app.build_air_nearby(51.464444, -0.164298, 'london', today=TODAY)
            self.assertIsNone(block)
            self.assertEqual(len(notices), 2)
            # The monitor copy matters anywhere in the UK.
            block, notices = app.build_air_nearby(53.379941, -2.265017, 'manchester', today=TODAY)
            self.assertIsNone(block)
            self.assertEqual(len(notices), 1)
            self.assertTrue(notices[0].startswith('The nearest DEFRA AURN monitor is missing'), notices[0])

    def test_an_unread_sensor_copy_is_said_wherever_a_sensor_could_be_near(self):
        # The circle holds every sensor in the site's file with the 5 km scope to spare...
        lat0, lon0, reach = app.AIR_SENSOR_REACH
        farthest = max(app.site_km(lat0, lon0, r['lat'], r['lon']) for r in RAW['sensor']['sites'])
        self.assertLessEqual(farthest + app.AIR_SCOPE_KM, reach)
        # ...so a point in no covered borough (the route's city is None) but within 5 km of a sensor is told its
        # copy is missing (review 2026-11-19): Stanwell, Spelthorne (Surrey), 4 km from Heathrow Bath Road's sensor.
        stanwell = (51.4499, -0.4709)
        near = app.nearest_within(RAW['sensor']['sites'], *stanwell)
        self.assertIsNotNone(near, 'the Stanwell point is no longer within 5 km of a sensor: pick another')
        given = {'sensor': None, 'monitor': files('monitor')}
        with patch.object(app, 'air_file', side_effect=lambda kind, now=None: given[kind]):
            _, notices = app.build_air_nearby(*stanwell, None, today=TODAY)
        self.assertEqual(len(notices), 1)
        self.assertTrue(notices[0].startswith('The nearest Breathe London sensor is missing'), notices[0])

    def test_a_sensors_kerb_distance_is_the_networks_own_figure(self):
        checked = 0
        for row in RAW['sensor']['sites']:
            if row.get('kerbDistanceM') is None:
                continue
            block, _ = self.nearby(row['lat'], row['lon'])
            if block['sensor']['siteCode'] == row['code']:
                self.assertEqual(block['sensor']['kerbDistanceM'], row['kerbDistanceM'], row['code'])
                checked += 1
        self.assertGreater(checked, 50)

    def test_the_distance_is_sent_as_the_site_shows_it(self):
        # A caller formatting distanceKm the site's way (stationDistance; the extension's nearbyDistance is the same
        # two lines, held below) must get the site's words for the RAW distance. Rounded to 2 dp first, as until
        # 2026-11-19, 1.0451 km read "1.1 km" where the site says "1.0 km": the sweep must reach that defect.
        edges = [0, 0.004, 0.0049999, 0.005, 0.9949, 0.99499999, 0.995, 0.9951, 1.0, 1.0449999, 1.045, 1.0451,
                 1.049999, 1.05, 1.0500001, 1.15, 2.25, 4.95, 4.9999, 5.0]
        rng = random.Random(20261119)  # noqa: S311 - a seeded sweep of test distances, not a secret
        raw = edges + [rng.uniform(0, 5) for _ in range(5000)]
        js = (
            "import { readFileSync } from 'node:fs';"
            "import { stationDistance as d } from './js/street_report.mjs';"
            "console.log(JSON.stringify(JSON.parse(readFileSync(0, 'utf8')).map((xs) => xs.map(d))));"
        )
        site, sent, old = json.loads(subprocess.run(  # noqa: S603 - node with our own fixed script
            ['node', '--input-type=module', '-e', js],  # noqa: S607 - node from PATH, as preflight runs it
            cwd=REPO, input=json.dumps([raw, [app.shown_km(x) for x in raw], [round(x, 2) for x in raw]]),
            capture_output=True, text=True, encoding='utf-8', check=True,
        ).stdout)
        self.assertEqual(sent, site)
        self.assertNotEqual(old, site)
        self.assertEqual(site[edges.index(1.0451)], '1.0 km')
        # And the answer sends exactly that figure, at real points and instruments, under and over 1 km.
        checked = set()
        for lat, lon in [[51.28 + i * 0.021, -0.51 + j * 0.042] for i in range(21) for j in range(21)]:
            block, _ = self.nearby(lat, lon)
            for kind, entry in (block or {}).items():
                if not isinstance(entry, dict):
                    continue
                row = next(r for r in RAW[kind]['sites'] if r['code'] == entry['siteCode'])
                km = app.site_km(lat, lon, row['lat'], row['lon'])
                self.assertEqual(entry['distanceKm'], app.shown_km(km), (kind, lat, lon))
                checked.add(km >= 1)
        self.assertEqual(checked, {True, False})
        # The extension words the distance with the site's own two lines, character for character.
        panel = (REPO / 'extension' / 'content' / 'panel.js').read_text(encoding='utf-8')
        rule = r'\{\s*(const m = Math\.round\(km \* 100\) \* 10;\s*return [^;]+;)'
        ours = re.search(r'function nearbyDistance\(km\) ' + rule, panel)
        theirs = re.search(r'export const stationDistance = \(km\) => ' + rule, SITE_JS)
        self.assertIsNotNone(ours, 'nearbyDistance not found in extension/content/panel.js')
        self.assertIsNotNone(theirs, 'stationDistance not found in js/street_report.mjs')
        self.assertEqual(ours.group(1).split(), theirs.group(1).split())

    def test_a_monitor_that_closed_during_its_year_ends_its_period_there(self):
        monitor = files('monitor')
        row = monitor['sites'][0]
        row['closed'] = f"{monitor['year']}-06-30"
        block, _ = self.nearby(row['lat'], row['lon'], monitor=monitor)
        self.assertEqual(block['monitor']['period'], {'from': f"{monitor['year']}-01-01", 'to': row['closed']})

    def test_the_period_is_worded_as_the_site_words_it(self):
        self.assertEqual(app.air_period_words({'from': '2025-11-01', 'to': '2026-10-31'}), '12 months to October 2026')
        self.assertEqual(app.air_period_words({'from': '2024-01-01', 'to': '2024-12-31'}), '2024')
        self.assertEqual(app.air_period_words({'from': '2024-01-01', 'to': '2024-06-30'}), '2024-01-01 to 2024-06-30')


class AFileIsReadWholeOrNotAtAll(unittest.TestCase):
    def refused(self, kind, change):
        data = files(kind)
        change(data)
        with self.assertRaises(app.AirFileRefused):
            app.check_air_file(kind, data)

    def test_the_repos_own_files_pass(self):
        for kind in RAW:
            app.check_air_file(kind, files(kind))

    def test_each_defect_refuses_the_whole_file(self):
        site = lambda d: d['sites'][3]  # noqa: E731
        self.refused('sensor', lambda d: d.update(sites=[]))
        self.refused('sensor', lambda d: d.pop('attribution'))
        self.refused('sensor', lambda d: d.update(attributionLink='http://example.org'))
        self.refused('sensor', lambda d: d['window'].update(to='2026-13-01'))
        self.refused('sensor', lambda d: d['window'].update(**{'from': '2027-01-01'}))
        self.refused('sensor', lambda d: site(d).pop('lat'))
        self.refused('sensor', lambda d: site(d).update(lat=True))
        self.refused('sensor', lambda d: site(d).update(lon=float('nan')))
        self.refused('sensor', lambda d: site(d).update(no2=None, pm25=None))
        self.refused('sensor', lambda d: site(d).update(no2={'mean': None}))
        self.refused('sensor', lambda d: site(d).update(no2={'mean': -1}))
        self.refused('sensor', lambda d: site(d).update(classification=''))
        self.refused('sensor', lambda d: site(d).update(kerbDistanceM='3 m'))
        self.refused('monitor', lambda d: d.update(year='2024'))
        self.refused('monitor', lambda d: d.pop('licence'))
        self.refused('monitor', lambda d: site(d).update(type=None))
        self.refused('monitor', lambda d: site(d).update(closed='soon'))
        # A date the site's Date.parse would refuse: Python 3.11 takes these, the site does not.
        self.refused('sensor', lambda d: d['window'].update(to=d['window']['to'].replace('-', '')))
        self.refused('sensor', lambda d: d['window'].update(to='2026-W44-6'))
        # A site that closed before the file's year holds no mean for it.
        self.refused('monitor', lambda d: site(d).update(closed=f"{d['year'] - 1}-06-30"))


class FakeResponse:
    """The body in pieces of at most `step` bytes through read1, as http.client gives it; each open starts again."""

    def __init__(self, body, step=65536):
        self.body, self.step, self.at = body, step, 0

    def __enter__(self):
        self.at = 0
        return self

    def __exit__(self, *exc):
        return False

    def read1(self, n=-1):
        n = self.step if n < 0 else min(n, self.step)
        chunk = self.body[self.at:self.at + n]
        self.at += len(chunk)
        return chunk


class TheCopyIsKept(unittest.TestCase):
    def setUp(self):
        app._AIR_FILE_CACHE.clear()
        self.addCleanup(app._AIR_FILE_CACHE.clear)
        self.good = json.dumps(RAW['sensor']).encode('utf-8')

    def test_a_good_copy_is_read_once_an_hour(self):
        with patch.object(app, 'urlopen', return_value=FakeResponse(self.good)) as opened:
            self.assertEqual(app.air_file('sensor', now=0)['window'], RAW['sensor']['window'])
            app.air_file('sensor', now=app.AIR_FILE_TTL_S - 1)
            self.assertEqual(opened.call_count, 1)
            app.air_file('sensor', now=app.AIR_FILE_TTL_S)
            self.assertEqual(opened.call_count, 2)
        request = opened.call_args[0][0]
        self.assertEqual(request.full_url, app.AIR_FILES['sensor'])
        self.assertEqual(opened.call_args[1]['timeout'], app.AIR_FILE_TIMEOUT_S)

    def test_a_failed_read_keeps_the_last_good_copy_and_waits_longer_to_try_again(self):
        with patch.object(app, 'urlopen', return_value=FakeResponse(self.good)):
            first = app.air_file('sensor', now=0)
        start = app.AIR_FILE_TTL_S
        with patch.object(app, 'urlopen', side_effect=URLError('down')) as opened, self.assertLogs(level='WARNING'):
            self.assertIs(app.air_file('sensor', now=start), first)
            self.assertIs(app.air_file('sensor', now=start + app.AIR_FILE_RETRY_HELD_S - 1), first)
            self.assertEqual(opened.call_count, 1)
            app.air_file('sensor', now=start + app.AIR_FILE_RETRY_HELD_S)
            self.assertEqual(opened.call_count, 2)

    def test_with_no_good_copy_a_failure_is_tried_again_after_a_minute(self):
        with patch.object(app, 'urlopen', side_effect=URLError('down')) as opened, self.assertLogs(level='WARNING'):
            self.assertIsNone(app.air_file('sensor', now=0))
            app.air_file('sensor', now=app.AIR_FILE_RETRY_S - 1)
            self.assertEqual(opened.call_count, 1)
            app.air_file('sensor', now=app.AIR_FILE_RETRY_S)
            self.assertEqual(opened.call_count, 2)
        self.assertLess(app.AIR_FILE_RETRY_S, app.AIR_FILE_RETRY_HELD_S)

    def test_both_files_due_are_read_side_by_side(self):
        # Each read waits for the other: read one after the other, the first would wait alone and break the barrier.
        barrier = threading.Barrier(2, timeout=5)
        bodies = {u: json.dumps(RAW[k]).encode('utf-8') for k, u in app.AIR_FILES.items()}

        def opened(req, timeout):
            barrier.wait()
            return FakeResponse(bodies[req.full_url])

        with patch.object(app, 'urlopen', side_effect=opened):
            got = app.air_files(now=0)
        self.assertEqual(set(got), {'sensor', 'monitor'})
        self.assertTrue(all(got.values()))
        with patch.object(app, 'urlopen', side_effect=AssertionError('read again')):
            app.air_files(now=1)  # both held: nothing is read

    def test_with_no_good_copy_a_failure_is_none(self):
        for err in (URLError('down'), HTTPError(app.AIR_FILES['sensor'], 404, 'Not Found', {}, io.BytesIO(b'')),
                    TimeoutError(), http.client.IncompleteRead(b'{"sites": [', 60_000),
                    http.client.RemoteDisconnected('closed')):
            app._AIR_FILE_CACHE.clear()
            with self.subTest(err=type(err).__name__), patch.object(app, 'urlopen', side_effect=err), \
                    self.assertLogs(level='WARNING'):
                self.assertIsNone(app.air_file('sensor', now=0))

    def test_a_body_that_arrives_too_slowly_is_not_read(self):
        # urlopen's timeout is per socket read: a body that keeps arriving inside it, a second a piece here, must
        # still stop at the deadline, or a live caller waits for all of it (review 2026-11-19).
        clock = iter(range(100_000))
        with patch.object(app, 'urlopen', return_value=FakeResponse(self.good, step=1000)), \
                patch.object(app.time, 'monotonic', side_effect=lambda: float(next(clock))), \
                self.assertLogs(level='WARNING') as logs:
            self.assertIsNone(app.air_file('sensor', now=0))
        self.assertIn('TimeoutError', logs.output[0])
        # The same body in the same pieces, read in time, is read whole.
        app._AIR_FILE_CACHE.clear()
        with patch.object(app, 'urlopen', return_value=FakeResponse(self.good, step=1000)):
            self.assertEqual(app.air_file('sensor', now=0)['window'], RAW['sensor']['window'])

    def test_a_body_that_is_not_the_file_is_refused(self):
        # The oversized one is the GOOD file padded with spaces: cut at the cap it is still valid JSON, so only the
        # size rule can refuse it.
        # The last is nested past the JSON parser's depth (RecursionError, not a ValueError).
        for body in (b'<html>Not here</html>', json.dumps({'sites': []}).encode(),
                     self.good + b' ' * (app.AIR_FILE_MAX_BYTES + 1), b'\xff\xfe', b'[' * 200_000):
            app._AIR_FILE_CACHE.clear()
            with self.subTest(body=body[:20]), patch.object(app, 'urlopen', return_value=FakeResponse(body)), \
                    self.assertLogs(level='WARNING'):
                self.assertIsNone(app.air_file('sensor', now=0))


class ItsProvenance(unittest.TestCase):
    def body(self):
        block, _ = TheBlock.nearby(TheBlock(), 51.464444, -0.164298)
        return {'location': {'lat': 51.464444, 'lon': -0.164298, 'postcode': 'SW11 9DX'},
                'environment': {'no2AnnualMeanUgm3': 20.0, 'airQualitySource': 'DEFRA background pollution maps '
                                '(PCM), annual mean 2024, 1 km grid', 'airMeasuredNearby': block}}

    def test_the_means_are_measured_and_the_distance_derived(self):
        prov, index = app.build_provenance(self.body())
        base = 'environment.airMeasuredNearby'
        self.assertEqual(prov[f'{base}.sensor.no2MeanUgm3']['method'], 'measured')
        self.assertEqual(prov[f'{base}.sensor.no2MeanUgm3']['sources'], ['breathe-london'])
        self.assertEqual(prov[f'{base}.sensor.no2MeanUgm3']['period'], app.air_period_words(RAW['sensor']['window']))
        self.assertEqual(prov[f'{base}.monitor.no2MeanUgm3']['sources'], ['defra-aurn'])
        self.assertEqual(prov[f'{base}.monitor.no2MeanUgm3']['period'], str(RAW['monitor']['year']))
        self.assertEqual(prov[f'{base}.sensor.distanceKm']['method'], 'derived')
        self.assertEqual(index['breathe-london']['method'], 'measured')
        self.assertEqual(index['defra-aurn']['method'], 'measured')
        # DEFRA's model beside it stays modelled.
        self.assertEqual(prov['environment.no2AnnualMeanUgm3']['method'], 'modelled')

    def test_every_key_is_a_value_with_an_entry_or_describes_the_instrument(self):
        body = self.body()
        prov, _ = app.build_provenance(body)
        leaves = {f'environment.airMeasuredNearby.{p}' for p, _ in walk(body['environment']['airMeasuredNearby'])}
        unknown = {p for p in leaves if p not in prov and p.split('.')[-1] not in app.AIR_NEARBY_DESCRIBES
                   and p.split('.')[-2] not in ('period',)}
        self.assertEqual(unknown, set())
        self.assertTrue({p for p in prov if 'airMeasuredNearby' in p} <= leaves)

    def test_the_route_sends_the_block_with_its_provenance(self):
        loaded = {k: files(k) for k in RAW}
        event = {'queryStringParameters': {'lat': '51.464444', 'lon': '-0.164298'}}
        location = {'postcode': 'SW11 9DX', 'ladCode': 'E09000032', 'adminDistrict': 'Wandsworth'}
        with patch.object(app, 'reverse_geocode', return_value=location), \
                patch.object(app, '_lookup_noise_row', return_value=None), \
                patch.object(app, 'calc_postcode_quiet', return_value=None), \
                patch.object(app, 'air_file', side_effect=lambda kind, now=None: loaded[kind]):
            res = app.handle_environment(event)
        self.assertEqual(res['statusCode'], 200)
        body = json.loads(res['body'])
        block = body['environment']['airMeasuredNearby']
        self.assertEqual(set(block), {'scopeKm', 'sensor', 'monitor'})
        self.assertIn('environment.airMeasuredNearby.sensor.no2MeanUgm3', body['provenance'])
        self.assertIn('breathe-london', body['sourceIndex'])
        self.assertIn('defra-aurn', body['sourceIndex'])

    def test_the_route_passes_its_city_so_an_unread_london_copy_is_said(self):
        # The city decides whether an unread sensor copy is worth a notice, so the route must pass the one it derived.
        given = {'sensor': None, 'monitor': files('monitor')}
        event = {'queryStringParameters': {'lat': '51.464444', 'lon': '-0.164298'}}
        location = {'postcode': 'SW11 9DX', 'ladCode': 'E09000032', 'adminDistrict': 'Wandsworth'}
        self.assertEqual(app.derive_city(location['ladCode'], location['adminDistrict']), 'london')
        with patch.object(app, 'reverse_geocode', return_value=location), \
                patch.object(app, '_lookup_noise_row', return_value=None), \
                patch.object(app, 'calc_postcode_quiet', return_value=None), \
                patch.object(app, 'air_file', side_effect=lambda kind, now=None: given[kind]):
            body = json.loads(app.handle_environment(event)['body'])
        self.assertIn('monitor', body['environment']['airMeasuredNearby'])
        said = [n for n in body['notices'] if n.startswith('The nearest Breathe London sensor is missing')]
        self.assertEqual(len(said), 1, body['notices'])


class TheSpecDescribesIt(unittest.TestCase):
    def schemas(self):
        import yaml  # noqa: PLC0415 - only this test reads the spec
        spec = yaml.safe_load((REPO / 'score-demo' / 'openapi.yaml').read_text(encoding='utf-8'))
        self.assertEqual(spec['paths']['/v1/environment']['get']['security'], [])
        return spec['components']['schemas']

    def test_every_key_an_entry_carries_is_in_the_spec_and_every_required_one_is_sent(self):
        schemas = self.schemas()
        props, required = set(schemas['AirInstrument']['properties']), set(schemas['AirInstrument']['required'])
        sent = set()
        for point in [(r['lat'], r['lon']) for kind in RAW for r in RAW[kind]['sites']]:
            block, _ = TheBlock.nearby(TheBlock(), *point)
            self.assertEqual(set(block) - set(schemas['AirMeasuredNearby']['properties']), set())
            for entry in (v for v in block.values() if isinstance(v, dict)):
                sent |= set(entry)
                self.assertEqual(required - set(entry), set(), entry['siteCode'])
        self.assertEqual(sent - props, set())
        self.assertEqual(props - sent, set(), 'the spec names a key no entry sends')

    def test_every_environment_key_the_route_sends_is_in_the_spec(self):
        # The live /v1/environment answer captured for provenance, plus the keys only other places produce.
        fixture = Path(__file__).parent / 'fixtures' / 'provenance' / 'environment-hounslow.json'
        live = json.loads(fixture.read_text(encoding='utf-8'))
        source = (REPO / 'backend' / 'lambdas' / 'score' / 'app.py').read_text(encoding='utf-8')
        built = set()
        for name in ('build_environment', 'handle_environment'):
            start = source.index(f'def {name}(')
            body = source[start:source.index('\ndef ', start + 1)]
            built |= set(re.findall(r"env\['(\w+)'\] =", body))
        self.assertGreater(len(built), 12)
        documented = set(self.schemas()['EnvironmentResponse']['properties']['environment']['properties'])
        self.assertEqual((set(live['environment']) | built) - documented, set())


class NeverScored(unittest.TestCase):
    def test_only_the_environment_route_builds_the_block(self):
        source = (REPO / 'backend' / 'lambdas' / 'score' / 'app.py').read_text(encoding='utf-8')
        callers = set()
        for fn in ast.walk(ast.parse(source)):
            if isinstance(fn, ast.FunctionDef):
                for node in ast.walk(fn):
                    if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'build_air_nearby':
                        callers.add(fn.name)
        self.assertEqual(callers, {'handle_environment'})
        self.assertEqual(source.count("'airMeasuredNearby'"), 2)  # the route sets it; provenance reads it


if __name__ == '__main__':
    unittest.main()
