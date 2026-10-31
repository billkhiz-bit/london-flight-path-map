"""ZIP codes for the Bay Area: data/us-bayarea-zips.json, and the score Lambda's BAYAREA_ZIPS table.

    python scripts/build_bayarea_zips.py --fetch   # the Census files (network), then write
    python scripts/build_bayarea_zips.py --write   # derive from the cached Census files, write both holders
    python scripts/build_bayarea_zips.py --check   # are both holders sane, equal, and what the files derive?

WHY THIS EXISTS (2026-10-03)
----------------------------
Bill's ruling: the Bay Area joins the main map in two releases, and the first
includes ZIP search. A ZIP typed into the search has to become a place on the
map: a point to pin, and the city whose card to open. New York's ZIPs are a
hand-built table in two holders; this one is derived, and ONE builder writes
both holders: the file the front page and the full map read, and the table the
score Lambda reads (between BAYAREA-ZIPS markers in its app.py).

A ZIP IS NAMED BY WHERE ITS RESIDENTS LIVE (2026-10-23, Bill)
-------------------------------------------------------------
The first rule named the city holding the most of a ZIP's LAND. Land is where
the hills are: 94010 went to Hillsborough though 71% of its residents live in
Burlingame, 95014 read "44% Cupertino" though 96% of its people do, and 7 of
the 50 cities held no ZIP's majority. A score is about where people live, so
the rule is now RESIDENTS, from the 2020 Census at its finest grain: every
California block's population and the place the Census puts it in (the
redistricting file, PL 94-171, read by bayarea_blocks.pl_blocks()), joined to
the ZIP area that block belongs to (the 2020 ZCTA-to-block relationship file,
streamed to California's rows: 14 Bay Area ZIPs reach into six other counties,
so a four-county file would undercount their residents).

Bill's two calls, the same day:
  - A ZIP is SCORED AS A CITY when half or more of its residents live in one
    of the 50 cities (cityMajority), and the response says so, with the shares
    of the next places ("94010: 71% of residents in Burlingame, 26%
    Hillsborough"). Under half, or a majority in an unincorporated community,
    names no city: the API answers 404 with the places and shares, and the
    site opens the ZIP's own card.
  - ONE RULE FOR THE SITE AND THE API: both read this builder's output, so they
    can only disagree if a holder is hand-edited, which --check refuses.

WHAT THE FILE SAYS, AND WHAT IT REFUSES TO SAY
----------------------------------------------
  - These are ZCTAs, the Census's map of ZIP delivery areas, not the Postal
    Service's ZIPs. A ZIP that is only PO boxes has no area and is not here.
  - A ZIP belongs to the county holding the LARGEST share of its LAND (where it
    is on the map); 165 ZIPs fall in the four counties.
  - place is the held place (city, town or census-designated community) where
    the most of the ZIP's residents live, with that share, kind, and the next
    two held places at 1% or more. Residents in no held place are never "the
    place". A ZIP with no residents names nothing.
  - The point is the ZIP AREA's internal point (the gazetteer's), where the map
    puts the pin. In a hill ZIP it can sit in open country outside the city.

`--check` re-derives both holders whenever the (gitignored) Census files are on
disk. Without them it still checks the file against a SECOND source that is
always on disk: each majority ZIP's internal point is tested against the outline
of the city it is said to be in. It always checks the Lambda's table against
the file, so neither holder can be edited alone.
"""

import argparse
import io
import json
import re
import sys
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from bayarea_blocks import PL_RAW, pl_blocks  # noqa: E402
from build_bay_area_page import CENSUS, COUNTIES, PLACES, UA  # noqa: E402

