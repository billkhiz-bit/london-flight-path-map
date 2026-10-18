"""Where the Bay Area's residents live: 2020 Census blocks, for the flood and road-noise shares (2026-10-18).

The UK's flood and road-noise inputs are shares of a borough's live POSTCODES (build_borough_bands.py),
so a share of where people live, not of land. The US analogue is the 2020 Census block (an urban block
holds about as many people as a postcode): each block's internal point, weighted by its 2020
population, in the city the Census Bureau itself places it in, never by testing the point against the
simplified outlines (a bounding box, or a 1:500,000 ring, is not containment). Blocks with no residents
are left out: a share is a share of people.

The source is the geographic header of California's 2020 redistricting file (PL 94-171), which carries
each block's population, internal point and place code in one row. It has no header line, so fields are
read by position; --check holds those positions against an independent file, the Block Assignment File.

  python scripts/bayarea_blocks.py --fetch   the PL file (~80 MB) and the assignment file (~11 MB)
                                             into gitignored data/census/
  python scripts/bayarea_blocks.py --check   every block's place code agrees with the assignment file,
                                             and each city's residents match its 2020 estimates base
"""

import argparse
import csv
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PL_URL = ('https://www2.census.gov/programs-surveys/decennial/2020/data/01-Redistricting_File--PL_94-171/'
          'California/ca2020.pl.zip')
BAF_URL = 'https://www2.census.gov/geo/docs/maps-data/data/baf2020/BlockAssign_ST06_CA.zip'
PL_RAW = REPO / 'data' / 'census' / 'ca2020.pl.zip'
BAF_RAW = REPO / 'data' / 'census' / 'BlockAssign_ST06_CA.zip'
POP_RAW = REPO / 'data' / 'census' / 'sub-est2025_6.csv'
PLACES = REPO / 'data' / 'us-bayarea-places.json'
KINDS = ('city', 'town')
# 0-based positions in the 2020 PL geographic header (97 pipe-separated fields, no header line)
SUMLEV, GEOCODE, PLACE, POP100, INTPTLAT, INTPTLON = 2, 9, 29, 90, 92, 93
BLOCK_SUMLEV = '750'


def cities():
    with open(PLACES, encoding='utf-8') as fh:
        return [p for p in json.load(fh)['places'] if p['kind'] in KINDS]


def pl_blocks():
    """Every California block: (block GEOID, place GEOID or None, population, lon, lat)."""
    with zipfile.ZipFile(PL_RAW) as z, z.open('cageo2020.pl') as fh:
        for raw in fh:
            f = raw.decode('latin-1').rstrip('\r\n').split('|')
            if f[SUMLEV] != BLOCK_SUMLEV:
                continue
            if len(f) != 97 or f[GEOCODE][:2] != '06':
                raise SystemExit(f'{PL_RAW.name}: a block row of {len(f)} fields; the header layout changed')
            place = None if f[PLACE] == '99999' else '06' + f[PLACE]
            yield f[GEOCODE], place, int(f[POP100]), float(f[INTPTLON]), float(f[INTPTLAT])


def blocks():
    """{place GEOID: [(lon, lat, population), ...]} for the 50 cities, residents' blocks only."""
    out = {p['geoid']: [] for p in cities()}
    for _, place, pop, lon, lat in pl_blocks():
        if place in out and pop > 0:
            out[place].append((lon, lat, pop))
    return out


def check():
    missing = [p.name for p in (PL_RAW, BAF_RAW, POP_RAW) if not p.exists()]
    if missing:
        print(f'INCONCLUSIVE: {missing} not on disk (gitignored; run --fetch); nothing to check the frame against')
        return 0
    with zipfile.ZipFile(BAF_RAW) as z:
        baf = dict(line.split('|') for line in
                   z.read('BlockAssign_ST06_CA_INCPLACE_CDP.txt').decode('ascii').splitlines()[1:])
    want = {p['geoid']: p['name'] for p in cities()}
    people, disagree, n = dict.fromkeys(want, 0), [], 0
    for block, place, pop, _, _ in pl_blocks():
        n += 1
        if (place or '').removeprefix('06') != ('' if place is None else baf.get(block, '')) and \
                (place in want or ('06' + baf.get(block, 'x')) in want):
            disagree.append(block)
        if place in want:
            people[place] += pop
    base = {}
    with open(POP_RAW, encoding='latin-1', newline='') as fh:
        for r in csv.DictReader(fh):
            if r['SUMLEV'] == '162':
                base['06' + r['PLACE']] = int(r['ESTIMATESBASE2020'])
    failures = [f'{len(disagree)} blocks are placed differently by the PL header and the assignment file, '
                f'e.g. {disagree[:3]}'] if disagree else []
    # The base is the census count after the Bureau's later corrections (count question resolution), so
    # it differs by tens of people: 1% or 50, whichever is larger (Colma: 1,507 counted, base 1,469).
    for g, name in want.items():
        b = base.get(g)
        if not people[g] or not b or abs(people[g] - b) > max(0.01 * b, 50):
            failures.append(f'{name}: {people[g]:,} residents in its blocks, its 2020 estimates base is {b}')
    print(f'{n:,} California blocks read; {sum(people.values()):,} residents in the {len(want)} cities')
    for f in failures:
        print('FAIL: ' + f)
    print('RESULT: ' + ('FAIL' if failures else 'PASS'))
    return 1 if failures else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--fetch', action='store_true')
    g.add_argument('--check', action='store_true')
    a = ap.parse_args()
    if a.fetch:
        for url, raw in ((PL_URL, PL_RAW), (BAF_URL, BAF_RAW)):
            raw.parent.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(url, headers={'User-Agent': 'SkyScore/1.0 (support@skyscore.co.uk)'})
            with urllib.request.urlopen(req, timeout=600) as resp:  # noqa: S310 - fixed https URLs
                raw.write_bytes(resp.read())
            print(f'fetched {raw.relative_to(REPO)} ({raw.stat().st_size:,} bytes)')
        return 0
    return check()


if __name__ == '__main__':
    sys.exit(main())
