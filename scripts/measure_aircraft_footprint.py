#!/usr/bin/env python3
"""Which boroughs DEFRA's published 55 dB Lden aircraft contour actually reaches.

WHY THIS EXISTS. `build_aircraft_bands.py` applies a NEAR-FIELD FLOOR: a borough
that overlaps the published 55 dB Lden footprint cannot be called quiet,
whatever the radial ladder says. Until 2026-09-01 that overlap was tested
against a DISC - `footprint_for()` returns sqrt(area/pi) as an equivalent
radius, and the borough ring was compared against it.

Round 4 contours are not discs. They are long thin strips along the runway
centreline: East Midlands' is 21.2 x 3.8 km against a disc of r = 3.46 km. So
the test was wrong in both directions at once, and the audit of 2026-08-31
found the consequence live:

    nottingham / Rushcliffe   published `Quiet skies 10.0/10`, band `low`
                              10.43 km2 of it is at or above 55 dB Lden,
                              peaking at 65.6 dB - the fourth-largest aircraft
                              footprint in the product. It missed the disc by
                              180 m.
    tyneandwear / North Tyneside  same defect at 0.32 km2 / 57.1 dB.

Solihull, at a comparable 9.21 km2, publishes `moderate-high`. So the disc was
not a deliberate threshold; it was internally inconsistent.

WHY A CHECKED-IN FILE RATHER THAN READING THE RASTER AT DERIVE TIME. The
GeoTIFFs are 2.6-29 MB each and gitignored, so on any machine but the one that
fetched them they are absent. `build_aircraft_bands.py --check` is BLOCKING in
preflight; making it need a raster would gate every commit on a 100 MB download.
This writes the measurement once, into a small checked-in file, and `--verify`
re-derives it from the GeoTIFFs so the file cannot drift from the rasters
silently. That is the shape `data/district-msoa-names.json` already uses: the
evidence is checked in, and the gate that needs no network reads the evidence.

WHAT IS MEASURED. Cell centres, in the raster's own CRS (EPSG:27700), masked by
the borough polygon with `rasterio.features.geometry_mask`. No reprojection of
the raster and no resampling: the borough ring is projected to BNG instead, so
the only interpolation anywhere is the one DEFRA already published.

  pip install rasterio pyproj numpy
  python scripts/measure_aircraft_footprint.py --write
  python scripts/measure_aircraft_footprint.py --verify
"""

import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(REPO, 'data', 'aircraft-footprint.json')

# The Lden contour DEFRA's Round 4 END maps publish down to. At or above this a
# location is inside the mapped footprint; below it DEFRA reports nothing, which
# is why 55 is the floor rather than a threshold we chose.
CONTOUR_DB = 55.0

# Airport code -> the per-airport coverage filename fetched by
# scripts/fetch_defra_aircraft_noise.py. Codes with no entry are NOT mapped by
# Round 4 at all - Teesside (MME) and Cardiff (CWL) - and those keep the disc,
# because there is no contour to test against. That is stated in the output so
# a reader can never mistake "no contour published" for "not measured here".
RASTER_FOR_CODE = {
    'LHR': 'heathrow', 'LCY': 'londoncity', 'LGW': 'gatwick', 'LTN': 'luton',
    'STN': 'stansted', 'BHX': 'birmingham', 'LBA': 'leedsbradford',
    'MAN': 'manchester', 'LPL': 'liverpool', 'NCL': 'newcastle',
    'BRS': 'bristol', 'EMA': 'eastmidlands',
}

SENTINEL_MAGNITUDE = 1e30


def raster_path(key):
    return os.path.join(REPO, 'data', 'defra_aircraft_lden_' + key + '.tif')


