"""ZIP codes for the Bay Area: data/us-bayarea-zips.json.

    python scripts/build_bayarea_zips.py --fetch   # the three Census files (network), then write
    python scripts/build_bayarea_zips.py --write   # derive from the cached Census files
    python scripts/build_bayarea_zips.py --check   # is the file sane, and is it what the Census files derive?

WHY THIS EXISTS (2026-10-03)
----------------------------
Bill's ruling: the Bay Area joins the main map in two releases, and the first
includes ZIP search. A ZIP typed into the search has to become a place on the
map: a point to pin, and the city whose card to open. New York's ZIPs are a
hand-built table in two holders; this one is derived, and it is one file that
the new front page reads today and the score Lambda will read when the Bay
Area has an entry there.

THREE CENSUS FILES, ALL PUBLIC DOMAIN, ALL PLAIN DOWNLOADS (no API key)
----------------------------------------------------------------------
  - the ZCTA gazetteer: each ZIP area's internal point and land area;
  - the 2020 ZCTA-to-county relationship file: how much of each ZIP area's
    land lies in each county, which is what selects the four counties' ZIPs;
  - the 2020 ZCTA-to-place relationship file: how much lies in each city,
    which is what names the city a ZIP is in.

WHAT THE FILE SAYS, AND WHAT IT REFUSES TO SAY
----------------------------------------------
  - These are ZCTAs, the Census's map of ZIP delivery areas, not the Postal
    Service's ZIPs. A ZIP that is only PO boxes has no area and is not here.
  - A ZIP belongs to the county holding the LARGEST share of its land.
  - A ZIP is given the city or community that holds the most of its land,
    ALWAYS WITH that share, however small. The share is what stops the name
    over-claiming: 94301 is wholly Palo Alto, but 95014 is 44% Cupertino and
    94550 is 5% Livermore, because both reach far into empty hills, and the
    page words each accordingly. The first version named a city only at half
    or more, which told everyone in 95014 and 94550 that their ZIP was in no
    city at all. That rule is right for publishing a STATISTIC under a label
    (the UK's WA8 lesson) and wrong for finding the city a person means. No
    figure is ever published for a ZIP under a city's name; the name only
    opens that city's card.
  - Land in no city is a row of its own in the Census file and is never "the
    place". Only a place held in data/us-bayarea-places.json can be named,
    matched on the Census GEOID and never on the name.
  - The point is the ZIP AREA's internal point, not where its people live. In
    a hill ZIP it can sit in open country outside the city. A population
    centre would be better and needs block-level counts; not built.

`--check` re-derives the file whenever the (gitignored) Census files are on
disk. Without them it still checks the file against a SECOND source that is
always on disk: each ZIP's internal point is tested against the outline of
the city it is said to be in. A table that paired ZIPs with the wrong cities
would fail that, however well formed it was.
"""

import argparse
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from build_bay_area_page import CENSUS, COUNTIES, PLACES, UA  # noqa: E402

OUT = ROOT / 'data' / 'us-bayarea-zips.json'
GAZETTEER_YEAR = '2024'
GAZETTEER = f'{GAZETTEER_YEAR}_Gaz_zcta_national.zip'
REL_PLACE = 'tab20_zcta520_place20_natl.txt'
REL_COUNTY = 'tab20_zcta520_county20_natl.txt'
URLS = {
    GAZETTEER: f'https://www2.census.gov/geo/docs/maps-data/data/gazetteer/{GAZETTEER_YEAR}_Gazetteer/{GAZETTEER}',
    REL_PLACE: f'https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/{REL_PLACE}',
    REL_COUNTY: f'https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/{REL_COUNTY}',
}
STATE = '06'  # California
# Of the ZIPs said to be at least this much inside a city, the share whose
# internal point must fall inside that city's outline. Measured 2026-10-03: 93
# of 94; the floor leaves room for the outlines' 1:500,000 generalisation.
POINT_CHECK_SHARE = 0.9
POINT_CHECK_FLOOR = 0.97
# The four counties hold 165 ZIP areas (counted 2026-10-03 from the county
# relationship file: San Francisco 28, San Mateo 30, Santa Clara 58, Alameda
# 49; 173 touch them). The first version of this floor said "about 300" from
# memory and refused the real table. Far fewer than 165 means a file was read
# short or a column moved.
MIN_ZIPS = 150