OUT = ROOT / 'data' / 'us-bayarea-zips.json'
LAMBDA = ROOT / 'backend' / 'lambdas' / 'score' / 'app.py'
BEGIN = '# BAYAREA-ZIPS:BEGIN (scripts/build_bayarea_zips.py --write; never edit by hand)'
END = '# BAYAREA-ZIPS:END'
GAZETTEER_YEAR = '2024'
GAZETTEER = f'{GAZETTEER_YEAR}_Gaz_zcta_national.zip'
REL_COUNTY = 'tab20_zcta520_county20_natl.txt'
REL_BLOCK = 'tab20_zcta520_tabblock20_ca.txt'  # California's rows of the national file (1.06 GB)
URLS = {
    GAZETTEER: f'https://www2.census.gov/geo/docs/maps-data/data/gazetteer/{GAZETTEER_YEAR}_Gazetteer/{GAZETTEER}',
    REL_COUNTY: f'https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/{REL_COUNTY}',
}
REL_BLOCK_URL = 'https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_tabblock20_natl.txt'
STATE = '06'  # California
SCORED_KINDS = ('city', 'town')  # the 50 cities; a census-designated community is named, never scored
MAJORITY = 0.5  # half or more of the residents (Bill, 2026-10-23)
OTHERS = 2  # the next places a ZIP names, at 1% or more
# Of the majority ZIPs at least this much in one city, the share whose internal
# point is NOT inside ANOTHER city's outline. The point is the ZIP AREA's, not
# its residents', so a hill ZIP's point sits in open country (11 of 126 on
# 2026-10-23: Livermore's, Cupertino's and San Jose's hills, SFO's own ZIP):
# that is the caveat above, not a wrong pairing. A wrong pairing puts the point
# in another city, which happened once (94304, Stanford Research Park, its centre
# in Los Altos Hills, 93% of its residents in Palo Alto): 125 of 126.
POINT_CHECK_SHARE = 0.9
POINT_CHECK_FLOOR = 0.97
# The four counties hold 165 ZIP areas (counted 2026-10-03 from the county
# relationship file: San Francisco 28, San Mateo 30, Santa Clara 58, Alameda
# 49; 173 touch them). Far fewer means a file was read short or a column moved.
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


def block_residents(block_rel_rows, pl_rows):
    """{zcta: Counter({place GEOID or None: residents})}: each block's 2020 population, in the place the Census puts
    it, added to the ZIP area the block belongs to. A block in no ZIP area (5 populated ones in the four counties)
    counts nowhere."""
    zcta_of = {r['GEOID_TABBLOCK_20']: r['GEOID_ZCTA5_20'] for r in block_rel_rows if r['GEOID_ZCTA5_20']}
    out = defaultdict(Counter)
    for block, place, pop, _lon, _lat in pl_rows:
        z = zcta_of.get(block)
        if z and pop > 0:
            out[z][place] += pop
    return out


def derive(gazetteer_lines, county_lines, residents, places):
    """The ZIP table, from the gazetteer, the county file, each ZIP's residents by place, and the held places."""
    points = gazetteer_points(gazetteer_lines)
    held = {p['geoid']: (p['name'], p['kind']) for p in places}
    county_fips = {STATE + fips: name for fips, (name, _count) in COUNTIES.items()}

    # The county holding most of each ZIP's land: where the ZIP is on the map.
    best_county = {}
    for r in county_lines:
        z, part = r['GEOID_ZCTA5_20'], int(r['AREALAND_PART'] or 0)
        if not z:
            continue
        if z not in best_county or part > best_county[z][1]:
            best_county[z] = (r['GEOID_COUNTY_20'], part)
    ours = {z: county_fips[c] for z, (c, _part) in best_county.items() if c in county_fips}

    zips = {}
    for z in sorted(ours):
        if z not in points:
            continue
        lat, lon = points[z]
        people = residents.get(z, Counter())
        total = sum(people.values())
        # Residents in a place we hold, largest first; those in no held place are never "the place".
        ranked = sorted(((g, n) for g, n in people.items() if g in held), key=lambda gn: (-gn[1], gn[0]))
        rec = {'lat': round(lat, 5), 'lon': round(lon, 5), 'county': ours[z], 'residents': total,
               'place': None, 'kind': None, 'share': None, 'others': [], 'cityMajority': False}
        if total and ranked and round(ranked[0][1] / total, 2) > 0:
            g, n = ranked[0]
            name, kind = held[g]
            rec.update(
                place=name, kind=kind, share=round(n / total, 2),
                others=[[held[g2][0], round(n2 / total, 2)] for g2, n2 in ranked[1:1 + OTHERS] if round(n2 / total, 2) >= 0.01],
                # The exact ratio, not the rounded share: 0.496 is not a majority though it prints as 50%.
                cityMajority=kind in SCORED_KINDS and n / total >= MAJORITY,
            )
        zips[z] = rec
    return zips


def render_lambda(zips):
    """The Lambda's table: {zip: (place, kind, share, cityMajority, ((other, share), ...))}, one ZIP a line."""
    lines = [BEGIN, '# Bill, 2026-10-23: a ZIP is scored as a city when half or more of its 2020 residents live in it;',
             '# the shares are said in the response. Derived from the 2020 Census blocks; data/us-bayarea-zips.json.',
             'BAYAREA_ZIPS = {']
    for z, v in sorted(zips.items()):
        others = tuple((name, share) for name, share in v['others'])
        lines.append(f'    {z!r}: ({v["place"]!r}, {v["kind"]!r}, {v["share"]!r}, {v["cityMajority"]!r}, {others!r}),')
    lines += ['}', END]
    return '\n'.join(lines)