def load_bands_module():
    """Import build_aircraft_bands for its AIRPORTS registry.

    Imported rather than copied. A second copy of the airport table is the
    drift this repo has already paid for four times, and the registry is the
    thing that decides which raster a city is even asking about.
    """
    import importlib.util

    path = os.path.join(REPO, 'scripts', 'build_aircraft_bands.py')
    spec = importlib.util.spec_from_file_location('build_aircraft_bands_probe', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project_geometry(geom, transformer):
    """A GeoJSON geometry with every lon/lat replaced by BNG easting/northing."""
    def ring(coords):
        xs, ys = transformer.transform([c[0] for c in coords], [c[1] for c in coords])
        return [[x, y] for x, y in zip(xs, ys, strict=True)]

    if geom['type'] == 'Polygon':
        return {'type': 'Polygon', 'coordinates': [ring(r) for r in geom['coordinates']]}
    if geom['type'] == 'MultiPolygon':
        return {
            'type': 'MultiPolygon',
            'coordinates': [[ring(r) for r in poly] for poly in geom['coordinates']],
        }
    raise SystemExit('unsupported geometry ' + repr(geom['type']))


def measure_city(city, airport, verbose=True):
    """km2 at or above CONTOUR_DB, and peak dB, for every borough of one city.

    Returns None when this airport has no Round 4 coverage - a DIFFERENT answer
    from "every borough measured zero", and the caller must keep them apart.
    """
    import numpy as np
    import rasterio
    from pyproj import Transformer
    from rasterio.features import geometry_mask

    key = RASTER_FOR_CODE.get(airport['code'])
    if key is None:
        return None
    path = raster_path(key)
    if not os.path.exists(path):
        raise SystemExit(
            path + ' missing. Fetch it with scripts/fetch_defra_aircraft_noise.py before '
            'measuring; refusing to report a zero footprint from an absent raster.'
        )

    gj_path = os.path.join(REPO, 'data', city + '-boroughs.json')
    with open(gj_path, encoding='utf-8') as fh:
        gj = json.load(fh)
    transformer = Transformer.from_crs('EPSG:4326', 'EPSG:27700', always_xy=True)

    with rasterio.open(path) as r:
        band = r.read(1)
        transform = r.transform
        shape = band.shape
        nodata = r.nodata
    valid = np.abs(band) < SENTINEL_MAGNITUDE
    if nodata is not None:
        valid &= band != nodata
    loud = valid & (band >= CONTOUR_DB)
    cell_km2 = abs(transform.a * transform.e) / 1_000_000.0
    if verbose:
        print(f'  {city:15} {key:13} {int(loud.sum()):>9,} cells >= {CONTOUR_DB:.0f} dB = {loud.sum() * cell_km2:7.2f} km2 total')

    out = {}
    for feature in gj['features']:
        name = feature['properties']['name']
        projected = project_geometry(feature['geometry'], transformer)
        # invert=True gives True INSIDE the geometry, which is the sense the
        # name does not suggest and is the one bug worth guarding: the default
        # masks the inside out, so a borough would be measured against
        # everything except itself.
        inside = geometry_mask([projected], out_shape=shape, transform=transform, invert=True)
        hit = loud & inside
        cells = int(hit.sum())
        out[name] = {
            'cells': cells,
            'km2': round(cells * cell_km2, 4),
            'maxDb': round(float(band[hit].max()), 1) if cells else None,
        }
    return out


def build(verbose=True):
    """Measure every derivable city. Returns the payload written to disk."""
    module = load_bands_module()
    cities, unmapped = {}, {}
    exempt = {'london', 'nyc'}
    for city, airport in sorted(module.AIRPORTS.items()):
        if city in exempt:
            continue
        if airport is None:
            # A city with no operating airport. Recorded EXPLICITLY, because an
            # absent key and a measured zero are the same shape in JSON and only
            # one of them means "we looked".
            unmapped[city] = {'reason': 'no operating commercial airport', 'code': None}
            continue
        if airport['code'] not in RASTER_FOR_CODE:
            unmapped[city] = {
                'reason': 'airport is not mapped by DEFRA Round 4, so no contour exists to test',
                'code': airport['code'],
            }
            continue
        measured = measure_city(city, airport, verbose=verbose)
        cities[city] = {'airport': airport['code'], 'boroughs': measured}
    return {
        'generatedBy': 'scripts/measure_aircraft_footprint.py',
        'source': 'DEFRA Strategic Noise Mapping Round 4 (2021 traffic), per-airport Lden coverages',
        'licence': 'Open Government Licence v3.0',
        'contourDb': CONTOUR_DB,
        'note': (
            'km2 of each borough at or above the contour, from cell centres in EPSG:27700. '
            'Used by build_aircraft_bands.py for the near-field floor, which until 2026-09-01 '
            'compared the borough against a DISC of equivalent radius and so missed '
            'Rushcliffe by 180 m while 10.43 km2 of it sat above 55 dB.'
        ),
        'cities': cities,
        'unmapped': unmapped,
    }


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--write', action='store_true', help='measure and rewrite the checked-in file')
    ap.add_argument('--verify', action='store_true', help='re-measure and compare against the file')
    args = ap.parse_args()

    if not (args.write or args.verify):
        ap.error('give --write or --verify')

    print(f'DEFRA Round 4 aircraft footprint per borough (>= {CONTOUR_DB:.0f} dB Lden)')
    payload = build()

    if args.write:
        with open(OUT_PATH, 'w', encoding='utf-8', newline='\n') as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write('\n')
        touched = sum(
            1 for c in payload['cities'].values() for b in c['boroughs'].values() if b['cells']
        )
        total = sum(len(c['boroughs']) for c in payload['cities'].values())
        print('')
        print('wrote {}: {} of {} boroughs touch the contour, {} cities have no Round 4 coverage'
              .format(OUT_PATH, touched, total, len(payload['unmapped'])))
        return 0

    if not os.path.exists(OUT_PATH):
        print('FAIL: ' + OUT_PATH + ' missing - run --write.')
        return 1
    with open(OUT_PATH, encoding='utf-8') as fh:
        have = json.load(fh)
    compared = differ = 0
    for city, block in sorted(payload['cities'].items()):
        old = have.get('cities', {}).get(city, {}).get('boroughs')
        if old is None:
            print(f'  FAIL: {city} measured now and absent from the file')
            differ += 1
            continue
        for name, rec in sorted(block['boroughs'].items()):
            compared += 1
            was = old.get(name)
            if was is None or was['cells'] != rec['cells']:
                differ += 1
                print('  {}/{}: file {} cells, raster {} cells'.format(
                    city, name, was and was['cells'], rec['cells']))
    # A per-CITY floor, not a global one. This repo has been bitten five times
    # by `compared > 0`, which one city of eleven satisfies.
    thin = [c for c in payload['cities'] if not payload['cities'][c]['boroughs']]
    print('')
    print('compared {} boroughs across {} cities'.format(compared, len(payload['cities'])))
    if differ or thin:
        print(f'FAIL: {differ} boroughs differ, {len(thin)} cities measured nothing.')
        print('Re-run with --write, and re-derive bands with build_aircraft_bands.py --write.')
        return 1
    print('OK: the checked-in footprint file reproduces from the DEFRA GeoTIFFs.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
