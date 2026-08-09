#!/usr/bin/env python3
"""Build Greater Manchester neighbourhood entries for the consumer-site ranking.

WHY THIS SCRIPT EXISTS RATHER THAN A HAND-WRITTEN TABLE.

London's and NYC's neighbourhood entries in `index.html` carry a curated
median price (LONDON_NEIGHBOURHOOD_DETAIL: `price`, in GBP thousands) and a
hand-assigned `crime` modifier on a -2..+1 scale. Those numbers are editorial.
Writing forty more of them for Greater Manchester would repeat the defect this
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
             checked against the ten GM metropolitan boroughs.
  crime      0 for every entry, and NOT a measurement. There is no honest
             sub-borough crime source: ONS Table C4 publishes at Community
             Safety Partnership level, which for Greater Manchester is the
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

USAGE
    python scripts/build_manchester_neighbourhoods.py
    python scripts/build_manchester_neighbourhoods.py --years 2025 2026
    python scripts/build_manchester_neighbourhoods.py --min-sales 40

Writes data/manchester-neighbourhoods.json. Re-run when a new PPD year lands;
the output records its own vintage and the site prints it beside the figures,
because a median price with no date is unreadable and a stale one is worse
than none.
"""

import argparse
import csv
import json
import os
import statistics
import sys
import urllib.request
from collections import defaultdict

PPD_URL = (
    'http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com/pp-{year}.csv'
)

