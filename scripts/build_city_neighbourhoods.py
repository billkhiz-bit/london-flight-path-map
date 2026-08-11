#!/usr/bin/env python3
"""Build a city's neighbourhood entries for the consumer-site ranking.

WHY THIS SCRIPT EXISTS RATHER THAN A HAND-WRITTEN TABLE.

London's and NYC's neighbourhood entries in `index.html` carry a curated
median price (LONDON_NEIGHBOURHOOD_DETAIL: `price`, in GBP thousands) and a
hand-assigned `crime` modifier on a -2..+1 scale. Those numbers are editorial.
Writing four hundred more of them by hand would repeat the defect this
project has already removed twice: the Ofsted school bands, which turned out
not to reproduce from any published threshold, and the prototype's invented
decibel readings at named locations.

So every number this emits is sourced or absent:

  price      MEDIAN of real HM Land Registry Price Paid transactions for the
             postcode district, over the vintage below. Not an estimate.
  lat/lon    MEAN of live postcode coordinates in that district, from the ONS
             National Statistics Postcode Lookup already on disk for the
             score Lambda's postcode table.
  borough    The Land Registry `district` field on the transactions themselves,
             checked against the city's boroughs in LAD_TO_BOROUGH.
  crime      0 for every entry, and NOT a measurement. There is no honest
             sub-borough crime source: ONS Table C4 publishes at Community
             Safety Partnership level, which for these cities is the
             borough. A modifier invented per neighbourhood would be exactly
             the editorial number this script exists to avoid. The site
             discloses this rather than printing a silent zero.

WHAT A "NEIGHBOURHOOD" IS HERE, STATED PLAINLY.

It is a POSTCODE DISTRICT (outward code: M20, BL1, SK4), labelled with the
Royal Mail locality that most transactions in it use. It is not a ward, not an
MSOA, and not a conservation-area boundary. METHODOLOGY's standing rule is to
say what a number is rather than dress a coarse figure as a fine one, so the
site labels these as postcode districts and names the source.

A district is DROPPED, not estimated, when it has fewer than MIN_SALES
transactions - a median drawn from four sales is noise wearing a statistic's
clothing. Every drop is printed, because a silent cap reads as full coverage.

SOURCES
  HM Land Registry Price Paid Data (bulk CSV, per calendar year)
    http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com/pp-<year>.csv
    Contains HM Land Registry data (C) Crown copyright and database right.
    Licensed under the Open Government Licence v3.0.
  ONS National Statistics Postcode Lookup (data/nspl.csv, already on disk)
    Contains OS data (C) Crown copyright and database right; Royal Mail data
    (C) Royal Mail copyright and database right; ONS data (C) Crown copyright.
    Open Government Licence v3.0.

GENERALISED 2026-08-11 from build_manchester_neighbourhoods.py. Greater
Manchester was the only generated city for two days; six more now use the same
path, which produced 448 districts across seven cities in one pass. Its output
for GM is byte-identical to the hand-run it replaced.

USAGE
    python scripts/build_city_neighbourhoods.py --write-index
    python scripts/build_city_neighbourhoods.py --city bristol --write-index
    python scripts/build_city_neighbourhoods.py --years 2025 2026 --min-sales 40

Writes data/<city>-neighbourhoods.json. Re-run when a new PPD year lands;
the output records its own vintage and the site prints it beside the figures,
because a median price with no date is unreadable and a stale one is worse
than none.
"""

import argparse
import csv
import json
import os
import re
import statistics
import sys
import urllib.request
from collections import defaultdict

PPD_URL = (
    'http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com/pp-{year}.csv'
)

# Boroughs come from the score Lambda's LAD_TO_BOROUGH, not from a table here.
#
# This replaced a hardcoded ten-entry GM_BOROUGHS dict when the script was
# generalised on 2026-08-11. A second copy of the borough list is the exact
# defect that took six cities off the map that morning - CITY_DATA held nine
# and a second registry held three - so the list is imported rather than
# retyped, and a city added to the Lambda is buildable here with no edit.
#
# Land Registry spells districts its own way in the `district` column, so the
# match is NORMALISED rather than exact. Measured against pp-2025 before being
# written: every borough of every city on the site matches, including
# `Westminster` -> `CITY OF WESTMINSTER`, `St Helens` -> `ST HELENS` and
# `City of Bristol` -> `CITY OF BRISTOL`. A borough that matches NOTHING is
# reported loudly by main() rather than quietly contributing no districts,
# because a silent miss reads as "this borough has no neighbourhoods".
def _norm_district(name):
    """Normalise a district name for matching across ONS and Land Registry."""
    import re

    s = (name or '').upper().replace('.', '').replace('-', ' ')
    s = re.sub(r'^THE\s+', '', s)
    s = re.sub(r'^(CITY OF|COUNTY OF)\s+', '', s)
    s = re.sub(r'\s+(CITY|DISTRICT|BOROUGH)$', '', s)
    return re.sub(r'\s+', ' ', s).strip()


