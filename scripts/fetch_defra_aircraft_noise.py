#!/usr/bin/env python3
"""Fetch DEFRA Round 4 per-airport aircraft Lden surfaces.

WHY PER AIRPORT, NEVER `Airport_Noise_ALL_Lden`
------------------------------------------------
The combined coverage is 26,097 x 48,046 - 1.25 billion cells - and asking for
it is how this dataset earns its reputation for being undownloadable. The
per-airport coverages are 1 to 17 MB and each fetches in a SINGLE request, no
tiling: Birmingham is 979x1467 and arrives in about 20 seconds.

WHAT THIS CHANGES, AND THE LIMIT THAT MATTERS MOST
---------------------------------------------------
Six of the nine cities score aircraft noise from an ESTIMATE derived from runway
geometry (`scripts/build_aircraft_bands.py`), because nobody had sampled DEFRA
for them. Round 4 publishes a surface for every airport those cities use -
Birmingham, Leeds Bradford, Liverpool, Newcastle, Bristol and Manchester - so
the estimate was never the only option available.

**But these are localised lobes, not city-wide surfaces.** Birmingham's covers
9.8 x 14.7 km around the runway; Bristol's is a 34 x 6.5 km corridor. Outside
them there is no reading at all, and no reading is NOT the same as quiet. Any
consumer of this data has to keep those two apart, exactly as `/v1/environment`
already does by omitting the key rather than returning a default.

South Yorkshire is absent on purpose: Doncaster Sheffield closed to commercial
flights in 2022 and DEFRA publishes no surface for it.

MEASURED COVERAGE AT POSTCODE CENTROIDS, 2026-08-11 - READ BEFORE PLANNING WORK
-------------------------------------------------------------------------------
This surface set does NOT support a measured borough-level aircraft band, and
the numbers are here so that is not rediscovered by building one:

    london           9.3% of postcodes inside a contour
    manchester       3.7%
    merseyside       3.4%
    westmidlands     2.2%
    nottingham       2.1%
    tyneandwear      0.6%
    westyorkshire    0.5%
    southyorkshire   no surface at all

Most boroughs are at 0.0%. Birmingham has a reading for 1,503 of its 35,085
postcodes; Leeds for 459 of 30,925. A borough band derived from 1.5% of its
addresses would be a genuine measurement of an unrepresentative sliver, dressed
as a statement about the borough - strictly worse than the honestly-labelled
runway-geometry estimate it would replace.

So `build_aircraft_bands.py` stays as the borough-level source. What these
surfaces ARE good for is the per-ADDRESS tier: `/v1/environment` and the raster
quiet tier can report a real Lden for the minority of postcodes inside a lobe
and omit the key everywhere else, which is exactly how London already behaves.

  pip install rasterio requests
  python scripts/fetch_defra_aircraft_noise.py --list
  python scripts/fetch_defra_aircraft_noise.py --city westmidlands
  python scripts/fetch_defra_aircraft_noise.py --all
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / 'data'

WCS = 'https://environment.data.gov.uk/spatialdata/airport-noise-all-metrics-england-round-4/wcs'
PREFIX = 'dac9cba4-abe7-43bd-b8e9-8a83da52edd8__Airport_Noise_'
UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/126.0 Safari/537.36'
)

# Which DEFRA airport surfaces belong to which city. Keyed on the city ids the
# registry uses, so a reader can check this against CITY_DATA directly.
#
# South Yorkshire is deliberately absent, not forgotten: Doncaster Sheffield
# closed to commercial flights in 2022 and DEFRA publishes nothing for it. A
# city with no airport is a real case here, and the score path already handles
# it - un-gating postcode scoring turned it into min() over an empty sequence
# and 500'd every South Yorkshire postcode until it was fixed.
CITY_AIRPORTS = {
    'london': ['Heathrow', 'Gatwick', 'LondonCity', 'Luton', 'Stansted'],
    'westmidlands': ['Birmingham'],
    'westyorkshire': ['LeedsBradford'],
    'merseyside': ['Liverpool'],
    'tyneandwear': ['Newcastle'],
    'bristol': ['Bristol'],
    'manchester': ['Manchester'],
    'nottingham': ['EastMidlands'],
}


def out_path(airport):
    return DATA / f'defra_aircraft_lden_{airport.lower()}.tif'


def fetch_airport(airport):
    """Download one airport's Lden surface. Returns True on success."""
    path = out_path(airport)
    if path.exists() and path.stat().st_size > 10000:
        print(f'  skip {path.name} (have it)')
        return True

    url = f'{WCS}?service=WCS&version=2.0.1&request=GetCoverage&coverageId={PREFIX}{airport}_Lden&format=image/tiff'
    for attempt in range(1, 4):
        try:
            started = time.time()
            data = urllib.request.urlopen(
                urllib.request.Request(url, headers={'User-Agent': UA}), timeout=600
            ).read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            print(f'  {airport}: attempt {attempt}/3 failed ({exc})')
            time.sleep(3 * attempt)
            continue
        # Magic bytes, not the status code: a gateway timeout can arrive as an
        # HTML body with a 200-ish shape. Same check as the road-noise fetcher.
        if data[:4] not in (b'II*\x00', b'MM\x00*'):
            print(f'  {airport}: attempt {attempt}/3 returned non-TIFF ({len(data)} bytes)')
            time.sleep(3 * attempt)
            continue
        path.write_bytes(data)
        print(f'  got  {path.name} ({len(data) // 1024} KB, {time.time() - started:.0f}s)')
        return True

    print(f'  FAIL {airport} after 3 attempts')
    return False


def describe(airport):
    """Report what is actually inside a downloaded surface."""
    import numpy as np
    import rasterio

    path = out_path(airport)
    if not path.exists():
        return f'{airport:14s} not downloaded'
    with rasterio.open(path) as ds:
        arr = ds.read(1).astype('float64')
        nodata = ds.nodata
        bounds = ds.bounds
        w, h = ds.width, ds.height
    mask = np.isfinite(arr) & (arr > 0)
    if nodata is not None:
        mask &= arr != nodata
    vals = arr[mask]
    km = ((bounds.right - bounds.left) / 1000, (bounds.top - bounds.bottom) / 1000)
    if not vals.size:
        return f'{airport:14s} {w}x{h}  NO DATA IN SURFACE'
    return (
        f'{airport:14s} {w:5d}x{h:<5d} {km[0]:5.1f}x{km[1]:<5.1f} km  '
        f'{100 * vals.size / arr.size:5.1f}% with data  {vals.min():.0f}-{vals.max():.0f} dB'
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--city', help='city key from CITY_AIRPORTS')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--list', action='store_true', help='describe what is already downloaded')
    args = ap.parse_args()

    if args.list:
        for city, airports in CITY_AIRPORTS.items():
            print(f'\n{city}')
            for a in airports:
                print('  ' + describe(a))
        return 0

    if args.all:
        wanted = [a for airports in CITY_AIRPORTS.values() for a in airports]
    elif args.city:
        if args.city not in CITY_AIRPORTS:
            raise SystemExit(f'no DEFRA airport surface mapped for {args.city}')
        wanted = CITY_AIRPORTS[args.city]
    else:
        ap.error('pass --city <key>, --all, or --list')

    rc = 0
    seen = set()
    for airport in wanted:
        if airport in seen:
            continue
        seen.add(airport)
        if not fetch_airport(airport):
            rc = 1
        time.sleep(1.0)

    print()
    for airport in sorted(seen):
        print(describe(airport))
    return rc


if __name__ == '__main__':
    sys.exit(main())
