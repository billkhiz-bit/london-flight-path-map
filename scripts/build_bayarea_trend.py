"""House-price trend for the Bay Area's four counties: FHFA's county HPI (2026-10-16).

Release 2's growth input (ROADMAP "Release 2 plan"): the Federal Housing Finance Agency's
annual county house price index, the "developmental" all-transactions series, for the four
counties of data/us-bayarea-places.json (Alameda, San Francisco, San Mateo, Santa Clara).
It is a COUNTY figure, so every city in a county shares it, and an ANNUAL one, a calendar
year behind the UK's monthly HPI: the file says both, and nothing may present it as a city's
own trend.

Licence: public domain under FHFA's website policy, section 10 ("information and materials
produced by Federal agencies, including FHFA, are in the public domain and may be copied and
distributed without permission. This excludes the FHFA seal"); section 11 forbids implying
FHFA's endorsement. Keyless download.

  python scripts/build_bayarea_trend.py --fetch   download the workbook (~5 MB) into data/fhfa/
  python scripts/build_bayarea_trend.py --write   write data/us-bayarea-trend.json from it
  python scripts/build_bayarea_trend.py --check   the file is sound (offline); and, when the
                                                  workbook is on disk, every value against it
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
URL = 'https://www.fhfa.gov/hpi/download/annual/hpi_at_county.xlsx'
RAW = REPO / 'data' / 'fhfa' / 'hpi_at_county.xlsx'
PLACES = REPO / 'data' / 'us-bayarea-places.json'
OUT = REPO / 'data' / 'us-bayarea-trend.json'
HEADER = ('State', 'County', 'FIPS code', 'Year', 'Annual Change (%)', 'HPI')
FIPS = {'Alameda': '06001', 'San Francisco': '06075', 'San Mateo': '06081', 'Santa Clara': '06085'}


def counties():
    """The counties the Bay Area's cities sit in, from the places file (never a list typed here alone)."""
    with open(PLACES, encoding='utf-8') as fh:
        names = {p['county'] for p in json.load(fh)['places']}
    names = {n.removesuffix(' County') for n in names}
    if names != set(FIPS):
        raise SystemExit(f'{PLACES.name} names counties {sorted(names)}; FIPS here covers {sorted(FIPS)}')
    return names


def read_raw():
    """{fips: [(year, annual change %, index)]} for the four counties, from FHFA's workbook."""
    import openpyxl  # noqa: PLC0415 - only the write and verify paths need it
    wb = openpyxl.load_workbook(RAW, read_only=True)
    ws = wb.worksheets[0]
    out, seen_header, updated = {f: [] for f in FIPS.values()}, False, None
    for row in ws.iter_rows(values_only=True):
        if not seen_header:
            if row and isinstance(row[0], str) and row[0].startswith('Last updated:'):
                updated = row[0].removeprefix('Last updated:').strip().rstrip('.')
            if tuple(row[:6]) == HEADER:
                seen_header = True
            continue
        if row[2] in out and row[4] is not None:
            out[row[2]].append((int(row[3]), float(row[4]), float(row[5])))
    if not seen_header:
        raise SystemExit(f'{RAW.name}: header {HEADER} not found; FHFA changed the layout')
    return out, updated


def build():
    counties()
    raw, updated = read_raw()
    rows = []
    for name, fips in sorted(FIPS.items()):
        series = sorted(raw[fips])
        if not series:
            raise SystemExit(f'{name} ({fips}): no FHFA rows')
        year, change, index = series[-1]
        rows.append({'county': name, 'fips': fips, 'year': year, 'annual_change_pct': change, 'index': index})
    if len({r['year'] for r in rows}) != 1:
        raise SystemExit(f'the counties end in different years: {rows}')
    return {
        'source': 'Federal Housing Finance Agency, House Price Index for counties (all-transactions, annual, '
                  'not seasonally adjusted), a series FHFA calls developmental',
        'url': URL,
        'fhfa_last_updated': updated,
        'licence': 'public domain (FHFA website policy s10); never imply FHFA endorsement (s11)',
        'generator': 'scripts/build_bayarea_trend.py --write',
        'scope': 'county-wide: every city in a county shares its figure, and it is a calendar year, not a month',
        'counties': rows,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--fetch', action='store_true')
    g.add_argument('--write', action='store_true')
    g.add_argument('--check', action='store_true')
    a = ap.parse_args()
    if a.fetch:
        RAW.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=300) as resp, open(RAW, 'wb') as fh:  # noqa: S310
            fh.write(resp.read())
        print(f'wrote {RAW.relative_to(REPO)}')
        return 0
    if a.write:
        doc = build()
        OUT.write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8', newline='\n')
        print(f'wrote {OUT.relative_to(REPO)}: ' + ', '.join(f"{r['county']} {r['annual_change_pct']:+.2f}% ({r['year']})" for r in doc['counties']))
        return 0
    failures = []
    doc = json.loads(OUT.read_text(encoding='utf-8'))
    names = {r['county'] for r in doc['counties']}
    if names != counties():
        failures.append(f'counties {sorted(names)} are not the places file\'s')
    for r in doc['counties']:
        if not (-50 < r['annual_change_pct'] < 50) or r['fips'] != FIPS.get(r['county']):
            failures.append(f'implausible row {r}')
    if RAW.exists():
        if build()['counties'] != doc['counties']:
            failures.append(f'{OUT.name} is not what the workbook gives (re-run --write)')
        else:
            print(f'  workbook       {OUT.name} == {RAW.name}')
    else:
        print('  workbook       not on disk; the checked-in file was checked for shape only')
    if failures:
        print('RESULT: FAIL')
        for f in failures:
            print('  ' + f)
        return 1
    print(f"RESULT: PASS ({len(doc['counties'])} counties, {doc['counties'][0]['year']})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
