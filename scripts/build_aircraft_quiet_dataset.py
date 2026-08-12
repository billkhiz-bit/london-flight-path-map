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

# --- Everywhere else (2026-08-12) -------------------------------------------
#
# The London file above comes from a single London-REGION export. DEFRA also
# publishes a separate coverage per airport, and those are what the other eight
# cities need. They are narrow contour strips, not city rectangles - Heathrow's
# is 41 km by 10.4 km - so coverage is thin by nature: measured across all of
# NSPL, they reach 0.6% to 3.9% of each city's postcodes.
#
# ONLY SEVEN OF THE TWELVE ARE USED, and the exclusions are measured rather than
# assumed (scripts/probe_aircraft_raster_coverage.py):
#
#   heathrow, londoncity  EXCLUDED - London is already covered, and better. The
#                         region export gives London 35,352 postcodes; these two
#                         give 17,330. Loading them would REPLACE good coverage
#                         with less of it.
#   gatwick, luton,       EXCLUDED - between them 3,704 readings, every one of
#   stansted              which lands outside LAD_TO_BOROUGH (Surrey, Beds,
#                         Essex). /v1/score cannot resolve those postcodes to a
#                         city at all, so the rows would be written and read by
#                         nobody.
#
# The remaining seven carry 7,339 postcodes inside cities we serve.
REGION_RASTERS = [
    'birmingham', 'bristol', 'eastmidlands', 'leedsbradford',
    'liverpool', 'manchester', 'newcastle',
]
REGION_OUT = ROOT / 'data' / 'aircraft-quiet-regions.json'

# Per-airport coverages declare nodata as -3.4e38, where the London region
# export uses +3.4e38. A one-sided test catches one and writes the other as a
# decibel reading, so absence is tested by MAGNITUDE here.
SENTINEL_MAGNITUDE = 1e30

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
#
# The margin means the file carries some postcodes /v1/score will not serve:
# terminated ones (NSPL keeps them, postcodes.io 404s them) and ones outside the
# 33 boroughs, such as TW20 in Egham. Measured over a 12-postcode spread, 9 were
# scorable and all 9 matched the live API exactly; the other 3 returned errors
# rather than different numbers. Harmless - index.html only looks up postcodes a
# user searched, which resolved through postcodes.io to get there - and trimming
# them would need per-postcode borough data this script does not read.
BBOX = (51.25, -0.55, 51.72, 0.35)


def lden_db_to_quiet(lden):
    """Byte-for-byte the Lambda's ramp. Any drift here IS the divergence."""
    if lden <= QUIET_CEILING_DB:
        return 10.0
    if lden >= QUIET_FLOOR_DB:
        return 0.0
    span = QUIET_FLOOR_DB - QUIET_CEILING_DB
    return round(10.0 * (QUIET_FLOOR_DB - lden) / span, 1)


