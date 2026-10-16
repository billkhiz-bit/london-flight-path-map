"""New York's borough aircraft band, from the fitted geometry (2026-10-16).

WHY
---
A New York borough's Quiet Skies comes from its `impact` band (IMPACT_TO_QUIET),
and the five bands were written by hand. On 16 Oct the postcode-level estimate was
refitted to the Port Authority's noise monitors (scripts/measure_us_quiet_yardstick.py),
and the hand bands disagreed with it in four boroughs out of five - in BOTH
directions: Queens and Brooklyn read louder than the fitted estimate, the Bronx,
under LaGuardia's approaches, quieter. This derives the bands from that estimate
instead, so a borough says what its own streets say.

HOW
---
Each 2020 ZIP Code Tabulation Area (ZCTA) whose internal point lies inside a
borough's outline (data/nyc-boroughs.json) is scored by the Lambda's own
calc_postcode_quiet at that point, and the borough's figure is the mean weighted
by each ZCTA's population (ACS 5-year table B01003): the quiet of a typical
RESIDENT, not of the borough's land, so JFK's runways and Jamaica Bay do not count
as people. The band is the QUIETEST one whose IMPACT_TO_QUIET value does not exceed
that mean, so a borough never publishes quieter than its own estimate (Bill,
2026-10-16, on the audit's finding that the nearest band put Brooklyn at 5.0 over a
4.11 estimate): the same err-loud rule the fit itself follows.

The ZCTA points and populations are CHECKED IN as data/us-nyc-zcta.json, so
--check runs offline; their sources (the Census gazetteer and the B01003 summary
file, both under ignored data/census/) are re-read when present. Public domain
(US government works).

  python scripts/build_nyc_impact.py --fetch   download B01003 (~18 MB) into data/census/
  python scripts/build_nyc_impact.py --write   rebuild data/us-nyc-zcta.json and both holders' bands
  python scripts/build_nyc_impact.py --check   bands in both holders == the derivation (offline);
                                               the ZCTA file == its sources when they are on disk
"""

import argparse
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'backend' / 'lambdas' / 'score'))
import app  # noqa: E402

YEAR = 2024  # the 2020-2024 ACS 5-year release
POP_URL = (f'https://www2.census.gov/programs-surveys/acs/summary_file/{YEAR}/table-based-SF/data/5YRData/'
           f'acsdt5y{YEAR}-b01003.dat')
POP_RAW = REPO / 'data' / 'census' / f'acsdt5y{YEAR}-b01003.dat'
GAZETTEER = REPO / 'data' / 'census' / '2024_Gaz_zcta_national.zip'
OUTLINES = REPO / 'data' / 'nyc-boroughs.json'
OUT = REPO / 'data' / 'us-nyc-zcta.json'
LAMBDA = REPO / 'backend' / 'lambdas' / 'score' / 'app.py'
SITE = REPO / 'index.html'
BOROUGHS = ('Bronx', 'Brooklyn', 'Manhattan', 'Queens', 'Staten Island')
MIN_ZCTAS = 150  # New York has about 180 populated ZCTAs; fewer means the join broke


def inside(lat, lon, geometry):
    """Even-odd point-in-polygon over every ring, the rule the map's fill uses."""
    polys = geometry['coordinates'] if geometry['type'] == 'MultiPolygon' else [geometry['coordinates']]
    hit = False
    for poly in polys:
        for ring in poly:
            for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1], strict=True):
                if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
                    hit = not hit
    return hit


def from_sources():
    """[{zcta, borough, lat, lon, population}] read from the gazetteer and B01003."""
    with open(OUTLINES, encoding='utf-8') as fh:
        outlines = {f['properties']['name']: f['geometry'] for f in json.load(fh)['features']}
    if set(outlines) != set(BOROUGHS):
        raise SystemExit(f'{OUTLINES.name}: expected the five boroughs, found {sorted(outlines)}')
    pop = {}
    with open(POP_RAW, encoding='utf-8') as fh:
        head = fh.readline().rstrip('\n').split('|')
        if head[:2] != ['GEO_ID', 'B01003_E001']:
            raise SystemExit(f'{POP_RAW.name}: unexpected header {head[:2]}')
        for line in fh:
            gid, est = line.split('|')[:2]
            if gid.startswith('860Z200US'):
                pop[gid[9:]] = int(est)
    rows = []
    with zipfile.ZipFile(GAZETTEER) as z, z.open(z.namelist()[0]) as fh:
        head = fh.readline().decode().split()
        i_id, i_lat, i_lon = head.index('GEOID'), head.index('INTPTLAT'), head.index('INTPTLONG')
        for raw in fh:
            cells = raw.decode().split()
            lat, lon = float(cells[i_lat]), float(cells[i_lon])
            if not (40.4 < lat < 41.0 and -74.3 < lon < -73.6):
                continue
            borough = next((b for b, g in outlines.items() if inside(lat, lon, g)), None)
            if borough:
                zcta = cells[i_id]
                if zcta not in pop:
                    raise SystemExit(f'ZCTA {zcta} ({borough}) has no B01003 row')
                rows.append({'zcta': zcta, 'borough': borough, 'lat': lat, 'lon': lon, 'population': pop[zcta]})
    rows.sort(key=lambda r: r['zcta'])
    return rows


