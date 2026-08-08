#!/usr/bin/env python3
"""Build the extension's London borough rent reference from ONS PIPR.

WHAT THIS IS FOR, AND WHAT IT IS NOT.

The extension shows Land Registry sold prices as a RANGE on a sale listing,
because every transaction it draws is a real sale on that postcode, listed
underneath. There is no equivalent for rent: HM Land Registry records sales
only, and no open UK dataset publishes rental comparables at postcode level.

ONS publishes rent at LOCAL AUTHORITY level. That is a genuinely weaker claim
and it must be presented as one - a borough typical figure, never a comparable.
Drawing it in the sold-price chart's visual grammar would say "here is what
things like this go for near here" while being a borough-wide average over
every property type and condition. METHODOLOGY's standing rule applies: state
what the number is, and never dress a coarse figure as a fine one.

SOURCE
  Price Index of Private Rents, UK: monthly price statistics
  https://www.ons.gov.uk/economy/inflationandpriceindices/datasets/
    priceindexofprivaterentsukmonthlypricestatistics
  Contains public sector information licensed under the Open Government
  Licence v3.0.

The workbook is ~18 MB and holds every UK area from 2015 to the latest month.
This extracts the LATEST month for the 33 London boroughs only, which is ~4 KB
of JSON - small enough to bundle in the extension, so no Lambda change and no
deploy is needed to serve it.

  pip install openpyxl
  python scripts/build_london_rents.py                     # uses the cached xlsx
  python scripts/build_london_rents.py --xlsx path/to.xlsx

Re-run when ONS publishes a new month. The output records its own source month,
and the panel prints that month beside the figure - a rent number without a date
is unreadable, and a stale one is worse than none.
"""

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

DEFAULT_XLSX = Path('data/ons_pipr_latest.xlsx')
BOROUGHS_GEOJSON = Path('data/london-boroughs.json')
OUT = Path('extension/data/london-rents.json')

SHEET = 'Table 1'
HEADER_ROW = 3

# Columns we keep, by header text. Overall plus the bedroom splits; property
# type is dropped because the panel has no reliable bedroom-or-type signal from
# the listing and offering four more numbers nobody can select between is noise.
WANTED = {
    'Rental price': 'all',
    'Rental price one bed': '1',
    'Rental price two bed': '2',
    'Rental price three bed': '3',
    'Rental price four or more bed': '4+',
}

# ONS suppression markers. [x] = not available, [z] = not applicable, [c] =
# suppressed. Treated as ABSENT, never as zero - the substitution of "no data"
# for "a low number" is this project's most-repeated defect.
MISSING = {'[x]', '[z]', '[c]', '[low]', '', None}