def boroughs_for_city(city):
    """{normalised Land Registry district: our borough name} for one city."""
    import importlib.util

    path = os.path.join(REPO, 'backend', 'lambdas', 'score', 'app.py')
    spec = importlib.util.spec_from_file_location('score_app_nbhd', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = {}
    for _code, (city_id, borough) in module.LAD_TO_BOROUGH.items():
        if city_id == city:
            out[_norm_district(borough)] = borough
    if not out:
        sys.exit(f'no boroughs registered for city {city!r} in LAD_TO_BOROUGH')
    return out

# PPD column indices. The bulk CSV has no header row.
C_PRICE, C_DATE, C_POSTCODE, C_LOCALITY, C_TOWN, C_DISTRICT = 1, 2, 3, 10, 11, 12

# Display names for postal districts whose Royal Mail `locality` field is blank,
# so the fallback would be the post town and 17 different places would all read
# "Manchester".
#
# THIS IS A LABEL, NOT A MEASUREMENT, and the distinction is the whole reason
# it is allowed to be curated when `price` and `crime` are not. "M20 is
# Didsbury and Withington" is a checkable fact about postal geography; it does
# not enter any score, cannot move a ranking, and the outward code stays
# visible beside it so the label can never claim more precision than the data.
# A district is left as its post town where no single area name is widely
# recognised - most of the Bolton, Wigan, Oldham and Rochdale ones - because
# inventing a plausible-sounding name is the same failure as inventing a
# plausible-sounding number.
# Keyed by CITY. Only Greater Manchester has any, because GM was the only
# generated city when these were written. The other six are left to their Royal
# Mail locality: inventing a plausible-sounding area name is the same failure as
# inventing a plausible-sounding number, so an empty dict is the honest default
# rather than a gap waiting to be filled.
NAME_OVERRIDES_BY_CITY = {}
NAME_OVERRIDES_BY_CITY['manchester'] = {
    'M1': 'Manchester City Centre',
    'M3': 'Salford Central',
    'M4': 'Ancoats & Northern Quarter',
    'M5': 'Ordsall & Seedley',
    'M6': 'Pendleton',
    'M7': 'Broughton',
    'M8': 'Cheetham Hill & Crumpsall',
    'M9': 'Blackley & Harpurhey',
    'M11': 'Openshaw & Clayton',
    'M12': 'Ardwick & Longsight',
    'M13': 'Chorlton-on-Medlock',
    'M14': 'Fallowfield & Rusholme',
    'M15': 'Hulme',
    'M16': 'Whalley Range & Old Trafford',
    'M18': 'Gorton',
    'M19': 'Levenshulme & Burnage',
    'M20': 'Didsbury & Withington',
    'M21': 'Chorlton-cum-Hardy',
    'M22': 'Wythenshawe North',
    'M23': 'Wythenshawe South',
    'M40': 'Newton Heath & Moston',
    'M50': 'Salford Quays',
    'SK1': 'Stockport Town Centre',
    'SK3': 'Edgeley & Cheadle Heath',
    'SK4': 'The Heatons',
    'SK5': 'Reddish',
}

# A median under this many transactions is not reported. 30 is a judgement,
# stated rather than hidden: it keeps every district whose median moves less
# than ~5% when the highest and lowest sale are removed, checked on the 2025
# data at build time and printed in the summary.
DEFAULT_MIN_SALES = 30

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NSPL_PATH = os.path.join(REPO, 'data', 'nspl.csv')
OUT_PATH = os.path.join(REPO, 'data', 'manchester-neighbourhoods.json')
CACHE_DIR = os.path.join(REPO, 'data')


def outward(postcode):
    """'M20 2RN' -> 'M20'. Returns None for anything that is not a UK postcode."""
    pc = (postcode or '').strip().upper()
    if ' ' not in pc:
        return None
    out = pc.split(' ', 1)[0]
    return out if 2 <= len(out) <= 4 else None


def fetch_ppd(year, cache_dir):
    """Download pp-<year>.csv unless already cached. Returns the local path.

    Cached under data/, which is gitignored file-by-file, so these large files
    never enter the repo. That gitignore behaviour is the same one that kept
    manchester-boroughs.json out of git until it was un-ignored explicitly.
    """
    path = os.path.join(cache_dir, f'pp-{year}.csv')
    if os.path.exists(path) and os.path.getsize(path) > 1_000_000:
        print(f'  pp-{year}.csv cached ({os.path.getsize(path) / 1024 / 1024:.0f} MB)')
        return path
    url = PPD_URL.format(year=year)
    print(f'  downloading {url} ...')
    req = urllib.request.Request(url, headers={'User-Agent': 'sky-score-build/1.0'})
    tmp = path + '.part'
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, 'wb') as fh:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
    os.replace(tmp, path)
    print(f'  saved {os.path.getsize(path) / 1024 / 1024:.0f} MB')
    return path


