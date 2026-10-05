"""Regenerate data/usa-locator.json, the United States silhouette in the
locator inset, from the Census Bureau's state outlines.

    python scripts/build_us_locator.py

The US twin of scripts/build_uk_locator.sh, written 2026-10-05 when the
Bay Area joined the live map and the inset had to mark it. The previous file
marked New York alone and came from a source nothing recorded, so it could
not be rebuilt; this one can.

Source: cb_2023_us_state_20m, the Census Bureau's 1:20,000,000 cartographic
boundary file (public domain, as a US federal work). It is fetched once into
data/census/ (gitignored) and converted to GeoJSON with the shapefile readers
scripts/build_bay_area_page.py already uses for the Bay Area's cities.

Each ring is drawn as its own polygon. At 1:20m no state carries a hole that
shows at 170 px, and build_locator.py drops rings under --min-area anyway.

Markers: New York at its own coordinate (as before), and the Bay Area at the
bbox centre of data/us-bayarea-cities.json - the file the map draws - so the
marker cannot sit where the map is not. Marker NAMES must match
LOCATOR_TO_CITY in index.html; tests/locator-verify.mjs and
tests/bayarea-map.mjs read the markers through it.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import build_bay_area_page as page  # noqa: E402  (the shapefile readers)

NAME = 'cb_2023_us_state_20m'
URL = f'https://www2.census.gov/geo/tiger/GENZ2023/shp/{NAME}.zip'
ZIP = ROOT / 'data' / 'census' / f'{NAME}.zip'
GEOJSON = ROOT / 'data' / 'census' / 'us-states.json'


def fetch() -> None:
    if ZIP.exists():
        return
    ZIP.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(URL, headers=page.UA)
    ZIP.write_bytes(urllib.request.urlopen(req, timeout=120).read())
    print(f'fetched {URL}')


def convert() -> int:
    with zipfile.ZipFile(ZIP) as z:
        rows = page.read_dbf(z.read(f'{NAME}.dbf'))
        shapes = page.read_shp(z.read(f'{NAME}.shp'))
    if len(rows) != len(shapes):
        sys.exit(f'{NAME}: {len(rows)} records against {len(shapes)} shapes')
    features = [
        {
            'type': 'Feature',
            'properties': {'name': row['NAME']},
            'geometry': {'type': 'MultiPolygon', 'coordinates': [[[list(p) for p in ring]] for ring in rings]},
        }
        for row, rings in zip(rows, shapes, strict=True)
    ]
    # A floor, so a reader that silently returns nothing cannot write an empty map.
    if len(features) < 50:
        sys.exit(f'{NAME}: only {len(features)} states read')
    GEOJSON.write_text(json.dumps({'type': 'FeatureCollection', 'features': features}), encoding='utf-8')
    return len(features)


def main() -> int:
    fetch()
    print(f'{convert()} states read from {NAME}')
    return subprocess.run(  # noqa: S603  (our own script, fixed arguments)
        [
            sys.executable,
            str(ROOT / 'scripts' / 'build_locator.py'),
            '--src',
            str(GEOJSON),
            '--out',
            str(ROOT / 'data' / 'usa-locator.json'),
            '--region',
            'Contiguous United States',
            '--unit',
            'cities',
            '--projection',
            'albers-us',
            '--exclude',
            'Alaska',
            'Hawaii',
            'Puerto Rico',
            '--city',
            'New York City:40.7128:-74.0060',
            '--city-bbox',
            'San Francisco Bay Area:data/us-bayarea-cities.json',
        ],
        cwd=ROOT,
        check=False,
    ).returncode


if __name__ == '__main__':
    sys.exit(main())
