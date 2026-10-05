"""The Bay Area's neighbourhood and ZIP tiers for the LIVE map: the same facts as a city, measured over smaller areas.

    python scripts/build_bayarea_areas.py --fetch    # DataSF's neighbourhoods into data/datasf/ (network)
    python scripts/build_bayarea_areas.py --check    # re-measure, compare both files (blocking)
    python scripts/build_bayarea_areas.py --write

Layer 1 of the deeper Bay Area (Bill, 2026-10-05: "a more in depth preview of
ZIP, area and borough like we do for New York, London"). A city has a facts
card; this gives the two tiers beneath it the same card:

- data/us-sf-neighbourhoods.json - San Francisco's 41 Analysis Neighborhoods
  (DataSF dataset j2bu-swwd, Open Data Commons PDDL: public domain), the
  neighbourhood tier, as London's named areas sit beneath its boroughs.
- data/us-bayarea-zip-areas.json - the 165 ZIP areas of data/us-bayarea-zips.json,
  measured over each ZIP's AREA (Census 2020 ZCTA cartographic boundaries,
  public domain), not at its centre point.

Every fact is the /bay-area/ page's own: its routes(), its noise picture, its
measure() and its cell wording, through build_bayarea_map_data.row_facts(),
so a neighbourhood, a ZIP and a city can never be described two ways.

Outlines are wound for d3's SPHERICAL paths (outer rings clockwise, holes
anticlockwise). DataSF's GeoJSON is wound the RFC 7946 way except for one
polygon, and drawn as delivered either would paint the whole globe; every ring
is rewound to the one convention here. Only polygons inside the page's frame
are kept, for the reason the city outlines drop the Farallon Islands.

--check needs no network and no Census files: it re-measures every stored
outline and compares the facts. With the source files on disk it also
re-derives the outlines and compares the files whole.
"""

import argparse
import json
import struct
import sys
import urllib.request
import zipfile
from pathlib import Path

import build_bay_area_page as page
import build_bayarea_map_data as cities

ROOT = Path(__file__).resolve().parents[1]
PLACES = ROOT / 'data' / 'us-bayarea-places.json'
RECORD = ROOT / 'data' / 'us-flight-procedures.json'
ZIPS = ROOT / 'data' / 'us-bayarea-zips.json'
SF_SOURCE = ROOT / 'data' / 'datasf' / 'analysis-neighborhoods.geojson'  # ignored (data/*): re-fetchable
SF_URL = 'https://data.sf.gov/resource/j2bu-swwd.geojson?$limit=100'
ZCTA = ROOT / 'data' / 'census' / 'cb_2020_us_zcta520_500k.zip'  # ignored (data/*): re-fetchable
ZCTA_STEM = 'cb_2020_us_zcta520_500k'
SF_OUT = ROOT / 'data' / 'us-sf-neighbourhoods.json'
ZIP_OUT = ROOT / 'data' / 'us-bayarea-zip-areas.json'
EXPECTED_SF = 41  # DataSF's Analysis Neighborhoods; asserted so a changed file is noticed, not absorbed
UA = {'User-Agent': page.UA['User-Agent']}


def wound(polys):
    """Outer rings clockwise, holes anticlockwise: d3's spherical convention."""
    out = []
    for poly in polys:
        rings = []
        for i, r in enumerate(poly):
            clockwise = cities.signed_area(r) < 0
            rings.append(r if clockwise == (i == 0) else r[::-1])
        out.append(rings)
    return out


def framed(name, polys, frame_box):
    kept, gone = cities.in_frame(polys, frame_box)
    if not kept:
        raise SystemExit(f'{name}: every polygon lies outside the page frame')
    return kept, gone


def tidy_polys(polys):
    """The page's own simplifier, ring by ring, keeping each polygon's outer ring first."""
    out = []
    for poly in polys:
        rings = page.tidy(poly)
        if rings and len(rings[0]) >= 4:
            out.append(rings)
    return out


