#!/usr/bin/env python3
"""Fetch Environment Agency flood risk (RoFRS) for a city as a classified GeoTIFF.

WHY THIS IS AWKWARD, AND WHY IT IS STILL THE RIGHT SOURCE
---------------------------------------------------------
Flood risk was the last of the three borough fill layers with no source at all:
curated for London and New York, absent for the other seven cities, and until
2026-08-11 defaulted to 'low' by the renderer, which painted a reassuring claim
over places nobody had checked.

The Environment Agency's national assessment - Risk of Flooding from Rivers and
Sea, NAFRA2 - is the right dataset. Getting at it is the awkward part, and the
routes that did NOT work are worth recording so they are not retried:

  * There is no WCS and no WFS. `/spatialdata/<slug>/wcs` and `/wfs` both 404
    for this dataset, unlike the road-noise dataset which serves a clean WCS.
  * `/ows`, `/wfs` and `/geoserver/ows` on the same host also 404.
  * The published postcode-level product ("Postcodes in Areas at Risk") is
    RETIRED and offers no download.
  * Bulk download is a browser "select an area of interest" workflow, which is
    exactly the barrier the road-noise WCS removed for that dataset.

What IS available is a WMS, and it is a VECTOR layer behind that WMS - so
GetFeatureInfo returns the authoritative `risk_band` attribute per feature. That
is one HTTP request per point, which is fine for verification and hopeless for
the ~500,000 postcodes across our cities.

So this renders the layer to an image and decodes the classes back out.

WHY THAT IS SAFE HERE, AND WHERE IT IS NOT
-------------------------------------------
Decoding a rendered image is normally a bad idea: antialiasing blends class
colours, and an upstream style change silently rewrites your data. Both are
handled, and neither is assumed:

  * `format_options=antialias:none` is LOAD-BEARING. Without it a single tile
    carries 16,289 distinct colours and class edges are unrecoverable; with it,
    exactly 5.
  * The colour to band mapping below was VERIFIED against the service's own
    `risk_band` attribute by point-in-polygon containment, not by reading the
    legend. An earlier check that trusted "the first feature returned" made High
    and Medium look interchangeable - a 200 m query box spans several 50 m
    polygons, so features[0] is arbitrary. Containment resolved it: High 4/4,
    Medium 4/4, Low 3/3, Very low 3/3.
  * `--verify` re-runs that check. Run it after any upstream restyle. If the
    palette changes, this script must fail rather than silently reclassify.

RENDERING IS SCALE DEPENDENT. Nothing draws at 25 m/px; 10 m/px works. Tiles are
therefore 20 km at 2000x2000 px, which is 10 m/px and inside GeoServer's default
2048 limit. The source data is 50 m cells, so 10 m/px oversamples rather than
loses detail.

ENGLAND ONLY. RoFRS is an Environment Agency product; Natural Resources Wales
publishes Welsh flood maps separately, so Cardiff is skipped by name rather than
fetched into a misleading empty raster.

  pip install rasterio pillow numpy pyproj
  python scripts/fetch_ea_flood_risk.py --verify
  python scripts/fetch_ea_flood_risk.py --city london
  python scripts/fetch_ea_flood_risk.py --all
"""

from __future__ import annotations

import argparse
import io
import json
import random
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / 'data'
TILE_DIR = DATA / 'flood_risk_tiles'

WMS = 'https://environment.data.gov.uk/spatialdata/nafra2-risk-of-flooding-from-rivers-and-sea/wms'
LAYER = 'rofrs_4band'
UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/126.0 Safari/537.36'
)

# 10 m/px: 20 km across 2000 px. Anything coarser than ~10 m/px renders blank.
TILE_M = 20000
TILE_PX = 2000
# Metres per pixel. Every tile is requested AND mosaicked at this resolution;
# the two used to be derived separately, which is how they came to disagree.
RES_M = TILE_M // TILE_PX
PAUSE_S = 1.0
RETRIES = 4

# VERIFIED, not read off the legend. See the module docstring.
# Codes are ordered by severity so a numeric comparison means what it looks like.
BAND_CODE = {
    (255, 255, 255, 0): 0,  # no feature - not in any modelled risk polygon
    (200, 247, 255, 255): 1,  # Very low   - below 0.1% annual chance
    (195, 224, 255, 255): 2,  # Low        - 0.1% to 1%
    (154, 159, 222, 255): 3,  # Medium     - 1% to 3.3%
    (85, 91, 157, 255): 4,  # High       - 3.3% or greater
    (110, 110, 110, 255): 255,  # Unavailable - modelled data not published here
}
CODE_NAME = {0: 'none', 1: 'Very low', 2: 'Low', 3: 'Medium', 4: 'High', 255: 'Unavailable'}