def collect_sales(paths, borough_maps):
    """Stream the PPD CSVs once, bucketing rows by city.

    ONE pass for every city, not one per city. The bulk CSV is 162 MB and the
    NSPL scan below is 806 MB; doing both per city turned a three-minute build
    into a twenty-minute one when this went from Greater Manchester alone to
    seven cities. `borough_maps` is {city: {normalised district: borough}}.

    Returns {city: {outward: {'prices': [...], 'boroughs': {...}, 'localities': {...}}}}
    """
    lookup = {}
    for city, boroughs in borough_maps.items():
        for norm, borough in boroughs.items():
            # A district belongs to exactly one of our cities, so a collision
            # here is a registry error worth failing on rather than resolving
            # arbitrarily.
            if norm in lookup:
                sys.exit(f'district {norm!r} claimed by both {lookup[norm][0]} and {city}')
            lookup[norm] = (city, borough)

    per_city = {city: defaultdict(
        lambda: {'prices': [], 'boroughs': defaultdict(int), 'localities': defaultdict(int)}
    ) for city in borough_maps}
    seen = kept = 0
    for path in paths:
        with open(path, newline='', encoding='utf-8', errors='replace') as fh:
            for row in csv.reader(fh):
                seen += 1
                if len(row) <= C_DISTRICT:
                    continue
                hit = lookup.get(_norm_district(row[C_DISTRICT]))
                if not hit:
                    continue
                city, borough = hit
                out = outward(row[C_POSTCODE])
                if not out:
                    continue
                try:
                    price = int(row[C_PRICE])
                except (ValueError, TypeError):
                    continue
                if price <= 0:
                    continue
                rec = per_city[city][out]
                rec['prices'].append(price)
                rec['boroughs'][borough] += 1
                loc = (row[C_LOCALITY] or '').strip().title()
                town = (row[C_TOWN] or '').strip().title()
                name = loc or town
                if name:
                    rec['localities'][name] += 1
                kept += 1
    total = sum(len(v) for v in per_city.values())
    print(f'  scanned {seen:,} transactions, kept {kept:,} across {total} districts in {len(per_city)} cities')
    return per_city


def collect_centroids(wanted):
    """Mean lat/lon per outward code from NSPL, live postcodes only.

    NSPL is ~806 MB and is scanned once. `doterm` (date of termination) is
    non-empty for retired postcodes; including them would drag a centroid
    toward wherever the estate used to be.
    """
    if not os.path.exists(NSPL_PATH):
        sys.exit(
            f'NSPL not found at {NSPL_PATH}.\n'
            'It is gitignored and local-only. Without it there are no coordinates,\n'
            'and a neighbourhood with no lat/lon cannot be scored for quiet at all.'
        )
    sums = defaultdict(lambda: [0.0, 0.0, 0])
    with open(NSPL_PATH, newline='', encoding='utf-8', errors='replace') as fh:
        reader = csv.DictReader(fh)
        cols = {c.lower(): c for c in (reader.fieldnames or [])}
        c_pcds = cols.get('pcds') or cols.get('pcd')
        c_lat, c_long = cols.get('lat'), cols.get('long')
        c_term = cols.get('doterm')
        if not (c_pcds and c_lat and c_long):
            sys.exit(f'NSPL columns not as expected: {reader.fieldnames[:12]}')
        for row in reader:
            if c_term and (row.get(c_term) or '').strip():
                continue
            out = outward(row.get(c_pcds))
            if out not in wanted:
                continue
            try:
                lat, lon = float(row[c_lat]), float(row[c_long])
            except (ValueError, TypeError):
                continue
            # NSPL uses 99.999999 for postcodes with no grid reference.
            if lat > 90 or lat < 49:
                continue
            s = sums[out]
            s[0] += lat
            s[1] += lon
            s[2] += 1
    return {k: (v[0] / v[2], v[1] / v[2], v[2]) for k, v in sums.items() if v[2]}