def context():
    data = json.loads(PLACES.read_text(encoding='utf-8'))
    record = json.loads(RECORD.read_text(encoding='utf-8'))
    frame = page.Frame(data['frame']['px'])
    noise = page.Noise(frame, page.PAGE_DIR / data['noise']['file'])
    approaches, departures, _ = page.routes(record)
    owners = page.patch_owners(noise, data['airfields'], approaches)
    refs = {code: record['airports'][code]['ref'] for code in page.AIRPORTS}
    west, north = page.lonlat_of(frame.x0, frame.y0)
    east, south = page.lonlat_of(frame.x1, frame.y1)

    def measure(name, polys):
        rings = [r for poly in polys for r in poly]
        m = page.measure(page.Shape(rings), approaches, departures)
        pct, sample = noise.share_pct(rings)
        return {
            'name': name,
            **m,
            'noise_pct': pct,
            'airfield': page.shading_airfield(noise, owners, sample),
            'airports_inside': sorted(c for c, (lat, lon) in refs.items() if page.inside(rings, lon, lat)),
        }

    return measure, (west, south, east, north), record


def within(facts, what):
    """The page's cell says 'The airport is inside the city': true of a city's
    row, not of a ZIP or a neighbourhood holding an airport (ZIP 94128 holds SFO)."""
    facts['approach'] = facts['approach'].replace('The airport is inside the city', f'The airport is inside the {what}')
    return facts


def feature(props, polys):
    return {'type': 'Feature', 'properties': props, 'geometry': {'type': 'MultiPolygon', 'coordinates': polys}}


# ---- the neighbourhood tier --------------------------------------------------


def sf_outlines(frame_box, stored):
    """{name: polys}: from DataSF when the file is on disk, else the stored outlines."""
    if not SF_SOURCE.exists():
        return {f['properties']['name']: f['geometry']['coordinates'] for f in stored['features']}, None
    src = json.loads(SF_SOURCE.read_text(encoding='utf-8'))
    out, dropped = {}, {}
    for f in src['features']:
        name = f['properties']['nhood']
        g = f['geometry']
        polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
        polys = [[[tuple(p) for p in r] for r in poly] for poly in polys]
        kept, gone = framed(name, wound(polys), frame_box)
        if gone:
            dropped[name] = gone
        out[name] = tidy_polys(kept)
    if len(out) != EXPECTED_SF:
        raise SystemExit(f'DataSF holds {len(out)} neighbourhoods, expected {EXPECTED_SF}')
    return out, dropped


def build_sf(measure, frame_box, stored):
    outlines, dropped = sf_outlines(frame_box, stored)
    measured = [measure(name, polys) for name, polys in outlines.items()]
    ranked = {
        c['name']: within(cities.row_facts(c, rank), 'neighbourhood') for rank, c in enumerate(page.order(measured), 1)
    }
    fc = {
        'type': 'FeatureCollection',
        'source': 'DataSF Analysis Neighborhoods (j2bu-swwd), Open Data Commons PDDL',
        'generator': 'scripts/build_bayarea_areas.py --write',
        'features': [
            feature({'name': name, 'city': 'San Francisco', **ranked[name]}, outlines[name])
            for name in sorted(outlines)
        ],
    }
    return fc, dropped


# ---- the ZIP tier ------------------------------------------------------------


def read_zcta(codes):
    """{zip: rings} for the codes asked for, reading only their records via the .shx index."""
    with zipfile.ZipFile(ZCTA) as z:
        rows = page.read_dbf(z.read(f'{ZCTA_STEM}.dbf'))
        shx = z.read(f'{ZCTA_STEM}.shx')
        shp = z.read(f'{ZCTA_STEM}.shp')
    key = next(k for k in rows[0] if k.startswith('ZCTA5CE'))
    want = {i: r[key] for i, r in enumerate(rows) if r[key] in codes}
    out = {}
    for i, code in want.items():
        offset_words, length_words = struct.unpack('>ii', shx[100 + 8 * i : 108 + 8 * i])
        start = offset_words * 2
        record = shp[start : start + 8 + length_words * 2]
        out[code] = page.read_shp(b'\0' * 100 + record)[0]
    return out


