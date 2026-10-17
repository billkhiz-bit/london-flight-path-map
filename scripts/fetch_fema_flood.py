"""Fetch FEMA's flood hazard zones (NFHL) over the Bay Area's 50 cities, as one Esri JSON file.

Bay Area release 2's flood input: the share of a city inside FEMA's 1%-annual-chance zone (the
Special Flood Hazard Area), the US counterpart of the Environment Agency's Medium-or-High line.

WHY THIS RUNS ON A US MACHINE. FEMA's flood hosts (msc.fema.gov, hazards.fema.gov) reset every
connection from Bill's UK network, from Chrome and from scripts alike (measured 2026-10-17), and
www.fema.gov answers 403. So the GitHub Actions workflow `fema-flood-fetch.yml` runs this on a US
runner and keeps the output as a short-lived artifact. Bill chose that route on 2026-10-17.

WHAT IT FETCHES, and the guards:
- The search box is DERIVED from data/us-bayarea-places.json (the 43 cities and 7 towns), never
  typed in, so it follows the city set. Polygons are selected SPATIALLY, never by county code
  (ROADMAP: a county's DFIRM can reach over its line).
- The layer is found BY NAME ("Flood Hazard Zones") in the service's own layer list, and the
  service is tried at both of FEMA's documented paths, because a layer id or path guessed from
  memory would fail silently as "no flood anywhere".
- Object ids first, then features in chunks, so the service's record cap cannot truncate the set.
- A fetch that finds NO features fails: an empty result is not "no flood risk" (the EA flood tile
  cached all-zero is this repo's precedent).
- Standard library only, so the runner installs nothing.

Usage: python -I scripts/fetch_fema_flood.py --out <dir>
Writes <dir>/nfhl-bayarea.esrijson.gz and <dir>/manifest.json (service, layer, box, count, sha256).
"""

import argparse
import datetime as dt
import gzip
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLACES = REPO / 'data' / 'us-bayarea-places.json'
SERVICES = (
    'https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer',
    'https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer',
)
LAYER_NAME = 'flood hazard zones'
FIELDS = 'FLD_ZONE,ZONE_SUBTY,SFHA_TF,DFIRM_ID,VERSION_ID'
CHUNK = 200  # features per request: well under any NFHL record cap, small enough to retry
TILE_DEG = 0.25  # first search tile; a refused tile is split in four
MIN_TILE_DEG = 0.02  # ...down to this, then the run fails naming the tile
MARGIN_DEG = 0.01
UA = {'User-Agent': 'Sky Score data fetch (skyscore.co.uk; public-domain FEMA NFHL)'}


def city_box(places_doc):
    """[xmin, ymin, xmax, ymax] over the scored places' rings ([lon, lat]), with a small margin."""
    xs, ys = [], []
    for p in places_doc['places']:
        if p['kind'] not in ('city', 'town'):
            continue
        for ring in p['rings']:
            for lon, lat in ring:
                xs.append(lon)
                ys.append(lat)
    if not xs:
        raise SystemExit(f'{PLACES.name}: no city or town rings, so no box to search')
    return [min(xs) - MARGIN_DEG, min(ys) - MARGIN_DEG, max(xs) + MARGIN_DEG, max(ys) + MARGIN_DEG]


class ServiceError(Exception):
    """The service answered, with an error body: a refusal, not a network failure."""


