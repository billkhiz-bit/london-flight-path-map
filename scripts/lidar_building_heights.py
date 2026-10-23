"""Building heights from the Environment Agency's lidar survey: a pilot for one council area (2026-10-23, Bill).

WHY. The audience at a talk asked "is it the land or the building? A flat on a high floor hears a road
differently." Sky Score's figures are for a postcode at street level, and a building's height cannot say which
floor a flat is on, so a height is NEVER scored (DEFRA's road model already accounts for buildings; planes are
1,000 ft and more above any roof). It may become a plain fact beside a street: "most homes here are in buildings of
1-2 storeys". OS's own building heights cannot feed the API or reports (its licence; ROADMAP), so this is the OPEN
route: the EA's survey and OS Open Map Local outlines, both under the Open Government Licence.

HOW. For each building outline (OS Open Map Local, its centre inside the council area's real boundary), the
height is a high percentile (p90) of SURFACE minus GROUND over the 1 m pixels inside the outline: the EA's 2022
lidar composites, first-return DSM and DTM, read tile by tile (5 km OS tiles), so a building across a tile edge is
measured from every tile it touches. Pixels the National LIDAR Programme's vegetation layer marks as trees, where
it covers, are dropped. Storeys = the MEDIAN roof height / 3 m, rounded (validated 2026-10-23 against 842
OpenStreetMap buildings with building:levels: no bias, 74% exact, 96% within one storey; 99% for 1-2 storeys, 93%
for 3-4, 76% for 5-9; towers of 10+ read about 3 storeys low, 14 buildings). The p90 (the ridge of a pitched
roof) read one storey HIGH (+1.0), which is why it is the height in metres and not the storey count. The tiles come from the Defra Data Services
Platform's keyless tile catalogue (the route its own download page uses), the outlines from OS's keyless
downloads API; both land in gitignored data/lidar/.

    python scripts/lidar_building_heights.py --fetch --borough Hounslow     # ~1-1.5 GB: tiles + outlines
    python scripts/lidar_building_heights.py --measure --borough Hounslow   # data/lidar/<borough>-buildings.csv
    python scripts/lidar_building_heights.py --validate --borough Hounslow  # against OpenStreetMap's height tags
    python scripts/lidar_building_heights.py --postcodes --borough Hounslow # data/lidar/<borough>-postcodes.csv

--postcodes links buildings to postcodes the way that needs no new licence: every live postcode of the council
(NSPL, at ONS's own grid reference, adsb_postcode_averages.covered_postcodes) and the measured buildings within
NEAR_M of it with a footprint of at least MIN_FOOTPRINT_M2 (sheds and garages out), counted two ways: most
BUILDINGS (each once) and most FLOOR SPACE (footprint x storeys, nearer to where people live). They differ for a
block of flats among houses (12.7% of Hounslow's postcodes); which one a page says is Bill's call. Matching each
address to its own building needs ONS's address file, whose postcodes ONS says it has "no formal agreement" over.

PILOT RESULTS, Hounslow, 2026-10-23 (data in gitignored data/lidar/, 1.6 GB): 26,535 of 26,687 buildings measured;
storeys within one of OpenStreetMap for 96% of 842 (above); 4,933 postcodes, 57 with no building within 50 m.

--validate reads OpenStreetMap's height and building:levels tags through the Overpass API as an INDEPENDENT check
only: OSM is under the ODbL, so its values are compared and counted here and never stored or published.

Needs numpy, pyproj, rasterio and pyshp (pip install pyshp: pure Python, MIT).
"""

import argparse
import csv
import io
import json
import math
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
LIDAR = ROOT / 'data' / 'lidar'
BOROUGHS = ROOT / 'data' / 'london-boroughs.json'
UA = {'User-Agent': 'SkyScore/1.0 (support@skyscore.co.uk)'}
CATALOGUE = 'https://environment.data.gov.uk/backend/catalog/api/tiles/collections/survey/search'
LAYERS = {  # what to fetch: product, year, resolution
    'dtm': ('lidar_composite_dtm', '2022', '1'),
    'dsm': ('lidar_composite_first_return_dsm', '2022', '1'),
    'vom': ('national_lidar_programme_vom', None, '1'),  # the newest survey year that covers each tile
}
OS_DOWNLOADS = 'https://api.os.uk/downloads/v1/products/OpenMapLocal/downloads'
TILE = 5000  # metres
PERCENTILE = 90  # the roof, not the walls or a chimney
STOREY_M = 3.0
TREE_M = 0.5  # a vegetation-layer value above this marks a tree pixel
NODATA_BELOW = -100  # EA rasters mark no data with large negatives