def document(zips):
    return {
        'source': (f'US Census Bureau, public domain: {GAZETTEER_YEAR} ZCTA gazetteer (internal points), the 2020 '
                   'ZCTA-to-county relationship file (the county), and 2020 residents by block (PL 94-171) joined '
                   'to the 2020 ZCTA-to-block relationship file (the place)'),
        'note': ('ZIP Code Tabulation Areas, the Census map of ZIP delivery areas. place is the held city, town or '
                 'community where the most of the ZIP\'s 2020 residents live, share is that fraction, others the '
                 'next places; cityMajority is true when half or more live in one of the 50 cities, and only then '
                 'is the ZIP scored as that city (Bill, 2026-10-23). lat and lon are the ZIP area\'s internal point.'),
        'generator': 'scripts/build_bayarea_zips.py --fetch',
        'zips': zips,
    }


def cached():
    return all((CENSUS / name).exists() for name in (*URLS, REL_BLOCK)) and PL_RAW.exists()


def derive_from_cache():
    places = json.loads(PLACES.read_text(encoding='utf-8'))['places']
    with zipfile.ZipFile(CENSUS / GAZETTEER) as z:
        with z.open(z.namelist()[0]) as fh:
            gaz = list(io.TextIOWrapper(fh, encoding='utf-8'))
    with open(CENSUS / REL_COUNTY, encoding='utf-8') as fh:
        county = list(rows(fh))
    with open(CENSUS / REL_BLOCK, encoding='utf-8') as fh:
        residents = block_residents(rows(fh), pl_blocks())
    return derive(gaz, county, residents, places)


def fetch():
    CENSUS.mkdir(parents=True, exist_ok=True)
    for name, url in URLS.items():
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=120) as res:  # noqa: S310 - fixed https Census URLs
            (CENSUS / name).write_bytes(res.read())
        print(f'fetched {name}')
    # The national block file is 1.06 GB: streamed, and only California's rows kept.
    part = CENSUS / (REL_BLOCK + '.part')
    kept = 0
    req = urllib.request.Request(REL_BLOCK_URL, headers=UA)
    with urllib.request.urlopen(req, timeout=600) as res, open(part, 'w', encoding='utf-8', newline='\n') as out:  # noqa: S310
        head = res.readline().decode('utf-8-sig').rstrip('\r\n')
        col = head.split('|').index('GEOID_TABBLOCK_20')
        out.write(head + '\n')
        for raw in res:
            line = raw.decode('utf-8').rstrip('\r\n')
            cells = line.split('|')
            if len(cells) > col and cells[col].startswith(STATE):
                out.write(line + '\n')
                kept += 1
    part.replace(CENSUS / REL_BLOCK)
    print(f'fetched {REL_BLOCK}: {kept:,} California block rows')
    if not PL_RAW.exists():
        print('The 2020 redistricting file is not on disk: run python scripts/bayarea_blocks.py --fetch', file=sys.stderr)


def lambda_block_now():
    """The table as the Lambda holds it now, or None when its markers are missing."""
    src = LAMBDA.read_text(encoding='utf-8')
    m = re.search(re.escape(BEGIN) + r'.*?' + re.escape(END), src, re.S)
    return m.group(0) if m else None


def write_lambda(zips):
    src = LAMBDA.read_text(encoding='utf-8')
    if lambda_block_now() is None:
        print(f'{LAMBDA.relative_to(ROOT)} has no BAYAREA-ZIPS markers', file=sys.stderr)
        return False
    new = re.sub(re.escape(BEGIN) + r'.*?' + re.escape(END), lambda _m: render_lambda(zips), src, count=1, flags=re.S)
    LAMBDA.write_bytes(new.encode('utf-8'))
    return True


