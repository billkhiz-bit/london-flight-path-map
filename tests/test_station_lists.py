"""The published `<CITY>_STATIONS` arrays in index.html — audit I19.

WHY THIS EXISTS AND WHAT NOTHING ELSE COVERS.

`tests/uk-city-panel.mjs` asserts the nearest-stations section is non-empty.
That is a floor on the LIST, not on what is in it, and it passed throughout the
period the product published **Attercliffe five times** — as "Attercliffe",
"Attercliffe From City", "Attercliffe To City", "Attercliffe Platform to City"
and "Attercliffe Platform to Meadowhall". Sheffield Supertram names each
DIRECTION as its own NaPTAN node, so a "four nearest stations" panel could fill
four rows with one tram stop and every gate stayed green.

Measured on the published arrays before the fix: **170 of 943 entries were a
place already listed, 166 of them South Yorkshire.** South Yorkshire went
268 -> 102 and the product 1,651 -> 1,419.

These tests read the SHIPPED arrays rather than re-running the builder, on
purpose: the builder needs the 101 MB gitignored NaPTAN CSV, which a fresh
clone does not have, and the defect was in what reached index.html. A test that
can only run where the raw data is present is a test that does not run.
"""

import json
import math
import os
import re
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
INDEX = os.path.join(REPO, 'index.html')

# The same clause `clean_name` strips, restated here on purpose. Importing it
# from the builder would make this test agree with the builder's bugs - the
# repeated lesson that an expectation read from the code it checks cannot
# disagree with it.
DIRECTIONAL = re.compile(r'\s*\b(?:platform\s+)?(?:to|from|towards)\s+.+$', re.I)

# Names NaPTAN itself marks as retired carry these in the clear. They are not
# how the filter works - `Status` is - but if one appears in the shipped array
# then the Status filter did not run, which is the observable consequence.
RETIRED_MARKERS = ('(closed)', 'disused', 'former station')

# A floor. Every count in this repo's gates carries one, because "0 problems"
# over 0 parsed stations reads exactly like a clean dataset.
MIN_STATIONS = 900
MIN_CITIES = 8


def _metres(a, b):
    """Equirectangular; the distances here are hundreds of metres, not tens of km."""
    lon1, lat1 = a
    lon2, lat2 = b
    dlat = (lat2 - lat1) * 111_320.0
    dlon = (lon2 - lon1) * 111_320.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dlat, dlon)


def _load():
    with open(INDEX, encoding='utf-8', newline='') as handle:
        src = handle.read()
    cities = {}
    for match in re.finditer(r'const ([A-Z_]*STATIONS) = (\[.*?\]);', src, re.S):
        const = match.group(1)
        city = 'london' if const == 'STATIONS' else const[: -len('_STATIONS')].lower()
        cities[city] = json.loads(match.group(2))
    return cities


class StationListTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.cities = _load()

    def test_the_arrays_are_actually_there(self):
        """A parse that finds nothing must fail, not report every check clean."""
        self.assertGreaterEqual(
            len(self.cities), MIN_CITIES,
            f'only {len(self.cities)} station arrays parsed out of index.html - the '
            'constant naming or the JSON layout changed, so every test below is '
            'checking nothing. Fix the pattern, do not delete it.')
        total = sum(len(v) for v in self.cities.values())
        self.assertGreaterEqual(
            total, MIN_STATIONS,
            f'only {total} stations parsed, floor is {MIN_STATIONS}')

    def test_no_place_is_listed_twice_under_a_direction(self):
        """One stop, one entry — however many directions NaPTAN gives it.

        Two entries count as the same place only if they are physically
        together: two genuinely different stations can share a core name, and
        failing those would push the fix towards editing real names, which is
        the scar `clean_name`'s docstring records.
        """
        duplicates = []
        for city, rows in sorted(self.cities.items()):
            by_core = {}
            for row in rows:
                core = ' '.join(DIRECTIONAL.sub('', row['name']).split()).strip(' -,').lower()
                by_core.setdefault(core, []).append(row)
            for core, members in by_core.items():
                if len(members) < 2:
                    continue
                base = members[0]['coords']
                near = [m for m in members if _metres(base, m['coords']) < 800]
                if len(near) > 1:
                    duplicates.append(
                        f'{city}/{core}: ' + ', '.join(repr(m['name']) for m in near))
        self.assertEqual(
            [], duplicates,
            'these places are listed more than once, differing only by a trailing '
            'direction - a "four nearest stations" panel will show fewer than four '
            'places:\n  ' + '\n  '.join(duplicates))

    def test_no_retired_station_is_published_as_current(self):
        """NaPTAN keeps retired nodes with real names and coordinates.

        806 rail-type nodes are `Status: inactive` and were shipping as current
        services until 2026-09-01, among them Oldham Werneth (closed 2009),
        North Woolwich and Silvertown (2006) and Angel Road (2019). The builder
        filters on Status; this asserts the consequence, which is the part a
        reader sees.
        """
        offenders = [
            f'{city}: {row["name"]!r}'
            for city, rows in sorted(self.cities.items())
            for row in rows
            if any(marker in row['name'].lower() for marker in RETIRED_MARKERS)
        ]
        self.assertEqual(
            [], offenders,
            'these carry a retired marker in their own name, so the NaPTAN Status '
            'filter did not run:\n  ' + '\n  '.join(offenders))

    def test_every_entry_has_a_name_and_plausible_uk_coordinates(self):
        """A station with no name renders as an empty row in the panel."""
        bad = []
        for city, rows in sorted(self.cities.items()):
            for row in rows:
                lon, lat = row.get('coords', (None, None))
                if not (row.get('name') or '').strip():
                    bad.append(f'{city}: entry with no name')
                elif not (49.5 <= lat <= 61.0 and -8.5 <= lon <= 2.0):
                    bad.append(f'{city}: {row["name"]!r} at {lat},{lon} is outside the UK')
        self.assertEqual([], bad, '\n  '.join(bad))