# The ten GM metropolitan boroughs as Land Registry spells them in the
# `district` column (upper case). Checked against CITIES['manchester'] in
# backend/lambdas/score/app.py by the assertion at the end of main().
GM_BOROUGHS = {
    'BOLTON': 'Bolton',
    'BURY': 'Bury',
    'MANCHESTER': 'Manchester',
    'OLDHAM': 'Oldham',
    'ROCHDALE': 'Rochdale',
    'SALFORD': 'Salford',
    'STOCKPORT': 'Stockport',
    'TAMESIDE': 'Tameside',
    'TRAFFORD': 'Trafford',
    'WIGAN': 'Wigan',
}

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
NAME_OVERRIDES = {
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


def collect_sales(paths):
    """Stream the PPD CSVs, keeping only Greater Manchester rows.

    Returns {outward: {'prices': [...], 'borough': str, 'localities': {name: n}}}
    """
    acc = defaultdict(lambda: {'prices': [], 'boroughs': defaultdict(int), 'localities': defaultdict(int)})
    seen = kept = 0
    for path in paths:
        with open(path, newline='', encoding='utf-8', errors='replace') as fh:
            for row in csv.reader(fh):
                seen += 1
                if len(row) <= C_DISTRICT:
                    continue
                borough = GM_BOROUGHS.get(row[C_DISTRICT].strip().upper())
                if not borough:
                    continue
                out = outward(row[C_POSTCODE])
                if not out:
                    continue
                try:
                    price = int(row[C_PRICE])
                except (ValueError, TypeError):
                    continue
                if price <= 0:
                    continue
                rec = acc[out]
                rec['prices'].append(price)
                rec['boroughs'][borough] += 1
                loc = (row[C_LOCALITY] or '').strip().title()
                town = (row[C_TOWN] or '').strip().title()
                name = loc or town
                if name:
                    rec['localities'][name] += 1
                kept += 1
    print(f'  scanned {seen:,} transactions, kept {kept:,} in Greater Manchester')
    return acc


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
MARK_START = '/* GM-NEIGHBOURHOODS:START */'
MARK_END = '/* GM-NEIGHBOURHOODS:END */'


def write_index(entries, payload):
    """Rewrite index.html between the GM-NEIGHBOURHOODS markers.

    Inline rather than fetched, because London's and NYC's neighbourhood tables
    are inline too and a fourth network request on first paint is not worth
    ~11 KB. Marker-delimited so a rebuild cannot drift from the JSON: this is
    the file `data/*` gitignore taught us to distrust hand-syncing.
    """
    with open(INDEX_PATH, encoding='utf-8') as fh:
        src = fh.read()
    a, b = src.find(MARK_START), src.find(MARK_END)
    if a < 0 or b < 0:
        sys.exit(f'markers not found in index.html - expected {MARK_START} ... {MARK_END}')

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
        f'{MARK_START}\n'
        f'      // GENERATED by scripts/build_manchester_neighbourhoods.py - do not hand-edit.\n'
        f'      // {len(entries)} postcode districts. price = MEDIAN of real HM Land Registry\n'
        f'      // Price Paid transactions ({payload["priceVintage"]}), sales = how many that median rests on,\n'
        f'      // coordinates = mean of live ONS NSPL postcodes in the district.\n'
        f'      // crime is 0 for every entry and is NOT a measurement - sub-borough crime\n'
        f'      // is not published for Greater Manchester. renderGroup discloses this.\n'
        f'      const MANCHESTER_NEIGHBOURHOOD_VINTAGE = {json.dumps(payload["priceVintage"])};\n'
        f'      const MANCHESTER_NEIGHBOURHOOD_MIN_SALES = {payload["minSales"]};\n'
        f'      Object.assign(MANCHESTER_AREA_MAP, {json.dumps(area, sort_keys=True)});\n'
        f'      Object.assign(MANCHESTER_NEIGHBOURHOOD_DETAIL, {json.dumps(detail, sort_keys=True)});\n'
        f'      '
    )
    out = src[:a] + block + src[b:]
    with open(INDEX_PATH, 'w', encoding='utf-8', newline='') as fh:
        fh.write(out)
    return len(block)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--years', nargs='+', type=int, default=[2025])
    ap.add_argument('--min-sales', type=int, default=DEFAULT_MIN_SALES)
    ap.add_argument('--out', default=OUT_PATH)
    ap.add_argument(
        '--write-index',
        action='store_true',
        help='also rewrite index.html between the GM-NEIGHBOURHOODS markers',
    )
    args = ap.parse_args()

    print('Greater Manchester neighbourhoods, from HM Land Registry Price Paid')
    print(f'  vintage: {", ".join(str(y) for y in args.years)}')
    paths = [fetch_ppd(y, CACHE_DIR) for y in args.years]

    acc = collect_sales(paths)
    if not acc:
        sys.exit('FAIL: no Greater Manchester transactions found. Check the district names.')

    # Threshold BEFORE the NSPL scan, so we only look up coordinates we will use.
    keep, dropped = {}, []
    for out, rec in acc.items():
        n = len(rec['prices'])
        if n < args.min_sales:
            dropped.append((out, n))
            continue
        keep[out] = rec
    print(f'  {len(keep)} districts at or above {args.min_sales} sales; {len(dropped)} dropped')
    for out, n in sorted(dropped, key=lambda x: -x[1])[:15]:
        print(f'     dropped {out}: {n} sales')
    if len(dropped) > 15:
        print(f'     ... and {len(dropped) - 15} more below the threshold')

    print('  scanning NSPL for coordinates (this is the slow part) ...')
    centroids = collect_centroids(set(keep))

    entries = {}
    no_coords = []
    for out, rec in sorted(keep.items()):
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
        label = f'{NAME_OVERRIDES.get(out, locality)} ({out})'
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
        'generatedBy': 'scripts/build_manchester_neighbourhoods.py',
        'priceSource': 'HM Land Registry Price Paid Data',
        'priceVintage': ', '.join(str(y) for y in args.years),
        'priceBasis': 'median sale price per postcode district',
        'coordinateSource': 'ONS National Statistics Postcode Lookup (live postcodes, mean centroid)',
        'crimeSourced': False,
        'crimeNote': (
            'Sub-borough crime is not published for Greater Manchester; ONS Table C4 '
            'is Community Safety Partnership level, which here is the borough. No '
            'per-neighbourhood crime modifier is applied.'
        ),
        'minSales': args.min_sales,
        'licence': 'Open Government Licence v3.0',
        'neighbourhoods': entries,
    }
    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, indent=1, sort_keys=False)
        fh.write('\n')

    print(f'\n  wrote {len(entries)} neighbourhoods to {args.out}')

    if args.write_index:
        n = write_index(entries, payload)
        print(f'  rewrote {n} bytes between the markers in index.html')
    boroughs = defaultdict(int)
    for e in entries.values():
        boroughs[e['borough']] += 1
    missing = sorted(set(GM_BOROUGHS.values()) - set(boroughs))
    for b in sorted(boroughs):
        print(f'     {b:<12} {boroughs[b]}')
    if missing:
        print(f'  BOROUGHS WITH NO NEIGHBOURHOOD: {", ".join(missing)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