def rows(lines):
    """Pipe-delimited relationship rows as dicts. The files open with a BOM."""
    head = None
    for line in lines:
        cells = line.rstrip('\r\n').lstrip('﻿').split('|')
        if head is None:
            head = cells
            continue
        if len(cells) == len(head):
            yield dict(zip(head, cells, strict=True))


def gazetteer_points(lines):
    """{zcta: (lat, lon)} from the tab-separated gazetteer, whose last column is padded with spaces."""
    out = {}
    head = None
    for line in lines:
        cells = [c.strip() for c in line.rstrip('\r\n').split('\t')]
        if head is None:
            head = cells
            continue
        # Not strict: a short or padded row simply lacks the keys tested below.
        rec = dict(zip(head, cells, strict=False))
        if rec.get('GEOID') and rec.get('INTPTLAT') and rec.get('INTPTLONG'):
            out[rec['GEOID']] = (float(rec['INTPTLAT']), float(rec['INTPTLONG']))
    return out


def derive(gazetteer_lines, county_lines, place_lines, places):
    """The ZIP table, from the three Census files and the places the map holds."""
    points = gazetteer_points(gazetteer_lines)
    held = {p['geoid']: p['name'] for p in places}
    county_fips = {STATE + fips: name for fips, (name, _count) in COUNTIES.items()}

    # The county holding most of each ZIP's land.
    best_county = {}
    for r in county_lines:
        z, part = r['GEOID_ZCTA5_20'], int(r['AREALAND_PART'] or 0)
        if not z:
            continue
        if z not in best_county or part > best_county[z][1]:
            best_county[z] = (r['GEOID_COUNTY_20'], part)
    ours = {z: county_fips[c] for z, (c, _part) in best_county.items() if c in county_fips}

    # The HELD place with the most of each ZIP's land, against the ZIP's whole
    # land area. A row with no place GEOID is the land in no city, and a place
    # we do not hold (another county's) cannot be named either.
    land, best_place = {}, {}
    for r in place_lines:
        z = r['GEOID_ZCTA5_20']
        if z not in ours:
            continue
        land[z] = int(r['AREALAND_ZCTA5_20'] or 0)
        part = int(r['AREALAND_PART'] or 0)
        if r['GEOID_PLACE_20'] not in held:
            continue
        if z not in best_place or part > best_place[z][1]:
            best_place[z] = (r['GEOID_PLACE_20'], part)

    zips = {}
    for z in sorted(ours):
        if z not in points:
            continue
        lat, lon = points[z]
        place, share = None, None
        geoid, part = best_place.get(z, ('', 0))
        # Rounded to 2dp for the page; a sliver that rounds to nothing names no place.
        if land.get(z) and geoid in held and round(part / land[z], 2) > 0:
            place, share = held[geoid], round(part / land[z], 2)
        zips[z] = {'lat': round(lat, 5), 'lon': round(lon, 5), 'county': ours[z], 'place': place, 'share': share}
    return zips


def document(zips):
    return {
        'source': (f'US Census Bureau: {GAZETTEER_YEAR} ZCTA gazetteer (internal points) and the 2020 '
                   'ZCTA-to-county and ZCTA-to-place relationship files, public domain'),
        'note': ('ZIP Code Tabulation Areas, the Census map of ZIP delivery areas. place is the held city or '
                 'community with the most of the area\'s land and share is that fraction, however small. '
                 'lat and lon are the area\'s internal point, which in a hill ZIP can lie outside the city.'),
        'generator': 'scripts/build_bayarea_zips.py --fetch',
        'zips': zips,
    }


def cached():
    return all((CENSUS / name).exists() for name in URLS)


def derive_from_cache():
    places = json.loads(PLACES.read_text(encoding='utf-8'))['places']
    with zipfile.ZipFile(CENSUS / GAZETTEER) as z:
        with z.open(z.namelist()[0]) as fh:
            gaz = list(io.TextIOWrapper(fh, encoding='utf-8'))
    with open(CENSUS / REL_COUNTY, encoding='utf-8') as fh:
        county = list(rows(fh))
    with open(CENSUS / REL_PLACE, encoding='utf-8') as fh:
        place = list(rows(fh))
    return derive(gaz, county, place, places)