INDEX_PATH = os.path.join(REPO, 'index.html')


def markers(city):
    """Marker pair delimiting one city's generated block in index.html.

    Uniform per city. Greater Manchester's were `GM-NEIGHBOURHOODS` while it was
    the only generated city; a one-off name is the kind of special case that
    bites the day a second city arrives, which is today.
    """
    tag = city.upper()
    return f'/* {tag}-NEIGHBOURHOODS:START */', f'/* {tag}-NEIGHBOURHOODS:END */'


def write_index(city, entries, payload):
    """Rewrite index.html between this city's NEIGHBOURHOODS markers.

    Inline rather than fetched, because London's and NYC's neighbourhood tables
    are inline too and a fourth network request on first paint is not worth
    ~11 KB. Marker-delimited so a rebuild cannot drift from the JSON: this is
    the file `data/*` gitignore taught us to distrust hand-syncing.
    """
    mark_start, mark_end = markers(city)
    prefix = city.upper()
    with open(INDEX_PATH, encoding='utf-8') as fh:
        src = fh.read()
    a, b = src.find(mark_start), src.find(mark_end)
    if a < 0 or b < 0:
        sys.exit(f'markers not found in index.html - expected {mark_start} ... {mark_end}')

    area, detail = {}, {}
    for label, e in entries.items():
        area[label] = {'code': e['outward'], 'lat': e['lat'], 'lon': e['lon'], 'borough': e['borough']}
        detail[label] = {
            'price': e['price'],
            'crime': e['crime'],
            'lat': e['lat'],
            'lon': e['lon'],
            'borough': e['borough'],
            'sales': e['sales'],
        }
    block = (
        f'{mark_start}\n'
        f'      // GENERATED by scripts/build_city_neighbourhoods.py - do not hand-edit.\n'
        f'      // {len(entries)} postcode districts. price = MEDIAN of real HM Land Registry\n'
        f'      // Price Paid transactions ({payload["priceVintage"]}), sales = how many that median rests on,\n'
        f'      // coordinates = mean of live ONS NSPL postcodes in the district.\n'
        f'      // crime is 0 for every entry and is NOT a measurement - sub-borough crime\n'
        f'      // is not published at this geography. renderGroup discloses this.\n'
        f'      const {prefix}_NEIGHBOURHOOD_VINTAGE = {json.dumps(payload["priceVintage"])};\n'
        f'      const {prefix}_NEIGHBOURHOOD_MIN_SALES = {payload["minSales"]};\n'
        f'      Object.assign({prefix}_AREA_MAP, {json.dumps(area, sort_keys=True)});\n'
        f'      Object.assign({prefix}_NEIGHBOURHOOD_DETAIL, {json.dumps(detail, sort_keys=True)});\n'
        f'      '
    )
    out = src[:a] + block + src[b:]
    with open(INDEX_PATH, 'w', encoding='utf-8', newline='') as fh:
        fh.write(out)
    return len(block)


def _cities_with_markers():
    """Every city index.html has a <CITY>-NEIGHBOURHOODS block for.

    DERIVED, not listed. This was a hardcoded list of seven, and on 2026-08-11
    Leicester and Teesside were added to index.html with markers in place and
    this script reported "448 neighbourhoods across 7 cities" - a confident
    success that had silently skipped both. The markers ARE the contract, since
    they are what --write-index rewrites between, so reading them cannot drift
    from the file being written.

    London and New York are absent by design: their neighbourhood tables are
    CURATED inline, not generated from Price Paid.
    """
    with open('index.html', encoding='utf-8') as fh:
        src = fh.read()
    return sorted(m.lower() for m in re.findall(r'([A-Z]+)-NEIGHBOURHOODS:START', src))


DEFAULT_CITIES = _cities_with_markers()


