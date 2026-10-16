"""Rail, metro and light-rail stations of the Bay Area's four counties: BTS National Transit Map (2026-10-16).

Release 2's transport input (ROADMAP "Release 2 plan"): the US Bureau of Transportation
Statistics' National Transit Map stops layer, compiled from the agencies' own GTFS feeds.
The UK method counts rail, metro and tram nodes (NaPTAN); this keeps the GTFS route types
that match them, 0 (tram, light rail), 1 (subway, metro) and 2 (rail), one record per
station.

  - A station is its GTFS station record (location_type 1) where the agency publishes one;
    its platforms and entrances (parent_station set) are folded into it. An agency with no
    station records (Muni's light rail) is folded by name within STATION_M metres.
  - Cable cars (type 5) are LEFT OUT and counted, a decision recorded in the file: they are
    a tourist line with stops every block, and counting them would read central San
    Francisco as better served than any station-based measure would.
  - Capitol Corridor (Amtrak) is ABSENT from the layer (BTS lists Emeryville only as an AC
    Transit bus stop), so Emeryville reads no station and Berkeley, Hayward and Jack London
    Square each lose one. The file says so; nothing is filled in.

Licence: the layer is Creative Commons Attribution 3.0 United States (CC-BY-3.0); credit
"US Department of Transportation, Bureau of Transportation Statistics". The Bay Area
agencies' own feeds are listed as public domain in the layer's agency table.

  python scripts/build_bayarea_transit.py --fetch   query the layer (paged) into data/bts/
  python scripts/build_bayarea_transit.py --write   write data/us-bayarea-transit.json from it
  python scripts/build_bayarea_transit.py --check   the file is sound (offline); and, when the
                                                    raw query is on disk, the file against it
"""

import argparse
import json
import math
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LAYER = ('https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/'
         'NTAD_National_Transit_Map_Stops/FeatureServer/0')
RAW = REPO / 'data' / 'bts' / 'bayarea-transit-stops.json'
PLACES = REPO / 'data' / 'us-bayarea-places.json'
OUT = REPO / 'data' / 'us-bayarea-transit.json'
RAIL_TYPES = {'0', '1', '2'}
CABLE_CAR = '5'
STATION_M = 150
FIELDS = 'ntd_id,stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station,stop_type,download_date'


def bbox():
    """The four counties' extent, from the city outlines (with a 2 km margin)."""
    with open(PLACES, encoding='utf-8') as fh:
        places = json.load(fh)['places']
    pts = [pt for p in places for poly in p['rings'] for pt in poly] if 'rings' in places[0] else None
    if pts is None:
        lats = [p['lat'] for p in places]
        lons = [p['lon'] for p in places]
    else:
        lons = [x for x, _ in pts]
        lats = [y for _, y in pts]
    m = 0.02
    return min(lons) - m, min(lats) - m, max(lons) + m, max(lats) + m