def borough_rings(name):
    """The council area's outline as rings of OS grid (x, y)."""
    geo = json.loads(BOROUGHS.read_text(encoding='utf-8'))
    feat = next(f for f in geo['features'] if json.dumps(f['properties']).lower().find(name.lower()) >= 0)
    to_bng = Transformer.from_crs('EPSG:4326', 'EPSG:27700', always_xy=True)
    g = feat['geometry']
    polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
    return [[to_bng.transform(lon, lat) for lon, lat in ring] for poly in polys for ring in poly]


def inside(x, y, rings):
    """Even-odd point in polygon over every ring (a bounding box is not containment)."""
    hit = False
    for ring in rings:
        j = len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                hit = not hit
            j = i
    return hit


def extent(rings):
    xs = [x for r in rings for x, _ in r]
    ys = [y for r in rings for _, y in r]
    return min(xs), min(ys), max(xs), max(ys)


def get(url, data=None, headers=None, timeout=600):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as res:  # noqa: S310 - fixed https government URLs
        return res.read()


def fetch(name):
    rings = borough_rings(name)
    x0, y0, x1, y1 = extent(rings)
    to_wgs = Transformer.from_crs('EPSG:27700', 'EPSG:4326', always_xy=True)
    corners = [to_wgs.transform(x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))]
    body = json.dumps({'type': 'Polygon', 'coordinates': [corners]}).encode()
    found = json.loads(get(CATALOGUE, body, {'Content-Type': 'application/geo+json'}))['results']
    want = {}
    for layer, (product, year, res) in LAYERS.items():
        rows = [r for r in found if r['product']['id'] == product and r['resolution']['id'] == res
                and (year is None or r['year']['id'] == year)]
        for r in sorted(rows, key=lambda r: r['year']['id']):  # the newest year wins per tile
            want[(layer, r['tile']['id'])] = r['uri']
    for (layer, tile), uri in sorted(want.items()):
        out = LIDAR / layer / f'{tile}.zip'
        if out.exists():
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        blob = get(uri)
        if blob[:2] != b'PK':  # a 200 is not the product (CLAUDE.md): test the magic bytes
            raise SystemExit(f'{layer} {tile}: not a zip ({blob[:60]!r})')
        out.write_bytes(blob)
        print(f'fetched {layer} {tile} ({len(blob) / 1e6:.0f} MB)', flush=True)
    # OS Open Map Local outlines: the 100 km square holding the borough (TQ for London), Building layer only.
    square = 'TQ'
    shp = LIDAR / 'os' / f'{square}_Building.shp'
    if not shp.exists():
        listing = json.loads(get(f'{OS_DOWNLOADS}?area={square}'))
        url = next(d['url'] for d in listing if d['format'].startswith('ESRI'))
        blob = get(url)
        if blob[:2] != b'PK':
            raise SystemExit(f'OS Open Map Local {square}: not a zip')
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for member in z.namelist():
                if Path(member).stem == f'{square}_Building':
                    (LIDAR / 'os').mkdir(parents=True, exist_ok=True)
                    (LIDAR / 'os' / Path(member).name).write_bytes(z.read(member))
        print(f'fetched OS Open Map Local {square} buildings ({len(blob) / 1e6:.0f} MB zip)', flush=True)
    return 0


