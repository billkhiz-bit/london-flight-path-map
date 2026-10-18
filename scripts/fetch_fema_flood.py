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
  (ROADMAP: a county's DFIRM can reach over its line), and only in tiles that touch a city's own
  box: the overall box reaches into Santa Cruz County, whose records FEMA refuses to serve at all
  (run 39137323723: ids 352386-352389, even attributes refused).
- The layer is found BY NAME ("Flood Hazard Zones") in the service's own layer list, and the
  service is tried at both of FEMA's documented paths, because a layer id or path guessed from
  memory would fail silently as "no flood anywhere".
- Object ids first, searched tile by tile, then features in id chunks, so neither the service's
  record cap nor a heavy query can truncate the set. FEMA answers a heavy query in one of two ways,
  both seen on the US runner on 2026-10-17: a 400 "Failed to execute query" (run 39066895696,
  the whole box at once) or a dropped connection (run 39069350042, after 6,707 ids). Both are
  treated alike: the tile or chunk is SPLIT and retried, and only a refusal at the smallest size
  fails the run, naming what was refused.
- A fetch that finds NO features fails: an empty result is not "no flood risk" (the EA flood tile
  cached all-zero is this repo's precedent).
- Standard library only, so the runner installs nothing; a short pause between requests, because
  this is a shared public service.

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
# Run 39142466860: for a refused feature FEMA answered an EXTENT query (no fields) but refused even an
# attributes-only query with FIELDS, so the failure follows the fields, not the geometry. A feature refused
# alone is asked again with only what the reader needs; one refused even then has each field probed alone.
MIN_FIELDS = 'FLD_ZONE,SFHA_TF'
CHUNK = 100  # features per request; a refused chunk is halved, down to one feature
TILE_DEG = 0.1  # first search tile; a refused tile is split in four
MIN_TILE_DEG = 0.0125  # ...down to this, then the run fails naming the tile
MARGIN_DEG = 0.01
PAUSE_S = 0.3  # between requests: a shared public service
TRIES = 2  # per request before the tile or chunk is split instead
# A single polygon FEMA refuses even alone (run 39072503762: feature 352386, after all 169 tiles answered) is
# asked for again with its outline simplified by these tolerances in degrees (about 1, 5 and 20 m), and the
# tolerance used is recorded per id in the manifest. 20 m is negligible for the share of a city in a zone.
GENERALISE_DEG = (0.00001, 0.00005, 0.0002)
# Run 39134615637 refused feature 352386 even at 20 m, so its size is not the cause. A polygon refused at every
# tolerance is LEFT OUT and recorded with what FEMA will say about it (attributes, extent): the reader counts a
# resident in no polygon as UNKNOWN, never safe. More than this many is systemic, and fails the run.
MAX_REFUSED = 25  # near the cities; a systemic failure refuses thousands (run 4 refused 3 near, all tiny)
# A refused polygon whose extent touches no city's box cannot hold a city resident: it is recorded apart
# and does not count towards MAX_REFUSED (a box that misses every city box misses every city).
UA = {'User-Agent': 'Sky Score data fetch (skyscore.co.uk; public-domain FEMA NFHL)'}


class Ledger:
    """What the fetch had to do to a polygon: simplify it, or leave it out (near a city, or not)."""

    def __init__(self, near=None):
        self.near = near  # the cities' boxes; None means every refusal counts
        self.generalised, self.refused, self.outside = {}, {}, {}
        self.minimal = set()  # ids fetched with MIN_FIELDS only


class ServiceError(Exception):
    """The service answered, with an error body: a refusal."""


class NetworkError(Exception):
    """No answer after TRIES attempts: on FEMA, a dropped connection under a heavy query."""


def touches(a, b):
    """Whether two [xmin, ymin, xmax, ymax] boxes overlap."""
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def city_boxes(places_doc):
    """Each scored place's own box over its rings, with the margin."""
    out = []
    for p in places_doc['places']:
        if p['kind'] in ('city', 'town'):
            xs = [lon for ring in p['rings'] for lon, _ in ring]
            ys = [lat for ring in p['rings'] for _, lat in ring]
            out.append([min(xs) - MARGIN_DEG, min(ys) - MARGIN_DEG, max(xs) + MARGIN_DEG, max(ys) + MARGIN_DEG])
    return out


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


def get_json(url, params, tries=TRIES):
    query = urllib.parse.urlencode(params)
    for attempt in range(tries):
        try:
            req = urllib.request.Request(f'{url}?{query}', headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r:
                doc = json.loads(r.read().decode('utf-8'))
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as exc:
            if attempt == tries - 1:
                raise NetworkError(f'{url}: {exc} after {tries} tries') from exc
            time.sleep(5 * (attempt + 1))
            continue
        if 'error' in doc:  # ArcGIS answers 200 with an error body
            raise ServiceError(f'{url}: the service refused the request: {doc["error"]}')
        return doc
    raise NetworkError(f'{url}: unreachable')  # pragma: no cover


def find_layer(get=get_json):
    """(service url, layer id, layer name) for the flood hazard zone layer, found by name."""
    tried = []
    for service in SERVICES:
        try:
            doc = get(service, {'f': 'json'})
        except (ServiceError, NetworkError) as exc:
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


def object_ids(layer_url, box, get=get_json, near=None):
    """Every flood polygon id in the box's tiles that touch a city (`near`), tile by tile; a refused
    tile is split."""
    ids = set()
    todo = [t for t in tiles(box, TILE_DEG) if near is None or any(touches(t, c) for c in near)]
    done = split = 0
    while todo:
        t = todo.pop()
        try:
            doc = get(f'{layer_url}/query', {
                'where': '1=1', 'geometry': ','.join(map(str, t)), 'geometryType': 'esriGeometryEnvelope',
                'inSR': 4326, 'spatialRel': 'esriSpatialRelIntersects', 'returnIdsOnly': 'true', 'f': 'json',
            })
        except (ServiceError, NetworkError) as exc:
            if t[2] - t[0] <= MIN_TILE_DEG:
                raise SystemExit(f'tile {t} refused even at {MIN_TILE_DEG} degrees: {exc}') from exc
            todo.extend(tiles(t, (t[2] - t[0]) / 2))
            split += 1
            continue
        finally:
            time.sleep(PAUSE_S)
        ids.update(doc.get('objectIds') or [])
        done += 1
        if done % 10 == 0 or not todo:
            print(f'  {done} tiles answered ({split} split): {len(ids):,} ids', flush=True)
    if not ids:
        raise SystemExit('FEMA returned no flood polygons over the Bay Area box: a failed fetch, not "no flood"')
    return sorted(ids)


def refuse(layer_url, oid, get, ledger, exc):
    """Record a polygon FEMA will not return at any tolerance, with its attributes and extent where FEMA
    gives those, and leave it out. One whose extent touches no city is recorded apart; past MAX_REFUSED
    near the cities the run fails: that is no longer one bad outline."""
    note = {'error': str(exc)[:200], 'fields': {}}
    for field in FIELDS.split(','):  # which field FEMA cannot serve for this record
        try:
            get(f'{layer_url}/query', {'objectIds': str(oid), 'f': 'json', 'returnGeometry': 'false', 'outFields': field})
            note['fields'][field] = 'ok'
        except (ServiceError, NetworkError):
            note['fields'][field] = 'refused'
        finally:
            time.sleep(PAUSE_S)
    for key, extra in (('attributes', {'returnGeometry': 'false', 'outFields': MIN_FIELDS}),
                       ('extent', {'returnExtentOnly': 'true', 'outSR': 4326})):
        try:
            doc = get(f'{layer_url}/query', {'objectIds': str(oid), 'f': 'json', **extra})
            note[key] = ((doc.get('features') or [{}])[0].get('attributes') if key == 'attributes'
                         else doc.get('extent'))
        except (ServiceError, NetworkError) as e:
            note[key] = f'refused too: {e}'[:200]
        finally:
            time.sleep(PAUSE_S)
    ext = note.get('extent')
    if isinstance(ext, dict) and ledger.near is not None and not any(
            touches([ext['xmin'], ext['ymin'], ext['xmax'], ext['ymax']], c) for c in ledger.near):
        ledger.outside[oid] = note
        print(f'  feature {oid} refused, but its extent touches no city: left out, recorded apart', flush=True)
        return []
    if len(ledger.refused) >= MAX_REFUSED:
        raise SystemExit(f'feature {oid} is refused even simplified, after {sorted(ledger.refused)}: systemic ({exc})')
    ledger.refused[oid] = note
    print(f'  feature {oid} REFUSED at every tolerance: left out, recorded as {note}', flush=True)
    return []


def fetch_chunk(layer_url, chunk, get, ledger, offset=None, fields=FIELDS):
    """Esri JSON features for these ids. A refused chunk is halved; one id refused alone is asked for
    again with MIN_FIELDS, then with its outline simplified (GENERALISE_DEG), each recorded in the ledger;
    refused even then, it is left out and recorded (see refuse())."""
    params = {
        'objectIds': ','.join(map(str, chunk)), 'outFields': fields, 'returnGeometry': 'true',
        'outSR': 4326, 'geometryPrecision': 6, 'f': 'json',
    }
    if offset is not None:
        params['maxAllowableOffset'] = offset
    try:
        doc = get(f'{layer_url}/query', params)
    except (ServiceError, NetworkError) as exc:
        if len(chunk) > 1:
            half = len(chunk) // 2
            return (fetch_chunk(layer_url, chunk[:half], get, ledger)
                    + fetch_chunk(layer_url, chunk[half:], get, ledger))
        if fields != MIN_FIELDS:
            return fetch_chunk(layer_url, chunk, get, ledger, None, MIN_FIELDS)
        tried = GENERALISE_DEG if offset is None else GENERALISE_DEG[GENERALISE_DEG.index(offset) + 1:]
        if not tried:
            return refuse(layer_url, chunk[0], get, ledger, exc)
        return fetch_chunk(layer_url, chunk, get, ledger, tried[0], MIN_FIELDS)
    finally:
        time.sleep(PAUSE_S)
    got = doc.get('features')
    if got is None:
        raise SystemExit(f'{layer_url}: no "features" in the reply')
    if len(got) != len(chunk):
        raise SystemExit(f'{layer_url}: asked for {len(chunk)} features, got {len(got)}: a truncated set')
    if fields == MIN_FIELDS:
        ledger.minimal.add(chunk[0])
    if offset is not None:
        ledger.generalised[chunk[0]] = offset  # the tolerance that WORKED, recorded by the call that used it
    return got


def features(layer_url, ids, ledger, get=get_json):
    """Esri JSON features (attributes + geometry rings, WGS84), in id chunks.

    Esri JSON, not GeoJSON: every ArcGIS server speaks it, and a reader tests a point against a
    feature's rings by the even-odd rule, which needs no ring-orientation conversion.
    """
    out = []
    for i in range(0, len(ids), CHUNK):
        out.extend(fetch_chunk(layer_url, ids[i:i + CHUNK], get, ledger))
        if (i // CHUNK) % 10 == 9 or i + CHUNK >= len(ids):
            print(f'  {len(out):,} of {len(ids):,} features', flush=True)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    places = json.loads(PLACES.read_text(encoding='utf-8'))
    box, near = city_box(places), city_boxes(places)
    service, layer_id, layer_name = find_layer()
    layer_url = f'{service}/{layer_id}'
    print(f'{layer_name} at {layer_url}; box {box}', flush=True)
    ids = object_ids(layer_url, box, near=near)
    ledger = Ledger(near)
    feats = features(layer_url, ids, ledger)
    doc = {'format': 'esrijson', 'spatialReference': {'wkid': 4326}, 'features': feats}
    args.out.mkdir(parents=True, exist_ok=True)
    blob = gzip.compress(json.dumps(doc, separators=(',', ':')).encode('utf-8'), mtime=0)
    (args.out / 'nfhl-bayarea.esrijson.gz').write_bytes(blob)
    zones = sorted({f['attributes'].get('FLD_ZONE') for f in feats if f.get('attributes')} - {None})
    manifest = {
        'source': 'FEMA National Flood Hazard Layer (public domain, US government work)', 'format': 'esrijson',
        'service': service, 'layer_id': layer_id, 'layer_name': layer_name, 'fields': FIELDS,
        'box_lonlat': box, 'box_from': str(PLACES.relative_to(REPO)), 'features': len(feats),
        'zones': zones, 'generalised_deg': {str(k): v for k, v in sorted(ledger.generalised.items())},
        'refused': {str(k): v for k, v in sorted(ledger.refused.items())},
        'refused_outside_cities': {str(k): v for k, v in sorted(ledger.outside.items())},
        'minimal_fields': {'fields': MIN_FIELDS, 'ids': sorted(ledger.minimal)},
        'fetched_utc': dt.datetime.now(dt.UTC).isoformat(timespec='seconds'),
        'sha256_gz': hashlib.sha256(blob).hexdigest(),
    }
    (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=1) + '\n', encoding='utf-8')
    print(f'wrote {len(feats):,} features ({len(blob) / 1e6:.1f} MB gzipped), zones {zones}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