def zip_outlines(frame_box, stored, codes):
    if not ZCTA.exists():
        return {f['properties']['zip']: f['geometry']['coordinates'] for f in stored['features']}, None
    rings_by_zip = read_zcta(set(codes))
    missing = sorted(set(codes) - set(rings_by_zip))
    if missing:
        raise SystemExit(f'the Census ZCTA file holds no outline for {missing}')
    out, dropped = {}, {}
    for code, rings in rings_by_zip.items():
        polys = cities.polygons({'name': code, 'rings': rings})  # group holes under outer rings, as for cities
        kept, gone = framed(code, wound(polys), frame_box)
        if gone:
            dropped[code] = gone
        out[code] = tidy_polys(kept)
    return out, dropped


def build_zips(measure, frame_box, stored):
    table = json.loads(ZIPS.read_text(encoding='utf-8'))['zips']
    outlines, dropped = zip_outlines(frame_box, stored, list(table))
    features = []
    for code in sorted(outlines):
        c = measure(code, outlines[code])
        facts = within(cities.row_facts(c, 0), 'ZIP area')
        del facts['rank']  # a ZIP is looked up, never ranked
        features.append(feature({'zip': code, **facts}, outlines[code]))
    fc = {
        'type': 'FeatureCollection',
        'source': 'US Census Bureau 2020 ZCTA cartographic boundaries (cb_2020_us_zcta520_500k), public domain',
        'generator': 'scripts/build_bayarea_areas.py --write',
        'features': features,
    }
    return fc, dropped


def render(fc):
    return json.dumps(fc, separators=(',', ':'), ensure_ascii=False) + '\n'


def fetch():
    SF_SOURCE.parent.mkdir(parents=True, exist_ok=True)
    body = urllib.request.urlopen(urllib.request.Request(SF_URL, headers=UA), timeout=60).read()
    n = len(json.loads(body).get('features', []))
    if n != EXPECTED_SF:
        raise SystemExit(f'DataSF answered with {n} neighbourhoods, expected {EXPECTED_SF}')
    SF_SOURCE.write_bytes(body)
    print(f'wrote {SF_SOURCE.relative_to(ROOT)} ({n} neighbourhoods)')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--fetch', action='store_true')
    g.add_argument('--check', action='store_true')
    g.add_argument('--write', action='store_true')
    args = ap.parse_args()
    if args.fetch:
        fetch()
        return 0
    measure, frame_box, _ = context()
    empty = {'features': []}
    stored_sf = json.loads(SF_OUT.read_text(encoding='utf-8')) if SF_OUT.exists() else empty
    stored_zip = json.loads(ZIP_OUT.read_text(encoding='utf-8')) if ZIP_OUT.exists() else empty
    sf, sf_dropped = build_sf(measure, frame_box, stored_sf)
    zips, zip_dropped = build_zips(measure, frame_box, stored_zip)
    print(f'{len(sf["features"])} San Francisco neighbourhoods, {len(zips["features"])} ZIP areas')
    for what, dropped in (('neighbourhood', sf_dropped), ('ZIP', zip_dropped)):
        if dropped:
            print(f'  {what} polygons outside the page frame, dropped: {dropped}')
    if not args.write and (not SF_SOURCE.exists() or not ZCTA.exists()):
        print('  outlines NOT re-derived (source files absent); facts re-measured from the stored outlines')
    stale = []
    for path, fc in ((SF_OUT, sf), (ZIP_OUT, zips)):
        body = render(fc)
        if not path.exists() or path.read_text(encoding='utf-8') != body:
            stale.append(str(path.relative_to(ROOT)))
            if args.write:
                path.write_text(body, encoding='utf-8', newline='\n')
    if args.write:
        print('wrote ' + ', '.join(stale) if stale else 'both files already match')
        return 0
    if stale:
        print('FAIL: stale: ' + ', '.join(stale) + ' - run scripts/build_bayarea_areas.py --write')
        return 1
    print('PASS: the neighbourhood and ZIP files equal a fresh measurement')
    return 0


if __name__ == '__main__':
    sys.exit(main())