def tile_raster(layer, tile):
    """(array, x origin, y origin) of a tile's 1 m raster, top-left pixel corner; None when not fetched."""
    path = LIDAR / layer / f'{tile}.zip'
    if not path.exists():
        return None
    with zipfile.ZipFile(path) as z:
        tif = next(n for n in z.namelist() if n.lower().endswith('.tif'))
        tfw = next(n for n in z.namelist() if n.lower().endswith('.tfw'))
        a, _b, _c, d, e, f = (float(v) for v in z.read(tfw).decode().split())
        if (a, d) != (1.0, -1.0):
            raise SystemExit(f'{layer} {tile}: not a 1 m north-up grid ({a}, {d})')
        import rasterio  # noqa: PLC0415 - only the measuring step needs it
        with rasterio.MemoryFile(z.read(tif)) as mem, mem.open() as src:
            arr = src.read(1).astype(np.float32)
    return arr, e - 0.5, f + 0.5  # the world file gives the centre of the top-left pixel


def tile_id(x, y):
    return f'TQ{(int(x) // TILE * TILE - 500000) // 1000:02d}{(int(y) // TILE * TILE - 100000) // 1000:02d}'


def buildings(rings):
    """OS outlines whose centre is inside the council area: [(id, points)], points as (x, y)."""
    import shapefile  # noqa: PLC0415
    out = []
    with shapefile.Reader(str(LIDAR / 'os' / 'TQ_Building.shp')) as r:
        x0, y0, x1, y1 = extent(rings)
        for i, sr in enumerate(r.iterShapeRecords()):
            pts = sr.shape.points
            if not pts:
                continue
            bx0, by0, bx1, by1 = sr.shape.bbox
            if bx1 < x0 or bx0 > x1 or by1 < y0 or by0 > y1:
                continue
            cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
            if inside(cx, cy, rings):
                rec = sr.record.as_dict()
                out.append((rec.get('ID') or str(i), pts, (bx0, by0, bx1, by1)))
    return out


def polygon_mask(pts, x0, y1, w, h):
    """Pixels of a w x h window (top-left corner x0, y1) whose centres fall inside the outline."""
    xs = x0 + np.arange(w) + 0.5
    ys = y1 - np.arange(h) - 0.5
    gx, gy = np.meshgrid(xs, ys)
    hit = np.zeros(gx.shape, dtype=bool)
    p = np.asarray(pts)
    j = len(p) - 1
    for i in range(len(p)):
        xi, yi = p[i]
        xj, yj = p[j]
        if yi != yj:
            cross = ((yi > gy) != (yj > gy)) & (gx < (xj - xi) * (gy - yi) / (yj - yi) + xi)
            hit ^= cross
        j = i
    return hit