NO_COVERAGE = {'cardiff', 'nyc'}


def fetch_bytes(url, timeout=240):
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=timeout).read()


def getmap_url(bbox, width, height):
    return (
        f'{WMS}?service=WMS&version=1.1.1&request=GetMap&layers={LAYER}&styles='
        f'&srs=EPSG:27700&bbox={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}'
        f'&width={width}&height={height}&format=image/png&transparent=true'
        # Load-bearing. Without it a tile carries 16,289 colours instead of 5.
        f'&format_options=antialias:none'
    )


def classify(rgba):
    """RGBA array -> uint8 band codes. Unknown colours raise rather than guess."""
    import numpy as np

    h, w, _ = rgba.shape
    flat = rgba.reshape(-1, 4)
    out = np.zeros(flat.shape[0], dtype='uint8')
    seen = set(map(tuple, np.unique(flat, axis=0)))
    unknown = seen - set(BAND_CODE)
    if unknown:
        # Refuse rather than bucket an unrecognised colour into a band. A style
        # change upstream must break this loudly; silently reclassifying flood
        # risk is the failure this whole exercise exists to stop.
        raise SystemExit(
            f'unrecognised colours in the RoFRS render: {sorted(unknown)[:6]}\n'
            'The upstream style has changed. Re-run with --verify and update BAND_CODE.'
        )
    for colour, code in BAND_CODE.items():
        mask = (flat == np.array(colour, dtype=flat.dtype)).all(axis=1)
        out[mask] = code
    return out.reshape(h, w)


def tile_px(bbox):
    """Pixel size for a tile rendered at exactly RES_M per pixel.

    LOAD-BEARING, and the fix for a defect that published wrong flood figures in
    10 of the 11 covered cities. Edge tiles are CLIPPED to the city bbox (see
    fetch_city), so their extent is smaller than TILE_M - but this function used
    to be a constant, TILE_PX, and every tile was requested 2000x2000 whatever
    ground it covered. A 5 km-wide edge tile therefore rendered at 2.5 m/px and
    was pasted by the mosaic as if 10 m/px, stretching real flood polygons 4x
    out of position. Only Nottingham escaped: its 40x40 km bbox is the one exact
    multiple of the 20 km tile.

    Nothing downstream could see it. build_borough_bands.py --check re-derives
    the borough percentages by sampling the same mosaic, so the two things it
    compares are the file and itself.

    The city bbox is snapped to 1 km (fetch_defra_road_noise.city_bbox), so both
    divisions are always exact.
    """
    return (bbox[2] - bbox[0]) // RES_M, (bbox[3] - bbox[1]) // RES_M


def fetch_tile(path, bbox):
    """Download and classify one tile, skipping if already present."""
    import numpy as np
    from PIL import Image

    if path.exists() and path.stat().st_size > 200:
        print(f'  skip {path.name} (have it)')
        return True

    for attempt in range(1, RETRIES + 1):
        try:
            raw = fetch_bytes(getmap_url(bbox, *tile_px(bbox)))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            print(f'  {path.name}: attempt {attempt}/{RETRIES} failed ({exc})')
            time.sleep(PAUSE_S * attempt * 2)
            continue
        if raw[:4] != b'\x89PNG':
            print(f'  {path.name}: attempt {attempt}/{RETRIES} returned non-PNG ({len(raw)} bytes)')
            time.sleep(PAUSE_S * attempt * 2)
            continue
        arr = np.array(Image.open(io.BytesIO(raw)).convert('RGBA'))
        codes = classify(arr)
        nz = int((codes > 0).sum())
        # A WHOLLY UNCLASSIFIED TILE IS AN OUTAGE, NOT A SAFE AREA.
        #
        # (255,255,255,0) is a KNOWN colour meaning 'not in any modelled risk
        # polygon', so a fully transparent render sails through classify()
        # without raising and becomes 100% code 0 - which reads downstream as
        # 'low flood risk, fully surveyed'. Every way this service can fail
        # while still returning a valid PNG produces exactly that image: a
        # renamed layer, an outage behind a 200, or a request above the ~10 m/px
        # scale limit at which RoFRS draws nothing at all.
        #
        # And it would be PERMANENT. The 4 MB .npy defeats the `st_size > 200`
        # skip at the top of this function, so a re-run says 'have it' and the
        # bad tile outlives the outage that produced it.
        #
        # Retried rather than aborted: a transient outage is the likeliest
        # cause, and the loop already backs off. If every attempt comes back
        # blank the function returns False and the caller reports the failure.
        if nz == 0:
            print(
                f'  {path.name}: attempt {attempt}/{RETRIES} classified 0% - '
                'a blank render is an outage, not a risk-free area. Not caching.'
            )
            time.sleep(PAUSE_S * attempt * 2)
            continue
        np.save(path, codes)
        print(f'  got  {path.name} ({100 * nz / codes.size:5.1f}% classified)')
        return True

    print(f'  FAIL {path.name} after {RETRIES} attempts')
    return False