def get_json(url, params, tries=4):
    query = urllib.parse.urlencode(params)
    for attempt in range(tries):
        try:
            req = urllib.request.Request(f'{url}?{query}', headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r:
                doc = json.loads(r.read().decode('utf-8'))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == tries - 1:
                raise SystemExit(f'{url}: {exc} after {tries} tries; nothing was written') from exc
            time.sleep(5 * (attempt + 1))
            continue
        if 'error' in doc:  # ArcGIS answers 200 with an error body
            raise ServiceError(f'{url}: the service refused the request: {doc["error"]}')
        return doc
    raise SystemExit(f'{url}: unreachable')  # pragma: no cover


def find_layer(get=get_json):
    """(service url, layer id, layer name) for the flood hazard zone layer, found by name."""
    tried = []
    for service in SERVICES:
        try:
            doc = get(service, {'f': 'json'}, tries=2)
        except (SystemExit, ServiceError) as exc:
            tried.append(str(exc))
            continue
        for layer in doc.get('layers', []):
            if layer.get('name', '').strip().lower() == LAYER_NAME:
                return service, layer['id'], layer['name']
        tried.append(f'{service}: no layer named "{LAYER_NAME}" among {len(doc.get("layers", []))}')
    raise SystemExit('no FEMA NFHL service answered with the flood layer:\n  ' + '\n  '.join(tried))


def tiles(box, size):
    """The box cut into tiles of at most `size` degrees a side, row by row."""
    xmin, ymin, xmax, ymax = box
    out = []
    y = ymin
    while y < ymax:
        x = xmin
        while x < xmax:
            out.append([round(x, 6), round(y, 6), round(min(x + size, xmax), 6), round(min(y + size, ymax), 6)])
            x += size
        y += size
    return out


def object_ids(layer_url, box, get=get_json):
    """Every flood polygon id intersecting the box, searched tile by tile.

    The first run (2026-10-17, run 39066895696) asked for the whole 1.5 x 1 degree box at once and
    FEMA answered 400 "Failed to execute query": too heavy a spatial query on a national layer. So
    the box is searched in TILE_DEG tiles, and a tile the service refuses is split into four and
    retried, down to MIN_TILE_DEG; a tile refused even then fails the run, naming it.
    """
    ids = set()
    todo = tiles(box, TILE_DEG)
    done = 0
    while todo:
        t = todo.pop()
        try:
            doc = get(f'{layer_url}/query', {
                'where': '1=1', 'geometry': ','.join(map(str, t)), 'geometryType': 'esriGeometryEnvelope',
                'inSR': 4326, 'spatialRel': 'esriSpatialRelIntersects', 'returnIdsOnly': 'true', 'f': 'json',
            })
        except ServiceError as exc:
            if t[2] - t[0] <= MIN_TILE_DEG:
                raise SystemExit(f'tile {t} refused even at {MIN_TILE_DEG} degrees: {exc}') from exc
            todo.extend(tiles(t, (t[2] - t[0]) / 2))
            continue
        ids.update(doc.get('objectIds') or [])
        done += 1
        print(f'  tile {done}: {len(ids):,} ids so far', flush=True)
    if not ids:
        raise SystemExit('FEMA returned no flood polygons over the Bay Area box: a failed fetch, not "no flood"')
    return sorted(ids)


def features(layer_url, ids, get=get_json):
    """Esri JSON features (attributes + geometry rings, WGS84), in id chunks.

    Esri JSON, not GeoJSON: every ArcGIS server speaks it, and a reader tests a point against a
    feature's rings by the even-odd rule, which needs no ring-orientation conversion.
    """
    out = []
    for i in range(0, len(ids), CHUNK):
        chunk = ids[i:i + CHUNK]
        try:
            doc = get(f'{layer_url}/query', {
                'objectIds': ','.join(map(str, chunk)), 'outFields': FIELDS, 'returnGeometry': 'true',
                'outSR': 4326, 'geometryPrecision': 6, 'f': 'json',
            })
        except ServiceError as exc:
            raise SystemExit(str(exc)) from exc
        got = doc.get('features')
        if got is None:
            raise SystemExit(f'{layer_url}: no "features" in the reply')
        if len(got) != len(chunk):
            raise SystemExit(f'{layer_url}: asked for {len(chunk)} features, got {len(got)}: a truncated set')
        out.extend(got)
        print(f'  {len(out):,} of {len(ids):,} features', flush=True)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    box = city_box(json.loads(PLACES.read_text(encoding='utf-8')))
    service, layer_id, layer_name = find_layer()
    layer_url = f'{service}/{layer_id}'
    print(f'{layer_name} at {layer_url}; box {box}', flush=True)
    ids = object_ids(layer_url, box)
    feats = features(layer_url, ids)
    doc = {'format': 'esrijson', 'spatialReference': {'wkid': 4326}, 'features': feats}
    args.out.mkdir(parents=True, exist_ok=True)
    blob = gzip.compress(json.dumps(doc, separators=(',', ':')).encode('utf-8'), mtime=0)
    (args.out / 'nfhl-bayarea.esrijson.gz').write_bytes(blob)
    zones = sorted({f['attributes'].get('FLD_ZONE') for f in feats if f.get('attributes')} - {None})
    manifest = {
        'source': 'FEMA National Flood Hazard Layer (public domain, US government work)', 'format': 'esrijson',
        'service': service, 'layer_id': layer_id, 'layer_name': layer_name, 'fields': FIELDS,
        'box_lonlat': box, 'box_from': str(PLACES.relative_to(REPO)), 'features': len(feats),
        'zones': zones, 'fetched_utc': dt.datetime.now(dt.UTC).isoformat(timespec='seconds'),
        'sha256_gz': hashlib.sha256(blob).hexdigest(),
    }
    (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=1) + '\n', encoding='utf-8')
    print(f'wrote {len(feats):,} features ({len(blob) / 1e6:.1f} MB gzipped), zones {zones}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