def build_city(city, keep_by_city, centroids, args):
    """Turn one city's kept districts into entries, JSON and an index block."""
    name_overrides = NAME_OVERRIDES_BY_CITY.get(city, {})
    entries = {}
    no_coords = []
    for out, rec in sorted(keep_by_city[city].items()):
        if out not in centroids:
            no_coords.append(out)
            continue
        lat, lon, pc_count = centroids[out]
        prices = rec['prices']
        borough = max(rec['boroughs'].items(), key=lambda kv: kv[1])[0]
        # Display name: a curated postal-district label where one is widely
        # recognised, else the Royal Mail locality most transactions use, else
        # the outward code itself rather than a name we invent.
        locality = max(rec['localities'].items(), key=lambda kv: kv[1])[0] if rec['localities'] else out
        label = f'{name_overrides.get(out, locality)} ({out})'
        entries[label] = {
            'outward': out,
            'borough': borough,
            'price': round(statistics.median(prices) / 1000),
            'sales': len(prices),
            'lat': round(lat, 5),
            'lon': round(lon, 5),
            'postcodes': pc_count,
            # Sub-borough crime is NOT SOURCED. Zero here means "no modifier
            # applied", never "average crime". The site says so.
            'crime': 0,
        }

    if no_coords:
        print(f'  {len(no_coords)} districts had sales but no NSPL coordinates: {", ".join(sorted(no_coords))}')

    payload = {
        'generatedBy': 'scripts/build_city_neighbourhoods.py',
        'city': city,
        'priceSource': 'HM Land Registry Price Paid Data',
        'priceVintage': ', '.join(str(y) for y in args.years),
        'priceBasis': 'median sale price per postcode district',
        'coordinateSource': 'ONS National Statistics Postcode Lookup (live postcodes, mean centroid)',
        'crimeSourced': False,
        'crimeNote': (
            'Sub-borough crime is not published at this geography; ONS Table C4 is '
            'Community Safety Partnership level, which here is the borough. No '
            'per-neighbourhood crime modifier is applied.'
        ),
        'minSales': args.min_sales,
        'licence': 'Open Government Licence v3.0',
        'neighbourhoods': entries,
    }
    out_path = os.path.join(REPO, 'data', f'{city}-neighbourhoods.json')
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, indent=1, sort_keys=False)
        fh.write('\n')
    print(f'  wrote {len(entries)} neighbourhoods to {os.path.basename(out_path)}')

    if args.write_index:
        n = write_index(city, entries, payload)
        print(f'  rewrote {n} bytes between the {city.upper()}-NEIGHBOURHOODS markers')

    # Every borough must contribute at least one district. A borough with none
    # is nearly always a district-name mismatch rather than a real absence, and
    # a silent miss reads as "this borough has no neighbourhoods".
    counts = defaultdict(int)
    for e in entries.values():
        counts[e['borough']] += 1
    expected = set(boroughs_for_city(city).values())
    missing = sorted(expected - set(counts))
    for b in sorted(counts):
        print(f'     {b:<28} {counts[b]}')
    if missing:
        print(f'  BOROUGHS WITH NO NEIGHBOURHOOD: {", ".join(missing)}')
    return len(entries), missing


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--years', nargs='+', type=int, default=[2025])
    ap.add_argument('--min-sales', type=int, default=DEFAULT_MIN_SALES)
    ap.add_argument('--city', help='one city key; default is every generated city')
    ap.add_argument(
        '--write-index',
        action='store_true',
        help="also rewrite index.html between each city's NEIGHBOURHOODS markers",
    )
    args = ap.parse_args()

    cities = [args.city] if args.city else list(DEFAULT_CITIES)
    print(f'Neighbourhoods from HM Land Registry Price Paid for: {", ".join(cities)}')
    print(f'  vintage: {", ".join(str(y) for y in args.years)}')

    borough_maps = {c: boroughs_for_city(c) for c in cities}
    paths = [fetch_ppd(y, CACHE_DIR) for y in args.years]
    per_city = collect_sales(paths, borough_maps)

    # Threshold BEFORE the NSPL scan, so we only look up coordinates we use.
    keep_by_city = {}
    wanted = set()
    for city in cities:
        keep, dropped = {}, []
        for out, rec in per_city[city].items():
            if len(rec['prices']) < args.min_sales:
                dropped.append((out, len(rec['prices'])))
                continue
            keep[out] = rec
        keep_by_city[city] = keep
        wanted |= set(keep)
        print(f'  {city}: {len(keep)} districts at or above {args.min_sales} sales; {len(dropped)} dropped')

    if not wanted:
        sys.exit('FAIL: no districts met the threshold for any city. Check the district names.')

    # ONE NSPL pass for every city. It is 806 MB.
    print('  scanning NSPL for coordinates (this is the slow part) ...')
    centroids = collect_centroids(wanted)

    total = 0
    any_missing = []
    for city in cities:
        print(f'\n{city}')
        n, missing = build_city(city, keep_by_city, centroids, args)
        total += n
        any_missing += [f'{city}.{b}' for b in missing]

    print(f'\n{total} neighbourhoods across {len(cities)} cities')
    if any_missing:
        print(f'BOROUGHS WITH NO NEIGHBOURHOOD: {", ".join(any_missing)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