def london_borough_codes():
    """The 33 borough codes, from the boundary file the site already ships.

    Read from the GeoJSON rather than hardcoded so the two cannot drift: if a
    borough is ever missing from the map it is missing from the rents too,
    which is the honest failure rather than a rent figure for a shape we
    cannot locate.
    """
    if not BOROUGHS_GEOJSON.exists():
        print(f'ERROR: {BOROUGHS_GEOJSON} not found')
        sys.exit(1)
    geo = json.loads(BOROUGHS_GEOJSON.read_text(encoding='utf-8'))
    out = {}
    for f in geo['features']:
        p = f['properties']
        out[p['LAD13CD']] = p['LAD13NM']
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--xlsx', type=Path, default=DEFAULT_XLSX)
    args = ap.parse_args()

    try:
        import openpyxl
    except ImportError:
        print('Install with: pip install openpyxl')
        return 1

    if not args.xlsx.exists():
        print(f'ERROR: {args.xlsx} not found. Download it from the URL in the docstring.')
        return 1

    codes = london_borough_codes()
    print(f'{len(codes)} London boroughs from {BOROUGHS_GEOJSON}')

    wb = openpyxl.load_workbook(args.xlsx, read_only=True, data_only=True)
    ws = wb[SHEET]

    rows = ws.iter_rows(min_row=HEADER_ROW, values_only=True)
    header = list(next(rows))
    idx = {h: i for i, h in enumerate(header) if h}
    for col in ('Time period', 'Area code', 'Area name'):
        if col not in idx:
            print(f'ERROR: column "{col}" missing — ONS changed the layout')
            return 1
    missing_cols = [c for c in WANTED if c not in idx]
    if missing_cols:
        print(f'ERROR: columns missing — ONS changed the layout: {missing_cols}')
        return 1

    # Keep only the LATEST period per borough. The sheet is a long time series;
    # scanning it all and keeping the max date avoids assuming row order.
    latest = {}
    scanned = 0
    for row in rows:
        scanned += 1
        code = row[idx['Area code']]
        if code not in codes:
            continue
        period = row[idx['Time period']]
        if period is None:
            continue
        prev = latest.get(code)
        if prev is None or period > prev[0]:
            latest[code] = (period, row)

    print(f'scanned {scanned:,} rows, matched {len(latest)} boroughs')

    if len(latest) != len(codes):
        absent = sorted(set(codes) - set(latest))
        print(f'WARNING: no ONS rows for {len(absent)} borough(s): {absent}')

    months = {p.strftime('%Y-%m') for p, _ in latest.values()}
    if len(months) > 1:
        # Not fatal, but the panel prints one month for all of them, so a mixed
        # vintage would make that label a lie for some boroughs.
        print(f'WARNING: mixed vintages across boroughs: {sorted(months)}')

    boroughs = {}
    for code, (_period, row) in sorted(latest.items()):
        entry = {}
        for header_name, key in WANTED.items():
            raw = row[idx[header_name]]
            if raw in MISSING or isinstance(raw, str):
                continue
            entry[key] = round(float(raw))
        if entry:
            boroughs[code] = {'name': codes[code], **entry}

    # Borough outlines ship in the SAME file as the rents, keyed identically.
    #
    # The extension has a coordinate, not a borough, so something has to do
    # point-in-polygon. Two files could drift - a borough present in one and
    # absent from the other yields either a rent nobody can locate or a shape
    # with no figure. Generated together, keyed by LAD13CD, they cannot.
    #
    # Coordinates rounded to 4 dp (~11 m). Borough assignment does not need
    # metre precision and the full-precision outlines are 30 KB larger.
    def _round(x, p=4):
        if isinstance(x, list):
            return [_round(i, p) for i in x]
        return round(x, p)

    geo = json.loads(BOROUGHS_GEOJSON.read_text(encoding='utf-8'))
    shapes = {}
    for f in geo['features']:
        code = f['properties']['LAD13CD']
        g = f['geometry']
        # Normalise Polygon and MultiPolygon to one shape: a list of rings.
        # The panel's hit test then has exactly one case to handle.
        if g['type'] == 'Polygon':
            rings = g['coordinates']
        elif g['type'] == 'MultiPolygon':
            rings = [ring for poly in g['coordinates'] for ring in poly]
        else:
            continue
        shapes[code] = _round(rings)

    payload = {
        'source': 'ONS Price Index of Private Rents, UK: monthly price statistics',
        'licence': 'Open Government Licence v3.0',
        'sourceMonth': sorted(months)[-1] if months else None,
        'geography': 'local authority (London borough)',
        # Read by the panel and printed verbatim. The claim travels WITH the
        # number so no renderer has to remember to qualify it.
        'basis': 'borough-wide average, all property conditions — not a comparable',
        'boroughs': boroughs,
        'shapes': shapes,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1, sort_keys=False) + '\n', encoding='utf-8')

    size = OUT.stat().st_size
    print(f'wrote {OUT} ({size:,} bytes), month {payload["sourceMonth"]}, {len(boroughs)} boroughs')
    sample = next(iter(boroughs.items()))
    print(f'  sample: {sample[0]} {sample[1]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