def fetch():
    x0, y0, x1, y1 = bbox()
    where = "stop_type LIKE '%0%' OR stop_type LIKE '%1%' OR stop_type LIKE '%2%' OR stop_type LIKE '%5%'"
    out, offset = [], 0
    while True:
        q = urllib.parse.urlencode({
            'where': where, 'geometry': f'{x0},{y0},{x1},{y1}', 'geometryType': 'esriGeometryEnvelope',
            'inSR': 4326, 'spatialRel': 'esriSpatialRelIntersects', 'outFields': FIELDS,
            'returnGeometry': 'false', 'f': 'json', 'resultOffset': offset, 'resultRecordCount': 2000,
            'orderByFields': 'OBJECTID'})
        req = urllib.request.Request(f'{LAYER}/query?{q}', headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
            page = json.load(resp)
        if 'error' in page:
            raise SystemExit(f"layer error: {page['error']}")
        feats = [f['attributes'] for f in page.get('features', [])]
        out += feats
        if not page.get('exceededTransferLimit') or not feats:
            break
        offset += len(feats)
    return {'layer': LAYER, 'bbox': [x0, y0, x1, y1], 'stops': out}


def metres(a, b):
    k = 111_320
    return math.hypot((a[0] - b[0]) * k, (a[1] - b[1]) * k * math.cos(math.radians(a[0])))


def build(raw):
    stops = raw['stops']
    types = lambda s: set(str(s['stop_type'] or '').replace(' ', '').split(';'))  # noqa: E731
    rail = [s for s in stops if types(s) & RAIL_TYPES]
    cable = [s for s in stops if CABLE_CAR in types(s) and not types(s) & RAIL_TYPES]
    stations = {}
    # 1. Station records, keyed by agency and stop id.
    for s in rail:
        if str(s['location_type']) == '1':
            stations[(s['ntd_id'], s['stop_id'])] = {'name': s['stop_name'].strip(), 'agency': s['ntd_id'],
                                                     'lat': s['stop_lat'], 'lon': s['stop_lon'],
                                                     'types': sorted(types(s) & RAIL_TYPES)}
    # 2. Stops with no parent station: fold by agency and name within STATION_M.
    for s in rail:
        if str(s['location_type']) == '1' or (s['parent_station'] or '').strip():
            continue
        if not (s['stop_lat'] and s['stop_lon']):
            continue
        here = (s['stop_lat'], s['stop_lon'])
        same = next((k for k, v in stations.items()
                     if v['agency'] == s['ntd_id'] and v['name'].lower() == s['stop_name'].strip().lower()
                     and metres(here, (v['lat'], v['lon'])) <= STATION_M), None)
        if same is None:
            stations[(s['ntd_id'], f"stop:{s['stop_id']}")] = {'name': s['stop_name'].strip(), 'agency': s['ntd_id'],
                                                               'lat': s['stop_lat'], 'lon': s['stop_lon'],
                                                               'types': sorted(types(s) & RAIL_TYPES)}
    rows = sorted(stations.values(), key=lambda r: (r['agency'], r['name'], r['lat']))
    by_agency = {}
    for r in rows:
        by_agency[r['agency']] = by_agency.get(r['agency'], 0) + 1
    return {
        'source': 'US Department of Transportation, Bureau of Transportation Statistics, National Transit Map '
                  'Stops (compiled from the agencies\' GTFS feeds)',
        'layer': raw['layer'],
        'compiled': sorted({str(s.get('download_date')) for s in stops if s.get('download_date')})[-1:],
        'licence': 'Creative Commons Attribution 3.0 United States (CC-BY-3.0): credit USDOT BTS',
        'generator': 'scripts/build_bayarea_transit.py --write',
        'kept': 'GTFS route types 0 (tram, light rail), 1 (subway, metro), 2 (rail); one record per station',
        'left_out': {'cable_car_stops': len(cable),
                     'why': 'a tourist line with stops every block; a decision, not a gap in the data'},
        'known_gap': 'Capitol Corridor (Amtrak) is absent from the layer: Emeryville reads no station, and '
                     'Berkeley, Hayward and Jack London Square each lose one',
        'stations_by_agency_ntd_id': by_agency,
        'stations': rows,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--fetch', action='store_true')
    g.add_argument('--write', action='store_true')
    g.add_argument('--check', action='store_true')
    a = ap.parse_args()
    if a.fetch:
        RAW.parent.mkdir(parents=True, exist_ok=True)
        raw = fetch()
        RAW.write_text(json.dumps(raw) + '\n', encoding='utf-8', newline='\n')
        print(f"wrote {RAW.relative_to(REPO)}: {len(raw['stops'])} stops")
        return 0
    if a.write:
        doc = build(json.loads(RAW.read_text(encoding='utf-8')))
        OUT.write_text(json.dumps(doc, indent=1) + '\n', encoding='utf-8', newline='\n')
        print(f"wrote {OUT.relative_to(REPO)}: {len(doc['stations'])} stations "
              f"({doc['stations_by_agency_ntd_id']}); {doc['left_out']['cable_car_stops']} cable-car stops left out")
        return 0
    failures = []
    doc = json.loads(OUT.read_text(encoding='utf-8'))
    n = len(doc['stations'])
    # BART alone has 50 stations; fewer than 150 rail stations in the four counties means the query broke.
    if n < 150:
        failures.append(f'only {n} stations (floor 150): the query or the folding broke')
    if doc['stations_by_agency_ntd_id'].get('90003', 0) < 40:
        failures.append('fewer than 40 BART stations (ntd 90003)')
    if RAW.exists():
        if build(json.loads(RAW.read_text(encoding='utf-8')))['stations'] != doc['stations']:
            failures.append(f'{OUT.name} is not what the raw query gives (re-run --write)')
        else:
            print(f'  raw query      {OUT.name} == {RAW.name}')
    else:
        print('  raw query      not on disk; the checked-in file was checked for shape only')
    if failures:
        print('RESULT: FAIL')
        for f in failures:
            print('  ' + f)
        return 1
    print(f'RESULT: PASS ({n} stations)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