def serviceable_lads():
    """LAD codes /v1/score can actually resolve to a city.

    Filtering on this is what keeps the regions file free of the Surrey, Beds
    and Essex postcodes around Gatwick, Luton and Stansted: they carry a real
    DEFRA reading and no city, so shipping them would grow the file for
    postcodes the API answers with a 400.
    """
    import importlib.util

    path = ROOT / 'backend' / 'lambdas' / 'score' / 'app.py'
    spec = importlib.util.spec_from_file_location('score_app_quiet', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return set(module.LAD_TO_BOROUGH)


def build_regions():
    """Per-airport coverages for every city except London. One NSPL pass."""
    import rasterio
    from pyproj import Transformer

    rasters = []
    for name in REGION_RASTERS:
        path = ROOT / 'data' / f'defra_aircraft_lden_{name}.tif'
        if not path.exists():
            print(f'ERROR: {path} not found')
            return 1
        with rasterio.open(path) as r:
            rasters.append({'name': name, 'array': r.read(1), 'bounds': r.bounds,
                            'res_x': r.transform.a, 'res_y': -r.transform.e,
                            'w': r.width, 'h': r.height, 'nodata': r.nodata})

    lads = serviceable_lads()
    to_bng = Transformer.from_crs('EPSG:4326', 'EPSG:27700', always_xy=True)
    quiet = {}
    per_raster = {r['name']: 0 for r in rasters}

    with NSPL.open(encoding='utf-8', errors='replace') as fh:
        reader = csv.DictReader(fh)
        cols = {c.lower(): c for c in reader.fieldnames}
        c_lad = cols.get('lad25cd')
        c_term = cols.get('doterm')
        for row in reader:
            if c_term and row[c_term].strip():
                continue
            if not c_lad or row[c_lad].strip() not in lads:
                continue
            try:
                lat, lon = float(row['lat']), float(row['long'])
            except (KeyError, TypeError, ValueError):
                continue
            if lat > 90 or lat < 49:
                continue
            x, y = to_bng.transform(lon, lat)
            best = None
            for r in rasters:
                b = r['bounds']
                if not (b.left <= x < b.right and b.bottom < y <= b.top):
                    continue
                col = int((x - b.left) / r['res_x'])
                rr = int((b.top - y) / r['res_y'])
                if not (0 <= rr < r['h'] and 0 <= col < r['w']):
                    continue
                v = float(r['array'][rr, col])
                if abs(v) > SENTINEL_MAGNITUDE:
                    continue
                if r['nodata'] is not None and v == r['nodata']:
                    continue
                if not (LDEN_MIN <= v <= LDEN_MAX):
                    continue
                # Louder wins. No postcode currently falls inside two of these
                # coverages - measured, not assumed - but if a future round
                # overlaps them, the quieter of two real readings is the wrong
                # one to publish for a noise product.
                if best is None or v > best[1]:
                    best = (r['name'], v)
            if best is None:
                continue
            per_raster[best[0]] += 1
            # Round to 1 dp BEFORE the ramp, matching what the loader stores;
            # see the note in main(). Feeding full precision here reproduces the
            # 0.1-point divergence this file exists to prevent.
            quiet[row['pcds'].replace(' ', '').upper()] = lden_db_to_quiet(round(best[1], 1))

    payload = {
        'methodologyVersion': METHODOLOGY_VERSION,
        'source': 'DEFRA Strategic Noise Mapping Round 4 (2022), aircraft, Lden, per-airport coverages',
        'note': (
            'Quiet scores for the postcodes DEFRA measured around Birmingham, '
            'Bristol, East Midlands, Leeds Bradford, Liverpool, Manchester and '
            'Newcastle airports. London is in aircraft-quiet-london.json. '
            'Postcodes absent from both have no aircraft contour and fall back '
            'to flight-path geometry.'
        ),
        'count': len(quiet),
        'quiet': quiet,
    }
    REGION_OUT.write_text(json.dumps(payload, separators=(',', ':')), encoding='utf-8')
    for name in REGION_RASTERS:
        print(f'  {name:14} {per_raster[name]:6,} postcodes')
    print(f'  wrote {REGION_OUT} ({REGION_OUT.stat().st_size / 1024:.0f} KB, '
          f'{len(quiet):,} postcodes)')
    return 0


def main():
    try:
        import rasterio
        from pyproj import Transformer
    except ImportError:
        print('Install with: pip install rasterio pyproj')
        return 1

    if '--regions' in sys.argv:
        return build_regions()

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
            # ROUND TO 1 DP BEFORE THE RAMP, matching what the loader stores.
            #
            # load_defra_raster.py writes f'{lden:.1f}', so DynamoDB holds 58.2
            # for Heathrow while the raster itself samples 58.24. Feeding the
            # full-precision value into the ramp gave 2.6 here against the API's
            # 2.7 — a 0.1 divergence on exactly the measured postcodes this file
            # exists to make agree, and one that only appeared because the live
            # API was checked after deploying rather than the file being trusted.
            quiet[row['pcds'].replace(' ', '').upper()] = lden_db_to_quiet(round(value, 1))

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