def fetch():
    CENSUS.mkdir(parents=True, exist_ok=True)
    for name, url in URLS.items():
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=120) as res:  # noqa: S310 - fixed https Census URLs
            (CENSUS / name).write_bytes(res.read())
        print(f'fetched {name}')


def write():
    if not cached():
        print('The Census files are not in data/census/. Run --fetch.', file=sys.stderr)
        return 2
    zips = derive_from_cache()
    problems, _points = sanity(zips)
    if problems:
        print('\n'.join(problems), file=sys.stderr)
        return 1
    OUT.write_text(json.dumps(document(zips), separators=(',', ':'), ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    named = sum(1 for v in zips.values() if v['place'])
    print(f'wrote {OUT.relative_to(ROOT)}: {len(zips)} ZIP areas, {named} with a city named')
    return 0


def inside(lat, lon, rings):
    """Even-odd point-in-polygon over every ring of a place (holes and islands alike)."""
    hit = False
    for ring in rings:
        j = len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                hit = not hit
            j = i
    return hit


def sanity(zips):
    """What must hold of the table whether or not the Census files are on disk."""
    places = {p['name']: p for p in json.loads(PLACES.read_text(encoding='utf-8'))['places']}
    counties = {name for name, _count in COUNTIES.values()}
    problems = []
    if len(zips) < MIN_ZIPS:
        problems.append(f'only {len(zips)} ZIP areas; the four counties hold 165 (floor {MIN_ZIPS})')
    tested = agree = 0
    for z, v in zips.items():
        if not (len(z) == 5 and z.isdigit()):
            problems.append(f'{z}: not a five-digit ZIP')
        if v['county'] not in counties:
            problems.append(f'{z}: county {v["county"]!r} is not one of the four')
        if (v['place'] is None) != (v['share'] is None):
            problems.append(f'{z}: a place and its share must both be given or both be absent')
        if v['place'] is None:
            continue
        if v['place'] not in places:
            problems.append(f'{z}: place {v["place"]!r} is not in {PLACES.name}')
            continue
        if not 0 < v['share'] <= 1:
            problems.append(f'{z}: share {v["share"]} is not a fraction above zero')
        if v['share'] >= POINT_CHECK_SHARE:
            tested += 1
            agree += inside(v['lat'], v['lon'], places[v['place']]['rings'])
    if tested == 0:
        problems.append('no ZIP was tested against its city outline: the cross-check compared nothing')
    elif agree / tested < POINT_CHECK_FLOOR:
        problems.append(f'only {agree} of {tested} ZIP centre points fall inside the city they are said to be in '
                        f'(floor {POINT_CHECK_FLOOR:.0%}): the pairing with the outlines is wrong')
    return problems, (agree, tested)


def check():
    if not OUT.exists():
        print(f'FAIL: {OUT.relative_to(ROOT)} does not exist. Run --fetch.')
        return 1
    doc = json.loads(OUT.read_text(encoding='utf-8'))
    problems, (agree, tested) = sanity(doc['zips'])
    if problems:
        print('FAIL:\n  ' + '\n  '.join(problems))
        return 1
    named = sum(1 for v in doc['zips'].values() if v['place'])
    print(f'{len(doc["zips"])} ZIP areas, {named} with a city named; '
          f'{agree} of {tested} centre points fall inside the city they are said to be in')
    if not cached():
        print('PASS (structure and outlines only: the Census files are not in data/census/, so nothing was re-derived)')
        return 0
    derived = derive_from_cache()
    if derived != doc['zips']:
        changed = sorted(z for z in set(derived) | set(doc['zips']) if derived.get(z) != doc['zips'].get(z))
        print(f'FAIL: the file is not what the Census files derive; {len(changed)} ZIPs differ, e.g. {changed[:5]}. Run --write.')
        return 1
    print('PASS: the file is what the Census files derive')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--fetch', action='store_true', help='download the three Census files, then write')
    ap.add_argument('--write', action='store_true', help='derive the table from the cached Census files')
    ap.add_argument('--check', action='store_true', help='fail if the table is unsound or is not what the files derive')
    args = ap.parse_args()
    if args.fetch:
        fetch()
        return write()
    if args.write:
        return write()
    if args.check:
        return check()
    ap.print_help()
    return 2


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.exit(main())