class CollectGuardTests(unittest.TestCase):
    """The two guards inside `collect()`, exercised on a SYNTHETIC NaPTAN.

    The builder itself only ever runs where the 101 MB gitignored NaPTAN CSV
    is present, so without these the guards would be unexercised on every
    machine that does not have it - which is every fresh clone and CI. A guard
    nothing runs is the shape this repo keeps paying for.

    Both guards are deliberately two-directional. An absent `Status` column
    makes `row.get('Status')` return None, which compares unequal to 'active'
    and would silently drop EVERY station; the opposite spelling of the same
    test would keep every retired one. Either way the run looks normal.
    """

    SQUARE = {
        'type': 'Polygon',
        'coordinates': [[
            [-1.48, 53.37], [-1.44, 53.37], [-1.44, 53.40],
            [-1.48, 53.40], [-1.48, 53.37],
        ]],
    }
    BBOX = {'t': ((53.37, -1.48, 53.40, -1.44), [SQUARE])}
    COLUMNS = ['CommonName', 'StopType', 'Easting', 'Northing', 'Status']
    ACTIVE = {'CommonName': 'Proof Central', 'StopType': 'RLY',
              'Easting': 435000, 'Northing': 387000, 'Status': 'active'}

    @classmethod
    def setUpClass(cls):
        import importlib.util  # noqa: PLC0415
        import sys  # noqa: PLC0415
        path = os.path.join(REPO, 'scripts', 'build_city_stations.py')
        spec = importlib.util.spec_from_file_location('bcs_under_test', path)
        cls.bcs = importlib.util.module_from_spec(spec)
        sys.modules['bcs_under_test'] = cls.bcs
        spec.loader.exec_module(cls.bcs)

    def _run(self, rows, columns=None):
        import csv  # noqa: PLC0415
        import tempfile  # noqa: PLC0415
        columns = columns or self.COLUMNS
        handle = tempfile.NamedTemporaryFile(
            'w', suffix='.csv', newline='', encoding='utf-8', delete=False)
        with handle as fh:
            writer = csv.DictWriter(fh, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, '') for k in columns})
        self.addCleanup(os.unlink, handle.name)
        self.bcs.NAPTAN_CSV = handle.name
        return self.bcs.collect(self.BBOX)

    def test_active_is_kept_and_inactive_is_dropped(self):
        """The happy path, so the two failures below are not just 'it exits'."""
        inactive = dict(self.ACTIVE, CommonName='Proof Closed', Status='inactive')
        out = self._run([self.ACTIVE, inactive])
        self.assertEqual(['Proof Central'], [s['name'] for s in out['t']])

    def test_an_absent_status_column_is_refused(self):
        columns = [c for c in self.COLUMNS if c != 'Status']
        row = {k: v for k, v in self.ACTIVE.items() if k != 'Status'}
        with self.assertRaises(SystemExit) as caught:
            self._run([row], columns)
        self.assertIn('no Status column', str(caught.exception))

    def test_a_scan_that_excludes_nothing_is_refused(self):
        """NaPTAN changing its Status vocabulary must not read as a clean set."""
        with self.assertRaises(SystemExit) as caught:
            self._run([self.ACTIVE, dict(self.ACTIVE, CommonName='Proof North')])
        self.assertIn('without excluding a single inactive one', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