def write():
    if not cached():
        print('The Census files are not in data/census/. Run --fetch (and bayarea_blocks.py --fetch).', file=sys.stderr)
        return 2
    zips = derive_from_cache()
    problems, _points = sanity(zips)
    if problems:
        print('\n'.join(problems), file=sys.stderr)
        return 1
    OUT.write_text(json.dumps(document(zips), separators=(',', ':'), ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    if not write_lambda(zips):
        return 1
    scored = sum(1 for v in zips.values() if v['cityMajority'])
    print(f'wrote {OUT.relative_to(ROOT)} and the Lambda table: {len(zips)} ZIP areas, {scored} scored as a city')
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
        missing = {'residents', 'kind', 'others', 'cityMajority'} - set(v)
        if missing:
            problems.append(f'{z}: no {sorted(missing)}: the file predates the residents rule. Run --write.')
            continue
        if not (len(z) == 5 and z.isdigit()):
            problems.append(f'{z}: not a five-digit ZIP')
        if v['county'] not in counties:
            problems.append(f'{z}: county {v["county"]!r} is not one of the four')
        if not isinstance(v['residents'], int) or v['residents'] < 0:
            problems.append(f'{z}: residents {v["residents"]!r} is not a count')
        if len({v['place'] is None, v['kind'] is None, v['share'] is None}) != 1:
            problems.append(f'{z}: a place, its kind and its share must all be given or all be absent')
        if v['place'] is None:
            if v['others'] or v['cityMajority']:
                problems.append(f'{z}: names no place, yet has others or a city majority')
            continue
        if v['place'] not in places or places[v['place']]['kind'] != v['kind']:
            problems.append(f'{z}: place {v["place"]!r} ({v["kind"]}) is not a held place of that kind')
            continue
        if not 0 < v['share'] <= 1:
            problems.append(f'{z}: share {v["share"]} is not a fraction above zero')
        if any(name not in places or not 0 < s <= v['share'] for name, s in v['others']):
            problems.append(f'{z}: others {v["others"]} are not held places with smaller shares')
        if v['share'] + sum(s for _n, s in v['others']) > 1.02:
            problems.append(f'{z}: the shares add up to more than the whole ZIP')
        if v['cityMajority'] and not (v['kind'] in SCORED_KINDS and v['share'] >= MAJORITY):
            problems.append(f'{z}: a city majority for {v["place"]} ({v["kind"]}, {v["share"]}) is not one')
        if v['cityMajority'] and v['share'] >= POINT_CHECK_SHARE:
            tested += 1
            other = [n for n, p in places.items()
                     if p['kind'] in SCORED_KINDS and n != v['place'] and inside(v['lat'], v['lon'], p['rings'])]
            agree += not other
    if tested == 0:
        problems.append('no ZIP was tested against its city outline: the cross-check compared nothing')
    elif agree / tested < POINT_CHECK_FLOOR:
        problems.append(f'{tested - agree} of {tested} majority ZIPs have their centre point inside ANOTHER city '
                        f'(floor {POINT_CHECK_FLOOR:.0%} not): the pairing with the outlines is wrong')
    return problems, (agree, tested)


def check():
    if not OUT.exists():
        print(f'FAIL: {OUT.relative_to(ROOT)} does not exist. Run --fetch.')
        return 1
    doc = json.loads(OUT.read_text(encoding='utf-8'))
    problems, (agree, tested) = sanity(doc['zips'])
    held = lambda_block_now()
    if held is None:
        problems.append(f'{LAMBDA.relative_to(ROOT)} has no BAYAREA-ZIPS markers')
    elif not problems and held != render_lambda(doc['zips']):  # an unsound file is reported above, never rendered
        problems.append('the Lambda\'s BAYAREA_ZIPS is not what the file says: the two holders disagree. Run --write.')
    if problems:
        print('FAIL:\n  ' + '\n  '.join(problems))
        return 1
    scored = sum(1 for v in doc['zips'].values() if v['cityMajority'])
    print(f'{len(doc["zips"])} ZIP areas, {scored} scored as a city; the Lambda table agrees; '
          f'{agree} of {tested} majority centre points lie in their city or in open country, not in another city')
    if not cached():
        print('PASS (structure, outlines and the two holders only: the Census files are not in data/census/, so '
              'nothing was re-derived)')
        return 0
    derived = derive_from_cache()
    if derived != doc['zips']:
        changed = sorted(z for z in set(derived) | set(doc['zips']) if derived.get(z) != doc['zips'].get(z))
        print(f'FAIL: the file is not what the Census files derive; {len(changed)} ZIPs differ, e.g. {changed[:5]}. Run --write.')
        return 1
    print('PASS: both holders are what the Census files derive')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--fetch', action='store_true', help='download the Census files, then write')
    ap.add_argument('--write', action='store_true', help='derive both holders from the cached Census files')
    ap.add_argument('--check', action='store_true', help='fail if a holder is unsound, they disagree, or the files derive otherwise')
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
