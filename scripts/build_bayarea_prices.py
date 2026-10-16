"""Median home value for the Bay Area's 50 cities: ACS 5-year table B25077 (2026-10-16).

Release 2's price input (ROADMAP "Release 2 plan"): the US Census Bureau's American
Community Survey 5-year estimate of the median value of owner-occupied housing units,
for each of the 43 cities and 7 towns of data/us-bayarea-places.json (the 28
unincorporated CDPs are not cities and are left out, as on the page).

Fetched from the keyless SUMMARY FILE (one file per table, every US geography); the
Census API now refuses requests without a key, so it is not used. Public domain
(a US government work).

TOP-CODING: B25077 reports "$2,000,000+" as 2000001. That is a FLOOR, not a price: 16
cities carry it in 2020-24 (Palo Alto, Los Altos, Saratoga and others). The file keeps
the number and sets top_coded, and nothing may present 2000001 as a median - it means
"at least $2 million". Two 5-year releases overlap and are NOT a trend (the Census
Bureau: "Do not compare overlapping datasets"), so this is a level, never a growth.

  python scripts/build_bayarea_prices.py --fetch   download the summary file (~18 MB) into data/census/
  python scripts/build_bayarea_prices.py --write   write data/us-bayarea-prices.json from it
  python scripts/build_bayarea_prices.py --check   coverage of the 50 cities (offline); and, when the
                                                   summary file is on disk, every value against it
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
YEAR = 2024  # the 2020-2024 5-year release
TABLE = 'b25077'
URL = (f'https://www2.census.gov/programs-surveys/acs/summary_file/{YEAR}/table-based-SF/data/5YRData/'
       f'acsdt5y{YEAR}-{TABLE}.dat')
RAW = REPO / 'data' / 'census' / f'acsdt5y{YEAR}-{TABLE}.dat'
PLACES = REPO / 'data' / 'us-bayarea-places.json'
OUT = REPO / 'data' / 'us-bayarea-prices.json'
TOP_CODE = 2000001
KINDS = ('city', 'town')


def cities():
    with open(PLACES, encoding='utf-8') as fh:
        return [p for p in json.load(fh)['places'] if p['kind'] in KINDS]


def read_raw():
    """{7-digit place GEOID: (estimate, margin)} for California places."""
    out = {}
    with open(RAW, encoding='utf-8') as fh:
        head = fh.readline().rstrip('\n').split('|')
        if head[:3] != ['GEO_ID', 'B25077_E001', 'B25077_M001']:
            raise SystemExit(f'{RAW.name}: unexpected header {head[:3]}')
        for line in fh:
            gid, est, moe = line.rstrip('\n').split('|')[:3]
            if gid.startswith('1600000US06'):
                out[gid[9:]] = (est, moe)
    return out


def build():
    raw = read_raw()
    rows = []
    for p in cities():
        est, moe = raw.get(p['geoid'], (None, None))
        if est is None or not est.isdigit():
            raise SystemExit(f"{p['name']} ({p['geoid']}): no usable B25077 estimate ({est!r})")
        value = int(est)
        rows.append({'geoid': p['geoid'], 'name': p['name'], 'kind': p['kind'], 'county': p['county'],
                     'median_value_usd': value, 'margin_usd': int(moe) if moe.isdigit() else None,
                     'top_coded': value >= TOP_CODE})
    return {
        'source': 'US Census Bureau, American Community Survey 5-year estimates, table B25077 (median value, '
                  'owner-occupied housing units, dollars)',
        'vintage': f'{YEAR - 4}-{YEAR}',
        'url': URL,
        'licence': 'public domain (a US government work)',
        'generator': 'scripts/build_bayarea_prices.py --write',
        'top_code': f'{TOP_CODE} means "$2,000,000+": a floor, never a price (top_coded: true)',
        'not_a_trend': 'overlapping 5-year releases must not be compared (Census Bureau); this is a level only',
        'cities': rows,
    }


def check():
    failures = []
    with open(OUT, encoding='utf-8') as fh:
        doc = json.load(fh)
    want = {p['geoid'] for p in cities()}
    have = {r['geoid'] for r in doc['cities']}
    if have != want:
        failures.append(f'coverage: missing {sorted(want - have)}, extra {sorted(have - want)}')
    for r in doc['cities']:
        if r['top_coded'] != (r['median_value_usd'] >= TOP_CODE):
            failures.append(f"{r['name']}: top_coded flag disagrees with its value")
    print(f'coverage: {len(have & want)} of {len(want)} cities; {sum(r["top_coded"] for r in doc["cities"])} top-coded')
    if RAW.exists():
        fresh = build()['cities']
        diff = [a['name'] for a, b in zip(sorted(fresh, key=lambda r: r['geoid']),
                                          sorted(doc['cities'], key=lambda r: r['geoid']), strict=False) if a != b]
        print(f'against {RAW.name}: {len(fresh)} compared, {len(diff)} differ {diff}')
        if diff:
            failures.append(f'{len(diff)} cities differ from the summary file (re-run --write)')
    else:
        print(f'INCONCLUSIVE for values: {RAW.relative_to(REPO)} is not on disk (run --fetch); coverage checked')
    for f in failures:
        print('FAIL: ' + f)
    return 1 if failures else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--fetch', action='store_true')
    g.add_argument('--write', action='store_true')
    g.add_argument('--check', action='store_true')
    a = ap.parse_args()
    if a.fetch:
        RAW.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(URL, headers={'User-Agent': 'SkyScore/1.0 (support@skyscore.co.uk)'})
        with urllib.request.urlopen(req, timeout=120) as r:
            RAW.write_bytes(r.read())
        print(f'fetched {RAW.relative_to(REPO)} ({RAW.stat().st_size:,} bytes)')
        return 0
    if a.write:
        doc = build()
        with open(OUT, 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(doc, fh, indent=2)
            fh.write('\n')
        top = [r['name'] for r in doc['cities'] if r['top_coded']]
        print(f"wrote {OUT.relative_to(REPO)}: {len(doc['cities'])} cities, {len(top)} top-coded {top}")
        return 0
    return check()


if __name__ == '__main__':
    sys.exit(main())