def document(rows):
    return {
        'source': ('US Census Bureau: 2024 ZCTA gazetteer (internal points) and American Community Survey '
                   f'5-year estimates {YEAR - 4}-{YEAR}, table B01003 (total population)'),
        'licence': 'public domain (US government works)',
        'urls': [POP_URL, 'https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/'
                          '2024_Gaz_zcta_national.zip'],
        'borough_rule': 'a ZCTA belongs to the borough whose outline (data/nyc-boroughs.json) holds its internal point',
        'generator': 'scripts/build_nyc_impact.py --write',
        'zctas': rows,
    }


def derive(rows):
    """{borough: (population-weighted mean quiet, band, ZCTAs, population)}."""
    out = {}
    for b in BOROUGHS:
        mine = [r for r in rows if r['borough'] == b and r['population'] > 0]
        people = sum(r['population'] for r in mine)
        if not mine or not people:
            raise SystemExit(f'{b}: no populated ZCTA')
        mean = sum(r['population'] * app.calc_postcode_quiet(r['lat'], r['lon'], 'nyc', raster_lden=None)
                   for r in mine) / people
        # The quietest band not quieter than the estimate: round toward LOUD, never away.
        # 'severe' is 0.0, so some band always qualifies.
        band = max((k for k, v in app.IMPACT_TO_QUIET.items() if v <= mean + 1e-9),
                   key=lambda k: app.IMPACT_TO_QUIET[k])
        out[b] = (mean, band, len(mine), people)
    return out


def block(text, start, path):
    i = text.find(start)
    if i < 0:
        raise SystemExit(f'{path.name}: {start!r} not found')
    j = text.find('\n' + start[:len(start) - len(start.lstrip())] + '}', i)
    return i, j


def holder_bands(text, start, key_fmt, path):
    """{borough: band} read from one holder's New York borough block."""
    i, j = block(text, start, path)
    body = text[i:j]
    out = {}
    for b in BOROUGHS:
        m = re.search(re.escape(key_fmt(b)) + r"\s*\{\s*['\"]?impact['\"]?:\s*'([a-z-]+)'", body)
        if not m:
            raise SystemExit(f'{path.name}: no impact for {b} in its New York block')
        out[b] = m.group(1)
    return out


def rewrite(text, start, key_fmt, bands, path):
    i, j = block(text, start, path)
    body = text[i:j]
    for b, band in bands.items():
        body, n = re.subn(r"(" + re.escape(key_fmt(b)) + r"\s*\{\s*['\"]?impact['\"]?:\s*)'[a-z-]+'",
                          lambda m, band=band: m.group(1) + f"'{band}'", body)
        if n != 1:
            raise SystemExit(f'{path.name}: {b} matched {n} times')
    return text[:i] + body + text[j:]


HOLDERS = (
    (LAMBDA, 'NYC_BOROUGHS = {', lambda b: f"'{b}':"),
    (SITE, '      const NYC_BOROUGH_DATA_RAW = {', lambda b: f"'{b}':" if ' ' in b else f'{b}:'),
)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--fetch', action='store_true')
    g.add_argument('--write', action='store_true')
    g.add_argument('--check', action='store_true')
    args = ap.parse_args()

    if args.fetch:
        POP_RAW.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(POP_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=300) as resp, open(POP_RAW, 'wb') as fh:  # noqa: S310
            fh.write(resp.read())
        print(f'wrote {POP_RAW.relative_to(REPO)}')
        return 0

    failures = []
    if args.write:
        rows = from_sources()
        OUT.write_text(json.dumps(document(rows), indent=1) + '\n', encoding='utf-8', newline='\n')
        print(f'wrote {OUT.relative_to(REPO)}: {len(rows)} ZCTAs')
    else:
        rows = json.loads(OUT.read_text(encoding='utf-8'))['zctas']
        if POP_RAW.exists() and GAZETTEER.exists():
            if from_sources() != rows:
                failures.append(f'{OUT.name} is not what its sources give (re-run --write)')
            else:
                print(f'  sources        {OUT.name} == gazetteer + B01003')
        else:
            print('  sources        not on disk; the checked-in ZCTA file was not re-derived')
    if len(rows) < MIN_ZCTAS:
        failures.append(f'only {len(rows)} ZCTAs (floor {MIN_ZCTAS}): the borough join broke')

    derived = derive(rows)
    for b, (mean, band, n, people) in derived.items():
        print(f'  {b:14} {n:3} ZCTAs  {people:>9,} people  quiet {mean:4.2f} -> {band} '
              f'({app.IMPACT_TO_QUIET[band]})')
    want = {b: v[1] for b, v in derived.items()}
    for path, start, key_fmt in HOLDERS:
        text = path.read_text(encoding='utf-8')
        have = holder_bands(text, start, key_fmt, path)
        if have == want:
            print(f'  {path.name:14} bands already current')
            continue
        if args.write:
            path.write_text(rewrite(text, start, key_fmt, want, path), encoding='utf-8', newline='')
            print(f'  {path.name:14} rewritten: ' +
                  ', '.join(f'{b} {have[b]} -> {want[b]}' for b in BOROUGHS if have[b] != want[b]))
        else:
            failures.extend(f'{path.name}: {b} is {have[b]}, the fit gives {want[b]}'
                            for b in BOROUGHS if have[b] != want[b])
    if failures:
        print('RESULT: FAIL')
        for f in failures:
            print('  ' + f)
        return 1
    print('RESULT: PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
