#!/usr/bin/env python3
"""Emit the per-postcode aircraft quiet scores the site needs, from the raster.

WHY THIS EXISTS. index.html computes its own per-postcode quiet from Haversine
geometry; /v1/score computes it from the DEFRA raster where one exists. Lifting
RASTER_TIER_QUARANTINED would therefore make the two publish different numbers
for the ~9% of London postcodes DEFRA covers — reopening exactly the site/API
divergence closed on 2026-08-03, and one that SiteApiGeometryParityTests cannot
see because it compares FLIGHT_PATHS waypoints, which would still match.

The obvious fix — have the site read /v1/score — was recommended and is wrong:
that route is API-key gated, so the site would embed a key and meter every
visitor. This is the other option from the quarantine note, and the sparse
coverage that causes the problem is what makes it cheap: only 35,352 of 393,942
London-bbox postcodes carry a real reading, about 483 KB of JSON.

WHY IT SHIPS THE SCORE, NOT THE DECIBELS. Shipping dB would make index.html
reimplement lden_db_to_quiet — a 45→63 dB ramp with two cited anchors. This
codebase has been bitten repeatedly by the site holding its own copy of a Lambda
formula (see the SCHOOL_SCORE_P8 comment in index.html, which says so
explicitly). Shipping the computed value means the two CANNOT disagree about the
mapping; they can only disagree about the data, and the data is this one file.

Consequence to respect: this file is derived from a methodology version and goes
stale when the ramp changes. `methodologyVersion` is embedded so a mismatch is
detectable rather than silent, and the site refuses the file when it disagrees.

  pip install rasterio pyproj
  python scripts/build_aircraft_quiet_dataset.py
"""

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEOTIFF = ROOT / 'data' / 'defra_lden_2022.tif'
NSPL = ROOT / 'data' / 'nspl.csv'
OUT = ROOT / 'data' / 'aircraft-quiet-london.json'

# Mirrors backend/lambdas/score/app.py. Kept as constants rather than inlined so
# a future change is a two-line edit with a visible diff.
QUIET_CEILING_DB = 45.0
QUIET_FLOOR_DB = 63.0
METHODOLOGY_VERSION = '3.6'

# The raster's measured range is 40.0-88.9 dB. Anything outside that is a
# sentinel — this GeoTIFF declares nodata as 3.4e38, the float32 maximum, and a
# naive `>= 40.0` test passes it straight through. That mistake reported 100%
# coverage on the first attempt at this measurement.
LDEN_MIN = 40.0
LDEN_MAX = 100.0

# Greater London plus margin, matching the noise-raster bbox.
BBOX = (51.25, -0.55, 51.72, 0.35)


def lden_db_to_quiet(lden):
    """Byte-for-byte the Lambda's ramp. Any drift here IS the divergence."""
    if lden <= QUIET_CEILING_DB:
        return 10.0
    if lden >= QUIET_FLOOR_DB:
        return 0.0
    span = QUIET_FLOOR_DB - QUIET_CEILING_DB
    return round(10.0 * (QUIET_FLOOR_DB - lden) / span, 1)


def main():
    try:
        import rasterio
        from pyproj import Transformer
    except ImportError:
        print('Install with: pip install rasterio pyproj')
        return 1

    for path in (GEOTIFF, NSPL):
        if not path.exists():
            print(f'ERROR: {path} not found')
            return 1

    raster = rasterio.open(GEOTIFF)
    bounds = raster.bounds
    to_bng = Transformer.from_crs('EPSG:4326', 'EPSG:27700', always_xy=True)

    quiet = {}
    considered = 0

    with NSPL.open(encoding='utf-8', errors='replace') as fh:
        for row in csv.DictReader(fh):
            try:
                lat, lon = float(row['lat']), float(row['long'])
            except (KeyError, TypeError, ValueError):
                continue
            if not (BBOX[0] <= lat <= BBOX[2] and BBOX[1] <= lon <= BBOX[3]):
                continue
            x, y = to_bng.transform(lon, lat)
            if not (bounds.left <= x <= bounds.right and bounds.bottom <= y <= bounds.top):
                continue
            considered += 1
            value = float(list(raster.sample([(x, y)]))[0][0])
            if not (LDEN_MIN <= value <= LDEN_MAX):
                continue
            quiet[row['pcds'].replace(' ', '').upper()] = lden_db_to_quiet(value)

    payload = {
        'methodologyVersion': METHODOLOGY_VERSION,
        'source': 'DEFRA Strategic Noise Mapping Round 4 (2022), aircraft, Lden',
        'note': (
            'Quiet scores for the London postcodes DEFRA actually measured. '
            'Postcodes absent from this file have no aircraft contour and fall '
            'back to flight-path geometry.'
        ),
        'count': len(quiet),
        'quiet': quiet,
    }
    OUT.write_text(json.dumps(payload, separators=(',', ':')), encoding='utf-8')

    pct = 100 * len(quiet) / considered if considered else 0
    print(f'considered {considered:,} London-bbox postcodes')
    print(f'  with a real reading: {len(quiet):,} ({pct:.1f}%)')
    print(f'  wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
