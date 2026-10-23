"""Staten Island's note on the full map says only what the data holds (audit 2026-10-22 M-7).

It said Newark departures pass "at high altitude" and that the borough is "well away from major flight paths".
The FAA's PORTT4 departure from runway 22 (CIFP: heading 219 magnetic to 518 ft, then direct BAGGA, then PORTT)
crosses the north-west of the borough 4.2 to 7.6 km after the runway end, and the CIFP codes no altitude after
518 ft, so "high altitude" had no source. The note now names the route and where it crosses, in words rather
than kilometres (a hand-typed number goes stale with the next FAA cycle), and these checks hold each claim to
the data it rests on: that PORTT still crosses the borough, inside "a few kilometres" (under 10 km of the
runway end), and that Staten Island still has the highest Quiet Skies of the five boroughs.
"""
import json
import math
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def note():
    src = (ROOT / 'index.html').read_text(encoding='utf-8')
    m = re.search(r"'Staten Island'.*?note: '([^']*)'", src, re.S)
    return m.group(1) if m else ''


def staten_polygons():
    geo = json.loads((ROOT / 'data' / 'nyc-boroughs.json').read_text(encoding='utf-8'))
    feat = next(f for f in geo['features'] if 'staten' in json.dumps(f['properties']).lower())
    g = feat['geometry']
    return g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]


def inside(polys, lat, lon):
    """Ray casting on each polygon's outer ring: a point in the borough, never its bounding box."""
    hit = False
    for poly in polys:
        ring = poly[0]
        j = len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                hit = not hit
            j = i
    return hit


def km(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    return 2 * 6371.0 * math.asin(math.sqrt(math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2))


class StatenIslandNoteTests(unittest.TestCase):
    def test_the_note_claims_no_altitude_and_no_distance_from_flight_paths(self):
        text = note()
        self.assertTrue(text, 'Staten Island has no note in index.html: update this test with the move')
        self.assertNotIn('high altitude', text)
        self.assertNotIn('Well away from major flight paths', text)

    def test_the_portt_route_it_names_still_crosses_the_borough_within_a_few_kilometres(self):
        if 'PORTT' not in note():
            self.skipTest('the note no longer names the PORTT route')
        ewr = json.loads((ROOT / 'data' / 'us-flight-procedures.json').read_text(encoding='utf-8'))['airports']['EWR']
        portt = [d for d in ewr['departures'] if d['name'].startswith('PORTT')]
        self.assertTrue(portt, 'the FAA data has no PORTT departure from Newark: rewrite the note')
        polys = staten_polygons()
        # A runway 22 departure leaves the ground at the far end, the runway 4 threshold.
        for rw, end in (('22L', ewr['runways']['04R']['thr']), ('22R', ewr['runways']['04L']['thr'])):
            path, along, crossing = [tuple(end)] + [tuple(p) for p in portt[0]['waypoints']], 0.0, []
            for a, b in zip(path, path[1:], strict=False):  # consecutive pairs: the second list is one shorter
                seg = km(a, b)
                n = int(seg / 0.02) + 1
                crossing += [along + seg * k / n for k in range(n + 1)
                             if inside(polys, a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)]
                along += seg
            self.assertTrue(crossing, f'PORTT from {rw} no longer crosses Staten Island: rewrite the note')
            self.assertLess(max(crossing), 10, f'PORTT from {rw} crosses {min(crossing):.1f}-{max(crossing):.1f} km out: not "a few kilometres"')

    def test_it_is_still_the_quietest_borough_it_says_it_is(self):
        if 'quietest borough for aircraft noise in NYC' not in note():
            self.skipTest('the note no longer makes the claim')
        rows = json.loads((ROOT / 'data' / 'us-nyc.json').read_text(encoding='utf-8'))['rows']
        quiet = {r['borough']: float(r['quiet']) for r in rows if r.get('quiet') not in (None, '')}
        self.assertEqual(max(quiet, key=quiet.get), 'Staten Island', quiet)


if __name__ == '__main__':
    unittest.main()