def fetch_city(city):
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from fetch_defra_road_noise import city_bbox  # single holder for the bbox rule

    if city in NO_COVERAGE:
        print(f'{city}: SKIPPED - outside the Environment Agency England coverage.')
        return 0

    bbox = city_bbox(city)
    TILE_DIR.mkdir(parents=True, exist_ok=True)
    tiles = []
    e = bbox[0]
    while e < bbox[2]:
        n = bbox[1]
        while n < bbox[3]:
            e2, n2 = min(e + TILE_M, bbox[2]), min(n + TILE_M, bbox[3])
            # The EXTENT is in the name, not just the origin. A clipped edge
            # tile and a full tile can share an origin while being different
            # images, and the cache skip in fetch_tile only tests existence - so
            # a name carrying (e, n) alone kept serving 2000x2000 renders of
            # 5 km tiles to every later run, outliving the bug that made them.
            # It also collided across cities, whose grids start at their own
            # min_e. Renaming is what invalidates the stale cache.
            tiles.append((TILE_DIR / f'flood_{e}_{n}_{e2 - e}x{n2 - n}.npy', (e, n, e2, n2)))
            n += TILE_M
        e += TILE_M

    print(f'\n{city}: {len(tiles)} tiles covering {bbox} at {RES_M} m/px')
    failed = [p.name for p, bb in tiles if not fetch_tile(p, bb) or time.sleep(PAUSE_S)]
    failed = [f for f in failed if f]
    if failed and len(failed) == len(tiles):
        # Every tile blank or unreachable is an outage, not a risk-free city.
        print(f'  ALL {len(tiles)} tiles failed - refusing to write a mosaic.')
        return 1
    if failed:
        # A city is NOT abandoned for one bad tile. Two of the eleven cities are
        # held by a single near-all-sea tile that the service renders blank at
        # every resolution tried (verified 2026-08-30 at 10, 5.5 and 5 m/px), and
        # in both cases the tile lies outside every borough or clips one corner.
        # Discarding a whole city's flood data over it would lose four boroughs
        # of good readings to an estuary. The gap is carried as Unavailable
        # instead, which is what that code means and what floodCoverage reports.
        print(f'  {len(failed)} of {len(tiles)} tiles missing: {", ".join(failed)}')
        print('  Their area is written as Unavailable, NOT as no-risk. Re-run to retry them.')

    # Mosaic the classified tiles into one GeoTIFF in the raster's own CRS, so
    # build_borough_bands.py can sample it exactly like the road-noise raster.
    min_e, min_n, max_e, max_n = bbox
    width = (max_e - min_e) // RES_M
    height = (max_n - min_n) // RES_M
    # 255 = Unavailable, NOT 0 = none.
    #
    # 0 is a REAL READING meaning 'surveyed, outside every modelled risk
    # polygon'. Initialising to it makes any pixel no tile ever wrote claim to
    # have been surveyed and found safe - absence rendered as a measurement,
    # the defect class this repo has now shipped six times. It was unreachable
    # while a single failed tile aborted the city; the moment a partial mosaic
    # became possible (above), the fill value became load-bearing.
    mosaic = np.full((height, width), 255, dtype='uint8')
    res = RES_M
    for path, (te, tn, te2, tn2) in tiles:
        if not path.exists():
            continue  # left as Unavailable by the fill above
        codes = np.load(path)
        col = (te - min_e) // res
        row = (max_n - tn2) // res
        h, w = codes.shape
        # A tile must match the ground it claims. This assertion is what the
        # mosaic lacked while it was pasting clipped edge tiles as if they were
        # full ones, and it is one subtraction: cheap enough that its absence
        # was the whole cost. It fires on a stale pre-2026-08-30 tile too.
        want_h, want_w = (tn2 - tn) // res, (te2 - te) // res
        if (h, w) != (want_h, want_w):
            raise SystemExit(
                f'{path.name}: {w}x{h} px for a {(te2 - te) / 1000:g}x{(tn2 - tn) / 1000:g} km '
                f'extent - expected {want_w}x{want_h} at {res} m/px. Delete it and re-fetch.'
            )
        mosaic[row : row + h, col : col + w] = codes[: height - row, : width - col]

    out = DATA / f'ea_flood_risk_{city}.tif'
    transform = from_origin(min_e, max_n, res, res)
    with rasterio.open(
        out, 'w', driver='GTiff', height=height, width=width, count=1,
        dtype='uint8', crs='EPSG:27700', transform=transform, compress='deflate',
    ) as dst:
        dst.write(mosaic, 1)

    counts = {CODE_NAME[c]: int((mosaic == c).sum()) for c in sorted(set(np.unique(mosaic)))}
    total = mosaic.size
    detail = ', '.join(f'{k} {100 * v / total:.1f}%' for k, v in counts.items())
    print(f'wrote {out.name} ({width}x{height}, {out.stat().st_size / 1e6:.1f} MB) - {detail}')
    return 0