def measure(name):
    rings = borough_rings(name)
    blds = buildings(rings)
    print(f'{len(blds):,} OS building outlines with their centre inside {name}', flush=True)
    by_tile = {}
    for k, (_bid, _pts, (bx0, by0, bx1, by1)) in enumerate(blds):
        for tx in range(int(bx0) // TILE, int(bx1) // TILE + 1):
            for ty in range(int(by0) // TILE, int(by1) // TILE + 1):
                by_tile.setdefault(tile_id(tx * TILE, ty * TILE), []).append(k)
    values = [[] for _ in blds]
    trees = [0] * len(blds)
    for tile, ks in sorted(by_tile.items()):
        dtm, dsm, vom = tile_raster('dtm', tile), tile_raster('dsm', tile), tile_raster('vom', tile)
        if dtm is None or dsm is None:
            print(f'  {tile}: no DTM or DSM fetched; {len(ks)} buildings lose its pixels', flush=True)
            continue
        ground, gx0, gy1 = dtm
        surface = dsm[0]
        canopy = vom[0] if vom is not None else None
        for k in ks:
            _bid, pts, (bx0, by0, bx1, by1) = blds[k]
            c0 = max(0, int(math.floor(bx0 - gx0)))
            c1 = min(ground.shape[1], int(math.ceil(bx1 - gx0)))
            r0 = max(0, int(math.floor(gy1 - by1)))
            r1 = min(ground.shape[0], int(math.ceil(gy1 - by0)))
            if c1 <= c0 or r1 <= r0:
                continue
            mask = polygon_mask(pts, gx0 + c0, gy1 - r0, c1 - c0, r1 - r0)
            g = ground[r0:r1, c0:c1][mask]
            s = surface[r0:r1, c0:c1][mask]
            ok = (g > NODATA_BELOW) & (s > NODATA_BELOW)
            if canopy is not None:
                tree = canopy[r0:r1, c0:c1][mask] > TREE_M
                trees[k] += int((tree & ok).sum())
                ok &= ~tree
            values[k].append(s[ok] - g[ok])
    out = LIDAR / f'{name.lower().replace(" ", "-")}-buildings.csv'
    heights = []
    with open(out, 'w', newline='', encoding='utf-8') as fh:
        wr = csv.writer(fh)
        wr.writerow(['os_id', 'easting', 'northing', 'pixels', 'tree_pixels', 'height_p50_m', 'height_p90_m', 'storeys_est'])
        for (bid, _pts, (bx0, by0, bx1, by1)), vals, nt in zip(blds, values, trees, strict=True):
            v = np.concatenate(vals) if vals else np.array([])
            if v.size < 4:  # too small to measure: a kiosk, or no data
                wr.writerow([bid, round((bx0 + bx1) / 2), round((by0 + by1) / 2), v.size, nt, '', '', ''])
                continue
            p50, p90 = float(np.percentile(v, 50)), float(np.percentile(v, PERCENTILE))
            heights.append(p90)
            wr.writerow([bid, round((bx0 + bx1) / 2), round((by0 + by1) / 2), v.size, nt, round(p50, 1), round(p90, 1),
                         storeys(p50)])
    h = np.asarray(heights)
    print(f'wrote {out.relative_to(ROOT)}: {len(h):,} measured of {len(blds):,}')
    if len(h):
        for lo, hi in ((0, 6), (6, 12), (12, 21), (21, 36), (36, 1000)):
            n = int(((h >= lo) & (h < hi)).sum())
            print(f'  {lo:>3}-{hi if hi < 1000 else "":<3} m: {n:7,} ({n / len(h):.0%})')
    return 0


def validate(name):
    """Compare with OpenStreetMap's height and building:levels tags, read now and never stored."""
    rings = borough_rings(name)
    to_wgs = Transformer.from_crs('EPSG:27700', 'EPSG:4326', always_xy=True)
    to_bng = Transformer.from_crs('EPSG:4326', 'EPSG:27700', always_xy=True)
    x0, y0, x1, y1 = extent(rings)
    (w, s), (e, n) = to_wgs.transform(x0, y0), to_wgs.transform(x1, y1)
    q = f'[out:json][timeout:120];way["building"]["height"]({s},{w},{n},{e});out center tags;way["building"]["building:levels"]({s},{w},{n},{e});out center tags;'
    osm = json.loads(get('https://overpass-api.de/api/interpreter', urllib.parse.urlencode({'data': q}).encode()))
    ours = {}
    with open(LIDAR / f'{name.lower().replace(" ", "-")}-buildings.csv', encoding='utf-8') as fh:
        for row in csv.DictReader(fh):
            if row['height_p90_m']:
                ours[(int(row['easting']), int(row['northing']))] = (float(row['height_p90_m']), int(row['storeys_est']))
    grid = {}
    for (x, y), v in ours.items():
        grid.setdefault((x // 20, y // 20), []).append((x, y, v))
    dh, dl = [], []
    for el in osm['elements']:
        c = el.get('center')
        if not c:
            continue
        x, y = to_bng.transform(c['lon'], c['lat'])
        if not inside(x, y, rings):
            continue
        near = [(math.hypot(px - x, py - y), v) for gx in range(int(x // 20) - 1, int(x // 20) + 2)
                for gy in range(int(y // 20) - 1, int(y // 20) + 2) for px, py, v in grid.get((gx, gy), [])]
        if not near:
            continue
        dist, (hm, st) = min(near)
        if dist > 10:
            continue
        tags = el.get('tags', {})
        try:
            if 'height' in tags:
                dh.append(hm - float(tags['height'].split()[0].rstrip('m')))
            if 'building:levels' in tags:
                dl.append(st - int(float(tags['building:levels'])))
        except ValueError:
            continue
    for label, d, unit, near_ok in (('height', dh, 'm', 3), ('storeys', dl, 'storeys', 1)):
        d = np.asarray(d)
        if len(d):
            print(f'{label}: {len(d):,} matched; median error {np.median(d):+.1f} {unit}, median absolute '
                  f'{np.median(np.abs(d)):.1f} {unit}, within {near_ok} {unit}: {(np.abs(d) <= near_ok).mean():.0%}')
        else:
            print(f'{label}: no OSM buildings matched')
    return 0


NEAR_M = 50
MIN_FOOTPRINT_M2 = 40
BANDS = ((1, 2, '1 to 2 storeys'), (3, 5, '3 to 5 storeys'), (6, 9, '6 to 9 storeys'), (10, 999, '10 or more storeys'))


def storeys(height_p50_m):
    """Storeys from the median roof height: validated against OpenStreetMap (docstring above)."""
    return max(1, round(height_p50_m / STOREY_M))


def band(n):
    return next(label for lo, hi, label in BANDS if lo <= n <= hi)


def near_summary(near):
    """(most buildings' band, most floor space's band, tallest storeys) for [(footprint m2, storeys)], or None."""
    if not near:
        return None
    by_count, by_floor = {}, {}
    for area, st in near:
        b = band(st)
        by_count[b] = by_count.get(b, 0) + 1
        by_floor[b] = by_floor.get(b, 0) + area * st
    # Ties go to the LOWER band (BANDS order), so a fact never overstates the height of a street.
    order = [label for _lo, _hi, label in BANDS]
    most = lambda counts: max(counts, key=lambda k: (counts[k], -order.index(k)))  # noqa: E731
    return most(by_count), most(by_floor), max(st for _a, st in near)


def postcodes(name):
    sys.path.insert(0, str(ROOT / 'scripts'))
    import adsb_postcode_averages as apa  # noqa: PLC0415 - reads NSPL; only this step needs it
    import build_borough_bands as bands  # noqa: PLC0415
    lad = next((code for code, (_city, borough) in bands.load_lad_map().items() if borough.lower() == name.lower()), None)
    if lad is None:
        raise SystemExit(f'{name} is not a council area the API covers')
    pcs, _left = apa.covered_postcodes({lad: bands.load_lad_map()[lad]})
    slug = name.lower().replace(' ', '-')
    grid = {}
    with open(LIDAR / f'{slug}-buildings.csv', encoding='utf-8') as fh:
        for r in csv.DictReader(fh):
            if r['height_p50_m'] and int(r['pixels']) >= MIN_FOOTPRINT_M2:
                x, y = int(r['easting']), int(r['northing'])
                grid.setdefault((x // NEAR_M, y // NEAR_M), []).append((x, y, int(r['pixels']), storeys(float(r['height_p50_m']))))
    out = LIDAR / f'{slug}-postcodes.csv'
    none = 0
    with open(out, 'w', newline='', encoding='utf-8') as fh:
        wr = csv.writer(fh)
        wr.writerow(['postcode', f'buildings_within_{NEAR_M}m', 'most_buildings', 'most_floor_space', 'tallest_storeys'])
        for pc, _lad, _city, e, n, _gridind in pcs:
            near = [(area, st) for gx in range(int(e // NEAR_M) - 1, int(e // NEAR_M) + 2)
                    for gy in range(int(n // NEAR_M) - 1, int(n // NEAR_M) + 2)
                    for x, y, area, st in grid.get((gx, gy), []) if math.hypot(x - e, y - n) <= NEAR_M]
            s = near_summary(near)
            none += s is None
            wr.writerow([pc, len(near), *(s or ('', '', ''))])
    print(f'wrote {out.relative_to(ROOT)}: {len(pcs):,} postcodes, {none:,} with no measured building within {NEAR_M} m')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--borough', default='Hounslow')
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--fetch', action='store_true')
    g.add_argument('--measure', action='store_true')
    g.add_argument('--validate', action='store_true')
    g.add_argument('--postcodes', action='store_true')
    a = ap.parse_args()
    if a.fetch:
        return fetch(a.borough)
    if a.measure:
        return measure(a.borough)
    if a.postcodes:
        return postcodes(a.borough)
    return validate(a.borough)


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.exit(main())