def verify(samples=4):
    """Re-check the colour to band mapping against the service's own attribute.

    Uses point-in-polygon containment, NOT features[0]. A GetFeatureInfo query
    box spans several 50 m polygons, so the first feature returned is arbitrary
    and made High and Medium look interchangeable on the first attempt.
    """
    import numpy as np
    from PIL import Image

    def contains(ring, x, y):
        inside = False
        n = len(ring)
        for i in range(n):
            x1, y1 = ring[i][:2]
            x2, y2 = ring[(i + 1) % n][:2]
            if (y1 > y) != (y2 > y):
                if x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                    inside = not inside
        return inside

    def band_at(e, n):
        url = (
            f'{WMS}?service=WMS&version=1.1.1&request=GetFeatureInfo&layers={LAYER}'
            f'&query_layers={LAYER}&srs=EPSG:27700&bbox={e - 100},{n - 100},{e + 100},{n + 100}'
            f'&width=101&height=101&x=50&y=50&info_format=application/json&feature_count=25'
        )
        for attempt in range(4):
            try:
                doc = json.loads(fetch_bytes(url, 120))
                break
            except Exception:
                time.sleep(3.0 * (attempt + 1))
        else:
            return 'HTTPERR'
        for feature in doc.get('features', []):
            geom = feature.get('geometry') or {}
            polys = geom.get('coordinates', []) if geom.get('type') == 'MultiPolygon' else [geom.get('coordinates', [])]
            for poly in polys:
                if poly and contains(poly[0], e, n):
                    return feature['properties'].get('risk_band')
        return 'none'

    cx, cy, half, px = 535500, 179800, 4000, 800
    bbox = (cx - half, cy - half, cx + half, cy + half)
    arr = np.array(Image.open(io.BytesIO(fetch_bytes(getmap_url(bbox, px, px)))).convert('RGBA'))
    by_colour = defaultdict(list)
    for yy in range(0, px, 3):
        for xx in range(0, px, 3):
            by_colour[tuple(arr[yy, xx])].append((xx, yy))

    random.seed(3)
    expected = {0: 'none', 1: 'Very low', 2: 'Low', 3: 'Medium', 4: 'High'}
    bad = 0
    print('colour                    code  expected     observed')
    for colour, pts in sorted(by_colour.items(), key=lambda kv: -len(kv[1])):
        code = BAND_CODE.get(colour)
        if code is None:
            print(f'{str(colour):25s} UNKNOWN COLOUR')
            bad += 1
            continue
        if code == 255:
            continue  # Unavailable overlays polygons of every band; nothing to assert
        seen = defaultdict(int)
        for xx, yy in random.sample(pts, min(samples, len(pts))):
            e = bbox[0] + (xx + 0.5) * (bbox[2] - bbox[0]) / px
            n = bbox[3] - (yy + 0.5) * (bbox[3] - bbox[1]) / px
            seen[band_at(e, n)] += 1
            time.sleep(1.5)
        want = expected[code]
        got = {k: v for k, v in seen.items() if k != 'HTTPERR'}
        ok = got and all(k == want for k in got)
        if not ok:
            bad += 1
        print(f'{str(colour):25s} {code:4d}  {want:11s} {dict(seen)}  {"ok" if ok else "MISMATCH"}')

    print('\nmapping verified' if not bad else f'\n{bad} colour(s) disagree with the service')
    return 0 if not bad else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--city')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--verify', action='store_true', help='re-check the colour mapping upstream')
    args = ap.parse_args()

    if args.verify:
        return verify()
    if args.all:
        cities = sorted(p.name.replace('-boroughs.json', '') for p in DATA.glob('*-boroughs.json'))
    elif args.city:
        cities = [args.city]
    else:
        ap.error('pass --city <key>, --all, or --verify')

    rc = 0
    for city in cities:
        rc |= fetch_city(city)
    return rc


if __name__ == '__main__':
    sys.exit(main())
